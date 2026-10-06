import AppKit
import SwiftUI

struct DesktopCompanionView: View {
    @ObservedObject var app: AppModel
    @ObservedObject var owner: DesktopCompanionWindows
    @ObservedObject var surface: DesktopCompanion
    @ObservedObject private var chrome: WorkspacePanelChrome
    @ObservedObject private var presentations: WorkspacePresentations
    @Environment(\.accessibilityVoiceOverEnabled) private var voiceOver
    /// The small window previews its content as laid out in the expanded one. A page opened inside
    /// it and VoiceOver keep the content usable at its own size.
    private var miniature: Bool { !surface.expanded && presentations.pages.isEmpty && !voiceOver }

    init(app: AppModel, owner: DesktopCompanionWindows, surface: DesktopCompanion) {
        self.app = app; self.owner = owner; self.surface = surface
        self.chrome = surface.chrome
        self.presentations = surface.presentations
    }

    var body: some View {
        VStack(spacing: 0) {
            HStack(spacing: 6) {
                Image(systemName: "rectangle").font(.system(size: 11))
                Text(surface.id.title).font(.system(size: 11, weight: .medium))
                CompanionDragArea(owner: owner, id: surface.id).frame(maxWidth: .infinity).frame(height: 30)
                Button { owner.toggleExpansion(surface.id) } label: {
                    Image(systemName: surface.expanded ? "arrow.down.right.and.arrow.up.left" : "arrow.up.left.and.arrow.down.right")
                        .frame(width: 26, height: 28)
                }.help(surface.expanded ? L10n.text("Вернуть миниатюру") : L10n.text("Развернуть окно"))
                    .accessibilityLabel((surface.expanded ? L10n.text("Миниатюра · ") : L10n.text("Развернуть окно · ")) + surface.id.title)
                Button { owner.restoreBase(surface.id) } label: {
                    Image(systemName: "arrow.uturn.backward").frame(width: 26, height: 28)
                }.help(surface.id == .first ? L10n.text("Вернуть наверх справа · исходный размер") : L10n.text("Вернуть вниз справа · исходный размер"))
                    .accessibilityLabel(L10n.text("Вернуть на место · ") + surface.id.title)
                Button { owner.toggle(surface.id) } label: { Image(systemName: "xmark").frame(width: 24, height: 28) }
                    .help(L10n.text("Скрыть окно")).accessibilityLabel(L10n.text("Скрыть · ") + surface.id.title)
            }.frame(height: 34).foregroundStyle(.secondary).buttonStyle(.nativeHover)
                .padding(.leading, surface.id == .second ? 32 : 16).padding(.trailing, 8).padding(.top, 4)
                .workspacePanelHeader()
            CompanionMiniature(active: miniature,
                               reference: surface.expandedSize.map { CGSize(width: $0.width, height: $0.height - Self.headerHeight) },
                               expand: { owner.toggleExpansion(surface.id) }) {
                WorkspacePresentationHost(presentations: presentations, backTitle: L10n.text("К окну")) {
                    WorkspacePanelView(model: app, panel: surface.panel, position: surface.id.position,
                        controls: WorkspacePanelControls(title: surface.id.title, activate: { owner.pinPreview() }))
                }
                // The miniature is the page alone: hovering shows the window's own header row,
                // not the tab and browser bars inside a preview that cannot be used.
                .environment(\.workspaceChromeVisible, miniature ? false : surface.expanded || chrome.visible || voiceOver || !presentations.pages.isEmpty)
            }
        }
        .background(DesktopGlassBackground(transparency: surface.transparency, tint: NativeTheme.canvas))
        .clipShape(RoundedRectangle(cornerRadius: 20, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: 20, style: .continuous)
                .strokeBorder(surface.dockingSuggested ? Color.teal.opacity(0.8) : .white.opacity(0.15), lineWidth: surface.dockingSuggested ? 2 : 1)
                .allowsHitTesting(false)
        }
        .overlay(alignment: surface.id == .first ? .bottomLeading : .topLeading) {
            CompanionCornerControl(upperCorner: surface.id == .second, expanded: surface.expanded,
                title: surface.id.title) { owner.toggleExpansion(surface.id) }
        }
        .overlay(alignment: surface.id == .first ? .bottom : .top) {
            if owner.hasStack {
                CompanionSplitHandle(owner: owner).frame(height: 7).padding(.horizontal, 38)
                    .help(L10n.text("Изменить высоту боковых окон"))
                    .accessibilityElement().accessibilityLabel(L10n.text("Высота боковых окон"))
                    .accessibilityValue(L10n.format("Верхнее окно \(Int(owner.topFraction * 100)) процентов"))
                    .accessibilityAdjustableAction { direction in
                        owner.setTopFraction(owner.topFraction + (direction == .increment ? 0.05 : -0.05))
                    }
            }
        }
        .background(CompanionHoverRegion(owner: owner, id: surface.id))
        .environment(\.desktopGlass, true)
        .environment(\.workspaceChrome, chrome)
        .environment(\.workspacePresentations, presentations)
        .environment(\.locale, L10n.locale)
        .environment(\.workspaceChromeVisible, surface.expanded || chrome.visible || voiceOver || !presentations.pages.isEmpty)
        .onChange(of: miniature) { _, small in
            // Typing must not continue into a field that is now a tiny, inert preview.
            if small, let window = surface.window, let responder = window.firstResponder as? NSView,
               responder !== window.contentView { window.makeFirstResponder(nil) }
        }
        .onExitCommand {
            if !presentations.pages.isEmpty { presentations.dismissTop() }
            else if surface.expanded { owner.toggleExpansion(surface.id) }
            else { owner.toggle(surface.id) }
        }
    }
}

extension DesktopCompanionView {
    /// The header row above the content: 34 pt plus its 4 pt top padding.
    static let headerHeight: CGFloat = 38
}

/// In the small window, the content as it looks in the expanded one, scaled down to fit and not
/// interactive; a click expands the window. Expanded, it is laid out and used as usual. The same
/// view stays in place either way, so tabs, sessions and scroll positions are kept.
struct CompanionMiniature<Content: View>: View {
    let active: Bool
    let reference: CGSize?
    let expand: () -> Void
    @ViewBuilder let content: Content

    var body: some View {
        GeometryReader { proxy in
            let size = proxy.size
            let layout = active ? Self.layout(for: size, reference: reference) : size
            let scale = layout.width > 0 && layout.height > 0 ? min(1, size.width / layout.width, size.height / layout.height) : 1
            content
                .frame(width: layout.width, height: layout.height)
                .scaleEffect(scale, anchor: .topLeading)
                .frame(width: size.width, height: size.height, alignment: .topLeading)
                .clipped()
                .allowsHitTesting(!active)
                .overlay {
                    if active {
                        Color.clear.contentShape(Rectangle()).onTapGesture(perform: expand)
                            .accessibilityElement().accessibilityLabel(L10n.text("Развернуть окно")).accessibilityAddTraits(.isButton)
                    }
                }
        }
    }

    /// The expanded layout when it is larger than the small window; otherwise the window itself.
    static func layout(for size: CGSize, reference: CGSize?) -> CGSize {
        guard let reference, reference.width > size.width || reference.height > size.height,
              reference.width > 0, reference.height > 0 else { return size }
        return CGSize(width: max(reference.width, size.width), height: max(reference.height, size.height * reference.width / max(size.width, 1)))
    }
}

struct CompanionSplitHandle: NSViewRepresentable {
    let owner: DesktopCompanionWindows
    func makeNSView(context: Context) -> ResizeArea { let view = ResizeArea(); view.owner = owner; return view }
    func updateNSView(_ view: ResizeArea, context: Context) { view.owner = owner }
    final class ResizeArea: NSView {
        weak var owner: DesktopCompanionWindows?
        private var startY: CGFloat = 0
        private var startHeight: CGFloat = 0
        override func acceptsFirstMouse(for event: NSEvent?) -> Bool { true }
        override var mouseDownCanMoveWindow: Bool { false }
        override func resetCursorRects() { addCursorRect(bounds, cursor: .resizeUpDown) }
        override func mouseDown(with event: NSEvent) {
            owner?.pinPreview()
            startY = DesktopPointer.screenLocation(of: event, in: window).y
            startHeight = owner?.topHeight ?? 0
        }
        override func mouseDragged(with event: NSEvent) {
            let point = DesktopPointer.screenLocation(of: event, in: window)
            owner?.resizeStack(topHeight: startHeight + startY - point.y)
        }
    }
}

/// The corner itself lights up; the hit target stays reachable by keyboard and accessibility.
struct CompanionCornerControl: View {
    let upperCorner: Bool
    let expanded: Bool
    let title: String
    let action: () -> Void
    @State private var hovered = false
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    var body: some View {
        Button(action: action) {
            CornerShape().fill(LinearGradient(colors: [.white.opacity(0.62), .white.opacity(0.05), .clear], startPoint: .topLeading, endPoint: .bottomTrailing))
                .overlay(alignment: .topLeading) {
                    CornerShape().stroke(.white.opacity(0.4), lineWidth: 0.6)
                }
                .rotationEffect(.degrees(upperCorner ? 0 : -90))
                .opacity(hovered ? 1 : 0)
                .frame(width: 32, height: 32).contentShape(Rectangle())
        }.buttonStyle(.plain).padding(2)
            .onHover { hovered = $0 }
            .animation(reduceMotion ? nil : .easeOut(duration: 0.14), value: hovered)
            .help(expanded ? L10n.text("Вернуть размер") : L10n.text("Развернуть окно"))
            .accessibilityLabel((expanded ? L10n.text("Свернуть · ") : L10n.text("Развернуть · ")) + title)
    }
    private struct CornerShape: Shape {
        func path(in rect: CGRect) -> Path {
            Path { path in
                path.move(to: CGPoint(x: rect.minX + 1, y: rect.maxY))
                path.addLine(to: CGPoint(x: rect.minX + 1, y: rect.minY + 18))
                path.addQuadCurve(to: CGPoint(x: rect.minX + 18, y: rect.minY + 1), control: CGPoint(x: rect.minX + 1, y: rect.minY + 1))
                path.addLine(to: CGPoint(x: rect.maxX, y: rect.minY + 1))
                path.closeSubpath()
            }
        }
    }
}

struct CompanionDragArea: NSViewRepresentable {
    let owner: DesktopCompanionWindows
    let id: DesktopCompanionID
    func makeNSView(context: Context) -> DragArea { let view = DragArea(); view.owner = owner; view.id = id; return view }
    func updateNSView(_ view: DragArea, context: Context) { view.owner = owner; view.id = id }
    final class DragArea: NSView {
        weak var owner: DesktopCompanionWindows?
        var id: DesktopCompanionID = .first
        private var startPoint = NSPoint.zero
        private var startFrame = NSRect.zero
        private var dragged = false
        private let chromeHold = UUID()
        override var mouseDownCanMoveWindow: Bool { false }
        override func acceptsFirstMouse(for event: NSEvent?) -> Bool { true }
        override func resetCursorRects() { addCursorRect(bounds, cursor: .openHand) }
        override func mouseDown(with event: NSEvent) {
            owner?.pinPreview()
            owner?.surface(id).chrome.hold(chromeHold, while: true)
            startPoint = DesktopPointer.screenLocation(of: event, in: window)
            startFrame = window?.frame ?? .zero; dragged = false
        }
        override func mouseDragged(with event: NSEvent) {
            let point = DesktopPointer.screenLocation(of: event, in: window)
            let dx = point.x - startPoint.x, dy = point.y - startPoint.y
            guard dragged || hypot(dx, dy) >= 4 else { return }
            if !dragged { owner?.beginDrag(id) }
            dragged = true
            window?.setFrameOrigin(NSPoint(x: startFrame.minX + dx, y: startFrame.minY + dy))
        }
        override func mouseUp(with event: NSEvent) {
            if dragged { owner?.endDrag(id) }
            dragged = false
            owner?.surface(id).chrome.hold(chromeHold, while: false)
        }
    }
}

struct CompanionHoverRegion: NSViewRepresentable {
    let owner: DesktopCompanionWindows
    let id: DesktopCompanionID
    func makeNSView(context: Context) -> TrackingView { let view = TrackingView(); view.owner = owner; view.id = id; return view }
    func updateNSView(_ view: TrackingView, context: Context) { view.owner = owner; view.id = id }
    final class TrackingView: NSView {
        weak var owner: DesktopCompanionWindows?
        var id: DesktopCompanionID = .first
        private var area: NSTrackingArea?
        override func hitTest(_ point: NSPoint) -> NSView? { nil }
        override func updateTrackingAreas() {
            super.updateTrackingAreas()
            if let area { removeTrackingArea(area) }
            let next = NSTrackingArea(rect: bounds, options: [.mouseEnteredAndExited, .activeAlways, .inVisibleRect], owner: self, userInfo: nil)
            addTrackingArea(next); area = next
        }
        override func mouseEntered(with event: NSEvent) { owner?.updateHover(id, inside: true) }
        override func mouseExited(with event: NSEvent) { owner?.updateHover(id, inside: false) }
        override func viewDidMoveToWindow() { super.viewDidMoveToWindow(); if window == nil { owner?.updateHover(id, inside: false) } }
    }
}
