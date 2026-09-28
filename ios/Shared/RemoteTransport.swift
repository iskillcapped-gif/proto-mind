import Foundation

struct RemoteHTTPError: Error { let status: Int; let code: String }

protocol RemoteRequesting {
    func request(endpoint: String, path: String, token: String, body: Data?) async throws -> Data
}

/// An ephemeral session with no cookies, cache, credential store, redirects or
/// automatic mutation retries. Pairing never gives an endpoint a provider key.
final class RemoteTransport: NSObject, RemoteRequesting, URLSessionTaskDelegate {
    private lazy var session: URLSession = {
        let config = URLSessionConfiguration.ephemeral
        config.httpCookieStorage = nil; config.httpShouldSetCookies = false
        config.urlCredentialStorage = nil; config.urlCache = nil
        config.requestCachePolicy = .reloadIgnoringLocalCacheData
        config.timeoutIntervalForRequest = 20; config.timeoutIntervalForResource = 25
        return URLSession(configuration: config, delegate: self, delegateQueue: nil)
    }()
    var allowLoopback = false // Injected only in tests / DEBUG simulator runs.
    func request(endpoint: String, path: String, token: String, body: Data?) async throws -> Data {
        guard let base = MobileWire.endpoint(endpoint, allowLoopback: allowLoopback), path.hasPrefix("/v1/"),
              let url = URL(string: path, relativeTo: base)?.absoluteURL,
              url.host == base.host, url.scheme == base.scheme, url.port == base.port else { throw MobileClientError.disconnected }
        var request = URLRequest(url: url)
        request.httpMethod = body == nil ? "GET" : "POST"
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        if !token.isEmpty { request.setValue("Bearer " + token, forHTTPHeaderField: "Authorization") }
        if let body { request.setValue("application/json", forHTTPHeaderField: "Content-Type"); request.httpBody = body }
        let (bytes, response) = try await session.bytes(for: request)
        guard let http = response as? HTTPURLResponse,
              http.value(forHTTPHeaderField: "Content-Type")?.lowercased().hasPrefix("application/json") == true,
              response.expectedContentLength <= 16_000_000 else { throw MobileClientError.disconnected }
        var data = Data()
        for try await byte in bytes {
            guard data.count < 16_000_000 else { throw MobileClientError.disconnected }
            data.append(byte)
        }
        guard (200..<300).contains(http.statusCode) else {
            throw RemoteHTTPError(status: http.statusCode, code: (try? MobileWire.decoder().decode(MobileAPIError.self, from: data).error) ?? "connection_unavailable")
        }
        return data
    }
    func urlSession(_ session: URLSession, task: URLSessionTask, willPerformHTTPRedirection response: HTTPURLResponse,
                    newRequest request: URLRequest, completionHandler: @escaping (URLRequest?) -> Void) { completionHandler(nil) }
    func close() { session.invalidateAndCancel() }
}

struct RemoteConnection: Codable, Equatable {
    let endpoint: String
    let deviceID: UUID
    let token: String
}

struct RemoteLocalState: Codable {
    var drafts: [String: String] = [:]
    var pending: MobileCommand?
}

protocol RemotePersistence {
    func connection() throws -> RemoteConnection?
    func save(connection: RemoteConnection?) throws
    func load() throws -> RemoteLocalState
    func save(state: RemoteLocalState) throws
}
