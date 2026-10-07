import AppKit

extension NativeChecks {
    /// Reply notifications, continuing after a usage limit, and unused new chats.
    @MainActor static func workflowConveniences(root: URL) throws {
        try check(ReplyNotifications.preview("## Итог\n\nНашёл **три** места: [ссылка](https://example.com) и `код`.") == "Итог"
                  && ReplyNotifications.preview("```swift\nlet a = 1\n```\n- Первый *пункт*") == "Первый пункт"
                  && ReplyNotifications.preview(String(repeating: "а", count: 300)).count == 160,
                  "A notification shows the reply's first line as plain text, at most 160 characters")

        let now = Date(timeIntervalSince1970: 2_000_000_000)
        func window(_ id: String, remaining: Double, resetIn hours: Double) throws -> ClaudeQuotaWindow {
            let decoder = JSONDecoder(); decoder.keyDecodingStrategy = .convertFromSnakeCase
            let json = #"{"id":"\#(id)","title":"","window_minutes":\#(id == "five_hour" ? 300 : 10080),"used_percent":\#(100 - remaining),"remaining_percent":\#(remaining),"resets_at":\#(now.timeIntervalSince1970 + hours * 3600)}"#
            return try decoder.decode(ClaudeQuotaWindow.self, from: Data(json.utf8))
        }
        let fiveHourOut = try [window("five_hour", remaining: 0, resetIn: 2), window("seven_day", remaining: 40, resetIn: 30)]
        let bothOut = try [window("five_hour", remaining: 0, resetIn: 2), window("seven_day", remaining: 0, resetIn: 30)]
        let available = try [window("five_hour", remaining: 12, resetIn: 2), window("seven_day", remaining: 40, resetIn: 30)]
        try check(AppModel.limitReset(fiveHourOut, now: now) == now.addingTimeInterval(2 * 3600)
                  && AppModel.limitReset(bothOut, now: now) == now.addingTimeInterval(30 * 3600)
                  && AppModel.limitReset(available, now: now) == nil,
                  "Continuing waits for the latest exhausted window, or not at all when the limit is open")

        let suite = "pm-workflow-" + UUID().uuidString
        let defaults = UserDefaults(suiteName: suite)!
        let app = AppModel(configuration: LaunchConfiguration(projectRoot: root, python: root, stateDirectory: root.appendingPathComponent("workflow-state")),
                           uiDefaults: defaults)
        defer { app.shutdown(); defaults.removePersistentDomain(forName: suite) }
        let start = app.conversations.count
        app.newConversation()
        let fresh = app.selectedID!
        let afterFirst = app.conversations.count
        app.newConversation(); app.newConversation()
        try check(afterFirst <= start + 1 && app.conversations.count == afterFirst && app.selectedID == fresh,
                  "⌘N on an unused new chat keeps it instead of adding more")
        app.setAutoProjectRecallEnabled(false)
        app.newConversation()
        try check(app.selectedID != fresh && app.selected?.autoProjectRecallEnabled == true,
                  "An unused chat with a changed setting is left as it is, and ⌘N opens a fresh one")
        app.select(fresh)
        app.setAutoProjectRecallEnabled(true)
        app.composer = "Есть вопрос"
        app.newConversation()
        let next = app.selectedID!
        try check(next != fresh && app.visibleConversations.contains { $0.id == fresh } && app.visibleConversations.contains { $0.id == next },
                  "A chat with a draft stays listed, and the open new chat is listed")
        app.select(fresh)
        try check(!app.visibleConversations.contains { $0.id == next } && app.conversations.contains { $0.id == next },
                  "An unused new chat leaves the list once another chat is open, and is kept")

        if let index = app.conversations.firstIndex(where: { $0.id == fresh }) {
            app.conversations[index].provider = "claude"
            app.conversations[index].messages.append(ChatMessage(role: "user", text: "Сделай задачу"))
            app.conversations[index].messages.append(ChatMessage(role: "report", text: AppModel.claudeLimitPrefixes[0] + ". После обновления…", isError: true))
        }
        let interruption = app.limitInterruption(in: fresh)
        try check(interruption != nil, "A Claude usage-limit error at the end of a chat offers to continue")
        app.limitContinuations.schedule(fresh, at: now.addingTimeInterval(365 * 86400 * 30), after: interruption!.id, app: app)
        try check(app.limitContinuations.scheduled[fresh] != nil, "Continuing after the reset is scheduled only on request")
        app.limitContinuations.cancel(fresh)
        try check(app.limitContinuations.scheduled[fresh] == nil, "A scheduled continuation can be cancelled")
        if let index = app.conversations.firstIndex(where: { $0.id == fresh }) {
            app.conversations[index].messages.append(ChatMessage(role: "user", text: "Продолжай"))
        }
        try check(app.limitInterruption(in: fresh) == nil, "Once the chat moved on, the limit error no longer offers to continue")
    }
}
