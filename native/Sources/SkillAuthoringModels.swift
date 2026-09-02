import Foundation

struct NativeSkillEvidence: Decodable {
    let schema: String
    let readOnly: Bool
    let noExecution: Bool
    let storeMutationPerformed: Bool
    let status: String
    let skillId: String
    let provenanceId: String
    let sourceLessonId: String
    let sourceStatus: String
    let currentPayloadMatches: Bool
    let issues: [String]
    let warnings: [String]
    let verified: Bool

    var isSafe: Bool {
        schema == "proto_mind.native_skill_evidence.v1" && readOnly && noExecution && !storeMutationPerformed &&
        ["UNAVAILABLE", "ERROR", "VERIFIED", "HISTORICAL", "DRIFTED"].contains(status) && skillID(skillId) &&
        (sourceLessonId.isEmpty || skillID(sourceLessonId)) && (provenanceId.isEmpty || skillID(provenanceId)) &&
        skillFindings(issues) && skillFindings(warnings) && (!verified || (issues.isEmpty && !provenanceId.isEmpty)) &&
        (status != "VERIFIED" || (verified && currentPayloadMatches && sourceStatus == "current"))
    }
}

enum NativeSkillOperation: String, Decodable {
    case author, apply
    var title: String { self == .author ? "Подтвердить описание" : "Сохранить один навык" }
    var mutation: String { self == .author ? "process_memory_only" : "skills_one_record" }
    var tokenPrefix: String { self == .author ? "CONFIRM-SKILL-AUTHOR-" : "CONFIRM-SKILL-APPLY-" }
}

struct NativeSkillFields: Codable, Equatable {
    var name = ""
    var summary = ""
    var trigger = ""
    var preconditions: [String] = []
    var steps: [String] = []
    var permissions: [String] = []
    var verification: [String] = []
    var knownFailureModes: [String] = []

    var json: JSONValue {
        .object(["name": .string(name), "summary": .string(summary), "trigger": .string(trigger),
                 "preconditions": .array(preconditions.map(JSONValue.string)), "steps": .array(steps.map(JSONValue.string)),
                 "permissions": .array(permissions.map(JSONValue.string)), "verification": .array(verification.map(JSONValue.string)),
                 "known_failure_modes": .array(knownFailureModes.map(JSONValue.string))])
    }

    var bounded: Bool {
        let groups = [preconditions, steps, permissions, verification, knownFailureModes]
        return [name, summary, trigger].allSatisfy(skillText) &&
            zip(groups, [8, 16, 8, 8, 8]).allSatisfy { values, limit in
                values.count <= limit && values.allSatisfy { !$0.trimmingCharacters(in: .whitespaces).isEmpty && skillText($0) }
            }
    }

    var complete: Bool {
        bounded && [name, summary, trigger].allSatisfy { !$0.trimmingCharacters(in: .whitespaces).isEmpty } &&
            [preconditions, steps, permissions, verification, knownFailureModes].allSatisfy { !$0.isEmpty }
    }
}

struct NativeSkillDraft: Equatable {
    var name = ""
    var summary = ""
    var trigger = ""
    var preconditions = ""
    var steps = ""
    var permissions = ""
    var verification = ""
    var failures = ""

    init(_ fields: NativeSkillFields = NativeSkillFields()) {
        name = fields.name; summary = fields.summary; trigger = fields.trigger
        preconditions = fields.preconditions.joined(separator: "\n"); steps = fields.steps.joined(separator: "\n")
        permissions = fields.permissions.joined(separator: "\n"); verification = fields.verification.joined(separator: "\n")
        failures = fields.knownFailureModes.joined(separator: "\n")
    }

    var fields: NativeSkillFields {
        func lines(_ text: String) -> [String] {
            text.components(separatedBy: .newlines).map { $0.trimmingCharacters(in: .whitespaces) }.filter { !$0.isEmpty }
        }
        return NativeSkillFields(name: name, summary: summary, trigger: trigger,
            preconditions: lines(preconditions), steps: lines(steps), permissions: lines(permissions),
            verification: lines(verification), knownFailureModes: lines(failures))
    }
}

struct NativeSkillSelection: Equatable {
    let conversationID: UUID
    let lessonID: String
    let workspace: String?
    let fields: NativeSkillFields

    var parameters: [String: JSONValue] {
        var value: [String: JSONValue] = ["conversation_id": .string(conversationID.uuidString),
                                         "lesson_id": .string(lessonID), "authored": fields.json]
        if let workspace { value["workspace_root"] = .string(workspace) }
        return value
    }

    func matchesWorkspace(_ reported: String) -> Bool {
        guard let workspace else { return reported.isEmpty }
        guard workspace.hasPrefix("/"), reported.hasPrefix("/"), reported.count <= 4096 else { return false }
        // Foundation and Python spell macOS /private aliases differently.
        return URL(fileURLWithPath: reported).resolvingSymlinksInPath().standardizedFileURL.path ==
            URL(fileURLWithPath: workspace).resolvingSymlinksInPath().standardizedFileURL.path
    }
}

struct NativeSkillReceipt: Decodable {
    let kind: String
    let id: String
    let sourceLessonId: String
    let createdAt: String
    let authoringHash: String
    let recordId: String
    let beforeStoreSha256: String
    let afterStoreSha256: String
    let receiptHash: String
    let verificationStatus: String
    let warnings: [String]
    let processMemoryOnly: Bool
    let executable: Bool
    let details: String

    func valid(kind expected: String, lesson: String) -> Bool {
        guard kind == expected, sourceLessonId == lesson, !createdAt.isEmpty,
              skillHash(authoringHash), skillHash(receiptHash), processMemoryOnly, !executable,
              details.count <= 64_000, skillFindings(warnings) else { return false }
        if kind == "author" {
            return id == "skillauth_\(authoringHash.prefix(16))" && recordId.isEmpty &&
                receiptHash == authoringHash && beforeStoreSha256.isEmpty && afterStoreSha256.isEmpty && verificationStatus == "NOT APPLICABLE"
        }
        return kind == "apply" && id == "skillapply_\(receiptHash.prefix(16))" &&
            recordId == "skilllearn_\(authoringHash.prefix(16))" && skillHash(beforeStoreSha256) && skillHash(afterStoreSha256) &&
            ["OK", "WARN", "ERROR"].contains(verificationStatus)
    }
}

struct NativeSkillReview: Decodable {
    let schema: String
    let readOnly: Bool
    let conversationId: String
    let lessonId: String
    let workspacePath: String
    let status: String
    let eligible: Bool
    let sourceStatus: String
    let sourceContent: String
    let sourceProvenanceId: String
    let sourceRecordHash: String
    let lifecycleState: String
    let sourceChecks: [String: Bool]
    let fields: NativeSkillFields
    let authoringReceipt: NativeSkillReceipt?
    let applyReceipt: NativeSkillReceipt?
    let applyChecks: [String: Bool]
    let applyIssues: [String]
    let storeHashes: [String: String]
    let nativeApplySlotAvailable: Bool
    let skillStoreScope: String
    let projectIsolationEnforced: Bool
    let issues: [String]
    let sourceIssues: [String]
    let warnings: [String]

    static func decode(_ value: JSONValue, selection: NativeSkillSelection) throws -> Self {
        let report = try decodeSkill(Self.self, value, fields: ["schema", "read_only", "conversation_id", "lesson_id", "workspace_path",
            "status", "eligible", "source_status", "source_content", "source_provenance_id", "source_record_hash", "lifecycle_state",
            "source_checks", "fields", "authoring_receipt", "apply_receipt", "apply_checks", "apply_issues", "store_hashes",
            "native_apply_slot_available", "skill_store_scope", "project_isolation_enforced", "issues", "source_issues", "warnings", "store_mutation_performed"])
        guard report.schema == "proto_mind.native_skill_authoring.v1", report.readOnly,
              UUID(uuidString: report.conversationId) == selection.conversationID, report.lessonId == selection.lessonID,
              selection.matchesWorkspace(report.workspacePath),
              ["ERROR", "REVIEW", "AUTHORED", "APPLIED"].contains(report.status),
              report.fields.bounded, report.sourceContent.count <= 800,
              report.sourceRecordHash.isEmpty || skillHash(report.sourceRecordHash),
              report.sourceProvenanceId.isEmpty || skillID(report.sourceProvenanceId),
              !report.eligible || (report.issues.isEmpty && report.sourceIssues.isEmpty && report.sourceChecks.values.allSatisfy { $0 } &&
                  !report.sourceChecks.isEmpty && report.lifecycleState == "active" && skillHash(report.sourceRecordHash) && !report.sourceProvenanceId.isEmpty),
              report.authoringReceipt?.valid(kind: "author", lesson: report.lessonId) != false,
              report.applyReceipt?.valid(kind: "apply", lesson: report.lessonId) != false,
              report.applyReceipt == nil || report.authoringReceipt?.authoringHash == report.applyReceipt?.authoringHash,
              report.status != "AUTHORED" || report.authoringReceipt != nil,
              report.status != "APPLIED" || (report.applyReceipt != nil && !report.nativeApplySlotAvailable),
              report.authoringReceipt == nil || report.fields.complete,
              report.skillStoreScope == "global_legacy_stores", !report.projectIsolationEnforced,
              skillStores(report.storeHashes), [report.issues, report.sourceIssues, report.warnings, report.applyIssues].allSatisfy(skillFindings),
              value["store_mutation_performed"] == .bool(false) else {
            throw NativeError.message("Карточка навыка не прошла проверку контракта. Запись недоступна.")
        }
        return report
    }
}

struct NativeSkillPreview: Decodable {
    let schema: String
    let readOnly: Bool
    let conversationId: String
    let lessonId: String
    let operation: NativeSkillOperation
    let ready: Bool
    let issues: [String]
    let previewFingerprint: String
    let confirmationToken: String
    let targetSchema: String
    let futureMutation: String
    let requiresGlobalSkillsAcknowledgement: Bool
    let name: String
    let summary: String
    let body: String
    let authoringHash: String
    let storeHashes: [String: String]

    static func decode(_ value: JSONValue, selection: NativeSkillSelection, operation: NativeSkillOperation) throws -> Self {
        let preview = try decodeSkill(Self.self, value, fields: ["schema", "read_only", "conversation_id", "lesson_id", "operation", "ready",
            "issues", "preview_fingerprint", "confirmation_token", "target_schema", "future_mutation", "requires_global_skills_acknowledgement",
            "name", "summary", "body", "authoring_hash", "store_hashes", "store_mutation_performed"])
        guard preview.schema == "proto_mind.native_skill_confirmation.v1", preview.readOnly,
              UUID(uuidString: preview.conversationId) == selection.conversationID, preview.lessonId == selection.lessonID,
              preview.operation == operation, preview.targetSchema == "skill.procedure.v1", preview.futureMutation == operation.mutation,
              preview.requiresGlobalSkillsAcknowledgement == (operation == .apply), skillHash(preview.previewFingerprint),
              skillText(preview.name), skillText(preview.summary), preview.body.count <= 12_000,
              skillStores(preview.storeHashes), skillFindings(preview.issues),
              preview.ready ? (preview.issues.isEmpty && skillHash(preview.authoringHash) && !preview.body.isEmpty &&
                  preview.confirmationToken.range(of: "^\(operation.tokenPrefix)[A-F0-9]{12}$", options: .regularExpression) != nil)
                  : (!preview.issues.isEmpty && preview.confirmationToken.isEmpty),
              value["store_mutation_performed"] == .bool(false) else {
            throw NativeError.message("Preview навыка не прошёл проверку. Ничего не выполнено.")
        }
        return preview
    }

    func accepts(token: String, acknowledgeGlobal: Bool) -> Bool {
        ready && token == confirmationToken && (!requiresGlobalSkillsAcknowledgement || acknowledgeGlobal)
    }
}

struct NativeSkillResult: Decodable {
    let schema: String
    let conversationId: String
    let lessonId: String
    let operation: NativeSkillOperation
    let receipt: NativeSkillReceipt
    let mutation: String
    let skillMutationPerformed: Bool
    let batchApplyPerformed: Bool

    static func decode(_ value: JSONValue, selection: NativeSkillSelection, operation: NativeSkillOperation) throws -> Self {
        let result = try decodeSkill(Self.self, value, fields: ["schema", "conversation_id", "lesson_id", "operation", "receipt",
            "mutation", "skill_mutation_performed", "batch_apply_performed"])
        guard result.schema == "proto_mind.native_skill_result.v1", UUID(uuidString: result.conversationId) == selection.conversationID,
              result.lessonId == selection.lessonID, result.operation == operation, result.mutation == operation.mutation,
              result.receipt.valid(kind: operation.rawValue, lesson: selection.lessonID),
              result.skillMutationPerformed == (operation == .apply), !result.batchApplyPerformed else {
            throw NativeError.message("Результат записи не удалось проверить. Не повторяйте сохранение: обновите карточку и проверьте receipt.")
        }
        return result
    }
}

private func decodeSkill<T: Decodable>(_ type: T.Type, _ value: JSONValue, fields: Set<String>) throws -> T {
    let falseFlags: Set<String> = ["model_call_performed", "network_call_performed", "retrieval_performed", "consent_state_changed",
        "automatic_promotion", "context_injection_changed", "permissions_changed", "memory_mutation_performed"]
    guard case .object(let root) = value, Set(root.keys) == fields.union(falseFlags).union(["no_execution"]),
          value["no_execution"] == .bool(true), falseFlags.allSatisfy({ value[$0] == .bool(false) }) else {
        throw NativeError.message("Недопустимое расширение контракта навыка. Ничего не подтверждено.")
    }
    let decoder = JSONDecoder()
    decoder.keyDecodingStrategy = .convertFromSnakeCase
    return try decoder.decode(type, from: JSONEncoder().encode(value))
}

private func skillID(_ value: String) -> Bool { value.range(of: "^[A-Za-z0-9_.:-]{1,200}$", options: .regularExpression) != nil }
private func skillHash(_ value: String) -> Bool { value.range(of: "^[a-f0-9]{64}$", options: .regularExpression) != nil }
private func skillText(_ value: String) -> Bool { value.count <= 800 && !value.unicodeScalars.contains { $0.value < 32 } }
private func skillFindings(_ values: [String]) -> Bool { values.count <= 200 && values.allSatisfy { $0.count <= 4000 } }
private func skillStores(_ values: [String: String]) -> Bool {
    values.allSatisfy { key, value in
        ["working_memory.json", "persistent_memory.json", "skills.jsonl"].contains(key) && (value == "missing" || skillHash(value))
    }
}
