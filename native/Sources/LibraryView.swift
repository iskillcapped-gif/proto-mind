import SwiftUI

struct LibraryView: View {
    @ObservedObject var model: AppModel
    @State private var showSources = false
    private var collection: LibraryCollection { model.section.libraryCollection ?? .memory }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack(alignment: .top, spacing: 13) {
                Image(systemName: collection.symbol).font(.system(size: 26, weight: .light)).padding(.top, 3)
                VStack(alignment: .leading, spacing: 5) {
                    Text(collection.title).font(.system(size: 24, weight: .semibold))
                    Text(collection.subtitle).font(.callout).foregroundStyle(.secondary)
                    Label("Локально · только просмотр", systemImage: "lock.shield").font(.caption).foregroundStyle(.secondary)
                }
                Spacer(minLength: 12)
                if collection == .memory {
                    Button { Task { await model.openProjectMemory() } } label: {
                        Label("Память проекта…", systemImage: "folder.badge.person.crop")
                    }.buttonStyle(.nativeHover).disabled(model.busy || model.selected?.workspacePath == nil)
                        .help("Явные заметки выбранной папки; старые общие записи не переносятся")
                    Button { model.openMemoryWorkshop() } label: {
                        Label("Кандидаты опыта", systemImage: "sparkles.rectangle.stack")
                    }
                    .buttonStyle(.nativeHover)
                    .help("Показать уже собранные process-memory кандидаты без запуска и записи")
                    .disabled(model.busy)
                }
                Button { Task { await model.loadLibraryPage() } } label: { Image(systemName: "arrow.clockwise") }
                    .help("Перечитать исходные хранилища без изменений")
                    .disabled(model.busy || model.loadingLibrary)
            }.padding(24)

            HStack(spacing: 12) {
                HStack(spacing: 7) {
                    Image(systemName: "magnifyingglass").foregroundStyle(.secondary)
                    TextField("Поиск по тексту, тегам или ID", text: $model.libraryQuery)
                        .textFieldStyle(.plain).onSubmit { Task { await model.loadLibraryPage() } }
                    Button("Найти") { Task { await model.loadLibraryPage() } }.disabled(model.loadingLibrary)
                }.padding(9).background(.quaternary.opacity(0.45), in: RoundedRectangle(cornerRadius: 8))
                Picker("Записи", selection: Binding(get: { model.libraryFilter }, set: { filter in
                    model.libraryFilter = filter
                    Task { await model.loadLibraryPage() }
                })) {
                    ForEach(LibraryFilter.allCases) { filter in Text(filter.title).tag(filter) }
                }.pickerStyle(.segmented).frame(width: 250)
            }.disabled(model.busy).padding(.horizontal, 24).padding(.bottom, 16)

            if let page = model.libraryPage, page.collection == collection {
                HStack(spacing: 12) {
                    Text("Всего \(page.totalRecords) · текущих \(page.currentRecords) · найдено \(page.matchingRecords)")
                    if page.omittedRecords > 0 { Text("Не показано: \(page.omittedRecords)").foregroundStyle(.orange) }
                    Spacer()
                    Button { showSources.toggle() } label: {
                        Label(page.warnings.isEmpty ? "Источники" : "Проверить источники: \(page.warnings.count)",
                              systemImage: page.warnings.isEmpty ? "doc.text.magnifyingglass" : "exclamationmark.triangle")
                    }.buttonStyle(.nativeHover)
                }.font(.caption).foregroundStyle(.secondary).padding(.horizontal, 24).padding(.bottom, 13)
                if showSources { sources(page).frame(maxHeight: 165).padding(.horizontal, 24).padding(.bottom, 12) }
            }
            Divider()
            if let error = model.libraryError {
                placeholder("Не удалось открыть библиотеку", detail: error, symbol: "exclamationmark.triangle")
            } else if let page = model.libraryPage, page.collection == collection {
                HStack(spacing: 0) {
                    VStack(spacing: 0) {
                        ScrollView {
                            LazyVStack(alignment: .leading, spacing: 4) {
                                ForEach(page.items) { item in
                                    Button { Task { await model.inspectLibrary(item) } } label: {
                                        row(item)
                                    }.buttonStyle(.nativeHover).disabled(model.busy || model.loadingLibrary)
                                }
                                if page.items.isEmpty {
                                    Text(page.sources.contains { $0.health == "ERROR" } ? "Источник прочитан не полностью. Откройте диагностику выше." : "В этой выборке записей нет. Попробуйте другой фильтр или запрос.")
                                        .font(.callout).foregroundStyle(.secondary).padding(16)
                                }
                            }.padding(10)
                        }
                        Divider()
                        HStack {
                            Button { Task { await model.loadLibraryPage(offset: max(0, page.offset - page.limit)) } } label: { Image(systemName: "chevron.left") }
                                .disabled(page.offset == 0 || model.loadingLibrary || model.busy)
                            Spacer()
                            Text(page.matchingRecords == 0 ? "0 записей" : "\(page.offset + 1)–\(page.offset + page.items.count) из \(page.matchingRecords)")
                                .font(.caption).foregroundStyle(.secondary)
                            Spacer()
                            Button { Task { await model.loadLibraryPage(offset: page.offset + page.limit) } } label: { Image(systemName: "chevron.right") }
                                .disabled(page.offset + page.limit >= page.matchingRecords || model.loadingLibrary || model.busy)
                        }.padding(12)
                    }.frame(width: 290)
                    Divider()
                    detail.frame(maxWidth: .infinity, maxHeight: .infinity)
                }.overlay(alignment: .topTrailing) {
                    if model.loadingLibrary { ProgressView().controlSize(.small).padding(12) }
                }
            } else {
                if model.loadingLibrary {
                    VStack { ProgressView(); Text("Читаем локальные записи").font(.caption).foregroundStyle(.secondary) }
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                } else {
                    placeholder("Библиотека ещё не загружена", detail: "Обновите список. Просмотр не создаёт отсутствующие файлы.", symbol: collection.symbol)
                }
            }
        }.frame(maxWidth: .infinity, maxHeight: .infinity).clipped()
    }

    private func row(_ item: LibraryItem) -> some View {
        VStack(alignment: .leading, spacing: 7) {
            HStack(alignment: .top, spacing: 6) {
                if item.focused { Image(systemName: "scope").foregroundStyle(.orange).help("Сохранённый фокус цели") }
                Text(item.title.isEmpty ? "Без текста" : item.title).font(.system(size: 13, weight: .medium)).lineLimit(3)
            }
            HStack(spacing: 6) {
                Text(item.stateLabel)
                Text("· \(item.priority.isEmpty ? item.subtype : item.priorityLabel)").lineLimit(1)
            }.font(.system(size: 10)).foregroundStyle(.secondary)
            if !item.preview.isEmpty && collection != .memory { Text(item.preview).font(.caption).lineLimit(2).foregroundStyle(.secondary) }
            Text(collection == .memory ? LibrarySource.title(item.store) : item.recordId)
                .font(.system(size: 9, design: .monospaced)).lineLimit(1).foregroundStyle(.tertiary)
        }.multilineTextAlignment(.leading).padding(12).frame(maxWidth: .infinity, alignment: .leading)
            .background(model.selectedLibraryID == item.id ? Color.primary.opacity(0.07) : .clear, in: RoundedRectangle(cornerRadius: 9))
    }

    @ViewBuilder
    private var detail: some View {
        if model.loadingLibraryDetail {
            ProgressView().frame(maxWidth: .infinity, maxHeight: .infinity)
        } else if let error = model.libraryDetailError {
            placeholder("Карточка недоступна", detail: error, symbol: "exclamationmark.triangle")
        } else if let detail = model.libraryDetail {
            if let item = detail.item {
                ScrollView {
                    VStack(alignment: .leading, spacing: 21) {
                        VStack(alignment: .leading, spacing: 8) {
                            Text(item.title.isEmpty ? "Без текста" : item.title).font(.title3.weight(.semibold))
                            Text("\(item.stateLabel) · \(LibrarySource.title(item.store))").font(.caption).foregroundStyle(.secondary)
                            if !item.priority.isEmpty {
                                Text("Приоритет: \(item.priorityLabel)\(item.focused ? " · В фокусе" : "")").font(.callout)
                            }
                            if !item.tags.isEmpty { Text(item.tags.joined(separator: " · ")).font(.caption).foregroundStyle(.secondary) }
                            if item.store == "skills" {
                                Button { Task { await model.openSkillInspection(item) } } label: {
                                    Label("Результаты и жизненный цикл…", systemImage: "clock.arrow.circlepath")
                                }.buttonStyle(.bordered).nativeHoverSurface()
                                    .disabled(model.busy || model.client.turnOutstanding)
                                    .help("Проверить происхождение, ручные результаты и сохранённые переходы без действий")
                                Button { Task { await model.openSkillOutcome(item) } } label: {
                                    Label("Отметить ручной результат…", systemImage: "square.and.pencil")
                                }.buttonStyle(.bordered).nativeHoverSurface()
                                    .disabled(model.busy || model.client.turnOutstanding || model.selected == nil || model.selected?.archived == true)
                                    .help("Отдельная форма оператора: после точного подтверждения только запись опыта до перезапуска ядра")
                            }
                        }
                        if detail.changedSinceList { Label("Источник изменился. Ниже свежая версия записи.", systemImage: "arrow.clockwise").font(.callout).foregroundStyle(.orange) }
                        ForEach(detail.blocks) { block in
                            VStack(alignment: .leading, spacing: 9) {
                                Text(block.title).font(.caption.weight(.semibold)).foregroundStyle(.secondary)
                                Text(block.text.isEmpty ? "Не заполнено" : block.text).font(.system(size: 13))
                                    .textSelection(.enabled).frame(maxWidth: .infinity, alignment: .leading).fixedSize(horizontal: false, vertical: true)
                                if block.truncated { Text("Показаны первые 24 000 символов. Исходник не изменён.").font(.caption).foregroundStyle(.orange) }
                            }
                        }
                        if let evidence = detail.memoryEvidence {
                            memoryEvidence(evidence)
                            if item.store == "persistent", evidence.memoryType == "lesson", evidence.verified {
                                Button {
                                    Task { await model.openSkillAuthoring(lessonID: item.recordId) }
                                } label: { Label("Создать навык из урока…", systemImage: "books.vertical") }
                                .buttonStyle(.bordered).nativeHoverSurface()
                                .disabled(model.busy || model.selected?.archived != false)
                                .help("Открыть локальную форму. Сам просмотр ничего не сохраняет и не выполняет.")
                            }
                        }
                        if let evidence = detail.skillEvidence {
                            VStack(alignment: .leading, spacing: 10) {
                                Label("Происхождение навыка · \(evidence.status)", systemImage: evidence.status == "VERIFIED" ? "checkmark.seal" : "doc.text.magnifyingglass")
                                    .font(.callout.weight(.semibold))
                                Text("Проверяются сохранённый контракт, SHA и исходный урок. Это не запуск процедуры и не доказательство её эффективности.")
                                    .font(.caption).foregroundStyle(.secondary)
                                if !evidence.provenanceId.isEmpty { evidenceLine("Provenance", evidence.provenanceId) }
                                if !evidence.sourceLessonId.isEmpty {
                                    evidenceLine("Исходный урок", "\(evidence.sourceLessonId) · \(evidence.sourceStatus)")
                                    Button("Открыть исходный урок") {
                                        Task { await model.openMemoryEvidence(recordID: evidence.sourceLessonId) }
                                    }.disabled(model.busy)
                                }
                                ForEach(Array((evidence.issues + evidence.warnings).enumerated()), id: \.offset) { _, finding in
                                    Text(finding).font(.caption).foregroundStyle(evidence.status == "ERROR" ? .red : .orange)
                                }
                            }.padding(14).background(Color.primary.opacity(0.035), in: RoundedRectangle(cornerRadius: 11))
                        }
                        Divider()
                        VStack(alignment: .leading, spacing: 11) {
                            Text("Сохранённые метаданные").font(.callout.weight(.semibold))
                            ForEach(detail.fields) { field in
                                VStack(alignment: .leading, spacing: 3) {
                                    Text(field.title).font(.caption).foregroundStyle(.secondary)
                                    Text(field.value.isEmpty ? "Не указано" : field.value).font(.system(size: 11, design: .monospaced)).textSelection(.enabled)
                                        .frame(maxWidth: .infinity, alignment: .leading).fixedSize(horizontal: false, vertical: true)
                                }
                            }
                            if let source = detail.sources.first(where: { $0.store == item.store }) {
                                Text(source.path).font(.caption).foregroundStyle(.secondary).textSelection(.enabled)
                                Text("SHA-256 \(source.sha256)").font(.system(size: 9, design: .monospaced)).foregroundStyle(.tertiary).textSelection(.enabled)
                            }
                        }
                        if !detail.warnings.isEmpty {
                            VStack(alignment: .leading, spacing: 7) {
                                Label("Ограничения данных", systemImage: "info.circle").font(.callout.weight(.medium))
                                ForEach(Array(detail.warnings.enumerated()), id: \.offset) { _, warning in Text(warning).font(.caption).foregroundStyle(.secondary) }
                            }
                        }
                        Text(collection == .memory
                             ? "Проверка происхождения читает embedded provenance и пересчитывает его hash, но не доказывает истинность обычной legacy-записи. Просмотр не меняет запись или usage telemetry. Диагностика: \(collection.manualDoctor)"
                             : "Просмотр не меняет записи, счётчики использования или фокус. Метаданные не являются новой проверкой достоверности. Диагностика вручную: \(collection.manualDoctor)")
                            .font(.caption).foregroundStyle(.secondary).textSelection(.enabled)
                    }.padding(25).frame(maxWidth: .infinity, alignment: .leading)
                }.id(item.id)
            } else {
                placeholder("Запись недоступна", detail: detail.message, symbol: "doc.questionmark")
            }
        } else {
            placeholder("Выберите запись", detail: "Содержание, источник и сохранённые метаданные появятся здесь. Ничего не отправляется модели.", symbol: collection.symbol)
        }
    }

    private func memoryEvidence(_ evidence: NativeMemoryEvidence) -> some View {
        VStack(alignment: .leading, spacing: 11) {
            HStack {
                Label("Почему Proto-Mind это знает", systemImage: evidence.verified ? "checkmark.seal" : "questionmark.diamond")
                    .font(.callout.weight(.semibold))
                Spacer()
                Text(evidence.status)
                    .font(.system(size: 10, weight: .semibold, design: .monospaced))
                    .foregroundStyle(evidence.verified ? .green : evidence.status == "ERROR" ? .red : .orange)
            }
            Text(evidence.explanation).font(.callout).foregroundStyle(.secondary)
            evidenceLine("Тип / источник", "\(evidence.memoryType) · \(evidence.recordSource)")
            if !evidence.provenanceId.isEmpty { evidenceLine("Provenance ID", evidence.provenanceId) }
            if !evidence.provenanceHash.isEmpty { evidenceLine("Hash", evidence.provenanceHash) }
            if !evidence.evidenceEventIds.isEmpty { evidenceLine("События", evidence.evidenceEventIds.joined(separator: " · ")) }
            if !evidence.sourceKinds.isEmpty { evidenceLine("Виды доказательств", evidence.sourceKinds.joined(separator: " · ")) }
            if !evidence.selectedScopeHash.isEmpty { evidenceLine("Scope hash", evidence.selectedScopeHash) }
            if evidence.operatorConfirmationRecorded {
                Label("Сохранено через точное подтверждение оператора · automatic promotion: false", systemImage: "hand.raised")
                    .font(.caption).foregroundStyle(.secondary)
            }
            ForEach(Array((evidence.issues + evidence.warnings).enumerated()), id: \.offset) { _, finding in
                Text(finding).font(.caption).foregroundStyle(evidence.status == "ERROR" ? .red : .orange)
            }
            Text("Read-only: без retrieval, model/network call и записи в store.")
                .font(.caption).foregroundStyle(.tertiary)
        }
        .padding(14)
        .background(Color.primary.opacity(0.035), in: RoundedRectangle(cornerRadius: 11))
    }

    private func evidenceLine(_ label: String, _ value: String) -> some View {
        VStack(alignment: .leading, spacing: 3) {
            Text(label).font(.caption).foregroundStyle(.secondary)
            Text(value).font(.system(size: 10, design: .monospaced)).textSelection(.enabled)
                .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    private func sources(_ page: LibraryPage) -> some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 12) {
                ForEach(page.sources) { source in
                    VStack(alignment: .leading, spacing: 4) {
                        Text("\(source.title) · \(source.health) · \(source.recordCount) записей").font(.caption.weight(.medium))
                        Text(source.path).font(.caption2).textSelection(.enabled)
                        if !source.modifiedAt.isEmpty { Text("Изменён: \(source.modifiedAt)").font(.caption2) }
                        if !source.message.isEmpty { Text(source.message).font(.caption).foregroundStyle(.orange) }
                    }
                }
                ForEach(Array(page.warnings.enumerated()), id: \.offset) { _, warning in
                    if !page.sources.contains(where: { warning == "\($0.store): \($0.message)" }) {
                        Text(warning).font(.caption).foregroundStyle(.secondary)
                    }
                }
            }.frame(maxWidth: .infinity, alignment: .leading).padding(12)
        }.background(.quaternary.opacity(0.3), in: RoundedRectangle(cornerRadius: 8))
    }

    private func placeholder(_ title: String, detail: String, symbol: String) -> some View {
        VStack(alignment: .center, spacing: 12) {
            Image(systemName: symbol).font(.system(size: 32, weight: .light)).foregroundStyle(.tertiary)
            Text(title).font(.title3.weight(.medium))
            Text(detail).font(.callout).foregroundStyle(.secondary).multilineTextAlignment(.center).textSelection(.enabled)
        }.padding(32).frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}
