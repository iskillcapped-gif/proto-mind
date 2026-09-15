import AppKit
import Combine
import CryptoKit
import SwiftUI

/// Window geometry is UI state only. It never participates in dialog or voice ownership.
enum DesktopGeometry {
    static let coreSize = NSSize(width: 136, height: 124)
    static let minimumWorkspace = NSSize(width: 780, height: 520)

    static func sidebarWidth(total: CGFloat) -> CGFloat { min(260, max(220, total * 0.23)) }

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

/// Only glass backgrounds change; text and controls keep their own contrast.
enum DesktopGlassAppearance {
    static let chatDefault = 0.34
    static let sidebarDefault = 0.25
    static func normalized(_ value: Double, fallback: Double) -> Double {
        value.isFinite ? min(1, max(0, value)) : fallback
    }
}

@MainActor
final class DesktopPresentation: ObservableObject {
    let companions: DesktopCompanionWindows
    @Published private(set) var enabled = false
    @Published private(set) var expanded = false
    @Published private(set) var previewing = false
    @Published private(set) var chatTransparency: Double
    @Published private(set) var sidebarTransparency: Double
    @Published private(set) var coreHovered = false
    private(set) weak var window: NSWindow?
    private(set) var corePanel: NSPanel?
    private(set) var voicePanel: DesktopVoicePanel?
    private weak var app: AppModel?
    private let defaults: UserDefaults
    private let presentsWindows: Bool
    private let preferenceKey: String
    private var observers: [NSObjectProtocol] = []
    private var voiceObservers: [NSObjectProtocol] = []
    private var original: WindowAppearance?
    private var changingWindow = false
    private var transition = UUID()
    private var windowDelegate: DesktopWindowDelegate?
    private var openSettings: () -> Void = {}
    private var workspaceHovered = false
    private var companionHovered = false
    private var coreInteracting = false
    private var hoverSuppressed = false
    private var hoverTask: Task<Void, Never>?
    private var previewPointerTask: Task<Void, Never>?
    private let pointerLocation: (() -> NSPoint)?
    private var interactionMonitor: Any?
    private var companionSubscription: AnyCancellable?

    private struct WindowAppearance {
        let frame: NSRect
        let background: NSColor
        let opaque: Bool
        let level: NSWindow.Level
        let collection: NSWindow.CollectionBehavior
        let minimum: NSSize
        let transparentTitlebar: Bool
    }

    init(stateDirectory: URL, defaults: UserDefaults = .standard, presentsWindows: Bool = true,
         pointerLocation: (() -> NSPoint)? = { NSEvent.mouseLocation }) {
        companions = DesktopCompanionWindows(stateDirectory: stateDirectory, defaults: defaults, presentsWindows: presentsWindows)
        self.defaults = defaults
        self.presentsWindows = presentsWindows
        self.pointerLocation = pointerLocation
        let digest = SHA256.hash(data: Data(stateDirectory.standardizedFileURL.path.utf8))
            .map { String(format: "%02x", $0) }.joined()
        preferenceKey = "desktopPresentation.v1." + digest
        chatTransparency = DesktopGlassAppearance.normalized(
            defaults.object(forKey: preferenceKey + ".chatTransparency") as? Double ?? DesktopGlassAppearance.chatDefault,
            fallback: DesktopGlassAppearance.chatDefault)
        sidebarTransparency = DesktopGlassAppearance.normalized(
            defaults.object(forKey: preferenceKey + ".sidebarTransparency") as? Double ?? DesktopGlassAppearance.sidebarDefault,
            fallback: DesktopGlassAppearance.sidebarDefault)
        companionSubscription = companions.objectWillChange.sink { [weak self] in self?.objectWillChange.send() }
    }

    func setChatTransparency(_ value: Double) {
        chatTransparency = DesktopGlassAppearance.normalized(value, fallback: DesktopGlassAppearance.chatDefault)
        defaults.set(chatTransparency, forKey: preferenceKey + ".chatTransparency")
    }

    func setSidebarTransparency(_ value: Double) {
        sidebarTransparency = DesktopGlassAppearance.normalized(value, fallback: DesktopGlassAppearance.sidebarDefault)
        defaults.set(sidebarTransparency, forKey: preferenceKey + ".sidebarTransparency")
    }

    func openVoice() { app?.presentLiveVoice(openSettings: openSettings) }
    func updateCoreHover(_ inside: Bool) {
        guard enabled else { return }
        guard coreHovered != inside else { return }
        coreHovered = inside
        if !inside { hoverSuppressed = false }
        scheduleHoverTransition()
    }

    func updateWorkspaceHover(_ inside: Bool) {
        guard enabled else { return }
        guard workspaceHovered != inside else { return }
        workspaceHovered = inside
        scheduleHoverTransition()
    }

    func updateCompanionHover(_ inside: Bool) {
        guard companionHovered != inside else { return }
        companionHovered = inside
        scheduleHoverTransition()
    }

    private func scheduleHoverTransition() {
        hoverTask?.cancel(); hoverTask = nil
        guard enabled, !coreInteracting else { return }
        if !expanded, coreHovered, !hoverSuppressed {
            hoverTask = Task { @MainActor [weak self] in
                do { try await Task.sleep(for: .milliseconds(180)) } catch { return }
                guard let self, self.enabled, self.coreHovered, !self.hoverSuppressed,
                      !self.coreInteracting, !self.expanded else { return }
                self.showWorkspace(preview: true, animated: true)
            }
        } else if previewing, pointerLocation != nil {
            trackPreviewPointer()
        } else if previewing, !coreHovered, !workspaceHovered, !companionHovered {
            hoverTask = Task { @MainActor [weak self] in
                // Leave time to cross the gap between the core and its workspace.
                do { try await Task.sleep(for: .milliseconds(320)) } catch { return }
                guard let self, self.previewing, !self.coreHovered, !self.workspaceHovered, !self.companionHovered,
                      !self.coreInteracting else { return }
                self.collapse()
            }
        }
    }

    private func cancelHoverTransition() {
        hoverTask?.cancel(); hoverTask = nil
        previewPointerTask?.cancel(); previewPointerTask = nil
    }

    private func trackPreviewPointer() {
        guard previewing, pointerLocation != nil, previewPointerTask == nil else { return }
        // Child windows can receive an enter without a matching exit when they
        // appear behind the cube or their tracking areas are rebuilt. While peeking,
        // actual pointer geometry is authoritative. No polling runs when pinned/hidden.
        previewPointerTask = Task { @MainActor [weak self] in
            var outsideSince: ContinuousClock.Instant?
            while !Task.isCancelled {
                do { try await Task.sleep(for: .milliseconds(100)) } catch { return }
                guard let self, self.enabled, self.previewing, let point = self.pointerLocation?() else { return }
                let overCore = self.corePanel.map { $0.isVisible && $0.frame.contains(point) } == true
                if self.coreHovered != overCore { self.coreHovered = overCore }
                if !overCore { self.hoverSuppressed = false }
                let inside = [self.corePanel, self.window].compactMap { $0 }.contains {
                    $0.isVisible && $0.frame.contains(point)
                } || self.companions.containsVisibleWindow(at: point)
                if inside || self.coreInteracting { outsideSince = nil }
                else {
                    if outsideSince == nil { outsideSince = .now }
                    if let outsideSince, outsideSince.duration(to: .now) >= .milliseconds(320) {
                        self.collapse()
                        return
                    }
                }
            }
        }
    }

    func handleWorkspaceInteraction(_ event: NSEvent) {
        guard previewing, let target = event.window,
              target === window || companions.owns(target) else { return }
        switch event.type {
        case .leftMouseDown, .rightMouseDown, .otherMouseDown, .keyDown:
            // Only intentional input pins a preview; ordering/focus notifications
            // also happen as a side effect of revealing an AppKit child window.
            expand(animated: false)
        default: break
        }
    }

    func beginCoreInteraction() { coreInteracting = true; cancelHoverTransition() }
    func endCoreInteraction() { coreInteracting = false; scheduleHoverTransition() }
    func beginCoreDrag() {
        if previewing { collapse(animated: false) }
        hoverSuppressed = true
    }

    func toggleWorkspace() {
        if expanded && !previewing { collapse() }
        else { expand() }
    }

    func setVoiceVisible(_ visible: Bool, app: AppModel) {
        guard visible else { voicePanel?.orderOut(nil); return }
        let panel: DesktopVoicePanel
        if let existing = voicePanel { panel = existing }
        else {
            panel = DesktopVoicePanel(contentRect: NSRect(x: 0, y: 0, width: 410, height: 545),
                                      styleMask: [.titled, .closable, .resizable, .fullSizeContentView], backing: .buffered, defer: false)
            panel.title = "Голос Proto-Mind"; panel.titleVisibility = .hidden; panel.titlebarAppearsTransparent = true
            panel.isReleasedWhenClosed = false; panel.isFloatingPanel = true; panel.hidesOnDeactivate = false
            panel.isOpaque = false; panel.backgroundColor = .clear; panel.hasShadow = true
            panel.level = .floating; panel.collectionBehavior = [.moveToActiveSpace, .fullScreenAuxiliary]
            panel.minSize = NSSize(width: 350, height: 480)
            panel.onClose = { [weak app] in app?.showLiveVoice = false }
            panel.contentView = NSHostingView(rootView: FloatingVoiceView(app: app, voice: app.liveVoice, desktop: self))
            let screens = NSScreen.screens.map(\.visibleFrame)
            let screen = DesktopGeometry.screen(for: window?.frame ?? .zero, screens: screens)
            let initial = NSRect(x: screen.maxX - 446, y: screen.midY - 272, width: 410, height: 545)
            panel.setFrame(DesktopGeometry.fit(savedFrame("voice") ?? initial, within: screen), display: false)
            for name in [NSWindow.didMoveNotification, NSWindow.didEndLiveResizeNotification] {
                voiceObservers.append(NotificationCenter.default.addObserver(forName: name, object: panel, queue: .main) { [weak self, weak panel] _ in
                    MainActor.assumeIsolated {
                        guard let self, let panel else { return }
                        self.defaults.set(NSStringFromRect(panel.frame), forKey: self.preferenceKey + ".voice")
                    }
                })
            }
            voicePanel = panel
        }
        if presentsWindows { NSApp.activate(ignoringOtherApps: true); panel.makeKeyAndOrderFront(nil) }
    }

    func attach(window: NSWindow, app: AppModel, openSettings: @escaping () -> Void = {}) {
        self.openSettings = openSettings
        guard self.window !== window else { return }
        removeObservers()
        self.window = window; self.app = app
        companions.attach(desktop: self, app: app)
        app.presentations.window = window
        let delegate = DesktopWindowDelegate(desktop: self, previous: window.delegate)
        windowDelegate = delegate; window.delegate = delegate
        for name in [NSWindow.didMoveNotification, NSWindow.didResizeNotification, NSWindow.didEndLiveResizeNotification] {
            observers.append(NotificationCenter.default.addObserver(forName: name, object: window, queue: .main) { [weak self] _ in
                MainActor.assumeIsolated {
                    guard let self, !self.changingWindow else { return }
                    self.companions.parentChanged(resized: name == NSWindow.didResizeNotification)
                    self.saveWorkspaceFrame()
                }
            })
        }
        observers.append(NotificationCenter.default.addObserver(forName: NSApplication.didChangeScreenParametersNotification, object: nil, queue: .main) { [weak self] _ in
            MainActor.assumeIsolated { self?.recoverVisibleFrames() }
        })
        // An approval can arrive while the workspace is folded away. Reveal its owner.
        observers.append(NotificationCenter.default.addObserver(forName: NSWindow.willBeginSheetNotification, object: window, queue: .main) { [weak self] _ in
            MainActor.assumeIsolated { self?.expand(animated: false) }
        })
        interactionMonitor = NSEvent.addLocalMonitorForEvents(matching: [.leftMouseDown, .rightMouseDown, .otherMouseDown, .keyDown]) { [weak self] event in
            self?.handleWorkspaceInteraction(event)
            return event
        }
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
        let initial = NSRect(origin: NSPoint(x: screen.maxX - 116, y: screen.midY - DesktopGeometry.coreSize.height / 2), size: DesktopGeometry.coreSize)
        let coreOrigin = (savedCore ?? initial).origin
        core.setFrame(DesktopGeometry.fit(NSRect(origin: coreOrigin, size: DesktopGeometry.coreSize), within: screen), display: false)
        let savedWorkspace = savedFrame("workspace")
        let size = savedWorkspace?.size ?? NSSize(width: 1080, height: 760)
        let target = savedWorkspace.map { frame in
            let widened = NSRect(origin: frame.origin, size: NSSize(width: max(frame.width, DesktopGeometry.minimumWorkspace.width),
                                                                  height: max(frame.height, DesktopGeometry.minimumWorkspace.height)))
            return DesktopGeometry.fit(widened, within: DesktopGeometry.screen(for: frame, screens: screens))
        }
            ?? DesktopGeometry.workspace(beside: core.frame, size: size, screen: screen)
        window.setFrame(target, display: true)
        if presentsWindows { core.orderFrontRegardless() }
        defaults.set(true, forKey: preferenceKey + ".enabled")
        changingWindow = false
        expand(animated: animated)
    }

    func expand(animated: Bool = true) {
        cancelHoverTransition()
        showWorkspace(preview: false, animated: animated)
    }

    func revealMainContent() {
        companions.collapseDockedExpansion()
        expand(animated: false)
        if presentsWindows { window?.makeKeyAndOrderFront(nil) }
    }

    private func showWorkspace(preview: Bool, animated: Bool) {
        guard enabled, let window else { return }
        guard !preview || !window.isMiniaturized else { return }
        let alreadyExpanded = expanded
        transition = UUID(); previewing = preview; expanded = true
        recoverVisibleFrames()
        window.alphaValue = animated && !alreadyExpanded && !NSWorkspace.shared.accessibilityDisplayShouldReduceMotion ? 0 : 1
        if presentsWindows {
            if preview {
                // Hover is visual only: leave the active app and keyboard responder alone.
                window.orderFrontRegardless()
                corePanel?.orderFrontRegardless()
            } else {
                NSApp.activate(ignoringOtherApps: true)
                if window.isMiniaturized { window.deminiaturize(nil) }
                window.makeKeyAndOrderFront(nil)
            }
        }
        if window.alphaValue < 1 {
            NSAnimationContext.runAnimationGroup { context in
                context.duration = 0.18
                window.animator().alphaValue = 1
            }
        }
        companions.layout()
        if preview { trackPreviewPointer() }
    }

    func collapse(animated: Bool = true) {
        guard enabled, expanded, let window, window.attachedSheet == nil else { return }
        app?.dictation.stop()
        app?.flushDraft()
        guard app?.historyPersistence.failure == nil else { return }
        cancelHoverTransition()
        saveWorkspaceFrame()
        let token = UUID(); transition = token
        expanded = false; previewing = false; workspaceHovered = false; companionHovered = false
        companions.layout()
        hoverSuppressed = coreHovered
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
        cancelHoverTransition()
        transition = UUID(); changingWindow = true
        saveWorkspaceFrame(force: true)
        enabled = false; expanded = false; previewing = false
        companions.leaveFloatingMode()
        coreHovered = false; workspaceHovered = false; companionHovered = false; coreInteracting = false; hoverSuppressed = false
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
            companions.parentChanged()
        }
    }

    func shutdown() {
        transition = UUID()
        cancelHoverTransition()
        companions.shutdown(); companionSubscription = nil
        removeObservers(); corePanel?.orderOut(nil); corePanel?.contentView = nil; corePanel = nil
        voiceObservers.forEach(NotificationCenter.default.removeObserver); voiceObservers.removeAll()
        voicePanel?.orderOut(nil); voicePanel?.contentView = nil; voicePanel = nil
        if window?.delegate === windowDelegate { window?.delegate = windowDelegate?.previous }
        windowDelegate = nil
        window = nil; app = nil; openSettings = {}; coreHovered = false
        previewing = false; workspaceHovered = false; coreInteracting = false; hoverSuppressed = false
    }

    private func removeObservers() {
        observers.forEach(NotificationCenter.default.removeObserver); observers.removeAll()
        if let interactionMonitor { NSEvent.removeMonitor(interactionMonitor) }; interactionMonitor = nil
        cancelHoverTransition()
    }

    private func savedFrame(_ name: String) -> NSRect? {
        guard let value = defaults.string(forKey: preferenceKey + "." + name) else { return nil }
        let frame = NSRectFromString(value)
        guard [frame.minX, frame.minY, frame.width, frame.height].allSatisfy(\.isFinite), frame.width > 0, frame.height > 0 else { return nil }
        return frame
    }

    private func saveWorkspaceFrame(force: Bool = false) {
        guard enabled, expanded, (!changingWindow || force), let window else { return }
        defaults.set(NSStringFromRect(companions.preferredWorkspaceFrame ?? window.frame), forKey: preferenceKey + ".workspace")
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
        companions.layout()
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
        let host = DesktopCoreHost(rootView: DesktopCoreView(app: app, voice: app.liveVoice, desktop: self))
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

final class DesktopCoreHost: NSHostingView<DesktopCoreView> {
    weak var desktop: DesktopPresentation?
    private var hoverArea: NSTrackingArea?
    override func acceptsFirstMouse(for event: NSEvent?) -> Bool { true }
    override func updateTrackingAreas() {
        super.updateTrackingAreas()
        if let hoverArea { removeTrackingArea(hoverArea) }
        // The core is nonactivating: hovering must also work while another app is active.
        let area = NSTrackingArea(rect: bounds, options: [.mouseEnteredAndExited, .activeAlways, .inVisibleRect], owner: self, userInfo: nil)
        addTrackingArea(area); hoverArea = area
    }
    override func mouseEntered(with event: NSEvent) { desktop?.updateCoreHover(true) }
    override func mouseExited(with event: NSEvent) { desktop?.updateCoreHover(false) }
}

struct DesktopCoreHandle: NSViewRepresentable {
    let desktop: DesktopPresentation
    func makeNSView(context: Context) -> DesktopCoreDragView { let view = DesktopCoreDragView(); view.desktop = desktop; return view }
    func updateNSView(_ view: DesktopCoreDragView, context: Context) { view.desktop = desktop }
}

/// The cube owns dragging. The buttons below it retain native hit testing and accessibility.
final class DesktopCoreDragView: NSView {
    weak var desktop: DesktopPresentation?
    private var startPoint = NSPoint.zero
    private var startFrame = NSRect.zero
    private var dragged = false
    override func hitTest(_ point: NSPoint) -> NSView? { bounds.contains(point) ? self : nil }
    override func acceptsFirstMouse(for event: NSEvent?) -> Bool { true }
    override func resetCursorRects() { addCursorRect(bounds, cursor: .openHand) }
    override func mouseDown(with event: NSEvent) {
        desktop?.beginCoreInteraction()
        startPoint = DesktopPointer.screenLocation(of: event, in: window)
        startFrame = window?.frame ?? .zero; dragged = false
    }
    override func mouseDragged(with event: NSEvent) {
        let point = DesktopPointer.screenLocation(of: event, in: window)
        let dx = point.x - startPoint.x, dy = point.y - startPoint.y
        guard dragged || hypot(dx, dy) > 4 else { return }
        if !dragged { desktop?.beginCoreDrag() }
        dragged = true
        let proposed = startFrame.offsetBy(dx: dx, dy: dy)
        let screen = NSScreen.screens.first { $0.frame.contains(point) }?.visibleFrame
            ?? DesktopGeometry.screen(for: proposed, screens: NSScreen.screens.map(\.visibleFrame))
        window?.setFrame(DesktopGeometry.fit(proposed, within: screen), display: true)
    }
    override func mouseUp(with event: NSEvent) {
        desktop?.endCoreInteraction()
        if dragged { desktop?.coreMoved() }
        else { desktop?.toggleWorkspace() }
    }
    override func rightMouseDown(with event: NSEvent) {
        desktop?.beginCoreInteraction()
        defer { desktop?.endCoreInteraction() }
        let menu = NSMenu()
        let toggle = NSMenuItem(title: desktop?.previewing == true ? "Оставить открытым" : desktop?.expanded == true ? "Свернуть в ядро" : "Открыть Proto-Mind", action: #selector(toggleWorkspace), keyEquivalent: "")
        toggle.target = self; menu.addItem(toggle)
        let voice = NSMenuItem(title: "Голос Proto-Mind", action: #selector(openVoice), keyEquivalent: "")
        voice.target = self; menu.addItem(voice)
        for (title, action) in [("Боковое окно 1", #selector(toggleFirstCompanion)), ("Боковое окно 2", #selector(toggleSecondCompanion))] {
            let item = NSMenuItem(title: title, action: action, keyEquivalent: "")
            item.target = self; menu.addItem(item)
        }
        let restore = NSMenuItem(title: "Обычное окно", action: #selector(restoreWorkspace), keyEquivalent: "")
        restore.target = self; menu.addItem(restore)
        NSMenu.popUpContextMenu(menu, with: event, for: self)
    }
    @objc private func toggleWorkspace() { desktop?.toggleWorkspace() }
    @objc private func restoreWorkspace() { desktop?.restoreWindow() }
    @objc private func openVoice() { desktop?.openVoice() }
    @objc private func toggleFirstCompanion() { desktop?.companions.toggle(.first) }
    @objc private func toggleSecondCompanion() { desktop?.companions.toggle(.second) }
    override func isAccessibilityElement() -> Bool { true }
    override func accessibilityRole() -> NSAccessibility.Role? { .button }
    override func accessibilityLabel() -> String? { "Ядро Proto-Mind" }
    override func accessibilityHelp() -> String? { "Наведите курсор, чтобы заглянуть в чат и боковую панель. Нажмите, чтобы оставить открытыми, ещё раз — свернуть. Перетащите в удобное место." }
    override func accessibilityPerformPress() -> Bool { toggleWorkspace(); return true }
    override func accessibilityCustomActions() -> [NSAccessibilityCustomAction]? {
        [NSAccessibilityCustomAction(name: "Голос Proto-Mind", handler: { [weak self] in
            guard let desktop = self?.desktop else { return false }; desktop.openVoice(); return true
        }), NSAccessibilityCustomAction(name: "Обычное окно", handler: { [weak self] in
            guard let desktop = self?.desktop else { return false }; desktop.restoreWindow(); return true
        }), NSAccessibilityCustomAction(name: "Боковое окно 1", handler: { [weak self] in
            guard let desktop = self?.desktop else { return false }; desktop.companions.toggle(.first); return true
        }), NSAccessibilityCustomAction(name: "Боковое окно 2", handler: { [weak self] in
            guard let desktop = self?.desktop else { return false }; desktop.companions.toggle(.second); return true
        })]
    }
}

struct DesktopWindowAttachment: NSViewRepresentable {
    let app: AppModel
    let openSettings: () -> Void
    func makeNSView(context: Context) -> Attachment {
        let view = Attachment(); view.app = app; view.openSettings = openSettings; return view
    }
    func updateNSView(_ nsView: Attachment, context: Context) { nsView.app = app; nsView.openSettings = openSettings }
    final class Attachment: NSView {
        weak var app: AppModel?
        var openSettings: () -> Void = {}
        override func viewDidMoveToWindow() {
            super.viewDidMoveToWindow()
            guard let window, let app else { return }
            DispatchQueue.main.async { [weak window, weak app, openSettings] in
                guard let window, let app else { return }
                app.desktop.attach(window: window, app: app, openSettings: openSettings)
            }
        }
    }
}
