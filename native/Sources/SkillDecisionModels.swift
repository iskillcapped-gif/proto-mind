import Foundation

enum NativeSkillDecision: String, CaseIterable, Decodable {
    case keep, revise, archive

    var title: String {
        switch self { case .keep: return "Оставить без изменений"; case .revise: return "Нужна доработка"; case .archive: return "Рекомендовать архивирование" }
    }
    var explanation: String {
        switch self {
        case .keep: return "Зафиксировать решение сохранить текущий навык. Это не разрешение на его автоматический запуск."
        case .revise: return "Зафиксировать необходимость отдельной версии или исправления. Текст навыка сейчас не редактируется."
        case .archive: return "Зафиксировать выбор в пользу архива. Статус остаётся прежним: само архивирование требует отдельного подтверждения."
        }
    }
    var nextStep: String {
        switch self {
        case .keep: return "Навык остаётся как есть. Новые ручные результаты могут изменить актуальность этого решения."
        case .revise: return "Отдельно подготовьте исправленный вариант и проверку результата. Это решение не создаёт новую версию."
        case .archive: return "Перед реальной архивацией потребуется отдельно проверить текущие данные и подтвердить точный переход. Этот экран ничего не архивирует."
        }
    }
}

struct NativeSkillDecisionSelection: Equatable {
    let scope: NativeSkillInspectionSelection
    let decision: NativeSkillDecision
    var parameters: [String: JSONValue] {
        var params = scope.parameters; params["decision"] = .string(decision.rawValue); return params
    }
}

struct NativeSkillDecisionEvidence: Decodable, Equatable {
    let skillId: String
    let provenanceId: String
    let outcomeStatus: String
    let decision: NativeSkillDecision
    let selectedSignalId: String
    let evidenceEventIds: [String]
    let captureReceiptIds: [String]
    let captureReceiptHashes: [String]
    let reviewHash: String
    let decisionHash: String

    func valid(skill: String) -> Bool {
        skillId == skill && decisionID(provenanceId) && decisionHashValue(reviewHash) && decisionHashValue(decisionHash) &&
        decisionAllowed(decision, for: outcomeStatus) && evidenceEventIds.contains(selectedSignalId) &&
        (1...256).contains(evidenceEventIds.count) && Set(evidenceEventIds).count == evidenceEventIds.count && evidenceEventIds.allSatisfy(decisionID) &&
        (1...16).contains(captureReceiptIds.count) && captureReceiptIds.count == captureReceiptHashes.count &&
        Set(captureReceiptIds).count == captureReceiptIds.count && Set(captureReceiptHashes).count == captureReceiptHashes.count &&
        captureReceiptIds.allSatisfy(decisionID) && captureReceiptHashes.allSatisfy(decisionHashValue)
    }
    var token: String { "CONFIRM-SKILL-\(decision.rawValue.uppercased())-\(decisionHash.prefix(12).uppercased())" }
}

struct NativeSkillDecisionReceipt: Decodable, Identifiable {
    let id: String
    let createdAt: String
    let confirmationMethod: String
    let confirmationTokenHash: String
    let receiptHash: String
    let verificationStatus: String
    let evidenceState: String
    let evidence: NativeSkillDecisionEvidence

    private enum CodingKeys: String, CodingKey {
        case id, createdAt, confirmationMethod, confirmationTokenHash, receiptHash, verificationStatus, evidenceState
    }
    init(from decoder: Decoder) throws {
        evidence = try NativeSkillDecisionEvidence(from: decoder)
        let values = try decoder.container(keyedBy: CodingKeys.self)
        id = try values.decode(String.self, forKey: .id)
        createdAt = try values.decode(String.self, forKey: .createdAt)
        confirmationMethod = try values.decode(String.self, forKey: .confirmationMethod)
        confirmationTokenHash = try values.decode(String.self, forKey: .confirmationTokenHash)
        receiptHash = try values.decode(String.self, forKey: .receiptHash)
        verificationStatus = try values.decode(String.self, forKey: .verificationStatus)
        evidenceState = try values.decode(String.self, forKey: .evidenceState)
    }
    func valid(skill: String) -> Bool {
        evidence.valid(skill: skill) && id == "skilloutdec_\(evidence.decisionHash.prefix(16))" &&
        !createdAt.isEmpty && createdAt.count <= 100 && confirmationMethod == "exact_current_skill_outcome_decision_token" &&
        decisionHashValue(confirmationTokenHash) && decisionHashValue(receiptHash) &&
        ["VERIFIED", "ERROR", "UNAVAILABLE"].contains(verificationStatus) && ["CURRENT", "HISTORICAL", "UNAVAILABLE"].contains(evidenceState) &&
        (verificationStatus == "VERIFIED" ? evidenceState != "UNAVAILABLE" : evidenceState == "UNAVAILABLE")
    }
}

struct NativeSkillDecisionChoice: Decodable, Identifiable {
    let decision: NativeSkillDecision
    let allowed: Bool
    let reasons: [String]
    var id: String { decision.rawValue }
}

struct NativeSkillDecisionReview: Decodable {
    let status: String
    let name: String
    let sourceEligible: Bool
    let contextInjectionDisabled: Bool
    let pilotState: String
    let sessionId: String
    let eventCount: Int
    let captureReceiptCount: Int
    let decisionCount: Int
    let decisionLimit: Int
    let outcomeStatus: String
    let manualUseCount: Int
    let signalCount: Int
    let choices: [NativeSkillDecisionChoice]
    let receipt: NativeSkillDecisionReceipt?
    let storeHashes: [String: String]
    let changedSinceSelection: Bool
    let skillStoreScope: String
    let projectIsolationEnforced: Bool
    let reasons: [String]
    let issues: [String]
    let warnings: [String]

    static func decode(_ value: JSONValue, scope: NativeSkillInspectionSelection) throws -> Self {
        let report: Self = try decodeDecision(value, scope: scope, kind: "review", readOnly: true, fields: [
            "status", "name", "source_eligible", "context_injection_disabled", "pilot_state", "session_id", "event_count",
            "capture_receipt_count", "decision_count", "decision_limit", "outcome_status", "manual_use_count", "signal_count",
            "choices", "receipt", "store_hashes", "changed_since_selection", "skill_store_scope", "project_isolation_enforced", "reasons", "issues", "warnings"])
        let allowed = report.choices.filter(\.allowed)
        guard ["READY", "NOT_READY", "RECORDED", "ERROR"].contains(report.status), report.name.count <= 200,
              ["not_started", "disabled", "previewed", "consented", "stopped", "expired"].contains(report.pilotState),
              report.sessionId.isEmpty ? report.pilotState == "not_started" : decisionID(report.sessionId),
              (0...256).contains(report.eventCount), (0...256).contains(report.manualUseCount), (0...256).contains(report.signalCount),
              (0...16).contains(report.captureReceiptCount), (0...16).contains(report.decisionCount), report.decisionLimit == 16,
              ["UNAVAILABLE", "SUCCESS_CANDIDATE", "FAILURE_CANDIDATE", "MIXED_EVIDENCE", "NEEDS_MORE_EVIDENCE", "NOT_FOUND", "ERROR"].contains(report.outcomeStatus),
              report.choices.map(\.decision) == NativeSkillDecision.allCases, report.choices.allSatisfy({ decisionFindings($0.reasons) && (!$0.allowed || $0.reasons.isEmpty) }),
              report.skillStoreScope == "global_legacy_stores", !report.projectIsolationEnforced,
              decisionStores(report.storeHashes), decisionFindings(report.reasons), decisionFindings(report.issues), decisionFindings(report.warnings),
              (report.status == "READY") == !allowed.isEmpty else { throw decisionContractError() }
        if !allowed.isEmpty {
            guard report.sourceEligible, report.contextInjectionDisabled, report.captureReceiptCount > 0,
                  report.manualUseCount > 0, report.signalCount > 0, report.decisionCount < 16, report.storeHashes.count == 3,
                  !report.sessionId.isEmpty, report.reasons.isEmpty, report.issues.isEmpty, report.receipt == nil,
                  allowed.allSatisfy({ decisionAllowed($0.decision, for: report.outcomeStatus) }) else { throw decisionContractError() }
        }
        if let receipt = report.receipt {
            guard receipt.valid(skill: scope.skillID), report.decisionCount > 0, allowed.isEmpty,
                  ["RECORDED", "ERROR"].contains(report.status) else { throw decisionContractError() }
        } else if report.status == "RECORDED" { throw decisionContractError() }
        return report
    }
}

struct NativeSkillDecisionPreview: Decodable {
    let ready: Bool
    let decision: NativeSkillDecision
    let previewFingerprint: String
    let reasons: [String]
    let confirmationToken: String
    let blueprint: NativeSkillDecisionEvidence?
    let futureMutation: String
    let requiresDecisionOnlyAcknowledgement: Bool
    let storeHashes: [String: String]

    static func decode(_ value: JSONValue, selection: NativeSkillDecisionSelection) throws -> Self {
        let preview: Self = try decodeDecision(value, scope: selection.scope, kind: "preview", readOnly: true, fields: [
            "ready", "decision", "preview_fingerprint", "reasons", "confirmation_token", "blueprint", "future_mutation",
            "requires_decision_only_acknowledgement", "store_hashes"])
        guard preview.ready == preview.reasons.isEmpty, preview.decision == selection.decision,
              decisionHashValue(preview.previewFingerprint), decisionFindings(preview.reasons), decisionStores(preview.storeHashes),
              preview.futureMutation == "process_memory_one_terminal_decision_receipt", preview.requiresDecisionOnlyAcknowledgement else { throw decisionContractError() }
        if let blueprint = preview.blueprint {
            guard preview.ready, blueprint.valid(skill: selection.scope.skillID), blueprint.decision == selection.decision,
                  preview.storeHashes.count == 3, preview.confirmationToken == blueprint.token else { throw decisionContractError() }
        } else if preview.ready || !preview.confirmationToken.isEmpty { throw decisionContractError() }
        return preview
    }
    func accepts(token: String, acknowledgement: Bool) -> Bool { ready && acknowledgement && token == confirmationToken }
}

struct NativeSkillDecisionResult: Decodable {
    let mutation: String
    let eventsAppended: Int
    let receipt: NativeSkillDecisionReceipt

    static func decode(_ value: JSONValue, selection: NativeSkillDecisionSelection, preview: NativeSkillDecisionPreview) throws -> Self {
        let result: Self = try decodeDecision(value, scope: selection.scope, kind: "result", readOnly: false, fields: ["mutation", "events_appended", "receipt"])
        guard result.mutation == "process_memory_one_terminal_decision_receipt", result.eventsAppended == 0,
              result.receipt.valid(skill: selection.scope.skillID), result.receipt.evidence == preview.blueprint,
              result.receipt.verificationStatus == "VERIFIED", result.receipt.evidenceState == "CURRENT" else { throw decisionContractError() }
        return result
    }
}

private let decisionEvidenceFields: Set<String> = ["skill_id", "provenance_id", "outcome_status", "decision", "selected_signal_id",
    "evidence_event_ids", "capture_receipt_ids", "capture_receipt_hashes", "review_hash", "decision_hash"]

private func decodeDecision<T: Decodable>(_ value: JSONValue, scope: NativeSkillInspectionSelection, kind: String,
                                          readOnly: Bool, fields: Set<String>) throws -> T {
    let falseFlags: Set<String> = ["store_mutation_performed", "model_call_performed", "network_call_performed", "retrieval_performed",
        "context_injection_changed", "permissions_changed", "consent_state_changed", "automatic_promotion", "session_log_mutation_performed",
        "skill_mutation_performed", "memory_mutation_performed", "experience_mutation_performed", "lifecycle_apply_performed", "future_apply_ready"]
    let base: Set<String> = ["schema", "conversation_id", "skill_id", "workspace_path", "read_only", "no_execution"]
    guard case .object(let root) = value, Set(root.keys) == base.union(fields).union(falseFlags),
          value["schema"] == .string("proto_mind.native_skill_decision_\(kind).v1"), value["read_only"] == .bool(readOnly),
          value["no_execution"] == .bool(true), falseFlags.allSatisfy({ value[$0] == .bool(false) }),
          let conversation = scope.conversationID, UUID(uuidString: value["conversation_id"].text) == conversation,
          value["skill_id"] == .string(scope.skillID), scope.matchesWorkspace(value["workspace_path"].text) else { throw decisionContractError() }
    if let blueprint = root["blueprint"], blueprint != .null {
        try decisionFlags(blueprint, fields: decisionEvidenceFields, trueFlags: ["operator_choice_required", "terminal_process_decision"],
                          falseFlags: ["future_apply_ready", "skill_mutation_allowed", "procedure_execution_allowed", "persistence_allowed"])
    }
    if let receipt = root["receipt"], receipt != .null {
        try decisionFlags(receipt, fields: decisionEvidenceFields.union(["id", "created_at", "confirmation_method", "confirmation_token_hash",
                            "receipt_hash", "verification_status", "evidence_state"]),
                          trueFlags: ["operator_confirmation_recorded", "terminal_process_decision", "process_memory_only", "restart_expiring"],
                          falseFlags: ["future_apply_ready", "skill_mutation_performed", "memory_mutation_performed", "experience_mutation_performed",
                                       "persistence_performed", "procedure_execution_performed"])
    }
    let bytes = try JSONEncoder().encode(value)
    guard bytes.count <= 256_000 else { throw decisionContractError() }
    let decoder = JSONDecoder(); decoder.keyDecodingStrategy = .convertFromSnakeCase
    return try decoder.decode(T.self, from: bytes)
}

private func decisionFlags(_ value: JSONValue, fields: Set<String>, trueFlags: Set<String>, falseFlags: Set<String>) throws {
    guard case .object(let object) = value, Set(object.keys) == fields.union(trueFlags).union(falseFlags),
          trueFlags.allSatisfy({ value[$0] == .bool(true) }), falseFlags.allSatisfy({ value[$0] == .bool(false) }) else { throw decisionContractError() }
}
private func decisionContractError() -> NativeError { .message("Не удалось проверить точный контракт решения. Автоповтора и дополнительных действий нет; обновите квитанции.") }
func decisionID(_ value: String) -> Bool { value.range(of: "^[A-Za-z0-9_.:-]{1,200}$", options: .regularExpression) != nil }
func decisionHashValue(_ value: String) -> Bool { value.range(of: "^[a-f0-9]{64}$", options: .regularExpression) != nil }
func decisionFindings(_ values: [String]) -> Bool { values.count <= 33 && values.allSatisfy { $0.count <= 1000 } }
func decisionStores(_ values: [String: String]) -> Bool {
    values.allSatisfy { ["skills.jsonl", "persistent_memory.json", "context_injection.json"].contains($0.key) && decisionHashValue($0.value) }
}
private func decisionAllowed(_ decision: NativeSkillDecision, for status: String) -> Bool {
    status == "SUCCESS_CANDIDATE" ? decision == .keep : ["FAILURE_CANDIDATE", "MIXED_EVIDENCE"].contains(status) && decision != .keep
}
