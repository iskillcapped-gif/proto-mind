import AppKit
import UserNotifications

/// A macOS notification when a reply or an error arrives while the operator is not looking at
/// that chat: PM is in the background, the cube is folded, or another chat is open. A click opens
/// the chat at that reply. Only the app bundle posts them; checks and the gallery never do.
@MainActor
final class ReplyNotifications: NSObject, ObservableObject, UNUserNotificationCenterDelegate {
    @Published private(set) var enabled: Bool
    private weak var app: AppModel?
    private let center: UNUserNotificationCenter?
    private let defaults: UserDefaults
    private let key: String

    init(stateDirectory: URL, defaults: UserDefaults) {
        self.defaults = defaults
        key = NativeUIPreference.key("replyNotifications", stateDirectory: stateDirectory)
        enabled = defaults.object(forKey: key) as? Bool ?? true
        // UNUserNotificationCenter needs a bundled app; a bare test binary has none.
        center = Bundle.main.bundleURL.pathExtension == "app" && Bundle.main.bundleIdentifier != nil ? .current() : nil
    }

    func start(app: AppModel) {
        self.app = app
        guard let center else { return }
        center.delegate = self
        if enabled { center.requestAuthorization(options: [.alert, .sound]) { _, _ in } }
    }

    func setEnabled(_ value: Bool) {
        enabled = value
        defaults.set(value, forKey: key)
        if value { center?.requestAuthorization(options: [.alert, .sound]) { _, _ in } }
    }

    /// Called from the completion append path, with the chat that received the reply.
    func replyArrived(_ message: ChatMessage, in conversation: Conversation) {
        guard enabled, let center, let app, message.role == "assistant" || message.isError else { return }
        let folded = app.desktop.enabled && !app.desktop.expanded
        guard !NSApp.isActive || folded || app.selectedID != conversation.id else { return }
        let content = UNMutableNotificationContent()
        content.title = conversation.displayTitle
        if message.isError { content.subtitle = L10n.pick("Нужна проверка", "Needs attention") }
        content.body = Self.preview(message.text)
        content.sound = .default
        content.threadIdentifier = conversation.id.uuidString
        content.userInfo = ["conversation": conversation.id.uuidString, "message": message.id.uuidString]
        center.add(UNNotificationRequest(identifier: message.id.uuidString, content: content, trigger: nil))
    }

    /// The first line that reads as prose: Markdown markers, code fences and extra spaces removed.
    static func preview(_ text: String, limit: Int = 160) -> String {
        var fenced = false, line = ""
        for raw in text.split(whereSeparator: \.isNewline) {
            let candidate = raw.trimmingCharacters(in: .whitespaces)
            if candidate.hasPrefix("```") { fenced.toggle(); continue }
            if !fenced, !candidate.isEmpty, !candidate.hasPrefix("|") { line = candidate; break }
        }
        var plain = line.replacingOccurrences(of: #"^(#{1,6}\s+|>\s*|[-*+]\s+|\d+[.)]\s+)"#, with: "", options: .regularExpression)
        plain = plain.replacingOccurrences(of: #"\[([^\]]+)\]\([^)]+\)"#, with: "$1", options: .regularExpression)
        plain = plain.replacingOccurrences(of: #"[*_`]"#, with: "", options: .regularExpression)
        plain = plain.replacingOccurrences(of: #"\s+"#, with: " ", options: .regularExpression)
        return plain.count > limit ? String(plain.prefix(limit - 1)) + "…" : plain
    }

    nonisolated func userNotificationCenter(_ center: UNUserNotificationCenter, didReceive response: UNNotificationResponse,
                                            withCompletionHandler completionHandler: @escaping () -> Void) {
        let info = response.notification.request.content.userInfo
        let conversation = (info["conversation"] as? String).flatMap(UUID.init(uuidString:))
        let message = (info["message"] as? String).flatMap(UUID.init(uuidString:))
        Task { @MainActor in
            self.open(conversation, at: message)
            completionHandler()
        }
    }

    nonisolated func userNotificationCenter(_ center: UNUserNotificationCenter, willPresent notification: UNNotification,
                                            withCompletionHandler completionHandler: @escaping (UNNotificationPresentationOptions) -> Void) {
        // Posted only when that chat is out of sight, so show it even while PM is frontmost.
        completionHandler([.banner, .sound])
    }

    private func open(_ id: UUID?, at message: UUID?) {
        guard let app, let id, app.conversations.contains(where: { $0.id == id }) else { return }
        NSApp.activate(ignoringOtherApps: true)
        app.desktop.revealWorkspace()
        if app.canNavigateConversations { app.returnToConversation(id, messageID: message) }
    }
}
