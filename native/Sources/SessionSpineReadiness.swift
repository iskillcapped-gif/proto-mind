import SwiftUI

struct NativeSessionSpinePilotGrant: Equatable {
    let candidateHash: String
    let conversationID: String
    let runID: String
    let previewHash: String

    init(readiness: NativeSessionSpineActivationReadiness) throws {
        guard readiness.canArm else {
            throw NativeError.message("Session Spine readiness не допускает локальную подготовку. Ничего не включено.")
        }
        candidateHash = readiness.candidateHash
        conversationID = readiness.source["conversation_id"].text
        runID = readiness.source["run_id"].text
        previewHash = readiness.source["preview_hash"].text
    }

    func matches(_ readiness: NativeSessionSpineActivationReadiness) -> Bool {
        candidateHash == readiness.candidateHash
            && conversationID == readiness.source["conversation_id"].text
            && runID == readiness.source["run_id"].text
            && previewHash == readiness.source["preview_hash"].text
    }
}

struct NativeSessionSpineActivationReadiness: Identifiable, Equatable {
    let value: JSONValue
    let candidateHash: String
    let state: String
    let identityState: String
    let recoveryState: String
    let source: JSONValue

    var id: String { source["run_id"].text }
    var armed: Bool { state == "ARMED" }
    var recoveryRequired: Bool { state == "RECOVERY_REQUIRED" }
    var canArm: Bool { state == "INACTIVE" && value["candidate_eligible"].flag }
    var nextAction: String { value["next_action"].text }
    var identityPath: String { value["identity"]["path"].text }
    var safeguards: [String] { value["required_future_safeguards"].items.map(\.text) }

    static func inspect(
        preview: NativeSessionSpinePreview,
        identity: NativeSessionSpineInstallationIdentity?,
        identityPath: URL,
        identityError: String? = nil,
        grant: NativeSessionSpinePilotGrant? = nil
    ) throws -> NativeSessionSpineActivationReadiness {
        guard identityError == nil || identity == nil,
              identity.map({ !$0.permissionGranted && !$0.executionAuthorityGranted }) ?? true else {
            throw NativeError.message("Session Spine identity widened its non-authorizing boundary.")
        }
        let identityState: String
        let recoveryState: String
        if identityError != nil {
            identityState = "recovery_required"
            recoveryState = "manual_inspection_required"
        } else if identity != nil {
            identityState = "verified"
            recoveryState = "identity_ready"
        } else {
            identityState = "missing"
            recoveryState = "clean_uninitialized"
        }
        let source: JSONValue = .object([
            "conversation_id": preview.source["conversation_id"],
            "user_message_id": preview.source["user_message_id"],
            "assistant_message_id": preview.source["assistant_message_id"],
            "run_id": preview.source["run_id"],
            "run_fingerprint": preview.source["run_fingerprint"],
            "reference_hash": preview.source["reference_hash"],
            "turn_receipt_hash": preview.source["turn_receipt_hash"],
            "preview_hash": preview.value["preview_hash"],
            "provider": preview.source["provider"],
            "mode": preview.source["mode"],
        ])
        let candidateMaterial: JSONValue = .object([
            "schema": .string("proto_mind.native_session_spine_activation_candidate.v1"),
            "source": source,
            "identity_state": .string(identityState),
            "identity_hash": identity.map { .string($0.identityHash) } ?? .null,
        ])
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys, .withoutEscapingSlashes]
        let encoded = try encoder.encode(candidateMaterial)
        guard let canonical = String(data: encoded, encoding: .utf8) else {
            throw NativeError.message("Session Spine readiness candidate не удалось канонизировать.")
        }
        let candidateHash = NativeTurnReceipt.hash(canonical)
        let eligible = identityError == nil
        let base = NativeSessionSpineActivationReadiness(
            value: .null,
            candidateHash: candidateHash,
            state: eligible ? "INACTIVE" : "RECOVERY_REQUIRED",
            identityState: identityState,
            recoveryState: recoveryState,
            source: source
        )
        let armed = eligible && grant?.matches(base) == true
        let state = identityError != nil ? "RECOVERY_REQUIRED" : armed ? "ARMED" : "INACTIVE"
        let nextAction: String
        switch state {
        case "RECOVERY_REQUIRED": nextAction = "inspect_identity_bytes_manually_no_cleanup"
        case "ARMED": nextAction = "run_separate_personal_acceptance_before_any_writer_activation"
        default: nextAction = "explicitly_arm_this_exact_turn_until_relaunch"
        }
        let material: JSONValue = .object([
            "schema": .string("proto_mind.native_session_spine_activation_readiness.v1"),
            "state": .string(state),
            "read_only": .bool(true),
            "candidate_eligible": .bool(eligible),
            "writer_active": .bool(false),
            "write_authority_granted": .bool(false),
            "persistent_opt_in": .bool(false),
            "no_write": .bool(true),
            "no_default_spine_path": .bool(true),
            "no_default_intent_path": .bool(true),
            "no_identity_creation": .bool(true),
            "no_model_call": .bool(true),
            "no_command_execution": .bool(true),
            "no_tool_replay": .bool(true),
            "no_migration": .bool(true),
            "legacy_backfill_allowed": .bool(false),
            "context_injection_changed": .bool(false),
            "source": source,
            "candidate_hash": .string(candidateHash),
            "identity": .object([
                "state": .string(identityState),
                "recovery_state": .string(recoveryState),
                "path": .string(identityPath.path),
                "owner_id": identity.map { .string($0.ownerID) } ?? .null,
                "identity_hash": identity.map { .string($0.identityHash) } ?? .null,
                "error": identityError.map(JSONValue.string) ?? .null,
            ]),
            "gate": .object([
                "explicit_operator_opt_in_required": .bool(true),
                "armed_for_exact_candidate": .bool(armed),
                "resets_on_relaunch": .bool(true),
                "resets_on_context_change": .bool(true),
                "activates_writer": .bool(false),
            ]),
            "required_future_safeguards": .array([
                .string("exact_history_save_and_readback"),
                .string("stable_non_authorizing_installation_identity"),
                .string("durable_intent_before_spine_apply"),
                .string("lost_response_recovery_without_duplicate_write"),
                .string("one_new_personal_exact_linked_turn_acceptance"),
                .string("manual_recovery_for_unknown_tail"),
            ]),
            "next_action": .string(nextAction),
        ])
        let materialData = try encoder.encode(material)
        guard let materialText = String(data: materialData, encoding: .utf8) else {
            throw NativeError.message("Session Spine readiness report не удалось канонизировать.")
        }
        guard case .object(var fields) = material else {
            throw NativeError.message("Session Spine readiness report имеет неверную форму.")
        }
        fields["report_hash"] = .string(NativeTurnReceipt.hash(materialText))
        return NativeSessionSpineActivationReadiness(
            value: .object(fields),
            candidateHash: candidateHash,
            state: state,
            identityState: identityState,
            recoveryState: recoveryState,
            source: source
        )
    }
}

struct SessionSpineReadinessView: View {
    @ObservedObject var model: AppModel
    let readiness: NativeSessionSpineActivationReadiness
    @Environment(\.dismiss) private var dismiss
    @State private var acknowledged = false

    private var current: NativeSessionSpineActivationReadiness {
        guard let value = model.sessionSpineReadiness, value.id == readiness.id else { return readiness }
        return value
    }

    var body: some View {
        VStack(spacing: 0) {
            HStack(spacing: 12) {
                Label("Session Spine · readiness", systemImage: "lock.shield")
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
                        badge("только этот ход", icon: "scope")
                        badge("до перезапуска", icon: "arrow.clockwise")
                    }
                    VStack(alignment: .leading, spacing: 6) {
                        metadata("Запуск", current.source["run_id"].text)
                        metadata("Провайдер и режим", "\(current.source["provider"].text) · \(current.source["mode"].text)")
                        metadata("Кандидат", current.candidateHash)
                        metadata("Installation identity", current.identityState)
                        metadata("Recovery", current.recoveryState)
                        metadata("Readiness receipt", current.value["report_hash"].text)
                    }.padding(14).background(Color.primary.opacity(0.035), in: RoundedRectangle(cornerRadius: 12))

                    VStack(alignment: .leading, spacing: 9) {
                        Text("Будущие обязательные предохранители").font(.headline)
                        ForEach(current.safeguards, id: \.self) { item in
                            Label(safeguardLabel(item), systemImage: "checkmark.shield")
                                .font(.callout).foregroundStyle(.secondary)
                        }
                    }

                    if current.recoveryRequired {
                        VStack(alignment: .leading, spacing: 7) {
                            Label("Нужна ручная проверка", systemImage: "exclamationmark.triangle")
                                .font(.headline).foregroundStyle(.orange)
                            Text("Существующие identity-байты не прошли read-only проверку. Proto-Mind не исправлял, не удалял и не пересоздавал их.")
                            Text(current.identityPath).font(NativeTheme.codeFont).textSelection(.enabled)
                        }.padding(14).background(Color.orange.opacity(0.08), in: RoundedRectangle(cornerRadius: 12))
                    } else if current.armed {
                        VStack(alignment: .leading, spacing: 10) {
                            Label("Локальная подготовка действует только для этого точного кандидата", systemImage: "checkmark.circle")
                                .foregroundStyle(.green)
                            Text("Она не переживёт перезапуск и не включает writer. Следующий этап всё равно потребует отдельной персональной приёмки нового exact-linked хода.")
                                .font(.callout).foregroundStyle(.secondary)
                            Button("Открыть personal acceptance rehearsal…") {
                                model.openSessionSpineAcceptance(current)
                            }
                            .buttonStyle(.borderedProminent).nativeHoverSurface()
                            Button("Снять локальную подготовку") { model.revokeSessionSpinePilot() }
                        }.padding(14).background(Color.green.opacity(0.07), in: RoundedRectangle(cornerRadius: 12))
                    } else {
                        VStack(alignment: .leading, spacing: 11) {
                            Toggle("Понимаю: это только per-launch readiness, без записи Session Spine", isOn: $acknowledged)
                                .toggleStyle(.checkbox)
                            Button("Подготовить этот точный ход") {
                                model.armSessionSpinePilot(candidateHash: current.candidateHash)
                                acknowledged = false
                            }
                            .buttonStyle(.borderedProminent).nativeHoverSurface()
                            .disabled(!acknowledged || !current.canArm)
                        }.padding(14).background(Color.primary.opacity(0.035), in: RoundedRectangle(cornerRadius: 12))
                    }

                    Text("Readiness не создаёт installation identity, intent или Session Spine store, не вызывает модель, команды либо инструменты и не меняет историю, Work Session, разрешения или Context Injection. Legacy turns не становятся кандидатами и никогда не backfill-ятся по времени или соседству.")
                        .font(.caption).foregroundStyle(.secondary)
                }.padding(22).frame(maxWidth: .infinity, alignment: .leading)
            }
        }.frame(width: 760, height: 690).background(NativeTheme.canvas)
            .font(NativeTheme.interfaceFont).buttonStyle(.nativeHover)
            .sheet(item: $model.sessionSpineAcceptance) {
                SessionSpineAcceptanceView(model: model, rehearsal: $0)
            }
    }

    private var statusColor: Color {
        if current.recoveryRequired { return .orange }
        return current.armed ? .green : .secondary
    }

    private var title: String {
        if current.recoveryRequired { return "Пилот заблокирован без автоматического ремонта" }
        return current.armed ? "Точный кандидат подготовлен" : "Writer остаётся выключенным"
    }

    private var summary: String {
        if current.recoveryRequired {
            return "Read-only inspection обнаружил неоднозначное recovery-состояние. Ни одна запись не выполнялась."
        }
        if current.armed {
            return "Явный opt-in связан с одним проверенным turn receipt и исчезнет при смене контекста или перезапуске."
        }
        return "Можно подготовить один уже завершённый exact-linked ход к отдельной будущей приёмке. Это не разрешение на запись."
    }

    private func badge(_ text: String, icon: String) -> some View {
        Label(text, systemImage: icon).font(.caption).padding(.horizontal, 10).padding(.vertical, 7)
            .background(NativeTheme.bubble, in: Capsule())
    }

    private func metadata(_ label: String, _ value: String) -> some View {
        HStack(alignment: .firstTextBaseline) {
            Text(label).foregroundStyle(.secondary).frame(width: 150, alignment: .leading)
            Text(value).font(NativeTheme.codeFont).textSelection(.enabled)
        }.font(.caption)
    }

    private func safeguardLabel(_ value: String) -> String {
        switch value {
        case "exact_history_save_and_readback": return "точное сохранение и readback истории"
        case "stable_non_authorizing_installation_identity": return "стабильная identity без полномочий"
        case "durable_intent_before_spine_apply": return "durable intent до любой записи"
        case "lost_response_recovery_without_duplicate_write": return "recovery без повторной записи"
        case "one_new_personal_exact_linked_turn_acceptance": return "отдельная приёмка нового личного хода"
        case "manual_recovery_for_unknown_tail": return "ручная проверка UNKNOWN tail"
        default: return value
        }
    }
}
