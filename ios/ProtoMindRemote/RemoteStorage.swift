import Foundation
import Security

final class RemoteStorage: RemotePersistence {
    private let service = "com.virencore.protomind.remote.connection"
    private var query: [String: Any] { [kSecClass as String: kSecClassGenericPassword, kSecAttrService as String: service, kSecAttrAccount as String: "paired-mac"] }
    private let directory: URL
    init() {
        directory = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0].appendingPathComponent("PMRemote", isDirectory: true)
    }
    func connection() throws -> RemoteConnection? {
        var q = query; q[kSecReturnData as String] = true; q[kSecMatchLimit as String] = kSecMatchLimitOne
        var value: CFTypeRef?
        let status = SecItemCopyMatching(q as CFDictionary, &value)
        if status == errSecItemNotFound { return nil }
        guard status == errSecSuccess, let data = value as? Data else { throw MobileClientError.disconnected }
        return try MobileWire.decoder().decode(RemoteConnection.self, from: data)
    }
    func save(connection: RemoteConnection?) throws {
        guard let connection else {
            let status = SecItemDelete(query as CFDictionary)
            guard status == errSecSuccess || status == errSecItemNotFound else { throw MobileClientError.disconnected }; return
        }
        let data = try MobileWire.encoder().encode(connection)
        let attributes: [String: Any] = [kSecValueData as String: data, kSecAttrAccessible as String: kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly]
        var status = SecItemUpdate(query as CFDictionary, attributes as CFDictionary)
        if status == errSecItemNotFound { status = SecItemAdd(query.merging(attributes) { _, new in new } as CFDictionary, nil) }
        guard status == errSecSuccess, try self.connection() == connection else { throw MobileClientError.disconnected }
    }
    func load() throws -> RemoteLocalState {
        let url = directory.appendingPathComponent("drafts.json")
        guard FileManager.default.fileExists(atPath: url.path) else { return RemoteLocalState() }
        let data = try Data(contentsOf: url)
        guard data.count <= 8_000_000 else { throw MobileClientError.disconnected }
        return try MobileWire.decoder().decode(RemoteLocalState.self, from: data)
    }
    func save(state: RemoteLocalState) throws {
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true, attributes: [.protectionKey: FileProtectionType.complete])
        var url = directory
        var excluded = URLResourceValues(); excluded.isExcludedFromBackup = true; try url.setResourceValues(excluded)
        let data = try MobileWire.encoder().encode(state)
        guard data.count <= 8_000_000 else { throw MobileClientError.disconnected }
        let file = directory.appendingPathComponent("drafts.json")
        try data.write(to: file, options: [.atomic, .completeFileProtection])
        let handle = try FileHandle(forWritingTo: file)
        defer { try? handle.close() }
        try handle.synchronize()
    }
    static func token() throws -> String {
        var bytes = [UInt8](repeating: 0, count: 32)
        guard SecRandomCopyBytes(kSecRandomDefault, bytes.count, &bytes) == errSecSuccess else { throw MobileClientError.disconnected }
        return bytes.map { String(format: "%02x", $0) }.joined()
    }
}
