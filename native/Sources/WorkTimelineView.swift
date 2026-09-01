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
        case "completed": return "Выполнено за \(duration(log["elapsed_ms"].integer))"
        case "interrupted": return "Остановлено · \(duration(log["elapsed_ms"].integer))"
        default: return "Ход не завершён · \(duration(log["elapsed_ms"].integer))"
        }
    }
}

struct WorkTimelineView: View {
    let log: JSONValue
    let agentReceipt: JSONValue
    var toolItems: [JSONValue]? = nil
    var live = false
    var startedAt: Date? = nil
    @State private var expanded = false

    private var entries: [JSONValue] { Array(log["entries"].items.prefix(96)) }

    var body: some View {
        VStack(alignment: .leading, spacing: 15) {
            Button {
                withAnimation(.easeInOut(duration: 0.16)) { expanded.toggle() }
            } label: {
                HStack(spacing: 8) {
                    if live { ProgressView().controlSize(.mini).scaleEffect(0.75) }
                    Text(WorkLogPresentation.title(log, live: live))
                    if live, let startedAt {
                        TimelineView(.periodic(from: startedAt, by: 1)) { tick in
                            Text(WorkLogPresentation.duration(Int(max(0, tick.date.timeIntervalSince(startedAt)) * 1000)))
                                .monospacedDigit().foregroundStyle(.tertiary)
                        }
                    }
                    Image(systemName: expanded ? "chevron.down" : "chevron.right").font(.system(size: 10, weight: .semibold))
                    Spacer(minLength: 0)
                }.font(.system(size: 13)).foregroundStyle(.secondary).contentShape(Rectangle())
            }.buttonStyle(.nativeHover).accessibilityElement(children: .ignore)
                .accessibilityAddTraits(.isButton)
                .accessibilityLabel("Ход работы: " + WorkLogPresentation.title(log, live: live))
                .help("Публичные комментарии модели и наблюдаемые действия, не внутренние рассуждения")
            if expanded {
                VStack(alignment: .leading, spacing: 20) {
                    if entries.isEmpty {
                        Text(live ? "Ожидаю публичный комментарий или результат. Внутренние рассуждения не отображаются." : "Провайдер не передал публичные этапы работы для этого ответа.")
                            .font(.system(size: 13)).foregroundStyle(.secondary)
                    }
                    ForEach(Array(entries.enumerated()), id: \.offset) { _, entry in
                        row(entry)
                    }
                    if log["truncated"].flag {
                        Label("Показана ограниченная часть хода работы.", systemImage: "info.circle").font(.caption).foregroundStyle(.secondary)
                    }
                    ForEach(Array(agentReceipt["warnings"].items.prefix(8).enumerated()), id: \.offset) { _, warning in
                        Label(warning.text, systemImage: "exclamationmark.triangle")
                            .font(.caption).foregroundStyle(.orange).textSelection(.enabled)
                    }
                    if !live && agentReceipt["execution_may_have_occurred"].flag {
                        Text("Журнал действий не является автоматической проверкой или откатом изменений.")
                            .font(.caption).foregroundStyle(.tertiary)
                    }
                }.padding(.leading, 14).padding(.vertical, 3)
                    .overlay(alignment: .leading) { Rectangle().fill(NativeTheme.hairline).frame(width: 1) }
            } else if live, let latest = entries.last(where: { $0["kind"].text == "commentary" }), !latest["text"].text.isEmpty {
                Text(latest["text"].text).font(NativeTheme.interfaceFont).foregroundStyle(.secondary).lineLimit(2)
            }
        }.onAppear { if live { expanded = true } }
    }

    @ViewBuilder
    private func row(_ entry: JSONValue) -> some View {
        switch entry["kind"].text {
        case "commentary":
            Text(MarkdownBlock.inline(entry["text"].text)).font(NativeTheme.interfaceFont).lineSpacing(5).textSelection(.enabled)
        case "tool":
            if let item = (toolItems ?? agentReceipt["items"].items).first(where: { $0["id"].text == entry["tool_id"].text }) {
                AgentToolRow(item: item)
            } else {
                Label("Действие инструмента · подробности не сохранились", systemImage: "wrench.and.screwdriver")
                    .font(.system(size: 12)).foregroundStyle(.secondary)
            }
        case "plan":
            VStack(alignment: .leading, spacing: 8) {
                Label("План работы", systemImage: "list.bullet.clipboard").font(.system(size: 13, weight: .medium))
                if !entry["text"].text.isEmpty { Text(entry["text"].text).font(.system(size: 13)).foregroundStyle(.secondary) }
                ForEach(Array(entry["steps"].items.prefix(12).enumerated()), id: \.offset) { _, step in
                    Label(step["step"].text, systemImage: step["status"].text == "completed" ? "checkmark.circle" : step["status"].text == "inProgress" ? "circle.dotted" : "circle")
                        .font(.system(size: 13)).foregroundStyle(step["status"].text == "inProgress" ? Color.primary : .secondary)
                }
            }.textSelection(.enabled)
        case "context_compaction":
            Label("Провайдер сжал контекст", systemImage: "rectangle.compress.vertical").font(.system(size: 12)).foregroundStyle(.secondary)
        default:
            EmptyView()
        }
    }
}
