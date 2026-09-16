import AppKit
import Combine
import CryptoKit
import SwiftUI

@MainActor
final class DesktopCompanion: ObservableObject, Identifiable {
    let id: DesktopCompanionID
    let panel = WorkspacePanelModel()
    let chrome = WorkspacePanelChrome()
    let presentations = WorkspacePresentations()
    @Published fileprivate(set) var visible = false
    @Published fileprivate(set) var docked = true
    @Published fileprivate(set) var expanded = false
    @Published fileprivate(set) var transparency = DesktopGlassAppearance.chatDefault
    @Published fileprivate(set) var dockingSuggested = false
    fileprivate(set) var window: DesktopCompanionPanel?
    fileprivate var delegate: DesktopCompanionDelegate?
    fileprivate var width: CGFloat = DesktopCompanionGeometry.defaultWidth
    fileprivate var appliedSize: NSSize?
    fileprivate var compactFrame: NSRect?
    fileprivate var expandedFrame: NSRect?
    fileprivate var dragging = false
    init(_ id: DesktopCompanionID) { self.id = id; panel.presentations = presentations }
}

/// Windows own geometry and visibility; their retained panel models own content and sessions.
@MainActor
final class DesktopCompanionWindows: ObservableObject {
    let surfaces = DesktopCompanionID.allCases.map(DesktopCompanion.init)
    private weak var desktop: DesktopPresentation?
    private weak var app: AppModel?
    private let defaults: UserDefaults
    private let key: String
    private let presentsWindows: Bool
    private var subscriptions: [AnyCancellable] = []
    private var layingOut = false
    private var workspaceHome: NSRect?
    private var lastRow: DesktopCompanionGeometry.Row?
    private var hovered: Set<DesktopCompanionID> = []
    @Published private(set) var topFraction: CGFloat = 0.5
    @Published private(set) var keepDetachedVisible = false

    init(stateDirectory: URL, defaults: UserDefaults = .standard, presentsWindows: Bool = true) {
        self.defaults = defaults; self.presentsWindows = presentsWindows
        key = "desktopCompanions.v1." + SHA256.hash(data: Data(stateDirectory.standardizedFileURL.path.utf8)).map { String(format: "%02x", $0) }.joined()
        let fraction = defaults.object(forKey: key + ".topFraction") as? Double ?? 0.5
        topFraction = fraction.isFinite ? min(0.9, max(0.1, fraction)) : 0.5
        keepDetachedVisible = defaults.bool(forKey: key + ".keepDetachedVisible")
        for surface in surfaces {
            let prefix = key + "." + surface.id.rawValue
            surface.visible = defaults.bool(forKey: prefix + ".visible")
            surface.docked = defaults.object(forKey: prefix + ".docked") as? Bool ?? true
            let width = defaults.object(forKey: prefix + ".width") as? Double ?? 380
            surface.width = width.isFinite ? max(280, min(1800, width)) : 380
            surface.transparency = DesktopGlassAppearance.normalized(defaults.object(forKey: prefix + ".transparency") as? Double ?? DesktopGlassAppearance.chatDefault, fallback: DesktopGlassAppearance.chatDefault)
            surface.compactFrame = savedFrame(prefix + ".compact")
            surface.expandedFrame = savedFrame(prefix + ".expanded")
        }
        subscriptions = surfaces.map { $0.objectWillChange.sink { [weak self] in self?.objectWillChange.send() } }
    }

    func surface(_ id: DesktopCompanionID) -> DesktopCompanion { surfaces.first { $0.id == id }! }
    func owns(_ window: NSWindow) -> Bool { surfaces.contains { $0.window === window } }
    /// Voice and explicitly independent free windows never join a workspace fade.
    var workspaceWindows: [NSWindow] {
        surfaces.filter { $0.visible && ($0.docked || !keepDetachedVisible) }
            .compactMap(\.window).filter { $0.isVisible || !presentsWindows }
    }
    func containsVisibleWindow(at point: NSPoint) -> Bool {
        surfaces.contains { $0.window.map { $0.isVisible && $0.frame.contains(point) } == true }
    }
    var preferredWorkspaceFrame: NSRect? { workspaceHome }
    var hasStack: Bool { surfaces.allSatisfy { $0.visible && $0.docked && !$0.expanded } }
    var topHeight: CGFloat { lastRow?.panels[.first]?.height ?? 0 }
    func resizeStack(topHeight: CGFloat) {
        guard hasStack, let workspace = desktop?.window else { return }
        setTopFraction(topHeight / max(2, workspace.frame.height - DesktopCompanionGeometry.gap))
    }
    var minimumWorkspaceWidth: CGFloat {
        let count = surfaces.filter { $0.visible && $0.docked }.count
        guard count > 0 else { return desktop?.enabled == true ? DesktopGeometry.minimumWorkspace.width : 940 }
        let bounds = screen(for: desktop?.window?.frame ?? .zero)
        return min(640, max(1, bounds.width - DesktopCompanionGeometry.gap) * 0.52)
    }
    func attach(desktop: DesktopPresentation, app: AppModel) {
        self.desktop = desktop; self.app = app
        for item in surfaces { app.presentations.register(item.presentations) }
    }

    func presentationSource(for window: NSWindow?) -> WorkspacePresentations? {
        var candidate = window
        while let window = candidate {
            if let item = surfaces.first(where: { $0.window === window }) { return item.presentations }
            candidate = window.sheetParent ?? window.parent
        }
        return nil
    }

    private func revealPresentation(_ id: DesktopCompanionID) {
        let item = surface(id)
        guard item.visible else { return }
        app?.dictation.stop()
        if item.docked {
            for other in surfaces where other.id != id && other.docked && other.expanded {
                other.expanded = false; other.panel.expanded = false
            }
        }
        // Raise the source window without using revealMainContent, which folds it.
        desktop?.revealWorkspace()
        layout()
        if presentsWindows { item.window?.makeKeyAndOrderFront(nil) }
    }

    func toggle(_ id: DesktopCompanionID) {
        let item = surface(id)
        item.visible.toggle()
        if !item.visible { item.expanded = false; item.panel.expanded = false; updateHover(id, inside: false) }
        save(item)
        if item.visible { desktop?.revealWorkspace() }
        layout()
        if item.visible && presentsWindows { item.window?.makeKeyAndOrderFront(nil) }
    }

    func setTransparency(_ value: Double, for id: DesktopCompanionID) {
        let item = surface(id)
        item.transparency = DesktopGlassAppearance.normalized(value, fallback: DesktopGlassAppearance.chatDefault)
        save(item)
    }

    func setKeepDetachedVisible(_ value: Bool) {
        keepDetachedVisible = value
        defaults.set(value, forKey: key + ".keepDetachedVisible")
        layout()
    }

    /// Both the header action and drag-to-attach use the same canonical reset.
    func restoreBase(_ id: DesktopCompanionID) {
        let item = surface(id)
        storeFreeFrame(item)
        item.visible = true; item.docked = true; item.dragging = false
        item.dockingSuggested = false
        topFraction = 0.5
        defaults.set(topFraction, forKey: key + ".topFraction")
        for sibling in surfaces where sibling.docked {
            sibling.width = DesktopCompanionGeometry.defaultWidth
            sibling.expanded = false; sibling.panel.expanded = false
            save(sibling)
        }
        // One layout applies both slots together, after clearing any covering expansion.
        desktop?.revealWorkspace()
        layout()
        if presentsWindows { item.window?.makeKeyAndOrderFront(nil) }
    }

    func detach(_ id: DesktopCompanionID) {
        let item = surface(id)
        guard item.docked else { return }
        let compact = lastRow?.panels[id] ?? item.window?.frame
        item.docked = false
        if item.expanded { item.expandedFrame = item.window?.frame }
        else if let compact, let previous = item.expandedFrame {
            // Reuse the size, never a position left over from an earlier docking.
            item.expandedFrame = DesktopCompanionGeometry.enlarged(compact, screen: screen(for: compact), preferredSize: previous.size)
        }
        item.compactFrame = compact
        save(item); layout()
    }

    func toggleExpansion(_ id: DesktopCompanionID) {
        let item = surface(id)
        guard item.visible else { return }
        if !item.docked { storeFreeFrame(item) }
        if item.docked && !item.expanded { collapseDockedExpansion() }
        item.expanded.toggle(); item.panel.expanded = item.expanded
        if !item.docked && item.expanded && item.expandedFrame == nil, let frame = item.window?.frame {
            item.expandedFrame = DesktopCompanionGeometry.enlarged(frame, screen: screen(for: frame))
        }
        save(item); layout()
        if presentsWindows { item.window?.makeKeyAndOrderFront(nil) }
    }

    func collapseDockedExpansion() {
        for item in surfaces where item.docked && item.expanded {
            item.expanded = false; item.panel.expanded = false
        }
        layout()
    }

    func parentChanged(resized: Bool = false) {
        guard !layingOut, let window = desktop?.window else { return }
        if workspaceHome != nil {
            workspaceHome?.origin = window.frame.origin
            workspaceHome?.size.height = window.frame.height
            if resized { workspaceHome?.size.width = window.frame.width }
        }
        if !resized {
            // AppKit moves attached child windows in the same WindowServer operation.
            // Update our reference only; setting their frames here causes visible chasing.
            lastRow = lastRow?.moved(to: window.frame.origin)
        } else if let row = lastRow, abs(row.workspace.width - window.frame.width) < 1,
                  abs(row.workspace.height - window.frame.height) < 1 {
            // AppKit can deliver a deferred resize notification for an applied frame.
            lastRow = row.moved(to: window.frame.origin)
        } else { layout() }
    }

    func updateHover(_ id: DesktopCompanionID, inside: Bool) {
        if inside { hovered.insert(id) } else { hovered.remove(id) }
        surface(id).chrome.setHovered(inside)
        desktop?.updateCompanionHover(!hovered.isEmpty)
    }

    func pinPreview() { if desktop?.previewing == true { desktop?.expand(animated: false) } }

    func beginDrag(_ id: DesktopCompanionID) {
        pinPreview()
        let item = surface(id)
        item.dragging = true
        detach(id)
    }

    func endDrag(_ id: DesktopCompanionID) {
        let item = surface(id)
        item.dragging = false
        if let frame = item.window?.frame, canDock(frame, id: id) {
            restoreBase(id)
            return
        } else { storeFreeFrame(item) }
        item.dockingSuggested = false
        save(item); layout()
    }

    fileprivate func surfaceMoved(_ id: DesktopCompanionID, resized: Bool = false) {
        guard !layingOut else { return }
        let item = surface(id)
        guard let window = item.window else { return }
        if item.dragging {
            item.dockingSuggested = canDock(window.frame, id: id)
        } else if item.docked {
            // Position-only notifications also arrive when the parent moves its children.
            guard resized, !item.expanded else { return }
            if let applied = item.appliedSize, abs(applied.width - window.frame.width) < 1,
               abs(applied.height - window.frame.height) < 1 { return }
            let docked = surfaces.filter { $0.visible && $0.docked }
            if abs(window.frame.width - (lastRow?.panels[id]?.width ?? 0)) > 0.5 {
                for sibling in docked { sibling.width = window.frame.width; save(sibling) }
            }
            if let workspace = desktop?.window,
               abs(window.frame.height - (lastRow?.panels[id]?.height ?? 0)) > 0.5 {
                let available = max(2, workspace.frame.height - DesktopCompanionGeometry.gap)
                setTopFraction(id == .first ? window.frame.height / available : 1 - window.frame.height / available)
            } else { layout() }
        } else { storeFreeFrame(item); save(item) }
    }

    fileprivate func constrainResize(_ id: DesktopCompanionID, size: NSSize) -> NSSize {
        let item = surface(id)
        guard item.docked, !item.dragging, let workspace = desktop?.window else { return size }
        if item.expanded { return item.window?.frame.size ?? size }
        let available = max(2, workspace.frame.height - DesktopCompanionGeometry.gap)
        let minimum = min(DesktopCompanionGeometry.minimumStackHeight, available / 2)
        return NSSize(width: max(DesktopCompanionGeometry.minimum.width, size.width),
                      height: min(available - minimum, max(minimum, size.height)))
    }

    func setTopFraction(_ fraction: CGFloat) {
        topFraction = fraction.isFinite ? min(0.9, max(0.1, fraction)) : 0.5
        defaults.set(topFraction, forKey: key + ".topFraction")
        layout()
    }

    func layout() {
        NSAnimationContext.runAnimationGroup { context in
            context.duration = 0
            layoutWindows()
        }
    }

    private func layoutWindows() {
        guard !layingOut else { return }
        layingOut = true
        defer { layingOut = false }
        guard let desktop, let workspace = desktop.window else {
            for item in surfaces { hideWindow(item) }
            return
        }
        if !desktop.enabled && !desktop.regularWorkspaceVisible {
            for item in surfaces { hideWindow(item) }
            return
        }
        let docked = surfaces.filter { $0.visible && $0.docked }
        for item in surfaces where !item.docked || !item.visible {
            if let window = item.window { window.parent?.removeChildWindow(window) }
        }
        if !docked.isEmpty && workspaceHome == nil { workspaceHome = workspace.frame }
        let desired = workspaceHome ?? workspace.frame
        let bounds = screen(for: workspace.frame)
        let row = DesktopCompanionGeometry.row(workspace: desired, widths: Dictionary(uniqueKeysWithValues: docked.map { ($0.id, $0.width) }), screen: bounds, topFraction: topFraction)
        lastRow = row
        let minimumHeight: CGFloat = desktop.enabled ? DesktopGeometry.minimumWorkspace.height : 640
        workspace.minSize = NSSize(width: min(minimumWorkspaceWidth, row.workspace.width), height: min(minimumHeight, bounds.height))
        if workspace.frame != row.workspace { workspace.setFrame(row.workspace, display: true) }
        if docked.isEmpty { workspaceHome = nil }
        let covering = docked.first { $0.expanded }?.id
        var prepared: [NSWindow] = []
        for item in surfaces {
            let independent = desktop.enabled && !item.docked && keepDetachedVisible
            let finishingFade = desktop.hidingWorkspace && item.window?.isVisible == true
            let shown = item.visible && (!desktop.enabled || desktop.expanded || finishingFade || independent)
                && (!item.docked || covering == nil || covering == item.id)
            guard shown else {
                hideWindow(item)
                hovered.remove(item.id)
                continue
            }
            let window = makeWindow(item)
            window.isFloatingPanel = desktop.enabled
            window.level = desktop.enabled ? .floating : workspace.level
            window.collectionBehavior = desktop.enabled ? [.moveToActiveSpace, .fullScreenAuxiliary] : [.fullScreenAuxiliary]
            let target: NSRect
            if item.docked {
                target = item.expanded ? row.expanded(content: desktop.regularContentFrame) : row.panels[item.id]!
                window.minSize = NSSize(width: min(DesktopCompanionGeometry.minimum.width, target.width),
                                        height: min(DesktopCompanionGeometry.minimumStackHeight, target.height))
            }
            else {
                window.minSize = DesktopCompanionGeometry.minimum
                let fallback = NSRect(x: bounds.midX - 190, y: bounds.midY - 260, width: item.width, height: 520)
                let saved = item.expanded ? item.expandedFrame : item.compactFrame
                let frame = saved ?? (item.expanded ? DesktopCompanionGeometry.enlarged(fallback, screen: bounds) : fallback)
                target = DesktopGeometry.fit(frame, within: screen(for: frame))
            }
            if !item.dragging && window.frame != target { window.setFrame(target, display: true) }
            item.appliedSize = window.frame.size
            if independent || !desktop.enabled { window.animator().alphaValue = 1 }
            else if !window.isVisible { window.animator().alphaValue = workspace.alphaValue }
            if presentsWindows && !window.isVisible {
                window.contentView?.layoutSubtreeIfNeeded()
                window.displayIfNeeded()
            }
            if item.docked && window.parent !== workspace { workspace.addChildWindow(window, ordered: .above) }
            prepared.append(window)
        }
        // Building the second surface must not delay the first surface's reveal.
        if presentsWindows {
            for window in prepared where !window.isVisible { window.orderFrontRegardless() }
        }
        desktop.updateCompanionHover(!hovered.isEmpty)
        if presentsWindows && desktop.enabled { desktop.corePanel?.orderFrontRegardless() }
    }

    /// Rebase docking onto the destination mode's workspace, retaining every tab,
    /// local presentation and detached frame. No session is closed here.
    func prepareModeChange() {
        for item in surfaces { storeFreeFrame(item); hideWindow(item) }
        hovered.removeAll(); desktop?.updateCompanionHover(false)
        workspaceHome = nil; lastRow = nil
    }

    func shutdown() {
        for item in surfaces {
            item.chrome.shutdown()
            item.presentations.shutdown()
            storeFreeFrame(item); save(item)
            item.panel.closeAll()
            if let window = item.window { window.parent?.removeChildWindow(window) }
            item.window?.delegate = nil; item.window?.orderOut(nil); item.window?.contentView = nil
            item.window = nil; item.delegate = nil
        }
        subscriptions.removeAll(); hovered.removeAll(); desktop = nil; app = nil
    }

    private func canDock(_ frame: NSRect, id: DesktopCompanionID) -> Bool {
        guard let desktop, let workspace = desktop.window,
              desktop.enabled ? desktop.expanded : desktop.regularWorkspaceVisible else { return false }
        if DesktopCompanionGeometry.shouldAttach(frame, beside: workspace.frame) { return true }
        let siblingID: DesktopCompanionID = id == .first ? .second : .first
        let sibling = surface(siblingID)
        return sibling.visible && sibling.docked && lastRow?.panels[siblingID].map {
            DesktopCompanionGeometry.shouldStack(frame, with: $0, id: id)
        } == true
    }

    private func hideWindow(_ item: DesktopCompanion) {
        item.chrome.reset()
        guard let window = item.window else { return }
        window.parent?.removeChildWindow(window)
        window.makeFirstResponder(nil); window.orderOut(nil)
        NSAnimationContext.runAnimationGroup { context in
            context.duration = 0
            window.animator().alphaValue = 1
        }
    }

    private func storeFreeFrame(_ item: DesktopCompanion) {
        guard !item.docked, let frame = item.window?.frame else { return }
        if item.expanded { item.expandedFrame = frame }
        else {
            if let previous = item.compactFrame, let expanded = item.expandedFrame, previous.origin != frame.origin {
                item.expandedFrame = DesktopGeometry.fit(expanded.offsetBy(dx: frame.midX - previous.midX,
                    dy: frame.midY - previous.midY), within: screen(for: frame))
            }
            item.compactFrame = frame
        }
    }

    private func makeWindow(_ item: DesktopCompanion) -> DesktopCompanionPanel {
        if let window = item.window { return window }
        let window = DesktopCompanionPanel(contentRect: NSRect(x: 0, y: 0, width: 380, height: 600),
            styleMask: [.borderless, .closable, .resizable, .nonactivatingPanel], backing: .buffered, defer: false)
        window.title = "Proto-Mind · " + item.id.title
        window.isReleasedWhenClosed = false; window.isFloatingPanel = true; window.hidesOnDeactivate = false
        window.isOpaque = false; window.backgroundColor = .clear; window.hasShadow = true
        window.animationBehavior = .none
        window.level = .floating; window.collectionBehavior = [.moveToActiveSpace, .fullScreenAuxiliary]
        window.minSize = DesktopCompanionGeometry.minimum
        let delegate = DesktopCompanionDelegate(owner: self, id: item.id)
        item.delegate = delegate; window.delegate = delegate
        item.presentations.window = window
        let id = item.id
        item.presentations.reveal = { [weak self] in self?.revealPresentation(id) }
        if let app {
            let host = NSHostingView(rootView: DesktopCompanionView(app: app, owner: self, surface: item))
            // Docking owns the frame. Content-derived min/max constraints must not
            // enlarge a half-height slot after its SwiftUI contents update.
            host.sizingOptions = []
            window.contentView = host
        }
        item.window = window
        item.chrome.attach(to: window)
        return window
    }

    private func screen(for frame: NSRect) -> NSRect { DesktopGeometry.screen(for: frame, screens: NSScreen.screens.map(\.visibleFrame)) }

    private func save(_ item: DesktopCompanion) {
        let prefix = key + "." + item.id.rawValue
        defaults.set(item.visible, forKey: prefix + ".visible")
        defaults.set(item.docked, forKey: prefix + ".docked")
        defaults.set(item.width, forKey: prefix + ".width")
        defaults.set(item.transparency, forKey: prefix + ".transparency")
        if let frame = item.compactFrame { defaults.set(NSStringFromRect(frame), forKey: prefix + ".compact") }
        if let frame = item.expandedFrame { defaults.set(NSStringFromRect(frame), forKey: prefix + ".expanded") }
    }

    private func savedFrame(_ key: String) -> NSRect? {
        guard let value = defaults.string(forKey: key) else { return nil }
        let rect = NSRectFromString(value)
        return [rect.minX, rect.minY, rect.width, rect.height].allSatisfy(\.isFinite) && rect.width >= 1 && rect.height >= 1 ? rect : nil
    }
}

final class DesktopCompanionPanel: NSPanel {
    override var canBecomeKey: Bool { true }
    override var canBecomeMain: Bool { false }
}

@MainActor
private final class DesktopCompanionDelegate: NSObject, NSWindowDelegate {
    weak var owner: DesktopCompanionWindows?
    let id: DesktopCompanionID
    init(owner: DesktopCompanionWindows, id: DesktopCompanionID) { self.owner = owner; self.id = id }
    func windowShouldClose(_ sender: NSWindow) -> Bool { owner?.toggle(id); return false }
    func windowDidMove(_ notification: Notification) { owner?.surfaceMoved(id) }
    func windowDidResize(_ notification: Notification) { owner?.surfaceMoved(id, resized: true) }
    func windowWillResize(_ sender: NSWindow, to frameSize: NSSize) -> NSSize { owner?.constrainResize(id, size: frameSize) ?? frameSize }
}
