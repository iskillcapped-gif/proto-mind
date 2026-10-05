import AppKit
import CryptoKit
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
        let selected = galleryConversations(app, root: root)
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
        // The sidebar at the cube's width, and the card a chat row shows beside it on hover.
        try await galleryRender(SidebarView(model: app, libraryExpanded: .constant(false), openSettings: {}), size: NSSize(width: 230, height: 760), dark: true,
                                to: file("sidebar-narrow-dark"))
        try await galleryRender(SidebarHoverCardView(title: "Лендинг для кофейни с очень длинным названием, которое не помещается в строку",
                                                     detail: "Codex · 20 ч назад", status: ("pencil", "Есть черновик"))
                                    .padding(.horizontal, 12).padding(.vertical, 9).frame(width: 290, alignment: .leading)
                                    .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 10)).padding(20),
                                size: NSSize(width: 340, height: 150), dark: true, to: file("sidebar-hover-card-dark"))
        app.showInspector = false
        try await galleryRender(EvidenceInspectorView(model: app), size: NSSize(width: 560, height: 680), dark: false, to: file("inspector"))
        app.setComposer("Ещё проверь, пожалуйста, тёмную тему")
        app.busy = true
        try await galleryRender(ComposerView(model: app).padding(20), size: NSSize(width: 820, height: 220), dark: false, to: file("composer-busy-with-text"))
        app.setComposer("")
        try await galleryRender(ComposerView(model: app).padding(20), size: NSSize(width: 820, height: 220), dark: false, to: file("composer-busy-empty"))
        app.busy = false
        // A draft with an attached screenshot shows the picture itself; the second frame is a Claude chat without cloud permission.
        if let index = app.conversations.firstIndex(where: { $0.id == selected }) {
            let screenshot = galleryImage(root: root)
            _ = await AttachmentThumbnails.load(screenshot)
            app.conversations[index].pendingImages = [screenshot]
            app.setComposer("Брат, посмотри на этот скрин")
            app.cloudConsent = true
            for dark in [true, false] {
                try await galleryRender(ComposerView(model: app).padding(20), size: NSSize(width: 820, height: 300), dark: dark, to: file("composer-image-\(dark ? "dark" : "light")"))
            }
            app.cloudConsent = false
            try await galleryRender(ComposerView(model: app).padding(20), size: NSSize(width: 820, height: 300), dark: true, to: file("composer-image-not-sent"))
            app.conversations[index].pendingImages = []
            app.setComposer("")
        }
        for section in NativeSettingsSection.allCases {
            app.settingsSection = section
            for dark in [false, true] {
                try await galleryRender(NativeSettingsView(model: app), size: NSSize(width: 820, height: 1000), dark: dark,
                                        to: file("settings-\(section.rawValue)-\(dark ? "dark" : "light")"))
            }
        }
        L10n.language = .english
        for section in NativeSettingsSection.allCases where section != .services {
            app.settingsSection = section
            try await galleryRender(NativeSettingsView(model: app), size: NSSize(width: 820, height: 1000), dark: true, to: file("settings-\(section.rawValue)-en"))
        }
        L10n.language = .russian
        // Models for each kind of source; Settings follows the selected chat.
        if let index = app.conversations.firstIndex(where: { $0.id == selected }) {
            let original = app.conversations[index]
            app.settingsSection = .models
            for provider in ["codex", "ollama", "api"] {
                app.conversations[index].provider = provider
                try await galleryRender(NativeSettingsView(model: app), size: NSSize(width: 820, height: 1000), dark: true, to: file("settings-models-\(provider)"))
            }
            app.conversations[index] = original
        }
        // Connections: the list by purpose, then each connection's own page.
        var service = WorkspaceService(); service.name = "Linear"; service.endpoint = "https://mcp.linear.app/mcp"; service.enabled = true
        try? app.workspaceServices.save(service)
        app.settingsSection = .services
        for dark in [false, true] {
            try await galleryRender(NativeSettingsView(model: app), size: NSSize(width: 820, height: 760), dark: dark, to: file("settings-connections-\(dark ? "dark" : "light")"))
        }
        try await galleryRender(NativeSettingsView(model: app), size: NSSize(width: 600, height: 760), dark: true, to: file("settings-connections-narrow"))
        L10n.language = .english
        try await galleryRender(NativeSettingsView(model: app), size: NSSize(width: 820, height: 760), dark: true, to: file("settings-connections-en"))
        app.settingsConnection = .mcp
        try await galleryRender(NativeSettingsView(model: app), size: NSSize(width: 820, height: 760), dark: true, to: file("settings-connection-mcp-en"))
        L10n.language = .russian
        for kind in ConnectionKind.allCases {
            app.settingsConnection = kind
            try await galleryRender(NativeSettingsView(model: app), size: NSSize(width: 820, height: 760), dark: true, to: file("settings-connection-\(kind.rawValue)"))
        }
        app.settingsConnection = nil
        try? app.workspaceServices.remove(service)
        if let withImage = app.conversations.first(where: { $0.id == selected })?.messages.first(where: { !($0.imageContext ?? []).isEmpty }) {
            for image in withImage.imageContext ?? [] { _ = await AttachmentThumbnails.load(image) }
            try await galleryRender(MessageView(message: withImage, model: app).padding(24), size: NSSize(width: 820, height: 320), dark: true,
                                    to: file("message-image-dark"))
        }
        // A screenshot opened from a message fills a side panel; a double click shows it at 100%.
        let panel = app.workspacePanel, shown = panel.visible
        if let tab = panel.open(.image(try zoomPreview(width: 2872, height: 1712, dpi: 144))) {
            try await galleryRender(WorkspacePanelView(model: app, panel: panel), size: NSSize(width: 560, height: 640), dark: true, to: file("image-panel-fit-dark"))
            try await galleryRender(WorkspacePanelView(model: app, panel: panel), size: NSSize(width: 560, height: 640), dark: true, to: file("image-panel-100-dark")) { host in
                guard let zoom = galleryZoomView(in: host) else { throw NativeError.message("Gallery picture unavailable") }
                zoom.toggle(at: NSPoint(x: 1436 * 0.3, y: 856 * 0.45))
                for _ in 0..<40 where !zoom.showsOriginal { try await Task.sleep(for: .milliseconds(50)) }
            }
            panel.close(tab)
        }
        panel.visible = shown
        // The library keeps what was sent to chats: pictures in a grid, PDFs and text files in a list.
        let fixtures = try libraryFixtures(root: root.appendingPathComponent("gallery-library"))
        await app.attachmentLibrary.capture(AttachmentLibraryStore.candidates(images: fixtures.images + [galleryImage(root: root)], pdfs: fixtures.pdfs,
                                                                              files: fixtures.files, workspace: fixtures.workspace.path,
                                                                              conversationID: selected, messageID: UUID(), sentAt: Date()))?.value
        await app.attachmentLibrary.reload()
        for entry in app.attachmentLibrary.entries where entry.kind == .image {
            if let copy = app.attachmentLibrary.copy(of: entry) { _ = await AttachmentThumbnails.load(entry.imageMetadata(copy: copy)) }
        }
        for pictures in [true, false] {
            try await galleryRender(AttachmentLibraryView(model: app, library: app.attachmentLibrary, pictures: pictures), size: NSSize(width: 900, height: 520),
                                    dark: true, to: file(pictures ? "library-images-dark" : "library-files-dark"))
        }
        try await galleryRender(SidebarView(model: app, libraryExpanded: .constant(true), openSettings: {}), size: NSSize(width: 230, height: 760), dark: true,
                                to: file("sidebar-library-dark"))
        // The built-in browser when a site asks for a passkey (reserved .example hosts, local HTML).
        let passkeyTab = NativeBrowserTab()
        passkeyTab.webView.frame = NSRect(x: 0, y: 0, width: 560, height: 480)
        passkeyTab.navigate("https://claim.example/code")
        passkeyTab.webView.loadHTMLString("<html><body style='font: 15px -apple-system; padding: 40px; color: #222'><h2>Подтвердите личность с помощью ключа доступа</h2><p>Используйте отпечаток пальца или блокировку экрана.</p></body></html>",
                                          baseURL: URL(string: "https://accounts.example/")!)
        var waited = 0
        while passkeyTab.webView.isLoading || passkeyTab.webView.url?.host != "accounts.example", waited < 500 { try await Task.sleep(for: .milliseconds(20)); waited += 1 }
        _ = try? await passkeyTab.webView.callAsyncJavaScript("navigator.credentials.get({ publicKey: { challenge: new Uint8Array(16) } }).catch(() => {}); return true", contentWorld: .page)
        while passkeyTab.passkeyRequest == nil, waited < 1000 { try await Task.sleep(for: .milliseconds(20)); waited += 1 }
        try await galleryRender(BrowserView(browser: passkeyTab, app: app), size: NSSize(width: 560, height: 480), dark: true, to: file("browser-passkey-dark"))
        passkeyTab.close()
        let (log, receipt) = galleryWork()
        for dark in [true, false] {
            try await galleryRender(WorkTimelineView(log: log, agentReceipt: receipt, live: true, startedAt: Date().addingTimeInterval(-95)).padding(24),
                                    size: NSSize(width: 820, height: 520), dark: dark, to: file("work-timeline-\(dark ? "dark" : "light")"))
        }
        try await galleryRender(AgentActivityView(items: receipt["items"].items, receipt: receipt).padding(24), size: NSSize(width: 820, height: 560), dark: true, to: file("work-actions-dark"))
        app.newConversation()
        try await galleryRender(WorkspaceView(model: app), size: NSSize(width: 1320, height: 860), dark: true, to: file("welcome-dark"))
        app.select(selected)
        print("Interface gallery: \(directory.path)")
    }

    @MainActor private static func galleryZoomView(in view: NSView) -> ImageZoomScrollView? {
        if let zoom = view as? ImageZoomScrollView { return zoom }
        return view.subviews.lazy.compactMap { galleryZoomView(in: $0) }.first
    }

    /// A small attached screenshot, so the transcript shows an image the way a message carries it.
    private static func galleryImage(root: URL) -> JSONValue {
        let context = CGContext(data: nil, width: 1440, height: 860, bitsPerComponent: 8, bytesPerRow: 0, space: CGColorSpaceCreateDeviceRGB(),
                                bitmapInfo: CGImageAlphaInfo.noneSkipLast.rawValue)!
        context.setFillColor(CGColor(red: 0.13, green: 0.14, blue: 0.17, alpha: 1)); context.fill(CGRect(x: 0, y: 0, width: 1440, height: 860))
        context.setFillColor(CGColor(red: 0.2, green: 0.45, blue: 0.9, alpha: 1)); context.fill(CGRect(x: 80, y: 620, width: 520, height: 120))
        context.setFillColor(CGColor(gray: 0.85, alpha: 1)); context.fill(CGRect(x: 80, y: 420, width: 1100, height: 40))
        context.setFillColor(CGColor(gray: 0.55, alpha: 1)); context.fill(CGRect(x: 80, y: 340, width: 860, height: 30))
        let data = NSBitmapImageRep(cgImage: context.makeImage()!).representation(using: .png, properties: [:])!
        let file = root.appendingPathComponent("Снимок экрана.png")
        try? FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        try? data.write(to: file)
        return .object(["schema": .string("proto_mind.native_image.v1"), "path": .string(file.path), "name": .string(file.lastPathComponent),
                        "sha256": .string(SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()), "mime_type": .string("image/png"),
                        "size_bytes": .number(Double(data.count)), "width": .number(1440), "height": .number(860)])
    }

    @MainActor private static func galleryConversations(_ app: AppModel, root: URL) -> UUID {
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
        accepted.imageContext = [galleryImage(root: root)]
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
            { var value = message("user", "Брат, проведи аудит интерфейса и найди, что можно улучшить", minutesAgo: 30, updates: [accepted])
              value.imageContext = [galleryImage(root: root)]
              return value }(),
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

    /// A Claude turn's public work log and action receipt, as the worker now reports them.
    private static func galleryWork() -> (JSONValue, JSONValue) {
        func row(_ id: String, _ fields: [String: JSONValue]) -> JSONValue { .object(["id": .string(id), "status": .string("completed")].merging(fields) { $1 }) }
        let items: [JSONValue] = [
            row("t1", ["kind": .string("commandExecution"), "tool": .string("Bash"), "command": .string("git status --short && git log --oneline -3"),
                       "text": .string("Show repo state and recent commits"), "output_preview": .string("?? notes.md\n2c91def fix: interface audit findings"), "duration_ms": .number(420)]),
            row("t2", ["kind": .string("fileRead"), "tool": .string("Read"), "path": .string("/Users/demo/proto_mind/AGENTS.md"), "duration_ms": .number(35)]),
            row("t3", ["kind": .string("search"), "tool": .string("Grep"), "query": .string("canUpdateTask"), "path": .string("native/Sources"),
                       "output_preview": .string("TaskUpdates.swift:83"), "duration_ms": .number(60)]),
            row("t4", ["kind": .string("fileChange"), "tool": .string("Edit"), "paths": .array([.string("/Users/demo/proto_mind/native/Sources/TaskUpdates.swift")]),
                       "change_count": .number(1), "diff_preview": .string("- provider == \"codex\"\n+ updatableProviders.contains(provider)"), "duration_ms": .number(80)]),
            row("t5", ["kind": .string("commandExecution"), "tool": .string("Bash"), "command": .string("scripts/test_native.sh"),
                       "text": .string("Run all native checks"), "status": .string("inProgress")]),
            row("t6", ["kind": .string("dynamicToolCall"), "tool": .string("pm_list_tasks"), "duration_ms": .number(210)]),
            row("t7", ["kind": .string("agentTool"), "tool": .string("Agent"), "text": .string("Explore the settings views"), "duration_ms": .number(61000)]),
        ]
        let entry = { (id: String, kind: String, extra: [String: JSONValue]) in JSONValue.object(["id": .string(id), "kind": .string(kind)].merging(extra) { $1 }) }
        let log = JSONValue.object(["schema": .string("proto_mind.native_work_log.v1"), "id": .string("gallery-log"), "public_only": .bool(true),
            "status": .string("running"), "stage": .string("working"), "state_version": .number(3), "entries": .array([
                entry("c1", "commentary", ["text": .string("Смотрю состояние репозитория и нужные файлы.")]),
                entry("tool:t1", "tool", ["tool_id": .string("t1"), "tool_kind": .string("commandExecution")]),
                entry("tool:t2", "tool", ["tool_id": .string("t2"), "tool_kind": .string("fileRead")]),
                entry("tool:t3", "tool", ["tool_id": .string("t3"), "tool_kind": .string("search")]),
                entry("c2", "commentary", ["text": .string("Нашёл проверку провайдера, правлю её.")]),
                entry("tool:t4", "tool", ["tool_id": .string("t4"), "tool_kind": .string("fileChange")]),
                entry("tool:t5", "tool", ["tool_id": .string("t5"), "tool_kind": .string("commandExecution")]),
                entry("c3", "commentary", ["text": .string("Параллельно проверяю задачи PM и прошу помощника осмотреть настройки.")]),
                entry("tool:t6", "tool", ["tool_id": .string("t6"), "tool_kind": .string("dynamicToolCall")]),
                entry("tool:t7", "tool", ["tool_id": .string("t7"), "tool_kind": .string("agentTool")]),
            ])])
        let receipt = JSONValue.object(["schema": .string("proto_mind.claude_agent_run.v1"), "provider": .string("claude"), "run_id": .string("3f2a9c1e-0000"),
            "status": .string("completed"), "items": .array(items), "command_count": .number(2), "web_search_count": .number(0), "computer_use_count": .number(0),
            "finished_at": .string("2026-09-26T12:40:00Z")])
        return (log, receipt)
    }

    @MainActor private static func galleryRender<Content: View>(_ content: Content, size: NSSize, dark: Bool, to destination: URL,
                                                               prepare: ((NSView) async throws -> Void)? = nil) async throws {
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
        try await prepare?(host)
        try await Task.sleep(for: .milliseconds(400))
        host.layoutSubtreeIfNeeded()
        guard let bitmap = host.bitmapImageRepForCachingDisplay(in: host.bounds) else { throw NativeError.message("Gallery bitmap unavailable") }
        // Dynamic AppKit colors resolve against the current drawing appearance.
        (appearance ?? NSAppearance.currentDrawing()).performAsCurrentDrawingAppearance { host.cacheDisplay(in: host.bounds, to: bitmap) }
        guard let data = bitmap.representation(using: .png, properties: [:]) else { throw NativeError.message("Gallery image unavailable") }
        try data.write(to: destination)
    }
}
