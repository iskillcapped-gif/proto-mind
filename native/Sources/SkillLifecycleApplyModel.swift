import Foundation
import SwiftUI

@MainActor
final class SkillLifecycleApplyModel: ObservableObject, Identifiable {
    let id = UUID()
    unowned let app: AppModel
    let selection: NativeSkillLifecycleSelection
    @Published private(set) var report: NativeSkillLifecycleApplyReview?
    @Published private(set) var preview: NativeSkillLifecycleApplyPreview?
    @Published private(set) var result: NativeSkillLifecycleApplyResult?
    @Published private(set) var error: String?
    @Published private(set) var loading = false
    @Published private(set) var committing = false
    private var requestID = UUID()

    init(app: AppModel, selection: NativeSkillLifecycleSelection) { self.app = app; self.selection = selection }
    var current: Bool {
        app.skillLifecycleApply?.id == id && app.selectedID == selection.scope.conversationID &&
        app.selected?.workspacePath == selection.scope.workspace && app.selected?.archived == false
    }
    var locked: Bool { app.busy || app.client.turnOutstanding || loading || !current }
    var canPrepare: Bool { !locked && report?.canApply == true }
    func invalidate() { preview = nil }

    func refresh(clearError: Bool = true) async {
        guard !locked else { return }
        let request = UUID(); requestID = request; loading = true; invalidate()
        if clearError { error = nil }
        defer { if requestID == request { loading = false } }
        do {
            let raw = try await app.client.request("skill_lifecycle_review", selection.parameters)
            let report = try NativeSkillLifecycleApplyReview.decode(raw, selection: selection)
            guard current, requestID == request else { return }
            self.report = report
        } catch {
            guard current, requestID == request else { return }
            report = nil; self.error = error.localizedDescription
        }
    }

    func prepare() async {
        guard canPrepare else { return }
        let request = UUID(); requestID = request; loading = true; error = nil; invalidate()
        defer { if requestID == request { loading = false } }
        do {
            let raw = try await app.client.request("skill_lifecycle_preview", selection.parameters)
            let preview = try NativeSkillLifecycleApplyPreview.decode(raw, selection: selection)
            guard current, requestID == request else { return }
            self.preview = preview
        } catch {
            guard current, requestID == request else { return }
            self.error = error.localizedDescription
        }
    }

    func confirm(token: String, acknowledgement: Bool) async {
        guard !locked, let preview, preview.accepts(token: token, acknowledgement: acknowledgement) else { return }
        app.busy = true; committing = true; error = nil; invalidate()
        do {
            var params = selection.parameters
            params["preview_fingerprint"] = .string(preview.previewFingerprint)
            params["confirmation_token"] = .string(token)
            params["acknowledge_global_skills"] = .bool(acknowledgement)
            let raw = try await app.client.request("skill_lifecycle_confirm", params)
            let result = try NativeSkillLifecycleApplyResult.decode(raw, selection: selection, preview: preview)
            if current {
                self.result = result
                app.status = result.receipt.verificationStatus == "VERIFIED" && result.receipt.evidenceState == "CURRENT"
                    ? (result.decision == .archive ? "Один навык архивирован; причина и состояние проверены" : "Навык оставлен без изменений; проверка записана до перезапуска")
                    : "Применение завершилось; проверьте актуальное состояние навыка и квитанцию"
            }
        } catch {
            if current { self.error = "\(error.localizedDescription) Не повторяйте применение автоматически. Откройте навык и проверьте квитанцию." }
        }
        app.busy = false; committing = false
        if current { await refresh(clearError: false) }
    }

    func close() {
        guard !committing else { return }
        requestID = UUID(); invalidate()
        if app.skillLifecycleApply?.id == id { app.skillLifecycleApply = nil }
    }

    func openEvidence() async {
        guard !locked else { return }
        close()
        let inspector = SkillInspectionModel(app: app, selection: selection.scope)
        app.skillInspection = inspector
        await inspector.refresh()
    }

    func openSkill() async {
        guard !locked else { return }
        close()
        app.section = .skills; app.libraryQuery = selection.scope.skillID; app.libraryFilter = .all
        await app.loadLibraryPage()
        if let item = app.libraryPage?.items.first(where: { $0.recordId == selection.scope.skillID }) { await app.inspectLibrary(item) }
    }
}

extension AppModel {
    func openSkillLifecycleApply(_ selection: NativeSkillLifecycleSelection) async {
        guard !busy, !client.turnOutstanding, let conversation = selected, !conversation.archived,
              conversation.id == selection.scope.conversationID, conversation.workspacePath == selection.scope.workspace else { return }
        let model = SkillLifecycleApplyModel(app: self, selection: selection)
        skillLifecycleApply = model
        await model.refresh()
    }
}
