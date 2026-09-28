import Foundation
import CryptoKit

// Shared verbatim by the Mac target and the iPhone Xcode target. No provider
// credentials, model instructions, editor drafts or raw tool output cross this API.
enum MobileWire {
    static let version = 1
    static let port: UInt16 = 8765
    static let maximumBody = 96 * 1024
    static let messageLimit = 100_000
    static func encoder() -> JSONEncoder {
        let value = JSONEncoder()
        // Integer milliseconds give commands the same fingerprint on both
        // devices, regardless of floating-point Date round-trip precision.
        value.dateEncodingStrategy = .custom { date, encoder in
            var field = encoder.singleValueContainer()
            let stamp = (date.timeIntervalSince1970 * 1000).rounded()
            guard stamp.isFinite, stamp >= Double(Int64.min), stamp < Double(Int64.max) else {
                throw EncodingError.invalidValue(date, .init(codingPath: encoder.codingPath, debugDescription: "Date outside the mobile protocol range"))
            }
            try field.encode(Int64(stamp))
        }
        value.outputFormatting = [.sortedKeys]; return value
    }
    static func decoder() -> JSONDecoder {
        let value = JSONDecoder(); value.dateDecodingStrategy = .millisecondsSince1970; return value
    }
    static func hash(_ data: Data) -> String { SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined() }
    static func validSecret(_ text: String) -> Bool { text.utf8.count == 64 && text.allSatisfy { "0123456789abcdef".contains($0) } }
    static func constantEqual(_ a: String, _ b: String) -> Bool {
        let left = Array(a.utf8), right = Array(b.utf8)
        guard left.count == right.count else { return false }
        return zip(left, right).reduce(UInt8(0)) { $0 | ($1.0 ^ $1.1) } == 0
    }
    static func endpoint(_ text: String, allowLoopback: Bool = false) -> URL? {
        guard let parts = URLComponents(string: text.trimmingCharacters(in: .whitespacesAndNewlines)),
              let host = parts.host, !host.isEmpty, parts.user == nil, parts.password == nil,
              parts.query == nil, parts.fragment == nil, ["", "/"].contains(parts.path),
              parts.scheme == "https" || (allowLoopback && parts.scheme == "http" && ["127.0.0.1", "localhost", "::1"].contains(host)),
              let url = parts.url else { return nil }
        return url
    }
}

struct MobilePairing: Codable, Equatable {
    var version = MobileWire.version
    let endpoint: String
    let code: String
    let expiresAt: Date
    var link: String? {
        guard let data = try? MobileWire.encoder().encode(self) else { return nil }
        return "protomind-remote://pair#" + data.base64EncodedString()
            .replacingOccurrences(of: "+", with: "-").replacingOccurrences(of: "/", with: "_").replacingOccurrences(of: "=", with: "")
    }
    static func parse(_ text: String, now: Date = Date(), allowLoopback: Bool = false) throws -> MobilePairing {
        guard text.utf8.count < 4096, let parts = URLComponents(string: text.trimmingCharacters(in: .whitespacesAndNewlines)),
              parts.scheme == "protomind-remote", parts.host == "pair", parts.query == nil, let fragment = parts.fragment else { throw MobileClientError.invalidPairing }
        var encoded = fragment.replacingOccurrences(of: "-", with: "+").replacingOccurrences(of: "_", with: "/")
        encoded += String(repeating: "=", count: (4 - encoded.count % 4) % 4)
        guard let data = Data(base64Encoded: encoded), let value = try? MobileWire.decoder().decode(MobilePairing.self, from: data),
              value.version == MobileWire.version, MobileWire.endpoint(value.endpoint, allowLoopback: allowLoopback) != nil,
              MobileWire.validSecret(value.code), value.expiresAt > now,
              value.expiresAt.timeIntervalSince(now) <= 660 else { throw MobileClientError.invalidPairing }
        return value
    }
}

struct MobilePairRequest: Codable {
    var version = MobileWire.version
    let code: String
    let deviceID: UUID
    let name: String
    let token: String
}

struct MobileServerInfo: Codable {
    var version = MobileWire.version
    let name: String
    let status: String
}

struct MobileChat: Codable, Identifiable, Equatable {
    let id: UUID
    let title: String
    let projectID: String
    let projectName: String
    let provider: String
    let model: String
    let effort: String
    let account: String
    let fullAccess: Bool
    let status: String
    let runID: String?
    let updatedAt: Date
    let canUpdate: Bool
}

struct MobileChatList: Codable {
    var version = MobileWire.version
    let chats: [MobileChat]
}

struct MobileMessage: Codable, Identifiable, Equatable {
    let id: UUID
    let role: String
    let text: String
    let createdAt: Date
    let isError: Bool
    let truncated: Bool
    let updates: [MobileUpdate]
    let updatesTruncated: Bool
}

struct MobileUpdate: Codable, Identifiable, Equatable {
    let id: UUID
    let text: String
    let state: String
}

struct MobileTranscript: Codable {
    let chat: MobileChat
    let messages: [MobileMessage]
    let before: UUID?
    let liveText: String
    let liveTruncated: Bool
    let activity: String
}

struct MobileCommand: Codable, Equatable {
    enum Kind: String, Codable { case send, stop, create }
    let id: UUID
    let conversationID: UUID
    let kind: Kind
    let text: String
    let expectedRunID: String?
    let createdAt: Date
    var fingerprint: String { MobileWire.hash((try? MobileWire.encoder().encode(self)) ?? Data()) }
    func valid(now: Date) -> Bool {
        guard (-30...600).contains(now.timeIntervalSince(createdAt)),
              (expectedRunID?.utf8.count ?? 0) <= 200, !text.contains("\0") else { return false }
        switch kind {
        case .send: return !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && text.unicodeScalars.count <= 20_000
        case .stop: return text.isEmpty && expectedRunID != nil
        case .create: return !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && text.count <= 160 && expectedRunID == nil
        }
    }
}

struct MobileReceipt: Codable, Equatable, Identifiable {
    enum Status: String, Codable { case reserved, accepted, rejected, unknown }
    let id: UUID
    let deviceID: UUID
    let fingerprint: String
    let conversationID: UUID
    let createdAt: Date
    var status: Status
    var code: String
    var createdConversationID: UUID?
}

struct MobileAPIError: Codable { let error: String }

enum MobileClientError: LocalizedError {
    case invalidPairing, disconnected, rejected(String), uncertain
    var errorDescription: String? {
        switch self {
        case .invalidPairing: return "This pairing link is invalid or expired. Create a new link on your Mac."
        case .disconnected: return "Could not reach your Mac. Keep Proto-Mind open and check the connection."
        case .rejected(let code): return code
        case .uncertain: return "Delivery is unconfirmed. Check its status before sending another message."
        }
    }
}
