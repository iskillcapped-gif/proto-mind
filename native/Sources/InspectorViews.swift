import SwiftUI

struct EvidenceInspectorView: View {
    @ObservedObject var model: AppModel

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 23) {
                HStack {
                    Text("Об ответе").font(.system(size: 16, weight: .semibold))
                    Spacer()
                    Button { model.showInspector = false } label: { Image(systemName: "xmark").font(.system(size: 11)) }
                        .accessibilityLabel("Закрыть подробности ответа")
                }
                Text("Источники памяти и сохранённые сведения о выбранном ответе.")
                    .font(.system(size: 12)).foregroundStyle(.secondary).lineSpacing(3)
                if let message = model.evidenceMessage {
                    if let raw = message.autoSkills, let report = try? NativeAutoSkillsReport(raw) { AutoSkillsReportView(report: report) }
                    if let raw = message.knowledgeContext, let report = try? NativeProjectRecallReport(raw["project_recall"]) { ProjectRecallReportView(report: report) }
                    if !message.notices.isEmpty {
                        InspectorSection(title: "Примечания к ответу", icon: "info.circle") {
                            ForEach(Array(message.notices.enumerated()), id: \.offset) { _, notice in Text(notice).foregroundStyle(.secondary).textSelection(.enabled) }
                        }
                    }
                    if let receipt = message.agentRun {
                        DisclosureGroup("Журнал инструментов и технические сведения") {
                            AgentActivityView(items: receipt["items"].items, receipt: receipt)
                        }
                    }
                    if !message.evidence.isNull {
                    let turn = message.evidence
                    InspectorSection(title: "Источник ответа", icon: "cpu") {
                        detail("Модель", turn["reasoner_backend"].text)
                        detail("Тип запроса", turn["observer"]["query_type"].text)
                        detail("Поиск памяти", turn["observer"]["needs_memory"].flag ? "нужен" : "не нужен")
                    }
                    InspectorSection(title: "Найденная память", icon: "tray.2") {
                        let memories = turn["retrieved_memories"].items
                        if memories.isEmpty { Text("Для этого ответа записи не выбраны.").foregroundStyle(.secondary) }
                        ForEach(Array(memories.enumerated()), id: \.offset) { _, item in
                            VStack(alignment: .leading, spacing: 5) {
                                Text(item["record_id"].text).font(.system(size: 9, design: .monospaced)).foregroundStyle(.secondary)
                                Text(item["content_preview"].text).textSelection(.enabled)
                                Text(item["memory_type"].text).foregroundStyle(.tertiary)
                                Button("Открыть запись") {
                                    Task { await model.openMemoryEvidence(recordID: item["record_id"].text) }
                                }
                                .buttonStyle(.nativeHover)
                                .disabled(model.busy || item["record_id"].text.isEmpty)
                            }.padding(.vertical, 4)
                        }
                        Text("Передача записи модели не доказывает, что она использована в ответе.")
                            .font(.system(size: 10)).foregroundStyle(.tertiary)
                    }
                    InspectorSection(title: "Решение о памяти", icon: "square.and.arrow.down") {
                        let decision = turn["memory_decision"]
                        detail("Сохранение", !decision["stored_record_id"].text.isEmpty ? "запись подтверждена ядром" : decision["should_store"].flag ? "предложено, ID записи отсутствует" : "нет")
                        if !decision["storage_rationale"].text.isEmpty {
                            DisclosureGroup("Почему") {
                                Text(decision["storage_rationale"].text).foregroundStyle(.secondary).textSelection(.enabled)
                            }
                        }
                        if !turn["memory_decision"]["stored_record_id"].text.isEmpty {
                            Text(turn["memory_decision"]["stored_record_id"].text).font(.system(size: 9, design: .monospaced))
                        }
                    }
                    InspectorSection(title: "Проверки", icon: "checkmark.magnifyingglass") {
                        detail("Согласованность с памятью", turn["grounding"]["grounding_status"].text)
                        detail("Оценка ядра", turn["reflection"]["overall_confidence"].text)
                        Text("Локальные проверки не оценивают фактическую точность ответа.")
                            .font(.system(size: 10)).foregroundStyle(.secondary)
                        ForEach(Array((turn["grounding"]["warnings"].items + turn["reflection"]["warnings"].items).enumerated()), id: \.offset) { _, value in
                            Text(value.text).foregroundStyle(.orange).textSelection(.enabled)
                        }
                    }
                    InspectorSection(title: "Дополнительный контекст", icon: "doc.text") {
                        let injection = turn["context_injection"]
                        Text(injection.isNull ? "Нет данных об этом запросе" : injection["applied"].flag ? "Применён вручную включённый режим" : "Не применялся")
                    }
                    }
                } else {
                    InspectorSection(title: "Пока нет сведений", icon: "text.bubble") {
                        Text("Когда у ответа появятся сохранённые источники и проверки, их можно будет открыть через меню «Подробнее» под сообщением.").foregroundStyle(.secondary)
                    }
                }
                Divider()
                DisclosureGroup("Технические сведения") {
                    Text(model.contextLabel).font(.caption).foregroundStyle(.secondary)
                    Text("Показанные проверки не раскрывают внутренние рассуждения модели и не доказывают правильность ответа. Команды приложения выполняются отдельно от модели.")
                        .font(.caption).foregroundStyle(.secondary)
                }
            }.font(.system(size: 12)).padding(20).frame(maxWidth: .infinity, alignment: .leading)
        }.background(NativeTheme.composer.opacity(0.4))
    }

    private func detail(_ label: String, _ value: String) -> some View {
        VStack(alignment: .leading, spacing: 3) {
            Text(label).foregroundStyle(.secondary)
            Text(value.isEmpty ? "не указано" : Self.valueLabels[value] ?? value).textSelection(.enabled).help(value)
        }
    }

    private static let valueLabels = [
        "mock": "Тестовый режим", "codex": "Codex", "ollama": "Ollama",
        "new_question": "Новый вопрос", "personal_context": "Личный контекст",
        "project_context": "О проекте", "meta_architecture": "Об устройстве приложения",
        "continuity_followup": "Продолжение разговора", "memory_inventory": "Обзор памяти",
        "decision_request": "Выбор решения", "not_needed": "Проверка не требовалась",
        "grounded": "Согласовано", "partially_grounded": "Частично согласовано",
        "ungrounded": "Недостаточно опоры", "contradicted": "Найдено противоречие",
        "high": "Высокая", "medium": "Средняя", "low": "Низкая"
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
            Text("Все возможности. Одно ядро.").font(.system(size: 25, weight: .medium))
            Text("Каталог из действующего реестра. Выбор только переносит команду в поле ввода; ничего не запускается автоматически.")
                .font(.callout).foregroundStyle(.secondary)
            HStack {
                TextField("Найти команду, категорию или описание", text: $search).textFieldStyle(.roundedBorder)
                Toggle("Только чтение", isOn: $readOnly).toggleStyle(.checkbox).font(.caption)
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
                                        Text(item["read_only"].flag ? "read-only · \(item["risk"].text)" : "Изменяет: \(item["mutates"].text) · \(item["risk"].text)")
                                            .font(.system(size: 10)).foregroundStyle(item["read_only"].flag ? Color.secondary : .orange)
                                    }
                                    Spacer(minLength: 10)
                                    Button("Подготовить") { model.setComposer(item["prefix"].text); model.section = .chat }
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
                Text("Локальное ядро на месте").font(.system(size: 28, weight: .medium))
                Text("Новый интерфейс не переносит и не заменяет ваши данные. Здесь быстрый обзор, прочитанный без создания записей.")
                    .foregroundStyle(.secondary).font(.callout)
                HStack(spacing: 15) {
                    stat("Команды", model.bootstrap["registry_count"].integer)
                    stat("Категории", model.bootstrap["category_count"].integer)
                    stat("Записи памяти", model.bootstrap["memory_count"].integer)
                }
                GroupBox {
                    VStack(alignment: .leading, spacing: 12) {
                        Label(model.contextLabel, systemImage: "lock.shield")
                        Text(model.bootstrap["project_root"].text).font(.system(size: 11, design: .monospaced)).textSelection(.enabled)
                        Text("Память, цели, задачи, навыки и существующие разрешения обслуживает прежний Python-core.")
                            .font(.callout).foregroundStyle(.secondary)
                    }.padding(8).frame(maxWidth: .infinity, alignment: .leading)
                }
                Button { model.showPersonaInspector = true } label: {
                    HStack(spacing: 13) {
                        Image(systemName: "person.crop.circle.badge.checkmark").font(.title3)
                        VStack(alignment: .leading, spacing: 4) {
                            Text("Persona Inspector").font(.headline)
                            Text("Brother Kernel, Identity и текущий self-model · только read-only preview")
                                .font(.caption).foregroundStyle(.secondary)
                        }
                        Spacer()
                        Image(systemName: "chevron.right").foregroundStyle(.tertiary)
                    }.padding(15).background(Color.primary.opacity(0.035), in: RoundedRectangle(cornerRadius: 12))
                }.buttonStyle(.nativeHover).disabled(model.busy)
                Text("РУЧНЫЕ ПРОВЕРКИ").font(.system(size: 10, weight: .semibold)).foregroundStyle(.secondary)
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
