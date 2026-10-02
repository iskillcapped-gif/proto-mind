import SwiftUI

struct DictationButton: View {
    @ObservedObject var app: AppModel
    @ObservedObject var dictation: DictationModel
    @ObservedObject var voice: LiveVoiceModel
    var conversationID: UUID? = nil
    @Environment(\.workspacePresentations) private var presentations
    private var id: UUID? { conversationID ?? app.selectedID }
    private var active: Bool { dictation.active && dictation.conversationID == id }

    var body: some View {
        Button { Task { await dictation.toggle(app: app, conversationID: id, in: presentations) } } label: {
            Image(systemName: active ? "stop.circle.fill" : "mic")
                .font(.system(size: 17))
                .foregroundStyle(active ? NativeTheme.accent : .secondary)
                .frame(width: 28, height: 32)
        }.buttonStyle(.nativeHover)
            .disabled(!active && !dictation.canStart(app: app, conversationID: id, in: presentations))
            .help(voice.inCall ? L10n.text("Завершите голосовой разговор, чтобы диктовать текст")
                  : active ? L10n.text("Закончить диктовку") : L10n.text("Диктовать сообщение · ") + dictation.language.title)
            .accessibilityLabel(active ? L10n.text("Закончить диктовку") : L10n.text("Диктовка сообщения"))
    }
}

struct DictationStatusView: View {
    @ObservedObject var dictation: DictationModel

    var body: some View {
        if dictation.active || dictation.error != nil {
            HStack(spacing: 8) {
                if dictation.active {
                    Image(systemName: "mic.fill")
                    Text(dictation.phase == .preparing ? L10n.text("Подключаю микрофон…")
                         : dictation.phase == .finishing ? L10n.text("Завершаю диктовку…") : L10n.text("Слушаю · ") + dictation.language.title)
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
                        .buttonStyle(.nativeHover).accessibilityLabel(L10n.text("Скрыть сообщение о диктовке"))
                }
            }.font(.system(size: 11)).foregroundStyle(.secondary).padding(.horizontal, 16).padding(.vertical, 8)
        }
    }
}

struct DictationSettings: View {
    @ObservedObject var dictation: DictationModel

    var body: some View {
        Picker(L10n.text("Язык"), selection: Binding(get: { dictation.language }, set: dictation.setLanguage)) {
            ForEach(DictationLanguage.allCases) { Text($0.title).tag($0) }
        }
    }
}
