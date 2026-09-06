import SwiftUI

enum WorkLogEventGate {
    static func shouldAccept(current: JSONValue, incoming: JSONValue) -> Bool {
        guard incoming["schema"].text == "proto_mind.native_work_log.v1",
              incoming["public_only"].flag,
              !incoming["id"].text.isEmpty else { return false }
        guard !current.isNull, current["id"].text == incoming["id"].text else { return true }
        let previous = current["state_version"].integer
        let next = incoming["state_version"].integer
        if previous > 0 || next > 0 { return next > previous }
        return true // Compatibility with pre-versioned saved/live logs.
    }
}

enum WorkLogPresentation {
    static func duration(_ milliseconds: Int) -> String {
        let seconds = max(0, milliseconds) / 1000
        if seconds < 1 { return "менее секунды" }
        if seconds < 60 { return "\(seconds) с" }
        if seconds < 3600 { return "\(seconds / 60) мин \(seconds % 60) с" }
        return "\(seconds / 3600) ч \((seconds % 3600) / 60) мин"
    }

    static func title(_ log: JSONValue, live: Bool) -> String {
        if live {
            switch log["stage"].text {
            case "connecting": return "Подключаюсь"
            case "answering": return "Пишу ответ"
            default: return "Работаю"
            }
        }
        switch log["status"].text {
        case "completed": return "Ответ получен · \(duration(log["elapsed_ms"].integer))"
        case "interrupted": return "Остановлено · \(duration(log["elapsed_ms"].integer))"
        default: return "Ход не завершён · \(duration(log["elapsed_ms"].integer))"
        }
    }
}

struct WorkTimelineSection: Identifiable {
    let id: String
    var entries: [JSONValue]
    var isTools: Bool { entries.first?["kind"].text == "tool" }
}

enum WorkTimelinePresentation {
    static func sections(_ entries: [JSONValue]) -> [WorkTimelineSection] {
        var result: [WorkTimelineSection] = []
        for (index, entry) in entries.prefix(96).enumerated() {
            if entry["kind"].text == "tool", result.last?.isTools == true {
                result[result.count - 1].entries.append(entry)
            } else {
                result.append(WorkTimelineSection(id: entry["id"].text.isEmpty ? "entry-\(index)" : entry["id"].text, entries: [entry]))
            }
        }
        return result
    }

    static func toolSummary(_ kinds: Set<String>, live: Bool) -> String {
        var parts: [String] = []
        if kinds.contains("fileChange") { parts.append(live ? "Редактирует файлы" : "Редактирование файлов") }
        if kinds.contains("commandExecution") { parts.append(live ? "выполняет команды" : "команды в терминале") }
        if kinds.contains("webSearch") { parts.append(live ? "ищет в интернете" : "поиск в интернете") }
        if kinds.contains("computerUse") { parts.append(live ? "работает с приложениями" : "работа с приложениями") }
        if kinds.contains("imageView") { parts.append(live ? "смотрит изображения" : "просмотр изображений") }
        let text = parts.isEmpty ? "Действия инструментов" : parts.joined(separator: ", ")
        return text.prefix(1).uppercased() + text.dropFirst()
    }

    static func visibleTools(_ items: [JSONValue], live: Bool) -> [JSONValue] {
        items.filter { !live || $0["kind"].text != "fileChange" }
    }
}

struct WorkTimelineView: View {
    let log: JSONValue
    let agentReceipt: JSONValue
    var toolItems: [JSONValue]? = nil
    var live = false
    var startedAt: Date? = nil
    @State private var expanded: Bool? = nil

    private var isExpanded: Bool { expanded ?? live }
    private var entries: [JSONValue] { Array(log["entries"].items.prefix(96)) }

    var body: some View {
        VStack(alignment: .leading, spacing: 20) {
            Button { expanded = !isExpanded } label: {
                HStack(spacing: 8) {
                    if live { WorkingIndicator() }
                    WorkingStatusText(text: WorkLogPresentation.title(log, live: live), active: live)
                    if live, let startedAt {
                        TimelineView(.periodic(from: startedAt, by: 1)) { tick in
                            Text(WorkLogPresentation.duration(Int(max(0, tick.date.timeIntervalSince(startedAt)) * 1000)))
                                .monospacedDigit().foregroundStyle(.tertiary)
                        }
                    }
                    Image(systemName: isExpanded ? "chevron.down" : "chevron.right").font(.system(size: 10, weight: .semibold))
                    Spacer(minLength: 0)
                }.font(.system(size: 12)).foregroundStyle(.secondary).contentShape(Rectangle())
            }.buttonStyle(.nativeHover).accessibilityElement(children: .ignore)
                .accessibilityAddTraits(.isButton)
                .accessibilityLabel("Ход работы: " + WorkLogPresentation.title(log, live: live))
            if isExpanded {
                VStack(alignment: .leading, spacing: 22) {
                    ForEach(WorkTimelinePresentation.sections(entries)) { section in
                        if section.isTools {
                            let ids = Set(section.entries.map { $0["tool_id"].text })
                            let items = (toolItems ?? agentReceipt["items"].items).filter { ids.contains($0["id"].text) }
                            WorkToolGroup(items: items, kinds: Set(section.entries.map { $0["tool_kind"].text }).union(items.map { $0["kind"].text }), live: live)
                        } else if let entry = section.entries.first { row(entry) }
                    }
                    if log["truncated"].flag {
                        Text("Показана часть хода работы").font(.caption).foregroundStyle(.tertiary)
                    }
                }
            } else if live, let latest = entries.last(where: { $0["kind"].text == "commentary" }), !latest["text"].text.isEmpty {
                Text(latest["text"].text).font(NativeTheme.messageFont).foregroundStyle(.secondary).lineLimit(2)
            }
        }
    }

    @ViewBuilder private func row(_ entry: JSONValue) -> some View {
        switch entry["kind"].text {
        case "commentary":
            MessageMarkdownView(text: entry["text"].text, copy: { NSPasteboard.general.clearContents(); NSPasteboard.general.setString($0, forType: .string) })
        case "plan":
            DisclosureGroup("План работы") {
                VStack(alignment: .leading, spacing: 8) {
                    if !entry["text"].text.isEmpty { Text(entry["text"].text) }
                    ForEach(Array(entry["steps"].items.prefix(12).enumerated()), id: \.offset) { _, step in
                        Label(step["step"].text, systemImage: step["status"].text == "completed" ? "checkmark.circle" : step["status"].text == "inProgress" ? "circle.dotted" : "circle")
                    }
                }.padding(.top, 8).textSelection(.enabled)
            }.font(.system(size: 13)).foregroundStyle(.secondary)
        case "context_compaction":
            Label("Сжатие контекста", systemImage: "rectangle.compress.vertical").font(.system(size: 12)).foregroundStyle(.tertiary)
        default: EmptyView()
        }
    }
}

private struct WorkToolGroup: View {
    let items: [JSONValue]
    let kinds: Set<String>
    let live: Bool
    @State private var expanded = false

    private var running: Bool { live && items.contains { ["inProgress", "starting"].contains($0["status"].text) } }
    private var hasErrors: Bool { items.contains { ["failed", "declined", "unknown"].contains($0["status"].text) } }
    private var visible: [JSONValue] { WorkTimelinePresentation.visibleTools(items, live: live) }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Button { expanded.toggle() } label: {
                HStack(spacing: 8) {
                    Image(systemName: hasErrors ? "exclamationmark.circle" : kinds.contains("fileChange") ? "pencil" : "terminal")
                    WorkingStatusText(text: WorkTimelinePresentation.toolSummary(kinds, live: running),
                                      active: running, color: hasErrors ? .orange : .secondary).lineLimit(2)
                    if !visible.isEmpty { Image(systemName: expanded ? "chevron.up" : "chevron.down").font(.system(size: 9)) }
                    if running { WorkingIndicator() }
                    Spacer(minLength: 0)
                }.font(.system(size: 13)).foregroundStyle(hasErrors ? Color.orange : .secondary)
                    .contentShape(Rectangle())
            }.buttonStyle(.nativeHover).disabled(visible.isEmpty)
            if expanded {
                VStack(alignment: .leading, spacing: 12) {
                    ForEach(Array(visible.enumerated()), id: \.offset) { _, item in AgentToolRow(item: item) }
                }.padding(.leading, 17)
            }
        }
    }
}
