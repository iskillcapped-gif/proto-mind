import CryptoKit
import Foundation

struct NativeTurnReceipt: Equatable {
    private static let fields: Set<String> = [
        "schema", "content_free", "input_text_stored", "response_text_stored", "response_observed",
        "task_success_verified", "provider_delivery_verified", "scope", "run_id", "conversation_id",
        "provider", "mode", "input_chars", "input_sha256", "response_chars", "response_sha256",
        "answer_preview_chars", "answer_preview_sha256", "instruction_receipt_hash", "receipt_hash", "hash_material",
    ]
    private static let materialFields = fields.subtracting(["schema", "receipt_hash", "hash_material"])
    let value: JSONValue

    init(_ value: JSONValue) throws {
        guard case .object(let fields) = value, Set(fields.keys) == Self.fields,
              value["schema"] == .string("proto_mind.native_turn_receipt.v1"),
              value["content_free"] == .bool(true), value["input_text_stored"] == .bool(false),
              value["response_text_stored"] == .bool(false), value["response_observed"] == .bool(true),
              value["task_success_verified"] == .bool(false), value["provider_delivery_verified"] == .bool(false),
              value["scope"] == .string("native_turn_metadata"),
              Self.normalizedUUID(value["run_id"].text), Self.normalizedUUID(value["conversation_id"].text),
              ["codex", "ollama"].contains(value["provider"].text),
              ["chat", "full_access"].contains(value["mode"].text),
              value["provider"].text != "ollama" || value["mode"].text == "chat",
              Self.count(value["input_chars"]), Self.count(value["response_chars"]),
              Self.count(value["answer_preview_chars"], maximum: 1_650),
              ["input_sha256", "response_sha256", "answer_preview_sha256", "instruction_receipt_hash", "receipt_hash"]
                .allSatisfy({ Self.isHash(value[$0].text) }) else { throw Self.error() }
        let material = JSONValue.object(fields.filter { Self.materialFields.contains($0.key) })
        guard case .string(let materialText) = value["hash_material"],
              let bytes = materialText.data(using: .utf8), bytes.count <= 16 * 1024,
              (try? JSONDecoder().decode(JSONValue.self, from: bytes)) == material,
              value["receipt_hash"] == .string(Self.hash(materialText)) else { throw Self.error() }
        self.value = value
    }

    private static func count(_ value: JSONValue, maximum: Double = 100_000_000) -> Bool {
        guard case .number(let count) = value else { return false }
        return count.isFinite && count.rounded() == count && count >= 0 && count <= maximum
    }

    fileprivate static func normalizedUUID(_ value: String) -> Bool {
        UUID(uuidString: value)?.uuidString.lowercased() == value
    }

    static func isHash(_ value: String) -> Bool {
        value.range(of: "^[a-f0-9]{64}$", options: .regularExpression) != nil
    }

    static func hash(_ text: String) -> String {
        SHA256.hash(data: Data(text.utf8)).map { String(format: "%02x", $0) }.joined()
    }

    fileprivate static func textCount(_ text: String) -> Int { text.unicodeScalars.count }

    private static func error() -> NativeError {
        .message("Квитанция связи хода не прошла проверку. История и журнал не изменены.")
    }
}

struct NativeTurnReference: Equatable {
    private static let fields: Set<String> = [
        "schema", "content_free", "input_text_stored", "response_text_stored", "scope", "source_message_id",
        "run_id", "conversation_id", "provider", "mode", "input_chars", "input_sha256", "response_chars",
        "response_sha256", "turn_receipt_hash", "reference_hash", "hash_material",
    ]
    private static let materialFields = fields.subtracting(["schema", "reference_hash", "hash_material"])
    let value: JSONValue

    init(_ value: JSONValue) throws {
        guard case .object(let fields) = value, Set(fields.keys) == Self.fields,
              value["schema"] == .string("proto_mind.native_turn_reference.v1"),
              value["content_free"] == .bool(true), value["input_text_stored"] == .bool(false),
              value["response_text_stored"] == .bool(false), value["scope"] == .string("native_chat_to_work_session"),
              Self.normalizedUUID(value["source_message_id"].text), Self.normalizedUUID(value["run_id"].text),
              Self.normalizedUUID(value["conversation_id"].text), ["codex", "ollama"].contains(value["provider"].text),
              ["chat", "full_access"].contains(value["mode"].text),
              value["provider"].text != "ollama" || value["mode"].text == "chat",
              Self.count(value["input_chars"]), Self.count(value["response_chars"]),
              ["input_sha256", "response_sha256", "turn_receipt_hash", "reference_hash"]
                .allSatisfy({ NativeTurnReceipt.isHash(value[$0].text) }) else { throw Self.error() }
        let material = JSONValue.object(fields.filter { Self.materialFields.contains($0.key) })
        guard case .string(let materialText) = value["hash_material"],
              let bytes = materialText.data(using: .utf8), bytes.count <= 16 * 1024,
              (try? JSONDecoder().decode(JSONValue.self, from: bytes)) == material,
              value["reference_hash"] == .string(NativeTurnReceipt.hash(materialText)) else { throw Self.error() }
        self.value = value
    }

    static func make(receipt rawReceipt: JSONValue, source: ChatMessage, conversation: UUID, response: String) throws -> JSONValue {
        let receipt = try NativeTurnReceipt(rawReceipt)
        let inputHash = NativeTurnReceipt.hash(source.text)
        let responseHash = NativeTurnReceipt.hash(response)
        guard source.role == "user", !source.isError, source.operatorInput != true,
              receipt.value["conversation_id"].text == conversation.uuidString.lowercased(),
              receipt.value["input_chars"].integer == NativeTurnReceipt.textCount(source.text),
              receipt.value["input_sha256"] == .string(inputHash),
              receipt.value["response_chars"].integer == NativeTurnReceipt.textCount(response),
              receipt.value["response_sha256"] == .string(responseHash) else { throw Self.error() }
        let material: [String: JSONValue] = [
            "content_free": .bool(true), "input_text_stored": .bool(false), "response_text_stored": .bool(false),
            "scope": .string("native_chat_to_work_session"), "source_message_id": .string(source.id.uuidString.lowercased()),
            "run_id": receipt.value["run_id"], "conversation_id": receipt.value["conversation_id"],
            "provider": receipt.value["provider"], "mode": receipt.value["mode"],
            "input_chars": receipt.value["input_chars"], "input_sha256": receipt.value["input_sha256"],
            "response_chars": receipt.value["response_chars"], "response_sha256": receipt.value["response_sha256"],
            "turn_receipt_hash": receipt.value["receipt_hash"],
        ]
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys, .withoutEscapingSlashes]
        let encoded = try encoder.encode(JSONValue.object(material))
        guard let text = String(data: encoded, encoding: .utf8) else { throw Self.error() }
        return try NativeTurnReference(.object(material.merging([
            "schema": .string("proto_mind.native_turn_reference.v1"),
            "reference_hash": .string(NativeTurnReceipt.hash(text)), "hash_material": .string(text),
        ]) { _, new in new })).value
    }

    func matches(source: ChatMessage, assistant: ChatMessage, conversation: UUID) -> Bool {
        let response = assistant.raw.isEmpty ? assistant.text : assistant.raw
        return assistant.role == "assistant" && !assistant.isError && assistant.operatorInput != true
            && source.role == "user" && !source.isError && source.operatorInput != true
            && value["source_message_id"].text == source.id.uuidString.lowercased()
            && value["conversation_id"].text == conversation.uuidString.lowercased()
            && value["input_chars"].integer == NativeTurnReceipt.textCount(source.text)
            && value["input_sha256"] == .string(NativeTurnReceipt.hash(source.text))
            && value["response_chars"].integer == NativeTurnReceipt.textCount(response)
            && value["response_sha256"] == .string(NativeTurnReceipt.hash(response))
    }

    func matches(run: NativeWorkSession) -> Bool {
        guard let receipt = run.turnReceipt else { return false }
        return value["run_id"] == receipt.value["run_id"]
            && value["conversation_id"] == receipt.value["conversation_id"]
            && value["provider"] == receipt.value["provider"] && value["mode"] == receipt.value["mode"]
            && value["input_chars"] == receipt.value["input_chars"] && value["input_sha256"] == receipt.value["input_sha256"]
            && value["response_chars"] == receipt.value["response_chars"] && value["response_sha256"] == receipt.value["response_sha256"]
            && value["turn_receipt_hash"] == receipt.value["receipt_hash"]
    }

    func resolve(in runs: [NativeWorkSession], conversation: UUID) throws -> NativeWorkSession {
        guard value["conversation_id"].text == conversation.uuidString.lowercased(),
              let run = runs.first(where: { $0.id == value["run_id"].text }), matches(run: run) else { throw Self.error() }
        return run
    }

    private static func count(_ value: JSONValue) -> Bool {
        guard case .number(let count) = value else { return false }
        return count.isFinite && count.rounded() == count && count >= 0 && count <= 100_000_000
    }

    private static func normalizedUUID(_ value: String) -> Bool { NativeTurnReceipt.normalizedUUID(value) }

    private static func error() -> NativeError {
        .message("Ответ не удалось связать с точным сохранённым запуском. Ничего не открыто и не повторено.")
    }
}

func validateTurnLineageHistory(_ messages: [ChatMessage], conversation: UUID) throws {
    var sourceIDs = Set<UUID>()
    var runIDs = Set<String>()
    for (index, message) in messages.enumerated() {
        guard let raw = message.turnReference else { continue }
        let reference = try NativeTurnReference(raw)
        guard index > 0,
              let sourceID = UUID(uuidString: reference.value["source_message_id"].text),
              messages[index - 1].id == sourceID,
              !sourceIDs.contains(sourceID), !runIDs.contains(reference.value["run_id"].text),
              reference.matches(source: messages[index - 1], assistant: message, conversation: conversation) else {
            throw NativeError.message("История содержит непроверяемую связь ответа с запуском. Файл не изменён.")
        }
        sourceIDs.insert(sourceID)
        runIDs.insert(reference.value["run_id"].text)
    }
}
