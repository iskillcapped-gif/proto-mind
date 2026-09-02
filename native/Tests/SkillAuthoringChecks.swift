import AppKit
import Foundation
import SwiftUI

extension NativeChecks {
    @MainActor
    static func skillAuthoring(app: AppModel, lessonID: String, project: URL, state: URL) async throws {
        let before = try fileBytes(project), privateBefore = try fileBytes(state)
        let draftBefore = app.composer, messagesBefore = app.messages
        await app.openSkillAuthoring(lessonID: lessonID)
        guard let model = app.skillAuthoring, let report = model.report else {
            throw NativeError.message(app.skillAuthoring?.error ?? "Missing Native skill form")
        }
        try check(report.eligible && report.lifecycleState == "active" && !report.projectIsolationEnforced,
                  "Native skill form accepts a durable verified lesson after core restart without a live Experience pilot")
        try check(report.authoringReceipt == nil && report.applyReceipt == nil && report.fields.steps.isEmpty,
                  "Opening the form does not synthesize a procedure, author a receipt or apply a skill")
        try check(try fileBytes(project) == before && fileBytes(state) == privateBefore,
                  "Skill form inspection does not initialize or rewrite core or private stores")
        let alias = project.deletingLastPathComponent().appendingPathComponent("skill-workspace-alias")
        try FileManager.default.createSymbolicLink(at: alias, withDestinationURL: project)
        let aliasSelection = NativeSkillSelection(conversationID: model.conversationID, lessonID: lessonID,
                                                 workspace: alias.path, fields: model.draft.fields)
        let aliasRaw = try await app.client.request("skill_authoring_review", aliasSelection.parameters)
        let aliasReport = try NativeSkillReview.decode(aliasRaw, selection: aliasSelection)
        try check(aliasReport.eligible && URL(fileURLWithPath: aliasReport.workspacePath).resolvingSymlinksInPath().path == project.resolvingSymlinksInPath().path,
                  "Skill form accepts the same canonical workspace through a macOS path alias")
        if case .object(var wrongWorkspace) = aliasRaw {
            wrongWorkspace["workspace_path"] = .string(project.deletingLastPathComponent().path)
            var refused = false
            do { _ = try NativeSkillReview.decode(.object(wrongWorkspace), selection: aliasSelection) } catch { refused = true }
            try check(refused, "Canonical workspace matching still rejects a genuinely different directory")
        }
        await model.prepare(.apply)
        try check(model.preview?.ready == false, "Saving a skill requires a separate confirmed authored contract")

        model.draft = NativeSkillDraft(NativeSkillFields(name: "Synthetic evidence check", summary: "Review a local result before claiming completion.",
            trigger: "Before completing a synthetic work item.", preconditions: ["The expected result is explicitly stated."],
            steps: ["Read the expected result.", "Compare it with the observed evidence."],
            permissions: ["Read-only access to the selected evidence; no execution permission."],
            verification: ["Every completion claim has supporting evidence."], knownFailureModes: ["Missing evidence: stop and report uncertainty."]))
        let form = NSHostingController(rootView: SkillAuthoringView(model: model))
        let fitted = form.sizeThatFits(in: CGSize(width: 860, height: 730))
        try check(fitted.width <= 851 && fitted.height <= 721 && fitted.height >= 600,
                  "Skill authoring uses a bounded, scrollable Native sheet")
        await model.prepare(.author)
        guard let initial = model.preview, initial.ready else {
            throw NativeError.message(model.error ?? model.preview?.issues.joined(separator: "; ") ?? "Missing skill author preview")
        }
        try check(initial.futureMutation == "process_memory_only" && initial.body.contains("Compare it with the observed evidence"),
                  "Author preview shows the exact future skill body and no file mutation")
        await model.confirm(token: "WRONG", acknowledgeGlobal: false)
        try check(model.preview?.ready == true && model.report?.authoringReceipt == nil,
                  "Wrong Native skill token cannot dispatch confirmation")
        model.draft.trigger = "Before marking a synthetic result complete."
        try check(model.preview == nil, "Editing any skill field invalidates its pending confirmation")
        await model.confirm(token: initial.confirmationToken, acknowledgeGlobal: false)
        try check(model.report?.authoringReceipt == nil, "A stale form token is never silently reused")

        let selection = model.selection
        let rawReport = try await app.client.request("skill_authoring_review", selection.parameters)
        try skillContractRefusals(rawReport, selection: selection)
        await model.prepare(.author)
        guard let author = model.preview, author.ready else { throw NativeError.message(model.error ?? "No current skill preview") }
        await model.confirm(token: author.confirmationToken, acknowledgeGlobal: false)
        guard let authored = model.report?.authoringReceipt else { throw NativeError.message(model.error ?? "No skill author receipt") }
        try check(authored.kind == "author" && model.result?.skillMutationPerformed == false && model.report?.applyReceipt == nil,
                  "Author confirmation records only core process-memory fields, without automatic apply")
        try check(try fileBytes(project) == before && fileBytes(state) == privateBefore,
                  "A confirmed authored contract changes no files, history or settings")
        await model.prepare(.apply)
        guard let apply = model.preview, apply.ready else {
            throw NativeError.message(model.error ?? model.preview?.issues.joined(separator: "; ") ?? "No skill apply preview")
        }
        try check(apply.futureMutation == "skills_one_record" && apply.requiresGlobalSkillsAcknowledgement,
                  "Skill save preview declares exactly one shared-library record")
        await model.confirm(token: apply.confirmationToken, acknowledgeGlobal: false)
        try check(model.report?.applyReceipt == nil && model.preview?.ready == true,
                  "Skill apply requires global-scope acknowledgement in addition to the exact token")
        var params = model.selection.parameters
        params["operation"] = .string("apply")
        let rawPreview = try await app.client.request("skill_authoring_preview", params)
        if case .object(var unsafe) = rawPreview {
            unsafe["future_mutation"] = .string("multiple_stores")
            var refused = false
            do { _ = try NativeSkillPreview.decode(.object(unsafe), selection: model.selection, operation: .apply) } catch { refused = true }
            try check(refused, "Native skill preview rejects expanded mutation scope")
        }
        await model.confirm(token: apply.confirmationToken, acknowledgeGlobal: true)
        guard let applied = model.report?.applyReceipt else { throw NativeError.message(model.error ?? "No saved skill receipt") }
        try check(model.report?.status == "APPLIED" && applied.verificationStatus == "OK" && !applied.executable,
                  "Skill apply creates a verified non-executable procedural record through the core writer")
        let after = try fileBytes(project)
        let changes = Set(after.keys).union(before.keys).filter { after[$0] != before[$0] }
        let canonical = Set(changes.map { URL(fileURLWithPath: $0).resolvingSymlinksInPath().path })
        try check(canonical == [project.appendingPathComponent("proto_mind/data/skills.jsonl").resolvingSymlinksInPath().path],
                  "Confirmed Native skill apply changes only skills.jsonl")
        try check(try fileBytes(state) == privateBefore && app.composer == draftBefore && app.messages == messagesBefore &&
                  !app.cloudConsent && !app.fullAccessEnabled,
                  "Native skill authoring preserves chat, drafts, consent and tool grants")
        await model.prepare(.apply)
        await model.confirm(token: apply.confirmationToken, acknowledgeGlobal: true)
        try check(model.preview?.ready == false && !model.report!.nativeApplySlotAvailable && (try fileBytes(project)) == after,
                  "The same Native skill cannot be saved a second time")
        await model.openSavedSkill()
        try check(app.skillAuthoring == nil && app.section == .skills && app.libraryDetail?.item?.recordId == applied.recordId,
                  "Saved skill opens directly in the existing Native library")
        try check(app.libraryDetail?.skillEvidence?.status == "VERIFIED" && app.libraryDetail?.skillEvidence?.sourceLessonId == lessonID,
                  "Skill Library independently verifies embedded provenance and links its source lesson")
        await app.openSkillAuthoring(lessonID: lessonID)
        try check(app.skillAuthoring?.report?.status == "APPLIED" && app.skillAuthoring?.report?.nativeApplySlotAvailable == false,
                  "Closing and reopening the form does not renew the skill apply budget")
        app.skillAuthoring?.close()
        let restart = AppModel(configuration: app.client.configuration)
        defer { restart.client.shutdown() }
        await restart.openSkillAuthoring(lessonID: lessonID)
        try check(restart.skillAuthoring?.report?.eligible == false && restart.skillAuthoring?.report?.authoringReceipt == nil,
                  "Restart expires authoring receipts while the existing active skill prevents duplicate creation")
        restart.skillAuthoring?.close()
        restart.section = .skills; restart.libraryQuery = applied.recordId
        await restart.loadLibraryPage()
        if let item = restart.libraryPage?.items.first { await restart.inspectLibrary(item) }
        try check(restart.libraryDetail?.skillEvidence?.status == "VERIFIED",
                  "Skill provenance remains independently inspectable after restart")
        try check(try fileBytes(project) == after && fileBytes(state) == privateBefore,
                  "Skill restart/readback performs no migration, automatic action or private-state write")
        if let item = restart.libraryDetail?.item {
            try await skillInspection(app: restart, item: item, project: project, state: state)
            try await skillOutcome(app: restart, item: item, project: project, state: state)
            try await skillHistory(app: restart, item: item, project: project, state: state, minimumReceipts: 2)
            try await skillLifecycleApply(configuration: restart.client.configuration, item: item, project: project, state: state)
            try await skillRestore(configuration: restart.client.configuration, item: item, project: project, state: state)
            try await skillTasks(configuration: restart.client.configuration, item: item, project: project, state: state)
            try await autoSkillsIntegration(configuration: restart.client.configuration, project: project, state: state)
        } else { throw NativeError.message("Missing saved skill for inspection checks") }
    }

    static func skillContractRefusals(_ value: JSONValue, selection: NativeSkillSelection) throws {
        guard case .object(let original) = value else { throw NativeError.message("No skill contract fixture") }
        for key in ["automatic_promotion", "store_mutation_performed", "model_call_performed", "permissions_changed", "context_injection_changed", "project_isolation_enforced", "execute"] {
            var unsafe = original
            unsafe[key] = .bool(true)
            var refused = false
            do { _ = try NativeSkillReview.decode(.object(unsafe), selection: selection) } catch { refused = true }
            try check(refused, "Native skill contract rejects unsafe \(key)")
        }
        var wrong = original
        wrong["conversation_id"] = .string(UUID().uuidString)
        var refused = false
        do { _ = try NativeSkillReview.decode(.object(wrong), selection: selection) } catch { refused = true }
        try check(refused, "Native skill report cannot cross conversation scope")
    }
}
