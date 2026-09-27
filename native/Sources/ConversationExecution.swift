import Combine
import Foundation

/// The running turn's frequently changing output. Only the views that show it observe it:
/// an execution change reaches every AppModel observer, and in a long conversation that
/// re-evaluated every message for each streamed batch or work-log row.
@MainActor
final class LiveTurnOutput: ObservableObject {
    @Published var stream = ""
    @Published var agentItems: [JSONValue] = []
    @Published var agentReceipt: JSONValue = .null
    @Published var workLog: JSONValue = .null
}

/// One live turn and one provider connection belong to one conversation.
/// AppModel remains the sole owner/writer of the complete dialog archive.
@MainActor
final class ConversationExecution: ObservableObject {
    let conversationID: UUID
    let client: BridgeClient
    var observation: AnyCancellable?
    @Published var running = false
    let live = LiveTurnOutput()
    var stream: String { get { live.stream } set { live.stream = newValue } }
    var agentItems: [JSONValue] { get { live.agentItems } set { live.agentItems = newValue } }
    var agentReceipt: JSONValue { get { live.agentReceipt } set { live.agentReceipt = newValue } }
    var workLog: JSONValue { get { live.workLog } set { live.workLog = newValue } }
    private var pendingStream = ""
    private var streamFlush: Task<Void, Never>?
    @Published private var statusKey = "Готов"
    var status: String {
        get { L10n.text(statusKey) }
        set { if statusKey != newValue { statusKey = newValue } }  // Tool rows repeat it; each change reaches all of AppModel.
    }
    @Published var startedAt: Date?
    @Published var autoSkillsReport: NativeAutoSkillsReport?
    @Published var personaReceipt: NativePersonaTurnReceipt?
    @Published var sourceMessageID: UUID?
    @Published var updateTarget: String?
    @Published var sendingUpdate = false
    @Published var updatesStopped = false
    @Published var workspaceQuestions: [WorkspaceAgentQuestion] = []
    var workspaceToolCalls: Set<String> = []
    var workspaceToolsAllowed = false
    /// Pixel-to-point mapping of this turn's latest computer-use screen capture.
    var computerCapture: ComputerCapture?
    var workspaceToolBinding: String?
    var workspaceCreatedTasks: Set<UUID> = []
    var workspaceWorker: BridgeClient?
    var requestID: String?

    init(conversationID: UUID, configuration: LaunchConfiguration, codexAccountID: UUID? = nil) {
        self.conversationID = conversationID
        client = BridgeClient(configuration: configuration, codexAccountID: codexAccountID)
    }

    /// Shows streamed text at most ten times a second. Every change re-renders the whole
    /// conversation, and a provider can send deltas several times faster than that.
    func appendStream(_ delta: String) {
        pendingStream += delta
        guard streamFlush == nil else { return }
        streamFlush = Task { @MainActor [weak self] in
            try? await Task.sleep(for: .milliseconds(100))
            guard !Task.isCancelled, let self else { return }
            streamFlush = nil
            stream += pendingStream
            pendingStream = ""
        }
    }

    func resetStream() {
        streamFlush?.cancel(); streamFlush = nil
        pendingStream = ""; stream = ""
    }

    func clearTurn() {
        workspaceWorker?.shutdown(); workspaceWorker = nil; workspaceToolsAllowed = false
        running = false; resetStream(); requestID = nil; agentItems = []
        agentReceipt = .null; workLog = .null; startedAt = nil
        autoSkillsReport = nil; sourceMessageID = nil; computerCapture = nil
    }
}

extension AppModel {
    var selectedExecution: ConversationExecution? { selectedID.flatMap { executions[$0] } }
    var anyTaskRunning: Bool { executions.values.contains { $0.running || $0.client.turnOutstanding } || serviceClient.turnOutstanding }
    var globalBusy: Bool { operationBusy || anyTaskRunning || executions.values.contains { $0.sendingUpdate } }
    var canNavigateConversations: Bool {
        !operationBusy && !loadingDroppedAttachments && !loadingImagePreview && !loadingPDFPreview && !presentations.locked
    }
    var busy: Bool {
        get { operationBusy || selectedExecution?.running == true }
        set { operationBusy = newValue }
    }

    func execution(for id: UUID) -> ConversationExecution {
        if let existing = executions[id] { return existing }
        let accountID = conversations.first { $0.id == id }?.codexAccountID
        let state = ConversationExecution(conversationID: id, configuration: serviceClient.configuration, codexAccountID: accountID)
        state.workspaceQuestions = conversations.first { $0.id == id }?.workspaceQuestions ?? []
        state.observation = state.objectWillChange.sink { [weak self] in self?.objectWillChange.send() }
        state.client.onEvent = { [weak self, weak state] event in
            guard let self, let state else { return }
            self.receiveExecutionEvent(event, state: state)
        }
        executions[id] = state
        return state
    }

    var turnClient: BridgeClient { selectedID.map { execution(for: $0).client } ?? client }
    func isRunning(_ id: UUID) -> Bool { executions[id]?.running == true }

    func closeIdleExecutionConnections() {
        guard !globalBusy else { return }
        for state in executions.values { state.workspaceWorker?.shutdown(); state.client.shutdown() }
        executions.removeAll(); agentGrants.removeAll(); pendingAgentAccess = nil
        if let id = selectedID { _ = execution(for: id) }
    }

    func shutdown() {
        appUpdate.stop()
        closeClaudeAuthentication()
        telegram.stop()
        workspaceServices.shutdown()
        workspacePanels.closeAll()
        dictation.shutdown()
        presentations.shutdown()
        desktop.shutdown()
        liveVoice.shutdown()
        restoringAgentAccess.values.forEach { $0.cancel() }; restoringAgentAccess.removeAll()
        for state in executions.values { state.workspaceWorker?.shutdown(); state.client.shutdown() }
        serviceClient.shutdown()
        codexAccounts.shutdown()
    }

    func receiveExecutionEvent(_ event: JSONValue, state: ConversationExecution) {
        guard state.running, event["request_id"].text == state.requestID else { return }
        switch event["event"].text {
        case "workspace_tool": receiveWorkspaceTool(event, state: state)
        case "answer_delta": state.appendStream(event["delta"].text)
        case "answer_reset": state.resetStream()
        case "steering_ready": receiveTaskUpdateTarget(event, execution: state)
        case "auto_skills":
            if let report = try? NativeAutoSkillsReport(event["report"]) {
                state.autoSkillsReport = report
                if report.state == "selecting" { state.status = "Подбираю навык · без инструментов" }
            }
        case "agent_activity":
            let item = event["item"]
            guard !item["id"].text.isEmpty else { return }
            if let index = state.agentItems.firstIndex(where: { $0["id"] == item["id"] }) { state.agentItems[index] = item }
            else {
                state.agentItems.append(item)
                if state.agentItems.count > 64 { state.agentItems.removeFirst(state.agentItems.count - 64) }
            }
            if item["failure_code"].text == "macos_automation_permission_denied" {
                state.status = "Нужно разрешение macOS Automation"
                if selectedID == state.conversationID {
                    computerUsePermissionIssue = true
                    error = L10n.text("macOS не разрешила Proto-Mind управлять приложениями. Откройте Automation, разрешите Proto-Mind Native и начните новый ход с полным доступом. Автоповтора не было.")
                }
            } else { state.status = "Агент работает" }
        case "agent_run": state.agentReceipt = event["receipt"]; state.agentItems = state.agentReceipt["items"].items
        case "work_log":
            if event["log"]["schema"].text == "proto_mind.native_work_log.v1",
               WorkLogEventGate.shouldAccept(current: state.workLog, incoming: event["log"]) { state.workLog = event["log"] }
        default: break
        }
    }

    // Selected-conversation projections keep presentation code independent of
    // background tasks. Async execution code always holds its captured state.
    private func setSelected<T>(_ path: ReferenceWritableKeyPath<ConversationExecution, T>, _ value: T) {
        if let id = selectedID { execution(for: id)[keyPath: path] = value }
    }
    var stream: String { get { selectedExecution?.stream ?? "" } set { setSelected(\.stream, newValue) } }
    var status: String {
        get { selectedExecution?.status ?? L10n.text(idleStatus) }
        set { if let state = selectedExecution { state.status = newValue } else { idleStatus = newValue } }
    }
    var lastPersonaTurnReceipt: NativePersonaTurnReceipt? { selectedExecution?.personaReceipt }
    var agentItems: [JSONValue] { get { selectedExecution?.agentItems ?? [] } set { setSelected(\.agentItems, newValue) } }
    var agentReceipt: JSONValue { get { selectedExecution?.agentReceipt ?? .null } set { setSelected(\.agentReceipt, newValue) } }
    var workLog: JSONValue { get { selectedExecution?.workLog ?? .null } set { setSelected(\.workLog, newValue) } }
    var turnStartedAt: Date? { get { selectedExecution?.startedAt } set { setSelected(\.startedAt, newValue) } }
    var activeRequest: String? { get { selectedExecution?.requestID } set { setSelected(\.requestID, newValue) } }
    var autoSkillsReport: NativeAutoSkillsReport? { get { selectedExecution?.autoSkillsReport } set { setSelected(\.autoSkillsReport, newValue) } }
    var activeTaskMessageID: UUID? { get { selectedExecution?.sourceMessageID } set { setSelected(\.sourceMessageID, newValue) } }
    var taskUpdateTarget: String? { get { selectedExecution?.updateTarget } set { setSelected(\.updateTarget, newValue) } }
    var sendingTaskUpdate: Bool { get { selectedExecution?.sendingUpdate ?? false } set { setSelected(\.sendingUpdate, newValue) } }
    var taskUpdatesStopped: Bool { get { selectedExecution?.updatesStopped ?? false } set { setSelected(\.updatesStopped, newValue) } }
}
