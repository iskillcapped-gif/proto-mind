import AppKit
import Combine
import Foundation
import UniformTypeIdentifiers

enum WorkspaceSection: String {
    case chat, commands, overview, workspace, memory, goals, skills, github
    var libraryCollection: LibraryCollection? { LibraryCollection(rawValue: rawValue) }
}

struct PendingOperatorAction: Identifiable {
    let id = UUID()
    let text: String
    let conversationID: UUID
    let summary: String
}

struct PendingPersonaActivation: Identifiable {
    let id = UUID()
    let conversationID: UUID
    let provider: String
    let model: String
    let accessMode: String
    let workspaceRoot: String?
    let readinessHash: String
}

@MainActor
final class AppModel: ObservableObject {
    @Published var conversations: [Conversation] = []
    // Unsent panel launchers are UI drafts, not entries in the conversation list.
    @Published var provisionalPanelConversations: Set<UUID> = []
    @Published var selectedID: UUID? {
        didSet {
            if !initializing, oldValue != selectedID { dictation.stop() }
            if !initializing, let id = selectedID {
                _ = execution(for: id)
                liveVoice.updateContext(app: self)
            }
            if !initializing, let oldValue, oldValue != selectedID { finishPanelDraft(oldValue) }
        }
    }
    @Published var section: WorkspaceSection = .chat {
        didSet { if !initializing, section != .chat { dictation.stop() } }
    }
    @Published var composer = "" { didSet { if !initializing { dictation.composerChanged() }; draftChanged() } }
    @Published var composerRevision = 0
    @Published var bootstrap: JSONValue = .null
    let codexAccounts: CodexAccounts
    private var accountsObservation: AnyCancellable?
    var account: JSONValue { get { selectedCodexAccount.account } set { selectedCodexAccount.account = newValue } }
    var codexUsage: CodexUsageModel { selectedCodexAccount.usage }
    var presentedCodexAccount: CodexAccountConnection?
    let apiConnections: ModelAPIConnections
    let messengers: MessengerConnections
    let telegram: TelegramRemoteModel
    let liveVoice: LiveVoiceModel
    let dictation: DictationModel
    let responseAttention: ResponseAttention
    private var attentionObservation: AnyCancellable?
    let sidebarProjectOrder: SidebarProjectOrder
    let desktop: DesktopPresentation
    let presentations = WorkspacePresentations()
    @Published var showSettings = false
    @Published var showFirstLaunch = false
    @Published var exitPrompt: WorkspaceExitPrompt?
    var discardUnsavedOnExit = false
    @Published var showLiveVoice = false {
        didSet { if oldValue != showLiveVoice { desktop.setVoiceVisible(showLiveVoice, app: self) } }
    }
    @Published var showCodexUsage = false
    @Published var showCodexAccounts = false
    var codexAccountsConversationID: UUID?
    var models: [JSONValue] { get { selectedCodexAccount.models } set { selectedCodexAccount.models = newValue } }
    @Published var modelSelectionNotice: String?
    @Published var codexThreadStatus: JSONValue = .null
    @Published var loadingCodexThreadStatus = false
    @Published var idleStatus = "Готов"
    @Published var operationBusy = false
    @Published var executions: [UUID: ConversationExecution] = [:]
    var connecting: Bool { get { selectedCodexAccount.connecting } set { selectedCodexAccount.connecting = newValue } }
    @Published var cloudConsent = false {
        didSet {
            guard !initializing, !restoringPreferences else { return }
            do {
                try savePreferences()
                invalidateSessionSpinePilot()
                if !cloudConsent { discardAgentGrants(); codexAccounts.clearUsage(); liveVoice.stop() }
            }
            catch {
                restoringPreferences = true
                cloudConsent = oldValue
                restoringPreferences = false
                report(error)
            }
        }
    }
    @Published var personaEnabled = false {
        didSet {
            guard !initializing, !restoringPreferences else { return }
            do {
                try savePreferences()
                invalidateContextPreview()
                invalidateSessionSpinePilot()
            }
            catch {
                restoringPreferences = true
                personaEnabled = oldValue
                restoringPreferences = false
                report(error)
            }
        }
    }
    var loginPending: Bool { get { selectedCodexAccount.loginPending } set { selectedCodexAccount.loginPending = newValue } }
    @Published var error: String?
    @Published var historyPersistence = HistoryPersistenceState()
    @Published var showHistoryBackups = false
    @Published var settingsSection: NativeSettingsSection = .models
    @Published var historyBackupPreview: ChatBackupPreview?
    @Published var historyBackupItems: [ChatBackupSummary] = []
    @Published var historyBackupError: String?
    @Published var historyBackupNotice: String?
    @Published var showInspector = false
    let workspacePanels: WorkspacePanels
    var workspacePanel: WorkspacePanelModel { workspacePanels.activePanel }
    let github = GitHubModel()
    let privateBackup = PrivateBackupModel()
    @Published var showPrivateBackup = false
    @Published var privateBackupRestartRequired = false
    var quitAfterPrivateBackup = false
    @Published var inspectedMessageID: UUID?
    @Published var pendingAction: PendingOperatorAction?
    @Published var pendingPersonaActivation: PendingPersonaActivation?
    @Published var pendingAgentAccess: PendingAgentAccess?
    @Published var agentGrants: [UUID: AgentAccessGrant] = [:]
    @Published var rememberedAgentAccess: [RememberedAgentAccess] = []
    var restoringAgentAccess: [UUID: Task<AgentAccessGrant, Error>] = [:]
    @Published var computerUsePermissionIssue = false
    @Published var showWorkSessions = false
    @Published var showConversationHistory = false
    @Published var transcriptDestination: TranscriptDestination?
    @Published var inspectedWorkSessionID: String?
    @Published var showContextDesk = false
    @Published var showPersonaInspector = false
    @Published var showMemoryWorkshop = false
    @Published var skillAuthoring: SkillAuthoringModel?
    @Published var skillInspection: SkillInspectionModel?
    @Published var skillOutcome: SkillOutcomeModel?
    @Published var skillDecision: SkillDecisionModel?
    @Published var skillLifecycleApply: SkillLifecycleApplyModel?
    @Published var skillRestore: SkillRestoreModel?
    @Published var skillHistory: SkillHistoryModel?
    @Published var projectMemory: ProjectMemoryModel?
    @Published var memorySuggestion: MemorySuggestionModel?
    @Published var reviewedMemorySuggestions: Set<String> = []
    @Published var projectNoteSelections: [UUID: [ProjectNote]] = [:]
    @Published var skillTask: SkillTaskModel?
    @Published var preparedSkillTasks: [UUID: PreparedSkillTask] = [:]
    @Published var showTaskCriteria = false
    @Published var imagePreview: NativeImagePreview?
    @Published var pdfPreview: NativePDFPreview?
    @Published var loadingPDFPreview = false
    @Published var loadingImagePreview = false
    @Published private(set) var imageThumbnails: [String: NSImage] = [:]
    @Published var attachmentDropPreview: NativeAttachmentDropPreview?
    @Published var attachmentDropTargeted = false
    @Published var loadingDroppedAttachments = false
    @Published var contextPreview: NativeContextPreview?
    @Published var contextPreviewError: String?
    @Published private(set) var loadingContextPreview = false
    @Published private(set) var personaPreview: NativePersonaPreview?
    @Published private(set) var personaPreviewError: String?
    @Published private(set) var loadingPersonaPreview = false
    @Published private(set) var personaReadiness: NativePersonaReadiness?
    @Published private(set) var personaReadinessError: String?
    @Published private(set) var loadingPersonaReadiness = false
    @Published var workSessions: [NativeWorkSession] = []
    @Published var workSessionsTotal: Int?
    @Published var workSessionsNextCursor: JSONValue?
    @Published var workSessionsPath = ""
    @Published var workSessionsWarning: String?
    @Published var workSessionsActionError: String?
    @Published var loadingWorkSessions = false
    @Published var sessionSpinePreview: NativeSessionSpinePreview?
    @Published var loadingSessionSpinePreview = false
    @Published var sessionSpineReadiness: NativeSessionSpineActivationReadiness?
    @Published var sessionSpinePilotGrant: NativeSessionSpinePilotGrant?
    @Published var sessionSpineAcceptance: NativeSessionSpineAcceptanceRehearsal?
    @Published var sessionSpineAcceptanceGrant: NativeSessionSpineAcceptanceGrant?
    @Published var sessionSpineWriterPreview: NativeSessionSpineWriterPreview?
    @Published var sessionSpineWriterReceipt: NativeSessionSpineWriterReceipt?
    @Published var loadingSessionSpineWriter = false
    @Published var applyingSessionSpineWriter = false
    @Published var conversationSearch = ""
    @Published var showArchived = false
    @Published var workspaceStatus: JSONValue = .null
    @Published var workspaceListing: JSONValue = .null
    @Published var filePreview: JSONValue = .null
    @Published var loadingWorkspace = false
    @Published var workspaceError: String?
    @Published var ollamaStatus: JSONValue = .null
    @Published private(set) var libraryPage: LibraryPage?
    @Published private(set) var libraryDetail: LibraryDetail?
    @Published private(set) var selectedLibraryID: String?
    @Published var libraryQuery = ""
    @Published var libraryFilter: LibraryFilter = .current
    @Published private(set) var loadingLibrary = false
    @Published private(set) var loadingLibraryDetail = false
    @Published private(set) var libraryError: String?
    @Published private(set) var libraryDetailError: String?
    @Published var memoryWorkshop: NativeMemoryWorkshop?
    @Published private(set) var loadingMemoryWorkshop = false
    @Published var memoryWorkshopError: String?
    @Published private(set) var learningCandidateID: String?
    @Published private(set) var learningReview: NativeLearningReview?
    @Published private(set) var learningPreview: NativeLearningPreview?
    @Published private(set) var learningResult: NativeLearningResult?
    @Published private(set) var learningReviewError: String?
    @Published private(set) var loadingLearningReview = false
    @Published private(set) var committingLearningReview = false
    @Published private(set) var learningReferenceIDs: [String] = []
    @Published var learningReferenceQuery = "" { didSet { invalidateLearningConfirmation() } }
    @Published var learningReason = "" { didSet { invalidateLearningConfirmation() } }
    let serviceClient: BridgeClient
    var client: BridgeClient { selectedExecution?.client ?? serviceClient }
    let store: ChatStore
    let preferences: PreferenceStore
    private var started = false
    var initializing = true
    private var restoringPreferences = false
    var restoringDraft = false
    var dirtyDraft = false
    var draftSave: Task<Void, Never>?
    private var libraryRequest = UUID()
    private var libraryDetailRequest = UUID()
    private var memoryWorkshopRequest = UUID()
    private var learningReviewRequest = UUID()
    private var pendingLearningSelection: NativeLearningSelection?
    var workSessionsRequest = UUID()
    var sessionSpinePreviewRequest = UUID()
    private var contextPreviewRequest = UUID()
    private var personaPreviewRequest = UUID()
    private var personaReadinessRequest = UUID()

    init(configuration: LaunchConfiguration = .load(), historyStore: ChatStore? = nil,
         uiDefaults: UserDefaults = .standard, dictationSpeech: DictationRecognizing? = nil,
         telegram: TelegramRemoteModel? = nil) {
        workspacePanels = WorkspacePanels(stateDirectory: configuration.stateDirectory, defaults: uiDefaults)
        apiConnections = ModelAPIConnections(stateDirectory: configuration.stateDirectory, defaults: uiDefaults)
        messengers = MessengerConnections(profile: configuration.stateDirectory)
        self.telegram = telegram ?? TelegramRemoteModel(profile: configuration.stateDirectory)
        desktop = DesktopPresentation(stateDirectory: configuration.stateDirectory, defaults: uiDefaults)
        liveVoice = LiveVoiceModel(stateDirectory: configuration.stateDirectory)
        dictation = DictationModel(stateDirectory: configuration.stateDirectory, defaults: uiDefaults, speech: dictationSpeech)
        responseAttention = ResponseAttention(stateDirectory: configuration.stateDirectory, defaults: uiDefaults)
        sidebarProjectOrder = SidebarProjectOrder(stateDirectory: configuration.stateDirectory, defaults: uiDefaults)
        serviceClient = BridgeClient(configuration: configuration)
        codexAccounts = CodexAccounts(configuration: configuration, defaults: uiDefaults, mainClient: serviceClient)
        store = historyStore ?? ChatStore(directory: configuration.stateDirectory)
        preferences = PreferenceStore(directory: configuration.stateDirectory)
        do {
            try PrivateStateAccess.requireAvailable(configuration.projectRoot.appendingPathComponent("proto_mind/data"))
            let archive = try store.load()
            conversations = archive.conversations
            selectedID = conversations.first { $0.id == archive.selectedID }?.id ?? conversations.first?.id
        } catch {
            self.error = error.localizedDescription
            historyPersistence = HistoryPersistenceState(failure: error.localizedDescription, requiresRecovery: store.writeBlocked)
        }
        do {
            try PrivateStateAccess.requireAvailable(configuration.projectRoot.appendingPathComponent("proto_mind/data"))
            let saved = try preferences.load()
            cloudConsent = saved.cloudProcessingAllowed
            personaEnabled = saved.personaEnabled
            rememberedAgentAccess = saved.cloudProcessingAllowed ? saved.rememberedAgentAccess : []
        }
        catch { self.error = error.localizedDescription }
        if conversations.isEmpty {
            var chat = Conversation()
            if configuration.isPortable { chat.provider = "codex"; chat.model = "" }
            conversations = [chat]
            selectedID = chat.id
        }
        composer = selected?.draft ?? ""
        serviceClient.onEvent = { [weak self] event in
            guard let self, let state = self.executions.values.first(where: { $0.requestID == event["request_id"].text }) else { return }
            self.receiveExecutionEvent(event, state: state)
        }
        if let id = selectedID { _ = execution(for: id) }
        presentations.reveal = { [weak self] in
            guard let self else { return }
            self.dictation.stop()
            self.desktop.revealMainContent()
        }
        if !historyPersistence.blocksSubmission { responseAttention.prune(conversations) }
        attentionObservation = responseAttention.objectWillChange.sink { [weak self] _ in self?.objectWillChange.send() }
        accountsObservation = codexAccounts.objectWillChange.sink { [weak self] in self?.objectWillChange.send() }
        for chat in conversations { _ = codexAccounts.connection(chat.codexAccountID) }
        initializing = false
    }

    func savePreferences() throws {
        guard !privateBackupRestartRequired else { throw NativeError.message(L10n.text("Перезапустите Proto-Mind после восстановления данных.")) }
        try preferences.save(NativePreferences(
            cloudProcessingAllowed: cloudConsent,
            personaEnabled: personaEnabled,
            rememberedAgentAccess: cloudConsent ? rememberedAgentAccess : []
        ))
    }

    var selected: Conversation? { conversations.first { $0.id == selectedID } }
    var listedConversations: [Conversation] {
        conversations.filter { !provisionalPanelConversations.contains($0.id) }
    }
    var visibleConversations: [Conversation] {
        let query = conversationSearch.trimmingCharacters(in: .whitespacesAndNewlines)
        return listedConversations.filter { chat in
            chat.archived == showArchived && (query.isEmpty || chat.title.localizedCaseInsensitiveContains(query)
                || chat.messages.contains { $0.searchableText.localizedCaseInsensitiveContains(query) })
        }.sorted { $0.updatedAt == $1.updatedAt ? $0.id.uuidString < $1.id.uuidString : $0.updatedAt > $1.updatedAt }
    }
    var messages: [ChatMessage] { selected?.messages ?? [] }
    var evidenceMessage: ChatMessage? {
        messages.first { $0.id == inspectedMessageID } ?? messages.last { $0.role != "user" && !$0.isError }
    }
    var contextLabel: String {
        bootstrap["context_injection"].isNull ? L10n.text("Context: неизвестно") : bootstrap["context_injection"].flag ? L10n.text("Context: включён") : L10n.text("Context: выключен")
    }

    var contextRequestParameters: [String: JSONValue]? {
        guard let conversation = selected else { return nil }
        var params: [String: JSONValue] = [
            "text": .string(composer), "conversation_id": .string(conversation.id.uuidString),
            "provider": .string(conversation.provider), "model": .string(conversation.model),
            "reasoning_effort": .string(conversation.provider == "codex" ? conversation.reasoningEffort : ""),
            "history": .array(conversation.history), "files": .array(conversation.pendingFiles),
            "images": .array(conversation.pendingImages),
            "pdfs": .array(conversation.pendingPDFs),
            "project_memory": .array(pendingProjectNotes.map(\.selection)),
            "criteria": .array(conversation.pendingCriteria.map(JSONValue.string)),
            "auto_skills": .bool(conversation.provider == "codex" && conversation.autoSkillsEnabled),
            "auto_project_recall": .bool(conversation.provider == "codex" && conversation.autoProjectRecallEnabled),
            "project_recall_algorithm": .string("local_content_terms_v3"),
            "persona_enabled": .bool(personaEnabled && conversation.provider != "api"),
            "cloud_consent": .bool(cloudConsent), "access_mode": .string(fullAccessEnabled ? "full_access" : "chat")
        ]
        if let path = conversation.workspacePath { params["workspace_root"] = .string(path) }
        if let pendingSkillTask { params["skill_task"] = pendingSkillTask.selection }
        if fullAccessEnabled, let grant = agentGrants[conversation.id] {
            params["access_token"] = .string(grant.token)
        }
        return params
    }

    var personaRequestParameters: [String: JSONValue]? {
        guard let conversation = selected else { return nil }
        var params: [String: JSONValue] = [
            "conversation_id": .string(conversation.id.uuidString),
            "provider": .string(conversation.provider),
            "model": .string(conversation.model),
            "cloud_consent": .bool(cloudConsent),
            "access_mode": .string(fullAccessEnabled ? "full_access" : "chat")
        ]
        if let path = conversation.workspacePath { params["workspace_root"] = .string(path) }
        if fullAccessEnabled, let grant = agentGrants[conversation.id] {
            params["access_token"] = .string(grant.token)
        }
        return params
    }

    func invalidateContextPreview() { loadingContextPreview = false; contextPreview = nil; contextPreviewError = nil; contextPreviewRequest = UUID() }

    func refreshContextPreview() async {
        guard !busy, await prepareSelectedAgentAccess() else { return }
        guard !busy, let conversationID = selectedID, let params = contextRequestParameters else { return }
        let request = UUID()
        contextPreviewRequest = request
        contextPreview = nil; contextPreviewError = nil; loadingContextPreview = true
        defer { if contextPreviewRequest == request { loadingContextPreview = false } }
        do {
            let value = try await turnClient.request("context_preview", params)
            guard contextPreviewRequest == request, selectedID == conversationID else { return }
            guard params == contextRequestParameters else {
                throw NativeError.message(L10n.text("Состав запроса изменился. Обновите локальный просмотр."))
            }
            let preview = try NativeContextPreview(value)
            if !preview.manifest["knowledge_context"]["project_recall"].isNull {
                let recall = try NativeProjectRecallReport(preview.manifest["knowledge_context"]["project_recall"])
                guard params["auto_project_recall"] == .bool(true), params["project_memory"]?.items.isEmpty == true,
                      recall.matches(conversation: conversationID, text: params["text"]!.text.trimmingCharacters(in: .whitespacesAndNewlines),
                                     workspace: params["workspace_root"]?.text, mode: params["access_mode"]!.text) else { throw NativeProjectRecallReport.error() }
            }
            contextPreview = preview
        } catch {
            if contextPreviewRequest == request && selectedID == conversationID { contextPreviewError = error.localizedDescription }
        }
    }

    func refreshPersonaPreview() async {
        guard !busy, await prepareSelectedAgentAccess() else { return }
        guard !busy, let conversationID = selectedID, let params = personaRequestParameters else { return }
        let request = UUID()
        personaPreviewRequest = request
        personaPreview = nil; personaPreviewError = nil; loadingPersonaPreview = true
        defer { if personaPreviewRequest == request { loadingPersonaPreview = false } }
        do {
            let value = try await turnClient.request("persona_preview", params)
            guard personaPreviewRequest == request, selectedID == conversationID else { return }
            guard params == personaRequestParameters else {
                throw NativeError.message(L10n.text("Провайдер, модель или доступ изменились. Обновите PersonaSnapshot."))
            }
            personaPreview = try NativePersonaPreview(value)
        } catch {
            if personaPreviewRequest == request && selectedID == conversationID {
                personaPreviewError = error.localizedDescription
            }
        }
    }

    func refreshPersonaReadiness() async {
        guard !busy, await prepareSelectedAgentAccess() else { return }
        guard !busy, let conversationID = selectedID, let params = personaRequestParameters else { return }
        let request = UUID()
        personaReadinessRequest = request
        personaReadiness = nil; personaReadinessError = nil; loadingPersonaReadiness = true
        defer { if personaReadinessRequest == request { loadingPersonaReadiness = false } }
        do {
            let value = try await turnClient.request("persona_readiness", params)
            guard personaReadinessRequest == request, selectedID == conversationID else { return }
            guard params == personaRequestParameters else {
                throw NativeError.message(L10n.text("Провайдер, модель или доступ изменились. Обновите readiness evidence."))
            }
            personaReadiness = try NativePersonaReadiness(value)
        } catch {
            if personaReadinessRequest == request && selectedID == conversationID {
                personaReadinessError = error.localizedDescription
            }
        }
    }

    func refreshPersonaInspector() async {
        await refreshPersonaPreview()
        await refreshPersonaReadiness()
    }

    func preparePersonaActivation() async -> Bool {
        guard !globalBusy, await prepareSelectedAgentAccess() else { return false }
        guard !globalBusy, !personaEnabled, let conversation = selected,
              ["codex", "ollama"].contains(conversation.provider),
              let params = personaRequestParameters else {
            report(NativeError.message(L10n.text("Brother Persona доступна только для выбранного Codex или Ollama диалога.")))
            return false
        }
        if conversation.provider == "codex" && conversation.model.isEmpty {
            report(NativeError.message(L10n.text("Сначала явно выберите модель Codex; значение аккаунта по умолчанию не создаёт проверяемый self-model.")))
            return false
        }
        let conversationID = conversation.id
        loadingPersonaReadiness = true
        defer { loadingPersonaReadiness = false }
        do {
            let readiness = try NativePersonaReadiness(await turnClient.request("persona_readiness", params))
            guard selectedID == conversationID, params == personaRequestParameters else {
                throw NativeError.message(L10n.text("Провайдер, модель или доступ изменились. Проверьте readiness заново."))
            }
            guard readiness.status == "READY", readiness.value["selected_adapter_ready"] == .bool(true) else {
                let reason = readiness.blockers.first?.text ?? L10n.text("выбранный adapter не готов")
                throw NativeError.message(L10n.format("Brother Persona не готова к включению: \(reason)"))
            }
            personaReadiness = readiness
            personaReadinessError = nil
            pendingPersonaActivation = PendingPersonaActivation(
                conversationID: conversationID,
                provider: conversation.provider,
                model: conversation.model,
                accessMode: fullAccessEnabled ? "full_access" : "chat",
                workspaceRoot: conversation.workspacePath,
                readinessHash: readiness.value["activation_fingerprint"].text
            )
            return true
        } catch {
            pendingPersonaActivation = nil
            report(error)
            return false
        }
    }

    func confirmPersonaActivation() async {
        guard !globalBusy, await prepareSelectedAgentAccess() else { return }
        guard !globalBusy, !personaEnabled, let pending = pendingPersonaActivation,
              pending.conversationID == selectedID, let conversation = selected,
              pending.provider == conversation.provider,
              pending.model == conversation.model,
              pending.accessMode == (fullAccessEnabled ? "full_access" : "chat"),
              pending.workspaceRoot == conversation.workspacePath,
              let params = personaRequestParameters else {
            pendingPersonaActivation = nil
            report(NativeError.message(L10n.text("Условия Persona activation изменились. Начните проверку заново.")))
            return
        }
        loadingPersonaReadiness = true
        defer { loadingPersonaReadiness = false }
        do {
            let readiness = try NativePersonaReadiness(await turnClient.request("persona_readiness", params))
            guard selectedID == pending.conversationID, params == personaRequestParameters,
                  readiness.status == "READY", readiness.value["selected_adapter_ready"] == .bool(true),
                  readiness.value["activation_fingerprint"].text == pending.readinessHash else {
                throw NativeError.message(L10n.text("Readiness evidence изменилось. Ничего не включено; проверьте заново."))
            }
            pendingPersonaActivation = nil
            personaReadiness = readiness
            personaEnabled = true
            guard personaEnabled else { return }
            error = nil
            status = "Brother Persona включена · gates будут повторно проверены при Send"
        } catch {
            pendingPersonaActivation = nil
            report(error)
        }
    }

    func cancelPersonaActivation() { pendingPersonaActivation = nil }

    func disablePersona() {
        pendingPersonaActivation = nil
        personaEnabled = false
        if !personaEnabled {
            error = nil
            status = "Brother Persona выключена · следующий ход использует legacy prompt"
        }
    }

    func inspectArtifacts(_ run: NativeWorkSession) async throws -> NativeArtifactDesk {
        let params = try artifactParameters(run)
        return try NativeArtifactDesk(await client.request("artifact_list", params), run: run)
    }

    func inspectArtifact(_ artifactID: String, run: NativeWorkSession) async throws -> NativeArtifactPreview {
        var params = try artifactParameters(run)
        params["artifact_id"] = .string(artifactID)
        return try NativeArtifactPreview(await client.request("artifact_preview", params), run: run, artifactID: artifactID)
    }

    func setPendingCriteria(_ values: [String], conversationID: UUID) throws {
        guard !busy, selectedID == conversationID, selected?.archived != true,
              let index = conversations.firstIndex(where: { $0.id == conversationID }) else {
            throw NativeError.message(L10n.text("Диалог изменился или занят. Критерии не сохранены."))
        }
        let items = try NativeTaskCriteria.validate(values)
        let previous = conversations[index].pendingCriteria
        conversations[index].pendingCriteria = items
        do {
            try saveHistory()
        } catch {
            conversations[index].pendingCriteria = previous
            throw error
        }
    }

    func previewManualReview(_ run: NativeWorkSession, selection: JSONValue) async throws -> NativeManualReviewPreview {
        var params = try artifactParameters(run)
        params["review"] = selection
        return try NativeManualReviewPreview(await client.request("review_preview", params), run: run, selection: selection)
    }

    func saveManualReview(_ run: NativeWorkSession, preview: NativeManualReviewPreview) async throws -> NativeWorkSession {
        guard preview.ready, preview.value["run_id"].text == run.id, preview.value["run_fingerprint"] == run.value["fingerprint"] else {
            throw NativeError.message(L10n.text("Сначала проверьте точную ручную оценку. Ничего не записано."))
        }
        var params = try artifactParameters(run)
        params["review"] = preview.selection
        params["preview_fingerprint"] = preview.value["preview_fingerprint"]
        params["confirmation"] = .string("RECORD OPERATOR REVIEW ONLY")
        busy = true
        defer { busy = false }
        let value = try await client.request("review_save", params)
        guard value["schema"].text == "proto_mind.native_review_saved.v1", value["no_execution"] == .bool(true),
              value["mutation"].text == "private_run_review_only", value["run"]["id"].text == run.id else {
            throw NativeError.message(L10n.text("Ответ записи не прошёл проверку. Обновите журнал перед повтором: оценка могла сохраниться."))
        }
        let updated = try NativeWorkSession(value["run"])
        if let index = workSessions.firstIndex(where: { $0.id == updated.id }) { workSessions[index] = updated }
        return updated
    }

    private func artifactParameters(_ run: NativeWorkSession) throws -> [String: JSONValue] {
        guard !busy, let selected, UUID(uuidString: run.value["conversation_id"].text) == selected.id else {
            throw NativeError.message(L10n.text("Дождитесь завершения запроса и откройте журнал выбранного диалога."))
        }
        var params: [String: JSONValue] = ["conversation_id": .string(selected.id.uuidString), "run": run.reference]
        if let path = selected.workspacePath { params["workspace_root"] = .string(path) }
        return params
    }
    var providerLabel: String {
        switch selected?.provider { case "api": return L10n.text("Модель через API"); case "codex": return L10n.text("Codex · облако"); case "mock": return L10n.text("Mock · локальный тест"); default: return L10n.text("Ollama · локально") }
    }
    var computerUseAvailable: Bool { bootstrap["agent"]["computer_use"]["available"].flag }
    var computerUseVersion: String { bootstrap["agent"]["computer_use"]["version"].text }
    var fullAccessLabel: String { computerUseAvailable ? L10n.text("Полный доступ + экран") : L10n.text("Полный доступ + интернет") }
    var fullAccessEnabled: Bool {
        guard let conversation = selected else { return false }
        return hasAgentAccessSelection(conversation)
    }

    func requestAgentAccess(conversationID: UUID? = nil, in source: WorkspacePresentations? = nil) {
        guard let id = conversationID ?? selectedID,
              let conversation = conversations.first(where: { $0.id == id }),
              !operationBusy, !isRunning(id), !conversation.archived, conversation.provider == "codex", cloudConsent else {
            report(NativeError.message(L10n.text("Сначала выберите Codex и разрешите облачную обработку."))); return
        }
        let request = PendingAgentAccess(conversationID: id, workspace: conversation.workspacePath)
        presentations.prepare(request.id, in: source ?? presentations.currentDestination)
        pendingAgentAccess = request
    }

    func confirmAgentAccess() async {
        guard !operationBusy, let request = pendingAgentAccess, !isRunning(request.conversationID),
              let conversation = conversations.first(where: { $0.id == request.conversationID }), !conversation.archived,
              request.workspace == conversation.workspacePath, cloudConsent, conversation.provider == "codex" else {
            pendingAgentAccess = nil; return
        }
        pendingAgentAccess = nil; busy = true
        defer { busy = false }
        do {
            var params: [String: JSONValue] = ["conversation_id": .string(request.conversationID.uuidString),
                "mode": .string("full_access"), "cloud_consent": .bool(cloudConsent),
                "confirmation": .string("ALLOW FULL MAC ACCESS")]
            if let workspace = request.workspace { params["workspace_root"] = .string(workspace) }
            let result = try await execution(for: request.conversationID).client.request("agent_access", params)
            guard result["mode"].text == "full_access", !result["token"].text.isEmpty,
                  result["workspace_root"] == (request.workspace.map(JSONValue.string) ?? .null),
                  let current = conversations.first(where: { $0.id == request.conversationID }), request.workspace == current.workspacePath,
                  cloudConsent, current.provider == "codex", !current.archived else { throw NativeError.message(L10n.text("Не удалось проверить разрешение агента.")) }
            invalidateSessionSpinePilot()
            agentGrants[request.conversationID] = AgentAccessGrant(token: result["token"].text, workspace: request.workspace,
                bridgeGeneration: execution(for: request.conversationID).client.connectionGeneration)
            let previous = rememberedAgentAccess
            rememberedAgentAccess.removeAll { $0.conversationID == request.conversationID }
            rememberedAgentAccess.append(RememberedAgentAccess(conversationID: request.conversationID, workspace: request.workspace))
            do { try savePreferences() }
            catch {
                rememberedAgentAccess = previous
                agentGrants.removeValue(forKey: request.conversationID)
                _ = try? await execution(for: request.conversationID).client.request("agent_access", ["conversation_id": .string(request.conversationID.uuidString), "mode": .string("chat")])
                throw error
            }
            invalidateContextPreview()
            error = nil
            status = computerUseAvailable
                ? L10n.text("Полный доступ, интернет и Computer Use включены для этого диалога")
                : L10n.text("Полный доступ и интернет включены; Computer Use недоступен")
        } catch { report(error) }
    }

    func disableAgentAccess(conversationID: UUID? = nil) async {
        guard let id = conversationID ?? selectedID, !operationBusy, !isRunning(id) else { return }
        let previous = rememberedAgentAccess
        rememberedAgentAccess.removeAll { $0.conversationID == id }
        do { try savePreferences() }
        catch { rememberedAgentAccess = previous; report(error); return }
        invalidateSessionSpinePilot()
        restoringAgentAccess.removeValue(forKey: id)?.cancel()
        agentGrants.removeValue(forKey: id)
        invalidateContextPreview()
        busy = true
        defer { busy = false }
        do {
            _ = try await execution(for: id).client.request("agent_access", ["conversation_id": .string(id.uuidString), "mode": .string("chat")])
            error = nil
            status = "Обычный чат · инструменты выключены"
        } catch { report(error) }
    }

    func openAutomationSettings() {
        guard let url = URL(string: "x-apple.systempreferences:com.apple.preference.security?Privacy_Automation") else {
            report(NativeError.message(L10n.text("Не удалось открыть настройки Automation."))); return
        }
        NSWorkspace.shared.open(url)
    }

    func clearError() {
        error = nil
        computerUsePermissionIssue = false
    }

    func discardAgentGrants(for id: UUID? = nil, forgetSelection: Bool = true) {
        let ids = id.map { [$0] } ?? Array(Set(agentGrants.keys).union(rememberedAgentAccess.map(\.conversationID)))
        if forgetSelection {
            rememberedAgentAccess.removeAll { id == nil || $0.conversationID == id }
            if !initializing { do { try savePreferences() } catch { report(error) } }
        }
        pendingAgentAccess = nil
        for id in ids { restoringAgentAccess.removeValue(forKey: id)?.cancel() }
        for id in ids where agentGrants.removeValue(forKey: id) != nil {
            guard let state = executions[id] else { continue }
            Task {
                _ = try? await state.client.request("agent_access", ["conversation_id": .string(id.uuidString), "mode": .string("chat")])
            }
        }
    }

    func start() async {
        guard !started else { return }; started = true
        do {
            try PrivateStateAccess.requireAvailable(client.configuration.stateDirectory)
            try PrivateStateAccess.requireAvailable(client.configuration.projectRoot.appendingPathComponent("proto_mind/data"))
        } catch {
            showPrivateBackup = true
            await privateBackup.refresh(app: self)
            report(error)
            return
        }
        showFirstLaunch = FirstLaunch.shouldPresent(serviceClient.configuration)
        do {
            bootstrap = try await serviceClient.request("bootstrap"); status = "Готов"
            await refreshWorkSessions()
            if selected?.provider == "codex" {
                await refreshCodexThreadStatus()
                if cloudConsent { await refreshAccount() }
            }
        }
        catch { report(error) }
    }

    func refresh() async {
        do { bootstrap = try await serviceClient.request("bootstrap") }
        catch { report(error) }
        await refreshWorkSessions()
    }

    func showMessage(_ message: ChatMessage, in source: WorkspacePresentations? = nil) {
        presentations.prepare("inspector", in: source ?? presentations.currentDestination)
        inspectedMessageID = message.id; showInspector = true
    }

    func checkOllama() async {
        guard !busy else { return }
        do { ollamaStatus = try await client.request("ollama_status") }
        catch { report(error) }
    }

    func chooseWorkspace(in source: WorkspacePresentations? = nil) {
        guard !busy else { return }
        let panel = NSOpenPanel()
        panel.canChooseDirectories = true; panel.canChooseFiles = false; panel.allowsMultipleSelection = false
        panel.prompt = L10n.pick("Подключить только для чтения", "Open for reading")
        panel.directoryURL = selected?.workspacePath.map { URL(fileURLWithPath: $0) } ?? client.configuration.projectRoot
        let conversationID = selectedID
        presentFilePicker(panel, in: source) { [weak self] response in
            guard response == .OK, let url = panel.url, let self, self.selectedID == conversationID else { return }
            Task { await self.bindWorkspace(url.path) }
        }
    }

    func bindWorkspace(_ path: String) async {
        guard !busy, !loadingWorkspace, let id = selectedID else { return }
        loadingWorkspace = true; workspaceError = nil
        defer { loadingWorkspace = false }
        do {
            let value = try await client.request("workspace_status", ["workspace_root": .string(path)])
            guard let index = conversations.firstIndex(where: { $0.id == id }) else { return }
            invalidateSessionSpinePilot()
            conversations[index].workspacePath = value["root"].text
            projectNoteSelections[id] = nil; projectMemory = nil; memorySuggestion = nil; invalidateContextPreview()
            preparedSkillTasks[id] = nil; skillTask = nil
            closeLearningReview()
            memoryWorkshop = nil
            discardAgentGrants(for: id)
            conversations[index].pendingFiles = []
            persist()
            if selectedID == id {
                resetWorkspaceView(); workspaceStatus = value; section = .chat; workspacePanel.showFiles()
                codexThreadStatus = .null
            }
        } catch { workspaceError = error.localizedDescription }
        loadingWorkspace = false
        if selectedID == id && workspaceError == nil {
            await refreshWorkspace()
            await refreshCodexThreadStatus()
        }
    }

    func refreshWorkspace(_ path: String = "") async {
        guard canEditMessageAttachments, !loadingWorkspace, let root = selected?.workspacePath, let id = selectedID else { return }
        loadingWorkspace = true; workspaceError = nil
        defer { loadingWorkspace = false }
        do {
            let status = try await client.request("workspace_status", ["workspace_root": .string(root)])
            let listing = try await client.request("workspace_list", ["workspace_root": .string(root), "path": .string(path)])
            if selectedID == id { workspaceStatus = status; workspaceListing = listing; filePreview = .null }
        } catch { workspaceError = error.localizedDescription }
    }

    func openWorkspaceEntry(_ entry: JSONValue, in targetPanel: WorkspacePanelModel? = nil) async {
        let panel = targetPanel ?? workspacePanel
        if entry["directory"].flag { await refreshWorkspace(entry["path"].text); return }
        guard canEditMessageAttachments, !loadingWorkspace, let root = selected?.workspacePath, let id = selectedID else { return }
        let suffix = URL(fileURLWithPath: entry["path"].text).pathExtension.lowercased()
        if ["png", "jpg", "jpeg", "pdf"].contains(suffix) {
            do {
                let url = try NativeAttachmentDrop.localURL(URL(fileURLWithPath: root).appendingPathComponent(entry["path"].text))
                _ = try NativeAttachmentDrop.relativePath(url, workspace: root)
                if suffix == "pdf" { await previewPDF(url.path, inWorkspacePanel: true, targetPanel: panel) }
                else { await previewImage(url.path, inWorkspacePanel: true, targetPanel: panel) }
            } catch {
                workspaceError = error.localizedDescription
                panel.visible = true; panel.error = error.localizedDescription
            }
            return
        }
        loadingWorkspace = true; workspaceError = nil
        defer { loadingWorkspace = false }
        do {
            let preview = try await client.request("workspace_read", ["workspace_root": .string(root), "path": entry["path"]])
            guard selectedID == id, selected?.workspacePath == root else { return }
            guard preview["read_only"].flag, preview["path"] == entry["path"] else {
                throw NativeError.message(L10n.text("Просмотр относится к другому файлу."))
            }
            filePreview = preview
            panel.open(.text(WorkspaceTextPreview(conversationID: id, root: root, value: preview)))
        } catch {
            guard selectedID == id, selected?.workspacePath == root else { return }
            workspaceError = error.localizedDescription
            panel.visible = true; panel.error = error.localizedDescription
        }
    }

    func attachPreview() {
        guard canEditMessageAttachments, !filePreview.isNull, let index = conversations.firstIndex(where: { $0.id == selectedID }) else { return }
        let path = filePreview["path"].text
        let existing = conversations[index].pendingFiles.firstIndex { $0["path"].text == path }
        guard existing != nil || conversations[index].pendingFiles.count < 3 else {
            workspaceError = L10n.text("К одному сообщению можно выбрать до трёх файлов."); return
        }
        let count = min(6000, filePreview["characters"].integer)
        let item: JSONValue = .object(["path": .string(path), "sha256": filePreview["sha256"],
                                       "included_chars": .number(Double(count)), "truncated": .bool(filePreview["characters"].integer > count)])
        if let existing { conversations[index].pendingFiles[existing] = item }
        else { conversations[index].pendingFiles.append(item) }
        persist(); section = .chat
    }

    func removePendingFile(_ path: String) {
        guard canEditMessageAttachments, let index = conversations.firstIndex(where: { $0.id == selectedID }) else { return }
        conversations[index].pendingFiles.removeAll { $0["path"].text == path }
        persist()
    }

    var imageDestinationNotice: String {
        guard selected?.provider == "codex" else {
            return L10n.text("Изображения пока поддерживаются только через Codex. Выбор локальный; Ollama/Mock не получат эти файлы. Провайдер не меняется автоматически.")
        }
        guard cloudConsent else {
            return L10n.text("Сейчас всё остаётся на Mac. Для отправки изображений в OpenAI разрешите облачную обработку; выбор файла сам по себе её не включает.")
        }
        let selectedModel = models.first { selected?.model.isEmpty == false ? $0["id"].text == selected?.model : $0["default"].flag }
        guard selectedModel?["input_modalities"].items.contains(.string("image")) == true else {
            return L10n.text("Каталог пока не подтверждает изображения для выбранной модели. Обновите модели или выберите совместимую; Send повторно проверит поддержку.")
        }
        return L10n.text("После «Отправить» выбранные изображения уйдут в OpenAI вместе с сообщением. До этого просмотр локальный. В следующих запросах они не пересылаются автоматически.")
    }

    func chooseImage() {
        guard canReceiveAttachments, let conversationID = selectedID else { return }
        let panel = NSOpenPanel()
        panel.canChooseDirectories = false; panel.canChooseFiles = true; panel.allowsMultipleSelection = false
        panel.allowedContentTypes = [.png, .jpeg]; panel.resolvesAliases = false
        panel.prompt = L10n.text("Просмотреть локально")
        panel.message = L10n.text("Выберите PNG/JPEG до 4 МиБ. Этот шаг ничего не отправляет в модель.")
        let completion: (NSApplication.ModalResponse) -> Void = { [weak self] response in
            guard response == .OK, let url = panel.url, let self, self.selectedID == conversationID else { return }
            Task { await self.previewImage(url.path) }
        }
        presentFilePicker(panel, completion: completion)
    }

    func previewImage(_ path: String, expectedSHA: String? = nil, canAttach: Bool = true, inWorkspacePanel: Bool = false, targetPanel: WorkspacePanelModel? = nil) async {
        let panel = targetPanel ?? workspacePanel
        guard canEditMessageAttachments, !loadingImagePreview, !loadingDroppedAttachments, !loadingPDFPreview,
              pdfPreview == nil, attachmentDropPreview == nil,
              let conversationID = selectedID else { return }
        loadingImagePreview = true
        defer { loadingImagePreview = false }
        do {
            var params: [String: JSONValue] = ["path": .string(path)]
            if let expectedSHA { params["expected_sha256"] = .string(expectedSHA) }
            let result = try await client.request("image_preview", params)
            guard selectedID == conversationID, canEditMessageAttachments else { return }
            let preview = try NativeImagePreview(result, conversationID: conversationID, canAttach: canAttach)
            guard preview.source.path == path, expectedSHA == nil || preview.source.sha256 == expectedSHA else {
                throw NativeError.message(L10n.text("Предпросмотр относится к другому изображению. Ничего не прикреплено."))
            }
            if imageThumbnails.count >= 12 { imageThumbnails.removeAll() }
            imageThumbnails[preview.source.sha256] = preview.thumbnail
            if inWorkspacePanel { panel.open(.image(preview)) }
            else { imagePreview = preview }
        } catch { report(error) }
    }

    func attachImage(_ preview: NativeImagePreview) throws {
        guard preview.canAttach, canEditMessageAttachments, selectedID == preview.conversationID, selected?.archived != true,
              let index = conversations.firstIndex(where: { $0.id == preview.conversationID }) else {
            throw NativeError.message(L10n.text("Диалог изменился или занят. Изображение не прикреплено."))
        }
        var next = conversations[index].pendingImages.filter { $0["path"].text != preview.source.path }
        next.append(preview.source.value)
        try updatePendingImages(next, index: index)
        section = .chat
    }

    func removePendingImage(_ path: String) {
        guard canEditMessageAttachments, let index = conversations.firstIndex(where: { $0.id == selectedID }) else { return }
        do { try updatePendingImages(conversations[index].pendingImages.filter { $0["path"].text != path }, index: index) }
        catch { report(error) }
    }

    private func updatePendingImages(_ next: [JSONValue], index: Int) throws {
        try NativeImageAttachment.validate(next)
        let previous = conversations[index].pendingImages
        conversations[index].pendingImages = next
        do {
            try saveHistory()
        } catch {
            conversations[index].pendingImages = previous
            throw error
        }
    }

    var canReceiveAttachments: Bool {
        selected != nil && selected?.archived != true && canEditMessageAttachments
            && !loadingDroppedAttachments && !loadingImagePreview && !loadingPDFPreview
            && imagePreview == nil && pdfPreview == nil && attachmentDropPreview == nil
            && pendingAction == nil && pendingAgentAccess == nil
    }

    func receiveAttachmentDrop(_ providers: [NSItemProvider]) -> Bool {
        guard canReceiveAttachments, let conversation = selected else { return false }
        guard (1...NativeAttachmentDrop.maximumItems).contains(providers.count),
              providers.allSatisfy({ $0.hasItemConformingToTypeIdentifier(UTType.fileURL.identifier) }) else {
            error = L10n.text("Перетащите до 6 локальных файлов. Черновик не изменён."); return false
        }
        loadingDroppedAttachments = true
        Task {
            await finishAttachmentDrop(conversation) {
                var urls: [URL] = []
                for provider in providers { urls.append(try await NativeAttachmentDrop.loadURL(provider)) }
                return urls
            }
        }
        return true
    }

    func receiveAttachmentDrop(_ urls: [URL]) -> Bool {
        guard canReceiveAttachments, let conversation = selected else { return false }
        loadingDroppedAttachments = true
        Task { await finishAttachmentDrop(conversation) { urls } }
        return true
    }

    func previewDroppedAttachments(_ urls: [URL]) async {
        guard canReceiveAttachments, let conversation = selected else { return }
        loadingDroppedAttachments = true
        await finishAttachmentDrop(conversation) { urls }
    }

    private func finishAttachmentDrop(_ conversation: Conversation, load: () async throws -> [URL]) async {
        defer { loadingDroppedAttachments = false; attachmentDropTargeted = false }
        do {
            let urls = try NativeAttachmentDrop.selection(await load())
            if urls.contains(where: NativeAttachmentDrop.isPDF) {
                guard urls.count == 1 else { throw NativeError.message(L10n.text("Перетащите один PDF отдельно, чтобы выбрать страницы. Остальные файлы добавьте следующим действием; черновик не изменён.")) }
                pdfPreview = try await readPDFPreview(urls[0].path, pages: [1], conversation: conversation, canAttach: true)
                return
            }
            guard urls.filter(NativeAttachmentDrop.isImage).count <= 3,
                  urls.filter({ !NativeAttachmentDrop.isImage($0) }).count <= 3 else {
                throw NativeError.message(L10n.text("Допускается до 3 изображений и 3 текстовых файлов. Черновик не изменён."))
            }
            var images: [NativeImagePreview] = [], files: [NativeDroppedFile] = []
            for url in urls {
                guard selectedID == conversation.id, selected?.workspacePath == conversation.workspacePath, canEditMessageAttachments else { return }
                if NativeAttachmentDrop.isImage(url) {
                    let value = try await client.request("image_preview", ["path": .string(url.path)])
                    let preview = try NativeImagePreview(value, conversationID: conversation.id, canAttach: true)
                    guard preview.source.path == url.path else { throw NativeError.message(L10n.text("Предпросмотр относится к другому изображению.")) }
                    images.append(preview)
                } else {
                    let path = try NativeAttachmentDrop.relativePath(url, workspace: conversation.workspacePath)
                    let value = try await client.request("workspace_read", ["workspace_root": .string(conversation.workspacePath ?? ""), "path": .string(path)])
                    files.append(try NativeDroppedFile(value, path: path))
                }
            }
            guard selectedID == conversation.id, let current = selected, canEditMessageAttachments else { return }
            let preview = NativeAttachmentDropPreview(conversationID: conversation.id, workspace: conversation.workspacePath, images: images, files: files)
            _ = try preview.merged(with: current)
            attachmentDropPreview = preview
        } catch {
            if selectedID == conversation.id { report(error) }
        }
    }

    func attachDrop(_ preview: NativeAttachmentDropPreview) throws {
        guard canEditMessageAttachments, !loadingDroppedAttachments, selectedID == preview.conversationID,
              let index = conversations.firstIndex(where: { $0.id == preview.conversationID }) else {
            throw NativeError.message(L10n.text("Диалог изменился или занят. Файлы не прикреплены."))
        }
        let previous = conversations[index]
        let next = try preview.merged(with: previous)
        conversations[index].pendingImages = next.images
        conversations[index].pendingFiles = next.files
        do {
            try saveHistory()
        } catch {
            conversations[index] = previous
            throw error
        }
        if imageThumbnails.count + preview.images.count > 12 { imageThumbnails.removeAll() }
        for image in preview.images { imageThumbnails[image.source.sha256] = image.thumbnail }
        section = .chat
    }

    var pdfDestinationNotice: String {
        if selected?.provider == "codex" {
            return cloudConsent
                ? L10n.text("Только после «Отправить» выбранный текст страниц уйдёт в OpenAI. Оригинал PDF не пересылается и не копируется. В истории сохраняются лишь метаданные вложения.")
                : L10n.text("Просмотр локальный. Для отправки текста PDF в Codex нужно облачное разрешение. Выбор PDF его не включает и ничего не отправляет.")
        }
        return selected?.provider == "mock"
            ? L10n.text("Mock проверяет интерфейс, но не анализирует PDF. Оригинал и текст остаются локально; провайдер не меняется автоматически.")
            : L10n.text("После «Отправить» выбранный текст страниц получит локальная Ollama. Оригинал PDF не пересылается и не копируется.")
    }

    func choosePDF() {
        guard canReceiveAttachments, let conversationID = selectedID else { return }
        let panel = NSOpenPanel()
        panel.canChooseDirectories = false; panel.canChooseFiles = true; panel.allowsMultipleSelection = false
        panel.allowedContentTypes = [.pdf]; panel.resolvesAliases = false
        panel.prompt = L10n.text("Выбрать страницы")
        panel.message = L10n.text("PDF с текстовым слоем до 8 МиБ. Локальный просмотр, без отправки.")
        let completion: (NSApplication.ModalResponse) -> Void = { [weak self] response in
            guard response == .OK, let url = panel.url, let self, self.selectedID == conversationID else { return }
            Task { await self.previewPDF(url.path) }
        }
        presentFilePicker(panel, completion: completion)
    }

    func readPDFPreview(_ path: String, pages: [Int], conversation: Conversation,
                                canAttach: Bool, expectedSHA: String? = nil) async throws -> NativePDFPreview {
        let path = try NativeAttachmentDrop.localURL(URL(fileURLWithPath: path)).path
        var params: [String: JSONValue] = ["path": .string(path), "pages": .array(pages.map { .number(Double($0)) })]
        if let expectedSHA { params["expected_sha256"] = .string(expectedSHA) }
        let result = try await client.request("pdf_preview", params)
        guard canEditMessageAttachments, selectedID == conversation.id,
              selected?.workspacePath == conversation.workspacePath, selected?.archived != true else {
            throw NativeError.message(L10n.text("Диалог изменился или занят. PDF не прикреплён и не отправлен."))
        }
        let preview = try NativePDFPreview(result, conversationID: conversation.id, workspace: conversation.workspacePath, canAttach: canAttach)
        guard preview.source.path == path, preview.source.pages == pages,
              expectedSHA == nil || preview.source.sha256 == expectedSHA else {
            throw NativeError.message(L10n.text("Предпросмотр не соответствует выбранному PDF или страницам."))
        }
        return preview
    }

    func previewPDF(_ path: String, expected: JSONValue? = nil, canAttach: Bool = true, inWorkspacePanel: Bool = false, targetPanel: WorkspacePanelModel? = nil) async {
        let panel = targetPanel ?? workspacePanel
        guard canReceiveAttachments, let conversation = selected else { return }
        loadingPDFPreview = true
        defer { loadingPDFPreview = false }
        do {
            let source = try expected.map(NativePDFAttachment.init)
            let preview = try await readPDFPreview(path, pages: source?.pages ?? [1], conversation: conversation,
                                                   canAttach: canAttach, expectedSHA: source?.sha256)
            guard expected == nil || preview.source.value == expected else {
                throw NativeError.message(L10n.text("Текст выбранных страниц изменился. Уберите PDF и выберите его заново."))
            }
            if inWorkspacePanel { panel.open(.pdf(preview)) }
            else { pdfPreview = preview }
        } catch { if selectedID == conversation.id { report(error) } }
    }

    func reloadPDFPreview(_ preview: NativePDFPreview, pages: [Int]) async throws -> NativePDFPreview {
        guard canEditMessageAttachments, !loadingPDFPreview, preview.canAttach, let conversation = selected,
              conversation.id == preview.conversationID, conversation.workspacePath == preview.workspace,
              pdfPreview?.source.path == preview.source.path else {
            throw NativeError.message(L10n.text("Выбор PDF изменился или занят. Ничего не отправлено."))
        }
        loadingPDFPreview = true
        defer { loadingPDFPreview = false }
        return try await readPDFPreview(preview.source.path, pages: pages, conversation: conversation,
                                         canAttach: true, expectedSHA: preview.source.sha256)
    }

    func attachPDF(_ preview: NativePDFPreview) throws {
        guard preview.canAttach, preview.hasText, canEditMessageAttachments, !loadingPDFPreview,
              !loadingDroppedAttachments, selectedID == preview.conversationID,
              selected?.workspacePath == preview.workspace, selected?.archived != true,
              let index = conversations.firstIndex(where: { $0.id == preview.conversationID }) else {
            throw NativeError.message(L10n.text("PDF не готов, диалог изменился или занят. Ничего не прикреплено."))
        }
        let next = conversations[index].pendingPDFs.filter { $0["path"].text != preview.source.path } + [preview.source.value]
        try updatePendingPDFs(next, index: index)
        section = .chat
    }

    func removePendingPDF() {
        guard canEditMessageAttachments, let index = conversations.firstIndex(where: { $0.id == selectedID }) else { return }
        do { try updatePendingPDFs([], index: index) } catch { report(error) }
    }

    private func updatePendingPDFs(_ next: [JSONValue], index: Int) throws {
        try NativePDFAttachment.validate(next)
        let previous = conversations[index].pendingPDFs
        conversations[index].pendingPDFs = next
        do {
            try saveHistory()
        } catch { conversations[index].pendingPDFs = previous; throw error }
    }

    func resetWorkspaceView() { workspaceStatus = .null; workspaceListing = .null; filePreview = .null; workspaceError = nil }

    func showLibrary(_ collection: LibraryCollection) async {
        guard !busy else { return }
        section = collection.section
        libraryQuery = ""; libraryFilter = .current
        libraryPage = nil
        await loadLibraryPage()
    }

    func loadLibraryPage(offset: Int = 0) async {
        guard !busy, let collection = section.libraryCollection else { return }
        let request = UUID()
        libraryRequest = request; libraryDetailRequest = UUID()
        loadingLibrary = true; loadingLibraryDetail = false
        libraryError = nil; libraryDetailError = nil; libraryDetail = nil; selectedLibraryID = nil
        let query = libraryQuery, filter = libraryFilter
        defer { if libraryRequest == request { loadingLibrary = false } }
        do {
            let params: [String: JSONValue] = ["collection": .string(collection.rawValue),
                "query": .string(query), "filter": .string(filter.rawValue), "offset": .number(Double(offset))]
            let value = try await localKnowledgeResult(capability: "search", method: "capability_search",
                                                       legacyMethod: "library_list", params: params)
            let page = try LibraryPage.decode(value, for: collection)
            guard libraryRequest == request, section.libraryCollection == collection else { return }
            libraryPage = page
        } catch {
            guard libraryRequest == request, section.libraryCollection == collection else { return }
            libraryPage = nil; libraryError = error.localizedDescription
        }
    }

    func inspectLibrary(_ item: LibraryItem) async {
        guard !busy, let collection = section.libraryCollection,
              libraryPage?.collection == collection, libraryPage?.items.contains(item) == true else { return }
        let request = UUID()
        libraryDetailRequest = request
        selectedLibraryID = item.id; libraryDetail = nil; libraryDetailError = nil; loadingLibraryDetail = true
        defer { if libraryDetailRequest == request { loadingLibraryDetail = false } }
        do {
            let params: [String: JSONValue] = ["collection": .string(collection.rawValue),
                "record_key": .string(item.id), "expected_sha256": .string(item.storeSha256)]
            let value = try await localKnowledgeResult(capability: "fetch", method: "capability_fetch",
                                                       legacyMethod: "library_inspect", params: params)
            let detail = try LibraryDetail.decode(value, for: collection, recordKey: item.id)
            guard libraryDetailRequest == request, selectedLibraryID == item.id,
                  section.libraryCollection == collection else { return }
            libraryDetail = detail
        } catch {
            guard libraryDetailRequest == request, section.libraryCollection == collection else { return }
            libraryDetailError = error.localizedDescription
        }
    }

    func openMemoryEvidence(recordID: String) async {
        guard !busy, !recordID.isEmpty, recordID.count <= 200 else { return }
        showInspector = false
        section = .memory
        libraryQuery = recordID
        libraryFilter = .all
        await loadLibraryPage()
        guard let page = libraryPage, page.collection == .memory else { return }
        let exact = page.items.filter { $0.recordId == recordID }
        guard exact.count == 1 else {
            libraryError = exact.isEmpty
                ? L10n.format("Запись \(recordID) больше не найдена в локальной памяти.")
                : L10n.format("ID \(recordID) неоднозначен между слоями памяти; выберите запись вручную.")
            return
        }
        await inspectLibrary(exact[0])
    }

    func openMemoryWorkshop() {
        guard !busy, selectedID != nil else { return }
        closeLearningReview()
        memoryWorkshop = nil
        memoryWorkshopError = nil
        showMemoryWorkshop = true
    }

    func refreshMemoryWorkshop() async {
        guard !busy, let conversation = selected else { return }
        let request = UUID()
        memoryWorkshopRequest = request
        loadingMemoryWorkshop = true
        memoryWorkshopError = nil
        defer { if memoryWorkshopRequest == request { loadingMemoryWorkshop = false } }
        do {
            var params: [String: JSONValue] = [
                "conversation_id": .string(conversation.id.uuidString),
            ]
            if let workspace = conversation.workspacePath {
                params["workspace_root"] = .string(workspace)
            }
            let value = try await client.request("memory_workshop", params)
            let report = try NativeMemoryWorkshop.decode(value, conversationId: conversation.id.uuidString)
            guard memoryWorkshopRequest == request, selectedID == conversation.id,
                  selected?.workspacePath == conversation.workspacePath else { return }
            memoryWorkshop = report
        } catch {
            guard memoryWorkshopRequest == request, selectedID == conversation.id else { return }
            memoryWorkshop = nil
            memoryWorkshopError = error.localizedDescription
        }
    }

    func prepareMemoryWorkshopCommand(_ command: String) {
        guard !command.isEmpty, !busy else { return }
        setComposer(command)
        showMemoryWorkshop = false
        section = .chat
    }

    var learningSelection: NativeLearningSelection? {
        guard let conversation = selected, !conversation.archived, let candidateID = learningCandidateID else { return nil }
        return NativeLearningSelection(conversationID: conversation.id, candidateID: candidateID,
            workspace: conversation.workspacePath, memoryIDs: learningReferenceIDs.sorted(),
            query: learningReferenceQuery, reason: learningReason)
    }

    func closeLearningReview() {
        guard !committingLearningReview else { return }
        learningReviewRequest = UUID()
        learningCandidateID = nil; learningReview = nil; learningResult = nil
        learningReviewError = nil; loadingLearningReview = false
        learningReferenceIDs = []; learningReferenceQuery = ""; learningReason = ""
        invalidateLearningConfirmation()
    }

    func invalidateLearningConfirmation() {
        learningPreview = nil
        pendingLearningSelection = nil
    }

    func openLearningReview(candidateID: String) async {
        guard !busy, !client.turnOutstanding, selected?.archived == false else { return }
        closeLearningReview()
        learningCandidateID = candidateID
        await refreshLearningReview()
    }

    func setLearningReference(_ id: String, selected: Bool) {
        guard !busy, !loadingLearningReview, learningReview?.proposal == nil,
              learningReview?.references.contains(where: { $0.recordId == id && $0.selectable }) == true else { return }
        var ids = Set(learningReferenceIDs)
        if selected { guard ids.count < 20 else { return }; ids.insert(id) }
        else { ids.remove(id) }
        learningReferenceIDs = ids.sorted()
        invalidateLearningConfirmation()
    }

    func refreshLearningReview(clearError: Bool = true) async {
        guard !busy, !client.turnOutstanding, let selection = learningSelection else { return }
        let request = UUID()
        learningReviewRequest = request
        loadingLearningReview = true
        invalidateLearningConfirmation()
        if clearError { learningReviewError = nil }
        defer { if learningReviewRequest == request { loadingLearningReview = false } }
        do {
            let value = try await client.request("memory_learning_review", selection.parameters)
            let review = try NativeLearningReview.decode(value, selection: selection)
            guard learningReviewRequest == request, learningSelection == selection else { return }
            learningReview = review
            if review.proposal != nil { learningReferenceIDs = review.requestedMemoryIds.sorted() }
        } catch {
            guard learningReviewRequest == request, learningSelection == selection else { return }
            learningReview = nil
            learningReviewError = error.localizedDescription
        }
    }

    func previewLearningOperation(_ operation: NativeLearningOperation) async {
        guard !busy, !client.turnOutstanding, !loadingLearningReview, let selection = learningSelection else { return }
        let request = UUID()
        learningReviewRequest = request
        loadingLearningReview = true
        learningReviewError = nil
        invalidateLearningConfirmation()
        defer { if learningReviewRequest == request { loadingLearningReview = false } }
        do {
            var params = selection.parameters
            params["operation"] = .string(operation.rawValue)
            let value = try await client.request("memory_learning_preview", params)
            let preview = try NativeLearningPreview.decode(value, selection: selection, operation: operation)
            guard learningReviewRequest == request, learningSelection == selection else { return }
            learningPreview = preview
            pendingLearningSelection = selection
        } catch {
            guard learningReviewRequest == request, learningSelection == selection else { return }
            learningReviewError = error.localizedDescription
        }
    }

    func confirmLearningOperation(token: String, acknowledgeGlobal: Bool) async {
        guard !globalBusy, !client.turnOutstanding, !loadingLearningReview,
              let selection = pendingLearningSelection, learningSelection == selection,
              let preview = learningPreview, preview.accepts(token: token, acknowledgeGlobal: acknowledgeGlobal) else { return }
        busy = true; committingLearningReview = true
        learningReviewError = nil
        invalidateLearningConfirmation()
        do {
            var params = selection.parameters
            params["operation"] = .string(preview.operation.rawValue)
            params["preview_fingerprint"] = .string(preview.previewFingerprint)
            params["confirmation_token"] = .string(token)
            params["acknowledge_global_memory"] = .bool(acknowledgeGlobal)
            let value = try await client.request("memory_learning_confirm", params)
            let result = try NativeLearningResult.decode(value, selection: selection, operation: preview.operation)
            if learningSelection == selection {
                learningResult = result
                status = result.memoryMutationPerformed ? "Один урок сохранён и проверен" : "Решение сохранено только до закрытия ядра"
            }
        } catch {
            if learningSelection == selection {
                learningReviewError = L10n.format("\(error.localizedDescription) Автоповтора нет. Проверьте текущую карточку и receipt перед новым действием.")
            }
        }
        busy = false; committingLearningReview = false
        // After an uncertain result, inspect only. Never retry a confirmation.
        if learningSelection == selection { await refreshLearningReview(clearError: false) }
    }

    private func localKnowledgeResult(capability: String, method: String, legacyMethod: String,
                                      params: [String: JSONValue]) async throws -> JSONValue {
        do {
            let envelope = try await client.request(method, params)
            return try LocalKnowledgeEnvelope.structured(envelope, capability: capability)
        } catch {
            // A newer app bundle can still open against an older bridge during
            // a rolling local rebuild. Only method absence gets the old direct
            // read path; malformed envelopes and store errors remain visible.
            guard error.localizedDescription.contains("Unknown native bridge method") else { throw error }
            return try await client.request(legacyMethod, params)
        }
    }

    func copy(_ text: String) {
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(text, forType: .string)
    }

    func append(_ message: ChatMessage, to id: UUID) {
        guard let index = conversations.firstIndex(where: { $0.id == id }) else { return }
        conversations[index].messages.append(message)
        conversations[index].updatedAt = Date()
        responseAttention.record(message, conversationID: id)
    }

    func report(_ error: Error) { self.error = error.localizedDescription; status = "Нужна проверка" }

}
