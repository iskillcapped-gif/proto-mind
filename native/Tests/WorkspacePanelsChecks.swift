import AppKit
import SwiftTerm

extension NativeChecks {
    @MainActor
    static func workspacePanelsContracts(root: URL) async throws {
        let panels = WorkspacePanels()
        try check(!panels.visible && panels.expanded == nil, "Two surfaces start without launching a browser, shell or model")
        panels.toggle()
        try check(panels.visible, "Toolbar reveals both surfaces")
        panels.toggleExpansion(.upper)
        try check(panels.expanded == .upper && !panels.lower.expanded, "Upper expansion owns the workspace without expanding both surfaces")
        panels.toggleExpansion(.lower)
        try check(panels.expanded == .lower && !panels.upper.expanded, "Lower expansion replaces the upper expansion")
        panels.toggleExpansion(.lower)
        try check(panels.expanded == nil && panels.visible, "Collapsing expansion returns to the two-surface layout")
        let id = UUID()
        let tab = panels.upper.open(.conversation(id))
        panels.lower.open(.conversation(UUID()))
        panels.toggle(); panels.toggle()
        try check(panels.upper.selectedID == tab && panels.upper.tabs.count == 1 && panels.lower.tabs.count == 1,
                  "Hiding and reopening the deck preserves independent selected tabs")
        for size in [CGSize(width: 550, height: 300), CGSize(width: 1200, height: 850), CGSize(width: 2000, height: 1000)] {
            for fraction: CGFloat in [-10, 0.2, 0.5, 0.8, 10] {
                let layout = WorkspacePanelsLayout(size: size, visible: true, expanded: nil, horizontal: fraction, vertical: fraction)
                try check(!layout.upper.intersects(layout.lower) && layout.main.maxX <= layout.upper.minX
                          && abs(layout.lower.maxY - size.height) < 0.01 && layout.upper.maxX <= size.width,
                          "Resizable panes remain non-overlapping and bounded")
            }
            for slot in WorkspacePanelPosition.allCases {
                let layout = WorkspacePanelsLayout(size: size, visible: true, expanded: slot, horizontal: 0.48, vertical: 0.5)
                try check((slot == .upper ? layout.upper : layout.lower) == CGRect(origin: .zero, size: size),
                          "Each expanded pane covers only the supplied workspace, excluding the sidebar")
            }
        }
        let terminal = WorkspaceTerminal(directory: root)
        try check(!terminal.running && terminal.view.process.shellPid == 0, "A terminal object cannot launch a shell before the explicit start action")
        terminal.start(executable: "/bin/zsh", arguments: ["-f", "-c", "printf '\\033[32mPTY_READY\\033[0m\\n'; read answer; printf 'GOT:%s\\n' \"$answer\""])
        for _ in 0..<100 {
            if String(data: terminal.view.getTerminal().getBufferAsData(), encoding: .utf8)?.contains("PTY_READY") == true { break }
            try await Task.sleep(nanoseconds: 20_000_000)
        }
        let pid = terminal.view.process.shellPid
        terminal.view.process.send(data: Array("panel input\n".utf8)[...])
        for _ in 0..<100 {
            if !terminal.running { break }
            try await Task.sleep(nanoseconds: 20_000_000)
        }
        let text = String(data: terminal.view.getTerminal().getBufferAsData(), encoding: .utf8) ?? ""
        try check(text.contains("PTY_READY") && text.contains("GOT:panel input"), "Embedded terminal handles ANSI output and interactive PTY input")
        terminal.close()
        try check(!terminal.running && (pid <= 0 || kill(pid, 0) != 0), "A finished terminal does not leave its child running")
        let path = TerminalLaunch.environmentPath("/bin:/bin:relative:/custom/bin")
        try check(path.hasPrefix("/bin:/custom/bin:") && !path.contains("relative") && path.contains("/opt/homebrew/bin"),
                  "CLI lookup preserves explicit absolute paths and includes common Mac installations")
        var connection = ModelAPIConnection()
        connection.name = "Local fixture"; connection.model = "fixture"; connection.endpoint = "http://127.0.0.1:9999/v1"
        try connection.validate()
        let encoded = try JSONEncoder().encode(connection)
        try check(!String(decoding: encoded, as: UTF8.self).contains("key"), "Connection metadata has no API credential field")
        connection.endpoint = "http://example.com/v1"
        var rejected = false
        do { try connection.validate() } catch { rejected = true }
        try check(rejected, "Remote API endpoints require HTTPS")
    }

    @MainActor
    static func workspacePanelsIntegration(fixture: URL, python: URL, root: URL) async throws {
        let state = root.appendingPathComponent("two-panels-state")
        let app = AppModel(configuration: LaunchConfiguration(projectRoot: fixture, python: python, stateDirectory: state))
        defer { app.shutdown() }
        await app.start(); app.setProvider("mock")
        let main = app.selectedID
        app.setComposer("Keep the main editor draft")
        app.newPanelConversation(in: app.workspacePanels.upper)
        app.newPanelConversation(in: app.workspacePanels.lower)
        guard case .conversation(let upper)? = app.workspacePanels.upper.selected?.content,
              case .conversation(let lower)? = app.workspacePanels.lower.selected?.content else { throw NativeError.message("Missing panel conversations") }
        try check(main != upper && upper != lower && app.selectedID == main && app.composer == "Keep the main editor draft",
                  "Creating panel conversations does not replace the main editor or its draft")
        app.setConversationDraft("Upper fixture", id: upper)
        app.setConversationDraft("Lower fixture", id: lower)
        async let first: () = app.submit(conversationID: upper)
        async let second: () = app.submit(conversationID: lower)
        await first; await second
        try check(app.conversations.first { $0.id == upper }?.messages.first?.text == "Upper fixture"
                  && app.conversations.first { $0.id == lower }?.messages.first?.text == "Lower fixture",
                  "Concurrent panel sends keep exact input and output ownership")
        try check(app.conversations.first { $0.id == upper }?.messages.last?.role == "assistant"
                  && app.conversations.first { $0.id == lower }?.messages.last?.role == "assistant"
                  && app.selectedID == main && app.composer == "Keep the main editor draft",
                  "Both PM workflows finish without changing the selected editor")
        let active = app.execution(for: upper)
        active.running = true
        if let tab = app.workspacePanels.upper.selectedID { app.workspacePanels.upper.close(tab) }
        try check(active.running && app.conversations.contains { $0.id == upper }, "Closing a conversation tab never stops or deletes the task")
        active.running = false
        let archive = try ChatStore(directory: state).load()
        try check(archive.conversations.contains { $0.id == upper && !$0.messages.isEmpty }
                  && archive.conversations.contains { $0.id == lower && !$0.messages.isEmpty },
                  "Panel conversations are durable in the existing archive")

        // Exercise the real Swift -> stdio -> HTTP -> receipt -> history path without an account or paid call.
        let addressFile = root.appendingPathComponent("api-fixture-address")
        let server = Process()
        server.executableURL = python
        server.arguments = ["-u", "-c", #"""
import json, sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        self.send_response(200); self.send_header('Content-Type', 'text/event-stream'); self.end_headers()
        for event in [{'type':'response.output_text.delta', 'delta':'API fixture answer'}, {'type':'response.completed','response':{'status':'completed'}}]:
            self.wfile.write(b'data: ' + json.dumps(event).encode() + b'\n\n')
            self.wfile.flush()
    def log_message(self, *_): pass
server = HTTPServer(('127.0.0.1', 0), Handler)
Path(sys.argv[1]).write_text(f'http://127.0.0.1:{server.server_port}/v1')
server.serve_forever()
"""#, addressFile.path]
        server.standardOutput = FileHandle.nullDevice; server.standardError = FileHandle.nullDevice
        try server.run()
        defer { if server.isRunning { server.terminate() }; try? FileManager.default.removeItem(at: addressFile) }
        for _ in 0..<100 {
            if FileManager.default.fileExists(atPath: addressFile.path) { break }
            try await Task.sleep(nanoseconds: 20_000_000)
        }
        var connection = ModelAPIConnection()
        connection.name = "Disposable API"; connection.model = "fixture-model"
        connection.endpoint = try String(contentsOf: addressFile, encoding: .utf8)
        try app.apiConnections.save(connection, secret: "")
        defer { try? app.apiConnections.remove(connection) }
        app.selectAPIConnection(connection, conversationID: lower)
        app.cloudConsent = true
        app.setConversationDraft("Native API input", id: lower)
        await app.submit(conversationID: lower)
        let apiChat = app.conversations.first { $0.id == lower }
        try check(apiChat?.messages.last?.role == "assistant" && apiChat?.messages.last?.text == "API fixture answer",
                  "An API reply passes Native receipt validation and renders as an ordinary assistant response")
        let apiArchive = try ChatStore(directory: state).load()
        try check(apiArchive.conversations.first { $0.id == lower }?.apiConnectionID == connection.id
                  && app.selectedID == main && app.composer == "Keep the main editor draft",
                  "The API route survives history readback without moving or replacing the main draft")
    }
}
