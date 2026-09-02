import SwiftUI

struct SkillOutcomeView: View {
    @ObservedObject var model: SkillOutcomeModel
    @State private var token = ""
    @State private var acknowledgement = false

    var body: some View {
        VStack(spacing: 0) {
            HStack(spacing: 12) {
                Image(systemName: "checklist").font(.title2)
                VStack(alignment: .leading, spacing: 4) {
                    Text("Результат ручного использования").font(.title2.weight(.semibold))
                    Text("Ваше наблюдение, не автоматическая проверка навыка").font(.caption).foregroundStyle(.secondary)
                }
                Spacer()
                if model.loading || model.committing { ProgressView().controlSize(.small) }
                Button { Task { await model.refresh() } } label: { Image(systemName: "arrow.clockwise") }
                    .disabled(model.locked).help("Обновить условия и квитанции; сбросить старое подтверждение")
                Button { model.close() } label: { Image(systemName: "xmark") }
                    .disabled(model.committing).keyboardShortcut(.cancelAction)
            }.padding(22)
            Divider()
            ScrollViewReader { scroll in
                ScrollView {
                    VStack(alignment: .leading, spacing: 18) {
                        if let error = model.error {
                            Label(error, systemImage: "exclamationmark.triangle").font(.callout).foregroundStyle(.orange).textSelection(.enabled).outcomeCard()
                        }
                        if let report = model.report {
                            conditions(report)
                            if report.sourceEligible { form(report) }
                            if let preview = model.preview { confirmation(preview).id("outcome-confirmation") }
                            if !report.receipts.isEmpty {
                                HStack {
                                    Text("Записи этого навыка в текущем диалоге").font(.headline)
                                    Spacer()
                                    Button("Открыть результаты") { Task { await model.openEvidence() } }.disabled(model.locked)
                                }
                                ForEach(report.receipts) { receipt in receiptCard(receipt) }
                            }
                            DisclosureGroup("Условия, источники и ограничения") {
                                VStack(alignment: .leading, spacing: 8) {
                                    ForEach(Array(report.reasons.enumerated()), id: \.offset) { _, reason in
                                        Text(reason).font(.caption).foregroundStyle(.orange).textSelection(.enabled)
                                    }
                                    ForEach(report.storeHashes.keys.sorted(), id: \.self) { key in detail(key, report.storeHashes[key] ?? "") }
                                    Text("Навыки и уроки пока общие для проектов. Рабочая папка привязывает подтверждение, но не создаёт изоляцию библиотеки.")
                                        .font(.caption).foregroundStyle(.secondary)
                                }.padding(.top, 10)
                            }.outcomeCard()
                        } else if model.loading {
                            Text("Проверяем навык, источник и разрешение текущего диалога…").foregroundStyle(.secondary)
                        }
                        Text("Без LLM, выполнения процедуры, записи файлов, изменения uses, автоматического обучения, архивации и восстановления. Context Injection и права инструментов не меняются.")
                            .font(.caption).foregroundStyle(.secondary)
                    }.padding(22)
                }
                .onChange(of: model.preview?.previewFingerprint) { _, value in
                    token = ""; acknowledgement = false
                    if value != nil { scroll.scrollTo("outcome-confirmation", anchor: .top) }
                }
            }
        }.frame(width: 850, height: 720).buttonStyle(.nativeHover).interactiveDismissDisabled(model.committing)
    }

    private func conditions(_ report: NativeSkillOutcomeReview) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Text(report.name.isEmpty ? "Навык недоступен" : report.name).font(.title3.weight(.semibold))
                Spacer()
                Text(report.captureAvailable ? "Можно подготовить запись" : "Запись пока недоступна").font(.caption).foregroundStyle(.secondary)
            }
            Text("Фиксируется уже выполненное вами ручное использование. После отдельного подтверждения ядро добавит четыре связанных события и одну квитанцию только в оперативную память. Они исчезнут при перезапуске.")
                .font(.callout).foregroundStyle(.secondary)
            Text("Событий: \(report.eventCount)/\(report.eventLimit) · Квитанций: \(report.receiptCount)/\(report.receiptLimit)")
                .font(.caption.monospacedDigit()).foregroundStyle(.secondary)
            if !report.sourceEligible {
                Label("Нужен активный навык с проверенным происхождением. Для архивных, восстановленных и неподтверждённых записей этот путь недоступен.", systemImage: "hand.raised")
                    .font(.callout).foregroundStyle(.orange)
            }
            if !report.contextInjectionDisabled {
                Label("Отключённый Context Injection не подтверждён. Настройка не будет изменена автоматически.", systemImage: "lock.shield")
                    .font(.callout).foregroundStyle(.orange)
            }
            if report.pilotState != "consented" {
                Label("Сначала нужно отдельное согласие на сбор опыта в этом диалоге", systemImage: "hand.raised").font(.callout.weight(.medium))
                Text(report.pilotState == "stopped" || report.pilotState == "expired"
                     ? "Сбор опыта остановлен для этой сессии ядра. Открытие формы его не возобновляет."
                     : "В Workshop подготовьте /experience preview, отправьте команду вручную и подтвердите показанную сессионную фразу. Это существующее согласие также разрешает ограниченный сбор обычных ходов диалога, не только этой записи.")
                    .font(.caption).foregroundStyle(.secondary)
                Button("Открыть Workshop для настройки согласия") { model.openConsentHelp() }
                    .buttonStyle(.bordered).nativeHoverSurface().disabled(model.locked)
                Text("Только откроется экран. Команды не выполняются, несохранённая форма результата будет закрыта.")
                    .font(.caption).foregroundStyle(.secondary)
            }
            if report.changedSinceSelection {
                Label("Библиотека изменилась после выбора. Предпросмотр использует свежие данные.", systemImage: "arrow.clockwise")
                    .font(.caption).foregroundStyle(.orange)
            }
            detail("Skill ID", model.scope.skillID)
        }.outcomeCard()
    }

    private func form(_ report: NativeSkillOutcomeReview) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Что произошло при ручном использовании?").font(.headline)
            Picker("Результат", selection: $model.outcome) {
                Text("Успех").tag("success")
                Text("Ошибка или исправление").tag("failure")
            }.pickerStyle(.segmented).disabled(model.locked)
            Text("Кратко: что ожидалось, что вы сделали и что наблюдали. Не добавляйте пароли или токены; встроенное скрытие секретов не гарантирует распознавание всех форматов.")
                .font(.caption).foregroundStyle(.secondary)
            TextEditor(text: $model.evidence).font(.system(size: 13)).scrollContentBackground(.hidden)
                .padding(8).frame(height: 110).background(Color.primary.opacity(0.035), in: RoundedRectangle(cornerRadius: 8))
                .overlay(RoundedRectangle(cornerRadius: 8).stroke(Color.primary.opacity(0.12), lineWidth: 1))
                .accessibilityLabel("Описание ручного результата").disabled(model.locked)
            HStack {
                Text("\(model.evidence.unicodeScalars.count)/800 символов").font(.caption)
                    .foregroundStyle(model.evidence.unicodeScalars.count > 800 ? .red : .secondary)
                Spacer()
                Button("Проверить перед записью…") { Task { await model.prepare() } }
                    .buttonStyle(.bordered).nativeHoverSurface()
                    .disabled(model.locked || !report.captureAvailable || !model.selection.complete)
            }
            Text("Редактирование и предпросмотр не создают события. Исправление описывается как ручной неуспех; навык от этого не меняется.")
                .font(.caption).foregroundStyle(.secondary)
        }.outcomeCard()
    }

    private func confirmation(_ preview: NativeSkillOutcomePreview) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            Label("Подтверждение одной записи опыта", systemImage: preview.ready ? "checkmark.shield" : "hand.raised").font(.headline)
            if preview.ready {
                Text(preview.outcome == "success" ? "Успех, сообщённый оператором" : "Ошибка / исправление, сообщённые оператором").font(.callout.weight(.semibold))
                Text(preview.evidencePreview).font(.callout).textSelection(.enabled)
                Text("Краткий текст после обработки ядром, до 160 символов. Полная обработанная формулировка связана SHA-256; исходный текст не пишется в файлы.")
                    .font(.caption).foregroundStyle(.secondary)
                detail("Fingerprint описания", preview.evidenceFingerprint)
                detail("Введите точную фразу", preview.confirmationToken)
                TextField("CONFIRM-SKILL-OUTCOME-…", text: $token).textFieldStyle(.roundedBorder).font(.body.monospaced())
                    .autocorrectionDisabled().disabled(model.locked)
                Toggle("Это мой ручной результат, не проверка Proto-Mind; запись только до перезапуска ядра", isOn: $acknowledgement)
                    .toggleStyle(.checkbox).disabled(model.locked)
                HStack {
                    Button("Записать ручной результат") { Task { await model.confirm(token: token, acknowledgement: acknowledgement) } }
                        .buttonStyle(.borderedProminent).nativeHoverSurface()
                        .disabled(model.locked || !preview.accepts(token: token, acknowledgement: acknowledgement))
                    Button("Отмена") { model.invalidate() }.disabled(model.locked)
                }
            } else {
                Text("Запись отказана. Проверьте причину, не повторяйте автоматически.").font(.callout).foregroundStyle(.orange)
                ForEach(Array(preview.reasons.enumerated()), id: \.offset) { _, reason in Text(reason).font(.caption).textSelection(.enabled) }
            }
        }.outcomeCard().overlay(RoundedRectangle(cornerRadius: 12).stroke(Color.accentColor.opacity(0.4), lineWidth: 1))
    }

    private func receiptCard(_ receipt: NativeSkillOutcomeReceipt) -> some View {
        VStack(alignment: .leading, spacing: 9) {
            Label(receipt.outcome == "success" ? "Оператор сообщил об успехе" : "Оператор сообщил об ошибке / исправлении", systemImage: "doc.text")
                .font(.headline)
            Text(receipt.evidencePreview).font(.callout).textSelection(.enabled)
            Text("\(receipt.createdAt) · Проверка связности квитанции: \(receipt.verificationStatus)").font(.caption).foregroundStyle(.secondary)
            Text("Результат записан в текущем процессе. Это не независимая проверка качества и не решение об обучении.")
                .font(.caption).foregroundStyle(.secondary)
            DisclosureGroup("Квитанция и ссылки на события") {
                VStack(alignment: .leading, spacing: 8) {
                    detail("Receipt ID", receipt.id)
                    detail("Receipt SHA-256", receipt.receiptHash)
                    detail("Сессия опыта", receipt.sessionId)
                    ForEach(receipt.eventIds, id: \.self) { detail("Событие", $0) }
                }.padding(.top, 8)
            }
        }.outcomeCard()
    }

    private func detail(_ title: String, _ value: String) -> some View {
        VStack(alignment: .leading, spacing: 3) {
            Text(title).font(.caption).foregroundStyle(.secondary)
            Text(value).font(.system(size: 11, design: .monospaced)).textSelection(.enabled)
                .fixedSize(horizontal: false, vertical: true)
        }
    }
}

private extension View {
    func outcomeCard() -> some View {
        padding(16).frame(maxWidth: .infinity, alignment: .leading)
            .background(Color.primary.opacity(0.035), in: RoundedRectangle(cornerRadius: 12))
    }
}
