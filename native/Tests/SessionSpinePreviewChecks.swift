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
        let size = NSHostingController(rootView: SessionSpinePreviewView(preview: preview))
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
        app.sessionSpinePreview = nil
        try check(try fileBytes(state) == before && app.messages == messagesBefore && !app.cloudConsent && !app.fullAccessEnabled,
                  "Opening and closing Live Session Spine changes no history, run, preference or permission bytes")
    }
}
