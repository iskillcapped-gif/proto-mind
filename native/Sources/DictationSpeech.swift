import AVFoundation
import Speech

@MainActor
protocol DictationRecognizing: AnyObject {
    var onText: ((String, Bool) -> Void)? { get set }
    var onLevel: ((Double) -> Void)? { get set }
    var onFailure: ((String) -> Void)? { get set }
    func start(locale: Locale) async throws
    func finish()
    func cancel()
}

@MainActor
protocol DictationAudioSource: AnyObject {
    var onPCM: ((Data) -> Void)? { get set }
    var onFailure: ((String) -> Void)? { get set }
    var captureIsFlowing: Bool { get }
    func requestAccess() async -> Bool
    func start() async throws
    func stop()
}

extension LiveVoiceAudio: DictationAudioSource {
    func requestAccess() async -> Bool { await Self.requestMicrophone() }
}

/// Apple Speech receives only the microphone stream of this explicit dictation.
/// Reuse the validated microphone channel mapping and device recovery from Live.
@MainActor
final class DictationSpeech: DictationRecognizing {
    var onText: ((String, Bool) -> Void)?
    var onLevel: ((Double) -> Void)?
    var onFailure: ((String) -> Void)?
    private let audio: DictationAudioSource
    private var recognizer: SFSpeechRecognizer?
    private var request: SFSpeechAudioBufferRecognitionRequest?
    private var task: SFSpeechRecognitionTask?
    private var events: DictationSpeechEvents?
    private var transcript = DictationTranscript()
    private var generation = UUID()
    private var monitor: Task<Void, Never>?
    private var receivingAudio = false

    init(audio: DictationAudioSource? = nil) { self.audio = audio ?? LiveVoiceAudio() }

    func start(locale: Locale) async throws {
        cancel()
        let token = generation
        guard let recognizer = SFSpeechRecognizer(locale: locale) else {
            throw NativeError.message(L10n.text("Этот язык диктовки недоступен. Выберите другой в настройках голоса."))
        }
        let authorization = await Self.authorization()
        try validate(token)
        guard authorization == .authorized else {
            throw NativeError.message(L10n.text("Разрешите распознавание речи для Proto-Mind: Настройки macOS → Конфиденциальность и безопасность → Распознавание речи."))
        }
        let microphone = await audio.requestAccess()
        try validate(token)
        guard microphone else {
            throw NativeError.message(L10n.text("Разрешите микрофон для Proto-Mind в настройках конфиденциальности macOS."))
        }
        guard recognizer.isAvailable else {
            throw NativeError.message(L10n.text("Диктовка Apple пока недоступна. Проверьте подключение к интернету или выберите другой язык."))
        }
        let request = SFSpeechAudioBufferRecognitionRequest()
        request.shouldReportPartialResults = true
        request.taskHint = .dictation
        request.addsPunctuation = true
        request.requiresOnDeviceRecognition = recognizer.supportsOnDeviceRecognition
        self.request = request; self.recognizer = recognizer; receivingAudio = true
        audio.onPCM = { [weak self] data in
            guard let self, self.generation == token, self.receivingAudio else { return }
            guard let buffer = Self.pcmBuffer(data) else { return }
            self.onLevel?(LiveVoiceSignal.level(data))
            self.request?.append(buffer)
        }
        audio.onFailure = { [weak self] message in
            guard let self, self.generation == token else { return }
            self.fail(message)
        }
        // The result-handler API starts a new bestTranscription after a pause,
        // even with isFinal == false. The delegate distinguishes an utterance
        // ending from the entire recognition task ending.
        recognizer.queue = .main
        let events = DictationSpeechEvents { [weak self] event in
            DispatchQueue.main.async {
                guard let self, self.generation == token else { return }
                switch event {
                case .partial(let text):
                    self.transcript.hypothesize(text)
                    self.onText?(self.transcript.text, false)
                case .utterance(let text):
                    self.transcript.completeUtterance(text)
                    self.onText?(self.transcript.text, false)
                case .finished(let failure):
                    if let failure {
                        self.fail(L10n.text("Не удалось закончить диктовку. Уже распознанный текст сохранён. ") + String(failure.prefix(200)))
                    } else {
                        let text = self.transcript.text
                        self.cancel()
                        self.onText?(text, true)
                    }
                }
            }
        }
        self.events = events
        task = recognizer.recognitionTask(with: request, delegate: events)
        do {
            try await audio.start()
            try validate(token)
        } catch {
            if generation == token { cancel() }
            throw error
        }
        monitor = Task { [weak self] in
            while !Task.isCancelled {
                do { try await Task.sleep(for: .seconds(1)) } catch { return }
                guard let self, self.generation == token, self.receivingAudio else { return }
                if !self.audio.captureIsFlowing {
                    self.fail(L10n.text("Микрофон перестал передавать звук. Распознанный текст сохранён; можно включить диктовку снова."))
                    return
                }
            }
        }
    }

    func finish() {
        receivingAudio = false
        audio.stop(); monitor?.cancel(); monitor = nil
        request?.endAudio()
    }

    func cancel() {
        generation = UUID(); receivingAudio = false
        audio.stop(); monitor?.cancel(); monitor = nil
        task?.cancel(); task = nil; request = nil; recognizer = nil
        events = nil; transcript = DictationTranscript()
    }

    private func fail(_ message: String) { cancel(); onFailure?(message) }

    private func validate(_ token: UUID) throws {
        try Task.checkCancellation()
        guard generation == token else { throw CancellationError() }
    }

    private static func authorization() async -> SFSpeechRecognizerAuthorizationStatus {
        let status = SFSpeechRecognizer.authorizationStatus()
        guard status == .notDetermined else { return status }
        return await withCheckedContinuation { continuation in
            SFSpeechRecognizer.requestAuthorization { continuation.resume(returning: $0) }
        }
    }

    static func pcmBuffer(_ data: Data) -> AVAudioPCMBuffer? {
        guard !data.isEmpty, data.count % 2 == 0, data.count <= 1_048_576,
              let format = AVAudioFormat(commonFormat: .pcmFormatInt16, sampleRate: 24_000, channels: 1, interleaved: true),
              let buffer = AVAudioPCMBuffer(pcmFormat: format, frameCapacity: AVAudioFrameCount(data.count / 2)),
              let destination = buffer.int16ChannelData?[0] else { return nil }
        buffer.frameLength = AVAudioFrameCount(data.count / 2)
        data.withUnsafeBytes { source in
            if let address = source.baseAddress { memcpy(destination, address, data.count) }
        }
        return buffer
    }
}

/// Only the current utterance is revisable. Text equality is deliberately not
/// used to find boundaries: repeating the same sentence is valid dictation.
struct DictationTranscript {
    private var completed: [String] = []
    private var partial = ""
    var text: String { (completed + [partial]).filter { !$0.isEmpty }.joined(separator: " ") }

    mutating func hypothesize(_ text: String) {
        let text = text.trimmingCharacters(in: .whitespacesAndNewlines)
        if !text.isEmpty { partial = text }
    }

    mutating func completeUtterance(_ text: String) {
        let text = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return }
        completed.append(text)
        partial = ""
    }
}

private final class DictationSpeechEvents: NSObject, SFSpeechRecognitionTaskDelegate {
    enum Event: Sendable {
        case partial(String), utterance(String), finished(String?)
    }
    private let receive: @Sendable (Event) -> Void
    init(receive: @escaping @Sendable (Event) -> Void) { self.receive = receive }

    func speechRecognitionTask(_ task: SFSpeechRecognitionTask, didHypothesizeTranscription transcription: SFTranscription) {
        receive(.partial(transcription.formattedString))
    }

    func speechRecognitionTask(_ task: SFSpeechRecognitionTask, didFinishRecognition result: SFSpeechRecognitionResult) {
        receive(.utterance(result.bestTranscription.formattedString))
    }

    func speechRecognitionTask(_ task: SFSpeechRecognitionTask, didFinishSuccessfully successfully: Bool) {
        receive(.finished(successfully ? nil : (task.error?.localizedDescription ?? L10n.text("Распознавание прервано."))))
    }

    func speechRecognitionTaskWasCancelled(_ task: SFSpeechRecognitionTask) {
        receive(.finished(L10n.text("Распознавание отменено системой.")))
    }
}
