import CryptoKit
import Foundation

struct ChatHistoryEntry: Codable, Equatable {
    let id: UUID
    let sha256: String
    let bytes: Int
    let runIDs: [String]
}

struct ChatHistoryManifest: Codable, Equatable {
    var version = 6
    let conversations: [ChatHistoryEntry]
    let selectedID: UUID?
}

enum ChatHistoryFormat {
    static let fileLimit = 50 * 1024 * 1024
    static let legacyLimit = 512 * 1024 * 1024
    static let conversationLimit = 10_000

    static func hash(_ data: Data) -> String { SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined() }

    static func encode<T: Encodable>(_ value: T) throws -> Data {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys, .withoutEscapingSlashes]
        return try encoder.encode(value)
    }

    static func runIDs(_ conversation: Conversation) -> [String] {
        conversation.messages.compactMap { $0.turnReference?["run_id"].text }
    }

    static func entry(_ conversation: Conversation, data: Data) -> ChatHistoryEntry {
        ChatHistoryEntry(id: conversation.id, sha256: hash(data), bytes: data.count, runIDs: runIDs(conversation))
    }

    static func isManifest(_ data: Data) throws -> Bool {
        struct Header: Decodable { let version: Int }
        return try JSONDecoder().decode(Header.self, from: data).version == 6
    }

    static func manifest(_ data: Data) throws -> ChatHistoryManifest {
        let value = try JSONDecoder().decode(JSONValue.self, from: data)
        guard case .object(let fields) = value,
              Set(fields.keys).isSubset(of: ["version", "conversations", "selectedID"]),
              value["version"] == .number(6), case .array(let rows) = value["conversations"],
              rows.allSatisfy({ if case .object(let row) = $0 { return Set(row.keys) == ["id", "sha256", "bytes", "runIDs"] }; return false }) else {
            throw invalid()
        }
        let result = try JSONDecoder().decode(ChatHistoryManifest.self, from: data)
        let runs = result.conversations.flatMap(\.runIDs)
        guard result.conversations.count <= conversationLimit,
              Set(result.conversations.map(\.id)).count == result.conversations.count,
              result.selectedID == nil || result.conversations.contains(where: { $0.id == result.selectedID }),
              Set(runs).count == runs.count, runs.allSatisfy({ UUID(uuidString: $0)?.uuidString.lowercased() == $0 }),
              result.conversations.allSatisfy({ $0.sha256.count == 64 && $0.sha256.allSatisfy { "0123456789abcdef".contains($0) }
                  && (1..<fileLimit).contains($0.bytes) }) else { throw invalid() }
        return result
    }

    static func conversation(_ data: Data, entry: ChatHistoryEntry? = nil) throws -> Conversation {
        guard data.count < fileLimit else { throw NativeError.message("Один диалог достиг лимита 50 МБ. Остальная история сохранена.") }
        let conversation = try JSONDecoder().decode(Conversation.self, from: data)
        guard Set(conversation.messages.map(\.id)).count == conversation.messages.count else { throw invalid() }
        if let entry {
            guard data.count == entry.bytes, hash(data) == entry.sha256, conversation.id == entry.id,
                  runIDs(conversation) == entry.runIDs else { throw invalid() }
        }
        return conversation
    }

    static func legacy(_ data: Data) throws -> ChatArchive {
        guard data.count < legacyLimit else { throw NativeError.message("Старый единый файл истории превышает 512 МБ. Исходник не изменён.") }
        let result = try JSONDecoder().decode(ChatArchive.self, from: data)
        guard [1, 2, 3, 4, 5].contains(result.version), result.conversations.count <= conversationLimit,
              Set(result.conversations.map(\.id)).count == result.conversations.count else { throw invalid() }
        for conversation in result.conversations {
            guard Set(conversation.messages.map(\.id)).count == conversation.messages.count else { throw invalid() }
        }
        return result
    }

    // A detached exact-turn snapshot binds the complete manifest and the selected
    // conversation bytes. Both Native and Python construct this same envelope.
    static func turnSnapshot(manifest: Data, entry: ChatHistoryEntry, conversation: Data) -> Data {
        var data = Data("{\"conversations\":[".utf8)
        data.append(conversation)
        data.append(Data("],\"selectedID\":\"\(entry.id.uuidString)\",\"storage_manifest_sha256\":\"\(hash(manifest))\",\"version\":5}".utf8))
        return data
    }

    static func invalid() -> NativeError { .message("Не удалось проверить историю: формат, состав или контрольные суммы не совпали.") }
}
