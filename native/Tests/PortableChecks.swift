import Foundation

extension NativeChecks {
    @MainActor
    static func portableConfiguration(root: URL) throws {
        let home = root.appendingPathComponent("New Mac/User With Spaces")
        let resources = root.appendingPathComponent("Applications/Moved Proto-Mind.app/Contents/Resources")
        let inherited = ["PROTO_MIND_PROJECT_ROOT": "/developer/private", "PROTO_MIND_PYTHON": "/developer/python"]
        let configuration = LaunchConfiguration.resolve(arguments: [], environment: inherited,
            bundled: ["distribution": "portable"], resources: resources, home: home, currentDirectory: "/", pdfHelper: nil)
        try check(configuration.isPortable && configuration.projectRoot.path.hasPrefix(home.path), "Portable profile belongs to the current Mac user")
        try check(configuration.codeRoot.path == resources.appendingPathComponent("core").path, "Relocated application resolves code from its own resources")
        try check(configuration.python == resources.appendingPathComponent("runtime/python/bin/python3"), "Portable Python is independent of build-machine paths")
        try check(configuration.codexExecutable == resources.appendingPathComponent("runtime/codex/bin/codex"), "Portable Codex preserves its official package layout")
        try check(configuration.stateDirectory.deletingLastPathComponent() == configuration.projectRoot.deletingLastPathComponent(), "Core and Native stores are separate siblings compatible with backup inventory")
        try check(!FileManager.default.fileExists(atPath: home.path), "Resolving portable paths does not initialize private data")
        let moved = LaunchConfiguration.resolve(arguments: [], environment: [:], bundled: ["distribution": "portable"],
            resources: root.appendingPathComponent("Updated.app/Contents/Resources"), home: home, currentDirectory: "/tmp", pdfHelper: nil)
        try check(moved.stateDirectory == configuration.stateDirectory && moved.projectRoot == configuration.projectRoot,
                  "Replacing or moving the app preserves the same personal profile")
        let qa = LaunchConfiguration.resolve(arguments: ["app", "--profile-root", root.appendingPathComponent("QA").path], environment: [:],
            bundled: ["distribution": "portable"], resources: resources, home: home, currentDirectory: "/", pdfHelper: nil)
        try check(qa.stateDirectory.path.hasPrefix(root.appendingPathComponent("QA").path), "QA profile override isolates both stores from the daily app")
        let legacy = LaunchConfiguration.resolve(arguments: [], environment: inherited, bundled: [:], resources: resources,
            home: home, currentDirectory: "/", pdfHelper: nil)
        try check(!legacy.isPortable && legacy.codeRoot.path == "/developer/private"
                  && legacy.stateDirectory.lastPathComponent == "ProtoMindNative", "Development edition keeps its existing paths and environment overrides")
        let suite = "portable-checks-" + UUID().uuidString
        let defaults = UserDefaults(suiteName: suite)!
        defer { defaults.removePersistentDomain(forName: suite) }
        try check(FirstLaunch.shouldPresent(configuration, defaults: defaults) && !FirstLaunch.shouldPresent(legacy, defaults: defaults),
                  "Welcome appears for a new portable profile, never an existing development installation")
        FirstLaunch.dismiss(configuration, defaults: defaults)
        try check(!FirstLaunch.shouldPresent(moved, defaults: defaults) && FirstLaunch.shouldPresent(qa, defaults: defaults),
                  "Welcome dismissal survives updates but never leaks into another profile")
        try check(!FileManager.default.fileExists(atPath: configuration.stateDirectory.path), "Dismissing welcome grants no permissions and writes no private profile")
    }

    @MainActor
    static func portableBridge(fixture: URL, python: URL, root: URL) async throws {
        let config = LaunchConfiguration(projectRoot: root.appendingPathComponent("portable/core"), python: python,
            stateDirectory: root.appendingPathComponent("portable/native"), sourceRoot: fixture, isPortable: true)
        let bridge = BridgeClient(configuration: config)
        defer { bridge.shutdown() }
        let initial = try await bridge.request("bootstrap")
        try check(!initial.isNull && initial["operator_name"].text.isEmpty, "Separated bridge bootstraps a fresh profile without copying the operator's identity")
        try check(!FileManager.default.fileExists(atPath: config.projectRoot.appendingPathComponent("proto_mind/main.py").path),
                  "Bridge starts with source outside its writable root")
        let store = ChatStore(directory: config.stateDirectory)
        var chat = Conversation()
        chat.draft = "My portable draft"
        let loaded = try store.load()
        // Use AppModel's existing writer path, with exactly this disposable profile.
        let model = AppModel(configuration: config)
        try check(model.selected?.provider == "codex" && model.selected?.model == "", "Fresh portable dialogs use the account's Codex model catalog")
        model.conversations = [chat]; model.selectedID = chat.id
        model.persist()
        let restarted = AppModel(configuration: config)
        try check(loaded.conversations.isEmpty && restarted.selected?.draft == chat.draft, "Portable Native history survives a new app model with no profile migration")
        try check(!restarted.cloudConsent && restarted.agentGrants.isEmpty, "A clean portable profile starts without cloud or Mac permissions")
    }
}
