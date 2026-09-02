import SwiftUI

struct SkillTaskView: View {
    @ObservedObject var model: SkillTaskModel
    @State private var acknowledgement = false
    var body: some View {
        VStack(spacing: 0) {
            HStack {
                Label("Задача с навыком", systemImage: "list.bullet.clipboard").font(.title2.weight(.semibold))
                Spacer()
                if model.loading { ProgressView().controlSize(.small) }
                Button { model.close() } label: { Image(systemName: "xmark") }.keyboardShortcut(.cancelAction)
            }.padding(22)
            Divider()
            ScrollView {
                VStack(alignment: .leading, spacing: 18) {
                    Text("Навык станет ориентиром для обычного запроса, а не исполняемым сценарием. Подготовка не вызывает модель и не включает инструменты.").foregroundStyle(.secondary)
                    Text(model.scope.workspace).font(.caption).textSelection(.enabled)
                    if let error = model.error { Label(error, systemImage: "exclamationmark.triangle").foregroundStyle(.orange) }
                    Text("Цель оператора").font(.headline)
                    TextEditor(text: $model.goal).font(NativeTheme.interfaceFont).frame(height: 90).padding(8)
                        .background(Color.primary.opacity(0.04), in: RoundedRectangle(cornerRadius: 10)).accessibilityLabel("Цель задачи с навыком")
                    Text("Готово, когда…").font(.headline)
                    TextEditor(text: $model.criteriaText).font(NativeTheme.interfaceFont).frame(height: 90).padding(8)
                        .background(Color.primary.opacity(0.04), in: RoundedRectangle(cornerRadius: 10)).accessibilityLabel("Критерии задачи с навыком")
                    Text("До 8 наблюдаемых критериев, каждый на отдельной строке. Они не становятся проверенными автоматически.").font(.caption).foregroundStyle(.secondary)
                    Button("Проверить подготовку") { Task { await model.refresh() } }.disabled(model.locked)
                    if let preview = model.preview {
                        Label(preview.ready ? "Готово к ручной отправке" : "Нужно дополнить или проверить", systemImage: preview.ready ? "checkmark.circle" : "info.circle").font(.headline)
                        if !preview.body.isNull { SkillTaskContractView(value: preview.body) }
                        ForEach(Array(preview.reasons.enumerated()), id: \.offset) { _, reason in Text(reason).font(.callout).foregroundStyle(.orange) }
                        DisclosureGroup("Условия и ограничения") {
                            ForEach(Array(preview.raw["warnings"].items.enumerated()), id: \.offset) { _, warning in Text(warning.text).font(.caption).padding(.vertical, 3) }
                        }
                    }
                }.padding(22)
            }
            Divider()
            VStack(alignment: .leading, spacing: 10) {
                Toggle("Просмотрел цель, критерии и процедуру. Подготовить только черновик", isOn: $acknowledgement).toggleStyle(.checkbox)
                HStack {
                    Text("Send отдельно. Права доступа не меняются.").font(.caption).foregroundStyle(.secondary)
                    Spacer()
                    Button("Применить к черновику") { model.use(acknowledgement: acknowledgement) }
                        .disabled(!model.ready || !acknowledgement).buttonStyle(.borderedProminent).nativeHoverSurface()
                }
            }.padding(20)
        }.frame(width: 850, height: 760).background(NativeTheme.canvas)
            .font(NativeTheme.interfaceFont).buttonStyle(.nativeHover).disclosureGroupStyle(NativeDisclosureStyle())
            .onChange(of: model.goal) { model.invalidate(); acknowledgement = false }
            .onChange(of: model.criteriaText) { model.invalidate(); acknowledgement = false }
    }
}

struct SkillTaskContractView: View {
    let value: JSONValue
    var bodyContent: JSONValue { value["contract"] }
    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(bodyContent["name"].text).font(.headline)
            Text(bodyContent["summary"].text)
            Text("Когда применять: \(bodyContent["trigger"].text)").font(.callout)
            ForEach([("preconditions", "Предусловия"), ("steps", "Предлагаемые шаги"), ("permissions", "Заявленные потребности в доступе"), ("verification", "Как проверять"), ("known_failure_modes", "Возможные ошибки")], id: \.0) { key, title in
                DisclosureGroup(title) {
                    ForEach(Array(bodyContent[key].items.enumerated()), id: \.offset) { index, row in Text("\(index + 1). \(row.text)").font(.callout).padding(.vertical, 3) }
                }
            }
            Text("Происхождение проверено, эффективность не оценена. Общая библиотека навыков; применение только к явно выбранной задаче.").font(.caption).foregroundStyle(.secondary)
        }.padding(16).background(Color.primary.opacity(0.035), in: RoundedRectangle(cornerRadius: 12)).textSelection(.enabled)
    }
}

struct PendingSkillTaskView: View {
    @ObservedObject var model: AppModel
    var body: some View {
        if let task = model.pendingSkillTask {
            HStack(spacing: 8) {
                Image(systemName: model.skillTaskMatchesDraft ? "list.bullet.clipboard" : "exclamationmark.triangle")
                Text(task.body["skill_name"].text).lineLimit(1)
                Text(model.skillTaskMatchesDraft ? "Подготовлен · не отправлен" : "Перепроверьте изменения").foregroundStyle(.secondary).lineLimit(1)
                Spacer(minLength: 4)
                Button("Просмотр") { Task { await model.openSkillTask(skillID: task.skillID) } }
                Button { model.removeSkillTask() } label: { Image(systemName: "xmark") }.help("Убрать навык из следующего запроса; цель и критерии сохранятся")
            }.font(.caption).padding(10).background(Color.primary.opacity(0.045), in: RoundedRectangle(cornerRadius: 10))
                .disabled(model.busy).accessibilityElement(children: .contain)
        }
    }
}
