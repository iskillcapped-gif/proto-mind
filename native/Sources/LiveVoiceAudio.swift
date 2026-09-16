import AVFoundation
import Foundation
import OSLog

/// Conversion runs off the audio render thread with a small bounded backlog.
final class LiveVoiceCapture: @unchecked Sendable {
    private let queue = DispatchQueue(label: "local.proto-mind.live.capture", qos: .userInitiated)
    private let lock = NSLock()
    private var pending = 0
    private var stopped = false
    let converter: AVAudioConverter
    let format: AVAudioFormat
    let onPCM: (Data) -> Void
    let onFailure: () -> Void

    init(input: AVAudioFormat, onPCM: @escaping (Data) -> Void, onFailure: @escaping () -> Void) throws {
        guard let format = AVAudioFormat(commonFormat: .pcmFormatInt16, sampleRate: 24_000, channels: 1, interleaved: true),
              let converter = AVAudioConverter(from: input, to: format) else { throw NativeError.message(L10n.text("Не удалось настроить формат микрофона.")) }
        // Voice Processing I/O on macOS can expose a multichannel client format
        // without a standard channel layout. The default converter map may then
        // select no source for mono and silently produce zeros. The processed
        // microphone is channel zero; select it explicitly instead of downmixing
        // an unspecified layout (which may also contain reference channels).
        converter.channelMap = [0]
        self.format = format; self.converter = converter; self.onPCM = onPCM; self.onFailure = onFailure
    }

    func stop() { lock.lock(); stopped = true; lock.unlock() }

    func receive(_ source: AVAudioPCMBuffer) {
        lock.lock()
        guard !stopped, pending < 8 else {
            let failed = !stopped; stopped = true; lock.unlock()
            if failed { onFailure() }; return
        }
        pending += 1; lock.unlock()
        guard let copy = AVAudioPCMBuffer(pcmFormat: source.format, frameCapacity: source.frameLength) else {
            finish(); onFailure(); return
        }
        copy.frameLength = source.frameLength
        let original = UnsafeMutableAudioBufferListPointer(UnsafeMutablePointer(mutating: source.audioBufferList))
        let destination = UnsafeMutableAudioBufferListPointer(copy.mutableAudioBufferList)
        for (src, dst) in zip(original, destination) {
            if let from = src.mData, let to = dst.mData { memcpy(to, from, Int(src.mDataByteSize)) }
        }
        queue.async { [self] in
            defer { finish() }
            lock.lock(); let active = !stopped; lock.unlock()
            guard active else { return }
            let capacity = AVAudioFrameCount(ceil(Double(copy.frameLength) * 24_000 / copy.format.sampleRate)) + 32
            guard let output = AVAudioPCMBuffer(pcmFormat: format, frameCapacity: capacity) else { onFailure(); return }
            var supplied = false
            var error: NSError?
            let status = converter.convert(to: output, error: &error) { _, state in
                if supplied { state.pointee = .noDataNow; return nil }
                supplied = true; state.pointee = .haveData; return copy
            }
            guard status != .error, error == nil else { onFailure(); return }
            if output.frameLength > 0, let bytes = output.int16ChannelData?[0] {
                onPCM(Data(bytes: bytes, count: Int(output.frameLength) * 2))
            }
        }
    }
    private func finish() { lock.lock(); pending -= 1; lock.unlock() }
}

@MainActor
final class LiveVoiceAudio {
    var onPCM: ((Data) -> Void)?
    var onFailure: ((String) -> Void)?
    var onPlaybackLevel: ((Double) -> Void)?
    private var engine: AVAudioEngine?
    private var player: AVAudioPlayerNode?
    private var capture: LiveVoiceCapture?
    private var queuedFrames = 0
    private var playbackLevels: [Double] = []
    private var generation = UUID()
    private var playbackGeneration = UUID()
    private var observer: NSObjectProtocol?
    private var recovery: Task<Void, Never>?
    private var recovering = false
    private var recoveryTimes: [Date] = []
    private var enabled = false
    private var captureSession = UUID()
    private var lastCapture: Date?
    private(set) var capturedFrames = 0
    private(set) var playedFrames = 0
    private let playbackFormat = AVAudioFormat(commonFormat: .pcmFormatFloat32, sampleRate: 24_000, channels: 1, interleaved: false)!
    private let makeEngine: () -> AVAudioEngine
    private let logger = Logger(subsystem: "local.proto-mind.native", category: "voice-audio")

    init(makeEngine: @escaping () -> AVAudioEngine = { AVAudioEngine() }) { self.makeEngine = makeEngine }

    static func requestMicrophone() async -> Bool {
        switch AVCaptureDevice.authorizationStatus(for: .audio) {
        case .authorized: return true
        case .notDetermined: return await AVCaptureDevice.requestAccess(for: .audio)
        default: return false
        }
    }

    func start() async throws {
        stop()
        let session = UUID(); captureSession = session
        enabled = true; capturedFrames = 0; playedFrames = 0; recoveryTimes = []
        do {
            try startEngine()
            // A started engine can still fail to render. Do not open the paid
            // network session until real capture callbacks arrive, even silence.
            let deadline = Date().addingTimeInterval(5)
            while enabled, captureSession == session, capturedFrames == 0, Date() < deadline {
                try await Task.sleep(for: .milliseconds(50))
            }
            try Task.checkCancellation()
            guard captureSession == session else { throw CancellationError() }
            guard enabled, capturedFrames > 0 else { throw NativeError.message(L10n.text("Микрофон не передаёт звук. Проверьте выбранное устройство в настройках macOS.")) }
        } catch { if captureSession == session { stop() }; throw error }
    }

    private func startEngine() throws {
        let generation = UUID(); self.generation = generation
        let engine = makeEngine()
        let input = engine.inputNode
        try input.setVoiceProcessingEnabled(true)
        let format = input.outputFormat(forBus: 0)
        logger.info("Preparing voice audio: \(format.channelCount) input channels at \(format.sampleRate) Hz")
        guard format.sampleRate > 0, format.channelCount > 0 else { throw NativeError.message(L10n.text("Микрофон недоступен.")) }
        let capture = try LiveVoiceCapture(input: format, onPCM: { [weak self] bytes in
            Task { @MainActor in
                guard let self, self.generation == generation else { return }
                self.lastCapture = Date(); self.capturedFrames += bytes.count / 2
                self.onPCM?(bytes)
            }
        }, onFailure: { [weak self] in
            Task { @MainActor in
                guard let self, self.generation == generation else { return }
                self.onFailure?(L10n.text("Не удалось обработать звук микрофона. Попробуйте снова подключить аудиоустройство."))
            }
        })
        let mutedInput = AVAudioMixerNode()
        engine.attach(mutedInput)
        engine.connect(input, to: mutedInput, format: format)
        mutedInput.outputVolume = 0
        engine.connect(mutedInput, to: engine.mainMixerNode, format: format)
        engine.connect(engine.mainMixerNode, to: engine.outputNode, format: format)
        let player = AVAudioPlayerNode()
        engine.attach(player)
        engine.connect(player, to: engine.mainMixerNode, format: playbackFormat)
        input.installTap(onBus: 0, bufferSize: 1024, format: format) { buffer, _ in capture.receive(buffer) }
        self.engine = engine; self.capture = capture; self.player = player
        do { engine.prepare(); try engine.start(); player.play() }
        catch { stop(); throw error }
        observer = NotificationCenter.default.addObserver(forName: .AVAudioEngineConfigurationChange, object: engine, queue: .main) { [weak self] _ in
            Task { @MainActor in
                guard let self, self.generation == generation else { return }
                self.configurationChanged()
            }
        }
    }

    /// Notifications can be queued by our own Voice Processing setup. Recheck
    /// the engine after the notification returns rather than destroying it in
    /// Core Audio's callback. Recover the local graph without restarting Live.
    private func configurationChanged() {
        guard enabled, recovery == nil else { return }
        recovery = Task { [weak self] in
            try? await Task.sleep(for: .milliseconds(200))
            guard let self, !Task.isCancelled, self.enabled else { return }
            self.recovery = nil
            // A running graph may still be warming up. Capture health has its
            // own deadline; a notification alone must not restart that graph.
            if self.engine?.isRunning == true { return }
            self.recoveryTimes.removeAll { Date().timeIntervalSince($0) > 5 }
            guard self.recoveryTimes.count < 3 else {
                self.onFailure?(L10n.text("Не удалось стабилизировать аудиоустройство. Проверьте микрофон и наушники в настройках macOS.")); return
            }
            self.recoveryTimes.append(Date()); self.recovering = true
            do {
                if let engine = self.engine, let capture = self.capture,
                   engine.inputNode.outputFormat(forBus: 0) == capture.converter.inputFormat {
                    // Voice Processing can stop its engine while settling the
                    // aggregate device, without changing the client format.
                    // Recreating it here repeats that negotiation indefinitely.
                    self.logger.info("Restarting the existing voice audio graph after configuration change")
                    self.clearPlayback()
                    engine.prepare(); try engine.start(); self.player?.play()
                } else {
                    self.logger.info("Rebuilding voice audio for a changed microphone format")
                    self.releaseEngine(); try self.startEngine()
                }
            }
            catch { self.onFailure?(L10n.format("Не удалось переподключить аудиоустройство: \(error.localizedDescription)")) }
            self.recovering = false
        }
    }

    var captureIsFlowing: Bool {
        enabled && (recovering || recovery != nil || lastCapture.map { Date().timeIntervalSince($0) < 3 } == true)
    }

    func play(_ data: Data) throws {
        guard let player, !data.isEmpty else { return }
        guard data.count % 2 == 0, data.count <= 192_000 else { throw NativeError.message(L10n.text("Неверный формат звука GPT Live.")) }
        let frames = data.count / 2
        guard queuedFrames + frames <= 24_000 * 5 else { throw NativeError.message(L10n.text("Воспроизведение отстаёт. Голос остановлен, чтобы не проигрывать устаревшие ответы.")) }
        guard let buffer = AVAudioPCMBuffer(pcmFormat: playbackFormat, frameCapacity: AVAudioFrameCount(frames)),
              let samples = buffer.floatChannelData?[0] else { throw NativeError.message(L10n.text("Не удалось подготовить звук.")) }
        buffer.frameLength = AVAudioFrameCount(frames)
        data.withUnsafeBytes { bytes in
            for index in 0..<frames {
                let value = bytes.loadUnaligned(fromByteOffset: index * 2, as: Int16.self).littleEndian
                samples[index] = Float(value) / 32768
            }
        }
        queuedFrames += frames
        playbackLevels.append(LiveVoiceSignal.level(data))
        if playbackLevels.count == 1 { onPlaybackLevel?(playbackLevels[0]) }
        let generation = playbackGeneration
        player.scheduleBuffer(buffer, completionCallbackType: .dataPlayedBack) { [weak self] _ in
            Task { @MainActor in
                guard let self, self.playbackGeneration == generation else { return }
                self.queuedFrames -= frames
                self.playedFrames += frames
                if !self.playbackLevels.isEmpty { self.playbackLevels.removeFirst() }
                self.onPlaybackLevel?(self.playbackLevels.first ?? 0)
            }
        }
    }

    func stop() {
        captureSession = UUID()
        enabled = false; recovery?.cancel(); recovery = nil; recovering = false
        lastCapture = nil
        releaseEngine()
    }

    private func releaseEngine() {
        generation = UUID()
        if let observer { NotificationCenter.default.removeObserver(observer) }; observer = nil
        capture?.stop(); capture = nil
        if let engine { engine.inputNode.removeTap(onBus: 0); engine.stop() }
        clearPlayback(); engine = nil; player = nil
    }

    private func clearPlayback() {
        playbackGeneration = UUID()
        player?.stop(); queuedFrames = 0
        playbackLevels.removeAll(); onPlaybackLevel?(0)
    }
}

enum LiveVoiceSignal {
    static func level(_ pcm: Data) -> Double {
        guard !pcm.isEmpty, pcm.count % 2 == 0 else { return 0 }
        let energy = pcm.withUnsafeBytes { bytes in
            stride(from: 0, to: bytes.count, by: 2).reduce(0.0) { sum, offset in
                let sample = Double(bytes.loadUnaligned(fromByteOffset: offset, as: Int16.self).littleEndian) / 32768
                return sum + sample * sample
            }
        }
        let rms = sqrt(energy / Double(pcm.count / 2))
        return min(1, max(0, (20 * log10(max(rms, 0.000_001)) + 60) / 60))
    }
}
