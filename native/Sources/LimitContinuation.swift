import SwiftUI

/// After a Claude turn stops at the usage limit, the operator can ask PM to continue on its own once
/// the limit renews. Nothing is scheduled without that click, and what is sent then is an ordinary
/// request in the same chat, so the session continues with its interruption notice. A schedule
/// lives while PM runs; after a restart the button appears again.
@MainActor
final class LimitContinuations: ObservableObject {
    @Published private(set) var scheduled: [UUID: Date] = [:]
    private var tasks: [UUID: Task<Void, Never>] = [:]

    func schedule(_ conversationID: UUID, at date: Date, after messageID: UUID, app: AppModel) {
        cancel(conversationID)
        scheduled[conversationID] = date
        tasks[conversationID] = Task { @MainActor [weak self, weak app] in
            // A minute past the renewal, then confirm with the account before sending.
            let delay = date > .now ? date.timeIntervalSinceNow + 60 : 0
            if delay > 0 { try? await Task.sleep(for: .seconds(delay)) }
            for _ in 0..<12 {
                guard !Task.isCancelled, let app else { return }
                await app.claudeAccount.refresh(app: app, minimumInterval: 0)
                if AppModel.limitReset(app.claudeAccount.snapshot?.windows ?? []) == nil { break }
                try? await Task.sleep(for: .seconds(300))
            }
            guard !Task.isCancelled, let self, let app else { return }
            self.scheduled.removeValue(forKey: conversationID); self.tasks.removeValue(forKey: conversationID)
            // The operator may have continued already; then there is nothing to do.
            guard app.limitInterruption(in: conversationID)?.id == messageID, !app.isRunning(conversationID) else { return }
            do { _ = try await app.sendExternalTaskMessage(L10n.pick("Продолжай с того места, где остановился.", "Continue where you left off."), id: conversationID) }
            catch { app.error = error.localizedDescription }
        }
    }

    func cancel(_ conversationID: UUID) {
        tasks.removeValue(forKey: conversationID)?.cancel()
        scheduled.removeValue(forKey: conversationID)
    }
}

extension AppModel {
    /// The bridge reports the usage limit in the interface language.
    static let claudeLimitPrefixes = ["Claude: достигнут лимит", "Claude: usage limit reached"]

    /// The usage-limit error a Claude turn ended with, while it is still the chat's last message.
    func limitInterruption(in conversationID: UUID) -> ChatMessage? {
        guard let chat = conversations.first(where: { $0.id == conversationID }), chat.provider == "claude", !chat.archived,
              let last = chat.messages.last, last.role == "report", last.isError,
              Self.claudeLimitPrefixes.contains(where: last.text.hasPrefix) else { return nil }
        return last
    }

    /// When the exhausted window renews: the latest reset among windows with nothing left.
    /// Nil when no window is exhausted, so the chat can continue now.
    static func limitReset(_ windows: [ClaudeQuotaWindow], now: Date = .now) -> Date? {
        windows.filter { ($0.remainingPercent ?? 100) <= 0.5 }
            .compactMap { $0.resetsAt.map { Date(timeIntervalSince1970: $0) } }
            .filter { $0 > now }.max()
    }
}

/// Under a usage-limit error: continue after the reset, or the scheduled time with a way to cancel.
struct LimitContinuationRow: View {
    let app: AppModel
    @ObservedObject var continuations: LimitContinuations
    @ObservedObject var account: ClaudeAccountModel
    let conversationID: UUID
    let messageID: UUID

    var body: some View {
        HStack(spacing: 10) {
            if let date = continuations.scheduled[conversationID] {
                Label(L10n.pick("Продолжу сам в ", "I will continue at ") + Self.time(date), systemImage: "clock")
                    .foregroundStyle(.secondary)
                Button(L10n.text("Отмена")) { continuations.cancel(conversationID) }
            } else {
                let reset = AppModel.limitReset(account.snapshot?.windows ?? [])
                Button {
                    continuations.schedule(conversationID, at: reset ?? .now, after: messageID, app: app)
                } label: {
                    Label(reset.map { L10n.pick("Продолжить после сброса · ", "Continue after the reset · ") + Self.time($0) }
                          ?? L10n.pick("Продолжить", "Continue"), systemImage: "arrow.clockwise")
                }.help(L10n.pick("PM сам отправит «Продолжай», когда лимит обновится, если вы не продолжите раньше.",
                                 "PM sends “Continue” itself when the limit renews, unless you continue first."))
            }
        }
        .font(.system(size: 12)).buttonStyle(.bordered).controlSize(.small)
        .task { await account.refresh(app: app) }
    }

    /// "21:40" today, otherwise with the weekday.
    static func time(_ date: Date) -> String {
        Calendar.current.isDate(date, inSameDayAs: .now)
            ? date.formatted(.dateTime.hour().minute().locale(L10n.locale))
            : date.formatted(.dateTime.weekday(.abbreviated).hour().minute().locale(L10n.locale))
    }
}
