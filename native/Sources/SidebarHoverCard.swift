import AppKit
import SwiftUI

/// Where a sidebar row's hover card stands: just right of the sidebar column and centred on the
/// row, or left of the row when the screen has no room on the right; always inside the screen.
enum SidebarHoverCardPlacement {
    /// The rows sit 12 pt inside the sidebar, so the card starts 8 pt past the sidebar's edge.
    static let gap: CGFloat = 20

    static func frame(row: CGRect, size: CGSize, screen: CGRect) -> CGRect {
        let bounds = screen.insetBy(dx: 6, dy: 6)
        guard !bounds.isNull, bounds.width > 0, bounds.height > 0 else { return .zero }
        let width = min(size.width, bounds.width), height = min(size.height, bounds.height)
        var x = row.maxX + gap
        if x + width > bounds.maxX { x = row.minX - gap - width }
        x = min(max(x, bounds.minX), bounds.maxX - width)
        let y = min(max(row.midY - height / 2, bounds.minY), bounds.maxY - height)
        return CGRect(x: x, y: y, width: width, height: height)
    }
}

/// One card for the whole sidebar. It appears after a short rest on a row, moves at once to the
/// next row the pointer reaches, never takes focus or clicks, and hides on exit, click or scroll.
@MainActor
final class SidebarHoverCards: ObservableObject {
    static let delay: TimeInterval = 0.45
    static let maxWidth: CGFloat = 290

    private final class Panel: NSPanel {
        override var canBecomeKey: Bool { false }
        override var canBecomeMain: Bool { false }
    }

    private var panel: Panel?
    private weak var anchor: SidebarHoverCardAnchor.TrackingView?
    private var pending: DispatchWorkItem?
    private var monitor: Any?
    private var observers: [NSObjectProtocol] = []
    private var hiddenAt = Date.distantPast
    var visible: Bool { panel != nil }

    fileprivate func enter(_ view: SidebarHoverCardAnchor.TrackingView) {
        pending?.cancel()
        anchor = view
        let show = DispatchWorkItem { [weak self, weak view] in
            MainActor.assumeIsolated {
                guard let self, let view, self.anchor === view else { return }
                self.show(beside: view)
            }
        }
        pending = show
        // A card that is already out, or was just hidden by moving between rows, follows at once.
        // Rows passing under a still pointer while the list scrolls wait for the scrolling to stop.
        let scrolling = NSApp.currentEvent?.type == .scrollWheel
        let warm = !scrolling && (panel != nil || Date().timeIntervalSince(hiddenAt) < 0.35)
        if scrolling { hide() }
        DispatchQueue.main.asyncAfter(deadline: .now() + (warm ? 0 : Self.delay), execute: show)
    }

    fileprivate func exit(_ view: SidebarHoverCardAnchor.TrackingView) {
        guard anchor === view else { return }
        anchor = nil
        pending?.cancel(); pending = nil
        // The pointer may be crossing into the next row, whose entry takes the card over.
        DispatchQueue.main.async { [weak self] in
            if let self, self.anchor == nil { self.hide() }
        }
    }

    func hide() {
        pending?.cancel(); pending = nil
        if let monitor { NSEvent.removeMonitor(monitor) }
        monitor = nil
        observers.forEach(NotificationCenter.default.removeObserver); observers = []
        guard let panel else { return }
        self.panel = nil
        panel.orderOut(nil)
        panel.close()
        hiddenAt = Date()
    }

    private func show(beside view: SidebarHoverCardAnchor.TrackingView) {
        guard let window = view.window, window.isVisible, window.occlusionState.contains(.visible),
              let screen = window.screen, let card = view.card else { hide(); return }
        let row = window.convertToScreen(view.convert(view.bounds, to: nil))
        guard row.insetBy(dx: -1, dy: -1).contains(NSEvent.mouseLocation) else { hide(); return }
        let content = card().padding(.horizontal, 12).padding(.vertical, 9)
        let size = NSHostingController(rootView: content).sizeThatFits(in: CGSize(width: Self.maxWidth, height: 400))
        let frame = SidebarHoverCardPlacement.frame(row: row, size: CGSize(width: ceil(size.width), height: ceil(size.height)), screen: screen.visibleFrame)
        guard frame.width > 0, frame.height > 0 else { hide(); return }
        let root = AnyView(content
            .frame(width: frame.width, height: frame.height, alignment: .leading)
            .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 10, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 10, style: .continuous).strokeBorder(NativeTheme.hairline))
            .environment(\.colorScheme, window.effectiveAppearance.bestMatch(from: [.darkAqua, .aqua]) == .darkAqua ? .dark : .light))
        if let panel {
            (panel.contentView as? NSHostingView<AnyView>)?.rootView = root
            panel.setFrame(frame, display: true)
            return
        }
        let panel = Panel(contentRect: frame, styleMask: [.borderless, .nonactivatingPanel], backing: .buffered, defer: false)
        panel.isReleasedWhenClosed = false
        panel.isOpaque = false
        panel.backgroundColor = .clear
        panel.hasShadow = true
        panel.ignoresMouseEvents = true
        panel.level = .popUpMenu
        panel.collectionBehavior = [.transient, .ignoresCycle, .fullScreenAuxiliary]
        panel.appearance = window.effectiveAppearance
        panel.contentView = NSHostingView(rootView: root)
        self.panel = panel
        panel.orderFront(nil)
        monitor = NSEvent.addLocalMonitorForEvents(matching: [.scrollWheel, .leftMouseDown, .rightMouseDown, .otherMouseDown, .keyDown]) { [weak self] event in
            MainActor.assumeIsolated { self?.hide() }
            return event
        }
        for name in [NSWindow.willCloseNotification, NSWindow.didMoveNotification, NSWindow.didResizeNotification,
                     NSWindow.didMiniaturizeNotification, NSWindow.didChangeOcclusionStateNotification] {
            observers.append(NotificationCenter.default.addObserver(forName: name, object: window, queue: .main) { [weak self] _ in
                MainActor.assumeIsolated { self?.hide() }
            })
        }
        observers.append(NotificationCenter.default.addObserver(forName: .interfaceLanguageChanged, object: nil, queue: .main) { [weak self] _ in
            MainActor.assumeIsolated { self?.hide() }
        })
    }
}

/// Tracks the pointer over one row with an AppKit tracking area, which also reports the row's
/// frame on screen; the card content is built only when the card is shown.
struct SidebarHoverCardAnchor: NSViewRepresentable {
    let cards: SidebarHoverCards
    let card: () -> AnyView

    final class TrackingView: NSView {
        weak var cards: SidebarHoverCards?
        var card: (() -> AnyView)?
        override func hitTest(_ point: NSPoint) -> NSView? { nil }
        override func updateTrackingAreas() {
            super.updateTrackingAreas()
            trackingAreas.forEach(removeTrackingArea)
            addTrackingArea(NSTrackingArea(rect: .zero, options: [.mouseEnteredAndExited, .activeAlways, .inVisibleRect], owner: self))
        }
        override func mouseEntered(with event: NSEvent) { cards?.enter(self) }
        override func mouseExited(with event: NSEvent) { cards?.exit(self) }
        override func viewWillMove(toWindow newWindow: NSWindow?) {
            if newWindow == nil { cards?.exit(self) }
            super.viewWillMove(toWindow: newWindow)
        }
    }

    func makeNSView(context: Context) -> TrackingView {
        let view = TrackingView()
        view.cards = cards; view.card = card
        return view
    }

    func updateNSView(_ view: TrackingView, context: Context) {
        view.cards = cards; view.card = card
    }
}

/// The card itself: the whole title, the model and last activity, and what the chat is waiting on.
struct SidebarHoverCardView: View {
    let title: String
    let detail: String
    var status: (icon: String, text: String)? = nil

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(title).font(.system(size: 13, weight: .medium)).lineLimit(4).fixedSize(horizontal: false, vertical: true)
            Text(detail).font(.system(size: 11)).foregroundStyle(.secondary).lineLimit(1)
            if let status {
                Label(status.text, systemImage: status.icon).font(.system(size: 11)).foregroundStyle(.secondary).lineLimit(1)
            }
        }
    }
}

/// A one-line title that, while its row is hovered and the title does not fit, glides to show its
/// end and back; otherwise it is truncated as usual. Motion starts only after a short rest, so
/// rows passing under a still pointer while the list scrolls do not start it.
struct SidebarMarqueeText: View {
    let text: String
    let active: Bool
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var fullWidth: CGFloat = 0
    @State private var boxWidth: CGFloat = 0
    @State private var scrolling = false
    @State private var offset: CGFloat = 0

    private var overflow: CGFloat { max(0, fullWidth - boxWidth) }

    var body: some View {
        ZStack(alignment: .leading) {
            if scrolling {
                Text(text).lineLimit(1).fixedSize().offset(x: offset)
            } else {
                Text(text).lineLimit(1).truncationMode(.tail)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .clipped()
        .mask {
            if scrolling {
                HStack(spacing: 0) {
                    LinearGradient(colors: [.clear, .black], startPoint: .leading, endPoint: .trailing).frame(width: offset < 0 ? 8 : 0)
                    Rectangle()
                    LinearGradient(colors: [.black, .clear], startPoint: .leading, endPoint: .trailing).frame(width: 8)
                }
            } else { Rectangle() }
        }
        .background(GeometryReader { box in
            Color.clear.onAppear { boxWidth = box.size.width }.onChange(of: box.size.width) { _, width in boxWidth = width }
        })
        .background(alignment: .leading) {
            Text(text).lineLimit(1).fixedSize().hidden().accessibilityHidden(true)
                .background(GeometryReader { line in
                    Color.clear.onAppear { fullWidth = line.size.width }.onChange(of: line.size.width) { _, width in fullWidth = width }
                })
        }
        .task(id: active && overflow > 1 && !reduceMotion) {
            guard active, overflow > 1, !reduceMotion else {
                scrolling = false; offset = 0
                return
            }
            try? await Task.sleep(for: .milliseconds(600))
            guard !Task.isCancelled else { return }
            scrolling = true
            let distance = overflow + 8
            let duration = Double(distance) / 40 + 0.3
            while !Task.isCancelled {
                withAnimation(.easeInOut(duration: duration)) { offset = -distance }
                try? await Task.sleep(for: .seconds(duration + 1.2))
                guard !Task.isCancelled else { break }
                withAnimation(.easeInOut(duration: duration)) { offset = 0 }
                try? await Task.sleep(for: .seconds(duration + 1.2))
            }
        }
    }
}

/// Gives a row's content its own hover state without re-rendering the other rows.
struct SidebarRowHover<Content: View>: View {
    @ViewBuilder let content: (Bool) -> Content
    @State private var hovered = false

    var body: some View {
        content(hovered).onHover { next in if hovered != next { hovered = next } }
    }
}
