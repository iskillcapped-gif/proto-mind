import SwiftUI

enum NativeTaskCriteria {
    static func validate(_ items: [String]) throws -> [String] {
        let result = items.map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
        guard result.count <= 8, result.allSatisfy({ !$0.isEmpty && $0.unicodeScalars.count <= 300 && $0.rangeOfCharacter(from: .controlCharacters) == nil }),
              Set(result.map { $0.lowercased().split(whereSeparator: \.isWhitespace).joined(separator: " ") }).count == result.count else {
            throw NativeError.message("До 8 разных критериев, каждый в одну строку и не длиннее 300 символов.")
        }
        return result
    }

    static func parse(_ draft: String) throws -> [String] {
        try validate(draft.components(separatedBy: .newlines).map { $0.trimmingCharacters(in: .whitespaces) }.filter { !$0.isEmpty })
    }

    static func validContract(_ value: JSONValue) -> Bool {
        if value.isNull { return true }
        guard value["schema"].text == "proto_mind.native_success_criteria.v1", value["origin"].text == "operator_before_send",
              case .array(let items) = value["items"], !items.isEmpty, value["sha256"].text.count == 64,
              (try? validate(items.map { $0["text"].text })) == items.map({ $0["text"].text }) else { return false }
        return items.enumerated().allSatisfy { $0.element["id"].text == "criterion_\($0.offset + 1)" }
    }
}

enum NativeManualReview {
    static func unavailableReason(_ run: NativeWorkSession) -> String? {
        switch run.state {
        case "running", "preparing":
            return "Запрос ещё выполняется. Приёмка появится после получения завершённого ответа."
        case "not_started":
            return "Запрос не был отправлен, поэтому принимать пока нечего. Можно скрыть уведомление, не меняя запись запуска."
        case "unknown":
            return "Завершённый ответ не подтверждён: запрос прервался или завершился ошибкой. Приёмка недоступна, потому что это ошибочно обозначило бы проверенный результат. Скрытие уведомления ниже не принимает результат и не повторяет запрос."
        default:
            if run.value["status"].text != "completed" || (!run.value["agent_status"].isNull && run.value["agent_status"].text != "completed") {
                return "Состояние запуска не подтверждает завершённый ответ. Обновите журнал перед ручной оценкой."
            }
            return run.value["operator_reviews"].items.count >= 12 ? "Достигнут лимит 12 ручных оценок. Их история сохранена; новые оценки не перезаписывают прежние." : nil
        }
    }

    static func initialDecision(_ run: NativeWorkSession) -> String {
        run.value["success_criteria"]["items"].items.isEmpty ? "needs_work" : "accepted"
    }

    static func label(_ value: String) -> String {
        switch value {
        case "operator_accepted": return "Принято оператором"
        case "operator_needs_work": return "Отмечено оператором: нужна доработка"
        default: return "Операторская приёмка не записана"
        }
    }

    static func validRun(_ run: JSONValue) -> Bool {
        guard NativeTaskCriteria.validContract(run["success_criteria"]) else { return false }
        let reviews = run["operator_reviews"]
        if reviews.isNull || reviews == .array([]) { return run["acceptance"].text == "not_recorded" }
        guard case .array(let rows) = reviews, rows.count <= 12, run["status"].text == "completed",
              rows.allSatisfy({ $0["schema"].text == "proto_mind.native_operator_review.v1" && $0["run_id"] == run["id"]
                  && UUID(uuidString: $0["id"].text) != nil && $0["reviewer"].text == "operator"
                  && $0["no_execution"] == .bool(true) && $0["automatic_verification"] == .bool(false)
                  && $0["receipt_hash"].text.count == 64 && !$0["reviewed_at"].text.isEmpty
                  && ["accepted", "needs_work"].contains($0["selection"]["decision"].text)
                  && $0["selection"]["checks"].items.count == run["success_criteria"]["items"].items.count
                  && $0["selection"]["checks"].items.allSatisfy({ ["met", "not_met", "not_checked"].contains($0.text) }) }) else { return false }
        return run["acceptance"].text == (rows.last?["selection"]["decision"].text == "accepted" ? "operator_accepted" : "operator_needs_work")
    }
}

struct NativeManualReviewPreview: Identifiable {
    let id = UUID()
    let value: JSONValue
    var ready: Bool { value["ready"].flag }
    var selection: JSONValue { value["selection"] }

    init(_ value: JSONValue, run: NativeWorkSession, selection: JSONValue) throws {
        guard value["schema"].text == "proto_mind.native_review_preview.v1",
              value["read_only"] == .bool(true), value["no_execution"] == .bool(true),
              value["run_id"].text == run.id, value["run_fingerprint"] == run.value["fingerprint"],
              value["selection"] == selection, value["criteria"] == run.value["success_criteria"],
              value["preview_fingerprint"].text.count == 64, value["evidence_sha256"].text.count == 64,
              case .array(let observations) = value["observations"], observations.count <= 24,
              case .array(let reasons) = value["reasons"], reasons.count <= 8,
              case .array(let codes) = value["reason_codes"], codes.count == reasons.count,
              reasons.allSatisfy({ !$0.text.isEmpty }), codes.allSatisfy({ !$0.text.isEmpty }),
              value["ready"] == .bool(reasons.isEmpty) else {
            throw NativeError.message("Состав ручной оценки изменился или не прошёл проверку. Ничего не записано.")
        }
        self.value = value
    }

    var reasons: [String] {
        value["reason_codes"].items.map {
            switch $0.text {
            case "incomplete_run": return "Приёмка доступна только для завершённого ответа. Неизвестный или прерванный исход не превращается в успех."
            case "history_limit": return "Достигнут лимит 12 ручных оценок. Старые записи не удаляются и не перезаписываются."
            case "no_criteria": return "До этого запуска критерии не задавались. Укажите их для новой задачи: мы не дописываем условия задним числом."
            case "unchecked_criteria": return "Для принятия лично отметьте каждый критерий как выполненный."
            case "workspace_changed": return "Исходная рабочая папка недоступна или изменилась. Сначала перепроверьте привязку."
            case "artifacts_changed": return "Файлы изменились, недоступны или не имеют сохранённого SHA. Проверьте результаты; приёмка не записана."
            case "explain_rework": return "Опишите, что осталось доработать, либо отметьте невыполненный или непроверенный критерий."
            default: return "Нужна повторная проверка ручной оценки; запись не выполнена."
            }
        }
    }
}

struct TaskCriteriaView: View {
    @ObservedObject var model: AppModel
    private let conversationID: UUID?
    @State private var draft: String
    @State private var error: String?

    init(model: AppModel) {
        self.model = model; conversationID = model.selectedID
        _draft = State(initialValue: (model.selected?.pendingCriteria ?? []).joined(separator: "\n"))
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            Label("Готово, когда…", systemImage: "checklist").font(.title2.weight(.semibold))
            Text("Задайте критерии для следующего обычного сообщения. Один пункт на строку, максимум 8.")
                .foregroundStyle(.secondary)
            TextEditor(text: $draft).font(NativeTheme.interfaceFont).padding(10)
                .background(Color.primary.opacity(0.035), in: RoundedRectangle(cornerRadius: 10))
                .frame(minHeight: 170).accessibilityLabel("Критерии следующей задачи")
            if let error { Text(error).foregroundStyle(.orange) }
            Text("Критерии сохраняются только в личном черновике. При отправке они попадут выбранной модели и в журнал запуска. Это не разрешение на инструменты и не автоматическая проверка. Операторские команды их пропускают.")
                .font(.callout).foregroundStyle(.secondary)
            HStack {
                Button("Отмена") { model.showTaskCriteria = false }.keyboardShortcut(.cancelAction)
                Spacer()
                Button("Сохранить критерии") {
                    do {
                        guard let conversationID else { throw NativeError.message("Откройте диалог.") }
                        try model.setPendingCriteria(NativeTaskCriteria.parse(draft), conversationID: conversationID)
                        model.showTaskCriteria = false
                    } catch { self.error = error.localizedDescription }
                }.disabled(model.busy).keyboardShortcut(.return, modifiers: .command)
            }
        }.padding(26).frame(width: 620, height: 440).background(NativeTheme.canvas)
            .font(NativeTheme.interfaceFont).buttonStyle(.nativeHover)
    }
}

struct TaskReviewView: View {
    @ObservedObject var model: AppModel
    let run: NativeWorkSession
    @State private var checks: [String]
    @State private var decision = "accepted"
    @State private var note = ""
    @State private var editing: Bool
    @State private var loading = false
    @State private var error: String?
    @State private var lastPreview: NativeManualReviewPreview?
    @State private var confirmation: NativeManualReviewPreview?

    init(model: AppModel, run: NativeWorkSession) {
        self.model = model; self.run = run
        _checks = State(initialValue: Array(repeating: "not_checked", count: run.value["success_criteria"]["items"].items.count))
        _decision = State(initialValue: NativeManualReview.initialDecision(run))
        _editing = State(initialValue: run.value["operator_reviews"].items.isEmpty)
    }

    private var criteria: [JSONValue] { run.value["success_criteria"]["items"].items }
    private var reviews: [JSONValue] { run.value["operator_reviews"].items }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                Label("Ручная приёмка", systemImage: "person.crop.circle.badge.checkmark").font(.title3.weight(.semibold))
                Text(NativeManualReview.label(run.value["acceptance"].text)).font(.headline)
                Text("\(run.title). Автоматическая проверка достижения цели не выполнялась. Оценка ниже принадлежит оператору, а не модели.")
                    .foregroundStyle(.secondary)
                Text(run.value["input_preview"].text).textSelection(.enabled)
                if !reviews.isEmpty { reviewHistory }
                if let reason = NativeManualReview.unavailableReason(run) {
                    VStack(alignment: .leading, spacing: 12) {
                        Label("Почему приёмка недоступна", systemImage: "info.circle").font(.headline)
                        Text(reason).textSelection(.enabled)
                        WorkSessionNoticeControls(model: model, run: run)
                    }.padding(16).background(Color.orange.opacity(0.06), in: RoundedRectangle(cornerRadius: 12))
                } else if editing { editor }
                else if reviews.count < 12 {
                    Button("Пересмотреть вручную…") { editing = true }
                        .help("Предыдущая оценка сохранится в истории; новый запрос модели не запускается")
                }
                if let error { Text(error).foregroundStyle(.orange).textSelection(.enabled) }
                if let lastPreview, !lastPreview.ready {
                    ForEach(Array(lastPreview.reasons.enumerated()), id: \.offset) { _, reason in
                        Label(reason, systemImage: "exclamationmark.triangle").foregroundStyle(.orange)
                    }
                }
                Button("Обновить журнал") { Task { await model.refreshWorkSessions() } }.disabled(model.busy || loading)
                Button("Вернуться в диалог") { model.showWorkSessions = false; model.section = .chat }
                Text("При сохранении перечитываются запись запуска и наблюдаемые файлы. Изменившийся результат нельзя принять как прежний. Записывается только ручная оценка в личном журнале; команды не выполняются, файлы проекта и память не меняются.")
                    .font(.caption).foregroundStyle(.secondary)
            }.padding(22).frame(maxWidth: .infinity, alignment: .leading)
        }
        .sheet(item: $confirmation) { preview in confirmationSheet(preview) }
        .onChange(of: checks) { lastPreview = nil; error = nil }
        .onChange(of: decision) { lastPreview = nil; error = nil }
        .onChange(of: note) { lastPreview = nil; error = nil }
    }

    private var editor: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text("Критерии, заданные до отправки").font(.headline)
            if criteria.isEmpty {
                Text("Критерии не задавались. Можно записать необходимость доработки с пояснением, но не выдумывать выполненные условия задним числом.").foregroundStyle(.secondary)
            }
            ForEach(Array(criteria.enumerated()), id: \.offset) { index, item in
                VStack(alignment: .leading, spacing: 8) {
                    Text("\(index + 1). \(item["text"].text)").textSelection(.enabled)
                    Picker("Критерий \(index + 1)", selection: $checks[index]) {
                        Text("Не проверено").tag("not_checked")
                        Text("Выполнено").tag("met")
                        Text("Не выполнено").tag("not_met")
                    }.pickerStyle(.segmented).labelsHidden()
                }.padding(12).background(Color.primary.opacity(0.035), in: RoundedRectangle(cornerRadius: 10))
            }
            if !criteria.isEmpty {
                Picker("Моё решение", selection: $decision) {
                    Text("Принять результат").tag("accepted")
                    Text("Нужна доработка").tag("needs_work")
                }.pickerStyle(.segmented)
            } else {
                Label("Нужна доработка: опишите её в комментарии", systemImage: "square.and.pencil")
            }
            Text("Комментарий · до 1 000 символов").font(.caption).foregroundStyle(.secondary)
            TextEditor(text: $note).frame(height: 75).font(NativeTheme.interfaceFont)
                .accessibilityLabel("Комментарий к ручной приёмке")
            Button {
                Task {
                    loading = true; error = nil; lastPreview = nil
                    defer { loading = false }
                    do {
                        let selection: JSONValue = .object(["decision": .string(decision), "checks": .array(checks.map(JSONValue.string)),
                                                           "note": .string(note.trimmingCharacters(in: .whitespacesAndNewlines))])
                        let preview = try await model.previewManualReview(run, selection: selection)
                        lastPreview = preview
                        if preview.ready { confirmation = preview }
                    } catch { self.error = error.localizedDescription }
                }
            } label: { Label(loading ? "Проверяю запись и файлы…" : "Проверить перед записью…", systemImage: "checkmark.shield") }
        }.disabled(model.busy || loading || run.state != "completed" || reviews.count >= 12)
    }

    private var reviewHistory: some View {
        DisclosureGroup("История ручных оценок · \(reviews.count)/12") {
            ForEach(Array(reviews.enumerated().reversed()), id: \.offset) { _, item in
                VStack(alignment: .leading, spacing: 7) {
                    Text(item["selection"]["decision"].text == "accepted" ? "Принято оператором" : "Нужна доработка").fontWeight(.medium)
                    Text(item["reviewed_at"].text).font(.caption).foregroundStyle(.secondary)
                    if !item["selection"]["note"].text.isEmpty { Text(item["selection"]["note"].text).textSelection(.enabled) }
                    Text("\(item["selection"]["checks"].items.filter { $0.text == "met" }.count)/\(criteria.count) отмечено выполненными · receipt \(item["receipt_hash"].text.prefix(12))")
                        .font(.caption.monospaced()).foregroundStyle(.secondary)
                    if !criteria.isEmpty {
                        DisclosureGroup("Оценка по пунктам") {
                            ForEach(Array(criteria.enumerated()), id: \.offset) { index, criterion in
                                let check = item["selection"]["checks"].items[index].text
                                Text("\(index + 1). \(criterion["text"].text) · \(check == "met" ? "Выполнено" : check == "not_met" ? "Не выполнено" : "Не проверено")")
                                    .frame(maxWidth: .infinity, alignment: .leading).padding(.vertical, 3).textSelection(.enabled)
                            }
                        }.font(.callout)
                    }
                }.padding(.vertical, 8)
            }
            Text("Это историческая оценка на момент записи, не обещание, что файлы с тех пор не менялись. Хеши не являются подписью личности оператора.")
                .font(.caption).foregroundStyle(.secondary)
        }
    }

    private func confirmationSheet(_ preview: NativeManualReviewPreview) -> some View {
        VStack(alignment: .leading, spacing: 18) {
            Label("Записать вашу оценку?", systemImage: "hand.raised").font(.title2.weight(.semibold))
            Text(preview.selection["decision"].text == "accepted" ? "Вы лично принимаете результат по заданным критериям." : "Вы отмечаете, что результат требует доработки.")
            Text("Отмечено выполненными: \(preview.selection["checks"].items.filter { $0.text == "met" }.count)/\(criteria.count). Наблюдаемых файлов: \(preview.value["observations"].items.count).")
            ScrollView {
                VStack(alignment: .leading, spacing: 12) {
                    ForEach(Array(criteria.enumerated()), id: \.offset) { index, item in
                        let check = preview.selection["checks"].items[index].text
                        VStack(alignment: .leading, spacing: 4) {
                            Text("\(index + 1). \(item["text"].text)")
                            Label(check == "met" ? "Выполнено" : check == "not_met" ? "Не выполнено" : "Не проверено",
                                  systemImage: check == "met" ? "checkmark.circle" : "questionmark.circle")
                                .font(.caption).foregroundStyle(.secondary)
                        }
                    }
                    if !preview.selection["note"].text.isEmpty {
                        Divider()
                        Text(preview.selection["note"].text)
                    }
                }.frame(maxWidth: .infinity, alignment: .leading).textSelection(.enabled)
            }.frame(maxHeight: 220)
            Text("Только запись в личном журнале. Ни запуска, ни исправления файлов, ни новой памяти или разрешений. Предыдущие оценки сохраняются.")
                .foregroundStyle(.secondary)
            HStack {
                Button("Отмена") { confirmation = nil }.keyboardShortcut(.cancelAction)
                Spacer()
                Button("Записать мою оценку") {
                    Task {
                        loading = true
                        defer { loading = false; confirmation = nil }
                        do { _ = try await model.saveManualReview(run, preview: preview) }
                        catch {
                            self.error = "Не удалось подтвердить запись оценки. Обновите журнал перед повтором: при ошибке связи оценка могла сохраниться.\n\n" + error.localizedDescription
                        }
                    }
                }.disabled(model.busy || loading)
            }
        }.padding(26).frame(width: 560).background(NativeTheme.canvas)
            .font(NativeTheme.interfaceFont).buttonStyle(.nativeHover)
    }
}
