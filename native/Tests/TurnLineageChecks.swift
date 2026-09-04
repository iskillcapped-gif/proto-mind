import CryptoKit
import Foundation

extension NativeChecks {
    static func turnReceiptFixture(prompt: String, response: String, conversation: UUID, run: UUID) throws -> JSONValue {
        let instruction = try instructionReceiptFixture()
        let preview = String(response.prefix(1_600))
        let material: [String: JSONValue] = [
            "content_free": .bool(true), "input_text_stored": .bool(false), "response_text_stored": .bool(false),
            "response_observed": .bool(true), "task_success_verified": .bool(false), "provider_delivery_verified": .bool(false),
            "scope": .string("native_turn_metadata"), "run_id": .string(run.uuidString.lowercased()),
            "conversation_id": .string(conversation.uuidString.lowercased()), "provider": .string("codex"), "mode": .string("chat"),
            "input_chars": .number(Double(prompt.unicodeScalars.count)), "input_sha256": .string(NativeTurnReceipt.hash(prompt)),
            "response_chars": .number(Double(response.unicodeScalars.count)), "response_sha256": .string(NativeTurnReceipt.hash(response)),
            "answer_preview_chars": .number(Double(preview.unicodeScalars.count)), "answer_preview_sha256": .string(NativeTurnReceipt.hash(preview)),
            "instruction_receipt_hash": instruction["receipt_hash"],
        ]
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys, .withoutEscapingSlashes]
        let bytes = try encoder.encode(JSONValue.object(material))
        let text = String(data: bytes, encoding: .utf8)!
        return .object(material.merging([
            "schema": .string("proto_mind.native_turn_receipt.v1"),
            "receipt_hash": .string(NativeTurnReceipt.hash(text)), "hash_material": .string(text),
        ]) { _, new in new })
    }

    static func turnLineageContracts(root: URL) throws {
        let prompt = "Проверь точный запуск"
        let response = "Ответ связан с журналом"
        let conversation = UUID(), runID = UUID()
        let receipt = try turnReceiptFixture(prompt: prompt, response: response, conversation: conversation, run: runID)
        let parsed = try NativeTurnReceipt(receipt)
        try check(parsed.value["response_text_stored"] == .bool(false), "Native turn receipt validates content-free response evidence")

        let source = ChatMessage(role: "user", text: prompt)
        let referenceValue = try NativeTurnReference.make(receipt: receipt, source: source, conversation: conversation, response: response)
        let reference = try NativeTurnReference(referenceValue)
        let assistant = ChatMessage(role: "assistant", text: response, raw: response, turnReference: referenceValue)
        try check(reference.matches(source: source, assistant: assistant, conversation: conversation),
                  "Native history reference closes user message, exact response and conversation")

        var gappedHistoryRefused = false
        do {
            try validateTurnLineageHistory(
                [source, ChatMessage(role: "report", text: "intervening report"), assistant],
                conversation: conversation
            )
        } catch { gappedHistoryRefused = true }
        try check(gappedHistoryRefused, "Turn lineage requires the exact immediately preceding user message")

        var chat = Conversation(); chat.id = conversation; chat.messages = [source, assistant]
        let state = root.appendingPathComponent("turn-lineage-history")
        let store = ChatStore(directory: state)
        try store.save(ChatArchive(conversations: [chat], selectedID: conversation))
        let before = try fileBytes(state)
        let restored = try store.load().conversations[0]
        try check(restored.messages[1].turnReference == referenceValue && (try fileBytes(state)) == before,
                  "Strict turn lineage survives restart without rewriting private history")

        var legacy = Conversation(); legacy.messages = [ChatMessage(role: "user", text: "old"), ChatMessage(role: "assistant", text: "history")]
        let legacyState = root.appendingPathComponent("turn-lineage-legacy")
        let legacyStore = ChatStore(directory: legacyState)
        try legacyStore.save(ChatArchive(conversations: [legacy], selectedID: legacy.id))
        let legacyBefore = try fileBytes(legacyState)
        try check(try legacyStore.load().conversations[0] == legacy && fileBytes(legacyState) == legacyBefore,
                  "History without turn lineage remains readable with no migration")

        var changedSourceMessage = source
        changedSourceMessage.text = "changed"
        for (name, changedSource, changedAssistant, changedConversation) in [
            ("source text", changedSourceMessage, assistant, conversation),
            ("response text", source, ChatMessage(role: "assistant", text: "changed", raw: "changed", turnReference: referenceValue), conversation),
            ("conversation", source, assistant, UUID()),
        ] {
            try check(!reference.matches(source: changedSource, assistant: changedAssistant, conversation: changedConversation),
                      "Turn lineage rejects changed \(name)")
        }

        guard case .object(var changedReference) = referenceValue else { throw NativeError.message("Expected turn reference") }
        changedReference["run_id"] = .string(UUID().uuidString.lowercased())
        var badHashRefused = false
        do { _ = try NativeTurnReference(.object(changedReference)) } catch { badHashRefused = true }
        try check(badHashRefused, "Turn lineage rejects a relabelled run without a matching hash")

        var runFields: [String: JSONValue] = [
            "schema": .string("proto_mind.native_work_session.v1"), "id": .string(runID.uuidString.lowercased()),
            "conversation_id": .string(conversation.uuidString.lowercased()), "status": .string("completed"),
            "display_status": .string("completed"), "verification": .string("not_assessed"), "acceptance": .string("not_recorded"),
            "automatic_resume": .bool(false), "fingerprint": .string(String(repeating: "f", count: 64)),
            "tools": .array([]), "context_manifest": .null, "auto_skills": .null, "agent_contract": .null,
            "instruction_receipt": try instructionReceiptFixture(), "turn_receipt": receipt,
            "provider": .string("codex"), "access_mode": .string("chat"),
            "input_chars": receipt["input_chars"], "input_sha256": receipt["input_sha256"],
            "answer_preview": .string(String(response.prefix(1_600))),
        ]
        let run = try NativeWorkSession(.object(runFields))
        try check(try reference.resolve(in: [run], conversation: conversation) == run,
                  "Message reference resolves only the exact journal run")
        runFields["fingerprint"] = .string(String(repeating: "e", count: 64))
        let reviewed = try NativeWorkSession(.object(runFields))
        try check(try reference.resolve(in: [reviewed], conversation: conversation) == reviewed,
                  "Operator review may change the run fingerprint without breaking stable turn lineage")
        var missingRefused = false
        do { _ = try reference.resolve(in: [], conversation: conversation) } catch { missingRefused = true }
        try check(missingRefused, "Missing journal evidence is never guessed from adjacent runs")
    }
}
