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
        Section {
            HStack(spacing: 12) {
                VStack(alignment: .leading, spacing: 3) {
                    if let snapshot = account.snapshot, snapshot.connected {
                        Text(snapshot.email.isEmpty ? L10n.pick("Аккаунт Claude", "Claude account") : snapshot.email)
                            .font(.system(size: 13, weight: .medium)).textSelection(.enabled)
                        Text(snapshot.plan.isEmpty ? L10n.pick("Вход через Claude Code", "Signed in through Claude Code")
                             : L10n.pick("План ", "Plan ") + snapshot.plan.capitalized + L10n.pick(" · вход через Claude Code", " · signed in through Claude Code"))
                            .font(.caption).foregroundStyle(.secondary)
                    } else {
                        Text(account.snapshot != nil ? L10n.pick("Вход не выполнен", "Not signed in")
                             : account.refreshing ? L10n.pick("Проверяем…", "Checking…") : L10n.pick("Не проверено", "Not checked"))
                            .font(.system(size: 13, weight: .medium))
                        Text(L10n.pick("Вход через официальный Claude Code", "Sign in through official Claude Code")).font(.caption).foregroundStyle(.secondary)
                    }
                }
                Spacer()
                if account.refreshing { ProgressView().controlSize(.small) }
                Button { Task { await app.refreshClaudeAccount() } } label: { Image(systemName: "arrow.clockwise") }
                    .help(L10n.text("Обновить")).accessibilityLabel(L10n.text("Обновить"))
                if account.snapshot?.connected == true {
                    Button(L10n.pick("Выйти", "Sign out")) { Task { await app.authenticateClaude("logout") } }
                } else {
                    Button(L10n.pick("Войти в Claude", "Sign in to Claude")) { Task { await app.authenticateClaude("login") } }.buttonStyle(.borderedProminent)
                }
            }.disabled(app.operationBusy || app.claudeTasksRunning || app.claudeAuthenticating || account.refreshing)
            if let terminal = app.claudeAuthenticationTerminal {
                WorkspaceTerminalView(terminal: terminal).frame(height: 270).clipShape(RoundedRectangle(cornerRadius: 10))
                HStack { Spacer(); Button(L10n.pick("Закрыть вход", "Close sign-in")) { app.closeClaudeAuthentication() } }
            }
            if let error = app.claudeAccountError { Text(error).font(.caption).foregroundStyle(.orange) }
            if let error = account.error { Text(error).font(.caption).foregroundStyle(.secondary) }
        } header: { Text(L10n.pick("Аккаунт", "Account")) } footer: {
            Text(L10n.pick("Для работы по подписке войдите в аккаунт Claude с доступом к Claude Code (например, Pro или Max). Вход через Console использует отдельную оплату API. Пароль и токены обрабатывает Claude Code; PM не копирует их в диалоги или резервные копии.", "For subscription usage, sign in with a Claude account that includes Claude Code (such as Pro or Max). Console login uses separate API billing. Claude Code handles passwords and tokens; PM never copies them into chats or backups."))
                .font(.caption).foregroundStyle(.secondary)
        }
        .task { await app.refreshClaudeAccount() }
        Section {
            HStack {
                Text(L10n.pick("Лимиты подписки", "Subscription limits"))
                Spacer()
                Button(L10n.pick("Посмотреть лимиты", "View limits")) {
                    app.presentations.prepare("codexUsage", in: presentations ?? app.presentations)
                    app.openAccountUsage("claude")
                }
            }
        } header: { Text(L10n.pick("Использование", "Usage")) } footer: {
            Text(L10n.pick("После входа выберите Claude в меню модели любого чата.", "After signing in, choose Claude in any chat’s model menu."))
                .font(.caption).foregroundStyle(.secondary)
        }
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
        Text(L10n.pick("Доступность моделей и усилий определяет Claude Code для вашего аккаунта. Беседа продолжает свою сессию Claude вместе с историей инструментов и каждый раз получает выбранную память. Пока Claude работает, новое сообщение доходит до него как уточнение.", "Claude Code determines model and effort availability for your account. A conversation continues its Claude session with its tool history and receives selected memory every turn. While Claude works, a new message reaches it as an update."))
            .font(.caption).foregroundStyle(.secondary)
        }.task { await account.refresh(app: app) }
    }
}
