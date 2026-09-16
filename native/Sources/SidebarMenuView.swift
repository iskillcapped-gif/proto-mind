import SwiftUI

struct SidebarMenuView: View {
    @ObservedObject var app: AppModel
    @ObservedObject var usage: CodexUsageModel
    @ObservedObject var client: BridgeClient
    let openSettings: () -> Void
    var columnWidth: CGFloat = 260
    @Environment(\.scenePhase) private var scenePhase
    @State private var open = false

    private var canRefresh: Bool {
        client.connected && !app.bootstrap.isNull && app.cloudConsent && !app.connecting
            && !app.loginPending && !app.privateBackupRestartRequired
    }
    private var autoRefresh: Bool { canRefresh && scenePhase == .active }

    var body: some View {
        TimelineView(.periodic(from: .now, by: 15)) { context in
            Button { open.toggle() } label: {
                HStack(spacing: 10) {
                    Image(systemName: "line.3.horizontal").font(.system(size: 16)).foregroundStyle(.secondary)
                    VStack(alignment: .leading, spacing: 4) {
                        Text(L10n.text("Меню")).font(.system(size: 13))
                        HStack(spacing: 4) {
                            Text(open ? L10n.text("Настройки и лимиты") : compactLabel).lineLimit(1).minimumScaleFactor(0.85)
                            if !open, stale(at: context.date), !SidebarQuotaSummary.windows(usage.displaySnapshot).isEmpty {
                                Image(systemName: "clock").font(.system(size: 9))
                            }
                        }.font(.system(size: 10.5)).monospacedDigit().foregroundStyle(.secondary)
                    }
                    Spacer(minLength: 0)
                    Image(systemName: "chevron.up").font(.system(size: 9)).foregroundStyle(.secondary)
                }.padding(10).contentShape(Rectangle())
            }.buttonStyle(.nativeHover).accessibilityLabel(L10n.text("Меню"))
                .accessibilityValue("\(compactLabel)\(stale(at: context.date) ? L10n.pick(", требуется обновление", ", refresh needed") : "")")
                .help(L10n.text("Настройки и лимиты Codex. Показан остаток лимитов аккаунта."))
        }
        .composerPopover(isPresented: $open, width: columnWidth, confinedToColumn: true, columnWidth: columnWidth) {
            menuContent
        }
        .task(id: autoRefresh) {
            guard autoRefresh else { return }
            while !Task.isCancelled {
                await usage.refreshLimits(app: app)
                do { try await Task.sleep(for: .seconds(60)) } catch { return }
            }
        }
        .onChange(of: open) { _, value in
            if value && canRefresh { Task { await usage.refreshLimits(app: app) } }
        }
        .onChange(of: app.turnStartedAt) { old, new in
            if old != nil && new == nil && autoRefresh {
                Task { await usage.refreshLimits(app: app, minimumInterval: 5) }
            }
        }
    }

    private var compactLabel: String {
        guard let value = usage.displaySnapshot else { return L10n.text("Лимиты Codex · —") }
        guard value.connected else { return L10n.text("Нет входа в ChatGPT") }
        let windows = SidebarQuotaSummary.windows(value)
        guard !windows.isEmpty else { return L10n.text("Лимиты Codex · —") }
        return L10n.text("Осталось ") + windows.map { "\($0.title) \($0.remainingLabel)" }.joined(separator: " · ")
    }

    private func stale(at date: Date) -> Bool {
        usage.summaryError != nil || usage.displaySnapshot?.limitsAreStale(at: date) != false
    }

    private var menuContent: some View {
        VStack(alignment: .leading, spacing: 0) {
            VStack(alignment: .leading, spacing: 14) {
                HStack {
                    Text(L10n.text("Лимиты Codex")).font(.system(size: 12, weight: .medium))
                    Spacer()
                    Text(L10n.text("Осталось")).font(.system(size: 10)).foregroundStyle(.secondary)
                }
                let windows = SidebarQuotaSummary.windows(usage.displaySnapshot)
                if windows.isEmpty {
                    Text(usage.refreshingLimits ? L10n.text("Обновляю…") : L10n.text("Данные пока недоступны"))
                        .font(.system(size: 12)).foregroundStyle(.secondary)
                } else {
                    ForEach(windows) { window in
                        VStack(spacing: 7) {
                            HStack {
                                Text(window.title).foregroundStyle(.secondary)
                                Spacer()
                                Text(window.remainingLabel).monospacedDigit()
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
            }.padding(16)
            Divider().padding(.horizontal, 10)
            VStack(spacing: 2) {
                ComposerMenuRow(title: L10n.text("Настройки"), icon: "gearshape") {
                    open = false
                    Task { @MainActor in await Task.yield(); openSettings() }
                }
                ComposerMenuRow(title: L10n.text("Лимиты"), icon: "gauge.with.dots.needle.50percent") {
                    open = false
                    Task { @MainActor in await Task.yield(); app.showCodexUsage = true }
                }
                ComposerMenuRow(title: app.desktop.enabled ? L10n.text("Обычное окно") : L10n.text("Парящий режим"),
                                icon: app.desktop.enabled ? "macwindow" : "cube.transparent") {
                    open = false
                    Task { @MainActor in await Task.yield(); app.desktop.toggleMode() }
                }
            }.padding(6)
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
