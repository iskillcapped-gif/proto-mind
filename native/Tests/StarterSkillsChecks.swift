import Foundation

extension NativeChecks {
    @MainActor
    static func starterSkills(app: AppModel, project: URL, state: URL) async throws {
        let before = try fileBytes(project), privateBefore = try fileBytes(state)
        let raw = try await app.client.request("starter_skills")
        let snapshot = try StarterSkillsSnapshot(raw)
        try check(snapshot.pack["skills"].items.count == 4 && snapshot.pack["learned_from_user"] == .bool(false),
                  "Four built-in procedures are visibly application-authored, never fabricated learned lessons")
        try check(snapshot.pack["skills"].items.allSatisfy { !$0["contract"]["verification"].items.isEmpty },
                  "Every starter procedure includes actual result checks")
        try check(try fileBytes(project) == before && fileBytes(state) == privateBefore,
                  "Real starter inspection RPC is read-only across core and private files")
        guard case .object(let original) = raw else { throw NativeAutoSkillsReport.error() }
        for (field, value) in [("read_only", JSONValue.bool(false)), ("no_execution", .bool(false)),
                               ("sha256", .string(String(repeating: "0", count: 64))), ("execute", .bool(true))] {
            var bad = original; bad[field] = value
            try outcomeRefused("Starter inspection rejects \(field)") { _ = try StarterSkillsSnapshot(.object(bad)) }
        }
        var report = autoSkillReport(conversation: app.selectedID!, text: "Task")
        report["schema"] = .string("proto_mind.native_auto_skills.v2")
        report["starter_pack"] = .object(["id": snapshot.pack["id"], "version": snapshot.pack["version"], "sha256": raw["sha256"]])
        report["bundled_count"] = .number(4); report["learned_count"] = .number(1)
        report["catalog_count"] = .number(5); report["eligible_count"] = .number(5)
        var bundled: [String: JSONValue] = ["origin": .string("bundled"), "skill_id": .string("builtin.verified_change"),
            "skill_name": .string("Implement and verify a change"), "pack_id": snapshot.pack["id"],
            "version": snapshot.pack["version"], "pack_hash": raw["sha256"], "contract_hash": .string(String(repeating: "a", count: 64))]
        report["selected"] = .array([.object(bundled)])
        let checked = try NativeAutoSkillsReport(.object(report))
        try check(checked.selected[0]["source_lesson_id"].isNull && checked.selected[0]["origin"] == .string("bundled"),
                  "Bundled v2 receipt has pack version/hash and no learned provenance")
        for (field, value) in [("source_lesson_id", JSONValue.string("invented")), ("origin", .string("learned")),
                               ("pack_hash", .string(String(repeating: "0", count: 64))), ("version", .string("9.0.0"))] {
            var reference = bundled; reference[field] = value
            var bad = report; bad["selected"] = .array([.object(reference)])
            try outcomeRefused("Bundled receipt rejects invented \(field)") { _ = try NativeAutoSkillsReport(.object(bad)) }
        }
        bundled.removeValue(forKey: "origin")
        var forged = report; forged["selected"] = .array([.object(bundled)])
        try outcomeRefused("V2 cannot silently infer missing source origin") { _ = try NativeAutoSkillsReport(.object(forged)) }
        let legacy = autoSkillReport(conversation: app.selectedID!, text: "Old task")
        try check(try NativeAutoSkillsReport(.object(legacy)).value["starter_pack"].isNull,
                  "V1 history remains readable without invented pack metadata or migration")
        var chat = Conversation(); chat.messages = [ChatMessage(role: "assistant", text: "Answer", autoSkills: .object(report))]
        let saved = ChatStore(directory: state.appendingPathComponent("starter-history"))
        try saved.save(ChatArchive(conversations: [chat], selectedID: chat.id))
        try check(try saved.load().conversations[0].messages[0].autoSkills == .object(report),
                  "V2 selection origin survives private history reload without saving full procedures")
    }
}
