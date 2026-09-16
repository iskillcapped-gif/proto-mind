import AppKit
import SwiftUI

extension NativeChecks {
    @MainActor static func chatPresentation(root: URL) throws {
        let tools: [JSONValue] = [
            .object(["id": .string("edit"), "kind": .string("fileChange"), "status": .string("inProgress")]),
            .object(["id": .string("command"), "kind": .string("commandExecution"), "status": .string("completed")])
        ]
        let entries: [JSONValue] = [
            .object(["id": .string("comment"), "kind": .string("commentary"), "text": .string("Проверяю страницу")]),
            .object(["id": .string("tool1"), "kind": .string("tool"), "tool_id": .string("edit")]),
            .object(["id": .string("tool2"), "kind": .string("tool"), "tool_id": .string("command")]),
            .object(["id": .string("comment2"), "kind": .string("commentary"), "text": .string("Проверка прошла")])
        ]
        let sections = WorkTimelinePresentation.sections(entries)
        try check(sections.count == 3 && sections[1].entries.count == 2 && sections[0].entries[0] == entries[0]
                  && sections[2].entries[0] == entries[3], "Activity groups only adjacent tools, preserving commentary and order")
        try check(WorkTimelinePresentation.sections(entries + [entries[1]])[1].id == sections[1].id,
                  "Growing activity preserves existing disclosure identity")
        try check(WorkTimelinePresentation.visibleTools(tools, live: true) == [tools[1]],
                  "Live activity cannot reveal file lists or diffs even when the tool group is expanded")
        try check(WorkTimelinePresentation.visibleTools(tools, live: false) == tools,
                  "Finished activity keeps source actions available on demand")

        func edit(_ id: String, path: String, added: JSONValue, removed: JSONValue, status: String = "completed") -> JSONValue {
            .object(["id": .string(id), "kind": .string("fileChange"), "status": .string(status), "change_count": .number(1),
                     "file_changes": .array([.object(["path": .string(path), "additions": added, "deletions": removed])])])
        }
        let one = edit("one", path: "page.html", added: .number(20), removed: .number(2))
        let two = edit("two", path: "page.html", added: .number(3), removed: .number(1))
        let three = edit("three", path: "style.css", added: .number(15), removed: .number(0))
        let failed = edit("failed", path: "failed.txt", added: .number(90), removed: .number(0), status: "failed")
        let receipt: JSONValue = .object(["status": .string("completed"), "items": .array([one, one, two, three, failed])])
        let result = CompletedFileChanges.project(receipt)
        let recent = CompletedFileChanges.project(.object(["status": .string("completed"), "items_truncated": .bool(true), "items": .array([one])]))
        try check(recent.partial && recent.additions == nil && recent.deletions == nil,
                  "A retained portion of a long task cannot claim complete file or line totals")
        try check(result.files.map(\.path) == ["page.html", "style.css"] && result.additions == 38 && result.deletions == 3,
                  "Final changes deduplicate notifications, combine repeated file edits and exclude failed edits")
        var conversation = Conversation()
        conversation.messages = [ChatMessage(role: "assistant", text: "Ответ", agentRun: receipt)]
        let store = ChatStore(directory: root.appendingPathComponent("file-change-history"))
        try store.save(ChatArchive(conversations: [conversation], selectedID: conversation.id))
        let stored = try store.load().conversations[0].messages[0].agentRun ?? .null
        try check(stored == receipt && CompletedFileChanges.project(stored).additions == 38,
                  "File counts survive dialog save and reload without depending on truncated journal previews")
        try check(CompletedFileChanges.project(receipt, live: true).files.isEmpty,
                  "Even a terminal receipt cannot display file totals while the turn remains live")
        for status in ["starting", "inProgress", "unknown", ""] {
            try check(CompletedFileChanges.project(.object(["status": .string(status), "items": .array([one])])).files.isEmpty,
                      "Nonterminal or unrecognized receipt \(status) cannot publish a final change card")
        }
        for status in ["failed", "interrupted"] {
            try check(CompletedFileChanges.project(.object(["status": .string(status), "items": .array([one, failed])])).files.count == 1,
                      "Terminal \(status) preserves known completed edits without counting failed actions")
        }
        let legacy: JSONValue = .object(["id": .string("legacy"), "kind": .string("fileChange"), "status": .string("completed"),
                                         "paths": .array([.string("page.html")]), "diff_preview": .string("+cut off")])
        let older = CompletedFileChanges.project(.object(["status": .string("completed"), "items": .array([one, legacy])]))
        try check(older.files.count == 1 && older.additions == nil && older.deletions == nil,
                  "Older or missing statistics remain unknown instead of becoming a misleading zero or partial total")
        let truncated: JSONValue = .object(["id": .string("part"), "kind": .string("fileChange"), "status": .string("completed"),
                                            "change_count": .number(9), "paths": .array([.string("one.txt")])])
        try check(CompletedFileChanges.project(.object(["status": .string("completed"), "items": .array([truncated])])).partial,
                  "Truncated historical path lists are labelled partial")

        let app = AppModel(configuration: LaunchConfiguration(projectRoot: root, python: root, stateDirectory: root.appendingPathComponent("chat-ui")))
        app.conversations[0].provider = "codex"
        app.conversations[0].model = "5.6 Sol"
        app.conversations[0].reasoningEffort = "low"
        let short = NSHostingController(rootView: ModelSelectionMenu(model: app, openSettings: {})).sizeThatFits(in: CGSize(width: 400, height: 40))
        app.conversations[0].reasoningEffort = "xhigh"
        let long = NSHostingController(rootView: ModelSelectionMenu(model: app, openSettings: {})).sizeThatFits(in: CGSize(width: 400, height: 40))
        try check(short.width + 15 < long.width && long.width <= 220,
                  "The rendered model control shrinks when a shorter effort is selected")
        for screen in [CGRect(x: 0, y: 0, width: 1440, height: 900), CGRect(x: -1440, y: 300, width: 1440, height: 900)] {
            for y: CGFloat in [50, 700] {
                let anchor = CGRect(x: screen.maxX - 70, y: screen.minY + y, width: 40, height: 32)
                let frame = ComposerPopoverPlacement.frame(anchor: anchor, screen: screen, size: CGSize(width: 320, height: 1000), trailing: true)
                try check(frame.minY > anchor.maxY && screen.contains(frame) && frame.height < 1000,
                          "Composer popup stays above the anchor and scrolls within the current screen, including offset displays")
            }
            let sidebarButton = CGRect(x: screen.minX + 30, y: screen.minY + 20, width: 185, height: 54)
            let menu = ComposerPopoverPlacement.frame(anchor: sidebarButton, screen: screen, size: CGSize(width: 290, height: 1200),
                                                       trailing: false, confinedToColumn: true)
            try check(menu.minX >= sidebarButton.minX && menu.maxX <= sidebarButton.maxX
                      && menu.minY > sidebarButton.maxY && screen.contains(menu),
                      "The sidebar popup stays inside its narrow column and scrolls above the menu button")
        }
        let message = ChatMessage(role: "assistant", text: "Ответ", notices: ["Служебное пояснение"])
        try check(message.hasResponseDetails && !ChatMessage(role: "assistant", text: "Ответ").hasResponseDetails,
                  "Moved notices remain reachable through details even without cognitive evidence")

        let response = "# **План запуска**\n\nПервый шаг 💙\n\n```swift\nprint(\"готово\")\n```\n"
        var source = ChatMessage(role: "assistant", text: response, raw: "PRIVATE RECEIPTS", notices: ["PRIVATE NOTICE"])
        let document = ResponseDocument(text: source.text, conversationTitle: "Другой заголовок")
        source.text = "A later reply must not replace the chosen export"
        let exportDirectory = root.appendingPathComponent("reply-export")
        try FileManager.default.createDirectory(at: exportDirectory, withIntermediateDirectories: true)
        let destination = exportDirectory.appendingPathComponent(document.filename)
        try "Previous file".write(to: destination, atomically: true, encoding: .utf8)
        try document.write(to: destination)
        try check(try Data(contentsOf: destination) == Data(response.utf8),
                  "Saving a captured reply preserves exact Markdown and Unicode, excludes private receipts and replaces only the chosen file")
        try check(document.title == "План запуска" && document.filename == "План запуска.md",
                  "Result tabs and suggested filenames use the visible heading without Markdown emphasis")
        let fenced = ResponseDocument(text: "```sh\n# Not a heading\n```", conversationTitle: "Настоящая задача")
        try check(fenced.title == "Настоящая задача", "Code headings cannot rename a result tab")
        for title in ["../../private/notes:plan\\draft\nnext", String(repeating: "💙", count: 100), "...", "\u{0000}"] {
            let filename = ResponseDocument(text: "Plain response", conversationTitle: title).filename
            try check(filename.utf8.count <= 163 && filename.hasSuffix(".md") && !filename.hasPrefix(".")
                      && !filename.contains("/") && !filename.contains("\\") && !filename.contains(":"),
                      "Suggested reply filename is a bounded visible component for \(title.debugDescription)")
        }
        do {
            try document.write(to: exportDirectory)
            throw NativeError.message("Saving over a directory must fail")
        } catch {
            try check((error as? CocoaError) != nil && (try Data(contentsOf: destination)) == Data(response.utf8),
                      "A failed reply export leaves the previous saved reply intact")
        }
        try check(!app.client.connected && !app.fullAccessEnabled && !FileManager.default.fileExists(atPath: root.appendingPathComponent("chat-ui").path),
                  "Chat presentation never starts providers, grants access or writes private state")
    }
}
