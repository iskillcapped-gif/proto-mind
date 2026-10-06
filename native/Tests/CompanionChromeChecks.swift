import AppKit
import SwiftUI

extension NativeChecks {
    @MainActor
    static func companionChrome(root: URL) async throws {
        let suite = "proto-companion-chrome." + UUID().uuidString
        let defaults = UserDefaults(suiteName: suite)!
        defer { defaults.removePersistentDomain(forName: suite) }
        let state = root.appendingPathComponent("companion-chrome")
        let app = AppModel(configuration: LaunchConfiguration(projectRoot: root, python: root, stateDirectory: state), uiDefaults: defaults)
        let desktop = DesktopPresentation(stateDirectory: state, defaults: defaults, presentsWindows: false, pointerLocation: nil)
        let window = NSWindow(contentRect: NSRect(x: 100, y: 100, width: 1080, height: 720),
                              styleMask: [.titled, .resizable, .closable], backing: .buffered, defer: false)
        window.isReleasedWhenClosed = false
        defer { desktop.shutdown(); app.shutdown(); window.close() }
        desktop.attach(window: window, app: app)
        desktop.enable(animated: false)
        let owner = desktop.companions
        owner.toggle(.first); owner.toggle(.second)
        let first = owner.surface(.first), second = owner.surface(.second)
        let browser = NativeBrowserTab()
        let browserID = first.panel.open(.browser(browser))
        // The HTML is supplied in memory. The base URL makes no network request.
        browser.webView.loadHTMLString("<html><head><title>Chrome fixture</title></head><body style='margin:0;height:3000px'>Retained page<script>window.chromeToken='retained'</script></body></html>",
                                       baseURL: URL(string: "https://chrome.example.invalid/"))
        let terminal = WorkspaceTerminal(directory: root)
        let terminalID = second.panel.open(.terminal(terminal))
        terminal.start(executable: "/bin/zsh", arguments: ["-f", "-c", "printf 'CHROME_READY\\n'; read answer; printf 'GOT:%s\\n' \"$answer\""])
        let pid = terminal.view.process.shellPid
        for _ in 0..<150 {
            if browser.currentURL != nil && !browser.loading && browser.webView.title == "Chrome fixture" { break }
            try await Task.sleep(for: .milliseconds(20))
        }
        try check(browser.webView.title == "Chrome fixture" && browser.error == nil && terminal.running,
                  "Chrome fixture opens a real WebKit page and interactive terminal without a provider call")
        let originalWebView = browser.webView
        let originalTerminal = terminal.view
        func settle() async throws {
            try await Task.sleep(for: .milliseconds(200))
            first.window?.contentView?.layoutSubtreeIfNeeded()
            second.window?.contentView?.layoutSubtreeIfNeeded()
        }
        try await settle()
        let firstWidth = first.window!.contentView!.bounds.width
        let secondWidth = second.window!.contentView!.bounds.width
        // A small companion previews its page as laid out in the expanded window, scaled to fit.
        func miniature(_ view: NSView, in surface: DesktopCompanion) -> Bool {
            guard let reference = surface.expandedSize, let content = surface.window?.contentView else { return false }
            return view.bounds.width > content.bounds.width * 1.5 && abs(view.bounds.width - reference.width) < 2
        }
        try check(miniature(browser.webView, in: first) && miniature(terminal.view, in: second),
                  "Small companions show their page and terminal laid out at the expanded size as a miniature (web \(browser.webView.bounds.width) in \(firstWidth), terminal \(terminal.view.bounds.width) in \(secondWidth))")
        owner.updateHover(.first, inside: true)
        try await settle()
        try check(first.chrome.visible && miniature(browser.webView, in: first) && miniature(terminal.view, in: second),
                  "Hover shows the window header and keeps the miniature without bars")
        owner.updateHover(.second, inside: true)
        try await settle()
        try check(second.chrome.visible && miniature(terminal.view, in: second), "The lower miniature keeps its terminal unchanged on hover")
        let editing = UUID(), dragging = UUID()
        first.chrome.hold(editing, while: true); first.chrome.hold(dragging, while: true)
        owner.updateHover(.first, inside: false)
        first.chrome.hold(editing, while: false)
        try await settle()
        try check(first.chrome.visible, "Overlapping editing and dragging holds cannot hide the header until both interactions finish")
        first.chrome.hold(dragging, while: false)
        owner.updateHover(.second, inside: false)
        try await settle()
        try check(!first.chrome.visible && !second.chrome.visible && miniature(browser.webView, in: first) && miniature(terminal.view, in: second),
                  "Leaving both windows hides their headers")
        owner.updateHover(.first, inside: true)
        owner.updateHover(.first, inside: false)
        owner.updateHover(.first, inside: true)
        try await settle()
        try check(first.chrome.visible, "Rapid re-entry cancels an obsolete header hide")
        owner.updateHover(.first, inside: false)
        try await settle()
        owner.toggleExpansion(.first)
        try await settle()
        try check(first.expanded && first.window!.contentView!.bounds.height - browser.webView.bounds.height > 100
                  && abs(browser.webView.bounds.width - first.window!.contentView!.bounds.width) < 2,
                  "An expanded companion is used at its own size, with its full controls")
        owner.toggleExpansion(.first)
        owner.detach(.first)
        try await settle()
        try check(!first.docked && miniature(browser.webView, in: first), "A detached small window is a miniature too")
        let token = try await browser.webView.evaluateJavaScript("window.chromeToken") as? String
        try check(token == "retained" && browser.webView === originalWebView && terminal.view === originalTerminal
                  && terminal.view.process.shellPid == pid && terminal.running
                  && first.panel.selectedID == browserID && second.panel.selectedID == terminalID,
                  "Hover, expansion, miniature and detachment preserve the loaded page, selected tabs and exact PTY process")
        terminal.view.process.send(data: Array("after hover\n".utf8)[...])
        for _ in 0..<100 {
            if !terminal.running { break }
            try await Task.sleep(for: .milliseconds(20))
        }
        try check(String(data: terminal.view.getTerminal().getBufferAsData(), encoding: .utf8)?.contains("GOT:after hover") == true,
                  "The retained terminal still accepts input after its miniature")
        first.chrome.hold(editing, while: true)
        desktop.collapse(animated: false)
        try check(!first.chrome.visible && !second.chrome.visible, "Folding clears temporary hover and editing holds")
        desktop.expand(animated: false)
        try await settle()
        try check(!first.chrome.visible && miniature(browser.webView, in: first),
                  "Reopening cannot inherit a stuck header from the preceding presentation")

        let normalBrowser = NativeBrowserTab()
        normalBrowser.webView.loadHTMLString("<title>Normal fixture</title>", baseURL: URL(string: "https://normal.example.invalid/"))
        let normalHost = NSHostingView(rootView: BrowserView(browser: normalBrowser, app: app))
        normalHost.sizingOptions = []
        normalHost.frame = NSRect(x: 0, y: 0, width: 500, height: 400)
        defer { normalBrowser.close() }
        try await Task.sleep(for: .milliseconds(300))
        normalHost.layoutSubtreeIfNeeded()
        try check(normalBrowser.webView.bounds.height < 370 && normalBrowser.webView.bounds.height > 200,
                  "Browser controls outside companion windows remain visible by default")
    }
}
