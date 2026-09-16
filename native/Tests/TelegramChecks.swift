import Foundation

private final class TelegramTestSecret: TelegramSecretStoring {
    var value = "12345678:" + String(repeating: "x", count: 32)
    var hasKey: Bool { !value.isEmpty }
    func read() throws -> String { value }
    func save(_ value: String) throws { self.value = value }
    func remove() throws { value = "" }
}

@MainActor
private final class TelegramTestTransport: TelegramTransport {
    var sent: [[String: JSONValue]] = []
    var webhook = ""
    var closed = false
    func call(_ method: String, parameters: [String: JSONValue]) async throws -> JSONValue {
        switch method {
        case "getMe": return .object(["id": .number(12345678), "username": .string("pm_fixture_bot"), "is_bot": .bool(true)])
        case "getWebhookInfo": return .object(["url": .string(webhook)])
        case "getUpdates": try await Task.sleep(for: .seconds(30)); return .array([])
        case "sendMessage": sent.append(parameters); return .object(["message_id": .number(Double(sent.count))])
        default: throw NativeError.message("Unexpected fixture method")
        }
    }
    func close() { closed = true }
}

extension NativeChecks {
    static func telegramUpdate(_ id: Int, _ text: String, user: Int = 42, chat: Int? = nil,
                               fields: [String: JSONValue] = [:]) -> JSONValue {
        var message: [String: JSONValue] = ["text": .string(text), "date": .number(floor(Date().timeIntervalSince1970)),
            "from": .object(["id": .number(Double(user)), "is_bot": .bool(false), "first_name": .string("Fixture owner")]),
            "chat": .object(["id": .number(Double(chat ?? user)), "type": .string("private")])]
        message.merge(fields) { _, new in new }
        return .object(["update_id": .number(Double(id)), "message": .object(message)])
    }

    @MainActor
    static func telegramRemote(fixture: URL, service: URL, python: URL, root: URL) async throws {
        let before = Date().addingTimeInterval(-2)
        try check(TelegramInbound.parse(telegramUpdate(1, "hello"), notBefore: before)?.peer.userID == 42,
                  "Telegram accepts a fresh private message with the exact sender/chat identity")
        for update in [
            telegramUpdate(1, "hello", chat: 84),
            telegramUpdate(1, "hello", fields: ["chat": .object(["id": .number(42), "type": .string("group")])]),
            telegramUpdate(1, "hello", fields: ["from": .object(["id": .number(42), "is_bot": .bool(true)])]),
            telegramUpdate(1, "hello", fields: ["forward_origin": .object(["type": .string("user")])]),
            telegramUpdate(1, "hello", fields: ["via_bot": .object(["id": .number(4)])]),
            telegramUpdate(1, "hello", fields: ["date": .number(Date().timeIntervalSince1970 - 3600)]),
            telegramUpdate(1, "hello", fields: ["date": .number(Date().timeIntervalSince1970 + 3600)]),
            telegramUpdate(1, ""), telegramUpdate(1, "a\0b"), telegramUpdate(1, String(repeating: "x", count: 20_001)),
            .object(["update_id": .number(1), "edited_message": telegramUpdate(1, "hello")["message"]])
        ] {
            try check(TelegramInbound.parse(update, notBefore: before) == nil,
                      "Telegram rejects groups, mismatched peers, forwarded/bot/edited/stale or invalid input")
        }
        try check(TelegramCommand.parse("/use 2") == .use(2) && TelegramCommand.parse("/new New task") == .new("New task")
                  && TelegramCommand.parse("Add one detail") == .message("Add one detail")
                  && TelegramCommand.parse("/stop anything") == .unknown && TelegramCommand.parse("/use nonsense") == .unknown,
                  "Remote commands use an explicit grammar without interpreting arbitrary slash commands")
        let project = root.appendingPathComponent("telegram-project"), state = root.appendingPathComponent("telegram-state")
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        try FileManager.default.copyItem(at: fixture, to: project)
        try FileManager.default.copyItem(at: service, to: project.appendingPathComponent("proto_mind/steering_fixture.py"))
        let bridge = project.appendingPathComponent("proto_mind/native_bridge.py")
        let code = try String(contentsOf: bridge, encoding: .utf8)
            .replacingOccurrences(of: "class NativeBackend:", with: "from proto_mind.steering_fixture import FixtureSubscription, delayed_steering_reply\n\nclass NativeBackend:")
            .replacingOccurrences(of: "subscription_factory=CodexSubscription", with: "subscription_factory=FixtureSubscription")
        try code.write(to: bridge, atomically: true, encoding: .utf8)
        let secret = TelegramTestSecret(), transport = TelegramTestTransport()
        let remote = TelegramRemoteModel(profile: state, secret: secret, directory: root.appendingPathComponent("telegram-receipts"), factory: { _ in transport })
        let app = AppModel(configuration: LaunchConfiguration(projectRoot: project, python: python, stateDirectory: state), telegram: remote)
        defer { app.shutdown() }
        try check(!FileManager.default.fileExists(atPath: remote.store.directory.path), "Reading Telegram metadata creates no connection state")
        await app.start(); app.setProvider("codex"); app.cloudConsent = true; app.setAutoSkillsEnabled(false)
        app.requestAgentAccess(); await app.confirmAgentAccess()
        let a = app.selectedID!
        app.setComposer("Keep the Mac draft")
        let file: JSONValue = .object(["path": .string("draft-only.txt"), "sha256": .string(String(repeating: "0", count: 64)), "included_chars": .number(4), "truncated": .bool(false)])
        app.conversations[app.conversations.firstIndex { $0.id == a }!].pendingFiles = [file]
        try remote.allow(a, enabled: true)
        await remote.connect(app: app)
        try check(remote.running && remote.pairingURL != nil && remote.state.peer == nil, "Connecting a bot does not authorize any Telegram account")
        let contender = TelegramRemoteStore(profile: state, directory: remote.store.directory)
        var locked = false
        do { try contender.acquire() } catch { locked = true }
        try check(locked, "A second instance cannot poll or mutate the same Telegram connection")
        try await remote.consume(telegramUpdate(1, "Run without pairing"))
        try check(transport.sent.isEmpty && !app.isRunning(a), "Unpaired input neither runs a task nor receives private metadata")
        try await remote.consume(telegramUpdate(2, "/start pm_" + remote.pairingCode!))
        try check(remote.pendingPeer?.userID == 42 && remote.state.peer == nil && transport.sent.isEmpty,
                  "A pairing link still requires local approval before remote access")
        try remote.approvePeer()
        try await awaitMessenger { transport.sent.count == 1 }
        let beforeWrongPeer = transport.sent.count
        try await remote.consume(telegramUpdate(3, "/status", user: 99))
        try check(transport.sent.count == beforeWrongPeer && !app.isRunning(a), "A different sender cannot use a paired bot")
        try await remote.consume(telegramUpdate(4, "Remote task A"))
        try await awaitMessenger { app.executions[a]?.updateTarget != nil }
        try check(app.composer == "Keep the Mac draft" && app.selected?.pendingFiles == [file]
                  && app.messages.first?.fileContext?.isEmpty == true, "Remote execution preserves Mac draft text and attachments")
        let acceptedCount = transport.sent.count
        try await remote.consume(telegramUpdate(4, "Run a duplicate"))
        try check(transport.sent.count == acceptedCount && app.messages.filter { $0.role == "user" }.count == 1,
                  "A durably consumed Telegram update cannot execute twice")
        try await remote.consume(telegramUpdate(5, "Remote correction A"))
        try await awaitMessenger { app.conversations.first(where: { $0.id == a })?.messages.first?.taskUpdates?.first?.state == .accepted }
        try await remote.consume(telegramUpdate(6, "/new Remote B"))
        let b = remote.state.selected!
        try check(b != a && app.selectedID == a && app.composer == "Keep the Mac draft"
                  && app.agentGrants[b] == nil && !app.hasAgentAccessSelection(app.conversations.first { $0.id == b }!),
                  "Remote new chat preserves the Mac editor and does not inherit Full Mac rights")
        let count = transport.sent.count
        try Data().write(to: state.appendingPathComponent("finish-steering-" + a.uuidString.lowercased()))
        try await awaitMessenger { !app.isRunning(a) && transport.sent.count > count }
        try check(transport.sent.suffix(from: count).contains { $0["text"]?.text.contains("Remote correction A") == true },
                  "A completed background task sends its saved corrected answer to the requesting Telegram chat")
        try check(try ChatStore(directory: state).load().conversations.first(where: { $0.id == a })?.messages.last?.role == "assistant",
                  "Remote completion is delivered after the ordinary history writer saves the answer")
        try remote.allow(a, enabled: false)
        try await remote.consume(telegramUpdate(7, "/tasks"))
        try check(transport.sent.last?["text"]?.text.contains("Remote B") == true
                  && transport.sent.last?["text"]?.text.contains("Remote task A") == false,
                  "The phone sees only currently shared tasks")
        let stored = try String(contentsOf: remote.store.directory.appendingPathComponent("state.json"), encoding: .utf8)
        try check(!stored.contains(secret.value) && !stored.contains("Remote correction A") && !stored.contains("Keep the Mac draft"),
                  "Telegram receipts contain no token, task content or editor draft")
        try check(try remote.store.load().offset == 8, "The remote cursor survives a fresh read independently of dialog backups")
        app.select(b); app.requestAgentAccess(); await app.confirmAgentAccess()
        app.select(a)
        try await remote.consume(telegramUpdate(8, "Remote task B"))
        try await awaitMessenger { app.executions[b]?.updateTarget != nil }
        try await remote.consume(telegramUpdate(9, "/stop"))
        try await awaitMessenger { !app.isRunning(b) }
        try check(app.selectedID == a && app.composer == "Keep the Mac draft"
                  && (try app.liveVoiceTaskStatus(b))["status"].text == "needs_attention",
                  "Remote stop targets the selected remote execution and preserves the Mac reader")
        try await remote.consume(telegramUpdate(10, "Remote task B again"))
        try await awaitMessenger { app.executions[b]?.updateTarget != nil }
        remote.stop()
        try check(app.isRunning(b), "Disconnecting Telegram leaves already accepted work running")
        let afterDisconnect = transport.sent.count
        try Data().write(to: state.appendingPathComponent("finish-steering-" + b.uuidString.lowercased()))
        try await awaitMessenger { !app.isRunning(b) }
        try check(transport.sent.count == afterDisconnect, "Disconnect suppresses late task replies to Telegram")
        try contender.acquire(); contender.release()
        try check(!remote.running && transport.closed && !remote.store.ownsLease, "Disconnect releases polling ownership")
        let webhookTransport = TelegramTestTransport(); webhookTransport.webhook = "https://other.invalid/webhook"
        let other = TelegramRemoteModel(profile: root.appendingPathComponent("telegram-other"), secret: secret, factory: { _ in webhookTransport })
        await other.connect(app: app)
        try check(!other.running && other.error != nil && webhookTransport.sent.isEmpty,
                  "PM refuses an existing bot webhook without replacing another application's connection")
    }
}
