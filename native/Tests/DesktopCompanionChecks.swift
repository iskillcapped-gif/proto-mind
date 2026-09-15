import AppKit
import SwiftUI

extension NativeChecks {
    @MainActor
    static func desktopCompanions(root: URL) async throws {
        for screen in [NSRect(x: 0, y: 20, width: 1315, height: 835), NSRect(x: -2560, y: -300, width: 2560, height: 1440), NSRect(x: 40, y: 10, width: 800, height: 580)] {
            for widths: [DesktopCompanionID: CGFloat] in [[:], [.first: 380], [.second: 900], [.first: 380, .second: 460], [.first: 2000, .second: 1800]] {
                let row = DesktopCompanionGeometry.row(workspace: NSRect(x: screen.maxX - 700, y: screen.maxY - 400, width: 1080, height: 780), widths: widths, screen: screen)
                try check(screen.insetBy(dx: -0.1, dy: -0.1).contains(row.bounds), "Attached row stays within its monitor, including narrow and negative-coordinate screens")
                for id in DesktopCompanionID.allCases {
                    if let frame = row.panels[id] {
                        try check(abs(frame.minX - row.workspace.maxX - DesktopCompanionGeometry.gap) < 0.1
                                  && frame.height <= row.workspace.height && frame.minY >= row.workspace.minY,
                                  "Attached windows share a right-hand column within the workspace height")
                    }
                }
                if let top = row.panels[.first], let bottom = row.panels[.second] {
                    try check(abs(top.height - bottom.height) < 0.1 && top.width == bottom.width
                              && top.maxY == row.workspace.maxY && bottom.minY == row.workspace.minY
                              && abs(top.minY - bottom.maxY - DesktopCompanionGeometry.gap) < 0.1,
                              "Two attached windows divide the workspace height equally with a small vertical gap")
                }
                try check(row.expanded.minX > row.workspace.minX && abs(row.expanded.maxX - row.bounds.maxX) < 0.1 && row.expanded.height == row.workspace.height,
                          "Attached expansion covers the workspace and companions while preserving the sidebar")
            }
        }
        let anchor = NSRect(x: 100, y: 100, width: 800, height: 650)
        let stacked = DesktopCompanionGeometry.row(workspace: anchor, widths: [.first: 380, .second: 380],
                                                   screen: NSRect(x: 0, y: 0, width: 1800, height: 1000), topFraction: 0.7)
        try check(stacked.panels[.first]!.height > stacked.panels[.second]!.height
                  && abs(stacked.panels.values.reduce(0) { $0 + $1.height } + DesktopCompanionGeometry.gap - anchor.height) < 0.1,
                  "Unequal split heights remain complementary and preserve the total height")
        try check(DesktopCompanionGeometry.shouldStack(stacked.panels[.second]!, with: stacked.panels[.first]!, id: .second)
                  && DesktopCompanionGeometry.shouldStack(stacked.panels[.first]!, with: stacked.panels[.second]!, id: .first)
                  && !DesktopCompanionGeometry.shouldStack(stacked.panels[.second]!.offsetBy(dx: 800, dy: 0), with: stacked.panels[.first]!, id: .second),
                  "Sibling docking accepts the adjoining horizontal edges and rejects distant columns")
        for fraction: CGFloat in [-20, 0, 0.5, 1, 20, .nan] {
            let height = DesktopCompanionGeometry.topHeight(total: 520, fraction: fraction)
            try check(height >= 200 && height <= 312, "Split limits keep both attached windows usable")
        }
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
        let desktop = DesktopPresentation(stateDirectory: state, defaults: defaults, presentsWindows: true, pointerLocation: nil)
        let window = CompanionDragCheckWindow(contentRect: NSRect(x: 100, y: 100, width: 1080, height: 720), styleMask: [.titled, .resizable, .closable], backing: .buffered, defer: false)
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
        try check(firstWindow !== secondWindow && firstWindow !== window && firstWindow.frame.maxY == window.frame.maxY
                  && secondWindow.frame.minY == window.frame.minY && firstWindow.frame.minX == secondWindow.frame.minX
                  && firstWindow.canBecomeKey && firstWindow.parent === window && secondWindow.parent === window,
                  "Stacked companions are interactive child windows in the main window's system movement group")
        let startMain = window.frame, startFirst = firstWindow.frame, startSecond = secondWindow.frame
        // Repeated, reversing movements also cross the screen edge. A position
        // notification must never clamp/reflow the group back under the pointer.
        for delta in [NSPoint(x: -45, y: 25), NSPoint(x: -140, y: -60), .zero,
                      NSPoint(x: 30, y: -20), NSPoint(x: -15, y: 25), .zero] {
            window.setFrameOrigin(NSPoint(x: startMain.minX + delta.x, y: startMain.minY + delta.y))
            NotificationCenter.default.post(name: NSWindow.didResizeNotification, object: window)
            try await Task.sleep(for: .milliseconds(20))
            try check(window.frame == startMain.offsetBy(dx: delta.x, dy: delta.y)
                      && firstWindow.frame == startFirst.offsetBy(dx: delta.x, dy: delta.y)
                      && secondWindow.frame == startSecond.offsetBy(dx: delta.x, dy: delta.y),
                      "Repeated parent moves and delayed frame notifications preserve the exact group translation")
        }
        let mainHandle = DesktopWindowDragArea.DragArea(frame: NSRect(x: 400, y: 600, width: 200, height: 32))
        window.contentView?.addSubview(mainHandle)
        let down = NSEvent.mouseEvent(with: .leftMouseDown, location: NSPoint(x: 450, y: 610), modifierFlags: [],
            timestamp: 1, windowNumber: window.windowNumber, context: nil, eventNumber: 71, clickCount: 1, pressure: 1)!
        mainHandle.mouseDown(with: down)
        try check(window.dragEvent === down && window.frame == startMain,
                  "The header hands the original mouse-down to AppKit without running competing frame calculations")
        mainHandle.removeFromSuperview()
        companions.setTopFraction(0.6)
        let beforeResize = firstWindow.frame.height
        var resized = secondWindow.frame; resized.size.height += 30
        secondWindow.setFrame(resized, display: false)
        try check(abs(firstWindow.frame.height - beforeResize + 30) < 0.5
                  && abs(firstWindow.frame.height + secondWindow.frame.height + DesktopCompanionGeometry.gap - window.frame.height) < 0.5,
                  "Resizing one attached window immediately resizes the other while keeping the total height (before \(beforeResize), top \(firstWindow.frame.height), bottom \(secondWindow.frame.height), total \(window.frame.height), fraction \(companions.topFraction))")
        let beforeSplit = firstWindow.frame.height
        companions.resizeStack(topHeight: beforeSplit + 20)
        try check(abs(firstWindow.frame.height - beforeSplit - 20) < 0.5,
                  "Dragging the shared split updates both frames through the same geometry")
        companions.setTopFraction(0.5)
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
        func capturedMouse(_ type: CGEventType, _ dx: CGFloat, _ dy: CGFloat) -> NSEvent {
            let point = NSPoint(x: beforeDrag.minX + 150 + dx, y: beforeDrag.maxY - 18 + dy)
            let screenHeight = NSScreen.screens.first!.frame.height
            return NSEvent(cgEvent: CGEvent(mouseEventSource: nil, mouseType: type,
                mouseCursorPosition: NSPoint(x: point.x, y: screenHeight - point.y), mouseButton: .left)!)!
        }
        let capturedDown = capturedMouse(.leftMouseDown, 0, 0)
        let capturedDrags = [capturedMouse(.leftMouseDragged, -80, -30),
                             capturedMouse(.leftMouseDragged, -100, -60),
                             capturedMouse(.leftMouseDragged, -80, -60)]
        let capturedUp = capturedMouse(.leftMouseUp, -80, -60)
        handle.mouseDown(with: capturedDown)
        for event in capturedDrags { handle.mouseDragged(with: event) }
        try check(firstWindow.frame.origin == beforeDrag.offsetBy(dx: -80, dy: -60).origin,
                  "Queued drag events use their captured screen coordinates, without compounding earlier movement")
        handle.mouseUp(with: capturedUp)
        try check(!first.docked && firstWindow.frame != beforeDrag, "Native drag events detach and move the companion without depending on global cursor polling")
        try check(firstWindow.parent == nil && secondWindow.parent === window && secondWindow.frame.height == startSecond.height,
                  "Detachment leaves the movement group while the other window keeps its lower slot")
        companions.restoreBase(.first)
        let browser = NativeBrowserTab()
        let browserID = first.panel.open(.browser(browser))
        let terminal = WorkspaceTerminal(directory: root)
        let terminalID = second.panel.open(.terminal(terminal))
        let small = firstWindow.frame
        companions.toggleExpansion(.first)
        try check(abs(firstWindow.frame.minX - (window.frame.minX + DesktopGeometry.sidebarWidth(total: window.frame.width) + 10)) <= 1
                  && firstWindow.frame.maxX >= secondWindow.frame.maxX - 1 && first.expanded,
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
        // A tall free window overlaps its neighbour while being dragged to the
        // edge. Attachment must reset the split and width, not reuse that frame.
        companions.setTopFraction(0.7)
        companions.beginDrag(.second)
        secondWindow.setFrame(NSRect(x: window.frame.maxX + DesktopCompanionGeometry.gap,
            y: window.frame.minY, width: 700, height: window.frame.height), display: false)
        companions.endDrag(.second)
        try await Task.sleep(for: .milliseconds(50))
        try check(second.docked && secondWindow.parent === window && companions.topFraction == 0.5
                  && abs(firstWindow.frame.height - secondWindow.frame.height) <= 1
                  && abs(firstWindow.frame.minY - secondWindow.frame.maxY - DesktopCompanionGeometry.gap) < 0.5
                  && secondWindow.frame.minY == window.frame.minY && firstWindow.frame.width == secondWindow.frame.width,
                  "A large free window snaps into its lower half after SwiftUI layout, without overlapping its neighbour")
        let baseFirst = firstWindow.frame, baseSecond = secondWindow.frame
        companions.restoreBase(.second); companions.restoreBase(.second)
        try check(firstWindow.frame == baseFirst && secondWindow.frame == baseSecond && second.docked,
                  "Return-to-base is idempotent even when the window is already attached")
        companions.detach(.first); companions.toggleExpansion(.first)
        firstWindow.setFrame(large, display: false)
        companions.toggleExpansion(.second)
        companions.restoreBase(.first)
        try await Task.sleep(for: .milliseconds(50))
        try check(first.docked && !first.expanded && !second.expanded && firstWindow.frame == baseFirst
                  && secondWindow.frame == baseSecond && first.panel.selectedID == browserID && second.panel.selectedID == terminalID,
                  "Return-to-base clears free and covering expansions and restores both slots without recreating content")
        companions.toggle(.first)
        companions.restoreBase(.second)
        try check(secondWindow.frame == baseSecond, "The lower base remains half-height even when the upper window is hidden")
        companions.toggle(.first)
        companions.detach(.second)
        companions.beginDrag(.second)
        secondWindow.setFrameOrigin(NSPoint(x: firstWindow.frame.minX + 5,
            y: firstWindow.frame.minY - DesktopCompanionGeometry.gap - secondWindow.frame.height))
        companions.endDrag(.second)
        try check(second.docked && secondWindow.frame == baseSecond, "Dropping below the upper sibling uses the same canonical lower slot")
        companions.toggleExpansion(.second)
        desktop.revealMainContent()
        try check(!second.expanded && !first.expanded && desktop.expanded, "Opening main content clears covering expansions so settings and confirmations remain usable")
        companions.detach(.second)
        desktop.collapse(animated: false)
        try check(!desktop.expanded && first.visible && second.visible && !firstWindow.isVisible && !secondWindow.isVisible
                  && firstWindow.parent == nil && secondWindow.parent == nil && !companions.keepDetachedVisible
                  && app.selectedExecution?.running == true && app.currentHistoryArchive.conversations == archive.conversations
                  && app.composer == "Keep the main draft",
                  "Folding hides attached and detached windows by default while retaining their content and running work")
        desktop.updateCoreHover(true)
        try await Task.sleep(for: .milliseconds(260))
        try check(desktop.previewing && firstWindow.parent === window && !second.docked
                  && firstWindow.isVisible && secondWindow.isVisible && !window.isKeyWindow,
                  "Cube hover restores attached ownership and includes the free window in the same preview")
        desktop.updateCoreHover(false)
        companions.updateHover(.first, inside: false); companions.updateHover(.second, inside: false)
        try await Task.sleep(for: .milliseconds(520))
        try check(!desktop.expanded && !firstWindow.isVisible && !secondWindow.isVisible,
                  "Leaving the cube hides both windows, including the detached one")
        companions.setKeepDetachedVisible(true)
        try check(secondWindow.isVisible && !firstWindow.isVisible && !desktop.expanded,
                  "The explicit preference keeps only detached windows visible while folded")
        let independent = DesktopCompanionWindows(stateDirectory: state, defaults: defaults, presentsWindows: false)
        try check(independent.keepDetachedVisible, "Independent visibility is explicitly persisted in the same UI profile")
        companions.setKeepDetachedVisible(false)
        try check(!secondWindow.isVisible, "Turning off independent visibility immediately hides the folded free window")
        desktop.expand(animated: false)
        companions.setTransparency(0.13, for: .first); companions.setTransparency(0.77, for: .second)
        companions.setTopFraction(0.65)
        desktop.restoreWindow(); desktop.enable(animated: false)
        try check(first.window === firstWindow && second.window === secondWindow && first.panel.selectedID == browserID && second.panel.selectedID == terminalID,
                  "Normal and floating mode transitions retain companion browser and terminal ownership")
        let saved = DesktopCompanionWindows(stateDirectory: state, defaults: defaults, presentsWindows: false)
        let other = DesktopCompanionWindows(stateDirectory: root.appendingPathComponent("other-companions"), defaults: defaults, presentsWindows: false)
        try check(saved.surface(.first).transparency == 0.13 && saved.surface(.second).transparency == 0.77 && !saved.surface(.second).docked
                  && saved.topFraction == 0.65 && other.topFraction == 0.5
                  && !saved.keepDetachedVisible && !other.keepDetachedVisible
                  && !other.surface(.first).visible && other.surface(.first).transparency == DesktopGlassAppearance.chatDefault,
                  "Separate transparency, docking and visibility preferences persist only in their UI profile")
        saved.setTransparency(.nan, for: .first); saved.setTransparency(9, for: .second)
        try check(saved.surface(.first).transparency == DesktopGlassAppearance.chatDefault && saved.surface(.second).transparency == 1,
                  "Invalid companion transparency is clamped without changing text opacity")
        app.selectedExecution?.running = false
        desktop.shutdown()
        try check(first.window == nil && second.window == nil && first.panel.tabs.isEmpty && second.panel.tabs.isEmpty,
                  "Shutdown releases both floating windows and their owned sessions")
        try await companionHoverRecovery(root: root)
        try await desktopWindowTransitions(root: root)
    }
}

@MainActor
private final class CompanionDragCheckWindow: NSWindow {
    var dragEvent: NSEvent?
    override func performDrag(with event: NSEvent) { dragEvent = event }
}
