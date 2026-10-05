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

extension NativeChecks {
    /// `--link-pointer-window`: a real reply with a link in a window at the screen's right edge for
    /// ten seconds, to check the pointer by hand or with `screencapture -C`. Nothing is opened.
    @MainActor static func linkPointerWindow() async throws {
        let app = NSApplication.shared
        app.setActivationPolicy(.regular)
        let reply = MessageMarkdownView(text: "Read the [setup guide](https://example.com/guide) before you start.", copy: { _ in },
                                        openLink: { print("OPENED", $0.absoluteString); fflush(stdout) })
        let screen = NSScreen.screens[0].frame
        let window = NSWindow(contentRect: NSRect(x: screen.maxX - 520, y: screen.midY, width: 500, height: 160),
                              styleMask: [.titled], backing: .buffered, defer: false)
        window.title = "PM link pointer"
        window.contentView = NSHostingView(rootView: reply.padding(24).frame(width: 500, height: 160, alignment: .topLeading))
        window.makeKeyAndOrderFront(nil)
        // Pointer updates need AppKit's event loop, which the async checks do not otherwise run.
        DispatchQueue.main.asyncAfter(deadline: .now() + 10) {
            window.close(); app.stop(nil)
            if let wake = NSEvent.otherEvent(with: .applicationDefined, location: .zero, modifierFlags: [], timestamp: 0,
                                             windowNumber: 0, context: nil, subtype: 0, data1: 0, data2: 0) { app.postEvent(wake, atStart: false) }
        }
        app.run()
    }
}
