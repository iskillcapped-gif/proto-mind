import AppKit

extension NativeChecks {
    @MainActor
    static func desktopWindowTransitions(root: URL) async throws {
        let suite = "proto-desktop-transitions." + UUID().uuidString
        let defaults = UserDefaults(suiteName: suite)!
        defer { defaults.removePersistentDomain(forName: suite) }
        let state = root.appendingPathComponent("desktop-transitions")
        let app = AppModel(configuration: LaunchConfiguration(projectRoot: root, python: root, stateDirectory: state), uiDefaults: defaults)
        var reduceMotion = false
        let desktop = DesktopPresentation(stateDirectory: state, defaults: defaults, presentsWindows: true,
            pointerLocation: nil, reduceMotion: { reduceMotion })
        let window = NSWindow(contentRect: NSRect(x: 100, y: 100, width: 1000, height: 700),
                              styleMask: [.titled, .resizable, .closable], backing: .buffered, defer: false)
        window.isReleasedWhenClosed = false
        window.animationBehavior = .documentWindow
        defer { desktop.shutdown(); app.shutdown(); window.close() }
        desktop.attach(window: window, app: app)
        app.setComposer("Keep the draft while the windows fade")
        app.flushDraft()
        let archive = app.currentHistoryArchive
        app.selectedExecution?.running = true
        desktop.enable(animated: false)
        let companions = desktop.companions
        companions.toggle(.first); companions.toggle(.second)
        let first = companions.surface(.first).window!, second = companions.surface(.second).window!
        let core = desktop.corePanel!
        let group = [window, first, second]
        try check(group.allSatisfy { $0.animationBehavior == .none },
                  "Floating windows disable independent automatic ordering animations")

        // Observe actual AppKit opacity/ordering throughout each transition, not
        // just its final state. The previous code hid the companions at time zero.
        func sample(_ followers: [NSWindow], independent: NSWindow? = nil) async throws -> Int {
            var intermediateFrames = 0
            for _ in 0..<24 {
                let visible = followers.map(\.isVisible)
                let alpha = followers.map(\.alphaValue)
                guard visible.allSatisfy({ $0 == visible[0] }),
                      (alpha.max()! - alpha.min()!) < 0.035 else {
                    throw NativeError.message("Window transition drift: visible=\(visible), alpha=\(alpha)")
                }
                if visible[0] && alpha[0] > 0.01 && alpha[0] < 0.99 { intermediateFrames += 1 }
                guard core.isVisible, core.alphaValue == 1,
                      independent.map({ $0.isVisible && $0.alphaValue == 1 }) ?? true else {
                    throw NativeError.message("A workspace fade affected the cube or independent window")
                }
                try await Task.sleep(for: .milliseconds(12))
            }
            return intermediateFrames
        }

        for detached in [false, true] {
            if detached { companions.detach(.second) }
            desktop.collapse(animated: false)
            desktop.expand()
            let openingFrames = try await sample(group)
            try check(openingFrames > 0 && group.allSatisfy({ $0.isVisible && $0.alphaValue == 1 }),
                      "All three windows share the complete fade in (detached: \(detached))")
            desktop.collapse()
            try check(group.allSatisfy(\.isVisible) && desktop.hidingWorkspace,
                      "Companions remain mounted until the shared fade out ends")
            companions.layout()
            let closingFrames = try await sample(group)
            try check(closingFrames > 0 && group.allSatisfy({ !$0.isVisible && $0.alphaValue == 1 })
                      && !desktop.hidingWorkspace && first.parent == nil && second.parent == nil,
                      "All three windows finish fading before hiding and releasing child ownership")
        }

        desktop.expand()
        try await Task.sleep(for: .milliseconds(45))
        desktop.collapse()
        try await Task.sleep(for: .milliseconds(40))
        let alphaBeforeReversal = window.alphaValue
        desktop.expand()
        try check(abs(window.alphaValue - alphaBeforeReversal) < 0.035,
                  "Reopening an unfinished fade continues from its current opacity without flashing")
        _ = try await sample(group)
        try check(group.allSatisfy({ $0.isVisible && $0.alphaValue == 1 }) && desktop.expanded,
                  "An obsolete fade completion cannot hide a reopened workspace")

        desktop.collapse()
        try await Task.sleep(for: .milliseconds(40))
        desktop.revealMainContent()
        _ = try await sample(group)
        try check(group.allSatisfy({ $0.isVisible && $0.alphaValue == 1 }) && !desktop.previewing,
                  "Explicit presentation cancels all in-flight alpha animations together")

        companions.setKeepDetachedVisible(true)
        desktop.collapse()
        _ = try await sample([window, first], independent: second)
        desktop.expand()
        _ = try await sample([window, first], independent: second)
        try check(second.isVisible && second.alphaValue == 1 && second.parent == nil,
                  "An explicitly independent detached window stays fully visible through both fades")
        companions.setKeepDetachedVisible(false)
        companions.restoreBase(.second)
        companions.toggleExpansion(.first)
        desktop.collapse()
        _ = try await sample([window, first])
        desktop.expand()
        _ = try await sample([window, first])
        try check(first.isVisible && !second.isVisible,
                  "Shared transitions do not reveal a sibling covered by an expanded companion")
        companions.collapseDockedExpansion()

        reduceMotion = true
        desktop.collapse()
        try check(group.allSatisfy({ !$0.isVisible }) && !desktop.hidingWorkspace,
                  "Reduce Motion folds the complete group synchronously")
        desktop.expand()
        try check(group.allSatisfy({ $0.isVisible && $0.alphaValue == 1 }),
                  "Reduce Motion opens the complete group without a partial frame")
        reduceMotion = false
        desktop.collapse()
        try await Task.sleep(for: .milliseconds(40))
        desktop.restoreWindow()
        try await Task.sleep(for: .milliseconds(250))
        try check(window.isVisible && window.alphaValue == 1 && !first.isVisible && !second.isVisible
                  && window.animationBehavior == .documentWindow && !desktop.enabled,
                  "Returning to normal mode cancels the fade and restores native animation behavior")
        try check(app.selectedExecution?.running == true && app.composer == "Keep the draft while the windows fade"
                  && app.currentHistoryArchive.conversations == archive.conversations && !app.liveVoice.inCall,
                  "Window transitions preserve the running task, draft, history and microphone state")
        app.selectedExecution?.running = false
    }
}
