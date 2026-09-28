import Foundation

@MainActor
func makeRemoteModel() -> RemoteModel {
#if DEBUG
    if ProcessInfo.processInfo.arguments.contains("--ui-fixture") {
        let model = RemoteModel(transport: RemotePreviewTransport(), persistence: RemotePreviewStorage())
        if ProcessInfo.processInfo.arguments.contains("--ui-chat") {
            Task {
                await model.refresh()
                if let id = model.chats.first?.id { await model.open(id) }
            }
        }
        return model
    }
#endif
    return RemoteModel(transport: RemoteTransport(), persistence: RemoteStorage())
}

#if DEBUG
// Simulator-only visual fixture requested by an explicit launch argument. No
// network, provider, files, real connection or Keychain item is used or modified.
private final class RemotePreviewStorage: RemotePersistence {
    var state = RemoteLocalState()
    var paired: RemoteConnection? = RemoteConnection(endpoint: "https://demo.invalid", deviceID: UUID(), token: String(repeating: "a", count: 64))
    func connection() throws -> RemoteConnection? { paired }
    func save(connection: RemoteConnection?) throws { paired = connection }
    func load() throws -> RemoteLocalState { state }
    func save(state: RemoteLocalState) throws { self.state = state }
}

private final class RemotePreviewTransport: RemoteRequesting {
    let chats = [
        MobileChat(id: UUID(), title: R("Предложение для Northstar", "Northstar proposal"), projectID: "northstar", projectName: "Northstar Studio · DEMO", provider: "codex", model: "GPT-6 Astra", effort: "high", account: "Personal", fullAccess: false, status: "response_received", runID: nil, updatedAt: Date(), canUpdate: false),
        MobileChat(id: UUID(), title: R("Проверить мобильное подключение", "Review mobile connection"), projectID: "pm", projectName: "Proto-Mind · DEMO", provider: "claude", model: "Claude Opus 5.5", effort: "max", account: "Claude Code", fullAccess: true, status: "running", runID: "fixture-run", updatedAt: Date(), canUpdate: true)
    ]
    func request(endpoint: String, path: String, token: String, body: Data?) async throws -> Data {
        if path == "/v1/status" { return try MobileWire.encoder().encode(MobileServerInfo(name: "DEMO", status: "connected")) }
        if path == "/v1/chats" { return try MobileWire.encoder().encode(MobileChatList(chats: chats)) }
        if let chat = chats.first(where: { path == "/v1/chats/" + $0.id.uuidString }) {
            return try MobileWire.encoder().encode(MobileTranscript(chat: chat, messages: [
                MobileMessage(id: chat.id, role: "user", text: R("Подготовь короткое предложение по брифу. Отдели условия от предположений.", "Prepare a concise proposal from the brief. Separate included work from assumptions."), createdAt: Date().addingTimeInterval(-90), isError: false, truncated: false, updates: [], updatesTruncated: false),
                MobileMessage(id: UUID(uuidString: "876DA131-1E8B-49F4-A89D-0755D3D04C71")!, role: "assistant", text: R("**Предложение готово.**\n\nВ работу входят дизайн главной страницы, адаптация для телефона и форма заявки.\n\nБюджет указан в евро; платные интеграции и тексты клиента вынесены в предположения.\n\nПеред началом нужно уточнить сроки и согласовать материалы. Файл сохранён в проекте на Mac.", "**The proposal is ready.**\n\nIncluded work covers the homepage design, a mobile layout, and a contact form.\n\nThe budget is in euros. Paid integrations and client copy are listed as assumptions.\n\nBefore starting, confirm the timeline and source materials. The file is saved in the project on your Mac."), createdAt: Date().addingTimeInterval(-30), isError: false, truncated: false, updates: [], updatesTruncated: false)
            ], before: nil, liveText: "", liveTruncated: false, activity: chat.status == "running" ? R("Проверяю сохранение черновиков…", "Checking draft preservation…") : ""))
        }
        throw RemoteHTTPError(status: 409, code: "task_unavailable")
    }
}
#endif
