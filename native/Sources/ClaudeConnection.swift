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
        await claudeAccount.refresh(app: self, minimumInterval: 0)
    }

    func authenticateClaude(_ operation: String) async {
        guard ["login", "logout"].contains(operation), !claudeTasksRunning, !operationBusy,
              !claudeAuthenticating, !claudeAccount.refreshing else { return }
        claudeAccount.clear()
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
    @ObservedObject var account: ClaudeAccountModel
    @Environment(\.workspacePresentations) private var presentations
    init(app: AppModel) { self.app = app; self.account = app.claudeAccount }
    var body: some View {
        Section("Claude · Claude Code") {
            LabeledContent(L10n.pick("Подключение", "Connection"), value: account.snapshot == nil
                ? L10n.pick("Не проверено", "Not checked") : account.snapshot?.connected == true
                ? L10n.pick("Подключено", "Connected") : L10n.pick("Нужен вход", "Sign in required"))
            if let snapshot = account.snapshot {
                Text([snapshot.email, snapshot.plan.capitalized].filter { !$0.isEmpty }.joined(separator: " · "))
                    .font(.callout).textSelection(.enabled)
            }
            Text(L10n.pick("Вход через официальный Claude Code. Для работы по подписке выберите свой аккаунт Claude с доступом к Claude Code (например, Pro или Max). Вход через Console использует отдельную оплату API.", "Sign in through official Claude Code. For subscription usage, choose your Claude account with Claude Code access (such as Pro or Max). Console login uses separate API billing."))
                .font(.callout).foregroundStyle(.secondary)
            HStack {
                Button(L10n.pick("Войти в Claude", "Sign in to Claude")) { Task { await app.authenticateClaude("login") } }
                Button(L10n.pick("Выйти", "Sign out")) { Task { await app.authenticateClaude("logout") } }
                    .disabled(account.snapshot?.connected != true)
                Spacer()
                Button(L10n.text("Обновить")) { Task { await app.refreshClaudeAccount() } }
            }.disabled(app.operationBusy || app.claudeTasksRunning || app.claudeAuthenticating || account.refreshing)
            if let terminal = app.claudeAuthenticationTerminal {
                WorkspaceTerminalView(terminal: terminal).frame(height: 270).clipShape(RoundedRectangle(cornerRadius: 10))
                Button(L10n.pick("Закрыть вход", "Close sign-in")) { app.closeClaudeAuthentication() }
            }
            if let error = app.claudeAccountError { Text(error).font(.caption).foregroundStyle(.orange) }
            if let error = account.error { Text(error).font(.caption).foregroundStyle(.secondary) }
            Button(L10n.pick("Посмотреть лимиты Claude", "View Claude limits")) {
                app.presentations.prepare("codexUsage", in: presentations ?? app.presentations)
                app.openAccountUsage("claude")
            }
            Text(L10n.pick("Пароль и токены обрабатывает Claude Code. PM не копирует их в диалоги или резервные копии. После входа выберите Claude в меню модели любого чата.", "Claude Code handles passwords and tokens. PM does not copy them into chats or backups. After sign-in, choose Claude in any chat’s model menu."))
                .font(.caption).foregroundStyle(.secondary)
        }.task { await app.refreshClaudeAccount() }
    }
}

struct ClaudeModelControls: View {
    @ObservedObject var app: AppModel
    @ObservedObject var account: ClaudeAccountModel
    let conversationID: UUID?
    init(app: AppModel, conversationID: UUID?) { self.app = app; self.account = app.claudeAccount; self.conversationID = conversationID }
    private var context: ConversationComposerContext { ConversationComposerContext(app: app, id: conversationID) }
    var body: some View {
        Group {
        Picker(L10n.text("Модель"), selection: Binding(get: { context.conversation?.model ?? "" }, set: context.setModel)) {
            Text(L10n.text("Автоматически")).tag("")
            ForEach(account.snapshot?.models.filter { !$0.isDefault } ?? []) { Text($0.title).tag($0.id) }
            if let model = context.conversation?.model, !model.isEmpty,
               account.snapshot?.models.contains(where: { $0.id == model }) != true { Text(account.label(for: model)).tag(model) }
        }
        TextField(L10n.pick("Или точный ID модели", "Or an exact model ID"), text: Binding(get: { context.conversation?.model ?? "" }, set: context.setModel))
        Picker(L10n.text("Усилие"), selection: Binding(get: { context.conversation?.reasoningEffort ?? "" }, set: context.setEffort)) {
            Text(L10n.text("Авто")).tag("")
            ForEach(account.snapshot?.model(context.conversation?.model ?? "")?.efforts ?? [], id: \.self) { Text(ClaudeSelection.effortTitle($0)).tag($0) }
            if let effort = context.conversation?.reasoningEffort, !effort.isEmpty,
               account.snapshot?.model(context.conversation?.model ?? "")?.efforts.contains(effort) != true {
                Text(ClaudeSelection.effortTitle(effort)).tag(effort)
            }
        }
        Text(L10n.pick("Доступность моделей и усилий определяет Claude Code для вашего аккаунта. Каждый запрос получает последние сообщения PM и выбранную память. Уточнения во время работы пока доступны только в Codex.", "Claude Code determines model and effort availability for your account. Each request receives recent PM messages and selected memory. Live steering is currently available only with Codex."))
            .font(.caption).foregroundStyle(.secondary)
        }.task { await account.refresh(app: app) }
    }
}
