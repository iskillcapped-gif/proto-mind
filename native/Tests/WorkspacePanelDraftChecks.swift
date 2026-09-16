import AppKit

extension NativeChecks {
    @MainActor
    static func workspacePanelDrafts(fixture: URL, python: URL, root: URL) async throws {
        let state = root.appendingPathComponent("panel-draft-state")
        let configuration = LaunchConfiguration(projectRoot: fixture, python: python, stateDirectory: state)
        var rejectWrites = false
        let store = ChatStore(directory: state, beforeCommit: { _ in
            if rejectWrites { throw NativeError.message("Synthetic panel draft save failure") }
        })
        let app = AppModel(configuration: configuration, historyStore: store)
        defer { app.shutdown() }
        app.setProvider("mock")
        app.setComposer("Keep the main draft")
        app.flushDraft()
        let main = app.selectedID!
        let original = try Data(contentsOf: store.url)
        let initialIDs = app.listedConversations.map(\.id)
        let initialExecutions = Set(app.executions.keys)
        let panels = [app.workspacePanels.upper, app.workspacePanels.lower] + app.desktop.companions.surfaces.map(\.panel)
        var ids: [UUID] = []
        for panel in panels {
            app.newPanelConversation(in: panel)
            guard case .conversation(let id)? = panel.selected?.content else { throw NativeError.message("Missing provisional panel draft") }
            ids.append(id)
            let tabID = panel.selectedID
            app.newPanelConversation(in: panel)
            try check(panel.tabs.count == 1 && panel.selectedID == tabID,
                      "Repeated PM launcher clicks reuse the untouched draft in each surface")
        }
        try check(Set(ids).count == 4 && app.listedConversations.map(\.id) == initialIDs
                  && app.visibleConversations.map(\.id) == initialIDs,
                  "Four independent panel drafts do not create sidebar or history entries")
        try check(try Data(contentsOf: store.url) == original && Set(app.executions.keys) == initialExecutions
                  && app.selectedID == main && app.composer == "Keep the main draft",
                  "Opening PM tabs does not write history, allocate bridges or replace the main editor")
        app.configureConversation(ids[0], model: "draft-fixture-model")
        app.setConversationDraft(" \n ", id: ids[1])
        await app.submit(conversationID: ids[1])
        app.flushDraft()
        try check(try ChatStore(directory: state).load().conversations.map(\.id) == initialIDs
                  && Set(app.executions.keys) == initialExecutions,
                  "Model selection and an empty Send keep a launcher out of persisted history")
        app.setConversationDraft("A written but unsent panel draft", id: ids[0])
        app.flushDraft()
        try check(app.listedConversations.map(\.id) == initialIDs,
                  "Autosaving a panel draft does not insert a premature sidebar chat")
        let reopened = AppModel(configuration: configuration)
        try check(reopened.conversations.count == initialIDs.count + 1
                  && reopened.conversations.first(where: { $0.id == ids[0] })?.draft == "A written but unsent panel draft"
                  && reopened.conversations.first(where: { $0.id == ids[0] })?.model == "draft-fixture-model",
                  "Restart preserves the written draft and its model while omitting untouched launchers")
        reopened.shutdown()
        panels[0].close(panels[0].selectedID!)
        panels[1].close(panels[1].selectedID!)
        try check(app.listedConversations.contains { $0.id == ids[0] }
                  && !app.conversations.contains { $0.id == ids[1] },
                  "Closing an unsent written tab keeps its draft reachable; closing a blank tab discards only the launcher")

        app.setConversationDraft("Draft moved into the main editor", id: ids[2])
        app.select(ids[2])
        panels[2].close(panels[2].selectedID!)
        try check(app.selectedID == ids[2] && app.composer == "Draft moved into the main editor",
                  "Closing the pane cannot discard a draft currently open in the main editor")
        app.select(main)
        try check(app.listedConversations.contains { $0.id == ids[2] }
                  && app.composer == "Keep the main draft",
                  "Leaving a moved draft preserves it and restores the unrelated main draft")
        app.select(ids[3])
        panels[3].close(panels[3].selectedID!)
        app.select(main)
        try check(!app.conversations.contains { $0.id == ids[3] }
                  && !app.currentHistoryArchive.conversations.contains { $0.id == ids[3] },
                  "An untouched draft opened in the main editor is discarded once its last surface leaves")

        let panel = panels[0]
        app.newPanelConversation(in: panel)
        guard case .conversation(let failureID)? = panel.selected?.content else { throw NativeError.message("Missing failure fixture draft") }
        app.setConversationDraft("Save before sending this exact input", id: failureID)
        let bytesBeforeFailure = try Data(contentsOf: store.url)
        rejectWrites = true
        await app.submit(conversationID: failureID)
        try check(app.provisionalPanelConversations.contains(failureID)
                  && app.conversations.first(where: { $0.id == failureID })?.draft == "Save before sending this exact input"
                  && app.executions[failureID] == nil && app.historyPersistence.blocksSubmission
                  && (try Data(contentsOf: store.url)) == bytesBeforeFailure,
                  "Failed first-send persistence retains the provisional draft without creating a bridge or a turn")
        rejectWrites = false
        try check(app.retryHistorySave(), "A panel draft can be durably recovered without dispatching it")
        await app.submit(conversationID: failureID)
        try check(!app.provisionalPanelConversations.contains(failureID)
                  && app.listedConversations.filter { $0.id == failureID }.count == 1
                  && app.conversations.first(where: { $0.id == failureID })?.messages.filter { $0.role == "user" }.count == 1,
                  "First successful Send publishes exactly one chat and one user message")

        let workspace = root.appendingPathComponent("panel-draft-workspace").resolvingSymlinksInPath()
        try FileManager.default.createDirectory(at: workspace, withIntermediateDirectories: true)
        let file = workspace.appendingPathComponent("draft-context.txt")
        try Data("Synthetic attachment for a first panel message.".utf8).write(to: file)
        app.newPanelConversation(in: panels[1])
        guard case .conversation(let attachmentID)? = panels[1].selected?.content,
              let index = app.conversations.firstIndex(where: { $0.id == attachmentID }) else { throw NativeError.message("Missing attachment fixture draft") }
        app.conversations[index].workspacePath = workspace.path
        await app.attachPanelFile(file, conversationID: attachmentID, in: panels[1])
        if let error = panels[1].error { throw NativeError.message("Panel draft attachment fixture: \(error)") }
        try check(app.conversations[index].pendingFiles.count == 1
                  && !app.listedConversations.contains { $0.id == attachmentID }
                  && (try ChatStore(directory: state).load()).conversations.first { $0.id == attachmentID }?.pendingFiles.count == 1,
                  "An attachment-only draft is recoverable without prematurely entering the sidebar")
        await app.submit(conversationID: attachmentID)
        try check(app.listedConversations.contains { $0.id == attachmentID }
                  && app.conversations.first { $0.id == attachmentID }?.messages.first?.text == "Посмотри вложения."
                  && app.conversations.first { $0.id == attachmentID }?.messages.first?.fileContext?.count == 1,
                  "Sending only an attachment creates its chat and retains the exact selected file context")

        app.newPanelConversation(in: panels[3])
        guard case .conversation(let clearedID)? = panels[3].selected?.content else { throw NativeError.message("Missing cleared draft fixture") }
        app.setConversationDraft("An autosaved draft later erased", id: clearedID)
        app.flushDraft()
        app.setConversationDraft("", id: clearedID)
        panels[3].close(panels[3].selectedID!)
        try check(app.saveBeforeExit() && !(try ChatStore(directory: state).load()).conversations.contains { $0.id == clearedID },
                  "Erasing and closing an autosaved provisional draft cannot resurrect an empty chat on restart")
        try check(app.selectedID == main && app.composer == "Keep the main draft",
                  "Panel draft publication, attachments and recovery preserve main editor ownership")
    }
}
