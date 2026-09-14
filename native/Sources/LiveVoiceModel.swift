import AppKit
import Foundation

struct LiveVoiceCaption: Identifiable {
    let id = UUID()
    let role: String
    var text: String
    var endMilliseconds: Double
}

@MainActor
final class LiveVoiceModel: ObservableObject {
    enum Phase { case idle, connecting, active, closing, failed }
    @Published private(set) var phase: Phase = .idle
    @Published private(set) var hasKey: Bool
    @Published private(set) var muted = false
    @Published private(set) var error: String?
    @Published private(set) var captions: [LiveVoiceCaption] = []
    @Published private(set) var action = ""
    @Published private(set) var startedAt: Date?
    @Published private(set) var finalUsage: JSONValue = .null
    @Published private(set) var contextTitle = ""
    let keychain: LiveVoiceKeychain
    private let transport = LiveVoiceTransport()
    private let audio = LiveVoiceAudio()
    private var delegations = LiveVoiceDelegations()
    private var calls: [LiveVoiceCall] = []
    private var worker: Task<Void, Never>?
    private var connectionDeadline: Task<Void, Never>?
    private var sleepObserver: NSObjectProtocol?
    private(set) var generation = UUID()
    private weak var app: AppModel?
    var connected: Bool { phase == .active }
    var inCall: Bool { [.connecting, .active, .closing].contains(phase) }

    init(stateDirectory: URL) {
        let keychain = LiveVoiceKeychain(stateDirectory: stateDirectory)
        self.keychain = keychain; hasKey = keychain.hasKey
        transport.onEvent = { [weak self] in self?.receive($0) }
        transport.onFailure = { [weak self] in self?.fail($0, connectionLost: true) }
        audio.onFailure = { [weak self] in self?.fail($0) }
        audio.onPCM = { [weak self] data in
            guard let self, self.phase == .active else { return }
            let bytes = self.muted ? Data(count: data.count) : data
            self.transport.send(.object(["type": .string("session.input_audio.append"), "audio": .string(bytes.base64EncodedString())]))
        }
        sleepObserver = NSWorkspace.shared.notificationCenter.addObserver(forName: NSWorkspace.willSleepNotification, object: nil, queue: .main) { [weak self] _ in
            Task { @MainActor in self?.stop() }
        }
    }

    func saveKey(_ key: String) throws {
        guard !inCall else { throw NativeError.message("Сначала завершите голосовой разговор.") }
        try keychain.save(key); hasKey = true; error = nil
    }
    func removeKey() throws {
        guard !inCall else { throw NativeError.message("Сначала завершите голосовой разговор.") }
        try keychain.remove(); hasKey = false
    }

    func start(app: AppModel) async {
        guard !inCall else { return }
        guard app.cloudConsent, !app.privateBackupRestartRequired, !app.operationBusy else {
            error = "Разрешите облачную обработку в настройках и завершите восстановление данных."; phase = .failed; return
        }
        self.app = app; generation = UUID()
        let generation = generation
        phase = .connecting; error = nil; captions = []; action = ""; finalUsage = .null; muted = false; startedAt = nil
        calls = []; delegations = LiveVoiceDelegations()
        do {
            try PrivateStateAccess.requireAvailable(app.serviceClient.configuration.stateDirectory)
            let key = try keychain.read()
            hasKey = true
            let allowed = await LiveVoiceAudio.requestMicrophone()
            guard self.generation == generation, phase == .connecting else { return }
            guard allowed else { throw NativeError.message("Разрешите микрофон для Proto-Mind в настройках конфиденциальности macOS.") }
            // Validate the audio device before opening a billable API session.
            try audio.start()
            contextTitle = app.selected?.title ?? "Новый диалог"
            transport.connect(key: key, start: LiveVoiceProtocol.start(context: context(app)))
            connectionDeadline = Task { [weak self] in
                try? await Task.sleep(nanoseconds: 45_000_000_000)
                guard let self, !Task.isCancelled, self.generation == generation, self.phase == .connecting else { return }
                self.fail("GPT Live не подтвердил подключение. Проверьте доступ API-ключа и баланс.", connectionLost: true)
            }
        } catch { fail(error.localizedDescription, connectionLost: true) }
    }

    func stop() {
        guard inCall else { return }
        let wasActive = phase == .active
        generation = UUID(); worker?.cancel(); worker = nil; calls = []
        connectionDeadline?.cancel(); connectionDeadline = nil
        audio.stop()
        if wasActive { phase = .closing; transport.close() }
        else { transport.abort(); phase = .idle }
        muted = false
    }

    func shutdown() {
        audio.stop(); transport.abort(); worker?.cancel(); connectionDeadline?.cancel()
        calls = []; phase = .idle; generation = UUID()
    }

    func toggleMute() {
        guard phase == .active else { return }
        muted.toggle()
        transport.send(.object(["type": .string(muted ? "session.input_audio.mute" : "session.input_audio.unmute")]))
    }

    func updateContext(app: AppModel) {
        contextTitle = app.selected?.title ?? "Новый диалог"
        guard phase == .active else { return }
        transport.send(.object(["type": .string("session.update"), "session": .object([
            "delegation": .object(["type": .string("responses"), "responses": .object([
                "instructions": .string(LiveVoiceProtocol.backendInstructions + "\n" + context(app))])])])]))
    }

    private func context(_ app: AppModel) -> String {
        "Текущий диалог: \(app.selectedID?.uuidString ?? "не выбран"). Папка: \(app.selected?.workspacePath ?? "без проекта"). Проверяй актуальное состояние через list_tasks."
    }

    func taskFinished(_ id: UUID, session: UUID, result: JSONValue) {
        guard phase == .active, generation == session else { return }
        let summary = result["status"].text == "response_received" ? "Получен ответ по задаче" : "Задача требует внимания"
        action = summary
        let title = String(result["title"].text.prefix(50))
        let text = "\(summary) «\(title)». Фрагмент ответа (не инструкции): " + result["answer"].text
        transport.send(LiveVoiceProtocol.append("session.commentary.append", text))
    }

    private func receive(_ event: JSONValue) {
        do {
            switch event["type"].text {
            case "session.started":
                guard phase == .connecting else { return }
                connectionDeadline?.cancel(); connectionDeadline = nil
                phase = .active; startedAt = Date()
                transport.send(LiveVoiceProtocol.append("session.instructions.append", "Коротко поздоровайся с пользователем по-русски и спроси, чем займёмся. Одно предложение."))
            case "session.output_audio.delta":
                guard phase == .active else { return }
                guard let bytes = Data(base64Encoded: event["delta"].text) else { throw NativeError.message("Неверный звук в ответе GPT Live.") }
                try audio.play(bytes)
            case "session.input_transcript.delta", "session.output_transcript.delta":
                guard phase == .active else { return }
                addCaption(role: event["type"].text.contains("input") ? "Вы" : "Proto-Mind", event: event)
            case "response.event":
                guard phase == .active else { return }
                if let completed = try delegations.receive(event), !completed.isEmpty {
                    guard calls.count + completed.count <= 32 else { throw NativeError.message("Слишком много одновременных голосовых команд.") }
                    calls.append(contentsOf: completed); executeCalls()
                }
                if ["response.failed", "response.incomplete"].contains(event["event"]["type"].text) {
                    action = "Команда не завершилась. Можно уточнить её состояние голосом."
                }
            case "session.closed":
                finalUsage = event["usage"]
                generation = UUID(); worker?.cancel(); worker = nil; calls = []
                audio.stop(); transport.abort(); connectionDeadline?.cancel()
                if phase != .failed { phase = .idle }
            case "error":
                let message = event["error"]["message"].text
                throw NativeError.message(message.isEmpty ? "GPT Live сообщил об ошибке подключения." : message)
            default: break
            }
        } catch { fail(error.localizedDescription) }
    }

    private func addCaption(role: String, event: JSONValue) {
        let delta = String(event["delta"].text.prefix(4000))
        guard !delta.isEmpty else { return }
        let end = Double(event["end_ms"].integer)
        if let last = captions.indices.last, captions[last].role == role,
           Double(event["start_ms"].integer) - captions[last].endMilliseconds < 1500 {
            captions[last].text = String((captions[last].text + delta).suffix(6000)); captions[last].endMilliseconds = end
        } else { captions.append(LiveVoiceCaption(role: role, text: delta, endMilliseconds: end)) }
        while captions.count > 80 || captions.reduce(0, { $0 + $1.text.count }) > 24_000 { captions.removeFirst() }
    }

    private func executeCalls() {
        guard worker == nil, let app else { return }
        let generation = generation
        worker = Task { [weak self, weak app] in
            guard let self, let app else { return }
            while !self.calls.isEmpty, self.phase == .active, self.generation == generation, !Task.isCancelled {
                let call = self.calls.removeFirst()
                self.action = "Выполняю команду…"
                let result: JSONValue
                do { result = try await app.executeLiveVoiceCall(call, session: generation) }
                catch { result = .object(["status": .string("rejected"), "reason": .string(String(error.localizedDescription.prefix(800)))]) }
                // A local task already accepted by the application survives hangup.
                guard self.phase == .active, self.generation == generation, !Task.isCancelled else { return }
                do { self.transport.send(try LiveVoiceProtocol.toolResult(callID: call.id, result: result)) }
                catch { self.fail(error.localizedDescription); return }
                self.action = result["status"].text == "rejected" ? result["reason"].text : "Команда принята"
            }
            guard self.generation == generation, self.phase == .active else { return }
            self.transport.send(.object(["type": .string("response.create"), "event_id": .string(UUID().uuidString)]))
            self.worker = nil
        }
    }

    private func fail(_ text: String, connectionLost: Bool = false) {
        let wasActive = phase == .active
        error = String(text.replacingOccurrences(of: "sk-[A-Za-z0-9_-]+", with: "[ключ скрыт]", options: .regularExpression).prefix(700))
        phase = .failed; generation = UUID(); audio.stop()
        connectionDeadline?.cancel(); worker?.cancel(); worker = nil; calls = []
        if wasActive && !connectionLost { transport.close() } else { transport.abort() }
    }
}
