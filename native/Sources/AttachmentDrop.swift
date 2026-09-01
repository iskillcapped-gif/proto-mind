import AppKit
import SwiftUI
import UniformTypeIdentifiers

enum NativeAttachmentDrop {
    static let maximumItems = 6

    static func localURL(_ url: URL) throws -> URL {
        guard url.isFileURL, url.host == nil || url.host == "" || url.host == "localhost",
              url.user == nil, url.password == nil, url.port == nil, url.query == nil, url.fragment == nil,
              url.path.hasPrefix("/"), url.path.utf8.count <= 16_384,
              !url.path.unicodeScalars.contains(where: { $0.value < 32 || $0.value == 127 }),
              !url.path.split(separator: "/").contains("..") else {
            throw NativeError.message("Перетащите локальные файлы из Finder, не веб-ссылку или обещанный файл.")
        }
        // These are macOS system aliases, not arbitrary symlinks. Readers still
        // validate every file component with no-follow access before returning data.
        var path = url.path
        for alias in ["/var/", "/tmp/"] where path.hasPrefix(alias) { path = "/private" + path; break }
        return URL(fileURLWithPath: path)
    }

    static func decodeURL(_ data: Data) throws -> URL {
        guard data.count <= 16_384, let text = String(data: data, encoding: .utf8),
              let url = URL(string: text) else { throw NativeError.message("Не удалось прочитать адрес перетаскиваемого файла.") }
        return try localURL(url)
    }

    static func selection(_ urls: [URL]) throws -> [URL] {
        guard !urls.isEmpty, urls.count <= maximumItems else {
            throw NativeError.message("За один раз можно выбрать до 3 изображений и 3 текстовых файлов.")
        }
        let result = try urls.map(localURL)
        guard Set(result.map(\.path)).count == result.count else { throw NativeError.message("Один файл выбран несколько раз. Черновик не изменён.") }
        return result
    }

    static func isImage(_ url: URL) -> Bool { ["png", "jpg", "jpeg"].contains(url.pathExtension.lowercased()) }
    static func isPDF(_ url: URL) -> Bool { url.pathExtension.lowercased() == "pdf" }

    static func relativePath(_ url: URL, workspace: String?) throws -> String {
        guard let workspace else {
            throw NativeError.message("Для текстовых файлов сначала выберите рабочую папку диалога. Перетаскивание не меняет её автоматически.")
        }
        let root = try localURL(URL(fileURLWithPath: workspace)).path
        guard url.path.hasPrefix(root + "/") else {
            throw NativeError.message("Текстовые файлы прикрепляются только из рабочей папки диалога. Выберите её вручную; файл не скопирован и не отправлен.")
        }
        return String(url.path.dropFirst(root.count + 1))
    }

    static func pasteboardURLs(_ pasteboard: NSPasteboard) throws -> [URL] {
        guard let items = pasteboard.pasteboardItems, (1...maximumItems).contains(items.count) else {
            throw NativeError.message("Перетащите до 6 локальных файлов.")
        }
        return try selection(items.map { item in
            guard let data = item.data(forType: .fileURL) else { throw NativeError.message("Поддерживаются только готовые локальные файлы, не ссылки или file promises.") }
            return try decodeURL(data)
        })
    }

    static func loadURL(_ provider: NSItemProvider, timeout: TimeInterval = 10) async throws -> URL {
        let data: Data = try await withCheckedThrowingContinuation { continuation in
            let load = AttachmentURLLoad(continuation)
            let progress = provider.loadDataRepresentation(forTypeIdentifier: UTType.fileURL.identifier) { data, _ in
                if let data, data.count <= 16_384 { load.finish(.success(data)) }
                else { load.finish(.failure(NativeError.message("Источник не предоставил локальный адрес файла."))) }
            }
            DispatchQueue.global().asyncAfter(deadline: .now() + timeout) {
                if load.finish(.failure(NativeError.message("Источник слишком долго передаёт файл. Попробуйте перетащить его из Finder ещё раз."))) {
                    progress.cancel()
                }
            }
        }
        return try decodeURL(data)
    }
}

private final class AttachmentURLLoad: @unchecked Sendable {
    private let lock = NSLock()
    private var continuation: CheckedContinuation<Data, Error>?
    init(_ continuation: CheckedContinuation<Data, Error>) { self.continuation = continuation }
    @discardableResult
    func finish(_ result: Result<Data, Error>) -> Bool {
        lock.lock()
        let waiting = continuation
        continuation = nil
        lock.unlock()
        waiting?.resume(with: result)
        return waiting != nil
    }
}

struct NativeDroppedFile {
    let value: JSONValue
    var metadata: JSONValue {
        .object(["path": value["path"], "sha256": value["sha256"],
                 "included_chars": .number(Double(min(6000, value["characters"].integer))),
                 "truncated": .bool(value["characters"].integer > 6000)])
    }
    init(_ value: JSONValue, path: String) throws {
        guard value["read_only"] == .bool(true), value["path"] == .string(path),
              value["sha256"].text.count == 64, value["sha256"].text.allSatisfy({ "0123456789abcdef".contains($0) }),
              value["size_bytes"] == .number(Double(value["size_bytes"].integer)),
              value["characters"] == .number(Double(value["characters"].integer)),
              (0...262_144).contains(value["size_bytes"].integer),
              (0...262_144).contains(value["characters"].integer),
              value["preview"] == .string(value["preview"].text),
              value["preview"].text.unicodeScalars.count == min(12_000, value["characters"].integer) else {
            throw NativeError.message("Предпросмотр текстового файла не прошёл проверку.")
        }
        self.value = value
    }
}

struct NativeAttachmentDropPreview: Identifiable {
    let id = UUID()
    let conversationID: UUID
    let workspace: String?
    let images: [NativeImagePreview]
    let files: [NativeDroppedFile]
    var count: Int { images.count + files.count }

    func merged(with conversation: Conversation) throws -> (images: [JSONValue], files: [JSONValue]) {
        guard (1...NativeAttachmentDrop.maximumItems).contains(count), images.count <= 3, files.count <= 3,
              images.allSatisfy({ $0.canAttach && $0.conversationID == conversationID }),
              conversation.id == conversationID, conversation.workspacePath == workspace, !conversation.archived else {
            throw NativeError.message("Диалог или рабочая папка изменились. Повторите перетаскивание; ничего не прикреплено.")
        }
        let images = conversation.pendingImages.filter { old in !self.images.contains { $0.source.path == old["path"].text } } + self.images.map(\.source.value)
        let files = conversation.pendingFiles.filter { old in !self.files.contains { $0.value["path"] == old["path"] } } + self.files.map(\.metadata)
        try NativeImageAttachment.validate(images)
        guard files.count <= 3 else { throw NativeError.message("В черновике уже есть файлы. Допускается до 3 текстовых вложений.") }
        return (images, files)
    }
}

struct AttachmentDropPreviewView: View {
    @ObservedObject var model: AppModel
    let preview: NativeAttachmentDropPreview
    @Environment(\.dismiss) private var dismiss
    @State private var error: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            Label("Прикрепить файлы · \(preview.count)", systemImage: "paperclip").font(.title3.weight(.semibold))
            Text("Только локальный предпросмотр. Файлы не копируются, перетаскивание ничего не отправляет.").foregroundStyle(.secondary)
            ScrollView {
                VStack(alignment: .leading, spacing: 18) {
                    ForEach(preview.images) { image in
                        HStack(alignment: .top, spacing: 12) {
                            Image(nsImage: image.thumbnail).resizable().scaledToFit().frame(width: 110, height: 85)
                            VStack(alignment: .leading, spacing: 5) {
                                Text(image.source.name).font(.headline)
                                Text("\(image.source.value["width"].integer) × \(image.source.value["height"].integer) · SHA \(image.source.sha256.prefix(12))").font(.caption).foregroundStyle(.secondary)
                                Text(image.source.path).font(.caption).foregroundStyle(.secondary).textSelection(.enabled)
                            }
                        }
                    }
                    ForEach(Array(preview.files.enumerated()), id: \.offset) { _, file in
                        VStack(alignment: .leading, spacing: 6) {
                            Label(file.value["path"].text, systemImage: "doc.text").font(.headline)
                            Text("В сообщение: до \(file.metadata["included_chars"].integer) символов · SHA \(file.value["sha256"].text.prefix(12))").font(.caption).foregroundStyle(.secondary)
                            Text(String(file.value["preview"].text.prefix(6000))).font(NativeTheme.codeFont).textSelection(.enabled)
                                .frame(maxWidth: .infinity, alignment: .leading)
                        }.padding(12).background(Color.primary.opacity(0.04), in: RoundedRectangle(cornerRadius: 10))
                    }
                }.frame(maxWidth: .infinity, alignment: .leading)
            }.frame(maxHeight: .infinity)
            if !preview.images.isEmpty { Text(model.imageDestinationNotice).font(.callout).foregroundStyle(.secondary) }
            Text("Отправка только отдельной кнопкой. Текст получит выбранный провайдер; изображения с исходными метаданными поддерживаются через Codex. Перед отправкой содержимое проверяется по SHA-256.")
                .font(.caption).foregroundStyle(.secondary)
            if let error { Text(error).font(.callout).foregroundStyle(.orange) }
            HStack {
                Button("Отмена") { dismiss() }.keyboardShortcut(.cancelAction)
                Spacer()
                Button("Прикрепить \(preview.count)") {
                    do { try model.attachDrop(preview); dismiss() }
                    catch { self.error = error.localizedDescription }
                }.keyboardShortcut(.defaultAction).disabled(model.busy)
            }
        }.padding(22).frame(width: 720, height: 570).buttonStyle(.nativeHover)
    }
}

struct AttachmentDropTarget: ViewModifier {
    @ObservedObject var model: AppModel
    func body(content: Content) -> some View {
        content
            .contentShape(Rectangle())
            .onDrop(of: [UTType.fileURL.identifier], isTargeted: $model.attachmentDropTargeted) { providers in
                model.receiveAttachmentDrop(providers)
            }
            .overlay {
                if model.attachmentDropTargeted && model.canReceiveAttachments || model.loadingDroppedAttachments {
                    RoundedRectangle(cornerRadius: 20).fill(NativeTheme.canvas.opacity(0.93))
                        .overlay(RoundedRectangle(cornerRadius: 20).strokeBorder(Color.accentColor.opacity(0.65), style: StrokeStyle(lineWidth: 2, dash: [7])))
                        .overlay {
                            VStack(spacing: 12) {
                                Image(systemName: "square.and.arrow.down").font(.system(size: 30))
                                Text(model.loadingDroppedAttachments ? "Проверяю файлы локально…" : "Отпустите для предпросмотра").font(.headline)
                                Text("PDF отдельно, PNG / JPEG или текстовые файлы рабочей папки\nНичего не отправится автоматически")
                                    .font(.callout).foregroundStyle(.secondary).multilineTextAlignment(.center)
                            }.padding(20)
                        }.padding(12).allowsHitTesting(false).accessibilityHidden(true)
                }
            }
    }
}
