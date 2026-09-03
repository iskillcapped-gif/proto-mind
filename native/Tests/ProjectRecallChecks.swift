import AppKit
import CryptoKit
import Foundation
import SwiftUI

extension NativeChecks {
    @MainActor
    static func projectRecallContracts(root: URL) throws {
        let state = root.appendingPathComponent("recall-contracts")
        let app = AppModel(configuration: LaunchConfiguration(projectRoot: root, python: root, stateDirectory: state))
        try check(app.selected?.autoProjectRecallEnabled == true && !FileManager.default.fileExists(atPath: state.path),
                  "Project recall defaults on without creating notes, history or provider connection")
        let originalID = app.selectedID!
        app.setAutoProjectRecallEnabled(false)
        let before = try fileBytes(state)
        let restarted = AppModel(configuration: app.client.configuration)
        try check(restarted.selected?.autoProjectRecallEnabled == false && !restarted.cloudConsent && !restarted.fullAccessEnabled
                  && (try fileBytes(state)) == before, "Recall opt-out reloads without rewriting history or granting cloud/tools")
        app.busy = true; app.setAutoProjectRecallEnabled(true)
        try check(app.selected?.autoProjectRecallEnabled == false, "Recall mode cannot change during a running turn")
        app.busy = false; app.newConversation()
        try check(app.selected?.autoProjectRecallEnabled == true && app.conversations.first(where: { $0.id == originalID })?.autoProjectRecallEnabled == false,
                  "Recall opt-out belongs to one chat, not every project or permission setting")
        let menu = NSHostingController(rootView: ProjectRecallMenu(model: app))
        let size = menu.sizeThatFits(in: CGSize(width: 160, height: 80))
        try check(size.width < 65 && size.height < 50, "Project recall icon fits without another wide composer control")
        var legacy = try JSONSerialization.jsonObject(with: JSONEncoder().encode(Conversation())) as! [String: Any]
        legacy.removeValue(forKey: "autoProjectRecallEnabled")
        let decoded = try JSONDecoder().decode(Conversation.self, from: JSONSerialization.data(withJSONObject: legacy))
        try check(decoded.autoProjectRecallEnabled, "Old chats support project recall without a migration")
        let fixture = recallMetadata(conversation: originalID, workspace: root.path)
        try checkKnowledgeMetadata(fixture.metadata)
        try checkProjectMemorySources(.array([fixture.source]), metadata: fixture.metadata)
        let report = try NativeProjectRecallReport(fixture.metadata["project_recall"], notes: fixture.metadata["project_memory"].items)
        try check(report.state == "selected" && report.matches(conversation: originalID, text: "Cobalt palette", workspace: root.path, mode: "chat"),
                  "Automatic provenance binds exact task, project, note versions and read-only selection")
        try check(!report.matches(conversation: UUID(), text: "Cobalt palette", workspace: root.path, mode: "chat")
                  && !report.matches(conversation: originalID, text: "Other task", workspace: root.path, mode: "chat")
                  && !report.matches(conversation: originalID, text: "Cobalt palette", workspace: nil, mode: "chat")
                  && !report.matches(conversation: originalID, text: "Cobalt palette", workspace: root.path, mode: "full_access"),
                  "Reviewed recall cannot be silently rebound after scope, draft or access changes")
        if case .object(let raw) = report.value {
            for (key, value) in [("permission_granted", JSONValue.bool(true)), ("automatic_learning", .bool(true)),
                                 ("model_call_performed", .bool(true)), ("read_only", .bool(false)), ("total_count", .bool(true)),
                                 ("source_snapshot_hash", .null), ("selected_ids", .array([])), ("characters", .number(6001)),
                                 ("execute", .string("shell")), ("omitted_count", .number(1))] {
                var changed = raw; changed[key] = value
                try outcomeRefused("Project recall rejects invalid \(key)") { _ = try NativeProjectRecallReport(.object(changed)) }
            }
        }
        if case .object(let source) = fixture.source {
            for (key, value) in [("content", JSONValue.string("Replaced content")), ("record_hash", .string(String(repeating: "c", count: 64))),
                                 ("status", .string("superseded")), ("basis", .string("Changed basis length"))] {
                var changed = source; changed[key] = value
                try outcomeRefused("Context desk refuses mismatched selected-note \(key)") {
                    try checkProjectMemorySources(.array([.object(changed)]), metadata: fixture.metadata)
                }
            }
        }
        try outcomeRefused("Context cannot omit selected sources while claiming recalled notes") {
            try checkProjectMemorySources(.null, metadata: fixture.metadata)
        }
        var run: [String: JSONValue] = ["conversation_id": report.value["conversation_id"], "workspace": report.value["workspace"],
            "input_sha256": report.value["goal_sha256"], "access_mode": .string("chat"), "provider": .string("codex")]
        _ = try NativeProjectRecallReport(report.value, run: .object(run))
        run["provider"] = .string("mock")
        try outcomeRefused("A saved recall report is not valid for another provider") { _ = try NativeProjectRecallReport(report.value, run: .object(run)) }
        var chat = Conversation(); chat.id = originalID
        chat.messages = [ChatMessage(role: "assistant", text: "A bounded answer", knowledgeContext: fixture.metadata)]
        let store = ChatStore(directory: root.appendingPathComponent("recall-history"))
        try store.save(ChatArchive(conversations: [chat], selectedID: chat.id))
        let bytes = try Data(contentsOf: store.url)
        try check(try store.load().conversations[0].messages[0].knowledgeContext == fixture.metadata && Data(contentsOf: store.url) == bytes,
                  "Content-free recall provenance survives history reload without rewriting the archive")
        try check(!String(decoding: bytes, as: UTF8.self).contains(fixture.source["content"].text)
                  && !chat.history[0]["content"].text.contains("source_snapshot_hash"),
                  "History metadata neither duplicates note text nor replays recall reports as instructions")
    }

    static func recallMetadata(conversation: UUID, workspace: String) -> (metadata: JSONValue, source: JSONValue) {
        func hash(_ text: String) -> JSONValue { .string(SHA256.hash(data: Data(text.utf8)).map { String(format: "%02x", $0) }.joined()) }
        let scope = JSONValue.object(["path": .string(workspace), "device": .number(1), "inode": .number(2)])
        let id = JSONValue.string(String(repeating: "a", count: 64)), recordHash = JSONValue.string(String(repeating: "b", count: 64))
        let content = "Cobalt palette is the current project choice.", basis = "Operator synthetic fixture."
        let reference: JSONValue = .object(["id": id, "record_hash": recordHash, "kind": .string("decision"), "workspace": scope,
            "characters": .number(Double(content.unicodeScalars.count)), "content_sha256": hash(content),
            "verification": .string("operator_asserted_not_independently_verified")])
        let report: JSONValue = .object(["schema": .string("proto_mind.native_project_recall.v1"),
            "conversation_id": .string(conversation.uuidString.lowercased()), "workspace": scope, "goal_sha256": hash("Cobalt palette"),
            "access_mode": .string("chat"), "state": .string("selected"), "algorithm": .string("local_content_token_overlap_v1"),
            "source_snapshot_hash": recordHash, "total_count": .number(1), "active_count": .number(1), "matching_count": .number(1),
            "selected_ids": .array([id]), "characters": .number(Double(content.unicodeScalars.count + basis.unicodeScalars.count)),
            "omitted_count": .number(0), "reason": .string("Current project content-word match."), "read_only": .bool(true),
            "model_call_performed": .bool(false), "permission_granted": .bool(false), "automatic_learning": .bool(false)])
        let source: JSONValue = .object(["id": id, "record_hash": recordHash, "kind": .string("decision"), "workspace": scope,
            "saved_at": .string("2026-09-03T00:00:00Z"), "content": .string(content), "basis": .string(basis),
            "status": .string("active"), "supersedes_id": .string(""), "verification": .string("operator_asserted_not_independently_verified")])
        let metadata: JSONValue = .object(["schema": .string("proto_mind.native_knowledge_context.v2"),
            "selection": .string("automatic_project_recall"), "permission_granted": .bool(false), "automatic_recall": .bool(true),
            "automatic_skill_execution": .bool(false), "project_memory": .array([reference]), "project_recall": report])
        return (metadata, source)
    }

    @MainActor
    static func projectRecallIntegration(fixture: URL, python: URL, root: URL) async throws {
        let state = root.appendingPathComponent("project-recall-ui")
        let app = AppModel(configuration: LaunchConfiguration(projectRoot: fixture, python: python, stateDirectory: state))
        defer { app.client.shutdown() }
        await app.start(); app.setProvider("codex"); await app.bindWorkspace(fixture.path)
        app.setAutoSkillsEnabled(false); app.setComposer("Explain the cobalt palette."); app.flushDraft()
        let core = try fileBytes(fixture), initial = try fileBytes(state), messages = app.messages
        await app.refreshContextPreview()
        try check(app.contextPreview?.manifest["knowledge_context"]["project_recall"]["state"] == .string("empty")
                  && (try fileBytes(state)) == initial && (try fileBytes(fixture)) == core,
                  "Real stdio empty recall preview needs no cloud, store initialization or mutation")
        await app.openProjectMemory()
        guard let panel = app.projectMemory else { throw NativeError.message("Project notes unavailable") }
        panel.content = "Cobalt palette is used by this project."; panel.basis = "Explicit operator fixture requirement."
        await panel.prepare()
        guard let prepared = panel.preview else { throw NativeError.message(panel.error ?? "No note preview") }
        await panel.save(token: prepared["confirmation_token"].text, acknowledgement: true)
        guard panel.error == nil, let note = panel.notes.first else { throw NativeError.message(panel.error ?? "No note saved") }
        panel.close()
        let saved = try fileBytes(state)
        await app.refreshContextPreview()
        guard let preview = app.contextPreview else { throw NativeError.message(app.contextPreviewError ?? "No recall preview") }
        try check(preview.manifest["knowledge_context"]["project_recall"]["selected_ids"] == .array([.string(note.id)])
                  && preview.value["project_memory_sources"].items.first?["content"] == note.raw["content"],
                  "Ordinary Codex draft automatically previews exact current note content without manual attachment")
        try check(try fileBytes(state) == saved && fileBytes(fixture) == core && app.messages == messages && app.pendingProjectNotes.isEmpty,
                  "Automatic recall preview writes neither notes, run journal, chat nor target stores")
        let report = try NativeProjectRecallReport(preview.manifest["knowledge_context"]["project_recall"])
        let hosting = NSHostingController(rootView: ProjectRecallReportView(report: report))
        let size = hosting.sizeThatFits(in: CGSize(width: 900, height: 760))
        try check(size.width <= 901 && size.height <= 801, "Automatic note report remains bounded inside the context desk")
        if case .object(let raw) = preview.value, case .object(var manifest) = preview.manifest {
            manifest["provider"] = .string("mock")
            var changed = raw; changed["manifest"] = .object(manifest)
            try outcomeRefused("Context desk rejects recalled sources attached to the wrong provider") { _ = try NativeContextPreview(.object(changed)) }
        }
        app.setAutoProjectRecallEnabled(false); await app.refreshContextPreview()
        try check(app.contextPreview?.manifest["knowledge_context"].isNull == true, "Opt-out removes automatic notes from the next context")
        app.setAutoProjectRecallEnabled(true)
        await app.openProjectMemory()
        guard let manual = app.projectMemory else { throw NativeError.message("Manual notes unavailable") }
        await manual.inspect(note); manual.attach(); await app.refreshContextPreview()
        try check(app.contextPreview?.manifest["knowledge_context"]["selection"] == .string("operator_explicit")
                  && app.contextPreview?.manifest["knowledge_context"]["project_recall"].isNull == true,
                  "Manual note selection takes precedence without hidden automatic merging")
        app.removeProjectNote(note.id)
        app.setComposer("/commands status"); app.flushDraft(); await app.refreshContextPreview()
        try check(app.contextPreview?.manifest["knowledge_context"].isNull == true, "Operator routes bypass automatic note context")
        app.setComposer("What is the weather?"); app.flushDraft(); await app.refreshContextPreview()
        try check(app.contextPreview?.manifest["knowledge_context"]["project_recall"]["state"] == .string("no_match"),
                  "An unrelated draft yields no selection, not fabricated semantic recall")
        app.setProvider("mock"); await app.refreshContextPreview()
        try check(app.contextPreview?.manifest["knowledge_context"].isNull == true, "Local provider never implicitly receives auto-recalled Codex notes")
        try check(!app.fullAccessEnabled && !app.cloudConsent && !app.bootstrap["context_injection"].flag
                  && (try fileBytes(fixture)) == core && app.messages == messages,
                  "Recall controls never enable Context Injection, cloud, tools, execute a task or alter core stores")
        let noteBytes = try fileBytes(state.appendingPathComponent("project_memory"))
        app.setProvider("codex"); app.newConversation(); app.setProvider("codex"); await app.bindWorkspace(fixture.path)
        app.setComposer("Cobalt palette"); app.flushDraft(); await app.refreshContextPreview()
        try check(app.contextPreview?.manifest["knowledge_context"]["project_recall"]["selected_ids"] == .array([.string(note.id)])
                  && (try fileBytes(state.appendingPathComponent("project_memory"))) == noteBytes,
                  "New chat recalls the same explicitly saved project note without promoting or rewriting it")
    }
}
