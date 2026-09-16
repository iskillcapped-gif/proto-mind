import SwiftUI

struct EvidenceInspectorView: View {
    @ObservedObject var model: AppModel

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 23) {
                HStack {
                    Text(L10n.text("Об ответе")).font(.system(size: 16, weight: .semibold))
                    Spacer()
                    Button { model.showInspector = false } label: { Image(systemName: "xmark").font(.system(size: 11)) }
                        .accessibilityLabel(L10n.text("Закрыть подробности ответа"))
                }
                Text(L10n.text("Источники памяти и сохранённые сведения о выбранном ответе."))
                    .font(.system(size: 12)).foregroundStyle(.secondary).lineSpacing(3)
                if let message = model.evidenceMessage {
                    if let raw = message.autoSkills, let report = try? NativeAutoSkillsReport(raw) { AutoSkillsReportView(report: report) }
                    if let raw = message.knowledgeContext, let report = try? NativeProjectRecallReport(raw["project_recall"]) { ProjectRecallReportView(report: report) }
                    if !message.notices.isEmpty {
                        InspectorSection(title: L10n.text("Примечания к ответу"), icon: "info.circle") {
                            ForEach(Array(message.notices.enumerated()), id: \.offset) { _, notice in Text(notice).foregroundStyle(.secondary).textSelection(.enabled) }
                        }
                    }
                    if let receipt = message.agentRun {
                        DisclosureGroup(L10n.text("Журнал инструментов и технические сведения")) {
                            AgentActivityView(items: receipt["items"].items, receipt: receipt)
                        }
                    }
                    if !message.evidence.isNull {
                    let turn = message.evidence
                    InspectorSection(title: L10n.text("Источник ответа"), icon: "cpu") {
                        detail(L10n.text("Модель"), turn["reasoner_backend"].text)
                        detail(L10n.text("Тип запроса"), turn["observer"]["query_type"].text)
                        detail(L10n.text("Поиск памяти"), turn["observer"]["needs_memory"].flag ? L10n.text("нужен") : L10n.text("не нужен"))
                    }
                    InspectorSection(title: L10n.text("Найденная память"), icon: "tray.2") {
                        let memories = turn["retrieved_memories"].items
                        if memories.isEmpty { Text(L10n.text("Для этого ответа записи не выбраны.")).foregroundStyle(.secondary) }
                        ForEach(Array(memories.enumerated()), id: \.offset) { _, item in
                            VStack(alignment: .leading, spacing: 5) {
                                Text(item["record_id"].text).font(.system(size: 9, design: .monospaced)).foregroundStyle(.secondary)
                                Text(item["content_preview"].text).textSelection(.enabled)
                                Text(item["memory_type"].text).foregroundStyle(.tertiary)
                                Button(L10n.text("Открыть запись")) {
                                    Task { await model.openMemoryEvidence(recordID: item["record_id"].text) }
                                }
                                .buttonStyle(.nativeHover)
                                .disabled(model.busy || item["record_id"].text.isEmpty)
                            }.padding(.vertical, 4)
                        }
                        Text(L10n.text("Передача записи модели не доказывает, что она использована в ответе."))
                            .font(.system(size: 10)).foregroundStyle(.tertiary)
                    }
                    InspectorSection(title: L10n.text("Решение о памяти"), icon: "square.and.arrow.down") {
                        let decision = turn["memory_decision"]
                        detail(L10n.text("Сохранение"), !decision["stored_record_id"].text.isEmpty ? L10n.text("запись подтверждена ядром") : decision["should_store"].flag ? L10n.text("предложено, ID записи отсутствует") : L10n.text("нет"))
                        if !decision["storage_rationale"].text.isEmpty {
                            DisclosureGroup(L10n.text("Почему")) {
                                Text(decision["storage_rationale"].text).foregroundStyle(.secondary).textSelection(.enabled)
                            }
                        }
                        if !turn["memory_decision"]["stored_record_id"].text.isEmpty {
                            Text(turn["memory_decision"]["stored_record_id"].text).font(.system(size: 9, design: .monospaced))
                        }
                    }
                    InspectorSection(title: L10n.text("Проверки"), icon: "checkmark.magnifyingglass") {
                        detail(L10n.text("Согласованность с памятью"), turn["grounding"]["grounding_status"].text)
                        detail(L10n.text("Оценка ядра"), turn["reflection"]["overall_confidence"].text)
                        Text(L10n.text("Локальные проверки не оценивают фактическую точность ответа."))
                            .font(.system(size: 10)).foregroundStyle(.secondary)
                        ForEach(Array((turn["grounding"]["warnings"].items + turn["reflection"]["warnings"].items).enumerated()), id: \.offset) { _, value in
                            Text(value.text).foregroundStyle(.orange).textSelection(.enabled)
                        }
                    }
                    InspectorSection(title: L10n.text("Дополнительный контекст"), icon: "doc.text") {
                        let injection = turn["context_injection"]
                        Text(injection.isNull ? L10n.text("Нет данных об этом запросе") : injection["applied"].flag ? L10n.text("Применён вручную включённый режим") : L10n.text("Не применялся"))
                    }
                    }
                } else {
                    InspectorSection(title: L10n.text("Пока нет сведений"), icon: "text.bubble") {
                        Text(L10n.text("Когда у ответа появятся сохранённые источники и проверки, их можно будет открыть через меню «Подробнее» под сообщением.")).foregroundStyle(.secondary)
                    }
                }
                Divider()
                DisclosureGroup(L10n.text("Технические сведения")) {
                    Text(model.contextLabel).font(.caption).foregroundStyle(.secondary)
                    Text(L10n.text("Показанные проверки не раскрывают внутренние рассуждения модели и не доказывают правильность ответа. Команды приложения выполняются отдельно от модели."))
                        .font(.caption).foregroundStyle(.secondary)
                }
            }.font(.system(size: 12)).padding(20).frame(maxWidth: .infinity, alignment: .leading)
        }.background(NativeTheme.composer.opacity(0.4))
    }

    private func detail(_ label: String, _ value: String) -> some View {
        VStack(alignment: .leading, spacing: 3) {
            Text(label).foregroundStyle(.secondary)
            Text(value.isEmpty ? L10n.text("не указано") : Self.valueLabels[value] ?? value).textSelection(.enabled).help(value)
        }
    }

    private static let valueLabels = [
        "mock": L10n.text("Тестовый режим"), "codex": "Codex", "ollama": "Ollama",
        "new_question": L10n.text("Новый вопрос"), "personal_context": L10n.text("Личный контекст"),
        "project_context": L10n.text("О проекте"), "meta_architecture": L10n.text("Об устройстве приложения"),
        "continuity_followup": L10n.text("Продолжение разговора"), "memory_inventory": L10n.text("Обзор памяти"),
        "decision_request": L10n.text("Выбор решения"), "not_needed": L10n.text("Проверка не требовалась"),
        "grounded": L10n.text("Согласовано"), "partially_grounded": L10n.text("Частично согласовано"),
        "ungrounded": L10n.text("Недостаточно опоры"), "contradicted": L10n.text("Найдено противоречие"),
        "high": L10n.text("Высокая"), "medium": L10n.text("Средняя"), "low": L10n.text("Низкая")
    ]
}

private struct InspectorSection<Content: View>: View {
    let title: String
    let icon: String
    @ViewBuilder var content: () -> Content

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Label(title, systemImage: icon).font(.system(size: 11, weight: .semibold))
            content()
        }.frame(maxWidth: .infinity, alignment: .leading)
    }
}

struct CommandCatalogView: View {
    @ObservedObject var model: AppModel
    @State private var search = ""
    @State private var readOnly = false

    private var commands: [JSONValue] {
        model.bootstrap["commands"].items.filter { item in
            (!readOnly || item["read_only"].flag) && (search.isEmpty ||
                [item["prefix"].text, item["description"].text, item["category"].text].joined(separator: " ").localizedCaseInsensitiveContains(search))
        }
    }
    private var categories: [String] { Set(commands.map { $0["category"].text }).sorted() }

    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            Text(L10n.text("Все возможности. Одно ядро.")).font(.system(size: 25, weight: .medium))
            Text(L10n.text("Каталог из действующего реестра. Выбор только переносит команду в поле ввода; ничего не запускается автоматически."))
                .font(.callout).foregroundStyle(.secondary)
            HStack {
                TextField(L10n.text("Найти команду, категорию или описание"), text: $search).textFieldStyle(.roundedBorder)
                Toggle(L10n.text("Только чтение"), isOn: $readOnly).toggleStyle(.checkbox).font(.caption)
            }
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 20) {
                    ForEach(categories, id: \.self) { category in
                        VStack(alignment: .leading, spacing: 10) {
                            Text(category.uppercased()).font(.system(size: 10, weight: .semibold)).foregroundStyle(.secondary)
                            ForEach(Array(commands.filter { $0["category"].text == category }.enumerated()), id: \.offset) { _, item in
                                HStack(alignment: .top, spacing: 15) {
                                    VStack(alignment: .leading, spacing: 5) {
                                        Text(item["prefix"].text).font(.system(size: 12, weight: .medium, design: .monospaced))
                                        Text(item["description"].text).font(.system(size: 11)).foregroundStyle(.secondary)
                                        Text(item["read_only"].flag ? "read-only · \(item["risk"].text)" : L10n.format("Изменяет: \(item["mutates"].text) · \(item["risk"].text)"))
                                            .font(.system(size: 10)).foregroundStyle(item["read_only"].flag ? Color.secondary : .orange)
                                    }
                                    Spacer(minLength: 10)
                                    Button(L10n.text("Подготовить")) { model.setComposer(item["prefix"].text); model.section = .chat }
                                        .controlSize(.small).disabled(model.busy)
                                }.padding(13).frame(maxWidth: .infinity, alignment: .leading)
                                    .background(Color.primary.opacity(0.025), in: RoundedRectangle(cornerRadius: 9))
                            }
                        }
                    }
                }
            }
        }.padding(28)
    }
}

struct OverviewView: View {
    @ObservedObject var model: AppModel

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 25) {
                Text(L10n.text("Локальное ядро на месте")).font(.system(size: 28, weight: .medium))
                Text(L10n.text("Новый интерфейс не переносит и не заменяет ваши данные. Здесь быстрый обзор, прочитанный без создания записей."))
                    .foregroundStyle(.secondary).font(.callout)
                HStack(spacing: 15) {
                    stat(L10n.text("Команды"), model.bootstrap["registry_count"].integer)
                    stat(L10n.text("Категории"), model.bootstrap["category_count"].integer)
                    stat(L10n.text("Записи памяти"), model.bootstrap["memory_count"].integer)
                }
                GroupBox {
                    VStack(alignment: .leading, spacing: 12) {
                        Label(model.contextLabel, systemImage: "lock.shield")
                        Text(model.bootstrap["project_root"].text).font(.system(size: 11, design: .monospaced)).textSelection(.enabled)
                        Text(L10n.text("Память, цели, задачи, навыки и существующие разрешения обслуживает прежний Python-core."))
                            .font(.callout).foregroundStyle(.secondary)
                    }.padding(8).frame(maxWidth: .infinity, alignment: .leading)
                }
                Button { model.showPersonaInspector = true } label: {
                    HStack(spacing: 13) {
                        Image(systemName: "person.crop.circle.badge.checkmark").font(.title3)
                        VStack(alignment: .leading, spacing: 4) {
                            Text("Persona Inspector").font(.headline)
                            Text(L10n.text("Brother Kernel, Identity и текущий self-model · только read-only preview"))
                                .font(.caption).foregroundStyle(.secondary)
                        }
                        Spacer()
                        Image(systemName: "chevron.right").foregroundStyle(.tertiary)
                    }.padding(15).background(Color.primary.opacity(0.035), in: RoundedRectangle(cornerRadius: 12))
                }.buttonStyle(.nativeHover).disabled(model.busy)
                Text(L10n.text("РУЧНЫЕ ПРОВЕРКИ")).font(.system(size: 10, weight: .semibold)).foregroundStyle(.secondary)
                ForEach(["/proto status", "/proto doctor", "/memory doctor", "/skills list", "/context injection status"], id: \.self) { command in
                    Button { Task { await model.submit(command) } } label: {
                        HStack { Text(command).font(.system(size: 12, design: .monospaced)); Spacer(); Image(systemName: "arrow.up.right") }
                            .padding(12).background(Color.primary.opacity(0.03), in: RoundedRectangle(cornerRadius: 9))
                    }.buttonStyle(.nativeHover).disabled(model.busy)
                }
                ForEach(Array(model.bootstrap["notes"].items.enumerated()), id: \.offset) { _, note in
                    Label(note.text, systemImage: "exclamationmark.circle").foregroundStyle(.orange).font(.caption)
                }
            }.padding(32).frame(maxWidth: 820, alignment: .leading).frame(maxWidth: .infinity)
        }
    }
    private func stat(_ label: String, _ value: Int) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("\(value)").font(.system(size: 29, weight: .medium, design: .rounded))
            Text(label).font(.caption).foregroundStyle(.secondary)
        }.frame(maxWidth: .infinity, alignment: .leading).padding(18)
            .background(Color.primary.opacity(0.035), in: RoundedRectangle(cornerRadius: 12))
    }
}


extension ChatMessage {
    var hasResponseDetails: Bool {
        !evidence.isNull || autoSkills != nil || knowledgeContext != nil || agentRun != nil || !notices.isEmpty
    }
}
