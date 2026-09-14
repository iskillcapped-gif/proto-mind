import AVFoundation
import Foundation

// Explicit hardware check only. No API call, no microphone recording to disk.
extension NativeChecks {
    @MainActor
    static func liveVoiceAudioDeviceProbe(pcm: URL) async throws {
        guard await LiveVoiceAudio.requestMicrophone() else { throw NativeError.message("Microphone permission required for the explicit device check") }
        let speech = try Data(contentsOf: pcm)
        guard !speech.isEmpty, speech.count % 2 == 0, speech.count <= 24_000 * 2 * 10 else { throw NativeError.message("Invalid synthetic speech fixture") }
        weak var currentEngine: AVAudioEngine?
        var engineCount = 0
        let audio = LiveVoiceAudio(makeEngine: { let engine = AVAudioEngine(); currentEngine = engine; engineCount += 1; return engine })
        defer { audio.stop() }
        var failure: String?, peak = 0.0
        audio.onFailure = { failure = $0 }
        audio.onPCM = { peak = max(peak, LiveVoiceSignal.level($0)) }
        for run in 1...3 {
            try await audio.start()
            try check(audio.capturedFrames > 0 && audio.captureIsFlowing, "Device start \(run) waits for actual microphone frames")
            let oldCount = engineCount
            let before = audio.capturedFrames
            if run == 2 { currentEngine!.stop() }
            NotificationCenter.default.post(name: .AVAudioEngineConfigurationChange, object: currentEngine!)
            try await Task.sleep(for: .seconds(1))
            try check(failure == nil && audio.captureIsFlowing && audio.capturedFrames > before && engineCount == oldCount,
                      "Device run \(run) handles configuration notification without failing the call")
            for offset in stride(from: 0, to: speech.count, by: 4800) {
                try audio.play(speech.subdata(in: offset..<min(offset + 4800, speech.count)))
                try await Task.sleep(for: .milliseconds(100))
            }
            let deadline = Date().addingTimeInterval(3)
            while audio.playedFrames < speech.count / 2, failure == nil, Date() < deadline { try await Task.sleep(for: .milliseconds(50)) }
            try check(failure == nil && audio.playedFrames == speech.count / 2, "Device run \(run) confirms playback completion for synthetic speech")
            print("AUDIO DEVICE", run, "captured_frames", audio.capturedFrames, "played_frames", audio.playedFrames, "peak", peak)
            audio.stop()
            let stopped = audio.capturedFrames
            try await Task.sleep(for: .milliseconds(250))
            try check(!audio.captureIsFlowing && audio.capturedFrames == stopped && currentEngine == nil,
                      "Device run \(run) releases its engine and stops delivering microphone frames after hangup")
        }
    }
}
