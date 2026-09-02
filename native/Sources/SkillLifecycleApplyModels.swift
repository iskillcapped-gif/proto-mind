import CryptoKit
import Foundation

struct NativeSkillLifecycleSelection: Equatable {
    let scope: NativeSkillInspectionSelection
    let decisionReceiptID: String
    let decision: NativeSkillDecision
    var parameters: [String: JSONValue] {
        var params = scope.parameters; params["decision_receipt_id"] = .string(decisionReceiptID); return params
    }
}

private let archiveChangedFields = ["lifecycle", "status", "updated_at"]

struct NativeSkillLifecycleApplyReceipt: Decodable, Identifiable {
    let id: String
    let skillId: String
    let decisionReceiptId: String
    let decision: NativeSkillDecision
    let appliedAt: String
    let decisionHash: String
    let beforeStoreSha256: String
    let afterStoreSha256: String
    let beforeRecordHash: String
    let afterRecordHash: String
    let confirmationTokenHash: String
    let receiptHash: String
    let postStateVerified: Bool
    let durableProvenancePreserved: Bool
    let persistentMemoryUnchanged: Bool
    let actualRecordMutations: Int
    let changedFields: [String]
    let metadataId: String
    let metadataHash: String
    let verificationStatus: String
    let evidenceState: String
    let detailedReceiptPersistence: String
    let lifecycleMetadataPersistence: String
    let warnings: [String]
    let details: String

    func valid(_ selection: NativeSkillLifecycleSelection) -> Bool {
        let archive = decision == .archive
        return decision != .revise && decision == selection.decision && skillId == selection.scope.skillID &&
            decisionReceiptId == selection.decisionReceiptID && decisionReceiptId == "skilloutdec_\(decisionHash.prefix(16))" &&
            id.range(of: "^\(archive ? "skilllifemetaapply" : "skilllifeapply")_[a-f0-9]{16}$", options: .regularExpression) != nil &&
            !appliedAt.isEmpty && appliedAt.count <= 100 &&
            [decisionHash, beforeStoreSha256, afterStoreSha256, beforeRecordHash, afterRecordHash, confirmationTokenHash, receiptHash].allSatisfy(decisionHashValue) &&
            postStateVerified && durableProvenancePreserved && persistentMemoryUnchanged &&
            actualRecordMutations == (archive ? 1 : 0) && changedFields == (archive ? archiveChangedFields : []) &&
            (archive ? decisionID(metadataId) && decisionHashValue(metadataHash) && beforeStoreSha256 != afterStoreSha256 && beforeRecordHash != afterRecordHash
                     : metadataId.isEmpty && metadataHash.isEmpty && beforeStoreSha256 == afterStoreSha256 && beforeRecordHash == afterRecordHash) &&
            ["VERIFIED", "ERROR", "UNAVAILABLE"].contains(verificationStatus) && ["CURRENT", "HISTORICAL", "UNAVAILABLE"].contains(evidenceState) &&
            (verificationStatus == "VERIFIED" ? evidenceState != "UNAVAILABLE" : evidenceState == "UNAVAILABLE") &&
            detailedReceiptPersistence == "process_memory_only" && lifecycleMetadataPersistence == (archive ? "skill_record" : "none") &&
            decisionFindings(warnings) && !details.isEmpty && details.utf8.count <= 64_000
    }
}

struct NativeSkillLifecycleApplyReview: Decodable {
    let status: String
    let name: String
    let decision: String
    let storedSkillStatus: String
    let decisionHash: String
    let canApply: Bool
    let nativeApplySlotAvailable: Bool
    let contextInjectionDisabled: Bool
    let storeHashes: [String: String]
    let checks: [String: Bool]
    let reasons: [String]
    let issues: [String]
    let warnings: [String]
    let receipt: NativeSkillLifecycleApplyReceipt?
    let skillStoreScope: String
    let projectIsolationEnforced: Bool

    static func decode(_ value: JSONValue, selection: NativeSkillLifecycleSelection) throws -> Self {
        let report: Self = try decodeLifecycle(value, selection: selection, kind: "review", fields: [
            "status", "name", "decision", "stored_skill_status", "decision_hash", "can_apply", "native_apply_slot_available",
            "context_injection_disabled", "store_hashes", "checks", "reasons", "issues", "warnings", "receipt", "skill_store_scope", "project_isolation_enforced"])
        guard ["READY", "NOT_READY", "APPLIED", "ERROR"].contains(report.status), report.name.count <= 200,
              ["keep", "revise", "archive", "unknown"].contains(report.decision), ["active", "archived", "unavailable"].contains(report.storedSkillStatus),
              report.decisionHash.isEmpty || decisionHashValue(report.decisionHash), report.canApply == (report.status == "READY"),
              report.checks.count <= 40, report.checks.keys.allSatisfy({ $0.count <= 160 }),
              decisionStores(report.storeHashes), [report.reasons, report.issues, report.warnings].allSatisfy(decisionFindings),
              report.skillStoreScope == "global_legacy_stores", !report.projectIsolationEnforced else { throw lifecycleContractError() }
        if report.canApply {
            guard report.decision == selection.decision.rawValue, selection.decision != .revise, report.contextInjectionDisabled,
                  report.nativeApplySlotAvailable, report.storedSkillStatus == "active", report.storeHashes.count == 3,
                  report.reasons.isEmpty, report.issues.isEmpty, !report.checks.isEmpty, report.checks.values.allSatisfy({ $0 }),
                  report.receipt == nil, selection.decisionReceiptID == "skilloutdec_\(report.decisionHash.prefix(16))" else { throw lifecycleContractError() }
        }
        if let receipt = report.receipt {
            guard receipt.valid(selection), !report.canApply, !report.nativeApplySlotAvailable,
                  ["APPLIED", "ERROR"].contains(report.status) else { throw lifecycleContractError() }
        } else if report.status == "APPLIED" { throw lifecycleContractError() }
        return report
    }
}

struct NativeSkillLifecycleApplyPreview: Decodable {
    let ready: Bool
    let decision: String
    let decisionHash: String
    let previewFingerprint: String
    let confirmationToken: String
    let reasons: [String]
    let beforeStoreSha256: String
    let beforeRecordHash: String
    let metadataBlueprintHash: String
    let expectedRecordMutations: Int
    let expectedChangedFields: [String]
    let futureMutation: String
    let requiresGlobalSkillsAcknowledgement: Bool
    let storeHashes: [String: String]

    static func decode(_ value: JSONValue, selection: NativeSkillLifecycleSelection) throws -> Self {
        let preview: Self = try decodeLifecycle(value, selection: selection, kind: "preview", fields: [
            "ready", "decision", "decision_hash", "preview_fingerprint", "confirmation_token", "reasons", "before_store_sha256",
            "before_record_hash", "metadata_blueprint_hash", "expected_record_mutations", "expected_changed_fields", "future_mutation",
            "requires_global_skills_acknowledgement", "store_hashes"])
        let archive = preview.decision == "archive"
        guard ["keep", "revise", "archive", "unknown"].contains(preview.decision), preview.ready == preview.reasons.isEmpty,
              decisionHashValue(preview.previewFingerprint), decisionFindings(preview.reasons), decisionStores(preview.storeHashes),
              preview.expectedRecordMutations == (archive ? 1 : 0), preview.expectedChangedFields == (archive ? archiveChangedFields : []),
              preview.futureMutation == (archive ? "skills_one_durable_archive" : "process_memory_keep_receipt"),
              preview.requiresGlobalSkillsAcknowledgement else { throw lifecycleContractError() }
        if preview.ready {
            guard selection.decision != .revise, preview.decision == selection.decision.rawValue,
                  [preview.decisionHash, preview.beforeStoreSha256, preview.beforeRecordHash].allSatisfy(decisionHashValue),
                  selection.decisionReceiptID == "skilloutdec_\(preview.decisionHash.prefix(16))", preview.storeHashes.count == 3,
                  preview.storeHashes["skills.jsonl"] == preview.beforeStoreSha256,
                  archive ? decisionHashValue(preview.metadataBlueprintHash) : preview.metadataBlueprintHash.isEmpty,
                  preview.confirmationToken == (try preview.expectedToken(selection)) else { throw lifecycleContractError() }
        } else if !preview.confirmationToken.isEmpty { throw lifecycleContractError() }
        return preview
    }

    private func expectedToken(_ selection: NativeSkillLifecycleSelection) throws -> String {
        var material: [String: Any] = ["decision_receipt_id": selection.decisionReceiptID, "skill_id": selection.scope.skillID,
            "decision": decision, "decision_hash": decisionHash, "before_store_sha256": beforeStoreSha256, "before_record_hash": beforeRecordHash]
        if decision == "archive" {
            material["metadata_blueprint_hash"] = metadataBlueprintHash; material["expected_changed_fields"] = expectedChangedFields
        } else { material["expected_record_mutations"] = expectedRecordMutations }
        let bytes = try JSONSerialization.data(withJSONObject: material, options: [.sortedKeys, .withoutEscapingSlashes])
        let digest = SHA256.hash(data: bytes).map { String(format: "%02x", $0) }.joined()
        return "CONFIRM-\(decision == "archive" ? "DURABLE-" : "")SKILL-LIFECYCLE-\(decision.uppercased())-\(digest.prefix(12).uppercased())"
    }
    func accepts(token: String, acknowledgement: Bool) -> Bool { ready && acknowledgement && token == confirmationToken }
}

struct NativeSkillLifecycleApplyResult: Decodable {
    let decision: NativeSkillDecision
    let mutation: String
    let eventsAppended: Int
    let receipt: NativeSkillLifecycleApplyReceipt

    static func decode(_ value: JSONValue, selection: NativeSkillLifecycleSelection, preview: NativeSkillLifecycleApplyPreview) throws -> Self {
        let archive = selection.decision == .archive
        let result: Self = try decodeLifecycle(value, selection: selection, kind: "result", fields: ["decision", "mutation", "events_appended", "receipt"], changed: archive)
        guard result.decision == selection.decision, result.mutation == preview.futureMutation, result.eventsAppended == 0,
              result.receipt.valid(selection), result.receipt.decisionHash == preview.decisionHash,
              result.receipt.beforeStoreSha256 == preview.beforeStoreSha256, result.receipt.beforeRecordHash == preview.beforeRecordHash else { throw lifecycleContractError() }
        return result
    }
}

private func decodeLifecycle<T: Decodable>(_ value: JSONValue, selection: NativeSkillLifecycleSelection, kind: String,
                                          fields: Set<String>, changed: Bool = false) throws -> T {
    let falseFlags: Set<String> = ["model_call_performed", "network_call_performed", "retrieval_performed", "context_injection_changed",
        "permissions_changed", "consent_state_changed", "automatic_promotion", "session_log_mutation_performed", "memory_mutation_performed",
        "experience_mutation_performed", "batch_apply_performed"]
    let base: Set<String> = ["schema", "conversation_id", "skill_id", "workspace_path", "decision_receipt_id", "read_only", "no_execution",
                             "store_mutation_performed", "skill_mutation_performed"]
    guard case .object(let root) = value, Set(root.keys) == base.union(falseFlags).union(fields),
          value["schema"] == .string("proto_mind.native_skill_lifecycle_\(kind).v1"), value["read_only"] == .bool(kind != "result"),
          value["no_execution"] == .bool(true), value["store_mutation_performed"] == .bool(changed), value["skill_mutation_performed"] == .bool(changed),
          falseFlags.allSatisfy({ value[$0] == .bool(false) }), let conversation = selection.scope.conversationID,
          UUID(uuidString: value["conversation_id"].text) == conversation, value["skill_id"] == .string(selection.scope.skillID),
          selection.scope.matchesWorkspace(value["workspace_path"].text), value["decision_receipt_id"] == .string(selection.decisionReceiptID) else { throw lifecycleContractError() }
    if let receipt = root["receipt"], receipt != .null {
        let keys: Set<String> = ["id", "skill_id", "decision_receipt_id", "decision", "applied_at", "decision_hash", "before_store_sha256",
            "after_store_sha256", "before_record_hash", "after_record_hash", "confirmation_token_hash", "receipt_hash", "post_state_verified",
            "durable_provenance_preserved", "persistent_memory_unchanged", "actual_record_mutations", "changed_fields", "metadata_id", "metadata_hash",
            "verification_status", "evidence_state", "detailed_receipt_persistence", "lifecycle_metadata_persistence", "warnings", "details"]
        guard case .object(let data) = receipt, Set(data.keys) == keys else { throw lifecycleContractError() }
    }
    let bytes = try JSONEncoder().encode(value)
    guard bytes.count <= 256_000 else { throw lifecycleContractError() }
    let decoder = JSONDecoder(); decoder.keyDecodingStrategy = .convertFromSnakeCase
    return try decoder.decode(T.self, from: bytes)
}

private func lifecycleContractError() -> NativeError {
    .message("Не удалось проверить точный контракт применения. Автоповтора нет; проверьте состояние навыка и квитанцию.")
}
