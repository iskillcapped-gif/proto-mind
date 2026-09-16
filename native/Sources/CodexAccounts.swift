import AppKit
import Combine
import SwiftUI

/// A login owns its metadata client and quota cache. Task bridges keep the same
/// immutable account ID but never share this client's live RPC connection.
@MainActor
final class CodexAccountConnection: ObservableObject, Identifiable {
    nonisolated let accountID: UUID?
    nonisolated var id: String { accountID?.uuidString ?? "main" }
    @Published var name: String
    @Published var account: JSONValue = .null
    @Published var models: [JSONValue] = []
    @Published var connecting = false
    @Published var loginPending = false
    @Published var error: String?
    let client: BridgeClient
    let usage: CodexUsageModel

    init(id: UUID?, name: String, client: BridgeClient) {
        accountID = id; self.name = name; self.client = client
        usage = CodexUsageModel(accountID: id, client: client)
    }
    var label: String {
        let email = account["email"].text
        return email.isEmpty ? name : name + " · " + email
    }
    var shortName: String { name.count > 12 ? String(name.prefix(12)) + "…" : name }
    var options: [CodexModelOption] {
        var seen = Set<String>()
        return models.compactMap(CodexModelOption.init).filter { seen.insert($0.id).inserted }
    }
}

@MainActor
final class CodexAccounts: ObservableObject {
    struct Entry: Codable { let id: UUID?; var name: String }
    @Published private(set) var items: [CodexAccountConnection] = []
    private let defaults: UserDefaults
    private let key: String
    private let configuration: LaunchConfiguration
    private var observations: [AnyCancellable] = []

    init(configuration: LaunchConfiguration, defaults: UserDefaults, mainClient: BridgeClient) {
        self.configuration = configuration; self.defaults = defaults
        key = "proto-mind.codex-accounts." + String(ChatHistoryFormat.hash(Data(configuration.stateDirectory.standardizedFileURL.path.utf8)).prefix(20))
        let decoded = defaults.data(forKey: key).flatMap { try? JSONDecoder().decode([Entry].self, from: $0) }
        let entries = decoded.flatMap { values in
            values.count <= 20 && Set(values.map { $0.id }).count == values.count
                && values.allSatisfy { Self.validName($0.name) } ? values : nil
        } ?? []
        add(CodexAccountConnection(id: nil, name: entries.first { $0.id == nil }?.name ?? L10n.pick("Основной", "Main"), client: mainClient))
        for entry in entries where entry.id != nil {
            add(CodexAccountConnection(id: entry.id, name: entry.name,
                client: BridgeClient(configuration: configuration, codexAccountID: entry.id)))
        }
    }
    private static func validName(_ name: String) -> Bool {
        !name.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && name.count <= 60
            && !name.unicodeScalars.contains { CharacterSet.controlCharacters.contains($0) }
    }
    private func add(_ connection: CodexAccountConnection) {
        items.append(connection)
        observations.append(connection.objectWillChange.sink { [weak self] in self?.objectWillChange.send() })
    }
    func connection(_ id: UUID?) -> CodexAccountConnection {
        if let existing = items.first(where: { $0.accountID == id }) { return existing }
        // Restored chats retain their exact account namespace even if this Mac
        // has no label/login for it. Never silently substitute the main login.
        let value = CodexAccountConnection(id: id, name: L10n.pick("Аккаунт ", "Account ") + String(id!.uuidString.prefix(6)),
            client: BridgeClient(configuration: configuration, codexAccountID: id))
        add(value)
        return value
    }
    @discardableResult func create(name: String) throws -> CodexAccountConnection {
        let name = name.trimmingCharacters(in: .whitespacesAndNewlines)
        guard Self.validName(name), items.count < 20 else {
            throw NativeError.message(L10n.pick("Введите название до 60 символов. Можно добавить до 20 аккаунтов.", "Enter a name of up to 60 characters. You can add up to 20 accounts."))
        }
        let value = connection(UUID())
        value.name = name; save()
        return value
    }
    func rename(_ connection: CodexAccountConnection, to name: String) throws {
        let name = name.trimmingCharacters(in: .whitespacesAndNewlines)
        guard Self.validName(name) else { throw NativeError.message(L10n.pick("Введите название от 1 до 60 символов.", "Enter a name of 1 to 60 characters.")) }
        connection.name = name; save()
    }
    private func save() {
        guard let data = try? JSONEncoder().encode(items.map { Entry(id: $0.accountID, name: $0.name) }) else { return }
        defaults.set(data, forKey: key)
    }
    func clearUsage() { items.forEach { $0.usage.clear() } }
    func shutdown() { items.forEach { $0.client.shutdown() } }
}

extension AppModel {
    var selectedCodexAccount: CodexAccountConnection { codexAccount(for: selectedID) }
    func codexAccount(for conversationID: UUID?) -> CodexAccountConnection {
        codexAccounts.connection(conversations.first { $0.id == conversationID }?.codexAccountID)
    }
    func codexModels(for conversationID: UUID) -> [CodexModelOption] { codexAccount(for: conversationID).options }
    func accountHasRunningTasks(_ id: UUID?) -> Bool {
        executions.values.contains { $0.client.codexAccountID == id && ($0.running || $0.client.turnOutstanding || $0.sendingUpdate) }
    }
    func accountCanAuthenticate(_ connection: CodexAccountConnection) -> Bool {
        !operationBusy && !privateBackupRestartRequired && !connection.connecting
            && !connection.usage.resetting && !accountHasRunningTasks(connection.accountID)
    }
    func requireConversationAccount(_ conversation: Conversation) throws {
        guard conversation.provider == "codex" else { return }
        let connection = codexAccounts.connection(conversation.codexAccountID)
        guard !connection.connecting, !connection.loginPending, !connection.usage.resetting else {
            throw NativeError.message(L10n.pick("Дождитесь завершения подключения этого аккаунта ChatGPT.", "Wait for this ChatGPT account to finish connecting."))
        }
    }
    func prepareConversationAccount(_ state: ConversationExecution) async throws {
        let id = state.conversationID
        guard let conversation = conversations.first(where: { $0.id == id }),
              executions[id] === state, conversation.codexAccountID == state.client.codexAccountID else {
            throw NativeError.message(L10n.pick("Аккаунт чата изменился. Отправьте сообщение ещё раз.", "The chat account changed. Send the message again."))
        }
        try requireConversationAccount(conversation)
        guard conversation.provider == "codex", conversation.codexSessionResetPending == true else { return }
        // Returning to an earlier login must not resume its stale provider thread.
        // Keep this marker until the local reset and history save both succeed.
        restoringAgentAccess.removeValue(forKey: id)?.cancel()
        agentGrants.removeValue(forKey: id)
        let result = try await state.client.request("codex_thread_reset", [
            "conversation_id": .string(id.uuidString), "confirmation": .string("START NEW CODEX SESSION"),
        ])
        try Task.checkCancellation()
        guard result["schema"].text == "proto_mind.native_codex_thread_reset.v1",
              result["no_provider_call"].flag, result["provider_history_deleted"] == .bool(false),
              executions[id] === state,
              let index = conversations.firstIndex(where: { $0.id == id && $0.codexAccountID == state.client.codexAccountID }) else {
            throw NativeError.message(L10n.pick("Не удалось подготовить новую сессию аккаунта. Сообщение не отправлено.", "Couldn't prepare the account's new session. The message was not sent."))
        }
        conversations[index].codexSessionResetPending = nil
        guard persist() else {
            conversations[index].codexSessionResetPending = true
            throw NativeError.message(L10n.pick("Не удалось сохранить смену сессии. Сообщение не отправлено.", "Couldn't save the session change. The message was not sent."))
        }
    }
    func selectCodexAccount(_ accountID: UUID?, conversationID: UUID) {
        guard !operationBusy, !privateBackupRestartRequired, !isRunning(conversationID),
              executions[conversationID]?.client.turnOutstanding != true,
              executions[conversationID]?.sendingUpdate != true,
              let index = conversations.firstIndex(where: { $0.id == conversationID }),
              !conversations[index].archived, conversations[index].codexAccountID != accountID else { return }
        let original = conversations[index]
        conversations[index].codexAccountID = accountID
        conversations[index].codexSessionResetPending = true
        conversations[index].model = ""; conversations[index].reasoningEffort = ""
        conversations[index].draftContinuation = nil
        guard persist() else { conversations[index] = original; return }
        discardAgentGrants(for: conversationID)
        executions.removeValue(forKey: conversationID)?.client.shutdown()
        _ = execution(for: conversationID)
        invalidateContextPreview(); invalidateSessionSpinePilot()
        if selectedID == conversationID { codexThreadStatus = .null; modelSelectionNotice = nil }
        let connection = codexAccounts.connection(accountID)
        if cloudConsent { Task { await refreshAccount(connection) } }
    }
    private func closeAccountExecutions(_ accountID: UUID?) {
        let ids = Set(conversations.filter { $0.codexAccountID == accountID }.map(\.id))
        if rememberedAgentAccess.contains(where: { ids.contains($0.conversationID) }) {
            rememberedAgentAccess.removeAll { ids.contains($0.conversationID) }
            do { try savePreferences() } catch { report(error) }
        }
        if let pending = pendingAgentAccess, ids.contains(pending.conversationID) { pendingAgentAccess = nil }
        for id in ids {
            restoringAgentAccess.removeValue(forKey: id)?.cancel()
            agentGrants.removeValue(forKey: id)
            executions.removeValue(forKey: id)?.client.shutdown()
        }
    }
    func login(_ target: CodexAccountConnection? = nil) async {
        let connection = target ?? selectedCodexAccount
        guard accountCanAuthenticate(connection), !codexAccounts.items.contains(where: { $0 !== connection && ($0.loginPending || $0.connecting) }) else { return }
        connection.connecting = true; connection.error = nil; connection.usage.clear()
        defer { connection.connecting = false }
        do {
            connection.account = try await connection.client.request("account_status")
            if connection.account["connected"].flag {
                connection.models = try await connection.client.request("models")["models"].items
                return
            }
            closeAccountExecutions(connection.accountID)
            let result = try await connection.client.request("account_login")
            guard let url = URL(string: result["url"].text), url.scheme == "https", url.user == nil, url.password == nil,
                  ["auth.openai.com", "chatgpt.com", "openai.com"].contains(url.host ?? "") else {
                throw NativeError.message("Неожиданный адрес входа; браузер не открыт.")
            }
            connection.loginPending = true
            NSWorkspace.shared.open(url)
        } catch { connection.error = error.localizedDescription }
    }
    func cancelAccountLogin(_ connection: CodexAccountConnection) async {
        guard !connection.connecting, connection.loginPending else { return }
        connection.connecting = true
        defer { connection.connecting = false }
        do {
            _ = try await connection.client.request("account_login_cancel")
            connection.loginPending = false; connection.error = nil
        } catch { connection.error = error.localizedDescription }
    }
    func refreshAccount(_ target: CodexAccountConnection? = nil) async {
        let connection = target ?? selectedCodexAccount
        guard !operationBusy, !privateBackupRestartRequired, !connection.connecting else { return }
        connection.connecting = true; connection.error = nil
        defer { connection.connecting = false }
        do {
            let previous = connection.account
            connection.account = try await connection.client.request("account_status")
            if previous["email"] != connection.account["email"] || previous["connected"] != connection.account["connected"] { connection.usage.clear() }
            if connection.account["connected"].flag {
                connection.loginPending = false
                connection.models = try await connection.client.request("models")["models"].items
            } else { connection.models = [] }
        } catch { connection.error = error.localizedDescription }
    }
    func logout(_ target: CodexAccountConnection? = nil) async {
        let connection = target ?? selectedCodexAccount
        guard accountCanAuthenticate(connection) else { return }
        closeAccountExecutions(connection.accountID)
        connection.connecting = true; connection.error = nil; connection.usage.clear()
        defer { connection.connecting = false }
        do {
            connection.account = try await connection.client.request("account_logout")
            connection.models = []; connection.loginPending = false
        } catch { connection.error = error.localizedDescription }
    }
    func openCodexUsage(_ target: CodexAccountConnection? = nil) {
        presentedCodexAccount = target ?? selectedCodexAccount
        showCodexUsage = true
    }
}
