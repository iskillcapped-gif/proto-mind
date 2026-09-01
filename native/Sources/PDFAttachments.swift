import AppKit
import CryptoKit
import SwiftUI

struct NativePDFAttachment: Equatable {
    static let maximumBytes = 8 * 1024 * 1024
    static let maximumPages = 300
    static let maximumSelection = 8
    static let pageCharacters = 3000
    static let fields: Set<String> = ["schema", "path", "name", "sha256", "mime_type", "size_bytes", "page_count", "pages"]
    static let pageFields: Set<String> = ["number", "characters", "included_chars", "text_sha256", "truncated"]
    let value: JSONValue
    var path: String { value["path"].text }
    var name: String { value["name"].text }
    var sha256: String { value["sha256"].text }
    var pages: [Int] { value["pages"].items.map { $0["number"].integer } }
    var pageLabel: String { pages.map(String.init).joined(separator: ", ") }

    static func isHash(_ value: JSONValue) -> Bool {
        value.text.count == 64 && value.text.allSatisfy { "0123456789abcdef".contains($0) }
    }

    static func number(_ value: JSONValue, in range: ClosedRange<Int>) -> Bool {
        value == .number(Double(value.integer)) && range.contains(value.integer)
    }

    init(_ value: JSONValue) throws {
        guard case .object(let fields) = value, Set(fields.keys) == Self.fields,
              value["schema"] == .string("proto_mind.native_pdf.v1"),
              value["path"].text.hasPrefix("/"), value["path"].text.unicodeScalars.count <= 4096,
              !value["path"].text.unicodeScalars.contains(where: { $0.value < 32 || $0.value == 127 }),
              !value["path"].text.split(separator: "/").contains(".."),
              URL(fileURLWithPath: value["path"].text).pathExtension.lowercased() == "pdf",
              value["name"] == .string(URL(fileURLWithPath: value["path"].text).lastPathComponent),
              Self.isHash(value["sha256"]), value["mime_type"] == .string("application/pdf"),
              Self.number(value["size_bytes"], in: 1...Self.maximumBytes),
              Self.number(value["page_count"], in: 1...Self.maximumPages),
              case .array(let pages) = value["pages"], (1...Self.maximumSelection).contains(pages.count) else {
            throw NativeError.message("Описание PDF не прошло проверку. Ничего не прикреплено.")
        }
        var previous = 0
        for page in pages {
            guard case .object(let fields) = page, Set(fields.keys) == Self.pageFields,
                  Self.number(page["number"], in: 1...value["page_count"].integer), page["number"].integer > previous,
                  Self.number(page["characters"], in: 0...10_000_000),
                  page["included_chars"] == .number(Double(min(page["characters"].integer, Self.pageCharacters))),
                  page["truncated"] == .bool(page["characters"].integer > Self.pageCharacters),
                  Self.isHash(page["text_sha256"]) else {
                throw NativeError.message("Метаданные страниц PDF не прошли проверку.")
            }
            previous = page["number"].integer
        }
        self.value = value
    }

    static func validate(_ values: [JSONValue]) throws {
        guard values.count <= 1 else { throw NativeError.message("Можно прикрепить один PDF. Сначала уберите предыдущий.") }
        for value in values { _ = try Self(value) }
    }
}

enum NativePDFPageSelection {
    static func parse(_ text: String, total: Int) throws -> [Int] {
        guard text.utf8.count <= 100, (1...NativePDFAttachment.maximumPages).contains(total) else {
            throw NativeError.message("Укажите до 8 страниц, например: 1-3, 7.")
        }
        var pages = Set<Int>()
        for group in text.split(separator: ",", omittingEmptySubsequences: false) {
            let parts = group.split(separator: "-", omittingEmptySubsequences: false).map { $0.trimmingCharacters(in: .whitespaces) }
            let numbers = parts.compactMap { part -> Int? in
                guard !part.isEmpty, part.allSatisfy({ $0.isASCII && $0.isNumber }) else { return nil }
                return Int(part)
            }
            guard (1...2).contains(parts.count), numbers.count == parts.count,
                  numbers.allSatisfy({ (1...total).contains($0) }), let first = numbers.first, let last = numbers.last,
                  last >= first, last - first < NativePDFAttachment.maximumSelection else {
                throw NativeError.message("Выберите существующие страницы PDF, до 8 за раз: 1-3, 7.")
            }
            pages.formUnion(first...last)
            guard pages.count <= NativePDFAttachment.maximumSelection else { throw NativeError.message("Можно выбрать до 8 страниц PDF.") }
        }
        guard !pages.isEmpty else { throw NativeError.message("Укажите хотя бы одну страницу.") }
        return pages.sorted()
    }
}

struct NativePDFPreview: Identifiable {
    let id = UUID()
    let conversationID: UUID
    let workspace: String?
    let source: NativePDFAttachment
    let pages: [JSONValue]
    let canAttach: Bool
    var hasText: Bool { pages.contains { !$0["text"].text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty } }

    init(_ value: JSONValue, conversationID: UUID, workspace: String?, canAttach: Bool) throws {
        guard value["schema"] == .string("proto_mind.native_pdf_preview.v1"),
              value["read_only"] == .bool(true), value["no_execution"] == .bool(true) else {
            throw NativeError.message("Предпросмотр PDF не прошёл проверку.")
        }
        let source = try NativePDFAttachment(value["pdf"])
        guard case .array(let pages) = value["pages"], pages.count == source.pages.count else {
            throw NativeError.message("Предпросмотр не содержит выбранных страниц PDF.")
        }
        for (page, metadata) in zip(pages, source.value["pages"].items) {
            guard case .object(let fields) = page, Set(fields.keys) == NativePDFAttachment.pageFields.union(["text"]),
                  case .string(let text) = page["text"], text.unicodeScalars.count == metadata["included_chars"].integer,
                  NativePDFAttachment.pageFields.allSatisfy({ page[$0] == metadata[$0] }),
                  !text.unicodeScalars.contains(where: { $0.value < 32 && $0 != "\n" && $0 != "\t" || $0.value == 127 }),
                  SHA256.hash(data: Data(text.utf8)).map({ String(format: "%02x", $0) }).joined() == metadata["text_sha256"].text else {
                throw NativeError.message("Текст PDF не совпадает с метаданными и SHA-256 выбранных страниц.")
            }
        }
        self.source = source; self.pages = pages; self.conversationID = conversationID
        self.workspace = workspace; self.canAttach = canAttach
        guard value["has_text"] == .bool(hasText) else { throw NativeError.message("Не удалось проверить текстовый слой PDF.") }
    }
}

struct PDFAttachmentPreviewView: View {
    @ObservedObject var model: AppModel
    @Environment(\.dismiss) private var dismiss
    @State private var preview: NativePDFPreview
    @State private var selection: String
    @State private var error: String?

    init(model: AppModel, preview: NativePDFPreview) {
        self.model = model
        _preview = State(initialValue: preview)
        _selection = State(initialValue: preview.source.pageLabel)
    }

    private var selectionMatches: Bool {
        (try? NativePDFPageSelection.parse(selection, total: preview.source.value["page_count"].integer)) == preview.source.pages
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Label(preview.source.name, systemImage: "doc.richtext").font(.headline).lineLimit(1)
                Spacer()
                Text("PDF · только текст").font(.caption).foregroundStyle(.secondary)
            }
            Text("\(preview.source.value["page_count"].integer) стр. · \(ByteCountFormatter.string(fromByteCount: Int64(preview.source.value["size_bytes"].integer), countStyle: .binary)) · SHA \(preview.source.sha256.prefix(12))")
                .font(.caption).foregroundStyle(.secondary).textSelection(.enabled)
            if preview.canAttach {
                HStack {
                    Text("Страницы:")
                    TextField("1-3, 7", text: $selection).textFieldStyle(.roundedBorder).frame(width: 190)
                        .accessibilityLabel("Страницы PDF").disabled(model.loadingPDFPreview)
                    Button("Прочитать страницы") {
                        Task {
                            do {
                                let pages = try NativePDFPageSelection.parse(selection, total: preview.source.value["page_count"].integer)
                                preview = try await model.reloadPDFPreview(preview, pages: pages)
                                error = nil
                            } catch { self.error = error.localizedDescription }
                        }
                    }.disabled(model.loadingPDFPreview || model.busy)
                    if model.loadingPDFPreview { ProgressView().controlSize(.small) }
                }
            }
            Text("Ниже именно текст, который будет добавлен к сообщению. До 8 страниц, до 3 000 символов на страницу. Картинки, сканы и вёрстка не передаются; OCR пока нет.")
                .font(.callout).foregroundStyle(.secondary)
            ScrollView {
                VStack(alignment: .leading, spacing: 14) {
                    ForEach(Array(preview.pages.enumerated()), id: \.offset) { _, page in
                        VStack(alignment: .leading, spacing: 7) {
                            Text("Страница \(page["number"].integer) · \(page["included_chars"].integer) символов").font(.headline)
                            if page["text"].text.isEmpty {
                                Text("Текстовый слой отсутствует. Возможно, это скан или пустая страница.").foregroundStyle(.orange)
                            } else { Text(page["text"].text).font(NativeTheme.interfaceFont).textSelection(.enabled) }
                            if page["truncated"].flag { Text("Текст страницы обрезан до 3 000 символов. Остальное не отправится.").font(.caption).foregroundStyle(.orange) }
                        }.frame(maxWidth: .infinity, alignment: .leading).padding(14)
                            .background(Color.primary.opacity(0.04), in: RoundedRectangle(cornerRadius: 10))
                    }
                }.frame(maxWidth: .infinity, alignment: .leading)
            }.frame(maxHeight: .infinity)
            Text(preview.source.path).font(.caption).foregroundStyle(.secondary).textSelection(.enabled).lineLimit(2)
            Text(preview.canAttach ? model.pdfDestinationNotice : "Локальное повторное чтение выбранных страниц с проверкой SHA-256. PDF не прикрепляется и не отправляется повторно.")
                .font(.caption).foregroundStyle(.secondary)
            if !preview.hasText { Text("В выбранных страницах нет текста для модели. Выберите другие страницы; сканы пока не поддерживаются.").font(.callout).foregroundStyle(.orange) }
            if let error { Text(error).font(.callout).foregroundStyle(.orange).lineLimit(3) }
            if !selectionMatches { Text("Нажмите «Прочитать страницы», чтобы проверить новый выбор.").font(.caption).foregroundStyle(.orange) }
            HStack {
                Button(preview.canAttach ? "Отмена" : "Готово") { dismiss() }.keyboardShortcut(.cancelAction)
                Spacer()
                if preview.canAttach {
                    Button("Прикрепить выбранный текст") {
                        do { try model.attachPDF(preview); dismiss() }
                        catch { self.error = error.localizedDescription }
                    }.disabled(!preview.hasText || !selectionMatches || model.loadingPDFPreview || model.busy)
                }
            }
        }.padding(22).frame(width: 760, height: 650).buttonStyle(.nativeHover)
    }
}

struct PendingPDFAttachmentsView: View {
    @ObservedObject var model: AppModel
    var body: some View {
        ForEach(Array((model.selected?.pendingPDFs ?? []).enumerated()), id: \.offset) { _, pdf in
            HStack(spacing: 8) {
                Button { Task { await model.previewPDF(pdf["path"].text, expected: pdf, canAttach: false) } } label: {
                    Label("\(pdf["name"].text) · стр. \(pdf["pages"].items.map { String($0["number"].integer) }.joined(separator: ", "))", systemImage: "doc.richtext")
                        .lineLimit(1)
                }.help("Проверить локальный текст выбранных страниц PDF")
                Spacer(minLength: 4)
                Button { model.removePendingPDF() } label: { Image(systemName: "xmark") }
                    .help("Убрать PDF из сообщения").accessibilityLabel("Убрать PDF из сообщения")
            }.font(.caption).padding(10).frame(height: 42)
                .background(Color.primary.opacity(0.05), in: RoundedRectangle(cornerRadius: 10))
                .padding(.horizontal, 12).padding(.top, 10)
        }.buttonStyle(.nativeHover).disabled(model.busy || model.loadingPDFPreview || model.loadingDroppedAttachments)
    }
}
