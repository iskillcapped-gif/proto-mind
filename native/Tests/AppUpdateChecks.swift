import Foundation

extension NativeChecks {
    @MainActor static func appUpdateDetection(root: URL) async throws {
        let bundle = root.appendingPathComponent("update-fixture/Fixture.app")
        let contents = bundle.appendingPathComponent("Contents")
        try FileManager.default.createDirectory(at: contents.appendingPathComponent("MacOS"), withIntermediateDirectories: true)
        func install(version: String, number: String, binary: String) throws {
            let info: NSDictionary = ["CFBundleShortVersionString": version, "CFBundleVersion": number, "CFBundleExecutable": "Fixture"]
            try info.write(to: contents.appendingPathComponent("Info.plist"))
            // Swap by rename like the staged install, so the executable gets a new inode.
            let staged = contents.appendingPathComponent("MacOS/Fixture.staged")
            try Data(binary.utf8).write(to: staged)
            guard rename(staged.path, contents.appendingPathComponent("MacOS/Fixture").path) == 0 else {
                throw NativeError.message("Fixture swap failed")
            }
        }
        try install(version: "1.0", number: "1", binary: "first")
        let monitor = AppUpdateMonitor(bundle: bundle)
        monitor.check()
        try check(monitor.running?.version == "1.0" && !monitor.available, "The running build is not reported as an update")
        try install(version: "1.0", number: "1", binary: "rebuilt")
        monitor.check()
        try check(monitor.available && monitor.installed?.number == "1", "A swapped executable of the same version is an installed update")
        try install(version: "1.1", number: "2", binary: "newer")
        monitor.check()
        try check(monitor.installed?.version == "1.1" && monitor.installed?.number == "2", "The update names the installed version")
        let current = AppUpdateMonitor(bundle: bundle)
        current.check()
        try check(!current.available, "After a restart the same build is current again")
        try Data("not a property list".utf8).write(to: contents.appendingPathComponent("Info.plist"))
        current.check()
        try check(!current.available, "A bundle caught mid-swap is not reported as an update")
        let outside = AppUpdateMonitor(bundle: root)
        outside.start()
        outside.check()
        try check(outside.running == nil && !outside.available, "A process outside an app bundle never offers a restart")
        let data = Data("""
        [
          {"tag_name":"v0.75.9-beta","draft":false,"assets":[]},
          {"tag_name":"v8.0.0","draft":true,"assets":[]},
          {"tag_name":"mobile-99","draft":false,"assets":[]},
          {"tag_name":"v0.75.11-beta","draft":false,"assets":[{"name":"Proto-Mind-0.75.11-arm64-beta.dmg"}]}
        ]
        """.utf8)
        let release = try PublishedAppRelease.newest(in: data)
        try check(release?.tag == "v0.75.11-beta" && release?.download?.absoluteString ==
                  "https://github.com/iskillcapped-gif/proto-mind/releases/download/v0.75.11-beta/Proto-Mind-0.75.11-arm64-beta.dmg",
                  "Release check includes public betas, ignores drafts and selects the official installer")
        try check(release?.compare(to: "0.75.9") == .orderedDescending && release?.compare(to: "0.75.11") == .orderedSame
                  && release?.compare(to: "0.75.12") == .orderedAscending, "Release versions compare numerically in both directions")
        let fallback = try PublishedAppRelease.newest(in: Data(#"[{"tag_name":"v1.0.0","draft":false,"assets":[{"name":"SHA256SUMS"}]}]"#.utf8))
        try check(fallback?.download == nil && fallback?.page.absoluteString == "https://github.com/iskillcapped-gif/proto-mind/releases/tag/v1.0.0",
                  "A release with no DMG opens its own release page")
        await outside.checkPublished { throw URLError(.notConnectedToInternet) }
        try check(outside.published == .failed && !outside.available, "An offline check is distinct from being up to date")
        await outside.checkPublished { release }
        try check(outside.published == .checked(release) && !outside.available, "Retry can load a published release without proposing a local restart")
        outside.stop()
    }
}
