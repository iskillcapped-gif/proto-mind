import SwiftUI

/// The building blocks every Settings tab shares: a row with a title, a short explanation
/// and its controls on the right; a state badge; and a ⋯ menu for secondary actions.
struct SettingsRow<Trailing: View>: View {
    let title: String
    var detail: String? = nil
    var symbol: String? = nil
    var symbolColor: Color = .secondary
    @ViewBuilder var trailing: () -> Trailing

    var body: some View {
        HStack(spacing: 10) {
            if let symbol {
                Image(systemName: symbol).font(.system(size: 15)).foregroundStyle(symbolColor).frame(width: 20).accessibilityHidden(true)
            }
            VStack(alignment: .leading, spacing: 3) {
                Text(title)
                if let detail, !detail.isEmpty { Text(detail).font(.caption).foregroundStyle(.secondary).textSelection(.enabled) }
            }
            Spacer(minLength: 8)
            trailing()
        }
    }
}

extension SettingsRow where Trailing == EmptyView {
    init(title: String, detail: String? = nil, symbol: String? = nil, symbolColor: Color = .secondary) {
        self.init(title: title, detail: detail, symbol: symbol, symbolColor: symbolColor) { EmptyView() }
    }
}

/// A short state in a capsule: green when it works, orange when it needs the operator, gray when off.
struct StatusBadge: View {
    enum Tone { case on, attention, off }
    let text: String
    let tone: Tone

    private var color: Color {
        switch tone { case .on: return .green; case .attention: return .orange; case .off: return .secondary }
    }

    var body: some View {
        HStack(spacing: 5) {
            Circle().fill(color).frame(width: 6, height: 6)
            Text(text).lineLimit(1)
        }
        .font(.system(size: 11, weight: .medium)).foregroundStyle(tone == .off ? .secondary : .primary)
        .padding(.horizontal, 8).padding(.vertical, 3)
        .background(color.opacity(tone == .off ? 0.1 : 0.16), in: Capsule())
        .fixedSize()
    }
}

/// Secondary actions of a row; a right click on the row can offer the same items.
struct SettingsMoreMenu<Content: View>: View {
    @ViewBuilder var content: () -> Content

    var body: some View {
        Menu { content() } label: { Image(systemName: "ellipsis") }
            .menuStyle(.borderlessButton).menuIndicator(.hidden).fixedSize().help(L10n.text("Действия"))
    }
}

/// The explanation under a group of settings, in place of paragraphs between its controls.
struct SettingsFooter: View {
    let text: String
    init(_ text: String) { self.text = text }
    var body: some View { Text(text).font(.caption).foregroundStyle(.secondary) }
}

/// A message under a group of settings: an error in orange, anything else quietly.
struct SettingsNotice: View {
    let text: String
    var failed = true

    var body: some View {
        Label(text, systemImage: failed ? "exclamationmark.circle" : "checkmark.circle")
            .font(.caption).foregroundStyle(failed ? Color.orange : .secondary).textSelection(.enabled)
    }
}
