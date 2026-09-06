import Foundation

extension NativeChecks {
    @MainActor
    static func parallelTasks(fixture: URL, service: URL, python: URL, root: URL) async throws {
        let project = root.appendingPathComponent("parallel-project")
        let state = root.appendingPathComponent("parallel-state")
        try FileManager.default.copyItem(at: fixture, to: project)
        try FileManager.default.copyItem(at: service, to: project.appendingPathComponent("proto_mind/steering_fixture.py"))
        let bridge = project.appendingPathComponent("proto_mind/native_bridge.py")
        let code = try String(contentsOf: bridge, encoding: .utf8)
            .replacingOccurrences(of: "class NativeBackend:", with: "from proto_mind.steering_fixture import FixtureSubscription, delayed_steering_reply\n\nclass NativeBackend:")
            .replacingOccurrences(of: "subscription_factory=CodexSubscription", with: "subscription_factory=FixtureSubscription")
            .replacingOccurrences(of: "return steering.send(params)", with: "return delayed_steering_reply(self.state_dir, steering, params)")
        try code.write(to: bridge, atomically: true, encoding: .utf8)
        let configuration = LaunchConfiguration(projectRoot: project, python: python, stateDirectory: state)
        let app = AppModel(configuration: configuration)
        defer { app.shutdown() }
        await app.start()
        app.setProvider("codex"); app.cloudConsent = true; app.setAutoSkillsEnabled(false)
        app.requestAgentAccess(); await app.confirmAgentAccess()
        try check(app.fullAccessEnabled, "Parallel fixture has an explicit projectless grant for A")
        let a = app.selectedID!
        try Data(#"{"ready_delay":0.6,"ack_delay":0.2}"#.utf8).write(to: state.appendingPathComponent("steering-control.json"))
        app.setComposer("Первая задача")
        let first = Task { await app.submit() }
        try await awaitCondition { app.canUpdateTask }
        await app.submit("Уточнение только A")
        app.setComposer("Черновик A")
        app.newConversation()
        let b = app.selectedID!
        try check(a != b && app.isRunning(a) && !app.busy && app.composer.isEmpty,
                  "New conversation opens while A runs, with an independent empty composer")
        app.setProvider("codex"); app.setAutoSkillsEnabled(false)
        app.requestAgentAccess(); await app.confirmAgentAccess()
        try check(app.fullAccessEnabled && app.agentGrants[a] != nil && app.agentGrants[b] != nil
                  && app.executions[a]?.client !== app.executions[b]?.client,
                  "Each conversation owns its own granted connection; permissions are not transferred")
        app.setComposer("Вторая задача")
        let second = Task { await app.submit() }
        try await awaitCondition { app.executions[a]?.updateTarget != nil && app.executions[b]?.updateTarget != nil }
        try await awaitCondition { app.conversations.first(where: { $0.id == a })?.messages.first?.taskUpdates?.first?.state == .accepted }
        try check(app.isRunning(a) && app.isRunning(b) && app.executions[a]?.requestID != app.executions[b]?.requestID,
                  "Two actual bridge processes run at once and the hidden task's queued correction is delivered")
        let firstState = app.executions[a]!, secondState = app.executions[b]!
        let firstSource = firstState.sourceMessageID!
        app.setComposer("Уточнение только B")
        let correction = Task { await app.submit() }
        try await awaitCondition { secondState.sendingUpdate }
        app.returnToConversation(a)
        try check(app.selectedID == a && app.composer == "Черновик A" && app.activeTaskMessageID == firstSource,
                  "Switching during another task's acknowledgement restores A's draft and execution controls")
        await correction.value
        try check(app.conversations.first(where: { $0.id == b })?.messages.first?.taskUpdates?.first?.state == .accepted
                  && app.messages.first?.taskUpdates?.count == 1,
                  "A late acknowledgement is saved only in its original conversation")
        let firstStream = firstState.stream
        app.receiveExecutionEvent(.object(["event": .string("answer_delta"), "request_id": .string(secondState.requestID!), "delta": .string("FOREIGN")]), state: firstState)
        try check(firstState.stream == firstStream, "A foreign request ID cannot contaminate another task's stream")
        app.archiveConversation(b, archived: true)
        try check(app.conversations.first(where: { $0.id == b })?.archived == false,
                  "An active hidden conversation cannot be archived away")
        await app.stop(); await first.value
        try check(!app.isRunning(a) && app.isRunning(b) && secondState.client.turnOutstanding
                  && app.messages.last?.isError == true && app.composer == "Черновик A",
                  "Stopping A preserves its newer draft and leaves B running")
        try check(app.agentGrants[b] != nil, "Stopping A does not revoke B's Full Mac permission")
        app.newConversation()
        let c = app.selectedID!
        app.setComposer("Черновик третьего диалога")
        try check(!app.busy && app.globalBusy && app.anyTaskRunning,
                  "An idle selected chat is editable while shared recovery/exit still sees a background task")
        app.openHistoryBackups()
        try check(!app.showHistoryBackups, "History recovery remains blocked by a background turn")
        try Data(#"{"reply_delay":2.0}"#.utf8).write(to: state.appendingPathComponent("steering-control.json"))
        app.select(b)
        let lateCorrection = Task { await app.submit("Последнее уточнение B") }
        try await awaitCondition { FileManager.default.fileExists(atPath: state.appendingPathComponent("steering-delayed-reply").path) }
        app.select(c)
        try Data().write(to: state.appendingPathComponent("finish-steering-" + b.uuidString.lowercased()))
        await second.value
        try check(app.selectedID == c && app.composer == "Черновик третьего диалога" && app.messages.isEmpty && !app.anyTaskRunning,
                  "Background completion keeps the selected conversation, draft and transcript unchanged")
        app.openHistoryBackups()
        try check(secondState.sendingUpdate && app.globalBusy && !app.showHistoryBackups,
                  "History recovery and shutdown wait for a late steering receipt even after the answer finishes")
        await lateCorrection.value
        let completed = app.conversations.first(where: { $0.id == b })!
        try check(completed.messages.last?.role == "assistant" && completed.messages.last?.text.contains("Уточнение только B") == true
                  && completed.messages.last?.text.contains("Уточнение только A") == false && !app.globalBusy
                  && completed.messages.first?.taskUpdates?.last?.state == .accepted,
                  "B's final answer includes only B's steering input")
        let restored = AppModel(configuration: configuration)
        defer { restored.shutdown() }
        try check(restored.conversations == app.conversations && restored.selectedID == c
                  && completed.messages.last?.turnReference != nil && !restored.anyTaskRunning,
                  "One history writer preserves both task outcomes, exact lineage and all drafts across restart")
        let idleConnection = app.executions[c]!.client
        app.pendingAction = PendingOperatorAction(text: "/commands status", conversationID: a, summary: "Fixture read")
        await app.confirmPending()
        try check(!idleConnection.connected && app.selectedID == c && app.composer == "Черновик третьего диалога"
                  && app.messages.isEmpty && app.conversations.first(where: { $0.id == a })?.messages.last?.role == "report"
                  && app.conversations.first(where: { $0.id == a })?.messages.last?.isError == false,
                  "A pending core action uses its original session after navigation, without opening the selected idle bridge")
    }

    @MainActor
    private static func awaitCondition(_ condition: () -> Bool) async throws {
        let deadline = Date().addingTimeInterval(15)
        while !condition() && Date() < deadline { try await Task.sleep(for: .milliseconds(10)) }
        guard condition() else { throw NativeError.message("Parallel task fixture did not reach the expected boundary") }
    }
}
