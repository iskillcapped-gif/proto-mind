import SwiftUI

enum ClaudeSelection {
    static let models = ["", "sonnet", "opus", "haiku"]
    static let efforts = ["", "low", "medium", "high", "xhigh", "max"]
    static func title(_ model: String) -> String {
        model.isEmpty ? L10n.text("По умолчанию для аккаунта") : models.contains(model) ? model.capitalized : model
    }
    static func effortTitle(_ effort: String) -> String {
        effort.isEmpty ? L10n.text("Авто") : CodexReasoningEffort(rawValue: effort)?.title ?? effort
    }
}

extension AppModel {
    var claudeTasksRunning: Bool {
        conversations.contains { $0.provider == "claude" && isRunning($0.id) }
    }

    func refreshClaudeAccount() async {
        guard !claudeAccountLoading, !claudeAuthenticating else { return }
        claudeAccountLoading = true
        defer { claudeAccountLoading = false }
        do {
            claudeAccountStatus = try await serviceClient.request("claude_status")
            claudeAccountError = claudeAccountStatus["error"].text.isEmpty ? nil : claudeAccountStatus["error"].text
        } catch { claudeAccountError = error.localizedDescription }
    }

    func authenticateClaude(_ operation: String) async {
        guard ["login", "logout"].contains(operation), !claudeTasksRunning, !operationBusy,
              !claudeAuthenticating, !claudeAccountLoading else { return }
        claudeAuthenticating = true
        claudeAccountError = nil
        do {
            let command = try await serviceClient.request("claude_auth_command", ["operation": .string(operation)])
            guard !claudeTasksRunning, !operationBusy, case .object(let environment) = command["environment"],
                  command["arguments"].items.map(\.text) == ["auth", operation],
                  command["executable"].text.hasPrefix("/"), command["directory"].text.hasPrefix("/"),
                  environment.values.allSatisfy({ if case .string = $0 { return true }; return false }) else {
                throw NativeError.message(L10n.pick("Подключение изменилось. Повторите вход.", "Connection changed. Start sign-in again."))
            }
            let terminal = WorkspaceTerminal(directory: URL(fileURLWithPath: command["directory"].text))
            claudeAuthenticationTerminal?.close()
            claudeAuthenticationTerminal = terminal
            terminal.onExit = { [weak self, weak terminal] _ in
                guard let self, let terminal, self.claudeAuthenticationTerminal === terminal else { return }
                self.claudeAuthenticating = false
                Task { await self.refreshClaudeAccount() }
            }
            terminal.start(executable: command["executable"].text, arguments: ["auth", operation], environment: environment.mapValues(\.text))
            if !terminal.running {
                claudeAuthenticating = false
                await refreshClaudeAccount()
            }
        } catch { claudeAuthenticating = false; claudeAccountError = error.localizedDescription }
    }

    func closeClaudeAuthentication() {
        claudeAuthenticationTerminal?.close()
        claudeAuthenticationTerminal = nil
        claudeAuthenticating = false
    }
}

struct ClaudeConnectionSettings: View {
    @ObservedObject var app: AppModel
    var body: some View {
        Section("Claude · Claude Code") {
            LabeledContent(L10n.pick("Подключение", "Connection"), value: app.claudeAccountStatus.isNull
                ? L10n.pick("Не проверено", "Not checked") : app.claudeAccountStatus["connected"].flag
                ? L10n.pick("Подключено", "Connected") : L10n.pick("Нужен вход", "Sign in required"))
            if !app.claudeAccountStatus["email"].text.isEmpty { Text(app.claudeAccountStatus["email"].text).font(.callout).textSelection(.enabled) }
            if !app.claudeAccountStatus["subscriptionType"].text.isEmpty {
                Text(app.claudeAccountStatus["subscriptionType"].text).font(.caption).foregroundStyle(.secondary)
            }
            Text(L10n.pick("Вход через официальный Claude Code. Для работы по подписке выберите свой аккаунт Claude с доступом к Claude Code (например, Pro или Max). Вход через Console использует отдельную оплату API.", "Sign in through official Claude Code. For subscription usage, choose your Claude account with Claude Code access (such as Pro or Max). Console login uses separate API billing."))
                .font(.callout).foregroundStyle(.secondary)
            HStack {
                Button(L10n.pick("Войти в Claude", "Sign in to Claude")) { Task { await app.authenticateClaude("login") } }
                Button(L10n.pick("Выйти", "Sign out")) { Task { await app.authenticateClaude("logout") } }
                    .disabled(!app.claudeAccountStatus["connected"].flag)
                Spacer()
                Button(L10n.text("Обновить")) { Task { await app.refreshClaudeAccount() } }
            }.disabled(app.operationBusy || app.claudeTasksRunning || app.claudeAuthenticating || app.claudeAccountLoading)
            if let terminal = app.claudeAuthenticationTerminal {
                WorkspaceTerminalView(terminal: terminal).frame(height: 270).clipShape(RoundedRectangle(cornerRadius: 10))
                Button(L10n.pick("Закрыть вход", "Close sign-in")) { app.closeClaudeAuthentication() }
            }
            if let error = app.claudeAccountError { Text(error).font(.caption).foregroundStyle(.orange) }
            Text(L10n.pick("Пароль и токены обрабатывает Claude Code. PM не копирует их в диалоги или резервные копии. После входа выберите Claude в меню модели любого чата.", "Claude Code handles passwords and tokens. PM does not copy them into chats or backups. After sign-in, choose Claude in any chat’s model menu."))
                .font(.caption).foregroundStyle(.secondary)
        }.task { await app.refreshClaudeAccount() }
    }
}

struct ClaudeModelControls: View {
    @ObservedObject var app: AppModel
    let conversationID: UUID?
    private var context: ConversationComposerContext { ConversationComposerContext(app: app, id: conversationID) }
    var body: some View {
        Picker(L10n.text("Модель"), selection: Binding(get: { context.conversation?.model ?? "" }, set: context.setModel)) {
            ForEach(ClaudeSelection.models, id: \.self) { Text(ClaudeSelection.title($0)).tag($0) }
            if let model = context.conversation?.model, !ClaudeSelection.models.contains(model) { Text(model).tag(model) }
        }
        TextField(L10n.pick("Или точный ID модели", "Or an exact model ID"), text: Binding(get: { context.conversation?.model ?? "" }, set: context.setModel))
        Picker(L10n.text("Усилие"), selection: Binding(get: { context.conversation?.reasoningEffort ?? "" }, set: context.setEffort)) {
            ForEach(ClaudeSelection.efforts, id: \.self) { Text(ClaudeSelection.effortTitle($0)).tag($0) }
        }
        Text(L10n.pick("Доступность моделей и усилий определяет Claude Code для вашего аккаунта. Каждый запрос получает последние сообщения PM и выбранную память. Уточнения во время работы пока доступны только в Codex.", "Claude Code determines model and effort availability for your account. Each request receives recent PM messages and selected memory. Live steering is currently available only with Codex."))
            .font(.caption).foregroundStyle(.secondary)
    }
}
