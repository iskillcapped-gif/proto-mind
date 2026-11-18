import AppKit

extension WorkspacePanelModel {
    var sourceConversationID: UUID? {
        switch selected?.content {
        case .conversation(let id): return id
        case .text(let file): return file.conversationID
        case .image(let image): return image.conversationID
        case .pdf(let pdf): return pdf.conversationID
        case .document(let document): return document.conversationID
        case .terminal(let terminal): return terminal.conversationID
        case .answer(let answer): return answer.conversationID
        default: return nil
        }
    }

    func workingDirectory(in app: AppModel) -> URL {
        if case .terminal(let terminal) = selected?.content { return terminal.directory }
        let id = sourceConversationID ?? app.selectedID
        let path = app.conversations.first { $0.id == id }?.workspacePath
        return path.map { URL(fileURLWithPath: $0, isDirectory: true) } ?? FileManager.default.homeDirectoryForCurrentUser
    }
}

extension AppModel {
    @discardableResult
    func openWorkspaceLink(_ url: URL, relativeTo directory: URL? = nil, in targetPanel: WorkspacePanelModel? = nil,
                           conversationID: UUID? = nil) -> Task<Void, Never>? {
        let panel = targetPanel ?? workspacePanel
        if NativeBrowserURL.isWebURL(url) { panel.openBrowser(url); return nil }
        guard let chat = conversations.first(where: { $0.id == (conversationID ?? selectedID) }), let root = chat.workspacePath else {
            panel.visible = true; panel.error = L10n.text("Для просмотра файла выберите папку проекта.")
            return nil
        }
        let file = url.scheme == nil && !url.path.hasPrefix("/")
            ? (directory ?? URL(fileURLWithPath: root)).appendingPathComponent(url.path) : url
        let local = file.scheme == nil && file.path.hasPrefix("/") && file.host == nil ? URL(fileURLWithPath: file.path) : file
        let tab = panel.selectedID, wasVisible = panel.visible
        return Task {
            guard panel.selectedID == tab, !wasVisible || panel.visible else { return }
            await openWorkspaceFile(local, from: chat, in: panel, requiresSelection: conversationID == nil)
        }
    }

    func openWorkspaceTextLink(_ url: URL, from file: WorkspaceTextPreview, in panel: WorkspacePanelModel) {
        if NativeBrowserURL.isWebURL(url) { panel.openBrowser(url); return }
        guard conversations.contains(where: { $0.id == file.conversationID && $0.workspacePath == file.root }),
              !file.requiresSelectedConversation || selectedID == file.conversationID else {
            panel.error = L10n.text("Для файла нужна папка исходного диалога."); return
        }
        openWorkspaceLink(url, relativeTo: file.url.deletingLastPathComponent(), in: panel,
                          conversationID: file.requiresSelectedConversation ? nil : file.conversationID)
    }

    func chooseWorkspaceDocument(in targetPanel: WorkspacePanelModel? = nil) {
        let panel = targetPanel ?? workspacePanel
        let sourceID = panel.sourceConversationID
        guard !operationBusy, let chat = conversations.first(where: { $0.id == (sourceID ?? selectedID) }) else { return }
        let picker = NSOpenPanel()
        picker.canChooseDirectories = false; picker.allowsMultipleSelection = false; picker.resolvesAliases = false
        picker.prompt = L10n.text("Открыть")
        picker.message = L10n.pick("Текст и документы Office из проекта, изображения PNG и JPEG или PDF.",
                                   "Project text and Office documents, PNG and JPEG images, or PDFs.")
        picker.directoryURL = panel.workingDirectory(in: self)
        let tab = panel.selectedID
        presentFilePicker(picker, in: panel.presentations) { [weak self] response in
            guard response == .OK, let url = picker.url, panel.selectedID == tab, let self else { return }
            Task { await self.openWorkspaceFile(url, from: chat, in: panel, requiresSelection: sourceID == nil, picked: true) }
        }
    }

    /// Previews use the service bridge so a running task cannot hold up its own result.
    /// Only an explicit Finder selection can open media outside the originating project.
    func openWorkspaceFile(_ url: URL, from chat: Conversation, in panel: WorkspacePanelModel,
                           requiresSelection: Bool, picked: Bool = false) async {
        func current() -> Bool {
            !operationBusy && (!requiresSelection || selectedID == chat.id)
                && conversations.contains { $0.id == chat.id && $0.workspacePath == chat.workspacePath }
        }
        guard current() else { return }
        let ticket = UUID()
        panel.fileOpenID = ticket
        defer { if panel.fileOpenID == ticket { panel.fileOpenID = nil } }
        do {
            let local = try NativeAttachmentDrop.localURL(url)
            let content: WorkspacePanelTab.Content
            let media = NativeAttachmentDrop.isImage(local) || NativeAttachmentDrop.isPDF(local)
            let path = picked && media ? nil : try NativeAttachmentDrop.relativePath(local, workspace: chat.workspacePath)
            if NativeAttachmentDrop.isImage(local) {
                let value = try await serviceClient.request("image_preview", ["path": .string(local.path)])
                let preview = try NativeImagePreview(value, conversationID: chat.id, canAttach: true,
                                                     requiresSelectedConversation: requiresSelection, workspace: chat.workspacePath)
                guard preview.source.path == local.path else { throw NativeError.message(L10n.text("Ответ относится к другому файлу.")) }
                content = .image(preview)
            } else if NativeAttachmentDrop.isPDF(local) {
                let value = try await serviceClient.request("pdf_preview", ["path": .string(local.path), "pages": .array([.number(1)])])
                let preview = try NativePDFPreview(value, conversationID: chat.id, workspace: chat.workspacePath, canAttach: true,
                                                   requiresSelectedConversation: requiresSelection)
                guard preview.source.path == local.path, preview.source.pages == [1] else { throw NativeError.message(L10n.text("Предпросмотр PDF относится к другому файлу.")) }
                content = .pdf(preview)
            } else {
                guard let root = chat.workspacePath, let path else { throw NativeError.message(L10n.text("Для файла нужна папка исходного диалога.")) }
                let params: [String: JSONValue] = ["workspace_root": .string(root), "path": .string(path)]
                if ["docx", "xlsx", "pptx"].contains(local.pathExtension.lowercased()) {
                    let value = try await serviceClient.request("document_read", params)
                    guard value["path"].text == path, AttachmentLibraryStore.validSHA(value["sha256"].text) else {
                        throw NativeError.message(L10n.text("Ответ относится к другому файлу."))
                    }
                    content = .document(WorkspaceDocumentPreview(conversationID: chat.id, url: local, sha256: value["sha256"].text))
                } else {
                    let value = try await serviceClient.request("workspace_read", params)
                    _ = try NativeDroppedFile(value, path: path)
                    content = .text(WorkspaceTextPreview(conversationID: chat.id, root: root, value: value, requiresSelectedConversation: requiresSelection))
                }
            }
            guard current(), panel.fileOpenID == ticket, panel.open(content) != nil else { return }
            if requiresSelection {
                workspaceError = nil
                if case .text(let file) = content { filePreview = file.value }
            }
        } catch {
            guard current(), panel.fileOpenID == ticket else { return }
            panel.visible = true; panel.error = error.localizedDescription
            if requiresSelection { workspaceError = error.localizedDescription }
        }
    }
}
