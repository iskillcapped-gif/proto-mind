import AppKit
import Foundation
import SwiftUI

struct CodexUsageSnapshot: Decodable {
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
    let activity: Activity?
    let limitsError: String
    let activityError: String
    let checkedAt: Double
    let limitsUpdatedAt: Double?
    let activityUpdatedAt: Double?

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

@MainActor
final class CodexUsageModel: ObservableObject {
    @Published private(set) var snapshot: CodexUsageSnapshot?
    @Published private(set) var refreshing = false
    @Published private(set) var error: String?

    func clear() { snapshot = nil; error = nil }

    func refresh(app: AppModel) async {
        guard !refreshing, !app.busy, !app.connecting, !app.client.turnOutstanding, !app.privateBackupRestartRequired else { return }
        refreshing = true; app.busy = true; error = nil
        defer { refreshing = false; app.busy = false }
        do {
            let value = try await app.client.request("account_usage")
            guard !Task.isCancelled else { return }
            snapshot = try CodexUsageSnapshot.parse(value)
        } catch {
            // Do not show another account's old totals after a failed auth refresh.
            snapshot = nil
            self.error = error.localizedDescription
        }
    }
}

struct CodexUsageView: View {
    @ObservedObject var app: AppModel
    @ObservedObject var usage: CodexUsageModel

    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            HStack {
                Text("Использование Codex").font(.system(size: 22, weight: .semibold))
                Spacer()
                Button { app.showCodexUsage = false } label: { Image(systemName: "xmark") }.keyboardShortcut(.cancelAction)
            }
            ScrollView {
                VStack(alignment: .leading, spacing: 20) {
                    if let value = usage.snapshot {
                        if value.connected {
                            VStack(alignment: .leading, spacing: 5) {
                                Text([value.email, value.plan.capitalized].filter { !$0.isEmpty }.joined(separator: " · ")).font(.callout)
                                Text("Лимиты этого аккаунта общие для Codex, в том числе работы вне Proto-Mind.").font(.callout).foregroundStyle(.secondary)
                            }
                            if !value.limitsError.isEmpty { unavailable(value.limitsError) }
                            if value.buckets.isEmpty && value.limitsError.isEmpty { unavailable("Codex не предоставил сведения о лимитах.") }
                            ForEach(value.buckets) { bucket in
                                VStack(alignment: .leading, spacing: 15) {
                                    Text(bucket.name).font(.headline)
                                    if bucket.windows.isEmpty { unavailable("Данные по периодам пока недоступны.") }
                                    ForEach(bucket.windows) { window in quota(window) }
                                }.padding(16).background(.quaternary, in: RoundedRectangle(cornerRadius: 12))
                            }
                            if let count = value.resetCredits {
                                Text("Доступно сбросов лимита: \(count)").font(.callout).foregroundStyle(.secondary)
                            }
                            if let timestamp = value.limitsUpdatedAt {
                                Text("Лимиты проверены: \(Date(timeIntervalSince1970: timestamp).formatted(date: .abbreviated, time: .shortened))")
                                    .font(.caption).foregroundStyle(.secondary)
                            }
                            DisclosureGroup("Активность аккаунта") {
                                if !value.activityError.isEmpty { unavailable(value.activityError) }
                                else if let activity = value.activity {
                                    VStack(alignment: .leading, spacing: 12) {
                                        metric("Токенов за всё время", value: activity.summary.lifetimeTokens)
                                        metric("Максимум токенов за день", value: activity.summary.peakDailyTokens)
                                        metric("Дней подряд", value: activity.summary.currentStreakDays)
                                        if !activity.daily.isEmpty {
                                            Text("Последние дни с данными").font(.caption).foregroundStyle(.secondary)
                                            ForEach(activity.daily) { day in metric(day.date, value: day.tokens) }
                                        }
                                        Text("Статистика от Codex. Токены не переводятся в стоимость или оставшееся число сообщений.")
                                            .font(.caption).foregroundStyle(.secondary)
                                    }.padding(.top, 10)
                                } else { unavailable("Статистика активности пока недоступна.") }
                            }
                        } else {
                            unavailable("Войдите в ChatGPT в настройках модели, чтобы увидеть лимиты подписки.")
                        }
                    } else if !usage.refreshing && usage.error == nil {
                        unavailable(app.busy ? "Лимиты можно обновить после завершения текущей задачи." : "Нажмите «Обновить», чтобы проверить лимиты аккаунта Proto-Mind.")
                    }
                    if let error = usage.error { unavailable(error) }
                }.frame(maxWidth: .infinity, alignment: .leading)
            }
            HStack {
                if usage.refreshing { ProgressView().controlSize(.small); Text("Проверяю аккаунт…").foregroundStyle(.secondary) }
                Spacer()
                Button("Обновить") { Task { await usage.refresh(app: app) } }
                    .disabled(usage.refreshing || app.busy || app.connecting || app.client.turnOutstanding)
            }.font(.callout)
        }.padding(24).frame(width: 560, height: 610)
            .task { await usage.refresh(app: app) }
    }

    @ViewBuilder private func quota(_ window: CodexUsageSnapshot.Window) -> some View {
        VStack(alignment: .leading, spacing: 7) {
            HStack {
                Text(window.title)
                Spacer()
                if let remaining = window.remaining {
                    Text("Осталось \(remaining.formatted(.number.precision(.fractionLength(0...1))))%").monospacedDigit()
                } else { Text("Нет данных").foregroundStyle(.secondary) }
            }.font(.callout)
            if let remaining = window.remaining {
                ProgressView(value: remaining, total: 100).tint(remaining <= 10 ? .orange : .primary)
                if let used = window.usedPercent {
                    Text("Использовано \(used.formatted(.number.precision(.fractionLength(0...1))))%")
                        .font(.caption).foregroundStyle(.secondary)
                }
            }
            if let timestamp = window.resetsAt {
                TimelineView(.periodic(from: .now, by: 60)) { context in
                    Text(timestamp > context.date.timeIntervalSince1970
                         ? "Обновление: \(Date(timeIntervalSince1970: timestamp).formatted(date: .abbreviated, time: .shortened))"
                         : "Срок обновления наступил — проверьте лимит снова")
                        .font(.caption).foregroundStyle(.secondary)
                }
            } else { Text("Время обновления неизвестно").font(.caption).foregroundStyle(.secondary) }
        }
    }

    private func unavailable(_ text: String) -> some View {
        Text(text).font(.callout).foregroundStyle(.secondary).textSelection(.enabled)
    }

    private func metric(_ title: String, value: Int?) -> some View {
        LabeledContent(title, value: value.map { $0.formatted() } ?? "Нет данных").font(.callout)
    }
}
