import SwiftUI

struct MarkdownBlock: Equatable {
    enum Kind: Equatable { case text, heading(Int), code(String) }
    let kind: Kind
    let content: String

    static func parse(_ source: String) -> [MarkdownBlock] {
        var result: [MarkdownBlock] = []
        var paragraph: [String] = []
        var code: [String] = []
        var fence: String?
        var language = ""
        func flush() {
            if !paragraph.isEmpty { result.append(MarkdownBlock(kind: .text, content: paragraph.joined(separator: "\n"))); paragraph = [] }
        }
        for line in source.components(separatedBy: "\n") {
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
            else {
                let level = trimmed.prefix(while: { $0 == "#" }).count
                if (1...6).contains(level) && trimmed.dropFirst(level).hasPrefix(" ") {
                    flush()
                    result.append(MarkdownBlock(kind: .heading(level), content: String(trimmed.dropFirst(level + 1))))
                } else { paragraph.append(line) }
            }
        }
        if fence != nil { result.append(MarkdownBlock(kind: .code(language), content: code.joined(separator: "\n"))) }
        flush()
        return result
    }

    static func inline(_ source: String) -> AttributedString {
        var result = (try? AttributedString(markdown: source, options: .init(interpretedSyntax: .inlineOnlyPreservingWhitespace))) ?? AttributedString(source)
        for run in Array(result.runs) {
            if run.inlinePresentationIntent?.contains(.code) == true { result[run.range].font = NativeTheme.codeFont }
            if let link = run.link, !["http", "https"].contains(link.scheme?.lowercased() ?? "") {
                result[run.range].link = nil
            }
        }
        return result
    }
}

struct MessageMarkdownView: View {
    let text: String
    let copy: (String) -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 17) {
            ForEach(Array(MarkdownBlock.parse(text).enumerated()), id: \.offset) { _, block in
                switch block.kind {
                case .text:
                    Text(MarkdownBlock.inline(block.content)).font(NativeTheme.interfaceFont).lineSpacing(5)
                        .textSelection(.enabled)
                case .heading(let level):
                    Text(MarkdownBlock.inline(block.content)).font(.system(size: level < 3 ? 22 : 17, weight: .semibold)).padding(.top, 5)
                        .textSelection(.enabled)
                case .code(let language):
                    VStack(alignment: .leading, spacing: 0) {
                        HStack {
                            Text(language.isEmpty ? "Код" : language)
                            Spacer()
                            Button { copy(block.content) } label: { Label("Копировать", systemImage: "doc.on.doc") }.buttonStyle(.nativeHover)
                        }.font(.system(size: 10)).foregroundStyle(.secondary).padding(11)
                        Divider()
                        ScrollView(.horizontal) {
                            Text(block.content).font(NativeTheme.codeFont).padding(13).textSelection(.enabled)
                        }
                    }.background(Color.primary.opacity(0.035), in: RoundedRectangle(cornerRadius: 10))
                        .overlay(RoundedRectangle(cornerRadius: 10).stroke(Color.primary.opacity(0.08)))
                }
            }
        }.environment(\.openURL, OpenURLAction { url in
                ["http", "https"].contains(url.scheme?.lowercased() ?? "") ? .systemAction : .discarded
            })
    }
}
