import AppKit
import Foundation

// Main-actor transitions for this domain; stored state remains in AppModel.
extension AppModel {
    func submit(_ supplied: String? = nil) async {
        if supplied == nil { dictation.stop(for: selectedID) }
        guard let conversationID = selectedID else { return }
        await submit(conversationID: conversationID, supplied: supplied)
    }

    func submit(conversationID: UUID, supplied: String? = nil) async {
        if supplied == nil { dictation.stop(for: conversationID) }
        guard let conversation = conversations.first(where: { $0.id == conversationID }) else { return }
        let hasAttachments = !conversation.pendingFiles.isEmpty || !conversation.pendingImages.isEmpty || !conversation.pendingPDFs.isEmpty
        let draftText = (supplied ?? conversation.draft).trimmingCharacters(in: .whitespacesAndNewlines)
        let text = draftText.isEmpty && hasAttachments
            ? (isRunning(conversationID) ? L10n.text("Учти вложения в текущей задаче.") : L10n.text("Посмотри вложения.")) : draftText
        if isRunning(conversationID) {
            if !text.isEmpty && !loadingDroppedAttachments && !loadingImagePreview && !loadingPDFPreview
                && imagePreview == nil && pdfPreview == nil && attachmentDropPreview == nil {
                await enqueueTaskUpdate(text, conversationID: conversationID)
            }
            return
        }
        guard !text.isEmpty, !operationBusy, !loadingDroppedAttachments, !loadingImagePreview, !loadingPDFPreview,
              imagePreview == nil, pdfPreview == nil, attachmentDropPreview == nil,
              !conversation.archived else { return }
        guard !historyPersistence.blocksSubmission, !store.writeBlocked else {
            if selectedID == conversationID && composer.isEmpty { setComposer(text, preservingContinuation: true) }
            execution(for: conversationID).status = "Сначала восстановите сохранение истории"
            return
        }
        guard beginPanelConversation(conversationID, text: text) else { return }
        let state = execution(for: conversationID)
        state.running = true
        do {
            try await prepareConversationAccount(state)
            let description = try await state.client.request("describe", ["text": .string(text)])
            guard !description["blocked"].flag else { throw NativeError.message(description["notice"].text) }
            if description["operator"].flag && executions.values.contains(where: { $0 !== state && $0.running }) {
                throw NativeError.message(L10n.text("Дождитесь завершения задач перед выполнением команды ядра."))
            }
            if description["requires_confirmation"].flag {
                let summary = description["steps"].items.map { L10n.format("\($0["command"].text)\nИзменяет: \($0["mutates"].text) · риск: \($0["risk"].text)") }.joined(separator: "\n\n")
                pendingAction = PendingOperatorAction(text: text, conversationID: conversationID, summary: summary)
                state.running = false
                return
            }
            if !description["operator"].flag { try await ensureAgentAccess(for: state) }
            await perform(text, execution: state, confirmed: false, operatorInput: description["operator"].flag)
        } catch {
            state.running = false
            if selectedID == conversationID { report(error) }
            else { append(ChatMessage(role: "report", text: error.localizedDescription, isError: true), to: conversationID); persist() }
        }
    }

    func confirmPending() async {
        guard !globalBusy, let action = pendingAction else { return }
        guard !historyPersistence.blocksSubmission, !store.writeBlocked else {
            status = "Сначала восстановите сохранение истории"
            return
        }
        pendingAction = nil
        let state = execution(for: action.conversationID)
        state.running = true
        await perform(action.text, execution: state, confirmed: true, operatorInput: true)
    }

    func perform(_ text: String, execution state: ConversationExecution, confirmed: Bool, operatorInput: Bool, useDraft: Bool = true) async {
        let conversationID = state.conversationID
        guard let index = conversations.firstIndex(where: { $0.id == conversationID }) else { state.running = false; return }
        if conversations[index].provider == "claude", claudeAuthenticating {
            state.running = false
            report(NativeError.message(L10n.pick("Завершите вход в Claude перед запуском задачи.", "Finish signing in to Claude before starting a task.")))
            return
        }
        // Core/operator mutations block other work while retaining their original session.
        if operatorInput { operationBusy = true }
        defer { if operatorInput { operationBusy = false } }
        let providerClient = state.client
        let usePersona = !operatorInput && personaEnabled && ["codex", "ollama"].contains(conversations[index].provider)
        invalidateSessionSpinePilot()
        let conversation = conversations[index]
        let history = conversation.history
        let files = operatorInput || !useDraft ? [] : conversation.pendingFiles
        let images = operatorInput || !useDraft ? [] : conversation.pendingImages
        let pdfs = operatorInput || !useDraft ? [] : conversation.pendingPDFs
        let criteria = operatorInput || !useDraft ? [] : conversation.pendingCriteria
        let projectNotes = operatorInput || !useDraft ? [] : projectNoteSelections[conversationID] ?? []
        let skillTask = operatorInput || !useDraft ? nil : preparedSkillTasks[conversationID]
        let automaticSkills = !operatorInput && conversation.provider == "codex" && conversation.autoSkillsEnabled && skillTask == nil
        let automaticRecall = !operatorInput && ["codex", "claude"].contains(conversation.provider) && conversation.autoProjectRecallEnabled && projectNotes.isEmpty
        let suggestMemory = !operatorInput && conversation.provider == "codex" && conversation.memorySuggestionsEnabled && conversation.workspacePath != nil
        let grant = !operatorInput && cloudConsent && ["codex", "claude"].contains(conversation.provider)
            && state.client.connected && agentGrants[conversationID]?.workspace == conversation.workspacePath
            ? agentGrants[conversationID] : nil
        let reviewedRecall = (selectedID == conversationID ? contextPreview : nil).flatMap { try? NativeProjectRecallReport($0.manifest["knowledge_context"]["project_recall"]) }
        let expectedProjectSnapshot = automaticRecall && reviewedRecall?.matches(conversation: conversationID, text: text,
            workspace: conversation.workspacePath, mode: grant == nil ? "chat" : "full_access") == true
            ? reviewedRecall?.value["source_snapshot_hash"] : nil
        let continuation = operatorInput || !useDraft ? nil : conversation.draftContinuation
        let userMessage = ChatMessage(role: "user", text: text, operatorInput: operatorInput, fileContext: files, imageContext: images, pdfContext: pdfs)
        conversations[index].messages.append(userMessage)
        if !operatorInput && useDraft {
            conversations[index].pendingFiles = []; conversations[index].pendingImages = []; conversations[index].pendingPDFs = []
        }
        if conversations[index].title == "Новый диалог" {
            conversations[index].title = String(AppModel.delegatedTaskBody(text).split(whereSeparator: \.isWhitespace).joined(separator: " ").prefix(54))
        }
        conversations[index].updatedAt = Date()
        // The editor stays live while the initial request is being prepared.
        // Clear only the submitted text, never a newer draft typed meanwhile.
        if useDraft && selectedID == conversationID {
            if composer.trimmingCharacters(in: .whitespacesAndNewlines) == text { setComposer("") }
            section = .chat
        } else if useDraft && conversations[index].draft.trimmingCharacters(in: .whitespacesAndNewlines) == text {
            conversations[index].draft = ""; conversations[index].draftContinuation = nil
        }
        state.workspaceQuestions = conversation.workspaceQuestions.filter { $0.answer == nil }
        state.workspaceCreatedTasks = []
        state.workspaceToolCalls = []; state.workspaceToolsAllowed = !operatorInput && (grant != nil || conversation.provider == "api" && apiWorkspaceToolsAllowed(conversation))
        state.workspaceToolBinding = workspaceToolBinding(conversation)
        state.stream = ""; state.agentItems = []; state.agentReceipt = .null; state.workLog = .null; state.autoSkillsReport = nil
        state.startedAt = Date()
        state.status = grant == nil ? "Proto-Mind думает" : "Агент подключается · полный доступ + интернет"
        guard persist() else {
            // The provider has not been called. Restore the draft and attachments;
            // a local save failure must not create a failed or duplicate turn.
            conversations[index] = conversation
            if useDraft && selectedID == conversationID {
                restoreComposer()
                if composer.isEmpty { setComposer(text, preservingContinuation: true) }
            }
            state.running = false; state.startedAt = nil
            return
        }
        state.sourceMessageID = !operatorInput && conversation.provider == "codex" ? userMessage.id : nil
        state.updateTarget = nil; state.updatesStopped = false
        do {
            let requestedRunID = operatorInput ? nil : UUID()
            var params: [String: JSONValue] = [
                "text": .string(text), "conversation_id": .string(conversationID.uuidString),
                "provider": .string(conversation.provider), "model": .string(conversation.model),
                "reasoning_effort": .string(["codex", "claude"].contains(conversation.provider) ? conversation.reasoningEffort : ""),
                "cloud_consent": .bool(cloudConsent), "history": .array(history),
                "persona_enabled": .bool(usePersona),
            ]
            if conversation.provider == "api" && !operatorInput {
                params["api_connection"] = try apiConnections.parameters(for: conversation)
                if apiWorkspaceToolsAllowed(conversation) {
                    params["api_workspace_tools"] = .bool(true)
                    params["workspace_tools_version"] = .number(1)
                }
            }
            if confirmed { params["confirmed_text"] = .string(text) }
            if let requestedRunID {
                params["run_id"] = .string(requestedRunID.uuidString)
                params["criteria"] = .array(criteria.map(JSONValue.string))
                params["images"] = .array(images)
                params["pdfs"] = .array(pdfs)
                params["project_memory"] = .array(projectNotes.map(\.selection))
                params["auto_skills"] = .bool(automaticSkills)
                params["local_skill_selection"] = .bool(true)
                params["auto_project_recall"] = .bool(automaticRecall)
                params["project_recall_algorithm"] = .string("local_content_terms_v3")
                params["agent_contract_version"] = .number(grant == nil ? 2 : 3)
                params["memory_suggestions"] = .bool(suggestMemory)
                if let expectedProjectSnapshot, !expectedProjectSnapshot.isNull { params["expected_project_snapshot"] = expectedProjectSnapshot }
                if let skillTask { params["skill_task"] = skillTask.selection }
                if let root = conversation.workspacePath { params["workspace_root"] = .string(root) }
                if let continuation { params["continuation"] = continuation }
            }
            if let grant {
                params["workspace_tools_version"] = .number(1)
                params["access_mode"] = .string("full_access")
                params["access_token"] = .string(grant.token)
                if let workspace = grant.workspace { params["workspace_root"] = .string(workspace) }
            }
            if !files.isEmpty, let root = conversation.workspacePath {
                params["workspace_root"] = .string(root)
                params["files"] = .array(files)
            }
            let result = try await providerClient.request("process", params, onID: { state.requestID = $0 })
            if usePersona {
                state.personaReceipt = try NativePersonaTurnReceipt(result["persona_activation"])
            } else if !result["persona_activation"].isNull {
                throw NativeError.message(L10n.text("Ядро вернуло Persona receipt без активированного opt-in."))
            }
            let evidence = result["cognitive_turn"]
            try checkKnowledgeMetadata(result["knowledge_context"])
            let returnedNotes = result["knowledge_context"]["project_memory"].items
            if automaticRecall {
                let report = try NativeProjectRecallReport(result["knowledge_context"]["project_recall"], notes: returnedNotes, run: result["work_session"])
                guard report.matches(conversation: conversationID, text: text, workspace: conversation.workspacePath,
                                     mode: grant == nil ? "chat" : "full_access"),
                      expectedProjectSnapshot == nil || expectedProjectSnapshot?.isNull == true || report.value["source_snapshot_hash"] == expectedProjectSnapshot,
                      result["knowledge_context"] == result["work_session"]["context_manifest"]["knowledge_context"] else { throw NativeProjectRecallReport.error() }
            } else {
                guard result["knowledge_context"]["project_recall"].isNull,
                      returnedNotes.count == projectNotes.count, zip(returnedNotes, projectNotes).allSatisfy({ row, note in
                    row["id"] == note.raw["id"] && row["record_hash"] == note.raw["record_hash"]
                }) else { throw projectMemoryError() }
            }
            guard result["knowledge_context"]["skill_task"] == (skillTask?.reference ?? .null) else { throw skillTaskError() }
            if automaticSkills {
                let report = try NativeAutoSkillsReport(result["auto_skills"], run: result["work_session"])
                guard ["selected", "no_match", "empty", "unavailable"].contains(report.state),
                      report.matches(conversation: conversationID, text: text, workspace: conversation.workspacePath,
                                     mode: grant == nil ? "chat" : "full_access") else { throw NativeAutoSkillsReport.error() }
                state.autoSkillsReport = report
            } else if !result["auto_skills"].isNull { throw NativeAutoSkillsReport.error() }
            let raw = result["text"].text
            let body = result["exit_requested"].flag ? L10n.text("Сессия ядра завершена. История диалога сохранена локально.") : evidence.isNull ? raw : evidence["response"].text
            var notices = result["notices"].items.map(\.text)
            var suggestions: JSONValue?
            if !result["memory_suggestions"].isNull {
                do {
                    guard suggestMemory else { throw memorySuggestionError() }
                    let report = try MemorySuggestionsReport(result["memory_suggestions"], text: text, run: result["work_session"])
                    guard UUID(uuidString: report.source["conversation_id"].text) == conversationID,
                          ProjectMemoryScope(conversationID: conversationID, workspace: conversation.workspacePath ?? "").matches(report.source["workspace"]) else { throw memorySuggestionError() }
                    if report.value["state"] == .string("unavailable") { notices.append(L10n.text("Предложения памяти недоступны: проверьте папку, настройки и заметки. Ответ сохранён; автоматической записи памяти не было.")) }
                    if !report.items.isEmpty { suggestions = report.value }
                } catch { notices.append(L10n.text("Предложения памяти не прошли проверку источника. Ответ сохранён без карточек; ничего не записано в заметки проекта.")) }
            }
            if !result["envelope_warning"].text.isEmpty { notices.append(result["envelope_warning"].text) }
            try NativeImageAttachment.validate(result["image_context"].items)
            guard images.isEmpty || result["image_context"] == .array(images) else {
                throw NativeError.message(L10n.text("Результат не подтвердил выбранные изображения. Запрос не повторялся; проверьте журнал работы."))
            }
            try NativePDFAttachment.validate(result["pdf_context"].items)
            guard pdfs.isEmpty || result["pdf_context"] == .array(pdfs) else {
                throw NativeError.message(L10n.text("Результат не подтвердил выбранные страницы PDF. Запрос не повторялся; проверьте журнал работы."))
            }
            var turnReference: JSONValue?
            if !operatorInput && ["codex", "ollama", "api", "claude"].contains(conversation.provider) {
                let run = try NativeWorkSession(result["work_session"])
                guard run.id == requestedRunID?.uuidString.lowercased(), let receipt = run.turnReceipt else {
                    throw NativeError.message(L10n.text("Завершённый ответ не содержит проверяемую квитанцию связи с запуском. Запрос не повторялся."))
                }
                turnReference = try NativeTurnReference.make(
                    receipt: receipt.value, source: userMessage, conversation: conversationID, response: raw
                )
            } else if !result["work_session"]["turn_receipt"].isNull {
                throw NativeError.message(L10n.text("Квитанция связи появилась на неподдерживаемом маршруте. Ответ не сохранён и запрос не повторялся."))
            }
            let message = ChatMessage(role: result["operator"].flag ? "report" : "assistant", text: body,
                                      raw: raw, evidence: evidence, notices: notices,
                                      fileContext: result["workspace_context"].items,
                                      imageContext: result["image_context"].items,
                                      pdfContext: result["pdf_context"].items,
                                      agentRun: result["agent_run"].isNull ? nil : result["agent_run"],
                                      workLog: result["work_log"].isNull ? nil : result["work_log"],
                                      autoSkills: state.autoSkillsReport?.value,
                                      knowledgeContext: result["knowledge_context"].isNull ? nil : result["knowledge_context"],
                                      memorySuggestions: suggestions, memorySuggestionSourceID: suggestions == nil ? nil : userMessage.id,
                                      turnReference: turnReference)
            append(message, to: conversationID)
            if !operatorInput, useDraft, let current = conversations.firstIndex(where: { $0.id == conversationID }) {
                conversations[current].pendingCriteria = []
                projectNoteSelections[conversationID] = nil
                preparedSkillTasks[conversationID] = nil
            }
            if selectedID == conversationID {
                inspectedMessageID = message.id
                if !result["provider_thread"].isNull { codexThreadStatus = .null }
            }
            state.status = "Готов"
        } catch {
            if let current = conversations.firstIndex(where: { $0.id == conversationID }),
               let failed = conversations[current].messages.firstIndex(where: { $0.id == userMessage.id }) {
                conversations[current].messages[failed].isError = true
            }
            let caution = grant == nil && !apiWorkspaceToolsAllowed(conversation) ? "" : L10n.text("\nДействия могли уже изменить файлы. Проверьте журнал и результат перед повтором; автоматического отката нет.")
            append(ChatMessage(role: "report", text: error.localizedDescription + caution, isError: true,
                               agentRun: state.agentReceipt.isNull ? nil : state.agentReceipt,
                               workLog: state.workLog.isNull ? nil : state.workLog, autoSkills: state.autoSkillsReport?.value), to: conversationID)
            if grant != nil { discardAgentGrants(for: conversationID, forgetSelection: false) }
            if useDraft, let current = conversations.firstIndex(where: { $0.id == conversationID }),
               conversations[current].pendingFiles.isEmpty, conversations[current].pendingImages.isEmpty,
               conversations[current].pendingPDFs.isEmpty,
               conversations[current].draft.isEmpty || conversations[current].draft == conversation.draft {
                // Restore the failed request's selection without adding its files
                // to a different message the user has started drafting meanwhile.
                conversations[current].pendingFiles = files
                conversations[current].pendingImages = images
                conversations[current].pendingPDFs = pdfs
            }
            if useDraft, let current = conversations.firstIndex(where: { $0.id == conversationID }), conversations[current].draft.isEmpty {
                conversations[current].draftContinuation = continuation
                if selectedID == conversationID { setComposer(text, preservingContinuation: true) }
                else { conversations[current].draft = text }
            }
            state.status = "Запрос не завершён"
        }
        closeTaskUpdateQueue(execution: state)
        stopWorkspaceTools(for: state)
        state.clearTurn()
        let saved = persist()
        telegram.taskEnded(app: self, id: conversationID, source: userMessage.id, saved: saved)
        if selectedID == conversationID {
            await refreshCodexThreadStatus()
            if selectedID == conversationID { await refresh() }
        }
    }

    func stop() async {
        guard let id = selectedID else { return }
        await stop(conversationID: id)
    }

    func stop(conversationID: UUID) async {
        guard let state = executions[conversationID], state.running, let request = state.requestID else { return }
        stopWorkspaceTools(for: state)
        closeTaskUpdateQueue(execution: state); persist()
        do { state.status = try await state.client.request("cancel", ["request_id": .string(request)])["notice"].text }
        catch { if selectedID == state.conversationID { report(error) } }
    }

}
