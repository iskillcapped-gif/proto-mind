import AppKit
import SwiftUI

extension NativeChecks {
    @MainActor
    static func composerInteraction() async throws {
        let editor = NativeComposer.Editor()
        editor.string = "Keep the unfinished draft"
        editor.setSelectedRange(NSRange(location: 8, length: 3))
        var editableChanges: [Bool] = []
        let observation = editor.observe(\.isEditable, options: [.new]) { _, change in
            if let value = change.newValue { editableChanges.append(value) }
        }
        defer { observation.invalidate(); editor.dismantleInteraction() }
        let initial = editor.isEditable
        editor.updateInteraction(enabled: true, surfaceEnabled: false)
        try check(editor.isEditable == initial && editableChanges.isEmpty,
                  "Covering the composer does not activate AppKit input methods during the SwiftUI update")
        var sends = 0
        editor.onSend = { sends += 1 }
        let enter = NSEvent.keyEvent(with: .keyDown, location: .zero, modifierFlags: [], timestamp: 0,
                                    windowNumber: 0, context: nil, characters: "\r", charactersIgnoringModifiers: "\r",
                                    isARepeat: false, keyCode: 36)!
        editor.keyDown(with: enter)
        try check(sends == 0 && editor.string == "Keep the unfinished draft",
                  "A covered composer refuses Send immediately, before the deferred AppKit update")
        try await Task.sleep(nanoseconds: 20_000_000)
        try check(!editor.isEditable && editableChanges == [false] && editor.selectedRange() == NSRange(location: 8, length: 3),
                  "Deferred composer deactivation preserves its draft and selection")
        editableChanges.removeAll()
        for _ in 0..<40 { editor.updateInteraction(enabled: true, surfaceEnabled: false) }
        try await Task.sleep(nanoseconds: 20_000_000)
        try check(editableChanges.isEmpty, "Unchanged composer renders never repeat the input-method editable setter")
        editor.updateInteraction(enabled: true, surfaceEnabled: true)
        editor.updateInteraction(enabled: true, surfaceEnabled: false)
        try await Task.sleep(nanoseconds: 20_000_000)
        try check(!editor.isEditable && editableChanges.isEmpty,
                  "Rapid presentation changes apply only the latest composer interaction state")
        editor.updateInteraction(enabled: true, surfaceEnabled: true)
        try await Task.sleep(nanoseconds: 20_000_000)
        editor.keyDown(with: enter)
        try check(editor.isEditable && editableChanges == [true] && sends == 1,
                  "Closing the presentation restores the same composer and its Send handler")
        editor.updateInteraction(enabled: false, surfaceEnabled: true)
        try await Task.sleep(nanoseconds: 20_000_000)
        try check(!editor.isEditable, "Archived composers remain read-only after a deferred update")
        editor.updateInteraction(enabled: true, surfaceEnabled: true)
        editor.requestProgrammaticFocus()
        editor.dismantleInteraction()
        try await Task.sleep(nanoseconds: 20_000_000)
        try check(!editor.isEditable && !editor.pendingProgrammaticFocus,
                  "A removed composer cancels queued activation and cannot reclaim focus")
    }

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
