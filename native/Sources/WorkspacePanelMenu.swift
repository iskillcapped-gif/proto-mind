import SwiftUI

/// Submenus replace this list in place, so even narrow companion windows contain
/// the whole interaction instead of spawning another menu beside the window.
struct WorkspacePanelMenu: View {
    @ObservedObject var model: AppModel
    let panel: WorkspacePanelModel
    let activate: () -> Void
    let dismiss: () -> Void
    let chooseCLI: () -> Void
    @State private var page: Page = .root

    private enum Page { case root, conversations, messengers, cli }
    private var directory: URL { model.selected?.workspacePath.map { URL(fileURLWithPath: $0) } ?? FileManager.default.homeDirectoryForCurrentUser }
    private var title: String {
        switch page {
        case .root: return L10n.text("Добавить вкладку")
        case .conversations: return L10n.text("Открыть диалог")
        case .messengers: return L10n.pick("Мессенджеры", "Messengers")
        case .cli: return L10n.text("Другой CLI")
        }
    }
    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            if page != .root {
                ComposerMenuRow(title: L10n.text("Назад"), icon: "chevron.left") { page = .root }
                Text(title).font(.system(size: 11)).foregroundStyle(.secondary).padding(10)
            }
            switch page {
            case .root:
                row(L10n.text("Новый диалог PM"), "bubble.left.and.bubble.right") { model.newPanelConversation(in: panel) }
                branch(L10n.text("Открыть диалог"), icon: "clock", to: .conversations)
                row(L10n.text("Браузер / веб-приложение"), "globe") { panel.openBrowser() }
                branch(L10n.pick("Мессенджеры", "Messengers"), icon: "message", to: .messengers)
                row(L10n.text("Терминал"), "terminal") { panel.openTerminal(directory: directory) }
                branch(L10n.text("Другой CLI"), icon: "chevron.left.forwardslash.chevron.right", to: .cli)
                Divider().padding(.vertical, 4)
                row(L10n.text("Открыть файл…"), "doc") { model.chooseWorkspaceDocument(in: panel) }
                    .disabled(!model.canEditMessageAttachments)
                row(L10n.text("Файлы основного проекта"), "folder") { model.showProjectFiles(in: panel) }
            case .conversations:
                let chats = Array(model.listedConversations.filter { !$0.archived }.prefix(60))
                if chats.isEmpty {
                    Text(L10n.pick("Пока нет сохранённых чатов", "No saved chats yet")).font(.caption).foregroundStyle(.secondary).padding(10)
                }
                ForEach(chats) { conversation in
                    row(conversation.displayTitle, "bubble.left") { panel.open(.conversation(conversation.id)) }
                }
            case .messengers:
                ForEach(MessengerService.allCases) { service in
                    row(service.title, "message") { model.openMessenger(service, in: panel) }
                }
            case .cli:
                row("Claude Code", "terminal") {
                    if let path = TerminalLaunch.executable("claude") { panel.openTerminal(directory: directory, executable: path, arguments: []) }
                    else { panel.error = L10n.text("Claude Code не установлен. Установите CLI и войдите в свой аккаунт; затем откройте его здесь.") }
                }
                row(L10n.text("Выбрать исполняемый файл…"), "folder") { chooseCLI() }
            }
        }.padding(7)
    }

    private func row(_ title: String, _ icon: String, action: @escaping () -> Void) -> some View {
        ComposerMenuRow(title: title, icon: icon) {
            dismiss()
            Task { @MainActor in await Task.yield(); activate(); action() }
        }
    }
    private func branch(_ title: String, icon: String, to next: Page) -> some View {
        Button { page = next } label: {
            HStack(spacing: 10) {
                Image(systemName: icon).frame(width: 18)
                Text(title).lineLimit(2)
                Spacer(minLength: 6)
                Image(systemName: "chevron.right").font(.system(size: 9))
            }.font(.system(size: 13)).padding(.horizontal, 10).padding(.vertical, 8)
                .frame(maxWidth: .infinity, alignment: .leading).contentShape(Rectangle())
        }.buttonStyle(.nativeHover)
    }
}
