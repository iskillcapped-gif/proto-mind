"""Core flow checks: memory contracts."""
from __future__ import annotations

import unittest
from proto_mind.tests.flow_fixtures import (
    ACTIVE_READONLY_ALLOWLIST,
    COGNITIVE_BENCHMARK_CASES,
    COGNITIVE_RESPONSE_BENCHMARK_CASES,
    COMMAND_REGISTRY,
    Coordinator,
    ExperienceLedgerError,
    LESSON_RECALL_BENCHMARK_VERSION,
    LIVE_EXPERIENCE_LEDGER_PATH,
    LOCAL_CAPABILITY_CONTRACTS,
    LegacyWarningInspector,
    MemoryKeeper,
    MemoryRecord,
    MemoryStore,
    Observer,
    OperatorReviewedProceduralSkillOutcomeCaptureSession,
    PROCEDURAL_SKILL_RESTORE_CAPTURE_FUTURE_RECEIPT_FIELDS,
    PROCEDURAL_SKILL_RESTORE_CAPTURE_READINESS_MODE,
    PROCEDURAL_SKILL_RESTORE_REEVALUATION_MODE,
    PROCEDURAL_SKILL_RESTORE_REEVALUATION_REQUIRED_CALL_FIELDS,
    Path,
    ProceduralSkillOutcomeCaptureBuilder,
    ProceduralSkillOutcomeCaptureError,
    ProceduralSkillOutcomeDecisionBuilder,
    ProceduralSkillOutcomeDecisionError,
    ProceduralSkillRestoreCaptureReadiness,
    ProceduralSkillRestoreCaptureReadinessError,
    ProceduralSkillRestoreReevaluationReviewer,
    ReflectionJournal,
    ScriptedReasoner,
    SessionOperatorLogger,
    TemporaryDirectory,
    TemporaryExperienceLedgerStore,
    _accepted_warning_fixture,
    _create_healthy_export_dirs,
    _warning_fixture,
    _write_milestone_fixture,
    action_policy_doctor,
    build_local_capability_result,
    build_procedural_skill_restore_receipt_evidence,
    build_test_applied_procedural_skill,
    build_test_experience_events,
    build_test_restored_procedural_skill,
    build_test_restored_skill_outcome_events,
    build_test_system,
    command_registry_doctor,
    format_backup_command,
    format_benchmark_report,
    format_context_command,
    format_experience_store_doctor,
    format_memory_command,
    format_procedural_skill_restore_capture_readiness_command,
    format_procedural_skill_restore_reevaluation_command,
    format_reflection_command,
    format_verified_lesson_recall_benchmark,
    format_warning_command,
    get_local_capability_contract,
    json,
    local_capability_contract_doctor,
    patch,
    process_interactive_input,
    reflect_for_test,
    replace,
    run_benchmark,
    run_continuity_soak,
    run_verified_lesson_recall_benchmark,
    verify_procedural_skill_restore_capture_blueprint,
)


class MemoryContractsTests(unittest.TestCase):
    def test_observer_classification(self) -> None:
        observer = Observer()
        state = observer.analyze("As we discussed earlier, what did we decide about Proto-Mind memory?")
        self.assertEqual(state.query_type, "continuity_followup")
        self.assertTrue(state.needs_memory)
        self.assertIn("memory", state.topic_tags)

    def test_observer_detects_memory_inventory_queries(self) -> None:
        observer = Observer()
        state = observer.analyze("What preferences and decisions do you currently remember separately?")
        self.assertEqual(state.query_type, "memory_inventory")
        self.assertTrue(state.needs_memory)

    def test_observer_detects_override_decision_queries(self) -> None:
        observer = Observer()
        state = observer.analyze("Actually, we are changing direction: Proto-Mind should use SQLite instead of JSON")
        self.assertEqual(state.query_type, "decision_request")
        self.assertFalse(state.needs_memory)

    def test_observer_retrieves_current_direction_questions(self) -> None:
        observer = Observer()
        for query in (
            "Is JSON still the current architectural direction?",
            "What is the difference between current implementation and current direction?",
            "What did we change our mind about regarding memory storage?",
        ):
            state = observer.analyze(query)
            self.assertTrue(state.needs_memory, msg=query)
            self.assertIn(state.query_type, {"memory_inventory", "meta_architecture"}, msg=query)

    def test_bilingual_cognitive_benchmark_passes_all_local_cases(self) -> None:
        report = run_benchmark()
        output = format_benchmark_report()

        self.assertEqual(report["status"], "OK")
        expected_count = len(COGNITIVE_BENCHMARK_CASES) + len(COGNITIVE_RESPONSE_BENCHMARK_CASES)
        self.assertEqual(report["case_count"], expected_count)
        self.assertEqual(report["passed_count"], expected_count)
        self.assertEqual(report["failed_count"], 0)
        self.assertIn("Status: OK", output)
        self.assertIn("No LLM/API call", output)

    def test_temporary_experience_store_appends_atomic_hash_chain(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            path = root / "preview" / "experience_ledger.jsonl"
            store = TemporaryExperienceLedgerStore(path)
            events = build_test_experience_events(root / "turn-one")

            receipt = store.append_events(events, stored_at="2026-01-01T01:00:00Z")
            report = store.doctor()
            entries = store.read_entries()

            self.assertTrue(path.exists())
            self.assertEqual(receipt.appended_count, len(events))
            self.assertEqual(receipt.total_count, len(events))
            self.assertEqual(report.status, "OK")
            self.assertEqual(report.hash_verified_count, len(events))
            self.assertEqual(entries[0]["previous_hash"], "GENESIS")
            self.assertEqual(entries[-1]["entry_hash"], receipt.last_entry_hash)
            self.assertEqual(list(path.parent.glob("*.tmp")), [])

    def test_temporary_experience_store_supports_second_valid_batch(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = TemporaryExperienceLedgerStore(root / "experience_ledger.jsonl")
            first = build_test_experience_events(root / "turn-one", turn_id=1, trace_id="first")
            second = build_test_experience_events(root / "turn-two", turn_id=2, trace_id="second")

            first_receipt = store.append_events(first, stored_at="2026-01-01T01:00:00Z")
            second_receipt = store.append_events(second, stored_at="2026-01-01T01:01:00Z")
            report = store.doctor()

        self.assertEqual(second_receipt.first_sequence, first_receipt.total_count + 1)
        self.assertEqual(second_receipt.total_count, len(first) + len(second))
        self.assertEqual(report.status, "OK")

    def test_temporary_experience_store_refuses_duplicate_without_mutation(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            path = root / "experience_ledger.jsonl"
            store = TemporaryExperienceLedgerStore(path)
            events = build_test_experience_events(root / "turn")
            store.append_events(events, stored_at="2026-01-01T01:00:00Z")
            before = path.read_bytes()

            with self.assertRaisesRegex(ExperienceLedgerError, "Duplicate experience event ids"):
                store.append_events(events, stored_at="2026-01-01T01:01:00Z")

            self.assertEqual(path.read_bytes(), before)

    def test_temporary_experience_store_detects_tampered_hash_and_refuses_append(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            path = root / "experience_ledger.jsonl"
            store = TemporaryExperienceLedgerStore(path)
            events = build_test_experience_events(root / "turn-one", trace_id="first")
            store.append_events(events, stored_at="2026-01-01T01:00:00Z")
            lines = path.read_text(encoding="utf-8").splitlines()
            first_entry = json.loads(lines[0])
            first_entry["event"]["payload"]["input_preview"] = "tampered"
            lines[0] = json.dumps(first_entry, ensure_ascii=False, sort_keys=True)
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            before = path.read_bytes()
            second = build_test_experience_events(root / "turn-two", turn_id=2, trace_id="second")

            report = store.doctor()
            with self.assertRaisesRegex(ExperienceLedgerError, "not healthy"):
                store.append_events(second, stored_at="2026-01-01T01:01:00Z")

            self.assertEqual(report.status, "ERROR")
            self.assertTrue(any("entry_hash mismatch" in issue for issue in report.issues))
            self.assertEqual(path.read_bytes(), before)

    def test_temporary_experience_store_refuses_malformed_existing_file(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            path = root / "experience_ledger.jsonl"
            path.write_text('{"broken":\n', encoding="utf-8")
            store = TemporaryExperienceLedgerStore(path)
            events = build_test_experience_events(root / "turn")
            before = path.read_bytes()

            report = store.doctor()
            with self.assertRaisesRegex(ExperienceLedgerError, "not healthy"):
                store.append_events(events, stored_at="2026-01-01T01:00:00Z")

            self.assertEqual(report.status, "ERROR")
            self.assertTrue(any("Malformed JSONL" in issue for issue in report.issues))
            self.assertEqual(path.read_bytes(), before)

    def test_temporary_experience_store_refuses_forbidden_payload_before_write(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            path = root / "experience_ledger.jsonl"
            store = TemporaryExperienceLedgerStore(path)
            events = [event.to_dict() for event in build_test_experience_events(root / "turn")]
            events[0]["payload"]["system_prompt"] = "must never persist"

            with self.assertRaisesRegex(ExperienceLedgerError, "failed validation"):
                store.append_events(events, stored_at="2026-01-01T01:00:00Z")

            self.assertFalse(path.exists())

    def test_temporary_experience_store_refuses_live_data_path(self) -> None:
        existed_before = LIVE_EXPERIENCE_LEDGER_PATH.exists()
        with TemporaryDirectory() as temp_dir:
            events = build_test_experience_events(Path(temp_dir) / "turn")

            with self.assertRaisesRegex(ExperienceLedgerError, "Live Experience Ledger persistence"):
                TemporaryExperienceLedgerStore(LIVE_EXPERIENCE_LEDGER_PATH).append_events(events)

        self.assertEqual(LIVE_EXPERIENCE_LEDGER_PATH.exists(), existed_before)

    def test_temporary_experience_store_missing_doctor_is_read_only_warn(self) -> None:
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "missing" / "experience_ledger.jsonl"
            store = TemporaryExperienceLedgerStore(path)

            output = format_experience_store_doctor(store)

            self.assertFalse(path.exists())
        self.assertIn("Status: WARN", output)
        self.assertIn("does not exist", output)
        self.assertIn("Doctor is read-only", output)

    def test_continuity_soak_verifies_full_temporary_experience_hash_chain(self) -> None:
        report = run_continuity_soak(persist_experience_preview=True)

        self.assertEqual(report["status"], "OK")
        self.assertTrue(report["experience_persistence_preview"])
        self.assertEqual(report["experience_events"], 180)
        self.assertEqual(report["experience_store_doctor_status"], "OK")
        self.assertEqual(report["experience_store_hash_verified"], 180)
        self.assertTrue(report["checks"]["experience_live_store_absent"])
        self.assertTrue(report["checks"]["experience_temporary_store_hash_chain"])

    def test_recall_imperatives_do_not_become_new_decisions(self) -> None:
        with TemporaryDirectory() as temp_dir:
            coordinator, store, _ = build_test_system(Path(temp_dir))
            coordinator.handle("Теперь используем SQLite вместо JSON для памяти Proto-Mind.")
            before = (store.working_path.read_bytes(), store.persistent_path.read_bytes())
            check = coordinator.handle("Проверь текущее решение о хранилище памяти.")
            restate = coordinator.handle("Повтори текущее решение о хранилище памяти.")
            after = (store.working_path.read_bytes(), store.persistent_path.read_bytes())

        self.assertEqual(check.observer_state.query_type, "memory_inventory")
        self.assertEqual(restate.observer_state.query_type, "memory_inventory")
        self.assertFalse(check.memory_summary.should_store)
        self.assertFalse(restate.memory_summary.should_store)
        self.assertEqual(before, after)

    def test_continuity_reference_does_not_force_historical_state_bias(self) -> None:
        with TemporaryDirectory() as temp_dir:
            coordinator, _, _ = build_test_system(Path(temp_dir))
            coordinator.handle("Мы решили использовать JSON для памяти Proto-Mind.")
            coordinator.handle("Теперь используем SQLite вместо JSON для памяти Proto-Mind.")
            coordinator.handle("Запомни, что текущая цель Proto-Mind — Cognitive Continuity.")
            result = coordinator.handle(
                "Как мы обсуждали раньше, что важно для проекта Proto-Mind?"
            )

        self.assertIsNotNone(result.retrieval_trace)
        self.assertFalse(result.retrieval_trace.historical_state_oriented)
        self.assertTrue(result.retrieved_memory)
        self.assertEqual(result.retrieved_memory[0].type, "insight")
        self.assertTrue(all(record.active for record in result.retrieved_memory))
        self.assertEqual(result.grounding_audit.grounding_status, "grounded")

    def test_observer_classifies_russian_cognitive_intents(self) -> None:
        observer = Observer()
        expectations = (
            ("Как мы обсуждали раньше, что мы решили по памяти?", "continuity_followup", True),
            ("Что ты помнишь обо мне?", "memory_inventory", True),
            ("Я предпочитаю короткие ответы.", "personal_context", False),
            ("Мы решили использовать SQLite для памяти.", "decision_request", False),
            ("На самом деле теперь используем SQLite вместо JSON.", "decision_request", False),
        )

        for text, expected_type, expected_memory in expectations:
            state = observer.analyze(text)
            self.assertEqual(state.query_type, expected_type, msg=text)
            self.assertEqual(state.needs_memory, expected_memory, msg=text)

    def test_retrieval_trace_shows_active_vs_historical_bias(self) -> None:
        with TemporaryDirectory() as temp_dir:
            tmp_path = Path(temp_dir)
            coordinator, _, _ = build_test_system(tmp_path)
            coordinator.handle("We decided Proto-Mind should use JSON-backed memory.")
            coordinator.handle("Actually, we are changing direction: Proto-Mind should use SQLite instead of JSON.")
            result = coordinator.handle("What storage system are we using now?")
            self.assertIsNotNone(result.retrieval_trace)
            self.assertTrue(result.retrieval_trace.current_state_oriented)
            selected = [candidate for candidate in result.retrieval_trace.candidates if candidate.selected]
            filtered_or_unselected = [candidate for candidate in result.retrieval_trace.candidates if not candidate.selected]
            self.assertTrue(selected)
            self.assertIn("sqlite", selected[0].content_preview.lower())
            self.assertTrue(any(candidate.state_bias_contribution < 0 for candidate in filtered_or_unselected if not candidate.active))
            self.assertIsNotNone(selected[0].why_selected_summary)
            self.assertIn("won because", selected[0].why_selected_summary.lower())

    def test_retrieval_trace_explains_historical_selection(self) -> None:
        with TemporaryDirectory() as temp_dir:
            tmp_path = Path(temp_dir)
            coordinator, _, _ = build_test_system(tmp_path)
            coordinator.handle("We decided Proto-Mind should use JSON-backed memory.")
            coordinator.handle("Actually, we are changing direction: Proto-Mind should use SQLite instead of JSON.")
            result = coordinator.handle("What did we use before SQLite?")
            self.assertIsNotNone(result.retrieval_trace)
            selected = [candidate for candidate in result.retrieval_trace.candidates if candidate.selected]
            self.assertTrue(selected)
            self.assertTrue(any("historical" in (candidate.why_selected_summary or "").lower() for candidate in selected))

    def test_self_reflection_warns_when_response_contradicts_active_decision(self) -> None:
        active_sqlite = MemoryRecord(
            "Actually, we are changing direction: Proto-Mind should use SQLite instead of JSON.",
            "decision",
            0.95,
            "promoted",
            tags=["sqlite", "storage"],
        )

        reflection = reflect_for_test(
            "We are currently using JSON-backed memory as the storage system.",
            persistent_memory=[active_sqlite],
        )

        self.assertEqual(reflection.active_decision_alignment, "warning")
        self.assertTrue(any("active SQLite decision" in warning for warning in reflection.warnings))

    def test_self_reflection_generates_correction_hint_for_active_decision_contradiction(self) -> None:
        active_sqlite = MemoryRecord(
            "Actually, we are changing direction: Proto-Mind should use SQLite instead of JSON.",
            "decision",
            0.95,
            "promoted",
            tags=["sqlite", "storage"],
        )

        reflection = reflect_for_test(
            "We are currently using JSON-backed memory as the storage system.",
            persistent_memory=[active_sqlite],
        )

        self.assertTrue(reflection.should_carry_forward)
        self.assertEqual(reflection.carry_forward_scope, "next_turn")
        self.assertTrue(reflection.correction_hints)
        self.assertIn("Use the active decision as current state", reflection.correction_hints[0])
        self.assertIn("SQLite", reflection.correction_hints[0])

    def test_self_reflection_does_not_treat_instead_of_json_as_current_json(self) -> None:
        active_sqlite = MemoryRecord(
            "Actually, we are changing direction: Proto-Mind should use SQLite instead of JSON.",
            "decision",
            0.95,
            "promoted",
            tags=["sqlite", "storage"],
        )

        reflection = reflect_for_test(
            "Current stored memory: Active decisions: Actually, we are changing direction: Proto-Mind should use SQLite instead of JSON.",
            retrieved_memory=[active_sqlite],
            persistent_memory=[active_sqlite],
        )

        self.assertEqual(reflection.active_decision_alignment, "ok")
        self.assertEqual(reflection.superseded_memory_risk, "low")
        self.assertFalse(reflection.warnings)

    def test_self_reflection_warns_when_superseded_memory_used_as_current(self) -> None:
        active_sqlite = MemoryRecord(
            "Actually, we are changing direction: Proto-Mind should use SQLite instead of JSON.",
            "decision",
            0.95,
            "promoted",
            tags=["sqlite", "storage"],
        )
        old_json = MemoryRecord(
            "We decided Proto-Mind should use JSON-backed memory.",
            "decision",
            0.8,
            "promoted",
            tags=["json", "storage"],
            active=False,
            superseded_by=active_sqlite.id,
        )

        reflection = reflect_for_test(
            "The current storage system is JSON-backed memory.",
            persistent_memory=[old_json, active_sqlite],
        )

        self.assertEqual(reflection.superseded_memory_risk, "high")
        self.assertTrue(any("superseded JSON decision" in warning for warning in reflection.warnings))

    def test_self_reflection_allows_previous_decisions_heading_for_json_history(self) -> None:
        active_sqlite = MemoryRecord(
            "Actually, we are changing direction: Proto-Mind should use SQLite instead of JSON.",
            "decision",
            0.95,
            "promoted",
            tags=["sqlite", "storage"],
        )
        old_json = MemoryRecord(
            "We decided Proto-Mind should use JSON-backed memory.",
            "decision",
            0.8,
            "promoted",
            tags=["json", "storage"],
            active=False,
            superseded_by=active_sqlite.id,
        )

        reflection = reflect_for_test(
            "Current stored memory: Previous decisions: We decided Proto-Mind should use JSON-backed memory.",
            retrieved_memory=[old_json, active_sqlite],
            persistent_memory=[old_json, active_sqlite],
        )

        self.assertEqual(reflection.active_decision_alignment, "ok")
        self.assertEqual(reflection.superseded_memory_risk, "low")
        self.assertFalse(reflection.warnings)

    def test_self_reflection_reports_ok_when_active_preference_respected(self) -> None:
        preference = MemoryRecord(
            "I prefer concise architectural explanations.",
            "preference",
            0.9,
            "promoted",
            tags=["preference", "concise", "architecture"],
        )

        reflection = reflect_for_test(
            "Proto-Mind should explain the architecture briefly and focus on the memory pipeline.",
            retrieved_memory=[preference],
            persistent_memory=[preference],
        )

        self.assertEqual(reflection.preference_alignment, "ok")
        self.assertFalse(reflection.warnings)

    def test_self_reflection_warns_when_selected_memory_appears_ignored(self) -> None:
        selected_memory = MemoryRecord(
            "Proto-Mind should use SQLite persistence.",
            "decision",
            0.9,
            "promoted",
            tags=["sqlite", "storage", "persistence"],
        )

        reflection = reflect_for_test(
            "The coordinator should orchestrate observer, memory keeper, and reasoner.",
            retrieved_memory=[selected_memory],
            persistent_memory=[selected_memory],
        )

        self.assertEqual(reflection.memory_alignment, "warning")
        self.assertTrue(any("ignored important selected memory" in warning for warning in reflection.warnings))

    def test_self_reflection_is_neutral_without_retrieved_memory(self) -> None:
        state = Observer().analyze("Hello there.")

        reflection = reflect_for_test(
            "Hello. How can I help with Proto-Mind today?",
            observer_state=state,
        )

        self.assertFalse(reflection.reflection_needed)
        self.assertEqual(reflection.memory_alignment, "neutral")
        self.assertEqual(reflection.preference_alignment, "neutral")
        self.assertEqual(reflection.active_decision_alignment, "neutral")
        self.assertEqual(reflection.superseded_memory_risk, "low")
        self.assertEqual(reflection.unsupported_claims_risk, "low")

    def test_self_reflection_detects_russian_active_decision_contradiction(self) -> None:
        active_sqlite = MemoryRecord(
            "Теперь используем SQLite вместо JSON для хранения памяти.",
            "decision",
            0.95,
            "operator",
            tags=["sqlite", "json", "storage"],
        )

        reflection = reflect_for_test(
            "Текущее архитектурное решение — JSON для хранения памяти.",
            retrieved_memory=[active_sqlite],
            persistent_memory=[active_sqlite],
        )

        self.assertEqual(reflection.active_decision_alignment, "warning")
        self.assertTrue(any("active SQLite decision" in warning for warning in reflection.warnings))

    def test_self_reflection_recognizes_russian_json_override_direction(self) -> None:
        active_json = MemoryRecord(
            "Теперь используем JSON вместо SQLite для хранения памяти.",
            "decision",
            0.95,
            "operator",
            tags=["json", "sqlite", "storage"],
        )

        reflection = reflect_for_test(
            "Текущее архитектурное решение — SQLite для хранения памяти.",
            retrieved_memory=[active_json],
            persistent_memory=[active_json],
        )

        self.assertEqual(reflection.active_decision_alignment, "warning")
        self.assertTrue(any("active JSON decision" in warning for warning in reflection.warnings))

    def test_self_reflection_enforces_russian_concise_preference(self) -> None:
        preference = MemoryRecord(
            "Я предпочитаю короткие ответы.",
            "preference",
            0.9,
            "operator",
            tags=["preference", "short", "response_style"],
        )

        reflection = reflect_for_test(
            "Я дам короткий ответ. " + "подробность " * 145,
            retrieved_memory=[preference],
            persistent_memory=[preference],
        )

        self.assertEqual(reflection.preference_alignment, "warning")
        self.assertTrue(any("concise or short answers" in warning for warning in reflection.warnings))

    def test_correction_hint_is_carried_to_next_turn_and_then_cleared(self) -> None:
        with TemporaryDirectory() as temp_dir:
            tmp_path = Path(temp_dir)
            data_dir = tmp_path / "data"
            store = MemoryStore(
                working_path=data_dir / "working_memory.json",
                persistent_path=data_dir / "persistent_memory.json",
            )
            active_sqlite = MemoryRecord(
                "Actually, we are changing direction: Proto-Mind should use SQLite instead of JSON.",
                "decision",
                0.95,
                "promoted",
                tags=["sqlite", "storage"],
            )
            store.save_persistent_memory([active_sqlite])
            keeper = MemoryKeeper(store)
            reasoner = ScriptedReasoner(
                [
                    "We are currently using JSON-backed memory as the storage system.",
                    "SQLite is current.",
                ]
            )
            coordinator = Coordinator(
                observer=Observer(),
                memory_keeper=keeper,
                reasoner=reasoner,
            )

            first = coordinator.handle("What storage system are we using now?")
            second = coordinator.handle("Please restate the current storage decision.")

            self.assertTrue(first.self_reflection)
            self.assertTrue(first.self_reflection.correction_hints)
            self.assertEqual(reasoner.seen_correction_hints[0], [])
            self.assertEqual(reasoner.seen_correction_hints[1], first.self_reflection.correction_hints)
            self.assertEqual(second.previous_correction_hints, first.self_reflection.correction_hints)
            self.assertEqual(coordinator.pending_correction_hints, [])

    def test_correction_hints_are_not_persisted_as_durable_memory(self) -> None:
        with TemporaryDirectory() as temp_dir:
            tmp_path = Path(temp_dir)
            data_dir = tmp_path / "data"
            store = MemoryStore(
                working_path=data_dir / "working_memory.json",
                persistent_path=data_dir / "persistent_memory.json",
            )
            active_sqlite = MemoryRecord(
                "Actually, we are changing direction: Proto-Mind should use SQLite instead of JSON.",
                "decision",
                0.95,
                "promoted",
                tags=["sqlite", "storage"],
            )
            store.save_persistent_memory([active_sqlite])
            coordinator = Coordinator(
                observer=Observer(),
                memory_keeper=MemoryKeeper(store),
                reasoner=ScriptedReasoner(["We are currently using JSON-backed memory as the storage system."]),
            )

            result = coordinator.handle("What storage system are we using now?")
            hint = result.self_reflection.correction_hints[0]
            all_records = store.load_working_memory() + store.load_persistent_memory()

            self.assertTrue(hint)
            self.assertFalse(any(hint in record.content for record in all_records))

    def test_explicit_memory_status_works_with_current_memory_shape(self) -> None:
        with TemporaryDirectory() as temp_dir:
            _, store, _ = build_test_system(Path(temp_dir))
            store.save_persistent_memory(
                [
                    MemoryRecord("Legacy decision", "decision", 0.8, "promoted"),
                    MemoryRecord("Explicit active", "explicit", 1.0, "operator", confidence=1.0, updated_at="2026-06-18T01:00:00+00:00"),
                    MemoryRecord("Explicit forgotten", "explicit", 1.0, "operator", active=False, confidence=1.0, updated_at="2026-06-18T02:00:00+00:00"),
                ]
            )

            output = format_memory_command("/memory status", store)

            self.assertIsNotNone(output)
            self.assertIn("Memory v2.0 status:", output)
            self.assertIn("explicit_active: 1", output)
            self.assertIn("explicit_forgotten: 1", output)
            self.assertIn("legacy_records: 1", output)

    def test_explicit_memory_remember_creates_operator_memory(self) -> None:
        with TemporaryDirectory() as temp_dir:
            _, store, _ = build_test_system(Path(temp_dir))

            output = format_memory_command("/memory remember User likes local-first systems.", store)
            records = store.load_persistent_memory()
            explicit = [record for record in records if record.type == "explicit"]

            self.assertIsNotNone(output)
            self.assertEqual(len(explicit), 1)
            record = explicit[0]
            self.assertRegex(record.id, r"^mem_\d{8}_\d{6}_[0-9a-f]{4}$")
            self.assertEqual(record.content, "User likes local-first systems.")
            self.assertEqual(record.source, "operator")
            self.assertEqual(record.confidence, 1.0)
            self.assertTrue(record.active)
            self.assertIsNotNone(record.timestamp)
            self.assertEqual(record.updated_at, record.timestamp)
            self.assertIn(record.id, output)

    def test_explicit_memory_list_inspect_search_and_forget_flow(self) -> None:
        with TemporaryDirectory() as temp_dir:
            _, store, _ = build_test_system(Path(temp_dir))
            remember_output = format_memory_command("/memory remember User likes local-first systems.", store)
            memory_id = next(line.strip().split(" — ")[0] for line in remember_output.splitlines() if line.strip().startswith("mem_"))

            list_output = format_memory_command("/memory list", store)
            inspect_output = format_memory_command(f"/memory inspect {memory_id}", store)
            search_output = format_memory_command("/memory search LOCAL-FIRST", store)
            forget_output = format_memory_command(f"/memory forget {memory_id}", store)
            list_after_forget = format_memory_command("/memory list", store)
            list_all = format_memory_command("/memory list --all", store)
            inspect_after_forget = format_memory_command(f"/memory inspect {memory_id}", store)
            forget_again = format_memory_command(f"/memory forget {memory_id}", store)

            self.assertIn(memory_id, list_output)
            self.assertIn("text: User likes local-first systems.", inspect_output)
            self.assertIn("confidence: 1.0", inspect_output)
            self.assertIn(memory_id, search_output)
            self.assertIn("Forgotten:", forget_output)
            self.assertNotIn(memory_id, list_after_forget)
            self.assertIn(memory_id, list_all)
            self.assertIn("status: forgotten", inspect_after_forget)
            self.assertIn("Already forgotten:", forget_again)

    def test_explicit_memory_unknown_and_empty_inputs_are_clean(self) -> None:
        with TemporaryDirectory() as temp_dir:
            _, store, _ = build_test_system(Path(temp_dir))
            before = store.persistent_path.read_bytes()

            empty_remember = format_memory_command("/memory remember   ", store)
            missing_inspect = format_memory_command("/memory inspect missing-id", store)
            missing_forget = format_memory_command("/memory forget missing-id", store)
            empty_search = format_memory_command("/memory search   ", store)

            self.assertEqual(empty_remember, "Usage: /memory remember <text>")
            self.assertEqual(store.persistent_path.read_bytes(), before)
            self.assertIn("Explicit memory not found: missing-id", missing_inspect)
            self.assertIn("Explicit memory not found: missing-id", missing_forget)
            self.assertEqual(empty_search, "Usage: /memory search <query> [--all]")

    def test_explicit_memory_commands_handle_corrupted_persistent_file_gracefully(self) -> None:
        with TemporaryDirectory() as temp_dir:
            _, store, _ = build_test_system(Path(temp_dir))
            store.persistent_path.write_text("{not json", encoding="utf-8")

            output = format_memory_command("/memory status", store)
            remember = format_memory_command("/memory remember Should not overwrite corruption.", store)

            self.assertIn("Memory control error: could not read persistent memory:", output)
            self.assertIn("Memory control error: could not read persistent memory:", remember)
            self.assertEqual(store.persistent_path.read_text(encoding="utf-8"), "{not json")

    def test_explicit_memory_commands_work_through_shared_input_handler_without_session_log_turn(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            logger = SessionOperatorLogger(root / "logs" / "session_operator_log.jsonl")
            coordinator, store, _keeper = build_test_system(root)
            coordinator.session_logger = logger

            output = process_interactive_input(
                "/memory remember User likes local-first systems.",
                coordinator=coordinator,
                session_logger=logger,
                project_root=root,
            )

            self.assertIn("Remembered:", output)
            self.assertEqual(logger.status().entry_count, 0)
            self.assertEqual(len([record for record in store.load_persistent_memory() if record.type == "explicit"]), 1)

    def test_explicit_memory_backup_command_still_works(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            package_dir = project_root / "proto_mind"
            data_dir = package_dir / "data"
            data_dir.mkdir(parents=True)
            (package_dir / "__init__.py").write_text("", encoding="utf-8")
            (data_dir / "working_memory.json").write_text("[]", encoding="utf-8")
            (data_dir / "persistent_memory.json").write_text("[]", encoding="utf-8")

            output = format_backup_command("/memory backup", project_root)

            self.assertIsNotNone(output)
            self.assertIn("Memory backup created:", output)

    def test_reflection_status_works_when_journal_missing(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            logger = SessionOperatorLogger.from_project_root(project_root)

            output = format_reflection_command("/reflection status", project_root=project_root, session_logger=logger)

            self.assertIsNotNone(output)
            self.assertIn("Reflection journal status:", output)
            self.assertIn("exists: False", output)
            self.assertIn("entries: 0", output)

    def test_reflection_now_creates_entry_and_list_inspect_work(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            logger = SessionOperatorLogger.from_project_root(project_root)
            logger.log_path.parent.mkdir(parents=True)
            logger.log_path.write_text(
                json.dumps(
                    {
                        "timestamp": "2026-06-21T07:00:00+00:00",
                        "turn_id": 1,
                        "user_input": "What happened recently?",
                        "reasoner_backend": "mock",
                        "observer": {"query_type": "project_context", "tags": ["project"]},
                        "self_reflection": {"warnings": [], "correction_hints": []},
                        "grounding_audit": {"grounding_status": "grounded", "warnings": []},
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            output = format_reflection_command("/reflection now", project_root=project_root, session_logger=logger)
            journal = ReflectionJournal.from_project_root(project_root)
            records, malformed = journal.read_records()
            reflection_id = records[0]["id"]
            list_output = format_reflection_command("/reflection list", project_root=project_root, session_logger=logger)
            inspect_output = format_reflection_command(
                f"/reflection inspect {reflection_id}",
                project_root=project_root,
                session_logger=logger,
            )

            self.assertIn("Reflection Journal", output)
            self.assertIn("Created: refl_", output)
            self.assertEqual(malformed, 0)
            self.assertEqual(len(records), 1)
            self.assertIn("summary", records[0])
            self.assertIn("findings", records[0])
            self.assertIn("recommendations", records[0])
            self.assertIn(reflection_id, list_output)
            self.assertIn("Reflection entry:", inspect_output)
            self.assertIn("entries_analyzed: 1", inspect_output)

    def test_reflection_now_last_limit_and_malformed_session_log(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            logger = SessionOperatorLogger.from_project_root(project_root)
            logger.log_path.parent.mkdir(parents=True)
            lines = []
            for index in range(1, 4):
                lines.append(
                    json.dumps(
                        {
                            "timestamp": f"2026-06-21T07:00:0{index}+00:00",
                            "turn_id": index,
                            "user_input": f"Prompt {index}",
                            "reasoner_backend": "mock",
                            "observer": {"query_type": "new_question"},
                            "self_reflection": {"warnings": [], "correction_hints": []},
                            "grounding_audit": {"grounding_status": "grounded", "warnings": []},
                        }
                    )
                )
            lines.append("{not json")
            logger.log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

            output = format_reflection_command("/reflection now --last 2", project_root=project_root, session_logger=logger)
            journal = ReflectionJournal.from_project_root(project_root)
            records, _ = journal.read_records()

            self.assertIn("Entries analyzed: 2", output)
            self.assertIn("Malformed session log entries detected: 1.", output)
            self.assertEqual(records[0]["entries_analyzed"], 2)
            self.assertEqual(records[0]["metadata"]["malformed_entries"], 1)

    def test_reflection_empty_session_log_creates_clean_reflection(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            logger = SessionOperatorLogger.from_project_root(project_root)
            logger.log_path.parent.mkdir(parents=True)
            logger.log_path.write_text("", encoding="utf-8")

            output = format_reflection_command("/reflection now", project_root=project_root, session_logger=logger)

            self.assertIn("Entries analyzed: 0", output)
            self.assertIn("No session log entries found", output)
            self.assertIn("Saved:", output)

    def test_reflection_journal_append_preserves_existing_entries(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            logger = SessionOperatorLogger.from_project_root(project_root)
            logger.log_path.parent.mkdir(parents=True)
            logger.log_path.write_text(
                json.dumps(
                    {
                        "timestamp": "2026-06-21T07:00:00+00:00",
                        "turn_id": 1,
                        "user_input": "Prompt",
                        "reasoner_backend": "mock",
                        "observer": {"query_type": "new_question"},
                        "self_reflection": {"warnings": [], "correction_hints": []},
                        "grounding_audit": {"grounding_status": "grounded", "warnings": []},
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            format_reflection_command("/reflection now", project_root=project_root, session_logger=logger)
            format_reflection_command("/reflection now", project_root=project_root, session_logger=logger)
            records, malformed = ReflectionJournal.from_project_root(project_root).read_records()

            self.assertEqual(malformed, 0)
            self.assertEqual(len(records), 2)
            self.assertNotEqual(records[0]["id"], records[1]["id"])

    def test_reflection_commands_do_not_mutate_persistent_memory(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            coordinator, store, _ = build_test_system(project_root)
            logger = SessionOperatorLogger.from_project_root(project_root)
            coordinator.session_logger = logger
            before = store.persistent_path.read_bytes()

            output = process_interactive_input(
                "/reflection now",
                coordinator=coordinator,
                session_logger=logger,
                project_root=project_root,
            )

            self.assertIn("Reflection Journal", output)
            self.assertEqual(store.persistent_path.read_bytes(), before)
            self.assertEqual(logger.status().entry_count, 0)

    def test_reflection_inspect_unknown_and_invalid_arguments_are_clean(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            logger = SessionOperatorLogger.from_project_root(project_root)

            missing = format_reflection_command("/reflection inspect missing", project_root=project_root, session_logger=logger)
            empty_inspect = format_reflection_command("/reflection inspect   ", project_root=project_root, session_logger=logger)
            invalid_last = format_reflection_command(
                "/reflection now --last nope",
                project_root=project_root,
                session_logger=logger,
            )
            zero_last = format_reflection_command("/reflection now --last 0", project_root=project_root, session_logger=logger)
            invalid_limit = format_reflection_command(
                "/reflection list --limit nope",
                project_root=project_root,
                session_logger=logger,
            )

            self.assertIn("Reflection entry not found: missing", missing)
            self.assertIn("Usage: /reflection inspect <id>", empty_inspect)
            self.assertIn("Invalid --last value", invalid_last)
            self.assertIn("--last must be greater than 0", zero_last)
            self.assertIn("Invalid --limit value", invalid_limit)

    def test_reflection_detects_warnings_memory_commands_and_recommendations(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            logger = SessionOperatorLogger.from_project_root(project_root)
            logger.log_path.parent.mkdir(parents=True)
            logger.log_path.write_text(
                json.dumps(
                    {
                        "timestamp": "2026-06-21T07:00:00+00:00",
                        "turn_id": 1,
                        "user_input": "/memory doctor",
                        "reasoner_backend": "mock",
                        "observer": {"query_type": "memory_inventory"},
                        "self_reflection": {
                            "warnings": ["Repeated preference warning"],
                            "correction_hints": ["Repeated preference warning"],
                        },
                        "grounding_audit": {
                            "grounding_status": "unsupported",
                            "warnings": ["Grounding warning"],
                        },
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            output = format_reflection_command("/reflection last", project_root=project_root, session_logger=logger)
            records, _ = ReflectionJournal.from_project_root(project_root).read_records()

            self.assertIn("Self-reflection warnings detected: 1.", output)
            self.assertIn("Correction hints detected: 1.", output)
            self.assertIn("Grounding issue signals detected", output)
            self.assertIn("Run /session doctor", output)
            self.assertIn("Run /memory doctor", output)
            self.assertIn("warnings", records[0]["tags"])
            self.assertIn("memory", records[0]["tags"])

    def test_warning_status_classifies_known_historical_and_unknown_findings(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            with patch("proto_mind.warning_inspector.SessionRituals.read_state") as read_state:
                read_state.return_value = {
                    "warnings": _warning_fixture(),
                    "context_state": "disabled",
                    "daily_status": "OK",
                    "export_status": "OK",
                    "system_status": "WARN",
                }

                output = format_warning_command("/warnings status", project_root=project_root, memory_store=store)

            self.assertIn("Legacy Warning Inspector Status", output)
            self.assertIn("Status: WARN", output)
            self.assertIn("known_warnings: 3", output)
            self.assertIn("dangling_ref=1", output)
            self.assertIn("legacy=1", output)
            self.assertIn("novel_signal=1", output)
            self.assertIn("known_historical=2", output)
            self.assertIn("new_or_unknown=1", output)
            self.assertIn("legacy_or_historical: 2", output)
            self.assertIn("accepted_known: 2", output)
            self.assertIn("unmatched_unknown: 1", output)

    def test_warning_list_uses_stable_ids_sources_and_operator_severity(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            inspector = LegacyWarningInspector(project_root=project_root, memory_store=store)
            with patch("proto_mind.warning_inspector.SessionRituals.read_state") as read_state:
                read_state.return_value = {
                    "warnings": _warning_fixture(),
                    "context_state": "disabled",
                    "daily_status": "OK",
                    "export_status": "OK",
                    "system_status": "WARN",
                }
                first_ids = [item["id"] for item in inspector.warnings()]
                second_ids = [item["id"] for item in inspector.warnings()]
                output = inspector.format_list()

            self.assertEqual(first_ids, second_ids)
            self.assertTrue(first_ids[0].startswith("warn_legacy_act_20260628165932_d2a9_"))
            self.assertIn("severity: INFO", output)
            self.assertIn("severity: WARN", output)
            self.assertIn("source: /action queue-doctor, /action run-audit", output)
            self.assertIn("classification: new_or_unknown", output)

    def test_warning_inspect_explains_paths_impact_and_manual_options_without_repair(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            with patch("proto_mind.warning_inspector.SessionRituals.read_state") as read_state:
                read_state.return_value = {
                    "warnings": _warning_fixture()[:2],
                    "context_state": "disabled",
                    "daily_status": "OK",
                    "export_status": "OK",
                    "system_status": "WARN",
                }
                output = format_warning_command("/warnings inspect", project_root=project_root, memory_store=store)

            self.assertIn("Legacy Warning Inspection", output)
            self.assertIn(str(project_root / "proto_mind" / "data" / "action_queue.jsonl"), output)
            self.assertIn(str(project_root / "proto_mind" / "data" / "consolidation_queue.jsonl"), output)
            self.assertIn("runtime safety:", output)
            self.assertIn("data integrity:", output)
            self.assertIn("leave as historical/legacy", output)
            self.assertIn("create a separate migration/repair task later", output)
            self.assertIn("No repair performed", output)
            self.assertIn("No file", output)

    def test_warning_doctor_checks_dependencies_context_and_dangerous_actions(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            store.save_persistent_memory([])
            _create_healthy_export_dirs(project_root)
            _write_milestone_fixture(project_root)

            output = format_warning_command("/warnings doctor", project_root=project_root, memory_store=store)

            self.assertIn("Warning Inspector Doctor", output)
            self.assertIn("Status: OK", output)
            self.assertIn("All warning-inspector commands are registered", output)
            self.assertIn("read-only with mutates=none", output)
            self.assertIn("Daily, Session Ritual, Milestone, and Export diagnostics are reachable", output)
            self.assertIn("Context Injection is disabled", output)
            self.assertIn("No repair, deletion, move, rewrite, cleanup, compression, or execution action is exposed", output)
            self.assertIn("Existing Proto warning source is reachable", output)

    def test_warning_doctor_warns_without_changing_explicit_context_enablement(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            store.save_persistent_memory([])
            _create_healthy_export_dirs(project_root)
            _write_milestone_fixture(project_root)
            format_context_command("/context injection enable", project_root=project_root)
            settings_path = project_root / "proto_mind" / "data" / "context_injection.json"
            before = settings_path.read_bytes()

            output = format_warning_command("/warnings doctor", project_root=project_root, memory_store=store)

            self.assertIn("Status: WARN", output)
            self.assertIn("Context Injection is explicitly enabled", output)
            self.assertEqual(settings_path.read_bytes(), before)
            self.assertTrue(json.loads(settings_path.read_text(encoding="utf-8"))["enabled"])

    def test_warning_accepted_summarizes_narrow_rules_without_hiding_findings(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            with patch("proto_mind.warning_inspector.SessionRituals.read_state") as read_state:
                read_state.return_value = {
                    "warnings": _accepted_warning_fixture(),
                    "context_state": "disabled",
                    "daily_status": "OK",
                    "export_status": "OK",
                    "system_status": "WARN",
                }
                output = format_warning_command("/warnings accepted", project_root=project_root, memory_store=store)

            self.assertIn("Accepted Known Warnings", output)
            self.assertIn("Status: OK", output)
            self.assertIn("accepted_findings: 4", output)
            self.assertIn("total_findings: 4", output)
            self.assertIn("accepted_dangling_consolidation_receipt", output)
            self.assertIn("accepted_legacy_action_receipt_v1", output)
            self.assertIn("accepted_context_enable_readiness_guard", output)
            self.assertIn("accepted_approved_unconfirmed_queue_state", output)
            self.assertIn("Runtime gates remain protective", output)
            self.assertIn("does not authorize execution or suppress source warnings", output)

    def test_warning_accepted_ledger_reads_docs_without_updating_file(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            ledger = project_root / "KNOWN_WARNINGS_LEDGER.md"
            ledger.write_text("# Accepted fixture\n\nNo runtime mutation.\n", encoding="utf-8")
            before = ledger.read_bytes()

            output = format_warning_command("/warnings accepted-ledger", project_root=project_root, memory_store=store)

            self.assertIn("Accepted Known Warnings Ledger", output)
            self.assertIn(f"path: {ledger}", output)
            self.assertIn("readable: yes", output)
            self.assertIn("# Accepted fixture", output)
            self.assertIn("Ledger text was read only", output)
            self.assertEqual(ledger.read_bytes(), before)

    def test_warning_unknown_reports_zero_for_current_accepted_baseline(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            with patch("proto_mind.warning_inspector.SessionRituals.read_state") as read_state:
                read_state.return_value = {
                    "warnings": _accepted_warning_fixture(),
                    "context_state": "disabled",
                    "daily_status": "OK",
                    "export_status": "OK",
                    "system_status": "WARN",
                }
                output = format_warning_command("/warnings unknown", project_root=project_root, memory_store=store)

            self.assertIn("Unknown / Unaccepted Warning Findings", output)
            self.assertIn("Status: OK", output)
            self.assertIn("unknown_findings: 0", output)
            self.assertIn("accepted_findings: 4", output)
            self.assertIn("all current findings match narrow accepted-known rules", output)
            self.assertIn("this filter suppresses nothing", output)

    def test_warning_unknown_does_not_accept_new_record_with_known_category(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            new_legacy = dict(_warning_fixture()[0])
            new_legacy["message"] = "act_20990101000000_new1: executed record is missing run_id"
            with patch("proto_mind.warning_inspector.SessionRituals.read_state") as read_state:
                read_state.return_value = {
                    "warnings": [new_legacy],
                    "context_state": "disabled",
                    "daily_status": "OK",
                    "export_status": "OK",
                    "system_status": "WARN",
                }
                output = format_warning_command("/warnings unknown", project_root=project_root, memory_store=store)

            self.assertIn("Status: WARN", output)
            self.assertIn("unknown_findings: 1", output)
            self.assertIn("accepted_findings: 0", output)
            self.assertIn("act_20990101000000_new1", output)

    def test_warning_commands_are_read_only_through_shared_handler(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            coordinator, store, _ = build_test_system(project_root / "proto_mind")
            store.save_persistent_memory([])
            logger = SessionOperatorLogger.from_project_root(project_root)
            coordinator.session_logger = logger
            _create_healthy_export_dirs(project_root)
            _write_milestone_fixture(project_root)
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
                    "/warnings status",
                    "/warnings list",
                    "/warnings inspect",
                    "/warnings accepted",
                    "/warnings accepted-ledger",
                    "/warnings unknown",
                    "/warnings doctor",
                )
            ]

            self.assertIn("Legacy Warning Inspector Status", outputs[0])
            self.assertIn("Detected Warning List", outputs[1])
            self.assertIn("Legacy Warning Inspection", outputs[2])
            self.assertIn("Accepted Known Warnings", outputs[3])
            self.assertIn("Accepted Known Warnings Ledger", outputs[4])
            self.assertIn("Unknown / Unaccepted Warning Findings", outputs[5])
            self.assertIn("Warning Inspector Doctor", outputs[6])
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

    def test_local_capability_contracts_match_runner_allowlist_and_mcp_shape(self) -> None:
        self.assertEqual(
            tuple(contract.command for contract in LOCAL_CAPABILITY_CONTRACTS),
            tuple(ACTIVE_READONLY_ALLOWLIST),
        )
        self.assertEqual(len({contract.name for contract in LOCAL_CAPABILITY_CONTRACTS}), 4)
        for contract in LOCAL_CAPABILITY_CONTRACTS:
            descriptor = contract.to_descriptor()
            self.assertEqual(descriptor["inputSchema"]["properties"], {})
            self.assertFalse(descriptor["inputSchema"]["additionalProperties"])
            self.assertEqual(
                descriptor["annotations"],
                {
                    "readOnlyHint": True,
                    "destructiveHint": False,
                    "openWorldHint": False,
                    "idempotentHint": True,
                },
            )
            self.assertTrue(descriptor["_meta"]["proto_mind"]["local_only"])
            self.assertEqual(descriptor["_meta"]["proto_mind"]["transport"], "none")
            self.assertFalse(descriptor["_meta"]["proto_mind"]["network_access"])
            self.assertFalse(descriptor["_meta"]["proto_mind"]["external_exposure"])
        self.assertEqual(local_capability_contract_doctor()["status"], "OK")

    def test_local_capability_result_uses_explicit_three_channel_envelope(self) -> None:
        output = "Daily Layer Doctor\nStatus: WARN\n- accepted legacy warning"
        result = build_local_capability_result("/daily doctor", output).to_mcp_result()

        self.assertEqual(set(result), {"structuredContent", "content", "_meta"})
        self.assertEqual(result["structuredContent"]["command"], "/daily doctor")
        self.assertEqual(result["structuredContent"]["contract"], "daily_doctor")
        self.assertEqual(result["structuredContent"]["status"], "WARN")
        self.assertEqual(result["structuredContent"]["summary"], "Daily Layer Doctor")
        self.assertTrue(result["structuredContent"]["read_only"])
        self.assertTrue(result["structuredContent"]["local_only"])
        self.assertEqual(result["content"], [{"type": "text", "text": output}])
        self.assertEqual(result["_meta"]["proto_mind"]["transport"], "none")
        self.assertFalse(result["_meta"]["proto_mind"]["network_access"])
        self.assertFalse(result["_meta"]["proto_mind"]["store_mutation"])
        self.assertFalse(result["_meta"]["proto_mind"]["full_output_exportable"])

    def test_local_capability_contract_lookup_refuses_unlisted_commands(self) -> None:
        self.assertEqual(get_local_capability_contract("daily_doctor").command, "/daily doctor")
        self.assertEqual(get_local_capability_contract("/exports doctor").name, "exports_doctor")
        self.assertIsNone(get_local_capability_contract("/memory status"))
        with self.assertRaisesRegex(ValueError, "no local capability contract"):
            build_local_capability_result("/memory status", "Memory status")

    def test_local_capability_contract_doctor_rejects_registry_policy_drift(self) -> None:
        drifted_registry = tuple(
            replace(spec, read_only=False, mutates="session", risk="medium")
            if spec.prefix == "/daily doctor"
            else spec
            for spec in COMMAND_REGISTRY
        )

        report = local_capability_contract_doctor(registry=drifted_registry)

        self.assertEqual(report["status"], "ERROR")
        self.assertTrue(any("/daily doctor" in item["message"] for item in report["findings"]))

    def test_verified_lesson_recall_benchmark_passes_english_and_russian(self) -> None:
        report = run_verified_lesson_recall_benchmark()

        self.assertEqual(report.status, "OK")
        self.assertEqual(report.version, LESSON_RECALL_BENCHMARK_VERSION)
        self.assertEqual(report.case_count, 2)
        self.assertEqual(report.passed_count, 2)
        self.assertTrue(report.invalid_lesson_filtered)
        self.assertTrue(report.unprovenanced_lesson_filtered)
        self.assertEqual({case.language for case in report.cases}, {"en", "ru"})

    def test_verified_lesson_recall_benchmark_preserves_store_bytes_and_usage(self) -> None:
        report = run_verified_lesson_recall_benchmark()

        for case in report.cases:
            self.assertTrue(case.lesson_selected)
            self.assertTrue(case.trace_provenance_visible)
            self.assertEqual(case.grounding_status, "grounded")
            self.assertTrue(case.grounding_provenance_visible)
            self.assertTrue(case.persistent_bytes_unchanged)
            self.assertTrue(case.working_bytes_unchanged)
            self.assertTrue(case.usage_unchanged)
            self.assertTrue(case.memory_count_unchanged)

    def test_verified_lesson_recall_benchmark_report_states_safety_boundary(self) -> None:
        output = format_verified_lesson_recall_benchmark()

        self.assertIn("Status: OK", output)
        self.assertIn("cases: 2/2", output)
        self.assertIn("local temporary stores only", output)
        self.assertIn("retrieval usage tracking disabled", output)
        self.assertIn("no automatic memory write", output)
        self.assertIn("no automatic memory write, learning apply", output)

    def test_verified_lesson_recall_does_not_expand_command_surface(self) -> None:
        self.assertEqual(len(COMMAND_REGISTRY), 387)
        self.assertEqual(len({entry.category for entry in COMMAND_REGISTRY}), 41)
        self.assertEqual(command_registry_doctor()["status"], "OK")
        self.assertEqual(action_policy_doctor()["status"], "OK")

    def test_restored_skill_reevaluation_requires_a_verified_restore(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store, library, _, _ = build_test_applied_procedural_skill(Path(temp_dir))
            record = library.read_snapshot()["records"][0]
            review = ProceduralSkillRestoreReevaluationReviewer(
                [],
                [record],
                store.load_persistent_memory(),
                skills_path=library.skills_path,
                persistent_memory_path=store.persistent_path,
            ).review(str(record["id"]))

        self.assertEqual(review.status, "NOT_RESTORED")
        self.assertFalse(review.checks["active_restored_verified"])
        self.assertFalse(review.future_lifecycle_decision_ready)
        self.assertFalse(review.mutation_performed)

    def test_restored_skill_reevaluation_excludes_old_and_unbound_evidence(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store, library, record = build_test_restored_procedural_skill(Path(temp_dir))
            pre_restore_events = build_test_restored_skill_outcome_events(
                record,
                after_restore=False,
                exact_restore_binding=True,
            )
            unbound_events = build_test_restored_skill_outcome_events(
                record,
                after_restore=True,
                exact_restore_binding=False,
            )
            reviewer_args = {
                "skill_records": [record],
                "memory_records": store.load_persistent_memory(),
                "skills_path": library.skills_path,
                "persistent_memory_path": store.persistent_path,
            }
            old_review = ProceduralSkillRestoreReevaluationReviewer(
                pre_restore_events, **reviewer_args
            ).review(str(record["id"]))
            unbound_review = ProceduralSkillRestoreReevaluationReviewer(
                unbound_events, **reviewer_args
            ).review(str(record["id"]))

        self.assertEqual(old_review.status, "NEEDS_POST_RESTORE_EVIDENCE")
        self.assertEqual(old_review.pre_restore_manual_use_count, 1)
        self.assertEqual(old_review.bound_post_restore_manual_use_count, 0)
        self.assertIn("Excluded 1 pre-restore", " ".join(old_review.warnings))
        self.assertEqual(unbound_review.status, "NEEDS_POST_RESTORE_EVIDENCE")
        self.assertEqual(unbound_review.unbound_post_restore_manual_use_count, 1)
        self.assertFalse(unbound_review.checks["exact_restore_binding_present"])
        self.assertIn("without the exact restore binding", " ".join(unbound_review.warnings))

    def test_restored_skill_reevaluation_accepts_exact_new_success_evidence(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store, library, record = build_test_restored_procedural_skill(Path(temp_dir))
            events = build_test_restored_skill_outcome_events(record, outcome="success")
            skills_before = library.skills_path.read_bytes()
            memory_before = store.persistent_path.read_bytes()
            reviewer = ProceduralSkillRestoreReevaluationReviewer(
                events,
                [record],
                store.load_persistent_memory(),
                skills_path=library.skills_path,
                persistent_memory_path=store.persistent_path,
            )
            review = reviewer.review(str(record["id"]))
            doctor = reviewer.doctor()
            skills_after = library.skills_path.read_bytes()
            memory_after = store.persistent_path.read_bytes()

        self.assertEqual(review.status, "POST_RESTORE_SUCCESS_CANDIDATE")
        self.assertEqual(review.bound_post_restore_manual_use_count, 1)
        self.assertEqual(review.post_restore_signal_count, 1)
        self.assertTrue(review.checks["manual_use_strictly_after_restore"])
        self.assertTrue(review.checks["exact_restore_binding_present"])
        self.assertTrue(review.checks["decisive_post_restore_outcome_found"])
        self.assertEqual(len(review.review_hash), 64)
        self.assertFalse(review.future_lifecycle_decision_ready)
        self.assertEqual(doctor.status, "OK")
        self.assertEqual(doctor.exact_post_restore_evidence_count, 1)
        self.assertEqual(skills_after, skills_before)
        self.assertEqual(memory_after, memory_before)

    def test_restored_skill_reevaluation_refuses_execution_claim(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store, library, record = build_test_restored_procedural_skill(Path(temp_dir))
            events = build_test_restored_skill_outcome_events(
                record,
                execution_performed_by_proto_mind=True,
            )
            review = ProceduralSkillRestoreReevaluationReviewer(
                events,
                [record],
                store.load_persistent_memory(),
                skills_path=library.skills_path,
                persistent_memory_path=store.persistent_path,
            ).review(str(record["id"]))

        self.assertEqual(review.status, "ERROR")
        self.assertFalse(review.checks["proto_mind_execution_absent"])
        self.assertIn("execution_performed_by_proto_mind=false", " ".join(review.issues))

    def test_restored_skill_legacy_capture_and_decision_paths_fail_closed(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store, library, record = build_test_restored_procedural_skill(Path(temp_dir))
            capture_builder = ProceduralSkillOutcomeCaptureBuilder(
                memory_store=store,
                skill_library=library,
            )
            with self.assertRaisesRegex(
                ProceduralSkillOutcomeCaptureError, "restore-bound"
            ):
                capture_builder.build(
                    session_id="session_restored",
                    skill_id=str(record["id"]),
                    outcome="success",
                    evidence="Manual restored-skill result.",
                )
            decision_builder = ProceduralSkillOutcomeDecisionBuilder(
                events=build_test_restored_skill_outcome_events(record),
                memory_store=store,
                skill_library=library,
                capture_session=OperatorReviewedProceduralSkillOutcomeCaptureSession(),
            )
            with self.assertRaisesRegex(
                ProceduralSkillOutcomeDecisionError, "post-restore evidence"
            ):
                decision_builder.build(str(record["id"]), "keep")

        self.assertEqual(capture_builder.current_skill_is_valid(str(record["id"]))[0], False)

    def test_restored_skill_reevaluation_commands_are_read_only_and_registered(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store, library, record = build_test_restored_procedural_skill(Path(temp_dir))
            events = build_test_restored_skill_outcome_events(record)
            before = (library.skills_path.read_bytes(), store.persistent_path.read_bytes())
            common = {
                "events": events,
                "memory_store": store,
                "skill_library": library,
            }
            contract = format_procedural_skill_restore_reevaluation_command(
                "/experience learning skill-outcome-doctor --post-restore-contract",
                **common,
            )
            review = format_procedural_skill_restore_reevaluation_command(
                f"/experience learning skill-outcome-review {record['id']} --post-restore",
                **common,
            )
            plan = format_procedural_skill_restore_reevaluation_command(
                f"/experience learning skill-outcome-review {record['id']} --post-restore-plan",
                **common,
            )
            doctor = format_procedural_skill_restore_reevaluation_command(
                "/experience learning skill-outcome-doctor --post-restore",
                **common,
            )
            chained = format_procedural_skill_restore_reevaluation_command(
                "/experience learning skill-outcome-doctor --post-restore; /skills list",
                **common,
            )
            after = (library.skills_path.read_bytes(), store.persistent_path.read_bytes())

        registry = {entry.prefix: entry for entry in COMMAND_REGISTRY}
        assert contract is not None
        assert review is not None
        assert plan is not None
        assert doctor is not None
        assert chained is not None
        self.assertIn(PROCEDURAL_SKILL_RESTORE_REEVALUATION_MODE, contract)
        self.assertIn(
            ", ".join(PROCEDURAL_SKILL_RESTORE_REEVALUATION_REQUIRED_CALL_FIELDS),
            contract,
        )
        self.assertIn("POST_RESTORE_SUCCESS_CANDIDATE", review)
        self.assertIn("future_capture_command_available: false", plan)
        self.assertIn("Status: OK", doctor)
        self.assertIn("Command chaining", chained)
        self.assertEqual(after, before)
        for prefix in (
            "/experience learning skill-outcome-review",
            "/experience learning skill-outcome-doctor",
        ):
            self.assertTrue(registry[prefix].read_only)
            self.assertEqual(registry[prefix].mutates, "none")
        self.assertEqual(len(COMMAND_REGISTRY), 387)
        self.assertEqual(len({entry.category for entry in COMMAND_REGISTRY}), 41)
        self.assertEqual(command_registry_doctor()["status"], "OK")
        self.assertEqual(action_policy_doctor()["status"], "OK")

    def test_restored_skill_capture_readiness_binds_exact_current_evidence(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store, library, record = build_test_restored_procedural_skill(Path(temp_dir))
            before = (library.skills_path.read_bytes(), store.persistent_path.read_bytes())
            readiness = ProceduralSkillRestoreCaptureReadiness(
                memory_store=store,
                skill_library=library,
            )
            report = readiness.review(
                session_id="session_restore_capture",
                pilot_state="consented",
                skill_id=str(record["id"]),
                outcome="success",
                evidence="Operator manually verified the restored procedure.",
            )
            current, current_issues = readiness.current_state_matches(report)
            verified, verify_issues = verify_procedural_skill_restore_capture_blueprint(
                report.to_dict()
            )
            after = (library.skills_path.read_bytes(), store.persistent_path.read_bytes())

        lifecycle = record["lifecycle"]
        assert isinstance(lifecycle, dict)
        restore_evidence = build_procedural_skill_restore_receipt_evidence(record)
        self.assertEqual(report.status, "READY FOR AUTHORIZATION DESIGN")
        self.assertTrue(report.ready_for_authorization_design)
        self.assertEqual(report.restore_metadata_hash, lifecycle["metadata_hash"])
        self.assertEqual(report.restore_evidence_hash, restore_evidence["evidence_hash"])
        self.assertEqual(
            tuple(report.required_tool_called_fields),
            PROCEDURAL_SKILL_RESTORE_REEVALUATION_REQUIRED_CALL_FIELDS,
        )
        self.assertEqual(
            tuple(report.future_receipt_fields),
            PROCEDURAL_SKILL_RESTORE_CAPTURE_FUTURE_RECEIPT_FIELDS,
        )
        self.assertTrue(current, current_issues)
        self.assertTrue(verified, verify_issues)
        self.assertFalse(report.confirmation_token_generated)
        self.assertFalse(report.writer_installed)
        self.assertFalse(report.event_append_performed)
        self.assertEqual(after, before)

    def test_restored_skill_capture_readiness_requires_exact_session_consent(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store, library, record = build_test_restored_procedural_skill(Path(temp_dir))
            report = ProceduralSkillRestoreCaptureReadiness(
                memory_store=store,
                skill_library=library,
            ).review(
                session_id="session_restore_capture",
                pilot_state="disabled",
                skill_id=str(record["id"]),
                outcome="failure",
                evidence="Manual restored procedure did not meet the expected result.",
            )

        self.assertEqual(report.status, "NOT READY")
        self.assertFalse(report.checks["session_consent_active"])
        self.assertIn("consent is not active", " ".join(report.issues))
        self.assertFalse(report.confirmation_token_generated)

    def test_restored_skill_capture_readiness_refuses_ordinary_or_invalid_input(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store, library, _, _ = build_test_applied_procedural_skill(Path(temp_dir))
            record = library.read_snapshot()["records"][0]
            readiness = ProceduralSkillRestoreCaptureReadiness(
                memory_store=store,
                skill_library=library,
            )
            with self.assertRaisesRegex(
                ProceduralSkillRestoreCaptureReadinessError, "restore envelope"
            ):
                readiness.review(
                    session_id="session_restore_capture",
                    pilot_state="consented",
                    skill_id=str(record["id"]),
                    outcome="success",
                    evidence="Ordinary active skill.",
                )
            with self.assertRaisesRegex(
                ProceduralSkillRestoreCaptureReadinessError, "success or failure"
            ):
                readiness.review(
                    session_id="session_restore_capture",
                    pilot_state="consented",
                    skill_id=str(record["id"]),
                    outcome="mixed",
                    evidence="Invalid outcome.",
                )

    def test_restored_skill_capture_readiness_detects_tamper_and_store_drift(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store, library, record = build_test_restored_procedural_skill(Path(temp_dir))
            readiness = ProceduralSkillRestoreCaptureReadiness(
                memory_store=store,
                skill_library=library,
            )
            report = readiness.review(
                session_id="session_restore_capture",
                pilot_state="consented",
                skill_id=str(record["id"]),
                outcome="success",
                evidence="Verified before deterministic tamper check.",
            )
            tampered = report.to_dict()
            tampered["restore_evidence_hash"] = "0" * 64
            verified, verify_issues = verify_procedural_skill_restore_capture_blueprint(
                tampered
            )
            library.skills_path.write_bytes(library.skills_path.read_bytes() + b"\n")
            current, current_issues = readiness.current_state_matches(report)

        self.assertFalse(verified)
        self.assertIn("blueprint hash", " ".join(verify_issues))
        self.assertFalse(current)
        self.assertIn("bytes changed", " ".join(current_issues))

    def test_restored_skill_capture_readiness_commands_are_read_only(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store, library, record = build_test_restored_procedural_skill(Path(temp_dir))
            readiness = ProceduralSkillRestoreCaptureReadiness(
                memory_store=store,
                skill_library=library,
            )
            before = (library.skills_path.read_bytes(), store.persistent_path.read_bytes())
            common = {
                "readiness": readiness,
                "pilot_state": "consented",
                "pilot_session_id": "session_restore_capture",
            }
            preview = format_procedural_skill_restore_capture_readiness_command(
                "/experience learning skill-outcome-capture-preview "
                f"{record['id']} success --evidence \"Manual exact result.\" "
                "--post-restore-readiness",
                **common,
            )
            plan = format_procedural_skill_restore_capture_readiness_command(
                "/experience learning skill-outcome-capture-preview "
                f"{record['id']} success --evidence \"Manual exact result.\" "
                "--post-restore-plan",
                **common,
            )
            contract = format_procedural_skill_restore_capture_readiness_command(
                "/experience learning skill-outcome-capture-doctor --post-restore-contract",
                **common,
            )
            doctor = format_procedural_skill_restore_capture_readiness_command(
                "/experience learning skill-outcome-capture-doctor --post-restore",
                **common,
            )
            chained = format_procedural_skill_restore_capture_readiness_command(
                "/experience learning skill-outcome-capture-doctor --post-restore; /skills list",
                **common,
            )
            after = (library.skills_path.read_bytes(), store.persistent_path.read_bytes())

        assert preview is not None
        assert plan is not None
        assert contract is not None
        assert doctor is not None
        assert chained is not None
        self.assertIn("READY FOR AUTHORIZATION DESIGN", preview)
        self.assertIn("confirmation_token_generated: false", preview)
        self.assertIn("Future exact sequence", plan)
        self.assertIn("Status: DESIGN LOCKED", contract)
        self.assertIn("Status: OK", doctor)
        self.assertIn("Command chaining", chained)
        self.assertEqual(after, before)

    def test_restored_skill_capture_readiness_registry_and_policy_remain_safe(self) -> None:
        registry = {entry.prefix: entry for entry in COMMAND_REGISTRY}
        for prefix in (
            "/experience learning skill-outcome-capture-preview",
            "/experience learning skill-outcome-capture-doctor",
        ):
            self.assertTrue(registry[prefix].read_only)
            self.assertEqual(registry[prefix].mutates, "none")
            self.assertEqual(registry[prefix].risk, "low")
        self.assertEqual(len(COMMAND_REGISTRY), 387)
        self.assertEqual(len({entry.category for entry in COMMAND_REGISTRY}), 41)
        self.assertEqual(command_registry_doctor()["status"], "OK")
        self.assertEqual(action_policy_doctor()["status"], "OK")
        self.assertEqual(
            PROCEDURAL_SKILL_RESTORE_CAPTURE_READINESS_MODE,
            "read_only_exact_restore_bound_capture_authorization_design",
        )
