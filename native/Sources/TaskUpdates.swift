import Foundation
import SwiftUI

struct TaskUpdate: Codable, Identifiable, Equatable {
    enum State: String, Codable { case queued, sending, accepted, rejected, unknown }
    var id = UUID()
    let text: String
    var createdAt = Date()
    var state: State = .queued
    var fileContext: [JSONValue]? = nil
    var imageContext: [JSONValue]? = nil
    var pdfContext: [JSONValue]? = nil
    var reason: String? = nil

    var hasAttachments: Bool { !(fileContext ?? []).isEmpty || !(imageContext ?? []).isEmpty || !(pdfContext ?? []).isEmpty }
    var attachments: JSONValue {
        .object(["files": .array(fileContext ?? []), "images": .array(imageContext ?? []), "pdfs": .array(pdfContext ?? [])])
    }
    var attachmentNames: [String] {
        ((fileContext ?? []) + (imageContext ?? []) + (pdfContext ?? [])).map { URL(fileURLWithPath: $0["path"].text).lastPathComponent }
    }
    var historyText: String {
        (hasAttachments ? "[Earlier attachment content is NOT included. Reattach files to inspect them again.]\n" : "") + text
    }

    func label(active: Bool) -> String {
        switch state {
        case .queued: return active ? "Ожидает начала работы" : "Не отправлено"
        case .sending: return active ? "Отправляется…" : "Доставка не подтверждена"
        case .accepted: return "Добавлено к задаче"
        case .rejected: return reason ?? "Не отправлено · задача уже завершилась или не приняла уточнение"
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
            for update in updates {
                try NativeImageAttachment.validate(update.imageContext ?? [])
                try NativePDFAttachment.validate(update.pdfContext ?? [])
                let files = update.fileContext ?? []
                guard files.count <= 3, Set(files.map { $0["path"].text }).count == files.count,
                      files.allSatisfy({ file in
                          guard case .object(let fields) = file else { return false }
                          return Set(fields.keys) == ["path", "sha256", "included_chars", "truncated"]
                              && !file["path"].text.isEmpty && !file["path"].text.hasPrefix("/")
                              && !file["path"].text.split(separator: "/").contains("..")
                              && file["path"].text.utf8.count <= 16_384
                              && !file["path"].text.unicodeScalars.contains(where: { $0.value < 32 })
                              && file["sha256"].text.count == 64 && file["sha256"].text.allSatisfy { "0123456789abcdef".contains($0) }
                              && (0...6000).contains(file["included_chars"].integer)
                              && file["included_chars"] == .number(Double(file["included_chars"].integer))
                              && [.bool(true), .bool(false)].contains(file["truncated"])
                      }), (update.reason?.count ?? 0) <= 600 else {
                    throw NativeError.message("Не удалось проверить вложения уточнения.")
                }
            }
        }
    }
}

extension AppModel {
    var canEditMessageAttachments: Bool { (!busy && !client.turnOutstanding) || canUpdateTask }
    var hasPendingMessageAttachments: Bool {
        selected.map { !$0.pendingFiles.isEmpty || !$0.pendingImages.isEmpty || !$0.pendingPDFs.isEmpty } ?? false
    }
    var hasComposerInput: Bool { !composer.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || hasPendingMessageAttachments }
    var composerShowsStop: Bool { busy && !hasComposerInput }
    var canSendComposer: Bool {
        hasComposerInput && (!busy || canUpdateTask) && selected?.archived != true
            && !loadingDroppedAttachments && !loadingImagePreview && !loadingPDFPreview
            && imagePreview == nil && pdfPreview == nil && attachmentDropPreview == nil
            && !historyPersistence.blocksSubmission && !store.writeBlocked
    }
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
        let previous = conversations[index]
        let update = TaskUpdate(text: text, fileContext: previous.pendingFiles, imageContext: previous.pendingImages, pdfContext: previous.pendingPDFs)
        conversations[index].messages[message].taskUpdates = (previous.messages[message].taskUpdates ?? []) + [update]
        conversations[index].pendingFiles = []; conversations[index].pendingImages = []; conversations[index].pendingPDFs = []
        setComposer("")
        guard persist() else {
            conversations[index] = previous
            setComposer(text)
            return
        }
        if let state = selectedExecution { await flushTaskUpdates(execution: state) }
    }

    private func canUpdateTask(_ state: ConversationExecution) -> Bool {
        state.running && state.startedAt != nil && state.sourceMessageID != nil
            && cloudConsent && !state.updatesStopped && !historyPersistence.blocksSubmission && !store.writeBlocked
    }

    func receiveTaskUpdateTarget(_ event: JSONValue, execution state: ConversationExecution) {
        guard UUID(uuidString: event["conversation_id"].text) == state.conversationID else { return }
        state.updateTarget = UUID(uuidString: event["token"].text)?.uuidString.lowercased()
        if state.updateTarget != nil { Task { await flushTaskUpdates(execution: state) } }
    }

    func flushTaskUpdates(execution state: ConversationExecution) async {
        let conversationID = state.conversationID
        guard !state.sendingUpdate, canUpdateTask(state),
              let sourceID = state.sourceMessageID, let requestID = state.requestID else { return }
        state.sendingUpdate = true
        defer {
            state.sendingUpdate = false
            if state.sourceMessageID != sourceID && state.running { Task { await flushTaskUpdates(execution: state) } }
        }
        while canUpdateTask(state), state.sourceMessageID == sourceID,
              state.requestID == requestID, let target = state.updateTarget,
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
                var params: [String: JSONValue] = [
                    "request_id": .string(requestID), "conversation_id": .string(conversationID.uuidString),
                    "token": .string(target), "message_id": .string(update.id.uuidString),
                    "text": .string(update.text), "cloud_consent": .bool(cloudConsent)
                ]
                if update.hasAttachments { params["attachments"] = update.attachments }
                let result = try await state.client.request("steer", params)
                if result["schema"].text == "proto_mind.task_update.v1",
                   result["request_id"].text == requestID,
                   UUID(uuidString: result["conversation_id"].text) == conversationID,
                   UUID(uuidString: result["message_id"].text) == update.id,
                   result["text_sha256"].text == ChatHistoryFormat.hash(Data(update.text.utf8)),
                   result["attachments"] == (update.hasAttachments ? update.attachments : .null),
                   let deliveryState = TaskUpdate.State(rawValue: result["status"].text), [.accepted, .rejected, .unknown].contains(deliveryState) {
                    delivery = deliveryState
                    if deliveryState == .rejected, !result["reason"].text.isEmpty {
                        setTaskUpdateReason(String(result["reason"].text.prefix(600)), id: update.id, source: sourceID, conversation: conversationID)
                    }
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

    private func setTaskUpdateReason(_ reason: String, id: UUID, source: UUID, conversation: UUID) {
        guard let index = conversations.firstIndex(where: { $0.id == conversation }),
              let message = conversations[index].messages.firstIndex(where: { $0.id == source }),
              let update = conversations[index].messages[message].taskUpdates?.firstIndex(where: { $0.id == id }) else { return }
        conversations[index].messages[message].taskUpdates?[update].reason = reason
    }

    func closeTaskUpdateQueue(execution state: ConversationExecution) {
        state.updatesStopped = true; state.updateTarget = nil
        guard let source = state.sourceMessageID,
              let index = conversations.firstIndex(where: { $0.id == state.conversationID }),
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
                    if update.hasAttachments {
                        ForEach(Array(update.attachmentNames.enumerated()), id: \.offset) { _, name in
                            Label(name, systemImage: "paperclip").font(.system(size: 12)).foregroundStyle(.secondary).lineLimit(2)
                        }
                    }
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
