import AppKit
import Foundation

// Main-actor transitions for this domain; stored state remains in AppModel.
extension AppModel {
    func openSessionSpine(for message: ChatMessage) async {
        guard !globalBusy, !client.turnOutstanding, !loadingWorkSessions, !loadingSessionSpinePreview,
              let conversation = selected, let conversationID = selectedID else { return }
        let matches = conversation.messages.indices.filter { conversation.messages[$0].id == message.id }
        guard matches.count == 1, let assistantIndex = matches.first, assistantIndex > 0,
              let rawReference = message.turnReference else {
            report(NativeError.message("Для этого ответа нет однозначного источника Session Spine. Ничего не открыто.")); return
        }
        let source = conversation.messages[assistantIndex - 1]
        let request = UUID()
        sessionSpinePreviewRequest = request
        sessionSpinePreview = nil
        loadingSessionSpinePreview = true
        defer { if sessionSpinePreviewRequest == request { loadingSessionSpinePreview = false } }
        do {
            let reference = try NativeTurnReference(rawReference)
            if sessionSpinePilotGrant?.runID != reference.value["run_id"].text {
                invalidateSessionSpinePilot()
            }
            guard reference.matches(source: source, assistant: message, conversation: conversationID) else {
                throw NativeError.message("Связь сообщения с запуском изменилась. Ничего не открыто.")
            }
            let saved = try await lookupWorkSession(reference.value["run_id"].text, conversation: conversationID)
            guard sessionSpinePreviewRequest == request, selectedID == conversationID else { return }
            let run = try reference.resolve(in: [saved], conversation: conversationID)
            workSessions = mergedWorkSessions(workSessions, with: [run])
            inspectedWorkSessionID = run.id
            let parameters = try NativeSessionSpinePreview.parameters(
                source: source, assistant: message, conversation: conversationID, reference: reference, run: run
            )
            let raw = try await client.request("session_spine_preview", parameters)
            guard sessionSpinePreviewRequest == request, selectedID == conversationID,
                  selected?.messages.indices.contains(assistantIndex) == true,
                  selected?.messages[assistantIndex] == message,
                  selected?.messages[assistantIndex - 1] == source else { return }
            sessionSpinePreview = try NativeSessionSpinePreview(
                raw, source: source, assistant: message, conversation: conversationID, reference: reference, run: run
            )
            status = "Session Spine · точная read-only проекция"
        } catch {
            if sessionSpinePreviewRequest == request && selectedID == conversationID { report(error) }
        }
    }

    func openSessionSpineReadiness(_ preview: NativeSessionSpinePreview) {
        do {
            sessionSpineReadiness = try buildSessionSpineReadiness(preview, grant: sessionSpinePilotGrant)
            error = nil
            status = sessionSpineReadiness?.recoveryRequired == true
                ? "Session Spine · нужна ручная recovery-проверка"
                : "Session Spine · writer выключен, readiness проверена"
        } catch {
            invalidateSessionSpinePilot()
            report(error)
        }
    }

    func armSessionSpinePilot(candidateHash: String) {
        do {
            guard let preview = sessionSpinePreview else {
                throw NativeError.message("Точный Session Spine preview закрыт или изменился. Проверьте ход заново.")
            }
            let refreshed = try buildSessionSpineReadiness(preview, grant: nil)
            guard refreshed.candidateHash == candidateHash, refreshed.canArm else {
                throw NativeError.message("Session Spine readiness изменилась. Ничего не подготовлено.")
            }
            let grant = try NativeSessionSpinePilotGrant(readiness: refreshed)
            let armed = try buildSessionSpineReadiness(preview, grant: grant)
            guard armed.armed else {
                throw NativeError.message("Session Spine per-launch opt-in не прошёл повторную проверку.")
            }
            sessionSpinePilotGrant = grant
            sessionSpineReadiness = armed
            sessionSpineAcceptance = nil
            sessionSpineAcceptanceGrant = nil
            error = nil
            status = "Session Spine · один точный ход подготовлен, writer выключен"
        } catch {
            invalidateSessionSpinePilot()
            report(error)
        }
    }

    func revokeSessionSpinePilot() {
        sessionSpinePilotGrant = nil
        sessionSpineAcceptance = nil
        sessionSpineAcceptanceGrant = nil
        if let preview = sessionSpinePreview {
            do { sessionSpineReadiness = try buildSessionSpineReadiness(preview, grant: nil) }
            catch { sessionSpineReadiness = nil; report(error); return }
        } else {
            sessionSpineReadiness = nil
        }
        error = nil
        status = "Session Spine · локальная подготовка снята, writer выключен"
    }

    var sessionSpinePilotArmed: Bool { sessionSpinePilotGrant != nil }
    var sessionSpineAcceptanceAccepted: Bool { sessionSpineAcceptanceGrant != nil }

    func openSessionSpineAcceptance(_ readiness: NativeSessionSpineActivationReadiness) {
        do {
            guard let preview = sessionSpinePreview, let pilot = sessionSpinePilotGrant else {
                throw NativeError.message("P2k требует активный exact-candidate P2j. Ничего не принято.")
            }
            let refreshed = try buildSessionSpineReadiness(preview, grant: pilot)
            guard refreshed.armed, refreshed.candidateHash == readiness.candidateHash,
                  refreshed.value["report_hash"] == readiness.value["report_hash"] else {
                throw NativeError.message("Session Spine readiness изменилась. Повторите проверку без записи.")
            }
            let rehearsal = try NativeSessionSpineAcceptanceRehearsal.inspect(
                readiness: refreshed,
                stateDirectory: client.configuration.stateDirectory,
                grant: sessionSpineAcceptanceGrant
            )
            if sessionSpineAcceptanceGrant?.matches(rehearsal) != true {
                sessionSpineAcceptanceGrant = nil
            }
            sessionSpineAcceptance = rehearsal
            error = nil
            status = rehearsal.recoveryRequired
                ? "Session Spine · P2k требует ручной recovery-проверки"
                : rehearsal.accepted
                    ? "Session Spine · personal rehearsal принят, writer выключен"
                    : "Session Spine · personal rehearsal готов, writer выключен"
        } catch {
            sessionSpineAcceptance = nil
            sessionSpineAcceptanceGrant = nil
            report(error)
        }
    }

    func acceptSessionSpineRehearsal(rehearsalHash: String) {
        do {
            guard let preview = sessionSpinePreview, let pilot = sessionSpinePilotGrant else {
                throw NativeError.message("P2j grant отсутствует или устарел. P2k ничего не принял.")
            }
            let readiness = try buildSessionSpineReadiness(preview, grant: pilot)
            let fresh = try NativeSessionSpineAcceptanceRehearsal.inspect(
                readiness: readiness,
                stateDirectory: client.configuration.stateDirectory
            )
            guard fresh.canAccept, fresh.rehearsalHash == rehearsalHash else {
                throw NativeError.message("P2k rehearsal или private paths изменились. Ничего не принято.")
            }
            let grant = try NativeSessionSpineAcceptanceGrant(rehearsal: fresh)
            let accepted = try NativeSessionSpineAcceptanceRehearsal.inspect(
                readiness: readiness,
                stateDirectory: client.configuration.stateDirectory,
                grant: grant
            )
            guard accepted.accepted else {
                throw NativeError.message("P2k process-memory acceptance не прошёл повторную проверку.")
            }
            sessionSpineAcceptanceGrant = grant
            sessionSpineAcceptance = accepted
            error = nil
            status = "Session Spine · exact rehearsal принят до перезапуска, writer выключен"
        } catch {
            sessionSpineAcceptance = nil
            sessionSpineAcceptanceGrant = nil
            report(error)
        }
    }

    func revokeSessionSpineAcceptance() {
        sessionSpineAcceptanceGrant = nil
        guard let readiness = sessionSpineReadiness, readiness.armed else {
            sessionSpineAcceptance = nil
            status = "Session Spine · P2k acceptance снят, writer выключен"
            return
        }
        do {
            sessionSpineAcceptance = try NativeSessionSpineAcceptanceRehearsal.inspect(
                readiness: readiness,
                stateDirectory: client.configuration.stateDirectory
            )
            error = nil
            status = "Session Spine · P2k acceptance снят, writer выключен"
        } catch {
            sessionSpineAcceptance = nil
            report(error)
        }
    }

    func openSessionSpineWriter(_ rehearsal: NativeSessionSpineAcceptanceRehearsal) async {
        guard !globalBusy, !client.turnOutstanding, !loadingSessionSpineWriter else { return }
        loadingSessionSpineWriter = true
        defer { loadingSessionSpineWriter = false }
        do {
            await refreshWorkSessions()
            let context = try buildSessionSpineWriterContext(rehearsal)
            let raw = try await client.request("session_spine_writer_preview", context.parameters)
            sessionSpineWriterPreview = try NativeSessionSpineWriterPreview(
                raw, live: context.preview, readiness: context.readiness,
                rehearsal: context.rehearsal, stateDirectory: client.configuration.stateDirectory
            )
            sessionSpineWriterReceipt = nil
            error = nil
            status = sessionSpineWriterPreview?.closed == true
                ? "Session Spine · этот exact turn уже закрыт"
                : sessionSpineWriterPreview?.canApply == true
                    ? "Session Spine · P2l ждёт точную ручную фразу"
                    : "Session Spine · P2l заблокирован evidence"
        } catch {
            sessionSpineWriterPreview = nil
            sessionSpineWriterReceipt = nil
            report(error)
        }
    }

    func applySessionSpineWriter(
        _ preview: NativeSessionSpineWriterPreview,
        token: String,
        acknowledgement: Bool
    ) async {
        guard !globalBusy, !client.turnOutstanding, !applyingSessionSpineWriter,
              sessionSpineWriterReceipt == nil else { return }
        guard preview.accepts(token: token, acknowledgement: acknowledgement) else {
            report(NativeError.message("Точная фраза P2l или acknowledgement не совпали. Ни один файл не записан."))
            return
        }
        applyingSessionSpineWriter = true
        busy = true
        var durableWriteStarted = false
        defer { applyingSessionSpineWriter = false; busy = false }
        do {
            guard let rehearsal = sessionSpineAcceptance else {
                throw NativeError.message("P2l acceptance context исчез. Ничего не записано.")
            }
            let context = try buildSessionSpineWriterContext(rehearsal)
            let refreshedRaw = try await client.request("session_spine_writer_preview", context.parameters)
            let refreshed = try NativeSessionSpineWriterPreview(
                refreshedRaw, live: context.preview, readiness: context.readiness,
                rehearsal: context.rehearsal, stateDirectory: client.configuration.stateDirectory
            )
            guard refreshed.value == preview.value, refreshed.accepts(token: token, acknowledgement: acknowledgement) else {
                throw NativeError.message("P2l preview изменился перед первой записью. Повторите проверку; ничего не записано.")
            }

            let archive = ChatArchive(conversations: conversations, selectedID: selectedID)
            durableWriteStarted = true
            let readback = try store.saveAndReadBack(archive)
            draftSave?.cancel(); dirtyDraft = false
            historyPersistence = HistoryPersistenceState()
            guard readback.sha256 == preview.source["history_sha256"].text,
                  readback.sizeBytes == preview.source["history_bytes"].integer else {
                throw NativeError.message("История была сохранена, но exact candidate изменился. Writer не вызван; проверьте history вручную.")
            }
            let identityStore = NativeSessionSpineInstallationStore(stateDirectory: client.configuration.stateDirectory)
            let existingIdentity = try identityStore.load()
            let identity = try identityStore.loadOrCreate()
            var parameters = context.parameters
            parameters["preview"] = preview.value
            parameters["confirmation_token"] = .string(token)
            parameters["owner_identity"] = identity.value
            parameters["history_sha256"] = .string(readback.sha256)
            parameters["history_bytes"] = .number(Double(readback.sizeBytes))
            parameters["history_write_performed"] = .bool(true)
            parameters["identity_created"] = .bool(existingIdentity == nil)
            let result = try await client.request("session_spine_writer_apply", parameters)
            sessionSpineWriterReceipt = try NativeSessionSpineWriterReceipt(
                result, preview: preview, identity: identity, readback: readback
            )
            error = nil
            status = "Session Spine · один exact-linked ход записан и закрыт"
        } catch {
            if durableWriteStarted { invalidateSessionSpinePilot() }
            if store.writeBlocked {
                historyPersistence = HistoryPersistenceState(hasUnsavedChanges: true, failure: error.localizedDescription, requiresRecovery: true)
            }
            report(error)
        }
    }

    private func buildSessionSpineWriterContext(
        _ rehearsal: NativeSessionSpineAcceptanceRehearsal
    ) throws -> (
        preview: NativeSessionSpinePreview,
        readiness: NativeSessionSpineActivationReadiness,
        rehearsal: NativeSessionSpineAcceptanceRehearsal,
        parameters: [String: JSONValue]
    ) {
        guard let preview = sessionSpinePreview, let pilot = sessionSpinePilotGrant,
              let conversation = selected, let conversationID = selectedID,
              let sourceID = UUID(uuidString: preview.source["user_message_id"].text),
              let assistantID = UUID(uuidString: preview.source["assistant_message_id"].text) else {
            throw NativeError.message("P2l требует свежие Live Preview и ARMED P2j evidence. Ничего не записано.")
        }
        let readiness = try buildSessionSpineReadiness(preview, grant: pilot)
        let currentRehearsal = try NativeSessionSpineAcceptanceRehearsal.inspect(
            readiness: readiness,
            stateDirectory: client.configuration.stateDirectory,
            grant: rehearsal.accepted ? sessionSpineAcceptanceGrant : nil
        )
        guard readiness.armed, currentRehearsal.value == rehearsal.value,
              currentRehearsal.accepted || currentRehearsal.recoveryRequired else {
            throw NativeError.message("P2j/P2k evidence изменилось. Writer не получил управление.")
        }
        let matches = conversation.messages.indices.filter { conversation.messages[$0].id == assistantID }
        guard matches.count == 1, let assistantIndex = matches.first, assistantIndex > 0,
              conversation.messages[assistantIndex - 1].id == sourceID,
              let referenceValue = conversation.messages[assistantIndex].turnReference else {
            throw NativeError.message("Exact-linked пара P2l больше не существует. Ничего не записано.")
        }
        let source = conversation.messages[assistantIndex - 1]
        let assistant = conversation.messages[assistantIndex]
        let reference = try NativeTurnReference(referenceValue)
        let run = try reference.resolve(in: workSessions, conversation: conversationID)
        let checked = try NativeSessionSpinePreview(
            preview.value, source: source, assistant: assistant,
            conversation: conversationID, reference: reference, run: run
        )
        var parameters = try NativeSessionSpinePreview.parameters(
            source: source, assistant: assistant, conversation: conversationID, reference: reference, run: run
        )
        parameters["gate"] = .object([
            "acceptance_state": .string(currentRehearsal.state),
            "candidate_hash": .string(readiness.candidateHash),
            "readiness_report_hash": readiness.value["report_hash"],
            "rehearsal_hash": .string(currentRehearsal.rehearsalHash),
            "acceptance_report_hash": currentRehearsal.value["report_hash"],
        ])
        return (checked, readiness, currentRehearsal, parameters)
    }

    private func buildSessionSpineReadiness(
        _ preview: NativeSessionSpinePreview,
        grant: NativeSessionSpinePilotGrant?
    ) throws -> NativeSessionSpineActivationReadiness {
        guard let conversation = selected, let conversationID = selectedID,
              conversation.id == conversationID,
              UUID(uuidString: preview.source["conversation_id"].text) == conversationID,
              let sourceID = UUID(uuidString: preview.source["user_message_id"].text),
              let assistantID = UUID(uuidString: preview.source["assistant_message_id"].text) else {
            throw NativeError.message("Session Spine readiness относится к другому диалогу. Ничего не подготовлено.")
        }
        let assistantMatches = conversation.messages.indices.filter { conversation.messages[$0].id == assistantID }
        guard assistantMatches.count == 1, let assistantIndex = assistantMatches.first, assistantIndex > 0,
              conversation.messages[assistantIndex - 1].id == sourceID,
              let rawReference = conversation.messages[assistantIndex].turnReference else {
            throw NativeError.message("Точная пара сообщений Session Spine больше не существует. Ничего не подготовлено.")
        }
        let source = conversation.messages[assistantIndex - 1]
        let assistant = conversation.messages[assistantIndex]
        let reference = try NativeTurnReference(rawReference)
        let run = try reference.resolve(in: workSessions, conversation: conversationID)
        let checked = try NativeSessionSpinePreview(
            preview.value, source: source, assistant: assistant,
            conversation: conversationID, reference: reference, run: run
        )
        let identityStore = NativeSessionSpineInstallationStore(stateDirectory: client.configuration.stateDirectory)
        let identity: NativeSessionSpineInstallationIdentity?
        do {
            identity = try identityStore.load()
        } catch {
            return try NativeSessionSpineActivationReadiness.inspect(
                preview: checked, identity: nil, identityPath: identityStore.url,
                identityError: error.localizedDescription, grant: nil
            )
        }
        return try NativeSessionSpineActivationReadiness.inspect(
            preview: checked, identity: identity,
            identityPath: identityStore.url, grant: grant
        )
    }

    func invalidateSessionSpinePilot() {
        sessionSpinePilotGrant = nil
        sessionSpineReadiness = nil
        sessionSpineAcceptanceGrant = nil
        sessionSpineAcceptance = nil
        sessionSpineWriterPreview = nil
        sessionSpineWriterReceipt = nil
    }

}
