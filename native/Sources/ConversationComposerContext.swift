import Foundation

@MainActor
struct ConversationComposerContext {
    let app: AppModel
    let id: UUID?
    var conversation: Conversation? { app.conversations.first { $0.id == id } }
    var state: ConversationExecution? { id.flatMap { app.executions[$0] } }
    var busy: Bool { app.operationBusy || state?.running == true }
    var draft: String { id == app.selectedID ? app.composer : conversation?.draft ?? "" }
    var hasAttachments: Bool { conversation.map { !$0.pendingFiles.isEmpty || !$0.pendingImages.isEmpty || !$0.pendingPDFs.isEmpty } ?? false }
    var hasInput: Bool { !draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || hasAttachments }
    var canUpdate: Bool { state.map(app.canUpdateTask) == true }
    var showsStop: Bool { state?.running == true && (!hasInput || conversation?.provider != "codex") }
    var canEditAttachments: Bool {
        conversation?.archived == false && !app.operationBusy && (canUpdate || (state?.running != true && state?.client.turnOutstanding != true))
    }
    var canSend: Bool {
        hasInput && conversation?.archived == false && !app.operationBusy && (!busy || canUpdate)
            && !app.historyPersistence.blocksSubmission && !app.store.writeBlocked
            && !app.loadingDroppedAttachments && !app.loadingImagePreview && !app.loadingPDFPreview
            && app.imagePreview == nil && app.pdfPreview == nil && app.attachmentDropPreview == nil
    }
    var fullAccess: Bool { conversation.map(app.hasAgentAccessSelection) == true }
    var models: [CodexModelOption] { id.map { app.codexModels(for: $0) } ?? [] }
    var selectedModel: CodexModelOption? {
        guard let conversation else { return nil }
        return conversation.model.isEmpty ? models.first(where: \.isDefault) : models.first { $0.id == conversation.model }
    }
    var modelLabel: String { selectedModel?.displayName ?? (conversation?.model.isEmpty == false ? conversation!.model : "Codex") }
    var effortLabel: String {
        let value = conversation?.reasoningEffort ?? ""
        return value.isEmpty ? selectedModel?.defaultEffort?.title ?? L10n.text("Авто") : CodexReasoningEffort(rawValue: value)?.title ?? value
    }
    var providerLabel: String {
        switch conversation?.provider {
        case "api": return L10n.text("Модель через API")
        case "codex": return L10n.text("Codex · облако")
        case "mock": return L10n.text("Тестовый режим")
        default: return L10n.text("Ollama · локально")
        }
    }
    var localLabel: String { conversation?.provider == "mock" || conversation?.model.isEmpty != false ? providerLabel : conversation!.model }
    var warning: String? {
        guard conversation?.provider == "codex", !models.isEmpty else { return nil }
        if conversation?.model.isEmpty == false && selectedModel == nil { return L10n.text("Сохранённая модель недоступна в текущем каталоге. Выберите другую: автоматической подмены не будет.") }
        if let effort = conversation?.reasoningEffort, !effort.isEmpty, selectedModel?.efforts.contains(where: { $0.rawValue == effort }) != true {
            return L10n.text("Сохранённое усилие больше не поддерживается. Выберите доступное или сбросьте настройки.")
        }
        return nil
    }
    func setModel(_ value: String) {
        guard let id else { return }
        if id == app.selectedID { app.setModel(value) } else { app.configureConversation(id, model: value) }
    }
    func setEffort(_ value: String) {
        guard let id else { return }
        if id == app.selectedID { app.setReasoningEffort(value) } else { app.configureConversation(id, effort: value) }
    }
    func setDraft(_ value: String) { if let id { app.setConversationDraft(value, id: id) } }
    func set(_ key: WritableKeyPath<Conversation, Bool>, _ value: Bool) {
        guard !busy, let index = app.conversations.firstIndex(where: { $0.id == id }), !app.conversations[index].archived else { return }
        app.conversations[index][keyPath: key] = value
        app.invalidateContextPreview(); app.persist()
    }
}
