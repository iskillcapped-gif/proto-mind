import AppKit
import SwiftUI

struct TelegramRemoteSettings: View {
    @ObservedObject var app: AppModel
    @ObservedObject var remote: TelegramRemoteModel
    @State private var token = ""
    @State private var editingToken = false
    @State private var confirmDisconnect = false
    var body: some View {
        Section {
            if !remote.hasToken || editingToken {
                SecureField(L10n.pick("Токен Telegram-бота", "Telegram bot token"), text: $token, prompt: Text(L10n.pick("Токен от BotFather", "Token from BotFather")))
                    .textFieldStyle(.roundedBorder).labelsHidden()
                    .accessibilityLabel(L10n.pick("Токен Telegram-бота", "Telegram bot token"))
                HStack {
                    Button(L10n.pick("Открыть BotFather", "Open BotFather")) { NSWorkspace.shared.open(URL(string: "https://t.me/BotFather")!) }
                    Spacer()
                    if editingToken { Button(L10n.text("Отмена")) { token = ""; editingToken = false } }
                    Button(L10n.pick("Сохранить токен", "Save token")) {
                        do { try remote.saveToken(token); token = ""; editingToken = false }
                        catch { remote.error = error.localizedDescription }
                    }.buttonStyle(.borderedProminent).disabled(!TelegramKeychain.valid(token.trimmingCharacters(in: .whitespacesAndNewlines)))
                }
            } else {
                HStack(spacing: 10) {
                    VStack(alignment: .leading, spacing: 3) {
                        Text(remote.state.botName.isEmpty ? L10n.pick("Токен сохранён", "Token saved") : "@" + remote.state.botName)
                        Text(L10n.pick("Токен хранится в Связке ключей этого Mac", "The token is kept in this Mac's Keychain")).font(.caption).foregroundStyle(.secondary)
                    }
                    Spacer(minLength: 8)
                    SettingsMoreMenu { botActions }
                }.contextMenu { botActions }
            }
        } header: { Text(L10n.pick("Бот", "Bot")) } footer: {
            Text(!remote.hasToken || editingToken
                 ? L10n.pick("В BotFather создайте отдельного бота командой /newbot. Вставьте полученный токен — он сохранится в Связке ключей этого Mac.", "Create a separate bot with /newbot in BotFather. Paste its token; it will be stored in this Mac's Keychain.")
                 : L10n.pick("Отправляйте задачи и уточнения личному боту, получайте ответы и останавливайте работу с телефона. PM должен быть открыт, а Mac — бодрствовать.", "Send tasks and updates to your private bot, receive answers and stop work from your phone. PM must be open and your Mac awake."))
                .font(.caption).foregroundStyle(.secondary)
        }
        Section {
            Toggle(L10n.pick("Принимать команды с телефона", "Accept commands from your phone"), isOn: Binding(
                get: { remote.running || remote.connecting },
                set: { enabled in if enabled { Task { await remote.connect(app: app) } } else { remote.stop() } }))
                .disabled(!remote.hasToken || (!remote.running && (app.operationBusy || app.privateBackupRestartRequired)))
            Text(remote.connecting ? L10n.pick("Проверяем подключение…", "Checking connection…") :
                    remote.running ? (remote.state.peer == nil ? L10n.pick("Ожидаем подключение аккаунта", "Waiting for account pairing") : "@" + remote.state.botName) :
                    L10n.pick("Выключено. После запуска PM включите подключение здесь.", "Off. Enable this connection here after launching PM."))
                .font(.caption).foregroundStyle(.secondary)
            if let peer = remote.state.peer {
                HStack {
                    LabeledContent(L10n.pick("Подключённый аккаунт", "Paired account"), value: peer.name + " · " + String(peer.userID))
                    Button(L10n.pick("Отвязать аккаунт", "Unpair account")) {
                        do { try remote.unpair() } catch { remote.error = error.localizedDescription }
                    }
                }
            } else if remote.running {
                if let peer = remote.pendingPeer {
                    Text(L10n.pick("Запрос от: ", "Request from: ") + peer.name + " · " + String(peer.userID)).font(.headline)
                    HStack {
                        Spacer()
                        Button(L10n.pick("Отклонить и создать новую ссылку", "Reject and create a new link")) { remote.beginPairing() }
                        Button(L10n.pick("Разрешить доступ этому аккаунту", "Allow this account")) {
                            do { try remote.approvePeer() } catch { remote.error = error.localizedDescription }
                        }.buttonStyle(.borderedProminent)
                    }
                } else if let url = remote.pairingURL {
                    Text(L10n.pick("Откройте своего бота и нажмите Start. Затем подтвердите аккаунт здесь. Ссылка действует 10 минут.", "Open your bot and press Start. Then approve the account here. The link expires in 10 minutes."))
                        .font(.caption).foregroundStyle(.secondary)
                    HStack {
                        Spacer()
                        Button(L10n.pick("Обновить ссылку", "Refresh link")) { remote.beginPairing() }
                        Button(L10n.pick("Открыть моего бота", "Open my bot")) { NSWorkspace.shared.open(url) }.buttonStyle(.borderedProminent)
                    }
                }
            }
        } header: { Text(L10n.pick("Подключение", "Connection")) }
        Section {
            if remote.state.allowed.isEmpty {
                Text(L10n.pick("Пока нет задач.", "No tasks yet.")).foregroundStyle(.secondary)
            }
            ForEach(remote.state.allowed, id: \.self) { id in
                HStack {
                    Button {
                        do { try remote.select(id) } catch { remote.error = error.localizedDescription }
                    } label: {
                        Label(app.conversations.first { $0.id == id }?.displayTitle ?? L10n.pick("Чат недоступен", "Chat unavailable"),
                              systemImage: remote.state.selected == id ? "checkmark.circle.fill" : "circle")
                            .lineLimit(1)
                    }.buttonStyle(.plain)
                    Spacer()
                    Button(L10n.pick("Убрать доступ", "Remove access")) {
                        do { try remote.allow(id, enabled: false) } catch { remote.error = error.localizedDescription }
                    }
                }
            }
            HStack {
                Spacer()
                Menu(L10n.pick("Добавить задачу", "Share a task")) {
                    ForEach(app.listedConversations.filter { !$0.archived && !remote.state.allowed.contains($0.id) }) { chat in
                        Button(chat.displayTitle) {
                            do { try remote.allow(chat.id, enabled: true) } catch { remote.error = error.localizedDescription }
                        }
                    }
                }.menuStyle(.button).fixedSize().disabled(remote.state.allowed.count >= 64)
            }
        } header: { Text(L10n.pick("Доступные задачи", "Shared tasks")) } footer: {
            Text(L10n.pick("Подключённый аккаунт сможет читать ответы, отправлять текст и использовать уже выданные этим задачам права. Остальные чаты не доступны боту.", "The paired account can read replies, send text and use permissions already granted to these tasks. Other chats are not shared with the bot."))
                .font(.caption).foregroundStyle(.secondary)
        }
        Section {
            DisclosureGroup(L10n.pick("Команды бота", "Bot commands")) {
                Text(TelegramCommand.helpText).font(.caption).textSelection(.enabled)
            }
            if let error = remote.error { Text(error).font(.caption).foregroundStyle(.orange).textSelection(.enabled) }
        }.workspaceConfirmationDialog(L10n.pick("Отключить Telegram-бота?", "Disconnect the Telegram bot?"), isPresented: $confirmDisconnect, titleVisibility: .visible) {
            Button(L10n.pick("Отключить", "Disconnect"), role: .destructive) {
                confirmDisconnect = false
                do { try remote.removeToken() } catch { remote.error = error.localizedDescription }
            }
            Button(L10n.text("Отмена"), role: .cancel) { confirmDisconnect = false }
        } message: { Text(L10n.pick("Ключ и привязка аккаунта будут удалены с этого Mac. Принятые задачи продолжат работу в PM.", "The key and account pairing will be removed from this Mac. Accepted tasks continue in PM.")) }
    }

    @ViewBuilder private var botActions: some View {
        Button(L10n.pick("Заменить токен…", "Replace token…")) { editingToken = true }
        Divider()
        Button(L10n.pick("Отключить бота…", "Disconnect the bot…"), role: .destructive) { confirmDisconnect = true }
    }
}
