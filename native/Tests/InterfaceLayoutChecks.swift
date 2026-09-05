import AppKit
import SwiftUI

extension NativeChecks {
    @MainActor
    static func interfaceLayout(root: URL) throws {
        let state = root.appendingPathComponent("interface-layout")
        let app = AppModel(configuration: LaunchConfiguration(projectRoot: root, python: root, stateDirectory: state))
        app.conversations[0].provider = "codex"
        app.conversations[0].model = String(repeating: "long-model-name-", count: 9)
        app.conversations[0].pendingCriteria = ["Check the result", "Keep the original files"]
        let original = app.currentHistoryArchive
        let composer = NSHostingController(rootView: ComposerView(model: app))
        for width: CGFloat in [240, 300, 360, 480, 790] {
            let size = composer.sizeThatFits(in: CGSize(width: width, height: 280))
            try check(size.width <= width + 1 && size.height <= 280,
                      "Composer keeps send/access controls within \(Int(width)) points with a long model name and criteria")
        }
        app.busy = true
        let busyComposer = NSHostingController(rootView: ComposerView(model: app))
        for width: CGFloat in [240, 360, 790] {
            let size = busyComposer.sizeThatFits(in: CGSize(width: width, height: 280))
            try check(size.width <= width + 1 && size.height <= 280,
                      "Live composer remains bounded with Stop at \(Int(width)) points")
        }
        app.busy = false
        for section in NativeSettingsSection.allCases {
            app.settingsSection = section
            let settings = NSHostingController(rootView: NativeSettingsView(model: app))
            let size = settings.sizeThatFits(in: CGSize(width: 800, height: 680))
            try check(size.width <= 801 && size.height <= 681, "Settings section \(section.rawValue) fits the application window")
        }
        try check(app.currentHistoryArchive.conversations == original.conversations
                  && app.currentHistoryArchive.selectedID == original.selectedID
                  && !app.client.connected && !app.cloudConsent && !app.fullAccessEnabled
                  && !FileManager.default.fileExists(atPath: state.path),
                  "Interface layout and settings navigation preserve history and grant no provider or tool authority")
    }
}
