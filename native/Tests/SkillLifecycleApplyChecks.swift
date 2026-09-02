import AppKit
import Foundation
import SwiftUI

extension NativeChecks {
    @MainActor
    static func skillLifecycleApply(configuration: LaunchConfiguration, item: LibraryItem, project: URL, state: URL) async throws {
        let privateBefore = try fileBytes(state)

        func prepareDecision(_ decision: NativeSkillDecision) async throws -> (AppModel, SkillLifecycleApplyModel) {
            let app = AppModel(configuration: configuration)
            do {
                func operatorCommand(_ text: String) async throws -> JSONValue {
                    try await app.client.request("process", ["conversation_id": .string(app.selectedID!.uuidString), "text": .string(text),
                        "confirmed_text": .string(text), "provider": .string("mock"), "persona_enabled": .bool(false)])
                }
                let preview = try await operatorCommand("/experience preview")
                guard let phrase = preview["text"].text.components(separatedBy: "\n").first(where: { $0.hasPrefix("/experience consent ") }) else {
                    throw NativeError.message("Missing lifecycle fixture consent")
                }
                _ = try await operatorCommand(phrase)
                await app.openSkillOutcome(item)
                guard let outcome = app.skillOutcome else { throw NativeError.message("Missing fixture outcome") }
                outcome.outcome = decision == .keep ? "success" : "failure"
                outcome.evidence = "Explicit synthetic manual evidence for the Native lifecycle test."
                await outcome.prepare()
                guard let capture = outcome.preview, capture.ready else { throw NativeError.message(outcome.error ?? "Missing capture") }
                await outcome.confirm(token: capture.confirmationToken, acknowledgement: true)
                let scope = outcome.scope
                outcome.close()
                await app.openSkillDecision(scope)
                guard let model = app.skillDecision else { throw NativeError.message("Missing fixture decision") }
                model.choice = decision; await model.prepare()
                guard let exact = model.preview, exact.ready else { throw NativeError.message(model.error ?? "Missing decision preview") }
                await model.confirm(token: exact.confirmationToken, acknowledgement: true)
                await model.openLifecycleApply()
                guard let lifecycle = app.skillLifecycleApply, lifecycle.report != nil else {
                    throw NativeError.message(app.skillLifecycleApply?.error ?? "Missing lifecycle form")
                }
                return (app, lifecycle)
            } catch { app.client.shutdown(); throw error }
        }

        let (keepApp, keep) = try await prepareDecision(.keep)
        defer { keepApp.client.shutdown() }
        let keepBefore = try fileBytes(project), messages = keepApp.messages, draft = keepApp.composer
        try check(keepApp.skillDecision == nil && keep.report?.canApply == true && keep.preview == nil,
                  "Decision opens a separate lifecycle review without pre-authorizing application")
        await keep.prepare()
        guard let keepPreview = keep.preview, keepPreview.ready else { throw NativeError.message(keep.error ?? "Missing keep preview") }
        try check(keepPreview.expectedRecordMutations == 0 && keepPreview.expectedChangedFields.isEmpty,
                  "Keep preview declares a receipt-only no-op, never archive or procedure execution")
        await keep.confirm(token: "WRONG", acknowledgement: true)
        await keep.confirm(token: keepPreview.confirmationToken, acknowledgement: false)
        try check(keep.report?.receipt == nil && keep.preview != nil, "Keep also requires a new exact apply token and acknowledgement")
        await keep.confirm(token: keepPreview.confirmationToken, acknowledgement: true)
        try check(keep.result?.receipt.actualRecordMutations == 0 && keep.report?.receipt?.verificationStatus == "VERIFIED" && keep.report?.status == "APPLIED",
                  "Exact keep application returns the existing core's verified zero-mutation receipt")
        try check(try fileBytes(project) == keepBefore && fileBytes(state) == privateBefore && keepApp.messages == messages && keepApp.composer == draft,
                  "Keep changes no core/private file, conversation or draft")
        await keep.prepare()
        try check(keep.preview == nil && !keep.canPrepare && keep.report?.nativeApplySlotAvailable == false,
                  "The Native process apply budget is not renewed by an executed keep")
        keep.close(); keepApp.client.shutdown()

        let (reviseApp, revise) = try await prepareDecision(.revise)
        defer { reviseApp.client.shutdown() }
        try check(revise.report?.status == "NOT_READY" && !revise.canPrepare, "Revision decisions have no hidden edit/apply path")
        await revise.prepare()
        try check(revise.preview == nil && (try fileBytes(project)) == keepBefore, "Unavailable revision cannot prepare or write anything")
        revise.close(); reviseApp.client.shutdown()

        let (app, model) = try await prepareDecision(.archive)
        defer { app.client.shutdown() }
        let before = try fileBytes(project), beforeMessages = app.messages, beforeDraft = app.composer
        let hosting = NSHostingController(rootView: SkillLifecycleApplyView(model: model))
        let fitted = hosting.sizeThatFits(in: CGSize(width: 860, height: 730))
        try check(fitted.width <= 851 && fitted.height <= 721 && fitted.height >= 600,
                  "Lifecycle application and receipts fit a bounded scrollable sheet")
        let rawReview = try await app.client.request("skill_lifecycle_review", model.selection.parameters)
        if case .object(let data) = rawReview {
            for field in ["store_mutation_performed", "skill_mutation_performed", "model_call_performed", "network_call_performed",
                          "retrieval_performed", "context_injection_changed", "permissions_changed", "consent_state_changed", "automatic_promotion",
                          "session_log_mutation_performed", "memory_mutation_performed", "experience_mutation_performed", "batch_apply_performed", "execute"] {
                var changed = data; changed[field] = .bool(true)
                try outcomeRefused("Lifecycle review rejects widened \(field)") { _ = try NativeSkillLifecycleApplyReview.decode(.object(changed), selection: model.selection) }
            }
            for field in ["conversation_id", "skill_id", "decision_receipt_id", "workspace_path"] {
                var changed = data; changed[field] = .string(field == "workspace_path" ? project.deletingLastPathComponent().path : UUID().uuidString)
                try outcomeRefused("Lifecycle review binds exact \(field)") { _ = try NativeSkillLifecycleApplyReview.decode(.object(changed), selection: model.selection) }
            }
        }
        await model.prepare()
        let cancelled = model.preview?.confirmationToken
        await model.refresh()
        try check(cancelled != nil && model.preview == nil && model.report?.receipt == nil, "Refreshing clears pending lifecycle authority without applying")
        await model.prepare()
        guard let preview = model.preview, preview.ready else { throw NativeError.message(model.error ?? "Missing archive preview") }
        try check(preview.expectedRecordMutations == 1 && preview.expectedChangedFields == ["lifecycle", "status", "updated_at"],
                  "Archive preview limits the write to one record and exactly three fields")
        let rawPreview = try await app.client.request("skill_lifecycle_preview", model.selection.parameters)
        if case .object(let data) = rawPreview {
            for field in ["confirmation_token", "decision_hash", "before_store_sha256", "before_record_hash", "metadata_blueprint_hash"] {
                var changed = data; changed[field] = .string(field == "confirmation_token" ? "CONFIRM-DURABLE-SKILL-LIFECYCLE-ARCHIVE-AAAAAAAAAAAA" : String(repeating: "0", count: 64))
                try outcomeRefused("Lifecycle token cryptographically binds \(field)") { _ = try NativeSkillLifecycleApplyPreview.decode(.object(changed), selection: model.selection) }
            }
            var changed = data; changed["expected_changed_fields"] = .array([.string("body")])
            try outcomeRefused("Lifecycle preview cannot expand to procedure edits") { _ = try NativeSkillLifecycleApplyPreview.decode(.object(changed), selection: model.selection) }
        }
        await model.confirm(token: "WRONG", acknowledgement: true)
        await model.confirm(token: preview.confirmationToken, acknowledgement: false)
        try check(try fileBytes(project) == before && model.report?.receipt == nil, "Wrong archive token or missing acknowledgement writes nothing")
        await model.confirm(token: preview.confirmationToken, acknowledgement: true)
        guard let result = model.result, let receipt = model.report?.receipt else { throw NativeError.message(model.error ?? "No archive receipt") }
        try check(result.eventsAppended == 0 && receipt.actualRecordMutations == 1 && receipt.verificationStatus == "VERIFIED" && receipt.evidenceState == "CURRENT",
                  "Native uses the real durable archive writer and returns its verified exact receipt")
        let after = try fileBytes(project)
        let changedPaths = before.keys.filter { before[$0] != after[$0] }.map {
            URL(fileURLWithPath: $0).resolvingSymlinksInPath().path
        }
        let expectedPath = project.appendingPathComponent("proto_mind/data/skills.jsonl").resolvingSymlinksInPath().path
        try check(Set(after.keys) == Set(before.keys) && changedPaths == [expectedPath],
                  "Archive changes only the fixed Skill Library; no new core/export files; changed=\(changedPaths), expected=\(expectedPath), added=\(Set(after.keys).subtracting(before.keys)), removed=\(Set(before.keys).subtracting(after.keys))")
        try check(try fileBytes(state) == privateBefore && app.messages == beforeMessages && app.composer == beforeDraft && !app.cloudConsent && !app.fullAccessEnabled,
                  "Archive does not write private history, turn evidence, consent or permissions")
        try check(model.report?.status == "APPLIED" && model.report?.storedSkillStatus == "archived" && !model.canPrepare,
                  "The applied record is archived and cannot be automatically rerun")
        var replay = model.selection.parameters
        replay["preview_fingerprint"] = .string(preview.previewFingerprint); replay["confirmation_token"] = .string(preview.confirmationToken)
        replay["acknowledge_global_skills"] = .bool(true)
        var refused = false
        do { _ = try await app.client.request("skill_lifecycle_confirm", replay) } catch { refused = true }
        try check(refused && (try fileBytes(project)) == after, "Core independently refuses archive replay without touching bytes")
        let rawReceipt = try await app.client.request("skill_lifecycle_review", model.selection.parameters)
        if case .object(let data) = rawReceipt, case .object(let raw) = data["receipt"] {
            for field in ["executable", "persistence_performed", "actual_record_mutations", "persistent_memory_unchanged", "post_state_verified"] {
                var invalid = raw; invalid[field] = field == "actual_record_mutations" ? .number(2) : .bool(field == "executable" || field == "persistence_performed")
                var changed = data; changed["receipt"] = .object(invalid)
                try outcomeRefused("Apply receipt rejects unsafe \(field)") { _ = try NativeSkillLifecycleApplyReview.decode(.object(changed), selection: model.selection) }
            }
        }
        let selection = model.selection
        await model.openSkill()
        try check(app.skillLifecycleApply == nil && app.libraryDetail?.item?.recordId == selection.scope.skillID && app.libraryFilter == .all,
                  "Applied archive opens the exact saved skill including archived records")
        await app.openSkillLifecycleApply(selection)
        try check(app.skillLifecycleApply?.report?.receipt?.id == receipt.id && app.skillLifecycleApply?.preview == nil,
                  "Reopening shows the same receipt without recreating apply authority")
        await app.skillLifecycleApply?.openEvidence()
        try check(app.skillInspection?.report?.lifecycle?.status == "archived" && app.skillInspection?.report?.lifecycle?.outcomeArchiveProven == true,
                  "The independent existing inspector proves durable archive cause and links the skill source")
        app.skillInspection?.close()
        let restart = AppModel(configuration: configuration)
        defer { restart.client.shutdown() }
        await restart.openSkillLifecycleApply(selection)
        try check(restart.skillLifecycleApply?.report?.receipt == nil && restart.skillLifecycleApply?.report?.canApply == false,
                  "Restart cannot restore process decisions, consent or repeat authorization")
        await restart.skillLifecycleApply?.openEvidence()
        try check(restart.skillInspection?.report?.lifecycle?.outcomeArchiveProven == true,
                  "Archive metadata remains verifiable after process receipt expiry")
        restart.skillInspection?.close()
        try check(try fileBytes(project) == after && fileBytes(state) == privateBefore, "Receipt/inspector/restart reads never rewrite the archived skill or private state")
    }
}
