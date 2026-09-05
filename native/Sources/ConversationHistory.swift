import Foundation

enum ConversationHistoryScope: String, CaseIterable, Identifiable {
    case all, active, archived
    var id: String { rawValue }
    var title: String {
        switch self { case .all: return "Все"; case .active: return "Диалоги"; case .archived: return "Архив" }
    }
    func includes(_ chat: Conversation) -> Bool {
        self == .all || (self == .archived) == chat.archived
    }
}

struct ConversationHistoryResult: Identifiable {
    let conversation: Conversation
    let matches: [UUID]
    let snippet: String
    var id: UUID { conversation.id }

    var lastRequest: ChatMessage? { conversation.messages.last { $0.role == "user" } }
    var lastReply: ChatMessage? {
        let messages = conversation.messages
        let start = messages.lastIndex { $0.role == "user" }.map { $0 + 1 } ?? 0
        return messages[start...].last { $0.role != "user" }
    }

    func continuationMessage(matching id: UUID?) -> ChatMessage? {
        guard let id else { return lastReply }
        guard let index = conversation.messages.firstIndex(where: { $0.id == id }) else { return nil }
        let match = conversation.messages[index]
        if match.role == "assistant" { return match }
        if match.role == "user", conversation.messages.indices.contains(index + 1) {
            let next = conversation.messages[index + 1]
            if let raw = next.turnReference, let reference = try? NativeTurnReference(raw),
               reference.matches(source: match, assistant: next, conversation: conversation.id) { return next }
        }
        return nil
    }
}

enum ConversationHistorySearch {
    static func excerpt(_ text: String, query: String = "", limit: Int = 190) -> String {
        let value = text
        let match = query.isEmpty ? nil : value.range(of: query, options: [.caseInsensitive, .diacriticInsensitive])
        let start = match.map { value.index($0.lowerBound, offsetBy: -55, limitedBy: value.startIndex) ?? value.startIndex } ?? value.startIndex
        let end = value.index(start, offsetBy: limit, limitedBy: value.endIndex) ?? value.endIndex
        return (start > value.startIndex ? "…" : "") + value[start..<end].replacingOccurrences(of: "\n", with: " ") + (end < value.endIndex ? "…" : "")
    }

    static func find(in conversations: [Conversation], query: String, scope: ConversationHistoryScope) async -> [ConversationHistoryResult] {
        let query = query.trimmingCharacters(in: .whitespacesAndNewlines)
        func contains(_ value: String) -> Bool {
            value.range(of: query, options: [.caseInsensitive, .diacriticInsensitive]) != nil
        }
        var results: [ConversationHistoryResult] = []
        for (offset, chat) in conversations.enumerated() where scope.includes(chat) {
            if offset.isMultiple(of: 32) { await Task.yield() }
            guard !Task.isCancelled else { return [] }
            var matches: [UUID] = []
            if !query.isEmpty {
                for (index, message) in chat.messages.enumerated().reversed() {
                    if index.isMultiple(of: 128) { await Task.yield() }
                    guard !Task.isCancelled else { return [] }
                    if contains(message.searchableText) { matches.append(message.id) }
                }
                guard !matches.isEmpty || contains(chat.title) || contains(chat.workspacePath ?? "") || contains(chat.draft) else { continue }
            }
            let matched = matches.first.flatMap { id in chat.messages.first { $0.id == id } }
            let preview = matched?.searchableText ?? (!query.isEmpty && contains(chat.draft) ? chat.draft : chat.messages.last?.searchableText ?? chat.draft)
            results.append(ConversationHistoryResult(conversation: chat, matches: matches,
                                                      snippet: excerpt(preview, query: query)))
        }
        return results.sorted {
            $0.conversation.updatedAt == $1.conversation.updatedAt
                ? $0.id.uuidString < $1.id.uuidString : $0.conversation.updatedAt > $1.conversation.updatedAt
        }
    }
}

struct TranscriptDestination: Equatable {
    let requestID = UUID()
    let conversationID: UUID
    let messageID: UUID?
}

extension AppModel {
    func focusReturnedDraft() {
        guard !busy, section == .chat, selected?.archived != true,
              transcriptDestination?.messageID == nil else { return }
        composerRevision += 1
    }

    func openConversationHistory() {
        workSessionsActionError = nil
        showConversationHistory = true
    }

    func returnToConversation(_ id: UUID, messageID: UUID? = nil) {
        guard !busy, !client.turnOutstanding, let chat = conversations.first(where: { $0.id == id }),
              messageID == nil || chat.messages.contains(where: { $0.id == messageID }) else { return }
        if selectedID != id { select(id) }
        else { flushDraft(); section = .chat }
        showArchived = chat.archived
        showConversationHistory = false
        workspacePanel.expanded = false
        transcriptDestination = TranscriptDestination(conversationID: id, messageID: messageID)
        // Focus the existing draft when returning to the latest messages.
        if messageID == nil { composerRevision += 1 }
    }
}
