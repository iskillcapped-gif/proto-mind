import AppKit
import Foundation
import SwiftUI

extension NativeChecks {
    @MainActor
    static func codexUsageContracts(root: URL) async throws {
        let raw = Data("""
        {"schema":"proto_mind.codex_usage.v1","connected":true,"email":"fixture@example.invalid","plan":"plus",
         "buckets":[{"id":"codex","name":"Codex","plan":"plus","windows":[
          {"kind":"primary","used_percent":25.5,"remaining_percent":74.5,"window_minutes":300,"resets_at":1789000000},
          {"kind":"secondary","used_percent":null,"remaining_percent":null,"window_minutes":10080,"resets_at":null}]}],
         "reset_credits":0,"activity":{"summary":{"lifetimeTokens":0,"peakDailyTokens":null,"currentStreakDays":3},"daily":[]},
         "limits_error":"","activity_error":"","checked_at":1788658000,"limits_updated_at":1788658000,"activity_updated_at":1788658000}
        """.utf8)
        let json = try JSONDecoder().decode(JSONValue.self, from: raw)
        let value = try CodexUsageSnapshot.parse(json)
        try check(value.buckets[0].windows[0].remaining == 74.5 && value.buckets[0].windows[0].title == "5 ч",
                  "Usage displays the returned quota duration and fractional remaining percentage")
        try check(value.buckets[0].windows[1].remaining == nil && value.buckets[0].windows[1].resetsAt == nil
                  && value.buckets[0].windows[1].title == "Неделя", "Missing quota percentage and reset remain unknown in Native")
        try check(value.activity?.summary.lifetimeTokens == 0 && value.activity?.summary.peakDailyTokens == nil,
                  "Native distinguishes zero account activity from missing metrics")
        try check(value.resetCredits == 0, "Zero earned resets is explicit and does not invoke a reset action")
        try check(!value.canReset, "Missing reset identity never enables redemption")
        let reference = String(repeating: "a", count: 64)
        guard case .object(var actionable) = json else { throw NativeError.message("Invalid usage fixture") }
        actionable["reset_credits"] = .number(3)
        actionable["reset"] = .object(["account_ref": .string(reference), "attempt_key": .string(""),
                                        "outcome": .string(""), "credit_id": .string("fixture-credit")])
        let ready = try CodexUsageSnapshot.parse(.object(actionable))
        try check(ready.canReset, "Available resets with verified account enable the explicit action")
        let attempt = CodexResetAttempt(ready.reset!)
        try check(UUID(uuidString: attempt.key) != nil && attempt.parameters["credit_id"] == .string("fixture-credit")
                  && attempt.parameters["account_ref"] == .string(reference), "Confirmation freezes the account, exact credit and one attempt key")
        actionable["reset_credits"] = .number(0)
        try check(try !CodexUsageSnapshot.parse(.object(actionable)).canReset, "No credits hides a new reset action")
        actionable["reset"] = .object(["account_ref": .string(reference), "attempt_key": .string(attempt.key),
                                        "outcome": .string("pending"), "credit_id": .string("fixture-credit")])
        let pending = try CodexUsageSnapshot.parse(.object(actionable))
        try check(pending.canReset && CodexResetAttempt(pending.reset!).key == attempt.key,
                  "An uncertain attempt remains recoverable at zero credits and reuses its original key")
        try check(CodexUsageModel.message(for: "reset") != CodexUsageModel.message(for: "pending")
                  && CodexUsageModel.message(for: "nothingToReset").contains("не потрачен"),
                  "Known success, uncertainty and an unused reset have distinct user messages")
        let state = root.appendingPathComponent("usage-layout")
        let app = AppModel(configuration: LaunchConfiguration(projectRoot: root, python: root, stateDirectory: state))
        let view = NSHostingController(rootView: CodexUsageView(app: app, usage: app.codexUsage))
        let size = view.sizeThatFits(in: CGSize(width: 800, height: 720))
        try check(size.width <= 640 && size.height <= 660 && !FileManager.default.fileExists(atPath: state.path),
                  "Usage sheet fits a small window and layout measurement never creates account state")
        let combined = NSHostingController(rootView: AccountUsageView(app: app, usage: app.codexUsage))
        let combinedSize = combined.sizeThatFits(in: CGSize(width: 800, height: 720))
        try check(combinedSize.width <= 640 && combinedSize.height <= 660 && !FileManager.default.fileExists(atPath: state.path),
                  "Combined subscription page fits the same window without creating account state")
        var invalid = String(decoding: raw, as: UTF8.self)
        invalid = invalid.replacingOccurrences(of: "proto_mind.codex_usage.v1", with: "unknown")
        do {
            _ = try CodexUsageSnapshot.parse(JSONDecoder().decode(JSONValue.self, from: Data(invalid.utf8)))
            throw NativeError.message("Unknown usage schema accepted")
        } catch { try check(error.localizedDescription != "Unknown usage schema accepted", "Unknown usage report schema is refused") }
        try await codexLimitsRefresh(root: root)
    }

    @MainActor
    static func projectlessAccess(fixture: URL, python: URL, root: URL) async throws {
        let state = root.appendingPathComponent("projectless-access")
        let app = AppModel(configuration: LaunchConfiguration(projectRoot: fixture, python: python, stateDirectory: state))
        defer { app.shutdown() }
        await app.start()
        app.setProvider("codex")
        app.cloudConsent = true
        app.requestAgentAccess()
        try check(app.selected?.workspacePath == nil && app.pendingAgentAccess != nil
                  && app.pendingAgentAccess?.workspace == nil && !app.fullAccessEnabled,
                  "An unbound conversation can ask for Full Mac without a folder picker")
        await app.confirmAgentAccess()
        try check(app.fullAccessEnabled && app.selected?.workspacePath == nil && app.error == nil,
                  "Explicit projectless grant keeps the conversation unbound")
        try check(app.contextRequestParameters?["workspace_root"] == nil
                  && app.contextRequestParameters?["access_mode"] == .string("full_access")
                  && app.contextRequestParameters?["access_token"] != nil,
                  "Projectless context uses a real grant without substituting the application project")
        let restart = AppModel(configuration: LaunchConfiguration(projectRoot: fixture, python: python, stateDirectory: state))
        defer { restart.shutdown() }
        try check(restart.fullAccessEnabled && restart.agentGrants.isEmpty && restart.selected?.workspacePath == nil,
                  "Projectless Full Mac selection survives restart without persisting a bridge token")
        try await restart.ensureAgentAccess(for: restart.execution(for: restart.selectedID!))
        try check(restart.agentGrants[restart.selectedID!]?.token != app.agentGrants[app.selectedID!]?.token
                  && restart.agentGrants[restart.selectedID!] != nil,
                  "Restart reissues a distinct grant on the new conversation bridge")
        restart.closeIdleExecutionConnections()
        try check(restart.fullAccessEnabled && restart.agentGrants.isEmpty, "Idle reconnection preserves selection, not a stale token")
        try await restart.ensureAgentAccess(for: restart.execution(for: restart.selectedID!))
        try check(restart.agentGrants[restart.selectedID!] != nil, "Remembered access reconnects after closing idle bridges")
        await app.bindWorkspace(fixture.path)
        try check(app.selected?.workspacePath != nil && !app.fullAccessEnabled,
                  "Choosing a project revokes the earlier projectless grant")
    }
}
