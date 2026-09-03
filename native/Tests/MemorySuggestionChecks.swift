import AppKit
import Foundation
import SwiftUI

extension NativeChecks {
    static func suggestionFixture(conversation: UUID, workspace: String, text: String = "Я предпочитаю синий цвет 💙.") -> JSONValue {
        let run = UUID().uuidString.lowercased(), hash = suggestionTextHash(text), count = text.unicodeScalars.count
        let id = suggestionTextHash("\(run)\n\(hash)\npreference\n0:\(count)\n\(hash)")
        return .object(["schema": .string("proto_mind.native_memory_suggestions.v1"), "algorithm": .string("explicit_operator_statements_v1"),
            "source": .object(["conversation_id": .string(conversation.uuidString.lowercased()), "run_id": .string(run),
                "fingerprint": .string(String(repeating: "b", count: 64)), "input_sha256": .string(hash), "input_chars": .number(Double(count)),
                "workspace": .object(["path": .string(workspace), "device": .number(1), "inode": .number(2)])]),
            "state": .string("suggested"), "reason": .string("explicit_operator_statement"), "omitted_count": .number(0),
            "candidates": .array([.object(["id": .string(id), "kind": .string("preference"), "start": .number(0), "end": .number(Double(count)), "content_sha256": .string(hash)])]),
            "read_only": .bool(true), "automatic_save": .bool(false), "model_call_performed": .bool(false), "permission_granted": .bool(false)])
    }

    @MainActor
    static func memorySuggestionContracts(root: URL) throws {
        let state = root.appendingPathComponent("suggestion-contracts")
        let app = AppModel(configuration: LaunchConfiguration(projectRoot: root, python: root, stateDirectory: state))
        try check(app.selected?.memorySuggestionsEnabled == true && !FileManager.default.fileExists(atPath: state.path),
                  "Memory suggestions default on without writing a store or connecting a provider")
        app.setMemorySuggestionsEnabled(false)
        let bytes = try fileBytes(state)
        let restored = AppModel(configuration: app.client.configuration)
        try check(restored.selected?.memorySuggestionsEnabled == false && (try fileBytes(state)) == bytes,
                  "Per-chat suggestion opt-out survives restart without a history migration")
        app.busy = true; app.setMemorySuggestionsEnabled(true)
        try check(app.selected?.memorySuggestionsEnabled == false, "Suggestion mode cannot change during a turn")
        app.busy = false; app.newConversation()
        try check(app.selected?.memorySuggestionsEnabled == true && !app.cloudConsent && !app.fullAccessEnabled,
                  "A new chat gets local suggestions, never implicit cloud or tool consent")
        var legacy = try JSONSerialization.jsonObject(with: JSONEncoder().encode(Conversation())) as! [String: Any]
        legacy.removeValue(forKey: "memorySuggestionsEnabled")
        let decoded = try JSONDecoder().decode(Conversation.self, from: JSONSerialization.data(withJSONObject: legacy))
        try check(decoded.memorySuggestionsEnabled, "Legacy chats load the optional suggestion mode without rewriting records")
        let text = "Я предпочитаю синий цвет 💙.", conversation = UUID()
        let fixture = suggestionFixture(conversation: conversation, workspace: root.path, text: text)
        let report = try MemorySuggestionsReport(fixture, text: text)
        try check(try report.items[0].quote(in: text) == text, "Exact quote validation uses Unicode scalars rather than UTF-16 or grapheme offsets")
        try outcomeRefused("A changed source cannot generate a suggestion card") { _ = try MemorySuggestionsReport(fixture, text: "Different input") }
        if case .object(let fields) = fixture {
            for (key, value) in [("automatic_save", JSONValue.bool(true)), ("permission_granted", .bool(true)), ("model_call_performed", .bool(true)),
                                 ("read_only", .bool(false)), ("candidates", .array([])), ("execute", .string("shell")), ("omitted_count", .bool(true))] {
                var bad = fields; bad[key] = value
                try outcomeRefused("Suggestions reject widened or inconsistent \(key)") { _ = try MemorySuggestionsReport(.object(bad), text: text) }
            }
            if case .object(let candidate) = fixture["candidates"].items[0] {
                for (key, value) in [("kind", JSONValue.string("system")), ("start", .number(-1)), ("end", .number(601)),
                                     ("content_sha256", .string(String(repeating: "a", count: 64))), ("id", .string(String(repeating: "a", count: 64))),
                                     ("end", .bool(true)), ("start", .number(1e100)), ("content", .string("Injected body"))] {
                    var changed = candidate; changed[key] = value
                    var bad = fields; bad["candidates"] = .array([.object(changed)])
                    try outcomeRefused("Suggestion quote contract rejects \(key)") { _ = try MemorySuggestionsReport(.object(bad), text: text) }
                }
            }
        }
        var chat = Conversation(); chat.id = conversation
        let user = ChatMessage(role: "user", text: text)
        chat.messages = [user, ChatMessage(role: "assistant", text: "A synthetic answer.", memorySuggestions: fixture, memorySuggestionSourceID: user.id)]
        let store = ChatStore(directory: root.appendingPathComponent("suggestion-history"))
        try store.save(ChatArchive(conversations: [chat], selectedID: chat.id))
        let saved = try Data(contentsOf: store.url)
        try check(try store.load().conversations[0].messages == chat.messages && Data(contentsOf: store.url) == saved,
                  "Suggestion metadata and source-message reference survive restart without rewriting history")
        try check(chat.history.count == 2 && !chat.history.contains { $0["content"].text.contains("native_memory_suggestions") },
                  "Suggestion metadata is not provider replay or a duplicate memory source")
        chat.messages[0].text = "Changed original message"
        try outcomeRefused("Changed historical source blocks writing a misleading suggestion") { try store.save(ChatArchive(conversations: [chat], selectedID: chat.id)) }
        try check(try Data(contentsOf: store.url) == saved, "Rejected history write preserves original bytes")
        let scope = ProjectMemoryScope(conversationID: conversation, workspace: root.path)
        try outcomeRefused("Another conversation cannot review a source-bound suggestion") {
            _ = try MemorySuggestionModel(app: app, scope: ProjectMemoryScope(conversationID: UUID(), workspace: scope.workspace),
                                          report: report, suggestion: report.items[0], text: text)
        }
    }

    @MainActor
    static func memorySuggestionIntegration(fixture: URL, python: URL, root: URL) async throws {
        let state = root.appendingPathComponent("suggestion-integration")
        try seedMemorySuggestion(fixture: fixture, state: state, python: python)
        let app = AppModel(configuration: LaunchConfiguration(projectRoot: fixture, python: python, stateDirectory: state))
        defer { app.client.shutdown() }
        await app.start(); app.flushDraft()
        guard let message = app.messages.last, let (report, text) = app.memorySuggestions(for: message) else { throw NativeError.message("Synthetic memory suggestion missing") }
        guard report.items.count == 2 else { throw NativeError.message("Expected two synthetic suggestions: \(report.value.pretty)") }
        let before = try fileBytes(state), core = try fileBytes(fixture), messages = app.messages
        await app.openMemorySuggestion(report.items[0], report: report, text: text)
        guard let panel = app.memorySuggestion, panel.preview != nil else { throw NativeError.message(app.memorySuggestion?.error ?? "No reviewed memory suggestion") }
        let hosting = NSHostingController(rootView: MemorySuggestionView(model: panel))
        let size = hosting.sizeThatFits(in: CGSize(width: 680, height: 670))
        try check(size.width <= 661 && size.height <= 651, "Suggestion review stays within a bounded scrollable Native sheet")
        try check(panel.quote == "Мы решили использовать кобальтовую палитру." && panel.preview?["body"]["source"] == .string("operator_explicit"),
                  "Real bridge revalidates an exact Russian source quote and operator-only provenance")
        await panel.save(acknowledgement: false); panel.close()
        try check(try fileBytes(state) == before && fileBytes(fixture) == core && app.messages == messages,
                  "Reading, cancelling and declining acknowledgement never write history, core, runs or private notes")
        await app.openMemorySuggestion(report.items[0], report: report, text: text)
        guard let saving = app.memorySuggestion else { throw NativeError.message("No save review") }
        await saving.save(acknowledgement: true)
        guard let note = saving.saved, saving.error == nil else { throw NativeError.message(saving.error ?? "Explicit save failed") }
        let after = try fileBytes(state)
        let added = Set(after.keys).subtracting(before.keys)
        let expectedFiles = Set([state.appendingPathComponent("project_memory/\(note.id).json").resolvingSymlinksInPath().path,
                                 state.appendingPathComponent("project_memory/.writer.lock").resolvingSymlinksInPath().path])
        let canonicalAdded = Set(added.map { URL(fileURLWithPath: $0).resolvingSymlinksInPath().path })
        let changed = before.keys.filter { after[$0] != before[$0] }
        let expectedWrite = changed.isEmpty && canonicalAdded == expectedFiles
        try check(expectedWrite, "Explicit button confirmation creates only one immutable private note and writer lock"
                  + (expectedWrite ? "" : "; changed=\(changed), added=\(canonicalAdded), expected=\(expectedFiles)"))
        try check(try fileBytes(fixture) == core && app.messages == messages && app.reviewedMemorySuggestions.contains(report.items[0].id),
                  "Save hides the reviewed card in this process without another task or conversation write")
        await saving.save(acknowledgement: true)
        try check(try fileBytes(state) == after, "Repeated Save does not write or create a second note")
        saving.close()
        await app.openMemorySuggestion(report.items[0], report: report, text: text)
        try check(app.memorySuggestion?.preview == nil && app.memorySuggestion?.error != nil && (try fileBytes(state)) == after,
                  "A historical duplicate remains ineligible after fresh review; no retry write")
        app.memorySuggestion?.close()
        await app.openMemorySuggestion(report.items[1], report: report, text: text)
        guard let remaining = app.memorySuggestion else { throw NativeError.message("Second source missing") }
        app.newConversation()
        await remaining.save(acknowledgement: true)
        try check(remaining.saved == nil && app.memorySuggestion == nil, "Changing chats invalidates a pending suggestion review")
        app.select(UUID(uuidString: report.source["conversation_id"].text)!)
        app.setProvider("codex"); app.setComposer("Какую кобальтовую палитру используем?"); app.flushDraft()
        let beforeRecall = try fileBytes(state)
        await app.refreshContextPreview()
        try check(app.contextPreview?.manifest["knowledge_context"]["project_recall"]["selected_ids"] == .array([.string(note.id)])
                  && (try fileBytes(state)) == beforeRecall,
                  "Explicitly saved suggestion enters existing automatic project recall without manual attachment or an LLM")
        try check(!app.cloudConsent && !app.fullAccessEnabled && !app.bootstrap["context_injection"].flag,
                  "Suggestion review/save never enables cloud, tools or Context Injection")
    }

    static func seedMemorySuggestion(fixture: URL, state: URL, python: URL) throws {
        let process = Process(); process.executableURL = python; process.currentDirectoryURL = fixture
        process.arguments = ["-c", """
        import sys
        from pathlib import Path
        from native_smoke_fixture import memory_suggestion_fixture
        memory_suggestion_fixture(Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve())
        """, fixture.path, state.path]
        let scripts = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent().appendingPathComponent("scripts")
        process.environment = ProcessInfo.processInfo.environment.merging(["PYTHONPATH": scripts.path, "PYTHONDONTWRITEBYTECODE": "1"]) { _, right in right }
        let pipe = Pipe(); process.standardOutput = pipe; process.standardError = pipe
        try process.run()
        let output = pipe.fileHandleForReading.readDataToEndOfFile(); process.waitUntilExit()
        guard process.terminationStatus == 0 else { throw NativeError.message(String(decoding: output, as: UTF8.self)) }
    }
}
