import AppKit
import SwiftUI

struct WorkspacePanelView: View {
    @ObservedObject var model: AppModel
    @ObservedObject var panel: WorkspacePanelModel
    var width: CGFloat = 0

    var body: some View {
        VStack(spacing: 0) {
            HStack(spacing: 5) {
                Button { panel.showFiles() } label: {
                    Image(systemName: "folder").padding(8)
                        .background(panel.selectedID == nil ? NativeTheme.selection : .clear, in: RoundedRectangle(cornerRadius: 8))
                }.help("Файлы проекта").accessibilityLabel("Файлы проекта")
                ScrollViewReader { proxy in ScrollView(.horizontal) {
                    HStack(spacing: 4) {
                        ForEach(panel.tabs) { tab in
                            HStack(spacing: 6) {
                                Button { panel.selectedID = tab.id } label: {
                                    HStack(spacing: 6) {
                                        Image(systemName: tab.symbol)
                                        if case .browser(let browser) = tab.content {
                                            BrowserTabTitle(browser: browser) {
                                                if let id = panel.selectedID {
                                                    Task { @MainActor in await Task.yield(); proxy.scrollTo(id, anchor: .trailing) }
                                                }
                                            }
                                        }
                                        else { Text(tab.title).lineLimit(1) }
                                    }.frame(maxWidth: 170)
                                }
                                Button { panel.close(tab.id) } label: { Image(systemName: "xmark").font(.system(size: 10)) }
                                    .help("Закрыть вкладку").accessibilityLabel("Закрыть вкладку \(tab.title)")
                            }.font(.system(size: 12)).padding(9)
                                .background(panel.selectedID == tab.id ? NativeTheme.composer : .clear, in: RoundedRectangle(cornerRadius: 9))
                                .id(tab.id)
                        }
                    }
                }.scrollIndicators(.hidden)
                    .onChange(of: panel.selectedID) { _, id in
                        if let id { Task { @MainActor in await Task.yield(); proxy.scrollTo(id, anchor: .trailing) } }
                    }
                    .onChange(of: width) { _, _ in
                        if let id = panel.selectedID { Task { @MainActor in await Task.yield(); proxy.scrollTo(id, anchor: .trailing) } }
                    }
                    .onAppear { if let id = panel.selectedID { proxy.scrollTo(id, anchor: .trailing) } }
                }
                Menu {
                    Button("Новая страница", systemImage: "globe") { panel.openBrowser() }
                    Button("Открыть файл…", systemImage: "doc") { model.chooseWorkspaceDocument() }.disabled(model.busy)
                    Button("Файлы проекта", systemImage: "folder") { model.showProjectFiles() }
                } label: { Image(systemName: "plus").frame(width: 24, height: 28) }
                    .menuStyle(.borderlessButton).menuIndicator(.hidden).fixedSize().help("Новая вкладка").accessibilityLabel("Новая вкладка")
                Button { panel.expanded.toggle() } label: {
                    Image(systemName: panel.expanded ? "arrow.down.right.and.arrow.up.left" : "arrow.up.left.and.arrow.down.right")
                }.help(panel.expanded ? "Вернуть разговор" : "Развернуть панель").accessibilityLabel(panel.expanded ? "Вернуть разговор" : "Развернуть панель")
                Button { panel.visible = false; panel.expanded = false } label: { Image(systemName: "sidebar.right") }
                    .help("Скрыть рабочую панель").accessibilityLabel("Скрыть рабочую панель")
            }.padding(.horizontal, 10).frame(height: 46)
            Divider()
            if let error = panel.error {
                HStack(alignment: .top) {
                    Text(error).font(.callout).textSelection(.enabled)
                    Spacer()
                    Button { panel.error = nil } label: { Image(systemName: "xmark") }
                }.foregroundStyle(.orange).padding(12)
            }
            Group {
                if let tab = panel.selected {
                    switch tab.content {
                    case .text(let file): WorkspaceTextView(model: model, file: file)
                    case .image(let image): WorkspaceImageView(model: model, preview: image)
                    case .pdf(let pdf): WorkspacePDFView(model: model, preview: pdf, tabID: tab.id)
                    case .browser(let browser): BrowserView(browser: browser)
                    }
                } else { ProjectWorkspaceView(model: model) }
            }.id(panel.selectedID).frame(maxWidth: .infinity, maxHeight: .infinity)
        }.background(NativeTheme.canvas)
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
    let file: WorkspaceTextPreview
    @State private var showSource = false
    private var markdown: Bool { ["md", "markdown"].contains(file.url.pathExtension.lowercased()) }
    private var canAttach: Bool { !model.busy && model.selectedID == file.conversationID && model.selected?.workspacePath == file.root && model.selected?.archived != true }

    var body: some View {
        VStack(spacing: 0) {
            HStack(spacing: 10) {
                Text(file.path).font(.system(size: 12)).lineLimit(1).truncationMode(.middle).help(file.url.path)
                Spacer(minLength: 0)
                if markdown {
                    Button(showSource ? "Просмотр" : "Исходник") { showSource.toggle() }.font(.caption)
                }
                Button { Task { await model.openWorkspaceEntry(.object(["path": .string(file.path), "directory": .bool(false)])) } } label: {
                    Image(systemName: "arrow.clockwise")
                }.disabled(!canAttach || model.loadingWorkspace).help("Обновить файл").accessibilityLabel("Обновить файл")
                Button { model.attachWorkspaceText(file) } label: { Image(systemName: "paperclip") }
                    .disabled(!canAttach).help("Прикрепить к сообщению").accessibilityLabel("Прикрепить файл к сообщению")
                documentMenu(file.url, text: true)
            }.padding(14)
            Divider()
            if markdown && !showSource {
                ScrollView {
                    MessageMarkdownView(text: file.value["preview"].text, copy: model.copy, openLink: {
                        model.openWorkspaceLink($0, relativeTo: file.url.deletingLastPathComponent())
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
    let preview: NativeImagePreview
    var body: some View {
        VStack(spacing: 0) {
            HStack {
                Text(preview.source.name).font(.callout).lineLimit(1)
                Spacer()
                if preview.canAttach {
                    Button {
                        do { try model.attachImage(preview) } catch { model.workspacePanel.error = error.localizedDescription }
                    } label: { Image(systemName: "paperclip") }
                        .disabled(model.busy || model.selectedID != preview.conversationID || model.selected?.archived == true)
                        .help("Прикрепить к сообщению").accessibilityLabel("Прикрепить изображение к сообщению")
                }
                documentMenu(URL(fileURLWithPath: preview.source.path))
            }.padding(14)
            Divider()
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
                        do { try model.attachPDF(preview) } catch { model.workspacePanel.error = error.localizedDescription }
                    } label: { Image(systemName: "paperclip") }
                        .disabled(model.busy || model.loadingPDFPreview || !currentConversation || !preview.hasText || model.selected?.archived == true)
                        .help("Прикрепить выбранные страницы").accessibilityLabel("Прикрепить страницы PDF")
                }
                documentMenu(URL(fileURLWithPath: preview.source.path))
            }.padding(14)
            Divider()
            HStack {
                Text("Текст PDF").font(.caption).foregroundStyle(.secondary)
                Spacer()
                Button { changePage(page - 1) } label: { Image(systemName: "chevron.left") }
                    .disabled(page <= 1 || model.loadingPDFPreview || model.busy || !currentConversation)
                    .accessibilityLabel("Предыдущая страница PDF")
                Text("\(preview.source.pageLabel) / \(total)").font(.caption.monospacedDigit())
                Button { changePage((preview.source.pages.last ?? page) + 1) } label: { Image(systemName: "chevron.right") }
                    .disabled((preview.source.pages.last ?? page) >= total || model.loadingPDFPreview || model.busy || !currentConversation)
                    .accessibilityLabel("Следующая страница PDF")
                if model.loadingPDFPreview { ProgressView().controlSize(.small) }
            }.padding(12)
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
    private func changePage(_ next: Int) { Task { await model.refreshWorkspacePDF(preview, page: next, tabID: tabID) } }
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
