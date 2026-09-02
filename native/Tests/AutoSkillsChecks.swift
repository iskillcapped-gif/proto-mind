import AppKit
import CryptoKit
import Foundation
import SwiftUI

extension NativeChecks {
    @MainActor
    static func autoSkillsContracts(root: URL) throws {
        let state = root.appendingPathComponent("auto-skills-contracts")
        let app = AppModel(configuration: LaunchConfiguration(projectRoot: root, python: root, stateDirectory: state))
        try check(app.selected?.autoSkillsEnabled == true && !FileManager.default.fileExists(atPath: state.path),
                  "Automatic skills default on without a provider call or initialization write")
        app.setAutoSkillsEnabled(false)
        let restart = AppModel(configuration: app.client.configuration)
        try check(restart.selected?.autoSkillsEnabled == false && !restart.cloudConsent && !restart.fullAccessEnabled,
                  "Disabling auto skills persists per conversation, independently of cloud/access consent")
        app.busy = true; app.setAutoSkillsEnabled(true)
        try check(app.selected?.autoSkillsEnabled == false, "Skill mode cannot change during a running turn")
        app.busy = false
        let menu = NSHostingController(rootView: AutoSkillsMenu(model: app))
        let size = menu.sizeThatFits(in: CGSize(width: 500, height: 100))
        try check(size.width < 220 && size.height < 55, "Automatic skills control remains compact in the composer")
        var legacy = try JSONSerialization.jsonObject(with: JSONEncoder().encode(Conversation())) as! [String: Any]
        legacy.removeValue(forKey: "autoSkillsEnabled")
        let decoded = try JSONDecoder().decode(Conversation.self, from: JSONSerialization.data(withJSONObject: legacy))
        try check(decoded.autoSkillsEnabled, "Old conversation files need no migration to support auto skills")
        var report = autoSkillReport(conversation: app.selectedID!, text: "Task")
        let checked = try NativeAutoSkillsReport(.object(report))
        try check(checked.state == "selected" && checked.matches(conversation: app.selectedID!, text: "Task", workspace: nil, mode: "chat"),
                  "Selected report binds task, conversation, mode, source version and model without authority")
        try check(!checked.matches(conversation: UUID(), text: "Task", workspace: nil, mode: "chat")
                  && !checked.matches(conversation: app.selectedID!, text: "Other", workspace: nil, mode: "chat")
                  && !checked.matches(conversation: app.selectedID!, text: "Task", workspace: nil, mode: "full_access"),
                  "Auto report cannot be rebound to a different request or permissions")
        for (key, value) in [("permission_granted", JSONValue.bool(true)), ("automatic_learning", .bool(true)),
                             ("quality_verification", .string("verified")), ("selector_attempted", .bool(false)),
                             ("execute", .bool(true)), ("catalog_count", .bool(true)), ("selected", .array([]))] {
            var changed = report; changed[key] = value
            try outcomeRefused("Auto report rejects invalid \(key)") { _ = try NativeAutoSkillsReport(.object(changed)) }
        }
        var chat = Conversation(); chat.id = app.selectedID!
        chat.messages = [ChatMessage(role: "assistant", text: "Answer", autoSkills: .object(report))]
        let store = ChatStore(directory: root.appendingPathComponent("auto-report-history"))
        try store.save(ChatArchive(conversations: [chat], selectedID: chat.id))
        try check(try store.load().conversations.first?.messages.first?.autoSkills == .object(report),
                  "Automatic skill metadata remains visible after history reload")
        try check(!chat.history[0]["content"].text.contains("skill_record_hash"), "Selection receipts are not replayed as chat instructions")
        report["state"] = .string("failed"); report["selected"] = .array([]); report["suggested_checks"] = .array([])
        try check(try NativeAutoSkillsReport(.object(report)).state == "failed", "Interrupted selection remains diagnostic, not a success claim")
    }

    static func autoSkillReport(conversation: UUID, text: String) -> [String: JSONValue] {
        let hash = JSONValue.string(String(repeating: "a", count: 64))
        return ["schema": .string("proto_mind.native_auto_skills.v1"), "conversation_id": .string(conversation.uuidString.lowercased()),
                "workspace": .null, "goal_sha256": .string(SHA256.hash(data: Data(text.utf8)).map { String(format: "%02x", $0) }.joined()),
                "access_mode": .string("chat"), "state": .string("selected"), "catalog_count": .number(1), "eligible_count": .number(1),
                "excluded_count": .number(0), "catalog_truncated": .bool(false), "catalog_hash": hash,
                "source_hashes": .object(["skills.jsonl": hash, "persistent_memory.json": hash, "context_injection.json": hash]),
                "selected": .array([.object(["skill_id": .string("fixture"), "skill_name": .string("Inspect a fixture"),
                    "skill_record_hash": hash, "source_lesson_id": .string("lesson"), "provenance_hash": hash,
                    "contract_hash": hash, "lifecycle_state": .string("active_verified")])]),
                "selector_attempted": .bool(true), "selector_model": .string("fixture-model"), "selector_effort": .string("low"),
                "reason": .string("Relevant procedure."), "suggested_checks": .array([.string("Observe actual results.")]),
                "quality_verification": .string("not_assessed"), "permission_granted": .bool(false), "automatic_learning": .bool(false)]
    }

    @MainActor
    static func autoSkillsIntegration(configuration: LaunchConfiguration, project: URL, state: URL) async throws {
        let privateState = state.deletingLastPathComponent().appendingPathComponent("auto-skills-state")
        let app = AppModel(configuration: LaunchConfiguration(projectRoot: project, python: configuration.python, stateDirectory: privateState))
        defer { app.client.shutdown() }
        await app.start(); app.setProvider("codex"); await app.bindWorkspace(project.path)
        app.setComposer("Inspect the recurring failure safely."); app.flushDraft()
        let before = try fileBytes(project), privateBefore = try fileBytes(privateState)
        let skillsURL = project.appendingPathComponent("proto_mind/data/skills.jsonl")
        let skillsBefore = try Data(contentsOf: skillsURL)
        await app.refreshContextPreview()
        guard let preview = app.contextPreview, let report = try? NativeAutoSkillsReport(preview.value["auto_skills"]) else {
            throw NativeError.message("No verified automatic-skill context preview")
        }
        try check(report.state == "ready" && report.value["catalog_count"].integer >= 1 && !report.value["selector_attempted"].flag,
                  "Real stdio context preview sees a verified catalog without calling Codex")
        try check(try fileBytes(project) == before && fileBytes(privateState) == privateBefore,
                  "Automatic catalog preview writes neither personal stores nor private run/history files")
        try check(!app.cloudConsent && !app.fullAccessEnabled && !app.bootstrap["context_injection"].flag,
                  "Automatic availability is not cloud consent, Full Mac authorization or Context Injection")
        try await starterSkills(app: app, project: project, state: privateState)
        app.setAutoSkillsEnabled(false)
        await app.refreshContextPreview()
        try check(app.contextPreview?.value["auto_skills"].isNull == true, "Turning Auto off removes the automatic selector from the next context")
        app.setAutoSkillsEnabled(true)
        app.setProvider("mock")
        await app.submit()
        try check(app.messages.last?.isError == false && app.messages.last?.autoSkills == nil,
                  "Mock ordinary Send stays ordinary and never fabricates automatic model selection")
        try check(try Data(contentsOf: skillsURL) == skillsBefore,
                  "Automatic controls and ordinary Mock Send never modify procedural skills")
    }
}
