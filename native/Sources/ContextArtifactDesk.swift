import SwiftUI

struct NativeContextPreview: Equatable {
    let value: JSONValue
    var manifest: JSONValue { value["manifest"] }
    var sources: [JSONValue] { value["sources"].items }
    var imageSources: [JSONValue] { value["image_sources"].items }
    var pdfSources: [JSONValue] { value["pdf_sources"].items }

    init(_ value: JSONValue) throws {
        guard value["schema"].text == "proto_mind.native_context_preview.v1",
              value["read_only"] == .bool(true), value["no_execution"] == .bool(true),
              value["manifest"]["schema"].text == "proto_mind.native_context_manifest.v1",
              value["manifest"]["permission_granted"] == .bool(false),
              value["manifest"]["memory_scope"].text == "shared_core_not_workspace",
              NativeTaskCriteria.validContract(value["manifest"]["success_criteria"]),
              case .array(let sources) = value["sources"], sources.count <= 3,
              sources.allSatisfy({ ["ready", "changed", "unavailable"].contains($0["state"].text)
                  && $0["excerpt"].text.unicodeScalars.count <= 6000 && $0["expected_sha256"].text.count == 64 }),
              case .array(let history) = value["history"], history.count <= 12,
              history.allSatisfy({ ["user", "assistant"].contains($0["role"].text) && $0["content"].text.unicodeScalars.count <= 2000 }) else {
            throw NativeError.message("Формат локального контекста не прошёл проверку. Ничего не отправлено.")
        }
        if !value["image_sources"].isNull {
            guard case .array(let images) = value["image_sources"], images.count <= 3,
                  images.allSatisfy({ ["ready", "changed", "unavailable", "over_limit"].contains($0["state"].text)
                      && $0["expected_sha256"].text.count == 64 && $0["data_base64"].isNull }) else {
                throw NativeError.message("Состав изображений не прошёл проверку.")
            }
            for image in images where image["state"].text == "ready" { _ = try NativeImageAttachment(image["image"]) }
        }
        if !value["manifest"]["images"].isNull {
            guard case .array = value["manifest"]["images"] else { throw NativeError.message("Неверный manifest изображений.") }
            try NativeImageAttachment.validate(value["manifest"]["images"].items)
        }
        if !value["pdf_sources"].isNull {
            guard case .array(let pdfs) = value["pdf_sources"], pdfs.count <= 1,
                  pdfs.allSatisfy({ ["ready", "changed", "unavailable"].contains($0["state"].text)
                      && NativePDFAttachment.isHash($0["expected_sha256"]) }) else {
                throw NativeError.message("Состав PDF не прошёл проверку.")
            }
            for pdf in pdfs where pdf["state"].text == "ready" {
                _ = try NativePDFPreview(.object(["schema": .string("proto_mind.native_pdf_preview.v1"),
                    "read_only": .bool(true), "no_execution": .bool(true), "pdf": pdf["pdf"], "pages": pdf["pages"],
                    "has_text": .bool(true)]), conversationID: UUID(), workspace: nil, canAttach: false)
            }
        }
        if !value["manifest"]["pdfs"].isNull {
            guard case .array = value["manifest"]["pdfs"] else { throw NativeError.message("Неверный manifest PDF.") }
            try NativePDFAttachment.validate(value["manifest"]["pdfs"].items)
        }
        try checkKnowledgeMetadata(value["manifest"]["knowledge_context"])
        if !value["project_memory_sources"].isNull {
            guard case .array(let notes) = value["project_memory_sources"], notes.count <= 5,
                  notes.count == value["manifest"]["knowledge_context"]["project_memory"].items.count,
                  notes.allSatisfy({ (1...4000).contains($0["content"].text.unicodeScalars.count) && (1...1000).contains($0["basis"].text.unicodeScalars.count) }) else { throw projectMemoryError() }
        }
        let reference = value["manifest"]["knowledge_context"]["skill_task"]
        if !reference.isNull {
            guard case .object(let selected) = value["skill_task_source"],
                  let conversation = UUID(uuidString: reference["conversation_id"].text),
                  selected["preview_fingerprint"] == reference["preview_fingerprint"] else { throw skillTaskError() }
            let body = JSONValue.object(selected.filter { $0.key != "preview_fingerprint" })
            let scope = ProjectMemoryScope(conversationID: conversation, workspace: reference["workspace"]["path"].text)
            try checkSkillTaskBody(body, scope: scope)
            let hash = try verifyCanonicalMaterial(value["skill_task_hash_material"], expected: body)
            guard reference == skillTaskReference(body: body, fingerprint: hash), body["success_criteria"] == value["manifest"]["success_criteria"],
                  reference["goal_sha256"] == value["manifest"]["input"]["sha256"] else { throw skillTaskError() }
        } else if !value["skill_task_source"].isNull || !value["skill_task_hash_material"].isNull { throw skillTaskError() }
        if !value["auto_skills"].isNull {
            let report = try NativeAutoSkillsReport(value["auto_skills"])
            guard ["ready", "empty", "unavailable"].contains(report.state), !report.value["selector_attempted"].flag,
                  report.value["goal_sha256"] == value["manifest"]["input"]["sha256"], reference.isNull else { throw NativeAutoSkillsReport.error() }
        }
        self.value = value
    }
}

struct NativeArtifactDesk: Equatable {
    let value: JSONValue
    var items: [JSONValue] { value["items"].items }

    init(_ value: JSONValue, run: NativeWorkSession) throws {
        guard value["schema"].text == "proto_mind.native_artifact_desk.v1",
              value["read_only"] == .bool(true), value["no_execution"] == .bool(true),
              value["run_id"].text == run.id, value["run_fingerprint"] == run.value["fingerprint"],
              value["verification"]["status"].text == "not_assessed", value["verification"]["acceptance"] == run.value["acceptance"],
              value["success_criteria"] == run.value["success_criteria"],
              value["operator_reviews"].items == run.value["operator_reviews"].items,
              case .array(let items) = value["items"], items.count <= 24,
              items.allSatisfy({ !$0["id"].text.isEmpty && ["captured", "unavailable", "not_captured"].contains($0["state"].text) }),
              case .array(let commands) = value["commands"], commands.count <= 64,
              commands.allSatisfy({ $0["kind"].text == "commandExecution" }) else {
            throw NativeError.message("Не удалось проверить происхождение результатов. Запуск не изменён.")
        }
        self.value = value
    }
}

struct NativeArtifactPreview: Equatable {
    let value: JSONValue

    init(_ value: JSONValue, run: NativeWorkSession, artifactID: String) throws {
        guard value["schema"].text == "proto_mind.native_artifact_preview.v1",
              value["read_only"] == .bool(true), value["no_execution"] == .bool(true),
              value["run_id"].text == run.id, value["run_fingerprint"] == run.value["fingerprint"],
              value["artifact"]["id"].text == artifactID,
              ["current", "changed", "unavailable", "not_captured"].contains(value["state"].text),
              value["current"]["preview"].text.unicodeScalars.count <= 12000,
              value["diff_preview"].text.unicodeScalars.count <= 800 else {
            throw NativeError.message("Файл не соответствует выбранному артефакту. Повторно откройте журнал.")
        }
        self.value = value
    }
}

struct ContextDeskView: View {
    @ObservedObject var model: AppModel

    var body: some View {
        VStack(spacing: 0) {
            HStack {
                Label("Контекст перед отправкой", systemImage: "doc.text.magnifyingglass").font(.title3.weight(.semibold))
                Spacer()
                if model.loadingContextPreview { ProgressView().controlSize(.small) }
                Button { Task { await model.refreshContextPreview() } } label: { Image(systemName: "arrow.clockwise") }
                    .disabled(model.busy || model.loadingContextPreview).help("Перепроверить файлы локально")
                Button { model.showContextDesk = false } label: { Image(systemName: "xmark") }.keyboardShortcut(.cancelAction)
            }.padding(20)
            Divider()
            ScrollView {
                VStack(alignment: .leading, spacing: 20) {
                    if let error = model.contextPreviewError { Label(error, systemImage: "exclamationmark.triangle").foregroundStyle(.orange) }
                    if let preview = model.contextPreview {
                        let manifest = preview.manifest
                        DeskSection("Куда пойдёт запрос", icon: "arrow.up.circle") {
                            Text(destination(manifest["destination"].text)).font(.headline)
                            if manifest["destination"].text == "openai_cloud" {
                                Text(preview.value["cloud_consent"].flag
                                     ? "Облачная обработка разрешена вами. Данные уйдут только после отдельной отправки сообщения."
                                     : "Облачная обработка не разрешена. Этот просмотр остаётся локальным и ничего не разрешает.")
                                    .foregroundStyle(.orange)
                            }
                            Text("Текст запроса: \(manifest["input"]["characters"].integer) символов. История: \(manifest["history"]["messages"].integer) сообщений, \(manifest["history"]["characters"].integer) символов.")
                            Text("Модель: \(manifest["requested_model"].text.isEmpty ? "по умолчанию аккаунта/провайдера" : manifest["requested_model"].text). Это выбранные настройки, не подтверждение доступности модели.")
                                .font(.caption).foregroundStyle(.secondary)
                        }
                        if manifest["provider"].text == "codex" {
                            let thread = manifest["provider_thread"]
                            DeskSection("Сессия Codex", icon: "link.circle") {
                                if thread["linked"].flag {
                                    Text(thread["workspace_matches"].flag
                                         ? "Продолжится сохранённый thread · \(thread["thread_id_short"].text)"
                                         : "Сохранённый thread относится к другой рабочей папке.")
                                        .fontWeight(.medium)
                                        .foregroundStyle(thread["workspace_matches"].flag ? Color.primary : .orange)
                                    Text("Локальная история повторно не прикладывается. Историю provider thread этот preview не дублирует.")
                                        .font(.caption).foregroundStyle(.secondary)
                                } else {
                                    Text("Следующее сообщение создаст новый постоянный thread Codex.").fontWeight(.medium)
                                    Text("До 12 показанных локальных реплик будут использованы один раз для начального continuity.")
                                        .font(.caption).foregroundStyle(.secondary)
                                }
                            }
                        }
                        DeskSection("Папка и память: разные области", icon: "folder.badge.questionmark") {
                            Text("Файлы: \(manifest["workspace"].text.isEmpty ? "рабочая папка не привязана" : manifest["workspace"].text)").textSelection(.enabled)
                            Text("Память: общее ядро Proto-Mind, не отдельная память этой папки.").fontWeight(.medium)
                            Text(manifest["memory_root"].text).font(.caption).foregroundStyle(.secondary).textSelection(.enabled)
                            Text(manifest["operator"].flag
                                 ? "Операторский маршрут не получает вложения и историю модели. Саму команду здесь не выполняем."
                                 : "Поиск памяти и контекст исправлений выбираются ядром при отправке, здесь они не вычислялись. Фактически выбранную память можно проверить в инспекторе полученного ответа.")
                                .foregroundStyle(.secondary)
                            Text("Context Injection: \(injectionLabel(manifest["context_injection"]["state"].text)). Настройка не меняется.")
                            if manifest["access_mode"].text == "full_access" {
                                Text(model.computerUseAvailable
                                     ? "Выбран полный доступ к Mac, интернету и экрану: инструменты могут прочитать другие файлы, использовать live Web Search и управлять видимыми приложениями. Этот список не ограничивает их права."
                                     : "Выбран полный доступ к Mac и интернету: инструменты могут прочитать другие файлы, использовать live Web Search и сеть. Computer Use недоступен. Этот список не ограничивает их права.").foregroundStyle(.orange)
                            }
                        }
                        if !manifest["success_criteria"].isNull {
                            DeskSection("Критерии следующей задачи", icon: "checklist") {
                                ForEach(Array(manifest["success_criteria"]["items"].items.enumerated()), id: \.offset) { index, item in
                                    Text("\(index + 1). \(item["text"].text)").textSelection(.enabled)
                                }
                                Text("Передаются выбранной модели при отправке, но не добавляют прав и не являются автоматически проверенными фактами.")
                                    .font(.caption).foregroundStyle(.secondary)
                            }
                        } else if preview.value["excluded_criterion_count"].integer > 0 {
                            Text("Критерии пропущены для операторской команды: \(preview.value["excluded_criterion_count"].integer). Они остаются в черновике.")
                                .foregroundStyle(.secondary)
                        }
                        if !preview.value["skill_task_source"].isNull {
                            DeskSection("Явно выбранный навык", icon: "list.bullet.clipboard") {
                                SkillTaskContractView(value: preview.value["skill_task_source"])
                                Text("Это ориентир для следующего ручного Send. Проверка происхождения не оценивает качество выполнения и не выдаёт разрешений.").font(.caption).foregroundStyle(.secondary)
                            }
                        }
                        if let report = try? NativeAutoSkillsReport(preview.value["auto_skills"]) {
                            DeskSection("Автоматические навыки", icon: "square.stack.3d.up") {
                                AutoSkillsReportView(report: report)
                                Text("При отправке: один отдельный запрос выбранной Codex-модели на low, если поддерживается, иначе на усилии по умолчанию. Он получает задачу, до четырёх последних сообщений и краткий каталог. Основной ответ сохраняет выбранное вами усилие. Здесь облачного запроса нет.").font(.caption).foregroundStyle(.secondary)
                            }
                        }
                        DeskSection("Заметки проекта", icon: "brain") {
                            if !preview.value["project_memory_sources"].items.isEmpty {
                                Text("Явно выбранная память проекта").font(.headline)
                                ForEach(Array(preview.value["project_memory_sources"].items.enumerated()), id: \.offset) { _, note in
                                    Text("\(ProjectNote.title(note["kind"].text)) · \(note["id"].text.prefix(12))").fontWeight(.medium)
                                    Text(note["content"].text).textSelection(.enabled)
                                    Text("Основание оператора: \(note["basis"].text)").font(.caption).foregroundStyle(.secondary)
                                }
                                Text("Утверждения оператора, не независимые факты. Этот выбор попадёт в следующий запрос; Send проверит источники заново. Старый контекст может оставаться в истории провайдера.").font(.caption).foregroundStyle(.secondary)
                                Divider()
                            }
                            if preview.value["project_memory_sources"].items.isEmpty { Text("Заметки не выбраны или пропущены для операторской команды.").foregroundStyle(.secondary) }
                        }
                        DeskSection("Текстовые вложения · \(preview.sources.count)/3", icon: "paperclip") {
                            if preview.sources.isEmpty {
                                Text(manifest["operator"].flag ? "Вложения пропущены: \(preview.value["excluded_attachment_count"].integer)." : "Файлы не выбраны. Папка целиком, экран и буфер обмена не прикладываются.").foregroundStyle(.secondary)
                            }
                            ForEach(Array(preview.sources.enumerated()), id: \.offset) { _, source in
                                VStack(alignment: .leading, spacing: 8) {
                                    Label(source["path"].text, systemImage: source["state"].text == "ready" ? "doc.text" : "exclamationmark.triangle")
                                        .fontWeight(.medium).textSelection(.enabled)
                                    Text(sourceLabel(source)).foregroundStyle(source["state"].text == "ready" ? Color.secondary : .orange)
                                    hashLine("Выбранный SHA-256", source["expected_sha256"].text)
                                    if !source["current_sha256"].text.isEmpty { hashLine("Текущий SHA-256", source["current_sha256"].text) }
                                    if source["state"].text == "ready" {
                                        DisclosureGroup("Точный фрагмент вложения · \(source["included_chars"].integer) символов") {
                                            DeskPlainText(text: source["excerpt"].text)
                                        }
                                    }
                                }.padding(.vertical, 6)
                            }
                            Text("До 6 000 символов из каждого UTF-8 файла. SHA-256 проверяется снова перед отправкой; новая версия не подставляется автоматически. Это не проверка секретов в тексте.")
                                .font(.caption).foregroundStyle(.secondary)
                        }
                        DeskSection("Изображения · \(preview.imageSources.count)/3", icon: "photo.on.rectangle") {
                            if preview.imageSources.isEmpty {
                                Text(manifest["operator"].flag ? "Изображения пропущены для команды: \(preview.value["excluded_image_count"].integer)." : "Изображения не выбраны. Экран и фототека не читаются автоматически.")
                                    .foregroundStyle(.secondary)
                            }
                            ForEach(Array(preview.imageSources.enumerated()), id: \.offset) { _, source in
                                VStack(alignment: .leading, spacing: 5) {
                                    Text(source["path"].text).font(.callout).textSelection(.enabled)
                                    hashLine("Выбранный SHA-256", source["expected_sha256"].text)
                                    if source["state"].text == "ready" {
                                        Text("Готово локально · \(source["image"]["width"].integer) × \(source["image"]["height"].integer) · \(source["image"]["size_bytes"].integer) байт").foregroundStyle(.secondary)
                                    } else {
                                        Text(source["state"].text == "changed" ? "Файл изменился. Просмотрите и выберите его повторно." : "Недоступно или превышен лимит. Ничего не отправлено.").foregroundStyle(.orange)
                                    }
                                }.padding(.vertical, 5)
                            }
                            if !preview.imageSources.isEmpty { Text(model.imageDestinationNotice).font(.callout).foregroundStyle(.secondary) }
                            Text("До 4 МиБ на файл и 8 МиБ суммарно. При Send проверяются SHA-256 и поддержка изображений моделью. Встроенные метаданные не удаляются. Старые картинки не пересылаются из истории.")
                                .font(.caption).foregroundStyle(.secondary)
                        }
                        DeskSection("PDF · выбранный текст", icon: "doc.richtext") {
                            if preview.pdfSources.isEmpty {
                                Text(manifest["operator"].flag ? "PDF пропущены для команды: \(preview.value["excluded_pdf_count"].integer)." : "PDF не выбран.").foregroundStyle(.secondary)
                            }
                            ForEach(Array(preview.pdfSources.enumerated()), id: \.offset) { _, pdf in
                                Text(pdf["path"].text).textSelection(.enabled)
                                hashLine("Выбранный SHA-256", pdf["expected_sha256"].text)
                                if pdf["state"].text == "ready" {
                                    ForEach(Array(pdf["pages"].items.enumerated()), id: \.offset) { _, page in
                                        DisclosureGroup("Страница \(page["number"].integer) · \(page["included_chars"].integer) символов\(page["truncated"].flag ? " · обрезана" : "")") {
                                            DeskPlainText(text: page["text"].text.isEmpty ? "Нет текстового слоя." : page["text"].text)
                                        }
                                    }
                                } else { Text(pdf["reason"].text).foregroundStyle(.orange) }
                            }
                            Text("Только выбранные страницы, не оригинал PDF. Без OCR и картинок. Перед отправкой проверяются SHA-256 документа и текста; предыдущие PDF не пересылаются из истории.")
                                .font(.caption).foregroundStyle(.secondary)
                        }
                        if !preview.value["history"].items.isEmpty {
                            DisclosureGroup("История, которая войдёт в запрос") {
                                ForEach(Array(preview.value["history"].items.enumerated()), id: \.offset) { _, item in
                                    VStack(alignment: .leading, spacing: 6) {
                                        Text(item["role"].text == "user" ? "Вы" : "Ассистент").font(.caption).foregroundStyle(.secondary)
                                        Text(item["content"].text).textSelection(.enabled)
                                    }.padding(.vertical, 8)
                                }
                            }
                        }
                        Text("Максимум 12 сообщений по 2 000 символов; отчёты, ошибки и журналы инструментов не повторяются как история. Mock не анализирует вложения. Полный системный prompt и приватные рассуждения здесь не показываются.")
                            .font(.caption).foregroundStyle(.secondary)
                    } else if !model.loadingContextPreview && model.contextPreviewError == nil {
                        Text("Откройте просмотр вне активного запроса.").foregroundStyle(.secondary)
                    }
                }.padding(24).frame(maxWidth: .infinity, alignment: .leading)
            }
            Divider()
            HStack {
                Text("Только просмотр. Ни одного запроса модели, записи в память или нового разрешения.").font(.caption).foregroundStyle(.secondary)
                Spacer()
                Button("К сообщению") { model.showContextDesk = false }
            }.padding(18)
        }.frame(width: 850, height: 680).background(NativeTheme.canvas)
            .font(NativeTheme.interfaceFont).buttonStyle(.nativeHover).disclosureGroupStyle(NativeDisclosureStyle())
            .task { await model.refreshContextPreview() }
    }

    private func destination(_ value: String) -> String {
        switch value {
        case "openai_cloud": return "Codex · облачная обработка OpenAI"
        case "ollama_loopback": return "Ollama · на этом Mac"
        case "operator_local": return "Операторская команда · без модели"
        default: return "Mock · локальная диагностика без модели"
        }
    }

    private func injectionLabel(_ state: String) -> String {
        switch state { case "disabled", "default_disabled": return "выключен"; case "enabled": return "включён вручную"; default: return "не удалось прочитать" }
    }

    private func sourceLabel(_ source: JSONValue) -> String {
        switch source["state"].text {
        case "ready": return source["truncated"].flag ? "Совпадает с выбранной версией; будет отправлен только фрагмент." : "Совпадает с выбранной версией."
        case "changed": return "Файл изменился. Заново просмотрите и прикрепите его; отправка со старым SHA будет отклонена."
        default: return "Источник недоступен или исключён. Никакой замены и обходного чтения."
        }
    }
}

struct ArtifactDeskView: View {
    @ObservedObject var model: AppModel
    let run: NativeWorkSession
    @State private var desk: NativeArtifactDesk?
    @State private var preview: NativeArtifactPreview?
    @State private var selectedID: String?
    @State private var error: String?
    @State private var loading = false
    @State private var previewLoading = false
    @State private var previewRequest = UUID()

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                HStack {
                    Text("Файлы и проверка").font(.title3.weight(.semibold))
                    Spacer()
                    if loading || previewLoading { ProgressView().controlSize(.small) }
                    Button { Task { await refresh() } } label: { Image(systemName: "arrow.clockwise") }
                        .help("Перечитать сведения о результате").disabled(model.busy || loading)
                }
                if let error { Text(error).foregroundStyle(.orange).textSelection(.enabled) }
                if let desk {
                    DeskSection("Наблюдения, не обещание успеха", icon: "checkmark.magnifyingglass") {
                        let checks = desk.value["verification"]
                        Text("Команды: \(checks["exit_zero"].integer) с exit 0, \(checks["exit_nonzero"].integer) с ошибкой, \(checks["unknown"].integer) без подтверждённого исхода.")
                        Text(desk.value["success_criteria"].isNull ? "Критерии до запуска не задавались." : "Критериев до запуска: \(desk.value["success_criteria"]["items"].items.count). Их ручная оценка доступна на вкладке «Приёмка».")
                            .foregroundStyle(.secondary)
                        Text("Автоматическая проверка достижения цели не выполнялась. \(NativeManualReview.label(checks["acceptance"].text)).")
                            .foregroundStyle(.secondary)
                        Text("Код 0 не доказывает запуск тестов или успешность всей задачи.").font(.caption).foregroundStyle(.secondary)
                    }
                    DeskSection("Наблюдаемые файлы · \(desk.items.count)", icon: "doc.on.doc") {
                        if !desk.value["captured_at"].text.isEmpty {
                            Text("Чтение SHA при завершении: \(desk.value["captured_at"].text)").font(.caption).foregroundStyle(.secondary)
                        }
                        if desk.items.isEmpty { Text("Изменений через file-change события не наблюдалось. Файлы, созданные через shell без таких событий, автоматически не ищем.").foregroundStyle(.secondary) }
                        ForEach(Array(desk.items.enumerated()), id: \.offset) { _, item in
                            Button { Task { await select(item["id"].text) } } label: {
                                HStack(alignment: .top) {
                                    Image(systemName: "doc.text")
                                    VStack(alignment: .leading, spacing: 4) {
                                        Text(item["reported_path"].text).lineLimit(2)
                                        Text(item["state"].text == "captured" ? "SHA сохранён при завершении ответа" : "Историческая версия не зафиксирована")
                                            .font(.caption).foregroundStyle(.secondary)
                                    }
                                    Spacer()
                                    Image(systemName: "chevron.right").font(.caption)
                                }.padding(10).background(selectedID == item["id"].text ? NativeTheme.selection : .clear, in: RoundedRectangle(cornerRadius: 8))
                            }.disabled(model.busy)
                        }
                        if desk.value["partial"].flag { Text("Показаны первые 24 артефакта; журнал ограничен.").foregroundStyle(.orange) }
                    }
                    if let preview { artifact(preview.value) }
                    if !desk.value["commands"].items.isEmpty {
                        DisclosureGroup("Команды и сохранённый вывод") {
                            ForEach(Array(desk.value["commands"].items.enumerated()), id: \.offset) { _, item in AgentToolRow(item: item) }
                        }
                    }
                    if !desk.value["answer_preview"].text.isEmpty {
                        DisclosureGroup("Ответ модели · не результат независимой проверки") {
                            Text(desk.value["answer_preview"].text).textSelection(.enabled)
                        }
                    }
                    if !desk.value["context_manifest"].isNull {
                        let manifest = desk.value["context_manifest"]
                        DisclosureGroup("Состав запроса при отправке") {
                            Text("\(manifest["provider"].text) · \(manifest["input"]["characters"].integer) символов ввода · история: \(manifest["history"]["messages"].integer) сообщений")
                            Text("Память общего ядра, не память папки. Manifest не содержит полного текста запроса, истории или скрытых prompts.").font(.caption).foregroundStyle(.secondary)
                            ForEach(Array(manifest["knowledge_context"]["project_memory"].items.enumerated()), id: \.offset) { _, note in
                                Text("Заметка проекта: \(note["id"].text.prefix(12)) · SHA \(note["record_hash"].text.prefix(12)) · утверждение оператора")
                                    .font(.caption).textSelection(.enabled)
                            }
                            ForEach(Array(manifest["files"].items.enumerated()), id: \.offset) { _, source in
                                Text("\(source["path"].text) · \(source["included_chars"].integer) символов · SHA \(source["sha256"].text.prefix(12))").font(.caption).textSelection(.enabled)
                            }
                            ForEach(Array(manifest["images"].items.enumerated()), id: \.offset) { _, image in
                                Text("Изображение: \(image["name"].text) · \(image["width"].integer) × \(image["height"].integer) · SHA \(image["sha256"].text.prefix(12))")
                                    .font(.caption).textSelection(.enabled)
                            }
                            if !manifest["images"].items.isEmpty {
                                Text("Сохранены только метаданные изображений, не их байты. Они не прикладываются повторно при продолжении.").font(.caption).foregroundStyle(.secondary)
                            }
                        }
                    }
                    Text("Run: \(run.id)").font(.caption.monospaced()).foregroundStyle(.secondary).textSelection(.enabled)
                    Text("Только локальный текстовый просмотр. HTML и скрипты не исполняются. Исходники не копируются, не восстанавливаются и не прикладываются к новому запросу.")
                        .font(.caption).foregroundStyle(.secondary)
                }
            }.padding(22).frame(maxWidth: .infinity, alignment: .leading)
        }.task { await refresh() }
    }

    @ViewBuilder
    private func artifact(_ value: JSONValue) -> some View {
        DeskSection("Просмотр выбранного результата", icon: "doc.text.magnifyingglass") {
            Text(value["artifact"]["reported_path"].text).fontWeight(.medium).textSelection(.enabled)
            Text("Событие: \(value["artifact"]["tool_id"].text) · текстовый просмотр")
                .font(.caption).foregroundStyle(.secondary).textSelection(.enabled)
            Text(artifactState(value["state"].text)).foregroundStyle(value["state"].text == "current" ? Color.secondary : .orange)
            hashLine("SHA при завершении", value["artifact"]["sha256"].text)
            hashLine("Текущий SHA", value["current"]["sha256"].text)
            hashLine("Исходное вложение", value["artifact"]["original_sha256"].text)
            Text("SHA исходного вложения известен только если этот же файл был прикреплён до работы. Копия прежнего содержимого не хранится; восстановление не предлагается.")
                .font(.caption).foregroundStyle(.secondary)
            if !value["diff_preview"].text.isEmpty {
                DisclosureGroup("Сохранённый diff · фрагмент всего события инструмента") {
                    DeskPlainText(text: value["diff_preview"].text)
                }
            }
            if !value["current"].isNull {
                DisclosureGroup("Текущий файл на диске · до 12 000 символов") {
                    DeskPlainText(text: value["current"]["preview"].text)
                }
            }
            Button("Проверить этот файл ещё раз") { Task { await select(value["artifact"]["id"].text) } }
                .disabled(model.busy || previewLoading)
        }
    }

    private func artifactState(_ state: String) -> String {
        switch state {
        case "current": return "Файл сейчас совпадает с SHA, прочитанным при завершении ответа. Это не доказательство исключительного авторства агента."
        case "changed": return "Файл изменился после завершения. Ниже текущая версия, а не сохранённый результат того запуска."
        case "not_captured": return "Для этого запуска нет исторического SHA. Ниже только текущий файл; его нельзя считать проверенным результатом прошлого запуска."
        default: return "Файл недоступен, вне выбранной папки или не поддерживается. Сохранённое наблюдение не доказывает наличие файла сейчас."
        }
    }

    @MainActor
    private func refresh() async {
        previewRequest = UUID()
        loading = true; desk = nil; preview = nil; selectedID = nil; error = nil; previewLoading = false
        defer { loading = false }
        do { desk = try await model.inspectArtifacts(run) }
        catch { self.error = error.localizedDescription }
    }

    @MainActor
    private func select(_ id: String) async {
        let request = UUID()
        previewRequest = request
        selectedID = id; preview = nil; error = nil; previewLoading = true
        defer { if previewRequest == request { previewLoading = false } }
        do {
            let result = try await model.inspectArtifact(id, run: run)
            if previewRequest == request { preview = result }
        } catch { if previewRequest == request { self.error = error.localizedDescription } }
    }
}

private struct DeskSection<Content: View>: View {
    let title: String
    let icon: String
    @ViewBuilder let content: () -> Content

    init(_ title: String, icon: String, @ViewBuilder content: @escaping () -> Content) {
        self.title = title; self.icon = icon; self.content = content
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Label(title, systemImage: icon).font(.system(size: 12, weight: .semibold)).foregroundStyle(.secondary)
            content()
        }.frame(maxWidth: .infinity, alignment: .leading).padding(16)
            .background(Color.primary.opacity(0.035), in: RoundedRectangle(cornerRadius: 12))
    }
}

private struct DeskPlainText: View {
    let text: String
    var body: some View {
        GeometryReader { viewport in
            ScrollView([.horizontal, .vertical]) {
                Text(text).font(.system(size: 12, design: .monospaced)).textSelection(.enabled)
                    .fixedSize(horizontal: true, vertical: true).padding(12)
                    .frame(minWidth: viewport.size.width, alignment: .leading)
            }
        }.frame(height: min(280, max(60, CGFloat(text.components(separatedBy: "\n").count) * 17 + 24)))
            .background(Color.primary.opacity(0.025), in: RoundedRectangle(cornerRadius: 8))
    }
}

private func hashLine(_ title: String, _ hash: String) -> some View {
    Text("\(title): \(hash.isEmpty ? "не зафиксирован" : hash)")
        .font(.caption.monospaced()).foregroundStyle(.secondary).textSelection(.enabled)
}
