import AppKit
import SwiftUI

/// Notices a newer build installed over the running bundle (built in a staging
/// folder and swapped in while the app runs) and relaunches on request.
/// A separate observable keeps its periodic check out of AppModel's updates.
@MainActor
final class AppUpdateMonitor: ObservableObject {
    struct Build: Equatable {
        let version: String
        let number: String
        let executable: UInt64
        let modified: Date
    }

    /// The build on disk when it differs from the one this process started with.
    @Published private(set) var installed: Build?
    let running: Build?
    private let bundle: URL
    private var timer: Timer?

    init(bundle: URL = Bundle.main.bundleURL) {
        self.bundle = bundle
        running = Self.read(bundle)
    }

    var available: Bool { installed != nil }

    func start() {
        guard timer == nil, running != nil else { return }
        check()
        timer = Timer.scheduledTimer(withTimeInterval: 30, repeats: true) { [weak self] _ in
            Task { @MainActor in self?.check() }
        }
    }

    func stop() { timer?.invalidate(); timer = nil }

    func check() {
        // An unreadable bundle mid-swap is not an update; the next check decides.
        guard let running, let current = Self.read(bundle) else { return }
        let next = current == running ? nil : current
        if next != installed { installed = next }
    }

    static func read(_ bundle: URL) -> Build? {
        let contents = bundle.appendingPathComponent("Contents")
        guard let info = NSDictionary(contentsOf: contents.appendingPathComponent("Info.plist")),
              let version = info["CFBundleShortVersionString"] as? String, let number = info["CFBundleVersion"] as? String,
              let name = info["CFBundleExecutable"] as? String, !name.contains("/"),
              let attributes = try? FileManager.default.attributesOfItem(atPath: contents.appendingPathComponent("MacOS/" + name).path),
              let inode = attributes[.systemFileNumber] as? NSNumber, let modified = attributes[.modificationDate] as? Date
        else { return nil }
        return Build(version: version, number: number, executable: inode.uint64Value, modified: modified)
    }

    /// Opens the same bundle path after this process exits. If the quit is
    /// cancelled (unsaved history, a shared operation), nothing is relaunched.
    func relaunch() throws {
        let helper = Process()
        helper.executableURL = URL(fileURLWithPath: "/bin/sh")
        helper.arguments = ["-c", "i=0; while /bin/kill -0 \"$1\" 2>/dev/null; do i=$((i+1)); [ \"$i\" -gt 300 ] && exit 0; /bin/sleep 0.2; done; exec /usr/bin/open \"$2\"",
                            "proto-mind-relaunch", String(ProcessInfo.processInfo.processIdentifier), bundle.path]
        try helper.run()
        NSApp.terminate(nil)
    }
}

extension AppModel {
    var runningTaskCount: Int { executions.values.filter(\.running).count }

    func restartForUpdate() {
        guard appUpdate.available else { return }
        do { try appUpdate.relaunch() } catch { report(error) }
    }
}

/// A small sidebar control: blue when a newer build is installed, gray otherwise.
struct AppUpdateButton: View {
    @ObservedObject var app: AppModel
    @ObservedObject var monitor: AppUpdateMonitor
    @State private var confirming = false

    var body: some View {
        Button {
            if app.runningTaskCount > 0 { confirming = true } else { app.restartForUpdate() }
        } label: {
            Image(systemName: "arrow.triangle.2.circlepath").font(.system(size: 12, weight: .semibold))
                .foregroundStyle(monitor.available ? Color.blue : Color.secondary.opacity(0.45))
        }
        .buttonStyle(.plain).disabled(!monitor.available)
        .help(help).accessibilityLabel(help)
        .alert(L10n.text("Перезапустить Proto-Mind?"), isPresented: $confirming) {
            Button(L10n.text("Перезапустить"), role: .destructive) { app.restartForUpdate() }
            Button(L10n.text("Отмена"), role: .cancel) {}
        } message: {
            Text(L10n.format("Сейчас выполняются задачи: \(app.runningTaskCount). Перезапуск остановит их; уже сделанные изменения не отменяются."))
        }
    }

    private var help: String {
        guard let installed = monitor.installed else { return L10n.text("Обновлений нет") }
        return L10n.format("Установлена версия \(installed.version) (\(installed.number)). Нажмите, чтобы перезапустить Proto-Mind.")
    }
}
