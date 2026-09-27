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
        let origin = AppModel.delegatedTaskOrigin(marked)
        try check(origin?.body == "Review the draft" && origin?.model.hasPrefix("api") == true && origin?.task.isEmpty == false
                  && AppModel.delegatedTaskOrigin("[Proto-Mind: sent by the agent of task «Broken") == nil,
                  "The transcript shows an agent-sent request with its source task and model, not the raw header")
        try check(AppModel.delegatedTaskMessage(" \n ", from: app.conversations.first { $0.id == id }!).isEmpty,
                  "An empty agent-sent message stays empty and is still rejected")
        let item = { (fields: [String: JSONValue]) in JSONValue.object(fields) }
        try check(AgentToolRow.title(item(["kind": .string("commandExecution"), "command": .string("pytest -q"), "text": .string("Run the tests")])) == "Run the tests"
                  && AgentToolRow.title(item(["kind": .string("commandExecution"), "command": .string("git status --short\nsecond")])) == "git status --short",
                  "A command shows its description or first line instead of a bare tool name")
        try check(AgentToolRow.title(item(["kind": .string("fileChange"), "paths": .array([.string("/tmp/SidebarView.swift")]), "change_count": .number(1)])).hasSuffix("SidebarView.swift")
                  && AgentToolRow.title(item(["kind": .string("fileRead"), "path": .string("/tmp/AGENTS.md")])).hasSuffix("AGENTS.md")
                  && AgentToolRow.icon(item(["kind": .string("search")])) == "magnifyingglass",
                  "File edits, reads and searches name their file or pattern")
        try check(AgentToolRow.title(item(["kind": .string("dynamicToolCall"), "tool": .string("Bash")])) == "Bash"
                  && AgentToolRow.title(item(["kind": .string("dynamicToolCall"), "tool": .string("mcp__pm__pm_list_tasks")])) == "PM · list_tasks"
                  && AgentToolRow.title(item(["kind": .string("dynamicToolCall"), "tool": .string("pm_open_task")])) == "PM · open_task",
                  "Earlier Claude actions are not labeled as PM tools, while real PM tools still are")
        let home = FileManager.default.homeDirectoryForCurrentUser.path
        try check(CompletedFileChangesView.displayPath("/work/app/scripts/build.sh", root: "/work/app") == "scripts/build.sh"
                  && CompletedFileChangesView.displayPath(home + "/notes/a.md", root: "/work/app") == "~/notes/a.md"
                  && CompletedFileChangesView.displayPath("src/main.swift", root: "") == "src/main.swift",
                  "Changed files read relative to the task folder or the home folder")
        try check(WorkTimelinePresentation.toolSummary(["fileRead", "search"], live: false) == "Чтение файлов, поиск по файлам",
                  "A group of reads and searches is summarized as such, not as PM tools")
        do {
            _ = try await app.executeWorkspaceTool("pm_computer_action", args: .object(["action": .string("click"), "x": .number(10), "y": .number(10),
                "x2": .null, "y2": .null, "amount": .null, "text": .null]), state: state, request: "request-a")
            try check(false, "An API chat must not control the Mac")
        } catch { try check(error.localizedDescription.contains("Claude with Full Mac"), "Computer use is refused outside Claude with Full Mac") }
        do {
            _ = try await app.executeWorkspaceTool("pm_computer_batch", args: .object(["steps": .array([]), "capture": .null]), state: state, request: "request-a")
            try check(false, "An API chat must not run computer batches")
        } catch { try check(error.localizedDescription.contains("Claude with Full Mac"), "Computer batches are refused outside Claude with Full Mac") }
        do {
            _ = try await app.executeWorkspaceTool("pm_screen_zoom", args: .object(["region": .array([.number(0), .number(0), .number(10), .number(10)])]),
                                                   state: state, request: "request-a")
            try check(false, "An API chat must not zoom into the screen")
        } catch { try check(error.localizedDescription.contains("Claude with Full Mac"), "Screen zoom is refused outside Claude with Full Mac") }
        let mapping = ComputerCapture(originX: 182, originY: 38, pointsPerPixel: 0.5, width: 2468, height: 1854)
        try check(try mapping.point(878, 790) == CGPoint(x: 621, y: 433) && (try? mapping.point(3000, 10)) == nil
                  && mapping.pixel(CGPoint(x: 621, y: 433))! == (878, 790) && mapping.pixel(CGPoint(x: 10, y: 10)) == nil,
                  "Capture pixels map to screen points and back, and out-of-image coordinates are refused")
        let shortcut = try ComputerUseController.keyStroke("cmd+shift+t")
        try check(shortcut.key == 17 && shortcut.flags.contains(.maskCommand) && shortcut.flags.contains(.maskShift)
                  && (try ComputerUseController.keyStroke("return")).key == 36 && (try? ComputerUseController.keyStroke("hyper+q")) == nil,
                  "Key names and modifiers become macOS key codes and flags")
        try check((try ComputerUseController.keyStroke("Page_Down")).key == 121 && (try ComputerUseController.keyStroke("Return")).key == 36
                  && (try ComputerUseController.keyStroke("super+l")).flags == .maskCommand
                  && (try ComputerUseController.modifiers("shift+cmd")) == [.maskShift, .maskCommand] && (try ComputerUseController.modifiers("")).isEmpty
                  && (try? ComputerUseController.modifiers("cmd+x")) == nil,
                  "xdotool-style key names and click modifiers are understood")
        func step(_ action: String, x: Int? = nil, y: Int? = nil, amount: Int? = nil, text: String? = nil, direction: String? = nil) -> JSONValue {
            .object(["action": .string(action), "x": x.map { .number(Double($0)) } ?? .null, "y": y.map { .number(Double($0)) } ?? .null,
                     "x2": .null, "y2": .null, "amount": amount.map { .number(Double($0)) } ?? .null, "text": text.map { .string($0) } ?? .null,
                     "direction": direction.map { .string($0) } ?? .null])
        }
        let planned = try ComputerUseController.plan(batch: [step("click", x: 878, y: 790, text: "cmd"), step("type", text: "поиск"),
                                                             step("key", amount: 3, text: "Down"), step("scroll", amount: 4, direction: "left"),
                                                             step("wait", amount: 2), step("click")], capture: mapping)
        try check(planned.map(\.action) == ["click", "type", "key", "scroll", "wait", "click"] && planned[0].flags == .maskCommand
                  && planned[0].start == CGPoint(x: 621, y: 433) && planned[2].amount == 3 && planned[3].direction == "left"
                  && planned[5].start == nil,
                  "A batch is planned step by step; a click without coordinates acts at the pointer")
        do {
            _ = try ComputerUseController.plan(batch: [step("click", x: 10, y: 10), step("drag", x: 10, y: 10)], capture: mapping)
            try check(false, "A malformed batch step must be rejected")
        } catch { try check(error.localizedDescription.hasPrefix("Step 2:") && error.localizedDescription.hasSuffix("Nothing ran."),
                            "A malformed step rejects the whole batch before anything runs") }
        try check((try? ComputerUseController.plan(step("wait", amount: 31), capture: nil)) == nil
                  && (try? ComputerUseController.plan(step("key", amount: 101, text: "Down"), capture: nil)) == nil
                  && (try? ComputerUseController.plan(step("click", x: 5, y: 5), capture: nil)) == nil
                  && (try? ComputerUseController.plan(step("cursor_position"), capture: nil)) != nil,
                  "Waits, repeats and coordinates are bounded, and coordinates need a capture")
        let small = CGContext(data: nil, width: 300, height: 120, bitsPerComponent: 8, bytesPerRow: 0, space: CGColorSpaceCreateDeviceRGB(),
                              bitmapInfo: CGImageAlphaInfo.noneSkipLast.rawValue)!
        small.setFillColor(CGColor(gray: 0.4, alpha: 1)); small.fill(CGRect(x: 0, y: 0, width: 300, height: 120))
        let zoomed = try ComputerUseController.encode(small.makeImage()!, enlarge: true), plain = try ComputerUseController.encode(small.makeImage()!)
        try check(zoomed.1 == 1200 && zoomed.2 == 480 && plain.1 == 300,
                  "A zoomed region is enlarged to a normal capture size; a normal capture never is")
        let noise = CGContext(data: nil, width: 3420, height: 2214, bitsPerComponent: 8, bytesPerRow: 0, space: CGColorSpaceCreateDeviceRGB(),
                              bitmapInfo: CGImageAlphaInfo.noneSkipLast.rawValue)!
        for band in 0..<220 {
            noise.setFillColor(CGColor(red: CGFloat(band % 7) / 7, green: CGFloat(band % 11) / 11, blue: CGFloat(band % 5) / 5, alpha: 1))
            noise.fill(CGRect(x: (band * 37) % 3420, y: (band * 53) % 2214, width: 300, height: 60))
        }
        let (jpeg, width, height) = try ComputerUseController.encode(noise.makeImage()!)
        try check(jpeg.count <= 300_000 && width <= 1400 && height <= 1400 && width > 600,
                  "A Retina screen capture fits PM's tool-reply bound")
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
