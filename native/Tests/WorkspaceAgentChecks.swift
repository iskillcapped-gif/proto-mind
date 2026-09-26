import AppKit
import Foundation
import SwiftUI

extension NativeChecks {
    @MainActor static func workspaceAgentTools(fixture: URL, python: URL, root: URL) async throws {
        let configuration = LaunchConfiguration(projectRoot: fixture, python: python, stateDirectory: root.appendingPathComponent("agent-workspace"))
        let app = AppModel(configuration: configuration)
        defer { app.shutdown() }
        app.cloudConsent = true
        let id = app.selectedID!
        let index = app.conversations.firstIndex { $0.id == id }!
        app.conversations[index].provider = "api"
        app.conversations[index].apiWorkspaceToolsEnabled = true
        app.conversations[index].apiWorkspaceGeneration = app.workspacePermissionGeneration
        app.conversations[index].workspacePath = fixture.path
        app.setComposer("KEEP THIS DRAFT")
        let state = app.execution(for: id)
        state.running = true; state.requestID = "request-a"; state.workspaceToolsAllowed = true
        state.workspaceToolBinding = app.workspaceToolBinding(app.conversations[index])
        let projects = try await app.executeWorkspaceTool("pm_list_projects", args: .object([:]), state: state, request: "request-a")
        try check(projects["projects"].items.contains { $0["path"].text == fixture.path }, "Workspace tools list exact known projects")
        let question = try await app.executeWorkspaceTool("pm_ask_user", args: .object(["question": .string("Which format?"), "options": .array([.string("PDF"),.string("Word")])]), state: state, request: "request-a")
        try check(state.workspaceQuestions.count == 1 && question["status"].text == "pending", "A question leaves the tool channel free for independent work")
        state.workspaceQuestions[0].answer = "Word"
        let reply = try await app.executeWorkspaceTool("pm_question_result", args: .object(["question_id": question["question_id"]]), state: state, request: "request-a")
        try check(reply["answer"].text == "Word", "Question answers remain bound to their source turn")
        let child = try await app.executeWorkspaceTool("pm_create_task", args: .object(["title": .string("Independent review"), "project_path": .string(fixture.path)]), state: state, request: "request-a")
        try check(app.selectedID == id && app.composer == "KEEP THIS DRAFT" && child["conversation_id"].text != id.uuidString,
                  "Creating a task preserves selection and the editor draft")
        let childID = UUID(uuidString: child["conversation_id"].text)!
        try check(!app.hasAgentAccessSelection(app.conversations.first { $0.id == childID }!), "New delegated task does not silently inherit Full Mac")
        let saved = try JSONDecoder().decode(Conversation.self, from: JSONEncoder().encode(app.conversations.first { $0.id == id }!))
        try check(saved.workspaceQuestions.count == 1 && saved.workspaceQuestions[0].text == "Which format?", "Structured question survives a history round trip")
        _ = try await app.executeWorkspaceTool("pm_offer_continuation", args: .object(["next_step": .string("Verify the final output")]), state: state, request: "request-a")
        try check(app.conversations.first { $0.id == id }?.workspaceContinuation == "Verify the final output" && app.composer == "KEEP THIS DRAFT", "Continuation is saved without starting a paid turn or consuming the draft")
        app.conversations[app.conversations.firstIndex { $0.id == id }!].apiWorkspaceToolsEnabled = false
        do { _ = try await app.executeWorkspaceTool("pm_list_tasks", args: .object([:]), state: state, request: "request-a"); try check(false, "Revoked API tool permission must fail") }
        catch { try check(true, "Workspace tools recheck revoked API permission") }
        app.conversations[app.conversations.firstIndex { $0.id == id }!].apiWorkspaceToolsEnabled = true
        app.conversations[app.conversations.firstIndex { $0.id == id }!].apiWorkspaceGeneration = "old-restore-generation"
        do { _ = try await app.executeWorkspaceTool("pm_list_tasks", args: .object([:]), state: state, request: "request-a"); try check(false, "Restored API tool permission must fail") }
        catch { try check(true, "Restoring private data does not restore API tool authority") }
        app.conversations[app.conversations.firstIndex { $0.id == id }!].apiWorkspaceGeneration = app.workspacePermissionGeneration
        app.conversations[app.conversations.firstIndex { $0.id == id }!].model = "changed-model"
        do { _ = try await app.executeWorkspaceTool("pm_list_tasks", args: .object([:]), state: state, request: "request-a"); try check(false, "Changed source binding must fail") }
        catch { try check(true, "Source model or account changes invalidate in-flight workspace calls") }
        app.conversations[app.conversations.firstIndex { $0.id == id }!].model = saved.model
        do {
            _ = try await app.executeWorkspaceTool("pm_send_task_message", args: .object(["conversation_id": .string(id.uuidString), "text": .string("loop")]), state: state, request: "request-a")
            try check(false, "Self-delegation must fail")
        } catch { try check(true, "Self-delegation is rejected") }
        let marked = AppModel.delegatedTaskMessage("  Review the draft  ", from: app.conversations.first { $0.id == id }!)
        try check(marked.hasPrefix("[Proto-Mind: sent by the agent of task «") && marked.contains("(api")
                  && marked.contains("the operator did not type it") && marked.hasSuffix("]\n\nReview the draft"),
                  "An agent-sent task message names its source task before the text")
        try check(AppModel.delegatedTaskBody(marked) == "Review the draft" && AppModel.delegatedTaskBody("[Plain] text") == "[Plain] text",
                  "An untitled task is named after the delegated request, not its origin header")
        try check(AppModel.delegatedTaskMessage(" \n ", from: app.conversations.first { $0.id == id }!).isEmpty,
                  "An empty agent-sent message stays empty and is still rejected")
        state.requestID = "request-b"
        do {
            _ = try await app.executeWorkspaceTool("pm_list_tasks", args: .object([:]), state: state, request: "request-a")
            try check(false, "Expired workspace turn must fail")
        } catch { try check(true, "A stale tool call cannot act in a newer turn") }
        state.running = false
        try await mcpSessionOwnership(app: app, python: python, root: root)
        if let output = LaunchConfiguration.argument("--workspace-ui-directory") {
            let directory = URL(fileURLWithPath: output)
            try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
            state.workspaceQuestions = [WorkspaceAgentQuestion(requestID: "preview", text: "Which format should I prepare for the client?", options: ["PDF", "Word", "Both"])]
            try await renderWorkspacePreview(WorkspaceAgentQuestionsView(model: app, state: state).padding(24).background(NativeTheme.canvas),
                size: NSSize(width: 640, height: 260), destination: directory.appendingPathComponent("question.png"))
            let table = """
            ## Project estimate

            Included work and assumptions remain separate.

            | Deliverable | Status | Budget |
            | :--- | :---: | ---: |
            | **Landing page** | Ready to review | €350 |
            | `proposal.md` | Saved | €0 |
            | Client photography | Awaiting confirmation of the final selection | — |

            Next: review the proposal with the client.
            """
            try await renderWorkspacePreview(MessageMarkdownView(text: table, copy: { _ in }).padding(24).background(NativeTheme.canvas),
                size: NSSize(width: 740, height: 410), destination: directory.appendingPathComponent("markdown-table.png"))
            try await renderWorkspacePreview(MessageMarkdownView(text: table, copy: { _ in }).padding(20).background(NativeTheme.canvas),
                size: NSSize(width: 340, height: 460), destination: directory.appendingPathComponent("markdown-table-narrow.png"))
            var service = WorkspaceService(); service.name = "Example service"; service.endpoint = "https://example.invalid/mcp"
            try app.workspaceServices.save(service)
            try await renderWorkspacePreview(Form { WorkspaceServiceSettings(app: app, services: app.workspaceServices) }.formStyle(.grouped),
                size: NSSize(width: 640, height: 430), destination: directory.appendingPathComponent("connections.png"))
            try app.workspaceServices.remove(service)
        }

        let browser = NativeBrowserTab()
        defer { browser.close() }
        browser.webView.frame = NSRect(x:0,y:0,width:800,height:600)
        let url = URL(string:"https://workspace-fixture.invalid/")!
        browser.webView.loadHTMLString("""
        <html><body><p id="status">Before</p><button onclick="document.querySelector('#status').textContent='After'">Apply</button>
        <input id="name" placeholder="Name"><input type="password" value="SECRET_SENTINEL"><textarea>PRIVATE_SENTINEL</textarea></body></html>
        """, baseURL:url)
        let deadline = Date().addingTimeInterval(15)
        while (browser.webView.isLoading || browser.webView.url != url) && Date() < deadline {
            try await Task.sleep(for: .milliseconds(20))
        }
        try check(!browser.webView.isLoading && browser.webView.url == url, "Browser fixture loaded")
        try await Task.sleep(for:.milliseconds(100))
        let snapshot = try await browser.agentInspect()
        try check(snapshot["text"].text.contains("Before") && !String(data: try JSONEncoder().encode(snapshot), encoding: .utf8)!.contains("SENTINEL"), "Agent browser inspection excludes form values and secrets")
        guard let button = snapshot["elements"].items.first(where: { $0["label"].text == "Apply" }) else { throw NativeError.message("Missing fixture button") }
        let args: JSONValue = .object(["snapshot_id": snapshot["snapshot_id"], "element_id": button["id"], "action":.string("click"), "text":.string("")])
        _ = try await browser.agentAction(args)
        let after = try await browser.agentInspect()
        try check(after["text"].text.contains("After"), "Agent browser performs an observed action and can verify its outcome")
        do { _ = try await browser.agentAction(args); try check(false,"Stale snapshot must fail") }
        catch { try check(true,"Browser rejects targets from a previous inspection") }
        browser.close()
        do { _ = try await browser.agentInspect(); try check(false,"Closed browser must fail") }
        catch { try check(true,"Closed browser cannot be operated") }
    }

    @MainActor private static func mcpSessionOwnership(app: AppModel, python: URL, root: URL) async throws {
        let script = root.appendingPathComponent("mcp-counter.py")
        try """
        import json, sys, time
        count = 0
        for line in sys.stdin:
            value = json.loads(line)
            if 'id' not in value: continue
            if value['method'] == 'initialize': result = {'protocolVersion':'2025-06-18'}
            elif value['method'] == 'tools/list': result = {'tools':[{'name':'next'}]}
            else:
                if value['params'].get('arguments',{}).get('wait'): time.sleep(30)
                count += 1
                result = {'count':count}
            print(json.dumps({'jsonrpc':'2.0','id':value['id'],'result':result}),flush=True)
        """.write(to: script, atomically: true, encoding: .utf8)
        var service = WorkspaceService(); service.name = "Offline counter"; service.transport = "stdio"
        service.command = python.path; service.arguments = [script.path]; service.enabled = true
        try app.workspaceServices.save(service)
        let a = UUID(), b = UUID()
        let services = app.workspaceServices
        _ = try await services.perform(id: service.id, operation: "list", owner: a)
        _ = try await services.perform(id: service.id, operation: "list", owner: b)
        let first = try await services.perform(id: service.id, operation: "call", name: "next", owner: a)
        let second = try await services.perform(id: service.id, operation: "call", name: "next", owner: a)
        let other = try await services.perform(id: service.id, operation: "call", name: "next", owner: b)
        try check(first["result"]["count"].integer == 1 && second["result"]["count"].integer == 2 && other["result"]["count"].integer == 1,
                  "MCP retains server state across calls but isolates concurrent conversation owners")
        services.cancel(owner: a)
        do { _ = try await services.perform(id: service.id, operation: "call", name: "next", owner: a); try check(false, "Closed owner's catalog must be invalidated") }
        catch { try check(true, "Turn completion closes idle MCP sessions and invalidates their catalog") }
        let stillLive = try await services.perform(id: service.id, operation: "call", name: "next", owner: b)
        try check(stillLive["result"]["count"].integer == 2, "Stopping another conversation leaves this MCP session alive")
        let blocked = Task { try await services.perform(id: service.id, operation: "call", name: "next", arguments: .object(["wait":.bool(true)]), owner: b) }
        try await Task.sleep(for: .milliseconds(100))
        do { _ = try await services.perform(id: service.id, operation: "list", owner: b); try check(false, "Concurrent requests to one session must fail") }
        catch { try check(error.localizedDescription.contains("previous request") || error.localizedDescription.contains("предыдущий запрос"), "Busy MCP reports a busy connection, not a disabled service") }
        services.cancel(owner: b)
        do { _ = try await blocked.value; try check(false, "Cancelled MCP call must not report success") }
        catch { try check(true, "Stop closes an in-flight MCP transport without waiting for its tool") }
        let listed = try await services.checkTools(id: service.id)
        do { _ = try await services.perform(id: service.id, operation: "call", name: "next"); try check(false, "A Settings check must not leave its MCP session open") }
        catch { try check(listed == 1 && error.localizedDescription.contains("List this service"), "A Settings tool check closes its own MCP session") }
        try services.remove(service)
    }

    @MainActor private static func renderWorkspacePreview<Content: View>(_ content: Content, size: NSSize, destination: URL) async throws {
        let window = NSWindow(contentRect: NSRect(origin: .zero, size: size), styleMask: [.borderless], backing: .buffered, defer: false)
        window.isReleasedWhenClosed = false
        let host = NSHostingView(rootView: content.frame(width: size.width, height: size.height, alignment: .topLeading).background(NativeTheme.canvas).environment(\.colorScheme, .dark))
        host.frame = NSRect(origin: .zero, size: size)
        window.contentView = host
        defer { window.contentView = nil; window.close() }
        host.layoutSubtreeIfNeeded()
        try await Task.sleep(for: .milliseconds(150))
        guard let bitmap = host.bitmapImageRepForCachingDisplay(in: host.bounds) else { throw NativeError.message("Preview bitmap unavailable") }
        host.cacheDisplay(in: host.bounds, to: bitmap)
        guard let data = bitmap.representation(using: .png, properties: [:]) else { throw NativeError.message("Preview image unavailable") }
        try data.write(to: destination)
        try check(bitmap.pixelsWide > 0 && bitmap.pixelsHigh > 0, "Workspace controls render in a disposable profile without taking desktop focus")
    }
}
