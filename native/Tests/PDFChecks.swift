import AppKit
import Foundation
import PDFKit
import SwiftUI
import UniformTypeIdentifiers

extension NativeChecks {
    @MainActor
    static func syntheticPDF(_ pages: [String]) throws -> Data {
        let data = NSMutableData()
        var mediaBox = CGRect(x: 0, y: 0, width: 612, height: 792)
        guard let consumer = CGDataConsumer(data: data), let context = CGContext(consumer: consumer, mediaBox: &mediaBox, nil) else {
            throw NativeError.message("Cannot create synthetic PDF fixture")
        }
        for text in pages {
            context.beginPDFPage(nil)
            NSGraphicsContext.saveGraphicsState()
            NSGraphicsContext.current = NSGraphicsContext(cgContext: context, flipped: false)
            NSAttributedString(string: text, attributes: [.font: NSFont.systemFont(ofSize: 14)]).draw(in: CGRect(x: 30, y: 30, width: 550, height: 730))
            NSGraphicsContext.restoreGraphicsState()
            context.endPDFPage()
        }
        context.closePDF()
        return data as Data
    }

    @MainActor
    static func pdfAttachments(fixture: URL, python: URL, root: URL) async throws {
        guard let helperPath = LaunchConfiguration.argument("--pdf-helper") else { throw NativeError.message("PDF helper is required for Native checks") }
        let helper = URL(fileURLWithPath: helperPath).resolvingSymlinksInPath()
        let state = root.appendingPathComponent("pdf-state")
        let configuration = LaunchConfiguration(projectRoot: fixture, python: python, stateDirectory: state, pdfHelper: helper)
        let app = AppModel(configuration: configuration)
        defer { app.client.shutdown() }
        await app.start(); app.setProvider("mock")
        let document = try NativeAttachmentDrop.localURL(root.appendingPathComponent("selected document.pdf"))
        let original = try syntheticPDF(["PAGE ONE: Привет, локальный PDF.", "PAGE TWO: SELECTED PRIVATE EXCERPT", "PAGE THREE: NEVER SELECTED"])
        try original.write(to: document)
        try check(NativeAttachmentDrop.isPDF(document), "PDF has a dedicated attachment route outside workspace text files")
        try check(try NativePDFPageSelection.parse("1-3, 7, 2", total: 7) == [1, 2, 3, 7], "PDF page ranges are bounded, unique and sorted")
        for input in ["", "0", "2-1", "1-9", "1; /memory remember", "1,", "301", "-1", "1...3", "99-999999999999999"] {
            var refused = false
            do { _ = try NativePDFPageSelection.parse(input, total: 300) } catch { refused = true }
            try check(refused, "Invalid PDF page selection refused: \(input)")
        }

        let before = try fileBytes(state), coreBefore = try fileBytes(fixture)
        let pasteboard = NSPasteboard.withUniqueName()
        defer { pasteboard.releaseGlobally() }
        pasteboard.writeObjects([document as NSURL])
        let dropped = try NativeAttachmentDrop.pasteboardURLs(pasteboard)
        try check(dropped == [document], "Finder-style PDF pasteboard resolves one local file URL")
        try check(app.receiveAttachmentDrop(dropped), "AppKit composer accepts the PDF drop")
        for _ in 0..<150 where app.loadingDroppedAttachments { try await Task.sleep(nanoseconds: 100_000_000) }
        guard let initial = app.pdfPreview else { throw NativeError.message(app.error ?? "No PDF drop preview") }
        try check(initial.source.pages == [1] && initial.pages[0]["text"].text.contains("Привет"), "Real sandboxed PDFKit worker reads the selected Cyrillic text layer")
        try check(!app.loadingDroppedAttachments && !app.canReceiveAttachments && app.selected?.pendingPDFs.isEmpty == true,
                  "Drop finishes loading with preview only, no implicit attachment")
        await app.submit("Do not send from preview")
        try check(app.messages.isEmpty && (try fileBytes(state)) == before && (try fileBytes(fixture)) == coreBefore && !app.cloudConsent,
                  "Enter during PDF preview does not send, write stores, start a run or grant cloud")
        let selected = try await app.reloadPDFPreview(initial, pages: [2])
        try check(selected.source.pages == [2] && selected.pages[0]["text"].text.contains("SELECTED PRIVATE EXCERPT")
                  && !selected.pages[0]["text"].text.contains("PAGE THREE"), "Only explicitly selected page text appears in refreshed PDF preview")
        let raw = try await app.client.request("pdf_preview", ["path": .string(document.path), "pages": .array([.number(2)])])
        for change in ["text", "number", "hash", "payload"] {
            guard case .object(var invalid) = raw, case .object(var page) = raw["pages"].items[0], case .object(var metadata) = raw["pdf"] else { throw NativeError.message("Invalid fixture") }
            if change == "text" { page["text"] = .string("substituted") }
            if change == "number" { page["number"] = .number(1) }
            if change == "hash" { page["text_sha256"] = .string(String(repeating: "a", count: 64)) }
            if change == "payload" { metadata["text"] = .string("forbidden saved payload") }
            invalid["pages"] = .array([.object(page)]); invalid["pdf"] = .object(metadata)
            var refused = false
            do { _ = try NativePDFPreview(.object(invalid), conversationID: app.selectedID!, workspace: nil, canAttach: true) } catch { refused = true }
            try check(refused, "Tampered PDF preview refuses \(change)")
        }
        try app.attachPDF(selected); app.pdfPreview = nil
        let saved = try ChatStore(directory: state).load()
        try check(saved.version == 5 && saved.conversations[0].pendingPDFs == [selected.source.value], "PDF selection persists as metadata in private history v5")
        try check(!String(decoding: Data(contentsOf: app.store.url), as: UTF8.self).contains("SELECTED PRIVATE EXCERPT")
                  && (try Data(contentsOf: document)) == original, "No PDF original or extracted text is copied to conversation history")
        let strip = NSHostingController(rootView: PendingPDFAttachmentsView(model: app))
        for width in [0.0, 100.0, 640.0, 1000.0] {
            try check(strip.sizeThatFits(in: CGSize(width: width, height: 900)).height < 100, "PDF strip does not stretch window at width \(width)")
        }
        let restored = AppModel(configuration: configuration)
        try check(restored.selected?.pendingPDFs == [selected.source.value] && !restored.client.connected && restored.pdfPreview == nil,
                  "Restart restores PDF metadata without reading documents or contacting a provider")
        app.setComposer("Summarize selected pages"); app.flushDraft()
        let attached = try fileBytes(state)
        await app.refreshContextPreview()
        try check(app.contextPreview?.pdfSources.first?["state"].text == "ready"
                  && app.contextPreview?.manifest["pdfs"].items == [selected.source.value], "Context desk verifies selected PDF page text and manifest")
        try check(try fileBytes(state) == attached && fileBytes(fixture) == coreBefore, "PDF context inspection remains read-only")
        await app.submit("/commands status")
        try check(app.selected?.pendingPDFs == [selected.source.value] && app.messages.last?.pdfContext?.isEmpty == true && app.workSessions.isEmpty,
                  "Operator command bypasses PDF and leaves selected pages in draft")

        app.setProvider("codex"); app.cloudConsent = false
        let preCloud = try fileBytes(fixture)
        await app.submit("Summarize this PDF")
        try check(app.messages.last?.isError == true && app.selected?.pendingPDFs == [selected.source.value]
                  && app.workSessions.isEmpty && !app.cloudConsent && (try fileBytes(fixture)) == preCloud,
                  "PDF does not grant cloud, fall back or create a run without consent")
        app.setProvider("mock")
        try syntheticPDF(["REPLACED PDF"]).write(to: document)
        let preStale = try fileBytes(fixture)
        await app.submit("Summarize this PDF")
        try check(app.messages.last?.isError == true && app.composer == "Summarize this PDF" && app.workSessions.isEmpty
                  && (try fileBytes(fixture)) == preStale, "Changed PDF fails before dispatch and keeps draft without a core-store write")
        try original.write(to: document)
        await app.submit("Summarize this PDF")
        try check(app.messages.last?.isError == false && app.messages.last?.pdfContext == [selected.source.value]
                  && app.selected?.pendingPDFs.isEmpty == true && app.workSessions.count == 1,
                  "Explicit Mock send completes with the exact page manifest, then clears only the pending PDF")
        try check(app.messages.last?.notices.contains(where: { $0.contains("not a PDF-understanding model") }) == true,
                  "Mock PDF response explicitly disclaims analysis")
        try check(app.workSessions[0].value["context_manifest"]["pdfs"].items == [selected.source.value]
                  && !app.workSessions[0].value.pretty.contains("SELECTED PRIVATE EXCERPT"), "Run journal saves only PDF provenance, not selected text")
        try check(app.selected!.history.contains { $0["content"].text.contains("Earlier PDF page text is NOT included") }
                  && !app.selected!.history.contains { $0.pretty.contains("SELECTED PRIVATE EXCERPT") || $0.pretty.contains(document.path) },
                  "Next-turn history does not replay PDF text or source paths")
        await app.submit("Another question without PDF")
        try check(app.messages.last?.pdfContext?.isEmpty == true, "Following normal turn does not reattach PDF automatically")

        let empty = root.appendingPathComponent("blank.pdf").resolvingSymlinksInPath()
        try syntheticPDF([""]).write(to: empty)
        await app.previewDroppedAttachments([empty])
        guard let blank = app.pdfPreview else { throw NativeError.message(app.error ?? "No blank PDF preview") }
        var refusedBlank = false
        do { try app.attachPDF(blank) } catch { refusedBlank = true }
        try check(!blank.hasText && refusedBlank && app.selected?.pendingPDFs.isEmpty == true, "Blank or scan-only page previews explain missing text and cannot attach")
        app.pdfPreview = nil
        let broken = root.appendingPathComponent("broken.pdf").resolvingSymlinksInPath()
        try Data("%PDF-broken".utf8).write(to: broken)
        let encrypted = root.appendingPathComponent("encrypted.pdf").resolvingSymlinksInPath()
        guard let protected = PDFDocument(data: original)?.dataRepresentation(options: [PDFDocumentWriteOption.userPasswordOption: "fixture-password", PDFDocumentWriteOption.ownerPasswordOption: "fixture-owner"]) else { throw NativeError.message("Cannot create encrypted fixture") }
        try protected.write(to: encrypted)
        let link = root.appendingPathComponent("linked.pdf").resolvingSymlinksInPath()
        try FileManager.default.createSymbolicLink(at: link, withDestinationURL: document)
        for urls in [[broken], [encrypted], [link], [document, broken]] {
            app.error = nil
            let unchanged = try fileBytes(state), targets = try fileBytes(fixture)
            await app.previewDroppedAttachments(urls)
            try check(app.pdfPreview == nil && app.error != nil && !app.loadingDroppedAttachments
                      && (try fileBytes(state)) == unchanged && (try fileBytes(fixture)) == targets,
                      "Invalid, encrypted, symlink or mixed PDF drop fails cleanly without draft/store mutation: \(urls.map(\.lastPathComponent))")
        }
        let badState = root.appendingPathComponent("bad-pdf-history")
        try FileManager.default.createDirectory(at: badState, withIntermediateDirectories: true)
        let corrupt = Data("broken history".utf8)
        try corrupt.write(to: badState.appendingPathComponent("conversations.json"))
        let blocked = AppModel(configuration: LaunchConfiguration(projectRoot: fixture, python: python, stateDirectory: badState, pdfHelper: helper))
        let blockedPreview = try NativePDFPreview(raw, conversationID: blocked.selectedID!, workspace: nil, canAttach: true)
        var refusedSave = false
        do { try blocked.attachPDF(blockedPreview) } catch { refusedSave = true }
        try check(refusedSave && blocked.selected?.pendingPDFs.isEmpty == true && (try Data(contentsOf: blocked.store.url)) == corrupt,
                  "Failed PDF history save rolls back draft and preserves damaged history")
        try check(try Data(contentsOf: document) == original && !app.fullAccessEnabled && !app.cloudConsent,
                  "All PDF checks preserve original file and do not enable cloud or full-access tools")
    }
}
