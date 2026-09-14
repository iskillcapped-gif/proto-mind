import AVFoundation
import Foundation

extension NativeChecks {
    @MainActor
    static func liveVoiceAudioConversion() async throws {
        // Reproduces the Mac's unspecified nine-channel Voice Processing format.
        // Only the microphone channel has a tone; reference channels stay silent.
        for channels: AVAudioChannelCount in [1, 2, 9] {
            let layout = AVAudioChannelLayout(layoutTag: kAudioChannelLayoutTag_DiscreteInOrder | channels)!
            let format = AVAudioFormat(commonFormat: .pcmFormatFloat32, sampleRate: 48_000, interleaved: false, channelLayout: layout)
            var frames = 0, maximumLevel = 0.0, failure = false
            let capture = try LiveVoiceCapture(input: format, onPCM: { data in
                Task { @MainActor in frames += data.count / 2; maximumLevel = max(maximumLevel, LiveVoiceSignal.level(data)) }
            }, onFailure: { Task { @MainActor in failure = true } })
            for chunk in 0..<4 {
                let buffer = AVAudioPCMBuffer(pcmFormat: format, frameCapacity: 4800)!
                buffer.frameLength = 4800
                for ch in 0..<Int(channels) {
                    for frame in 0..<4800 {
                        buffer.floatChannelData![ch][frame] = ch == 0 ? Float(sin(Double(chunk * 4800 + frame) * 2 * .pi * 440 / 48_000)) * 0.2 : 0
                    }
                }
                capture.receive(buffer)
                try await Task.sleep(for: .milliseconds(25))
            }
            let deadline = Date().addingTimeInterval(3)
            while frames < 9000, !failure, Date() < deadline { try await Task.sleep(for: .milliseconds(10)) }
            try check(!failure && frames >= 9000 && frames < 10_000 && maximumLevel > 0.6,
                      "PCM microphone tone survives \(channels)-channel to 24 kHz mono conversion")
            capture.stop()
        }
        try check(LiveVoiceSignal.level(Data(count: 4800)) == 0 && LiveVoiceSignal.level(Data([1])) == 0,
                  "Microphone meter distinguishes silence and rejects incomplete PCM samples")
    }

}
