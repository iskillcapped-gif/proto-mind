import AppKit

extension NativeChecks {
    @MainActor
    static func companionHoverRecovery(root: URL) async throws {
        let suite = "proto-hover-recovery." + UUID().uuidString
        let defaults = UserDefaults(suiteName: suite)!
        defer { defaults.removePersistentDomain(forName: suite) }
        let state = root.appendingPathComponent("hover-recovery")
        var point = NSPoint(x: -90_000, y: -90_000)
        var pointerReads = 0
        let app = AppModel(configuration: LaunchConfiguration(projectRoot: root, python: root, stateDirectory: state), uiDefaults: defaults)
        let desktop = DesktopPresentation(stateDirectory: state, defaults: defaults, presentsWindows: true,
            pointerLocation: { pointerReads += 1; return point })
        let window = NSWindow(contentRect: NSRect(x: 100, y: 100, width: 1000, height: 700),
                              styleMask: [.titled, .resizable, .closable], backing: .buffered, defer: false)
        window.isReleasedWhenClosed = false
        let unrelated = NSWindow(contentRect: .zero, styleMask: [.titled], backing: .buffered, defer: false)
        unrelated.isReleasedWhenClosed = false
        defer { desktop.shutdown(); app.shutdown(); unrelated.close(); window.close() }
        desktop.attach(window: window, app: app)
        app.setComposer("Keep my task and draft")
        app.flushDraft()
        app.selectedExecution?.running = true
        let archive = app.currentHistoryArchive
        desktop.enable(animated: false)
        let companions = desktop.companions
        companions.toggle(.first); companions.toggle(.second)
        let first = companions.surface(.first).window!, second = companions.surface(.second).window!
        let core = desktop.corePanel!
        func center(_ rect: NSRect) -> NSPoint { NSPoint(x: rect.midX, y: rect.midY) }
        func mouse(_ type: NSEvent.EventType, in target: NSWindow) -> NSEvent {
            NSEvent.mouseEvent(with: type, location: NSPoint(x: 100, y: 80), modifierFlags: [], timestamp: 1,
                windowNumber: target.windowNumber, context: nil, eventNumber: 1, clickCount: 1, pressure: 1)!
        }
        for detached in [false, true] {
            desktop.expand(animated: false)
            if detached { companions.detach(.second) }
            desktop.collapse(animated: false)
            point = center(core.frame)
            desktop.updateCoreHover(false); desktop.updateCoreHover(true)
            try await Task.sleep(for: .milliseconds(280))
            try check(desktop.previewing && window.isVisible && first.isVisible && second.isVisible,
                      "Pointer-backed cube preview shows both companion windows (detached: \(detached))")

            // Focus/order can change while a child is shown; it is not a click.
            first.makeKeyAndOrderFront(nil)
            second.makeKeyAndOrderFront(nil)
            window.makeKeyAndOrderFront(nil)
            try check(desktop.previewing, "Window focus notifications alone never pin a cube preview")
            desktop.handleWorkspaceInteraction(mouse(.mouseMoved, in: first))
            desktop.handleWorkspaceInteraction(mouse(.leftMouseDown, in: unrelated))
            try check(desktop.previewing, "Pointer movement and input in unrelated windows do not pin the preview")

            point = center(second.frame)
            desktop.updateCoreHover(false)
            // Simulate overlapping/rebuilt tracking areas with enter events but
            // deliberately NO subsequent mouseExited events from either companion.
            companions.updateHover(.first, inside: true)
            companions.updateHover(.second, inside: true)
            try await Task.sleep(for: .milliseconds(650))
            try check(desktop.previewing && second.isVisible,
                      "The actual pointer inside a companion keeps the preview available for interaction")
            point = NSPoint(x: -90_000, y: -90_000)
            try await Task.sleep(for: .milliseconds(800))
            try check(!desktop.expanded && !window.isVisible && !first.isVisible && !second.isVisible,
                      "Leaving the group hides all windows despite missing companion exit events (detached: \(detached))")
            let readsAfterHide = pointerReads
            try await Task.sleep(for: .milliseconds(220))
            try check(pointerReads == readsAfterHide, "Hidden workspaces perform no pointer polling")
        }

        for keyboard in [false, true] {
            point = center(core.frame)
            desktop.updateCoreHover(false); desktop.updateCoreHover(true)
            try await Task.sleep(for: .milliseconds(280))
            let event = keyboard
                ? NSEvent.keyEvent(with: .keyDown, location: .zero, modifierFlags: [], timestamp: 1,
                    windowNumber: second.windowNumber, context: nil, characters: "x", charactersIgnoringModifiers: "x",
                    isARepeat: false, keyCode: 7)!
                : mouse(.leftMouseDown, in: first)
            desktop.handleWorkspaceInteraction(event)
            point = NSPoint(x: -90_000, y: -90_000)
            let readsAfterPin = pointerReads
            try await Task.sleep(for: .milliseconds(650))
            try check(desktop.expanded && !desktop.previewing && first.isVisible && second.isVisible,
                      "Intentional companion \(keyboard ? "keyboard" : "mouse") input pins the whole workspace")
            try check(pointerReads == readsAfterPin, "Pinned workspaces perform no pointer polling")
            desktop.collapse(animated: false)
        }
        try check(app.selectedExecution?.running == true && app.composer == "Keep my task and draft"
                  && app.currentHistoryArchive.conversations == archive.conversations && !app.liveVoice.inCall,
                  "Preview recovery and pinning preserve task ownership, history, draft and microphone state")
        point = center(core.frame)
        desktop.updateCoreHover(false); desktop.updateCoreHover(true)
        try await Task.sleep(for: .milliseconds(280))
        desktop.shutdown()
        let readsAfterShutdown = pointerReads
        try await Task.sleep(for: .milliseconds(220))
        try check(pointerReads == readsAfterShutdown, "Shutdown cancels the preview pointer task")
        app.selectedExecution?.running = false
    }
}
