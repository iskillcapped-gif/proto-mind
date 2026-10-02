import SwiftUI

extension AppModel {
    /// Every voice entry uses the same one-click path. An existing call only reveals its controls.
    func presentLiveVoice(openSettings: () -> Void) {
        dictation.stop()
        guard liveVoice.inCall || (liveVoice.hasKey && cloudConsent) else {
            showLiveVoice = false
            settingsSection = .voice
            openSettings()
            return
        }
        showLiveVoice = true
        Task { await liveVoice.start(app: self) }
    }
}

struct LiveVoiceButton: View {
    @ObservedObject var app: AppModel
    @ObservedObject var voice: LiveVoiceModel
    private func openSettings() { app.openSettings() }

    var body: some View {
        Button { app.presentLiveVoice(openSettings: { openSettings() }) } label: {
            Image(systemName: voice.inCall ? "waveform.circle.fill" : "waveform")
                .font(.system(size: 16, weight: .regular))
                .foregroundStyle(voice.inCall ? NativeTheme.accent : .secondary)
                .frame(width: 28, height: 28)
        }.buttonStyle(.nativeHover)
            .help(voice.connected ? L10n.text("Голосовой разговор подключён") : voice.inCall ? L10n.text("Подключение голосового разговора") : L10n.text("Поговорить с Proto-Mind"))
            .accessibilityLabel(L10n.text("Голос Proto-Mind"))
    }
}

struct LiveVoiceView: View {
    @ObservedObject var app: AppModel
    @ObservedObject var voice: LiveVoiceModel
    private func openSettings() { app.openSettings() }

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack {
                Image(systemName: "waveform").font(.system(size: 24)).foregroundStyle(NativeTheme.accent)
                VStack(alignment: .leading, spacing: 3) {
                    Text(L10n.text("Голос Proto-Mind")).font(.system(size: 18, weight: .semibold))
                    Text("GPT Live 1").font(.caption).foregroundStyle(.secondary)
                }
                DesktopWindowDragArea().frame(maxWidth: .infinity).frame(height: 34)
                Button {
                    app.showLiveVoice = false; app.settingsSection = .voice; openSettings()
                } label: { Image(systemName: "gearshape") }
                    .buttonStyle(.nativeHover).help(L10n.text("Настройки голоса"))
                Button { app.showLiveVoice = false } label: { Image(systemName: "chevron.down") }
                    .buttonStyle(.nativeHover).help(L10n.text("Свернуть разговор"))
            }
            Group {
                Label(voice.contextTitle.isEmpty ? app.selected?.displayTitle ?? L10n.text("Новый диалог") : voice.contextTitle,
                      systemImage: "folder").font(.callout).lineLimit(2).foregroundStyle(.secondary)
                if voice.captions.isEmpty {
                    VStack(alignment: .leading, spacing: 14) {
                        Text(L10n.text("Обсудим и сделаем")).font(.system(size: 23, weight: .medium))
                        Text(L10n.text("«Открой проект…»\n«Создай задачу…»\n«Добавь к текущей задаче…»\n«Как продвигается работа?»"))
                            .font(.system(size: 15)).lineSpacing(8).foregroundStyle(.secondary)
                        Text(L10n.text("Работа выполняется выбранной моделью и с доступом соответствующего диалога."))
                            .font(.caption).foregroundStyle(.secondary)
                    }.frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .leading)
                } else {
                    ScrollViewReader { proxy in
                        ScrollView {
                            LazyVStack(alignment: .leading, spacing: 14) {
                                ForEach(voice.captions) { caption in
                                    VStack(alignment: .leading, spacing: 4) {
                                        Text(caption.role).font(.caption).foregroundStyle(.secondary)
                                        Text(caption.text).font(.system(size: 14)).lineSpacing(4).textSelection(.enabled)
                                    }.frame(maxWidth: .infinity, alignment: .leading)
                                }
                                Color.clear.frame(height: 1).id("voice-bottom")
                            }
                        }.onChange(of: voice.captions.last?.text) { _, _ in proxy.scrollTo("voice-bottom", anchor: .bottom) }
                    }
                }
            }
            if let error = voice.error {
                Text(error).font(.caption).foregroundStyle(.orange).textSelection(.enabled).fixedSize(horizontal: false, vertical: true)
            }
            if !voice.action.isEmpty, voice.connected {
                Text(voice.action).font(.caption).foregroundStyle(.secondary).lineLimit(2)
            }
            if voice.inCall {
                HStack(spacing: 8) {
                    Image(systemName: voice.muted ? "mic.slash" : "mic")
                    Text(voice.muted ? L10n.text("Микрофон выключен") : voice.connected ? L10n.text("Слушаю") : L10n.text("Подключаюсь…"))
                    Spacer()
                    HStack(alignment: .center, spacing: 3) {
                        ForEach(0..<8) { index in
                            Capsule().fill(!voice.muted && voice.inputLevel > Double(index) / 8 ? Color.primary : Color.secondary.opacity(0.2))
                                .frame(width: 3, height: 6 + Double(index % 4) * 3)
                        }
                    }.accessibilityLabel(L10n.text("Уровень микрофона")).accessibilityValue("\(Int(voice.inputLevel * 100))%")
                }.font(.caption).foregroundStyle(.secondary)
            }
            HStack(spacing: 12) {
                if voice.inCall {
                    Button { voice.toggleMute() } label: {
                        Label(voice.muted ? L10n.text("Включить микрофон") : L10n.text("Микрофон"), systemImage: voice.muted ? "mic.slash" : "mic")
                    }.disabled(!voice.connected)
                    Spacer()
                    if let started = voice.startedAt {
                        TimelineView(.periodic(from: started, by: 1)) { context in
                            Text(duration(context.date.timeIntervalSince(started))).monospacedDigit().font(.caption).foregroundStyle(.secondary)
                        }
                    }
                    Button(voice.phase == .closing ? L10n.text("Завершаю…") : L10n.text("Завершить")) { voice.stop() }
                        .tint(.red).disabled(voice.phase == .closing)
                } else {
                    Button { app.presentLiveVoice(openSettings: { openSettings() }) } label: {
                        Label(L10n.text("Начать разговор"), systemImage: "waveform").frame(maxWidth: .infinity)
                    }.buttonStyle(.borderedProminent).disabled(!voice.hasKey || !app.cloudConsent || app.operationBusy)
                }
            }.controlSize(.large)
            Text(voice.inCall
                 ? L10n.text("Можно свернуть и продолжать говорить. «Завершить» отключает голос; рабочие задачи продолжаются.")
                 : L10n.text("Микрофон и речь передаются OpenAI. $0,05/мин разговора + обработка команд API; отдельно от подписки ChatGPT."))
                .font(.system(size: 11)).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
        }.padding(22).padding(.top, 14)
            .frame(minWidth: 350, idealWidth: 410, maxWidth: .infinity, minHeight: 440, idealHeight: 545, maxHeight: .infinity)
    }

    private func duration(_ seconds: TimeInterval) -> String {
        let value = max(0, Int(seconds)); return String(format: "%d:%02d", value / 60, value % 60)
    }
}

/// Settings → Voice: the OpenAI key for voice conversations, kept in this Mac's Keychain.
struct LiveVoiceKeySettings: View {
    @ObservedObject var voice: LiveVoiceModel
    @State private var key = ""
    @State private var message: String?
    @State private var failed = false
    @State private var replacing = false

    var body: some View {
        Section {
            if voice.hasKey && !replacing {
                SettingsRow(title: L10n.text("API-ключ сохранён"), detail: L10n.pick("Хранится в Связке ключей этого Mac", "Kept in this Mac's Keychain"), symbol: "key.fill") {
                    SettingsMoreMenu {
                        Button(L10n.pick("Заменить ключ…", "Replace key…")) { replacing = true; key = ""; message = nil }
                        Divider()
                        Button(L10n.text("Удалить"), role: .destructive) {
                            do { try voice.removeKey(); message = L10n.text("Ключ удалён с этого Mac."); failed = false }
                            catch { message = error.localizedDescription; failed = true }
                        }
                    }.disabled(voice.inCall)
                }
            } else {
                SecureField(L10n.text("API-ключ OpenAI"), text: $key, prompt: Text(voice.hasKey ? L10n.text("Новый ключ для замены") : L10n.text("API-ключ OpenAI")))
                    .textFieldStyle(.roundedBorder).labelsHidden().disabled(voice.inCall).accessibilityLabel(L10n.text("API-ключ OpenAI"))
                HStack {
                    Link(L10n.text("Открыть API-ключи OpenAI"), destination: URL(string: "https://platform.openai.com/api-keys")!)
                    Spacer()
                    if replacing { Button(L10n.text("Отмена")) { replacing = false; key = "" } }
                    Button(L10n.text("Сохранить ключ")) {
                        do { try voice.saveKey(key); key = ""; replacing = false; message = nil; failed = false }
                        catch { message = error.localizedDescription; failed = true }
                    }.buttonStyle(.borderedProminent).disabled(key.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || voice.inCall)
                }
            }
            if let message { SettingsNotice(text: message, failed: failed) }
        } header: { Text(L10n.pick("Ключ OpenAI API", "OpenAI API key")) } footer: {
            SettingsFooter(L10n.text("Ключ хранится на этом Mac, отдельно от истории и резервных копий. Разговор включается только по кнопке; после запуска приложения микрофон выключен.")
                           + " " + L10n.text("Во время разговора OpenAI получает звук, названия проектов и результаты запрошенных задач.")
                           + " " + L10n.text("Реплики разговора видны до следующего звонка. Поручения и уточнения сохраняются в истории соответствующих задач; аудиозапись на диск не ведётся."))
        }
    }
}
