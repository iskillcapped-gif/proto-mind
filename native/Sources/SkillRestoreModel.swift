import Foundation
import SwiftUI

@MainActor
final class SkillRestoreModel: ObservableObject, Identifiable {
    let id = UUID()
    unowned let app: AppModel
    let selection: NativeSkillInspectionSelection
    @Published private(set) var report: NativeSkillRestoreReview?
    @Published private(set) var preview: NativeSkillRestorePreview?
    @Published private(set) var result: NativeSkillRestoreReceipt?
    @Published private(set) var error: String?
    @Published private(set) var loading = false
    @Published private(set) var committing = false
    private var requestID = UUID()

    init(app: AppModel, selection: NativeSkillInspectionSelection) { self.app = app; self.selection = selection }
    var current: Bool { app.skillRestore?.id == id && app.selectedID == selection.conversationID && app.selected?.workspacePath == selection.workspace && app.selected?.archived == false }
    var locked: Bool { app.busy || app.client.turnOutstanding || loading || !current }
    var canPrepare: Bool { !locked && report?.ready == true }
    func invalidate() { preview = nil }

    func refresh(clearError: Bool = true) async {
        guard !locked else { return }
        let request = UUID(); requestID = request; loading = true; invalidate()
        if clearError { error = nil }
        defer { if requestID == request { loading = false } }
        do {
            let raw = try await app.client.request("skill_restore_review", selection.parameters)
            let report = try NativeSkillRestoreReview.decode(raw, selection: selection)
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
            let raw = try await app.client.request("skill_restore_preview", selection.parameters)
            let preview = try NativeSkillRestorePreview.decode(raw, selection: selection)
            guard current, requestID == request else { return }
            self.preview = preview
        } catch {
            if current, requestID == request { self.error = error.localizedDescription }
        }
    }
    func confirm(token: String, acknowledgement: Bool) async {
        guard !locked, let preview, preview.accepts(token, acknowledgement: acknowledgement) else { return }
        app.busy = true; committing = true; error = nil; invalidate()
        do {
            var params = selection.parameters
            params["preview_fingerprint"] = .string(preview.fingerprint)
            params["confirmation_token"] = .string(token); params["acknowledge_global_skills"] = .bool(acknowledgement)
            let raw = try await app.client.request("skill_restore_confirm", params)
            let receipt = try decodeSkillRestoreResult(raw, selection: selection, preview: preview)
            if current {
                result = receipt
                app.status = receipt.verification == "VERIFIED" && receipt.current ? "Навык восстановлен; переход проверен, процедура не запускалась" : "Проверьте состояние навыка и квитанцию восстановления"
            }
        } catch {
            if current { self.error = "\(error.localizedDescription) Не повторяйте автоматически; проверьте текущую запись." }
        }
        app.busy = false; committing = false
        if current { await refresh(clearError: false) }
    }
    func close() {
        guard !committing else { return }
        requestID = UUID(); invalidate()
        if app.skillRestore?.id == id { app.skillRestore = nil }
    }
    func openEvidence() async {
        guard !locked else { return }
        close()
        let selection = NativeSkillInspectionSelection(conversationID: selection.conversationID, skillID: selection.skillID, workspace: selection.workspace, expectedSHA256: "")
        let inspector = SkillInspectionModel(app: app, selection: selection)
        app.skillInspection = inspector; await inspector.refresh()
    }
    func openSkill() async {
        guard !locked else { return }
        close(); app.section = .skills; app.libraryQuery = selection.skillID; app.libraryFilter = .all
        await app.loadLibraryPage()
        if let item = app.libraryPage?.items.first(where: { $0.recordId == selection.skillID }) { await app.inspectLibrary(item) }
    }
}

extension AppModel {
    func openSkillRestore(_ selection: NativeSkillInspectionSelection) async {
        guard !busy, !client.turnOutstanding, let conversation = selected, !conversation.archived,
              conversation.id == selection.conversationID, conversation.workspacePath == selection.workspace else { return }
        let model = SkillRestoreModel(app: self, selection: selection); skillRestore = model; await model.refresh()
    }
}
