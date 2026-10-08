import SwiftUI

/// A usage-limit error from the bridge, with the renewal time Claude Code announced.
struct ClaudeLimitError: LocalizedError {
    let message: String
    let resetsAt: Date
    var errorDescription: String? { message }
}

/// After a Claude turn stops at the usage limit, the operator can ask PM to continue on its own once
/// the limit renews. Nothing is scheduled without that click, and what is sent then is an ordinary
/// request in the same chat, so the session continues with its interruption notice. A schedule
/// lives while PM runs; after a restart the button appears again.
@MainActor
final class LimitContinuations: ObservableObject {
    /// One click covers this many sends: a limit can still hold right after its announced renewal.
    static let attempts = 3
    @Published private(set) var scheduled: [UUID: Date] = [:]
    private var tasks: [UUID: Task<Void, Never>] = [:]

    func schedule(_ conversationID: UUID, at date: Date, after messageID: UUID, app: AppModel, attempt: Int = 1) {
        cancel(conversationID)
        scheduled[conversationID] = date
        tasks[conversationID] = Task { @MainActor [weak self, weak app] in
            var date = date
            // A minute past the renewal; the account may still show an exhausted window that renews later.
            for _ in 0..<12 {
                if date > .now { try? await Task.sleep(for: .seconds(date.timeIntervalSinceNow + 60)) }
                guard !Task.isCancelled, let app else { return }
                await app.claudeAccount.refresh(app: app, minimumInterval: 0)
                guard !Task.isCancelled, let later = AppModel.limitReset(app.claudeAccount.snapshot?.windows ?? []) else { break }
                date = later; self?.scheduled[conversationID] = later
            }
            guard !Task.isCancelled, let self, let app else { return }
            self.scheduled.removeValue(forKey: conversationID); self.tasks.removeValue(forKey: conversationID)
            // The operator may have continued already; then there is nothing to do.
            guard app.limitInterruption(in: conversationID)?.id == messageID, !app.isRunning(conversationID) else { return }
            do {
                _ = try await app.sendExternalTaskMessage(L10n.pick("Продолжай с того места, где остановился.", "Continue where you left off."),
                                                          id: conversationID, finished: { [weak self, weak app] _ in
                    // Stopped by the limit again: wait for the renewal it announced this time.
                    guard let self, let app, attempt < Self.attempts, self.tasks[conversationID] == nil,
                          let again = app.limitInterruption(in: conversationID), again.id != messageID else { return }
                    self.schedule(conversationID, at: app.limitReset(after: again) ?? .now.addingTimeInterval(1800),
                                  after: again.id, app: app, attempt: attempt + 1)
                })
            } catch { app.error = error.localizedDescription }
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

    /// When the limit behind this error renews: the time Claude Code announced with it, or a
    /// later exhausted window from the account. Nil once both have passed.
    func limitReset(after message: ChatMessage, now: Date = .now) -> Date? {
        [message.limitResetsAt, Self.limitReset(claudeAccount.snapshot?.windows ?? [], now: now)]
            .compactMap { $0 }.filter { $0 > now }.max()
    }
}

/// Under a usage-limit error: continue after the reset, or the scheduled time with a way to cancel.
struct LimitContinuationRow: View {
    let app: AppModel
    @ObservedObject var continuations: LimitContinuations
    @ObservedObject var account: ClaudeAccountModel
    let conversationID: UUID
    let message: ChatMessage

    var body: some View {
        HStack(spacing: 10) {
            if let date = continuations.scheduled[conversationID] {
                Label(L10n.pick("Продолжу сам в ", "I will continue at ") + Self.time(date), systemImage: "clock")
                    .foregroundStyle(.secondary)
                Button(L10n.text("Отмена")) { continuations.cancel(conversationID) }
            } else {
                let reset = app.limitReset(after: message)
                Button {
                    continuations.schedule(conversationID, at: reset ?? .now, after: message.id, app: app)
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
