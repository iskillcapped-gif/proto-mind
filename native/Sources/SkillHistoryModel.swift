import Foundation
import SwiftUI

@MainActor
final class SkillHistoryModel: ObservableObject, Identifiable {
    let id = UUID()
    unowned let app: AppModel
    let selection: NativeSkillInspectionSelection
    @Published private(set) var entries: [SkillHistoryEntry] = []
    @Published private(set) var preview: JSONValue?
    @Published private(set) var detail: JSONValue?
    @Published private(set) var issues: [String] = []
    @Published private(set) var error: String?
    @Published private(set) var loading = false
    @Published private(set) var saving = false
    init(app: AppModel, selection: NativeSkillInspectionSelection) { self.app = app; self.selection = selection }
    var current: Bool { app.skillHistory?.id == id && app.selectedID == selection.conversationID && app.selected?.workspacePath == selection.workspace }
    var locked: Bool { loading || saving || app.busy || app.client.turnOutstanding || !current }
    func invalidate() { preview = nil }
    func close() { guard !saving else { return }; invalidate(); if current { app.skillHistory = nil } }
    func refresh() async {
        guard !locked else { return }
        loading = true; preview = nil; error = nil
        defer { loading = false }
        do {
            let raw = try await app.client.request("skill_history_list", selection.parameters)
            try checkSkillHistory(raw, selection: selection, kind: "list")
            guard current, raw["items"].items.count <= 200, raw["limit"] == .number(200), raw["issues"].items.count <= 201 else { throw historyError() }
            entries = try raw["items"].items.map(SkillHistoryEntry.init); issues = raw["issues"].items.map(\.text)
        } catch { if current { self.error = error.localizedDescription } }
    }
    func prepare() async {
        guard !locked else { return }
        loading = true; preview = nil; error = nil
        defer { loading = false }
        do {
            let raw = try await app.client.request("skill_history_preview", selection.parameters)
            try checkSkillHistory(raw, selection: selection, kind: "preview")
            if current { preview = raw; detail = nil }
        } catch { if current { self.error = error.localizedDescription } }
    }
    func inspect(_ entry: SkillHistoryEntry) async {
        guard !locked else { return }
        loading = true; preview = nil; error = nil
        defer { loading = false }
        do {
            var params = selection.parameters; params["record_id"] = .string(entry.id)
            let raw = try await app.client.request("skill_history_inspect", params)
            try checkSkillHistory(raw, selection: selection, kind: "inspect")
            guard raw["record"]["id"] == .string(entry.id), raw["record"]["record_hash"] == entry.raw["record_hash"] else { throw historyError() }
            if current { detail = raw }
        } catch { if current { detail = nil; self.error = error.localizedDescription } }
    }
    func save(token: String, acknowledgement: Bool) async {
        guard !locked, let preview, token == preview["confirmation_token"].text, acknowledgement else { return }
        app.busy = true; saving = true; self.preview = nil; error = nil
        do {
            var params = selection.parameters
            params["preview_fingerprint"] = preview["preview_fingerprint"]; params["confirmation_token"] = .string(token)
            params["acknowledge_history_only"] = .bool(true)
            let raw = try await app.client.request("skill_history_save", params)
            try checkSkillHistory(raw, selection: selection, kind: "saved")
            let entry = try SkillHistoryEntry(raw["record"])
            guard entry.id == preview["preview_fingerprint"].text else { throw historyError() }
            if current { app.status = "История навыка сохранена локально; разрешения не восстановлены" }
        } catch { if current { self.error = "\(error.localizedDescription) Проверьте список перед новым сохранением." } }
        app.busy = false; saving = false
        let failure = error
        if current { await refresh(); error = failure }
    }
}

extension AppModel {
    func openSkillHistory(_ selection: NativeSkillInspectionSelection) async {
        guard !busy, !client.turnOutstanding, selectedID == selection.conversationID, selected?.workspacePath == selection.workspace else { return }
        let model = SkillHistoryModel(app: self, selection: selection); skillHistory = model; await model.refresh()
    }
}
