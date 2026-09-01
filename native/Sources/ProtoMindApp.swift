import AppKit
import SwiftUI

@MainActor
final class NativeAppDelegate: NSObject, NSApplicationDelegate {
    weak var model: AppModel?

    func applicationShouldTerminate(_ sender: NSApplication) -> NSApplication.TerminateReply {
        if model?.busy == true || model?.client.turnOutstanding == true {
            let alert = NSAlert()
            alert.messageText = "Запрос ещё выполняется"
            alert.informativeText = "Дождитесь завершения или нажмите «Стоп» для Codex. Приложение не будет прерывать запись локального ядра."
            alert.addButton(withTitle: "Вернуться в Proto-Mind")
            alert.runModal()
            return .terminateCancel
        }
        model?.flushDraft()
        model?.client.shutdown()
        return .terminateNow
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
                .frame(minWidth: 940, minHeight: 640)
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
                    .keyboardShortcut("n").disabled(model.busy)
            }
            CommandMenu("Proto-Mind") {
                Button("Каталог команд") { model.section = .commands }
                    .keyboardShortcut("k")
                Button("Рабочая папка") { model.section = .workspace; Task { await model.refreshWorkspace() } }
                    .keyboardShortcut("o", modifiers: [.command, .shift])
                Button("Инспектор ответа") { model.showInspector.toggle() }
                    .keyboardShortcut("i", modifiers: [.command, .option])
                Button("Обновить обзор") { Task { await model.refresh() } }
                    .disabled(model.busy)
            }
        }
        Settings {
            NativeSettingsView(model: model).frame(width: 640, height: 650)
        }
    }
}
