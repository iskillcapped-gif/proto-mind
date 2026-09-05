import AppKit
import Foundation

extension NativeChecks {
    @MainActor
    static func taskUpdatesIntegration(fixture: URL, service: URL, python: URL, root: URL) async throws {
        let project = root.appendingPathComponent("steering-project")
        let state = root.appendingPathComponent("steering-state")
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        try FileManager.default.copyItem(at: fixture, to: project)
        try FileManager.default.copyItem(at: service, to: project.appendingPathComponent("proto_mind/steering_fixture.py"))
        let bridge = project.appendingPathComponent("proto_mind/native_bridge.py")
        var code = try String(contentsOf: bridge, encoding: .utf8)
        code = code.replacingOccurrences(of: "class NativeBackend:", with: "from proto_mind.steering_fixture import FixtureSubscription\n\nclass NativeBackend:")
            .replacingOccurrences(of: "subscription_factory=CodexSubscription", with: "subscription_factory=FixtureSubscription")
        try code.write(to: bridge, atomically: true, encoding: .utf8)
        let app = AppModel(configuration: LaunchConfiguration(projectRoot: project, python: python, stateDirectory: state))
        defer { app.client.shutdown() }
        await app.start()
        app.setProvider("codex"); app.cloudConsent = true
        app.setAutoSkillsEnabled(false)
        app.setComposer("Более новый черновик")
        try Data(#"{"ready_delay":0.4}"#.utf8).write(to: state.appendingPathComponent("steering-control.json"), options: .atomic)
        let running = Task { await app.submit("Подготовь страницу") }
        let deadline = Date().addingTimeInterval(10)
        while !app.canUpdateTask && Date() < deadline { try await Task.sleep(for: .milliseconds(10)) }
        try check(app.canUpdateTask && app.taskUpdateTarget == nil, "Text updates are available while the main model is preparing")
        try check(app.composer == "Более новый черновик", "Preparing a supplied request does not erase a different composer draft")
        await app.submit("Добавь синюю кнопку")
        try check(app.messages.first?.taskUpdates?.first?.state == .queued && app.composer.isEmpty,
                  "Early update is saved in the task queue and clears only its submitted draft")
        while app.messages.first?.taskUpdates?.first?.state != .accepted && Date() < deadline { try await Task.sleep(for: .milliseconds(10)) }
        try check(app.busy && app.messages.first?.taskUpdates?.first?.state == .accepted,
                  "Queued update reaches the same running model turn before its answer")
        while !app.stream.isEmpty && Date() < deadline { try await Task.sleep(for: .milliseconds(10)) }
        try check(app.stream.isEmpty && app.workLog.pretty.contains("Предварительный ответ"),
                  "A steering boundary clears the superseded live answer and preserves it in public work history")
        await app.codexUsage.refreshLimits(app: app)
        try check(app.busy && app.codexUsage.summary?.compactBucket?.windows.first?.used == 27,
                  "Menu quota reads also complete during the same running task")
        await app.submit("И крупный заголовок")
        try check(app.messages.first?.taskUpdates?.last?.state == .accepted && app.busy,
                  "A second live update is delivered without starting another task")
        try Data(#"{"outcome":"unknown"}"#.utf8).write(to: state.appendingPathComponent("steering-control.json"), options: .atomic)
        await app.submit("Добавь отступы")
        try check(app.messages.first?.taskUpdates?.last?.state == .unknown,
                  "A lost acknowledgement is shown as unconfirmed and is not retried")
        app.setComposer("Черновик следующего сообщения")
        try Data().write(to: state.appendingPathComponent("finish-steering"))
        await running.value
        try check(!app.busy && app.messages.count == 2 && app.messages.last?.role == "assistant"
                  && app.messages.last?.text.contains("Добавь синюю кнопку") == true
                  && app.messages.last?.text.contains("И крупный заголовок") == true,
                  "One final response includes live updates and keeps its original exact source pair")
        try check(app.composer == "Черновик следующего сообщения", "Finishing the task preserves text being typed for the next message")
        let rpc = try String(contentsOf: state.appendingPathComponent("steering-rpc.jsonl"), encoding: .utf8)
            .split(separator: "\n").map { try JSONDecoder().decode(JSONValue.self, from: Data($0.utf8)) }
        try check(rpc.filter { $0["method"].text == "turn/steer" }.count == 3,
                  "Three explicit updates produce exactly three steering calls, including an uncertain reply")
        let restored = AppModel(configuration: LaunchConfiguration(projectRoot: project, python: python, stateDirectory: state))
        try check(restored.messages.first?.taskUpdates?.map(\.state) == [.accepted, .accepted, .unknown]
                  && restored.messages.last?.turnReference != nil,
                  "Restart preserves update delivery states and validates the original turn lineage")
        try check(restored.selected?.history.filter { $0["role"].text == "user" }.count == 3,
                  "Only confirmed updates join a newly bootstrapped provider history")
        let found = await ConversationHistorySearch.find(in: restored.conversations, query: "синюю", scope: .all)
        try check(found.count == 1, "Saved updates remain searchable with their parent task")

        // A prepared but unsent update is never replayed after completion/restart.
        var original = ChatMessage(role: "user", text: "Original task")
        original.taskUpdates = [TaskUpdate(text: "Unsent correction")]
        try TaskUpdate.validate([original])
        try check(original.taskUpdates?.first?.label(active: false) == "Не отправлено",
                  "Restored queued text is visibly unsent rather than silently replayed")
    }
}
