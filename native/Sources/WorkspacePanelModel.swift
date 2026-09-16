import AppKit
import Combine
import Foundation

struct WorkspaceTextPreview {
    let conversationID: UUID
    let root: String
    let value: JSONValue
    var path: String { value["path"].text }
    var url: URL { URL(fileURLWithPath: root).appendingPathComponent(path) }
}

struct WorkspaceAnswerPreview {
    let conversationID: UUID
    let messageID: UUID
    let title: String
    let text: String
}

struct WorkspacePanelTab: Identifiable {
    enum Content {
        case text(WorkspaceTextPreview)
        case image(NativeImagePreview)
        case pdf(NativePDFPreview)
        case browser(NativeBrowserTab)
        case conversation(UUID)
        case terminal(WorkspaceTerminal)
        case answer(WorkspaceAnswerPreview)
    }
    let id: UUID
    var content: Content
    var title: String {
        switch content {
        case .text(let file): return file.url.lastPathComponent
        case .image(let image): return image.source.name
        case .pdf(let pdf): return pdf.source.name
        case .browser(let browser): return browser.messenger?.title ?? L10n.text("Браузер")
        case .conversation: return L10n.text("Диалог PM")
        case .terminal: return L10n.text("Терминал")
        case .answer(let answer): return answer.title
        }
    }
    var symbol: String {
        switch content {
        case .text: return "doc.text"
        case .image: return "photo"
        case .pdf: return "doc.richtext"
        case .browser(let browser): return browser.messenger == nil ? "globe" : "message"
        case .conversation: return "bubble.left.and.bubble.right"
        case .terminal: return "terminal"
        case .answer: return "doc.text"
        }
    }
    var sourceKey: String? {
        switch content {
        case .text(let file): return "text:\(file.conversationID):\(file.root):\(file.path)"
        case .image(let image): return "image:\(image.conversationID):\(image.source.path)"
        case .pdf(let pdf): return "pdf:\(pdf.conversationID):\(pdf.workspace ?? ""):\(pdf.source.path)"
        case .conversation(let id): return "conversation:\(id)"
        case .answer(let answer): return "answer:\(answer.conversationID):\(answer.messageID)"
        case .browser, .terminal: return nil
        }
    }
}

// An in-memory work surface. Tabs never enter chat history or provider context.
@MainActor
final class WorkspacePanelModel: ObservableObject {
    static let maximumTabs = 12
    @Published var visible = false
    @Published var expanded = false
    @Published private(set) var tabs: [WorkspacePanelTab] = []
    @Published var selectedID: UUID?
    @Published var error: String?
    @Published var filesSelected = false
    weak var presentations: WorkspacePresentations?
    var onConversationClosed: ((UUID) -> Void)?
    var selected: WorkspacePanelTab? { tabs.first { $0.id == selectedID } }

    func showFiles() { visible = true; selectedID = nil; filesSelected = true; error = nil }

    @discardableResult
    func open(_ content: WorkspacePanelTab.Content) -> UUID? {
        visible = true; error = nil
        let proposed = WorkspacePanelTab(id: UUID(), content: content)
        if let key = proposed.sourceKey, let index = tabs.firstIndex(where: { $0.sourceKey == key }) {
            tabs[index].content = content
            selectedID = tabs[index].id
            return selectedID
        }
        guard tabs.count < Self.maximumTabs else {
            error = "Открыто 12 вкладок. Закройте одну перед открытием следующей."
            return nil
        }
        tabs.append(proposed); selectedID = proposed.id
        return proposed.id
    }

    func openBrowser(_ url: URL? = nil) {
        let browser = NativeBrowserTab()
        guard open(.browser(browser)) != nil else { return }
        browser.openTab = { [weak self] url in self?.openBrowser(url) }
        if let url { browser.navigate(url.absoluteString) }
    }

    func showBrowser() {
        visible = true
        if let existing = tabs.last(where: { if case .browser = $0.content { return true }; return false }) {
            selectedID = existing.id
        } else { openBrowser() }
    }

    func close(_ id: UUID) {
        guard let index = tabs.firstIndex(where: { $0.id == id }) else { return }
        let closed = tabs[index].content
        if case .browser(let browser) = tabs[index].content { browser.close() }
        if case .terminal(let terminal) = tabs[index].content { terminal.close() }
        tabs.remove(at: index)
        if selectedID == id { selectedID = tabs.isEmpty ? nil : tabs[min(index, tabs.count - 1)].id }
        error = nil
        if case .conversation(let conversationID) = closed { onConversationClosed?(conversationID) }
    }

    func closeAll() {
        for tab in tabs {
            if case .browser(let browser) = tab.content { browser.close() }
            if case .terminal(let terminal) = tab.content { terminal.close() }
        }
        tabs = []; selectedID = nil; error = nil; visible = false; expanded = false
        filesSelected = false
    }

    func replacePDF(_ id: UUID, expected: NativePDFPreview, with preview: NativePDFPreview) throws {
        guard let index = tabs.firstIndex(where: { $0.id == id }),
              case .pdf(let current) = tabs[index].content, current.id == expected.id else {
            throw NativeError.message("Вкладка PDF уже закрыта или изменилась.")
        }
        tabs[index].content = .pdf(preview)
    }
}

extension AppModel {
    func openAnswerBesideChat(_ message: ChatMessage, conversationID: UUID, sourcePanel: WorkspacePanelModel? = nil) {
        guard message.role == "assistant" else { return }
        let panel: WorkspacePanelModel
        if let sourcePanel { panel = sourcePanel }
        else if desktop.enabled {
            let companion = desktop.companions.surface(.first)
            if !companion.visible { desktop.companions.toggle(.first) }
            panel = companion.panel
        } else { panel = workspacePanel }
        let document = ResponseDocument(text: message.text,
            conversationTitle: conversations.first { $0.id == conversationID }?.displayTitle ?? "")
        panel.open(.answer(WorkspaceAnswerPreview(conversationID: conversationID, messageID: message.id,
            title: document.title, text: document.text)))
    }

    func showProjectFiles(in panel: WorkspacePanelModel? = nil) {
        section = .chat; (panel ?? workspacePanel).showFiles()
        Task { await refreshWorkspace() }
    }

    func openWorkspaceLink(_ url: URL, relativeTo directory: URL? = nil, in targetPanel: WorkspacePanelModel? = nil) {
        let panel = targetPanel ?? workspacePanel
        if NativeBrowserURL.isWebURL(url) { panel.openBrowser(url); return }
        guard url.isFileURL || url.scheme == nil, let root = selected?.workspacePath else {
            panel.visible = true; panel.error = "Для просмотра файла выберите папку проекта."
            return
        }
        let file: URL
        if url.isFileURL || url.path.hasPrefix("/") { file = URL(fileURLWithPath: url.path) }
        else { file = (directory ?? URL(fileURLWithPath: root)).appendingPathComponent(url.path) }
        do {
            let path = try NativeAttachmentDrop.relativePath(file, workspace: root)
            Task { await openWorkspaceEntry(.object(["path": .string(path), "directory": .bool(false)]), in: panel) }
        } catch { panel.visible = true; panel.error = error.localizedDescription }
    }

    func chooseWorkspaceDocument(in targetPanel: WorkspacePanelModel? = nil) {
        let panel = targetPanel ?? workspacePanel
        guard canEditMessageAttachments, let conversationID = selectedID else { return }
        let picker = NSOpenPanel()
        picker.canChooseDirectories = false; picker.allowsMultipleSelection = false; picker.resolvesAliases = false
        picker.prompt = L10n.text("Открыть")
        picker.message = "Текстовые файлы проекта, PNG, JPEG или PDF. Просмотр не прикрепляет файл к сообщению."
        picker.directoryURL = selected?.workspacePath.map { URL(fileURLWithPath: $0) }
        let completion: (NSApplication.ModalResponse) -> Void = { [weak self] response in
            guard response == .OK, let url = picker.url, let self, self.selectedID == conversationID else { return }
            Task {
                switch url.pathExtension.lowercased() {
                case "png", "jpg", "jpeg": await self.previewImage(url.path, inWorkspacePanel: true, targetPanel: panel)
                case "pdf": await self.previewPDF(url.path, inWorkspacePanel: true, targetPanel: panel)
                default: self.openWorkspaceLink(url, in: panel)
                }
            }
        }
        presentFilePicker(picker, in: panel.presentations, completion: completion)
    }

    func attachWorkspaceText(_ file: WorkspaceTextPreview, in targetPanel: WorkspacePanelModel? = nil) {
        let panel = targetPanel ?? workspacePanel
        guard selectedID == file.conversationID, selected?.workspacePath == file.root,
              selected?.archived != true, !busy else {
            panel.error = "Вернитесь в исходный диалог и папку, чтобы прикрепить этот файл."
            return
        }
        filePreview = file.value
        workspaceError = nil
        attachPreview()
        panel.error = workspaceError
    }

    func refreshWorkspacePDF(_ preview: NativePDFPreview, page: Int, tabID: UUID, in targetPanel: WorkspacePanelModel? = nil) async {
        let panel = targetPanel ?? workspacePanel
        guard canEditMessageAttachments, !loadingPDFPreview, let conversation = selected,
              conversation.id == preview.conversationID, conversation.workspacePath == preview.workspace,
              (1...preview.source.value["page_count"].integer).contains(page) else { return }
        loadingPDFPreview = true
        defer { loadingPDFPreview = false }
        do {
            let next = try await readPDFPreview(preview.source.path, pages: [page], conversation: conversation,
                                                canAttach: preview.canAttach, expectedSHA: preview.source.sha256)
            try panel.replacePDF(tabID, expected: preview, with: next)
        } catch { panel.error = error.localizedDescription }
    }
}
