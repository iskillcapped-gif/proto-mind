import Foundation
import SwiftUI

@MainActor
final class SkillAuthoringModel: ObservableObject, Identifiable {
    let id = UUID()
    unowned let app: AppModel
    let conversationID: UUID
    let lessonID: String
    let workspace: String?
    @Published var draft = NativeSkillDraft() { didSet { invalidateConfirmation() } }
    @Published private(set) var report: NativeSkillReview?
    @Published private(set) var preview: NativeSkillPreview?
    @Published private(set) var result: NativeSkillResult?
    @Published private(set) var error: String?
    @Published private(set) var loading = false
    @Published private(set) var committing = false
    private var requestID = UUID()
    private var pendingSelection: NativeSkillSelection?
    private var loadedFields = false

    init(app: AppModel, conversationID: UUID, lessonID: String, workspace: String?) {
        self.app = app; self.conversationID = conversationID; self.lessonID = lessonID; self.workspace = workspace
    }

    var selection: NativeSkillSelection {
        NativeSkillSelection(conversationID: conversationID, lessonID: lessonID, workspace: workspace, fields: draft.fields)
    }
    var current: Bool {
        app.selectedID == conversationID && app.selected?.workspacePath == workspace && app.selected?.archived == false
    }
    var locked: Bool { app.busy || app.client.turnOutstanding || loading || !current }

    func invalidateConfirmation() { preview = nil; pendingSelection = nil }

    func refresh(clearError: Bool = true) async {
        guard !locked else { return }
        let request = UUID(), selected = selection
        requestID = request; loading = true
        invalidateConfirmation()
        if clearError { error = nil }
        defer { if requestID == request { loading = false } }
        do {
            let raw = try await app.client.request("skill_authoring_review", selected.parameters)
            let value = try NativeSkillReview.decode(raw, selection: selected)
            guard requestID == request, current, selection == selected else { return }
            report = value
            if !loadedFields || value.authoringReceipt != nil {
                draft = NativeSkillDraft(value.fields)
                loadedFields = true
            }
        } catch {
            guard requestID == request, current else { return }
            report = nil; self.error = error.localizedDescription
        }
    }

    func prepare(_ operation: NativeSkillOperation) async {
        guard !locked else { return }
        let selected = selection, request = UUID()
        requestID = request; loading = true; error = nil
        invalidateConfirmation()
        defer { if requestID == request { loading = false } }
        do {
            var params = selected.parameters
            params["operation"] = .string(operation.rawValue)
            let raw = try await app.client.request("skill_authoring_preview", params)
            let value = try NativeSkillPreview.decode(raw, selection: selected, operation: operation)
            guard requestID == request, current, selection == selected else { return }
            preview = value; pendingSelection = selected
        } catch {
            guard requestID == request, current else { return }
            self.error = error.localizedDescription
        }
    }

    func confirm(token: String, acknowledgeGlobal: Bool) async {
        guard !locked, let selected = pendingSelection, selected == selection,
              let preview, preview.accepts(token: token, acknowledgeGlobal: acknowledgeGlobal) else { return }
        app.busy = true; committing = true; error = nil
        invalidateConfirmation()
        do {
            var params = selected.parameters
            params["operation"] = .string(preview.operation.rawValue)
            params["preview_fingerprint"] = .string(preview.previewFingerprint)
            params["confirmation_token"] = .string(token)
            params["acknowledge_global_skills"] = .bool(acknowledgeGlobal)
            let raw = try await app.client.request("skill_authoring_confirm", params)
            let value = try NativeSkillResult.decode(raw, selection: selected, operation: preview.operation)
            if current, selection == selected {
                result = value
                app.status = value.skillMutationPerformed ? "Один навык сохранён и проверен" : "Описание подтверждено; навык ещё не сохранён"
            }
        } catch {
            if current { self.error = "\(error.localizedDescription) Автоповтора нет. Проверьте карточку и receipt перед следующим действием." }
        }
        app.busy = false; committing = false
        if current { await refresh(clearError: false) }
    }

    func close() {
        guard !committing else { return }
        requestID = UUID(); invalidateConfirmation()
        if app.skillAuthoring?.id == id { app.skillAuthoring = nil }
    }

    func openSavedSkill() async {
        guard !locked, let receipt = report?.applyReceipt else { return }
        close()
        app.section = .skills; app.libraryQuery = receipt.recordId; app.libraryFilter = .all
        await app.loadLibraryPage()
        guard let item = app.libraryPage?.items.first(where: { $0.recordId == receipt.recordId }) else { return }
        await app.inspectLibrary(item)
    }
}

extension AppModel {
    func openSkillAuthoring(lessonID: String) async {
        guard !busy, !client.turnOutstanding, let conversation = selected, !conversation.archived else { return }
        let review = SkillAuthoringModel(app: self, conversationID: conversation.id,
                                        lessonID: lessonID, workspace: conversation.workspacePath)
        skillAuthoring = review
        await review.refresh()
    }
}
