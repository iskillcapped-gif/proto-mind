import Foundation
import SwiftUI

struct WorkspaceService: Codable, Identifiable, Equatable {
    var id = UUID()
    var name = ""
    var transport = "http"
    var endpoint = "https://"
    var command = ""
    var arguments: [String] = []
    var enabled = false
    var usesToken = false

    func validate() throws {
        guard !name.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty, name.count <= 80,
              ["http", "stdio"].contains(transport), arguments.count <= 40,
              arguments.allSatisfy({ $0.count <= 2048 && !$0.contains("\0") }) else { throw NativeError.message("Invalid MCP connection.") }
        if transport == "http" {
            guard let url = URL(string: endpoint), NativeBrowserURL.isWebURL(url), url.query == nil, url.fragment == nil,
                  url.scheme == "https" || ["localhost", "127.0.0.1", "::1", "[::1]"].contains(url.host ?? "") else {
                throw NativeError.message(L10n.pick("Укажите HTTPS-адрес MCP или HTTP на этом Mac.", "Enter an HTTPS MCP endpoint or HTTP on this Mac."))
            }
        } else {
            guard command.hasPrefix("/"), command.count <= 4096, FileManager.default.isExecutableFile(atPath: command), !usesToken else {
                throw NativeError.message(L10n.pick("Выберите абсолютный путь к программе MCP.", "Choose the absolute path of an MCP executable."))
            }
        }
    }
}

@MainActor final class WorkspaceServices: ObservableObject {
    private struct Session: Hashable {
        let service: UUID
        let owner: UUID?
    }
    @Published private(set) var items: [WorkspaceService] = []
    private let defaults: UserDefaults
    private let preference: String
    private let keychainService: String
    private let configuration: LaunchConfiguration
    private var clients: [Session: BridgeClient] = [:]
    private var active: Set<Session> = []
    private var catalogs: [Session: Set<String>] = [:]

    init(configuration: LaunchConfiguration, defaults: UserDefaults) {
        self.configuration = configuration; self.defaults = defaults
        let namespace = String(ChatHistoryFormat.hash(Data(configuration.stateDirectory.path.utf8)).prefix(20))
        preference = "proto-mind.mcp." + namespace; keychainService = "local.proto-mind.mcp." + namespace
        if let data = defaults.data(forKey: preference), let stored = try? JSONDecoder().decode([WorkspaceService].self, from: data),
           stored.count <= 20, Set(stored.map(\.id)).count == stored.count { items = stored }
    }

    private func keychain(_ service: WorkspaceService) -> ModelAPIKeychain {
        var binding = ModelAPIConnection(); binding.id = service.id; binding.name = service.name; binding.endpoint = service.endpoint
        return ModelAPIKeychain(service: keychainService, connection: binding)
    }

    func save(_ service: WorkspaceService, token: String = "") throws {
        try service.validate()
        guard !active.contains(where: { $0.service == service.id }), items.count < 20 || items.contains(where: { $0.id == service.id }) else { throw NativeError.message("MCP connection is busy or the list is full.") }
        if service.usesToken {
            if !token.isEmpty { try keychain(service).save(token) } else { _ = try keychain(service).read() }
        }
        let next = items.filter { $0.id != service.id } + [service]
        defaults.set(try JSONEncoder().encode(next), forKey: preference); items = next
        closeSessions { $0.service == service.id }
    }

    func remove(_ service: WorkspaceService) throws {
        guard !active.contains(where: { $0.service == service.id }) else { throw NativeError.message("MCP connection is busy.") }
        if service.usesToken { try keychain(service).remove() }
        let next = items.filter { $0.id != service.id }
        defaults.set(try JSONEncoder().encode(next), forKey: preference); items = next
        closeSessions { $0.service == service.id }
    }

    func perform(id: UUID, operation: String, name: String = "", arguments: JSONValue = .object([:]), cursor: String = "", owner: UUID? = nil) async throws -> JSONValue {
        guard let service = items.first(where: { $0.id == id && $0.enabled }) else { throw NativeError.message("Enable an available MCP connection in Settings first.") }
        let session = Session(service: id, owner: owner)
        guard !active.contains(session) else { throw NativeError.message(L10n.pick("Подключение MCP выполняет предыдущий запрос. Дождитесь его завершения.", "This MCP connection is completing its previous request. Wait for it to finish.")) }
        try service.validate()
        if operation == "call" && catalogs[session]?.contains(name) != true { throw NativeError.message("List this service's tools before calling one.") }
        let token = service.usesToken ? try keychain(service).read() : ""
        active.insert(session)
        defer { active.remove(session) }
        let client = clients[session] ?? BridgeClient(configuration: configuration); clients[session] = client
        do {
            let result = try await client.request("workspace_mcp", ["connection": .object([
                "transport": .string(service.transport), "endpoint": .string(service.endpoint), "command": .string(service.command),
                "arguments": .array(service.arguments.map(JSONValue.string)), "secret": .string(token)]),
                "operation": .string(operation), "name": .string(name), "arguments": arguments, "cursor": .string(cursor)])
            guard items.contains(service), clients[session] === client else { throw NativeError.message("MCP connection changed while the request was running.") }
            if operation == "list" {
                let names = Set(result["tools"].items.map { $0["name"].text }.filter { !$0.isEmpty && $0.count <= 200 })
                catalogs[session] = (cursor.isEmpty ? [] : catalogs[session] ?? []).union(names)
            }
            return result
        } catch {
            if clients[session] === client {
                clients.removeValue(forKey: session)?.shutdown()
                catalogs.removeValue(forKey: session)
            }
            throw error
        }
    }

    /// A Settings check owns no task, so its bridge and server close when the check ends.
    func checkTools(id: UUID) async throws -> Int {
        defer { closeSessions { $0.service == id && $0.owner == nil && !active.contains($0) } }
        return try await perform(id: id, operation: "list")["tools"].items.count
    }

    func cancel(owner: UUID) {
        closeSessions { $0.owner == owner }
    }

    private func closeSessions(where matches: (Session) -> Bool) {
        for session in clients.keys.filter(matches) {
            clients.removeValue(forKey: session)?.shutdown()
            catalogs.removeValue(forKey: session)
        }
    }

    func shutdown() { closeSessions { _ in true } }
}

struct WorkspaceServiceSettings: View {
    @ObservedObject var app: AppModel
    @ObservedObject var services: WorkspaceServices
    @State private var draft = WorkspaceService()
    @State private var editing = false
    @State private var token = ""
    @State private var arguments = "[]"
    @State private var error: String?
    @State private var checking: Set<UUID> = []
    @State private var toolCounts: [UUID: Int] = [:]

    var body: some View {
        Section {
            if services.items.isEmpty {
                Text(L10n.pick("Пока нет подключений.", "No connections yet.")).foregroundStyle(.secondary)
            }
            ForEach(services.items) { item in
                HStack(spacing: 10) {
                    VStack(alignment: .leading, spacing: 3) {
                        Text(item.name)
                        Text(subtitle(item)).font(.caption).foregroundStyle(.secondary).lineLimit(1).truncationMode(.middle)
                    }
                    Spacer(minLength: 8)
                    if checking.contains(item.id) { ProgressView().controlSize(.small) }
                    SettingsMoreMenu { actions(item) }
                    Toggle(L10n.pick("Разрешить задачам использовать подключение", "Allow tasks to use this connection"), isOn: Binding(get: { item.enabled }, set: { enabled in
                        var next = item; next.enabled = enabled
                        do { try services.save(next); error = nil } catch { self.error = error.localizedDescription }
                    })).labelsHidden().help(L10n.pick("Разрешить задачам использовать подключение", "Allow tasks to use this connection"))
                }.contextMenu { actions(item) }
            }
            if !editing {
                HStack {
                    Spacer()
                    Button(L10n.pick("Добавить MCP", "Add MCP")) { draft = WorkspaceService(); token = ""; arguments = "[]"; editing = true; error = nil }
                }
            }
        } header: { Text(L10n.pick("Подключения", "Connections")) } footer: {
            Text(L10n.pick("Подключите инструменты своих сервисов. Включённые подключения доступны задачам с инструментами PM и могут выполнять действия от вашего имени.", "Connect your services' tools. Enabled connections are available to tasks with PM tools and can act on your behalf."))
                .font(.caption).foregroundStyle(.secondary)
        }.disabled(app.globalBusy)
        if editing {
            Section {
                TextField(L10n.text("Название"), text: $draft.name)
                Picker(L10n.pick("Подключение", "Connection"), selection: $draft.transport) { Text("Streamable HTTP").tag("http"); Text("Local stdio").tag("stdio") }
                    .onChange(of: draft.transport) { _, value in if value == "stdio" { draft.usesToken = false } }
                if draft.transport == "http" {
                    TextField("MCP URL", text: $draft.endpoint)
                    Toggle("Bearer token", isOn: $draft.usesToken)
                    if draft.usesToken { SecureField(L10n.pick("Токен · хранится в Связке ключей", "Token · stored in Keychain"), text: $token) }
                } else {
                    TextField(L10n.pick("Путь к программе", "Executable path"), text: $draft.command)
                    TextField(L10n.pick("Аргументы (JSON-массив)", "Arguments (JSON array)"), text: $arguments)
                }
                Toggle(L10n.pick("Разрешить задачам использовать подключение", "Allow tasks to use this connection"), isOn: $draft.enabled)
                HStack {
                    Spacer()
                    Button(L10n.text("Отмена")) { token = ""; editing = false }
                    Button(L10n.text("Сохранить")) {
                        do {
                            draft.arguments = try JSONDecoder().decode([String].self, from: Data(arguments.utf8)); try services.save(draft, token: token)
                            toolCounts[draft.id] = nil; token = ""; editing = false; error = nil
                        } catch { self.error = error.localizedDescription }
                    }.buttonStyle(.borderedProminent)
                }
            } header: {
                Text(services.items.contains { $0.id == draft.id } ? L10n.pick("Изменить подключение", "Edit connection") : L10n.pick("Новое подключение", "New connection"))
            } footer: {
                if draft.transport != "http" {
                    Text(L10n.pick("Вход выполните средствами самого сервиса. Не помещайте ключи в аргументы.", "Sign in using the service's own tools. Keep keys out of arguments."))
                        .font(.caption).foregroundStyle(.secondary)
                }
            }.disabled(app.globalBusy)
        }
        if let error {
            Section { Label(error, systemImage: "exclamationmark.circle").font(.caption).foregroundStyle(.orange).textSelection(.enabled) }
        }
    }

    /// Where the connection points, and how many tools its last check found.
    private func subtitle(_ item: WorkspaceService) -> String {
        let place = item.transport == "stdio" ? item.command : item.endpoint
        guard let count = toolCounts[item.id] else { return place }
        return place + " · " + L10n.pick("инструменты: ", "tools: ") + String(count)
    }

    @ViewBuilder private func actions(_ item: WorkspaceService) -> some View {
        Button(L10n.pick("Проверить инструменты", "Check tools")) { check(item) }
            .disabled(!item.enabled || checking.contains(item.id))
        Button(L10n.pick("Изменить…", "Edit…")) {
            draft = item; token = ""; arguments = (try? String(data: JSONEncoder().encode(item.arguments), encoding: .utf8)) ?? "[]"; editing = true; error = nil
        }
        Divider()
        Button(L10n.pick("Удалить", "Remove"), role: .destructive) {
            do { try services.remove(item); toolCounts[item.id] = nil; error = nil } catch { self.error = error.localizedDescription }
        }
    }

    private func check(_ item: WorkspaceService) {
        checking.insert(item.id)
        Task {
            defer { checking.remove(item.id) }
            do { toolCounts[item.id] = try await services.checkTools(id: item.id); error = nil }
            catch { toolCounts[item.id] = nil; self.error = item.name + ": " + error.localizedDescription }
        }
    }
}
