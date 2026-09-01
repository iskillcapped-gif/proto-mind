import SwiftUI

struct NativePersonaPreview: Equatable {
    static let fields: Set<String> = [
        "schema", "read_only", "no_execution", "no_model_call", "no_network_call",
        "no_retrieval", "no_store_write", "production_prompt_active",
        "private_reasoning_included", "context_injection_changed",
        "context_injection_state", "snapshot", "rendered_preview", "source_summary", "notices"
    ]
    static let snapshotFields: Set<String> = [
        "schema", "generated_at", "kernel", "identity", "communication_preferences",
        "relevant_memories", "task", "self_model", "notices", "omitted_memory_count",
        "omitted_identity_item_count", "read_only", "authorizes_actions",
        "context_injection_changed", "snapshot_hash"
    ]
    static let kernelFields: Set<String> = [
        "schema", "persona_id", "version", "display_name", "role", "default_language",
        "core_laws", "voice", "boundaries"
    ]
    static let voiceFields: Set<String> = ["tone", "preferred_address", "humor", "emoji", "adaptation"]
    static let identityFields: Set<String> = [
        "source", "source_version", "source_updated_at", "product_name", "product_role",
        "style", "mission", "items"
    ]
    static let identityItemFields: Set<String> = ["item_id", "kind", "text"]
    static let taskFields: Set<String> = ["kind", "risk", "goal_id", "task_id", "workspace_id"]
    static let runtimeFields: Set<String> = [
        "provider", "model", "access_mode", "workspace_id", "workspace_label", "network_state",
        "tools", "can_write_workspace", "can_control_computer", "can_use_web", "authorization_source"
    ]
    static let sourceFields: Set<String> = [
        "kernel", "identity", "memory", "runtime", "workspace", "full_access_grant_verified"
    ]

    let value: JSONValue
    var snapshot: JSONValue { value["snapshot"] }
    var kernel: JSONValue { snapshot["kernel"] }
    var identity: JSONValue { snapshot["identity"] }
    var runtime: JSONValue { snapshot["self_model"] }
    var notices: [JSONValue] { value["notices"].items }

    init(_ value: JSONValue) throws {
        guard case .object(let root) = value, Set(root.keys) == Self.fields,
              value["schema"] == .string("proto_mind.native_persona_preview.v1"),
              value["read_only"] == .bool(true), value["no_execution"] == .bool(true),
              value["no_model_call"] == .bool(true), value["no_network_call"] == .bool(true),
              value["no_retrieval"] == .bool(true), value["no_store_write"] == .bool(true),
              value["production_prompt_active"] == .bool(false),
              value["private_reasoning_included"] == .bool(false),
              value["context_injection_changed"] == .bool(false),
              ["enabled", "disabled", "default_disabled", "unknown"].contains(value["context_injection_state"].text),
              case .object(let snapshot) = value["snapshot"], Set(snapshot.keys) == Self.snapshotFields,
              value["snapshot"]["schema"] == .string("proto_mind.persona_snapshot.v1"),
              value["snapshot"]["read_only"] == .bool(true),
              value["snapshot"]["authorizes_actions"] == .bool(false),
              value["snapshot"]["context_injection_changed"] == .bool(false),
              Self.isHash(value["snapshot"]["snapshot_hash"].text),
              value["rendered_preview"].text.unicodeScalars.count <= 16_000,
              value["rendered_preview"].text.contains(value["snapshot"]["snapshot_hash"].text),
              case .array(let snapshotNotices) = value["snapshot"]["notices"], snapshotNotices.count <= 32,
              snapshotNotices.allSatisfy({ Self.validText($0.text, maximum: 400) }),
              value["snapshot"]["omitted_memory_count"] == .number(0),
              value["snapshot"]["communication_preferences"] == .array([]),
              value["snapshot"]["relevant_memories"] == .array([]) else {
            throw NativeError.message("PersonaSnapshot не прошёл локальную проверку. Ничего не применено.")
        }

        let kernel = value["snapshot"]["kernel"]
        guard case .object(let kernelObject) = kernel, Set(kernelObject.keys) == Self.kernelFields,
              kernel["schema"] == .string("proto_mind.persona_kernel.v1"),
              kernel["persona_id"] == .string("brother"), kernel["display_name"] == .string("Brother"),
              Self.validText(kernel["version"].text, maximum: 32),
              Self.validText(kernel["role"].text, maximum: 400),
              Self.validText(kernel["default_language"].text, maximum: 64),
              case .array(let laws) = kernel["core_laws"], (4...16).contains(laws.count),
              laws.allSatisfy({ Self.validText($0.text, maximum: 400) }),
              case .array(let boundaries) = kernel["boundaries"], (3...16).contains(boundaries.count),
              boundaries.allSatisfy({ Self.validText($0.text, maximum: 400) }),
              case .object(let voice) = kernel["voice"], Set(voice.keys) == Self.voiceFields,
              kernel["voice"]["adaptation"] == .string("contextual_without_modes") else {
            throw NativeError.message("Brother Kernel имеет неожиданный формат. Ничего не применено.")
        }

        let identity = value["snapshot"]["identity"]
        guard case .object(let identityObject) = identity, Set(identityObject.keys) == Self.identityFields,
              identity["source"] == .string("identity.json"),
              case .array(let identityItems) = identity["items"], identityItems.count <= 36,
              identityItems.allSatisfy({ item in
                  guard case .object(let object) = item else { return false }
                  return Set(object.keys) == Self.identityItemFields
                      && ["value", "principle", "boundary"].contains(item["kind"].text)
                      && Self.validText(item["item_id"].text, maximum: 120)
                      && Self.validText(item["text"].text, maximum: 400)
              }) else {
            throw NativeError.message("Identity projection имеет неожиданный формат. Ничего не применено.")
        }

        let task = value["snapshot"]["task"], runtime = value["snapshot"]["self_model"]
        guard case .object(let taskObject) = task, Set(taskObject.keys) == Self.taskFields,
              task["workspace_id"] == runtime["workspace_id"],
              case .object(let runtimeObject) = runtime, Set(runtimeObject.keys) == Self.runtimeFields,
              ["codex_subscription", "ollama", "mock"].contains(runtime["provider"].text),
              ["chat", "full_access", "local", "mock"].contains(runtime["access_mode"].text),
              ["disabled", "local_only", "available"].contains(runtime["network_state"].text),
              case .array(let tools) = runtime["tools"], tools.count <= 32,
              tools.allSatisfy({ Self.validIdentifier($0.text) }), Set(tools.map(\.text)).count == tools.count,
              Self.validWorkspace(runtime["workspace_id"].text),
              Self.validText(runtime["workspace_label"].text, maximum: 120),
              Self.validText(runtime["model"].text, maximum: 160) else {
            throw NativeError.message("Self-model не прошёл проверку полномочий. Ничего не применено.")
        }

        let access = runtime["access_mode"].text
        let toolNames = Set(tools.map(\.text))
        let canWrite = runtime["can_write_workspace"] == .bool(true)
        let canControl = runtime["can_control_computer"] == .bool(true)
        let canWeb = runtime["can_use_web"] == .bool(true)
        let verified = value["source_summary"]["full_access_grant_verified"] == .bool(true)
        guard (access != "chat" || (tools.isEmpty && !canWrite && !canControl && !canWeb
                    && runtime["authorization_source"] == .string("none"))),
              (access != "full_access" || (verified
                    && runtime["authorization_source"] == .string("operator_explicit_turn_grant")
                    && canWrite && canWeb && toolNames.contains("shell_and_files") && toolNames.contains("web_search")
                    && canControl == toolNames.contains("computer_use"))),
              (access != "local" || (runtime["authorization_source"] == .string("local_runtime")
                    && tools.isEmpty && !canWrite && !canControl && !canWeb)),
              (access != "mock" || (runtime["authorization_source"] == .string("none")
                    && tools.isEmpty && !canWrite && !canControl && !canWeb)),
              verified == (access == "full_access") else {
            throw NativeError.message("Persona self-model попытался расширить текущие полномочия. Ничего не применено.")
        }

        guard case .object(let sources) = value["source_summary"], Set(sources.keys) == Self.sourceFields,
              value["source_summary"]["kernel"] == .string("checked_in_versioned"),
              value["source_summary"]["identity"] == .string("private_read_only"),
              value["source_summary"]["memory"] == .string("none_selected_no_retrieval"),
              value["source_summary"]["runtime"] == .string("current_native_controls"),
              value["source_summary"]["workspace"] == .string("opaque_reference_only"),
              case .array(let notices) = value["notices"], (4...8).contains(notices.count),
              notices.allSatisfy({ Self.validText($0.text, maximum: 400) }) else {
            throw NativeError.message("Источники PersonaSnapshot не прошли проверку. Ничего не применено.")
        }
        self.value = value
    }

    private static func validText(_ value: String, maximum: Int) -> Bool {
        !value.isEmpty && value.unicodeScalars.count <= maximum && !value.contains("\0")
    }

    private static func validIdentifier(_ value: String) -> Bool {
        validText(value, maximum: 64) && value.allSatisfy { $0.isLowercase || $0.isNumber || $0 == "_" || $0 == "-" }
    }

    private static func validWorkspace(_ value: String) -> Bool {
        value == "unbound" || (value.hasPrefix("workspace_") && value.count == 26
            && value.dropFirst(10).allSatisfy { "0123456789abcdef".contains($0) })
    }

    private static func isHash(_ value: String) -> Bool {
        value.count == 64 && value.allSatisfy { "0123456789abcdef".contains($0) }
    }
}

struct NativePersonaReadiness: Equatable {
    static let fields: Set<String> = [
        "schema", "status", "selected_provider", "selected_adapter_ready", "read_only",
        "activation_performed", "no_model_call", "no_network_call", "no_retrieval",
        "no_store_write", "context_injection_changed", "context_injection_state",
        "adapters", "parity", "gates", "blockers", "warnings", "activation_fingerprint", "report_hash"
    ]
    static let adapterFields: Set<String> = [
        "provider", "model", "access_mode", "adapter", "placement", "refresh_scope",
        "provider_safety_boundary", "activation_supported", "snapshot_hash",
        "persona_invariant_hash", "runtime_hash", "prompt_context_hash",
        "prompt_context_chars", "provenance_complete"
    ]
    static let parityFields: Set<String> = [
        "checked_providers", "activation_providers", "persona_invariant_hash",
        "kernel_equal", "identity_equal", "memory_equal", "task_equal",
        "runtime_differences_expected", "mock_control_only"
    ]
    static let gateFields: Set<String> = ["id", "status", "detail"]
    static let providers = ["codex_subscription", "ollama", "mock"]

    let value: JSONValue
    var status: String { value["status"].text }
    var adapters: [JSONValue] { value["adapters"].items }
    var gates: [JSONValue] { value["gates"].items }
    var blockers: [JSONValue] { value["blockers"].items }
    var warnings: [JSONValue] { value["warnings"].items }
    var parity: JSONValue { value["parity"] }

    init(_ value: JSONValue) throws {
        guard case .object(let root) = value, Set(root.keys) == Self.fields,
              value["schema"] == .string("proto_mind.persona_activation_readiness.v1"),
              ["READY", "WARN", "NOT_READY"].contains(value["status"].text),
              Self.providers.contains(value["selected_provider"].text),
              value["read_only"] == .bool(true), value["activation_performed"] == .bool(false),
              value["no_model_call"] == .bool(true), value["no_network_call"] == .bool(true),
              value["no_retrieval"] == .bool(true), value["no_store_write"] == .bool(true),
              value["context_injection_changed"] == .bool(false),
              ["enabled", "disabled", "default_disabled", "unknown"].contains(value["context_injection_state"].text),
              Self.isHash(value["activation_fingerprint"].text), Self.isHash(value["report_hash"].text),
              case .array(let adapters) = value["adapters"], adapters.count == Self.providers.count else {
            throw NativeError.message("Persona readiness не прошёл локальную проверку. Ничего не активировано.")
        }
        for (provider, adapter) in zip(Self.providers, adapters) {
            let contract: (adapter: String, placement: String, refresh: String, safety: String, access: Set<String>) = {
                switch provider {
                case "codex_subscription":
                    return ("codex_base_instructions", "base_instructions", "thread_start_or_resume",
                            "developer_instructions_separate", ["chat", "full_access"])
                case "ollama":
                    return ("ollama_system_message", "system_message", "every_request",
                            "loopback_transport_separate", ["local"])
                default:
                    return ("mock_control_only", "no_model_prompt", "not_applicable",
                            "deterministic_control_no_activation", ["mock"])
                }
            }()
            guard case .object(let object) = adapter, Set(object.keys) == Self.adapterFields,
                  adapter["provider"] == .string(provider),
                  Self.validText(adapter["model"].text, maximum: 160),
                  contract.access.contains(adapter["access_mode"].text),
                  adapter["adapter"] == .string(contract.adapter),
                  adapter["placement"] == .string(contract.placement),
                  adapter["refresh_scope"] == .string(contract.refresh),
                  adapter["provider_safety_boundary"] == .string(contract.safety),
                  Self.isHash(adapter["snapshot_hash"].text),
                  Self.isHash(adapter["persona_invariant_hash"].text),
                  Self.isHash(adapter["runtime_hash"].text),
                  Self.isHash(adapter["prompt_context_hash"].text),
                  (1...16_000).contains(adapter["prompt_context_chars"].integer),
                  adapter["provenance_complete"] == .bool(true) else {
                throw NativeError.message("Persona adapter evidence имеет неожиданный формат. Ничего не активировано.")
            }
            if provider == "mock" {
                guard adapter["activation_supported"] == .bool(false),
                      adapter["placement"] == .string("no_model_prompt") else {
                    throw NativeError.message("Mock не может стать production Persona adapter.")
                }
            } else {
                guard adapter["activation_supported"] == .bool(true) else {
                    throw NativeError.message("Production Persona adapter не подтвердил готовность.")
                }
            }
        }
        let selected = value["selected_provider"].text
        guard value["selected_adapter_ready"] == .bool(selected != "mock"),
              case .object(let parity) = value["parity"], Set(parity.keys) == Self.parityFields,
              value["parity"]["checked_providers"].items.map(\.text) == Self.providers,
              value["parity"]["activation_providers"].items.map(\.text) == ["codex_subscription", "ollama"],
              value["parity"]["runtime_differences_expected"] == .bool(true),
              value["parity"]["mock_control_only"] == .bool(true),
              value["parity"]["persona_invariant_hash"].text.isEmpty
                || Self.isHash(value["parity"]["persona_invariant_hash"].text),
              case .array(let gates) = value["gates"], gates.count == 9 else {
            throw NativeError.message("Provider parity evidence имеет неожиданный формат. Ничего не активировано.")
        }
        var gateIDs = Set<String>()
        for gate in gates {
            guard case .object(let object) = gate, Set(object.keys) == Self.gateFields,
                  Self.validText(gate["id"].text, maximum: 80),
                  Self.validText(gate["detail"].text, maximum: 400),
                  ["PASS", "WARN", "FAIL"].contains(gate["status"].text),
                  gateIDs.insert(gate["id"].text).inserted else {
                throw NativeError.message("Persona activation gate имеет неожиданный формат. Ничего не активировано.")
            }
        }
        guard case .array(let blockers) = value["blockers"], blockers.count <= 16,
              blockers.allSatisfy({ Self.validText($0.text, maximum: 400) }),
              case .array(let warnings) = value["warnings"], warnings.count <= 16,
              warnings.allSatisfy({ Self.validText($0.text, maximum: 400) }) else {
            throw NativeError.message("Persona readiness findings имеют неожиданный формат. Ничего не активировано.")
        }
        let expectedStatus = blockers.isEmpty ? (warnings.isEmpty ? "READY" : "WARN") : "NOT_READY"
        guard value["status"] == .string(expectedStatus) else {
            throw NativeError.message("Persona readiness status не совпадает с gates. Ничего не активировано.")
        }
        self.value = value
    }

    private static func validText(_ value: String, maximum: Int) -> Bool {
        !value.isEmpty && value.unicodeScalars.count <= maximum && !value.contains("\0")
    }

    private static func isHash(_ value: String) -> Bool {
        value.count == 64 && value.allSatisfy { "0123456789abcdef".contains($0) }
    }
}

struct NativePersonaTurnReceipt: Equatable {
    static let fields: Set<String> = [
        "schema", "active", "activated_at", "persona_id", "persona_version",
        "provider", "model", "access_mode", "adapter", "placement",
        "snapshot_hash", "persona_invariant_hash", "runtime_hash", "prompt_context_hash",
        "legacy_prompt_hash", "active_prompt_hash", "readiness_hash",
        "selected_memory_count", "selected_memory_ids", "memory_provenance",
        "provider_safety_preserved", "no_added_authority", "context_injection_state",
        "context_injection_changed", "additional_model_calls", "additional_retrieval_calls",
        "store_writes_by_activation", "rollback_path", "private_reasoning_included", "receipt_hash"
    ]
    static let memoryFields: Set<String> = [
        "record_id", "provenance_id", "provenance_status", "source", "content_hash"
    ]

    let value: JSONValue
    var snapshotHash: String { value["snapshot_hash"].text }
    var receiptHash: String { value["receipt_hash"].text }
    var selectedMemoryCount: Int { value["selected_memory_count"].integer }

    init(_ value: JSONValue) throws {
        guard case .object(let root) = value, Set(root.keys) == Self.fields,
              value["schema"] == .string("proto_mind.persona_turn_activation.v1"),
              value["active"] == .bool(true), value["persona_id"] == .string("brother"),
              Self.validText(value["activated_at"].text, maximum: 80),
              Self.validText(value["persona_version"].text, maximum: 32),
              ["codex_subscription", "ollama"].contains(value["provider"].text),
              Self.validText(value["model"].text, maximum: 160),
              ["chat", "full_access", "local"].contains(value["access_mode"].text),
              ["disabled", "default_disabled"].contains(value["context_injection_state"].text),
              value["provider_safety_preserved"] == .bool(true),
              value["no_added_authority"] == .bool(true),
              value["context_injection_changed"] == .bool(false),
              value["private_reasoning_included"] == .bool(false),
              value["additional_model_calls"] == .number(0),
              value["additional_retrieval_calls"] == .number(0),
              value["store_writes_by_activation"] == .number(0),
              value["rollback_path"] == .string("legacy_prompt_next_turn") else {
            throw NativeError.message("Persona turn receipt имеет неожиданный или небезопасный формат.")
        }
        let adapter = value["provider"].text == "codex_subscription"
            ? ("codex_base_instructions", "base_instructions")
            : ("ollama_system_message", "system_message")
        guard value["adapter"] == .string(adapter.0), value["placement"] == .string(adapter.1),
              value["provider"].text != "codex_subscription" || ["chat", "full_access"].contains(value["access_mode"].text),
              value["provider"].text != "ollama" || value["access_mode"] == .string("local") else {
            throw NativeError.message("Persona receipt не совпадает с выбранным provider adapter.")
        }
        for field in [
            "snapshot_hash", "persona_invariant_hash", "runtime_hash", "prompt_context_hash",
            "legacy_prompt_hash", "active_prompt_hash", "readiness_hash", "receipt_hash"
        ] where !Self.isHash(value[field].text) {
            throw NativeError.message("Persona receipt содержит неверный SHA-256.")
        }
        let ids = value["selected_memory_ids"].items
        let provenance = value["memory_provenance"].items
        guard value["selected_memory_count"].integer == ids.count,
              ids.count == provenance.count, ids.count <= 8,
              Set(ids.map(\.text)).count == ids.count,
              ids.allSatisfy({ Self.validText($0.text, maximum: 160) }) else {
            throw NativeError.message("Persona receipt содержит неверную сводку выбранной памяти.")
        }
        for (identifier, item) in zip(ids, provenance) {
            guard case .object(let record) = item, Set(record.keys) == Self.memoryFields,
                  item["record_id"] == identifier,
                  Self.validText(item["provenance_id"].text, maximum: 160),
                  Self.validText(item["source"].text, maximum: 160),
                  ["verified", "record_source_only"].contains(item["provenance_status"].text),
                  Self.isHash(item["content_hash"].text) else {
                throw NativeError.message("Persona receipt memory provenance не прошёл локальную проверку.")
            }
        }
        self.value = value
    }

    private static func validText(_ value: String, maximum: Int) -> Bool {
        !value.isEmpty && value.unicodeScalars.count <= maximum && !value.contains("\0")
    }

    private static func isHash(_ value: String) -> Bool {
        value.count == 64 && value.allSatisfy { "0123456789abcdef".contains($0) }
    }
}

struct PersonaInspectorView: View {
    @ObservedObject var model: AppModel

    var body: some View {
        VStack(spacing: 0) {
            HStack(spacing: 12) {
                Label("Persona Inspector", systemImage: "person.crop.circle.badge.checkmark")
                    .font(.title3.weight(.semibold))
                Spacer()
                if model.loadingPersonaPreview || model.loadingPersonaReadiness { ProgressView().controlSize(.small) }
                Button { Task { await model.refreshPersonaInspector() } } label: { Image(systemName: "arrow.clockwise") }
                    .disabled(model.busy || model.loadingPersonaPreview || model.loadingPersonaReadiness)
                    .help("Пересобрать read-only snapshot и readiness evidence")
                Button { model.showPersonaInspector = false } label: { Image(systemName: "xmark") }
                    .keyboardShortcut(.cancelAction)
            }.padding(20)
            Divider()
            ScrollView {
                VStack(alignment: .leading, spacing: 18) {
                    PersonaSection("Production state", icon: "switch.2") {
                        HStack(spacing: 8) {
                            Circle().fill(model.personaEnabled ? Color.green : Color.secondary).frame(width: 8, height: 8)
                            headline(model.personaEnabled ? "Brother Persona включена" : "Legacy prompt активен")
                            Spacer()
                            if model.personaEnabled {
                                Button("Rollback") { model.disablePersona() }.disabled(model.busy)
                            }
                        }
                        Text(model.personaEnabled
                             ? "Каждый Send повторно проверяет readiness. Rollback возвращает точный legacy prompt на следующем ходе и не стирает историю provider thread."
                             : "Snapshot/readiness доступны для проверки, но production prompt не меняется без явного opt-in в настройках моделей.")
                            .font(.caption).foregroundStyle(.secondary)
                        if let receipt = model.lastPersonaTurnReceipt {
                            fact("Последний snapshot", String(receipt.snapshotHash.prefix(16)))
                            fact("Память", "\(receipt.selectedMemoryCount) выбранных записей")
                            fact("Receipt SHA", String(receipt.receiptHash.prefix(16)))
                        }
                    }
                    if let error = model.personaPreviewError {
                        Label(error, systemImage: "exclamationmark.triangle").foregroundStyle(.orange)
                    }
                    if let error = model.personaReadinessError {
                        Label(error, systemImage: "exclamationmark.triangle").foregroundStyle(.orange)
                    }
                    if let preview = model.personaPreview {
                        PersonaSection("Brother Kernel", icon: "person.crop.circle") {
                            headline("\(preview.kernel["display_name"].text) · \(preview.kernel["version"].text)")
                            fact("Роль", preview.kernel["role"].text)
                            fact("Язык", preview.kernel["default_language"].text)
                            fact("Тон", preview.kernel["voice"]["tone"].text)
                            fact("Обращение", preview.kernel["voice"]["preferred_address"].text)
                            fact("Адаптация", "Контекстная, без режимов и крутилок личности")
                        }
                        PersonaSection("Identity projection", icon: "checkmark.seal") {
                            fact("Продукт", preview.identity["product_name"].text.isEmpty ? "не указан" : preview.identity["product_name"].text)
                            fact("Роль", preview.identity["product_role"].text.isEmpty ? "не указана" : preview.identity["product_role"].text)
                            fact("Стиль", preview.identity["style"].text.isEmpty ? "не указан" : preview.identity["style"].text)
                            fact("Миссия", preview.identity["mission"].text.isEmpty ? "не указана" : preview.identity["mission"].text)
                            ForEach(Array(preview.identity["items"].items.enumerated()), id: \.offset) { _, item in
                                Text("\(identityLabel(item["kind"].text)) [\(item["item_id"].text)]: \(item["text"].text)")
                                    .font(.callout).textSelection(.enabled)
                            }
                        }
                        PersonaSection("Текущий self-model", icon: "gauge.with.dots.needle.67percent") {
                            fact("Провайдер", preview.runtime["provider"].text)
                            fact("Модель", preview.runtime["model"].text)
                            fact("Доступ", accessLabel(preview.runtime["access_mode"].text))
                            fact("Сеть", networkLabel(preview.runtime["network_state"].text))
                            fact("Workspace", "\(preview.runtime["workspace_label"].text) · \(preview.runtime["workspace_id"].text)")
                            fact("Инструменты", preview.runtime["tools"].items.map(\.text).joined(separator: ", ").nilIfEmpty ?? "нет")
                            Text("Описание отражает уже проверенные controls, но само не выдаёт права.")
                                .font(.caption).foregroundStyle(.secondary)
                        }
                        PersonaSection("Память и границы", icon: "lock.shield") {
                            fact("Выбранная память", "нет · retrieval не запускался")
                            fact("Context Injection", contextLabel(preview.value["context_injection_state"].text))
                            ForEach(Array(preview.kernel["core_laws"].items.enumerated()), id: \.offset) { _, law in
                                Label(law.text, systemImage: "checkmark.circle").font(.callout)
                            }
                            ForEach(Array(preview.kernel["boundaries"].items.enumerated()), id: \.offset) { _, boundary in
                                Label(boundary.text, systemImage: "hand.raised").font(.callout)
                            }
                        }
                        PersonaSection("Доказательства", icon: "number.square") {
                            Text("SHA-256 \(preview.snapshot["snapshot_hash"].text)")
                                .font(.caption.monospaced()).textSelection(.enabled)
                            ForEach(Array(preview.notices.enumerated()), id: \.offset) { _, notice in
                                Text(notice.text).font(.caption).foregroundStyle(.secondary)
                            }
                        }
                        if let readiness = model.personaReadiness {
                            PersonaSection("Activation readiness", icon: "checklist.checked") {
                                HStack(spacing: 8) {
                                    Circle().fill(readinessColor(readiness.status)).frame(width: 8, height: 8)
                                    headline(readinessLabel(readiness.status))
                                    Spacer()
                                    Text("только проверка").font(.caption).foregroundStyle(.secondary)
                                }
                                fact("Выбран", readiness.value["selected_provider"].text)
                                fact("Activation SHA", String(readiness.value["activation_fingerprint"].text.prefix(16)))
                                fact("Parity SHA", readiness.parity["persona_invariant_hash"].text.isEmpty
                                     ? "не совпал" : String(readiness.parity["persona_invariant_hash"].text.prefix(16)))
                                ForEach(Array(readiness.adapters.enumerated()), id: \.offset) { _, adapter in
                                    VStack(alignment: .leading, spacing: 3) {
                                        Text("\(adapter["provider"].text) · \(adapter["placement"].text)")
                                            .font(.callout.weight(.medium))
                                        Text("\(adapter["refresh_scope"].text) · provenance \(adapter["provenance_complete"].flag ? "OK" : "FAIL")")
                                            .font(.caption).foregroundStyle(.secondary)
                                    }
                                }
                                Divider()
                                ForEach(Array(readiness.gates.enumerated()), id: \.offset) { _, gate in
                                    Label {
                                        VStack(alignment: .leading, spacing: 2) {
                                            Text(gate["id"].text).font(.callout.weight(.medium))
                                            Text(gate["detail"].text).font(.caption).foregroundStyle(.secondary)
                                        }
                                    } icon: {
                                        Image(systemName: gateIcon(gate["status"].text))
                                            .foregroundStyle(gateColor(gate["status"].text))
                                    }
                                }
                                ForEach(Array(readiness.blockers.enumerated()), id: \.offset) { _, finding in
                                    Label(finding.text, systemImage: "xmark.octagon.fill").font(.caption).foregroundStyle(.red)
                                }
                                ForEach(Array(readiness.warnings.enumerated()), id: \.offset) { _, finding in
                                    Label(finding.text, systemImage: "exclamationmark.triangle.fill").font(.caption).foregroundStyle(.orange)
                                }
                                Text("Readiness не включает Persona, не вызывает модель и не меняет provider safety instructions.")
                                    .font(.caption).foregroundStyle(.secondary)
                            }
                        }
                    } else if model.personaPreviewError == nil && !model.loadingPersonaPreview {
                        Text("Откройте инспектор повторно или обновите snapshot.").foregroundStyle(.secondary)
                    }
                }.padding(22).frame(maxWidth: 760, alignment: .leading).frame(maxWidth: .infinity)
            }
            Divider()
            Label(model.personaEnabled
                  ? "Opt-in активен · один snapshot на ход · provider safety сохранена · rollback доступен"
                  : "Preview/readiness only · Persona не активна в prompt · нет model call, retrieval, execution или записи",
                  systemImage: model.personaEnabled ? "person.crop.circle.badge.checkmark" : "eye")
                .font(.caption).foregroundStyle(.secondary).padding(14)
        }
        .frame(minWidth: 680, idealWidth: 760, minHeight: 620, idealHeight: 740)
        .task { await model.refreshPersonaInspector() }
    }

    private func headline(_ text: String) -> some View {
        Text(text).font(.headline).textSelection(.enabled)
    }

    private func fact(_ label: String, _ value: String) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 8) {
            Text(label).foregroundStyle(.secondary).frame(width: 110, alignment: .leading)
            Text(value).textSelection(.enabled)
        }.font(.callout)
    }

    private func identityLabel(_ value: String) -> String {
        ["value": "Ценность", "principle": "Принцип", "boundary": "Граница"][value] ?? value
    }

    private func accessLabel(_ value: String) -> String {
        ["chat": "Чат без инструментов", "full_access": "Full Mac · действующий grant",
         "local": "Локальный runtime", "mock": "Детерминированный Mock"][value] ?? value
    }

    private func networkLabel(_ value: String) -> String {
        ["disabled": "выключена", "local_only": "только loopback", "available": "доступна по текущему grant"][value] ?? value
    }

    private func contextLabel(_ value: String) -> String {
        ["enabled": "включён ранее, snapshot его не применяет", "disabled": "выключен",
         "default_disabled": "выключен по умолчанию", "unknown": "не удалось проверить"][value] ?? value
    }

    private func readinessLabel(_ value: String) -> String {
        ["READY": "READY к отдельному activation milestone", "WARN": "WARN · control-only выбор",
         "NOT_READY": "NOT READY · activation заблокирована"][value] ?? value
    }

    private func readinessColor(_ value: String) -> Color {
        value == "READY" ? .green : (value == "WARN" ? .orange : .red)
    }

    private func gateIcon(_ value: String) -> String {
        value == "PASS" ? "checkmark.circle.fill" : (value == "WARN" ? "exclamationmark.triangle.fill" : "xmark.octagon.fill")
    }

    private func gateColor(_ value: String) -> Color {
        value == "PASS" ? .green : (value == "WARN" ? .orange : .red)
    }
}

private struct PersonaSection<Content: View>: View {
    let title: String
    let icon: String
    @ViewBuilder let content: () -> Content

    init(_ title: String, icon: String, @ViewBuilder content: @escaping () -> Content) {
        self.title = title
        self.icon = icon
        self.content = content
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 11) {
            Label(title, systemImage: icon).font(.headline)
            content()
        }.padding(16).frame(maxWidth: .infinity, alignment: .leading)
            .background(Color.primary.opacity(0.035), in: RoundedRectangle(cornerRadius: 12))
    }
}

private extension String {
    var nilIfEmpty: String? { isEmpty ? nil : self }
}
