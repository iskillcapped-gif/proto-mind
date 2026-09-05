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
        defer { app.workspacePanel.closeAll(); app.client.shutdown() }
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
    }
}
