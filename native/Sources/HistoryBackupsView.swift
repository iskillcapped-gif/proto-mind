import SwiftUI

struct HistoryBackupsView: View {
    @ObservedObject var model: AppModel
    @State private var confirmRestore = false

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack {
                Text(L10n.text("Копии и восстановление диалогов")).font(.title3.weight(.semibold))
                Spacer()
                Button { model.showHistoryBackups = false } label: { Image(systemName: "xmark") }.keyboardShortcut(.cancelAction)
            }
            Text(L10n.text("В копию входят сообщения, черновики и настройки диалогов. Память, отдельный журнал запусков и исходные файлы вложений хранятся отдельно."))
                .font(.callout).foregroundStyle(.secondary)
            HStack {
                Button(L10n.text("Сохранить копию…")) { model.chooseHistoryExport() }
                Button(L10n.text("Выбрать копию…")) { model.chooseHistoryBackup() }
                if model.store.conflictDetected {
                    Button(L10n.text("Открыть актуальную историю")) { model.reloadCurrentHistory() }
                }
            }.buttonStyle(.bordered).disabled(model.busy || model.client.turnOutstanding)
            if let error = model.historyBackupError {
                Label(error, systemImage: "exclamationmark.triangle").foregroundStyle(.orange).textSelection(.enabled)
            }
            if let notice = model.historyBackupNotice {
                Label(notice, systemImage: "checkmark.circle").foregroundStyle(.secondary).textSelection(.enabled)
            }
            if let preview = model.historyBackupPreview {
                VStack(alignment: .leading, spacing: 10) {
                    Label(L10n.text("Копия проверена"), systemImage: "checkmark.shield").font(.headline)
                    Text(L10n.format("Диалогов: \(preview.archive.conversations.count) · сообщений: \(preview.messageCount)"))
                    Text(preview.source.lastPathComponent).font(.caption).foregroundStyle(.secondary).lineLimit(2)
                    Text(L10n.text("Восстановление заменит список диалогов этой копией. Текущее состояние, включая несохранённые сообщения, сначала сохранится отдельно. Облачные сессии модели не откатываются и могут помнить более поздние сообщения."))
                        .font(.callout)
                    Button(L10n.text("Восстановить диалоги…")) { confirmRestore = true }.buttonStyle(.borderedProminent)
                        .disabled(model.busy || model.client.turnOutstanding)
                }.padding(16).frame(maxWidth: .infinity, alignment: .leading).background(.quaternary, in: RoundedRectangle(cornerRadius: 12))
            }
            Text(L10n.text("Локальные снимки")).font(.headline)
            Text(L10n.text("Последние 20 состояний сохраняются автоматически. Копии перед переходом формата и восстановлением хранятся дополнительно. Для защиты от потери диска сохраняйте копию в другом месте."))
                .font(.caption).foregroundStyle(.secondary)
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 8) {
                    if model.historyBackupItems.isEmpty { Text(L10n.text("Локальных снимков пока нет.")).foregroundStyle(.secondary) }
                    ForEach(model.historyBackupItems) { item in
                        Button { model.inspectHistoryBackup(item.url) } label: {
                            HStack {
                                Image(systemName: "clock.arrow.circlepath")
                                Text(item.date.formatted(date: .abbreviated, time: .standard))
                                Spacer()
                                Text(item.url.lastPathComponent.hasPrefix("legacy-") ? L10n.text("До обновления") : item.url.lastPathComponent.hasPrefix("recovery-") ? L10n.text("До восстановления") : L10n.text("Автоматически"))
                                    .font(.caption).foregroundStyle(.secondary)
                            }.padding(10).contentShape(Rectangle())
                        }.buttonStyle(.plain).disabled(model.busy || model.client.turnOutstanding)
                    }
                }
            }
        }.padding(24).workspacePageSize(width: 690, height: 640)
            .workspaceConfirmationDialog(L10n.text("Восстановить выбранную историю?"), isPresented: $confirmRestore, titleVisibility: .visible) {
                Button(L10n.text("Восстановить диалоги")) { confirmRestore = false; if let preview = model.historyBackupPreview { model.restoreHistoryBackup(preview) } }
                Button(L10n.text("Отмена"), role: .cancel) { confirmRestore = false }
            } message: {
                Text(L10n.text("Текущая история будет заменена после сохранения её копии. Запросы к модели не выполняются."))
            }
    }
}
