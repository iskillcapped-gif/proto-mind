import AppKit
import Foundation

extension AppModel {
    /// Every surface edits the existing archive through its one writer. No shadow AppModel or store.
    func setConversationDraft(_ text: String, id: UUID, preservingContinuation: Bool = false) {
        guard let index = conversations.firstIndex(where: { $0.id == id }), !conversations[index].archived else { return }
        if selectedID == id { setComposer(text, preservingContinuation: preservingContinuation); return }
        dictation.composerChanged(conversationID: id)
        conversations[index].draft = text
        if !preservingContinuation || text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty { conversations[index].draftContinuation = nil }
        dirtyDraft = true; historyPersistence.hasUnsavedChanges = true
        draftSave?.cancel()
        draftSave = Task { [weak self] in
            do { try await Task.sleep(nanoseconds: 500_000_000) } catch { return }
            self?.flushDraft()
        }
    }

    func newPanelConversation(in panel: WorkspacePanelModel) {
        guard canNavigateConversations else { return }
        panel.onConversationClosed = { [weak self] id in self?.finishPanelDraft(id) }
        if let empty = panel.tabs.first(where: { tab in
            guard case .conversation(let id) = tab.content else { return false }
            return provisionalPanelConversations.contains(id)
                && conversations.first(where: { $0.id == id })?.hasDraftOrMessages == false
        }) {
            panel.selectedID = empty.id; panel.visible = true
            return
        }
        guard panel.tabs.count < WorkspacePanelModel.maximumTabs else { return }
        var chat = Conversation()
        if let source = selected {
            chat.provider = source.provider; chat.model = source.model; chat.reasoningEffort = source.reasoningEffort
            chat.codexAccountID = source.codexAccountID
            chat.workspacePath = source.workspacePath; chat.apiConnectionID = source.apiConnectionID
        } else if serviceClient.configuration.isPortable { chat.provider = "codex"; chat.model = "" }
        // A new conversation inherits a model and folder, never an authorization grant.
        provisionalPanelConversations.insert(chat.id)
        conversations.insert(chat, at: 0)
        panel.open(.conversation(chat.id))
    }

    /// Closing an unused launcher discards UI state. A written draft stays reachable.
    func finishPanelDraft(_ id: UUID) {
        guard provisionalPanelConversations.contains(id), selectedID != id, !isRunning(id),
              let chat = conversations.first(where: { $0.id == id }) else { return }
        let panels = [workspacePanels.upper, workspacePanels.lower] + desktop.companions.surfaces.map(\.panel)
        guard !panels.contains(where: { panel in
            panel.tabs.contains { if case .conversation(let other) = $0.content { return other == id }; return false }
        }) else { return }
        dictation.stop(for: id)
        provisionalPanelConversations.remove(id)
        if chat.hasDraftOrMessages { persist(); return }
        // This idle draft loses its bridge entirely, so do not enqueue a revocation
        // RPC which could reconnect that bridge after shutdown.
        restoringAgentAccess.removeValue(forKey: id)?.cancel()
        agentGrants.removeValue(forKey: id)
        if pendingAgentAccess?.conversationID == id { pendingAgentAccess = nil }
        if rememberedAgentAccess.contains(where: { $0.conversationID == id }) {
            rememberedAgentAccess.removeAll { $0.conversationID == id }
            do { try savePreferences() } catch { report(error) }
        }
        executions.removeValue(forKey: id)?.client.shutdown()
        conversations.removeAll { $0.id == id }
    }

    /// Publish only after an explicit nonempty send; save its draft before any RPC.
    func beginPanelConversation(_ id: UUID, text: String) -> Bool {
        guard provisionalPanelConversations.contains(id), let index = conversations.firstIndex(where: { $0.id == id }) else { return true }
        if conversations[index].draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            if selectedID == id { setComposer(text) } else { conversations[index].draft = text }
        }
        provisionalPanelConversations.remove(id)
        guard persist() else { provisionalPanelConversations.insert(id); return false }
        return true
    }

    func configureConversation(_ id: UUID, provider: String? = nil, model: String? = nil, effort: String? = nil) {
        guard !operationBusy, !isRunning(id), let index = conversations.firstIndex(where: { $0.id == id }),
              !conversations[index].archived else { return }
        if let provider, provider != conversations[index].provider {
            guard ["codex", "ollama", "mock", "claude"].contains(provider) else { return }
            discardAgentGrants(for: id)
            conversations[index].provider = provider
            conversations[index].apiConnectionID = nil
            conversations[index].apiWorkspaceToolsEnabled = false; conversations[index].apiWorkspaceGeneration = nil
            conversations[index].model = ""; conversations[index].reasoningEffort = ""
        }
        if let model {
            guard conversations[index].provider != "codex" || model.isEmpty || codexModels(for: id).contains(where: { $0.id == model }) else { return }
            conversations[index].model = model
            if conversations[index].provider == "claude", let option = claudeAccount.snapshot?.model(model),
               !option.efforts.contains(conversations[index].reasoningEffort) {
                conversations[index].reasoningEffort = ""
            }
            if conversations[index].provider == "codex" {
                let option = codexModels(for: id).first { model.isEmpty ? $0.isDefault : $0.id == model }
                if option?.efforts.contains(where: { $0.rawValue == conversations[index].reasoningEffort }) != true {
                    conversations[index].reasoningEffort = ""
                }
            }
        }
        if let effort {
            let model = codexModels(for: id).first { conversations[index].model.isEmpty ? $0.isDefault : $0.id == conversations[index].model }
            let claudeEfforts = claudeAccount.snapshot?.model(conversations[index].model)?.efforts ?? ClaudeSelection.efforts
            let valid = conversations[index].provider == "claude" ? (effort.isEmpty || claudeEfforts.contains(effort))
                : conversations[index].provider == "codex" && (effort.isEmpty || model?.efforts.contains(where: { $0.rawValue == effort }) == true)
            guard valid else { return }
            conversations[index].reasoningEffort = effort
        }
        invalidateContextPreview(); invalidateSessionSpinePilot(); persist()
    }

    func choosePanelWorkspace(conversationID: UUID, in panel: WorkspacePanelModel? = nil) {
        guard !operationBusy, !isRunning(conversationID), let original = conversations.first(where: { $0.id == conversationID }), !original.archived else { return }
        let picker = NSOpenPanel()
        picker.canChooseDirectories = true; picker.canChooseFiles = false; picker.allowsMultipleSelection = false
        picker.prompt = L10n.text("Выбрать папку")
        presentFilePicker(picker, in: panel?.presentations) { [weak self] response in
            guard response == .OK, let url = picker.url, let self else { return }
            Task {
                let state = self.execution(for: conversationID)
                do {
                    let result = try await state.client.request("workspace_status", ["workspace_root": .string(url.path)])
                    guard !self.operationBusy, !state.running, let index = self.conversations.firstIndex(where: { $0.id == conversationID }),
                          !self.conversations[index].archived,
                          self.conversations[index].workspacePath == original.workspacePath,
                          self.conversations[index].provider == original.provider else { return }
                    self.discardAgentGrants(for: conversationID)
                    self.conversations[index].workspacePath = result["root"].text
                    self.conversations[index].pendingFiles = []
                    self.projectNoteSelections[conversationID] = nil; self.preparedSkillTasks[conversationID] = nil
                    self.persist()
                } catch {
                    if let panel { panel.error = error.localizedDescription } else { self.report(error) }
                }
            }
        }
    }
}

extension Conversation {
    var hasDraftOrMessages: Bool {
        !messages.isEmpty || !draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
            || !pendingFiles.isEmpty || !pendingImages.isEmpty || !pendingPDFs.isEmpty
            || !pendingCriteria.isEmpty || draftContinuation != nil
    }
}
