import AppKit
import SwiftUI

/// Find in the open chat (⌘F). Matches are whole messages, newest first: the first match is the
/// latest one, and "next" goes further back, as in messengers. The current match is scrolled to and
/// marked like any other jump in the transcript; the words themselves are highlighted.
@MainActor
final class ChatFindModel: ObservableObject {
    /// The chat the bar is open in; nil while it is closed.
    @Published private(set) var conversationID: UUID?
    @Published var query = "" { didSet { if query != oldValue { scheduleSearch() } } }
    /// The query the matches were found for. Highlighting follows it rather than each keystroke.
    @Published private(set) var applied = ""
    @Published private(set) var matches: [UUID] = []
    @Published private(set) var current = 0
    @Published private(set) var focusRequest = 0
    private weak var app: AppModel?
    private var pending: Task<Void, Never>?

    var visible: Bool { conversationID != nil }
    var currentMatch: UUID? { matches.indices.contains(current) ? matches[current] : nil }

    func open(_ id: UUID, app: AppModel) {
        self.app = app
        if conversationID != id { conversationID = id; search(jump: !query.isEmpty) }
        focusRequest += 1
    }

    func close() {
        pending?.cancel()
        conversationID = nil; applied = ""; matches = []; current = 0
    }

    /// Earlier in the chat: Return, ↑ or ⌘G.
    func next() { step(1) }
    /// Later in the chat: ⇧Return, ↓ or ⇧⌘G.
    func previous() { step(-1) }

    private func step(_ delta: Int) {
        guard !matches.isEmpty else { return }
        current = (current + delta + matches.count) % matches.count
        jump()
    }

    private func scheduleSearch() {
        pending?.cancel()
        guard visible else { return }
        pending = Task { [weak self] in
            try? await Task.sleep(for: .milliseconds(160))
            guard !Task.isCancelled else { return }
            self?.search(jump: true)
        }
    }

    /// Finds the query in the chat again. Without a jump, e.g. after a new message, the current
    /// match stays current while it still matches.
    func search(jump: Bool) {
        guard let id = conversationID, let chat = app?.conversations.first(where: { $0.id == id }) else { return }
        let query = query.trimmingCharacters(in: .whitespacesAndNewlines)
        let kept = currentMatch
        applied = query
        matches = query.isEmpty ? [] : chat.messages.reversed().filter { Self.contains($0.searchableText, query) }.map(\.id)
        current = jump ? 0 : kept.flatMap { matches.firstIndex(of: $0) } ?? 0
        if jump { self.jump() }
    }

    private func jump() {
        guard let app, let id = conversationID, let match = currentMatch else { return }
        app.transcriptDestination = TranscriptDestination(conversationID: id, messageID: match)
    }

    nonisolated static func contains(_ text: String, _ query: String) -> Bool {
        text.range(of: query, options: [.caseInsensitive, .diacriticInsensitive]) != nil
    }

    /// The text with every occurrence of the query marked as macOS marks found text.
    nonisolated static func highlighted(_ text: AttributedString, _ query: String) -> AttributedString {
        guard !query.isEmpty else { return text }
        var result = text
        var start = result.startIndex
        while start < result.endIndex,
              let range = result[start...].range(of: query, options: [.caseInsensitive, .diacriticInsensitive]), !range.isEmpty {
            result[range].backgroundColor = Color(nsColor: .findHighlightColor)
            result[range].foregroundColor = .black
            start = range.upperBound
        }
        return result
    }
}

extension AppModel {
    /// ⌘F: the find bar over the open chat, revealing the chat first.
    func openChatFind() {
        guard let id = selectedID, presentations.pages.isEmpty else { return }
        if desktop.enabled && !desktop.expanded { desktop.revealWorkspace() }
        if section != .chat && section != .workspace { section = .chat }
        chatFind.open(id, app: self)
    }
}

/// The bar above the transcript: the query, which match of how many, and the way to the others.
struct ChatFindBar: View {
    @ObservedObject var find: ChatFindModel
    @FocusState private var focused: Bool

    var body: some View {
        HStack(spacing: 6) {
            Image(systemName: "magnifyingglass").foregroundStyle(.secondary).accessibilityHidden(true)
            TextField(L10n.pick("Найти в чате", "Find in chat"), text: $find.query)
                .textFieldStyle(.plain).focused($focused)
                .onSubmit { find.next() }
                .onKeyPress(keys: [.upArrow, .downArrow, .return]) { press in
                    switch press.key {
                    case .upArrow: find.next()
                    case .downArrow: find.previous()
                    default:
                        guard press.modifiers.contains(.shift) else { return .ignored }
                        find.previous()
                    }
                    return .handled
                }
                .onExitCommand { find.close() }
            if !status.isEmpty {
                Text(status).font(.system(size: 11.5)).monospacedDigit().foregroundStyle(.secondary).fixedSize()
            }
            Group {
                Button { find.next() } label: { Image(systemName: "chevron.up").frame(width: 22, height: 22) }
                    .help(L10n.pick("Раньше · Return или ⌘G", "Earlier · Return or ⌘G"))
                    .accessibilityLabel(L10n.pick("Совпадение раньше", "Earlier match"))
                Button { find.previous() } label: { Image(systemName: "chevron.down").frame(width: 22, height: 22) }
                    .help(L10n.pick("Позже · ⇧Return или ⇧⌘G", "Later · ⇧Return or ⇧⌘G"))
                    .accessibilityLabel(L10n.pick("Совпадение позже", "Later match"))
            }.disabled(find.matches.isEmpty)
            Button(L10n.pick("Готово", "Done")) { find.close() }
                .help(L10n.pick("Закрыть поиск · Esc", "Close find · Esc"))
        }
        .font(.system(size: 13)).buttonStyle(.nativeHover(minSize: 24, cornerRadius: 6))
        .padding(.leading, 12).padding(.trailing, 6).padding(.vertical, 6)
        .background(NativeTheme.composer, in: RoundedRectangle(cornerRadius: 12))
        .overlay(RoundedRectangle(cornerRadius: 12).stroke(NativeTheme.hairline))
        .shadow(color: .black.opacity(0.08), radius: 6, y: 2)
        .onAppear { focused = true }
        .onChange(of: find.focusRequest) { _, _ in focused = true }
    }

    private var status: String {
        guard !find.applied.isEmpty else { return "" }
        guard !find.matches.isEmpty else { return L10n.pick("Не найдено", "Not found") }
        return L10n.pick("\(find.current + 1) из \(find.matches.count)", "\(find.current + 1) of \(find.matches.count)")
    }
}

/// Edit menu: find in the open chat and step through the matches.
struct ChatFindCommands: View {
    let app: AppModel
    @ObservedObject var find: ChatFindModel

    var body: some View {
        Button(L10n.pick("Найти в чате…", "Find in Chat…")) { app.openChatFind() }
            .keyboardShortcut("f")
        Button(L10n.pick("Найти раньше", "Find Earlier")) { find.next() }
            .keyboardShortcut("g").disabled(find.matches.isEmpty)
        Button(L10n.pick("Найти позже", "Find Later")) { find.previous() }
            .keyboardShortcut("g", modifiers: [.command, .shift]).disabled(find.matches.isEmpty)
    }
}
