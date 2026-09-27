import AppKit
import CryptoKit
import ImageIO
import SwiftUI

struct NativeImageAttachment: Equatable {
    static let maximumCount = 3
    static let maximumBytes = 4 * 1024 * 1024
    static let maximumTotalBytes = 8 * 1024 * 1024
    static let fields: Set<String> = ["schema", "path", "name", "sha256", "mime_type", "size_bytes", "width", "height"]
    let value: JSONValue
    var name: String { value["name"].text }
    var path: String { value["path"].text }
    var sha256: String { value["sha256"].text }

    init(_ value: JSONValue) throws {
        guard case .object(let fields) = value, Set(fields.keys) == Self.fields,
              value["schema"].text == "proto_mind.native_image.v1",
              value["path"].text.hasPrefix("/"), value["path"].text.utf8.count <= 16_384,
              !value["path"].text.unicodeScalars.contains(where: { $0.value < 32 }),
              !value["path"].text.split(separator: "/").contains(".."),
              value["name"].text == URL(fileURLWithPath: value["path"].text).lastPathComponent,
              value["sha256"].text.count == 64,
              value["sha256"].text.allSatisfy({ "0123456789abcdef".contains($0) }),
              ["image/png", "image/jpeg"].contains(value["mime_type"].text),
              value["size_bytes"] == .number(Double(value["size_bytes"].integer)),
              (1...Self.maximumBytes).contains(value["size_bytes"].integer),
              value["width"] == .number(Double(value["width"].integer)),
              value["height"] == .number(Double(value["height"].integer)),
              (1...16_384).contains(value["width"].integer), (1...16_384).contains(value["height"].integer),
              value["width"].integer * value["height"].integer <= 24_000_000 else {
            throw NativeError.message(L10n.text("Описание изображения не прошло проверку. Ничего не прикреплено."))
        }
        self.value = value
    }

    static func validate(_ values: [JSONValue]) throws {
        guard values.count <= maximumCount else { throw NativeError.message(L10n.text("Можно выбрать до трёх изображений.")) }
        let images = try values.map(Self.init)
        guard Set(images.map(\.path)).count == images.count,
              images.reduce(0, { $0 + $1.value["size_bytes"].integer }) <= maximumTotalBytes else {
            throw NativeError.message(L10n.text("Повторяющиеся изображения или превышен общий лимит 8 МиБ."))
        }
    }
}

struct NativeImagePreview: Identifiable {
    let id = UUID()
    let conversationID: UUID
    let source: NativeImageAttachment
    let thumbnail: NSImage
    let canAttach: Bool
    // Main-chat previews expire on navigation; explicitly bound panel previews retain their owner.
    let requiresSelectedConversation: Bool

    init(_ value: JSONValue, conversationID: UUID, canAttach: Bool, requiresSelectedConversation: Bool = true) throws {
        guard value["schema"].text == "proto_mind.native_image_preview.v1",
              value["read_only"] == .bool(true), value["no_execution"] == .bool(true) else {
            throw NativeError.message(L10n.text("Предпросмотр изображения не прошёл проверку."))
        }
        let source = try NativeImageAttachment(value["image"])
        let encoded = value["data_base64"].text
        guard encoded.utf8.count <= (NativeImageAttachment.maximumBytes + 2) / 3 * 4,
              let bytes = Data(base64Encoded: encoded), bytes.count == source.value["size_bytes"].integer,
              SHA256.hash(data: bytes).map({ String(format: "%02x", $0) }).joined() == source.sha256,
              let image = CGImageSourceCreateWithData(bytes as CFData, [kCGImageSourceShouldCache: false] as CFDictionary),
              CGImageSourceGetType(image) as String? == (source.value["mime_type"].text == "image/png" ? "public.png" : "public.jpeg"),
              CGImageSourceGetStatus(image) == .statusComplete, CGImageSourceGetCount(image) == 1,
              let properties = CGImageSourceCopyPropertiesAtIndex(image, 0, nil) as? [CFString: Any],
              (properties[kCGImagePropertyPixelWidth] as? Int) == source.value["width"].integer,
              (properties[kCGImagePropertyPixelHeight] as? Int) == source.value["height"].integer,
              let thumbnail = CGImageSourceCreateThumbnailAtIndex(image, 0, [
                kCGImageSourceCreateThumbnailFromImageAlways: true,
                kCGImageSourceCreateThumbnailWithTransform: true,
                kCGImageSourceThumbnailMaxPixelSize: 1440,
                kCGImageSourceShouldCacheImmediately: true
              ] as CFDictionary) else {
            throw NativeError.message(L10n.text("Изображение не декодируется или его SHA-256/размер изменился. Ничего не отправлено."))
        }
        self.source = source
        self.thumbnail = NSImage(cgImage: thumbnail, size: .zero)
        self.conversationID = conversationID
        self.canAttach = canAttach
        self.requiresSelectedConversation = requiresSelectedConversation
    }
}

struct ImageAttachmentPreviewView: View {
    @ObservedObject var model: AppModel
    let preview: NativeImagePreview
    @WorkspaceDismiss private var dismiss
    @State private var error: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack {
                Label(preview.source.name, systemImage: "photo").font(.headline).lineLimit(1)
                Spacer()
                Text(L10n.text("Локальный просмотр")).font(.caption).foregroundStyle(.secondary)
            }
            Image(nsImage: preview.thumbnail).resizable().scaledToFit()
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .background(Color.primary.opacity(0.04), in: RoundedRectangle(cornerRadius: 12))
                .accessibilityLabel(L10n.format("Локальный предпросмотр \(preview.source.name)"))
            Text("\(preview.source.value["width"].integer) × \(preview.source.value["height"].integer) · \(ByteCountFormatter.string(fromByteCount: Int64(preview.source.value["size_bytes"].integer), countStyle: .binary)) · SHA \(preview.source.sha256.prefix(12))")
                .font(.caption).foregroundStyle(.secondary).textSelection(.enabled)
            Text(preview.source.path).font(.caption).foregroundStyle(.secondary).textSelection(.enabled).lineLimit(2)
            Text(preview.canAttach ? model.imageDestinationNotice(for: preview.conversationID) : L10n.text("Исходный файл проверен по сохранённому SHA-256. Этот просмотр ничего не отправляет и не прикрепляет повторно."))
                .font(.callout).foregroundStyle(.secondary)
            Text(L10n.text("Превью уменьшено для экрана; при отправке передаётся исходный файл, включая встроенные метаданные. Автоматического скрытия личных данных нет."))
                .font(.caption).foregroundStyle(.secondary)
            if let error { Text(error).font(.callout).foregroundStyle(.orange) }
            HStack {
                Text(L10n.text("PNG / JPEG · до 4 МиБ каждый · до 3 файлов / 8 МиБ всего")).font(.caption).foregroundStyle(.tertiary)
                Spacer()
                Button(preview.canAttach ? L10n.text("Отмена") : L10n.text("Готово")) { dismiss() }.keyboardShortcut(.cancelAction)
                if preview.canAttach {
                    Button(L10n.text("Прикрепить к сообщению")) {
                        do { try model.attachImage(preview); dismiss() }
                        catch { self.error = error.localizedDescription }
                    }.keyboardShortcut(.defaultAction).disabled(!model.canEditAttachments(for: preview.conversationID))
                }
            }
        }.padding(22).workspacePageSize(width: 740, height: 620).buttonStyle(.nativeHover)
    }
}

struct PendingImageAttachmentsView: View {
    @ObservedObject var model: AppModel
    var conversationID: UUID? = nil
    @Environment(\.workspacePresentations) private var presentations
    private var context: ConversationComposerContext { ConversationComposerContext(app: model, id: conversationID ?? model.selectedID) }

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            ScrollView(.horizontal) {
                HStack(spacing: 8) {
                    ForEach(Array((context.conversation?.pendingImages ?? []).enumerated()), id: \.offset) { _, image in
                        HStack(spacing: 6) {
                            Button { Task { await model.previewImage(image["path"].text, expectedSHA: image["sha256"].text, canAttach: false, conversationID: context.id, in: presentations) } } label: {
                                HStack(spacing: 8) {
                                    if let thumbnail = model.imageThumbnails[image["sha256"].text] {
                                        Image(nsImage: thumbnail).resizable().scaledToFit().frame(width: 48, height: 40)
                                    } else { Image(systemName: "photo").frame(width: 48, height: 40) }
                                    VStack(alignment: .leading, spacing: 3) {
                                        Text(image["name"].text).lineLimit(1).frame(maxWidth: 150, alignment: .leading)
                                        Text("\(image["width"].integer) × \(image["height"].integer)").foregroundStyle(.secondary)
                                    }.font(.caption)
                                }
                            }.help(L10n.text("Просмотреть локально; файл будет проверен по SHA-256"))
                            Button { model.removeConversationAttachment(image["path"].text, kind: .image, conversationID: context.id) } label: { Image(systemName: "xmark") }
                                .help(L10n.text("Убрать изображение из сообщения")).accessibilityLabel(L10n.format("Убрать изображение \(image["name"].text)"))
                        }.padding(5).background(Color.primary.opacity(0.05), in: RoundedRectangle(cornerRadius: 10))
                    }
                }
            }.frame(height: 60).scrollIndicators(.hidden)
            // Split-view minimum-width probes must not turn this notice into a
            // tall fixedSize column and push the whole window outside its bounds.
            Text(model.imageDestinationNotice(for: context.id)).font(.caption).foregroundStyle(.secondary)
                .lineLimit(3).help(model.imageDestinationNotice(for: context.id))
        }.buttonStyle(.nativeHover).disabled(!context.canEditAttachments || model.loadingImagePreview || model.loadingDroppedAttachments).padding(.horizontal, 12).padding(.top, 10)
    }
}

/// Pictures of attached images for the transcript. A picture is read from the original file only
/// while it still has the size and SHA-256 recorded at attachment, and is kept in memory.
@MainActor
enum AttachmentThumbnails {
    private static var cache: [String: NSImage] = [:]
    private static var order: [String] = []

    static func cached(_ sha: String) -> NSImage? { cache[sha] }

    static func load(_ metadata: JSONValue) async -> NSImage? {
        let sha = metadata["sha256"].text
        if let image = cache[sha] { return image }
        let path = metadata["path"].text, size = metadata["size_bytes"].integer
        let type = metadata["mime_type"].text == "image/png" ? "public.png" : "public.jpeg"
        let picture = await Task.detached(priority: .utility) { () -> CGImage? in
            let url = URL(fileURLWithPath: path)
            guard (1...NativeImageAttachment.maximumBytes).contains(size),
                  let values = try? url.resourceValues(forKeys: [.isRegularFileKey, .isSymbolicLinkKey, .fileSizeKey]),
                  values.isRegularFile == true, values.isSymbolicLink != true, values.fileSize == size,
                  let data = try? Data(contentsOf: url), data.count == size,
                  SHA256.hash(data: data).map({ String(format: "%02x", $0) }).joined() == sha,
                  let source = CGImageSourceCreateWithData(data as CFData, [kCGImageSourceShouldCache: false] as CFDictionary),
                  CGImageSourceGetType(source) as String? == type else { return nil }
            return CGImageSourceCreateThumbnailAtIndex(source, 0, [
                kCGImageSourceCreateThumbnailFromImageAlways: true,
                kCGImageSourceCreateThumbnailWithTransform: true,
                kCGImageSourceThumbnailMaxPixelSize: 640,
                kCGImageSourceShouldCacheImmediately: true,
            ] as CFDictionary)
        }.value
        guard let picture else { return nil }
        let image = NSImage(cgImage: picture, size: .zero)
        cache[sha] = image
        order.append(sha)
        if order.count > 40 { cache[order.removeFirst()] = nil }
        return image
    }
}

/// An attached image shown as a picture in its message; a click opens the checked local preview.
/// Its size comes from the recorded dimensions, so the transcript does not jump while it loads.
struct AttachedImageThumbnail: View {
    let image: JSONValue
    var existing: NSImage? = nil
    var maxSize = CGSize(width: 260, height: 180)
    let open: () -> Void
    @State private var picture: NSImage?

    private var size: CGSize {
        let width = Double(max(1, image["width"].integer)), height = Double(max(1, image["height"].integer))
        let scale = min(1, maxSize.width / width, maxSize.height / height)
        return CGSize(width: max(40, width * scale), height: max(30, height * scale))
    }

    var body: some View {
        Button(action: open) {
            ZStack {
                if let shown = picture ?? existing ?? AttachmentThumbnails.cached(image["sha256"].text) {
                    Image(nsImage: shown).resizable().scaledToFill()
                } else {
                    Color.primary.opacity(0.06)
                    Image(systemName: "photo").font(.system(size: 18)).foregroundStyle(.tertiary)
                }
            }
            .frame(width: size.width, height: size.height)
            .clipShape(RoundedRectangle(cornerRadius: 10))
            .overlay(RoundedRectangle(cornerRadius: 10).strokeBorder(Color.primary.opacity(0.1)))
            .contentShape(RoundedRectangle(cornerRadius: 10))
        }
        .buttonStyle(.plain)
        .help("\(image["name"].text) · \(image["width"].integer) × \(image["height"].integer)")
        .accessibilityLabel(image["name"].text)
        .task(id: image["sha256"].text) {
            if existing == nil, picture == nil, AttachmentThumbnails.cached(image["sha256"].text) == nil { picture = await AttachmentThumbnails.load(image) }
        }
    }
}
