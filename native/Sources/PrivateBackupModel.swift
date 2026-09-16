import AppKit
import Foundation

enum PrivateStateAccess {
    static func requireAvailable(_ directory: URL) throws {
        if try ChatHistoryFiles.read(directory.appendingPathComponent(".private-restore.json"), limit: 8192) != nil {
            throw NativeError.message(L10n.text("Восстановление данных не завершено. Откройте «Полная копия», чтобы продолжить или вернуть прежние данные."))
        }
    }
    static func generation(_ directory: URL) throws -> Data? {
        try ChatHistoryFiles.read(directory.appendingPathComponent(".private-state-generation.json"), limit: 1025)
    }

    static func completedRestore(configuration: LaunchConfiguration, since previous: Data?) throws -> JSONValue? {
        let state = configuration.stateDirectory
        let core = configuration.projectRoot.appendingPathComponent("proto_mind/data")
        try requireAvailable(state); try requireAvailable(core)
        guard let current = try generation(state), current != previous, try generation(core) == current else { return nil }
        let value = try JSONDecoder().decode(JSONValue.self, from: current)
        let identifier = value["id"].text
        guard UUID(uuidString: identifier) != nil, ["restore", "rollback"].contains(value["direction"].text) else { return nil }
        let path = state.appendingPathComponent("private_backups/restore-" + identifier + "/receipt.json")
        guard let raw = try ChatHistoryFiles.read(path, limit: 16384) else { return nil }
        let receipt = try JSONDecoder().decode(JSONValue.self, from: raw)
        guard receipt["id"] == value["id"], receipt["direction"] == value["direction"],
              receipt["completed"].flag, receipt["restart_required"].flag else { return nil }
        return receipt
    }
}

@MainActor
final class PrivateBackupModel: ObservableObject {
    @Published private(set) var status: JSONValue = .null
    @Published private(set) var preview: JSONValue = .null
    @Published private(set) var result: JSONValue = .null
    @Published private(set) var working = false
    @Published private(set) var error: String?
    @Published private(set) var notice: String?
    @Published private(set) var conversations = 0
    @Published private(set) var messages = 0
    private var preservedWindow: ChatArchive?

    var pending: Bool { status["pending"].flag }
    var restartRequired: Bool { result["restart_required"].flag }

    func windowIsPreserved(_ app: AppModel) -> Bool {
        preservedWindow?.conversations == app.currentHistoryArchive.conversations && preservedWindow?.selectedID == app.currentHistoryArchive.selectedID
    }

    func refresh(app: AppModel) async {
        guard !working, !app.globalBusy, !restartRequired else { return }
        do {
            status = try await app.client.request("private_backup_status")
            if !status["error"].text.isEmpty { error = status["error"].text }
        } catch { self.error = error.localizedDescription }
    }

    func chooseExport(app: AppModel) {
        guard !app.globalBusy, !working, !app.client.turnOutstanding else { return }
        let panel = NSSavePanel()
        panel.title = L10n.text("Сохранить полную копию данных Proto-Mind")
        panel.nameFieldStringValue = "Proto-Mind \(Date().formatted(.iso8601.year().month().day())).protomind-backup"
        panel.canCreateDirectories = true
        app.presentFilePicker(panel) { [weak self, weak app] response in
            guard response == .OK, let url = panel.url, let self, let app else { return }
            Task { await self.create(at: url, app: app) }
        }
    }

    func chooseSource(app: AppModel) {
        guard !app.globalBusy, !working, !app.client.turnOutstanding else { return }
        let panel = NSOpenPanel()
        panel.title = L10n.text("Выберите полную копию Proto-Mind")
        panel.message = L10n.text("Выберите папку с расширением .protomind-backup.")
        panel.canChooseDirectories = true; panel.canChooseFiles = false; panel.allowsMultipleSelection = false
        app.presentFilePicker(panel) { [weak self, weak app] response in
            guard response == .OK, let url = panel.url, let self, let app else { return }
            Task { await self.inspect(url, app: app) }
        }
    }

    func create(at url: URL, app: AppModel) async {
        guard !working, !app.globalBusy, !app.client.turnOutstanding else { return }
        working = true; app.busy = true; error = nil; notice = nil
        defer { working = false; app.busy = false }
        do {
            try app.saveHistory()
            let value = try await app.client.request("private_backup_create", ["path": .string(url.path)])
            notice = L10n.format("Копия сохранена и проверена: \(value["files"].integer) файлов.")
            result = value
        } catch { self.error = error.localizedDescription }
    }

    func inspect(_ url: URL, app: AppModel) async {
        guard !working, !app.globalBusy, !app.client.turnOutstanding else { return }
        working = true; app.busy = true; error = nil; notice = nil; preview = .null
        defer { working = false; app.busy = false }
        do {
            let value = try await app.client.request("private_backup_preview", ["path": .string(url.path)])
            let source = URL(fileURLWithPath: value["path"].text).appendingPathComponent("payload/native")
            let archive = try ChatStore(directory: source).load()
            conversations = archive.conversations.count
            messages = archive.conversations.reduce(0) { $0 + $1.messages.count }
            preview = value
        } catch { self.error = error.localizedDescription }
    }

    func restore(app: AppModel) async {
        guard !working, !app.globalBusy, !app.client.turnOutstanding, !preview.isNull, preview["same_scope"].flag else { return }
        await execute(app: app) {
            let archive = app.currentHistoryArchive
            let name = "window-\(UUID().uuidString).protomind-history"
            let directory = app.client.configuration.stateDirectory.appendingPathComponent("private_backups")
            try ChatHistoryFiles.directory(directory, create: true)
            try app.store.exportBackup(archive, to: directory.appendingPathComponent(name))
            preservedWindow = archive
            app.draftSave?.cancel()
            return try await app.client.request("private_backup_restore", ["path": preview["path"], "sha256": preview["sha256"],
                "target_fingerprint": preview["target_fingerprint"], "window": .string(name)])
        }
    }

    func resume(app: AppModel, rollback: Bool = false) async {
        guard !working, !app.globalBusy, !app.client.turnOutstanding, pending, !status["id"].text.isEmpty else { return }
        await execute(app: app) {
            try await app.client.request(rollback ? "private_backup_rollback" : "private_backup_resume", ["id": status["id"]])
        }
    }

    func execute(app: AppModel, operation: () async throws -> JSONValue) async {
        working = true; app.busy = true; error = nil; notice = nil
        defer { working = false; app.busy = false }
        var previous: Data?
        var started = false
        do {
            previous = try PrivateStateAccess.generation(app.client.configuration.stateDirectory)
            started = true
            result = try await operation()
            guard result["completed"].flag, result["restart_required"].flag else { throw NativeError.message(L10n.text("Ядро не подтвердило завершение восстановления.")) }
            finish(app: app)
        } catch {
            // A bridge disconnect after the durable commit must not let the old
            // in-window archive overwrite the restored generation on exit.
            if started, let receipt = try? PrivateStateAccess.completedRestore(configuration: app.client.configuration, since: previous) {
                result = receipt
                finish(app: app)
                return
            }
            self.error = error.localizedDescription
            if let value = try? await app.client.request("private_backup_status") { status = value }
        }
    }

    private func finish(app: AppModel) {
        app.privateBackupRestartRequired = true
        app.draftSave?.cancel()
        app.agentGrants.removeAll(); app.pendingAgentAccess = nil
        app.rememberedAgentAccess.removeAll()
        app.codexAccounts.clearUsage()
        app.invalidateSessionSpinePilot()
        app.shutdown()
        preview = .null
    }
}
