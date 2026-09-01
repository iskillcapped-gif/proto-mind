import SwiftUI

struct MemoryWorkshopView: View {
    @ObservedObject var model: AppModel

    var body: some View {
        VStack(spacing: 0) {
            HStack(spacing: 12) {
                Image(systemName: "sparkles.rectangle.stack").font(.title2)
                VStack(alignment: .leading, spacing: 3) {
                    Text("Memory Workshop").font(.title2.weight(.semibold))
                    Text("Наблюдаемый опыт → кандидат → ручное решение")
                        .font(.caption).foregroundStyle(.secondary)
                }
                Spacer()
                Button { Task { await model.refreshMemoryWorkshop() } } label: { Image(systemName: "arrow.clockwise") }
                    .disabled(model.busy || model.loadingMemoryWorkshop)
                Button { model.showMemoryWorkshop = false } label: { Image(systemName: "xmark") }
                    .keyboardShortcut(.cancelAction)
            }.padding(22)
            Divider()

            if model.loadingMemoryWorkshop && model.memoryWorkshop == nil {
                VStack(spacing: 12) {
                    ProgressView()
                    Text("Читаем только текущее process-memory состояние")
                        .font(.caption).foregroundStyle(.secondary)
                }.frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if let error = model.memoryWorkshopError {
                empty("Workshop недоступен", error, icon: "exclamationmark.triangle")
            } else if let report = model.memoryWorkshop {
                reportView(report)
            } else {
                empty("Нет отчёта", "Обновите Workshop. Это не создаст pilot или consent.", icon: "tray")
            }
        }
        .frame(minWidth: 760, idealWidth: 860, minHeight: 580, idealHeight: 700)
        .task { if model.memoryWorkshop == nil { await model.refreshMemoryWorkshop() } }
    }

    private func reportView(_ report: NativeMemoryWorkshop) -> some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                HStack(spacing: 12) {
                    stat("Состояние", report.status)
                    stat("Эпизоды", "\(report.episodeCount)")
                    stat("Кандидаты", "\(report.candidateCount)")
                    stat("Pilot", report.pilotState)
                }

                VStack(alignment: .leading, spacing: 9) {
                    Label("Граница доверия", systemImage: "lock.shield").font(.headline)
                    Text(report.notice).foregroundStyle(.secondary)
                    Label("Никакого автоматического promotion/apply", systemImage: "hand.raised")
                        .font(.callout.weight(.medium))
                    Text("Нет model/network call, retrieval, command execution, consent change или store write.")
                        .font(.caption).foregroundStyle(.secondary)
                }.card()

                VStack(alignment: .leading, spacing: 9) {
                    Label("Область памяти", systemImage: "folder.badge.questionmark").font(.headline)
                    Text(report.scope.explanation).foregroundStyle(.secondary)
                    if report.scope.workspaceSelected {
                        value("Текущая рабочая папка", report.scope.workspacePath)
                        value("Workspace identity", report.scope.workspaceIdentityHash)
                    } else {
                        Text("Рабочая папка не выбрана для этого диалога.").font(.callout).foregroundStyle(.secondary)
                    }
                    Label("Project isolation: пока не обеспечена", systemImage: "exclamationmark.triangle")
                        .font(.callout.weight(.medium)).foregroundStyle(.orange)
                }.card()

                if report.candidates.isEmpty {
                    VStack(alignment: .leading, spacing: 11) {
                        Text(report.pilotPresent ? "Кандидатов пока нет" : "Supervised capture ещё не запускался")
                            .font(.headline)
                        Text(report.pilotPresent
                             ? "Чистый turn не превращается в урок автоматически. Кандидаты появляются только из correction/reflection/grounding evidence."
                             : "Сначала можно вручную запросить одноразовую consent-фразу. Workshop сам её не создаёт и ничего не включает.")
                            .foregroundStyle(.secondary)
                        Button("Подготовить /experience preview") {
                            model.prepareMemoryWorkshopCommand(report.commands.startPreview)
                        }.buttonStyle(.borderedProminent).nativeHoverSurface()
                    }.card()
                } else {
                    Text("КАНДИДАТЫ ДЛЯ РУЧНОГО REVIEW").font(.caption.weight(.semibold)).foregroundStyle(.secondary)
                    ForEach(report.candidates) { candidate in candidateCard(candidate) }
                }

                if !report.issues.isEmpty || !report.warnings.isEmpty {
                    VStack(alignment: .leading, spacing: 7) {
                        Label("Диагностика", systemImage: "stethoscope").font(.headline)
                        ForEach(Array((report.issues + report.warnings).enumerated()), id: \.offset) { _, finding in
                            Text(finding).font(.caption).foregroundStyle(report.issues.isEmpty ? .orange : .red)
                        }
                    }.card()
                }

                HStack {
                    Button("Подготовить status") { model.prepareMemoryWorkshopCommand(report.commands.status) }
                    Button("Подготовить learning doctor") { model.prepareMemoryWorkshopCommand(report.commands.learningDoctor) }
                    Spacer()
                    Text("Команда только помещается в поле ввода.").font(.caption).foregroundStyle(.tertiary)
                }
            }.padding(22)
        }
    }

    private func candidateCard(_ candidate: NativeMemoryWorkshopCandidate) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Text(candidate.reviewStatus).font(.caption.weight(.semibold)).foregroundStyle(.orange)
                Spacer()
                Text(candidate.decision).font(.caption).foregroundStyle(.secondary)
            }
            Text(candidate.text).font(.body).textSelection(.enabled)
            Text(candidate.rationale).font(.callout).foregroundStyle(.secondary)
            value("Candidate ID", candidate.id)
            value("Evidence", candidate.evidenceEventIds.joined(separator: " · "))
            value("Sources", candidate.sourceKinds.joined(separator: " · "))
            HStack {
                Button("Подготовить evidence preview") {
                    model.prepareMemoryWorkshopCommand(candidate.previewCommand)
                }
                Button("Подготовить decision review") {
                    model.prepareMemoryWorkshopCommand(candidate.reviewCommand)
                }
                Spacer()
                Text("promotion_ready: false").font(.caption).foregroundStyle(.tertiary)
            }
        }.card()
    }

    private func stat(_ label: String, _ value: String) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(label).font(.caption).foregroundStyle(.secondary)
            Text(value).font(.system(size: 14, weight: .semibold, design: .rounded)).lineLimit(1)
        }.padding(12).frame(maxWidth: .infinity, alignment: .leading)
            .background(Color.primary.opacity(0.035), in: RoundedRectangle(cornerRadius: 10))
    }

    private func value(_ label: String, _ value: String) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(label).font(.caption).foregroundStyle(.secondary)
            Text(value.isEmpty ? "не указано" : value).font(.system(size: 10, design: .monospaced))
                .textSelection(.enabled).frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    private func empty(_ title: String, _ detail: String, icon: String) -> some View {
        VStack(spacing: 12) {
            Image(systemName: icon).font(.system(size: 30, weight: .light)).foregroundStyle(.secondary)
            Text(title).font(.title3.weight(.medium))
            Text(detail).foregroundStyle(.secondary).multilineTextAlignment(.center).textSelection(.enabled)
        }.padding(30).frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}

private extension View {
    func card() -> some View {
        padding(15).frame(maxWidth: .infinity, alignment: .leading)
            .background(Color.primary.opacity(0.035), in: RoundedRectangle(cornerRadius: 12))
    }
}
