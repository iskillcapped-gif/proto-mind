import AppKit
import Foundation

extension NativeChecks {
    @MainActor
    static func taskUpdatesIntegration(fixture: URL, service: URL, python: URL, root: URL) async throws {
        let project = root.appendingPathComponent("steering-project")
        let state = root.appendingPathComponent("steering-state")
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        try FileManager.default.copyItem(at: fixture, to: project)
        try FileManager.default.copyItem(at: service, to: project.appendingPathComponent("proto_mind/steering_fixture.py"))
        let bridge = project.appendingPathComponent("proto_mind/native_bridge.py")
        var code = try String(contentsOf: bridge, encoding: .utf8)
        code = code.replacingOccurrences(of: "class NativeBackend:", with: "from proto_mind.steering_fixture import FixtureSubscription\n\nclass NativeBackend:")
            .replacingOccurrences(of: "subscription_factory=CodexSubscription", with: "subscription_factory=FixtureSubscription")
        try code.write(to: bridge, atomically: true, encoding: .utf8)
        let helper = LaunchConfiguration.argument("--pdf-helper").map { URL(fileURLWithPath: $0) }
        let app = AppModel(configuration: LaunchConfiguration(projectRoot: project, python: python, stateDirectory: state, pdfHelper: helper))
        defer { app.shutdown() }
        await app.start()
        app.setProvider("codex"); app.cloudConsent = true
        app.setAutoSkillsEnabled(false)
        let workspace = root.appendingPathComponent("steering-workspace")
        try FileManager.default.createDirectory(at: workspace, withIntermediateDirectories: true)
        let file = workspace.appendingPathComponent("design.txt")
        try Data("ATTACHMENT_BLUE_BUTTON".utf8).write(to: file)
        await app.bindWorkspace(workspace.path)
        app.setComposer("Более новый черновик")
        try Data(#"{"ready_delay":0.4}"#.utf8).write(to: state.appendingPathComponent("steering-control.json"), options: .atomic)
        let running = Task { await app.submit("Подготовь страницу") }
        let deadline = Date().addingTimeInterval(10)
        while !app.canUpdateTask && Date() < deadline { try await Task.sleep(for: .milliseconds(10)) }
        try check(app.canUpdateTask && app.taskUpdateTarget == nil, "Text updates are available while the main model is preparing")
        try check(app.composer == "Более новый черновик", "Preparing a supplied request does not erase a different composer draft")
        await app.submit("Добавь синюю кнопку")
        try check(app.messages.first?.taskUpdates?.first?.state == .queued && app.composer.isEmpty,
                  "Early update is saved in the task queue and clears only its submitted draft")
        while app.messages.first?.taskUpdates?.first?.state != .accepted && Date() < deadline { try await Task.sleep(for: .milliseconds(10)) }
        try check(app.busy && app.messages.first?.taskUpdates?.first?.state == .accepted,
                  "Queued update reaches the same running model turn before its answer")
        while !app.stream.isEmpty && Date() < deadline { try await Task.sleep(for: .milliseconds(10)) }
        try check(app.stream.isEmpty && app.workLog.pretty.contains("Предварительный ответ"),
                  "A steering boundary clears the superseded live answer and preserves it in public work history")
        await app.codexUsage.refreshLimits(app: app)
        try check(app.busy && app.codexUsage.summary?.compactBucket?.windows.first?.used == 27,
                  "Menu quota reads also complete during the same running task")
        try check(app.composerShowsStop && !app.canSendComposer && app.canReceiveAttachments,
                  "An empty working composer shows Stop and accepts local attachments")
        app.setComposer("Временный текст")
        try check(!app.composerShowsStop && app.canSendComposer, "Typing during work changes the single action to Send")
        app.setComposer("")
        try check(app.composerShowsStop, "Removing the text changes the single action back to Stop")
        await app.previewDroppedAttachments([file])
        guard let attachment = app.attachmentDropPreview else { throw NativeError.message("Running file preview unavailable") }
        try app.attachDrop(attachment); app.attachmentDropPreview = nil
        try check(!app.composerShowsStop && app.canSendComposer && app.busy,
                  "An attachment without text changes Stop to an enabled Send while the task runs")
        await app.submit()
        try check(app.messages.first?.taskUpdates?.last?.state == .accepted && app.composerShowsStop
                  && app.selected?.pendingFiles.isEmpty == true && app.messages.first?.taskUpdates?.last?.attachmentNames == ["design.txt"],
                  "An attachment-only correction is delivered, saved as metadata and returns the action to Stop")
        let image = workspace.appendingPathComponent("sample.png")
        let bitmap = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: 16, pixelsHigh: 10,
            bitsPerSample: 8, samplesPerPixel: 3, hasAlpha: false, isPlanar: false,
            colorSpaceName: .deviceRGB, bytesPerRow: 48, bitsPerPixel: 24)!
        bitmap.bitmapData?.initialize(repeating: 128, count: 480)
        try bitmap.representation(using: .png, properties: [:])!.write(to: image)
        await app.previewImage(image.path)
        guard let imagePreview = app.imagePreview else { throw NativeError.message("Live image preview unavailable") }
        try app.attachImage(imagePreview); app.imagePreview = nil
        let pdf = workspace.appendingPathComponent("sample.pdf")
        try syntheticPDF(["LIVE_PDF_SELECTED_PAGE"]).write(to: pdf)
        await app.previewPDF(pdf.path)
        guard let pdfPreview = app.pdfPreview else { throw NativeError.message("Live PDF preview unavailable") }
        try app.attachPDF(pdfPreview); app.pdfPreview = nil
        await app.submit("Сверь с картинкой и PDF")
        try check(app.messages.first?.taskUpdates?.last?.state == .accepted
                  && app.messages.first?.taskUpdates?.last?.imageContext?.count == 1
                  && app.messages.first?.taskUpdates?.last?.pdfContext?.count == 1 && app.composerShowsStop,
                  "Image bytes and selected PDF pages reach the running task while only metadata is saved")
        await app.submit("И крупный заголовок")
        try check(app.messages.first?.taskUpdates?.last?.state == .accepted && app.busy,
                  "A second live update is delivered without starting another task")
        try Data(#"{"outcome":"unknown"}"#.utf8).write(to: state.appendingPathComponent("steering-control.json"), options: .atomic)
        await app.submit("Добавь отступы")
        try check(app.messages.first?.taskUpdates?.last?.state == .unknown,
                  "A lost acknowledgement is shown as unconfirmed and is not retried")
        // Previewed bytes must never be silently replaced after the source changes.
        await app.previewDroppedAttachments([file])
        guard let changed = app.attachmentDropPreview else { throw NativeError.message("Changed-file preview unavailable") }
        try app.attachDrop(changed); app.attachmentDropPreview = nil
        try Data("CHANGED_AFTER_PREVIEW".utf8).write(to: file)
        await app.submit()
        try check(app.messages.first?.taskUpdates?.last?.state == .rejected
                  && app.messages.first?.taskUpdates?.last?.reason?.contains("Вложение изменилось") == true,
                  "A changed attachment is rejected locally with a useful delivery reason")
        await app.previewDroppedAttachments([file])
        guard let nextDraft = app.attachmentDropPreview else { throw NativeError.message("Draft attachment preview unavailable") }
        try app.attachDrop(nextDraft); app.attachmentDropPreview = nil
        app.setComposer("Черновик следующего сообщения")
        try Data().write(to: state.appendingPathComponent("finish-steering"))
        await running.value
        try check(!app.busy && app.messages.count == 2 && app.messages.last?.role == "assistant"
                  && app.messages.last?.text.contains("Добавь синюю кнопку") == true
                  && app.messages.last?.text.contains("И крупный заголовок") == true,
                  "One final response includes live updates and keeps its original exact source pair")
        try check(app.composer == "Черновик следующего сообщения" && app.selected?.pendingFiles.count == 1,
                  "Finishing the task preserves the next draft's text and attachment")
        let rpc = try String(contentsOf: state.appendingPathComponent("steering-rpc.jsonl"), encoding: .utf8)
            .split(separator: "\n").map { try JSONDecoder().decode(JSONValue.self, from: Data($0.utf8)) }
        let steering = rpc.filter { $0["method"].text == "turn/steer" }
        try check(steering.count == 5, "Five updates produce exactly five steering calls (observed \(steering.count))")
        try check(steering.contains { $0["params"]["input"].pretty.contains("ATTACHMENT_BLUE_BUTTON") }
                  && !steering.contains { $0["params"]["input"].pretty.contains("CHANGED_AFTER_PREVIEW") },
                  "Selected text reaches the model; changed bytes and unknown replies are never resent")
        // Compare the actual PDFKit text as a JSON string: extraction may insert
        // line breaks that are escaped inside the quoted provider context.
        let excerpt = String(data: try JSONEncoder().encode(pdfPreview.pages[0]["text"]), encoding: .utf8)!
        try check(steering.contains { $0["params"]["input"].items.first?["text"].text.contains(excerpt) == true
                      && $0["params"]["input"].items.last?["type"].text == "image" },
                  "The selected PDF excerpt and actual image input share one steering request")
        let restored = AppModel(configuration: LaunchConfiguration(projectRoot: project, python: python, stateDirectory: state))
        try check(restored.messages.first?.taskUpdates?.map(\.state) == [.accepted, .accepted, .accepted, .accepted, .unknown, .rejected]
                  && restored.messages.last?.turnReference != nil,
                  "Restart preserves update delivery states and validates the original turn lineage")
        try check(restored.selected?.history.filter { $0["role"].text == "user" }.count == 5
                  && restored.selected?.history.contains { $0["content"].text.contains("Earlier attachment content is NOT included") } == true,
                  "Only confirmed updates join a newly bootstrapped provider history")
        let found = await ConversationHistorySearch.find(in: restored.conversations, query: "синюю", scope: .all)
        try check(found.count == 1, "Saved updates remain searchable with their parent task")

        // A prepared but unsent update is never replayed after completion/restart.
        var original = ChatMessage(role: "user", text: "Original task")
        original.taskUpdates = [TaskUpdate(text: "Unsent correction")]
        try TaskUpdate.validate([original])
        try check(original.taskUpdates?.first?.label(active: false) == "Не отправлено",
                  "Restored queued text is visibly unsent rather than silently replayed")

        try FileManager.default.removeItem(at: state.appendingPathComponent("finish-steering"))
        app.setComposer("Проверь исходный файл")
        let interrupted = Task { await app.submit() }
        let stopDeadline = Date().addingTimeInterval(10)
        while !app.canUpdateTask && Date() < stopDeadline { try await Task.sleep(for: .milliseconds(10)) }
        try check(app.canUpdateTask && app.selected?.pendingFiles.isEmpty == true,
                  "Starting a new task moves its selected files out of the next draft")
        app.setComposer("Новое сообщение без вложения")
        await app.stop(); await interrupted.value
        try check(app.composer == "Новое сообщение без вложения" && app.selected?.pendingFiles.isEmpty == true
                  && app.messages.suffix(2).first?.fileContext?.count == 1,
                  "Stopping preserves a different new draft without silently restoring old files into it")
    }
}
