import AppKit
import SwiftUI

extension NativeChecks {
    @MainActor
    static func desktopCompanions(root: URL) async throws {
        for screen in [NSRect(x: 0, y: 20, width: 1315, height: 835), NSRect(x: -2560, y: -300, width: 2560, height: 1440), NSRect(x: 40, y: 10, width: 800, height: 580)] {
            for widths: [DesktopCompanionID: CGFloat] in [[:], [.first: 380], [.second: 900], [.first: 380, .second: 460], [.first: 2000, .second: 1800]] {
                let row = DesktopCompanionGeometry.row(workspace: NSRect(x: screen.maxX - 700, y: screen.maxY - 400, width: 1080, height: 780), widths: widths, screen: screen)
                try check(screen.insetBy(dx: -0.1, dy: -0.1).contains(row.bounds), "Attached row stays within its monitor, including narrow and negative-coordinate screens")
                var previous = row.workspace
                for id in DesktopCompanionID.allCases {
                    if let frame = row.panels[id] {
                        try check(abs(frame.minX - previous.maxX - DesktopCompanionGeometry.gap) < 0.1 && frame.minY == row.workspace.minY && frame.height == row.workspace.height,
                                  "Attached windows share workspace height and have independent non-overlapping widths")
                        previous = frame
                    }
                }
                try check(row.expanded.minX > row.workspace.minX && abs(row.expanded.maxX - row.bounds.maxX) < 0.1 && row.expanded.height == row.workspace.height,
                          "Attached expansion covers the workspace and companions while preserving the sidebar")
            }
        }
        let anchor = NSRect(x: 100, y: 100, width: 800, height: 650)
        try check(DesktopCompanionGeometry.shouldAttach(NSRect(x: 910, y: 150, width: 350, height: 400), beside: anchor)
                  && !DesktopCompanionGeometry.shouldAttach(NSRect(x: 940, y: 150, width: 350, height: 400), beside: anchor)
                  && !DesktopCompanionGeometry.shouldAttach(NSRect(x: 910, y: 900, width: 350, height: 400), beside: anchor),
                  "Snap requires a nearby right edge and actual vertical overlap")

        let suite = "proto-companion-checks." + UUID().uuidString
        let defaults = UserDefaults(suiteName: suite)!
        defer { defaults.removePersistentDomain(forName: suite) }
        let state = root.appendingPathComponent("companion-ui")
        let panels = WorkspacePanels(stateDirectory: state, defaults: defaults)
        panels.toggle()
        try check(!panels.lowerEnabled && panels.upper.visible && !panels.lower.visible,
                  "The internal panel defaults to one full-height surface")
        panels.setLowerEnabled(true)
        let retainedTab = panels.lower.open(.conversation(UUID()))
        panels.toggleExpansion(.lower)
        panels.setLowerEnabled(false)
        try check(panels.expanded == nil && panels.upper.visible && !panels.lower.visible && panels.lower.selectedID == retainedTab,
                  "Disabling the lower panel returns to the chat and retains its tabs")
        panels.setLowerEnabled(true)
        let restoredPanels = WorkspacePanels(stateDirectory: state, defaults: defaults)
        let otherPanels = WorkspacePanels(stateDirectory: root.appendingPathComponent("other-panels"), defaults: defaults)
        try check(restoredPanels.lowerEnabled && !otherPanels.lowerEnabled && panels.lower.selectedID == retainedTab,
                  "The optional lower panel persists per profile without destroying hidden content")
        let single = WorkspacePanelsLayout(size: CGSize(width: 1100, height: 780), visible: true, expanded: nil, horizontal: 0.48, vertical: 0.5, lowerEnabled: false)
        try check(single.upper.height == 780 && single.upper.minY == 0, "One internal panel uses the full available height")

        _ = NSApplication.shared
        let app = AppModel(configuration: LaunchConfiguration(projectRoot: root, python: root, stateDirectory: state), uiDefaults: defaults)
        let desktop = DesktopPresentation(stateDirectory: state, defaults: defaults, presentsWindows: false)
        let window = NSWindow(contentRect: NSRect(x: 100, y: 100, width: 1080, height: 720), styleMask: [.titled, .resizable, .closable], backing: .buffered, defer: false)
        window.isReleasedWhenClosed = false
        defer { desktop.shutdown(); app.shutdown(); window.close() }
        desktop.attach(window: window, app: app)
        app.setComposer("Keep the main draft")
        app.flushDraft()
        let archive = app.currentHistoryArchive
        app.selectedExecution?.running = true
        desktop.enable(animated: false)
        let companions = desktop.companions
        companions.toggle(.first); companions.toggle(.second)
        let first = companions.surface(.first), second = companions.surface(.second)
        guard let firstWindow = first.window, let secondWindow = second.window else { throw NativeError.message("Companion windows not created") }
        try check(firstWindow !== secondWindow && firstWindow !== window && firstWindow.frame.height == window.frame.height
                  && secondWindow.frame.minX > firstWindow.frame.maxX && firstWindow.canBecomeKey,
                  "Companions are separate interactive AppKit windows arranged beside the main workspace")
        func dragArea(_ view: NSView) -> CompanionDragArea.DragArea? {
            if let view = view as? CompanionDragArea.DragArea { return view }
            return view.subviews.compactMap { dragArea($0) }.first
        }
        firstWindow.contentView?.layoutSubtreeIfNeeded()
        guard let handle = firstWindow.contentView.flatMap({ dragArea($0) }) else { throw NativeError.message("Missing companion drag handle") }
        try check(handle.frame.height <= 34, "The drag header stays compact instead of absorbing the window height")
        func mouse(_ type: NSEvent.EventType, _ point: NSPoint) -> NSEvent {
            NSEvent.mouseEvent(with: type, location: point, modifierFlags: [], timestamp: 1,
                windowNumber: firstWindow.windowNumber, context: nil, eventNumber: 1, clickCount: 1, pressure: 1)!
        }
        handle.mouseDown(with: mouse(.leftMouseDown, NSPoint(x: 150, y: 600)))
        handle.mouseUp(with: mouse(.leftMouseUp, NSPoint(x: 150, y: 600)))
        try check(first.docked, "A title-bar click never detaches the window")
        let beforeDrag = firstWindow.frame
        handle.mouseDown(with: mouse(.leftMouseDown, NSPoint(x: 150, y: 600)))
        handle.mouseDragged(with: mouse(.leftMouseDragged, NSPoint(x: 70, y: 540)))
        handle.mouseUp(with: mouse(.leftMouseUp, NSPoint(x: 70, y: 540)))
        try check(!first.docked && firstWindow.frame != beforeDrag, "Native drag events detach and move the companion without depending on global cursor polling")
        companions.toggleDocking(.first)
        let browser = NativeBrowserTab()
        let browserID = first.panel.open(.browser(browser))
        let terminal = WorkspaceTerminal(directory: root)
        let terminalID = second.panel.open(.terminal(terminal))
        let small = firstWindow.frame
        companions.toggleExpansion(.first)
        try check(firstWindow.frame.minX == window.frame.minX + DesktopGeometry.sidebarWidth(total: window.frame.width) + 10
                  && firstWindow.frame.maxX >= secondWindow.frame.maxX && first.expanded,
                  "A docked corner expands exactly to the sidebar and over the second window")
        companions.toggleExpansion(.first)
        try check(firstWindow.frame == small && first.panel.selectedID == browserID && second.panel.selectedID == terminalID,
                  "Returning from expansion preserves exact compact geometry and both selected tabs")
        companions.beginDrag(.second)
        let free = DesktopGeometry.fit(NSRect(x: 150, y: 170, width: 350, height: 380), within: NSScreen.main!.visibleFrame)
        secondWindow.setFrame(free, display: false)
        companions.endDrag(.second)
        try check(!second.docked && secondWindow.frame == free, "Dragging away detaches the window and keeps its independent frame")
        companions.toggleExpansion(.second)
        let large = DesktopGeometry.fit(NSRect(x: free.minX + 20, y: free.minY + 15, width: 700, height: 610), within: NSScreen.main!.visibleFrame)
        secondWindow.setFrame(large, display: false)
        companions.toggleExpansion(.second)
        try check(secondWindow.frame == free, "Detached compact size and position survive resizing the expanded window")
        companions.toggleExpansion(.second)
        try check(secondWindow.frame == large, "Detached expansion reuses its separately adjusted size and position")
        companions.toggleExpansion(.second)
        companions.toggle(.second); companions.toggle(.second)
        try check(second.window === secondWindow && second.panel.selectedID == terminalID && secondWindow.frame == free && !terminal.running,
                  "Hide and show retain the same terminal and NSWindow without launching a process")
        companions.beginDrag(.second)
        secondWindow.setFrameOrigin(NSPoint(x: firstWindow.frame.maxX + 10, y: firstWindow.frame.minY + 20))
        companions.endDrag(.second)
        try check(second.docked && secondWindow.frame.height == window.frame.height,
                  "Dragging beside the preceding window snaps back to the full-height row")
        companions.toggleExpansion(.second)
        desktop.revealMainContent()
        try check(!second.expanded && !first.expanded && desktop.expanded, "Opening main content clears covering expansions so settings and confirmations remain usable")
        companions.toggleDocking(.second)
        desktop.collapse(animated: false)
        try check(!desktop.expanded && first.visible && second.visible && app.selectedExecution?.running == true
                  && app.currentHistoryArchive.conversations == archive.conversations && app.composer == "Keep the main draft",
                  "Folding the workspace retains companion choices, the running conversation and draft")
        desktop.expand(animated: false)
        companions.setTransparency(0.13, for: .first); companions.setTransparency(0.77, for: .second)
        desktop.restoreWindow(); desktop.enable(animated: false)
        try check(first.window === firstWindow && second.window === secondWindow && first.panel.selectedID == browserID && second.panel.selectedID == terminalID,
                  "Normal and floating mode transitions retain companion browser and terminal ownership")
        let saved = DesktopCompanionWindows(stateDirectory: state, defaults: defaults, presentsWindows: false)
        let other = DesktopCompanionWindows(stateDirectory: root.appendingPathComponent("other-companions"), defaults: defaults, presentsWindows: false)
        try check(saved.surface(.first).transparency == 0.13 && saved.surface(.second).transparency == 0.77 && !saved.surface(.second).docked
                  && !other.surface(.first).visible && other.surface(.first).transparency == DesktopGlassAppearance.chatDefault,
                  "Separate transparency, docking and visibility preferences persist only in their UI profile")
        saved.setTransparency(.nan, for: .first); saved.setTransparency(9, for: .second)
        try check(saved.surface(.first).transparency == DesktopGlassAppearance.chatDefault && saved.surface(.second).transparency == 1,
                  "Invalid companion transparency is clamped without changing text opacity")
        app.selectedExecution?.running = false
        desktop.shutdown()
        try check(first.window == nil && second.window == nil && first.panel.tabs.isEmpty && second.panel.tabs.isEmpty,
                  "Shutdown releases both floating windows and their owned sessions")
    }
}
