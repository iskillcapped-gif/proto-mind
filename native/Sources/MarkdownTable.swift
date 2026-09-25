import SwiftUI

struct MarkdownTable: Equatable {
    enum ColumnAlignment: Equatable { case leading, center, trailing }
    let header: [String]
    let rows: [[String]]
    let alignments: [ColumnAlignment]

    static func parse(_ lines: [String], at index: Int) -> (table: MarkdownTable, end: Int)? {
        guard index + 1 < lines.count, let header = cells(lines[index]), !header.isEmpty, header.count <= 16,
              let separator = cells(lines[index + 1]), separator.count == header.count else { return nil }
        var alignments: [ColumnAlignment] = []
        for cell in separator {
            let stripped = cell.trimmingCharacters(in: CharacterSet(charactersIn: ":"))
            guard stripped.count >= 3, stripped.allSatisfy({ $0 == "-" }),
                  [stripped, ":" + stripped, stripped + ":", ":" + stripped + ":"].contains(cell) else { return nil }
            alignments.append(cell.hasSuffix(":") ? (cell.hasPrefix(":") ? .center : .trailing) : .leading)
        }
        var rows: [[String]] = []
        var end = index + 1
        while end + 1 < lines.count, rows.count < 500,
              let row = cells(lines[end + 1]), row.count <= header.count {
            rows.append(row + Array(repeating: "", count: header.count - row.count))
            end += 1
        }
        return (MarkdownTable(header: header, rows: rows, alignments: alignments), end)
    }

    // Split only outside code spans. Escaped pipes belong to their cell, even
    // inside code; preserving other escapes leaves inline Markdown in charge.
    private static func cells(_ source: String) -> [String]? {
        let characters = Array(source.trimmingCharacters(in: .whitespaces))
        guard !characters.isEmpty else { return nil }
        var result: [String] = [], cell = "", ticks = 0, index = 0
        var separators = 0, leadingPipe = false, trailingPipe = false
        while index < characters.count {
            let char = characters[index]
            if char == "\\", index + 1 < characters.count {
                let next = characters[index + 1]
                cell += next == "|" ? "|" : "\\" + String(next)
                index += 2; trailingPipe = false; continue
            }
            if char == "`" {
                let start = index
                while index < characters.count, characters[index] == "`" { index += 1 }
                let length = index - start
                if ticks == 0 { ticks = length } else if ticks == length { ticks = 0 }
                cell += String(repeating: "`", count: length); trailingPipe = false; continue
            }
            if char == "|", ticks == 0 {
                if index == 0 { leadingPipe = true }
                result.append(cell.trimmingCharacters(in: .whitespaces)); cell = ""
                separators += 1; trailingPipe = true
            } else { cell.append(char); trailingPipe = false }
            index += 1
        }
        guard separators > 0 else { return nil }
        result.append(cell.trimmingCharacters(in: .whitespaces))
        if leadingPipe { result.removeFirst() }
        if trailingPipe { result.removeLast() }
        return result
    }
}

struct MarkdownTableView: View {
    let table: MarkdownTable
    let allowFileLinks: Bool

    private func alignment(_ index: Int) -> Alignment {
        switch table.alignments[index] {
        case .leading: return .leading
        case .center: return .center
        case .trailing: return .trailing
        }
    }

    var body: some View {
        let rows = [table.header] + table.rows
        let widths = table.header.indices.map { column in
            min(280.0, max(80.0, rows.map {
                let plain = String(MarkdownBlock.inline($0[column]).characters)
                return (plain as NSString).size(withAttributes: [.font: NSFont.systemFont(ofSize: NativeTheme.responseSize)]).width
            }.max() ?? 80) + 4)
        }
        ScrollView(.horizontal) {
            VStack(alignment: .leading, spacing: 0) {
                ForEach(Array(rows.enumerated()), id: \.offset) { row, cells in
                    HStack(alignment: .top, spacing: 0) {
                        ForEach(Array(cells.enumerated()), id: \.offset) { column, cell in
                            Text(MarkdownBlock.inline(cell, allowFileLinks: allowFileLinks))
                                .font(row == 0 ? NativeTheme.responseFont.weight(.semibold) : NativeTheme.responseFont)
                                .lineSpacing(4).textSelection(.enabled)
                                .frame(width: widths[column], alignment: alignment(column))
                                .fixedSize(horizontal: false, vertical: true)
                                .padding(.horizontal, 12).padding(.vertical, 10)
                                .accessibilityLabel(row == 0 ? cell : table.header[column] + ": " + cell)
                        }
                    }
                    .background(Color.primary.opacity(row == 0 ? 0.065 : row.isMultiple(of: 2) ? 0.025 : 0))
                    .overlay(alignment: .bottom) { Rectangle().fill(Color.primary.opacity(0.08)).frame(height: 1) }
                }
            }
        }
        .fixedSize(horizontal: false, vertical: true)
        .frame(maxWidth: widths.reduce(0, +) + CGFloat(widths.count) * 24, alignment: .leading)
        .background(Color.primary.opacity(0.02))
        .clipShape(RoundedRectangle(cornerRadius: 9))
        .overlay(RoundedRectangle(cornerRadius: 9).stroke(Color.primary.opacity(0.10)))
    }
}
