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

struct PersonaInspectorView: View {
    @ObservedObject var model: AppModel

    var body: some View {
        VStack(spacing: 0) {
            HStack(spacing: 12) {
                Label("Persona Inspector", systemImage: "person.crop.circle.badge.checkmark")
                    .font(.title3.weight(.semibold))
                Spacer()
                if model.loadingPersonaPreview { ProgressView().controlSize(.small) }
                Button { Task { await model.refreshPersonaPreview() } } label: { Image(systemName: "arrow.clockwise") }
                    .disabled(model.busy || model.loadingPersonaPreview).help("Пересобрать read-only snapshot")
                Button { model.showPersonaInspector = false } label: { Image(systemName: "xmark") }
                    .keyboardShortcut(.cancelAction)
            }.padding(20)
            Divider()
            ScrollView {
                VStack(alignment: .leading, spacing: 18) {
                    if let error = model.personaPreviewError {
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
                    } else if model.personaPreviewError == nil && !model.loadingPersonaPreview {
                        Text("Откройте инспектор повторно или обновите snapshot.").foregroundStyle(.secondary)
                    }
                }.padding(22).frame(maxWidth: 760, alignment: .leading).frame(maxWidth: .infinity)
            }
            Divider()
            Label("Не активен в prompt · нет model call, retrieval, execution или записи", systemImage: "eye")
                .font(.caption).foregroundStyle(.secondary).padding(14)
        }
        .frame(minWidth: 680, idealWidth: 760, minHeight: 620, idealHeight: 740)
        .task { await model.refreshPersonaPreview() }
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
