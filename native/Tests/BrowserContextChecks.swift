import AppKit
import WebKit

extension NativeChecks {
    @MainActor
    static func browserContext(fixture: URL, python: URL, root: URL) async throws {
        let url = URL(string: "https://brief.example.invalid/project")!
        let page = try BrowserPageSnapshot(["url": url.absoluteString, "title": "Client brief", "text": "Use EUR.\nDeliver a short proposal.", "selection": true, "truncated": false], expectedURL: url)
        let message = try page.message(instruction: "Prepare a proposal")
        try check(message.contains("Source: " + url.absoluteString) && message.contains("Scope: selected text")
                  && message.contains("> Use EUR.\n> Deliver a short proposal."),
                  "Browser reference preserves the source, selected scope and quoted text in the exact message")
        try check(BrowserReferencePresentation(message)?.instruction == "Prepare a proposal"
                  && BrowserReferencePresentation(message)?.content == page.text,
                  "Browser material collapses in the transcript without changing saved message contents")
        for invalid: [String: Any] in [
            ["url": "https://other.example.invalid", "text": "other page"],
            ["url": url.absoluteString, "text": " "],
            ["url": url.absoluteString, "text": String(repeating: "a", count: 12_002)]
        ] {
            var rejected = false
            do { _ = try BrowserPageSnapshot(invalid, expectedURL: url) } catch { rejected = true }
            try check(rejected, "Browser capture rejects a different URL, empty page or unbounded content")
        }
        var emptyInstruction = false
        do { _ = try page.message(instruction: "  ") } catch { emptyInstruction = true }
        try check(emptyInstruction, "A browser capture requires an explicit task instruction")

        let configuration = LaunchConfiguration(projectRoot: fixture, python: python, stateDirectory: root.appendingPathComponent("browser-context"))
        var rejectWrite = false
        let store = ChatStore(directory: configuration.stateDirectory, beforeCommit: { _ in
            if rejectWrite { throw NativeError.message("Synthetic browser draft save failure") }
        })
        let app = AppModel(configuration: configuration, historyStore: store)
        defer { app.shutdown() }
        app.setProvider("mock"); app.setComposer("Existing main draft")
        let main = app.selectedID!
        app.newPanelConversation(in: app.workspacePanels.lower)
        guard case .conversation(let destination)? = app.workspacePanels.lower.selected?.content else { throw NativeError.message("Missing destination") }
        app.setConversationDraft("Keep my introduction", id: destination)
        try app.addPageToDraft(page, instruction: "Prepare a proposal", conversationID: destination)
        try check(app.selectedID == main && app.composer == "Existing main draft"
                  && app.conversations.first(where: { $0.id == destination })?.draft == "Keep my introduction\n\n" + message,
                  "Page transfer appends to the captured destination while preserving the selected editor")
        let recovered = try ChatStore(directory: configuration.stateDirectory).load()
        try check(recovered.conversations.first(where: { $0.id == destination })?.draft.contains(url.absoluteString) == true
                  && !app.listedConversations.contains(where: { $0.id == destination }),
                  "Unsent browser material survives restart without publishing a premature sidebar task")
        await app.submit(conversationID: destination)
        try check(app.conversations.first(where: { $0.id == destination })?.messages.first?.text == "Keep my introduction\n\n" + message,
                  "First send records the exact selected browser snapshot through the existing task pipeline")
        let panel = app.workspacePanels.upper
        let answer = WorkspaceAnswerPreview(conversationID: destination, messageID: UUID(), title: "Result", text: "# Proposal\n\nReady for review.")
        let answerTab = panel.open(.answer(answer))
        try check(panel.open(.answer(answer)) == answerTab && panel.tabs.count == 1,
                  "Opening a completed answer beside the chat reuses its document tab")
        app.openAnswerBesideChat(ChatMessage(role: "assistant", text: "Panel-owned result"), conversationID: destination,
                                sourcePanel: app.workspacePanels.lower)
        try check(app.workspacePanels.lower.tabs.count == 2 && panel.tabs.count == 1,
                  "An answer opened from a panel keeps its originating surface")

        // Exercise real WebKit against in-memory HTML: no account, network, microphone or paid model.
        let browser = NativeBrowserTab()
        defer { browser.close() }
        browser.webView.frame = NSRect(x: 0, y: 0, width: 800, height: 600)
        panel.open(.browser(browser))
        browser.webView.loadHTMLString("""
            <html><head><title>Local browser fixture</title></head><body>
            <h1>Project brief</h1><p id="selected">Keep the proposal concise.</p>
            <div style="display:none">HIDDEN_SENTINEL</div>
            <textarea>FORM_SENTINEL</textarea><input value="PASSWORD_SENTINEL" type="password">
            <div contenteditable>EDIT_SENTINEL</div><script>window.secret = 'SCRIPT_SENTINEL';</script>
            </body></html>
            """, baseURL: url)
        try await awaitBrowser { !browser.webView.isLoading && browser.webView.url == url }
        // Allow the first layout after navigation; capture itself never changes page focus.
        try await Task.sleep(for: .milliseconds(100))
        let captured = try await browser.capturePage()
        try check(captured.text.contains("Project brief") && captured.text.contains("Keep the proposal")
                  && !captured.text.contains("SENTINEL") && !captured.selection,
                  "Real WebKit capture excludes hidden text, form values, editable regions and scripts")
        _ = try await browser.webView.evaluateJavaScript("const r=document.createRange(); r.selectNodeContents(document.getElementById('selected')); const s=window.getSelection(); s.removeAllRanges(); s.addRange(r); true")
        let selected = try await browser.capturePage()
        try check(selected.selection && selected.text == "Keep the proposal concise.",
                  "WebKit text selection captures only the explicitly selected passage")
        _ = try await browser.webView.evaluateJavaScript("window.getSelection().removeAllRanges(); document.getElementById('selected').textContent = 'x'.repeat(16000); true")
        let bounded = try await browser.capturePage()
        try check(bounded.truncated && bounded.text.utf16.count == BrowserPageSnapshot.characterLimit,
                  "Long browser pages are bounded before crossing WebKit and visibly marked partial")
        _ = try await browser.webView.evaluateJavaScript("(() => { document.getElementById('selected').textContent='Keep the proposal concise.'; const r=document.createRange(); r.selectNodeContents(document.getElementById('selected')); window.getSelection().addRange(r); return true; })()")
        app.cloudConsent = true
        let metadata = try await app.executeLiveVoiceCall(voiceCall("list_browser_pages"), session: UUID())
        try check(metadata["pages"].items.contains(where: { $0["browser_id"].text == browser.id.uuidString })
                  && !metadata.pretty.contains("Keep the proposal concise"),
                  "Voice page discovery returns exact tab IDs without reading or forwarding page text")
        app.setComposer("Keep the voice-independent draft")
        let result = try await app.executeLiveVoiceCall(voiceCall("send_browser_page", ["browser_id": .string(browser.id.uuidString),
            "conversation_id": .string(main.uuidString), "text": .string("Summarize this selection")]), session: UUID())
        try check(result["status"].text == "preparing", "Voice page request uses the selected task's normal execution")
        app.select(destination)
        try await awaitBrowser { !app.isRunning(main) }
        try check(app.conversations.first(where: { $0.id == main })?.messages.first?.text.contains("Scope: selected text") == true
                  && app.conversations.first(where: { $0.id == main })?.draft == "Keep the voice-independent draft"
                  && app.selectedID == destination,
                  "Voice page execution preserves the captured destination and unrelated drafts across navigation")
        browser.close()
        var closedRejected = false
        do { _ = try await browser.capturePage() } catch { closedRejected = true }
        try check(closedRejected && !app.browserPages.contains(where: { $0.browser === browser }),
                  "Closed browser tabs cannot be captured or reused by voice")

        let beforeFailure = try Data(contentsOf: store.url)
        rejectWrite = true
        var saveRejected = false
        do { try app.addPageToDraft(page, instruction: "Retain even if saving fails", conversationID: destination) }
        catch { saveRejected = true }
        try check(saveRejected && app.historyPersistence.blocksSubmission
                  && app.conversations.first(where: { $0.id == destination })?.draft.contains("Retain even if saving fails") == true
                  && (try Data(contentsOf: store.url)) == beforeFailure,
                  "Failed browser draft persistence keeps the local text and blocks sending instead of losing it")
        rejectWrite = false
        try check(app.retryHistorySave(), "Browser draft recovery succeeds without dispatching another task")
    }

    @MainActor
    private static func awaitBrowser(_ condition: () -> Bool) async throws {
        let deadline = Date().addingTimeInterval(15)
        while !condition(), Date() < deadline { try await Task.sleep(for: .milliseconds(20)) }
        guard condition() else { throw NativeError.message("Browser fixture did not reach its expected state") }
    }

    @MainActor
    static func interfaceLanguage(root: URL) throws {
        try liveInterfaceLanguage(root: root)
        let previous = L10n.language
        defer { L10n.language = previous }
        L10n.language = .english
        try check(L10n.text("Новый диалог") == "New conversation" && CodexReasoningEffort.high.title == "High"
                  && NativeSettingsSection.appearance.title == "Appearance",
                  "English localizes primary navigation and model controls without changing model identifiers")
        try check(LiveVoiceProtocol.start(context: "") ["session"]["instructions"].text.contains("Speak English")
                  && LiveVoiceOpening().greetingForLanguageCheck().contains("Speak English"),
                  "English voice sessions and their initial greeting agree on the chosen language")
        let a = LaunchConfiguration(projectRoot: root, python: root, stateDirectory: root.appendingPathComponent("language-a"))
        let b = LaunchConfiguration(projectRoot: root, python: root, stateDirectory: root.appendingPathComponent("language-b"))
        try check(InterfaceLanguage.key(a) != InterfaceLanguage.key(b), "Language preference is isolated by app profile")
        var conversation = Conversation()
        try check(conversation.displayTitle == "New conversation" && conversation.title == "Новый диалог",
                  "Default conversation labels are translated without rewriting saved history")
        conversation.title = "Мой проект"
        try check(conversation.displayTitle == "Мой проект", "User-authored conversation titles are never translated")
    }
}

private extension LiveVoiceOpening {
    func greetingForLanguageCheck() -> String { var value = self; return value.begin()?["content"].text ?? "" }
}
