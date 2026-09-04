import AppKit
import Foundation
import SwiftUI

extension NativeChecks {
    static func historyWriteProbe(_ state: URL) {
        do {
            let store = ChatStore(directory: state)
            var archive = try store.load()
            archive.conversations[0].messages.append(ChatMessage(role: "assistant", text: "Saved by another process"))
            try store.save(archive)
            print("WROTE")
        } catch { print("REFUSED") }
    }

    static func childHistoryWrite(_ state: URL) throws -> String {
        let process = Process(), output = Pipe()
        process.executableURL = URL(fileURLWithPath: CommandLine.arguments[0])
        process.arguments = ["--history-write-probe", state.path]
        process.standardOutput = output; process.standardError = FileHandle.nullDevice
        try process.run()
        let data = output.fileHandleForReading.readDataToEndOfFile()
        process.waitUntilExit()
        guard process.terminationStatus == 0 else { throw NativeError.message("History child process failed") }
        return String(decoding: data, as: UTF8.self).trimmingCharacters(in: .whitespacesAndNewlines)
    }

    @MainActor
    static func chatStorage(root: URL) throws {
        let state = root.appendingPathComponent("chat-storage")
        let store = ChatStore(directory: state)
        try check(try store.load().conversations.isEmpty && !FileManager.default.fileExists(atPath: state.path),
                  "History startup creates no files, directories, backups or locks")
        var first = Conversation(), second = Conversation()
        first.messages = [ChatMessage(role: "user", text: "Original conversation")]
        second.messages = [ChatMessage(role: "assistant", text: "Independent conversation")]
        var archive = ChatArchive(conversations: [first, second], selectedID: first.id)
        try store.save(archive)
        let manifest = try ChatHistoryFormat.manifest(Data(contentsOf: store.url))
        try check(manifest.version == 6 && manifest.conversations.count == 2,
                  "New history stores a small manifest and separate conversation objects")
        let before = try fileBytes(state)
        let independent = store.objectsDirectory.appendingPathComponent(manifest.conversations[1].sha256 + ".json")
        let independentStamp = try ChatHistoryFiles.stamp(independent)
        try store.save(archive)
        try check(try fileBytes(state) == before, "Saving unchanged history performs no data or snapshot writes")
        archive.conversations[0].draft = "Unsent updated draft"
        try store.save(archive)
        let afterManifest = try ChatHistoryFormat.manifest(Data(contentsOf: store.url))
        try check(afterManifest.conversations[1] == manifest.conversations[1]
                  && (try ChatHistoryFiles.stamp(independent)) == independentStamp,
                  "Editing one conversation never rewrites an unchanged conversation")
        try check(try ChatStore(directory: state).load().conversations == archive.conversations,
                  "Sharded history reloads all messages, settings and unsent drafts exactly")
        let stableObjectBytes = try Data(contentsOf: independent)
        try Data("damaged cached conversation".utf8).write(to: independent)
        let beforeCorruptSave = try fileBytes(state)
        var rejectedCorruptCache = false
        do { try store.save(archive) } catch { rejectedCorruptCache = true }
        try check(rejectedCorruptCache && (try fileBytes(state)) == beforeCorruptSave,
                  "An unchanged in-memory conversation cannot conceal changed or corrupt stored bytes")
        try stableObjectBytes.write(to: independent)
        let oldPreview = try store.previewBackup(at: store.backups().first!.url)
        try check(oldPreview.archive.conversations == [first, second], "Automatic snapshot reconstructs the previous complete history")

        let stale = ChatStore(directory: state)
        var staleArchive = try stale.load()
        try check(try childHistoryWrite(state) == "WROTE", "A separate Native process can save the same history store")
        let concurrentBytes = try fileBytes(state)
        staleArchive.conversations[1].draft = "Do not lose either edit"
        var refused = false
        do { try stale.save(staleArchive) } catch { refused = true }
        try check(refused && stale.conflictDetected && (try fileBytes(state)) == concurrentBytes,
                  "A stale second process cannot overwrite another process's saved messages")
        try ChatHistoryFiles.withLock(in: state, write: true) {
            try check(try childHistoryWrite(state) == "REFUSED", "An active writer lock refuses a competing Native process")
        }
        let export = root.appendingPathComponent("unsent-copy.protomind-history")
        try stale.exportBackup(staleArchive, to: export)
        let exportPreview = try stale.previewBackup(at: export)
        try check(exportPreview.archive.conversations == staleArchive.conversations && (try fileBytes(state)) == concurrentBytes,
                  "Unsaved conflicting messages can be exported without replacing current history")
        let reloaded = try stale.reloadPreserving(staleArchive)
        try check(reloaded.conversations[0].messages.last?.text == "Saved by another process"
                  && stale.backups().contains(where: { $0.url.lastPathComponent.hasPrefix("recovery-") }),
                  "Reloading current history preserves the previous in-window version as a recovery copy")

        let legacyState = root.appendingPathComponent("history-legacy-migration")
        try FileManager.default.createDirectory(at: legacyState, withIntermediateDirectories: true)
        let legacyFile = legacyState.appendingPathComponent("conversations.json")
        let legacyBytes = try ChatHistoryFormat.encode(ChatArchive(conversations: [first], selectedID: first.id))
        try legacyBytes.write(to: legacyFile)
        let legacy = ChatStore(directory: legacyState)
        var migrated = try legacy.load()
        try check(try fileBytes(legacyState).count == 1 && Data(contentsOf: legacyFile) == legacyBytes,
                  "Reading legacy v5 history leaves its bytes and format untouched")
        migrated.conversations[0].draft = "First change after upgrade"
        try legacy.save(migrated)
        let pinned = try legacy.backups().first { $0.url.lastPathComponent.hasPrefix("legacy-") }!
        try check(try Data(contentsOf: pinned.url) == legacyBytes && ChatHistoryFormat.manifest(Data(contentsOf: legacyFile)).version == 6,
                  "First explicit history change pins exact legacy bytes before committing v6")
        for index in 0..<25 {
            migrated.conversations[0].draft = "Draft revision \(index)"
            try legacy.save(migrated)
        }
        let snapshots = try legacy.backups()
        try check(snapshots.filter { $0.url.lastPathComponent.hasPrefix("snapshot-") }.count == 20
                  && snapshots.contains(where: { $0.id == pinned.id }), "Snapshot retention keeps 20 automatic versions plus the original migration copy")
        for snapshot in snapshots { _ = try legacy.previewBackup(at: snapshot.url) }
        try check(true, "Every retained snapshot still resolves all of its conversation objects after cleanup")
        let objectCount = try FileManager.default.contentsOfDirectory(atPath: legacy.objectsDirectory.path).count
        try check(objectCount <= 21, "Unreferenced draft objects are cleaned only after a committed snapshot rotation")
        let oldest = snapshots.last { $0.url.lastPathComponent.hasPrefix("snapshot-") }!
        let oldestBytes = try Data(contentsOf: oldest.url)
        try Data("Damaged previously verified snapshot".utf8).write(to: pinned.url)
        migrated.conversations[0].draft = "Revision after checkpoint damage"
        try legacy.save(migrated)
        try check(try Data(contentsOf: oldest.url) == oldestBytes
                  && legacy.backups().filter { $0.url.lastPathComponent.hasPrefix("snapshot-") }.count == 21,
                  "Changed checkpoint bytes invalidate cached references and stop deletion of previous recovery states")

        let faultState = root.appendingPathComponent("history-commit-failure")
        let stable = ChatStore(directory: faultState)
        try stable.save(ChatArchive(conversations: [first], selectedID: first.id))
        let stableRoot = try Data(contentsOf: stable.url)
        let fault = ChatStore(directory: faultState, dataWriter: { _, _ in throw NativeError.message("Injected final commit failure") })
        var faultArchive = try fault.load(); faultArchive.conversations[0].messages.append(ChatMessage(role: "assistant", text: "Must remain unsaved"))
        do { try fault.save(faultArchive) } catch {}
        try check(try Data(contentsOf: stable.url) == stableRoot && ChatStore(directory: faultState).load().conversations == [first],
                  "Failure after writing a new object leaves the previous complete manifest authoritative")

        let restoreState = root.appendingPathComponent("history-restore")
        let restore = ChatStore(directory: restoreState)
        try restore.save(ChatArchive(conversations: [second], selectedID: second.id))
        let preview = try restore.previewBackup(at: export)
        let snapshotBeforePreview = try fileBytes(restoreState)
        _ = try restore.previewBackup(at: export)
        try check(try fileBytes(restoreState) == snapshotBeforePreview, "Backup validation is a read-only operation")
        let restored = try restore.restore(preview, preserving: ChatArchive(conversations: [second], selectedID: second.id))
        try check(restored.conversations == staleArchive.conversations && restore.backups().contains { $0.url.lastPathComponent.hasPrefix("recovery-") },
                  "Explicit restore replaces history only after preserving current disk and in-window state")
        let failedRestore = ChatStore(directory: faultState, dataWriter: { _, _ in })
        let failedCurrent = try failedRestore.load()
        let failedPreview = try failedRestore.previewBackup(at: export)
        refused = false
        do { _ = try failedRestore.restore(failedPreview, preserving: failedCurrent) } catch { refused = true }
        try check(refused && failedRestore.writeBlocked && (try Data(contentsOf: failedRestore.url)) == stableRoot
                  && failedRestore.backups().contains { $0.url.lastPathComponent.hasPrefix("recovery-") },
                  "Restore verifies actual disk bytes and never reports success for an uncommitted manifest")
        let stalePreview = try restore.previewBackup(at: export)
        var changed = restored; changed.conversations[0].title = "Changed after preview"
        try restore.save(changed)
        let staleBefore = try fileBytes(restoreState)
        refused = false
        do { _ = try restore.restore(stalePreview, preserving: changed) } catch { refused = true }
        try check(refused && (try fileBytes(restoreState)) == staleBefore, "Restore refuses a target that changed after preview without writing anything")

        let brokenBytes = Data("corrupt history to preserve".utf8)
        try brokenBytes.write(to: restore.url)
        do { _ = try restore.load() } catch {}
        let recovery = try restore.previewBackup(at: export)
        _ = try restore.restore(recovery, preserving: changed)
        let recoveryFiles = try restore.backups()
        try check(!restore.writeBlocked && (try restore.load()).conversations == staleArchive.conversations
                  && recoveryFiles.contains(where: { (try? Data(contentsOf: $0.url)) == brokenBytes }),
                  "A verified copy restores corrupt history while preserving the damaged original bytes")

        let corruptPreview = try restore.previewBackup(at: export)
        let exportedManifest = try ChatHistoryFormat.manifest(Data(contentsOf: export.appendingPathComponent("conversations.json")))
        let exportedObject = export.appendingPathComponent("chat_objects/" + exportedManifest.conversations[0].sha256 + ".json")
        try Data("tampered".utf8).write(to: exportedObject)
        let beforeTamper = try fileBytes(restoreState)
        refused = false
        do { _ = try restore.restore(corruptPreview, preserving: changed) } catch { refused = true }
        try check(refused && (try fileBytes(restoreState)) == beforeTamper, "Backup source tampering after preview is refused before target writes")

        try FileManager.default.removeItem(at: restore.url)
        let missing = ChatStore(directory: restoreState)
        let missingBefore = try fileBytes(restoreState)
        do { _ = try missing.load() } catch {}
        try check(missing.writeBlocked && (try fileBytes(restoreState)) == missingBefore,
                  "A missing manifest with surviving objects opens recovery rather than silently replacing history")

        let large = ChatStore(directory: root.appendingPathComponent("history-over-50mb"))
        var largeChats = [Conversation(), Conversation(), Conversation()]
        for index in largeChats.indices { largeChats[index].messages = [ChatMessage(role: "assistant", text: String(repeating: "x", count: 18_000_000))] }
        let largeArchive = ChatArchive(conversations: largeChats, selectedID: largeChats[0].id)
        try large.save(largeArchive)
        try check(try large.load().conversations == largeChats && Data(contentsOf: large.url).count < 4096,
                  "History exceeding the old global 50 MB ceiling saves and reloads through a small manifest")

        let appState = root.appendingPathComponent("history-recovery-model")
        let app = AppModel(configuration: LaunchConfiguration(projectRoot: root, python: root, stateDirectory: appState))
        app.setComposer("Keep my current draft"); app.flushDraft()
        let appExport = root.appendingPathComponent("app-history.protomind-history")
        try app.exportHistoryBackup(to: appExport)
        app.openHistoryBackups(); app.inspectHistoryBackup(appExport)
        let viewSize = NSHostingController(rootView: HistoryBackupsView(model: app)).sizeThatFits(in: CGSize(width: 900, height: 800))
        try check(viewSize.width <= 690 && viewSize.height <= 640 && app.historyBackupPreview != nil && !app.client.connected,
                  "Backup review opens in a bounded Native sheet without connecting a provider")
        app.setComposer("A later unsaved message")
        app.restoreHistoryBackup(app.historyBackupPreview!)
        try check(app.composer == "Keep my current draft" && !app.historyPersistence.blocksSubmission
                  && !app.fullAccessEnabled && app.pendingAction == nil, "Native restore adopts the selected history and clears pending action authority")
    }
}
