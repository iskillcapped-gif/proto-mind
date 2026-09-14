import AVFoundation
import Foundation

/// Conversion runs off the audio render thread with a small bounded backlog.
private final class LiveVoiceCapture: @unchecked Sendable {
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
              let converter = AVAudioConverter(from: input, to: format) else { throw NativeError.message("Не удалось настроить формат микрофона.") }
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
    private var engine: AVAudioEngine?
    private var player: AVAudioPlayerNode?
    private var capture: LiveVoiceCapture?
    private var queuedFrames = 0
    private var generation = UUID()
    private var observer: NSObjectProtocol?
    private let playbackFormat = AVAudioFormat(commonFormat: .pcmFormatFloat32, sampleRate: 24_000, channels: 1, interleaved: false)!

    static func requestMicrophone() async -> Bool {
        switch AVCaptureDevice.authorizationStatus(for: .audio) {
        case .authorized: return true
        case .notDetermined: return await AVCaptureDevice.requestAccess(for: .audio)
        default: return false
        }
    }

    func start() throws {
        stop()
        let generation = UUID(); self.generation = generation
        let engine = AVAudioEngine()
        let input = engine.inputNode
        try input.setVoiceProcessingEnabled(true)
        let format = input.outputFormat(forBus: 0)
        guard format.sampleRate > 0, format.channelCount > 0 else { throw NativeError.message("Микрофон недоступен.") }
        let capture = try LiveVoiceCapture(input: format, onPCM: { [weak self] bytes in
            Task { @MainActor in
                guard let self, self.generation == generation else { return }
                self.onPCM?(bytes)
            }
        }, onFailure: { [weak self] in
            Task { @MainActor in
                guard let self, self.generation == generation else { return }
                self.onFailure?("Не удалось обработать звук микрофона. Попробуйте снова подключить аудиоустройство.")
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
                self.onFailure?("Аудиоустройство изменилось. Подключите голос снова.")
            }
        }
    }

    func play(_ data: Data) throws {
        guard let player, !data.isEmpty else { return }
        guard data.count % 2 == 0, data.count <= 192_000 else { throw NativeError.message("Неверный формат звука GPT Live.") }
        let frames = data.count / 2
        guard queuedFrames + frames <= 24_000 * 5 else { throw NativeError.message("Воспроизведение отстаёт. Голос остановлен, чтобы не проигрывать устаревшие ответы.") }
        guard let buffer = AVAudioPCMBuffer(pcmFormat: playbackFormat, frameCapacity: AVAudioFrameCount(frames)),
              let samples = buffer.floatChannelData?[0] else { throw NativeError.message("Не удалось подготовить звук.") }
        buffer.frameLength = AVAudioFrameCount(frames)
        data.withUnsafeBytes { bytes in
            for index in 0..<frames {
                let value = bytes.loadUnaligned(fromByteOffset: index * 2, as: Int16.self).littleEndian
                samples[index] = Float(value) / 32768
            }
        }
        queuedFrames += frames
        let generation = generation
        player.scheduleBuffer(buffer, completionCallbackType: .dataPlayedBack) { [weak self] _ in
            Task { @MainActor in
                guard let self, self.generation == generation else { return }
                self.queuedFrames -= frames
            }
        }
    }

    func stop() {
        generation = UUID()
        if let observer { NotificationCenter.default.removeObserver(observer) }; observer = nil
        capture?.stop(); capture = nil
        if let engine { engine.inputNode.removeTap(onBus: 0); engine.stop() }
        player?.stop(); engine = nil; player = nil; queuedFrames = 0
    }
}
