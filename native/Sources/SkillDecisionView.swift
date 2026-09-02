import SwiftUI

struct SkillDecisionView: View {
    @ObservedObject var model: SkillDecisionModel
    @State private var token = ""
    @State private var acknowledgement = false

    var body: some View {
        VStack(spacing: 0) {
            HStack(spacing: 12) {
                Image(systemName: "list.clipboard").font(.title2)
                VStack(alignment: .leading, spacing: 4) {
                    Text("Решение по результатам навыка").font(.title2.weight(.semibold))
                    Text("Ручной выбор, не изменение навыка и не разрешение на запуск").font(.caption).foregroundStyle(.secondary)
                }
                Spacer()
                if model.loading || model.committing { ProgressView().controlSize(.small) }
                Button { Task { await model.refresh() } } label: { Image(systemName: "arrow.clockwise") }
                    .disabled(model.locked).help("Перепроверить основания; сбросить выбор и подтверждение")
                Button { model.close() } label: { Image(systemName: "xmark") }
                    .disabled(model.committing).keyboardShortcut(.cancelAction)
            }.padding(22)
            Divider()
            ScrollViewReader { scroll in
                ScrollView {
                    VStack(alignment: .leading, spacing: 18) {
                        if let error = model.error {
                            Label(error, systemImage: "exclamationmark.triangle").font(.callout).foregroundStyle(.orange).textSelection(.enabled).decisionCard()
                        }
                        if let report = model.report {
                            overview(report)
                            if let receipt = report.receipt { receiptCard(receipt) }
                            else { choices(report) }
                            if let preview = model.preview { confirmation(preview).id("decision-confirmation") }
                            DisclosureGroup("Точные источники и ограничения") {
                                VStack(alignment: .leading, spacing: 8) {
                                    detail("Skill ID", model.scope.skillID)
                                    detail("Сессия опыта", report.sessionId.isEmpty ? "Не запущена" : report.sessionId)
                                    ForEach(report.storeHashes.keys.sorted(), id: \.self) { key in detail(key, report.storeHashes[key] ?? "") }
                                    ForEach(Array((report.issues + report.reasons + report.warnings).enumerated()), id: \.offset) { _, reason in
                                        Text(reason).font(.caption).foregroundStyle(.secondary).textSelection(.enabled)
                                    }
                                    Text("Библиотека навыков пока общая для проектов. Рабочая папка привязывает подтверждение, но не создаёт изоляцию хранения.")
                                        .font(.caption).foregroundStyle(.secondary)
                                }.padding(.top, 10)
                            }.decisionCard()
                        } else if model.loading { Text("Проверяем существующие результаты и решения…").foregroundStyle(.secondary) }
                        Text("Без LLM, команд, новых событий опыта и записи файлов. Сбор опыта, Context Injection и права не меняются. Открытие экрана не выбирает решение.")
                            .font(.caption).foregroundStyle(.secondary)
                    }.padding(22)
                }
                .onChange(of: model.preview?.previewFingerprint) { _, value in
                    token = ""; acknowledgement = false
                    if value != nil { scroll.scrollTo("decision-confirmation", anchor: .top) }
                }
            }
        }.frame(width: 850, height: 720).buttonStyle(.nativeHover).interactiveDismissDisabled(model.committing)
    }

    private func overview(_ report: NativeSkillDecisionReview) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Text(report.name.isEmpty ? "Навык недоступен" : report.name).font(.title3.weight(.semibold))
                Spacer()
                Text(report.status).font(.caption.weight(.semibold)).foregroundStyle(report.status == "ERROR" ? .red : .secondary)
            }
            Text(outcomeTitle(report.outcomeStatus)).font(.callout.weight(.medium))
            Text("Основания: \(report.manualUseCount) ручных использований, \(report.signalCount) сигналов результата. Решений в диалоге: \(report.decisionCount)/\(report.decisionLimit).")
                .font(.caption).foregroundStyle(.secondary)
            Text("После точного подтверждения сохранится одна квитанция только в памяти текущего ядра. Она исчезнет при перезапуске. Навык и его статус останутся прежними.")
                .font(.callout).foregroundStyle(.secondary)
            if report.status == "NOT_READY" {
                Label("Нужен активный навык с проверенным происхождением и точной квитанцией ручного результата в этом диалоге.", systemImage: "hand.raised")
                    .font(.callout).foregroundStyle(.orange)
            }
            if !report.contextInjectionDisabled {
                Text("Отключённый Context Injection не подтверждён. Настройка не будет изменена автоматически.").font(.caption).foregroundStyle(.orange)
            }
            if report.changedSinceSelection {
                Label("Источник изменился после выбора; показаны свежие данные.", systemImage: "arrow.clockwise").font(.caption).foregroundStyle(.orange)
            }
            Button("Вернуться к результатам и источнику") { Task { await model.openEvidence() } }
                .buttonStyle(.bordered).nativeHoverSurface().disabled(model.locked)
        }.decisionCard()
    }

    private func choices(_ report: NativeSkillDecisionReview) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Какое решение вы принимаете?").font(.headline)
            ForEach(report.choices) { choice in
                VStack(alignment: .leading, spacing: 6) {
                    Button { model.choice = choice.decision } label: {
                        Label(choice.decision.title, systemImage: model.choice == choice.decision ? "largecircle.fill.circle" : "circle")
                            .frame(maxWidth: .infinity, alignment: .leading)
                    }.buttonStyle(.bordered).nativeHoverSurface().disabled(model.locked || !choice.allowed)
                    Text(choice.decision.explanation).font(.caption).foregroundStyle(.secondary)
                    if !choice.allowed {
                        Text("Недоступно при текущих основаниях. Точная причина ниже в источниках или подробностях выбора.")
                            .font(.caption).foregroundStyle(.secondary)
                        DisclosureGroup("Почему недоступно") {
                            ForEach(Array(choice.reasons.enumerated()), id: \.offset) { _, reason in Text(reason).font(.caption).textSelection(.enabled) }
                        }.font(.caption)
                    }
                }
            }
            Text("Успех допускает только «оставить». Ошибка или смешанные результаты допускают «доработать» либо «рекомендовать архивирование». Выбор остаётся за вами.")
                .font(.caption).foregroundStyle(.secondary)
            Button("Проверить выбранное решение…") { Task { await model.prepare() } }
                .buttonStyle(.bordered).nativeHoverSurface().disabled(!model.canPrepare)
        }.decisionCard()
    }

    private func confirmation(_ preview: NativeSkillDecisionPreview) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            Label("Подтвердить только решение", systemImage: preview.ready ? "checkmark.shield" : "hand.raised").font(.headline)
            if let evidence = preview.blueprint, preview.ready {
                Text(preview.decision.title).font(.callout.weight(.semibold))
                Text(preview.decision.explanation).font(.callout).foregroundStyle(.secondary)
                detail("Точный сигнал результата", evidence.selectedSignalId)
                Text("Квитанций ручного результата: \(evidence.captureReceiptIds.count). Они связаны с текущим разбором и проверены ядром.").font(.caption).foregroundStyle(.secondary)
                detail("Введите точную фразу", preview.confirmationToken)
                TextField("CONFIRM-SKILL-…", text: $token).textFieldStyle(.roundedBorder).font(.body.monospaced())
                    .autocorrectionDisabled().disabled(model.locked)
                Toggle("Подтверждаю только решение до перезапуска ядра; не изменение или запуск навыка", isOn: $acknowledgement)
                    .toggleStyle(.checkbox).disabled(model.locked)
                Text("Одно окончательное решение для навыка в текущем диалоге. Поздние доказательства могут сделать его историческим, но не перепишут его.")
                    .font(.caption).foregroundStyle(.secondary)
                HStack {
                    Button("Записать только решение") { Task { await model.confirm(token: token, acknowledgement: acknowledgement) } }
                        .buttonStyle(.borderedProminent).nativeHoverSurface()
                        .disabled(model.locked || !preview.accepts(token: token, acknowledgement: acknowledgement))
                    Button("Отмена") { model.invalidate() }.disabled(model.locked)
                }
            } else {
                Text("Подтверждение недоступно. Ничего не записано; обновите основания вручную.").font(.callout).foregroundStyle(.orange)
                ForEach(Array(preview.reasons.enumerated()), id: \.offset) { _, reason in Text(reason).font(.caption).textSelection(.enabled) }
            }
        }.decisionCard().overlay(RoundedRectangle(cornerRadius: 12).stroke(Color.accentColor.opacity(0.4), lineWidth: 1))
    }

    private func receiptCard(_ receipt: NativeSkillDecisionReceipt) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Label("Записанное решение: \(receipt.evidence.decision.title)", systemImage: "doc.text").font(.headline)
            Text("\(receipt.createdAt) · Проверка квитанции: \(receipt.verificationStatus)").font(.caption).foregroundStyle(.secondary)
            if receipt.evidenceState == "HISTORICAL" {
                Label("Историческое решение: текущие основания отличаются. Оно не заменено и не считается актуальным разрешением.", systemImage: "clock.arrow.circlepath")
                    .font(.callout).foregroundStyle(.orange)
            } else {
                Text(receipt.evidenceState == "CURRENT" ? "Основания решения пока актуальны. Это всё равно не разрешение на применение или выполнение."
                     : "Актуальность оснований не подтверждена. Не используйте эту квитанцию для последующих действий.")
                    .font(.callout).foregroundStyle(.secondary)
            }
            Text(receipt.evidence.decision.nextStep).font(.callout).foregroundStyle(.secondary)
            Button("Проверить применение решения…") { Task { await model.openLifecycleApply() } }
                .buttonStyle(.bordered).nativeHoverSurface().disabled(model.locked)
            Text("Откроется отдельный экран. Сам переход требует новой точной фразы и подтверждения общей библиотеки.")
                .font(.caption).foregroundStyle(.secondary)
            DisclosureGroup("Квитанция и точная связь с результатами") {
                VStack(alignment: .leading, spacing: 7) {
                    detail("Decision receipt", receipt.id)
                    detail("Receipt SHA-256", receipt.receiptHash)
                    detail("Review SHA-256", receipt.evidence.reviewHash)
                    detail("Decision SHA-256", receipt.evidence.decisionHash)
                    ForEach(receipt.evidence.captureReceiptIds, id: \.self) { detail("Квитанция ручного результата", $0) }
                    ForEach(receipt.evidence.evidenceEventIds, id: \.self) { detail("Сигнал результата", $0) }
                }.padding(.top, 8)
            }
        }.decisionCard()
    }

    private func outcomeTitle(_ status: String) -> String {
        switch status {
        case "SUCCESS_CANDIDATE": return "Оператор сообщил об успехе"
        case "FAILURE_CANDIDATE": return "Оператор сообщил об ошибке или исправлении"
        case "MIXED_EVIDENCE": return "Ручные результаты противоречат друг другу"
        case "ERROR": return "Доказательства не прошли проверку"
        default: return "Точных оснований для решения пока недостаточно"
        }
    }
    private func detail(_ title: String, _ value: String) -> some View {
        VStack(alignment: .leading, spacing: 3) {
            Text(title).font(.caption).foregroundStyle(.secondary)
            Text(value).font(.system(size: 11, design: .monospaced)).textSelection(.enabled).fixedSize(horizontal: false, vertical: true)
        }
    }
}

private extension View {
    func decisionCard() -> some View {
        padding(16).frame(maxWidth: .infinity, alignment: .leading)
            .background(Color.primary.opacity(0.035), in: RoundedRectangle(cornerRadius: 12))
    }
}
