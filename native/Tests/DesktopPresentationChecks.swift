import AppKit
import SwiftUI

extension NativeChecks {
    @MainActor
    static func desktopPresentation(root: URL) throws {
        let laptop = NSRect(x: 0, y: 40, width: 1440, height: 860)
        let leftDisplay = NSRect(x: -1920, y: 0, width: 1920, height: 1080)
        let core = NSRect(x: -100, y: 900, width: 88, height: 108)
        try check(DesktopGeometry.screen(for: core, screens: [laptop, leftDisplay]) == leftDisplay,
                  "Desktop core selects a monitor with negative coordinates")
        let recovered = DesktopGeometry.fit(core, within: laptop)
        try check(laptop.contains(recovered) && recovered.size == core.size,
                  "Unplugged monitor recovery keeps the entire core reachable")
        for screen in [laptop, leftDisplay, NSRect(x: 20, y: 20, width: 600, height: 520)] {
            for x in [screen.minX, screen.maxX - 88] {
                let anchor = NSRect(x: x, y: screen.midY, width: 88, height: 108)
                let workspace = DesktopGeometry.workspace(beside: anchor, size: NSSize(width: 800, height: 740), screen: screen)
                try check(screen.contains(workspace), "Expanded desktop workspace fits either screen edge, including a small display")
            }
        }
        let invalid = NSRect(x: CGFloat.nan, y: CGFloat.infinity, width: 8000, height: 740)
        try check(laptop.contains(DesktopGeometry.fit(invalid, within: laptop)), "Corrupt or oversized saved window geometry remains recoverable")

        _ = NSApplication.shared
        let suite = "proto-mind-desktop-checks." + UUID().uuidString
        let defaults = UserDefaults(suiteName: suite)!
        defer { defaults.removePersistentDomain(forName: suite) }
        let state = root.appendingPathComponent("desktop-presentation")
        let app = AppModel(configuration: LaunchConfiguration(projectRoot: root, python: root, stateDirectory: state))
        let desktop = DesktopPresentation(stateDirectory: state, defaults: defaults, presentsWindows: false)
        desktop.setChatTransparency(0.72)
        desktop.setSidebarTransparency(0.18)
        let otherState = DesktopPresentation(stateDirectory: root.appendingPathComponent("other-desktop"), defaults: defaults, presentsWindows: false)
        try check(otherState.chatTransparency == DesktopGlassAppearance.chatDefault
                  && otherState.sidebarTransparency == DesktopGlassAppearance.sidebarDefault,
                  "Glass preferences are isolated from other private-state namespaces")
        let window = NSWindow(contentRect: NSRect(x: 100, y: 100, width: 1000, height: 700),
                              styleMask: [.titled, .resizable, .closable], backing: .buffered, defer: false)
        window.isReleasedWhenClosed = false
        defer { desktop.shutdown(); app.shutdown(); window.close() }
        desktop.attach(window: window, app: app)
        try check(!desktop.enabled && !FileManager.default.fileExists(atPath: state.path),
                  "Attaching desktop UI grants no access and does not create private state")
        app.setComposer("Unsent draft survives every presentation")
        app.flushDraft()
        let execution = app.selectedExecution!
        execution.running = true
        let selectedID = app.selectedID
        let archive = app.currentHistoryArchive
        let originalStyle = window.styleMask
        desktop.enable(animated: false)
        try check(desktop.enabled && desktop.expanded && desktop.window === window
                  && desktop.corePanel?.canBecomeKey == false && desktop.corePanel?.canBecomeMain == false,
                  "Floating mode reuses the workspace while the core cannot steal keyboard focus")
        desktop.collapse(animated: false)
        try check(!desktop.expanded && desktop.enabled && execution.running
                  && app.selectedExecution === execution && app.selectedID == selectedID
                  && app.composer == "Unsent draft survives every presentation",
                  "Collapsing does not stop or replace the running task, selected dialog or draft")
        let corePanel = desktop.corePanel!
        corePanel.contentView?.layoutSubtreeIfNeeded()
        let coreHost = corePanel.contentView as! DesktopCoreHost
        coreHost.updateTrackingAreas()
        try check(coreHost.trackingAreas.contains { $0.options.contains(.activeAlways) }
                  && !desktop.coreHovered,
                  "Hidden core controls track hovering even when another app owns keyboard focus")
        let hover = NSEvent.enterExitEvent(with: .mouseEntered, location: .zero, modifierFlags: [], timestamp: 1,
                                          windowNumber: corePanel.windowNumber, context: nil, eventNumber: 1,
                                          trackingNumber: 1, userData: nil)!
        coreHost.mouseEntered(with: hover)
        try check(desktop.coreHovered && !desktop.expanded && !app.liveVoice.inCall,
                  "Entering the core reveals controls without opening a window or starting voice")
        coreHost.mouseExited(with: hover)
        try check(!desktop.coreHovered, "Leaving the entire core hides its controls again")
        func dragHandle(_ view: NSView) -> DesktopCoreDragView? {
            if let handle = view as? DesktopCoreDragView { return handle }
            return view.subviews.compactMap { dragHandle($0) }.first
        }
        guard let handle = corePanel.contentView.flatMap({ dragHandle($0) }) else {
            throw NativeError.message("Core drag handle was not mounted")
        }
        try check(handle.accessibilityCustomActions()?.map(\.name) == ["Голос Proto-Mind", "Обычное окно"],
                  "Both core actions remain accessible without pointer hovering")
        let origin = corePanel.frame.origin
        func mouse(_ type: NSEvent.EventType, _ point: NSPoint) -> NSEvent {
            NSEvent.mouseEvent(with: type, location: point, modifierFlags: [], timestamp: 1,
                              windowNumber: corePanel.windowNumber, context: nil, eventNumber: 1, clickCount: 1, pressure: 1)!
        }
        handle.mouseDown(with: mouse(.leftMouseDown, NSPoint(x: 44, y: 60)))
        handle.mouseDragged(with: mouse(.leftMouseDragged, NSPoint(x: 24, y: 85)))
        handle.mouseUp(with: mouse(.leftMouseUp, NSPoint(x: 44, y: 60)))
        try check(corePanel.frame.origin != origin && !desktop.expanded,
                  "Dragging follows event coordinates, moves the core and does not turn into a click")
        desktop.expand(animated: false)
        try check(desktop.expanded && app.currentHistoryArchive.conversations == archive.conversations
                  && !app.liveVoice.inCall && !app.cloudConsent && !app.fullAccessEnabled,
                  "Reopening keeps history intact and never starts voice or grants permissions")
        window.performClose(nil)
        try check(!desktop.expanded && desktop.enabled && execution.running,
                  "Close folds a floating workspace without destroying its running task")
        desktop.expand(animated: false)
        desktop.restoreWindow()
        try check(!desktop.enabled && window.styleMask == originalStyle && window.level == .normal
                  && execution.running && app.selectedExecution === execution,
                  "Returning to the regular window restores its level and preserves execution")
        execution.running = false

        let host = NSHostingController(rootView: FloatingWorkspaceView(app: app, desktop: desktop))
        for width: CGFloat in [780, 940, 1100] {
            let size = host.sizeThatFits(in: CGSize(width: width, height: 740))
            try check(size.width <= width + 1 && size.height <= 741, "Glass workspace stays inside a \(Int(width))-point window")
        }
        desktop.enable(animated: false)
        desktop.shutdown()
        let restored = DesktopPresentation(stateDirectory: state, defaults: defaults, presentsWindows: false)
        try check(restored.chatTransparency == 0.72 && restored.sidebarTransparency == 0.18,
                  "Both glass backgrounds keep independent transparency across restart")
        restored.setChatTransparency(.nan); restored.setSidebarTransparency(4)
        try check(restored.chatTransparency == DesktopGlassAppearance.chatDefault && restored.sidebarTransparency == 1,
                  "Invalid glass opacity cannot make the whole window or its controls disappear")
        restored.attach(window: window, app: app)
        try check(restored.enabled && restored.expanded && !app.liveVoice.inCall,
                  "Desktop mode survives restart without automatically opening the microphone")
        restored.restoreWindow(); restored.shutdown()
        let audio = LiveVoiceAudio()
        var playbackLevel = 1.0
        audio.onPlaybackLevel = { playbackLevel = $0 }
        audio.stop()
        try check(playbackLevel == 0 && audio.capturedFrames == 0,
                  "Stopped playback clears the desktop glow without starting an audio device")
        var settingsOpened = false
        app.presentLiveVoice { settingsOpened = true }
        try check(settingsOpened && app.settingsSection == .voice && !app.showLiveVoice
                  && !app.liveVoice.inCall && !app.cloudConsent,
                  "Unconfigured voice opens Settings directly without capturing audio or changing consent")
    }
}
