import AppKit
import Foundation
import SwiftUI

struct CodexUsageSnapshot: Decodable {
    struct Reset: Decodable {
        let accountRef: String
        let attemptKey: String
        let outcome: String
        let creditId: String?
        var pending: Bool { outcome == "pending" }
        var valid: Bool {
            accountRef.count == 64 && accountRef.allSatisfy { "0123456789abcdef".contains($0) }
                && ((attemptKey.isEmpty && outcome.isEmpty)
                    || (UUID(uuidString: attemptKey) != nil && ["pending", "reset", "alreadyRedeemed", "nothingToReset", "noCredit"].contains(outcome)))
        }
    }
    struct Window: Decodable, Identifiable {
        let kind: String
        let usedPercent: Double?
        let remainingPercent: Double?
        let windowMinutes: Int?
        let resetsAt: Double?
        var id: String { kind }
        var title: String {
            guard let minutes = windowMinutes else { return kind == "primary" ? "Основной лимит" : "Дополнительный лимит" }
            if minutes == 10080 { return "Неделя" }
            if minutes % 1440 == 0 { return "\(minutes / 1440) дн." }
            if minutes % 60 == 0 { return "\(minutes / 60) ч" }
            return "\(minutes) мин"
        }
        var remaining: Double? {
            guard let value = remainingPercent, value.isFinite, (0...100).contains(value) else { return nil }
            return value
        }
        var used: Double? {
            guard let value = usedPercent, value.isFinite, value >= 0 else { return nil }
            return value
        }
        var usedLabel: String {
            guard let used else { return "—" }
            return used > 100 ? "100%+" : "\(used.formatted(.number.precision(.fractionLength(0...1))))%"
        }
        var remainingLabel: String {
            guard let remaining else { return "—" }
            return "\(remaining.formatted(.number.precision(.fractionLength(0...1))))%"
        }
    }
    struct Bucket: Decodable, Identifiable {
        let id: String
        let name: String
        let plan: String
        let windows: [Window]
    }
    struct Activity: Decodable {
        struct Summary: Decodable {
            let lifetimeTokens: Int?
            let peakDailyTokens: Int?
            let currentStreakDays: Int?
        }
        struct Day: Decodable, Identifiable {
            let date: String
            let tokens: Int
            var id: String { date }
        }
        let summary: Summary
        let daily: [Day]
    }
    let schema: String
    let connected: Bool
    let plan: String
    let email: String
    let buckets: [Bucket]
    let resetCredits: Int?
    let reset: Reset?
    let resetError: String?
    let activity: Activity?
    let limitsError: String
    let activityError: String
    let checkedAt: Double
    let limitsUpdatedAt: Double?
    let activityUpdatedAt: Double?

    var canReset: Bool {
        guard connected, (resetError ?? "").isEmpty, let reset, reset.valid else { return false }
        return reset.pending || ((resetCredits ?? 0) > 0 && limitsError.isEmpty)
    }

    var compactBucket: Bucket? {
        buckets.first { $0.id == "codex" && !$0.windows.isEmpty } ?? buckets.first { !$0.windows.isEmpty }
    }

    func sameAccount(as other: Self) -> Bool {
        connected && other.connected && !email.isEmpty && email.caseInsensitiveCompare(other.email) == .orderedSame && plan == other.plan
    }

    // Background reads update quota only. Preserve separately fetched activity
    // and reset-attempt details, but never carry them across account changes.
    func withDetails(from other: Self) -> Self {
        guard sameAccount(as: other) else { return self }
        return Self(schema: schema, connected: connected, plan: plan, email: email, buckets: buckets,
                    resetCredits: resetCredits, reset: other.reset, resetError: other.resetError,
                    activity: other.activity, limitsError: limitsError, activityError: other.activityError,
                    checkedAt: checkedAt, limitsUpdatedAt: limitsUpdatedAt, activityUpdatedAt: other.activityUpdatedAt)
    }

    func limitsAreStale(at date: Date) -> Bool {
        guard let updated = limitsUpdatedAt, updated.isFinite else { return true }
        return date.timeIntervalSince1970 - updated > 90
            || buckets.flatMap(\.windows).contains { window in
                guard let reset = window.resetsAt else { return false }
                // A past reset reported by the service is not proof of zero usage.
                return reset <= date.timeIntervalSince1970
            }
    }

    static func parse(_ raw: JSONValue) throws -> Self {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let value = try decoder.decode(Self.self, from: JSONEncoder().encode(raw))
        guard value.schema == "proto_mind.codex_usage.v1", value.buckets.count <= 64 else {
            throw NativeError.message("Не удалось прочитать данные об использовании Codex.")
        }
        return value
    }
}

struct CodexResetAttempt {
    let key: String
    let accountRef: String
    let previousKey: String
    let creditId: String?

    init(_ reset: CodexUsageSnapshot.Reset) {
        key = reset.pending ? reset.attemptKey : UUID().uuidString.lowercased()
        accountRef = reset.accountRef; previousKey = reset.attemptKey; creditId = reset.creditId
    }

    var parameters: [String: JSONValue] {
        ["account_ref": .string(accountRef), "expected_attempt": .string(previousKey),
         "idempotency_key": .string(key), "credit_id": creditId.map(JSONValue.string) ?? .null,
         "confirmation": .string("USE ONE CODEX RESET")]
    }
}

@MainActor
final class CodexUsageModel: ObservableObject {
    @Published private(set) var snapshot: CodexUsageSnapshot?
    @Published private(set) var refreshing = false
    @Published private(set) var resetting = false
    @Published private(set) var error: String?
    @Published private(set) var resetMessage: String?
    @Published private(set) var summary: CodexUsageSnapshot?
    @Published private(set) var refreshingLimits = false
    @Published private(set) var summaryError: String?
    private var generation = UUID()
    private var lastLimitsAttempt: Date?
    private let limitsRequest: (AppModel) async throws -> JSONValue
    private let usageRequest: (AppModel) async throws -> JSONValue

    init(usageRequest: @escaping (AppModel) async throws -> JSONValue = { try await $0.client.request("account_usage") },
         limitsRequest: @escaping (AppModel) async throws -> JSONValue = { try await $0.client.request("account_limits") }) {
        self.usageRequest = usageRequest
        self.limitsRequest = limitsRequest
    }

    var displaySnapshot: CodexUsageSnapshot? {
        guard let summary else { return snapshot }
        guard let snapshot else { return summary }
        return summary.withDetails(from: snapshot)
    }

    func clear() {
        generation = UUID(); lastLimitsAttempt = nil
        snapshot = nil; summary = nil; error = nil; summaryError = nil; resetMessage = nil
    }

    private func acceptSummary(_ value: CodexUsageSnapshot?) {
        if let value, let summary, value.checkedAt < summary.checkedAt { return }
        summary = value
        summaryError = value?.limitsError.isEmpty == false ? value?.limitsError : nil
    }

    func refreshLimits(app: AppModel, minimumInterval: TimeInterval = 30, now: Date = .now) async {
        guard !refreshingLimits, !refreshing, !resetting, app.cloudConsent, !app.connecting,
              !app.loginPending, !app.privateBackupRestartRequired,
              lastLimitsAttempt.map({ now.timeIntervalSince($0) >= minimumInterval }) ?? true else { return }
        let requestGeneration = generation
        lastLimitsAttempt = now; refreshingLimits = true
        defer { refreshingLimits = false }
        do {
            let raw = try await limitsRequest(app)
            // Leaving the foreground stops future polling, not the delivery of
            // an already completed, read-only request for the same account.
            guard requestGeneration == generation, app.cloudConsent,
                  !app.connecting, !app.loginPending, !app.privateBackupRestartRequired else { return }
            acceptSummary(try CodexUsageSnapshot.parse(raw))
        } catch {
            guard requestGeneration == generation else { return }
            summaryError = "Не удалось обновить лимиты."
        }
    }

    static func message(for outcome: String) -> String {
        switch outcome {
        case "reset": return "Сброс использован."
        case "alreadyRedeemed": return "Этот сброс уже был применён. Повторно он не расходуется."
        case "nothingToReset": return "Сейчас нет лимита, который можно сбросить. Сброс не потрачен."
        case "noCredit": return "Доступных сбросов больше нет."
        default: return "Результат сброса пока неизвестен. Проверьте эту попытку повторно."
        }
    }

    func consume(_ attempt: CodexResetAttempt, app: AppModel) async {
        guard !refreshing, !resetting, !app.busy, !app.connecting, !app.client.turnOutstanding,
              !app.privateBackupRestartRequired, let value = displaySnapshot, value.canReset,
              value.reset?.accountRef == attempt.accountRef,
              value.reset?.attemptKey == attempt.previousKey else { return }
        generation = UUID()
        resetting = true; app.busy = true; error = nil; resetMessage = nil
        defer { resetting = false; app.busy = false }
        do {
            let result = try await app.client.request("account_reset", attempt.parameters)
            resetMessage = Self.message(for: result["outcome"].text)
            self.snapshot = result["usage"].isNull ? nil : try CodexUsageSnapshot.parse(result["usage"])
            acceptSummary(self.snapshot)
            if !result["refresh_error"].text.isEmpty { error = result["refresh_error"].text }
        } catch {
            self.snapshot = nil
            acceptSummary(nil)
            self.error = "Не удалось подтвердить результат. Обновите лимиты: незавершённую попытку можно проверить повторно."
        }
    }

    func refresh(app: AppModel) async {
        guard !refreshing, !resetting, app.cloudConsent, !app.connecting, !app.loginPending, !app.privateBackupRestartRequired else { return }
        let requestGeneration = generation
        refreshing = true; error = nil; resetMessage = nil
        lastLimitsAttempt = .now
        defer { refreshing = false }
        do {
            let value = try await usageRequest(app)
            guard requestGeneration == generation, app.cloudConsent, !app.connecting,
                  !app.loginPending, !app.privateBackupRestartRequired else { return }
            snapshot = try CodexUsageSnapshot.parse(value)
            acceptSummary(snapshot)
            if let reset = snapshot?.reset, !reset.outcome.isEmpty { resetMessage = Self.message(for: reset.outcome) }
        } catch {
            guard requestGeneration == generation else { return }
            // Retain this account's previous reading with a visible error.
            // Explicit account changes already clear both snapshots.
            self.error = "Не удалось обновить данные аккаунта."
            summaryError = self.error
        }
    }
}
