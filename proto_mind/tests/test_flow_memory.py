"""Core flow checks: memory."""
from __future__ import annotations

import unittest
from proto_mind.tests.flow_fixtures import (
    COMMAND_REGISTRY,
    MemoryHygiene,
    MemoryRecord,
    MemoryStore,
    Observer,
    Path,
    SessionOperatorLogger,
    TemporaryDirectory,
    UTC,
    _create_healthy_export_dirs,
    _memory_card_state,
    _write_milestone_fixture,
    action_policy_doctor,
    apply_test_learning_proposal,
    build_test_learning_apply,
    build_test_system,
    classify_command,
    command_registry_doctor,
    datetime,
    format_context_command,
    format_memory_card_command,
    format_memory_command,
    inspect_memory_quality,
    json,
    memory_write_policy,
    patch,
    process_interactive_input,
    timedelta,
)


class MemoryFlowTests(unittest.TestCase):
    def test_memory_retrieval_scoring(self) -> None:
        with TemporaryDirectory() as temp_dir:
            tmp_path = Path(temp_dir)
            _, store, keeper = build_test_system(tmp_path)
            recent = MemoryRecord(
                content="We decided JSON storage fits the MVP.",
                type="decision",
                importance=0.9,
                source="test",
                tags=["proto-mind", "memory"],
                timestamp=datetime.now(UTC).isoformat(),
                usage_count=3,
            )
            stale = MemoryRecord(
                content="We joked about naming the bot.",
                type="insight",
                importance=0.2,
                source="test",
                tags=["name"],
                timestamp=(datetime.now(UTC) - timedelta(days=20)).isoformat(),
                usage_count=0,
                weight=0.6,
            )
            store.save_working_memory([recent, stale])
            state = Observer().analyze("What did we decide earlier about Proto-Mind memory?")
            retrieved = keeper.retrieve(state, top_k=2)
            self.assertTrue(retrieved)
            self.assertEqual(retrieved[0].content, recent.content)
            self.assertGreater(keeper.score_record(recent, state), keeper.score_record(stale, state))

    def test_memory_retrieval_is_store_read_only_by_default(self) -> None:
        with TemporaryDirectory() as temp_dir:
            tmp_path = Path(temp_dir)
            _, store, keeper = build_test_system(tmp_path)
            record = MemoryRecord(
                content="I prefer short answers.",
                type="preference",
                importance=0.8,
                source="test",
                tags=["preference", "short", "response_style"],
            )
            store.save_persistent_memory([record])
            before_working = store.working_path.read_bytes()
            before_persistent = store.persistent_path.read_bytes()

            selected = keeper.retrieve(Observer().analyze("What style should you use in future responses?"))

            self.assertTrue(selected)
            self.assertEqual(store.working_path.read_bytes(), before_working)
            self.assertEqual(store.persistent_path.read_bytes(), before_persistent)
            reloaded = store.load_persistent_memory()[0]
            self.assertEqual(reloaded.usage_count, 0)
            self.assertIsNone(reloaded.last_used)

    def test_memory_usage_telemetry_requires_explicit_api_call(self) -> None:
        with TemporaryDirectory() as temp_dir:
            tmp_path = Path(temp_dir)
            _, store, keeper = build_test_system(tmp_path)
            record = MemoryRecord(
                content="I prefer short answers.",
                type="preference",
                importance=0.8,
                source="test",
                tags=["preference", "short", "response_style"],
            )
            store.save_persistent_memory([record])
            selected = keeper.retrieve(Observer().analyze("What style should you use in future responses?"))

            keeper.record_retrieval_usage(selected)

            reloaded = store.load_persistent_memory()[0]
            self.assertEqual(reloaded.usage_count, 1)
            self.assertIsNotNone(reloaded.last_used)

    def test_memory_write_policy_is_explicit_and_non_mutating(self) -> None:
        policy = memory_write_policy()
        with TemporaryDirectory() as temp_dir:
            _, store, _ = build_test_system(Path(temp_dir))
            before_working = store.working_path.read_bytes()
            before_persistent = store.persistent_path.read_bytes()
            output = format_memory_command("/memory write-policy", store)

            self.assertEqual(store.working_path.read_bytes(), before_working)
            self.assertEqual(store.persistent_path.read_bytes(), before_persistent)

        self.assertFalse(policy["retrieval_store_mutation"])
        self.assertEqual(policy["usage_telemetry"], "explicit_api_only")
        self.assertEqual(policy["automatic_content_source"], "user_input_only")
        self.assertFalse(policy["full_response_storage"])
        self.assertIn("retrieval_store_mutation: false", output)
        self.assertIn("migration_mode: preview_only", output)

    def test_memory_quality_preview_detects_recursive_response_coupling(self) -> None:
        content = (
            "User input: first | System response: User input: nested | System response: answer "
            + ("x" * 1100)
        )
        with TemporaryDirectory() as temp_dir:
            _, store, _ = build_test_system(Path(temp_dir))
            store.save_persistent_memory(
                [MemoryRecord(content=content, type="project", importance=0.9, source="legacy")]
            )
            before = store.persistent_path.read_bytes()
            report = inspect_memory_quality(store)
            output = format_memory_command("/memory quality-preview", store)

            self.assertEqual(store.persistent_path.read_bytes(), before)

        self.assertEqual(report["status"], "WARN")
        self.assertEqual(len(report["findings"]), 1)
        self.assertEqual(
            set(report["findings"][0].flags),
            {"response_coupled", "recursive_context", "long_content"},
        )
        self.assertIn("migration_candidates: 1", output)
        self.assertIn("mutation_performed", output)
        self.assertIn("Preview only", output)

    def test_memory_quality_preview_reports_clean_compact_records(self) -> None:
        with TemporaryDirectory() as temp_dir:
            _, store, _ = build_test_system(Path(temp_dir))
            store.save_persistent_memory(
                [
                    MemoryRecord(
                        content="Я предпочитаю короткие ответы.",
                        type="preference",
                        importance=0.8,
                        source="operator",
                    )
                ]
            )
            report = inspect_memory_quality(store)
            output = format_memory_command("/memory quality-preview", store)

        self.assertEqual(report["status"], "OK")
        self.assertFalse(report["findings"])
        self.assertIn("Status: OK", output)
        self.assertIn("migration_candidates: 0", output)

    def test_memory_inventory_answer_is_grounded_in_stored_memory(self) -> None:
        with TemporaryDirectory() as temp_dir:
            tmp_path = Path(temp_dir)
            coordinator, _, _ = build_test_system(tmp_path)
            coordinator.handle("I prefer concise architectural explanations for future Proto-Mind discussions.")
            coordinator.handle("We decided JSON-backed memory is enough for v0.")
            result = coordinator.handle("What preferences and decisions do you currently remember separately?")
            self.assertEqual(result.observer_state.query_type, "memory_inventory")
            self.assertTrue(result.retrieved_memory)
            self.assertIsNotNone(result.retrieval_trace)
            self.assertEqual(result.retrieval_trace.query_mode, "broad_inventory")
            self.assertIn("current stored memory", result.response.lower())
            self.assertIn("concise architectural explanations", result.response.lower())
            self.assertIn("json-backed memory is enough for v0", result.response.lower())

    def test_memory_decision_metadata_consistency(self) -> None:
        with TemporaryDirectory() as temp_dir:
            tmp_path = Path(temp_dir)
            coordinator, _, _ = build_test_system(tmp_path)
            coordinator.handle("We decided JSON storage is enough for v0.")
            result = coordinator.handle("What durable architectural decisions do we currently have?")
            summary = result.memory_summary
            self.assertEqual(summary.should_promote_new, bool(summary.promoted_record_ids) if summary.should_store else False)
            if summary.should_promote_existing:
                self.assertTrue(summary.promoted_record_ids)
                self.assertIn("promoted existing memory", summary.promotion_rationale.lower())
            else:
                self.assertFalse(summary.promoted_record_ids)
                self.assertNotIn("promoted existing memory", summary.promotion_rationale.lower())

    def test_memory_hygiene_detects_normalized_duplicates(self) -> None:
        with TemporaryDirectory() as temp_dir:
            tmp_path = Path(temp_dir)
            _, store, _ = build_test_system(tmp_path)
            store.save_working_memory(
                [
                    MemoryRecord("I prefer short answers.", "preference", 0.8, "test", tags=["preference"]),
                    MemoryRecord("  i prefer short answers  ", "preference", 0.7, "test", tags=["preference"]),
                ]
            )
            preview = MemoryHygiene(store).preview_cleanup()
            self.assertEqual(len(preview.duplicate_groups), 1)
            self.assertEqual(preview.cleanup_candidate_count, 1)

    def test_memory_hygiene_preview_does_not_mutate_memory(self) -> None:
        with TemporaryDirectory() as temp_dir:
            tmp_path = Path(temp_dir)
            _, store, _ = build_test_system(tmp_path)
            record = MemoryRecord("I prefer short answers.", "preference", 0.8, "test", tags=["preference"])
            duplicate = MemoryRecord("I prefer short answers.", "preference", 0.7, "test", tags=["preference"])
            store.save_working_memory([record, duplicate])
            before = [item.to_dict() for item in store.load_working_memory()]
            MemoryHygiene(store).preview_cleanup()
            after = [item.to_dict() for item in store.load_working_memory()]
            self.assertEqual(before, after)

    def test_memory_hygiene_cleanup_removes_safe_working_and_persistent_duplicates(self) -> None:
        with TemporaryDirectory() as temp_dir:
            tmp_path = Path(temp_dir)
            _, store, _ = build_test_system(tmp_path)
            content = "We decided JSON-backed memory is enough for v0."
            working_one = MemoryRecord(content, "decision", 0.8, "interaction", tags=["json", "storage"])
            working_two = MemoryRecord(content, "decision", 0.7, "interaction", tags=["json", "storage"])
            persistent_keep = MemoryRecord(content, "decision", 0.95, "promoted", tags=["json", "storage"])
            persistent_duplicate = MemoryRecord(content, "decision", 0.85, "promoted", tags=["json", "storage"])
            store.save_working_memory([working_one, working_two])
            store.save_persistent_memory([persistent_keep, persistent_duplicate])

            result = MemoryHygiene(store).apply_cleanup()

            self.assertEqual(sorted(result.removed_working_ids), sorted([working_one.id, working_two.id]))
            self.assertEqual(result.removed_persistent_ids, [persistent_duplicate.id])
            self.assertFalse(store.load_working_memory())
            remaining_persistent = store.load_persistent_memory()
            self.assertEqual(len(remaining_persistent), 1)
            self.assertEqual(remaining_persistent[0].id, persistent_keep.id)

    def test_memory_hygiene_preserves_unique_superseded_history(self) -> None:
        with TemporaryDirectory() as temp_dir:
            tmp_path = Path(temp_dir)
            _, store, _ = build_test_system(tmp_path)
            old_decision = MemoryRecord(
                "We decided JSON-backed memory is enough for v0.",
                "decision",
                0.85,
                "promoted",
                tags=["json", "storage"],
                active=False,
                superseded_by="sqlite-decision",
            )
            new_decision = MemoryRecord(
                "Actually, we are changing direction: Proto-Mind should use SQLite instead of JSON.",
                "decision",
                0.85,
                "promoted",
                tags=["sqlite", "storage"],
            )
            store.save_persistent_memory([old_decision, new_decision])

            result = MemoryHygiene(store).apply_cleanup()

            self.assertFalse(result.removed_persistent_ids)
            remaining = store.load_persistent_memory()
            self.assertEqual({record.id for record in remaining}, {old_decision.id, new_decision.id})
            self.assertTrue(any(not record.active for record in remaining))

    def test_memory_hygiene_preserves_active_durable_memory_when_cleaning_duplicate(self) -> None:
        with TemporaryDirectory() as temp_dir:
            tmp_path = Path(temp_dir)
            _, store, _ = build_test_system(tmp_path)
            content = "I prefer concise architectural explanations."
            working = MemoryRecord(content, "preference", 0.8, "interaction", tags=["preference", "concise"])
            persistent = MemoryRecord(content, "preference", 0.9, "promoted", tags=["preference", "concise"])
            store.save_working_memory([working])
            store.save_persistent_memory([persistent])

            result = MemoryHygiene(store).apply_cleanup()

            self.assertEqual(result.removed_working_ids, [working.id])
            remaining_persistent = store.load_persistent_memory()
            self.assertEqual(len(remaining_persistent), 1)
            self.assertEqual(remaining_persistent[0].id, persistent.id)
            self.assertTrue(remaining_persistent[0].active)

    def test_memory_hygiene_repairs_superseded_by_when_duplicate_target_removed(self) -> None:
        with TemporaryDirectory() as temp_dir:
            tmp_path = Path(temp_dir)
            _, store, _ = build_test_system(tmp_path)
            sqlite_content = "Actually, we are changing direction: Proto-Mind should use SQLite instead of JSON."
            working_sqlite = MemoryRecord(
                sqlite_content,
                "decision",
                0.85,
                "interaction",
                tags=["sqlite", "storage"],
                id="sqlite-working-id",
            )
            persistent_sqlite = MemoryRecord(
                sqlite_content,
                "decision",
                0.95,
                "promoted",
                tags=["sqlite", "storage"],
                id="sqlite-persistent-id",
            )
            old_json = MemoryRecord(
                "We decided Proto-Mind should use JSON-backed memory.",
                "decision",
                0.8,
                "promoted",
                tags=["json", "storage"],
                id="json-old-id",
                active=False,
                superseded_by=working_sqlite.id,
                superseded_at="2026-04-27T12:00:00+00:00",
                superseded_reason="Superseded by a newer explicit decision.",
            )
            store.save_working_memory([working_sqlite])
            store.save_persistent_memory([old_json, persistent_sqlite])

            result = MemoryHygiene(store).apply_cleanup()

            self.assertEqual(result.removed_working_ids, [working_sqlite.id])
            self.assertEqual(result.preview.replacement_record_ids, {working_sqlite.id: persistent_sqlite.id})
            self.assertEqual(len(result.repaired_superseded_by_refs), 1)
            repair = result.repaired_superseded_by_refs[0]
            self.assertEqual(repair.record_id, old_json.id)
            self.assertEqual(repair.old_superseded_by, working_sqlite.id)
            self.assertEqual(repair.new_superseded_by, persistent_sqlite.id)
            remaining_json = next(record for record in store.load_persistent_memory() if record.id == old_json.id)
            self.assertEqual(remaining_json.superseded_by, persistent_sqlite.id)
            self.assertEqual(remaining_json.superseded_at, "2026-04-27T12:00:00+00:00")
            self.assertEqual(remaining_json.superseded_reason, "Superseded by a newer explicit decision.")

    def test_memory_hygiene_does_not_repair_without_safe_duplicate_mapping(self) -> None:
        with TemporaryDirectory() as temp_dir:
            tmp_path = Path(temp_dir)
            _, store, _ = build_test_system(tmp_path)
            old_json = MemoryRecord(
                "We decided Proto-Mind should use JSON-backed memory.",
                "decision",
                0.8,
                "promoted",
                tags=["json", "storage"],
                active=False,
                superseded_by="missing-sqlite-id",
                superseded_reason="Superseded by a newer explicit decision.",
            )
            store.save_persistent_memory([old_json])

            result = MemoryHygiene(store).apply_cleanup()

            self.assertFalse(result.removed_working_ids)
            self.assertFalse(result.removed_persistent_ids)
            self.assertFalse(result.repaired_superseded_by_refs)
            remaining_json = store.load_persistent_memory()[0]
            self.assertEqual(remaining_json.superseded_by, "missing-sqlite-id")

    def test_memory_commands_show_repaired_superseded_by_after_cleanup(self) -> None:
        with TemporaryDirectory() as temp_dir:
            tmp_path = Path(temp_dir)
            _, store, _ = build_test_system(tmp_path)
            sqlite_content = "Actually, we are changing direction: Proto-Mind should use SQLite instead of JSON."
            working_sqlite = MemoryRecord(
                sqlite_content,
                "decision",
                0.85,
                "interaction",
                id="sqlite-working-id",
            )
            persistent_sqlite = MemoryRecord(
                sqlite_content,
                "decision",
                0.95,
                "promoted",
                id="sqlite-persistent-id",
            )
            old_json = MemoryRecord(
                "We decided Proto-Mind should use JSON-backed memory.",
                "decision",
                0.8,
                "promoted",
                id="json-old-id",
                active=False,
                superseded_by=working_sqlite.id,
            )
            store.save_working_memory([working_sqlite])
            store.save_persistent_memory([old_json, persistent_sqlite])

            MemoryHygiene(store).apply_cleanup()
            output = format_memory_command("/memory history", store)

            self.assertIsNotNone(output)
            self.assertIn("superseded_by=sqlite-p", output)
            self.assertNotIn("superseded_by=sqlite-w", output)

    def test_memory_doctor_reports_header_and_counts(self) -> None:
        with TemporaryDirectory() as temp_dir:
            _, store, _ = build_test_system(Path(temp_dir))
            store.save_persistent_memory(
                [
                    MemoryRecord("Active explicit", "explicit", 1.0, "operator", confidence=1.0, updated_at="2026-06-18T01:00:00+00:00"),
                    MemoryRecord("Forgotten explicit", "explicit", 1.0, "operator", active=False, confidence=1.0, updated_at="2026-06-18T02:00:00+00:00"),
                    MemoryRecord("Legacy decision", "decision", 0.8, "promoted"),
                ]
            )

            output = format_memory_command("/memory doctor", store)

            self.assertIn("Memory Doctor", output)
            self.assertIn("Status: OK", output)
            self.assertIn("explicit active: 1", output)
            self.assertIn("explicit forgotten: 1", output)
            self.assertIn("legacy/other records: 1", output)

    def test_memory_doctor_empty_and_missing_files_are_clean(self) -> None:
        with TemporaryDirectory() as temp_dir:
            _, store, _ = build_test_system(Path(temp_dir))
            store.save_persistent_memory([])
            empty_output = format_memory_command("/memory doctor", store)
            store.persistent_path.unlink()
            missing_output = format_memory_command("/memory doctor", store)

            self.assertIn("Status: OK", empty_output)
            self.assertIn("Persistent memory is readable", empty_output)
            self.assertIn("Status: WARN", missing_output)
            self.assertIn("Persistent memory file is missing.", missing_output)

    def test_memory_doctor_invalid_json_is_error_and_read_only(self) -> None:
        with TemporaryDirectory() as temp_dir:
            _, store, _ = build_test_system(Path(temp_dir))
            store.persistent_path.write_text("{not json", encoding="utf-8")
            before = store.persistent_path.read_bytes()

            output = format_memory_command("/memory doctor", store)

            self.assertIn("Status: ERROR", output)
            self.assertIn("invalid JSON", output)
            self.assertEqual(store.persistent_path.read_bytes(), before)

    def test_memory_doctor_detects_duplicate_active_explicit_memories(self) -> None:
        with TemporaryDirectory() as temp_dir:
            _, store, _ = build_test_system(Path(temp_dir))
            duplicate_text = "User prefers local-first Proto-Mind architecture."
            store.save_persistent_memory(
                [
                    MemoryRecord(duplicate_text, "explicit", 1.0, "operator", id="mem_a", confidence=1.0, updated_at="2026-06-18T01:00:00+00:00"),
                    MemoryRecord(duplicate_text, "explicit", 1.0, "operator", id="mem_b", confidence=1.0, updated_at="2026-06-18T01:00:01+00:00"),
                    MemoryRecord(duplicate_text, "explicit", 1.0, "operator", id="mem_old", active=False, confidence=1.0, updated_at="2026-06-18T01:00:02+00:00"),
                ]
            )

            output = format_memory_command("/memory doctor", store)

            self.assertIn("Status: WARN", output)
            self.assertIn("Duplicate active explicit memories detected.", output)
            self.assertIn("mem_a, mem_b", output)
            self.assertNotIn("mem_old", output.split("Duplicate active explicit memories detected.", 1)[1])

    def test_memory_doctor_detects_long_empty_low_info_unknown_and_confidence_warnings(self) -> None:
        with TemporaryDirectory() as temp_dir:
            _, store, _ = build_test_system(Path(temp_dir))
            raw = [
                {
                    "content": "x" * 501,
                    "type": "explicit",
                    "importance": 1.0,
                    "source": "operator",
                    "id": "mem_long",
                    "timestamp": "2026-06-18T01:00:00+00:00",
                    "active": True,
                    "confidence": 1.0,
                    "updated_at": "2026-06-18T01:00:00+00:00",
                },
                {
                    "content": "",
                    "type": "explicit",
                    "importance": 1.0,
                    "source": "operator",
                    "id": "mem_empty",
                    "timestamp": "2026-06-18T01:00:00+00:00",
                    "active": True,
                    "confidence": 1.0,
                    "updated_at": "2026-06-18T01:00:00+00:00",
                },
                {
                    "content": "ok",
                    "type": "explicit",
                    "importance": 1.0,
                    "source": "operator",
                    "id": "mem_low",
                    "timestamp": "2026-06-18T01:00:00+00:00",
                    "active": True,
                    "confidence": 1.0,
                    "updated_at": "2026-06-18T01:00:00+00:00",
                },
                {
                    "content": "Unknown type",
                    "type": "mystery",
                    "importance": 0.5,
                    "source": "test",
                    "id": "unknown",
                    "timestamp": "2026-06-18T01:00:00+00:00",
                },
                {
                    "content": "Bad confidence",
                    "type": "explicit",
                    "importance": 1.0,
                    "source": "operator",
                    "id": "bad_conf",
                    "timestamp": "2026-06-18T01:00:00+00:00",
                    "active": True,
                    "confidence": 1.5,
                    "updated_at": "2026-06-18T01:00:00+00:00",
                },
            ]
            store.persistent_path.write_text(json.dumps(raw), encoding="utf-8")

            output = format_memory_command("/memory doctor", store)

            self.assertIn("Status: WARN", output)
            self.assertIn("Empty memory content found.", output)
            self.assertIn("Possible low-information active explicit memories detected.", output)
            self.assertIn("Unknown memory types found.", output)
            self.assertIn("Invalid confidence values found.", output)
            self.assertIn("Long active explicit memories detected.", output)

    def test_memory_doctor_detects_conflicts_and_near_duplicates(self) -> None:
        with TemporaryDirectory() as temp_dir:
            _, store, _ = build_test_system(Path(temp_dir))
            store.save_persistent_memory(
                [
                    MemoryRecord("User likes concise answers.", "explicit", 1.0, "operator", id="mem_like", confidence=1.0, updated_at="2026-06-18T01:00:00+00:00"),
                    MemoryRecord("User does not like concise answers.", "explicit", 1.0, "operator", id="mem_dislike", confidence=1.0, updated_at="2026-06-18T01:00:01+00:00"),
                    MemoryRecord("User prefers concise local first Proto Mind architecture.", "explicit", 1.0, "operator", id="mem_near_a", confidence=1.0, updated_at="2026-06-18T01:00:02+00:00"),
                    MemoryRecord("User prefers concise local first Proto Mind architecture please.", "explicit", 1.0, "operator", id="mem_near_b", confidence=1.0, updated_at="2026-06-18T01:00:03+00:00"),
                ]
            )

            output = format_memory_command("/memory doctor", store)

            self.assertIn("Possible conflicting active explicit memories detected.", output)
            self.assertIn("mem_like conflicts-with mem_dislike", output)
            self.assertIn("Possible near-duplicate active explicit memories detected.", output)
            self.assertIn("mem_near_a ~ mem_near_b", output)

    def test_memory_doctor_is_read_only_and_memory_commands_still_work_afterward(self) -> None:
        with TemporaryDirectory() as temp_dir:
            _, store, _ = build_test_system(Path(temp_dir))
            format_memory_command("/memory remember User prefers local-first Proto-Mind architecture.", store)
            before = store.persistent_path.read_bytes()

            doctor_output = format_memory_command("/memory doctor", store)
            after_doctor = store.persistent_path.read_bytes()
            remember_output = format_memory_command("/memory remember User likes explicit controls.", store)
            memory_id = next(line.strip().split(" — ")[0] for line in remember_output.splitlines() if line.strip().startswith("mem_"))
            forget_output = format_memory_command(f"/memory forget {memory_id}", store)

            self.assertIn("Memory Doctor", doctor_output)
            self.assertEqual(after_doctor, before)
            self.assertIn("Remembered:", remember_output)
            self.assertIn("Forgotten:", forget_output)

    def test_memory_reference_preview_detects_orphaned_superseded_by(self) -> None:
        with TemporaryDirectory() as temp_dir:
            tmp_path = Path(temp_dir)
            _, store, _ = build_test_system(tmp_path)
            old_json = MemoryRecord(
                "We decided Proto-Mind should use JSON-backed memory.",
                "decision",
                0.8,
                "promoted",
                tags=["json", "storage"],
                active=False,
                superseded_by="missing-sqlite-id",
            )
            store.save_persistent_memory([old_json])

            preview = MemoryHygiene(store).preview_reference_repair()

            self.assertEqual(len(preview.orphaned_references), 1)
            self.assertEqual(preview.orphaned_references[0].record_id, old_json.id)
            self.assertEqual(preview.orphaned_references[0].missing_superseded_by, "missing-sqlite-id")
            self.assertFalse(preview.orphaned_references[0].auto_repairable)

    def test_memory_reference_repair_applies_when_one_active_overlapping_decision_exists(self) -> None:
        with TemporaryDirectory() as temp_dir:
            tmp_path = Path(temp_dir)
            _, store, _ = build_test_system(tmp_path)
            active_sqlite = MemoryRecord(
                "Actually, we are changing direction: Proto-Mind should use SQLite instead of JSON.",
                "decision",
                0.95,
                "promoted",
                tags=["sqlite", "storage", "persistence"],
                id="sqlite-persistent-id",
            )
            old_json = MemoryRecord(
                "We decided Proto-Mind should use JSON-backed memory.",
                "decision",
                0.8,
                "promoted",
                tags=["json", "storage", "persistence"],
                id="json-old-id",
                active=False,
                superseded_by="missing-sqlite-id",
                superseded_at="2026-04-27T12:00:00+00:00",
                superseded_reason="Superseded by a newer explicit decision.",
            )
            store.save_persistent_memory([old_json, active_sqlite])

            preview = MemoryHygiene(store).preview_reference_repair()
            result = MemoryHygiene(store).apply_reference_repair()

            self.assertEqual(preview.repairable_count, 1)
            self.assertTrue(preview.orphaned_references[0].auto_repairable)
            self.assertEqual(preview.orphaned_references[0].candidate_record_id, active_sqlite.id)
            self.assertEqual(len(result.repaired_superseded_by_refs), 1)
            repaired_json = next(record for record in store.load_persistent_memory() if record.id == old_json.id)
            self.assertEqual(repaired_json.superseded_by, active_sqlite.id)
            self.assertEqual(repaired_json.superseded_at, "2026-04-27T12:00:00+00:00")
            self.assertEqual(repaired_json.superseded_reason, "Superseded by a newer explicit decision.")

    def test_memory_reference_repair_does_not_apply_when_multiple_candidates_exist(self) -> None:
        with TemporaryDirectory() as temp_dir:
            tmp_path = Path(temp_dir)
            _, store, _ = build_test_system(tmp_path)
            old_json = MemoryRecord(
                "We decided Proto-Mind should use JSON-backed memory.",
                "decision",
                0.8,
                "promoted",
                tags=["json", "storage"],
                active=False,
                superseded_by="missing-target-id",
            )
            active_sqlite = MemoryRecord(
                "Proto-Mind should use SQLite persistence.",
                "decision",
                0.9,
                "promoted",
                tags=["sqlite", "storage", "persistence"],
            )
            active_postgres = MemoryRecord(
                "Proto-Mind should use Postgres storage later.",
                "decision",
                0.9,
                "promoted",
                tags=["postgres", "storage", "persistence"],
            )
            store.save_persistent_memory([old_json, active_sqlite, active_postgres])

            result = MemoryHygiene(store).apply_reference_repair()

            self.assertFalse(result.repaired_superseded_by_refs)
            self.assertEqual(result.preview.repairable_count, 0)
            self.assertIn("multiple active decisions", result.preview.orphaned_references[0].reason)
            remaining_json = next(record for record in store.load_persistent_memory() if record.id == old_json.id)
            self.assertEqual(remaining_json.superseded_by, "missing-target-id")

    def test_memory_reference_repair_does_not_apply_when_no_candidate_exists(self) -> None:
        with TemporaryDirectory() as temp_dir:
            tmp_path = Path(temp_dir)
            _, store, _ = build_test_system(tmp_path)
            old_json = MemoryRecord(
                "We decided Proto-Mind should use JSON-backed memory.",
                "decision",
                0.8,
                "promoted",
                tags=["json", "storage"],
                active=False,
                superseded_by="missing-target-id",
            )
            unrelated = MemoryRecord(
                "We decided the coordinator owns orchestration.",
                "decision",
                0.9,
                "promoted",
                tags=["coordinator", "architecture"],
            )
            store.save_persistent_memory([old_json, unrelated])

            result = MemoryHygiene(store).apply_reference_repair()

            self.assertFalse(result.repaired_superseded_by_refs)
            self.assertEqual(result.preview.repairable_count, 0)
            self.assertIn("No active decision shares", result.preview.orphaned_references[0].reason)
            remaining_json = next(record for record in store.load_persistent_memory() if record.id == old_json.id)
            self.assertEqual(remaining_json.superseded_by, "missing-target-id")

    def test_memory_history_shows_repaired_id_after_orphan_reference_apply(self) -> None:
        with TemporaryDirectory() as temp_dir:
            tmp_path = Path(temp_dir)
            _, store, _ = build_test_system(tmp_path)
            active_sqlite = MemoryRecord(
                "Proto-Mind should use SQLite persistence.",
                "decision",
                0.95,
                "promoted",
                tags=["sqlite", "storage", "persistence"],
                id="sqlite-live-id",
            )
            old_json = MemoryRecord(
                "We decided Proto-Mind should use JSON-backed memory.",
                "decision",
                0.8,
                "promoted",
                tags=["json", "storage", "persistence"],
                id="json-old-id",
                active=False,
                superseded_by="missing-target-id",
            )
            store.save_persistent_memory([old_json, active_sqlite])

            MemoryHygiene(store).apply_reference_repair()
            output = format_memory_command("/memory history", store)

            self.assertIsNotNone(output)
            self.assertIn("superseded_by=sqlite-l", output)
            self.assertNotIn("missing-", output)

    def test_memory_summary_command_shows_compact_counts(self) -> None:
        with TemporaryDirectory() as temp_dir:
            tmp_path = Path(temp_dir)
            _, store, _ = build_test_system(tmp_path)
            store.save_working_memory(
                [
                    MemoryRecord("I prefer concise architectural explanations.", "preference", 0.8, "test"),
                ]
            )
            store.save_persistent_memory(
                [
                    MemoryRecord("We decided Proto-Mind should use SQLite.", "decision", 0.9, "test"),
                    MemoryRecord("We decided Proto-Mind should use JSON.", "decision", 0.8, "test", active=False),
                    MemoryRecord("The MVP should remain local-first.", "project", 0.75, "test"),
                    MemoryRecord("Retrieval explanations are useful for debugging.", "insight", 0.65, "test"),
                ]
            )

            output = format_memory_command("/memory summary", store)

            self.assertIsNotNone(output)
            self.assertIn("working: 1", output)
            self.assertIn("persistent: 4", output)
            self.assertIn("active: 4", output)
            self.assertIn("superseded: 1", output)
            self.assertIn("preferences: 1", output)
            self.assertIn("decisions: 2", output)
            self.assertIn("projects: 1", output)
            self.assertIn("insights: 1", output)

    def test_memory_decisions_command_separates_active_and_superseded(self) -> None:
        with TemporaryDirectory() as temp_dir:
            tmp_path = Path(temp_dir)
            _, store, _ = build_test_system(tmp_path)
            active = MemoryRecord("We decided Proto-Mind should use SQLite.", "decision", 0.9, "test")
            superseded = MemoryRecord(
                "We decided Proto-Mind should use JSON.",
                "decision",
                0.8,
                "test",
                active=False,
                superseded_by=active.id,
                superseded_reason="Superseded by SQLite.",
            )
            store.save_persistent_memory([superseded, active])

            output = format_memory_command("/memory decisions", store)

            self.assertIsNotNone(output)
            active_section, historical_section = output.split("Superseded/historical decisions:")
            self.assertIn("SQLite", active_section)
            self.assertNotIn("JSON", active_section)
            self.assertIn("JSON", historical_section)
            self.assertIn(f"superseded_by={active.id[:8]}", historical_section)
            self.assertIn("Superseded by SQLite.", historical_section)

    def test_memory_preferences_command_shows_active_preferences(self) -> None:
        with TemporaryDirectory() as temp_dir:
            tmp_path = Path(temp_dir)
            _, store, _ = build_test_system(tmp_path)
            store.save_persistent_memory(
                [
                    MemoryRecord("I prefer concise architectural explanations.", "preference", 0.8, "test"),
                    MemoryRecord("I used to prefer verbose answers.", "preference", 0.4, "test", active=False),
                ]
            )

            output = format_memory_command("/memory preferences", store)

            self.assertIsNotNone(output)
            self.assertIn("Active preference memories:", output)
            self.assertIn("concise architectural explanations", output)
            self.assertNotIn("verbose answers", output)

    def test_memory_history_command_shows_superseded_metadata(self) -> None:
        with TemporaryDirectory() as temp_dir:
            tmp_path = Path(temp_dir)
            _, store, _ = build_test_system(tmp_path)
            superseded = MemoryRecord(
                "We decided Proto-Mind should use JSON.",
                "decision",
                0.8,
                "test",
                active=False,
                superseded_by="sqlite-decision-id",
                superseded_at="2026-04-27T12:00:00+00:00",
                superseded_reason="Superseded by a newer explicit decision.",
            )
            store.save_persistent_memory([superseded])

            output = format_memory_command("/memory history", store)

            self.assertIsNotNone(output)
            self.assertIn("Superseded/inactive memory history:", output)
            self.assertIn("JSON", output)
            self.assertIn("superseded_by=sqlite-d", output)
            self.assertIn("superseded_at=2026-04-27T12:00:00+00:00", output)
            self.assertIn("Superseded by a newer explicit decision.", output)

    def test_memory_command_dispatch_keeps_hygiene_commands_separate(self) -> None:
        with TemporaryDirectory() as temp_dir:
            tmp_path = Path(temp_dir)
            _, store, _ = build_test_system(tmp_path)

            self.assertIsNone(format_memory_command("/memory hygiene", store))
            self.assertIsNone(format_memory_command("/memory hygiene-preview", store))
            self.assertIsNone(format_memory_command("/memory cleanup-preview", store))
            self.assertIsNone(format_memory_command("/memory cleanup-apply", store))

    def test_memory_card_status_reports_warn_baseline_and_safe_generation(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            with patch("proto_mind.memory_card_layer.OperatorMemoryCard.read_state", return_value=_memory_card_state()):
                output = format_memory_card_command("/memory-card status", project_root=project_root, memory_store=store)

            self.assertIn("Operator Memory Card Status", output)
            self.assertIn("Status: WARN", output)
            self.assertIn("command_registry: commands=387 categories=41", output)
            self.assertIn("context_injection: disabled", output)
            self.assertIn("closure_readiness: WARN", output)
            self.assertIn("baseline_readiness: WARN", output)
            self.assertIn("acceptance_readiness: WARN", output)
            self.assertIn("accepted_known_warnings: 12", output)
            self.assertIn("unknown_warnings: 0", output)
            self.assertIn("blockers: 0", output)
            self.assertIn("memory_card_generation_safe: true", output)

    def test_memory_card_status_blocks_unknown_warnings_or_blockers(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            with patch(
                "proto_mind.memory_card_layer.OperatorMemoryCard.read_state",
                return_value=_memory_card_state(unknown=True, blockers=1),
            ):
                output = format_memory_card_command("/memory-card status", project_root=project_root, memory_store=store)

            self.assertIn("Status: BLOCKED", output)
            self.assertIn("unknown_warnings: 1", output)
            self.assertIn("blockers: 1", output)
            self.assertIn("memory_card_generation_safe: false", output)

    def test_memory_card_short_is_compact_and_complete(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            with patch("proto_mind.memory_card_layer.OperatorMemoryCard.read_state", return_value=_memory_card_state()):
                output = format_memory_card_command("/memory-card short", project_root=project_root, memory_store=store)

            self.assertGreaterEqual(len(output.splitlines()), 10)
            self.assertLessEqual(len(output.splitlines()), 20)
            self.assertIn("Proto-Mind Operator Memory Card (Short)", output)
            self.assertIn(f"Project: {project_root}", output)
            self.assertIn("Registry: 387 commands / 41 categories", output)
            self.assertIn("Tests: 671 tests OK", output)
            self.assertIn("Context Injection: disabled", output)
            self.assertIn("accepted=12, unknown=0, blockers=0", output)
            self.assertIn("Operating phase: post-acceptance continuity", output)
            self.assertIn("/runner-mvp design", output)
            self.assertIn("Rule 0:", output)

    def test_memory_card_short_prioritizes_unknown_warnings(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            with patch(
                "proto_mind.memory_card_layer.OperatorMemoryCard.read_state",
                return_value=_memory_card_state(unknown=True),
            ):
                output = format_memory_card_command("/memory-card short", project_root=project_root, memory_store=store)

            self.assertIn("Inspect unknown warnings", output)
            self.assertIn("Manual command: /warnings unknown", output)

    def test_memory_card_full_contains_identity_layers_safety_and_limits(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            with patch("proto_mind.memory_card_layer.OperatorMemoryCard.read_state", return_value=_memory_card_state()):
                output = format_memory_card_command("/memory-card full", project_root=project_root, memory_store=store)

            self.assertIn("Proto-Mind Operator Memory Card (Full)", output)
            self.assertIn("Project identity:", output)
            self.assertIn("Accepted operating-loop layers:", output)
            self.assertIn("Available command families:", output)
            self.assertIn("/memory-card", output)
            self.assertIn("Safety invariants:", output)
            self.assertIn("Warning baseline:", output)
            self.assertIn("Snapshot / diff:", output)
            self.assertIn("Verification commands:", output)
            self.assertIn("Current limitations:", output)
            self.assertIn("/runner-mvp design", output)
            self.assertIn("no card, memory, store, export, context setting, session log, or command", output)

    def test_memory_card_codex_is_reusable_read_only_header(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            with patch("proto_mind.memory_card_layer.OperatorMemoryCard.read_state", return_value=_memory_card_state()):
                output = format_memory_card_command("/memory-card codex", project_root=project_root, memory_store=store)

            self.assertIn("Proto-Mind Codex Context Header", output)
            self.assertIn("Rule 0: before changes", output)
            self.assertIn("Current baseline:", output)
            self.assertIn("Registry/tests: 387 commands, 41 categories", output)
            self.assertIn("accepted=12, unknown=0, blockers=0", output)
            self.assertIn("Context Injection: disabled", output)
            self.assertIn("do not write proto_mind/data/* or proto_mind/exports/*", output)
            self.assertIn("Verification:", output)
            self.assertIn("Final report:", output)
            self.assertIn("not authorization to execute commands", output)

    def test_memory_card_doctor_checks_helpers_ledger_context_and_safety(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            store.save_persistent_memory([])
            _create_healthy_export_dirs(project_root)
            _write_milestone_fixture(project_root)
            with patch("proto_mind.memory_card_layer.OperatorMemoryCard.read_state", return_value=_memory_card_state()):
                output = format_memory_card_command("/memory-card doctor", project_root=project_root, memory_store=store)

            self.assertIn("Operator Memory Card Doctor", output)
            self.assertIn("Status: OK", output)
            self.assertIn("All memory-card commands are registered", output)
            self.assertIn("read-only with mutates=none", output)
            self.assertIn("Closure, Baseline, Acceptance, Focus, Pre-Change, Agenda, Session, Milestone, Warning, Export, and Snapshot helpers are reachable", output)
            self.assertIn("Accepted-known warnings ledger is reachable", output)
            self.assertIn("Warning state is computable", output)
            self.assertIn("Context Injection is disabled", output)
            self.assertIn("No execution, persistence, clipboard, snapshot, backup, repair, cleanup, migration, deletion, move, compression, or external action is exposed", output)

    def test_memory_card_doctor_warns_without_changing_enabled_context(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            store.save_persistent_memory([])
            _create_healthy_export_dirs(project_root)
            _write_milestone_fixture(project_root)
            format_context_command("/context injection enable", project_root=project_root)
            settings_path = project_root / "proto_mind" / "data" / "context_injection.json"
            before = settings_path.read_bytes()
            with patch(
                "proto_mind.memory_card_layer.OperatorMemoryCard.read_state",
                return_value=_memory_card_state(context_state="enabled"),
            ):
                output = format_memory_card_command("/memory-card doctor", project_root=project_root, memory_store=store)

            self.assertIn("Status: WARN", output)
            self.assertIn("Context Injection is explicitly enabled", output)
            self.assertEqual(settings_path.read_bytes(), before)
            self.assertTrue(json.loads(settings_path.read_text(encoding="utf-8"))["enabled"])

    def test_memory_card_commands_are_read_only_through_shared_handler(self) -> None:
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
                    "/memory-card status",
                    "/memory-card short",
                    "/memory-card full",
                    "/memory-card codex",
                    "/memory-card doctor",
                )
            ]

            self.assertIn("Operator Memory Card Status", outputs[0])
            self.assertIn("Operator Memory Card (Short)", outputs[1])
            self.assertIn("Operator Memory Card (Full)", outputs[2])
            self.assertIn("Codex Context Header", outputs[3])
            self.assertIn("Operator Memory Card Doctor", outputs[4])
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

    def test_memory_record_serialization_omits_empty_provenance(self) -> None:
        record = MemoryRecord(
            id="mem_legacy_shape",
            content="Legacy-compatible memory shape.",
            type="project_fact",
            importance=0.7,
            source="test",
        )
        payload = record.to_dict()
        round_trip = MemoryRecord.from_dict(payload)

        self.assertNotIn("provenance", payload)
        self.assertIsNone(round_trip.provenance)
        self.assertEqual(round_trip.to_dict(), payload)

    def test_memory_why_verifies_learning_provenance_after_store_restart(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _, store, pilot, bridge, _, skills, proposal = build_test_learning_apply(root)
            _, receipt = apply_test_learning_proposal(
                store,
                pilot,
                bridge,
                skills,
                proposal,
            )
            restarted_store = MemoryStore(store.working_path, store.persistent_path)
            before = restarted_store.persistent_path.read_bytes()
            output = format_memory_command(
                f"/memory why {receipt.created_record_id}",
                restarted_store,
            )
            doctor = format_memory_command("/memory doctor", restarted_store)
            after = restarted_store.persistent_path.read_bytes()

        self.assertIn("Status: VERIFIED", output)
        self.assertIn(f"proposal_id: {proposal.id}", output)
        self.assertIn(f"candidate_id: {proposal.candidate_id}", output)
        self.assertIn("survives process restart", output)
        self.assertIn("Read-only explanation", output)
        self.assertIn("Status: OK", doctor)
        self.assertIn("durable provenance records: 1", doctor)
        self.assertEqual(before, after)

    def test_memory_why_does_not_invent_provenance_for_legacy_record(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = MemoryStore(root / "working.json", root / "persistent.json")
            store.save_persistent_memory(
                [
                    MemoryRecord(
                        id="mem_without_provenance",
                        content="Operator supplied this fact.",
                        type="explicit",
                        importance=1.0,
                        source="operator",
                    )
                ]
            )
            before = store.persistent_path.read_bytes()
            output = format_memory_command("/memory why mem_without_provenance", store)
            after = store.persistent_path.read_bytes()

        self.assertIn("Status: UNAVAILABLE", output)
        self.assertIn("will not invent a source chain", output)
        self.assertEqual(before, after)

    def test_memory_why_handles_usage_and_unknown_id_cleanly(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = MemoryStore(root / "working.json", root / "persistent.json")
            before = store.persistent_path.read_bytes()
            usage = format_memory_command("/memory why", store)
            missing = format_memory_command("/memory why mem_missing", store)
            after = store.persistent_path.read_bytes()

        self.assertEqual(usage, "Usage: /memory why <id>")
        self.assertIn("Status: NOT FOUND", missing)
        self.assertEqual(before, after)

    def test_memory_why_and_doctor_detect_payload_tamper(self) -> None:
        with TemporaryDirectory() as temp_dir:
            _, store, pilot, bridge, _, skills, proposal = build_test_learning_apply(
                Path(temp_dir)
            )
            _, receipt = apply_test_learning_proposal(
                store,
                pilot,
                bridge,
                skills,
                proposal,
            )
            records = store.load_persistent_memory()
            created = next(record for record in records if record.id == receipt.created_record_id)
            created.content = "Tampered lesson content."
            store.save_persistent_memory(records)
            why = format_memory_command(f"/memory why {created.id}", store)
            doctor = format_memory_command("/memory doctor", store)

        self.assertIn("Status: ERROR", why)
        self.assertIn("proposal payload hash", why)
        self.assertIn("Status: ERROR", doctor)
        self.assertIn("Invalid embedded memory provenance", doctor)

    def test_memory_why_detects_provenance_hash_tamper(self) -> None:
        with TemporaryDirectory() as temp_dir:
            _, store, pilot, bridge, _, skills, proposal = build_test_learning_apply(
                Path(temp_dir)
            )
            _, receipt = apply_test_learning_proposal(
                store,
                pilot,
                bridge,
                skills,
                proposal,
            )
            records = store.load_persistent_memory()
            created = next(record for record in records if record.id == receipt.created_record_id)
            created.provenance["provenance_hash"] = "0" * 64
            store.save_persistent_memory(records)
            output = format_memory_command(f"/memory why {created.id}", store)

        self.assertIn("Status: ERROR", output)
        self.assertIn("Provenance hash does not match", output)

    def test_memory_forget_refuses_unprovenanced_non_explicit_record(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = MemoryStore(root / "working.json", root / "persistent.json")
            store.save_persistent_memory(
                [MemoryRecord("Unprovenanced lesson.", "lesson", 0.7, "legacy", id="legacy_lesson")]
            )
            before = store.persistent_path.read_bytes()
            output = format_memory_command("/memory forget legacy_lesson", store)
            after = store.persistent_path.read_bytes()

        self.assertIn("Explicit memory not found", output)
        self.assertEqual(before, after)

    def test_memory_why_registry_policy_is_read_only(self) -> None:
        registry = {entry.prefix: entry for entry in COMMAND_REGISTRY}
        spec = registry["/memory why"]

        self.assertTrue(spec.read_only)
        self.assertEqual(spec.mutates, "none")
        self.assertEqual(spec.risk, "low")
        self.assertEqual(classify_command("/memory why mem_learn_123").policy_class, "auto_allowed")
        self.assertEqual(len(COMMAND_REGISTRY), 387)
        self.assertEqual(len({entry.category for entry in COMMAND_REGISTRY}), 41)
        self.assertEqual(command_registry_doctor()["status"], "OK")
        self.assertEqual(action_policy_doctor()["status"], "OK")
