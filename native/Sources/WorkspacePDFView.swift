import AppKit
import CryptoKit
import ImageIO
import SwiftUI
import UniformTypeIdentifiers

struct RenderedPDFPage {
    let preview: NativePDFPreview
    let image: NSImage
    let size: CGSize

    init(_ value: JSONValue, source: NativePDFPreview, page: Int) throws {
        func invalid() -> NativeError { .message(L10n.pick("Не удалось проверить страницу PDF. Откройте документ заново.", "Could not verify the PDF page. Reopen the document.")) }
        guard value["schema"] == .string("proto_mind.native_pdf_page.v1"), value["read_only"] == .bool(true),
              value["no_execution"] == .bool(true), value["page"] == .number(Double(page)),
              NativePDFAttachment.number(value["width"], in: 1...1600), NativePDFAttachment.number(value["height"], in: 1...1600),
              value["png_base64"].text.utf8.count <= 6_990_508,
              let bytes = Data(base64Encoded: value["png_base64"].text), bytes.count <= 5 * 1024 * 1024,
              SHA256.hash(data: bytes).map({ String(format: "%02x", $0) }).joined() == value["png_sha256"].text else { throw invalid() }
        let preview = try NativePDFPreview(value["preview"], conversationID: source.conversationID, workspace: source.workspace, canAttach: source.canAttach)
        guard preview.source.path == source.source.path, preview.source.value["sha256"] == source.source.value["sha256"],
              preview.source.value["size_bytes"] == source.source.value["size_bytes"],
              preview.source.value["page_count"] == source.source.value["page_count"], preview.source.pages == [page],
              let imageSource = CGImageSourceCreateWithData(bytes as CFData, nil),
              CGImageSourceGetType(imageSource) as String? == UTType.png.identifier,
              CGImageSourceGetCount(imageSource) == 1,
              let properties = CGImageSourceCopyPropertiesAtIndex(imageSource, 0, nil) as? [CFString: Any],
              (properties[kCGImagePropertyPixelWidth] as? Int) == value["width"].integer,
              (properties[kCGImagePropertyPixelHeight] as? Int) == value["height"].integer,
              let image = CGImageSourceCreateImageAtIndex(imageSource, 0, nil) else { throw invalid() }
        self.preview = preview
        size = CGSize(width: image.width, height: image.height)
        self.image = NSImage(cgImage: image, size: size)
    }
}

@MainActor
final class PDFPageReader: ObservableObject {
    @Published private(set) var rendered: RenderedPDFPage?
    @Published private(set) var loading = false
    @Published private(set) var error: String?
    private var request = UUID()

    func load(_ source: NativePDFPreview, page: Int, client: BridgeClient) async {
        let token = UUID(); request = token
        loading = true; error = nil; rendered = nil
        defer { if request == token { loading = false } }
        do {
            let value = try await client.request("pdf_render_page", ["path": .string(source.source.path),
                "expected_sha256": source.source.value["sha256"], "page": .number(Double(page))])
            guard !Task.isCancelled, request == token else { return }
            rendered = try RenderedPDFPage(value, source: source, page: page)
        } catch {
            guard !Task.isCancelled, request == token else { return }
            self.error = error.localizedDescription
        }
    }
}

struct WorkspacePDFView: View {
    @ObservedObject var model: AppModel
    let panel: WorkspacePanelModel
    let preview: NativePDFPreview
    let tabID: UUID
    @StateObject private var reader = PDFPageReader()
    @State private var page: Int
    @State private var textMode = false
    @State private var zoom: CGFloat = 1
    @State private var reload = UUID()

    init(model: AppModel, panel: WorkspacePanelModel, preview: NativePDFPreview, tabID: UUID) {
        self.model = model; self.panel = panel; self.preview = preview; self.tabID = tabID
        _page = State(initialValue: preview.source.pages.first ?? 1)
    }

    private var total: Int { preview.source.value["page_count"].integer }
    private var currentConversation: Bool { model.selectedID == preview.conversationID && model.selected?.workspacePath == preview.workspace }

    var body: some View {
        VStack(spacing: 0) {
            HStack(spacing: 10) {
                Text(preview.source.name).font(.callout).lineLimit(1).help(preview.source.path)
                Spacer(minLength: 0)
                if preview.canAttach {
                    Button {
                        guard let selected = reader.rendered?.preview else { return }
                        do { try model.attachPDF(selected) } catch { panel.error = error.localizedDescription }
                    } label: { Image(systemName: "paperclip") }
                        .disabled(!model.canEditMessageAttachments || !currentConversation || reader.rendered?.preview.hasText != true || model.selected?.archived == true)
                        .help(L10n.pick("Прикрепить текст этой страницы", "Attach this page’s text"))
                        .accessibilityLabel(L10n.pick("Прикрепить текст этой страницы", "Attach this page’s text"))
                }
                documentMenu(URL(fileURLWithPath: preview.source.path))
            }.padding(12).workspacePanelHeader()
            Divider().workspacePanelHeader()
            ViewThatFits(in: .horizontal) {
                HStack(spacing: 12) { pageControls; Spacer(minLength: 0); displayControls }
                VStack(spacing: 10) { pageControls; displayControls }
            }.buttonStyle(.nativeHover).font(.system(size: 12)).padding(10).workspacePanelHeader()
            Divider().workspacePanelHeader()
            Group {
                if let rendered = reader.rendered {
                    if textMode {
                        ScrollView {
                            VStack(alignment: .leading, spacing: 12) {
                                Text(rendered.preview.pages[0]["text"].text.isEmpty ? L10n.text("На этой странице нет текстового слоя.") : rendered.preview.pages[0]["text"].text)
                                    .font(NativeTheme.messageFont).lineSpacing(6).textSelection(.enabled)
                                if rendered.preview.pages[0]["truncated"].flag {
                                    Text(L10n.text("Показано начало текста страницы.")).font(.caption).foregroundStyle(.secondary)
                                }
                            }.frame(maxWidth: .infinity, alignment: .leading).padding(24)
                        }
                    } else { pageImage(rendered) }
                } else if let error = reader.error {
                    VStack(spacing: 12) {
                        Image(systemName: "doc.questionmark").font(.title2).foregroundStyle(.secondary)
                        Text(error).font(.callout).textSelection(.enabled)
                        Button(L10n.pick("Повторить", "Retry")) { reload = UUID() }
                    }.padding(24).frame(maxWidth: .infinity, maxHeight: .infinity)
                } else { ProgressView().frame(maxWidth: .infinity, maxHeight: .infinity) }
            }
        }
        .task(id: "\(preview.id)-\(page)-\(reload)") { await reader.load(preview, page: page, client: model.serviceClient) }
    }

    private var pageControls: some View {
        HStack(spacing: 8) {
            Button { page -= 1 } label: { Image(systemName: "chevron.left").frame(width: 24, height: 24) }
                .disabled(page <= 1).accessibilityLabel(L10n.text("Предыдущая страница PDF"))
            Menu {
                ForEach(1...total, id: \.self) { number in
                    Button(String(number)) { page = number }
                }
            } label: { Text("\(page) / \(total)").monospacedDigit() }
                .menuStyle(.borderlessButton).fixedSize().help(L10n.pick("Перейти к странице", "Go to page"))
            Button { page += 1 } label: { Image(systemName: "chevron.right").frame(width: 24, height: 24) }
                .disabled(page >= total).accessibilityLabel(L10n.text("Следующая страница PDF"))
        }
    }

    private var displayControls: some View {
        HStack(spacing: 6) {
            if !textMode {
                Button { zoom = max(1, zoom - 0.5) } label: { Image(systemName: "minus.magnifyingglass") }
                    .disabled(zoom <= 1).help(L10n.pick("Уменьшить", "Zoom out"))
                Button { zoom = 1 } label: { Image(systemName: "arrow.up.left.and.arrow.down.right") }
                    .help(L10n.pick("Вписать страницу", "Fit page"))
                    .accessibilityLabel(L10n.pick("Вписать страницу", "Fit page"))
                Button { zoom = min(4, zoom + 0.5) } label: { Image(systemName: "plus.magnifyingglass") }
                    .disabled(zoom >= 4).help(L10n.pick("Увеличить", "Zoom in"))
            }
            Button { textMode.toggle() } label: {
                Label(textMode ? L10n.pick("Страница", "Page") : L10n.pick("Текст", "Text"), systemImage: textMode ? "doc.richtext" : "text.alignleft")
            }.help(L10n.pick("Переключить страницу и текст", "Switch page and text"))
        }.fixedSize()
    }

    private func pageImage(_ rendered: RenderedPDFPage) -> some View {
        GeometryReader { geometry in
            let scale = max(0.02, min(max(1, geometry.size.width - 32) / rendered.size.width,
                                      max(1, geometry.size.height - 32) / rendered.size.height)) * zoom
            ScrollView([.horizontal, .vertical]) {
                Image(nsImage: rendered.image).resizable().interpolation(.high)
                    .frame(width: rendered.size.width * scale, height: rendered.size.height * scale)
                    .shadow(color: .black.opacity(0.18), radius: 6, y: 2).padding(16)
                    .frame(minWidth: geometry.size.width, minHeight: geometry.size.height)
                    .accessibilityLabel(L10n.pick("Страница PDF", "PDF page") + " \(page) / \(total)")
            }.background(.black.opacity(0.07))
        }
    }
}
