import Foundation
import SwiftUI

struct TaskUpdate: Codable, Identifiable, Equatable {
    enum State: String, Codable { case queued, sending, accepted, rejected, unknown }
    var id = UUID()
    let text: String
    var createdAt = Date()
    var state: State = .queued

    func label(active: Bool) -> String {
        switch state {
        case .queued: return active ? "Ожидает начала работы" : "Не отправлено"
        case .sending: return active ? "Отправляется…" : "Доставка не подтверждена"
        case .accepted: return "Добавлено к задаче"
        case .rejected: return "Не отправлено · задача уже завершилась или не приняла уточнение"
        case .unknown: return "Доставка не подтверждена · автоповтора не было"
        }
    }

    static func validate(_ messages: [ChatMessage]) throws {
        for message in messages {
            guard let updates = message.taskUpdates else { continue }
            guard message.role == "user", message.operatorInput != true, updates.count <= 32,
                  Set(updates.map(\.id)).count == updates.count,
                  updates.allSatisfy({ !$0.text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                      && $0.text.unicodeScalars.count <= 20_000 && !$0.text.contains("\0") }) else {
                throw NativeError.message("Не удалось проверить сохранённые уточнения задачи.")
            }
        }
    }
}

extension AppModel {
    var canUpdateTask: Bool {
        busy && turnStartedAt != nil && activeTaskMessageID != nil && selected?.provider == "codex"
            && cloudConsent && !taskUpdatesStopped && !historyPersistence.blocksSubmission && !store.writeBlocked
    }

    func enqueueTaskUpdate(_ text: String) async {
        guard canUpdateTask, let sourceID = activeTaskMessageID, let conversationID = selectedID,
              let index = conversations.firstIndex(where: { $0.id == conversationID }),
              let message = conversations[index].messages.firstIndex(where: { $0.id == sourceID }) else { return }
        guard text.unicodeScalars.count <= 20_000, !text.contains("\0"),
              (conversations[index].messages[message].taskUpdates?.count ?? 0) < 32 else {
            error = "Можно отправить до 32 уточнений по 20 000 символов в одной задаче."
            return
        }
        let previous = conversations[index].messages[message].taskUpdates
        let update = TaskUpdate(text: text)
        conversations[index].messages[message].taskUpdates = (previous ?? []) + [update]
        setComposer("")
        guard persist() else {
            conversations[index].messages[message].taskUpdates = previous
            setComposer(text)
            return
        }
        await flushTaskUpdates()
    }

    func receiveTaskUpdateTarget(_ event: JSONValue) {
        guard UUID(uuidString: event["conversation_id"].text) == selectedID else { return }
        taskUpdateTarget = UUID(uuidString: event["token"].text)?.uuidString.lowercased()
        if taskUpdateTarget != nil { Task { await flushTaskUpdates() } }
    }

    func flushTaskUpdates() async {
        guard !sendingTaskUpdate, canUpdateTask, let conversationID = selectedID,
              let sourceID = activeTaskMessageID, let requestID = activeRequest,
              selected?.messages.first(where: { $0.id == sourceID })?.taskUpdates?.contains(where: { $0.state == .queued }) == true else { return }
        sendingTaskUpdate = true
        defer {
            sendingTaskUpdate = false
            // A previous task's acknowledgement can arrive after a new task's
            // ready event. Give that task's saved queue its own sender.
            if activeTaskMessageID != sourceID { Task { await flushTaskUpdates() } }
        }
        while canUpdateTask, selectedID == conversationID, activeTaskMessageID == sourceID,
              activeRequest == requestID, let target = taskUpdateTarget,
              let index = conversations.firstIndex(where: { $0.id == conversationID }),
              let message = conversations[index].messages.firstIndex(where: { $0.id == sourceID }),
              let update = conversations[index].messages[message].taskUpdates?.first(where: { $0.state == .queued }) {
            setTaskUpdateState(.sending, id: update.id, source: sourceID, conversation: conversationID)
            guard persist() else {
                setTaskUpdateState(.queued, id: update.id, source: sourceID, conversation: conversationID)
                return
            }
            var delivery: TaskUpdate.State = .unknown
            do {
                let result = try await client.request("steer", [
                    "request_id": .string(requestID), "conversation_id": .string(conversationID.uuidString),
                    "token": .string(target), "message_id": .string(update.id.uuidString),
                    "text": .string(update.text), "cloud_consent": .bool(cloudConsent)
                ])
                if result["schema"].text == "proto_mind.task_update.v1",
                   result["request_id"].text == requestID,
                   UUID(uuidString: result["conversation_id"].text) == conversationID,
                   UUID(uuidString: result["message_id"].text) == update.id,
                   result["text_sha256"].text == ChatHistoryFormat.hash(Data(update.text.utf8)),
                   let state = TaskUpdate.State(rawValue: result["status"].text), [.accepted, .rejected, .unknown].contains(state) {
                    delivery = state
                }
            } catch { /* Delivery is uncertain; never resend a potentially accepted update. */ }
            setTaskUpdateState(delivery, id: update.id, source: sourceID, conversation: conversationID)
            guard persist() else { return }
        }
    }

    private func setTaskUpdateState(_ state: TaskUpdate.State, id: UUID, source: UUID, conversation: UUID) {
        guard let index = conversations.firstIndex(where: { $0.id == conversation }),
              let message = conversations[index].messages.firstIndex(where: { $0.id == source }),
              let update = conversations[index].messages[message].taskUpdates?.firstIndex(where: { $0.id == id }) else { return }
        conversations[index].messages[message].taskUpdates?[update].state = state
    }

    func closeTaskUpdateQueue() {
        taskUpdatesStopped = true; taskUpdateTarget = nil
        guard let source = activeTaskMessageID,
              let index = conversations.firstIndex(where: { $0.id == selectedID }),
              let message = conversations[index].messages.firstIndex(where: { $0.id == source }),
              let updates = conversations[index].messages[message].taskUpdates else { return }
        for update in updates where update.state == .queued {
            setTaskUpdateState(.rejected, id: update.id, source: source, conversation: conversations[index].id)
        }
    }
}

struct TaskUpdatesView: View {
    let updates: [TaskUpdate]
    let active: Bool
    let copy: (String) -> Void

    var body: some View {
        ForEach(updates) { update in
            HStack {
                Spacer(minLength: 65)
                VStack(alignment: .leading, spacing: 7) {
                    Text(update.text).font(NativeTheme.messageFont).lineSpacing(6).textSelection(.enabled)
                    HStack(spacing: 6) {
                        Image(systemName: update.state == .accepted ? "checkmark" : "arrow.turn.down.right")
                        Text(update.label(active: active)).lineLimit(2)
                        Spacer(minLength: 0)
                        Button { copy(update.text) } label: { Image(systemName: "doc.on.doc") }
                            .buttonStyle(.nativeHover).accessibilityLabel("Копировать уточнение")
                    }.font(.system(size: 10.5)).foregroundStyle(.secondary)
                }.padding(.horizontal, 18).padding(.vertical, 13)
                    .background(NativeTheme.bubble, in: RoundedRectangle(cornerRadius: 20))
                    .frame(maxWidth: 650, alignment: .trailing)
            }
        }
    }
}
