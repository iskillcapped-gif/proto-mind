import Foundation
import Combine

@MainActor
final class MobileRemoteModel: ObservableObject {
    @Published private(set) var state = MobileRemoteState()
    @Published private(set) var running = false
    @Published private(set) var connecting = false
    @Published private(set) var pairing: MobilePairing?
    @Published private(set) var pending: MobileDevice?
    @Published var error: String?
    let store: MobileRemoteStore
    private let server = MobileHTTPServer()
    private weak var app: AppModel?
    private var epoch = UUID()
    private var pendingExpiry = Date.distantPast
    private var restoreGeneration = ""
    private var pairingAttempts: [Date] = []
    private var readable = true
    var port = MobileWire.port

    init(profile: URL, directory: URL? = nil) {
        store = MobileRemoteStore(profile: profile, directory: directory)
        do { state = try store.load() } catch { readable = false; self.error = L10n.pick("Не удалось прочитать подключение iPhone.", "Could not read the iPhone connection.") }
    }
    private func change(_ body: (inout MobileRemoteState) throws -> Void) throws {
        guard readable else { throw MobileHTTPFailure(status: 503, code: "invalid_connection_state") }
        let temporary = !store.ownsLease
        if temporary { try store.acquire() }
        defer { if temporary { store.release() } }
        var changed = state; try body(&changed); try store.save(changed); state = changed
    }
    func setEndpoint(_ value: String) throws {
        guard !running, !connecting, let url = MobileWire.endpoint(value) else { throw MobileClientError.rejected("Enter an HTTPS address, for example https://your-mac.your-tailnet.ts.net") }
        try change { $0.endpoint = url.absoluteString }
    }
    func allow(_ id: UUID, enabled: Bool) throws {
        try change { value in
            if enabled && !value.allowed.contains(id) {
                guard value.allowed.count < 500 else { throw MobileHTTPFailure(status: 409, code: "too_many_chats") }
                value.allowed.append(id)
            } else if !enabled { value.allowed.removeAll { $0 == id } }
        }
    }
    func revoke(_ id: UUID) throws { try change { $0.devices.removeAll { $0.id == id } } }
    func beginPairing() throws {
        guard running, MobileWire.endpoint(state.endpoint) != nil else { throw MobileHTTPFailure(status: 409, code: "connection_off") }
        pairing = MobilePairing(endpoint: state.endpoint, code: try MobileRemoteStore.secret(), expiresAt: Date().addingTimeInterval(600))
        pending = nil
    }
    func approve() throws {
        try requireAvailable()
        guard running, let pending, pendingExpiry > Date(), state.devices.count < 8 else { throw MobileHTTPFailure(status: 409, code: "pairing_expired") }
        try change { value in value.devices.removeAll { $0.id == pending.id }; value.devices.append(pending) }
        self.pending = nil; pairing = nil
    }
    func start(app: AppModel, port: UInt16 = MobileWire.port) throws {
        guard !running, !connecting else { return }
        self.app = app
        try store.acquire()
        do {
            state = try store.load(); readable = true
            let stamp = try generation(app)
            try change { value in
                if value.generation != stamp && !value.generation.isEmpty { value.devices = []; value.allowed = [] }
                value.generation = stamp
                for i in value.receipts.indices where value.receipts[i].status == .reserved {
                    value.receipts[i].status = .unknown; value.receipts[i].code = "delivery_unconfirmed"
                }
            }
            restoreGeneration = stamp; try requireAvailable()
            connecting = true; error = nil; epoch = UUID(); let current = epoch
            try server.start(port: port, handler: { [weak self] request, reply in
                Task { @MainActor in
                    guard let self, self.epoch == current, self.running else { reply(.error(503, "connection_off")); return }
                    reply(await self.handle(request))
                }
            }, ready: { [weak self] result in
                Task { @MainActor in
                    guard let self, self.epoch == current else { return }; self.connecting = false
                    switch result {
                    case .success(let port): self.port = port; self.running = true
                    case .failure: self.stop(); self.error = L10n.pick("Не удалось открыть локальное подключение. Возможно, порт занят другой копией PM.", "Could not open the local connection. Another PM instance may be using the port.")
                    }
                }
            })
        } catch { store.release(); throw error }
    }
    func stop() {
        epoch = UUID(); running = false; connecting = false; pairing = nil; pending = nil
        server.stop(); store.release()
    }
    private func generation(_ app: AppModel) throws -> String {
        let config = app.serviceClient.configuration
        try PrivateStateAccess.requireAvailable(config.stateDirectory)
        try PrivateStateAccess.requireAvailable(config.projectRoot.appendingPathComponent("proto_mind/data"))
        let native = try PrivateStateAccess.generation(config.stateDirectory) ?? Data()
        let core = try PrivateStateAccess.generation(config.projectRoot.appendingPathComponent("proto_mind/data")) ?? Data()
        return MobileWire.hash(native + Data([0]) + core)
    }
    private func requireAvailable() throws {
        guard let app, !app.privateBackupRestartRequired, !app.privateBackup.pending,
              !app.historyPersistence.blocksSubmission, !app.store.writeBlocked,
              try generation(app) == restoreGeneration else { throw MobileHTTPFailure(status: 503, code: "history_unavailable") }
    }
    private func device(_ request: MobileHTTPRequest) throws -> MobileDevice {
        guard let auth = request.headers["authorization"], auth.hasPrefix("Bearer ") else { throw MobileHTTPFailure(status: 401, code: "not_paired") }
        let token = String(auth.dropFirst(7))
        guard MobileWire.validSecret(token) else { throw MobileHTTPFailure(status: 401, code: "not_paired") }
        let hash = MobileWire.hash(Data(token.utf8))
        guard let device = state.devices.first(where: { MobileWire.constantEqual($0.tokenHash, hash) }) else {
            if let pending, pendingExpiry > Date(), MobileWire.constantEqual(pending.tokenHash, hash) {
                throw MobileHTTPFailure(status: 403, code: "awaiting_approval")
            }
            throw MobileHTTPFailure(status: 401, code: "not_paired")
        }
        return device
    }
    private func authorized(device: MobileDevice, chat: UUID, epoch: UUID) -> Bool {
        guard running, self.epoch == epoch, state.allowed.contains(chat), state.devices.contains(device) else { return false }
        return (try? requireAvailable()) != nil
    }
    func handle(_ request: MobileHTTPRequest) async -> MobileHTTPResponse {
        do {
            guard running, let app else { throw MobileHTTPFailure(status: 503, code: "connection_off") }
            try requireAvailable()
            if request.path == "/v1/pair" && request.method == "POST" {
                pairingAttempts = pairingAttempts.filter { Date().timeIntervalSince($0) < 60 }
                guard pairingAttempts.count < 20 else { throw MobileHTTPFailure(status: 429, code: "try_later") }
                pairingAttempts.append(Date())
                let value = try MobileWire.decoder().decode(MobilePairRequest.self, from: request.body)
                guard value.version == MobileWire.version, let pairing, pairing.expiresAt > Date(),
                      pending == nil, MobileWire.constantEqual(pairing.code, value.code),
                      MobileWire.validSecret(value.token), !value.name.isEmpty, value.name.count <= 80,
                      !value.name.unicodeScalars.contains(where: { $0.value < 32 }),
                      !state.devices.contains(where: { $0.id == value.deviceID || $0.tokenHash == MobileWire.hash(Data(value.token.utf8)) }) else {
                    throw MobileHTTPFailure(status: 403, code: "pairing_expired")
                }
                pending = MobileDevice(id: value.deviceID, name: value.name, tokenHash: MobileWire.hash(Data(value.token.utf8)), pairedAt: Date())
                pendingExpiry = pairing.expiresAt; self.pairing = nil
                return .json(MobileServerInfo(name: "Proto-Mind", status: "awaiting_approval"), status: 202)
            }
            let device = try device(request)
            if request.method == "GET", request.path == "/v1/status" { return .json(MobileServerInfo(name: "Proto-Mind", status: "connected")) }
            if request.method == "GET", request.path == "/v1/chats" {
                let allowed = Set(state.allowed)
                let chats = app.listedConversations.filter { allowed.contains($0.id) && !$0.archived }.sorted { $0.updatedAt > $1.updatedAt }
                return .json(MobileChatList(chats: chats.map { app.mobileChat($0) }))
            }
            let parts = request.path.split(separator: "/")
            if request.method == "GET", parts.count == 3, parts[1] == "chats", let id = UUID(uuidString: String(parts[2])) {
                guard state.allowed.contains(id), let chat = app.listedConversations.first(where: { $0.id == id && !$0.archived }),
                      Set(request.query.keys).isSubset(of: ["before"]) else { throw MobileHTTPFailure(status: 404, code: "chat_unavailable") }
                let before: UUID?
                if let raw = request.query["before"] {
                    guard let value = UUID(uuidString: raw) else { throw MobileHTTPFailure.badRequest }; before = value
                } else { before = nil }
                return .json(try app.mobileTranscript(chat, before: before))
            }
            if request.method == "GET", parts.count == 3, parts[1] == "commands", let id = UUID(uuidString: String(parts[2])) {
                guard let receipt = state.receipts.first(where: { $0.id == id && $0.deviceID == device.id }) else { throw MobileHTTPFailure(status: 404, code: "receipt_not_found") }
                return .json(receipt)
            }
            if request.method == "POST", request.path == "/v1/commands" {
                let command = try MobileWire.decoder().decode(MobileCommand.self, from: request.body)
                return .json(try await execute(command, device: device, app: app))
            }
            throw MobileHTTPFailure(status: 404, code: "not_found")
        } catch let failure as MobileHTTPFailure { return .error(failure.status, failure.code) }
        catch is DecodingError { return .error(400, "bad_request") }
        catch { return .error(503, "connection_unavailable") }
    }
    private func execute(_ command: MobileCommand, device: MobileDevice, app: AppModel) async throws -> MobileReceipt {
        // This check precedes all side effects, including any bridge call.
        if let old = state.receipts.first(where: { $0.id == command.id }) {
            guard old.deviceID == device.id, old.fingerprint == command.fingerprint else { throw MobileHTTPFailure(status: 409, code: "command_conflict") }
            return old
        }
        guard command.valid(now: Date()), state.allowed.contains(command.conversationID),
              let chat = app.listedConversations.first(where: { $0.id == command.conversationID && !$0.archived }),
              !app.operationBusy else { throw MobileHTTPFailure(status: 409, code: "task_unavailable") }
        let execution = app.executions[chat.id]
        let currentRun = execution?.running == true ? execution?.requestID : nil
        guard command.kind == .create || (currentRun == command.expectedRunID && (execution?.running != true || currentRun != nil)),
              command.kind != .stop || execution?.running == true else { throw MobileHTTPFailure(status: 409, code: "task_changed") }
        let now = Date(), currentEpoch = epoch
        var receipt = MobileReceipt(id: command.id, deviceID: device.id, fingerprint: command.fingerprint,
                                    conversationID: chat.id, createdAt: now, status: .reserved, code: "preparing")
        try change { value in
            value.receipts.removeAll { now.timeIntervalSince($0.createdAt) > 86_400 }
            guard value.receipts.count < 5000 else { throw MobileHTTPFailure(status: 503, code: "receipt_store_full") }
            value.receipts.append(receipt)
        }
        do {
            guard authorized(device: device, chat: chat.id, epoch: currentEpoch) else { throw MobileHTTPFailure(status: 403, code: "access_changed") }
            switch command.kind {
            case .send:
                let result = try await app.sendExternalTaskMessage(command.text, id: chat.id, authorized: { [weak self] in
                    self?.authorized(device: device, chat: chat.id, epoch: currentEpoch) == true
                })
                receipt.status = .accepted; receipt.code = result["status"].text == "preparing" ? "preparing" : "update_queued"
            case .stop:
                guard let execution, let request = execution.requestID, request == command.expectedRunID else { throw MobileHTTPFailure(status: 409, code: "task_changed") }
                app.closeTaskUpdateQueue(execution: execution)
                guard app.persist() else { throw MobileHTTPFailure(status: 503, code: "history_unavailable") }
                app.stopWorkspaceTools(for: execution)
                _ = try await execution.client.request("cancel", ["request_id": .string(request)])
                receipt.status = .accepted; receipt.code = "stop_requested"
            case .create:
                guard !app.conversations.contains(where: { $0.id == command.id }), state.allowed.count < 500 else { throw MobileHTTPFailure(status: 409, code: "task_unavailable") }
                var created = Conversation(); created.id = command.id; created.title = command.text
                created.workspacePath = chat.workspacePath; created.provider = chat.provider; created.model = chat.model
                created.reasoningEffort = chat.reasoningEffort; created.codexAccountID = chat.codexAccountID; created.apiConnectionID = chat.apiConnectionID
                created.autoSkillsEnabled = chat.autoSkillsEnabled; created.autoProjectRecallEnabled = chat.autoProjectRecallEnabled
                created.memorySuggestionsEnabled = chat.memorySuggestionsEnabled
                try change { $0.allowed.append(created.id) }
                app.conversations.insert(created, at: 0)
                guard app.persist() else {
                    app.conversations.removeAll { $0.id == created.id }
                    throw MobileHTTPFailure(status: 503, code: "history_unavailable")
                }
                receipt.status = .accepted; receipt.code = "chat_created"; receipt.createdConversationID = created.id
            }
        } catch let failure as MobileHTTPFailure { receipt.status = .rejected; receipt.code = failure.code }
        catch { receipt.status = .unknown; receipt.code = "delivery_unconfirmed" }
        // Disconnecting/revoking while a call awaits cannot authorize another write.
        // A reserved receipt survives instead of making an uncertain operation replayable.
        guard store.ownsLease, epoch == currentEpoch else { return receipt }
        try change { value in if let index = value.receipts.firstIndex(where: { $0.id == receipt.id }) { value.receipts[index] = receipt } }
        return receipt
    }
}

extension AppModel {
    func mobileChat(_ chat: Conversation) -> MobileChat {
        let execution = executions[chat.id], answer = chat.messages.last { $0.role == "assistant" || $0.role == "report" }
        let running = execution?.running == true
        let status = running ? "running" : answer?.isError == true ? "needs_attention" : answer == nil ? "idle" : "response_received"
        let account = chat.provider == "codex" ? codexAccounts.connection(chat.codexAccountID).name : chat.provider == "claude" ? "Claude Code" : chat.provider == "api" ? "API" : "Local"
        return MobileChat(id: chat.id, title: chat.displayTitle,
            projectID: MobileWire.hash(Data((chat.workspacePath ?? "").utf8)),
            projectName: chat.workspacePath.map { URL(fileURLWithPath: $0).lastPathComponent } ?? L10n.pick("Без проекта", "No project"),
            provider: chat.provider, model: chat.model, effort: chat.reasoningEffort, account: account,
            fullAccess: hasAgentAccessSelection(chat), status: status, runID: running ? execution?.requestID : nil,
            updatedAt: chat.updatedAt, canUpdate: execution.map { canUpdateTask($0) } ?? false)
    }
    func mobileTranscript(_ chat: Conversation, before: UUID?) throws -> MobileTranscript {
        let messages = chat.messages.filter { ["user", "assistant", "report"].contains($0.role) }
        let end: Int
        if let before {
            guard let index = messages.firstIndex(where: { $0.id == before }) else { throw MobileHTTPFailure(status: 409, code: "history_changed") }; end = index
        } else { end = messages.count }
        let start = max(0, end - 30)
        var budget = 250_000
        let rows = messages[start..<end].map { message in
            let text = String(message.text.prefix(min(budget, MobileWire.messageLimit))); budget -= text.count
            let original = message.taskUpdates ?? []
            let updates = original.suffix(8).map { MobileUpdate(id: $0.id, text: String($0.text.prefix(2000)), state: $0.state.rawValue) }
            return MobileMessage(id: message.id, role: message.role, text: text,
                createdAt: message.createdAt, isError: message.isError, truncated: text.count < message.text.count,
                updates: updates, updatesTruncated: original.count > 8 || original.suffix(8).contains { $0.text.count > 2000 })
        }
        let execution = executions[chat.id], live = execution?.running == true ? execution?.stream ?? "" : ""
        return MobileTranscript(chat: mobileChat(chat), messages: rows, before: start > 0 ? messages[start].id : nil,
            liveText: String(live.suffix(MobileWire.messageLimit)), liveTruncated: live.count > MobileWire.messageLimit,
            activity: execution?.running == true ? execution?.status ?? "" : "")
    }
}
