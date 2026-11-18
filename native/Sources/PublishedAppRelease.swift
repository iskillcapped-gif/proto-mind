import Foundation
import SwiftUI

struct PublishedAppRelease: Equatable {
    static let repository = URL(string: "https://github.com/iskillcapped-gif/proto-mind")!
    static let endpoint = URL(string: "https://api.github.com/repos/iskillcapped-gif/proto-mind/releases?per_page=50")!
    let tag: String
    let version: String
    let download: URL?
    var page: URL { Self.repository.appendingPathComponent("releases/tag/" + tag) }

    private struct Release: Decodable {
        struct Asset: Decodable { let name: String }
        let tag_name: String
        let draft: Bool
        let assets: [Asset]
    }

    /// Only app version tags participate. GitHub's /latest endpoint skips our public betas.
    static func newest(in data: Data) throws -> Self? {
        try JSONDecoder().decode([Release].self, from: data).compactMap { release -> Self? in
            let tag = release.tag_name
            guard !release.draft, tag.range(of: #"^v[0-9]+\.[0-9]+\.[0-9]+(-beta)?$"#, options: .regularExpression) != nil else { return nil }
            let version = String(tag.dropFirst().prefix { $0 != "-" })
            let suffix = tag.hasSuffix("-beta") ? "-beta" : ""
            let name = "Proto-Mind-" + version + "-arm64" + suffix + ".dmg"
            let download = release.assets.contains { $0.name == name }
                ? repository.appendingPathComponent("releases/download/" + tag + "/" + name) : nil
            return Self(tag: tag, version: version, download: download)
        }.max { lhs, rhs in
            let order = lhs.version.compare(rhs.version, options: .numeric)
            if order == .orderedSame { return lhs.tag.hasSuffix("-beta") && !rhs.tag.hasSuffix("-beta") }
            return order == .orderedAscending
        }
    }

    func compare(to installed: String) -> ComparisonResult {
        version.compare(installed, options: .numeric)
    }

    static func fetch() async throws -> Self? {
        let session = URLSession(configuration: .ephemeral)
        defer { session.finishTasksAndInvalidate() }
        var request = URLRequest(url: endpoint, cachePolicy: .reloadIgnoringLocalCacheData, timeoutInterval: 15)
        request.setValue("application/vnd.github+json", forHTTPHeaderField: "Accept")
        request.setValue("Proto-Mind", forHTTPHeaderField: "User-Agent")
        let (data, response) = try await session.data(for: request)
        guard let http = response as? HTTPURLResponse, http.statusCode == 200, data.count <= 2_000_000 else {
            throw URLError(.badServerResponse)
        }
        return try newest(in: data)
    }
}

extension AppUpdateMonitor {
    enum PublishedState: Equatable {
        case idle, checking, checked(PublishedAppRelease?), failed
    }

    func checkPublished(using fetch: () async throws -> PublishedAppRelease? = PublishedAppRelease.fetch) async {
        guard published != .checking else { return }
        check()
        published = .checking
        do { published = .checked(try await fetch()) }
        catch { published = .failed }
    }
}

extension AppModel {
    func openAppUpdates() {
        let destination = presentations.currentDestination
        guard !destination.locked else { return }
        presentations.prepare("appUpdates", in: destination)
        showAppUpdates = true
        Task { await appUpdate.checkPublished() }
    }
}

struct AppReleasesView: View {
    @ObservedObject var app: AppModel
    @ObservedObject var monitor: AppUpdateMonitor

    private var installed: AppUpdateMonitor.Build? { monitor.installed ?? monitor.running }

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text(L10n.pick("Обновления Proto-Mind", "Proto-Mind updates")).font(.title2.weight(.semibold))
            if let installed {
                LabeledContent(L10n.pick("Установлено на Mac", "Installed on this Mac"),
                               value: installed.version + " (" + installed.number + ")")
            }
            switch monitor.published {
            case .idle, .checking:
                HStack { ProgressView().controlSize(.small); Text(L10n.pick("Проверяю релизы на GitHub…", "Checking GitHub releases…")) }
            case .failed:
                Label(L10n.pick("Не удалось получить список релизов с GitHub.", "Could not reach the GitHub releases feed."), systemImage: "wifi.exclamationmark")
            case .checked(nil):
                Text(L10n.pick("Опубликованных версий пока нет.", "No published versions yet."))
            case .checked(let release?):
                LabeledContent(L10n.pick("Последний релиз", "Latest release"), value: release.tag)
                if let installed {
                    switch release.compare(to: installed.version) {
                    case .orderedDescending: Text(L10n.pick("Доступна новая версия.", "A new version is available."))
                    case .orderedSame: Text(L10n.pick("У вас актуальная версия.", "You’re up to date."))
                    default: Text(L10n.pick("На Mac установлена более новая версия.", "Your Mac has a newer version."))
                    }
                }
                HStack {
                    if let url = release.download, installed.map({ release.compare(to: $0.version) == .orderedDescending }) ?? true {
                        Link(L10n.pick("Скачать для Mac", "Download for Mac"), destination: url).buttonStyle(.borderedProminent)
                    }
                    Link(L10n.pick("Открыть релиз на GitHub", "View release on GitHub"), destination: release.page)
                }
            }
            HStack {
                Button(L10n.pick("Проверить ещё раз", "Check again")) { Task { await monitor.checkPublished() } }
                    .disabled(monitor.published == .checking)
                Spacer()
                Button(L10n.text("Готово")) { app.showAppUpdates = false }
            }.buttonStyle(.bordered)
        }.padding(24).workspacePageSize(width: 440, height: 270)
    }
}
