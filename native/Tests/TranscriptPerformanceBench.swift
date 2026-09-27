import AppKit
import SwiftUI

/// Measures the main-thread cost of a long conversation while a task runs:
/// `scripts/test_native.sh --perf-bench <messages>`. It needs a visible window for display
/// cycles, so a window appears for about 15 seconds; a disposable profile keeps the
/// operator's data untouched and no bridge or model starts.
extension NativeChecks {
    @MainActor static func transcriptPerformance(root: URL, messages count: Int) async throws {
        let suite = "pm-perf-bench-" + UUID().uuidString
        let defaults = UserDefaults(suiteName: suite)!
        let app = AppModel(configuration: LaunchConfiguration(projectRoot: root, python: root, stateDirectory: root.appendingPathComponent("perf-state")),
                           uiDefaults: defaults)
        defer { app.shutdown(); defaults.removePersistentDomain(forName: suite) }
        var conversation = Conversation()
        conversation.title = "Performance bench"
        conversation.provider = "claude"
        conversation.model = "claude-opus-5-5"
        conversation.messages = (0..<count).map { index in
            guard !index.isMultiple(of: 2) else {
                return ChatMessage(role: "user", text: "Брат, посмотри, пожалуйста, шаг \(index): что ещё можно улучшить в ленте и почему она подтормаживает?")
            }
            var message = ChatMessage(role: "assistant", text: benchAnswer(index))
            message.workLog = benchLog(index, entries: 12, live: false)
            message.agentRun = benchReceipt(index)
            return message
        }
        app.conversations = [conversation]
        app.select(conversation.id)
        let state = app.execution(for: conversation.id)
        state.running = true
        state.startedAt = Date()
        state.requestID = "bench"
        state.workLog = benchLog(999, entries: 4, live: true)

        let window = NSWindow(contentRect: NSRect(x: 180, y: 120, width: 1000, height: 760), styleMask: [.titled, .resizable],
                              backing: .buffered, defer: false)
        window.isReleasedWhenClosed = false
        window.level = .statusBar  // Above PM's floating windows, so it is never occluded.
        window.title = "PM transcript benchmark"
        window.contentView = NSHostingView(rootView: WorkspaceView(model: app))
        window.orderFrontRegardless()
        defer { window.orderOut(nil); window.close() }
        try await Task.sleep(for: .seconds(2))

        func cpu() -> Double { var value = timespec(); clock_gettime(CLOCK_THREAD_CPUTIME_ID, &value); return Double(value.tv_sec) + Double(value.tv_nsec) / 1e9 }
        // `--perf-sample <directory>` also profiles each phase with /usr/bin/sample.
        func profile(_ phase: String, seconds: Double) {
            guard let directory = LaunchConfiguration.argument("--perf-sample") else { return }
            let process = Process()
            process.executableURL = URL(fileURLWithPath: "/usr/bin/sample")
            process.arguments = [String(ProcessInfo.processInfo.processIdentifier), String(seconds), "-mayDie", "-file", directory + "/" + phase + ".txt"]
            process.standardOutput = FileHandle.nullDevice
            process.standardError = FileHandle.nullDevice
            try? process.run()
        }
        profile("idle", seconds: 2.5)
        var start = cpu()
        try await Task.sleep(for: .seconds(3))
        print(String(format: "PERF idle while running: %.1f%% of the main thread", (cpu() - start) / 3 * 100))

        profile("streaming", seconds: 2.5)
        start = cpu()
        for step in 0..<30 {
            state.appendStream("Порция ответа номер \(step), чтобы лента росла как при печати. ")
            if step % 5 == 4 { state.workLog = benchLog(999, entries: 5 + step / 5, live: true) }
            try await Task.sleep(for: .milliseconds(100))
        }
        let streaming = cpu() - start
        if let directory = LaunchConfiguration.argument("--perf-sample") {
            let capture = Process()
            capture.executableURL = URL(fileURLWithPath: "/usr/sbin/screencapture")
            capture.arguments = ["-x", "-o", "-l", String(window.windowNumber), directory + "/window.png"]
            try? capture.run()
            capture.waitUntilExit()
        }
        print(String(format: "PERF streaming 3 s (30 text batches, 6 work-log updates): %.1f%% of the main thread", streaming / 3 * 100))

        let frame = window.frame, top = NSScreen.screens[0].frame.maxY
        let point = CGPoint(x: frame.minX + frame.width * 0.62, y: top - frame.midY)
        CGEvent(mouseEventSource: nil, mouseType: .mouseMoved, mouseCursorPosition: point, mouseButton: .left)?.post(tap: .cghidEventTap)
        try await Task.sleep(for: .milliseconds(300))
        profile("scrolling", seconds: 1.8)
        start = cpu()
        for step in 0..<120 {
            let event = CGEvent(scrollWheelEvent2Source: nil, units: .pixel, wheelCount: 1, wheel1: step < 60 ? 40 : -40, wheel2: 0, wheel3: 0)
            event?.location = point
            event?.post(tap: .cghidEventTap)
            if step % 20 == 19 { state.appendStream("Ещё текст. ") }
            try await Task.sleep(for: .milliseconds(16))
        }
        let scrolling = cpu() - start
        print(String(format: "PERF scrolling ~2 s while running: %.1f%% of the main thread", scrolling / 2 * 100))
        if LaunchConfiguration.argument("--perf-sample") != nil { try await Task.sleep(for: .seconds(15)) }  // Let sample finish.
    }

    private static func benchAnswer(_ index: Int) -> String {
        """
        Брат, готово. Нашёл причину и исправил её, подробности ниже.

        **Что было.** Пока я работаю, лента пересобиралась на каждом кадре анимации: у сообщения \(index) десятки абзацев, и главный поток был занят почти на четверть даже без прокрутки.

        **Что сделал:**
        - Индикатор и блик перевёл на Core Animation, главный поток в этом не участвует.
        - Текст ответа выводится порциями не чаще 10 раз в секунду, на глаз разницы нет.
        - Добавил проверки, чтобы это не вернулось: `WorkingSpinnerView` и `appendStream`.

        **Что проверил:**
        1. Стенд на 400 сообщений: 126 перерисовок в секунду стало 0.
        2. Все 2015 нативных проверок прошли, включая 5 новых.
        3. Галерея показывает шапку журнала работы как раньше.

        ## Что осталось

        Сама прокрутка длинной ленты тоже недешёвая: SwiftUI на каждом шаге пересчитывает весь видимый набор сообщений, а выделение текста удваивает эту цену. В кадр это пока укладывается, но запас небольшой.

        Коммиты `a377749` и `7ee651c` локальные, запасная версия сохранена. Если после перезапуска всё ещё будет подтормаживать, следующий шаг — уменьшить число одновременно отображаемых сообщений или перестать пересобирать неизменившиеся.
        """
    }

    private static func benchLog(_ index: Int, entries: Int, live: Bool) -> JSONValue {
        let rows: [JSONValue] = (0..<entries).map { entry in
            entry.isMultiple(of: 3)
                ? .object(["id": .string("c\(index)-\(entry)"), "kind": .string("commentary"), "text": .string("Смотрю, что происходит, шаг \(entry).")])
                : .object(["id": .string("tool:t\(index)-\(entry)"), "kind": .string("tool"), "tool_id": .string("t\(index)-\(entry)"),
                           "tool_kind": .string("commandExecution"), "status": .string(live && entry == entries - 1 ? "inProgress" : "completed")])
        }
        return .object(["schema": .string("proto_mind.native_work_log.v1"), "id": .string("log-\(index)"), "public_only": .bool(true),
                        "status": .string(live ? "running" : "completed"), "stage": .string("working"), "state_version": .number(Double(entries)),
                        "elapsed_ms": .number(95_000), "entries": .array(rows)])
    }

    private static func benchReceipt(_ index: Int) -> JSONValue {
        let items: [JSONValue] = (0..<12).map { entry in
            entry == 5
                ? .object(["id": .string("t\(index)-\(entry)"), "kind": .string("fileChange"), "status": .string("completed"), "change_count": .number(1),
                           "paths": .array([.string("/Users/demo/proto_mind/native/Sources/WorkingIndicators.swift")]),
                           "file_changes": .array([.object(["path": .string("/Users/demo/proto_mind/native/Sources/WorkingIndicators.swift"),
                                                            "additions": .number(40), "deletions": .number(12)])])])
                : .object(["id": .string("t\(index)-\(entry)"), "kind": .string("commandExecution"), "status": .string("completed"),
                           "command": .string("scripts/test_native.sh"), "text": .string("Run native checks"), "duration_ms": .number(1200)])
        }
        return .object(["schema": .string("proto_mind.claude_agent_run.v1"), "provider": .string("claude"), "run_id": .string("run-\(index)"),
                        "status": .string("completed"), "items": .array(items), "command_count": .number(11), "workspace_root": .string("/Users/demo/proto_mind")])
    }
}
