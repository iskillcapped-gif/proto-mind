import AppKit
import Foundation

// Main-actor transitions for this domain; stored state remains in AppModel.
extension AppModel {
    func newConversation() {
        guard canNavigateConversations else { return }
        conversationRouting.activate(nil)
        presentations.dismissAll()
        invalidateContextPreview()
        invalidateSessionSpinePilot()
        closeLearningReview()
        memoryWorkshop = nil; showMemoryWorkshop = false
        skillAuthoring = nil
        skillInspection?.close()
        skillOutcome?.close()
        skillDecision?.close()
        skillLifecycleApply?.close()
        skillRestore?.close()
        skillHistory?.close()
        projectMemory?.close()
        memorySuggestion?.close()
        skillTask?.close()
        sessionSpinePreview = nil
        flushDraft()
        var chat = Conversation()
        chat.codexAccountID = selected?.codexAccountID
        if serviceClient.configuration.isPortable { chat.provider = "codex"; chat.model = "" }
        conversations.insert(chat, at: 0)
        selectedID = chat.id
        transcriptDestination = nil
        resetWorkSessionPages()
        codexThreadStatus = .null
        modelSelectionNotice = nil
        inspectedMessageID = nil
        restoreComposer()
        showArchived = false
        conversationSearch = ""
        resetWorkspaceView()
        section = .chat
        persist()
    }

    func select(_ id: UUID) {
        guard canNavigateConversations, conversations.contains(where: { $0.id == id }) else { return }
        conversationRouting.activate(nil)
        presentations.dismissAll()
        invalidateContextPreview()
        invalidateSessionSpinePilot()
        closeLearningReview()
        memoryWorkshop = nil; showMemoryWorkshop = false
        skillAuthoring = nil
        skillInspection?.close()
        skillOutcome?.close()
        skillDecision?.close()
        skillLifecycleApply?.close()
        skillRestore?.close()
        skillHistory?.close()
        projectMemory?.close()
        memorySuggestion?.close()
        skillTask?.close()
        sessionSpinePreview = nil
        flushDraft()
        selectedID = id; section = .chat; inspectedMessageID = nil
        transcriptDestination = nil
        modelSelectionNotice = nil
        codexThreadStatus = .null
        restoreComposer(); resetWorkspaceView(); persist()
        resetWorkSessionPages()
        Task {
            await refreshWorkSessions()
            await refreshCodexThreadStatus()
        }
    }

    func setAutoSkillsEnabled(_ enabled: Bool) {
        guard !busy, let index = conversations.firstIndex(where: { $0.id == selectedID }), !conversations[index].archived else { return }
        conversations[index].autoSkillsEnabled = enabled
        invalidateContextPreview(); persist()
    }

    func setAutoProjectRecallEnabled(_ enabled: Bool) {
        guard !busy, let index = conversations.firstIndex(where: { $0.id == selectedID }), !conversations[index].archived else { return }
        conversations[index].autoProjectRecallEnabled = enabled
        invalidateContextPreview(); persist()
    }

    func setMemorySuggestionsEnabled(_ enabled: Bool) {
        guard !busy, let index = conversations.firstIndex(where: { $0.id == selectedID }), !conversations[index].archived else { return }
        conversations[index].memorySuggestionsEnabled = enabled; persist()
    }

    func setProvider(_ value: String) {
        guard !busy, ["ollama", "codex", "mock", "api", "claude"].contains(value), selected?.provider != value,
              let index = conversations.firstIndex(where: { $0.id == selectedID }) else { return }
        discardAgentGrants(for: selectedID)
        invalidateSessionSpinePilot()
        pendingPersonaActivation = nil
        conversations[index].provider = value
        conversations[index].apiWorkspaceToolsEnabled = false; conversations[index].apiWorkspaceGeneration = nil
        conversations[index].model = ""
        conversations[index].reasoningEffort = ""
        modelSelectionNotice = nil
        codexThreadStatus = .null
        persist()
    }

    func setModel(_ value: String) {
        guard !busy, let index = conversations.firstIndex(where: { $0.id == selectedID }) else { return }
        if selected?.provider == "codex", !value.isEmpty, !codexModels.contains(where: { $0.id == value }) { return }
        if selected?.model != value { invalidateSessionSpinePilot() }
        conversations[index].model = value
        if selected?.provider == "claude", let option = claudeAccount.snapshot?.model(value),
           !option.efforts.contains(conversations[index].reasoningEffort) {
            conversations[index].reasoningEffort = ""
        }
        pendingPersonaActivation = nil
        modelSelectionNotice = nil
        if selected?.provider == "codex", !conversations[index].reasoningEffort.isEmpty,
           !availableReasoningEfforts.contains(where: { $0.rawValue == conversations[index].reasoningEffort }) {
            conversations[index].reasoningEffort = ""
            modelSelectionNotice = L10n.text("Предыдущее усилие недоступно для этой модели. Выбрано значение по умолчанию.")
        }
        persist()
    }

    var codexModels: [CodexModelOption] {
        var seen = Set<String>()
        return models.compactMap(CodexModelOption.init).filter { seen.insert($0.id).inserted }
    }

    var selectedCodexModel: CodexModelOption? {
        let identifier = selected?.model ?? ""
        return identifier.isEmpty ? codexModels.first(where: \.isDefault) : codexModels.first { $0.id == identifier }
    }

    var availableReasoningEfforts: [CodexReasoningEffort] { selectedCodexModel?.efforts ?? [] }

    var reasoningEffortLabel: String {
        let value = selected?.reasoningEffort ?? ""
        if value.isEmpty { return selectedCodexModel?.defaultEffort?.title ?? L10n.text("Авто") }
        return CodexReasoningEffort(rawValue: value)?.title ?? value
    }

    var codexModelLabel: String {
        selectedCodexModel?.displayName ?? ((selected?.model.isEmpty ?? true) ? "Codex" : selected!.model)
    }

    var modelSelectionWarning: String? {
        guard selected?.provider == "codex", !models.isEmpty else { return nil }
        if !(selected?.model.isEmpty ?? true), selectedCodexModel == nil {
            return L10n.text("Сохранённая модель недоступна в текущем каталоге. Выберите другую: автоматической подмены не будет.")
        }
        if let effort = selected?.reasoningEffort, !effort.isEmpty,
           !availableReasoningEfforts.contains(where: { $0.rawValue == effort }) {
            return L10n.text("Сохранённое усилие больше не поддерживается. Выберите доступное или сбросьте настройки.")
        }
        return nil
    }

    func setReasoningEffort(_ value: String) {
        if selected?.provider == "claude", let id = selectedID { configureConversation(id, effort: value); return }
        guard !busy, selected?.provider == "codex", let index = conversations.firstIndex(where: { $0.id == selectedID }),
              value.isEmpty || availableReasoningEfforts.contains(where: { $0.rawValue == value }) else { return }
        if selected?.reasoningEffort != value { invalidateSessionSpinePilot() }
        conversations[index].reasoningEffort = value
        modelSelectionNotice = nil
        persist()
    }

    func resetCodexSelection() {
        guard !busy, selected?.provider == "codex", let index = conversations.firstIndex(where: { $0.id == selectedID }) else { return }
        invalidateSessionSpinePilot()
        conversations[index].model = ""
        conversations[index].reasoningEffort = ""
        modelSelectionNotice = nil
        persist()
    }

    var codexThreadLabel: String {
        guard selected?.provider == "codex" else { return L10n.text("Codex не выбран") }
        guard !codexThreadStatus.isNull else { return L10n.text("Статус не проверен") }
        guard codexThreadStatus["workspace_matches"].flag else { return L10n.text("Нужна новая сессия") }
        if codexThreadStatus["refresh_required"].flag { return L10n.text("Обновление инструкций при следующем сообщении") }
        guard codexThreadStatus["linked"].flag else { return L10n.text("Новая сессия при следующем сообщении") }
        let short = codexThreadStatus["thread_id_short"].text
        return short.isEmpty ? L10n.text("Продолжение сохранённой сессии") : L10n.format("Продолжение · \(short)")
    }

    func refreshCodexThreadStatus() async {
        guard !busy, let conversation = selected, conversation.provider == "codex" else {
            codexThreadStatus = .null
            return
        }
        let id = conversation.id
        let workspace = conversation.workspacePath
        loadingCodexThreadStatus = true
        defer { if selectedID == id { loadingCodexThreadStatus = false } }
        do {
            var params: [String: JSONValue] = ["conversation_id": .string(id.uuidString), "workspace_tools_version": .number(1)]
            if let workspace { params["workspace_root"] = .string(workspace) }
            let value = try await codexAccount(for: id).client.request("codex_thread_status", params)
            guard selectedID == id, selected?.workspacePath == workspace, selected?.provider == "codex", selected?.codexAccountID == conversation.codexAccountID else { return }
            guard value["schema"].text == "proto_mind.native_codex_threads.v1",
                  !value["linked"].isNull, !value["workspace_matches"].isNull else {
                throw NativeError.message(L10n.text("Не удалось проверить локальную связь с сессией Codex."))
            }
            codexThreadStatus = value
        } catch {
            guard selectedID == id else { return }
            codexThreadStatus = .null
            report(error)
        }
    }

    func resetCodexThread() async {
        guard !busy, !client.turnOutstanding, let id = selectedID, selected?.provider == "codex" else { return }
        discardAgentGrants(for: id)
        do {
            let value = try await client.request("codex_thread_reset", [
                "conversation_id": .string(id.uuidString),
                "confirmation": .string("START NEW CODEX SESSION"),
            ])
            guard value["schema"].text == "proto_mind.native_codex_thread_reset.v1",
                  value["no_provider_call"].flag, value["provider_history_deleted"] == .bool(false) else {
                throw NativeError.message(L10n.text("Сброс сессии Codex не прошёл локальную проверку."))
            }
            modelSelectionNotice = value["notice"].text
            codexThreadStatus = .null
            await refreshCodexThreadStatus()
        } catch { report(error) }
    }

    func setComposer(_ value: String, preservingContinuation: Bool = false) {
        if !preservingContinuation, let index = conversations.firstIndex(where: { $0.id == selectedID }) {
            conversations[index].draftContinuation = nil
        }
        composer = value
        composerRevision += 1
    }

    func renameConversation(_ id: UUID, title: String) {
        guard !operationBusy, let index = conversations.firstIndex(where: { $0.id == id }) else { return }
        let name = title.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !name.isEmpty, name.count <= 120 else { report(NativeError.message(L10n.text("Название должно содержать от 1 до 120 символов."))); return }
        conversations[index].title = name
        persist()
    }

    func archiveConversation(_ id: UUID, archived: Bool) {
        guard !operationBusy, !isRunning(id), let index = conversations.firstIndex(where: { $0.id == id }) else { return }
        conversations[index].archived = archived
        if archived && selectedID == id {
            if let next = conversations.first(where: { !$0.archived }) { select(next.id) }
            else { newConversation() }
        } else if !archived && selectedID == id {
            showArchived = false
        }
        persist()
    }

    func restoreComposer() {
        restoringDraft = true
        composer = selected?.draft ?? ""
        composerRevision += 1
        restoringDraft = false
    }

    func draftChanged() {
        guard !initializing, !restoringDraft, let index = conversations.firstIndex(where: { $0.id == selectedID }) else { return }
        conversations[index].draft = composer
        if composer.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty { conversations[index].draftContinuation = nil }
        dirtyDraft = true
        historyPersistence.hasUnsavedChanges = true
        draftSave?.cancel()
        draftSave = Task { [weak self] in
            do { try await Task.sleep(nanoseconds: 500_000_000) }
            catch { return }
            self?.flushDraft()
        }
    }

    func flushDraft() { if dirtyDraft { persist() } }

}
