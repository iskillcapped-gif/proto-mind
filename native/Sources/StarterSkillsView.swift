import SwiftUI

struct StarterSkillsSnapshot: Equatable {
    static let ids: Set<String> = ["builtin.project_orientation", "builtin.verified_change", "builtin.failure_diagnosis", "builtin.work_handoff"]
    let value: JSONValue
    var pack: JSONValue { value["pack"] }

    init(_ value: JSONValue) throws {
        let pack = value["pack"]
        guard case .object(let envelope) = value,
              Set(envelope.keys) == ["schema", "read_only", "no_execution", "pack", "sha256", "hash_material"],
              value["schema"] == .string("proto_mind.native_starter_skills.v1"),
              value["read_only"] == .bool(true), value["no_execution"] == .bool(true),
              case .object(let fields) = pack,
              Set(fields.keys) == ["schema", "id", "version", "origin", "learned_from_user", "executable", "skills"],
              pack["schema"] == .string("proto_mind.starter_skill_pack.v1"), pack["id"] == .string("proto_mind.starter_skills"),
              pack["version"] == .string("1.0.0"), pack["origin"] == .string("bundled"),
              pack["learned_from_user"] == .bool(false), pack["executable"] == .bool(false),
              case .array(let skills) = pack["skills"], skills.count == 4,
              Set(skills.map { $0["id"].text }) == Self.ids,
              value["hash_material"].text.utf8.count <= 40_000,
              try value["sha256"] == .string(verifyCanonicalMaterial(value["hash_material"], expected: pack)) else {
            throw NativeError.message("Не удалось проверить встроенный набор навыков. Ничего не запускалось.")
        }
        let decoder = JSONDecoder(); decoder.keyDecodingStrategy = .convertFromSnakeCase
        for skill in skills {
            guard case .object(let row) = skill, Set(row.keys) == ["id", "contract"] else { throw NativeAutoSkillsReport.error() }
            let contract = try decoder.decode(NativeSkillFields.self, from: JSONEncoder().encode(skill["contract"]))
            guard contract.complete, contract.json == skill["contract"] else { throw NativeAutoSkillsReport.error() }
        }
        self.value = value
    }

    static func title(_ id: String) -> String {
        switch id {
        case "builtin.project_orientation": return "Разобраться в проекте"
        case "builtin.verified_change": return "Внести изменение и проверить"
        case "builtin.failure_diagnosis": return "Исследовать ошибку"
        case "builtin.work_handoff": return "Подготовить продолжение работы"
        default: return id
        }
    }
}

struct StarterSkillsView: View {
    let client: BridgeClient
    @Environment(\.dismiss) private var dismiss
    @State private var snapshot: StarterSkillsSnapshot?
    @State private var error = ""

    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            HStack {
                Label("Встроенные навыки", systemImage: "square.stack.3d.up").font(.title3.weight(.semibold))
                Spacer()
                Button("Закрыть") { dismiss() }.keyboardShortcut(.cancelAction)
            }
            Text("Готовые процедуры приложения, не воспоминания и не выученные уроки. Auto подбирает их по вашей задаче; они не запускаются сами и не расширяют доступ.")
                .foregroundStyle(.secondary)
            if let snapshot {
                Text("Набор v\(snapshot.pack["version"].text) · 4 навыка · SHA \(snapshot.value["sha256"].text.prefix(12))")
                    .font(.caption).foregroundStyle(.secondary).textSelection(.enabled)
                ScrollView {
                    VStack(alignment: .leading, spacing: 16) {
                        ForEach(snapshot.pack["skills"].items, id: \.["id"].text) { skill in
                            DisclosureGroup {
                                VStack(alignment: .leading, spacing: 10) {
                                    Text(skill["contract"]["summary"].text).textSelection(.enabled)
                                    Text("Когда подходит: " + skill["contract"]["trigger"].text).textSelection(.enabled)
                                    group("Предусловия", skill["contract"]["preconditions"])
                                    group("Порядок работы", skill["contract"]["steps"])
                                    group("Разрешения", skill["contract"]["permissions"])
                                    group("Проверка результата", skill["contract"]["verification"])
                                    group("Ограничения", skill["contract"]["known_failure_modes"])
                                }.font(.system(size: 13)).foregroundStyle(.secondary).padding(.top, 8)
                            } label: { Text(StarterSkillsSnapshot.title(skill["id"].text)).font(.body.weight(.medium)) }
                            Divider()
                        }
                    }.padding(.trailing, 6)
                }
            } else if !error.isEmpty {
                Text(error).foregroundStyle(.orange).textSelection(.enabled)
                Spacer()
            } else { ProgressView("Читаю локальный набор…"); Spacer() }
            Text("Только просмотр. Личная библиотека, память и настройки не меняются. Отправка задачи остаётся отдельным действием.")
                .font(.caption).foregroundStyle(.secondary)
        }.padding(24).frame(width: 740, height: 620)
            .task {
                do { snapshot = try StarterSkillsSnapshot(await client.request("starter_skills")) }
                catch { self.error = error.localizedDescription }
            }
    }

    private func group(_ title: String, _ items: JSONValue) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(title).fontWeight(.medium)
            ForEach(Array(items.items.enumerated()), id: \.offset) { index, value in
                Text("\(index + 1). \(value.text)").textSelection(.enabled)
            }
        }
    }
}
