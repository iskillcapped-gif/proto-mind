"""Core flow checks: data."""
from __future__ import annotations

import unittest
from proto_mind.tests.flow_fixtures import (
    Path,
    SessionOperatorLogger,
    TemporaryDirectory,
    build_test_system,
    format_data_command,
    json,
    process_interactive_input,
)


class DataFlowTests(unittest.TestCase):
    def test_data_status_works(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)

            output = format_data_command("/data status", project_root=project_root)

            self.assertIn("Data Integrity Status", output)
            self.assertIn("data_dir:", output)
            self.assertIn("exports_dir:", output)
            self.assertIn("backups_dir:", output)
            self.assertIn("/data doctor", output)

    def test_data_inventory_works_with_empty_missing_stores(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)

            output = format_data_command("/data inventory", project_root=project_root)

            self.assertIn("Data Inventory", output)
            self.assertIn("persistent_memory", output)
            self.assertIn("reflection_journal", output)
            self.assertIn("exists=False", output)
            self.assertIn("Export directories:", output)
            self.assertIn("action_queue: path=", output)

    def test_data_doctor_works_with_empty_missing_stores(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)

            output = format_data_command("/data doctor", project_root=project_root)

            self.assertIn("Data Integrity Doctor", output)
            self.assertIn("Status: WARN", output)
            self.assertIn("Missing expected store", output)
            self.assertIn("Read-only diagnostics only", output)

    def test_data_doctor_detects_invalid_json(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            data_dir = project_root / "proto_mind" / "data"
            data_dir.mkdir(parents=True)
            (data_dir / "persistent_memory.json").write_text("{not-json", encoding="utf-8")

            output = format_data_command("/data doctor", project_root=project_root)

            self.assertIn("Status: ERROR", output)
            self.assertIn("persistent_memory read/parse issue", output)
            self.assertIn("invalid JSON", output)

    def test_data_doctor_detects_malformed_jsonl_and_counts_valid_records(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            data_dir = project_root / "proto_mind" / "data"
            data_dir.mkdir(parents=True)
            (data_dir / "tasks.jsonl").write_text(
                '{"id":"task_one","created_at":"2026-06-26T00:00:00+00:00"}\nnot-json\n',
                encoding="utf-8",
            )

            inventory = format_data_command("/data inventory", project_root=project_root)
            doctor = format_data_command("/data doctor", project_root=project_root)

            self.assertIn("tasks: path=", inventory)
            self.assertIn("records=1", inventory)
            self.assertIn("malformed_lines: 1", inventory)
            self.assertIn("tasks has malformed JSONL lines: 1", doctor)

    def test_data_doctor_detects_duplicate_ids(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            data_dir = project_root / "proto_mind" / "data"
            data_dir.mkdir(parents=True)
            record = {"id": "task_dup", "created_at": "2026-06-26T00:00:00+00:00", "title": "Duplicate"}
            (data_dir / "tasks.jsonl").write_text(json.dumps(record) + "\n" + json.dumps(record) + "\n", encoding="utf-8")

            output = format_data_command("/data doctor", project_root=project_root)

            self.assertIn("tasks has duplicate ids: task_dup", output)

    def test_data_commands_do_not_mutate_store_files(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            data_dir = project_root / "proto_mind" / "data"
            data_dir.mkdir(parents=True)
            persistent = data_dir / "persistent_memory.json"
            tasks = data_dir / "tasks.jsonl"
            persistent.write_text("[]", encoding="utf-8")
            tasks.write_text('{"id":"task_one"}\n', encoding="utf-8")
            before = {path: path.read_bytes() for path in (persistent, tasks)}

            status = format_data_command("/data status", project_root=project_root)
            inventory = format_data_command("/data inventory", project_root=project_root)
            doctor = format_data_command("/data doctor", project_root=project_root)
            after = {path: path.read_bytes() for path in (persistent, tasks)}

            self.assertIn("Data Integrity Status", status)
            self.assertIn("Data Inventory", inventory)
            self.assertIn("Data Integrity Doctor", doctor)
            self.assertEqual(after, before)

    def test_data_commands_work_through_shared_input_handler(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            coordinator, _, _ = build_test_system(project_root / "proto_mind")
            logger = SessionOperatorLogger.from_project_root(project_root, enabled=False)

            output = process_interactive_input(
                "/data status",
                coordinator=coordinator,
                session_logger=logger,
                project_root=project_root,
            )

            self.assertIn("Data Integrity Status", output)

    def test_data_refs_and_refs_doctor_work_with_missing_stores(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)

            refs = format_data_command("/data refs", project_root=project_root)
            doctor = format_data_command("/data refs-doctor", project_root=project_root)

            self.assertIn("Cross-Store Reference Inventory", refs)
            self.assertIn("Focused goal:", refs)
            self.assertIn("tasks -> goals: total=0", refs)
            self.assertIn("Cross-Store Reference Doctor", doctor)
            self.assertIn("Status: WARN", doctor)

    def test_data_refs_doctor_detects_task_with_missing_goal(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            data_dir = project_root / "proto_mind" / "data"
            data_dir.mkdir(parents=True)
            (data_dir / "goals.jsonl").write_text("", encoding="utf-8")
            (data_dir / "tasks.jsonl").write_text(
                json.dumps({"id": "task_one", "status": "open", "goal_id": "goal_missing"}) + "\n",
                encoding="utf-8",
            )

            output = format_data_command("/data refs-doctor", project_root=project_root)

            self.assertIn("Task task_one references missing goal: goal_missing", output)

    def test_data_refs_doctor_detects_experiment_with_missing_task(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            data_dir = project_root / "proto_mind" / "data"
            data_dir.mkdir(parents=True)
            (data_dir / "tasks.jsonl").write_text("", encoding="utf-8")
            (data_dir / "experiments.jsonl").write_text(
                json.dumps({"id": "exp_one", "status": "open", "task_id": "task_missing"}) + "\n",
                encoding="utf-8",
            )

            output = format_data_command("/data refs-doctor", project_root=project_root)

            self.assertIn("Experiment exp_one references missing task: task_missing", output)

    def test_data_refs_doctor_detects_world_with_missing_experiment(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            data_dir = project_root / "proto_mind" / "data"
            data_dir.mkdir(parents=True)
            (data_dir / "experiments.jsonl").write_text("", encoding="utf-8")
            (data_dir / "world_model.jsonl").write_text(
                json.dumps({"id": "wm_one", "status": "open", "experiment_id": "exp_missing"}) + "\n",
                encoding="utf-8",
            )

            output = format_data_command("/data refs-doctor", project_root=project_root)

            self.assertIn("World prediction wm_one references missing experiment: exp_missing", output)

    def test_data_refs_doctor_detects_terminal_focused_goal_and_active_task(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            data_dir = project_root / "proto_mind" / "data"
            data_dir.mkdir(parents=True)
            (data_dir / "goals.jsonl").write_text(
                json.dumps({"id": "goal_done", "title": "Done", "status": "completed", "focus": True}) + "\n",
                encoding="utf-8",
            )
            (data_dir / "tasks.jsonl").write_text(
                json.dumps({"id": "task_open", "status": "open", "goal_id": "goal_done"}) + "\n",
                encoding="utf-8",
            )

            output = format_data_command("/data refs-doctor", project_root=project_root)

            self.assertIn("Focused goal is not active: goal_done status=completed", output)
            self.assertIn("Active task task_open is linked to terminal goal goal_done", output)

    def test_data_refs_doctor_detects_missing_and_multiple_focus(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            data_dir = project_root / "proto_mind" / "data"
            data_dir.mkdir(parents=True)
            goals_path = data_dir / "goals.jsonl"
            goals_path.write_text(json.dumps({"id": "goal_one", "status": "active", "focus": False}) + "\n", encoding="utf-8")

            missing_focus = format_data_command("/data refs-doctor", project_root=project_root)

            goals_path.write_text(
                json.dumps({"id": "goal_one", "status": "active", "focus": True})
                + "\n"
                + json.dumps({"id": "goal_two", "status": "active", "focus": True})
                + "\n",
                encoding="utf-8",
            )
            multiple_focus = format_data_command("/data refs-doctor", project_root=project_root)

            self.assertIn("No focused goal is selected", missing_focus)
            self.assertIn("Multiple focused goals detected: goal_one, goal_two", multiple_focus)

    def test_data_refs_doctor_detects_queue_receipt_with_missing_target(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            data_dir = project_root / "proto_mind" / "data"
            data_dir.mkdir(parents=True)
            (data_dir / "persistent_memory.json").write_text("[]", encoding="utf-8")
            (data_dir / "working_memory.json").write_text("[]", encoding="utf-8")
            (data_dir / "skills.jsonl").write_text("", encoding="utf-8")
            queue_records = [
                {
                    "id": "cq_memory",
                    "status": "applied",
                    "applied_kind": "memory",
                    "applied_record_id": "mem_missing",
                    "undo_suggestion": "/memory forget mem_missing",
                },
                {
                    "id": "cq_skill",
                    "status": "applied",
                    "applied_kind": "skill",
                    "applied_record_id": "skill_missing",
                    "undo_suggestion": "/skills archive skill_missing",
                },
            ]
            (data_dir / "consolidation_queue.jsonl").write_text(
                "".join(json.dumps(record) + "\n" for record in queue_records),
                encoding="utf-8",
            )

            output = format_data_command("/data refs-doctor", project_root=project_root)

            self.assertIn("references missing memory: mem_missing", output)
            self.assertIn("references missing skill: skill_missing", output)
            self.assertIn("undo suggestion points to missing memory: mem_missing", output)
            self.assertIn("undo suggestion points to missing skill: skill_missing", output)

    def test_data_refs_doctor_detects_applied_receipt_missing_record_id(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            data_dir = project_root / "proto_mind" / "data"
            data_dir.mkdir(parents=True)
            (data_dir / "consolidation_queue.jsonl").write_text(
                json.dumps(
                    {
                        "id": "cq_missing_receipt",
                        "status": "applied",
                        "applied_kind": "memory",
                        "applied_record_id": "",
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            output = format_data_command("/data refs-doctor", project_root=project_root)

            self.assertIn("missing applied_record_id for memory receipt", output)

    def test_data_reference_commands_do_not_mutate_stores(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            data_dir = project_root / "proto_mind" / "data"
            data_dir.mkdir(parents=True)
            goals = data_dir / "goals.jsonl"
            tasks = data_dir / "tasks.jsonl"
            goals.write_text(json.dumps({"id": "goal_one", "status": "active", "focus": True}) + "\n", encoding="utf-8")
            tasks.write_text(json.dumps({"id": "task_one", "status": "open", "goal_id": "goal_one"}) + "\n", encoding="utf-8")
            before = {path: path.read_bytes() for path in (goals, tasks)}

            refs = format_data_command("/data refs", project_root=project_root)
            doctor = format_data_command("/data refs-doctor", project_root=project_root)
            after = {path: path.read_bytes() for path in (goals, tasks)}

            self.assertIn("resolved=1", refs)
            self.assertIn("Cross-Store Reference Doctor", doctor)
            self.assertEqual(after, before)
