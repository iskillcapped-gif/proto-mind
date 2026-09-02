import CryptoKit
import SwiftUI

struct NativeAutoSkillsReport: Equatable {
    let value: JSONValue
    var state: String { value["state"].text }
    var selected: [JSONValue] { value["selected"].items }
    var title: String {
        switch state {
        case "ready": return "Навыки · выбор при отправке"
        case "selecting": return "Подбираю подходящий навык"
        case "selected": return "Навыки · " + selected.map { $0["skill_name"].text }.joined(separator: ", ")
        case "no_match": return "Навыки · для этой задачи не нужны"
        case "empty": return "Навыки · нет активных проверенных процедур"
        case "unavailable": return "Навыки · источники недоступны"
        default: return "Подбор навыков не завершён"
        }
    }

    init(_ value: JSONValue, run: JSONValue? = nil) throws {
        let v2 = value["schema"] == .string("proto_mind.native_auto_skills.v2")
        var fields: Set<String> = ["schema", "conversation_id", "workspace", "goal_sha256", "access_mode", "state",
            "catalog_count", "eligible_count", "excluded_count", "catalog_truncated", "catalog_hash", "source_hashes",
            "selected", "selector_attempted", "selector_model", "selector_effort", "reason", "suggested_checks",
            "quality_verification", "permission_granted", "automatic_learning"]
        if v2 { fields.formUnion(["starter_pack", "bundled_count", "learned_count"]) }
        let stores: Set<String> = ["skills.jsonl", "persistent_memory.json", "context_injection.json"]
        guard case .object(let raw) = value, Set(raw.keys) == fields,
              ["proto_mind.native_auto_skills.v1", "proto_mind.native_auto_skills.v2"].contains(value["schema"].text), UUID(uuidString: value["conversation_id"].text) != nil,
              ["ready", "selecting", "selected", "no_match", "empty", "unavailable", "failed"].contains(value["state"].text),
              ["chat", "full_access"].contains(value["access_mode"].text),
              decisionHashValue(value["goal_sha256"].text), decisionHashValue(value["catalog_hash"].text),
              ["catalog_count", "eligible_count", "excluded_count"].allSatisfy({ Self.count(value[$0]) }),
              value["catalog_count"].integer <= 32, value["catalog_count"].integer <= value["eligible_count"].integer,
              value["catalog_truncated"] == .bool(value["eligible_count"].integer > value["catalog_count"].integer),
              case .object(let hashes) = value["source_hashes"], Set(hashes.keys).isSubset(of: stores),
              hashes.values.allSatisfy({ decisionHashValue($0.text) }),
              value["state"] == .string("unavailable") || Set(hashes.keys) == stores,
              case .bool(let attempted) = value["selector_attempted"],
              Self.plain(value["selector_model"], limit: 160, empty: true),
              Self.plain(value["selector_effort"], limit: 20, empty: true),
              ["", "none", "minimal", "low", "medium", "high", "xhigh", "max", "ultra"].contains(value["selector_effort"].text),
              Self.plain(value["reason"], limit: 600),
              case .array(let selected) = value["selected"], selected.count <= 2, selected.count <= value["catalog_count"].integer,
              case .array(let checks) = value["suggested_checks"], checks.count <= 4,
              checks.allSatisfy({ Self.plain($0, limit: 300) }), Set(checks.map(\.text)).count == checks.count,
              checks.isEmpty || !selected.isEmpty,
              value["quality_verification"] == .string("not_assessed"), value["permission_granted"] == .bool(false),
              value["automatic_learning"] == .bool(false) else { throw Self.error() }
        if v2 {
            let pack = value["starter_pack"]
            guard case .object(let metadata) = pack, Set(metadata.keys) == ["id", "version", "sha256"],
                  pack["id"] == .string("proto_mind.starter_skills"),
                  pack["version"].text.range(of: "^[0-9]{1,3}\\.[0-9]{1,3}\\.[0-9]{1,3}$", options: .regularExpression) != nil,
                  decisionHashValue(pack["sha256"].text), Self.count(value["bundled_count"]), Self.count(value["learned_count"]),
                  [0, 4].contains(value["bundled_count"].integer), value["learned_count"].integer <= 5000,
                  value["eligible_count"].integer == value["bundled_count"].integer + value["learned_count"].integer else { throw Self.error() }
        }
        if !value["workspace"].isNull {
            guard Self.plain(value["workspace"]["path"], limit: 4096), value["workspace"]["path"].text.hasPrefix("/"),
                  ProjectMemoryScope(conversationID: UUID(), workspace: value["workspace"]["path"].text).matches(value["workspace"]) else { throw Self.error() }
        }
        for row in selected {
            if v2 && row["origin"] == .string("bundled") {
                guard case .object(let reference) = row,
                      Set(reference.keys) == ["origin", "skill_id", "skill_name", "version", "pack_id", "pack_hash", "contract_hash"],
                      StarterSkillsSnapshot.ids.contains(row["skill_id"].text), Self.plain(row["skill_name"], limit: 800),
                      row["pack_id"] == value["starter_pack"]["id"], row["pack_hash"] == value["starter_pack"]["sha256"],
                      row["version"] == value["starter_pack"]["version"], decisionHashValue(row["contract_hash"].text),
                      value["bundled_count"].integer == 4 else { throw Self.error() }
                continue
            }
            var referenceFields: Set<String> = ["skill_id", "skill_name", "skill_record_hash", "source_lesson_id", "provenance_hash", "contract_hash", "lifecycle_state"]
            if v2 { referenceFields.insert("origin") }
            guard case .object(let reference) = row,
                  Set(reference.keys) == referenceFields,
                  !v2 || (row["origin"] == .string("learned") && !row["skill_id"].text.hasPrefix("builtin.") && value["learned_count"].integer > 0),
                  ["skill_id", "source_lesson_id"].allSatisfy({ row[$0].text.range(of: "^[A-Za-z0-9_.:-]{1,200}$", options: .regularExpression) != nil }),
                  Self.plain(row["skill_name"], limit: 800),
                  ["skill_record_hash", "provenance_hash", "contract_hash"].allSatisfy({ decisionHashValue(row[$0].text) }),
                  ["active_verified", "active_restored_verified"].contains(row["lifecycle_state"].text) else { throw Self.error() }
        }
        guard Set(selected.map { $0["skill_id"].text }).count == selected.count,
              !selected.isEmpty == (value["state"] == .string("selected")),
              !["ready", "empty", "unavailable"].contains(value["state"].text) || !attempted,
              !["selecting", "selected", "no_match"].contains(value["state"].text) || attempted,
              !["selected", "no_match"].contains(value["state"].text) || !value["selector_model"].text.isEmpty else { throw Self.error() }
        if let run {
            guard value["conversation_id"] == run["conversation_id"], value["workspace"] == run["workspace"],
                  value["goal_sha256"] == run["input_sha256"], value["access_mode"] == run["access_mode"],
                  run["provider"] == .string("codex") else { throw Self.error() }
        }
        self.value = value
    }

    func matches(conversation: UUID, text: String, workspace: String?, mode: String) -> Bool {
        let hash = SHA256.hash(data: Data(text.utf8)).map { String(format: "%02x", $0) }.joined()
        let workspaceOK = workspace.map {
            ProjectMemoryScope(conversationID: conversation, workspace: $0).matches(value["workspace"])
        } ?? value["workspace"].isNull
        return UUID(uuidString: value["conversation_id"].text) == conversation && value["goal_sha256"] == .string(hash)
            && value["access_mode"] == .string(mode) && workspaceOK
    }

    static func error() -> NativeError { .message("Отчёт автовыбора навыков не прошёл проверку. Автоповтора нет; проверьте журнал.") }
    private static func count(_ value: JSONValue) -> Bool {
        if case .number(let number) = value { return number.isFinite && number.rounded() == number && (0...5004).contains(number) }
        return false
    }
    private static func plain(_ value: JSONValue, limit: Int, empty: Bool = false) -> Bool {
        guard case .string(let text) = value else { return false }
        return (empty || !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty) && text.unicodeScalars.count <= limit
            && !text.unicodeScalars.contains { $0.value < 32 }
    }
}

struct AutoSkillsMenu: View {
    @ObservedObject var model: AppModel
    @State private var showStarters = false
    var body: some View {
        Menu {
            Toggle("Подбирать навыки автоматически", isOn: Binding(get: { model.selected?.autoSkillsEnabled != false }, set: model.setAutoSkillsEnabled))
            Text("Один короткий запрос Codex для подбора навыков")
            Text("Без новых разрешений и автоматического обучения")
            if model.pendingSkillTask != nil {
                Text("На этот ход приоритет у вашего ручного выбора")
                Button("Убрать ручной выбор", action: model.removeSkillTask)
            }
            Divider()
            Button("Встроенный набор…") { showStarters = true }
            Button("Личная библиотека навыков…") { Task { await model.showLibrary(.skills) } }
        } label: {
            Label(model.pendingSkillTask != nil ? "Навыки · Вручную" : model.selected?.autoSkillsEnabled != false ? "Навыки · Авто" : "Навыки · Выкл",
                  systemImage: "square.stack.3d.up").font(.system(size: 12))
        }.menuStyle(.borderlessButton).fixedSize().nativeHoverSurface()
            .disabled(model.busy || model.selected?.archived == true)
            .help("Подбор по смыслу задачи через выбранную модель. Отбор без инструментов; затем обычный запрос с текущими правами. Можно отключить для этого диалога.")
            .accessibilityLabel("Автоматический выбор навыков")
            .sheet(isPresented: $showStarters) { StarterSkillsView(client: model.client) }
    }
}

struct AutoSkillsReportView: View {
    let report: NativeAutoSkillsReport
    var body: some View {
        DisclosureGroup {
            VStack(alignment: .leading, spacing: 8) {
                if ["empty", "unavailable"].contains(report.state) {
                    Text("Запрос идёт обычным путём, без автоматического навыка. Память, настройки и библиотека не изменены.")
                } else { Text(report.value["reason"].text).textSelection(.enabled) }
                ForEach(report.selected, id: \.["skill_id"].text) { row in
                    Text("\(row["skill_name"].text) · \(row["origin"] == .string("bundled") ? "Встроенный, v" + row["version"].text : "Из опыта, с проверенным происхождением") · \(row["contract_hash"].text.prefix(12))").textSelection(.enabled)
                }
                if !report.value["suggested_checks"].items.isEmpty {
                    Text("Модель предложила проверить:").fontWeight(.medium)
                    ForEach(report.value["suggested_checks"].items.map(\.text), id: \.self) { Text("• " + $0).textSelection(.enabled) }
                }
                Text("Каталог: \(report.value["catalog_count"].integer) · исключено: \(report.value["excluded_count"].integer). Личная библиотека общая, не отдельная память проекта.")
                if report.value["schema"] == .string("proto_mind.native_auto_skills.v2") {
                    Text("Доступно встроенных: \(report.value["bundled_count"].integer) · из опыта: \(report.value["learned_count"].integer). Встроенные процедуры созданы разработчиками, а не выучены из ваших разговоров.")
                }
                if report.value["catalog_truncated"].flag { Text("Каталог ограничен 32 записями; в v2 четыре места зарезервированы для встроенных навыков, остальные для первых проверенных личных записей по ID.").foregroundStyle(.orange) }
                if report.value["selector_attempted"].flag {
                    Text("Отбор: \(report.value["selector_model"].text) · \(report.value["selector_effort"].text). Без инструментов, отдельный запрос в рамках подписки.")
                }
                Text("Происхождение проверено, эффективность не оценена. Проверки модели не являются вашей приёмкой. Навыки не исполняются как скрипты и не дают дополнительных прав.")
            }.font(.caption).foregroundStyle(.secondary).padding(.top, 8)
        } label: {
            Label(report.title, systemImage: "square.stack.3d.up").lineLimit(1)
        }.font(.system(size: 12)).foregroundStyle(.secondary)
    }
}
