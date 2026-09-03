import Foundation
import SwiftUI

@MainActor
final class MemorySuggestionModel: ObservableObject, Identifiable {
    let id = UUID()
    unowned let app: AppModel
    let scope: ProjectMemoryScope
    let report: MemorySuggestionsReport
    let suggestion: MemorySuggestion
    let sourceText: String
    let quote: String
    @Published private(set) var preview: JSONValue?
    @Published private(set) var error: String?
    @Published private(set) var loading = false
    @Published private(set) var saving = false
    @Published private(set) var saved: ProjectNote?

    init(app: AppModel, scope: ProjectMemoryScope, report: MemorySuggestionsReport, suggestion: MemorySuggestion, text: String) throws {
        guard report.items.contains(suggestion), UUID(uuidString: report.source["conversation_id"].text) == scope.conversationID,
              scope.matches(report.source["workspace"]) else { throw memorySuggestionError() }
        _ = try MemorySuggestionsReport(report.value, text: text)
        self.app = app; self.scope = scope; self.report = report; self.suggestion = suggestion; sourceText = text
        quote = try suggestion.quote(in: text)
    }
    var current: Bool { app.memorySuggestion?.id == id && app.selectedID == scope.conversationID && app.selected?.workspacePath == scope.workspace }
    var locked: Bool { !current || app.busy || app.client.turnOutstanding || loading || saving || app.selected?.archived == true }
    var parameters: [String: JSONValue] {
        scope.parameters.merging(["run": report.reference, "text": .string(sourceText), "candidate_id": .string(suggestion.id)]) { _, right in right }
    }
    func close() { guard !saving else { return }; if current { app.memorySuggestion = nil } }
    func prepare() async {
        guard !locked, saved == nil else { return }
        loading = true; preview = nil; error = nil
        defer { loading = false }
        do {
            let result = try await app.client.request("memory_suggestion_preview", parameters)
            guard current, case .object(let fields) = result,
                  Set(fields.keys) == ["schema", "source", "candidate", "note_preview", "read_only", "automatic_save", "model_call_performed", "permission_granted"],
                  result["schema"] == .string("proto_mind.native_memory_suggestion_review.v1"),
                  result["source"] == report.source, result["candidate"] == suggestion.value, result["read_only"] == .bool(true),
                  ["automatic_save", "model_call_performed", "permission_granted"].allSatisfy({ result[$0] == .bool(false) }) else { throw memorySuggestionError() }
            let preview = result["note_preview"]
            try checkProjectMemory(preview, scope: scope, kind: "preview")
            let body = preview["body"]
            guard body["content"] == .string(quote), body["kind"] == .string(suggestion.kind), body["supersedes_id"] == .string(""),
                  suggestionTextHash(body["content"].text) == suggestion.value["content_sha256"].text,
                  body["workspace"] == report.source["workspace"],
                  body["basis"].text.contains(report.source["run_id"].text), body["basis"].text.contains(report.source["input_sha256"].text),
                  URL(fileURLWithPath: body["project_root"].text).resolvingSymlinksInPath() == app.client.configuration.projectRoot.resolvingSymlinksInPath() else { throw memorySuggestionError() }
            self.preview = preview
        } catch { if current { self.error = error.localizedDescription } }
    }
    func save(acknowledgement: Bool) async {
        guard !locked, saved == nil, acknowledgement, let preview else { return }
        app.busy = true; saving = true; self.preview = nil; error = nil
        defer { app.busy = false; saving = false }
        do {
            var params = parameters
            params["preview_fingerprint"] = preview["preview_fingerprint"]
            params["confirmation_token"] = preview["confirmation_token"]
            params["acknowledge_operator_note"] = .bool(true)
            let result = try await app.client.request("memory_suggestion_save", params)
            try checkProjectMemory(result, scope: scope, kind: "saved")
            let note = try ProjectNote(result["item"])
            guard ["content", "kind", "basis", "supersedes_id"].allSatisfy({ note.raw[$0] == preview["body"][$0] }) else { throw memorySuggestionError() }
            if current {
                saved = note; app.reviewedMemorySuggestions.insert(suggestion.id)
                app.invalidateContextPreview()
                app.status = "Заметка сохранена для этой папки; отдельного запроса модели не было"
            }
        } catch { if current { self.error = "\(error.localizedDescription) Перед повтором проверьте заметки проекта." } }
    }
}

extension AppModel {
    func memorySuggestions(for message: ChatMessage) -> (MemorySuggestionsReport, String)? {
        guard message.role == "assistant", !message.isError, let value = message.memorySuggestions,
              let id = message.memorySuggestionSourceID, let source = messages.first(where: { $0.id == id }),
              source.role == "user", !source.isError, source.operatorInput != true,
              let report = try? MemorySuggestionsReport(value, text: source.text) else { return nil }
        return (report, source.text)
    }
    func openMemorySuggestion(_ suggestion: MemorySuggestion, report: MemorySuggestionsReport, text: String) async {
        guard !busy, !client.turnOutstanding, let selected, !selected.archived, let workspace = selected.workspacePath else { return }
        do {
            let panel = try MemorySuggestionModel(app: self, scope: ProjectMemoryScope(conversationID: selected.id, workspace: workspace),
                                                 report: report, suggestion: suggestion, text: text)
            memorySuggestion = panel; await panel.prepare()
        } catch { self.error = error.localizedDescription }
    }
}
