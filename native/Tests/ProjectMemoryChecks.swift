import AppKit
import Foundation
import SwiftUI

extension NativeChecks {
    @MainActor
    static func projectMemory(fixture: URL, python: URL, root: URL) async throws {
        let state = root.appendingPathComponent("project-memory-ui")
        let app = AppModel(configuration: LaunchConfiguration(projectRoot: fixture, python: python, stateDirectory: state))
        defer { app.client.shutdown() }
        await app.start(); app.setProvider("mock"); await app.bindWorkspace(fixture.path); app.flushDraft()
        let core = try fileBytes(fixture), initial = try fileBytes(state), messages = app.messages
        await app.openProjectMemory()
        guard let panel = app.projectMemory else { throw NativeError.message("Project memory did not open") }
        try check(panel.notes.isEmpty && panel.error == nil && panel.issues.isEmpty, "Project memory opens with a missing private ledger without initializing it")
        let hosting = NSHostingController(rootView: ProjectMemoryView(model: panel))
        let size = hosting.sizeThatFits(in: CGSize(width: 860, height: 750))
        try check(size.width <= 851 && size.height <= 741, "Project memory fits a bounded scrollable Native sheet")
        panel.content = "Use copper colors in this project."
        panel.basis = "Operator-provided synthetic requirement."
        await panel.prepare()
        guard let preview = panel.preview else { throw NativeError.message(panel.error ?? "Project note preview missing") }
        try check(preview["body"]["source"] == .string("operator_explicit") && preview["body"]["executable"] == .bool(false), "Project note preview distinguishes an operator assertion from verified knowledge or authority")
        if case .object(let raw) = preview {
            for key in ["core_mutation_performed", "automatic_recall", "model_call_performed", "legacy_memory_migrated"] {
                var invalid = raw; invalid[key] = .bool(true)
                try outcomeRefused("Project memory refuses widened \(key)") { try checkProjectMemory(.object(invalid), scope: panel.scope, kind: "preview") }
            }
            var invalid = raw; invalid["confirmation_token"] = .string("SAVE-PROJECT-MEMORY-AAAAAAAAAAAA")
            try outcomeRefused("Project memory independently binds the exact token to the selected content and ledger") { try checkProjectMemory(.object(invalid), scope: panel.scope, kind: "preview") }
        }
        await panel.save(token: "wrong", acknowledgement: true)
        await panel.save(token: preview["confirmation_token"].text, acknowledgement: false)
        try check(try fileBytes(fixture) == core && fileBytes(state) == initial && app.messages == messages, "Project preview and incomplete confirmation are read-only and do not send a turn")
        await panel.save(token: preview["confirmation_token"].text, acknowledgement: true)
        guard panel.error == nil, let note = panel.notes.first else { throw NativeError.message(panel.error ?? "Saved note missing") }
        let saved = try fileBytes(state)
        try check(panel.notes.count == 1 && initial.allSatisfy { saved[$0.key] == $0.value }
                  && Set(saved.keys).subtracting(initial.keys).allSatisfy({ $0.contains("project_memory/") }), "Explicit save adds only one immutable project-memory note and its cooperative lock")
        try check(try fileBytes(fixture) == core && app.messages == messages && app.pendingProjectNotes.isEmpty, "Saving project knowledge neither changes shared core memory nor auto-attaches it")
        await panel.inspect(note)
        try check(panel.detail == note && panel.error == nil, "Native independently verifies the saved record hash before attachment")
        panel.attach()
        try check(app.pendingProjectNotes == [note] && app.projectMemory == nil && app.messages == messages, "Explicit attachment only selects the note for a future manual Send")
        try check(try fileBytes(state) == saved && fileBytes(fixture) == core, "Project-note attachment is ephemeral and does not write chat or stores")
        app.setComposer("Explain the selected project context."); app.flushDraft()
        await app.refreshContextPreview()
        try check(app.contextPreview?.value["project_memory_sources"].items.first?["content"] == note.raw["content"]
                  && app.contextPreview?.manifest["knowledge_context"]["permission_granted"] == .bool(false), "Pre-send context desk shows exactly selected project notes without changing permissions")
        let restart = AppModel(configuration: app.client.configuration)
        defer { restart.client.shutdown() }
        await restart.openProjectMemory()
        try check(restart.projectMemory?.notes == [note] && restart.pendingProjectNotes.isEmpty && !restart.fullAccessEnabled && !restart.cloudConsent,
                  "Project memory survives restart but pending note selection and execution authority do not")
        restart.projectMemory?.close()
        await app.submit("/commands status")
        try check(app.pendingProjectNotes == [note] && app.messages.last?.role == "report", "Slash routes ignore and preserve selected project notes")
        await app.submit("Explain the selected project context.")
        await app.refreshWorkSessions()
        let run = app.workSessions.first { $0.value["context_manifest"]["knowledge_context"]["project_memory"].items.first?["id"] == .string(note.id) }
        try check(app.messages.last?.isError == false && app.pendingProjectNotes.isEmpty && run != nil,
                  "Manual normal Send consumes explicit notes and records content-free project provenance")
        try check(run?.value["verification"] == .string("not_assessed") && app.messages.last?.notices.contains(where: { $0.contains("Mock does not analyze") }) == true,
                  "A mock reply is never mistaken for verified note understanding or task acceptance")
        await app.openProjectMemory()
        guard let updating = app.projectMemory, let first = updating.notes.first else { throw NativeError.message("Project note missing for supersession") }
        await updating.inspect(first); updating.replaceSelected()
        updating.content = "Use teal colors in this project."; updating.basis = "Operator correction in the fixture."
        await updating.prepare()
        guard let replacement = updating.preview else { throw NativeError.message(updating.error ?? "Missing replacement preview") }
        await updating.save(token: replacement["confirmation_token"].text, acknowledgement: true)
        try check(updating.error == nil && updating.notes.count == 1 && updating.notes[0].content.contains("teal"), "A replacement is a new immutable current note, not an edit of historical bytes")
        updating.includeHistory = true; await updating.refresh()
        try check(updating.notes.count == 2 && updating.notes.contains(where: { $0.id == note.id && !$0.active }), "Historical project notes remain inspectable after explicit replacement")
        updating.query = "teal"; await updating.refresh(recall: true)
        try check(updating.notes.count == 1 && updating.notes.first?.content.contains("teal") == true, "Local recall uses deterministic token matching without an LLM")
        await updating.inspect(updating.notes[0]); updating.attach()
        let other = root.appendingPathComponent("another-workspace")
        try FileManager.default.createDirectory(at: other, withIntermediateDirectories: true)
        await app.bindWorkspace(other.path); await app.openProjectMemory()
        try check(app.pendingProjectNotes.isEmpty && app.projectMemory?.notes.isEmpty == true, "Changing projects clears selected notes and never migrates knowledge by guesswork")
        app.projectMemory?.close()
        try check(!app.fullAccessEnabled && !app.cloudConsent && !app.bootstrap["context_injection"].flag, "Project-memory workflow never enables tools, cloud processing or Context Injection")
    }
}
