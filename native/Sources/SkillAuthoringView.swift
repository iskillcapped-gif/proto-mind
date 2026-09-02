import SwiftUI

struct SkillAuthoringView: View {
    @ObservedObject var model: SkillAuthoringModel
    @State private var token = ""
    @State private var acknowledgeGlobal = false

    var body: some View {
        VStack(spacing: 0) {
            HStack(spacing: 12) {
                Image(systemName: "books.vertical").font(.title2)
                VStack(alignment: .leading, spacing: 4) {
                    Text("Из урока в навык").font(.title2.weight(.semibold))
                    Text("Опишите процедуру, проверьте и сохраните отдельно").font(.caption).foregroundStyle(.secondary)
                }
                Spacer()
                if model.loading || model.committing { ProgressView().controlSize(.small) }
                Button { Task { await model.refresh() } } label: { Image(systemName: "arrow.clockwise") }
                    .disabled(model.locked).help("Перечитать источник и библиотеку; старое подтверждение будет сброшено")
                Button { model.close() } label: { Image(systemName: "xmark") }
                    .disabled(model.committing).keyboardShortcut(.cancelAction)
            }.padding(22)
            Divider()
            ScrollViewReader { scroll in
                ScrollView {
                    VStack(alignment: .leading, spacing: 18) {
                        boundary
                        if let error = model.error {
                            Label(error, systemImage: "exclamationmark.triangle").font(.callout).foregroundStyle(.orange)
                                .textSelection(.enabled).skillCard()
                        }
                        if let report = model.report {
                            source(report)
                            if report.eligible || report.authoringReceipt != nil {
                                authoringForm(report)
                                if let preview = model.preview { confirmation(preview).id("skill-confirmation") }
                                if let receipt = report.authoringReceipt { receiptCard(receipt, title: "Подтверждённое описание") }
                                if let receipt = report.applyReceipt { receiptCard(receipt, title: "Навык сохранён") }
                            } else {
                                Label("Этот урок пока нельзя превратить в навык", systemImage: "hand.raised")
                                    .font(.headline).skillCard()
                                Text("Нужен активный урок с проверяемым происхождением, без ошибок жизненного цикла и активного точного дубля. Обычная legacy-запись не получает источник автоматически.")
                                    .font(.callout).foregroundStyle(.secondary)
                            }
                            diagnostics(report)
                        } else if model.loading {
                            Text("Проверяем локальный урок и библиотеку навыков…").foregroundStyle(.secondary)
                        }
                        Text("Без LLM, команд, сбора опыта и выполнения шагов. Закрытие формы не создаёт файлы и не меняет черновик чата.")
                            .font(.caption).foregroundStyle(.secondary)
                    }.padding(22)
                }
                .onChange(of: model.preview?.previewFingerprint) { _, value in
                    if value != nil { scroll.scrollTo("skill-confirmation", anchor: .top) }
                    token = ""; acknowledgeGlobal = false
                }
            }
        }
        .frame(width: 850, height: 720)
        .buttonStyle(.nativeHover)
        .interactiveDismissDisabled(model.committing)
    }

    private var boundary: some View {
        VStack(alignment: .leading, spacing: 7) {
            Label("Навык описывает действия, но не запускает их", systemImage: "hand.raised").font(.headline)
            Text("Просмотр и редактирование формы не меняют файлы. Первое подтверждение фиксирует описание только до перезапуска ядра; второе сохраняет одну запись в общую библиотеку навыков.")
                .font(.callout).foregroundStyle(.secondary)
            Text("Библиотека общая для всех проектов. Разрешения в карточке являются требованиями, а не выдачей доступа. Один apply на запущенное Native-ядро.")
                .font(.caption).foregroundStyle(.orange)
        }.skillCard()
    }

    private func source(_ report: NativeSkillReview) -> some View {
        VStack(alignment: .leading, spacing: 9) {
            HStack {
                Label("Исходный урок", systemImage: report.eligible ? "checkmark.seal" : "doc.text.magnifyingglass").font(.headline)
                Spacer()
                Text(report.lifecycleState).font(.caption).foregroundStyle(.secondary)
            }
            Text(report.sourceContent.isEmpty ? "Проверенный источник недоступен" : report.sourceContent).textSelection(.enabled)
            detail("Урок", model.lessonID)
            if !report.sourceProvenanceId.isEmpty { detail("Provenance", report.sourceProvenanceId) }
            findings(report.sourceIssues, color: .orange)
            Text("Проверка источника подтверждает цепочку происхождения и неизменность, а не качество будущей процедуры.")
                .font(.caption).foregroundStyle(.secondary)
        }.skillCard()
    }

    private func authoringForm(_ report: NativeSkillReview) -> some View {
        VStack(alignment: .leading, spacing: 14) {
            Label("1. Описание навыка", systemImage: "square.and.pencil").font(.headline)
            Text("Шаги заполняете вы. Одна строка означает один пункт; модель ничего не дописывает автоматически.")
                .font(.caption).foregroundStyle(.secondary)
            Group {
                singleField("Название", prompt: "Например: Проверить результат перед завершением", text: $model.draft.name)
                singleField("Краткое назначение", prompt: "Какую задачу помогает решить навык", text: $model.draft.summary)
                singleField("Когда применять", prompt: "Условие или ситуация", text: $model.draft.trigger)
                listField("Что должно быть готово", hint: "До 8 условий", text: $model.draft.preconditions)
                listField("Шаги", hint: "До 16 шагов, в порядке выполнения", text: $model.draft.steps)
                listField("Необходимые разрешения", hint: "До 8 требований; для чтения укажите это явно", text: $model.draft.permissions)
                listField("Как проверить результат", hint: "До 8 проверок", text: $model.draft.verification)
                listField("Когда остановиться / возможные ошибки", hint: "До 8 случаев", text: $model.draft.failures)
            }.disabled(model.locked || report.authoringReceipt != nil)
            Text("До 800 символов на пункт, до 8000 суммарно. Пустые обязательные поля и дубли не пройдут проверку.")
                .font(.caption).foregroundStyle(.secondary)
            if report.authoringReceipt == nil {
                Button("Проверить описание…") { Task { await model.prepare(.author) } }
                    .buttonStyle(.bordered).nativeHoverSurface()
                    .disabled(model.locked || !report.eligible || !model.draft.fields.complete)
            } else {
                Label("Описание зафиксировано в текущем ядре", systemImage: "checkmark.circle").font(.callout)
            }
            Divider()
            Label("2. Сохранение в библиотеку", systemImage: "books.vertical").font(.headline)
            if report.applyReceipt == nil {
                Text("Отдельный preview ещё раз проверит исходный урок, описание, дубли и текущие SHA хранилищ. После него потребуется точное подтверждение записи.")
                    .font(.callout).foregroundStyle(.secondary)
                Button("Проверить перед сохранением…") { Task { await model.prepare(.apply) } }
                    .buttonStyle(.bordered).nativeHoverSurface()
                    .disabled(model.locked || report.authoringReceipt == nil || !report.nativeApplySlotAvailable || !report.issues.isEmpty)
                if !report.nativeApplySlotAvailable {
                    Text("Лимит одного сохранения в этом ядре уже использован. Проверьте результат, не повторяйте запись.")
                        .font(.caption).foregroundStyle(.orange)
                }
            } else {
                Text("Запись уже создана. Автоматического выполнения и повторного сохранения нет.").font(.callout).foregroundStyle(.secondary)
            }
        }.skillCard()
    }

    private func confirmation(_ preview: NativeSkillPreview) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            Label(preview.operation.title, systemImage: preview.ready ? "checkmark.shield" : "hand.raised.slash").font(.headline)
            if preview.ready {
                Text(preview.operation == .apply ? "Будет добавлена одна запись skill.procedure.v1 в proto_mind/data/skills.jsonl." : "Будет зафиксировано только описание в оперативной памяти. Файлы не изменятся.")
                    .font(.callout).foregroundStyle(.secondary)
                Text(preview.name).font(.headline)
                Text(preview.summary).font(.callout).textSelection(.enabled)
                DisclosureGroup("Точное содержимое будущего навыка") {
                    Text(preview.body).font(.system(size: 12, design: .monospaced)).textSelection(.enabled)
                        .frame(maxWidth: .infinity, alignment: .leading).padding(.top, 8)
                }
                detail("Введите точную фразу подтверждения", preview.confirmationToken)
                TextField("CONFIRM-…", text: $token).textFieldStyle(.roundedBorder).font(.body.monospaced())
                    .autocorrectionDisabled().disabled(model.locked)
                if preview.requiresGlobalSkillsAcknowledgement {
                    Toggle("Понимаю: это запись в общую библиотеку, без выполнения и выдачи разрешений", isOn: $acknowledgeGlobal)
                        .toggleStyle(.checkbox).disabled(model.locked)
                }
                HStack {
                    Button(preview.operation.title) { Task { await model.confirm(token: token, acknowledgeGlobal: acknowledgeGlobal) } }
                        .buttonStyle(.borderedProminent).nativeHoverSurface()
                        .disabled(model.locked || !preview.accepts(token: token, acknowledgeGlobal: acknowledgeGlobal))
                    Button("Отмена") { model.invalidateConfirmation() }.disabled(model.locked)
                }
            } else {
                Text("Подтверждение недоступно. Ничего не изменено.").font(.callout).foregroundStyle(.orange)
                findings(preview.issues, color: .orange)
            }
        }.skillCard().overlay(RoundedRectangle(cornerRadius: 12).stroke(Color.accentColor.opacity(0.4), lineWidth: 1))
    }

    private func receiptCard(_ receipt: NativeSkillReceipt, title: String) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Label(title, systemImage: "checkmark.seal").font(.headline)
            detail("Receipt", "\(receipt.id) · \(receipt.createdAt)")
            if receipt.kind == "apply" {
                detail("Навык", receipt.recordId)
                Text("Проверка текущей записи: \(receipt.verificationStatus)").font(.callout)
                detail("SHA до", receipt.beforeStoreSha256)
                detail("SHA после", receipt.afterStoreSha256)
                Button("Открыть навык в библиотеке") { Task { await model.openSavedSkill() } }.disabled(model.locked)
            }
            findings(receipt.warnings, color: .orange)
            DisclosureGroup("Полные поля результата") {
                Text(receipt.details).font(.system(size: 11, design: .monospaced)).textSelection(.enabled)
                    .frame(maxWidth: .infinity, alignment: .leading).padding(.top, 8)
            }.font(.caption)
        }.skillCard()
    }

    private func diagnostics(_ report: NativeSkillReview) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            findings(report.issues, color: .red)
            DisclosureGroup("Проверки, источники и ограничения") {
                VStack(alignment: .leading, spacing: 8) {
                    findings(report.warnings + report.applyIssues, color: .secondary)
                    ForEach(report.sourceChecks.keys.sorted(), id: \.self) { name in
                        Label(name, systemImage: report.sourceChecks[name] == true ? "checkmark.circle" : "minus.circle").font(.caption)
                    }
                    ForEach(report.storeHashes.keys.sorted(), id: \.self) { name in detail(name, report.storeHashes[name] ?? "") }
                }.padding(.top, 8)
            }
        }.skillCard()
    }

    private func singleField(_ title: String, prompt: String, text: Binding<String>) -> some View {
        VStack(alignment: .leading, spacing: 5) {
            Text(title).font(.callout.weight(.medium))
            TextField(prompt, text: text).textFieldStyle(.roundedBorder)
        }
    }

    private func listField(_ title: String, hint: String, text: Binding<String>) -> some View {
        VStack(alignment: .leading, spacing: 5) {
            HStack { Text(title).font(.callout.weight(.medium)); Spacer(); Text(hint).font(.caption).foregroundStyle(.secondary) }
            TextEditor(text: text).font(.system(size: 13)).scrollContentBackground(.hidden)
                .padding(6).frame(height: title == "Шаги" ? 110 : 66)
                .background(Color.primary.opacity(0.035), in: RoundedRectangle(cornerRadius: 7))
                .overlay(RoundedRectangle(cornerRadius: 7).stroke(Color.primary.opacity(0.12), lineWidth: 1))
                .accessibilityLabel(title)
        }
    }

    private func detail(_ title: String, _ value: String) -> some View {
        VStack(alignment: .leading, spacing: 3) {
            Text(title).font(.caption).foregroundStyle(.secondary)
            Text(value).font(.system(size: 11, design: .monospaced)).textSelection(.enabled)
        }
    }

    private func findings(_ values: [String], color: Color) -> some View {
        ForEach(Array(values.enumerated()), id: \.offset) { _, value in Text(value).font(.caption).foregroundStyle(color).textSelection(.enabled) }
    }
}

private extension View {
    func skillCard() -> some View {
        padding(16).frame(maxWidth: .infinity, alignment: .leading)
            .background(Color.primary.opacity(0.035), in: RoundedRectangle(cornerRadius: 12))
    }
}
