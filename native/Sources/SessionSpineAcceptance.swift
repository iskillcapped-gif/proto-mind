import Darwin
import Foundation
import SwiftUI

struct NativeSessionSpinePathObservation: Identifiable, Equatable {
    let label: String
    let path: String
    let expectedKind: String
    let expectedMode: String
    let state: String
    let entryCount: Int
    let scopeHash: String

    var id: String { label }
    var ready: Bool {
        ["verified_private_directory", "verified_private_file", "private_empty_directory", "clean_uninitialized"]
            .contains(state)
    }

    var value: JSONValue {
        .object([
            "label": .string(label),
            "path": .string(path),
            "expected_kind": .string(expectedKind),
            "expected_mode": .string(expectedMode),
            "state": .string(state),
            "entry_count": .number(Double(entryCount)),
            "scope_sha256": .string(scopeHash),
            "ready": .bool(ready),
        ])
    }

    static func stateRoot(_ url: URL) -> NativeSessionSpinePathObservation {
        inspectDirectory(label: "Native private state", url: url, missingIsClean: false)
    }

    static func futureDirectory(label: String, url: URL) -> NativeSessionSpinePathObservation {
        inspectDirectory(label: label, url: url, missingIsClean: true)
    }

    static func identity(
        path: String,
        identityState: String,
        recoveryRequired: Bool
    ) -> NativeSessionSpinePathObservation {
        let state = recoveryRequired
            ? "manual_inspection_required"
            : identityState == "verified" ? "verified_private_file" : "clean_uninitialized"
        return NativeSessionSpinePathObservation(
            label: "Installation identity",
            path: path,
            expectedKind: "canonical_json_file",
            expectedMode: "0600",
            state: state,
            entryCount: identityState == "verified" ? 1 : 0,
            scopeHash: NativeTurnReceipt.hash(path)
        )
    }

    private static func inspectDirectory(
        label: String,
        url: URL,
        missingIsClean: Bool
    ) -> NativeSessionSpinePathObservation {
        let path = url.standardizedFileURL.path
        let base = { (state: String, count: Int) in
            NativeSessionSpinePathObservation(
                label: label,
                path: path,
                expectedKind: "private_directory",
                expectedMode: "0700",
                state: state,
                entryCount: count,
                scopeHash: NativeTurnReceipt.hash(path)
            )
        }
        guard url.isFileURL, url.path == path, path.hasPrefix("/") else {
            return base("noncanonical_path", 0)
        }
        var metadata = stat()
        guard lstat(path, &metadata) == 0 else {
            return errno == ENOENT && missingIsClean
                ? base("clean_uninitialized", 0)
                : base("unavailable", 0)
        }
        guard (metadata.st_mode & S_IFMT) == S_IFDIR, metadata.st_mode & 0o077 == 0 else {
            return base("unsafe_type_or_permissions", 0)
        }
        let descriptor = open(path, O_RDONLY | O_DIRECTORY | O_NOFOLLOW)
        guard descriptor >= 0 else { return base("unavailable", 0) }
        defer { close(descriptor) }
        var opened = stat()
        guard fstat(descriptor, &opened) == 0,
              opened.st_dev == metadata.st_dev, opened.st_ino == metadata.st_ino else {
            return base("changed_during_inspection", 0)
        }
        let contents: [String]
        do {
            contents = try FileManager.default.contentsOfDirectory(atPath: path)
        } catch {
            return base("unreadable", 0)
        }
        guard contents.count <= 256 else { return base("unbounded_existing_evidence", contents.count) }
        return contents.isEmpty
            ? base(label == "Native private state" ? "verified_private_directory" : "private_empty_directory", 0)
            : base(label == "Native private state" ? "verified_private_directory" : "existing_evidence_requires_manual_inspection", contents.count)
    }
}

struct NativeSessionSpineAcceptanceGrant: Equatable {
    let rehearsalHash: String
    let candidateHash: String
    let conversationID: String
    let runID: String

    init(rehearsal: NativeSessionSpineAcceptanceRehearsal) throws {
        guard rehearsal.canAccept else {
            throw NativeError.message("Session Spine rehearsal не готов к локальной приёмке. Writer остался выключен.")
        }
        rehearsalHash = rehearsal.rehearsalHash
        candidateHash = rehearsal.source["candidate_hash"].text
        conversationID = rehearsal.source["conversation_id"].text
        runID = rehearsal.source["run_id"].text
    }

    func matches(_ rehearsal: NativeSessionSpineAcceptanceRehearsal) -> Bool {
        rehearsalHash == rehearsal.rehearsalHash
            && candidateHash == rehearsal.source["candidate_hash"].text
            && conversationID == rehearsal.source["conversation_id"].text
            && runID == rehearsal.source["run_id"].text
    }
}

struct NativeSessionSpineAcceptanceRehearsal: Identifiable, Equatable {
    let value: JSONValue
    let state: String
    let rehearsalHash: String
    let source: JSONValue
    let paths: [NativeSessionSpinePathObservation]

    var id: String { source["run_id"].text }
    var accepted: Bool { state == "ACCEPTED" }
    var recoveryRequired: Bool { state == "RECOVERY_REQUIRED" }
    var canAccept: Bool { state == "READY" && value["candidate_eligible"].flag }
    var recoveryCases: [JSONValue] { value["recovery_rehearsal"].items }
    var nextAction: String { value["next_action"].text }

    static func inspect(
        readiness: NativeSessionSpineActivationReadiness,
        stateDirectory: URL,
        grant: NativeSessionSpineAcceptanceGrant? = nil
    ) throws -> NativeSessionSpineAcceptanceRehearsal {
        guard readiness.armed,
              readiness.value["read_only"] == .bool(true),
              readiness.value["no_write"] == .bool(true),
              readiness.value["writer_active"] == .bool(false),
              readiness.value["write_authority_granted"] == .bool(false),
              readiness.value["gate"]["armed_for_exact_candidate"] == .bool(true),
              NativeTurnReceipt.isHash(readiness.candidateHash),
              NativeTurnReceipt.isHash(readiness.value["report_hash"].text) else {
            throw NativeError.message("P2k требует свежий ARMED-кандидат P2j. Ничего не принято и не записано.")
        }

        let root = stateDirectory.standardizedFileURL
        let expectedIdentityPath = root
            .appendingPathComponent("session_spine_identity", isDirectory: true)
            .appendingPathComponent("installation.json")
            .path
        guard readiness.identityPath == expectedIdentityPath else {
            throw NativeError.message("P2k identity path не принадлежит текущему private state scope. Ничего не принято.")
        }
        let paths = [
            NativeSessionSpinePathObservation.stateRoot(root),
            NativeSessionSpinePathObservation.identity(
                path: readiness.identityPath,
                identityState: readiness.identityState,
                recoveryRequired: readiness.recoveryRequired
            ),
            NativeSessionSpinePathObservation.futureDirectory(
                label: "Session Spine store",
                url: root.appendingPathComponent("session_spine_store", isDirectory: true)
            ),
            NativeSessionSpinePathObservation.futureDirectory(
                label: "Durable intent store",
                url: root.appendingPathComponent("session_spine_intents", isDirectory: true)
            ),
        ]
        let source: JSONValue = .object([
            "candidate_hash": .string(readiness.candidateHash),
            "readiness_report_hash": readiness.value["report_hash"],
            "conversation_id": readiness.source["conversation_id"],
            "user_message_id": readiness.source["user_message_id"],
            "assistant_message_id": readiness.source["assistant_message_id"],
            "run_id": readiness.source["run_id"],
            "turn_receipt_hash": readiness.source["turn_receipt_hash"],
            "preview_hash": readiness.source["preview_hash"],
            "provider": readiness.source["provider"],
            "mode": readiness.source["mode"],
        ])
        let recovery: [JSONValue] = [
            recoveryCase("before_any_write", "history_save_and_exact_readback_first"),
            recoveryCase("identity_only", "prepare_exact_durable_intent_or_stop"),
            recoveryCase("intent_prepared_spine_absent", "revalidate_sources_then_single_cas_apply"),
            recoveryCase("spine_committed_marker_missing", "no_write_replay_then_commit_marker"),
            recoveryCase("unknown_or_torn_tail", "manual_inspection_no_retry_or_repair"),
        ]
        let hashMaterial: JSONValue = .object([
            "schema": .string("proto_mind.native_session_spine_acceptance_candidate.v1"),
            "source": source,
            "paths": .array(paths.map(\.value)),
            "recovery_rehearsal": .array(recovery),
        ])
        let rehearsalHash = try hash(hashMaterial)
        let base = NativeSessionSpineAcceptanceRehearsal(
            value: .null,
            state: paths.allSatisfy(\.ready) ? "READY" : "RECOVERY_REQUIRED",
            rehearsalHash: rehearsalHash,
            source: source,
            paths: paths
        )
        let accepted = base.state == "READY" && grant?.matches(base) == true
        let state = base.state == "RECOVERY_REQUIRED" ? "RECOVERY_REQUIRED" : accepted ? "ACCEPTED" : "READY"
        let material: JSONValue = .object([
            "schema": .string("proto_mind.native_session_spine_acceptance_rehearsal.v1"),
            "state": .string(state),
            "read_only": .bool(true),
            "candidate_eligible": .bool(base.state == "READY"),
            "writer_active": .bool(false),
            "write_authority_granted": .bool(false),
            "persistence_performed": .bool(false),
            "identity_created": .bool(false),
            "intent_prepared": .bool(false),
            "spine_write_performed": .bool(false),
            "history_write_performed": .bool(false),
            "model_call_performed": .bool(false),
            "command_executed": .bool(false),
            "permission_changed": .bool(false),
            "legacy_backfill_allowed": .bool(false),
            "context_injection_changed": .bool(false),
            "source": source,
            "paths": .array(paths.map(\.value)),
            "recovery_rehearsal": .array(recovery),
            "rehearsal_hash": .string(rehearsalHash),
            "gate": .object([
                "p2j_exact_candidate_armed": .bool(true),
                "accepted_for_future_design": .bool(accepted),
                "accepted_until_relaunch": .bool(accepted),
                "persists_acceptance": .bool(false),
                "activates_writer": .bool(false),
                "authorizes_next_milestone": .bool(false),
            ]),
            "limitations": .array([
                .string("filesystem_snapshot_only"),
                .string("no_cross_store_transaction_exercised"),
                .string("no_process_crash_injected"),
                .string("no_production_writer_reachable"),
                .string("personal_turn_acceptance_is_process_only"),
            ]),
            "next_action": .string(state == "RECOVERY_REQUIRED"
                ? "inspect_existing_private_evidence_manually_no_cleanup"
                : state == "ACCEPTED"
                    ? "decide_separately_whether_a_single_forward_writer_pilot_should_exist"
                    : "explicitly_accept_this_exact_rehearsal_until_relaunch"),
        ])
        guard case .object(var fields) = material else {
            throw NativeError.message("Session Spine acceptance report имеет неверную форму.")
        }
        fields["report_hash"] = .string(try hash(material))
        return NativeSessionSpineAcceptanceRehearsal(
            value: .object(fields), state: state, rehearsalHash: rehearsalHash, source: source, paths: paths
        )
    }

    private static func recoveryCase(_ observed: String, _ response: String) -> JSONValue {
        .object([
            "observed_state": .string(observed),
            "required_response": .string(response),
            "automatic_retry": .bool(false),
            "automatic_repair": .bool(false),
            "writer_executed": .bool(false),
        ])
    }

    private static func hash(_ value: JSONValue) throws -> String {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys, .withoutEscapingSlashes]
        let data = try encoder.encode(value)
        guard let text = String(data: data, encoding: .utf8) else {
            throw NativeError.message("Session Spine acceptance report не удалось канонизировать.")
        }
        return NativeTurnReceipt.hash(text)
    }
}

struct SessionSpineAcceptanceView: View {
    @ObservedObject var model: AppModel
    let rehearsal: NativeSessionSpineAcceptanceRehearsal
    @Environment(\.dismiss) private var dismiss
    @State private var acknowledged = false

    private var current: NativeSessionSpineAcceptanceRehearsal {
        guard let value = model.sessionSpineAcceptance, value.id == rehearsal.id else { return rehearsal }
        return value
    }

    var body: some View {
        VStack(spacing: 0) {
            HStack(spacing: 12) {
                Label("Session Spine · personal rehearsal", systemImage: "checkmark.shield")
                    .font(.title3.weight(.semibold))
                Text(current.state).font(.caption2.weight(.semibold)).padding(.horizontal, 8).padding(.vertical, 4)
                    .background(statusColor.opacity(0.13), in: Capsule()).foregroundStyle(statusColor)
                Spacer()
                Button("Закрыть") { dismiss() }.keyboardShortcut(.cancelAction)
            }.padding(20)
            Divider()
            ScrollView {
                VStack(alignment: .leading, spacing: 18) {
                    VStack(alignment: .leading, spacing: 7) {
                        Text(title).font(.title2.weight(.medium))
                        Text(summary).foregroundStyle(.secondary)
                    }
                    HStack(spacing: 10) {
                        badge("writer выключен", icon: "pencil.slash")
                        badge("exact-linked turn", icon: "link")
                        badge("не сохраняется", icon: "memorychip")
                    }
                    VStack(alignment: .leading, spacing: 6) {
                        metadata("Запуск", current.source["run_id"].text)
                        metadata("Кандидат P2j", current.source["candidate_hash"].text)
                        metadata("Rehearsal", current.rehearsalHash)
                        metadata("Report", current.value["report_hash"].text)
                    }.padding(14).background(Color.primary.opacity(0.035), in: RoundedRectangle(cornerRadius: 12))

                    VStack(alignment: .leading, spacing: 10) {
                        Text("Явные private paths").font(.headline)
                        ForEach(current.paths) { path in
                            VStack(alignment: .leading, spacing: 4) {
                                HStack {
                                    Label(path.label, systemImage: path.ready ? "checkmark.circle" : "exclamationmark.triangle")
                                        .foregroundStyle(path.ready ? Color.primary : .orange)
                                    Spacer()
                                    Text(path.state).font(.caption2.monospaced()).foregroundStyle(.secondary)
                                }
                                Text(path.path).font(NativeTheme.codeFont).foregroundStyle(.secondary).textSelection(.enabled)
                                Text("ожидается \(path.expectedKind) · mode \(path.expectedMode) · scope \(path.scopeHash.prefix(12))")
                                    .font(.caption2).foregroundStyle(.tertiary)
                            }.padding(12).background(NativeTheme.bubble.opacity(0.55), in: RoundedRectangle(cornerRadius: 10))
                        }
                    }

                    VStack(alignment: .leading, spacing: 9) {
                        Text("Crash/recovery rehearsal").font(.headline)
                        ForEach(Array(current.recoveryCases.enumerated()), id: \.offset) { _, item in
                            HStack(alignment: .top, spacing: 10) {
                                Image(systemName: item["observed_state"].text == "unknown_or_torn_tail"
                                      ? "hand.raised" : "arrow.triangle.branch")
                                    .foregroundStyle(.secondary).frame(width: 18)
                                VStack(alignment: .leading, spacing: 2) {
                                    Text(recoveryLabel(item["observed_state"].text)).font(.callout.weight(.medium))
                                    Text(responseLabel(item["required_response"].text))
                                        .font(.caption).foregroundStyle(.secondary)
                                }
                            }
                        }
                    }

                    if current.recoveryRequired {
                        VStack(alignment: .leading, spacing: 10) {
                            Label("Обнаружены существующие path-evidence. Только точный P2l intent может быть показан как recovery; неизвестные байты останутся заблокированы.", systemImage: "exclamationmark.triangle")
                                .foregroundStyle(.orange)
                            Button(model.loadingSessionSpineWriter ? "Проверяем evidence…" : "Проверить P2l evidence без записи") {
                                Task { await model.openSessionSpineWriter(current) }
                            }
                            .buttonStyle(.bordered).nativeHoverSurface()
                            .disabled(model.loadingSessionSpineWriter)
                        }.padding(14).background(Color.orange.opacity(0.08), in: RoundedRectangle(cornerRadius: 12))
                    } else if current.accepted {
                        VStack(alignment: .leading, spacing: 10) {
                            Label("Этот точный rehearsal принят до перезапуска", systemImage: "checkmark.circle")
                                .foregroundStyle(.green)
                            Text("Это подтверждает только понятность будущей последовательности. Writer, identity и stores не созданы, следующий milestone не авторизован.")
                                .font(.callout).foregroundStyle(.secondary)
                            Button(model.loadingSessionSpineWriter ? "Проверяем exact sources…" : "Открыть P2l writer gate…") {
                                Task { await model.openSessionSpineWriter(current) }
                            }
                            .buttonStyle(.borderedProminent).nativeHoverSurface()
                            .disabled(model.loadingSessionSpineWriter)
                            Button("Снять acceptance") { model.revokeSessionSpineAcceptance() }
                        }.padding(14).background(Color.green.opacity(0.07), in: RoundedRectangle(cornerRadius: 12))
                    } else {
                        VStack(alignment: .leading, spacing: 11) {
                            Toggle("Понимаю: принимаю только rehearsal этого exact turn, без writer и записи", isOn: $acknowledged)
                                .toggleStyle(.checkbox)
                            Button("Принять personal rehearsal") {
                                model.acceptSessionSpineRehearsal(rehearsalHash: current.rehearsalHash)
                                acknowledged = false
                            }
                            .buttonStyle(.borderedProminent).nativeHoverSurface()
                            .disabled(!acknowledged || !current.canAccept)
                        }.padding(14).background(Color.primary.opacity(0.035), in: RoundedRectangle(cornerRadius: 12))
                    }

                    Text("P2k выполняет только локальное чтение метаданных путей и process-memory acceptance. Он не вызывает loadOrCreate, saveAndReadBack, intent prepare/apply, Session Spine writer, модель, команды или инструменты; не меняет историю, Work Session, разрешения и Context Injection. Снимок путей не заменяет повторную проверку непосредственно перед любой будущей записью.")
                        .font(.caption).foregroundStyle(.secondary)
                }.padding(22).frame(maxWidth: .infinity, alignment: .leading)
            }
        }.frame(width: 790, height: 720).background(NativeTheme.canvas)
            .font(NativeTheme.interfaceFont).buttonStyle(.nativeHover)
            .sheet(item: $model.sessionSpineWriterPreview) {
                SessionSpineWriterView(model: model, preview: $0)
            }
    }

    private var statusColor: Color {
        current.recoveryRequired ? .orange : current.accepted ? .green : .secondary
    }

    private var title: String {
        current.recoveryRequired ? "Rehearsal заблокирован существующим evidence"
            : current.accepted ? "Личный exact-linked ход принят для проектирования"
            : "Последняя проверка перед решением о writer"
    }

    private var summary: String {
        current.recoveryRequired
            ? "Read-only осмотр не может доказать чистое стартовое состояние. Ничего не исправлялось."
            : "Пути и recovery-ветви привязаны к одному ARMED-кандидату P2j. Ни одна ветвь не выполняется."
    }

    private func badge(_ text: String, icon: String) -> some View {
        Label(text, systemImage: icon).font(.caption).padding(.horizontal, 10).padding(.vertical, 7)
            .background(NativeTheme.bubble, in: Capsule())
    }

    private func metadata(_ label: String, _ value: String) -> some View {
        HStack(alignment: .firstTextBaseline) {
            Text(label).foregroundStyle(.secondary).frame(width: 120, alignment: .leading)
            Text(value).font(NativeTheme.codeFont).textSelection(.enabled)
        }.font(.caption)
    }

    private func recoveryLabel(_ value: String) -> String {
        switch value {
        case "before_any_write": return "До первой записи"
        case "identity_only": return "Identity уже durable, intent отсутствует"
        case "intent_prepared_spine_absent": return "Intent prepared, Spine ещё отсутствует"
        case "spine_committed_marker_missing": return "Spine committed, marker ответа потерян"
        case "unknown_or_torn_tail": return "UNKNOWN или torn tail"
        default: return value
        }
    }

    private func responseLabel(_ value: String) -> String {
        switch value {
        case "history_save_and_exact_readback_first": return "Сначала сохранить историю и получить точный readback."
        case "prepare_exact_durable_intent_or_stop": return "Подготовить только exact intent либо остановиться."
        case "revalidate_sources_then_single_cas_apply": return "Повторно сверить источники перед одним CAS apply."
        case "no_write_replay_then_commit_marker": return "Сначала no-write replay, затем только missing marker."
        case "manual_inspection_no_retry_or_repair": return "Остановиться: только ручная проверка, без retry/repair."
        default: return value
        }
    }
}
