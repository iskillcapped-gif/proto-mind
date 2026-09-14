import Foundation

// Opt-in integration probe. Never runs in ordinary tests, never opens a real
// microphone, and never executes a project action. Only synthetic PCM is sent.
extension NativeChecks {
    @MainActor
    static func liveVoiceAPIProbe(stateDirectory: URL, pcm: URL) async throws {
        let key = try LiveVoiceKeychain(stateDirectory: stateDirectory).read()
        let input = try Data(contentsOf: pcm)
        guard input.count < 24_000 * 2 * 20, input.count % 2 == 0 else { throw NativeError.message("Invalid synthetic PCM fixture") }
        let transport = LiveVoiceTransport()
        defer { transport.abort() }
        var started = false, closed = false
        var failure: String?
        var audioBytes = 0, transcript = ""
        var toolNames: [String] = []
        var usage: JSONValue = .null
        var events: [String: Int] = [:]
        var delegations = LiveVoiceDelegations()
        transport.onFailure = { failure = $0 }
        transport.onEvent = { event in
            events[event["type"].text, default: 0] += 1
            do {
                switch event["type"].text {
                case "session.started": started = true
                case "session.closed": closed = true; usage = event["usage"]
                case "session.output_audio.delta": audioBytes += Data(base64Encoded: event["delta"].text)?.count ?? 0
                case "session.output_transcript.delta": transcript += event["delta"].text
                case "error": failure = String(event["error"]["message"].text.prefix(600))
                case "response.event":
                    if let calls = try delegations.receive(event), !calls.isEmpty {
                        for call in calls {
                            toolNames.append(call.name)
                            let result: JSONValue = call.name == "list_projects" || call.name == "list_tasks"
                                ? .object(["status": .string("ok"), "projects": .array([.object(["name": .string("Голосовая проверка"), "path": .string("/synthetic/voice-check")])])])
                                : .object(["status": .string("rejected"), "reason": .string("Synthetic test only; no local actions are allowed.")])
                            transport.send(try LiveVoiceProtocol.toolResult(callID: call.id, result: result))
                        }
                        transport.send(.object(["type": .string("response.create")]))
                    }
                default: break
                }
            } catch { failure = error.localizedDescription }
        }
        transport.connect(key: key, start: LiveVoiceProtocol.start(context: "Synthetic integration test. Use list_projects to answer the spoken question about projects."))
        let deadline = Date().addingTimeInterval(25)
        while !started, failure == nil, Date() < deadline { try await Task.sleep(for: .milliseconds(50)) }
        guard started, failure == nil else { throw NativeError.message(failure ?? "Live start timed out") }
        // One second of silence, the complete utterance, then paced silence.
        let stream = Data(count: 48_000) + input + Data(count: 48_000 * 17)
        for offset in stride(from: 0, to: stream.count, by: 4800) {
            if failure != nil || closed { break }
            let bytes = stream.subdata(in: offset..<min(offset + 4800, stream.count))
            transport.send(.object(["type": .string("session.input_audio.append"), "audio": .string(bytes.base64EncodedString())]))
            try await Task.sleep(for: .milliseconds(100))
        }
        transport.close()
        let closeDeadline = Date().addingTimeInterval(16)
        while !closed, failure == nil, Date() < closeDeadline { try await Task.sleep(for: .milliseconds(50)) }
        let result: JSONValue = .object(["started": .bool(started), "closed": .bool(closed), "audio_bytes": .number(Double(audioBytes)),
            "tools": .array(toolNames.map(JSONValue.string)), "transcript": .string(transcript), "usage": usage,
            "event_counts": .object(events.mapValues { .number(Double($0)) }), "error": failure.map(JSONValue.string) ?? .null])
        print(result.pretty.replacingOccurrences(of: "sk-[A-Za-z0-9_-]+", with: "[key hidden]", options: .regularExpression))
        guard closed, failure == nil, audioBytes > 0, toolNames.contains("list_projects") || toolNames.contains("list_tasks") else {
            throw NativeError.message("Live API smoke did not verify audio plus delegated project lookup")
        }
    }
}
