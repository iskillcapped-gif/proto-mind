import AppKit
import Combine
import SwiftUI

extension NativeChecks {
    @MainActor
    static func codexLimitsRefresh(root: URL) async throws {
        let raw = JSONValue.object([
            "schema": .string("proto_mind.codex_usage.v1"), "connected": .bool(true),
            "email": .string("limits@example.invalid"), "plan": .string("plus"),
            "buckets": .array([.object(["id": .string("codex"), "name": .string("Codex"), "plan": .string("plus"),
                "windows": .array([.object(["kind": .string("primary"), "used_percent": .number(27),
                    "remaining_percent": .number(73), "window_minutes": .number(300), "resets_at": .number(2000)])])])]),
            "limits_error": .string(""), "activity_error": .string(""), "checked_at": .number(1000),
            "limits_updated_at": .number(1000)
        ])
        let value = try CodexUsageSnapshot.parse(raw)
        try check(value.compactBucket?.windows.first?.usedLabel == "27%", "Quota metadata retains the separately labelled used percentage")
        try check(value.compactBucket?.windows.first?.remainingLabel == "73%", "Menu and full sheet can show the same explicit remaining percentage")
        try check(!value.limitsAreStale(at: Date(timeIntervalSince1970: 1089))
                  && value.limitsAreStale(at: Date(timeIntervalSince1970: 1091)), "Old quota readings are explicitly stale")
        let missing = CodexUsageSnapshot.Window(kind: "primary", usedPercent: nil, remainingPercent: nil, windowMinutes: nil, resetsAt: nil)
        let over = CodexUsageSnapshot.Window(kind: "primary", usedPercent: 120, remainingPercent: 0, windowMinutes: 300, resetsAt: nil)
        try check(missing.usedLabel == "—" && missing.remainingLabel == "—" && over.usedLabel == "100%+" && over.remainingLabel == "0%", "Compact quotas preserve unknown and over-limit readings")
        let app = AppModel(configuration: LaunchConfiguration(projectRoot: root, python: root, stateDirectory: root.appendingPathComponent("limits-refresh")))
        var calls = 0
        var fail = false
        let usage = CodexUsageModel(limitsRequest: { _ in
            calls += 1
            if fail { throw NativeError.message("Fixture unavailable") }
            return raw
        })
        await usage.refreshLimits(app: app)
        try check(calls == 0, "Automatic limits do not read the account without cloud consent")
        app.cloudConsent = true; app.busy = true
        await usage.refreshLimits(app: app, now: Date(timeIntervalSince1970: 1000))
        try check(calls == 1 && app.busy && usage.summary != nil && usage.snapshot == nil,
                  "Quota summary reads during a turn without changing work state or full reset data")
        app.busy = false
        await usage.refreshLimits(app: app, now: Date(timeIntervalSince1970: 1001))
        try check(calls == 1 && !app.busy, "Repeated menu opens are throttled without blocking send")
        fail = true
        await usage.refreshLimits(app: app, now: Date(timeIntervalSince1970: 1040))
        try check(calls == 2 && usage.summaryError != nil && usage.summary?.compactBucket?.windows.first?.used == 27,
                  "Failed refresh preserves the previous reading with an explicit error")

        var continuation: CheckedContinuation<JSONValue, Error>?
        let pending = CodexUsageModel(limitsRequest: { _ in
            try await withCheckedThrowingContinuation { continuation = $0 }
        })
        let task = Task { await pending.refreshLimits(app: app) }
        while continuation == nil { await Task.yield() }
        try check(pending.refreshingLimits && !app.busy && !app.client.turnOutstanding,
                  "An in-flight quota request leaves model work and send available")
        pending.clear()
        continuation?.resume(returning: raw)
        await task.value
        try check(pending.summary == nil && !pending.refreshingLimits, "An old account response cannot repopulate limits after clear")

        continuation = nil
        let cancelledPoll = Task { await pending.refreshLimits(app: app) }
        while continuation == nil { await Task.yield() }
        cancelledPoll.cancel()
        continuation?.resume(returning: raw)
        await cancelledPoll.value
        try check(pending.summary?.compactBucket?.windows.first?.remaining == 73,
                  "Leaving the foreground does not discard a completed quota read for the same account")

        try await fullUsageRefresh(app: app, raw: raw)

        for width: CGFloat in [190, 230, 280] {
            let view = NSHostingController(rootView: SidebarMenuView(app: app, usage: usage, client: app.client, openSettings: {}))
            let size = view.sizeThatFits(in: CGSize(width: width, height: 100))
            try check(size.width <= width + 1 && size.height <= 70, "Sidebar menu fits width \(Int(width)) without pushing content off screen")
        }
    }

    @MainActor
    private static func fullUsageRefresh(app: AppModel, raw: JSONValue) async throws {
        guard case .object(var full) = raw else { throw NativeError.message("Invalid usage fixture") }
        full["activity"] = .object(["summary": .object(["lifetimeTokens": .number(123)]), "daily": .array([])])
        full["activity_updated_at"] = .number(1000)
        full["reset_credits"] = .number(3)
        full["reset"] = .object(["account_ref": .string(String(repeating: "a", count: 64)),
                                "attempt_key": .string(""), "outcome": .string("")])
        var nextSummary = raw
        var continuation: CheckedContinuation<JSONValue, Error>?
        let usage = CodexUsageModel(usageRequest: { _ in
            try await withCheckedThrowingContinuation { continuation = $0 }
        }, limitsRequest: { _ in nextSummary })

        app.setComposer("Не отправлять и не стирать этот черновик")
        let originalMessages = app.messages
        var busyChanges: [Bool] = []
        let observation = app.$busy.dropFirst().sink { busyChanges.append($0) }
        defer { observation.cancel() }
        let first = Task { await usage.refresh(app: app) }
        while continuation == nil { await Task.yield() }
        try check(usage.refreshing && !app.busy && busyChanges.isEmpty && !app.client.turnOutstanding,
                  "Opening usage does not start chat work or lock the composer")
        // A real task may start while the independent account read is pending.
        app.busy = true; busyChanges = []
        continuation?.resume(returning: .object(full))
        await first.value
        try check(app.busy && busyChanges.isEmpty && app.messages == originalMessages
                  && app.composer == "Не отправлять и не стирать этот черновик",
                  "Finishing the usage read preserves a task started meanwhile and its draft")
        try check(usage.displaySnapshot?.canReset == true && usage.displaySnapshot?.activity?.summary.lifetimeTokens == 123,
                  "A full read provides account activity and explicit reset details")

        guard case .object(var latest) = raw, case .array(var buckets) = latest["buckets"],
              case .object(var bucket) = buckets.first, case .array(var windows) = bucket["windows"],
              case .object(var window) = windows.first else { throw NativeError.message("Invalid quota fixture") }
        window["used_percent"] = .number(40); window["remaining_percent"] = .number(60)
        windows[0] = .object(window); bucket["windows"] = .array(windows); buckets[0] = .object(bucket)
        latest["buckets"] = .array(buckets); latest["checked_at"] = .number(2000); latest["limits_updated_at"] = .number(2000)
        latest["reset_credits"] = .number(2)
        nextSummary = .object(latest)
        await usage.refreshLimits(app: app, minimumInterval: 0)
        try check(usage.displaySnapshot?.compactBucket?.windows.first?.remainingLabel == "60%"
                  && usage.displaySnapshot?.activity?.summary.lifetimeTokens == 123
                  && usage.displaySnapshot?.reset != nil && usage.displaySnapshot?.resetCredits == 2,
                  "Fresh sidebar quotas also update the full sheet without erasing activity or reset details")

        continuation = nil
        let failed = Task { await usage.refresh(app: app) }
        while continuation == nil { await Task.yield() }
        try check(app.busy && usage.refreshing, "Full usage can refresh during active model work")
        continuation?.resume(throwing: NativeError.message("Fixture unavailable"))
        await failed.value
        try check(app.busy && busyChanges.isEmpty && usage.summaryError != nil
                  && usage.displaySnapshot?.compactBucket?.windows.first?.remaining == 60,
                  "An account-read failure retains the last quota with an error and never stops model work")

        continuation = nil
        let older = Task { await usage.refresh(app: app) }
        while continuation == nil { await Task.yield() }
        continuation?.resume(returning: .object(full))
        await older.value
        try check(usage.displaySnapshot?.compactBucket?.windows.first?.remaining == 60,
                  "An older full response cannot roll newer sidebar percentages backwards")

        latest["email"] = .string("different@example.invalid"); latest["checked_at"] = .number(3000)
        nextSummary = .object(latest)
        await usage.refreshLimits(app: app, minimumInterval: 0)
        try check(usage.displaySnapshot?.activity == nil && usage.displaySnapshot?.reset == nil,
                  "Another account cannot inherit activity or reset authority from the prior full read")
        continuation = nil
        let cleared = Task { await usage.refresh(app: app) }
        while continuation == nil { await Task.yield() }
        usage.clear()
        continuation?.resume(returning: .object(full))
        await cleared.value
        try check(usage.snapshot == nil && usage.summary == nil && usage.error == nil && app.busy,
                  "Account invalidation also rejects a pending full response without changing the task")
        app.busy = false
    }
}
