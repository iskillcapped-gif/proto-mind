import SwiftUI

struct CodexUsageView: View {
    @ObservedObject var app: AppModel
    @ObservedObject var usage: CodexUsageModel
    @State private var confirmingReset = false
    @State private var proposedReset: CodexResetAttempt?

    private var refreshBlocked: Bool {
        usage.refreshing || usage.resetting || !app.cloudConsent || app.connecting || app.loginPending || app.privateBackupRestartRequired
    }
    private var resetBlocked: Bool { refreshBlocked || app.busy || app.client.turnOutstanding }

    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            HStack {
                Text("Использование Codex").font(.system(size: 22, weight: .semibold))
                Spacer()
                Button { app.showCodexUsage = false } label: { Image(systemName: "xmark") }
                    .keyboardShortcut(.cancelAction).disabled(usage.resetting)
            }
            ScrollView {
                VStack(alignment: .leading, spacing: 20) {
                    if let value = usage.displaySnapshot {
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
                            HStack {
                                if let count = value.resetCredits {
                                    Text("Доступно сбросов: \(count)").font(.callout).foregroundStyle(.secondary)
                                }
                                Spacer()
                                if value.canReset, let reset = value.reset {
                                    Button(reset.pending ? "Проверить попытку" : "Сбросить лимит…") {
                                        let attempt = CodexResetAttempt(reset)
                                        if reset.pending { Task { await usage.consume(attempt, app: app) } }
                                        else { proposedReset = attempt; confirmingReset = true }
                                    }.disabled(resetBlocked)
                                }
                            }
                            if let message = value.resetError, !message.isEmpty { unavailable(message) }
                            if (value.resetCredits ?? 0) > 0 && value.reset == nil && (value.resetError ?? "").isEmpty {
                                unavailable("Сброс недоступен, пока Codex не подтвердит аккаунт. Попробуйте обновить данные.")
                            }
                            if let timestamp = value.limitsUpdatedAt {
                                TimelineView(.periodic(from: .now, by: 15)) { context in
                                    Text("\(value.limitsAreStale(at: context.date) || usage.summaryError != nil ? "Данные устарели" : "Лимиты проверены"): \(Date(timeIntervalSince1970: timestamp).formatted(date: .abbreviated, time: .shortened))")
                                        .font(.caption).foregroundStyle(.secondary)
                                }
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
                        unavailable("Нажмите «Обновить», чтобы проверить лимиты аккаунта Proto-Mind.")
                    }
                    if let error = usage.error { unavailable(error) }
                    if let error = usage.summaryError, error != usage.error, error != usage.displaySnapshot?.limitsError { unavailable(error) }
                    if let message = usage.resetMessage { unavailable(message) }
                }.frame(maxWidth: .infinity, alignment: .leading)
            }
            HStack {
                if usage.refreshing { ProgressView().controlSize(.small); Text("Проверяю аккаунт…").foregroundStyle(.secondary) }
                if usage.resetting { ProgressView().controlSize(.small); Text("Проверяю сброс…").foregroundStyle(.secondary) }
                Spacer()
                Button("Обновить") { Task { await usage.refresh(app: app) } }
                    .disabled(refreshBlocked)
            }.font(.callout)
        }.padding(24).frame(width: 560, height: 610)
            .task { await usage.refresh(app: app) }
            .interactiveDismissDisabled(usage.resetting)
            .alert("Использовать один сброс?", isPresented: $confirmingReset, presenting: proposedReset) { attempt in
                Button("Отмена", role: .cancel) { proposedReset = nil }
                Button("Сбросить лимит") { Task { await usage.consume(attempt, app: app) } }
            } message: { _ in
                Text("Codex использует один доступный сброс для аккаунта \(usage.snapshot?.email ?? "ChatGPT"). Это действие нельзя отменить. Если подходящего лимита нет, сброс не расходуется.")
            }
    }

    @ViewBuilder private func quota(_ window: CodexUsageSnapshot.Window) -> some View {
        VStack(alignment: .leading, spacing: 7) {
            HStack {
                Text(window.title)
                Spacer()
                if window.remaining != nil {
                    Text("Осталось \(window.remainingLabel)").monospacedDigit()
                } else { Text("Нет данных").foregroundStyle(.secondary) }
            }.font(.callout)
            if let remaining = window.remaining {
                ProgressView(value: remaining, total: 100).tint(remaining <= 10 ? .orange : .primary)
                if window.used != nil {
                    Text("Использовано \(window.usedLabel)")
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
