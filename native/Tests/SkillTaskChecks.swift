import AppKit
import Foundation
import SwiftUI

extension NativeChecks {
    @MainActor
    static func skillTasks(configuration: LaunchConfiguration, item: LibraryItem, project: URL, state: URL) async throws {
        let privateState = state.deletingLastPathComponent().appendingPathComponent("guided-task-state")
        let app = AppModel(configuration: LaunchConfiguration(projectRoot: project, python: configuration.python, stateDirectory: privateState))
        defer { app.client.shutdown() }
        await app.start(); app.setProvider("mock"); await app.bindWorkspace(project.path); app.flushDraft()
        let skillURL = project.appendingPathComponent("proto_mind/data/skills.jsonl")
        let skillBytes = try Data(contentsOf: skillURL)
        let before = try fileBytes(project), privateBefore = try fileBytes(privateState), messages = app.messages
        await app.openSkillTask(skillID: item.recordId)
        guard let panel = app.skillTask, let initial = panel.preview else { throw NativeError.message(app.skillTask?.error ?? "Skill task did not open") }
        try check(!initial.ready && !initial.body.isNull && initial.body["lifecycle_state"] == .string("active_restored_verified"),
                  "A verified restored procedure can be reviewed but missing operator goal/criteria are not READY")
        let host = NSHostingController(rootView: SkillTaskView(model: panel))
        let size = host.sizeThatFits(in: CGSize(width: 860, height: 770))
        try check(size.width <= 851 && size.height <= 761, "Guided task form fits a bounded scrollable sheet")
        panel.goal = "Explain the procedure and its limits without tools."
        panel.criteriaText = "The fixture reply is visible.\nIts model/execution limitations are explicit."
        await panel.refresh()
        guard let preview = panel.preview, preview.ready else { throw NativeError.message(panel.error ?? "Task preview not READY") }
        try check(preview.body["permission_granted"] == .bool(false) && preview.body["quality_verification"] == .string("not_assessed"),
                  "READY means source and task preparation, not tool permission or verified effectiveness")
        if case .object(let raw) = preview.raw {
            for key in ["permission_granted", "store_mutation_performed", "model_call_performed", "execute"] {
                var changed = raw; changed[key] = .bool(true)
                try outcomeRefused("Task preview rejects widened \(key)") { _ = try NativeSkillTaskPreview(.object(changed), scope: panel.scope, skillID: item.recordId) }
            }
            var changed = raw; changed["preview_fingerprint"] = .string(String(repeating: "0", count: 64))
            try outcomeRefused("Task preview independently checks the source/task fingerprint") { _ = try NativeSkillTaskPreview(.object(changed), scope: panel.scope, skillID: item.recordId) }
            changed = raw; changed["conversation_id"] = .string(UUID().uuidString)
            try outcomeRefused("Task preview cannot cross conversation scope") { _ = try NativeSkillTaskPreview(.object(changed), scope: panel.scope, skillID: item.recordId) }
        }
        panel.use(acknowledgement: false)
        try check(app.pendingSkillTask == nil && app.messages == messages && app.composer.isEmpty,
                  "No task is selected without the operator's explicit review acknowledgement")
        try check(try fileBytes(project) == before && fileBytes(privateState) == privateBefore, "Reading and preparing a skill task never writes private/core files")
        panel.use(acknowledgement: true)
        app.flushDraft()
        guard let task = app.pendingSkillTask else { throw NativeError.message(panel.error ?? "Prepared task missing") }
        try check(app.skillTask == nil && app.composer == task.goal && app.selected?.pendingCriteria == task.criteria && app.messages == messages,
                  "Apply to draft selects guidance and criteria without Send")
        try check(try fileBytes(project) == before && !app.fullAccessEnabled && !app.cloudConsent && !app.bootstrap["context_injection"].flag,
                  "Draft preparation never changes core records, Context Injection, cloud consent or Full Mac")
        let restart = AppModel(configuration: app.client.configuration)
        defer { restart.client.shutdown() }
        try check(restart.pendingSkillTask == nil && restart.composer == task.goal && restart.selected?.pendingCriteria == task.criteria,
                  "Restart keeps the ordinary goal/criteria draft but cannot resurrect skill selection or authorization")
        await app.refreshContextPreview()
        guard let context = app.contextPreview else { throw NativeError.message("Guided context did not verify") }
        try check(context.manifest["knowledge_context"]["skill_task"] == task.reference && context.value["skill_task_source"]["contract"] == task.body["contract"],
                  "Context desk shows exact guidance with the same content-free run reference")
        if case .object(var raw) = context.value {
            raw["skill_task_hash_material"] = .string("{}")
            try outcomeRefused("Context desk rejects mismatched procedure bytes") { _ = try NativeContextPreview(.object(raw)) }
        }
        app.setComposer("An unrelated task")
        try check(!app.skillTaskMatchesDraft, "Changed operator text visibly marks the selection stale")
        let staleBefore = try fileBytes(project)
        await app.submit()
        try check(app.messages.last?.isError == true && app.pendingSkillTask == task && (try fileBytes(project)) == staleBefore,
                  "Stale guidance is refused before a core/model turn, not silently dropped or applied elsewhere")
        app.setComposer(task.goal)
        await app.submit("/commands status")
        try check(app.pendingSkillTask == task && app.messages.last?.role == "report", "Slash commands ignore but preserve prepared skill guidance")
        app.setComposer(task.goal)
        await app.submit()
        await app.refreshWorkSessions()
        guard let run = app.workSessions.first(where: { $0.value["context_manifest"]["knowledge_context"]["skill_task"] == task.reference }) else {
            throw NativeError.message(app.messages.last?.text ?? "No guided run receipt")
        }
        try check(app.pendingSkillTask == nil && app.messages.last?.isError == false && run.value["verification"] == .string("not_assessed") && run.value["acceptance"] == .string("not_recorded"),
                  "Only manual Send creates an ordinary run, consumes guidance and leaves outcome unaccepted")
        try check(app.messages.last?.notices.contains(where: { $0.contains("Mock does not execute") }) == true,
                  "Mock results cannot be mistaken for procedural execution or understanding")
        if case .object(var raw) = run.value, case .object(var manifest) = raw["context_manifest"], case .object(var knowledge) = manifest["knowledge_context"], case .object(var reference) = knowledge["skill_task"] {
            reference["goal_sha256"] = .string(String(repeating: "0", count: 64)); knowledge["skill_task"] = .object(reference)
            manifest["knowledge_context"] = .object(knowledge); raw["context_manifest"] = .object(manifest)
            try outcomeRefused("Saved run cannot claim guidance for another goal") { _ = try NativeWorkSession(.object(raw)) }
        }
        let unassessed: JSONValue = .object(["decision": .string("accepted"), "checks": .array(task.criteria.map { _ in .string("not_checked") }), "note": .string("")])
        let refused = try await app.previewManualReview(run, selection: unassessed)
        try check(!refused.ready, "A completed guided turn is not accepted until the operator checks every criterion")
        let review: JSONValue = .object(["decision": .string("accepted"), "checks": .array(task.criteria.map { _ in .string("met") }), "note": .string("Synthetic fixture checks only, not proof of skill effectiveness.")])
        let ready = try await app.previewManualReview(run, selection: review)
        try check(ready.ready, "Existing evidence review accepts an explicit, scoped operator assessment")
        let beforeReview = try fileBytes(project)
        let accepted = try await app.saveManualReview(run, preview: ready)
        try check(accepted.value["acceptance"] == .string("operator_accepted") && accepted.value["verification"] == .string("not_assessed") &&
                  (try fileBytes(project)) == beforeReview, "Manual acceptance writes private evidence only; no automatic skill learning or proven effectiveness")
        try check(try Data(contentsOf: skillURL) == skillBytes, "A guided task and its manual acceptance preserve skills including uses and lifecycle")
        await app.openSkillTask(skillID: item.recordId)
        guard let next = app.skillTask else { throw NativeError.message("Could not reopen guided form") }
        next.goal = task.goal; next.criteriaText = task.criteria.joined(separator: "\n"); await next.refresh()
        app.setComposer("Operator wrote this while the form was open")
        next.use(acknowledgement: true)
        try check(app.pendingSkillTask == nil && app.composer.hasPrefix("Operator wrote") && next.error != nil,
                  "Prepared form cannot overwrite a concurrently changed operator draft")
        next.close()
        await app.openSkillTask(skillID: item.recordId)
        guard let last = app.skillTask else { throw NativeError.message("No final fixture form") }
        last.criteriaText = task.criteria.joined(separator: "\n"); await last.refresh(); last.use(acknowledgement: true)
        let another = privateState.deletingLastPathComponent().appendingPathComponent("skill-other-project")
        try FileManager.default.createDirectory(at: another, withIntermediateDirectories: true)
        await app.bindWorkspace(another.path)
        try check(app.pendingSkillTask == nil && app.skillTask == nil, "Changing project removes ephemeral guidance; shared skills are never silently rebound")
    }
}
