import Foundation

@MainActor
final class LiveVoiceTransport {
    var onEvent: ((JSONValue) -> Void)?
    var onFailure: ((String) -> Void)?
    private var socket: URLSessionWebSocketTask?
    private var session: URLSession?
    private var receiver: Task<Void, Never>?
    private var sender: Task<Void, Never>?
    private var closingTimer: Task<Void, Never>?
    private var queued: [(data: Data, audio: Bool)] = []
    private var queuedBytes = 0
    private var generation = UUID()
    private(set) var closing = false

    func connect(key: String, start: JSONValue) {
        abort()
        let generation = UUID(); self.generation = generation; closing = false
        let configuration = URLSessionConfiguration.ephemeral
        configuration.timeoutIntervalForRequest = 30
        // This is a continuously streamed session, not a short HTTP request.
        configuration.timeoutIntervalForResource = 0
        configuration.urlCache = nil
        let session = URLSession(configuration: configuration)
        self.session = session
        var request = URLRequest(url: LiveVoiceProtocol.endpoint)
        request.setValue("Bearer " + key, forHTTPHeaderField: "Authorization")
        let socket = session.webSocketTask(with: request)
        socket.maximumMessageSize = LiveVoiceProtocol.maxMessageBytes
        self.socket = socket
        socket.resume()
        receiver = Task { [weak self] in
            do {
                while !Task.isCancelled {
                    let message = try await socket.receive()
                    guard let self, self.generation == generation else { return }
                    let data: Data
                    switch message {
                    case .data(let bytes): data = bytes
                    case .string(let text): data = Data(text.utf8)
                    @unknown default: continue
                    }
                    guard data.count <= LiveVoiceProtocol.maxMessageBytes else { throw NativeError.message(L10n.text("Ответ голоса слишком велик.")) }
                    let event = try JSONDecoder().decode(JSONValue.self, from: data)
                    self.onEvent?(event)
                }
            } catch {
                guard let self, self.generation == generation, !Task.isCancelled else { return }
                self.fail(L10n.format("Голосовое соединение прервано. \(error.localizedDescription)"))
            }
        }
        send(start)
    }

    func send(_ event: JSONValue) {
        guard socket != nil, !closing || event["type"].text == "session.close" else { return }
        do {
            let data = try JSONEncoder().encode(event)
            // Backpressure is bounded by bytes, not a lifetime/action cutoff.
            guard data.count <= LiveVoiceProtocol.maxMessageBytes, queuedBytes + data.count <= 256_000 else {
                throw NativeError.message(L10n.text("Сеть не успевает передавать звук. Разговор остановлен; задачи продолжают работать."))
            }
            queued.append((data, event["type"].text == "session.input_audio.append")); queuedBytes += data.count
            drain()
        } catch { fail(error.localizedDescription) }
    }

    private func drain() {
        guard sender == nil, let socket else { return }
        let generation = generation
        sender = Task { [weak self] in
            guard let self else { return }
            do {
                while self.generation == generation, !self.queued.isEmpty, !Task.isCancelled {
                    let item = self.queued.removeFirst(); self.queuedBytes -= item.data.count
                    try await socket.send(.string(String(decoding: item.data, as: UTF8.self)))
                }
                if self.generation == generation { self.sender = nil }
            } catch {
                if self.generation == generation, !Task.isCancelled { self.fail(L10n.format("Не удалось отправить звук или команду. \(error.localizedDescription)")) }
            }
        }
    }

    func close() {
        guard socket != nil, !closing else { return }
        closing = true
        queued.removeAll { $0.audio }; queuedBytes = queued.reduce(0) { $0 + $1.data.count }
        send(.object(["type": .string("session.close")]))
        let generation = generation
        closingTimer = Task { [weak self] in
            try? await Task.sleep(nanoseconds: 15_000_000_000)
            guard let self, !Task.isCancelled, self.generation == generation else { return }
            self.fail(L10n.text("Разговор отключён. Сервер не прислал итог использования; повторного подключения не было."))
        }
    }

    func abort() {
        generation = UUID()
        receiver?.cancel(); sender?.cancel(); closingTimer?.cancel()
        receiver = nil; sender = nil; closingTimer = nil
        queued.removeAll(); queuedBytes = 0
        socket?.cancel(with: .normalClosure, reason: nil); socket = nil
        session?.invalidateAndCancel(); session = nil
    }

    private func fail(_ message: String) {
        abort()
        onFailure?(String(message.replacingOccurrences(of: "sk-[A-Za-z0-9_-]+", with: L10n.text("[ключ скрыт]"), options: .regularExpression).prefix(600)))
    }
}
