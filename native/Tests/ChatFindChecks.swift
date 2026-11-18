import AppKit
import SwiftUI

extension NativeChecks {
    /// ⌘F in the open chat and the keyboard shortcuts page in Settings.
    @MainActor static func chatFindContracts(root: URL) throws {
        let suite = "pm-chat-find-" + UUID().uuidString
        let defaults = UserDefaults(suiteName: suite)!
        let app = AppModel(configuration: LaunchConfiguration(projectRoot: root, python: root, stateDirectory: root.appendingPathComponent("chat-find-state")),
                           uiDefaults: defaults)
        defer { app.shutdown(); defaults.removePersistentDomain(forName: suite) }
        var chat = Conversation(); chat.title = "Поиск"
        chat.messages = [ChatMessage(role: "user", text: "Где лежит конфиг?"),
                         ChatMessage(role: "assistant", text: "**Конфиг** лежит в `~/config`."),
                         ChatMessage(role: "user", text: "Спасибо"),
                         ChatMessage(role: "assistant", text: "Ещё одно про конфиг: его читает мост.")]
        app.conversations.append(chat)
        app.select(chat.id)
        let ids = chat.messages.map(\.id)
        let find = app.chatFind

        app.section = .commands
        app.openChatFind()
        try check(find.conversationID == chat.id && app.section == .chat, "⌘F opens the find bar over the open chat, showing the chat first")
        find.query = "КОНФИГ"
        find.search(jump: true)
        try check(find.matches == [ids[3], ids[1], ids[0]] && find.current == 0 && app.transcriptDestination?.messageID == ids[3],
                  "Find matches messages regardless of case, newest first, and scrolls to the newest")
        find.next()
        try check(find.current == 1 && app.transcriptDestination?.messageID == ids[1], "Next goes to an earlier match")
        find.previous(); find.previous()
        try check(find.current == 2 && app.transcriptDestination?.messageID == ids[0], "Stepping past the newest match wraps around to the oldest")
        find.query = "еще"
        find.search(jump: true)
        try check(find.matches == [ids[3]], "Find ignores diacritics: «еще» finds «Ещё»")

        find.query = "конфиг"
        find.search(jump: true)
        find.next()
        if let index = app.conversations.firstIndex(where: { $0.id == chat.id }) {
            app.conversations[index].messages.append(ChatMessage(role: "user", text: "И ещё конфиг"))
        }
        find.search(jump: false)
        try check(find.matches.count == 4 && find.currentMatch == ids[1], "A new message joins the matches without moving away from the current one")

        let marked = ChatFindModel.highlighted(AttributedString("Конфиг и конфиг"), "конфиг")
        try check(marked.runs.filter { $0.backgroundColor != nil }.count == 2 && String(marked.characters) == "Конфиг и конфиг",
                  "Every occurrence of the query is highlighted and the text stays the same")
        let markdown = MarkdownBlock.inline("**Конфиг** в `~/config`", highlight: "конфиг")
        try check(markdown.runs.contains { $0.backgroundColor != nil } && String(markdown.characters) == "Конфиг в ~/config",
                  "Highlighting keeps Markdown formatting")
        try check(MessageMarkdownView(text: "a", copy: { _ in }, highlight: "a") != MessageMarkdownView(text: "a", copy: { _ in }),
                  "A message redraws when its highlight changes")

        find.close()
        try check(!find.visible && find.matches.isEmpty && find.query == "конфиг", "Done closes the bar and keeps the query for the next ⌘F")
        app.openChatFind()
        try check(find.matches.count == 4 && app.transcriptDestination?.messageID == find.matches.first, "⌘F again finds the kept query at once")
        find.close()

        var side = Conversation()
        side.messages = [ChatMessage(role: "user", text: "side match"), ChatMessage(role: "assistant", text: "another side match")]
        app.conversations.append(side)
        let panel = app.workspacePanels.upper
        panel.open(.conversation(side.id))
        app.conversationRouting.activate(panel)
        let original = app.transcriptDestination
        app.openChatFind()
        panel.chatFind.query = "side"; panel.chatFind.search(jump: true); app.activeChatFind?.next()
        try check(panel.chatFind.conversationID == side.id && panel.transcriptDestination?.messageID == side.messages.first?.id
                    && app.transcriptDestination == original && !find.visible && app.selectedID == chat.id,
                  "Find and next scroll only the active panel's chat, leaving the main editor and destination alone")
        panel.open(.conversation(chat.id))
        app.openChatFind()
        panel.chatFind.query = "конфиг"; panel.chatFind.search(jump: true); panel.chatFind.previous()
        try check(panel.chatFind.currentMatch == ids[0] && app.transcriptDestination == original && !find.visible,
                  "The same chat shown twice has independent match navigation")
        panel.showFiles()
        app.openChatFind()
        try check(app.activeChatFind == nil && !panel.chatFind.visible && !find.visible && app.transcriptDestination == original,
                  "Find on a non-chat panel never redirects the shortcut into the other window")

        panel.visible = false
        try check(app.activeChatFind === find, "Hiding the last active panel routes find shortcuts back to the main conversation")

        try check(NativeSettingsSection.allCases.contains(.keyboard) && NativeSettingsSection.keyboard.symbol == "keyboard",
                  "Settings has a page with the keyboard shortcuts")
    }
}
