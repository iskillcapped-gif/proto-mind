import SwiftUI

/// A usage-limit error from the bridge, with the renewal time Claude Code announced.
struct ClaudeLimitError: LocalizedError {
    let message: String
    let resetsAt: Date
    var errorDescription: String? { message }
}

/// The wrapper distinguishes a folderless turn from a report saved by an older build.
struct ClaudeLimitOrigin: Codable, Equatable {
    let workspace: String?
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

    private var tickets: [UUID: UUID] = [:]

    func schedule(_ conversationID: UUID, at date: Date, after messageID: UUID, app: AppModel, attempt: Int = 1) {
        guard let chat = app.conversations.first(where: { $0.id == conversationID }),
              app.limitInterruption(in: conversationID)?.id == messageID, !app.isRunning(conversationID) else { return }
        cancel(conversationID)
        let ticket = UUID(), workspace = chat.workspacePath
        tickets[conversationID] = ticket
        scheduled[conversationID] = date
        let authorized = { [weak self, weak app] in
            self?.tickets[conversationID] == ticket
                && app?.conversations.contains(where: { $0.id == conversationID && $0.workspacePath == workspace }) == true
                && app?.limitInterruption(in: conversationID)?.id == messageID
        }
        tasks[conversationID] = Task { @MainActor [weak self, weak app] in
            var next = date
            var handedOff = false
            defer {
                if self?.tickets[conversationID] == ticket {
                    if !handedOff { self?.tickets.removeValue(forKey: conversationID) }
                    self?.tasks.removeValue(forKey: conversationID)
                    self?.scheduled.removeValue(forKey: conversationID)
                }
            }
            while true {
                if next > .now { try? await Task.sleep(for: .seconds(next.timeIntervalSinceNow + 60)) }
                guard authorized(), let app else { return }
                await app.claudeAccount.refresh(app: app, minimumInterval: 0)
                guard authorized() else { return }
                guard let later = AppModel.limitReset(app.claudeAccount.snapshot?.windows ?? []) else { break }
                next = later
                self?.scheduled[conversationID] = later
            }
            guard authorized(), let app, !app.isRunning(conversationID) else { return }
            do {
                _ = try await app.sendExternalTaskMessage(L10n.pick("Продолжай с того места, где остановился.", "Continue where you left off."),
                                                          id: conversationID, authorized: authorized, finished: { [weak self, weak app] _ in
                    guard let self, self.tickets[conversationID] == ticket else { return }
                    self.tickets.removeValue(forKey: conversationID)
                    guard let app, attempt < Self.attempts, let again = app.limitInterruption(in: conversationID),
                          again.id != messageID, app.conversations.contains(where: { $0.id == conversationID && $0.workspacePath == workspace }) else { return }
                    self.schedule(conversationID, at: app.limitReset(after: again) ?? .now.addingTimeInterval(1800),
                                  after: again.id, app: app, attempt: attempt + 1)
                })
                handedOff = true
            } catch {
                if authorized() { app.error = error.localizedDescription }
            }
        }
    }

    func cancel(_ conversationID: UUID) {
        tickets.removeValue(forKey: conversationID)
        tasks.removeValue(forKey: conversationID)?.cancel()
        scheduled.removeValue(forKey: conversationID)
    }

    func cancelAll() {
        for id in Array(tickets.keys) { cancel(id) }
    }
}

extension AppModel {
    /// Stamp legacy reports before rebinding so that reopening them cannot continue into a different folder.
    func setConversationWorkspace(_ path: String?, at index: Int) {
        let chat = conversations[index]
        guard chat.workspacePath != path else { return }
        limitContinuations.cancel(chat.id)
        if let last = chat.messages.indices.last, chat.messages[last].limitOrigin == nil,
           Self.claudeLimitPrefixes.contains(where: chat.messages[last].text.hasPrefix), chat.messages[last].isError {
            conversations[index].messages[last].limitOrigin = ClaudeLimitOrigin(workspace: chat.workspacePath)
        }
        conversations[index].workspacePath = path
    }

    /// The bridge reports the usage limit in the interface language.
    static let claudeLimitPrefixes = ["Claude: достигнут лимит", "Claude: usage limit reached"]

    /// The usage-limit error a Claude turn ended with, while it is still the chat's last message.
    func limitInterruption(in conversationID: UUID) -> ChatMessage? {
        guard let chat = conversations.first(where: { $0.id == conversationID }), chat.provider == "claude", !chat.archived,
              let last = chat.messages.last, last.role == "report", last.isError,
              Self.claudeLimitPrefixes.contains(where: last.text.hasPrefix) else { return nil }
        if let origin = last.limitOrigin, origin.workspace != chat.workspacePath { return nil }
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
