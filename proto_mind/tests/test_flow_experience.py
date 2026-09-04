"""Core flow checks: experience."""
from __future__ import annotations

import unittest
from proto_mind.tests.flow_fixtures import (
    BoundedExperiencePreviewBuffer,
    COMMAND_REGISTRY,
    DEFAULT_CAPTURE_SETTINGS,
    EXPERIENCE_ACTIVATION_DECISION,
    EXPERIENCE_NEXT_STAGE,
    EXPERIENCE_PILOT_MAX_BYTES,
    EXPERIENCE_PILOT_MAX_EVENTS,
    EXPERIENCE_PREVIEW_MAX_CHARS,
    EXPERIENCE_ROOT_EVENT_TYPES,
    ExperienceCaptureActivationReadinessReview,
    ExperienceCaptureGate,
    ExperienceEpisodeProjectionError,
    ExperienceEpisodeProjector,
    ExperienceEvent,
    ExperienceLearningInputAdapter,
    ExperienceLearningInputError,
    ExperienceLearningReviewer,
    ExperienceLifecycleBuilder,
    ExperienceTraceBuilder,
    ExperienceTraceIndex,
    LEARNING_INPUT_SELECTION_MODE,
    LIVE_CAPTURE_HOOK_INSTALLED,
    LIVE_EXPERIENCE_PERSISTENCE_ENABLED,
    MemoryRecord,
    MemoryStore,
    PERSISTENT_EXPERIENCE_COMMAND_PREFIXES,
    Path,
    REDACTION_PREFIX,
    SOAK_MAX_BYTES,
    SOAK_MAX_EVENTS,
    SOAK_MAX_EVENTS_PER_TURN,
    SOAK_NORMAL_TURNS,
    SessionOperatorLogger,
    SimpleNamespace,
    SkillLibrary,
    SupervisedExperiencePilot,
    TemporaryDirectory,
    TemporaryExperienceLedgerStore,
    build_failure_correction_trace,
    build_success_lifecycle_trace,
    build_test_system,
    classify_command,
    command_registry_doctor,
    compact_preview,
    find_sensitive_preview_categories,
    format_experience_activation_benchmark,
    format_experience_activation_doctor,
    format_experience_activation_evidence,
    format_experience_activation_status,
    format_experience_capture_doctor,
    format_experience_capture_preview,
    format_experience_capture_soak,
    format_experience_capture_status,
    format_experience_doctor,
    format_experience_episode,
    format_experience_episode_benchmark,
    format_experience_episode_doctor,
    format_experience_episode_list,
    format_experience_event_explanation,
    format_experience_explainability_benchmark,
    format_experience_explainability_doctor,
    format_experience_learning_benchmark,
    format_experience_learning_candidate,
    format_experience_learning_doctor,
    format_experience_learning_input_benchmark,
    format_experience_learning_input_doctor,
    format_experience_learning_input_snapshot,
    format_experience_learning_review,
    format_experience_persistence_policy,
    format_experience_pilot_command,
    format_experience_preview,
    format_experience_privacy_benchmark,
    format_experience_privacy_doctor,
    format_experience_privacy_status,
    format_experience_trace_map,
    format_experience_vocabulary_report,
    get_experience_pilot,
    inspect_experience_events,
    inspect_experience_privacy,
    json,
    peek_experience_pilot,
    process_interactive_input,
    redact_experience_preview,
    run_experience_activation_benchmark,
    run_experience_capture_soak,
    run_experience_episode_benchmark,
    run_experience_explainability_benchmark,
    run_experience_learning_benchmark,
    run_experience_learning_input_benchmark,
    run_experience_privacy_benchmark,
    run_experience_vocabulary_benchmark,
)


class ExperienceFlowTests(unittest.TestCase):
    def test_experience_ledger_builds_typed_provenance_trace(self) -> None:
        with TemporaryDirectory() as temp_dir:
            coordinator, _, _ = build_test_system(Path(temp_dir))
            result = coordinator.handle("Что ты помнишь о текущем решении Proto-Mind?")
            events = ExperienceTraceBuilder(session_id="test-session").build_turn_events(
                "Что ты помнишь о текущем решении Proto-Mind?",
                result,
                turn_id=1,
                trace_id="test-trace",
                created_at="2026-01-01T00:00:01Z",
            )

        report = inspect_experience_events(events)
        event_types = [event.event_type for event in events]
        self.assertEqual(report.status, "OK")
        self.assertEqual(event_types[0], "conversation_observed")
        self.assertIn("intent_detected", event_types)
        self.assertIn("memory_retrieved", event_types)
        self.assertIn("response_generated", event_types)
        self.assertIn("reflection_evaluated", event_types)
        self.assertIn("grounding_evaluated", event_types)
        self.assertGreater(report.provenance_edge_count, 0)

    def test_experience_ledger_uses_compact_previews_without_full_prompts(self) -> None:
        user_input = "Объясни observer. " + ("очень подробно " * 40)
        with TemporaryDirectory() as temp_dir:
            coordinator, _, _ = build_test_system(Path(temp_dir))
            result = coordinator.handle(user_input)
            events = ExperienceTraceBuilder(session_id="privacy-test").build_turn_events(
                user_input,
                result,
                turn_id=1,
                trace_id="privacy",
                created_at="2026-01-01T00:00:01Z",
            )

        serialized = json.dumps([event.to_dict() for event in events], ensure_ascii=False)
        observed = events[0]
        response = next(event for event in events if event.event_type == "response_generated")
        self.assertLessEqual(len(observed.payload["input_preview"]), EXPERIENCE_PREVIEW_MAX_CHARS)
        self.assertLessEqual(len(response.payload["response_preview"]), EXPERIENCE_PREVIEW_MAX_CHARS)
        self.assertNotIn('"user_input"', serialized)
        self.assertNotIn('"full_response"', serialized)
        self.assertNotIn('"system_prompt"', serialized)
        self.assertNotIn('"injected_prompt"', serialized)

    def test_experience_ledger_records_memory_provenance_without_new_write(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            coordinator, store, _ = build_test_system(root)
            result = coordinator.handle("Запомни, что текущая цель — Experience Ledger.")
            before = store.persistent_path.read_bytes()
            events = ExperienceTraceBuilder(session_id="memory-test").build_turn_events(
                "Запомни, что текущая цель — Experience Ledger.",
                result,
                turn_id=1,
                trace_id="memory",
                created_at="2026-01-01T00:00:01Z",
            )
            after = store.persistent_path.read_bytes()

        recorded = next(event for event in events if event.event_type == "memory_recorded")
        evaluated = next(event for event in events if event.event_type == "memory_evaluated")
        self.assertEqual(recorded.payload["record_id"], result.memory_summary.stored_record_id)
        self.assertEqual(recorded.source_event_ids, [evaluated.id])
        self.assertEqual(before, after)

    def test_experience_ledger_doctor_detects_duplicate_and_missing_provenance(self) -> None:
        with TemporaryDirectory() as temp_dir:
            coordinator, _, _ = build_test_system(Path(temp_dir))
            result = coordinator.handle("Explain observer briefly.")
            events = ExperienceTraceBuilder(session_id="doctor-test").build_turn_events(
                "Explain observer briefly.",
                result,
                turn_id=1,
                trace_id="doctor",
                created_at="2026-01-01T00:00:01Z",
            )
        broken = [event.to_dict() for event in events]
        broken.append(events[0].to_dict())
        broken[1]["source_event_ids"] = ["evt_missing"]

        report = inspect_experience_events(broken)
        output = format_experience_doctor(broken)
        self.assertEqual(report.status, "ERROR")
        self.assertTrue(any("Duplicate event id" in issue for issue in report.issues))
        self.assertTrue(any("missing or later source" in issue for issue in report.issues))
        self.assertIn("Status: ERROR", output)

    def test_experience_ledger_doctor_rejects_forbidden_payload_fields(self) -> None:
        with TemporaryDirectory() as temp_dir:
            coordinator, _, _ = build_test_system(Path(temp_dir))
            result = coordinator.handle("Explain coordinator briefly.")
            events = ExperienceTraceBuilder(session_id="privacy-doctor").build_turn_events(
                "Explain coordinator briefly.",
                result,
                turn_id=1,
                trace_id="privacy-doctor",
                created_at="2026-01-01T00:00:01Z",
            )
        broken = [event.to_dict() for event in events]
        broken[0]["payload"]["full_response"] = "must not be stored"

        report = inspect_experience_events(broken)
        self.assertEqual(report.status, "ERROR")
        self.assertTrue(any("forbidden payload key" in issue for issue in report.issues))

    def test_experience_ledger_preview_is_explicitly_in_memory_only(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            coordinator, _, _ = build_test_system(root)
            result = coordinator.handle("What is the current project focus?")
            events = ExperienceTraceBuilder(session_id="preview-test").build_turn_events(
                "What is the current project focus?",
                result,
                turn_id=1,
                trace_id="preview",
                created_at="2026-01-01T00:00:01Z",
            )
            output = format_experience_preview(events)

            self.assertFalse((root / "data" / "experience_ledger.jsonl").exists())
        self.assertIn("Status: OK", output)
        self.assertIn("in-memory preview only", output)
        self.assertIn("No live Experience Ledger file", output)

    def test_experience_persistence_policy_keeps_live_writes_disabled(self) -> None:
        output = format_experience_persistence_policy()

        self.assertFalse(LIVE_EXPERIENCE_PERSISTENCE_ENABLED)
        self.assertIn("Status: PREVIEW_ONLY", output)
        self.assertIn("isolated temporary paths only", output)
        self.assertIn("no automatic deletion", output)
        self.assertIn("live Coordinator hook: absent", output)

    def test_experience_capture_gate_missing_config_is_safe_and_read_only(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            gate = ExperienceCaptureGate(root)

            status = gate.status()
            output = format_experience_capture_status(gate)

            self.assertEqual(status.status, "OK")
            self.assertFalse(status.settings_exists)
            self.assertEqual(status.settings_source, "safe_defaults_missing_file")
            self.assertFalse(status.enabled_requested)
            self.assertFalse(status.effective_enabled)
            self.assertFalse(gate.settings_path.exists())
            self.assertFalse(gate.live_ledger_path.exists())
        self.assertIn("Capture is safely disabled", output)
        self.assertIn("no config initialization", output)

    def test_experience_capture_preview_never_processes_or_writes_a_turn(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            gate = ExperienceCaptureGate(root)
            before = list(root.rglob("*"))

            preview = gate.preview()
            output = format_experience_capture_preview(gate)
            after = list(root.rglob("*"))

        self.assertEqual(before, after)
        self.assertFalse(preview["would_capture"])
        self.assertEqual(preview["reason"], "disabled_by_default")
        self.assertFalse(preview["mutation_performed"])
        self.assertIn("No normal prompt was processed", output)
        self.assertIn("mutation_performed: false", output)

    def test_experience_capture_gate_reads_valid_disabled_config_without_mutation(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            gate = ExperienceCaptureGate(root)
            gate.settings_path.parent.mkdir(parents=True)
            gate.settings_path.write_text(
                json.dumps(DEFAULT_CAPTURE_SETTINGS, sort_keys=True),
                encoding="utf-8",
            )
            before = gate.settings_path.read_bytes()

            status = gate.status()
            doctor = format_experience_capture_doctor(gate)

            self.assertEqual(gate.settings_path.read_bytes(), before)
        self.assertEqual(status.status, "OK")
        self.assertEqual(status.settings_source, "local_file")
        self.assertFalse(status.effective_enabled)
        self.assertIn("Status: OK", doctor)

    def test_experience_capture_gate_refuses_enabled_request_without_hook(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            gate = ExperienceCaptureGate(root)
            settings = dict(DEFAULT_CAPTURE_SETTINGS)
            settings["enabled"] = True
            gate.settings_path.parent.mkdir(parents=True)
            gate.settings_path.write_text(json.dumps(settings), encoding="utf-8")
            before = gate.settings_path.read_bytes()

            status = gate.status()
            preview = gate.preview()

            self.assertEqual(gate.settings_path.read_bytes(), before)
            self.assertFalse(gate.live_ledger_path.exists())
        self.assertFalse(LIVE_CAPTURE_HOOK_INSTALLED)
        self.assertEqual(status.status, "WARN")
        self.assertTrue(status.enabled_requested)
        self.assertFalse(status.effective_enabled)
        self.assertEqual(preview["reason"], "live_writer_hook_absent")

    def test_experience_capture_gate_corrupt_config_fails_closed(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            gate = ExperienceCaptureGate(root)
            gate.settings_path.parent.mkdir(parents=True)
            gate.settings_path.write_text('{"enabled":', encoding="utf-8")
            before = gate.settings_path.read_bytes()

            status = gate.status()
            output = format_experience_capture_doctor(gate)

            self.assertEqual(gate.settings_path.read_bytes(), before)
            self.assertFalse(gate.live_ledger_path.exists())
        self.assertEqual(status.status, "ERROR")
        self.assertFalse(status.effective_enabled)
        self.assertIn("Settings are unreadable", output)

    def test_experience_capture_gate_rejects_full_content_and_alternate_path(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            gate = ExperienceCaptureGate(root)
            settings = dict(DEFAULT_CAPTURE_SETTINGS)
            settings["persist_full_content"] = True
            settings["write_path"] = "/tmp/alternate-ledger.jsonl"
            gate.settings_path.parent.mkdir(parents=True)
            gate.settings_path.write_text(json.dumps(settings), encoding="utf-8")

            status = gate.status()

        self.assertEqual(status.status, "ERROR")
        self.assertFalse(status.effective_enabled)
        self.assertTrue(any("persist_full_content" in issue for issue in status.issues))
        self.assertTrue(any("Alternate" in issue for issue in status.issues))

    def test_experience_capture_gate_warns_on_unexpected_live_ledger(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            gate = ExperienceCaptureGate(root)
            gate.live_ledger_path.parent.mkdir(parents=True)
            gate.live_ledger_path.write_text("{}\n", encoding="utf-8")
            before = gate.live_ledger_path.read_bytes()

            status = gate.status()
            output = format_experience_capture_status(gate)

            self.assertEqual(gate.live_ledger_path.read_bytes(), before)
        self.assertEqual(status.status, "WARN")
        self.assertTrue(status.live_ledger_exists)
        self.assertFalse(status.effective_enabled)
        self.assertIn("inspect it manually", output)

    def test_experience_capture_gate_exposes_no_activation_or_write_api(self) -> None:
        gate_methods = set(dir(ExperienceCaptureGate))

        self.assertFalse({"enable", "activate", "append", "capture", "write"} & gate_methods)
        self.assertFalse(LIVE_CAPTURE_HOOK_INSTALLED)
        self.assertFalse(LIVE_EXPERIENCE_PERSISTENCE_ENABLED)
        self.assertFalse(
            any(spec.prefix.startswith(PERSISTENT_EXPERIENCE_COMMAND_PREFIXES) for spec in COMMAND_REGISTRY)
        )

    def test_experience_privacy_redacts_english_and_russian_credentials(self) -> None:
        english = redact_experience_preview("password=hunter2-secret")
        russian = redact_experience_preview("пароль: сверх-секрет-42")

        self.assertTrue(english.safe)
        self.assertTrue(russian.safe)
        self.assertNotIn("hunter2-secret", english.text)
        self.assertNotIn("сверх-секрет-42", russian.text)
        self.assertIn(REDACTION_PREFIX, english.text)
        self.assertIn(REDACTION_PREFIX, russian.text)

    def test_experience_privacy_redacts_common_credential_formats(self) -> None:
        # Assemble the synthetic fixture without a key-shaped literal in published sources.
        synthetic_aws_key = "AKIA" + "ABCDEFGHIJKLMNOP"
        cases = {
            "Authorization: Bearer abcdefghijklmnopqrstuvwxyz": "bearer_token",
            "postgresql://proto:private-pass@localhost/db": "uri_credentials",
            "sk-proj-abcdefghijklmnopqrstuvwxyz123456": "openai_key",
            "ghp_abcdefghijklmnopqrstuvwxyz123456": "github_token",
            synthetic_aws_key: "aws_access_key",
        }

        for value, category in cases.items():
            with self.subTest(category=category):
                result = redact_experience_preview(value)
                self.assertTrue(result.safe)
                self.assertIn(category, result.categories)
                self.assertNotEqual(result.text, value)

    def test_experience_privacy_keeps_benign_controls_unchanged(self) -> None:
        values = (
            "Use a password manager and rotate credentials regularly.",
            "The token budget is 1200.",
            "Пароль следует хранить в менеджере секретов.",
        )

        for value in values:
            with self.subTest(value=value):
                result = redact_experience_preview(value)
                self.assertEqual(result.text, value)
                self.assertEqual(result.redaction_count, 0)

    def test_experience_privacy_redacts_before_truncation(self) -> None:
        result = redact_experience_preview("api_key=" + ("x" * 200), max_chars=40)

        self.assertTrue(result.safe)
        self.assertTrue(result.truncated is False)
        self.assertLessEqual(result.output_chars, 40)
        self.assertNotIn("x", result.text)
        self.assertIn(REDACTION_PREFIX, result.text)

    def test_experience_privacy_truncation_never_splits_redaction_placeholder(self) -> None:
        value = ("safe context " * 11) + "password=boundary-secret"

        result = redact_experience_preview(value, max_chars=160)

        self.assertTrue(result.truncated)
        self.assertTrue(result.safe)
        self.assertLessEqual(result.output_chars, 160)
        self.assertIn("[REDACTED:credential]", result.text)
        self.assertNotIn("[REDACTE...", result.text)
        self.assertEqual(result.sensitive_remainder_categories, [])

    def test_experience_privacy_redaction_is_idempotent_and_retains_no_input(self) -> None:
        first = redact_experience_preview("ACCESS_TOKEN=temporary-access-value")
        second = redact_experience_preview(first.text)

        self.assertEqual(second.text, first.text)
        self.assertEqual(second.redaction_count, 0)
        self.assertNotIn("value", first.to_dict())
        self.assertNotIn("temporary-access-value", first.to_dict().values())

    def test_experience_ledger_compact_preview_uses_privacy_redaction(self) -> None:
        secret = "integration-secret-value"
        preview = compact_preview(f'Payload {{"api_key": "{secret}"}}')

        self.assertNotIn(secret, preview)
        self.assertIn(REDACTION_PREFIX, preview)
        self.assertEqual(find_sensitive_preview_categories(preview), [])

    def test_experience_trace_builder_never_retains_secret_preview(self) -> None:
        secret = "builder-secret-value"
        with TemporaryDirectory() as temp_dir:
            coordinator, _, _ = build_test_system(Path(temp_dir))
            user_input = f"Explain safe handling. password={secret}"
            result = coordinator.handle(user_input)
            events = ExperienceTraceBuilder(session_id="redaction-test").build_turn_events(
                user_input,
                result,
                turn_id=1,
                trace_id="redaction",
                created_at="2026-01-01T00:00:01Z",
            )

        serialized = json.dumps([event.to_dict() for event in events], ensure_ascii=False)
        self.assertNotIn(secret, serialized)
        self.assertIn(REDACTION_PREFIX, events[0].payload["input_preview"])
        self.assertEqual(inspect_experience_events(events).status, "OK")

    def test_experience_doctor_rejects_unredacted_credential_preview(self) -> None:
        event = {
            "id": "evt_privacy_1_01_conversation_observed",
            "created_at": "2026-01-01T00:00:00Z",
            "event_type": "conversation_observed",
            "session_id": "privacy-doctor",
            "turn_id": "1",
            "source": "test",
            "source_event_ids": [],
            "payload": {
                "input_preview": "password=doctor-secret",
                "input_chars": 22,
                "language_hint": "english",
            },
            "confidence": None,
            "schema_version": 1,
        }

        report = inspect_experience_events([event])

        self.assertEqual(report.status, "ERROR")
        self.assertTrue(any("unredacted credential-like" in issue for issue in report.issues))

    def test_experience_privacy_reports_are_local_design_only(self) -> None:
        report = inspect_experience_privacy()
        output = "\n".join(
            [
                format_experience_privacy_status(),
                format_experience_privacy_doctor(),
            ]
        )

        self.assertEqual(report.status, "OK")
        self.assertEqual(report.rule_count, 9)
        self.assertIn("deterministic_preview_only", output)
        self.assertIn("No capture, persistence", output)
        self.assertFalse(
            any(item.prefix.startswith(PERSISTENT_EXPERIENCE_COMMAND_PREFIXES) for item in COMMAND_REGISTRY)
        )

    def test_experience_privacy_benchmark_passes_without_files(self) -> None:
        report = run_experience_privacy_benchmark()
        output = format_experience_privacy_benchmark()

        self.assertEqual(report.status, "OK")
        self.assertEqual(report.case_count, 16)
        self.assertEqual(report.sensitive_case_count, 12)
        self.assertEqual(report.benign_case_count, 4)
        self.assertEqual(report.files_created, 0)
        self.assertTrue(all(report.checks.values()))
        self.assertIn("no PII inference", output)

    def test_experience_capture_soak_buffer_accepts_valid_detached_event(self) -> None:
        event = ExperienceEvent(
            id="evt_buffer_1_01_conversation_observed",
            created_at="2026-01-01T00:00:00Z",
            event_type="conversation_observed",
            session_id="buffer-test",
            turn_id="1",
            source="test",
            source_event_ids=[],
            payload={"input_preview": "safe preview", "input_chars": 12},
        )
        buffer = BoundedExperiencePreviewBuffer()

        decision = buffer.consider_batch([event])

        self.assertTrue(decision.accepted)
        self.assertEqual(decision.reason, "accepted_in_memory_preview")
        self.assertEqual(buffer.event_count, 1)
        self.assertGreater(buffer.byte_count, 0)
        self.assertEqual(buffer.doctor().status, "OK")
        self.assertFalse(decision.capture_performed)
        self.assertFalse(decision.persistence_performed)

    def test_experience_capture_soak_buffer_rejects_empty_batch(self) -> None:
        buffer = BoundedExperiencePreviewBuffer()

        decision = buffer.consider_batch([])

        self.assertFalse(decision.accepted)
        self.assertEqual(decision.reason, "empty_batch_refused")
        self.assertEqual(buffer.event_count, 0)
        self.assertEqual(buffer.byte_count, 0)

    def test_experience_capture_soak_buffer_enforces_per_turn_limit(self) -> None:
        event = ExperienceEvent(
            id="evt_per_turn_1_01_conversation_observed",
            created_at="2026-01-01T00:00:00Z",
            event_type="conversation_observed",
            session_id="per-turn-test",
            turn_id="1",
            source="test",
            source_event_ids=[],
            payload={"input_preview": "safe preview", "input_chars": 12},
        )
        buffer = BoundedExperiencePreviewBuffer(max_events_per_turn=1)

        decision = buffer.consider_batch([event, event])

        self.assertFalse(decision.accepted)
        self.assertEqual(decision.reason, "per_turn_event_limit")
        self.assertEqual(buffer.event_count, 0)

    def test_experience_capture_soak_buffer_enforces_total_event_limit(self) -> None:
        first = ExperienceEvent(
            id="evt_total_1_01_conversation_observed",
            created_at="2026-01-01T00:00:00Z",
            event_type="conversation_observed",
            session_id="total-test",
            turn_id="1",
            source="test",
            source_event_ids=[],
            payload={"input_preview": "first", "input_chars": 5},
        )
        second = ExperienceEvent(
            id="evt_total_2_01_conversation_observed",
            created_at="2026-01-01T00:00:01Z",
            event_type="conversation_observed",
            session_id="total-test",
            turn_id="2",
            source="test",
            source_event_ids=[],
            payload={"input_preview": "second", "input_chars": 6},
        )
        buffer = BoundedExperiencePreviewBuffer(max_events=1)
        self.assertTrue(buffer.consider_batch([first]).accepted)
        before = buffer.snapshot()

        decision = buffer.consider_batch([second])

        self.assertFalse(decision.accepted)
        self.assertEqual(decision.reason, "total_event_limit")
        self.assertEqual(buffer.snapshot(), before)

    def test_experience_capture_soak_buffer_enforces_total_byte_limit(self) -> None:
        event = ExperienceEvent(
            id="evt_bytes_1_01_conversation_observed",
            created_at="2026-01-01T00:00:00Z",
            event_type="conversation_observed",
            session_id="bytes-test",
            turn_id="1",
            source="test",
            source_event_ids=[],
            payload={"input_preview": "safe preview", "input_chars": 12},
        )
        buffer = BoundedExperiencePreviewBuffer(max_bytes=16)

        decision = buffer.consider_batch([event])

        self.assertFalse(decision.accepted)
        self.assertEqual(decision.reason, "total_byte_limit")
        self.assertEqual(buffer.event_count, 0)

    def test_experience_capture_soak_snapshot_is_detached(self) -> None:
        event = ExperienceEvent(
            id="evt_detached_1_01_conversation_observed",
            created_at="2026-01-01T00:00:00Z",
            event_type="conversation_observed",
            session_id="detached-test",
            turn_id="1",
            source="test",
            source_event_ids=[],
            payload={"input_preview": "safe preview", "input_chars": 12},
        )
        buffer = BoundedExperiencePreviewBuffer()
        buffer.consider_batch([event])
        snapshot = buffer.snapshot()
        snapshot[0]["payload"]["input_preview"] = "mutated outside"

        self.assertEqual(buffer.snapshot()[0]["payload"]["input_preview"], "safe preview")

    def test_experience_capture_soak_models_exact_consent_and_normal_scope(self) -> None:
        report = run_experience_capture_soak()

        self.assertEqual(report.status, "OK")
        self.assertEqual(report.normal_turns, SOAK_NORMAL_TURNS)
        self.assertEqual(report.accepted_normal_turns, SOAK_NORMAL_TURNS)
        self.assertTrue(report.checks["pre_consent_turn_refused"])
        self.assertTrue(report.checks["wrong_consent_refused"])
        self.assertTrue(report.checks["exact_session_consent_modeled"])

    def test_experience_capture_soak_keeps_strict_event_and_byte_bounds(self) -> None:
        report = run_experience_capture_soak()

        self.assertLessEqual(report.event_count, SOAK_MAX_EVENTS)
        self.assertLessEqual(report.byte_count, SOAK_MAX_BYTES)
        self.assertEqual(report.max_events_per_turn, SOAK_MAX_EVENTS_PER_TURN)
        self.assertEqual(report.event_count, 252)
        self.assertTrue(report.checks["count_overflow_refused_without_mutation"])
        self.assertTrue(report.checks["per_turn_overflow_refused"])
        self.assertTrue(report.checks["byte_overflow_refused"])

    def test_experience_capture_soak_covers_redaction_bypass_stop_and_expiry(self) -> None:
        report = run_experience_capture_soak()

        self.assertGreater(report.redaction_markers, 0)
        self.assertEqual(report.bypass_events, 4)
        self.assertTrue(report.checks["credential_fixtures_redacted"])
        self.assertTrue(report.checks["bypass_events_refused"])
        self.assertTrue(report.checks["stop_blocks_later_turn"])
        self.assertTrue(report.checks["failure_stops_session"])
        self.assertTrue(report.checks["restart_expires_consent"])

    def test_experience_capture_soak_creates_no_files_or_runtime_surface(self) -> None:
        report = run_experience_capture_soak()
        output = format_experience_capture_soak(report)

        self.assertEqual(report.files_created, 0)
        self.assertTrue(report.checks["live_capture_boundaries_disabled"])
        self.assertTrue(report.checks["no_persistent_experience_commands"])
        self.assertTrue(report.checks["no_files_created"])
        self.assertTrue(all(report.checks.values()))
        self.assertIn("Synthetic process-memory preview simulation only", output)
        self.assertIn("files_created: 0", output)

    def test_experience_activation_review_keeps_runtime_disabled_when_ready(self) -> None:
        with TemporaryDirectory() as temp_dir:
            report = ExperienceCaptureActivationReadinessReview(Path(temp_dir)).evaluate()

        self.assertEqual(report.status, "OK")
        self.assertEqual(report.decision, EXPERIENCE_ACTIVATION_DECISION)
        self.assertEqual(report.next_stage, EXPERIENCE_NEXT_STAGE)
        self.assertTrue(report.evidence_ready)
        self.assertFalse(report.runtime_activation_allowed)
        self.assertFalse(report.implementation_authorized)
        self.assertFalse(report.mutation_performed)

    def test_experience_activation_review_has_complete_evidence_matrix(self) -> None:
        with TemporaryDirectory() as temp_dir:
            report = ExperienceCaptureActivationReadinessReview(Path(temp_dir)).evaluate()

        self.assertEqual(
            {item.name for item in report.evidence},
            {
                "design_lock",
                "session_consent_spec",
                "privacy_redaction",
                "bounded_growth",
                "temporary_integrity",
                "live_gate_disabled",
                "live_paths_absent",
                "context_injection_disabled",
                "persistence_policy_preview_only",
                "persistent_command_surface_absent",
            },
        )
        self.assertTrue(all(item.ready for item in report.evidence))
        self.assertEqual(report.blockers, [])

    def test_experience_activation_review_is_zero_file_on_empty_root(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            before = list(root.rglob("*"))

            ExperienceCaptureActivationReadinessReview(root).evaluate()

            after = list(root.rglob("*"))
        self.assertEqual(before, after)

    def test_experience_activation_review_doctor_exposes_no_activation_api(self) -> None:
        with TemporaryDirectory() as temp_dir:
            review = ExperienceCaptureActivationReadinessReview(Path(temp_dir))
            report = review.doctor()

        self.assertEqual(report.status, "OK")
        self.assertEqual(report.evidence_count, 10)
        self.assertEqual(report.ready_count, 10)
        self.assertEqual(report.blocker_count, 0)
        self.assertFalse(
            {"activate", "append", "capture", "enable", "execute", "persist", "start", "write"}
            & set(dir(review))
        )

    def test_experience_activation_review_blocks_requested_capture_fixture(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            path = root / "proto_mind" / "data" / "experience_capture.json"
            path.parent.mkdir(parents=True)
            settings = dict(DEFAULT_CAPTURE_SETTINGS)
            settings["enabled"] = True
            path.write_text(json.dumps(settings), encoding="utf-8")
            before = path.read_bytes()

            report = ExperienceCaptureActivationReadinessReview(root).evaluate()

            after = path.read_bytes()
        self.assertEqual(report.status, "BLOCKED")
        self.assertIn("live_gate_disabled", report.blockers)
        self.assertIn("live_paths_absent", report.blockers)
        self.assertFalse(report.runtime_activation_allowed)
        self.assertEqual(before, after)

    def test_experience_activation_review_blocks_enabled_context_fixture(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            path = root / "proto_mind" / "data" / "context_injection.json"
            path.parent.mkdir(parents=True)
            path.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "enabled": True,
                        "mode": "preview_safe",
                        "max_chars": 2500,
                        "include_safety_footer": True,
                        "apply_to": "normal_prompts_only",
                        "updated_at": "2026-01-01T00:00:00Z",
                        "updated_by": "test",
                    }
                ),
                encoding="utf-8",
            )
            before = path.read_bytes()

            report = ExperienceCaptureActivationReadinessReview(root).evaluate()

            after = path.read_bytes()
        self.assertEqual(report.status, "BLOCKED")
        self.assertTrue(report.context_injection_enabled)
        self.assertIn("context_injection_disabled", report.blockers)
        self.assertEqual(before, after)

    def test_experience_activation_review_blocks_malformed_capture_settings(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            path = root / "proto_mind" / "data" / "experience_capture.json"
            path.parent.mkdir(parents=True)
            path.write_text("{malformed", encoding="utf-8")
            before = path.read_bytes()

            review = ExperienceCaptureActivationReadinessReview(root)
            report = review.evaluate()
            doctor = review.doctor()

            after = path.read_bytes()
        self.assertEqual(report.status, "BLOCKED")
        self.assertIn("design_lock", report.blockers)
        self.assertIn("live_gate_disabled", report.blockers)
        self.assertEqual(doctor.status, "WARN")
        self.assertEqual(before, after)

    def test_experience_activation_review_reports_readiness_without_authorization(self) -> None:
        with TemporaryDirectory() as temp_dir:
            review = ExperienceCaptureActivationReadinessReview(Path(temp_dir))
            output = "\n".join(
                [
                    format_experience_activation_status(review),
                    format_experience_activation_evidence(review),
                    format_experience_activation_doctor(review),
                ]
            )

        self.assertIn("decision: KEEP_DISABLED", output)
        self.assertIn("evidence_ready: true", output)
        self.assertIn("runtime_activation_allowed: false", output)
        self.assertIn("implementation_authorized: false", output)
        self.assertIn("[READY] bounded_growth", output)

    def test_experience_activation_benchmark_passes_without_files(self) -> None:
        report = run_experience_activation_benchmark()
        output = format_experience_activation_benchmark(report)

        self.assertEqual(report.status, "OK")
        self.assertEqual(report.evidence_count, 10)
        self.assertEqual(report.ready_count, 10)
        self.assertEqual(report.files_created, 0)
        self.assertTrue(all(report.checks.values()))
        self.assertIn("no activation, capture", output)

    def test_experience_activation_review_adds_no_persistent_command_surface(self) -> None:
        self.assertFalse(
            any(item.prefix.startswith(PERSISTENT_EXPERIENCE_COMMAND_PREFIXES) for item in COMMAND_REGISTRY)
        )
        self.assertFalse(LIVE_CAPTURE_HOOK_INSTALLED)
        self.assertFalse(LIVE_EXPERIENCE_PERSISTENCE_ENABLED)

    def test_experience_vocabulary_success_trace_is_typed_and_valid(self) -> None:
        events = build_success_lifecycle_trace()
        report = inspect_experience_events(events)

        self.assertEqual(report.status, "OK")
        self.assertEqual(len(events), 8)
        self.assertEqual(events[0].event_type, "goal_created")
        self.assertIn("goal_created", EXPERIENCE_ROOT_EVENT_TYPES)
        self.assertEqual(
            [event.event_type for event in events],
            [
                "goal_created",
                "plan_created",
                "tool_called",
                "tool_succeeded",
                "task_completed",
                "reflection_created",
                "lesson_candidate_created",
                "memory_promoted",
            ],
        )

    def test_experience_vocabulary_failure_trace_links_operator_correction(self) -> None:
        events = build_failure_correction_trace()
        report = inspect_experience_events(events)
        failure = next(event for event in events if event.event_type == "tool_failed")
        correction = next(event for event in events if event.event_type == "user_corrected")

        self.assertEqual(report.status, "OK")
        self.assertEqual(len(events), 7)
        self.assertEqual(correction.source_event_ids, [failure.id])
        self.assertEqual(correction.payload["target_event_ids"], [failure.id])

    def test_experience_vocabulary_tool_call_is_evidence_not_execution(self) -> None:
        events = build_success_lifecycle_trace() + build_failure_correction_trace()
        calls = [event for event in events if event.event_type == "tool_called"]

        self.assertEqual(len(calls), 2)
        self.assertTrue(all(call.payload["read_only"] for call in calls))
        self.assertTrue(
            all(call.payload["execution_performed_by_builder"] is False for call in calls)
        )

    def test_experience_vocabulary_memory_promotion_requires_operator_confirmation(self) -> None:
        promotion = next(
            event
            for event in build_success_lifecycle_trace()
            if event.event_type == "memory_promoted"
        )

        self.assertTrue(promotion.payload["operator_confirmation_required"])
        self.assertFalse(promotion.payload["promotion_performed_by_builder"])
        self.assertEqual(len(promotion.payload["evidence_event_ids"]), 1)

    def test_experience_vocabulary_compacts_long_domain_summaries(self) -> None:
        builder = ExperienceLifecycleBuilder(
            session_id="long-preview",
            trace_id="long-preview",
            turn_id=1,
            created_at="2026-01-01T04:00:00Z",
        )
        goal = builder.goal_created(
            goal_id="goal_long",
            title="very long title " * 30,
            success_criteria="very long criteria " * 30,
        )

        self.assertLessEqual(len(goal.payload["title_preview"]), EXPERIENCE_PREVIEW_MAX_CHARS)
        self.assertLessEqual(
            len(goal.payload["success_criteria_preview"]),
            EXPERIENCE_PREVIEW_MAX_CHARS,
        )

    def test_experience_vocabulary_builder_refuses_wrong_or_foreign_source(self) -> None:
        first = ExperienceLifecycleBuilder(
            session_id="source-test",
            trace_id="first",
            turn_id=1,
            created_at="2026-01-01T04:00:00Z",
        )
        second = ExperienceLifecycleBuilder(
            session_id="source-test",
            trace_id="second",
            turn_id=2,
            created_at="2026-01-01T04:01:00Z",
        )
        goal = first.goal_created(goal_id="goal_one", title="Goal one")

        with self.assertRaisesRegex(ValueError, "source events must already exist"):
            second.plan_created(goal, plan_id="plan_foreign", plan="Foreign", step_count=1)
        with self.assertRaisesRegex(ValueError, "expected plan_created"):
            first.tool_called(
                goal,
                call_id="bad_call",
                capability="none",
                input_summary="Wrong source",
            )

    def test_experience_vocabulary_doctor_detects_missing_required_payload(self) -> None:
        broken = [event.to_dict() for event in build_success_lifecycle_trace()]
        tool_success = next(event for event in broken if event["event_type"] == "tool_succeeded")
        del tool_success["payload"]["call_id"]

        report = inspect_experience_events(broken)

        self.assertEqual(report.status, "ERROR")
        self.assertTrue(any("missing payload fields: call_id" in issue for issue in report.issues))

    def test_experience_vocabulary_doctor_detects_wrong_source_type(self) -> None:
        broken = [event.to_dict() for event in build_success_lifecycle_trace()]
        plan = next(event for event in broken if event["event_type"] == "plan_created")
        tool_success = next(event for event in broken if event["event_type"] == "tool_succeeded")
        tool_success["source_event_ids"] = [plan["id"]]

        report = inspect_experience_events(broken)

        self.assertEqual(report.status, "ERROR")
        self.assertTrue(any("requires provenance from one of: tool_called" in issue for issue in report.issues))

    def test_experience_vocabulary_benchmark_verifies_temporary_hash_chain(self) -> None:
        report = run_experience_vocabulary_benchmark()
        output = format_experience_vocabulary_report(report)

        self.assertEqual(report.status, "OK")
        self.assertEqual(report.total_events, 15)
        self.assertEqual(report.provenance_edges, 13)
        self.assertEqual(report.hash_verified, 15)
        self.assertTrue(all(report.checks.values()))
        self.assertIn("temporary_hash_verified: 15/15", output)
        self.assertIn("no goal/task/memory mutation", output)

    def test_experience_trace_index_reports_roots_leaves_and_depth(self) -> None:
        events = build_success_lifecycle_trace() + build_failure_correction_trace()
        index = ExperienceTraceIndex(events)
        report = index.doctor()

        self.assertEqual(report.status, "OK")
        self.assertEqual(report.event_count, 15)
        self.assertEqual(report.root_count, 2)
        self.assertEqual(report.leaf_count, 2)
        self.assertEqual(report.max_depth, 8)

    def test_experience_trace_explains_full_memory_promotion_lineage(self) -> None:
        events = build_success_lifecycle_trace()
        index = ExperienceTraceIndex(events)
        promotion = events[-1]

        explanation = index.explain(promotion.id)

        self.assertIsNotNone(explanation)
        self.assertEqual(
            explanation.lineage_event_types,
            [
                "goal_created",
                "plan_created",
                "tool_called",
                "tool_succeeded",
                "task_completed",
                "reflection_created",
                "lesson_candidate_created",
                "memory_promoted",
            ],
        )
        self.assertIn("approval boundary", explanation.why)
        self.assertIn("operator_confirmation_required=true", explanation.safety_note)

    def test_experience_trace_explains_failure_to_operator_correction(self) -> None:
        events = build_failure_correction_trace()
        index = ExperienceTraceIndex(events)
        correction = next(event for event in events if event.event_type == "user_corrected")

        explanation = index.explain(correction.id)
        output = format_experience_event_explanation(index, correction.id)

        self.assertEqual(
            explanation.lineage_event_types,
            ["goal_created", "plan_created", "tool_called", "tool_failed", "user_corrected"],
        )
        self.assertIn("exact event it corrects", explanation.why)
        self.assertIn("Source chain:", output)
        self.assertIn("tool_failed", output)

    def test_experience_trace_never_treats_tool_call_as_execution_proof(self) -> None:
        events = build_success_lifecycle_trace()
        index = ExperienceTraceIndex(events)
        tool_call = next(event for event in events if event.event_type == "tool_called")

        explanation = index.explain(tool_call.id)

        self.assertIn("not proof of execution", explanation.why)
        self.assertIn("execution_performed_by_builder=false", explanation.safety_note)

    def test_experience_trace_missing_and_entity_query_are_clean(self) -> None:
        index = ExperienceTraceIndex(build_success_lifecycle_trace())

        missing = format_experience_event_explanation(index, "evt_missing")
        matches = index.find_by_entity_id("memory_vocabulary")

        self.assertIn("Status: NOT_FOUND", missing)
        self.assertIn("No event matched", missing)
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].event_type, "memory_promoted")

    def test_experience_trace_explanations_are_detached_from_index_state(self) -> None:
        events = build_success_lifecycle_trace()
        index = ExperienceTraceIndex(events)
        promotion = events[-1]
        first = index.explain(promotion.id)

        first.payload["memory_id"] = "mutated_outside_index"
        second = index.explain(promotion.id)

        self.assertEqual(second.payload["memory_id"], "memory_vocabulary")
        self.assertEqual(events[-1].payload["memory_id"], "memory_vocabulary")

    def test_experience_trace_index_loads_verified_temporary_store_read_only(self) -> None:
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "experience.jsonl"
            store = TemporaryExperienceLedgerStore(path)
            success = build_success_lifecycle_trace()
            failure = build_failure_correction_trace()
            store.append_events(success, stored_at="2026-01-01T05:00:00Z")
            store.append_events(failure, stored_at="2026-01-01T05:01:00Z")
            before = path.read_bytes()

            index = ExperienceTraceIndex.from_temporary_store(store)
            report = index.doctor()

            self.assertEqual(path.read_bytes(), before)
        self.assertEqual(report.status, "OK")
        self.assertEqual(index.event_count, 15)

    def test_experience_trace_doctor_surfaces_broken_provenance_without_repair(self) -> None:
        broken = [event.to_dict() for event in build_success_lifecycle_trace()]
        broken[-1]["source_event_ids"] = ["evt_missing"]
        before = json.dumps(broken, sort_keys=True)
        index = ExperienceTraceIndex(broken)

        output = format_experience_explainability_doctor(index)

        self.assertEqual(json.dumps(broken, sort_keys=True), before)
        self.assertIn("Status: ERROR", output)
        self.assertIn("missing or later source event", output)
        self.assertIn("no repair", output.lower())

    def test_experience_explainability_benchmark_and_trace_map_are_read_only(self) -> None:
        report = run_experience_explainability_benchmark()
        benchmark_output = format_experience_explainability_benchmark(report)
        map_output = format_experience_trace_map(
            ExperienceTraceIndex(build_success_lifecycle_trace())
        )

        self.assertEqual(report.status, "OK")
        self.assertEqual(report.event_count, 15)
        self.assertEqual(report.promotion_lineage_depth, 8)
        self.assertEqual(report.correction_lineage_depth, 5)
        self.assertEqual(report.temporary_hash_verified, 15)
        self.assertTrue(all(report.checks.values()))
        self.assertIn("Status: OK", benchmark_output)
        self.assertIn("memory_promoted", map_output)
        self.assertIn("Read-only map", map_output)

    def test_experience_episode_projects_verified_success_lifecycle(self) -> None:
        events = build_success_lifecycle_trace()
        episode = ExperienceEpisodeProjector(events).project()[0]

        self.assertEqual(episode.status, "completed_verified")
        self.assertTrue(episode.verified)
        self.assertEqual(episode.goal["goal_id"], "goal_vocabulary")
        self.assertEqual(len(episode.actions), 1)
        self.assertEqual(len(episode.outcomes), 1)
        self.assertEqual(episode.task_result["task_id"], "task_vocabulary")
        self.assertEqual(
            episode.learning_state,
            "promotion_evidence_confirmation_required",
        )

    def test_experience_episode_preserves_failed_corrected_state(self) -> None:
        events = build_failure_correction_trace()
        episode = ExperienceEpisodeProjector(events).project()[0]

        self.assertEqual(episode.status, "failed_corrected")
        self.assertFalse(episode.verified)
        self.assertEqual(len(episode.corrections), 1)
        self.assertEqual(len(episode.reflections), 1)
        self.assertEqual(len(episode.lesson_candidates), 1)
        self.assertFalse(episode.memory_promotions)
        self.assertEqual(episode.learning_state, "lesson_candidate_pending")

    def test_experience_episode_keeps_learning_as_confirmation_bounded_evidence(self) -> None:
        episode = ExperienceEpisodeProjector(build_success_lifecycle_trace()).project()[0]
        promotion = episode.memory_promotions[0]
        lesson = episode.lesson_candidates[0]

        self.assertTrue(promotion["operator_confirmation_required"])
        self.assertFalse(promotion["promotion_performed_by_builder"])
        self.assertTrue(lesson["requires_operator_confirmation"])

    def test_experience_episode_preserves_exact_source_event_ids(self) -> None:
        events = build_success_lifecycle_trace()
        episode = ExperienceEpisodeProjector(events).project()[0]

        self.assertEqual(episode.source_event_ids, [event.id for event in events])

    def test_experience_episode_formats_compact_read_only_report_and_list(self) -> None:
        episodes = ExperienceEpisodeProjector(
            build_success_lifecycle_trace() + build_failure_correction_trace()
        ).project()

        detail = format_experience_episode(episodes[0])
        listing = format_experience_episode_list(episodes)

        self.assertIn("outcome_status: completed_verified", detail)
        self.assertIn("Memory promotion evidence:", detail)
        self.assertIn("Projection only", detail)
        self.assertIn("episodes: 2", listing)
        self.assertIn("failed_corrected", listing)
        self.assertIn("no episode is persisted", listing)

    def test_experience_episode_reads_temporary_store_without_mutation(self) -> None:
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "experience.jsonl"
            store = TemporaryExperienceLedgerStore(path)
            store.append_events(
                build_success_lifecycle_trace(),
                stored_at="2026-01-01T07:00:00Z",
            )
            before = path.read_bytes()

            projector = ExperienceEpisodeProjector.from_temporary_store(store)
            episodes = projector.project()

            self.assertEqual(path.read_bytes(), before)
        self.assertEqual(len(episodes), 1)
        self.assertEqual(episodes[0].status, "completed_verified")

    def test_experience_episode_refuses_broken_provenance_without_repair(self) -> None:
        broken = [event.to_dict() for event in build_success_lifecycle_trace()]
        broken[-1]["source_event_ids"] = ["evt_missing"]
        before = json.dumps(broken, sort_keys=True)
        projector = ExperienceEpisodeProjector(broken)

        with self.assertRaisesRegex(ExperienceEpisodeProjectionError, "failed validation"):
            projector.project()
        output = format_experience_episode_doctor(projector)

        self.assertEqual(json.dumps(broken, sort_keys=True), before)
        self.assertIn("Status: ERROR", output)
        self.assertIn("no repair", output.lower())

    def test_experience_episode_doctor_reports_valid_projection(self) -> None:
        projector = ExperienceEpisodeProjector(
            build_success_lifecycle_trace() + build_failure_correction_trace()
        )
        report = projector.doctor()
        output = format_experience_episode_doctor(projector)

        self.assertEqual(report.status, "OK")
        self.assertEqual(report.event_count, 15)
        self.assertEqual(report.episode_count, 2)
        self.assertEqual(report.verified_count, 1)
        self.assertEqual(report.corrected_count, 1)
        self.assertIn("Status: OK", output)
        self.assertIn("promotion retains confirmation boundaries", output)

    def test_experience_episode_benchmark_verifies_projection_and_hash_chain(self) -> None:
        report = run_experience_episode_benchmark()
        output = format_experience_episode_benchmark(report)

        self.assertEqual(report.status, "OK")
        self.assertEqual(report.event_count, 15)
        self.assertEqual(report.episode_count, 2)
        self.assertEqual(report.success_episode_status, "completed_verified")
        self.assertEqual(report.failure_episode_status, "failed_corrected")
        self.assertEqual(report.temporary_hash_verified, 15)
        self.assertTrue(all(report.checks.values()))
        self.assertIn("no LLM summarization", output)

    def test_experience_learning_marks_verified_success_eligible_for_review(self) -> None:
        episode = ExperienceEpisodeProjector(build_success_lifecycle_trace()).project()[0]
        candidate = ExperienceLearningReviewer([episode]).review()[0]

        self.assertEqual(candidate.status, "eligible_for_review")
        self.assertEqual(candidate.confidence, 0.9)
        self.assertTrue(candidate.operator_confirmation_required)
        self.assertFalse(candidate.auto_apply_allowed)
        self.assertEqual(len(candidate.promotion_evidence), 1)
        self.assertIn(
            candidate.evidence_event_ids[0],
            candidate.promotion_evidence[0]["evidence_event_ids"],
        )

    def test_experience_learning_keeps_corrected_failure_needing_evidence(self) -> None:
        episode = ExperienceEpisodeProjector(build_failure_correction_trace()).project()[0]
        candidate = ExperienceLearningReviewer([episode]).review()[0]

        self.assertEqual(candidate.status, "needs_more_evidence")
        self.assertFalse(episode.verified)
        self.assertIn("lacks verified successful outcome", candidate.reasons[0])

    def test_experience_learning_detects_exact_memory_duplicate(self) -> None:
        episode = ExperienceEpisodeProjector(build_success_lifecycle_trace()).project()[0]
        lesson = episode.lesson_candidates[0]["lesson_preview"]
        candidate = ExperienceLearningReviewer(
            [episode],
            active_memories=[{"id": "mem_existing", "content": f"  {lesson.upper()}  "}],
        ).review()[0]

        self.assertEqual(candidate.status, "duplicate")
        self.assertIn("memory:mem_existing:content", candidate.duplicate_matches)

    def test_experience_learning_detects_exact_skill_duplicate(self) -> None:
        episode = ExperienceEpisodeProjector(build_failure_correction_trace()).project()[0]
        lesson = episode.lesson_candidates[0]["lesson_preview"]
        candidate = ExperienceLearningReviewer(
            [episode],
            active_skills=[{"id": "skill_existing", "summary": lesson}],
        ).review()[0]

        self.assertEqual(candidate.status, "duplicate")
        self.assertIn("skill:skill_existing:summary", candidate.duplicate_matches)

    def test_experience_learning_detects_repeated_candidates_in_review(self) -> None:
        episodes = ExperienceEpisodeProjector(
            build_success_lifecycle_trace() + build_failure_correction_trace()
        ).project()
        episodes[1].lesson_candidates[0]["lesson_preview"] = episodes[0].lesson_candidates[0][
            "lesson_preview"
        ]

        candidates = ExperienceLearningReviewer(episodes).review()

        self.assertTrue(all(candidate.status == "duplicate" for candidate in candidates))
        self.assertTrue(
            all("another_learning_candidate" in candidate.duplicate_matches for candidate in candidates)
        )

    def test_experience_learning_blocks_missing_confirmation_without_input_mutation(self) -> None:
        episode = ExperienceEpisodeProjector(build_success_lifecycle_trace()).project()[0]
        episode.lesson_candidates[0]["requires_operator_confirmation"] = False
        before = json.dumps(episode.to_dict(), sort_keys=True)
        reviewer = ExperienceLearningReviewer([episode])

        candidate = reviewer.review()[0]
        output = format_experience_learning_doctor(reviewer)

        self.assertEqual(json.dumps(episode.to_dict(), sort_keys=True), before)
        self.assertEqual(candidate.status, "blocked")
        self.assertFalse(candidate.operator_confirmation_required)
        self.assertIn("Status: ERROR", output)
        self.assertIn("confirmation boundary is missing", output)

    def test_experience_learning_doctor_rejects_unlinked_promotion_evidence(self) -> None:
        episode = ExperienceEpisodeProjector(build_success_lifecycle_trace()).project()[0]
        episode.memory_promotions[0]["evidence_event_ids"] = [episode.source_event_ids[0]]
        reviewer = ExperienceLearningReviewer([episode])

        report = reviewer.doctor()

        self.assertEqual(report.status, "ERROR")
        self.assertTrue(any("not linked to a lesson event" in issue for issue in report.issues))

    def test_experience_learning_formatters_state_advisory_no_apply_boundary(self) -> None:
        episodes = ExperienceEpisodeProjector(
            build_success_lifecycle_trace() + build_failure_correction_trace()
        ).project()
        reviewer = ExperienceLearningReviewer(episodes)
        candidate_output = format_experience_learning_candidate(reviewer.review()[0])
        review_output = format_experience_learning_review(reviewer)

        self.assertIn("auto_apply_allowed: false", candidate_output)
        self.assertIn("no memory, skill", candidate_output)
        self.assertIn("eligible_for_review: 1", review_output)
        self.assertIn("needs_more_evidence: 1", review_output)
        self.assertIn("No automatic apply", review_output)

    def test_experience_learning_reads_temporary_evidence_without_mutation(self) -> None:
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "experience.jsonl"
            store = TemporaryExperienceLedgerStore(path)
            store.append_events(
                build_success_lifecycle_trace(),
                stored_at="2026-01-01T09:00:00Z",
            )
            before = path.read_bytes()

            episodes = ExperienceEpisodeProjector.from_temporary_store(store).project()
            candidates = ExperienceLearningReviewer(episodes).review()

            self.assertEqual(path.read_bytes(), before)
        self.assertEqual(candidates[0].status, "eligible_for_review")

    def test_experience_learning_benchmark_verifies_boundaries_and_hash_chain(self) -> None:
        report = run_experience_learning_benchmark()
        output = format_experience_learning_benchmark(report)

        self.assertEqual(report.status, "OK")
        self.assertEqual(report.event_count, 15)
        self.assertEqual(report.episode_count, 2)
        self.assertEqual(report.candidate_count, 2)
        self.assertEqual(report.eligible_count, 1)
        self.assertEqual(report.needs_evidence_count, 1)
        self.assertEqual(report.temporary_hash_verified, 15)
        self.assertTrue(all(report.checks.values()))
        self.assertIn("no LLM", output)
        self.assertIn("automatic apply", output)

    def test_experience_learning_input_selects_only_explicit_active_ids(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = MemoryStore(root / "working.json", root / "persistent.json")
            store.save_working_memory(
                [MemoryRecord("Selected lesson", "lesson", 0.9, "operator", id="mem_selected")]
            )
            store.save_persistent_memory(
                [MemoryRecord("Not selected", "lesson", 0.8, "operator", id="mem_other")]
            )
            skills_path = root / "skills.jsonl"
            skills_path.write_text(
                json.dumps({"id": "skill_selected", "name": "Selected", "status": "active"})
                + "\n"
                + json.dumps({"id": "skill_other", "name": "Other", "status": "active"})
                + "\n",
                encoding="utf-8",
            )
            adapter = ExperienceLearningInputAdapter(
                memory_store=store,
                skill_library=SkillLibrary(skills_path),
            )

            snapshot = adapter.build_snapshot(
                memory_ids=["mem_selected"],
                skill_ids=["skill_selected"],
            )

        self.assertEqual(snapshot.status, "OK")
        self.assertEqual(snapshot.selection_mode, LEARNING_INPUT_SELECTION_MODE)
        self.assertEqual([item["id"] for item in snapshot.memory_records], ["mem_selected"])
        self.assertEqual([item["id"] for item in snapshot.skill_records], ["skill_selected"])
        self.assertFalse(snapshot.retrieval_performed)

    def test_experience_learning_input_excludes_inactive_and_archived_records(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = MemoryStore(root / "working.json", root / "persistent.json")
            store.save_working_memory(
                [
                    MemoryRecord(
                        "Inactive",
                        "lesson",
                        0.8,
                        "operator",
                        id="mem_inactive",
                        active=False,
                    )
                ]
            )
            skills_path = root / "skills.jsonl"
            skills_path.write_text(
                json.dumps({"id": "skill_archived", "name": "Old", "status": "archived"})
                + "\n",
                encoding="utf-8",
            )
            adapter = ExperienceLearningInputAdapter(
                memory_store=store,
                skill_library=SkillLibrary(skills_path),
            )

            snapshot = adapter.build_snapshot(
                memory_ids=["mem_inactive"],
                skill_ids=["skill_archived"],
            )

        self.assertEqual(snapshot.status, "WARN")
        self.assertFalse(snapshot.memory_records)
        self.assertFalse(snapshot.skill_records)
        self.assertEqual(snapshot.excluded_memory_ids, ["mem_inactive"])
        self.assertEqual(snapshot.excluded_skill_ids, ["skill_archived"])

    def test_experience_learning_input_reports_missing_and_repeated_ids(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = MemoryStore(root / "working.json", root / "persistent.json")
            adapter = ExperienceLearningInputAdapter(
                memory_store=store,
                skill_library=SkillLibrary(root / "skills.jsonl"),
            )

            snapshot = adapter.build_snapshot(
                memory_ids=["mem_missing", "mem_missing"],
                skill_ids=["skill_missing", "skill_missing"],
            )
            report = adapter.doctor(snapshot)

        self.assertEqual(snapshot.requested_memory_ids, ["mem_missing"])
        self.assertEqual(snapshot.requested_skill_ids, ["skill_missing"])
        self.assertEqual(report.status, "WARN")
        self.assertEqual(report.missing_count, 2)
        self.assertTrue(any("deduplicated" in warning for warning in report.warnings))

    def test_experience_learning_input_fails_closed_on_ambiguous_memory_id(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = MemoryStore(root / "working.json", root / "persistent.json")
            duplicate = MemoryRecord("Duplicate", "lesson", 0.8, "operator", id="mem_same")
            store.save_working_memory([duplicate])
            store.save_persistent_memory([duplicate])
            adapter = ExperienceLearningInputAdapter(
                memory_store=store,
                skill_library=SkillLibrary(root / "skills.jsonl"),
            )
            snapshot = adapter.build_snapshot(memory_ids=["mem_same"])
            episodes = ExperienceEpisodeProjector(build_success_lifecycle_trace()).project()

            with self.assertRaisesRegex(ExperienceLearningInputError, "ambiguous"):
                adapter.build_reviewer(episodes, snapshot)

        self.assertEqual(snapshot.status, "ERROR")
        self.assertFalse(snapshot.memory_records)

    def test_experience_learning_input_fails_closed_on_malformed_skill_store(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = MemoryStore(root / "working.json", root / "persistent.json")
            skills_path = root / "skills.jsonl"
            skills_path.write_text("{bad json}\n", encoding="utf-8")
            adapter = ExperienceLearningInputAdapter(
                memory_store=store,
                skill_library=SkillLibrary(skills_path),
            )

            snapshot = adapter.build_snapshot(skill_ids=["skill_any"])
            output = format_experience_learning_input_doctor(adapter, snapshot)

        self.assertEqual(snapshot.status, "ERROR")
        self.assertIn("malformed records", output)

    def test_experience_learning_input_only_selected_duplicates_affect_reviewer(self) -> None:
        episode = ExperienceEpisodeProjector(build_success_lifecycle_trace()).project()[0]
        lesson = episode.lesson_candidates[0]["lesson_preview"]
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = MemoryStore(root / "working.json", root / "persistent.json")
            store.save_working_memory(
                [
                    MemoryRecord(lesson, "lesson", 0.9, "operator", id="mem_duplicate"),
                    MemoryRecord("Unrelated selected", "lesson", 0.8, "operator", id="mem_other"),
                ]
            )
            adapter = ExperienceLearningInputAdapter(
                memory_store=store,
                skill_library=SkillLibrary(root / "skills.jsonl"),
            )

            unrelated = adapter.build_snapshot(memory_ids=["mem_other"])
            duplicate = adapter.build_snapshot(memory_ids=["mem_duplicate"])
            unrelated_result = adapter.build_reviewer([episode], unrelated).review()[0]
            duplicate_result = adapter.build_reviewer([episode], duplicate).review()[0]

        self.assertEqual(unrelated_result.status, "eligible_for_review")
        self.assertEqual(duplicate_result.status, "duplicate")

    def test_experience_learning_input_does_not_touch_usage_or_source_files(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = MemoryStore(root / "working.json", root / "persistent.json")
            store.save_working_memory(
                [
                    MemoryRecord(
                        "Usage stable",
                        "lesson",
                        0.8,
                        "operator",
                        id="mem_usage",
                        usage_count=11,
                        last_used="2026-01-01T00:00:00Z",
                    )
                ]
            )
            skills_path = root / "skills.jsonl"
            skills_path.write_text("", encoding="utf-8")
            paths = [store.working_path, store.persistent_path, skills_path]
            before = {str(path): path.read_bytes() for path in paths}
            adapter = ExperienceLearningInputAdapter(
                memory_store=store,
                skill_library=SkillLibrary(skills_path),
            )

            snapshot = adapter.build_snapshot(memory_ids=["mem_usage"])
            after = {str(path): path.read_bytes() for path in paths}

        self.assertEqual(before, after)
        self.assertEqual(snapshot.memory_records[0]["usage_count"], 11)
        self.assertEqual(snapshot.memory_records[0]["last_used"], "2026-01-01T00:00:00Z")
        self.assertFalse(snapshot.usage_telemetry_recorded)
        self.assertFalse(snapshot.mutation_performed)

    def test_experience_learning_input_formatter_uses_compact_previews(self) -> None:
        long_content = "sensitive-looking-test-content " * 20
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = MemoryStore(root / "working.json", root / "persistent.json")
            store.save_working_memory(
                [MemoryRecord(long_content, "lesson", 0.8, "operator", id="mem_long")]
            )
            adapter = ExperienceLearningInputAdapter(
                memory_store=store,
                skill_library=SkillLibrary(root / "skills.jsonl"),
            )
            snapshot = adapter.build_snapshot(memory_ids=["mem_long"])

            output = format_experience_learning_input_snapshot(snapshot)

        self.assertNotIn(long_content, output)
        self.assertIn("...", output)
        self.assertIn("retrieval_performed: false", output)
        self.assertIn("mutation_performed: false", output)

    def test_experience_learning_input_benchmark_preserves_files_and_telemetry(self) -> None:
        report = run_experience_learning_input_benchmark()
        output = format_experience_learning_input_benchmark(report)

        self.assertEqual(report.status, "OK")
        self.assertEqual(report.selected_memory_count, 1)
        self.assertEqual(report.selected_skill_count, 1)
        self.assertEqual(report.reviewer_duplicate_count, 2)
        self.assertTrue(report.files_unchanged)
        self.assertTrue(all(report.checks.values()))
        self.assertIn("usage_telemetry_not_recorded", output)
        self.assertIn("no relevance search", output)

    def test_experience_pilot_status_and_preview_create_no_files(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            owner = SimpleNamespace()
            before = list(root.rglob("*"))

            status = format_experience_pilot_command(
                "/experience status", owner=owner, project_root=root
            )
            preview = format_experience_pilot_command(
                "/experience preview", owner=owner, project_root=root
            )
            pilot = peek_experience_pilot(owner)
            after = list(root.rglob("*"))

        self.assertIsNotNone(pilot)
        self.assertEqual(pilot.state, "previewed")
        self.assertIn("Status: INACTIVE", status)
        self.assertIn("READY_FOR_CONSENT", preview)
        self.assertIn(pilot.expected_consent_phrase, preview)
        self.assertEqual(before, after)

    def test_experience_pilot_requires_exact_previewed_session_consent(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            pilot = SupervisedExperiencePilot(root, session_id="pilot-consent")

            premature = pilot.consent(pilot.expected_consent_phrase)
            pilot.preview()
            wrong = pilot.consent("yes")
            accepted = pilot.consent(pilot.expected_consent_phrase)

        self.assertIn("preview_required_before_consent", premature)
        self.assertIn("broad_or_implicit_consent_refused", wrong)
        self.assertIn("Status: CONSENTED", accepted)
        self.assertEqual(pilot.state, "consented")

    def test_experience_pilot_captures_redacted_typed_events_in_process_memory(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            pilot_root = root / "pilot-root"
            pilot = SupervisedExperiencePilot(pilot_root, session_id="pilot-redaction")
            coordinator, _, _ = build_test_system(root / "cognitive")
            pilot.preview()
            pilot.consent(pilot.expected_consent_phrase)
            secret = "pilot-super-secret-value"
            user_input = f"Explain safe credential handling. password={secret}"
            result = coordinator.handle(user_input)

            observation = pilot.observe_normal_turn(user_input, result)
            events = pilot.snapshot()
            serialized = json.dumps(events, ensure_ascii=False)

        self.assertTrue(observation.capture_performed)
        self.assertEqual(observation.captured_turn, 1)
        self.assertEqual(observation.captured_event_count, 7)
        self.assertEqual(len(events), 7)
        self.assertNotIn(secret, serialized)
        self.assertIn(REDACTION_PREFIX, serialized)
        self.assertFalse(pilot_root.exists())

    def test_experience_pilot_fails_closed_without_partial_batch_on_bound_overflow(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            pilot = SupervisedExperiencePilot(root, session_id="pilot-bound", max_events=6)
            coordinator, _, _ = build_test_system(root / "cognitive")
            pilot.preview()
            pilot.consent(pilot.expected_consent_phrase)
            result = coordinator.handle("Explain a bounded pilot turn.")

            observation = pilot.observe_normal_turn("Explain a bounded pilot turn.", result)

        self.assertFalse(observation.capture_performed)
        self.assertIn("total_event_limit_fail_closed", observation.reason)
        self.assertEqual(pilot.state, "stopped")
        self.assertEqual(pilot.event_count, 0)

    def test_experience_pilot_fails_closed_when_context_injection_is_applied(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            pilot = SupervisedExperiencePilot(root, session_id="pilot-context")
            coordinator, _, _ = build_test_system(root / "cognitive")
            pilot.preview()
            pilot.consent(pilot.expected_consent_phrase)
            result = coordinator.handle("Explain the current focus.")

            observation = pilot.observe_normal_turn(
                "Explain the current focus.",
                result,
                context_injection_applied=True,
            )

        self.assertFalse(observation.capture_performed)
        self.assertEqual(observation.reason, "context_injection_active_fail_closed")
        self.assertEqual(pilot.state, "stopped")
        self.assertEqual(pilot.event_count, 0)

    def test_experience_pilot_stop_is_terminal_for_process_session(self) -> None:
        with TemporaryDirectory() as temp_dir:
            pilot = SupervisedExperiencePilot(Path(temp_dir), session_id="pilot-stop")
            pilot.preview()
            pilot.consent(pilot.expected_consent_phrase)

            stopped = pilot.stop()
            refused = pilot.consent(pilot.expected_consent_phrase)

        self.assertIn("Status: STOPPED", stopped)
        self.assertIn("terminal_state_requires_restart", refused)
        self.assertEqual(pilot.state, "stopped")

    def test_experience_pilot_events_inspect_and_doctor_are_process_memory_only(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            owner = SimpleNamespace()
            coordinator, _, _ = build_test_system(root / "cognitive")
            pilot = get_experience_pilot(owner, project_root=root)
            pilot.preview()
            pilot.consent(pilot.expected_consent_phrase)
            result = coordinator.handle("Explain the current architecture briefly.")
            pilot.observe_normal_turn("Explain the current architecture briefly.", result)
            event_id = pilot.snapshot()[0]["id"]

            events = format_experience_pilot_command(
                "/experience events --last 1", owner=owner, project_root=root
            )
            inspect = format_experience_pilot_command(
                f"/experience inspect {event_id}", owner=owner, project_root=root
            )
            doctor = format_experience_pilot_command(
                "/experience doctor", owner=owner, project_root=root
            )

        self.assertIn("showing: 1/7", events)
        self.assertIn(event_id, inspect)
        self.assertIn("conversation_observed", inspect)
        self.assertIn("Status: OK", doctor)
        self.assertIn("process_memory_only: true", doctor)
        self.assertIn("live_persistence_enabled: false", doctor)

    def test_experience_pilot_shared_handler_bypasses_slash_and_natural_routes(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            coordinator, _, _ = build_test_system(root / "cognitive")
            logger = SessionOperatorLogger(root / "session.jsonl", enabled=False)
            process_interactive_input(
                "/experience preview",
                coordinator=coordinator,
                session_logger=logger,
                project_root=root,
            )
            pilot = peek_experience_pilot(coordinator)
            process_interactive_input(
                f"/experience consent {pilot.expected_consent_phrase}",
                coordinator=coordinator,
                session_logger=logger,
                project_root=root,
            )

            slash_output = process_interactive_input(
                "/memory status",
                coordinator=coordinator,
                session_logger=logger,
                project_root=root,
            )
            natural_output = process_interactive_input(
                "что делать дальше",
                coordinator=coordinator,
                session_logger=logger,
                project_root=root,
            )
            unknown_slash_output = process_interactive_input(
                "/unknown-pilot-probe",
                coordinator=coordinator,
                session_logger=logger,
                project_root=root,
            )

        self.assertIn("Memory v2.0 status", slash_output)
        self.assertIn("Natural command matched", natural_output)
        self.assertNotIn("Experience pilot: captured", unknown_slash_output)
        self.assertEqual(pilot.event_count, 0)
        self.assertEqual(pilot.state, "consented")

    def test_experience_pilot_shared_handler_captures_only_normal_turn_after_consent(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            coordinator, _, _ = build_test_system(root / "cognitive")
            logger = SessionOperatorLogger(root / "session.jsonl", enabled=False)
            preview = process_interactive_input(
                "/experience preview",
                coordinator=coordinator,
                session_logger=logger,
                project_root=root,
            )
            pilot = peek_experience_pilot(coordinator)
            consent = process_interactive_input(
                f"/experience consent {pilot.expected_consent_phrase}",
                coordinator=coordinator,
                session_logger=logger,
                project_root=root,
            )

            normal = process_interactive_input(
                "Explain Proto-Mind continuity in one sentence.",
                coordinator=coordinator,
                session_logger=logger,
                project_root=root,
            )
            events = process_interactive_input(
                "/experience events --last 2",
                coordinator=coordinator,
                session_logger=logger,
                project_root=root,
            )

        self.assertIn("Exact consent command", preview)
        self.assertIn("Status: CONSENTED", consent)
        self.assertIn("Experience pilot: captured turn 1", normal)
        self.assertIn("process-memory only", normal)
        self.assertIn("showing: 2/7", events)
        self.assertEqual(pilot.event_count, 7)

    def test_experience_pilot_registry_and_policy_keep_persistence_closed(self) -> None:
        registry = {spec.prefix: spec for spec in COMMAND_REGISTRY}
        expected = {
            "/experience status",
            "/experience preview",
            "/experience consent",
            "/experience stop",
            "/experience episodes",
            "/experience episode",
            "/experience events",
            "/experience inspect",
            "/experience doctor",
        }

        self.assertTrue(expected.issubset(registry))
        self.assertEqual(len(COMMAND_REGISTRY), 387)
        self.assertEqual(len({spec.category for spec in COMMAND_REGISTRY}), 41)
        self.assertEqual(classify_command("/experience events").policy_class, "auto_allowed")
        self.assertEqual(
            classify_command("/experience consent exact phrase").policy_class,
            "confirmation_required",
        )
        self.assertFalse(
            any(spec.prefix.startswith(PERSISTENT_EXPERIENCE_COMMAND_PREFIXES) for spec in COMMAND_REGISTRY)
        )
        self.assertEqual(command_registry_doctor()["status"], "OK")

    def test_experience_pilot_default_bounds_are_explicit_and_doctor_healthy(self) -> None:
        with TemporaryDirectory() as temp_dir:
            pilot = SupervisedExperiencePilot(Path(temp_dir), session_id="pilot-bounds")
            report = pilot.doctor()

        self.assertEqual(pilot.max_events, EXPERIENCE_PILOT_MAX_EVENTS)
        self.assertEqual(pilot.max_bytes, EXPERIENCE_PILOT_MAX_BYTES)
        self.assertEqual(report.status, "OK")
        self.assertTrue(report.process_memory_only)
        self.assertFalse(report.live_writer_installed)
        self.assertFalse(report.live_persistence_enabled)

    def test_experience_episode_commands_do_not_mutate_process_memory(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            owner = SimpleNamespace()
            coordinator, _, _ = build_test_system(root / "cognitive")
            pilot = get_experience_pilot(owner, project_root=root)
            pilot.preview()
            pilot.consent(pilot.expected_consent_phrase)
            user_input = "Explain the current architecture briefly."
            pilot.observe_normal_turn(user_input, coordinator.handle(user_input))
            before = json.dumps(pilot.snapshot(), sort_keys=True)

            listing = format_experience_pilot_command(
                "/experience episodes", owner=owner, project_root=root
            )
            detail = format_experience_pilot_command(
                "/experience episode latest", owner=owner, project_root=root
            )
            after = json.dumps(pilot.snapshot(), sort_keys=True)

        self.assertIn("Cognitive Turn Episodes", listing)
        self.assertIn("Cognitive Turn Episode", detail)
        self.assertEqual(before, after)
        self.assertEqual(pilot.event_count, 7)

    def test_experience_episode_command_works_through_shared_handler_without_capture(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            coordinator, _, _ = build_test_system(root / "cognitive")
            logger = SessionOperatorLogger(root / "session.jsonl", enabled=False)
            process_interactive_input(
                "/experience preview", coordinator=coordinator, session_logger=logger, project_root=root
            )
            pilot = peek_experience_pilot(coordinator)
            process_interactive_input(
                f"/experience consent {pilot.expected_consent_phrase}",
                coordinator=coordinator,
                session_logger=logger,
                project_root=root,
            )
            process_interactive_input(
                "Explain the current focus.",
                coordinator=coordinator,
                session_logger=logger,
                project_root=root,
            )

            output = process_interactive_input(
                "/experience episode",
                coordinator=coordinator,
                session_logger=logger,
                project_root=root,
            )

        self.assertIn("Status: COMPLETE", output)
        self.assertIn("turn_id: 1", output)
        self.assertEqual(pilot.event_count, 7)
