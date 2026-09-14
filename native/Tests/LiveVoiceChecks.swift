import Foundation
import SwiftUI
import AVFoundation

extension NativeChecks {
    static func voiceCall(_ name: String, _ args: [String: JSONValue] = [:], id: String = UUID().uuidString) throws -> LiveVoiceCall {
        try LiveVoiceCall(.object(["type": .string("function_call"), "call_id": .string(id),
            "name": .string(name), "arguments": .string(JSONValue.object(args).pretty)]))
    }

    @MainActor
    static func liveVoiceContracts(root: URL) throws {
        let start = LiveVoiceProtocol.start(context: "Selected: fixture")
        try check(start["type"] == .string("session.start") && start["session"]["model"] == .string("gpt-live-1")
                  && start["session"]["store"] == .bool(false), "Live uses its own protocol and disables remote session storage")
        try check(start["session"]["audio"]["format"]["rate"] == .number(24_000)
                  && start["session"]["delegation"]["responses"]["parallel_tool_calls"] == .bool(false),
                  "Live audio format and serial tool configuration match the public contract")
        let keyA = LiveVoiceKeychain(stateDirectory: root.appendingPathComponent("a"))
        let keyB = LiveVoiceKeychain(stateDirectory: root.appendingPathComponent("b"))
        try check(keyA.service != keyB.service, "Disposable state has an independent credential namespace")
        let unicode = String(repeating: "😀й", count: 600)
        try check(LiveVoiceProtocol.append("session.commentary.append", unicode)["content"].text.utf8.count <= 400,
                  "Live context hints remain below the token ceiling even with multibyte text")
        var opening = LiveVoiceOpening()
        let greeting = opening.begin()!
        try check(!greeting["event_id"].text.isEmpty && opening.begin() == nil,
                  "Opening greeting is issued once with a correlated event ID")
        try check(opening.acknowledge(.object(["type": .string("session.instructions.appended"), "client_event_id": .string("old")])) == nil,
                  "An unrelated context acknowledgment cannot trigger a greeting")
        let acknowledgment: JSONValue = .object(["type": .string("session.instructions.appended"), "client_event_id": greeting["event_id"]])
        try check(opening.acknowledge(acknowledgment)?["type"].text == "session.commentary.append"
                  && opening.acknowledge(acknowledgment) == nil, "Greeting prompt follows its own acknowledged instructions once")
        var interrupted = LiveVoiceOpening()
        let interruptedGreeting = interrupted.begin()!
        interrupted.heardUser = true
        try check(interrupted.acknowledge(.object(["type": .string("session.instructions.appended"), "client_event_id": interruptedGreeting["event_id"]])) == nil,
                  "Greeting does not restart a conversation after the caller has spoken")
        let preferences = PreferenceStore(directory: root.appendingPathComponent("voice-preferences"))
        _ = try preferences.load()
        try preferences.save(NativePreferences())
        let before = try Data(contentsOf: preferences.url)
        var overflowRejected = false
        do {
            try preferences.save(NativePreferences(rememberedAgentAccess: [.init(conversationID: UUID(), workspace: String(repeating: "a", count: 70_000))]))
        } catch { overflowRejected = true }
        let afterOverflow = try Data(contentsOf: preferences.url)
        try check(overflowRejected && afterOverflow == before,
                  "Oversized permission preferences cannot replace a readable settings file")
        var state = LiveVoiceDelegations()
        func event(_ type: String, _ fields: [String: JSONValue] = [:]) -> JSONValue {
            .object(["type": .string("response.event"), "delegation_id": .string("delegation-A"),
                     "event": .object(fields.merging(["type": .string(type)]) { _, new in new })])
        }
        try check(try state.receive(event("response.created", ["response": .object(["id": .string("response-A")])])) == nil,
                  "Response start cannot execute a tool")
        try check(try state.receive(event("response.function_call_arguments.done", ["arguments": .string("{}")])) == nil,
                  "Incomplete argument events never execute project commands")
        let item: JSONValue = .object(["type": .string("function_call"), "call_id": .string("call-A"),
            "name": .string("list_tasks"), "arguments": .string("{}")])
        try check(try state.receive(event("response.output_item.done", ["item": item])) == nil,
                  "Completed function item waits for the matching response boundary")
        let released = try state.receive(event("response.completed", ["response": .object(["id": .string("response-A"), "output": .array([])])]))
        try check(released?.count == 1 && released?.first?.id == "call-A", "Empty final output does not discard pending Live function calls")
        _ = try state.receive(event("response.created", ["response": .object(["id": .string("response-B")])]))
        do { _ = try state.receive(event("response.output_item.done", ["item": item])); throw NativeError.message("Duplicate call accepted") }
        catch { try check(error.localizedDescription.contains("Повторная"), "Duplicate Live call IDs cannot repeat a local action") }
        for (name, args) in [("shell", ["command": JSONValue.string("rm -rf anything")]),
                             ("list_tasks", ["extra": .bool(true)]),
                             ("open_task", ["conversation_id": .string("unknown")]),
                             ("send_task_message", ["conversation_id": .string(UUID().uuidString), "text": .number(42)])] {
            var rejected = false
            do { _ = try voiceCall(name, args) } catch { rejected = true }
            try check(rejected, "Live rejects an unknown tool, extra field, invalid ID or invalid argument type: \(name)")
        }
        let app = AppModel(configuration: LaunchConfiguration(projectRoot: root, python: root, stateDirectory: root.appendingPathComponent("voice-defaults")))
        defer { app.shutdown() }
        try check(!app.liveVoice.inCall && app.liveVoice.captions.isEmpty && !app.liveVoice.hasKey,
                  "Launching an isolated app never activates the microphone or imports a real API key")
        let view = NSHostingController(rootView: LiveVoiceView(app: app, voice: app.liveVoice))
        let size = view.sizeThatFits(in: CGSize(width: 454, height: 589))
        try check(size.width <= 454 && size.height <= 589, "Voice setup stays within its compact panel")
        try check(!FileManager.default.fileExists(atPath: root.appendingPathComponent("voice-defaults").path),
                  "Voice setup and rendering do not write preferences or history")
    }

    @MainActor
    static func liveVoiceIntegration(fixture: URL, service: URL, python: URL, root: URL) async throws {
        let project = root.appendingPathComponent("voice-project"), stateDirectory = root.appendingPathComponent("voice-state")
        try FileManager.default.copyItem(at: fixture, to: project)
        try FileManager.default.copyItem(at: service, to: project.appendingPathComponent("proto_mind/steering_fixture.py"))
        let bridge = project.appendingPathComponent("proto_mind/native_bridge.py")
        let code = try String(contentsOf: bridge, encoding: .utf8)
            .replacingOccurrences(of: "class NativeBackend:", with: "from proto_mind.steering_fixture import FixtureSubscription, delayed_steering_reply\n\nclass NativeBackend:")
            .replacingOccurrences(of: "subscription_factory=CodexSubscription", with: "subscription_factory=FixtureSubscription")
        try code.write(to: bridge, atomically: true, encoding: .utf8)
        let configuration = LaunchConfiguration(projectRoot: project, python: python, stateDirectory: stateDirectory)
        let app = AppModel(configuration: configuration)
        defer { app.shutdown() }
        await app.start(); app.setProvider("codex"); app.cloudConsent = true; app.setAutoSkillsEnabled(false)
        app.requestAgentAccess(); await app.confirmAgentAccess()
        let a = app.selectedID!, session = UUID()
        app.setComposer("Несвязанный черновик A")
        let file: JSONValue = .object(["path": .string("draft-only.txt"), "sha256": .string(String(repeating: "0", count: 64)),
                                      "included_chars": .number(4), "truncated": .bool(false)])
        let index = app.conversations.firstIndex { $0.id == a }!
        app.conversations[index].pendingFiles = [file]; app.conversations[index].pendingCriteria = ["Критерий черновика"]
        let accepted = try await app.executeLiveVoiceCall(voiceCall("send_task_message", ["conversation_id": .string(a.uuidString), "text": .string("Голосовая задача A")]), session: session)
        try check(accepted["status"] == .string("preparing"), "Voice acknowledges preparation without claiming task completion")
        try await awaitVoiceCondition { app.executions[a]?.updateTarget != nil }
        try check(app.composer == "Несвязанный черновик A" && app.selected?.pendingFiles == [file]
                  && app.messages.first?.fileContext?.isEmpty == true, "Voice starts the task without consuming draft text or attachments")
        let created = try await app.executeLiveVoiceCall(voiceCall("create_task", ["title": .string("Задача B"), "project_path": .null]), session: session)
        let b = UUID(uuidString: created["conversation_id"].text)!
        app.setComposer("Черновик B")
        try check(app.selectedID == b && app.isRunning(a) && !app.fullAccessEnabled, "Voice creates a second task without transferring Full Mac access")
        let update = try await app.executeLiveVoiceCall(voiceCall("send_task_message", ["conversation_id": .string(a.uuidString), "text": .string("Голосовое уточнение A")]), session: session)
        try check(update["status"] == .string("queued") && app.selectedID == b && app.composer == "Черновик B",
                  "Voice correction targets a background task and preserves the selected editor")
        try await awaitVoiceCondition { app.conversations.first(where: { $0.id == a })?.messages.first?.taskUpdates?.first?.state == .accepted }
        let status = try await app.executeLiveVoiceCall(voiceCall("task_status", ["conversation_id": .string(a.uuidString)]), session: session)
        try check(status["status"] == .string("running"), "Voice reports the actual running state of a background task")
        app.liveVoice.shutdown()
        try check(app.isRunning(a), "Hanging up the voice channel leaves the working task running")
        try Data().write(to: stateDirectory.appendingPathComponent("finish-steering-" + a.uuidString.lowercased()))
        try await awaitVoiceCondition { !app.isRunning(a) }
        let final = try app.liveVoiceTaskStatus(a)
        try check(final["status"] == .string("response_received") && final["answer"].text.contains("Голосовое уточнение A"),
                  "Voice work and its accepted correction produce a saved answer in the correct task")
        let completed = app.conversations.first { $0.id == a }!
        try check(app.selectedID == b && app.composer == "Черновик B" && completed.draft == "Несвязанный черновик A"
                  && completed.pendingFiles == [file] && completed.pendingCriteria == ["Критерий черновика"],
                  "Background voice completion preserves both editors and their draft context")
        let restart = AppModel(configuration: configuration)
        defer { restart.shutdown() }
        try check(restart.conversations == app.conversations && !restart.liveVoice.inCall,
                  "Voice task history survives restart without automatically opening a paid call")
    }

    @MainActor
    private static func awaitVoiceCondition(_ condition: () -> Bool) async throws {
        let deadline = Date().addingTimeInterval(20)
        while !condition(), Date() < deadline { try await Task.sleep(for: .milliseconds(20)) }
        guard condition() else { throw NativeError.message("Voice fixture did not reach the expected task boundary") }
    }
}
