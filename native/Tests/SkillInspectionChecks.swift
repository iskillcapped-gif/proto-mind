import AppKit
import Foundation
import SwiftUI

extension NativeChecks {
    @MainActor
    static func skillInspection(app: AppModel, item: LibraryItem, project: URL, state: URL) async throws {
        let before = try fileBytes(project), privateBefore = try fileBytes(state)
        let messages = app.messages, draft = app.composer, conversation = app.selectedID
        await app.openSkillInspection(item)
        guard let model = app.skillInspection, let report = model.report else {
            throw NativeError.message(app.skillInspection?.error ?? "No skill inspection")
        }
        try check(report.lifecycle?.state == .activeVerified && report.lifecycle?.storedStatusTitle == "Активен" && report.transitions.count == 1 && report.transitions[0].kind == "apply",
                  "Native skill inspection recovers verified durable apply evidence")
        try check(report.outcome?.status == "UNAVAILABLE" && report.outcome?.pilotAvailable == false && !report.historyComplete,
                  "Restart does not invent skill outcome events or complete lifecycle history")
        try check(report.skillStoreScope == "global_legacy_stores" && !report.projectIsolationEnforced,
                  "Skill evidence explicitly discloses global library scope")
        let view = NSHostingController(rootView: SkillInspectionView(model: model))
        let fitted = view.sizeThatFits(in: CGSize(width: 860, height: 730))
        try check(fitted.width <= 851 && fitted.height <= 721 && fitted.height >= 600,
                  "Skill inspection is a bounded scrollable Native sheet")
        let raw = try await app.client.request("skill_inspection", model.selection.parameters)
        guard case .object(let original) = raw else { throw NativeError.message("No inspection fixture") }
        for key in ["store_mutation_performed", "model_call_performed", "network_call_performed", "retrieval_performed",
                    "consent_state_changed", "context_injection_changed", "permissions_changed", "automatic_action", "history_complete",
                    "project_isolation_enforced", "execute"] {
            var unsafe = original; unsafe[key] = .bool(true)
            try inspectionRefused(.object(unsafe), selection: model.selection, message: "Inspection rejects widened \(key)")
        }
        var wrong = original; wrong["conversation_id"] = .string(UUID().uuidString)
        try inspectionRefused(.object(wrong), selection: model.selection, message: "Inspection cannot cross selected conversation")
        wrong = original; wrong["skill_id"] = .string("another-skill")
        try inspectionRefused(.object(wrong), selection: model.selection, message: "Inspection cannot substitute another skill")
        wrong = original; wrong["workspace_path"] = .string(project.deletingLastPathComponent().path)
        try inspectionRefused(.object(wrong), selection: model.selection, message: "Inspection cannot cross selected workspace")
        if case .object(var outcome) = original["outcome"] {
            outcome["automatic_decision_allowed"] = .bool(true)
            wrong = original; wrong["outcome"] = .object(outcome)
            try inspectionRefused(.object(wrong), selection: model.selection, message: "Outcome cannot imply automatic lifecycle decisions")
            outcome["automatic_decision_allowed"] = .bool(false)
            outcome["status"] = .string("SUCCESS_CANDIDATE")
            wrong["outcome"] = .object(outcome)
            try inspectionRefused(.object(wrong), selection: model.selection, message: "Empty outcome cannot be relabeled as success")
        }
        if case .object(var lifecycle) = original["lifecycle"] {
            lifecycle["executable"] = .bool(true)
            wrong = original; wrong["lifecycle"] = .object(lifecycle)
            try inspectionRefused(.object(wrong), selection: model.selection, message: "Verified state cannot claim executable capability")
        }
        await model.refresh()
        try check(model.report?.lifecycle?.state == .activeVerified && model.error == nil,
                  "Read-only skill evidence can be refreshed")
        try check(try fileBytes(project) == before && fileBytes(state) == privateBefore && app.messages == messages && app.composer == draft,
                  "Skill inspection and refresh preserve core/private bytes, chat and draft")
        app.busy = true
        await app.openSkillInspection(item)
        try check(app.skillInspection?.id == model.id, "Skill inspection waits for a foreground turn instead of competing with it")
        app.busy = false
        await model.openSource()
        try check(app.skillInspection == nil && app.section == .memory && app.libraryDetail?.item?.recordId == report.lifecycle?.sourceLessonId,
                  "Skill inspection can navigate to the exact source lesson without a command")

        app.selectedID = nil
        await app.openSkillInspection(item)
        try check(app.skillInspection?.report?.lifecycle?.state == .activeVerified && app.skillInspection?.report?.conversationId == "",
                  "Durable skill inspection works even without a selected conversation")
        app.skillInspection?.close(); app.selectedID = conversation
        var missing = item; missing.recordId = "missing-skill"
        await app.openSkillInspection(missing)
        try check(app.skillInspection?.report?.status == "NOT_FOUND" && app.skillInspection?.report?.lifecycle == nil,
                  "Deleted or missing skill is reported without a fallback record")
        app.skillInspection?.close()
        try check(try fileBytes(project) == before && fileBytes(state) == privateBefore && !app.cloudConsent && !app.fullAccessEnabled,
                  "Evidence navigation creates no files, tool grants, cloud calls or process capture")
    }

    static func inspectionRefused(_ value: JSONValue, selection: NativeSkillInspectionSelection, message: String) throws {
        var refused = false
        do { _ = try NativeSkillInspection.decode(value, selection: selection) } catch { refused = true }
        try check(refused, message)
    }
}
