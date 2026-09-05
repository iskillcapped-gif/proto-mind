import AppKit
import Foundation
import SwiftUI

extension NativeChecks {
    @MainActor
    static func privateBackupContracts(root: URL) throws {
        let state = root.appendingPathComponent("private-backup-gates")
        let store = ChatStore(directory: state)
        var chat = Conversation()
        chat.messages = [ChatMessage(role: "assistant", text: "Preserved answer")]
        let archive = ChatArchive(conversations: [chat], selectedID: chat.id)
        try store.save(archive)
        let preferences = PreferenceStore(directory: state)
        _ = try preferences.load()
        let before = try Data(contentsOf: store.url)
        try Data("{\"id\":\"new-generation\"}".utf8).write(to: state.appendingPathComponent(".private-state-generation.json"))
        do { try store.save(archive); throw NativeError.message("Stale history write was accepted") }
        catch { try check(error.localizedDescription != "Stale history write was accepted", "An identical history manifest still refuses a stale private-state generation") }
        do { try preferences.save(NativePreferences()); throw NativeError.message("Stale preferences accepted") }
        catch { try check(error.localizedDescription != "Stale preferences accepted", "Preferences refuse writes from before the private-state restore") }
        try check(try Data(contentsOf: store.url) == before, "Stale stores preserve the restored manifest bytes")
        try Data("{}".utf8).write(to: state.appendingPathComponent(".private-restore.json"))
        do { _ = try ChatStore(directory: state).load(); throw NativeError.message("Pending history read accepted") }
        catch { try check(error.localizedDescription != "Pending history read accepted", "Pending full restore blocks ordinary history reads") }
        do { _ = try PreferenceStore(directory: state).load(); throw NativeError.message("Pending preferences read accepted") }
        catch { try check(error.localizedDescription != "Pending preferences read accepted", "Pending full restore blocks preference loading") }
        let app = AppModel(configuration: LaunchConfiguration(projectRoot: root, python: root, stateDirectory: state))
        let view = NSHostingController(rootView: PrivateBackupView(app: app, backup: app.privateBackup))
        let size = view.sizeThatFits(in: CGSize(width: 900, height: 750))
        try check(size.width <= 800 && size.height <= 700, "Full backup controls fit the minimum supported app window")
    }

    @MainActor
    static func privateBackupIntegration(fixture: URL, python: URL, root: URL) async throws {
        // Separate core and Native state: no other check's storage or provider is reused.
        let project = root.appendingPathComponent("private-backup-project")
        try FileManager.default.copyItem(at: fixture, to: project)
        let state = root.appendingPathComponent("private-backup-state")
        let configuration = LaunchConfiguration(projectRoot: project, python: python, stateDirectory: state)
        let app = AppModel(configuration: configuration)
        defer { app.client.shutdown() }
        app.setComposer("Draft included in the complete backup")
        try app.saveHistory()
        let original = app.currentHistoryArchive
        let marker = project.appendingPathComponent("proto_mind/data/backup_fixture.json")
        try FileManager.default.createDirectory(at: marker.deletingLastPathComponent(), withIntermediateDirectories: true)
        try Data("{\"value\":\"before\"}".utf8).write(to: marker)
        let source = root.appendingPathComponent("complete.protomind-backup")
        await app.privateBackup.create(at: source, app: app)
        try check(app.privateBackup.error == nil && app.privateBackup.result["files"].integer > 0,
                  "Native creates and verifies a complete backup through the real Python bridge")
        app.setComposer("Later draft preserved before restore")
        try app.saveHistory()
        try Data("{\"value\":\"after\"}".utf8).write(to: marker)
        let beforePreview = try fileBytes(state)
        await app.privateBackup.inspect(source, app: app)
        try check(app.privateBackup.error == nil && app.privateBackup.conversations == original.conversations.count
                  && (try fileBytes(state)) == beforePreview, "Full backup preview validates Native history without modifying live state")
        await app.privateBackup.restore(app: app)
        try check(app.privateBackup.error == nil && app.privateBackup.restartRequired && app.privateBackupRestartRequired,
                  "Native complete restore reaches its explicit restart state")
        try check(try String(data: Data(contentsOf: marker), encoding: .utf8)?.contains("before") == true,
                  "Complete restore brings back the separate core store")
        let restored = AppModel(configuration: configuration)
        defer { restored.client.shutdown() }
        try check(restored.currentHistoryArchive.conversations == original.conversations && !restored.cloudConsent,
                  "Fresh Native instance reads the original dialogs and draft with cloud access disabled")
        let window = URL(fileURLWithPath: app.privateBackup.result["window_path"].text)
        try check(try ChatStore(directory: window).load().conversations.contains { $0.draft == "Later draft preserved before restore" },
                  "The in-window draft remains independently recoverable after replacing live history")
        let restoredBytes = try fileBytes(state)
        try check(app.saveBeforeExit() && (try fileBytes(state)) == restoredBytes,
                  "Quitting the old Native instance does not rewrite restored state")

        // Lose the response only after a second real restore commits, then reconcile
        // its on-disk receipt instead of retrying or continuing with stale state.
        let preview = try await restored.client.request("private_backup_preview", ["path": .string(source.path)])
        await restored.privateBackup.execute(app: restored) {
            _ = try await restored.client.request("private_backup_restore", ["path": preview["path"], "sha256": preview["sha256"],
                "target_fingerprint": preview["target_fingerprint"], "window": .string(window.lastPathComponent)])
            throw NativeError.message("Synthetic lost response after commit")
        }
        try check(restored.privateBackup.error == nil && restored.privateBackupRestartRequired && restored.saveBeforeExit(),
                  "A lost restore response is recovered from matching durable completion evidence without replay")
    }
}
