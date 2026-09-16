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
              !value.contains(" ") else { throw NativeError.message(L10n.text("Введите адрес сайта, например https://example.com.")) }
        let hasScheme = value.contains("://") || value.lowercased().hasPrefix("about:")
            || value.lowercased().hasPrefix("javascript:") || value.lowercased().hasPrefix("data:")
            || value.lowercased().hasPrefix("file:") || value.lowercased().hasPrefix("mailto:")
        let candidate = hasScheme ? value : "https://" + value
        guard let url = URL(string: candidate), isWebURL(url) else {
            throw NativeError.message(L10n.text("Здесь открываются адреса http и https. Локальные файлы открывайте через «Файлы»."))
        }
        return url
    }
}

@MainActor
final class NativeBrowserTab: NSObject, ObservableObject, WKNavigationDelegate, WKUIDelegate {
    let id = UUID()
    private(set) var navigationRevision = 0
    private(set) var closed = false
    let webView: WKWebView
    let messenger: MessengerService?
    @Published var address = ""
    @Published private(set) var title = L10n.text("Новая страница")
    @Published private(set) var currentURL: URL?
    @Published private(set) var loading = false
    @Published private(set) var canGoBack = false
    @Published private(set) var canGoForward = false
    @Published var error: String?
    var openTab: ((URL) -> Void)?
    private var observations: [NSKeyValueObservation] = []

    override convenience init() { self.init(store: .nonPersistent()) }

    init(store: WKWebsiteDataStore, messenger: MessengerService? = nil) {
        self.messenger = messenger
        let configuration = WKWebViewConfiguration()
        configuration.websiteDataStore = store
        if messenger == .whatsapp {
            // WhatsApp's browser gate expects a Safari version token; WKWebView
            // omits it. Advertise the macOS 14 minimum WebKit compatibility level.
            configuration.applicationNameForUserAgent = "Version/17.0 Safari/605.1.15"
        }
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
            self.title = self.webView.title?.isEmpty == false ? self.webView.title! : nextURL?.host ?? L10n.text("Новая страница")
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
        closed = true; navigationRevision += 1
        webView.stopLoading()
        observations = []; openTab = nil
        webView.navigationDelegate = nil; webView.uiDelegate = nil
    }

    func webView(_ webView: WKWebView, didStartProvisionalNavigation navigation: WKNavigation!) {
        navigationRevision += 1
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
            error = L10n.text("Этот адрес не открывается во встроенном браузере.")
            return
        }
        guard !navigationAction.shouldPerformDownload else {
            decisionHandler(.cancel)
            error = L10n.text("Для скачивания откройте страницу во внешнем браузере.")
            return
        }
        if let messenger, navigationAction.targetFrame?.isMainFrame != false, !messenger.accepts(url) {
            decisionHandler(.cancel)
            if navigationAction.navigationType == .linkActivated { openTab?(url) }
            else { error = L10n.pick("Этот переход отклонён. Откройте ссылку в обычной вкладке браузера.", "This navigation was blocked. Open the link in a regular browser tab.") }
            return
        }
        decisionHandler(.allow)
    }

    func webView(_ webView: WKWebView, decidePolicyFor navigationResponse: WKNavigationResponse,
                 decisionHandler: @escaping (WKNavigationResponsePolicy) -> Void) {
        if navigationResponse.canShowMIMEType { decisionHandler(.allow) }
        else {
            error = L10n.text("Этот файл можно скачать во внешнем браузере.")
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
        error = L10n.text("Страница остановилась. Нажмите «Обновить», чтобы загрузить её заново.")
    }
    func webView(_ webView: WKWebView, createWebViewWith configuration: WKWebViewConfiguration,
                 for navigationAction: WKNavigationAction, windowFeatures: WKWindowFeatures) -> WKWebView? {
        if let url = navigationAction.request.url, NativeBrowserURL.isWebURL(url) { openTab?(url) }
        return nil
    }
    func webView(_ webView: WKWebView, requestMediaCapturePermissionFor origin: WKSecurityOrigin,
                 initiatedByFrame frame: WKFrameInfo, type: WKMediaCaptureType,
                 decisionHandler: @escaping (WKPermissionDecision) -> Void) { decisionHandler(.deny) }

    func webView(_ webView: WKWebView, runOpenPanelWith parameters: WKOpenPanelParameters,
                 initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping ([URL]?) -> Void) {
        guard messenger != nil, let owner = webView.window, owner.attachedSheet == nil else { completionHandler(nil); return }
        let expected = navigationRevision
        let picker = NSOpenPanel()
        picker.canChooseFiles = true; picker.canChooseDirectories = false
        picker.allowsMultipleSelection = parameters.allowsMultipleSelection
        picker.beginSheetModal(for: owner) { [weak self] response in
            guard let self, !self.closed, self.navigationRevision == expected, response == .OK else { completionHandler(nil); return }
            completionHandler(picker.urls)
        }
    }
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
    @ObservedObject var app: AppModel
    var sourcePanel: WorkspacePanelModel? = nil
    @State private var snapshot: BrowserPageSnapshot?
    @State private var snapshotDestination: UUID?
    @State private var capturing = false
    @FocusState private var addressFocused: Bool
    @Environment(\.workspaceChrome) private var chrome
    @Environment(\.isEnabled) private var enabled
    var body: some View {
        VStack(spacing: 0) {
            HStack(spacing: 8) {
                Button { browser.webView.goBack() } label: { Image(systemName: "chevron.left") }
                    .disabled(!browser.canGoBack).help(L10n.text("Назад")).accessibilityLabel(L10n.text("Назад"))
                Button { browser.webView.goForward() } label: { Image(systemName: "chevron.right") }
                    .disabled(!browser.canGoForward).help(L10n.text("Вперёд")).accessibilityLabel(L10n.text("Вперёд"))
                Button {
                    if browser.loading { browser.webView.stopLoading() }
                    else if let url = browser.currentURL { browser.navigate(url.absoluteString) }
                    else { browser.navigate(browser.address) }
                } label: { Image(systemName: browser.loading ? "xmark" : "arrow.clockwise") }
                    .help(browser.loading ? L10n.text("Остановить загрузку") : L10n.text("Обновить страницу"))
                    .accessibilityLabel(browser.loading ? L10n.text("Остановить загрузку") : L10n.text("Обновить страницу"))
                TextField(L10n.text("Адрес сайта"), text: $browser.address)
                    .textFieldStyle(.roundedBorder).onSubmit { browser.navigate(browser.address); addressFocused = false }
                    .focused($addressFocused)
                    .workspaceChromeField($addressFocused)
                    .onExitCommand { addressFocused = false }
                    .accessibilityLabel(L10n.text("Адрес сайта"))
                Button {
                    guard !capturing else { return }
                    capturing = true
                    snapshotDestination = app.selectedID
                    Task { @MainActor in
                        defer { capturing = false }
                        do { snapshot = try await browser.capturePage() }
                        catch { browser.error = error.localizedDescription }
                    }
                } label: {
                    Image(systemName: capturing ? "hourglass" : "text.badge.plus")
                }.disabled(capturing || browser.loading || browser.currentURL == nil)
                    .help(L10n.pick("Передать страницу или выделение в задачу", "Use this page or selection in a task"))
                    .accessibilityLabel(L10n.pick("Передать в задачу", "Use in a task"))
                Button {
                    if let url = browser.currentURL, NativeBrowserURL.isWebURL(url) { NSWorkspace.shared.open(url) }
                } label: { Image(systemName: "arrow.up.right.square") }
                    .disabled(browser.currentURL == nil).help(L10n.text("Открыть во внешнем браузере")).accessibilityLabel(L10n.text("Открыть во внешнем браузере"))
            }.padding(12).workspacePanelHeader()
            Divider().workspacePanelHeader()
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
                    Text(L10n.text("Откройте страницу рядом с разговором")).font(.headline)
                    Text(L10n.pick("Введите адрес выше или нажмите ссылку в ответе.\nПередайте текст кнопкой «В задачу» или голосом.\nВходы на сайты сохраняются только до закрытия вкладки.", "Enter an address above or follow a link in a reply.\nUse the page in a task with the toolbar button or your voice.\nWebsite sessions last until the tab closes."))
                        .font(.callout).foregroundStyle(.secondary).multilineTextAlignment(.center)
                }.padding(24).frame(maxWidth: .infinity, maxHeight: .infinity)
            }
            NativeWebSurface(browser: browser).id(ObjectIdentifier(browser))
                .frame(maxWidth: .infinity, maxHeight: browser.currentURL == nil && !browser.loading ? 0 : .infinity)
        }.background(NativeTheme.canvas)
            .workspaceSheet(item: $snapshot) { value in
                BrowserContextView(app: app, snapshot: value, sourcePanel: sourcePanel, destination: snapshotDestination)
            }
            .task {
                // Wait until the newly selected tab's text field has joined the window.
                await Task.yield()
                if !Task.isCancelled && enabled && browser.currentURL == nil && (chrome?.visible ?? true) { addressFocused = true }
            }
    }
}
