import Foundation

extension NativeChecks {
    static func mobileContracts(root: URL) throws {
        let secret = String(repeating: "a", count: 64)
        let pairing = MobilePairing(endpoint: "https://mac.example.ts.net", code: secret, expiresAt: Date().addingTimeInterval(300))
        let parsed = try MobilePairing.parse(pairing.link!)
        try check(parsed.link == pairing.link && parsed.code == pairing.code && abs(parsed.expiresAt.timeIntervalSince(pairing.expiresAt)) < 0.001,
                  "Mobile pairing round-trips its private fragment without a query")
        try check(MobileWire.endpoint("http://mac.example") == nil && MobileWire.endpoint("https://u:p@mac.example") == nil
                  && MobileWire.endpoint("https://mac.example/path") == nil && MobileWire.endpoint("https://mac.example?secret=a") == nil,
                  "Mobile endpoints require HTTPS without credentials, paths or queries")
        let expired = MobilePairing(endpoint: pairing.endpoint, code: secret, expiresAt: Date().addingTimeInterval(-1))
        try check((try? MobilePairing.parse(expired.link!)) == nil && (try? MobilePairing.parse("https://example.com")) == nil,
                  "Expired or unrelated QR links cannot pair a phone")
        let command = MobileCommand(id: UUID(), conversationID: UUID(), kind: .send, text: "One message", expectedRunID: nil, createdAt: Date())
        let decoded = try MobileWire.decoder().decode(MobileCommand.self, from: MobileWire.encoder().encode(command))
        try check(decoded.fingerprint == command.fingerprint && decoded.valid(now: Date()), "Command identity survives wire serialization")
        let invalidDate = MobileCommand(id: command.id, conversationID: command.conversationID, kind: .send, text: "x", expectedRunID: nil, createdAt: Date(timeIntervalSince1970: 1e100))
        try check((try? MobileWire.encoder().encode(invalidDate)) == nil && !invalidDate.valid(now: Date()), "An out-of-range wire date is rejected without trapping the server")
        let stale = MobileCommand(id: command.id, conversationID: command.conversationID, kind: .send, text: "old", expectedRunID: nil, createdAt: Date().addingTimeInterval(-601))
        try check(!stale.valid(now: Date()), "Old unreserved commands cannot execute after receipt pruning")
        let header = "POST /v1/commands HTTP/1.1\r\nHost: localhost\r\nContent-Type: application/json\r\nContent-Length: 2\r\n\r\n"
        try check(try MobileHTTPRequest.parse(Data((header + "{").utf8)) == nil, "Fragmented HTTP bodies wait for all bytes")
        try check(try MobileHTTPRequest.parse(Data((header + "{}").utf8))?.body == Data("{}".utf8), "Complete bounded HTTP request parses")
        for bad in [header + "{}extra", header.replacingOccurrences(of: "Host: localhost", with: "Host: localhost\r\nOrigin: https://evil.invalid") + "{}",
                    header.replacingOccurrences(of: "Content-Length: 2", with: "Content-Length: 2\r\nContent-Length: 2") + "{}",
                    header.replacingOccurrences(of: "Content-Length: 2", with: "Transfer-Encoding: chunked") + "{}",
                    "GET /v1/chats?before=a&before=b HTTP/1.1\r\nHost: localhost\r\n\r\n"] {
            try check((try? MobileHTTPRequest.parse(Data(bad.utf8))) == nil, "HTTP rejects browser origins, duplicate headers, smuggling and ambiguous query parameters")
        }
        let store = MobileRemoteStore(profile: root.appendingPathComponent("mobile-store-profile"))
        try check(try store.load().devices.isEmpty && !FileManager.default.fileExists(atPath: store.directory.path), "Reading mobile metadata never creates files")
        try store.acquire(); defer { store.release() }
        var state = MobileRemoteState(); state.endpoint = pairing.endpoint
        try store.save(state)
        let other = MobileRemoteStore(profile: root.appendingPathComponent("mobile-store-profile"))
        var locked = false; do { try other.acquire() } catch { locked = true }
        try check(locked, "Only one PM instance owns a phone connection")
        let original = try Data(contentsOf: store.file)
        try Data("different".utf8).write(to: store.file)
        var refused = false; do { try store.save(state) } catch { refused = true }
        try check(refused && (try Data(contentsOf: store.file)) == Data("different".utf8), "Conflicting state writes preserve outside changes")
        try original.write(to: store.file)
    }

    @MainActor
    static func mobileRemote(fixture: URL, service: URL, python: URL, root: URL) async throws {
        let project = root.appendingPathComponent("mobile-project"), state = root.appendingPathComponent("mobile-state")
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        try FileManager.default.copyItem(at: fixture, to: project)
        try FileManager.default.copyItem(at: service, to: project.appendingPathComponent("proto_mind/steering_fixture.py"))
        let bridge = project.appendingPathComponent("proto_mind/native_bridge.py")
        let code = try String(contentsOf: bridge, encoding: .utf8)
            .replacingOccurrences(of: "class NativeBackend:", with: "from proto_mind.steering_fixture import FixtureSubscription, delayed_steering_reply\n\nclass NativeBackend:")
            .replacingOccurrences(of: "subscription_factory=CodexSubscription", with: "subscription_factory=FixtureSubscription")
        try code.write(to: bridge, atomically: true, encoding: .utf8)
        let app = AppModel(configuration: LaunchConfiguration(projectRoot: project, python: python, stateDirectory: state))
        let remote = app.mobile, transport = RemoteTransport(); transport.allowLoopback = true
        defer { transport.close(); app.shutdown() }
        await app.start(); app.setProvider("codex"); app.cloudConsent = true; app.setAutoSkillsEnabled(false)
        let a = app.selectedID!
        app.setComposer("Keep the Mac draft")
        try remote.setEndpoint("https://mac.example.ts.net"); try remote.allow(a, enabled: true)
        try remote.start(app: app, port: 0); try await awaitMessenger { remote.running || remote.error != nil }
        try check(remote.running && remote.state.allowed == [a], "Starting the loopback server preserves the initial explicit chat selection")
        let endpoint = "http://127.0.0.1:\(remote.port)", token = try MobileRemoteStore.secret(), device = UUID()
        var refused = false
        do { _ = try await transport.request(endpoint: endpoint, path: "/v1/chats", token: "", body: nil) } catch let error as RemoteHTTPError { refused = error.status == 401 }
        try check(refused, "Actual TCP listener exposes no conversations without a pairing token")
        try remote.beginPairing()
        let pair = MobilePairRequest(code: remote.pairing!.code, deviceID: device, name: "Disposable iPhone", token: token)
        _ = try await transport.request(endpoint: endpoint, path: "/v1/pair", token: "", body: MobileWire.encoder().encode(pair))
        refused = false
        do { _ = try await transport.request(endpoint: endpoint, path: "/v1/chats", token: token, body: nil) } catch let error as RemoteHTTPError { refused = error.code == "awaiting_approval" }
        try check(refused && remote.state.devices.isEmpty, "Knowing a pairing code is insufficient until the Mac approves the phone")
        try remote.approve()
        let listData = try await transport.request(endpoint: endpoint, path: "/v1/chats", token: token, body: nil)
        let list = try MobileWire.decoder().decode(MobileChatList.self, from: listData)
        try check(list.chats.map(\.id) == [a] && list.chats.first?.fullAccess == false, "Paired phone sees only shared chats and their real permission state")

        func send(_ command: MobileCommand) async throws -> MobileReceipt {
            let data = try await transport.request(endpoint: endpoint, path: "/v1/commands", token: token, body: MobileWire.encoder().encode(command))
            return try MobileWire.decoder().decode(MobileReceipt.self, from: data)
        }
        let first = MobileCommand(id: UUID(), conversationID: a, kind: .send, text: "Phone task A", expectedRunID: nil, createdAt: Date())
        let receipt = try await send(first)
        try check(receipt.status == .accepted && receipt.fingerprint == first.fingerprint, "Phone text is durably accepted through the shared task execution path")
        try await awaitMessenger { app.executions[a]?.updateTarget != nil }
        let repeated = try await send(first)
        try check(repeated == receipt && app.messages.filter { $0.role == "user" }.count == 1 && app.composer == "Keep the Mac draft",
                  "Repeated command IDs return the same receipt without sending or consuming the Mac draft")
        let wrong = MobileCommand(id: first.id, conversationID: a, kind: .send, text: "Different input", expectedRunID: nil, createdAt: first.createdAt)
        refused = false
        do { _ = try await send(wrong) } catch let error as RemoteHTTPError { refused = error.status == 409 }
        try check(refused, "Reusing a command ID with different content is rejected")
        let run = app.executions[a]!.requestID!
        let update = MobileCommand(id: UUID(), conversationID: a, kind: .send, text: "Keep it concise", expectedRunID: run, createdAt: Date())
        let updateReceipt = try await send(update)
        try await awaitMessenger { app.messages.first?.taskUpdates?.first?.state == .accepted }
        try check(updateReceipt.status == .accepted && app.isRunning(a), "A phone correction joins the existing live task instead of starting another")
        let create = MobileCommand(id: UUID(), conversationID: a, kind: .create, text: "Phone B", expectedRunID: nil, createdAt: Date())
        let created = try await send(create), b = create.id
        try check(created.createdConversationID == b && app.selectedID == a && !app.hasAgentAccessSelection(app.conversations.first { $0.id == b }!),
                  "Creating a phone chat preserves Mac navigation and grants no Full Mac permission")
        let bSend = MobileCommand(id: UUID(), conversationID: b, kind: .send, text: "Phone task B", expectedRunID: nil, createdAt: Date())
        _ = try await send(bSend); try await awaitMessenger { app.executions[b]?.updateTarget != nil }
        try check(app.isRunning(a) && app.isRunning(b), "Independent phone tasks can run in parallel on the Mac")
        let staleStop = MobileCommand(id: UUID(), conversationID: b, kind: .stop, text: "", expectedRunID: "wrong-run", createdAt: Date())
        refused = false
        do { _ = try await send(staleStop) } catch let error as RemoteHTTPError { refused = error.code == "task_changed" }
        try check(refused && app.isRunning(b), "A delayed stop cannot cancel a different turn")
        let stop = MobileCommand(id: UUID(), conversationID: b, kind: .stop, text: "", expectedRunID: app.executions[b]!.requestID!, createdAt: Date())
        let stopped = try await send(stop); try await awaitMessenger { !app.isRunning(b) }
        try check(stopped.status == .accepted && app.isRunning(a), "Phone stop cancels only the exact target execution")
        try Data().write(to: state.appendingPathComponent("finish-steering-" + a.uuidString.lowercased()))
        try await awaitMessenger { !app.isRunning(a) }
        let history = try MobileWire.decoder().decode(MobileTranscript.self, from: await transport.request(endpoint: endpoint, path: "/v1/chats/" + a.uuidString, token: token, body: nil))
        try check(history.messages.last?.text.contains("Keep it concise") == true && history.chat.status == "response_received",
                  "The phone reads the saved answer, including its live correction, after completion")
        let stored = try String(contentsOf: remote.store.file, encoding: .utf8)
        try check(!stored.contains(token) && !stored.contains("Phone task A") && !stored.contains("Keep the Mac draft"),
                  "Mac pairing and receipt records contain neither raw token nor prompt/draft text")
        try remote.allow(a, enabled: false)
        refused = false
        do { _ = try await transport.request(endpoint: endpoint, path: "/v1/chats/" + a.uuidString, token: token, body: nil) } catch let error as RemoteHTTPError { refused = error.status == 404 }
        try check(refused, "Removing a chat immediately revokes transcript access")
        try remote.revoke(device)
        refused = false
        do { _ = try await transport.request(endpoint: endpoint, path: "/v1/chats", token: token, body: nil) } catch let error as RemoteHTTPError { refused = error.status == 401 }
        try check(refused, "Unpairing immediately invalidates the phone token")
        remote.stop()
        var saved = try remote.store.load()
        var reserved = receipt; reserved.status = .reserved; saved.receipts = [reserved]
        saved.generation = String(repeating: "e", count: 64)
        saved.devices = [MobileDevice(id: device, name: "Old phone", tokenHash: MobileWire.hash(Data(token.utf8)), pairedAt: Date())]
        try remote.store.acquire(); try remote.store.save(saved); remote.store.release()
        try remote.start(app: app, port: 0); try await awaitMessenger { remote.running }
        try check(remote.state.devices.isEmpty && remote.state.allowed.isEmpty && remote.state.receipts.first?.status == .unknown,
                  "Restore generation changes invalidate phone authority and interrupted receipts never replay")
    }
}
