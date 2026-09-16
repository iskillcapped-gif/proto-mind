import AppKit
import Foundation

extension AppModel {
    var currentHistoryArchive: ChatArchive {
        // Preserve written drafts for restart/recovery, but never serialize untouched launchers.
        let saved = conversations.filter { !provisionalPanelConversations.contains($0.id) || $0.hasDraftOrMessages }
        let selection = selectedID.flatMap { id in saved.contains(where: { $0.id == id }) ? id : saved.first?.id }
        return ChatArchive(conversations: saved, selectedID: selection)
    }

    func openHistoryBackups() {
        guard !globalBusy, !client.turnOutstanding else { return }
        historyBackupPreview = nil; historyBackupError = nil; historyBackupNotice = nil
        refreshHistoryBackups()
        showHistoryBackups = true
        NSApp?.windows.first(where: { $0.title == "Proto-Mind" })?.makeKeyAndOrderFront(nil)
    }

    func refreshHistoryBackups() {
        do { historyBackupItems = try store.backups() }
        catch { historyBackupError = error.localizedDescription }
    }

    func inspectHistoryBackup(_ url: URL) {
        guard !globalBusy, !client.turnOutstanding else { return }
        historyBackupPreview = nil; historyBackupError = nil; historyBackupNotice = nil
        do { historyBackupPreview = try store.previewBackup(at: url) }
        catch { historyBackupError = error.localizedDescription }
    }

    func chooseHistoryBackup() {
        guard !globalBusy, !client.turnOutstanding else { return }
        let panel = NSOpenPanel()
        panel.title = "Выберите копию диалогов"
        panel.message = "Выберите папку копии Proto-Mind или прежний файл conversations.json."
        panel.canChooseFiles = true; panel.canChooseDirectories = true; panel.allowsMultipleSelection = false
        presentFilePicker(panel) { [weak self] response in
            guard response == .OK, let url = panel.url else { return }
            self?.inspectHistoryBackup(url)
        }
    }

    func exportHistoryBackup(to url: URL) throws {
        guard !globalBusy, !client.turnOutstanding else { throw NativeError.message("Дождитесь завершения запроса перед сохранением копии.") }
        try store.exportBackup(currentHistoryArchive, to: url)
        historyBackupNotice = "Копия диалогов сохранена: \(url.lastPathComponent)"
        historyBackupError = nil
    }

    func chooseHistoryExport() {
        guard !globalBusy, !client.turnOutstanding else { return }
        let panel = NSSavePanel()
        panel.title = "Сохранить копию диалогов"
        panel.nameFieldStringValue = "Proto-Mind Dialogs \(Date().formatted(.iso8601.year().month().day())).protomind-history"
        panel.canCreateDirectories = true
        presentFilePicker(panel) { [weak self] response in
            guard response == .OK, let url = panel.url, let self else { return }
            do { try self.exportHistoryBackup(to: url) }
            catch { self.historyBackupError = error.localizedDescription }
        }
    }

    func restoreHistoryBackup(_ preview: ChatBackupPreview) {
        guard !globalBusy, !client.turnOutstanding, historyBackupPreview?.id == preview.id else { return }
        do {
            let archive = try store.restore(preview, preserving: currentHistoryArchive)
            installRestoredHistory(archive)
            historyBackupPreview = nil
            historyBackupNotice = "Диалоги восстановлены. Предыдущее состояние и ваши несохранённые сообщения оставлены в локальных копиях."
            historyBackupError = nil
            refreshHistoryBackups()
        } catch { historyBackupError = error.localizedDescription }
    }

    func reloadCurrentHistory() {
        guard !globalBusy, !client.turnOutstanding else { return }
        do {
            let archive = try store.reloadPreserving(currentHistoryArchive)
            installRestoredHistory(archive)
            historyBackupNotice = "Актуальная история открыта. Предыдущая версия из этого окна сохранена в локальных копиях."
            historyBackupError = nil
            refreshHistoryBackups()
        } catch { historyBackupError = error.localizedDescription; report(error) }
    }

    private func installRestoredHistory(_ archive: ChatArchive) {
        draftSave?.cancel(); dirtyDraft = false
        discardAgentGrants(); invalidateSessionSpinePilot()
        pendingAction = nil; imagePreview = nil; pdfPreview = nil; attachmentDropPreview = nil
        showWorkSessions = false; showConversationHistory = false; showContextDesk = false; showInspector = false
        workspacePanel.closeAll()
        provisionalPanelConversations.removeAll()
        conversations = archive.conversations
        if conversations.isEmpty { conversations = [Conversation()] }
        selectedID = conversations.first(where: { $0.id == archive.selectedID })?.id ?? conversations.first?.id
        historyPersistence = HistoryPersistenceState(); error = nil
        restoreComposer(); resetWorkSessionPages(); resetWorkspaceView()
        // select() also closes source-bound inspectors and invalidates their requests.
        if let selectedID { select(selectedID) }
        status = "История восстановлена"
    }

    func saveHistory() throws {
        guard !privateBackupRestartRequired else { throw NativeError.message("Перезапустите Proto-Mind после восстановления данных.") }
        draftSave?.cancel()
        do {
            try store.save(currentHistoryArchive)
            dirtyDraft = false
            if error == historyPersistence.failure { error = nil }
            historyPersistence = HistoryPersistenceState()
        } catch {
            historyPersistence = HistoryPersistenceState(hasUnsavedChanges: true, failure: error.localizedDescription,
                                                         requiresRecovery: store.writeBlocked)
            throw error
        }
    }

    @discardableResult
    func persist() -> Bool {
        do { try saveHistory(); return true }
        catch { status = "История не сохранена"; return false }
    }

    @discardableResult
    func retryHistorySave() -> Bool {
        guard !globalBusy, !client.turnOutstanding, !store.writeBlocked else { return false }
        guard persist() else { return false }
        status = "История сохранена"
        return true
    }

    func saveBeforeExit() -> Bool {
        if privateBackupRestartRequired || (privateBackup.pending && privateBackup.windowIsPreserved(self)) { return true }
        guard dirtyDraft || historyPersistence.hasUnsavedChanges else { return true }
        return persist()
    }
}
