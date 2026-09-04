import AppKit
import Foundation
import SwiftUI

extension NativeChecks {
    @MainActor
    static func historyPersistence(fixture: URL, python: URL, root: URL) async throws {
        let brokenState = root.appendingPathComponent("history-corrupt")
        try FileManager.default.createDirectory(at: brokenState, withIntermediateDirectories: true)
        let brokenFile = brokenState.appendingPathComponent("conversations.json")
        let original = Data("corrupt synthetic history".utf8)
        try original.write(to: brokenFile)
        let broken = AppModel(configuration: LaunchConfiguration(projectRoot: fixture, python: python, stateDirectory: brokenState))
        defer { broken.client.shutdown() }
        try check(broken.historyPersistence.requiresRecovery && broken.saveBeforeExit(),
                  "Unreadable history blocks submission but permits closing an untouched recovery window")
        broken.clearError()
        await broken.submit("Keep this unsent draft")
        try check(broken.messages.isEmpty && broken.composer == "Keep this unsent draft" && !broken.client.connected,
                  "Unreadable history refuses Send before even connecting the bridge and retains the input")
        try check(!broken.saveBeforeExit() && broken.historyPersistence.blocksSubmission && !broken.retryHistorySave(),
                  "Clearing a generic error cannot bypass history recovery or discard an unsaved draft on quit")
        try check(try Data(contentsOf: brokenFile) == original,
                  "History recovery never overwrites the unreadable source with an empty chat")
        let notice = NSHostingController(rootView: HistoryPersistenceNotice(model: broken))
        let noticeSize = notice.sizeThatFits(in: CGSize(width: 880, height: 600))
        try check(noticeSize.height > 80 && noticeSize.height < 600,
                  "History recovery has a visible bounded notice independent of the dismissible generic error")

        let state = root.appendingPathComponent("history-write-faults")
        var rejectWrites = false
        var rejectAnswers = false
        let history = ChatStore(directory: state, dataWriter: { data, url in
            let archive = try JSONDecoder().decode(ChatArchive.self, from: data)
            if rejectWrites || (rejectAnswers && archive.conversations.contains { $0.messages.contains { $0.role == "assistant" } }) {
                throw NativeError.message("Synthetic disk write failure")
            }
            try FileManager.default.createDirectory(at: url.deletingLastPathComponent(), withIntermediateDirectories: true,
                                                     attributes: [.posixPermissions: 0o700])
            try data.write(to: url, options: .atomic)
            try FileManager.default.setAttributes([.posixPermissions: 0o600], ofItemAtPath: url.path)
        })
        let configuration = LaunchConfiguration(projectRoot: fixture, python: python, stateDirectory: state)
        let app = AppModel(configuration: configuration, historyStore: history)
        defer { app.client.shutdown() }
        app.setProvider("mock")
        try app.setPendingCriteria(["Keep the exact draft and criteria"], conversationID: app.selectedID!)
        app.setComposer("Give a short local fixture answer.")
        app.flushDraft()
        let originalChat = app.selected!
        let beforeFailure = try fileBytes(state), coreBefore = try fileBytes(fixture)
        rejectWrites = true
        await app.submit()
        try check(app.selected == originalChat && !app.busy && app.turnStartedAt == nil && app.messages.isEmpty,
                  "A pre-dispatch save failure restores the exact conversation, title, draft and criteria")
        try check(try fileBytes(state) == beforeFailure && fileBytes(fixture) == coreBefore && app.workSessions.isEmpty,
                  "A failed pre-dispatch save creates no run or core mutation")
        try check(app.historyPersistence.blocksSubmission && !app.historyPersistence.requiresRecovery && !app.saveBeforeExit(),
                  "Transient write failure remains visible and prevents silently quitting with unsaved changes")
        rejectWrites = false
        try check(app.retryHistorySave() && !app.historyPersistence.blocksSubmission,
                  "An explicit local save retry recovers without resubmitting the task")

        rejectAnswers = true
        await app.submit()
        let completed = app.messages
        try check(completed.count == 2 && completed.last?.role == "assistant" && app.workSessions.count == 1,
                  "A post-answer save failure retains the completed reply and its one work session")
        try check(app.historyPersistence.blocksSubmission && app.historyPersistence.hasUnsavedChanges && !app.saveBeforeExit(),
                  "An unsaved reply cannot be mistaken for a durable result during quit")
        let persisted = try ChatStore(directory: state).load()
        try check(persisted.conversations.first?.messages.count == 1,
                  "Injected final-save failure leaves only the already saved user message on disk")
        let evidenceBeforeRetry = try fileBytes(state.appendingPathComponent("work_sessions"))
        let coreBeforeRetry = try fileBytes(fixture)
        await app.submit("Do not start another task")
        try check(app.messages == completed && app.workSessions.count == 1,
                  "An unsaved answer blocks a second Send without appending another turn")
        rejectAnswers = false
        try check(app.retryHistorySave() && app.saveBeforeExit(),
                  "Completed answer can be saved after storage recovers")
        try check(try fileBytes(state.appendingPathComponent("work_sessions")) == evidenceBeforeRetry
                  && fileBytes(fixture) == coreBeforeRetry,
                  "Saving the retained answer does not repeat provider, journal or core work")
        let restored = AppModel(configuration: configuration)
        try check(restored.messages == completed && !restored.historyPersistence.blocksSubmission && !restored.client.connected,
                  "Restart recovers the same message IDs and complete answer without replay")

        app.setComposer("A later unsent draft")
        rejectWrites = true
        try check(!app.saveBeforeExit() && app.composer == "A later unsent draft",
                  "Quit attempts to flush a fresh draft and preserves it when saving fails")
        rejectWrites = false
        try check(app.saveBeforeExit() && AppModel(configuration: configuration).composer == "A later unsent draft",
                  "Quit saves a recovered draft so it survives restart")

        let commandState = root.appendingPathComponent("history-confirmed-command")
        let commandApp = AppModel(configuration: LaunchConfiguration(projectRoot: fixture, python: python, stateDirectory: commandState))
        defer { commandApp.client.shutdown() }
        await commandApp.submit("/memory remember A synthetic record that must not be written")
        try check(commandApp.pendingAction != nil, "Mutation fixture reaches its normal explicit confirmation")
        try FileManager.default.createDirectory(at: commandApp.store.url, withIntermediateDirectories: true)
        let commandCoreBefore = try fileBytes(fixture)
        await commandApp.confirmPending()
        try check(commandApp.messages.isEmpty && commandApp.composer.contains("must not be written")
                  && commandApp.historyPersistence.blocksSubmission && (try fileBytes(fixture)) == commandCoreBefore,
                  "Confirmed operator mutation is also refused when its history cannot be saved")
    }
}
