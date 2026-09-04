import AppKit
import Foundation
import SwiftUI

extension NativeChecks {
    @MainActor
    static func sessionSpineLiveIntegration(fixture: URL, python: URL, state: URL) async throws {
        let before = try fileBytes(state)
        let app = AppModel(configuration: LaunchConfiguration(projectRoot: fixture, python: python, stateDirectory: state))
        defer { app.client.shutdown() }
        let messagesBefore = app.messages
        await app.start()
        guard app.messages.count == 2, let source = app.messages.first, let assistant = app.messages.last,
              let rawReference = assistant.turnReference else {
            throw NativeError.message("Synthetic Session Spine history did not load")
        }
        let reference = try NativeTurnReference(rawReference)
        let run = try reference.resolve(in: app.workSessions, conversation: app.selectedID!)
        await app.openSessionSpine(for: assistant)
        guard let preview = app.sessionSpinePreview else {
            throw NativeError.message(app.error ?? "Live Session Spine preview missing")
        }
        try check(preview.value["read_only"].flag && preview.value["no_write"].flag
                  && preview.value["no_model_call"].flag && preview.value["no_command_execution"].flag,
                  "Live Session Spine opens as a read-only no-execution projection")
        try check(preview.source["run_id"].text == run.id && preview.events.count == preview.projection["spine"]["event_count"].integer
                  && preview.events.filter(\.surfaceVisible).map(\.seq) == preview.projection["spine"]["surface_nodes"].items.map(\.integer),
                  "Live Session Spine preserves exact run and folded-surface parity")
        try check(!preview.value.pretty.contains(source.text) && !preview.value.pretty.contains(assistant.raw),
                  "Live preview returns content-free event metadata rather than duplicate message text")
        try check(preview.events.allSatisfy { $0.type != "tool/result" || $0.value["tool_kind"].text.isEmpty == false }
                  && preview.value["no_tool_replay"].flag,
                  "Live Session Spine exposes bounded evidence metadata without replay authority")
        let size = NSHostingController(rootView: SessionSpinePreviewView(model: app, preview: preview))
            .sizeThatFits(in: CGSize(width: 900, height: 760))
        try check(size.width <= 800 && size.height <= 700,
                  "Live Session Spine stays inside a bounded scrollable Native sheet")

        guard case .object(var changed) = preview.value else { throw NativeError.message("Expected Session Spine object") }
        changed["no_write"] = .bool(false)
        var wideningRefused = false
        do {
            _ = try NativeSessionSpinePreview(
                .object(changed), source: source, assistant: assistant, conversation: app.selectedID!, reference: reference, run: run
            )
        } catch { wideningRefused = true }
        try check(wideningRefused, "Native rejects a Session Spine preview that claims write authority")

        guard case .object(var nestedChanged) = preview.value,
              case .object(var projectionFields) = nestedChanged["projection"] else {
            throw NativeError.message("Expected closed Session Spine projection")
        }
        projectionFields["private_text"] = .string("must not cross the preview boundary")
        nestedChanged["projection"] = .object(projectionFields)
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys, .withoutEscapingSlashes]
        let hashMaterial = JSONValue.object(nestedChanged.filter { $0.key != "preview_hash" })
        let encoded = try encoder.encode(hashMaterial)
        guard let canonical = String(data: encoded, encoding: .utf8) else {
            throw NativeError.message("Could not encode Session Spine fixture")
        }
        nestedChanged["preview_hash"] = .string(NativeTurnReceipt.hash(canonical))
        var nestedWideningRefused = false
        do {
            _ = try NativeSessionSpinePreview(
                .object(nestedChanged), source: source, assistant: assistant,
                conversation: app.selectedID!, reference: reference, run: run
            )
        } catch { nestedWideningRefused = true }
        try check(nestedWideningRefused,
                  "Native rejects a self-hashed preview that widens the closed nested projection")

        await app.openSessionSpine(for: assistant)
        try check(app.sessionSpinePreview?.value == preview.value,
                  "Repeated read-only preview is deterministic for unchanged exact evidence")

        app.openSessionSpineReadiness(preview)
        guard let inactive = app.sessionSpineReadiness else {
            throw NativeError.message(app.error ?? "Session Spine readiness missing")
        }
        try check(inactive.state == "INACTIVE" && inactive.identityState == "missing"
                  && inactive.recoveryState == "clean_uninitialized" && inactive.canArm,
                  "Missing pilot identity is a clean uninitialized state, not inferred recovery evidence")
        try check(inactive.value["read_only"].flag && inactive.value["no_write"].flag
                  && !inactive.value["writer_active"].flag && !inactive.value["write_authority_granted"].flag
                  && !inactive.value["legacy_backfill_allowed"].flag,
                  "Readiness keeps the writer, authority, migration and legacy backfill disabled")
        try check(!FileManager.default.fileExists(atPath: inactive.identityPath)
                  && !inactive.value.pretty.contains(source.text) && !inactive.value.pretty.contains(assistant.raw),
                  "Readiness inspection creates no identity and returns content-free evidence")
        let candidate = inactive.candidateHash
        app.openSessionSpineReadiness(preview)
        try check(app.sessionSpineReadiness?.candidateHash == candidate,
                  "Unchanged exact evidence produces one deterministic readiness candidate")

        app.armSessionSpinePilot(candidateHash: candidate)
        guard let armed = app.sessionSpineReadiness else {
            throw NativeError.message(app.error ?? "Armed Session Spine readiness missing")
        }
        try check(armed.state == "ARMED" && armed.value["gate"]["armed_for_exact_candidate"].flag
                  && armed.value["gate"]["resets_on_relaunch"].flag && app.sessionSpinePilotArmed,
                  "Explicit opt-in arms only the exact candidate until relaunch")
        try check(!armed.value["writer_active"].flag && !armed.value["persistent_opt_in"].flag
                  && armed.nextAction == "run_separate_personal_acceptance_before_any_writer_activation",
                  "Armed readiness still cannot activate a writer and requires separate acceptance")
        let readinessSize = NSHostingController(rootView: SessionSpineReadinessView(model: app, readiness: armed))
            .sizeThatFits(in: CGSize(width: 900, height: 760))
        try check(readinessSize.width <= 780 && readinessSize.height <= 710,
                  "Session Spine readiness and recovery UI stays bounded")

        app.openSessionSpineAcceptance(armed)
        guard let rehearsal = app.sessionSpineAcceptance else {
            throw NativeError.message(app.error ?? "Session Spine personal rehearsal missing")
        }
        try check(rehearsal.state == "READY" && rehearsal.canAccept
                  && rehearsal.value["read_only"].flag && !rehearsal.value["writer_active"].flag
                  && !rehearsal.value["write_authority_granted"].flag,
                  "P2k opens one read-only exact-candidate rehearsal without writer authority "
                    + "(state=\(rehearsal.state); paths="
                    + rehearsal.paths.map { "\($0.label):\($0.state)" }.joined(separator: ",") + ")")
        try check(rehearsal.paths.count == 4 && rehearsal.paths.allSatisfy(\.ready)
                  && rehearsal.paths.filter { $0.state == "clean_uninitialized" }.count == 3,
                  "P2k binds the existing private root and three clean future storage paths")
        try check(rehearsal.recoveryCases.count == 5
                  && rehearsal.recoveryCases.allSatisfy { !$0["automatic_retry"].flag && !$0["automatic_repair"].flag }
                  && rehearsal.recoveryCases.last?["required_response"] == .string("manual_inspection_no_retry_or_repair"),
                  "P2k rehearses each crash window without retrying, repairing or executing it")
        try check(!rehearsal.value.pretty.contains(source.text) && !rehearsal.value.pretty.contains(assistant.raw)
                  && !FileManager.default.fileExists(atPath: rehearsal.paths[2].path)
                  && !FileManager.default.fileExists(atPath: rehearsal.paths[3].path),
                  "P2k evidence is content-free and creates no future store")
        let rehearsalSize = NSHostingController(rootView: SessionSpineAcceptanceView(model: app, rehearsal: rehearsal))
            .sizeThatFits(in: CGSize(width: 900, height: 760))
        try check(rehearsalSize.width <= 810 && rehearsalSize.height <= 740,
                  "Session Spine personal rehearsal stays inside a bounded scrollable sheet")

        app.acceptSessionSpineRehearsal(rehearsalHash: String(repeating: "0", count: 64))
        try check(!app.sessionSpineAcceptanceAccepted && app.sessionSpineAcceptance == nil
                  && app.sessionSpinePilotArmed,
                  "Incorrect P2k token grants nothing while preserving the separately armed P2j candidate")
        app.openSessionSpineAcceptance(armed)
        guard let refreshedRehearsal = app.sessionSpineAcceptance else {
            throw NativeError.message(app.error ?? "Refreshed Session Spine personal rehearsal missing")
        }
        app.acceptSessionSpineRehearsal(rehearsalHash: refreshedRehearsal.rehearsalHash)
        guard let accepted = app.sessionSpineAcceptance else {
            throw NativeError.message(app.error ?? "Accepted Session Spine personal rehearsal missing")
        }
        try check(accepted.state == "ACCEPTED" && accepted.value["gate"]["accepted_for_future_design"].flag
                  && !accepted.value["gate"]["activates_writer"].flag && app.sessionSpineAcceptanceAccepted,
                  "Exact P2k token accepts only the process-memory design rehearsal")
        try check(!accepted.value["identity_created"].flag && !accepted.value["intent_prepared"].flag
                  && !accepted.value["spine_write_performed"].flag && !accepted.value["history_write_performed"].flag
                  && (try fileBytes(state)) == before,
                  "Accepted rehearsal creates no identity, intent, Spine event or history write")

        let existingEvidence = state.appendingPathComponent("session_spine_store", isDirectory: true)
        try FileManager.default.createDirectory(
            at: existingEvidence, withIntermediateDirectories: false,
            attributes: [.posixPermissions: 0o700]
        )
        let unknownEvidence = existingEvidence.appendingPathComponent("unexpected.tmp")
        try Data("synthetic recovery evidence".utf8).write(to: unknownEvidence)
        let evidenceBefore = try fileBytes(existingEvidence)
        let blocked = try NativeSessionSpineAcceptanceRehearsal.inspect(
            readiness: armed, stateDirectory: state
        )
        try check(blocked.state == "RECOVERY_REQUIRED" && !blocked.canAccept
                  && blocked.paths.first(where: { $0.label == "Session Spine store" })?.state
                    == "existing_evidence_requires_manual_inspection",
                  "Existing private store evidence blocks P2k without guessing recovery")
        try check(try fileBytes(existingEvidence) == evidenceBefore,
                  "Recovery inspection leaves unknown evidence byte-identical")
        try FileManager.default.removeItem(at: existingEvidence)

        var mismatchedPathRefused = false
        do {
            _ = try NativeSessionSpineAcceptanceRehearsal.inspect(
                readiness: armed,
                stateDirectory: state.deletingLastPathComponent().appendingPathComponent("other-private-state")
            )
        } catch { mismatchedPathRefused = true }
        try check(mismatchedPathRefused,
                  "P2k refuses rebinding an armed candidate to another private state scope")

        app.revokeSessionSpineAcceptance()
        try check(!app.sessionSpineAcceptanceAccepted && app.sessionSpineAcceptance?.state == "READY"
                  && app.sessionSpinePilotArmed,
                  "Operator can revoke P2k acceptance without revoking or widening P2j")

        let restarted = AppModel(configuration: LaunchConfiguration(projectRoot: fixture, python: python, stateDirectory: state))
        defer { restarted.client.shutdown() }
        try check(!restarted.sessionSpinePilotArmed && restarted.sessionSpineReadiness == nil
                  && !restarted.sessionSpineAcceptanceAccepted && restarted.sessionSpineAcceptance == nil,
                  "Per-launch Session Spine opt-in and personal acceptance never survive relaunch")
        let recovered = try NativeSessionSpineActivationReadiness.inspect(
            preview: preview, identity: nil,
            identityPath: state.appendingPathComponent("session_spine_identity/installation.json"),
            identityError: "synthetic unknown recovery evidence"
        )
        try check(recovered.state == "RECOVERY_REQUIRED" && !recovered.canArm
                  && recovered.nextAction == "inspect_identity_bytes_manually_no_cleanup",
                  "Unknown identity evidence blocks the pilot and exposes manual no-cleanup recovery")

        app.revokeSessionSpinePilot()
        try check(!app.sessionSpinePilotArmed && app.sessionSpineReadiness?.state == "INACTIVE"
                  && app.sessionSpineAcceptance == nil && !app.sessionSpineAcceptanceAccepted,
                  "Operator can revoke the in-memory preparation and dependent acceptance without changing persisted state")
        app.armSessionSpinePilot(candidateHash: String(repeating: "0", count: 64))
        try check(!app.sessionSpinePilotArmed && app.sessionSpineReadiness == nil,
                  "Stale or incorrect readiness input clears all in-memory pilot state")
        app.sessionSpinePreview = nil
        try check(try fileBytes(state) == before && app.messages == messagesBefore && !app.cloudConsent && !app.fullAccessEnabled,
                  "Preview, readiness, opt-in, acceptance, relaunch and revoke change no history, run, preference or permission bytes")

        await app.openSessionSpine(for: assistant)
        guard let writerLive = app.sessionSpinePreview else {
            throw NativeError.message(app.error ?? "P2l Live Session Spine source missing")
        }
        app.openSessionSpineReadiness(writerLive)
        guard let writerInactive = app.sessionSpineReadiness else {
            throw NativeError.message(app.error ?? "P2l readiness missing")
        }
        app.armSessionSpinePilot(candidateHash: writerInactive.candidateHash)
        guard let writerArmed = app.sessionSpineReadiness else {
            throw NativeError.message(app.error ?? "P2l exact candidate did not arm")
        }
        app.openSessionSpineAcceptance(writerArmed)
        guard let writerRehearsal = app.sessionSpineAcceptance else {
            throw NativeError.message(app.error ?? "P2l personal rehearsal missing")
        }
        app.acceptSessionSpineRehearsal(rehearsalHash: writerRehearsal.rehearsalHash)
        guard let writerAccepted = app.sessionSpineAcceptance, writerAccepted.accepted else {
            throw NativeError.message(app.error ?? "P2l personal rehearsal was not accepted")
        }
        let beforeWriter = try fileBytes(state)
        await app.openSessionSpineWriter(writerAccepted)
        guard let writerPreview = app.sessionSpineWriterPreview else {
            throw NativeError.message(app.error ?? "P2l exact writer preview missing")
        }
        try check(writerPreview.state == "READY" && writerPreview.canApply
                  && writerPreview.value["read_only"].flag
                  && writerPreview.confirmationToken.hasPrefix("CONFIRM-SESSION-SPINE-"),
                  "P2l opens one content-free read-only preview with an exact confirmation phrase")
        try check(!writerPreview.value.pretty.contains(source.text) && !writerPreview.value.pretty.contains(assistant.raw)
                  && (try fileBytes(state)) == beforeWriter,
                  "P2l preview exposes hashes and paths without message text or writes")
        let writerSize = NSHostingController(rootView: SessionSpineWriterView(model: app, preview: writerPreview))
            .sizeThatFits(in: CGSize(width: 900, height: 760))
        try check(writerSize.width <= 800 && writerSize.height <= 700,
                  "P2l writer gate stays inside a bounded scrollable sheet")

        await app.applySessionSpineWriter(
            writerPreview, token: "CONFIRM-SESSION-SPINE-0000000000000000", acknowledgement: true
        )
        try check(app.sessionSpineWriterReceipt == nil && (try fileBytes(state)) == beforeWriter,
                  "An incorrect P2l phrase writes no history, identity, intent or Spine event")
        await app.applySessionSpineWriter(
            writerPreview, token: writerPreview.confirmationToken, acknowledgement: true
        )
        let stabilizedHistory = try fileBytes(state)
        let historyPath = state.appendingPathComponent("conversations.json").path
        let stabilizedKeys = Set(beforeWriter.keys).union(stabilizedHistory.keys)
        let changedByReadback = Set(stabilizedKeys.filter { beforeWriter[$0] != stabilizedHistory[$0] })
        let changedHistoryOnly = changedByReadback.count == 1
            && URL(fileURLWithPath: changedByReadback.first!).resolvingSymlinksInPath()
                == URL(fileURLWithPath: historyPath).resolvingSymlinksInPath()
        try check(app.sessionSpineWriterReceipt == nil && app.sessionSpineWriterPreview == nil
                  && !app.sessionSpinePilotArmed && !app.sessionSpineAcceptanceAccepted
                  && changedHistoryOnly
                  && !FileManager.default.fileExists(atPath: state.appendingPathComponent("session_spine_identity").path)
                  && !FileManager.default.fileExists(atPath: state.appendingPathComponent("session_spine_store").path)
                  && !FileManager.default.fileExists(atPath: state.appendingPathComponent("session_spine_intents").path),
                  "A changed history readback invalidates the one-time grants before identity, intent or Spine writes "
                    + "(changed=\(changedByReadback.sorted()); history=\(historyPath); writer=\(app.sessionSpineWriterPreview != nil); "
                    + "identity=\(FileManager.default.fileExists(atPath: state.appendingPathComponent("session_spine_identity").path)))")

        await app.openSessionSpine(for: assistant)
        guard let stableLive = app.sessionSpinePreview else {
            throw NativeError.message(app.error ?? "P2l stable Live Session Spine source missing")
        }
        app.openSessionSpineReadiness(stableLive)
        guard let stableInactive = app.sessionSpineReadiness else {
            throw NativeError.message(app.error ?? "P2l stable readiness missing")
        }
        app.armSessionSpinePilot(candidateHash: stableInactive.candidateHash)
        guard let stableArmed = app.sessionSpineReadiness else {
            throw NativeError.message(app.error ?? "P2l stable exact candidate did not arm")
        }
        app.openSessionSpineAcceptance(stableArmed)
        guard let stableRehearsal = app.sessionSpineAcceptance else {
            throw NativeError.message(app.error ?? "P2l stable rehearsal missing")
        }
        app.acceptSessionSpineRehearsal(rehearsalHash: stableRehearsal.rehearsalHash)
        guard let stableAccepted = app.sessionSpineAcceptance, stableAccepted.accepted else {
            throw NativeError.message(app.error ?? "P2l stable rehearsal was not accepted")
        }
        await app.openSessionSpineWriter(stableAccepted)
        guard let committedPreview = app.sessionSpineWriterPreview else {
            throw NativeError.message(app.error ?? "P2l stable writer preview missing")
        }
        let beforeCommittedWriter = try fileBytes(state)
        await app.applySessionSpineWriter(
            committedPreview, token: committedPreview.confirmationToken, acknowledgement: true
        )
        guard let writerReceipt = app.sessionSpineWriterReceipt else {
            throw NativeError.message(app.error ?? "P2l verified writer receipt missing")
        }
        try check(writerReceipt.result == "COMMITTED"
                  && writerReceipt.value["identity_created"].flag
                  && writerReceipt.value["intent_prepare_write_performed"].flag
                  && writerReceipt.value["spine_write_performed"].flag
                  && writerReceipt.value["intent_commit_write_performed"].flag,
                  "P2l commits exactly one fresh identity-bound intent and Session Spine event")
        try check(writerReceipt.value["target_execution_performed"] == .bool(false)
                  && writerReceipt.value["model_call_performed"] == .bool(false)
                  && writerReceipt.value["command_executed"] == .bool(false)
                  && writerReceipt.value["permission_changed"] == .bool(false)
                  && writerReceipt.value["context_injection_changed"] == .bool(false),
                  "P2l receipt proves no target, model, command, permission or Context Injection action")
        let afterWriter = try fileBytes(state)
        let addedPaths = Set(afterWriter.keys).subtracting(beforeCommittedWriter.keys)
        let allowedPrefixes = [
            state.appendingPathComponent("session_spine_identity", isDirectory: true).resolvingSymlinksInPath().path + "/",
            state.appendingPathComponent("session_spine_store", isDirectory: true).resolvingSymlinksInPath().path + "/",
            state.appendingPathComponent("session_spine_intents", isDirectory: true).resolvingSymlinksInPath().path + "/",
        ]
        try check(beforeCommittedWriter.allSatisfy { afterWriter[$0.key] == $0.value }
                  && !addedPaths.isEmpty
                  && addedPaths.allSatisfy { path in
                      let resolved = URL(fileURLWithPath: path).resolvingSymlinksInPath().path
                      return allowedPrefixes.contains { resolved.hasPrefix($0) }
                  },
                  "P2l preserves every existing byte and adds files only under three fixed private namespaces")
        let afterFirstApply = try fileBytes(state)
        await app.applySessionSpineWriter(
            committedPreview, token: committedPreview.confirmationToken, acknowledgement: true
        )
        try check(try fileBytes(state) == afterFirstApply,
                  "P2l removes repeat-run reachability after the first verified receipt")

        let recoveredApp = AppModel(
            configuration: LaunchConfiguration(projectRoot: fixture, python: python, stateDirectory: state)
        )
        defer { recoveredApp.client.shutdown() }
        await recoveredApp.start()
        guard let recoveredAssistant = recoveredApp.messages.last else {
            throw NativeError.message("P2l restart history did not load")
        }
        await recoveredApp.openSessionSpine(for: recoveredAssistant)
        guard let recoveredLive = recoveredApp.sessionSpinePreview else {
            throw NativeError.message(recoveredApp.error ?? "P2l restart source missing")
        }
        recoveredApp.openSessionSpineReadiness(recoveredLive)
        guard let recoveredInactive = recoveredApp.sessionSpineReadiness else {
            throw NativeError.message(recoveredApp.error ?? "P2l restart readiness missing")
        }
        recoveredApp.armSessionSpinePilot(candidateHash: recoveredInactive.candidateHash)
        guard let recoveredArmed = recoveredApp.sessionSpineReadiness else {
            throw NativeError.message(recoveredApp.error ?? "P2l restart exact candidate did not arm")
        }
        recoveredApp.openSessionSpineAcceptance(recoveredArmed)
        guard let recoveryRehearsal = recoveredApp.sessionSpineAcceptance else {
            throw NativeError.message(recoveredApp.error ?? "P2l recovery evidence missing")
        }
        try check(recoveryRehearsal.recoveryRequired && !recoveryRehearsal.canAccept,
                  "Relaunch exposes durable P2l evidence as recovery-only rather than persisting acceptance")
        let beforeClosedPreview = try fileBytes(state)
        await recoveredApp.openSessionSpineWriter(recoveryRehearsal)
        guard let closedPreview = recoveredApp.sessionSpineWriterPreview else {
            throw NativeError.message(recoveredApp.error ?? "P2l closed-state preview missing")
        }
        try check(closedPreview.closed && !closedPreview.canApply && closedPreview.confirmationToken.isEmpty
                  && recoveredApp.sessionSpineWriterReceipt == nil
                  && (try fileBytes(state)) == beforeClosedPreview,
                  "P2l restart verifies CLOSED evidence without restoring a token or writing again")
    }
}
