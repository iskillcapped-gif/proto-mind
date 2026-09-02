import AppKit
import Foundation
import SwiftUI

extension NativeChecks {
    @MainActor
    static func learningReview(fixture: URL, python: URL, root: URL) async throws {
        let project = root.resolvingSymlinksInPath().appendingPathComponent("learning-project")
        let package = project.appendingPathComponent("proto_mind")
        try FileManager.default.createDirectory(at: package, withIntermediateDirectories: true)
        for file in try FileManager.default.contentsOfDirectory(at: fixture.appendingPathComponent("proto_mind"), includingPropertiesForKeys: nil)
            where !["data", "exports", "__pycache__"].contains(file.lastPathComponent) {
            try FileManager.default.copyItem(at: file, to: package.appendingPathComponent(file.lastPathComponent))
        }
        let state = root.appendingPathComponent("learning-state")
        let app = AppModel(configuration: LaunchConfiguration(projectRoot: project, python: python, stateDirectory: state))
        defer { app.client.shutdown() }
        app.setProvider("mock")
        let initialCore = try fileBytes(project), initialPrivate = try fileBytes(state)
        await app.openLearningReview(candidateID: "missing")
        try check(app.learningReview?.status == "NOT FOUND" && app.learningReviewError == nil,
                  "Native learning inspection does not recreate a missing pilot or candidate")
        await app.previewLearningOperation(.accept)
        try check(app.learningPreview?.ready == false && app.learningPreview?.confirmationToken == "",
                  "Missing Native candidate cannot obtain a confirmation token")
        try check(try fileBytes(project) == initialCore && fileBytes(state) == initialPrivate,
                  "Native read-only learning RPCs create neither core nor private files")
        app.closeLearningReview()

        func sendFixture(_ text: String) async throws {
            await app.submit(text)
            if app.pendingAction != nil { await app.confirmPending() }
            try check(app.messages.last?.isError == false, "Synthetic Mock learning setup: \(text.prefix(45))")
        }
        try await sendFixture("/experience preview")
        guard let consent = app.messages.last?.text.components(separatedBy: "\n").first(where: { $0.hasPrefix("/experience consent ") }) else {
            throw NativeError.message("Missing fixture consent phrase")
        }
        try await sendFixture(consent)
        try await sendFixture("I prefer short answers.")
        try await sendFixture("Explain a synthetic example. " + String(repeating: "word ", count: 180))
        try await sendFixture("Continue the synthetic example.")
        app.setComposer("Keep this unsent operator draft.")
        app.flushDraft()
        app.openMemoryWorkshop()
        await app.refreshMemoryWorkshop()
        guard let candidate = app.memoryWorkshop?.candidates.first(where: { $0.reviewStatus == "operator_review_required" }) else {
            throw NativeError.message(app.memoryWorkshopError ?? "Missing fixture correction-guidance candidate")
        }
        await app.openLearningReview(candidateID: candidate.id)
        guard let review = app.learningReview, app.learningSelection != nil else {
            throw NativeError.message(app.learningReviewError ?? "Missing learning report")
        }
        try check(review.candidate?.id == candidate.id && !review.projectIsolationEnforced && review.requestedMemoryIds.isEmpty,
                  "Native candidate review exposes evidence and global scope without auto-selecting references")
        let coreBefore = try fileBytes(project), privateBefore = try fileBytes(state), messagesBefore = app.messages
        await app.previewLearningOperation(.accept)
        guard let acceptance = app.learningPreview, acceptance.ready else {
            throw NativeError.message(app.learningReviewError ?? app.learningPreview?.issues.joined(separator: "; ") ?? "Missing acceptance preview")
        }
        try check(acceptance.futureMutation == "process_memory_only", "Accept preview explicitly excludes a memory write")
        await app.confirmLearningOperation(token: "WRONG", acknowledgeGlobal: false)
        try check(app.learningReview?.decision == nil && app.learningPreview?.ready == true,
                  "A wrong UI token cannot send a learning confirmation")
        app.learningReason = "Reviewed synthetic evidence."
        await app.confirmLearningOperation(token: acceptance.confirmationToken, acknowledgeGlobal: false)
        try check(app.learningPreview == nil && app.learningReview?.decision == nil,
                  "Editing the reason invalidates the pending Native confirmation")
        await app.previewLearningOperation(.accept)
        guard let current = app.learningPreview else { throw NativeError.message("No fresh preview") }

        let controller = NSHostingController(rootView: MemoryWorkshopView(model: app))
        let fitted = controller.sizeThatFits(in: CGSize(width: 860, height: 700))
        try check(fitted.width <= 861 && fitted.height <= 701 && fitted.height >= 580,
                  "Native learning detail remains inside its scrollable Workshop sheet")
        let rawReview = try await app.client.request("memory_learning_review", app.learningSelection!.parameters)
        try learningContractRefusals(rawReview, selection: app.learningSelection!)
        var previewParams = app.learningSelection!.parameters
        previewParams["operation"] = .string("accept")
        let rawPreview = try await app.client.request("memory_learning_preview", previewParams)
        if case .object(var unsafe) = rawPreview {
            unsafe["future_mutation"] = .string("multiple_stores")
            var refused = false
            do { _ = try NativeLearningPreview.decode(.object(unsafe), selection: app.learningSelection!, operation: .accept) }
            catch { refused = true }
            try check(refused, "Native rejects a confirmation preview with widened mutation scope")
        }
        await app.confirmLearningOperation(token: current.confirmationToken, acknowledgeGlobal: false)
        try check(app.learningReview?.decision?.status == "accepted" && app.learningReview?.proposal == nil,
                  "Native accept records a decision without automatically creating a proposal")
        try check(try fileBytes(project) == coreBefore && fileBytes(state) == privateBefore,
                  "Native accept and all previews leave stores, logs and private history byte-identical")

        await app.previewLearningOperation(.propose)
        try check(app.learningPreview?.ready == false, "Native proposal requires an explicit reference selection")
        guard let reference = app.learningReview?.references.first(where: \.selectable) else { throw NativeError.message("No fixture reference") }
        app.setLearningReference(reference.recordId, selected: true)
        try check(app.learningPreview == nil, "Changing references clears an earlier confirmation")
        await app.refreshLearningReview()
        await app.previewLearningOperation(.propose)
        guard let proposal = app.learningPreview, proposal.ready else {
            throw NativeError.message(app.learningReviewError ?? app.learningPreview?.issues.joined(separator: "; ") ?? "No proposal preview")
        }
        await app.confirmLearningOperation(token: proposal.confirmationToken, acknowledgeGlobal: false)
        try check(app.learningReview?.proposal?.targetSchema == "memory.lesson.v1" && app.learningReview?.applyReceipt == nil,
                  "Native proposal confirmation does not automatically apply a lesson")
        try check(try fileBytes(project) == coreBefore && fileBytes(state) == privateBefore,
                  "Confirmed Native proposal remains process-memory-only")
        await app.previewLearningOperation(.apply)
        guard let apply = app.learningPreview, apply.ready else {
            throw NativeError.message(app.learningReviewError ?? app.learningPreview?.issues.joined(separator: "; ") ?? "No apply preview")
        }
        await app.confirmLearningOperation(token: apply.confirmationToken, acknowledgeGlobal: false)
        try check(app.learningReview?.applyReceipt == nil && app.learningPreview?.ready == true,
                  "Native apply also requires acknowledgement of shared global memory")
        await app.confirmLearningOperation(token: apply.confirmationToken, acknowledgeGlobal: true)
        guard let receipt = app.learningReview?.applyReceipt else { throw NativeError.message(app.learningReviewError ?? "No apply receipt") }
        try check(receipt.verificationStatus == "OK" && !receipt.durableProvenanceId.isEmpty && app.learningResult?.memoryMutationPerformed == true,
                  "Native apply produces a verified record and durable provenance through the existing core writer")
        let after = try fileBytes(project)
        let changes = Set(after.keys).union(coreBefore.keys).filter { after[$0] != coreBefore[$0] }
        let canonicalChanges = Set(changes.map { URL(fileURLWithPath: $0).resolvingSymlinksInPath().path })
        let expectedPath = package.appendingPathComponent("data/persistent_memory.json").resolvingSymlinksInPath().path
        try check(canonicalChanges == [expectedPath],
                  "Native confirmed apply changes exactly persistent_memory.json; expected \(expectedPath), observed \(canonicalChanges.sorted())")
        try check(try fileBytes(state) == privateBefore && app.messages == messagesBefore && app.composer == "Keep this unsent operator draft."
                  && !app.cloudConsent && !app.fullAccessEnabled,
                  "Native learning never submits chat text, changes the draft, calls a model or grants tools")
        await app.previewLearningOperation(.apply)
        await app.confirmLearningOperation(token: apply.confirmationToken, acknowledgeGlobal: true)
        try check(app.learningPreview?.ready == false && (try fileBytes(project)) == after,
                  "Native repeated apply is refused with byte-identical stores")
        await app.openMemoryEvidence(recordID: receipt.recordId)
        try check(app.libraryDetail?.memoryEvidence?.status == "VERIFIED",
                  "The saved Native lesson opens its validated provenance in Memory Library")
        let restart = AppModel(configuration: LaunchConfiguration(projectRoot: project, python: python, stateDirectory: state))
        defer { restart.client.shutdown() }
        await restart.openLearningReview(candidateID: candidate.id)
        await restart.openMemoryEvidence(recordID: receipt.recordId)
        try check(restart.learningReview?.status == "NOT FOUND" && restart.libraryDetail?.memoryEvidence?.status == "VERIFIED",
                  "Restart loses process review but preserves the independently verified lesson source")
        try check(try fileBytes(project) == after && fileBytes(state) == privateBefore,
                  "Restart inspection performs no history migration, core write or auto-capture")
        try await skillAuthoring(app: restart, lessonID: receipt.recordId, project: project, state: state)
    }

    static func learningContractRefusals(_ value: JSONValue, selection: NativeLearningSelection) throws {
        guard case .object(let valid) = value else { throw NativeError.message("Missing review object") }
        for key in ["automatic_promotion", "store_mutation_performed", "model_call_performed", "command_execution_performed", "project_isolation_enforced"] {
            var unsafe = valid
            unsafe[key] = .bool(true)
            var refused = false
            do { _ = try NativeLearningReview.decode(.object(unsafe), selection: selection) } catch { refused = true }
            try check(refused, "Native learning contract rejects unsafe \(key)")
        }
        var wrong = valid
        wrong["conversation_id"] = .string(UUID().uuidString)
        var refused = false
        do { _ = try NativeLearningReview.decode(.object(wrong), selection: selection) } catch { refused = true }
        try check(refused, "Native learning report cannot cross the selected conversation")
    }

}
