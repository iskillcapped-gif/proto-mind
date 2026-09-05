import AppKit
import SwiftUI

enum NativeSettingsSection: String, CaseIterable, Identifiable {
    case models, persona, services, data, advanced
    var id: String { rawValue }
    var title: String {
        switch self {
        case .models: return "Модели"
        case .persona: return "Общение"
        case .services: return "Подключения"
        case .data: return "Данные и копии"
        case .advanced: return "Дополнительно"
        }
    }
    var symbol: String {
        switch self {
        case .models: return "slider.horizontal.3"
        case .persona: return "bubble.left.and.bubble.right"
        case .services: return "point.3.connected.trianglepath.dotted"
        case .data: return "externaldrive"
        case .advanced: return "gearshape.2"
        }
    }
    var subtitle: String {
        switch self {
        case .models: return "Выберите, с какой моделью продолжить этот диалог."
        case .persona: return "Характер общения и использование памяти."
        case .services: return "Сервисы, которыми вы пользуетесь в работе."
        case .data: return "Ваши диалоги и способы их восстановить."
        case .advanced: return "Доступ, сессии и технические сведения."
        }
    }
}

struct NativeSettingsView: View {
    @ObservedObject var model: AppModel
    @State private var confirmCodexThreadReset = false
    @State private var confirmPersonaActivation = false

    private var codexThreadTaskID: String {
        [model.selectedID?.uuidString ?? "", model.selected?.provider ?? "", model.selected?.workspacePath ?? ""].joined(separator: "|")
    }

    var body: some View {
        HStack(spacing: 0) {
            VStack(alignment: .leading, spacing: 5) {
                Text("Настройки").font(.system(size: 17, weight: .semibold)).padding(.horizontal, 12).padding(.top, 20).padding(.bottom, 18)
                ForEach(NativeSettingsSection.allCases) { section in
                    Button { model.settingsSection = section } label: {
                        Label(section.title, systemImage: section.symbol).font(.system(size: 13))
                            .frame(maxWidth: .infinity, alignment: .leading).padding(11)
                            .background(model.settingsSection == section ? NativeTheme.selection : .clear, in: RoundedRectangle(cornerRadius: 9))
                    }.buttonStyle(.nativeHover)
                }
                Spacer(minLength: 0)
                Label("Proto-Mind", systemImage: "cube.transparent.fill")
                    .font(.system(size: 12)).foregroundStyle(.secondary).padding(12)
            }.padding(.horizontal, 10).padding(.bottom, 8).frame(width: 185).background(NativeTheme.sidebar)
            VStack(alignment: .leading, spacing: 0) {
                VStack(alignment: .leading, spacing: 7) {
                    Text(model.settingsSection.title).font(.system(size: 24, weight: .semibold))
                    Text(model.settingsSection.subtitle).font(.system(size: 13)).foregroundStyle(.secondary)
                }.padding(.horizontal, 26).padding(.top, 28).padding(.bottom, 12)
                Form {
                    switch model.settingsSection {
                    case .models:
                        modelSettings
                        if model.selected?.provider == "codex" { accountSettings }
                    case .persona:
                        personaSettings
                        Section("Память и навыки") {
                            Text("Заметки проекта и автоматический подбор навыков настраиваются для каждого диалога через кнопку рядом с вложениями.")
                                .font(.callout).foregroundStyle(.secondary)
                            Text("Перед отправкой можно посмотреть, какие сведения попадут в запрос, в разделе «Контекст запроса».")
                                .font(.caption).foregroundStyle(.secondary)
                        }
                    case .services:
                        Section { GitHubConnectionView(app: model, github: model.github) }
                            .task { await model.github.refresh(app: model) }
                    case .data: dataSettings
                    case .advanced:
                        accessSettings
                        if model.selected?.provider == "codex" { sessionSettings }
                        spineSettings
                        Section("О приложении") {
                            LabeledContent("Версия", value: Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "Локальная сборка")
                            DisclosureGroup("Технические сведения") {
                                Text("Python: \(model.client.configuration.python.path)\nПроект: \(model.client.configuration.projectRoot.path)")
                                    .font(.caption.monospaced()).textSelection(.enabled)
                                Text("Управление экраном: \(model.computerUseAvailable ? model.computerUseVersion : "недоступно")")
                                    .font(.caption).foregroundStyle(.secondary)
                            }
                        }
                    }
                    if let error = model.error {
                        Section { Label(error, systemImage: "exclamationmark.circle").foregroundStyle(.orange).font(.callout).textSelection(.enabled) }
                    }
                }.formStyle(.grouped)
            }.frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading).background(NativeTheme.canvas)
        }
        .font(NativeTheme.interfaceFont).buttonStyle(.nativeHover).tint(NativeTheme.accent)
        .navigationTitle("Настройки Proto-Mind")
        .task(id: codexThreadTaskID) { await model.refreshCodexThreadStatus() }
        .confirmationDialog("Начать новую сессию ChatGPT?", isPresented: $confirmCodexThreadReset, titleVisibility: .visible) {
            Button("Начать новую сессию", role: .destructive) { Task { await model.resetCodexThread() } }
            Button("Отмена", role: .cancel) {}
        } message: {
            Text("Следующее сообщение начнёт новую сессию модели. Диалоги Proto-Mind и прежние записи Codex сохранятся. Полный доступ к Mac будет выключен.")
        }
        .confirmationDialog("Включить Brother?", isPresented: $confirmPersonaActivation, titleVisibility: .visible) {
            Button("Проверить и включить") { Task { await model.confirmPersonaActivation() } }
            Button("Отмена", role: .cancel) { model.cancelPersonaActivation() }
        } message: {
            Text("Совместимость будет проверена повторно. Изменение действует со следующего сообщения и не добавляет доступа к файлам или инструментам.")
        }
    }

    private var modelSettings: some View {
        Section("В этом диалоге") {
            Text(model.selected?.title ?? "Новый диалог").font(.callout.weight(.medium)).lineLimit(2)
            Picker("Источник модели", selection: Binding(get: { model.selected?.provider ?? "ollama" }, set: model.setProvider)) {
                Text("ChatGPT · по подписке").tag("codex")
                Text("Ollama · на этом Mac").tag("ollama")
                Text("Тестовый режим · без модели").tag("mock")
            }.disabled(model.busy)
            if model.selected?.provider == "ollama" {
                TextField("Модель Ollama", text: Binding(get: { model.selected?.model ?? "" }, set: model.setModel), prompt: Text(model.bootstrap["ollama_model"].text))
                    .disabled(model.busy)
                Text("Сообщения обрабатываются локально. Для работы запустите Ollama на этом Mac.")
                    .font(.caption).foregroundStyle(.secondary)
                HStack {
                    Button("Проверить подключение") { Task { await model.checkOllama() } }.disabled(model.busy)
                    Spacer()
                    if !model.ollamaStatus.isNull {
                        Label(model.ollamaStatus["connected"].flag ? "Доступна" : "Недоступна", systemImage: model.ollamaStatus["connected"].flag ? "checkmark.circle" : "exclamationmark.circle")
                            .font(.caption).foregroundStyle(.secondary)
                    }
                }
                if !model.ollamaStatus["models"].items.isEmpty {
                    Menu("Установленные модели") {
                        ForEach(model.ollamaStatus["models"].items.map(\.text), id: \.self) { name in Button(name) { model.setModel(name) } }
                    }.disabled(model.busy)
                }
            } else if model.selected?.provider == "codex" {
                Picker("Модель", selection: Binding(get: { model.selected?.model ?? "" }, set: model.setModel)) {
                    Text("По умолчанию для аккаунта").tag("")
                    ForEach(model.codexModels) { item in Text(item.displayName).tag(item.id) }
                    if let selected = model.selected?.model, !selected.isEmpty, model.selectedCodexModel == nil {
                        Text("\(selected) · недоступна").tag(selected)
                    }
                }.disabled(model.busy)
                Picker("Глубина рассуждения", selection: Binding(get: { model.selected?.reasoningEffort ?? "" }, set: model.setReasoningEffort)) {
                    Text(model.selectedCodexModel?.defaultEffort.map { "По умолчанию · \($0.title)" } ?? "По умолчанию").tag("")
                    ForEach(model.availableReasoningEfforts) { effort in Text(effort.title).tag(effort.rawValue) }
                    if let selected = model.selected?.reasoningEffort, !selected.isEmpty, !model.availableReasoningEfforts.contains(where: { $0.rawValue == selected }) {
                        Text("\(selected) · недоступно").tag(selected)
                    }
                }.disabled(model.busy)
                HStack {
                    Button("Обновить список") { Task { await model.refreshAccount() } }
                    Spacer()
                    Button("Сбросить выбор") { model.resetCodexSelection() }
                }.disabled(model.busy || model.connecting)
                Text("Выбор сохраняется для этого диалога. Доступные модели и уровни зависят от аккаунта.")
                    .font(.caption).foregroundStyle(.secondary)
                if let note = model.modelSelectionWarning ?? model.modelSelectionNotice { Text(note).font(.caption).foregroundStyle(.orange) }
            } else {
                Text("Этот режим проверяет приложение без запроса к модели. Он не выполняет задачи и не анализирует сообщения.")
                    .font(.caption).foregroundStyle(.secondary)
            }
        }
    }

    private var accountSettings: some View {
        Section("Аккаунт ChatGPT") {
            HStack {
                Label(model.account.isNull ? "Вход ещё не проверен" : model.account["connected"].flag ? "Подключено" : "Не подключено", systemImage: model.account["connected"].flag ? "checkmark.circle" : "person.crop.circle")
                Spacer()
                if model.connecting { ProgressView().controlSize(.small) }
            }
            if model.account["connected"].flag {
                Text("\(model.account["email"].text) · \(model.account["plan"].text)").font(.caption).foregroundStyle(.secondary)
            }
            HStack {
                Button("Войти через ChatGPT…") { Task { await model.login() } }
                Button("Проверить вход") { Task { await model.refreshAccount() } }
                Spacer()
                if model.account["connected"].flag { Button("Выйти") { Task { await model.logout() } } }
            }.disabled(model.busy || model.connecting)
            if model.loginPending {
                Text("Завершите вход в браузере и нажмите «Проверить вход».").font(.caption).foregroundStyle(.secondary)
            }
            Toggle("Разрешить облачную обработку", isOn: $model.cloudConsent).disabled(model.busy)
            Text("Сообщения, выбранная память и прикреплённые материалы передаются OpenAI. Разрешение действует на этом Mac и сохраняется после перезапуска.")
                .font(.caption).foregroundStyle(.secondary)
            DisclosureGroup("Как работает подключение") {
                Text("Proto-Mind использует официальный Codex и отдельный профиль входа. API-ключ не нужен. Сессии продолжаются между сообщениями; при создании новой сессии добавляется до 12 локальных реплик. Данные входа и настройки Codex Desktop не используются.")
                    .font(.caption).foregroundStyle(.secondary)
            }
        }
    }

    private var personaSettings: some View {
        Section("Характер общения · Brother") {
            LabeledContent("Состояние", value: model.personaEnabled ? "Включён" : "Обычный режим")
            Text("Brother задаёт устойчивый характер общения и использует память, уже выбранную ядром для ответа.")
                .font(.callout).foregroundStyle(.secondary)
            if model.personaEnabled {
                Button("Вернуться к обычному режиму") { model.disablePersona() }.disabled(model.busy)
            } else {
                Button(model.loadingPersonaReadiness ? "Проверяем совместимость…" : "Проверить и включить…") {
                    Task { if await model.preparePersonaActivation() { confirmPersonaActivation = true } }
                }.disabled(model.busy || model.loadingPersonaReadiness || !["codex", "ollama"].contains(model.selected?.provider ?? ""))
                if model.selected?.provider == "mock" { Text("Выберите ChatGPT или Ollama для включения Brother.").font(.caption).foregroundStyle(.secondary) }
            }
            Text("Изменение действует со следующего сообщения. Оно не даёт дополнительных разрешений и не стирает прежнюю историю модели.")
                .font(.caption).foregroundStyle(.secondary)
            DisclosureGroup("Сведения о проверке") {
                if let readiness = model.personaReadiness {
                    Text("Состояние: \(readiness.status)\nПроверка: \(readiness.value["activation_fingerprint"].text)")
                        .font(.caption.monospaced()).textSelection(.enabled)
                } else { Text("Проверка ещё не выполнялась.").font(.caption).foregroundStyle(.secondary) }
                if let receipt = model.lastPersonaTurnReceipt {
                    Text("Последний ответ: \(receipt.snapshotHash)\nЗаписей памяти: \(receipt.selectedMemoryCount)\nКвитанция: \(receipt.receiptHash)")
                        .font(.caption.monospaced()).textSelection(.enabled)
                }
                Text("Persona не меняет Context Injection, не создаёт скрытых записей и проверяет совместимость перед каждым ответом.")
                    .font(.caption).foregroundStyle(.secondary)
            }
        }
    }

    private var dataSettings: some View {
        Group {
            Section("Копии диалогов") {
                Text("Сохраните отдельную копию или вернитесь к предыдущему состоянию истории.")
                    .font(.callout).foregroundStyle(.secondary)
                Button("Копии и восстановление…") { model.openHistoryBackups() }.buttonStyle(.borderedProminent)
                    .disabled(model.busy || model.client.turnOutstanding)
                Text("В копию входят сообщения, черновики и настройки диалогов. Память, журнал задач, облачные сессии и исходные вложения хранятся отдельно.")
                    .font(.caption).foregroundStyle(.secondary)
            }
            Section("На этом Mac") {
                Text("Диалоги хранятся в приватной папке приложения. Локальные снимки помогают восстановить историю, а копия на другом диске — защититься от потери данных.")
                    .font(.callout).foregroundStyle(.secondary)
                DisclosureGroup("Расположение данных") {
                    Text(model.client.configuration.stateDirectory.path).font(.caption.monospaced()).textSelection(.enabled)
                    Button("Показать в Finder") { NSWorkspace.shared.activateFileViewerSelecting([model.client.configuration.stateDirectory]) }
                    Text("В профиле Codex могут храниться полные сообщения и вывод инструментов. Папка содержит личные данные и не предназначена для публикации.")
                        .font(.caption).foregroundStyle(.secondary)
                }
            }
        }
    }

    private var accessSettings: some View {
        Section("Доступ к Mac") {
            Label(model.fullAccessEnabled ? "Полный доступ включён" : "Только чат · инструменты выключены", systemImage: model.fullAccessEnabled ? "exclamationmark.shield" : "lock.shield")
                .foregroundStyle(model.fullAccessEnabled ? Color.orange : .primary)
            Text("Доступ включается отдельно для диалога возле поля сообщения. Он разрешает работу с файлами, терминалом и интернетом, а при доступности — управление экраном. После перезапуска разрешение снимается.")
                .font(.caption).foregroundStyle(.secondary)
            if model.fullAccessEnabled {
                Button("Выключить доступ") { Task { await model.disableAgentAccess() } }.disabled(model.busy)
            }
            DisclosureGroup("Ограничения и журнал действий") {
                Text("Доступ охватывает весь Mac в пределах прав пользователя. Экран может обрабатываться OpenAI. Остановка не откатывает уже выполненные действия. В журнале управления экраном остаются тип действия и приложение, без скриншотов, координат и введённого текста. Это не полный аудит.")
                    .font(.caption).foregroundStyle(.secondary)
                Text("Подключается только проверенная служба OpenAI Computer Use. Прочие MCP, hooks и субагенты выключены. Зависший вызов ограничен 30 секундами и не повторяется автоматически под другим именем приложения.")
                    .font(.caption).foregroundStyle(.secondary)
            }
        }
    }

    private var sessionSettings: some View {
        Section("Сессия модели") {
            Label(model.codexThreadLabel, systemImage: model.codexThreadStatus["linked"].flag ? "link" : "bubble.left")
            if model.loadingCodexThreadStatus { ProgressView().controlSize(.small) }
            if !model.codexThreadStatus["notice"].text.isEmpty { Text(model.codexThreadStatus["notice"].text).font(.caption).foregroundStyle(.secondary) }
            HStack {
                Button("Обновить статус") { Task { await model.refreshCodexThreadStatus() } }
                Spacer()
                Button("Начать заново…", role: .destructive) { confirmCodexThreadReset = true }
                    .disabled(!model.codexThreadStatus["linked"].flag && !model.codexThreadStatus["refresh_required"].flag && !model.codexThreadStatus["legacy_binding"].flag)
            }.disabled(model.busy || model.loadingCodexThreadStatus)
            DisclosureGroup("Технические сведения о сессии") {
                Text("Для чата и полного доступа создаются разные сессии Codex. Следующие сообщения продолжают соответствующую сессию. Обновление инструкций может начать новую сессию, сохраняя прежнюю историю.")
                    .font(.caption).foregroundStyle(.secondary)
                Text("Последний режим: \(model.codexThreadStatus["last_mode"].text)\nМодель: \(model.codexThreadStatus["last_model"].text)\nДоступные режимы: \(model.codexThreadStatus["available_modes"].items.map(\.text).joined(separator: ", "))")
                    .font(.caption.monospaced()).textSelection(.enabled)
                if model.codexThreadStatus["legacy_binding"].flag { Text("Старая сессия сохранена, но не возобновляется автоматически.").font(.caption).foregroundStyle(.orange) }
            }
        }
    }

    private var spineSettings: some View {
        Section {
            DisclosureGroup("Цепочка диалога · Session Spine") {
                Label(model.sessionSpineWriterReceipt != nil ? "Один ход записан" : model.sessionSpinePilotArmed ? "Ход подготовлен до перезапуска" : "Запись не включена", systemImage: "point.3.connected.trianglepath.dotted")
                    .font(.callout)
                Text("Экспериментальная связь ответа с сохранёнными данными о его выполнении. Открывается из меню «Подробнее» под связанным ответом.")
                    .font(.caption).foregroundStyle(.secondary)
                if let readiness = model.sessionSpineReadiness {
                    Text("Состояние: \(readiness.state)\nIdentity: \(readiness.identityState)\nКандидат: \(readiness.candidateHash)")
                        .font(.caption.monospaced()).foregroundStyle(readiness.recoveryRequired ? .orange : .secondary).textSelection(.enabled)
                }
                if model.sessionSpinePilotArmed {
                    if let rehearsal = model.sessionSpineAcceptance { Text("P2k: \(rehearsal.state) · \(rehearsal.rehearsalHash)").font(.caption.monospaced()).textSelection(.enabled) }
                    Button("Отменить подготовку") { model.revokeSessionSpinePilot() }.disabled(model.busy)
                }
                Text("P2j/P2k действуют только до перезапуска и ничего не записывают. P2l требует новой проверки, подтверждения и точной фразы для одного связанного хода. Старые ответы без Turn Lineage не переносятся. Существующие ошибки требуют ручной проверки; автоматического ремонта нет.")
                    .font(.caption).foregroundStyle(.secondary)
            }
        }
    }
}
