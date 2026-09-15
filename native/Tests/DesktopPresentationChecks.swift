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
        let origin = corePanel.frame.origin
        func mouse(_ type: NSEvent.EventType, _ point: NSPoint) -> NSEvent {
            NSEvent.mouseEvent(with: type, location: point, modifierFlags: [], timestamp: 1,
                              windowNumber: corePanel.windowNumber, context: nil, eventNumber: 1, clickCount: 1, pressure: 1)!
        }
        corePanel.contentView?.mouseDown(with: mouse(.leftMouseDown, NSPoint(x: 44, y: 40)))
        corePanel.contentView?.mouseDragged(with: mouse(.leftMouseDragged, NSPoint(x: 24, y: 65)))
        corePanel.contentView?.mouseUp(with: mouse(.leftMouseUp, NSPoint(x: 44, y: 40)))
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
        for width: CGFloat in [580, 800, 1100] {
            let size = host.sizeThatFits(in: CGSize(width: width, height: 740))
            try check(size.width <= width + 1 && size.height <= 741, "Glass workspace stays inside a \(Int(width))-point window")
        }
        desktop.enable(animated: false)
        desktop.shutdown()
        let restored = DesktopPresentation(stateDirectory: state, defaults: defaults, presentsWindows: false)
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
    }
}
