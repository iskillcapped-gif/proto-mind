import AppKit
import SwiftUI
import SwiftTerm

/// A terminal owns its PTY for the life of its tab, not for the life of a SwiftUI view.
@MainActor
final class WorkspaceTerminal: NSObject, ObservableObject, @preconcurrency LocalProcessTerminalViewDelegate {
    let view: LocalProcessTerminalView
    let directory: URL
    @Published private(set) var title = "Терминал"
    @Published private(set) var running = false
    @Published private(set) var exitCode: Int32?
    private var started = false

    init(directory: URL) {
        self.directory = directory
        view = LocalProcessTerminalView(frame: CGRect(x: 0, y: 0, width: 640, height: 320))
        super.init()
        view.processDelegate = self
        view.font = .monospacedSystemFont(ofSize: 12, weight: .regular)
        view.nativeBackgroundColor = NSColor(calibratedWhite: 0.09, alpha: 1)
        view.nativeForegroundColor = NSColor(calibratedWhite: 0.86, alpha: 1)
    }

    func start(executable: String = "/bin/zsh", arguments: [String] = ["-l"]) {
        guard !started else { return }
        started = true
        var environment = ProcessInfo.processInfo.environment
        environment["TERM"] = "xterm-256color"
        environment["COLORTERM"] = "truecolor"
        environment["PATH"] = TerminalLaunch.environmentPath(environment["PATH"])
        view.startProcess(executable: executable, args: arguments,
                          environment: environment.map { "\($0.key)=\($0.value)" }, currentDirectory: directory.path)
        running = view.process.running
    }

    func close() {
        guard started, view.process.running else { return }
        // An interactive command may own a different foreground process group from its shell.
        let foreground = view.process.childfd >= 0 ? tcgetpgrp(view.process.childfd) : -1
        if foreground > 1 && foreground != getpgrp() { kill(-foreground, SIGHUP) }
        view.terminate()
        running = false
    }

    func sizeChanged(source: LocalProcessTerminalView, newCols: Int, newRows: Int) {}
    func setTerminalTitle(source: LocalProcessTerminalView, title: String) { self.title = String(title.prefix(120)) }
    func hostCurrentDirectoryUpdate(source: TerminalView, directory: String?) {}
    func processTerminated(source: TerminalView, exitCode: Int32?) { running = false; self.exitCode = exitCode }
}

enum TerminalLaunch {
    static func environmentPath(_ inherited: String?) -> String {
        var seen = Set<String>()
        return ((inherited ?? "").split(separator: ":").map(String.init)
            + ["/opt/homebrew/bin", "/usr/local/bin", "/usr/bin", "/bin", "/usr/sbin", "/sbin"])
            .filter { $0.hasPrefix("/") && seen.insert($0).inserted }.joined(separator: ":")
    }

    static func executable(_ name: String) -> String? {
        let candidates = name.hasPrefix("/") ? [name] : environmentPath(ProcessInfo.processInfo.environment["PATH"])
            .split(separator: ":").map { String($0) + "/" + name }
        return candidates.first { FileManager.default.isExecutableFile(atPath: $0) }
    }
}

private struct TerminalSurface: NSViewRepresentable {
    @Environment(\.isEnabled) private var enabled
    let terminal: WorkspaceTerminal
    func makeNSView(context: Context) -> LocalProcessTerminalView { terminal.view }
    func updateNSView(_ view: LocalProcessTerminalView, context: Context) {
        // Hidden tabs retain their process/page but must give up keyboard input.
        if !enabled, let responder = view.window?.firstResponder as? NSView,
           responder === view || responder.isDescendant(of: view) { view.window?.makeFirstResponder(nil) }
    }
}

struct WorkspaceTerminalView: View {
    @ObservedObject var terminal: WorkspaceTerminal
    var body: some View {
        VStack(spacing: 0) {
            HStack(spacing: 8) {
                Circle().fill(terminal.running ? Color.green : .secondary).frame(width: 5, height: 5)
                Text(terminal.directory.lastPathComponent).lineLimit(1).help(terminal.directory.path)
                Spacer()
                if !terminal.running { Text(terminal.exitCode.map { "Завершено · \($0)" } ?? "Завершено") }
            }.font(.system(size: 11)).foregroundStyle(.secondary).padding(.horizontal, 12).padding(.vertical, 8)
                .workspacePanelHeader()
            TerminalSurface(terminal: terminal).frame(maxWidth: .infinity, maxHeight: .infinity)
        }
    }
}

extension WorkspacePanelModel {
    func openTerminal(directory: URL, executable: String = "/bin/zsh", arguments: [String] = ["-l"]) {
        guard tabs.count < Self.maximumTabs else { error = "Закройте одну из вкладок перед открытием терминала."; return }
        guard FileManager.default.isExecutableFile(atPath: executable) else { error = "CLI не найден: \(executable)"; return }
        let terminal = WorkspaceTerminal(directory: directory)
        guard open(.terminal(terminal)) != nil else { return }
        terminal.start(executable: executable, arguments: arguments)
    }
}
