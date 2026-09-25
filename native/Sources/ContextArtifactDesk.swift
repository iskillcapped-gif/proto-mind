import CryptoKit
import SwiftUI

struct NativeInstructionPreview: Equatable {
    private static let fields: Set<String> = [
        "schema", "read_only", "no_execution", "no_model_call", "no_network_call", "no_store_write",
        "no_thread_refresh", "private_reasoning_included", "provider", "mode", "operator", "persona_state",
        "current_projection", "recomputed_on_send", "read_only_retrieval_performed", "selected_memory_count",
        "selected_memory_ids", "correction_hint_count", "provider_owned_instructions", "layers", "notices",
        "projection_hash", "hash_material",
    ]
    private static let materialFields = fields.subtracting(["schema", "projection_hash", "hash_material"])
    private static let layerFields: Set<String> = [
        "id", "owner", "placement", "source", "text", "characters", "sha256", "dynamic", "provider_visible_at_send",
    ]
    let value: JSONValue
    var layers: [JSONValue] { value["layers"].items }

    init(_ value: JSONValue) throws {
        guard case .object(let fields) = value, Set(fields.keys) == Self.fields,
              value["schema"] == .string("proto_mind.native_instruction_preview.v1"),
              ["read_only", "no_execution", "no_model_call", "no_network_call", "no_store_write", "no_thread_refresh", "current_projection"]
                .allSatisfy({ value[$0] == .bool(true) }),
              value["private_reasoning_included"] == .bool(false),
              ["codex", "ollama", "mock", "api", "claude"].contains(value["provider"].text),
              ["chat", "full_access", "operator"].contains(value["mode"].text),
              case .bool = value["operator"], case .bool = value["recomputed_on_send"],
              case .bool = value["read_only_retrieval_performed"],
              ["brother", "legacy", "bypassed"].contains(value["persona_state"].text),
              case .array(let memoryIDs) = value["selected_memory_ids"], memoryIDs.count <= 10,
              memoryIDs.allSatisfy({ !$0.text.isEmpty && $0.text.unicodeScalars.count <= 160 }),
              Set(memoryIDs.map(\.text)).count == memoryIDs.count,
              value["selected_memory_count"] == .number(Double(memoryIDs.count)),
              case .number(let correctionCount) = value["correction_hint_count"], correctionCount.rounded() == correctionCount,
              correctionCount >= 0, correctionCount <= 5,
              case .object(let boundary) = value["provider_owned_instructions"],
              Set(boundary.keys) == ["included", "available_to_proto_mind", "reason"],
              value["provider_owned_instructions"]["included"] == .bool(false),
              value["provider_owned_instructions"]["available_to_proto_mind"] == .bool(false),
              (1...500).contains(value["provider_owned_instructions"]["reason"].text.unicodeScalars.count),
              case .array(let layers) = value["layers"], layers.count <= 2,
              case .array(let notices) = value["notices"], (2...8).contains(notices.count),
              notices.allSatisfy({ (1...800).contains($0.text.unicodeScalars.count) }) else {
            throw Self.error()
        }
        for layer in layers {
            guard case .object(let body) = layer, Set(body.keys) == Self.layerFields,
                  layer["owner"] == .string("proto_mind"), layer["provider_visible_at_send"] == .bool(true),
                  case .bool = layer["dynamic"],
                  (1...24_512).contains(layer["text"].text.unicodeScalars.count),
                  !layer["text"].text.contains("\0"), !layer["text"].text.contains("\r"),
                  layer["characters"] == .number(Double(layer["text"].text.unicodeScalars.count)),
                  layer["sha256"].text == Self.hash(layer["text"].text) else { throw Self.error() }
        }
        let identifiers = layers.map { $0["id"].text }
        let bypassed = value["operator"].flag || value["provider"].text == "mock"
        if bypassed {
            guard layers.isEmpty, value["persona_state"] == .string("bypassed"),
                  value["recomputed_on_send"] == .bool(false),
                  value["mode"] == .string(value["operator"].flag ? "operator" : "chat"),
                  memoryIDs.isEmpty, value["correction_hint_count"] == .number(0),
                  value["read_only_retrieval_performed"] == .bool(false) else { throw Self.error() }
        } else if value["provider"] == .string("codex") {
            guard ["chat", "full_access"].contains(value["mode"].text),
                  identifiers == ["base_instructions", "developer_instructions"],
                  layers[0]["placement"] == .string("codex_base_instructions"),
                  ["legacy_cognitive_core_current_projection", "brother_persona_current_projection"].contains(layers[0]["source"].text),
                  layers[0]["dynamic"] == .bool(true),
                  layers[1]["placement"] == .string("codex_developer_instructions"),
                  layers[1]["source"] == .string(value["mode"].text == "full_access" ? "full_mac_static_contract" : "chat_static_contract"),
                  layers[1]["dynamic"] == .bool(false), value["recomputed_on_send"] == .bool(true) else { throw Self.error() }
        } else {
            guard ["ollama", "api", "claude"].contains(value["provider"].text), (value["provider"].text == "claude" || value["mode"] == .string("chat")),
                  identifiers == ["system_instructions"], layers[0]["placement"] == .string(value["provider"].text + "_system_message"),
                  ["legacy_cognitive_core_current_projection", "brother_persona_current_projection"].contains(layers[0]["source"].text),
                  layers[0]["dynamic"] == .bool(true), value["recomputed_on_send"] == .bool(true) else { throw Self.error() }
        }
        if !bypassed {
            let expected = layers[0]["source"].text == "brother_persona_current_projection" ? "brother" : "legacy"
            guard value["persona_state"] == .string(expected),
                  memoryIDs.isEmpty || value["read_only_retrieval_performed"] == .bool(true) else { throw Self.error() }
        }
        let material = JSONValue.object(fields.filter { Self.materialFields.contains($0.key) })
        guard case .string(let materialText) = value["hash_material"],
              let bytes = materialText.data(using: .utf8), bytes.count <= 256 * 1024,
              (try? JSONDecoder().decode(JSONValue.self, from: bytes)) == material,
              value["projection_hash"] == .string(Self.hash(materialText)) else { throw Self.error() }
        self.value = value
    }

    private static func hash(_ text: String) -> String {
        SHA256.hash(data: Data(text.utf8)).map { String(format: "%02x", $0) }.joined()
    }

    private static func error() -> NativeError {
        .message(L10n.text("Локальные инструкции или их SHA-256 не прошли проверку. Ничего не отправлено."))
    }
}

struct NativeInstructionReceipt: Equatable {
    private static let fields: Set<String> = [
        "schema", "content_free", "instruction_text_stored", "assembled_for_provider_call",
        "provider_delivery_verified", "provider_owned_instructions_included", "private_reasoning_included",
        "scope", "provider", "mode", "persona_state", "selected_memory_count", "selected_memory_ids",
        "correction_hint_count", "layer_count", "layers", "receipt_hash", "hash_material",
    ]
    private static let materialFields = fields.subtracting(["schema", "receipt_hash", "hash_material"])
    private static let layerFields: Set<String> = [
        "id", "owner", "placement", "source", "characters", "sha256", "dynamic", "provider_visible_at_send",
    ]
    let value: JSONValue
    var layers: [JSONValue] { value["layers"].items }

    init(_ value: JSONValue) throws {
        guard case .object(let fields) = value, Set(fields.keys) == Self.fields,
              value["schema"] == .string("proto_mind.native_instruction_receipt.v1"),
              value["content_free"] == .bool(true), value["instruction_text_stored"] == .bool(false),
              value["assembled_for_provider_call"] == .bool(true), value["provider_delivery_verified"] == .bool(false),
              value["provider_owned_instructions_included"] == .bool(false), value["private_reasoning_included"] == .bool(false),
              value["scope"] == .string("proto_mind_authored_instruction_metadata"),
              ["codex", "ollama", "api", "claude"].contains(value["provider"].text), ["chat", "full_access"].contains(value["mode"].text),
              ["codex", "claude"].contains(value["provider"].text) || value["mode"].text == "chat",
              ["brother", "legacy"].contains(value["persona_state"].text),
              case .array(let memoryIDs) = value["selected_memory_ids"], memoryIDs.count <= 10,
              memoryIDs.allSatisfy({ !$0.text.isEmpty && $0.text.unicodeScalars.count <= 160 }),
              Set(memoryIDs.map(\.text)).count == memoryIDs.count,
              value["selected_memory_count"] == .number(Double(memoryIDs.count)),
              case .number(let correctionCount) = value["correction_hint_count"], correctionCount.rounded() == correctionCount,
              correctionCount >= 0, correctionCount <= 5,
              case .array(let layers) = value["layers"], (1...2).contains(layers.count),
              value["layer_count"] == .number(Double(layers.count)) else { throw Self.error() }
        for layer in layers {
            guard case .object(let body) = layer, Set(body.keys) == Self.layerFields,
                  layer["owner"] == .string("proto_mind"), layer["provider_visible_at_send"] == .bool(true),
                  case .bool = layer["dynamic"], case .number(let characters) = layer["characters"],
                  characters.rounded() == characters, characters >= 1, characters <= 24_512,
                  Self.isHash(layer["sha256"].text) else { throw Self.error() }
        }
        let identifiers = layers.map { $0["id"].text }
        if value["provider"] == .string("codex") {
            guard identifiers == ["base_instructions", "developer_instructions"],
                  layers[0]["placement"] == .string("codex_base_instructions"),
                  ["legacy_cognitive_core_current_projection", "brother_persona_current_projection"].contains(layers[0]["source"].text),
                  layers[0]["dynamic"] == .bool(true), layers[1]["placement"] == .string("codex_developer_instructions"),
                  layers[1]["source"] == .string(value["mode"].text == "full_access" ? "full_mac_static_contract" : "chat_static_contract"),
                  layers[1]["dynamic"] == .bool(false) else { throw Self.error() }
        } else {
            guard identifiers == ["system_instructions"], layers[0]["placement"] == .string(value["provider"].text + "_system_message"),
                  ["legacy_cognitive_core_current_projection", "brother_persona_current_projection"].contains(layers[0]["source"].text),
                  layers[0]["dynamic"] == .bool(true) else { throw Self.error() }
        }
        let expectedPersona = layers[0]["source"].text == "brother_persona_current_projection" ? "brother" : "legacy"
        guard value["persona_state"] == .string(expectedPersona) else { throw Self.error() }
        let material = JSONValue.object(fields.filter { Self.materialFields.contains($0.key) })
        guard case .string(let materialText) = value["hash_material"],
              let bytes = materialText.data(using: .utf8), bytes.count <= 64 * 1024,
              (try? JSONDecoder().decode(JSONValue.self, from: bytes)) == material,
              value["receipt_hash"] == .string(Self.hash(materialText)) else { throw Self.error() }
        self.value = value
    }

    private static func isHash(_ value: String) -> Bool {
        value.range(of: "^[a-f0-9]{64}$", options: .regularExpression) != nil
    }

    private static func hash(_ text: String) -> String {
        SHA256.hash(data: Data(text.utf8)).map { String(format: "%02x", $0) }.joined()
    }

    private static func error() -> NativeError {
        .message(L10n.text("Квитанция локальных инструкций не прошла проверку. Историческая запись не изменена."))
    }
}

struct NativeContextPreview: Equatable {
    let value: JSONValue
    let instructionPreview: NativeInstructionPreview
    var manifest: JSONValue { value["manifest"] }
    var sources: [JSONValue] { value["sources"].items }
    var imageSources: [JSONValue] { value["image_sources"].items }
    var pdfSources: [JSONValue] { value["pdf_sources"].items }

    init(_ value: JSONValue) throws {
        let claude = value["manifest"]["provider"].text == "claude"
        guard value["schema"].text == "proto_mind.native_context_preview.v1",
              value["read_only"] == .bool(true), value["no_execution"] == .bool(true),
              value["manifest"]["schema"].text == "proto_mind.native_context_manifest.v1",
              value["manifest"]["permission_granted"] == .bool(false),
              value["manifest"]["memory_scope"].text == "shared_core_not_workspace",
              NativeTaskCriteria.validContract(value["manifest"]["success_criteria"]),
              case .array(let sources) = value["sources"], sources.count <= 3,
              sources.allSatisfy({ ["ready", "changed", "unavailable"].contains($0["state"].text)
                  && $0["excerpt"].text.unicodeScalars.count <= 6000 && $0["expected_sha256"].text.count == 64 }),
              case .array(let history) = value["history"], history.count <= (claude ? 2000 : 12),
              history.allSatisfy({ ["user", "assistant"].contains($0["role"].text) && (claude || $0["content"].text.unicodeScalars.count <= 2000) }),
              !claude || history.reduce(0, { $0 + $1["content"].text.unicodeScalars.count }) <= 300_000 else {
            throw NativeError.message(L10n.text("Формат локального контекста не прошёл проверку. Ничего не отправлено."))
        }
        if !value["image_sources"].isNull {
            guard case .array(let images) = value["image_sources"], images.count <= 3,
                  images.allSatisfy({ ["ready", "changed", "unavailable", "over_limit"].contains($0["state"].text)
                      && $0["expected_sha256"].text.count == 64 && $0["data_base64"].isNull }) else {
                throw NativeError.message(L10n.text("Состав изображений не прошёл проверку."))
            }
            for image in images where image["state"].text == "ready" { _ = try NativeImageAttachment(image["image"]) }
        }
        if !value["manifest"]["images"].isNull {
            guard case .array = value["manifest"]["images"] else { throw NativeError.message(L10n.text("Неверный manifest изображений.")) }
            try NativeImageAttachment.validate(value["manifest"]["images"].items)
        }
        if !value["pdf_sources"].isNull {
            guard case .array(let pdfs) = value["pdf_sources"], pdfs.count <= 1,
                  pdfs.allSatisfy({ ["ready", "changed", "unavailable"].contains($0["state"].text)
                      && NativePDFAttachment.isHash($0["expected_sha256"]) }) else {
                throw NativeError.message(L10n.text("Состав PDF не прошёл проверку."))
            }
            for pdf in pdfs where pdf["state"].text == "ready" {
                _ = try NativePDFPreview(.object(["schema": .string("proto_mind.native_pdf_preview.v1"),
                    "read_only": .bool(true), "no_execution": .bool(true), "pdf": pdf["pdf"], "pages": pdf["pages"],
                    "has_text": .bool(true)]), conversationID: UUID(), workspace: nil, canAttach: false)
            }
        }
        if !value["manifest"]["pdfs"].isNull {
            guard case .array = value["manifest"]["pdfs"] else { throw NativeError.message(L10n.text("Неверный manifest PDF.")) }
            try NativePDFAttachment.validate(value["manifest"]["pdfs"].items)
        }
        let instructionPreview = try NativeInstructionPreview(value["instruction_preview"])
        try checkKnowledgeMetadata(value["manifest"]["knowledge_context"])
        try checkProjectMemorySources(value["project_memory_sources"], metadata: value["manifest"]["knowledge_context"])
        if !value["manifest"]["knowledge_context"]["project_recall"].isNull {
            let report = try NativeProjectRecallReport(value["manifest"]["knowledge_context"]["project_recall"])
            let workspace = report.value["workspace"].isNull ? JSONValue.null : report.value["workspace"]["path"]
            guard report.value["goal_sha256"] == value["manifest"]["input"]["sha256"],
                  report.value["access_mode"] == value["manifest"]["access_mode"], workspace == value["manifest"]["workspace"],
                  ["codex", "claude"].contains(value["manifest"]["provider"].text), !value["manifest"]["operator"].flag else { throw NativeProjectRecallReport.error() }
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
        self.instructionPreview = instructionPreview
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
            throw NativeError.message(L10n.text("Не удалось проверить происхождение результатов. Запуск не изменён."))
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
            throw NativeError.message(L10n.text("Файл не соответствует выбранному артефакту. Повторно откройте журнал."))
        }
        self.value = value
    }
}

struct ContextDeskView: View {
    @ObservedObject var model: AppModel
    var conversationID: UUID? = nil
    @WorkspaceDismiss private var dismiss
    @State private var scopedPreview: NativeContextPreview?
    @State private var scopedError: String?
    @State private var scopedLoading = false
    private var preview: NativeContextPreview? { conversationID == nil ? model.contextPreview : scopedPreview }
    private var error: String? { conversationID == nil ? model.contextPreviewError : scopedError }
    private var loading: Bool { conversationID == nil ? model.loadingContextPreview : scopedLoading }
    private var busy: Bool { model.operationBusy || (conversationID.map(model.isRunning) ?? model.busy) }
    private func refresh() async {
        guard let id = conversationID else { await model.refreshContextPreview(); return }
        guard !busy, !scopedLoading else { return }
        scopedLoading = true; scopedError = nil; scopedPreview = nil
        defer { scopedLoading = false }
        do {
            let state = model.execution(for: id)
            try await model.ensureAgentAccess(for: state)
            guard let params = model.contextRequestParameters(for: id) else { return }
            let result = try await state.client.request("context_preview", params)
            guard params == model.contextRequestParameters(for: id) else { throw NativeError.message(L10n.text("Состав запроса изменился. Обновите локальный просмотр.")) }
            let value = try NativeContextPreview(result)
            if !value.manifest["knowledge_context"]["project_recall"].isNull {
                let recall = try NativeProjectRecallReport(value.manifest["knowledge_context"]["project_recall"])
                guard params["auto_project_recall"] == .bool(true), params["project_memory"]?.items.isEmpty == true,
                      recall.matches(conversation: id, text: params["text"]!.text.trimmingCharacters(in: .whitespacesAndNewlines), workspace: params["workspace_root"]?.text, mode: params["access_mode"]!.text) else { throw NativeProjectRecallReport.error() }
            }
            scopedPreview = value
        } catch { scopedError = error.localizedDescription }
    }

    var body: some View {
        VStack(spacing: 0) {
            HStack {
                Label(L10n.text("Контекст перед отправкой"), systemImage: "doc.text.magnifyingglass").font(.title3.weight(.semibold))
                Spacer()
                if loading { ProgressView().controlSize(.small) }
                Button { Task { await refresh() } } label: { Image(systemName: "arrow.clockwise") }
                    .disabled(busy || loading).help(L10n.text("Перепроверить файлы локально"))
                Button { dismiss() } label: { Image(systemName: "xmark") }.keyboardShortcut(.cancelAction)
            }.padding(20)
            Divider()
            ScrollView {
                VStack(alignment: .leading, spacing: 20) {
                    if let error = error { Label(error, systemImage: "exclamationmark.triangle").foregroundStyle(.orange) }
                    if let preview = preview {
                        let manifest = preview.manifest
                        DeskSection(L10n.text("Куда пойдёт запрос"), icon: "arrow.up.circle") {
                            Text(destination(manifest["destination"].text)).font(.headline)
                            if manifest["destination"].text == "openai_cloud" {
                                Text(preview.value["cloud_consent"].flag
                                     ? L10n.text("Облачная обработка разрешена вами. Данные уйдут только после отдельной отправки сообщения.")
                                     : L10n.text("Облачная обработка не разрешена. Этот просмотр остаётся локальным и ничего не разрешает."))
                                    .foregroundStyle(.orange)
                            }
                            Text(L10n.format("Текст запроса: \(manifest["input"]["characters"].integer) символов. История: \(manifest["history"]["messages"].integer) сообщений, \(manifest["history"]["characters"].integer) символов."))
                            Text(L10n.format("Модель: \(manifest["requested_model"].text.isEmpty ? L10n.text("по умолчанию аккаунта/провайдера") : manifest["requested_model"].text). Это выбранные настройки, не подтверждение доступности модели."))
                                .font(.caption).foregroundStyle(.secondary)
                        }
                        if manifest["provider"].text == "codex" {
                            let thread = manifest["provider_thread"]
                            DeskSection(L10n.text("Сессия Codex"), icon: "link.circle") {
                                if !thread["workspace_matches"].flag {
                                    Text(L10n.text("Сохранённый thread относится к другой рабочей папке."))
                                        .fontWeight(.medium).foregroundStyle(.orange)
                                    Text(L10n.text("Отправка заблокирована до ручного начала новой сессии; автоматическое обновление инструкций не меняет привязку папки."))
                                        .font(.caption).foregroundStyle(.secondary)
                                } else if thread["linked"].flag {
                                    Text(L10n.format("Продолжится сохранённый thread · \(thread["thread_id_short"].text)"))
                                        .fontWeight(.medium)
                                    Text(L10n.text("Локальная история повторно не прикладывается. Историю provider thread этот preview не дублирует."))
                                        .font(.caption).foregroundStyle(.secondary)
                                } else if thread["refresh_required"].flag {
                                    Text(L10n.text("Статические инструкции режима обновились: будет создан свежий thread Codex."))
                                        .fontWeight(.medium).foregroundStyle(.orange)
                                    Text(L10n.text("До 12 показанных локальных реплик один раз восстановят continuity. Прежний rollout останется в приватном профиле как история."))
                                        .font(.caption).foregroundStyle(.secondary)
                                } else {
                                    Text(L10n.text("Следующее сообщение создаст новый постоянный thread Codex.")).fontWeight(.medium)
                                    Text(L10n.text("До 12 показанных локальных реплик будут использованы один раз для начального continuity."))
                                        .font(.caption).foregroundStyle(.secondary)
                                }
                            }
                        }
                        if manifest["provider"].text == "claude" {
                            let thread = manifest["provider_thread"]
                            DeskSection(L10n.pick("Сессия Claude", "Claude session"), icon: "link.circle") {
                                Text(thread["linked"].flag
                                     ? L10n.pick("Продолжится сохранённая сессия Claude с историей работы и инструментов.", "Claude will continue its saved conversation and tool history.")
                                     : L10n.pick("Начнётся новая сессия Claude с локальной перепиской, показанной выше.", "A new Claude session will start with the local conversation shown above."))
                                Text(L10n.pick("При продолжении переписка повторно не отправляется. История сессии Claude в этом просмотре не дублируется.", "Resuming does not resend the local conversation. This preview does not reproduce Claude's saved session history."))
                                    .font(.caption).foregroundStyle(.secondary)
                                if thread["bootstrap_partial"].flag {
                                    Text(L10n.pick("Старая переписка превышает объём начальной передачи. Пропуск раннего текста явно обозначен.", "The old conversation exceeds the initial transfer budget. Omitted earlier text is explicitly marked."))
                                        .font(.caption).foregroundStyle(.orange)
                                }
                            }
                        }
                        let instructions = preview.instructionPreview
                        DeskSection(L10n.text("Локальные инструкции Proto-Mind"), icon: "text.badge.checkmark") {
                            Text(L10n.format("Режим: \(instructionMode(instructions.value)) · Persona: \(personaLabel(instructions.value["persona_state"].text))"))
                                .fontWeight(.medium)
                            if instructions.layers.isEmpty {
                                Text(instructions.value["operator"].flag
                                     ? L10n.text("Операторская команда обходит reasoner: локальный provider prompt не создаётся.")
                                     : L10n.text("У Mock нет системного/developer envelope провайдера; Proto-Mind ничего не дорисовывает."))
                                    .foregroundStyle(.secondary)
                            }
                            ForEach(Array(instructions.layers.enumerated()), id: \.offset) { _, layer in
                                VStack(alignment: .leading, spacing: 7) {
                                    Text(instructionLayerTitle(layer["id"].text)).font(.headline)
                                    Text(L10n.format("Источник: \(instructionSourceLabel(layer["source"].text)) · \(instructionPlacementLabel(layer["placement"].text))"))
                                        .font(.caption).foregroundStyle(.secondary)
                                    Text(layer["dynamic"].flag ? L10n.text("Пересобирается из текущего локального состояния.") : L10n.text("Статический контракт выбранного режима."))
                                        .font(.caption).foregroundStyle(.secondary)
                                    hashLine(L10n.text("SHA-256 слоя"), layer["sha256"].text)
                                    DisclosureGroup(L10n.format("Точный локальный текст · \(layer["characters"].integer) символов")) {
                                        DeskPlainText(text: layer["text"].text)
                                    }
                                }.padding(.vertical, 5)
                            }
                            if instructions.value["read_only_retrieval_performed"].flag {
                                Text(L10n.format("Read-only retrieval: выбрано \(instructions.value["selected_memory_count"].integer) записей общей памяти; usage telemetry и запись не выполнялись."))
                                    .foregroundStyle(.secondary)
                            } else if !instructions.layers.isEmpty {
                                Text(L10n.text("Observer не запросил память для этого черновика; записей общей памяти в проекции: 0."))
                                    .foregroundStyle(.secondary)
                            }
                            if instructions.value["correction_hint_count"].integer > 0 {
                                Text(L10n.format("Активных подсказок прошлой самопроверки: \(instructions.value["correction_hint_count"].integer). Их точный текст виден внутри base/system слоя."))
                                    .foregroundStyle(.secondary)
                            }
                            Divider()
                            Text(instructions.value["provider_owned_instructions"]["reason"].text)
                                .font(.callout).foregroundStyle(.orange)
                            Text(L10n.text("Приватные рассуждения модели не включены. Это текущая локальная проекция; Send соберёт её заново после проверки Persona, памяти, режима и доступа."))
                                .font(.caption).foregroundStyle(.secondary)
                            hashLine(L10n.text("SHA-256 всей проекции"), instructions.value["projection_hash"].text)
                        }
                        DeskSection(L10n.text("Папка и память: разные области"), icon: "folder.badge.questionmark") {
                            Text(L10n.format("Файлы: \(manifest["workspace"].text.isEmpty ? L10n.text("рабочая папка не привязана") : manifest["workspace"].text)")).textSelection(.enabled)
                            Text(L10n.text("Память: общее ядро Proto-Mind, не отдельная память этой папки.")).fontWeight(.medium)
                            Text(manifest["memory_root"].text).font(.caption).foregroundStyle(.secondary).textSelection(.enabled)
                            Text(manifest["operator"].flag
                                 ? L10n.text("Операторский маршрут не получает вложения и историю модели. Саму команду здесь не выполняем.")
                                 : L10n.text("Текущая проекция Observer/памяти/исправлений показана в локальных инструкциях выше. Send вычислит её заново; фактический выбор после ответа остаётся доступен в инспекторе."))
                                .foregroundStyle(.secondary)
                            Text(L10n.format("Context Injection: \(injectionLabel(manifest["context_injection"]["state"].text)). Настройка не меняется."))
                            if manifest["access_mode"].text == "full_access" {
                                Text(model.computerUseAvailable
                                     ? L10n.text("Выбран полный доступ к Mac, интернету и экрану: инструменты могут прочитать другие файлы, использовать live Web Search и управлять видимыми приложениями. Этот список не ограничивает их права.")
                                     : L10n.text("Выбран полный доступ к Mac и интернету: инструменты могут прочитать другие файлы, использовать live Web Search и сеть. Computer Use недоступен. Этот список не ограничивает их права.")).foregroundStyle(.orange)
                            }
                        }
                        if !manifest["success_criteria"].isNull {
                            DeskSection(L10n.text("Критерии следующей задачи"), icon: "checklist") {
                                ForEach(Array(manifest["success_criteria"]["items"].items.enumerated()), id: \.offset) { index, item in
                                    Text("\(index + 1). \(item["text"].text)").textSelection(.enabled)
                                }
                                Text(L10n.text("Передаются выбранной модели при отправке, но не добавляют прав и не являются автоматически проверенными фактами."))
                                    .font(.caption).foregroundStyle(.secondary)
                            }
                        } else if preview.value["excluded_criterion_count"].integer > 0 {
                            Text(L10n.format("Критерии пропущены для операторской команды: \(preview.value["excluded_criterion_count"].integer). Они остаются в черновике."))
                                .foregroundStyle(.secondary)
                        }
                        if !preview.value["skill_task_source"].isNull {
                            DeskSection(L10n.text("Явно выбранный навык"), icon: "list.bullet.clipboard") {
                                SkillTaskContractView(value: preview.value["skill_task_source"])
                                Text(L10n.text("Это ориентир для следующего ручного Send. Проверка происхождения не оценивает качество выполнения и не выдаёт разрешений.")).font(.caption).foregroundStyle(.secondary)
                            }
                        }
                        if let report = try? NativeAutoSkillsReport(preview.value["auto_skills"]) {
                            DeskSection(L10n.text("Автоматические навыки"), icon: "square.stack.3d.up") {
                                AutoSkillsReportView(report: report)
                                Text(L10n.text("При отправке: один отдельный запрос выбранной Codex-модели на low, если поддерживается, иначе на усилии по умолчанию. Он получает задачу, до четырёх последних сообщений и краткий каталог. Основной ответ сохраняет выбранное вами усилие. Здесь облачного запроса нет.")).font(.caption).foregroundStyle(.secondary)
                            }
                        }
                        DeskSection(L10n.text("Заметки проекта"), icon: "brain") {
                            if let report = try? NativeProjectRecallReport(manifest["knowledge_context"]["project_recall"]) {
                                ProjectRecallReportView(report: report)
                            }
                            if !preview.value["project_memory_sources"].items.isEmpty {
                                Text(manifest["knowledge_context"]["automatic_recall"].flag ? L10n.text("Автоматически выбранные заметки") : L10n.text("Явно выбранная память проекта")).font(.headline)
                                ForEach(Array(preview.value["project_memory_sources"].items.enumerated()), id: \.offset) { _, note in
                                    Text("\(ProjectNote.title(note["kind"].text)) · \(note["id"].text.prefix(12))").fontWeight(.medium)
                                    Text(note["content"].text).textSelection(.enabled)
                                    Text(L10n.format("Основание оператора: \(note["basis"].text)")).font(.caption).foregroundStyle(.secondary)
                                }
                                Text(L10n.text("Утверждения оператора, не независимые факты. Этот выбор попадёт в следующий запрос; Send проверит источники заново. Старый контекст может оставаться в истории провайдера.")).font(.caption).foregroundStyle(.secondary)
                                Divider()
                            }
                            if preview.value["project_memory_sources"].items.isEmpty && manifest["knowledge_context"]["project_recall"].isNull { Text(L10n.text("Заметки не выбраны или пропущены для операторской команды.")).foregroundStyle(.secondary) }
                        }
                        DeskSection(L10n.format("Текстовые вложения · \(preview.sources.count)/3"), icon: "paperclip") {
                            if preview.sources.isEmpty {
                                Text(manifest["operator"].flag ? L10n.format("Вложения пропущены: \(preview.value["excluded_attachment_count"].integer).") : L10n.text("Файлы не выбраны. Папка целиком, экран и буфер обмена не прикладываются.")).foregroundStyle(.secondary)
                            }
                            ForEach(Array(preview.sources.enumerated()), id: \.offset) { _, source in
                                VStack(alignment: .leading, spacing: 8) {
                                    Label(source["path"].text, systemImage: source["state"].text == "ready" ? "doc.text" : "exclamationmark.triangle")
                                        .fontWeight(.medium).textSelection(.enabled)
                                    Text(sourceLabel(source)).foregroundStyle(source["state"].text == "ready" ? Color.secondary : .orange)
                                    hashLine(L10n.text("Выбранный SHA-256"), source["expected_sha256"].text)
                                    if !source["current_sha256"].text.isEmpty { hashLine(L10n.text("Текущий SHA-256"), source["current_sha256"].text) }
                                    if source["state"].text == "ready" {
                                        DisclosureGroup(L10n.format("Точный фрагмент вложения · \(source["included_chars"].integer) символов")) {
                                            DeskPlainText(text: source["excerpt"].text)
                                        }
                                    }
                                }.padding(.vertical, 6)
                            }
                            Text(L10n.text("До 6 000 символов из каждого UTF-8 файла. SHA-256 проверяется снова перед отправкой; новая версия не подставляется автоматически. Это не проверка секретов в тексте."))
                                .font(.caption).foregroundStyle(.secondary)
                        }
                        DeskSection(L10n.format("Изображения · \(preview.imageSources.count)/3"), icon: "photo.on.rectangle") {
                            if preview.imageSources.isEmpty {
                                Text(manifest["operator"].flag ? L10n.format("Изображения пропущены для команды: \(preview.value["excluded_image_count"].integer).") : L10n.text("Изображения не выбраны. Экран и фототека не читаются автоматически."))
                                    .foregroundStyle(.secondary)
                            }
                            ForEach(Array(preview.imageSources.enumerated()), id: \.offset) { _, source in
                                VStack(alignment: .leading, spacing: 5) {
                                    Text(source["path"].text).font(.callout).textSelection(.enabled)
                                    hashLine(L10n.text("Выбранный SHA-256"), source["expected_sha256"].text)
                                    if source["state"].text == "ready" {
                                        Text(L10n.format("Готово локально · \(source["image"]["width"].integer) × \(source["image"]["height"].integer) · \(source["image"]["size_bytes"].integer) байт")).foregroundStyle(.secondary)
                                    } else {
                                        Text(source["state"].text == "changed" ? L10n.text("Файл изменился. Просмотрите и выберите его повторно.") : L10n.text("Недоступно или превышен лимит. Ничего не отправлено.")).foregroundStyle(.orange)
                                    }
                                }.padding(.vertical, 5)
                            }
                            if !preview.imageSources.isEmpty { Text(model.imageDestinationNotice(for: conversationID ?? model.selectedID)).font(.callout).foregroundStyle(.secondary) }
                            Text(L10n.text("До 4 МиБ на файл и 8 МиБ суммарно. При Send проверяются SHA-256 и поддержка изображений моделью. Встроенные метаданные не удаляются. Старые картинки не пересылаются из истории."))
                                .font(.caption).foregroundStyle(.secondary)
                        }
                        DeskSection(L10n.text("PDF · выбранный текст"), icon: "doc.richtext") {
                            if preview.pdfSources.isEmpty {
                                Text(manifest["operator"].flag ? L10n.format("PDF пропущены для команды: \(preview.value["excluded_pdf_count"].integer).") : L10n.text("PDF не выбран.")).foregroundStyle(.secondary)
                            }
                            ForEach(Array(preview.pdfSources.enumerated()), id: \.offset) { _, pdf in
                                Text(pdf["path"].text).textSelection(.enabled)
                                hashLine(L10n.text("Выбранный SHA-256"), pdf["expected_sha256"].text)
                                if pdf["state"].text == "ready" {
                                    ForEach(Array(pdf["pages"].items.enumerated()), id: \.offset) { _, page in
                                        DisclosureGroup(L10n.format("Страница \(page["number"].integer) · \(page["included_chars"].integer) символов\(page["truncated"].flag ? L10n.text(" · обрезана") : "")")) {
                                            DeskPlainText(text: page["text"].text.isEmpty ? L10n.text("Нет текстового слоя.") : page["text"].text)
                                        }
                                    }
                                } else { Text(pdf["reason"].text).foregroundStyle(.orange) }
                            }
                            Text(L10n.text("Только выбранные страницы, не оригинал PDF. Без OCR и картинок. Перед отправкой проверяются SHA-256 документа и текста; предыдущие PDF не пересылаются из истории."))
                                .font(.caption).foregroundStyle(.secondary)
                        }
                        if !preview.value["history"].items.isEmpty {
                            DisclosureGroup(L10n.text("История, которая войдёт в запрос")) {
                                ForEach(Array(preview.value["history"].items.enumerated()), id: \.offset) { _, item in
                                    VStack(alignment: .leading, spacing: 6) {
                                        Text(item["role"].text == "user" ? L10n.text("Вы") : L10n.text("Ассистент")).font(.caption).foregroundStyle(.secondary)
                                        Text(item["content"].text).textSelection(.enabled)
                                    }.padding(.vertical, 8)
                                }
                            }
                        }
                        Text(L10n.text("Максимум 12 сообщений по 2 000 символов; отчёты, ошибки и журналы инструментов не повторяются как история. Mock не анализирует вложения. Локальные инструкции Proto-Mind показаны выше; скрытые инструкции провайдера и приватные рассуждения недоступны."))
                            .font(.caption).foregroundStyle(.secondary)
                    } else if !loading && error == nil {
                        Text(L10n.text("Откройте просмотр вне активного запроса.")).foregroundStyle(.secondary)
                    }
                }.padding(24).frame(maxWidth: .infinity, alignment: .leading)
            }
            Divider()
            HStack {
                Text(L10n.text("Только просмотр. Ни одного запроса модели, записи в память или нового разрешения.")).font(.caption).foregroundStyle(.secondary)
                Spacer()
                Button(L10n.text("К сообщению")) { dismiss() }
            }.padding(18)
        }.workspacePageSize(width: 850, height: 680).workspaceBackground(NativeTheme.canvas)
            .font(NativeTheme.interfaceFont).buttonStyle(.nativeHover).disclosureGroupStyle(NativeDisclosureStyle())
            .task { await refresh() }
    }

    private func destination(_ value: String) -> String {
        switch value {
        case "anthropic_cloud": return L10n.pick("Claude · облачная обработка Anthropic", "Claude · Anthropic cloud processing")
        case "openai_cloud": return L10n.text("Codex · облачная обработка OpenAI")
        case "ollama_loopback": return L10n.text("Ollama · на этом Mac")
        case "operator_local": return L10n.text("Операторская команда · без модели")
        default: return L10n.text("Mock · локальная диагностика без модели")
        }
    }

    private func injectionLabel(_ state: String) -> String {
        switch state { case "disabled", "default_disabled": return L10n.text("выключен"); case "enabled": return L10n.text("включён вручную"); default: return L10n.text("не удалось прочитать") }
    }

    private func instructionMode(_ value: JSONValue) -> String {
        switch value["mode"].text {
        case "full_access": return "Full Mac"
        case "operator": return L10n.text("операторский")
        default: return value["provider"].text == "ollama" ? L10n.text("локальный") : "Chat"
        }
    }

    private func personaLabel(_ value: String) -> String {
        switch value {
        case "brother": return "Brother"
        case "legacy": return "legacy cognitive core"
        default: return L10n.text("обход")
        }
    }

    private func instructionLayerTitle(_ value: String) -> String {
        switch value {
        case "developer_instructions": return L10n.text("Developer instructions режима")
        case "system_instructions": return "System instructions Ollama"
        default: return "Base instructions Proto-Mind"
        }
    }

    private func instructionSourceLabel(_ value: String) -> String {
        switch value {
        case "brother_persona_current_projection": return "Brother Persona"
        case "legacy_cognitive_core_current_projection": return "legacy cognitive core"
        case "full_mac_static_contract": return "Full Mac contract"
        default: return "Chat-only contract"
        }
    }

    private func instructionPlacementLabel(_ value: String) -> String {
        switch value {
        case "codex_developer_instructions": return "developerInstructions"
        case "ollama_system_message": return "system message"
        default: return "baseInstructions"
        }
    }

    private func sourceLabel(_ source: JSONValue) -> String {
        switch source["state"].text {
        case "ready": return source["truncated"].flag ? L10n.text("Совпадает с выбранной версией; будет отправлен только фрагмент.") : L10n.text("Совпадает с выбранной версией.")
        case "changed": return L10n.text("Файл изменился. Заново просмотрите и прикрепите его; отправка со старым SHA будет отклонена.")
        default: return L10n.text("Источник недоступен или исключён. Никакой замены и обходного чтения.")
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
                    Text(L10n.text("Файлы и проверка")).font(.title3.weight(.semibold))
                    Spacer()
                    if loading || previewLoading { ProgressView().controlSize(.small) }
                    Button { Task { await refresh() } } label: { Image(systemName: "arrow.clockwise") }
                        .help(L10n.text("Перечитать сведения о результате")).disabled(model.busy || loading)
                }
                if let error { Text(error).foregroundStyle(.orange).textSelection(.enabled) }
                if let desk {
                    DeskSection(L10n.text("Наблюдения, не обещание успеха"), icon: "checkmark.magnifyingglass") {
                        let checks = desk.value["verification"]
                        Text(L10n.format("Команды: \(checks["exit_zero"].integer) с exit 0, \(checks["exit_nonzero"].integer) с ошибкой, \(checks["unknown"].integer) без подтверждённого исхода."))
                        Text(desk.value["success_criteria"].isNull ? L10n.text("Критерии до запуска не задавались.") : L10n.format("Критериев до запуска: \(desk.value["success_criteria"]["items"].items.count). Их ручная оценка доступна на вкладке «Приёмка»."))
                            .foregroundStyle(.secondary)
                        Text(L10n.format("Автоматическая проверка достижения цели не выполнялась. \(NativeManualReview.label(checks["acceptance"].text))."))
                            .foregroundStyle(.secondary)
                        Text(L10n.text("Код 0 не доказывает запуск тестов или успешность всей задачи.")).font(.caption).foregroundStyle(.secondary)
                    }
                    DeskSection(L10n.format("Наблюдаемые файлы · \(desk.items.count)"), icon: "doc.on.doc") {
                        if !desk.value["captured_at"].text.isEmpty {
                            Text(L10n.format("Чтение SHA при завершении: \(desk.value["captured_at"].text)")).font(.caption).foregroundStyle(.secondary)
                        }
                        if desk.items.isEmpty { Text(L10n.text("Изменений через file-change события не наблюдалось. Файлы, созданные через shell без таких событий, автоматически не ищем.")).foregroundStyle(.secondary) }
                        ForEach(Array(desk.items.enumerated()), id: \.offset) { _, item in
                            Button { Task { await select(item["id"].text) } } label: {
                                HStack(alignment: .top) {
                                    Image(systemName: "doc.text")
                                    VStack(alignment: .leading, spacing: 4) {
                                        Text(item["reported_path"].text).lineLimit(2)
                                        Text(item["state"].text == "captured" ? L10n.text("SHA сохранён при завершении ответа") : L10n.text("Историческая версия не зафиксирована"))
                                            .font(.caption).foregroundStyle(.secondary)
                                    }
                                    Spacer()
                                    Image(systemName: "chevron.right").font(.caption)
                                }.padding(10).background(selectedID == item["id"].text ? NativeTheme.selection : .clear, in: RoundedRectangle(cornerRadius: 8))
                            }.disabled(model.busy)
                        }
                        if desk.value["partial"].flag { Text(L10n.text("Показаны первые 24 артефакта; журнал ограничен.")).foregroundStyle(.orange) }
                    }
                    if let preview { artifact(preview.value) }
                    if !desk.value["commands"].items.isEmpty {
                        DisclosureGroup(L10n.text("Команды и сохранённый вывод")) {
                            ForEach(Array(desk.value["commands"].items.enumerated()), id: \.offset) { _, item in AgentToolRow(item: item) }
                        }
                    }
                    if !desk.value["answer_preview"].text.isEmpty {
                        DisclosureGroup(L10n.text("Ответ модели · не результат независимой проверки")) {
                            Text(desk.value["answer_preview"].text).textSelection(.enabled)
                        }
                    }
                    if !desk.value["context_manifest"].isNull {
                        let manifest = desk.value["context_manifest"]
                        DisclosureGroup(L10n.text("Состав запроса при отправке")) {
                            Text(L10n.format("\(manifest["provider"].text) · \(manifest["input"]["characters"].integer) символов ввода · история: \(manifest["history"]["messages"].integer) сообщений"))
                            Text(L10n.text("Память общего ядра, не память папки. Manifest не содержит полного текста запроса, истории или скрытых prompts.")).font(.caption).foregroundStyle(.secondary)
                            ForEach(Array(manifest["knowledge_context"]["project_memory"].items.enumerated()), id: \.offset) { _, note in
                                Text(L10n.format("Заметка проекта: \(note["id"].text.prefix(12)) · SHA \(note["record_hash"].text.prefix(12)) · утверждение оператора"))
                                    .font(.caption).textSelection(.enabled)
                            }
                            ForEach(Array(manifest["files"].items.enumerated()), id: \.offset) { _, source in
                                Text(L10n.format("\(source["path"].text) · \(source["included_chars"].integer) символов · SHA \(source["sha256"].text.prefix(12))")).font(.caption).textSelection(.enabled)
                            }
                            ForEach(Array(manifest["images"].items.enumerated()), id: \.offset) { _, image in
                                Text(L10n.format("Изображение: \(image["name"].text) · \(image["width"].integer) × \(image["height"].integer) · SHA \(image["sha256"].text.prefix(12))"))
                                    .font(.caption).textSelection(.enabled)
                            }
                            if !manifest["images"].items.isEmpty {
                                Text(L10n.text("Сохранены только метаданные изображений, не их байты. Они не прикладываются повторно при продолжении.")).font(.caption).foregroundStyle(.secondary)
                            }
                        }
                    }
                    Text("Run: \(run.id)").font(.caption.monospaced()).foregroundStyle(.secondary).textSelection(.enabled)
                    Text(L10n.text("Только локальный текстовый просмотр. HTML и скрипты не исполняются. Исходники не копируются, не восстанавливаются и не прикладываются к новому запросу."))
                        .font(.caption).foregroundStyle(.secondary)
                }
            }.padding(22).frame(maxWidth: .infinity, alignment: .leading)
        }.task { await refresh() }
    }

    @ViewBuilder
    private func artifact(_ value: JSONValue) -> some View {
        DeskSection(L10n.text("Просмотр выбранного результата"), icon: "doc.text.magnifyingglass") {
            Text(value["artifact"]["reported_path"].text).fontWeight(.medium).textSelection(.enabled)
            Text(L10n.format("Событие: \(value["artifact"]["tool_id"].text) · текстовый просмотр"))
                .font(.caption).foregroundStyle(.secondary).textSelection(.enabled)
            Text(artifactState(value["state"].text)).foregroundStyle(value["state"].text == "current" ? Color.secondary : .orange)
            hashLine(L10n.text("SHA при завершении"), value["artifact"]["sha256"].text)
            hashLine(L10n.text("Текущий SHA"), value["current"]["sha256"].text)
            hashLine(L10n.text("Исходное вложение"), value["artifact"]["original_sha256"].text)
            Text(L10n.text("SHA исходного вложения известен только если этот же файл был прикреплён до работы. Копия прежнего содержимого не хранится; восстановление не предлагается."))
                .font(.caption).foregroundStyle(.secondary)
            if !value["diff_preview"].text.isEmpty {
                DisclosureGroup(L10n.text("Сохранённый diff · фрагмент всего события инструмента")) {
                    DeskPlainText(text: value["diff_preview"].text)
                }
            }
            if !value["current"].isNull {
                DisclosureGroup(L10n.text("Текущий файл на диске · до 12 000 символов")) {
                    DeskPlainText(text: value["current"]["preview"].text)
                }
            }
            Button(L10n.text("Проверить этот файл ещё раз")) { Task { await select(value["artifact"]["id"].text) } }
                .disabled(model.busy || previewLoading)
        }
    }

    private func artifactState(_ state: String) -> String {
        switch state {
        case "current": return L10n.text("Файл сейчас совпадает с SHA, прочитанным при завершении ответа. Это не доказательство исключительного авторства агента.")
        case "changed": return L10n.text("Файл изменился после завершения. Ниже текущая версия, а не сохранённый результат того запуска.")
        case "not_captured": return L10n.text("Для этого запуска нет исторического SHA. Ниже только текущий файл; его нельзя считать проверенным результатом прошлого запуска.")
        default: return L10n.text("Файл недоступен, вне выбранной папки или не поддерживается. Сохранённое наблюдение не доказывает наличие файла сейчас.")
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
    Text("\(title): \(hash.isEmpty ? L10n.text("не зафиксирован") : hash)")
        .font(.caption.monospaced()).foregroundStyle(.secondary).textSelection(.enabled)
}
