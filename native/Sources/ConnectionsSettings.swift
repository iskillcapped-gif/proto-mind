import SwiftUI

/// A service PM connects to. Settings → Connections lists them by purpose with their state; each
/// opens its own page.
enum ConnectionKind: String, CaseIterable, Identifiable {
    case claude, api, mcp, github, iphone, telegramBot, messengers
    var id: String { rawValue }

    var title: String {
        switch self {
        case .claude: return "Claude · Claude Code"
        case .api: return L10n.pick("Модели через API", "Models via API")
        case .mcp: return L10n.pick("MCP-сервисы", "MCP services")
        case .github: return "GitHub"
        case .iphone: return "iPhone · PM Remote"
        case .telegramBot: return L10n.pick("Telegram-бот", "Telegram bot")
        case .messengers: return L10n.pick("Мессенджеры", "Messengers")
        }
    }

    var summary: String {
        switch self {
        case .claude: return L10n.pick("Подписка Claude через официальный Claude Code.", "Your Claude subscription through official Claude Code.")
        case .api: return L10n.pick("OpenAI и совместимые серверы по вашим ключам.", "OpenAI and compatible servers with your keys.")
        case .mcp: return L10n.pick("Инструменты ваших сервисов для задач PM.", "Your services' tools for PM tasks.")
        case .github: return L10n.pick("Репозитории, pull requests и задачи через GitHub CLI.", "Repositories, pull requests and issues through GitHub CLI.")
        case .iphone: return L10n.pick("Проекты и чаты PM с вашего iPhone.", "PM projects and chats on your iPhone.")
        case .telegramBot: return L10n.pick("Задачи и ответы через личного бота.", "Tasks and replies through your private bot.")
        case .messengers: return L10n.pick("Telegram и WhatsApp в панели рядом с задачей.", "Telegram and WhatsApp in a panel beside your work.")
        }
    }

    var symbol: String {
        switch self {
        case .claude: return "sparkle"
        case .api: return "server.rack"
        case .mcp: return "puzzlepiece.extension.fill"
        case .github: return "chevron.left.forwardslash.chevron.right"
        case .iphone: return "iphone"
        case .telegramBot: return "paperplane.fill"
        case .messengers: return "bubble.left.and.bubble.right.fill"
        }
    }

    var tint: Color {
        switch self {
        case .claude: return Color(red: 0.84, green: 0.46, blue: 0.33)
        case .api: return .indigo
        case .mcp: return .teal
        case .github: return Color(white: 0.3)
        case .iphone: return .blue
        case .telegramBot: return Color(red: 0.16, green: 0.62, blue: 0.9)
        case .messengers: return .green
        }
    }
}

/// Connections by what they are for.
enum ConnectionGroup: CaseIterable, Identifiable {
    case models, tools, phone, chat
    var id: Self { self }
    var title: String {
        switch self {
        case .models: return L10n.pick("Модели", "Models")
        case .tools: return L10n.pick("Инструменты задач", "Task tools")
        case .phone: return L10n.pick("Управление с телефона", "Control from your phone")
        case .chat: return L10n.pick("Переписка", "Chats")
        }
    }
    var kinds: [ConnectionKind] {
        switch self {
        case .models: return [.claude, .api]
        case .tools: return [.mcp, .github]
        case .phone: return [.iphone, .telegramBot]
        case .chat: return [.messengers]
        }
    }
}

/// A connection's state in a few words, and whether it works, needs the operator or is off.
struct ConnectionState: Equatable {
    enum Tone { case on, attention, off }
    let text: String
    let tone: Tone
    let detail: String
}

/// The rounded, tinted symbol that stands for a connection.
struct ConnectionIcon: View {
    let kind: ConnectionKind
    var size: CGFloat = 28

    var body: some View {
        RoundedRectangle(cornerRadius: size * 0.26, style: .continuous).fill(kind.tint.gradient)
            .frame(width: size, height: size)
            .overlay(Image(systemName: kind.symbol).font(.system(size: size * 0.46, weight: .semibold)).foregroundStyle(.white))
            .accessibilityHidden(true)
    }
}

struct ConnectionBadge: View {
    let state: ConnectionState

    private var color: Color {
        switch state.tone { case .on: return .green; case .attention: return .orange; case .off: return .secondary }
    }

    var body: some View {
        HStack(spacing: 5) {
            Circle().fill(color).frame(width: 6, height: 6)
            Text(state.text).lineLimit(1)
        }
        .font(.system(size: 11, weight: .medium)).foregroundStyle(state.tone == .off ? .secondary : .primary)
        .padding(.horizontal, 8).padding(.vertical, 3)
        .background(color.opacity(state.tone == .off ? 0.1 : 0.16), in: Capsule())
    }
}

/// Settings → Connections: every connection by purpose, with its state. A row opens its page.
struct ConnectionsOverview: View {
    @ObservedObject var app: AppModel

    var body: some View {
        ForEach(ConnectionGroup.allCases) { group in
            Section(group.title) {
                ForEach(group.kinds) { kind in
                    Button { app.settingsConnection = kind } label: { ConnectionStatusRow(app: app, kind: kind) }
                        .buttonStyle(.plain)
                        .accessibilityHint(L10n.pick("Открыть настройки подключения", "Open connection settings"))
                }
            }
        }
        // At most once a minute: Claude's account check starts a Claude Code worker.
        .task { await app.claudeAccount.refresh(app: app) }
        .task { await app.github.refresh(app: app) }
    }
}

/// A connection's own page: its settings, below the header with the way back.
struct ConnectionDetailSections: View {
    @ObservedObject var app: AppModel
    let kind: ConnectionKind

    var body: some View {
        // Actions read as buttons here, not as rows of text.
        Group { pages }.buttonStyle(.bordered)
    }

    @ViewBuilder private var pages: some View {
        switch kind {
        case .claude: ClaudeConnectionSettings(app: app)
        case .api: ModelAPIConnectionSettings(app: app, connections: app.apiConnections)
        case .mcp: WorkspaceServiceSettings(app: app, services: app.workspaceServices)
        case .github: GitHubConnectionSettings(app: app, github: app.github)
        case .iphone: MobileRemoteSettings(app: app, remote: app.mobile)
        case .telegramBot: TelegramRemoteSettings(app: app, remote: app.telegram)
        case .messengers: MessengerSettings(app: app, connections: app.messengers)
        }
    }
}

/// The page title of an open connection, with the way back to the list.
struct ConnectionHeader: View {
    @ObservedObject var app: AppModel
    let kind: ConnectionKind

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Button { app.settingsConnection = nil } label: {
                Label(L10n.pick("Подключения", "Connections"), systemImage: "chevron.left").font(.system(size: 12, weight: .medium))
            }.buttonStyle(.plain).foregroundStyle(NativeTheme.accent).keyboardShortcut("[", modifiers: .command)
                .help(L10n.pick("Назад к списку подключений (⌘[)", "Back to all connections (⌘[)"))
            HStack(spacing: 12) {
                ConnectionIcon(kind: kind, size: 38)
                VStack(alignment: .leading, spacing: 3) {
                    HStack(spacing: 10) {
                        Text(kind.title).font(.system(size: 21, weight: .semibold)).lineLimit(1)
                        ConnectionStatusBadge(app: app, kind: kind)
                    }
                    Text(kind.summary).font(.system(size: 13)).foregroundStyle(.secondary)
                }
            }
        }
    }
}

/// One overview row: symbol, name, what is connected and its state.
private struct ConnectionStatusRow: View {
    @ObservedObject var app: AppModel
    let kind: ConnectionKind

    var body: some View {
        ConnectionStateReader(app: app, kind: kind) { state in
            HStack(spacing: 11) {
                ConnectionIcon(kind: kind)
                VStack(alignment: .leading, spacing: 2) {
                    Text(kind.title).font(.system(size: 13, weight: .medium)).lineLimit(1)
                    Text(state.detail).font(.system(size: 11)).foregroundStyle(.secondary).lineLimit(1)
                }
                Spacer(minLength: 8)
                if !state.text.isEmpty { ConnectionBadge(state: state) }
                Image(systemName: "chevron.right").font(.system(size: 11, weight: .semibold)).foregroundStyle(.tertiary)
            }.padding(.vertical, 3).contentShape(Rectangle())
        }
    }
}

private struct ConnectionStatusBadge: View {
    @ObservedObject var app: AppModel
    let kind: ConnectionKind

    var body: some View {
        ConnectionStateReader(app: app, kind: kind) { state in
            if !state.text.isEmpty { ConnectionBadge(state: state) }
        }
    }
}

/// Reads a connection's state from its own model, so a row redraws only when that model changes.
private struct ConnectionStateReader<Content: View>: View {
    @ObservedObject var app: AppModel
    let kind: ConnectionKind
    @ViewBuilder let content: (ConnectionState) -> Content

    var body: some View {
        switch kind {
        case .claude: ClaudeConnectionState(account: app.claudeAccount, content: content)
        case .api: ModelsConnectionState(connections: app.apiConnections, content: content)
        case .mcp: ServicesConnectionState(services: app.workspaceServices, content: content)
        case .github: GitHubConnectionState(github: app.github, content: content)
        case .iphone: MobileConnectionState(remote: app.mobile, content: content)
        case .telegramBot: TelegramConnectionState(remote: app.telegram, content: content)
        case .messengers:
            content(ConnectionState(text: "", tone: .off, detail: MessengerService.allCases.map(\.title).joined(separator: " · ")))
        }
    }
}

private func names(_ values: [String]) -> String {
    values.count <= 2 ? values.joined(separator: ", ") : values.prefix(2).joined(separator: ", ") + " +\(values.count - 2)"
}

private struct ClaudeConnectionState<Content: View>: View {
    @ObservedObject var account: ClaudeAccountModel
    let content: (ConnectionState) -> Content
    var body: some View {
        if let snapshot = account.snapshot, snapshot.connected {
            content(ConnectionState(text: L10n.pick("Подключено", "Connected"), tone: .on,
                                    detail: [snapshot.email, snapshot.plan.capitalized].filter { !$0.isEmpty }.joined(separator: " · ")))
        } else if account.snapshot != nil {
            content(ConnectionState(text: L10n.pick("Нужен вход", "Sign in"), tone: .attention, detail: L10n.pick("Войдите через Claude Code", "Sign in through Claude Code")))
        } else {
            content(ConnectionState(text: account.refreshing ? L10n.pick("Проверяем…", "Checking…") : L10n.pick("Не проверено", "Not checked"), tone: .off,
                                    detail: L10n.pick("Вход через Claude Code", "Sign in through Claude Code")))
        }
    }
}

private struct ModelsConnectionState<Content: View>: View {
    @ObservedObject var connections: ModelAPIConnections
    let content: (ConnectionState) -> Content
    var body: some View {
        content(connections.items.isEmpty
            ? ConnectionState(text: L10n.pick("Не настроено", "Not set up"), tone: .off, detail: L10n.pick("Свои ключи OpenAI или локальный сервер", "Your OpenAI keys or a local server"))
            : ConnectionState(text: L10n.pick("Подключено", "Connected"), tone: .on, detail: names(connections.items.map(\.name))))
    }
}

private struct ServicesConnectionState<Content: View>: View {
    @ObservedObject var services: WorkspaceServices
    let content: (ConnectionState) -> Content
    var body: some View {
        let enabled = services.items.filter(\.enabled)
        content(services.items.isEmpty
            ? ConnectionState(text: L10n.pick("Не настроено", "Not set up"), tone: .off, detail: L10n.pick("Streamable HTTP или локальная программа", "Streamable HTTP or a local program"))
            : ConnectionState(text: enabled.isEmpty ? L10n.pick("Выключено", "Off") : L10n.pick("Включено", "On"), tone: enabled.isEmpty ? .off : .on,
                              detail: names(services.items.map(\.name))))
    }
}

private struct GitHubConnectionState<Content: View>: View {
    @ObservedObject var github: GitHubModel
    let content: (ConnectionState) -> Content
    var body: some View {
        content(github.connected
            ? ConnectionState(text: L10n.pick("Подключено", "Connected"), tone: .on, detail: "@" + github.status["login"].text)
            : ConnectionState(text: L10n.pick("Не подключено", "Not connected"), tone: .off,
                              detail: github.status["available_login"].text.isEmpty ? L10n.pick("Вход через GitHub CLI", "Sign in through GitHub CLI")
                                  : L10n.pick("Можно подключить @", "Ready to connect @") + github.status["available_login"].text))
    }
}

private struct MobileConnectionState<Content: View>: View {
    @ObservedObject var remote: MobileRemoteModel
    let content: (ConnectionState) -> Content
    var body: some View {
        let devices = names(remote.state.devices.map(\.name))
        if let pending = remote.pending {
            content(ConnectionState(text: L10n.pick("Ждёт подтверждения", "Needs approval"), tone: .attention, detail: pending.name))
        } else if remote.running || remote.connecting {
            content(ConnectionState(text: L10n.pick("Включено", "On"), tone: .on,
                                    detail: devices.isEmpty ? L10n.pick("Подключите iPhone по QR-коду", "Pair an iPhone with the QR code") : devices))
        } else if remote.state.endpoint.isEmpty {
            content(ConnectionState(text: L10n.pick("Не настроено", "Not set up"), tone: .off, detail: L10n.pick("Нужен частный адрес Mac через Tailscale", "Needs a private Mac address through Tailscale")))
        } else {
            content(ConnectionState(text: L10n.pick("Выключено", "Off"), tone: .off, detail: devices.isEmpty ? remote.state.endpoint : devices))
        }
    }
}

private struct TelegramConnectionState<Content: View>: View {
    @ObservedObject var remote: TelegramRemoteModel
    let content: (ConnectionState) -> Content
    var body: some View {
        let bot = remote.state.botName.isEmpty ? L10n.pick("Токен сохранён", "Token saved") : "@" + remote.state.botName
        if !remote.hasToken {
            content(ConnectionState(text: L10n.pick("Не настроено", "Not set up"), tone: .off, detail: L10n.pick("Нужен бот из BotFather", "Needs a bot from BotFather")))
        } else if let pending = remote.pendingPeer {
            content(ConnectionState(text: L10n.pick("Ждёт подтверждения", "Needs approval"), tone: .attention, detail: pending.name))
        } else if remote.running || remote.connecting {
            content(remote.state.peer.map { ConnectionState(text: L10n.pick("Включено", "On"), tone: .on, detail: bot + " · " + $0.name) }
                    ?? ConnectionState(text: L10n.pick("Ждёт аккаунт", "Awaiting account"), tone: .attention, detail: bot))
        } else {
            content(ConnectionState(text: L10n.pick("Выключено", "Off"), tone: .off, detail: bot))
        }
    }
}
