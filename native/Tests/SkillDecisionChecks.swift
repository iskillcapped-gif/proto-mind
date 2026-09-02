import AppKit
import Foundation
import SwiftUI

extension NativeChecks {
    @MainActor
    static func skillDecision(app: AppModel, item: LibraryItem, project: URL, state: URL) async throws {
        let before = try fileBytes(project), privateBefore = try fileBytes(state), messages = app.messages, draft = app.composer
        await app.openSkillInspection(item)
        guard let inspector = app.skillInspection else { throw NativeError.message("Missing inspection entry for decision") }
        await inspector.openDecision()
        guard let model = app.skillDecision, let report = model.report else {
            throw NativeError.message(app.skillDecision?.error ?? "Missing decision review")
        }
        try check(app.skillInspection == nil && report.outcomeStatus == "MIXED_EVIDENCE" && model.choice == nil && !model.canPrepare,
                  "Inspector opens an exact decision review without preselecting or recording a choice")
        try check(report.choices.filter(\.allowed).map(\.decision) == [.revise, .archive] && report.receipt == nil,
                  "Mixed manual outcomes permit revise/archive, never keep or automatic application")
        let hosting = NSHostingController(rootView: SkillDecisionView(model: model))
        let fitted = hosting.sizeThatFits(in: CGSize(width: 860, height: 730))
        try check(fitted.width <= 851 && fitted.height <= 721 && fitted.height >= 600,
                  "Decision choices and receipts remain in a bounded scrollable sheet")
        let rawReview = try await app.client.request("skill_decision_review", model.scope.parameters)
        guard case .object(let reviewData) = rawReview else { throw NativeError.message("Missing decision contract") }
        for field in ["store_mutation_performed", "model_call_performed", "network_call_performed", "retrieval_performed",
                      "context_injection_changed", "permissions_changed", "consent_state_changed", "automatic_promotion",
                      "session_log_mutation_performed", "skill_mutation_performed", "memory_mutation_performed",
                      "experience_mutation_performed", "lifecycle_apply_performed", "future_apply_ready", "execute"] {
            var invalid = reviewData; invalid[field] = .bool(true)
            try outcomeRefused("Decision review rejects widened \(field)") {
                _ = try NativeSkillDecisionReview.decode(.object(invalid), scope: model.scope)
            }
        }
        for field in ["conversation_id", "skill_id", "workspace_path"] {
            var invalid = reviewData; invalid[field] = .string(field == "workspace_path" ? project.deletingLastPathComponent().path : UUID().uuidString)
            try outcomeRefused("Decision review binds exact \(field)") {
                _ = try NativeSkillDecisionReview.decode(.object(invalid), scope: model.scope)
            }
        }
        model.choice = .keep; await model.prepare()
        try check(model.preview == nil && !model.canPrepare, "Native cannot prepare a choice outside the current core evidence rules")
        model.choice = .revise; await model.prepare()
        guard let revise = model.preview, revise.ready else { throw NativeError.message(model.error ?? "No revise preview") }
        await model.confirm(token: "WRONG", acknowledgement: true)
        await model.confirm(token: revise.confirmationToken, acknowledgement: false)
        try check(model.report?.receipt == nil && model.preview != nil, "Decision needs both exact token and decision-only acknowledgement")
        model.choice = .archive
        await model.confirm(token: revise.confirmationToken, acknowledgement: true)
        try check(model.preview == nil && model.report?.receipt == nil, "Changing a choice invalidates its pending confirmation")
        await model.prepare()
        await model.refresh()
        try check(model.choice == nil && model.preview == nil, "Refresh clears old decision choice, token and blueprint")
        model.choice = .archive; await model.prepare()
        guard let preview = model.preview, preview.ready, let selected = model.selection else { throw NativeError.message(model.error ?? "No archive choice preview") }
        let rawPreview = try await app.client.request("skill_decision_preview", selected.parameters)
        if case .object(let data) = rawPreview, case .object(let blueprint) = data["blueprint"] {
            for field in ["future_apply_ready", "skill_mutation_allowed", "procedure_execution_allowed", "persistence_allowed", "extra_operation"] {
                var unsafe = blueprint; unsafe[field] = .bool(true)
                var changed = data; changed["blueprint"] = .object(unsafe)
                try outcomeRefused("Decision blueprint rejects \(field)") {
                    _ = try NativeSkillDecisionPreview.decode(.object(changed), selection: selected)
                }
            }
            var changed = data; changed["confirmation_token"] = .string("CONFIRM-SKILL-ARCHIVE-WRONG")
            try outcomeRefused("Decision token must bind its exact blueprint hash") {
                _ = try NativeSkillDecisionPreview.decode(.object(changed), selection: selected)
            }
        }
        await model.confirm(token: preview.confirmationToken, acknowledgement: true)
        guard let result = model.result, let recorded = model.report?.receipt else { throw NativeError.message(model.error ?? "No decision receipt") }
        try check(result.eventsAppended == 0 && recorded.evidence.decision == .archive && recorded.verificationStatus == "VERIFIED" && recorded.evidenceState == "CURRENT",
                  "Exact Native choice records one core decision receipt without experience events or skill application")
        try check(model.report?.status == "RECORDED" && model.report?.decisionCount == 1 && model.report?.choices.allSatisfy({ !$0.allowed }) == true,
                  "One terminal decision prevents replacement and all alternative choices")
        try check(try fileBytes(project) == before && fileBytes(state) == privateBefore && app.messages == messages && app.composer == draft,
                  "Native decision confirmation preserves core/private files, conversation and draft")
        var replay = selected.parameters
        replay["preview_fingerprint"] = .string(preview.previewFingerprint)
        replay["confirmation_token"] = .string(preview.confirmationToken)
        replay["acknowledge_decision_only"] = .bool(true)
        var refused = false
        do { _ = try await app.client.request("skill_decision_confirm", replay) } catch { refused = true }
        try check(refused, "Core independently refuses terminal decision replay after a lost response")

        var rawReceipt = try await app.client.request("skill_decision_review", model.scope.parameters)
        if case .object(let data) = rawReceipt, case .object(let receipt) = data["receipt"] {
            for field in ["skill_mutation_performed", "memory_mutation_performed", "experience_mutation_performed",
                          "persistence_performed", "procedure_execution_performed", "future_apply_ready", "execute"] {
                var unsafe = receipt; unsafe[field] = .bool(true)
                var changed = data; changed["receipt"] = .object(unsafe)
                try outcomeRefused("Decision receipt rejects unsafe \(field)") {
                    _ = try NativeSkillDecisionReview.decode(.object(changed), scope: model.scope)
                }
            }
            var changed = data; changed["receipt"] = .object(receipt.merging(["decision_hash": .string(String(repeating: "0", count: 64))]) { _, new in new })
            try outcomeRefused("Decision receipt ID must match its decision hash") {
                _ = try NativeSkillDecisionReview.decode(.object(changed), scope: model.scope)
            }
        }
        await model.openEvidence()
        try check(app.skillDecision == nil && app.skillInspection?.report?.lifecycle?.status == "active",
                  "Archive recommendation leaves the real skill active and returns to inspection without applying")
        await app.skillInspection?.openDecision()
        guard let reopened = app.skillDecision else { throw NativeError.message("Missing reopened decision") }
        try check(reopened.report?.receipt?.id == recorded.id && reopened.choice == nil,
                  "Reopening finds the existing bounded decision, not a persisted or automatically selected draft")

        let outcome = NativeSkillOutcomeSelection(scope: reopened.scope, outcome: "failure", evidence: "A new synthetic manual result arrived after the decision.")
        let outcomePreview = try NativeSkillOutcomePreview.decode(try await app.client.request("skill_outcome_preview", outcome.parameters), selection: outcome)
        var capture = outcome.parameters
        capture["confirmation_token"] = .string(outcomePreview.confirmationToken)
        capture["preview_fingerprint"] = .string(outcomePreview.previewFingerprint)
        capture["acknowledge_manual_only"] = .bool(true)
        _ = try await app.client.request("skill_outcome_confirm", capture)
        await reopened.refresh()
        try check(reopened.report?.receipt?.id == recorded.id && reopened.report?.receipt?.evidenceState == "HISTORICAL" && !reopened.canPrepare,
                  "Later manual evidence marks the same decision historical without rewriting or reauthorizing it")
        rawReceipt = try await app.client.request("skill_decision_review", reopened.scope.parameters)
        try check(try NativeSkillDecisionReview.decode(rawReceipt, scope: reopened.scope).receipt?.verificationStatus == "VERIFIED",
                  "Historical is distinct from a corrupt receipt; its integrity still verifies")
        reopened.close()
        app.busy = true; await app.openSkillDecision(model.scope)
        try check(app.skillDecision == nil, "Decision UI does not compete with foreground execution")
        app.busy = false
        let conversation = app.selectedID; app.selectedID = nil
        await app.openSkillDecision(model.scope)
        try check(app.skillDecision == nil, "Decision UI never implicitly selects or creates a conversation")
        app.selectedID = conversation
        let restart = AppModel(configuration: app.client.configuration)
        defer { restart.client.shutdown() }
        await restart.openSkillDecision(model.scope)
        try check(restart.skillDecision?.report?.receipt == nil && restart.skillDecision?.report?.decisionCount == 0 &&
                  restart.skillDecision?.report?.status == "NOT_READY" && restart.skillDecision?.report?.sourceEligible == true,
                  "Restart loses process-only decisions and evidence, not the durable skill")
        restart.skillDecision?.close()
        try check(try fileBytes(project) == before && fileBytes(state) == privateBefore && !app.cloudConsent && !app.fullAccessEnabled,
                  "Decision workflow, receipt viewing and restart preserve files, consent and tool grants")
    }
}
