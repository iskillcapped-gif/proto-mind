import Foundation
import SwiftUI

private func sessionSpineWriterHash(_ value: JSONValue) throws -> String {
    let encoder = JSONEncoder()
    encoder.outputFormatting = [.sortedKeys, .withoutEscapingSlashes]
    let data = try encoder.encode(value)
    guard let text = String(data: data, encoding: .utf8) else {
        throw NativeError.message("Session Spine writer evidence не удалось канонизировать.")
    }
    return NativeTurnReceipt.hash(text)
}

private func sessionSpineWriterPathMatches(_ reported: String, _ expected: String) -> Bool {
    func canonical(_ path: String) -> String {
        var cursor = URL(fileURLWithPath: path).standardizedFileURL
        var missingComponents: [String] = []
        while cursor.path != "/" && !FileManager.default.fileExists(atPath: cursor.path) {
            missingComponents.insert(cursor.lastPathComponent, at: 0)
            cursor.deleteLastPathComponent()
        }
        cursor = cursor.resolvingSymlinksInPath().standardizedFileURL
        for component in missingComponents { cursor.appendPathComponent(component) }
        return cursor.standardizedFileURL.path
    }
    return canonical(reported) == canonical(expected)
}

struct NativeSessionSpineWriterPreview: Identifiable, Equatable {
    private static let fields: Set<String> = [
        "schema", "format_version", "status", "state", "read_only", "source", "gate", "identity", "stores",
        "intent_id", "recovery_state", "writes_on_confirm", "boundaries", "candidate_hash", "confirmation_token",
        "preview_hash",
    ]
    private static let sourceFields: Set<String> = [
        "conversation_id", "user_message_id", "assistant_message_id", "run_id", "run_fingerprint",
        "turn_receipt_hash", "reference_hash", "live_preview_hash", "history_sha256", "history_bytes",
        "history_turn_sha256", "work_session_sha256", "work_session_bytes",
    ]
    private static let gateFields: Set<String> = [
        "acceptance_state", "candidate_hash", "readiness_report_hash", "rehearsal_hash", "acceptance_report_hash",
    ]
    private static let boundaryFields: Set<String> = [
        "single_exact_latest_turn", "fixed_private_paths_only", "legacy_backfill", "automatic_retry",
        "automatic_repair", "model_call", "provider_call", "command_execution", "tool_replay", "permission_change",
        "context_injection_change",
    ]
    private static let writes = [
        "native_history_exact_save_and_readback",
        "installation_identity_create_once_if_missing",
        "durable_intent_prepare_once",
        "session_spine_compare_and_swap_once",
        "durable_intent_commit_marker_once",
    ]

    let value: JSONValue
    let state: String
    let source: JSONValue
    let confirmationToken: String

    var id: String { value["preview_hash"].text }
    var candidateHash: String { value["candidate_hash"].text }
    var canApply: Bool { ["READY", "RECOVERY_READY"].contains(state) && !confirmationToken.isEmpty }
    var closed: Bool { state == "CLOSED" }
    var recoveryReady: Bool { state == "RECOVERY_READY" }

    init(
        _ value: JSONValue,
        live: NativeSessionSpinePreview,
        readiness: NativeSessionSpineActivationReadiness,
        rehearsal: NativeSessionSpineAcceptanceRehearsal,
        stateDirectory: URL
    ) throws {
        guard case .object(let fields) = value, Set(fields.keys) == Self.fields,
              value["schema"] == .string("proto_mind.native_session_spine_writer_preview.v1"),
              value["format_version"] == .number(1), value["read_only"] == .bool(true),
              case .object(let sourceFields) = value["source"], Set(sourceFields.keys) == Self.sourceFields,
              case .object(let gateFields) = value["gate"], Set(gateFields.keys) == Self.gateFields,
              case .object(let boundaryFields) = value["boundaries"], Set(boundaryFields.keys) == Self.boundaryFields,
              case .object(let stores) = value["stores"], Set(stores.keys) == ["spine", "intent"],
              value["writes_on_confirm"].items.map(\.text) == Self.writes else { throw Self.error("envelope") }

        let state = value["state"].text
        let status = value["status"].text
        guard ["READY", "RECOVERY_READY", "CLOSED", "BLOCKED"].contains(state),
              (state == "READY" ? status == "OK" : state == "RECOVERY_READY" ? status == "WARN"
               : state == "BLOCKED" ? status == "ERROR" : ["OK", "WARN"].contains(status)) else { throw Self.error("state") }

        let source = value["source"]
        guard source["conversation_id"] == live.source["conversation_id"],
              source["user_message_id"] == live.source["user_message_id"],
              source["assistant_message_id"] == live.source["assistant_message_id"],
              source["run_id"] == live.source["run_id"],
              source["run_fingerprint"] == live.source["run_fingerprint"],
              source["turn_receipt_hash"] == live.source["turn_receipt_hash"],
              source["reference_hash"] == live.source["reference_hash"],
              source["live_preview_hash"] == live.value["preview_hash"],
              NativeTurnReceipt.isHash(source["history_sha256"].text), source["history_bytes"].integer > 0,
              NativeTurnReceipt.isHash(source["history_turn_sha256"].text),
              NativeTurnReceipt.isHash(source["work_session_sha256"].text), source["work_session_bytes"].integer > 0 else {
            throw Self.error("source")
        }

        let gate = value["gate"]
        guard gate["acceptance_state"] == .string(rehearsal.state),
              gate["candidate_hash"] == .string(readiness.candidateHash),
              gate["readiness_report_hash"] == readiness.value["report_hash"],
              gate["rehearsal_hash"] == .string(rehearsal.rehearsalHash),
              gate["acceptance_report_hash"] == rehearsal.value["report_hash"],
              ["ACCEPTED", "RECOVERY_REQUIRED"].contains(rehearsal.state),
              NativeTurnReceipt.isHash(gate["candidate_hash"].text),
              NativeTurnReceipt.isHash(gate["readiness_report_hash"].text),
              NativeTurnReceipt.isHash(gate["rehearsal_hash"].text),
              NativeTurnReceipt.isHash(gate["acceptance_report_hash"].text) else { throw Self.error("gate") }

        // Foundation and Python may spell macOS' /var alias differently.
        let root = stateDirectory.resolvingSymlinksInPath().standardizedFileURL
        let expectedPaths = [
            "spine": root.appendingPathComponent("session_spine_store", isDirectory: true).path,
            "intent": root.appendingPathComponent("session_spine_intents", isDirectory: true).path,
        ]
        for name in ["spine", "intent"] {
            let item = value["stores"][name]
            guard case .object(let fields) = item, Set(fields.keys) == ["path", "state", "entry_count"] else {
                throw Self.error("store fields")
            }
            guard let expectedPath = expectedPaths[name],
                  sessionSpineWriterPathMatches(item["path"].text, expectedPath) else {
                throw Self.error("store path \(name): \(item["path"].text) != \(expectedPaths[name] ?? "missing")")
            }
            guard ["missing", "empty", "evidence"].contains(item["state"].text),
                  item["entry_count"].integer >= 0 else { throw Self.error("store state") }
        }
        let identity = value["identity"]
        let expectedIdentity = root.appendingPathComponent("session_spine_identity/installation.json").path
        guard sessionSpineWriterPathMatches(identity["path"].text, expectedIdentity),
              ["missing", "verified"].contains(identity["state"].text) else {
            throw Self.error("identity path")
        }
        if identity["state"] == .string("missing") {
            guard case .object(let fields) = identity,
                  Set(fields.keys) == ["state", "path", "identity_hash", "transition_on_confirm"],
                  identity["identity_hash"].isNull,
                  identity["transition_on_confirm"] == .string("create_once_then_exact_readback") else { throw Self.error("missing identity") }
        } else {
            guard case .object(let fields) = identity,
                  Set(fields.keys) == ["state", "path", "identity_hash", "owner_id", "directory_state"],
                  NativeTurnReceipt.isHash(identity["identity_hash"].text),
                  identity["owner_id"].text.hasPrefix("native-session-spine:"),
                  ["empty", "evidence"].contains(identity["directory_state"].text) else { throw Self.error("verified identity") }
        }

        for key in ["single_exact_latest_turn", "fixed_private_paths_only"] {
            guard value["boundaries"][key] == .bool(true) else { throw Self.error("required boundary") }
        }
        for key in Self.boundaryFields.subtracting(["single_exact_latest_turn", "fixed_private_paths_only"]) {
            guard value["boundaries"][key] == .bool(false) else { throw Self.error("closed boundary") }
        }
        if !value["intent_id"].isNull {
            guard value["intent_id"].text.range(of: "^[0-9a-f]{32}$", options: .regularExpression) != nil else {
                throw Self.error("intent")
            }
        }
        guard NativeTurnReceipt.isHash(value["candidate_hash"].text),
              NativeTurnReceipt.isHash(value["preview_hash"].text) else { throw Self.error("digest shape") }
        let confirmation = value["confirmation_token"].text
        if ["READY", "RECOVERY_READY"].contains(state) {
            guard confirmation == "CONFIRM-SESSION-SPINE-" + value["candidate_hash"].text.prefix(16).uppercased() else {
                throw Self.error("confirmation")
            }
        } else if !confirmation.isEmpty { throw Self.error("blocked confirmation") }

        let candidateMaterial = JSONValue.object(fields.filter {
            !["candidate_hash", "confirmation_token", "preview_hash"].contains($0.key)
        })
        let previewMaterial = JSONValue.object(fields.filter { $0.key != "preview_hash" })
        guard value["candidate_hash"] == .string(try sessionSpineWriterHash(candidateMaterial)),
              value["preview_hash"] == .string(try sessionSpineWriterHash(previewMaterial)) else { throw Self.error("hash") }
        self.value = value
        self.state = state
        self.source = source
        self.confirmationToken = confirmation
    }

    func accepts(token: String, acknowledgement: Bool) -> Bool {
        canApply && acknowledgement && token == confirmationToken
    }

    private static func error(_ stage: String = "contract") -> NativeError {
        .message("Session Spine writer preview не прошёл точную локальную проверку (\(stage)). Ничего не записано.")
    }
}

struct NativeSessionSpineWriterReceipt: Identifiable, Equatable {
    private static let fields: Set<String> = [
        "schema", "format_version", "result", "candidate_hash", "preview_hash", "conversation_id", "run_id",
        "intent_id", "owner_id", "identity_hash", "history_sha256", "work_session_sha256",
        "history_saved_and_read_back", "history_write_performed", "identity_created",
        "intent_prepare_write_performed", "spine_write_performed", "intent_commit_write_performed",
        "target_execution_performed", "closed", "run_once", "automatic_retry", "automatic_repair", "legacy_backfill",
        "model_call_performed", "provider_call_performed", "command_executed", "tool_replayed", "permission_changed",
        "context_injection_changed", "intent_apply_receipt_hash", "post_inspection_hash", "receipt_hash",
    ]
    let value: JSONValue
    var id: String { value["receipt_hash"].text }
    var result: String { value["result"].text }

    init(
        _ value: JSONValue,
        preview: NativeSessionSpineWriterPreview,
        identity: NativeSessionSpineInstallationIdentity,
        readback: ChatStoreReadback
    ) throws {
        guard case .object(let fields) = value, Set(fields.keys) == Self.fields,
              value["schema"] == .string("proto_mind.native_session_spine_writer_receipt.v1"),
              value["format_version"] == .number(1),
              ["COMMITTED", "RECOVERED_COMMIT_MARKER", "ALREADY_CLOSED"].contains(value["result"].text),
              value["candidate_hash"] == .string(preview.candidateHash),
              value["preview_hash"] == preview.value["preview_hash"],
              value["conversation_id"] == preview.source["conversation_id"],
              value["run_id"] == preview.source["run_id"],
              value["owner_id"] == .string(identity.ownerID), value["identity_hash"] == .string(identity.identityHash),
              value["history_sha256"] == .string(readback.sha256),
              value["work_session_sha256"] == preview.source["work_session_sha256"],
              value["history_saved_and_read_back"] == .bool(true), value["history_write_performed"] == .bool(true),
              value["identity_created"] == .bool(preview.value["identity"]["state"] == .string("missing")),
              value["target_execution_performed"] == .bool(false), value["closed"] == .bool(true),
              value["run_once"] == .bool(true), NativeTurnReceipt.isHash(value["intent_apply_receipt_hash"].text),
              NativeTurnReceipt.isHash(value["post_inspection_hash"].text),
              NativeTurnReceipt.isHash(value["receipt_hash"].text),
              value["intent_id"].text.range(of: "^[0-9a-f]{32}$", options: .regularExpression) != nil else {
            throw Self.error()
        }
        for key in ["automatic_retry", "automatic_repair", "legacy_backfill", "model_call_performed",
                    "provider_call_performed", "command_executed", "tool_replayed", "permission_changed",
                    "context_injection_changed"] {
            guard value[key] == .bool(false) else { throw Self.error() }
        }
        let prepared = value["intent_prepare_write_performed"].flag
        let spine = value["spine_write_performed"].flag
        let committed = value["intent_commit_write_performed"].flag
        switch value["result"].text {
        case "COMMITTED": guard spine && committed else { throw Self.error() }
        case "RECOVERED_COMMIT_MARKER": guard !prepared && !spine && committed else { throw Self.error() }
        case "ALREADY_CLOSED": guard !prepared && !spine && !committed else { throw Self.error() }
        default: throw Self.error()
        }
        guard value["receipt_hash"] == .string(try sessionSpineWriterHash(.object(fields.filter { $0.key != "receipt_hash" }))) else {
            throw Self.error()
        }
        self.value = value
    }

    private static func error() -> NativeError {
        .message("Session Spine writer receipt не прошёл проверку. Не повторяйте запись; проверьте recovery evidence.")
    }
}

struct SessionSpineWriterView: View {
    @ObservedObject var model: AppModel
    let preview: NativeSessionSpineWriterPreview
    @Environment(\.dismiss) private var dismiss
    @State private var acknowledged = false
    @State private var token = ""

    private var receipt: NativeSessionSpineWriterReceipt? {
        guard let value = model.sessionSpineWriterReceipt,
              value.value["candidate_hash"] == .string(preview.candidateHash) else { return nil }
        return value
    }

    var body: some View {
        VStack(spacing: 0) {
            HStack(spacing: 12) {
                Label("Session Spine · single-turn writer", systemImage: "pencil.and.outline")
                    .font(.title3.weight(.semibold))
                Text(receipt == nil ? preview.state : "CLOSED").font(.caption2.weight(.semibold))
                    .padding(.horizontal, 8).padding(.vertical, 4)
                    .background(statusColor.opacity(0.13), in: Capsule()).foregroundStyle(statusColor)
                Spacer()
                Button("Закрыть") { dismiss() }.keyboardShortcut(.cancelAction)
            }.padding(20)
            Divider()
            ScrollView {
                VStack(alignment: .leading, spacing: 18) {
                    Text(title).font(.title2.weight(.medium))
                    Text(summary).foregroundStyle(.secondary)
                    VStack(alignment: .leading, spacing: 6) {
                        detail("Диалог", preview.source["conversation_id"].text)
                        detail("Запуск", preview.source["run_id"].text)
                        detail("History SHA-256", preview.source["history_sha256"].text)
                        detail("Candidate", preview.candidateHash)
                        if !preview.value["intent_id"].isNull { detail("Durable intent", preview.value["intent_id"].text) }
                    }.padding(14).background(Color.primary.opacity(0.035), in: RoundedRectangle(cornerRadius: 12))

                    if let receipt {
                        VStack(alignment: .leading, spacing: 9) {
                            Label("Один точный ход закрыт проверяемой квитанцией", systemImage: "checkmark.seal")
                                .font(.headline).foregroundStyle(.green)
                            detail("Результат", receipt.result)
                            detail("Intent", receipt.value["intent_id"].text)
                            detail("Receipt SHA-256", receipt.value["receipt_hash"].text)
                            Text("Повторная кнопка отсутствует. Новый ход не будет записан автоматически.")
                                .font(.callout).foregroundStyle(.secondary)
                        }.padding(14).background(Color.green.opacity(0.07), in: RoundedRectangle(cornerRadius: 12))
                    } else if preview.canApply {
                        VStack(alignment: .leading, spacing: 12) {
                            Label(preview.recoveryReady ? "Восстановление exact intent" : "Первая личная запись Session Spine",
                                  systemImage: "exclamationmark.shield")
                                .font(.headline).foregroundStyle(.orange)
                            Text("После финальной проверки могут быть затронуты только conversations.json и три private namespace: identity, intent и Session Spine. Каждый этап проверяется receipt/recovery-контрактом; Work Session останется read-only.")
                                .font(.callout).foregroundStyle(.secondary)
                            Toggle("Понимаю область записи и подтверждаю только этот exact-linked ход", isOn: $acknowledged)
                                .toggleStyle(.checkbox)
                            Text(preview.confirmationToken).font(NativeTheme.codeFont).textSelection(.enabled)
                            TextField("Введите точную фразу", text: $token).textFieldStyle(.roundedBorder)
                            Button(model.applyingSessionSpineWriter ? "Проверяем и записываем…" : "Записать один точный ход") {
                                Task { await model.applySessionSpineWriter(preview, token: token, acknowledgement: acknowledged) }
                            }
                            .buttonStyle(.borderedProminent).nativeHoverSurface()
                            .disabled(model.applyingSessionSpineWriter || !preview.accepts(token: token, acknowledgement: acknowledged))
                        }.padding(14).background(Color.orange.opacity(0.07), in: RoundedRectangle(cornerRadius: 12))
                    } else {
                        Label(preview.closed ? "Этот exact-linked ход уже закрыт; повторная запись запрещена."
                              : "Evidence не допускает writer. Нужна ручная проверка без очистки и retry.",
                              systemImage: preview.closed ? "checkmark.seal" : "hand.raised")
                            .padding(14).background(Color.primary.opacity(0.035), in: RoundedRectangle(cornerRadius: 12))
                    }
                    Text("P2l не вызывает модель, провайдера, команды или инструменты; не делает legacy backfill, repair или automatic retry; не меняет разрешения и Context Injection. Потерянный ответ восстанавливается только из точного durable intent и повторной ручной проверки.")
                        .font(.caption).foregroundStyle(.secondary)
                }.padding(22).frame(maxWidth: .infinity, alignment: .leading)
            }
        }.frame(width: 790, height: 690).background(NativeTheme.canvas)
            .font(NativeTheme.interfaceFont).buttonStyle(.nativeHover)
    }

    private var statusColor: Color { receipt != nil || preview.closed ? .green : preview.canApply ? .orange : .red }
    private var title: String { receipt != nil ? "Проверяемая запись завершена" : preview.closed ? "Ход уже записан"
        : preview.recoveryReady ? "Продолжить только подтверждённый durable intent" : preview.canApply ? "Последний gate перед writer" : "Writer заблокирован" }
    private var summary: String { preview.recoveryReady
        ? "Существующий prepared intent точно совпал с этим turn; новый токен разрешает только его завершение."
        : "Источник, история, Work Session, private paths и P2j/P2k evidence связаны одним self-hashed preview." }

    private func detail(_ label: String, _ value: String) -> some View {
        HStack(alignment: .firstTextBaseline) {
            Text(label).foregroundStyle(.secondary).frame(width: 130, alignment: .leading)
            Text(value).font(NativeTheme.codeFont).textSelection(.enabled)
        }.font(.caption)
    }
}
