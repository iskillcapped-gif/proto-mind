import Foundation
import SwiftUI

@MainActor
final class SkillOutcomeModel: ObservableObject, Identifiable {
    let id = UUID()
    unowned let app: AppModel
    let item: LibraryItem
    let scope: NativeSkillInspectionSelection
    @Published var outcome = "success" { didSet { invalidate() } }
    @Published var evidence = "" { didSet { invalidate() } }
    @Published private(set) var report: NativeSkillOutcomeReview?
    @Published private(set) var preview: NativeSkillOutcomePreview?
    @Published private(set) var result: NativeSkillOutcomeResult?
    @Published private(set) var error: String?
    @Published private(set) var loading = false
    @Published private(set) var committing = false
    private var requestID = UUID()
    private var pendingSelection: NativeSkillOutcomeSelection?

    init(app: AppModel, item: LibraryItem, scope: NativeSkillInspectionSelection) { self.app = app; self.item = item; self.scope = scope }
    var selection: NativeSkillOutcomeSelection { NativeSkillOutcomeSelection(scope: scope, outcome: outcome, evidence: evidence) }
    var current: Bool {
        app.skillOutcome?.id == id && app.selectedID == scope.conversationID &&
        app.selected?.workspacePath == scope.workspace && app.selected?.archived == false
    }
    var locked: Bool { app.busy || app.client.turnOutstanding || loading || !current }
    func invalidate() { preview = nil; pendingSelection = nil }

    func refresh(clearError: Bool = true) async {
        guard !locked else { return }
        let request = UUID(); requestID = request; loading = true; invalidate()
        if clearError { error = nil }
        defer { if requestID == request { loading = false } }
        do {
            let raw = try await app.client.request("skill_outcome_review", scope.parameters)
            let report = try NativeSkillOutcomeReview.decode(raw, scope: scope)
            guard current, requestID == request else { return }
            self.report = report
        } catch {
            guard current, requestID == request else { return }
            report = nil; self.error = error.localizedDescription
        }
    }

    func prepare() async {
        guard !locked, selection.complete else { return }
        let selected = selection, request = UUID(); requestID = request; loading = true; error = nil; invalidate()
        defer { if requestID == request { loading = false } }
        do {
            let raw = try await app.client.request("skill_outcome_preview", selected.parameters)
            let preview = try NativeSkillOutcomePreview.decode(raw, selection: selected)
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
            params["acknowledge_manual_only"] = .bool(acknowledgement)
            let raw = try await app.client.request("skill_outcome_confirm", params)
            let result = try NativeSkillOutcomeResult.decode(raw, selection: selected, preview: preview)
            if current, selection == selected {
                self.result = result
                app.status = "Ручной результат записан до перезапуска ядра; навык не запускался"
            }
        } catch {
            if current { self.error = "\(error.localizedDescription) Автоповтора нет. Обновите квитанции перед следующей попыткой." }
        }
        app.busy = false; committing = false
        if current { await refresh(clearError: false) }
    }

    func close() {
        guard !committing else { return }
        requestID = UUID(); invalidate()
        if app.skillOutcome?.id == id { app.skillOutcome = nil }
    }

    func openEvidence() async {
        guard !locked else { return }
        close(); await app.openSkillInspection(item)
    }

    func openConsentHelp() {
        guard !locked else { return }
        close(); app.openMemoryWorkshop()
    }
}

extension AppModel {
    func openSkillOutcome(_ item: LibraryItem) async {
        guard !busy, !client.turnOutstanding, item.store == "skills", let conversation = selected, !conversation.archived else { return }
        let scope = NativeSkillInspectionSelection(conversationID: conversation.id, skillID: item.recordId,
                                                   workspace: conversation.workspacePath, expectedSHA256: item.storeSha256)
        let model = SkillOutcomeModel(app: self, item: item, scope: scope)
        skillOutcome = model
        await model.refresh()
    }
}
