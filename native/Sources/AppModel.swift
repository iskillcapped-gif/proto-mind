import AppKit
import Foundation
import UniformTypeIdentifiers

enum WorkspaceSection: String {
    case chat, commands, overview, workspace, memory, goals, skills
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
    @Published var selectedID: UUID?
    @Published var section: WorkspaceSection = .chat
    @Published var composer = "" { didSet { draftChanged() } }
    @Published private(set) var composerRevision = 0
    @Published var bootstrap: JSONValue = .null
    @Published var account: JSONValue = .null
    @Published var models: [JSONValue] = []
    @Published var modelSelectionNotice: String?
    @Published private(set) var codexThreadStatus: JSONValue = .null
    @Published private(set) var loadingCodexThreadStatus = false
    @Published var busy = false
    @Published var connecting = false
    @Published var cloudConsent = false {
        didSet {
            guard !initializing, !restoringPreferences else { return }
            do {
                try savePreferences()
                if !cloudConsent { discardAgentGrants() }
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
            do { try savePreferences() }
            catch {
                restoringPreferences = true
                personaEnabled = oldValue
                restoringPreferences = false
                report(error)
            }
        }
    }
    @Published var loginPending = false
    @Published var stream = ""
    @Published var status = "Запускаем локальное ядро"
    @Published var error: String?
    @Published var showInspector = false
    @Published var inspectedMessageID: UUID?
    @Published var pendingAction: PendingOperatorAction?
    @Published private(set) var pendingPersonaActivation: PendingPersonaActivation?
    @Published var pendingAgentAccess: PendingAgentAccess?
    @Published private(set) var agentGrants: [UUID: AgentAccessGrant] = [:]
    @Published private(set) var agentItems: [JSONValue] = []
    @Published private(set) var agentReceipt: JSONValue = .null
    @Published var computerUsePermissionIssue = false
    @Published private(set) var workLog: JSONValue = .null
    @Published private(set) var turnStartedAt: Date?
    @Published var showWorkSessions = false
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
    @Published var autoSkillsReport: NativeAutoSkillsReport?
    @Published var showTaskCriteria = false
    @Published var imagePreview: NativeImagePreview?
    @Published var pdfPreview: NativePDFPreview?
    @Published private(set) var loadingPDFPreview = false
    @Published private(set) var loadingImagePreview = false
    @Published private(set) var imageThumbnails: [String: NSImage] = [:]
    @Published var attachmentDropPreview: NativeAttachmentDropPreview?
    @Published var attachmentDropTargeted = false
    @Published private(set) var loadingDroppedAttachments = false
    @Published private(set) var contextPreview: NativeContextPreview?
    @Published private(set) var contextPreviewError: String?
    @Published private(set) var loadingContextPreview = false
    @Published private(set) var personaPreview: NativePersonaPreview?
    @Published private(set) var personaPreviewError: String?
    @Published private(set) var loadingPersonaPreview = false
    @Published private(set) var personaReadiness: NativePersonaReadiness?
    @Published private(set) var personaReadinessError: String?
    @Published private(set) var loadingPersonaReadiness = false
    @Published private(set) var lastPersonaTurnReceipt: NativePersonaTurnReceipt?
    @Published private(set) var workSessions: [NativeWorkSession] = []
    @Published private(set) var workSessionsPath = ""
    @Published private(set) var workSessionsWarning: String?
    @Published var workSessionsActionError: String?
    @Published private(set) var loadingWorkSessions = false
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
    @Published private(set) var memoryWorkshop: NativeMemoryWorkshop?
    @Published private(set) var loadingMemoryWorkshop = false
    @Published private(set) var memoryWorkshopError: String?
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
    let client: BridgeClient
    let store: ChatStore
    let preferences: PreferenceStore
    private var activeRequest: String?
    private var started = false
    private var initializing = true
    private var restoringPreferences = false
    private var restoringDraft = false
    private var dirtyDraft = false
    private var draftSave: Task<Void, Never>?
    private var libraryRequest = UUID()
    private var libraryDetailRequest = UUID()
    private var memoryWorkshopRequest = UUID()
    private var learningReviewRequest = UUID()
    private var pendingLearningSelection: NativeLearningSelection?
    private var workSessionsRequest = UUID()
    private var contextPreviewRequest = UUID()
    private var personaPreviewRequest = UUID()
    private var personaReadinessRequest = UUID()

    init(configuration: LaunchConfiguration = .load()) {
        client = BridgeClient(configuration: configuration)
        store = ChatStore(directory: configuration.stateDirectory)
        preferences = PreferenceStore(directory: configuration.stateDirectory)
        do {
            let archive = try store.load()
            conversations = archive.conversations
            selectedID = conversations.first { $0.id == archive.selectedID }?.id ?? conversations.first?.id
        } catch { self.error = error.localizedDescription }
        do {
            let saved = try preferences.load()
            cloudConsent = saved.cloudProcessingAllowed
            personaEnabled = saved.personaEnabled
        }
        catch { self.error = error.localizedDescription }
        if conversations.isEmpty {
            let chat = Conversation()
            conversations = [chat]
            selectedID = chat.id
        }
        composer = selected?.draft ?? ""
        client.onEvent = { [weak self] event in
            guard let self, event["request_id"].text == self.activeRequest else { return }
            if event["event"].text == "answer_delta" { self.stream += event["delta"].text }
            if event["event"].text == "auto_skills", let report = try? NativeAutoSkillsReport(event["report"]) {
                self.autoSkillsReport = report
                if report.state == "selecting" { self.status = "Подбираю навык · без инструментов" }
            }
            if event["event"].text == "agent_activity" {
                let item = event["item"]
                guard !item["id"].text.isEmpty else { return }
                if let index = self.agentItems.firstIndex(where: { $0["id"] == item["id"] }) {
                    self.agentItems[index] = item
                } else if self.agentItems.count < 64 { self.agentItems.append(item) }
                if item["failure_code"].text == "macos_automation_permission_denied" {
                    self.computerUsePermissionIssue = true
                    self.error = "macOS не разрешила Proto-Mind управлять приложениями. Откройте Automation, разрешите Proto-Mind Native и начните новый ход с полным доступом. Автоповтора не было."
                    self.status = "Нужно разрешение macOS Automation"
                } else {
                    self.status = "Агент работает · \(self.agentItems.count) действий"
                }
            }
            if event["event"].text == "agent_run" {
                self.agentReceipt = event["receipt"]
                self.agentItems = self.agentReceipt["items"].items
            }
            if event["event"].text == "work_log" && event["log"]["schema"].text == "proto_mind.native_work_log.v1" {
                let incoming = event["log"]
                if WorkLogEventGate.shouldAccept(current: self.workLog, incoming: incoming) {
                    self.workLog = incoming
                }
            }
        }
        initializing = false
    }

    private func savePreferences() throws {
        try preferences.save(NativePreferences(
            cloudProcessingAllowed: cloudConsent,
            personaEnabled: personaEnabled
        ))
    }

    var selected: Conversation? { conversations.first { $0.id == selectedID } }
    var visibleConversations: [Conversation] {
        let query = conversationSearch.trimmingCharacters(in: .whitespacesAndNewlines)
        return conversations.filter { chat in
            chat.archived == showArchived && (query.isEmpty || chat.title.localizedCaseInsensitiveContains(query)
                || chat.messages.contains { $0.text.localizedCaseInsensitiveContains(query) })
        }.sorted { $0.updatedAt == $1.updatedAt ? $0.id.uuidString < $1.id.uuidString : $0.updatedAt > $1.updatedAt }
    }
    var messages: [ChatMessage] { selected?.messages ?? [] }
    var evidenceMessage: ChatMessage? {
        messages.first { $0.id == inspectedMessageID } ?? messages.last { $0.role != "user" && !$0.isError }
    }
    var contextLabel: String {
        bootstrap["context_injection"].isNull ? "Context: неизвестно" : bootstrap["context_injection"].flag ? "Context: включён" : "Context: выключен"
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
            "cloud_consent": .bool(cloudConsent), "access_mode": .string(fullAccessEnabled ? "full_access" : "chat")
        ]
        if let path = conversation.workspacePath { params["workspace_root"] = .string(path) }
        if let pendingSkillTask { params["skill_task"] = pendingSkillTask.selection }
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

    func invalidateContextPreview() { contextPreview = nil; contextPreviewError = nil; contextPreviewRequest = UUID() }

    func refreshContextPreview() async {
        guard !busy, let conversationID = selectedID, let params = contextRequestParameters else { return }
        let request = UUID()
        contextPreviewRequest = request
        contextPreview = nil; contextPreviewError = nil; loadingContextPreview = true
        defer { if contextPreviewRequest == request { loadingContextPreview = false } }
        do {
            let value = try await client.request("context_preview", params)
            guard contextPreviewRequest == request, selectedID == conversationID else { return }
            guard params == contextRequestParameters else {
                throw NativeError.message("Состав запроса изменился. Обновите локальный просмотр.")
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
        guard !busy, let conversationID = selectedID, let params = personaRequestParameters else { return }
        let request = UUID()
        personaPreviewRequest = request
        personaPreview = nil; personaPreviewError = nil; loadingPersonaPreview = true
        defer { if personaPreviewRequest == request { loadingPersonaPreview = false } }
        do {
            let value = try await client.request("persona_preview", params)
            guard personaPreviewRequest == request, selectedID == conversationID else { return }
            guard params == personaRequestParameters else {
                throw NativeError.message("Провайдер, модель или доступ изменились. Обновите PersonaSnapshot.")
            }
            personaPreview = try NativePersonaPreview(value)
        } catch {
            if personaPreviewRequest == request && selectedID == conversationID {
                personaPreviewError = error.localizedDescription
            }
        }
    }

    func refreshPersonaReadiness() async {
        guard !busy, let conversationID = selectedID, let params = personaRequestParameters else { return }
        let request = UUID()
        personaReadinessRequest = request
        personaReadiness = nil; personaReadinessError = nil; loadingPersonaReadiness = true
        defer { if personaReadinessRequest == request { loadingPersonaReadiness = false } }
        do {
            let value = try await client.request("persona_readiness", params)
            guard personaReadinessRequest == request, selectedID == conversationID else { return }
            guard params == personaRequestParameters else {
                throw NativeError.message("Провайдер, модель или доступ изменились. Обновите readiness evidence.")
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
        guard !busy, !personaEnabled, let conversation = selected,
              ["codex", "ollama"].contains(conversation.provider),
              let params = personaRequestParameters else {
            report(NativeError.message("Brother Persona доступна только для выбранного Codex или Ollama диалога."))
            return false
        }
        if conversation.provider == "codex" && conversation.model.isEmpty {
            report(NativeError.message("Сначала явно выберите модель Codex; значение аккаунта по умолчанию не создаёт проверяемый self-model."))
            return false
        }
        let conversationID = conversation.id
        loadingPersonaReadiness = true
        defer { loadingPersonaReadiness = false }
        do {
            let readiness = try NativePersonaReadiness(await client.request("persona_readiness", params))
            guard selectedID == conversationID, params == personaRequestParameters else {
                throw NativeError.message("Провайдер, модель или доступ изменились. Проверьте readiness заново.")
            }
            guard readiness.status == "READY", readiness.value["selected_adapter_ready"] == .bool(true) else {
                let reason = readiness.blockers.first?.text ?? "выбранный adapter не готов"
                throw NativeError.message("Brother Persona не готова к включению: \(reason)")
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
        guard !busy, !personaEnabled, let pending = pendingPersonaActivation,
              pending.conversationID == selectedID, let conversation = selected,
              pending.provider == conversation.provider,
              pending.model == conversation.model,
              pending.accessMode == (fullAccessEnabled ? "full_access" : "chat"),
              pending.workspaceRoot == conversation.workspacePath,
              let params = personaRequestParameters else {
            pendingPersonaActivation = nil
            report(NativeError.message("Условия Persona activation изменились. Начните проверку заново."))
            return
        }
        loadingPersonaReadiness = true
        defer { loadingPersonaReadiness = false }
        do {
            let readiness = try NativePersonaReadiness(await client.request("persona_readiness", params))
            guard selectedID == pending.conversationID, params == personaRequestParameters,
                  readiness.status == "READY", readiness.value["selected_adapter_ready"] == .bool(true),
                  readiness.value["activation_fingerprint"].text == pending.readinessHash else {
                throw NativeError.message("Readiness evidence изменилось. Ничего не включено; проверьте заново.")
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
            throw NativeError.message("Диалог изменился или занят. Критерии не сохранены.")
        }
        let items = try NativeTaskCriteria.validate(values)
        let previous = conversations[index].pendingCriteria
        conversations[index].pendingCriteria = items
        do {
            try store.save(ChatArchive(conversations: conversations, selectedID: selectedID))
            draftSave?.cancel(); dirtyDraft = false
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
            throw NativeError.message("Сначала проверьте точную ручную оценку. Ничего не записано.")
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
            throw NativeError.message("Ответ записи не прошёл проверку. Обновите журнал перед повтором: оценка могла сохраниться.")
        }
        let updated = try NativeWorkSession(value["run"])
        if let index = workSessions.firstIndex(where: { $0.id == updated.id }) { workSessions[index] = updated }
        return updated
    }

    private func artifactParameters(_ run: NativeWorkSession) throws -> [String: JSONValue] {
        guard !busy, let selected, UUID(uuidString: run.value["conversation_id"].text) == selected.id else {
            throw NativeError.message("Дождитесь завершения запроса и откройте журнал выбранного диалога.")
        }
        var params: [String: JSONValue] = ["conversation_id": .string(selected.id.uuidString), "run": run.reference]
        if let path = selected.workspacePath { params["workspace_root"] = .string(path) }
        return params
    }
    var providerLabel: String {
        switch selected?.provider { case "codex": return "Codex · облако"; case "mock": return "Mock · локальный тест"; default: return "Ollama · локально" }
    }
    var computerUseAvailable: Bool { bootstrap["agent"]["computer_use"]["available"].flag }
    var computerUseVersion: String { bootstrap["agent"]["computer_use"]["version"].text }
    var fullAccessLabel: String { computerUseAvailable ? "Полный доступ + экран" : "Полный доступ + интернет" }
    var fullAccessEnabled: Bool {
        guard client.connected, cloudConsent, selected?.provider == "codex", let id = selectedID,
              let grant = agentGrants[id] else { return false }
        return grant.workspace == selected?.workspacePath
    }

    func requestAgentAccess() {
        guard !busy, selected?.archived != true, selected?.provider == "codex", cloudConsent,
              let id = selectedID, let workspace = selected?.workspacePath else {
            report(NativeError.message("Сначала выберите Codex, разрешите облачную обработку и подключите рабочую папку.")); return
        }
        pendingAgentAccess = PendingAgentAccess(conversationID: id, workspace: workspace)
    }

    func confirmAgentAccess() async {
        guard !busy, let request = pendingAgentAccess, request.conversationID == selectedID,
              request.workspace == selected?.workspacePath, cloudConsent, selected?.provider == "codex" else {
            pendingAgentAccess = nil; return
        }
        pendingAgentAccess = nil; busy = true
        defer { busy = false }
        do {
            let result = try await client.request("agent_access", ["conversation_id": .string(request.conversationID.uuidString),
                "mode": .string("full_access"), "workspace_root": .string(request.workspace), "cloud_consent": .bool(cloudConsent),
                "confirmation": .string("ALLOW FULL MAC ACCESS")])
            guard result["mode"].text == "full_access", !result["token"].text.isEmpty,
                  result["workspace_root"].text == request.workspace else { throw NativeError.message("Не удалось проверить разрешение агента.") }
            agentGrants[request.conversationID] = AgentAccessGrant(token: result["token"].text, workspace: request.workspace)
            error = nil
            status = computerUseAvailable
                ? "Полный доступ, интернет и Computer Use включены для этого диалога"
                : "Полный доступ и интернет включены; Computer Use недоступен"
        } catch { report(error) }
    }

    func disableAgentAccess() async {
        guard !busy, let id = selectedID else { return }
        agentGrants.removeValue(forKey: id)
        busy = true
        defer { busy = false }
        do {
            _ = try await client.request("agent_access", ["conversation_id": .string(id.uuidString), "mode": .string("chat")])
            error = nil
            status = "Обычный чат · инструменты выключены"
        } catch { report(error) }
    }

    func openAutomationSettings() {
        guard let url = URL(string: "x-apple.systempreferences:com.apple.preference.security?Privacy_Automation") else {
            report(NativeError.message("Не удалось открыть настройки Automation.")); return
        }
        NSWorkspace.shared.open(url)
    }

    func clearError() {
        error = nil
        computerUsePermissionIssue = false
    }

    private func discardAgentGrants(for id: UUID? = nil) {
        let ids = id.map { [$0] } ?? Array(agentGrants.keys)
        pendingAgentAccess = nil
        for id in ids where agentGrants.removeValue(forKey: id) != nil {
            Task { _ = try? await client.request("agent_access", ["conversation_id": .string(id.uuidString), "mode": .string("chat")]) }
        }
    }

    func start() async {
        guard !started else { return }; started = true
        do {
            bootstrap = try await client.request("bootstrap"); status = "Готов"
            await refreshWorkSessions()
            if selected?.provider == "codex" {
                await refreshCodexThreadStatus()
                if cloudConsent { await refreshAccount() }
            }
        }
        catch { report(error) }
    }

    func refresh() async {
        do { bootstrap = try await client.request("bootstrap") }
        catch { report(error) }
        await refreshWorkSessions()
    }

    func refreshWorkSessions() async {
        guard !busy, let id = selectedID else { return }
        let request = UUID(); workSessionsRequest = request; loadingWorkSessions = true
        defer { if request == workSessionsRequest { loadingWorkSessions = false } }
        do {
            let page = try await client.request("work_sessions", ["conversation_id": .string(id.uuidString)])
            guard request == workSessionsRequest, id == selectedID else { return }
            guard page["schema"].text == "proto_mind.native_work_sessions.v1", page["read_only"] == .bool(true),
                  page["runs"].items.count <= 30 else { throw NativeError.message("Не удалось проверить локальный журнал работы.") }
            let runs = try page["runs"].items.map(NativeWorkSession.init)
            guard runs.allSatisfy({ UUID(uuidString: $0.value["conversation_id"].text) == id }) else {
                throw NativeError.message("Журнал относится к другому диалогу; он не показан.")
            }
            workSessions = runs; workSessionsPath = page["path"].text
            workSessionsWarning = page["warnings"].items.isEmpty ? nil : page["warnings"].items.map(\.text).joined(separator: "\n")
        } catch {
            guard request == workSessionsRequest, id == selectedID else { return }
            workSessions = []; workSessionsWarning = error.localizedDescription
        }
    }

    var workSessionNoticeToShow: NativeWorkSession? {
        workSessions.first { $0.needsReview && UUID(uuidString: $0.value["conversation_id"].text) == selectedID && !isWorkSessionWarningHidden($0) }
    }

    var hasWorkSessionNotice: Bool { workSessionsWarning != nil || workSessionNoticeToShow != nil }

    func isWorkSessionWarningHidden(_ run: NativeWorkSession) -> Bool {
        guard run.needsReview, UUID(uuidString: run.value["conversation_id"].text) == selectedID else { return false }
        return selected?.dismissedWorkSessionWarnings.contains { $0.matches(run) } == true
    }

    func openWorkSessions(_ run: NativeWorkSession? = nil) {
        inspectedWorkSessionID = run?.id
        showWorkSessions = true
    }

    func setWorkSessionWarningHidden(_ run: NativeWorkSession, hidden: Bool) throws {
        guard !busy, !client.turnOutstanding, !loadingWorkSessions,
              let index = conversations.firstIndex(where: { $0.id == selectedID }),
              UUID(uuidString: run.value["conversation_id"].text) == selectedID,
              let current = workSessions.first(where: { $0.id == run.id }), current.reference == run.reference,
              current.state == run.state, current.needsReview else {
            throw NativeError.message("Запуск изменился или работа ещё идёт. Обновите журнал; уведомление не скрыто.")
        }
        let notice = try NativeWorkSessionNotice(current)
        let previous = conversations[index].dismissedWorkSessionWarnings
        if hidden && previous.contains(notice) { return }
        var next = previous.filter { $0.runID != notice.runID }
        if hidden { next.append(notice) }
        try NativeWorkSessionNotice.validate(next)
        guard next != previous else { return }
        conversations[index].dismissedWorkSessionWarnings = next
        do {
            try store.save(ChatArchive(conversations: conversations, selectedID: selectedID))
            draftSave?.cancel(); dirtyDraft = false
        } catch {
            conversations[index].dismissedWorkSessionWarnings = previous
            throw error
        }
    }

    func prepareContinuation(_ run: NativeWorkSession) async {
        workSessionsActionError = nil
        guard !busy, run.canPrepare, let id = selectedID, UUID(uuidString: run.value["conversation_id"].text) == id,
              selected?.archived != true else { return }
        guard composer.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty, selected?.pendingFiles.isEmpty == true,
              selected?.pendingImages.isEmpty == true, selected?.pendingPDFs.isEmpty == true else {
            workSessionsActionError = "Сначала сохраните или очистите текущий черновик и вложения. Продолжение не заменит их автоматически."
            report(NativeError.message(workSessionsActionError!)); return
        }
        busy = true
        defer { busy = false }
        do {
            var params: [String: JSONValue] = ["conversation_id": .string(id.uuidString), "continuation": run.reference]
            if let root = selected?.workspacePath { params["workspace_root"] = .string(root) }
            let result = try await client.request("work_session_continuation", params)
            guard result["schema"].text == "proto_mind.native_continuation.v1", result["read_only"] == .bool(true),
                  result["automatic_resume"] == .bool(false), result["run_id"].text == run.id,
                  result["fingerprint"] == run.value["fingerprint"], !result["draft"].text.isEmpty,
                  result["draft"].text.count <= 5000,
                  let index = conversations.firstIndex(where: { $0.id == id }) else {
                throw NativeError.message("Черновик продолжения не прошёл проверку. Ничего не отправлено.")
            }
            conversations[index].draftContinuation = run.reference
            setComposer(result["draft"].text, preservingContinuation: true)
            flushDraft(); section = .chat; showWorkSessions = false
            status = "Черновик подготовлен · проверьте и отправьте вручную"
        } catch { workSessionsActionError = error.localizedDescription; report(error) }
    }

    func clearContinuation() {
        guard !busy, let index = conversations.firstIndex(where: { $0.id == selectedID }) else { return }
        conversations[index].draftContinuation = nil
        persist()
    }

    func newConversation() {
        guard !busy else { return }
        closeLearningReview()
        memoryWorkshop = nil; showMemoryWorkshop = false
        skillAuthoring = nil
        skillInspection?.close()
        skillOutcome?.close()
        skillDecision?.close()
        skillLifecycleApply?.close()
        skillRestore?.close()
        skillHistory?.close()
        projectMemory?.close()
        memorySuggestion?.close()
        skillTask?.close()
        flushDraft()
        let chat = Conversation()
        conversations.insert(chat, at: 0)
        selectedID = chat.id
        workSessions = []; workSessionsWarning = nil
        codexThreadStatus = .null
        modelSelectionNotice = nil
        inspectedMessageID = nil
        restoreComposer()
        showArchived = false
        conversationSearch = ""
        resetWorkspaceView()
        section = .chat
        persist()
    }

    func select(_ id: UUID) {
        guard !busy else { return }
        closeLearningReview()
        memoryWorkshop = nil; showMemoryWorkshop = false
        skillAuthoring = nil
        skillInspection?.close()
        skillOutcome?.close()
        skillDecision?.close()
        skillLifecycleApply?.close()
        skillRestore?.close()
        skillHistory?.close()
        projectMemory?.close()
        memorySuggestion?.close()
        skillTask?.close()
        flushDraft()
        selectedID = id; section = .chat; inspectedMessageID = nil
        modelSelectionNotice = nil
        codexThreadStatus = .null
        restoreComposer(); resetWorkspaceView(); persist()
        workSessions = []; workSessionsWarning = nil
        Task {
            await refreshWorkSessions()
            await refreshCodexThreadStatus()
        }
    }

    func setAutoSkillsEnabled(_ enabled: Bool) {
        guard !busy, let index = conversations.firstIndex(where: { $0.id == selectedID }), !conversations[index].archived else { return }
        conversations[index].autoSkillsEnabled = enabled
        invalidateContextPreview(); persist()
    }

    func setAutoProjectRecallEnabled(_ enabled: Bool) {
        guard !busy, let index = conversations.firstIndex(where: { $0.id == selectedID }), !conversations[index].archived else { return }
        conversations[index].autoProjectRecallEnabled = enabled
        invalidateContextPreview(); persist()
    }

    func setMemorySuggestionsEnabled(_ enabled: Bool) {
        guard !busy, let index = conversations.firstIndex(where: { $0.id == selectedID }), !conversations[index].archived else { return }
        conversations[index].memorySuggestionsEnabled = enabled; persist()
    }

    func setProvider(_ value: String) {
        guard !busy, ["ollama", "codex", "mock"].contains(value), selected?.provider != value,
              let index = conversations.firstIndex(where: { $0.id == selectedID }) else { return }
        discardAgentGrants(for: selectedID)
        pendingPersonaActivation = nil
        conversations[index].provider = value
        conversations[index].model = ""
        conversations[index].reasoningEffort = ""
        modelSelectionNotice = nil
        codexThreadStatus = .null
        persist()
    }

    func setModel(_ value: String) {
        guard !busy, let index = conversations.firstIndex(where: { $0.id == selectedID }) else { return }
        if selected?.provider == "codex", !value.isEmpty, !codexModels.contains(where: { $0.id == value }) { return }
        conversations[index].model = value
        pendingPersonaActivation = nil
        modelSelectionNotice = nil
        if selected?.provider == "codex", !conversations[index].reasoningEffort.isEmpty,
           !availableReasoningEfforts.contains(where: { $0.rawValue == conversations[index].reasoningEffort }) {
            conversations[index].reasoningEffort = ""
            modelSelectionNotice = "Предыдущее усилие недоступно для этой модели. Выбрано значение по умолчанию."
        }
        persist()
    }

    var codexModels: [CodexModelOption] {
        var seen = Set<String>()
        return models.compactMap(CodexModelOption.init).filter { seen.insert($0.id).inserted }
    }

    var selectedCodexModel: CodexModelOption? {
        let identifier = selected?.model ?? ""
        return identifier.isEmpty ? codexModels.first(where: \.isDefault) : codexModels.first { $0.id == identifier }
    }

    var availableReasoningEfforts: [CodexReasoningEffort] { selectedCodexModel?.efforts ?? [] }

    var reasoningEffortLabel: String {
        let value = selected?.reasoningEffort ?? ""
        if value.isEmpty { return selectedCodexModel?.defaultEffort?.title ?? "Авто" }
        return CodexReasoningEffort(rawValue: value)?.title ?? value
    }

    var codexModelLabel: String {
        selectedCodexModel?.displayName ?? ((selected?.model.isEmpty ?? true) ? "Codex" : selected!.model)
    }

    var modelSelectionWarning: String? {
        guard selected?.provider == "codex", !models.isEmpty else { return nil }
        if !(selected?.model.isEmpty ?? true), selectedCodexModel == nil {
            return "Сохранённая модель недоступна в текущем каталоге. Выберите другую: автоматической подмены не будет."
        }
        if let effort = selected?.reasoningEffort, !effort.isEmpty,
           !availableReasoningEfforts.contains(where: { $0.rawValue == effort }) {
            return "Сохранённое усилие больше не поддерживается. Выберите доступное или сбросьте настройки."
        }
        return nil
    }

    func setReasoningEffort(_ value: String) {
        guard !busy, selected?.provider == "codex", let index = conversations.firstIndex(where: { $0.id == selectedID }),
              value.isEmpty || availableReasoningEfforts.contains(where: { $0.rawValue == value }) else { return }
        conversations[index].reasoningEffort = value
        modelSelectionNotice = nil
        persist()
    }

    func resetCodexSelection() {
        guard !busy, selected?.provider == "codex", let index = conversations.firstIndex(where: { $0.id == selectedID }) else { return }
        conversations[index].model = ""
        conversations[index].reasoningEffort = ""
        modelSelectionNotice = nil
        persist()
    }

    var codexThreadLabel: String {
        guard selected?.provider == "codex" else { return "Codex не выбран" }
        guard !codexThreadStatus.isNull else { return "Статус не проверен" }
        guard codexThreadStatus["workspace_matches"].flag else { return "Нужна новая сессия" }
        if codexThreadStatus["refresh_required"].flag { return "Обновление инструкций при следующем сообщении" }
        guard codexThreadStatus["linked"].flag else { return "Новая сессия при следующем сообщении" }
        let short = codexThreadStatus["thread_id_short"].text
        return short.isEmpty ? "Продолжение сохранённой сессии" : "Продолжение · \(short)"
    }

    func refreshCodexThreadStatus() async {
        guard !busy, let conversation = selected, conversation.provider == "codex" else {
            codexThreadStatus = .null
            return
        }
        let id = conversation.id
        let workspace = conversation.workspacePath
        loadingCodexThreadStatus = true
        defer { if selectedID == id { loadingCodexThreadStatus = false } }
        do {
            var params: [String: JSONValue] = ["conversation_id": .string(id.uuidString)]
            if let workspace { params["workspace_root"] = .string(workspace) }
            let value = try await client.request("codex_thread_status", params)
            guard selectedID == id, selected?.workspacePath == workspace, selected?.provider == "codex" else { return }
            guard value["schema"].text == "proto_mind.native_codex_threads.v1",
                  !value["linked"].isNull, !value["workspace_matches"].isNull else {
                throw NativeError.message("Не удалось проверить локальную связь с сессией Codex.")
            }
            codexThreadStatus = value
        } catch {
            guard selectedID == id else { return }
            codexThreadStatus = .null
            report(error)
        }
    }

    func resetCodexThread() async {
        guard !busy, !client.turnOutstanding, let id = selectedID, selected?.provider == "codex" else { return }
        discardAgentGrants(for: id)
        do {
            let value = try await client.request("codex_thread_reset", [
                "conversation_id": .string(id.uuidString),
                "confirmation": .string("START NEW CODEX SESSION"),
            ])
            guard value["schema"].text == "proto_mind.native_codex_thread_reset.v1",
                  value["no_provider_call"].flag, value["provider_history_deleted"] == .bool(false) else {
                throw NativeError.message("Сброс сессии Codex не прошёл локальную проверку.")
            }
            modelSelectionNotice = value["notice"].text
            codexThreadStatus = .null
            await refreshCodexThreadStatus()
        } catch { report(error) }
    }

    func setComposer(_ value: String, preservingContinuation: Bool = false) {
        if !preservingContinuation, let index = conversations.firstIndex(where: { $0.id == selectedID }) {
            conversations[index].draftContinuation = nil
        }
        composer = value
        composerRevision += 1
    }

    func renameConversation(_ id: UUID, title: String) {
        guard !busy, let index = conversations.firstIndex(where: { $0.id == id }) else { return }
        let name = title.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !name.isEmpty, name.count <= 120 else { report(NativeError.message("Название должно содержать от 1 до 120 символов.")); return }
        conversations[index].title = name
        persist()
    }

    func archiveConversation(_ id: UUID, archived: Bool) {
        guard !busy, let index = conversations.firstIndex(where: { $0.id == id }) else { return }
        conversations[index].archived = archived
        if archived && selectedID == id {
            if let next = conversations.first(where: { !$0.archived }) { select(next.id) }
            else { newConversation() }
        } else if !archived && selectedID == id {
            showArchived = false
        }
        persist()
    }

    private func restoreComposer() {
        restoringDraft = true
        composer = selected?.draft ?? ""
        composerRevision += 1
        restoringDraft = false
    }

    private func draftChanged() {
        guard !initializing, !restoringDraft, let index = conversations.firstIndex(where: { $0.id == selectedID }) else { return }
        conversations[index].draft = composer
        if composer.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty { conversations[index].draftContinuation = nil }
        dirtyDraft = true
        draftSave?.cancel()
        draftSave = Task { [weak self] in
            do { try await Task.sleep(nanoseconds: 500_000_000) }
            catch { return }
            self?.flushDraft()
        }
    }

    func flushDraft() { if dirtyDraft { persist() } }

    func submit(_ supplied: String? = nil) async {
        let text = (supplied ?? composer).trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty, !busy, !loadingDroppedAttachments, !loadingImagePreview, !loadingPDFPreview,
              imagePreview == nil, pdfPreview == nil, attachmentDropPreview == nil,
              selected?.archived != true, let conversationID = selectedID else { return }
        busy = true
        do {
            let description = try await client.request("describe", ["text": .string(text)])
            guard !description["blocked"].flag else { throw NativeError.message(description["notice"].text) }
            if description["requires_confirmation"].flag {
                let summary = description["steps"].items.map { "\($0["command"].text)\nИзменяет: \($0["mutates"].text) · риск: \($0["risk"].text)" }.joined(separator: "\n\n")
                pendingAction = PendingOperatorAction(text: text, conversationID: conversationID, summary: summary)
                busy = false
                return
            }
            await perform(text, conversationID: conversationID, confirmed: false, operatorInput: description["operator"].flag)
        } catch { busy = false; report(error) }
    }

    func confirmPending() async {
        guard let action = pendingAction else { return }
        pendingAction = nil
        busy = true
        await perform(action.text, conversationID: action.conversationID, confirmed: true, operatorInput: true)
    }

    private func perform(_ text: String, conversationID: UUID, confirmed: Bool, operatorInput: Bool) async {
        guard let index = conversations.firstIndex(where: { $0.id == conversationID }) else { busy = false; return }
        let conversation = conversations[index]
        let history = conversation.history
        let files = operatorInput ? [] : conversation.pendingFiles
        let images = operatorInput ? [] : conversation.pendingImages
        let pdfs = operatorInput ? [] : conversation.pendingPDFs
        let criteria = operatorInput ? [] : conversation.pendingCriteria
        let projectNotes = operatorInput ? [] : projectNoteSelections[conversationID] ?? []
        let skillTask = operatorInput ? nil : preparedSkillTasks[conversationID]
        let automaticSkills = !operatorInput && conversation.provider == "codex" && conversation.autoSkillsEnabled && skillTask == nil
        let automaticRecall = !operatorInput && conversation.provider == "codex" && conversation.autoProjectRecallEnabled && projectNotes.isEmpty
        let suggestMemory = !operatorInput && conversation.provider == "codex" && conversation.memorySuggestionsEnabled && conversation.workspacePath != nil
        let grant = !operatorInput && fullAccessEnabled ? agentGrants[conversationID] : nil
        let reviewedRecall = contextPreview.flatMap { try? NativeProjectRecallReport($0.manifest["knowledge_context"]["project_recall"]) }
        let expectedProjectSnapshot = automaticRecall && reviewedRecall?.matches(conversation: conversationID, text: text,
            workspace: conversation.workspacePath, mode: grant == nil ? "chat" : "full_access") == true
            ? reviewedRecall?.value["source_snapshot_hash"] : nil
        let continuation = operatorInput ? nil : conversation.draftContinuation
        let userMessage = ChatMessage(role: "user", text: text, operatorInput: operatorInput, fileContext: files, imageContext: images, pdfContext: pdfs)
        conversations[index].messages.append(userMessage)
        if conversations[index].title == "Новый диалог" {
            conversations[index].title = String(text.split(whereSeparator: \.isWhitespace).joined(separator: " ").prefix(54))
        }
        conversations[index].updatedAt = Date()
        setComposer(""); stream = ""; agentItems = []; agentReceipt = .null; workLog = .null; autoSkillsReport = nil
        turnStartedAt = Date(); section = .chat
        status = grant == nil ? "Proto-Mind думает" : "Агент подключается · полный доступ + интернет"
        persist()
        do {
            var params: [String: JSONValue] = [
                "text": .string(text), "conversation_id": .string(conversationID.uuidString),
                "provider": .string(conversation.provider), "model": .string(conversation.model),
                "reasoning_effort": .string(conversation.provider == "codex" ? conversation.reasoningEffort : ""),
                "cloud_consent": .bool(cloudConsent), "history": .array(history),
                "persona_enabled": .bool(!operatorInput && personaEnabled),
            ]
            if confirmed { params["confirmed_text"] = .string(text) }
            if !operatorInput {
                params["run_id"] = .string(UUID().uuidString)
                params["criteria"] = .array(criteria.map(JSONValue.string))
                params["images"] = .array(images)
                params["pdfs"] = .array(pdfs)
                params["project_memory"] = .array(projectNotes.map(\.selection))
                params["auto_skills"] = .bool(automaticSkills)
                params["auto_project_recall"] = .bool(automaticRecall)
                params["memory_suggestions"] = .bool(suggestMemory)
                if let expectedProjectSnapshot, !expectedProjectSnapshot.isNull { params["expected_project_snapshot"] = expectedProjectSnapshot }
                if let skillTask { params["skill_task"] = skillTask.selection }
                if let root = conversation.workspacePath { params["workspace_root"] = .string(root) }
                if let continuation { params["continuation"] = continuation }
            }
            if let grant {
                params["access_mode"] = .string("full_access")
                params["access_token"] = .string(grant.token)
                params["workspace_root"] = .string(grant.workspace)
            }
            if !files.isEmpty, let root = conversation.workspacePath {
                params["workspace_root"] = .string(root)
                params["files"] = .array(files)
            }
            let result = try await client.request("process", params, onID: { self.activeRequest = $0 })
            if !operatorInput && personaEnabled {
                lastPersonaTurnReceipt = try NativePersonaTurnReceipt(result["persona_activation"])
            } else if !result["persona_activation"].isNull {
                throw NativeError.message("Ядро вернуло Persona receipt без активированного opt-in.")
            }
            let evidence = result["cognitive_turn"]
            try checkKnowledgeMetadata(result["knowledge_context"])
            let returnedNotes = result["knowledge_context"]["project_memory"].items
            if automaticRecall {
                let report = try NativeProjectRecallReport(result["knowledge_context"]["project_recall"], notes: returnedNotes, run: result["work_session"])
                guard report.matches(conversation: conversationID, text: text, workspace: conversation.workspacePath,
                                     mode: grant == nil ? "chat" : "full_access"),
                      expectedProjectSnapshot == nil || expectedProjectSnapshot?.isNull == true || report.value["source_snapshot_hash"] == expectedProjectSnapshot,
                      result["knowledge_context"] == result["work_session"]["context_manifest"]["knowledge_context"] else { throw NativeProjectRecallReport.error() }
            } else {
                guard result["knowledge_context"]["project_recall"].isNull,
                      returnedNotes.count == projectNotes.count, zip(returnedNotes, projectNotes).allSatisfy({ row, note in
                    row["id"] == note.raw["id"] && row["record_hash"] == note.raw["record_hash"]
                }) else { throw projectMemoryError() }
            }
            guard result["knowledge_context"]["skill_task"] == (skillTask?.reference ?? .null) else { throw skillTaskError() }
            if automaticSkills {
                let report = try NativeAutoSkillsReport(result["auto_skills"], run: result["work_session"])
                guard ["selected", "no_match", "empty", "unavailable"].contains(report.state),
                      report.matches(conversation: conversationID, text: text, workspace: conversation.workspacePath,
                                     mode: grant == nil ? "chat" : "full_access") else { throw NativeAutoSkillsReport.error() }
                autoSkillsReport = report
            } else if !result["auto_skills"].isNull { throw NativeAutoSkillsReport.error() }
            let raw = result["text"].text
            let body = result["exit_requested"].flag ? "Сессия ядра завершена. История диалога сохранена локально." : evidence.isNull ? raw : evidence["response"].text
            var notices = result["notices"].items.map(\.text)
            var suggestions: JSONValue?
            if !result["memory_suggestions"].isNull {
                do {
                    guard suggestMemory else { throw memorySuggestionError() }
                    let report = try MemorySuggestionsReport(result["memory_suggestions"], text: text, run: result["work_session"])
                    guard UUID(uuidString: report.source["conversation_id"].text) == conversationID,
                          ProjectMemoryScope(conversationID: conversationID, workspace: conversation.workspacePath ?? "").matches(report.source["workspace"]) else { throw memorySuggestionError() }
                    if report.value["state"] == .string("unavailable") { notices.append("Предложения памяти недоступны: проверьте папку, настройки и заметки. Ответ сохранён; автоматической записи памяти не было.") }
                    if !report.items.isEmpty { suggestions = report.value }
                } catch { notices.append("Предложения памяти не прошли проверку источника. Ответ сохранён без карточек; ничего не записано в заметки проекта.") }
            }
            if !result["envelope_warning"].text.isEmpty { notices.append(result["envelope_warning"].text) }
            try NativeImageAttachment.validate(result["image_context"].items)
            guard images.isEmpty || result["image_context"] == .array(images) else {
                throw NativeError.message("Результат не подтвердил выбранные изображения. Запрос не повторялся; проверьте журнал работы.")
            }
            try NativePDFAttachment.validate(result["pdf_context"].items)
            guard pdfs.isEmpty || result["pdf_context"] == .array(pdfs) else {
                throw NativeError.message("Результат не подтвердил выбранные страницы PDF. Запрос не повторялся; проверьте журнал работы.")
            }
            let message = ChatMessage(role: result["operator"].flag ? "report" : "assistant", text: body,
                                      raw: raw, evidence: evidence, notices: notices,
                                      fileContext: result["workspace_context"].items,
                                      imageContext: result["image_context"].items,
                                      pdfContext: result["pdf_context"].items,
                                      agentRun: result["agent_run"].isNull ? nil : result["agent_run"],
                                      workLog: result["work_log"].isNull ? nil : result["work_log"],
                                      autoSkills: autoSkillsReport?.value,
                                      knowledgeContext: result["knowledge_context"].isNull ? nil : result["knowledge_context"],
                                      memorySuggestions: suggestions, memorySuggestionSourceID: suggestions == nil ? nil : userMessage.id)
            append(message, to: conversationID)
            if !operatorInput, let current = conversations.firstIndex(where: { $0.id == conversationID }) {
                conversations[current].pendingFiles = []
                conversations[current].pendingImages = []
                conversations[current].pendingPDFs = []
                conversations[current].pendingCriteria = []
                projectNoteSelections[conversationID] = nil
                preparedSkillTasks[conversationID] = nil
            }
            inspectedMessageID = message.id
            if !result["provider_thread"].isNull { codexThreadStatus = .null }
            status = "Готов"
        } catch {
            if let current = conversations.firstIndex(where: { $0.id == conversationID }),
               let failed = conversations[current].messages.firstIndex(where: { $0.id == userMessage.id }) {
                conversations[current].messages[failed].isError = true
            }
            let caution = grant == nil ? "" : "\nДействия могли уже изменить файлы. Проверьте журнал и результат перед повтором; автоматического отката нет."
            append(ChatMessage(role: "report", text: error.localizedDescription + caution, isError: true,
                               agentRun: agentReceipt.isNull ? nil : agentReceipt,
                               workLog: workLog.isNull ? nil : workLog, autoSkills: autoSkillsReport?.value), to: conversationID)
            if grant != nil { discardAgentGrants(for: conversationID) }
            if selectedID == conversationID && composer.isEmpty {
                if let current = conversations.firstIndex(where: { $0.id == conversationID }) {
                    conversations[current].draftContinuation = continuation
                }
                setComposer(text, preservingContinuation: true)
            }
            status = "Запрос не завершён"
        }
        busy = false; stream = ""; activeRequest = nil; agentItems = []; agentReceipt = .null; workLog = .null; turnStartedAt = nil; autoSkillsReport = nil
        persist()
        await refreshCodexThreadStatus()
        await refresh()
    }

    func stop() async {
        guard let request = activeRequest else { return }
        do { status = try await client.request("cancel", ["request_id": .string(request)])["notice"].text }
        catch { report(error) }
    }

    func login() async {
        guard !busy, !connecting else { return }
        connecting = true
        defer { connecting = false }
        do {
            let result = try await client.request("account_login")
            guard let url = URL(string: result["url"].text), url.scheme == "https",
                  ["auth.openai.com", "chatgpt.com", "openai.com"].contains(url.host ?? "") else {
                throw NativeError.message("Неожиданный адрес входа; браузер не открыт.")
            }
            loginPending = true
            NSWorkspace.shared.open(url)
        } catch { report(error) }
    }

    func refreshAccount() async {
        guard !busy, !connecting else { return }
        connecting = true
        defer { connecting = false }
        do {
            account = try await client.request("account_status")
            if account["connected"].flag {
                loginPending = false
                models = try await client.request("models")["models"].items
            } else { models = [] }
        } catch { report(error) }
    }

    func logout() async {
        guard !busy else { return }
        do { account = try await client.request("account_logout"); models = []; cloudConsent = false; loginPending = false }
        catch { report(error) }
    }

    func showMessage(_ message: ChatMessage) { inspectedMessageID = message.id; showInspector = true }

    func checkOllama() async {
        guard !busy else { return }
        do { ollamaStatus = try await client.request("ollama_status") }
        catch { report(error) }
    }

    func chooseWorkspace() {
        guard !busy else { return }
        let panel = NSOpenPanel()
        panel.canChooseDirectories = true; panel.canChooseFiles = false; panel.allowsMultipleSelection = false
        panel.prompt = "Подключить только для чтения"
        panel.directoryURL = selected?.workspacePath.map { URL(fileURLWithPath: $0) } ?? client.configuration.projectRoot
        if panel.runModal() == .OK, let url = panel.url { Task { await bindWorkspace(url.path) } }
    }

    func bindWorkspace(_ path: String) async {
        guard !busy, !loadingWorkspace, let id = selectedID else { return }
        loadingWorkspace = true; workspaceError = nil
        defer { loadingWorkspace = false }
        do {
            let value = try await client.request("workspace_status", ["workspace_root": .string(path)])
            guard let index = conversations.firstIndex(where: { $0.id == id }) else { return }
            conversations[index].workspacePath = value["root"].text
            projectNoteSelections[id] = nil; projectMemory = nil; memorySuggestion = nil; invalidateContextPreview()
            preparedSkillTasks[id] = nil; skillTask = nil
            closeLearningReview()
            memoryWorkshop = nil
            discardAgentGrants(for: id)
            conversations[index].pendingFiles = []
            persist()
            if selectedID == id {
                resetWorkspaceView(); workspaceStatus = value; section = .workspace
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
        guard !busy, !loadingWorkspace, let root = selected?.workspacePath, let id = selectedID else { return }
        loadingWorkspace = true; workspaceError = nil
        defer { loadingWorkspace = false }
        do {
            let status = try await client.request("workspace_status", ["workspace_root": .string(root)])
            let listing = try await client.request("workspace_list", ["workspace_root": .string(root), "path": .string(path)])
            if selectedID == id { workspaceStatus = status; workspaceListing = listing; filePreview = .null }
        } catch { workspaceError = error.localizedDescription }
    }

    func openWorkspaceEntry(_ entry: JSONValue) async {
        if entry["directory"].flag { await refreshWorkspace(entry["path"].text); return }
        guard !busy, !loadingWorkspace, let root = selected?.workspacePath, let id = selectedID else { return }
        loadingWorkspace = true; workspaceError = nil
        defer { loadingWorkspace = false }
        do {
            let preview = try await client.request("workspace_read", ["workspace_root": .string(root), "path": entry["path"]])
            if selectedID == id { filePreview = preview }
        } catch { workspaceError = error.localizedDescription }
    }

    func attachPreview() {
        guard !busy, !filePreview.isNull, let index = conversations.firstIndex(where: { $0.id == selectedID }) else { return }
        let path = filePreview["path"].text
        let existing = conversations[index].pendingFiles.firstIndex { $0["path"].text == path }
        guard existing != nil || conversations[index].pendingFiles.count < 3 else {
            workspaceError = "К одному сообщению можно выбрать до трёх файлов."; return
        }
        let count = min(6000, filePreview["characters"].integer)
        let item: JSONValue = .object(["path": .string(path), "sha256": filePreview["sha256"],
                                       "included_chars": .number(Double(count)), "truncated": .bool(filePreview["characters"].integer > count)])
        if let existing { conversations[index].pendingFiles[existing] = item }
        else { conversations[index].pendingFiles.append(item) }
        persist(); section = .chat
    }

    func removePendingFile(_ path: String) {
        guard !busy, let index = conversations.firstIndex(where: { $0.id == selectedID }) else { return }
        conversations[index].pendingFiles.removeAll { $0["path"].text == path }
        persist()
    }

    var imageDestinationNotice: String {
        guard selected?.provider == "codex" else {
            return "Изображения пока поддерживаются только через Codex. Выбор локальный; Ollama/Mock не получат эти файлы. Провайдер не меняется автоматически."
        }
        guard cloudConsent else {
            return "Сейчас всё остаётся на Mac. Для отправки изображений в OpenAI разрешите облачную обработку; выбор файла сам по себе её не включает."
        }
        let selectedModel = models.first { selected?.model.isEmpty == false ? $0["id"].text == selected?.model : $0["default"].flag }
        guard selectedModel?["input_modalities"].items.contains(.string("image")) == true else {
            return "Каталог пока не подтверждает изображения для выбранной модели. Обновите модели или выберите совместимую; Send повторно проверит поддержку."
        }
        return "После «Отправить» выбранные изображения уйдут в OpenAI вместе с сообщением. До этого просмотр локальный. В следующих запросах они не пересылаются автоматически."
    }

    func chooseImage() {
        guard canReceiveAttachments, let conversationID = selectedID else { return }
        let panel = NSOpenPanel()
        panel.canChooseDirectories = false; panel.canChooseFiles = true; panel.allowsMultipleSelection = false
        panel.allowedContentTypes = [.png, .jpeg]; panel.resolvesAliases = false
        panel.prompt = "Просмотреть локально"
        panel.message = "Выберите PNG/JPEG до 4 МиБ. Этот шаг ничего не отправляет в модель."
        let completion: (NSApplication.ModalResponse) -> Void = { [weak self] response in
            guard response == .OK, let url = panel.url, let self, self.selectedID == conversationID else { return }
            Task { await self.previewImage(url.path) }
        }
        if let window = NSApp.keyWindow { panel.beginSheetModal(for: window, completionHandler: completion) }
        else { panel.begin(completionHandler: completion) }
    }

    func previewImage(_ path: String, expectedSHA: String? = nil, canAttach: Bool = true) async {
        guard !busy, !loadingImagePreview, !loadingDroppedAttachments, !loadingPDFPreview,
              pdfPreview == nil, attachmentDropPreview == nil,
              let conversationID = selectedID else { return }
        loadingImagePreview = true
        defer { loadingImagePreview = false }
        do {
            var params: [String: JSONValue] = ["path": .string(path)]
            if let expectedSHA { params["expected_sha256"] = .string(expectedSHA) }
            let result = try await client.request("image_preview", params)
            guard selectedID == conversationID, !busy else { return }
            let preview = try NativeImagePreview(result, conversationID: conversationID, canAttach: canAttach)
            guard preview.source.path == path, expectedSHA == nil || preview.source.sha256 == expectedSHA else {
                throw NativeError.message("Предпросмотр относится к другому изображению. Ничего не прикреплено.")
            }
            if imageThumbnails.count >= 12 { imageThumbnails.removeAll() }
            imageThumbnails[preview.source.sha256] = preview.thumbnail
            imagePreview = preview
        } catch { report(error) }
    }

    func attachImage(_ preview: NativeImagePreview) throws {
        guard preview.canAttach, !busy, selectedID == preview.conversationID, selected?.archived != true,
              let index = conversations.firstIndex(where: { $0.id == preview.conversationID }) else {
            throw NativeError.message("Диалог изменился или занят. Изображение не прикреплено.")
        }
        var next = conversations[index].pendingImages.filter { $0["path"].text != preview.source.path }
        next.append(preview.source.value)
        try updatePendingImages(next, index: index)
        section = .chat
    }

    func removePendingImage(_ path: String) {
        guard !busy, let index = conversations.firstIndex(where: { $0.id == selectedID }) else { return }
        do { try updatePendingImages(conversations[index].pendingImages.filter { $0["path"].text != path }, index: index) }
        catch { report(error) }
    }

    private func updatePendingImages(_ next: [JSONValue], index: Int) throws {
        try NativeImageAttachment.validate(next)
        let previous = conversations[index].pendingImages
        conversations[index].pendingImages = next
        do {
            try store.save(ChatArchive(conversations: conversations, selectedID: selectedID))
            draftSave?.cancel(); dirtyDraft = false
        } catch {
            conversations[index].pendingImages = previous
            throw error
        }
    }

    var canReceiveAttachments: Bool {
        selected != nil && selected?.archived != true && !busy && !client.turnOutstanding
            && !loadingDroppedAttachments && !loadingImagePreview && !loadingPDFPreview
            && imagePreview == nil && pdfPreview == nil && attachmentDropPreview == nil
            && pendingAction == nil && pendingAgentAccess == nil
    }

    func receiveAttachmentDrop(_ providers: [NSItemProvider]) -> Bool {
        guard canReceiveAttachments, let conversation = selected else { return false }
        guard (1...NativeAttachmentDrop.maximumItems).contains(providers.count),
              providers.allSatisfy({ $0.hasItemConformingToTypeIdentifier(UTType.fileURL.identifier) }) else {
            error = "Перетащите до 6 локальных файлов. Черновик не изменён."; return false
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
                guard urls.count == 1 else { throw NativeError.message("Перетащите один PDF отдельно, чтобы выбрать страницы. Остальные файлы добавьте следующим действием; черновик не изменён.") }
                pdfPreview = try await readPDFPreview(urls[0].path, pages: [1], conversation: conversation, canAttach: true)
                return
            }
            guard urls.filter(NativeAttachmentDrop.isImage).count <= 3,
                  urls.filter({ !NativeAttachmentDrop.isImage($0) }).count <= 3 else {
                throw NativeError.message("Допускается до 3 изображений и 3 текстовых файлов. Черновик не изменён.")
            }
            var images: [NativeImagePreview] = [], files: [NativeDroppedFile] = []
            for url in urls {
                guard selectedID == conversation.id, selected?.workspacePath == conversation.workspacePath, !busy else { return }
                if NativeAttachmentDrop.isImage(url) {
                    let value = try await client.request("image_preview", ["path": .string(url.path)])
                    let preview = try NativeImagePreview(value, conversationID: conversation.id, canAttach: true)
                    guard preview.source.path == url.path else { throw NativeError.message("Предпросмотр относится к другому изображению.") }
                    images.append(preview)
                } else {
                    let path = try NativeAttachmentDrop.relativePath(url, workspace: conversation.workspacePath)
                    let value = try await client.request("workspace_read", ["workspace_root": .string(conversation.workspacePath ?? ""), "path": .string(path)])
                    files.append(try NativeDroppedFile(value, path: path))
                }
            }
            guard selectedID == conversation.id, let current = selected, !busy else { return }
            let preview = NativeAttachmentDropPreview(conversationID: conversation.id, workspace: conversation.workspacePath, images: images, files: files)
            _ = try preview.merged(with: current)
            attachmentDropPreview = preview
        } catch {
            if selectedID == conversation.id { report(error) }
        }
    }

    func attachDrop(_ preview: NativeAttachmentDropPreview) throws {
        guard !busy, !loadingDroppedAttachments, selectedID == preview.conversationID,
              let index = conversations.firstIndex(where: { $0.id == preview.conversationID }) else {
            throw NativeError.message("Диалог изменился или занят. Файлы не прикреплены.")
        }
        let previous = conversations[index]
        let next = try preview.merged(with: previous)
        conversations[index].pendingImages = next.images
        conversations[index].pendingFiles = next.files
        do {
            try store.save(ChatArchive(conversations: conversations, selectedID: selectedID))
            draftSave?.cancel(); dirtyDraft = false
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
                ? "Только после «Отправить» выбранный текст страниц уйдёт в OpenAI. Оригинал PDF не пересылается и не копируется. В истории сохраняются лишь метаданные вложения."
                : "Просмотр локальный. Для отправки текста PDF в Codex нужно облачное разрешение. Выбор PDF его не включает и ничего не отправляет."
        }
        return selected?.provider == "mock"
            ? "Mock проверяет интерфейс, но не анализирует PDF. Оригинал и текст остаются локально; провайдер не меняется автоматически."
            : "После «Отправить» выбранный текст страниц получит локальная Ollama. Оригинал PDF не пересылается и не копируется."
    }

    func choosePDF() {
        guard canReceiveAttachments, let conversationID = selectedID else { return }
        let panel = NSOpenPanel()
        panel.canChooseDirectories = false; panel.canChooseFiles = true; panel.allowsMultipleSelection = false
        panel.allowedContentTypes = [.pdf]; panel.resolvesAliases = false
        panel.prompt = "Выбрать страницы"
        panel.message = "PDF с текстовым слоем до 8 МиБ. Локальный просмотр, без отправки."
        let completion: (NSApplication.ModalResponse) -> Void = { [weak self] response in
            guard response == .OK, let url = panel.url, let self, self.selectedID == conversationID else { return }
            Task { await self.previewPDF(url.path) }
        }
        if let window = NSApp.keyWindow { panel.beginSheetModal(for: window, completionHandler: completion) }
        else { panel.begin(completionHandler: completion) }
    }

    private func readPDFPreview(_ path: String, pages: [Int], conversation: Conversation,
                                canAttach: Bool, expectedSHA: String? = nil) async throws -> NativePDFPreview {
        let path = try NativeAttachmentDrop.localURL(URL(fileURLWithPath: path)).path
        var params: [String: JSONValue] = ["path": .string(path), "pages": .array(pages.map { .number(Double($0)) })]
        if let expectedSHA { params["expected_sha256"] = .string(expectedSHA) }
        let result = try await client.request("pdf_preview", params)
        guard !busy, !client.turnOutstanding, selectedID == conversation.id,
              selected?.workspacePath == conversation.workspacePath, selected?.archived != true else {
            throw NativeError.message("Диалог изменился или занят. PDF не прикреплён и не отправлен.")
        }
        let preview = try NativePDFPreview(result, conversationID: conversation.id, workspace: conversation.workspacePath, canAttach: canAttach)
        guard preview.source.path == path, preview.source.pages == pages,
              expectedSHA == nil || preview.source.sha256 == expectedSHA else {
            throw NativeError.message("Предпросмотр не соответствует выбранному PDF или страницам.")
        }
        return preview
    }

    func previewPDF(_ path: String, expected: JSONValue? = nil, canAttach: Bool = true) async {
        guard canReceiveAttachments, let conversation = selected else { return }
        loadingPDFPreview = true
        defer { loadingPDFPreview = false }
        do {
            let source = try expected.map(NativePDFAttachment.init)
            let preview = try await readPDFPreview(path, pages: source?.pages ?? [1], conversation: conversation,
                                                   canAttach: canAttach, expectedSHA: source?.sha256)
            guard expected == nil || preview.source.value == expected else {
                throw NativeError.message("Текст выбранных страниц изменился. Уберите PDF и выберите его заново.")
            }
            pdfPreview = preview
        } catch { if selectedID == conversation.id { report(error) } }
    }

    func reloadPDFPreview(_ preview: NativePDFPreview, pages: [Int]) async throws -> NativePDFPreview {
        guard !busy, !loadingPDFPreview, preview.canAttach, let conversation = selected,
              conversation.id == preview.conversationID, conversation.workspacePath == preview.workspace,
              pdfPreview?.source.path == preview.source.path else {
            throw NativeError.message("Выбор PDF изменился или занят. Ничего не отправлено.")
        }
        loadingPDFPreview = true
        defer { loadingPDFPreview = false }
        return try await readPDFPreview(preview.source.path, pages: pages, conversation: conversation,
                                         canAttach: true, expectedSHA: preview.source.sha256)
    }

    func attachPDF(_ preview: NativePDFPreview) throws {
        guard preview.canAttach, preview.hasText, !busy, !client.turnOutstanding, !loadingPDFPreview,
              !loadingDroppedAttachments, selectedID == preview.conversationID,
              selected?.workspacePath == preview.workspace, selected?.archived != true,
              let index = conversations.firstIndex(where: { $0.id == preview.conversationID }) else {
            throw NativeError.message("PDF не готов, диалог изменился или занят. Ничего не прикреплено.")
        }
        let next = conversations[index].pendingPDFs.filter { $0["path"].text != preview.source.path } + [preview.source.value]
        try updatePendingPDFs(next, index: index)
        section = .chat
    }

    func removePendingPDF() {
        guard !busy, let index = conversations.firstIndex(where: { $0.id == selectedID }) else { return }
        do { try updatePendingPDFs([], index: index) } catch { report(error) }
    }

    private func updatePendingPDFs(_ next: [JSONValue], index: Int) throws {
        try NativePDFAttachment.validate(next)
        let previous = conversations[index].pendingPDFs
        conversations[index].pendingPDFs = next
        do {
            try store.save(ChatArchive(conversations: conversations, selectedID: selectedID))
            draftSave?.cancel(); dirtyDraft = false
        } catch { conversations[index].pendingPDFs = previous; throw error }
    }

    private func resetWorkspaceView() { workspaceStatus = .null; workspaceListing = .null; filePreview = .null; workspaceError = nil }

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
                ? "Запись \(recordID) больше не найдена в локальной памяти."
                : "ID \(recordID) неоднозначен между слоями памяти; выберите запись вручную."
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
        guard !busy, !client.turnOutstanding, !loadingLearningReview,
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
                learningReviewError = "\(error.localizedDescription) Автоповтора нет. Проверьте текущую карточку и receipt перед новым действием."
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

    private func append(_ message: ChatMessage, to id: UUID) {
        guard let index = conversations.firstIndex(where: { $0.id == id }) else { return }
        conversations[index].messages.append(message)
        conversations[index].updatedAt = Date()
    }

    private func report(_ error: Error) { self.error = error.localizedDescription; status = "Нужна проверка" }
    private func persist() {
        draftSave?.cancel()
        do { try store.save(ChatArchive(conversations: conversations, selectedID: selectedID)); dirtyDraft = false }
        catch { report(error) }
    }
}
