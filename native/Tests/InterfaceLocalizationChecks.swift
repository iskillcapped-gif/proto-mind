import Foundation
import Observation

extension NativeChecks {
    @MainActor
    static func liveInterfaceLanguage(root: URL) throws {
        let previous = L10n.language
        let suite = "ProtoMind.LanguageChecks.\(UUID().uuidString)"
        let defaults = UserDefaults(suiteName: suite)!
        defer { L10n.language = previous; defaults.removePersistentDomain(forName: suite) }
        let a = LaunchConfiguration(projectRoot: root, python: root, stateDirectory: root.appendingPathComponent("live-language-a"))
        let b = LaunchConfiguration(projectRoot: root, python: root, stateDirectory: root.appendingPathComponent("live-language-b"))
        defaults.set("ru", forKey: InterfaceLanguage.key(b))
        L10n.language = .russian
        let browser = NativeBrowserTab()
        let browserView = browser.webView
        let terminal = WorkspaceTerminal(directory: root)
        defer { browser.close(); terminal.close() }
        var conversation = Conversation()
        conversation.title = "Мой проект — English"
        conversation.draft = "Черновик {0}: 80% готово"
        conversation.model = "provider/model-v1"
        conversation.pendingFiles = [.object(["path": .string("/tmp/Мой файл {1}.txt")])]
        conversation.messages = [ChatMessage(role: "assistant", text: "Ответ остаётся оригинальным.")]
        let original = conversation
        let execution = ConversationExecution(conversationID: conversation.id, configuration: a)
        execution.running = true
        execution.status = "Агент работает"
        execution.stream = "Пишу ответ…"
        execution.requestID = "exact-request"
        let updates = LocalizationSignals(), notices = LocalizationSignals()
        withObservationTracking {
            _ = L10n.text("Настройки")
            _ = execution.status
        } onChange: { updates.record() }
        let observer = NotificationCenter.default.addObserver(forName: .interfaceLanguageChanged, object: nil, queue: nil) { _ in notices.record() }
        defer { NotificationCenter.default.removeObserver(observer) }
        L10n.select(.english, configuration: a, defaults: defaults)
        try check(updates.count == 1 && notices.count == 1 && L10n.text("Настройки") == "Settings",
                  "Choosing English immediately invalidates observed labels and notifies existing native windows")
        try check(defaults.string(forKey: InterfaceLanguage.key(a)) == "en"
                  && defaults.string(forKey: InterfaceLanguage.key(b)) == "ru",
                  "Live language changes persist only in the originating profile")
        try check(conversation == original && execution.running && execution.requestID == "exact-request"
                  && execution.stream == "Пишу ответ…" && execution.status == "Agent working",
                  "Language switching retains exact drafts, messages, attachments and running execution while translating its status")
        try check(browser.title == L10n.text("Новая страница") && terminal.title == "Terminal"
                  && browser.webView === browserView,
                  "Existing empty browser and terminal labels update without replacing their surfaces")
        L10n.select(.english, configuration: a, defaults: defaults)
        try check(notices.count == 1, "Selecting the current language does not reopen or invalidate native windows again")
        let userText = "Мой {1} проект: 80% 😀"
        try check(L10n.format("Продолжение · \(userText)") == "Continue · \(userText)",
                  "Translated templates preserve Cyrillic, percent signs, braces and Unicode in user values")
        let pair: InterfaceMessage = "\(userText) / \("второе {0}")"
        try check(pair.render(template: "{1} — {0}") == "второе {0} — \(userText)",
                  "Translation placeholders can reorder values without recursively substituting inserted text")
        try check(pair.render(template: "{999999999999999999999999999}") == "{999999999999999999999999999}",
                  "Unrecognized translation slots remain literal instead of crashing")
        L10n.select(.russian, configuration: a, defaults: defaults)
        try check(execution.status == "Агент работает" && L10n.text("Настройки") == "Настройки"
                  && conversation == original && defaults.string(forKey: InterfaceLanguage.key(a)) == "ru",
                  "Switching back restores Russian labels without rewriting conversation state")
        try check(browser.title == "Новая страница" && terminal.title == "Терминал" && browser.webView === browserView,
                  "Browser and terminal default labels also switch back while retaining their instances")
        let slots = try NSRegularExpression(pattern: #"\{[0-9]+\}"#)
        func placeholders(_ text: String) -> [String] {
            let value = text as NSString
            return slots.matches(in: text, range: NSRange(location: 0, length: value.length))
                .map { value.substring(with: $0.range) }.sorted()
        }
        try check(Set(L10n.english.keys).isDisjoint(with: L10n.additionalEnglish.keys),
                  "English catalogs have no conflicting duplicate keys")
        for (key, value) in L10n.additionalEnglish {
            guard !value.isEmpty, placeholders(key) == placeholders(value) else {
                throw NativeError.message("Invalid English translation: \(key)")
            }
        }
        try check(true, "All additional English templates retain every dynamic placeholder")
    }
}

private final class LocalizationSignals: @unchecked Sendable {
    private let lock = NSLock()
    private var value = 0
    var count: Int { lock.lock(); defer { lock.unlock() }; return value }
    func record() { lock.lock(); defer { lock.unlock() }; value += 1 }
}
