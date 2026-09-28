import AppKit
import CryptoKit
import Darwin
import Foundation

/// A picture or file the operator sent to a chat, kept by PM under its SHA-256.
struct AttachmentLibraryEntry: Identifiable, Equatable, Sendable {
    enum Kind: String, CaseIterable, Sendable { case image, pdf, file }
    struct Source: Equatable, Sendable {
        let conversationID: UUID
        let messageID: UUID
        let sentAt: Date
        /// Where the original was when it was sent.
        let path: String
    }
    let sha256: String
    let kind: Kind
    let name: String
    let mimeType: String
    let size: Int
    let width: Int
    let height: Int
    let pageCount: Int
    let addedAt: Date
    let sources: [Source]
    var id: String { sha256 }
    var lastSentAt: Date { sources.map(\.sentAt).max() ?? addedAt }

    /// The image as a message carries it, pointing at the library copy.
    func imageMetadata(copy: URL) -> JSONValue {
        .object(["schema": .string("proto_mind.native_image.v1"), "path": .string(copy.path), "name": .string(copy.lastPathComponent),
                 "sha256": .string(sha256), "mime_type": .string(mimeType), "size_bytes": .number(Double(size)),
                 "width": .number(Double(width)), "height": .number(Double(height))])
    }
}

/// Copies of what the operator sent to chats, one folder per SHA-256: `entry.json` and the file
/// under its original name in `original/`. A copy stays until the operator deletes it, so a
/// message can still show a picture after its original was moved or deleted. Like the original
/// attachments, the library is not part of private backups.
enum AttachmentLibraryStore {
    static let folderName = "attachment_library"
    static let schema = "proto_mind.attachment_library_entry.v1"
    static let maximumSources = 200

    /// One attachment of a sent message, with the file it was read from.
    struct Candidate: Sendable {
        let kind: AttachmentLibraryEntry.Kind
        let file: URL
        let name: String
        let sha256: String
        let mimeType: String
        let width: Int
        let height: Int
        let pageCount: Int
        let source: AttachmentLibraryEntry.Source
    }

    static func folder(_ state: URL) -> URL { state.appendingPathComponent(folderName, isDirectory: true) }

    static func limit(_ kind: AttachmentLibraryEntry.Kind) -> Int {
        switch kind {
        case .image: return NativeImageAttachment.maximumBytes
        case .pdf: return NativePDFAttachment.maximumBytes
        case .file: return 256 * 1024
        }
    }

    /// What a message (or a task update) sent: pictures and PDFs by their absolute paths, text files
    /// relative to the conversation's project folder.
    static func candidates(images: [JSONValue], pdfs: [JSONValue], files: [JSONValue], workspace: String?,
                           conversationID: UUID, messageID: UUID, sentAt: Date) -> [Candidate] {
        func source(_ path: String) -> AttachmentLibraryEntry.Source {
            .init(conversationID: conversationID, messageID: messageID, sentAt: sentAt, path: path)
        }
        var result: [Candidate] = []
        for image in images where (try? NativeImageAttachment(image)) != nil {
            result.append(Candidate(kind: .image, file: URL(fileURLWithPath: image["path"].text), name: image["name"].text, sha256: image["sha256"].text,
                                    mimeType: image["mime_type"].text, width: image["width"].integer, height: image["height"].integer, pageCount: 0,
                                    source: source(image["path"].text)))
        }
        for pdf in pdfs where pdf["path"].text.hasPrefix("/") && validSHA(pdf["sha256"].text) {
            result.append(Candidate(kind: .pdf, file: URL(fileURLWithPath: pdf["path"].text), name: pdf["name"].text, sha256: pdf["sha256"].text,
                                    mimeType: "application/pdf", width: 0, height: 0, pageCount: pdf["page_count"].integer, source: source(pdf["path"].text)))
        }
        if let workspace, workspace.hasPrefix("/") {
            for file in files where !file["path"].text.isEmpty && !file["path"].text.hasPrefix("/") && validSHA(file["sha256"].text)
                && !file["path"].text.split(separator: "/").contains("..") {
                let url = URL(fileURLWithPath: workspace).appendingPathComponent(file["path"].text)
                result.append(Candidate(kind: .file, file: url, name: url.lastPathComponent, sha256: file["sha256"].text, mimeType: "text/plain",
                                        width: 0, height: 0, pageCount: 0, source: source(url.path)))
            }
        }
        return result
    }

    /// Copies an attachment whose file still has the recorded SHA-256, or adds this message to
    /// the entry that already holds it. False when the file changed or is gone.
    @discardableResult
    static func capture(_ candidate: Candidate, in folder: URL) throws -> Bool {
        let entryFolder = folder.appendingPathComponent(candidate.sha256, isDirectory: true)
        let existing = try? stored(entryFolder)
        if var entry = existing, entry.sha256 == candidate.sha256, copy(in: entryFolder) != nil {
            if !entry.sources.contains(where: { $0.message_id == candidate.source.messageID.uuidString && $0.path == candidate.source.path }) {
                entry.sources = Array((entry.sources + [StoredSource(candidate.source)]).suffix(maximumSources))
                try save(entry, in: entryFolder)
            }
            return true
        }
        // A new picture or file, or an entry whose copy went missing: copy the original again.
        guard let data = try ChatHistoryFiles.read(candidate.file, limit: limit(candidate.kind) + 1), !data.isEmpty,
              digest(data) == candidate.sha256 else { return false }
        let name = fileName(candidate.name, kind: candidate.kind)
        try ChatHistoryFiles.write(data, to: entryFolder.appendingPathComponent("original", isDirectory: true).appendingPathComponent(name), replace: false)
        let earlier = existing.flatMap { $0.sha256 == candidate.sha256 ? $0.sources : nil } ?? []
        try save(StoredEntry(sha256: candidate.sha256, kind: candidate.kind.rawValue, name: name, mime_type: candidate.mimeType, size_bytes: data.count,
                             width: candidate.width, height: candidate.height, page_count: candidate.pageCount,
                             added_at: existing?.added_at ?? candidate.source.sentAt.timeIntervalSince1970,
                             sources: Array((earlier + [StoredSource(candidate.source)]).suffix(maximumSources))), in: entryFolder)
        return true
    }

    /// Every readable entry, the most recently sent first.
    static func entries(in folder: URL) -> [AttachmentLibraryEntry] {
        guard let names = try? FileManager.default.contentsOfDirectory(atPath: folder.path) else { return [] }
        return names.filter(validSHA).compactMap { name in
            let entryFolder = folder.appendingPathComponent(name, isDirectory: true)
            guard let value = try? stored(entryFolder), value.sha256 == name, copy(in: entryFolder) != nil else { return nil }
            return value.entry
        }.sorted { $0.lastSentAt > $1.lastSentAt }
    }

    /// The library copy of `sha256`, if one is kept.
    static func copy(of sha256: String, in folder: URL) -> URL? {
        guard validSHA(sha256) else { return nil }
        return copy(in: folder.appendingPathComponent(sha256, isDirectory: true))
    }

    /// The entry kept for `sha256`, if any.
    static func entry(_ sha256: String, in folder: URL) -> AttachmentLibraryEntry? {
        guard validSHA(sha256), let value = try? stored(folder.appendingPathComponent(sha256, isDirectory: true)), value.sha256 == sha256 else { return nil }
        return value.entry
    }

    /// The copy's bytes, only while they still have their SHA-256.
    static func data(of sha256: String, kind: AttachmentLibraryEntry.Kind, in folder: URL) -> Data? {
        guard let url = copy(of: sha256, in: folder), let data = try? ChatHistoryFiles.read(url, limit: limit(kind) + 1),
              digest(data) == sha256 else { return nil }
        return data
    }

    static func remove(_ sha256: String, in folder: URL) throws {
        guard validSHA(sha256) else { return }
        let entryFolder = folder.appendingPathComponent(sha256, isDirectory: true)
        var info = stat()
        guard lstat(entryFolder.path, &info) == 0 else { return }
        guard (info.st_mode & S_IFMT) == S_IFDIR else { throw ChatHistoryFormat.invalid() }
        try FileManager.default.removeItem(at: entryFolder)
    }

    static func digest(_ data: Data) -> String { SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined() }

    static func validSHA(_ value: String) -> Bool { value.count == 64 && value.allSatisfy { "0123456789abcdef".contains($0) } }

    /// The original name when it is a plain file name, otherwise a neutral one.
    static func fileName(_ name: String, kind: AttachmentLibraryEntry.Kind) -> String {
        let plain = !name.isEmpty && name.utf8.count <= 240 && !name.hasPrefix(".") && name != "entry.json"
            && !name.contains("/") && !name.unicodeScalars.contains { $0.value < 32 || $0.value == 127 }
        if plain { return name }
        switch kind { case .image: return "picture.png"; case .pdf: return "document.pdf"; case .file: return "file.txt" }
    }

    /// The single regular file in `original/`.
    private static func copy(in entryFolder: URL) -> URL? {
        let original = entryFolder.appendingPathComponent("original", isDirectory: true)
        guard let names = try? FileManager.default.contentsOfDirectory(atPath: original.path) else { return nil }
        let files = names.filter { !$0.hasPrefix(".") }
        guard files.count == 1 else { return nil }
        let url = original.appendingPathComponent(files[0])
        var info = stat()
        guard lstat(url.path, &info) == 0, (info.st_mode & S_IFMT) == S_IFREG else { return nil }
        return url
    }

    private static func stored(_ entryFolder: URL) throws -> StoredEntry? {
        guard let data = try ChatHistoryFiles.read(entryFolder.appendingPathComponent("entry.json"), limit: 256 * 1024) else { return nil }
        let entry = try JSONDecoder().decode(StoredEntry.self, from: data)
        guard entry.schema == schema, validSHA(entry.sha256), AttachmentLibraryEntry.Kind(rawValue: entry.kind) != nil,
              fileName(entry.name, kind: .file) == entry.name, entry.size_bytes > 0,
              entry.size_bytes <= limit(AttachmentLibraryEntry.Kind(rawValue: entry.kind) ?? .file),
              !entry.sources.isEmpty, entry.sources.count <= maximumSources else { throw ChatHistoryFormat.invalid() }
        return entry
    }

    private static func save(_ entry: StoredEntry, in entryFolder: URL) throws {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys, .prettyPrinted]
        try ChatHistoryFiles.write(try encoder.encode(entry), to: entryFolder.appendingPathComponent("entry.json"), replace: true)
    }

    private struct StoredSource: Codable {
        let conversation_id: String
        let message_id: String
        let sent_at: Double
        let path: String
        init(_ source: AttachmentLibraryEntry.Source) {
            conversation_id = source.conversationID.uuidString; message_id = source.messageID.uuidString
            sent_at = source.sentAt.timeIntervalSince1970; path = source.path
        }
    }

    private struct StoredEntry: Codable {
        var schema = AttachmentLibraryStore.schema
        let sha256: String
        let kind: String
        let name: String
        let mime_type: String
        let size_bytes: Int
        let width: Int
        let height: Int
        let page_count: Int
        let added_at: Double
        var sources: [StoredSource]

        var entry: AttachmentLibraryEntry? {
            guard let kind = AttachmentLibraryEntry.Kind(rawValue: kind) else { return nil }
            let sources = sources.compactMap { source -> AttachmentLibraryEntry.Source? in
                guard let conversation = UUID(uuidString: source.conversation_id), let message = UUID(uuidString: source.message_id) else { return nil }
                return .init(conversationID: conversation, messageID: message, sentAt: Date(timeIntervalSince1970: source.sent_at), path: source.path)
            }
            return AttachmentLibraryEntry(sha256: sha256, kind: kind, name: name, mimeType: mime_type, size: size_bytes, width: width, height: height,
                                          pageCount: page_count, addedAt: Date(timeIntervalSince1970: added_at), sources: sources)
        }
    }
}

/// The library as the app shows it. Copies are made one after another off the main thread.
@MainActor
final class AttachmentLibraryModel: ObservableObject {
    @Published private(set) var entries: [AttachmentLibraryEntry] = []
    @Published private(set) var loaded = false
    let folder: URL
    private let state: URL
    private var copying: Task<Void, Never>?

    init(stateDirectory: URL) {
        state = stateDirectory
        folder = AttachmentLibraryStore.folder(stateDirectory)
    }

    func reload() async {
        let folder = folder
        entries = await Task.detached(priority: .userInitiated) { AttachmentLibraryStore.entries(in: folder) }.value
        loaded = true
    }

    /// Keeps copies of what a sent message carried. A file that changed or is gone is skipped;
    /// the message itself is never affected.
    @discardableResult
    func capture(_ candidates: [AttachmentLibraryStore.Candidate]) -> Task<Void, Never>? {
        guard !candidates.isEmpty, (try? PrivateStateAccess.requireAvailable(state)) != nil else { return nil }
        let folder = folder, previous = copying
        let task = Task { [weak self] in
            await previous?.value
            await Task.detached(priority: .utility) {
                for candidate in candidates { _ = try? AttachmentLibraryStore.capture(candidate, in: folder) }
            }.value
            if let self, self.loaded { await self.reload() }
        }
        copying = task
        return task
    }

    func remove(_ entry: AttachmentLibraryEntry) throws {
        try PrivateStateAccess.requireAvailable(state)
        try AttachmentLibraryStore.remove(entry.sha256, in: folder)
        entries.removeAll { $0.sha256 == entry.sha256 }
        AttachmentThumbnails.forget(entry.sha256)
    }

    func copy(of entry: AttachmentLibraryEntry) -> URL? { AttachmentLibraryStore.copy(of: entry.sha256, in: folder) }

    /// The copy's location, only while its bytes still have their SHA-256.
    func verifiedCopy(_ sha256: String, kind: AttachmentLibraryEntry.Kind) -> URL? {
        AttachmentLibraryStore.data(of: sha256, kind: kind, in: folder) == nil ? nil : AttachmentLibraryStore.copy(of: sha256, in: folder)
    }

    /// The picture from its library copy, checked like one read by the bridge.
    func imagePreview(_ sha256: String, conversationID: UUID) -> NativeImagePreview? {
        guard let entry = AttachmentLibraryStore.entry(sha256, in: folder), entry.kind == .image, let copy = copy(of: entry),
              let data = AttachmentLibraryStore.data(of: sha256, kind: .image, in: folder) else { return nil }
        return try? NativeImagePreview(bytes: data, metadata: entry.imageMetadata(copy: copy), conversationID: conversationID)
    }
}

extension AppModel {
    /// What a sent message or task update carried, for the library.
    func libraryCandidates(images: [JSONValue], pdfs: [JSONValue], files: [JSONValue], conversation: Conversation,
                           messageID: UUID, sentAt: Date) -> [AttachmentLibraryStore.Candidate] {
        AttachmentLibraryStore.candidates(images: images, pdfs: pdfs, files: files, workspace: conversation.workspacePath,
                                          conversationID: conversation.id, messageID: messageID, sentAt: sentAt)
    }

    /// Pictures open in a side panel with zoom; PDFs and text files in Quick Look.
    func openLibraryEntry(_ entry: AttachmentLibraryEntry) {
        let conversationID = entry.sources.last?.conversationID ?? selectedID ?? UUID()
        switch entry.kind {
        case .image:
            guard let preview = attachmentLibrary.imagePreview(entry.sha256, conversationID: conversationID) else { return libraryUnavailable() }
            workspacePanel.open(.image(preview))
        case .pdf, .file:
            guard let copy = attachmentLibrary.verifiedCopy(entry.sha256, kind: entry.kind) else { return libraryUnavailable() }
            workspacePanel.open(.document(WorkspaceDocumentPreview(conversationID: conversationID, url: copy, sha256: entry.sha256)))
        }
    }

    /// The message that sent it most recently, in a conversation that still exists.
    func libraryMessage(_ entry: AttachmentLibraryEntry) -> AttachmentLibraryEntry.Source? {
        entry.sources.sorted { $0.sentAt > $1.sentAt }.first { source in
            conversations.first { $0.id == source.conversationID }?.messages.contains { $0.id == source.messageID } == true
        }
    }

    func showLibraryMessage(_ entry: AttachmentLibraryEntry) {
        guard let source = libraryMessage(entry) else { return }
        returnToConversation(source.conversationID, messageID: source.messageID)
    }

    func revealLibraryEntry(_ entry: AttachmentLibraryEntry) {
        guard let copy = attachmentLibrary.copy(of: entry) else { return libraryUnavailable() }
        NSWorkspace.shared.activateFileViewerSelecting([copy])
    }

    /// Attaches the kept copy to the selected conversation's draft. PM's own data is never read as an
    /// attachment, so a temporary copy goes through the usual checks; after Send the library keeps it again.
    func attachLibraryEntry(_ entry: AttachmentLibraryEntry) async {
        guard entry.kind != .file, let id = selectedID, canEditAttachments(for: id),
              let data = AttachmentLibraryStore.data(of: entry.sha256, kind: entry.kind, in: attachmentLibrary.folder) else { return libraryUnavailable() }
        let file = FileManager.default.temporaryDirectory.appendingPathComponent("Proto-Mind Library", isDirectory: true)
            .appendingPathComponent(String(entry.sha256.prefix(16)), isDirectory: true).appendingPathComponent(entry.name)
        do { try ChatHistoryFiles.write(data, to: file, replace: false) } catch { return report(error) }
        section = .chat
        if entry.kind == .image { await attachImageFile(file.path, conversationID: id) }
        else { await previewPDF(file.path, canAttach: true, conversationID: id) }
    }

    private func libraryUnavailable() {
        report(NativeError.message(L10n.text("Копия в библиотеке недоступна или изменилась. Обновите список.")))
    }
}
