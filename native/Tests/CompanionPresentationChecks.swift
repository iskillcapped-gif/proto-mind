import AppKit
import SwiftUI

@MainActor private final class CompanionPageProbe {
    var destination: WorkspacePresentations?
    var glass = false
    var inline = false
}

private struct CompanionProbePage: View {
    let probe: CompanionPageProbe
    @Environment(\.workspacePresentations) private var destination
    @Environment(\.desktopGlass) private var glass
    @Environment(\.workspaceInline) private var inline
    var body: some View {
        Text("Panel-local preview").onAppear {
            probe.destination = destination; probe.glass = glass; probe.inline = inline
        }
    }
}

@MainActor private final class CompanionPickerProbe: NSSavePanel {
    var receivedWindow: NSWindow?
    override func beginSheetModal(for window: NSWindow, completionHandler handler: @escaping (NSApplication.ModalResponse) -> Void) {
        receivedWindow = window; handler(.cancel)
    }
}

extension NativeChecks {
    @MainActor
    static func companionPresentations(root: URL) async throws {
        let suite = "proto-companion-presentations." + UUID().uuidString
        let defaults = UserDefaults(suiteName: suite)!
        defer { defaults.removePersistentDomain(forName: suite) }
        let state = root.appendingPathComponent("companion-presentations")
        let app = AppModel(configuration: LaunchConfiguration(projectRoot: root, python: root, stateDirectory: state), uiDefaults: defaults)
        let desktop = DesktopPresentation(stateDirectory: state, defaults: defaults, presentsWindows: true, pointerLocation: nil)
        let window = NSWindow(contentRect: NSRect(x: 100, y: 100, width: 1080, height: 720),
                              styleMask: [.titled, .resizable, .closable], backing: .buffered, defer: false)
        window.isReleasedWhenClosed = false
        defer { desktop.shutdown(); app.shutdown(); window.close() }
        desktop.attach(window: window, app: app); desktop.enable(animated: false)
        let owner = desktop.companions
        owner.toggle(.first); owner.toggle(.second)
        let bounds = NSScreen.main!.visibleFrame
        app.setComposer("Preserve the main draft"); app.flushDraft()
        app.selectedExecution?.running = true
        let archive = app.currentHistoryArchive
        func settle() async throws { try await Task.sleep(for: .milliseconds(140)) }
        func closeFrames(_ a: NSRect, _ b: NSRect) -> Bool {
            abs(a.minX - b.minX) < 1.5 && abs(a.minY - b.minY) < 1.5
                && abs(a.width - b.width) < 1.5 && abs(a.height - b.height) < 1.5
        }

        for id in DesktopCompanionID.allCases {
            let item = owner.surface(id), panelWindow = item.window!
            owner.restoreBase(id); owner.detach(id)
            let compact = NSRect(x: bounds.minX + 50, y: bounds.minY + 70, width: 320, height: 330)
            panelWindow.setFrame(compact, display: false)
            owner.toggleExpansion(id)
            let adjusted = DesktopGeometry.fit(NSRect(x: bounds.minX + 20, y: bounds.minY + 40, width: 570, height: 490), within: bounds)
            panelWindow.setFrame(adjusted, display: false)
            let savedLarge = panelWindow.frame
            owner.toggleExpansion(id)
            let beforeMove = panelWindow.frame
            panelWindow.setFrameOrigin(NSPoint(x: beforeMove.minX + 190, y: beforeMove.minY + 100))
            let afterMove = panelWindow.frame
            owner.toggleExpansion(id)
            let expected = DesktopGeometry.fit(savedLarge.offsetBy(dx: afterMove.midX - beforeMove.midX, dy: afterMove.midY - beforeMove.midY), within: bounds)
            try check(!item.docked && panelWindow.parent == nil && closeFrames(panelWindow.frame, expected),
                      "Detached \(id.rawValue) expands at its moved location instead of an obsolete sidebar position")
            owner.toggleExpansion(id)
            try check(closeFrames(panelWindow.frame, afterMove), "The size button restores the exact moved miniature for \(id.rawValue)")
            owner.toggleExpansion(id)
            try check(closeFrames(panelWindow.frame, expected), "Repeated toggles preserve the independently adjusted expanded size for \(id.rawValue)")
            owner.restoreBase(id); owner.detach(id)
            let base = panelWindow.frame
            let rebased = DesktopCompanionGeometry.enlarged(base, screen: bounds, preferredSize: expected.size)
            owner.toggleExpansion(id)
            try check(!item.docked && closeFrames(panelWindow.frame, rebased),
                      "Reattaching and detaching \(id.rawValue) discards the previous expansion location while retaining its size")
            owner.restoreBase(id)
        }

        for id in DesktopCompanionID.allCases {
            let item = owner.surface(id), panelWindow = item.window!
            owner.toggleExpansion(id)
            let frame = panelWindow.frame
            let selectedTab = item.panel.open(.conversation(app.selectedID!))
            let other = owner.surface(id == .first ? .second : .first)
            let center = item.presentations
            let pageID = UUID(), childID = UUID()
            let probe = CompanionPageProbe()
            var closed = 0, childClosed = 0
            // A captured destination remains authoritative after another window gains focus.
            app.presentations.prepare("delayed-preview", in: center)
            window.makeKeyAndOrderFront(nil)
            try await settle()
            app.presentations.present(id: pageID, content: AnyView(CompanionProbePage(probe: probe)),
                clearBinding: { closed += 1 }, routingKey: "delayed-preview")
            try await settle()
            try check(center.pages.count == 1 && app.presentations.pages.isEmpty && other.presentations.pages.isEmpty
                      && item.expanded && closeFrames(panelWindow.frame, frame),
                      "A captured page opens in expanded \(id.rawValue) without shrinking it or opening the main chat")
            try check(probe.destination === center && probe.glass && probe.inline,
                      "Companion content receives its own nested presentation route and glass appearance")
            app.presentations.update(id: pageID, content: AnyView(Text("Updated at the original destination")))
            center.present(id: childID, content: AnyView(Text("Nested confirmation")), clearBinding: { childClosed += 1 })
            center.setDismissalDisabled(true, id: childID)
            try check(center.pages.count == 2 && app.presentations.locked && !app.presentations.dismissAll(),
                      "A nested companion operation retains its dismissal guard across the whole workspace")
            center.setDismissalDisabled(false, id: childID); center.dismissTop()
            try check(center.pages.count == 1 && childClosed == 1 && closed == 0,
                      "Back closes only the companion's child page")
            app.presentations.remove(id: pageID)
            try check(center.pages.isEmpty && closed == 1 && item.panel.selectedID == selectedTab && item.expanded,
                      "Model-driven dismissal returns to the retained companion tab and expanded geometry")

            let picker = CompanionPickerProbe()
            var cancelled = false
            window.makeKeyAndOrderFront(nil)
            app.presentFilePicker(picker, in: center) { cancelled = $0 == .cancel }
            try check(picker.receivedWindow === panelWindow && cancelled && item.expanded && closeFrames(panelWindow.frame, frame),
                      "An OS file picker attaches to the captured \(id.rawValue) window without collapsing it")
            let popup = NSPanel(contentRect: NSRect(x: frame.minX + 20, y: frame.minY + 20, width: 100, height: 100),
                                styleMask: [.titled], backing: .buffered, defer: false)
            popup.isReleasedWhenClosed = false
            panelWindow.addChildWindow(popup, ordered: .above)
            try check(owner.presentationSource(for: popup) === center,
                      "Actions originating in a companion's popup resolve to that same companion")
            panelWindow.removeChildWindow(popup); popup.close()
            owner.toggleExpansion(id)
        }
        try check(app.currentHistoryArchive.conversations == archive.conversations && app.composer == "Preserve the main draft"
                  && app.selectedExecution?.running == true && !app.liveVoice.inCall,
                  "Window-owned dialogs preserve the running task, history, draft and voice state")
        app.selectedExecution?.running = false
    }
}
