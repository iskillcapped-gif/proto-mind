import SwiftUI

extension NativeChecks {
    /// Links read as links, and the menu row's five-hour timer counts down in hours and minutes.
    @MainActor static func chatPolish() throws {
        let line = MarkdownBlock.inline("See [the guide](https://example.com/guide) first.")
        let link = line.runs.first { $0.link != nil }
        let plain = line.runs.first { $0.link == nil }
        try check(link?.foregroundColor == NativeTheme.link && link?.underlineStyle != nil && plain?.foregroundColor == nil,
                  "Links in replies are underlined in the link color; the rest keeps the reply color")

        let now = Date(timeIntervalSince1970: 1_000_000)
        try check(QuotaResetTime.compact(until: now.timeIntervalSince1970 + 2 * 3600 + 4 * 60 + 1, now: now) == "2:05"
                  && QuotaResetTime.compact(until: now.timeIntervalSince1970 + 30, now: now) == "0:01"
                  && QuotaResetTime.compact(until: now.timeIntervalSince1970, now: now) == nil
                  && QuotaResetTime.compact(until: .infinity, now: now) == nil,
                  "The five-hour timer shows hours and minutes left, rounded up, and disappears at the reset")
        let saved = L10n.language
        defer { L10n.language = saved }
        L10n.language = .russian
        let russian = QuotaResetTime.spoken(until: now.timeIntervalSince1970 + 2 * 3600 + 5 * 60, now: now) ?? ""
        let week = QuotaResetTime.spoken(until: now.timeIntervalSince1970 + 3 * 86400 + 4 * 3600 + 30 * 60, now: now) ?? ""
        L10n.language = .english
        let english = QuotaResetTime.spoken(until: now.timeIntervalSince1970 + 2 * 3600 + 5 * 60, now: now) ?? ""
        try check(russian == "2 ч 5 мин" && english == "2h 5m" && week.hasPrefix("3") && !week.contains("мин"),
                  "The reset time reads in the interface language with at most two units")
    }
}
