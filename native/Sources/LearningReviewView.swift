import SwiftUI

struct LearningReviewView: View {
    @ObservedObject var model: AppModel
    @State private var token = ""
    @State private var acknowledgeGlobal = false

    private var locked: Bool { model.busy || model.loadingLearningReview }

    var body: some View {
        VStack(spacing: 0) {
            HStack(spacing: 12) {
                Button {
                    model.closeLearningReview()
                    Task { await model.refreshMemoryWorkshop() }
                } label: { Image(systemName: "chevron.left") }.disabled(locked)
                VStack(alignment: .leading, spacing: 3) {
                    Text("Разбор урока").font(.title2.weight(.semibold))
                    Text("Решение → предложение → одна проверенная запись")
                        .font(.caption).foregroundStyle(.secondary)
                }
                Spacer()
                if model.loadingLearningReview || model.committingLearningReview { ProgressView().controlSize(.small) }
                Button { Task { await model.refreshLearningReview() } } label: { Image(systemName: "arrow.clockwise") }
                    .disabled(locked).help("Перечитать evidence и сбросить старое подтверждение")
                Button { model.showMemoryWorkshop = false } label: { Image(systemName: "xmark") }
                    .disabled(model.committingLearningReview).keyboardShortcut(.cancelAction)
            }.padding(22)
            Divider()
            ScrollViewReader { scroll in
              ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    boundary
                    if let error = model.learningReviewError {
                        Label(error, systemImage: "exclamationmark.triangle")
                            .font(.callout).foregroundStyle(.orange).textSelection(.enabled).learningCard()
                    }
                    if model.committingLearningReview {
                        Label("Подтверждаем один шаг. Не закрывайте ядро до получения результата.", systemImage: "hourglass")
                            .font(.callout).learningCard()
                    }
                    if let report = model.learningReview {
                        if let candidate = report.candidate {
                            evidence(candidate)
                            stages(report)
                            if let preview = model.learningPreview { confirmation(preview).id("learning-confirmation") }
                            if let receipt = report.decision { receiptCard(receipt, title: "Решение оператора") }
                            if let receipt = report.proposal { receiptCard(receipt, title: "Предложение записи") }
                            if let receipt = report.applyReceipt { receiptCard(receipt, title: "Результат сохранения") }
                        } else {
                            Label("Кандидат не найден в текущем ядре", systemImage: "tray")
                                .font(.headline).learningCard()
                            Text("После перезапуска process-memory кандидаты и решения не восстанавливаются автоматически. Уже сохранённый урок можно найти в Памяти и проверить его происхождение.")
                                .foregroundStyle(.secondary)
                        }
                        diagnostics(report)
                    } else if model.loadingLearningReview {
                        Text("Читаем локальные evidence и текущие хранилища…").foregroundStyle(.secondary)
                    }
                    Text("Ни одно действие не запускает модель, инструменты, slash-команду или автоматическое обучение.")
                        .font(.caption).foregroundStyle(.secondary)
                }.padding(22)
              }
              .onChange(of: model.learningPreview?.previewFingerprint) { _, value in
                  if value != nil { scroll.scrollTo("learning-confirmation", anchor: .top) }
              }
            }
        }
        .onChange(of: model.learningPreview?.previewFingerprint) { _, _ in
            token = ""; acknowledgeGlobal = false
        }
    }

    private var boundary: some View {
        VStack(alignment: .leading, spacing: 8) {
            Label("Под вашим контролем", systemImage: "hand.raised").font(.headline)
            Text("Принятие кандидата ещё не сохраняет урок. Предложение тоже не пишет в память. Только последний шаг добавляет одну запись memory.lesson.v1.")
                .font(.callout).foregroundStyle(.secondary)
            Label("Память общая для проектов, а не изолирована выбранной папкой", systemImage: "folder.badge.questionmark")
                .font(.callout.weight(.medium)).foregroundStyle(.orange)
            Text("Один apply на всё запущенное Native-ядро. Решения и предложения живут до его закрытия; предложение действует 15 минут. Сохранённый урок и его provenance переживают перезапуск.")
                .font(.caption).foregroundStyle(.secondary)
        }.learningCard()
    }

    private func evidence(_ candidate: NativeLearningCandidate) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Label("Кандидат, не установленный факт", systemImage: "text.quote").font(.headline)
                Spacer()
                Text(candidate.reviewStatus).font(.caption).foregroundStyle(.secondary)
            }
            Text(candidate.text).font(.body).textSelection(.enabled)
            Text(candidate.rationale).font(.callout).foregroundStyle(.secondary)
            detail("Candidate ID", candidate.id)
            detail("Источники", candidate.sourceKinds.joined(separator: " · "))
            detail("Evidence IDs", candidate.evidenceEventIds.joined(separator: "\n"))
            Text("Confidence из evidence: \(candidate.confidence). Это не независимая проверка истинности урока.")
                .font(.caption).foregroundStyle(.secondary)
        }.learningCard()
    }

    private func stages(_ report: NativeLearningReview) -> some View {
        VStack(alignment: .leading, spacing: 15) {
            stageTitle("1", "Решение", state: report.decision?.status ?? "не принято")
            if report.decision == nil {
                TextField("Причина решения, необязательно (до 160 символов)", text: $model.learningReason)
                    .textFieldStyle(.roundedBorder).disabled(locked)
                HStack {
                    previewButton(.accept, disabled: report.candidate?.reviewStatus != "operator_review_required")
                    previewButton(.reject)
                }
            }
            Divider()
            stageTitle("2", "Сравнение и предложение", state: report.proposal == nil ? report.eligibilityStatus : "подтверждено")
            if report.decision?.status == "accepted", report.proposal == nil {
                Text("Выберите от 1 до 20 активных записей для сравнения. Они не изменятся; выбор ограничивает проверку дублей, а не доступ к проектам.")
                    .font(.callout).foregroundStyle(.secondary)
                HStack {
                    TextField("Поиск по ID или тексту памяти", text: $model.learningReferenceQuery)
                        .textFieldStyle(.roundedBorder).onSubmit { Task { await model.refreshLearningReview() } }
                    Button("Найти") { Task { await model.refreshLearningReview() } }
                }.disabled(locked)
                if report.references.isEmpty {
                    Text("Подходящих активных записей нет. Предложение не создаётся без явно выбранного reference ID.")
                        .font(.callout).foregroundStyle(.secondary)
                }
                ForEach(report.references) { reference in
                    Toggle(isOn: Binding(get: { model.learningReferenceIDs.contains(reference.recordId) },
                                         set: {
                                             model.setLearningReference(reference.recordId, selected: $0)
                                             Task { await model.refreshLearningReview() }
                                         })) {
                        VStack(alignment: .leading, spacing: 3) {
                            Text(reference.preview).font(.callout)
                            Text("\(reference.store) · \(reference.recordId)").font(.caption.monospaced()).foregroundStyle(.secondary)
                        }
                    }.toggleStyle(.checkbox)
                        .disabled(locked || !reference.selectable || (model.learningReferenceIDs.count >= 20 && !model.learningReferenceIDs.contains(reference.recordId)))
                }
                Text("Выбрано: \(model.learningReferenceIDs.count)/20. За лимитом выдачи: \(report.omittedReferenceCount).")
                    .font(.caption).foregroundStyle(.secondary)
                if !model.learningReferenceIDs.isEmpty { detail("Точный scope", model.learningReferenceIDs.joined(separator: " · ")) }
                previewButton(.propose, disabled: model.learningReferenceIDs.isEmpty)
            } else if report.proposal != nil {
                detail("Зафиксированные reference IDs", report.requestedMemoryIds.joined(separator: " · "))
            } else {
                Text("Сначала необходимо отдельное принятие кандидата.").font(.caption).foregroundStyle(.secondary)
            }
            Divider()
            stageTitle("3", "Запись урока", state: report.applyReceipt == nil ? report.applyStatus : "сохранён")
            if report.applyReceipt == nil {
                Text("Preview перепроверит evidence, возраст предложения, SHA хранилищ и активные точные дубли. Затем потребуется отдельное подтверждение записи в общую память.")
                    .font(.caption).foregroundStyle(.secondary)
                previewButton(.apply, disabled: report.proposal == nil || !report.nativeApplySlotAvailable)
                if !report.nativeApplySlotAvailable {
                    Text("Лимит одной записи уже использован в этом Native-ядре.").font(.caption).foregroundStyle(.orange)
                }
            } else {
                Text("Повторное сохранение недоступно. Проверьте receipt ниже.").font(.callout).foregroundStyle(.secondary)
            }
        }.learningCard()
    }

    private func confirmation(_ preview: NativeLearningPreview) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            Label(preview.operation.title, systemImage: preview.ready ? "checkmark.shield" : "hand.raised.slash")
                .font(.headline)
            Text(preview.ready ? "Preview готов. Этот шаг ещё не выполнен." : "Шаг недоступен. Ничего не выполнено.")
                .foregroundStyle(preview.ready ? Color.secondary : .orange)
            if preview.ready {
                Text(preview.content).textSelection(.enabled)
                Text(preview.operation == .apply
                     ? "Будет добавлена ровно одна запись в proto_mind/data/persistent_memory.json. Другие записи сохраняют исходные поля."
                     : "Изменится только решение или предложение в оперативной памяти ядра. Файлы не изменятся.")
                    .font(.callout).foregroundStyle(.secondary)
                detail("Введите точную фразу подтверждения", preview.confirmationToken)
                TextField("CONFIRM-…", text: $token).textFieldStyle(.roundedBorder).font(.body.monospaced())
                    .disabled(locked).autocorrectionDisabled()
                if preview.requiresGlobalMemoryAcknowledgement {
                    Toggle("Понимаю: урок станет частью общей памяти Proto-Mind для всех проектов", isOn: $acknowledgeGlobal)
                        .toggleStyle(.checkbox).disabled(locked)
                }
                HStack {
                    Button(preview.operation.title) {
                        Task { await model.confirmLearningOperation(token: token, acknowledgeGlobal: acknowledgeGlobal) }
                    }.buttonStyle(.borderedProminent).nativeHoverSurface()
                        .disabled(locked || !preview.accepts(token: token, acknowledgeGlobal: acknowledgeGlobal))
                    Button("Отмена") { model.invalidateLearningConfirmation() }.disabled(locked)
                }
                detail("Fingerprint", preview.previewFingerprint)
            } else {
                findings(preview.issues, color: .orange)
            }
        }.learningCard()
            .overlay(RoundedRectangle(cornerRadius: 12).stroke(Color.accentColor.opacity(0.35), lineWidth: 1))
    }

    private func receiptCard(_ receipt: NativeLearningReceipt, title: String) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Label(title, systemImage: receipt.kind == "apply" ? "checkmark.seal" : "doc.text").font(.headline)
            detail("Receipt", "\(receipt.id) · \(receipt.status) · \(receipt.createdAt)")
            if receipt.kind == "apply" {
                detail("Запись памяти", receipt.recordId)
                detail("Durable provenance", receipt.durableProvenanceId)
                Text("Проверка текущей записи: \(receipt.verificationStatus)").font(.callout.weight(.medium))
                detail("SHA до", receipt.beforeStoreSha256)
                detail("SHA после", receipt.afterStoreSha256)
                Button("Открыть запись и происхождение") {
                    model.showMemoryWorkshop = false
                    Task { await model.openMemoryEvidence(recordID: receipt.recordId) }
                }.disabled(locked)
                detail("Только ручной rollback, здесь не выполняется", receipt.rollbackSuggestion)
            }
            findings(receipt.warnings, color: .orange)
            DisclosureGroup("Полные поля receipt") {
                Text(receipt.details).font(.system(size: 11, design: .monospaced)).textSelection(.enabled)
                    .frame(maxWidth: .infinity, alignment: .leading).padding(.top, 8)
            }.font(.caption)
        }.learningCard()
    }

    private func diagnostics(_ report: NativeLearningReview) -> some View {
        DisclosureGroup("Проверки и границы хранения") {
            VStack(alignment: .leading, spacing: 9) {
                findings(report.issues, color: .red)
                findings(report.warnings + report.eligibilityWarnings + report.applyWarnings, color: .secondary)
                ForEach(report.applyChecks.keys.sorted(), id: \.self) { name in
                    Label(name, systemImage: report.applyChecks[name] == true ? "checkmark.circle" : "minus.circle")
                        .font(.caption).foregroundStyle(.secondary)
                }
                ForEach(report.storeHashes.keys.sorted(), id: \.self) { name in detail(name, report.storeHashes[name] ?? "") }
            }.padding(.top, 8)
        }.learningCard()
    }

    private func previewButton(_ operation: NativeLearningOperation, disabled: Bool = false) -> some View {
        Button("\(operation.title)…") { Task { await model.previewLearningOperation(operation) } }
            .buttonStyle(.bordered).nativeHoverSurface().disabled(locked || disabled || model.learningReview?.issues.isEmpty == false)
    }

    private func stageTitle(_ number: String, _ title: String, state: String) -> some View {
        HStack {
            Text(number).font(.caption.weight(.bold)).frame(width: 24, height: 24)
                .background(Color.primary.opacity(0.07), in: Circle())
            Text(title).font(.headline)
            Spacer()
            Text(state).font(.caption).foregroundStyle(.secondary).lineLimit(2)
        }
    }

    private func detail(_ label: String, _ value: String) -> some View {
        VStack(alignment: .leading, spacing: 3) {
            Text(label).font(.caption).foregroundStyle(.secondary)
            Text(value).font(.system(size: 11, design: .monospaced)).textSelection(.enabled)
                .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    private func findings(_ values: [String], color: Color) -> some View {
        ForEach(Array(values.enumerated()), id: \.offset) { _, value in
            Text(value).font(.caption).foregroundStyle(color).textSelection(.enabled)
        }
    }
}

private extension View {
    func learningCard() -> some View {
        padding(15).frame(maxWidth: .infinity, alignment: .leading)
            .background(Color.primary.opacity(0.035), in: RoundedRectangle(cornerRadius: 12))
    }
}
