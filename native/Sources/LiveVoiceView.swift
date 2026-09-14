import SwiftUI

struct LiveVoiceButton: View {
    @ObservedObject var app: AppModel
    @ObservedObject var voice: LiveVoiceModel

    var body: some View {
        Button { app.showLiveVoice.toggle() } label: {
            Image(systemName: voice.inCall ? "waveform.circle.fill" : "waveform")
                .font(.system(size: 20, weight: .regular))
                .foregroundStyle(voice.inCall ? NativeTheme.accent : .secondary)
                .frame(width: 30, height: 32)
        }.buttonStyle(.nativeHover)
            .help(voice.connected ? "Голосовой разговор подключён" : voice.inCall ? "Подключение голосового разговора" : "Поговорить с Proto-Mind")
            .accessibilityLabel("Голос Proto-Mind")
    }
}

struct LiveVoiceView: View {
    @ObservedObject var app: AppModel
    @ObservedObject var voice: LiveVoiceModel
    @State private var showingKey = false

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack {
                Image(systemName: "waveform").font(.system(size: 24)).foregroundStyle(NativeTheme.accent)
                VStack(alignment: .leading, spacing: 3) {
                    Text("Голос Proto-Mind").font(.system(size: 18, weight: .semibold))
                    Text("GPT Live 1").font(.caption).foregroundStyle(.secondary)
                }
                Spacer()
                Button { showingKey.toggle() } label: { Image(systemName: "gearshape") }
                    .buttonStyle(.nativeHover).help("Настройки API-ключа")
                Button { app.showLiveVoice = false } label: { Image(systemName: "chevron.down") }
                    .buttonStyle(.nativeHover).help("Свернуть разговор")
            }
            if !voice.hasKey || showingKey {
                LiveVoiceKeySettings(voice: voice)
            } else {
                Label(voice.contextTitle.isEmpty ? app.selected?.title ?? "Новый диалог" : voice.contextTitle,
                      systemImage: "folder").font(.callout).lineLimit(2).foregroundStyle(.secondary)
                if voice.captions.isEmpty {
                    VStack(alignment: .leading, spacing: 14) {
                        Text("Обсудим и сделаем").font(.system(size: 23, weight: .medium))
                        Text("«Открой проект…»\n«Создай задачу…»\n«Добавь к текущей задаче…»\n«Как продвигается работа?»")
                            .font(.system(size: 15)).lineSpacing(8).foregroundStyle(.secondary)
                        Text("Работа выполняется выбранной моделью и с доступом соответствующего диалога.")
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
                    Text(voice.muted ? "Микрофон выключен" : voice.connected ? "Слушаю" : "Подключаюсь…")
                    Spacer()
                    HStack(alignment: .center, spacing: 3) {
                        ForEach(0..<8) { index in
                            Capsule().fill(!voice.muted && voice.inputLevel > Double(index) / 8 ? Color.primary : Color.secondary.opacity(0.2))
                                .frame(width: 3, height: 6 + Double(index % 4) * 3)
                        }
                    }.accessibilityLabel("Уровень микрофона").accessibilityValue("\(Int(voice.inputLevel * 100))%")
                }.font(.caption).foregroundStyle(.secondary)
            }
            if !app.cloudConsent { Toggle("Разрешить обработку в OpenAI", isOn: $app.cloudConsent).font(.callout) }
            HStack(spacing: 12) {
                if voice.inCall {
                    Button { voice.toggleMute() } label: {
                        Label(voice.muted ? "Включить микрофон" : "Микрофон", systemImage: voice.muted ? "mic.slash" : "mic")
                    }.disabled(!voice.connected)
                    Spacer()
                    if let started = voice.startedAt {
                        TimelineView(.periodic(from: started, by: 1)) { context in
                            Text(duration(context.date.timeIntervalSince(started))).monospacedDigit().font(.caption).foregroundStyle(.secondary)
                        }
                    }
                    Button(voice.phase == .closing ? "Завершаю…" : "Завершить") { voice.stop() }
                        .tint(.red).disabled(voice.phase == .closing)
                } else {
                    Button { Task { await voice.start(app: app) } } label: {
                        Label("Начать разговор", systemImage: "waveform").frame(maxWidth: .infinity)
                    }.buttonStyle(.borderedProminent).disabled(!voice.hasKey || !app.cloudConsent || app.operationBusy)
                }
            }.controlSize(.large)
            Text(voice.inCall
                 ? "Можно свернуть и продолжать говорить. «Завершить» отключает голос; рабочие задачи продолжаются."
                 : "Микрофон и речь передаются OpenAI. $0,05/мин разговора + обработка команд API; отдельно от подписки ChatGPT.")
                .font(.system(size: 11)).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
        }.padding(22).frame(width: 410, height: 545)
            .background(NativeTheme.composer, in: RoundedRectangle(cornerRadius: 16))
            .overlay(RoundedRectangle(cornerRadius: 16).stroke(NativeTheme.hairline))
    }

    private func duration(_ seconds: TimeInterval) -> String {
        let value = max(0, Int(seconds)); return String(format: "%d:%02d", value / 60, value % 60)
    }
}

struct LiveVoiceKeySettings: View {
    @ObservedObject var voice: LiveVoiceModel
    @State private var key = ""
    @State private var message: String?
    @State private var failed = false

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Label(voice.hasKey ? "API-ключ сохранён" : "Подключите OpenAI API", systemImage: voice.hasKey ? "key.fill" : "key")
                .font(.headline)
            SecureField(voice.hasKey ? "Новый ключ для замены" : "API-ключ OpenAI", text: $key)
                .textFieldStyle(.roundedBorder).disabled(voice.inCall).accessibilityLabel("API-ключ OpenAI")
            HStack {
                Button("Сохранить ключ") {
                    do { try voice.saveKey(key); key = ""; message = "Ключ сохранён в Связке ключей macOS."; failed = false }
                    catch { message = error.localizedDescription; failed = true }
                }.disabled(key.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || voice.inCall)
                if voice.hasKey {
                    Button("Удалить") {
                        do { try voice.removeKey(); message = "Ключ удалён с этого Mac."; failed = false }
                        catch { message = error.localizedDescription; failed = true }
                    }.disabled(voice.inCall)
                }
            }
            if let message { Text(message).font(.caption).foregroundStyle(failed ? Color.orange : .secondary) }
            Text("Ключ хранится на этом Mac, отдельно от истории и резервных копий. Разговор включается только по кнопке; после запуска приложения микрофон выключен.")
                .font(.caption).foregroundStyle(.secondary)
            Text("Во время разговора OpenAI получает звук, названия проектов и результаты запрошенных задач.")
                .font(.caption).foregroundStyle(.secondary)
            Text("Голос: GPT Live 1 · команды: GPT-5.6 Luna. Работа над проектами использует модель выбранной задачи и её память.")
                .font(.caption).foregroundStyle(.secondary)
            Text("Реплики разговора видны до следующего звонка. Поручения и уточнения сохраняются в истории соответствующих задач; аудиозапись на диск не ведётся.")
                .font(.caption).foregroundStyle(.secondary)
            Link("Открыть API-ключи OpenAI", destination: URL(string: "https://platform.openai.com/api-keys")!)
                .font(.callout)
        }
    }
}
