import Foundation
import Network

struct MobileHTTPRequest {
    let method: String
    let path: String
    let query: [String: String]
    let headers: [String: String]
    let body: Data
    static func parse(_ bytes: Data) throws -> MobileHTTPRequest? {
        guard bytes.count <= MobileWire.maximumBody + 16_384 else { throw MobileHTTPFailure(status: 413, code: "request_too_large") }
        guard let boundary = bytes.range(of: Data("\r\n\r\n".utf8)) else {
            if bytes.count > 16_384 { throw MobileHTTPFailure(status: 413, code: "headers_too_large") }; return nil
        }
        guard boundary.lowerBound <= 16_384, let head = String(data: bytes[..<boundary.lowerBound], encoding: .utf8) else { throw MobileHTTPFailure.badRequest }
        let lines = head.components(separatedBy: "\r\n")
        let start = lines[0].components(separatedBy: " ")
        guard start.count == 3, ["GET", "POST"].contains(start[0]), start[2] == "HTTP/1.1",
              start[1].hasPrefix("/v1/"), !start[1].hasPrefix("//"), !start[1].contains("%"),
              let url = URLComponents(string: start[1]), url.fragment == nil else { throw MobileHTTPFailure.badRequest }
        var headers: [String: String] = [:]
        for line in lines.dropFirst() {
            guard let colon = line.firstIndex(of: ":"), colon != line.startIndex else { throw MobileHTTPFailure.badRequest }
            let name = String(line[..<colon]).lowercased(), value = String(line[line.index(after: colon)...]).trimmingCharacters(in: .whitespaces)
            guard name.allSatisfy({ $0.isASCII && ($0.isLetter || $0.isNumber || $0 == "-") }), headers[name] == nil,
                  !value.unicodeScalars.contains(where: { $0.value < 32 || $0.value == 127 }) else { throw MobileHTTPFailure.badRequest }
            headers[name] = value
        }
        guard headers["host"] != nil, headers["transfer-encoding"] == nil, headers["origin"] == nil,
              headers["expect"] == nil else { throw MobileHTTPFailure.badRequest }
        let length: Int
        if let value = headers["content-length"] {
            guard !value.isEmpty, value.allSatisfy({ $0.isASCII && $0.isNumber }), let count = Int(value), count <= MobileWire.maximumBody else { throw MobileHTTPFailure.badRequest }
            length = count
        } else { length = 0 }
        guard (start[0] == "GET" && length == 0) || (start[0] == "POST" && length > 0 && headers["content-type"]?.lowercased().split(separator: ";").first == "application/json") else { throw MobileHTTPFailure.badRequest }
        let available = bytes.count - boundary.upperBound
        guard available >= length else { return nil }
        guard available == length else { throw MobileHTTPFailure.badRequest } // No pipelining/smuggling.
        var query: [String: String] = [:]
        for item in url.queryItems ?? [] {
            guard let value = item.value, query[item.name] == nil else { throw MobileHTTPFailure.badRequest }
            query[item.name] = value
        }
        return MobileHTTPRequest(method: start[0], path: url.path, query: query, headers: headers, body: Data(bytes[boundary.upperBound...]))
    }
}

struct MobileHTTPFailure: Error {
    let status: Int
    let code: String
    static let badRequest = MobileHTTPFailure(status: 400, code: "bad_request")
}

struct MobileHTTPResponse {
    let status: Int
    let data: Data
    static func json<T: Encodable>(_ value: T, status: Int = 200) -> Self {
        Self(status: status, data: (try? MobileWire.encoder().encode(value)) ?? Data("{}".utf8))
    }
    static func error(_ status: Int, _ code: String) -> Self { .json(MobileAPIError(error: code), status: status) }
    var bytes: Data {
        var result = Data("HTTP/1.1 \(status) \(status < 400 ? "OK" : "Error")\r\nContent-Type: application/json; charset=utf-8\r\nContent-Length: \(data.count)\r\nCache-Control: no-store\r\nX-Content-Type-Options: nosniff\r\nConnection: close\r\n\r\n".utf8)
        result.append(data); return result
    }
}

/// Loopback only. HTTPS is terminated by the operator's private Tailscale Serve
/// connection. This listener is never reachable from a LAN/public interface.
final class MobileHTTPServer {
    typealias Handler = (MobileHTTPRequest, @escaping (MobileHTTPResponse) -> Void) -> Void
    private let queue = DispatchQueue(label: "app.protomind.mobile-http")
    private var listener: NWListener?
    private var peers: [UUID: MobileHTTPPeer] = [:]
    private var epoch = UUID()
    func start(port: UInt16 = MobileWire.port, handler: @escaping Handler, ready: @escaping (Result<UInt16, Error>) -> Void) throws {
        let params = NWParameters.tcp
        params.requiredLocalEndpoint = .hostPort(host: .ipv4(.loopback), port: NWEndpoint.Port(rawValue: port)!)
        params.allowLocalEndpointReuse = false
        let incoming = try NWListener(using: params)
        queue.async {
            let current = UUID(); self.epoch = current; self.listener = incoming
            incoming.stateUpdateHandler = { state in
                guard self.epoch == current else { return }
                switch state {
                case .ready: ready(.success(incoming.port?.rawValue ?? port))
                case .failed(let error): self.close(); ready(.failure(error))
                default: break
                }
            }
            incoming.newConnectionHandler = { connection in
                guard self.epoch == current, self.peers.count < 16 else { connection.cancel(); return }
                let id = UUID()
                let peer = MobileHTTPPeer(connection: connection, queue: self.queue, handler: handler) { self.peers.removeValue(forKey: id) }
                self.peers[id] = peer; peer.start()
            }
            incoming.start(queue: self.queue)
        }
    }
    func stop() { queue.async { self.close() } }
    private func close() {
        epoch = UUID(); listener?.stateUpdateHandler = nil; listener?.newConnectionHandler = nil; listener?.cancel(); listener = nil
        let current = Array(peers.values); peers.removeAll(); current.forEach { $0.close() }
    }
}

private final class MobileHTTPPeer {
    let connection: NWConnection
    let queue: DispatchQueue
    let handler: MobileHTTPServer.Handler
    let finished: () -> Void
    var bytes = Data()
    var handled = false
    var closed = false
    var timeout: DispatchWorkItem?
    init(connection: NWConnection, queue: DispatchQueue, handler: @escaping MobileHTTPServer.Handler, finished: @escaping () -> Void) {
        self.connection = connection; self.queue = queue; self.handler = handler; self.finished = finished
    }
    func start() {
        let timeout = DispatchWorkItem { [weak self] in self?.close() }; self.timeout = timeout
        queue.asyncAfter(deadline: .now() + 15, execute: timeout)
        connection.stateUpdateHandler = { [weak self] state in
            if case .failed = state { self?.close() }
            if case .cancelled = state { self?.close() }
        }
        connection.start(queue: queue); read()
    }
    func read() {
        connection.receive(minimumIncompleteLength: 1, maximumLength: 16_384) { [weak self] data, _, complete, error in
            guard let self, !self.closed, !self.handled else { return }
            if let data { self.bytes.append(data) }
            do {
                if let request = try MobileHTTPRequest.parse(self.bytes) {
                    self.handled = true
                    self.handler(request) { [weak self] response in
                        guard let self else { return }; self.queue.async { self.reply(response) }
                    }
                } else if complete || error != nil { self.close() }
                else { self.read() }
            } catch let failure as MobileHTTPFailure { self.reply(.error(failure.status, failure.code)) }
            catch { self.reply(.error(400, "bad_request")) }
        }
    }
    func reply(_ response: MobileHTTPResponse) {
        guard !closed else { return }; handled = true
        connection.send(content: response.bytes, completion: .contentProcessed { [weak self] _ in self?.close() })
    }
    func close() {
        guard !closed else { return }; closed = true; timeout?.cancel(); timeout = nil
        connection.cancel(); finished()
    }
}
