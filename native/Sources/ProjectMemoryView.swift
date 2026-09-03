import SwiftUI

struct ProjectMemoryView: View {
    @ObservedObject var model: ProjectMemoryModel
    @State private var token = ""
    @State private var acknowledgement = false
    @State private var showEditor = false
    var body: some View {
        VStack(spacing: 0) {
            HStack {
                Label("Память проекта", systemImage: "brain.head.profile").font(.title2.weight(.semibold))
                Spacer()
                Button { Task { await model.refresh() } } label: { Image(systemName: "arrow.clockwise") }.disabled(model.locked)
                Button { model.close() } label: { Image(systemName: "xmark") }.disabled(model.saving).keyboardShortcut(.cancelAction)
            }.padding(22)
            Divider()
            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    Text(model.scope.workspace).font(.caption.monospaced()).textSelection(.enabled)
                    Text("Только явно сохранённые заметки этой папки. Общая старая память не переносится и не получает выдуманную привязку к проекту.").foregroundStyle(.secondary)
                    Text("В Codex текущие заметки могут подбираться к задаче автоматически. Переключатель памяти рядом с навыками отключает подбор для диалога; ручное прикрепление имеет приоритет. Сохранение здесь ничего не отправляет.").font(.caption).foregroundStyle(.secondary)
                    if let error = model.error { Text(error).foregroundStyle(.orange) }
                    ForEach(model.issues, id: \.self) { Text($0).font(.caption).foregroundStyle(.orange) }
                    HStack {
                        TextField("Найти по словам, без модели", text: $model.query).textFieldStyle(.roundedBorder)
                            .onSubmit { Task { await model.refresh(recall: !model.query.isEmpty) } }
                        Button("Вспомнить") { Task { await model.refresh(recall: !model.query.isEmpty) } }
                        Toggle("История", isOn: $model.includeHistory).toggleStyle(.checkbox)
                            .onChange(of: model.includeHistory) { Task { await model.refresh() } }
                    }.disabled(model.locked)
                    Text("В проекте: \(model.total) · показано: \(model.notes.count)").font(.caption).foregroundStyle(.secondary)
                    if !model.recalling && model.matching > 40 {
                        HStack {
                            Button("Предыдущие") { Task { await model.refresh(offset: max(0, model.offset - 40)) } }.disabled(model.locked || model.offset == 0)
                            Text("\(model.offset + 1)–\(model.offset + model.notes.count) из \(model.matching)").font(.caption)
                            Button("Следующие") { Task { await model.refresh(offset: model.offset + 40) } }.disabled(model.locked || model.offset + model.notes.count >= model.matching)
                        }
                    }
                    ForEach(model.notes) { note in
                        Button { Task { await model.inspect(note) } } label: {
                            VStack(alignment: .leading, spacing: 5) {
                                Text(note.content).lineLimit(3).frame(maxWidth: .infinity, alignment: .leading)
                                Text("\(ProjectNote.title(note.kind)) · \(note.active ? "текущая" : "заменена") · \(note.id.prefix(10))").font(.caption).foregroundStyle(.secondary)
                            }.padding(10).background(Color.primary.opacity(0.035), in: RoundedRectangle(cornerRadius: 9))
                        }.disabled(model.locked)
                    }
                    if model.notes.isEmpty { Text("Нет подходящих заметок. Отсутствующие сведения не достраиваются.").foregroundStyle(.secondary) }
                    if let note = model.detail {
                        VStack(alignment: .leading, spacing: 10) {
                            Label("SHA-256 проверен · утверждение оператора", systemImage: "checkmark.seal").font(.headline)
                            Text(note.content).textSelection(.enabled)
                            Text("Основание: \(note.basis)").font(.callout).foregroundStyle(.secondary).textSelection(.enabled)
                            Text("Не независимая проверка факта. Прикрепление не отправляет сообщение и не меняет разрешения.").font(.caption)
                            HStack {
                                Button("К следующему сообщению") { model.attach() }.disabled(model.locked || !note.active || !model.issues.isEmpty || model.app.selected?.archived == true)
                                Button("Заменить новой заметкой…") { model.replaceSelected(); showEditor = true }.disabled(model.locked || !note.active || !model.issues.isEmpty)
                            }
                        }.padding(16).background(Color.primary.opacity(0.04), in: RoundedRectangle(cornerRadius: 12))
                    }
                    DisclosureGroup("Новая заметка · сохранить явно", isExpanded: $showEditor) {
                        VStack(alignment: .leading, spacing: 12) {
                            Picker("Тип", selection: $model.noteKind) { ForEach(ProjectNote.kinds, id: \.self) { Text(ProjectNote.title($0)).tag($0) } }
                            Text("Содержание · до 4 000 символов").font(.caption)
                            TextEditor(text: $model.content).font(.body).frame(height: 110).padding(5)
                                .background(Color.primary.opacity(0.03), in: RoundedRectangle(cornerRadius: 8))
                            TextField("Откуда это известно / основание оператора", text: $model.basis).textFieldStyle(.roundedBorder)
                            if !model.supersedesID.isEmpty {
                                HStack { Text("Заменяет: \(model.supersedesID.prefix(12)). Исходник останется историей.").font(.caption); Button("Не заменять") { model.supersedesID = "" } }
                            }
                            Button("Проверить перед сохранением") { Task { await model.prepare() } }
                        }.padding(.top, 10).disabled(model.locked)
                    }
                    if let preview = model.preview {
                        VStack(alignment: .leading, spacing: 10) {
                            Text("Будет добавлена одна личная заметка. Общие хранилища и Context Injection не меняются.").font(.callout)
                            DisclosureGroup("Точный состав записи") { Text(preview["body"].pretty).font(.caption.monospaced()).textSelection(.enabled) }
                            Text(preview["confirmation_token"].text).font(.caption.monospaced()).textSelection(.enabled)
                            TextField("SAVE-PROJECT-MEMORY-…", text: $token).textFieldStyle(.roundedBorder)
                            Toggle("Это моё явное утверждение, а не автоматически проверенный факт", isOn: $acknowledgement)
                            HStack {
                                Button("Сохранить заметку") { Task { await model.save(token: token, acknowledgement: acknowledgement) } }
                                    .disabled(model.locked || !acknowledgement || token != preview["confirmation_token"].text)
                                Button("Отмена") { model.invalidate() }.disabled(model.saving)
                            }
                        }.padding(16).background(Color.primary.opacity(0.04), in: RoundedRectangle(cornerRadius: 12))
                    }
                    Text("Без LLM, фонового поиска, автоматического обучения и миграции. Ручной выбор для отправки временный: исчезнет после перезапуска. Автоподбор проверяет актуальные заметки заново; уже отправленный контекст может остаться в истории провайдера.").font(.caption).foregroundStyle(.secondary)
                }.padding(22)
            }
        }.frame(width: 850, height: 740).buttonStyle(.nativeHover).interactiveDismissDisabled(model.saving)
            .onChange(of: model.note) { model.invalidate() }
            .onChange(of: model.preview?["preview_fingerprint"].text) { token = ""; acknowledgement = false }
    }
}

struct PendingProjectNotesView: View {
    @ObservedObject var model: AppModel
    var body: some View {
        ScrollView(.horizontal) {
            HStack(spacing: 6) {
                ForEach(model.pendingProjectNotes) { note in
                    HStack(spacing: 6) {
                        Image(systemName: "brain.head.profile")
                        Text(String(note.content.prefix(45))).lineLimit(1)
                        Button { model.removeProjectNote(note.id) } label: { Image(systemName: "xmark") }.disabled(model.busy)
                    }.font(.caption).padding(8).background(Color.primary.opacity(0.05), in: RoundedRectangle(cornerRadius: 8))
                        .help("Явно выбранная заметка проекта. Перед Send проверяются проект, актуальность и SHA. Не автоматический recall.")
                }
            }
        }.frame(height: 44).scrollIndicators(.hidden).padding(.horizontal, 12).padding(.top, 8)
    }
}
