import AppKit

enum PanelAttachmentKind { case image, pdf, file }

extension AppModel {
    func reportAttachmentError(_ error: Error, in destination: WorkspacePresentations) {
        let panels = [workspacePanels.upper, workspacePanels.lower] + desktop.companions.surfaces.map(\.panel)
        if destination !== presentations, let panel = panels.first(where: { $0.presentations === destination }) {
            panel.error = error.localizedDescription
        } else { report(error) }
    }

    func clearPanelAttachments(_ id: UUID) {
        guard !operationBusy, let index = conversations.firstIndex(where: { $0.id == id }), !conversations[index].archived else { return }
        conversations[index].pendingFiles = []; conversations[index].pendingImages = []; conversations[index].pendingPDFs = []
        persist()
    }

    func choosePanelAttachment(conversationID: UUID, in panel: WorkspacePanelModel? = nil, kind: PanelAttachmentKind = .file) {
        if kind == .image { chooseImage(conversationID: conversationID, in: panel?.presentations); return }
        if kind == .pdf { choosePDF(conversationID: conversationID, in: panel?.presentations); return }
        guard canReceiveAttachments(for: conversationID), let conversation = conversations.first(where: { $0.id == conversationID }) else { return }
        let picker = NSOpenPanel()
        picker.canChooseDirectories = false; picker.allowsMultipleSelection = false
        picker.directoryURL = conversation.workspacePath.map { URL(fileURLWithPath: $0) }
        picker.prompt = L10n.text("Прикрепить")
        picker.message = L10n.text("Текстовый файл из папки этого диалога или первая страница PDF.")
        presentFilePicker(picker, in: panel?.presentations) { [weak self] response in
            guard response == .OK, let url = picker.url, let self else { return }
            _ = self.receiveAttachmentDrop([url], conversationID: conversationID, in: panel?.presentations)
        }
    }

    func attachPanelFile(_ url: URL, conversationID: UUID, in panel: WorkspacePanelModel? = nil) async {
        guard !operationBusy, !isRunning(conversationID), let conversation = conversations.first(where: { $0.id == conversationID }), !conversation.archived else { return }
        do {
            let client = execution(for: conversationID).client
            if url.pathExtension.lowercased() == "pdf" {
                let path = try NativeAttachmentDrop.localURL(url).path
                let result = try await client.request("pdf_preview", ["path": .string(path), "pages": .array([.number(1)])])
                let preview = try NativePDFPreview(result, conversationID: conversationID, workspace: conversation.workspacePath, canAttach: true)
                guard preview.source.path == path, preview.source.pages == [1], preview.hasText else { throw NativeError.message(L10n.text("Предпросмотр PDF относится к другому файлу.")) }
                guard !isRunning(conversationID), let index = conversations.firstIndex(where: { $0.id == conversationID }),
                      conversations[index].workspacePath == conversation.workspacePath, !conversations[index].archived,
                      conversations[index].provider == conversation.provider, !operationBusy else { return }
                var next = conversations[index].pendingPDFs.filter { $0["path"] != preview.source.value["path"] }
                next.append(preview.source.value)
                try NativePDFAttachment.validate(next)
                conversations[index].pendingPDFs = next
            } else {
                guard let root = conversation.workspacePath else { throw NativeError.message(L10n.text("Выберите папку проекта для текстового вложения.")) }
                let path = try NativeAttachmentDrop.relativePath(NativeAttachmentDrop.localURL(url), workspace: root)
                let file = try await client.request("workspace_read", ["workspace_root": .string(root), "path": .string(path)])
                guard file["read_only"].flag, file["path"].text == path, !isRunning(conversationID),
                      let index = conversations.firstIndex(where: { $0.id == conversationID }), conversations[index].workspacePath == root, !conversations[index].archived,
                      conversations[index].provider == conversation.provider, !operationBusy else { return }
                var files = conversations[index].pendingFiles.filter { $0["path"].text != path }
                guard files.count < 3 else { throw NativeError.message(L10n.text("Можно прикрепить до трёх текстовых файлов.")) }
                files.append(.object(["path": file["path"], "sha256": file["sha256"], "included_chars": .number(Double(min(6000, file["characters"].integer))), "truncated": .bool(file["characters"].integer > 6000)]))
                conversations[index].pendingFiles = files
            }
            persist()
        } catch {
            if let panel { panel.error = error.localizedDescription } else { report(error) }
        }
    }

    func openPanelFile(_ url: URL, conversationID: UUID, panel: WorkspacePanelModel) {
        guard let conversation = conversations.first(where: { $0.id == conversationID }), let root = conversation.workspacePath,
              url.isFileURL || url.scheme == nil else { panel.error = L10n.text("Для файла нужна папка исходного диалога."); return }
        Task {
            do {
                let local = url.isFileURL || url.path.hasPrefix("/") ? URL(fileURLWithPath: url.path) : URL(fileURLWithPath: root).appendingPathComponent(url.path)
                let path = try NativeAttachmentDrop.relativePath(local, workspace: root)
                // Reading an artifact must not queue behind the task that created it.
                let kind = local.pathExtension.lowercased()
                if kind == "pdf" {
                    let value = try await serviceClient.request("pdf_preview", ["path": .string(local.path), "pages": .array([.number(1)])])
                    guard conversations.contains(where: { $0.id == conversationID && $0.workspacePath == root }) else { return }
                    panel.open(.pdf(try NativePDFPreview(value, conversationID: conversationID, workspace: root, canAttach: false)))
                    return
                }
                if ["docx", "xlsx", "pptx"].contains(kind) {
                    let value = try await serviceClient.request("document_read", ["workspace_root": .string(root), "path": .string(path)])
                    guard conversations.contains(where: { $0.id == conversationID && $0.workspacePath == root }) else { return }
                    panel.open(.document(WorkspaceDocumentPreview(conversationID: conversationID, url: local, sha256: value["sha256"].text)))
                    return
                }
                let file = try await serviceClient.request("workspace_read", ["workspace_root": .string(root), "path": .string(path)])
                guard conversations.contains(where: { $0.id == conversationID && $0.workspacePath == root }) else { return }
                guard file["read_only"].flag, file["path"].text == path else { throw NativeError.message(L10n.text("Ответ относится к другому файлу.")) }
                panel.open(.text(WorkspaceTextPreview(conversationID: conversationID, root: root, value: file)))
            } catch { panel.error = error.localizedDescription }
        }
    }
}

extension AppModel {
    func canEditAttachments(for id: UUID) -> Bool { ConversationComposerContext(app: self, id: id).canEditAttachments }
    func canReceiveAttachments(for id: UUID) -> Bool {
        canEditAttachments(for: id) && !loadingDroppedAttachments && !loadingImagePreview && !loadingPDFPreview
            && imagePreview == nil && pdfPreview == nil && attachmentDropPreview == nil && pendingAction == nil && pendingAgentAccess == nil
    }
    func removeConversationAttachment(_ path: String, kind: PanelAttachmentKind, conversationID: UUID?) {
        guard let id = conversationID, canEditAttachments(for: id), let index = conversations.firstIndex(where: { $0.id == id }) else { return }
        let previous = conversations[index]
        switch kind {
        case .file: conversations[index].pendingFiles.removeAll { $0["path"].text == path }
        case .image: conversations[index].pendingImages.removeAll { $0["path"].text == path }
        case .pdf: conversations[index].pendingPDFs.removeAll { $0["path"].text == path }
        }
        do { try saveHistory() } catch { conversations[index] = previous; report(error) }
    }
}
