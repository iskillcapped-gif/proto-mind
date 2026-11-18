import AppKit
import Foundation
import SwiftUI

extension NativeChecks {
    @MainActor
    static func workspacePanelContracts(root: URL) throws {
        let panel = WorkspacePanelModel()
        let conversationID = UUID()
        let file = WorkspaceTextPreview(conversationID: conversationID, root: root.path,
                                        value: .object(["path": .string("README.md"), "preview": .string("# Initial")]))
        try check(!panel.visible && panel.tabs.isEmpty, "Work panel starts closed without creating a browser or reading files")
        let first = panel.open(.text(file))
        let updated = WorkspaceTextPreview(conversationID: conversationID, root: root.path,
                                           value: .object(["path": .string("README.md"), "preview": .string("# Refreshed")]))
        try check(panel.open(.text(updated)) == first && panel.tabs.count == 1,
                  "Refreshing a file replaces its tab snapshot without creating duplicates")
        let other = WorkspaceTextPreview(conversationID: UUID(), root: root.path, value: file.value)
        let second = panel.open(.text(other))
        try check(second != first && panel.tabs.count == 2, "Same file in another conversation has a separate attachment scope")
        panel.close(second!)
        try check(panel.selectedID == first && panel.tabs.count == 1, "Closing the selected tab selects a remaining neighbour")
        for index in 1..<WorkspacePanelModel.maximumTabs {
            _ = panel.open(.text(WorkspaceTextPreview(conversationID: conversationID, root: root.path,
                                                     value: .object(["path": .string("\(index).txt")]))))
        }
        let existing = panel.tabs.map(\.id)
        let overflow = panel.open(.text(WorkspaceTextPreview(conversationID: conversationID, root: root.path,
                                                             value: .object(["path": .string("overflow.txt")]))))
        try check(overflow == nil && panel.tabs.map(\.id) == existing && panel.error != nil,
                  "Tab capacity refuses another tab without silently closing user pages")
        panel.closeAll()
        try check(panel.tabs.isEmpty && panel.selectedID == nil && !panel.visible, "Closing the workspace clears transient tabs")

        for total: CGFloat in [540, 650, 1000, 1600] {
            let half = WorkspacePanelLayout.width(total: total, fraction: 0.5)
            try check(abs(half * 2 + WorkspacePanelLayout.divider - total) < 1,
                      "Work panel opens at half width in a \(Int(total))-point content area")
            let narrow = WorkspacePanelLayout.width(total: total, fraction: -2)
            let wide = WorkspacePanelLayout.width(total: total, fraction: 3)
            try check(narrow >= min(300, (total - 6) / 2) && wide <= total - 6 - narrow,
                      "Dragging the divider keeps both panes inside \(Int(total)) points")
        }
        for input in ["https://example.invalid/path?q=1", "http://127.0.0.1:8123/", "example.invalid"] {
            try check(NativeBrowserURL.isWebURL(NativeBrowserURL.parse(input)), "Browser accepts explicit web address: \(input)")
        }
        for input in ["", "javascript:alert(1)", "file:/tmp/example", "file:///tmp/example", "data:text/html,hello",
                      "mailto:example@example.invalid", "ftp://example.invalid", "https://user:pass@example.invalid",
                      "https://", "some words", "https://example.invalid/\u{0000}"] {
            var refused = false
            do { _ = try NativeBrowserURL.parse(input) } catch { refused = true }
            try check(refused, "Browser rejects non-web, credential-bearing or malformed input")
        }
        let browser = NativeBrowserTab()
        browser.navigate("file:///tmp/not-opened")
        try check(!browser.webView.configuration.websiteDataStore.isPersistent && browser.webView.url == nil && browser.error != nil,
                  "A browser tab has ephemeral data and refuses file navigation before loading")
        browser.close()
        let links = MarkdownBlock.inline("[file](README.md) [web](https://example.invalid) [command](javascript:alert)",
                                         allowFileLinks: true).runs.compactMap(\.link)
        try check(links.count == 2 && links.allSatisfy { $0.scheme == nil || $0.scheme == "https" },
                  "Workspace Markdown enables explicit file links while removing command schemes")
    }

    @MainActor
    static func workspacePanelIntegration(fixture: URL, python: URL, root: URL) async throws {
        let state = root.appendingPathComponent("work-panel-state")
        let helper = LaunchConfiguration.argument("--pdf-helper").map { URL(fileURLWithPath: $0).resolvingSymlinksInPath() }
        let app = AppModel(configuration: LaunchConfiguration(projectRoot: fixture, python: python, stateDirectory: state, pdfHelper: helper))
        defer { app.workspacePanel.closeAll(); app.shutdown() }
        await app.start(); app.setProvider("mock"); await app.bindWorkspace(fixture.path)
        let source = fixture.appendingPathComponent("panel-readme.md")
        try Data("# A local document\n\nNo model call.\n".utf8).write(to: source)
        let pdfFile = fixture.appendingPathComponent("panel-pages.pdf")
        try syntheticPDF(["PANEL PAGE ONE", "PANEL PAGE TWO"]).write(to: pdfFile)
        let bitmap = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: 16, pixelsHigh: 10,
                                      bitsPerSample: 8, samplesPerPixel: 3, hasAlpha: false, isPlanar: false,
                                      colorSpaceName: .deviceRGB, bytesPerRow: 48, bitsPerPixel: 24)!
        bitmap.bitmapData!.initialize(repeating: 120, count: bitmap.bytesPerRow * bitmap.pixelsHigh)
        let imageFile = fixture.appendingPathComponent("panel-image.png")
        try bitmap.representation(using: .png, properties: [:])!.write(to: imageFile)
        let before = try fileBytes(state), sourceBefore = try fileBytes(fixture)

        await app.openWorkspaceEntry(.object(["path": .string(source.lastPathComponent)]))
        guard case .text(let text)? = app.workspacePanel.selected?.content else { throw NativeError.message("Missing text work tab") }
        try check(text.value["preview"].text.contains("local document") && app.selected?.pendingFiles.isEmpty == true,
                  "Opening a real workspace document creates a readable tab without an attachment")
        await app.openWorkspaceEntry(.object(["path": .string(imageFile.lastPathComponent)]))
        guard case .image(let image)? = app.workspacePanel.selected?.content else { throw NativeError.message(app.error ?? "Missing image work tab") }
        try check(image.source.value["width"].integer == 16 && app.imagePreview == nil && app.selected?.pendingImages.isEmpty == true,
                  "Image work tab reuses validated pixels without opening an attachment sheet or selecting context")
        await app.openWorkspaceEntry(.object(["path": .string(pdfFile.lastPathComponent)]))
        guard let pdfID = app.workspacePanel.selectedID, case .pdf(let pdf)? = app.workspacePanel.selected?.content else {
            throw NativeError.message(app.error ?? "Missing PDF work tab")
        }
        await app.refreshWorkspacePDF(pdf, page: 2, tabID: pdfID)
        guard case .pdf(let secondPage)? = app.workspacePanel.selected?.content else { throw NativeError.message("Missing next PDF page") }
        try check(secondPage.source.pages == [2] && secondPage.pages[0]["text"].text.contains("PANEL PAGE TWO")
                  && app.pdfPreview == nil && app.selected?.pendingPDFs.isEmpty == true,
                  "PDF tab reads the selected next page with the original file hash and no attachment")
        let readableTabs = app.workspacePanel.tabs.map(\.id)
        app.workspacePanel.visible = false
        await app.openWorkspaceEntry(.object(["path": .string("missing-panel-document.md")]))
        try check(app.workspacePanel.visible && app.workspacePanel.error != nil
                  && app.workspacePanel.selectedID == pdfID && app.workspacePanel.tabs.map(\.id) == readableTabs,
                  "A missing document shows a panel error while preserving every readable tab")
        try check(try fileBytes(state) == before && fileBytes(fixture) == sourceBefore
                  && !app.cloudConsent && !app.fullAccessEnabled,
                  "File, image and PDF tab navigation preserve all fixture history/core bytes and grant no authority")
        app.workspacePanel.close(pdfID)
        var refused = false
        do { try app.workspacePanel.replacePDF(pdfID, expected: secondPage, with: pdf) } catch { refused = true }
        try check(refused && !app.workspacePanel.tabs.contains(where: { $0.id == pdfID }),
                  "A late PDF response cannot reopen a closed tab")
        app.newConversation()
        app.attachWorkspaceText(text)
        try check(app.selected?.pendingFiles.isEmpty == true && app.workspacePanel.error != nil,
                  "A retained document tab cannot attach a previous conversation's file to a new conversation")
        let tabsBefore = app.workspacePanel.tabs.map(\.id)
        app.showMessage(ChatMessage(role: "assistant", text: "Details fixture"))
        try check(app.showInspector && app.workspacePanel.tabs.map(\.id) == tabsBefore,
                  "Answer details use a separate presentation without replacing working tabs")
        try await workspaceOrigins(app: app, root: root, picture: imageFile)
    }

    @MainActor
    private static func workspaceOrigins(app: AppModel, root: URL, picture: URL) async throws {
        let a = try NativeAttachmentDrop.localURL(root.appendingPathComponent("project-A"))
        let b = try NativeAttachmentDrop.localURL(root.appendingPathComponent("project-B"))
        let fileManager = FileManager.default
        for folder in [a, b] {
            try fileManager.createDirectory(at: folder.appendingPathComponent("docs"), withIntermediateDirectories: true)
            try Data(folder.lastPathComponent.utf8).write(to: folder.appendingPathComponent("docs/notes.md"))
            try fileManager.copyItem(at: picture, to: folder.appendingPathComponent("picture.png"))
            let params: [String: JSONValue] = ["workspace_root": .string(folder.path), "path": .string("proposal.docx"),
                "content": .object(["title": .string(folder.lastPathComponent), "paragraphs": .array([.string("Example")])])]
            _ = try await app.serviceClient.request("document_create", params)
        }
        await app.bindWorkspace(a.path)
        let mainID = app.selectedID!
        var side = Conversation(); side.workspacePath = b.path; side.provider = "mock"; side.draft = "side draft"
        app.conversations.append(side)
        let panel = app.workspacePanels.lower
        panel.open(.conversation(side.id))
        try check(panel.workingDirectory(in: app).path == b.path && app.selected?.workspacePath == a.path,
                  "Terminal and CLI directory follows the panel chat in B while the main editor is in A")
        panel.openTerminal(in: app, executable: "/bin/pwd", arguments: [])
        guard case .terminal(let terminal) = panel.selected?.content else { throw NativeError.message("Terminal tab missing") }
        try check(terminal.directory.path == b.path && panel.sourceConversationID == side.id,
                  "A terminal opened from the side chat keeps its owning folder for subsequent file and CLI actions")
        await app.openWorkspaceLink(URL(string: "proposal.docx")!)?.value
        guard case .document(let mainDoc) = app.workspacePanel.selected?.content else { throw NativeError.message(app.workspacePanel.error ?? "Main Office tab missing") }
        await app.openWorkspaceLink(URL(string: "proposal.docx")!, in: panel, conversationID: side.id)?.value
        guard case .document(let sideDoc) = panel.selected?.content else { throw NativeError.message(panel.error ?? "Side Office tab missing") }
        try check(mainDoc.url.deletingLastPathComponent().path == a.path && sideDoc.url.deletingLastPathComponent().path == b.path
                    && mainDoc.conversationID == mainID && sideDoc.conversationID == side.id && mainDoc.sha256 != sideDoc.sha256,
                  "Identical Office filenames in two chats open as separate verified Quick Look documents")
        for (id, target, folder) in [(mainID, app.workspacePanel, a), (side.id, panel, b)] {
            let capturedID = id == mainID ? nil : id
            await app.openWorkspaceLink(URL(string: "picture.png")!, in: target, conversationID: capturedID)?.value
            guard case .image(let image) = target.selected?.content else { throw NativeError.message(target.error ?? "Picture tab missing") }
            try check(image.conversationID == id && image.source.path == folder.appendingPathComponent("picture.png").path,
                      "PNG preview uses the originating chat's folder in both surfaces")
            await app.openWorkspaceLink(URL(string: "notes.md")!, relativeTo: folder.appendingPathComponent("docs"), in: target, conversationID: capturedID)?.value
            guard case .text(let file) = target.selected?.content else { throw NativeError.message(target.error ?? "Markdown tab missing") }
            try check(file.conversationID == id && file.value["preview"].text == folder.lastPathComponent,
                      "Nested relative Markdown links resolve in the right project")
        }
        let tab = panel.selectedID
        await app.openWorkspaceLink(a.appendingPathComponent("picture.png"), in: panel, conversationID: side.id)?.value
        try check(panel.error != nil && panel.selectedID == tab && app.selectedID == mainID && app.conversations.last?.draft == "side draft",
                  "An out-of-project file link leaves both the selected file and other chat draft intact")
        let keptImage = panel.tabs.compactMap { tab -> NativeImagePreview? in
            if case .image(let preview) = tab.content { return preview }
            return nil
        }.first!
        let sideIndex = app.conversations.firstIndex { $0.id == side.id }!
        app.setConversationWorkspace(a.path, at: sideIndex)
        try check(!app.canAttachImage(keptImage) && app.conversations[sideIndex].pendingImages.isEmpty,
                  "An image retained in a side tab cannot be attached after that chat changes project")
        let folderless = Conversation()
        app.conversations.append(folderless); panel.open(.conversation(folderless.id))
        try check(panel.workingDirectory(in: app) == fileManager.homeDirectoryForCurrentUser,
                  "A folderless side chat opens Terminal at home, independently of the main project")

        let idx = app.conversations.firstIndex { $0.id == mainID }!
        app.conversations[idx].provider = "claude"
        let limit = ChatMessage(role: "report", text: AppModel.claudeLimitPrefixes[0], isError: true)
        app.conversations[idx].messages.append(limit)
        let date = Date.now.addingTimeInterval(3600)
        app.limitContinuations.schedule(mainID, at: date, after: limit.id, app: app)
        try check(app.limitContinuations.scheduled[mainID] == date, "A dated continuation is pending in its original workspace")
        await app.bindWorkspace(b.path)
        app.limitContinuations.schedule(mainID, at: .now, after: limit.id, app: app)
        try check(app.limitContinuations.scheduled[mainID] == nil && app.limitInterruption(in: mainID) == nil
                    && app.conversations[idx].messages.last?.limitOrigin == ClaudeLimitOrigin(workspace: a.path),
                  "Rebinding A to B cancels the timer and prevents rearming that old interruption in B")
        await app.bindWorkspace(a.path)
        try check(app.limitInterruption(in: mainID)?.id == limit.id && app.limitContinuations.scheduled[mainID] == nil,
                  "Returning to the original project allows a fresh explicit click only")
        app.setConversationWorkspace(nil, at: idx)
        let noFolder = ChatMessage(role: "report", text: AppModel.claudeLimitPrefixes[1], isError: true,
                                   limitOrigin: ClaudeLimitOrigin(workspace: nil))
        app.conversations[idx].messages.append(noFolder)
        let persisted = try JSONDecoder().decode(ChatMessage.self, from: JSONEncoder().encode(noFolder))
        app.limitContinuations.schedule(mainID, at: date, after: noFolder.id, app: app)
        app.setConversationWorkspace(b.path, at: idx)
        try check(persisted.limitOrigin == ClaudeLimitOrigin(workspace: nil) && app.limitContinuations.scheduled[mainID] == nil
                    && app.limitInterruption(in: mainID) == nil && !app.isRunning(mainID),
                  "A folderless interruption survives encoding and cannot resume into a newly chosen project")
    }
}
