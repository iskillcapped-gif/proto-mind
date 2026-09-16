import Foundation
import Security
import LocalAuthentication

/// The secret never enters preferences, transcripts, Python RPCs or backups.
struct LiveVoiceKeychain {
    let service: String
    init(stateDirectory: URL) {
        service = "local.proto-mind.openai-live." + String(ChatHistoryFormat.hash(Data(stateDirectory.standardizedFileURL.path.utf8)).prefix(20))
    }
    private var query: [String: Any] {
        [kSecClass as String: kSecClassGenericPassword, kSecAttrService as String: service,
         kSecAttrAccount as String: "openai-api-key"]
    }
    var hasKey: Bool {
        var value = query
        value[kSecReturnAttributes as String] = true
        let context = LAContext()
        context.interactionNotAllowed = true
        value[kSecUseAuthenticationContext as String] = context
        let status = SecItemCopyMatching(value as CFDictionary, nil)
        return status == errSecSuccess || status == errSecInteractionNotAllowed
    }
    func read() throws -> String {
        var value = query
        value[kSecReturnData as String] = true
        var result: CFTypeRef?
        let status = SecItemCopyMatching(value as CFDictionary, &result)
        guard status == errSecSuccess, let data = result as? Data,
              let key = String(data: data, encoding: .utf8), !key.isEmpty else {
            throw NativeError.message(status == errSecItemNotFound ? L10n.text("Добавьте API-ключ OpenAI в настройках голоса.") : L10n.format("Связка ключей не предоставила API-ключ (\(status))."))
        }
        return key
    }
    func save(_ raw: String) throws {
        let key = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        guard key.hasPrefix("sk-"), key.count >= 20, key.count < 1024, !key.contains(where: \.isWhitespace) else {
            throw NativeError.message(L10n.text("Вставьте секретный API-ключ OpenAI целиком."))
        }
        let attributes: [String: Any] = [kSecValueData as String: Data(key.utf8)]
        var status = SecItemUpdate(query as CFDictionary, attributes as CFDictionary)
        if status == errSecItemNotFound {
            var value = query.merging(attributes) { _, new in new }
            value[kSecAttrAccessible as String] = kSecAttrAccessibleWhenUnlockedThisDeviceOnly
            value[kSecAttrLabel as String] = "Proto-Mind · OpenAI Live"
            status = SecItemAdd(value as CFDictionary, nil)
        }
        guard status == errSecSuccess else { throw NativeError.message(L10n.format("Не удалось сохранить ключ в Связке ключей (\(status)).")) }
    }
    func remove() throws {
        let status = SecItemDelete(query as CFDictionary)
        guard status == errSecSuccess || status == errSecItemNotFound else {
            throw NativeError.message(L10n.format("Не удалось удалить ключ из Связки ключей (\(status))."))
        }
    }
}
