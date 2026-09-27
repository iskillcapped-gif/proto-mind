import SwiftUI

struct SidebarMenuView: View {
    @ObservedObject var app: AppModel
    @ObservedObject var usage: CodexUsageModel
    @ObservedObject var client: BridgeClient
    @ObservedObject var claude: ClaudeAccountModel
    let openSettings: () -> Void
    var columnWidth: CGFloat = 260
    @Environment(\.scenePhase) private var scenePhase
    @State private var open = false
    @State private var chosenProvider: String?
    private var provider: String { chosenProvider ?? app.currentUsageProvider }
    private var isClaude: Bool { provider == "claude" }
    init(app: AppModel, usage: CodexUsageModel, client: BridgeClient, openSettings: @escaping () -> Void, columnWidth: CGFloat = 260) {
        self.app = app; self.usage = usage; self.client = client; self.claude = app.claudeAccount
        self.openSettings = openSettings; self.columnWidth = columnWidth
    }
    private var windows: [SidebarUsageWindow] {
        if isClaude { return (claude.snapshot?.compactWindows ?? []).map { SidebarUsageWindow(id: $0.id, title: $0.periodTitle, label: $0.remainingLabel, remaining: $0.remainingPercent) } }
        return SidebarQuotaSummary.windows(usage.displaySnapshot).map { SidebarUsageWindow(id: $0.id, title: $0.title, label: $0.remainingLabel, remaining: $0.remaining) }
    }

    private var canRefresh: Bool {
        !app.bootstrap.isNull && app.cloudConsent && !app.privateBackupRestartRequired
    }
    private var autoRefresh: Bool { canRefresh && scenePhase == .active }

    var body: some View {
        TimelineView(.periodic(from: .now, by: 15)) { context in
            Button { open.toggle() } label: {
                HStack(spacing: 8) {
                    Image(systemName: "line.3.horizontal").font(.system(size: 13)).foregroundStyle(.secondary)
                    VStack(alignment: .leading, spacing: 0) {
                        Text(L10n.text("Меню")).font(.system(size: 12))
                        HStack(spacing: 4) {
                            Text(open ? L10n.text("Настройки и лимиты") : compactLabel).lineLimit(1).minimumScaleFactor(0.85)
                            if !open, stale(at: context.date), !windows.isEmpty {
                                Image(systemName: "clock").font(.system(size: 8))
                            }
                        }.font(.system(size: 10)).monospacedDigit().foregroundStyle(.secondary)
                    }
                    Spacer(minLength: 0)
                    Image(systemName: "chevron.up").font(.system(size: 8)).foregroundStyle(.secondary)
                }.padding(.horizontal, 8).padding(.vertical, 4).contentShape(Rectangle())
            }.buttonStyle(.nativeHover).accessibilityLabel(L10n.text("Меню"))
                .accessibilityValue("\(compactLabel)\(stale(at: context.date) ? L10n.pick(", требуется обновление", ", refresh needed") : "")")
                .help(L10n.pick("Настройки и лимиты Codex / Claude. Показан остаток.", "Settings and Codex / Claude limits. Shows remaining quota."))
        }
        .composerPopover(isPresented: $open, width: columnWidth, confinedToColumn: true, columnWidth: columnWidth) {
            menuContent
        }
        .task(id: app.selectedCodexAccount.id + String(autoRefresh)) {
            guard autoRefresh else { return }
            while !Task.isCancelled {
                async let codexRefresh: Void = usage.refreshLimits(app: app)
                async let claudeRefresh: Void = claude.refresh(app: app)
                _ = await (codexRefresh, claudeRefresh)
                do { try await Task.sleep(for: .seconds(60)) } catch { return }
            }
        }
        .onChange(of: open) { _, value in
            if value && canRefresh { Task {
                async let codexRefresh: Void = usage.refreshLimits(app: app)
                async let claudeRefresh: Void = claude.refresh(app: app)
                _ = await (codexRefresh, claudeRefresh)
            } }
        }
        .onChange(of: app.selected?.provider) { _, _ in chosenProvider = nil }
        .onChange(of: app.turnStartedAt) { old, new in
            if old != nil && new == nil && autoRefresh {
                Task {
                    async let codexRefresh: Void = usage.refreshLimits(app: app, minimumInterval: 5)
                    async let claudeRefresh: Void = claude.refresh(app: app, minimumInterval: 5)
                    _ = await (codexRefresh, claudeRefresh)
                }
            }
        }
    }

    private var compactLabel: String {
        if isClaude { return claude.compactLabel }
        guard let value = usage.displaySnapshot else { return L10n.text("Лимиты Codex · —") }
        guard value.connected else { return L10n.text("Нет входа в ChatGPT") }
        let windows = SidebarQuotaSummary.windows(value)
        guard !windows.isEmpty else { return L10n.text("Лимиты Codex · —") }
        return "Codex · " + L10n.text("Осталось ") + windows.map { "\($0.title) \($0.remainingLabel)" }.joined(separator: " · ")
    }

    private func stale(at date: Date) -> Bool {
        isClaude ? claude.error != nil || claude.snapshot?.limitsAreStale(at: date) != false
            : usage.summaryError != nil || usage.displaySnapshot?.limitsAreStale(at: date) != false
    }

    private var menuContent: some View {
        VStack(alignment: .leading, spacing: 0) {
            VStack(alignment: .leading, spacing: 9) {
                SubscriptionProviderPicker(provider: Binding(get: { provider }, set: { chosenProvider = $0 }))
                HStack {
                    Text(isClaude ? "Claude" : "Codex").font(.system(size: 12, weight: .medium))
                    Spacer()
                    Text(L10n.text("Осталось")).font(.system(size: 10)).foregroundStyle(.secondary)
                }
                Text(isClaude ? [claude.snapshot?.email ?? "", claude.snapshot?.plan.capitalized ?? ""].filter { !$0.isEmpty }.joined(separator: " · ") : app.selectedCodexAccount.label).font(.system(size: 10)).foregroundStyle(.secondary).lineLimit(2)
                if windows.isEmpty {
                    Text((isClaude ? claude.refreshing : usage.refreshingLimits) ? L10n.text("Обновляю…") : L10n.text("Данные пока недоступны"))
                        .font(.system(size: 12)).foregroundStyle(.secondary)
                } else {
                    ForEach(windows) { window in
                        VStack(spacing: 5) {
                            HStack {
                                Text(window.title).foregroundStyle(.secondary)
                                Spacer()
                                Text(window.label).monospacedDigit()
                            }.font(.system(size: 12))
                            if let remaining = window.remaining {
                                GeometryReader { geometry in
                                    Capsule().fill(Color.primary.opacity(0.08))
                                        .overlay(alignment: .leading) {
                                            Capsule().fill(remaining <= 10 ? Color.orange : Color.primary.opacity(0.55))
                                                .frame(width: geometry.size.width * remaining / 100)
                                        }
                                }.frame(height: 4)
                            }
                        }.accessibilityElement(children: .combine)
                    }
                }
                if stale(at: Date()), !windows.isEmpty {
                    Label(L10n.text("Данные устарели"), systemImage: "clock").font(.system(size: 10)).foregroundStyle(.secondary)
                }
            }.padding(.horizontal, 13).padding(.vertical, 11)
            Divider().padding(.horizontal, 10)
            VStack(spacing: 0) {
                ComposerMenuRow(title: L10n.text("Настройки"), icon: "gearshape") {
                    open = false
                    Task { @MainActor in await Task.yield(); openSettings() }
                }
                ComposerMenuRow(title: L10n.text("Лимиты"), icon: "gauge.with.dots.needle.50percent") {
                    open = false
                    Task { @MainActor in await Task.yield(); app.openAccountUsage(provider) }
                }
                ComposerMenuRow(title: app.desktop.enabled ? L10n.text("Обычное окно") : L10n.text("Парящий режим"),
                                icon: app.desktop.enabled ? "macwindow" : "cube.transparent") {
                    open = false
                    Task { @MainActor in await Task.yield(); app.desktop.toggleMode() }
                }
            }.padding(4)
        }
    }
}

/// Compact UI deliberately excludes reserve/model-specific buckets and absent periods.
enum SidebarQuotaSummary {
    static func windows(_ snapshot: CodexUsageSnapshot?) -> [CodexUsageSnapshot.Window] {
        guard let snapshot, snapshot.connected, let main = snapshot.buckets.first(where: { $0.id == "codex" }) else { return [] }
        return [10080, 300].compactMap { minutes in main.windows.first { $0.windowMinutes == minutes } }
    }
}

private struct SidebarUsageWindow: Identifiable {
    let id: String
    let title: String
    let label: String
    let remaining: Double?
}
