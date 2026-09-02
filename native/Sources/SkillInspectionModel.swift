import Foundation
import SwiftUI

@MainActor
final class SkillInspectionModel: ObservableObject, Identifiable {
    let id = UUID()
    unowned let app: AppModel
    let selection: NativeSkillInspectionSelection
    @Published private(set) var report: NativeSkillInspection?
    @Published private(set) var error: String?
    @Published private(set) var loading = false
    private var requestID = UUID()

    init(app: AppModel, selection: NativeSkillInspectionSelection) { self.app = app; self.selection = selection }
    var current: Bool { app.selectedID == selection.conversationID && app.selected?.workspacePath == selection.workspace && app.skillInspection?.id == id }
    var locked: Bool { app.busy || app.client.turnOutstanding || loading || !current }

    func refresh() async {
        guard !locked else { return }
        let request = UUID(); requestID = request; loading = true; error = nil
        defer { if requestID == request { loading = false } }
        do {
            let raw = try await app.client.request("skill_inspection", selection.parameters)
            let report = try NativeSkillInspection.decode(raw, selection: selection)
            guard requestID == request, current else { return }
            self.report = report
        } catch {
            guard requestID == request, current else { return }
            report = nil; self.error = error.localizedDescription
        }
    }

    func close() {
        requestID = UUID()
        if app.skillInspection?.id == id { app.skillInspection = nil }
    }

    func openSource() async {
        guard !locked, let source = report?.lifecycle?.sourceLessonId, !source.isEmpty else { return }
        close()
        await app.openMemoryEvidence(recordID: source)
    }

    var canOpenDecision: Bool { !locked && app.selected != nil && app.selected?.archived == false }
    func openDecision() async {
        guard canOpenDecision else { return }
        close()
        await app.openSkillDecision(selection)
    }
}

extension AppModel {
    func openSkillInspection(_ item: LibraryItem) async {
        guard !busy, !client.turnOutstanding, item.store == "skills" else { return }
        let selection = NativeSkillInspectionSelection(conversationID: selectedID, skillID: item.recordId,
                                                       workspace: selected?.workspacePath, expectedSHA256: item.storeSha256)
        let model = SkillInspectionModel(app: self, selection: selection)
        skillInspection = model
        await model.refresh()
    }
}
