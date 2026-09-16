import AppKit
import WebKit

extension NativeChecks {
    @MainActor
    static func messengerConnections(root: URL) async throws {
        _ = NSApplication.shared
        let profile = root.appendingPathComponent("messenger-ui")
        let telegram = MessengerService.telegram, whatsapp = MessengerService.whatsapp
        try check(telegram.storeID(profile: profile) == telegram.storeID(profile: profile)
                  && telegram.storeID(profile: profile) != whatsapp.storeID(profile: profile)
                  && telegram.storeID(profile: profile) != telegram.storeID(profile: root),
                  "Messenger login stores persist by exact profile and service")
        for value in ["http://web.telegram.org/a/", "https://web.telegram.org.evil.invalid/", "https://user@web.telegram.org/", "https://web.whatsapp.com/"] {
            try check(!telegram.accepts(URL(string: value)!), "Telegram cannot reuse its signed-in browser for an unrelated origin")
        }
        let app = AppModel(configuration: LaunchConfiguration(projectRoot: root, python: root, stateDirectory: profile))
        defer { app.shutdown() }
        let browser = NativeBrowserTab(store: app.messengers.store(telegram), messenger: telegram)
        let second = NativeBrowserTab(store: app.messengers.store(telegram), messenger: telegram)
        let ordinary = NativeBrowserTab()
        let whatsappBrowser = NativeBrowserTab(store: .nonPersistent(), messenger: whatsapp)
        defer { whatsappBrowser.close() }
        let agent = try await whatsappBrowser.webView.evaluateJavaScript("navigator.userAgent") as? String ?? ""
        try check(agent.contains("Version/17.0") && agent.contains("Safari/"),
                  "WhatsApp Web receives the Safari compatibility version missing from stock WKWebView")
        let panel = app.workspacePanels.upper
        panel.open(.browser(browser)); app.desktop.companions.surface(.second).panel.open(.browser(second))
        app.workspacePanels.lower.open(.browser(ordinary))
        try check(browser.webView.configuration.websiteDataStore.isPersistent
                  && !ordinary.webView.configuration.websiteDataStore.isPersistent,
                  "Messenger sign-in persists while ordinary browsing stays ephemeral")
        let url = telegram.url
        browser.webView.frame = NSRect(x: 0, y: 0, width: 800, height: 600)
        browser.webView.loadHTMLString("<html><body><p id='one'>Selected message</p><p>Private neighbour</p></body></html>", baseURL: url)
        try await awaitMessenger { !browser.webView.isLoading && browser.webView.url == url }
        try await Task.sleep(for: .milliseconds(100))
        var rejected = false
        do { _ = try await browser.capturePage() } catch { rejected = true }
        try check(rejected, "Discussing a messenger requires an explicit text selection")
        _ = try await browser.webView.evaluateJavaScript("const r = document.createRange(); r.selectNodeContents(document.getElementById('one')); window.getSelection().addRange(r); true")
        let selected = try await browser.capturePage()
        try check(selected.selection && selected.text == "Selected message" && !selected.text.contains("neighbour"),
                  "Only selected messages enter the bounded untrusted-source snapshot")
        await app.messengers.clear(telegram, app: app)
        try check(panel.tabs.isEmpty && app.desktop.companions.surface(.second).panel.tabs.isEmpty
                  && app.workspacePanels.lower.tabs.count == 1 && browser.closed && second.closed && !ordinary.closed,
                  "Resetting one messenger closes its views in all surfaces without closing ordinary tabs")
    }

    @MainActor
    static func awaitMessenger(_ condition: () -> Bool) async throws {
        let deadline = Date().addingTimeInterval(20)
        while !condition(), Date() < deadline { try await Task.sleep(for: .milliseconds(20)) }
        guard condition() else { throw NativeError.message("Messenger fixture did not reach its expected boundary") }
    }
}
