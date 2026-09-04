"""Core flow checks: proto."""
from __future__ import annotations

import unittest
from proto_mind.tests.flow_fixtures import (
    MemoryRecord,
    Path,
    SessionOperatorLogger,
    TaskQueue,
    TemporaryDirectory,
    _executed_action,
    _id_from_output,
    _single_action_record,
    _snapshot_diff_fixture,
    build_test_system,
    format_action_queue_command,
    format_context_command,
    format_data_command,
    format_goal_command,
    format_identity_command,
    format_proto_command,
    format_task_command,
    json,
    os,
    process_interactive_input,
)


class ProtoFlowTests(unittest.TestCase):
    def test_proto_status_shows_focus_memory_context_and_health(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            coordinator, store, _ = build_test_system(project_root / "proto_mind")
            store.save_persistent_memory(
                [MemoryRecord("Proto status memory", "explicit", 1.0, "operator")]
            )
            format_identity_command("/identity set operator_name Operator", project_root=project_root)
            goal_output = format_goal_command("/goals add Proto overview --priority high", project_root=project_root)
            goal_id = next(line.strip().split(" — ")[0] for line in goal_output.splitlines() if line.strip().startswith("goal_"))
            format_goal_command(f"/goals focus {goal_id}", project_root=project_root)
            format_task_command(f"/tasks add Inspect system --priority high --goal {goal_id}", project_root=project_root)
            format_context_command("/context injection enable --max-chars 2000", project_root=project_root)

            output = format_proto_command("/proto status", project_root=project_root, memory_store=store)

            self.assertIn("Proto-Mind System Status", output)
            self.assertIn("operator: Operator", output)
            self.assertIn(goal_id, output)
            self.assertIn("open high-priority tasks: 1", output)
            self.assertIn("active explicit memories: 1", output)
            self.assertIn("context injection: enabled", output)
            self.assertIn("/data doctor:", output)
            self.assertIn("/action run-audit:", output)
            self.assertIn("Read-only overview", output)

    def test_proto_doctor_aggregates_major_doctors(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            store.save_persistent_memory([])

            output = format_proto_command("/proto doctor", project_root=project_root, memory_store=store)

            self.assertIn("Proto-Mind System Doctor", output)
            self.assertRegex(output, r"Status: (OK|WARN|ERROR)")
            self.assertIn("Doctors checked: 12", output)
            for command in (
                "/data doctor",
                "/data refs-doctor",
                "/loop doctor",
                "/memory doctor",
                "/consolidation queue-doctor",
                "/natural doctor",
                "/commands doctor",
                "/policy doctor",
                "/action doctor",
                "/action queue-doctor",
                "/action readiness-doctor",
                "/action run-audit",
            ):
                self.assertIn(f"- {command}:", output)
            self.assertIn("no target commands or repairs were executed", output)

    def test_proto_doctor_reports_legacy_action_receipt_warning(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            store.save_persistent_memory([])
            _executed_action(project_root)
            queue_path = project_root / "proto_mind" / "data" / "action_queue.jsonl"
            record = _single_action_record(project_root)
            record["run_receipt"]["version"] = 1
            for field in ("run_id", "executed_command_count", "receipt_hash"):
                record.pop(field, None)
                record["run_receipt"].pop(field, None)
            record["run_receipt"]["commands"][0].pop("description", None)
            record["run_receipt"]["commands"][0].pop("risk", None)
            queue_path.write_text(json.dumps(record) + "\n", encoding="utf-8")

            output = format_proto_command("/proto doctor", project_root=project_root, memory_store=store)

            self.assertIn("- /action run-audit: WARN", output)
            self.assertIn("missing run_id", output)

    def test_proto_next_aggregates_signals_without_executing_suggestions(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            store.save_persistent_memory([])
            goal_output = format_goal_command("/goals add Next goal", project_root=project_root)
            goal_id = next(line.strip().split(" — ")[0] for line in goal_output.splitlines() if line.strip().startswith("goal_"))
            format_goal_command(f"/goals focus {goal_id}", project_root=project_root)
            task_output = format_task_command(f"/tasks add Next task --priority high --goal {goal_id}", project_root=project_root)
            task_id = next(line.strip().split(" — ")[0] for line in task_output.splitlines() if line.strip().startswith("task_"))
            format_action_queue_command("/action propose /data doctor", project_root=project_root)

            output = format_proto_command("/proto next", project_root=project_root, memory_store=store)

            self.assertIn("Proto-Mind Next", output)
            self.assertIn(goal_id, output)
            self.assertIn(task_id, output)
            self.assertIn("proposed actions: 1", output)
            self.assertIn("consolidation candidates:", output)
            self.assertIn("/action proposals", output)
            self.assertIn("suggested commands were not executed", output)
            self.assertEqual(TaskQueue.from_project_root(project_root)._read_state().records[0]["status"], "open")

    def test_proto_commands_are_read_only_through_shared_handler(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            coordinator, store, _ = build_test_system(project_root / "proto_mind")
            store.save_persistent_memory([])
            logger = SessionOperatorLogger.from_project_root(project_root)
            coordinator.session_logger = logger
            format_context_command("/context injection enable", project_root=project_root)
            data_dir = project_root / "proto_mind" / "data"
            before = {path.name: path.read_bytes() for path in data_dir.glob("*") if path.is_file()}

            outputs = [
                process_interactive_input(
                    command,
                    coordinator=coordinator,
                    session_logger=logger,
                    project_root=project_root,
                )
                for command in (
                    "/proto status",
                    "/proto doctor",
                    "/proto next",
                    "/proto warnings",
                    "/proto warnings-explain",
                    "/proto cleanup-preview",
                    "/proto snapshot",
                    "/proto snapshot-status",
                    "/proto snapshot-list",
                    "/proto snapshot-diff-latest",
                    "/proto snapshot-diff-status",
                )
            ]
            after = {path.name: path.read_bytes() for path in data_dir.glob("*") if path.is_file()}

            self.assertIn("Proto-Mind System Status", outputs[0])
            self.assertIn("Proto-Mind System Doctor", outputs[1])
            self.assertIn("Proto-Mind Next", outputs[2])
            self.assertIn("Proto-Mind Warning Triage", outputs[3])
            self.assertIn("Proto-Mind Warning Explanations", outputs[4])
            self.assertIn("Proto-Mind Cleanup Preview", outputs[5])
            self.assertIn("Proto-Mind Snapshot", outputs[6])
            self.assertIn("Proto-Mind Snapshot Export Status", outputs[7])
            self.assertIn("Proto-Mind Snapshot List", outputs[8])
            self.assertIn("Need at least 2 snapshot JSON exports", outputs[9])
            self.assertIn("Proto-Mind Snapshot Diff Export Status", outputs[10])
            self.assertEqual(after, before)
            self.assertEqual(logger.status().entry_count, 0)

    def test_proto_warnings_classifies_legacy_receipt_and_dangling_reference(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            store.save_persistent_memory([])
            action_id = _executed_action(project_root)
            action_path = project_root / "proto_mind" / "data" / "action_queue.jsonl"
            action_record = _single_action_record(project_root)
            action_record["run_receipt"]["version"] = 1
            for field in ("run_id", "executed_command_count", "receipt_hash"):
                action_record.pop(field, None)
                action_record["run_receipt"].pop(field, None)
            action_path.write_text(json.dumps(action_record) + "\n", encoding="utf-8")
            consolidation_path = project_root / "proto_mind" / "data" / "consolidation_queue.jsonl"
            consolidation_path.write_text(
                json.dumps(
                    {
                        "id": "cq_legacy_reference",
                        "created_at": "2026-01-01T00:00:00+00:00",
                        "updated_at": "2026-01-01T00:00:00+00:00",
                        "status": "applied",
                        "kind": "memory",
                        "source": "operator",
                        "title": "Legacy apply",
                        "suggested_command": "/memory remember legacy",
                        "rationale": "fixture",
                        "tags": [],
                        "applied_kind": "memory",
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            output = format_proto_command("/proto warnings", project_root=project_root, memory_store=store)

            self.assertIn("Proto-Mind Warning Triage", output)
            self.assertIn("category: legacy", output)
            self.assertIn("category: dangling_ref", output)
            self.assertIn(action_id, output)
            self.assertIn("cq_legacy_reference", output)
            self.assertIn("safe_to_ignore_temporarily: yes", output)
            self.assertIn("warnings were not suppressed", output)

    def test_proto_warnings_explain_covers_known_warning_types(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")

            output = format_proto_command("/proto warnings-explain", project_root=project_root, memory_store=store)

            self.assertIn("legacy action receipt", output)
            self.assertIn("old dangling consolidation reference", output)
            self.assertIn("approved but unconfirmed action proposal", output)
            self.assertIn("policy drift", output)
            self.assertIn("missing store", output)
            self.assertIn("malformed json/jsonl", output)
            self.assertIn("/action run-receipt <action_id>", output)
            self.assertIn("/consolidation queue-inspect <queue_id>", output)
            self.assertIn("no commands were executed", output.lower())

    def test_proto_cleanup_preview_exports_first_and_does_not_mutate_queues(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            store.save_persistent_memory([])
            proposed = format_action_queue_command("/action propose /data doctor", project_root=project_root)
            action_id = _id_from_output(proposed, "id:")
            format_action_queue_command(f"/action approve {action_id}", project_root=project_root)
            consolidation_path = project_root / "proto_mind" / "data" / "consolidation_queue.jsonl"
            consolidation_path.write_text(
                json.dumps(
                    {
                        "id": "cq_cleanup_reference",
                        "created_at": "2026-01-01T00:00:00+00:00",
                        "updated_at": "2026-01-01T00:00:00+00:00",
                        "status": "applied",
                        "kind": "memory",
                        "source": "operator",
                        "title": "Cleanup reference",
                        "suggested_command": "/memory remember cleanup",
                        "rationale": "fixture",
                        "tags": [],
                        "applied_kind": "memory",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            action_path = project_root / "proto_mind" / "data" / "action_queue.jsonl"
            before_action = action_path.read_bytes()
            before_consolidation = consolidation_path.read_bytes()

            output = format_proto_command("/proto cleanup-preview", project_root=project_root, memory_store=store)

            self.assertLess(output.index("/action queue-export"), output.index(f"/action archive {action_id}"))
            self.assertLess(
                output.index("/consolidation queue-export"),
                output.index("/consolidation queue-archive cq_cleanup_reference"),
            )
            self.assertIn(f"/action inspect {action_id}", output)
            self.assertIn("/consolidation queue-inspect cq_cleanup_reference", output)
            self.assertIn("suggestions only and were not executed", output)
            self.assertEqual(action_path.read_bytes(), before_action)
            self.assertEqual(consolidation_path.read_bytes(), before_consolidation)

    def test_proto_snapshot_status_handles_missing_export_directory(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            export_dir = project_root / "proto_mind" / "exports" / "proto_snapshots"

            output = format_proto_command("/proto snapshot-status", project_root=project_root, memory_store=store)

            self.assertIn("Proto-Mind Snapshot Export Status", output)
            self.assertIn(f"export_dir: {export_dir}", output)
            self.assertIn("exists: False", output)
            self.assertIn("snapshot_sets: 0", output)
            self.assertIn("export_files: 0", output)
            self.assertFalse(export_dir.exists())

    def test_proto_snapshot_includes_structured_state_and_is_read_only(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            store.save_persistent_memory([MemoryRecord("Snapshot memory", "explicit", 1.0, "operator")])
            format_context_command("/context injection enable --max-chars 1800", project_root=project_root)
            format_action_queue_command("/action propose /data doctor", project_root=project_root)
            consolidation_path = project_root / "proto_mind" / "data" / "consolidation_queue.jsonl"
            consolidation_path.write_text(
                json.dumps(
                    {
                        "id": "cq_snapshot_reference",
                        "created_at": "2026-01-01T00:00:00+00:00",
                        "updated_at": "2026-01-01T00:00:00+00:00",
                        "status": "applied",
                        "kind": "memory",
                        "source": "operator",
                        "title": "Snapshot reference",
                        "suggested_command": "/memory remember snapshot",
                        "rationale": "fixture",
                        "tags": [],
                        "applied_kind": "memory",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            data_dir = project_root / "proto_mind" / "data"
            before = {path.name: path.read_bytes() for path in data_dir.glob("*") if path.is_file()}

            output = format_proto_command("/proto snapshot", project_root=project_root, memory_store=store)

            self.assertIn("Proto-Mind Snapshot", output)
            self.assertIn("## Identity", output)
            self.assertIn("## Doctor Summary", output)
            self.assertIn("## Warning Summary", output)
            self.assertIn("data_integrity", output)
            self.assertIn("dangling_ref", output)
            self.assertIn("## Action Queue", output)
            self.assertIn("- Total: 1", output)
            self.assertIn("Context injection: enabled", output)
            self.assertIn("## Cleanup Preview", output)
            self.assertIn("no_mutation: true", output)
            after = {path.name: path.read_bytes() for path in data_dir.glob("*") if path.is_file()}
            self.assertEqual(after, before)
            self.assertFalse((project_root / "proto_mind" / "exports" / "proto_snapshots").exists())

    def test_proto_snapshot_export_creates_valid_files_without_core_mutation(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            store.save_persistent_memory([])
            format_action_queue_command("/action propose /data doctor", project_root=project_root)
            consolidation_path = project_root / "proto_mind" / "data" / "consolidation_queue.jsonl"
            consolidation_path.write_text("", encoding="utf-8")
            action_path = project_root / "proto_mind" / "data" / "action_queue.jsonl"
            context_path = project_root / "proto_mind" / "data" / "context_injection.json"
            before_action = action_path.read_bytes()
            before_consolidation = consolidation_path.read_bytes()

            output = format_proto_command("/proto snapshot-export", project_root=project_root, memory_store=store)
            export_dir = project_root / "proto_mind" / "exports" / "proto_snapshots"
            markdown_files = list(export_dir.glob("proto_snapshot_*.md"))
            json_files = list(export_dir.glob("proto_snapshot_*.json"))
            payload = json.loads(json_files[0].read_text(encoding="utf-8"))
            markdown = markdown_files[0].read_text(encoding="utf-8")
            status = format_proto_command("/proto snapshot-status", project_root=project_root, memory_store=store)
            inventory = format_data_command("/data inventory", project_root=project_root)

            self.assertIn("Proto-Mind Snapshot Export", output)
            self.assertEqual(len(markdown_files), 1)
            self.assertEqual(len(json_files), 1)
            self.assertTrue(payload["no_mutation"])
            for key in (
                "generated_at",
                "status",
                "doctor_summary",
                "warnings",
                "cleanup_preview",
                "action_summary",
                "consolidation_summary",
                "next_summary",
                "source_notes",
            ):
                self.assertIn(key, payload)
            self.assertIn("# Proto-Mind Snapshot", markdown)
            self.assertIn("## Doctor Summary", markdown)
            self.assertIn("## Mutation Policy", markdown)
            self.assertIn("snapshot_sets: 1", status)
            self.assertIn("export_files: 2", status)
            self.assertIn("proto_snapshots:", inventory)
            self.assertIn("exists=True", next(line for line in inventory.splitlines() if "proto_snapshots:" in line))
            self.assertEqual(action_path.read_bytes(), before_action)
            self.assertEqual(consolidation_path.read_bytes(), before_consolidation)
            self.assertFalse(context_path.exists())

    def test_proto_snapshot_list_handles_missing_dir_and_lists_snapshot(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")

            empty = format_proto_command("/proto snapshot-list", project_root=project_root, memory_store=store)
            export_dir = project_root / "proto_mind" / "exports" / "proto_snapshots"
            export_dir.mkdir(parents=True)
            snapshot_path = export_dir / "proto_snapshot_fixture.json"
            snapshot_path.write_text(
                json.dumps(
                    {
                        "generated_at": "2026-06-30T10:00:00+00:00",
                        "status": "WARN",
                        "warning_summary": {"count": 2, "categories": {"legacy": 1, "dangling_ref": 1}},
                    }
                ),
                encoding="utf-8",
            )
            before = snapshot_path.read_bytes()

            listed = format_proto_command("/proto snapshot-list", project_root=project_root, memory_store=store)

            self.assertIn("json_snapshots: 0", empty)
            self.assertIn("Snapshots:\n- none", empty)
            self.assertIn("proto_snapshot_fixture.json", listed)
            self.assertIn("generated_at=2026-06-30T10:00:00+00:00", listed)
            self.assertIn("status=WARN", listed)
            self.assertIn("warnings=2", listed)
            self.assertIn("dangling_ref=1", listed)
            self.assertEqual(snapshot_path.read_bytes(), before)

    def test_proto_snapshot_diff_handles_missing_files_cleanly(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")

            output = format_proto_command(
                "/proto snapshot-diff missing-old.json missing-new.json",
                project_root=project_root,
                memory_store=store,
            )

            self.assertIn("Proto-Mind Snapshot Diff", output)
            self.assertIn("Status: ERROR", output)
            self.assertIn("Snapshot JSON file not found", output)
            self.assertIn("No snapshot files were modified", output)

    def test_proto_snapshot_diff_detects_structural_changes(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            export_dir = project_root / "proto_mind" / "exports" / "proto_snapshots"
            export_dir.mkdir(parents=True)
            old_path = export_dir / "proto_snapshot_old.json"
            new_path = export_dir / "proto_snapshot_new.json"
            old = _snapshot_diff_fixture(status="OK", enabled=False, warning_count=1, legacy_count=1)
            new = _snapshot_diff_fixture(status="WARN", enabled=True, warning_count=3, legacy_count=2)
            new["doctor_summary"]["doctors"]["/data doctor"] = "WARN"
            new["action_summary"]["total"] = 2
            new["consolidation_summary"]["candidate_count"] = 4
            new["memory_summary"]["active"] = 2
            new["task_summary"]["open_total"] = 1
            new["focus"]["focused_goal"] = {"id": "goal_new", "status": "active"}
            new["registry_summary"]["registered_commands"] = 205
            old_path.write_text(json.dumps(old), encoding="utf-8")
            new_path.write_text(json.dumps(new), encoding="utf-8")
            before_old = old_path.read_bytes()
            before_new = new_path.read_bytes()

            output = format_proto_command(
                f"/proto snapshot-diff {old_path.name} {new_path}",
                project_root=project_root,
                memory_store=store,
            )

            self.assertIn("Result: CHANGED", output)
            self.assertIn("status: OK -> WARN (changed)", output)
            self.assertIn("doctor./data doctor: OK -> WARN", output)
            self.assertIn("warning_count: 1 -> 3", output)
            self.assertIn("category.legacy: 1 -> 2", output)
            self.assertIn("enabled: false -> true", output)
            self.assertIn("memory.active: 1 -> 2", output)
            self.assertIn("tasks.open_total: 0 -> 1", output)
            self.assertIn("focused_goal.id: missing -> goal_new", output)
            self.assertIn("registered_commands: 202 -> 205", output)
            self.assertEqual(old_path.read_bytes(), before_old)
            self.assertEqual(new_path.read_bytes(), before_new)

    def test_proto_snapshot_diff_latest_requires_two_snapshots(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            export_dir = project_root / "proto_mind" / "exports" / "proto_snapshots"
            export_dir.mkdir(parents=True)
            (export_dir / "proto_snapshot_only.json").write_text(
                json.dumps(_snapshot_diff_fixture()), encoding="utf-8"
            )

            output = format_proto_command("/proto snapshot-diff-latest", project_root=project_root, memory_store=store)

            self.assertIn("Available JSON snapshots: 1", output)
            self.assertIn("Need at least 2", output)
            self.assertIn("No snapshot files were modified", output)

    def test_proto_snapshot_diff_latest_compares_newest_two_without_mutation(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            export_dir = project_root / "proto_mind" / "exports" / "proto_snapshots"
            export_dir.mkdir(parents=True)
            old_path = export_dir / "proto_snapshot_oldest.json"
            new_path = export_dir / "proto_snapshot_newest.json"
            old_path.write_text(json.dumps(_snapshot_diff_fixture(status="OK")), encoding="utf-8")
            new_path.write_text(json.dumps(_snapshot_diff_fixture(status="WARN")), encoding="utf-8")
            os.utime(old_path, (100, 100))
            os.utime(new_path, (200, 200))
            before_old = old_path.read_bytes()
            before_new = new_path.read_bytes()

            output = format_proto_command("/proto snapshot-diff-latest", project_root=project_root, memory_store=store)

            self.assertIn(f"Old: {old_path.resolve()}", output)
            self.assertIn(f"New: {new_path.resolve()}", output)
            self.assertIn("status: OK -> WARN", output)
            self.assertEqual(old_path.read_bytes(), before_old)
            self.assertEqual(new_path.read_bytes(), before_new)

    def test_proto_snapshot_diff_status_handles_missing_export_directory(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            export_dir = project_root / "proto_mind" / "exports" / "proto_snapshot_diffs"

            output = format_proto_command("/proto snapshot-diff-status", project_root=project_root, memory_store=store)

            self.assertIn("Proto-Mind Snapshot Diff Export Status", output)
            self.assertIn(f"export_dir: {export_dir}", output)
            self.assertIn("exists: False", output)
            self.assertIn("diff_export_sets: 0", output)
            self.assertIn("export_files: 0", output)
            self.assertFalse(export_dir.exists())

    def test_proto_snapshot_diff_export_missing_files_creates_nothing(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            export_dir = project_root / "proto_mind" / "exports" / "proto_snapshot_diffs"

            output = format_proto_command(
                "/proto snapshot-diff-export missing-old.json missing-new.json",
                project_root=project_root,
                memory_store=store,
            )

            self.assertIn("Proto-Mind Snapshot Diff Export", output)
            self.assertIn("Status: ERROR", output)
            self.assertIn("Snapshot JSON file not found", output)
            self.assertIn("No diff export files were created", output)
            self.assertFalse(export_dir.exists())

    def test_proto_snapshot_diff_export_creates_valid_no_change_files_without_core_mutation(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            store.save_persistent_memory([])
            format_action_queue_command("/action propose /data doctor", project_root=project_root)
            format_context_command("/context injection enable", project_root=project_root)
            consolidation_path = project_root / "proto_mind" / "data" / "consolidation_queue.jsonl"
            consolidation_path.write_text("", encoding="utf-8")
            snapshot_dir = project_root / "proto_mind" / "exports" / "proto_snapshots"
            snapshot_dir.mkdir(parents=True)
            old_path = snapshot_dir / "proto_snapshot_export_old.json"
            new_path = snapshot_dir / "proto_snapshot_export_new.json"
            old = _snapshot_diff_fixture(status="WARN", warning_count=1, legacy_count=1)
            new = json.loads(json.dumps(old))
            new["generated_at"] = "2026-06-30T12:00:00+00:00"
            old_path.write_text(json.dumps(old), encoding="utf-8")
            new_path.write_text(json.dumps(new), encoding="utf-8")
            data_dir = project_root / "proto_mind" / "data"
            before_core = {path.name: path.read_bytes() for path in data_dir.glob("*") if path.is_file()}
            before_old = old_path.read_bytes()
            before_new = new_path.read_bytes()

            output = format_proto_command(
                f"/proto snapshot-diff-export {old_path.name} {new_path.name}",
                project_root=project_root,
                memory_store=store,
            )
            diff_dir = project_root / "proto_mind" / "exports" / "proto_snapshot_diffs"
            markdown_files = list(diff_dir.glob("proto_snapshot_diff_*.md"))
            json_files = list(diff_dir.glob("proto_snapshot_diff_*.json"))
            payload = json.loads(json_files[0].read_text(encoding="utf-8"))
            markdown = markdown_files[0].read_text(encoding="utf-8")
            status = format_proto_command("/proto snapshot-diff-status", project_root=project_root, memory_store=store)
            inventory = format_data_command("/data inventory", project_root=project_root)

            self.assertIn("diff_status: NO STRUCTURAL CHANGES", output)
            self.assertEqual(len(markdown_files), 1)
            self.assertEqual(len(json_files), 1)
            self.assertEqual(payload["diff_status"], "NO STRUCTURAL CHANGES")
            self.assertEqual(payload["changed_sections"], [])
            self.assertIn("structured_diff", payload)
            self.assertTrue(payload["no_mutation"])
            self.assertEqual(payload["old_snapshot"]["filename"], old_path.name)
            self.assertEqual(payload["new_snapshot"]["filename"], new_path.name)
            self.assertIn("# Proto-Mind Snapshot Diff", markdown)
            self.assertIn("Diff status: **NO STRUCTURAL CHANGES**", markdown)
            self.assertIn("## Mutation Policy", markdown)
            self.assertIn("diff_export_sets: 1", status)
            self.assertIn("export_files: 2", status)
            self.assertIn("proto_snapshot_diffs:", inventory)
            self.assertIn("exists=True", next(line for line in inventory.splitlines() if "proto_snapshot_diffs:" in line))
            after_core = {path.name: path.read_bytes() for path in data_dir.glob("*") if path.is_file()}
            self.assertEqual(after_core, before_core)
            self.assertEqual(old_path.read_bytes(), before_old)
            self.assertEqual(new_path.read_bytes(), before_new)

    def test_proto_snapshot_diff_export_latest_requires_two_snapshots(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            snapshot_dir = project_root / "proto_mind" / "exports" / "proto_snapshots"
            snapshot_dir.mkdir(parents=True)
            (snapshot_dir / "proto_snapshot_only.json").write_text(
                json.dumps(_snapshot_diff_fixture()), encoding="utf-8"
            )
            diff_dir = project_root / "proto_mind" / "exports" / "proto_snapshot_diffs"

            output = format_proto_command(
                "/proto snapshot-diff-export-latest", project_root=project_root, memory_store=store
            )

            self.assertIn("Available JSON snapshots: 1", output)
            self.assertIn("Need at least 2", output)
            self.assertIn("No diff export files were created", output)
            self.assertFalse(diff_dir.exists())

    def test_proto_snapshot_diff_export_latest_writes_changed_sections(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            snapshot_dir = project_root / "proto_mind" / "exports" / "proto_snapshots"
            snapshot_dir.mkdir(parents=True)
            old_path = snapshot_dir / "proto_snapshot_latest_old.json"
            new_path = snapshot_dir / "proto_snapshot_latest_new.json"
            old_path.write_text(json.dumps(_snapshot_diff_fixture(status="OK")), encoding="utf-8")
            new_path.write_text(
                json.dumps(_snapshot_diff_fixture(status="WARN", enabled=True, warning_count=2, legacy_count=2)),
                encoding="utf-8",
            )
            os.utime(old_path, (100, 100))
            os.utime(new_path, (200, 200))

            output = format_proto_command(
                "/proto snapshot-diff-export-latest", project_root=project_root, memory_store=store
            )
            diff_dir = project_root / "proto_mind" / "exports" / "proto_snapshot_diffs"
            payload = json.loads(next(diff_dir.glob("proto_snapshot_diff_*.json")).read_text(encoding="utf-8"))

            self.assertIn("diff_status: CHANGED", output)
            self.assertEqual(payload["diff_status"], "CHANGED")
            self.assertIn("overall_status", payload["changed_sections"])
            self.assertIn("warnings", payload["changed_sections"])
            self.assertIn("context_injection", payload["changed_sections"])
            self.assertTrue(payload["structured_diff"]["warnings"])
            self.assertTrue(payload["no_mutation"])
