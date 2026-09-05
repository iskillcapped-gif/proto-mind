import AppKit
import Foundation
import SwiftUI

extension NativeChecks {
    @MainActor
    static func codexUsageContracts(root: URL) throws {
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
        let state = root.appendingPathComponent("usage-layout")
        let app = AppModel(configuration: LaunchConfiguration(projectRoot: root, python: root, stateDirectory: state))
        let view = NSHostingController(rootView: CodexUsageView(app: app, usage: app.codexUsage))
        let size = view.sizeThatFits(in: CGSize(width: 800, height: 720))
        try check(size.width <= 640 && size.height <= 660 && !FileManager.default.fileExists(atPath: state.path),
                  "Usage sheet fits a small window and layout measurement never creates account state")
        var invalid = String(decoding: raw, as: UTF8.self)
        invalid = invalid.replacingOccurrences(of: "proto_mind.codex_usage.v1", with: "unknown")
        do {
            _ = try CodexUsageSnapshot.parse(JSONDecoder().decode(JSONValue.self, from: Data(invalid.utf8)))
            throw NativeError.message("Unknown usage schema accepted")
        } catch { try check(error.localizedDescription != "Unknown usage schema accepted", "Unknown usage report schema is refused") }
    }
}
