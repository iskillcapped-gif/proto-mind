import AppKit
import CryptoKit
import SwiftUI

/// Window geometry is UI state only. It never participates in dialog or voice ownership.
enum DesktopGeometry {
    static let coreSize = NSSize(width: 88, height: 108)
    static let minimumWorkspace = NSSize(width: 580, height: 500)

    static func fit(_ frame: NSRect, within screen: NSRect) -> NSRect {
        let width = min(max(1, frame.width.isFinite ? frame.width : 800), screen.width)
        let height = min(max(1, frame.height.isFinite ? frame.height : 740), screen.height)
        let x = frame.minX.isFinite ? frame.minX : screen.midX - width / 2
        let y = frame.minY.isFinite ? frame.minY : screen.midY - height / 2
        return NSRect(x: min(max(x, screen.minX), screen.maxX - width),
                      y: min(max(y, screen.minY), screen.maxY - height), width: width, height: height)
    }

    static func screen(for frame: NSRect, screens: [NSRect]) -> NSRect {
        screens.max { left, right in
            func area(_ rect: NSRect) -> CGFloat {
                let overlap = rect.intersection(frame)
                return overlap.isNull ? 0 : overlap.width * overlap.height
            }
            return area(left) < area(right)
        } ?? NSRect(x: 0, y: 0, width: 1280, height: 800)
    }

    static func workspace(beside core: NSRect, size: NSSize, screen: NSRect) -> NSRect {
        let x = core.minX - size.width - 16 >= screen.minX
            ? core.minX - size.width - 16 : core.maxX + 16
        return fit(NSRect(x: x, y: core.midY - size.height / 2, width: size.width, height: size.height), within: screen)
    }
}

@MainActor
final class DesktopPresentation: ObservableObject {
    @Published private(set) var enabled = false
    @Published private(set) var expanded = false
    private(set) weak var window: NSWindow?
    private(set) var corePanel: NSPanel?
    private weak var app: AppModel?
    private let defaults: UserDefaults
    private let presentsWindows: Bool
    private let preferenceKey: String
    private var observers: [NSObjectProtocol] = []
    private var original: WindowAppearance?
    private var changingWindow = false
    private var transition = UUID()
    private var windowDelegate: DesktopWindowDelegate?

    private struct WindowAppearance {
        let frame: NSRect
        let background: NSColor
        let opaque: Bool
        let level: NSWindow.Level
        let collection: NSWindow.CollectionBehavior
        let minimum: NSSize
        let transparentTitlebar: Bool
    }

    init(stateDirectory: URL, defaults: UserDefaults = .standard, presentsWindows: Bool = true) {
        self.defaults = defaults
        self.presentsWindows = presentsWindows
        let digest = SHA256.hash(data: Data(stateDirectory.standardizedFileURL.path.utf8))
            .map { String(format: "%02x", $0) }.joined()
        preferenceKey = "desktopPresentation.v1." + digest
    }

    func attach(window: NSWindow, app: AppModel) {
        guard self.window !== window else { return }
        removeObservers()
        self.window = window; self.app = app
        let delegate = DesktopWindowDelegate(desktop: self, previous: window.delegate)
        windowDelegate = delegate; window.delegate = delegate
        for name in [NSWindow.didMoveNotification, NSWindow.didEndLiveResizeNotification] {
            observers.append(NotificationCenter.default.addObserver(forName: name, object: window, queue: .main) { [weak self] _ in
                MainActor.assumeIsolated { self?.saveWorkspaceFrame() }
            })
        }
        observers.append(NotificationCenter.default.addObserver(forName: NSApplication.didChangeScreenParametersNotification, object: nil, queue: .main) { [weak self] _ in
            MainActor.assumeIsolated { self?.recoverVisibleFrames() }
        })
        // An approval can arrive while the workspace is folded away. Reveal its owner.
        observers.append(NotificationCenter.default.addObserver(forName: NSWindow.willBeginSheetNotification, object: window, queue: .main) { [weak self] _ in
            MainActor.assumeIsolated { self?.expand(animated: false) }
        })
        if defaults.bool(forKey: preferenceKey + ".enabled") { enable(animated: false) }
    }

    func toggleMode() { enabled ? restoreWindow() : enable() }

    func enable(animated: Bool = true) {
        guard !enabled, let window, let app, window.attachedSheet == nil else { return }
        original = WindowAppearance(frame: window.frame, background: window.backgroundColor,
                                    opaque: window.isOpaque, level: window.level, collection: window.collectionBehavior,
                                    minimum: window.minSize, transparentTitlebar: window.titlebarAppearsTransparent)
        changingWindow = true
        enabled = true; expanded = true
        // SwiftUI owns its toolbar/background host. Keep the titled frame alive;
        // removing it while SwiftUI detaches that host raises an AppKit exception.
        window.titlebarAppearsTransparent = true
        for kind in [NSWindow.ButtonType.closeButton, .miniaturizeButton, .zoomButton] {
            window.standardWindowButton(kind)?.isHidden = true
        }
        window.isOpaque = false; window.backgroundColor = .clear; window.hasShadow = true
        window.level = .floating; window.collectionBehavior = [.moveToActiveSpace, .fullScreenAuxiliary]
        window.minSize = DesktopGeometry.minimumWorkspace
        let core = makeCore(app: app)
        let screens = NSScreen.screens.map(\.visibleFrame)
        let savedCore = savedFrame("core")
        let screen = DesktopGeometry.screen(for: savedCore ?? window.frame, screens: screens)
        let initial = NSRect(x: screen.maxX - 116, y: screen.midY - 54, width: 88, height: 108)
        let coreOrigin = (savedCore ?? initial).origin
        core.setFrame(DesktopGeometry.fit(NSRect(origin: coreOrigin, size: DesktopGeometry.coreSize), within: screen), display: false)
        let savedWorkspace = savedFrame("workspace")
        let size = savedWorkspace?.size ?? NSSize(width: 800, height: 740)
        let target = savedWorkspace.map { DesktopGeometry.fit($0, within: DesktopGeometry.screen(for: $0, screens: screens)) }
            ?? DesktopGeometry.workspace(beside: core.frame, size: size, screen: screen)
        window.setFrame(target, display: true)
        if presentsWindows { core.orderFrontRegardless() }
        defaults.set(true, forKey: preferenceKey + ".enabled")
        changingWindow = false
        expand(animated: animated)
    }

    func expand(animated: Bool = true) {
        guard enabled, let window else { return }
        transition = UUID(); expanded = true
        recoverVisibleFrames()
        window.alphaValue = animated && !NSWorkspace.shared.accessibilityDisplayShouldReduceMotion ? 0 : 1
        if presentsWindows {
            NSApp.activate(ignoringOtherApps: true)
            if window.isMiniaturized { window.deminiaturize(nil) }
            window.makeKeyAndOrderFront(nil)
        }
        if window.alphaValue < 1 {
            NSAnimationContext.runAnimationGroup { context in
                context.duration = 0.18
                window.animator().alphaValue = 1
            }
        }
    }

    func collapse(animated: Bool = true) {
        guard enabled, expanded, let window, window.attachedSheet == nil else { return }
        app?.flushDraft()
        guard app?.historyPersistence.failure == nil else { return }
        saveWorkspaceFrame()
        let token = UUID(); transition = token
        expanded = false
        let finish: @MainActor @Sendable () -> Void = { [weak self, weak window] in
            guard let self, self.transition == token, !self.expanded else { return }
            window?.orderOut(nil); window?.alphaValue = 1
        }
        if animated && !NSWorkspace.shared.accessibilityDisplayShouldReduceMotion {
            NSAnimationContext.runAnimationGroup({ context in
                context.duration = 0.16; window.animator().alphaValue = 0
            }, completionHandler: { Task { @MainActor in finish() } })
        } else { finish() }
    }

    func restoreWindow() {
        guard enabled, let window, let original, window.attachedSheet == nil else { return }
        transition = UUID(); changingWindow = true
        saveWorkspaceFrame(force: true)
        enabled = false; expanded = false
        corePanel?.orderOut(nil)
        window.alphaValue = 1
        for kind in [NSWindow.ButtonType.closeButton, .miniaturizeButton, .zoomButton] {
            window.standardWindowButton(kind)?.isHidden = false
        }
        window.isOpaque = original.opaque; window.backgroundColor = original.background
        window.titlebarAppearsTransparent = original.transparentTitlebar
        window.level = original.level; window.collectionBehavior = original.collection
        window.minSize = original.minimum
        let screen = DesktopGeometry.screen(for: original.frame, screens: NSScreen.screens.map(\.visibleFrame))
        window.setFrame(DesktopGeometry.fit(original.frame, within: screen), display: true)
        defaults.set(false, forKey: preferenceKey + ".enabled")
        changingWindow = false
        if presentsWindows { NSApp.activate(ignoringOtherApps: true); window.makeKeyAndOrderFront(nil) }
        self.original = nil
    }

    func reopen() -> Bool {
        guard enabled else { return false }
        expand(); return true
    }

    func coreMoved() {
        guard let corePanel else { return }
        defaults.set(NSStringFromRect(corePanel.frame), forKey: preferenceKey + ".core")
        if !expanded, let window {
            let screen = DesktopGeometry.screen(for: corePanel.frame, screens: NSScreen.screens.map(\.visibleFrame))
            changingWindow = true
            window.setFrame(DesktopGeometry.workspace(beside: corePanel.frame, size: window.frame.size, screen: screen), display: false)
            defaults.set(NSStringFromRect(window.frame), forKey: preferenceKey + ".workspace")
            changingWindow = false
        }
    }

    func shutdown() {
        transition = UUID()
        removeObservers(); corePanel?.orderOut(nil); corePanel?.contentView = nil; corePanel = nil
        if window?.delegate === windowDelegate { window?.delegate = windowDelegate?.previous }
        windowDelegate = nil
        window = nil; app = nil
    }

    private func removeObservers() {
        observers.forEach(NotificationCenter.default.removeObserver); observers.removeAll()
    }

    private func savedFrame(_ name: String) -> NSRect? {
        guard let value = defaults.string(forKey: preferenceKey + "." + name) else { return nil }
        let frame = NSRectFromString(value)
        guard [frame.minX, frame.minY, frame.width, frame.height].allSatisfy(\.isFinite), frame.width > 0, frame.height > 0 else { return nil }
        return frame
    }

    private func saveWorkspaceFrame(force: Bool = false) {
        guard enabled, expanded, (!changingWindow || force), let window else { return }
        defaults.set(NSStringFromRect(window.frame), forKey: preferenceKey + ".workspace")
    }

    private func recoverVisibleFrames() {
        guard enabled, let window else { return }
        changingWindow = true
        let screens = NSScreen.screens.map(\.visibleFrame)
        for surface in [window, corePanel].compactMap({ $0 }) {
            let screen = DesktopGeometry.screen(for: surface.frame, screens: screens)
            let target = DesktopGeometry.fit(surface.frame, within: screen)
            if surface.frame != target { surface.setFrame(target, display: true) }
        }
        changingWindow = false
    }

    private func makeCore(app: AppModel) -> NSPanel {
        if let corePanel { return corePanel }
        let panel = DesktopCorePanel(contentRect: NSRect(origin: .zero, size: DesktopGeometry.coreSize),
                                     styleMask: [.borderless, .nonactivatingPanel], backing: .buffered, defer: false)
        panel.title = "Ядро Proto-Mind"
        panel.setAccessibilitySubrole(.floatingWindow)
        panel.isFloatingPanel = true; panel.hidesOnDeactivate = false
        panel.isOpaque = false; panel.backgroundColor = .clear; panel.hasShadow = false
        panel.level = .floating; panel.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary, .ignoresCycle]
        panel.isReleasedWhenClosed = false
        let host = DesktopCoreDragView(rootView: DesktopCoreView(app: app, voice: app.liveVoice, desktop: self))
        host.desktop = self; panel.contentView = host
        corePanel = panel
        return panel
    }
}

/// Preserve SwiftUI's delegate behavior; closing a floating workspace only folds it away.
private final class DesktopWindowDelegate: NSObject, NSWindowDelegate {
    weak var desktop: DesktopPresentation?
    let previous: NSWindowDelegate?
    init(desktop: DesktopPresentation, previous: NSWindowDelegate?) {
        self.desktop = desktop; self.previous = previous
    }
    func windowShouldClose(_ sender: NSWindow) -> Bool {
        if desktop?.enabled == true { desktop?.collapse(); return false }
        return previous?.windowShouldClose?(sender) ?? true
    }
    override func responds(to selector: Selector!) -> Bool {
        super.responds(to: selector) || previous?.responds(to: selector) == true
    }
    override func forwardingTarget(for selector: Selector!) -> Any? { previous }
}

private final class DesktopCorePanel: NSPanel {
    override var canBecomeKey: Bool { false }
    override var canBecomeMain: Bool { false }
}

private final class DesktopCoreDragView: NSHostingView<DesktopCoreView> {
    weak var desktop: DesktopPresentation?
    private var startPoint = NSPoint.zero
    private var startFrame = NSRect.zero
    private var dragged = false
    override func hitTest(_ point: NSPoint) -> NSView? { bounds.contains(point) ? self : nil }
    override func acceptsFirstMouse(for event: NSEvent?) -> Bool { true }
    override func resetCursorRects() { addCursorRect(bounds, cursor: .openHand) }
    override func mouseDown(with event: NSEvent) {
        startPoint = window?.convertPoint(toScreen: event.locationInWindow) ?? event.locationInWindow
        startFrame = window?.frame ?? .zero; dragged = false
    }
    override func mouseDragged(with event: NSEvent) {
        let point = window?.convertPoint(toScreen: event.locationInWindow) ?? event.locationInWindow
        let dx = point.x - startPoint.x, dy = point.y - startPoint.y
        guard dragged || hypot(dx, dy) > 4 else { return }
        dragged = true
        let proposed = startFrame.offsetBy(dx: dx, dy: dy)
        let screen = NSScreen.screens.first { $0.frame.contains(point) }?.visibleFrame
            ?? DesktopGeometry.screen(for: proposed, screens: NSScreen.screens.map(\.visibleFrame))
        window?.setFrame(DesktopGeometry.fit(proposed, within: screen), display: true)
    }
    override func mouseUp(with event: NSEvent) {
        if dragged { desktop?.coreMoved() }
        else if desktop?.expanded == true { desktop?.collapse() }
        else { desktop?.expand() }
    }
    override func rightMouseDown(with event: NSEvent) {
        let menu = NSMenu()
        let toggle = NSMenuItem(title: desktop?.expanded == true ? "Свернуть в ядро" : "Открыть Proto-Mind", action: #selector(toggleWorkspace), keyEquivalent: "")
        toggle.target = self; menu.addItem(toggle)
        let restore = NSMenuItem(title: "Обычное окно", action: #selector(restoreWorkspace), keyEquivalent: "")
        restore.target = self; menu.addItem(restore)
        NSMenu.popUpContextMenu(menu, with: event, for: self)
    }
    @objc private func toggleWorkspace() { desktop?.expanded == true ? desktop?.collapse() : desktop?.expand() }
    @objc private func restoreWorkspace() { desktop?.restoreWindow() }
    override func isAccessibilityElement() -> Bool { true }
    override func accessibilityRole() -> NSAccessibility.Role? { .button }
    override func accessibilityLabel() -> String? { "Ядро Proto-Mind" }
    override func accessibilityHelp() -> String? { "Нажмите, чтобы раскрыть или свернуть чат. Перетащите в удобное место." }
    override func accessibilityPerformPress() -> Bool { toggleWorkspace(); return true }
}

struct DesktopWindowAttachment: NSViewRepresentable {
    let app: AppModel
    func makeNSView(context: Context) -> Attachment {
        let view = Attachment(); view.app = app; return view
    }
    func updateNSView(_ nsView: Attachment, context: Context) { nsView.app = app }
    final class Attachment: NSView {
        weak var app: AppModel?
        override func viewDidMoveToWindow() {
            super.viewDidMoveToWindow()
            guard let window, let app else { return }
            DispatchQueue.main.async { [weak window, weak app] in
                guard let window, let app else { return }
                app.desktop.attach(window: window, app: app)
            }
        }
    }
}
