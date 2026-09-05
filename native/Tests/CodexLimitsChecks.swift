import AppKit
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
        try check(value.compactBucket?.windows.first?.usedLabel == "27%", "Compact quota shows used, not remaining, percentage")
        try check(!value.limitsAreStale(at: Date(timeIntervalSince1970: 1089))
                  && value.limitsAreStale(at: Date(timeIntervalSince1970: 1091)), "Old quota readings are explicitly stale")
        let missing = CodexUsageSnapshot.Window(kind: "primary", usedPercent: nil, remainingPercent: nil, windowMinutes: nil, resetsAt: nil)
        let over = CodexUsageSnapshot.Window(kind: "primary", usedPercent: 120, remainingPercent: 0, windowMinutes: 300, resetsAt: nil)
        try check(missing.usedLabel == "—" && over.usedLabel == "100%+", "Compact quotas preserve unknown and over-limit readings")
        let app = AppModel(configuration: LaunchConfiguration(projectRoot: root, python: root, stateDirectory: root.appendingPathComponent("limits-refresh")))
        var calls = 0
        var fail = false
        let usage = CodexUsageModel { _ in
            calls += 1
            if fail { throw NativeError.message("Fixture unavailable") }
            return raw
        }
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
        let pending = CodexUsageModel { _ in
            try await withCheckedThrowingContinuation { continuation = $0 }
        }
        let task = Task { await pending.refreshLimits(app: app) }
        while continuation == nil { await Task.yield() }
        try check(pending.refreshingLimits && !app.busy && !app.client.turnOutstanding,
                  "An in-flight quota request leaves model work and send available")
        pending.clear()
        continuation?.resume(returning: raw)
        await task.value
        try check(pending.summary == nil && !pending.refreshingLimits, "An old account response cannot repopulate limits after clear")

        for width: CGFloat in [190, 230, 280] {
            let view = NSHostingController(rootView: SidebarMenuView(app: app, usage: usage, client: app.client, openSettings: {}))
            let size = view.sizeThatFits(in: CGSize(width: width, height: 100))
            try check(size.width <= width + 1 && size.height <= 70, "Sidebar menu fits width \(Int(width)) without pushing content off screen")
        }
    }
}
