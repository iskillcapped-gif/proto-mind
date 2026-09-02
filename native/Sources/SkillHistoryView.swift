import SwiftUI

struct SkillHistoryView: View {
    @ObservedObject var model: SkillHistoryModel
    @State private var token = ""
    @State private var acknowledgement = false
    var body: some View {
        VStack(spacing: 0) {
            HStack {
                Label("История обучения", systemImage: "clock.arrow.circlepath").font(.title2.weight(.semibold))
                Spacer()
                Button { Task { await model.refresh() } } label: { Image(systemName: "arrow.clockwise") }.disabled(model.locked)
                Button { model.close() } label: { Image(systemName: "xmark") }.disabled(model.saving).keyboardShortcut(.cancelAction)
            }.padding(22)
            Divider()
            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    Text("Явно сохранённые снимки выбранного навыка и диалога. После перезапуска доступны исходные квитанции и их основания, но не прежние разрешения, согласия и токены.").foregroundStyle(.secondary)
                    if let error = model.error { Text(error).foregroundStyle(.orange) }
                    ForEach(model.issues, id: \.self) { Text($0).font(.caption).foregroundStyle(.orange) }
                    Button("Подготовить сохранение текущей истории…") { Task { await model.prepare() } }.disabled(model.locked)
                    if let preview = model.preview {
                        VStack(alignment: .leading, spacing: 10) {
                            Text("Квитанций: \(preview["receipt_count"].integer) · событий ручного результата: \(preview["event_count"].integer)").font(.headline)
                            Text("Сохранятся текущая запись и доступные сейчас подробности. Потерянная до этого перезапуска история не восстанавливается. Это не независимое доказательство успеха.").font(.caption)
                            DisclosureGroup("Точный состав снимка") { Text(preview["body"].pretty).font(.caption.monospaced()) }
                            Text(preview["confirmation_token"].text).font(.caption.monospaced()).textSelection(.enabled)
                            TextField("SAVE-SKILL-HISTORY-…", text: $token).textFieldStyle(.roundedBorder)
                            Toggle("Сохранить только историческую копию в личном профиле", isOn: $acknowledgement)
                            HStack {
                                Button("Сохранить историю") { Task { await model.save(token: token, acknowledgement: acknowledgement) } }
                                    .disabled(model.locked || !acknowledgement || token != preview["confirmation_token"].text)
                                Button("Отмена") { model.invalidate() }.disabled(model.saving)
                            }
                        }.padding(16).background(Color.primary.opacity(0.04), in: RoundedRectangle(cornerRadius: 12))
                    }
                    Text("Сохранённые снимки · \(model.entries.count)").font(.headline)
                    if model.entries.isEmpty { Text("Пока ничего не сохранено. Просмотр сам не создаёт файлы.").foregroundStyle(.secondary) }
                    ForEach(model.entries) { entry in
                        Button { Task { await model.inspect(entry) } } label: {
                            HStack { Image(systemName: "doc.text.magnifyingglass"); Text(entry.date); Spacer(); Text("\(entry.receiptCount) квитанций · \(entry.eventCount) событий") }.padding(10).frame(maxWidth: .infinity)
                        }.disabled(model.locked)
                    }
                    if let detail = model.detail {
                        VStack(alignment: .leading, spacing: 10) {
                            Label("SHA-256 проверен · исторические данные", systemImage: "checkmark.seal").font(.headline)
                            Text("Текущая запись: \(detail["current_record_state"].text)").font(.caption)
                            Text("Проверка целостности не доказывает авторство или эффективность. Снимок не загружается обратно в действующий пилот.").font(.caption).foregroundStyle(.secondary)
                            DisclosureGroup("Запись, исходные квитанции и события") { Text(detail["record"].pretty).font(.caption.monospaced()) }
                        }.padding(16).background(Color.primary.opacity(0.04), in: RoundedRectangle(cornerRadius: 12))
                    }
                    Text("Только отдельный личный архив learning_history. Без записи в общую память/навыки, модели, запуска задач, миграции или автоматического восстановления.").font(.caption).foregroundStyle(.secondary)
                }.padding(22).textSelection(.enabled)
            }
        }.frame(width: 850, height: 720).buttonStyle(.nativeHover).interactiveDismissDisabled(model.saving)
            .onChange(of: model.preview?["preview_fingerprint"].text) { token = ""; acknowledgement = false }
    }
}
