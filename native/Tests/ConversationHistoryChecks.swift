import AppKit
import Foundation
import SwiftUI

extension NativeChecks {
    @MainActor
    static func conversationHistoryContracts(root: URL) async throws {
        var archived = Conversation()
        archived.title = "План поездки"; archived.archived = true; archived.workspacePath = "/tmp/Маршрут"
        archived.updatedAt = Date(timeIntervalSince1970: 100)
        archived.messages = (0..<240).map { ChatMessage(role: $0.isMultiple(of: 2) ? "user" : "assistant", text: "Сообщение \($0)") }
        archived.messages[2].text = String(repeating: "До встречи. ", count: 80) + "Маяк на берегу 🌊" + String(repeating: " После встречи.", count: 80)
        archived.messages[27].text = "МАЯК нашли у старой пристани"
        archived.messages[0].raw = "PRIVATE_RAW_SENTINEL"
        archived.messages[0].evidence = .object(["source": .string("PRIVATE_EVIDENCE_SENTINEL")])
        var active = Conversation(); active.title = "Сегодня"; active.draft = "Напомни про билет"
        active.updatedAt = Date(timeIntervalSince1970: 200)
        var empty = Conversation(); empty.updatedAt = Date(timeIntervalSince1970: 50)
        let chats = [empty, archived, active]
        let all = await ConversationHistorySearch.find(in: chats, query: "", scope: .all)
        try check(all.map(\.id) == [active.id, archived.id, empty.id], "History includes archive and orders every dialog by activity")
        let matches = await ConversationHistorySearch.find(in: chats, query: "  мАяК\n", scope: .all)
        try check(matches.count == 1 && matches[0].matches == [archived.messages[27].id, archived.messages[2].id],
                  "Search finds every old message beyond the latest transcript and model-history windows")
        let excerpt = ConversationHistorySearch.excerpt(archived.messages[2].text, query: "маяк")
        try check(excerpt.contains("Маяк на берегу 🌊") && excerpt.count <= 192 && excerpt.hasPrefix("…") && excerpt.hasSuffix("…"),
                  "Search snippets show bounded readable text around a distant Unicode match")
        let activeOnly = await ConversationHistorySearch.find(in: chats, query: "маяк", scope: .active)
        let archiveOnly = await ConversationHistorySearch.find(in: chats, query: "маяк", scope: .archived)
        try check(activeOnly.isEmpty && archiveOnly.map(\.id) == [archived.id], "History archive filters are explicit and do not change stored archive state")
        let folder = await ConversationHistorySearch.find(in: chats, query: "маршрут", scope: .all)
        let title = await ConversationHistorySearch.find(in: chats, query: "поездки", scope: .all)
        let draft = await ConversationHistorySearch.find(in: chats, query: "БИЛЕТ", scope: .all)
        try check(folder.map(\.id) == [archived.id] && title.map(\.id) == [archived.id] && draft.map(\.id) == [active.id]
                  && draft.first?.snippet == active.draft, "History searches titles, project paths and unsent drafts")
        let raw = await ConversationHistorySearch.find(in: chats, query: "PRIVATE_", scope: .all)
        try check(raw.isEmpty, "History search reads displayed messages, never hidden raw evidence or provider prompts")
        active.messages = [ChatMessage(role: "user", text: "Первый запрос"), ChatMessage(role: "assistant", text: "Старый ответ"),
                           ChatMessage(role: "user", text: "Новый запрос")]
        let unanswered = await ConversationHistorySearch.find(in: [active], query: "", scope: .all)
        try check(unanswered[0].lastRequest?.text == "Новый запрос" && unanswered[0].lastReply == nil,
                  "An old answer is not presented as the result of a later unanswered request")
        active.messages.append(ChatMessage(role: "report", text: "Сбой", isError: true))
        let failed = await ConversationHistorySearch.find(in: [active], query: "", scope: .all)
        try check(failed[0].lastReply?.isError == true && failed[0].lastReply?.text == "Сбой",
                  "The latest error remains visible instead of being hidden by an earlier successful reply")
        for target in [0, 2, 4999, 9999] {
            let range = TranscriptRenderingPolicy.focusedRange(totalCount: 10000, targetIndex: target)
            try check(range?.contains(target) == true && range?.count == 80,
                      "Jump to message \(target) mounts only an 80-message neighbourhood")
        }
        try check(TranscriptRenderingPolicy.focusedRange(totalCount: 0, targetIndex: 0) == nil
                  && TranscriptRenderingPolicy.focusedRange(totalCount: 20, targetIndex: -1) == nil
                  && TranscriptRenderingPolicy.focusedRange(totalCount: 20, targetIndex: 20) == nil
                  && TranscriptRenderingPolicy.focusedRange(totalCount: 20, targetIndex: 19) == 0..<20,
                  "Transcript destinations reject missing indices and preserve short conversations")
        let state = root.appendingPathComponent("history-browser-local")
        try ChatStore(directory: state).save(ChatArchive(conversations: chats, selectedID: active.id))
        let app = AppModel(configuration: LaunchConfiguration(projectRoot: root, python: root.appendingPathComponent("unused"), stateDirectory: state))
        let before = try fileBytes(state)
        app.openConversationHistory()
        let size = NSHostingController(rootView: ConversationHistoryView(model: app)).sizeThatFits(in: CGSize(width: 1100, height: 850))
        try check(app.showConversationHistory && size.width <= 900 && size.height <= 690 && fileBytes(state) == before && !app.client.connected,
                  "Opening and laying out history is local and read-only")
        app.busy = true
        app.returnToConversation(archived.id, messageID: archived.messages[2].id)
        try check(app.selectedID == active.id && app.showConversationHistory && fileBytes(state) == before,
                  "History navigation cannot switch an actively running conversation")
        app.busy = false
        app.returnToConversation(archived.id, messageID: UUID())
        try check(app.selectedID == active.id && app.transcriptDestination == nil && fileBytes(state) == before,
                  "An absent message never redirects to a neighbouring or different conversation")
    }

    @MainActor
    static func conversationHistoryIntegration(fixture: URL, python: URL, state sourceState: URL) async throws {
        let state = sourceState.deletingLastPathComponent().appendingPathComponent("conversation-history-state")
        try FileManager.default.copyItem(at: sourceState, to: state)
        let store = ChatStore(directory: state)
        let initial = try store.load()
        guard let linked = initial.conversations.first, let answer = linked.messages.last,
              let reference = answer.turnReference else { throw NativeError.message("Missing continuity fixture") }
        var current = Conversation(); current.provider = "mock"; current.title = "Текущая работа"
        current.draft = "Не потерять этот черновик"; current.pendingCriteria = ["Сохранить мою цель"]
        current.workspacePath = fixture.path
        try store.save(ChatArchive(conversations: [current, linked], selectedID: current.id))
        let app = AppModel(configuration: LaunchConfiguration(projectRoot: fixture, python: python, stateDirectory: state))
        defer { app.shutdown() }
        await app.start()
        let journal = state.appendingPathComponent("work_sessions")
        let journalBefore = try fileBytes(journal), projectBefore = try fileBytes(fixture), before = try fileBytes(state)
        app.openConversationHistory()
        let found = await ConversationHistorySearch.find(in: app.conversations, query: linked.messages[0].text, scope: .all)
        try check(found.map(\.id) == [linked.id] && found[0].continuationMessage(matching: linked.messages[0].id)?.id == answer.id,
                  "Finding the earlier question resolves its exact linked answer for continuation")
        try check(fileBytes(state) == before && !app.cloudConsent && !app.fullAccessEnabled,
                  "Opening and searching complete saved work invokes no provider or state writer")
        app.returnToConversation(linked.id, messageID: answer.id)
        try check(app.selectedID == linked.id && app.transcriptDestination?.messageID == answer.id && !app.showConversationHistory
                  && app.conversations.first { $0.id == current.id } == current,
                  "Opening a search result targets its exact message and preserves the other dialog's draft and criteria")
        let firstDestination = app.transcriptDestination
        app.returnToConversation(linked.id, messageID: answer.id)
        try check(app.transcriptDestination?.requestID != firstDestination?.requestID,
                  "Opening the same old message again issues a fresh scroll destination")
        app.returnToConversation(current.id)
        try check(app.composer == current.draft && app.selected?.pendingCriteria == current.pendingCriteria
                  && app.transcriptDestination?.messageID == nil,
                  "Return to latest restores the existing draft without replacing text or context")
        guard let target = app.conversations.firstIndex(where: { $0.id == linked.id }) else { throw NativeError.message("Missing target") }
        app.conversations[target].archived = true; app.persist()
        app.returnToConversation(linked.id, messageID: answer.id)
        try check(app.selected?.archived == true && app.showArchived, "Reading an archived result keeps it archived")
        app.returnToConversation(current.id); app.openConversationHistory()
        let archivedBytes = try fileBytes(state)
        await app.prepareHistoryContinuation(messageID: answer.id, conversationID: linked.id)
        try check(app.selectedID == current.id && app.showConversationHistory && fileBytes(state) == archivedBytes,
                  "Continuation cannot silently restore an archived conversation")
        app.archiveConversation(linked.id, archived: false)
        app.conversations[target].draft = "Черновик прежней работы"; app.persist()
        let draftBefore = try fileBytes(state)
        await app.prepareHistoryContinuation(messageID: answer.id, conversationID: linked.id)
        try check(app.workSessionsActionError != nil && app.selectedID == current.id && app.composer == current.draft
                  && app.conversations[target].draft == "Черновик прежней работы" && fileBytes(state) == draftBefore,
                  "Continuation preserves both the current and target drafts and offers an actionable refusal")
        app.conversations[target].draft = ""; app.conversations[target].pendingCriteria = ["Прежние критерии"]; app.persist()
        await app.prepareHistoryContinuation(messageID: answer.id, conversationID: linked.id)
        try check(app.workSessionsActionError != nil && app.conversations[target].pendingCriteria == ["Прежние критерии"],
                  "Selected criteria are not silently mixed into a reconstructed continuation")
        app.conversations[target].pendingCriteria = []; app.persist()
        let runURL = journal.appendingPathComponent(reference["run_id"].text + ".json")
        let hiddenURL = runURL.appendingPathExtension("saved")
        try FileManager.default.moveItem(at: runURL, to: hiddenURL)
        await app.prepareHistoryContinuation(messageID: answer.id, conversationID: linked.id)
        try FileManager.default.moveItem(at: hiddenURL, to: runURL)
        try check(app.workSessionsActionError != nil && app.selectedID == current.id && app.composer == current.draft,
                  "Missing exact run evidence refuses continuation without selecting a neighbouring run")
        let pending = Task { @MainActor in await app.prepareHistoryContinuation(messageID: answer.id, conversationID: linked.id) }
        for _ in 0..<100 where !app.busy { await Task.yield() }
        try check(app.busy, "Continuation fixture reaches its asynchronous evidence read")
        app.conversations[target].workspacePath = fixture.appendingPathComponent("other-folder").path
        await pending.value
        try check(app.workSessionsActionError != nil && app.selectedID == current.id && app.conversations[target].draft.isEmpty,
                  "A folder changed during evidence loading invalidates the continuation before any draft write")
        app.conversations[target].workspacePath = linked.workspacePath; app.persist()
        let originalMessage = app.conversations[target].messages[1]
        app.conversations[target].messages[1].text = "changed displayed answer"
        app.conversations[target].messages[1].raw = "changed raw answer"
        await app.prepareHistoryContinuation(messageID: answer.id, conversationID: linked.id)
        try check(app.workSessionsActionError != nil && app.selectedID == current.id && app.conversations[target].draft.isEmpty,
                  "An altered answer cannot reuse a cached turn reference")
        app.conversations[target].messages[1] = originalMessage
        await app.prepareHistoryContinuation(messageID: answer.id, conversationID: current.id)
        try check(app.workSessionsActionError != nil && app.selectedID == current.id,
                  "A linked message from another conversation cannot prepare context for the selected dialog")
        app.error = nil
        await app.prepareHistoryContinuation(messageID: answer.id, conversationID: linked.id)
        try check(app.error == nil && app.workSessionsActionError == nil && app.selectedID == linked.id
                  && app.selected?.draftContinuation?["run_id"] == reference["run_id"] && app.composer.contains("Моя следующая цель")
                  && !app.showConversationHistory, "History prepares an exact continuation draft and opens it for manual editing")
        try check(app.conversations.first { $0.id == current.id } == current && app.selected?.messages == linked.messages
                  && !app.cloudConsent && !app.fullAccessEnabled && !app.busy && fileBytes(journal) == journalBefore
                  && fileBytes(fixture) == projectBefore, "Navigation and preparation preserve all messages, journal, project, grants and the other draft")
        let persisted = try ChatStore(directory: state).load()
        let saved = persisted.conversations.first { $0.id == linked.id }
        try check(saved?.draft == app.composer && saved?.draftContinuation == app.selected?.draftContinuation,
                  "The prepared draft and exact source link survive a history readback")
        let restartBefore = try fileBytes(state)
        let restarted = AppModel(configuration: LaunchConfiguration(projectRoot: fixture, python: python, stateDirectory: state))
        await restarted.start()
        try check(restarted.composer == app.composer && !restarted.busy && !restarted.fullAccessEnabled
                  && fileBytes(state) == restartBefore, "Restart restores the continuation draft without resuming or rewriting work")
        restarted.shutdown()
        await app.submit()
        try check(app.messages.last?.isError == false && app.workSessions.first?.value["parent_run_id"] == reference["run_id"],
                  "Only explicit Send dispatches a new Mock turn linked to the chosen historical answer")
        let afterSend = try fileBytes(journal)
        app.openConversationHistory()
        await app.prepareHistoryContinuation(messageID: answer.id, conversationID: linked.id)
        try check(app.workSessionsActionError != nil && app.composer.isEmpty && fileBytes(journal) == afterSend,
                  "History cannot replay a parent that already has a continuation")
    }
}
