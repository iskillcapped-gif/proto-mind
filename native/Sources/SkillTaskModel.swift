import Foundation
import SwiftUI

@MainActor
final class SkillTaskModel: ObservableObject, Identifiable {
    let id = UUID()
    unowned let app: AppModel
    let scope: ProjectMemoryScope
    let skillID: String
    let initialDraft: String
    let initialCriteria: [String]
    @Published var goal: String
    @Published var criteriaText: String
    @Published private(set) var preview: NativeSkillTaskPreview?
    @Published private(set) var error: String?
    @Published private(set) var loading = false
    init(app: AppModel, scope: ProjectMemoryScope, skillID: String) {
        self.app = app; self.scope = scope; self.skillID = skillID
        initialDraft = app.composer; initialCriteria = app.selected?.pendingCriteria ?? []
        goal = initialDraft; criteriaText = initialCriteria.joined(separator: "\n")
    }
    var current: Bool { app.skillTask?.id == id && app.selectedID == scope.conversationID && app.selected?.workspacePath == scope.workspace }
    var locked: Bool { !current || app.busy || app.client.turnOutstanding || loading || app.selected?.archived != false }
    var ready: Bool { !locked && preview?.ready == true && formMatches(preview!.body) }
    private var mode: String { app.fullAccessEnabled ? "full_access" : "chat" }
    private func formMatches(_ body: JSONValue) -> Bool {
        body["goal"] == .string(goal.trimmingCharacters(in: .whitespacesAndNewlines)) &&
        body["success_criteria"]["items"].items.map({ $0["text"].text }) == (try? NativeTaskCriteria.parse(criteriaText)) &&
        body["provider"] == .string(app.selected?.provider ?? "") && body["access_mode"] == .string(mode)
    }
    func invalidate() { preview = nil; error = nil }
    func close() { if app.skillTask?.id == id { app.skillTask = nil } }
    func refresh() async {
        guard !locked else { return }
        loading = true; error = nil; preview = nil
        defer { loading = false }
        do {
            var params = scope.parameters
            params["skill_id"] = .string(skillID)
            params["goal"] = .string(goal.trimmingCharacters(in: .whitespacesAndNewlines))
            params["criteria"] = .array(try NativeTaskCriteria.parse(criteriaText).map(JSONValue.string))
            params["provider"] = .string(app.selected?.provider ?? "mock"); params["access_mode"] = .string(mode)
            let checked = try NativeSkillTaskPreview(await app.client.request("skill_task_preview", params), scope: scope, skillID: skillID)
            guard current, checked.body.isNull || formMatches(checked.body) else { throw skillTaskError() }
            preview = checked
        } catch { if current { self.error = error.localizedDescription } }
    }
    func use(acknowledgement: Bool) {
        guard ready, acknowledgement, let preview else { return }
        do {
            guard app.composer == initialDraft, app.selected?.pendingCriteria == initialCriteria else {
                throw NativeError.message("Основной черновик изменился, пока форма была открыта. Закройте и откройте подготовку заново; чужой текст не заменён.")
            }
            let task = try PreparedSkillTask(preview)
            try app.setPendingCriteria(task.criteria, conversationID: scope.conversationID)
            app.setComposer(task.goal)
            app.preparedSkillTasks[scope.conversationID] = task
            app.invalidateContextPreview(); app.section = .chat
            app.status = "Навык и критерии подготовлены. Отправьте задачу вручную"
            close()
        } catch { self.error = error.localizedDescription }
    }
}

extension AppModel {
    var pendingSkillTask: PreparedSkillTask? { selectedID.flatMap { preparedSkillTasks[$0] } }
    var skillTaskMatchesDraft: Bool {
        guard let task = pendingSkillTask else { return true }
        return task.goal == composer.trimmingCharacters(in: .whitespacesAndNewlines) && task.criteria == selected?.pendingCriteria &&
            task.body["provider"] == .string(selected?.provider ?? "") && task.body["access_mode"] == .string(fullAccessEnabled ? "full_access" : "chat")
    }
    func openSkillTask(skillID: String) async {
        guard !busy, !client.turnOutstanding, let selected, !selected.archived, let workspace = selected.workspacePath else {
            error = "Сначала выберите обычный диалог и его рабочую папку."; return
        }
        let panel = SkillTaskModel(app: self, scope: ProjectMemoryScope(conversationID: selected.id, workspace: workspace), skillID: skillID)
        skillTask = panel; await panel.refresh()
    }
    func removeSkillTask() {
        guard !busy, let selectedID else { return }
        preparedSkillTasks[selectedID] = nil; invalidateContextPreview()
    }
}
