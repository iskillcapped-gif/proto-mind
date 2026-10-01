import AppKit
import SwiftUI

extension NativeChecks {
    /// Settings → Connections lists every connection once, by purpose; a deep link opens its page,
    /// and leaving the tab returns to the list.
    @MainActor static func connectionsSettings(root: URL) throws {
        let kinds = ConnectionGroup.allCases.flatMap(\.kinds)
        try check(kinds.count == ConnectionKind.allCases.count && Set(kinds) == Set(ConnectionKind.allCases),
                  "Every connection appears exactly once in the Connections list")
        let suite = "pm-connections-" + UUID().uuidString
        let defaults = UserDefaults(suiteName: suite)!
        let app = AppModel(configuration: LaunchConfiguration(projectRoot: root, python: root, stateDirectory: root.appendingPathComponent("connections-state")),
                           uiDefaults: defaults)
        defer { app.shutdown(); defaults.removePersistentDomain(forName: suite) }
        app.settingsConnection = .api
        app.settingsSection = .services
        try check(app.settingsConnection == .api, "A link such as “Connect API…” opens that connection's page")
        app.settingsSection = .models
        try check(app.settingsConnection == nil, "Leaving Connections returns it to the list")
    }
}
