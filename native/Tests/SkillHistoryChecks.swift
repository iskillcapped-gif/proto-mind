import AppKit
import Foundation
import SwiftUI

extension NativeChecks {
    @MainActor
    static func skillHistory(app: AppModel, item: LibraryItem, project: URL, state: URL, minimumReceipts: Int) async throws {
        let coreBefore = try fileBytes(project), privateBefore = try fileBytes(state)
        let selection = NativeSkillInspectionSelection(conversationID: app.selectedID, skillID: item.recordId, workspace: app.selected?.workspacePath, expectedSHA256: "")
        await app.openSkillHistory(selection)
        guard let model = app.skillHistory else { throw NativeError.message("Missing learning history") }
        let countBefore = model.entries.count
        try check(model.error == nil && model.preview == nil && !app.fullAccessEnabled && !app.cloudConsent, "History opens without capture, consent, file write or permission")
        let hosting = NSHostingController(rootView: SkillHistoryView(model: model))
        let fitted = hosting.sizeThatFits(in: CGSize(width: 860, height: 730))
        try check(fitted.width <= 851 && fitted.height <= 721, "Learning history fits a bounded scrollable sheet")
        await model.prepare()
        guard let preview = model.preview else { throw NativeError.message(model.error ?? "Missing history preview") }
        try check(preview["receipt_count"].integer >= minimumReceipts && preview["body"]["historical_only"].flag && !preview["body"]["authority_restored"].flag, "History keeps the available original receipts without making them live authority")
        if case .object(let raw) = preview {
            for field in ["core_mutation_performed", "authority_restored", "model_call_performed", "execute"] {
                var invalid = raw; invalid[field] = .bool(true)
                try outcomeRefused("History rejects widened \(field)") { try checkSkillHistory(.object(invalid), selection: selection, kind: "preview") }
            }
            var invalid = raw; invalid["confirmation_token"] = .string("SAVE-SKILL-HISTORY-AAAAAAAAAAAA")
            try outcomeRefused("History binds its token to the exact snapshot") { try checkSkillHistory(.object(invalid), selection: selection, kind: "preview") }
        }
        await model.save(token: "WRONG", acknowledgement: true)
        await model.save(token: preview["confirmation_token"].text, acknowledgement: false)
        try check(try fileBytes(project) == coreBefore && fileBytes(state) == privateBefore, "History review and incomplete confirmation are byte-stable")
        await model.save(token: preview["confirmation_token"].text, acknowledgement: true)
        guard model.error == nil, let entry = model.entries.first(where: { $0.id == preview["preview_fingerprint"].text }) else { throw NativeError.message(model.error ?? "Missing saved history") }
        try check(model.entries.count == countBefore + 1 && (try fileBytes(project)) == coreBefore, "Explicit save appends exactly one historical snapshot without core changes")
        let savedBytes = try fileBytes(state)
        try check(privateBefore.allSatisfy { savedBytes[$0.key] == $0.value }, "Saving history never rewrites any previous private record")
        await model.inspect(entry)
        try check(model.detail?["integrity"] == .string("VERIFIED") && model.detail?["record"]["body"]["receipts"] == preview["body"]["receipts"], "Saved full original receipts verify and remain readable")
        await model.prepare()
        guard let repeated = model.preview else { throw NativeError.message(model.error ?? "Missing repeated preview") }
        await model.save(token: repeated["confirmation_token"].text, acknowledgement: true)
        try check(try fileBytes(state) == savedBytes && model.entries.count == countBefore + 1, "Identical history save is idempotent and byte-stable")
        model.close()
        let restart = AppModel(configuration: app.client.configuration)
        defer { restart.client.shutdown() }
        await restart.openSkillHistory(selection)
        guard let history = restart.skillHistory else { throw NativeError.message("Missing history after restart") }
        await history.inspect(entry)
        try check(history.detail?["integrity"] == .string("VERIFIED") && history.detail?["authority_restored"] == .bool(false), "History survives bridge restart without reloading old authority")
        let outcome = try await restart.client.request("skill_outcome_review", selection.parameters)
        try check(outcome["pilot_state"] == .string("not_started") && outcome["receipts"].items.isEmpty, "Historical outcomes do not hydrate live consent/capture sessions")
        history.close()
        try check(try fileBytes(project) == coreBefore && fileBytes(state) == savedBytes, "Reading historical evidence after restart is fully read-only")
    }
}
