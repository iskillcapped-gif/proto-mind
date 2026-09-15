import AppKit
import Combine
import CryptoKit
import SwiftUI

@MainActor
final class DesktopCompanion: ObservableObject, Identifiable {
    let id: DesktopCompanionID
    let panel = WorkspacePanelModel()
    @Published fileprivate(set) var visible = false
    @Published fileprivate(set) var docked = true
    @Published fileprivate(set) var expanded = false
    @Published fileprivate(set) var transparency = DesktopGlassAppearance.chatDefault
    @Published fileprivate(set) var dockingSuggested = false
    fileprivate(set) var window: DesktopCompanionPanel?
    fileprivate var delegate: DesktopCompanionDelegate?
    fileprivate var width: CGFloat = 380
    fileprivate var compactFrame: NSRect?
    fileprivate var expandedFrame: NSRect?
    fileprivate var dragging = false
    init(_ id: DesktopCompanionID) { self.id = id }
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

    init(stateDirectory: URL, defaults: UserDefaults = .standard, presentsWindows: Bool = true) {
        self.defaults = defaults; self.presentsWindows = presentsWindows
        key = "desktopCompanions.v1." + SHA256.hash(data: Data(stateDirectory.standardizedFileURL.path.utf8)).map { String(format: "%02x", $0) }.joined()
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
    var preferredWorkspaceFrame: NSRect? { workspaceHome }
    var minimumWorkspaceWidth: CGFloat {
        let count = surfaces.filter { $0.visible && $0.docked }.count
        guard count > 0 else { return DesktopGeometry.minimumWorkspace.width }
        let bounds = screen(for: desktop?.window?.frame ?? .zero)
        return min(640, max(1, bounds.width - CGFloat(count) * DesktopCompanionGeometry.gap) * 0.52)
    }
    func attach(desktop: DesktopPresentation, app: AppModel) { self.desktop = desktop; self.app = app }

    func toggle(_ id: DesktopCompanionID) {
        let item = surface(id)
        item.visible.toggle()
        if !item.visible { item.expanded = false; item.panel.expanded = false; updateHover(id, inside: false) }
        save(item)
        if item.visible && item.docked { desktop?.expand(animated: false) }
        layout()
        if item.visible && presentsWindows { item.window?.makeKeyAndOrderFront(nil) }
    }

    func setTransparency(_ value: Double, for id: DesktopCompanionID) {
        let item = surface(id)
        item.transparency = DesktopGlassAppearance.normalized(value, fallback: DesktopGlassAppearance.chatDefault)
        save(item)
    }

    func toggleDocking(_ id: DesktopCompanionID) {
        let item = surface(id)
        if item.docked { detach(id) }
        else {
            storeFreeFrame(item)
            item.docked = true; item.expanded = false; item.panel.expanded = false
            save(item); desktop?.expand(animated: false); layout()
        }
        if item.visible && presentsWindows { item.window?.makeKeyAndOrderFront(nil) }
    }

    func detach(_ id: DesktopCompanionID) {
        let item = surface(id)
        guard item.docked else { return }
        let compact = lastRow?.panels[id] ?? item.window?.frame
        item.docked = false
        if item.expanded { item.expandedFrame = item.window?.frame }
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
        guard !layingOut, desktop?.enabled == true, let window = desktop?.window else { return }
        if workspaceHome != nil {
            workspaceHome?.origin = window.frame.origin
            workspaceHome?.size.height = window.frame.height
            if resized { workspaceHome?.size.width = window.frame.width }
        }
        layout()
    }

    func updateHover(_ id: DesktopCompanionID, inside: Bool) {
        if inside { hovered.insert(id) } else { hovered.remove(id) }
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
        if let frame = item.window?.frame, let anchor = dockingAnchor(for: id),
           DesktopCompanionGeometry.shouldAttach(frame, beside: anchor) {
            item.docked = true; item.expanded = false; item.panel.expanded = false
        } else { storeFreeFrame(item) }
        item.dockingSuggested = false
        save(item); layout()
    }

    fileprivate func surfaceMoved(_ id: DesktopCompanionID, resized: Bool = false) {
        guard !layingOut else { return }
        let item = surface(id)
        guard let window = item.window else { return }
        if item.dragging {
            item.dockingSuggested = dockingAnchor(for: id).map { DesktopCompanionGeometry.shouldAttach(window.frame, beside: $0) } ?? false
        } else if item.docked {
            if resized && !item.expanded { item.width = window.frame.width }
            save(item); layout()
        } else { storeFreeFrame(item); save(item) }
    }

    fileprivate func constrainResize(_ id: DesktopCompanionID, size: NSSize) -> NSSize {
        let item = surface(id)
        guard item.docked, !item.dragging, let workspace = desktop?.window else { return size }
        if item.expanded { return item.window?.frame.size ?? size }
        return NSSize(width: max(DesktopCompanionGeometry.minimum.width, size.width), height: workspace.frame.height)
    }

    func layout() {
        guard !layingOut else { return }
        layingOut = true
        defer { layingOut = false }
        guard let desktop, desktop.enabled, let workspace = desktop.window else {
            for item in surfaces { item.window?.makeFirstResponder(nil); item.window?.orderOut(nil) }
            return
        }
        let docked = surfaces.filter { $0.visible && $0.docked }
        if !docked.isEmpty && workspaceHome == nil { workspaceHome = workspace.frame }
        let desired = workspaceHome ?? workspace.frame
        let bounds = screen(for: workspace.frame)
        let row = DesktopCompanionGeometry.row(workspace: desired, widths: Dictionary(uniqueKeysWithValues: docked.map { ($0.id, $0.width) }), screen: bounds)
        lastRow = row
        workspace.minSize = NSSize(width: min(DesktopGeometry.minimumWorkspace.width, row.workspace.width), height: min(DesktopGeometry.minimumWorkspace.height, bounds.height))
        if workspace.frame != row.workspace { workspace.setFrame(row.workspace, display: true) }
        if docked.isEmpty { workspaceHome = nil }
        let covering = docked.first { $0.expanded }?.id
        for item in surfaces {
            let shown = item.visible && (!item.docked || desktop.expanded) && (!item.docked || covering == nil || covering == item.id)
            guard shown else {
                item.window?.makeFirstResponder(nil); item.window?.orderOut(nil)
                hovered.remove(item.id)
                continue
            }
            let window = makeWindow(item)
            let target: NSRect
            if item.docked { target = item.expanded ? row.expanded : row.panels[item.id]! }
            else {
                let fallback = NSRect(x: bounds.midX - 190, y: bounds.midY - 260, width: item.width, height: 520)
                let saved = item.expanded ? item.expandedFrame : item.compactFrame
                let frame = saved ?? (item.expanded ? DesktopCompanionGeometry.enlarged(fallback, screen: bounds) : fallback)
                target = DesktopGeometry.fit(frame, within: screen(for: frame))
            }
            if !item.dragging && window.frame != target { window.setFrame(target, display: true) }
            if presentsWindows && !window.isVisible { window.orderFrontRegardless() }
        }
        desktop.updateCompanionHover(!hovered.isEmpty)
        if presentsWindows { desktop.corePanel?.orderFrontRegardless() }
    }

    func leaveFloatingMode() {
        for item in surfaces { item.window?.makeFirstResponder(nil); item.window?.orderOut(nil) }
        hovered.removeAll(); desktop?.updateCompanionHover(false)
        workspaceHome = nil; lastRow = nil
    }

    func shutdown() {
        for item in surfaces {
            storeFreeFrame(item); save(item)
            item.panel.closeAll()
            item.window?.delegate = nil; item.window?.orderOut(nil); item.window?.contentView = nil
            item.window = nil; item.delegate = nil
        }
        subscriptions.removeAll(); hovered.removeAll(); desktop = nil; app = nil
    }

    private func dockingAnchor(for id: DesktopCompanionID) -> NSRect? {
        guard desktop?.enabled == true, desktop?.expanded == true, let workspace = desktop?.window else { return nil }
        if id == .second, surface(.first).visible, surface(.first).docked {
            return lastRow?.panels[.first]
        }
        return workspace.frame
    }

    private func storeFreeFrame(_ item: DesktopCompanion) {
        guard !item.docked, let frame = item.window?.frame else { return }
        if item.expanded { item.expandedFrame = frame } else { item.compactFrame = frame }
    }

    private func makeWindow(_ item: DesktopCompanion) -> DesktopCompanionPanel {
        if let window = item.window { return window }
        let window = DesktopCompanionPanel(contentRect: NSRect(x: 0, y: 0, width: 380, height: 600),
            styleMask: [.borderless, .closable, .resizable, .nonactivatingPanel], backing: .buffered, defer: false)
        window.title = "Proto-Mind · " + item.id.title
        window.isReleasedWhenClosed = false; window.isFloatingPanel = true; window.hidesOnDeactivate = false
        window.isOpaque = false; window.backgroundColor = .clear; window.hasShadow = true
        window.level = .floating; window.collectionBehavior = [.moveToActiveSpace, .fullScreenAuxiliary]
        window.minSize = DesktopCompanionGeometry.minimum
        let delegate = DesktopCompanionDelegate(owner: self, id: item.id)
        item.delegate = delegate; window.delegate = delegate
        if let app {
            window.contentView = NSHostingView(rootView: DesktopCompanionView(app: app, owner: self, surface: item)
                .environment(\.workspacePresentations, app.presentations))
        }
        item.window = window
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
    func windowDidBecomeKey(_ notification: Notification) { owner?.pinPreview() }
    func windowWillResize(_ sender: NSWindow, to frameSize: NSSize) -> NSSize { owner?.constrainResize(id, size: frameSize) ?? frameSize }
}
