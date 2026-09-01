import Foundation

@MainActor
final class BridgeClient: ObservableObject {
    @Published private(set) var connected = false
    @Published private(set) var turnOutstanding = false
    let configuration: LaunchConfiguration
    var onEvent: ((JSONValue) -> Void)?
    private var process: Process?
    private var input: FileHandle?
    private var output: FileHandle?
    private var buffer = Data()
    private var pending: [String: CheckedContinuation<JSONValue, Error>] = [:]
    private var turnRequestID: String?
    private var shuttingDown = false
    private var generation = UUID()

    init(configuration: LaunchConfiguration) { self.configuration = configuration }

    func start() throws {
        guard !shuttingDown else { throw NativeError.message("Мост завершает работу. Перезапустите приложение; запросы не повторялись автоматически.") }
        if process?.isRunning == true { return }
        if process != nil {
            output?.readabilityHandler = nil
            try? input?.close()
            failAll("Предыдущее соединение завершилось. Запросы не повторялись автоматически.")
        }
        generation = UUID()
        let generation = generation
        buffer.removeAll()
        guard FileManager.default.isExecutableFile(atPath: configuration.python.path),
              FileManager.default.fileExists(atPath: configuration.projectRoot.appendingPathComponent("proto_mind/main.py").path) else {
            throw NativeError.message("Не найден Python 3.11+ или проект Proto-Mind. Пересобери native launcher.")
        }
        let process = Process()
        let stdin = Pipe(), stdout = Pipe()
        process.executableURL = configuration.python
        process.arguments = ["-u", "-m", "proto_mind.native_bridge", "--project-root", configuration.projectRoot.path,
                             "--state-dir", configuration.stateDirectory.path]
        if let helper = configuration.pdfHelper { process.arguments?.append(contentsOf: ["--pdf-helper", helper.path]) }
        process.currentDirectoryURL = configuration.projectRoot
        var environment = ProcessInfo.processInfo.environment
        environment["PYTHONPATH"] = configuration.projectRoot.path
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        environment["PYTHONIOENCODING"] = "utf-8"
        process.environment = environment
        process.standardInput = stdin
        process.standardOutput = stdout
        process.standardError = FileHandle.nullDevice
        stdout.fileHandleForReading.readabilityHandler = { [weak self] handle in
            let data = handle.availableData
            Task { @MainActor in
                guard let self, self.generation == generation else { return }
                self.receive(data)
            }
        }
        process.terminationHandler = { [weak self] _ in
            Task { @MainActor in
                guard let self, self.generation == generation else { return }
                self.failAll("Локальное ядро остановлено. Автоматический повтор запросов отключён.")
            }
        }
        try process.run()
        self.process = process
        self.input = stdin.fileHandleForWriting
        self.output = stdout.fileHandleForReading
        connected = true
    }

    func request(_ method: String, _ params: [String: JSONValue] = [:], onID: ((String) -> Void)? = nil) async throws -> JSONValue {
        try start()
        if method == "process" && turnOutstanding {
            throw NativeError.message("Предыдущий запрос ещё не завершился в ядре. Повтор отключён во избежание двойной записи.")
        }
        let id = UUID().uuidString
        let message = JSONValue.object(["id": .string(id), "method": .string(method), "params": .object(params)])
        var data = try JSONEncoder().encode(message)
        guard data.count <= 512 * 1024 else { throw NativeError.message("Запрос превышает локальный лимит.") }
        data.append(10)
        return try await withCheckedThrowingContinuation { continuation in
            pending[id] = continuation
            if method == "process" { turnRequestID = id; turnOutstanding = true }
            onID?(id)
            do { try input?.write(contentsOf: data) }
            catch {
                if turnRequestID == id { turnOutstanding = false; turnRequestID = nil }
                pending.removeValue(forKey: id)?.resume(throwing: error)
                return
            }
            // A live turn stays pending until the bounded provider finishes or the bridge exits.
            // Timing out only the UI could make an unfinished mutation appear safe to retry.
            if method != "process" {
                Task { [weak self] in
                    try? await Task.sleep(nanoseconds: 120_000_000_000)
                    self?.pending.removeValue(forKey: id)?.resume(throwing: NativeError.message("Ядро не ответило вовремя. Запрос не был повторён автоматически."))
                }
            }
        }
    }

    private func receive(_ data: Data) {
        guard !data.isEmpty else { return }
        buffer.append(data)
        guard buffer.count <= 8 * 1024 * 1024 else { failAll("Ответ ядра превышает лимит."); shutdown(); return }
        while let newline = buffer.firstIndex(of: 10) {
            let line = buffer.prefix(upTo: newline)
            buffer.removeSubrange(...newline)
            do {
                let message = try JSONDecoder().decode(JSONValue.self, from: line)
                if !message["event"].text.isEmpty { onEvent?(message); continue }
                if message["id"].text == turnRequestID { turnOutstanding = false; turnRequestID = nil }
                guard let continuation = pending.removeValue(forKey: message["id"].text) else { continue }
                if !message["error"].isNull {
                    continuation.resume(throwing: NativeError.message(message["error"]["message"].text))
                } else { continuation.resume(returning: message["result"]) }
            } catch { failAll("Неверный ответ локального протокола. Автоматический повтор отключён.") }
        }
    }

    private func failAll(_ message: String) {
        connected = false
        if process?.isRunning != true { turnOutstanding = false; turnRequestID = nil }
        let continuations = pending.values
        pending.removeAll()
        for continuation in continuations { continuation.resume(throwing: NativeError.message(message)) }
    }

    func shutdown() {
        shuttingDown = true
        output?.readabilityHandler = nil
        try? input?.close()
        input = nil
        // EOF interrupts model turns, lets core writes finish, and closes Codex.
        // Killing the bridge here would orphan that child or interrupt a store write.
        failAll("Соединение закрыто.")
    }
}
