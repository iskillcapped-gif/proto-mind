import AppKit
import Foundation
import SwiftUI

extension NativeChecks {
    @MainActor static func claudeAccountControls(fixture: URL, python: URL, root: URL) async throws {
        let raw = """
        {"schema":"proto_mind.claude_account.v1","installed":true,"connected":true,"email":"fixture@example.invalid","plan":"pro","account_ref":"fixture-account",
        "models":[
          {"id":"","alias":"","resolved_id":"claude-opus-5-5","title":"Opus 5.5","description":"Default","efforts":["low","high"]},
          {"id":"claude-opus-5-5","alias":"opus","resolved_id":"claude-opus-5-5","title":"Opus 5.5","description":"Opus 5.5","efforts":["low","high"]},
          {"id":"claude-haiku-4-5-20251001","alias":"haiku","resolved_id":"claude-haiku-4-5-20251001","title":"Haiku 4.5","description":"Fast","efforts":[]}],
        "windows":[{"id":"seven_day","title":"","window_minutes":10080,"used_percent":0,"remaining_percent":100,"resets_at":2000000000},
          {"id":"five_hour","title":"","window_minutes":300,"used_percent":3,"remaining_percent":97,"resets_at":2000000000}],
        "models_error":"","limits_error":"","limits_available":true,"checked_at":1900000000,"models_updated_at":1900000000,"limits_updated_at":1900000000}
        """
        func decode(_ text: String) throws -> JSONValue { try JSONDecoder().decode(JSONValue.self, from: Data(text.utf8)) }
        var next = try decode(raw)
        var requests = 0
        var pending: CheckedContinuation<Void, Never>?
        var delay = false
        let metadata = ClaudeAccountModel { app in
            requests += 1
            if delay { await withCheckedContinuation { pending = $0 } }
            return next
        }
        let suite = "pm-claude-account-" + UUID().uuidString
        let defaults = UserDefaults(suiteName: suite)!
        let app = AppModel(configuration: LaunchConfiguration(projectRoot: fixture, python: python, stateDirectory: root.appendingPathComponent("claude-account")), uiDefaults: defaults, claudeAccount: metadata)
        defer { app.shutdown(); defaults.removePersistentDomain(forName: suite) }
        let id = app.selectedID!
        app.setProvider("claude"); app.setComposer("My unsent draft"); app.cloudConsent = true
        let originalMessages = app.messages.count
        await metadata.refresh(app: app, now: Date(timeIntervalSince1970: 1900000000))
        try check(metadata.snapshot?.compactWindows.count == 2 && metadata.snapshot?.compactWindows.last?.remainingPercent == 97,
                  "Claude quota displays 3 percent used as 97 percent remaining, separately from Codex")
        try check(metadata.label(for: "opus") == "Opus 5.5" && metadata.label(for: "") == "Opus 5.5",
                  "Legacy Claude aliases and account default resolve to the observed model version")
        app.setModel("claude-opus-5-5"); app.setReasoningEffort("high")
        try check(app.selected?.model == "claude-opus-5-5" && ConversationComposerContext(app: app, id: id).localLabel == "Opus 5.5",
                  "Claude composer stores exact version and displays readable model name")
        app.setModel("claude-haiku-4-5-20251001")
        try check(app.selected?.reasoningEffort == "", "Selecting a model without effort support clears the previous effort")
        app.setReasoningEffort("high")
        try check(app.selected?.reasoningEffort == "", "Unavailable Claude effort cannot be selected")
        app.newPanelConversation(in: app.workspacePanels.upper)
        guard case .conversation(let side) = app.workspacePanels.upper.selected?.content else { throw NativeError.message("Missing side chat") }
        app.configureConversation(side, provider: "claude", model: "claude-opus-5-5", effort: "high")
        try check(app.conversations.first { $0.id == side }?.model == "claude-opus-5-5", "Side chat retains its own exact Claude model")
        try check(app.selectedID == id && app.composer == "My unsent draft" && app.messages.count == originalMessages && !app.busy,
                  "Claude metadata refresh does not change navigation, task state, messages or composer")
        await metadata.refresh(app: app, now: Date(timeIntervalSince1970: 1900000010))
        try check(requests == 1, "Repeated menu openings reuse recent metadata without extra CLI calls")
        next = try decode(raw.replacingOccurrences(of: "\"windows\":[", with: "\"discarded_windows\":[").replacingOccurrences(of: "\"limits_error\":\"\"", with: "\"windows\":[],\"limits_error\":\"unavailable\""))
        await metadata.refresh(app: app, minimumInterval: 0)
        try check(metadata.snapshot?.windows.count == 2 && metadata.snapshot?.limitsAreStale(at: Date(timeIntervalSince1970:1900000010)) == true,
                  "Failed Claude quota refresh keeps the prior reading visibly stale")
        next = try decode(raw.replacingOccurrences(of: "fixture-account", with: "different-account").replacingOccurrences(of: "\"windows\":[", with: "\"discarded_windows\":[").replacingOccurrences(of: "\"limits_error\":\"\"", with: "\"windows\":[],\"limits_error\":\"unavailable\""))
        await metadata.refresh(app: app, minimumInterval: 0)
        try check(metadata.snapshot?.windows.isEmpty == true, "Claude quotas never carry into a different account")
        delay = true
        let refresh = Task { await metadata.refresh(app: app, minimumInterval: 0) }
        while pending == nil { await Task.yield() }
        metadata.clear(); pending?.resume(); await refresh.value
        try check(metadata.snapshot == nil, "Late metadata cannot repopulate a cleared Claude account")
        delay = false; next = try decode(raw)
        await metadata.refresh(app: app, minimumInterval: 0)
        app.openAccountUsage("claude")
        try check(app.presentedUsageProvider == "claude" && app.showCodexUsage, "Shared limits page opens on the requested provider")
        app.openCodexUsage()
        try check(app.presentedUsageProvider == "codex", "Explicit Codex account actions preserve their provider destination")
        // Render real SwiftUI content for a visual check without live accounts.
        if let output = LaunchConfiguration.argument("--claude-ui-output") {
            let directory = URL(fileURLWithPath: output); try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
            app.setModel("claude-opus-5-5")
            let models = NSHostingView(rootView: ClaudeModelChoices(app: app, account: metadata, conversationID: id, close: {}).padding(12).frame(width: 326).background(Color(nsColor: .windowBackgroundColor)).environment(\.colorScheme, .dark))
            models.frame = NSRect(x: 0, y: 0, width: 326, height: 560)
            let limits = NSHostingView(rootView: ClaudeUsageView(app: app, account: metadata).padding(24).frame(width: 560, height: 500).background(Color(nsColor: .windowBackgroundColor)).environment(\.colorScheme, .dark))
            limits.frame = NSRect(x:0,y:0,width:560,height:500)
            for (name, view) in [("models", models as NSView), ("limits", limits as NSView)] {
                view.layoutSubtreeIfNeeded()
                if let bitmap = view.bitmapImageRepForCachingDisplay(in: view.bounds) {
                    view.cacheDisplay(in: view.bounds, to: bitmap)
                    try bitmap.representation(using: .png, properties: [:])?.write(to: directory.appendingPathComponent(name + ".png"))
                }
            }
        }
    }
}
