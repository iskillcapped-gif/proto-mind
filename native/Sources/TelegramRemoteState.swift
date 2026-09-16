import Foundation
import Darwin

struct TelegramPeer: Codable, Equatable {
    let userID: Int64
    let chatID: Int64
    let name: String
}

struct TelegramRemoteState: Codable, Equatable {
    var version = 1
    var botID: Int64?
    var botName = ""
    var peer: TelegramPeer?
    var offset: Int64 = 0
    var allowed: [UUID] = []
    var selected: UUID?
}

/// This connection/receipt store is outside restored private backups. Holding a
/// persistent sidecar lease prevents two app instances polling the same profile.
final class TelegramRemoteStore {
    let directory: URL
    private var descriptor: Int32 = -1
    var ownsLease: Bool { descriptor >= 0 }
    init(profile: URL, directory: URL? = nil) {
        let scope = String(ChatHistoryFormat.hash(Data(profile.standardizedFileURL.path.utf8)).prefix(32))
        self.directory = directory ?? profile.deletingLastPathComponent().appendingPathComponent("ProtoMindConnections/" + scope + "/telegram")
    }
    func acquire() throws {
        guard !ownsLease else { return }
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true, attributes: [.posixPermissions: 0o700])
        let fd = open(directory.appendingPathComponent(".connection.lock").path, O_CREAT | O_RDWR | O_NOFOLLOW, 0o600)
        guard fd >= 0 else { throw NativeError.message("Could not open Telegram connection lock") }
        guard flock(fd, LOCK_EX | LOCK_NB) == 0 else {
            close(fd)
            throw NativeError.message(L10n.pick("Это подключение уже используется другим окном приложения.", "Another app instance is using this connection."))
        }
        descriptor = fd
    }
    func release() { if descriptor >= 0 { flock(descriptor, LOCK_UN); close(descriptor); descriptor = -1 } }
    deinit { release() }
    func load() throws -> TelegramRemoteState {
        let url = directory.appendingPathComponent("state.json")
        guard FileManager.default.fileExists(atPath: url.path) else { return TelegramRemoteState() }
        let data = try Data(contentsOf: url)
        guard data.count <= 64_000 else { throw NativeError.message("Telegram connection state is too large") }
        let state = try JSONDecoder().decode(TelegramRemoteState.self, from: data)
        guard state.version == 1, state.offset >= 0, state.allowed.count <= 64,
              Set(state.allowed).count == state.allowed.count,
              state.peer.map({ $0.userID > 0 && $0.chatID == $0.userID }) != false else {
            throw NativeError.message("Invalid Telegram connection state")
        }
        return state
    }
    func save(_ state: TelegramRemoteState) throws {
        guard ownsLease else { throw NativeError.message("Telegram connection lease is missing") }
        let data = try JSONEncoder().encode(state)
        let url = directory.appendingPathComponent("state.json")
        try data.write(to: url, options: .atomic)
        try FileManager.default.setAttributes([.posixPermissions: 0o600], ofItemAtPath: url.path)
        let fd = open(url.path, O_RDONLY | O_NOFOLLOW)
        guard fd >= 0 else { throw NativeError.message("Could not verify Telegram state") }
        let synced = fsync(fd) == 0; close(fd)
        let parent = open(directory.path, O_RDONLY)
        let directorySynced = parent >= 0 && fsync(parent) == 0
        if parent >= 0 { close(parent) }
        guard synced, directorySynced, try Data(contentsOf: url) == data else { throw NativeError.message("Telegram state was not durably saved") }
    }
}

struct TelegramInbound {
    let id: Int64
    let peer: TelegramPeer
    let text: String
    static func parse(_ value: JSONValue, notBefore: Date, now: Date = Date()) -> TelegramInbound? {
        let message = value["message"]
        let user = Int64(message["from"]["id"].integer)
        let chat = Int64(message["chat"]["id"].integer)
        let date = Date(timeIntervalSince1970: Double(message["date"].integer))
        let text = message["text"].text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !value["update_id"].isNull, value["update_id"].integer >= 0,
              message["chat"]["type"].text == "private", user > 0, chat == user,
              !message["from"]["is_bot"].flag, message["sender_chat"].isNull,
              message["forward_origin"].isNull, message["forward_date"].isNull,
              message["via_bot"].isNull, message["is_automatic_forward"].flag == false,
              date >= notBefore, now.timeIntervalSince(date) <= 600, date.timeIntervalSince(now) <= 60,
              !text.isEmpty, text.unicodeScalars.count <= 20_000, !text.contains("\0") else { return nil }
        let name = [message["from"]["first_name"].text, message["from"]["last_name"].text]
            .filter { !$0.isEmpty }.joined(separator: " ")
        return TelegramInbound(id: Int64(value["update_id"].integer),
            peer: TelegramPeer(userID: user, chatID: chat, name: String(name.prefix(100))), text: text)
    }
}

enum TelegramCommand: Equatable {
    case help, tasks, status, stop, use(Int), new(String), message(String), unknown
    static func parse(_ text: String) -> TelegramCommand {
        guard text.hasPrefix("/") else { return .message(text) }
        let pieces = text.split(maxSplits: 1, whereSeparator: \.isWhitespace)
        let verb = String(pieces[0]).lowercased()
        let argument = pieces.count > 1 ? String(pieces[1]).trimmingCharacters(in: .whitespacesAndNewlines) : ""
        switch verb {
        case "/help" where argument.isEmpty, "/start" where argument.isEmpty: return .help
        case "/tasks" where argument.isEmpty: return .tasks
        case "/status" where argument.isEmpty: return .status
        case "/stop" where argument.isEmpty: return .stop
        case "/use": return Int(argument).map { .use($0) } ?? .unknown
        case "/new": return .new(argument)
        default: return .unknown
        }
    }
    static var helpText: String { L10n.pick("""
    /tasks — доступные задачи
    /use 1 — выбрать задачу из списка
    /new название — новый чат с той же моделью и папкой
    /status — состояние и последний ответ
    /stop — остановить выбранную задачу

    Обычный текст запускает задачу или уточняет текущую. Новые чаты работают без полного доступа к Mac, пока вы не включите его в PM. Приложение должно быть открыто, а Mac — бодрствовать.
    """, """
    /tasks — shared tasks
    /use 1 — select a task by its number
    /new title — a new chat with the same model and project folder
    /status — current state and latest answer
    /stop — stop the selected task

    Plain text starts a task or adds an update to the running task. New chats have no Full Mac access until you enable it in PM. Keep PM open and your Mac awake.
    """) }
}
