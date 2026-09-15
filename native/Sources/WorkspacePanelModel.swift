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

struct WorkspacePanelTab: Identifiable {
    enum Content {
        case text(WorkspaceTextPreview)
        case image(NativeImagePreview)
        case pdf(NativePDFPreview)
        case browser(NativeBrowserTab)
    }
    let id: UUID
    var content: Content
    var title: String {
        switch content {
        case .text(let file): return file.url.lastPathComponent
        case .image(let image): return image.source.name
        case .pdf(let pdf): return pdf.source.name
        case .browser: return "Браузер"
        }
    }
    var symbol: String {
        switch content {
        case .text: return "doc.text"
        case .image: return "photo"
        case .pdf: return "doc.richtext"
        case .browser: return "globe"
        }
    }
    var sourceKey: String? {
        switch content {
        case .text(let file): return "text:\(file.conversationID):\(file.root):\(file.path)"
        case .image(let image): return "image:\(image.conversationID):\(image.source.path)"
        case .pdf(let pdf): return "pdf:\(pdf.conversationID):\(pdf.workspace ?? ""):\(pdf.source.path)"
        case .browser: return nil
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
    var selected: WorkspacePanelTab? { tabs.first { $0.id == selectedID } }

    func showFiles() { visible = true; selectedID = nil; error = nil }

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
        if case .browser(let browser) = tabs[index].content { browser.close() }
        tabs.remove(at: index)
        if selectedID == id { selectedID = tabs.isEmpty ? nil : tabs[min(index, tabs.count - 1)].id }
        error = nil
    }

    func closeAll() {
        for tab in tabs { if case .browser(let browser) = tab.content { browser.close() } }
        tabs = []; selectedID = nil; error = nil; visible = false; expanded = false
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
    func showProjectFiles() {
        section = .chat; workspacePanel.showFiles()
        Task { await refreshWorkspace() }
    }

    func openWorkspaceLink(_ url: URL, relativeTo directory: URL? = nil) {
        if NativeBrowserURL.isWebURL(url) { workspacePanel.openBrowser(url); return }
        guard url.isFileURL || url.scheme == nil, let root = selected?.workspacePath else {
            workspacePanel.visible = true; workspacePanel.error = "Для просмотра файла выберите папку проекта."
            return
        }
        let file: URL
        if url.isFileURL || url.path.hasPrefix("/") { file = URL(fileURLWithPath: url.path) }
        else { file = (directory ?? URL(fileURLWithPath: root)).appendingPathComponent(url.path) }
        do {
            let path = try NativeAttachmentDrop.relativePath(file, workspace: root)
            Task { await openWorkspaceEntry(.object(["path": .string(path), "directory": .bool(false)])) }
        } catch { workspacePanel.visible = true; workspacePanel.error = error.localizedDescription }
    }

    func chooseWorkspaceDocument() {
        guard canEditMessageAttachments, let conversationID = selectedID else { return }
        let picker = NSOpenPanel()
        picker.canChooseDirectories = false; picker.allowsMultipleSelection = false; picker.resolvesAliases = false
        picker.prompt = "Открыть"
        picker.message = "Текстовые файлы проекта, PNG, JPEG или PDF. Просмотр не прикрепляет файл к сообщению."
        picker.directoryURL = selected?.workspacePath.map { URL(fileURLWithPath: $0) }
        let completion: (NSApplication.ModalResponse) -> Void = { [weak self] response in
            guard response == .OK, let url = picker.url, let self, self.selectedID == conversationID else { return }
            Task {
                switch url.pathExtension.lowercased() {
                case "png", "jpg", "jpeg": await self.previewImage(url.path, inWorkspacePanel: true)
                case "pdf": await self.previewPDF(url.path, inWorkspacePanel: true)
                default: self.openWorkspaceLink(url)
                }
            }
        }
        presentFilePicker(picker, completion: completion)
    }

    func attachWorkspaceText(_ file: WorkspaceTextPreview) {
        guard selectedID == file.conversationID, selected?.workspacePath == file.root,
              selected?.archived != true, !busy else {
            workspacePanel.error = "Вернитесь в исходный диалог и папку, чтобы прикрепить этот файл."
            return
        }
        filePreview = file.value
        workspaceError = nil
        attachPreview()
        workspacePanel.error = workspaceError
    }

    func refreshWorkspacePDF(_ preview: NativePDFPreview, page: Int, tabID: UUID) async {
        guard canEditMessageAttachments, !loadingPDFPreview, let conversation = selected,
              conversation.id == preview.conversationID, conversation.workspacePath == preview.workspace,
              (1...preview.source.value["page_count"].integer).contains(page) else { return }
        loadingPDFPreview = true
        defer { loadingPDFPreview = false }
        do {
            let next = try await readPDFPreview(preview.source.path, pages: [page], conversation: conversation,
                                                canAttach: preview.canAttach, expectedSHA: preview.source.sha256)
            try workspacePanel.replacePDF(tabID, expected: preview, with: next)
        } catch { workspacePanel.error = error.localizedDescription }
    }
}
