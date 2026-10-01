import AppKit
import Combine
import SwiftUI

@MainActor private final class PresentationProbe: ObservableObject {
    struct Item: Identifiable { let id = UUID(); let text: String }
    @Published var shown = false
    @Published var item: Item?
    @Published var label = "Initial"
    @Published var locked = false
    var rendered = ""
    var renderedLocal = ""
    var changeLocal: (String) -> Void = { _ in }
    var parentDismissals = 0
    var childDismissals = 0
}

private struct PresentationProbeView: View {
    @ObservedObject var app: AppModel
    @ObservedObject var probe: PresentationProbe
    @State private var localText = "Local initial"
    var body: some View {
        WorkspaceContentHost(app: app, presentations: app.presentations)
            .workspaceSheet(isPresented: $probe.shown, routingKey: "probe", onDismiss: { probe.parentDismissals += 1 }) {
                VStack {
                    Text(probe.label).onChange(of: probe.label, initial: true) { _, value in probe.rendered = value }
                    Text(localText).onChange(of: localText, initial: true) { _, value in probe.renderedLocal = value }
                }
                    .workspaceDismissDisabled(probe.locked)
                    .workspaceSheet(item: $probe.item, onDismiss: { probe.childDismissals += 1 }) { item in
                        Text(item.text)
                    }
            }
            .workspaceSheet(isPresented: $app.showSettings, routingKey: "settings") { Text("Settings") }
            .onAppear { probe.changeLocal = { localText = $0 } }
            .environment(\.workspacePresentations, app.presentations)
    }
}

extension NativeChecks {
    @MainActor
    static func workspacePresentations(root: URL) async throws {
        _ = NSApplication.shared
        let app = AppModel(configuration: LaunchConfiguration(projectRoot: root, python: root,
                            stateDirectory: root.appendingPathComponent("workspace-presentations")))
        let center = app.presentations
        let probe = PresentationProbe()
        let host = NSHostingController(rootView: PresentationProbeView(app: app, probe: probe))
        let window = NSWindow(contentRect: NSRect(x: 100, y: 100, width: 580, height: 620),
                              styleMask: [.titled, .closable, .resizable], backing: .buffered, defer: false)
        window.isReleasedWhenClosed = false; window.contentViewController = host; center.window = window
        defer { app.shutdown(); window.close() }
        host.view.layoutSubtreeIfNeeded()
        var revealCount = 0, publications = 0
        center.reveal = { revealCount += 1 }
        let observation = center.$pages.sink { _ in publications += 1 }
        defer { observation.cancel() }
        let selected = app.selectedID
        let original = app.currentHistoryArchive
        let execution = app.selectedExecution!
        execution.running = true
        func settle() async throws {
            host.view.layoutSubtreeIfNeeded()
            try await Task.sleep(for: .milliseconds(120))
            host.view.layoutSubtreeIfNeeded()
        }
        try await settle()
        probe.shown = true
        try await settle()
        try check(center.pages.count == 1 && revealCount == 1 && window.sheets.isEmpty,
                  "Auxiliary page opens inside the existing workspace without a native sheet")
        let parentID = center.pages.first?.id
        probe.label = "Updated"
        try await settle()
        try check(center.pages.first?.id == parentID && probe.rendered == "Updated" && revealCount == 1,
                  "Open page receives changing source values without a new presentation or focus reset")
        probe.changeLocal("Local changed")
        try await settle()
        try check(probe.renderedLocal == "Local changed", "Inline forms re-evaluate values and validation owned by the source's local State")
        probe.item = .init(text: "First child")
        try await settle()
        try check(center.pages.count == 2, "Nested preview occupies the same chat area above its retained parent")
        let firstChild = center.pages.last?.id
        let replacement = PresentationProbe.Item(text: "Replacement")
        probe.item = replacement
        try await settle()
        try check(center.pages.count == 2 && center.pages.last?.id != firstChild && probe.item?.id == replacement.id
                  && probe.childDismissals == 1, "Replacing an item closes its old page without clearing the new binding")
        let settledPublications = publications
        try await settle()
        try await settle()
        try check(publications == settledPublications,
                  "An idle nested presentation does not continuously publish or re-render its source")
        center.dismissTop()
        try await settle()
        try check(center.pages.count == 1 && probe.shown && probe.item == nil && probe.childDismissals == 2,
                  "Back clears only the top preview and restores its parent")
        probe.locked = true
        try await settle()
        center.dismissTop()
        app.newConversation()
        try check(center.locked && center.pages.count == 1 && probe.shown && app.selectedID == selected,
                  "An operation's dismissal guard applies to the inline Back and Escape route")
        probe.locked = false
        try await settle()
        center.dismissTop()
        try await settle()
        try check(center.pages.isEmpty && !probe.shown && probe.parentDismissals == 1,
                  "Closing an inline page clears its source and invokes onDismiss exactly once")
        probe.shown = true
        try await settle()
        center.dismissAll(); probe.shown = true
        try await settle()
        try check(center.pages.count == 1 && probe.shown,
                  "Dismissing and reopening a binding in one UI turn still mounts the new page")
        center.dismissAll()
        try await settle()
        probe.shown = true
        try await settle()
        probe.item = .init(text: "Child")
        try await settle()
        probe.shown = false
        try await settle()
        try check(center.pages.isEmpty && probe.item == nil && probe.parentDismissals == 4 && probe.childDismissals == 3,
                  "Model-driven parent removal also clears nested previews exactly once")
        try check(app.currentHistoryArchive.conversations == original.conversations
                  && app.selectedID == selected && execution.running && !app.liveVoice.inCall && !app.cloudConsent,
                  "Inline navigation preserves task, selection, history and voice consent")
        let remote = WorkspacePresentations()
        let remoteHost = NSHostingController(rootView: WorkspacePresentationHost(presentations: remote, backTitle: "Back") { Color.clear })
        let remoteWindow = NSWindow(contentRect: NSRect(x: 150, y: 150, width: 580, height: 620),
                                    styleMask: [.titled], backing: .buffered, defer: false)
        remoteWindow.isReleasedWhenClosed = false
        remoteWindow.contentViewController = remoteHost; remote.window = remoteWindow
        defer { remoteWindow.close() }
        center.register(remote)
        center.prepare("probe", in: remote); probe.shown = true
        try await settle()
        probe.label = "Updated in companion"
        try await settle()
        try check(center.pages.isEmpty && remote.pages.count == 1 && probe.rendered == "Updated in companion",
                  "A forwarded source binding stays live inside its captured companion")
        let dismissalsBeforeMove = probe.parentDismissals
        center.prepare("probe", in: center); probe.shown = true
        try await settle()
        try check(center.pages.count == 1 && remote.pages.isEmpty && probe.shown,
                  "Reopening the same bound screen from another window moves only that presentation")
        try check(probe.parentDismissals == dismissalsBeforeMove && probe.rendered == "Updated in companion",
                  "A moved page keeps its binding and is not dismissed on the way")
        center.dismissAll()
        try await settle()
        app.openSettings(in: remote)
        try await settle()
        try check(remote.pages.count == 1 && center.pages.isEmpty && app.showSettings,
                  "Opening settings captures the companion instead of falling back to the main chat")
        let settingsID = remote.pages[0].id
        remote.setDismissalDisabled(true, id: settingsID)
        app.openSettings(in: center)
        try await settle()
        try check(remote.pages.count == 1 && center.pages.isEmpty && app.showSettings,
                  "Settings cannot move away from a window while its nested operation blocks dismissal")
        remote.setDismissalDisabled(false, id: settingsID)
        app.openSettings(in: center)
        try await settle()
        try check(center.pages.count == 1 && remote.pages.isEmpty && app.showSettings,
                  "Settings already open elsewhere move to the requesting window after the operation finishes")
        center.dismissAll()
        try await settle()
        execution.running = false
        app.discardUnsavedOnExit = true; app.busy = true
        try check(!app.canTerminateWorkspace() && app.exitPrompt == .busy && !app.discardUnsavedOnExit,
                  "A prior discard choice cannot interrupt a later shared persistence operation")
        app.busy = false; app.exitPrompt = nil

        for width: CGFloat in [530, 752, 1000] {
            for section in NativeSettingsSection.allCases {
                app.settingsSection = section
                let settings = NSHostingController(rootView: NativeSettingsView(model: app)
                    .environment(\.workspaceInline, true).environment(\.desktopGlass, true))
                let size = settings.sizeThatFits(in: CGSize(width: width, height: 560))
                try check(size.width <= width + 1 && size.height <= 561,
                          "Inline settings \(section.rawValue) fits a \(Int(width))-point glass chat")
            }
            for page in [AnyView(ConversationHistoryView(model: app)), AnyView(WorkSessionsView(model: app)),
                         AnyView(CodexUsageView(app: app, usage: app.codexUsage)), AnyView(TaskCriteriaView(model: app))] {
                let content = NSHostingController(rootView: page.environment(\.workspaceInline, true))
                let size = content.sizeThatFits(in: CGSize(width: width, height: 560))
                try check(size.width <= width + 1 && size.height <= 561, "Inline auxiliary content fits the chat viewport")
            }
        }
        probe.shown = true
        try await settle()
        app.returnToConversation(selected!)
        try await settle()
        try check(center.pages.isEmpty && !probe.shown && app.selectedID == selected,
                  "Choosing a dialog replaces auxiliary screens with that chat, including the already-selected dialog")
        try sidebarQuotaPresentation()
    }

    static func sidebarQuotaPresentation() throws {
        func snapshot(_ buckets: [CodexUsageSnapshot.Bucket], connected: Bool = true) -> CodexUsageSnapshot {
            .init(schema: "proto_mind.codex_usage.v1", connected: connected, plan: "fixture", email: "fixture@example.invalid",
                  buckets: buckets, resetCredits: nil, reset: nil, resetError: nil, activity: nil, limitsError: "",
                  activityError: "", checkedAt: 0, limitsUpdatedAt: 0, activityUpdatedAt: nil)
        }
        let weekly = CodexUsageSnapshot.Window(kind: "secondary", usedPercent: 32, remainingPercent: 68, windowMinutes: 10080, resetsAt: nil)
        let five = CodexUsageSnapshot.Window(kind: "primary", usedPercent: 91, remainingPercent: 9, windowMinutes: 300, resetsAt: nil)
        let reserve = CodexUsageSnapshot.Bucket(id: "gpt-reserve", name: "Reserve", plan: "fixture", windows: [weekly, five])
        let main = CodexUsageSnapshot.Bucket(id: "codex", name: "Codex", plan: "fixture", windows: [five, weekly])
        try check(SidebarQuotaSummary.windows(snapshot([reserve, main])).map(\.windowMinutes) == [10080, 300],
                  "Sidebar shows core weekly then five-hour quotas, never duplicate reserve buckets")
        let weeklyOnly = CodexUsageSnapshot.Bucket(id: "codex", name: "Codex", plan: "fixture", windows: [weekly])
        try check(SidebarQuotaSummary.windows(snapshot([weeklyOnly, reserve])).map(\.windowMinutes) == [10080],
                  "An account without a five-hour core quota does not receive a fabricated or reserve substitute")
        try check(SidebarQuotaSummary.windows(snapshot([reserve])).isEmpty
                  && SidebarQuotaSummary.windows(snapshot([main], connected: false)).isEmpty
                  && SidebarQuotaSummary.windows(nil).isEmpty,
                  "Unavailable core quotas remain unavailable instead of borrowing another limit")
        for width: CGFloat in [196, 236, 316] {
            let anchor = CGRect(x: 100, y: 100, width: width - 40, height: 44)
            let frame = ComposerPopoverPlacement.frame(anchor: anchor, screen: CGRect(x: 0, y: 0, width: 1440, height: 900),
                            size: CGSize(width: 340, height: 410), trailing: false, confinedToColumn: true, columnWidth: width)
            try check(frame.minX == anchor.minX && frame.width == width && frame.minY >= anchor.maxY,
                      "Sidebar menu uses the whole column width and expands upward")
        }
    }
}
