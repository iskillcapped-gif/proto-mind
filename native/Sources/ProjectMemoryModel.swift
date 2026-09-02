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
    @Published private(set) var detail: ProjectNote?
    @Published private(set) var error: String?
    @Published private(set) var loading = false
    @Published private(set) var saving = false
    @Published private(set) var total = 0
    @Published private(set) var offset = 0
    @Published private(set) var matching = 0
    @Published private(set) var recalling = false
    init(app: AppModel, scope: ProjectMemoryScope) { self.app = app; self.scope = scope }
    var current: Bool { app.projectMemory?.id == id && app.selectedID == scope.conversationID && app.selected?.workspacePath == scope.workspace }
    var locked: Bool { !current || app.busy || app.client.turnOutstanding || loading || saving }
    var note: JSONValue { .object(["kind": .string(noteKind), "content": .string(content.trimmingCharacters(in: .whitespacesAndNewlines)),
                                 "basis": .string(basis.trimmingCharacters(in: .whitespacesAndNewlines)), "supersedes_id": .string(supersedesID)]) }
    func invalidate() { preview = nil }
    func close() { guard !saving else { return }; if current { app.projectMemory = nil } }
    func refresh(recall: Bool = false, offset: Int = 0) async {
        guard !locked else { return }
        loading = true; error = nil; preview = nil; detail = nil
        defer { loading = false }
        do {
            var params = scope.parameters
            if recall { params["query"] = .string(query.trimmingCharacters(in: .whitespacesAndNewlines)) }
            else { params["include_history"] = .bool(includeHistory); params["offset"] = .number(Double(offset)) }
            let value = try await app.client.request(recall ? "project_memory_recall" : "project_memory_list", params)
            try checkProjectMemory(value, scope: scope, kind: "list")
            guard current, case .array(let rows) = value["items"], rows.count <= (recall ? 5 : 40),
                  case .array(let warnings) = value["issues"], warnings.count <= 201,
                  value["limit"] == .number(200), (0...200).contains(value["total_count"].integer) else { throw projectMemoryError() }
            notes = try rows.map(ProjectNote.init); issues = warnings.map(\.text); total = value["total_count"].integer
            self.offset = value["offset"].integer; matching = value["matching_count"].integer; recalling = recall
        } catch { if current { self.error = error.localizedDescription; notes = [] } }
    }
    func inspect(_ note: ProjectNote) async {
        guard !locked else { return }
        loading = true; preview = nil; detail = nil; error = nil
        defer { loading = false }
        do {
            var params = scope.parameters; params["record_id"] = .string(note.id)
            let value = try await app.client.request("project_memory_inspect", params)
            try checkProjectMemory(value, scope: scope, kind: "inspect")
            let checked = try ProjectNote(value["item"])
            guard current, checked.id == note.id, checked.raw["record_hash"] == note.raw["record_hash"] else { throw projectMemoryError() }
            detail = checked; issues = value["issues"].items.map(\.text)
        } catch { if current { self.error = error.localizedDescription } }
    }
    func prepare() async {
        guard !locked else { return }
        loading = true; preview = nil; error = nil
        let selected = note
        defer { loading = false }
        do {
            var params = scope.parameters; params["note"] = selected
            let value = try await app.client.request("project_memory_preview", params)
            try checkProjectMemory(value, scope: scope, kind: "preview")
            guard current, selected == note, ["kind", "content", "basis", "supersedes_id"].allSatisfy({ value["body"][$0] == selected[$0] }) else { throw projectMemoryError() }
            preview = value
        } catch { if current { self.error = error.localizedDescription } }
    }
    func save(token: String, acknowledgement: Bool) async {
        guard !locked, let preview, acknowledgement, token == preview["confirmation_token"].text,
              ["kind", "content", "basis", "supersedes_id"].allSatisfy({ preview["body"][$0] == note[$0] }) else { return }
        app.busy = true; saving = true; self.preview = nil; error = nil
        do {
            var params = scope.parameters; params["note"] = note
            params["preview_fingerprint"] = preview["preview_fingerprint"]; params["confirmation_token"] = .string(token)
            params["acknowledge_operator_note"] = .bool(true)
            let value = try await app.client.request("project_memory_save", params)
            try checkProjectMemory(value, scope: scope, kind: "saved")
            _ = try ProjectNote(value["item"])
            if current { content = ""; basis = ""; supersedesID = ""; app.status = "Заметка проекта сохранена; модели не отправлялась" }
        } catch { if current { self.error = "\(error.localizedDescription) Проверьте список перед повтором." } }
        app.busy = false; saving = false
        let failure = error
        if current { await refresh(); error = failure }
    }
    func replaceSelected() {
        guard !locked, let detail, detail.active, issues.isEmpty else { return }
        supersedesID = detail.id; noteKind = detail.kind; content = detail.content; basis = ""; preview = nil
    }
    func attach() {
        guard !locked, let detail, detail.active, issues.isEmpty, app.selected?.archived == false else { return }
        var selected = app.projectNoteSelections[scope.conversationID] ?? []
        selected.removeAll { $0.id == detail.id }
        guard selected.count < 5 else { error = "Можно выбрать не больше пяти заметок для одного сообщения."; return }
        selected.append(detail); app.projectNoteSelections[scope.conversationID] = selected
        app.invalidateContextPreview()
        app.status = "Заметка выбрана только для следующего сообщения; отправьте его вручную"
        app.section = .chat; close()
    }
}

extension AppModel {
    var pendingProjectNotes: [ProjectNote] { selectedID.map { projectNoteSelections[$0] ?? [] } ?? [] }
    func openProjectMemory() async {
        guard !busy, !client.turnOutstanding, let selected, let workspace = selected.workspacePath else {
            error = "Сначала выберите рабочую папку диалога."; return
        }
        let panel = ProjectMemoryModel(app: self, scope: ProjectMemoryScope(conversationID: selected.id, workspace: workspace))
        projectMemory = panel; await panel.refresh()
    }
    func removeProjectNote(_ id: String) {
        guard !busy, let selectedID else { return }
        projectNoteSelections[selectedID]?.removeAll { $0.id == id }; invalidateContextPreview()
    }
}
