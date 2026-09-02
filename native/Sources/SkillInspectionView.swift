import SwiftUI

struct SkillInspectionView: View {
    @ObservedObject var model: SkillInspectionModel

    var body: some View {
        VStack(spacing: 0) {
            HStack(spacing: 12) {
                Image(systemName: "books.vertical").font(.title2)
                VStack(alignment: .leading, spacing: 4) {
                    Text("Результаты и жизненный цикл").font(.title2.weight(.semibold))
                    Text("Сохранённые факты и доступные доказательства · без действий").font(.caption).foregroundStyle(.secondary)
                }
                Spacer()
                if model.loading { ProgressView().controlSize(.small) }
                Button { Task { await model.refresh() } } label: { Image(systemName: "arrow.clockwise") }
                    .disabled(model.locked).help("Перечитать доказательства без записи и выполнения")
                Button { model.close() } label: { Image(systemName: "xmark") }.keyboardShortcut(.cancelAction)
            }.padding(22)
            Divider()
            ScrollView {
                VStack(alignment: .leading, spacing: 18) {
                    if let error = model.error { Label(error, systemImage: "exclamationmark.triangle").foregroundStyle(.orange).inspectionCard() }
                    if let report = model.report {
                        overview(report)
                        if let outcome = report.outcome { outcomes(outcome, uses: report.usesDisplay) }
                        transitions(report)
                        if let restore = report.restore { restoreEvidence(restore) }
                        VStack(alignment: .leading, spacing: 8) {
                            Label("Что дальше", systemImage: "arrow.right.circle").font(.headline)
                            Text(report.nextAdvice).font(.callout).foregroundStyle(.secondary)
                            Button("Решение по результатам…") { Task { await model.openDecision() } }
                                .buttonStyle(.bordered).nativeHoverSurface().disabled(!model.canOpenDecision)
                            Text("Откроется отдельный разбор. Просмотр не записывает решение и не меняет навык.")
                                .font(.caption).foregroundStyle(.secondary)
                        }.inspectionCard()
                        sources(report)
                    } else if model.loading {
                        Text("Проверяем текущие записи навыка и исходного урока…").foregroundStyle(.secondary)
                    }
                    Text("Только локальный просмотр. Без LLM, запуска навыка, сбора опыта, записи, архивации и восстановления. Разрешения и Context Injection не меняются.")
                        .font(.caption).foregroundStyle(.secondary)
                }.padding(22).textSelection(.enabled)
            }
        }.frame(width: 850, height: 720).buttonStyle(.nativeHover)
    }

    private func overview(_ report: NativeSkillInspection) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(alignment: .top) {
                Text(report.name.isEmpty ? "Навык недоступен" : report.name).font(.title3.weight(.semibold))
                Spacer()
                Text(report.status).font(.caption.weight(.semibold)).foregroundStyle(report.status == "ERROR" ? .red : .secondary)
                    .padding(.horizontal, 9).padding(.vertical, 4).background(Color.primary.opacity(0.06), in: Capsule())
            }
            if let lifecycle = report.lifecycle {
                Label(lifecycle.state.title, systemImage: lifecycle.restartSafe ? "checkmark.seal" : "doc.text.magnifyingglass").font(.headline)
                Text("Сохранённый статус: \(lifecycle.storedStatusTitle)").font(.caption).foregroundStyle(.secondary)
                Text("Проверяется согласованность записи и её происхождения, не эффективность навыка.")
                    .font(.callout).foregroundStyle(.secondary)
                if !lifecycle.sourceLessonId.isEmpty {
                    line("Исходный урок · \(lifecycle.sourceStatus)", lifecycle.sourceLessonId)
                    Button("Открыть исходный урок") { Task { await model.openSource() } }
                        .buttonStyle(.bordered).nativeHoverSurface().disabled(model.locked)
                }
            }
            line("Skill ID", report.skillId)
            Text("Навыки и уроки остаются общей библиотекой проектов. Изоляция по рабочей папке не подразумевается.")
                .font(.caption).foregroundStyle(.secondary)
            if report.changedSinceSelection {
                Label("Источник изменился после выбора. Показана свежая версия.", systemImage: "arrow.clockwise").font(.callout).foregroundStyle(.orange)
            }
            if !report.issues.isEmpty || !report.warnings.isEmpty {
                Label("Ошибок: \(report.issues.count) · Ограничений: \(report.warnings.count)", systemImage: "exclamationmark.triangle")
                    .font(.caption).foregroundStyle(.orange)
            }
        }.inspectionCard()
    }

    private func outcomes(_ outcome: NativeSkillOutcome, uses: String) -> some View {
        VStack(alignment: .leading, spacing: 11) {
            Label("Результаты ручного использования", systemImage: "checklist").font(.headline)
            Text(outcome.title).font(.callout.weight(.semibold))
            Text("Только уже собранный опыт выбранного диалога в текущем ядре. После перезапуска эти события могут быть недоступны; чужие диалоги и тексты чата не подмешиваются.")
                .font(.caption).foregroundStyle(.secondary)
            HStack(spacing: 20) {
                metric("Событий в диалоге", outcome.eventCount)
                metric("Точных использований", outcome.manualUseCount)
                metric("Сигналов результата", outcome.signalCount)
            }.padding(.vertical, 4)
            Text("Сохранённый uses: \(uses). Этот счётчик не доказывает успех и не увеличивается при просмотре.")
                .font(.caption).foregroundStyle(.secondary)
            if outcome.postRestore {
                Text("Исключено: до восстановления \(outcome.preRestoreUseCount); без точной привязки к восстановлению \(outcome.unboundPostRestoreUseCount). Старый успех нельзя повторно использовать как новый.")
                    .font(.caption).foregroundStyle(.orange)
            }
            if outcome.signals.isEmpty {
                Text("Нет подтверждённых сигналов в доступной выборке. Это не означает, что навык не работает или никогда не использовался.")
                    .font(.callout).foregroundStyle(.secondary)
            }
            ForEach(outcome.signals) { signal in
                VStack(alignment: .leading, spacing: 6) {
                    Label(signal.successful ? "Успех, отмеченный оператором" : "Ошибка / исправление оператора",
                          systemImage: signal.successful ? "checkmark.circle" : "exclamationmark.bubble")
                        .font(.callout.weight(.medium))
                    Text(signal.createdAt).font(.caption).foregroundStyle(.secondary)
                    DisclosureGroup("Основание и точные ссылки") {
                        VStack(alignment: .leading, spacing: 7) {
                            Text(signal.reason).font(.caption)
                            line("Событие", signal.eventId)
                            line("Ручное использование", signal.useEventId)
                        }.padding(.top, 7)
                    }
                }.padding(12).frame(maxWidth: .infinity, alignment: .leading)
                    .background(Color.primary.opacity(0.035), in: RoundedRectangle(cornerRadius: 9))
            }
            Text("Даже подтверждённый оператором результат является кандидатом для разбора, не автоматическим обучением и не независимым тестом процедуры.")
                .font(.caption).foregroundStyle(.secondary)
        }.inspectionCard()
    }

    private func transitions(_ report: NativeSkillInspection) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            Label("Сохранённые переходы", systemImage: "clock.arrow.circlepath").font(.headline)
            Text("Это только проверенные следы в текущей записи, не полная история. Недостающие события и причины не достраиваются.")
                .font(.caption).foregroundStyle(.secondary)
            if report.transitions.isEmpty {
                Text("Проверяемая цепочка переходов недоступна. Исходная запись сохранена без изменений.")
                    .font(.callout).foregroundStyle(.secondary)
            }
            ForEach(report.transitions) { transition in
                VStack(alignment: .leading, spacing: 6) {
                    Label(transition.title, systemImage: transition.kind == "apply" ? "plus.circle" : transition.kind == "archive" ? "archivebox" : "arrow.uturn.backward.circle")
                        .font(.callout.weight(.semibold))
                    Text(transition.occurredAt).font(.caption).foregroundStyle(.secondary)
                    DisclosureGroup("Сохранённое основание") {
                        VStack(alignment: .leading, spacing: 7) {
                            Text(transition.reason).font(.caption)
                            line("Metadata ID", transition.id)
                            line("SHA-256", transition.hash)
                            if transition.evidenceCount > 0 { Text("Ссылок на события: \(transition.evidenceCount). Ссылка не восстанавливает исходное событие.").font(.caption) }
                        }.padding(.top, 7)
                    }
                }.padding(.vertical, 6)
            }
        }.inspectionCard()
    }

    private func restoreEvidence(_ restore: NativeSkillRestoreEvidence) -> some View {
        VStack(alignment: .leading, spacing: 9) {
            Label("Проверка восстановления · \(restore.status)", systemImage: "checkmark.shield").font(.headline)
            Text("Сохранённые метаданные проверяются после перезапуска. Это не восстановленная полная квитанция исходной операции.")
                .font(.caption).foregroundStyle(.secondary)
            line("Evidence SHA-256", restore.evidenceHash)
            Text(restore.processReceiptStatus == "NOT_AVAILABLE" ? "Квитанция операции в текущем процессе недоступна. Она не выдумывается по метаданным." : "Квитанция текущего процесса: \(restore.processReceiptStatus)")
                .font(.callout).foregroundStyle(.secondary)
        }.inspectionCard()
    }

    private func sources(_ report: NativeSkillInspection) -> some View {
        DisclosureGroup("Источники, проверки и ограничения") {
            VStack(alignment: .leading, spacing: 12) {
                ForEach(report.storeHashes.keys.sorted(), id: \.self) { key in line(key, report.storeHashes[key] ?? "") }
                if let lifecycle = report.lifecycle {
                    line("Lifecycle", lifecycle.state.rawValue)
                    line("Provenance", lifecycle.provenanceId.isEmpty ? "Недоступно" : lifecycle.provenanceId)
                }
                if let outcome = report.outcome {
                    line("Outcome", outcome.status)
                    ForEach(outcome.checks.keys.sorted(), id: \.self) { key in
                        Text("\(outcome.checks[key] == true ? "OK" : "NOT MET") · \(key)").font(.caption.monospaced())
                    }
                }
                ForEach(Array(report.issues.enumerated()), id: \.offset) { _, text in Text(text).font(.caption).foregroundStyle(.red) }
                ForEach(Array(report.warnings.enumerated()), id: \.offset) { _, text in Text(text).font(.caption).foregroundStyle(.orange) }
            }.padding(.top, 12)
        }.inspectionCard()
    }

    private func metric(_ title: String, _ value: Int) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text("\(value)").font(.title3.monospacedDigit().weight(.medium))
            Text(title).font(.caption).foregroundStyle(.secondary)
        }.frame(maxWidth: .infinity, alignment: .leading)
    }
    private func line(_ title: String, _ value: String) -> some View {
        VStack(alignment: .leading, spacing: 3) {
            Text(title).font(.caption).foregroundStyle(.secondary)
            Text(value).font(.system(size: 11, design: .monospaced)).fixedSize(horizontal: false, vertical: true)
        }
    }
}

private extension View {
    func inspectionCard() -> some View {
        padding(16).frame(maxWidth: .infinity, alignment: .leading)
            .background(Color.primary.opacity(0.04), in: RoundedRectangle(cornerRadius: 12))
    }
}
