import Foundation

extension NativeChecks {
    @MainActor static func appUpdateDetection(root: URL) throws {
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
        outside.stop()
    }
}
