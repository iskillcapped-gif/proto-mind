import CryptoKit
import Foundation

func skillTaskError() -> NativeError {
    .message("Подготовка навыка, цель или область изменились. Перепроверьте форму либо уберите навык; автоматической замены нет.")
}

private let skillTaskReferenceFields: Set<String> = ["schema", "conversation_id", "workspace", "skill_id", "skill_name", "preview_fingerprint", "skill_record_hash", "source_lesson_id", "provenance_id", "provenance_hash", "contract_hash", "lifecycle_state", "store_hashes", "goal_sha256", "criteria_sha256", "provider", "access_mode", "execution_path", "quality_verification", "shared_skill_library"]

func checkSkillTaskReference(_ value: JSONValue) throws {
    guard case .object(let fields) = value, Set(fields.keys) == skillTaskReferenceFields,
          value["schema"] == .string("proto_mind.native_skill_task_reference.v1"),
          UUID(uuidString: value["conversation_id"].text) != nil,
          ["preview_fingerprint", "skill_record_hash", "provenance_hash", "contract_hash", "goal_sha256", "criteria_sha256"].allSatisfy({ decisionHashValue(value[$0].text) }),
          ["skill_id", "source_lesson_id", "provenance_id"].allSatisfy({ value[$0].text.range(of: "^[A-Za-z0-9_.:-]{1,200}$", options: .regularExpression) != nil }),
          (1...800).contains(value["skill_name"].text.unicodeScalars.count),
          ["active_verified", "active_restored_verified"].contains(value["lifecycle_state"].text),
          ["codex", "ollama", "mock"].contains(value["provider"].text),
          ["chat", "full_access"].contains(value["access_mode"].text),
          value["access_mode"] != .string("full_access") || value["provider"] == .string("codex"),
          value["execution_path"] == .string("existing_operator_sent_provider_turn"), value["quality_verification"] == .string("not_assessed"),
          value["shared_skill_library"] == .bool(true),
          case .object(let hashes) = value["store_hashes"], Set(hashes.keys) == ["skills.jsonl", "persistent_memory.json", "context_injection.json"],
          hashes.values.allSatisfy({ decisionHashValue($0.text) }), value["workspace"]["path"].text.hasPrefix("/"),
          ProjectMemoryScope(conversationID: UUID(), workspace: value["workspace"]["path"].text).matches(value["workspace"]) else { throw skillTaskError() }
}

func skillTaskReference(body: JSONValue, fingerprint: String) -> JSONValue {
    var fields = Dictionary(uniqueKeysWithValues: skillTaskReferenceFields.map { ($0, body[$0]) })
    fields["schema"] = .string("proto_mind.native_skill_task_reference.v1")
    fields["preview_fingerprint"] = .string(fingerprint)
    fields["goal_sha256"] = .string(SHA256.hash(data: Data(body["goal"].text.utf8)).map { String(format: "%02x", $0) }.joined())
    fields["criteria_sha256"] = body["success_criteria"]["sha256"]
    return .object(fields)
}

func checkSkillTaskBody(_ body: JSONValue, scope: ProjectMemoryScope) throws {
    let fields: Set<String> = ["schema", "conversation_id", "project_root", "workspace", "skill_id", "skill_name", "skill_record_hash", "source_lesson_id", "provenance_id", "provenance_hash", "lifecycle_state", "store_hashes", "contract", "contract_hash", "goal", "success_criteria", "provider", "access_mode", "execution_path", "skill_interpreter_installed", "permission_granted", "automatic_execution", "automatic_learning", "quality_verification", "shared_skill_library"]
    guard case .object(let values) = body, Set(values.keys) == fields, body["schema"] == .string("proto_mind.native_skill_task.v1"),
          UUID(uuidString: body["conversation_id"].text) == scope.conversationID, scope.matches(body["workspace"]), body["project_root"].text.hasPrefix("/"),
          ["skill_interpreter_installed", "permission_granted", "automatic_execution", "automatic_learning"].allSatisfy({ body[$0] == .bool(false) }),
          body["goal"].text.unicodeScalars.count <= 4000, NativeTaskCriteria.validContract(body["success_criteria"]),
          case .object(let contract) = body["contract"], Set(contract.keys) == ["name", "summary", "trigger", "preconditions", "steps", "permissions", "verification", "known_failure_modes"],
          ["name", "summary", "trigger"].allSatisfy({ (1...800).contains(body["contract"][$0].text.unicodeScalars.count) }) else { throw skillTaskError() }
    for key in ["preconditions", "steps", "permissions", "verification", "known_failure_modes"] {
        guard case .array(let rows) = body["contract"][key], rows.count <= (key == "steps" ? 16 : 8),
              !rows.isEmpty, rows.allSatisfy({ (1...800).contains($0.text.unicodeScalars.count) }) else { throw skillTaskError() }
    }
    // An incomplete form can show the verified procedure but cannot produce a selection.
    var reference = skillTaskReference(body: body, fingerprint: String(repeating: "0", count: 64))
    if body["success_criteria"].isNull, case .object(var values) = reference {
        values["criteria_sha256"] = .string(String(repeating: "0", count: 64)); reference = .object(values)
    }
    try checkSkillTaskReference(reference)
}

struct NativeSkillTaskPreview: Equatable {
    let raw: JSONValue
    var body: JSONValue { raw["body"] }
    var ready: Bool { raw["status"] == .string("READY") }
    var fingerprint: String { raw["preview_fingerprint"].text }
    var reasons: [String] {
        raw["reasons"].items.map {
            switch $0.text {
            case "Enter the operator goal before preparing a task.": return "Заполните цель задачи."
            case "Declare at least one observable success criterion before Send.": return "Добавьте хотя бы один наблюдаемый критерий результата."
            case "Slash, natural command and exit routes cannot be wrapped as skill tasks.": return "Команды Proto-Mind и выход не оборачиваются в задачу с навыком. Введите обычную цель."
            default: return $0.text
            }
        }
    }
    init(_ raw: JSONValue, scope: ProjectMemoryScope, skillID: String) throws {
        guard case .object(let fields) = raw,
              Set(fields.keys) == ["schema", "conversation_id", "workspace", "skill_id", "status", "reasons", "warnings", "body", "hash_material", "preview_fingerprint", "read_only", "no_execution", "permission_granted", "store_mutation_performed", "model_call_performed"],
              raw["schema"] == .string("proto_mind.native_skill_task_preview.v1"), UUID(uuidString: raw["conversation_id"].text) == scope.conversationID,
              scope.matches(raw["workspace"]), raw["skill_id"] == .string(skillID),
              ["READY", "NOT_READY"].contains(raw["status"].text), raw["read_only"] == .bool(true), raw["no_execution"] == .bool(true),
              ["permission_granted", "store_mutation_performed", "model_call_performed"].allSatisfy({ raw[$0] == .bool(false) }),
              case .array(let reasons) = raw["reasons"], case .array(let warnings) = raw["warnings"],
              reasons.count <= 32, warnings.count <= 128, (reasons + warnings).allSatisfy({ !$0.text.isEmpty }),
              try JSONEncoder().encode(raw).count <= 128 * 1024 else { throw skillTaskError() }
        if raw["body"].isNull {
            guard raw["status"] == .string("NOT_READY"), !reasons.isEmpty, raw["hash_material"] == .string(""), raw["preview_fingerprint"] == .string("") else { throw skillTaskError() }
        } else {
            try checkSkillTaskBody(raw["body"], scope: scope)
            let hash = try verifyCanonicalMaterial(raw["hash_material"], expected: raw["body"])
            guard raw["body"]["skill_id"] == .string(skillID), raw["body"]["workspace"] == raw["workspace"] else { throw skillTaskError() }
            if raw["status"] == .string("READY") {
                guard reasons.isEmpty, raw["preview_fingerprint"] == .string(hash), !raw["body"]["goal"].text.isEmpty,
                      !raw["body"]["success_criteria"].isNull else { throw skillTaskError() }
            } else if reasons.isEmpty || raw["preview_fingerprint"] != .string("") { throw skillTaskError() }
        }
        self.raw = raw
    }
}

struct PreparedSkillTask: Equatable {
    let preview: NativeSkillTaskPreview
    var body: JSONValue { preview.body }
    var skillID: String { body["skill_id"].text }
    var goal: String { body["goal"].text }
    var criteria: [String] { body["success_criteria"]["items"].items.map { $0["text"].text } }
    var reference: JSONValue { skillTaskReference(body: body, fingerprint: preview.fingerprint) }
    var selection: JSONValue { .object(["skill_id": .string(skillID), "goal": .string(goal), "criteria": .array(criteria.map(JSONValue.string)), "preview_fingerprint": .string(preview.fingerprint)]) }
    init(_ preview: NativeSkillTaskPreview) throws {
        guard preview.ready else { throw skillTaskError() }
        try checkSkillTaskReference(skillTaskReference(body: preview.body, fingerprint: preview.fingerprint))
        self.preview = preview
    }
}
