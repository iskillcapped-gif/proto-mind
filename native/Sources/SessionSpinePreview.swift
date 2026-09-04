import SwiftUI

struct NativeSessionSpineEvent: Identifiable, Equatable {
    private static let fields: Set<String> = [
        "seq", "event_type", "time_ms", "surface_visible", "source_event_seqs", "stream", "part", "parts",
        "characters", "sha256", "tool_kind", "tool_status", "state", "outcome",
    ]
    private static let eventTypes: Set<String> = [
        "turn/start", "user/chunk", "user/message", "tool/result", "assistant/chunk", "assistant/message", "turn/end",
    ]
    let value: JSONValue
    let seq: Int
    var id: Int { seq }
    var type: String { value["event_type"].text }
    var surfaceVisible: Bool { value["surface_visible"].flag }

    init(_ value: JSONValue) throws {
        guard case .object(let fields) = value, Set(fields.keys) == Self.fields,
              let seq = Self.integer(value["seq"]), let time = Self.integer(value["time_ms"]), time >= 0,
              Self.eventTypes.contains(value["event_type"].text),
              case .bool = value["surface_visible"], case .array(let rawSources) = value["source_event_seqs"] else {
            throw Self.error()
        }
        let sources = rawSources.compactMap(Self.integer)
        guard sources.count == rawSources.count, sources == Array(Set(sources)).sorted(),
              sources.allSatisfy({ $0 >= 0 && $0 < seq }) else { throw Self.error() }
        let type = value["event_type"].text
        switch type {
        case "user/chunk", "assistant/chunk":
            let streams: Set<String> = type == "user/chunk" ? ["user"] : ["display", "raw"]
            guard streams.contains(value["stream"].text),
                  let part = Self.integer(value["part"]), let parts = Self.integer(value["parts"]),
                  let characters = Self.integer(value["characters"]), part >= 0, parts > 0, part < parts,
                  characters >= 0, NativeTurnReceipt.isHash(value["sha256"].text),
                  Self.onlyNull(value, except: ["stream", "part", "parts", "characters", "sha256"]) else { throw Self.error() }
        case "user/message", "assistant/message":
            let expected = type == "user/message" ? "user" : "display"
            guard value["stream"].text == expected, let characters = Self.integer(value["characters"]), characters > 0,
                  NativeTurnReceipt.isHash(value["sha256"].text),
                  Self.onlyNull(value, except: ["stream", "characters", "sha256"]) else { throw Self.error() }
        case "tool/result":
            guard !value["tool_kind"].text.isEmpty, value["tool_kind"].text.count <= 40,
                  !value["tool_status"].text.isEmpty, value["tool_status"].text.count <= 40,
                  Self.onlyNull(value, except: ["tool_kind", "tool_status"]) else { throw Self.error() }
        case "turn/start":
            guard value["state"] == .string("completed"), Self.onlyNull(value, except: ["state"]) else { throw Self.error() }
        case "turn/end":
            guard value["outcome"] == .string("response_recorded"), Self.onlyNull(value, except: ["outcome"]) else { throw Self.error() }
        default:
            throw Self.error()
        }
        self.value = value
        self.seq = seq
    }

    fileprivate static func integer(_ value: JSONValue) -> Int? {
        guard case .number(let number) = value, number.isFinite, number.rounded() == number,
              number >= 0, number < Double(Int.max) else { return nil }
        return Int(number)
    }

    private static func onlyNull(_ value: JSONValue, except: Set<String>) -> Bool {
        let optional: Set<String> = ["stream", "part", "parts", "characters", "sha256", "tool_kind", "tool_status", "state", "outcome"]
        return optional.subtracting(except).allSatisfy { value[$0].isNull }
    }

    private static func error() -> NativeError {
        .message("Карта события Session Spine не прошла локальную проверку. Ничего не открыто и не сохранено.")
    }
}

struct NativeSessionSpinePreview: Identifiable, Equatable {
    private static let fields: Set<String> = [
        "schema", "read_only", "source_record_read", "source_record_write", "no_write", "no_export", "no_migration",
        "no_model_call", "no_command_execution", "no_tool_replay", "no_permission_change", "context_injection_changed",
        "input_text_returned", "response_text_returned", "private_reasoning_included", "authoritative_history", "source",
        "projection", "timeline", "limitations", "preview_hash",
    ]
    private static let sourceFields: Set<String> = [
        "conversation_id", "user_message_id", "assistant_message_id", "run_id", "run_fingerprint", "reference_hash",
        "turn_receipt_hash", "display_status", "provider", "mode",
    ]
    private static let projectionFields: Set<String> = [
        "schema", "read_only", "no_file_access", "no_write", "execute", "source", "spine", "input", "answer",
        "tools", "work_log_sha256", "memory_candidate_ids", "warnings",
    ]
    private static let projectionSourceFields: Set<String> = ["run_id", "run_fingerprint", "display_status"]
    private static let projectionSpineFields: Set<String> = ["event_count", "surface_nodes", "fingerprint"]
    private static let projectionInputFields: Set<String> = ["event_seq", "sha256", "preserved"]
    private static let projectionAnswerFields: Set<String> = ["event_seq", "displayed_sha256", "raw_sha256", "preserved"]
    private static let projectionToolFields: Set<String> = ["count", "event_seqs"]
    let value: JSONValue
    let events: [NativeSessionSpineEvent]
    var id: String { value["source"]["run_id"].text + value["preview_hash"].text }
    var source: JSONValue { value["source"] }
    var projection: JSONValue { value["projection"] }

    init(
        _ value: JSONValue,
        source user: ChatMessage,
        assistant: ChatMessage,
        conversation: UUID,
        reference: NativeTurnReference,
        run: NativeWorkSession
    ) throws {
        guard case .object(let fields) = value, Set(fields.keys) == Self.fields,
              value["schema"] == .string("proto_mind.native_session_spine_live_preview.v1"),
              value["read_only"] == .bool(true), value["source_record_read"] == .bool(true),
              value["source_record_write"] == .bool(false), value["no_write"] == .bool(true),
              value["no_export"] == .bool(true), value["no_migration"] == .bool(true),
              value["no_model_call"] == .bool(true), value["no_command_execution"] == .bool(true),
              value["no_tool_replay"] == .bool(true), value["no_permission_change"] == .bool(true),
              value["context_injection_changed"] == .bool(false), value["input_text_returned"] == .bool(false),
              value["response_text_returned"] == .bool(false), value["private_reasoning_included"] == .bool(false),
              value["authoritative_history"] == .bool(false), case .object(let sourceFields) = value["source"],
              Set(sourceFields.keys) == Self.sourceFields else { throw Self.error() }

        let source = value["source"]
        guard reference.matches(source: user, assistant: assistant, conversation: conversation), reference.matches(run: run),
              source["conversation_id"].text == conversation.uuidString.lowercased(),
              source["user_message_id"].text == user.id.uuidString.lowercased(),
              source["assistant_message_id"].text == assistant.id.uuidString.lowercased(),
              source["run_id"] == reference.value["run_id"], source["run_id"].text == run.id,
              source["run_fingerprint"] == run.value["fingerprint"],
              source["reference_hash"] == reference.value["reference_hash"],
              source["turn_receipt_hash"] == reference.value["turn_receipt_hash"],
              source["display_status"] == .string("completed"),
              source["provider"] == reference.value["provider"], source["mode"] == reference.value["mode"] else { throw Self.error() }

        let projection = value["projection"]
        guard case .object(let projectionFields) = projection, Set(projectionFields.keys) == Self.projectionFields,
              case .object(let projectionSourceFields) = projection["source"],
              Set(projectionSourceFields.keys) == Self.projectionSourceFields,
              case .object(let projectionSpineFields) = projection["spine"],
              Set(projectionSpineFields.keys) == Self.projectionSpineFields,
              case .object(let projectionInputFields) = projection["input"],
              Set(projectionInputFields.keys) == Self.projectionInputFields,
              case .object(let projectionAnswerFields) = projection["answer"],
              Set(projectionAnswerFields.keys) == Self.projectionAnswerFields,
              case .object(let projectionToolFields) = projection["tools"],
              Set(projectionToolFields.keys) == Self.projectionToolFields,
              projection["schema"] == .string("proto_mind.native_session_spine_projection.v1"),
              projection["read_only"] == .bool(true), projection["no_write"] == .bool(true),
              projection["no_file_access"] == .bool(true), projection["execute"] == .bool(false),
              projection["source"]["run_id"] == source["run_id"],
              projection["source"]["run_fingerprint"] == source["run_fingerprint"],
              projection["source"]["display_status"] == .string("completed"),
              projection["input"]["sha256"] == reference.value["input_sha256"],
              projection["input"]["preserved"] == .bool(true),
              projection["answer"]["raw_sha256"] == reference.value["response_sha256"],
              projection["answer"]["preserved"] == .bool(true),
              NativeTurnReceipt.isHash(projection["answer"]["displayed_sha256"].text),
              NativeTurnReceipt.isHash(projection["spine"]["fingerprint"].text),
              NativeTurnReceipt.isHash(projection["work_log_sha256"].text),
              case .array(let rawEvents) = value["timeline"], rawEvents.count <= 132,
              case .array(let rawNodes) = projection["spine"]["surface_nodes"],
              case .array(let rawToolSequences) = projection["tools"]["event_seqs"],
              case .array(let memoryIDs) = projection["memory_candidate_ids"], memoryIDs.count <= 2,
              memoryIDs.allSatisfy({ NativeTurnReceipt.isHash($0.text) }),
              case .array(let warnings) = projection["warnings"], warnings.isEmpty else { throw Self.error() }
        let events = try rawEvents.map(NativeSessionSpineEvent.init)
        let nodes = try rawNodes.map(Self.checkedInteger)
        let toolSequences = try rawToolSequences.map(Self.checkedInteger)
        guard let eventCount = NativeSessionSpineEvent.integer(projection["spine"]["event_count"]),
              let inputSequence = NativeSessionSpineEvent.integer(projection["input"]["event_seq"]),
              let answerSequence = NativeSessionSpineEvent.integer(projection["answer"]["event_seq"]),
              let toolCount = NativeSessionSpineEvent.integer(projection["tools"]["count"]),
              events.map(\.seq) == Array(events.indices), eventCount == events.count,
              events.first?.type == "turn/start", events.last?.type == "turn/end",
              events.filter({ $0.type == "user/message" }).map(\.seq) == [inputSequence],
              events.filter({ $0.type == "assistant/message" }).map(\.seq) == [answerSequence],
              events.first(where: { $0.seq == inputSequence })?.value["sha256"] == projection["input"]["sha256"],
              events.first(where: { $0.seq == answerSequence })?.value["sha256"] == projection["answer"]["displayed_sha256"],
              toolSequences == events.filter({ $0.type == "tool/result" }).map(\.seq), toolCount == toolSequences.count,
              nodes == events.filter(\.surfaceVisible).map(\.seq),
              value["limitations"].items.map(\.text) == [
                "in_memory_projection_only", "not_authoritative_history",
                "no_task_success_or_provider_delivery_proof", "tool_evidence_not_replayable",
              ], NativeTurnReceipt.isHash(value["preview_hash"].text) else { throw Self.error() }

        let material = JSONValue.object(fields.filter { $0.key != "preview_hash" })
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys, .withoutEscapingSlashes]
        let encoded = try encoder.encode(material)
        guard let text = String(data: encoded, encoding: .utf8),
              value["preview_hash"] == .string(NativeTurnReceipt.hash(text)) else { throw Self.error() }
        self.value = value
        self.events = events
    }

    private static func checkedInteger(_ value: JSONValue) throws -> Int {
        guard let result = NativeSessionSpineEvent.integer(value) else { throw Self.error() }
        return result
    }

    static func parameters(
        source: ChatMessage,
        assistant: ChatMessage,
        conversation: UUID,
        reference: NativeTurnReference,
        run: NativeWorkSession
    ) throws -> [String: JSONValue] {
        guard reference.matches(source: source, assistant: assistant, conversation: conversation), reference.matches(run: run) else {
            throw Self.error()
        }
        var assistantFields: [String: JSONValue] = [
            "id": .string(assistant.id.uuidString.lowercased()), "role": .string(assistant.role),
            "text": .string(assistant.text), "raw": .string(assistant.raw),
            "isError": .bool(assistant.isError), "operatorInput": .bool(assistant.operatorInput == true),
        ]
        if let suggestions = assistant.memorySuggestions, let suggestionSource = assistant.memorySuggestionSourceID {
            assistantFields["memorySuggestions"] = suggestions
            assistantFields["memorySuggestionSourceID"] = .string(suggestionSource.uuidString.lowercased())
        } else if assistant.memorySuggestions != nil || assistant.memorySuggestionSourceID != nil {
            throw Self.error()
        }
        return [
            "conversation_id": .string(conversation.uuidString.lowercased()),
            "run": run.reference,
            "turn_reference": reference.value,
            "user_message": .object([
                "id": .string(source.id.uuidString.lowercased()), "role": .string(source.role),
                "text": .string(source.text), "isError": .bool(source.isError),
                "operatorInput": .bool(source.operatorInput == true),
            ]),
            "assistant_message": .object(assistantFields),
        ]
    }

    private static func error() -> NativeError {
        .message("Live Session Spine Preview не прошёл точную проверку источника. Ничего не записано и не выполнено.")
    }
}

struct SessionSpinePreviewView: View {
    let preview: NativeSessionSpinePreview
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        VStack(spacing: 0) {
            HStack(spacing: 12) {
                Label("Live Session Spine", systemImage: "point.3.connected.trianglepath.dotted")
                    .font(.title3.weight(.semibold))
                Text("ТОЛЬКО ЧТЕНИЕ").font(.caption2.weight(.semibold)).padding(.horizontal, 8).padding(.vertical, 4)
                    .background(Color.green.opacity(0.12), in: Capsule()).foregroundStyle(.green)
                Spacer()
                Button("Закрыть") { dismiss() }.keyboardShortcut(.cancelAction)
            }.padding(20)
            Divider()
            ScrollView {
                VStack(alignment: .leading, spacing: 18) {
                    VStack(alignment: .leading, spacing: 7) {
                        Text("Точная проекция одного хода").font(.title2.weight(.medium))
                        Text("Сообщение, исходный ответ и сохранённый запуск повторно сверены через Turn Lineage. Ниже временная карта существующего P1-контракта, а не новая история.")
                            .foregroundStyle(.secondary)
                    }
                    HStack(spacing: 10) {
                        badge("\(preview.events.count) событий", icon: "list.number")
                        badge("\(preview.projection["spine"]["surface_nodes"].items.count) на поверхности", icon: "rectangle.stack")
                        badge("\(preview.projection["tools"]["count"].integer) инструментов", icon: "wrench.and.screwdriver")
                    }
                    VStack(alignment: .leading, spacing: 6) {
                        metadata("Запуск", preview.source["run_id"].text)
                        metadata("Провайдер и режим", "\(preview.source["provider"].text) · \(preview.source["mode"].text)")
                        metadata("Turn receipt", preview.source["turn_receipt_hash"].text)
                        metadata("Surface fingerprint", preview.projection["spine"]["fingerprint"].text)
                        metadata("Preview SHA-256", preview.value["preview_hash"].text)
                    }.padding(14).background(Color.primary.opacity(0.035), in: RoundedRectangle(cornerRadius: 12))
                    VStack(alignment: .leading, spacing: 12) {
                        Text("Карта событий").font(.headline)
                        ForEach(preview.events) { event in
                            HStack(alignment: .top, spacing: 12) {
                                Image(systemName: icon(event.type)).frame(width: 18).foregroundStyle(event.surfaceVisible ? .primary : .secondary)
                                VStack(alignment: .leading, spacing: 3) {
                                    HStack {
                                        Text("\(event.seq) · \(label(event.type))").font(.callout.weight(.medium))
                                        if event.surfaceVisible { Text("SURFACE").font(.caption2).foregroundStyle(.secondary) }
                                    }
                                    Text(detail(event)).font(.caption).foregroundStyle(.secondary).textSelection(.enabled)
                                }
                            }
                        }
                    }
                    Label("Текст сообщения и ответа не возвращался вторым payload-ом; в preview есть только размеры, SHA-256, типы и provenance событий.", systemImage: "checkmark.shield")
                        .font(.callout).foregroundStyle(.secondary)
                    Text("Открытие и закрытие этого окна не пишет Session Spine, не экспортирует данные, не вызывает модель или команды, не повторяет инструменты и не меняет разрешения либо Context Injection. Проекция не доказывает выполнение задачи или доставку ответа провайдером.")
                        .font(.caption).foregroundStyle(.secondary)
                }.padding(22).frame(maxWidth: .infinity, alignment: .leading)
            }
        }.frame(width: 780, height: 680).background(NativeTheme.canvas)
            .font(NativeTheme.interfaceFont).buttonStyle(.nativeHover)
    }

    private func badge(_ text: String, icon: String) -> some View {
        Label(text, systemImage: icon).font(.caption).padding(.horizontal, 10).padding(.vertical, 7)
            .background(NativeTheme.bubble, in: Capsule())
    }

    private func metadata(_ label: String, _ value: String) -> some View {
        HStack(alignment: .firstTextBaseline) {
            Text(label).foregroundStyle(.secondary).frame(width: 145, alignment: .leading)
            Text(value).font(NativeTheme.codeFont).textSelection(.enabled)
        }.font(.caption)
    }

    private func label(_ type: String) -> String {
        switch type {
        case "turn/start": return "начало хода"
        case "user/chunk": return "фрагмент пользователя"
        case "user/message": return "сообщение пользователя"
        case "tool/result": return "результат инструмента"
        case "assistant/chunk": return "фрагмент ответа"
        case "assistant/message": return "ответ ассистента"
        case "turn/end": return "завершение хода"
        default: return type
        }
    }

    private func icon(_ type: String) -> String {
        switch type {
        case "turn/start", "turn/end": return "circle.dotted"
        case "user/message": return "person.crop.circle"
        case "assistant/message": return "sparkles"
        case "tool/result": return "wrench.and.screwdriver"
        default: return "number"
        }
    }

    private func detail(_ event: NativeSessionSpineEvent) -> String {
        if event.type.hasSuffix("/chunk") {
            return "\(event.value["stream"].text) · часть \(event.value["part"].integer + 1)/\(event.value["parts"].integer) · \(event.value["characters"].integer) символов · SHA \(event.value["sha256"].text.prefix(12))"
        }
        if ["user/message", "assistant/message"].contains(event.type) {
            return "\(event.value["characters"].integer) символов · SHA \(event.value["sha256"].text.prefix(12)) · источники \(event.value["source_event_seqs"].items.count)"
        }
        if event.type == "tool/result" {
            return "\(event.value["tool_kind"].text) · \(event.value["tool_status"].text) · evidence-only, повтор запрещён"
        }
        if event.type == "turn/start" { return "Сохранённый источник имеет состояние completed" }
        return "response_recorded · успех задачи отдельно не выводится"
    }
}
