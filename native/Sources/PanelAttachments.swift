import AppKit

extension AppModel {
    func clearPanelAttachments(_ id: UUID) {
        guard !operationBusy, let index = conversations.firstIndex(where: { $0.id == id }), !conversations[index].archived else { return }
        conversations[index].pendingFiles = []; conversations[index].pendingImages = []; conversations[index].pendingPDFs = []
        persist()
    }

    func choosePanelAttachment(conversationID: UUID, in panel: WorkspacePanelModel? = nil) {
        guard !operationBusy, !isRunning(conversationID), let conversation = conversations.first(where: { $0.id == conversationID }) else { return }
        let picker = NSOpenPanel()
        picker.canChooseDirectories = false; picker.allowsMultipleSelection = false
        picker.directoryURL = conversation.workspacePath.map { URL(fileURLWithPath: $0) }
        picker.prompt = "Прикрепить"
        picker.message = "Текстовый файл из папки этого диалога или первая страница PDF."
        presentFilePicker(picker, in: panel?.presentations) { [weak self] response in
            guard response == .OK, let url = picker.url, let self else { return }
            Task { await self.attachPanelFile(url, conversationID: conversationID, in: panel) }
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
                guard preview.source.path == path, preview.source.pages == [1], preview.hasText else { throw NativeError.message("Предпросмотр PDF относится к другому файлу.") }
                guard !isRunning(conversationID), let index = conversations.firstIndex(where: { $0.id == conversationID }),
                      conversations[index].workspacePath == conversation.workspacePath, !conversations[index].archived,
                      conversations[index].provider == conversation.provider, !operationBusy else { return }
                var next = conversations[index].pendingPDFs.filter { $0["path"] != preview.source.value["path"] }
                next.append(preview.source.value)
                try NativePDFAttachment.validate(next)
                conversations[index].pendingPDFs = next
            } else {
                guard let root = conversation.workspacePath else { throw NativeError.message("Выберите папку проекта для текстового вложения.") }
                let path = try NativeAttachmentDrop.relativePath(NativeAttachmentDrop.localURL(url), workspace: root)
                let file = try await client.request("workspace_read", ["workspace_root": .string(root), "path": .string(path)])
                guard file["read_only"].flag, file["path"].text == path, !isRunning(conversationID),
                      let index = conversations.firstIndex(where: { $0.id == conversationID }), conversations[index].workspacePath == root, !conversations[index].archived,
                      conversations[index].provider == conversation.provider, !operationBusy else { return }
                var files = conversations[index].pendingFiles.filter { $0["path"].text != path }
                guard files.count < 3 else { throw NativeError.message("Можно прикрепить до трёх текстовых файлов.") }
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
              url.isFileURL || url.scheme == nil else { panel.error = "Для файла нужна папка исходного диалога."; return }
        Task {
            do {
                let local = url.isFileURL || url.path.hasPrefix("/") ? URL(fileURLWithPath: url.path) : URL(fileURLWithPath: root).appendingPathComponent(url.path)
                let path = try NativeAttachmentDrop.relativePath(local, workspace: root)
                let file = try await execution(for: conversationID).client.request("workspace_read", ["workspace_root": .string(root), "path": .string(path)])
                guard file["read_only"].flag, file["path"].text == path else { throw NativeError.message("Ответ относится к другому файлу.") }
                panel.open(.text(WorkspaceTextPreview(conversationID: conversationID, root: root, value: file)))
            } catch { panel.error = error.localizedDescription }
        }
    }
}
