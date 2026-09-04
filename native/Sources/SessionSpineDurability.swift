import CryptoKit
import Darwin
import Foundation

private let nativeSessionSpineApplicationID = "local.proto-mind.native"
private let nativeSessionSpineOwnerRole = "session_spine_forward_writer"

private func sessionSpineCanonical(_ value: JSONValue) throws -> Data {
    let encoder = JSONEncoder()
    encoder.outputFormatting = [.sortedKeys, .withoutEscapingSlashes]
    return try encoder.encode(value)
}

private func sessionSpineHash(_ value: JSONValue) throws -> String {
    SHA256.hash(data: try sessionSpineCanonical(value)).map { String(format: "%02x", $0) }.joined()
}

struct NativeSessionSpineInstallationIdentity: Codable, Equatable {
    let schema: String
    let formatVersion: Int
    let applicationID: String
    let installationID: String
    let role: String
    let ownerScope: String
    let ownerID: String
    let stableAcrossRelaunch: Bool
    let processIDBound: Bool
    let osUserBound: Bool
    let permissionGranted: Bool
    let executionAuthorityGranted: Bool
    let identityHash: String

    enum CodingKeys: String, CodingKey {
        case schema
        case formatVersion = "format_version"
        case applicationID = "application_id"
        case installationID = "installation_id"
        case role
        case ownerScope = "owner_scope"
        case ownerID = "owner_id"
        case stableAcrossRelaunch = "stable_across_relaunch"
        case processIDBound = "process_id_bound"
        case osUserBound = "os_user_bound"
        case permissionGranted = "permission_granted"
        case executionAuthorityGranted = "execution_authority_granted"
        case identityHash = "identity_hash"
    }

    private var derivation: JSONValue {
        .object([
            "schema": .string(schema),
            "format_version": .number(Double(formatVersion)),
            "application_id": .string(applicationID),
            "installation_id": .string(installationID),
            "role": .string(role),
            "owner_scope": .string(ownerScope),
        ])
    }

    var valueWithoutIdentityHash: JSONValue {
        .object([
            "schema": .string(schema),
            "format_version": .number(Double(formatVersion)),
            "application_id": .string(applicationID),
            "installation_id": .string(installationID),
            "role": .string(role),
            "owner_scope": .string(ownerScope),
            "owner_id": .string(ownerID),
            "stable_across_relaunch": .bool(stableAcrossRelaunch),
            "process_id_bound": .bool(processIDBound),
            "os_user_bound": .bool(osUserBound),
            "permission_granted": .bool(permissionGranted),
            "execution_authority_granted": .bool(executionAuthorityGranted),
        ])
    }

    var value: JSONValue {
        guard case .object(var fields) = valueWithoutIdentityHash else { return .null }
        fields["identity_hash"] = .string(identityHash)
        return .object(fields)
    }

    static func make(installationID: UUID) throws -> NativeSessionSpineInstallationIdentity {
        let identifier = installationID.uuidString.lowercased()
        let seed = NativeSessionSpineInstallationIdentity(
            schema: "proto_mind.native_session_spine_owner.v1",
            formatVersion: 1,
            applicationID: nativeSessionSpineApplicationID,
            installationID: identifier,
            role: nativeSessionSpineOwnerRole,
            ownerScope: "native_installation",
            ownerID: "",
            stableAcrossRelaunch: true,
            processIDBound: false,
            osUserBound: false,
            permissionGranted: false,
            executionAuthorityGranted: false,
            identityHash: ""
        )
        let owner = "native-session-spine:" + String(try sessionSpineHash(seed.derivation).prefix(32))
        let material = NativeSessionSpineInstallationIdentity(
            schema: seed.schema,
            formatVersion: seed.formatVersion,
            applicationID: seed.applicationID,
            installationID: seed.installationID,
            role: seed.role,
            ownerScope: seed.ownerScope,
            ownerID: owner,
            stableAcrossRelaunch: true,
            processIDBound: false,
            osUserBound: false,
            permissionGranted: false,
            executionAuthorityGranted: false,
            identityHash: ""
        )
        return NativeSessionSpineInstallationIdentity(
            schema: material.schema,
            formatVersion: material.formatVersion,
            applicationID: material.applicationID,
            installationID: material.installationID,
            role: material.role,
            ownerScope: material.ownerScope,
            ownerID: material.ownerID,
            stableAcrossRelaunch: material.stableAcrossRelaunch,
            processIDBound: material.processIDBound,
            osUserBound: material.osUserBound,
            permissionGranted: material.permissionGranted,
            executionAuthorityGranted: material.executionAuthorityGranted,
            identityHash: try sessionSpineHash(material.valueWithoutIdentityHash)
        )
    }

    func validated() throws -> NativeSessionSpineInstallationIdentity {
        guard let uuid = UUID(uuidString: installationID), uuid.uuidString.lowercased() == installationID,
              self == (try Self.make(installationID: uuid)) else {
            throw NativeError.message("Session Spine installation identity does not verify.")
        }
        return self
    }

    static func decode(_ data: Data) throws -> NativeSessionSpineInstallationIdentity {
        guard data.count > 0, data.count <= 16_384,
              case .object(let fields) = try JSONDecoder().decode(JSONValue.self, from: data),
              Set(fields.keys) == [
                "schema", "format_version", "application_id", "installation_id", "role", "owner_scope",
                "owner_id", "stable_across_relaunch", "process_id_bound", "os_user_bound",
                "permission_granted", "execution_authority_granted", "identity_hash",
              ] else {
            throw NativeError.message("Session Spine installation identity has an unknown format.")
        }
        let identity = try JSONDecoder().decode(NativeSessionSpineInstallationIdentity.self, from: data)
        guard try sessionSpineCanonical(identity.value) == data else {
            throw NativeError.message("Session Spine installation identity is not canonical JSON.")
        }
        return try identity.validated()
    }

    func encoded() throws -> Data {
        try sessionSpineCanonical(try validated().value)
    }
}

final class NativeSessionSpineInstallationStore {
    let directory: URL
    let url: URL
    private(set) var writeBlocked = false

    init(stateDirectory: URL) {
        directory = stateDirectory.appendingPathComponent("session_spine_identity", isDirectory: true)
        url = directory.appendingPathComponent("installation.json")
    }

    private func privateDirectory(create: Bool) throws -> Int32? {
        if create {
            try FileManager.default.createDirectory(
                at: directory,
                withIntermediateDirectories: true,
                attributes: [.posixPermissions: 0o700]
            )
        }
        var metadata = stat()
        guard lstat(directory.path, &metadata) == 0 else {
            if errno == ENOENT { return nil }
            throw NativeError.message("Session Spine identity directory is unavailable.")
        }
        guard (metadata.st_mode & S_IFMT) == S_IFDIR, metadata.st_mode & 0o077 == 0 else {
            throw NativeError.message("Session Spine identity directory must be private and non-symlinked.")
        }
        let descriptor = open(directory.path, O_RDONLY | O_DIRECTORY | O_NOFOLLOW)
        guard descriptor >= 0 else { throw NativeError.message("Session Spine identity directory cannot be opened safely.") }
        return descriptor
    }

    private func readFile(directory descriptor: Int32) throws -> Data? {
        var metadata = stat()
        let opened = "installation.json".withCString { openat(descriptor, $0, O_RDONLY | O_NOFOLLOW | O_NONBLOCK) }
        if opened < 0 {
            if errno == ENOENT { return nil }
            throw NativeError.message("Session Spine installation identity cannot be opened safely.")
        }
        defer { close(opened) }
        guard fstat(opened, &metadata) == 0, (metadata.st_mode & S_IFMT) == S_IFREG,
              metadata.st_mode & 0o077 == 0, metadata.st_size > 0, metadata.st_size <= 16_384 else {
            throw NativeError.message("Session Spine installation identity is unsafe or unbounded.")
        }
        var bytes = Data(count: Int(metadata.st_size))
        let count = bytes.count
        try bytes.withUnsafeMutableBytes { buffer in
            guard let base = buffer.baseAddress else {
                throw NativeError.message("Session Spine installation identity has no readable bytes.")
            }
            var offset = 0
            while offset < count {
                let readCount = Darwin.read(opened, base.advanced(by: offset), count - offset)
                if readCount < 0 && errno == EINTR { continue }
                guard readCount > 0 else {
                    throw NativeError.message("Session Spine installation identity readback is incomplete.")
                }
                offset += readCount
            }
        }
        return bytes
    }

    private func validateInventory(directory descriptor: Int32) throws {
        let names = try FileManager.default.contentsOfDirectory(atPath: directory.path)
        guard names.allSatisfy({ $0 == "installation.json" }) else {
            throw NativeError.message("Session Spine identity directory contains unknown recovery evidence; no cleanup was attempted.")
        }
        if names.contains("installation.json") {
            var metadata = stat()
            guard "installation.json".withCString({ fstatat(descriptor, $0, &metadata, AT_SYMLINK_NOFOLLOW) }) == 0,
                  (metadata.st_mode & S_IFMT) == S_IFREG else {
                throw NativeError.message("Session Spine identity path is not a regular file.")
            }
        }
    }

    func load() throws -> NativeSessionSpineInstallationIdentity? {
        do {
            guard let descriptor = try privateDirectory(create: false) else { return nil }
            defer { close(descriptor) }
            try validateInventory(directory: descriptor)
            guard let data = try readFile(directory: descriptor) else { return nil }
            return try NativeSessionSpineInstallationIdentity.decode(data)
        } catch {
            writeBlocked = true
            throw NativeError.message("Session Spine installation identity was not trusted; existing bytes remain unchanged: \(url.path)")
        }
    }

    func loadOrCreate() throws -> NativeSessionSpineInstallationIdentity {
        if let existing = try load() { return existing }
        guard !writeBlocked else {
            throw NativeError.message("Session Spine installation identity writes are blocked pending manual inspection.")
        }
        let identity = try NativeSessionSpineInstallationIdentity.make(installationID: UUID())
        let data = try identity.encoded()
        guard let descriptor = try privateDirectory(create: true) else {
            throw NativeError.message("Session Spine identity directory could not be created.")
        }
        defer { close(descriptor) }
        try validateInventory(directory: descriptor)
        let temporary = ".installation.\(UUID().uuidString.lowercased()).tmp"
        let file = temporary.withCString {
            openat(descriptor, $0, O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW, mode_t(0o600))
        }
        guard file >= 0 else { throw NativeError.message("Session Spine installation identity could not be prepared.") }
        var temporaryExists = true
        defer {
            close(file)
            if temporaryExists { temporary.withCString { _ = unlinkat(descriptor, $0, 0) } }
        }
        try data.withUnsafeBytes { buffer in
            guard let base = buffer.baseAddress else {
                throw NativeError.message("Session Spine installation identity had no bytes to write.")
            }
            var offset = 0
            while offset < data.count {
                let written = Darwin.write(file, base.advanced(by: offset), data.count - offset)
                if written < 0 && errno == EINTR { continue }
                guard written > 0 else {
                    throw NativeError.message("Session Spine installation identity write was incomplete.")
                }
                offset += written
            }
        }
        guard fsync(file) == 0 else {
            throw NativeError.message("Session Spine installation identity durability is unknown; inspect before retrying.")
        }
        let linked = temporary.withCString { source in
            "installation.json".withCString { destination in
                linkat(descriptor, source, descriptor, destination, 0)
            }
        }
        if linked != 0 && errno != EEXIST {
            throw NativeError.message("Session Spine installation identity could not be committed atomically.")
        }
        guard fsync(descriptor) == 0 else {
            throw NativeError.message("Session Spine installation identity directory durability is unknown.")
        }
        temporary.withCString { _ = unlinkat(descriptor, $0, 0) }
        temporaryExists = false
        _ = fsync(descriptor)
        guard let persisted = try load() else {
            throw NativeError.message("Session Spine installation identity did not survive exact readback.")
        }
        if linked == 0 {
            guard try persisted.encoded() == data else {
                throw NativeError.message("Session Spine installation identity did not survive exact readback.")
            }
        }
        return persisted
    }
}
