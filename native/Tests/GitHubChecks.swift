import AppKit
import SwiftUI

extension NativeChecks {
    @MainActor
    static func githubContracts(root: URL) throws {
        let app = AppModel(configuration: LaunchConfiguration(projectRoot: root, python: root, stateDirectory: root.appendingPathComponent("github-ui")))
        app.setComposer("Существующий черновик")
        app.section = .github
        app.transcriptDestination = TranscriptDestination(conversationID: app.selectedID!, messageID: UUID())
        app.workspacePanel.expanded = true
        let grants = app.agentGrants
        app.github.discuss("Посмотри репозиторий https://github.com/example/project", app: app)
        try check(app.composer == "Существующий черновик\n\nПосмотри репозиторий https://github.com/example/project" && app.section == .chat,
                  "Discussing a GitHub repository preserves the existing draft and prepares an unsent message")
        try check(app.transcriptDestination?.messageID == nil && !app.workspacePanel.expanded,
                  "GitHub discussion returns to the current draft even after a historical match or expanded panel")
        try check(!app.client.connected && !app.cloudConsent && app.agentGrants.count == grants.count && !app.busy,
                  "GitHub draft preparation starts no provider and grants no Mac access")
        app.busy = true
        let draft = app.composer
        app.github.discuss("Should not replace the draft", app: app)
        try check(app.composer == draft, "GitHub cannot change the composer during an active turn")
        app.busy = false
        app.conversations[0].archived = true
        app.github.discuss("Should not replace the draft", app: app)
        try check(app.composer == draft, "GitHub preserves archived conversation drafts")
        let host = NSHostingController(rootView: GitHubView(app: app, github: app.github))
        let size = host.sizeThatFits(in: CGSize(width: 640, height: 640))
        try check(size.width <= 641 && size.height <= 641, "GitHub connection view fits the minimum workspace")
    }
}
