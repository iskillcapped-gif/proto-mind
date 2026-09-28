import AppKit
import CryptoKit
import SwiftUI

extension NativeChecks {
    /// Library fixtures: a Retina screenshot, a PDF and a project text file, with the metadata a message carries.
    static func libraryFixtures(root: URL) throws -> (images: [JSONValue], pdfs: [JSONValue], files: [JSONValue], workspace: URL) {
        let originals = root.appendingPathComponent("library-originals", isDirectory: true)
        let workspace = root.appendingPathComponent("library-project", isDirectory: true)
        try FileManager.default.createDirectory(at: originals, withIntermediateDirectories: true)
        try FileManager.default.createDirectory(at: workspace.appendingPathComponent("notes"), withIntermediateDirectories: true)
        let picture = try zoomPreview(width: 1200, height: 800, dpi: 144)
        let screenshot = originals.appendingPathComponent("Снимок экрана — 2026-09-28.png")
        try picture.bytes.write(to: screenshot)
        let pdf = originals.appendingPathComponent("Договор.pdf"), pdfBytes = Data("%PDF-1.4\n% library check\n%%EOF\n".utf8)
        try pdfBytes.write(to: pdf)
        let text = Data("# План\nПроверить библиотеку.\n".utf8)
        try text.write(to: workspace.appendingPathComponent("notes/plan.md"))
        func sha(_ data: Data) -> String { SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined() }
        let image: JSONValue = .object(["schema": .string("proto_mind.native_image.v1"), "path": .string(screenshot.path), "name": .string(screenshot.lastPathComponent),
                                        "sha256": .string(sha(picture.bytes)), "mime_type": .string("image/png"), "size_bytes": .number(Double(picture.bytes.count)),
                                        "width": .number(1200), "height": .number(800)])
        let document: JSONValue = .object(["schema": .string("proto_mind.native_pdf.v1"), "path": .string(pdf.path), "name": .string(pdf.lastPathComponent),
                                           "sha256": .string(sha(pdfBytes)), "mime_type": .string("application/pdf"), "size_bytes": .number(Double(pdfBytes.count)),
                                           "page_count": .number(3), "pages": .array([])])
        let file: JSONValue = .object(["path": .string("notes/plan.md"), "sha256": .string(sha(text)), "included_chars": .number(30), "truncated": .bool(false)])
        return ([image], [document], [file], workspace)
    }

    /// Pictures and files sent to chats stay in PM's library after their originals are gone,
    /// until the operator deletes them.
    @MainActor static func attachmentLibrary(root: URL) async throws {
        let folder = AttachmentLibraryStore.folder(root.appendingPathComponent("library-state"))
        let fixtures = try libraryFixtures(root: root)
        let first = UUID(), second = UUID(), chat = UUID()
        let candidates = AttachmentLibraryStore.candidates(images: fixtures.images, pdfs: fixtures.pdfs, files: fixtures.files, workspace: fixtures.workspace.path,
                                                           conversationID: chat, messageID: first, sentAt: Date(timeIntervalSince1970: 1_790_000_000))
        try check(candidates.map(\.kind) == [.image, .pdf, .file] && candidates[2].file.path == fixtures.workspace.appendingPathComponent("notes/plan.md").path,
                  "A sent message's pictures, PDFs and project text files become library candidates")
        for candidate in candidates { try check(try AttachmentLibraryStore.capture(candidate, in: folder), "Sent \(candidate.kind.rawValue) is copied to the library") }
        let again = AttachmentLibraryStore.candidates(images: fixtures.images, pdfs: [], files: [], workspace: nil, conversationID: chat, messageID: second,
                                                      sentAt: Date(timeIntervalSince1970: 1_790_000_600))
        try check(try AttachmentLibraryStore.capture(again[0], in: folder), "Sending the same picture again is recorded")
        let entries = AttachmentLibraryStore.entries(in: folder)
        let picture = entries.first { $0.kind == .image }
        let copies = try FileManager.default.contentsOfDirectory(atPath: folder.appendingPathComponent(picture?.sha256 ?? "").appendingPathComponent("original").path)
        try check(entries.count == 3 && entries.first?.kind == .image && picture?.sources.map(\.messageID) == [first, second] && copies.count == 1
                  && picture?.name == "Снимок экрана — 2026-09-28.png",
                  "One copy per SHA-256 remembers every message that sent it, the latest first in the list")

        var info = stat()
        let privateModes = [folder.path, folder.appendingPathComponent(picture!.sha256).path].allSatisfy { lstat($0, &info) == 0 && info.st_mode & 0o077 == 0 }
            && lstat(AttachmentLibraryStore.copy(of: picture!.sha256, in: folder)!.path, &info) == 0 && info.st_mode & 0o077 == 0
        try check(privateModes, "Library folders and copies are private to the operator's account")

        // The original is deleted: the chat's picture and its preview come from the library copy.
        try FileManager.default.removeItem(atPath: fixtures.images[0]["path"].text)
        AttachmentThumbnails.library = folder
        AttachmentThumbnails.forget(picture!.sha256)
        let thumbnail = await AttachmentThumbnails.load(fixtures.images[0])
        let library = AttachmentLibraryModel(stateDirectory: root.appendingPathComponent("library-state"))
        let preview = library.imagePreview(picture!.sha256, conversationID: chat)
        try check(thumbnail != nil && preview?.source.sha256 == picture!.sha256 && preview?.pointSize == CGSize(width: 600, height: 400),
                  "A picture whose original was deleted still shows and opens from the library copy")

        // A changed or linked original is never kept under the recorded SHA-256.
        let changed = fixtures.workspace.appendingPathComponent("notes/plan.md")
        try Data("# Другой план\n".utf8).write(to: changed)
        var stale = candidates[2]
        try AttachmentLibraryStore.remove(stale.sha256, in: folder)
        try check(!(try AttachmentLibraryStore.capture(stale, in: folder)), "A file changed after it was sent is not copied")
        let pdfSHA = candidates[1].sha256, link = fixtures.workspace.appendingPathComponent("notes/link.pdf")
        try AttachmentLibraryStore.remove(pdfSHA, in: folder)
        try FileManager.default.createSymbolicLink(at: link, withDestinationURL: URL(fileURLWithPath: fixtures.pdfs[0]["path"].text))
        stale = AttachmentLibraryStore.Candidate(kind: .pdf, file: link, name: "link.pdf", sha256: pdfSHA, mimeType: "application/pdf",
                                                 width: 0, height: 0, pageCount: 1, source: candidates[1].source)
        try check((try? AttachmentLibraryStore.capture(stale, in: folder)) != true && AttachmentLibraryStore.copy(of: pdfSHA, in: folder) == nil,
                  "A symbolic link is not followed into the library")
        try check(try AttachmentLibraryStore.capture(candidates[1], in: folder), "The PDF itself is copied again")
        try check(["../up.png", ".hidden", "entry.json", "a/b"].allSatisfy { AttachmentLibraryStore.fileName($0, kind: .image) == "picture.png" }
                  && AttachmentLibraryStore.fileName("Снимок.png", kind: .image) == "Снимок.png", "Unsafe names are replaced by neutral ones")

        // Deleting from the library is final: the chat falls back to a placeholder.
        await library.reload()
        try library.remove(library.entries.first { $0.kind == .image }!)
        let gone = await AttachmentThumbnails.load(fixtures.images[0])
        try check(library.entries.map(\.kind) == [.pdf] && gone == nil && AttachmentLibraryStore.copy(of: picture!.sha256, in: folder) == nil,
                  "Deleting a picture removes its copy; the chat then shows a placeholder")

        // The app records a sent message's attachments one after another, off the main thread.
        let model = AttachmentLibraryModel(stateDirectory: root.appendingPathComponent("library-model-state"))
        await model.reload()
        let pdfOnly = AttachmentLibraryStore.candidates(images: [], pdfs: fixtures.pdfs, files: [], workspace: nil, conversationID: chat, messageID: first, sentAt: Date())
        await model.capture(pdfOnly)?.value
        try check(model.entries.map(\.name) == ["Договор.pdf"] && model.entries.first?.pageCount == 3, "A loaded library shows a newly sent PDF")
    }
}
