import AppKit
import SwiftUI

extension NativeChecks {
    @MainActor
    static func regularCompanions(root: URL) async throws {
        let suite = "proto-regular-companions." + UUID().uuidString
        let defaults = UserDefaults(suiteName: suite)!
        defer { defaults.removePersistentDomain(forName: suite) }
        let state = root.appendingPathComponent("regular-companions")
        let app = AppModel(configuration: LaunchConfiguration(projectRoot: root, python: root, stateDirectory: state), uiDefaults: defaults)
        let desktop = DesktopPresentation(stateDirectory: state, defaults: defaults, pointerLocation: nil)
        let window = NSWindow(contentRect: NSRect(x: 80, y: 100, width: 1020, height: 700),
                              styleMask: [.titled, .resizable, .closable, .miniaturizable], backing: .buffered, defer: false)
        window.isReleasedWhenClosed = false; window.animationBehavior = .none
        defer { desktop.shutdown(); app.shutdown(); window.close() }
        desktop.attach(window: window, app: app)
        app.setComposer("Draft during a normal-window task"); app.flushDraft()
        app.selectedExecution?.running = true
        let archive = app.currentHistoryArchive
        let owner = desktop.companions
        owner.toggle(.first); owner.toggle(.second)
        let first = owner.surface(.first), second = owner.surface(.second)
        guard let upper = first.window, let lower = second.window else { throw NativeError.message("Missing regular companions") }
        let browser = NativeBrowserTab()
        let browserTab = first.panel.open(.browser(browser))
        let terminal = WorkspaceTerminal(directory: root)
        let terminalTab = second.panel.open(.terminal(terminal))
        terminal.start(executable: "/bin/cat", arguments: [])
        let processID = terminal.view.process.shellPid
        try check(!desktop.enabled && desktop.corePanel == nil && upper.isVisible && lower.isVisible
                  && upper.level == .normal && lower.level == .normal && !upper.isFloatingPanel
                  && upper.parent === window && lower.parent === window,
                  "Both companions open directly in normal mode without a cube or floating window level")
        let start = window.frame, top = upper.frame, bottom = lower.frame
        window.setFrameOrigin(NSPoint(x: start.minX - 20, y: start.minY - 15))
        try check(upper.frame == top.offsetBy(dx: -20, dy: -15) && lower.frame == bottom.offsetBy(dx: -20, dy: -15),
                  "Normal-mode attached windows move as native children without a second layout pass")
        owner.setTopFraction(0.6)
        try check(upper.frame.height > lower.frame.height && abs(upper.frame.minY - lower.frame.maxY - 8) < 1,
                  "Normal mode retains the shared height split and gap")
        let content = NSRect(x: 300, y: 0, width: window.frame.width - 300, height: window.frame.height - 38)
        desktop.updateRegularContentRect(content, in: window)
        owner.toggleExpansion(.first)
        try check(abs(upper.frame.minX - window.convertToScreen(content).minX) < 1
                  && abs(upper.frame.maxY - window.convertToScreen(content).maxY) < 1 && !lower.isVisible,
                  "Normal expansion respects the measured sidebar edge and leaves the native toolbar visible")
        var narrowerSidebar = content; narrowerSidebar.origin.x = 225
        desktop.updateRegularContentRect(narrowerSidebar, in: window)
        try check(abs(upper.frame.minX - window.convertToScreen(narrowerSidebar).minX) < 1,
                  "An expanded companion follows a resized regular sidebar")
        var underTitlebar = narrowerSidebar; underTitlebar.size.height = window.frame.height
        desktop.updateRegularContentRect(underTitlebar, in: window)
        try check(abs(upper.frame.maxY - window.convertToScreen(window.contentLayoutRect).maxY) < 1,
                  "A SwiftUI background extending under the titlebar cannot cover the regular toolbar")
        let pageID = UUID()
        first.presentations.present(id: pageID, content: AnyView(Text("Local companion settings")), clearBinding: {})
        try check(first.expanded && first.presentations.pages.count == 1 && app.presentations.pages.isEmpty,
                  "Normal-mode companion presentations stay expanded in their source window")
        desktop.enable(animated: false)
        try check(desktop.enabled && upper.level == .floating && upper.isFloatingPanel && first.expanded
                  && first.presentations.pages.count == 1 && first.window === upper && second.window === lower,
                  "Switching to the cube preserves an expanded window and its local presentation stack")
        desktop.restoreWindow()
        try check(upper.isVisible && first.expanded && first.presentations.pages.count == 1 && !desktop.enabled,
                  "Returning to normal retains that same expanded source window and page")
        first.presentations.dismissTop()
        desktop.revealMainContent()
        try check(!first.expanded && lower.isVisible, "Main settings can reveal the chat in normal mode by clearing covering expansions")
        owner.detach(.second)
        let free = DesktopGeometry.fit(NSRect(x: 100, y: 170, width: 330, height: 340), within: NSScreen.main!.visibleFrame)
        lower.setFrame(free, display: false)
        owner.toggleExpansion(.second)
        let large = lower.frame
        desktop.enable(animated: false); desktop.restoreWindow()
        try check(!second.docked && second.expanded && lower.parent == nil && lower.frame == large,
                  "Detached expansion keeps its independent frame through both mode changes")
        owner.toggleExpansion(.second)
        try check(lower.frame == free, "The miniature still returns to its own detached location in normal mode")
        owner.restoreBase(.second)
        try check(second.docked && lower.parent === window && lower.frame.minY == window.frame.minY
                  && abs(upper.frame.height - lower.frame.height) < 1,
                  "Normal-mode return-to-position restores the lower half and equal split")
        owner.detach(.second)
        owner.setKeepDetachedVisible(true)
        NotificationCenter.default.post(name: NSWindow.willMiniaturizeNotification, object: window)
        try check(!upper.isVisible && !lower.isVisible && first.visible && second.visible,
                  "Minimizing normal mode hides attached and detached windows without changing their enabled state")
        NotificationCenter.default.post(name: NSWindow.didDeminiaturizeNotification, object: window)
        try check(upper.isVisible && lower.isVisible && !second.docked,
                  "Restoring normal mode brings back both windows with their docking choices")
        window.performClose(nil)
        try check(!upper.isVisible && !lower.isVisible && desktop.reopen() && upper.isVisible && lower.isVisible,
                  "Closing and reopening the normal workspace preserves and restores companion windows")
        owner.toggle(.first)
        desktop.enable(animated: false); desktop.restoreWindow()
        try check(!first.visible && !upper.isVisible && second.visible && lower.isVisible,
                  "A hidden companion stays hidden through mode switches while its neighbour stays open")
        try check(first.panel.selectedID == browserTab && second.panel.selectedID == terminalTab
                  && terminal.running && terminal.view.process.shellPid == processID
                  && app.selectedExecution?.running == true && app.composer == "Draft during a normal-window task"
                  && app.currentHistoryArchive.conversations == archive.conversations && !app.liveVoice.inCall,
                  "Mode, docking and visibility changes preserve the real PTY, tabs, task, draft and dialog bytes")
        app.selectedExecution?.running = false
        desktop.shutdown()

        let restored = DesktopPresentation(stateDirectory: state, defaults: defaults, pointerLocation: nil)
        restored.attach(window: window, app: app)
        try check(!restored.enabled && !restored.companions.surface(.first).visible
                  && restored.companions.surface(.second).window?.isVisible == true
                  && restored.companions.surface(.second).window?.level == .normal && !restored.companions.surface(.second).docked,
                  "Normal-mode companion visibility and docking restore per profile without enabling the cube")
        restored.shutdown()
    }
}
