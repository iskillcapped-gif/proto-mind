import AppKit
import Foundation

// Main-actor transitions for this domain; stored state remains in AppModel.
extension AppModel {
    func refreshWorkSessions() async {
        await loadWorkSessionPage(cursor: nil, append: false)
    }

    func loadMoreWorkSessions() async {
        guard let cursor = workSessionsNextCursor else { return }
        await loadWorkSessionPage(cursor: cursor, append: true)
    }

    private func loadWorkSessionPage(cursor: JSONValue?, append: Bool) async {
        guard !busy, !loadingWorkSessions, let id = selectedID else { return }
        let request = UUID(); workSessionsRequest = request; loadingWorkSessions = true
        defer { if request == workSessionsRequest { loadingWorkSessions = false } }
        do {
            var params: [String: JSONValue] = ["conversation_id": .string(id.uuidString)]
            if let cursor { params["cursor"] = cursor }
            let raw = try await serviceClient.request("work_sessions", params)
            guard request == workSessionsRequest, id == selectedID else { return }
            let page = try NativeWorkSessionPage(raw, conversation: id, project: client.configuration.projectRoot, cursor: cursor)
            var runs = page.runs
            var warning = page.warning
            let retainedID = workSessions.first { $0.id == inspectedWorkSessionID
                && UUID(uuidString: $0.value["conversation_id"].text) == id }?.id
            if !append, let retainedID, !runs.contains(where: { $0.id == retainedID }) {
                do { runs.append(try await lookupWorkSession(retainedID, conversation: id)) }
                catch { warning = [warning, error.localizedDescription].compactMap { $0 }.joined(separator: "\n") }
            }
            guard request == workSessionsRequest, id == selectedID else { return }
            workSessions = mergedWorkSessions(append ? workSessions : [], with: runs)
            workSessionsPath = page.path; workSessionsTotal = page.total
            workSessionsNextCursor = page.nextCursor; workSessionsWarning = warning
        } catch {
            guard request == workSessionsRequest, id == selectedID else { return }
            if !append { workSessions = []; workSessionsTotal = nil; workSessionsNextCursor = nil }
            workSessionsWarning = error.localizedDescription
        }
    }

    func lookupWorkSession(_ runID: String, conversation: UUID) async throws -> NativeWorkSession {
        let value = try await serviceClient.request("work_session_lookup", ["conversation_id": .string(conversation.uuidString), "run_id": .string(runID)])
        guard value["schema"] == .string("proto_mind.native_work_session_lookup.v1"), value["read_only"] == .bool(true) else {
            throw NativeWorkSessionPage.error()
        }
        let run = try NativeWorkSession(value["run"])
        guard run.id == runID, UUID(uuidString: run.value["conversation_id"].text) == conversation,
              NativeWorkSessionPage.matchesProject(run.value["project_root"], client.configuration.projectRoot) else { throw NativeWorkSessionPage.error() }
        return run
    }

    func mergedWorkSessions(_ existing: [NativeWorkSession], with incoming: [NativeWorkSession]) -> [NativeWorkSession] {
        var byID = Dictionary(uniqueKeysWithValues: existing.map { ($0.id, $0) })
        for run in incoming { byID[run.id] = run }
        return byID.values.sorted { NativeWorkSessionPage.key($0) > NativeWorkSessionPage.key($1) }
    }

    func resetWorkSessionPages() {
        workSessionsRequest = UUID(); loadingWorkSessions = false
        workSessions = []; workSessionsWarning = nil; workSessionsTotal = nil; workSessionsNextCursor = nil
        inspectedWorkSessionID = nil; workSessionsActionError = nil
    }

    var workSessionNoticeToShow: NativeWorkSession? {
        workSessions.first { $0.needsReview && UUID(uuidString: $0.value["conversation_id"].text) == selectedID && !isWorkSessionWarningHidden($0) }
    }

    var hasWorkSessionNotice: Bool { workSessionsWarning != nil || workSessionNoticeToShow != nil }

    func isWorkSessionWarningHidden(_ run: NativeWorkSession) -> Bool {
        guard run.needsReview, UUID(uuidString: run.value["conversation_id"].text) == selectedID else { return false }
        return selected?.dismissedWorkSessionWarnings.contains { $0.matches(run) } == true
    }

    func openWorkSessions(_ run: NativeWorkSession? = nil, in source: WorkspacePresentations? = nil) {
        presentations.prepare("workSessions", in: source ?? presentations.currentDestination)
        inspectedWorkSessionID = run?.id
        showWorkSessions = true
    }

    func openWorkSession(for message: ChatMessage, in source: WorkspacePresentations? = nil) async {
        guard !busy, !loadingWorkSessions, let raw = message.turnReference, let conversation = selectedID else { return }
        let destination = source ?? presentations.currentDestination
        let request = UUID(); workSessionsRequest = request; loadingWorkSessions = true
        defer { if request == workSessionsRequest { loadingWorkSessions = false } }
        do {
            let reference = try NativeTurnReference(raw)
            guard let index = selected?.messages.firstIndex(where: { $0.id == message.id }), index > 0,
                  selected?.messages[index] == message, let source = selected?.messages[index - 1],
                  reference.matches(source: source, assistant: message, conversation: conversation) else {
                throw NativeError.message(L10n.text("Связь сообщения с запуском изменилась. Ничего не открыто."))
            }
            let saved = try await lookupWorkSession(reference.value["run_id"].text, conversation: conversation)
            guard request == workSessionsRequest, selectedID == conversation,
                  selected?.messages.indices.contains(index) == true, selected?.messages[index] == message,
                  selected?.messages[index - 1] == source else { return }
            let run = try reference.resolve(in: [saved], conversation: conversation)
            workSessions = mergedWorkSessions(workSessions, with: [run])
            workSessionsActionError = nil
            openWorkSessions(run, in: destination)
        } catch { if request == workSessionsRequest && selectedID == conversation { report(error) } }
    }


    func setWorkSessionWarningHidden(_ run: NativeWorkSession, hidden: Bool) throws {
        guard !busy, !client.turnOutstanding, !loadingWorkSessions,
              let index = conversations.firstIndex(where: { $0.id == selectedID }),
              UUID(uuidString: run.value["conversation_id"].text) == selectedID,
              let current = workSessions.first(where: { $0.id == run.id }), current.reference == run.reference,
              current.state == run.state, current.needsReview else {
            throw NativeError.message(L10n.text("Запуск изменился или работа ещё идёт. Обновите журнал; уведомление не скрыто."))
        }
        let notice = try NativeWorkSessionNotice(current)
        let previous = conversations[index].dismissedWorkSessionWarnings
        if hidden && previous.contains(notice) { return }
        var next = previous.filter { $0.runID != notice.runID }
        if hidden { next.append(notice) }
        try NativeWorkSessionNotice.validate(next)
        guard next != previous else { return }
        conversations[index].dismissedWorkSessionWarnings = next
        do {
            try saveHistory()
        } catch {
            conversations[index].dismissedWorkSessionWarnings = previous
            throw error
        }
    }

    func prepareContinuation(_ run: NativeWorkSession) async {
        workSessionsActionError = nil
        guard !busy, !client.turnOutstanding, run.canPrepare, let chat = selected,
              UUID(uuidString: run.value["conversation_id"].text) == chat.id, !chat.archived else { return }
        busy = true
        defer { busy = false }
        do {
            try requireEmptyContinuationDraft(chat)
            let draft = try await continuationDraft(run, conversation: chat)
            guard selected == chat else { throw continuationChangedError() }
            try requireEmptyContinuationDraft(chat)
            installContinuationDraft(draft, run: run, conversation: chat.id)
        } catch { workSessionsActionError = error.localizedDescription; report(error) }
    }

    func prepareHistoryContinuation(messageID: UUID, conversationID: UUID) async {
        workSessionsActionError = nil
        guard !busy, !client.turnOutstanding, let chat = conversations.first(where: { $0.id == conversationID }),
              !chat.archived else { return }
        let origin = selectedID
        busy = true
        defer { busy = false }
        do {
            try requireEmptyContinuationDraft(chat)
            guard let index = chat.messages.firstIndex(where: { $0.id == messageID }), index > 0,
                  chat.messages[index].role == "assistant", !chat.messages[index].isError,
                  let raw = chat.messages[index].turnReference else { throw continuationChangedError() }
            let reference = try NativeTurnReference(raw)
            guard reference.matches(source: chat.messages[index - 1], assistant: chat.messages[index], conversation: chat.id) else {
                throw continuationChangedError()
            }
            let saved = try await lookupWorkSession(reference.value["run_id"].text, conversation: chat.id)
            let run = try reference.resolve(in: [saved], conversation: chat.id)
            guard run.canPrepare else { throw continuationChangedError() }
            let draft = try await continuationDraft(run, conversation: chat)
            guard selectedID == origin, conversations.first(where: { $0.id == chat.id }) == chat else {
                throw continuationChangedError()
            }
            try requireEmptyContinuationDraft(chat)
            // Both reads are complete. Select only now, preserving the other dialog's draft.
            busy = false
            returnToConversation(chat.id)
            installContinuationDraft(draft, run: run, conversation: chat.id)
        } catch { workSessionsActionError = error.localizedDescription; report(error) }
    }

    private func requireEmptyContinuationDraft(_ chat: Conversation) throws {
        guard chat.draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
              chat.id != selectedID || composer.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
              chat.pendingFiles.isEmpty, chat.pendingImages.isEmpty, chat.pendingPDFs.isEmpty,
              chat.pendingCriteria.isEmpty, projectNoteSelections[chat.id, default: []].isEmpty,
              preparedSkillTasks[chat.id] == nil else {
            throw NativeError.message(L10n.text("В этом диалоге уже есть черновик или выбранный контекст. Откройте его: продолжение не заменит ваш ввод и вложения."))
        }
    }

    private func continuationDraft(_ run: NativeWorkSession, conversation chat: Conversation) async throws -> String {
        var params: [String: JSONValue] = ["conversation_id": .string(chat.id.uuidString), "continuation": run.reference]
        if let root = chat.workspacePath { params["workspace_root"] = .string(root) }
        let result = try await client.request("work_session_continuation", params)
        guard result["schema"].text == "proto_mind.native_continuation.v1", result["read_only"] == .bool(true),
              result["automatic_resume"] == .bool(false), result["run_id"].text == run.id,
              result["fingerprint"] == run.value["fingerprint"], !result["draft"].text.isEmpty,
              result["draft"].text.count <= 5000 else { throw continuationChangedError() }
        return result["draft"].text
    }

    private func continuationChangedError() -> NativeError {
        NativeError.message(L10n.text("Диалог или сохранённая работа изменились. Откройте историю заново. Ничего не отправлено."))
    }

    private func installContinuationDraft(_ draft: String, run: NativeWorkSession, conversation: UUID) {
        guard selectedID == conversation, let index = conversations.firstIndex(where: { $0.id == conversation }) else { return }
        conversations[index].draftContinuation = run.reference
        setComposer(draft, preservingContinuation: true)
        invalidateContextPreview()
        flushDraft(); section = .chat; showWorkSessions = false
        transcriptDestination = TranscriptDestination(conversationID: conversation, messageID: nil)
        status = L10n.text("Черновик подготовлен · проверьте и отправьте вручную")
    }

    func clearContinuation() {
        guard !busy, let index = conversations.firstIndex(where: { $0.id == selectedID }) else { return }
        conversations[index].draftContinuation = nil
        persist()
    }

}
