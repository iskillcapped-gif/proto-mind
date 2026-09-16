import SwiftUI

struct SkillLifecycleApplyView: View {
    @ObservedObject var model: SkillLifecycleApplyModel
    @State private var token = ""
    @State private var acknowledgement = false

    private var archive: Bool { model.selection.decision == .archive }
    var body: some View {
        VStack(spacing: 0) {
            HStack(spacing: 12) {
                Image(systemName: "checkmark.shield").font(.title2)
                VStack(alignment: .leading, spacing: 4) {
                    Text(L10n.text("Применение решения по навыку")).font(.title2.weight(.semibold))
                    Text(L10n.text("Отдельное подтверждение. Никакого запуска процедуры.")).font(.caption).foregroundStyle(.secondary)
                }
                Spacer()
                if model.loading || model.committing { ProgressView().controlSize(.small) }
                Button { Task { await model.refresh() } } label: { Image(systemName: "arrow.clockwise") }
                    .disabled(model.locked).help(L10n.text("Обновить источники; сбросить старое подтверждение"))
                Button { model.close() } label: { Image(systemName: "xmark") }
                    .disabled(model.committing).keyboardShortcut(.cancelAction)
            }.padding(22)
            Divider()
            ScrollViewReader { scroll in
                ScrollView {
                    VStack(alignment: .leading, spacing: 18) {
                        if let error = model.error {
                            Label(error, systemImage: "exclamationmark.triangle").font(.callout).foregroundStyle(.orange).textSelection(.enabled).lifecycleCard()
                        }
                        if let report = model.report {
                            overview(report)
                            if let receipt = report.receipt { receiptCard(receipt) }
                            else {
                                Button(archive ? L10n.text("Проверить точное архивирование…") : L10n.text("Проверить сохранение без изменений…")) { Task { await model.prepare() } }
                                    .buttonStyle(.bordered).nativeHoverSurface().disabled(!model.canPrepare)
                            }
                            if let preview = model.preview { confirmation(preview).id("lifecycle-confirmation") }
                            DisclosureGroup(L10n.text("Проверки, точные источники и ограничения")) {
                                VStack(alignment: .leading, spacing: 8) {
                                    detail("Skill ID", model.selection.scope.skillID)
                                    detail(L10n.text("Решение"), model.selection.decisionReceiptID)
                                    ForEach(report.storeHashes.keys.sorted(), id: \.self) { key in detail(key, report.storeHashes[key] ?? "") }
                                    ForEach(report.checks.keys.sorted(), id: \.self) { key in
                                        Label(key, systemImage: report.checks[key] == true ? "checkmark.circle" : "exclamationmark.circle").font(.caption).textSelection(.enabled)
                                    }
                                    ForEach(Array((report.issues + report.reasons + report.warnings).enumerated()), id: \.offset) { _, reason in
                                        Text(reason).font(.caption).foregroundStyle(.secondary).textSelection(.enabled)
                                    }
                                    Text(L10n.text("Одна попытка применения в текущем ядре. После потери ответа или ошибки автоматического повтора нет. Подробная квитанция исчезнет при перезапуске; причина архивирования останется в записи навыка."))
                                        .font(.caption).foregroundStyle(.secondary)
                                    Text(L10n.text("Запись заменяется атомарно. При неуспешной проверке откат допустим только поверх собственных неизменённых байтов; сторонние изменения не затираются. Это не блокировка всех внешних процессов."))
                                        .font(.caption).foregroundStyle(.secondary)
                                }.padding(.top, 10)
                            }.lifecycleCard()
                        } else if model.loading { Text(L10n.text("Проверяю текущее решение и источники…")).foregroundStyle(.secondary) }
                    }.padding(22)
                }.onChange(of: model.preview?.previewFingerprint) { _, value in
                    token = ""; acknowledgement = false
                    if value != nil { scroll.scrollTo("lifecycle-confirmation", anchor: .top) }
                }
            }
        }.workspacePageSize(width: 850, height: 720).buttonStyle(.nativeHover).workspaceDismissDisabled(model.committing)
    }

    private func overview(_ report: NativeSkillLifecycleApplyReview) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Text(report.name.isEmpty ? L10n.text("Навык недоступен") : report.name).font(.title3.weight(.semibold))
                Spacer()
                Text(report.status).font(.caption.weight(.semibold)).foregroundStyle(report.status == "ERROR" ? .red : .secondary)
            }
            Text(L10n.format("Решение: \(model.selection.decision.title). Сохранённый статус: \(report.storedSkillStatus).")).font(.callout)
            if report.receipt != nil {
                Text(L10n.text("Применение уже зафиксировано. Квитанция и текущее состояние показаны ниже; повторный просмотр ничего не применяет."))
                    .font(.callout).foregroundStyle(.secondary)
            } else {
                Text(archive ? L10n.text("После отдельного подтверждения статус станет archived, а причина и связь с доказательствами сохранятся в навыке. Текст процедуры, uses и происхождение не меняются.")
                             : L10n.text("Keep проверит неизменность навыка и запишет квитанцию только в памяти процесса. Revise пока не имеет механизма применения."))
                    .font(.callout).foregroundStyle(.secondary)
            }
            Label(L10n.text("Библиотека навыков общая для проектов. Изменение этой записи относится ко всем проектам."), systemImage: "externaldrive")
                .font(.callout).foregroundStyle(.orange)
            if !report.canApply && report.receipt == nil {
                Text(model.selection.decision == .revise ? L10n.text("Доработка требует отдельного описания новой версии; на этом экране она не выполняется.")
                     : L10n.text("Применение сейчас недоступно. Проверьте актуальность решения, источники и лимит попыток ниже.")).font(.callout).foregroundStyle(.orange)
            }
            if !report.contextInjectionDisabled { Text(L10n.text("Отключённый Context Injection не подтверждён. Настройки не меняются автоматически.")).font(.caption).foregroundStyle(.orange) }
            HStack {
                Button(L10n.text("Результаты и источник")) { Task { await model.openEvidence() } }
                Button(L10n.text("Открыть навык")) { Task { await model.openSkill() } }
            }.buttonStyle(.bordered).disabled(model.locked)
        }.lifecycleCard()
    }

    private func confirmation(_ preview: NativeSkillLifecycleApplyPreview) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            Label(L10n.text("Точное применение"), systemImage: preview.ready ? "checkmark.shield" : "hand.raised").font(.headline)
            if preview.ready {
                Text(archive ? L10n.text("active → archived · одна запись") : L10n.text("active → active · ни одного изменения файла")).font(.callout.weight(.semibold))
                Text(archive ? L10n.text("Изменятся только lifecycle, status и updated_at. Новая квитанция описывает реальное изменение, а не рекомендацию.")
                     : L10n.text("Будет подтверждён только keep no-op. Навык не запускается и файл не перезаписывается."))
                    .font(.callout).foregroundStyle(.secondary)
                detail(L10n.text("SHA-256 до применения"), preview.beforeStoreSha256)
                detail(L10n.text("Введите новую точную фразу"), preview.confirmationToken)
                TextField("CONFIRM-…", text: $token).textFieldStyle(.roundedBorder).font(.body.monospaced()).autocorrectionDisabled().disabled(model.locked)
                Toggle(archive ? L10n.text("Подтверждаю архивирование именно этого навыка в общей библиотеке; без запуска процедуры")
                       : L10n.text("Подтверждаю keep без изменений общей библиотеки и без запуска процедуры"), isOn: $acknowledgement)
                    .toggleStyle(.checkbox).disabled(model.locked)
                HStack {
                    Button(archive ? L10n.text("Архивировать этот навык") : L10n.text("Подтвердить keep без изменений")) {
                        Task { await model.confirm(token: token, acknowledgement: acknowledgement) }
                    }.buttonStyle(.borderedProminent).nativeHoverSurface().disabled(model.locked || !preview.accepts(token: token, acknowledgement: acknowledgement))
                    Button(L10n.text("Отмена")) { model.invalidate() }.disabled(model.locked)
                }
            } else {
                Text(L10n.text("Основания изменились или применение запрещено. Ничего не применено.")).font(.callout).foregroundStyle(.orange)
                ForEach(Array(preview.reasons.enumerated()), id: \.offset) { _, reason in Text(reason).font(.caption).textSelection(.enabled) }
            }
        }.lifecycleCard().overlay(RoundedRectangle(cornerRadius: 12).stroke(Color.accentColor.opacity(0.4), lineWidth: 1))
    }

    private func receiptCard(_ receipt: NativeSkillLifecycleApplyReceipt) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Label(receipt.decision == .archive ? L10n.text("Квитанция архивирования") : L10n.text("Квитанция keep без изменений"), systemImage: "doc.text").font(.headline)
            Text("\(receipt.appliedAt) · \(receipt.verificationStatus) · \(receipt.evidenceState)").font(.caption).foregroundStyle(.secondary)
            Text(L10n.format("Изменено записей: \(receipt.actualRecordMutations). Процедура не запускалась.")).font(.callout)
            if receipt.evidenceState != "CURRENT" {
                Text(L10n.text("Текущее состояние отличается или не подтверждено. Квитанция не разрешает повторное применение.")).font(.callout).foregroundStyle(.orange)
            }
            detail("Receipt ID", receipt.id)
            detail("Receipt SHA-256", receipt.receiptHash)
            if !receipt.metadataId.isEmpty { detail(L10n.text("Сохранённая причина перехода"), receipt.metadataId) }
            Text(receipt.decision == .archive ? L10n.text("Причина архивирования переживёт перезапуск. Восстановление требует отдельного существующего gate; этот экран не выполняет restore.")
                 : L10n.text("Файл навыков не изменён. Подробная keep-квитанция доступна только до перезапуска ядра.")).font(.caption).foregroundStyle(.secondary)
            DisclosureGroup(L10n.text("Полная квитанция")) {
                Text(receipt.details).font(.system(size: 11, design: .monospaced)).textSelection(.enabled).fixedSize(horizontal: false, vertical: true)
                ForEach(Array(receipt.warnings.enumerated()), id: \.offset) { _, warning in Text(warning).font(.caption).foregroundStyle(.secondary) }
            }
        }.lifecycleCard()
    }

    private func detail(_ title: String, _ value: String) -> some View {
        VStack(alignment: .leading, spacing: 3) {
            Text(title).font(.caption).foregroundStyle(.secondary)
            Text(value).font(.system(size: 11, design: .monospaced)).textSelection(.enabled).fixedSize(horizontal: false, vertical: true)
        }
    }
}

private extension View {
    func lifecycleCard() -> some View {
        padding(16).frame(maxWidth: .infinity, alignment: .leading).background(Color.primary.opacity(0.035), in: RoundedRectangle(cornerRadius: 12))
    }
}
