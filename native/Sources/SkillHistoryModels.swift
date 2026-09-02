import CryptoKit
import Foundation

struct SkillHistoryEntry: Identifiable {
    let raw: JSONValue
    var id: String { raw["id"].text }
    var date: String { raw["saved_at"].text }
    var receiptCount: Int { raw["receipt_count"].integer }
    var eventCount: Int { raw["event_count"].integer }
    init(_ raw: JSONValue) throws {
        guard case .object(let fields) = raw, Set(fields.keys) == ["id", "saved_at", "record_hash", "receipt_count", "event_count"],
              decisionHashValue(raw["id"].text), decisionHashValue(raw["record_hash"].text), !raw["saved_at"].text.isEmpty,
              raw["receipt_count"] == .number(Double(raw["receipt_count"].integer)), (0...40).contains(raw["receipt_count"].integer),
              raw["event_count"] == .number(Double(raw["event_count"].integer)), (0...64).contains(raw["event_count"].integer) else { throw historyError() }
        self.raw = raw
    }
}

func checkSkillHistory(_ raw: JSONValue, selection: NativeSkillInspectionSelection, kind: String) throws {
    let extras: [String: Set<String>] = ["list": ["items", "issues", "directory", "limit"],
        "preview": ["preview_fingerprint", "confirmation_token", "receipt_count", "event_count", "body", "hash_material", "notice"],
        "saved": ["record", "already_saved"], "inspect": ["record", "integrity", "current_record_state", "hash_material", "notice"]]
    let base: Set<String> = ["schema", "conversation_id", "skill_id", "workspace_path", "read_only", "no_execution", "core_mutation_performed",
                             "authority_restored", "model_call_performed", "private_write_performed"]
    guard case .object(let fields) = raw, let extra = extras[kind], Set(fields.keys) == base.union(extra),
          raw["schema"] == .string("proto_mind.native_skill_history_\(kind).v1"),
          UUID(uuidString: raw["conversation_id"].text) == selection.conversationID, raw["skill_id"] == .string(selection.skillID),
          selection.matchesWorkspace(raw["workspace_path"].text), raw["no_execution"] == .bool(true),
          ["core_mutation_performed", "authority_restored", "model_call_performed"].allSatisfy({ raw[$0] == .bool(false) }),
          try JSONEncoder().encode(raw).count <= 2 * 1024 * 1024 else { throw historyError() }
    let write = kind == "saved" && raw["already_saved"] == .bool(false)
    guard raw["private_write_performed"] == .bool(write), raw["read_only"] == .bool(!write) else { throw historyError() }
    if kind == "preview" {
        let hash = try historyHashMaterial(raw["hash_material"], expected: raw["body"])
        guard raw["preview_fingerprint"] == .string(hash), raw["confirmation_token"] == .string("SAVE-SKILL-HISTORY-" + hash.prefix(12).uppercased()) else { throw historyError() }
        try checkHistoricalBody(raw["body"], selection: selection)
    }
    if kind == "inspect" {
        guard raw["integrity"] == .string("VERIFIED"), ["MATCHES_SAVED_RECORD", "CHANGED_OR_MISSING", "UNAVAILABLE"].contains(raw["current_record_state"].text),
              case .object(let record) = raw["record"], Set(record.keys) == ["schema", "namespace", "id", "saved_at", "body", "record_hash"],
              record["schema"] == .string("proto_mind.native_private_record.v1"), record["namespace"] == .string("learning_history"),
              decisionHashValue(raw["record"]["id"].text),
              try historyHashMaterial(raw["hash_material"], expected: .object(record.filter { $0.key != "record_hash" })) == raw["record"]["record_hash"].text else { throw historyError() }
        try checkHistoricalBody(raw["record"]["body"], selection: selection)
    }
}

private func checkHistoricalBody(_ value: JSONValue, selection: NativeSkillInspectionSelection) throws {
    guard value["schema"] == .string("proto_mind.native_learning_history.v1"), value["skill_id"] == .string(selection.skillID),
          UUID(uuidString: value["conversation_id"].text) == selection.conversationID,
          value["historical_only"] == .bool(true), value["authority_restored"] == .bool(false), value["automatic_learning"] == .bool(false),
          value["quality_verification"] == .string("not_independently_verified"),
          value["receipts"].items.count <= 40, value["events"].items.count <= 64 else { throw historyError() }
}

private func historyHashMaterial(_ value: JSONValue, expected: JSONValue) throws -> String {
    // Keep Python's original numeric representation (e.g. event confidence 1.0).
    guard case .string(let material) = value, let data = material.data(using: .utf8), data.count <= 512 * 1024,
          try JSONDecoder().decode(JSONValue.self, from: data) == expected else { throw historyError() }
    return SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
}
func historyError() -> NativeError { .message("Сохранённая история или её SHA-256 не прошли проверку. Никакого восстановления разрешений или автоматического повтора.") }
