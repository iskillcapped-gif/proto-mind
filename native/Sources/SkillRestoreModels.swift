import CryptoKit
import Foundation

private let restoreFields: [JSONValue] = ["lifecycle", "status", "updated_at"].map(JSONValue.string)
private let restoreReceiptFields: Set<String> = ["restore_apply_id", "applied_at", "skill_id", "restore_review_hash",
    "restore_metadata_id", "restore_metadata_hash", "prior_archive_id", "prior_archive_hash", "before_store_sha256", "after_store_sha256",
    "before_record_hash", "after_record_hash", "exact_record_mutations", "changed_fields", "confirmation_token_hash", "post_state_verified",
    "archive_evidence_preserved", "durable_provenance_preserved", "persistent_memory_unchanged", "rollback_performed", "receipt_hash"]
private let restoreTokenFields: Set<String> = ["skill_id", "authorization_blueprint_hash", "restore_review_hash", "restore_metadata_blueprint_hash",
    "before_store_sha256", "before_record_hash", "prior_archive_id", "prior_archive_hash", "expected_changed_fields", "immutable_record_fields"]

struct NativeSkillRestoreReceipt {
    let raw: JSONValue
    var id: String { raw["restore_apply_id"].text }
    var verification: String { raw["verification_status"].text }
    var current: Bool { raw["evidence_state"] == .string("CURRENT") }

    static func decode(_ value: JSONValue, selection: NativeSkillInspectionSelection) throws -> Self {
        let extra: Set<String> = ["verification_status", "evidence_state", "detailed_receipt_persistence", "restore_metadata_persistence", "warnings"]
        guard case .object(let fields) = value, Set(fields.keys) == restoreReceiptFields.union(extra),
              value["skill_id"] == .string(selection.skillID), value["exact_record_mutations"] == .number(1),
              value["changed_fields"] == .array(restoreFields), value["rollback_performed"] == .bool(false),
              ["post_state_verified", "archive_evidence_preserved", "durable_provenance_preserved", "persistent_memory_unchanged"].allSatisfy({ value[$0] == .bool(true) }),
              ["restore_apply_id", "restore_metadata_id", "prior_archive_id"].allSatisfy({ decisionID(value[$0].text) }),
              ["restore_review_hash", "restore_metadata_hash", "prior_archive_hash", "before_store_sha256", "after_store_sha256", "before_record_hash",
               "after_record_hash", "confirmation_token_hash", "receipt_hash"].allSatisfy({ decisionHashValue(value[$0].text) }),
              value["before_store_sha256"] != value["after_store_sha256"], value["before_record_hash"] != value["after_record_hash"],
              !value["applied_at"].text.isEmpty, value["applied_at"].text.count <= 100,
              ["VERIFIED", "ERROR", "UNAVAILABLE"].contains(value["verification_status"].text),
              ["CURRENT", "HISTORICAL", "UNAVAILABLE"].contains(value["evidence_state"].text),
              (value["verification_status"] == .string("VERIFIED") ? value["evidence_state"] != .string("UNAVAILABLE") : value["evidence_state"] == .string("UNAVAILABLE")),
              value["detailed_receipt_persistence"] == .string("process_memory_only"), value["restore_metadata_persistence"] == .string("skill_record"),
              validRestoreFindings(value["warnings"]) else { throw restoreError() }
        let core = fields.filter { restoreReceiptFields.contains($0.key) }
        guard try restoreHash(.object(core.filter { $0.key != "receipt_hash" })) == value["receipt_hash"].text,
              try "skillrestoreapply_" + restoreHash(.object(core.filter { !["receipt_hash", "restore_apply_id"].contains($0.key) })).prefix(16) == value["restore_apply_id"].text else { throw restoreError() }
        return Self(raw: value)
    }
}

struct NativeSkillRestoreReview {
    let raw: JSONValue
    let receipt: NativeSkillRestoreReceipt?
    var ready: Bool { raw["can_restore"].flag }
    var name: String { raw["name"].text }
    var status: String { raw["status"].text }
    static func decode(_ value: JSONValue, selection: NativeSkillInspectionSelection) throws -> Self {
        try restoreEnvelope(value, selection: selection, kind: "review", fields: ["status", "name", "stored_skill_status", "can_restore",
            "native_restore_slot_available", "context_injection_disabled", "store_hashes", "checks", "reasons", "issues", "warnings", "receipt", "skill_store_scope", "project_isolation_enforced"])
        let receipt = value["receipt"].isNull ? nil : try NativeSkillRestoreReceipt.decode(value["receipt"], selection: selection)
        guard ["READY", "NOT_READY", "RESTORED", "ERROR"].contains(value["status"].text), value["name"].text.count <= 200,
              ["active", "archived", "unavailable"].contains(value["stored_skill_status"].text),
              value["can_restore"] == .bool(value["status"] == .string("READY")),
              ["native_restore_slot_available", "context_injection_disabled"].allSatisfy({ value[$0] == .bool(true) || value[$0] == .bool(false) }),
              ["reasons", "issues", "warnings"].allSatisfy({ validRestoreFindings(value[$0]) }), validRestoreStores(value["store_hashes"]),
              value["skill_store_scope"] == .string("global_legacy_stores"), value["project_isolation_enforced"] == .bool(false),
              case .object(let checks) = value["checks"], checks.count <= 40, checks.keys.allSatisfy({ $0.count <= 160 }),
              checks.values.allSatisfy({ $0 == .bool(true) || $0 == .bool(false) }) else { throw restoreError() }
        if value["can_restore"].flag {
            guard value["stored_skill_status"] == .string("archived"), value["context_injection_disabled"].flag,
                  value["native_restore_slot_available"].flag, value["store_hashes"].objectCount == 3,
                  !checks.isEmpty, checks.values.allSatisfy({ $0 == .bool(true) }),
                  value["reasons"].items.isEmpty, value["issues"].items.isEmpty, receipt == nil else { throw restoreError() }
        }
        if receipt != nil {
            guard !value["can_restore"].flag, !value["native_restore_slot_available"].flag,
                  ["RESTORED", "ERROR"].contains(value["status"].text) else { throw restoreError() }
        } else if value["status"] == .string("RESTORED") { throw restoreError() }
        return Self(raw: value, receipt: receipt)
    }
}

struct NativeSkillRestorePreview {
    let raw: JSONValue
    var ready: Bool { raw["ready"].flag }
    var token: String { raw["confirmation_token"].text }
    var fingerprint: String { raw["preview_fingerprint"].text }
    func accepts(_ text: String, acknowledgement: Bool) -> Bool { ready && acknowledgement && text == token }
    static func decode(_ value: JSONValue, selection: NativeSkillInspectionSelection) throws -> Self {
        try restoreEnvelope(value, selection: selection, kind: "preview", fields: ["ready", "reasons", "preview_fingerprint", "confirmation_token", "token_material",
            "expected_record_mutations", "expected_changed_fields", "future_mutation", "requires_global_skills_acknowledgement", "store_hashes"])
        guard validRestoreFindings(value["reasons"]), value["ready"] == .bool(value["reasons"].items.isEmpty),
              decisionHashValue(value["preview_fingerprint"].text), value["expected_record_mutations"] == .number(1),
              value["expected_changed_fields"] == .array(restoreFields), value["future_mutation"] == .string("skills_one_durable_restore"),
              value["requires_global_skills_acknowledgement"] == .bool(true), validRestoreStores(value["store_hashes"]),
              case .object(let material) = value["token_material"] else { throw restoreError() }
        if value["ready"].flag {
            guard Set(material.keys) == restoreTokenFields, material["skill_id"] == .string(selection.skillID),
                  material["expected_changed_fields"] == .array(restoreFields), value["store_hashes"].objectCount == 3,
                  material["before_store_sha256"] == value["store_hashes"]["skills.jsonl"],
                  restoreTokenFields.filter({ $0.contains("hash") || $0.contains("sha256") }).allSatisfy({ decisionHashValue(material[$0]?.text ?? "") }),
                  decisionID(material["prior_archive_id"]?.text ?? ""), let immutable = material["immutable_record_fields"],
                  !immutable.items.isEmpty, immutable.items.count <= 40, immutable.items.allSatisfy({ !$0.text.isEmpty && $0.text.count <= 200 }),
                  try value["confirmation_token"].text == "CONFIRM-DURABLE-SKILL-RESTORE-" + restoreHash(.object(material)).prefix(12).uppercased() else { throw restoreError() }
        } else if !value["confirmation_token"].text.isEmpty || !material.isEmpty { throw restoreError() }
        return Self(raw: value)
    }
}

func decodeSkillRestoreResult(_ value: JSONValue, selection: NativeSkillInspectionSelection, preview: NativeSkillRestorePreview) throws -> NativeSkillRestoreReceipt {
    try restoreEnvelope(value, selection: selection, kind: "result", fields: ["mutation", "events_appended", "receipt"])
    let receipt = try NativeSkillRestoreReceipt.decode(value["receipt"], selection: selection)
    guard value["mutation"] == .string("skills_one_durable_restore"), value["events_appended"] == .number(0),
          receipt.raw["before_store_sha256"] == preview.raw["token_material"]["before_store_sha256"],
          receipt.raw["before_record_hash"] == preview.raw["token_material"]["before_record_hash"],
          receipt.raw["restore_review_hash"] == preview.raw["token_material"]["restore_review_hash"],
          receipt.raw["prior_archive_hash"] == preview.raw["token_material"]["prior_archive_hash"] else { throw restoreError() }
    return receipt
}

private func restoreEnvelope(_ value: JSONValue, selection: NativeSkillInspectionSelection, kind: String, fields: Set<String>) throws {
    let falseFlags: Set<String> = ["model_call_performed", "network_call_performed", "retrieval_performed", "context_injection_changed", "permissions_changed",
        "consent_state_changed", "automatic_promotion", "session_log_mutation_performed", "memory_mutation_performed", "experience_mutation_performed", "batch_apply_performed"]
    let base: Set<String> = ["schema", "conversation_id", "skill_id", "workspace_path", "read_only", "no_execution", "store_mutation_performed", "skill_mutation_performed"]
    guard case .object(let root) = value, Set(root.keys) == base.union(falseFlags).union(fields),
          value["schema"] == .string("proto_mind.native_skill_restore_\(kind).v1"), value["read_only"] == .bool(kind != "result"),
          value["no_execution"] == .bool(true), value["store_mutation_performed"] == .bool(kind == "result"), value["skill_mutation_performed"] == .bool(kind == "result"),
          falseFlags.allSatisfy({ value[$0] == .bool(false) }), let conversation = selection.conversationID,
          UUID(uuidString: value["conversation_id"].text) == conversation, value["skill_id"] == .string(selection.skillID),
          selection.matchesWorkspace(value["workspace_path"].text), try JSONEncoder().encode(value).count <= 256_000 else { throw restoreError() }
}

private func validRestoreFindings(_ value: JSONValue) -> Bool {
    guard case .array(let items) = value else { return false }
    return items.count <= 33 && items.allSatisfy { if case .string(let text) = $0 { return text.count <= 1000 }; return false }
}
private func validRestoreStores(_ value: JSONValue) -> Bool {
    guard case .object(let fields) = value else { return false }
    return Set(fields.keys).isSubset(of: ["skills.jsonl", "persistent_memory.json", "context_injection.json"]) && fields.values.allSatisfy({ decisionHashValue($0.text) })
}
private func restoreHash(_ value: JSONValue) throws -> String {
    let encoder = JSONEncoder(); encoder.outputFormatting = [.sortedKeys, .withoutEscapingSlashes]
    return SHA256.hash(data: try encoder.encode(value)).map { String(format: "%02x", $0) }.joined()
}
private extension JSONValue {
    var objectCount: Int { if case .object(let value) = self { return value.count }; return 0 }
}
private func restoreError() -> NativeError { .message("Не удалось проверить контракт восстановления. Автоповтора нет; проверьте навык и квитанцию.") }
