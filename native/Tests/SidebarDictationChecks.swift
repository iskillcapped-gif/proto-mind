import AppKit
import AVFoundation
import SwiftUI

@MainActor
private final class FixtureDictationSpeech: DictationRecognizing {
    var onText: ((String, Bool) -> Void)?
    var onLevel: ((Double) -> Void)?
    var onFailure: ((String) -> Void)?
    var starts = 0
    var finishes = 0
    var cancellations = 0
    var startHook: (() async throws -> Void)?
    func start(locale: Locale) async throws { starts += 1; try await startHook?() }
    func finish() { finishes += 1 }
    func cancel() { cancellations += 1 }
}

extension NativeChecks {
    @MainActor
    static func sidebarProjectOrdering(root: URL) throws {
        let suite = "proto-mind-sidebar-checks." + UUID().uuidString
        let defaults = UserDefaults(suiteName: suite)!
        defer { defaults.removePersistentDomain(forName: suite) }
        let state = root.appendingPathComponent("sidebar-order")
        let order = SidebarProjectOrder(stateDirectory: state, defaults: defaults)
        var a = Conversation(), b = Conversation(), c = Conversation(), loose = Conversation()
        a.workspacePath = "/projects/one/shared"; b.workspacePath = "/projects/two/shared"; c.workspacePath = "/projects/C"
        a.updatedAt = Date(timeIntervalSince1970: 40); b.updatedAt = Date(timeIntervalSince1970: 30)
        c.updatedAt = Date(timeIntervalSince1970: 20); loose.updatedAt = Date(timeIntervalSince1970: 10)
        var conversations = [c, loose, b, a]
        let original = order.groups(conversations).map(\.id)
        try check(original == ["workspace:" + a.workspacePath!, "workspace:" + b.workspacePath!, "workspace:/projects/C", "unbound"],
                  "Project groups distinguish identical folder names and preserve the original recency order before manual sorting")
        try check(!FileManager.default.fileExists(atPath: state.path) && defaults.dictionaryRepresentation().keys.allSatisfy { !$0.hasPrefix("sidebarProjectOrder") },
                  "Reading sidebar order creates no private state or preference writes")
        let transfer = SidebarProjectTransfer(id: original[2], owner: order.owner)
        try check(order.move(transfer, to: original[0], after: false, conversations: conversations), "Dragging a project upward moves the whole group")
        let expected = [original[2], original[0], original[1], original[3]]
        try check(order.ids == expected && SidebarProjectOrder(stateDirectory: state, defaults: defaults).ids == expected,
                  "Manual project order survives a new application instance")
        conversations[2].updatedAt = Date(timeIntervalSince1970: 1000)
        try check(order.groups(conversations).map(\.id) == expected, "New activity does not undo the manually chosen project order")
        try check(order.groups([a, c]).map(\.id) == [original[2], original[0]], "Search and archive filtering preserve the relative project order")
        try check(order.move(.init(id: original[0], owner: order.owner), to: original[1], after: true, conversations: conversations)
                  && order.ids == [original[2], original[1], original[0], original[3]], "Dropping below a project moves it downward without losing hidden groups")
        let before = order.ids
        try check(!order.move(.init(id: original[0], owner: UUID()), to: original[1], after: false, conversations: conversations)
                  && !order.move(.init(id: "missing", owner: order.owner), to: original[1], after: false, conversations: conversations)
                  && !order.move(.init(id: original[0], owner: order.owner), to: original[0], after: false, conversations: conversations)
                  && order.ids == before, "Foreign drags, missing projects and dropping onto the source cannot corrupt order")
        var fresh = Conversation(); fresh.workspacePath = "/projects/new"
        try check(order.groups(conversations + [fresh]).map(\.id) == before + ["workspace:/projects/new"],
                  "A newly added project follows the manual order without resetting existing projects")
        try check(SidebarProjectOrder(stateDirectory: root.appendingPathComponent("separate-profile"), defaults: defaults).ids.isEmpty,
                  "Project order is isolated by application profile")
        let app = AppModel(configuration: .init(projectRoot: root, python: root, stateDirectory: state), uiDefaults: defaults)
        defer { app.shutdown() }
        app.conversations = conversations; app.selectedID = a.id
        app.execution(for: c.id).running = true
        let history = app.currentHistoryArchive
        app.sidebarProjectOrder.move(.init(id: original[3], owner: app.sidebarProjectOrder.owner), to: original[2], after: false, conversations: conversations)
        try check(app.currentHistoryArchive.conversations == history.conversations && app.selectedID == history.selectedID && app.isRunning(c.id),
                  "Reordering while a task runs does not rewrite history, switch the editor or stop execution")
        for width: CGFloat in [240, 280, 320] {
            let view = NSHostingController(rootView: SidebarView(model: app, libraryExpanded: .constant(false), openSettings: {}))
            let size = view.sizeThatFits(in: .init(width: width, height: 680))
            try check(size.width <= width + 1 && size.height <= 681, "Sidebar menu and adjacent voice button fit \(Int(width)) points")
        }
    }

    @MainActor
    static func composerDictation(root: URL) async throws {
        let suite = "proto-mind-dictation-checks." + UUID().uuidString
        let defaults = UserDefaults(suiteName: suite)!
        defer { defaults.removePersistentDomain(forName: suite) }
        let speech = FixtureDictationSpeech()
        let state = root.appendingPathComponent("dictation")
        let app = AppModel(configuration: .init(projectRoot: root, python: root, stateDirectory: state), uiDefaults: defaults, dictationSpeech: speech)
        defer { app.shutdown() }
        let dictation = app.dictation
        try check(!dictation.active && speech.starts == 0 && !app.liveVoice.inCall && !app.cloudConsent,
                  "Creating the app does not start dictation, open an API call or grant cloud permission")
        try check(dictation.canStart(app: app), "Text dictation works without an OpenAI key or ChatGPT login")
        app.setComposer("Брат 💙,")
        app.conversations[0].pendingCriteria = ["Keep my attachment"]
        app.conversations[0].pendingFiles = [.object(["path": .string("notes.md"), "sha256": .string(String(repeating: "a", count: 64)),
            "included_chars": .number(20), "truncated": .bool(false)])]
        let files = app.selected!.pendingFiles
        app.execution(for: app.selectedID!).running = true
        await dictation.start(app: app)
        try check(dictation.phase == .listening && speech.starts == 1, "Dictation can add an update while the selected task is running")
        speech.onText?("давай", false)
        speech.onText?("давай продолжим", false)
        try check(app.composer == "Брат 💙, давай продолжим" && app.selected?.draft == app.composer
                  && app.selected?.messages.isEmpty == true && app.selected?.pendingFiles == files,
                  "Partial recognition replaces its own partial text, preserving the existing draft and attachments without sending")
        dictation.finish()
        try check(dictation.phase == .finishing && speech.finishes == 1, "Finishing stops microphone capture before waiting for final recognition")
        speech.onText?("Давай продолжим.", true)
        try check(!dictation.active && app.composer == "Брат 💙, Давай продолжим.", "The final transcript is left as an editable unsent message")
        app.flushDraft()
        try check(try ChatStore(directory: state).load().conversations.first?.draft == app.composer, "Dictated text uses the ordinary verified draft persistence path")

        await dictation.start(app: app)
        let delayed = speech.onText
        speech.onText?("Ещё", false)
        app.composer += " — исправлено вручную"
        let manual = app.composer
        delayed?("Устаревшее распознавание", true)
        try check(!dictation.active && app.composer == manual, "Typing during dictation preserves the edit and rejects late speech callbacks")

        await dictation.start(app: app)
        let fromPreviousConversation = speech.onText
        speech.onText?("Сохранить здесь", false)
        let originalID = app.selectedID!, oldDraft = app.composer
        var other = Conversation(); other.draft = "Другой черновик"
        app.conversations.append(other)
        app.selectedID = other.id; app.restoreComposer()
        fromPreviousConversation?("Нельзя вставить в другой диалог", true)
        try check(!dictation.active && app.composer == other.draft && app.conversations.first { $0.id == originalID }?.draft == oldDraft,
                  "Switching conversations stops capture and keeps the transcript with its original draft")

        await dictation.start(app: app)
        speech.onText?("Частичный текст", false)
        let beforeFailure = app.composer
        speech.onFailure?("Микрофон отключён")
        try check(!dictation.active && dictation.error == "Микрофон отключён" && app.composer == beforeFailure,
                  "Device failure releases dictation and retains already recognized text")
        await dictation.start(app: app)
        app.section = .workspace
        try check(!dictation.active, "Leaving the chat stops dictation")
        app.section = .chat
        await dictation.start(app: app)
        app.presentLiveVoice(openSettings: {})
        try check(!dictation.active && app.settingsSection == .voice && !app.liveVoice.inCall,
                  "Opening the voice entry releases dictation before setup or a voice call")

        dictation.setLanguage(.ukrainian)
        let reopened = DictationModel(stateDirectory: state, defaults: defaults, speech: FixtureDictationSpeech())
        try check(reopened.language == .ukrainian && !reopened.active, "Dictation language persists; microphone state never does")
        reopened.shutdown()

        var permission: CheckedContinuation<Void, Never>?
        speech.startHook = { await withCheckedContinuation { permission = $0 } }
        let starting = Task { await dictation.start(app: app) }
        await Task.yield()
        try check(dictation.phase == .preparing, "Pending microphone authorization has a visible cancellable state")
        dictation.stop()
        permission?.resume(); await starting.value
        try check(!dictation.active, "An authorization result arriving after cancellation cannot reactivate dictation")
        speech.startHook = nil

        await dictation.start(app: app)
        let finalAfterStop = speech.onText
        dictation.stop()
        app.setComposer("Следующее сообщение")
        finalAfterStop?("Старая финальная реплика", true)
        try check(app.composer == "Следующее сообщение" && !dictation.active, "Submission boundary rejects late recognition into the next message")
        await dictation.start(app: app)
        dictation.shutdown()
        try check(!dictation.active && speech.cancellations > 0 && !app.client.connected && !app.serviceClient.connected,
                  "Shutdown releases dictation without starting a provider or affecting the running task")

        let samples: [Int16] = [100, -2500, 0, .max, .min]
        let data = samples.withUnsafeBytes { Data($0) }
        let buffer = DictationSpeech.pcmBuffer(data)!
        try check(buffer.frameLength == samples.count && buffer.format.sampleRate == 24_000
                  && Array(UnsafeBufferPointer(start: buffer.int16ChannelData![0], count: samples.count)) == samples,
                  "Apple Speech receives the exact signed mono microphone samples with the correct sample rate")
        try check(DictationSpeech.pcmBuffer(Data()) == nil && DictationSpeech.pcmBuffer(Data([1])) == nil,
                  "Dictation never forwards an empty or incomplete PCM frame")
    }
}
