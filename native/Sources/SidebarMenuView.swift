import SwiftUI

struct SidebarMenuView: View {
    @ObservedObject var app: AppModel
    @ObservedObject var usage: CodexUsageModel
    @ObservedObject var client: BridgeClient
    let openSettings: () -> Void
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
                        Text("Меню").font(.system(size: 13))
                        HStack(spacing: 4) {
                            Text((usage.summary?.compactBucket == nil ? "" : "Исп. ") + compactLabel).lineLimit(1).minimumScaleFactor(0.85)
                            if stale(at: context.date), usage.summary?.compactBucket != nil {
                                Image(systemName: "clock").font(.system(size: 9))
                            }
                        }.font(.system(size: 10.5)).monospacedDigit().foregroundStyle(.secondary)
                    }
                    Spacer(minLength: 0)
                    Image(systemName: "chevron.up").font(.system(size: 9)).foregroundStyle(.secondary)
                }.padding(10).contentShape(Rectangle())
            }.buttonStyle(.nativeHover).accessibilityLabel("Меню")
                .accessibilityValue("Использовано: \(compactLabel)\(stale(at: context.date) ? ", требуется обновление" : "")")
                .help("Настройки и лимиты Codex. Показана использованная доля лимитов аккаунта.")
        }
        .composerPopover(isPresented: $open, width: 290, confinedToColumn: true) {
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
        guard let value = usage.summary else { return "Лимиты Codex · —" }
        guard value.connected else { return "Нет входа в ChatGPT" }
        guard let bucket = value.compactBucket else { return "Лимиты Codex · —" }
        return bucket.windows.map { "\($0.title) \($0.usedLabel)" }.joined(separator: " · ")
    }

    private func stale(at date: Date) -> Bool {
        usage.summaryError != nil || usage.summary?.limitsAreStale(at: date) != false
    }

    private var menuContent: some View {
        VStack(alignment: .leading, spacing: 4) {
            ComposerMenuRow(title: "Настройки", icon: "gearshape") {
                open = false
                Task { @MainActor in await Task.yield(); openSettings() }
            }
            ComposerMenuRow(title: "Лимиты", icon: "gauge.with.dots.needle.50percent") {
                open = false
                Task { @MainActor in await Task.yield(); app.showCodexUsage = true }
            }
            Divider().padding(.horizontal, 8).padding(.vertical, 5)
            VStack(alignment: .leading, spacing: 12) {
                if let value = usage.summary, value.connected {
                    VStack(alignment: .leading, spacing: 3) {
                        Text("ChatGPT · \(value.plan.capitalized)").font(.system(size: 12, weight: .medium))
                        if !value.email.isEmpty { Text(value.email).font(.system(size: 10.5)).lineLimit(2).textSelection(.enabled) }
                    }.foregroundStyle(.secondary)
                }
                HStack {
                    Text("Использовано").font(.system(size: 11, weight: .medium)).foregroundStyle(.secondary)
                    Spacer()
                    if usage.refreshingLimits { ProgressView().controlSize(.mini) }
                    Button { Task { await usage.refreshLimits(app: app, minimumInterval: 5) } } label: {
                        Image(systemName: "arrow.clockwise").font(.system(size: 11)).frame(width: 22, height: 22)
                    }.buttonStyle(.nativeHover).disabled(!canRefresh || usage.refreshingLimits || usage.refreshing || usage.resetting)
                        .accessibilityLabel("Обновить проценты лимитов").help("Обновить лимиты")
                }
                if let value = usage.summary, value.connected, !value.buckets.isEmpty {
                    ForEach(value.buckets) { bucket in
                        VStack(alignment: .leading, spacing: 9) {
                            if value.buckets.count > 1 || bucket.id != "codex" {
                                Text(bucket.name).font(.system(size: 11, weight: .medium))
                            }
                            ForEach(bucket.windows) { window in
                                VStack(spacing: 5) {
                                    HStack {
                                        Text(window.title).foregroundStyle(.secondary)
                                        Spacer()
                                        Text(window.usedLabel).monospacedDigit()
                                    }.font(.system(size: 12))
                                    if let used = window.used {
                                        ProgressView(value: min(used, 100), total: 100)
                                            .tint(used >= 90 ? .orange : .secondary).controlSize(.mini)
                                    }
                                    if let remaining = window.remaining {
                                        Text("Осталось \(remaining.formatted(.number.precision(.fractionLength(0...1))))%")
                                            .font(.system(size: 10.5)).foregroundStyle(.secondary).frame(maxWidth: .infinity, alignment: .trailing)
                                    }
                                }.accessibilityElement(children: .combine)
                            }
                        }
                    }
                } else {
                    Text(!app.cloudConsent || usage.summary?.connected == false
                         ? "Войдите в ChatGPT в настройках модели."
                         : usage.refreshingLimits ? "Проверяю лимиты…" : "Проценты пока недоступны.")
                        .font(.system(size: 12)).foregroundStyle(.secondary)
                }
                TimelineView(.periodic(from: .now, by: 15)) { context in
                    VStack(alignment: .leading, spacing: 4) {
                        if let updated = usage.summary?.limitsUpdatedAt {
                            Text("\(stale(at: context.date) ? "Данные устарели" : "Обновлено") · \(Date(timeIntervalSince1970: updated).formatted(date: .omitted, time: .shortened))")
                        }
                        if let error = usage.summaryError { Text(error) }
                        Text("Лимиты аккаунта, подключённого в Proto-Mind")
                    }.font(.system(size: 10.5)).foregroundStyle(.secondary)
                }
            }.padding(.horizontal, 12).padding(.bottom, 10)
        }.padding(6)
    }
}
