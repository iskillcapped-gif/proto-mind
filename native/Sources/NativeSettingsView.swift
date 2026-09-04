import SwiftUI

struct NativeSettingsView: View {
    @ObservedObject var model: AppModel
    @State private var confirmCodexThreadReset = false
    @State private var confirmPersonaActivation = false

    private var codexThreadTaskID: String {
        [model.selectedID?.uuidString ?? "", model.selected?.provider ?? "", model.selected?.workspacePath ?? ""].joined(separator: "|")
    }

    var body: some View {
        Form {
            Section("Модель этого диалога") {
                Picker("Провайдер", selection: Binding(get: { model.selected?.provider ?? "ollama" }, set: model.setProvider)) {
                    Text("Ollama · полностью локально").tag("ollama")
                    Text("Codex · подписка ChatGPT").tag("codex")
                    Text("Mock · без модели, для теста").tag("mock")
                }.disabled(model.busy)
                if model.selected?.provider == "ollama" {
                    TextField("Модель Ollama", text: Binding(get: { model.selected?.model ?? "" }, set: model.setModel), prompt: Text(model.bootstrap["ollama_model"].text))
                        .disabled(model.busy)
                    Text("Только loopback-сервер на этом Mac. Используется существующая конфигурация Proto-Mind; сетевые адреса вне localhost отклоняются.")
                        .font(.caption).foregroundStyle(.secondary)
                    HStack {
                        Button("Проверить Ollama") { Task { await model.checkOllama() } }.disabled(model.busy)
                        if !model.ollamaStatus.isNull {
                            Label(model.ollamaStatus["connected"].flag ? "Доступна" : "Не запущена или недоступна", systemImage: model.ollamaStatus["connected"].flag ? "checkmark.circle" : "exclamationmark.circle")
                                .font(.caption).foregroundStyle(.secondary)
                        }
                    }
                    if !model.ollamaStatus["models"].items.isEmpty {
                        Menu("Установленные модели") {
                            ForEach(model.ollamaStatus["models"].items.map(\.text), id: \.self) { name in
                                Button(name) { model.setModel(name) }
                            }
                        }.disabled(model.busy)
                    }
                }
                if model.selected?.provider == "codex" {
                    Picker("Модель Codex", selection: Binding(get: { model.selected?.model ?? "" }, set: model.setModel)) {
                        Text("По умолчанию для аккаунта").tag("")
                        ForEach(model.codexModels) { item in Text(item.displayName).tag(item.id) }
                        if let selected = model.selected?.model, !selected.isEmpty, model.selectedCodexModel == nil {
                            Text("\(selected) · недоступна").tag(selected)
                        }
                    }.disabled(model.busy)
                    Picker("Усилие рассуждения", selection: Binding(get: { model.selected?.reasoningEffort ?? "" }, set: model.setReasoningEffort)) {
                        Text(model.selectedCodexModel?.defaultEffort.map { "По умолчанию · \($0.title)" } ?? "По умолчанию").tag("")
                        ForEach(model.availableReasoningEfforts) { effort in Text(effort.title).tag(effort.rawValue) }
                        if let selected = model.selected?.reasoningEffort, !selected.isEmpty,
                           !model.availableReasoningEfforts.contains(where: { $0.rawValue == selected }) {
                            Text("\(selected) · недоступно").tag(selected)
                        }
                    }.disabled(model.busy)
                    HStack {
                        Button("Обновить модели") { Task { await model.refreshAccount() } }
                        Button("Сбросить модель и усилие") { model.resetCodexSelection() }
                    }.disabled(model.busy || model.connecting)
                    Text("Настройки сохраняются для этого диалога и передаются в Codex при следующем сообщении. Доступные уровни приходят от модели; список может отличаться от Codex Desktop. Изменение усилия не включает инструменты.")
                        .font(.caption).foregroundStyle(.secondary)
                    if let note = model.modelSelectionWarning ?? model.modelSelectionNotice {
                        Text(note).font(.caption).foregroundStyle(.orange)
                    }
                }
            }
            Section("Brother Persona") {
                HStack {
                    Label(model.personaEnabled ? "Включена" : "Выключена",
                          systemImage: model.personaEnabled ? "person.crop.circle.badge.checkmark" : "person.crop.circle.badge.xmark")
                    Spacer()
                    Text(model.personaEnabled ? "opt-in" : "legacy prompt")
                        .font(.caption).foregroundStyle(.secondary)
                }
                if model.personaEnabled {
                    Button("Вернуться к legacy prompt") { model.disablePersona() }
                        .disabled(model.busy)
                    Text("Отключение действует со следующего хода и меняет только локальную настройку. Уже существующая история durable Codex thread не стирается.")
                        .font(.caption).foregroundStyle(.secondary)
                } else {
                    Button("Проверить и включить…") {
                        Task {
                            if await model.preparePersonaActivation() { confirmPersonaActivation = true }
                        }
                    }
                    .disabled(model.busy || model.loadingPersonaReadiness || !["codex", "ollama"].contains(model.selected?.provider ?? ""))
                    Text("Сначала собирается свежий read-only readiness report. Включение потребует отдельного подтверждения; Mock не поддерживается.")
                        .font(.caption).foregroundStyle(.secondary)
                }
                if let readiness = model.personaReadiness {
                    Text("Последняя проверка: \(readiness.status) · activation \(String(readiness.value["activation_fingerprint"].text.prefix(12)))")
                        .font(.caption.monospaced()).foregroundStyle(readiness.status == "READY" ? Color.secondary : .orange)
                }
                if let receipt = model.lastPersonaTurnReceipt {
                    Text("Последний активный ход: \(String(receipt.snapshotHash.prefix(12))) · память \(receipt.selectedMemoryCount) · receipt \(String(receipt.receiptHash.prefix(12)))")
                        .font(.caption.monospaced()).foregroundStyle(.secondary).textSelection(.enabled)
                }
                Text("Один проверенный Brother snapshot использует уже выбранную ядром память в существующем model call. Persona не выдаёт инструменты, не меняет Context Injection и не добавляет скрытых записей.")
                    .font(.caption).foregroundStyle(.secondary)
            }
            Section("Session Spine pilot") {
                HStack {
                    Label(model.sessionSpinePilotArmed ? "Один точный ход подготовлен" : "Writer выключен",
                          systemImage: model.sessionSpinePilotArmed ? "checkmark.shield" : "lock.shield")
                    Spacer()
                    Text(model.sessionSpinePilotArmed ? "до перезапуска" : "inactive")
                        .font(.caption).foregroundStyle(.secondary)
                }
                if let readiness = model.sessionSpineReadiness {
                    Text("Readiness: \(readiness.state) · identity \(readiness.identityState) · candidate \(String(readiness.candidateHash.prefix(12)))")
                        .font(.caption.monospaced())
                        .foregroundStyle(readiness.recoveryRequired ? .orange : .secondary)
                    if readiness.recoveryRequired {
                        Text("Существующая identity требует ручной проверки. Автоматического ремонта, удаления или пересоздания нет.")
                            .font(.caption).foregroundStyle(.orange)
                    }
                } else {
                    Text("Откройте Session Spine у exact-linked ответа и выберите «Проверить readiness…». Legacy-ответы без Turn Lineage не подходят.")
                        .font(.caption).foregroundStyle(.secondary)
                }
                if model.sessionSpinePilotArmed {
                    Button("Снять локальную подготовку") { model.revokeSessionSpinePilot() }
                        .disabled(model.busy)
                }
                Text("Opt-in не сохраняется, не создаёт installation identity или intent и не активирует writer. Любая будущая запись требует отдельного milestone и персональной приёмки нового точного хода.")
                    .font(.caption).foregroundStyle(.secondary)
            }
            Section("Подписка ChatGPT / Codex") {
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
                    if model.account["connected"].flag { Button("Выйти") { Task { await model.logout() } } }
                }.disabled(model.busy || model.connecting)
                if model.loginPending {
                    Text("Завершите вход в открытом браузере, затем нажмите «Проверить вход». Пароли и коды не вводятся в Proto-Mind.")
                        .font(.caption).foregroundStyle(.secondary)
                }
                Text("Официальный Codex CLI, отдельный профиль Proto-Mind. Не читаем вход, hooks и MCP из Codex Desktop. Список моделей приходит от аккаунта. API-ключи и отдельный Platform API billing не используются.")
                    .font(.caption).foregroundStyle(.secondary)
                Toggle("Разрешаю облачную обработку через Codex на этом Mac", isOn: $model.cloudConsent)
                    .disabled(model.busy)
                Text("В режиме Codex новое сообщение, выбранная ядром память и явно прикреплённые фрагменты файлов передаются OpenAI. До 12 локальных реплик добавляются только при создании нового durable thread; последующие turns продолжаются через Codex. Это не офлайн-модель. Разрешение сохраняется локально и выключается здесь или при выходе из аккаунта.")
                    .font(.caption).foregroundStyle(model.cloudConsent ? Color.secondary : .orange)
            }
            if model.selected?.provider == "codex" {
                Section("Сессия Codex этого диалога") {
                    HStack {
                        Label(model.codexThreadLabel,
                              systemImage: model.codexThreadStatus["linked"].flag ? "link.circle" : "plus.bubble")
                        Spacer()
                        if model.loadingCodexThreadStatus { ProgressView().controlSize(.small) }
                    }
                    if !model.codexThreadStatus.isNull {
                        Text(model.codexThreadStatus["notice"].text)
                            .font(.caption)
                            .foregroundStyle(model.codexThreadStatus["workspace_matches"].flag && !model.codexThreadStatus["refresh_required"].flag ? Color.secondary : .orange)
                        if model.codexThreadStatus["linked"].flag || model.codexThreadStatus["refresh_required"].flag {
                            let mode = model.codexThreadStatus["last_mode"].text == "full_access" ? "полный доступ" : "чат без инструментов"
                            Text("Последний режим: \(mode) · модель: \(model.codexThreadStatus["last_model"].text.isEmpty ? "по умолчанию" : model.codexThreadStatus["last_model"].text)")
                                .font(.caption).foregroundStyle(.secondary)
                        }
                        let modes = model.codexThreadStatus["available_modes"].items.map(\.text)
                        if !modes.isEmpty {
                            Text("Раздельные сессии по режимам: \(modes.map { $0 == "full_access" ? "Full Mac" : "Chat" }.joined(separator: ", ")).")
                                .font(.caption).foregroundStyle(.secondary)
                        }
                        if model.codexThreadStatus["legacy_binding"].flag {
                            Text("Старая сессия с неоднозначными инструкциями сохранена как история и не будет возобновлена автоматически.")
                                .font(.caption).foregroundStyle(.orange)
                        }
                    }
                    HStack {
                        Button("Обновить статус") { Task { await model.refreshCodexThreadStatus() } }
                        Button("Начать новую сессию Codex…", role: .destructive) { confirmCodexThreadReset = true }
                            .disabled(!model.codexThreadStatus["linked"].flag && !model.codexThreadStatus["refresh_required"].flag && !model.codexThreadStatus["legacy_binding"].flag)
                    }.disabled(model.busy || model.loadingCodexThreadStatus)
                    Text("Для Chat и Full Mac создаются отдельные durable threads. Первый ход каждого режима один раз получает до 12 локальных реплик; следующие ходы этого же режима используют thread/resume. Если статический контракт инструкций обновился, только этот режим безопасно начнёт свежий thread, а прежний rollout не удаляется.")
                        .font(.caption).foregroundStyle(.secondary)
                }
            }
            Section("Локальное хранение и безопасность") {
                Text(model.client.configuration.stateDirectory.path).font(.system(size: 10, design: .monospaced)).textSelection(.enabled)
                Text("Здесь история нового интерфейса, приватный индекс связей сессий и отдельный профиль Codex. Rollout с запросами, ответами и выводом инструментов сохраняется самим Codex в этом профиле; это не редактированный экспорт. Исходные хранилища Proto-Mind не переносятся.")
                    .font(.caption).foregroundStyle(.secondary)
                Text(model.computerUseAvailable
                     ? "По умолчанию модель отвечает без инструментов. Отдельный Full Mac включает файлы, терминал, live Web Search, сеть и подписанный OpenAI Computer Use \(model.computerUseVersion). Экран и скриншоты могут обрабатываться OpenAI; разрешение не сохраняется между запусками. Другие MCP, hooks и субагенты выключены."
                     : "По умолчанию модель отвечает без инструментов. Отдельный Full Mac включает файлы, терминал, live Web Search и сеть. Подписанный OpenAI Computer Use не найден или не прошёл проверку; управление экраном выключено. Разрешение не сохраняется между запусками.")
                    .font(.caption).foregroundStyle(.secondary)
                Text("Журнал действий и ограниченные фрагменты вывода сохраняются только в локальной истории Native. Для Computer Use он хранит тип действия и имя приложения, но не скриншоты, UI-дерево, координаты или введённый текст. Журнал не является полным аудитом. Stop/Esc не откатывают изменения.")
                    .font(.caption).foregroundStyle(.secondary)
                Text("Первое чтение каждого приложения в новом ходе запрашивает полный свежий state. Зависший Computer Use вызов ограничен 30 секундами и не повторяется автоматически под другим именем приложения.")
                    .font(.caption).foregroundStyle(.secondary)
            }
            if let error = model.error { Text(error).foregroundStyle(.orange).font(.caption).textSelection(.enabled) }
        }
        .formStyle(.grouped)
        .font(NativeTheme.interfaceFont)
        .buttonStyle(.nativeHover)
        .navigationTitle("Proto-Mind · Модели")
        .tint(.primary)
        .task(id: codexThreadTaskID) { await model.refreshCodexThreadStatus() }
        .confirmationDialog("Начать новую сессию Codex?", isPresented: $confirmCodexThreadReset, titleVisibility: .visible) {
            Button("Начать новую сессию", role: .destructive) { Task { await model.resetCodexThread() } }
            Button("Отмена", role: .cancel) {}
        } message: {
            Text("Будет удалена только локальная связь этого диалога с thread Codex. История Proto-Mind и прежний rollout Codex не удаляются. Следующее сообщение создаст новый thread; полный доступ к Mac останется выключенным.")
        }
        .confirmationDialog("Включить Brother Persona?", isPresented: $confirmPersonaActivation, titleVisibility: .visible) {
            Button("Включить после повторной проверки") { Task { await model.confirmPersonaActivation() } }
            Button("Отмена", role: .cancel) { model.cancelPersonaActivation() }
        } message: {
            Text("Readiness будет проверена ещё раз по тому же SHA. После включения каждый Send заново проверяет provider, модель, доступ и выключенный Context Injection. Новых полномочий это не даёт.")
        }
    }
}
