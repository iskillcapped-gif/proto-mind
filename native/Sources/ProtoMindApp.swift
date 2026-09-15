import AppKit
import SwiftUI

@MainActor
final class NativeAppDelegate: NSObject, NSApplicationDelegate {
    weak var model: AppModel?

    func applicationShouldTerminate(_ sender: NSApplication) -> NSApplication.TerminateReply {
        if model?.globalBusy == true {
            let alert = NSAlert()
            alert.messageText = "Запрос ещё выполняется"
            alert.informativeText = "Дождитесь завершения или нажмите «Стоп» для Codex. Приложение не будет прерывать запись локального ядра."
            alert.addButton(withTitle: "Вернуться в Proto-Mind")
            alert.runModal()
            return .terminateCancel
        }
        if model?.saveBeforeExit() == false {
            let alert = NSAlert()
            alert.alertStyle = .warning
            alert.messageText = "Есть несохранённые сообщения или черновики"
            alert.informativeText = "Сохранение истории не удалось. Вернитесь в приложение, чтобы сохранить или скопировать нужный текст. При выходе несохранённые изменения будут потеряны."
            alert.addButton(withTitle: "Вернуться в Proto-Mind")
            alert.addButton(withTitle: "Выйти без сохранения")
            guard alert.runModal() == .alertSecondButtonReturn else { return .terminateCancel }
        }
        model?.shutdown()
        return .terminateNow
    }

    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool {
        !(model?.desktop.reopen() ?? false)
    }

    func applicationDidBecomeActive(_ notification: Notification) {
        guard let model, model.loginPending else { return }
        Task { await model.refreshAccount() }
    }
}

@main
struct ProtoMindApp: App {
    @NSApplicationDelegateAdaptor(NativeAppDelegate.self) private var delegate
    @StateObject private var model = AppModel()

    var body: some Scene {
        WindowGroup("Proto-Mind") {
            WorkspaceView(model: model)
                .task {
                    delegate.model = model
                    await model.start()
                }
        }
        .defaultSize(width: 1320, height: 860)
        .windowStyle(.hiddenTitleBar)
        .windowToolbarStyle(.unifiedCompact)
        .commands {
            CommandGroup(replacing: .newItem) {
                Button("Новый диалог") { model.newConversation() }
                    .keyboardShortcut("n").disabled(!model.canNavigateConversations)
            }
            CommandMenu("Proto-Mind") {
                Button("Переключить парящий режим") { model.desktop.toggleMode() }
                    .keyboardShortcut("j", modifiers: [.command, .option])
                Divider()
                Button("Использование Codex…") { model.showCodexUsage = true }
                Button("Полная копия данных…") { model.showPrivateBackup = true }
                    .disabled(model.globalBusy || model.client.turnOutstanding)
                Button("Копии диалогов…") { model.openHistoryBackups() }
                    .disabled(model.globalBusy || model.client.turnOutstanding)
                Button("Каталог команд") { model.section = .commands }
                    .keyboardShortcut("k")
                Button("Файлы проекта") { model.showProjectFiles() }
                    .keyboardShortcut("o", modifiers: [.command, .shift])
                Button("Новая страница в панели") { model.workspacePanel.openBrowser() }
                    .keyboardShortcut("t", modifiers: [.command, .option])
                Button("Инспектор ответа") { model.showInspector.toggle() }
                    .keyboardShortcut("i", modifiers: [.command, .option])
                Button("Обновить обзор") { Task { await model.refresh() } }
                    .disabled(model.busy)
            }
        }
        Settings {
            NativeSettingsView(model: model).frame(width: 800, height: 680)
        }
    }
}
