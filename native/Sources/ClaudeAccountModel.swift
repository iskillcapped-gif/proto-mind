import Foundation
import Combine

struct ClaudeModelOption: Decodable, Identifiable {
    let id: String
    let alias: String
    let resolvedId: String
    let title: String
    let description: String
    let efforts: [String]
    var isDefault: Bool { id.isEmpty }
    func matches(_ selection: String) -> Bool { selection == id || (!alias.isEmpty && selection == alias) }
    var menuTitle: String { isDefault ? L10n.text("Автоматически") : title }
}

struct ClaudeQuotaWindow: Decodable, Identifiable {
    let id: String
    let title: String
    let windowMinutes: Int
    let usedPercent: Double?
    let remainingPercent: Double?
    let resetsAt: Double?
    var periodTitle: String { windowMinutes == 300 ? L10n.pick("5 ч", "5 h") : L10n.text("Неделя") }
    var displayTitle: String { title.isEmpty ? periodTitle : "\(title) · \(periodTitle)" }
    var remainingLabel: String { remainingPercent.map { "\($0.formatted(.number.precision(.fractionLength(0...1)).locale(L10n.locale)))%" } ?? "—" }
    var usedLabel: String { usedPercent.map { "\($0.formatted(.number.precision(.fractionLength(0...1)).locale(L10n.locale)))%" } ?? "—" }
}

struct ClaudeAccountSnapshot: Decodable {
    let schema: String
    let installed: Bool
    let connected: Bool
    let email: String
    let plan: String
    let accountRef: String
    var models: [ClaudeModelOption]
    var windows: [ClaudeQuotaWindow]
    let modelsError: String
    let limitsError: String
    let limitsAvailable: Bool
    let checkedAt: Double
    var modelsUpdatedAt: Double?
    var limitsUpdatedAt: Double?

    var compactWindows: [ClaudeQuotaWindow] { windows.filter { ["seven_day", "five_hour"].contains($0.id) } }
    func model(_ selection: String) -> ClaudeModelOption? { models.first { $0.matches(selection) } }
    func limitsAreStale(at date: Date) -> Bool {
        guard limitsError.isEmpty, let updated = limitsUpdatedAt else { return true }
        return date.timeIntervalSince1970 - updated > 150 || windows.contains { ($0.resetsAt ?? .infinity) <= date.timeIntervalSince1970 }
    }
    static func parse(_ raw: JSONValue) throws -> Self {
        let decoder = JSONDecoder(); decoder.keyDecodingStrategy = .convertFromSnakeCase
        let value = try decoder.decode(Self.self, from: JSONEncoder().encode(raw))
        guard value.schema == "proto_mind.claude_account.v1", value.models.count <= 64, value.windows.count <= 36,
              Set(value.models.map(\.id)).count == value.models.count,
              Set(value.windows.map(\.id)).count == value.windows.count,
              value.checkedAt.isFinite,
              value.windows.allSatisfy({ window in
                  (window.remainingPercent.map { $0.isFinite && (0...100).contains($0) } ?? true)
                      && (window.usedPercent.map { $0.isFinite && $0 >= 0 } ?? true)
                      && (window.resetsAt.map { $0.isFinite && $0 > 0 } ?? true)
              }) else { throw NativeError.message("Invalid Claude metadata") }
        return value
    }
}

/// Metadata changes are observed by its controls, never by the transcript or
/// task state. No quotas or credentials are persisted in conversation history.
@MainActor final class ClaudeAccountModel: ObservableObject {
    @Published private(set) var snapshot: ClaudeAccountSnapshot?
    @Published private(set) var refreshing = false
    @Published private(set) var error: String?
    private var generation = UUID()
    private var lastAttempt: Date?
    private let request: (AppModel) async throws -> JSONValue
    init(request: @escaping (AppModel) async throws -> JSONValue = { try await $0.serviceClient.request("claude_metadata") }) { self.request = request }

    func clear() { generation = UUID(); snapshot = nil; error = nil; lastAttempt = nil }
    func refresh(app: AppModel, minimumInterval: TimeInterval = 60, now: Date = .now) async {
        guard !refreshing, !app.claudeAuthenticating, !app.privateBackupRestartRequired,
              minimumInterval <= 0 || (lastAttempt.map({ now.timeIntervalSince($0) >= minimumInterval || now < $0 }) ?? true) else { return }
        let expected = generation
        lastAttempt = now; refreshing = true
        defer { refreshing = false }
        do {
            var value = try ClaudeAccountSnapshot.parse(try await request(app))
            guard expected == generation, !app.claudeAuthenticating, !app.privateBackupRestartRequired else { return }
            if let previous = snapshot, value.connected, !value.accountRef.isEmpty, value.accountRef == previous.accountRef {
                if !value.modelsError.isEmpty { value.models = previous.models; value.modelsUpdatedAt = previous.modelsUpdatedAt }
                if !value.limitsError.isEmpty { value.windows = previous.windows; value.limitsUpdatedAt = previous.limitsUpdatedAt }
            }
            snapshot = value; error = nil
        } catch {
            guard expected == generation else { return }
            self.error = L10n.pick("Не удалось обновить данные Claude.", "Could not refresh Claude account data.")
        }
    }
    func label(for selection: String) -> String {
        snapshot?.model(selection)?.title ?? ClaudeSelection.title(selection)
    }
    var compactLabel: String {
        guard let snapshot, snapshot.connected else { return "Claude · —" }
        let windows = snapshot.compactWindows
        return windows.isEmpty ? "Claude · —" : "Claude · " + L10n.pick("Ост. ", "Left ") + windows.map { "\($0.periodTitle) \($0.remainingLabel)" }.joined(separator: " · ")
    }
}
