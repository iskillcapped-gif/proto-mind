import Foundation
import Security
import SwiftUI

struct ModelAPIConnection: Codable, Identifiable, Equatable {
    var id = UUID()
    var name = ""
    var endpoint = "https://api.openai.com/v1"
    var format = "responses"
    var model = ""

    var local: Bool { ["localhost", "127.0.0.1", "::1", "[::1]"].contains(URL(string: endpoint)?.host ?? "") }
    func validate() throws {
        guard !name.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty, name.count <= 80,
              !model.isEmpty, model.count <= 160, ["responses", "chat_completions"].contains(format),
              let url = URL(string: endpoint), NativeBrowserURL.isWebURL(url),
              url.query == nil, url.fragment == nil, url.scheme == "https" || (local && url.scheme == "http"),
              !endpoint.unicodeScalars.contains(where: { $0.value < 33 }),
              !model.unicodeScalars.contains(where: { $0.value < 32 }) else {
            throw NativeError.message(L10n.text("Укажите имя, модель и базовый адрес API (HTTPS; HTTP разрешён только на этом Mac)."))
        }
    }
}

struct ModelAPIKeychain {
    let service: String
    let connection: ModelAPIConnection
    private var query: [String: Any] {
        // Bind credentials to the reviewed destination, not just a mutable connection ID.
        let scope = connection.id.uuidString + "|" + connection.endpoint
        return [kSecClass as String: kSecClassGenericPassword, kSecAttrService as String: service,
                kSecAttrAccount as String: ChatHistoryFormat.hash(Data(scope.utf8))]
    }
    func read() throws -> String {
        var value = query
        value[kSecReturnData as String] = true
        var result: CFTypeRef?
        let status = SecItemCopyMatching(value as CFDictionary, &result)
        if status == errSecItemNotFound && connection.local { return "" }
        guard status == errSecSuccess, let data = result as? Data, let key = String(data: data, encoding: .utf8) else {
            throw NativeError.message(L10n.format("Добавьте API-ключ для «\(connection.name)» в настройках подключений."))
        }
        return key
    }
    func save(_ raw: String) throws {
        let key = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !key.isEmpty, key.utf8.count <= 4096, !key.unicodeScalars.contains(where: { $0.value < 33 || $0.value > 126 }) else {
            throw NativeError.message(L10n.text("Вставьте API-ключ целиком, без пробелов и переносов строк."))
        }
        let attributes: [String: Any] = [kSecValueData as String: Data(key.utf8)]
        var status = SecItemUpdate(query as CFDictionary, attributes as CFDictionary)
        if status == errSecItemNotFound {
            var item = query.merging(attributes) { _, next in next }
            item[kSecAttrAccessible as String] = kSecAttrAccessibleWhenUnlockedThisDeviceOnly
            item[kSecAttrLabel as String] = "Proto-Mind · " + connection.name
            status = SecItemAdd(item as CFDictionary, nil)
        }
        guard status == errSecSuccess else { throw NativeError.message(L10n.format("Связка ключей не сохранила API-ключ (\(status)).")) }
    }
    func remove() throws {
        let status = SecItemDelete(query as CFDictionary)
        guard status == errSecSuccess || status == errSecItemNotFound else { throw NativeError.message(L10n.format("Не удалось удалить API-ключ (\(status)).")) }
    }
}

@MainActor
final class ModelAPIConnections: ObservableObject {
    @Published private(set) var items: [ModelAPIConnection] = []
    let defaults: UserDefaults
    let preferenceKey: String
    let keychainService: String

    init(stateDirectory: URL, defaults: UserDefaults) {
        self.defaults = defaults
        let namespace = String(ChatHistoryFormat.hash(Data(stateDirectory.standardizedFileURL.path.utf8)).prefix(20))
        preferenceKey = "proto-mind.model-api." + namespace
        keychainService = "local.proto-mind.model-api." + namespace
        if let data = defaults.data(forKey: preferenceKey), let decoded = try? JSONDecoder().decode([ModelAPIConnection].self, from: data),
           decoded.count <= 20, Set(decoded.map(\.id)).count == decoded.count,
           decoded.allSatisfy({ (try? $0.validate()) != nil }) { items = decoded }
    }

    func save(_ connection: ModelAPIConnection, secret: String) throws {
        try connection.validate()
        guard items.count < 20 || items.contains(where: { $0.id == connection.id }) else { throw NativeError.message(L10n.text("Можно сохранить до 20 API-подключений.")) }
        let keychain = ModelAPIKeychain(service: keychainService, connection: connection)
        if !secret.isEmpty { try keychain.save(secret) }
        else { _ = try keychain.read() }
        var next = items.filter { $0.id != connection.id }; next.append(connection)
        let data = try JSONEncoder().encode(next)
        defaults.set(data, forKey: preferenceKey)
        items = next
    }

    func remove(_ connection: ModelAPIConnection) throws {
        try ModelAPIKeychain(service: keychainService, connection: connection).remove()
        let next = items.filter { $0.id != connection.id }
        defaults.set(try JSONEncoder().encode(next), forKey: preferenceKey)
        items = next
    }

    func parameters(for conversation: Conversation) throws -> JSONValue {
        guard let connection = items.first(where: { $0.id == conversation.apiConnectionID }) else {
            throw NativeError.message(L10n.text("Выберите API-подключение для этого диалога."))
        }
        try connection.validate()
        let key = try ModelAPIKeychain(service: keychainService, connection: connection).read()
        return .object(["endpoint": .string(connection.endpoint), "format": .string(connection.format), "key": .string(key)])
    }
}

struct ModelAPIConnectionSettings: View {
    @ObservedObject var app: AppModel
    @ObservedObject var connections: ModelAPIConnections
    @State private var draft = ModelAPIConnection()
    @State private var secret = ""
    @State private var error: String?
    @State private var notice: String?
    @State private var editor = false

    var body: some View {
        Section(L10n.text("Модели через API")) {
            Toggle(L10n.text("Разрешить облачную обработку"), isOn: $app.cloudConsent).disabled(app.globalBusy)
            ForEach(connections.items) { connection in
                HStack {
                    VStack(alignment: .leading, spacing: 3) {
                        Text(connection.name)
                        Text(connection.model).font(.caption).foregroundStyle(.secondary)
                    }
                    Spacer()
                    Button(L10n.text("Изменить")) { draft = connection; secret = ""; editor = true; error = nil; notice = nil }
                    Button { do { try connections.remove(connection) } catch { self.error = error.localizedDescription } } label: { Image(systemName: "trash") }
                        .help(L10n.text("Удалить подключение и его ключ")).disabled(app.globalBusy)
                }
            }
            Button(L10n.text("Добавить API-подключение")) { draft = ModelAPIConnection(); secret = ""; editor = true; error = nil; notice = nil }
            if editor {
                TextField(L10n.text("Название"), text: $draft.name, prompt: Text(L10n.text("Мой OpenAI / локальный сервер")))
                Picker(L10n.text("Формат"), selection: $draft.format) {
                    Text("OpenAI Responses").tag("responses")
                    Text(L10n.text("OpenAI-совместимый Chat Completions")).tag("chat_completions")
                }
                TextField(L10n.text("Базовый URL"), text: $draft.endpoint)
                TextField(L10n.text("ID модели"), text: $draft.model, prompt: Text(L10n.text("Точное имя из каталога провайдера")))
                SecureField(L10n.text("API-ключ"), text: $secret, prompt: Text(L10n.text("Оставьте пустым, чтобы сохранить прежний")))
                Text(L10n.text("Ключ отправляется только на этот адрес и хранится в Связке ключей. API оплачивается отдельно от подписки ChatGPT. Локальному серверу ключ не обязателен."))
                    .font(.caption).foregroundStyle(.secondary)
                HStack {
                    Button(L10n.text("Отмена")) { editor = false; secret = "" }
                    Spacer()
                    Button(L10n.text("Сохранить")) {
                        do { try connections.save(draft, secret: secret); secret = ""; editor = false; error = nil; notice = L10n.text("Подключение сохранено. Выберите его в меню модели любого диалога.") }
                        catch { self.error = error.localizedDescription }
                    }.disabled(app.globalBusy)
                }
            }
            if let error { Text(error).font(.caption).foregroundStyle(.orange) }
            if let notice { Text(notice).font(.caption).foregroundStyle(.secondary) }
            Text(L10n.pick("API поддерживает диалог и выбранный контекст. Инструменты PM включаются отдельно для каждого чата: задачи, браузер, документы и MCP. Управление Mac и уточнения во время выполнения остаются в маршруте Codex.", "API supports conversations and selected context. Enable PM tools per chat for tasks, browser, documents and MCP. Mac control and live steering use Codex."))
                .font(.caption).foregroundStyle(.secondary)
        }
    }
}

extension AppModel {
    func selectAPIConnection(_ connection: ModelAPIConnection, conversationID: UUID) {
        guard !operationBusy, !isRunning(conversationID), let index = conversations.firstIndex(where: { $0.id == conversationID }),
              !conversations[index].archived else { return }
        discardAgentGrants(for: conversationID)
        if conversations[index].apiConnectionID != connection.id || conversations[index].provider != "api" {
            conversations[index].apiWorkspaceToolsEnabled = false; conversations[index].apiWorkspaceGeneration = nil
        }
        conversations[index].provider = "api"
        conversations[index].apiConnectionID = connection.id
        conversations[index].model = connection.model
        conversations[index].reasoningEffort = ""
        invalidateContextPreview(); invalidateSessionSpinePilot(); persist()
    }
}

struct APIConnectionPicker: View {
    @ObservedObject var app: AppModel
    @ObservedObject var connections: ModelAPIConnections
    let conversationID: UUID?
    var body: some View {
        Picker(L10n.text("API-подключение"), selection: Binding(get: {
            app.conversations.first { $0.id == conversationID }?.apiConnectionID
        }, set: { next in
            if let id = conversationID, let connection = connections.items.first(where: { $0.id == next }) {
                app.selectAPIConnection(connection, conversationID: id)
            }
        })) {
            Text(L10n.text("Выберите подключение")).tag(UUID?.none)
            ForEach(connections.items) { Text($0.name + " · " + $0.model).tag(Optional($0.id)) }
        }.disabled(app.operationBusy || conversationID.map(app.isRunning) == true)
    }
}

struct ConversationProviderChoices: View {
    @ObservedObject var app: AppModel
    @ObservedObject var connections: ModelAPIConnections
    @Environment(\.workspacePresentations) private var presentations
    let conversationID: UUID
    var chosen: () -> Void = {}
    var body: some View {
        DisclosureGroup(L10n.text("Источник модели")) {
            VStack(alignment: .leading, spacing: 3) {
                ComposerMenuRow(title: L10n.text("ChatGPT · подписка"), icon: "sparkle") { app.configureConversation(conversationID, provider: "codex"); chosen() }
                ComposerMenuRow(title: L10n.text("Ollama · локально"), icon: "desktopcomputer") { app.configureConversation(conversationID, provider: "ollama"); chosen() }
                ForEach(connections.items) { connection in
                    ComposerMenuRow(title: connection.name + " · " + connection.model, icon: "network") {
                        app.selectAPIConnection(connection, conversationID: conversationID); chosen()
                    }
                }
                if let conversation = app.conversations.first(where: { $0.id == conversationID }), conversation.provider == "api" {
                    Toggle(L10n.pick("Инструменты PM", "PM tools"), isOn: Binding(get: { app.apiWorkspaceToolsAllowed(conversation) }, set: { app.setAPIWorkspaceTools($0, id: conversationID) }))
                        .font(.caption).padding(.horizontal, 8)
                }
                ComposerMenuRow(title: L10n.text("Подключить API…"), icon: "plus") {
                    chosen(); app.settingsSection = .services; app.openSettings(in: presentations)
                }
            }.padding(.top, 6)
        }.disclosureGroupStyle(ModelSourceDisclosureStyle()).font(.system(size: 12)).padding(8)
            .disabled(app.operationBusy || app.isRunning(conversationID))
    }
}

private struct ModelSourceDisclosureStyle: DisclosureGroupStyle {
    func makeBody(configuration: Configuration) -> some View {
        VStack(alignment: .leading, spacing: 0) {
            Button { configuration.isExpanded.toggle() } label: {
                HStack(spacing: 8) {
                    configuration.label
                    Spacer(minLength: 8)
                    Image(systemName: configuration.isExpanded ? "chevron.down" : "chevron.right")
                        .font(.system(size: 9, weight: .medium))
                }.frame(maxWidth: .infinity, minHeight: 30).contentShape(Rectangle())
            }.buttonStyle(.nativeHover)
                .accessibilityValue(configuration.isExpanded ? L10n.pick("Развёрнуто", "Expanded") : L10n.pick("Свёрнуто", "Collapsed"))
            if configuration.isExpanded { configuration.content }
        }
    }
}
