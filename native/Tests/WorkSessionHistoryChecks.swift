import AppKit
import Foundation
import SwiftUI

extension NativeChecks {
    static func workSessionPageContracts(_ value: JSONValue, conversation: UUID, project: URL) throws {
        let first = try NativeWorkSessionPage(value, conversation: conversation, project: project)
        try check(first.runs.count == 30 && first.total == 66 && first.nextCursor != nil,
                  "Journal page validates its bounded records, total and scoped continuation cursor")
        guard case .object(let fields) = value, case .object(let cursorFields) = value["next_cursor"] else {
            throw NativeError.message("Expected journal page fixture")
        }
        var variants: [(String, JSONValue)] = [
            ("conversation_id", .string(UUID().uuidString.lowercased())), ("project_root", .string("/other-project")),
            ("read_only", .bool(false)), ("total", .bool(true)), ("total", .number(0)),
            ("partial", .bool(false)), ("cursor", value["next_cursor"]), ("path", .string("relative")),
            ("warnings", .array([.number(1)])), ("runs", .array([])),
            ("runs", .array(Array(value["runs"].items.reversed()))),
            ("runs", .array([value["runs"].items[0], value["runs"].items[0]])),
        ]
        for (key, replacement) in [("run_id", JSONValue.string(UUID().uuidString.lowercased())),
                                   ("conversation_id", .string(UUID().uuidString.lowercased())),
                                   ("project_root", .string("/other-project")), ("created_at", .string(""))] {
            var bad = cursorFields; bad[key] = replacement
            variants.append(("next_cursor", .object(bad)))
        }
        for (key, replacement) in variants {
            var bad = fields; bad[key] = replacement
            var refused = false
            do { _ = try NativeWorkSessionPage(.object(bad), conversation: conversation, project: project) }
            catch { refused = true }
            try check(refused, "Journal rejects malformed or cross-scope \(key)")
        }
        var replay = fields; replay["cursor"] = value["next_cursor"]
        var refused = false
        do { _ = try NativeWorkSessionPage(.object(replay), conversation: conversation, project: project, cursor: value["next_cursor"]) }
        catch { refused = true }
        try check(refused, "Journal rejects a page that replays records at or newer than its incoming boundary")
    }

    @MainActor
    static func workSessionHistoryIntegration(fixture: URL, python: URL, state sourceState: URL) async throws {
        let state = sourceState.deletingLastPathComponent().appendingPathComponent("work-session-history-state")
        try FileManager.default.copyItem(at: sourceState, to: state)
        let archive = try ChatStore(directory: state).load()
        guard let chat = archive.conversations.first, let assistant = chat.messages.last,
              let reference = assistant.turnReference else { throw NativeError.message("Missing old linked turn fixture") }
        let runID = reference["run_id"].text
        let journal = state.appendingPathComponent("work_sessions")
        let originalURL = journal.appendingPathComponent(runID + ".json")
        let original = try Data(contentsOf: originalURL)
        guard case .object(let fields) = try JSONDecoder().decode(JSONValue.self, from: original) else {
            throw NativeError.message("Expected synthetic work session")
        }
        // Newer independent historical records push the exact linked turn off page one.
        // No fabricated message lineage is attached to these copied fixtures.
        for _ in 0..<65 {
            var row = fields
            let id = UUID().uuidString.lowercased()
            row["id"] = .string(id); row["created_at"] = .string("2099-01-01T00:00:00.000000Z")
            row["turn_receipt"] = nil; row["artifact_snapshot"] = nil
            try JSONEncoder().encode(JSONValue.object(row)).write(to: journal.appendingPathComponent(id + ".json"))
        }
        let before = try fileBytes(state), projectBefore = try fileBytes(fixture), journalBefore = try fileBytes(journal)
        let app = AppModel(configuration: LaunchConfiguration(projectRoot: fixture, python: python, stateDirectory: state))
        defer { app.shutdown() }
        await app.start()
        try check(app.workSessions.count == 30 && app.workSessionsTotal == 66 && app.workSessionsWarning == nil
                  && !app.workSessions.contains(where: { $0.id == runID }),
                  "Native starts with the newest 30 of 66 runs and exposes older pages")
        let rawPage = try await app.client.request("work_sessions", ["conversation_id": .string(chat.id.uuidString)])
        try workSessionPageContracts(rawPage, conversation: chat.id, project: fixture)
        await app.loadMoreWorkSessions()
        try check(app.workSessions.count == 60 && app.workSessionsNextCursor != nil,
                  "Load earlier appends the second page without replacing visible runs")
        await app.loadMoreWorkSessions()
        try check(app.workSessions.count == 66 && app.workSessionsNextCursor == nil
                  && Set(app.workSessions.map(\.id)).count == 66 && app.workSessions.last?.id == runID,
                  "Paging reaches every unique old run and stops at the end of history")
        await app.loadMoreWorkSessions()
        try check(app.workSessions.count == 66 && !app.loadingWorkSessions && (try fileBytes(state)) == before,
                  "Complete journal browsing and redundant Load earlier preserve every private byte")

        await app.refreshWorkSessions()
        try check(app.workSessions.count == 30, "Refresh returns to the first journal page")
        await app.openWorkSession(for: assistant)
        try check(app.showWorkSessions && app.inspectedWorkSessionID == runID && app.workSessions.count == 31,
                  "An old message opens its exact run directly beyond the first 30 records")
        await app.refreshWorkSessions()
        try check(app.workSessions.count == 31 && app.workSessions.contains(where: { $0.id == runID }),
                  "Opening or refreshing the sheet retains freshly validated selected old evidence")
        await app.loadMoreWorkSessions()
        await app.loadMoreWorkSessions()
        try check(app.workSessions.count == 66 && Set(app.workSessions.map(\.id)).count == 66,
                  "Direct old-run lookup does not skip or duplicate records during later paging")

        app.showWorkSessions = false; app.inspectedWorkSessionID = nil
        await app.refreshWorkSessions()
        await app.openSessionSpine(for: assistant)
        guard let preview = app.sessionSpinePreview else { throw NativeError.message(app.error ?? "Missing old Session Spine preview") }
        try check(preview.source["run_id"].text == runID && preview.value["no_write"].flag,
                  "Session Spine opens exact old message evidence outside the visible journal page")
        await app.refreshWorkSessions()
        app.openSessionSpineReadiness(preview)
        try check(app.sessionSpineReadiness?.state == "INACTIVE" && app.sessionSpineReadiness?.canArm == true,
                  "Refreshing a historical selection preserves exact Session Spine readiness context")
        let size = NSHostingController(rootView: WorkSessionsView(model: app)).sizeThatFits(in: CGSize(width: 1000, height: 800))
        try check(size.width <= 850 && size.height <= 660,
                  "Paginated history stays within its scrollable Native sheet")
        try check((try fileBytes(state)) == before && (try fileBytes(fixture)) == projectBefore,
                  "Old-link inspection, pages and readiness change no files or invoke a provider")

        var changedMessage = assistant; changedMessage.text = "changed synthetic answer"
        app.showWorkSessions = false; app.error = nil
        await app.openWorkSession(for: changedMessage)
        try check(!app.showWorkSessions && app.error != nil,
                  "An edited message cannot reuse another exact turn reference")
        let hiddenURL = journal.appendingPathComponent(runID + ".saved")
        try FileManager.default.moveItem(at: originalURL, to: hiddenURL)
        defer { if FileManager.default.fileExists(atPath: hiddenURL.path) { try? FileManager.default.moveItem(at: hiddenURL, to: originalURL) } }
        app.error = nil
        await app.openWorkSession(for: assistant)
        try check(!app.showWorkSessions && app.error != nil,
                  "Missing old evidence is refused despite a previously cached run and many neighbours")
        await app.openSessionSpine(for: assistant)
        try check(app.sessionSpinePreview == nil && app.error != nil,
                  "Session Spine refuses a disappeared old source rather than choosing a nearby run")
        try FileManager.default.moveItem(at: hiddenURL, to: originalURL)

        app.inspectedWorkSessionID = nil
        await app.refreshWorkSessions()
        let pending = Task { @MainActor in await app.loadMoreWorkSessions() }
        // Yield until the read has entered its asynchronous bridge request.
        for _ in 0..<100 where !app.loadingWorkSessions { await Task.yield() }
        try check(app.loadingWorkSessions, "Conversation-switch fixture has a journal page in flight")
        app.newConversation()
        await pending.value
        try check(app.selectedID != chat.id && app.workSessions.isEmpty && app.workSessionsTotal == nil
                  && app.workSessionsNextCursor == nil && !app.loadingWorkSessions && app.inspectedWorkSessionID == nil,
                  "Changing conversation discards old pagination state and its late bridge response")
        await app.refreshWorkSessions()
        try check(app.workSessions.isEmpty && app.workSessionsTotal == 0 && app.workSessionsNextCursor == nil,
                  "A new conversation never inherits another conversation's old runs")
        try check((try fileBytes(journal)) == journalBefore
                  && (try fileBytes(fixture)) == projectBefore,
                  "Conversation switching preserves all journal and project evidence")
    }
}
