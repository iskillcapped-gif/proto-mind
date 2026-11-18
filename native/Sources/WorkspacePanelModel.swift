import AppKit
import Combine
import Foundation

struct WorkspaceTextPreview {
    let conversationID: UUID
    let root: String
    let value: JSONValue
    var requiresSelectedConversation = true
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
        case document(WorkspaceDocumentPreview)
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
        case .document(let document): return document.url.lastPathComponent
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
        case .document: return "doc.richtext"
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
        case .document(let document): return "document:\(document.conversationID):\(document.url.path):\(document.sha256)"
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
    @Published var visible = false { didSet { if !visible { fileOpenID = nil } } }
    @Published var expanded = false
    @Published private(set) var tabs: [WorkspacePanelTab] = []
    let chatFind = ChatFindModel()
    var fileOpenID: UUID?
    @Published var selectedID: UUID? {
        didSet {
            guard selectedID != oldValue else { return }
            fileOpenID = nil
            if chatFind.visible { chatFind.close() }
        }
    }
    @Published var error: String?
    @Published var transcriptDestination: TranscriptDestination?
    @Published var filesSelected = false
    weak var presentations: WorkspacePresentations?
    var onConversationClosed: ((UUID) -> Void)?
    var selected: WorkspacePanelTab? { tabs.first { $0.id == selectedID } }

    func showFiles() { fileOpenID = nil; visible = true; selectedID = nil; filesSelected = true; error = nil }

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
            error = L10n.text("Открыто 12 вкладок. Закройте одну перед открытием следующей.")
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
        fileOpenID = nil
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
            throw NativeError.message(L10n.text("Вкладка PDF уже закрыта или изменилась."))
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

    func canAttachWorkspaceText(_ file: WorkspaceTextPreview) -> Bool {
        (!file.requiresSelectedConversation || selectedID == file.conversationID)
            && canEditAttachments(for: file.conversationID)
            && conversations.contains { $0.id == file.conversationID && $0.workspacePath == file.root && !$0.archived }
    }

    func attachWorkspaceText(_ file: WorkspaceTextPreview, in targetPanel: WorkspacePanelModel? = nil) {
        let panel = targetPanel ?? workspacePanel
        guard canAttachWorkspaceText(file), let index = conversations.firstIndex(where: { $0.id == file.conversationID }) else {
            panel.error = L10n.text("Вернитесь в исходный диалог и папку, чтобы прикрепить этот файл."); return
        }
        do {
            let metadata = try NativeDroppedFile(file.value, path: file.path).metadata
            let previous = conversations[index].pendingFiles
            var next = previous.filter { $0["path"].text != file.path }
            guard next.count < 3 else { throw NativeError.message(L10n.text("Можно прикрепить до трёх текстовых файлов.")) }
            if let position = previous.firstIndex(where: { $0["path"].text == file.path }) { next.insert(metadata, at: position) }
            else { next.append(metadata) }
            conversations[index].pendingFiles = next
            do { try saveHistory() } catch { conversations[index].pendingFiles = previous; throw error }
            if selectedID == file.conversationID { section = .chat }
            panel.error = nil
        } catch { panel.error = error.localizedDescription }
    }

    func refreshWorkspacePDF(_ preview: NativePDFPreview, page: Int, tabID: UUID, in targetPanel: WorkspacePanelModel? = nil) async {
        let panel = targetPanel ?? workspacePanel
        guard !loadingPDFPreview, let conversation = conversations.first(where: { $0.id == preview.conversationID }),
              (!preview.requiresSelectedConversation || selectedID == conversation.id), conversation.workspacePath == preview.workspace,
              (1...preview.source.value["page_count"].integer).contains(page) else { return }
        loadingPDFPreview = true
        defer { loadingPDFPreview = false }
        do {
            let next = try await readPDFPreview(preview.source.path, pages: [page], conversation: conversation,
                                                canAttach: preview.canAttach, expectedSHA: preview.source.sha256,
                                                requiresSelectedConversation: preview.requiresSelectedConversation)
            try panel.replacePDF(tabID, expected: preview, with: next)
        } catch { panel.error = error.localizedDescription }
    }
}
