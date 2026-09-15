import SwiftUI

struct DictationButton: View {
    @ObservedObject var app: AppModel
    @ObservedObject var dictation: DictationModel
    @ObservedObject var voice: LiveVoiceModel

    var body: some View {
        Button { Task { await dictation.toggle(app: app) } } label: {
            Image(systemName: dictation.active ? "stop.circle.fill" : "mic")
                .font(.system(size: 17))
                .foregroundStyle(dictation.active ? NativeTheme.accent : .secondary)
                .frame(width: 28, height: 32)
        }.buttonStyle(.nativeHover)
            .disabled(!dictation.active && !dictation.canStart(app: app))
            .help(voice.inCall ? "Завершите голосовой разговор, чтобы диктовать текст"
                  : dictation.active ? "Закончить диктовку" : "Диктовать сообщение · " + dictation.language.title)
            .accessibilityLabel(dictation.active ? "Закончить диктовку" : "Диктовка сообщения")
    }
}

struct DictationStatusView: View {
    @ObservedObject var dictation: DictationModel

    var body: some View {
        if dictation.active || dictation.error != nil {
            HStack(spacing: 8) {
                if dictation.active {
                    Image(systemName: "mic.fill")
                    Text(dictation.phase == .preparing ? "Подключаю микрофон…"
                         : dictation.phase == .finishing ? "Завершаю диктовку…" : "Слушаю · " + dictation.language.title)
                    Spacer(minLength: 4)
                    HStack(spacing: 3) {
                        ForEach(0..<6) { index in
                            Capsule().fill(dictation.level > Double(index) / 6 ? Color.primary : Color.primary.opacity(0.15))
                                .frame(width: 3, height: 5 + Double(index % 3) * 3)
                        }
                    }.accessibilityHidden(true)
                } else if let error = dictation.error {
                    Text(error).fixedSize(horizontal: false, vertical: true)
                    Spacer(minLength: 0)
                    Button { dictation.clearError() } label: { Image(systemName: "xmark") }
                        .buttonStyle(.nativeHover).accessibilityLabel("Скрыть сообщение о диктовке")
                }
            }.font(.system(size: 11)).foregroundStyle(.secondary).padding(.horizontal, 16).padding(.vertical, 8)
        }
    }
}

struct DictationSettings: View {
    @ObservedObject var dictation: DictationModel

    var body: some View {
        Picker("Язык", selection: Binding(get: { dictation.language }, set: dictation.setLanguage)) {
            ForEach(DictationLanguage.allCases) { Text($0.title).tag($0) }
        }
        Text("Микрофон в поле сообщения набирает текст. Отправляете его вы; API-ключ и лимиты ChatGPT для диктовки не нужны.")
            .font(.callout).foregroundStyle(.secondary)
        Text("Распознавание выполняет Apple: на устройстве, если язык поддерживает этот режим, иначе — на серверах Apple. Аудиозапись в Proto-Mind не сохраняется.")
            .font(.caption).foregroundStyle(.secondary)
    }
}
