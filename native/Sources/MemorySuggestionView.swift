import SwiftUI

struct MemorySuggestionCard: View {
    @ObservedObject var app: AppModel
    let report: MemorySuggestionsReport
    let text: String
    private var pending: [MemorySuggestion] { report.items.filter { !app.reviewedMemorySuggestions.contains($0.id) } }
    var body: some View {
        if !pending.isEmpty {
            DisclosureGroup {
                VStack(alignment: .leading, spacing: 12) {
                    Text("Явные слова из твоего сообщения. Пока это предложения, не память и не проверенные факты.")
                        .font(.caption).foregroundStyle(.secondary)
                    ForEach(pending) { suggestion in
                        VStack(alignment: .leading, spacing: 6) {
                            Text(ProjectNote.title(suggestion.kind)).font(.caption.weight(.semibold)).foregroundStyle(.secondary)
                            Text((try? suggestion.quote(in: text)) ?? "Источник недоступен").font(NativeTheme.interfaceFont).textSelection(.enabled)
                            Button("Проверить и сохранить…") {
                                Task { await app.openMemorySuggestion(suggestion, report: report, text: text) }
                            }.buttonStyle(.nativeHover).disabled(app.busy || app.client.turnOutstanding || app.selected?.archived == true)
                        }
                    }
                    Text("Без дополнительных запросов модели. Предложение не попадёт в заметки без подтверждения.")
                        .font(.caption).foregroundStyle(.secondary)
                }.padding(.top, 8)
            } label: { Label("Стоит запомнить? · \(pending.count)", systemImage: "lightbulb") }
                .font(.system(size: 12)).padding(12)
                .background(NativeTheme.bubble.opacity(0.6), in: RoundedRectangle(cornerRadius: 12))
        }
    }
}

struct MemorySuggestionView: View {
    @ObservedObject var model: MemorySuggestionModel
    @State private var acknowledged = false
    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack {
                Label("Сохранить в память проекта", systemImage: "brain").font(.title2.weight(.semibold))
                Spacer()
                Button("Закрыть") { model.close() }.keyboardShortcut(.cancelAction).disabled(model.saving)
            }
            ScrollView {
                VStack(alignment: .leading, spacing: 14) {
                    Text(model.scope.workspace).font(.caption).foregroundStyle(.secondary).textSelection(.enabled)
                    Text(ProjectNote.title(model.suggestion.kind)).font(.headline)
                    Text(model.quote).font(NativeTheme.interfaceFont).textSelection(.enabled)
                        .frame(maxWidth: .infinity, alignment: .leading).padding(14)
                        .background(NativeTheme.bubble, in: RoundedRectangle(cornerRadius: 12))
                    Text("Дословная цитата из твоего сообщения, не вывод из ответа модели.").font(.callout).foregroundStyle(.secondary)
                    Text("Источник · запуск \(model.report.source["run_id"].text)\nSHA-256 сообщения · \(model.report.source["input_sha256"].text)")
                        .font(NativeTheme.codeFont).foregroundStyle(.secondary).textSelection(.enabled)
                    Text("Будет добавлена одна локальная заметка для этой рабочей папки. Она сможет вспоминаться в следующих запросах, если включён автоподбор памяти. При отправке через Codex выбранная заметка попадёт в облачный контекст.")
                        .font(.callout)
                    Text("Это твоё утверждение, не независимая проверка. Старые заметки не заменяются: изменение прежнего решения нужно отдельно проверить в «Заметках проекта».")
                        .font(.callout).foregroundStyle(.secondary)
                    if model.loading { ProgressView("Проверяю источник и дубликаты…").controlSize(.small) }
                    if let error = model.error { Label(error, systemImage: "exclamationmark.triangle").foregroundStyle(.orange).textSelection(.enabled) }
                    if let saved = model.saved {
                        Label("Сохранено · \(saved.id.prefix(12))", systemImage: "checkmark.circle").foregroundStyle(.green)
                        Text("Модель не вызывалась, задача не запускалась, разрешения не менялись.").font(.caption).foregroundStyle(.secondary)
                    } else if model.preview != nil {
                        Toggle("Подтверждаю эту заметку как своё утверждение", isOn: $acknowledged).disabled(model.locked)
                        Button("Сохранить заметку") { Task { await model.save(acknowledgement: acknowledged) } }
                            .buttonStyle(.borderedProminent).disabled(model.locked || !acknowledged)
                    }
                }.frame(maxWidth: .infinity, alignment: .leading)
            }
            Text("Открытие и закрытие окна ничего не сохраняет. Подтверждение нужно только для записи заметки.")
                .font(.caption).foregroundStyle(.secondary)
        }.padding(24).frame(width: 660, height: 650)
            .interactiveDismissDisabled(model.saving)
    }
}
