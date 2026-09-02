import CryptoKit
import Foundation

struct ProjectMemoryScope: Equatable {
    let conversationID: UUID
    let workspace: String
    var parameters: [String: JSONValue] { ["conversation_id": .string(conversationID.uuidString), "workspace_root": .string(workspace)] }
    func matches(_ value: JSONValue) -> Bool {
        guard case .object(let fields) = value, Set(fields.keys) == ["path", "device", "inode"],
              case .number(let device) = value["device"], device >= 0, device.rounded() == device,
              case .number(let inode) = value["inode"], inode >= 0, inode.rounded() == inode else { return false }
        return URL(fileURLWithPath: value["path"].text).resolvingSymlinksInPath().path == URL(fileURLWithPath: workspace).resolvingSymlinksInPath().path
    }
}

struct ProjectNote: Identifiable, Equatable {
    static let kinds = ["project_fact", "preference", "decision", "lesson", "constraint"]
    let raw: JSONValue
    var id: String { raw["id"].text }
    var kind: String { raw["kind"].text }
    var content: String { raw["content"].text }
    var basis: String { raw["basis"].text }
    var active: Bool { raw["status"] == .string("active") }
    var selection: JSONValue { .object(["id": raw["id"], "record_hash": raw["record_hash"]]) }
    init(_ raw: JSONValue) throws {
        guard case .object(let fields) = raw, Set(fields.keys) == ["id", "record_hash", "saved_at", "kind", "content", "basis", "status", "supersedes_id", "verification"],
              decisionHashValue(raw["id"].text), decisionHashValue(raw["record_hash"].text), !raw["saved_at"].text.isEmpty,
              Self.kinds.contains(raw["kind"].text), ["active", "superseded"].contains(raw["status"].text),
              (1...4000).contains(raw["content"].text.unicodeScalars.count), (1...1000).contains(raw["basis"].text.unicodeScalars.count),
              raw["supersedes_id"] == .string("") || decisionHashValue(raw["supersedes_id"].text),
              raw["verification"] == .string("operator_asserted_not_independently_verified") else { throw projectMemoryError() }
        self.raw = raw
    }
    static func title(_ kind: String) -> String {
        ["project_fact": "Факт проекта", "preference": "Предпочтение", "decision": "Решение", "lesson": "Вывод", "constraint": "Ограничение"][kind] ?? kind
    }
}

func projectMemoryError() -> NativeError { .message("Заметка проекта, область или SHA-256 не прошли проверку. Ничего не прикреплено и не выполнено.") }

func verifyCanonicalMaterial(_ material: JSONValue, expected: JSONValue) throws -> String {
    guard case .string(let text) = material, let data = text.data(using: .utf8), data.count <= 512 * 1024,
          try JSONDecoder().decode(JSONValue.self, from: data) == expected else { throw projectMemoryError() }
    return SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
}

func checkProjectMemory(_ value: JSONValue, scope: ProjectMemoryScope, kind: String) throws {
    let base: Set<String> = ["schema", "conversation_id", "workspace", "read_only", "no_execution", "core_mutation_performed", "model_call_performed", "private_write_performed", "automatic_recall", "legacy_memory_migrated"]
    let extra: [String: Set<String>] = ["list": ["items", "issues", "total_count", "active_count", "matching_count", "offset", "page_size", "query", "algorithm", "directory", "limit", "notice"],
        "inspect": ["item", "record", "hash_material", "issues", "integrity"],
        "preview": ["body", "snapshot_hash", "hash_material", "preview_fingerprint", "confirmation_token", "notice"],
        "saved": ["item", "already_saved"]]
    let wrote = kind == "saved" && value["already_saved"] == .bool(false)
    guard case .object(let fields) = value, let expected = extra[kind], Set(fields.keys) == base.union(expected),
          value["schema"] == .string("proto_mind.native_project_memory_\(kind).v1"),
          UUID(uuidString: value["conversation_id"].text) == scope.conversationID, scope.matches(value["workspace"]),
          value["read_only"] == .bool(!wrote), value["no_execution"] == .bool(true), value["private_write_performed"] == .bool(wrote),
          ["core_mutation_performed", "model_call_performed", "automatic_recall", "legacy_memory_migrated"].allSatisfy({ value[$0] == .bool(false) }),
          try JSONEncoder().encode(value).count <= 2 * 1024 * 1024 else { throw projectMemoryError() }
    if kind == "preview" {
        let material = JSONValue.object(["body": value["body"], "snapshot_hash": value["snapshot_hash"]])
        let hash = try verifyCanonicalMaterial(value["hash_material"], expected: material)
        guard decisionHashValue(value["snapshot_hash"].text), value["preview_fingerprint"] == .string(hash),
              value["confirmation_token"] == .string("SAVE-PROJECT-MEMORY-" + hash.prefix(12).uppercased()),
              UUID(uuidString: value["body"]["conversation_id"].text) == scope.conversationID else { throw projectMemoryError() }
        try checkProjectNoteBody(value["body"], scope: scope)
    }
    if kind == "inspect" {
        guard case .object(let record) = value["record"], Set(record.keys) == ["schema", "namespace", "id", "saved_at", "body", "record_hash"],
              record["schema"] == .string("proto_mind.native_private_record.v1"), record["namespace"] == .string("project_memory"),
              value["integrity"] == .string("VERIFIED"),
              try verifyCanonicalMaterial(value["hash_material"], expected: .object(record.filter { $0.key != "record_hash" })) == value["record"]["record_hash"].text else { throw projectMemoryError() }
        try checkProjectNoteBody(value["record"]["body"], scope: scope)
        let item = try ProjectNote(value["item"])
        guard value["record"]["id"] == item.raw["id"], value["record"]["record_hash"] == item.raw["record_hash"],
              ["kind", "content", "basis", "supersedes_id", "verification"].allSatisfy({ item.raw[$0] == value["record"]["body"][$0] }) else { throw projectMemoryError() }
    }
}

private func checkProjectNoteBody(_ body: JSONValue, scope: ProjectMemoryScope) throws {
    guard case .object(let fields) = body,
          Set(fields.keys) == ["schema", "project_root", "workspace", "conversation_id", "kind", "content", "basis", "supersedes_id", "source", "verification", "executable", "automatic_learning"],
          body["schema"] == .string("proto_mind.native_project_memory.v1"), scope.matches(body["workspace"]),
          UUID(uuidString: body["conversation_id"].text) != nil, body["project_root"].text.hasPrefix("/"),
          body["source"] == .string("operator_explicit"), body["executable"] == .bool(false), body["automatic_learning"] == .bool(false),
          body["verification"] == .string("operator_asserted_not_independently_verified"), ProjectNote.kinds.contains(body["kind"].text),
          (1...4000).contains(body["content"].text.unicodeScalars.count), (1...1000).contains(body["basis"].text.unicodeScalars.count) else { throw projectMemoryError() }
}

func checkKnowledgeMetadata(_ value: JSONValue) throws {
    if value.isNull { return }
    let required: Set<String> = ["schema", "selection", "permission_granted", "automatic_recall", "automatic_skill_execution", "project_memory"]
    guard case .object(let fields) = value, required.isSubset(of: Set(fields.keys)), Set(fields.keys).subtracting(required).isSubset(of: ["skill_task"]),
          value["schema"] == .string("proto_mind.native_knowledge_context.v1"), value["selection"] == .string("operator_explicit"),
          ["permission_granted", "automatic_recall", "automatic_skill_execution"].allSatisfy({ value[$0] == .bool(false) }),
          case .array(let notes) = value["project_memory"], notes.count <= 5, !notes.isEmpty || fields["skill_task"] != nil,
          Set(notes.map { $0["id"].text }).count == notes.count else { throw projectMemoryError() }
    if let skill = fields["skill_task"] { try checkSkillTaskReference(skill) }
    for note in notes {
        guard case .object(let fields) = note, Set(fields.keys) == ["id", "record_hash", "kind", "workspace", "characters", "content_sha256", "verification"],
              ["id", "record_hash", "content_sha256"].allSatisfy({ decisionHashValue(note[$0].text) }), ProjectNote.kinds.contains(note["kind"].text),
              note["verification"] == .string("operator_asserted_not_independently_verified"),
              note["characters"] == .number(Double(note["characters"].integer)), (1...4000).contains(note["characters"].integer),
              ProjectMemoryScope(conversationID: UUID(), workspace: note["workspace"]["path"].text).matches(note["workspace"]),
              note["workspace"]["path"].text.hasPrefix("/") else { throw projectMemoryError() }
    }
}
