import AppKit
import Foundation

@MainActor
final class GitHubModel: ObservableObject {
    @Published private(set) var status: JSONValue = .null
    @Published private(set) var repositories: [JSONValue] = []
    @Published private(set) var repository: JSONValue = .null
    @Published private(set) var loading = false
    @Published private(set) var error: String?
    @Published private(set) var nextPage: Int?
    @Published var query = ""

    var connected: Bool { status["connected"].flag }
    var filteredRepositories: [JSONValue] {
        repositories.filter { query.isEmpty || $0["name"].text.localizedCaseInsensitiveContains(query) || $0["description"].text.localizedCaseInsensitiveContains(query) }
    }

    func refresh(app: AppModel) async {
        guard !loading, !app.busy else { return }
        loading = true; error = nil
        defer { loading = false }
        do {
            let value = try await app.client.request("github_status")
            if value["login"].text != status["login"].text || !value["connected"].flag { clearRepositories() }
            status = value
        } catch { self.error = error.localizedDescription }
    }

    func connect(app: AppModel) async {
        guard !loading, !app.busy, !status["available_login"].text.isEmpty else { return }
        loading = true; error = nil
        defer { loading = false }
        do {
            status = try await app.client.request("github_connect", ["login": status["available_login"]])
            clearRepositories()
        } catch { self.error = error.localizedDescription }
    }

    func disconnect(app: AppModel) async {
        guard !loading, !app.busy else { return }
        loading = true; error = nil
        defer { loading = false }
        do {
            status = try await app.client.request("github_disconnect")
            clearRepositories()
        } catch { self.error = error.localizedDescription }
    }

    func loadRepositories(app: AppModel, more: Bool = false) async {
        guard !loading, !app.busy, connected, !more || nextPage != nil else { return }
        loading = true; error = nil
        defer { loading = false }
        do {
            let value = try await app.client.request("github_repositories", ["page": .number(Double(more ? nextPage! : 1))])
            guard value["login"].text == status["login"].text else { throw NativeError.message("Аккаунт GitHub изменился. Проверьте подключение.") }
            let previous = more ? repositories : []
            let names = Set(previous.map { $0["name"].text })
            repositories = previous + value["items"].items.filter { !names.contains($0["name"].text) }
            nextPage = value["next_page"].isNull ? nil : value["next_page"].integer
            repository = .null
        } catch { self.error = error.localizedDescription }
    }

    func inspect(_ name: String, app: AppModel) async {
        guard !loading, !app.busy, connected else { return }
        loading = true; error = nil
        defer { loading = false }
        do { repository = try await app.client.request("github_repository", ["name": .string(name)]) }
        catch { self.error = error.localizedDescription }
    }

    func back() { repository = .null }
    private func clearRepositories() { repositories = []; repository = .null; nextPage = nil }

    func discuss(_ text: String, app: AppModel) {
        guard !app.busy, !app.client.turnOutstanding, let id = app.selectedID, app.selected?.archived == false else {
            error = "Откройте активный диалог перед подготовкой сообщения."; return
        }
        let draft = app.composer
        app.setComposer(draft.isEmpty ? text : draft + "\n\n" + text, preservingContinuation: true)
        app.returnToConversation(id)
    }

    func openLogin() {
        let executable = ["/opt/homebrew/bin/gh", "/usr/local/bin/gh"].first { FileManager.default.isExecutableFile(atPath: $0) }
        guard let executable else {
            NSWorkspace.shared.open(URL(string: "https://cli.github.com/")!); return
        }
        do {
            let file = FileManager.default.temporaryDirectory.appendingPathComponent("proto-mind-github-login-\(UUID().uuidString).command")
            let home = FileManager.default.homeDirectoryForCurrentUser.path
            func quote(_ value: String) -> String { "'" + value.replacingOccurrences(of: "'", with: "'\\''") + "'" }
            let command = "#!/bin/sh\n/usr/bin/env -i HOME=\(quote(home)) GH_CONFIG_DIR=\(quote(home + "/.config/gh")) PATH=/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin TERM=xterm-256color \(executable) auth login --hostname github.com --git-protocol https --web\n"
            try Data(command.utf8).write(to: file, options: .withoutOverwriting)
            try FileManager.default.setAttributes([.posixPermissions: 0o700], ofItemAtPath: file.path)
            NSWorkspace.shared.open([file], withApplicationAt: URL(fileURLWithPath: "/System/Applications/Utilities/Terminal.app"), configuration: NSWorkspace.OpenConfiguration()) { _, failure in
                if failure != nil { Task { @MainActor in self.error = "Не удалось открыть вход. Выполните gh auth login в Терминале." } }
            }
        } catch { self.error = "Не удалось открыть вход GitHub." }
    }
}
