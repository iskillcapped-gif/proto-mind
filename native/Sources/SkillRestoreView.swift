import SwiftUI

struct SkillRestoreView: View {
    @ObservedObject var model: SkillRestoreModel
    @State private var token = ""
    @State private var acknowledgement = false
    var body: some View {
        VStack(spacing: 0) {
            HStack(spacing: 12) {
                Image(systemName: "arrow.uturn.backward.circle").font(.title2)
                VStack(alignment: .leading, spacing: 4) {
                    Text("Восстановление навыка").font(.title2.weight(.semibold))
                    Text("Возврат доступности, не запуск и не доказательство качества").font(.caption).foregroundStyle(.secondary)
                }
                Spacer()
                if model.loading || model.committing { ProgressView().controlSize(.small) }
                Button { Task { await model.refresh() } } label: { Image(systemName: "arrow.clockwise") }.disabled(model.locked).help("Обновить и сбросить подтверждение")
                Button { model.close() } label: { Image(systemName: "xmark") }.disabled(model.committing).keyboardShortcut(.cancelAction)
            }.padding(22)
            Divider()
            ScrollViewReader { scroll in
                ScrollView {
                    VStack(alignment: .leading, spacing: 18) {
                        if let error = model.error { Label(error, systemImage: "exclamationmark.triangle").foregroundStyle(.orange).textSelection(.enabled).restoreCard() }
                        if let report = model.report {
                            VStack(alignment: .leading, spacing: 10) {
                                HStack { Text(report.name.isEmpty ? "Навык недоступен" : report.name).font(.title3.weight(.semibold)); Spacer(); Text(report.status).font(.caption) }
                                Text("Сохранённый статус: \(report.raw["stored_skill_status"].text)").font(.callout)
                                Text("Проверяются происхождение и сохранённая причина архива. Восстановление сохраняет полный предыдущий архивный след; описание, uses и исходный урок не меняются.").font(.callout).foregroundStyle(.secondary)
                                Label("Библиотека общая для проектов. Восстановление относится к этой записи во всех проектах.", systemImage: "externaldrive").font(.callout).foregroundStyle(.orange)
                                HStack {
                                    Button("Результаты и источник") { Task { await model.openEvidence() } }
                                    Button("Открыть навык") { Task { await model.openSkill() } }
                                }.buttonStyle(.bordered).disabled(model.locked)
                            }.restoreCard()
                            if let receipt = report.receipt {
                                VStack(alignment: .leading, spacing: 10) {
                                    Label("Квитанция восстановления", systemImage: "doc.text").font(.headline)
                                    Text("\(receipt.verification) · \(receipt.raw["evidence_state"].text) · \(receipt.raw["applied_at"].text)").font(.caption)
                                    Text("Изменена одна запись. Процедура не запускалась, новые результаты использования не создавались.").font(.callout)
                                    Text(receipt.id).font(.caption.monospaced()).textSelection(.enabled)
                                    if !receipt.current { Text("Состояние изменилось или не подтверждено. Повторное применение запрещено.").foregroundStyle(.orange) }
                                    DisclosureGroup("Полная квитанция") { Text(receipt.raw.pretty).font(.caption.monospaced()).textSelection(.enabled) }
                                }.restoreCard()
                            } else {
                                Button("Проверить точное восстановление…") { Task { await model.prepare() } }.buttonStyle(.bordered).disabled(!model.canPrepare)
                                if !report.ready { Text("Восстановление недоступно. Причина архива, источник и лимит попыток должны пройти проверку.").font(.callout).foregroundStyle(.orange) }
                            }
                            if let preview = model.preview {
                                VStack(alignment: .leading, spacing: 12) {
                                    Label("archived → active · одна запись", systemImage: "checkmark.shield").font(.headline)
                                    Text("Изменятся только lifecycle, status и updated_at. История архива сохраняется внутри нового перехода.").font(.callout)
                                    if preview.ready {
                                        Text(preview.token).font(.caption.monospaced()).textSelection(.enabled)
                                        TextField("CONFIRM-…", text: $token).textFieldStyle(.roundedBorder).font(.body.monospaced()).disabled(model.locked)
                                        Toggle("Подтверждаю восстановление именно этого навыка в общей библиотеке; без выполнения процедуры", isOn: $acknowledgement).toggleStyle(.checkbox).disabled(model.locked)
                                        HStack {
                                            Button("Восстановить этот навык") { Task { await model.confirm(token: token, acknowledgement: acknowledgement) } }
                                                .buttonStyle(.borderedProminent).disabled(model.locked || !preview.accepts(token, acknowledgement: acknowledgement))
                                            Button("Отмена") { model.invalidate() }.disabled(model.locked)
                                        }
                                    } else { Text("Основания изменились. Ничего не восстановлено.").foregroundStyle(.orange) }
                                }.restoreCard().id("restore-confirmation")
                            }
                            DisclosureGroup("Источники, проверки и ограничения") {
                                Text(report.raw.pretty).font(.caption.monospaced()).textSelection(.enabled)
                                Text("Одна попытка на текущее ядро, без автоматического повтора. Подробная квитанция пока не сохраняется между запусками; исходный архив и след восстановления сохраняются в навыке. Старые результаты не становятся новым успехом. Изменения чужих процессов не перезаписываются при откате.").font(.caption)
                            }.restoreCard()
                        }
                    }.padding(22)
                }.onChange(of: model.preview?.fingerprint) { _, value in
                    token = ""; acknowledgement = false
                    if value != nil { scroll.scrollTo("restore-confirmation", anchor: .top) }
                }
            }
        }.frame(width: 850, height: 720).buttonStyle(.nativeHover).interactiveDismissDisabled(model.committing)
    }
}
private extension View {
    func restoreCard() -> some View { padding(16).frame(maxWidth: .infinity, alignment: .leading).background(Color.primary.opacity(0.035), in: RoundedRectangle(cornerRadius: 12)) }
}
