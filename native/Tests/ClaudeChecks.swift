import Foundation

extension NativeChecks {
    @MainActor static func claudeProvider(fixture: URL, python: URL, root: URL) async throws {
        let directory = root.appendingPathComponent("claude-native")
        let configuration = LaunchConfiguration(projectRoot: fixture, python: python, stateDirectory: directory)
        let suite = "pm-claude-checks-" + UUID().uuidString
        let defaults = UserDefaults(suiteName: suite)!
        let app = AppModel(configuration: configuration, uiDefaults: defaults)
        defer { app.shutdown(); defaults.removePersistentDomain(forName: suite) }
        let id = app.selectedID!
        app.setComposer("Preserve this draft")
        app.cloudConsent = true
        app.setProvider("claude")
        app.setModel("sonnet")
        app.setReasoningEffort("high")
        try check(app.selected?.provider == "claude" && app.selected?.model == "sonnet" && app.selected?.reasoningEffort == "high", "Claude model and effort are selected in the ordinary conversation")
        try check(!app.fullAccessEnabled && app.composer == "Preserve this draft", "Selecting Claude preserves the draft without enabling tools")
        app.personaEnabled = true
        let plain = app.contextRequestParameters!
        try check(plain["persona_enabled"] == .bool(false) && plain["provider"] == .string("claude"), "Claude does not silently activate Brother Persona")
        let preview = try await app.client.request("context_preview", plain)
        _ = try NativeInstructionPreview(preview["instruction_preview"])
        try check(preview["manifest"]["destination"].text == "anthropic_cloud", "Claude context preview identifies Anthropic")
        app.requestAgentAccess()
        try check(app.pendingAgentAccess?.provider == "claude", "Full Mac confirmation captures the Claude provider")
        await app.confirmAgentAccess()
        try check(app.fullAccessEnabled && app.agentGrants[id] != nil, "Claude receives a fresh conversation-bound Full Mac grant")
        let fullPreview = try await app.client.request("context_preview", app.contextRequestParameters!)
        _ = try NativeInstructionPreview(fullPreview["instruction_preview"])
        try check(fullPreview["instruction_preview"]["mode"].text == "full_access", "Native accepts exact Claude Full Mac instruction metadata")
        let state = app.execution(for: id)
        state.running = true; state.requestID = "claude-tools"; state.workspaceToolsAllowed = true
        state.workspaceToolBinding = app.workspaceToolBinding(app.selected!)
        let tasks = try await app.executeWorkspaceTool("pm_list_tasks", args: .object([:]), state: state, request: "claude-tools")
        try check(!tasks.isNull, "Claude uses PM tools through the existing turn-bound channel")
        try check(!ConversationComposerContext(app: app, id: id).showsStop, "A draft typed while Claude runs turns the single action into Send, as for Codex updates")
        app.setComposer("")
        try check(ConversationComposerContext(app: app, id: id).showsStop, "An empty editor keeps Stop while Claude runs")
        app.setComposer("Preserve this draft")
        app.agentGrants.removeValue(forKey: id)
        do {
            _ = try app.requireWorkspaceTurn(state, "claude-tools")
            try check(false, "Revoked Claude tools must fail")
        } catch { try check(true, "Claude workspace tools recheck revocation") }
        state.running = false
        let saved = try JSONDecoder().decode(Conversation.self, from: JSONEncoder().encode(app.selected!))
        try check(saved.provider == "claude" && saved.model == "sonnet", "Claude selection survives conversation serialization")
        app.configureConversation(id, provider: "codex")
        try check(!app.fullAccessEnabled && app.rememberedAgentAccess.allSatisfy { $0.conversationID != id }, "Changing away from Claude clears saved tool access")
        app.configureConversation(id, provider: "claude", model: "opus", effort: "medium")
        try check(app.selected?.provider == "claude" && app.selected?.reasoningEffort == "medium", "Panel conversation configuration supports Claude")
        app.claudeAuthenticating = true
        let before = app.selected!.messages.count
        await app.submit()
        try check(app.selected!.messages.count == before && app.composer == "Preserve this draft", "Pending Claude login cannot dispatch a model turn or consume the draft")
        app.claudeAuthenticating = false
        try check(!FileManager.default.fileExists(atPath: directory.appendingPathComponent("claude-profile").path), "Native offline checks never create a Claude credential profile")
    }
}
