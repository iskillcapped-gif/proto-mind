import SwiftUI

struct NativeWorkSession: Identifiable, Equatable {
    let value: JSONValue
    var id: String { value["id"].text }
    var state: String { value["display_status"].text }
    var needsReview: Bool { ["unknown", "not_started"].contains(state) }
    var canPrepare: Bool { !["running", "preparing"].contains(state) }
    var instructionReceipt: NativeInstructionReceipt? { try? NativeInstructionReceipt(value["instruction_receipt"]) }
    var turnReceipt: NativeTurnReceipt? { try? NativeTurnReceipt(value["turn_receipt"]) }
    var reference: JSONValue { .object(["run_id": .string(id), "fingerprint": value["fingerprint"]]) }
    var title: String {
        switch state {
        case "completed": return L10n.text("Ответ получен")
        case "running": return L10n.text("Работа выполняется")
        case "preparing": return L10n.text("Подготовка запроса")
        case "not_started": return L10n.text("Запрос не был отправлен")
        default: return L10n.text("Исход неизвестен")
        }
    }

    init(_ value: JSONValue) throws {
        guard value["schema"].text == "proto_mind.native_work_session.v1",
              UUID(uuidString: value["id"].text) != nil,
              UUID(uuidString: value["conversation_id"].text) != nil,
              ["completed", "running", "preparing", "not_started", "unknown"].contains(value["display_status"].text),
              value["verification"].text == "not_assessed", NativeManualReview.validRun(value),
              value["automatic_resume"] == .bool(false), value["fingerprint"].text.count == 64,
              value["tools"].items.count <= 64 else {
            throw NativeError.message(L10n.text("Не удалось проверить формат журнала работы. Файл не изменён."))
        }
        try NativePDFAttachment.validate(value["context_manifest"]["pdfs"].items)
        try checkKnowledgeMetadata(value["context_manifest"]["knowledge_context"])
        if !value["context_manifest"]["knowledge_context"]["project_recall"].isNull {
            _ = try NativeProjectRecallReport(value["context_manifest"]["knowledge_context"]["project_recall"], run: value)
        }
        if !value["auto_skills"].isNull { _ = try NativeAutoSkillsReport(value["auto_skills"], run: value) }
        let skill = value["context_manifest"]["knowledge_context"]["skill_task"]
        if !skill.isNull {
            guard skill["workspace"] == value["workspace"], skill["conversation_id"] == value["conversation_id"],
                  skill["provider"] == value["provider"], skill["access_mode"] == value["access_mode"],
                  skill["goal_sha256"] == value["context_manifest"]["input"]["sha256"],
                  skill["criteria_sha256"] == value["success_criteria"]["sha256"] else { throw skillTaskError() }
        }
        if !value["agent_contract"].isNull {
            guard ["proto_mind.native_agent_contract.v1", "proto_mind.native_agent_contract.v2"].contains(value["agent_contract"]["schema"].text),
                  value["agent_contract_hash"].text.count == 64,
                  value["agent_contract"]["provider"].text == "codex_subscription",
                  value["agent_contract"]["access_mode"].text == "full_access" else {
                throw NativeError.message(L10n.text("Контракт сохранённого запуска не прошёл проверку. Файл не изменён."))
            }
        }
        if !value["instruction_receipt"].isNull {
            let receipt = try NativeInstructionReceipt(value["instruction_receipt"])
            guard value["status"] == .string("completed"), receipt.value["provider"] == value["provider"],
                  receipt.value["mode"] == value["access_mode"] else {
                throw NativeError.message(L10n.text("Квитанция инструкций не соответствует сохранённому запуску. Файл не изменён."))
            }
        }
        if !value["turn_receipt"].isNull {
            let receipt = try NativeTurnReceipt(value["turn_receipt"])
            guard value["status"] == .string("completed"), !value["instruction_receipt"].isNull,
                  receipt.value["run_id"] == value["id"], receipt.value["conversation_id"] == value["conversation_id"],
                  receipt.value["provider"] == value["provider"], receipt.value["mode"] == value["access_mode"],
                  receipt.value["input_chars"] == value["input_chars"], receipt.value["input_sha256"] == value["input_sha256"],
                  receipt.value["instruction_receipt_hash"] == value["instruction_receipt"]["receipt_hash"],
                  receipt.value["answer_preview_chars"].integer == value["answer_preview"].text.unicodeScalars.count,
                  receipt.value["answer_preview_sha256"] == .string(NativeTurnReceipt.hash(value["answer_preview"].text)) else {
                throw NativeError.message(L10n.text("Квитанция связи хода не соответствует сохранённому запуску. Файл не изменён."))
            }
        }
        self.value = value
    }
}

struct WorkSessionsView: View {
    @ObservedObject var model: AppModel
    @State private var detail = "overview"

    private var selected: NativeWorkSession? {
        model.workSessions.first { $0.id == model.inspectedWorkSessionID } ?? model.workSessions.first
    }

    var body: some View {
        GeometryReader { geometry in
            let compact = geometry.size.width < 700
            let split = compact ? AnyLayout(VStackLayout(spacing: 0)) : AnyLayout(HStackLayout(spacing: 0))
        VStack(spacing: 0) {
            HStack(spacing: 12) {
                Label(L10n.text("Журнал работы"), systemImage: "clock.arrow.circlepath").font(.title3.weight(.semibold))
                Spacer()
                if model.loadingWorkSessions { ProgressView().controlSize(.small) }
                Button { Task { await model.refreshWorkSessions() } } label: { Image(systemName: "arrow.clockwise") }
                    .disabled(model.busy || model.loadingWorkSessions).help(L10n.text("Перечитать локальный журнал"))
                Button { model.showWorkSessions = false } label: { Image(systemName: "xmark") }.keyboardShortcut(.cancelAction)
            }.padding(20)
            Divider()
            if let warning = model.workSessionsWarning {
                Label(warning, systemImage: "exclamationmark.triangle").font(.callout).foregroundStyle(.orange)
                    .textSelection(.enabled).frame(maxWidth: .infinity, alignment: .leading).padding(16)
            }
            if let error = model.workSessionsActionError {
                Label(error, systemImage: "exclamationmark.circle").font(.callout).foregroundStyle(.orange)
                    .textSelection(.enabled).frame(maxWidth: .infinity, alignment: .leading).padding(16)
            }
            if model.workSessions.isEmpty {
                VStack(spacing: 14) {
                    Image(systemName: "clock").font(.system(size: 30)).foregroundStyle(.tertiary)
                    Text(L10n.text("Для этого диалога пока нет сохранённых запусков."))
                    Text(L10n.text("Новые обычные сообщения сохраняют компактный ход работы. Старую историю мы не переписываем."))
                        .foregroundStyle(.secondary).multilineTextAlignment(.center).frame(maxWidth: 430)
                }.frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                split {
                    ScrollView {
                        LazyVStack(spacing: 6) {
                            ForEach(model.workSessions) { run in
                                Button { model.inspectedWorkSessionID = run.id } label: {
                                    VStack(alignment: .leading, spacing: 7) {
                                        HStack {
                                            Image(systemName: run.needsReview ? "exclamationmark.circle" : "bubble.left")
                                                .foregroundStyle(run.needsReview ? Color.orange : .secondary)
                                            Text(run.title).font(.system(size: 12, weight: .medium))
                                        }
                                        Text(run.value["input_preview"].text).lineLimit(2)
                                        if model.isWorkSessionWarningHidden(run) {
                                            Text(L10n.text("Уведомление скрыто")).font(.caption).foregroundStyle(.secondary)
                                        }
                                        if run.value["acceptance"].text != "not_recorded" {
                                            Text(NativeManualReview.label(run.value["acceptance"].text)).font(.caption).foregroundStyle(.secondary)
                                        }
                                        Text(run.value["created_at"].text).font(.caption).foregroundStyle(.tertiary)
                                    }.frame(maxWidth: .infinity, alignment: .leading).padding(12)
                                        .background(selected?.id == run.id ? NativeTheme.selection : .clear, in: RoundedRectangle(cornerRadius: 10))
                                }
                            }
                            if model.workSessionsNextCursor != nil {
                                Button(L10n.text("Загрузить более ранние")) { Task { await model.loadMoreWorkSessions() } }
                                    .disabled(model.busy || model.loadingWorkSessions)
                                    .frame(maxWidth: .infinity).padding(.vertical, 8)
                            }
                        }.padding(12)
                    }.frame(width: compact ? nil : 245, height: compact ? min(170, geometry.size.height * 0.28) : nil)
                    Divider()
                    if let selected {
                        VStack(spacing: 0) {
                            Picker(L10n.text("Сведения о запуске"), selection: $detail) {
                                Text(L10n.text("Обзор")).tag("overview")
                                Text(L10n.text("Результаты")).tag("results")
                                Text(L10n.text("Приёмка")).tag("review")
                            }.pickerStyle(.segmented).labelsHidden().padding(14)
                            if detail == "results" {
                                ArtifactDeskView(model: model, run: selected).id(selected.id + selected.value["fingerprint"].text)
                            } else if detail == "review" {
                                TaskReviewView(model: model, run: selected).id(selected.id + selected.value["fingerprint"].text)
                            } else {
                                ScrollView { card(selected).padding(22).frame(maxWidth: .infinity, alignment: .leading) }
                            }
                        }
                    }
                }
            }
            Divider()
            VStack(alignment: .leading, spacing: 5) {
                if model.busy { Text(L10n.text("Активный ход работы виден в диалоге. Журнал обновится после завершения запроса.")) }
                if let total = model.workSessionsTotal { Text(L10n.format("Показано запусков: \(model.workSessions.count) из \(total).")) }
                Text(L10n.text("Локальные фрагменты, не полный аудит и не резервная копия изменённых файлов. Автоповтора нет."))
                Text(model.workSessionsPath).textSelection(.enabled).lineLimit(2)
            }.font(.caption).foregroundStyle(.secondary).frame(maxWidth: .infinity, alignment: .leading).padding(16)
        }
        }
        .workspacePageSize(width: 850, height: 660).workspaceBackground(NativeTheme.canvas)
        .font(NativeTheme.interfaceFont).buttonStyle(.nativeHover).disclosureGroupStyle(NativeDisclosureStyle())
        .task { model.workSessionsActionError = nil; await model.refreshWorkSessions() }
    }

    @ViewBuilder
    private func card(_ run: NativeWorkSession) -> some View {
        VStack(alignment: .leading, spacing: 18) {
            Text(run.title).font(.title2.weight(.medium))
            if run.state == "unknown" {
                Label(L10n.text("Запрос успел начать обработку, но его полный результат не подтверждён. Действия могли уже произойти. Сначала проверьте файлы и команды, не запускайте их повторно вслепую."), systemImage: "exclamationmark.triangle")
                    .foregroundStyle(.orange).font(.callout)
            }
            Text(run.value["input_preview"].text).textSelection(.enabled)
            VStack(alignment: .leading, spacing: 6) {
                metadata(L10n.text("Запуск"), run.id)
                metadata(L10n.text("Провайдер"), run.value["provider"].text)
                metadata(L10n.text("Выбранная модель"), run.value["requested_model"].text.isEmpty ? L10n.text("по умолчанию провайдера") : run.value["requested_model"].text)
                metadata(L10n.text("Режим при запросе"), run.value["access_mode"].text)
                metadata(L10n.text("Рабочая папка"), run.value["workspace"]["path"].text.isEmpty ? L10n.text("не привязана") : run.value["workspace"]["path"].text)
                metadata(L10n.text("Обновлено"), run.value["updated_at"].text)
                if !run.value["agent_contract_hash"].text.isEmpty {
                    metadata(L10n.text("Контракт запуска"), String(run.value["agent_contract_hash"].text.prefix(12)))
                }
            }
            if !run.value["agent_contract"].isNull {
                Text(L10n.text("Контракт фиксирует провайдера, доступные инструменты, лимиты, stop conditions и отсутствие автоповтора до запуска Codex. Runtime-инвентарь проверяется отдельно; это не доказательство достижения цели."))
                    .font(.caption).foregroundStyle(.secondary)
            }
            if let receipt = run.instructionReceipt {
                VStack(alignment: .leading, spacing: 9) {
                    Label(L10n.text("Квитанция локальных инструкций"), systemImage: "checkmark.seal").font(.headline)
                    metadata(L10n.text("Провайдер и режим"), "\(receipt.value["provider"].text) · \(receipt.value["mode"].text)")
                    metadata("Persona", receipt.value["persona_state"].text)
                    metadata(L10n.text("Выбрано записей памяти"), String(receipt.value["selected_memory_count"].integer))
                    metadata("Correction hints", String(receipt.value["correction_hint_count"].integer))
                    ForEach(Array(receipt.layers.enumerated()), id: \.offset) { _, layer in
                        VStack(alignment: .leading, spacing: 3) {
                            Text(layer["id"].text).font(.callout.weight(.medium))
                            metadata(L10n.text("Размещение"), layer["placement"].text)
                            metadata(L10n.text("Источник"), layer["source"].text)
                            metadata(L10n.text("Размер"), L10n.format("\(layer["characters"].integer) символов"))
                            metadata("SHA-256", layer["sha256"].text)
                        }.padding(.vertical, 3)
                    }
                    metadata("Receipt SHA-256", receipt.value["receipt_hash"].text)
                    Text(L10n.text("Сохранены только размеры, источники и SHA-256 фактически собранных Proto-Mind слоёв. Текст инструкций, provider-owned prompt и приватные рассуждения не сохранены. Квитанция подтверждает локальную сборку для provider call, но не является независимым подтверждением доставки или интерпретации провайдером."))
                        .font(.caption).foregroundStyle(.secondary)
                }.padding(14).background(Color.primary.opacity(0.035), in: RoundedRectangle(cornerRadius: 12))
            } else if run.state == "completed" && ["codex", "ollama", "api"].contains(run.value["provider"].text) {
                Label(L10n.text("Исторический запуск: content-free квитанция инструкций ещё не сохранялась."), systemImage: "clock")
                    .font(.caption).foregroundStyle(.secondary)
            }
            Text(L10n.format("Автоматическая проверка достижения цели: не выполнялась. \(NativeManualReview.label(run.value["acceptance"].text)). Ответ модели и успешный exit code сами по себе не доказывают завершение задачи."))
                .font(.callout).foregroundStyle(.secondary)
            if !run.value["success_criteria"].isNull {
                DisclosureGroup(L10n.text("Критерии, заданные перед отправкой")) {
                    ForEach(Array(run.value["success_criteria"]["items"].items.enumerated()), id: \.offset) { index, item in
                        Text("\(index + 1). \(item["text"].text)").textSelection(.enabled)
                    }
                }
            }
            if let report = try? NativeAutoSkillsReport(run.value["auto_skills"], run: run.value) {
                AutoSkillsReportView(report: report)
            }
            if let report = try? NativeProjectRecallReport(run.value["context_manifest"]["knowledge_context"]["project_recall"], run: run.value) {
                ProjectRecallReportView(report: report)
            }
            if !run.value["context_manifest"]["knowledge_context"]["skill_task"].isNull {
                let skill = run.value["context_manifest"]["knowledge_context"]["skill_task"]
                VStack(alignment: .leading, spacing: 9) {
                    Label(L10n.format("Ориентир: \(skill["skill_name"].text)"), systemImage: "list.bullet.clipboard").font(.headline)
                    metadata("Skill ID", skill["skill_id"].text)
                    metadata(L10n.text("Проверенная версия"), String(skill["contract_hash"].text.prefix(12)))
                    Text(L10n.text("Навык был выбран оператором, не запускался интерпретатором. Происхождение проверялось перед запросом. Откройте «Приёмку», сопоставьте каждый критерий с результатами; ответ сам по себе не означает успех навыка.")).font(.callout).foregroundStyle(.secondary)
                    Button(L10n.text("Открыть текущий навык")) {
                        Task { model.showWorkSessions = false; await model.openSkillInspection(skillID: skill["skill_id"].text) }
                    }
                    Text(L10n.text("Исторические SHA не заменяются текущей версией. Ручная приёмка не меняет uses, память или жизненный цикл.")).font(.caption).foregroundStyle(.secondary)
                }.padding(14).background(Color.primary.opacity(0.035), in: RoundedRectangle(cornerRadius: 12))
            }
            if !run.value["work_log"]["entries"].items.isEmpty {
                DisclosureGroup(L10n.text("Публичный ход работы")) {
                    ForEach(Array(run.value["work_log"]["entries"].items.enumerated()), id: \.offset) { _, entry in
                        if !entry["text"].text.isEmpty { Text(entry["text"].text).textSelection(.enabled).padding(.vertical, 5) }
                        ForEach(Array(entry["steps"].items.enumerated()), id: \.offset) { _, step in
                            Text("\(step["status"].text): \(step["step"].text)").font(.callout)
                        }
                    }
                }
            }
            if !run.value["tools"].items.isEmpty {
                if run.value["tools_truncated"].flag {
                    Text(L10n.text("Сохранена последняя часть действий")).font(.caption).foregroundStyle(.secondary)
                }
                DisclosureGroup(L10n.format("Наблюдаемые действия: \(run.value["tools"].items.count)")) {
                    ForEach(Array(run.value["tools"].items.enumerated()), id: \.offset) { _, item in AgentToolRow(item: item) }
                }
            }
            if !run.value["answer_preview"].text.isEmpty {
                DisclosureGroup(L10n.text("Сохранённый фрагмент ответа")) { Text(run.value["answer_preview"].text).textSelection(.enabled) }
            }
            if !run.value["sources"].items.isEmpty {
                DisclosureGroup(L10n.text("Исходные вложения")) {
                    ForEach(Array(run.value["sources"].items.enumerated()), id: \.offset) { _, source in
                        Text("\(source["path"].text) · SHA \(source["sha256"].text.prefix(12))").font(.caption).textSelection(.enabled)
                    }
                }
            }
            if !run.value["context_manifest"]["images"].items.isEmpty {
                DisclosureGroup(L10n.text("Изображения этого запроса")) {
                    ForEach(Array(run.value["context_manifest"]["images"].items.enumerated()), id: \.offset) { _, image in
                        Text("\(image["path"].text) · \(image["width"].integer) × \(image["height"].integer) · SHA \(image["sha256"].text.prefix(12))")
                            .font(.caption).textSelection(.enabled)
                    }
                    Text(L10n.text("Журнал хранит метаданные, не копии изображений. Продолжение не прикрепляет их автоматически.")).font(.caption).foregroundStyle(.secondary)
                }
            }
            if !run.value["context_manifest"]["pdfs"].items.isEmpty {
                DisclosureGroup(L10n.text("PDF этого запроса · только метаданные")) {
                    ForEach(Array(run.value["context_manifest"]["pdfs"].items.enumerated()), id: \.offset) { _, pdf in
                        Text(L10n.format("\(pdf["name"].text) · стр. \(pdf["pages"].items.map { String($0["number"].integer) }.joined(separator: ", ")) · SHA \(pdf["sha256"].text.prefix(12))"))
                            .font(.caption).textSelection(.enabled)
                    }
                    Text(L10n.text("PDF и извлечённый текст здесь не сохраняются. Продолжение не прикрепляет страницы автоматически.")).font(.caption).foregroundStyle(.secondary)
                }
            }
            Divider()
            WorkSessionNoticeControls(model: model, run: run)
            Button { Task { await model.prepareContinuation(run) } } label: {
                Label(L10n.text("Подготовить продолжение"), systemImage: "square.and.pencil").padding(.horizontal, 8)
            }.disabled(model.busy || !run.canPrepare || model.selected?.archived == true)
            Text(L10n.text("Только черновик нового запроса. Просмотрите его и отправьте вручную. Это не восстановление потока провайдера, вложений или прав доступа."))
                .font(.caption).foregroundStyle(.secondary)
        }
    }

    private func metadata(_ label: String, _ value: String) -> some View {
        Text("\(label): \(value)").font(.caption).foregroundStyle(.secondary).textSelection(.enabled)
    }
}
