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
    private var scrollMonitor: Any?
    private var hoverObservers: [NSObjectProtocol] = []
    private var observers: [NSObjectProtocol] = []
    private var hiddenAt = Date.distantPast
    var visible: Bool { panel != nil }

    fileprivate func enter(_ view: SidebarHoverCardAnchor.TrackingView) {
        pending?.cancel()
        if let previous = anchor, previous !== view { previous.hover?(false) }
        anchor = view
        view.hover?(true)
        if scrollMonitor == nil {
            // Rows move under a still pointer while the list scrolls, and AppKit may report the
            // exit only on the next mouse move: the hovered row lets go of its title and card now.
            scrollMonitor = NSEvent.addLocalMonitorForEvents(matching: .scrollWheel) { [weak self] event in
                MainActor.assumeIsolated { self?.release() }
                return event
            }
            // A hidden or folded window sends no exit either.
            for name in [NSWindow.didChangeOcclusionStateNotification, NSWindow.willCloseNotification, NSWindow.didMiniaturizeNotification] {
                hoverObservers.append(NotificationCenter.default.addObserver(forName: name, object: view.window, queue: .main) { [weak self] _ in
                    MainActor.assumeIsolated { self?.release() }
                })
            }
        }
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
        view.hover?(false)
        anchor = nil
        pending?.cancel(); pending = nil
        // The pointer may be crossing into the next row, whose entry takes the card over.
        DispatchQueue.main.async { [weak self] in
            if let self, self.anchor == nil { self.release() }
        }
    }

    /// No row is hovered any more: its title stops gliding and the card goes.
    func release() {
        anchor?.hover?(false)
        anchor = nil
        if let scrollMonitor { NSEvent.removeMonitor(scrollMonitor) }
        scrollMonitor = nil
        hoverObservers.forEach(NotificationCenter.default.removeObserver); hoverObservers = []
        hide()
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
    let hover: (Bool) -> Void

    final class TrackingView: NSView {
        weak var cards: SidebarHoverCards?
        var card: (() -> AnyView)?
        var hover: ((Bool) -> Void)?
        override func hitTest(_ point: NSPoint) -> NSView? { nil }
        override func updateTrackingAreas() {
            super.updateTrackingAreas()
            trackingAreas.forEach(removeTrackingArea)
            addTrackingArea(NSTrackingArea(rect: .zero, options: [.mouseEnteredAndExited, .activeAlways, .inVisibleRect], owner: self))
        }
        override func mouseEntered(with event: NSEvent) { cards?.enter(self) }
        override func mouseExited(with event: NSEvent) { cards?.exit(self) }
        override func viewWillMove(toWindow newWindow: NSWindow?) {
            // A row being removed takes its hover state with it; SwiftUI state is not written during removal.
            if newWindow == nil { hover = nil; cards?.exit(self) }
            super.viewWillMove(toWindow: newWindow)
        }
    }

    func makeNSView(context: Context) -> TrackingView {
        let view = TrackingView()
        view.cards = cards; view.card = card; view.hover = hover
        return view
    }

    func updateNSView(_ view: TrackingView, context: Context) {
        view.cards = cards; view.card = card; view.hover = hover
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

/// A one-line title that glides left like a ticker while its row is hovered and the title does not
/// fit, and snaps back to its start when the pointer leaves; otherwise it is truncated as usual.
/// The truncated title always sets the layout and the moving copy is an overlay, so gliding never
/// changes the row's size or the measurement that decides whether to glide.
struct SidebarMarqueeText: View {
    static let gap: CGFloat = 36
    /// Points per second.
    static let speed: Double = 36
    let text: String
    let active: Bool
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var fullWidth: CGFloat = 0
    @State private var boxWidth: CGFloat = 0
    @State private var gliding = false
    @State private var offset: CGFloat = 0

    private var fits: Bool { fullWidth <= boxWidth + 0.5 }

    var body: some View {
        Text(text).lineLimit(1).truncationMode(.tail)
            .opacity(gliding ? 0 : 1)
            .frame(maxWidth: .infinity, alignment: .leading)
            .overlay(alignment: .leading) {
                if gliding {
                    HStack(spacing: Self.gap) { Text(text); Text(text) }
                        .lineLimit(1).fixedSize().offset(x: offset).accessibilityHidden(true)
                }
            }
            .clipped()
            .mask {
                if gliding {
                    HStack(spacing: 0) {
                        LinearGradient(colors: [.clear, .black], startPoint: .leading, endPoint: .trailing).frame(width: offset < 0 ? 6 : 0)
                        Rectangle()
                        LinearGradient(colors: [.black, .clear], startPoint: .leading, endPoint: .trailing).frame(width: 10)
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
            .task(id: active && !fits && !reduceMotion) {
                guard active, !fits, !reduceMotion else { stop(); return }
                try? await Task.sleep(for: .milliseconds(350))
                guard !Task.isCancelled else { return }
                gliding = true
                let distance = fullWidth + Self.gap
                let duration = Double(distance) / Self.speed
                while !Task.isCancelled {
                    withAnimation(.linear(duration: duration)) { offset = -distance }
                    try? await Task.sleep(for: .seconds(duration))
                    guard !Task.isCancelled else { break }
                    // The second copy now stands where the first began: rest a moment, then again.
                    jump { offset = 0 }
                    try? await Task.sleep(for: .seconds(1))
                }
            }
    }

    private func stop() { jump { gliding = false; offset = 0 } }

    private func jump(_ change: () -> Void) {
        var transaction = Transaction()
        transaction.disablesAnimations = true
        withTransaction(transaction, change)
    }
}

/// A sidebar row whose one AppKit tracking area drives both its gliding title and its hover card,
/// so the title stops exactly when the pointer leaves, the list scrolls or the window hides.
struct SidebarHoverRow<Content: View>: View {
    let cards: SidebarHoverCards
    let card: () -> AnyView
    @ViewBuilder let content: (Bool) -> Content
    @State private var hovered = false

    var body: some View {
        content(hovered).background(SidebarHoverCardAnchor(cards: cards, card: card) { next in
            if hovered != next { hovered = next }
        })
    }
}
