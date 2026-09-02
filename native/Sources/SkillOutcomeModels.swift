import Foundation

struct NativeSkillOutcomeSelection: Equatable {
    let scope: NativeSkillInspectionSelection
    let outcome: String
    let evidence: String
    var parameters: [String: JSONValue] {
        var value = scope.parameters
        value["outcome"] = .string(outcome); value["evidence"] = .string(evidence)
        return value
    }
    var complete: Bool {
        ["success", "failure"].contains(outcome) && !evidence.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty &&
        evidence.unicodeScalars.count <= 800
    }
}

struct NativeSkillOutcomeReceipt: Decodable, Identifiable {
    let id: String
    let createdAt: String
    let sessionId: String
    let skillId: String
    let outcome: String
    let evidencePreview: String
    let evidenceFingerprint: String
    let blueprintHash: String
    let receiptHash: String
    let eventIds: [String]
    let operatorReported: Bool
    let manualOperatorUse: Bool
    let executionPerformedByProtoMind: Bool
    let processMemoryOnly: Bool
    let restartExpiring: Bool
    let persistencePerformed: Bool
    let verificationStatus: String

    func valid(skill: String, session: String) -> Bool {
        skillId == skill && sessionId == session && outcomeID(session) &&
        id == "skilloutcap_\(blueprintHash.prefix(16))" && ["success", "failure"].contains(outcome) &&
        !createdAt.isEmpty && createdAt.count <= 100 && evidencePreview.count <= 160 &&
        outcomeHash(evidenceFingerprint) && outcomeHash(blueprintHash) && outcomeHash(receiptHash) &&
        eventIds.count == 4 && Set(eventIds).count == 4 && eventIds.allSatisfy(outcomeID) &&
        operatorReported && manualOperatorUse && !executionPerformedByProtoMind && processMemoryOnly &&
        restartExpiring && !persistencePerformed && ["VERIFIED", "ERROR"].contains(verificationStatus)
    }
}

struct NativeSkillOutcomeReview: Decodable {
    let status: String
    let name: String
    let sourceEligible: Bool
    let captureAvailable: Bool
    let pilotState: String
    let sessionId: String
    let contextInjectionDisabled: Bool
    let eventCount: Int
    let eventLimit: Int
    let receiptCount: Int
    let receiptLimit: Int
    let receipts: [NativeSkillOutcomeReceipt]
    let storeHashes: [String: String]
    let changedSinceSelection: Bool
    let skillStoreScope: String
    let projectIsolationEnforced: Bool
    let reasons: [String]
    let issues: [String]

    static func decode(_ value: JSONValue, scope: NativeSkillInspectionSelection) throws -> Self {
        let report: Self = try decodeOutcome(value, scope: scope, schema: "review", readOnly: true, fields: [
            "status", "name", "source_eligible", "capture_available", "pilot_state", "session_id", "context_injection_disabled",
            "event_count", "event_limit", "receipt_count", "receipt_limit", "receipts", "store_hashes", "changed_since_selection",
            "skill_store_scope", "project_isolation_enforced", "reasons", "issues"])
        guard ["READY", "NOT_READY", "ERROR"].contains(report.status), report.name.count <= 200,
              ["not_started", "disabled", "previewed", "consented", "stopped", "expired"].contains(report.pilotState),
              report.sessionId.isEmpty ? report.pilotState == "not_started" : outcomeID(report.sessionId),
              (1...256).contains(report.eventLimit), (0...report.eventLimit).contains(report.eventCount),
              report.receiptLimit == 16, (0...16).contains(report.receiptCount), report.receipts.count <= report.receiptCount,
              report.receipts.allSatisfy({ $0.valid(skill: scope.skillID, session: report.sessionId) }),
              Set(report.receipts.map(\.id)).count == report.receipts.count,
              outcomeStores(report.storeHashes), outcomeFindings(report.reasons), outcomeFindings(report.issues),
              report.skillStoreScope == "global_legacy_stores", !report.projectIsolationEnforced,
              report.captureAvailable == (report.status == "READY"),
              !report.captureAvailable || (report.sourceEligible && report.pilotState == "consented" && report.contextInjectionDisabled &&
                report.eventCount + 4 <= report.eventLimit && report.receiptCount < 16 && report.reasons.isEmpty && report.issues.isEmpty) else {
            throw NativeError.message("Не удалось проверить условия ручной записи результата.")
        }
        return report
    }
}

struct NativeSkillOutcomePreview: Decodable {
    let ready: Bool
    let reasons: [String]
    let previewFingerprint: String
    let confirmationToken: String
    let sessionId: String
    let blueprintHash: String
    let outcome: String
    let evidencePreview: String
    let evidenceFingerprint: String
    let evidenceInputChars: Int
    let futureMutation: String
    let operatorReported: Bool
    let requiresManualAcknowledgement: Bool
    let processMemoryOnly: Bool
    let restartExpiring: Bool
    let storeHashes: [String: String]

    static func decode(_ value: JSONValue, selection: NativeSkillOutcomeSelection) throws -> Self {
        let preview: Self = try decodeOutcome(value, scope: selection.scope, schema: "preview", readOnly: true, fields: [
            "ready", "reasons", "preview_fingerprint", "confirmation_token", "session_id", "blueprint_hash", "outcome",
            "evidence_preview", "evidence_fingerprint", "evidence_input_chars", "future_mutation", "operator_reported",
            "requires_manual_acknowledgement", "process_memory_only", "restart_expiring", "store_hashes"])
        guard preview.ready == preview.reasons.isEmpty, outcomeFindings(preview.reasons), outcomeHash(preview.previewFingerprint),
              preview.outcome == selection.outcome, preview.evidencePreview.count <= 160, (0...800).contains(preview.evidenceInputChars),
              preview.futureMutation == "process_memory_four_events_one_receipt", preview.operatorReported,
              preview.requiresManualAcknowledgement, preview.processMemoryOnly, preview.restartExpiring, outcomeStores(preview.storeHashes),
              preview.ready || preview.confirmationToken.isEmpty else { throw NativeError.message("Область подтверждения результата изменилась.") }
        if preview.ready {
            guard outcomeID(preview.sessionId), outcomeHash(preview.blueprintHash), outcomeHash(preview.evidenceFingerprint),
                  preview.evidenceInputChars > 0, !preview.evidencePreview.isEmpty, preview.storeHashes.count == 3,
                  preview.confirmationToken == "CONFIRM-SKILL-OUTCOME-\(preview.blueprintHash.prefix(12).uppercased())" else {
                throw NativeError.message("Не удалось проверить точное подтверждение результата.")
            }
        }
        return preview
    }

    func accepts(token: String, acknowledgement: Bool) -> Bool { ready && acknowledgement && token == confirmationToken }
}

struct NativeSkillOutcomeResult: Decodable {
    let mutation: String
    let eventsAppended: Int
    let receipt: NativeSkillOutcomeReceipt

    static func decode(_ value: JSONValue, selection: NativeSkillOutcomeSelection, preview: NativeSkillOutcomePreview) throws -> Self {
        let result: Self = try decodeOutcome(value, scope: selection.scope, schema: "result", readOnly: false,
                                            fields: ["mutation", "events_appended", "receipt"])
        guard result.mutation == "process_memory_four_events_one_receipt", result.eventsAppended == 4,
              result.receipt.valid(skill: selection.scope.skillID, session: preview.sessionId),
              result.receipt.blueprintHash == preview.blueprintHash, result.receipt.outcome == selection.outcome,
              result.receipt.evidenceFingerprint == preview.evidenceFingerprint else {
            throw NativeError.message("Квитанция не соответствует подтверждённой записи. Автоповтора нет; обновите список результатов.")
        }
        return result
    }
}

private func decodeOutcome<T: Decodable>(_ value: JSONValue, scope: NativeSkillInspectionSelection,
                                         schema: String, readOnly: Bool, fields: Set<String>) throws -> T {
    let falseFlags: Set<String> = ["store_mutation_performed", "model_call_performed", "network_call_performed", "retrieval_performed",
        "context_injection_changed", "permissions_changed", "consent_state_changed", "automatic_promotion", "session_log_mutation_performed",
        "skill_mutation_performed", "memory_mutation_performed"]
    let base: Set<String> = ["schema", "conversation_id", "skill_id", "workspace_path", "read_only", "no_execution"]
    guard case .object(let root) = value, Set(root.keys) == base.union(fields).union(falseFlags),
          value["schema"] == .string("proto_mind.native_skill_outcome_\(schema).v1"),
          value["read_only"] == .bool(readOnly), value["no_execution"] == .bool(true),
          falseFlags.allSatisfy({ value[$0] == .bool(false) }),
          let conversation = scope.conversationID, UUID(uuidString: value["conversation_id"].text) == conversation,
          value["skill_id"] == .string(scope.skillID), scope.matchesWorkspace(value["workspace_path"].text) else {
        throw NativeError.message("Контракт ручного результата изменился. Никаких дополнительных действий не разрешено.")
    }
    let bytes = try JSONEncoder().encode(value)
    guard bytes.count <= 256_000 else { throw NativeError.message("Результат превышает предел просмотра.") }
    let decoder = JSONDecoder(); decoder.keyDecodingStrategy = .convertFromSnakeCase
    return try decoder.decode(T.self, from: bytes)
}

private func outcomeID(_ value: String) -> Bool { value.range(of: "^[A-Za-z0-9_.:-]{1,200}$", options: .regularExpression) != nil }
private func outcomeHash(_ value: String) -> Bool { value.range(of: "^[a-f0-9]{64}$", options: .regularExpression) != nil }
private func outcomeFindings(_ values: [String]) -> Bool { values.count <= 40 && values.allSatisfy { $0.count <= 4000 } }
private func outcomeStores(_ values: [String: String]) -> Bool {
    values.allSatisfy { ["skills.jsonl", "persistent_memory.json", "context_injection.json"].contains($0.key) && outcomeHash($0.value) }
}
