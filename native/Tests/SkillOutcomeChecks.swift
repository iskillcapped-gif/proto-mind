import AppKit
import Foundation
import SwiftUI

extension NativeChecks {
    @MainActor
    static func skillOutcome(app: AppModel, item: LibraryItem, project: URL, state: URL) async throws {
        try Data("{\"enabled\":false}\n".utf8).write(to: project.appendingPathComponent("proto_mind/data/context_injection.json"))
        let initial = try fileBytes(project), initialPrivate = try fileBytes(state), draft = app.composer, messages = app.messages
        await app.openSkillOutcome(item)
        guard let unopened = app.skillOutcome, let initialReport = unopened.report else {
            throw NativeError.message(app.skillOutcome?.error ?? "Missing manual skill outcome form")
        }
        try check(initialReport.sourceEligible && !initialReport.captureAvailable && initialReport.pilotState == "not_started",
                  "Skill outcome form requires separate existing session consent instead of enabling it: \(initialReport.reasons.joined(separator: "; "))")
        try check(try fileBytes(project) == initial && fileBytes(state) == initialPrivate && app.messages == messages && app.composer == draft,
                  "Opening a manual outcome form does not create pilot, stores, history or draft writes")
        unopened.openConsentHelp()
        try check(app.showMemoryWorkshop && app.skillOutcome == nil && app.composer == draft && app.messages == messages,
                  "Consent help only opens the existing Workshop without preparing or executing a command")
        app.showMemoryWorkshop = false

        // Explicit CLI consent is fixture setup; the Native outcome endpoints never create it.
        func consentCommand(_ text: String) async throws -> JSONValue {
            try await app.client.request("process", ["conversation_id": .string(app.selectedID!.uuidString),
                "text": .string(text), "confirmed_text": .string(text), "provider": .string("mock"), "persona_enabled": .bool(false)])
        }
        let consentPreview = try await consentCommand("/experience preview")
        guard let phrase = consentPreview["text"].text.components(separatedBy: "\n").first(where: { $0.hasPrefix("/experience consent ") }) else {
            throw NativeError.message("Missing manual outcome fixture consent")
        }
        _ = try await consentCommand(phrase)
        let before = try fileBytes(project), privateBefore = try fileBytes(state)
        await app.openSkillOutcome(item)
        guard let model = app.skillOutcome, model.report?.captureAvailable == true else {
            throw NativeError.message(app.skillOutcome?.error ?? app.skillOutcome?.report?.reasons.joined(separator: "; ") ?? "No capture availability")
        }
        let view = NSHostingController(rootView: SkillOutcomeView(model: model))
        let fitted = view.sizeThatFits(in: CGSize(width: 860, height: 730))
        try check(fitted.width <= 851 && fitted.height <= 721 && fitted.height >= 600,
                  "Manual outcome form stays inside a bounded scrollable Native sheet")
        let rawReview = try await app.client.request("skill_outcome_review", model.scope.parameters)
        guard case .object(let original) = rawReview else { throw NativeError.message("Missing outcome contract") }
        for field in ["store_mutation_performed", "model_call_performed", "network_call_performed", "retrieval_performed",
                      "context_injection_changed", "permissions_changed", "consent_state_changed", "automatic_promotion",
                      "session_log_mutation_performed", "skill_mutation_performed", "memory_mutation_performed", "project_isolation_enforced", "execute"] {
            var unsafe = original; unsafe[field] = .bool(true)
            try outcomeRefused("Outcome review rejects widened \(field)") { _ = try NativeSkillOutcomeReview.decode(.object(unsafe), scope: model.scope) }
        }
        for field in ["conversation_id", "skill_id", "workspace_path"] {
            var unsafe = original; unsafe[field] = .string(field == "workspace_path" ? project.deletingLastPathComponent().path : UUID().uuidString)
            try outcomeRefused("Outcome review binds exact \(field)") { _ = try NativeSkillOutcomeReview.decode(.object(unsafe), scope: model.scope) }
        }
        model.evidence = "I manually compared the synthetic result with the expected evidence."
        await model.prepare()
        guard let pending = model.preview, pending.ready else { throw NativeError.message(model.error ?? "No manual outcome preview") }
        try check(pending.futureMutation == "process_memory_four_events_one_receipt" && pending.operatorReported && pending.restartExpiring,
                  "Manual outcome preview discloses one process-only batch, never independently verified execution")
        await model.confirm(token: "WRONG", acknowledgement: true)
        await model.confirm(token: pending.confirmationToken, acknowledgement: false)
        try check(model.report?.receiptCount == 0 && model.preview != nil,
                  "Native manual outcome requires both exact token and operator-reported acknowledgement")
        model.evidence += " The check passed."
        await model.confirm(token: pending.confirmationToken, acknowledgement: true)
        try check(model.preview == nil && model.report?.receiptCount == 0,
                  "An edited manual result invalidates its old confirmation")
        await model.prepare()
        guard let preview = model.preview, preview.ready else { throw NativeError.message(model.error ?? "No fresh manual outcome preview") }
        let selected = model.selection
        let rawPreview = try await app.client.request("skill_outcome_preview", selected.parameters)
        if case .object(let data) = rawPreview {
            for field in ["future_mutation", "confirmation_token", "blueprint_hash"] {
                var unsafe = data; unsafe[field] = .string("unsafe-or-stale")
                try outcomeRefused("Outcome preview rejects changed \(field)") {
                    _ = try NativeSkillOutcomePreview.decode(.object(unsafe), selection: selected)
                }
            }
        }
        await model.confirm(token: preview.confirmationToken, acknowledgement: true)
        try check(model.result?.eventsAppended == 4 && model.report?.receiptCount == 1 && model.report?.eventCount == 4 &&
                  model.report?.receipts.first?.verificationStatus == "VERIFIED",
                  "Native manual outcome appends exactly four core events and one verified process receipt")
        try check(try fileBytes(project) == before && fileBytes(state) == privateBefore && app.messages == messages && app.composer == draft,
                  "Confirmed manual outcome leaves core/private files, chat and draft byte-identical")
        await model.prepare()
        try check(model.preview?.ready == false && model.report?.receiptCount == 1,
                  "The same manual outcome cannot be replayed, even after a lost response or refresh")
        var retry = selected.parameters
        retry["confirmation_token"] = .string(preview.confirmationToken)
        retry["preview_fingerprint"] = .string(preview.previewFingerprint)
        retry["acknowledge_manual_only"] = .bool(true)
        var replayRefused = false
        do { _ = try await app.client.request("skill_outcome_confirm", retry) } catch { replayRefused = true }
        try check(replayRefused, "Core RPC independently refuses a repeated manual result")
        await model.openEvidence()
        try check(app.skillOutcome == nil && app.skillInspection?.report?.outcome?.status == "SUCCESS_CANDIDATE" &&
                  app.skillInspection?.report?.outcome?.signalCount == 1,
                  "A captured manual result is visible through the existing exact-lineage inspector")
        app.skillInspection?.close()
        await app.openSkillOutcome(item)
        guard let reopened = app.skillOutcome else { throw NativeError.message("Missing reopened result form") }
        try check(reopened.report?.receipts.count == 1 && reopened.evidence.isEmpty,
                  "Reopening shows existing process receipts but does not persist or restore an unsent form")

        let failure = NativeSkillOutcomeSelection(scope: reopened.scope, outcome: "failure", evidence: "A later manual attempt needed a correction.")
        let failurePreview = try NativeSkillOutcomePreview.decode(try await app.client.request("skill_outcome_preview", failure.parameters), selection: failure)
        var failureParams = failure.parameters
        failureParams["preview_fingerprint"] = .string(failurePreview.previewFingerprint)
        failureParams["confirmation_token"] = .string(failurePreview.confirmationToken)
        failureParams["acknowledge_manual_only"] = .bool(true)
        let rawResult = try await app.client.request("skill_outcome_confirm", failureParams)
        let failureResult = try NativeSkillOutcomeResult.decode(rawResult, selection: failure, preview: failurePreview)
        try check(failureResult.receipt.outcome == "failure" && failureResult.receipt.operatorReported,
                  "Failure and correction remain an operator report, not a changed skill")
        if case .object(let data) = rawResult {
            for field in ["store_mutation_performed", "no_execution", "events_appended"] {
                var unsafe = data; unsafe[field] = field == "events_appended" ? .number(1) : .bool(field != "no_execution")
                try outcomeRefused("Outcome result rejects invalid \(field)") {
                    _ = try NativeSkillOutcomeResult.decode(.object(unsafe), selection: failure, preview: failurePreview)
                }
            }
            if case .object(let receipt) = data["receipt"] {
                for field in ["execution_performed_by_proto_mind", "persistence_performed", "blueprint_hash", "skill_id"] {
                    var changed = receipt
                    changed[field] = field.hasSuffix("performed") || field == "execution_performed_by_proto_mind" ? .bool(true) : .string("wrong")
                    var unsafe = data; unsafe["receipt"] = .object(changed)
                    try outcomeRefused("Outcome receipt rejects invalid \(field)") {
                        _ = try NativeSkillOutcomeResult.decode(.object(unsafe), selection: failure, preview: failurePreview)
                    }
                }
            }
        }
        await reopened.openEvidence()
        try check(app.skillInspection?.report?.outcome?.status == "MIXED_EVIDENCE" && app.skillInspection?.report?.outcome?.automaticDecisionAllowed == false,
                  "Conflicting manual results stay mixed without automatic learning or lifecycle decisions")
        app.skillInspection?.close()
        app.busy = true; await app.openSkillOutcome(item)
        try check(app.skillOutcome == nil, "Manual outcome form does not compete with a foreground turn")
        app.busy = false
        let conversation = app.selectedID; app.selectedID = nil
        await app.openSkillOutcome(item)
        try check(app.skillOutcome == nil, "Manual outcome cannot select or create a conversation implicitly")
        app.selectedID = conversation
        let restart = AppModel(configuration: app.client.configuration)
        defer { restart.client.shutdown() }
        await restart.openSkillOutcome(item)
        try check(restart.skillOutcome?.report?.pilotState == "not_started" && restart.skillOutcome?.report?.receipts.isEmpty == true &&
                  restart.skillOutcome?.report?.sourceEligible == true,
                  "Restart expires consent and result receipts while preserving the saved skill")
        restart.skillOutcome?.close()
        try check(try fileBytes(project) == before && fileBytes(state) == privateBefore && !app.cloudConsent && !app.fullAccessEnabled,
                  "Manual outcome workflow and restart introduce no file mutations, cloud consent or tool grants")
    }

    static func outcomeRefused(_ message: String, action: () throws -> Void) throws {
        var refused = false
        do { try action() } catch { refused = true }
        try check(refused, message)
    }
}
