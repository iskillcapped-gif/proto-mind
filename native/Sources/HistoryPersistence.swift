import AppKit
import SwiftUI

struct HistoryPersistenceState: Equatable {
    var hasUnsavedChanges = false
    var failure: String?
    var requiresRecovery = false

    var blocksSubmission: Bool { failure != nil || requiresRecovery }
}

struct HistoryPersistenceNotice: View {
    @ObservedObject var model: AppModel

    var body: some View {
        if let failure = model.historyPersistence.failure {
            VStack(alignment: .leading, spacing: 8) {
                Label(model.historyPersistence.requiresRecovery ? L10n.text("История требует восстановления") : L10n.text("История не сохранена"),
                      systemImage: "externaldrive.badge.exclamationmark")
                    .font(.callout.weight(.semibold))
                Text(failure).font(.callout).textSelection(.enabled)
                Text(model.historyPersistence.requiresRecovery
                     ? L10n.text("Исходные файлы защищены от перезаписи. Выберите проверенную резервную копию для восстановления.")
                     : L10n.text("Сообщения и черновики остаются в этом окне. Повторите сохранение перед отправкой следующего запроса."))
                    .font(.caption).foregroundStyle(.secondary)
                HStack {
                    if !model.historyPersistence.requiresRecovery {
                        Button(L10n.text("Повторить сохранение")) { model.retryHistorySave() }
                            .disabled(model.globalBusy || model.client.turnOutstanding)
                    }
                    Button(L10n.text("Копии и восстановление…")) { model.openHistoryBackups() }
                        .disabled(model.globalBusy || model.client.turnOutstanding)
                    Button(L10n.text("Показать файл истории")) {
                        NSWorkspace.shared.activateFileViewerSelecting([model.store.url])
                    }
                }.buttonStyle(.bordered)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(14).background(Color.orange.opacity(0.09))
        }
    }
}
