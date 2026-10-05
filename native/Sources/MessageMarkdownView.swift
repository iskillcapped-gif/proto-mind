import SwiftUI

struct MarkdownBlock: Equatable {
    enum Kind: Equatable { case text, heading(Int), code(String), listItem(String, Int), quote, rule, table(MarkdownTable) }
    let kind: Kind
    let content: String

    static func parse(_ source: String) -> [MarkdownBlock] {
        var result: [MarkdownBlock] = []
        var paragraph: [String] = []
        var code: [String] = []
        var fence: String?
        var language = ""
        var paragraphKind: Kind = .text
        var continuationIndent = 0
        func flush() {
            if !paragraph.isEmpty {
                result.append(MarkdownBlock(kind: paragraphKind, content: paragraph.joined(separator: "\n")))
                paragraph = []
            }
            paragraphKind = .text
            continuationIndent = 0
        }
        let lines = source.components(separatedBy: "\n")
        var consumedThrough = -1
        for (index, line) in lines.enumerated() {
            if index <= consumedThrough { continue }
            let trimmed = line.trimmingCharacters(in: .whitespaces)
            if let opened = fence {
                if trimmed.hasPrefix(opened) && trimmed.dropFirst(opened.count).allSatisfy({ $0 == opened.first }) {
                    result.append(MarkdownBlock(kind: .code(language), content: code.joined(separator: "\n")))
                    code = []; fence = nil
                } else { code.append(line) }
            } else if trimmed.hasPrefix("```") || trimmed.hasPrefix("~~~") {
                flush()
                let delimiter = trimmed.first!
                let marker = String(trimmed.prefix(while: { $0 == delimiter }))
                fence = marker
                language = String(trimmed.dropFirst(marker.count).prefix(32)).trimmingCharacters(in: .whitespaces)
            } else if trimmed.isEmpty { flush() }
            else if let parsed = MarkdownTable.parse(lines, at: index) {
                flush()
                result.append(MarkdownBlock(kind: .table(parsed.table), content: lines[index...parsed.end].joined(separator: "\n")))
                consumedThrough = parsed.end
            }
            else {
                let level = trimmed.prefix(while: { $0 == "#" }).count
                let compact = trimmed.filter { !$0.isWhitespace }
                if compact.count >= 3 && ["-", "*", "_"].contains(String(compact.first!)) && Set(compact).count == 1 {
                    flush(); result.append(MarkdownBlock(kind: .rule, content: ""))
                } else if (1...6).contains(level) && trimmed.dropFirst(level).hasPrefix(" ") {
                    flush()
                    result.append(MarkdownBlock(kind: .heading(level), content: String(trimmed.dropFirst(level + 1))))
                } else if let item = listPrefix(line) {
                    flush()
                    paragraphKind = .listItem(item.marker, item.depth)
                    continuationIndent = item.indent
                    paragraph.append(item.text)
                } else if trimmed.hasPrefix(">") {
                    if paragraphKind != .quote { flush() }
                    paragraphKind = .quote
                    paragraph.append(String(trimmed.dropFirst()).trimmingCharacters(in: .whitespaces))
                } else {
                    let indent = line.prefix(while: { $0 == " " || $0 == "\t" }).count
                    if case .listItem = paragraphKind, indent >= continuationIndent {
                        paragraph.append(String(line.dropFirst(continuationIndent)))
                    } else {
                        if paragraphKind != .text { flush() }
                        paragraph.append(line)
                    }
                }
            }
        }
        if fence != nil { result.append(MarkdownBlock(kind: .code(language), content: code.joined(separator: "\n"))) }
        flush()
        return result
    }

    private static func listPrefix(_ line: String) -> (marker: String, depth: Int, indent: Int, text: String)? {
        let spaces = line.prefix(while: { $0 == " " || $0 == "\t" })
        let tail = line.dropFirst(spaces.count)
        let marker: String
        if let first = tail.first, "-*+".contains(first), tail.dropFirst().first?.isWhitespace == true {
            marker = String(first)
        } else {
            let digits = tail.prefix(while: { $0.isASCII && $0.isNumber })
            let suffix = tail.dropFirst(digits.count)
            guard !digits.isEmpty, digits.count <= 9, suffix.first == "." || suffix.first == ")",
                  suffix.dropFirst().first?.isWhitespace == true else { return nil }
            marker = String(digits) + String(suffix.prefix(1))
        }
        let gap = tail.dropFirst(marker.count).prefix(while: { $0.isWhitespace }).count
        let depth = min(6, spaces.reduce(0) { $0 + ($1 == "\t" ? 4 : 1) } / 2)
        return (marker.count == 1 ? "•" : marker, depth, spaces.count + marker.count + gap,
                String(tail.dropFirst(marker.count + gap)))
    }

    static func inline(_ source: String, allowFileLinks: Bool = false, font: Font = NativeTheme.responseFont) -> AttributedString {
        var result = (try? AttributedString(markdown: source, options: .init(interpretedSyntax: .inlineOnlyPreservingWhitespace))) ?? AttributedString(source)
        for run in Array(result.runs) {
            let intent = run.inlinePresentationIntent ?? []
            if intent.contains(.code) { result[run.range].font = NativeTheme.codeFont }
            else if intent.contains(.stronglyEmphasized) {
                // SwiftUI's default Markdown bold is too heavy at reading size.
                // Keep emphasis while using the same family and a quieter weight.
                result[run.range].inlinePresentationIntent = intent.subtracting(.stronglyEmphasized)
                result[run.range].font = intent.contains(.emphasized)
                    ? font.weight(.semibold).italic() : font.weight(.semibold)
            }
            if let link = run.link, !["http", "https"].contains(link.scheme?.lowercased() ?? ""),
               !(allowFileLinks && (link.isFileURL || link.scheme == nil)) {
                result[run.range].link = nil
            } else if run.link != nil {
                result[run.range].underlineStyle = Text.LineStyle(pattern: .solid)
                result[run.range].foregroundColor = NativeTheme.link
            }
        }
        return result
    }
}

struct MessageMarkdownView: View, Equatable {
    let text: String
    let copy: (String) -> Void
    var openLink: ((URL) -> Void)? = nil

    /// A message's actions stay the same while it is shown. Comparing only what is drawn
    /// lets `.equatable()` skip unchanged messages whenever anything else in the app updates;
    /// otherwise every message re-parsed its Markdown on each live update of a running task.
    static func == (lhs: Self, rhs: Self) -> Bool { lhs.text == rhs.text && (lhs.openLink == nil) == (rhs.openLink == nil) }

    var body: some View {
        let blocks = MarkdownBlock.parse(text)
        VStack(alignment: .leading, spacing: 0) {
            ForEach(Array(blocks.enumerated()), id: \.offset) { index, block in
                blockView(block).padding(.top, spacing(before: block, previous: index == 0 ? nil : blocks[index - 1]))
            }
        }.foregroundStyle(NativeTheme.responseText)
            .environment(\.openURL, OpenURLAction { url in
                if let openLink { openLink(url); return .handled }
                return ["http", "https"].contains(url.scheme?.lowercased() ?? "") ? .systemAction : .discarded
            })
    }

    private func spacing(before block: MarkdownBlock, previous: MarkdownBlock?) -> CGFloat {
        guard let previous else { return 0 }
        if case .listItem = block.kind, case .listItem = previous.kind { return 7 }
        if case .heading = block.kind { return 24 }
        return 16
    }

    private func prose(_ text: String) -> some View {
        let attributed = MarkdownBlock.inline(text, allowFileLinks: openLink != nil)
        return Group {
            if #available(macOS 15, *), attributed.runs.contains(where: { $0.link != nil }) {
                LinkAwareProse(text: attributed)
            } else {
                Text(attributed).font(NativeTheme.responseFont).lineSpacing(NativeTheme.responseLineSpacing).textSelection(.enabled)
            }
        }
            .fixedSize(horizontal: false, vertical: true)
            .frame(maxWidth: .infinity, alignment: .leading)
    }

    @ViewBuilder private func blockView(_ block: MarkdownBlock) -> some View {
                switch block.kind {
                case .text:
                    prose(block.content)
                case .heading(let level):
                    let headingFont = Font.system(size: level == 1 ? 19 : level == 2 ? 17 : 15, weight: .semibold)
                    Text(MarkdownBlock.inline(block.content, allowFileLinks: openLink != nil, font: headingFont))
                        .font(headingFont)
                        .lineSpacing(3).fixedSize(horizontal: false, vertical: true).textSelection(.enabled)
                        .frame(maxWidth: .infinity, alignment: .leading)
                case .listItem(let marker, let depth):
                    HStack(alignment: .firstTextBaseline, spacing: 8) {
                        Text(marker).font(NativeTheme.responseFont).frame(minWidth: 14, alignment: .trailing)
                        prose(block.content)
                    }.padding(.leading, 8 + CGFloat(depth) * 20)
                case .quote:
                    prose(block.content).foregroundStyle(.secondary).padding(.leading, 15)
                        .overlay(alignment: .leading) { Rectangle().fill(Color.secondary.opacity(0.3)).frame(width: 2) }
                case .rule:
                    Divider().padding(.vertical, 4)
                case .table(let table):
                    MarkdownTableView(table: table, allowFileLinks: openLink != nil)
                case .code(let language):
                    VStack(alignment: .leading, spacing: 0) {
                        HStack {
                            Text(language.isEmpty ? L10n.text("Код") : language)
                            Spacer()
                            Button { copy(block.content) } label: { Label(L10n.text("Копировать"), systemImage: "doc.on.doc") }.buttonStyle(.nativeHover)
                        }.font(.system(size: 10)).foregroundStyle(.secondary).padding(11)
                        Divider()
                        ScrollView(.horizontal) {
                            Text(block.content).font(NativeTheme.codeFont).padding(13).textSelection(.enabled)
                        }
                    }.background(Color.primary.opacity(0.035), in: RoundedRectangle(cornerRadius: 10))
                        .overlay(RoundedRectangle(cornerRadius: 10).stroke(Color.primary.opacity(0.08)))
                }
    }
}

/// Prose with links. Selectable SwiftUI text keeps its own pointer over a link and a pointer
/// style on the text does not override it, so a text renderer records where each link run is
/// drawn and a clear area above it shows the link pointer and opens the link on click. Keep
/// `.help` off these areas: its tooltip region turns the pointer back into the arrow.
@available(macOS 15, *)
private struct LinkAwareProse: View {
    let text: AttributedString
    @Environment(\.openURL) private var openURL
    @State private var geometry = LinkRunGeometry()
    @State private var links: [LinkRunGeometry.Link] = []

    var body: some View {
        Self.marked(text).font(NativeTheme.responseFont).lineSpacing(NativeTheme.responseLineSpacing)
            .textRenderer(LinkRunRecorder(geometry: geometry))
            // Selection must wrap only the text: around the link areas it keeps its own pointer.
            .textSelection(.enabled)
            .overlay(alignment: .topLeading) {
                ForEach(links) { link in
                    Color.clear.contentShape(Rectangle())
                        .frame(width: link.rect.width, height: link.rect.height)
                        .offset(x: link.rect.minX, y: link.rect.minY)
                        .pointerStyle(.link)
                        .onTapGesture { openURL(link.url) }
                        .accessibilityHidden(true)
                }
            }
            .onAppear { geometry.changed = { links = $0 }; links = geometry.links }
    }

    /// The same runs, with each link marked so the renderer can find it.
    private static func marked(_ value: AttributedString) -> Text {
        value.runs.reduce(Text(verbatim: "")) { text, run in
            let piece = Text(AttributedString(value[run.range]))
            return text + (run.link.map { piece.customAttribute(LinkRun(url: $0)) } ?? piece)
        }
    }
}

private struct LinkRun: TextAttribute { let url: URL }

/// Where the link runs were last drawn, in the text's own coordinates. Drawing publishes a change
/// on the next turn and only when the rects differ, so it settles after one more pass.
private final class LinkRunGeometry: @unchecked Sendable {
    struct Link: Identifiable, Equatable { let id: Int; let rect: CGRect; let url: URL }
    private(set) var links: [Link] = []
    var changed: (([Link]) -> Void)?

    func record(_ next: [Link]) {
        guard next != links else { return }
        links = next
        DispatchQueue.main.async { [weak self] in self?.changed?(next) }
    }
}

@available(macOS 15, *)
private struct LinkRunRecorder: TextRenderer {
    let geometry: LinkRunGeometry
    func draw(layout: Text.Layout, in context: inout GraphicsContext) {
        var found: [LinkRunGeometry.Link] = []
        for line in layout {
            for run in line {
                if let link = run[LinkRun.self] { found.append(.init(id: found.count, rect: run.typographicBounds.rect, url: link.url)) }
            }
            context.draw(line)
        }
        geometry.record(found)
    }
}
