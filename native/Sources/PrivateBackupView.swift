import SwiftUI

struct PrivateBackupView: View {
    @ObservedObject var app: AppModel
    @ObservedObject var backup: PrivateBackupModel
    @State private var action: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack {
                Text(L10n.text("Полная копия данных")).font(.system(size: 22, weight: .semibold))
                Spacer()
                if backup.working { ProgressView().controlSize(.small) }
                Button { app.showPrivateBackup = false } label: { Image(systemName: "xmark") }
                    .disabled(backup.working || backup.pending || backup.restartRequired).keyboardShortcut(.cancelAction)
            }
            ScrollView {
                VStack(alignment: .leading, spacing: 20) {
                    Text(L10n.text("Диалоги и черновики, ядро памяти, заметки проектов, журнал работы, история обучения, локальные экспорты и настройки — в одной проверяемой копии."))
                    Text(L10n.text("Входы и ключи сервисов, история провайдеров, исходные вложения и файлы рабочих проектов хранятся отдельно. Копия содержит личные данные; для защиты от потери диска сохраняйте её в другом месте."))
                        .foregroundStyle(.secondary).font(.callout)
                    if backup.restartRequired {
                        VStack(alignment: .leading, spacing: 12) {
                            Label(backup.result["direction"].text == "rollback" ? L10n.text("Прежние данные возвращены") : L10n.text("Данные восстановлены"), systemImage: "checkmark.circle").font(.headline)
                            Text(L10n.text("Перезапустите Proto-Mind, чтобы открыть восстановленные данные. Облачный доступ и подключения нужно включить заново; новые запросы начнут новые сессии модели."))
                            Button(L10n.text("Закрыть Proto-Mind")) {
                                app.quitAfterPrivateBackup = true
                                app.showPrivateBackup = false
                            }.buttonStyle(.borderedProminent)
                            showPath(L10n.text("Копия прежнего состояния"), path: backup.result["recovery_path"].text)
                            showPath(L10n.text("Сообщения из окна до восстановления"), path: backup.result["window_path"].text)
                        }.padding(16).background(.quaternary, in: RoundedRectangle(cornerRadius: 12))
                    } else if backup.pending {
                        VStack(alignment: .leading, spacing: 12) {
                            Label(L10n.text("Восстановление не завершено"), systemImage: "pause.circle").font(.headline)
                            Text(L10n.text("Запись обычных данных приостановлена. Можно закончить начатое восстановление или вернуть сохранённое прежнее состояние. Автоматического повтора не было."))
                            HStack {
                                Button(L10n.text("Продолжить восстановление…")) { action = "resume" }
                                Button(L10n.text("Вернуть прежние данные…")) { action = "rollback" }
                            }.buttonStyle(.bordered).disabled(backup.working || backup.status["id"].text.isEmpty)
                            showPath(L10n.text("Копия прежнего состояния"), path: backup.status["recovery_path"].text)
                        }.padding(16).background(Color.orange.opacity(0.08), in: RoundedRectangle(cornerRadius: 12))
                    } else {
                        HStack {
                            Button(L10n.text("Сохранить полную копию…")) { backup.chooseExport(app: app) }.buttonStyle(.borderedProminent)
                            Button(L10n.text("Выбрать копию…")) { backup.chooseSource(app: app) }.buttonStyle(.bordered)
                        }.disabled(backup.working || app.globalBusy || app.client.turnOutstanding)
                    }
                    if let error = backup.error { Text(error).foregroundStyle(.orange).textSelection(.enabled) }
                    if let notice = backup.notice {
                        Label(notice, systemImage: "checkmark.shield").foregroundStyle(.secondary)
                        showPath(L10n.text("Показать копию"), path: backup.result["path"].text)
                    }
                    if !backup.preview.isNull && !backup.pending {
                        VStack(alignment: .leading, spacing: 12) {
                            Label(L10n.text("Копия проверена"), systemImage: "checkmark.shield").font(.headline)
                            Text(L10n.format("Диалогов: \(backup.conversations) · сообщений: \(backup.messages)"))
                            Text(L10n.format("\(backup.preview["files"].integer) файлов · \(ByteCountFormatter.string(fromByteCount: Int64(backup.preview["bytes"].integer), countStyle: .file))"))
                            Text(URL(fileURLWithPath: backup.preview["path"].text).lastPathComponent).foregroundStyle(.secondary).lineLimit(2)
                            Text(L10n.text("Текущие данные и текст из окна сначала сохранятся отдельно. Восстановление заменит перечисленные локальные данные, сохраняя их исходные связи с папками. Облачный доступ, подключение GitHub и привязки активных сессий будут сброшены.")).font(.callout)
                            if !backup.preview["same_scope"].flag {
                                Text(L10n.text("Эта копия сделана для других путей установки. Автоматический перенос связей между установками пока не поддерживается.")).foregroundStyle(.secondary).font(.callout)
                            }
                            Button(L10n.text("Восстановить данные…")) { action = "restore" }.buttonStyle(.borderedProminent)
                                .disabled(backup.working || !backup.preview["same_scope"].flag)
                        }.padding(16).background(.quaternary, in: RoundedRectangle(cornerRadius: 12))
                    }
                    if !backup.status["copies"].items.isEmpty && !backup.pending && !backup.restartRequired {
                        VStack(alignment: .leading, spacing: 10) {
                            Text(L10n.text("Сохранённые локальные копии")).font(.headline)
                            ForEach(Array(backup.status["copies"].items.enumerated()), id: \.offset) { _, item in
                                Button { Task { await backup.inspect(URL(fileURLWithPath: item["path"].text), app: app) } } label: {
                                    Label(item["name"].text, systemImage: "externaldrive").lineLimit(2)
                                }.disabled(backup.working)
                            }
                        }
                    }
                }.frame(maxWidth: .infinity, alignment: .leading)
            }
        }.padding(24).workspacePageSize(width: 730, height: 630)
            .task { await backup.refresh(app: app) }
            .workspaceDismissDisabled(backup.working || backup.restartRequired)
            .workspaceConfirmationDialog(action == "rollback" ? L10n.text("Вернуть прежние данные?") : L10n.text("Восстановить данные из копии?"), isPresented: Binding(get: { action != nil }, set: { if !$0 { action = nil } }), titleVisibility: .visible) {
                Button(action == "rollback" ? L10n.text("Вернуть прежние данные") : L10n.text("Восстановить данные"), role: .destructive) {
                    let selected = action; action = nil
                    Task {
                        if selected == "restore" { await backup.restore(app: app) }
                        else { await backup.resume(app: app, rollback: selected == "rollback") }
                    }
                }
                Button(L10n.text("Отмена"), role: .cancel) { action = nil }
            } message: {
                Text(L10n.text("Текущее состояние останется в отдельной копии. После завершения потребуется перезапуск и повторное включение доступа к сервисам."))
            }
    }

    @ViewBuilder private func showPath(_ label: String, path: String) -> some View {
        if !path.isEmpty { Button(label) { NSWorkspace.shared.activateFileViewerSelecting([URL(fileURLWithPath: path)]) }.font(.callout) }
    }
}
