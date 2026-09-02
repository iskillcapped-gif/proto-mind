import Foundation
import SwiftUI

@MainActor
final class SkillDecisionModel: ObservableObject, Identifiable {
    let id = UUID()
    unowned let app: AppModel
    let scope: NativeSkillInspectionSelection
    @Published var choice: NativeSkillDecision? { didSet { invalidate() } }
    @Published private(set) var report: NativeSkillDecisionReview?
    @Published private(set) var preview: NativeSkillDecisionPreview?
    @Published private(set) var result: NativeSkillDecisionResult?
    @Published private(set) var error: String?
    @Published private(set) var loading = false
    @Published private(set) var committing = false
    private var requestID = UUID()
    private var pendingSelection: NativeSkillDecisionSelection?

    init(app: AppModel, scope: NativeSkillInspectionSelection) { self.app = app; self.scope = scope }
    var selection: NativeSkillDecisionSelection? { choice.map { NativeSkillDecisionSelection(scope: scope, decision: $0) } }
    var current: Bool {
        app.skillDecision?.id == id && app.selectedID == scope.conversationID &&
        app.selected?.workspacePath == scope.workspace && app.selected?.archived == false
    }
    var locked: Bool { app.busy || app.client.turnOutstanding || loading || !current }
    var canPrepare: Bool { !locked && report?.choices.contains(where: { $0.decision == choice && $0.allowed }) == true }
    func invalidate() { preview = nil; pendingSelection = nil }

    func refresh(clearError: Bool = true) async {
        guard !locked else { return }
        let request = UUID(); requestID = request; loading = true; choice = nil
        if clearError { error = nil }
        defer { if requestID == request { loading = false } }
        do {
            let raw = try await app.client.request("skill_decision_review", scope.parameters)
            let report = try NativeSkillDecisionReview.decode(raw, scope: scope)
            guard current, requestID == request else { return }
            self.report = report
        } catch {
            guard current, requestID == request else { return }
            report = nil; self.error = error.localizedDescription
        }
    }

    func prepare() async {
        guard canPrepare, let selected = selection else { return }
        let request = UUID(); requestID = request; loading = true; error = nil; invalidate()
        defer { if requestID == request { loading = false } }
        do {
            let raw = try await app.client.request("skill_decision_preview", selected.parameters)
            let preview = try NativeSkillDecisionPreview.decode(raw, selection: selected)
            guard current, requestID == request, selection == selected else { return }
            self.preview = preview; pendingSelection = selected
        } catch {
            guard current, requestID == request else { return }
            self.error = error.localizedDescription
        }
    }

    func confirm(token: String, acknowledgement: Bool) async {
        guard !locked, let selected = pendingSelection, selected == selection,
              let preview, preview.accepts(token: token, acknowledgement: acknowledgement) else { return }
        app.busy = true; committing = true; error = nil; invalidate()
        do {
            var params = selected.parameters
            params["preview_fingerprint"] = .string(preview.previewFingerprint)
            params["confirmation_token"] = .string(token)
            params["acknowledge_decision_only"] = .bool(acknowledgement)
            let raw = try await app.client.request("skill_decision_confirm", params)
            let result = try NativeSkillDecisionResult.decode(raw, selection: selected, preview: preview)
            if current, selection == selected {
                self.result = result
                app.status = "Решение записано до перезапуска ядра; навык не изменён"
            }
        } catch {
            if current { self.error = "\(error.localizedDescription) Автоповтора нет. Обновите квитанцию перед следующей попыткой." }
        }
        app.busy = false; committing = false
        if current { await refresh(clearError: false) }
    }

    func close() {
        guard !committing else { return }
        requestID = UUID(); invalidate()
        if app.skillDecision?.id == id { app.skillDecision = nil }
    }

    func openEvidence() async {
        guard !locked else { return }
        close()
        let inspector = SkillInspectionModel(app: app, selection: scope)
        app.skillInspection = inspector
        await inspector.refresh()
    }

    func openLifecycleApply() async {
        guard !locked, let receipt = report?.receipt else { return }
        let selection = NativeSkillLifecycleSelection(scope: scope, decisionReceiptID: receipt.id, decision: receipt.evidence.decision)
        close()
        await app.openSkillLifecycleApply(selection)
    }
}

extension AppModel {
    func openSkillDecision(_ scope: NativeSkillInspectionSelection) async {
        guard !busy, !client.turnOutstanding, let conversation = selected, !conversation.archived,
              conversation.id == scope.conversationID, conversation.workspacePath == scope.workspace else { return }
        let model = SkillDecisionModel(app: self, scope: scope)
        skillDecision = model
        await model.refresh()
    }
}
