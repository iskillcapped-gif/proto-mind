import Foundation
import Security
import Darwin

struct MobileDevice: Codable, Equatable, Identifiable {
    let id: UUID
    let name: String
    let tokenHash: String
    let pairedAt: Date
}

struct MobileRemoteState: Codable {
    var version = 1
    var endpoint = ""
    var generation = ""
    var devices: [MobileDevice] = []
    var allowed: [UUID] = []
    var receipts: [MobileReceipt] = []
}

/// Lives beside, not inside, the backed-up Native profile. Restoring a history
/// cannot restore an old device's authority or erase consumed command IDs.
final class MobileRemoteStore {
    let directory: URL
    private var fd: Int32 = -1
    private var loaded: Data?
    var ownsLease: Bool { fd >= 0 }
    var file: URL { directory.appendingPathComponent("state.json") }
    init(profile: URL, directory: URL? = nil) {
        let scope = String(MobileWire.hash(Data(profile.standardizedFileURL.path.utf8)).prefix(32))
        self.directory = directory ?? profile.deletingLastPathComponent().appendingPathComponent("ProtoMindConnections/" + scope + "/mobile")
    }
    func acquire() throws {
        guard !ownsLease else { return }
        try ChatHistoryFiles.directory(directory, create: true)
        let opened = open(directory.appendingPathComponent(".connection.lock").path, O_CREAT | O_RDWR | O_NOFOLLOW | O_CLOEXEC, 0o600)
        guard opened >= 0 else { throw MobileHTTPFailure(status: 503, code: "connection_unavailable") }
        var info = stat()
        guard fstat(opened, &info) == 0, (info.st_mode & S_IFMT) == S_IFREG, flock(opened, LOCK_EX | LOCK_NB) == 0 else {
            close(opened); throw MobileHTTPFailure(status: 503, code: "connection_in_use")
        }
        fd = opened
    }
    func release() { if fd >= 0 { flock(fd, LOCK_UN); close(fd); fd = -1 } }
    deinit { release() }
    func load() throws -> MobileRemoteState {
        loaded = try ChatHistoryFiles.read(file, limit: 8_000_000)
        guard let loaded else { return MobileRemoteState() }
        let state = try MobileWire.decoder().decode(MobileRemoteState.self, from: loaded)
        guard state.version == 1, state.devices.count <= 8, state.allowed.count <= 500, state.receipts.count <= 5000,
              Set(state.devices.map(\.id)).count == state.devices.count, Set(state.allowed).count == state.allowed.count,
              Set(state.receipts.map(\.id)).count == state.receipts.count,
              state.devices.allSatisfy({ MobileWire.validSecret($0.tokenHash) && !$0.name.isEmpty && $0.name.count <= 80 }),
              state.receipts.allSatisfy({ MobileWire.validSecret($0.fingerprint) && $0.code.count <= 100 }),
              (state.generation.isEmpty ? state.devices.isEmpty : MobileWire.validSecret(state.generation)),
              state.endpoint.isEmpty || MobileWire.endpoint(state.endpoint) != nil else {
            throw MobileHTTPFailure(status: 503, code: "invalid_connection_state")
        }
        return state
    }
    func save(_ state: MobileRemoteState) throws {
        guard ownsLease, try ChatHistoryFiles.read(file, limit: 8_000_000) == loaded else {
            throw MobileHTTPFailure(status: 503, code: "connection_state_changed")
        }
        let data = try MobileWire.encoder().encode(state)
        guard data.count < 8_000_000 else { throw MobileHTTPFailure(status: 503, code: "receipt_store_full") }
        try ChatHistoryFiles.write(data, to: file, replace: true)
        guard try ChatHistoryFiles.read(file, limit: 8_000_000) == data else { throw MobileHTTPFailure(status: 503, code: "connection_save_failed") }
        loaded = data
    }
    static func secret() throws -> String {
        var bytes = [UInt8](repeating: 0, count: 32)
        guard SecRandomCopyBytes(kSecRandomDefault, bytes.count, &bytes) == errSecSuccess else { throw MobileHTTPFailure(status: 503, code: "random_unavailable") }
        return bytes.map { String(format: "%02x", $0) }.joined()
    }
}
