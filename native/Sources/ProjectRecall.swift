import CryptoKit
import SwiftUI

struct NativeProjectRecallReport: Equatable {
    let value: JSONValue
    var state: String { value["state"].text }
    var selectedIDs: [String] { value["selected_ids"].items.map(\.text) }
    var title: String {
        switch state {
        case "selected": return "Память проекта · выбрано: \(selectedIDs.count)"
        case "empty": return "Память проекта · пока нет заметок"
        case "no_match": return "Память проекта · нет точных совпадений"
        default: return "Память проекта · подбор недоступен"
        }
    }

    init(_ value: JSONValue, notes: [JSONValue]? = nil, run: JSONValue? = nil) throws {
        let fields: Set<String> = ["schema", "conversation_id", "workspace", "goal_sha256", "access_mode", "state", "algorithm",
            "source_snapshot_hash", "total_count", "active_count", "matching_count", "selected_ids", "characters", "omitted_count",
            "reason", "read_only", "model_call_performed", "permission_granted", "automatic_learning"]
        guard case .object(let raw) = value, Set(raw.keys) == fields,
              value["schema"] == .string("proto_mind.native_project_recall.v1"),
              value["algorithm"] == .string("local_content_token_overlap_v1"),
              UUID(uuidString: value["conversation_id"].text) != nil, decisionHashValue(value["goal_sha256"].text),
              ["chat", "full_access"].contains(value["access_mode"].text),
              ["selected", "no_match", "empty", "unavailable"].contains(value["state"].text),
              ["total_count", "active_count", "matching_count", "omitted_count"].allSatisfy({ Self.count(value[$0], limit: 200) }),
              Self.count(value["characters"], limit: 6000), case .array(let ids) = value["selected_ids"], ids.count <= 3,
              ids.allSatisfy({ decisionHashValue($0.text) }), Set(ids.map(\.text)).count == ids.count,
              (1...400).contains(value["reason"].text.unicodeScalars.count),
              !value["reason"].text.unicodeScalars.contains(where: { $0.value < 32 }),
              value["read_only"] == .bool(true),
              ["model_call_performed", "permission_granted", "automatic_learning"].allSatisfy({ value[$0] == .bool(false) }),
              ids.count <= value["matching_count"].integer, value["matching_count"].integer <= value["active_count"].integer,
              value["active_count"].integer <= value["total_count"].integer,
              value["omitted_count"].integer == value["matching_count"].integer - ids.count,
              !ids.isEmpty == (value["state"] == .string("selected")), (value["characters"].integer > 0) == !ids.isEmpty,
              value["state"] != .string("empty") || value["active_count"].integer == 0,
              value["state"] != .string("no_match") || (value["active_count"].integer > 0 && value["matching_count"].integer == 0) else { throw Self.error() }
        if !value["workspace"].isNull {
            guard value["workspace"]["path"].text.hasPrefix("/"), value["workspace"]["path"].text.unicodeScalars.count <= 4096,
                  ProjectMemoryScope(conversationID: UUID(), workspace: value["workspace"]["path"].text).matches(value["workspace"]) else { throw Self.error() }
        }
        if value["state"] == .string("unavailable") {
            guard value["source_snapshot_hash"].isNull, value["total_count"].integer == 0 else { throw Self.error() }
        } else {
            guard !value["workspace"].isNull, decisionHashValue(value["source_snapshot_hash"].text) else { throw Self.error() }
        }
        if let notes {
            guard notes.map({ $0["id"] }) == ids, notes.allSatisfy({ $0["workspace"] == value["workspace"] }),
                  notes.reduce(0, { $0 + $1["characters"].integer }) <= value["characters"].integer else { throw Self.error() }
        }
        if let run {
            guard value["conversation_id"] == run["conversation_id"], value["workspace"] == run["workspace"],
                  value["goal_sha256"] == run["input_sha256"], value["access_mode"] == run["access_mode"],
                  run["provider"] == .string("codex") else { throw Self.error() }
        }
        self.value = value
    }

    func matches(conversation: UUID, text: String, workspace: String?, mode: String) -> Bool {
        let hash = SHA256.hash(data: Data(text.utf8)).map { String(format: "%02x", $0) }.joined()
        let sameWorkspace = workspace.map {
            ProjectMemoryScope(conversationID: conversation, workspace: $0).matches(value["workspace"])
        } ?? value["workspace"].isNull
        return UUID(uuidString: value["conversation_id"].text) == conversation && value["goal_sha256"] == .string(hash)
            && value["access_mode"] == .string(mode) && sameWorkspace
    }

    static func error() -> NativeError { .message("Автоподбор памяти не подтвердил задачу, проект или источники. Проверьте контекст и журнал; автоповтора нет.") }
    private static func count(_ value: JSONValue, limit: Double) -> Bool {
        if case .number(let number) = value { return number.isFinite && number.rounded() == number && (0...limit).contains(number) }
        return false
    }
}

struct ProjectRecallMenu: View {
    @ObservedObject var model: AppModel
    var body: some View {
        Menu {
            Toggle("Вспоминать заметки проекта автоматически", isOn: Binding(get: { model.selected?.autoProjectRecallEnabled != false }, set: model.setAutoProjectRecallEnabled))
            Text("Локальный подбор: до 3 заметок, без запроса модели")
            Text("Только явно сохранённые заметки этой папки")
            if !model.pendingProjectNotes.isEmpty { Text("На этот ход приоритет у ручного выбора заметок") }
            Divider()
            Toggle("Предлагать заметки из моих сообщений", isOn: Binding(get: { model.selected?.memorySuggestionsEnabled != false }, set: model.setMemorySuggestionsEnabled))
            Text("Локальные подсказки, запись только после подтверждения")
            Divider()
            Button("Заметки проекта…") { Task { await model.openProjectMemory() } }.disabled(model.selected?.workspacePath == nil)
            Button("Посмотреть контекст…") { model.showContextDesk = true }
        } label: {
            Image(systemName: "brain").font(.system(size: 14))
                .foregroundStyle(model.selected?.autoProjectRecallEnabled != false ? Color.primary : .secondary)
                .frame(width: 24, height: 28)
        }.menuStyle(.borderlessButton).menuIndicator(.hidden).fixedSize().nativeHoverSurface()
            .disabled(model.busy || model.selected?.archived == true)
            .accessibilityLabel("Память проекта · \(model.selected?.autoProjectRecallEnabled != false ? "Авто" : "Выкл")")
            .help("Автоподбор заметок текущей папки. Можно отключить для этого диалога; уже отправленный контекст может оставаться в истории Codex.")
    }
}

struct ProjectRecallReportView: View {
    let report: NativeProjectRecallReport
    var body: some View {
        DisclosureGroup {
            VStack(alignment: .leading, spacing: 7) {
                switch report.state {
                case "selected": Text("Выбраны текущие версии заметок по совпадению значимых слов задачи. Это утверждения оператора, а не независимая проверка фактов.")
                case "empty": Text("В этой папке нет активных явно сохранённых заметок. Старая память не переносилась, новое хранилище не создавалось.")
                case "no_match": Text("Значимые слова задачи не совпали с содержанием заметок. Подбор не угадывает смысл; можно прикрепить нужное вручную.")
                default: Text("Подбор недоступен: нет рабочей папки либо источник/настройки требуют проверки. Обычный запрос идёт без автоматически добавленных заметок.")
                }
                Text(report.value["reason"].text).textSelection(.enabled)
                ForEach(report.selectedIDs, id: \.self) { Text("Источник · \($0.prefix(12))").textSelection(.enabled) }
                Text("Активных: \(report.value["active_count"].integer) · совпадений: \(report.value["matching_count"].integer) · включено символов: \(report.value["characters"].integer)/6000")
                if report.value["omitted_count"].integer > 0 { Text("За пределами лимита: \(report.value["omitted_count"].integer). Заметки не обрезаются.") }
                Text("Только чтение. Нет отдельного запроса модели, записи памяти или новых прав. Старые заметки могут оставаться в истории провайдера; выключатель не удаляет их.")
            }.font(.caption).foregroundStyle(.secondary).padding(.top, 7)
        } label: { Label(report.title, systemImage: "brain") }
            .font(.system(size: 12)).foregroundStyle(.secondary)
    }
}
