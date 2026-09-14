import Foundation

extension AppModel {
    func hasAgentAccessSelection(_ conversation: Conversation) -> Bool {
        guard cloudConsent, conversation.provider == "codex" else { return false }
        return rememberedAgentAccess.contains { $0.conversationID == conversation.id && $0.workspace == conversation.workspacePath }
            || (executions[conversation.id]?.client.connected == true
                && agentGrants[conversation.id]?.workspace == conversation.workspacePath && agentGrants[conversation.id] != nil)
    }

    /// Preferences retain the operator's choice, never a bridge token. Each new
    /// bridge must issue its own grant and revalidate the conversation after await.
    func ensureAgentAccess(for state: ConversationExecution) async throws {
        let id = state.conversationID
        guard let conversation = conversations.first(where: { $0.id == id }), hasAgentAccessSelection(conversation) else { return }
        if state.client.connected, let grant = agentGrants[id], grant.workspace == conversation.workspacePath,
           grant.bridgeGeneration == state.client.connectionGeneration { return }
        let task: Task<AgentAccessGrant, Error>
        if let pending = restoringAgentAccess[id] { task = pending }
        else {
            task = Task { @MainActor in
                var params: [String: JSONValue] = ["conversation_id": .string(id.uuidString), "mode": .string("full_access"),
                    "cloud_consent": .bool(true), "confirmation": .string("ALLOW FULL MAC ACCESS")]
                if let workspace = conversation.workspacePath { params["workspace_root"] = .string(workspace) }
                let result = try await state.client.request("agent_access", params)
                try Task.checkCancellation()
                guard result["mode"].text == "full_access", !result["token"].text.isEmpty,
                      result["workspace_root"] == (conversation.workspacePath.map(JSONValue.string) ?? .null) else {
                    throw NativeError.message("Не удалось восстановить полный доступ к Mac. Задача не запускалась.")
                }
                return AgentAccessGrant(token: result["token"].text, workspace: conversation.workspacePath,
                                        bridgeGeneration: state.client.connectionGeneration)
            }
            restoringAgentAccess[id] = task
        }
        defer { restoringAgentAccess.removeValue(forKey: id) }
        let grant = try await task.value
        guard executions[id] === state, let current = conversations.first(where: { $0.id == id }),
              current.workspacePath == conversation.workspacePath, hasAgentAccessSelection(current),
              grant.bridgeGeneration == state.client.connectionGeneration else {
            throw NativeError.message("Диалог или доступ изменились во время подключения. Задача не запускалась.")
        }
        agentGrants[id] = grant
    }

    func prepareSelectedAgentAccess() async -> Bool {
        guard let id = selectedID else { return false }
        do {
            try await ensureAgentAccess(for: execution(for: id))
            return selectedID == id
        } catch { report(error); return false }
    }
}
