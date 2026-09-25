import AppKit
import SwiftUI

struct WorkspacePanelControls {
    let title: String
    let activate: () -> Void
}

struct WorkspacePanelView: View {
    @ObservedObject var model: AppModel
    @ObservedObject var panel: WorkspacePanelModel
    @Environment(\.desktopGlass) private var desktopGlass
    var width: CGFloat = 0
    var position: WorkspacePanelPosition = .upper
    var controls: WorkspacePanelControls? = nil
    @State private var hovered = false
    @State private var addingTab = false
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
                                        .help(L10n.text("Закрыть вкладку")).accessibilityLabel(L10n.pick("Закрыть вкладку \(title(tab))", "Close tab \(title(tab))"))
                                }.font(.system(size: 11)).padding(8)
                                    .background(panel.selectedID == tab.id ? NativeTheme.composer : .clear, in: RoundedRectangle(cornerRadius: 8))
                                    .id(tab.id)
                            }
                        }
                    }.onChange(of: panel.selectedID) { _, id in
                        if let id { Task { @MainActor in await Task.yield(); proxy.scrollTo(id, anchor: .trailing) } }
                    }
                }
                Button { activate(); addingTab.toggle() } label: { Image(systemName: "plus").frame(width: 26, height: 28).contentShape(Rectangle()) }
                    .buttonStyle(.nativeHover)
                    .help(L10n.text("Добавить вкладку")).accessibilityLabel(L10n.text("Добавить вкладку · ") + (controls?.title ?? position.title))
                    .composerPopover(isPresented: $addingTab, width: 270, trailing: true, direction: .below) {
                        WorkspacePanelMenu(model: model, panel: panel, activate: activate, dismiss: { addingTab = false }, chooseCLI: chooseCLI)
                    }
                if controls == nil {
                    Button { model.workspacePanels.toggleExpansion(position) } label: {
                        Image(systemName: panel.expanded ? "arrow.down.right.and.arrow.up.left" : "arrow.up.left.and.arrow.down.right")
                            .frame(width: 26, height: 28).contentShape(Rectangle())
                    }.buttonStyle(.nativeHover).foregroundStyle(.secondary)
                        .help(panel.expanded ? L10n.text("Вернуть размер") : L10n.text("Развернуть до боковой колонки"))
                        .accessibilityLabel((panel.expanded ? L10n.pick("Свернуть панель · ", "Restore panel · ") : L10n.pick("Развернуть панель · ", "Expand panel · ")) + position.title)
                }
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
        .onChange(of: panel.selectedID) { old, _ in
            if let tab = panel.tabs.first(where: { $0.id == old }), case .conversation(let id) = tab.content { model.dictation.stop(for: id) }
            if model.conversationRouting.panel === panel { model.conversationRouting.objectWillChange.send() }
        }
        .workspaceMenuBoundary()
        .background(ConversationInteractionRegion(routing: model.conversationRouting, panel: panel, enabled: panel.visible))
        .overlay(alignment: position == .upper ? .bottomLeading : .topLeading) {
            if controls == nil {
            Button { model.workspacePanels.toggleExpansion(position) } label: {
                Image(systemName: "triangle.fill")
                    .font(.system(size: 12)).rotationEffect(.degrees(position == .upper ? (panel.expanded ? 45 : -135) : (panel.expanded ? 135 : -45)))
                    .foregroundStyle(.primary.opacity(0.75)).frame(width: 27, height: 27)
                    .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 8))
            }.buttonStyle(.plain).padding(4).opacity(hovered ? 1 : 0).allowsHitTesting(hovered)
                .help(panel.expanded ? L10n.text("Вернуть две панели") : L10n.text("Развернуть до боковой колонки"))
                .accessibilityLabel((panel.expanded ? L10n.text("Свернуть · ") : L10n.text("Развернуть · ")) + position.title)
                .accessibilityHidden(!hovered)
            }
        }.onHover { hovered = $0 }
        .workspaceConfirmationDialog(L10n.text("Закрыть терминал?"), isPresented: $confirmTerminalClose, titleVisibility: .visible) {
            Button(L10n.text("Закрыть терминал"), role: .destructive) { confirmTerminalClose = false; if let id = terminalToClose { panel.close(id) }; terminalToClose = nil }
            Button(L10n.text("Отмена"), role: .cancel) { confirmTerminalClose = false; terminalToClose = nil }
        } message: { Text(L10n.text("Это завершит терминальный сеанс этой вкладки. Задачи в диалогах PM продолжат работу.")) }
    }

    private func activate() {
        model.conversationRouting.activate(panel)
        if let controls { controls.activate() } else { model.workspacePanels.active = position }
    }
    private var directory: URL { model.selected?.workspacePath.map { URL(fileURLWithPath: $0) } ?? FileManager.default.homeDirectoryForCurrentUser }

    private var welcome: some View {
        ViewThatFits {
            VStack(alignment: .leading, spacing: 12) {
                Text(L10n.text("Откройте рядом")).font(.system(size: 18, weight: .medium))
                Text(L10n.text("Диалог, страницу или инструменты для работы.")).font(.system(size: 12)).foregroundStyle(.secondary)
                HStack(spacing: 8) {
                    launcher(L10n.text("Диалог PM"), icon: "bubble.left.and.bubble.right") { model.newPanelConversation(in: panel) }
                    launcher(L10n.text("Браузер"), icon: "globe") { panel.openBrowser() }
                    launcher(L10n.text("Терминал"), icon: "terminal") { panel.openTerminal(directory: directory) }
                }.padding(.top, 5)
            }.padding(24)
            VStack(spacing: 10) {
                launcher(L10n.text("Диалог PM"), icon: "bubble.left.and.bubble.right") { model.newPanelConversation(in: panel) }
                HStack {
                    launcher(L10n.text("Браузер"), icon: "globe") { panel.openBrowser() }
                    launcher(L10n.text("Терминал"), icon: "terminal") { panel.openTerminal(directory: directory) }
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
        case .pdf(let pdf): WorkspacePDFView(model: model, panel: panel, preview: pdf, tabID: tab.id).id(pdf.id)
        case .document(let document): WorkspaceDocumentView(document: document)
        case .browser(let browser): BrowserView(browser: browser, app: model, sourcePanel: panel)
        case .conversation(let id): ConversationPaneView(app: model, conversationID: id, panel: panel)
        case .terminal(let terminal): WorkspaceTerminalView(terminal: terminal)
        case .answer(let answer): WorkspaceAnswerView(model: model, panel: panel, answer: answer)
        }
    }

    private func title(_ tab: WorkspacePanelTab) -> String {
        if case .conversation(let id) = tab.content { return model.conversations.first { $0.id == id }?.displayTitle ?? L10n.text("Диалог") }
        return tab.title
    }
    private func close(_ tab: WorkspacePanelTab) {
        if case .conversation(let id) = tab.content { model.dictation.stop(for: id) }
        if case .terminal(let terminal) = tab.content, terminal.running { terminalToClose = tab.id; confirmTerminalClose = true }
        else { panel.close(tab.id) }
    }
    private func chooseCLI() {
        activate()
        let picker = NSOpenPanel()
        picker.canChooseDirectories = false; picker.allowsMultipleSelection = false; picker.prompt = L10n.text("Запустить CLI")
        model.presentFilePicker(picker, in: panel.presentations) { result in
            if result == .OK, let url = picker.url { panel.openTerminal(directory: directory, executable: url.path, arguments: []) }
        }
    }
}

private struct WorkspaceAnswerView: View {
    @ObservedObject var model: AppModel
    let panel: WorkspacePanelModel
    let answer: WorkspaceAnswerPreview
    @Environment(\.workspacePresentations) private var presentations
    @StateObject private var responseExport = ResponseExportModel()

    var body: some View {
        VStack(spacing: 0) {
            HStack(spacing: 8) {
                Text(answer.title).font(.callout).lineLimit(1).help(answer.title)
                Spacer(minLength: 0)
                ResponseCopyButton { model.copy(answer.text) }
                Button {
                    responseExport.save(ResponseDocument(text: answer.text, conversationTitle: answer.title), using: model, in: presentations)
                } label: { Image(systemName: "square.and.arrow.down").frame(width: 28, height: 28) }
                    .help(L10n.pick("Сохранить ответ…", "Save response…"))
                    .accessibilityLabel(L10n.pick("Сохранить ответ…", "Save response…"))
                Button(L10n.pick("К диалогу", "Go to conversation")) { model.select(answer.conversationID) }
            }.buttonStyle(.nativeHover).foregroundStyle(.secondary).padding(12).workspacePanelHeader()
            Divider().workspacePanelHeader()
            ScrollView {
                MessageMarkdownView(text: answer.text, copy: model.copy, openLink: { url in
                    if NativeBrowserURL.isWebURL(url) { panel.openBrowser(url) }
                    else { model.openPanelFile(url, conversationID: answer.conversationID, panel: panel) }
                }).padding(24).frame(maxWidth: .infinity, alignment: .leading)
                Color.clear.frame(height: 16)
                    .background(ResponseReadMarker(app: model, conversationID: answer.conversationID, messageID: answer.messageID))
            }
        }.responseExportFeedback(responseExport)
    }
}

private struct BrowserTabTitle: View {
    @ObservedObject var browser: NativeBrowserTab
    var titleChanged: () -> Void
    var body: some View {
        Text(browser.title).lineLimit(1).help(browser.currentURL?.absoluteString ?? L10n.text("Новая страница"))
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
                    Button(showSource ? L10n.text("Просмотр") : L10n.text("Исходник")) { showSource.toggle() }.font(.caption)
                }
                Button { Task { await model.openWorkspaceEntry(.object(["path": .string(file.path), "directory": .bool(false)]), in: panel) } } label: {
                    Image(systemName: "arrow.clockwise")
                }.disabled(!canAttach || model.loadingWorkspace).help(L10n.text("Обновить файл")).accessibilityLabel(L10n.text("Обновить файл"))
                Button { model.attachWorkspaceText(file, in: panel) } label: { Image(systemName: "paperclip") }
                    .disabled(!canAttach).help(L10n.text("Прикрепить к сообщению")).accessibilityLabel(L10n.text("Прикрепить файл к сообщению"))
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
                Text(L10n.text("Показаны первые 12 000 символов. Полный файл доступен через «Открыть»."))
                    .font(.caption).foregroundStyle(.secondary).padding(10)
            }
            if model.selectedID != file.conversationID || model.selected?.workspacePath != file.root {
                Text(L10n.text("Файл открыт из другого диалога или папки.")).font(.caption).foregroundStyle(.secondary).padding(10)
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
                        .help(L10n.text("Прикрепить к сообщению")).accessibilityLabel(L10n.text("Прикрепить изображение к сообщению"))
                }
                documentMenu(URL(fileURLWithPath: preview.source.path))
            }.padding(14).workspacePanelHeader()
            Divider().workspacePanelHeader()
            Image(nsImage: preview.thumbnail).resizable().scaledToFit().padding(20)
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .accessibilityLabel(L10n.format("Изображение \(preview.source.name)"))
            Text("\(preview.source.value["width"].integer) × \(preview.source.value["height"].integer)")
                .font(.caption).foregroundStyle(.secondary).padding(10)
        }
    }
}

func documentMenu(_ url: URL, text: Bool = false) -> some View {
    Menu {
        Button(text ? L10n.text("Открыть в TextEdit") : L10n.text("Открыть в Просмотре")) {
            let application = URL(fileURLWithPath: text ? "/System/Applications/TextEdit.app" : "/System/Applications/Preview.app")
            NSWorkspace.shared.open([url], withApplicationAt: application, configuration: NSWorkspace.OpenConfiguration())
        }
        Button(L10n.text("Показать в Finder")) { NSWorkspace.shared.activateFileViewerSelecting([url]) }
    } label: { Label(L10n.text("Открыть"), systemImage: "arrow.up.right.square") }
        .menuStyle(.borderlessButton).fixedSize().font(.caption).help(url.path)
}
