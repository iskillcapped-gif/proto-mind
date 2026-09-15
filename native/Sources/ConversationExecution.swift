import Combine
import Foundation

/// One live turn and one provider connection belong to one conversation.
/// AppModel remains the sole owner/writer of the complete dialog archive.
@MainActor
final class ConversationExecution: ObservableObject {
    let conversationID: UUID
    let client: BridgeClient
    var observation: AnyCancellable?
    @Published var running = false
    @Published var stream = ""
    @Published var status = "Готов"
    @Published var agentItems: [JSONValue] = []
    @Published var agentReceipt: JSONValue = .null
    @Published var workLog: JSONValue = .null
    @Published var startedAt: Date?
    @Published var autoSkillsReport: NativeAutoSkillsReport?
    @Published var personaReceipt: NativePersonaTurnReceipt?
    @Published var sourceMessageID: UUID?
    @Published var updateTarget: String?
    @Published var sendingUpdate = false
    @Published var updatesStopped = false
    var requestID: String?

    init(conversationID: UUID, configuration: LaunchConfiguration) {
        self.conversationID = conversationID
        client = BridgeClient(configuration: configuration)
    }

    func clearTurn() {
        running = false; stream = ""; requestID = nil; agentItems = []
        agentReceipt = .null; workLog = .null; startedAt = nil
        autoSkillsReport = nil; sourceMessageID = nil
    }
}

extension AppModel {
    var selectedExecution: ConversationExecution? { selectedID.flatMap { executions[$0] } }
    var anyTaskRunning: Bool { executions.values.contains { $0.running || $0.client.turnOutstanding } || serviceClient.turnOutstanding }
    var globalBusy: Bool { operationBusy || anyTaskRunning || executions.values.contains { $0.sendingUpdate } }
    var canNavigateConversations: Bool {
        !operationBusy && !connecting && !loadingDroppedAttachments && !loadingImagePreview && !loadingPDFPreview && !presentations.locked
    }
    var busy: Bool {
        get { operationBusy || selectedExecution?.running == true }
        set { operationBusy = newValue }
    }

    func execution(for id: UUID) -> ConversationExecution {
        if let existing = executions[id] { return existing }
        let state = ConversationExecution(conversationID: id, configuration: serviceClient.configuration)
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
        for state in executions.values { state.client.shutdown() }
        executions.removeAll(); agentGrants.removeAll(); pendingAgentAccess = nil
        if let id = selectedID { _ = execution(for: id) }
    }

    func shutdown() {
        presentations.shutdown()
        desktop.shutdown()
        liveVoice.shutdown()
        restoringAgentAccess.values.forEach { $0.cancel() }; restoringAgentAccess.removeAll()
        for state in executions.values { state.client.shutdown() }
        serviceClient.shutdown()
    }

    func receiveExecutionEvent(_ event: JSONValue, state: ConversationExecution) {
        guard state.running, event["request_id"].text == state.requestID else { return }
        switch event["event"].text {
        case "answer_delta": state.stream += event["delta"].text
        case "answer_reset": state.stream = ""
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
                    error = "macOS не разрешила Proto-Mind управлять приложениями. Откройте Automation, разрешите Proto-Mind Native и начните новый ход с полным доступом. Автоповтора не было."
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
        get { selectedExecution?.status ?? idleStatus }
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
