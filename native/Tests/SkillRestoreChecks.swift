import AppKit
import Foundation
import SwiftUI

extension NativeChecks {
    @MainActor
    static func skillRestore(configuration: LaunchConfiguration, item: LibraryItem, project: URL, state: URL) async throws {
        let app = AppModel(configuration: configuration)
        defer { app.client.shutdown() }
        let before = try fileBytes(project), privateBefore = try fileBytes(state)
        let selection = NativeSkillInspectionSelection(conversationID: app.selectedID, skillID: item.recordId, workspace: app.selected?.workspacePath, expectedSHA256: "")
        await app.openSkillRestore(selection)
        guard let model = app.skillRestore, let report = model.report else { throw NativeError.message(app.skillRestore?.error ?? "Missing restore review") }
        try check(report.ready && model.preview == nil && report.receipt == nil, "Restart can review verified archive without restoring consent or a prior token")
        let hosting = NSHostingController(rootView: SkillRestoreView(model: model))
        let fitted = hosting.sizeThatFits(in: CGSize(width: 860, height: 730))
        try check(fitted.width <= 851 && fitted.height <= 721 && fitted.height >= 600, "Restore fits the bounded scrollable sheet")
        if case .object(let data) = report.raw {
            for field in ["read_only", "no_execution", "store_mutation_performed", "model_call_performed", "permissions_changed", "execute"] {
                var invalid = data; invalid[field] = .bool(!data[field, default: .bool(false)].flag)
                try outcomeRefused("Restore rejects widened \(field)") { _ = try NativeSkillRestoreReview.decode(.object(invalid), selection: selection) }
            }
        }
        await model.prepare()
        guard let preview = model.preview, preview.ready else { throw NativeError.message(model.error ?? "Missing restore preview") }
        try check(preview.token.hasPrefix("CONFIRM-DURABLE-SKILL-RESTORE-") && !preview.accepts(preview.token, acknowledgement: false), "Restoration needs exact independent token and shared-library acknowledgement")
        if case .object(let raw) = preview.raw {
            var changed = raw; changed["confirmation_token"] = .string("CONFIRM-DURABLE-SKILL-RESTORE-AAAAAAAAAAAA")
            try outcomeRefused("Restore token is cryptographically bound") { _ = try NativeSkillRestorePreview.decode(.object(changed), selection: selection) }
            changed = raw; changed["expected_changed_fields"] = .array([.string("body")])
            try outcomeRefused("Restore cannot edit the procedure") { _ = try NativeSkillRestorePreview.decode(.object(changed), selection: selection) }
        }
        await model.confirm(token: "WRONG", acknowledgement: true)
        await model.confirm(token: preview.token, acknowledgement: false)
        try check(try fileBytes(project) == before && fileBytes(state) == privateBefore, "Wrong or incomplete confirmation writes no files")
        await model.refresh()
        try check(model.preview == nil && model.result == nil, "Refresh discards pending authority without restoring")
        await model.prepare()
        guard let exact = model.preview else { throw NativeError.message(model.error ?? "Missing second preview") }
        await model.confirm(token: exact.token, acknowledgement: true)
        guard let receipt = model.result, let refreshed = model.report?.receipt else { throw NativeError.message(model.error ?? "Missing restore receipt") }
        try check(receipt.verification == "VERIFIED" && receipt.current && refreshed.id == receipt.id, "Native verifies the actual core restore receipt and current record")
        let after = try fileBytes(project)
        let changed = before.keys.filter { before[$0] != after[$0] }.map { URL(fileURLWithPath: $0).resolvingSymlinksInPath().path }
        try check(Set(before.keys) == Set(after.keys) && changed == [project.appendingPathComponent("proto_mind/data/skills.jsonl").resolvingSymlinksInPath().path], "Restore changes exactly the Skill Library, never other stores/exports")
        try check(try fileBytes(state) == privateBefore && !app.cloudConsent && !app.fullAccessEnabled, "Restore cannot change private history or model/computer permissions")
        try check(!model.canPrepare && model.report?.status == "RESTORED", "A successful restore cannot be replayed")
        if case .object(let raw) = receipt.raw {
            var invalid = raw; invalid["receipt_hash"] = .string(String(repeating: "0", count: 64))
            try outcomeRefused("Receipt tampering cannot be shown as verified") { _ = try NativeSkillRestoreReceipt.decode(.object(invalid), selection: selection) }
        }
        await model.openEvidence()
        try check(app.skillInspection?.report?.lifecycle?.state == .activeRestoredVerified, "Inspector proves the restored durable lifecycle")
        app.skillInspection?.close()
        let restart = AppModel(configuration: configuration)
        defer { restart.client.shutdown() }
        await restart.openSkillRestore(selection)
        try check(restart.skillRestore?.report?.receipt == nil && restart.skillRestore?.report?.ready == false, "Restart never recreates the detailed receipt or restoration authority")
        await restart.skillRestore?.openEvidence()
        try check(restart.skillInspection?.report?.outcome?.status == "NEEDS_POST_RESTORE_EVIDENCE", "Restoration is not invented fresh successful use")
        restart.skillInspection?.close()
        try check(try fileBytes(project) == after && fileBytes(state) == privateBefore, "Restoration inspection and restart reads preserve exact bytes")
        try await skillHistory(app: app, item: item, project: project, state: state, minimumReceipts: 1)
    }
}
