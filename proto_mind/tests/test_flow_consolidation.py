"""Core flow checks: consolidation."""
from __future__ import annotations

import unittest
from proto_mind.tests.flow_fixtures import (
    ExperimentJournal,
    Path,
    SessionOperatorLogger,
    SkillLibrary,
    TaskQueue,
    TemporaryDirectory,
    WorldModelLite,
    build_test_system,
    format_consolidation_command,
    format_experiment_command,
    format_skill_command,
    format_task_command,
    format_world_command,
    json,
    process_interactive_input,
)


class ConsolidationFlowTests(unittest.TestCase):
    def test_consolidation_commands_work_with_empty_stores(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)

            status = format_consolidation_command("/consolidation status", project_root=project_root)
            preview = format_consolidation_command("/consolidation preview", project_root=project_root)
            doctor = format_consolidation_command("/consolidation doctor", project_root=project_root)

            self.assertIn("Consolidation Preview status:", status)
            self.assertIn("source_stores_checked:", status)
            self.assertIn("Consolidation Preview", preview)
            self.assertIn("Mutation policy: read-only suggestions only", preview)
            self.assertIn("Memory candidates:", preview)
            self.assertIn("Consolidation Doctor", doctor)
            self.assertIn("No active explicit memories found.", doctor)

    def test_consolidation_export_status_works_when_export_dir_missing(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)

            output = format_consolidation_command("/consolidation export-status", project_root=project_root)

            self.assertIn("Consolidation Export Status", output)
            self.assertIn("exists: False", output)
            self.assertIn("export_files: 0", output)
            self.assertIn("/consolidation export", output)

    def test_consolidation_export_creates_markdown_and_json_on_empty_stores(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)

            output = format_consolidation_command("/consolidation export", project_root=project_root)
            export_dir = project_root / "proto_mind" / "exports" / "consolidation"
            md_files = sorted(export_dir.glob("consolidation_*.md"))
            json_files = sorted(export_dir.glob("consolidation_*.json"))

            self.assertIn("Consolidation export created:", output)
            self.assertEqual(len(md_files), 1)
            self.assertEqual(len(json_files), 1)
            markdown = md_files[0].read_text(encoding="utf-8")
            payload = json.loads(json_files[0].read_text(encoding="utf-8"))
            self.assertIn("# Consolidation Preview Export", markdown)
            self.assertIn("## Summary", markdown)
            self.assertIn("## Memory Candidates", markdown)
            self.assertIn("## Skill Candidates", markdown)
            self.assertIn("## Follow-Up Candidates", markdown)
            self.assertIn("## Suggested Commands", markdown)
            self.assertIn("memory_candidates", payload)
            self.assertIn("skill_candidates", payload)
            self.assertIn("followup_candidates", payload)

    def test_consolidation_export_is_read_only_for_core_stores(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            task_output = format_task_command("/tasks add Export read-only task", project_root=project_root)
            task_id = next(line.strip().split(" — ")[0] for line in task_output.splitlines() if line.strip().startswith("task_"))
            format_task_command(f"/tasks done {task_id} export should not change this", project_root=project_root)
            paths = [TaskQueue.from_project_root(project_root).tasks_path]
            before = tuple(path.read_bytes() for path in paths)

            output = format_consolidation_command("/consolidation export", project_root=project_root)
            after = tuple(path.read_bytes() for path in paths)

            self.assertIn("only export files were created", output)
            self.assertEqual(after, before)

    def test_consolidation_queue_status_works_when_file_missing(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)

            output = format_consolidation_command("/consolidation queue-status", project_root=project_root)

            self.assertIn("Consolidation Queue status:", output)
            self.assertIn("exists: False", output)
            self.assertIn("pending: 0", output)
            self.assertIn("/consolidation queue-add", output)

    def test_consolidation_queue_doctor_and_cleanup_work_when_file_missing(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)

            doctor = format_consolidation_command("/consolidation queue-doctor", project_root=project_root)
            cleanup = format_consolidation_command("/consolidation queue-cleanup-preview", project_root=project_root)

            self.assertIn("Consolidation Queue Doctor", doctor)
            self.assertIn("Status: OK", doctor)
            self.assertIn("total records: 0", doctor)
            self.assertIn("Queue is healthy", doctor)
            self.assertIn("Consolidation Queue Cleanup Preview", cleanup)
            self.assertIn("/consolidation queue-export", cleanup)
            self.assertIn("No cleanup issues detected", cleanup)

    def test_consolidation_queue_doctor_returns_ok_on_empty_queue_file(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            queue_path = project_root / "proto_mind" / "data" / "consolidation_queue.jsonl"
            queue_path.parent.mkdir(parents=True)
            queue_path.write_text("", encoding="utf-8")

            doctor = format_consolidation_command("/consolidation queue-doctor", project_root=project_root)

            self.assertIn("Status: OK", doctor)
            self.assertIn("total records: 0", doctor)

    def test_consolidation_queue_doctor_detects_malformed_jsonl(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            queue_path = project_root / "proto_mind" / "data" / "consolidation_queue.jsonl"
            queue_path.parent.mkdir(parents=True)
            queue_path.write_text("not-json\n", encoding="utf-8")

            doctor = format_consolidation_command("/consolidation queue-doctor", project_root=project_root)

            self.assertIn("Status: ERROR", doctor)
            self.assertIn("Malformed JSONL records: 1", doctor)

    def test_consolidation_queue_doctor_detects_missing_fields_invalid_status_and_kind(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            queue_path = project_root / "proto_mind" / "data" / "consolidation_queue.jsonl"
            queue_path.parent.mkdir(parents=True)
            queue_path.write_text(
                json.dumps(
                    {
                        "id": "cq_bad",
                        "created_at": "2026-06-01T00:00:00+00:00",
                        "status": "bogus",
                        "kind": "badkind",
                        "title": "Bad item",
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            doctor = format_consolidation_command("/consolidation queue-doctor", project_root=project_root)

            self.assertIn("Status: WARN", doctor)
            self.assertIn("cq_bad missing required fields", doctor)
            self.assertIn("cq_bad has invalid status: bogus", doctor)
            self.assertIn("cq_bad has invalid kind: badkind", doctor)

    def test_consolidation_queue_doctor_detects_duplicate_pending_title_and_command(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            queue = project_root / "proto_mind" / "data" / "consolidation_queue.jsonl"
            queue.parent.mkdir(parents=True)
            now = "2026-06-26T00:00:00+00:00"
            first = {
                "id": "cq_one",
                "created_at": now,
                "updated_at": now,
                "status": "pending",
                "kind": "memory",
                "source": "operator",
                "title": "Duplicate title",
                "suggested_command": "/memory remember duplicate",
                "rationale": "",
                "tags": [],
            }
            second = dict(first, id="cq_two")
            queue.write_text(json.dumps(first) + "\n" + json.dumps(second) + "\n", encoding="utf-8")

            doctor = format_consolidation_command("/consolidation queue-doctor", project_root=project_root)
            cleanup = format_consolidation_command("/consolidation queue-cleanup-preview", project_root=project_root)

            self.assertIn("Duplicate pending title", doctor)
            self.assertIn("Duplicate pending suggested_command", doctor)
            self.assertIn("/consolidation queue-reject cq_two duplicate pending title", cleanup)
            self.assertIn("/consolidation queue-reject cq_two duplicate pending command", cleanup)

    def test_consolidation_queue_cleanup_preview_suggests_archive_for_approved_items(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            added = format_consolidation_command(
                '/consolidation queue-add memory "Archive approved" --command "/memory remember approved"',
                project_root=project_root,
            )
            item_id = next(line.strip().split(" — ")[0] for line in added.splitlines() if line.strip().startswith("cq_"))
            format_consolidation_command(f"/consolidation queue-approve {item_id}", project_root=project_root)

            cleanup = format_consolidation_command("/consolidation queue-cleanup-preview", project_root=project_root)

            self.assertIn(f"/consolidation queue-archive {item_id}", cleanup)

    def test_consolidation_queue_doctor_and_cleanup_preview_are_read_only(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            added = format_consolidation_command(
                '/consolidation queue-add memory "Read-only doctor" --command "/memory remember readonly"',
                project_root=project_root,
            )
            self.assertIn("cq_", added)
            queue_path = project_root / "proto_mind" / "data" / "consolidation_queue.jsonl"
            before = queue_path.read_bytes()

            doctor = format_consolidation_command("/consolidation queue-doctor", project_root=project_root)
            cleanup = format_consolidation_command("/consolidation queue-cleanup-preview", project_root=project_root)
            after = queue_path.read_bytes()

            self.assertIn("Consolidation Queue Doctor", doctor)
            self.assertIn("Consolidation Queue Cleanup Preview", cleanup)
            self.assertEqual(after, before)

    def test_consolidation_queue_add_list_and_inspect(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)

            added = format_consolidation_command(
                '/consolidation queue-add memory "Remember queue smoke" --command "/memory remember Queue smoke worked" --rationale "Important milestone"',
                project_root=project_root,
            )
            item_id = next(line.strip().split(" — ")[0] for line in added.splitlines() if line.strip().startswith("cq_"))
            listing = format_consolidation_command("/consolidation queue-list", project_root=project_root)
            inspect = format_consolidation_command(f"/consolidation queue-inspect {item_id}", project_root=project_root)

            self.assertIn("Consolidation queue item added:", added)
            self.assertIn(item_id, listing)
            self.assertIn("Remember queue smoke", inspect)
            self.assertIn("/memory remember Queue smoke worked", inspect)
            self.assertIn("Important milestone", inspect)

    def test_consolidation_queue_add_accepts_smart_quotes_and_dash(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)

            added = format_consolidation_command(
                "/consolidation queue-add memory “Smart quoted title” –command “/memory remember smart quoted command” –rationale “smart rationale”",
                project_root=project_root,
            )

            self.assertIn("Consolidation queue item added:", added)

    def test_consolidation_queue_approve_marks_approved_but_does_not_execute_command(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            added = format_consolidation_command(
                '/consolidation queue-add memory "Remember approved item" --command "/memory remember This should not execute"',
                project_root=project_root,
            )
            item_id = next(line.strip().split(" — ")[0] for line in added.splitlines() if line.strip().startswith("cq_"))
            memory_path = project_root / "proto_mind" / "data" / "persistent_memory.json"

            approved = format_consolidation_command(f"/consolidation queue-approve {item_id}", project_root=project_root)
            inspect = format_consolidation_command(f"/consolidation queue-inspect {item_id}", project_root=project_root)

            self.assertIn("Consolidation queue item approved", approved)
            self.assertIn("Suggested command for manual run:", approved)
            self.assertIn("Note: command was not executed.", approved)
            self.assertIn("status: approved", inspect)
            self.assertFalse(memory_path.exists())

    def test_consolidation_queue_apply_rejects_missing_id(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)

            output = format_consolidation_command("/consolidation queue-apply", project_root=project_root)

            self.assertIn("Usage: /consolidation queue-apply <id>", output)

    def test_consolidation_queue_apply_rejects_non_approved_statuses(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            pending_output = format_consolidation_command(
                '/consolidation queue-add memory "Pending apply" --command "/memory remember pending apply"',
                project_root=project_root,
            )
            rejected_output = format_consolidation_command(
                '/consolidation queue-add memory "Rejected apply" --command "/memory remember rejected apply"',
                project_root=project_root,
            )
            archived_output = format_consolidation_command(
                '/consolidation queue-add memory "Archived apply" --command "/memory remember archived apply"',
                project_root=project_root,
            )
            pending_id = next(line.strip().split(" — ")[0] for line in pending_output.splitlines() if line.strip().startswith("cq_"))
            rejected_id = next(line.strip().split(" — ")[0] for line in rejected_output.splitlines() if line.strip().startswith("cq_"))
            archived_id = next(line.strip().split(" — ")[0] for line in archived_output.splitlines() if line.strip().startswith("cq_"))
            format_consolidation_command(f"/consolidation queue-reject {rejected_id} no", project_root=project_root)
            format_consolidation_command(f"/consolidation queue-archive {archived_id}", project_root=project_root)

            pending_apply = format_consolidation_command(f"/consolidation queue-apply {pending_id}", project_root=project_root)
            rejected_apply = format_consolidation_command(f"/consolidation queue-apply {rejected_id}", project_root=project_root)
            archived_apply = format_consolidation_command(f"/consolidation queue-apply {archived_id}", project_root=project_root)

            self.assertIn("only approved items can be applied", pending_apply)
            self.assertIn("status: pending", pending_apply)
            self.assertIn("status: rejected", rejected_apply)
            self.assertIn("status: archived", archived_apply)

    def test_consolidation_queue_apply_allows_approved_memory_remember_once(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            memory_path = project_root / "proto_mind" / "data" / "persistent_memory.json"
            added = format_consolidation_command(
                '/consolidation queue-add memory "Apply memory" --command "/memory remember Queue apply writes memory once"',
                project_root=project_root,
            )
            item_id = next(line.strip().split(" — ")[0] for line in added.splitlines() if line.strip().startswith("cq_"))
            format_consolidation_command(f"/consolidation queue-approve {item_id}", project_root=project_root)

            applied = format_consolidation_command(f"/consolidation queue-apply {item_id}", project_root=project_root)
            applied_again = format_consolidation_command(f"/consolidation queue-apply {item_id}", project_root=project_root)
            inspect = format_consolidation_command(f"/consolidation queue-inspect {item_id}", project_root=project_root)
            records = json.loads(memory_path.read_text(encoding="utf-8"))

            self.assertIn("Consolidation queue item applied:", applied)
            self.assertIn("command_type: memory_remember", applied)
            self.assertIn("Remembered:", applied)
            self.assertIn("status: applied", inspect)
            self.assertIn("applied_at:", inspect)
            self.assertIn("applied_command:", inspect)
            self.assertIn("applied_kind:", inspect)
            self.assertIn("applied_record_id:", inspect)
            self.assertIn("apply_result:", inspect)
            self.assertIn("undo_suggestion:", inspect)
            self.assertIn("only approved items can be applied", applied_again)
            self.assertEqual(len([item for item in records if item.get("content") == "Queue apply writes memory once"]), 1)

    def test_consolidation_queue_apply_memory_stores_receipt_and_undo_preview(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            added = format_consolidation_command(
                '/consolidation queue-add memory "Receipt memory" --command "/memory remember Receipt memory works"',
                project_root=project_root,
            )
            item_id = next(line.strip().split(" — ")[0] for line in added.splitlines() if line.strip().startswith("cq_"))
            format_consolidation_command(f"/consolidation queue-approve {item_id}", project_root=project_root)

            applied = format_consolidation_command(f"/consolidation queue-apply {item_id}", project_root=project_root)
            receipt = format_consolidation_command(f"/consolidation queue-apply-receipt {item_id}", project_root=project_root)
            undo = format_consolidation_command(f"/consolidation queue-undo-preview {item_id}", project_root=project_root)

            mem_id = next(token for token in receipt.replace(":", " ").split() if token.startswith("mem_"))
            self.assertIn("applied_kind: memory", applied)
            self.assertIn("Consolidation Queue Apply Receipt", receipt)
            self.assertIn("applied_kind: memory", receipt)
            self.assertIn(f"applied_record_id: {mem_id}", receipt)
            self.assertIn(f"undo_suggestion: /memory forget {mem_id}", receipt)
            self.assertIn(f"/memory forget {mem_id}", undo)
            self.assertIn("preview only; no undo was performed", undo)

    def test_consolidation_queue_apply_skill_add_stores_receipt_and_undo_preview(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            added = format_consolidation_command(
                '/consolidation queue-add skill "Receipt skill" --command "/skills add Receipt Skill --category workflow --summary Receipt works"',
                project_root=project_root,
            )
            item_id = next(line.strip().split(" — ")[0] for line in added.splitlines() if line.strip().startswith("cq_"))
            format_consolidation_command(f"/consolidation queue-approve {item_id}", project_root=project_root)
            format_consolidation_command(f"/consolidation queue-apply {item_id}", project_root=project_root)

            receipt = format_consolidation_command(f"/consolidation queue-apply-receipt {item_id}", project_root=project_root)
            undo = format_consolidation_command(f"/consolidation queue-undo-preview {item_id}", project_root=project_root)

            skill_id = next(token for token in receipt.replace(":", " ").split() if token.startswith("skill_"))
            self.assertIn("applied_kind: skill", receipt)
            self.assertIn(f"applied_record_id: {skill_id}", receipt)
            self.assertIn(f"undo_suggestion: /skills archive {skill_id}", receipt)
            self.assertIn(f"/skills archive {skill_id}", undo)

    def test_consolidation_queue_apply_skill_body_receipt_requires_manual_undo_review(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            skill_output = format_skill_command("/skills add Body Receipt Skill", project_root=project_root)
            skill_id = next(line.strip().split(" — ")[0] for line in skill_output.splitlines() if line.strip().startswith("skill_"))
            added = format_consolidation_command(
                f'/consolidation queue-add skill "Body receipt" --command "/skills body {skill_id} New body text"',
                project_root=project_root,
            )
            item_id = next(line.strip().split(" — ")[0] for line in added.splitlines() if line.strip().startswith("cq_"))
            format_consolidation_command(f"/consolidation queue-approve {item_id}", project_root=project_root)
            format_consolidation_command(f"/consolidation queue-apply {item_id}", project_root=project_root)

            receipt = format_consolidation_command(f"/consolidation queue-apply-receipt {item_id}", project_root=project_root)
            undo = format_consolidation_command(f"/consolidation queue-undo-preview {item_id}", project_root=project_root)

            self.assertIn("applied_kind: skill_body", receipt)
            self.assertIn(f"applied_record_id: {skill_id}", receipt)
            self.assertIn("Manual review required: skill body was changed", receipt)
            self.assertIn("Manual review required: skill body was changed", undo)
            self.assertNotIn("/skills archive", undo)

    def test_consolidation_queue_receipt_and_undo_handle_non_applied_item_cleanly(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            added = format_consolidation_command(
                '/consolidation queue-add memory "Pending receipt" --command "/memory remember pending receipt"',
                project_root=project_root,
            )
            item_id = next(line.strip().split(" — ")[0] for line in added.splitlines() if line.strip().startswith("cq_"))

            receipt = format_consolidation_command(f"/consolidation queue-apply-receipt {item_id}", project_root=project_root)
            undo = format_consolidation_command(f"/consolidation queue-undo-preview {item_id}", project_root=project_root)

            self.assertIn("Apply Receipt unavailable", receipt)
            self.assertIn("item has not been applied", receipt)
            self.assertIn("Undo Preview unavailable", undo)
            self.assertIn("item has not been applied", undo)

    def test_consolidation_queue_apply_rejects_non_allowlisted_and_chains(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            bad_output = format_consolidation_command(
                '/consolidation queue-add other "Bad command" --command "/world score wm_test 4"',
                project_root=project_root,
            )
            chain_output = format_consolidation_command(
                '/consolidation queue-add memory "Chain command" --command "/memory remember one && /memory remember two"',
                project_root=project_root,
            )
            bad_id = next(line.strip().split(" — ")[0] for line in bad_output.splitlines() if line.strip().startswith("cq_"))
            chain_id = next(line.strip().split(" — ")[0] for line in chain_output.splitlines() if line.strip().startswith("cq_"))
            format_consolidation_command(f"/consolidation queue-approve {bad_id}", project_root=project_root)
            format_consolidation_command(f"/consolidation queue-approve {chain_id}", project_root=project_root)

            bad_apply = format_consolidation_command(f"/consolidation queue-apply {bad_id}", project_root=project_root)
            chain_apply = format_consolidation_command(f"/consolidation queue-apply {chain_id}", project_root=project_root)

            self.assertIn("not in the consolidation apply allowlist", bad_apply)
            self.assertIn("Manual command for operator review:", bad_apply)
            self.assertIn("multi-command chains are not supported", chain_apply)

    def test_consolidation_queue_apply_preview_reports_applyability(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            added = format_consolidation_command(
                '/consolidation queue-add memory "Preview apply" --command "/memory remember preview apply"',
                project_root=project_root,
            )
            item_id = next(line.strip().split(" — ")[0] for line in added.splitlines() if line.strip().startswith("cq_"))
            pending_preview = format_consolidation_command(f"/consolidation queue-apply-preview {item_id}", project_root=project_root)
            format_consolidation_command(f"/consolidation queue-approve {item_id}", project_root=project_root)
            approved_preview = format_consolidation_command(f"/consolidation queue-apply-preview {item_id}", project_root=project_root)

            self.assertIn("Consolidation Queue Apply Preview", pending_preview)
            self.assertIn("applyable: False", pending_preview)
            self.assertIn("applyable: True", approved_preview)
            self.assertIn("allowlisted /memory remember", approved_preview)

    def test_consolidation_queue_doctor_list_and_export_handle_applied_status(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            added = format_consolidation_command(
                '/consolidation queue-add memory "Applied export" --command "/memory remember applied export"',
                project_root=project_root,
            )
            item_id = next(line.strip().split(" — ")[0] for line in added.splitlines() if line.strip().startswith("cq_"))
            format_consolidation_command(f"/consolidation queue-approve {item_id}", project_root=project_root)
            format_consolidation_command(f"/consolidation queue-apply {item_id}", project_root=project_root)

            status = format_consolidation_command("/consolidation queue-status", project_root=project_root)
            listing = format_consolidation_command("/consolidation queue-list --all", project_root=project_root)
            doctor = format_consolidation_command("/consolidation queue-doctor", project_root=project_root)
            export = format_consolidation_command("/consolidation queue-export", project_root=project_root)
            export_dir = project_root / "proto_mind" / "exports" / "consolidation_queue"
            payload = json.loads(sorted(export_dir.glob("consolidation_queue_*.json"))[0].read_text(encoding="utf-8"))

            self.assertIn("applied: 1", status)
            self.assertIn("[applied]", listing)
            self.assertIn("status counts: applied=1", doctor)
            self.assertIn("Consolidation queue export created:", export)
            self.assertEqual(payload["records"][0]["status"], "applied")
            self.assertIn("applied_at", payload["records"][0])
            self.assertIn("applied_command", payload["records"][0])
            self.assertIn("applied_kind", payload["records"][0])
            self.assertIn("applied_record_id", payload["records"][0])
            self.assertIn("undo_suggestion", payload["records"][0])

    def test_consolidation_queue_reject_archive_and_list_all(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            rejected_output = format_consolidation_command(
                '/consolidation queue-add memory "Reject me" --command "/memory remember reject me"',
                project_root=project_root,
            )
            archived_output = format_consolidation_command(
                '/consolidation queue-add skill "Archive me" --command "/skills add archive me"',
                project_root=project_root,
            )
            rejected_id = next(line.strip().split(" — ")[0] for line in rejected_output.splitlines() if line.strip().startswith("cq_"))
            archived_id = next(line.strip().split(" — ")[0] for line in archived_output.splitlines() if line.strip().startswith("cq_"))

            reject = format_consolidation_command(f"/consolidation queue-reject {rejected_id} not useful", project_root=project_root)
            archive = format_consolidation_command(f"/consolidation queue-archive {archived_id}", project_root=project_root)
            default_list = format_consolidation_command("/consolidation queue-list", project_root=project_root)
            all_list = format_consolidation_command("/consolidation queue-list --all", project_root=project_root)
            inspect = format_consolidation_command(f"/consolidation queue-inspect {rejected_id}", project_root=project_root)

            self.assertIn("rejected", reject)
            self.assertIn("archived", archive)
            self.assertNotIn(rejected_id, default_list)
            self.assertNotIn(archived_id, default_list)
            self.assertIn(rejected_id, all_list)
            self.assertIn(archived_id, all_list)
            self.assertIn("Rejected: not useful", inspect)

    def test_consolidation_queue_export_creates_markdown_and_json(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            format_consolidation_command(
                '/consolidation queue-add world_followup "Score world item" --command "/world score wm_test 4"',
                project_root=project_root,
            )

            output = format_consolidation_command("/consolidation queue-export", project_root=project_root)
            export_dir = project_root / "proto_mind" / "exports" / "consolidation_queue"
            md_files = sorted(export_dir.glob("consolidation_queue_*.md"))
            json_files = sorted(export_dir.glob("consolidation_queue_*.json"))

            self.assertIn("Consolidation queue export created:", output)
            self.assertEqual(len(md_files), 1)
            self.assertEqual(len(json_files), 1)
            markdown = md_files[0].read_text(encoding="utf-8")
            payload = json.loads(json_files[0].read_text(encoding="utf-8"))
            self.assertIn("# Consolidation Queue Export", markdown)
            self.assertIn("Score world item", markdown)
            self.assertEqual(len(payload["records"]), 1)

    def test_consolidation_queue_invalid_kind_returns_clean_error(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)

            output = format_consolidation_command(
                '/consolidation queue-add invalid "Bad kind" --command "/memory remember nope"',
                project_root=project_root,
            )

            self.assertIn("Invalid kind: invalid", output)

    def test_consolidation_queue_commands_do_not_mutate_core_stores(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            memory_path = project_root / "proto_mind" / "data" / "persistent_memory.json"
            skills_path = SkillLibrary.from_project_root(project_root).skills_path
            experiments_path = ExperimentJournal.from_project_root(project_root).experiments_path
            world_path = WorldModelLite.from_project_root(project_root).world_path
            memory_path.parent.mkdir(parents=True)
            memory_path.write_text("[]", encoding="utf-8")
            skills_path.write_text("", encoding="utf-8")
            experiments_path.write_text("", encoding="utf-8")
            world_path.write_text("", encoding="utf-8")
            paths = [memory_path, skills_path, experiments_path, world_path]
            before = tuple(path.read_bytes() for path in paths)

            added = format_consolidation_command(
                '/consolidation queue-add memory "Do not execute" --command "/memory remember should not happen"',
                project_root=project_root,
            )
            item_id = next(line.strip().split(" — ")[0] for line in added.splitlines() if line.strip().startswith("cq_"))
            format_consolidation_command(f"/consolidation queue-approve {item_id}", project_root=project_root)
            format_consolidation_command("/consolidation queue-export", project_root=project_root)
            after = tuple(path.read_bytes() for path in paths)

            self.assertEqual(after, before)

    def test_consolidation_preview_shows_memory_candidate_from_done_task_result(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            task_output = format_task_command("/tasks add Consolidate task", project_root=project_root)
            task_id = next(line.strip().split(" — ")[0] for line in task_output.splitlines() if line.strip().startswith("task_"))
            format_task_command(f"/tasks done {task_id} The operator validated consolidation preview behavior.", project_root=project_root)

            preview = format_consolidation_command("/consolidation preview", project_root=project_root)

            self.assertIn("Memory candidates:", preview)
            self.assertIn("/memory remember Task Consolidate task: The operator validated consolidation preview behavior.", preview)

    def test_consolidation_preview_shows_memory_and_skill_candidates_from_world_lesson(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            world_output = format_world_command("/world predict If lessons exist -> consolidation suggests them", project_root=project_root)
            world_id = next(line.strip().split(" — ")[0] for line in world_output.splitlines() if line.strip().startswith("wm_"))
            format_world_command(f"/world observe {world_id} Lesson was observed", project_root=project_root)
            format_world_command(f"/world score {world_id} 5", project_root=project_root)
            format_world_command(f"/world lesson {world_id} Repeatable validation steps should become a checklist.", project_root=project_root)

            preview = format_consolidation_command("/consolidation preview", project_root=project_root)

            self.assertIn("/memory remember World prediction lesson: Repeatable validation steps should become a checklist.", preview)
            self.assertIn("/skills add Apply world-model lesson:", preview)
            self.assertIn("/skills body <skill_id> Repeatable validation steps should become a checklist.", preview)

    def test_consolidation_preview_avoids_obvious_duplicate_active_memory(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            memory_path = project_root / "proto_mind" / "data" / "persistent_memory.json"
            memory_path.parent.mkdir(parents=True)
            duplicate_text = "Task Duplicate task: This lesson already exists."
            memory_path.write_text(
                json.dumps(
                    [
                        {
                            "id": "mem_existing",
                            "content": duplicate_text,
                            "type": "explicit",
                            "active": True,
                        }
                    ]
                ),
                encoding="utf-8",
            )
            task_output = format_task_command("/tasks add Duplicate task", project_root=project_root)
            task_id = next(line.strip().split(" — ")[0] for line in task_output.splitlines() if line.strip().startswith("task_"))
            format_task_command(f"/tasks done {task_id} This lesson already exists.", project_root=project_root)

            preview = format_consolidation_command("/consolidation preview", project_root=project_root)
            memory_section = preview.split("Skill candidates:", 1)[0]

            self.assertNotIn("/memory remember Task Duplicate task: This lesson already exists.", memory_section)
            self.assertIn("already present in active explicit memory", preview)

    def test_consolidation_doctor_detects_missing_results_and_lessons(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            task_output = format_task_command("/tasks add Missing result", project_root=project_root)
            task_id = next(line.strip().split(" — ")[0] for line in task_output.splitlines() if line.strip().startswith("task_"))
            format_task_command(f"/tasks done {task_id}", project_root=project_root)
            exp_output = format_experiment_command("/experiments start Missing lesson experiment", project_root=project_root)
            exp_id = next(line.strip().split(" — ")[0] for line in exp_output.splitlines() if line.strip().startswith("exp_"))
            format_experiment_command(f"/experiments complete {exp_id}", project_root=project_root)
            world_output = format_world_command("/world predict If scored -> lesson needed", project_root=project_root)
            world_id = next(line.strip().split(" — ")[0] for line in world_output.splitlines() if line.strip().startswith("wm_"))
            format_world_command(f"/world observe {world_id} observed", project_root=project_root)
            format_world_command(f"/world score {world_id} 4", project_root=project_root)

            doctor = format_consolidation_command("/consolidation doctor", project_root=project_root)

            self.assertIn("Status: WARN", doctor)
            self.assertIn(f"Completed task without result: {task_id}", doctor)
            self.assertIn(f"Completed/inconclusive experiment without lesson: {exp_id}", doctor)
            self.assertIn(f"Scored world prediction without lesson: {world_id}", doctor)

    def test_consolidation_doctor_is_read_only(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            task_output = format_task_command("/tasks add Read-only task", project_root=project_root)
            task_id = next(line.strip().split(" — ")[0] for line in task_output.splitlines() if line.strip().startswith("task_"))
            format_task_command(f"/tasks done {task_id} preserve this result", project_root=project_root)
            paths = [TaskQueue.from_project_root(project_root).tasks_path]
            before = tuple(path.read_bytes() for path in paths)

            doctor = format_consolidation_command("/consolidation doctor", project_root=project_root)
            preview = format_consolidation_command("/consolidation preview", project_root=project_root)
            after = tuple(path.read_bytes() for path in paths)

            self.assertIn("Consolidation Doctor", doctor)
            self.assertIn("Consolidation Preview", preview)
            self.assertEqual(after, before)

    def test_consolidation_commands_work_through_shared_input_handler_without_session_log_turn(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            coordinator, _, _ = build_test_system(project_root)
            logger = SessionOperatorLogger.from_project_root(project_root)
            coordinator.session_logger = logger

            output = process_interactive_input(
                "/consolidation status",
                coordinator=coordinator,
                session_logger=logger,
                project_root=project_root,
            )

            self.assertIn("Consolidation Preview status:", output)
            self.assertEqual(logger.status().entry_count, 0)
