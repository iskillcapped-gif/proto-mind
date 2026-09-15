import AppKit
import SwiftUI

enum WorkspaceExitPrompt: String, Identifiable {
    case busy, unsaved
    var id: String { rawValue }
}

extension AppModel {
    func canTerminateWorkspace() -> Bool {
        // Do not interrupt a shared persistence operation, including after an earlier failed exit.
        guard !globalBusy else { exitPrompt = .busy; discardUnsavedOnExit = false; return false }
        if discardUnsavedOnExit { discardUnsavedOnExit = false; return true }
        guard saveBeforeExit() else { exitPrompt = .unsaved; return false }
        return true
    }
}

struct WorkspaceExitView: View {
    @ObservedObject var app: AppModel
    let prompt: WorkspaceExitPrompt

    var body: some View {
        VStack(alignment: .leading, spacing: 22) {
            Text(prompt == .busy ? "Запрос ещё выполняется" : "Есть несохранённые сообщения или черновики")
                .font(.title2.weight(.semibold))
            Text(prompt == .busy
                 ? "Дождитесь завершения или нажмите «Стоп» для Codex. Приложение не будет прерывать запись локального ядра."
                 : "Сохранение истории не удалось. Вернитесь в приложение, чтобы сохранить или скопировать нужный текст. При выходе несохранённые изменения будут потеряны.")
                .foregroundStyle(.secondary)
            HStack(spacing: 12) {
                Button("Вернуться в Proto-Mind") { app.exitPrompt = nil }.keyboardShortcut(.cancelAction)
                if prompt == .unsaved {
                    Button("Выйти без сохранения", role: .destructive) {
                        app.exitPrompt = nil
                        app.discardUnsavedOnExit = true
                        NSApp.terminate(nil)
                    }
                }
            }.buttonStyle(.bordered).controlSize(.large)
        }.padding(26).workspacePageSize(width: 580)
    }
}
