import AppKit
import SwiftUI

/// Renders representative screens to PNG files for visual review:
/// `scripts/test_native.sh --ui-gallery <directory>`. A disposable profile and
/// UI-defaults suite keep the operator's data untouched; no bridge or model starts.
extension NativeChecks {
    @MainActor static func interfaceGallery(directory: URL, root: URL) async throws {
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        let suite = "pm-interface-gallery-" + UUID().uuidString
        let defaults = UserDefaults(suiteName: suite)!
        let state = root.appendingPathComponent("gallery-state")
        let app = AppModel(configuration: LaunchConfiguration(projectRoot: root, python: root, stateDirectory: state), uiDefaults: defaults)
        defer { app.shutdown(); defaults.removePersistentDomain(forName: suite); L10n.language = .russian }
        let selected = galleryConversations(app)
        func file(_ name: String) -> URL { directory.appendingPathComponent(name + ".png") }
        for language in [InterfaceLanguage.russian, .english] {
            L10n.language = language
            for dark in [true, false] {
                try await galleryRender(WorkspaceView(model: app), size: NSSize(width: 1320, height: 860), dark: dark,
                                        to: file("workspace-\(language.rawValue)-\(dark ? "dark" : "light")"))
            }
        }
        L10n.language = .russian
        try await galleryRender(WorkspaceView(model: app), size: NSSize(width: 960, height: 640), dark: false, to: file("workspace-small"))
        app.showInspector = false
        try await galleryRender(EvidenceInspectorView(model: app), size: NSSize(width: 560, height: 680), dark: false, to: file("inspector"))
        app.setComposer("Ещё проверь, пожалуйста, тёмную тему")
        app.busy = true
        try await galleryRender(ComposerView(model: app).padding(20), size: NSSize(width: 820, height: 220), dark: false, to: file("composer-busy-with-text"))
        app.setComposer("")
        try await galleryRender(ComposerView(model: app).padding(20), size: NSSize(width: 820, height: 220), dark: false, to: file("composer-busy-empty"))
        app.busy = false
        for section in NativeSettingsSection.allCases {
            app.settingsSection = section
            try await galleryRender(NativeSettingsView(model: app), size: NSSize(width: 820, height: 700), dark: false, to: file("settings-\(section.rawValue)"))
        }
        app.newConversation()
        try await galleryRender(WorkspaceView(model: app), size: NSSize(width: 1320, height: 860), dark: true, to: file("welcome-dark"))
        app.select(selected)
        print("Interface gallery: \(directory.path)")
    }

    @MainActor private static func galleryConversations(_ app: AppModel) -> UUID {
        func message(_ role: String, _ text: String, minutesAgo: Double, notices: [String] = [], error: Bool = false, updates: [TaskUpdate]? = nil) -> ChatMessage {
            var value = ChatMessage(role: role, text: text)
            value.createdAt = Date().addingTimeInterval(-minutesAgo * 60)
            value.notices = notices; value.isError = error; value.taskUpdates = updates
            return value
        }
        func conversation(_ title: String, provider: String, model: String, path: String?, hoursAgo: Double, messages: [ChatMessage] = []) -> Conversation {
            var value = Conversation()
            value.title = title; value.provider = provider; value.model = model; value.workspacePath = path
            value.updatedAt = Date().addingTimeInterval(-hoursAgo * 3600); value.messages = messages
            return value
        }
        var accepted = TaskUpdate(text: "И добавь, пожалуйста, проверку тёмной темы")
        accepted.state = .accepted
        let answer = """
        ## Итог проверки

        Нашёл **три** заметных места и одно улучшение. Подробности ниже.

        1. Шапка боковой панели обрезает длинные названия.
        2. В тёмной теме подсказки композера слишком бледные.
        3. Таблицы в узкой панели прокручиваются без видимой полосы.

        | Экран | Проблема | Важность |
        | :--- | :--- | :---: |
        | Боковая панель | Обрезка названий | средняя |
        | Композер | Контраст подсказок | низкая |

        ```swift
        Text(title).lineLimit(1).truncationMode(.middle)
        ```

        Файл `SidebarView.swift`, ссылка: [документация](https://developer.apple.com).
        """
        let main = conversation("Аудит интерфейса Proto-Mind", provider: "claude", model: "claude-opus-5-5", path: "/Users/demo/proto_mind", hoursAgo: 0.1, messages: [
            message("user", "Брат, проведи аудит интерфейса и найди, что можно улучшить", minutesAgo: 30, updates: [accepted]),
            message("assistant", answer, minutesAgo: 25, notices: ["Claude usage for this turn: 12 model requests, context up to 142K tokens."]),
            message("user", "[Proto-Mind: sent by the agent of task «Проверка тестов» (claude · claude-opus-5-5) through pm_send_task_message; the operator did not type it. Treat it as that agent's delegated request.]\n\nПроверь, пожалуйста, что тесты проходят после правки.", minutesAgo: 12),
            message("report", "Claude: достигнут лимит. После обновления (время — в разделе «Лимиты») следующее сообщение продолжит эту же сессию; автоматического повтора не было.", minutesAgo: 10, error: true),
            message("user", "Продолжай, брат", minutesAgo: 3),
            message("assistant", "Продолжил: тесты проходят, правка в `SidebarView.swift` готова. Осталось проверить узкое окно.", minutesAgo: 1),
        ])
        let others = [
            conversation("Коммерческое предложение для Northstar", provider: "codex", model: "gpt-6-astra", path: "/Users/demo/Работа", hoursAgo: 3),
            conversation("Лендинг для кофейни с очень длинным названием, которое не помещается в строку", provider: "codex", model: "", path: "/Users/demo/addons", hoursAgo: 20),
            conversation("Telegram · удалённые задачи", provider: "codex", model: "", path: nil, hoursAgo: 30),
            conversation("Идеи для VIREN", provider: "claude", model: "opus", path: nil, hoursAgo: 50),
            conversation("Новый диалог", provider: "ollama", model: "", path: nil, hoursAgo: 70),
        ]
        app.conversations = [main] + others
        app.select(main.id)
        return main.id
    }

    @MainActor private static func galleryRender<Content: View>(_ content: Content, size: NSSize, dark: Bool, to destination: URL) async throws {
        let appearance = NSAppearance(named: dark ? .darkAqua : .aqua)
        let window = NSWindow(contentRect: NSRect(origin: .zero, size: size), styleMask: [.borderless], backing: .buffered, defer: false)
        window.isReleasedWhenClosed = false
        window.appearance = appearance
        let host = NSHostingView(rootView: content.frame(width: size.width, height: size.height, alignment: .topLeading)
            .background(NativeTheme.canvas).environment(\.colorScheme, dark ? .dark : .light))
        host.appearance = appearance
        host.frame = NSRect(origin: .zero, size: size)
        window.contentView = host
        defer { window.contentView = nil; window.close() }
        host.layoutSubtreeIfNeeded()
        try await Task.sleep(for: .milliseconds(400))
        host.layoutSubtreeIfNeeded()
        guard let bitmap = host.bitmapImageRepForCachingDisplay(in: host.bounds) else { throw NativeError.message("Gallery bitmap unavailable") }
        // Dynamic AppKit colors resolve against the current drawing appearance.
        (appearance ?? NSAppearance.currentDrawing()).performAsCurrentDrawingAppearance { host.cacheDisplay(in: host.bounds, to: bitmap) }
        guard let data = bitmap.representation(using: .png, properties: [:]) else { throw NativeError.message("Gallery image unavailable") }
        try data.write(to: destination)
    }
}
