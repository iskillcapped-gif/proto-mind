import Foundation
import SwiftUI

@MainActor
final class ProjectMemoryModel: ObservableObject, Identifiable {
    let id = UUID()
    unowned let app: AppModel
    let scope: ProjectMemoryScope
    @Published var query = ""
    @Published var includeHistory = false
    @Published var noteKind = "project_fact"
    @Published var content = ""
    @Published var basis = ""
    @Published var supersedesID = ""
    @Published private(set) var notes: [ProjectNote] = []
    @Published private(set) var issues: [String] = []
    @Published private(set) var preview: JSONValue?
    @Published private(set) var statePreview: JSONValue?
    @Published private(set) var notice: String?
    @Published private(set) var detail: ProjectNote?
    @Published private(set) var error: String?
    @Published private(set) var loading = false
    @Published private(set) var saving = false
    @Published private(set) var total = 0
    @Published private(set) var offset = 0
    @Published private(set) var matching = 0
    @Published private(set) var recalling = false
    init(app: AppModel, scope: ProjectMemoryScope) { self.app = app; self.scope = scope }
    var conversation: Conversation? { app.conversations.first { $0.id == scope.conversationID } }
    var client: BridgeClient { app.execution(for: scope.conversationID).client }
    var current: Bool { app.projectMemory?.id == id && conversation?.workspacePath == scope.workspace }
    var locked: Bool { !current || app.globalBusy || client.turnOutstanding || loading || saving }
    var note: JSONValue { .object(["kind": .string(noteKind), "content": .string(content.trimmingCharacters(in: .whitespacesAndNewlines)),
                                 "basis": .string(basis.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ? L10n.text("Добавлено пользователем в память проекта.") : basis.trimmingCharacters(in: .whitespacesAndNewlines)), "supersedes_id": .string(supersedesID)]) }
    func invalidate() { preview = nil; statePreview = nil }
    func close() { guard !saving else { return }; if current { app.projectMemory = nil } }
    func refresh(recall: Bool = false, offset: Int = 0) async {
        guard !locked else { return }
        loading = true; error = nil; invalidate(); detail = nil
        defer { loading = false }
        do {
            var params = scope.parameters
            if recall { params["query"] = .string(query.trimmingCharacters(in: .whitespacesAndNewlines)); params["include_history"] = .bool(includeHistory) }
            else { params["include_history"] = .bool(includeHistory); params["offset"] = .number(Double(offset)) }
            let value = try await client.request(recall ? "project_memory_recall" : "project_memory_list", params)
            try checkProjectMemory(value, scope: scope, kind: "list")
            guard current, case .array(let rows) = value["items"], rows.count <= (recall ? 5 : 40),
                  case .array(let warnings) = value["issues"], warnings.count <= 2001,
                  value["limit"] == .number(200), (0...200).contains(value["total_count"].integer) else { throw projectMemoryError() }
            notes = try rows.map(ProjectNote.init); issues = warnings.map(\.text); total = value["total_count"].integer
            self.offset = value["offset"].integer; matching = value["matching_count"].integer; recalling = recall
        } catch { if current { self.error = error.localizedDescription; notes = [] } }
    }
    func inspect(_ note: ProjectNote) async {
        guard !locked else { return }
        loading = true; invalidate(); detail = nil; error = nil
        defer { loading = false }
        do {
            var params = scope.parameters; params["record_id"] = .string(note.id)
            let value = try await client.request("project_memory_inspect", params)
            try checkProjectMemory(value, scope: scope, kind: "inspect")
            let checked = try ProjectNote(value["item"])
            guard current, checked.id == note.id, checked.raw["record_hash"] == note.raw["record_hash"] else { throw projectMemoryError() }
            detail = checked; issues = value["issues"].items.map(\.text)
        } catch { if current { self.error = error.localizedDescription } }
    }
    func prepare() async {
        guard !locked else { return }
        loading = true; invalidate(); error = nil; notice = nil
        let selected = note
        defer { loading = false }
        do {
            var params = scope.parameters; params["note"] = selected
            let value = try await client.request("project_memory_preview", params)
            try checkProjectMemory(value, scope: scope, kind: "preview")
            guard current, selected == note, ["kind", "content", "basis", "supersedes_id"].allSatisfy({ value["body"][$0] == selected[$0] }) else { throw projectMemoryError() }
            preview = value
        } catch { if current { self.error = error.localizedDescription } }
    }
    func save(token: String, acknowledgement: Bool) async {
        guard !locked, let preview, acknowledgement, token == preview["confirmation_token"].text,
              ["kind", "content", "basis", "supersedes_id"].allSatisfy({ preview["body"][$0] == note[$0] }) else { return }
        app.busy = true; saving = true; self.preview = nil; error = nil
        let replaced = supersedesID
        do {
            var params = scope.parameters; params["note"] = note
            params["preview_fingerprint"] = preview["preview_fingerprint"]; params["confirmation_token"] = .string(token)
            params["acknowledge_operator_note"] = .bool(true)
            let value = try await client.request("project_memory_save", params)
            try checkProjectMemory(value, scope: scope, kind: "saved")
            _ = try ProjectNote(value["item"])
            if current {
                if !replaced.isEmpty { app.removeProjectNoteSelections(replaced) }
                app.invalidateContextPreview()
                content = ""; basis = ""; supersedesID = ""; query = ""
                notice = replaced.isEmpty ? L10n.text("Заметка сохранена в памяти проекта.") : L10n.text("Изменения сохранены. Прежняя версия осталась в истории.")
                app.status = L10n.text("Заметка проекта сохранена; модели не отправлялась")
            }
        } catch { if current { self.error = L10n.format("\(error.localizedDescription) Проверьте список перед повтором.") } }
        app.busy = false; saving = false
        let failure = error
        if current { await refresh(); error = failure }
    }
    func saveDraft() async {
        guard !locked else { return }
        let draft = note
        await prepare()
        guard current, note == draft, let preview else { return }
        await save(token: preview["confirmation_token"].text, acknowledgement: true)
    }
    func newNote() {
        guard !locked else { return }
        noteKind = "project_fact"; content = ""; basis = ""; supersedesID = ""; invalidate(); notice = nil
    }
    func prepareState(_ action: String) async {
        guard !locked, let selected = detail, issues.isEmpty,
              action == "archive" && selected.active || action == "restore" && selected.archived else { return }
        loading = true; invalidate(); error = nil; notice = nil
        defer { loading = false }
        do {
            var params = scope.parameters
            params["record_id"] = selected.raw["id"]; params["record_hash"] = selected.raw["record_hash"]; params["action"] = .string(action)
            let value = try await client.request("project_memory_state_preview", params)
            try checkProjectMemory(value, scope: scope, kind: "state_preview")
            guard current, detail == selected, value["item"] == selected.raw, value["body"]["action"] == .string(action) else { throw projectMemoryError() }
            statePreview = value
        } catch { if current { self.error = error.localizedDescription } }
    }
    func applyState(acknowledgement: Bool) async {
        guard !locked, acknowledgement, let statePreview, let detail, statePreview["item"] == detail.raw else { return }
        app.busy = true; saving = true; self.statePreview = nil; error = nil
        let action = statePreview["body"]["action"]
        do {
            var params = scope.parameters
            params["record_id"] = detail.raw["id"]; params["record_hash"] = detail.raw["record_hash"]; params["action"] = action
            params["preview_fingerprint"] = statePreview["preview_fingerprint"]; params["confirmation_token"] = statePreview["confirmation_token"]
            params["acknowledge_memory_change"] = .bool(true)
            let value = try await client.request("project_memory_state_save", params)
            try checkProjectMemory(value, scope: scope, kind: "state_saved")
            let saved = try ProjectNote(value["item"])
            guard value["action"] == action,
                  case .object(let old) = detail.raw, case .object(let new) = saved.raw,
                  old.filter({ $0.key != "status" }) == new.filter({ $0.key != "status" }) else { throw projectMemoryError() }
            if current {
                if saved.archived { app.removeProjectNoteSelections(saved.id) }
                app.invalidateContextPreview()
                notice = saved.archived ? L10n.text("Заметка убрана из памяти проекта. Вернуть её можно в истории.") : L10n.text("Заметка снова доступна в памяти проекта.")
            }
        } catch { if current { self.error = L10n.format("\(error.localizedDescription) Проверьте список перед повтором.") } }
        app.busy = false; saving = false
        let failure = error
        if current { await refresh(recall: !query.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty); error = failure }
    }
    func changeState(_ action: String) async {
        guard !locked, let selected = detail,
              action == "archive" && selected.active || action == "restore" && selected.archived else { return }
        await prepareState(action)
        guard current, detail == selected, statePreview?["body"]["action"] == .string(action) else { return }
        await applyState(acknowledgement: true)
    }
    func replaceSelected() {
        guard !locked, let detail, detail.active, issues.isEmpty else { return }
        supersedesID = detail.id; noteKind = detail.kind; content = detail.content; basis = ""; invalidate(); notice = nil
    }
    func attach() {
        guard !locked, let detail, detail.active, issues.isEmpty, conversation?.archived == false else { return }
        var selected = app.projectNoteSelections[scope.conversationID] ?? []
        selected.removeAll { $0.id == detail.id }
        guard selected.count < 5 else { error = L10n.text("Можно выбрать не больше пяти заметок для одного сообщения."); return }
        selected.append(detail); app.projectNoteSelections[scope.conversationID] = selected
        app.invalidateContextPreview()
        app.status = L10n.text("Заметка выбрана только для следующего сообщения; отправьте его вручную")
        if app.selectedID == scope.conversationID { app.section = .chat }
        close()
    }
}

extension AppModel {
    func removeProjectNoteSelections(_ id: String) {
        for conversation in Array(projectNoteSelections.keys) { projectNoteSelections[conversation]?.removeAll { $0.id == id } }
        invalidateContextPreview()
    }
    var pendingProjectNotes: [ProjectNote] { selectedID.map { projectNoteSelections[$0] ?? [] } ?? [] }
    func openProjectMemory(conversationID: UUID? = nil, in source: WorkspacePresentations? = nil) async {
        guard let id = conversationID ?? selectedID, !globalBusy, !execution(for: id).client.turnOutstanding,
              let chat = conversations.first(where: { $0.id == id }), let workspace = chat.workspacePath else {
            error = L10n.text("Сначала выберите рабочую папку диалога."); return
        }
        let destination = source ?? presentations.currentDestination
        let panel = ProjectMemoryModel(app: self, scope: ProjectMemoryScope(conversationID: id, workspace: workspace))
        presentations.prepare(panel.id, in: destination)
        projectMemory = panel; await panel.refresh()
    }
    func removeProjectNote(_ id: String) {
        guard !globalBusy, let selectedID else { return }
        projectNoteSelections[selectedID]?.removeAll { $0.id == id }; invalidateContextPreview()
    }
}
