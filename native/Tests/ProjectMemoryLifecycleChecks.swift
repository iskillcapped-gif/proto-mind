import AppKit
import Foundation
import SwiftUI

extension NativeChecks {
    @MainActor
    static func projectMemoryLifecycle(fixture: URL, python: URL, root: URL) async throws {
        let state = root.appendingPathComponent("project-memory-lifecycle-ui")
        let app = AppModel(configuration: LaunchConfiguration(projectRoot: fixture, python: python, stateDirectory: state))
        defer { app.shutdown() }
        await app.start(); app.setProvider("mock"); await app.bindWorkspace(fixture.path); app.flushDraft()
        let core = try fileBytes(fixture), history = try fileBytes(state), messages = app.messages
        await app.openProjectMemory()
        guard let panel = app.projectMemory else { throw NativeError.message("Missing project memory") }
        panel.content = "Server port is 4200."
        await panel.saveDraft()
        guard let original = panel.notes.first, panel.error == nil else { throw NativeError.message(panel.error ?? "Missing saved note") }
        try check(panel.notes.count == 1 && panel.notice != nil && panel.content.isEmpty,
                  "The Save button prepares and saves exactly the edited note without a copied token")
        try check(original.basis == "Добавлено пользователем в память проекта." && app.pendingProjectNotes.isEmpty,
                  "An omitted source is labelled as a manual user note, without inventing evidence or attaching it")
        let saved = try fileBytes(state)
        try check(history.allSatisfy { saved[$0.key] == $0.value } && fileBytes(fixture) == core && app.messages == messages,
                  "Convenient note saving leaves the original history, shared core and conversation unchanged")
        await panel.inspect(original)
        await panel.prepareState("archive")
        guard let preview = panel.statePreview else { throw NativeError.message(panel.error ?? "Missing archive preview") }
        try check(try fileBytes(state) == saved, "Preparing a note state change writes nothing")
        if case .object(let fields) = preview {
            var bad = fields; bad["confirmation_token"] = .string("wrong")
            try outcomeRefused("Note state confirmation is bound to the inspected note and exact ledger") {
                try checkProjectMemory(.object(bad), scope: panel.scope, kind: "state_preview")
            }
            bad = fields; bad["core_mutation_performed"] = .bool(true)
            try outcomeRefused("Note state preview cannot claim core mutation or wider authority") {
                try checkProjectMemory(.object(bad), scope: panel.scope, kind: "state_preview")
            }
        }
        await panel.applyState(acknowledgement: false)
        await panel.changeState("restore")
        try check(try fileBytes(state) == saved, "Missing confirmation or a mismatched action cannot apply a prepared archive")
        let anotherDialog = UUID()
        app.projectNoteSelections[panel.scope.conversationID] = [original]
        app.projectNoteSelections[anotherDialog] = [original]
        await panel.changeState("archive")
        guard panel.error == nil else { throw NativeError.message(panel.error!) }
        let archivedBytes = try fileBytes(state)
        try check(panel.notes.isEmpty && app.projectNoteSelections.values.allSatisfy(\.isEmpty),
                  "Archiving removes the note from current memory and every pending dialog selection")
        try check(saved.allSatisfy { archivedBytes[$0.key] == $0.value } && archivedBytes.count == saved.count + 1,
                  "Archiving appends one content-free event and preserves the original note and history bytes")
        panel.includeHistory = true; panel.query = "4200"; await panel.refresh(recall: true)
        guard let archived = panel.notes.first else { throw NativeError.message(panel.error ?? "Archived note not found") }
        try check(archived.archived && archived.statusTitle == "Убрана из памяти", "History search finds a removed note with an explicit state")
        await panel.inspect(archived); panel.attach(); panel.replaceSelected()
        try check(app.pendingProjectNotes.isEmpty && panel.supersedesID.isEmpty,
                  "An archived note cannot attach or become an active edit without restoration")
        await panel.changeState("restore")
        try check(panel.error == nil && panel.notes == [original] && app.pendingProjectNotes.isEmpty,
                  "Restore makes the original note current without reattaching it or duplicating its content")
        await panel.inspect(original)
        app.projectNoteSelections[panel.scope.conversationID] = [original]
        panel.replaceSelected(); panel.content = "Server port is 4300."
        await panel.saveDraft()
        try check(panel.error == nil && panel.notes.count == 2 && panel.notes.contains { $0.active && $0.content.contains("4300") }
                  && app.pendingProjectNotes.isEmpty && panel.query.isEmpty, "Saving an edit replaces the current version and clears stale pending selections and search")
        panel.query = ""; panel.includeHistory = false; await panel.refresh()
        guard let current = panel.notes.first else { throw NativeError.message("Missing corrected note") }
        await panel.inspect(current); await panel.prepareState("archive")
        let beforeStale = try fileBytes(state)
        // Another explicit writer changes the ledger between preview and Apply.
        let other = AppModel(configuration: app.client.configuration)
        defer { other.shutdown() }
        await other.openProjectMemory()
        other.projectMemory?.content = "A second independently saved note."
        await other.projectMemory?.saveDraft()
        guard other.projectMemory?.error == nil else { throw NativeError.message(other.projectMemory!.error!) }
        let concurrent = try fileBytes(state)
        await panel.applyState(acknowledgement: true)
        try check(panel.error != nil && fileBytes(state) == concurrent && concurrent.count == beforeStale.count + 1,
                  "A concurrent note save invalidates an archive preview without applying stale state")
        other.projectMemory?.close()
        await panel.refresh()
        try check(panel.notes.contains { $0.id == current.id && $0.active }, "A refused stale action leaves the current note available")
        let restart = AppModel(configuration: app.client.configuration)
        defer { restart.shutdown() }
        await restart.openProjectMemory()
        try check(restart.projectMemory?.notes == panel.notes && restart.pendingProjectNotes.isEmpty,
                  "Corrected notes and lifecycle state survive restart while pending selections stay temporary")
        try check(!app.cloudConsent && !app.fullAccessEnabled && fileBytes(fixture) == core && app.messages == messages,
                  "Memory lifecycle never calls a provider, widens access, or changes the shared core or conversation")
    }
}
