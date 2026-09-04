import AppKit
import CryptoKit
import Foundation
import SwiftUI

// Deliberately independent of XCTest: a Mac with Command Line Tools can run these checks.
@main
struct NativeChecks {
    private static var passed = 0
    static func check(_ condition: @autoclosure () throws -> Bool, _ name: String) throws {
        guard try condition() else { throw NativeError.message("FAIL: \(name)") }
        passed += 1
        print("PASS: \(name)")
        fflush(stdout)
    }

    @MainActor
    static func main() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent("proto-native-checks-" + UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: root) }
        if CommandLine.arguments.contains("--memory-suggestions-only"),
           let fixture = LaunchConfiguration.argument("--fixture"), let python = LaunchConfiguration.argument("--python") {
            try memorySuggestionContracts(root: root)
            try await memorySuggestionIntegration(fixture: URL(fileURLWithPath: fixture), python: URL(fileURLWithPath: python), root: root)
            print("Native memory suggestion checks: \(passed) OK")
            return
        }
        if CommandLine.arguments.contains("--learning-only"),
           let fixture = LaunchConfiguration.argument("--fixture"), let python = LaunchConfiguration.argument("--python") {
            try await learningReview(fixture: URL(fileURLWithPath: fixture), python: URL(fileURLWithPath: python), root: root)
            print("Native learning checks: \(passed) OK")
            return
        }
        if let icon = LaunchConfiguration.argument("--icon-source") {
            try appIcon(source: URL(fileURLWithPath: icon))
        }
        let value: JSONValue = .object(["enabled": .bool(false), "count": .number(387), "items": .array([.string("memory"), .null])])
        let decoded = try JSONDecoder().decode(JSONValue.self, from: JSONEncoder().encode(value))
        try check(decoded == value && decoded["count"].integer == 387 && !decoded["enabled"].flag, "JSON/evidence round trip")
        try check(JSONValue.number(Double.infinity).integer == 0, "Invalid numeric data is safe")
        let store = ChatStore(directory: root)
        try check(try store.load().conversations.isEmpty && !FileManager.default.fileExists(atPath: root.path), "Missing history is read-only")
        var chat = Conversation()
        chat.messages = [ChatMessage(role: "assistant", text: "Answer", evidence: value)]
        try store.save(ChatArchive(conversations: [chat], selectedID: chat.id))
        let archive = try ChatStore(directory: root).load()
        try check(archive.conversations == [chat] && archive.selectedID == chat.id, "Conversation/evidence restart persistence")
        let receipt: JSONValue = .object(["schema": .string("proto_mind.native_agent_run.v1"),
            "status": .string("failed"), "items": .array([.object(["id": .string("cmd"), "kind": .string("commandExecution"), "exit_code": .number(1)])])])
        chat.messages.append(ChatMessage(role: "report", text: "Partial work", isError: true, agentRun: receipt))
        try store.save(ChatArchive(conversations: [chat], selectedID: chat.id))
        let withReceipt = try ChatStore(directory: root).load()
        try check(withReceipt.version == 5 && withReceipt.conversations[0].messages.last?.agentRun == receipt, "Version 5 preserves partial agent receipts after restart")
        try check(!chat.history.contains { $0["content"].text == "Partial work" }, "Tool receipts and errors are not replayed as model conversation")
        try check(try FileManager.default.attributesOfItem(atPath: store.url.path)[.posixPermissions] as? Int == 0o600, "Private history permissions")

        let corrupt = ChatStore(directory: root.appendingPathComponent("corrupt"))
        try FileManager.default.createDirectory(at: corrupt.url.deletingLastPathComponent(), withIntermediateDirectories: true)
        let badData = Data("broken history".utf8)
        try badData.write(to: corrupt.url)
        do { _ = try corrupt.load() } catch { }
        do { try corrupt.save(ChatArchive(conversations: [], selectedID: nil)) } catch { }
        try check(corrupt.writeBlocked && (try Data(contentsOf: corrupt.url)) == badData, "Corrupt history cannot be overwritten")

        chat.messages = (0..<30).map { ChatMessage(role: "user", text: "message \($0) " + String(repeating: "x", count: 3000)) }
        chat.messages += [ChatMessage(role: "report", text: "not model history"), ChatMessage(role: "assistant", text: "error", isError: true)]
        try check(chat.history.count == 12 && chat.history.allSatisfy { $0["content"].text.count <= 2000 }, "Model history is bounded and excludes reports/errors")

        let untouched = root.appendingPathComponent("untouched")
        let app = AppModel(configuration: LaunchConfiguration(projectRoot: untouched, python: untouched.appendingPathComponent("python"), stateDirectory: untouched))
        try check(app.selected?.provider == "ollama" && !app.cloudConsent && !app.client.connected, "Startup is local with cloud disabled")
        try check(!FileManager.default.fileExists(atPath: untouched.path), "App initialization performs no writes")
        app.composer = "typed text"
        try check(app.composerRevision == 0, "Typing does not trigger programmatic editor replacement")
        app.setComposer("prepared command")
        try check(app.composerRevision == 1 && app.composer == "prepared command", "Explicit composer replacement has a revision")

        try preferencesAndLegacyHistory(root: root)
        try personaActivationContracts(root: root)
        try instructionReceiptContracts()
        try turnLineageContracts(root: root)
        try sessionSpineDurabilityContracts(root: root)
        if let fixture = LaunchConfiguration.argument("--session-spine-fixture"),
           let state = LaunchConfiguration.argument("--session-spine-state"),
           let python = LaunchConfiguration.argument("--python") {
            try await sessionSpineLiveIntegration(
                fixture: URL(fileURLWithPath: fixture), python: URL(fileURLWithPath: python),
                state: URL(fileURLWithPath: state)
            )
        }
        try conversationManagement(root: root)
        try modelSelection(root: root)
        try modelMenuLayout(root: root)
        try attachmentLayout(root: root)
        try await attachmentDropContracts(root: root)
        try taskCriteria(root: root)
        try autoSkillsContracts(root: root)
        try projectRecallContracts(root: root)
        try memorySuggestionContracts(root: root)
        try workLogAndGrouping(root: root)
        try sidebarLayout(root: root)
        try hoverFeedback()
        try markdown()

        if let fixture = LaunchConfiguration.argument("--fixture"), let python = LaunchConfiguration.argument("--python") {
            try await integration(fixture: URL(fileURLWithPath: fixture), python: URL(fileURLWithPath: python), root: root)
        }
        print("Native checks: \(passed) OK")
    }

    @MainActor
    static func modelMenuLayout(root: URL) throws {
        let state = root.appendingPathComponent("model-menu-layout")
        let app = AppModel(configuration: LaunchConfiguration(projectRoot: root, python: root, stateDirectory: state))
        let menu = NSHostingController(rootView: ModelSelectionMenu(model: app, openSettings: {}))
        let size = menu.sizeThatFits(in: CGSize(width: 700, height: 100))
        try check(size.width < 250 && size.height >= 32, "Model menu hover fits its label with a full-height target, not the empty row")
        let narrow = menu.sizeThatFits(in: CGSize(width: 300, height: 100))
        try check(abs(narrow.width - size.width) < 1 && abs(narrow.height - size.height) < 1,
                  "Model menu highlight keeps intrinsic geometry when composer width changes")
        try check(!FileManager.default.fileExists(atPath: state.path), "Measuring model menu never writes state or connects a provider")
    }

    @MainActor
    static func personaActivationContracts(root: URL) throws {
        let hash = String(repeating: "a", count: 64)
        let receipt: JSONValue = .object([
            "schema": .string("proto_mind.persona_turn_activation.v1"), "active": .bool(true),
            "activated_at": .string("2026-09-01T00:00:00.000000Z"), "persona_id": .string("brother"),
            "persona_version": .string("0.1.0"), "provider": .string("codex_subscription"),
            "model": .string("fixture-model"), "access_mode": .string("chat"),
            "adapter": .string("codex_base_instructions"), "placement": .string("base_instructions"),
            "snapshot_hash": .string(hash), "persona_invariant_hash": .string(hash),
            "runtime_hash": .string(hash), "prompt_context_hash": .string(hash),
            "legacy_prompt_hash": .string(hash), "active_prompt_hash": .string(hash),
            "readiness_hash": .string(hash), "selected_memory_count": .number(0),
            "selected_memory_ids": .array([]), "memory_provenance": .array([]),
            "provider_safety_preserved": .bool(true), "no_added_authority": .bool(true),
            "context_injection_state": .string("disabled"), "context_injection_changed": .bool(false),
            "additional_model_calls": .number(0), "additional_retrieval_calls": .number(0),
            "store_writes_by_activation": .number(0), "rollback_path": .string("legacy_prompt_next_turn"),
            "private_reasoning_included": .bool(false), "receipt_hash": .string(hash)
        ])
        let decoded = try NativePersonaTurnReceipt(receipt)
        try check(decoded.snapshotHash == hash && decoded.selectedMemoryCount == 0,
                  "Native validates a bounded provider-safe Persona turn receipt")
        if case .object(var object) = receipt {
            object["provider_safety_preserved"] = .bool(false)
            var rejected = false
            do { _ = try NativePersonaTurnReceipt(.object(object)) } catch { rejected = true }
            try check(rejected, "Native rejects a Persona receipt that weakens provider safety")
        }

        let state = root.appendingPathComponent("persona-preference")
        let app = AppModel(configuration: LaunchConfiguration(projectRoot: root, python: root, stateDirectory: state))
        app.personaEnabled = true
        try check(app.personaEnabled && (try PreferenceStore(directory: state).load()).personaEnabled,
                  "Explicit Persona opt-in changes only private preferences")
        app.disablePersona()
        let rolledBack = try PreferenceStore(directory: state).load()
        try check(!app.personaEnabled && !rolledBack.personaEnabled && !app.fullAccessEnabled,
                  "Persona rollback returns the next turn to legacy without granting tools")
    }

    static func instructionReceiptFixture() throws -> JSONValue {
        let layers: [JSONValue] = [
            .object([
                "id": .string("base_instructions"), "owner": .string("proto_mind"),
                "placement": .string("codex_base_instructions"), "source": .string("legacy_cognitive_core_current_projection"),
                "characters": .number(1_396), "sha256": .string(String(repeating: "a", count: 64)),
                "dynamic": .bool(true), "provider_visible_at_send": .bool(true),
            ]),
            .object([
                "id": .string("developer_instructions"), "owner": .string("proto_mind"),
                "placement": .string("codex_developer_instructions"), "source": .string("chat_static_contract"),
                "characters": .number(94), "sha256": .string(String(repeating: "b", count: 64)),
                "dynamic": .bool(false), "provider_visible_at_send": .bool(true),
            ]),
        ]
        let materialFields: [String: JSONValue] = [
            "content_free": .bool(true), "instruction_text_stored": .bool(false),
            "assembled_for_provider_call": .bool(true), "provider_delivery_verified": .bool(false),
            "provider_owned_instructions_included": .bool(false), "private_reasoning_included": .bool(false),
            "scope": .string("proto_mind_authored_instruction_metadata"), "provider": .string("codex"),
            "mode": .string("chat"), "persona_state": .string("legacy"),
            "selected_memory_count": .number(0), "selected_memory_ids": .array([]),
            "correction_hint_count": .number(0), "layer_count": .number(2), "layers": .array(layers),
        ]
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys, .withoutEscapingSlashes]
        let material = JSONValue.object(materialFields)
        let bytes = try encoder.encode(material)
        guard let text = String(data: bytes, encoding: .utf8) else { throw NativeError.message("Receipt fixture encoding failed") }
        let hash = SHA256.hash(data: bytes).map { String(format: "%02x", $0) }.joined()
        return .object(materialFields.merging([
            "schema": .string("proto_mind.native_instruction_receipt.v1"),
            "receipt_hash": .string(hash), "hash_material": .string(text),
        ]) { _, new in new })
    }

    static func instructionReceiptContracts() throws {
        let receipt = try instructionReceiptFixture()
        let parsed = try NativeInstructionReceipt(receipt)
        try check(parsed.layers.count == 2 && parsed.value["instruction_text_stored"] == .bool(false),
                  "Native validates a content-free production instruction receipt")
        guard case .object(let valid) = receipt else { throw NativeError.message("Expected instruction receipt fixture") }
        for (field, replacement) in [
            ("content_free", JSONValue.bool(false)),
            ("provider_delivery_verified", .bool(true)),
            ("private_reasoning_included", .bool(true)),
            ("receipt_hash", .string(String(repeating: "0", count: 64))),
            ("hash_material", .string("{}")),
        ] {
            var changed = valid
            changed[field] = replacement
            var refused = false
            do { _ = try NativeInstructionReceipt(.object(changed)) } catch { refused = true }
            try check(refused, "Native rejects tampered instruction receipt \(field)")
        }
        var withText = valid
        if case .array(var layers) = withText["layers"], case .object(var first) = layers[0] {
            first["text"] = .string("must never persist")
            layers[0] = .object(first)
            withText["layers"] = .array(layers)
        }
        var textRefused = false
        do { _ = try NativeInstructionReceipt(.object(withText)) } catch { textRefused = true }
        try check(textRefused, "Native instruction receipt refuses persisted instruction text")
    }

    @MainActor
    static func attachmentLayout(root: URL) throws {
        let state = root.appendingPathComponent("attachment-layout")
        let app = AppModel(configuration: LaunchConfiguration(projectRoot: root, python: root, stateDirectory: state))
        app.conversations[0].pendingImages = [.object([
            "schema": .string("proto_mind.native_image.v1"), "path": .string("/synthetic/screenshot.png"),
            "name": .string("screenshot.png"), "sha256": .string(String(repeating: "a", count: 64)),
            "mime_type": .string("image/png"), "size_bytes": .number(3_693_549), "width": .number(1448), "height": .number(1086)
        ])]
        let strip = NSHostingController(rootView: PendingImageAttachmentsView(model: app))
        let composer = NSHostingController(rootView: ComposerView(model: app))
        // NavigationSplitView probes minimum widths before choosing the window
        // height. An unbounded fixedSize notice used to request an 1800px window.
        for width in [0.0, 100.0, 640.0, 900.0] {
            for height in [320.0, 900.0] {
                let size = strip.sizeThatFits(in: CGSize(width: width, height: height))
                try check(size.height < 150, "Restored image strip stays compact at \(Int(width))x\(Int(height))")
                if width >= 640 {
                    let composerSize = composer.sizeThatFits(in: CGSize(width: width, height: height))
                    try check(composerSize.height < 290, "Image composer leaves room for chat at \(Int(width))x\(Int(height)); height=\(composerSize.height)")
                }
            }
        }
        let workspace = NSHostingController(rootView: WorkspaceView(model: app))
        for height in [0.0, 640.0, 900.0] {
            let size = workspace.sizeThatFits(in: CGSize(width: 1200, height: height))
            try check(size.height <= max(640, height), "Restored image workspace respects window height \(height); size=\(size)")
        }
        try check(!FileManager.default.fileExists(atPath: state.path) && !app.client.connected,
                  "Measuring a restored image attachment never reads the image, writes state, or connects")
    }

    @MainActor
    static func hoverFeedback() throws {
        let idle = NativeHoverState(enabled: true, hovered: false, pressed: false)
        let hover = NativeHoverState(enabled: true, hovered: true, pressed: false)
        let pressed = NativeHoverState(enabled: true, hovered: true, pressed: true)
        try check(idle.fill == 0 && idle.border == 0, "Hover idle state preserves the current native appearance")
        try check(hover.fill > idle.fill && hover.border > 0, "Hover has a visible fill and outline")
        try check(pressed.fill > hover.fill, "Press is distinct from hover without layout scaling")
        try check(NativeHoverState(enabled: false, hovered: true, pressed: true) == idle, "Disabled controls do not advertise clickable hover feedback")
    }

    @MainActor
    static func preferencesAndLegacyHistory(root: URL) throws {
        let directory = root.appendingPathComponent("preferences")
        let preferences = PreferenceStore(directory: directory)
        let defaults = try preferences.load()
        try check(!defaults.cloudProcessingAllowed && !defaults.personaEnabled && !FileManager.default.fileExists(atPath: directory.path), "Cloud and Persona preferences default off without creating files")
        try preferences.save(NativePreferences(cloudProcessingAllowed: true, personaEnabled: true))
        let current = try PreferenceStore(directory: directory).load()
        try check(current.version == 2 && current.cloudProcessingAllowed && current.personaEnabled, "Explicit cloud consent and Persona opt-in survive restart in preferences v2")
        try check(try FileManager.default.attributesOfItem(atPath: preferences.url.path)[.posixPermissions] as? Int == 0o600, "Private consent settings permissions")
        let legacyPreferences = Data("{\"cloudProcessingAllowed\":true,\"version\":1}".utf8)
        try legacyPreferences.write(to: preferences.url)
        let legacySettings = try PreferenceStore(directory: directory).load()
        try check(legacySettings.version == 1 && legacySettings.cloudProcessingAllowed && !legacySettings.personaEnabled,
                  "Preferences v1 load with Persona disabled")
        try check(try Data(contentsOf: preferences.url) == legacyPreferences,
                  "Reading preferences v1 does not rewrite or activate Persona")
        try preferences.save(NativePreferences(cloudProcessingAllowed: true, personaEnabled: false))
        let brokenData = Data("broken preferences".utf8)
        try brokenData.write(to: preferences.url)
        let broken = PreferenceStore(directory: directory)
        do { _ = try broken.load() } catch { }
        do { try broken.save(NativePreferences(cloudProcessingAllowed: true, personaEnabled: true)) } catch { }
        try check(broken.writeBlocked && (try Data(contentsOf: broken.url)) == brokenData, "Corrupt preferences cannot be overwritten or authorize cloud/Persona")
        let app = AppModel(configuration: LaunchConfiguration(projectRoot: root, python: root, stateDirectory: directory))
        app.cloudConsent = true
        app.personaEnabled = true
        try check(!app.cloudConsent && !app.personaEnabled && app.error != nil, "Failed preference saves remain fail-closed")

        var chat = Conversation()
        chat.messages = [ChatMessage(role: "user", text: "legacy message")]
        let archive = ChatArchive(version: 1, conversations: [chat], selectedID: chat.id)
        var object = try JSONSerialization.jsonObject(with: JSONEncoder().encode(archive)) as! [String: Any]
        var legacyChats = object["conversations"] as! [[String: Any]]
        for key in ["archived", "draft", "workspacePath", "pendingFiles", "pendingImages", "pendingPDFs", "pendingCriteria", "reasoningEffort"] { legacyChats[0].removeValue(forKey: key) }
        object["conversations"] = legacyChats
        let legacyData = try JSONSerialization.data(withJSONObject: object, options: [.sortedKeys])
        let store = ChatStore(directory: root.appendingPathComponent("legacy"))
        try FileManager.default.createDirectory(at: store.url.deletingLastPathComponent(), withIntermediateDirectories: true)
        try legacyData.write(to: store.url)
        let restored = try store.load()
        try check(restored.version == 1 && restored.conversations.first?.draft == "" && restored.conversations.first?.archived == false, "Version 1 history loads with safe workspace/draft defaults")
        try check(try Data(contentsOf: store.url) == legacyData, "Legacy history is not rewritten by reading")
        try check(restored.conversations[0].reasoningEffort.isEmpty, "Legacy history does not invent a reasoning override")
        object["version"] = 2
        let v2Data = try JSONSerialization.data(withJSONObject: object, options: [.sortedKeys])
        try v2Data.write(to: store.url)
        try check(try store.load().conversations[0].messages[0].agentRun == nil && Data(contentsOf: store.url) == v2Data, "Version 2 loads without tool permission or archive rewrite")
        object["version"] = 3
        let v3Data = try JSONSerialization.data(withJSONObject: object, options: [.sortedKeys])
        try v3Data.write(to: store.url)
        try check(try store.load().conversations[0].pendingImages.isEmpty && Data(contentsOf: store.url) == v3Data,
                  "Version 3 history loads without image inputs or an automatic rewrite")
        object["version"] = 4
        let v4Data = try JSONSerialization.data(withJSONObject: object, options: [.sortedKeys])
        try v4Data.write(to: store.url)
        try check(try store.load().conversations[0].pendingPDFs.isEmpty && Data(contentsOf: store.url) == v4Data,
                  "Version 4 loads without PDF references, extraction or a history rewrite")
    }

    @MainActor
    static func conversationManagement(root: URL) throws {
        let state = root.appendingPathComponent("chat-management")
        let configuration = LaunchConfiguration(projectRoot: root, python: root, stateDirectory: state)
        let app = AppModel(configuration: configuration)
        let first = app.selectedID!
        app.composer = "first draft"
        app.renameConversation(first, title: "First workspace")
        app.newConversation()
        let second = app.selectedID!
        try check(app.composer.isEmpty && app.selected?.draft == "", "New conversation does not inherit draft")
        app.composer = "second draft"
        app.select(first)
        try check(app.composer == "first draft" && app.selected?.draft == "first draft", "Switching restores the correct draft")
        app.select(second)
        try check(app.composer == "second draft", "Other conversation draft is preserved")
        app.conversationSearch = "first WORKSPACE"
        try check(app.visibleConversations.count == 1 && app.visibleConversations.first?.id == first, "Conversation search is case-insensitive")
        app.archiveConversation(first, archived: true)
        try check(app.visibleConversations.isEmpty, "Archived conversation is hidden from current list")
        app.showArchived = true
        try check(app.visibleConversations.first?.id == first, "Archive remains searchable and recoverable")
        app.archiveConversation(first, archived: false)
        app.select(first)
        app.cloudConsent = true
        let restored = AppModel(configuration: configuration)
        try check(restored.selected?.title == "First workspace" && restored.composer == "first draft" && restored.cloudConsent, "Title/drafts/consent restore on app restart")
        app.renameConversation(first, title: "   ")
        try check(app.selected?.title == "First workspace", "Invalid rename preserves original title")
        var chat = Conversation()
        chat.messages = [ChatMessage(role: "user", text: "включи контекст", operatorInput: true),
                         ChatMessage(role: "user", text: "/memory status"),
                         ChatMessage(role: "user", text: "failed normal turn", isError: true),
                         ChatMessage(role: "user", text: "normal turn"), ChatMessage(role: "assistant", text: "answer")]
        try check(chat.history.map { $0["content"].text } == ["normal turn", "answer"], "Natural operator inputs and failed turns stay out of model history")
    }

    @MainActor
    static func sidebarLayout(root: URL) throws {
        _ = NSApplication.shared
        let state = root.appendingPathComponent("sidebar-layout")
        let app = AppModel(configuration: LaunchConfiguration(projectRoot: root, python: root, stateDirectory: state))
        app.conversations = (0..<40).map { index in
            var chat = Conversation()
            chat.title = "Layout fixture \(index)"
            return chat
        }
        let collapsed = NSHostingController(rootView: SidebarView(model: app, libraryExpanded: .constant(false), openSettings: {}))
        let expanded = NSHostingController(rootView: SidebarView(model: app, libraryExpanded: .constant(true), openSettings: {}))
        let minimumProposal = CGSize(width: 260, height: 0)
        let collapsedMinimum = collapsed.sizeThatFits(in: minimumProposal).height
        let expandedMinimum = expanded.sizeThatFits(in: minimumProposal).height
        try check(abs(collapsedMinimum - expandedMinimum) < 1, "Library disclosure cannot increase the sidebar minimum height")
        for height: CGFloat in [320, 600, 820] {
            let proposal = CGSize(width: 260, height: height)
            try check(expanded.sizeThatFits(in: proposal).height <= height + 1 && collapsed.sizeThatFits(in: proposal).height <= height + 1,
                      "Sidebar stays inside a \(Int(height))-point viewport with a long conversation list")
        }
        app.conversationSearch = "no matching fixture"
        try check(expanded.sizeThatFits(in: CGSize(width: 225, height: 320)).height <= 321,
                  "Expanded sidebar with search and empty results remains height-bounded")
        try check(!FileManager.default.fileExists(atPath: state.path) && !app.client.connected && !app.fullAccessEnabled,
                  "Sidebar layout and disclosure perform no history writes or tool calls")
    }

    static func markdown() throws {
        let source = "# Header\n\nSome **bold** text.\n\n```swift\nlet x = 1\n```\n\nDone."
        let blocks = MarkdownBlock.parse(source)
        try check(blocks.count == 4 && blocks[0].kind == .heading(1) && blocks[2] == MarkdownBlock(kind: .code("swift"), content: "let x = 1"), "Markdown headings and fenced code keep source text")
        try check(MarkdownBlock.parse("```python\nprint(1)") == [MarkdownBlock(kind: .code("python"), content: "print(1)")], "Unclosed streaming code fence stays readable")
        let links = MarkdownBlock.inline("[unsafe](file:///tmp/test) [safe](https://example.invalid)")
        let urls = links.runs.compactMap(\.link)
        try check(urls.count == 1 && urls.first?.scheme == "https", "Rendered links cannot launch local files or command schemes")
        try check(NativeTheme.interfaceSize == 14 && NativeTheme.codeSize == 12, "Native typography uses 14-point system text and 12-point code")
        try check(MarkdownBlock.inline("Use `code` here").runs.first(where: { $0.inlinePresentationIntent?.contains(.code) == true })?.font == NativeTheme.codeFont, "Inline code shares the fenced-code font size")
    }

    @MainActor
    static func modelSelection(root: URL) throws {
        let state = root.appendingPathComponent("model-selection")
        let configuration = LaunchConfiguration(projectRoot: root, python: root, stateDirectory: state)
        let app = AppModel(configuration: configuration)
        func option(_ id: String, name: String, efforts: [String], isDefault: Bool = false) -> JSONValue {
            .object(["id": .string(id), "name": .string(name), "default": .bool(isDefault),
                     "default_reasoning_effort": .string("medium"),
                     "reasoning_efforts": .array(efforts.map { .object(["id": .string($0)]) })])
        }
        let primary = option("fixture-primary", name: "GPT-5.5", efforts: ["low", "medium", "high", "xhigh"], isDefault: true)
        let smaller = option("fixture-smaller", name: "GPT-5.4-Mini", efforts: ["low", "medium"])
        app.models = [primary, primary, smaller, .null]
        try check(app.codexModels.count == 2 && app.codexModels.last?.displayName == "5.4 Mini", "Picker uses unique provider model IDs with compact display names")
        try check(!FileManager.default.fileExists(atPath: state.path), "Reading picker capabilities never creates history or preferences")
        app.setProvider("codex")
        try check(app.selectedCodexModel?.id == "fixture-primary" && app.reasoningEffortLabel == "Среднее", "Default picker model and effort come from the catalog")
        try check(app.contextRequestParameters?["conversation_id"]?.text == app.selectedID?.uuidString
                  && app.codexThreadLabel == "Статус не проверен",
                  "Codex context and session controls stay bound to the selected conversation")
        try check(!app.availableReasoningEfforts.contains(.max) && !app.availableReasoningEfforts.contains(.ultra), "Unsupported Max and Ultra are never advertised")
        app.setModel("fixture-primary")
        app.setReasoningEffort("xhigh")
        let saved = try Data(contentsOf: app.store.url)
        let restored = AppModel(configuration: configuration)
        try check(restored.selected?.model == "fixture-primary" && restored.selected?.reasoningEffort == "xhigh", "Model and reasoning effort survive restart per conversation")
        try check(!restored.cloudConsent && !restored.fullAccessEnabled && !restored.client.connected, "Restoring model settings cannot grant cloud or tools")
        app.setReasoningEffort("ultra")
        app.setModel("made-up")
        try check(try Data(contentsOf: app.store.url) == saved && app.selected?.reasoningEffort == "xhigh", "Unavailable model and effort selections cannot rewrite the archive")
        app.busy = true
        app.setModel("fixture-smaller"); app.setReasoningEffort("low"); app.resetCodexSelection()
        try check(try Data(contentsOf: app.store.url) == saved, "An active turn freezes model, effort and reset controls")
        app.busy = false
        app.setModel("fixture-smaller")
        try check(app.selected?.reasoningEffort == "" && app.modelSelectionNotice != nil && app.reasoningEffortLabel == "Среднее", "Changing to an incompatible model visibly resets effort to its default")
        app.setReasoningEffort("medium")
        app.setModel("fixture-primary")
        try check(app.selected?.reasoningEffort == "medium", "Compatible effort survives a model change")
        let beforeCatalogRefresh = try Data(contentsOf: app.store.url)
        app.models = [option("fixture-primary", name: "GPT-5.5", efforts: ["low"], isDefault: true)]
        try check(try app.modelSelectionWarning != nil && Data(contentsOf: app.store.url) == beforeCatalogRefresh, "Catalog drift warns without silently rewriting saved choices")
        app.models = [primary, smaller]
        app.resetCodexSelection()
        try check(app.selected?.model == "" && app.selected?.reasoningEffort == "" && !app.cloudConsent && !app.fullAccessEnabled, "Reset changes only model/effort and does not enable permissions")
        app.setReasoningEffort("high")
        app.setProvider("ollama")
        try check(app.selected?.reasoningEffort.isEmpty == true, "Codex reasoning overrides do not carry into local providers")
        let future = CodexModelOption(option("fixture-future", name: "GPT-5.6-Sol", efforts: ["max", "ultra"]))!
        try check(future.efforts == [.max, .ultra] && future.defaultEffort == nil, "Future levels require explicit catalog support and no invented default")
    }

    @MainActor
    static func workLogAndGrouping(root: URL) throws {
        let log: JSONValue = .object([
            "schema": .string("proto_mind.native_work_log.v1"), "public_only": .bool(true),
            "status": .string("completed"), "elapsed_ms": .number(65000),
            "entries": .array([.object(["id": .string("commentary:c"), "kind": .string("commentary"), "text": .string("Public fixture progress")])])
        ])
        var chat = Conversation()
        chat.messages = [ChatMessage(role: "user", text: "Fixture task"), ChatMessage(role: "assistant", text: "Fixture answer", workLog: log)]
        let store = ChatStore(directory: root.appendingPathComponent("work-log"))
        try store.save(ChatArchive(conversations: [chat], selectedID: chat.id))
        let before = try Data(contentsOf: store.url)
        let restored = try store.load()
        try check(restored.version == 5 && restored.conversations[0].messages.last?.workLog == log, "Public work log survives restart in history v5")
        try check(try Data(contentsOf: store.url) == before, "Reading work log does not rewrite history")
        try check(chat.history.map { $0["content"].text } == ["Fixture task", "Fixture answer"], "Public work log is display-only, not replayed to the model")
        chat.messages[chat.messages.count - 1].workLog = nil
        try store.save(ChatArchive(conversations: [chat], selectedID: chat.id))
        let oldBytes = try Data(contentsOf: store.url)
        try check(try store.load().conversations[0].messages.last?.workLog == nil && Data(contentsOf: store.url) == oldBytes, "Older history v3 remains untouched and has no invented progress")
        try check(WorkLogPresentation.title(log, live: false) == "Выполнено за 1 мин 5 с", "Completed work title reports observed duration")
        try check(WorkLogPresentation.duration(-1000) == "менее секунды" && WorkLogPresentation.duration(3661000) == "1 ч 1 мин", "Duration handles invalid and long values")
        try check(WorkLogPresentation.title(.object(["status": .string("interrupted")]), live: false).hasPrefix("Остановлено"), "Interrupted work is never labelled completed")
        try check(WorkLogPresentation.title(.object(["stage": .string("answering")]), live: true) == "Пишу ответ", "Live work distinguishes final answer from public commentary")
        let liveV2: JSONValue = .object([
            "schema": .string("proto_mind.native_work_log.v1"), "public_only": .bool(true),
            "id": .string("run-one"), "state_version": .number(2),
        ])
        let staleV1: JSONValue = .object([
            "schema": .string("proto_mind.native_work_log.v1"), "public_only": .bool(true),
            "id": .string("run-one"), "state_version": .number(1),
        ])
        let liveV3: JSONValue = .object([
            "schema": .string("proto_mind.native_work_log.v1"), "public_only": .bool(true),
            "id": .string("run-one"), "state_version": .number(3),
        ])
        let anotherRun: JSONValue = .object([
            "schema": .string("proto_mind.native_work_log.v1"), "public_only": .bool(true),
            "id": .string("run-two"), "state_version": .number(1),
        ])
        try check(!WorkLogEventGate.shouldAccept(current: liveV2, incoming: staleV1), "Work log rejects a stale state version")
        try check(WorkLogEventGate.shouldAccept(current: liveV2, incoming: liveV3), "Work log accepts the next state version")
        try check(WorkLogEventGate.shouldAccept(current: liveV3, incoming: anotherRun), "Work log accepts a separately identified run")
        try check(!WorkLogEventGate.shouldAccept(current: liveV3, incoming: .object(["schema": .string("proto_mind.native_work_log.v1"), "public_only": .bool(true)])), "Work log rejects unbound events")
        var first = Conversation(), same = Conversation(), other = Conversation(), unbound = Conversation()
        first.workspacePath = "/one/project"; same.workspacePath = "/one/project"; other.workspacePath = "/two/project"
        unbound.title = "Unbound"
        let original = [first, other, same, unbound]
        let groups = ConversationGroup.make(original)
        try check(groups.count == 3 && groups[0].conversations.map(\.id) == [first.id, same.id], "Sidebar groups conversations by actual workspace preserving order")
        try check(groups[0].id != groups[1].id && groups[0].title == groups[1].title, "Same folder names at different paths remain distinct projects")
        try check(groups[2].workspace == nil && groups[2].conversations[0].id == unbound.id, "Unbound chats remain available without inventing a project")
        try check(ConversationGroup.make([]).isEmpty && original == [first, other, same, unbound], "Grouping is pure and handles no conversations")
        let state = root.appendingPathComponent("quiet-inspector")
        let app = AppModel(configuration: LaunchConfiguration(projectRoot: root, python: root, stateDirectory: state))
        try check(!app.showInspector && app.workLog.isNull && app.turnStartedAt == nil && !FileManager.default.fileExists(atPath: state.path), "Diagnostics start collapsed without fake activity or writes")
    }

    @MainActor
    static func integration(fixture: URL, python: URL, root: URL) async throws {
        guard fixture.resolvingSymlinksInPath().path.hasPrefix(FileManager.default.temporaryDirectory.resolvingSymlinksInPath().path + "/") else {
            throw NativeError.message("Native integration smoke accepts temporary fixture projects only.")
        }
        let app = AppModel(configuration: LaunchConfiguration(projectRoot: fixture, python: python, stateDirectory: root.appendingPathComponent("integration-state")))
        defer { app.client.shutdown() }
        await app.start()
        try check(app.client.connected && app.bootstrap["registry_count"].integer >= 387, "Native process connects to real Python bridge")
        app.setProvider("mock")
        await app.submit("/commands status")
        try check(app.messages.last?.role == "report" && app.messages.last?.isError == false, "Operator command returns a report")
        try check(app.workSessions.isEmpty && app.workSessionsWarning == nil, "Operator commands do not create durable Native work sessions")
        await app.submit("Я предпочитаю короткие ответы.")
        try check(app.messages.last?.evidence["schema"].text == "proto_mind.cognitive_turn.v1", "Normal turn returns real cognitive evidence")
        try check(app.messages.last?.evidence["memory_decision"]["should_store"].flag == true, "Existing memory evaluation is preserved in fixture")
        await app.submit("/context injection enable")
        try check(app.pendingAction != nil, "Mutating command waits for native confirmation")
        app.pendingAction = nil
        await app.refresh()
        try check(!app.bootstrap["context_injection"].flag, "Cancelling confirmation keeps injection disabled")
        let restored = try ChatStore(directory: root.appendingPathComponent("integration-state")).load()
        try check(restored.conversations.first?.messages == app.messages, "Real bridge responses persist only to native chat history")
        let sourceFile = fixture.appendingPathComponent("proto_mind/native_workspace.py")
        let sourceBefore = try Data(contentsOf: sourceFile)
        await app.bindWorkspace(fixture.path)
        let bound = URL(fileURLWithPath: app.selected?.workspacePath ?? "/").resolvingSymlinksInPath()
        try check(bound == fixture.resolvingSymlinksInPath() && app.workspaceStatus["read_only"].flag, "Explicit binding uses the same folder without a copy")
        try await personaInspector(app: app, fixture: fixture, state: root.appendingPathComponent("integration-state"))
        try await personaOptIn(app: app, fixture: fixture, state: root.appendingPathComponent("integration-state"))
        await app.openWorkspaceEntry(.object(["path": .string("proto_mind/native_workspace.py"), "directory": .bool(false)]))
        try check(app.filePreview["preview"].text.contains("WorkspaceReader"), "Native file preview reads actual source through the bridge")
        app.attachPreview()
        try check(app.selected?.pendingFiles.count == 1 && app.selected?.pendingFiles.first?["content"].isNull == true, "Only the preview hash/manifest is saved as an attachment")
        try await contextDesk(app: app, fixture: fixture, state: root.appendingPathComponent("integration-state"), source: sourceFile)
        await app.submit("/commands status")
        try check(app.selected?.pendingFiles.count == 1, "Operator command does not consume or send pending attachments")
        await app.submit("Explain the selected source.")
        try check(app.messages.last?.fileContext?.first?["path"].text == "proto_mind/native_workspace.py" && app.selected?.pendingFiles.isEmpty == true && app.messages.last?.notices.contains(where: { $0.contains("not a file-understanding model") }) == true, "Normal turn records manifest, clears attachment, and labels Mock limits")
        try check(try Data(contentsOf: sourceFile) == sourceBefore, "Workspace inspection/attachment leaves source bytes unchanged")
        try await workSessions(app: app, fixture: fixture, state: root.appendingPathComponent("integration-state"), python: python)
        try await workSessionNotices(app: app, fixture: fixture, state: root.appendingPathComponent("integration-state"), python: python)
        try await artifactDesk(app: app, fixture: fixture, state: root.appendingPathComponent("integration-state"))
        try await manualReview(app: app, fixture: fixture, state: root.appendingPathComponent("integration-state"), python: python)
        try await library(app: app, fixture: fixture, state: root.appendingPathComponent("integration-state"))
        try await learningReview(fixture: fixture, python: python, root: root)
        try await agentAccess(app: app, fixture: fixture, state: root.appendingPathComponent("integration-state"), python: python)
        try await imageAttachments(fixture: fixture, python: python, root: root)
        try await attachmentDrops(fixture: fixture, python: python, root: root)
        try await pdfAttachments(fixture: fixture, python: python, root: root)
        try await projectMemory(fixture: fixture, python: python, root: root)
        try await projectRecallIntegration(fixture: fixture, python: python, root: root)
        try await memorySuggestionIntegration(fixture: fixture, python: python, root: root)
        app.setProvider("codex")
        app.cloudConsent = false
        await app.submit("retry draft")
        try check(app.messages.last?.isError == true && app.composer == "retry draft", "Unsent cloud turn remains a draft without silent fallback")
        try check(!app.selected!.history.contains { $0["content"].text == "retry draft" }, "Failed send is excluded from subsequent model history")
    }

    @MainActor
    static func personaInspector(app: AppModel, fixture: URL, state: URL) async throws {
        let coreBefore = try fileBytes(fixture.appendingPathComponent("proto_mind/data"))
        let stateBefore = try fileBytes(state)
        let messagesBefore = app.messages, draftBefore = app.composer, providerBefore = app.selected?.provider
        await app.refreshPersonaInspector()
        guard let preview = app.personaPreview else {
            throw NativeError.message(app.personaPreviewError ?? "Missing Persona preview")
        }
        guard let readiness = app.personaReadiness else {
            throw NativeError.message(app.personaReadinessError ?? "Missing Persona readiness")
        }
        try check(preview.kernel["persona_id"].text == "brother"
                  && preview.kernel["voice"]["adaptation"].text == "contextual_without_modes",
                  "Persona Inspector shows one versioned Brother kernel without personality modes")
        try check(preview.snapshot["read_only"].flag && preview.snapshot["authorizes_actions"] == .bool(false)
                  && preview.value["production_prompt_active"] == .bool(false),
                  "Persona Inspector remains non-authorizing and outside the provider prompt")
        try check(preview.snapshot["communication_preferences"].items.isEmpty
                  && preview.snapshot["relevant_memories"].items.isEmpty
                  && preview.value["no_retrieval"].flag && preview.value["no_model_call"].flag,
                  "Persona Inspector performs no memory retrieval or model call")
        try check(preview.runtime["provider"].text == "mock" && preview.runtime["access_mode"].text == "mock"
                  && preview.runtime["tools"].items.isEmpty && !preview.runtime["can_write_workspace"].flag,
                  "Persona self-model reflects current Mock isolation without invented tools")
        try check(preview.runtime["workspace_id"].text.hasPrefix("workspace_")
                  && !preview.value.pretty.contains(fixture.path),
                  "Persona Inspector uses an opaque workspace reference instead of an absolute path")
        try check(readiness.status == "WARN" && !readiness.value["selected_adapter_ready"].flag
                  && readiness.value["activation_performed"] == .bool(false),
                  "Persona readiness keeps the selected Mock provider control-only and performs no activation")
        try check(readiness.parity["checked_providers"].items.map(\.text) == ["codex_subscription", "ollama", "mock"]
                  && readiness.parity["activation_providers"].items.map(\.text) == ["codex_subscription", "ollama"]
                  && readiness.parity["kernel_equal"].flag && readiness.parity["identity_equal"].flag,
                  "Persona readiness shows provider parity without treating Mock as a production adapter")
        try check(readiness.gates.count == 9 && readiness.gates.allSatisfy { $0["status"].text != "FAIL" }
                  && readiness.value["no_model_call"].flag && readiness.value["no_retrieval"].flag
                  && readiness.value["no_store_write"].flag,
                  "Persona readiness publishes bounded gates with no model, retrieval, or store work")
        try check(!readiness.value.pretty.contains(fixture.path),
                  "Persona readiness does not expose the absolute workspace path")
        let controller = NSHostingController(rootView: PersonaInspectorView(model: app))
        let size = controller.sizeThatFits(in: CGSize(width: 800, height: 800))
        try check(size.width >= 680 && size.height >= 620, "Persona Inspector has a usable bounded sheet layout")

        guard case .object(let valid) = preview.value else { throw NativeError.message("Expected Persona object") }
        for (field, invalid) in [("read_only", JSONValue.bool(false)), ("no_model_call", .bool(false)),
                                 ("production_prompt_active", .bool(true)), ("private_reasoning_included", .bool(true))] {
            var changed = valid; changed[field] = invalid
            var refused = false
            do { _ = try NativePersonaPreview(.object(changed)) } catch { refused = true }
            try check(refused, "Persona Inspector rejects unsafe \(field)")
        }
        var changed = valid
        guard case .object(var snapshot) = changed["snapshot"] else { throw NativeError.message("Expected snapshot") }
        snapshot["snapshot_hash"] = .string(String(repeating: "0", count: 64)); changed["snapshot"] = .object(snapshot)
        var badHashRefused = false
        do { _ = try NativePersonaPreview(.object(changed)) } catch { badHashRefused = true }
        try check(badHashRefused, "Persona Inspector rejects a snapshot hash that disagrees with its rendered evidence")

        changed = valid
        guard case .object(var sources) = changed["source_summary"] else { throw NativeError.message("Expected sources") }
        sources["memory"] = .string("all_memory"); changed["source_summary"] = .object(sources)
        var retrievalWideningRefused = false
        do { _ = try NativePersonaPreview(.object(changed)) } catch { retrievalWideningRefused = true }
        try check(retrievalWideningRefused, "Persona Inspector rejects a widened memory source")

        guard case .object(var readinessChanged) = readiness.value else { throw NativeError.message("Expected readiness object") }
        readinessChanged["activation_performed"] = .bool(true)
        var readinessActivationRefused = false
        do { _ = try NativePersonaReadiness(.object(readinessChanged)) } catch { readinessActivationRefused = true }
        try check(readinessActivationRefused, "Persona readiness rejects an activation claim")

        guard case .object(var readinessAdapters) = readiness.value,
              case .array(var adapterRows) = readinessAdapters["adapters"],
              case .object(var codexAdapter) = adapterRows.first else {
            throw NativeError.message("Expected readiness adapters")
        }
        codexAdapter["provider_safety_boundary"] = .string("replaceable")
        adapterRows[0] = .object(codexAdapter); readinessAdapters["adapters"] = .array(adapterRows)
        var readinessSafetyRefused = false
        do { _ = try NativePersonaReadiness(.object(readinessAdapters)) } catch { readinessSafetyRefused = true }
        try check(readinessSafetyRefused, "Persona readiness rejects a replaceable provider safety boundary")

        try check(try fileBytes(fixture.appendingPathComponent("proto_mind/data")) == coreBefore
                  && fileBytes(state) == stateBefore && app.messages == messagesBefore
                  && app.composer == draftBefore && app.selected?.provider == providerBefore,
                  "Persona inspection changes no core/private files, chat, draft, provider, or permission")
    }

    @MainActor
    static func personaOptIn(app: AppModel, fixture: URL, state: URL) async throws {
        app.setProvider("ollama")
        let coreBefore = try fileBytes(fixture.appendingPathComponent("proto_mind/data"))
        let stateBefore = try fileBytes(state)
        let messagesBefore = app.messages
        let prepared = await app.preparePersonaActivation()
        try check(prepared && app.pendingPersonaActivation != nil && !app.personaEnabled,
                  "Persona opt-in first produces a fresh READY confirmation without activation")
        try check(try fileBytes(fixture.appendingPathComponent("proto_mind/data")) == coreBefore
                  && fileBytes(state) == stateBefore && app.messages == messagesBefore,
                  "Persona readiness confirmation preview performs no writes or model turn")
        await app.confirmPersonaActivation()
        let enabledPreferences = try PreferenceStore(directory: state).load()
        try check(app.personaEnabled && enabledPreferences.version == 2 && enabledPreferences.personaEnabled,
                  "Fresh matching readiness evidence enables one persistent local opt-in")
        let stateAfterEnable = try fileBytes(state)
        let changedAfterEnable = Set(stateAfterEnable.keys.filter { stateBefore[$0] != stateAfterEnable[$0] })
            .union(stateBefore.keys.filter { stateAfterEnable[$0] == nil })
        let preferencePath = state.appendingPathComponent("preferences.json").standardizedFileURL.resolvingSymlinksInPath().path
        try check(changedAfterEnable.count == 1 && changedAfterEnable.first.map { URL(fileURLWithPath: $0).standardizedFileURL.resolvingSymlinksInPath().path == preferencePath } == true,
                  "Persona activation changes only the private preferences file; expected \(preferencePath), observed \(changedAfterEnable.sorted())")
        try check((try fileBytes(fixture.appendingPathComponent("proto_mind/data"))) == coreBefore,
                  "Persona activation leaves core stores byte-identical")
        try check(app.messages == messagesBefore && !app.fullAccessEnabled,
                  "Persona activation sends no model turn and grants no authority")
        app.disablePersona()
        try check(!app.personaEnabled && !(try PreferenceStore(directory: state).load()).personaEnabled
                  && (try fileBytes(fixture.appendingPathComponent("proto_mind/data"))) == coreBefore,
                  "Persona rollback returns to legacy without changing core stores")
        app.setProvider("mock")
    }

    @MainActor
    static func imageAttachments(fixture: URL, python: URL, root: URL) async throws {
        let state = root.appendingPathComponent("image-input-state")
        let app = AppModel(configuration: LaunchConfiguration(projectRoot: fixture, python: python, stateDirectory: state))
        defer { app.client.shutdown() }
        await app.start()
        app.setProvider("mock")
        let bitmap = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: 16, pixelsHigh: 10,
                                      bitsPerSample: 8, samplesPerPixel: 3, hasAlpha: false, isPlanar: false,
                                      colorSpaceName: .deviceRGB, bytesPerRow: 48, bitsPerPixel: 24)!
        bitmap.bitmapData!.initialize(repeating: 100, count: bitmap.bytesPerRow * bitmap.pixelsHigh)
        let bytes = bitmap.representation(using: .png, properties: [:])!
        let file = fixture.appendingPathComponent("selected-image.png")
        try bytes.write(to: file)
        let before = try fileBytes(state), coreBefore = try fileBytes(fixture)
        await app.previewImage(file.resolvingSymlinksInPath().path)
        guard let preview = app.imagePreview else { throw NativeError.message(app.error ?? "Missing local image preview") }
        try check(preview.source.value["width"].integer == 16 && preview.source.value["height"].integer == 10,
                  "Native PNG preview decodes bounded local bytes with ImageIO")
        try check(try fileBytes(state) == before && fileBytes(fixture) == coreBefore && !app.cloudConsent,
                  "Opening image preview writes nothing and does not authorize cloud")
        let raw = try await app.client.request("image_preview", ["path": .string(file.resolvingSymlinksInPath().path)])
        for change in ["hash", "mime", "execution", "payload"] {
            guard case .object(var invalid) = raw, case .object(var metadata) = raw["image"] else { throw NativeError.message("Expected image fixture") }
            if change == "hash" { metadata["sha256"] = .string(String(repeating: "0", count: 64)) }
            if change == "mime" { metadata["mime_type"] = .string("image/jpeg") }
            if change == "execution" { invalid["no_execution"] = .bool(false) }
            if change == "payload" { metadata["data_base64"] = .string("not metadata") }
            invalid["image"] = .object(metadata)
            var refused = false
            do { _ = try NativeImagePreview(.object(invalid), conversationID: app.selectedID!, canAttach: true) } catch { refused = true }
            try check(refused, "Image preview rejects incorrect \(change)")
        }
        let jpeg = fixture.appendingPathComponent("selected-image.jpeg")
        try bitmap.representation(using: .jpeg, properties: [.compressionFactor: 0.8])!.write(to: jpeg)
        let jpegValue = try await app.client.request("image_preview", ["path": .string(jpeg.resolvingSymlinksInPath().path)])
        try check(try NativeImagePreview(jpegValue, conversationID: app.selectedID!, canAttach: true).source.value["mime_type"].text == "image/jpeg",
                  "Native JPEG preview validates MIME and dimensions")
        try app.attachImage(preview)
        app.imagePreview = nil
        let restored = try ChatStore(directory: state).load()
        try check(restored.version == 5 && restored.conversations[0].pendingImages == [preview.source.value],
                  "Explicit image attachment persists metadata only in private history v5")
        try check(!String(decoding: Data(contentsOf: state.appendingPathComponent("conversations.json")), as: UTF8.self).contains("data_base64"),
                  "Image payload never enters conversation JSON")
        var historical = Conversation()
        historical.messages = [ChatMessage(role: "user", text: "Inspect this image", imageContext: [preview.source.value])]
        try check(historical.history[0]["content"].text.contains("Earlier image bytes are NOT included") && !historical.history[0].pretty.contains(preview.source.path),
                  "Model history discloses omitted images without reattaching pixels or local paths")
        var tooMany = false
        do { try NativeImageAttachment.validate([preview.source.value, preview.source.value]) } catch { tooMany = true }
        try check(tooMany, "Duplicate image metadata is refused")
        let targetsBefore = try fileBytes(fixture)
        app.setComposer("Inspect selected image")
        app.flushDraft()
        let draftBefore = try fileBytes(state)
        await app.refreshContextPreview()
        try check(app.contextPreview?.imageSources.first?["state"].text == "ready"
                  && app.contextPreview?.value["attachments_ready"] == .bool(false),
                  "Context desk shows local image metadata and unsupported Mock image boundary")
        try check(try fileBytes(state) == draftBefore && fileBytes(fixture) == targetsBefore,
                  "Image context inspection remains read-only")
        await app.submit("/data doctor")
        try check(app.selected?.pendingImages == [preview.source.value] && app.messages.last?.imageContext?.isEmpty == true,
                  "Operator command bypasses images and preserves pending attachment")
        await app.submit("Inspect this selected image.")
        try check(app.messages.last?.isError == true && app.selected?.pendingImages == [preview.source.value]
                  && app.composer == "Inspect this selected image." && app.workSessions.isEmpty,
                  "Unsupported local-provider image send preserves draft and creates no run")
        app.setProvider("codex")
        let noCloudBefore = try fileBytes(fixture)
        await app.submit("Inspect this selected image.")
        try check(app.messages.last?.isError == true && !app.cloudConsent && (try fileBytes(fixture)) == noCloudBefore,
                  "Image attachment cannot bypass cloud consent or silently change providers")
        let changed = bytes + Data([0])
        try changed.write(to: file)
        app.error = nil
        await app.previewImage(preview.source.path, expectedSHA: preview.source.sha256, canAttach: false)
        try check(app.imagePreview == nil && app.error?.contains("changed") == true && app.selected?.pendingImages == [preview.source.value],
                  "Changed image is not silently replaced in preview or draft")
        try bytes.write(to: file)
        let loaded = AppModel(configuration: LaunchConfiguration(projectRoot: fixture, python: python, stateDirectory: state))
        try check(loaded.selected?.pendingImages == [preview.source.value] && loaded.imageThumbnails.isEmpty && !loaded.client.connected,
                  "Restart retains only image references and does not read files or connect a provider")
        app.removePendingImage(preview.source.path)
        try check(app.selected?.pendingImages.isEmpty == true && (try Data(contentsOf: file)) == bytes,
                  "Removing an attachment changes draft metadata, never the original image")
        let other = app.selectedID!
        app.newConversation()
        var wrongChat = false
        do { try app.attachImage(preview) } catch { wrongChat = true }
        try check(wrongChat && app.selectedID != other && app.selected?.pendingImages.isEmpty == true,
                  "A stale preview cannot attach to another conversation")
        let corruptDirectory = root.appendingPathComponent("corrupt-image-state")
        try FileManager.default.createDirectory(at: corruptDirectory, withIntermediateDirectories: true)
        let corruptFile = corruptDirectory.appendingPathComponent("conversations.json")
        try Data("broken".utf8).write(to: corruptFile)
        let blocked = AppModel(configuration: LaunchConfiguration(projectRoot: fixture, python: python, stateDirectory: corruptDirectory))
        let blockedPreview = try NativeImagePreview(raw, conversationID: blocked.selectedID!, canAttach: true)
        var refused = false
        do { try blocked.attachImage(blockedPreview) } catch { refused = true }
        try check(refused && blocked.selected?.pendingImages.isEmpty == true && (try Data(contentsOf: corruptFile)) == Data("broken".utf8),
                  "Failed image persistence rolls back the draft and preserves corrupt history")
    }

    @MainActor
    static func attachmentDropContracts(root: URL) async throws {
        let file = root.appendingPathComponent("local file.png")
        try check(try NativeAttachmentDrop.decodeURL(Data(file.absoluteString.utf8)) == NativeAttachmentDrop.localURL(file),
                  "Drop URL preserves local filenames with spaces")
        for text in ["https://example.invalid/image.png", "file://remote.invalid/share/a.png", "file:///tmp/a.png?read=1", "file:///tmp/a%0Ab.png", "file:///tmp/../secret.png"] {
            var refused = false
            do { _ = try NativeAttachmentDrop.decodeURL(Data(text.utf8)) } catch { refused = true }
            try check(refused, "Drop rejects remote, decorated or unsafe URL: \(text)")
        }
        var oversized = false
        do { _ = try NativeAttachmentDrop.decodeURL(Data(repeating: 97, count: 16_385)) } catch { oversized = true }
        try check(oversized, "Oversize drop URL is refused without reading a file")
        var duplicate = false
        do { _ = try NativeAttachmentDrop.selection([file, file]) } catch { duplicate = true }
        try check(duplicate, "Repeated drop URLs are refused before preview")
        var outside = false
        do { _ = try NativeAttachmentDrop.relativePath(root.appendingPathComponent("other/file.txt"), workspace: root.appendingPathComponent("workspace").path) } catch { outside = true }
        try check(outside, "Drop cannot rebind a workspace to accept an outside text file")

        let pasteboard = NSPasteboard.withUniqueName()
        defer { pasteboard.releaseGlobally() }
        let item = NSPasteboardItem()
        item.setString(file.absoluteString, forType: .fileURL)
        pasteboard.writeObjects([item])
        let editor = NativeComposer.Editor()
        editor.string = "Keep draft text"
        var received: [URL] = [], sends = 0
        editor.canDrop = true
        editor.onFiles = { received = $0; return true }
        editor.onSend = { sends += 1 }
        try check(editor.acceptFileDrop(pasteboard) && received == (try NativeAttachmentDrop.selection([file])) && editor.string == "Keep draft text" && sends == 0,
                  "Text editor hands files to attachment preview, never inserts paths or sends")
        editor.canDrop = false; received = []
        try check(!editor.acceptFileDrop(pasteboard) && received.isEmpty && editor.string == "Keep draft text",
                  "Busy/archived editor refuses file drops without falling back to text insertion")
        let provider = NSItemProvider()
        provider.registerDataRepresentation(forTypeIdentifier: "public.file-url", visibility: .all) { completion in
            completion(Data(file.absoluteString.utf8), nil); return nil
        }
        let decoded = try await NativeAttachmentDrop.loadURL(provider)
        try check(decoded == NativeAttachmentDrop.localURL(file), "Finder-style URL provider loads only an address")
        let stalled = NSItemProvider()
        stalled.registerDataRepresentation(forTypeIdentifier: "public.file-url", visibility: .all) { completion in
            DispatchQueue.global().asyncAfter(deadline: .now() + 0.08) { completion(Data(file.absoluteString.utf8), nil) }
            return Progress(totalUnitCount: 1)
        }
        var timedOut = false
        do { _ = try await NativeAttachmentDrop.loadURL(stalled, timeout: 0.01) } catch { timedOut = true }
        try await Task.sleep(nanoseconds: 120_000_000)
        try check(timedOut, "Stalled drop times out; a late provider callback cannot resume twice")
    }

    @MainActor
    static func attachmentDrops(fixture: URL, python: URL, root: URL) async throws {
        let state = root.appendingPathComponent("attachment-drop-state")
        let app = AppModel(configuration: LaunchConfiguration(projectRoot: fixture, python: python, stateDirectory: state))
        defer { app.client.shutdown() }
        await app.start(); app.setProvider("mock")
        await app.bindWorkspace(fixture.path)
        app.section = .chat; app.setComposer("Inspect these files manually"); app.flushDraft()
        let bitmap = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: 1448, pixelsHigh: 850,
                                      bitsPerSample: 8, samplesPerPixel: 3, hasAlpha: false, isPlanar: false,
                                      colorSpaceName: .deviceRGB, bytesPerRow: 4344, bitsPerPixel: 24)!
        arc4random_buf(bitmap.bitmapData!, bitmap.bytesPerRow * bitmap.pixelsHigh)
        let image = fixture.appendingPathComponent("drop-large.png")
        let bytes = bitmap.representation(using: .png, properties: [:])!
        try bytes.write(to: image)
        let note = fixture.appendingPathComponent("drop-note.txt")
        try Data("Plain local drop fixture.\n".utf8).write(to: note)
        let unsupported = fixture.appendingPathComponent("drop-unsupported.pdf")
        try Data("%PDF-not a text attachment".utf8).write(to: unsupported)
        let outside = root.appendingPathComponent("outside-drop.txt")
        try Data("Outside workspace fixture".utf8).write(to: outside)
        let symlink = fixture.appendingPathComponent("drop-link.png")
        try FileManager.default.createSymbolicLink(at: symlink, withDestinationURL: image)
        let before = try fileBytes(state), sources = try fileBytes(fixture)
        await app.previewDroppedAttachments([image, note])
        guard let preview = app.attachmentDropPreview else { throw NativeError.message(app.error ?? "Missing drop preview") }
        try check(bytes.count > 3_500_000 && preview.images.count == 1 && preview.files.count == 1,
                  "Mixed drop previews a realistic 3.7 MB PNG and a workspace text file through stdio")
        try check(try fileBytes(state) == before && fileBytes(fixture) == sources && !app.cloudConsent && app.workSessions.isEmpty,
                  "Drop preview is read-only, with no cloud call, run, permissions or attachment save")
        await app.submit("Must not send while the preview is open")
        try check(app.messages.isEmpty && (try fileBytes(state)) == before,
                  "Enter/Send cannot start a turn while an attachment preview is open")
        app.attachmentDropPreview = nil
        try check(try fileBytes(state) == before && app.selected?.pendingImages.isEmpty == true && app.selected?.pendingFiles.isEmpty == true,
                  "Cancelling a mixed drop preserves draft and files byte-for-byte")
        try app.attachDrop(preview)
        let saved = try ChatStore(directory: state).load().conversations[0]
        try check(saved.pendingImages == preview.images.map(\.source.value) && saved.pendingFiles == preview.files.map(\.metadata) && saved.draft == "Inspect these files manually",
                  "Explicit mixed attachment saves only bounded metadata and preserves draft text")
        try check(try fileBytes(fixture) == sources && !String(decoding: Data(contentsOf: app.store.url), as: UTF8.self).contains("data_base64"),
                  "No original is copied, modified or embedded in private chat JSON")
        let restored = AppModel(configuration: LaunchConfiguration(projectRoot: fixture, python: python, stateDirectory: state))
        try check(restored.selected?.pendingImages == saved.pendingImages && restored.selected?.pendingFiles == saved.pendingFiles && restored.imageThumbnails.isEmpty,
                  "Mixed dropped attachments survive restart without reading pixels or auto-send")
        let composer = NSHostingController(rootView: ComposerView(model: restored))
        try check(composer.sizeThatFits(in: CGSize(width: 640, height: 900)).height < 340,
                  "Restored mixed attachments keep composer compact")
        let attachedState = try fileBytes(state)
        for urls in [[image, unsupported], [outside], [symlink], [URL(string: "https://example.invalid/test.png")!], [image, image], Array(repeating: note, count: 7)] {
            app.error = nil
            await app.previewDroppedAttachments(urls)
            try check(app.attachmentDropPreview == nil && app.error != nil && !app.loadingDroppedAttachments && (try fileBytes(state)) == attachedState,
                      "Invalid/mixed drop fails atomically without changing existing attachments: \(urls.count) items / \(urls[0].lastPathComponent)")
        }
        app.error = nil
        let provider = NSItemProvider()
        provider.registerDataRepresentation(forTypeIdentifier: "public.file-url", visibility: .all) { completion in
            completion(Data(note.absoluteString.utf8), nil); return nil
        }
        try check(app.receiveAttachmentDrop([provider]) && app.loadingDroppedAttachments && !app.receiveAttachmentDrop([provider]),
                  "Drop immediately reserves one preview; concurrent drop is refused")
        for _ in 0..<100 where app.loadingDroppedAttachments { try await Task.sleep(nanoseconds: 20_000_000) }
        try check(app.attachmentDropPreview?.files.count == 1 && !app.loadingDroppedAttachments && (try fileBytes(state)) == attachedState,
                  "Async Finder provider completes preview without metadata writes")
        app.attachmentDropPreview = nil
        var changedWorkspace = app.selected!
        changedWorkspace.workspacePath = root.path
        var refused = false
        do { _ = try preview.merged(with: changedWorkspace) } catch { refused = true }
        try check(refused, "A stale drop cannot attach after changing workspace")
        app.newConversation()
        let afterSwitch = try fileBytes(state)
        refused = false
        do { try app.attachDrop(preview) } catch { refused = true }
        try check(refused && (try fileBytes(state)) == afterSwitch, "A stale drop cannot attach to a different conversation")
        let badState = root.appendingPathComponent("corrupt-drop-state")
        try FileManager.default.createDirectory(at: badState, withIntermediateDirectories: true)
        let badHistory = badState.appendingPathComponent("conversations.json")
        try Data("broken".utf8).write(to: badHistory)
        let blocked = AppModel(configuration: LaunchConfiguration(projectRoot: fixture, python: python, stateDirectory: badState))
        let raw = try await app.client.request("image_preview", ["path": .string(image.path)])
        let blockedImage = try NativeImagePreview(raw, conversationID: blocked.selectedID!, canAttach: true)
        let blockedDrop = NativeAttachmentDropPreview(conversationID: blocked.selectedID!, workspace: nil, images: [blockedImage], files: [])
        refused = false
        do { try blocked.attachDrop(blockedDrop) } catch { refused = true }
        try check(refused && blocked.selected?.pendingImages.isEmpty == true && (try Data(contentsOf: badHistory)) == Data("broken".utf8),
                  "Failed drop save rolls back all attachment changes and preserves corrupt history")
        try check(try fileBytes(fixture) == sources && !app.cloudConsent && app.workSessions.isEmpty,
                  "All drop refusal/recovery paths leave source stores and permissions unchanged")
    }

    @MainActor
    static func taskCriteria(root: URL) throws {
        try check(try NativeTaskCriteria.parse("First criterion\n\n  Second criterion  ") == ["First criterion", "Second criterion"],
                  "Criteria editor normalizes explicit one-line requirements")
        for invalid in [[""], ["line\nbreak"], ["same", "SAME"], [String(repeating: "x", count: 301)], (0..<9).map(String.init)] {
            var refused = false
            do { _ = try NativeTaskCriteria.validate(invalid) } catch { refused = true }
            try check(refused, "Criteria bounds and duplicates are rejected: \(invalid.count) items")
        }
        let state = root.appendingPathComponent("task-criteria")
        let app = AppModel(configuration: LaunchConfiguration(projectRoot: root, python: root, stateDirectory: state))
        let id = app.selectedID!
        _ = NSHostingController(rootView: TaskCriteriaView(model: app)).sizeThatFits(in: CGSize(width: 800, height: 800))
        try check(!FileManager.default.fileExists(atPath: state.path) && app.selected!.pendingCriteria.isEmpty,
                  "Opening criteria editor does not create files or fill in requirements")
        try app.setPendingCriteria(["Keep original"], conversationID: id)
        let before = try fileBytes(state)
        let restored = try ChatStore(directory: state).load()
        try check(restored.conversations.first?.pendingCriteria == ["Keep original"] && restored.version == 5,
                  "Explicit criteria persist in the private draft across restart")
        try check(try fileBytes(state) == before && !app.cloudConsent && !app.fullAccessEnabled && !app.client.connected,
                  "Reading criteria never enables a model or tool access")
        var wrongChat = false
        do { try app.setPendingCriteria(["Wrong chat"], conversationID: UUID()) } catch { wrongChat = true }
        try check(wrongChat && (try fileBytes(state)) == before, "Stale criteria editor cannot save into another conversation")
        try app.setPendingCriteria([], conversationID: id)
        try check(app.selected!.pendingCriteria.isEmpty, "Clearing criteria is an explicit draft-only action")
        let blocked = root.appendingPathComponent("blocked-criteria")
        try FileManager.default.createDirectory(at: blocked, withIntermediateDirectories: true)
        try Data("not json".utf8).write(to: blocked.appendingPathComponent("conversations.json"))
        let broken = AppModel(configuration: LaunchConfiguration(projectRoot: root, python: root, stateDirectory: blocked))
        var saveFailed = false
        do { try broken.setPendingCriteria(["Not durable"], conversationID: broken.selectedID!) } catch { saveFailed = true }
        try check(saveFailed && broken.selected!.pendingCriteria.isEmpty && (try Data(contentsOf: blocked.appendingPathComponent("conversations.json"))) == Data("not json".utf8),
                  "Failed criteria persistence restores the old draft without overwriting corrupt history")
    }

    @MainActor
    static func manualReview(app: AppModel, fixture: URL, state: URL, python: URL) async throws {
        let criteria = ["Produce a readable response", "Do not execute commands"]
        try app.setPendingCriteria(criteria, conversationID: app.selectedID!)
        app.setComposer("/commands status"); app.flushDraft()
        await app.refreshContextPreview()
        try check(app.contextPreview?.manifest["success_criteria"].isNull == true && app.contextPreview?.value["excluded_criterion_count"].integer == 2,
                  "Operator context preview explicitly excludes pending criteria")
        await app.submit()
        try check(app.selected!.pendingCriteria == criteria, "Operator command does not consume draft criteria")
        app.setComposer("Provide a brief response for this local fixture."); app.flushDraft()
        let contextBefore = try fileBytes(state), coreBefore = try fileBytes(fixture)
        await app.refreshContextPreview()
        try check(app.contextPreview?.manifest["success_criteria"]["items"].items.map({ $0["text"].text }) == criteria,
                  "Context desk exposes the exact operator criteria that Send will use")
        try check(try fileBytes(state) == contextBefore && fileBytes(fixture) == coreBefore, "Criteria preview remains read-only")
        await app.submit()
        guard let run = app.workSessions.first else { throw NativeError.message("Missing criteria run") }
        try check(run.value["success_criteria"]["items"].items.map { $0["text"].text } == criteria && app.selected!.pendingCriteria.isEmpty,
                  "Successful normal turn freezes its criteria and consumes the draft only once")
        let unchecked: JSONValue = .object(["decision": .string("accepted"), "checks": .array([.string("met"), .string("not_checked")]), "note": .string("")])
        let selected: JSONValue = .object(["decision": .string("accepted"), "checks": .array([.string("met"), .string("met")]), "note": .string("Manually checked in UI fixture")])
        let before = try fileBytes(state), targetsBefore = try fileBytes(fixture)
        let refused = try await app.previewManualReview(run, selection: unchecked)
        let ready = try await app.previewManualReview(run, selection: selected)
        try check(!refused.ready && !refused.reasons.isEmpty && ready.ready, "Manual acceptance requires every declared criterion to be checked")
        try check(try fileBytes(state) == before && fileBytes(fixture) == targetsBefore, "Manual-review preview never writes evidence or target stores")
        guard case .object(var invalid) = ready.value else { throw NativeError.message("Expected review preview") }
        invalid["no_execution"] = .bool(false)
        var badPreview = false
        do { _ = try NativeManualReviewPreview(.object(invalid), run: run, selection: selected) } catch { badPreview = true }
        try check(badPreview, "Review preview refuses an execution-bearing response")
        let saved = try await app.saveManualReview(run, preview: ready)
        let after = try fileBytes(state)
        let changed = Set(before.keys).union(after.keys).filter { before[$0] != after[$0] }
            .map { URL(fileURLWithPath: $0).resolvingSymlinksInPath().path }.sorted()
        let expected = state.appendingPathComponent("work_sessions/" + run.id + ".json").resolvingSymlinksInPath().path
        let targetsAfter = try fileBytes(fixture)
        let targetChanges = Set(targetsBefore.keys).union(targetsAfter.keys).filter { targetsBefore[$0] != targetsAfter[$0] }.sorted()
        try check(changed == [expected] && targetChanges.isEmpty,
                  "Confirming manual review changes exactly one private run file, not chat, core or workspace")
        try check(saved.value["acceptance"].text == "operator_accepted" && saved.value["verification"].text == "not_assessed"
                  && saved.value["operator_reviews"].items.count == 1 && saved.state == "completed" && !app.fullAccessEnabled,
                  "Manual acceptance is labelled operator-reported and never an automatic verification or grant")
        let desk = try await app.inspectArtifacts(saved)
        try check(desk.value["verification"]["acceptance"].text == "operator_accepted", "Results desk shows manual review separately from command evidence")
        var replayRefused = false
        do { _ = try await app.saveManualReview(run, preview: ready) } catch { replayRefused = true }
        try check(replayRefused && (try fileBytes(state)) == after, "Replayed confirmation cannot append a duplicate manual review")
        let rework: JSONValue = .object(["decision": .string("needs_work"), "checks": .array([.string("met"), .string("not_met")]), "note": .string("A later manual check found a gap")])
        let next = try await app.previewManualReview(saved, selection: rework)
        let reviewed = try await app.saveManualReview(saved, preview: next)
        try check(reviewed.value["acceptance"].text == "operator_needs_work" && reviewed.value["operator_reviews"].items.count == 2
                  && reviewed.value["operator_reviews"].items[0] == saved.value["operator_reviews"].items[0],
                  "A later manual assessment preserves the earlier receipt rather than rewriting history")
        let restarted = AppModel(configuration: LaunchConfiguration(projectRoot: fixture, python: python, stateDirectory: state))
        defer { restarted.client.shutdown() }
        let restartBefore = try fileBytes(state)
        await restarted.start()
        try check(restarted.workSessions.first?.value["operator_reviews"].items.count == 2 && (try fileBytes(state)) == restartBefore,
                  "Manual review history survives a read-only restart without automatically resuming work")
    }

    @MainActor
    static func contextDesk(app: AppModel, fixture: URL, state: URL, source: URL) async throws {
        app.setComposer("Explain the selected source."); app.flushDraft()
        let original = try Data(contentsOf: source), nativeBefore = try fileBytes(state), coreBefore = try fileBytes(fixture)
        let messages = app.messages, selected = app.selectedID, files = app.selected?.pendingFiles
        await app.refreshContextPreview()
        guard let preview = app.contextPreview else { throw NativeError.message(app.contextPreviewError ?? "No context fixture") }
        try check(preview.sources.first?["state"].text == "ready" && preview.sources.first?["excerpt"].text.contains("WorkspaceReader") == true,
                  "Context desk shows a hash-checked selected excerpt through real read-only RPC")
        try check(preview.manifest["memory_scope"].text == "shared_core_not_workspace" && preview.manifest["recall"].text == "selected_at_send_not_previewed",
                  "Context desk distinguishes shared core memory from workspace files without invented recall")
        try check(preview.instructionPreview.value["provider"] == .string("mock")
                  && preview.instructionPreview.layers.isEmpty
                  && preview.instructionPreview.value["persona_state"] == .string("bypassed"),
                  "Context desk does not fabricate provider instructions for Mock")
        try check(preview.value["history"].items == app.selected?.history && preview.manifest["context_injection"]["enabled"] == .bool(false),
                  "Context desk shows the actual bounded conversation history and disabled injection")
        try check(app.messages == messages && app.selectedID == selected && app.selected?.pendingFiles == files && !app.busy && !app.fullAccessEnabled && !app.cloudConsent,
                  "Opening context desk never sends, authorizes, reselects files, or changes the conversation")
        try check(try fileBytes(state) == nativeBefore && fileBytes(fixture) == coreBefore, "Context desk leaves all Native/core/workspace/log bytes unchanged")
        guard case .object(let valid) = preview.value else { throw NativeError.message("Expected context object") }
        for (key, value) in [("schema", JSONValue.string("other")), ("no_execution", .bool(false)), ("read_only", .bool(false)), ("sources", .null),
                             ("history", .array([.object(["role": .string("system"), "content": .string("do not render")])]))] {
            var bad = valid; bad[key] = value
            var refused = false
            do { _ = try NativeContextPreview(.object(bad)) } catch { refused = true }
            try check(refused, "Context desk rejects invalid \(key)")
        }
        var changed = original; changed.append(Data("\n# changed fixture\n".utf8))
        try changed.write(to: source)
        await app.refreshContextPreview()
        try check(app.contextPreview?.sources.first?["state"].text == "changed" && app.contextPreview?.sources.first?["excerpt"].text == ""
                  && app.selected?.pendingFiles == files, "Context refresh marks changed files without replacing selection or showing unchosen bytes as attached")
        try original.write(to: source)
        await app.refreshContextPreview()
        try check(app.contextPreview?.value["attachments_ready"] == .bool(true), "Manual refresh rechecks restored source bytes")
        var cloudParams = app.contextRequestParameters!
        cloudParams["provider"] = .string("codex"); cloudParams["cloud_consent"] = .bool(false)
        let cloud = try NativeContextPreview(await app.client.request("context_preview", cloudParams))
        try check(cloud.manifest["destination"].text == "openai_cloud" && cloud.value["cloud_consent"] == .bool(false) && !app.cloudConsent && app.account.isNull,
                  "Cloud context disclosure does not contact account/model endpoints or grant cloud consent")
        try check(cloud.manifest["recall"] == .string("read_only_current_projection_recomputed_at_send")
                  && cloud.instructionPreview.layers.map({ $0["id"].text }) == ["base_instructions", "developer_instructions"]
                  && cloud.instructionPreview.layers[1]["source"] == .string("chat_static_contract")
                  && cloud.instructionPreview.value["no_model_call"] == .bool(true)
                  && cloud.instructionPreview.value["no_thread_refresh"] == .bool(true)
                  && cloud.instructionPreview.value["provider_owned_instructions"]["available_to_proto_mind"] == .bool(false),
                  "Codex context exposes exact local instruction layers while keeping provider-owned instructions unavailable")
        try check(cloud.manifest["provider_thread"]["linked"] == .bool(false)
                  && cloud.value["history"].items == app.selected?.history,
                  "A new Codex thread previews one bounded continuity bootstrap without starting a provider turn")
        guard case .object(var cloudValue) = cloud.value,
              case .object(var instructionValue) = cloudValue["instruction_preview"],
              case .array(var instructionLayers) = instructionValue["layers"],
              case .object(var baseLayer) = instructionLayers.first else { throw NativeError.message("Missing instruction fixture") }
        baseLayer["text"] = .string("tampered local instructions")
        instructionLayers[0] = .object(baseLayer)
        instructionValue["layers"] = .array(instructionLayers)
        cloudValue["instruction_preview"] = .object(instructionValue)
        var instructionTamperRefused = false
        do { _ = try NativeContextPreview(.object(cloudValue)) } catch { instructionTamperRefused = true }
        try check(instructionTamperRefused, "Context desk rejects tampered local instruction text and SHA evidence")
        app.setComposer("включи контекст"); app.flushDraft()
        let beforeOperator = try fileBytes(state), beforeOperatorCore = try fileBytes(fixture)
        await app.refreshContextPreview()
        try check(app.contextPreview?.manifest["operator"] == .bool(true) && app.contextPreview?.sources.isEmpty == true
                  && app.pendingAction == nil && app.bootstrap["context_injection"] == .bool(false), "Preview of natural mutation remains an inert operator explanation")
        try check(try fileBytes(state) == beforeOperator && fileBytes(fixture) == beforeOperatorCore, "Operator context preview changes no files")
        app.setComposer(""); app.flushDraft()
    }

    @MainActor
    static func artifactDesk(app: AppModel, fixture: URL, state: URL) async throws {
        guard let original = app.workSessions.first(where: { $0.state == "completed" }), let conversation = app.selectedID,
              case .object(var raw) = try JSONDecoder().decode(JSONValue.self, from: Data(contentsOf: state.appendingPathComponent("work_sessions/" + original.id + ".json"))) else {
            throw NativeError.message("No artifact parent fixture")
        }
        let id = UUID().uuidString.lowercased(), source = fixture.appendingPathComponent("artifact-result.html")
        try Data("<script>never_execute()</script>\nfixture result".utf8).write(to: source)
        let file = try await app.client.request("workspace_read", ["workspace_root": .string(fixture.path), "path": .string("artifact-result.html")])
        raw["id"] = .string(id); raw["parent_run_id"] = nil; raw["artifact_snapshot"] = nil
        raw["tools"] = .array([
            .object(["id": .string("change"), "kind": .string("fileChange"), "status": .string("completed"),
                     "paths": .array([.string("artifact-result.html")]), "diff_preview": .string("-old\n+fixture result")]),
            .object(["id": .string("check"), "kind": .string("commandExecution"), "status": .string("completed"),
                     "command": .string("fixture only, never executed"), "exit_code": .number(0), "output_preview": .string("fixture observation")])
        ])
        let path = state.appendingPathComponent("work_sessions/" + id + ".json")
        try JSONEncoder().encode(JSONValue.object(raw)).write(to: path)
        await app.refreshWorkSessions()
        guard var run = app.workSessions.first(where: { $0.id == id }) else { throw NativeError.message("Fixture run missing") }
        let beforeLegacy = try fileBytes(state), coreBefore = try fileBytes(fixture)
        let legacy = try await app.inspectArtifacts(run)
        let artifactID = legacy.items[0]["id"].text
        let legacyPreview = try await app.inspectArtifact(artifactID, run: run)
        try check(legacyPreview.value["state"].text == "not_captured" && legacyPreview.value["artifact"]["sha256"].text.isEmpty,
                  "Legacy artifact preview never invents a historical file hash")
        try check(legacyPreview.value["current"]["preview"].text.contains("<script>") && legacyPreview.value["no_execution"].flag,
                  "Artifact HTML is plain text, not an executed document")
        try check(try fileBytes(state) == beforeLegacy && fileBytes(fixture) == coreBefore, "Legacy artifact inspection performs no migration or write")
        guard case .object(var captured) = legacy.items[0] else { throw NativeError.message("Expected artifact") }
        captured["state"] = .string("captured"); captured["path"] = .string("artifact-result.html"); captured["sha256"] = file["sha256"]
        raw["artifact_snapshot"] = .object(["schema": .string("proto_mind.native_artifacts.v1"), "run_id": .string(id),
            "capture_boundary": .string("turn_completion_not_tool_transaction"),
            "captured_at": raw["finished_at"] ?? .string("fixture"), "items": .array([.object(captured)]), "total": .number(1), "partial": .bool(false)])
        try JSONEncoder().encode(JSONValue.object(raw)).write(to: path)
        var staleRefused = false
        do { _ = try await app.inspectArtifacts(run) } catch { staleRefused = true }
        try check(staleRefused, "Changed durable evidence invalidates the old artifact reference")
        await app.refreshWorkSessions()
        run = app.workSessions.first { $0.id == id }!
        let before = try fileBytes(state)
        let desk = try await app.inspectArtifacts(run), preview = try await app.inspectArtifact(artifactID, run: run)
        try check(desk.items.count == 1 && desk.value["verification"]["exit_zero"].integer == 1 && desk.value["verification"]["status"].text == "not_assessed",
                  "Artifact desk separates observed exit zero from task success and acceptance")
        try check(preview.value["state"].text == "current" && preview.value["diff_preview"].text.contains("+fixture result"),
                  "Artifact desk shows a run-linked diff and current hash match")
        try check(try fileBytes(state) == before && fileBytes(fixture) == coreBefore && app.selectedID == conversation && !app.fullAccessEnabled,
                  "Artifact desk leaves private state, target files, context settings and permissions unchanged")
        try Data("later operator edit".utf8).write(to: source)
        let changed = try await app.inspectArtifact(artifactID, run: run)
        try check(changed.value["state"].text == "changed" && changed.value["current"]["preview"].text == "later operator edit",
                  "Artifact refresh distinguishes current disk bytes from saved completion evidence")
        guard case .object(let valid) = desk.value else { throw NativeError.message("Expected artifact desk") }
        for (key, value) in [("run_id", JSONValue.string(UUID().uuidString)), ("no_execution", .bool(false)), ("read_only", .bool(false)), ("commands", .null)] {
            var bad = valid; bad[key] = value
            var refused = false
            do { _ = try NativeArtifactDesk(.object(bad), run: run) } catch { refused = true }
            try check(refused, "Artifact desk rejects invalid \(key)")
        }
        var wrongArtifact = false
        do { _ = try NativeArtifactPreview(preview.value, run: run, artifactID: "another") } catch { wrongArtifact = true }
        try check(wrongArtifact, "Artifact preview cannot be relabelled as a different file")
    }

    @MainActor
    static func workSessions(app: AppModel, fixture: URL, state: URL, python: URL) async throws {
        await app.refreshWorkSessions()
        guard let parent = app.workSessions.first, let selected = app.selectedID else { throw NativeError.message("Missing durable run fixture") }
        try check(parent.state == "completed" && parent.title == "Ответ получен", "Durable Native card reports response receipt, not task success")
        try check(parent.value["verification"].text == "not_assessed" && parent.value["acceptance"].text == "not_recorded", "Run evidence does not invent verification or acceptance")
        let journal = state.appendingPathComponent("work_sessions")
        let historyBefore = try fileBytes(state), coreBefore = try fileBytes(fixture.appendingPathComponent("proto_mind/data"))
        let logsBefore = try fileBytes(fixture.appendingPathComponent("logs"))
        await app.refreshWorkSessions()
        try check(try historyBefore == fileBytes(state), "Reading durable Native work sessions changes no private files")
        guard case .object(let valid) = parent.value else { throw NativeError.message("Expected a run object") }
        for (key, value) in [("schema", JSONValue.string("unknown")), ("automatic_resume", .bool(true)),
                             ("verification", .string("passed")), ("display_status", .string("success"))] {
            var invalid = valid; invalid[key] = value
            var rejected = false
            do { _ = try NativeWorkSession(.object(invalid)) } catch { rejected = true }
            try check(rejected, "Run card rejects invalid \(key)")
        }
        var codexRun = valid
        codexRun["provider"] = .string("codex")
        codexRun["access_mode"] = .string("chat")
        codexRun["instruction_receipt"] = try instructionReceiptFixture()
        let receiptRun = try NativeWorkSession(.object(codexRun))
        try check(receiptRun.instructionReceipt?.layers.count == 2,
                  "Run card accepts a verified content-free instruction receipt")
        codexRun["access_mode"] = .string("full_access")
        var mismatchRefused = false
        do { _ = try NativeWorkSession(.object(codexRun)) } catch { mismatchRefused = true }
        try check(mismatchRefused, "Run card rejects instruction evidence from another access mode")
        app.setComposer("existing unsent draft"); app.flushDraft()
        let beforeRefused = try fileBytes(state)
        await app.prepareContinuation(parent)
        try check(app.workSessionsActionError != nil && app.composer == "existing unsent draft" && app.selected?.draftContinuation == nil && (try fileBytes(state)) == beforeRefused,
                  "Preparing a continuation cannot replace an existing draft")
        app.error = nil; app.setComposer(""); app.flushDraft()
        let beforeJournal = try fileBytes(journal), messages = app.messages
        await app.prepareContinuation(parent)
        try check(app.error == nil && app.composer.contains("новый запрос") && app.selected?.draftContinuation == parent.reference,
                  "Manual recovery prepares a labelled reconstruction draft")
        try check(app.messages == messages && !app.busy && !app.cloudConsent && !app.fullAccessEnabled && app.selected?.pendingFiles.isEmpty == true,
                  "Continuation preparation sends nothing and restores no cloud, tools, or attachments")
        try check(try fileBytes(journal) == beforeJournal && fileBytes(fixture.appendingPathComponent("proto_mind/data")) == coreBefore
                  && fileBytes(fixture.appendingPathComponent("logs")) == logsBefore, "Continuation preparation changes only the explicitly edited Native draft")
        let persisted = try ChatStore(directory: state).load().conversations.first { $0.id == selected }
        try check(persisted?.draftContinuation == parent.reference && persisted?.draft == app.composer, "Draft reference survives restart without containing a permission token")
        let privateBeforeRestart = try fileBytes(state)
        let restarted = AppModel(configuration: LaunchConfiguration(projectRoot: fixture, python: python, stateDirectory: state))
        await restarted.start()
        try check(restarted.selected?.draftContinuation == parent.reference && restarted.composer == app.composer && !restarted.fullAccessEnabled,
                  "Restart restores a continuation draft but not a running turn or Full Mac grant")
        try check(try fileBytes(state) == privateBeforeRestart, "Restart reads evidence without rewriting history or runs")
        restarted.client.shutdown()
        let count = app.workSessions.count
        await app.submit()
        try check(app.messages.last?.isError == false && app.workSessions.count == count + 1
                  && app.workSessions.first?.value["parent_run_id"].text == parent.id, "Only explicit Send creates one new continuation turn")
        let afterChild = try fileBytes(journal)
        await app.prepareContinuation(parent)
        try check(app.error != nil && app.workSessionsActionError != nil && app.composer.isEmpty && (try fileBytes(journal)) == afterChild, "A used continuation parent cannot be replayed by the recovery button")
        app.error = nil
        app.setComposer("manual replacement")
        try check(app.selected?.draftContinuation == nil, "A new manually prepared draft does not inherit continuation metadata")
        app.setComposer(""); app.flushDraft()

        let raw = try JSONDecoder().decode(JSONValue.self, from: Data(contentsOf: journal.appendingPathComponent(parent.id + ".json")))
        guard case .object(var interrupted) = raw else { throw NativeError.message("Expected stored run") }
        let interruptedID = UUID().uuidString.lowercased()
        interrupted["id"] = .string(interruptedID); interrupted["status"] = .string("dispatching")
        interrupted["finished_at"] = nil; interrupted["answer_preview"] = nil
        interrupted["artifact_snapshot"] = nil
        interrupted["tools"] = .array([.object(["id": .string("unfinished"), "kind": .string("commandExecution"), "status": .string("inProgress")])])
        try JSONEncoder().encode(JSONValue.object(interrupted)).write(to: journal.appendingPathComponent(interruptedID + ".json"))
        let beforeRecoveryRead = try fileBytes(state)
        await app.refreshWorkSessions()
        let unknown = app.workSessions.first { $0.id == interruptedID }
        try check(unknown?.needsReview == true && unknown?.title == "Исход неизвестен"
                  && unknown?.value["tools"].items.first?["status"].text == "unknown", "Recovered unfinished work is visibly unknown, never silently successful")
        try check(try fileBytes(state) == beforeRecoveryRead, "Recovery display performs no automatic repair or replay")
    }

    @MainActor
    static func workSessionNotices(app: AppModel, fixture: URL, state: URL, python: URL) async throws {
        guard let run = app.workSessions.first(where: \.needsReview), let original = app.selected,
              let completed = app.workSessions.first(where: { $0.state == "completed" }) else {
            throw NativeError.message("Missing work-notice fixtures")
        }
        let journal = state.appendingPathComponent("work_sessions")
        let journalBefore = try fileBytes(journal), sourcesBefore = try fileBytes(fixture), before = try fileBytes(state)
        try check(app.hasWorkSessionNotice && app.workSessionNoticeToShow?.id == run.id, "An old unfinished run produces a scoped notice, not a live running state")
        app.openWorkSessions(run)
        try check(app.showWorkSessions && app.inspectedWorkSessionID == run.id && (try fileBytes(state)) == before,
                  "Opening a warning selects that run rather than the newest successful reply and writes nothing")
        app.showWorkSessions = false
        try app.setWorkSessionWarningHidden(run, hidden: true)
        var expected = original
        expected.dismissedWorkSessionWarnings = [try NativeWorkSessionNotice(run)]
        let after = try fileBytes(state)
        let changed = Set(before.keys).union(after.keys).filter { before[$0] != after[$0] }
            .map { URL(fileURLWithPath: $0).resolvingSymlinksInPath().path }.sorted()
        try check(changed == [app.store.url.resolvingSymlinksInPath().path] && app.selected == expected,
                  "Explicit hiding changes only display metadata in private conversation history")
        try check(!app.hasWorkSessionNotice && app.isWorkSessionWarningHidden(run)
                  && app.workSessions.first(where: { $0.id == run.id }) == run && run.needsReview,
                  "Hiding removes the banner but keeps the unknown run visible and unaccepted in its journal")
        try check(app.selected?.history == original.history && app.messages == original.messages && !app.cloudConsent && !app.fullAccessEnabled,
                  "Dismissal never becomes model context, a permission grant, a retry or manual acceptance")
        try app.setWorkSessionWarningHidden(run, hidden: true)
        try check(try fileBytes(state) == after, "Hiding the same observed warning twice is a no-write operation")

        let restarted = AppModel(configuration: LaunchConfiguration(projectRoot: fixture, python: python, stateDirectory: state))
        defer { restarted.client.shutdown() }
        await restarted.start()
        try check(restarted.isWorkSessionWarningHidden(run) && !restarted.hasWorkSessionNotice && (try fileBytes(state)) == after,
                  "Hidden notice survives restart without rewriting history or changing run evidence")
        try app.setWorkSessionWarningHidden(run, hidden: false)
        try check(app.hasWorkSessionNotice && app.selected?.dismissedWorkSessionWarnings.isEmpty == true,
                  "The journal can explicitly restore a hidden banner without altering its run")
        try app.setWorkSessionWarningHidden(run, hidden: true)
        try check(try fileBytes(journal) == journalBefore && fileBytes(fixture) == sourcesBefore,
                  "Hide and show preserve all work-session, core, export, source and log bytes")

        for busy in [true, false] {
            app.busy = busy
            if !busy { app.selectedID = UUID() }
            let snapshot = try fileBytes(state)
            var refused = false
            do { try app.setWorkSessionWarningHidden(run, hidden: false) } catch { refused = true }
            app.busy = false; app.selectedID = original.id
            try check(refused && (try fileBytes(state)) == snapshot,
                      busy ? "Active work blocks warning preference writes" : "A notice from another selected conversation cannot be hidden or restored")
        }
        var completedRefused = false
        do { try app.setWorkSessionWarningHidden(completed, hidden: true) } catch { completedRefused = true }
        try check(completedRefused, "Completed runs do not acquire unfinished-warning dismissal metadata")

        let runFile = journal.appendingPathComponent(run.id + ".json")
        guard case .object(var raw) = try JSONDecoder().decode(JSONValue.self, from: Data(contentsOf: runFile)) else {
            throw NativeError.message("Expected notice source object")
        }
        raw["updated_at"] = .string("2026-08-31T16:00:00.000000Z")
        try JSONEncoder().encode(JSONValue.object(raw)).write(to: runFile)
        await app.refreshWorkSessions()
        guard let changedRun = app.workSessions.first(where: { $0.id == run.id }) else { throw NativeError.message("Changed notice missing") }
        try check(changedRun.reference != run.reference && !app.isWorkSessionWarningHidden(changedRun) && app.hasWorkSessionNotice,
                  "Changed evidence reopens its warning instead of inheriting an old dismissal")
        let driftBefore = try fileBytes(state)
        var staleRefused = false
        do { try app.setWorkSessionWarningHidden(run, hidden: true) } catch { staleRefused = true }
        try check(staleRefused && (try fileBytes(state)) == driftBefore, "A stale observed revision cannot hide a newer warning")
        try app.setWorkSessionWarningHidden(changedRun, hidden: true)

        let newID = UUID().uuidString.lowercased()
        raw["id"] = .string(newID)
        try JSONEncoder().encode(JSONValue.object(raw)).write(to: journal.appendingPathComponent(newID + ".json"))
        await app.refreshWorkSessions()
        guard let newRun = app.workSessions.first(where: { $0.id == newID }) else { throw NativeError.message("New notice missing") }
        try check(app.workSessionNoticeToShow?.id == newID && !app.isWorkSessionWarningHidden(newRun),
                  "New failed runs always surface even when previous warnings were hidden")
        try app.setWorkSessionWarningHidden(newRun, hidden: true)
        let twoHidden = try fileBytes(state)
        try app.setWorkSessionWarningHidden(changedRun, hidden: true)
        try check(try fileBytes(state) == twoHidden, "Repeated dismissal is idempotent even with multiple hidden runs")
        let badFile = journal.appendingPathComponent(UUID().uuidString.lowercased() + ".json")
        try Data("broken diagnostic fixture".utf8).write(to: badFile)
        await app.refreshWorkSessions()
        try check(app.workSessionsWarning != nil && app.workSessionNoticeToShow == nil && app.hasWorkSessionNotice,
                  "Unreadable/corrupt journal diagnostics cannot be suppressed by historical notice preferences")
        try FileManager.default.removeItem(at: badFile)
        await app.refreshWorkSessions()

        try check(NativeManualReview.unavailableReason(run)?.contains("Приёмка недоступна") == true,
                  "Unknown runs explain why acceptance is unavailable instead of exposing a dead form")
        try check(NativeManualReview.unavailableReason(completed) == nil && NativeManualReview.initialDecision(completed) == "needs_work",
                  "Completed replies without criteria default to an explained rework-only review")
        guard case .object(let view) = run.value else { throw NativeError.message("Expected notice view") }
        for state in ["not_started", "running", "preparing"] {
            var value = view; value["display_status"] = .string(state)
            let variant = try NativeWorkSession(.object(value))
            try check(NativeManualReview.unavailableReason(variant) != nil,
                      "Review gives an explicit explanation for \(state) work")
            if state != "not_started" {
                var refused = false
                do { _ = try NativeWorkSessionNotice(variant) } catch { refused = true }
                try check(refused, "Running/preparing work cannot be hidden through a historical notice record")
            }
        }
        let notice = try NativeWorkSessionNotice(run)
        guard case .object(let noticeObject) = try JSONDecoder().decode(JSONValue.self, from: JSONEncoder().encode(notice)) else {
            throw NativeError.message("Expected notice preference")
        }
        for (key, value) in [("runID", "not-an-id"), ("fingerprint", "short"), ("fingerprint", String(repeating: "z", count: 64)), ("state", "completed")] {
            var item = noticeObject; item[key] = .string(value)
            var refused = false
            do {
                let decoded = try JSONDecoder().decode(NativeWorkSessionNotice.self, from: JSONEncoder().encode(JSONValue.object(item)))
                try NativeWorkSessionNotice.validate([decoded])
            } catch { refused = true }
            try check(refused, "Malformed warning preference \(key) is refused")
        }
        var duplicatesRefused = false
        do { try NativeWorkSessionNotice.validate([notice, notice]) } catch { duplicatesRefused = true }
        try check(duplicatesRefused, "Duplicate warning IDs cannot create an ambiguous display preference")

        let legacyState = state.deletingLastPathComponent().appendingPathComponent("notice-legacy")
        try FileManager.default.createDirectory(at: legacyState, withIntermediateDirectories: true)
        let legacyFile = legacyState.appendingPathComponent("conversations.json")
        let legacyConversation = try JSONDecoder().decode(JSONValue.self, from: JSONEncoder().encode(original))
        guard case .object(var legacyFields) = legacyConversation else { throw NativeError.message("Expected legacy conversation") }
        legacyFields.removeValue(forKey: "dismissedWorkSessionWarnings")
        let legacy: JSONValue = .object(["version": .number(4), "selectedID": .string(original.id.uuidString), "conversations": .array([.object(legacyFields)])])
        let legacyBytes = try JSONEncoder().encode(legacy)
        try legacyBytes.write(to: legacyFile)
        let loaded = try ChatStore(directory: legacyState).load()
        try check(loaded.conversations[0].dismissedWorkSessionWarnings.isEmpty && (try Data(contentsOf: legacyFile)) == legacyBytes,
                  "Existing v4 history without notice preferences loads read-only with no warnings hidden")

        let corruptState = state.deletingLastPathComponent().appendingPathComponent("notice-save-failure")
        try FileManager.default.createDirectory(at: corruptState, withIntermediateDirectories: true)
        try FileManager.default.copyItem(at: journal, to: corruptState.appendingPathComponent("work_sessions"))
        let corruptBytes = Data("corrupt private history fixture".utf8)
        try corruptBytes.write(to: corruptState.appendingPathComponent("conversations.json"))
        let blocked = AppModel(configuration: LaunchConfiguration(projectRoot: fixture, python: python, stateDirectory: corruptState))
        defer { blocked.client.shutdown() }
        blocked.conversations = [original]; blocked.selectedID = original.id
        await blocked.refreshWorkSessions()
        let blockedBefore = try fileBytes(corruptState)
        var saveRefused = false
        do { try blocked.setWorkSessionWarningHidden(changedRun, hidden: true) } catch { saveRefused = true }
        try check(saveRefused && blocked.selected == original && !blocked.isWorkSessionWarningHidden(changedRun)
                  && (try fileBytes(corruptState)) == blockedBefore,
                  "Failed preference save restores the visible warning and preserves corrupt history and run files")
        try check(try fileBytes(fixture) == sourcesBefore && app.selected?.messages == original.messages && !app.cloudConsent && !app.fullAccessEnabled,
                  "Warning preferences and review explanations never mutate targets, execute tools or alter permissions")
    }

    @MainActor
    static func agentAccess(app: AppModel, fixture: URL, state: URL, python: URL) async throws {
        try check(app.bootstrap["agent"]["web_search"].text == "live_full_access_only"
                  && app.bootstrap["agent"]["computer_use"]["provider"].text == "openai_signed_local_service"
                  && app.bootstrap["agent"]["computer_use"]["scope"].text == "explicit_full_access_turn_only"
                  && app.bootstrap["agent"]["computer_use"]["persistent_grant"].flag == false,
                  "Native advertises verified Computer Use only behind a non-persistent Full Mac grant")
        app.setProvider("codex")
        app.cloudConsent = false
        app.requestAgentAccess()
        try check(app.pendingAgentAccess == nil && !app.fullAccessEnabled, "Cloud-off cannot grant tools")
        app.error = nil
        app.cloudConsent = true
        app.requestAgentAccess()
        try check(app.pendingAgentAccess != nil && !app.fullAccessEnabled, "Selecting full access first shows a separate confirmation")
        app.pendingAgentAccess = nil
        try check(!app.fullAccessEnabled && app.agentGrants.isEmpty, "Cancelling access sheet leaves chat isolated")
        let beforeData = try fileBytes(fixture.appendingPathComponent("proto_mind/data"))
        let beforeState = try fileBytes(state)
        app.error = "Earlier configuration warning"
        app.requestAgentAccess()
        await app.confirmAgentAccess()
        try check(app.fullAccessEnabled && app.agentGrants.count == 1 && app.account.isNull && app.error == nil, "Explicit grant clears stale errors without contacting Codex or starting generation")
        let grantedContext = app.contextRequestParameters
        try check(grantedContext?["access_mode"] == .string("full_access")
                  && grantedContext?["access_token"]?.text == app.agentGrants[app.selectedID!]?.token
                  && grantedContext?["persona_enabled"] == .bool(false),
                  "Context inspection receives the current in-memory Full Mac grant without inventing Persona state")
        try check(try fileBytes(state) == beforeState && fileBytes(fixture.appendingPathComponent("proto_mind/data")) == beforeData, "Grant creates no history/settings/core-store files")
        let restart = AppModel(configuration: LaunchConfiguration(projectRoot: fixture, python: python, stateDirectory: state))
        try check(restart.agentGrants.isEmpty && !restart.fullAccessEnabled && restart.cloudConsent, "Cloud consent survives restart but Full Mac permission does not")
        app.error = "Earlier configuration warning"
        await app.disableAgentAccess()
        try check(!app.fullAccessEnabled && app.agentGrants.isEmpty && app.error == nil, "Disable clears stale errors and returns to chat without a target command")
        try check(app.contextRequestParameters?["access_mode"] == .string("chat")
                  && app.contextRequestParameters?["access_token"] == nil,
                  "Disabling Full Mac immediately removes its token and mode from context inspection")
        app.requestAgentAccess()
        await app.confirmAgentAccess()
        app.setProvider("mock")
        try check(!app.fullAccessEnabled && app.agentGrants.isEmpty, "Changing provider discards tool permission")
        app.setProvider("codex")
        app.requestAgentAccess()
        await app.confirmAgentAccess()
        app.cloudConsent = false
        try check(!app.fullAccessEnabled && app.agentGrants.isEmpty, "Revoking cloud permission also removes tool permission")
        try check(try fileBytes(fixture.appendingPathComponent("proto_mind/data")) == beforeData, "Agent permission UI never changes core records")
    }

    static func fileBytes(_ directory: URL) throws -> [String: Data] {
        guard let files = FileManager.default.enumerator(at: directory, includingPropertiesForKeys: [.isRegularFileKey]) else { return [:] }
        var result: [String: Data] = [:]
        for case let file as URL in files where try file.resourceValues(forKeys: [.isRegularFileKey]).isRegularFile == true {
            result[file.path] = try Data(contentsOf: file)
        }
        return result
    }

    @MainActor
    static func library(app: AppModel, fixture: URL, state: URL) async throws {
        let data = fixture.appendingPathComponent("proto_mind/data")
        let goal = data.appendingPathComponent("goals.jsonl")
        let skills = data.appendingPathComponent("skills.jsonl")
        try Data("{\"id\":\"goal-native\",\"title\":\"Native continuity\",\"description\":\"Read only fixture\",\"priority\":\"high\",\"focus\":true,\"status\":\"active\"}\n".utf8).write(to: goal)
        try Data("{\"id\":\"skill-native\",\"name\":\"Inspect records\",\"summary\":\"Stored procedure\",\"body\":\"<script>literal data</script> Never execute me.\",\"uses\":4}\n{\"id\":\"skill-old\",\"name\":\"Historical procedure\",\"status\":\"archived\"}\n".utf8).write(to: skills)
        app.setComposer("preserve this draft")
        app.flushDraft()
        let storesBefore = try fileBytes(data), stateBefore = try fileBytes(state)
        let logsBefore = try fileBytes(fixture.appendingPathComponent("logs"))
        let messagesBefore = app.messages, selectedBefore = app.selectedID, providerBefore = app.selected?.provider
        await app.showLibrary(.memory)
        try check(app.section == .memory && app.libraryError == nil && (app.libraryPage?.matchingRecords ?? 0) > 0, "Native memory list decodes existing core records")
        let memory = app.libraryPage!.items.first!
        await app.inspectLibrary(memory)
        try check(app.libraryDetail?.item?.recordId == memory.recordId && app.libraryDetail?.blocks.first?.key == "content", "Memory card decodes source identity and content")
        try check(app.libraryDetail?.memoryEvidence?.status == "UNAVAILABLE" && app.libraryDetail?.memoryEvidence?.isSafe == true,
                  "Memory card refuses to invent provenance for a legacy record")
        app.openMemoryWorkshop()
        await app.refreshMemoryWorkshop()
        try check(app.memoryWorkshop?.status == "EMPTY" && app.memoryWorkshop?.readOnly == true &&
                  app.memoryWorkshop?.scope.projectIsolationEnforced == false,
                  "Memory Workshop opens without creating pilot state or claiming project isolation")
        let workshopValue = try await app.client.request("memory_workshop", [
            "conversation_id": .string(app.selected!.id.uuidString),
        ])
        _ = try NativeMemoryWorkshop.decode(workshopValue, conversationId: app.selected!.id.uuidString)
        if case .object(var unsafeWorkshop) = workshopValue {
            unsafeWorkshop["automatic_promotion"] = .bool(true)
            var rejected = false
            do { _ = try NativeMemoryWorkshop.decode(.object(unsafeWorkshop), conversationId: app.selected!.id.uuidString) }
            catch { rejected = true }
            try check(rejected, "Memory Workshop rejects an automatic-promotion claim")
        }
        app.showMemoryWorkshop = false

        await app.showLibrary(.goals)
        try check(app.libraryPage?.items.first?.focused == true && app.libraryPage?.items.first?.priority == "high", "Goal screen shows stored focus and priority")
        await app.inspectLibrary(app.libraryPage!.items.first!)
        try check(app.libraryDetail?.blocks.last?.text == "Read only fixture", "Goal detail shows original description")

        await app.showLibrary(.skills)
        let skill = app.libraryPage!.items.first!
        try check(app.libraryPage?.matchingRecords == 1 && skill.recordId == "skill-native", "Skills screen defaults to active records")
        await app.inspectLibrary(skill)
        try check(app.libraryDetail?.blocks.last?.text.contains("<script>") == true && app.libraryDetail?.fields.contains { $0.key == "uses" && $0.value == "4" } == true, "Skill procedure is plain stored text with unchanged usage metadata")
        app.libraryFilter = .history
        await app.loadLibraryPage()
        try check(app.libraryPage?.items.first?.recordId == "skill-old" && app.libraryDetail == nil, "History filter excludes active skill and clears prior detail")
        app.libraryFilter = .all; app.libraryQuery = "INSPECT RECORDS"
        await app.loadLibraryPage()
        try check(app.libraryPage?.matchingRecords == 1 && app.libraryPage?.items.first?.recordId == skill.recordId, "Native explicit search is case-insensitive")
        app.libraryQuery = "no such text"
        await app.loadLibraryPage()
        try check(app.libraryPage?.items.isEmpty == true && app.libraryError == nil, "Empty search is a normal result")
        await app.showLibrary(.skills)
        let pageEnvelope = try await app.client.request("capability_search", ["collection": .string("skills")])
        let detailEnvelope = try await app.client.request("capability_fetch", ["collection": .string("skills"), "record_key": .string(skill.id)])
        let pageValue = try LocalKnowledgeEnvelope.structured(pageEnvelope, capability: "search")
        let detailValue = try LocalKnowledgeEnvelope.structured(detailEnvelope, capability: "fetch")
        try libraryContracts(page: pageValue, detail: detailValue, record: skill.id)
        var wrongCapabilityRejected = false
        do { _ = try LocalKnowledgeEnvelope.structured(pageEnvelope, capability: "fetch") } catch { wrongCapabilityRejected = true }
        try check(wrongCapabilityRejected, "Local knowledge envelope binds structured data to the requested capability")
        var unsafeEnvelope = pageEnvelope
        if case .object(var root) = unsafeEnvelope, case .object(var meta) = root["_meta"], case .object(var local) = meta["proto_mind"] {
            local["network_access"] = .bool(true); meta["proto_mind"] = .object(local); root["_meta"] = .object(meta); unsafeEnvelope = .object(root)
        }
        var unsafeEnvelopeRejected = false
        do { _ = try LocalKnowledgeEnvelope.structured(unsafeEnvelope, capability: "search") } catch { unsafeEnvelopeRejected = true }
        try check(unsafeEnvelopeRejected, "Local knowledge envelope rejects a widened network boundary")
        try check(try fileBytes(data) == storesBefore && fileBytes(state) == stateBefore && fileBytes(fixture.appendingPathComponent("logs")) == logsBefore, "Library views leave core stores, native history/settings, and session log bytes unchanged")
        try check(app.messages == messagesBefore && app.selectedID == selectedBefore && app.selected?.provider == providerBefore && app.composer == "preserve this draft" && !app.cloudConsent, "Library navigation preserves conversation/draft/provider and does not enable cloud")

        try Data("{\"id\":\"skill-native\",\"name\":\"Changed externally\",\"body\":\"Fresh details\",\"uses\":4}\n".utf8).write(to: skills)
        await app.inspectLibrary(skill)
        try check(app.libraryDetail?.changedSinceList == true && app.libraryDetail?.blocks.last?.text == "Fresh details", "Card reload exposes source changes after list preview")
        try Data("broken JSONL\n".utf8).write(to: skills)
        await app.inspectLibrary(skill)
        try check(app.libraryDetail?.item == nil && app.libraryDetail?.sources.first?.health == "ERROR", "Corrupt source clears old card instead of presenting stale details")
        await app.loadLibraryPage()
        try check(app.libraryPage?.items.isEmpty == true && app.libraryPage?.warnings.isEmpty == false, "Malformed library remains a readable diagnostic screen")
        app.libraryQuery = String(repeating: "x", count: 201)
        await app.loadLibraryPage()
        try check(app.libraryError != nil && app.libraryPage == nil && !app.loadingLibrary, "Rejected search reports an error and clears the loading state")
    }

    static func libraryContracts(page: JSONValue, detail: JSONValue, record: String) throws {
        guard case .object(let pageObject) = page, case .object(let detailObject) = detail else {
            throw NativeError.message("Library test requires object responses.")
        }
        let checks: [(String, JSONValue)] = [("schema", .string("unknown")), ("read_only", .bool(false)), ("collection", .string("memory")),
                                           ("items", .array([page["items"].items[0], page["items"].items[0]]))]
        for (field, invalid) in checks {
            var object = pageObject; object[field] = invalid
            var rejected = false
            do { _ = try LibraryPage.decode(.object(object), for: .skills) } catch { rejected = true }
            try check(rejected, "Library page rejects invalid \(field)")
        }
        var wrongKeyRejected = false
        do { _ = try LibraryDetail.decode(detail, for: .skills, recordKey: "skills:other") } catch { wrongKeyRejected = true }
        try check(wrongKeyRejected, "Library detail cannot be assigned to another selected record")
        var oversized = detailObject
        oversized["blocks"] = .array([.object(["key": .string("body"), "text": .string(String(repeating: "x", count: 24001)), "truncated": .bool(false)])])
        var oversizedRejected = false
        do { _ = try LibraryDetail.decode(.object(oversized), for: .skills, recordKey: record) } catch { oversizedRejected = true }
        try check(oversizedRejected, "Library detail enforces bounded rendered text")
    }
}
