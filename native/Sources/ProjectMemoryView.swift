import SwiftUI

struct ProjectMemoryView: View {
    @ObservedObject var model: ProjectMemoryModel
    @State private var showEditor = false
    private var searching: Bool { !model.query.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }
    var body: some View {
        VStack(spacing: 0) {
            HStack {
                Label(L10n.text("Память проекта"), systemImage: "brain.head.profile").font(.title2.weight(.semibold))
                Spacer()
                Button { Task { await model.refresh(recall: searching) } } label: { Image(systemName: "arrow.clockwise") }.disabled(model.locked)
                Button { model.close() } label: { Image(systemName: "xmark") }.disabled(model.saving).keyboardShortcut(.cancelAction)
            }.padding(22)
            Divider()
            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    Text(model.scope.workspace).font(.caption.monospaced()).textSelection(.enabled)
                    Text(L10n.text("Сохраняй важные факты, уточняй решения и убирай то, что больше не актуально.")).foregroundStyle(.secondary)
                    Text(L10n.text("Текущие заметки этой папки могут подбираться к новым запросам, если включена память проекта. При отправке через Codex выбранные сведения попадут в облачный контекст.")).font(.caption).foregroundStyle(.secondary)
                    if let notice = model.notice { Label(notice, systemImage: "checkmark.circle").foregroundStyle(.green).textSelection(.enabled) }
                    if let error = model.error { Text(error).foregroundStyle(.orange) }
                    ForEach(model.issues, id: \.self) { Text($0).font(.caption).foregroundStyle(.orange) }
                    HStack {
                        TextField(L10n.text("Найти заметку"), text: $model.query).textFieldStyle(.roundedBorder)
                            .onSubmit { Task { await model.refresh(recall: searching) } }
                        Button(L10n.text("Найти")) { Task { await model.refresh(recall: searching) } }
                        Toggle(L10n.text("История"), isOn: $model.includeHistory).toggleStyle(.checkbox)
                            .onChange(of: model.includeHistory) { Task { await model.refresh(recall: searching) } }
                    }.disabled(model.locked)
                    Text(L10n.format("В проекте: \(model.total) · показано: \(model.notes.count)")).font(.caption).foregroundStyle(.secondary)
                    if !model.recalling && model.matching > 40 {
                        HStack {
                            Button(L10n.text("Предыдущие")) { Task { await model.refresh(offset: max(0, model.offset - 40)) } }.disabled(model.locked || model.offset == 0)
                            Text(L10n.format("\(model.offset + 1)–\(model.offset + model.notes.count) из \(model.matching)")).font(.caption)
                            Button(L10n.text("Следующие")) { Task { await model.refresh(offset: model.offset + 40) } }.disabled(model.locked || model.offset + model.notes.count >= model.matching)
                        }
                    }
                    ForEach(model.notes) { note in
                        Button { Task { await model.inspect(note) } } label: {
                            VStack(alignment: .leading, spacing: 5) {
                                Text(note.content).lineLimit(3).frame(maxWidth: .infinity, alignment: .leading)
                                Text("\(ProjectNote.title(note.kind)) · \(note.statusTitle)").font(.caption).foregroundStyle(.secondary)
                            }.padding(10).background(Color.primary.opacity(0.035), in: RoundedRectangle(cornerRadius: 9))
                        }.disabled(model.locked)
                    }
                    if model.notes.isEmpty { Text(model.includeHistory ? L10n.text("Подходящих заметок нет.") : L10n.text("Подходящих заметок нет. Убранные и прежние версии доступны в истории.")).foregroundStyle(.secondary) }
                    if let note = model.detail {
                        VStack(alignment: .leading, spacing: 10) {
                            Text(note.statusTitle).font(.headline)
                            Text(note.content).textSelection(.enabled)
                            Text(L10n.format("Основание: \(note.basis)")).font(.callout).foregroundStyle(.secondary).textSelection(.enabled)
                            Text(L10n.text("Это сохранённое утверждение пользователя. Содержимое записи проверено; достоверность факта отдельно не оценивалась.")).font(.caption).foregroundStyle(.secondary)
                            HStack {
                                Button(L10n.text("К следующему сообщению")) { model.attach() }.disabled(model.locked || !note.active || !model.issues.isEmpty || model.app.selected?.archived == true)
                                if note.active {
                                    Button(L10n.text("Изменить")) { model.replaceSelected(); showEditor = true }.disabled(model.locked || !model.issues.isEmpty)
                                    Button(L10n.text("Убрать из памяти проекта")) { Task { await model.changeState("archive") } }.disabled(model.locked || !model.issues.isEmpty)
                                } else if note.archived {
                                    Button(L10n.text("Вернуть в память проекта")) { Task { await model.changeState("restore") } }.disabled(model.locked || !model.issues.isEmpty)
                                }
                            }
                            Text(L10n.text("Убранная заметка хранится в истории и не подбирается к новым запросам. Уже отправленные сообщения и контекст провайдера сохраняются.")).font(.caption).foregroundStyle(.secondary)
                            DisclosureGroup(L10n.text("Подробности записи")) { Text(note.raw.pretty).font(NativeTheme.codeFont).textSelection(.enabled) }
                        }.padding(16).background(Color.primary.opacity(0.04), in: RoundedRectangle(cornerRadius: 12))
                    }
                    DisclosureGroup(model.supersedesID.isEmpty ? L10n.text("Новая заметка") : L10n.text("Изменить заметку"), isExpanded: $showEditor) {
                        VStack(alignment: .leading, spacing: 12) {
                            Picker(L10n.text("Тип"), selection: $model.noteKind) { ForEach(ProjectNote.kinds, id: \.self) { Text(ProjectNote.title($0)).tag($0) } }
                            Text(L10n.text("Содержание · до 4 000 символов")).font(.caption)
                            TextEditor(text: $model.content).font(.body).frame(height: 110).padding(5)
                                .background(Color.primary.opacity(0.03), in: RoundedRectangle(cornerRadius: 8))
                            TextField(L10n.text("Источник или пояснение · необязательно"), text: $model.basis).textFieldStyle(.roundedBorder)
                            if !model.supersedesID.isEmpty {
                                Text(L10n.text("После сохранения прежняя версия останется в истории и перестанет подбираться к запросам.")).font(.caption).foregroundStyle(.secondary)
                            }
                            HStack {
                                Button(model.supersedesID.isEmpty ? L10n.text("Сохранить заметку") : L10n.text("Сохранить изменения")) {
                                    Task { await model.saveDraft(); if model.error == nil { showEditor = false } }
                                }.buttonStyle(.borderedProminent)
                                    .disabled(model.content.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                                Button(L10n.text("Отмена")) { model.newNote(); showEditor = false }
                                if model.loading || model.saving { ProgressView().controlSize(.small) }
                            }
                        }.padding(.top, 10).disabled(model.locked)
                    }
                    Text(L10n.text("Эти действия меняют только память выбранного проекта. Они не вызывают модель, не запускают задачу и не прикрепляют заметку автоматически. Общая старая память хранится отдельно.")).font(.caption).foregroundStyle(.secondary)
                }.padding(22)
            }
        }.workspacePageSize(width: 850, height: 740).buttonStyle(.nativeHover).workspaceDismissDisabled(model.saving)
            .onChange(of: model.note) { model.invalidate() }
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
                        .help(L10n.text("Явно выбранная заметка проекта. Перед Send проверяются проект, актуальность и SHA. Не автоматический recall."))
                }
            }
        }.frame(height: 44).scrollIndicators(.hidden).padding(.horizontal, 12).padding(.top, 8)
    }
}
