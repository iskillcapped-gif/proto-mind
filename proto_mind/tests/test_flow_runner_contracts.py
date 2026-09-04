"""Core flow checks: runner contracts."""
from __future__ import annotations

import unittest
from proto_mind.tests.flow_fixtures import (
    ExperimentJournal,
    OperatorAgenda,
    Path,
    ReflectionJournal,
    SessionOperatorLogger,
    TaskQueue,
    TemporaryDirectory,
    WorldModelLite,
    _acceptance_state,
    _activation_state,
    _agenda_state,
    _baseline_state,
    _capability_state,
    _closure_state,
    _confirmation_state,
    _confirmed_action,
    _create_healthy_export_dirs,
    _focus_state,
    _plan_state,
    _sandbox_state,
    _write_milestone_fixture,
    build_test_system,
    format_acceptance_command,
    format_action_queue_command,
    format_activation_command,
    format_agenda_command,
    format_baseline_command,
    format_capability_command,
    format_closure_command,
    format_confirmation_command,
    format_context_command,
    format_experiment_command,
    format_focus_command,
    format_goal_command,
    format_loop_command,
    format_plan_command,
    format_sandbox_command,
    format_skill_command,
    format_task_command,
    format_world_command,
    json,
    patch,
    process_interactive_input,
)


class RunnerContractsTests(unittest.TestCase):
    def test_executed_action_passes_doctors_and_exports_receipt(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            coordinator, _, _ = build_test_system(project_root / "proto_mind")
            logger = SessionOperatorLogger.from_project_root(project_root)
            proposal_id, _ = _confirmed_action(project_root, "/data doctor")
            process_interactive_input(
                f"/action run {proposal_id}", coordinator=coordinator, session_logger=logger, project_root=project_root
            )

            queue_doctor = format_action_queue_command("/action queue-doctor", project_root=project_root)
            readiness_doctor = format_action_queue_command("/action readiness-doctor", project_root=project_root)
            format_action_queue_command("/action queue-export", project_root=project_root)
            export_path = next((project_root / "proto_mind" / "exports" / "action_queue").glob("action_queue_*.json"))
            exported = json.loads(export_path.read_text(encoding="utf-8"))["records"][0]

            self.assertIn("Status: OK", queue_doctor)
            self.assertIn("Status: OK", readiness_doctor)
            self.assertIn("executed records: 1", readiness_doctor)
            self.assertEqual(exported["execution_state"], "executed")
            self.assertTrue(exported["target_execution_performed"])
            self.assertTrue(exported["run_id"].startswith("run_"))
            self.assertEqual(exported["executed_command_count"], 1)
            self.assertEqual(len(exported["receipt_hash"]), 64)
            self.assertEqual(exported["run_receipt"]["commands"][0]["command"], "/data doctor")

    def test_world_status_works_when_file_missing(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)

            output = format_world_command("/world status", project_root=project_root)

            self.assertIsNotNone(output)
            self.assertIn("World Model Lite status:", output)
            self.assertIn("exists: False", output)
            self.assertIn("total_records: 0", output)
            self.assertIn("latest_prediction: none", output)

    def test_world_predict_creates_schema_and_list_inspect_work(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)

            output = format_world_command(
                "/world predict If A happens -> then B follows --confidence 0.8",
                project_root=project_root,
            )
            model = WorldModelLite.from_project_root(project_root)
            state = model._read_state()
            record = state.records[0]
            record_id = record["id"]
            list_output = format_world_command("/world list", project_root=project_root)
            inspect_output = format_world_command(f"/world inspect {record_id}", project_root=project_root)

            self.assertIn("Prediction recorded:", output)
            self.assertTrue(record_id.startswith("wm_"))
            self.assertEqual(record["situation"], "If A happens")
            self.assertEqual(record["prediction"], "then B follows")
            self.assertEqual(record["status"], "open")
            self.assertEqual(record["source"], "operator")
            self.assertEqual(record["confidence"], 0.8)
            self.assertIn("created_at", record)
            self.assertIn("updated_at", record)
            self.assertIn(record_id, list_output)
            self.assertIn("World prediction:", inspect_output)
            self.assertIn("prediction: then B follows", inspect_output)

    def test_world_predict_without_arrow_and_invalid_confidence_are_clean(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            missing_arrow = format_world_command("/world predict If A then B", project_root=project_root)
            invalid_confidence = format_world_command(
                "/world predict If A -> B --confidence nope",
                project_root=project_root,
            )
            out_of_range = format_world_command(
                "/world predict If A -> B --confidence 1.5",
                project_root=project_root,
            )

            self.assertIn("Usage: /world predict", missing_arrow)
            self.assertIn("Invalid --confidence value", invalid_confidence)
            self.assertIn("Must be between 0.0 and 1.0", out_of_range)
            self.assertFalse(WorldModelLite.from_project_root(project_root).world_path.exists())

    def test_world_expect_observe_score_lesson_and_stats(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            output = format_world_command("/world predict If tasks are small -> bug diagnosis is easier", project_root=project_root)
            record_id = next(line.strip().split(" — ")[0] for line in output.splitlines() if line.strip().startswith("wm_"))

            expect = format_world_command(f"/world expect {record_id} fewer mixed bugs", project_root=project_root)
            score_without_outcome = format_world_command(f"/world score {record_id} 4", project_root=project_root)
            observe = format_world_command(f"/world observe {record_id} tests passed with small fixes", project_root=project_root)
            score = format_world_command(f"/world score {record_id} 4", project_root=project_root)
            lesson = format_world_command(f"/world lesson {record_id} Small patches reduce debugging complexity.", project_root=project_root)
            stats = format_world_command("/world stats", project_root=project_root)
            record = WorldModelLite.from_project_root(project_root)._read_state().records[0]

            self.assertIn("Expected signal updated:", expect)
            self.assertIn("Cannot score without an observed outcome", score_without_outcome)
            self.assertIn("Outcome observed:", observe)
            self.assertIn("Prediction scored:", score)
            self.assertIn("Lesson updated:", lesson)
            self.assertEqual(record["expected_signal"], "fewer mixed bugs")
            self.assertEqual(record["actual_outcome"], "tests passed with small fixes")
            self.assertEqual(record["score"], 4)
            self.assertEqual(record["status"], "scored")
            self.assertIn("Small patches", record["lesson"])
            self.assertIn("average_score: 4.00", stats)
            self.assertIn("score_counts: 4=1", stats)

    def test_world_invalid_score_unknown_and_corrupted_file_are_clean(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            model = WorldModelLite.from_project_root(project_root)
            invalid_score = format_world_command("/world score missing 9", project_root=project_root)
            notnum = format_world_command("/world score missing nope", project_root=project_root)
            unknown = format_world_command("/world observe missing outcome", project_root=project_root)
            model.world_path.parent.mkdir(parents=True)
            model.world_path.write_text("{not json\n", encoding="utf-8")
            status = format_world_command("/world status", project_root=project_root)
            refused = format_world_command("/world predict If A -> B", project_root=project_root)

            self.assertIn("Score must be an integer from 0 to 5", invalid_score)
            self.assertIn("Invalid score", notnum)
            self.assertIn("World prediction not found: missing", unknown)
            self.assertIn("file_health: malformed_jsonl", status)
            self.assertIn("refusing to modify", refused)
            self.assertEqual(model.world_path.read_text(encoding="utf-8"), "{not json\n")

    def test_world_archive_reopen_and_list_filters(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            first_output = format_world_command("/world predict If A -> B", project_root=project_root)
            second_output = format_world_command("/world predict If C -> D", project_root=project_root)
            first_id = next(line.strip().split(" — ")[0] for line in first_output.splitlines() if line.strip().startswith("wm_"))
            second_id = next(line.strip().split(" — ")[0] for line in second_output.splitlines() if line.strip().startswith("wm_"))
            format_world_command(f"/world observe {second_id} observed", project_root=project_root)
            format_world_command(f"/world score {second_id} 5", project_root=project_root)

            archived = format_world_command(f"/world archive {first_id}", project_root=project_root)
            default_list = format_world_command("/world list", project_root=project_root)
            all_list = format_world_command("/world list --all", project_root=project_root)
            scored_list = format_world_command("/world list --status scored", project_root=project_root)
            reopened = format_world_command(f"/world reopen {first_id}", project_root=project_root)
            reopened_list = format_world_command("/world list", project_root=project_root)

            self.assertIn("Archived prediction:", archived)
            self.assertNotIn(first_id, default_list)
            self.assertNotIn(second_id, default_list)
            self.assertIn(first_id, all_list)
            self.assertIn(second_id, all_list)
            self.assertIn(second_id, scored_list)
            self.assertNotIn(first_id, scored_list)
            self.assertIn("Reopened prediction:", reopened)
            self.assertIn(first_id, reopened_list)

    def test_world_stats_handles_no_scored_records_cleanly(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            format_world_command("/world predict If A -> B", project_root=project_root)

            stats = format_world_command("/world stats", project_root=project_root)

            self.assertIn("scored_count: 0", stats)
            self.assertIn("average_score: none", stats)
            self.assertIn("score_counts: none", stats)

    def test_world_goal_task_experiment_links_and_filters(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            goal_output = format_goal_command("/goals add Improve architecture", project_root=project_root)
            goal_id = next(line.strip().split(" — ")[0] for line in goal_output.splitlines() if line.strip().startswith("goal_"))
            task_output = format_task_command(f"/tasks add Build world model --goal {goal_id}", project_root=project_root)
            task_id = next(line.strip().split(" — ")[0] for line in task_output.splitlines() if line.strip().startswith("task_"))
            experiment_output = format_experiment_command(
                f"/experiments start Check world model --goal {goal_id} --task {task_id}",
                project_root=project_root,
            )
            experiment_id = next(line.strip().split(" — ")[0] for line in experiment_output.splitlines() if line.strip().startswith("exp_"))

            linked_output = format_world_command(
                f"/world predict If links are stored -> filters work --goal {goal_id} --task {task_id} --experiment {experiment_id}",
                project_root=project_root,
            )
            other_output = format_world_command("/world predict If unrelated -> does not match filters", project_root=project_root)
            linked_id = next(line.strip().split(" — ")[0] for line in linked_output.splitlines() if line.strip().startswith("wm_"))
            other_id = next(line.strip().split(" — ")[0] for line in other_output.splitlines() if line.strip().startswith("wm_"))
            by_goal = format_world_command(f"/world list --goal {goal_id}", project_root=project_root)
            by_task = format_world_command(f"/world list --task {task_id}", project_root=project_root)
            by_experiment = format_world_command(f"/world list --experiment {experiment_id}", project_root=project_root)
            inspect = format_world_command(f"/world inspect {linked_id}", project_root=project_root)
            missing_goal = format_world_command("/world predict If bad -> fails --goal missing_goal", project_root=project_root)
            missing_task = format_world_command("/world predict If bad -> fails --task missing_task", project_root=project_root)
            missing_experiment = format_world_command("/world predict If bad -> fails --experiment missing_exp", project_root=project_root)

            self.assertIn(f"goal={goal_id}", linked_output)
            self.assertIn(f"task={task_id}", linked_output)
            self.assertIn(f"experiment={experiment_id}", linked_output)
            self.assertIn(linked_id, by_goal)
            self.assertNotIn(other_id, by_goal)
            self.assertIn(linked_id, by_task)
            self.assertNotIn(other_id, by_task)
            self.assertIn(linked_id, by_experiment)
            self.assertNotIn(other_id, by_experiment)
            self.assertIn(f"goal_id: {goal_id}", inspect)
            self.assertIn(f"task_id: {task_id}", inspect)
            self.assertIn(f"experiment_id: {experiment_id}", inspect)
            self.assertIn("Goal not found: missing_goal", missing_goal)
            self.assertIn("Task not found: missing_task", missing_task)
            self.assertIn("Experiment not found: missing_exp", missing_experiment)

    def test_world_commands_work_through_shared_input_handler_without_session_log_turn(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            coordinator, _, _ = build_test_system(project_root)
            logger = SessionOperatorLogger.from_project_root(project_root)
            coordinator.session_logger = logger

            output = process_interactive_input(
                "/world predict If shared handler works -> command is routed",
                coordinator=coordinator,
                session_logger=logger,
                project_root=project_root,
            )
            status = process_interactive_input(
                "/world status",
                coordinator=coordinator,
                session_logger=logger,
                project_root=project_root,
            )

            self.assertIn("Prediction recorded:", output)
            self.assertIn("total_records: 1", status)
            self.assertEqual(logger.status().entry_count, 0)

    def test_loop_status_morning_evening_next_and_doctor_work_with_empty_stores(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)

            status = format_loop_command("/loop status", project_root=project_root)
            morning = format_loop_command("/loop morning", project_root=project_root)
            evening = format_loop_command("/loop evening", project_root=project_root)
            next_output = format_loop_command("/loop next", project_root=project_root)
            doctor = format_loop_command("/loop doctor", project_root=project_root)

            self.assertIn("Operating Loop Status", status)
            self.assertIn("focused goal: none", status)
            self.assertIn("Identity:", status)
            self.assertIn("Operating Loop Morning", morning)
            self.assertIn("Identity: none", morning)
            self.assertIn("Operating Loop Evening", evening)
            self.assertIn("Next action:", next_output)
            self.assertIn("type: goal", next_output)
            self.assertIn("/goals add <title>", next_output)
            self.assertIn("Operating Loop Doctor", doctor)
            self.assertIn("Status: OK", doctor)

    def test_loop_daily_commands_work_with_empty_stores(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)

            morning = format_loop_command("/loop morning-plan", project_root=project_root)
            evening = format_loop_command("/loop evening-review", project_root=project_root)
            capture = format_loop_command("/loop capture-today", project_root=project_root)

            self.assertIn("Operating Loop Morning Plan", morning)
            self.assertIn("focused goal: none", morning)
            self.assertIn("next task: none", morning)
            self.assertIn("Suggested commands:", morning)
            self.assertIn("Operating Loop Evening Review", evening)
            self.assertIn("Recent completed tasks:", evening)
            self.assertIn("- none", evening)
            self.assertIn("/reflection now --last 30", evening)
            self.assertIn("Operating Loop Capture Today", capture)
            self.assertIn("Mutation policy: read-only checklist", capture)
            self.assertIn("/context injection audit --last 20", capture)

    def test_loop_morning_plan_includes_focused_goal_and_next_task(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            goal_output = format_goal_command("/goals add Daily focus --priority high", project_root=project_root)
            goal_id = next(line.strip().split(" — ")[0] for line in goal_output.splitlines() if line.strip().startswith("goal_"))
            format_goal_command(f"/goals focus {goal_id}", project_root=project_root)
            task_output = format_task_command(f"/tasks add Daily task --priority high --goal {goal_id}", project_root=project_root)
            task_id = next(line.strip().split(" — ")[0] for line in task_output.splitlines() if line.strip().startswith("task_"))

            output = format_loop_command("/loop morning-plan", project_root=project_root)

            self.assertIn("Operating Loop Morning Plan", output)
            self.assertIn(goal_id, output)
            self.assertIn(task_id, output)
            self.assertIn("/tasks start", output)

    def test_loop_evening_review_handles_no_recent_completions_cleanly(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            format_task_command("/tasks add Still open --priority normal", project_root=project_root)

            output = format_loop_command("/loop evening-review", project_root=project_root)

            self.assertIn("Operating Loop Evening Review", output)
            self.assertIn("Recent completed tasks:", output)
            self.assertIn("Recent completed/inconclusive experiments:", output)
            self.assertIn("Recent scored world predictions:", output)
            self.assertIn("- none", output)
            self.assertIn("/world stats", output)

    def test_loop_capture_today_outputs_suggested_commands_and_is_read_only(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            task_output = format_task_command("/tasks add Capture active task --priority high", project_root=project_root)
            task_id = next(line.strip().split(" — ")[0] for line in task_output.splitlines() if line.strip().startswith("task_"))
            format_task_command(f"/tasks start {task_id}", project_root=project_root)
            exp_output = format_experiment_command("/experiments start Capture experiment", project_root=project_root)
            exp_id = next(line.strip().split(" — ")[0] for line in exp_output.splitlines() if line.strip().startswith("exp_"))
            world_output = format_world_command("/world predict If capture runs -> it stays read only", project_root=project_root)
            world_id = next(line.strip().split(" — ")[0] for line in world_output.splitlines() if line.strip().startswith("wm_"))
            paths = [
                TaskQueue.from_project_root(project_root).tasks_path,
                ExperimentJournal.from_project_root(project_root).experiments_path,
                WorldModelLite.from_project_root(project_root).world_path,
            ]
            before = tuple(path.read_bytes() for path in paths)

            output = format_loop_command("/loop capture-today", project_root=project_root)
            after = tuple(path.read_bytes() for path in paths)

            self.assertIn("Operating Loop Capture Today", output)
            self.assertIn(f"/tasks done {task_id}", output)
            self.assertIn(f"/experiments result {exp_id}", output)
            self.assertIn(f"/world observe {world_id}", output)
            self.assertIn("/reflection now --last 30", output)
            self.assertIn("/context export", output)
            self.assertEqual(after, before)

    def test_loop_status_shows_focused_goal_next_task_reflection_and_skills(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            goal_output = format_goal_command("/goals add Operating loop goal --priority high", project_root=project_root)
            goal_id = next(line.strip().split(" — ")[0] for line in goal_output.splitlines() if line.strip().startswith("goal_"))
            format_goal_command(f"/goals focus {goal_id}", project_root=project_root)
            task_output = format_task_command(f"/tasks add Focused high task --priority high --goal {goal_id}", project_root=project_root)
            task_id = next(line.strip().split(" — ")[0] for line in task_output.splitlines() if line.strip().startswith("task_"))
            ReflectionJournal.from_project_root(project_root).append(
                {
                    "id": "refl_test",
                    "created_at": "2026-06-26T10:00:00+00:00",
                    "scope": "last",
                    "source": "session_log",
                    "entries_analyzed": 0,
                    "summary": "test reflection",
                    "findings": [],
                    "recommendations": [],
                    "tags": [],
                }
            )
            format_skill_command("/skills add Checkpoint first --category workflow", project_root=project_root)

            output = format_loop_command("/loop status", project_root=project_root)

            self.assertIn(goal_id, output)
            self.assertIn(task_id, output)
            self.assertIn("reflection journal count: 1", output)
            self.assertIn("latest reflection: refl_test", output)
            self.assertIn("active skills count: 1", output)

    def test_loop_next_prefers_in_progress_task(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            first = format_task_command("/tasks add High open --priority high", project_root=project_root)
            second = format_task_command("/tasks add Started normal", project_root=project_root)
            first_id = next(line.strip().split(" — ")[0] for line in first.splitlines() if line.strip().startswith("task_"))
            second_id = next(line.strip().split(" — ")[0] for line in second.splitlines() if line.strip().startswith("task_"))
            format_task_command(f"/tasks start {second_id}", project_root=project_root)

            output = format_loop_command("/loop next", project_root=project_root)

            self.assertIn("type: task", output)
            self.assertIn(second_id, output)
            self.assertNotIn(first_id, output.split("summary:", 1)[1])

    def test_loop_next_prefers_focused_goal_high_priority_task(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            goal_output = format_goal_command("/goals add Focused goal", project_root=project_root)
            goal_id = next(line.strip().split(" — ")[0] for line in goal_output.splitlines() if line.strip().startswith("goal_"))
            format_goal_command(f"/goals focus {goal_id}", project_root=project_root)
            unrelated = format_task_command("/tasks add Unrelated normal", project_root=project_root)
            focused = format_task_command(f"/tasks add Focused high --priority high --goal {goal_id}", project_root=project_root)
            unrelated_id = next(line.strip().split(" — ")[0] for line in unrelated.splitlines() if line.strip().startswith("task_"))
            focused_id = next(line.strip().split(" — ")[0] for line in focused.splitlines() if line.strip().startswith("task_"))

            output = format_loop_command("/loop next", project_root=project_root)

            self.assertIn(focused_id, output)
            self.assertNotIn(unrelated_id, output.split("summary:", 1)[1])

    def test_loop_morning_shows_open_experiment_and_world_prediction(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            experiment = format_experiment_command("/experiments start Open experiment", project_root=project_root)
            prediction = format_world_command("/world predict If loop reads world -> it shows prediction", project_root=project_root)
            experiment_id = next(line.strip().split(" — ")[0] for line in experiment.splitlines() if line.strip().startswith("exp_"))
            prediction_id = next(line.strip().split(" — ")[0] for line in prediction.splitlines() if line.strip().startswith("wm_"))

            output = format_loop_command("/loop morning", project_root=project_root)

            self.assertIn(experiment_id, output)
            self.assertIn(prediction_id, output)

    def test_loop_doctor_detects_cross_module_consistency_issues_and_is_read_only(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            tasks_path = TaskQueue.from_project_root(project_root).tasks_path
            experiments_path = ExperimentJournal.from_project_root(project_root).experiments_path
            world_path = WorldModelLite.from_project_root(project_root).world_path
            tasks_path.parent.mkdir(parents=True)
            tasks_path.write_text(
                json.dumps(
                    {
                        "id": "task_missing_goal",
                        "created_at": "2026-06-26T10:00:00+00:00",
                        "updated_at": "2026-06-26T10:00:00+00:00",
                        "title": "Missing goal task",
                        "status": "done",
                        "priority": "normal",
                        "goal_id": "goal_missing",
                        "source": "operator",
                        "tags": [],
                        "result": "",
                        "blocked_reason": "",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            experiments_path.write_text(
                json.dumps(
                    {
                        "id": "exp_missing_task",
                        "created_at": "2026-06-26T10:00:00+00:00",
                        "updated_at": "2026-06-26T10:00:00+00:00",
                        "title": "Missing task exp",
                        "status": "completed",
                        "task_id": "task_missing",
                        "lesson": "",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            world_path.write_text(
                json.dumps(
                    {
                        "id": "wm_missing_exp",
                        "created_at": "2026-06-26T10:00:00+00:00",
                        "updated_at": "2026-06-26T10:00:00+00:00",
                        "situation": "x",
                        "prediction": "y",
                        "actual_outcome": "observed",
                        "score": 4,
                        "status": "scored",
                        "lesson": "",
                        "experiment_id": "exp_missing",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            before = (tasks_path.read_bytes(), experiments_path.read_bytes(), world_path.read_bytes())

            output = format_loop_command("/loop doctor", project_root=project_root)
            after = (tasks_path.read_bytes(), experiments_path.read_bytes(), world_path.read_bytes())

            self.assertIn("Status: WARN", output)
            self.assertIn("Task task_missing_goal links to missing goal_id=goal_missing", output)
            self.assertIn("Completed task has empty result: task_missing_goal", output)
            self.assertIn("Experiment exp_missing_task links to missing task_id=task_missing", output)
            self.assertIn("Completed experiment has empty lesson: exp_missing_task", output)
            self.assertIn("World prediction wm_missing_exp links to missing experiment_id=exp_missing", output)
            self.assertIn("Scored world prediction has empty lesson: wm_missing_exp", output)
            self.assertEqual(after, before)

    def test_loop_commands_work_through_shared_input_handler_without_session_log_turn(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            coordinator, _, _ = build_test_system(project_root)
            logger = SessionOperatorLogger.from_project_root(project_root)
            coordinator.session_logger = logger

            output = process_interactive_input(
                "/loop status",
                coordinator=coordinator,
                session_logger=logger,
                project_root=project_root,
            )

            self.assertIn("Operating Loop Status", output)
            self.assertEqual(logger.status().entry_count, 0)

    def test_agenda_status_reports_readiness_helpers_and_warning_counts(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            with patch("proto_mind.agenda_layer.OperatorAgenda.read_state", return_value=_agenda_state()):
                output = format_agenda_command("/agenda status", project_root=project_root, memory_store=store)

            self.assertIn("Operator Agenda Status", output)
            self.assertIn("Status: WARN", output)
            self.assertIn(f"project_root: {project_root}", output)
            self.assertIn("command_registry: commands=387 categories=41", output)
            self.assertIn("daily=true, session=true, milestone=true, warnings=true", output)
            self.assertIn("accepted_known_warnings: 12", output)
            self.assertIn("unknown_warnings: 0", output)
            self.assertIn("can_safely_suggest_next_work: true", output)
            self.assertIn("context_injection: disabled", output)

    def test_agenda_next_prioritizes_unknown_warning_inspection(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            agenda = OperatorAgenda(project_root=project_root, memory_store=store)
            with patch.object(agenda, "read_state", return_value=_agenda_state(unknown=True)):
                output = agenda.format_next()

            self.assertIn("Operator Agenda Next", output)
            self.assertIn("Inspect unknown warnings before accepting new work", output)
            self.assertIn("manual_command: /warnings unknown", output)
            self.assertIn("The command was not run", output)

    def test_agenda_next_continues_milestone_when_all_warnings_are_accepted(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            agenda = OperatorAgenda(project_root=project_root, memory_store=store)
            with patch.object(agenda, "read_state", return_value=_agenda_state()):
                output = agenda.format_next()

            self.assertIn("Open a planning-only focused work session", output)
            self.assertIn("one small manual work plan", output)
            self.assertIn("manual_command: /focus plan", output)
            self.assertIn("no commands, state, backups, or snapshots", output)

    def test_agenda_list_builds_short_ordered_manual_queue_without_persistence(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            agenda = OperatorAgenda(project_root=project_root, memory_store=store)
            with patch.object(agenda, "read_state", return_value=_agenda_state()):
                items = agenda.build_queue()
                output = agenda.format_list()

            self.assertGreaterEqual(len(items), 3)
            self.assertLessEqual(len(items), 7)
            self.assertTrue(all(item["priority"] in {"P0", "P1", "P2"} for item in items))
            self.assertIn("Mode: live read-only queue", output)
            self.assertIn("reason:", output)
            self.assertIn("safety:", output)
            self.assertIn("manual command:", output)
            self.assertIn("/focus plan", output)
            self.assertIn("/prechange checklist", output)
            self.assertIn("Generated live and not persisted", output)

    def test_agenda_doctor_checks_dependencies_ledger_context_and_dangerous_actions(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            store.save_persistent_memory([])
            _create_healthy_export_dirs(project_root)
            _write_milestone_fixture(project_root)

            output = format_agenda_command("/agenda doctor", project_root=project_root, memory_store=store)

            self.assertIn("Operator Agenda Doctor", output)
            self.assertIn("Status: OK", output)
            self.assertIn("All agenda commands are registered", output)
            self.assertIn("read-only with mutates=none", output)
            self.assertIn("Daily, Session, Milestone, Warning, Export, and Snapshot helpers are reachable", output)
            self.assertIn("Accepted-known warnings ledger is reachable", output)
            self.assertIn("Warning classification is available", output)
            self.assertIn("Context Injection is disabled", output)
            self.assertIn("No execution, repair, cleanup, migration, deletion, move, or compression action is exposed", output)

    def test_agenda_doctor_warns_without_changing_explicit_context_enablement(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            store.save_persistent_memory([])
            _create_healthy_export_dirs(project_root)
            _write_milestone_fixture(project_root)
            format_context_command("/context injection enable", project_root=project_root)
            settings_path = project_root / "proto_mind" / "data" / "context_injection.json"
            before = settings_path.read_bytes()

            output = format_agenda_command("/agenda doctor", project_root=project_root, memory_store=store)

            self.assertIn("Status: WARN", output)
            self.assertIn("Context Injection is explicitly enabled", output)
            self.assertEqual(settings_path.read_bytes(), before)
            self.assertTrue(json.loads(settings_path.read_text(encoding="utf-8"))["enabled"])

    def test_agenda_commands_are_read_only_through_shared_handler(self) -> None:
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
                for command in ("/agenda status", "/agenda next", "/agenda list", "/agenda doctor")
            ]

            self.assertIn("Operator Agenda Status", outputs[0])
            self.assertIn("Operator Agenda Next", outputs[1])
            self.assertIn("Operator Agenda", outputs[2])
            self.assertIn("Operator Agenda Doctor", outputs[3])
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

    def test_focus_status_reports_warn_baseline_and_safe_planning(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            with patch("proto_mind.focus_layer.FocusMode.read_state", return_value=_focus_state()):
                output = format_focus_command("/focus status", project_root=project_root, memory_store=store)

            self.assertIn("Focus Mode Status", output)
            self.assertIn("Status: WARN", output)
            self.assertIn(f"project_root: {project_root}", output)
            self.assertIn("command_registry: commands=387 categories=41", output)
            self.assertIn("context_injection: disabled", output)
            self.assertIn("prechange_readiness: WARN", output)
            self.assertIn("agenda_state: WARN", output)
            self.assertIn("accepted_known_warnings: 12", output)
            self.assertIn("unknown_warnings: 0", output)
            self.assertIn("blockers: 0", output)
            self.assertIn("focus_planning_safe: true", output)
            self.assertIn("does not execute commands", output)

    def test_focus_status_blocks_unknown_warnings_or_blockers(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            with patch(
                "proto_mind.focus_layer.FocusMode.read_state",
                return_value=_focus_state(unknown=True, blockers=1),
            ):
                output = format_focus_command("/focus status", project_root=project_root, memory_store=store)

            self.assertIn("Status: BLOCKED", output)
            self.assertIn("unknown_warnings: 1", output)
            self.assertIn("blockers: 1", output)
            self.assertIn("focus_planning_safe: false", output)

    def test_focus_plan_builds_current_baseline_manual_session(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            with patch("proto_mind.focus_layer.FocusMode.read_state", return_value=_focus_state()):
                output = format_focus_command("/focus plan", project_root=project_root, memory_store=store)

            self.assertIn("Focused Work Session Plan", output)
            self.assertIn("one small, explicitly scoped Proto-Mind milestone", output)
            self.assertIn("/prechange checklist", output)
            self.assertIn("/milestone next", output)
            self.assertIn("/prechange handoff", output)
            self.assertIn("scripts/which_python.sh", output)
            self.assertIn("scripts/run_tests.sh", output)
            self.assertIn("compileall proto_mind", output)
            self.assertIn("Done criteria:", output)
            self.assertIn("/acceptance checklist", output)
            self.assertIn("/acceptance decision-guide", output)
            self.assertIn("/session end-summary", output)
            self.assertIn("/session handoff-brief", output)
            self.assertIn("none of its commands or steps were run", output)

    def test_focus_plan_prioritizes_unknown_warning_inspection(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            with patch("proto_mind.focus_layer.FocusMode.read_state", return_value=_focus_state(unknown=True)):
                output = format_focus_command("/focus plan", project_root=project_root, memory_store=store)

            self.assertIn("Understand unknown warnings", output)
            self.assertIn("Warning inspection and operator classification", output)
            self.assertIn("Run /warnings unknown manually", output)
            self.assertIn("do not repair or accept automatically", output)

    def test_focus_checklist_is_manual_only_and_complete(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")

            output = format_focus_command("/focus checklist", project_root=project_root, memory_store=store)

            self.assertIn("Focused Session Manual Checklist", output)
            for expected in (
                "Define one concrete session objective",
                "Confirm allowed writes",
                "Confirm forbidden writes",
                "Rule 0 backup/checkpoint",
                "/warnings unknown",
                "/prechange status",
                "one small task",
                "scripts/which_python.sh",
                "scripts/run_tests.sh",
                "compileall",
                "manual smoke",
                "SHA-256",
                "acceptance decision",
            ):
                self.assertIn(expected, output)
            self.assertIn("Printed only", output)

    def test_focus_handoff_prints_copyable_baseline_without_writing(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            _write_milestone_fixture(project_root)
            with patch("proto_mind.focus_layer.FocusMode.read_state", return_value=_focus_state()):
                output = format_focus_command("/focus handoff", project_root=project_root, memory_store=store)

            self.assertIn("Proto-Mind Focused Session Handoff", output)
            self.assertIn(f"Project: {project_root}", output)
            self.assertIn("Registry baseline: 387 commands across 41 categories", output)
            self.assertIn("Focus readiness: WARN", output)
            self.assertIn("Warning baseline: accepted=12, unknown=0, blockers=0", output)
            self.assertIn("Context Injection: disabled", output)
            self.assertIn("Rule 0:", output)
            self.assertIn("Focus-mode safety constraints:", output)
            self.assertIn("<operator-selected milestone", output)
            self.assertIn("Verification:", output)
            self.assertIn("Manual smoke:", output)
            self.assertIn("SHA-256", output)
            self.assertIn("no file, clipboard, command, model, external call, or focus state", output)

    def test_focus_doctor_checks_helpers_context_and_dangerous_actions(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            store.save_persistent_memory([])
            _create_healthy_export_dirs(project_root)
            _write_milestone_fixture(project_root)
            with patch("proto_mind.focus_layer.FocusMode.read_state", return_value=_focus_state()):
                output = format_focus_command("/focus doctor", project_root=project_root, memory_store=store)

            self.assertIn("Focus Mode Doctor", output)
            self.assertIn("Status: OK", output)
            self.assertIn("All focus commands are registered", output)
            self.assertIn("read-only with mutates=none", output)
            self.assertIn("Pre-Change, Agenda, Session, Milestone, Warning, and Export helpers are reachable", output)
            self.assertIn("Warning readiness is computable", output)
            self.assertIn("Context Injection is disabled", output)
            self.assertIn("No execution, persistence, backup, snapshot, repair, cleanup, migration, deletion, move, or compression action is exposed", output)

    def test_focus_doctor_warns_without_changing_explicit_context_enablement(self) -> None:
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
                "proto_mind.focus_layer.FocusMode.read_state",
                return_value=_focus_state(context_state="enabled"),
            ):
                output = format_focus_command("/focus doctor", project_root=project_root, memory_store=store)

            self.assertIn("Status: WARN", output)
            self.assertIn("Context Injection is explicitly enabled", output)
            self.assertEqual(settings_path.read_bytes(), before)
            self.assertTrue(json.loads(settings_path.read_text(encoding="utf-8"))["enabled"])

    def test_focus_commands_are_read_only_through_shared_handler(self) -> None:
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
                    "/focus status",
                    "/focus plan",
                    "/focus checklist",
                    "/focus doctor",
                    "/focus handoff",
                )
            ]

            self.assertIn("Focus Mode Status", outputs[0])
            self.assertIn("Focused Work Session Plan", outputs[1])
            self.assertIn("Focused Session Manual Checklist", outputs[2])
            self.assertIn("Focus Mode Doctor", outputs[3])
            self.assertIn("Proto-Mind Focused Session Handoff", outputs[4])
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

    def test_acceptance_status_reports_warn_baseline_and_safe_human_review(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            with patch("proto_mind.acceptance_layer.AcceptanceReview.read_state", return_value=_acceptance_state()):
                output = format_acceptance_command("/acceptance status", project_root=project_root, memory_store=store)

            self.assertIn("Acceptance Review Status", output)
            self.assertIn("Status: WARN", output)
            self.assertIn(f"project_root: {project_root}", output)
            self.assertIn("command_registry: commands=387 categories=41", output)
            self.assertIn("context_injection: disabled", output)
            self.assertIn("focus_readiness: WARN", output)
            self.assertIn("prechange_readiness: WARN", output)
            self.assertIn("accepted_known_warnings: 12", output)
            self.assertIn("unknown_warnings: 0", output)
            self.assertIn("blockers: 0", output)
            self.assertIn("acceptance_review_safe: true", output)
            self.assertIn("never accepts, rejects, holds", output)

    def test_acceptance_status_blocks_unknown_warnings_or_blockers(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            with patch(
                "proto_mind.acceptance_layer.AcceptanceReview.read_state",
                return_value=_acceptance_state(unknown=True, blockers=1),
            ):
                output = format_acceptance_command("/acceptance status", project_root=project_root, memory_store=store)

            self.assertIn("Status: BLOCKED", output)
            self.assertIn("unknown_warnings: 1", output)
            self.assertIn("blockers: 1", output)
            self.assertIn("acceptance_review_safe: false", output)

    def test_acceptance_checklist_contains_required_manual_evidence(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")

            output = format_acceptance_command("/acceptance checklist", project_root=project_root, memory_store=store)

            self.assertIn("Acceptance Review Manual Checklist", output)
            for expected in (
                "Rule 0 backup path",
                "changed files",
                "added/changed commands",
                "Registry command/category counts",
                "scripts/which_python.sh",
                "scripts/run_tests.sh",
                "compileall",
                "manual smoke",
                "Context Injection",
                "SHA-256",
                "dangerous execution",
                "limitations and known warnings",
                "original task brief",
                "ACCEPT WITH NOTES",
                "REJECT / NEEDS FIX",
                "HOLD / NEEDS MORE INFO",
            ):
                self.assertIn(expected, output)
            self.assertIn("no report was parsed", output)

    def test_acceptance_criteria_lists_hard_blockers_and_required_evidence(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")

            output = format_acceptance_command("/acceptance criteria", project_root=project_root, memory_store=store)

            self.assertIn("Reusable Acceptance Criteria", output)
            self.assertIn("Hard blockers:", output)
            self.assertIn("Missing Rule 0 backup", output)
            self.assertIn("Tests fail", output)
            self.assertIn("Context Injection changed unexpectedly", output)
            self.assertIn("proto_mind/data or proto_mind/exports changed", output)
            self.assertIn("Unknown warnings", output)
            self.assertIn("Command Registry or routing is broken", output)
            self.assertIn("PySide or tkinter imports are broken", output)
            self.assertIn("Soft warnings:", output)
            self.assertIn("Acceptable limitations:", output)
            self.assertIn("Required verification evidence:", output)
            self.assertIn("Safety invariants:", output)
            self.assertIn("Documentation expectations:", output)

    def test_acceptance_decision_guide_is_framework_only(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")

            output = format_acceptance_command("/acceptance decision-guide", project_root=project_root, memory_store=store)

            self.assertIn("Acceptance Decision Guide", output)
            self.assertIn("ACCEPT:", output)
            self.assertIn("ACCEPT WITH NOTES:", output)
            self.assertIn("REJECT / NEEDS FIX:", output)
            self.assertIn("HOLD / NEEDS MORE INFO:", output)
            self.assertIn("does not inspect external text", output)
            self.assertIn("choose a decision", output)

    def test_acceptance_handoff_prints_copyable_review_instructions(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            _write_milestone_fixture(project_root)
            with patch("proto_mind.acceptance_layer.AcceptanceReview.read_state", return_value=_acceptance_state()):
                output = format_acceptance_command("/acceptance handoff", project_root=project_root, memory_store=store)

            self.assertIn("Proto-Mind Acceptance Review Handoff", output)
            self.assertIn(f"Project: {project_root}", output)
            self.assertIn("Registry baseline: 387 commands across 41 categories", output)
            self.assertIn("Acceptance readiness: WARN", output)
            self.assertIn("Warning baseline: accepted=12, unknown=0, blockers=0", output)
            self.assertIn("Context Injection: disabled", output)
            self.assertIn("Required Codex final report fields:", output)
            self.assertIn("Verification commands:", output)
            self.assertIn("Manual smoke:", output)
            self.assertIn("ACCEPT | ACCEPT WITH NOTES | REJECT / NEEDS FIX | HOLD / NEEDS MORE INFO", output)
            self.assertIn("SHA-256", output)
            self.assertIn("no external report was parsed", output)

    def test_acceptance_doctor_checks_helpers_ledger_context_and_dangerous_actions(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            store.save_persistent_memory([])
            _create_healthy_export_dirs(project_root)
            _write_milestone_fixture(project_root)
            with patch("proto_mind.acceptance_layer.AcceptanceReview.read_state", return_value=_acceptance_state()):
                output = format_acceptance_command("/acceptance doctor", project_root=project_root, memory_store=store)

            self.assertIn("Acceptance Review Doctor", output)
            self.assertIn("Status: OK", output)
            self.assertIn("All acceptance commands are registered", output)
            self.assertIn("read-only with mutates=none", output)
            self.assertIn("Focus, Pre-Change, Agenda, Session, Milestone, Warning, and Export helpers are reachable", output)
            self.assertIn("Accepted-known warnings ledger is reachable", output)
            self.assertIn("Warning readiness is computable", output)
            self.assertIn("Context Injection is disabled", output)
            self.assertIn("No automatic decision, execution, persistence, backup, snapshot, repair, cleanup, migration, deletion, move, or compression action is exposed", output)

    def test_acceptance_doctor_warns_without_changing_explicit_context_enablement(self) -> None:
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
                "proto_mind.acceptance_layer.AcceptanceReview.read_state",
                return_value=_acceptance_state(context_state="enabled"),
            ):
                output = format_acceptance_command("/acceptance doctor", project_root=project_root, memory_store=store)

            self.assertIn("Status: WARN", output)
            self.assertIn("Context Injection is explicitly enabled", output)
            self.assertEqual(settings_path.read_bytes(), before)
            self.assertTrue(json.loads(settings_path.read_text(encoding="utf-8"))["enabled"])

    def test_acceptance_commands_are_read_only_through_shared_handler(self) -> None:
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
                    "/acceptance status",
                    "/acceptance checklist",
                    "/acceptance criteria",
                    "/acceptance decision-guide",
                    "/acceptance doctor",
                    "/acceptance handoff",
                )
            ]

            self.assertIn("Acceptance Review Status", outputs[0])
            self.assertIn("Acceptance Review Manual Checklist", outputs[1])
            self.assertIn("Reusable Acceptance Criteria", outputs[2])
            self.assertIn("Acceptance Decision Guide", outputs[3])
            self.assertIn("Acceptance Review Doctor", outputs[4])
            self.assertIn("Proto-Mind Acceptance Review Handoff", outputs[5])
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

    def test_baseline_status_reports_warn_baseline_and_safe_review(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            with patch("proto_mind.baseline_layer.SnapshotBaselineRegistry.read_state", return_value=_baseline_state()):
                output = format_baseline_command("/baseline status", project_root=project_root, memory_store=store)

            self.assertIn("Snapshot Baseline Registry Status", output)
            self.assertIn("Status: WARN", output)
            self.assertIn("command_registry: commands=387 categories=41", output)
            self.assertIn("accepted_baseline: Snapshot Baseline Registry v1", output)
            self.assertIn("latest_snapshot: snapshot.json", output)
            self.assertIn("latest_snapshot_diff: diff.json", output)
            self.assertIn("accepted_known_warnings: 12", output)
            self.assertIn("unknown_warnings: 0", output)
            self.assertIn("blockers: 0", output)
            self.assertIn("baseline_review_safe: true", output)

    def test_baseline_status_blocks_unknown_warnings_or_blockers(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            with patch(
                "proto_mind.baseline_layer.SnapshotBaselineRegistry.read_state",
                return_value=_baseline_state(unknown=True, blockers=1),
            ):
                output = format_baseline_command("/baseline status", project_root=project_root, memory_store=store)

            self.assertIn("Status: BLOCKED", output)
            self.assertIn("unknown_warnings: 1", output)
            self.assertIn("blockers: 1", output)
            self.assertIn("baseline_review_safe: false", output)

    def test_baseline_current_separates_detected_inferred_and_unknown_fields(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            with patch("proto_mind.baseline_layer.SnapshotBaselineRegistry.read_state", return_value=_baseline_state()):
                output = format_baseline_command("/baseline current", project_root=project_root, memory_store=store)

            self.assertIn("Current Detected Accepted Baseline", output)
            self.assertIn("Detected facts:", output)
            self.assertIn("671 tests OK", output)
            self.assertIn("accepted=12, unknown=0, blockers=0", output)
            self.assertIn("Context Injection: disabled", output)
            self.assertIn("Inferred baseline:", output)
            self.assertIn("safe for manual baseline review: true", output)
            self.assertIn("Unknown / undetected fields:\n- none", output)

    def test_baseline_latest_reports_existing_snapshot_signals_without_creation(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            with patch("proto_mind.baseline_layer.SnapshotBaselineRegistry.read_state", return_value=_baseline_state()):
                output = format_baseline_command("/baseline latest", project_root=project_root, memory_store=store)

            self.assertIn("Latest Snapshot / Diff Baseline Signals", output)
            self.assertIn("snapshot.json", output)
            self.assertIn("diff.json", output)
            self.assertIn("manual_review: RECOMMENDED", output)
            self.assertIn("No snapshot, diff, export, backup, or command was created or run", output)

    def test_baseline_checklist_is_manual_and_complete(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")

            output = format_baseline_command("/baseline checklist", project_root=project_root, memory_store=store)

            self.assertIn("Accepted Baseline Manual Checklist", output)
            for expected in (
                "/acceptance checklist",
                "scripts/run_tests.sh",
                "compileall",
                "manual smoke",
                "Context Injection remains disabled",
                "unknown warnings = 0",
                "SHA-256",
                "snapshot diff",
                "architecture docs/ledger",
                "/session handoff-brief",
            ):
                self.assertIn(expected, output)
            self.assertIn("no check, command, snapshot, backup, baseline record", output)

    def test_baseline_handoff_prints_copyable_detected_baseline(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            with patch("proto_mind.baseline_layer.SnapshotBaselineRegistry.read_state", return_value=_baseline_state()):
                output = format_baseline_command("/baseline handoff", project_root=project_root, memory_store=store)

            self.assertIn("Proto-Mind Accepted Baseline Handoff", output)
            self.assertIn("Registry: 387 commands across 41 categories", output)
            self.assertIn("Tests: 671 tests OK", output)
            self.assertIn("Warnings: accepted=12, unknown=0, blockers=0", output)
            self.assertIn("Context Injection: disabled", output)
            self.assertIn("Latest snapshot: snapshot.json", output)
            self.assertIn("Rule 0:", output)
            self.assertIn("Verification commands:", output)
            self.assertIn("no file, clipboard, external call, baseline record, snapshot, backup, or command execution", output)

    def test_baseline_doctor_checks_helpers_ledgers_context_and_safety(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            store.save_persistent_memory([])
            _create_healthy_export_dirs(project_root)
            _write_milestone_fixture(project_root)
            with patch("proto_mind.baseline_layer.SnapshotBaselineRegistry.read_state", return_value=_baseline_state()):
                output = format_baseline_command("/baseline doctor", project_root=project_root, memory_store=store)

            self.assertIn("Snapshot Baseline Registry Doctor", output)
            self.assertIn("Status: OK", output)
            self.assertIn("All baseline commands are registered", output)
            self.assertIn("read-only with mutates=none", output)
            self.assertIn("Snapshot, diff, Acceptance, Focus, Pre-Change, and Warning helpers are reachable", output)
            self.assertIn("Architect Ledger is reachable", output)
            self.assertIn("Accepted-known warnings ledger is reachable", output)
            self.assertIn("Context Injection is disabled", output)
            self.assertIn("No snapshot, backup, persistence, execution, repair, cleanup, migration, deletion, move, or compression action is exposed", output)

    def test_baseline_doctor_warns_without_changing_enabled_context(self) -> None:
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
                "proto_mind.baseline_layer.SnapshotBaselineRegistry.read_state",
                return_value=_baseline_state(context_state="enabled"),
            ):
                output = format_baseline_command("/baseline doctor", project_root=project_root, memory_store=store)

            self.assertIn("Status: WARN", output)
            self.assertIn("Context Injection is explicitly enabled", output)
            self.assertEqual(settings_path.read_bytes(), before)
            self.assertTrue(json.loads(settings_path.read_text(encoding="utf-8"))["enabled"])

    def test_baseline_commands_are_read_only_through_shared_handler(self) -> None:
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
                    "/baseline status",
                    "/baseline current",
                    "/baseline latest",
                    "/baseline checklist",
                    "/baseline doctor",
                    "/baseline handoff",
                )
            ]

            self.assertIn("Snapshot Baseline Registry Status", outputs[0])
            self.assertIn("Current Detected Accepted Baseline", outputs[1])
            self.assertIn("Latest Snapshot / Diff Baseline Signals", outputs[2])
            self.assertIn("Accepted Baseline Manual Checklist", outputs[3])
            self.assertIn("Snapshot Baseline Registry Doctor", outputs[4])
            self.assertIn("Proto-Mind Accepted Baseline Handoff", outputs[5])
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

    def test_closure_status_reports_warn_baseline_and_safe_handoff(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            with patch("proto_mind.closure_layer.PostAcceptanceClosure.read_state", return_value=_closure_state()):
                output = format_closure_command("/closure status", project_root=project_root, memory_store=store)

            self.assertIn("Post-Acceptance Closure Status", output)
            self.assertIn("Status: WARN", output)
            self.assertIn("command_registry: commands=387 categories=41", output)
            self.assertIn("context_injection: disabled", output)
            self.assertIn("baseline_review: WARN", output)
            self.assertIn("acceptance_review: WARN", output)
            self.assertIn("accepted_known_warnings: 12", output)
            self.assertIn("unknown_warnings: 0", output)
            self.assertIn("blockers: 0", output)
            self.assertIn("closure_handoff_safe: true", output)

    def test_closure_status_blocks_unknown_warnings_or_blockers(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            with patch(
                "proto_mind.closure_layer.PostAcceptanceClosure.read_state",
                return_value=_closure_state(unknown=True, blockers=1),
            ):
                output = format_closure_command("/closure status", project_root=project_root, memory_store=store)

            self.assertIn("Status: BLOCKED", output)
            self.assertIn("unknown_warnings: 1", output)
            self.assertIn("blockers: 1", output)
            self.assertIn("closure_handoff_safe: false", output)

    def test_closure_summary_contains_baseline_layers_invariants_and_wrap_up(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            with patch("proto_mind.closure_layer.PostAcceptanceClosure.read_state", return_value=_closure_state()):
                output = format_closure_command("/closure summary", project_root=project_root, memory_store=store)

            self.assertIn("Post-Acceptance Session Closure Summary", output)
            self.assertIn("Snapshot Baseline Registry v1", output)
            self.assertIn("registry: 387 commands across 41 categories", output)
            self.assertIn("tests: 671 tests OK", output)
            self.assertIn("accepted=12, unknown=0, blockers=0", output)
            self.assertIn("Latest accepted operating layers:", output)
            self.assertIn("Context Injection disabled: true", output)
            self.assertIn("/baseline current", output)
            self.assertIn("/session end-summary", output)
            self.assertIn("/closure handoff", output)
            self.assertIn("Rule 0 backup/checkpoint", output)

    def test_closure_next_hands_off_to_plan_layer_and_manual_v211(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            with patch("proto_mind.closure_layer.PostAcceptanceClosure.read_state", return_value=_closure_state()):
                output = format_closure_command("/closure next", project_root=project_root, memory_store=store)

            self.assertIn("Post-Acceptance Next Manual Action", output)
            self.assertIn("separately scoped real runner task", output)
            self.assertIn("/activation preconditions and /runner-mvp design", output)
            self.assertIn("manual_command: /runner-mvp design", output)
            self.assertIn("No automatic execution", output)

    def test_closure_next_prioritizes_unknown_then_blockers(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            with patch(
                "proto_mind.closure_layer.PostAcceptanceClosure.read_state",
                return_value=_closure_state(unknown=True, blockers=1),
            ):
                unknown = format_closure_command("/closure next", project_root=project_root, memory_store=store)
            with patch(
                "proto_mind.closure_layer.PostAcceptanceClosure.read_state",
                return_value=_closure_state(blockers=1),
            ):
                blocked = format_closure_command("/closure next", project_root=project_root, memory_store=store)

            self.assertIn("Inspect unknown warnings", unknown)
            self.assertIn("manual_command: /warnings unknown", unknown)
            self.assertIn("Resolve or explicitly review current blockers", blocked)
            self.assertIn("manual_command: /acceptance status", blocked)

    def test_closure_handoff_prints_copyable_next_session_context(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            with patch("proto_mind.closure_layer.PostAcceptanceClosure.read_state", return_value=_closure_state()):
                output = format_closure_command("/closure handoff", project_root=project_root, memory_store=store)

            self.assertIn("Proto-Mind Post-Acceptance Handoff", output)
            self.assertIn(f"Project: {project_root}", output)
            self.assertIn("Registry: 387 commands across 41 categories", output)
            self.assertIn("Tests: 671 tests OK", output)
            self.assertIn("Context Injection: disabled", output)
            self.assertIn("Warnings: accepted=12, unknown=0, blockers=0", output)
            self.assertIn("Operator command families:", output)
            self.assertIn("/acceptance; /baseline; /closure", output)
            self.assertIn("Rule 0:", output)
            self.assertIn("Verification commands:", output)
            self.assertIn("real v3.0 runner requires a separate explicit task", output)
            self.assertIn("no clipboard, file, external call, closure log/state", output)

    def test_closure_doctor_checks_helpers_ledger_context_and_safety(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            store.save_persistent_memory([])
            _create_healthy_export_dirs(project_root)
            _write_milestone_fixture(project_root)
            with patch("proto_mind.closure_layer.PostAcceptanceClosure.read_state", return_value=_closure_state()):
                output = format_closure_command("/closure doctor", project_root=project_root, memory_store=store)

            self.assertIn("Post-Acceptance Closure Doctor", output)
            self.assertIn("Status: OK", output)
            self.assertIn("All closure commands are registered", output)
            self.assertIn("read-only with mutates=none", output)
            self.assertIn("Baseline, Acceptance, Focus, Pre-Change, Agenda, Session, Milestone, Warning, Export, and Snapshot helpers are reachable", output)
            self.assertIn("Accepted-known warnings ledger is reachable", output)
            self.assertIn("Warning state is computable", output)
            self.assertIn("Context Injection is disabled", output)
            self.assertIn("No execution, persistence, snapshot, backup, repair, cleanup, migration, deletion, move, compression, or external action is exposed", output)

    def test_closure_doctor_warns_without_changing_enabled_context(self) -> None:
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
                "proto_mind.closure_layer.PostAcceptanceClosure.read_state",
                return_value=_closure_state(context_state="enabled"),
            ):
                output = format_closure_command("/closure doctor", project_root=project_root, memory_store=store)

            self.assertIn("Status: WARN", output)
            self.assertIn("Context Injection is explicitly enabled", output)
            self.assertEqual(settings_path.read_bytes(), before)
            self.assertTrue(json.loads(settings_path.read_text(encoding="utf-8"))["enabled"])

    def test_closure_commands_are_read_only_through_shared_handler(self) -> None:
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
                    "/closure status",
                    "/closure summary",
                    "/closure next",
                    "/closure handoff",
                    "/closure doctor",
                )
            ]

            self.assertIn("Post-Acceptance Closure Status", outputs[0])
            self.assertIn("Post-Acceptance Session Closure Summary", outputs[1])
            self.assertIn("Post-Acceptance Next Manual Action", outputs[2])
            self.assertIn("Proto-Mind Post-Acceptance Handoff", outputs[3])
            self.assertIn("Post-Acceptance Closure Doctor", outputs[4])
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

    def test_capability_status_reports_warn_baseline_and_safe_generation(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            with patch("proto_mind.capability_map.CommandCapabilityMap.read_state", return_value=_capability_state()):
                output = format_capability_command("/capabilities status", project_root=project_root, memory_store=store)

            self.assertIn("Command Family Index Status", output)
            self.assertIn("Status: WARN", output)
            self.assertIn("command_registry: commands=387 categories=41", output)
            self.assertIn("context_injection: disabled", output)
            self.assertIn("accepted_known_warnings: 12", output)
            self.assertIn("unknown_warnings: 0", output)
            self.assertIn("blockers: 0", output)
            self.assertIn("detected_command_families: 41", output)
            self.assertIn("capability_map_generation_safe: true", output)
            self.assertIn("local_typed_contracts: 4", output)
            self.assertIn("contract_transport: none", output)
            self.assertIn("external_contract_exposure: false", output)

    def test_capability_status_blocks_unknown_warnings_or_blockers(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            with patch(
                "proto_mind.capability_map.CommandCapabilityMap.read_state",
                return_value=_capability_state(unknown=True, blockers=1),
            ):
                output = format_capability_command("/capabilities status", project_root=project_root, memory_store=store)

            self.assertIn("Status: BLOCKED", output)
            self.assertIn("unknown_warnings: 1", output)
            self.assertIn("blockers: 1", output)
            self.assertIn("capability_map_generation_safe: false", output)

    def test_capability_list_includes_core_and_registry_derived_families(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")

            output = format_capability_command("/capabilities list", project_root=project_root, memory_store=store)

            self.assertIn("Command Family Index", output)
            for family in (
                "/daily",
                "/session",
                "/milestone",
                "/warnings",
                "/agenda",
                "/prechange",
                "/focus",
                "/acceptance",
                "/baseline",
                "/closure",
                "/memory-card",
                "/exports",
                "/proto snapshot-diff",
            ):
                self.assertIn(family, output)
            self.assertIn("Other registered Registry categories:", output)
            self.assertIn("mixed / potentially mutating", output)
            self.assertIn("Undocumented or unregistered behavior is UNKNOWN, not SAFE", output)
            self.assertIn("No command executed", output)

    def test_capability_map_groups_manual_workflow_phases(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")

            output = format_capability_command("/capabilities map", project_root=project_root, memory_store=store)

            for phase in ("Awareness:", "Pre-work:", "Implementation support:", "Review:", "Closure / handoff:", "Maintenance:"):
                self.assertIn(phase, output)
            self.assertIn("/memory-card codex", output)
            self.assertIn("/acceptance criteria", output)
            self.assertIn("/proto snapshot-diff-status", output)
            self.assertIn("runtime mode: read-only for the listed commands", output)
            self.assertIn("awareness → prechange → focus", output)
            self.assertIn("Local Typed Capability Contracts", output)
            self.assertIn("result_envelope: structuredContent + content + _meta", output)
            self.assertIn("warnings_unknown -> /warnings unknown", output)
            self.assertIn("transport: none", output)
            self.assertIn("did not run any listed command", output)

    def test_capability_safety_uses_registry_and_policy_conservatively(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")

            output = format_capability_command("/capabilities safety", project_root=project_root, memory_store=store)

            self.assertIn("Command Capability Safety Classification", output)
            self.assertIn("Read-only operator layers:", output)
            self.assertIn("Docs / test implementation boundary:", output)
            self.assertIn("Potentially mutating or dangerous commands:", output)
            self.assertIn("Action Policy classes:", output)
            self.assertIn("confirmation-required examples:", output)
            self.assertIn("operator-only examples:", output)
            self.assertIn("UNKNOWN capability and blocked", output)
            for gate in ("Rule 0 backup/checkpoint", "/prechange status", "/warnings unknown", "/acceptance criteria", "/baseline current"):
                self.assertIn(gate, output)
            self.assertIn("Local typed contract boundary:", output)
            self.assertIn("Result shape is structuredContent + content + _meta", output)
            self.assertIn("no MCP server or network adapter is installed", output)
            self.assertIn("executes nothing and grants no authorization", output)

    def test_capability_handoff_prints_copyable_family_context(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            with patch("proto_mind.capability_map.CommandCapabilityMap.read_state", return_value=_capability_state()):
                output = format_capability_command("/capabilities handoff", project_root=project_root, memory_store=store)

            self.assertIn("Proto-Mind Capability Handoff", output)
            self.assertIn(f"Project: {project_root}", output)
            self.assertIn("Registry: 387 commands across 41 categories/families", output)
            self.assertIn("Key families:", output)
            self.assertIn("accepted=12, unknown=0, blockers=0", output)
            self.assertIn("Context Injection: disabled", output)
            self.assertIn("Safety gates:", output)
            self.assertIn("prechange → focus → dry-run plan → human-controlled Codex task", output)
            self.assertIn("/runner-mvp handoff", output)
            self.assertIn("no clipboard, command, model, file, capability state, snapshot, backup, or external call", output)

    def test_capability_doctor_checks_registry_helpers_context_and_safety(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            store.save_persistent_memory([])
            _create_healthy_export_dirs(project_root)
            _write_milestone_fixture(project_root)
            with patch("proto_mind.capability_map.CommandCapabilityMap.read_state", return_value=_capability_state()):
                output = format_capability_command("/capabilities doctor", project_root=project_root, memory_store=store)

            self.assertIn("Command Capability Map Doctor", output)
            self.assertIn("Status: OK", output)
            self.assertIn("All capability commands are registered", output)
            self.assertIn("read-only with mutates=none", output)
            self.assertIn("Command Registry is reachable and healthy", output)
            self.assertIn("Local capability contracts are healthy: 4 exact read-only zero-argument contracts", output)
            self.assertIn("Memory Card, Closure, Baseline, Acceptance, Focus, Pre-Change, Agenda, Session, Milestone, Warning, Export, and Snapshot helpers are reachable", output)
            self.assertIn("Warning state is computable", output)
            self.assertIn("Context Injection is disabled", output)
            self.assertIn("No execution, persistence, clipboard, snapshot, backup, repair, cleanup, migration, deletion, move, compression, or external action is exposed", output)

    def test_capability_doctor_warns_without_changing_enabled_context(self) -> None:
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
                "proto_mind.capability_map.CommandCapabilityMap.read_state",
                return_value=_capability_state(context_state="enabled"),
            ):
                output = format_capability_command("/capabilities doctor", project_root=project_root, memory_store=store)

            self.assertIn("Status: WARN", output)
            self.assertIn("Context Injection is explicitly enabled", output)
            self.assertEqual(settings_path.read_bytes(), before)
            self.assertTrue(json.loads(settings_path.read_text(encoding="utf-8"))["enabled"])

    def test_capability_commands_are_read_only_through_shared_handler(self) -> None:
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
                    "/capabilities status",
                    "/capabilities list",
                    "/capabilities map",
                    "/capabilities safety",
                    "/capabilities doctor",
                    "/capabilities handoff",
                )
            ]

            self.assertIn("Command Family Index Status", outputs[0])
            self.assertIn("Command Family Index", outputs[1])
            self.assertIn("Workflow Capability Map", outputs[2])
            self.assertIn("Safety Classification", outputs[3])
            self.assertIn("Command Capability Map Doctor", outputs[4])
            self.assertIn("Proto-Mind Capability Handoff", outputs[5])
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

    def test_plan_status_reports_warn_safe_and_blocks_unknown_state(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            with patch("proto_mind.plan_layer.ActionDryRunPlan.read_state", return_value=_plan_state()):
                ready = format_plan_command("/plan status", project_root=project_root, memory_store=store)
            with patch(
                "proto_mind.plan_layer.ActionDryRunPlan.read_state",
                return_value=_plan_state(unknown=True, blockers=1),
            ):
                blocked = format_plan_command("/plan status", project_root=project_root, memory_store=store)

            self.assertIn("Proposed Action Plan Status", ready)
            self.assertIn("Status: WARN", ready)
            self.assertIn("command_registry: commands=387 categories=41", ready)
            self.assertIn("context_injection: disabled", ready)
            self.assertIn("capability_map_readiness: WARN", ready)
            self.assertIn("accepted_known_warnings: 12", ready)
            self.assertIn("unknown_warnings: 0", ready)
            self.assertIn("blockers: 0", ready)
            self.assertIn("dry_run_planning_safe: true", ready)
            self.assertIn("Status: BLOCKED", blocked)
            self.assertIn("unknown_warnings: 1", blocked)
            self.assertIn("blockers: 1", blocked)
            self.assertIn("dry_run_planning_safe: false", blocked)

    def test_plan_next_proposes_manual_v211_with_evidence_and_done_criteria(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            with patch("proto_mind.plan_layer.ActionDryRunPlan.read_state", return_value=_plan_state()):
                output = format_plan_command("/plan next", project_root=project_root, memory_store=store)

            self.assertIn("Proposed Next Action Plan", output)
            self.assertIn("locked read-only Runner MVP design", output)
            self.assertIn("/capabilities map", output)
            self.assertIn("/plan gates", output)
            self.assertIn("/memory-card codex", output)
            self.assertIn("Risk class: LOW", output)
            self.assertIn("Required gates:", output)
            self.assertIn("Expected evidence:", output)
            self.assertIn("Done criteria:", output)
            self.assertIn("No execution:", output)

    def test_plan_next_prioritizes_unknown_then_blockers(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            with patch(
                "proto_mind.plan_layer.ActionDryRunPlan.read_state",
                return_value=_plan_state(unknown=True, blockers=1),
            ):
                unknown = format_plan_command("/plan next", project_root=project_root, memory_store=store)
            with patch(
                "proto_mind.plan_layer.ActionDryRunPlan.read_state",
                return_value=_plan_state(blockers=1),
            ):
                blocked = format_plan_command("/plan next", project_root=project_root, memory_store=store)

            self.assertIn("Inspect unknown warnings", unknown)
            self.assertIn("/warnings unknown", unknown)
            self.assertIn("Risk class: BLOCKED", unknown)
            self.assertIn("Resolve current blockers", blocked)
            self.assertIn("/acceptance status", blocked)

    def test_plan_dry_run_prints_complete_template_without_parsing(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")

            output = format_plan_command("/plan dry-run", project_root=project_root, memory_store=store)

            for section in (
                "Operator Intent:",
                "Proposed Commands:",
                "Command Safety Classification:",
                "Required Gates:",
                "Forbidden Actions:",
                "Expected Evidence:",
                "Acceptance Criteria:",
                "Rollback / Stop Conditions:",
                "Human Confirmation Required:",
            ):
                self.assertIn(section, output)
            self.assertIn("UNKNOWN if unregistered", output)
            self.assertIn("No free text was parsed", output)
            self.assertIn("no plan or confirmation was stored", output)

    def test_plan_gates_lists_every_required_safety_boundary(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")

            output = format_plan_command("/plan gates", project_root=project_root, memory_store=store)

            for gate in (
                "Rule 0 backup/checkpoint",
                "/warnings unknown must report 0",
                "Blocker count must be 0",
                "Context Injection must remain disabled",
                "/capabilities safety",
                "explicit human confirmation",
                "dry-run plan must be shown",
                "Allowed writes and forbidden writes",
                "Verification commands and expected evidence",
                "SHA-256 against Rule 0",
            ):
                self.assertIn(gate, output)
            self.assertIn("failed or unknown gate means STOP", output)
            self.assertIn("cannot waive, satisfy, or execute", output)

    def test_plan_handoff_contains_policy_gates_verification_and_report_fields(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            with patch("proto_mind.plan_layer.ActionDryRunPlan.read_state", return_value=_plan_state()):
                output = format_plan_command("/plan handoff", project_root=project_root, memory_store=store)

            self.assertIn("Proto-Mind Dry-Run Planning Handoff", output)
            self.assertIn(f"Project: {project_root}", output)
            self.assertIn("Rule 0:", output)
            self.assertIn("Registry: 387 commands across 41 categories", output)
            self.assertIn("auto_allowed=291", output)
            self.assertIn("accepted=12, unknown=0, blockers=0", output)
            self.assertIn("Context Injection: disabled", output)
            self.assertIn("Execution and authorization are forbidden", output)
            self.assertIn("Required gates:", output)
            self.assertIn("Verification commands:", output)
            self.assertIn("Required final report fields:", output)
            self.assertIn("no clipboard, command, model, plan state, approval, authorization", output)

    def test_plan_doctor_checks_helpers_context_and_no_execution(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            store.save_persistent_memory([])
            _create_healthy_export_dirs(project_root)
            _write_milestone_fixture(project_root)
            with patch("proto_mind.plan_layer.ActionDryRunPlan.read_state", return_value=_plan_state()):
                output = format_plan_command("/plan doctor", project_root=project_root, memory_store=store)

            self.assertIn("Proposed Action Plan Doctor", output)
            self.assertIn("Status: OK", output)
            self.assertIn("All plan commands are registered", output)
            self.assertIn("read-only with mutates=none", output)
            self.assertIn("Capability Map, Warning, Baseline, Pre-Change, Focus, Acceptance, Memory Card, and Milestone helpers are reachable", output)
            self.assertIn("Warning state is computable", output)
            self.assertIn("Context Injection is disabled", output)
            self.assertIn("No execution, authorization, approval, persistence, clipboard, snapshot, backup, repair, cleanup, migration, deletion, move, compression, or external action is exposed", output)

    def test_plan_doctor_warns_without_changing_enabled_context(self) -> None:
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
                "proto_mind.plan_layer.ActionDryRunPlan.read_state",
                return_value=_plan_state(context_state="enabled"),
            ):
                output = format_plan_command("/plan doctor", project_root=project_root, memory_store=store)

            self.assertIn("Status: WARN", output)
            self.assertIn("Context Injection is explicitly enabled", output)
            self.assertEqual(settings_path.read_bytes(), before)
            self.assertTrue(json.loads(settings_path.read_text(encoding="utf-8"))["enabled"])

    def test_plan_commands_are_read_only_through_shared_handler(self) -> None:
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
                    "/plan status",
                    "/plan next",
                    "/plan dry-run",
                    "/plan gates",
                    "/plan doctor",
                    "/plan handoff",
                )
            ]

            self.assertIn("Proposed Action Plan Status", outputs[0])
            self.assertIn("Proposed Next Action Plan", outputs[1])
            self.assertIn("Dry-Run Action Plan Template", outputs[2])
            self.assertIn("Future Execution Safety Gates", outputs[3])
            self.assertIn("Proposed Action Plan Doctor", outputs[4])
            self.assertIn("Proto-Mind Dry-Run Planning Handoff", outputs[5])
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

    def test_confirmation_status_reports_warn_baseline_and_safe_generation(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            with patch("proto_mind.confirmation_layer.ConfirmationVocabulary.read_state", return_value=_confirmation_state()):
                output = format_confirmation_command("/confirm status", project_root=project_root, memory_store=store)

            self.assertIn("Confirmation Gate Vocabulary Status", output)
            self.assertIn("Status: WARN", output)
            self.assertIn("command_registry: commands=387 categories=41", output)
            self.assertIn("context_injection: disabled", output)
            self.assertIn("accepted_known_warnings: 12", output)
            self.assertIn("unknown_warnings: 0", output)
            self.assertIn("blockers: 0", output)
            self.assertIn("confirmation_policy_generation_safe: true", output)
            self.assertIn("no approval, authorization, confirmation phrase, command, or runtime state was captured or executed", output)

    def test_confirmation_status_blocks_unknown_warnings_or_blockers(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            with patch(
                "proto_mind.confirmation_layer.ConfirmationVocabulary.read_state",
                return_value=_confirmation_state(unknown=True, blockers=1),
            ):
                output = format_confirmation_command("/confirm status", project_root=project_root, memory_store=store)

            self.assertIn("Status: BLOCKED", output)
            self.assertIn("unknown_warnings: 1", output)
            self.assertIn("blockers: 1", output)
            self.assertIn("confirmation_policy_generation_safe: false", output)

    def test_confirmation_policy_is_advisory_and_blocks_unsafe_assumptions(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")

            output = format_confirmation_command("/confirm policy", project_root=project_root, memory_store=store)

            self.assertIn("Proto-Mind Confirmation Policy (Advisory)", output)
            self.assertIn("Mutating commands require explicit, task-specific human confirmation", output)
            self.assertIn("Operator-only commands must never be auto-executed", output)
            self.assertIn("Unknown or unregistered commands are BLOCKED", output)
            self.assertIn("does not enforce, capture, grant, or persist authorization", output)

    def test_confirmation_levels_define_all_authorization_classes(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")

            output = format_confirmation_command("/confirm levels", project_root=project_root, memory_store=store)

            self.assertIn("Authorization / Confirmation Vocabulary", output)
            for level in ("NONE:", "READ_ONLY_MANUAL:", "CONFIRM_REQUIRED:", "ELEVATED_CONFIRM_REQUIRED:", "OPERATOR_ONLY:", "BLOCKED:"):
                self.assertIn(level, output)
            self.assertIn("grant no runtime authorization", output)

    def test_confirmation_requirements_report_registry_classes_and_gates(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")

            output = format_confirmation_command("/confirm requirements", project_root=project_root, memory_store=store)

            self.assertIn("Confirmation Requirements By Capability Class", output)
            self.assertIn("read-only (292): READ_ONLY_MANUAL", output)
            self.assertIn("mutating (95): CONFIRM_REQUIRED", output)
            self.assertIn("high-risk (4): ELEVATED_CONFIRM_REQUIRED", output)
            self.assertIn("confirmation-required (92)", output)
            self.assertIn("operator-only (4)", output)
            self.assertIn("Rule 0 backup/checkpoint is complete", output)
            self.assertIn("No user input is parsed as confirmation", output)

    def test_confirmation_handoff_contains_vocabulary_gates_and_next_milestone(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            with patch("proto_mind.confirmation_layer.ConfirmationVocabulary.read_state", return_value=_confirmation_state()):
                output = format_confirmation_command("/confirm handoff", project_root=project_root, memory_store=store)

            self.assertIn("Proto-Mind Confirmation Vocabulary Handoff", output)
            self.assertIn("Registry: 387 commands across 41 categories", output)
            self.assertIn("NONE | READ_ONLY_MANUAL | CONFIRM_REQUIRED", output)
            self.assertIn("Execution, approval capture, and authorization remain forbidden", output)
            self.assertIn("/runner-mvp confirmation", output)

    def test_confirmation_doctor_checks_registry_context_and_no_execution(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            with patch("proto_mind.confirmation_layer.ConfirmationVocabulary.read_state", return_value=_confirmation_state()):
                output = format_confirmation_command("/confirm doctor", project_root=project_root, memory_store=store)

            self.assertIn("Confirmation Vocabulary Doctor", output)
            self.assertIn("Status: OK", output)
            self.assertIn("All confirm commands are registered", output)
            self.assertIn("read-only with mutates=none", output)
            self.assertIn("Context Injection is disabled", output)
            self.assertIn("No execution, approval capture, authorization, persistence", output)

    def test_confirmation_doctor_warns_without_changing_enabled_context(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            format_context_command("/context injection enable", project_root=project_root)
            settings_path = project_root / "proto_mind" / "data" / "context_injection.json"
            before = settings_path.read_bytes()
            with patch(
                "proto_mind.confirmation_layer.ConfirmationVocabulary.read_state",
                return_value=_confirmation_state(context_state="enabled"),
            ):
                output = format_confirmation_command("/confirm doctor", project_root=project_root, memory_store=store)

            self.assertIn("Status: WARN", output)
            self.assertIn("Context Injection is explicitly enabled", output)
            self.assertEqual(settings_path.read_bytes(), before)
            self.assertTrue(json.loads(settings_path.read_text(encoding="utf-8"))["enabled"])

    def test_confirmation_commands_are_read_only_through_shared_handler(self) -> None:
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
                    "/confirm status",
                    "/confirm policy",
                    "/confirm levels",
                    "/confirm requirements",
                    "/confirm doctor",
                    "/confirm handoff",
                )
            ]

            self.assertIn("Confirmation Gate Vocabulary Status", outputs[0])
            self.assertIn("Proto-Mind Confirmation Policy (Advisory)", outputs[1])
            self.assertIn("Authorization / Confirmation Vocabulary", outputs[2])
            self.assertIn("Confirmation Requirements By Capability Class", outputs[3])
            self.assertIn("Confirmation Vocabulary Doctor", outputs[4])
            self.assertIn("Proto-Mind Confirmation Vocabulary Handoff", outputs[5])
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

    def test_sandbox_status_reports_warn_baseline_and_safe_generation(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            with patch("proto_mind.sandbox_layer.ExecutionSandboxBlueprint.read_state", return_value=_sandbox_state()):
                output = format_sandbox_command("/sandbox status", project_root=project_root, memory_store=store)

            self.assertIn("Execution Sandbox Blueprint Status", output)
            self.assertIn("Status: WARN", output)
            self.assertIn("command_registry: commands=387 categories=41", output)
            self.assertIn("context_injection: disabled", output)
            self.assertIn("confirmation_gate_readiness: WARN", output)
            self.assertIn("accepted_known_warnings: 12", output)
            self.assertIn("unknown_warnings: 0", output)
            self.assertIn("blockers: 0", output)
            self.assertIn("sandbox_blueprint_generation_safe: true", output)
            self.assertIn("no runner, command, subprocess, shell, eval/exec", output)

    def test_sandbox_status_blocks_unknown_warnings_or_blockers(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            with patch(
                "proto_mind.sandbox_layer.ExecutionSandboxBlueprint.read_state",
                return_value=_sandbox_state(unknown=True, blockers=1),
            ):
                output = format_sandbox_command("/sandbox status", project_root=project_root, memory_store=store)

            self.assertIn("Status: BLOCKED", output)
            self.assertIn("unknown_warnings: 1", output)
            self.assertIn("blockers: 1", output)
            self.assertIn("sandbox_blueprint_generation_safe: false", output)

    def test_sandbox_blueprint_defines_phases_invariants_and_no_runner(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")

            output = format_sandbox_command("/sandbox blueprint", project_root=project_root, memory_store=store)

            self.assertIn("Future Command Runner Blueprint (Design Only)", output)
            for phase in ("Intent parsing", "Capability lookup", "Risk classification", "Dry-run plan", "Gates check", "Explicit confirmation", "Scoped execution", "Evidence capture", "Post-run acceptance review"):
                self.assertIn(phase, output)
            self.assertIn("No direct shell by default", output)
            self.assertIn("No execution-capable runner code is created or invoked", output)

    def test_sandbox_boundaries_are_project_scoped_and_advisory(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")

            output = format_sandbox_command("/sandbox boundaries", project_root=project_root, memory_store=store)

            self.assertIn("Future Execution Sandbox Boundaries (Advisory)", output)
            self.assertIn(f"allowed project root: {project_root}", output)
            self.assertIn("proto_mind/data", output)
            self.assertIn("proto_mind/exports", output)
            self.assertIn("backups", output)
            self.assertIn("deletion, move/rename, destructive overwrite", output)
            self.assertIn("No path access or operation was attempted", output)

    def test_sandbox_allowlist_marks_only_future_candidates(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")

            output = format_sandbox_command("/sandbox allowlist", project_root=project_root, memory_store=store)

            self.assertIn("Proposed Initial Future Runner Allowlist", output)
            self.assertIn("Status: DESIGN_ONLY", output)
            for command in ("/daily doctor", "/warnings unknown", "/confirm policy", "/exports doctor", "/session handoff-brief"):
                self.assertIn(f"FUTURE_CANDIDATE: {command}", output)
            self.assertIn("not an active allowlist", output)

    def test_sandbox_denied_blocks_dangerous_classes(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")

            output = format_sandbox_command("/sandbox denied", project_root=project_root, memory_store=store)

            self.assertIn("Denied / Blocked Future Runner Classes", output)
            self.assertIn("Unknown or unregistered commands: BLOCKED", output)
            self.assertIn("Operator-only commands: never auto-execute", output)
            self.assertIn("Context Injection changes without a dedicated explicit task: BLOCKED", output)
            self.assertIn("Shell, subprocess, pipeline, eval, or exec execution in this layer: BLOCKED", output)
            self.assertIn("no runner or authorization engine exists", output)

    def test_sandbox_handoff_contains_blueprint_gates_and_v213_boundary(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            with patch("proto_mind.sandbox_layer.ExecutionSandboxBlueprint.read_state", return_value=_sandbox_state()):
                output = format_sandbox_command("/sandbox handoff", project_root=project_root, memory_store=store)

            self.assertIn("Proto-Mind Execution Sandbox Design Handoff", output)
            self.assertIn("Registry: 387 commands across 41 categories", output)
            self.assertIn("read_only=292, mutating=95, high_risk=4", output)
            self.assertIn("NONE | READ_ONLY_MANUAL | CONFIRM_REQUIRED", output)
            self.assertIn("FUTURE_CANDIDATE: /daily doctor", output)
            self.assertIn("Execution remains forbidden", output)
            self.assertIn("/runner-mvp design", output)

    def test_sandbox_doctor_checks_dependencies_context_and_no_execution(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            with patch("proto_mind.sandbox_layer.ExecutionSandboxBlueprint.read_state", return_value=_sandbox_state()):
                output = format_sandbox_command("/sandbox doctor", project_root=project_root, memory_store=store)

            self.assertIn("Execution Sandbox Blueprint Doctor", output)
            self.assertIn("Status: OK", output)
            self.assertIn("All sandbox commands are registered", output)
            self.assertIn("low-risk, read-only, and mutates=none", output)
            self.assertIn("Every FUTURE_CANDIDATE", output)
            self.assertIn("Context Injection is disabled", output)
            self.assertIn("No execution callback, runner command, subprocess/shell/eval/exec path", output)

    def test_sandbox_doctor_warns_without_changing_enabled_context(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            format_context_command("/context injection enable", project_root=project_root)
            settings_path = project_root / "proto_mind" / "data" / "context_injection.json"
            before = settings_path.read_bytes()
            with patch(
                "proto_mind.sandbox_layer.ExecutionSandboxBlueprint.read_state",
                return_value=_sandbox_state(context_state="enabled"),
            ):
                output = format_sandbox_command("/sandbox doctor", project_root=project_root, memory_store=store)

            self.assertIn("Status: WARN", output)
            self.assertIn("Context Injection is explicitly enabled", output)
            self.assertEqual(settings_path.read_bytes(), before)
            self.assertTrue(json.loads(settings_path.read_text(encoding="utf-8"))["enabled"])

    def test_sandbox_commands_are_read_only_through_shared_handler(self) -> None:
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
                    "/sandbox status",
                    "/sandbox blueprint",
                    "/sandbox boundaries",
                    "/sandbox allowlist",
                    "/sandbox denied",
                    "/sandbox doctor",
                    "/sandbox handoff",
                )
            ]

            self.assertIn("Execution Sandbox Blueprint Status", outputs[0])
            self.assertIn("Future Command Runner Blueprint (Design Only)", outputs[1])
            self.assertIn("Future Execution Sandbox Boundaries (Advisory)", outputs[2])
            self.assertIn("Proposed Initial Future Runner Allowlist", outputs[3])
            self.assertIn("Denied / Blocked Future Runner Classes", outputs[4])
            self.assertIn("Execution Sandbox Blueprint Doctor", outputs[5])
            self.assertIn("Proto-Mind Execution Sandbox Design Handoff", outputs[6])
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

    def test_activation_status_allows_design_review_but_blocks_execution(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            with patch("proto_mind.activation_layer.RunnerActivationPreconditions.read_state", return_value=_activation_state()):
                output = format_activation_command("/activation status", project_root=project_root, memory_store=store)

            self.assertIn("Runner Activation Preconditions Status", output)
            self.assertIn("Status: WARN", output)
            self.assertIn("command_registry: commands=387 categories=41", output)
            self.assertIn("context_injection: disabled", output)
            self.assertIn("runner_candidate_readiness: WARN", output)
            self.assertIn("accepted_known_warnings: 12", output)
            self.assertIn("unknown_warnings: 0", output)
            self.assertIn("blockers: 0", output)
            self.assertIn("active_allowlist: none/inactive", output)
            self.assertIn("execution_enabled=false", output)
            self.assertIn("activation_design_may_be_considered: true", output)
            self.assertIn("actual_execution_blocked=true", output)
            self.assertIn("activation_performed=false", output)

    def test_activation_status_blocks_design_on_unknown_or_blockers(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            with patch(
                "proto_mind.activation_layer.RunnerActivationPreconditions.read_state",
                return_value=_activation_state(unknown=True, blockers=1),
            ):
                output = format_activation_command("/activation status", project_root=project_root, memory_store=store)

            self.assertIn("Status: BLOCKED", output)
            self.assertIn("unknown_warnings: 1", output)
            self.assertIn("blockers: 1", output)
            self.assertIn("activation_design_may_be_considered: false", output)
            self.assertIn("actual_execution_blocked=true", output)

    def test_activation_preconditions_cover_future_v3x_safety(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")

            output = format_activation_command("/activation preconditions", project_root=project_root, memory_store=store)

            self.assertIn("Mandatory Preconditions for a Future v3.x Runner", output)
            for item in ("Rule 0 backup/checkpoint", "Unknown warnings equal 0", "Blocker count equals 0", "Context Injection is disabled", "Registry-known", "approved active allowlist", "classified read-only", "cannot write proto_mind/data or proto_mind/exports", "dry-run plan", "Confirmation policy", "human confirmation", "Execution evidence", "Post-run Acceptance Review", "Shell/subprocess/eval/exec", "Network and hidden background work", "Stop conditions"):
                self.assertIn(item, output)
            self.assertIn("none activates a candidate or enables execution", output)

    def test_activation_checklist_is_manual_and_nonpersistent(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")

            output = format_activation_command("/activation checklist", project_root=project_root, memory_store=store)

            for command in ("/runner-candidates doctor", "/runner disabled", "/sandbox denied", "/confirm policy", "/plan gates", "/capabilities safety", "/warnings unknown"):
                self.assertIn(f"Run {command}", output)
            self.assertIn("Define the exact candidate allowlist in a separate explicit task", output)
            self.assertIn("tests, compileall, manual smoke, and data/exports SHA-256", output)
            self.assertIn("no command was run and no checkbox state was stored", output)

    def test_activation_blockers_distinguish_design_from_execution(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            with patch("proto_mind.activation_layer.RunnerActivationPreconditions.read_state", return_value=_activation_state()):
                output = format_activation_command("/activation blockers", project_root=project_root, memory_store=store)

            self.assertIn("Runner Activation Blockers", output)
            self.assertIn("Current design blockers:", output)
            self.assertIn("none; v3.x design discussion may be considered", output)
            self.assertIn("Current execution blockers:", output)
            self.assertIn("active allowlist: absent", output)
            self.assertIn("approval capture: absent", output)
            self.assertIn("authorization engine: absent", output)
            self.assertIn("execution engine: absent", output)
            self.assertIn("actual_execution_blocked=true", output)

    def test_activation_forbidden_keeps_candidates_inactive(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")

            output = format_activation_command("/activation forbidden", project_root=project_root, memory_store=store)

            self.assertIn("Actions Forbidden Before a Separately Approved v3.x Runner", output)
            self.assertIn("activating a FUTURE_CANDIDATE automatically", output)
            self.assertIn("Treating the candidate set as an active allowlist", output)
            self.assertIn("Broad approvals, implicit confirmations", output)
            self.assertIn("shell/subprocess/pipeline/eval/exec", output)
            self.assertIn("active_allowlist: none/inactive", output)
            self.assertIn("execution_enabled=false", output)

    def test_activation_handoff_reports_execution_blockers_and_v216(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            with patch("proto_mind.activation_layer.RunnerActivationPreconditions.read_state", return_value=_activation_state()):
                output = format_activation_command("/activation handoff", project_root=project_root, memory_store=store)

            self.assertIn("Proto-Mind Runner Activation Preconditions Handoff", output)
            self.assertIn("Registry: 387 commands across 41 categories", output)
            self.assertIn("Candidate set: 13/13 registry-verified", output)
            self.assertIn("active_allowlist: none/inactive", output)
            self.assertIn("execution_enabled=false", output)
            self.assertIn("actual_execution_blocked=true", output)
            self.assertIn("approval capture, authorization engine, execution engine", output)
            self.assertIn("/runner-mvp design", output)

    def test_activation_doctor_checks_dependencies_and_no_activation(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            with patch("proto_mind.activation_layer.RunnerActivationPreconditions.read_state", return_value=_activation_state()):
                output = format_activation_command("/activation doctor", project_root=project_root, memory_store=store)

            self.assertIn("Runner Activation Preconditions Doctor", output)
            self.assertIn("Status: OK", output)
            self.assertIn("All activation commands are registered", output)
            self.assertIn("All 13 candidates remain FUTURE_CANDIDATE/NOT_ACTIVE/NOT_EXECUTABLE_BY_RUNNER_YET", output)
            self.assertIn("Active allowlist remains absent, execution remains disabled", output)
            self.assertIn("No activation API, execution callback, subprocess/shell/eval/exec path", output)

    def test_activation_doctor_warns_without_changing_enabled_context(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            format_context_command("/context injection enable", project_root=project_root)
            settings_path = project_root / "proto_mind" / "data" / "context_injection.json"
            before = settings_path.read_bytes()
            with patch(
                "proto_mind.activation_layer.RunnerActivationPreconditions.read_state",
                return_value=_activation_state(context_state="enabled"),
            ):
                output = format_activation_command("/activation doctor", project_root=project_root, memory_store=store)

            self.assertIn("Status: WARN", output)
            self.assertIn("Context Injection is explicitly enabled", output)
            self.assertEqual(settings_path.read_bytes(), before)
            self.assertTrue(json.loads(settings_path.read_text(encoding="utf-8"))["enabled"])

    def test_activation_commands_are_read_only_through_shared_handler(self) -> None:
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
                    "/activation status",
                    "/activation preconditions",
                    "/activation checklist",
                    "/activation blockers",
                    "/activation forbidden",
                    "/activation doctor",
                    "/activation handoff",
                )
            ]

            self.assertIn("Runner Activation Preconditions Status", outputs[0])
            self.assertIn("Mandatory Preconditions for a Future v3.x Runner", outputs[1])
            self.assertIn("Future Runner Implementation Checklist", outputs[2])
            self.assertIn("Runner Activation Blockers", outputs[3])
            self.assertIn("Actions Forbidden Before a Separately Approved v3.x Runner", outputs[4])
            self.assertIn("Runner Activation Preconditions Doctor", outputs[5])
            self.assertIn("Proto-Mind Runner Activation Preconditions Handoff", outputs[6])
            for output in outputs:
                self.assertNotIn("execution_enabled=true", output)
                self.assertNotIn("activation_performed=true", output)
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
