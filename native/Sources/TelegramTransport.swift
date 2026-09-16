import Foundation
import Security
import LocalAuthentication

protocol TelegramSecretStoring {
    var hasKey: Bool { get }
    func read() throws -> String
    func save(_ value: String) throws
    func remove() throws
}

struct TelegramKeychain: TelegramSecretStoring {
    let service: String
    init(profile: URL) { service = "local.proto-mind.telegram." + String(ChatHistoryFormat.hash(Data(profile.standardizedFileURL.path.utf8)).prefix(24)) }
    private var query: [String: Any] {
        [kSecClass as String: kSecClassGenericPassword, kSecAttrService as String: service, kSecAttrAccount as String: "bot-token"]
    }
    static func valid(_ value: String) -> Bool {
        value.range(of: "^[0-9]{5,20}:[A-Za-z0-9_-]{20,200}$", options: .regularExpression) != nil
    }
    var hasKey: Bool {
        var request = query; request[kSecReturnAttributes as String] = true
        let context = LAContext(); context.interactionNotAllowed = true
        request[kSecUseAuthenticationContext as String] = context
        let status = SecItemCopyMatching(request as CFDictionary, nil)
        return status == errSecSuccess || status == errSecInteractionNotAllowed
    }
    func read() throws -> String {
        var request = query; request[kSecReturnData as String] = true
        var result: CFTypeRef?
        guard SecItemCopyMatching(request as CFDictionary, &result) == errSecSuccess,
              let data = result as? Data, let value = String(data: data, encoding: .utf8), Self.valid(value) else {
            throw NativeError.message(L10n.pick("Добавьте токен бота в настройках Telegram.", "Add your bot token in Telegram settings."))
        }
        return value
    }
    func save(_ value: String) throws {
        guard Self.valid(value) else { throw NativeError.message(L10n.pick("Вставьте полный токен от BotFather.", "Paste the complete token from BotFather.")) }
        let attributes = [kSecValueData as String: Data(value.utf8)]
        var status = SecItemUpdate(query as CFDictionary, attributes as CFDictionary)
        if status == errSecItemNotFound {
            var item = query.merging(attributes) { _, new in new }
            item[kSecAttrAccessible as String] = kSecAttrAccessibleWhenUnlockedThisDeviceOnly
            item[kSecAttrLabel as String] = "Proto-Mind · Telegram"
            status = SecItemAdd(item as CFDictionary, nil)
        }
        guard status == errSecSuccess else { throw NativeError.message(L10n.pick("Связка ключей не сохранила токен Telegram.", "Keychain could not save the Telegram token.")) }
    }
    func remove() throws {
        let status = SecItemDelete(query as CFDictionary)
        guard status == errSecSuccess || status == errSecItemNotFound else { throw NativeError.message(L10n.pick("Не удалось удалить токен Telegram.", "Could not remove the Telegram token.")) }
    }
}

@MainActor
protocol TelegramTransport: AnyObject {
    func call(_ method: String, parameters: [String: JSONValue]) async throws -> JSONValue
    func close()
}

/// Telegram puts its token in the URL. Never expose URLSession errors or follow
/// redirects with that credential; neither cookies nor HTTP responses are cached.
final class TelegramHTTP: NSObject, TelegramTransport, URLSessionTaskDelegate, @unchecked Sendable {
    private let token: String
    private var session: URLSession!
    init(token: String) {
        self.token = token
        super.init()
        let configuration = URLSessionConfiguration.ephemeral
        configuration.urlCache = nil; configuration.httpCookieStorage = nil
        configuration.httpShouldSetCookies = false
        configuration.timeoutIntervalForRequest = 40; configuration.timeoutIntervalForResource = 50
        session = URLSession(configuration: configuration, delegate: self, delegateQueue: nil)
    }
    func urlSession(_ session: URLSession, task: URLSessionTask, willPerformHTTPRedirection response: HTTPURLResponse,
                    newRequest request: URLRequest, completionHandler: @escaping (URLRequest?) -> Void) { completionHandler(nil) }
    @MainActor func call(_ method: String, parameters: [String: JSONValue]) async throws -> JSONValue {
        guard ["getMe", "getWebhookInfo", "getUpdates", "sendMessage"].contains(method) else { throw NativeError.message("Unsupported Telegram method") }
        var request = URLRequest(url: URL(string: "https://api.telegram.org/bot" + token + "/" + method)!)
        request.httpMethod = "POST"; request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONEncoder().encode(parameters)
        let data: Data
        let response: URLResponse
        do { (data, response) = try await session.data(for: request) }
        catch {
            try Task.checkCancellation()
            throw NativeError.message(L10n.pick("Нет связи с Telegram. Проверьте сеть и включите подключение снова.", "Telegram is unreachable. Check your network and reconnect."))
        }
        guard let http = response as? HTTPURLResponse, http.statusCode == 200, data.count <= 2_000_000,
              let value = try? JSONDecoder().decode(JSONValue.self, from: data), value["ok"].flag else {
            throw NativeError.message(L10n.pick("Telegram отклонил запрос. Проверьте токен и убедитесь, что бот не подключён к другому приложению.", "Telegram rejected the request. Check the token and make sure this bot is not connected to another app."))
        }
        return value["result"]
    }
    @MainActor func close() { session.invalidateAndCancel() }
}
