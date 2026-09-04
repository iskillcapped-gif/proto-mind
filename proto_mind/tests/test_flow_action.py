"""Core flow checks: action."""
from __future__ import annotations

import unittest
from proto_mind.tests.flow_fixtures import (
    COMMAND_REGISTRY,
    HEALTH_CHECK_BUNDLE,
    Path,
    SessionOperatorLogger,
    TemporaryDirectory,
    _confirmed_action,
    _executed_action,
    _id_from_output,
    _single_action_record,
    action_policy_doctor,
    action_preview_doctor,
    build_test_system,
    classify_command,
    classify_command_bundle,
    classify_natural_route,
    format_action_command,
    format_action_queue_command,
    format_policy_command,
    json,
    process_interactive_input,
)


class ActionFlowTests(unittest.TestCase):
    def test_action_policy_status_works(self) -> None:
        output = format_policy_command("/policy status")

        self.assertIn("Action Safety Policy Status", output)
        self.assertIn("registered_commands: 387", output)
        self.assertIn("auto_allowed: 291", output)
        self.assertIn("confirmation_required: 92", output)
        self.assertIn("operator_only: 4", output)
        self.assertIn("blocked: 0", output)
        self.assertIn("read-only advisory", output)

    def test_action_policy_explain_read_only_command_is_auto_allowed(self) -> None:
        output = format_policy_command("/policy explain /data doctor")

        self.assertIn("command_prefix: /data doctor", output)
        self.assertIn("read_only: True", output)
        self.assertIn("policy_class: auto_allowed", output)
        self.assertIn("safe_for_future_autonomy: True", output)
        self.assertIn("No command executed.", output)

    def test_action_policy_explain_context_and_memory_mutations_require_confirmation(self) -> None:
        context = format_policy_command("/policy explain /context injection enable")
        memory = format_policy_command("/policy explain /memory remember hello")

        self.assertIn("mutates: context", context)
        self.assertIn("policy_class: confirmation_required", context)
        self.assertIn("safe_for_future_autonomy: False", context)
        self.assertIn("command_prefix: /memory remember", memory)
        self.assertIn("mutates: memory", memory)
        self.assertIn("policy_class: confirmation_required", memory)

    def test_action_policy_unknown_and_chained_commands_are_blocked(self) -> None:
        unknown = classify_command("/unknown command")
        chained = classify_command("/data doctor; /memory remember unsafe")

        self.assertEqual(unknown.policy_class, "blocked")
        self.assertEqual(chained.policy_class, "blocked")
        self.assertFalse(unknown.safe_for_future_autonomy)
        self.assertFalse(chained.safe_for_future_autonomy)

    def test_action_policy_high_risk_and_mutating_commands_are_not_auto_allowed(self) -> None:
        high_risk = classify_command("/memory cleanup-apply")
        mutating = [classify_command(spec.prefix) for spec in COMMAND_REGISTRY if not spec.read_only]

        self.assertEqual(high_risk.policy_class, "operator_only")
        self.assertNotEqual(high_risk.policy_class, "auto_allowed")
        self.assertTrue(mutating)
        self.assertTrue(all(decision.policy_class != "auto_allowed" for decision in mutating))

    def test_action_policy_bundle_uses_strictest_member(self) -> None:
        read_only_bundle = classify_command_bundle(HEALTH_CHECK_BUNDLE)
        mixed_bundle = classify_command_bundle(("/data doctor", "/context injection enable"))
        high_risk_bundle = classify_command_bundle(("/data doctor", "/consolidation queue-apply"))

        self.assertEqual(read_only_bundle["policy_class"], "auto_allowed")
        self.assertEqual(mixed_bundle["policy_class"], "confirmation_required")
        self.assertEqual(high_risk_bundle["policy_class"], "operator_only")

    def test_action_policy_natural_mutation_requires_confirmation(self) -> None:
        decision = classify_natural_route("/context injection enable")

        self.assertEqual(decision["policy_class"], "confirmation_required")
        self.assertFalse(decision["safe_for_future_autonomy"])

    def test_action_policy_doctor_returns_ok(self) -> None:
        report = action_policy_doctor()
        output = format_policy_command("/policy doctor")

        self.assertEqual(report["status"], "OK")
        self.assertIn("Action Safety Policy Doctor", output)
        self.assertIn("Status: OK", output)
        self.assertIn("Commands checked: 387", output)
        self.assertIn("Natural routes checked: 41", output)
        self.assertIn("policy invariants", output)

    def test_action_policy_works_through_shared_handler_without_execution(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            coordinator, _, _ = build_test_system(project_root / "proto_mind")
            logger = SessionOperatorLogger.from_project_root(project_root)
            coordinator.session_logger = logger

            output = process_interactive_input(
                "/policy explain /context injection enable",
                coordinator=coordinator,
                session_logger=logger,
                project_root=project_root,
            )

            self.assertIn("policy_class: confirmation_required", output)
            self.assertIn("No command executed.", output)
            self.assertFalse((project_root / "proto_mind" / "data" / "context_injection.json").exists())
            self.assertEqual(logger.status().entry_count, 0)

    def test_action_preview_status_works(self) -> None:
        output = format_action_command("/action status")

        self.assertIn("Action Preview Status", output)
        self.assertIn("mode: read-only", output)
        self.assertIn("slash commands and exact natural phrases", output)
        self.assertIn("Natural Router, Command Registry, Action Safety Policy", output)
        self.assertIn("execution: disabled", output)

    def test_action_preview_read_only_slash_command(self) -> None:
        output = format_action_command("/action preview /data doctor")

        self.assertIn("input_type: slash_command", output)
        self.assertIn("matched_prefix: /data doctor", output)
        self.assertIn("category: data", output)
        self.assertIn("read_only: True", output)
        self.assertIn("overall_policy: auto_allowed", output)
        self.assertIn("No command executed.", output)

    def test_action_preview_mutating_slash_commands_require_confirmation(self) -> None:
        context = format_action_command("/action preview /context injection enable")
        memory = format_action_command("/action preview /memory remember hello")

        self.assertIn("matched_prefix: /context injection enable", context)
        self.assertIn("mutates: context", context)
        self.assertIn("overall_policy: confirmation_required", context)
        self.assertIn("matched_prefix: /memory remember", memory)
        self.assertIn("mutates: memory", memory)
        self.assertIn("overall_policy: confirmation_required", memory)
        self.assertIn("No command executed.", memory)

    def test_action_preview_natural_health_bundle_uses_strictest_policy(self) -> None:
        output = format_action_command("/action preview проверь систему")

        self.assertIn("input_type: natural_phrase", output)
        self.assertIn("natural_phrase: проверь систему", output)
        self.assertIn("Step 5:", output)
        for command in HEALTH_CHECK_BUNDLE:
            self.assertIn(f"command: {command}", output)
        self.assertIn("strictest_bundle_policy: auto_allowed", output)
        self.assertIn("overall_policy: auto_allowed", output)

    def test_action_preview_natural_context_route_requires_confirmation(self) -> None:
        output = format_action_command("/action preview включи контекст")

        self.assertIn("command: /context injection enable", output)
        self.assertIn("read_only: False", output)
        self.assertIn("risk: medium", output)
        self.assertIn("overall_policy: confirmation_required", output)
        self.assertIn("No command executed.", output)

    def test_action_preview_unknown_natural_and_slash_inputs_are_safe(self) -> None:
        natural = format_action_command("/action preview какая сегодня погода")
        slash = format_action_command("/action preview /unknown command")

        self.assertIn("matched: False", natural)
        self.assertIn("Execution plan: none", natural)
        self.assertIn("suggestion: /natural suggest какая сегодня погода", natural)
        self.assertIn("overall_policy: blocked", natural)
        self.assertIn("matched: False", slash)
        self.assertIn("overall_policy: blocked", slash)
        self.assertIn("No command executed.", slash)

    def test_action_preview_doctor_returns_ok(self) -> None:
        report = action_preview_doctor()
        output = format_action_command("/action doctor")

        self.assertEqual(report["status"], "OK")
        self.assertIn("Action Preview Doctor", output)
        self.assertIn("Status: OK", output)
        self.assertIn("Command Registry Doctor: OK", output)
        self.assertIn("Action Safety Policy Doctor: OK", output)
        self.assertIn("Natural Command Router Doctor: OK", output)

    def test_action_preview_does_not_mutate_core_stores(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            coordinator, _, _ = build_test_system(project_root / "proto_mind")
            logger = SessionOperatorLogger.from_project_root(project_root)
            coordinator.session_logger = logger
            data_dir = project_root / "proto_mind" / "data"
            memory_paths = [data_dir / "working_memory.json", data_dir / "persistent_memory.json"]
            before = {path: path.read_bytes() for path in memory_paths}

            for action_input in (
                "/context injection enable",
                "/memory remember should not be stored",
                "/skills add should not exist",
                "/tasks add should not exist",
                "/world predict If preview runs -> this should not exist",
                "включи контекст",
            ):
                output = process_interactive_input(
                    f"/action preview {action_input}",
                    coordinator=coordinator,
                    session_logger=logger,
                    project_root=project_root,
                )
                self.assertIn("No command executed.", output)

            self.assertEqual({path: path.read_bytes() for path in memory_paths}, before)
            for filename in ("context_injection.json", "skills.jsonl", "tasks.jsonl", "world_model.jsonl"):
                self.assertFalse((data_dir / filename).exists())
            self.assertEqual(logger.status().entry_count, 0)

    def test_action_propose_slash_command_creates_preview_only_record(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)

            output = format_action_queue_command("/action propose /data doctor", project_root=project_root)
            queue_path = project_root / "proto_mind" / "data" / "action_queue.jsonl"
            record = json.loads(queue_path.read_text(encoding="utf-8").strip())

            self.assertIn("Action proposal created", output)
            self.assertIn("No target command executed.", output)
            self.assertEqual(record["status"], "proposed")
            self.assertEqual(record["input_type"], "slash")
            self.assertEqual(record["resolved_target"], "command")
            self.assertEqual(record["commands"], ["/data doctor"])
            self.assertEqual(record["strictest_policy"], "auto_allowed")
            self.assertTrue(record["no_execution"])

    def test_action_propose_natural_context_and_bundle_do_not_execute(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)

            context_output = format_action_queue_command("/action propose включи контекст", project_root=project_root)
            bundle_output = format_action_queue_command("/action propose проверь систему", project_root=project_root)
            queue_path = project_root / "proto_mind" / "data" / "action_queue.jsonl"
            records = [json.loads(line) for line in queue_path.read_text(encoding="utf-8").splitlines()]

            self.assertIn("strictest_policy: confirmation_required", context_output)
            self.assertIn("resolved_target: bundle", bundle_output)
            self.assertEqual(records[0]["commands"], ["/context injection enable"])
            self.assertEqual(records[0]["strictest_policy"], "confirmation_required")
            self.assertEqual(records[1]["commands"], list(HEALTH_CHECK_BUNDLE))
            self.assertEqual(records[1]["resolved_target"], "bundle")
            self.assertFalse((project_root / "proto_mind" / "data" / "context_injection.json").exists())

    def test_action_proposals_list_and_inspect_show_stored_metadata(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            created = format_action_queue_command("/action propose /memory remember hello", project_root=project_root)
            proposal_id = _id_from_output(created, "id:")

            listed = format_action_queue_command("/action proposals", project_root=project_root)
            inspected = format_action_queue_command(f"/action inspect {proposal_id}", project_root=project_root)

            self.assertIn(proposal_id, listed)
            self.assertIn("policy=confirmation_required", listed)
            self.assertIn("Action Proposal", inspected)
            self.assertIn("original_input: /memory remember hello", inspected)
            self.assertIn("strictest_policy: confirmation_required", inspected)
            self.assertIn("mutates=memory", inspected)
            self.assertIn("No target command executed.", inspected)

    def test_action_proposal_approve_changes_only_queue_status(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            created = format_action_queue_command("/action propose включи контекст", project_root=project_root)
            proposal_id = _id_from_output(created, "id:")

            approved = format_action_queue_command(f"/action approve {proposal_id}", project_root=project_root)
            record = _single_action_record(project_root)

            self.assertIn("Action proposal approved", approved)
            self.assertIn("No target command executed.", approved)
            self.assertEqual(record["status"], "approved")
            self.assertTrue(record["approved_at"])
            self.assertFalse((project_root / "proto_mind" / "data" / "context_injection.json").exists())

    def test_action_proposal_reject_preserves_reason(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            created = format_action_queue_command("/action propose /data doctor", project_root=project_root)
            proposal_id = _id_from_output(created, "id:")

            rejected = format_action_queue_command(f'/action reject {proposal_id} “not needed”', project_root=project_root)
            record = _single_action_record(project_root)

            self.assertIn("Action proposal rejected", rejected)
            self.assertIn("reason: not needed", rejected)
            self.assertEqual(record["status"], "rejected")
            self.assertEqual(record["reason"], "not needed")
            self.assertTrue(record["rejected_at"])

    def test_action_proposal_archive_hides_from_default_list(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            created = format_action_queue_command("/action propose /data doctor", project_root=project_root)
            proposal_id = _id_from_output(created, "id:")

            archived = format_action_queue_command(f"/action archive {proposal_id}", project_root=project_root)
            default_list = format_action_queue_command("/action proposals", project_root=project_root)
            all_list = format_action_queue_command("/action proposals --all", project_root=project_root)

            self.assertIn("Action proposal archived", archived)
            self.assertNotIn(proposal_id, default_list)
            self.assertIn(proposal_id, all_list)
            self.assertIn("[archived]", all_list)

    def test_action_queue_doctor_returns_ok_for_valid_queue(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            format_action_queue_command("/action propose /data doctor", project_root=project_root)

            output = format_action_queue_command("/action queue-doctor", project_root=project_root)

            self.assertIn("Action Proposal Queue Doctor", output)
            self.assertIn("Status: OK", output)
            self.assertIn("execution receipt invariants are healthy", output)

    def test_action_queue_doctor_detects_malformed_duplicate_and_invalid_records_read_only(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            queue_path = project_root / "proto_mind" / "data" / "action_queue.jsonl"
            queue_path.parent.mkdir(parents=True)
            invalid = {
                "id": "act_duplicate",
                "created_at": "2026-06-27T00:00:00+00:00",
                "status": "invalid",
                "original_input": "/unknown",
                "input_type": "bad",
                "resolved_target": "bad",
                "commands": ["/unknown command"],
                "strictest_policy": "bad",
                "policy_summary": "bad fixture",
                "registry_summary": [],
                "no_execution": False,
                "executed_at": "never allowed",
            }
            queue_path.write_text(json.dumps(invalid) + "\n" + json.dumps(invalid) + "\nnot-json\n", encoding="utf-8")
            before = queue_path.read_bytes()

            output = format_action_queue_command("/action queue-doctor", project_root=project_root)

            self.assertIn("Status: ERROR", output)
            self.assertIn("Malformed JSONL records: 1", output)
            self.assertIn("Duplicate proposal ids", output)
            self.assertIn("invalid status", output)
            self.assertIn("invalid input_type", output)
            self.assertIn("no_execution=false without executed state", output)
            self.assertIn("forbidden execution receipt fields", output)
            self.assertEqual(queue_path.read_bytes(), before)

    def test_action_queue_status_works_with_missing_queue(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)

            output = format_action_queue_command("/action queue-status", project_root=project_root)

            self.assertIn("Action Proposal Queue Status", output)
            self.assertIn("readable: True", output)
            self.assertIn("total_records: 0", output)
            self.assertIn("oldest_proposed_age: none", output)
            self.assertIn("/action queue-export", output)

    def test_action_queue_export_creates_valid_markdown_and_json(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            format_action_queue_command("/action propose /data doctor", project_root=project_root)

            output = format_action_queue_command("/action queue-export", project_root=project_root)
            export_dir = project_root / "proto_mind" / "exports" / "action_queue"
            markdown_path = next(export_dir.glob("action_queue_*.md"))
            json_path = next(export_dir.glob("action_queue_*.json"))
            markdown = markdown_path.read_text(encoding="utf-8")
            payload = json.loads(json_path.read_text(encoding="utf-8"))

            self.assertIn("Action Proposal Queue Export", output)
            self.assertIn("# Proto-Mind Action Proposal Queue Export", markdown)
            self.assertIn("## Summary", markdown)
            self.assertIn("## Records", markdown)
            self.assertIn("no target commands were executed", markdown.lower())
            self.assertTrue(payload["no_target_commands_executed"])
            self.assertEqual(payload["total_records"], 1)
            self.assertTrue(all(record["no_execution"] is True for record in payload["records"]))

    def test_action_queue_export_does_not_execute_target_command(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            format_action_queue_command("/action propose включи контекст", project_root=project_root)
            queue_path = project_root / "proto_mind" / "data" / "action_queue.jsonl"
            before = queue_path.read_bytes()

            output = format_action_queue_command("/action queue-export", project_root=project_root)

            self.assertIn("No target commands were executed", output)
            self.assertEqual(queue_path.read_bytes(), before)
            self.assertFalse((project_root / "proto_mind" / "data" / "context_injection.json").exists())

    def test_action_cleanup_preview_exports_before_archiving_approved_item(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            created = format_action_queue_command("/action propose /data doctor", project_root=project_root)
            proposal_id = _id_from_output(created, "id:")
            format_action_queue_command(f"/action approve {proposal_id}", project_root=project_root)
            queue_path = project_root / "proto_mind" / "data" / "action_queue.jsonl"
            before = queue_path.read_bytes()

            output = format_action_queue_command("/action cleanup-preview", project_root=project_root)

            self.assertLess(output.index("/action queue-export"), output.index(f"/action archive {proposal_id}"))
            self.assertIn("No queue records or target stores were changed.", output)
            self.assertEqual(queue_path.read_bytes(), before)

    def test_action_confirm_preview_shows_token_without_mutation(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            created = format_action_queue_command("/action propose /data doctor", project_root=project_root)
            proposal_id = _id_from_output(created, "id:")
            format_action_queue_command(f"/action approve {proposal_id}", project_root=project_root)
            queue_path = project_root / "proto_mind" / "data" / "action_queue.jsonl"
            before = queue_path.read_bytes()

            output = format_action_queue_command(f"/action confirm-preview {proposal_id}", project_root=project_root)
            token = _id_from_output(output, "confirmation_token:")

            self.assertIn("Action Confirmation Preview", output)
            self.assertIn("confirmable: True", output)
            self.assertTrue(token.startswith("CONFIRM-ACTION-"))
            self.assertIn("No target command executed.", output)
            self.assertEqual(queue_path.read_bytes(), before)

    def test_action_confirm_rejects_wrong_token_and_pending_proposal(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            created = format_action_queue_command("/action propose /data doctor", project_root=project_root)
            proposal_id = _id_from_output(created, "id:")

            pending = format_action_queue_command(f"/action confirm {proposal_id} WRONG-TOKEN", project_root=project_root)
            format_action_queue_command(f"/action approve {proposal_id}", project_root=project_root)
            queue_path = project_root / "proto_mind" / "data" / "action_queue.jsonl"
            before = queue_path.read_bytes()
            wrong = format_action_queue_command(f"/action confirm {proposal_id} WRONG-TOKEN", project_root=project_root)

            self.assertIn("status must be approved", pending)
            self.assertIn("token mismatch", wrong)
            self.assertIn("No target command executed.", wrong)
            self.assertEqual(queue_path.read_bytes(), before)

    def test_action_confirm_confirmation_required_changes_queue_metadata_only(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            created = format_action_queue_command("/action propose /context injection enable", project_root=project_root)
            proposal_id = _id_from_output(created, "id:")
            format_action_queue_command(f"/action approve {proposal_id}", project_root=project_root)
            preview = format_action_queue_command(f"/action confirm-preview {proposal_id}", project_root=project_root)
            token = _id_from_output(preview, "confirmation_token:")

            output = format_action_queue_command(f"/action confirm {proposal_id} {token}", project_root=project_root)
            record = _single_action_record(project_root)

            self.assertIn("Action proposal confirmed", output)
            self.assertIn("No target command executed.", output)
            self.assertEqual(record["execution_state"], "confirmed")
            self.assertEqual(record["confirmation_method"], "explicit_token")
            self.assertEqual(record["confirmation_token_used"], token)
            self.assertTrue(record["confirmed_at"])
            self.assertTrue(record["no_execution"])
            self.assertFalse((project_root / "proto_mind" / "data" / "context_injection.json").exists())

    def test_action_confirm_rejects_blocked_proposal(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            created = format_action_queue_command("/action propose /unknown command", project_root=project_root)
            proposal_id = _id_from_output(created, "id:")
            format_action_queue_command(f"/action approve {proposal_id}", project_root=project_root)

            preview = format_action_queue_command(f"/action confirm-preview {proposal_id}", project_root=project_root)
            output = format_action_queue_command(f"/action confirm {proposal_id} CONFIRM-ACTION-FAKE", project_root=project_root)

            self.assertIn("confirmable: False", preview)
            self.assertIn("confirmation_token: unavailable", preview)
            self.assertIn("policy blocked is not confirmable", output)
            self.assertEqual(_single_action_record(project_root)["execution_state"], "unconfirmed")

    def test_action_unconfirm_and_inspect_show_confirmation_metadata(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            created = format_action_queue_command("/action propose /data doctor", project_root=project_root)
            proposal_id = _id_from_output(created, "id:")
            format_action_queue_command(f"/action approve {proposal_id}", project_root=project_root)
            preview = format_action_queue_command(f"/action confirm-preview {proposal_id}", project_root=project_root)
            token = _id_from_output(preview, "confirmation_token:")
            format_action_queue_command(f"/action confirm {proposal_id} {token}", project_root=project_root)

            output = format_action_queue_command(f'/action unconfirm {proposal_id} “smoke complete”', project_root=project_root)
            inspected = format_action_queue_command(f"/action inspect {proposal_id}", project_root=project_root)
            record = _single_action_record(project_root)

            self.assertIn("Action proposal unconfirmed", output)
            self.assertEqual(record["execution_state"], "unconfirmed")
            self.assertTrue(record["unconfirmed_at"])
            self.assertEqual(record["unconfirmed_reason"], "smoke complete")
            self.assertEqual(record["confirmation_token_used"], "")
            self.assertIn("execution_state: unconfirmed", inspected)
            self.assertIn("unconfirmed_reason: smoke complete", inspected)
            self.assertIn("no_execution: True", inspected)

    def test_action_queue_doctor_validates_confirmed_records(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            created = format_action_queue_command("/action propose /data doctor", project_root=project_root)
            proposal_id = _id_from_output(created, "id:")
            format_action_queue_command(f"/action approve {proposal_id}", project_root=project_root)
            preview = format_action_queue_command(f"/action confirm-preview {proposal_id}", project_root=project_root)
            token = _id_from_output(preview, "confirmation_token:")
            format_action_queue_command(f"/action confirm {proposal_id} {token}", project_root=project_root)

            healthy = format_action_queue_command("/action queue-doctor", project_root=project_root)
            queue_path = project_root / "proto_mind" / "data" / "action_queue.jsonl"
            record = _single_action_record(project_root)
            record["status"] = "archived"
            queue_path.write_text(json.dumps(record) + "\n", encoding="utf-8")
            invalid = format_action_queue_command("/action queue-doctor", project_root=project_root)

            self.assertIn("Status: OK", healthy)
            self.assertIn("Status: ERROR", invalid)
            self.assertIn("Confirmed proposal is not approved", invalid)

    def test_action_queue_export_includes_confirmation_metadata(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            created = format_action_queue_command("/action propose /data doctor", project_root=project_root)
            proposal_id = _id_from_output(created, "id:")
            format_action_queue_command(f"/action approve {proposal_id}", project_root=project_root)
            preview = format_action_queue_command(f"/action confirm-preview {proposal_id}", project_root=project_root)
            token = _id_from_output(preview, "confirmation_token:")
            format_action_queue_command(f"/action confirm {proposal_id} {token}", project_root=project_root)

            format_action_queue_command("/action queue-export", project_root=project_root)
            export_path = next((project_root / "proto_mind" / "exports" / "action_queue").glob("action_queue_*.json"))
            record = json.loads(export_path.read_text(encoding="utf-8"))["records"][0]

            self.assertEqual(record["execution_state"], "confirmed")
            self.assertEqual(record["confirmation_method"], "explicit_token")
            self.assertEqual(record["confirmation_token_used"], token)
            self.assertTrue(record["no_execution"])

    def test_action_cleanup_preview_unconfirms_before_archiving_confirmed_item(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            created = format_action_queue_command("/action propose /data doctor", project_root=project_root)
            proposal_id = _id_from_output(created, "id:")
            format_action_queue_command(f"/action approve {proposal_id}", project_root=project_root)
            preview = format_action_queue_command(f"/action confirm-preview {proposal_id}", project_root=project_root)
            token = _id_from_output(preview, "confirmation_token:")
            format_action_queue_command(f"/action confirm {proposal_id} {token}", project_root=project_root)
            queue_path = project_root / "proto_mind" / "data" / "action_queue.jsonl"
            before = queue_path.read_bytes()

            output = format_action_queue_command("/action cleanup-preview", project_root=project_root)

            self.assertLess(output.index(f"/action unconfirm {proposal_id}"), output.index(f"/action archive {proposal_id}"))
            self.assertEqual(queue_path.read_bytes(), before)

    def test_action_queue_status_counts_confirmed_items(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            created = format_action_queue_command("/action propose /data doctor", project_root=project_root)
            proposal_id = _id_from_output(created, "id:")
            format_action_queue_command(f"/action approve {proposal_id}", project_root=project_root)
            preview = format_action_queue_command(f"/action confirm-preview {proposal_id}", project_root=project_root)
            token = _id_from_output(preview, "confirmation_token:")
            format_action_queue_command(f"/action confirm {proposal_id} {token}", project_root=project_root)

            output = format_action_queue_command("/action queue-status", project_root=project_root)

            self.assertIn("execution_state_counts: confirmed=1", output)

    def test_action_run_preview_confirmed_read_only_action_is_ready(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            proposal_id, _ = _confirmed_action(project_root, "/data doctor")
            queue_path = project_root / "proto_mind" / "data" / "action_queue.jsonl"
            before = queue_path.read_bytes()

            output = format_action_queue_command(f"/action run-preview {proposal_id}", project_root=project_root)

            self.assertIn("Action Run Preview", output)
            self.assertIn("readiness: READY", output)
            self.assertIn("/data doctor", output)
            self.assertIn("No target command executed.", output)
            self.assertEqual(queue_path.read_bytes(), before)

    def test_action_run_preview_approved_unconfirmed_is_not_ready(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            created = format_action_queue_command("/action propose /data doctor", project_root=project_root)
            proposal_id = _id_from_output(created, "id:")
            format_action_queue_command(f"/action approve {proposal_id}", project_root=project_root)

            output = format_action_queue_command(f"/action run-preview {proposal_id}", project_root=project_root)

            self.assertIn("readiness: NOT READY", output)
            self.assertIn("execution_state is not confirmed", output)
            self.assertIn("No target command executed.", output)

    def test_action_run_preview_pending_is_not_ready(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            created = format_action_queue_command("/action propose /data doctor", project_root=project_root)
            proposal_id = _id_from_output(created, "id:")

            output = format_action_queue_command(f"/action run-preview {proposal_id}", project_root=project_root)

            self.assertIn("readiness: NOT READY", output)
            self.assertIn("proposal status is not approved", output)
            self.assertIn("execution_state is not confirmed", output)

    def test_action_run_preview_missing_and_unknown_id_are_clean(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)

            missing = format_action_queue_command("/action run-preview", project_root=project_root)
            unknown = format_action_queue_command("/action run-preview act_missing", project_root=project_root)

            self.assertEqual(missing, "Usage: /action run-preview <id>")
            self.assertIn("Action proposal not found: act_missing", unknown)

    def test_action_run_preview_blocked_and_operator_only_are_not_ready(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            blocked_created = format_action_queue_command("/action propose /unknown command", project_root=project_root)
            blocked_id = _id_from_output(blocked_created, "id:")
            format_action_queue_command(f"/action approve {blocked_id}", project_root=project_root)
            operator_created = format_action_queue_command(
                "/action propose /consolidation queue-apply item", project_root=project_root
            )
            operator_id = _id_from_output(operator_created, "id:")
            format_action_queue_command(f"/action approve {operator_id}", project_root=project_root)

            blocked = format_action_queue_command(f"/action run-preview {blocked_id}", project_root=project_root)
            operator_only = format_action_queue_command(f"/action run-preview {operator_id}", project_root=project_root)

            self.assertIn("readiness: NOT READY", blocked)
            self.assertIn("stored policy blocked", blocked)
            self.assertIn("readiness: NOT READY", operator_only)
            self.assertIn("stored policy operator_only", operator_only)

    def test_action_run_preview_mutation_requires_future_receipt_without_execution(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            proposal_id, _ = _confirmed_action(project_root, "/context injection enable")
            queue_path = project_root / "proto_mind" / "data" / "action_queue.jsonl"
            before = queue_path.read_bytes()

            output = format_action_queue_command(f"/action run-preview {proposal_id}", project_root=project_root)

            self.assertIn("readiness: NOT READY", output)
            self.assertIn("run requires stored policy auto_allowed", output)
            self.assertIn("Future mutation receipt is required for target store(s): context", output)
            self.assertIn("rollback or undo metadata", output)
            self.assertIn("target record identifiers and rollback guidance", output)
            self.assertIn("No target command executed.", output)
            self.assertEqual(queue_path.read_bytes(), before)
            self.assertFalse((project_root / "proto_mind" / "data" / "context_injection.json").exists())

    def test_action_readiness_doctor_returns_ok_and_warn_cleanly(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            empty = format_action_queue_command("/action readiness-doctor", project_root=project_root)
            created = format_action_queue_command("/action propose /data doctor", project_root=project_root)
            proposal_id = _id_from_output(created, "id:")
            format_action_queue_command(f"/action approve {proposal_id}", project_root=project_root)
            queue_path = project_root / "proto_mind" / "data" / "action_queue.jsonl"
            before = queue_path.read_bytes()

            warning = format_action_queue_command("/action readiness-doctor", project_root=project_root)

            self.assertIn("Status: OK", empty)
            self.assertIn("Status: WARN", warning)
            self.assertIn("Approved but unconfirmed proposals: 1", warning)
            self.assertIn("v1.5 run support is limited", warning)
            self.assertEqual(queue_path.read_bytes(), before)

    def test_action_readiness_doctor_detects_confirmed_blocked_and_missing_no_execution(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            proposal_id, _ = _confirmed_action(project_root, "/data doctor")
            queue_path = project_root / "proto_mind" / "data" / "action_queue.jsonl"
            record = _single_action_record(project_root)
            record["strictest_policy"] = "blocked"
            record["no_execution"] = False
            queue_path.write_text(json.dumps(record) + "\n", encoding="utf-8")
            before = queue_path.read_bytes()

            output = format_action_queue_command("/action readiness-doctor", project_root=project_root)

            self.assertIn("Status: ERROR", output)
            self.assertIn("no_execution must remain true", output)
            self.assertIn("stored policy blocked", output)
            self.assertIn(proposal_id, output)
            self.assertEqual(queue_path.read_bytes(), before)

    def test_action_run_executes_data_doctor_and_stores_read_only_receipt(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            coordinator, _, _ = build_test_system(project_root / "proto_mind")
            logger = SessionOperatorLogger.from_project_root(project_root)
            coordinator.session_logger = logger
            proposal_id, _ = _confirmed_action(project_root, "/data doctor")
            queue_path = project_root / "proto_mind" / "data" / "action_queue.jsonl"

            def target_snapshot() -> dict[Path, bytes]:
                return {
                    path.relative_to(project_root): path.read_bytes()
                    for path in project_root.rglob("*")
                    if path.is_file() and path != queue_path
                }

            before = target_snapshot()
            output = process_interactive_input(
                f"/action run {proposal_id}",
                coordinator=coordinator,
                session_logger=logger,
                project_root=project_root,
            )
            receipt_output = process_interactive_input(
                f"/action run-receipt {proposal_id}",
                coordinator=coordinator,
                session_logger=logger,
                project_root=project_root,
            )
            record = _single_action_record(project_root)

            self.assertIn("Status: RUN", output)
            self.assertIn("Data Integrity Doctor", output)
            self.assertEqual(record["execution_state"], "executed")
            self.assertFalse(record["no_execution"])
            self.assertTrue(record["target_execution_performed"])
            self.assertEqual(record["run_policy"], "read_only_auto_allowed")
            self.assertTrue(record["executed_at"])
            self.assertTrue(str(record["run_id"]).startswith("run_"))
            self.assertEqual(record["executed_command_count"], 1)
            self.assertEqual(len(str(record["receipt_hash"])), 64)
            self.assertTrue(record["run_receipt"]["success"])
            self.assertEqual(record["run_receipt"]["run_id"], record["run_id"])
            self.assertEqual(record["run_receipt"]["executed_command_count"], 1)
            self.assertEqual(record["run_receipt"]["receipt_hash"], record["receipt_hash"])
            self.assertEqual(record["run_receipt"]["commands"][0]["command"], "/data doctor")
            self.assertIn("description", record["run_receipt"]["commands"][0])
            self.assertIn("risk", record["run_receipt"]["commands"][0])
            self.assertIn("Action Run Receipt", receipt_output)
            self.assertIn("run_id:", receipt_output)
            self.assertIn("executed_command_count: 1", receipt_output)
            self.assertIn("no_execution: False", receipt_output)
            self.assertIn("receipt_hash:", receipt_output)
            self.assertIn("output_preview:", receipt_output)
            self.assertEqual(target_snapshot(), before)
            self.assertEqual(logger.status().entry_count, 0)

    def test_action_run_refuses_unconfirmed_and_confirmation_required_targets(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            coordinator, _, _ = build_test_system(project_root / "proto_mind")
            logger = SessionOperatorLogger.from_project_root(project_root)
            coordinator.session_logger = logger
            created = format_action_queue_command("/action propose /data doctor", project_root=project_root)
            unconfirmed_id = _id_from_output(created, "id:")
            format_action_queue_command(f"/action approve {unconfirmed_id}", project_root=project_root)
            context_id, _ = _confirmed_action(project_root, "/context injection enable")
            queue_path = project_root / "proto_mind" / "data" / "action_queue.jsonl"
            before = queue_path.read_bytes()

            unconfirmed = process_interactive_input(
                f"/action run {unconfirmed_id}", coordinator=coordinator, session_logger=logger, project_root=project_root
            )
            context = process_interactive_input(
                f"/action run {context_id}", coordinator=coordinator, session_logger=logger, project_root=project_root
            )

            self.assertIn("Status: NOT RUN", unconfirmed)
            self.assertIn("execution_state is not confirmed", unconfirmed)
            self.assertIn("Status: NOT RUN", context)
            self.assertIn("run requires stored policy auto_allowed", context)
            self.assertIn("run command is not auto_allowed", context)
            self.assertEqual(queue_path.read_bytes(), before)
            self.assertFalse((project_root / "proto_mind" / "data" / "context_injection.json").exists())

    def test_action_run_refuses_memory_mutation_without_changing_memory(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            coordinator, _, _ = build_test_system(project_root / "proto_mind")
            logger = SessionOperatorLogger.from_project_root(project_root)
            proposal_id, _ = _confirmed_action(project_root, "/memory remember must not run")
            persistent_path = project_root / "proto_mind" / "data" / "persistent_memory.json"
            before = persistent_path.read_bytes()

            output = process_interactive_input(
                f"/action run {proposal_id}", coordinator=coordinator, session_logger=logger, project_root=project_root
            )

            self.assertIn("Status: NOT RUN", output)
            self.assertIn("run command declares mutation target memory", output)
            self.assertEqual(persistent_path.read_bytes(), before)
            self.assertNotIn("must not run", persistent_path.read_text(encoding="utf-8"))

    def test_action_run_refuses_unknown_shell_and_operator_only_records(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            coordinator, _, _ = build_test_system(project_root / "proto_mind")
            logger = SessionOperatorLogger.from_project_root(project_root)
            proposal_id, _ = _confirmed_action(project_root, "/data doctor")
            queue_path = project_root / "proto_mind" / "data" / "action_queue.jsonl"
            record = _single_action_record(project_root)

            outputs = []
            for command, policy in (
                ("/unknown command", "blocked"),
                ("/data doctor; /memory doctor", "blocked"),
                ("/consolidation queue-apply item", "operator_only"),
            ):
                record["commands"] = [command]
                record["strictest_policy"] = policy
                queue_path.write_text(json.dumps(record) + "\n", encoding="utf-8")
                outputs.append(
                    process_interactive_input(
                        f"/action run {proposal_id}",
                        coordinator=coordinator,
                        session_logger=logger,
                        project_root=project_root,
                    )
                )

            self.assertTrue(all("Status: NOT RUN" in output for output in outputs))
            self.assertIn("not registered", outputs[0])
            self.assertIn("blocked under current policy", outputs[1])
            self.assertIn("operator_only", outputs[2])

    def test_action_run_validates_whole_mixed_bundle_before_execution(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            coordinator, _, _ = build_test_system(project_root / "proto_mind")
            logger = SessionOperatorLogger.from_project_root(project_root)
            proposal_id, _ = _confirmed_action(project_root, "/data doctor")
            queue_path = project_root / "proto_mind" / "data" / "action_queue.jsonl"
            record = _single_action_record(project_root)
            record["commands"] = ["/data doctor", "/context injection enable"]
            record["strictest_policy"] = "confirmation_required"
            queue_path.write_text(json.dumps(record) + "\n", encoding="utf-8")
            before = queue_path.read_bytes()

            output = process_interactive_input(
                f"/action run {proposal_id}", coordinator=coordinator, session_logger=logger, project_root=project_root
            )

            self.assertIn("Status: NOT RUN", output)
            self.assertIn("/context injection enable", output)
            self.assertEqual(queue_path.read_bytes(), before)
            self.assertFalse((project_root / "proto_mind" / "data" / "context_injection.json").exists())

    def test_action_run_supports_safe_read_only_bundle(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            coordinator, _, _ = build_test_system(project_root / "proto_mind")
            logger = SessionOperatorLogger.from_project_root(project_root)
            proposal_id, _ = _confirmed_action(project_root, "проверь систему")

            output = process_interactive_input(
                f"/action run {proposal_id}", coordinator=coordinator, session_logger=logger, project_root=project_root
            )
            record = _single_action_record(project_root)

            self.assertIn("Status: RUN", output)
            self.assertIn("Data Integrity Doctor", output)
            self.assertIn("Cross-Store Reference Doctor", output)
            self.assertEqual(len(record["run_receipt"]["commands"]), len(HEALTH_CHECK_BUNDLE))
            self.assertTrue(all(item["success"] for item in record["run_receipt"]["commands"]))

    def test_action_run_once_refuses_second_execution_without_queue_mutation(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            proposal_id, _ = _confirmed_action(project_root, "/data doctor")
            calls: list[str] = []

            first = format_action_queue_command(
                f"/action run {proposal_id}",
                project_root=project_root,
                executor=lambda command: calls.append(command) or "doctor output",
            )
            queue_path = project_root / "proto_mind" / "data" / "action_queue.jsonl"
            before_second = queue_path.read_bytes()
            second = format_action_queue_command(
                f"/action run {proposal_id}",
                project_root=project_root,
                executor=lambda command: calls.append(f"again:{command}") or "must not run",
            )

            self.assertIn("Status: RUN", first)
            self.assertIn("Status: NOT RUN", second)
            self.assertIn("already executed", second)
            self.assertIn(f"/action run-receipt {proposal_id}", second)
            self.assertEqual(calls, ["/data doctor"])
            self.assertEqual(queue_path.read_bytes(), before_second)

    def test_action_run_preview_executed_record_is_not_ready_and_read_only(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            proposal_id, _ = _confirmed_action(project_root, "/data doctor")
            format_action_queue_command(
                f"/action run {proposal_id}", project_root=project_root, executor=lambda command: "doctor output"
            )
            queue_path = project_root / "proto_mind" / "data" / "action_queue.jsonl"
            before = queue_path.read_bytes()

            output = format_action_queue_command(f"/action run-preview {proposal_id}", project_root=project_root)

            self.assertIn("Action Run Preview", output)
            self.assertIn("readiness: NOT READY", output)
            self.assertIn("already executed", output)
            self.assertIn(f"/action run-receipt {proposal_id}", output)
            self.assertIn("No target command executed.", output)
            self.assertEqual(queue_path.read_bytes(), before)

    def test_action_queue_doctor_detects_v2_receipt_count_and_hash_corruption(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            proposal_id, _ = _confirmed_action(project_root, "/data doctor")
            format_action_queue_command(
                f"/action run {proposal_id}", project_root=project_root, executor=lambda command: "doctor output"
            )
            queue_path = project_root / "proto_mind" / "data" / "action_queue.jsonl"
            record = _single_action_record(project_root)
            record["executed_command_count"] = 2
            record["run_receipt"]["commands"][0]["output_preview"] = "tampered"
            queue_path.write_text(json.dumps(record) + "\n", encoding="utf-8")

            output = format_action_queue_command("/action queue-doctor", project_root=project_root)

            self.assertIn("Status: ERROR", output)
            self.assertIn("executed_command_count mismatch", output)
            self.assertIn("receipt_hash does not match", output)

    def test_action_queue_doctor_warns_for_legacy_receipt_without_guardrail_fields(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            proposal_id, _ = _confirmed_action(project_root, "/data doctor")
            format_action_queue_command(
                f"/action run {proposal_id}", project_root=project_root, executor=lambda command: "doctor output"
            )
            queue_path = project_root / "proto_mind" / "data" / "action_queue.jsonl"
            record = _single_action_record(project_root)
            record["run_receipt"]["version"] = 1
            for field in ("run_id", "executed_command_count", "receipt_hash"):
                record.pop(field, None)
                record["run_receipt"].pop(field, None)
            record["run_receipt"]["commands"][0].pop("description", None)
            record["run_receipt"]["commands"][0].pop("risk", None)
            queue_path.write_text(json.dumps(record) + "\n", encoding="utf-8")

            output = format_action_queue_command("/action queue-doctor", project_root=project_root)

            self.assertIn("Status: WARN", output)
            self.assertIn("missing run_id", output)
            self.assertIn("missing receipt_hash", output)

    def test_action_runs_lists_executed_records_and_respects_last_limit(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            first_id = _executed_action(project_root)
            second_id = _executed_action(project_root, "/memory doctor")

            all_runs = format_action_queue_command("/action runs --all", project_root=project_root)
            latest = format_action_queue_command("/action runs --last 1", project_root=project_root)

            self.assertIn("Action Runs (all)", all_runs)
            self.assertIn(first_id, all_runs)
            self.assertIn(second_id, all_runs)
            self.assertIn("run_id=run_", all_runs)
            self.assertIn("hash=", all_runs)
            self.assertIn("shown: 1", latest)
            self.assertIn(second_id, latest)

    def test_action_run_verify_v2_receipt_is_verified_and_read_only(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            proposal_id = _executed_action(project_root)
            queue_path = project_root / "proto_mind" / "data" / "action_queue.jsonl"
            before = queue_path.read_bytes()

            output = format_action_queue_command(f"/action run-verify {proposal_id}", project_root=project_root)

            self.assertIn("Action Run Verify", output)
            self.assertIn("Status: VERIFIED", output)
            self.assertIn("run_id: run_", output)
            self.assertIn("receipt_hash:", output)
            self.assertIn("No target command executed.", output)
            self.assertEqual(queue_path.read_bytes(), before)

    def test_action_run_verify_handles_missing_and_non_executed_ids(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            created = format_action_queue_command("/action propose /data doctor", project_root=project_root)
            proposal_id = _id_from_output(created, "id:")

            missing = format_action_queue_command("/action run-verify", project_root=project_root)
            unknown = format_action_queue_command("/action run-verify act_missing", project_root=project_root)
            not_executed = format_action_queue_command(f"/action run-verify {proposal_id}", project_root=project_root)

            self.assertEqual(missing, "Usage: /action run-verify <id>")
            self.assertIn("Action proposal not found", unknown)
            self.assertIn("Status: ERROR", not_executed)
            self.assertIn("proposal is not executed", not_executed)

    def test_action_run_verify_detects_receipt_hash_mismatch(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            proposal_id = _executed_action(project_root)
            queue_path = project_root / "proto_mind" / "data" / "action_queue.jsonl"
            record = _single_action_record(project_root)
            record["run_receipt"]["commands"][0]["output_preview"] = "tampered audit fixture"
            queue_path.write_text(json.dumps(record) + "\n", encoding="utf-8")

            output = format_action_queue_command(f"/action run-verify {proposal_id}", project_root=project_root)

            self.assertIn("Status: ERROR", output)
            self.assertIn("receipt_hash does not match", output)

    def test_action_run_audit_returns_ok_and_does_not_mutate_queue(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _executed_action(project_root)
            queue_path = project_root / "proto_mind" / "data" / "action_queue.jsonl"
            before = queue_path.read_bytes()

            output = format_action_queue_command("/action run-audit", project_root=project_root)

            self.assertIn("Action Execution Audit", output)
            self.assertIn("Status: OK", output)
            self.assertIn("executed records: 1", output)
            self.assertIn("receipt v2: 1", output)
            self.assertIn("hash verified: 1", output)
            self.assertIn("Read-only audit only", output)
            self.assertEqual(queue_path.read_bytes(), before)

    def test_action_run_audit_detects_duplicate_run_id(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _executed_action(project_root)
            _executed_action(project_root, "/memory doctor")
            queue_path = project_root / "proto_mind" / "data" / "action_queue.jsonl"
            records = [json.loads(line) for line in queue_path.read_text(encoding="utf-8").splitlines()]
            records[1]["run_id"] = records[0]["run_id"]
            records[1]["run_receipt"]["run_id"] = records[0]["run_id"]
            queue_path.write_text("".join(json.dumps(item) + "\n" for item in records), encoding="utf-8")

            output = format_action_queue_command("/action run-audit", project_root=project_root)

            self.assertIn("Status: ERROR", output)
            self.assertIn("duplicate run_id groups: 1", output)
            self.assertIn("Duplicate run_id values", output)

    def test_action_run_audit_detects_executed_mutating_command(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            proposal_id = _executed_action(project_root)
            queue_path = project_root / "proto_mind" / "data" / "action_queue.jsonl"
            record = _single_action_record(project_root)
            record["commands"] = ["/context injection enable"]
            record["strictest_policy"] = "confirmation_required"
            queue_path.write_text(json.dumps(record) + "\n", encoding="utf-8")

            output = format_action_queue_command("/action run-audit", project_root=project_root)

            self.assertIn("Status: ERROR", output)
            self.assertIn("mutating command records: 1", output)
            self.assertIn("executed command is not auto_allowed", output)
            self.assertIn(proposal_id, output)

    def test_action_propose_and_approve_mutating_target_do_not_mutate_target_store(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            coordinator, _, _ = build_test_system(project_root / "proto_mind")
            logger = SessionOperatorLogger.from_project_root(project_root)
            coordinator.session_logger = logger
            data_dir = project_root / "proto_mind" / "data"
            persistent = data_dir / "persistent_memory.json"
            before_memory = persistent.read_bytes()

            created = process_interactive_input(
                "/action propose /memory remember proposal must not execute",
                coordinator=coordinator,
                session_logger=logger,
                project_root=project_root,
            )
            proposal_id = _id_from_output(created, "id:")
            approved = process_interactive_input(
                f"/action approve {proposal_id}",
                coordinator=coordinator,
                session_logger=logger,
                project_root=project_root,
            )

            self.assertIn("No target command executed.", created)
            self.assertIn("No target command executed.", approved)
            self.assertEqual(persistent.read_bytes(), before_memory)
            self.assertEqual(logger.status().entry_count, 0)
