import SwiftUI

struct SubscriptionProviderPicker: View {
    @Binding var provider: String
    var body: some View {
        HStack(spacing: 4) {
            ForEach(["codex", "claude"], id: \.self) { value in
                Button { provider = value } label: {
                    Text(value == "codex" ? "Codex" : "Claude").font(.system(size: 12, weight: .medium))
                        .frame(maxWidth: .infinity).padding(.vertical, 8)
                        .background(provider == value ? NativeTheme.selection : .clear, in: RoundedRectangle(cornerRadius: 8))
                        .contentShape(Rectangle())
                }.buttonStyle(.plain).foregroundStyle(provider == value ? .primary : .secondary)
                    .accessibilityAddTraits(provider == value ? .isSelected : [])
            }
        }.padding(4).background(.primary.opacity(0.035), in: RoundedRectangle(cornerRadius: 11))
    }
}

struct AccountUsageView: View {
    @ObservedObject var app: AppModel
    @ObservedObject var usage: CodexUsageModel
    @State private var provider: String
    init(app: AppModel, usage: CodexUsageModel) {
        self.app = app; self.usage = usage; _provider = State(initialValue: app.presentedUsageProvider)
    }
    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack {
                Text(L10n.text("Лимиты")).font(.system(size: 22, weight: .semibold))
                Spacer()
                Button { app.showCodexUsage = false } label: { Image(systemName: "xmark") }
                    .keyboardShortcut(.cancelAction).disabled(usage.resetting)
            }
            SubscriptionProviderPicker(provider: $provider).disabled(usage.resetting)
            if provider == "claude" {
                ClaudeUsageView(app: app, account: app.claudeAccount)
            } else {
                CodexUsageView(app: app, usage: usage, embedded: true)
            }
        }.padding(24).workspacePageSize(width: 560, height: 650).workspaceDismissDisabled(usage.resetting)
    }
}

struct ClaudeUsageView: View {
    @ObservedObject var app: AppModel
    @ObservedObject var account: ClaudeAccountModel
    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            ScrollView {
                VStack(alignment: .leading, spacing: 18) {
                    if let value = account.snapshot, value.connected {
                        VStack(alignment: .leading, spacing: 5) {
                            Text([value.email, value.plan.capitalized].filter { !$0.isEmpty }.joined(separator: " · ")).font(.callout)
                            Text(L10n.pick("Лимиты аккаунта Claude, включая использование вне Proto-Mind.", "Claude account limits, including usage outside Proto-Mind."))
                                .font(.callout).foregroundStyle(.secondary)
                        }
                        ForEach(value.windows) { window in
                            VStack(alignment: .leading, spacing: 9) {
                                HStack {
                                    Text(window.displayTitle)
                                    Spacer()
                                    Text(L10n.pick("Осталось \(window.remainingLabel)", "\(window.remainingLabel) remaining")).monospacedDigit()
                                }.font(.callout)
                                if let remaining = window.remainingPercent {
                                    ProgressView(value: remaining, total: 100).tint(remaining <= 10 ? .orange : .primary)
                                    Text(L10n.pick("Использовано \(window.usedLabel)", "\(window.usedLabel) used")).font(.caption).foregroundStyle(.secondary)
                                }
                                if let reset = window.resetsAt {
                                    Text(L10n.pick("Обновление: ", "Resets: ") + Date(timeIntervalSince1970: reset).formatted(.dateTime.locale(L10n.locale)))
                                        .font(.caption).foregroundStyle(.secondary)
                                }
                            }.padding(16).background(.quaternary, in: RoundedRectangle(cornerRadius: 12))
                        }
                        if value.windows.isEmpty {
                            Text(value.limitsError.isEmpty
                                 ? L10n.pick("Claude Code пока не предоставил проценты лимитов для этого аккаунта.", "Claude Code has not provided quota percentages for this account.")
                                 : L10n.pick("Не удалось получить лимиты Claude. Попробуйте обновить данные.", "Could not read Claude limits. Try refreshing."))
                                .font(.callout).foregroundStyle(.secondary)
                        }
                        if let updated = value.limitsUpdatedAt {
                            TimelineView(.periodic(from: .now, by: 15)) { time in
                                Text((value.limitsAreStale(at: time.date) || account.error != nil ? L10n.text("Данные устарели") : L10n.text("Лимиты проверены"))
                                     + ": " + Date(timeIntervalSince1970: updated).formatted(.dateTime.locale(L10n.locale)))
                                    .font(.caption).foregroundStyle(.secondary)
                            }
                        }
                    } else if !account.refreshing {
                        Text(L10n.pick("Подключите Claude в настройках, чтобы видеть лимиты подписки.", "Connect Claude in Settings to see subscription limits."))
                            .font(.callout).foregroundStyle(.secondary)
                    }
                    if let error = account.error { Text(error).font(.callout).foregroundStyle(.secondary) }
                }.frame(maxWidth: .infinity, alignment: .leading)
            }
            HStack {
                if account.refreshing { ProgressView().controlSize(.small); Text(L10n.text("Обновляю…")).foregroundStyle(.secondary) }
                Spacer()
                Button(L10n.text("Обновить")) { Task { await account.refresh(app: app, minimumInterval: 0) } }
                    .disabled(account.refreshing || app.claudeAuthenticating || app.privateBackupRestartRequired)
            }.font(.callout)
        }.task { await account.refresh(app: app, minimumInterval: 5) }
    }
}

extension AppModel {
    var currentUsageProvider: String { selected?.provider == "claude" ? "claude" : "codex" }
    func openAccountUsage(_ provider: String? = nil) {
        presentedUsageProvider = provider ?? currentUsageProvider
        presentedCodexAccount = selectedCodexAccount
        showCodexUsage = true
    }
}
