import AppKit
import SwiftUI

/// Read state is a presentation preference, never a dialog-history mutation.
@MainActor
final class ResponseAttention: ObservableObject {
    struct Entry: Codable, Equatable {
        let messageID: UUID
        let needsAttention: Bool
        var label: String { needsAttention ? L10n.pick("Требует внимания", "Needs attention") : L10n.pick("Новый ответ", "New response") }
    }
    @Published private(set) var entries: [UUID: Entry]
    private let defaults: UserDefaults
    private let key: String

    init(stateDirectory: URL, defaults: UserDefaults = .standard) {
        self.defaults = defaults
        key = NativeUIPreference.key("responseAttention", stateDirectory: stateDirectory)
        entries = defaults.data(forKey: key).flatMap { try? JSONDecoder().decode([UUID: Entry].self, from: $0) } ?? [:]
    }

    func record(_ message: ChatMessage, conversationID: UUID) {
        guard message.role == "assistant" || message.isError && message.role == "report" else { return }
        entries[conversationID] = Entry(messageID: message.id, needsAttention: message.isError)
        save()
    }

    func entry(for conversation: Conversation) -> Entry? {
        guard let entry = entries[conversation.id], conversation.messages.contains(where: { $0.id == entry.messageID }) else { return nil }
        return entry
    }

    func acknowledge(conversationID: UUID, messageID: UUID) {
        guard entries[conversationID]?.messageID == messageID else { return }
        entries.removeValue(forKey: conversationID)
        save()
    }

    func prune(_ conversations: [Conversation]) {
        let valid = Set(conversations.filter { entry(for: $0) != nil }.map(\.id))
        let next = entries.filter { valid.contains($0.key) }
        if next != entries { entries = next; save() }
    }

    private func save() { if let data = try? JSONEncoder().encode(entries) { defaults.set(data, forKey: key) } }
}

extension AppModel {
    var unreadConversations: [Conversation] {
        listedConversations.filter { responseAttention.entry(for: $0) != nil }
            .sorted { $0.updatedAt > $1.updatedAt }
    }

    func openUnreadResponse(_ conversation: Conversation) {
        guard canNavigateConversations, let entry = responseAttention.entry(for: conversation), presentations.dismissAll() else { return }
        returnToConversation(conversation.id, messageID: entry.messageID)
        presentations.reveal()
    }
}

struct ResponseAttentionMark: View {
    let entry: ResponseAttention.Entry
    var body: some View {
        Group {
            if entry.needsAttention { Image(systemName: "exclamationmark.circle.fill").foregroundStyle(.orange) }
            else { Circle().fill(.teal).frame(width: 7, height: 7) }
        }.font(.system(size: 11)).frame(width: 14, height: 16)
            .help(entry.label).accessibilityLabel(entry.label)
    }
}

struct CoreResponseBadge: View {
    @ObservedObject var app: AppModel
    var body: some View {
        let unread = app.unreadConversations
        if !unread.isEmpty {
            Menu {
                ForEach(unread) { conversation in
                    if let entry = app.responseAttention.entry(for: conversation) {
                        Button { app.openUnreadResponse(conversation) } label: {
                            Label(conversation.displayTitle + " · " + entry.label,
                                  systemImage: entry.needsAttention ? "exclamationmark.circle" : "bubble.right")
                        }.disabled(!app.canNavigateConversations)
                    }
                }
            } label: { Image(systemName: "circle.fill").opacity(0) }
                .menuStyle(.borderlessButton).menuIndicator(.hidden).frame(width: 30, height: 30)
                .overlay {
                    Text(unread.count > 99 ? "99+" : String(unread.count))
                        .font(.system(size: 10, weight: .semibold, design: .rounded)).foregroundStyle(.white)
                        .padding(.horizontal, 5).frame(minWidth: 20, minHeight: 20)
                        .background(unread.contains { app.responseAttention.entry(for: $0)?.needsAttention == true } ? Color.orange : .teal, in: Capsule())
                        .overlay(Capsule().strokeBorder(.black.opacity(0.2)))
                        .allowsHitTesting(false).accessibilityHidden(true)
                }
                .help(L10n.pick("Непрочитанные результаты", "Unread results"))
                .accessibilityLabel(L10n.pick("Непрочитанные результаты", "Unread results"))
                .accessibilityValue(String(unread.count))
        }
    }
}

/// Only the visible end of a response in an active reader acknowledges it.
/// A mounted hidden tab, a covered chat, and a nonactivating cube peek do not.
struct ResponseReadMarker: View {
    @ObservedObject var app: AppModel
    let conversationID: UUID?
    let messageID: UUID
    @Environment(\.isEnabled) private var enabled
    @Environment(\.workspacePresentations) private var presentations

    var body: some View {
        if let id = conversationID, app.responseAttention.entries[id]?.messageID == messageID {
            ResponseReadProbe(allowed: { enabled && presentations?.pages.isEmpty != false }, read: {
                app.responseAttention.acknowledge(conversationID: id, messageID: messageID)
            })
        }
    }
}

struct ResponseReadProbe: NSViewRepresentable {
    let allowed: () -> Bool
    let read: () -> Void
    func makeNSView(context: Context) -> ResponseReadView { ResponseReadView() }
    func updateNSView(_ view: ResponseReadView, context: Context) { view.allowed = allowed; view.read = read }
    static func dismantleNSView(_ view: ResponseReadView, coordinator: ()) { view.stop() }
}

final class ResponseReadView: NSView {
    var allowed: () -> Bool = { false }
    var read: () -> Void = {}
    private var timer: Timer?
    private var visibleSince: Date?
    override func hitTest(_ point: NSPoint) -> NSView? { nil }
    override func viewDidMoveToWindow() {
        super.viewDidMoveToWindow()
        stop()
        guard window != nil else { return }
        // A few pending response footers at most; no display-link or idle animation.
        let timer = Timer(timeInterval: 0.25, repeats: true) { [weak self] _ in
            MainActor.assumeIsolated { self?.checkVisibility() }
        }
        self.timer = timer
        RunLoop.main.add(timer, forMode: .common)
    }
    var readable: Bool {
        guard allowed(), NSApp.isActive, let window, window.isKeyWindow, window.isVisible,
              !window.isMiniaturized, window.alphaValue > 0.95, window.occlusionState.contains(.visible),
              !isHiddenOrHasHiddenAncestor, bounds.width > 0, bounds.height > 0 else { return false }
        let visible = visibleRect.intersection(bounds)
        return visible.width >= min(bounds.width, 20) && visible.height >= min(bounds.height, 12)
    }
    private func checkVisibility() {
        guard readable else { visibleSince = nil; return }
        let now = Date()
        if let visibleSince, now.timeIntervalSince(visibleSince) >= 0.65 { stop(); read() }
        else if visibleSince == nil { visibleSince = now }
    }
    func stop() { timer?.invalidate(); timer = nil; visibleSince = nil }
    deinit { timer?.invalidate() }
}
