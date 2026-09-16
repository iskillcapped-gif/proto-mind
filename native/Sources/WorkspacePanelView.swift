import AppKit
import SwiftUI

struct WorkspacePanelControls {
    let title: String
    let activate: () -> Void
    let expand: () -> Void
}

struct WorkspacePanelView: View {
    @ObservedObject var model: AppModel
    @ObservedObject var panel: WorkspacePanelModel
    @Environment(\.desktopGlass) private var desktopGlass
    var width: CGFloat = 0
    var position: WorkspacePanelPosition = .upper
    var controls: WorkspacePanelControls? = nil
    @State private var hovered = false
    @State private var terminalToClose: UUID?
    @State private var confirmTerminalClose = false

    var body: some View {
        VStack(spacing: 0) {
            HStack(spacing: 5) {
                if panel.tabs.isEmpty {
                    Text(controls?.title ?? position.title).font(.system(size: 11, weight: .medium)).foregroundStyle(.secondary)
                        .padding(.leading, 5)
                }
                ScrollViewReader { proxy in
                    ScrollView(.horizontal, showsIndicators: false) {
                        HStack(spacing: 4) {
                            ForEach(panel.tabs) { tab in
                                HStack(spacing: 6) {
                                    Button { activate(); panel.selectedID = tab.id } label: {
                                        HStack(spacing: 6) {
                                            Image(systemName: tab.symbol)
                                            if case .browser(let browser) = tab.content {
                                                BrowserTabTitle(browser: browser, titleChanged: {})
                                            } else { Text(title(tab)).lineLimit(1) }
                                        }.frame(maxWidth: 170)
                                    }
                                    Button { close(tab) } label: { Image(systemName: "xmark").font(.system(size: 9)) }
                                        .help("Закрыть вкладку").accessibilityLabel("Закрыть вкладку \(title(tab))")
                                }.font(.system(size: 11)).padding(8)
                                    .background(panel.selectedID == tab.id ? NativeTheme.composer : .clear, in: RoundedRectangle(cornerRadius: 8))
                                    .id(tab.id)
                            }
                        }
                    }.onChange(of: panel.selectedID) { _, id in
                        if let id { Task { @MainActor in await Task.yield(); proxy.scrollTo(id, anchor: .trailing) } }
                    }
                }
                Menu { actions } label: { Image(systemName: "plus").frame(width: 26, height: 28) }
                    .menuStyle(.borderlessButton).menuIndicator(.hidden).fixedSize()
                    .help("Добавить вкладку").accessibilityLabel("Добавить вкладку · " + (controls?.title ?? position.title))
            }.padding(.horizontal, 9).frame(height: 40).workspacePanelHeader()
            Divider().opacity(0.5).workspacePanelHeader()
            if let error = panel.error {
                HStack(alignment: .top) {
                    Text(error).font(.system(size: 12)).textSelection(.enabled)
                    Spacer()
                    Button { panel.error = nil } label: { Image(systemName: "xmark") }
                }.foregroundStyle(.orange).padding(12)
            }
            ZStack {
                if panel.selectedID == nil {
                    if panel.filesSelected { ProjectWorkspaceView(model: model, panel: panel) }
                    else { welcome }
                }
                ForEach(panel.tabs) { tab in
                    tabContent(tab)
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                        .opacity(panel.selectedID == tab.id ? 1 : 0)
                        .allowsHitTesting(panel.selectedID == tab.id).disabled(panel.selectedID != tab.id)
                        .accessibilityHidden(panel.selectedID != tab.id)
                }
            }.frame(maxWidth: .infinity, maxHeight: .infinity)
        }
        .background(desktopGlass ? (controls == nil ? NativeTheme.canvas.opacity(0.12) : Color.clear) : NativeTheme.canvas)
        .overlay(alignment: position == .upper ? .bottomLeading : .topLeading) {
            if controls == nil {
            Button { model.workspacePanels.toggleExpansion(position) } label: {
                Image(systemName: "triangle.fill")
                    .font(.system(size: 12)).rotationEffect(.degrees(position == .upper ? (panel.expanded ? 45 : -135) : (panel.expanded ? 135 : -45)))
                    .foregroundStyle(.primary.opacity(0.75)).frame(width: 27, height: 27)
                    .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 8))
            }.buttonStyle(.plain).padding(4).opacity(hovered ? 1 : 0).allowsHitTesting(hovered)
                .help(panel.expanded ? "Вернуть две панели" : "Развернуть до боковой колонки")
                .accessibilityLabel((panel.expanded ? "Свернуть · " : "Развернуть · ") + position.title)
                .accessibilityHidden(!hovered)
            }
        }.onHover { hovered = $0 }
        .workspaceConfirmationDialog("Закрыть терминал?", isPresented: $confirmTerminalClose, titleVisibility: .visible) {
            Button("Закрыть терминал", role: .destructive) { confirmTerminalClose = false; if let id = terminalToClose { panel.close(id) }; terminalToClose = nil }
            Button("Отмена", role: .cancel) { confirmTerminalClose = false; terminalToClose = nil }
        } message: { Text("Это завершит терминальный сеанс этой вкладки. Задачи в диалогах PM продолжат работу.") }
    }

    private func activate() {
        if let controls { controls.activate() } else { model.workspacePanels.active = position }
    }
    private var directory: URL { model.selected?.workspacePath.map { URL(fileURLWithPath: $0) } ?? FileManager.default.homeDirectoryForCurrentUser }

    @ViewBuilder private var actions: some View {
        Button("Новый диалог PM", systemImage: "bubble.left.and.bubble.right") { activate(); model.newPanelConversation(in: panel) }
        Menu("Открыть диалог") {
            ForEach(model.listedConversations.filter { !$0.archived }.prefix(60)) { conversation in
                Button(conversation.title) { activate(); panel.open(.conversation(conversation.id)) }
            }
        }
        Button("Браузер / веб-приложение", systemImage: "globe") { activate(); panel.openBrowser() }
        Button("Терминал", systemImage: "terminal") { activate(); panel.openTerminal(directory: directory) }
        Menu("Другой CLI") {
            Button("Claude Code") {
                activate()
                if let path = TerminalLaunch.executable("claude") { panel.openTerminal(directory: directory, executable: path, arguments: []) }
                else { panel.error = "Claude Code не установлен. Установите CLI и войдите в свой аккаунт; затем откройте его здесь." }
            }
            Button("Выбрать исполняемый файл…") { chooseCLI() }
        }
        Divider()
        Button("Открыть файл…", systemImage: "doc") { activate(); model.chooseWorkspaceDocument(in: panel) }.disabled(!model.canEditMessageAttachments)
        Button("Файлы основного проекта", systemImage: "folder") { activate(); model.showProjectFiles(in: panel) }
        Divider()
        Button(panel.expanded ? "Вернуть размер" : "Развернуть панель", systemImage: "arrow.up.left.and.arrow.down.right") {
            if let controls { controls.expand() } else { model.workspacePanels.toggleExpansion(position) }
        }
    }

    private var welcome: some View {
        ViewThatFits {
            VStack(alignment: .leading, spacing: 12) {
                Text("Откройте рядом").font(.system(size: 18, weight: .medium))
                Text("Диалог, страницу или инструменты для работы.").font(.system(size: 12)).foregroundStyle(.secondary)
                HStack(spacing: 8) {
                    launcher("Диалог PM", icon: "bubble.left.and.bubble.right") { model.newPanelConversation(in: panel) }
                    launcher("Браузер", icon: "globe") { panel.openBrowser() }
                    launcher("Терминал", icon: "terminal") { panel.openTerminal(directory: directory) }
                }.padding(.top, 5)
            }.padding(24)
            VStack(spacing: 10) {
                launcher("Диалог PM", icon: "bubble.left.and.bubble.right") { model.newPanelConversation(in: panel) }
                HStack {
                    launcher("Браузер", icon: "globe") { panel.openBrowser() }
                    launcher("Терминал", icon: "terminal") { panel.openTerminal(directory: directory) }
                }
            }.padding(16)
        }.frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    private func launcher(_ title: String, icon: String, action: @escaping () -> Void) -> some View {
        Button { activate(); action() } label: {
            VStack(spacing: 9) {
                Image(systemName: icon).font(.system(size: 19, weight: .light))
                Text(title).font(.system(size: 11))
            }.padding(14).frame(minWidth: 65).background(NativeTheme.composer.opacity(0.75), in: RoundedRectangle(cornerRadius: 12))
        }.buttonStyle(.nativeHover)
    }

    @ViewBuilder private func tabContent(_ tab: WorkspacePanelTab) -> some View {
        switch tab.content {
        case .text(let file): WorkspaceTextView(model: model, panel: panel, file: file)
        case .image(let image): WorkspaceImageView(model: model, panel: panel, preview: image)
        case .pdf(let pdf): WorkspacePDFView(model: model, panel: panel, preview: pdf, tabID: tab.id)
        case .browser(let browser): BrowserView(browser: browser)
        case .conversation(let id): ConversationPaneView(app: model, conversationID: id, panel: panel)
        case .terminal(let terminal): WorkspaceTerminalView(terminal: terminal)
        }
    }

    private func title(_ tab: WorkspacePanelTab) -> String {
        if case .conversation(let id) = tab.content { return model.conversations.first { $0.id == id }?.title ?? "Диалог" }
        return tab.title
    }
    private func close(_ tab: WorkspacePanelTab) {
        if case .terminal(let terminal) = tab.content, terminal.running { terminalToClose = tab.id; confirmTerminalClose = true }
        else { panel.close(tab.id) }
    }
    private func chooseCLI() {
        activate()
        let picker = NSOpenPanel()
        picker.canChooseDirectories = false; picker.allowsMultipleSelection = false; picker.prompt = "Запустить CLI"
        model.presentFilePicker(picker, in: panel.presentations) { result in
            if result == .OK, let url = picker.url { panel.openTerminal(directory: directory, executable: url.path, arguments: []) }
        }
    }
}

private struct BrowserTabTitle: View {
    @ObservedObject var browser: NativeBrowserTab
    var titleChanged: () -> Void
    var body: some View {
        Text(browser.title).lineLimit(1).help(browser.currentURL?.absoluteString ?? "Новая страница")
            .onChange(of: browser.title) { _, _ in titleChanged() }
    }
}

private struct WorkspaceTextView: View {
    @ObservedObject var model: AppModel
    let panel: WorkspacePanelModel
    let file: WorkspaceTextPreview
    @State private var showSource = false
    private var markdown: Bool { ["md", "markdown"].contains(file.url.pathExtension.lowercased()) }
    private var canAttach: Bool { model.canEditMessageAttachments && model.selectedID == file.conversationID && model.selected?.workspacePath == file.root && model.selected?.archived != true }

    var body: some View {
        VStack(spacing: 0) {
            HStack(spacing: 10) {
                Text(file.path).font(.system(size: 12)).lineLimit(1).truncationMode(.middle).help(file.url.path)
                Spacer(minLength: 0)
                if markdown {
                    Button(showSource ? "Просмотр" : "Исходник") { showSource.toggle() }.font(.caption)
                }
                Button { Task { await model.openWorkspaceEntry(.object(["path": .string(file.path), "directory": .bool(false)]), in: panel) } } label: {
                    Image(systemName: "arrow.clockwise")
                }.disabled(!canAttach || model.loadingWorkspace).help("Обновить файл").accessibilityLabel("Обновить файл")
                Button { model.attachWorkspaceText(file, in: panel) } label: { Image(systemName: "paperclip") }
                    .disabled(!canAttach).help("Прикрепить к сообщению").accessibilityLabel("Прикрепить файл к сообщению")
                documentMenu(file.url, text: true)
            }.padding(14).workspacePanelHeader()
            Divider().workspacePanelHeader()
            if markdown && !showSource {
                ScrollView {
                    MessageMarkdownView(text: file.value["preview"].text, copy: model.copy, openLink: {
                        if NativeBrowserURL.isWebURL($0) { panel.openBrowser($0) }
                        else {
                            let target = $0.isFileURL || $0.path.hasPrefix("/") ? $0 : file.url.deletingLastPathComponent().appendingPathComponent($0.path)
                            model.openPanelFile(target, conversationID: file.conversationID, panel: panel)
                        }
                    }).padding(24).frame(maxWidth: .infinity, alignment: .leading)
                }
            } else {
                ScrollView([.vertical, .horizontal]) {
                    Text(file.value["preview"].text).font(NativeTheme.codeFont).textSelection(.enabled)
                        .padding(20).frame(maxWidth: .infinity, alignment: .topLeading)
                }
            }
            if file.value["truncated"].flag {
                Text("Показаны первые 12 000 символов. Полный файл доступен через «Открыть».")
                    .font(.caption).foregroundStyle(.secondary).padding(10)
            }
            if model.selectedID != file.conversationID || model.selected?.workspacePath != file.root {
                Text("Файл открыт из другого диалога или папки.").font(.caption).foregroundStyle(.secondary).padding(10)
            }
        }.id(file.url.path)
    }
}

private struct WorkspaceImageView: View {
    @ObservedObject var model: AppModel
    let panel: WorkspacePanelModel
    let preview: NativeImagePreview
    var body: some View {
        VStack(spacing: 0) {
            HStack {
                Text(preview.source.name).font(.callout).lineLimit(1)
                Spacer()
                if preview.canAttach {
                    Button {
                        do { try model.attachImage(preview) } catch { panel.error = error.localizedDescription }
                    } label: { Image(systemName: "paperclip") }
                        .disabled(!model.canEditMessageAttachments || model.selectedID != preview.conversationID || model.selected?.archived == true)
                        .help("Прикрепить к сообщению").accessibilityLabel("Прикрепить изображение к сообщению")
                }
                documentMenu(URL(fileURLWithPath: preview.source.path))
            }.padding(14).workspacePanelHeader()
            Divider().workspacePanelHeader()
            Image(nsImage: preview.thumbnail).resizable().scaledToFit().padding(20)
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .accessibilityLabel("Изображение \(preview.source.name)")
            Text("\(preview.source.value["width"].integer) × \(preview.source.value["height"].integer)")
                .font(.caption).foregroundStyle(.secondary).padding(10)
        }
    }
}

private struct WorkspacePDFView: View {
    @ObservedObject var model: AppModel
    let panel: WorkspacePanelModel
    let preview: NativePDFPreview
    let tabID: UUID
    private var page: Int { preview.source.pages.first ?? 1 }
    private var total: Int { preview.source.value["page_count"].integer }
    private var currentConversation: Bool { model.selectedID == preview.conversationID && model.selected?.workspacePath == preview.workspace }

    var body: some View {
        VStack(spacing: 0) {
            HStack {
                Text(preview.source.name).font(.callout).lineLimit(1)
                Spacer()
                if preview.canAttach {
                    Button {
                        do { try model.attachPDF(preview) } catch { panel.error = error.localizedDescription }
                    } label: { Image(systemName: "paperclip") }
                        .disabled(!model.canEditMessageAttachments || model.loadingPDFPreview || !currentConversation || !preview.hasText || model.selected?.archived == true)
                        .help("Прикрепить выбранные страницы").accessibilityLabel("Прикрепить страницы PDF")
                }
                documentMenu(URL(fileURLWithPath: preview.source.path))
            }.padding(14).workspacePanelHeader()
            Divider().workspacePanelHeader()
            HStack {
                Text("Текст PDF").font(.caption).foregroundStyle(.secondary)
                Spacer()
                Button { changePage(page - 1) } label: { Image(systemName: "chevron.left") }
                    .disabled(page <= 1 || model.loadingPDFPreview || !model.canEditMessageAttachments || !currentConversation)
                    .accessibilityLabel("Предыдущая страница PDF")
                Text("\(preview.source.pageLabel) / \(total)").font(.caption.monospacedDigit())
                Button { changePage((preview.source.pages.last ?? page) + 1) } label: { Image(systemName: "chevron.right") }
                    .disabled((preview.source.pages.last ?? page) >= total || model.loadingPDFPreview || !model.canEditMessageAttachments || !currentConversation)
                    .accessibilityLabel("Следующая страница PDF")
                if model.loadingPDFPreview { ProgressView().controlSize(.small) }
            }.padding(12).workspacePanelHeader()
            ScrollView {
                VStack(alignment: .leading, spacing: 20) {
                    ForEach(Array(preview.pages.enumerated()), id: \.offset) { _, value in
                        Text(value["text"].text.isEmpty ? "На этой странице нет текстового слоя." : value["text"].text)
                            .font(NativeTheme.messageFont).lineSpacing(6).textSelection(.enabled)
                            .frame(maxWidth: .infinity, alignment: .leading)
                        if value["truncated"].flag {
                            Text("Показано начало текста страницы.").font(.caption).foregroundStyle(.secondary)
                        }
                    }
                }.padding(24)
            }
            Text("Оригинальное оформление — через «Открыть».").font(.caption).foregroundStyle(.secondary).padding(10)
        }
    }
    private func changePage(_ next: Int) { Task { await model.refreshWorkspacePDF(preview, page: next, tabID: tabID, in: panel) } }
}

private func documentMenu(_ url: URL, text: Bool = false) -> some View {
    Menu {
        Button(text ? "Открыть в TextEdit" : "Открыть в Просмотре") {
            let application = URL(fileURLWithPath: text ? "/System/Applications/TextEdit.app" : "/System/Applications/Preview.app")
            NSWorkspace.shared.open([url], withApplicationAt: application, configuration: NSWorkspace.OpenConfiguration())
        }
        Button("Показать в Finder") { NSWorkspace.shared.activateFileViewerSelecting([url]) }
    } label: { Label("Открыть", systemImage: "arrow.up.right.square") }
        .menuStyle(.borderlessButton).fixedSize().font(.caption).help(url.path)
}
