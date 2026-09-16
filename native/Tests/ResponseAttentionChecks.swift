import Foundation

extension NativeChecks {
    @MainActor
    static func responseAttentionContracts(root: URL) throws {
        let suite = "proto-response-attention-checks-" + UUID().uuidString
        let defaults = UserDefaults(suiteName: suite)!
        defer { defaults.removePersistentDomain(forName: suite) }
        let state = root.appendingPathComponent("response-attention")
        let config = LaunchConfiguration(projectRoot: root, python: URL(fileURLWithPath: "/usr/bin/python3"), stateDirectory: state)
        let app = AppModel(configuration: config, uiDefaults: defaults)
        defer { app.shutdown() }
        let first = app.selectedID!
        let old = ChatMessage(role: "assistant", text: "Old history")
        app.conversations[0].messages = [old]
        try check(app.unreadConversations.isEmpty, "Existing history is read by default; rollout does not mark every old answer")
        app.append(ChatMessage(role: "report", text: "Local command"), to: first)
        try check(app.unreadConversations.isEmpty, "Local core reports do not pretend to be new model replies")
        let answer = ChatMessage(role: "assistant", text: "New answer")
        app.append(answer, to: first)
        app.newConversation()
        let second = app.selectedID!
        let interrupted = ChatMessage(role: "report", text: "Interrupted", isError: true)
        app.append(interrupted, to: second)
        app.setComposer("Keep this draft"); app.flushDraft()
        try check(app.persist(), "Attention fixture history saves")
        let bytes = try fileBytes(state)
        try check(app.unreadConversations.count == 2 && app.responseAttention.entries[first]?.needsAttention == false
                  && app.responseAttention.entries[second]?.needsAttention == true,
                  "Two conversations have independent reply and interrupted-result markers")
        let restored = AppModel(configuration: config, uiDefaults: defaults)
        defer { restored.shutdown() }
        try check(restored.unreadConversations.count == 2 && restored.composer == "Keep this draft",
                  "Unread outcomes and the selected draft survive restart independently")
        restored.responseAttention.acknowledge(conversationID: first, messageID: old.id)
        try check(restored.unreadConversations.count == 2, "Reading an older answer cannot acknowledge a newer completion")
        restored.responseAttention.acknowledge(conversationID: first, messageID: answer.id)
        try check(restored.unreadConversations.map(\.id) == [second] && (try fileBytes(state)) == bytes,
                  "Reading a response clears only that conversation and never rewrites private history")
        let preferences = ResponseAttention(stateDirectory: state, defaults: defaults)
        try check(preferences.entries[first] == nil && preferences.entries[second]?.messageID == interrupted.id,
                  "Exact acknowledgement is persisted without losing the other unread result")
        let fresh = ResponseAttention(stateDirectory: root.appendingPathComponent("another-profile"), defaults: defaults)
        try check(fresh.entries.isEmpty, "Unread preferences cannot leak across profiles")
        restored.conversations.removeAll { $0.id == second }
        try check(restored.unreadConversations.isEmpty, "Removed or replaced history cannot leave a stale cube count")
        preferences.prune(restored.conversations)
        try check(preferences.entries.isEmpty, "Pruning removes stale message references after recovery")
        app.execution(for: first).running = true
        try check(app.anyTaskRunning && app.unreadConversations.count == 2,
                  "A new running task can coexist with unread results; spinner and count have different meanings")
        preferences.record(answer, conversationID: first)
        let blockedRoot = root.appendingPathComponent("attention-restore-pending")
        let pending = blockedRoot.appendingPathComponent("proto_mind/data/.private-restore.json")
        try FileManager.default.createDirectory(at: pending.deletingLastPathComponent(), withIntermediateDirectories: true)
        try Data("{}".utf8).write(to: pending)
        let blocked = AppModel(configuration: LaunchConfiguration(projectRoot: blockedRoot, python: config.python,
            stateDirectory: state), uiDefaults: defaults)
        defer { blocked.shutdown() }
        try check(blocked.historyPersistence.blocksSubmission && blocked.responseAttention.entries[first]?.messageID == answer.id,
                  "A temporarily unreadable history during restore does not erase unread preferences")
    }
}
