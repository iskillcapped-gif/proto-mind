import AppKit
import SwiftUI
import WebKit

enum NativeBrowserURL {
    static func isWebURL(_ url: URL) -> Bool {
        ["http", "https"].contains(url.scheme?.lowercased() ?? "") && !(url.host ?? "").isEmpty
            && url.user == nil && url.password == nil
    }

    static func parse(_ input: String) throws -> URL {
        let value = input.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !value.isEmpty, value.utf8.count <= 8192,
              !value.unicodeScalars.contains(where: { $0.value < 32 || $0.value == 127 }),
              !value.contains(" ") else { throw NativeError.message("Введите адрес сайта, например https://example.com.") }
        let hasScheme = value.contains("://") || value.lowercased().hasPrefix("about:")
            || value.lowercased().hasPrefix("javascript:") || value.lowercased().hasPrefix("data:")
            || value.lowercased().hasPrefix("file:") || value.lowercased().hasPrefix("mailto:")
        let candidate = hasScheme ? value : "https://" + value
        guard let url = URL(string: candidate), isWebURL(url) else {
            throw NativeError.message("Здесь открываются адреса http и https. Локальные файлы открывайте через «Файлы».")
        }
        return url
    }
}

@MainActor
final class NativeBrowserTab: NSObject, ObservableObject, WKNavigationDelegate, WKUIDelegate {
    let webView: WKWebView
    @Published var address = ""
    @Published private(set) var title = "Новая страница"
    @Published private(set) var currentURL: URL?
    @Published private(set) var loading = false
    @Published private(set) var canGoBack = false
    @Published private(set) var canGoForward = false
    @Published var error: String?
    var openTab: ((URL) -> Void)?
    private var observations: [NSKeyValueObservation] = []

    override init() {
        let configuration = WKWebViewConfiguration()
        configuration.websiteDataStore = .nonPersistent()
        configuration.mediaTypesRequiringUserActionForPlayback = .all
        configuration.preferences.javaScriptCanOpenWindowsAutomatically = false
        webView = WKWebView(frame: .zero, configuration: configuration)
        super.init()
        webView.navigationDelegate = self; webView.uiDelegate = self
        webView.allowsBackForwardNavigationGestures = true
        observations = [
            webView.observe(\.url, options: [.new]) { [weak self] _, _ in self?.queueRefresh() },
            webView.observe(\.title, options: [.new]) { [weak self] _, _ in self?.queueRefresh() },
            webView.observe(\.isLoading, options: [.new]) { [weak self] _, _ in self?.queueRefresh() },
            webView.observe(\.canGoBack, options: [.new]) { [weak self] _, _ in self?.queueRefresh() },
            webView.observe(\.canGoForward, options: [.new]) { [weak self] _, _ in self?.queueRefresh() }
        ]
    }

    nonisolated private func queueRefresh() {
        DispatchQueue.main.async { [weak self] in
            guard let self else { return }
            let nextURL = self.webView.url
            if self.currentURL != nextURL {
                self.currentURL = nextURL
                self.address = nextURL?.absoluteString ?? ""
            }
            self.title = self.webView.title?.isEmpty == false ? self.webView.title! : nextURL?.host ?? "Новая страница"
            self.loading = self.webView.isLoading
            self.canGoBack = self.webView.canGoBack
            self.canGoForward = self.webView.canGoForward
        }
    }

    func navigate(_ value: String) {
        do {
            let url = try NativeBrowserURL.parse(value)
            error = nil; address = url.absoluteString
            webView.load(URLRequest(url: url))
        } catch { self.error = error.localizedDescription }
    }

    func close() {
        webView.stopLoading()
        observations = []; openTab = nil
        webView.navigationDelegate = nil; webView.uiDelegate = nil
    }

    func webView(_ webView: WKWebView, decidePolicyFor navigationAction: WKNavigationAction,
                 decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        if navigationAction.targetFrame?.isMainFrame == false,
           ["about:blank", "about:srcdoc"].contains(navigationAction.request.url?.absoluteString ?? "") {
            decisionHandler(.allow)
            return
        }
        guard let url = navigationAction.request.url, NativeBrowserURL.isWebURL(url) else {
            decisionHandler(.cancel)
            error = "Этот адрес не открывается во встроенном браузере."
            return
        }
        guard !navigationAction.shouldPerformDownload else {
            decisionHandler(.cancel)
            error = "Для скачивания откройте страницу во внешнем браузере."
            return
        }
        decisionHandler(.allow)
    }

    func webView(_ webView: WKWebView, decidePolicyFor navigationResponse: WKNavigationResponse,
                 decisionHandler: @escaping (WKNavigationResponsePolicy) -> Void) {
        if navigationResponse.canShowMIMEType { decisionHandler(.allow) }
        else {
            error = "Этот файл можно скачать во внешнем браузере."
            decisionHandler(.cancel)
        }
    }

    func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) {
        if (error as NSError).code != NSURLErrorCancelled { self.error = error.localizedDescription }
    }
    func webView(_ webView: WKWebView, didFail navigation: WKNavigation!, withError error: Error) {
        if (error as NSError).code != NSURLErrorCancelled { self.error = error.localizedDescription }
    }
    func webViewWebContentProcessDidTerminate(_ webView: WKWebView) {
        error = "Страница остановилась. Нажмите «Обновить», чтобы загрузить её заново."
    }
    func webView(_ webView: WKWebView, createWebViewWith configuration: WKWebViewConfiguration,
                 for navigationAction: WKNavigationAction, windowFeatures: WKWindowFeatures) -> WKWebView? {
        if let url = navigationAction.request.url, NativeBrowserURL.isWebURL(url) { openTab?(url) }
        return nil
    }
    func webView(_ webView: WKWebView, requestMediaCapturePermissionFor origin: WKSecurityOrigin,
                 initiatedByFrame frame: WKFrameInfo, type: WKMediaCaptureType,
                 decisionHandler: @escaping (WKPermissionDecision) -> Void) { decisionHandler(.deny) }
}

private struct NativeWebSurface: NSViewRepresentable {
    @Environment(\.isEnabled) private var enabled
    let browser: NativeBrowserTab
    func makeNSView(context: Context) -> WKWebView { browser.webView }
    func updateNSView(_ view: WKWebView, context: Context) {
        // Hidden tabs retain their process/page but must give up keyboard input.
        if !enabled, let responder = view.window?.firstResponder as? NSView,
           responder === view || responder.isDescendant(of: view) { view.window?.makeFirstResponder(nil) }
    }
}

struct BrowserView: View {
    @ObservedObject var browser: NativeBrowserTab
    @FocusState private var addressFocused: Bool
    var body: some View {
        VStack(spacing: 0) {
            HStack(spacing: 8) {
                Button { browser.webView.goBack() } label: { Image(systemName: "chevron.left") }
                    .disabled(!browser.canGoBack).help("Назад").accessibilityLabel("Назад")
                Button { browser.webView.goForward() } label: { Image(systemName: "chevron.right") }
                    .disabled(!browser.canGoForward).help("Вперёд").accessibilityLabel("Вперёд")
                Button {
                    if browser.loading { browser.webView.stopLoading() }
                    else if let url = browser.currentURL { browser.navigate(url.absoluteString) }
                    else { browser.navigate(browser.address) }
                } label: { Image(systemName: browser.loading ? "xmark" : "arrow.clockwise") }
                    .help(browser.loading ? "Остановить загрузку" : "Обновить страницу")
                    .accessibilityLabel(browser.loading ? "Остановить загрузку" : "Обновить страницу")
                TextField("Адрес сайта", text: $browser.address)
                    .textFieldStyle(.roundedBorder).onSubmit { browser.navigate(browser.address) }
                    .focused($addressFocused)
                    .accessibilityLabel("Адрес сайта")
                Button {
                    if let url = browser.currentURL, NativeBrowserURL.isWebURL(url) { NSWorkspace.shared.open(url) }
                } label: { Image(systemName: "arrow.up.right.square") }
                    .disabled(browser.currentURL == nil).help("Открыть во внешнем браузере").accessibilityLabel("Открыть во внешнем браузере")
            }.padding(12)
            Divider()
            if let error = browser.error {
                HStack(alignment: .top) {
                    Text(error).font(.caption).textSelection(.enabled)
                    Spacer()
                    Button { browser.error = nil } label: { Image(systemName: "xmark") }
                }.padding(12).foregroundStyle(.orange)
            }
            if browser.currentURL == nil && !browser.loading {
                VStack(spacing: 14) {
                    Image(systemName: "globe").font(.system(size: 34, weight: .light))
                    Text("Откройте страницу рядом с разговором").font(.headline)
                    Text("Введите адрес выше или нажмите ссылку в ответе.\nСтраницы не добавляются в запрос к модели.\nВходы на сайты сохраняются только до закрытия вкладки.")
                        .font(.callout).foregroundStyle(.secondary).multilineTextAlignment(.center)
                }.padding(24).frame(maxWidth: .infinity, maxHeight: .infinity)
            }
            NativeWebSurface(browser: browser).id(ObjectIdentifier(browser))
                .frame(maxWidth: .infinity, maxHeight: browser.currentURL == nil && !browser.loading ? 0 : .infinity)
        }.background(NativeTheme.canvas)
            .task {
                // Wait until the newly selected tab's text field has joined the window.
                await Task.yield()
                if !Task.isCancelled && browser.currentURL == nil { addressFocused = true }
            }
    }
}
