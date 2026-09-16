import AppKit
import Combine

enum DictationLanguage: String, CaseIterable, Identifiable {
    case russian = "ru-RU", ukrainian = "uk-UA", english = "en-US", system = "system"
    var id: String { rawValue }
    var title: String {
        switch self {
        case .russian: return "Русский"
        case .ukrainian: return "Українська"
        case .english: return "English"
        case .system: return L10n.text("Язык системы")
        }
    }
    var locale: Locale { self == .system ? .current : Locale(identifier: rawValue) }
}

@MainActor
final class DictationModel: ObservableObject {
    enum Phase { case idle, preparing, listening, finishing }
    @Published private(set) var phase: Phase = .idle
    @Published private(set) var error: String?
    @Published private(set) var level = 0.0
    @Published private(set) var language: DictationLanguage
    var active: Bool { phase != .idle }
    private let speech: DictationRecognizing
    private let defaults: UserDefaults
    private let preferenceKey: String
    private var token = UUID()
    private var finishDeadline: Task<Void, Never>?
    private var observers: [NSObjectProtocol] = []
    private weak var app: AppModel?
    private var conversationID: UUID?
    private var base = ""
    private var lastApplied = ""
    private var applying = false

    init(stateDirectory: URL, defaults: UserDefaults = .standard, speech: DictationRecognizing? = nil) {
        self.defaults = defaults; self.speech = speech ?? DictationSpeech()
        preferenceKey = NativeUIPreference.key("dictationLanguage", stateDirectory: stateDirectory)
        language = defaults.string(forKey: preferenceKey).flatMap(DictationLanguage.init) ?? .russian
        observers.append(NSWorkspace.shared.notificationCenter.addObserver(forName: NSWorkspace.willSleepNotification, object: nil, queue: .main) { [weak self] _ in
            Task { @MainActor in self?.stop() }
        })
    }

    func canStart(app: AppModel) -> Bool {
        app.selected != nil && app.selected?.archived != true && app.section == .chat
            && !app.operationBusy && !app.privateBackupRestartRequired && !app.liveVoice.inCall
            && !app.historyPersistence.blocksSubmission && app.presentations.pages.isEmpty
    }

    func setLanguage(_ value: DictationLanguage) {
        stop(); language = value; defaults.set(value.rawValue, forKey: preferenceKey)
    }

    func toggle(app: AppModel) async {
        if active { finish(); return }
        await start(app: app)
    }

    func start(app: AppModel) async {
        guard !active, canStart(app: app) else { return }
        token = UUID(); let token = token
        self.app = app; conversationID = app.selectedID
        base = app.composer; lastApplied = base
        phase = .preparing; error = nil; level = 0
        speech.onText = { [weak self] text, final in
            guard let self, self.token == token, self.active else { return }
            self.receive(text)
            if final { self.stop() }
        }
        speech.onLevel = { [weak self] level in
            guard let self, self.token == token, self.active else { return }
            self.level = level
        }
        speech.onFailure = { [weak self] message in
            guard let self, self.token == token, self.active else { return }
            self.stop(); self.error = message
        }
        do {
            try await speech.start(locale: language.locale)
            guard self.token == token, phase == .preparing else { return }
            phase = .listening
        } catch {
            guard self.token == token else { return }
            stop()
            if !(error is CancellationError) { self.error = error.localizedDescription }
        }
    }

    private func receive(_ transcript: String) {
        guard let app, app.selectedID == conversationID, app.selected?.archived != true,
              app.composer == lastApplied else { stop(); return }
        let text = transcript.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return }
        let separator = base.isEmpty || base.last?.isWhitespace == true ? "" : " "
        let updated = base + separator + text
        guard updated.unicodeScalars.count <= 20_000, !updated.contains("\0") else {
            stop(); error = "Сообщение достигло 20 000 символов. Продолжите диктовку в следующем сообщении."
            return
        }
        lastApplied = updated
        applying = true
        app.setComposer(updated, preservingContinuation: true)
        applying = false
    }

    /// Edits, submission and navigation own the draft from this point onward.
    /// Late recognition callbacks must never replace them or leak into another task.
    func composerChanged() { if active && !applying { stop() } }

    func finish() {
        guard active else { return }
        guard phase == .listening else { stop(); return }
        phase = .finishing; level = 0
        speech.finish()
        let token = token
        finishDeadline = Task { [weak self] in
            do { try await Task.sleep(for: .seconds(3)) } catch { return }
            guard let self, self.token == token else { return }
            self.stop()
        }
    }

    func stop() {
        token = UUID(); finishDeadline?.cancel(); finishDeadline = nil
        speech.cancel(); phase = .idle; level = 0
        conversationID = nil; base = ""; lastApplied = ""
    }

    func clearError() { error = nil }

    func shutdown() {
        stop()
        observers.forEach(NSWorkspace.shared.notificationCenter.removeObserver); observers = []
    }
}
