import Foundation
import Combine

@MainActor
final class TelegramRemoteModel: ObservableObject {
    @Published private(set) var state = TelegramRemoteState()
    @Published private(set) var running = false
    @Published private(set) var connecting = false
    @Published private(set) var hasToken = false
    @Published private(set) var pendingPeer: TelegramPeer?
    @Published private(set) var pairingCode: String?
    @Published var error: String?
    private let secret: TelegramSecretStoring
    let store: TelegramRemoteStore
    private let factory: @MainActor (String) -> TelegramTransport
    private var transport: TelegramTransport?
    private var polling: Task<Void, Never>?
    private struct CompletionRoute { let id = UUID(); let epoch: UUID; let source: UUID? }
    private var completions: [UUID: CompletionRoute] = [:]
    private var generation = UUID()
    private var beganAt = Date()
    private var pairingExpires = Date.distantPast
    private weak var app: AppModel?

    init(profile: URL, secret: TelegramSecretStoring? = nil, directory: URL? = nil,
         factory: @escaping @MainActor (String) -> TelegramTransport = { TelegramHTTP(token: $0) }) {
        self.secret = secret ?? TelegramKeychain(profile: profile)
        self.factory = factory
        store = TelegramRemoteStore(profile: profile, directory: directory)
        hasToken = self.secret.hasKey
        do { state = try store.load() } catch { self.error = L10n.pick("Не удалось прочитать настройки Telegram.", "Could not read Telegram settings.") }
    }
    var pairingURL: URL? {
        guard let pairingCode, !state.botName.isEmpty else { return nil }
        var value = URLComponents(string: "https://t.me/" + state.botName)
        value?.queryItems = [URLQueryItem(name: "start", value: "pm_" + pairingCode)]
        return value?.url
    }
    func saveToken(_ supplied: String) throws {
        stop()
        try store.acquire()
        defer { store.release() }
        _ = try store.load()
        let value = supplied.trimmingCharacters(in: .whitespacesAndNewlines)
        try secret.save(value); hasToken = true
        try change { $0.botID = nil; $0.botName = ""; $0.peer = nil; $0.offset = 0 }
    }
    func removeToken() throws {
        stop(); try store.acquire()
        defer { store.release() }
        try secret.remove(); hasToken = false
        try change { $0 = TelegramRemoteState() }
    }
    private func change(_ update: (inout TelegramRemoteState) -> Void) throws {
        let temporary = !store.ownsLease
        try store.acquire()
        defer { if temporary { store.release() } }
        var next = try store.load(); update(&next)
        try store.save(next); state = next
    }
    func allow(_ id: UUID, enabled: Bool) throws {
        try change { value in
            if enabled && !value.allowed.contains(id) && value.allowed.count < 64 { value.allowed.append(id) }
            else if !enabled { value.allowed.removeAll { $0 == id } }
            if value.selected == nil || !value.allowed.contains(value.selected!) { value.selected = value.allowed.first }
        }
        if !enabled { completions.removeValue(forKey: id) }
    }
    func select(_ id: UUID) throws {
        guard state.allowed.contains(id) else { throw NativeError.message("Task is not shared with Telegram") }
        try change { $0.selected = id }
    }
    func unpair() throws { stop(); try change { $0.peer = nil } }
    func beginPairing() {
        guard running, state.peer == nil else { return }
        pairingCode = UUID().uuidString.replacingOccurrences(of: "-", with: "").lowercased()
        pairingExpires = Date().addingTimeInterval(600); pendingPeer = nil
    }
    func approvePeer() throws {
        guard running, let peer = pendingPeer, pairingCode != nil, pairingExpires > Date() else {
            throw NativeError.message(L10n.pick("Ссылка подключения истекла. Создайте новую.", "The pairing link expired. Create a new one."))
        }
        try change { $0.peer = peer }
        pendingPeer = nil; pairingCode = nil
        let epoch = generation
        Task { await reply(L10n.text("Подключено к Proto-Mind.\n\n") + TelegramCommand.helpText, epoch: epoch) }
    }
    func connect(app: AppModel) async {
        guard !running, !connecting else { return }
        stop(); error = nil; connecting = true; self.app = app
        let epoch = generation
        defer { if generation == epoch { connecting = false } }
        do {
            try requireAvailable(app)
            try store.acquire(); state = try store.load()
            let client = factory(try secret.read()); transport = client
            let me = try await client.call("getMe", parameters: [:])
            guard generation == epoch else { return }
            let id = Int64(me["id"].integer), name = me["username"].text
            guard me["is_bot"].flag, id > 0,
                  name.range(of: "^[A-Za-z0-9_]{5,64}$", options: .regularExpression) != nil else {
                throw NativeError.message("Telegram did not identify a bot")
            }
            let webhook = try await client.call("getWebhookInfo", parameters: [:])
            guard generation == epoch else { return }
            guard webhook["url"].text.isEmpty else {
                throw NativeError.message(L10n.pick("Этот бот уже подключён к другому сервису. Создайте отдельного бота для PM.", "This bot is connected to another service. Create a separate bot for PM."))
            }
            try requireAvailable(app)
            try change {
                if $0.botID != id { $0.peer = nil; $0.offset = 0 }
                $0.botID = id; $0.botName = name
            }
            beganAt = Date().addingTimeInterval(-1); running = true
            if state.peer == nil { beginPairing() }
            polling = Task { [weak self] in await self?.poll(epoch: epoch) }
        } catch {
            guard generation == epoch else { return }
            self.error = error.localizedDescription; stop()
        }
    }
    func stop() {
        generation = UUID(); running = false; connecting = false
        polling?.cancel(); polling = nil
        completions = [:]
        transport?.close(); transport = nil
        pairingCode = nil; pendingPeer = nil
        store.release()
    }
    private func requireAvailable(_ app: AppModel) throws {
        guard !app.operationBusy, !app.privateBackupRestartRequired, !app.historyPersistence.blocksSubmission else {
            throw NativeError.message(L10n.pick("PM занят восстановлением или история требует проверки.", "PM is restoring data or history needs attention."))
        }
        try PrivateStateAccess.requireAvailable(app.serviceClient.configuration.stateDirectory)
    }
    private func poll(epoch: UUID) async {
        do {
            while running && generation == epoch, let transport {
                let updates = try await transport.call("getUpdates", parameters: ["offset": .number(Double(state.offset)),
                    "timeout": .number(25), "limit": .number(50), "allowed_updates": .array([.string("message")])])
                guard generation == epoch, running else { return }
                for update in updates.items { try await consume(update, epoch: epoch) }
                // A server that responds immediately with no updates must not spin.
                if updates.items.isEmpty { try await Task.sleep(for: .seconds(1)) }
            }
        } catch {
            guard generation == epoch else { return }
            self.error = error.localizedDescription; stop()
        }
    }
    func consume(_ update: JSONValue, epoch: UUID? = nil) async throws {
        let epoch = epoch ?? generation
        guard generation == epoch, running, !update["update_id"].isNull else { return }
        let updateID = Int64(update["update_id"].integer)
        guard updateID >= state.offset, updateID < Int64.max else { return }
        // Receipt first: a crash/uncertain send can never execute an update twice.
        try change { $0.offset = updateID + 1 }
        guard let inbound = TelegramInbound.parse(update, notBefore: beganAt) else { return }
        if state.peer == nil {
            guard pendingPeer == nil, let code = pairingCode, pairingExpires > Date(), inbound.text == "/start pm_" + code else { return }
            pendingPeer = inbound.peer
            return
        }
        guard state.peer?.userID == inbound.peer.userID, state.peer?.chatID == inbound.peer.chatID,
              let app else { return }
        do {
            try requireAvailable(app)
            switch TelegramCommand.parse(inbound.text) {
            case .help: await reply(TelegramCommand.helpText, epoch: epoch)
            case .tasks:
                let rows = state.allowed.enumerated().compactMap { index, id -> String? in
                    guard let chat = app.conversations.first(where: { $0.id == id && !$0.archived }) else { return nil }
                    return "\(index + 1). \(id == state.selected ? "→ " : "")\(chat.displayTitle)\(app.isRunning(id) ? L10n.text(" · выполняется") : "")"
                }
                await reply(rows.isEmpty ? L10n.text("Выберите доступные задачи в настройках Telegram на Mac.") : rows.joined(separator: "\n"), epoch: epoch)
            case .use(let number):
                guard number > 0, number <= state.allowed.count else { throw NativeError.message(L10n.text("Сначала получите список /tasks и выберите номер из него.")) }
                let id = state.allowed[number - 1]
                _ = try app.liveVoiceTaskStatus(id); try select(id)
                await reply(L10n.text("Выбрано: ") + (app.conversations.first { $0.id == id }?.displayTitle ?? ""), epoch: epoch)
            case .new(let title):
                let source = try destination(app)
                guard state.allowed.count < 64 else { throw NativeError.message(L10n.text("Уберите лишние задачи из доступа Telegram в настройках PM.")) }
                let id = try app.createTelegramConversation(title: title, source: source)
                try allow(id, enabled: true); try select(id)
                await reply(L10n.text("Новый чат готов. Напишите задачу. Модель и папка сохранены; полный доступ можно включить в PM."), epoch: epoch)
            case .status:
                let id = try destination(app)
                await reply(try statusText(app, id: id), epoch: epoch, taskID: id)
            case .stop:
                let id = try destination(app)
                guard let execution = app.executions[id], execution.running, let request = execution.requestID else { throw NativeError.message(L10n.text("В выбранной задаче сейчас нечего останавливать.")) }
                app.closeTaskUpdateQueue(execution: execution)
                guard app.persist() else { throw NativeError.message(L10n.text("Не удалось сохранить остановку. Проверьте PM.")) }
                _ = try await execution.client.request("cancel", ["request_id": .string(request)])
                await reply(L10n.text("Остановка запрошена. Уже сделанные изменения сохраняются."), epoch: epoch)
            case .message(let text):
                let id = try destination(app)
                let prior = completions[id]
                let route = CompletionRoute(epoch: epoch, source: app.executions[id]?.sourceMessageID)
                completions[id] = route
                let result: JSONValue
                do {
                    result = try await app.sendExternalTaskMessage(text, id: id, authorized: { [weak self] in
                        self?.running == true && self?.generation == epoch && self?.state.allowed.contains(id) == true
                            && self?.state.peer?.userID == inbound.peer.userID
                    }, finished: { [weak self] result in
                        // A failed first history save returns before the normal turn-ended hook.
                        guard let self, self.completions[id]?.id == route.id else { return }
                        self.completions.removeValue(forKey: id)
                        Task { await self.reply(result["answer"].text, epoch: epoch, taskID: id) }
                    })
                } catch { completions[id] = prior; throw error }
                guard generation == epoch, running, state.allowed.contains(id) else { return }
                let update = result["status"].text == "preparing" ? L10n.text("Задача принята. Результат придёт сюда.") : L10n.text("Уточнение сохранено в очереди. Состояние доставки видно в PM.")
                await reply(update, epoch: epoch)
            case .unknown: await reply(L10n.text("Неизвестная команда. /help — список команд."), epoch: epoch)
            }
        } catch {
            // Only this paired private chat receives errors; credentials and network URLs never reach here.
            await reply(error.localizedDescription, epoch: epoch)
        }
    }
    private func destination(_ app: AppModel) throws -> UUID {
        guard let id = state.selected, state.allowed.contains(id),
              app.conversations.contains(where: { $0.id == id && !$0.archived }) else {
            throw NativeError.message(L10n.text("Выберите доступную задачу: /tasks, затем /use номер. Доступ задаётся в настройках PM на Mac."))
        }
        return id
    }
    private func statusText(_ app: AppModel, id: UUID) throws -> String {
        let result = try app.liveVoiceTaskStatus(id)
        let label = result["status"].text == "running" ? L10n.text("Выполняется") : result["status"].text == "needs_attention" ? L10n.text("Нужна проверка") : result["status"].text == "idle" ? L10n.text("Готов к задаче") : L10n.text("Ответ получен")
        return label + " · " + result["title"].text + (result["answer"].text.isEmpty ? "" : "\n\n" + result["answer"].text)
            + (result["answer_partial"].flag ? L10n.text("\n\n… Полный ответ сохранён в PM.") : "")
    }
    func taskEnded(app: AppModel, id: UUID, source: UUID, saved: Bool) {
        guard let route = completions[id], route.source == nil || route.source == source else { return }
        completions.removeValue(forKey: id)
        guard running, generation == route.epoch, state.allowed.contains(id) else { return }
        let text = saved ? ((try? statusText(app, id: id)) ?? L10n.text("Проверьте результат в PM."))
            : L10n.text("Ответ получен, но сохранение требует проверки в PM. Запрос не повторяется автоматически.")
        Task { [weak self, weak app] in
            guard let self, let app, !app.privateBackupRestartRequired else { return }
            await self.reply(text, epoch: route.epoch, taskID: id)
        }
    }
    private func reply(_ text: String, epoch: UUID, taskID: UUID? = nil) async {
        guard generation == epoch, running, let peer = state.peer, let transport else { return }
        let scalars = Array(text.unicodeScalars.prefix(12_000))
        do {
            for start in stride(from: 0, to: scalars.count, by: 1800) {
                guard generation == epoch, running, state.peer == peer,
                      taskID.map({ state.allowed.contains($0) }) != false else { return }
                let part = String(String.UnicodeScalarView(scalars[start..<min(start + 1800, scalars.count)]))
                _ = try await transport.call("sendMessage", parameters: ["chat_id": .number(Double(peer.chatID)), "text": .string(part),
                    "link_preview_options": .object(["is_disabled": .bool(true)])])
            }
        } catch {
            guard generation == epoch else { return }
            self.error = L10n.pick("Доставка в Telegram не подтверждена. Ответ остаётся в PM; проверьте /status после восстановления связи.", "Telegram delivery is unconfirmed. The answer remains in PM; check /status after reconnecting.")
        }
    }
}

extension AppModel {
    func createTelegramConversation(title: String, source: UUID) throws -> UUID {
        guard !operationBusy, !privateBackupRestartRequired, !historyPersistence.blocksSubmission, !store.writeBlocked,
              let original = conversations.first(where: { $0.id == source && !$0.archived }) else { throw NativeError.message(L10n.text("Новый чат сейчас недоступен.")) }
        var chat = Conversation()
        chat.title = title.isEmpty ? "Telegram" : String(title.prefix(160))
        chat.workspacePath = original.workspacePath; chat.provider = original.provider
        chat.model = original.model; chat.reasoningEffort = original.reasoningEffort
        chat.codexAccountID = original.codexAccountID; chat.apiConnectionID = original.apiConnectionID
        conversations.insert(chat, at: 0)
        guard persist() else { conversations.removeAll { $0.id == chat.id }; throw NativeError.message(L10n.text("Не удалось сохранить новый чат.")) }
        return chat.id
    }
}
