import CryptoKit
import Foundation

extension NativeChecks {
    static func sessionSpineDurabilityContracts(root: URL) throws {
        let fixed = try NativeSessionSpineInstallationIdentity.make(
            installationID: UUID(uuidString: "00000000-0000-0000-0000-000000000001")!
        )
        try check(
            fixed.ownerID == "native-session-spine:274223a0080d53e4f132a170fabc0ac1" &&
            fixed.identityHash == "a746b29cd8f4af10034a6441e9dbee3b51bc02eaccf90b657bdc4fb0c1ca47b1",
            "Native installation owner exactly matches the detached Python P2h derivation"
        )
        try check(
            fixed.stableAcrossRelaunch && !fixed.processIDBound && !fixed.osUserBound &&
            !fixed.permissionGranted && !fixed.executionAuthorityGranted,
            "Native installation owner is stable identity, not process, account or execution authority"
        )

        let state = root.appendingPathComponent("session-spine-installation")
        let store = NativeSessionSpineInstallationStore(stateDirectory: state)
        try check(try store.load() == nil && !FileManager.default.fileExists(atPath: state.path),
                  "Constructing and reading a missing installation identity creates no private state")
        let created = try store.loadOrCreate()
        let firstBytes = try Data(contentsOf: store.url)
        let relaunched = NativeSessionSpineInstallationStore(stateDirectory: state)
        let restored = try relaunched.loadOrCreate()
        try check(created == restored && firstBytes == (try Data(contentsOf: relaunched.url)),
                  "One explicit installation identity survives relaunch without rewrite")
        let identityMode = try FileManager.default.attributesOfItem(atPath: store.url.path)[.posixPermissions] as? Int
        let directoryMode = try FileManager.default.attributesOfItem(atPath: store.directory.path)[.posixPermissions] as? Int
        try check(identityMode == 0o600 && directoryMode == 0o700,
                  "Installation identity uses private file and directory permissions")
        let identityText = String(decoding: firstBytes, as: UTF8.self)
        try check(!identityText.contains("prompt") && !identityText.contains("answer") &&
                  !identityText.contains(NSUserName()),
                  "Installation identity stores no conversation, OS-account or process content")

        let corruptState = root.appendingPathComponent("session-spine-installation-corrupt")
        let corrupt = NativeSessionSpineInstallationStore(stateDirectory: corruptState)
        _ = try corrupt.loadOrCreate()
        let corruptBytes = Data("{\"schema\":\"tampered\"}".utf8)
        try corruptBytes.write(to: corrupt.url, options: .atomic)
        try FileManager.default.setAttributes([.posixPermissions: 0o600], ofItemAtPath: corrupt.url.path)
        var corruptRejected = false
        do { _ = try NativeSessionSpineInstallationStore(stateDirectory: corruptState).load() }
        catch { corruptRejected = true }
        let blocked = NativeSessionSpineInstallationStore(stateDirectory: corruptState)
        do { _ = try blocked.load() } catch { }
        do { _ = try blocked.loadOrCreate() } catch { }
        try check(corruptRejected && blocked.writeBlocked && (try Data(contentsOf: corrupt.url)) == corruptBytes,
                  "Tampered installation identity is never replaced or regenerated")

        let symlinkState = root.appendingPathComponent("session-spine-installation-symlink")
        let symlinkTarget = root.appendingPathComponent("session-spine-installation-target")
        try FileManager.default.createDirectory(at: symlinkState, withIntermediateDirectories: true)
        try FileManager.default.createDirectory(at: symlinkTarget, withIntermediateDirectories: true)
        try FileManager.default.createSymbolicLink(
            at: symlinkState.appendingPathComponent("session_spine_identity"),
            withDestinationURL: symlinkTarget
        )
        var symlinkRejected = false
        do { _ = try NativeSessionSpineInstallationStore(stateDirectory: symlinkState).loadOrCreate() }
        catch { symlinkRejected = true }
        try check(symlinkRejected && (try FileManager.default.contentsOfDirectory(atPath: symlinkTarget.path)).isEmpty,
                  "Installation identity refuses a redirected directory without writing through it")

        let unknownState = root.appendingPathComponent("session-spine-installation-unknown")
        let unknown = NativeSessionSpineInstallationStore(stateDirectory: unknownState)
        try FileManager.default.createDirectory(
            at: unknown.directory,
            withIntermediateDirectories: true,
            attributes: [.posixPermissions: 0o700]
        )
        let unknownFile = unknown.directory.appendingPathComponent(".installation.interrupted.tmp")
        try Data("partial".utf8).write(to: unknownFile)
        try FileManager.default.setAttributes([.posixPermissions: 0o600], ofItemAtPath: unknownFile.path)
        var unknownRejected = false
        do { _ = try unknown.loadOrCreate() } catch { unknownRejected = true }
        try check(unknownRejected && FileManager.default.fileExists(atPath: unknownFile.path),
                  "Unknown identity recovery evidence blocks creation and is not auto-cleaned")

        let historyState = root.appendingPathComponent("session-spine-history-readback")
        var conversation = Conversation()
        conversation.messages = [ChatMessage(role: "user", text: "Exact throwable boundary fixture")]
        let history = ChatStore(directory: historyState)
        let readback = try history.saveAndReadBack(ChatArchive(conversations: [conversation], selectedID: conversation.id))
        let digest = SHA256.hash(data: readback.data).map { String(format: "%02x", $0) }.joined()
        try check(readback.sizeBytes == readback.data.count && readback.sha256 == digest &&
                  readback.archive.selectedID == conversation.id && readback.data == (try Data(contentsOf: history.url)),
                  "Throwable history save returns exact decoded bytes from post-save readback")

        let failedState = root.appendingPathComponent("session-spine-history-readback-failure")
        let failedReadback = ChatStore(directory: failedState, dataReader: { _ in
            throw NativeError.message("simulated post-save readback failure")
        })
        var failureSurfaced = false
        do {
            _ = try failedReadback.saveAndReadBack(ChatArchive(conversations: [conversation], selectedID: conversation.id))
        } catch { failureSurfaced = true }
        let savedAfterFailure = try ChatStore(directory: failedState).load()
        try check(failureSurfaced && failedReadback.writeBlocked && savedAfterFailure.selectedID == conversation.id,
                  "Post-save readback failure throws and blocks retry while preserving the durable history")

        let mismatchState = root.appendingPathComponent("session-spine-history-readback-mismatch")
        let mismatched = ChatStore(directory: mismatchState, dataReader: { _ in Data("{}".utf8) })
        var mismatchSurfaced = false
        do {
            _ = try mismatched.saveAndReadBack(ChatArchive(conversations: [conversation], selectedID: conversation.id))
        } catch { mismatchSurfaced = true }
        try check(mismatchSurfaced && mismatched.writeBlocked &&
                  (try ChatStore(directory: mismatchState).load()).selectedID == conversation.id,
                  "Mismatched history readback fails closed without rolling back confirmed saved bytes")
    }
}
