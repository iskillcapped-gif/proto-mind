import SwiftUI

struct ConversationAccountPicker: View {
    @ObservedObject var app: AppModel
    let conversationID: UUID
    var chosen: () -> Void = {}
    @Environment(\.workspacePresentations) private var presentations

    var body: some View {
        let current = app.codexAccount(for: conversationID)
        Menu {
            ForEach(app.codexAccounts.items) { connection in
                Button {
                    app.selectCodexAccount(connection.accountID, conversationID: conversationID)
                    chosen()
                } label: {
                    Label(connection.label, systemImage: current === connection ? "checkmark" : "person.crop.circle")
                }
            }
            Divider()
            Button(L10n.pick("Управлять аккаунтами…", "Manage accounts…")) {
                let destination = presentations
                chosen()
                app.presentations.prepare("codexAccounts", in: destination ?? app.presentations)
                app.codexAccountsConversationID = conversationID
                app.showCodexAccounts = true
            }
        } label: {
            HStack(spacing: 7) {
                Image(systemName: "person.crop.circle")
                VStack(alignment: .leading, spacing: 2) {
                    Text(current.name).lineLimit(1)
                    Text(current.account["email"].text.isEmpty ? L10n.pick("Аккаунт ChatGPT", "ChatGPT account") : current.account["email"].text)
                        .font(.system(size: 10)).foregroundStyle(.secondary).lineLimit(1)
                }
                Spacer(minLength: 4)
                Image(systemName: "chevron.up.chevron.down").font(.system(size: 8))
            }.font(.system(size: 12)).padding(8).contentShape(Rectangle())
        }.menuStyle(.borderlessButton).menuIndicator(.hidden)
            .disabled(app.operationBusy || app.isRunning(conversationID))
            .accessibilityLabel(L10n.pick("Аккаунт этого чата", "Account for this chat"))
            .help(current.label)
            .task(id: current.id) {
                if app.cloudConsent && current.account.isNull { await app.refreshAccount(current) }
            }
    }
}

struct CodexAccountsPage: View {
    @ObservedObject var app: AppModel
    let conversationID: UUID?
    @WorkspaceDismiss private var dismiss
    var body: some View {
        VStack(spacing: 0) {
            HStack {
                Text(L10n.pick("Аккаунты ChatGPT", "ChatGPT accounts")).font(.system(size: 21, weight: .semibold))
                Spacer()
                Button { dismiss() } label: { Image(systemName: "xmark") }.keyboardShortcut(.cancelAction)
            }.padding(22)
            Form { CodexAccountSettings(app: app, accounts: app.codexAccounts, conversationID: conversationID) }
                .formStyle(.grouped).scrollContentBackground(.hidden)
        }.workspacePageSize(width: 620, height: 650)
    }
}

struct CodexAccountSettings: View {
    @ObservedObject var app: AppModel
    @ObservedObject var accounts: CodexAccounts
    let conversationID: UUID?
    @State private var adding = false
    @State private var name = ""
    @State private var error: String?
    var body: some View {
        Section(L10n.pick("Аккаунты ChatGPT", "ChatGPT accounts")) {
            if let id = conversationID {
                ConversationAccountPicker(app: app, conversationID: id)
            }
            Text(L10n.pick("Для каждого чата можно выбрать свою подписку. Входы, модели и лимиты разделены; история чатов и память Proto-Mind остаются в этом приложении.", "Choose a subscription for each chat. Sign-ins, models and limits are separate; chat history and Proto-Mind memory remain in this app."))
                .font(.callout).foregroundStyle(.secondary)
            ForEach(accounts.items) { connection in
                CodexAccountSettingsRow(app: app, connection: connection, conversationID: conversationID)
            }
            if adding {
                TextField(L10n.pick("Название аккаунта", "Account name"), text: $name,
                    prompt: Text(L10n.pick("Например, Личный", "For example, Personal")))
                HStack {
                    Button(L10n.text("Отмена")) { adding = false; error = nil }
                    Spacer()
                    Button(L10n.pick("Добавить", "Add")) {
                        do { _ = try accounts.create(name: name); name = ""; adding = false; error = nil }
                        catch { self.error = error.localizedDescription }
                    }.disabled(app.operationBusy || app.privateBackupRestartRequired)
                }
            } else {
                Button(L10n.pick("Добавить аккаунт ChatGPT", "Add ChatGPT account"), systemImage: "person.crop.circle.badge.plus") {
                    adding = true; name = ""; error = nil
                }.disabled(app.operationBusy || app.privateBackupRestartRequired || accounts.items.count >= 20)
            }
            if let error { Text(error).font(.caption).foregroundStyle(.orange) }
            Toggle(L10n.text("Разрешить облачную обработку"), isOn: $app.cloudConsent).disabled(app.globalBusy)
            Text(L10n.pick("При входе выберите нужный логин на странице ChatGPT. Подключение сохраняется после перезапуска. При смене аккаунта чата модель и доступ к Mac выбираются заново; новая сессия получает последние сообщения этого чата. Аккаунт выполняющейся задачи менять нельзя.", "Choose the intended login on the ChatGPT sign-in page. Sign-ins survive restart. Changing a chat's account clears its model and Mac access; a new session receives the chat's recent messages. An active task's account cannot be changed."))
                .font(.caption).foregroundStyle(.secondary)
        }
    }
}

private struct CodexAccountSettingsRow: View {
    @ObservedObject var app: AppModel
    @ObservedObject var connection: CodexAccountConnection
    let conversationID: UUID?
    @Environment(\.workspacePresentations) private var presentations
    @State private var renaming = false
    @State private var name = ""
    @State private var error: String?
    private var selected: Bool { conversationID.map { app.codexAccount(for: $0) === connection } == true }
    private var anotherLogin: Bool { app.codexAccounts.items.contains { $0 !== connection && ($0.loginPending || $0.connecting) } }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Image(systemName: selected ? "checkmark.circle.fill" : "person.crop.circle").foregroundStyle(.secondary)
                Text(connection.name).font(.system(size: 14, weight: .medium))
                Spacer()
                if connection.connecting { ProgressView().controlSize(.small) }
                Button { name = connection.name; renaming.toggle() } label: { Image(systemName: "pencil") }
                    .help(L10n.pick("Переименовать аккаунт", "Rename account"))
            }
            if renaming {
                HStack {
                    TextField(L10n.pick("Название аккаунта", "Account name"), text: $name)
                    Button(L10n.text("Сохранить")) {
                        do { try app.codexAccounts.rename(connection, to: name); renaming = false; error = nil }
                        catch { self.error = error.localizedDescription }
                    }
                }
            }
            Text(connection.account.isNull ? L10n.pick("Вход ещё не проверен", "Sign-in not checked") :
                 connection.account["connected"].flag ? connection.account["email"].text + " · " + connection.account["plan"].text : L10n.pick("Не подключено", "Not connected"))
                .font(.caption).foregroundStyle(.secondary).textSelection(.enabled)
            HStack(spacing: 12) {
                if !connection.account["connected"].flag && !connection.loginPending {
                    Button(L10n.pick("Войти…", "Sign in…")) { Task { await app.login(connection) } }
                        .disabled(!app.accountCanAuthenticate(connection) || anotherLogin)
                }
                Button(L10n.text("Проверить вход")) { Task { await app.refreshAccount(connection) } }
                    .disabled(connection.connecting || app.operationBusy || app.privateBackupRestartRequired)
                Button(L10n.text("Лимиты")) {
                    app.presentations.prepare("codexUsage", in: presentations ?? app.presentations)
                    app.openCodexUsage(connection)
                }.disabled(connection.loginPending)
                Spacer(minLength: 0)
                if connection.account["connected"].flag {
                    Button(L10n.text("Выйти")) { Task { await app.logout(connection) } }
                        .disabled(!app.accountCanAuthenticate(connection))
                }
            }.font(.caption)
            if connection.loginPending {
                Text(L10n.text("Завершите вход в браузере и нажмите «Проверить вход»."))
                    .font(.caption).foregroundStyle(.secondary)
                Button(L10n.pick("Отменить вход", "Cancel sign-in")) { Task { await app.cancelAccountLogin(connection) } }
                    .font(.caption).disabled(connection.connecting)
            }
            if let id = conversationID, !selected {
                Button(L10n.pick("Использовать в этом чате", "Use in this chat")) {
                    app.selectCodexAccount(connection.accountID, conversationID: id)
                }.disabled(app.operationBusy || app.isRunning(id))
            }
            if app.accountHasRunningTasks(connection.accountID) {
                Text(L10n.pick("Аккаунт выполняет задачи", "This account is running tasks")).font(.caption).foregroundStyle(.secondary)
            }
            if let error = connection.error ?? error { Text(error).font(.caption).foregroundStyle(.orange) }
        }.padding(.vertical, 7)
    }
}
