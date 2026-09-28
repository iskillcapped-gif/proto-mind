import Foundation
import Combine

@MainActor
final class RemoteModel: ObservableObject {
    @Published private(set) var connection: RemoteConnection?
    @Published private(set) var chats: [MobileChat] = []
    @Published private(set) var transcripts: [UUID: MobileTranscript] = [:]
    @Published private(set) var local = RemoteLocalState()
    @Published private(set) var connected = false
    @Published private(set) var waitingForApproval = false
    @Published private(set) var busy = false
    @Published var error: String?
    @Published var notice: String?
    @Published var selected: UUID?
    private let transport: RemoteRequesting
    private let persistence: RemotePersistence
    private var refreshing = false
    private var epoch = UUID()
    private var hadStorageError = false
    var canSend: Bool { connected && !busy && local.pending == nil && !hadStorageError }
    var allowLoopback = false

    init(transport: RemoteRequesting, persistence: RemotePersistence) {
        self.transport = transport; self.persistence = persistence
        do {
            connection = try persistence.connection(); local = try persistence.load()
            if let connection, MobileWire.endpoint(connection.endpoint) == nil || !MobileWire.validSecret(connection.token) {
                throw MobileClientError.invalidPairing
            }
        } catch { hadStorageError = true; self.error = Self.message("storage_failed") }
    }
    func draft(_ id: UUID) -> String { local.drafts[id.uuidString] ?? "" }
    func setDraft(_ text: String, id: UUID) {
        var value = local; value.drafts[id.uuidString] = String(text.prefix(20_000))
        do { try save(value) } catch { self.error = Self.message("storage_failed") }
    }
    private func save(_ state: RemoteLocalState) throws {
        do { try persistence.save(state: state); local = state; hadStorageError = false }
        catch { hadStorageError = true; throw error }
    }
    func pair(_ link: String, name: String, token: String) async {
        guard !busy, connection == nil, !hadStorageError else { return }
        busy = true; defer { busy = false }; self.error = nil
        do {
            let value = try MobilePairing.parse(link, allowLoopback: allowLoopback)
            guard MobileWire.validSecret(token) else { throw MobileClientError.invalidPairing }
            let target = RemoteConnection(endpoint: value.endpoint, deviceID: UUID(), token: token)
            // Keep credentials before POST. If its reply is lost, GET /status can
            // recover the pending/approved pairing without replaying the code.
            try persistence.save(connection: target); connection = target; epoch = UUID()
            let request = MobilePairRequest(code: value.code, deviceID: target.deviceID, name: String(name.prefix(80)), token: token)
            let data = try await transport.request(endpoint: target.endpoint, path: "/v1/pair", token: "", body: MobileWire.encoder().encode(request))
            let status = try MobileWire.decoder().decode(MobileServerInfo.self, from: data)
            guard status.version == MobileWire.version else { throw MobileClientError.disconnected }
            waitingForApproval = true
        } catch is RemoteHTTPError { self.error = Self.message("pairing_expired") }
        catch { self.error = connection == nil ? Self.message("pairing_expired") : Self.message("connection_unavailable") }
    }
    func disconnect() {
        guard !busy else { return }
        do {
            try persistence.save(connection: nil); try persistence.save(state: RemoteLocalState())
            epoch = UUID(); connection = nil; local = RemoteLocalState(); chats = []; transcripts = [:]
            connected = false; waitingForApproval = false; self.error = nil; notice = nil; selected = nil; hadStorageError = false
        } catch { self.error = Self.message("storage_failed") }
    }
    func refresh() async {
        guard let target = connection, !refreshing else { return }
        let current = epoch; refreshing = true; defer { refreshing = false }
        do {
            let status: MobileServerInfo = try await get("/v1/status", target: target)
            guard status.version == MobileWire.version else { throw MobileClientError.disconnected }
            let list: MobileChatList = try await get("/v1/chats", target: target)
            guard list.version == MobileWire.version, current == epoch else { return }
            chats = list.chats; connected = true; waitingForApproval = false; self.error = nil
            let shared = Set(chats.map(\.id))
            transcripts = transcripts.filter { shared.contains($0.key) }
            if let id = selected {
                if shared.contains(id) { try await fetchTranscript(id, target: target, epoch: current) }
                else { selected = nil }
            }
            if local.pending != nil && !busy { await reconcile() }
        } catch let failure as RemoteHTTPError {
            guard current == epoch else { return }; connected = false
            waitingForApproval = failure.code == "awaiting_approval"
            self.error = waitingForApproval ? nil : Self.message(failure.code)
        } catch {
            guard current == epoch else { return }; connected = false; self.error = Self.message("connection_unavailable")
        }
    }
    private func get<T: Decodable>(_ path: String, target: RemoteConnection) async throws -> T {
        let data = try await transport.request(endpoint: target.endpoint, path: path, token: target.token, body: nil)
        return try MobileWire.decoder().decode(T.self, from: data)
    }
    func open(_ id: UUID) async {
        selected = id
        guard let connection else { return }
        do { try await fetchTranscript(id, target: connection, epoch: epoch) }
        catch { self.error = Self.message("connection_unavailable") }
    }
    private func fetchTranscript(_ id: UUID, target: RemoteConnection, epoch current: UUID) async throws {
        let page: MobileTranscript = try await get("/v1/chats/" + id.uuidString, target: target)
        guard current == epoch, page.chat.id == id else { return }
        // Keep explicitly loaded older messages; the newest page updates existing
        // rows (including live steering states) instead of duplicating them.
        let old = transcripts[id]
        let ids = Set(page.messages.map(\.id))
        let boundary = old?.messages.firstIndex { ids.contains($0.id) }
        let older = boundary.map { Array(old!.messages.prefix($0)) } ?? []
        transcripts[id] = MobileTranscript(chat: page.chat, messages: older + page.messages,
            before: older.isEmpty ? page.before : old?.before, liveText: page.liveText, liveTruncated: page.liveTruncated, activity: page.activity)
    }
    func loadEarlier(_ id: UUID) async {
        guard let connection, let page = transcripts[id], let before = page.before, !busy else { return }
        let current = epoch; busy = true; defer { busy = false }
        do {
            let earlier: MobileTranscript = try await get("/v1/chats/" + id.uuidString + "?before=" + before.uuidString, target: connection)
            guard current == epoch, earlier.chat.id == id, let latest = transcripts[id] else { return }
            let ids = Set(latest.messages.map(\.id))
            transcripts[id] = MobileTranscript(chat: latest.chat, messages: earlier.messages.filter { !ids.contains($0.id) } + latest.messages,
                before: earlier.before, liveText: latest.liveText, liveTruncated: latest.liveTruncated, activity: latest.activity)
        } catch { self.error = Self.message("connection_unavailable") }
    }
    func submit(kind: MobileCommand.Kind, chat: MobileChat, text: String) async {
        guard canSend, let target = connection else { return }
        let current = epoch
        let command = MobileCommand(id: UUID(), conversationID: chat.id, kind: kind, text: text,
                                    expectedRunID: kind == .create ? nil : chat.runID, createdAt: Date())
        guard command.valid(now: Date()) else { self.error = Self.message("invalid_message"); return }
        busy = true; self.error = nil; notice = nil; defer { busy = false }
        do {
            var state = local; state.pending = command; try save(state)
        } catch { self.error = Self.message("storage_failed"); return }
        do {
            let data = try await transport.request(endpoint: target.endpoint, path: "/v1/commands", token: target.token, body: MobileWire.encoder().encode(command))
            guard current == epoch else { return }
            try receive(MobileWire.decoder().decode(MobileReceipt.self, from: data), command: command, target: target)
        } catch let failure as RemoteHTTPError {
            guard current == epoch else { return }
            // These validation failures occur before reserving a command. A 5xx
            // may have happened after execution, so it remains uncertain.
            if [400, 401, 403, 404, 409, 413].contains(failure.status) {
                var state = local; state.pending = nil
                do { try save(state) } catch { self.error = Self.message("storage_failed"); return }
                self.error = Self.message(failure.code)
            } else { self.error = Self.message("delivery_unconfirmed") }
        } catch { if current == epoch { self.error = Self.message("delivery_unconfirmed") } }
    }
    func reconcile() async {
        guard let command = local.pending, let target = connection, !busy else { return }
        let current = epoch; busy = true; defer { busy = false }
        do {
            let receipt: MobileReceipt = try await get("/v1/commands/" + command.id.uuidString, target: target)
            guard current == epoch else { return }; try receive(receipt, command: command, target: target)
        } catch { if current == epoch { self.error = Self.message("delivery_unconfirmed") } }
    }
    private func receive(_ receipt: MobileReceipt, command: MobileCommand, target: RemoteConnection) throws {
        guard receipt.id == command.id, receipt.deviceID == target.deviceID, receipt.conversationID == command.conversationID,
              receipt.fingerprint == command.fingerprint else { throw MobileClientError.uncertain }
        switch receipt.status {
        case .reserved, .unknown: self.error = Self.message("delivery_unconfirmed")
        case .accepted, .rejected:
            var state = local; state.pending = nil
            if receipt.status == .accepted && command.kind == .send && state.drafts[command.conversationID.uuidString] == command.text {
                state.drafts.removeValue(forKey: command.conversationID.uuidString)
            }
            try save(state)
            if receipt.status == .accepted {
                notice = Self.message(receipt.code); self.error = nil
                if let id = receipt.createdConversationID, command.kind == .create { selected = id }
            } else { self.error = Self.message(receipt.code) }
        }
    }
    // This only dismisses a local notice after the person checks the chat. It
    // never replays a command or implies a missing response was a failed action.
    func acknowledgeUncertain() {
        guard !busy else { return }
        do { var value = local; value.pending = nil; try save(value); self.error = nil }
        catch { self.error = Self.message("storage_failed") }
    }
    static func message(_ code: String) -> String {
        switch code {
        case "preparing": return R("Задача принята на Mac", "Task accepted on your Mac")
        case "update_queued": return R("Уточнение поставлено в очередь", "Update queued")
        case "stop_requested": return R("Остановка запрошена", "Stop requested")
        case "chat_created": return R("Чат создан без полного доступа к Mac", "Chat created without full Mac access")
        case "awaiting_approval": return R("Подтвердите iPhone в настройках PM на Mac", "Approve this iPhone in PM settings on your Mac")
        case "pairing_expired": return R("Создайте новый QR-код на Mac и подключитесь заново", "Create a new QR code on your Mac and pair again")
        case "not_paired", "access_changed": return R("Доступ отключён на Mac. Подключите iPhone заново.", "Access was revoked on your Mac. Pair your iPhone again.")
        case "storage_failed": return R("Не удалось сохранить данные на iPhone. Отправка приостановлена.", "Could not save data on your iPhone. Sending is paused.")
        case "task_changed", "task_unavailable": return R("Состояние задачи изменилось. Обновите чат и проверьте перед отправкой.", "The task changed. Refresh and review the chat before sending.")
        case "delivery_unconfirmed": return R("Доставка не подтверждена. Проверьте статус и переписку. Автоматической повторной отправки нет.", "Delivery is unconfirmed. Check its status and the conversation. This command will not be resent automatically.")
        case "invalid_message": return R("Введите сообщение не длиннее 20 000 символов.", "Enter a message up to 20,000 characters.")
        case "history_unavailable": return R("На Mac нужно проверить сохранение истории или восстановление данных.", "Check history storage or data recovery on your Mac.")
        default: return R("Mac недоступен. Проверьте Tailscale, запущенный PM и режим сна.", "Your Mac is unreachable. Check Tailscale, running PM, and sleep mode.")
        }
    }
}

func R(_ russian: String, _ english: String) -> String { Locale.preferredLanguages.first?.hasPrefix("ru") == true ? russian : english }
