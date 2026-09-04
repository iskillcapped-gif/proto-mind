"""Core flow checks: session."""
from __future__ import annotations

import unittest
from proto_mind.tests.flow_fixtures import (
    COMMAND_REGISTRY,
    CONSENT_PHRASE_PREFIX,
    Coordinator,
    DEFAULT_CAPTURE_SETTINGS,
    MemoryKeeper,
    MemoryRecord,
    MemoryStore,
    MockReasoner,
    Observer,
    PERSISTENT_EXPERIENCE_COMMAND_PREFIXES,
    Path,
    SESSION_CAPTURE_CONSENT_MODEL,
    SESSION_CAPTURE_DESIGN_STATUS,
    SESSION_CAPTURE_FAILURE_MODE,
    ScriptedReasoner,
    SessionCaptureDesignReview,
    SessionConsentStateMachineSpec,
    SessionOperatorLogger,
    TemporaryDirectory,
    _create_healthy_export_dirs,
    build_test_system,
    format_context_command,
    format_session_capture_design_benchmark,
    format_session_capture_design_checklist,
    format_session_capture_design_doctor,
    format_session_capture_design_review,
    format_session_capture_design_status,
    format_session_consent_benchmark,
    format_session_consent_doctor,
    format_session_consent_refusals,
    format_session_consent_status,
    format_session_consent_transitions,
    format_session_log_command,
    format_session_ritual_command,
    json,
    patch,
    process_interactive_input,
    run_session_capture_design_benchmark,
    run_session_consent_benchmark,
)


class SessionFlowTests(unittest.TestCase):
    def test_session_log_appends_compact_turn_record(self) -> None:
        with TemporaryDirectory() as temp_dir:
            tmp_path = Path(temp_dir)
            logger = SessionOperatorLogger(tmp_path / "logs" / "session_operator_log.jsonl")
            data_dir = tmp_path / "data"
            store = MemoryStore(
                working_path=data_dir / "working_memory.json",
                persistent_path=data_dir / "persistent_memory.json",
            )
            store.save_persistent_memory(
                [
                    MemoryRecord(
                        "Actually, we are changing direction: Proto-Mind should use SQLite instead of JSON.",
                        "decision",
                        0.95,
                        "test",
                        tags=["sqlite", "storage"],
                    )
                ]
            )
            coordinator = Coordinator(
                observer=Observer(),
                memory_keeper=MemoryKeeper(store),
                reasoner=MockReasoner(),
                session_logger=logger,
            )

            coordinator.handle("What storage system are we using now?")

            entries = logger.tail(5)
            self.assertEqual(len(entries), 1)
            entry = entries[0]
            self.assertEqual(entry["observer"]["query_type"], "memory_inventory")
            self.assertTrue(entry["retrieved_memory_ids"])
            self.assertIn("self_reflection", entry)
            self.assertIn("grounding_audit", entry)
            self.assertIn("grounding_status", entry["grounding_audit"])
            self.assertNotIn("working_memory_snapshot", entry)
            self.assertNotIn("persistent_memory_snapshot", entry)

    def test_session_log_response_preview_is_truncated(self) -> None:
        with TemporaryDirectory() as temp_dir:
            tmp_path = Path(temp_dir)
            logger = SessionOperatorLogger(tmp_path / "logs" / "session_operator_log.jsonl")
            store = MemoryStore(
                working_path=tmp_path / "data" / "working_memory.json",
                persistent_path=tmp_path / "data" / "persistent_memory.json",
            )
            coordinator = Coordinator(
                observer=Observer(),
                memory_keeper=MemoryKeeper(store),
                reasoner=ScriptedReasoner(["x " * 300]),
                session_logger=logger,
            )

            coordinator.handle("Hello there.")
            entry = logger.tail(1)[0]

            self.assertLessEqual(len(entry["response_preview"]), 240)
            self.assertTrue(entry["response_preview"].endswith("..."))

    def test_session_log_commands_status_and_tail_are_readable(self) -> None:
        with TemporaryDirectory() as temp_dir:
            tmp_path = Path(temp_dir)
            logger = SessionOperatorLogger(tmp_path / "logs" / "session_operator_log.jsonl")
            store = MemoryStore(
                working_path=tmp_path / "data" / "working_memory.json",
                persistent_path=tmp_path / "data" / "persistent_memory.json",
            )
            coordinator = Coordinator(
                observer=Observer(),
                memory_keeper=MemoryKeeper(store),
                reasoner=MockReasoner(),
                session_logger=logger,
            )
            coordinator.handle("Hello there.")

            status = format_session_log_command("/session log status", logger)
            tail = format_session_log_command("/session log tail", logger)
            tail_10 = format_session_log_command("/session log tail 10", logger)

            self.assertIsNotNone(status)
            self.assertIn("enabled: True", status)
            self.assertIn(str(logger.log_path), status)
            self.assertIsNotNone(tail)
            self.assertIn("Session operator log tail", tail)
            self.assertIn("query=", tail)
            self.assertIsNotNone(tail_10)

    def test_session_log_inspect_command_is_detailed_and_readable(self) -> None:
        with TemporaryDirectory() as temp_dir:
            tmp_path = Path(temp_dir)
            logger = SessionOperatorLogger(tmp_path / "logs" / "session_operator_log.jsonl")
            store = MemoryStore(
                working_path=tmp_path / "data" / "working_memory.json",
                persistent_path=tmp_path / "data" / "persistent_memory.json",
            )
            coordinator = Coordinator(
                observer=Observer(),
                memory_keeper=MemoryKeeper(store),
                reasoner=MockReasoner(),
                session_logger=logger,
            )
            coordinator.handle("What storage system are we using now?")

            output = format_session_log_command("/session log inspect", logger)

            self.assertIsNotNone(output)
            self.assertIn("Session log inspect", output)
            self.assertIn("Input: What storage system are we using now?", output)
            self.assertIn("Response preview:", output)
            self.assertIn("query_type:", output)
            self.assertIn("Self-reflection:", output)
            self.assertIn("Grounding audit:", output)

    def test_session_log_inspect_handles_empty_log_gracefully(self) -> None:
        with TemporaryDirectory() as temp_dir:
            logger = SessionOperatorLogger(Path(temp_dir) / "logs" / "session_operator_log.jsonl")

            output = format_session_log_command("/session log inspect", logger)

            self.assertIsNotNone(output)
            self.assertIn("No entries found", output)

    def test_session_log_inspect_does_not_append_entry(self) -> None:
        with TemporaryDirectory() as temp_dir:
            tmp_path = Path(temp_dir)
            logger = SessionOperatorLogger(tmp_path / "logs" / "session_operator_log.jsonl")
            store = MemoryStore(
                working_path=tmp_path / "data" / "working_memory.json",
                persistent_path=tmp_path / "data" / "persistent_memory.json",
            )
            coordinator = Coordinator(
                observer=Observer(),
                memory_keeper=MemoryKeeper(store),
                reasoner=MockReasoner(),
                session_logger=logger,
            )
            coordinator.handle("Hello there.")
            before_count = logger.status().entry_count

            output = format_session_log_command("/session log inspect", logger)
            after_count = logger.status().entry_count

            self.assertIsNotNone(output)
            self.assertEqual(before_count, after_count)

    def test_session_log_inspect_handles_minimal_older_entry(self) -> None:
        with TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "logs" / "session_operator_log.jsonl"
            log_path.parent.mkdir(parents=True)
            log_path.write_text(
                json.dumps({"turn_id": 7, "user_input": "Older entry", "response_preview": "Minimal response"}) + "\n",
                encoding="utf-8",
            )
            logger = SessionOperatorLogger(log_path)

            output = format_session_log_command("/session log inspect", logger)

            self.assertIsNotNone(output)
            self.assertIn("Turn: 7", output)
            self.assertIn("Input: Older entry", output)
            self.assertIn("query_type: unknown", output)
            self.assertIn("status: unknown", output)

    def test_session_log_warnings_command_shows_reflection_warnings_and_hints(self) -> None:
        with TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "logs" / "session_operator_log.jsonl"
            log_path.parent.mkdir(parents=True)
            entries = [
                {
                    "turn_id": 1,
                    "timestamp": "2026-05-23T00:00:00+00:00",
                    "user_input": "Clean turn",
                    "self_reflection": {"warnings": [], "correction_hints": []},
                    "grounding_audit": {"grounding_status": "grounded", "warnings": []},
                },
                {
                    "turn_id": 2,
                    "timestamp": "2026-05-23T00:01:00+00:00",
                    "user_input": "Do you remember my response style preference?",
                    "self_reflection": {
                        "warnings": ["Response may be too long for active short-answer preference."],
                        "correction_hints": ["Respect active preference next turn: I prefer short answers."],
                    },
                    "grounding_audit": {"grounding_status": "grounded", "warnings": []},
                },
            ]
            log_path.write_text("\n".join(json.dumps(entry) for entry in entries) + "\n", encoding="utf-8")
            logger = SessionOperatorLogger(log_path)

            output = format_session_log_command("/session log warnings", logger)

            self.assertIsNotNone(output)
            self.assertIn("Session log warnings", output)
            self.assertIn("Found 1 warning entry", output)
            self.assertIn("Turn: 2", output)
            self.assertIn("Response may be too long", output)
            self.assertIn("Respect active preference", output)
            self.assertNotIn("Turn: 1", output)

    def test_session_log_warnings_command_shows_grounding_signals(self) -> None:
        with TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "logs" / "session_operator_log.jsonl"
            log_path.parent.mkdir(parents=True)
            entries = [
                {
                    "turn_id": 3,
                    "timestamp": "2026-05-23T00:02:00+00:00",
                    "user_input": "Is JSON still current?",
                    "self_reflection": {"warnings": [], "correction_hints": []},
                    "grounding_audit": {
                        "grounding_status": "contradicted",
                        "active_decision_status": "contradicted",
                        "superseded_memory_status": "treated_as_current",
                        "warnings": ["Response may treat superseded JSON as current."],
                    },
                }
            ]
            log_path.write_text("\n".join(json.dumps(entry) for entry in entries) + "\n", encoding="utf-8")
            logger = SessionOperatorLogger(log_path)

            output = format_session_log_command("/session log warnings", logger)

            self.assertIsNotNone(output)
            self.assertIn("Turn: 3", output)
            self.assertIn("Response may treat superseded JSON as current.", output)
            self.assertIn("grounding_status=contradicted", output)
            self.assertIn("active_decision_status=contradicted", output)
            self.assertIn("superseded_memory_status=treated_as_current", output)

    def test_session_log_warnings_handles_empty_and_minimal_logs(self) -> None:
        with TemporaryDirectory() as temp_dir:
            empty_logger = SessionOperatorLogger(Path(temp_dir) / "logs" / "missing.jsonl")
            empty_output = format_session_log_command("/session log warnings", empty_logger)
            self.assertIsNotNone(empty_output)
            self.assertIn("No warning entries found", empty_output)

            log_path = Path(temp_dir) / "logs" / "session_operator_log.jsonl"
            log_path.parent.mkdir(parents=True, exist_ok=True)
            log_path.write_text(json.dumps({"turn_id": 4, "user_input": "Older clean entry"}) + "\n", encoding="utf-8")
            minimal_logger = SessionOperatorLogger(log_path)
            minimal_output = format_session_log_command("/session log warnings", minimal_logger)
            self.assertIsNotNone(minimal_output)
            self.assertIn("No warning entries found", minimal_output)

    def test_session_log_warnings_does_not_append_entry(self) -> None:
        with TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "logs" / "session_operator_log.jsonl"
            log_path.parent.mkdir(parents=True)
            log_path.write_text(
                json.dumps(
                    {
                        "turn_id": 5,
                        "user_input": "Warning entry",
                        "self_reflection": {"warnings": ["warning"], "correction_hints": []},
                        "grounding_audit": {"grounding_status": "grounded", "warnings": []},
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            logger = SessionOperatorLogger(log_path)
            before_count = logger.status().entry_count

            output = format_session_log_command("/session log warnings", logger)
            after_count = logger.status().entry_count

            self.assertIsNotNone(output)
            self.assertEqual(before_count, after_count)

    def test_session_log_warnings_limit_is_respected(self) -> None:
        with TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "logs" / "session_operator_log.jsonl"
            log_path.parent.mkdir(parents=True)
            entries = [
                {
                    "turn_id": index,
                    "timestamp": f"2026-05-23T00:0{index}:00+00:00",
                    "user_input": f"Warning {index}",
                    "self_reflection": {"warnings": [f"warning {index}"], "correction_hints": []},
                    "grounding_audit": {"grounding_status": "grounded", "warnings": []},
                }
                for index in range(1, 5)
            ]
            log_path.write_text("\n".join(json.dumps(entry) for entry in entries) + "\n", encoding="utf-8")
            logger = SessionOperatorLogger(log_path)

            output = format_session_log_command("/session log warnings 2", logger)

            self.assertIsNotNone(output)
            self.assertIn("Found 2 warning entries", output)
            self.assertIn("Turn: 3", output)
            self.assertIn("Turn: 4", output)
            self.assertNotIn("Turn: 1", output)
            self.assertNotIn("Turn: 2", output)

    def test_session_log_search_matches_case_insensitively(self) -> None:
        with TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "logs" / "session_operator_log.jsonl"
            log_path.parent.mkdir(parents=True)
            log_path.write_text(
                json.dumps(
                    {
                        "turn_id": 1,
                        "timestamp": "2026-06-04T00:00:00+00:00",
                        "user_input": "What storage system uses SQLite?",
                        "response_preview": "SQLite is the current direction.",
                        "observer": {"query_type": "memory_inventory", "tags": ["storage"]},
                        "self_reflection": {"warnings": [], "correction_hints": []},
                        "grounding_audit": {"grounding_status": "grounded", "warnings": []},
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            logger = SessionOperatorLogger(log_path)

            output = format_session_log_command("/session log search sqlite", logger)

            self.assertIsNotNone(output)
            self.assertIn('Session log search: "sqlite"', output)
            self.assertIn("Found 1 match(es)", output)
            self.assertIn("turn_id=1", output)
            self.assertIn("SQLite", output)

    def test_session_log_search_matches_response_warning_and_grounding_fields(self) -> None:
        with TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "logs" / "session_operator_log.jsonl"
            log_path.parent.mkdir(parents=True)
            entries = [
                {
                    "turn_id": 2,
                    "timestamp": "2026-06-04T00:01:00+00:00",
                    "user_input": "Clean",
                    "response_preview": "Qwen fallback was not needed.",
                    "observer": {"query_type": "new_question", "tags": ["general"]},
                    "self_reflection": {"warnings": [], "correction_hints": []},
                    "grounding_audit": {
                        "grounding_status": "grounded",
                        "memory_support": "none_needed",
                        "active_decision_status": "not_applicable",
                        "superseded_memory_status": "not_applicable",
                        "warnings": [],
                    },
                },
                {
                    "turn_id": 3,
                    "timestamp": "2026-06-04T00:02:00+00:00",
                    "user_input": "Is JSON current?",
                    "response_preview": "JSON may be historical.",
                    "observer": {"query_type": "memory_inventory", "tags": ["storage", "json"]},
                    "self_reflection": {
                        "warnings": ["Response warning mentions superseded JSON."],
                        "correction_hints": ["Use SQLite as current direction."],
                    },
                    "grounding_audit": {
                        "grounding_status": "contradicted",
                        "memory_support": "selected_memory_used",
                        "active_decision_status": "contradicted",
                        "superseded_memory_status": "treated_as_current",
                        "warnings": ["Grounding warning mentions active decision."],
                    },
                },
            ]
            log_path.write_text("\n".join(json.dumps(entry) for entry in entries) + "\n", encoding="utf-8")
            logger = SessionOperatorLogger(log_path)

            response_match = format_session_log_command("/session log search qwen", logger)
            warning_match = format_session_log_command("/session log search superseded", logger)
            grounding_match = format_session_log_command("/session log search contradicted", logger)

            self.assertIn("turn_id=2", response_match)
            self.assertIn("turn_id=3", warning_match)
            self.assertIn("turn_id=3", grounding_match)

    def test_session_log_search_no_matches_and_missing_log_are_graceful(self) -> None:
        with TemporaryDirectory() as temp_dir:
            missing_logger = SessionOperatorLogger(Path(temp_dir) / "logs" / "missing.jsonl")
            missing_output = format_session_log_command("/session log search qwen", missing_logger)
            self.assertIsNotNone(missing_output)
            self.assertIn("Session operator log not found", missing_output)

            log_path = Path(temp_dir) / "logs" / "session_operator_log.jsonl"
            log_path.parent.mkdir(parents=True, exist_ok=True)
            log_path.write_text(json.dumps({"turn_id": 4, "user_input": "SQLite"}) + "\n", encoding="utf-8")
            logger = SessionOperatorLogger(log_path)
            no_match_output = format_session_log_command("/session log search qwen", logger)
            self.assertIsNotNone(no_match_output)
            self.assertIn("No matches found", no_match_output)

    def test_session_log_search_empty_query_prints_usage(self) -> None:
        with TemporaryDirectory() as temp_dir:
            logger = SessionOperatorLogger(Path(temp_dir) / "logs" / "session_operator_log.jsonl")

            output = format_session_log_command("/session log search", logger)

            self.assertIsNotNone(output)
            self.assertIn("Usage:", output)
            self.assertIn("/session log search <text>", output)

    def test_session_log_search_malformed_jsonl_line_does_not_crash(self) -> None:
        with TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "logs" / "session_operator_log.jsonl"
            log_path.parent.mkdir(parents=True)
            log_path.write_text(
                '{"turn_id": 5, "user_input": "Valid"}\n'
                'this is malformed but mentions qwen\n',
                encoding="utf-8",
            )
            logger = SessionOperatorLogger(log_path)

            output = format_session_log_command("/session log search qwen", logger)

            self.assertIsNotNone(output)
            self.assertIn("malformed_json: true", output)
            self.assertIn("line: 2", output)
            self.assertIn("qwen", output)

    def test_session_log_search_default_limit_is_twenty_and_custom_limit_is_supported(self) -> None:
        with TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "logs" / "session_operator_log.jsonl"
            log_path.parent.mkdir(parents=True)
            entries = [
                {
                    "turn_id": index,
                    "timestamp": f"2026-06-04T00:{index:02d}:00+00:00",
                    "user_input": f"SQLite query {index}",
                    "response_preview": "SQLite result",
                    "observer": {"query_type": "memory_inventory"},
                    "self_reflection": {"warnings": [], "correction_hints": []},
                    "grounding_audit": {"grounding_status": "grounded", "warnings": []},
                }
                for index in range(1, 26)
            ]
            log_path.write_text("\n".join(json.dumps(entry) for entry in entries) + "\n", encoding="utf-8")
            logger = SessionOperatorLogger(log_path)

            default_output = format_session_log_command("/session log search sqlite", logger)
            limited_output = format_session_log_command("/session log search sqlite --limit 3", logger)

            self.assertIn("Found 25 match(es). Showing 20 of 25.", default_output)
            self.assertIn("turn_id=25", default_output)
            self.assertNotIn("turn_id=5", default_output)
            self.assertIn("Found 25 match(es). Showing 3 of 25.", limited_output)
            self.assertIn("turn_id=25", limited_output)
            self.assertIn("turn_id=23", limited_output)
            self.assertNotIn("turn_id=22", limited_output)

    def test_session_log_search_is_read_only(self) -> None:
        with TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "logs" / "session_operator_log.jsonl"
            log_path.parent.mkdir(parents=True)
            log_path.write_text(json.dumps({"turn_id": 6, "user_input": "SQLite"}) + "\n", encoding="utf-8")
            logger = SessionOperatorLogger(log_path)
            before_bytes = log_path.read_bytes()
            before_count = logger.status().entry_count

            output = format_session_log_command("/session log search sqlite", logger)

            self.assertIsNotNone(output)
            self.assertEqual(log_path.read_bytes(), before_bytes)
            self.assertEqual(logger.status().entry_count, before_count)

    def test_session_log_export_creates_export_directory_and_markdown_file(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            log_path = root / "logs" / "session_operator_log.jsonl"
            log_path.parent.mkdir(parents=True)
            log_path.write_text(
                json.dumps(
                    {
                        "turn_id": 1,
                        "timestamp": "2026-06-04T00:00:00+00:00",
                        "user_input": "What storage system are we using now?",
                        "response_preview": "SQLite is current.",
                        "observer": {"query_type": "memory_inventory"},
                        "retrieved_memory_ids": ["abc"],
                        "self_reflection": {"memory_alignment": "ok", "warnings": [], "correction_hints": []},
                        "grounding_audit": {"grounding_status": "grounded", "warnings": []},
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            logger = SessionOperatorLogger(log_path)

            output = format_session_log_command("/session log export", logger)
            export_files = list((root / "exports").glob("session_log_export_*.md"))

            self.assertIsNotNone(output)
            self.assertIn("Session log export created.", output)
            self.assertIn("Entries exported: 1", output)
            self.assertIn("Format: md", output)
            self.assertEqual(len(export_files), 1)
            content = export_files[0].read_text(encoding="utf-8")
            self.assertIn("# Proto-Mind Session Log Export", content)
            self.assertIn("Order: chronological", content)
            self.assertIn("What storage system are we using now?", content)

    def test_session_log_export_default_exports_max_twenty_chronological_entries(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            log_path = root / "logs" / "session_operator_log.jsonl"
            log_path.parent.mkdir(parents=True)
            entries = [
                {
                    "turn_id": index,
                    "timestamp": f"2026-06-04T00:{index:02d}:00+00:00",
                    "user_input": f"Turn {index}",
                    "response_preview": f"Response {index}",
                    "observer": {"query_type": "new_question"},
                    "self_reflection": {"memory_alignment": "ok", "warnings": [], "correction_hints": []},
                    "grounding_audit": {"grounding_status": "grounded", "warnings": []},
                }
                for index in range(1, 26)
            ]
            log_path.write_text("\n".join(json.dumps(entry) for entry in entries) + "\n", encoding="utf-8")
            logger = SessionOperatorLogger(log_path)

            output = format_session_log_command("/session log export", logger)
            export_file = next((root / "exports").glob("session_log_export_*.md"))
            content = export_file.read_text(encoding="utf-8")

            self.assertIn("Entries exported: 20", output)
            self.assertIn("Entries exported: 20", content)
            self.assertNotIn("- turn_id: 5", content)
            self.assertIn("- turn_id: 6", content)
            self.assertIn("- turn_id: 25", content)
            self.assertLess(content.index("- turn_id: 6"), content.index("- turn_id: 25"))

    def test_session_log_export_last_exports_requested_recent_entries(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            log_path = root / "logs" / "session_operator_log.jsonl"
            log_path.parent.mkdir(parents=True)
            entries = [
                {
                    "turn_id": index,
                    "timestamp": f"2026-06-04T00:0{index}:00+00:00",
                    "user_input": f"Turn {index}",
                    "observer": {"query_type": "new_question"},
                    "self_reflection": {"memory_alignment": "ok", "warnings": [], "correction_hints": []},
                    "grounding_audit": {"grounding_status": "grounded", "warnings": []},
                }
                for index in range(1, 6)
            ]
            log_path.write_text("\n".join(json.dumps(entry) for entry in entries) + "\n", encoding="utf-8")
            logger = SessionOperatorLogger(log_path)

            output = format_session_log_command("/session log export --last 2", logger)
            export_file = next((root / "exports").glob("session_log_export_*.md"))
            content = export_file.read_text(encoding="utf-8")

            self.assertIn("Entries exported: 2", output)
            self.assertNotIn("- turn_id: 3", content)
            self.assertIn("- turn_id: 4", content)
            self.assertIn("- turn_id: 5", content)
            self.assertLess(content.index("- turn_id: 4"), content.index("- turn_id: 5"))

    def test_session_log_export_json_format_is_supported(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            log_path = root / "logs" / "session_operator_log.jsonl"
            log_path.parent.mkdir(parents=True)
            log_path.write_text(json.dumps({"turn_id": 1, "user_input": "JSON export"}) + "\n", encoding="utf-8")
            logger = SessionOperatorLogger(log_path)

            output = format_session_log_command("/session log export --format json", logger)
            export_file = next((root / "exports").glob("session_log_export_*.json"))
            payload = json.loads(export_file.read_text(encoding="utf-8"))

            self.assertIn("Format: json", output)
            self.assertEqual(payload["entries_exported"], 1)
            self.assertEqual(payload["order"], "chronological")
            self.assertEqual(payload["entries"][0]["entry"]["user_input"], "JSON export")

    def test_session_log_export_missing_and_empty_log_are_graceful(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            missing_logger = SessionOperatorLogger(root / "logs" / "missing.jsonl")
            missing_output = format_session_log_command("/session log export", missing_logger)
            self.assertIsNotNone(missing_output)
            self.assertIn("Session operator log not found", missing_output)

            empty_log = root / "logs" / "session_operator_log.jsonl"
            empty_log.parent.mkdir(parents=True, exist_ok=True)
            empty_log.write_text("", encoding="utf-8")
            empty_logger = SessionOperatorLogger(empty_log)
            empty_output = format_session_log_command("/session log export", empty_logger)
            self.assertIsNotNone(empty_output)
            self.assertIn("Session operator log is empty", empty_output)

    def test_session_log_export_malformed_jsonl_line_is_included(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            log_path = root / "logs" / "session_operator_log.jsonl"
            log_path.parent.mkdir(parents=True)
            log_path.write_text(
                '{"turn_id": 1, "user_input": "Valid"}\n'
                'malformed line with qwen\n',
                encoding="utf-8",
            )
            logger = SessionOperatorLogger(log_path)

            output = format_session_log_command("/session log export --last 2", logger)
            export_file = next((root / "exports").glob("session_log_export_*.md"))
            content = export_file.read_text(encoding="utf-8")

            self.assertIn("Entries exported: 2", output)
            self.assertIn("- malformed_json: true", content)
            self.assertIn("malformed line with qwen", content)

    def test_session_log_export_invalid_last_values_show_clean_errors(self) -> None:
        with TemporaryDirectory() as temp_dir:
            logger = SessionOperatorLogger(Path(temp_dir) / "logs" / "session_operator_log.jsonl")

            invalid_output = format_session_log_command("/session log export --last abc", logger)
            zero_output = format_session_log_command("/session log export --last 0", logger)

            self.assertEqual(invalid_output, "Invalid --last value. Usage: /session log export [--last N]")
            self.assertEqual(zero_output, "--last must be greater than 0.")

    def test_session_log_export_is_read_only_for_log_and_not_logged_as_turn(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            log_path = root / "logs" / "session_operator_log.jsonl"
            log_path.parent.mkdir(parents=True)
            log_path.write_text(json.dumps({"turn_id": 1, "user_input": "Export me"}) + "\n", encoding="utf-8")
            logger = SessionOperatorLogger(log_path)
            before_bytes = log_path.read_bytes()
            before_count = logger.status().entry_count

            output = format_session_log_command("/session log export", logger)

            self.assertIsNotNone(output)
            self.assertEqual(log_path.read_bytes(), before_bytes)
            self.assertEqual(logger.status().entry_count, before_count)

    def test_session_review_prints_summary_for_existing_log(self) -> None:
        with TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "logs" / "session_operator_log.jsonl"
            log_path.parent.mkdir(parents=True)
            entries = [
                {
                    "turn_id": 1,
                    "timestamp": "2026-06-04T00:00:00+00:00",
                    "user_input": "What storage system are we using now?",
                    "reasoner_backend": "mock",
                    "observer": {"query_type": "memory_inventory", "tags": ["storage", "current"]},
                    "retrieved_memory_ids": ["a", "b"],
                    "self_reflection": {"memory_alignment": "ok", "warnings": [], "correction_hints": []},
                    "grounding_audit": {"grounding_status": "grounded", "warnings": []},
                },
                {
                    "turn_id": 2,
                    "timestamp": "2026-06-04T00:01:00+00:00",
                    "user_input": "Do you remember my response style preference?",
                    "reasoner_backend": "mock",
                    "observer": {"query_type": "memory_inventory", "tags": ["preference", "response_style"]},
                    "retrieved_memory_ids": ["b"],
                    "self_reflection": {
                        "memory_alignment": "ok",
                        "warnings": ["Response may be long."],
                        "correction_hints": ["Respect short answers."],
                    },
                    "grounding_audit": {"grounding_status": "grounded", "warnings": []},
                },
                {
                    "turn_id": 3,
                    "timestamp": "2026-06-04T00:02:00+00:00",
                    "user_input": "Hello",
                    "reasoner_backend": "mock",
                    "observer": {"query_type": "new_question", "tags": ["general"]},
                    "retrieved_memory_ids": [],
                    "self_reflection": {"memory_alignment": "ok", "warnings": [], "correction_hints": []},
                    "grounding_audit": {"grounding_status": "not_needed", "warnings": []},
                },
            ]
            log_path.write_text("\n".join(json.dumps(entry) for entry in entries) + "\n", encoding="utf-8")
            logger = SessionOperatorLogger(log_path)

            output = format_session_log_command("/session review", logger)

            self.assertIsNotNone(output)
            self.assertIn("Session Review", output)
            self.assertIn("Entries reviewed: 3", output)
            self.assertIn("Window: last 20", output)
            self.assertIn("- memory_inventory: 2", output)
            self.assertIn("- new_question: 1", output)
            self.assertIn("- grounded: 2", output)
            self.assertIn("- not_needed: 1", output)
            self.assertIn("- warnings: 1", output)
            self.assertIn("- hints: 1", output)
            self.assertIn("entries with retrieved ids: 2", output)
            self.assertIn("total retrieved ids referenced: 3", output)
            self.assertIn("unique retrieved ids: 2", output)
            self.assertIn("- mock: 3", output)
            self.assertIn("- storage: 1", output)
            self.assertIn("Response may be long.", output)

    def test_session_review_default_uses_max_twenty_entries(self) -> None:
        with TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "logs" / "session_operator_log.jsonl"
            log_path.parent.mkdir(parents=True)
            entries = [
                {
                    "turn_id": index,
                    "user_input": f"Turn {index}",
                    "observer": {"query_type": "new_question"},
                    "self_reflection": {"memory_alignment": "ok", "warnings": [], "correction_hints": []},
                    "grounding_audit": {"grounding_status": "grounded", "warnings": []},
                }
                for index in range(1, 26)
            ]
            log_path.write_text("\n".join(json.dumps(entry) for entry in entries) + "\n", encoding="utf-8")
            logger = SessionOperatorLogger(log_path)

            output = format_session_log_command("/session review", logger)

            self.assertIn("Entries reviewed: 20", output)
            self.assertNotIn("Turn 5", output)
            self.assertIn("Turn 21", output)
            self.assertIn("Turn 25", output)

    def test_session_review_last_reviews_requested_recent_entries(self) -> None:
        with TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "logs" / "session_operator_log.jsonl"
            log_path.parent.mkdir(parents=True)
            entries = [
                {
                    "turn_id": index,
                    "user_input": f"Turn {index}",
                    "observer": {"query_type": "new_question"},
                    "self_reflection": {"memory_alignment": "ok", "warnings": [], "correction_hints": []},
                    "grounding_audit": {"grounding_status": "grounded", "warnings": []},
                }
                for index in range(1, 8)
            ]
            log_path.write_text("\n".join(json.dumps(entry) for entry in entries) + "\n", encoding="utf-8")
            logger = SessionOperatorLogger(log_path)

            output = format_session_log_command("/session review --last 3", logger)

            self.assertIn("Entries reviewed: 3", output)
            self.assertIn("Window: last 3", output)
            self.assertNotIn("Turn 4", output)
            self.assertIn("Turn 5", output)
            self.assertIn("Turn 7", output)

    def test_session_review_missing_empty_and_malformed_logs_are_graceful(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            missing_logger = SessionOperatorLogger(root / "logs" / "missing.jsonl")
            missing_output = format_session_log_command("/session review", missing_logger)
            self.assertIn("Session operator log not found", missing_output)

            log_path = root / "logs" / "session_operator_log.jsonl"
            log_path.parent.mkdir(parents=True, exist_ok=True)
            log_path.write_text("", encoding="utf-8")
            empty_logger = SessionOperatorLogger(log_path)
            empty_output = format_session_log_command("/session review", empty_logger)
            self.assertIn("Session operator log is empty", empty_output)

            log_path.write_text(
                json.dumps(
                    {
                        "turn_id": 1,
                        "user_input": "Valid",
                        "observer": {"query_type": "new_question"},
                        "self_reflection": {"memory_alignment": "ok", "warnings": [], "correction_hints": []},
                        "grounding_audit": {"grounding_status": "grounded", "warnings": []},
                    }
                )
                + "\nmalformed review line\n",
                encoding="utf-8",
            )
            malformed_logger = SessionOperatorLogger(log_path)
            malformed_output = format_session_log_command("/session review --last 2", malformed_logger)
            self.assertIn("Entries reviewed: 2", malformed_output)
            self.assertIn("Malformed entries: 1", malformed_output)
            self.assertIn("line 2: malformed JSONL entry", malformed_output)

    def test_session_review_invalid_last_values_show_clean_errors(self) -> None:
        with TemporaryDirectory() as temp_dir:
            logger = SessionOperatorLogger(Path(temp_dir) / "logs" / "session_operator_log.jsonl")

            invalid_output = format_session_log_command("/session review --last abc", logger)
            zero_output = format_session_log_command("/session review --last 0", logger)

            self.assertEqual(invalid_output, "Invalid --last value. Usage: /session review [--last N]")
            self.assertEqual(zero_output, "--last must be greater than 0.")

    def test_session_review_is_read_only_and_not_logged_as_turn(self) -> None:
        with TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "logs" / "session_operator_log.jsonl"
            log_path.parent.mkdir(parents=True)
            log_path.write_text(json.dumps({"turn_id": 1, "user_input": "Review me"}) + "\n", encoding="utf-8")
            logger = SessionOperatorLogger(log_path)
            before_bytes = log_path.read_bytes()
            before_count = logger.status().entry_count

            output = format_session_log_command("/session review", logger)

            self.assertIsNotNone(output)
            self.assertEqual(log_path.read_bytes(), before_bytes)
            self.assertEqual(logger.status().entry_count, before_count)

    def test_session_health_prints_ok_for_healthy_existing_log(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "exports").mkdir()
            (root / "backups").mkdir()
            log_path = root / "logs" / "session_operator_log.jsonl"
            log_path.parent.mkdir(parents=True)
            log_path.write_text(
                json.dumps(
                    {
                        "turn_id": 1,
                        "user_input": "Healthy turn",
                        "observer": {"query_type": "new_question"},
                        "self_reflection": {"warnings": [], "correction_hints": []},
                        "grounding_audit": {"grounding_status": "grounded", "warnings": []},
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            logger = SessionOperatorLogger(log_path)

            output = format_session_log_command("/session health", logger)

            self.assertIsNotNone(output)
            self.assertIn("Session Health", output)
            self.assertIn("Status: OK", output)
            self.assertIn("session log exists: OK", output)
            self.assertIn("session log readable: OK", output)
            self.assertIn("entries readable: OK", output)
            self.assertIn("malformed entries: 0", output)
            self.assertIn("recent entries checked: 1", output)
            self.assertIn("configured window: 20", output)
            self.assertIn("total log entries: 1", output)
            self.assertIn(f"log: {log_path}", output)

    def test_session_health_is_read_only_and_not_logged_as_turn(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "exports").mkdir()
            (root / "backups").mkdir()
            log_path = root / "logs" / "session_operator_log.jsonl"
            log_path.parent.mkdir(parents=True)
            log_path.write_text(json.dumps({"turn_id": 1, "user_input": "Health me"}) + "\n", encoding="utf-8")
            logger = SessionOperatorLogger(log_path)
            before_bytes = log_path.read_bytes()
            before_count = logger.status().entry_count

            output = format_session_log_command("/session health", logger)

            self.assertIsNotNone(output)
            self.assertEqual(log_path.read_bytes(), before_bytes)
            self.assertEqual(logger.status().entry_count, before_count)

    def test_session_health_missing_and_empty_log_return_warn(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "exports").mkdir()
            (root / "backups").mkdir()
            missing_logger = SessionOperatorLogger(root / "logs" / "missing.jsonl")

            missing_output = format_session_log_command("/session health", missing_logger)

            self.assertIn("Status: WARN", missing_output)
            self.assertIn("session log exists: WARN", missing_output)
            self.assertIn("Session operator log not found.", missing_output)

            log_path = root / "logs" / "session_operator_log.jsonl"
            log_path.parent.mkdir(parents=True, exist_ok=True)
            log_path.write_text("", encoding="utf-8")
            empty_logger = SessionOperatorLogger(log_path)
            empty_output = format_session_log_command("/session health", empty_logger)

            self.assertIn("Status: WARN", empty_output)
            self.assertIn("entries readable: WARN", empty_output)
            self.assertIn("total log entries: 0", empty_output)
            self.assertIn("Session operator log is empty.", empty_output)

    def test_session_health_malformed_jsonl_returns_warn_and_counts_entries(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "exports").mkdir()
            (root / "backups").mkdir()
            log_path = root / "logs" / "session_operator_log.jsonl"
            log_path.parent.mkdir(parents=True)
            log_path.write_text(
                json.dumps(
                    {
                        "turn_id": 1,
                        "user_input": "Valid",
                        "self_reflection": {"warnings": [], "correction_hints": []},
                        "grounding_audit": {"grounding_status": "grounded", "warnings": []},
                    }
                )
                + "\nmalformed health line\n",
                encoding="utf-8",
            )
            logger = SessionOperatorLogger(log_path)

            output = format_session_log_command("/session health", logger)

            self.assertIn("Status: WARN", output)
            self.assertIn("malformed entries: 1", output)
            self.assertIn("recent entries checked: 2", output)
            self.assertIn("Malformed JSONL entries found", output)

    def test_session_health_reports_missing_export_and_backup_dirs_without_creating_them(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            log_path = root / "logs" / "session_operator_log.jsonl"
            log_path.parent.mkdir(parents=True)
            log_path.write_text(json.dumps({"turn_id": 1, "user_input": "Dirs"}) + "\n", encoding="utf-8")
            logger = SessionOperatorLogger(log_path)

            output = format_session_log_command("/session health", logger)

            self.assertIn("Status: WARN", output)
            self.assertIn("export directory exists: WARN", output)
            self.assertIn("backup directory exists: WARN", output)
            self.assertFalse((root / "exports").exists())
            self.assertFalse((root / "backups").exists())

    def test_session_health_counts_reflection_and_grounding_issues(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "exports").mkdir()
            (root / "backups").mkdir()
            log_path = root / "logs" / "session_operator_log.jsonl"
            log_path.parent.mkdir(parents=True)
            log_path.write_text(
                json.dumps(
                    {
                        "turn_id": 1,
                        "user_input": "Issues",
                        "self_reflection": {
                            "warnings": ["reflection warning"],
                            "correction_hints": ["hint"],
                        },
                        "grounding_audit": {
                            "grounding_status": "contradicted",
                            "active_decision_status": "contradicted",
                            "superseded_memory_status": "treated_as_current",
                            "warnings": ["grounding warning"],
                        },
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            logger = SessionOperatorLogger(log_path)

            output = format_session_log_command("/session health", logger)

            self.assertIn("Status: WARN", output)
            self.assertIn("recent reflection warnings: 1", output)
            self.assertIn("recent correction hints: 1", output)
            self.assertIn("recent grounding issues: 4", output)

    def test_session_health_last_window_and_invalid_values(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "exports").mkdir()
            (root / "backups").mkdir()
            log_path = root / "logs" / "session_operator_log.jsonl"
            log_path.parent.mkdir(parents=True)
            entries = [
                {
                    "turn_id": index,
                    "user_input": f"Turn {index}",
                    "self_reflection": {"warnings": [], "correction_hints": []},
                    "grounding_audit": {"grounding_status": "grounded", "warnings": []},
                }
                for index in range(1, 6)
            ]
            log_path.write_text("\n".join(json.dumps(entry) for entry in entries) + "\n", encoding="utf-8")
            logger = SessionOperatorLogger(log_path)

            output = format_session_log_command("/session health --last 2", logger)
            invalid_output = format_session_log_command("/session health --last abc", logger)
            zero_output = format_session_log_command("/session health --last 0", logger)

            self.assertIn("recent entries checked: 2", output)
            self.assertIn("configured window: 2", output)
            self.assertIn("total log entries: 5", output)
            self.assertEqual(invalid_output, "Invalid --last value. Usage: /session health [--last N]")
            self.assertEqual(zero_output, "--last must be greater than 0.")

    def test_session_doctor_prints_ok_report_for_healthy_existing_log(self) -> None:
        with TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "logs" / "session_operator_log.jsonl"
            log_path.parent.mkdir(parents=True)
            log_path.write_text(
                json.dumps(
                    {
                        "turn_id": 1,
                        "user_input": "Healthy",
                        "reasoner_backend": "ollama",
                        "observer": {"query_type": "new_question"},
                        "retrieved_memory_ids": [],
                        "self_reflection": {"warnings": [], "correction_hints": []},
                        "grounding_audit": {"grounding_status": "grounded", "warnings": []},
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            logger = SessionOperatorLogger(log_path)

            output = format_session_log_command("/session doctor", logger)

            self.assertIsNotNone(output)
            self.assertIn("Session Doctor", output)
            self.assertIn("Status: OK", output)
            self.assertIn("Entries analyzed: 1", output)
            self.assertIn("Session log appears readable", output)
            self.assertIn("No grounding issues detected", output)

    def test_session_doctor_warns_for_reflection_warnings_and_correction_hints(self) -> None:
        with TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "logs" / "session_operator_log.jsonl"
            log_path.parent.mkdir(parents=True)
            entries = [
                {
                    "turn_id": 2,
                    "user_input": "Preference turn",
                    "reasoner_backend": "mock",
                    "observer": {"query_type": "memory_inventory"},
                    "retrieved_memory_ids": ["p1"],
                    "self_reflection": {
                        "warnings": ["Response may not respect the active preference for concise or short answers."],
                        "correction_hints": ["Respect active preference next turn: I prefer short answers."],
                    },
                    "grounding_audit": {"grounding_status": "grounded", "warnings": []},
                },
                {
                    "turn_id": 3,
                    "user_input": "Preference turn again",
                    "reasoner_backend": "mock",
                    "observer": {"query_type": "memory_inventory"},
                    "retrieved_memory_ids": ["p1"],
                    "self_reflection": {
                        "warnings": ["Response may not respect the active preference for concise or short answers."],
                        "correction_hints": ["Respect active preference next turn: I prefer short answers."],
                    },
                    "grounding_audit": {"grounding_status": "grounded", "warnings": []},
                },
            ]
            log_path.write_text("\n".join(json.dumps(entry) for entry in entries) + "\n", encoding="utf-8")
            logger = SessionOperatorLogger(log_path)

            output = format_session_log_command("/session doctor", logger)

            self.assertIn("Status: WARN", output)
            self.assertIn("Reflection warnings detected", output)
            self.assertIn("turns: 2, 3", output)
            self.assertIn("Correction hints detected", output)
            self.assertIn("Repeated warning theme detected", output)
            self.assertIn("x2", output)
            self.assertIn("Run /session log warnings", output)

    def test_session_doctor_counts_grounding_issues(self) -> None:
        with TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "logs" / "session_operator_log.jsonl"
            log_path.parent.mkdir(parents=True)
            log_path.write_text(
                json.dumps(
                    {
                        "turn_id": 4,
                        "user_input": "Is JSON current?",
                        "reasoner_backend": "ollama",
                        "observer": {"query_type": "memory_inventory"},
                        "retrieved_memory_ids": ["d1"],
                        "self_reflection": {"warnings": [], "correction_hints": []},
                        "grounding_audit": {
                            "grounding_status": "contradicted",
                            "active_decision_status": "contradicted",
                            "superseded_memory_status": "treated_as_current",
                            "warnings": ["Grounding issue."],
                        },
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            logger = SessionOperatorLogger(log_path)

            output = format_session_log_command("/session doctor", logger)

            self.assertIn("Status: WARN", output)
            self.assertIn("Grounding issues detected", output)
            self.assertIn("turns: 4", output)
            self.assertIn("count: 1", output)

    def test_session_doctor_missing_empty_and_malformed_logs_are_graceful(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            missing_logger = SessionOperatorLogger(root / "logs" / "missing.jsonl")
            missing_output = format_session_log_command("/session doctor", missing_logger)
            self.assertIn("Status: WARN", missing_output)
            self.assertIn("Session operator log not found", missing_output)

            log_path = root / "logs" / "session_operator_log.jsonl"
            log_path.parent.mkdir(parents=True, exist_ok=True)
            log_path.write_text("", encoding="utf-8")
            empty_logger = SessionOperatorLogger(log_path)
            empty_output = format_session_log_command("/session doctor", empty_logger)
            self.assertIn("Status: WARN", empty_output)
            self.assertIn("Session operator log is empty", empty_output)

            log_path.write_text(
                json.dumps(
                    {
                        "turn_id": 5,
                        "user_input": "Valid",
                        "self_reflection": {"warnings": [], "correction_hints": []},
                        "grounding_audit": {"grounding_status": "grounded", "warnings": []},
                    }
                )
                + "\nmalformed doctor line\n",
                encoding="utf-8",
            )
            malformed_logger = SessionOperatorLogger(log_path)
            malformed_output = format_session_log_command("/session doctor --last 2", malformed_logger)
            self.assertIn("Status: WARN", malformed_output)
            self.assertIn("Malformed JSONL entries detected", malformed_output)
            self.assertIn("lines: 2", malformed_output)
            self.assertIn("count: 1", malformed_output)

    def test_session_doctor_unreadable_log_returns_error(self) -> None:
        with TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "logs" / "session_operator_log.jsonl"
            log_path.parent.mkdir(parents=True)
            log_path.write_text(json.dumps({"turn_id": 1, "user_input": "Unreadable"}) + "\n", encoding="utf-8")
            logger = SessionOperatorLogger(log_path)

            with patch("proto_mind.session_log._non_empty_line_count", side_effect=OSError("permission denied")):
                output = format_session_log_command("/session doctor", logger)

            self.assertIn("Status: ERROR", output)
            self.assertIn("Session operator log cannot be read", output)
            self.assertIn("permission denied", output)

    def test_session_doctor_last_window_and_invalid_values(self) -> None:
        with TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "logs" / "session_operator_log.jsonl"
            log_path.parent.mkdir(parents=True)
            entries = [
                {
                    "turn_id": index,
                    "user_input": f"Turn {index}",
                    "reasoner_backend": "ollama",
                    "observer": {"query_type": "new_question"},
                    "retrieved_memory_ids": [],
                    "self_reflection": {"warnings": [], "correction_hints": []},
                    "grounding_audit": {"grounding_status": "grounded", "warnings": []},
                }
                for index in range(1, 6)
            ]
            log_path.write_text("\n".join(json.dumps(entry) for entry in entries) + "\n", encoding="utf-8")
            logger = SessionOperatorLogger(log_path)

            output = format_session_log_command("/session doctor --last 2", logger)
            invalid_output = format_session_log_command("/session doctor --last abc", logger)
            zero_output = format_session_log_command("/session doctor --last 0", logger)

            self.assertIn("Entries analyzed: 2", output)
            self.assertIn("Window: last 2", output)
            self.assertEqual(invalid_output, "Invalid --last value. Usage: /session doctor [--last N]")
            self.assertEqual(zero_output, "--last must be greater than 0.")

    def test_session_doctor_reports_retrieval_gap_and_mock_backend_info(self) -> None:
        with TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "logs" / "session_operator_log.jsonl"
            log_path.parent.mkdir(parents=True)
            log_path.write_text(
                json.dumps(
                    {
                        "turn_id": 6,
                        "user_input": "What do you remember?",
                        "reasoner_backend": "mock",
                        "observer": {"query_type": "memory_inventory"},
                        "retrieved_memory_ids": [],
                        "self_reflection": {"warnings": [], "correction_hints": []},
                        "grounding_audit": {"grounding_status": "grounded", "warnings": []},
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            logger = SessionOperatorLogger(log_path)

            output = format_session_log_command("/session doctor", logger)

            self.assertIn("Potential retrieval gaps detected", output)
            self.assertIn("turns: 6", output)
            self.assertIn("Reasoner/backend summary", output)
            self.assertIn("mock: 1", output)
            self.assertIn("Current log appears mock-backed", output)

    def test_session_doctor_is_read_only_and_creates_no_exports_or_backups(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            log_path = root / "logs" / "session_operator_log.jsonl"
            log_path.parent.mkdir(parents=True)
            log_path.write_text(json.dumps({"turn_id": 7, "user_input": "Doctor"}) + "\n", encoding="utf-8")
            logger = SessionOperatorLogger(log_path)
            before_bytes = log_path.read_bytes()
            before_count = logger.status().entry_count

            output = format_session_log_command("/session doctor", logger)

            self.assertIsNotNone(output)
            self.assertEqual(log_path.read_bytes(), before_bytes)
            self.assertEqual(logger.status().entry_count, before_count)
            self.assertFalse((root / "exports").exists())
            self.assertFalse((root / "backups").exists())

    def test_session_self_check_prints_ok_combined_report_for_healthy_log(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "exports").mkdir()
            (root / "backups").mkdir()
            log_path = root / "logs" / "session_operator_log.jsonl"
            log_path.parent.mkdir(parents=True)
            log_path.write_text(
                json.dumps(
                    {
                        "turn_id": 1,
                        "user_input": "Healthy",
                        "reasoner_backend": "ollama",
                        "observer": {"query_type": "new_question"},
                        "retrieved_memory_ids": [],
                        "self_reflection": {"warnings": [], "correction_hints": []},
                        "grounding_audit": {"grounding_status": "grounded", "warnings": []},
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            logger = SessionOperatorLogger(log_path)

            output = format_session_log_command("/session self-check", logger)

            self.assertIsNotNone(output)
            self.assertIn("Session Self-Check", output)
            self.assertIn("Overall: OK", output)
            self.assertIn("Entries checked: 1", output)
            self.assertIn("Health Summary:", output)
            self.assertIn("- log exists: OK", output)
            self.assertIn("- malformed entries: 0", output)
            self.assertIn("- reflection warnings: 0", output)
            self.assertIn("- grounding issues: 0", output)
            self.assertIn("Doctor Summary:", output)
            self.assertIn("No reflection warnings: OK", output)
            self.assertIn("No grounding issues: OK", output)
            self.assertIn("Recommended next commands:", output)
            self.assertIn("/session review --last 20", output)

    def test_session_self_check_warns_for_reflection_warnings_and_hints(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "exports").mkdir()
            (root / "backups").mkdir()
            log_path = root / "logs" / "session_operator_log.jsonl"
            log_path.parent.mkdir(parents=True)
            log_path.write_text(
                json.dumps(
                    {
                        "turn_id": 2,
                        "user_input": "Preference",
                        "reasoner_backend": "mock",
                        "observer": {"query_type": "memory_inventory"},
                        "retrieved_memory_ids": ["p1"],
                        "self_reflection": {
                            "warnings": ["Response may not respect the active preference for concise or short answers."],
                            "correction_hints": ["Respect active preference next turn: I prefer short answers."],
                        },
                        "grounding_audit": {"grounding_status": "grounded", "warnings": []},
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            logger = SessionOperatorLogger(log_path)

            output = format_session_log_command("/session self-check", logger)

            self.assertIn("Overall: WARN", output)
            self.assertIn("- reflection warnings: 1", output)
            self.assertIn("- correction hints: 1", output)
            self.assertIn("Reflection warnings: WARN", output)
            self.assertIn("Correction hints: INFO", output)
            self.assertIn("/session doctor --last 20", output)
            self.assertIn("/session log warnings", output)

    def test_session_self_check_missing_empty_and_malformed_logs_are_graceful(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            missing_logger = SessionOperatorLogger(root / "logs" / "missing.jsonl")
            missing_output = format_session_log_command("/session self-check", missing_logger)
            self.assertIn("Overall: WARN", missing_output)
            self.assertIn("Session operator log not found: WARN", missing_output)
            self.assertIn("/session log status", missing_output)

            log_path = root / "logs" / "session_operator_log.jsonl"
            log_path.parent.mkdir(parents=True, exist_ok=True)
            log_path.write_text("", encoding="utf-8")
            empty_logger = SessionOperatorLogger(log_path)
            empty_output = format_session_log_command("/session self-check", empty_logger)
            self.assertIn("Overall: WARN", empty_output)
            self.assertIn("Session operator log is empty: WARN", empty_output)

            log_path.write_text(
                json.dumps(
                    {
                        "turn_id": 3,
                        "user_input": "Valid",
                        "self_reflection": {"warnings": [], "correction_hints": []},
                        "grounding_audit": {"grounding_status": "grounded", "warnings": []},
                    }
                )
                + "\nmalformed self-check line\n",
                encoding="utf-8",
            )
            malformed_logger = SessionOperatorLogger(log_path)
            malformed_output = format_session_log_command("/session self-check --last 2", malformed_logger)
            self.assertIn("Overall: WARN", malformed_output)
            self.assertIn("- malformed entries: 1", malformed_output)
            self.assertIn("Malformed JSONL entries: WARN", malformed_output)

    def test_session_self_check_unreadable_log_returns_error(self) -> None:
        with TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "logs" / "session_operator_log.jsonl"
            log_path.parent.mkdir(parents=True)
            log_path.write_text(json.dumps({"turn_id": 1, "user_input": "Unreadable"}) + "\n", encoding="utf-8")
            logger = SessionOperatorLogger(log_path)

            with patch("proto_mind.session_log._non_empty_line_count", side_effect=OSError("permission denied")):
                output = format_session_log_command("/session self-check", logger)

            self.assertIn("Overall: ERROR", output)
            self.assertIn("- log readable: ERROR", output)
            self.assertIn("Session operator log cannot be read: ERROR", output)
            self.assertIn("permission denied", output)
            self.assertIn("/session log status", output)

    def test_session_self_check_last_window_and_invalid_values(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "exports").mkdir()
            (root / "backups").mkdir()
            log_path = root / "logs" / "session_operator_log.jsonl"
            log_path.parent.mkdir(parents=True)
            entries = [
                {
                    "turn_id": index,
                    "user_input": f"Turn {index}",
                    "reasoner_backend": "ollama",
                    "observer": {"query_type": "new_question"},
                    "retrieved_memory_ids": [],
                    "self_reflection": {"warnings": [], "correction_hints": []},
                    "grounding_audit": {"grounding_status": "grounded", "warnings": []},
                }
                for index in range(1, 6)
            ]
            log_path.write_text("\n".join(json.dumps(entry) for entry in entries) + "\n", encoding="utf-8")
            logger = SessionOperatorLogger(log_path)

            output = format_session_log_command("/session self-check --last 2", logger)
            invalid_output = format_session_log_command("/session self-check --last abc", logger)
            zero_output = format_session_log_command("/session self-check --last 0", logger)

            self.assertIn("Entries checked: 2", output)
            self.assertIn("Window: last 2", output)
            self.assertIn("/session review --last 2", output)
            self.assertEqual(invalid_output, "Invalid --last value. Usage: /session self-check [--last N]")
            self.assertEqual(zero_output, "--last must be greater than 0.")

    def test_session_self_check_is_read_only_and_creates_no_exports_or_backups(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            log_path = root / "logs" / "session_operator_log.jsonl"
            log_path.parent.mkdir(parents=True)
            log_path.write_text(json.dumps({"turn_id": 4, "user_input": "Self check"}) + "\n", encoding="utf-8")
            logger = SessionOperatorLogger(log_path)
            before_bytes = log_path.read_bytes()
            before_count = logger.status().entry_count

            output = format_session_log_command("/session self-check", logger)

            self.assertIsNotNone(output)
            self.assertEqual(log_path.read_bytes(), before_bytes)
            self.assertEqual(logger.status().entry_count, before_count)
            self.assertFalse((root / "exports").exists())
            self.assertFalse((root / "backups").exists())

    def test_session_logging_does_not_modify_memory_files_without_normal_turn_changes(self) -> None:
        with TemporaryDirectory() as temp_dir:
            tmp_path = Path(temp_dir)
            logger = SessionOperatorLogger(tmp_path / "logs" / "session_operator_log.jsonl")
            data_dir = tmp_path / "data"
            store = MemoryStore(
                working_path=data_dir / "working_memory.json",
                persistent_path=data_dir / "persistent_memory.json",
            )
            before_working = store.working_path.read_bytes()
            before_persistent = store.persistent_path.read_bytes()
            status = format_session_log_command("/session log status", logger)

            self.assertIsNotNone(status)
            self.assertEqual(store.working_path.read_bytes(), before_working)
            self.assertEqual(store.persistent_path.read_bytes(), before_persistent)

    def test_session_capture_design_defaults_disabled_without_creating_files(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            review = SessionCaptureDesignReview(root)
            before = list(root.rglob("*"))

            state = review.read_state()
            output = format_session_capture_design_status(review)

            self.assertEqual(list(root.rglob("*")), before)
        self.assertEqual(state["design"]["status"], SESSION_CAPTURE_DESIGN_STATUS)
        self.assertEqual(state["decision"], "KEEP_DISABLED")
        self.assertFalse(state["gate"]["effective_enabled"])
        self.assertFalse(state["design"]["implementation_authorized"])
        self.assertIn("implementation_authorized: false", output)

    def test_session_capture_design_requires_explicit_single_session_consent(self) -> None:
        review = SessionCaptureDesignReview(Path("/tmp/proto-mind-design-unused"))
        policy = review.policy
        consent = review.sections()["consent"]
        scope = review.sections()["scope"]

        self.assertEqual(policy.consent_model, SESSION_CAPTURE_CONSENT_MODEL)
        self.assertTrue(policy.process_restart_resets_consent)
        self.assertTrue(any("one current process session" in item for item in consent))
        self.assertTrue(any("Exclude slash commands" in item for item in scope))
        self.assertFalse(policy.operator_command_capture_allowed)
        self.assertFalse(policy.natural_routed_command_capture_allowed)

    def test_session_capture_design_denies_full_and_injected_context_content(self) -> None:
        review = SessionCaptureDesignReview(Path("/tmp/proto-mind-design-unused"))
        privacy = review.sections()["privacy"]

        self.assertFalse(review.policy.full_content_allowed)
        self.assertFalse(review.policy.context_injection_payload_allowed)
        self.assertTrue(any("system/hidden prompts" in item for item in privacy))
        self.assertTrue(any("secret/redaction regression tests" in item for item in privacy))

    def test_session_capture_design_retention_denies_backfill_and_automatic_actions(self) -> None:
        review = SessionCaptureDesignReview(Path("/tmp/proto-mind-design-unused"))
        retention = review.sections()["retention"]

        self.assertEqual(review.policy.persistence_default, "none")
        self.assertFalse(review.policy.backfill_allowed)
        self.assertFalse(review.policy.automatic_retention_actions_allowed)
        self.assertTrue(any("Never backfill" in item for item in retention))
        self.assertTrue(any("separate milestone" in item for item in retention))

    def test_session_capture_design_failure_isolation_fails_closed(self) -> None:
        review = SessionCaptureDesignReview(Path("/tmp/proto-mind-design-unused"))
        isolation = review.sections()["failure_isolation"]

        self.assertEqual(review.policy.failure_mode, SESSION_CAPTURE_FAILURE_MODE)
        self.assertTrue(any("normal user turn" in item for item in isolation))
        self.assertTrue(any("disable capture" in item for item in isolation))
        self.assertTrue(any("Do not retry" in item for item in isolation))

    def test_session_capture_design_doctor_has_no_activation_or_command_surface(self) -> None:
        with TemporaryDirectory() as temp_dir:
            review = SessionCaptureDesignReview(Path(temp_dir))
            report = review.doctor()
            output = format_session_capture_design_doctor(review)

        self.assertEqual(report.status, "OK")
        self.assertFalse(
            {"activate", "append", "capture", "enable", "persist", "run", "start", "write"}
            & set(dir(review))
        )
        self.assertFalse(
            any(spec.prefix.startswith(PERSISTENT_EXPERIENCE_COMMAND_PREFIXES) for spec in COMMAND_REGISTRY)
        )
        self.assertIn("Status: OK", output)
        self.assertIn("implementation_authorized: false", output)

    def test_session_capture_design_keeps_manual_enable_request_ineffective(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            review = SessionCaptureDesignReview(root)
            review.gate.settings_path.parent.mkdir(parents=True)
            settings = dict(DEFAULT_CAPTURE_SETTINGS)
            settings["enabled"] = True
            review.gate.settings_path.write_text(json.dumps(settings), encoding="utf-8")
            before = review.gate.settings_path.read_bytes()

            report = review.doctor()

            self.assertEqual(review.gate.settings_path.read_bytes(), before)
        self.assertEqual(report.status, "WARN")
        self.assertFalse(report.effective_capture_enabled)
        self.assertFalse(report.live_writer_installed)

    def test_session_capture_design_rejects_full_content_settings(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            review = SessionCaptureDesignReview(root)
            review.gate.settings_path.parent.mkdir(parents=True)
            settings = dict(DEFAULT_CAPTURE_SETTINGS)
            settings["persist_full_content"] = True
            review.gate.settings_path.write_text(json.dumps(settings), encoding="utf-8")

            report = review.doctor()
            output = format_session_capture_design_review(review)
            checklist = format_session_capture_design_checklist(review)

        self.assertEqual(report.status, "ERROR")
        self.assertFalse(report.effective_capture_enabled)
        self.assertIn("Deny full user messages", output)
        self.assertIn("BLOCKED_BY_DESIGN", checklist)

    def test_session_capture_design_benchmark_creates_no_files(self) -> None:
        report = run_session_capture_design_benchmark()
        output = format_session_capture_design_benchmark(report)

        self.assertEqual(report.status, "OK")
        self.assertEqual(report.files_created, 0)
        self.assertTrue(all(report.checks.values()))
        self.assertIn("no config, live ledger", output)
        self.assertIn("no_files_created", output)

    def test_session_consent_phrase_is_exact_and_session_bound(self) -> None:
        spec = SessionConsentStateMachineSpec("  session / one  ")

        self.assertEqual(spec.session_id, "session-one")
        self.assertEqual(
            spec.expected_phrase(),
            f"{CONSENT_PHRASE_PREFIX} session-one",
        )
        with self.assertRaisesRegex(ValueError, "session_id must not be empty"):
            SessionConsentStateMachineSpec("   ")

    def test_session_consent_requires_preview_before_exact_consent(self) -> None:
        spec = SessionConsentStateMachineSpec("consent-test")

        premature = spec.evaluate(
            "disabled",
            "consent_submitted",
            provided_phrase=spec.expected_phrase(),
        )
        preview = spec.evaluate("disabled", "preview_shown")
        consent = spec.evaluate(
            preview.next_state,
            "consent_submitted",
            provided_phrase=spec.expected_phrase(),
        )

        self.assertFalse(premature.accepted)
        self.assertEqual(premature.reason, "preview_required_before_consent")
        self.assertEqual(preview.next_state, "previewed")
        self.assertEqual(consent.next_state, "consented")
        self.assertTrue(consent.token_matched)
        self.assertFalse(consent.capture_performed)

    def test_session_consent_rejects_broad_cross_session_and_chained_phrases(self) -> None:
        spec = SessionConsentStateMachineSpec("primary")
        other = SessionConsentStateMachineSpec("other")
        phrases = [
            "yes",
            f"{CONSENT_PHRASE_PREFIX} all",
            other.expected_phrase(),
            spec.expected_phrase() + "; extra",
        ]

        results = [
            spec.evaluate("previewed", "consent_submitted", provided_phrase=phrase)
            for phrase in phrases
        ]

        self.assertTrue(all(not result.accepted for result in results))
        self.assertTrue(all(result.next_state == "previewed" for result in results))
        self.assertEqual(results[0].reason, "broad_or_implicit_consent_refused")
        self.assertEqual(results[-1].reason, "extra_or_chained_input_refused")

    def test_session_consent_scope_allows_only_normal_prompt_after_consent(self) -> None:
        spec = SessionConsentStateMachineSpec("scope-test")
        before = spec.evaluate("previewed", "normal_prompt_observed")
        after = spec.evaluate("consented", "normal_prompt_observed")

        self.assertFalse(before.scope_allowed)
        self.assertEqual(before.reason, "consent_not_active")
        self.assertTrue(after.scope_allowed)
        self.assertTrue(after.consent_active)
        self.assertFalse(after.capture_performed)
        self.assertFalse(after.implementation_authorized)

    def test_session_consent_bypasses_operator_natural_internal_and_history_events(self) -> None:
        spec = SessionConsentStateMachineSpec("bypass-test")
        events = [
            "slash_command_observed",
            "natural_routed_command_observed",
            "internal_report_observed",
            "historical_turn_observed",
        ]

        results = [spec.evaluate("consented", event) for event in events]

        self.assertTrue(all(not result.accepted for result in results))
        self.assertTrue(all(not result.scope_allowed for result in results))
        self.assertTrue(all(result.next_state == "consented" for result in results))
        self.assertEqual(results[-1].reason, "historical_backfill_refused")

    def test_session_consent_stop_and_failure_disable_remaining_session(self) -> None:
        spec = SessionConsentStateMachineSpec("stop-test")
        stopped = spec.evaluate("consented", "stop_requested")
        failed = spec.evaluate("consented", "capture_failure_observed")
        after_stop = spec.evaluate(stopped.next_state, "normal_prompt_observed")

        self.assertEqual(stopped.next_state, "stopped")
        self.assertEqual(failed.next_state, "stopped")
        self.assertEqual(failed.reason, "capture_disabled_fail_closed")
        self.assertFalse(after_stop.scope_allowed)
        self.assertEqual(after_stop.reason, "consent_not_active")

    def test_session_consent_restart_expires_and_cannot_reuse_phrase(self) -> None:
        spec = SessionConsentStateMachineSpec("expiry-test")
        expired = spec.evaluate("consented", "process_restarted")
        reused = spec.evaluate(
            expired.next_state,
            "consent_submitted",
            provided_phrase=spec.expected_phrase(),
        )

        self.assertEqual(expired.next_state, "expired")
        self.assertFalse(expired.consent_active)
        self.assertFalse(reused.accepted)
        self.assertEqual(reused.next_state, "expired")

    def test_session_consent_results_never_retain_raw_phrase_or_execute(self) -> None:
        spec = SessionConsentStateMachineSpec("privacy-test")
        phrase = spec.expected_phrase()
        result = spec.evaluate("previewed", "consent_submitted", provided_phrase=phrase)
        payload = result.to_dict()

        self.assertNotIn("provided_phrase", payload)
        self.assertNotIn(phrase, payload.values())
        self.assertFalse(payload["capture_performed"])
        self.assertFalse(payload["persistence_performed"])
        self.assertFalse(payload["implementation_authorized"])

    def test_session_consent_doctor_and_reports_are_design_only(self) -> None:
        spec = SessionConsentStateMachineSpec("doctor-test")
        report = spec.doctor()
        outputs = "\n".join(
            [
                format_session_consent_status(spec),
                format_session_consent_transitions(spec),
                format_session_consent_refusals(spec),
                format_session_consent_doctor(spec),
            ]
        )

        self.assertEqual(report.status, "OK")
        self.assertEqual(report.refusal_case_count, 14)
        self.assertFalse(
            {"capture", "persist", "write", "append", "enable", "activate"}
            & set(dir(spec))
        )
        self.assertFalse(
            any(item.prefix.startswith(PERSISTENT_EXPERIENCE_COMMAND_PREFIXES) for item in COMMAND_REGISTRY)
        )
        self.assertIn("DESIGN_ONLY_DISABLED", outputs)
        self.assertIn("stores no consent state", outputs)

    def test_session_consent_benchmark_is_closed_and_creates_no_files(self) -> None:
        report = run_session_consent_benchmark()
        output = format_session_consent_benchmark(report)

        self.assertEqual(report.status, "OK")
        self.assertEqual(report.transition_count, 7)
        self.assertEqual(report.refusal_case_count, 14)
        self.assertEqual(report.files_created, 0)
        self.assertTrue(all(report.checks.values()))
        self.assertIn("no_raw_phrase_retained", output)
        self.assertIn("no consent capture", output)

    def test_session_start_brief_reuses_daily_export_snapshot_and_warning_signals(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            store.save_persistent_memory([])
            _create_healthy_export_dirs(project_root)

            output = format_session_ritual_command(
                "/session start-brief",
                project_root=project_root,
                memory_store=store,
            )

            self.assertIn("Session Start Brief", output)
            self.assertIn(f"project_root: {project_root}", output)
            self.assertIn("command_registry: commands=387 categories=41", output)
            self.assertIn("daily_doctor: OK", output)
            self.assertIn("export_doctor: OK", output)
            self.assertIn("latest_snapshot: daily_fixture.json", output)
            self.assertIn("latest_snapshot_diff: daily_fixture.json", output)
            self.assertIn("Suggested first safe manual action:", output)

    def test_session_end_summary_is_live_and_only_suggests_manual_wrap_up(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            store.save_persistent_memory([])
            _create_healthy_export_dirs(project_root)

            output = format_session_ritual_command(
                "/session end-summary",
                project_root=project_root,
                memory_store=store,
            )

            self.assertIn("Session End Summary", output)
            self.assertIn("system_status:", output)
            self.assertIn("export_health: OK", output)
            self.assertIn("Recommended manual wrap-up:", output)
            self.assertIn("scripts/run_tests.sh", output)
            self.assertIn("not a persistent log", output)
            self.assertIn("no file was written", output)

    def test_session_checkpoint_advice_reads_signals_without_running_checkpoint_or_tests(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            store.save_persistent_memory([])
            _create_healthy_export_dirs(project_root)
            (project_root / "PROTO_MIND_ARCHITECT_LEDGER.md").write_text(
                "- Current test count: 443 unit tests OK.\n", encoding="utf-8"
            )

            output = format_session_ritual_command(
                "/session checkpoint-advice",
                project_root=project_root,
                memory_store=store,
            )

            self.assertIn("Session Checkpoint Advice", output)
            self.assertIn("test_status: 443 tests OK (Architect Ledger; not re-run by this command)", output)
            self.assertIn("latest_snapshot: daily_fixture.json", output)
            self.assertIn("latest_snapshot_diff: daily_fixture.json", output)
            self.assertIn("No checkpoint, snapshot, test, export, or repair command was run", output)

    def test_session_handoff_brief_is_copyable_and_includes_rule_zero(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            store.save_persistent_memory([])
            _create_healthy_export_dirs(project_root)
            (project_root / "PROTO_MIND_ARCHITECT_LEDGER.md").write_text(
                "## Last Completed Milestone\n\nDaily Agent Layer v1:\n\n"
                "## Next Candidate Tasks\n\n- Session rituals follow-up.\n",
                encoding="utf-8",
            )

            output = format_session_ritual_command(
                "/session handoff-brief",
                project_root=project_root,
                memory_store=store,
            )

            self.assertIn("Proto-Mind Session Handoff Brief", output)
            self.assertIn("Current milestone: Daily Agent Layer v1", output)
            self.assertIn("Registry: 387 commands across 41 categories", output)
            self.assertIn("/daily status; /daily brief; /daily doctor; /daily next", output)
            self.assertIn("/exports status; /exports inventory", output)
            self.assertIn("/proto snapshot-diff-status", output)
            self.assertIn("Session rituals follow-up.", output)
            self.assertIn("backup/checkpoint first", output)
            self.assertIn("no clipboard, file, external call, model call, or command execution", output)

    def test_session_ritual_commands_are_read_only_through_shared_handler(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            coordinator, store, _ = build_test_system(project_root / "proto_mind")
            store.save_persistent_memory([])
            logger = SessionOperatorLogger.from_project_root(project_root)
            coordinator.session_logger = logger
            _create_healthy_export_dirs(project_root)
            format_context_command("/context injection disable", project_root=project_root)
            data_dir = project_root / "proto_mind" / "data"
            exports_root = project_root / "proto_mind" / "exports"
            before_data = {path.name: path.read_bytes() for path in data_dir.glob("*") if path.is_file()}
            before_exports = {
                str(path.relative_to(exports_root)): path.read_bytes()
                for path in exports_root.rglob("*")
                if path.is_file()
            }

            outputs = [
                process_interactive_input(
                    command,
                    coordinator=coordinator,
                    session_logger=logger,
                    project_root=project_root,
                )
                for command in (
                    "/session start-brief",
                    "/session end-summary",
                    "/session checkpoint-advice",
                    "/session handoff-brief",
                )
            ]

            self.assertIn("Session Start Brief", outputs[0])
            self.assertIn("Session End Summary", outputs[1])
            self.assertIn("Session Checkpoint Advice", outputs[2])
            self.assertIn("Session Handoff Brief", outputs[3])
            after_data = {path.name: path.read_bytes() for path in data_dir.glob("*") if path.is_file()}
            after_exports = {
                str(path.relative_to(exports_root)): path.read_bytes()
                for path in exports_root.rglob("*")
                if path.is_file()
            }
            self.assertEqual(after_data, before_data)
            self.assertEqual(after_exports, before_exports)
            self.assertFalse(json.loads((data_dir / "context_injection.json").read_text(encoding="utf-8"))["enabled"])
            self.assertEqual(logger.status().entry_count, 0)
