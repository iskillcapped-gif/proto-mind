import Foundation

enum NativeLearningOperation: String, Decodable, CaseIterable, Identifiable {
    case accept, reject, propose, apply
    var id: String { rawValue }
    var title: String {
        switch self {
        case .accept: return "Принять кандидат"
        case .reject: return "Отклонить кандидат"
        case .propose: return "Подготовить запись"
        case .apply: return "Сохранить один урок"
        }
    }
    var mutation: String { self == .apply ? "persistent_memory_one_lesson" : "process_memory_only" }
    var tokenPrefix: String {
        switch self {
        case .accept: return "CONFIRM-LEARNING-"
        case .reject: return "CONFIRM-LEARNING-REJECT-"
        case .propose: return "CONFIRM-PROPOSAL-"
        case .apply: return "CONFIRM-LEARNING-APPLY-"
        }
    }
}

struct NativeLearningSelection: Equatable {
    let conversationID: UUID
    let candidateID: String
    let workspace: String?
    let memoryIDs: [String]
    let query: String
    let reason: String

    var parameters: [String: JSONValue] {
        var value: [String: JSONValue] = [
            "conversation_id": .string(conversationID.uuidString), "candidate_id": .string(candidateID),
            "memory_ids": .array(memoryIDs.map(JSONValue.string)), "query": .string(query), "reason": .string(reason),
        ]
        if let workspace { value["workspace_root"] = .string(workspace) }
        return value
    }
}

struct NativeLearningCandidate: Decodable {
    let id: String
    let sessionId: String
    let turnId: String
    let text: String
    let sourceKinds: [String]
    let evidenceEventIds: [String]
    let confidence: String
    let reviewStatus: String
    let suggestedTarget: String
    let rationale: String
    let operatorConfirmationRequired: Bool
    let promotionReady: Bool
    let autoApplyAllowed: Bool
    let persistencePerformed: Bool

    var valid: Bool {
        learningID(id) && !text.isEmpty && text.count <= 160 && rationale.count <= 1000 &&
        ["operator_review_required", "needs_more_evidence", "blocked"].contains(reviewStatus) &&
        !evidenceEventIds.isEmpty && evidenceEventIds.count <= 64 && evidenceEventIds.allSatisfy(learningID) &&
        !sourceKinds.isEmpty && sourceKinds.count <= 4 && sourceKinds.allSatisfy {
            ["correction_guidance", "reflection_warning", "grounding_warning", "unsupported_claim"].contains($0)
        } && operatorConfirmationRequired && !promotionReady && !autoApplyAllowed && !persistencePerformed
    }
}

struct NativeLearningReference: Decodable, Identifiable {
    let id: String
    let recordId: String
    let store: String
    let preview: String
    let selectable: Bool
}

struct NativeLearningReceipt: Decodable, Identifiable {
    let kind: String
    let id: String
    let candidateId: String
    let createdAt: String
    let status: String
    let targetSchema: String
    let content: String
    let recordId: String
    let durableProvenanceId: String
    let receiptHash: String
    let beforeStoreSha256: String
    let afterStoreSha256: String
    let rollbackSuggestion: String
    let verificationStatus: String
    let warnings: [String]
    let processMemoryOnly: Bool
    let details: String

    func valid(kind expected: String, candidateID: String) -> Bool {
        guard kind == expected, learningID(id), candidateId == candidateID, !createdAt.isEmpty,
              learningHash(receiptHash), processMemoryOnly, details.count <= 32_000, content.count <= 160 else { return false }
        switch kind {
        case "decision": return ["accepted", "rejected"].contains(status) && recordId.isEmpty && targetSchema.isEmpty
        case "proposal": return status == "created" && targetSchema == "memory.lesson.v1" && recordId.isEmpty && !content.isEmpty
        case "apply": return status == "applied" && targetSchema == "memory.lesson.v1" && learningID(recordId) &&
            learningID(durableProvenanceId) && learningHash(beforeStoreSha256) && learningHash(afterStoreSha256) &&
            ["OK", "WARN", "ERROR"].contains(verificationStatus) && rollbackSuggestion == "/memory forget \(recordId)"
        default: return false
        }
    }
}

struct NativeLearningReview: Decodable {
    let schema: String
    let readOnly: Bool
    let conversationId: String
    let candidateId: String
    let status: String
    let candidate: NativeLearningCandidate?
    let decision: NativeLearningReceipt?
    let proposal: NativeLearningReceipt?
    let applyReceipt: NativeLearningReceipt?
    let references: [NativeLearningReference]
    let omittedReferenceCount: Int
    let requestedMemoryIds: [String]
    let eligibilityStatus: String
    let eligibilityWarnings: [String]
    let applyStatus: String
    let applyChecks: [String: Bool]
    let applyWarnings: [String]
    let storeHashes: [String: String]
    let nativeApplySlotAvailable: Bool
    let projectIsolationEnforced: Bool
    let memoryStoreScope: String
    let workspacePath: String
    let workspaceIdentityHash: String
    let issues: [String]
    let warnings: [String]
    let commandExecutionPerformed: Bool
    let modelCallPerformed: Bool
    let networkCallPerformed: Bool
    let retrievalPerformed: Bool
    let consentStateChanged: Bool
    let storeMutationPerformed: Bool
    let automaticPromotion: Bool

    static func decode(_ value: JSONValue, selection: NativeLearningSelection) throws -> Self {
        let report = try decodeLearning(Self.self, value)
        guard report.schema == "proto_mind.native_learning_review.v1", report.readOnly,
              UUID(uuidString: report.conversationId) == selection.conversationID, report.candidateId == selection.candidateID,
              ["ERROR", "NOT FOUND", "REVIEW", "APPLIED"].contains(report.status),
              report.candidate == nil || (report.candidate?.valid == true && report.candidate?.id == report.candidateId),
              report.decision?.valid(kind: "decision", candidateID: report.candidateId) != false,
              report.proposal?.valid(kind: "proposal", candidateID: report.candidateId) != false,
              report.applyReceipt?.valid(kind: "apply", candidateID: report.candidateId) != false,
              report.proposal == nil || report.decision?.status == "accepted",
              report.applyReceipt == nil || report.proposal != nil,
              report.status != "APPLIED" || report.applyReceipt != nil,
              report.references.count <= 100, report.omittedReferenceCount >= 0,
              Set(report.references.map(\.id)).count == report.references.count,
              report.references.allSatisfy({ item in
                  ["persistent", "working"].contains(item.store) && item.id == "\(item.store):\(item.recordId)" &&
                  item.preview.count <= 160 && (!item.selectable || learningID(item.recordId))
              }), learningIDs(report.requestedMemoryIds), learningStoreHashes(report.storeHashes),
              report.memoryStoreScope == "global_legacy_stores", !report.projectIsolationEnforced,
              report.workspacePath == (selection.workspace ?? ""),
              report.workspaceIdentityHash.isEmpty || learningHash(report.workspaceIdentityHash),
              !report.commandExecutionPerformed, !report.modelCallPerformed, !report.networkCallPerformed,
              !report.retrievalPerformed, !report.consentStateChanged, !report.storeMutationPerformed, !report.automaticPromotion else {
            throw NativeError.message("Контракт разбора урока не прошёл проверку. Подтверждение недоступно.")
        }
        return report
    }
}

struct NativeLearningPreview: Decodable {
    let schema: String
    let readOnly: Bool
    let conversationId: String
    let candidateId: String
    let operation: NativeLearningOperation
    let ready: Bool
    let previewFingerprint: String
    let confirmationToken: String
    let issues: [String]
    let futureMutation: String
    let content: String
    let targetSchema: String
    let requestedMemoryIds: [String]
    let storeHashes: [String: String]
    let requiresGlobalMemoryAcknowledgement: Bool
    let commandExecutionPerformed: Bool
    let modelCallPerformed: Bool
    let networkCallPerformed: Bool
    let retrievalPerformed: Bool
    let consentStateChanged: Bool
    let storeMutationPerformed: Bool
    let automaticPromotion: Bool

    static func decode(_ value: JSONValue, selection: NativeLearningSelection, operation: NativeLearningOperation) throws -> Self {
        let preview = try decodeLearning(Self.self, value)
        let tokenPattern = "^\(operation.tokenPrefix)[A-F0-9]{12}$"
        guard preview.schema == "proto_mind.native_learning_confirmation.v1", preview.readOnly,
              UUID(uuidString: preview.conversationId) == selection.conversationID, preview.candidateId == selection.candidateID,
              preview.operation == operation, learningHash(preview.previewFingerprint),
              preview.futureMutation == operation.mutation, preview.targetSchema == "memory.lesson.v1", preview.content.count <= 160,
              learningIDs(preview.requestedMemoryIds), learningStoreHashes(preview.storeHashes),
              preview.requiresGlobalMemoryAcknowledgement == (operation == .apply),
              preview.ready ? (preview.issues.isEmpty && !preview.content.isEmpty && preview.confirmationToken.range(of: tokenPattern, options: .regularExpression) != nil)
                            : (!preview.issues.isEmpty && preview.confirmationToken.isEmpty),
              !preview.commandExecutionPerformed, !preview.modelCallPerformed, !preview.networkCallPerformed,
              !preview.retrievalPerformed, !preview.consentStateChanged, !preview.storeMutationPerformed, !preview.automaticPromotion else {
            throw NativeError.message("Контракт подтверждения не прошёл проверку. Ничего не выполнено.")
        }
        return preview
    }

    func accepts(token: String, acknowledgeGlobal: Bool) -> Bool {
        ready && token == confirmationToken && (!requiresGlobalMemoryAcknowledgement || acknowledgeGlobal)
    }
}

struct NativeLearningResult: Decodable {
    let schema: String
    let conversationId: String
    let candidateId: String
    let operation: NativeLearningOperation
    let receipt: NativeLearningReceipt
    let mutation: String
    let memoryMutationPerformed: Bool
    let skillMutationPerformed: Bool
    let commandExecutionPerformed: Bool
    let modelCallPerformed: Bool
    let networkCallPerformed: Bool
    let retrievalPerformed: Bool
    let consentStateChanged: Bool
    let automaticPromotion: Bool
    let batchApplyPerformed: Bool

    static func decode(_ value: JSONValue, selection: NativeLearningSelection, operation: NativeLearningOperation) throws -> Self {
        let result = try decodeLearning(Self.self, value)
        let kind = operation == .apply ? "apply" : operation == .propose ? "proposal" : "decision"
        guard result.schema == "proto_mind.native_learning_result.v1",
              UUID(uuidString: result.conversationId) == selection.conversationID, result.candidateId == selection.candidateID,
              result.operation == operation, result.mutation == operation.mutation,
              result.receipt.valid(kind: kind, candidateID: selection.candidateID),
              operation != .accept || result.receipt.status == "accepted", operation != .reject || result.receipt.status == "rejected",
              result.memoryMutationPerformed == (operation == .apply), !result.skillMutationPerformed,
              !result.commandExecutionPerformed, !result.modelCallPerformed, !result.networkCallPerformed,
              !result.retrievalPerformed, !result.consentStateChanged, !result.automaticPromotion, !result.batchApplyPerformed else {
            throw NativeError.message("Ответ подтверждения не удалось проверить. Не повторяйте запись: обновите карточку и проверьте receipt.")
        }
        return result
    }
}

private func decodeLearning<T: Decodable>(_ type: T.Type, _ value: JSONValue) throws -> T {
    let decoder = JSONDecoder()
    decoder.keyDecodingStrategy = .convertFromSnakeCase
    return try decoder.decode(type, from: JSONEncoder().encode(value))
}

private func learningID(_ value: String) -> Bool {
    value.range(of: "^[A-Za-z0-9_.:-]{1,200}$", options: .regularExpression) != nil
}

private func learningHash(_ value: String) -> Bool {
    value.range(of: "^[a-f0-9]{64}$", options: .regularExpression) != nil
}

private func learningIDs(_ values: [String]) -> Bool {
    values.count <= 20 && Set(values).count == values.count && values.allSatisfy(learningID)
}

private func learningStoreHashes(_ values: [String: String]) -> Bool {
    values.allSatisfy { key, value in
        ["working_memory.json", "persistent_memory.json", "skills.jsonl"].contains(key) && (value == "missing" || learningHash(value))
    }
}
