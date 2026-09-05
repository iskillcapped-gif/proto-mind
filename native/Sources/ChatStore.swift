import Foundation

struct ChatStoreReadback {
    let archive: ChatArchive
    let data: Data
    let sha256: String
    let sizeBytes: Int
}

final class ChatStore {
    let url: URL
    var directory: URL { url.deletingLastPathComponent() }
    var objectsDirectory: URL { directory.appendingPathComponent("chat_objects") }
    var backupsDirectory: URL { directory.appendingPathComponent("history_backups") }
    private(set) var writeBlocked = false
    private(set) var conflictDetected = false
    var baseline: Data?
    var loaded = false
    var generationBaseline: Data?
    var cached: [UUID: (Conversation, ChatHistoryEntry)] = [:]
    var objectStamps: [String: String] = [:]
    var snapshotReferences: [String: (stamp: String, hashes: Set<String>)] = [:]
    private let dataReader: (URL) throws -> Data
    private let dataWriter: ((Data, URL) throws -> Void)?
    private let beforeCommit: ((ChatArchive) throws -> Void)?

    init(directory: URL, dataReader: @escaping (URL) throws -> Data = { try Data(contentsOf: $0) },
         dataWriter: ((Data, URL) throws -> Void)? = nil, beforeCommit: ((ChatArchive) throws -> Void)? = nil) {
        url = directory.appendingPathComponent("conversations.json")
        self.dataReader = dataReader; self.dataWriter = dataWriter; self.beforeCommit = beforeCommit
    }

    func decode(_ data: Data, objects: URL) throws -> ChatArchive {
        guard try ChatHistoryFormat.isManifest(data) else { return try ChatHistoryFormat.legacy(data) }
        let manifest = try ChatHistoryFormat.manifest(data)
        try ChatHistoryFiles.directory(objects, create: false)
        let conversations = try manifest.conversations.map { entry -> Conversation in
            guard let raw = try ChatHistoryFiles.read(objects.appendingPathComponent(entry.sha256 + ".json")) else { throw ChatHistoryFormat.invalid() }
            return try ChatHistoryFormat.conversation(raw, entry: entry)
        }
        return ChatArchive(conversations: conversations, selectedID: manifest.selectedID)
    }

    func adopt(_ data: Data?, archive: ChatArchive) throws {
        generationBaseline = try PrivateStateAccess.generation(directory)
        baseline = data; loaded = true; cached = [:]; objectStamps = [:]
        if let data, try ChatHistoryFormat.isManifest(data) {
            let manifest = try ChatHistoryFormat.manifest(data)
            for (conversation, entry) in zip(archive.conversations, manifest.conversations) {
                cached[conversation.id] = (conversation, entry)
                objectStamps[entry.sha256] = try ChatHistoryFiles.stamp(objectsDirectory.appendingPathComponent(entry.sha256 + ".json"))
            }
        }
        writeBlocked = false; conflictDetected = false
    }

    func load() throws -> ChatArchive {
        try ChatHistoryFiles.withLock(in: directory, write: false) {
            let raw: Data?
            do { raw = try ChatHistoryFiles.read(url, limit: ChatHistoryFormat.legacyLimit) }
            catch { writeBlocked = true; throw error }
            baseline = raw; loaded = true
            guard let raw else {
                if FileManager.default.fileExists(atPath: objectsDirectory.path)
                    || FileManager.default.fileExists(atPath: backupsDirectory.path) {
                    writeBlocked = true
                    throw NativeError.message("Список диалогов отсутствует, но сохранённые данные найдены. Выберите резервную копию; новая пустая история не будет записана поверх них.")
                }
                let archive = ChatArchive(conversations: [], selectedID: nil)
                try adopt(nil, archive: archive)
                return archive
            }
            do {
                let readback = try dataReader(url)
                guard readback == raw else { throw ChatHistoryFormat.invalid() }
                let archive = try decode(raw, objects: objectsDirectory)
                try adopt(raw, archive: archive)
                return archive
            } catch {
                writeBlocked = true
                throw NativeError.message("Не удалось прочитать историю. Исходные файлы сохранены; можно выбрать резервную копию. " + error.localizedDescription)
            }
        }
    }

    func checkBaseline() throws -> Data? {
        let currentGeneration = try PrivateStateAccess.generation(directory)
        guard !loaded || currentGeneration == generationBaseline else {
            conflictDetected = true
            throw NativeError.message("Данные восстановлены другой копией приложения. Сохраните нужный текст отдельно и перезапустите Proto-Mind.")
        }
        let current = try ChatHistoryFiles.read(url, limit: ChatHistoryFormat.legacyLimit)
        guard (loaded || current == nil), current == baseline else {
            conflictDetected = true
            throw NativeError.message("История изменена другой копией Proto-Mind. Ваши сообщения остаются в окне. Сохраните их копию или откройте актуальную историю.")
        }
        return current
    }

    func prepare(_ archive: ChatArchive) throws -> (Data, [String: Data]) {
        guard archive.conversations.count <= ChatHistoryFormat.conversationLimit,
              Set(archive.conversations.map(\.id)).count == archive.conversations.count else { throw ChatHistoryFormat.invalid() }
        var objects: [String: Data] = [:]
        let entries = try archive.conversations.map { conversation -> ChatHistoryEntry in
            if let (old, entry) = cached[conversation.id], old == conversation { return entry }
            let raw = try ChatHistoryFormat.encode(conversation)
            _ = try ChatHistoryFormat.conversation(raw)
            let entry = ChatHistoryFormat.entry(conversation, data: raw)
            objects[entry.sha256] = raw
            return entry
        }
        let data = try ChatHistoryFormat.encode(ChatHistoryManifest(conversations: entries, selectedID: archive.selectedID))
        guard data.count < ChatHistoryFormat.fileLimit else { throw ChatHistoryFormat.invalid() }
        _ = try ChatHistoryFormat.manifest(data)
        return (data, objects)
    }

    func installObjects(_ objects: [String: Data]) throws {
        try ChatHistoryFiles.directory(objectsDirectory, create: true)
        for (hash, data) in objects { try ChatHistoryFiles.write(data, to: objectsDirectory.appendingPathComponent(hash + ".json"), replace: false) }
    }

    func commit(_ data: Data) throws {
        if let dataWriter { try dataWriter(data, url) }
        else { try ChatHistoryFiles.write(data, to: url, replace: true) }
    }

    func save(_ archive: ChatArchive) throws {
        guard !writeBlocked else { throw ChatHistoryFormat.invalid() }
        try beforeCommit?(archive)
        let (data, objects) = try prepare(archive)
        try ChatHistoryFiles.withLock(in: directory, write: true) {
            let current = try checkBaseline()
            for entry in try ChatHistoryFormat.manifest(data).conversations where objects[entry.sha256] == nil {
                let objectURL = objectsDirectory.appendingPathComponent(entry.sha256 + ".json")
                if try ChatHistoryFiles.stamp(objectURL) != objectStamps[entry.sha256] {
                    guard let raw = try ChatHistoryFiles.read(objectURL) else { throw ChatHistoryFormat.invalid() }
                    _ = try ChatHistoryFormat.conversation(raw, entry: entry)
                }
            }
            if current == data { return }
            if let current { try checkpoint(current, pin: !(try ChatHistoryFormat.isManifest(current))) }
            try installObjects(objects)
            try commit(data)
            try adopt(data, archive: archive)
            // Cleanup follows the atomic commit and cannot invalidate a successful save.
            try? compactSnapshots()
        }
    }

    func saveAndReadBack(_ archive: ChatArchive) throws -> ChatStoreReadback {
        // A v5 -> v6 transition changes the exact evidence. The existing Spine
        // comparison must invalidate that candidate before any identity/Spine write.
        try save(archive)
        return try ChatHistoryFiles.withLock(in: directory, write: false) {
            _ = try checkBaseline()
            return try readback(archive)
        }
    }

    func readback(_ archive: ChatArchive) throws -> ChatStoreReadback {
        do {
            let data = try dataReader(url)
            guard data == baseline else { throw ChatHistoryFormat.invalid() }
            let restored = try decode(data, objects: objectsDirectory)
            guard restored.conversations == archive.conversations, restored.selectedID == archive.selectedID else { throw ChatHistoryFormat.invalid() }
            let evidence: Data
            if try ChatHistoryFormat.isManifest(data) {
                let manifest = try ChatHistoryFormat.manifest(data)
                if let entry = manifest.conversations.first(where: { $0.id == archive.selectedID }),
                   let raw = try ChatHistoryFiles.read(objectsDirectory.appendingPathComponent(entry.sha256 + ".json")) {
                    evidence = ChatHistoryFormat.turnSnapshot(manifest: data, entry: entry, conversation: raw)
                } else { evidence = data }
            } else { evidence = data }
            return ChatStoreReadback(archive: restored, data: evidence, sha256: ChatHistoryFormat.hash(evidence), sizeBytes: evidence.count)
        } catch {
            writeBlocked = true
            throw NativeError.message("История записана, но чтение после сохранения не подтвердилось. Повторная запись заблокирована: " + error.localizedDescription)
        }
    }
}
