import AppKit
import SwiftUI

@MainActor
final class NativeAppDelegate: NSObject, NSApplicationDelegate {
    weak var model: AppModel?

    func applicationShouldTerminate(_ sender: NSApplication) -> NSApplication.TerminateReply {
        guard model?.canTerminateWorkspace() != false else { return .terminateCancel }
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
    @StateObject private var model: AppModel

    init() {
        let configuration = LaunchConfiguration.load()
        L10n.language = InterfaceLanguage.saved(configuration)
        _model = StateObject(wrappedValue: AppModel(configuration: configuration))
    }

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
            CommandGroup(replacing: .appSettings) {
                Button(L10n.text("Настройки…")) { model.openSettings() }.keyboardShortcut(",")
            }
            CommandGroup(replacing: .newItem) {
                Button(L10n.text("Новый диалог")) { model.newConversation() }
                    .keyboardShortcut("n").disabled(!model.canNavigateConversations)
            }
            CommandMenu("Proto-Mind") {
                DesktopWindowCommands(desktop: model.desktop)
                Divider()
                Button(L10n.text("Использование Codex…")) { model.showCodexUsage = true }
                Button(L10n.text("Полная копия данных…")) { model.showPrivateBackup = true }
                    .disabled(model.globalBusy || model.client.turnOutstanding)
                Button(L10n.text("Копии диалогов…")) { model.openHistoryBackups() }
                    .disabled(model.globalBusy || model.client.turnOutstanding)
                Button(L10n.text("Каталог команд")) { model.section = .commands }
                    .keyboardShortcut("k")
                Button(L10n.text("Файлы проекта")) { model.showProjectFiles() }
                    .keyboardShortcut("o", modifiers: [.command, .shift])
                Button(L10n.text("Новая страница в панели")) { model.workspacePanel.openBrowser() }
                    .keyboardShortcut("t", modifiers: [.command, .option])
                Button(L10n.text("Инспектор ответа")) { model.showInspector.toggle() }
                    .keyboardShortcut("i", modifiers: [.command, .option])
                Button(L10n.text("Обновить обзор")) { Task { await model.refresh() } }
                    .disabled(model.busy)
            }
        }
    }
}

private struct DesktopWindowCommands: View {
    @ObservedObject var desktop: DesktopPresentation
    var body: some View {
        Button(L10n.text("Переключить парящий режим")) { desktop.toggleMode() }
            .keyboardShortcut("j", modifiers: [.command, .option])
        Button(L10n.text("Боковое окно 1")) { desktop.companions.toggle(.first) }
            .keyboardShortcut("1", modifiers: [.command, .option])
        Button(L10n.text("Боковое окно 2")) { desktop.companions.toggle(.second) }
            .keyboardShortcut("2", modifiers: [.command, .option])
    }
}
