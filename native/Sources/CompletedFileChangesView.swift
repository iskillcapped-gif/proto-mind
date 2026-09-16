import SwiftUI

struct CompletedFileChanges {
    struct File: Identifiable {
        var id: String { path }
        let path: String
        var additions: Int?
        var deletions: Int?
    }
    var files: [File] = []
    var partial = false
    var additions: Int? { !partial && files.allSatisfy { $0.additions != nil } ? files.reduce(0) { $0 + ($1.additions ?? 0) } : nil }
    var deletions: Int? { !partial && files.allSatisfy { $0.deletions != nil } ? files.reduce(0) { $0 + ($1.deletions ?? 0) } : nil }

    static func project(_ receipt: JSONValue, live: Bool = false) -> Self {
        guard !live, ["completed", "failed", "interrupted"].contains(receipt["status"].text) else { return Self() }
        var result = Self()
        result.partial = receipt["items_truncated"].flag
        var seen: Set<String> = []
        // Last snapshot per tool ID wins; started/completed notifications are one edit.
        var snapshots: [String: JSONValue] = [:]
        var order: [String] = []
        for (index, item) in receipt["items"].items.enumerated() where item["kind"].text == "fileChange" {
            let id = item["id"].text.isEmpty ? "legacy-\(index)" : item["id"].text
            if snapshots[id] == nil { order.append(id) }
            snapshots[id] = item
        }
        for id in order {
            guard let item = snapshots[id], item["status"].text == "completed" else { continue }
            let detailed = !item["file_changes"].isNull
            let changes = detailed ? item["file_changes"].items : item["paths"].items.map { JSONValue.object(["path": $0]) }
            result.partial = result.partial || item["file_changes_truncated"].flag || item["change_count"].integer > changes.count
            for change in changes {
                let path = change["path"].text
                guard !path.isEmpty, !path.contains("\n"), path.count <= 1024 else { result.partial = true; continue }
                let added = count(change["additions"])
                let removed = count(change["deletions"])
                if seen.insert(path).inserted {
                    result.files.append(File(path: path, additions: added, deletions: removed))
                } else if let index = result.files.firstIndex(where: { $0.path == path }) {
                    if let previous = result.files[index].additions, let added { result.files[index].additions = previous + added }
                    else { result.files[index].additions = nil }
                    if let previous = result.files[index].deletions, let removed { result.files[index].deletions = previous + removed }
                    else { result.files[index].deletions = nil }
                }
            }
        }
        return result
    }

    private static func count(_ value: JSONValue) -> Int? {
        guard case .number(let number) = value, number.isFinite, number >= 0, number <= 4_000_000,
              number.rounded() == number else { return nil }
        return Int(number)
    }
}

struct CompletedFileChangesView: View {
    let receipt: JSONValue
    let openLink: (URL) -> Void
    @State private var expanded = false

    var body: some View {
        let summary = CompletedFileChanges.project(receipt)
        if !summary.files.isEmpty {
            VStack(alignment: .leading, spacing: 0) {
                HStack(spacing: 10) {
                    Image(systemName: "doc.badge.gearshape").foregroundStyle(.secondary)
                    Text("\(summary.partial ? L10n.text("Файлы в журнале") : L10n.text("Изменено файлов")): \(summary.files.count)")
                    Spacer(minLength: 4)
                    counts(summary.additions, summary.deletions)
                }.font(.system(size: 13, weight: .medium)).padding(14)
                Divider()
                if expanded {
                    ScrollView { rows(summary.files) }.frame(maxHeight: 270)
                } else { rows(Array(summary.files.prefix(3))) }
                if summary.files.count > 3 {
                    Divider()
                    Button(expanded ? L10n.text("Свернуть список") : L10n.format("Показать ещё \(summary.files.count - 3)")) { expanded.toggle() }
                        .font(.system(size: 12)).buttonStyle(.nativeHover).padding(12)
                }
            }.background(NativeTheme.composer.opacity(0.5), in: RoundedRectangle(cornerRadius: 12))
                .overlay(RoundedRectangle(cornerRadius: 12).stroke(NativeTheme.hairline))
                .help(summary.partial ? L10n.text("Сохранена часть списка. Полные сведения доступны в журнале задачи, если их передал провайдер.") : L10n.text("Строки посчитаны по завершённым правкам этой задачи; повторные правки суммируются. Это не сравнение с Git. У старых записей числа могут отсутствовать."))
        }
    }

    private func rows(_ files: [CompletedFileChanges.File]) -> some View {
        VStack(spacing: 0) {
            ForEach(files) { file in
                HStack(spacing: 8) {
                    Button {
                        let base = URL(fileURLWithPath: receipt["workspace_root"].text, isDirectory: true)
                        openLink(file.path.hasPrefix("/") ? URL(fileURLWithPath: file.path) : base.appendingPathComponent(file.path))
                    } label: {
                        Text(file.path).lineLimit(1).truncationMode(.middle).frame(maxWidth: .infinity, alignment: .leading)
                    }.buttonStyle(.nativeHover).help(file.path)
                    counts(file.additions, file.deletions)
                }.font(.system(size: 12)).padding(.horizontal, 14).padding(.vertical, 10)
            }
        }
    }

    private func counts(_ additions: Int?, _ deletions: Int?) -> some View {
        HStack(spacing: 5) {
            if let additions, let deletions {
                Text("+\(additions)").foregroundStyle(.green)
                Text("−\(deletions)").foregroundStyle(.red)
            }
        }.monospacedDigit().fixedSize()
    }
}
