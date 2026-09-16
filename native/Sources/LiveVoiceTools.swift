import Foundation

extension AppModel {
    var liveVoiceProjects: [String] {
        Array(Set(listedConversations.filter { !$0.archived }.compactMap(\.workspacePath))).sorted()
    }

    func liveVoiceTaskStatus(_ id: UUID) throws -> JSONValue {
        guard let conversation = conversations.first(where: { $0.id == id && !$0.archived }) else {
            throw NativeError.message("Диалог не найден или находится в архиве.")
        }
        let state = executions[id]
        let answer = conversation.messages.last { $0.role == "assistant" || $0.role == "report" }
        let status = state?.running == true ? "running" : answer == nil ? "idle" : answer?.isError == true ? "needs_attention" : "response_received"
        return .object(["conversation_id": .string(id.uuidString), "title": .string(conversation.title),
            "status": .string(status), "access": .string(hasAgentAccessSelection(conversation) ? "full_access" : "chat"),
            "project_path": conversation.workspacePath.map(JSONValue.string) ?? .null,
            "provider": .string(conversation.provider), "model": .string(conversation.model),
            "answer": .string(String((answer?.text ?? "").prefix(6000))),
            "updates": .array((conversation.messages.last { $0.role == "user" }?.taskUpdates ?? []).map {
                .object(["id": .string($0.id.uuidString), "state": .string($0.state.rawValue)])
            })])
    }

    func executeLiveVoiceCall(_ call: LiveVoiceCall, session: UUID) async throws -> JSONValue {
        guard cloudConsent, !privateBackupRestartRequired, !operationBusy else {
            throw NativeError.message("Сейчас управление задачами недоступно. Проверьте настройки и восстановление данных.")
        }
        try PrivateStateAccess.requireAvailable(serviceClient.configuration.stateDirectory)
        let args = call.arguments
        switch call.name {
        case "list_projects":
            return .object(["status": .string("ok"), "projects": .array(liveVoiceProjects.map {
                .object(["name": .string(URL(fileURLWithPath: $0).lastPathComponent), "path": .string($0)])
            })])
        case "list_tasks":
            let recent = listedConversations.filter { !$0.archived }.sorted { $0.updatedAt > $1.updatedAt }
            let included = recent.filter { isRunning($0.id) || $0.id == selectedID }
                + recent.filter { !isRunning($0.id) && $0.id != selectedID }.prefix(60)
            let rows: [JSONValue] = included.map { conversation in
                .object(["id": .string(conversation.id.uuidString), "title": .string(conversation.title),
                    "project_path": conversation.workspacePath.map(JSONValue.string) ?? .null,
                    "running": .bool(isRunning(conversation.id)), "access": .string(hasAgentAccessSelection(conversation) ? "full_access" : "chat")])
            }
            return .object(["status": .string("ok"), "selected_id": selectedID.map { .string($0.uuidString) } ?? .null,
                "tasks": .array(rows), "partial": .bool(included.count < recent.count)])
        case "open_task":
            let id = try voiceConversationID(args)
            guard canNavigateConversations else { throw NativeError.message("Дождитесь завершения выбора вложений или восстановления данных.") }
            select(id)
            guard selectedID == id, !historyPersistence.blocksSubmission else { throw NativeError.message("Не удалось сохранить переключение диалога.") }
            return try liveVoiceTaskStatus(id)
        case "create_task":
            guard canNavigateConversations, !historyPersistence.blocksSubmission, !store.writeBlocked else { throw NativeError.message("Сейчас нельзя создать новый диалог.") }
            let path = args["project_path"].isNull ? nil : args["project_path"].text
            guard path == nil || liveVoiceProjects.contains(path!) else {
                throw NativeError.message("Эта папка ещё не открыта в Proto-Mind. Выберите её через «Открыть проект», затем повторите команду.")
            }
            let title = args["title"].text.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !title.isEmpty, title.count <= 160 else { throw NativeError.message("Нужно короткое название задачи.") }
            flushDraft()
            guard !historyPersistence.blocksSubmission else { throw NativeError.message("Черновик не сохранён. Новый диалог не создан.") }
            var conversation = Conversation()
            conversation.title = title; conversation.workspacePath = path
            conversation.provider = selected?.provider ?? "codex"; conversation.model = selected?.model ?? ""
            conversation.reasoningEffort = selected?.reasoningEffort ?? ""
            conversations.insert(conversation, at: 0)
            guard persist() else { conversations.removeAll { $0.id == conversation.id }; throw NativeError.message("Не удалось сохранить новый диалог.") }
            select(conversation.id)
            return try liveVoiceTaskStatus(conversation.id)
        case "task_status": return try liveVoiceTaskStatus(voiceConversationID(args))
        case "stop_task":
            let id = try voiceConversationID(args)
            guard let state = executions[id], state.running, let request = state.requestID else {
                throw NativeError.message("У этой задачи нет активного запроса для остановки.")
            }
            closeTaskUpdateQueue(execution: state); persist()
            let result = try await state.client.request("cancel", ["request_id": .string(request)])
            return .object(["status": .string("cancellation_requested"), "notice": result["notice"], "conversation_id": .string(id.uuidString)])
        case "send_task_message":
            let id = try voiceConversationID(args)
            return try await sendLiveVoiceTaskMessage(args["text"].text, id: id, session: session)
        case "list_browser_pages":
            return .object(["pages": .array(browserPages.map { item in
                .object(["browser_id": .string(item.browser.id.uuidString), "title": .string(item.browser.title),
                    "url": .string(item.browser.currentURL?.absoluteString ?? ""),
                    "selected": .bool(item.panel.selected.map { if case .browser(let browser) = $0.content { return browser === item.browser }; return false } ?? false)])
            })])
        case "send_browser_page":
            let id = try voiceConversationID(args)
            guard let browserID = UUID(uuidString: args["browser_id"].text),
                  let browser = browserPages.first(where: { $0.browser.id == browserID })?.browser else {
                throw NativeError.message(L10n.pick("Вкладка браузера уже закрыта. Обновите список страниц.", "That browser tab is closed. List the pages again."))
            }
            let snapshot = try await browser.capturePage()
            guard cloudConsent, !operationBusy, !privateBackupRestartRequired,
                  conversations.contains(where: { $0.id == id && !$0.archived }) else {
                throw NativeError.message(L10n.pick("Условия отправки изменились. Страница не отправлена.", "The destination changed. The page was not sent."))
            }
            let message = try snapshot.message(instruction: args["text"].text)
            return try await sendLiveVoiceTaskMessage(message, id: id, session: session)
        default: throw NativeError.message("Неизвестная голосовая команда.")
        }
    }

    /// Explicit voice input carries its own context and never consumes the editor.
    private func sendLiveVoiceTaskMessage(_ supplied: String, id: UUID, session: UUID) async throws -> JSONValue {
        let text = supplied.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty, text.unicodeScalars.count <= 20_000,
              !historyPersistence.blocksSubmission, !store.writeBlocked else { throw NativeError.message("Сообщение пустое, слишком большое или история требует восстановления.") }
        let state = execution(for: id)
        if state.running { return try enqueueVoiceTaskUpdate(text, execution: state) }
        state.running = true
        do {
            let description = try await state.client.request("describe", ["text": .string(text)])
            guard !description["blocked"].flag, !description["operator"].flag, !description["requires_confirmation"].flag else {
                throw NativeError.message("Команды изменения самого ядра выполняются через текстовый интерфейс с его подтверждениями.")
            }
            try await ensureAgentAccess(for: state)
            try Task.checkCancellation()
            guard cloudConsent, !operationBusy, conversations.contains(where: { $0.id == id && !$0.archived }) else {
                throw NativeError.message("Условия запуска изменились. Задача не запускалась.")
            }
            let lastMessageBefore = conversations.first { $0.id == id }?.messages.last?.id
            Task { @MainActor in
                await perform(text, execution: state, confirmed: false, operatorInput: false, useDraft: false)
                if var result = try? liveVoiceTaskStatus(id) {
                    if conversations.first(where: { $0.id == id })?.messages.last?.id == lastMessageBefore {
                        result = .object(["status": .string("needs_attention"), "answer": .string("Запрос не удалось сохранить или запустить. Проверьте сообщение об ошибке в приложении.")])
                    }
                    liveVoice.taskFinished(id, session: session, result: result)
                }
            }
            return .object(["status": .string("preparing"), "conversation_id": .string(id.uuidString)])
        } catch { state.running = false; throw error }
    }

    private func voiceConversationID(_ args: JSONValue) throws -> UUID {
        guard let id = UUID(uuidString: args["conversation_id"].text),
              conversations.contains(where: { $0.id == id && !$0.archived }) else { throw NativeError.message("Не найден точный диалог для этой команды.") }
        return id
    }
}
