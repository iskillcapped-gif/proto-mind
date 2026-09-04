"""Core flow checks: cognitive."""
from __future__ import annotations

import unittest
from proto_mind.tests.flow_fixtures import (
    CARD_HINT_LIMIT,
    CARD_MEMORY_LIMIT,
    CARD_UNAVAILABLE_NOTICE,
    CARD_WARNING_LIMIT,
    COGNITIVE_TURN_SCHEMA,
    COGNITIVE_TURN_VERSION,
    COMMAND_REGISTRY,
    CognitiveTurnProjector,
    ContextInjectionAuditLog,
    Coordinator,
    ENVELOPE_UNAVAILABLE_WARNING,
    FrozenInstanceError,
    InteractiveResponse,
    MEMORY_PREVIEW_MAX_CHARS,
    MemoryHygiene,
    MemoryRecord,
    Path,
    REDACTION_PREFIX,
    ScriptedReasoner,
    SessionOperatorLogger,
    SimpleNamespace,
    SupervisedExperiencePilot,
    TemporaryDirectory,
    UTC,
    _format_interaction_result,
    _format_turn_notices,
    build_cognitive_turn_envelope,
    build_local_capability_card_html,
    build_test_cognitive_card_response,
    build_test_cognitive_card_ui,
    build_test_cognitive_turn_result,
    build_test_experience_events,
    build_test_system,
    classify_command,
    command_registry_doctor,
    datetime,
    deepcopy,
    desktop_app,
    format_cognitive_turn_episode,
    format_cognitive_turn_list,
    format_context_command,
    format_continuity_soak_report,
    get_experience_pilot,
    json,
    patch,
    process_interactive_input,
    process_interactive_input_with_envelope,
    project_cognitive_turn_card,
    project_interactive_response,
    pyside_app,
    replace,
    run_continuity_soak,
)


class CognitiveFlowTests(unittest.TestCase):
    def test_cognitive_turn_card_projects_typed_fields_without_parsing_answer(self) -> None:
        response = build_test_cognitive_card_response()
        card = project_cognitive_turn_card("What do you remember?", response)

        self.assertEqual(card.answer, response.cognitive_turn.response)
        self.assertIn("Observer: this line belongs to the answer", card.answer)
        self.assertEqual(card.intent, "continuity_followup")
        self.assertEqual(card.retrieval_mode, "current_state")
        self.assertEqual(card.backend, "scripted")
        self.assertEqual(card.memories[0].record_id, "turn-memory-1")
        self.assertEqual(card.memory_count, 1)
        self.assertEqual(card.grounding_status, "SUPPORTED")
        self.assertIn("aligned", card.reflection_summary)
        self.assertIn("No new memory record reported", card.memory_decision)

    def test_cognitive_turn_card_renders_escaped_markdown_and_metadata(self) -> None:
        result = build_test_cognitive_turn_result()
        result.response = "**Answer**\nObserver: keep this answer line.\n<script>bad()</script>\n```html\n<img src='https://example.invalid/x'>\n```"
        result.retrieved_memory[0].source = "<img src='file:///private/source'>"
        result.retrieved_memory[0].content = "<script>memory</script> & evidence"
        result.retrieved_memory[0].id = "<record-id>"
        result.grounding_audit.grounding_status = "<unsafe-status>"
        result.self_reflection.warnings = ["<warning> & uncertainty"]

        rendered = pyside_app.build_cognitive_turn_card_html("Normal request", build_test_cognitive_card_response(result))

        self.assertIn("<strong>Answer</strong>", rendered)
        self.assertIn("<pre><code>", rendered)
        self.assertIn("Observer: keep this answer line.", rendered)
        self.assertIn("&lt;script&gt;bad()&lt;/script&gt;", rendered)
        self.assertIn("&lt;record-id&gt;", rendered)
        self.assertIn("&lt;UNSAFE-STATUS&gt;", rendered)
        self.assertIn("&lt;warning&gt; &amp; uncertainty", rendered)
        self.assertNotIn("<script>", rendered)
        self.assertNotIn("<img", rendered)
        self.assertNotIn("<a ", rendered)
        self.assertNotIn("NOT_A_PROJECTED", rendered)
        self.assertIn("Retrieved", rendered.replace("RETRIEVED", "Retrieved"))
        self.assertIn("does not prove actual use", rendered)
        self.assertNotIn("Memory used:", rendered)

    def test_cognitive_turn_card_missing_audits_and_memory_remain_unknown(self) -> None:
        result = replace(build_test_cognitive_turn_result(), grounding_audit=None, self_reflection=None,
                         retrieval_trace=None, retrieved_memory=[], previous_correction_hints=[])
        response = build_test_cognitive_card_response(result)
        card = project_cognitive_turn_card("hello", response)
        rendered = pyside_app.build_cognitive_turn_card_html("hello", response)

        self.assertEqual(card.grounding_status, "UNKNOWN")
        self.assertEqual(card.grounding_tone, "unknown")
        self.assertEqual(card.retrieval_mode, "UNKNOWN")
        self.assertEqual(card.context_state, "UNKNOWN")
        self.assertIn("UNKNOWN", card.reflection_summary)
        self.assertEqual(card.memories, ())
        self.assertIn("No memory records were returned", rendered)
        self.assertNotIn("VERIFIED", rendered)

    def test_cognitive_turn_card_bounds_evidence_without_truncating_answer(self) -> None:
        result = build_test_cognitive_turn_result()
        result.response = "Full answer. " * 600
        result.retrieved_memory = [
            MemoryRecord(f"memory-{index} " * 100, "decision", 0.8, "operator", id=f"memory-{index}", active=index != 0)
            for index in range(5)
        ]
        result.grounding_audit.warnings = [f"warning-{index} " + "x" * 300 for index in range(6)]
        result.self_reflection.warnings = []
        result.self_reflection.suggested_next_turn_adjustments = [f"adjustment-{index}" for index in range(5)]
        result.self_reflection.correction_hints = []
        result.previous_correction_hints = [f"old-hint-{index}" for index in range(4)]
        response = build_test_cognitive_card_response(result)
        card = project_cognitive_turn_card("Recall history", response)
        rendered = pyside_app.build_cognitive_turn_card_html("Recall history", response)

        self.assertEqual(card.answer, result.response)
        self.assertEqual(len(card.memories), CARD_MEMORY_LIMIT)
        self.assertEqual(card.omitted_memories, 2)
        self.assertEqual(len(card.warnings), CARD_WARNING_LIMIT)
        self.assertEqual(card.omitted_warnings, 2)
        self.assertEqual(len(card.next_hints), CARD_HINT_LIMIT)
        self.assertEqual(card.omitted_next_hints, 3)
        self.assertEqual(card.omitted_previous_hints, 2)
        self.assertTrue(all(len(warning) <= 200 for warning in card.warnings))
        self.assertIn("inactive / historical", rendered)
        self.assertIn("2 more returned records not shown", rendered)
        self.assertIn("3 more items not shown", rendered)
        self.assertNotIn("warning-5", rendered)

    def test_cognitive_turn_card_reports_storage_receipts_not_requested_success(self) -> None:
        result = build_test_cognitive_turn_result()
        result.memory_summary.should_store = True
        pending = project_cognitive_turn_card("hello", build_test_cognitive_card_response(result))
        self.assertEqual(pending.memory_decision, "Storage requested; no stored record ID reported.")

        result.memory_summary.stored_record_id = "saved-memory"
        result.memory_summary.stored_record_type = "decision"
        result.memory_summary.promoted_record_ids = ["promoted-memory"]
        result.memory_summary.superseded_record_ids = ["older-memory"]
        stored = project_cognitive_turn_card("hello", build_test_cognitive_card_response(result))
        self.assertIn("Stored decision: saved-memory", stored.memory_decision)
        self.assertIn("Promoted: 1", stored.memory_decision)
        self.assertIn("Superseded: 1", stored.memory_decision)

    def test_cognitive_turn_card_refuses_operator_natural_exit_and_untyped_output(self) -> None:
        response = build_test_cognitive_card_response()
        for command in ("", "  ", "/daily doctor", "/memory remember text", "что делать дальше", "проверь систему", "exit", "/exit"):
            with self.subTest(command=command):
                self.assertIsNone(pyside_app.build_cognitive_turn_card_html(command, response))
        self.assertIsNone(pyside_app.build_cognitive_turn_card_html("hello", None))
        self.assertIsNone(pyside_app.build_cognitive_turn_card_html("hello", InteractiveResponse("Legacy text")))

    def test_cognitive_turn_card_falls_back_on_malformed_and_stale_payloads(self) -> None:
        response = build_test_cognitive_card_response()
        malformed = (
            replace(response, text="A different turn"),
            replace(response, cognitive_turn={"response": "not a typed envelope"}),
            replace(response, cognitive_turn=replace(response.cognitive_turn, response="Different answer")),
            replace(response, cognitive_turn=replace(response.cognitive_turn, retrieved_memories=[None])),
            replace(response, notices=["mutable notice"]),
            replace(response, envelope_warning="projection failed"),
        )
        for value in malformed:
            with self.subTest(value_type=type(value.cognitive_turn).__name__):
                self.assertIsNone(pyside_app.build_cognitive_turn_card_html("hello", value))
        for field, value in (("version", 2), ("version", True), ("projection_only", False), ("memory_scope", "proven_used")):
            altered = deepcopy(response)
            object.__setattr__(altered.cognitive_turn, field, value)
            self.assertIsNone(pyside_app.build_cognitive_turn_card_html("hello", altered))

    def test_cognitive_turn_card_preserves_structured_notices_without_scanning_answer(self) -> None:
        result = build_test_cognitive_turn_result()
        result.response += "\nExperience pilot: this line is part of the answer."
        injection = {"enabled": True, "applied": True, "mode": "preview_safe", "context_chars": 2000, "truncated": True}
        observation = SimpleNamespace(capture_performed=False, state="stopped", reason="safe stop\nObserver: not a delimiter")
        notices = _format_turn_notices(context_injection=injection, experience_pilot=observation)
        response = project_interactive_response(
            _format_interaction_result(result, notices=notices), result, context_injection=injection, notices=notices,
        )
        rendered = pyside_app.build_cognitive_turn_card_html("hello", response)

        self.assertEqual(response.notices, notices)
        self.assertEqual(len(notices), 2)
        self.assertIn("Context injection: enabled (preview_safe, 2000 chars, truncated)", rendered)
        self.assertIn("Experience pilot: stopped fail-closed", rendered)
        self.assertIn("Observer: not a delimiter", rendered)
        self.assertIn("Experience pilot: this line is part of the answer.", rendered)
        self.assertIn("Context Injection: APPLIED", rendered)

    def test_cognitive_turn_card_is_pure_and_repeatable(self) -> None:
        response = build_test_cognitive_card_response()
        before = response.to_dict()
        with (
            patch("pathlib.Path.open", side_effect=AssertionError("No files")),
            patch("socket.create_connection", side_effect=AssertionError("No network")),
            patch.object(Coordinator, "handle", side_effect=AssertionError("No second turn")),
        ):
            first = pyside_app.build_cognitive_turn_card_html("hello", response)
            second = pyside_app.build_cognitive_turn_card_html("hello", response)
        self.assertIsNotNone(first)
        self.assertEqual(first, second)
        self.assertEqual(response.to_dict(), before)

    def test_cognitive_turn_card_debug_and_renderer_failure_use_text_fallback(self) -> None:
        response = build_test_cognitive_card_response()
        with patch("proto_mind.pyside_app.project_cognitive_turn_card", side_effect=RuntimeError("projection failed")) as project:
            self.assertIsNone(pyside_app.build_cognitive_turn_card_html("hello", response, debug=True))
            project.assert_not_called()
            self.assertIsNone(pyside_app.build_cognitive_turn_card_html("hello", response))
        with patch("proto_mind.pyside_app.render_cognitive_turn_card_html", side_effect=RuntimeError("render failed")):
            self.assertIsNone(pyside_app.build_cognitive_turn_card_html("hello", response))

    def test_cognitive_turn_card_css_uses_existing_control_room_palette(self) -> None:
        stylesheet = pyside_app.pyside_chat_document_css()
        self.assertIn(".turn-card", stylesheet)
        self.assertIn(".turn-check-warn", stylesheet)
        self.assertIn(".turn-check-unknown", stylesheet)
        self.assertIn("#7fd8c4", stylesheet)
        self.assertIn("#d7a75b", stylesheet)

    @unittest.skipUnless(pyside_app.PYSIDE_AVAILABLE, "PySide6 is optional")
    def test_cognitive_turn_card_worker_processes_and_captures_once(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            coordinator, store, keeper = build_test_system(root / "proto_mind")
            logger = SessionOperatorLogger.from_project_root(root)
            coordinator.session_logger = logger
            runtime = desktop_app.DesktopRuntime(root, logger, coordinator, MemoryHygiene(store))
            pilot = get_experience_pilot(coordinator, project_root=root)
            pilot.preview()
            pilot.consent(pilot.expected_consent_phrase)
            worker = pyside_app.InputWorker(runtime, "I prefer concise answers.")
            outputs = []
            worker.finished.connect(outputs.append)
            with (
                patch.object(runtime, "process", side_effect=AssertionError("No second API")) as legacy,
                patch.object(coordinator.reasoner, "respond", wraps=coordinator.reasoner.respond) as respond,
                patch.object(keeper, "apply_memory_updates", wraps=keeper.apply_memory_updates) as update,
                patch.object(logger, "append_turn", wraps=logger.append_turn) as log,
                patch.object(pilot, "observe_normal_turn", wraps=pilot.observe_normal_turn) as capture,
                patch("proto_mind.main._format_turn_notices", wraps=_format_turn_notices) as notices,
            ):
                worker.run()
            self.assertEqual(len(outputs), 1)
            interaction = outputs[0]["interaction"]
            self.assertIsInstance(interaction, InteractiveResponse)
            self.assertEqual(outputs[0]["response"], interaction.text)
            self.assertIsNotNone(interaction.cognitive_turn)
            self.assertIn("Experience pilot: captured turn 1", interaction.notices[0])
            for call in (respond, update, log, capture, notices):
                call.assert_called_once()
            legacy.assert_not_called()
            self.assertEqual(len(store.load_persistent_memory()), 1)
            self.assertEqual(logger.status().entry_count, 1)
            self.assertEqual(pilot.captured_turns, 1)
            self.assertEqual(logger.tail(1)[0]["user_input"], "I prefer concise answers.")
            self.assertNotIn("cognitive_turn", logger.tail(1)[0])
            self.assertFalse((root / "proto_mind" / "data" / "context_injection.json").exists())

    @unittest.skipUnless(pyside_app.PYSIDE_AVAILABLE, "PySide6 is optional")
    def test_cognitive_turn_card_worker_operator_paths_never_run_reasoner(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            coordinator, store, _ = build_test_system(root / "proto_mind")
            logger = SessionOperatorLogger.from_project_root(root)
            runtime = desktop_app.DesktopRuntime(root, logger, coordinator, MemoryHygiene(store))
            before = {str(path.relative_to(root)): path.read_bytes() for path in root.rglob("*") if path.is_file()}
            with (
                patch.object(coordinator, "handle", side_effect=AssertionError("No turn")) as handle,
                patch("proto_mind.main.prepare_context_injection") as injection,
                patch.object(runtime, "process", side_effect=AssertionError("No legacy retry")) as legacy,
            ):
                for command in ("/daily doctor", "что делать дальше"):
                    outputs = []
                    worker = pyside_app.InputWorker(runtime, command)
                    worker.finished.connect(outputs.append)
                    worker.run()
                    self.assertEqual(len(outputs), 1)
                    self.assertIsNotNone(outputs[0]["response"])
                    self.assertIsNone(outputs[0]["interaction"].cognitive_turn)
                    self.assertEqual(outputs[0]["interaction"].notices, ())
                handle.assert_not_called()
                injection.assert_not_called()
                legacy.assert_not_called()
            after = {str(path.relative_to(root)): path.read_bytes() for path in root.rglob("*") if path.is_file()}
            self.assertEqual(before, after)

    @unittest.skipUnless(pyside_app.PYSIDE_AVAILABLE, "PySide6 is optional")
    def test_cognitive_turn_card_worker_failure_never_retries_legacy_path(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            coordinator, store, _ = build_test_system(root / "proto_mind")
            logger = SessionOperatorLogger.from_project_root(root)
            runtime = desktop_app.DesktopRuntime(root, logger, coordinator, MemoryHygiene(store))
            for failure in (RuntimeError("reasoner failed"), None):
                outputs = []
                worker = pyside_app.InputWorker(runtime, "hello")
                worker.finished.connect(outputs.append)
                with (
                    patch.object(runtime, "process_with_envelope", side_effect=failure, return_value="invalid result") as typed,
                    patch.object(runtime, "process", side_effect=AssertionError("No retry")) as legacy,
                ):
                    worker.run()
                typed.assert_called_once_with("hello")
                legacy.assert_not_called()
                self.assertEqual(len(outputs), 1)
                self.assertTrue(outputs[0]["response"].startswith("System error:"))
                self.assertIsNone(outputs[0]["interaction"])

    @unittest.skipUnless(pyside_app.PYSIDE_AVAILABLE, "PySide6 is optional")
    def test_cognitive_turn_card_worker_pre_cancel_does_not_process(self) -> None:
        runtime = SimpleNamespace(process_with_envelope=lambda _: self.fail("Cancelled worker executed"))
        outputs = []
        worker = pyside_app.InputWorker(runtime, "hello")
        worker.finished.connect(outputs.append)
        worker.request_cancel()
        worker.run()
        self.assertEqual(len(outputs), 1)
        self.assertTrue(outputs[0]["cancelled"])
        self.assertIsNone(outputs[0]["response"])

    @unittest.skipUnless(pyside_app.PYSIDE_AVAILABLE, "PySide6 is optional")
    def test_cognitive_turn_card_worker_result_forwards_the_same_envelope(self) -> None:
        response = build_test_cognitive_card_response()
        calls = []
        ui = SimpleNamespace(_finish_response=lambda text, **kwargs: calls.append((text, kwargs)))
        pyside_app.ProtoMindPySideApp._finish_worker_response(ui, {
            "input": "hello", "response": response.text, "interaction": response, "cancel_requested": True,
        })
        self.assertEqual(calls[0][0], response.text)
        self.assertIs(calls[0][1]["interaction"], response)
        self.assertTrue(calls[0][1]["cancel_requested"])
        pyside_app.ProtoMindPySideApp._finish_worker_response(ui, {"input": "hello", "response": "Legacy text"})
        self.assertIsNone(calls[1][1]["interaction"])

    @unittest.skipUnless(pyside_app.PYSIDE_AVAILABLE, "PySide6 is optional")
    def test_cognitive_turn_card_ui_compact_and_debug_preserve_original_response(self) -> None:
        response = build_test_cognitive_card_response()
        compact = build_test_cognitive_card_ui()
        pyside_app.ProtoMindPySideApp._finish_response(compact, response.text, user_input="hello", interaction=response)
        cards = [text for kind, text in compact.calls if kind == "card"]
        self.assertEqual(len(cards), 1)
        self.assertIn("Observer: this line belongs to the answer", cards[0])
        self.assertEqual(compact.last_raw_response, response.text)
        self.assertNotIn(("system", CARD_UNAVAILABLE_NOTICE), compact.calls)

        debug = build_test_cognitive_card_ui(debug=True)
        pyside_app.ProtoMindPySideApp._finish_response(debug, response.text, user_input="hello", interaction=response)
        self.assertNotIn("card", [kind for kind, _ in debug.calls])
        self.assertIn(("assistant", response.text), debug.calls)
        self.assertEqual(debug.last_raw_response, response.text)

    @unittest.skipUnless(pyside_app.PYSIDE_AVAILABLE, "PySide6 is optional")
    def test_cognitive_turn_card_ui_failure_falls_back_without_execution(self) -> None:
        response = build_test_cognitive_card_response()
        with (
            patch("proto_mind.pyside_app.render_cognitive_turn_card_html", side_effect=RuntimeError("private render error")),
            patch.object(Coordinator, "handle", side_effect=AssertionError("No runtime call")),
        ):
            ui = build_test_cognitive_card_ui()
            pyside_app.ProtoMindPySideApp._finish_response(ui, response.text, user_input="hello", interaction=response)
        self.assertIn(("assistant", desktop_app.format_desktop_response(response.text)), ui.calls)
        self.assertIn(("system", CARD_UNAVAILABLE_NOTICE), ui.calls)
        self.assertNotIn("card", [kind for kind, _ in ui.calls])
        self.assertNotIn("private render error", str(ui.calls))

        stale = build_test_cognitive_card_ui()
        pyside_app.ProtoMindPySideApp._finish_response(stale, "Different turn", user_input="hello", interaction=response)
        self.assertIn(("report", "Different turn"), stale.calls)
        self.assertIn(("system", CARD_UNAVAILABLE_NOTICE), stale.calls)

    @unittest.skipUnless(pyside_app.PYSIDE_AVAILABLE, "PySide6 is optional")
    def test_cognitive_turn_card_ui_keeps_operator_cards_and_natural_reports(self) -> None:
        raw = "Daily Agent Doctor\nStatus: OK"
        ui = build_test_cognitive_card_ui()
        pyside_app.ProtoMindPySideApp._finish_response(
            ui, raw, user_input="/daily doctor", interaction=InteractiveResponse(raw),
        )
        self.assertIn(("card", build_local_capability_card_html("/daily doctor", raw)), ui.calls)
        self.assertNotIn(("system", CARD_UNAVAILABLE_NOTICE), ui.calls)
        raw = "Natural command matched:\n/loop next\nNo next task."
        natural = build_test_cognitive_card_ui()
        pyside_app.ProtoMindPySideApp._finish_response(
            natural, raw, user_input="что делать дальше", interaction=InteractiveResponse(raw),
        )
        self.assertIn(("system", raw), natural.calls)
        self.assertNotIn("card", [kind for kind, _ in natural.calls])
        self.assertNotIn(("system", CARD_UNAVAILABLE_NOTICE), natural.calls)

    @unittest.skipUnless(pyside_app.PYSIDE_AVAILABLE, "PySide6 is optional")
    def test_cognitive_turn_card_ui_keeps_refresh_exit_and_stop_paths(self) -> None:
        response = build_test_cognitive_card_response()
        refresh = build_test_cognitive_card_ui(mode="status_refresh")
        pyside_app.ProtoMindPySideApp._finish_response(refresh, "Log status", interaction=InteractiveResponse("Log status"))
        self.assertIn(("refresh", "Log status"), refresh.calls)
        self.assertNotIn("card", [kind for kind, _ in refresh.calls])
        stopped = build_test_cognitive_card_ui()
        pyside_app.ProtoMindPySideApp._finish_response(
            stopped, response.text, user_input="hello", interaction=response, cancel_requested=True,
        )
        self.assertEqual(sum(kind == "card" for kind, _ in stopped.calls), 1)
        self.assertIn(("system", "Operation finished after stop request."), stopped.calls)
        self.assertFalse(stopped.cancel_requested_for_current_worker)
        exiting = build_test_cognitive_card_ui()
        pyside_app.ProtoMindPySideApp._finish_response(exiting, None, user_input="/exit")
        self.assertTrue(exiting.closed)

    def test_cognitive_turn_envelope_has_detached_json_ready_fields(self) -> None:
        result = build_test_cognitive_turn_result()
        before = result.to_dict()

        envelope = build_cognitive_turn_envelope(result)
        payload = envelope.to_dict()

        self.assertEqual(payload["schema"], COGNITIVE_TURN_SCHEMA)
        self.assertEqual(payload["version"], COGNITIVE_TURN_VERSION)
        self.assertEqual(payload["response"], result.response)
        self.assertEqual(payload["reasoner_backend"], "scripted")
        self.assertEqual(payload["observer"], result.observer_state.to_dict())
        self.assertEqual(payload["retrieved_memories"][0]["record_id"], "turn-memory-1")
        self.assertEqual(payload["retrieved_memories"][0]["source"], "operator")
        self.assertEqual(payload["retrieval"]["query_mode"], "current_state")
        self.assertEqual(payload["grounding"], result.grounding_audit.to_dict())
        self.assertEqual(payload["reflection"], result.self_reflection.to_dict())
        self.assertEqual(payload["previous_correction_hints"], ["Earlier correction."])
        self.assertTrue(payload["projection_only"])
        self.assertEqual(payload["memory_scope"], "retrieved_for_reasoner_not_proof_of_use")
        self.assertEqual(json.loads(json.dumps(payload, allow_nan=False)), payload)
        self.assertEqual(result.to_dict(), before)

    def test_cognitive_turn_envelope_omits_full_stores_inputs_and_provenance(self) -> None:
        result = build_test_cognitive_turn_result()
        injection = {
            "enabled": True, "applied": True, "mode": "preview_safe",
            "context_chars": 2000, "truncated": True,
            "reasoner_input": "NOT_A_PROJECTED_INJECTED_PROMPT",
            "context_pack": {"private": "NOT_A_PROJECTED_CONTEXT_PACK"},
        }

        envelope = build_cognitive_turn_envelope(result, context_injection=injection)
        serialized = json.dumps(envelope.to_dict())

        self.assertNotIn("NOT_A_PROJECTED", serialized)
        self.assertNotIn("working_memory_snapshot", serialized)
        self.assertNotIn("persistent_memory_snapshot", serialized)
        self.assertNotIn("reasoner_input", serialized)
        self.assertTrue(envelope.context_injection.enabled)
        self.assertTrue(envelope.context_injection.applied)
        self.assertEqual(envelope.context_injection.context_chars, 2000)
        self.assertTrue(envelope.context_injection.truncated)

    def test_cognitive_turn_envelope_is_immutable_and_does_not_share_lists(self) -> None:
        result = build_test_cognitive_turn_result()
        envelope = build_cognitive_turn_envelope(result)
        expected = envelope.to_dict()

        result.observer_state.topic_tags.append("later-tag")
        result.retrieved_memory[0].content = "Later edited content."
        result.memory_summary.promoted_record_ids.append("later-memory")
        result.grounding_audit.warnings.append("later-grounding-warning")
        result.self_reflection.correction_hints.append("later-hint")
        result.previous_correction_hints.append("later-previous-hint")
        payload = envelope.to_dict()
        payload["observer"]["topic_tags"].append("client-tag")
        payload["retrieved_memories"][0]["source"] = "client-change"
        payload["grounding"]["evidence"].append("client-evidence")

        self.assertEqual(envelope.to_dict(), expected)
        with self.assertRaises(FrozenInstanceError):
            envelope.response = "Changed"
        with self.assertRaises(FrozenInstanceError):
            envelope.observer.needs_memory = False

    def test_cognitive_turn_envelope_preserves_missing_audits_as_unknown(self) -> None:
        result = replace(
            build_test_cognitive_turn_result(),
            retrieved_memory=[], retrieval_trace=None, self_reflection=None,
            grounding_audit=None, previous_correction_hints=[],
        )

        envelope = build_cognitive_turn_envelope(result)

        self.assertIsNone(envelope.grounding)
        self.assertIsNone(envelope.reflection)
        self.assertIsNone(envelope.retrieval)
        self.assertIsNone(envelope.context_injection)
        self.assertEqual(envelope.retrieved_memories, ())
        self.assertEqual(envelope.previous_correction_hints, ())

    def test_cognitive_turn_envelope_preserves_memory_decision_ids(self) -> None:
        result = build_test_cognitive_turn_result()
        result.memory_summary = replace(
            result.memory_summary, memory_type="decision", should_store=True,
            stored_record_id="new-decision", stored_record_type="decision",
            should_promote_new=True, promoted_record_ids=["promoted-decision"],
            override_detected=True, superseded_record_ids=["old-decision"],
        )

        decision = build_cognitive_turn_envelope(result).memory_decision

        self.assertTrue(decision.should_store)
        self.assertEqual(decision.stored_record_id, "new-decision")
        self.assertEqual(decision.stored_record_type, "decision")
        self.assertEqual(decision.promoted_record_ids, ("promoted-decision",))
        self.assertTrue(decision.override_detected)
        self.assertEqual(decision.superseded_record_ids, ("old-decision",))

    def test_cognitive_turn_envelope_bounds_memory_previews_not_answer(self) -> None:
        result = build_test_cognitive_turn_result()
        result.retrieved_memory[0].content = "word\n\t" * 300
        result.response = "answer " * 1000

        envelope = build_cognitive_turn_envelope(result)
        memory = envelope.retrieved_memories[0]

        self.assertLessEqual(len(memory.content_preview), MEMORY_PREVIEW_MAX_CHARS)
        self.assertTrue(memory.preview_truncated)
        self.assertTrue(memory.content_preview.endswith("..."))
        self.assertNotIn("\n", memory.content_preview)
        self.assertEqual(envelope.response, result.response)

    def test_cognitive_turn_envelope_rejects_malformed_fields_without_losing_text(self) -> None:
        fixture = build_test_cognitive_turn_result()
        malformed = (
            replace(fixture, observer_state=replace(fixture.observer_state, importance_hint=float("nan"))),
            replace(fixture, observer_state=replace(fixture.observer_state, topic_tags="not-a-list")),
            replace(fixture, memory_summary=replace(fixture.memory_summary, should_store="false")),
            replace(fixture, grounding_audit=replace(fixture.grounding_audit, warnings=[None])),
            replace(fixture, response=None),
            None,
        )
        for result in malformed:
            with self.subTest(result_type=type(result).__name__):
                response = project_interactive_response("Original rendered output", result)
                self.assertEqual(response.text, "Original rendered output")
                self.assertIsNone(response.cognitive_turn)
                self.assertEqual(response.envelope_warning, ENVELOPE_UNAVAILABLE_WARNING)

    def test_cognitive_turn_envelope_projection_is_pure_and_repeatable(self) -> None:
        result = build_test_cognitive_turn_result()
        before = result.to_dict()
        with (
            patch("pathlib.Path.open", side_effect=AssertionError("No file access")),
            patch("socket.create_connection", side_effect=AssertionError("No network")),
            patch.object(Coordinator, "handle", side_effect=AssertionError("No cognitive turn")),
        ):
            first = build_cognitive_turn_envelope(result)
            second = build_cognitive_turn_envelope(result)

        self.assertEqual(first, second)
        self.assertEqual(result.to_dict(), before)

    def test_cognitive_turn_envelope_preserves_exact_legacy_text_and_notices(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            coordinator, _, _ = build_test_system(root / "proto_mind")
            logger = SessionOperatorLogger.from_project_root(root)
            result = build_test_cognitive_turn_result()
            injection = {
                "enabled": True, "applied": True, "mode": "preview_safe",
                "context_chars": 2000, "truncated": False,
                "reasoner_input": "Injected fixture for the one normal call.",
            }
            observation = SimpleNamespace(
                capture_performed=True, captured_turn=1, captured_event_count=7,
                total_event_count=7, total_bytes=1000,
            )
            expected = _format_interaction_result(
                result, context_injection=injection, experience_pilot=observation,
            )
            with (
                patch.object(coordinator, "handle", return_value=result) as handle,
                patch("proto_mind.main.prepare_context_injection", return_value=injection) as prepare,
                patch("proto_mind.main.observe_experience_pilot_if_active", return_value=observation) as observe,
            ):
                response = process_interactive_input_with_envelope(
                    "Normal request", coordinator=coordinator, session_logger=logger, project_root=root,
                )

            self.assertEqual(response.text.encode("utf-8"), expected.encode("utf-8"))
            self.assertEqual(response.cognitive_turn.response, result.response)
            self.assertIn("Context injection: enabled", response.text)
            self.assertIn("Experience pilot: captured turn", response.text)
            handle.assert_called_once_with("Normal request", reasoner_input=injection["reasoner_input"])
            prepare.assert_called_once()
            observe.assert_called_once()

    def test_cognitive_turn_envelope_legacy_api_never_builds_projection(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            coordinator, _, _ = build_test_system(root / "proto_mind")
            logger = SessionOperatorLogger.from_project_root(root)
            with patch("proto_mind.main.project_interactive_response") as project:
                response = process_interactive_input(
                    "hello", coordinator=coordinator, session_logger=logger, project_root=root,
                )

            self.assertIsInstance(response, str)
            self.assertIn("Proto-Mind:", response)
            project.assert_not_called()

    def test_cognitive_turn_envelope_updates_memory_and_log_only_once(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            coordinator, store, keeper = build_test_system(root / "proto_mind")
            logger = SessionOperatorLogger.from_project_root(root)
            coordinator.session_logger = logger
            with (
                patch.object(coordinator.reasoner, "respond", wraps=coordinator.reasoner.respond) as respond,
                patch.object(keeper, "evaluate_interaction", wraps=keeper.evaluate_interaction) as evaluate,
                patch.object(keeper, "apply_memory_updates", wraps=keeper.apply_memory_updates) as update,
                patch.object(store, "save_working_memory", wraps=store.save_working_memory) as working_write,
                patch.object(store, "save_persistent_memory", wraps=store.save_persistent_memory) as persistent_write,
                patch.object(logger, "append_turn", wraps=logger.append_turn) as log,
            ):
                response = process_interactive_input_with_envelope(
                    "I prefer concise answers.", coordinator=coordinator, session_logger=logger, project_root=root,
                )
                response.to_dict()
                response.to_dict()

            for call in (respond, evaluate, update, working_write, persistent_write, log):
                call.assert_called_once()
            self.assertEqual(len(store.load_working_memory()), 1)
            self.assertEqual(len(store.load_persistent_memory()), 1)
            self.assertEqual(
                response.cognitive_turn.memory_decision.stored_record_id,
                store.load_working_memory()[0].id,
            )
            self.assertEqual(logger.status().entry_count, 1)
            self.assertEqual(logger.tail(1)[0]["user_input"], "I prefer concise answers.")
            self.assertNotIn("cognitive_turn", logger.tail(1)[0])
            self.assertFalse((root / "proto_mind" / "data" / "context_injection.json").exists())

    def test_cognitive_turn_envelope_normal_apis_have_identical_files_and_output(self) -> None:
        with TemporaryDirectory() as temp_dir:
            outcomes = []
            for api in (process_interactive_input, process_interactive_input_with_envelope):
                root = Path(temp_dir) / api.__name__
                coordinator, store, _ = build_test_system(root / "proto_mind")
                logger = SessionOperatorLogger.from_project_root(root)
                coordinator.session_logger = logger
                fixed_now = datetime(2026, 8, 30, 12, 0, tzinfo=UTC)
                with (
                    patch("proto_mind.models.datetime") as model_clock,
                    patch("proto_mind.session_log.datetime") as log_clock,
                    patch("proto_mind.models.uuid4", return_value="fixed-turn-memory-id"),
                ):
                    model_clock.now.return_value = fixed_now
                    log_clock.now.return_value = fixed_now
                    response = api(
                        "I prefer concise answers.", coordinator=coordinator, session_logger=logger, project_root=root,
                    )
                text = response.text if isinstance(response, InteractiveResponse) else response
                outcomes.append((text.encode("utf-8"), store.working_path.read_bytes(),
                                 store.persistent_path.read_bytes(), logger.log_path.read_bytes()))

            self.assertEqual(outcomes[0], outcomes[1])

    def test_cognitive_turn_envelope_preserves_multiturn_russian_continuity(self) -> None:
        prompts = (
            "Я предпочитаю короткие ответы.",
            "Мы решили использовать JSON для памяти Proto-Mind.",
            "Что я предпочитаю в стиле ответа?",
            "На самом деле теперь используем SQLite вместо JSON для памяти Proto-Mind.",
            "Что мы использовали раньше, до SQLite?",
            "Проверь текущее решение о хранилище памяти.",
            "Повтори текущее решение о хранилище памяти.",
            "Как мы продолжим работу после исправления?",
        )
        answers = (
            "Учту: короткие ответы.",
            "Текущее архитектурное решение — JSON для хранения памяти.",
            "Вы предпочитаете короткие ответы.",
            "Текущее архитектурное решение — SQLite для хранения памяти.",
            "Раньше использовали JSON.",
            "Текущее архитектурное решение — JSON для хранения памяти.",
            "Текущее архитектурное решение — SQLite для хранения памяти.",
            "Продолжим с текущим решением SQLite.",
        )
        with TemporaryDirectory() as temp_dir:
            outcomes = []
            envelopes = []
            for api in (process_interactive_input, process_interactive_input_with_envelope):
                root = Path(temp_dir) / api.__name__
                coordinator, store, keeper = build_test_system(root / "proto_mind")
                coordinator.reasoner = ScriptedReasoner(list(answers))
                logger = SessionOperatorLogger.from_project_root(root)
                coordinator.session_logger = logger
                fixed_now = datetime(2026, 8, 30, 12, 0, tzinfo=UTC)
                with (
                    patch("proto_mind.models.datetime") as model_clock,
                    patch("proto_mind.session_log.datetime") as log_clock,
                    patch("proto_mind.models.uuid4", side_effect=[f"continuity-{index:02d}" for index in range(30)]),
                    patch("proto_mind.memory_keeper.datetime", wraps=datetime) as keeper_clock,
                    patch.object(coordinator.reasoner, "respond", wraps=coordinator.reasoner.respond) as respond,
                    patch.object(keeper, "apply_memory_updates", wraps=keeper.apply_memory_updates) as update,
                    patch.object(logger, "append_turn", wraps=logger.append_turn) as log,
                ):
                    model_clock.now.return_value = fixed_now
                    log_clock.now.return_value = fixed_now
                    keeper_clock.now.return_value = fixed_now
                    responses = [api(prompt, coordinator=coordinator, session_logger=logger, project_root=root)
                                 for prompt in prompts]
                for call in (respond, update, log):
                    self.assertEqual(call.call_count, len(prompts))
                texts = []
                for response in responses:
                    if isinstance(response, InteractiveResponse):
                        self.assertIsNone(response.envelope_warning)
                        envelopes.append(response.cognitive_turn)
                        texts.append(response.text)
                    else:
                        texts.append(response)
                outcomes.append((texts, store.working_path.read_bytes(), store.persistent_path.read_bytes(),
                                 logger.log_path.read_bytes()))

            self.assertEqual(outcomes[0], outcomes[1])
            self.assertEqual(len(envelopes), len(prompts))
            self.assertTrue(envelopes[3].memory_decision.override_detected)
            self.assertTrue(envelopes[3].memory_decision.superseded_record_ids)
            self.assertTrue(any(not memory.active for memory in envelopes[4].retrieved_memories))
            self.assertEqual(envelopes[5].grounding.grounding_status, "contradicted")
            self.assertTrue(envelopes[6].previous_correction_hints)
            self.assertFalse(envelopes[7].previous_correction_hints)

    def test_cognitive_turn_envelope_recall_does_not_write_memory_or_usage(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            coordinator, store, keeper = build_test_system(root / "proto_mind")
            logger = SessionOperatorLogger.from_project_root(root)
            store.save_persistent_memory([
                MemoryRecord("I prefer concise answers.", "preference", 0.95, "operator", tags=["preferences"]),
            ])
            before = (store.working_path.read_bytes(), store.persistent_path.read_bytes())
            with patch.object(keeper, "record_retrieval_usage") as usage:
                response = process_interactive_input_with_envelope(
                    "What do you remember about my preferences?",
                    coordinator=coordinator, session_logger=logger, project_root=root,
                )

            self.assertTrue(response.cognitive_turn.retrieved_memories)
            self.assertFalse(response.cognitive_turn.memory_decision.should_store)
            self.assertEqual((store.working_path.read_bytes(), store.persistent_path.read_bytes()), before)
            usage.assert_not_called()

    def test_cognitive_turn_envelope_commands_natural_routes_and_exit_bypass_projection(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            coordinator, _, _ = build_test_system(root / "proto_mind")
            logger = SessionOperatorLogger.from_project_root(root)
            before = {str(path.relative_to(root)): path.read_bytes() for path in root.rglob("*") if path.is_file()}
            with (
                patch.object(coordinator, "handle", side_effect=AssertionError("No cognitive call")) as handle,
                patch("proto_mind.main.project_interactive_response") as project,
                patch("proto_mind.main.prepare_context_injection") as prepare,
            ):
                for command in ("/session log status", "/context injection audit-status", "что делать дальше", "/exit"):
                    with self.subTest(command=command):
                        response = process_interactive_input_with_envelope(
                            command, coordinator=coordinator, session_logger=logger, project_root=root,
                        )
                        self.assertIsNone(response.cognitive_turn)
                        self.assertIsNone(response.envelope_warning)
                        self.assertEqual(response.text is None, command == "/exit")
                handle.assert_not_called()
                project.assert_not_called()
                prepare.assert_not_called()
            after = {str(path.relative_to(root)): path.read_bytes() for path in root.rglob("*") if path.is_file()}
            self.assertEqual(before, after)
            self.assertEqual(logger.status().entry_count, 0)

    def test_cognitive_turn_envelope_leaves_empty_and_unknown_slash_behavior_unchanged(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            coordinator, _, _ = build_test_system(root / "proto_mind")
            logger = SessionOperatorLogger.from_project_root(root)
            result = build_test_cognitive_turn_result()
            for user_input in ("  ", "/unknown-command"):
                with (
                    self.subTest(user_input=user_input),
                    patch.object(coordinator, "handle", return_value=result) as handle,
                    patch("proto_mind.main.prepare_context_injection", return_value={
                        "enabled": False, "applied": False, "reasoner_input": user_input.strip(),
                    }),
                    patch("proto_mind.main.observe_experience_pilot_if_active", return_value=None),
                    patch("proto_mind.main.project_interactive_response") as project,
                ):
                    text = process_interactive_input(
                        user_input, coordinator=coordinator, session_logger=logger, project_root=root,
                    )
                    response = process_interactive_input_with_envelope(
                        user_input, coordinator=coordinator, session_logger=logger, project_root=root,
                    )
                    self.assertEqual(response.text, text)
                    self.assertIsNone(response.cognitive_turn)
                    self.assertEqual(handle.call_count, 2)
                    project.assert_not_called()

    def test_cognitive_turn_envelope_projection_failure_never_retries_completed_turn(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            coordinator, store, keeper = build_test_system(root / "proto_mind")
            logger = SessionOperatorLogger.from_project_root(root)
            coordinator.session_logger = logger
            with (
                patch("proto_mind.cognitive_turn_envelope.build_cognitive_turn_envelope", side_effect=RuntimeError("private failure detail")),
                patch.object(coordinator.reasoner, "respond", wraps=coordinator.reasoner.respond) as respond,
                patch.object(keeper, "apply_memory_updates", wraps=keeper.apply_memory_updates) as update,
                patch.object(logger, "append_turn", wraps=logger.append_turn) as log,
            ):
                response = process_interactive_input_with_envelope(
                    "I prefer concise answers.", coordinator=coordinator, session_logger=logger, project_root=root,
                )
            self.assertIsNone(response.cognitive_turn)
            self.assertEqual(response.envelope_warning, ENVELOPE_UNAVAILABLE_WARNING)
            self.assertIn("Proto-Mind:", response.text)
            self.assertNotIn("private failure detail", response.text + response.envelope_warning)
            for call in (respond, update, log):
                call.assert_called_once()
            self.assertEqual(len(store.load_persistent_memory()), 1)

    def test_cognitive_turn_envelope_reasoner_failure_is_not_retried_or_projected(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            coordinator, _, keeper = build_test_system(root / "proto_mind")
            logger = SessionOperatorLogger.from_project_root(root)
            coordinator.session_logger = logger
            with (
                patch.object(coordinator.reasoner, "respond", side_effect=RuntimeError("reasoner failure")) as respond,
                patch.object(keeper, "apply_memory_updates") as update,
                patch("proto_mind.main.project_interactive_response") as project,
            ):
                with self.assertRaisesRegex(RuntimeError, "reasoner failure"):
                    process_interactive_input_with_envelope(
                        "hello", coordinator=coordinator, session_logger=logger, project_root=root,
                    )
            respond.assert_called_once()
            update.assert_not_called()
            project.assert_not_called()
            self.assertEqual(logger.status().entry_count, 0)

    def test_cognitive_turn_envelope_does_not_retain_previous_turn_on_command(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            coordinator, store, _ = build_test_system(root / "proto_mind")
            logger = SessionOperatorLogger.from_project_root(root)
            runtime = desktop_app.DesktopRuntime(root, logger, coordinator, MemoryHygiene(store))
            first = runtime.process_with_envelope("hello")
            second = runtime.process_with_envelope("/session log status")

            self.assertIsNotNone(first.cognitive_turn)
            self.assertIsNone(second.cognitive_turn)
            self.assertIn("Session operator log:", second.text)
            self.assertIsNone(runtime.process_with_envelope("/exit").text)

    def test_cognitive_turn_envelope_keeps_context_configuration_and_single_audit(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            coordinator, _, _ = build_test_system(root / "proto_mind")
            coordinator.reasoner = ScriptedReasoner(["One local answer."])
            logger = SessionOperatorLogger.from_project_root(root)
            coordinator.session_logger = logger
            format_context_command("/context injection enable --max-chars 2000", project_root=root)
            settings_path = root / "proto_mind" / "data" / "context_injection.json"
            settings_before = settings_path.read_bytes()
            with patch.object(coordinator.reasoner, "respond", wraps=coordinator.reasoner.respond) as respond:
                response = process_interactive_input_with_envelope(
                    "hello", coordinator=coordinator, session_logger=logger, project_root=root,
                )

            self.assertEqual(settings_path.read_bytes(), settings_before)
            self.assertTrue(response.cognitive_turn.context_injection.enabled)
            self.assertTrue(response.cognitive_turn.context_injection.applied)
            self.assertIn("[PROTO-MIND CONTEXT", respond.call_args.kwargs["user_input"])
            self.assertNotIn("[PROTO-MIND CONTEXT", json.dumps(response.cognitive_turn.to_dict()))
            self.assertEqual(logger.tail(1)[0]["user_input"], "hello")
            events, _ = ContextInjectionAuditLog.from_project_root(root).read_events()
            self.assertEqual(sum(event["event"] == "injected" for event in events), 1)
            respond.assert_called_once()

    def test_cognitive_turn_envelope_keeps_one_consented_experience_capture(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            coordinator, _, _ = build_test_system(root / "proto_mind")
            logger = SessionOperatorLogger.from_project_root(root)
            pilot = get_experience_pilot(coordinator, project_root=root)
            pilot.preview()
            pilot.consent(pilot.expected_consent_phrase)
            with patch.object(pilot, "observe_normal_turn", wraps=pilot.observe_normal_turn) as observe:
                response = process_interactive_input_with_envelope(
                    "Explain a bounded pilot turn.",
                    coordinator=coordinator, session_logger=logger, project_root=root,
                )

            self.assertIsNotNone(response.cognitive_turn)
            self.assertIn("Experience pilot: captured turn 1", response.text)
            self.assertEqual(pilot.captured_turns, 1)
            observe.assert_called_once()

    def test_cognitive_continuity_soak_passes_25_turn_contract(self) -> None:
        report = run_continuity_soak()

        self.assertEqual(report["status"], "OK")
        self.assertEqual(report["turn_count"], 25)
        self.assertEqual(report["expected_store_turns"], 4)
        self.assertEqual(report["byte_stable_read_only_turns"], 21)
        self.assertEqual(report["read_only_turns"], 21)
        self.assertEqual(report["working_records"], 4)
        self.assertEqual(report["persistent_records"], 3)
        self.assertEqual(report["unique_memory_contents"], 4)
        self.assertEqual(report["experience_events"], 180)
        self.assertEqual(report["experience_doctor_status"], "OK")
        self.assertTrue(all(report["checks"].values()))

    def test_cognitive_continuity_soak_report_states_local_no_write_boundary(self) -> None:
        report = run_continuity_soak()
        output = format_continuity_soak_report(report)

        self.assertIn("Status: OK", output)
        self.assertIn("byte_stable_read_only=21/21", output)
        self.assertIn("Temporary local store only", output)
        self.assertIn("no LLM/API", output)
        self.assertIn("live store", output)

    def test_cognitive_turn_projector_connects_complete_observe_to_verify_episode(self) -> None:
        with TemporaryDirectory() as temp_dir:
            events = build_test_experience_events(Path(temp_dir))
            episodes = CognitiveTurnProjector(events).project()

        self.assertEqual(len(episodes), 1)
        episode = episodes[0]
        self.assertEqual(episode.status, "COMPLETE")
        self.assertEqual(episode.turn_id, "1")
        self.assertEqual(episode.interpret["query_type"], "project_context")
        self.assertEqual(episode.recall["selected_count"], 0)
        self.assertFalse(episode.memory_decision["should_store"])
        self.assertTrue(episode.reflect["available"])
        self.assertTrue(episode.verify["available"])
        self.assertEqual(len(episode.event_ids), 7)
        self.assertFalse(episode.missing_event_types)

    def test_cognitive_turn_episode_formats_compact_path_and_provenance(self) -> None:
        with TemporaryDirectory() as temp_dir:
            events = build_test_experience_events(Path(temp_dir))
            listing = format_cognitive_turn_list(events)
            detail = format_cognitive_turn_episode(events)

        self.assertIn("turn=1 | status=COMPLETE", listing)
        self.assertIn("recall=0 selected", listing)
        for heading in (
            "Observe:",
            "Interpret:",
            "Recall:",
            "Respond:",
            "Memory decision:",
            "Reflect:",
            "Verify:",
            "Provenance:",
        ):
            self.assertIn(heading, detail)
        self.assertIn("No event, memory, skill, task, file", detail)

    def test_cognitive_turn_episode_handles_empty_unknown_and_incomplete_turns(self) -> None:
        empty = format_cognitive_turn_episode([])
        with TemporaryDirectory() as temp_dir:
            events = build_test_experience_events(Path(temp_dir))
            unknown = format_cognitive_turn_episode(events, "99")
            incomplete = CognitiveTurnProjector(events[:-1]).project()[0]

        self.assertIn("Status: EMPTY", empty)
        self.assertIn("Status: NOT FOUND", unknown)
        self.assertEqual(incomplete.status, "INCOMPLETE")
        self.assertEqual(incomplete.missing_event_types, ["grounding_evaluated"])

    def test_cognitive_turn_episode_fails_cleanly_on_invalid_trace(self) -> None:
        with TemporaryDirectory() as temp_dir:
            events = [event.to_dict() for event in build_test_experience_events(Path(temp_dir))]
            events[1]["source_event_ids"] = ["missing-event"]
            output = format_cognitive_turn_episode(events)

        self.assertIn("Status: ERROR", output)
        self.assertIn("missing or later source event", output)

    def test_cognitive_turn_episode_preserves_privacy_redaction(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            coordinator, _, _ = build_test_system(root / "cognitive")
            pilot = SupervisedExperiencePilot(root, session_id="pilot-episode-redaction")
            pilot.preview()
            pilot.consent(pilot.expected_consent_phrase)
            secret = "episode-secret-value"
            user_input = f"Explain credential safety. token={secret}"
            pilot.observe_normal_turn(user_input, coordinator.handle(user_input))
            output = format_cognitive_turn_episode(pilot.snapshot())

        self.assertNotIn(secret, output)
        self.assertIn(REDACTION_PREFIX, output)
        self.assertIn("Status: COMPLETE", output)

    def test_cognitive_turn_commands_are_registered_read_only_and_auto_allowed(self) -> None:
        registry = {spec.prefix: spec for spec in COMMAND_REGISTRY}
        for command in ("/experience episodes", "/experience episode"):
            self.assertIn(command, registry)
            self.assertTrue(registry[command].read_only)
            self.assertEqual(registry[command].mutates, "none")
            self.assertEqual(classify_command(command).policy_class, "auto_allowed")

        self.assertEqual(len(COMMAND_REGISTRY), 387)
        self.assertEqual(len({spec.category for spec in COMMAND_REGISTRY}), 41)
        self.assertEqual(command_registry_doctor()["status"], "OK")
