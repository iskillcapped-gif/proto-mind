import AppKit
import WebKit

extension NativeChecks {
    /// A page that asks for a passkey offers to continue in the default browser; passkey autofill
    /// and password requests do not, and leaving that site clears the hint. Real WebKit, local HTML.
    @MainActor static func browserPasskeyHint() async throws {
        func settle(_ condition: () -> Bool) async throws {
            let deadline = Date().addingTimeInterval(10)
            while !condition(), Date() < deadline { try await Task.sleep(for: .milliseconds(20)) }
            guard condition() else { throw NativeError.message("Browser passkey fixture did not reach its expected state") }
        }
        let browser = NativeBrowserTab()
        defer { browser.close() }
        browser.webView.frame = NSRect(x: 0, y: 0, width: 800, height: 600)
        let start = URL(string: "https://claim.example/start")!
        browser.navigate(start.absoluteString)
        let page = URL(string: "https://accounts.example/signin")!
        browser.webView.loadHTMLString("""
            <html><body><script>
            window.passkeyWatched = !!(navigator.credentials && window.webkit.messageHandlers.pmPasskeyRequest);
            navigator.credentials.get({ mediation: "conditional", publicKey: { challenge: new Uint8Array(16) } }).catch(() => {});
            navigator.credentials.get({ password: true }).catch(() => {});
            </script></body></html>
            """, baseURL: page)
        try await settle { !browser.webView.isLoading && browser.webView.url == page }
        try await Task.sleep(for: .milliseconds(200))
        let watched = try await browser.webView.callAsyncJavaScript("return window.passkeyWatched === true", contentWorld: .page) as? Bool
        try check(watched == true, "The built-in browser watches the page's passkey requests")
        try check(browser.passkeyRequest == nil, "Passkey autofill and password requests show no hint")
        _ = try await browser.webView.callAsyncJavaScript(
            "navigator.credentials.get({ publicKey: { challenge: new Uint8Array(16) } }).catch(() => {}); return true", contentWorld: .page)
        try await settle { browser.passkeyRequest != nil }
        try check(browser.passkeyRequest == .init(host: "accounts.example", start: start),
                  "A passkey request names its site and keeps the page the sign-in started from")
        browser.navigate("https://accounts.example/reload", start: false)
        try check(browser.startURL == start, "Reloading does not move where the sign-in started")
        let elsewhere = URL(string: "https://elsewhere.example/")!
        browser.webView.loadHTMLString("<html><body>Elsewhere</body></html>", baseURL: elsewhere)
        try await settle { !browser.webView.isLoading && browser.webView.url == elsewhere }
        try check(browser.passkeyRequest == nil, "Leaving the site that asked clears the passkey hint")
    }
}
