import AppKit
import Foundation

extension AppModel {
    /// Every surface edits the existing archive through its one writer. No shadow AppModel or store.
    func setConversationDraft(_ text: String, id: UUID) {
        guard let index = conversations.firstIndex(where: { $0.id == id }), !conversations[index].archived else { return }
        if selectedID == id { setComposer(text); return }
        conversations[index].draft = text
        if text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty { conversations[index].draftContinuation = nil }
        dirtyDraft = true; historyPersistence.hasUnsavedChanges = true
        draftSave?.cancel()
        draftSave = Task { [weak self] in
            do { try await Task.sleep(nanoseconds: 500_000_000) } catch { return }
            self?.flushDraft()
        }
    }

    func newPanelConversation(in panel: WorkspacePanelModel) {
        guard canNavigateConversations, panel.tabs.count < WorkspacePanelModel.maximumTabs else { return }
        var chat = Conversation()
        if let source = selected {
            chat.provider = source.provider; chat.model = source.model; chat.reasoningEffort = source.reasoningEffort
            chat.workspacePath = source.workspacePath; chat.apiConnectionID = source.apiConnectionID
        } else if serviceClient.configuration.isPortable { chat.provider = "codex"; chat.model = "" }
        // A new conversation inherits a model and folder, never an authorization grant.
        conversations.insert(chat, at: 0)
        _ = execution(for: chat.id)
        panel.open(.conversation(chat.id))
        persist()
    }

    func configureConversation(_ id: UUID, provider: String? = nil, model: String? = nil, effort: String? = nil) {
        guard !operationBusy, !isRunning(id), let index = conversations.firstIndex(where: { $0.id == id }),
              !conversations[index].archived else { return }
        if let provider, provider != conversations[index].provider {
            guard ["codex", "ollama", "mock"].contains(provider) else { return }
            discardAgentGrants(for: id)
            conversations[index].provider = provider
            conversations[index].apiConnectionID = nil
            conversations[index].model = ""; conversations[index].reasoningEffort = ""
        }
        if let model {
            guard conversations[index].provider != "codex" || model.isEmpty || codexModels.contains(where: { $0.id == model }) else { return }
            conversations[index].model = model
            conversations[index].reasoningEffort = ""
        }
        if let effort {
            let model = codexModels.first { conversations[index].model.isEmpty ? $0.isDefault : $0.id == conversations[index].model }
            guard conversations[index].provider == "codex", effort.isEmpty || model?.efforts.contains(where: { $0.rawValue == effort }) == true else { return }
            conversations[index].reasoningEffort = effort
        }
        invalidateContextPreview(); invalidateSessionSpinePilot(); persist()
    }

    func choosePanelWorkspace(conversationID: UUID) {
        guard !operationBusy, !isRunning(conversationID), let original = conversations.first(where: { $0.id == conversationID }), !original.archived else { return }
        let picker = NSOpenPanel()
        picker.canChooseDirectories = true; picker.canChooseFiles = false; picker.allowsMultipleSelection = false
        picker.prompt = "Выбрать папку"
        presentFilePicker(picker) { [weak self] response in
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
                } catch { self.report(error) }
            }
        }
    }
}
