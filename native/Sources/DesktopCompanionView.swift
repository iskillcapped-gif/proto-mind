import AppKit
import SwiftUI

struct DesktopCompanionView: View {
    @ObservedObject var app: AppModel
    @ObservedObject var owner: DesktopCompanionWindows
    @ObservedObject var surface: DesktopCompanion
    @ObservedObject private var chrome: WorkspacePanelChrome
    @Environment(\.accessibilityVoiceOverEnabled) private var voiceOver

    init(app: AppModel, owner: DesktopCompanionWindows, surface: DesktopCompanion) {
        self.app = app; self.owner = owner; self.surface = surface
        self.chrome = surface.chrome
    }

    var body: some View {
        VStack(spacing: 0) {
            HStack(spacing: 6) {
                Image(systemName: "rectangle").font(.system(size: 11))
                Text(surface.id.title).font(.system(size: 11, weight: .medium))
                CompanionDragArea(owner: owner, id: surface.id).frame(maxWidth: .infinity).frame(height: 30)
                Button { owner.restoreBase(surface.id) } label: {
                    Image(systemName: "arrow.uturn.backward").frame(width: 26, height: 28)
                }.help(surface.id == .first ? "Вернуть наверх справа · исходный размер" : "Вернуть вниз справа · исходный размер")
                    .accessibilityLabel("Вернуть на место · " + surface.id.title)
                Button { owner.toggle(surface.id) } label: { Image(systemName: "xmark").frame(width: 24, height: 28) }
                    .help("Скрыть окно").accessibilityLabel("Скрыть · " + surface.id.title)
            }.frame(height: 34).foregroundStyle(.secondary).buttonStyle(.nativeHover)
                .padding(.leading, surface.id == .second ? 32 : 16).padding(.trailing, 8).padding(.top, 4)
                .workspacePanelHeader()
            WorkspacePanelView(model: app, panel: surface.panel, position: surface.id.position,
                controls: WorkspacePanelControls(title: surface.id.title, activate: { owner.pinPreview() }, expand: { owner.toggleExpansion(surface.id) }))
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
                    .help("Изменить высоту боковых окон")
                    .accessibilityElement().accessibilityLabel("Высота боковых окон")
                    .accessibilityValue("Верхнее окно \(Int(owner.topFraction * 100)) процентов")
                    .accessibilityAdjustableAction { direction in
                        owner.setTopFraction(owner.topFraction + (direction == .increment ? 0.05 : -0.05))
                    }
            }
        }
        .background(CompanionHoverRegion(owner: owner, id: surface.id))
        .environment(\.desktopGlass, true)
        .environment(\.workspaceChrome, chrome)
        .environment(\.workspaceChromeVisible, surface.expanded || chrome.visible || voiceOver)
        .onExitCommand {
            if surface.expanded { owner.toggleExpansion(surface.id) }
            else { owner.toggle(surface.id) }
        }
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
            .help(expanded ? "Вернуть размер" : "Развернуть окно")
            .accessibilityLabel((expanded ? "Свернуть · " : "Развернуть · ") + title)
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
