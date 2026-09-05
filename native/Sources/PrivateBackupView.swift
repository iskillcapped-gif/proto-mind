import SwiftUI

struct PrivateBackupView: View {
    @ObservedObject var app: AppModel
    @ObservedObject var backup: PrivateBackupModel
    @State private var action: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack {
                Text("Полная копия данных").font(.system(size: 22, weight: .semibold))
                Spacer()
                if backup.working { ProgressView().controlSize(.small) }
                Button { app.showPrivateBackup = false } label: { Image(systemName: "xmark") }
                    .disabled(backup.working || backup.pending || backup.restartRequired).keyboardShortcut(.cancelAction)
            }
            ScrollView {
                VStack(alignment: .leading, spacing: 20) {
                    Text("Диалоги и черновики, ядро памяти, заметки проектов, журнал работы, история обучения, локальные экспорты и настройки — в одной проверяемой копии.")
                    Text("Входы и ключи сервисов, история провайдеров, исходные вложения и файлы рабочих проектов хранятся отдельно. Копия содержит личные данные; для защиты от потери диска сохраняйте её в другом месте.")
                        .foregroundStyle(.secondary).font(.callout)
                    if backup.restartRequired {
                        VStack(alignment: .leading, spacing: 12) {
                            Label(backup.result["direction"].text == "rollback" ? "Прежние данные возвращены" : "Данные восстановлены", systemImage: "checkmark.circle").font(.headline)
                            Text("Перезапустите Proto-Mind, чтобы открыть восстановленные данные. Облачный доступ и подключения нужно включить заново; новые запросы начнут новые сессии модели.")
                            Button("Закрыть Proto-Mind") {
                                app.quitAfterPrivateBackup = true
                                app.showPrivateBackup = false
                            }.buttonStyle(.borderedProminent)
                            showPath("Копия прежнего состояния", path: backup.result["recovery_path"].text)
                            showPath("Сообщения из окна до восстановления", path: backup.result["window_path"].text)
                        }.padding(16).background(.quaternary, in: RoundedRectangle(cornerRadius: 12))
                    } else if backup.pending {
                        VStack(alignment: .leading, spacing: 12) {
                            Label("Восстановление не завершено", systemImage: "pause.circle").font(.headline)
                            Text("Запись обычных данных приостановлена. Можно закончить начатое восстановление или вернуть сохранённое прежнее состояние. Автоматического повтора не было.")
                            HStack {
                                Button("Продолжить восстановление…") { action = "resume" }
                                Button("Вернуть прежние данные…") { action = "rollback" }
                            }.buttonStyle(.bordered).disabled(backup.working || backup.status["id"].text.isEmpty)
                            showPath("Копия прежнего состояния", path: backup.status["recovery_path"].text)
                        }.padding(16).background(Color.orange.opacity(0.08), in: RoundedRectangle(cornerRadius: 12))
                    } else {
                        HStack {
                            Button("Сохранить полную копию…") { backup.chooseExport(app: app) }.buttonStyle(.borderedProminent)
                            Button("Выбрать копию…") { backup.chooseSource(app: app) }.buttonStyle(.bordered)
                        }.disabled(backup.working || app.busy || app.client.turnOutstanding)
                    }
                    if let error = backup.error { Text(error).foregroundStyle(.orange).textSelection(.enabled) }
                    if let notice = backup.notice {
                        Label(notice, systemImage: "checkmark.shield").foregroundStyle(.secondary)
                        showPath("Показать копию", path: backup.result["path"].text)
                    }
                    if !backup.preview.isNull && !backup.pending {
                        VStack(alignment: .leading, spacing: 12) {
                            Label("Копия проверена", systemImage: "checkmark.shield").font(.headline)
                            Text("Диалогов: \(backup.conversations) · сообщений: \(backup.messages)")
                            Text("\(backup.preview["files"].integer) файлов · \(ByteCountFormatter.string(fromByteCount: Int64(backup.preview["bytes"].integer), countStyle: .file))")
                            Text(URL(fileURLWithPath: backup.preview["path"].text).lastPathComponent).foregroundStyle(.secondary).lineLimit(2)
                            Text("Текущие данные и текст из окна сначала сохранятся отдельно. Восстановление заменит перечисленные локальные данные, сохраняя их исходные связи с папками. Облачный доступ, подключение GitHub и привязки активных сессий будут сброшены.").font(.callout)
                            if !backup.preview["same_scope"].flag {
                                Text("Эта копия сделана для других путей установки. Автоматический перенос связей между установками пока не поддерживается.").foregroundStyle(.secondary).font(.callout)
                            }
                            Button("Восстановить данные…") { action = "restore" }.buttonStyle(.borderedProminent)
                                .disabled(backup.working || !backup.preview["same_scope"].flag)
                        }.padding(16).background(.quaternary, in: RoundedRectangle(cornerRadius: 12))
                    }
                    if !backup.status["copies"].items.isEmpty && !backup.pending && !backup.restartRequired {
                        VStack(alignment: .leading, spacing: 10) {
                            Text("Сохранённые локальные копии").font(.headline)
                            ForEach(Array(backup.status["copies"].items.enumerated()), id: \.offset) { _, item in
                                Button { Task { await backup.inspect(URL(fileURLWithPath: item["path"].text), app: app) } } label: {
                                    Label(item["name"].text, systemImage: "externaldrive").lineLimit(2)
                                }.disabled(backup.working)
                            }
                        }
                    }
                }.frame(maxWidth: .infinity, alignment: .leading)
            }
        }.padding(24).frame(width: 730, height: 630)
            .task { await backup.refresh(app: app) }
            .interactiveDismissDisabled(backup.working)
            .confirmationDialog(action == "rollback" ? "Вернуть прежние данные?" : "Восстановить данные из копии?", isPresented: Binding(get: { action != nil }, set: { if !$0 { action = nil } }), titleVisibility: .visible) {
                Button(action == "rollback" ? "Вернуть прежние данные" : "Восстановить данные", role: .destructive) {
                    let selected = action; action = nil
                    Task {
                        if selected == "restore" { await backup.restore(app: app) }
                        else { await backup.resume(app: app, rollback: selected == "rollback") }
                    }
                }
                Button("Отмена", role: .cancel) { action = nil }
            } message: {
                Text("Текущее состояние останется в отдельной копии. После завершения потребуется перезапуск и повторное включение доступа к сервисам.")
            }
    }

    @ViewBuilder private func showPath(_ label: String, path: String) -> some View {
        if !path.isEmpty { Button(label) { NSWorkspace.shared.activateFileViewerSelecting([URL(fileURLWithPath: path)]) }.font(.callout) }
    }
}
