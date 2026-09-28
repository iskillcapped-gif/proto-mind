import Foundation

final class MobileTestStorage: RemotePersistence {
    var paired: RemoteConnection? = RemoteConnection(endpoint: "https://mac.example.ts.net", deviceID: UUID(), token: String(repeating: "a", count: 64))
    var state = RemoteLocalState()
    var fails = false
    func connection() throws -> RemoteConnection? { paired }
    func save(connection: RemoteConnection?) throws { if fails { throw MobileClientError.disconnected }; paired = connection }
    func load() throws -> RemoteLocalState { state }
    func save(state: RemoteLocalState) throws { if fails { throw MobileClientError.disconnected }; self.state = state }
}

final class MobileTestTransport: RemoteRequesting {
    let store: MobileTestStorage
    var posted: [MobileCommand] = []
    var lostReply = false
    var receipt: MobileReceipt?
    var status: MobileReceipt.Status = .accepted
    let chat = MobileChat(id: UUID(), title: "Sample", projectID: "project", projectName: "Project", provider: "codex", model: "fixture", effort: "medium", account: "Original", fullAccess: false, status: "idle", runID: nil, updatedAt: Date(), canUpdate: false)
    init(_ store: MobileTestStorage) { self.store = store }
    func request(endpoint: String, path: String, token: String, body: Data?) async throws -> Data {
        if path == "/v1/status" { return try MobileWire.encoder().encode(MobileServerInfo(name: "Fixture", status: "connected")) }
        if path == "/v1/chats" { return try MobileWire.encoder().encode(MobileChatList(chats: [chat])) }
        if path.hasPrefix("/v1/chats/") { return try MobileWire.encoder().encode(MobileTranscript(chat: chat, messages: [], before: nil, liveText: "", liveTruncated: false, activity: "")) }
        if path == "/v1/commands", let body {
            let command = try MobileWire.decoder().decode(MobileCommand.self, from: body)
            guard store.state.pending?.id == command.id else { throw NativeError.message("Mutation happened before durable local receipt") }
            posted.append(command)
            receipt = MobileReceipt(id: command.id, deviceID: store.paired!.deviceID, fingerprint: command.fingerprint,
                conversationID: command.conversationID, createdAt: Date(), status: status, code: "preparing")
            if lostReply { throw MobileClientError.disconnected }
            return try MobileWire.encoder().encode(receipt!)
        }
        if path.hasPrefix("/v1/commands/"), let receipt { return try MobileWire.encoder().encode(receipt) }
        throw RemoteHTTPError(status: 404, code: "receipt_not_found")
    }
}

extension NativeChecks {
    @MainActor
    static func mobileClient() async throws {
        let storage = MobileTestStorage(), transport = MobileTestTransport(storage)
        let model = RemoteModel(transport: transport, persistence: storage)
        await model.refresh(); model.setDraft("Keep this thought", id: transport.chat.id)
        transport.lostReply = true
        await model.submit(kind: .send, chat: transport.chat, text: "Keep this thought")
        try check(model.local.pending != nil && model.draft(transport.chat.id) == "Keep this thought" && transport.posted.count == 1,
                  "A lost phone reply keeps the draft and exact command ID")
        await model.submit(kind: .send, chat: transport.chat, text: "Keep this thought")
        try check(transport.posted.count == 1, "An unresolved command cannot be resent by a second tap")
        let restarted = RemoteModel(transport: transport, persistence: storage)
        await restarted.refresh()
        try check(transport.posted.count == 1 && restarted.local.pending == nil && restarted.draft(transport.chat.id).isEmpty,
                  "After app restart the phone reconciles a receipt with GET and never repeats POST")
        storage.fails = true
        await restarted.submit(kind: .send, chat: transport.chat, text: "Cannot save")
        try check(transport.posted.count == 1, "Storage failure prevents a command from leaving the phone")
        storage.fails = false
        restarted.setDraft("New text", id: transport.chat.id)
        transport.status = .unknown
        await restarted.submit(kind: .send, chat: transport.chat, text: "New text")
        await restarted.refresh(); await restarted.refresh()
        try check(transport.posted.count == 2 && restarted.local.pending != nil && restarted.draft(transport.chat.id) == "New text",
                  "Unknown server outcomes remain visible and polling cannot replay actions")
        restarted.acknowledgeUncertain()
        try check(restarted.local.pending == nil && transport.posted.count == 2 && restarted.draft(transport.chat.id) == "New text",
                  "Explicit uncertainty acknowledgement preserves the draft without resending")
    }
}
