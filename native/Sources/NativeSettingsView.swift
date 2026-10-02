import AppKit
import SwiftUI

enum NativeSettingsSection: String, CaseIterable, Identifiable {
    case models, voice, appearance, persona, services, data, advanced
    var id: String { rawValue }
    var title: String {
        switch self {
        case .models: return L10n.text("Модели")
        case .voice: return L10n.text("Голос")
        case .appearance: return L10n.text("Оформление")
        case .persona: return L10n.text("Общение")
        case .services: return L10n.text("Подключения")
        case .data: return L10n.text("Данные и копии")
        case .advanced: return L10n.text("Дополнительно")
        }
    }
    var symbol: String {
        switch self {
        case .models: return "slider.horizontal.3"
        case .voice: return "waveform"
        case .appearance: return "paintpalette"
        case .persona: return "bubble.left.and.bubble.right"
        case .services: return "point.3.connected.trianglepath.dotted"
        case .data: return "externaldrive"
        case .advanced: return "gearshape.2"
        }
    }
    var subtitle: String {
        switch self {
        case .models: return L10n.text("Выберите, с какой моделью продолжить этот диалог.")
        case .voice: return L10n.text("Диктовка сообщений и голосовой разговор.")
        case .appearance: return L10n.text("Язык, панели и прозрачность рабочего пространства.")
        case .persona: return L10n.text("Характер общения и использование памяти.")
        case .services: return L10n.text("Сервисы, которыми вы пользуетесь в работе.")
        case .data: return L10n.text("Ваши диалоги и способы их восстановить.")
        case .advanced: return L10n.text("Доступ, сессии и технические сведения.")
        }
    }
}

struct NativeSettingsView: View {
    /// Version and build, e.g. "0.74.4 (108)", to tell which installed build is running.
    static var versionText: String {
        guard let version = Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String else { return L10n.text("Локальная сборка") }
        return (Bundle.main.object(forInfoDictionaryKey: "CFBundleVersion") as? String).map { "\(version) (\($0))" } ?? version
    }

    @ObservedObject var model: AppModel
    @State private var confirmCodexThreadReset = false
    @State private var confirmPersonaActivation = false

    private var codexThreadTaskID: String {
        [model.selectedID?.uuidString ?? "", model.selected?.provider ?? "", model.selected?.workspacePath ?? ""].joined(separator: "|")
    }

    var body: some View {
        GeometryReader { geometry in
            let compact = geometry.size.width < 740
            let layout = compact ? AnyLayout(VStackLayout(spacing: 0)) : AnyLayout(HStackLayout(spacing: 0))
            layout {
                if compact {
                    ScrollView(.horizontal, showsIndicators: false) {
                        HStack(spacing: 5) {
                            ForEach(NativeSettingsSection.allCases) { section in sectionButton(section) }
                        }.padding(12)
                    }.fixedSize(horizontal: false, vertical: true)
                } else {
                    VStack(alignment: .leading, spacing: 5) {
                        Text(L10n.text("Настройки")).font(.system(size: 17, weight: .semibold))
                            .padding(.horizontal, 12).padding(.top, 20).padding(.bottom, 18)
                        ForEach(NativeSettingsSection.allCases) { section in sectionButton(section) }
                        Spacer(minLength: 0)
                        Label("Proto-Mind", systemImage: "cube.transparent.fill")
                            .font(.system(size: 12)).foregroundStyle(.secondary).padding(12)
                    }.padding(.horizontal, 10).padding(.bottom, 8).frame(width: 185)
                        .workspaceBackground(NativeTheme.sidebar)
                }
                VStack(alignment: .leading, spacing: 0) {
                    Group {
                        if model.settingsSection == .services, let kind = model.settingsConnection {
                            ConnectionHeader(app: model, kind: kind)
                        } else {
                            VStack(alignment: .leading, spacing: 7) {
                                Text(model.settingsSection.title).font(.system(size: 23, weight: .semibold))
                                Text(model.settingsSection.subtitle).font(.system(size: 13)).foregroundStyle(.secondary)
                            }
                        }
                    }.frame(maxWidth: .infinity, alignment: .leading).padding(.horizontal, 24).padding(.top, compact ? 12 : 28).padding(.bottom, 12)
                    settingsForm
                }.frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
            }
        }.workspaceBackground(NativeTheme.canvas)
        .font(NativeTheme.interfaceFont).buttonStyle(.nativeHover).tint(NativeTheme.accent)
        .navigationTitle(L10n.text("Настройки Proto-Mind"))
        .task(id: codexThreadTaskID) { await model.refreshCodexThreadStatus() }
        .workspaceConfirmationDialog(L10n.text("Начать новую сессию ChatGPT?"), isPresented: $confirmCodexThreadReset, titleVisibility: .visible) {
            Button(L10n.text("Начать новую сессию"), role: .destructive) { confirmCodexThreadReset = false; Task { await model.resetCodexThread() } }
            Button(L10n.text("Отмена"), role: .cancel) { confirmCodexThreadReset = false }
        } message: {
            Text(L10n.text("Следующее сообщение начнёт новую сессию модели. Диалоги Proto-Mind и прежние записи Codex сохранятся. Полный доступ к Mac будет выключен."))
        }
        .workspaceConfirmationDialog(L10n.text("Включить Brother?"), isPresented: $confirmPersonaActivation, titleVisibility: .visible) {
            Button(L10n.text("Проверить и включить")) { confirmPersonaActivation = false; Task { await model.confirmPersonaActivation() } }
            Button(L10n.text("Отмена"), role: .cancel) { confirmPersonaActivation = false; model.cancelPersonaActivation() }
        } message: {
            Text(L10n.text("Совместимость будет проверена повторно. Изменение действует со следующего сообщения и не добавляет доступа к файлам или инструментам."))
        }
    }

    private func sectionButton(_ section: NativeSettingsSection) -> some View {
        Button { model.settingsSection = section } label: {
            Label(section.title, systemImage: section.symbol).font(.system(size: 13))
                .padding(11).frame(maxWidth: .infinity, alignment: .leading)
                .background(model.settingsSection == section ? NativeTheme.selection : .clear,
                            in: RoundedRectangle(cornerRadius: 9))
        }.buttonStyle(.nativeHover)
    }

    private var settingsForm: some View {
                Form {
                    switch model.settingsSection {
                    case .models:
                        modelSettings
                        if model.selected?.provider == "codex" { accountSettings }
                    case .voice:
                        Section {
                            DictationSettings(dictation: model.dictation)
                        } header: { Text(L10n.text("Диктовка")) } footer: {
                            SettingsFooter(L10n.text("Микрофон в поле сообщения набирает текст. Отправляете его вы; API-ключ и лимиты ChatGPT для диктовки не нужны.")
                                           + " " + L10n.text("Распознавание выполняет Apple: на устройстве, если язык поддерживает этот режим, иначе — на серверах Apple. Аудиозапись в Proto-Mind не сохраняется."))
                        }
                        Section {
                            Toggle(L10n.text("Разрешить обработку в OpenAI"), isOn: $model.cloudConsent).disabled(model.globalBusy)
                        } header: { Text(L10n.text("Голосовой разговор")) } footer: {
                            SettingsFooter(L10n.text("Кнопка голосовой волны рядом с «Меню» сразу начинает разговор. После запуска приложения голос остаётся выключенным."))
                        }
                        LiveVoiceKeySettings(voice: model.liveVoice)
                        Section {
                            LabeledContent(L10n.pick("Голос", "Voice"), value: "GPT Live 1")
                            LabeledContent(L10n.pick("Команды", "Commands"), value: "GPT-5.6 Luna")
                            LabeledContent(L10n.pick("Работа над задачами", "Work on tasks"), value: L10n.pick("Модель и память задачи", "The task's model and memory"))
                        } header: { Text(L10n.text("Использование API")) } footer: {
                            SettingsFooter(L10n.text("GPT Live 1: $0,05 за минуту подключённого разговора. Обработка команд GPT-5.6 Luna оплачивается дополнительно по тарифу API. Подписка ChatGPT не оплачивает этот голосовой канал."))
                        }
                    case .appearance:
                        Section {
                            InterfaceLanguagePicker(configuration: model.serviceClient.configuration, showsNote: false)
                        } footer: {
                            SettingsFooter(L10n.pick("Язык меняется сразу во всех окнах. Ваши сообщения и файлы остаются как есть.", "The language changes immediately in every window. Your messages and files stay as they are."))
                        }
                        DesktopAppearanceSettings(desktop: model.desktop, panels: model.workspacePanels, companions: model.desktop.companions)
                    case .persona:
                        personaSettings
                    case .services:
                        if let kind = model.settingsConnection { ConnectionDetailSections(app: model, kind: kind) }
                        else { ConnectionsOverview(app: model) }
                    case .data: dataSettings
                    case .advanced:
                        accessSettings
                        if model.selected?.provider == "codex" { sessionSettings }
                        spineSettings
                        Section {
                            LabeledContent(L10n.text("Версия"), value: Self.versionText)
                            DisclosureGroup(L10n.text("Технические сведения")) {
                                Text(L10n.format("Python: \(model.client.configuration.python.path)\nПроект: \(model.client.configuration.projectRoot.path)"))
                                    .font(.caption.monospaced()).textSelection(.enabled)
                                Text(L10n.format("Управление экраном: \(model.computerUseAvailable ? model.computerUseVersion : L10n.text("недоступно"))"))
                                    .font(.caption).foregroundStyle(.secondary)
                            }
                        } header: { Text(L10n.text("О приложении")) }
                    }
                    if let error = model.error {
                        Section { Label(error, systemImage: "exclamationmark.circle").foregroundStyle(.orange).font(.callout).textSelection(.enabled) }
                    }
                }.formStyle(.grouped)
                    .scrollContentBackground(.hidden)
                    // Actions read as buttons, not as rows of text.
                    .buttonStyle(.bordered)
    }

    private var provider: String { model.selected?.provider ?? "ollama" }

    private var modelSettings: some View {
        Group {
            Section {
                LabeledContent(L10n.pick("Диалог", "Chat")) {
                    Text(model.selected?.displayTitle ?? L10n.text("Новый диалог")).lineLimit(1).truncationMode(.tail)
                }
                Picker(L10n.text("Источник модели"), selection: Binding(get: { provider }, set: model.setProvider)) {
                    Text(L10n.text("ChatGPT · по подписке")).tag("codex")
                    Text("Claude · Claude Code").tag("claude")
                    Text(L10n.text("Ollama · на этом Mac")).tag("ollama")
                    Text(L10n.text("Модель через API")).tag("api")
                    Text(L10n.text("Тестовый режим · без модели")).tag("mock")
                }.disabled(model.globalBusy)
                switch provider {
                case "api":
                    APIConnectionPicker(app: model, connections: model.apiConnections, conversationID: model.selectedID)
                case "claude":
                    ClaudeModelControls(app: model, conversationID: model.selectedID)
                case "ollama":
                    TextField(L10n.text("Модель Ollama"), text: Binding(get: { model.selected?.model ?? "" }, set: model.setModel), prompt: Text(model.bootstrap["ollama_model"].text))
                        .disabled(model.globalBusy)
                case "codex":
                    Picker(L10n.text("Модель"), selection: Binding(get: { model.selected?.model ?? "" }, set: model.setModel)) {
                        Text(L10n.text("По умолчанию для аккаунта")).tag("")
                        ForEach(model.codexModels) { item in Text(item.displayName).tag(item.id) }
                        if let selected = model.selected?.model, !selected.isEmpty, model.selectedCodexModel == nil {
                            Text(L10n.format("\(selected) · недоступна")).tag(selected)
                        }
                    }.disabled(model.globalBusy)
                    Picker(L10n.text("Глубина рассуждения"), selection: Binding(get: { model.selected?.reasoningEffort ?? "" }, set: model.setReasoningEffort)) {
                        Text(model.selectedCodexModel?.defaultEffort.map { L10n.format("По умолчанию · \($0.title)") } ?? L10n.text("По умолчанию")).tag("")
                        ForEach(model.availableReasoningEfforts) { effort in Text(effort.title).tag(effort.rawValue) }
                        if let selected = model.selected?.reasoningEffort, !selected.isEmpty, !model.availableReasoningEfforts.contains(where: { $0.rawValue == selected }) {
                            Text(L10n.format("\(selected) · недоступно")).tag(selected)
                        }
                    }.disabled(model.globalBusy)
                    HStack {
                        Spacer()
                        Button(L10n.text("Сбросить выбор")) { model.resetCodexSelection() }
                        Button(L10n.text("Обновить список")) { Task { await model.refreshAccount() } }
                    }.disabled(model.globalBusy || model.connecting)
                    if let note = model.modelSelectionWarning ?? model.modelSelectionNotice { SettingsNotice(text: note) }
                default:
                    EmptyView()
                }
            } header: { Text(L10n.text("В этом диалоге")) } footer: {
                switch provider {
                case "claude": SettingsFooter(L10n.pick("Доступность моделей и усилий определяет Claude Code для вашего аккаунта. Беседа продолжает свою сессию Claude вместе с историей инструментов и каждый раз получает выбранную память. Пока Claude работает, новое сообщение доходит до него как уточнение.", "Claude Code determines model and effort availability for your account. A conversation continues its Claude session with its tool history and receives selected memory every turn. While Claude works, a new message reaches it as an update."))
                case "codex": SettingsFooter(L10n.text("Выбор сохраняется для этого диалога. Доступные модели и уровни зависят от аккаунта."))
                case "mock": SettingsFooter(L10n.text("Этот режим проверяет приложение без запроса к модели. Он не выполняет задачи и не анализирует сообщения."))
                default: EmptyView()
                }
            }
            switch provider {
            case "api":
                Section {
                    Toggle(L10n.text("Разрешить облачную обработку"), isOn: $model.cloudConsent).disabled(model.globalBusy)
                    Toggle(L10n.pick("Инструменты PM для этого чата", "PM tools for this chat"), isOn: Binding(get: { model.selected.map(model.apiWorkspaceToolsAllowed) ?? false }, set: { value in
                        if let id = model.selectedID { model.setAPIWorkspaceTools(value, id: id) }
                    })).disabled(model.busy)
                } header: { Text(L10n.pick("Доступ", "Access")) } footer: {
                    SettingsFooter(L10n.pick("Модель сможет работать с задачами, проектной памятью и браузером PM. Нужна поддержка function calling; обращения к API оплачиваются по тарифу провайдера.", "The model can use PM tasks, project memory and browser tools. Requires function calling; API usage is billed by your provider."))
                }
                connectionLink(.api)
            case "claude":
                Section {
                    Toggle(L10n.text("Разрешить облачную обработку"), isOn: $model.cloudConsent).disabled(model.globalBusy)
                } header: { Text(L10n.pick("Доступ", "Access")) }
                connectionLink(.claude)
            case "ollama":
                Section {
                    SettingsRow(title: L10n.pick("Ollama на этом Mac", "Ollama on this Mac"), symbol: "desktopcomputer") {
                        if !model.ollamaStatus.isNull {
                            StatusBadge(text: model.ollamaStatus["connected"].flag ? L10n.text("Доступна") : L10n.text("Недоступна"),
                                        tone: model.ollamaStatus["connected"].flag ? .on : .attention)
                        }
                        Button(L10n.text("Проверить подключение")) { Task { await model.checkOllama() } }.disabled(model.globalBusy)
                    }
                    if !model.ollamaStatus["models"].items.isEmpty {
                        HStack {
                            Text(L10n.text("Установленные модели"))
                            Spacer()
                            Menu(L10n.pick("Выбрать", "Choose")) {
                                ForEach(model.ollamaStatus["models"].items.map(\.text), id: \.self) { name in Button(name) { model.setModel(name) } }
                            }.fixedSize().disabled(model.globalBusy)
                        }
                    }
                } header: { Text(L10n.pick("Подключение", "Connection")) } footer: {
                    SettingsFooter(L10n.text("Сообщения обрабатываются локально. Для работы запустите Ollama на этом Mac."))
                }
            default:
                EmptyView()
            }
        }
    }

    /// The connection a provider depends on, as in Settings → Connections; it opens its page.
    private func connectionLink(_ kind: ConnectionKind) -> some View {
        Section {
            Button { model.settingsConnection = kind; model.settingsSection = .services } label: { ConnectionStatusRow(app: model, kind: kind) }
                .buttonStyle(.plain).accessibilityHint(L10n.pick("Открыть настройки подключения", "Open connection settings"))
        } header: { Text(L10n.pick("Подключение", "Connection")) }
    }

    private var accountSettings: some View {
        CodexAccountSettings(app: model, accounts: model.codexAccounts, conversationID: model.selectedID)
    }

    private var personaSettings: some View {
        Group {
            Section {
                SettingsRow(title: "Brother", detail: L10n.text("Brother задаёт устойчивый характер общения и использует память, уже выбранную ядром для ответа."),
                            symbol: "person.wave.2") {
                    StatusBadge(text: model.personaEnabled ? L10n.text("Включён") : L10n.text("Обычный режим"), tone: model.personaEnabled ? .on : .off)
                }
                HStack {
                    if !model.personaEnabled && !["codex", "ollama"].contains(provider) {
                        Text(L10n.pick("Brother работает с ChatGPT и Ollama. Выберите одну из них в «Моделях».", "Brother works with ChatGPT and Ollama. Choose one of them in Models."))
                            .font(.caption).foregroundStyle(.secondary)
                    }
                    Spacer()
                    if model.personaEnabled {
                        Button(L10n.text("Вернуться к обычному режиму")) { model.disablePersona() }.disabled(model.globalBusy)
                    } else {
                        if model.loadingPersonaReadiness { ProgressView().controlSize(.small) }
                        Button(model.loadingPersonaReadiness ? L10n.text("Проверяем совместимость…") : L10n.text("Проверить и включить…")) {
                            Task { if await model.preparePersonaActivation() { confirmPersonaActivation = true } }
                        }.buttonStyle(.borderedProminent)
                            .disabled(model.globalBusy || model.loadingPersonaReadiness || !["codex", "ollama"].contains(provider))
                    }
                }
                DisclosureGroup(L10n.text("Сведения о проверке")) {
                    if let readiness = model.personaReadiness {
                        Text(L10n.format("Состояние: \(readiness.status)\nПроверка: \(readiness.value["activation_fingerprint"].text)"))
                            .font(.caption.monospaced()).textSelection(.enabled)
                    } else { Text(L10n.text("Проверка ещё не выполнялась.")).font(.caption).foregroundStyle(.secondary) }
                    if let receipt = model.lastPersonaTurnReceipt {
                        Text(L10n.format("Последний ответ: \(receipt.snapshotHash)\nЗаписей памяти: \(receipt.selectedMemoryCount)\nКвитанция: \(receipt.receiptHash)"))
                            .font(.caption.monospaced()).textSelection(.enabled)
                    }
                    Text(L10n.text("Persona не меняет Context Injection, не создаёт скрытых записей и проверяет совместимость перед каждым ответом."))
                        .font(.caption).foregroundStyle(.secondary)
                }
            } header: { Text(L10n.pick("Характер общения", "Personality")) } footer: {
                SettingsFooter(L10n.text("Изменение действует со следующего сообщения. Оно не даёт дополнительных разрешений и не стирает прежнюю историю модели."))
            }
            Section {
                SettingsRow(title: L10n.pick("Заметки проекта и навыки", "Project notes and skills"),
                            detail: L10n.text("Заметки проекта и автоматический подбор навыков настраиваются для каждого диалога через кнопку рядом с вложениями."),
                            symbol: "brain")
                SettingsRow(title: L10n.pick("Контекст запроса", "Request context"),
                            detail: L10n.text("Перед отправкой можно посмотреть, какие сведения попадут в запрос, в разделе «Контекст запроса»."),
                            symbol: "doc.text.magnifyingglass")
            } header: { Text(L10n.text("Память и навыки")) }
        }
    }

    private var dataSettings: some View {
        Group {
            Section {
                SettingsRow(title: L10n.pick("Полная копия данных", "Full data copy"),
                            detail: L10n.text("Диалоги, память, журнал работы и настройки — в одной копии с проверкой файлов и восстановлением."),
                            symbol: "externaldrive.badge.checkmark") {
                    Button(L10n.pick("Открыть…", "Open…")) { model.showPrivateBackup = true }.buttonStyle(.borderedProminent)
                        .disabled(model.globalBusy || model.client.turnOutstanding)
                }
            } header: { Text(L10n.text("Все локальные данные")) }
            Section {
                SettingsRow(title: L10n.pick("Копии и восстановление", "Copies and recovery"),
                            detail: L10n.text("Сохраните отдельную копию или вернитесь к предыдущему состоянию истории."),
                            symbol: "clock.arrow.circlepath") {
                    Button(L10n.pick("Открыть…", "Open…")) { model.openHistoryBackups() }
                        .disabled(model.globalBusy || model.client.turnOutstanding)
                }
            } header: { Text(L10n.text("Копии диалогов")) } footer: {
                SettingsFooter(L10n.text("В копию входят сообщения, черновики и настройки диалогов. Память, журнал задач, облачные сессии и исходные вложения хранятся отдельно."))
            }
            Section {
                SettingsRow(title: L10n.pick("Папка данных", "Data folder"), detail: model.client.configuration.stateDirectory.path, symbol: "folder") {
                    Button(L10n.text("Показать в Finder")) { NSWorkspace.shared.activateFileViewerSelecting([model.client.configuration.stateDirectory]) }
                }
            } header: { Text(L10n.text("На этом Mac")) } footer: {
                SettingsFooter(L10n.text("Диалоги хранятся в приватной папке приложения. Локальные снимки помогают восстановить историю, а копия на другом диске — защититься от потери данных.")
                               + " " + L10n.pick("В профилях Codex и Claude Code хранятся полные сообщения и вывод инструментов, включая снимки экрана. Папка содержит личные данные и не предназначена для публикации.",
                                                 "The Codex and Claude Code profiles keep full messages and tool output, including screenshots. The folder holds personal data and is not meant to be shared."))
            }
        }
    }

    private var accessSettings: some View {
        Section {
            SettingsRow(title: model.fullAccessEnabled ? L10n.text("Полный доступ включён") : L10n.text("Только чат · инструменты выключены"),
                        symbol: model.fullAccessEnabled ? "exclamationmark.shield" : "lock.shield",
                        symbolColor: model.fullAccessEnabled ? .orange : .secondary) {
                if model.fullAccessEnabled {
                    Button(L10n.text("Выключить доступ")) { Task { await model.disableAgentAccess() } }.disabled(model.globalBusy)
                }
            }
            if model.fullAccessEnabled {
                Toggle(L10n.pick("Доступ к Mac для новых подзадач", "Mac access for new subtasks"), isOn: Binding(get: {
                    model.selectedID.map { model.workspaceDelegationEnabled.contains($0) } ?? false
                }, set: { enabled in
                    guard let id = model.selectedID else { return }
                    if enabled { model.workspaceDelegationEnabled.insert(id) } else { model.workspaceDelegationEnabled.remove(id) }
                })).disabled(model.busy)
            }
            DisclosureGroup(L10n.text("Ограничения и журнал действий")) {
                Text(L10n.pick("Доступ охватывает весь Mac в пределах прав пользователя. Снимки экрана получает модель чата: OpenAI у ChatGPT, Anthropic у Claude. Остановка не откатывает уже выполненные действия. В журнале управления экраном остаются тип действия и приложение, без скриншотов, координат и введённого текста; это не полный аудит. Дополнительные MCP-сервисы подключаются в «Подключениях». Ошибки инструментов не вызывают автоматический повтор действий.",
                               "Access covers the whole Mac within your user's permissions. Screenshots go to the chat's model: OpenAI for ChatGPT, Anthropic for Claude. Stopping does not undo actions already taken. The screen-control log keeps the action type and app, without screenshots, coordinates or typed text; it is not a complete audit. Additional MCP services are set up in Connections. Tool failures never automatically replay actions."))
                    .font(.caption).foregroundStyle(.secondary)
            }
        } header: { Text(L10n.text("Доступ к Mac")) } footer: {
            SettingsFooter(L10n.text("Доступ включается отдельно для диалога возле поля сообщения и сохраняется после перезапуска. Он разрешает работу с файлами, терминалом и интернетом, а при доступности — управление экраном. Смена папки или провайдера отключает его.")
                           + (model.fullAccessEnabled ? " " + L10n.pick("Только для одного запуска каждой подзадачи. Разрешение делегировать сбрасывается при перезапуске PM; слияние изменений не выполняется автоматически.", "For one run of each subtask. Delegation resets when PM restarts; changes are never merged automatically.") : ""))
        }
    }

    private var sessionSettings: some View {
        Section {
            SettingsRow(title: model.codexThreadLabel, symbol: model.codexThreadStatus["linked"].flag ? "link" : "bubble.left") {
                if model.loadingCodexThreadStatus { ProgressView().controlSize(.small) }
                Button { Task { await model.refreshCodexThreadStatus() } } label: { Image(systemName: "arrow.clockwise") }
                    .help(L10n.text("Обновить статус")).accessibilityLabel(L10n.text("Обновить статус"))
                Button(L10n.text("Начать заново…"), role: .destructive) { confirmCodexThreadReset = true }
                    .disabled(!model.codexThreadStatus["linked"].flag && !model.codexThreadStatus["refresh_required"].flag && !model.codexThreadStatus["legacy_binding"].flag)
            }.disabled(model.globalBusy || model.loadingCodexThreadStatus)
            DisclosureGroup(L10n.text("Технические сведения о сессии")) {
                Text(L10n.text("Для чата и полного доступа создаются разные сессии Codex. Следующие сообщения продолжают соответствующую сессию. Обновление инструкций может начать новую сессию, сохраняя прежнюю историю."))
                    .font(.caption).foregroundStyle(.secondary)
                Text(L10n.format("Последний режим: \(model.codexThreadStatus["last_mode"].text)\nМодель: \(model.codexThreadStatus["last_model"].text)\nДоступные режимы: \(model.codexThreadStatus["available_modes"].items.map(\.text).joined(separator: ", "))"))
                    .font(.caption.monospaced()).textSelection(.enabled)
                if model.codexThreadStatus["legacy_binding"].flag { Text(L10n.text("Старая сессия сохранена, но не возобновляется автоматически.")).font(.caption).foregroundStyle(.orange) }
            }
        } header: { Text(L10n.text("Сессия модели")) } footer: {
            if !model.codexThreadStatus["notice"].text.isEmpty { SettingsFooter(model.codexThreadStatus["notice"].text) }
        }
    }

    private var spineSettings: some View {
        Section {
            DisclosureGroup(L10n.text("Цепочка диалога · Session Spine")) {
                Label(model.sessionSpineWriterReceipt != nil ? L10n.text("Один ход записан") : model.sessionSpinePilotArmed ? L10n.text("Ход подготовлен до перезапуска") : L10n.text("Запись не включена"), systemImage: "point.3.connected.trianglepath.dotted")
                    .font(.callout)
                Text(L10n.text("Экспериментальная связь ответа с сохранёнными данными о его выполнении. Открывается из меню «Подробнее» под связанным ответом."))
                    .font(.caption).foregroundStyle(.secondary)
                if let readiness = model.sessionSpineReadiness {
                    Text(L10n.format("Состояние: \(readiness.state)\nIdentity: \(readiness.identityState)\nКандидат: \(readiness.candidateHash)"))
                        .font(.caption.monospaced()).foregroundStyle(readiness.recoveryRequired ? .orange : .secondary).textSelection(.enabled)
                }
                if model.sessionSpinePilotArmed {
                    if let rehearsal = model.sessionSpineAcceptance { Text("P2k: \(rehearsal.state) · \(rehearsal.rehearsalHash)").font(.caption.monospaced()).textSelection(.enabled) }
                    Button(L10n.text("Отменить подготовку")) { model.revokeSessionSpinePilot() }.disabled(model.globalBusy)
                }
                Text(L10n.text("P2j/P2k действуют только до перезапуска и ничего не записывают. P2l требует новой проверки, подтверждения и точной фразы для одного связанного хода. Старые ответы без Turn Lineage не переносятся. Существующие ошибки требуют ручной проверки; автоматического ремонта нет."))
                    .font(.caption).foregroundStyle(.secondary)
            }
        } header: { Text(L10n.pick("Эксперименты", "Experiments")) }
    }
}

struct DesktopAppearanceSettings: View {
    @ObservedObject var desktop: DesktopPresentation
    @ObservedObject var panels: WorkspacePanels
    @ObservedObject var companions: DesktopCompanionWindows
    @Environment(\.accessibilityReduceTransparency) private var reduceTransparency

    var body: some View {
        if !desktop.enabled {
            Section {
                SettingsRow(title: L10n.pick("Режим кубика", "Cube mode"),
                            detail: L10n.pick("Чат, кубик и боковые окна парят над рабочим столом.", "The chat, the cube and side windows float above your desktop."),
                            symbol: "cube.transparent") {
                    Button(L10n.pick("Включить", "Turn on")) { desktop.enable() }.buttonStyle(.borderedProminent)
                        .accessibilityLabel(L10n.text("Включить парящий режим"))
                }
            }
        }
        Section {
            Toggle(L10n.text("Показывать нижнюю панель"), isOn: Binding(get: { panels.lowerEnabled }, set: panels.setLowerEnabled))
        } header: { Text(L10n.text("Рабочие панели внутри окна")) } footer: {
            SettingsFooter(L10n.text("По умолчанию справа одна панель. Вторая располагается под ней. Отдельные боковые окна доступны в обоих режимах: через кнопку в верхней панели или кнопки 1 и 2 у кубика."))
        }
        Section {
            Toggle(L10n.text("Оставлять отлепленные окна на экране"), isOn: Binding(
                get: { companions.keepDetachedVisible }, set: companions.setKeepDetachedVisible))
        } header: { Text(L10n.text("Боковые окна")) } footer: {
            SettingsFooter(L10n.text("В режиме кубика боковые окна появляются и скрываются вместе с чатом. Этот переключатель оставляет отлепленные окна видимыми. При смене режима открытые окна сохраняются."))
        }
        Section {
            transparencySlider(L10n.text("Окно чата"), value: Binding(get: { desktop.chatTransparency }, set: desktop.setChatTransparency))
            transparencySlider(L10n.text("Левая колонка"), value: Binding(get: { desktop.sidebarTransparency }, set: desktop.setSidebarTransparency))
            ForEach(DesktopCompanionID.allCases) { id in
                transparencySlider(L10n.text("Боковое ") + id.title.lowercased(), value: Binding(
                    get: { companions.surface(id).transparency }, set: { companions.setTransparency($0, for: id) }))
            }
            if reduceTransparency {
                Label(L10n.text("В macOS включено уменьшение прозрачности. Фон остаётся непрозрачным, выбранные значения сохранены."), systemImage: "accessibility")
                    .font(.caption).foregroundStyle(.secondary)
            }
            HStack {
                Spacer()
                Button(L10n.text("Вернуть исходную прозрачность")) {
                    desktop.setChatTransparency(DesktopGlassAppearance.chatDefault)
                    desktop.setSidebarTransparency(DesktopGlassAppearance.sidebarDefault)
                    for id in DesktopCompanionID.allCases { companions.setTransparency(DesktopGlassAppearance.chatDefault, for: id) }
                }
            }
        } header: { Text(L10n.text("Прозрачность фона")) } footer: {
            SettingsFooter(L10n.text("Слева — плотный фон, справа — прозрачный. Текст и кнопки остаются чёткими. Прозрачность чата и колонки применяется в режиме кубика, боковых окон — в обоих режимах. Значения сохраняются после перезапуска."))
        }
    }

    /// One line per surface: its name, a continuous slider (no tick marks) and the percentage.
    private func transparencySlider(_ title: String, value: Binding<Double>) -> some View {
        HStack(spacing: 12) {
            Text(title).frame(minWidth: 120, alignment: .leading)
            Slider(value: value, in: 0...1) { Text(title) }
                .labelsHidden().accessibilityValue(L10n.format("\(Int((value.wrappedValue * 100).rounded())) процентов"))
            Text("\(Int((value.wrappedValue * 100).rounded()))%")
                .monospacedDigit().foregroundStyle(.secondary).frame(width: 40, alignment: .trailing)
        }
    }
}
