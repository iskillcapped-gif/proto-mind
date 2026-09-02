import Foundation

struct NativeSkillInspectionSelection: Equatable {
    let conversationID: UUID?
    let skillID: String
    let workspace: String?
    let expectedSHA256: String

    var parameters: [String: JSONValue] {
        var result: [String: JSONValue] = ["conversation_id": .string(conversationID?.uuidString ?? ""),
            "skill_id": .string(skillID), "expected_sha256": .string(expectedSHA256)]
        if let workspace { result["workspace_root"] = .string(workspace) }
        return result
    }

    func matchesWorkspace(_ reported: String) -> Bool {
        guard let workspace else { return reported.isEmpty }
        guard reported.hasPrefix("/"), workspace.hasPrefix("/"), reported.count <= 4096 else { return false }
        return URL(fileURLWithPath: reported).resolvingSymlinksInPath().standardizedFileURL.path ==
            URL(fileURLWithPath: workspace).resolvingSymlinksInPath().standardizedFileURL.path
    }
}

enum NativeSkillLifecycleState: String, Decodable {
    case activeVerified = "active_verified", activeHistorical = "active_historical"
    case activeRestoredVerified = "active_restored_verified", archivedVerified = "archived_verified"
    case archivedAmbiguous = "archived_ambiguous", drifted, legacyUnprovenanced = "legacy_unprovenanced"
    case unprovenanced, invalid

    var title: String {
        switch self {
        case .activeVerified: return "Активен · происхождение проверено"
        case .activeHistorical: return "Активен · источник исторический"
        case .activeRestoredVerified: return "Восстановлен · переход проверен"
        case .archivedVerified: return "В архиве · причина подтверждена"
        case .archivedAmbiguous: return "В архиве · причина неизвестна"
        case .drifted: return "Описание изменилось после подтверждения"
        case .legacyUnprovenanced, .unprovenanced: return "Историческая запись · без цепочки доказательств"
        case .invalid: return "Состояние не прошло проверку"
        }
    }

    var verifiedState: Bool {
        [.activeVerified, .activeHistorical, .activeRestoredVerified, .archivedVerified].contains(self)
    }
}

struct NativeSkillLifecycle: Decodable {
    let skillId: String
    let state: NativeSkillLifecycleState
    let status: String
    let provenanceStatus: String
    let provenanceId: String
    let sourceLessonId: String
    let sourceStatus: String
    let appliedAt: String
    let lifecycleEvidence: String
    let lifecycleReason: String
    let outcomeArchiveProven: Bool
    let restartSafe: Bool
    let executable: Bool
    let issues: [String]
    let warnings: [String]

    var storedStatusTitle: String {
        switch status { case "active": return "Активен"; case "archived": return "В архиве"; default: return "Неизвестен / некорректен" }
    }

    func valid(skill: String) -> Bool {
        skillId == skill && restartSafe == state.verifiedState &&
        (!executable || state == .invalid) && (!restartSafe || (!executable && !provenanceId.isEmpty)) &&
        (provenanceId.isEmpty || inspectionID(provenanceId)) && (sourceLessonId.isEmpty || inspectionID(sourceLessonId)) &&
        appliedAt.count <= 100 && status.count <= 200 && sourceStatus.count <= 200 &&
        ["UNAVAILABLE", "ERROR", "VERIFIED", "HISTORICAL", "DRIFTED"].contains(provenanceStatus) &&
        inspectionFindings(issues) && inspectionFindings(warnings)
    }
}

struct NativeSkillTransition: Decodable, Identifiable {
    let kind: String
    let occurredAt: String
    let id: String
    let hash: String
    let reason: String
    let evidenceCount: Int

    var title: String {
        switch kind { case "apply": return "Сохранён из подтверждённого урока"; case "archive": return "Архивирован оператором"; default: return "Восстановлен оператором" }
    }
    var valid: Bool {
        ["apply", "archive", "restore"].contains(kind) && inspectionID(id) && inspectionHash(hash) &&
        !occurredAt.isEmpty && occurredAt.count <= 100 && reason.count <= 1000 && (0...64).contains(evidenceCount)
    }
}

struct NativeSkillOutcomeSignal: Decodable, Identifiable {
    let eventId: String
    let eventType: String
    let createdAt: String
    let signal: String
    let reason: String
    let useEventId: String
    var id: String { "\(eventId):\(useEventId)" }
    var successful: Bool { signal == "SUCCESS_EVIDENCE" }
    var valid: Bool {
        inspectionID(eventId) && inspectionID(useEventId) && createdAt.count <= 100 && reason.count <= 2000 &&
        ["tool_succeeded", "tool_failed", "user_corrected"].contains(eventType) &&
        ["SUCCESS_EVIDENCE", "FAILURE_EVIDENCE"].contains(signal)
    }
}

struct NativeSkillOutcome: Decodable {
    let status: String
    let scope: String
    let pilotAvailable: Bool
    let eventCount: Int
    let manualUseCount: Int
    let signalCount: Int
    let signals: [NativeSkillOutcomeSignal]
    let checks: [String: Bool]
    let preRestoreUseCount: Int
    let unboundPostRestoreUseCount: Int
    let postRestore: Bool
    let usesMetricIgnored: Bool
    let automaticDecisionAllowed: Bool
    let postRestoreCaptureInstalled: Bool
    let issues: [String]
    let warnings: [String]

    var title: String {
        switch status {
        case "SUCCESS_CANDIDATE", "POST_RESTORE_SUCCESS_CANDIDATE": return "Есть подтверждённый оператором успех"
        case "FAILURE_CANDIDATE", "POST_RESTORE_FAILURE_CANDIDATE": return "Есть ошибка или исправление оператора"
        case "MIXED_EVIDENCE", "POST_RESTORE_MIXED_EVIDENCE": return "Результаты противоречивы"
        case "NEEDS_POST_RESTORE_EVIDENCE": return "Нужен новый опыт после восстановления"
        case "NEEDS_MORE_EVIDENCE": return "Доказательств результата пока недостаточно"
        case "ERROR": return "Доказательства результата не прошли проверку"
        default: return "Результат использования неизвестен"
        }
    }
    var valid: Bool {
        let statuses = ["UNAVAILABLE", "ERROR", "NOT_FOUND", "NOT_RESTORED", "NEEDS_MORE_EVIDENCE", "NEEDS_POST_RESTORE_EVIDENCE",
            "SUCCESS_CANDIDATE", "FAILURE_CANDIDATE", "MIXED_EVIDENCE", "POST_RESTORE_SUCCESS_CANDIDATE",
            "POST_RESTORE_FAILURE_CANDIDATE", "POST_RESTORE_MIXED_EVIDENCE"]
        let candidate = status.contains("CANDIDATE") || status.contains("MIXED_EVIDENCE")
        return statuses.contains(status) && scope == "selected_conversation_process_memory" &&
            usesMetricIgnored && !automaticDecisionAllowed && !postRestoreCaptureInstalled &&
            (0...256).contains(eventCount) && (0...256).contains(manualUseCount) &&
            (0...256).contains(preRestoreUseCount) && (0...256).contains(unboundPostRestoreUseCount) &&
            signalCount == signals.count && signalCount <= eventCount && signals.allSatisfy(\.valid) &&
            (!candidate || (pilotAvailable && manualUseCount > 0 && signalCount > 0 && issues.isEmpty)) &&
            (!postRestore || !["SUCCESS_CANDIDATE", "FAILURE_CANDIDATE", "MIXED_EVIDENCE"].contains(status)) &&
            (pilotAvailable || eventCount == 0) && checks.count <= 32 && inspectionFindings(issues) && inspectionFindings(warnings)
    }
}

struct NativeSkillRestoreEvidence: Decodable {
    let status: String
    let evidenceId: String
    let evidenceHash: String
    let restoreMetadataId: String
    let restoreMetadataHash: String
    let processReceiptStatus: String
    let processReceiptId: String
    let processReceiptHash: String
    let currentStateVerified: Bool
    let restartSafe: Bool
    let originalApplyReceiptReconstructed: Bool
    let processReceiptPersisted: Bool

    var valid: Bool {
        ["VERIFIED", "ERROR"].contains(status) && !originalApplyReceiptReconstructed && !processReceiptPersisted &&
        ["MATCHED", "NOT_AVAILABLE", "LEGACY", "INVALID", "MISMATCH"].contains(processReceiptStatus) &&
        (status != "VERIFIED" || (currentStateVerified && restartSafe && inspectionID(evidenceId) && inspectionHash(evidenceHash))) &&
        inspectionID(restoreMetadataId) && inspectionHash(restoreMetadataHash) &&
        processReceiptId.count <= 200 && processReceiptHash.count <= 64
    }
}

struct NativeSkillInspection: Decodable {
    let schema: String
    let readOnly: Bool
    let conversationId: String
    let skillId: String
    let workspacePath: String
    let status: String
    let name: String
    let usesDisplay: String
    let skillStoreScope: String
    let projectIsolationEnforced: Bool
    let storeHashes: [String: String]
    let changedSinceSelection: Bool
    let lifecycle: NativeSkillLifecycle?
    let transitions: [NativeSkillTransition]
    let restore: NativeSkillRestoreEvidence?
    let outcome: NativeSkillOutcome?
    let issues: [String]
    let warnings: [String]
    let historyComplete: Bool

    static func decode(_ value: JSONValue, selection: NativeSkillInspectionSelection) throws -> Self {
        let falseFlags: Set<String> = ["store_mutation_performed", "model_call_performed", "network_call_performed", "retrieval_performed",
            "consent_state_changed", "context_injection_changed", "permissions_changed", "automatic_action"]
        let fields: Set<String> = ["schema", "read_only", "no_execution", "conversation_id", "skill_id", "workspace_path", "status", "name",
            "uses_display", "skill_store_scope", "project_isolation_enforced", "store_hashes", "changed_since_selection", "lifecycle", "transitions",
            "restore", "outcome", "issues", "warnings", "history_complete"]
        guard case .object(let root) = value, Set(root.keys) == fields.union(falseFlags),
              value["no_execution"] == .bool(true), falseFlags.allSatisfy({ value[$0] == .bool(false) }) else {
            throw NativeError.message("Контракт просмотра навыка изменился. Никаких действий не выполнено.")
        }
        let bytes = try JSONEncoder().encode(value)
        guard bytes.count <= 512_000 else { throw NativeError.message("Ответ превышает предел просмотра навыка.") }
        let decoder = JSONDecoder(); decoder.keyDecodingStrategy = .convertFromSnakeCase
        let report = try decoder.decode(Self.self, from: bytes)
        let conversationMatches = selection.conversationID.map { UUID(uuidString: report.conversationId) == $0 } ?? report.conversationId.isEmpty
        let invalid = NativeError.message("Не удалось проверить карточку результата и жизненного цикла. Источники не изменены.")
        guard report.schema == "proto_mind.native_skill_inspection.v1", report.readOnly, conversationMatches,
              report.skillId == selection.skillID, selection.matchesWorkspace(report.workspacePath),
              ["OK", "WARN", "ERROR", "NOT_FOUND", "UNAVAILABLE"].contains(report.status),
              report.name.count <= 200, report.usesDisplay.count <= 100,
              report.skillStoreScope == "global_legacy_stores", !report.projectIsolationEnforced, !report.historyComplete else { throw invalid }
        guard report.storeHashes.allSatisfy({ ["skills.jsonl", "persistent_memory.json"].contains($0.key) && ($0.value == "missing" || inspectionHash($0.value)) }),
              inspectionFindings(report.issues), inspectionFindings(report.warnings) else { throw invalid }
        // Explicit unwrapping also avoids an optimized Swift optional-borrow compiler failure.
        var verifiedState = false, restoredState = false
        if let lifecycle = report.lifecycle {
            guard lifecycle.valid(skill: selection.skillID) else { throw invalid }
            verifiedState = lifecycle.restartSafe
            restoredState = lifecycle.state == .activeRestoredVerified
        }
        if let outcome = report.outcome {
            guard report.lifecycle != nil, outcome.valid, outcome.postRestore == restoredState else { throw invalid }
        }
        if let restore = report.restore {
            guard restoredState, restore.valid else { throw invalid }
        }
        guard report.transitions.count <= 3, report.transitions.allSatisfy(\.valid),
              report.transitions.isEmpty || verifiedState else { throw invalid }
        if report.status == "OK", !report.issues.isEmpty || !verifiedState { throw invalid }
        return report
    }

    var nextAdvice: String {
        if status == "ERROR" { return "Сначала проверьте отмеченные несоответствия в исходных данных. Автоматического исправления нет." }
        if status == "NOT_FOUND" { return "Обновите список навыков: выбранная запись отсутствует. Ничего не восстановлено автоматически." }
        if lifecycle?.state == .activeRestoredVerified { return "Оценивайте навык заново после восстановления. Старые результаты исключены; запись нового опыта после восстановления остаётся отдельным этапом разработки." }
        if lifecycle?.state == .archivedVerified || lifecycle?.state == .archivedAmbiguous { return "Сначала изучите сохранённую причину архивации. Просмотр не восстанавливает навык и не запускает его." }
        if lifecycle?.restartSafe == false { return "Сохраните историческую запись как есть или отдельно запланируйте проверку происхождения. Этот экран ничего не дописывает." }
        return "Сопоставьте описание навыка с ручным результатом. Наличие сигнала не изменяет навык: любое решение о его жизненном цикле принимается отдельно." }
}

private func inspectionID(_ value: String) -> Bool { value.range(of: "^[A-Za-z0-9_.:-]{1,200}$", options: .regularExpression) != nil }
private func inspectionHash(_ value: String) -> Bool { value.range(of: "^[a-f0-9]{64}$", options: .regularExpression) != nil }
private func inspectionFindings(_ values: [String]) -> Bool { values.count <= 200 && values.allSatisfy { $0.count <= 4000 } }
