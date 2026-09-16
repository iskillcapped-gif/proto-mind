import Foundation

struct ChatBackupSummary: Identifiable {
    let url: URL
    let date: Date
    var id: String { url.path }
}

struct ChatBackupPreview: Identifiable {
    let id = UUID()
    let source: URL
    let sourceHash: String
    let targetHash: String?
    let archive: ChatArchive
    var messageCount: Int { archive.conversations.reduce(0) { $0 + $1.messages.count } }
}

extension ChatStore {
    func checkpoint(_ data: Data, pin: Bool = false, recovery: Bool = false) throws {
        let prefix = recovery ? "recovery-" : pin ? "legacy-" : "snapshot-"
        let path = backupsDirectory.appendingPathComponent(prefix + ChatHistoryFormat.hash(data) + ".json")
        try ChatHistoryFiles.write(data, to: path, replace: false)
    }

    func backups() throws -> [ChatBackupSummary] {
        guard FileManager.default.fileExists(atPath: backupsDirectory.path) else { return [] }
        try ChatHistoryFiles.directory(backupsDirectory, create: false)
        return try FileManager.default.contentsOfDirectory(at: backupsDirectory, includingPropertiesForKeys: [.contentModificationDateKey])
            .filter { $0.pathExtension == "json" }.map { url in
                ChatBackupSummary(url: url, date: try url.resourceValues(forKeys: [.contentModificationDateKey]).contentModificationDate ?? .distantPast)
            }.sorted { ($0.date, $0.id) > ($1.date, $1.id) }
    }

    func compactSnapshots() throws {
        let all = try backups()
        let automatic = all.filter { $0.url.lastPathComponent.hasPrefix("snapshot-") }
        let removed = Array(automatic.dropFirst(20))
        let removedPaths = Set(removed.map(\.id))
        let kept = all.filter { !removedPaths.contains($0.id) }
        var referenced = Set<String>()
        let sources = [url] + kept.map(\.url)
        let paths = Set(sources.map(\.path))
        snapshotReferences = snapshotReferences.filter { paths.contains($0.key) }
        for source in sources {
            let stamp = try ChatHistoryFiles.stamp(source)
            if let previous = snapshotReferences[source.path], previous.stamp == stamp {
                referenced.formUnion(previous.hashes)
                continue
            }
            guard let data = try ChatHistoryFiles.read(source, limit: ChatHistoryFormat.legacyLimit) else { throw ChatHistoryFormat.invalid() }
            let hashes: Set<String>
            if try ChatHistoryFormat.isManifest(data) {
                hashes = Set(try ChatHistoryFormat.manifest(data).conversations.map(\.sha256))
            } else {
                _ = try ChatHistoryFormat.legacy(data)
                hashes = []
            }
            guard try ChatHistoryFiles.stamp(source) == stamp else { throw ChatHistoryFormat.invalid() }
            // Immutable snapshots, especially a large legacy archive, are parsed
            // once per file revision instead of on every subsequent draft save.
            snapshotReferences[source.path] = (stamp, hashes)
            referenced.formUnion(hashes)
        }
        // An unknown/corrupt checkpoint aborts cleanup, preserving its possible
        // dependencies. Only our own verified content-addressed files are removed.
        for item in removed { try FileManager.default.removeItem(at: item.url) }
        try ChatHistoryFiles.directory(objectsDirectory, create: false)
        for item in try FileManager.default.contentsOfDirectory(at: objectsDirectory, includingPropertiesForKeys: nil) {
            let hash = item.deletingPathExtension().lastPathComponent
            guard item.pathExtension == "json", hash.count == 64, hash.allSatisfy({ "0123456789abcdef".contains($0) }),
                  !referenced.contains(hash), let bytes = try ChatHistoryFiles.read(item), ChatHistoryFormat.hash(bytes) == hash else { continue }
            try FileManager.default.removeItem(at: item)
        }
    }

    private func backupData(at source: URL) throws -> (Data, ChatArchive) {
        var isDirectory: ObjCBool = false
        guard FileManager.default.fileExists(atPath: source.path, isDirectory: &isDirectory) else { throw ChatHistoryFormat.invalid() }
        let manifestURL = isDirectory.boolValue ? source.appendingPathComponent("conversations.json") : source
        if isDirectory.boolValue { try ChatHistoryFiles.directory(source, create: false) }
        guard let raw = try ChatHistoryFiles.read(manifestURL, limit: ChatHistoryFormat.legacyLimit) else { throw ChatHistoryFormat.invalid() }
        let objects: URL
        if isDirectory.boolValue { objects = source.appendingPathComponent("chat_objects") }
        else if source.deletingLastPathComponent().resolvingSymlinksInPath() == backupsDirectory.resolvingSymlinksInPath() { objects = objectsDirectory }
        else { objects = source.deletingLastPathComponent().appendingPathComponent("chat_objects") }
        return (raw, try decode(raw, objects: objects))
    }

    func previewBackup(at source: URL) throws -> ChatBackupPreview {
        try ChatHistoryFiles.withLock(in: directory, write: false) {
            let (raw, archive) = try backupData(at: source)
            let current = try ChatHistoryFiles.read(url, limit: ChatHistoryFormat.legacyLimit)
            return ChatBackupPreview(source: source, sourceHash: ChatHistoryFormat.hash(raw),
                                     targetHash: current.map(ChatHistoryFormat.hash), archive: archive)
        }
    }

    func exportBackup(_ archive: ChatArchive, to destination: URL) throws {
        guard !FileManager.default.fileExists(atPath: destination.path) else {
            throw NativeError.message(L10n.text("По этому пути уже есть файл или папка. Выберите новое имя копии."))
        }
        // Do not depend on cached disk objects: this also preserves unsaved replies
        // when the live store is corrupt or has been changed by another process.
        let isolated = ChatStore(directory: destination)
        let (manifest, objects) = try isolated.prepare(archive)
        let stage = destination.deletingLastPathComponent().appendingPathComponent(".history-export-" + UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: stage) }
        let writer = ChatStore(directory: stage)
        try writer.installObjects(objects)
        try ChatHistoryFiles.write(manifest, to: writer.url, replace: false)
        let verified = try writer.decode(manifest, objects: writer.objectsDirectory)
        guard verified.conversations == archive.conversations, verified.selectedID == archive.selectedID else { throw ChatHistoryFormat.invalid() }
        try FileManager.default.moveItem(at: stage, to: destination)
        try ChatHistoryFiles.syncDirectory(destination.deletingLastPathComponent())
    }

    func preserveUnsent(_ archive: ChatArchive) throws {
        let isolated = ChatStore(directory: directory)
        let (manifest, objects) = try isolated.prepare(archive)
        try installObjects(objects)
        try checkpoint(manifest, recovery: true)
    }

    func restore(_ preview: ChatBackupPreview, preserving unsent: ChatArchive) throws -> ChatArchive {
        try ChatHistoryFiles.withLock(in: directory, write: true) {
            let current = try ChatHistoryFiles.read(url, limit: ChatHistoryFormat.legacyLimit)
            guard current.map(ChatHistoryFormat.hash) == preview.targetHash else {
                throw NativeError.message(L10n.text("После проверки история изменилась. Откройте копию заново; восстановление не выполнялось."))
            }
            let (source, archive) = try backupData(at: preview.source)
            guard ChatHistoryFormat.hash(source) == preview.sourceHash,
                  archive.conversations == preview.archive.conversations, archive.selectedID == preview.archive.selectedID else {
                throw NativeError.message(L10n.text("Резервная копия изменилась после проверки. Восстановление не выполнялось."))
            }
            let isolated = ChatStore(directory: directory)
            let (manifest, objects) = try isolated.prepare(archive)
            // Both the current on-disk bytes (even corrupt) and the in-window
            // version survive before the single authoritative pointer is replaced.
            if let current { try checkpoint(current, recovery: true) }
            try preserveUnsent(unsent)
            try installObjects(objects)
            try commit(manifest)
            baseline = manifest
            let restored = try readback(archive).archive
            try adopt(manifest, archive: restored)
            return restored
        }
    }

    func reloadPreserving(_ unsent: ChatArchive) throws -> ChatArchive {
        try ChatHistoryFiles.withLock(in: directory, write: true) { try preserveUnsent(unsent) }
        return try load()
    }
}
