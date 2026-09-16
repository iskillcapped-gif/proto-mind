import AppKit
import SwiftUI

extension NativeChecks {
    @MainActor
    static func conversationSurfaces(fixture: URL, python: URL, root: URL) async throws {
        let app = AppModel(configuration: .init(projectRoot: fixture, python: python,
            stateDirectory: root.appendingPathComponent("conversation-surfaces")))
        defer { app.shutdown() }
        let main = app.selectedID!
        app.setComposer("Main draft stays here")
        var second = Conversation(); second.title = "Side work"; second.draft = "Side draft"
        second.workspacePath = fixture.path
        second.messages = [ChatMessage(role: "assistant", text: "Saved side response")]
        var third = Conversation(); third.title = "Another task"; third.draft = "Third draft"
        app.conversations += [second, third]
        let panel = app.workspacePanels.upper
        let browser = NativeBrowserTab()
        let browserID = panel.open(.browser(browser))!
        app.conversationRouting.activate(panel)
        app.openSidebarConversation(second.id, messageID: second.messages[0].id)
        try check(app.selectedID == main && app.composer == "Main draft stays here" && panel.tabs.count == 2,
                  "Sidebar opens the chosen conversation beside an existing browser without replacing the main editor")
        try check(panel.tabs.contains { $0.id == browserID } && panel.transcriptDestination?.messageID == second.messages[0].id,
                  "Sidebar preserves the browser tab and targets the exact searched or unread response")
        let sideTab = panel.selectedID
        app.openSidebarConversation(second.id)
        try check(panel.tabs.count == 2 && panel.selectedID == sideTab, "Repeated sidebar selection reuses the existing conversation tab")
        app.openSidebarConversation(third.id)
        try check(panel.tabs.count == 3 && app.conversations.first { $0.id == second.id }?.draft == "Side draft",
                  "Choosing another task retains the former side draft and open tabs")
        let side = ConversationComposerContext(app: app, id: second.id)
        app.execution(for: main).running = true
        try check(side.canSend && !side.busy && !side.showsStop && side.canEditAttachments,
                  "An idle side composer remains usable while the main task runs")
        try app.setPendingCriteria(["Side criterion"], conversationID: second.id)
        side.set(\.autoSkillsEnabled, false)
        try check(app.conversations.first { $0.id == second.id }?.pendingCriteria == ["Side criterion"]
                  && app.selected?.pendingCriteria.isEmpty == true && app.selected?.autoSkillsEnabled == true,
                  "Side request settings change only their captured conversation during a different active task")
        let params = app.contextRequestParameters(for: second.id)
        try check(params?["conversation_id"]?.text == second.id.uuidString && params?["text"]?.text == "Side draft"
                  && params?["workspace_root"]?.text == fixture.path && params?["criteria"]?.items == [.string("Side criterion")],
                  "Side context preview uses its own text, workspace, criteria and history")
        app.execution(for: main).running = false
        app.configureConversation(second.id, provider: "codex")
        app.cloudConsent = true
        let source = WorkspacePresentations(); panel.presentations = source
        app.requestAgentAccess(conversationID: second.id, in: source)
        try check(app.pendingAgentAccess?.conversationID == second.id && !app.fullAccessEnabled && !side.fullAccess,
                  "A side Full Mac request is bound to that chat and cannot silently grant either conversation access")
        app.pendingAgentAccess = nil
        app.configureConversation(second.id, provider: "mock")
        await app.openProjectMemory(conversationID: second.id, in: source)
        try check(app.projectMemory?.scope.conversationID == second.id && app.projectMemory?.current == true
                  && app.selectedID == main && app.composer == "Main draft stays here",
                  "Side project memory loads against the captured scope without switching the main chat")
        app.projectMemory?.close()
        for width: CGFloat in [300, 480, 840] {
            let host = NSHostingController(rootView: ComposerView(model: app, conversationID: second.id, panel: panel))
            let size = host.sizeThatFits(in: CGSize(width: width, height: 600))
            try check(size.width <= width + 1 && size.height < 400, "Shared side composer fits \(Int(width)) points without overflowing")
        }
        panel.visible = false
        app.openSidebarConversation(third.id)
        try check(app.selectedID == third.id && app.composer == "Third draft", "A hidden target falls back to the main chat")
        panel.visible = true; panel.selectedID = browserID
        app.conversationRouting.activate(panel)
        while panel.tabs.count < WorkspacePanelModel.maximumTabs {
            panel.open(.answer(.init(conversationID: main, messageID: UUID(), title: "Kept tab", text: "Fixture")))
        }
        panel.selectedID = browserID
        let savedTabs = panel.tabs.map(\.id)
        app.openSidebarConversation(main)
        try check(panel.tabs.map(\.id) == savedTabs && panel.selectedID == browserID && panel.error != nil && app.selectedID == third.id,
                  "A full side window reports capacity without losing its browser or redirecting the selected task")
        app.conversationRouting.activate(nil)
        app.openSidebarConversation(second.id)
        try check(app.selectedID == second.id, "Intentional main-window selection restores sidebar navigation to the main editor")
    }
}
