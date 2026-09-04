"""Core flow checks: runner."""
from __future__ import annotations

import unittest
from proto_mind.tests.flow_fixtures import (
    ACTIVE_READONLY_ALLOWLIST,
    CAPABILITIES_SAFETY_COMMAND,
    CAPABILITIES_SAFETY_CONFIRMATION,
    COMMAND_REGISTRY,
    DAILY_DOCTOR_COMMAND,
    DAILY_DOCTOR_CONFIRMATION,
    EVIDENCE_HISTORY_MAX_SIZE,
    EXACT_CONFIRMATION,
    EXPORTS_DOCTOR_COMMAND,
    EXPORTS_DOCTOR_CONFIRMATION,
    FUTURE_RUNNER_CANDIDATES,
    MVP_ALLOWLIST_CANDIDATES,
    PILOT_COMMAND,
    Path,
    ReadOnlyRunnerPilot,
    SessionOperatorLogger,
    TemporaryDirectory,
    _create_healthy_export_dirs,
    _runner_candidates_state,
    _runner_exec_executors,
    _runner_exec_state,
    _runner_mvp_state,
    _runner_state,
    _write_milestone_fixture,
    build_test_system,
    format_context_command,
    format_runner_candidates_command,
    format_runner_command,
    format_runner_exec_command,
    format_runner_mvp_command,
    json,
    patch,
    process_interactive_input,
    reset_runner_exec_evidence,
)


class RunnerFlowTests(unittest.TestCase):
    def test_runner_status_reports_warn_baseline_and_fixed_disabled_state(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            with patch("proto_mind.runner_layer.NoOpRunnerContract.read_state", return_value=_runner_state()):
                output = format_runner_command("/runner status", project_root=project_root, memory_store=store)

            self.assertIn("No-Op Runner Contract Status", output)
            self.assertIn("Status: WARN", output)
            self.assertIn("command_registry: commands=387 categories=41", output)
            self.assertIn("context_injection: disabled", output)
            self.assertIn("sandbox_blueprint_readiness: WARN", output)
            self.assertIn("confirmation_gate_readiness: WARN", output)
            self.assertIn("accepted_known_warnings: 12", output)
            self.assertIn("unknown_warnings: 0", output)
            self.assertIn("blockers: 0", output)
            self.assertIn("noop_runner_contract_generation_safe: true", output)
            self.assertIn("execution_enabled=false", output)
            self.assertIn("active_allowlist=false", output)

    def test_runner_status_blocks_unknown_warnings_or_blockers(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            with patch(
                "proto_mind.runner_layer.NoOpRunnerContract.read_state",
                return_value=_runner_state(unknown=True, blockers=1),
            ):
                output = format_runner_command("/runner status", project_root=project_root, memory_store=store)

            self.assertIn("Status: BLOCKED", output)
            self.assertIn("unknown_warnings: 1", output)
            self.assertIn("blockers: 1", output)
            self.assertIn("noop_runner_contract_generation_safe: false", output)
            self.assertIn("execution_enabled=false", output)

    def test_runner_contract_lists_request_response_and_noop_invariants(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")

            output = format_runner_command("/runner contract", project_root=project_root, memory_store=store)

            self.assertIn("Future Runner Interface Contract (No-Op v1)", output)
            for field in ("request_id", "operator_intent", "command_candidate", "safety_class", "confirmation_level", "allowed_writes", "forbidden_writes", "stop_conditions"):
                self.assertIn(field, output)
            for field in ("execution_enabled", "executed", "reason", "simulated_plan", "required_confirmation", "next_manual_step"):
                self.assertIn(field, output)
            self.assertIn("execution_enabled=false", output)
            self.assertIn("executed=false", output)
            self.assertIn("DRY_RUN_ONLY or EXECUTION_DISABLED", output)

    def test_runner_noop_sample_never_executes_or_mutates(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")

            output = format_runner_command("/runner noop", project_root=project_root, memory_store=store)

            self.assertIn("Sample No-Op Runner Response", output)
            self.assertIn("command_candidate: /warnings unknown", output)
            self.assertIn("status: DRY_RUN_ONLY", output)
            self.assertIn("execution_enabled=false", output)
            self.assertIn("executed=false", output)
            self.assertIn("files_written: none", output)
            self.assertIn("state_mutation: none", output)
            self.assertIn("no subprocess/shell/eval/exec", output)
            self.assertIn("Operator may run /warnings unknown manually", output)

    def test_runner_evidence_marks_execution_fields_unavailable(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")

            output = format_runner_command("/runner evidence", project_root=project_root, memory_store=store)

            self.assertIn("Future Runner Evidence Model", output)
            for field in ("command_requested", "gates_checked", "stdout_stderr_summary_if_executed", "files_changed_summary", "data_exports_sha256_summary", "tests_compile_smoke_summary", "post_run_acceptance_status"):
                self.assertIn(f"{field}: NOT_AVAILABLE_NOOP", output)
            self.assertIn("execution evidence was neither fabricated nor persisted", output)

    def test_runner_disabled_explains_every_absent_execution_capability(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")

            output = format_runner_command("/runner disabled", project_root=project_root, memory_store=store)

            self.assertIn("Why Runner Execution Is Disabled", output)
            self.assertIn("execution_enabled=false", output)
            self.assertIn("executed=false", output)
            self.assertIn("No active allowlist exists", output)
            self.assertIn("No approval capture exists", output)
            self.assertIn("No authorization engine exists", output)
            self.assertIn("No execution engine exists", output)
            self.assertIn("operator must run any desired command manually", output)

    def test_runner_handoff_contains_noop_contract_gates_and_v214_boundary(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            with patch("proto_mind.runner_layer.NoOpRunnerContract.read_state", return_value=_runner_state()):
                output = format_runner_command("/runner handoff", project_root=project_root, memory_store=store)

            self.assertIn("Proto-Mind No-Op Runner Contract Handoff", output)
            self.assertIn("Registry: 387 commands across 41 categories", output)
            self.assertIn("read_only=292, mutating=95, high_risk=4", output)
            self.assertIn("execution_enabled=false; executed=false", output)
            self.assertIn("Active allowlist: absent", output)
            self.assertIn("Execution engine: absent", output)
            self.assertIn("/runner-mvp design", output)

    def test_runner_doctor_checks_dependencies_context_and_no_execution(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            with patch("proto_mind.runner_layer.NoOpRunnerContract.read_state", return_value=_runner_state()):
                output = format_runner_command("/runner doctor", project_root=project_root, memory_store=store)

            self.assertIn("No-Op Runner Contract Doctor", output)
            self.assertIn("Status: OK", output)
            self.assertIn("All runner commands are registered", output)
            self.assertIn("low-risk, read-only, and mutates=none", output)
            self.assertIn("No active allowlist exists", output)
            self.assertIn("Context Injection is disabled", output)
            self.assertIn("No execution callback, active allowlist, subprocess/shell/eval/exec path", output)
            self.assertIn("execution_enabled=false and executed=false", output)

    def test_runner_doctor_warns_without_changing_enabled_context(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            format_context_command("/context injection enable", project_root=project_root)
            settings_path = project_root / "proto_mind" / "data" / "context_injection.json"
            before = settings_path.read_bytes()
            with patch(
                "proto_mind.runner_layer.NoOpRunnerContract.read_state",
                return_value=_runner_state(context_state="enabled"),
            ):
                output = format_runner_command("/runner doctor", project_root=project_root, memory_store=store)

            self.assertIn("Status: WARN", output)
            self.assertIn("Context Injection is explicitly enabled", output)
            self.assertEqual(settings_path.read_bytes(), before)
            self.assertTrue(json.loads(settings_path.read_text(encoding="utf-8"))["enabled"])

    def test_runner_commands_are_read_only_through_shared_handler(self) -> None:
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
                    "/runner status",
                    "/runner contract",
                    "/runner noop",
                    "/runner evidence",
                    "/runner disabled",
                    "/runner doctor",
                    "/runner handoff",
                )
            ]

            self.assertIn("No-Op Runner Contract Status", outputs[0])
            self.assertIn("Future Runner Interface Contract (No-Op v1)", outputs[1])
            self.assertIn("Sample No-Op Runner Response", outputs[2])
            self.assertIn("Future Runner Evidence Model", outputs[3])
            self.assertIn("Why Runner Execution Is Disabled", outputs[4])
            self.assertIn("No-Op Runner Contract Doctor", outputs[5])
            self.assertIn("Proto-Mind No-Op Runner Contract Handoff", outputs[6])
            for output in outputs:
                if "execution_enabled" in output:
                    self.assertNotIn("execution_enabled=true", output)
                if "executed" in output:
                    self.assertNotIn("executed=true", output)
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

    def test_runner_candidates_status_reports_warn_and_inactive_set(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            with patch("proto_mind.runner_candidates.RunnerCandidateSet.read_state", return_value=_runner_candidates_state()):
                output = format_runner_candidates_command("/runner-candidates status", project_root=project_root, memory_store=store)

            self.assertIn("Runner Candidate Set Status", output)
            self.assertIn("Status: WARN", output)
            self.assertIn("command_registry: commands=387 categories=41", output)
            self.assertIn("context_injection: disabled", output)
            self.assertIn("runner_contract_readiness: WARN", output)
            self.assertIn("candidate_count: 13", output)
            self.assertIn("verified_candidates: 13", output)
            self.assertIn("active_allowlist: none/inactive", output)
            self.assertIn("execution_enabled=false", output)
            self.assertIn("candidate_set_generation_safe: true", output)

    def test_runner_candidates_status_blocks_unknown_or_blockers(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            with patch(
                "proto_mind.runner_candidates.RunnerCandidateSet.read_state",
                return_value=_runner_candidates_state(unknown=True, blockers=1),
            ):
                output = format_runner_candidates_command("/runner-candidates status", project_root=project_root, memory_store=store)

            self.assertIn("Status: BLOCKED", output)
            self.assertIn("unknown_warnings: 1", output)
            self.assertIn("blockers: 1", output)
            self.assertIn("candidate_set_generation_safe: false", output)
            self.assertIn("active_allowlist: none/inactive", output)

    def test_runner_candidates_list_marks_every_item_inactive(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")

            output = format_runner_candidates_command("/runner-candidates list", project_root=project_root, memory_store=store)

            self.assertIn("Future Read-Only Runner Candidate Set", output)
            self.assertEqual(output.count("FUTURE_CANDIDATE | NOT_ACTIVE | NOT_EXECUTABLE_BY_RUNNER_YET"), 13)
            self.assertEqual(output.count("REGISTRY_VERIFIED"), 13)
            for command, *_ in FUTURE_RUNNER_CANDIDATES:
                self.assertIn(command, output)
            self.assertIn("This set is not an allowlist", output)

    def test_runner_candidates_explain_includes_metadata_gates_and_limits(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")

            output = format_runner_candidates_command("/runner-candidates explain", project_root=project_root, memory_store=store)

            self.assertIn("Runner Candidate Explanations", output)
            self.assertEqual(output.count("marker: FUTURE_CANDIDATE | NOT_ACTIVE | NOT_EXECUTABLE_BY_RUNNER_YET"), 13)
            self.assertIn("policy=auto_allowed", output)
            self.assertIn("required_gates:", output)
            self.assertIn("expected_output:", output)
            self.assertIn("future_value:", output)
            self.assertIn("limitation:", output)
            self.assertNotIn("NEEDS_REVIEW", output)

    def test_runner_candidates_denied_excludes_unsafe_and_unlisted_commands(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")

            output = format_runner_candidates_command("/runner-candidates denied", project_root=project_root, memory_store=store)

            self.assertIn("Runner Candidate Set Exclusions", output)
            self.assertIn("Every mutating command is excluded", output)
            self.assertIn("high-risk or operator-only", output)
            self.assertIn("unknown/unregistered command is excluded and BLOCKED", output)
            self.assertIn("not explicitly listed", output)
            self.assertIn("Shell, subprocess, pipeline, eval, exec", output)
            self.assertIn("active_allowlist: none/inactive", output)

    def test_runner_candidates_gates_require_separate_activation_milestone(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")

            output = format_runner_candidates_command("/runner-candidates gates", project_root=project_root, memory_store=store)

            self.assertIn("Future Candidate Activation Gates", output)
            self.assertIn("Rule 0 backup/checkpoint", output)
            self.assertIn("/warnings unknown reports 0", output)
            self.assertIn("Context Injection is disabled", output)
            self.assertIn("active allowlist is implemented only in a separate explicit checkpointed task", output)
            self.assertIn("No execution occurs before a separately approved v3.x", output)
            self.assertIn("cannot satisfy gates, activate an allowlist", output)

    def test_runner_candidates_handoff_keeps_activation_disabled(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            with patch("proto_mind.runner_candidates.RunnerCandidateSet.read_state", return_value=_runner_candidates_state()):
                output = format_runner_candidates_command("/runner-candidates handoff", project_root=project_root, memory_store=store)

            self.assertIn("Proto-Mind Runner Candidate Set Handoff", output)
            self.assertIn("Registry: 387 commands across 41 categories", output)
            self.assertIn("Candidate set: total=13, registry_verified=13", output)
            self.assertIn("active_allowlist: none/inactive", output)
            self.assertIn("execution_enabled=false", output)
            self.assertEqual(output.count("FUTURE_CANDIDATE | NOT_ACTIVE | NOT_EXECUTABLE_BY_RUNNER_YET"), 13)
            self.assertIn("/runner-mvp design", output)

    def test_runner_candidates_doctor_checks_registry_context_and_no_activation(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            with patch("proto_mind.runner_candidates.RunnerCandidateSet.read_state", return_value=_runner_candidates_state()):
                output = format_runner_candidates_command("/runner-candidates doctor", project_root=project_root, memory_store=store)

            self.assertIn("Runner Candidate Set Doctor", output)
            self.assertIn("Status: OK", output)
            self.assertIn("All runner-candidate commands are registered", output)
            self.assertIn("All 13 candidates are Registry-known", output)
            self.assertIn("Context Injection is disabled", output)
            self.assertIn("No active allowlist, execution callback, subprocess/shell/eval/exec path", output)

    def test_runner_candidates_doctor_warns_without_changing_enabled_context(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            format_context_command("/context injection enable", project_root=project_root)
            settings_path = project_root / "proto_mind" / "data" / "context_injection.json"
            before = settings_path.read_bytes()
            with patch(
                "proto_mind.runner_candidates.RunnerCandidateSet.read_state",
                return_value=_runner_candidates_state(context_state="enabled"),
            ):
                output = format_runner_candidates_command("/runner-candidates doctor", project_root=project_root, memory_store=store)

            self.assertIn("Status: WARN", output)
            self.assertIn("Context Injection is explicitly enabled", output)
            self.assertEqual(settings_path.read_bytes(), before)
            self.assertTrue(json.loads(settings_path.read_text(encoding="utf-8"))["enabled"])

    def test_runner_candidates_commands_route_separately_and_are_read_only(self) -> None:
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
                    "/runner-candidates status",
                    "/runner-candidates list",
                    "/runner-candidates explain",
                    "/runner-candidates denied",
                    "/runner-candidates gates",
                    "/runner-candidates doctor",
                    "/runner-candidates handoff",
                )
            ]

            self.assertIn("Runner Candidate Set Status", outputs[0])
            self.assertIn("Future Read-Only Runner Candidate Set", outputs[1])
            self.assertIn("Runner Candidate Explanations", outputs[2])
            self.assertIn("Runner Candidate Set Exclusions", outputs[3])
            self.assertIn("Future Candidate Activation Gates", outputs[4])
            self.assertIn("Runner Candidate Set Doctor", outputs[5])
            self.assertIn("Proto-Mind Runner Candidate Set Handoff", outputs[6])
            for output in outputs:
                self.assertNotIn("execution_enabled=true", output)
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

    def test_runner_mvp_status_reports_locked_design_and_disabled_execution(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            with patch("proto_mind.runner_mvp.RunnerMVPDesignLock.read_state", return_value=_runner_mvp_state()):
                output = format_runner_mvp_command("/runner-mvp status", project_root=project_root, memory_store=store)

            self.assertIn("Read-only Runner MVP Design Lock Status", output)
            self.assertIn("Status: WARN", output)
            self.assertIn("command_registry: commands=387 categories=41", output)
            self.assertIn("context_injection: disabled", output)
            self.assertIn("activation_readiness: WARN", output)
            self.assertIn("accepted_known_warnings: 12", output)
            self.assertIn("unknown_warnings: 0", output)
            self.assertIn("blockers: 0", output)
            self.assertIn("design_lock_status: LOCKED_DESIGN_ONLY", output)
            self.assertIn("mvp_allowlist_candidates: 5/5 verified=5", output)
            self.assertIn("active_allowlist: none/inactive", output)
            self.assertIn("execution_enabled=false", output)
            self.assertIn("mvp_design_lock_safe: true", output)

    def test_runner_mvp_status_blocks_unknown_or_blockers(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            with patch(
                "proto_mind.runner_mvp.RunnerMVPDesignLock.read_state",
                return_value=_runner_mvp_state(unknown=True, blockers=1),
            ):
                output = format_runner_mvp_command("/runner-mvp status", project_root=project_root, memory_store=store)

            self.assertIn("Status: BLOCKED", output)
            self.assertIn("unknown_warnings: 1", output)
            self.assertIn("blockers: 1", output)
            self.assertIn("mvp_design_lock_safe: false", output)
            self.assertIn("execution_enabled=false", output)

    def test_runner_mvp_design_locks_scope_transport_flow_and_refusals(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")

            output = format_runner_mvp_command("/runner-mvp design", project_root=project_root, memory_store=store)

            self.assertIn("Locked Read-only Runner MVP Design", output)
            self.assertIn("Read-only commands only", output)
            self.assertIn("internal Proto-Mind command router/handler only", output)
            self.assertIn("No subprocess, shell, pipeline, eval, exec", output)
            self.assertIn("No command outside a separately approved active allowlist", output)
            self.assertIn("exact command-specific human confirmation", output)
            self.assertIn("Capture evidence", output)
            self.assertIn("post-run operator Acceptance Review", output)
            self.assertIn("no transport, allowlist, confirmation capture, evidence collector, or executor is implemented", output)

    def test_runner_mvp_allowlist_has_five_verified_inactive_candidates(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")

            output = format_runner_mvp_command("/runner-mvp allowlist", project_root=project_root, memory_store=store)

            self.assertIn("Locked Proposed MVP Allowlist Candidates", output)
            self.assertEqual(output.count("MVP_ALLOWLIST_CANDIDATE | NOT_ACTIVE | NOT_EXECUTABLE_YET"), 5)
            self.assertEqual(output.count("REGISTRY_VERIFIED"), 5)
            for command, *_ in MVP_ALLOWLIST_CANDIDATES:
                self.assertIn(command, output)
            self.assertIn("active_allowlist: none/inactive", output)
            self.assertIn("execution_enabled=false", output)
            self.assertIn("Proposed candidates are not active", output)

    def test_runner_mvp_confirmation_locks_exact_one_run_rules_without_capture(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")

            output = format_runner_mvp_command("/runner-mvp confirmation", project_root=project_root, memory_store=store)

            self.assertIn("Locked MVP Confirmation Rules", output)
            self.assertIn("CONFIRM RUN READONLY: <exact command>", output)
            self.assertIn("match the exact command byte-for-byte", output)
            self.assertIn("expires immediately after one attempted run", output)
            self.assertIn("cannot be reused, cached, inherited, or inferred", output)
            self.assertIn("High-risk, operator-only, unknown, mutating", output)
            self.assertIn("No confirmation is parsed, captured, matched, stored, or consumed", output)

    def test_runner_mvp_evidence_is_design_only_and_complete(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")

            output = format_runner_mvp_command("/runner-mvp evidence", project_root=project_root, memory_store=store)

            self.assertIn("Locked MVP Execution Evidence Model", output)
            for field in ("command_requested", "command_executed", "execution_enabled", "confirmation_matched", "gates_checked", "stdout_stderr_summary", "status_code", "files_changed_summary", "data_exports_sha256_summary", "context_injection_status", "warnings_unknown_count", "post_run_acceptance_recommendation", "refusal_reason"):
                self.assertIn(f"{field}: NOT_AVAILABLE_DESIGN_ONLY", output)
            self.assertIn("evidence is explicitly unavailable rather than simulated as real", output)

    def test_runner_mvp_stop_conditions_fail_closed(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")

            output = format_runner_mvp_command("/runner-mvp stop-conditions", project_root=project_root, memory_store=store)

            self.assertIn("Locked MVP Stop / Refusal Conditions", output)
            for condition in ("unknown warnings > 0", "blockers > 0", "Context Injection unexpectedly enabled", "not present in the separately approved active allowlist", "not Registry-known", "not read-only", "mutation risk", "confirmation phrase mismatch", "dry-run plan not shown", "evidence capture unavailable", "shell/subprocess/eval/exec", "network or hidden background work", "unexpected exception"):
                self.assertIn(condition, output)
            self.assertIn("fails closed", output)

    def test_runner_mvp_handoff_contains_locked_scope_and_no_authority(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            with patch("proto_mind.runner_mvp.RunnerMVPDesignLock.read_state", return_value=_runner_mvp_state()):
                output = format_runner_mvp_command("/runner-mvp handoff", project_root=project_root, memory_store=store)

            self.assertIn("Proto-Mind Read-only Runner MVP Design Lock Handoff", output)
            self.assertIn("Registry: 387 commands across 41 categories", output)
            self.assertIn("MVP scope: 5 read-only candidates; verified=5", output)
            self.assertEqual(output.count("MVP_ALLOWLIST_CANDIDATE | NOT_ACTIVE | NOT_EXECUTABLE_YET"), 5)
            self.assertIn("CONFIRM RUN READONLY: <exact command>", output)
            self.assertIn("NOT_AVAILABLE_DESIGN_ONLY", output)
            self.assertIn("active_allowlist: none/inactive", output)
            self.assertIn("execution_enabled=false", output)
            self.assertIn("grants no activation or execution authority", output)

    def test_runner_mvp_doctor_checks_design_and_enabled_context_without_mutation(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            with patch("proto_mind.runner_mvp.RunnerMVPDesignLock.read_state", return_value=_runner_mvp_state()):
                healthy = format_runner_mvp_command("/runner-mvp doctor", project_root=project_root, memory_store=store)
            self.assertIn("Read-only Runner MVP Design Lock Doctor", healthy)
            self.assertIn("Status: OK", healthy)
            self.assertIn("All 5 MVP candidates are Registry-known", healthy)
            self.assertIn("MVP allowlist remains proposed/inactive", healthy)
            self.assertIn("Execution remains disabled", healthy)

            format_context_command("/context injection enable", project_root=project_root)
            settings_path = project_root / "proto_mind" / "data" / "context_injection.json"
            before = settings_path.read_bytes()
            with patch(
                "proto_mind.runner_mvp.RunnerMVPDesignLock.read_state",
                return_value=_runner_mvp_state(context_state="enabled"),
            ):
                enabled = format_runner_mvp_command("/runner-mvp doctor", project_root=project_root, memory_store=store)
            self.assertIn("Status: WARN", enabled)
            self.assertIn("Context Injection is explicitly enabled", enabled)
            self.assertEqual(settings_path.read_bytes(), before)

    def test_runner_mvp_commands_are_read_only_through_shared_handler(self) -> None:
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
                    "/runner-mvp status",
                    "/runner-mvp design",
                    "/runner-mvp allowlist",
                    "/runner-mvp confirmation",
                    "/runner-mvp evidence",
                    "/runner-mvp stop-conditions",
                    "/runner-mvp doctor",
                    "/runner-mvp handoff",
                )
            ]

            self.assertIn("Read-only Runner MVP Design Lock Status", outputs[0])
            self.assertIn("Locked Read-only Runner MVP Design", outputs[1])
            self.assertIn("Locked Proposed MVP Allowlist Candidates", outputs[2])
            self.assertIn("Locked MVP Confirmation Rules", outputs[3])
            self.assertIn("Locked MVP Execution Evidence Model", outputs[4])
            self.assertIn("Locked MVP Stop / Refusal Conditions", outputs[5])
            self.assertIn("Read-only Runner MVP Design Lock Doctor", outputs[6])
            self.assertIn("Proto-Mind Read-only Runner MVP Design Lock Handoff", outputs[7])
            for output in outputs:
                self.assertNotIn("execution_enabled=true", output)
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

    def test_runner_exec_status_starts_without_evidence(self) -> None:
        reset_runner_exec_evidence()
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            with patch("proto_mind.runner_exec.ReadOnlyRunnerPilot.read_state", return_value=_runner_exec_state()):
                output = format_runner_exec_command("/runner-exec status", project_root=project_root, memory_store=store)

            self.assertIn("Real Read-only Runner MVP Status", output)
            self.assertIn("command_registry: commands=387 categories=41", output)
            self.assertIn("active_allowlist_count: 4", output)
            self.assertIn("active_allowlisted_commands: /warnings unknown, /daily doctor, /exports doctor, /capabilities safety", output)
            self.assertIn("execution_enabled: true", output)
            self.assertIn("confirmation_required: true", output)
            self.assertIn(EXACT_CONFIRMATION, output)
            self.assertIn("last_evidence: NONE", output)

    def test_runner_exec_allowlist_contains_exactly_four_read_only_targets(self) -> None:
        reset_runner_exec_evidence()
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            with patch("proto_mind.runner_exec.ReadOnlyRunnerPilot.read_state", return_value=_runner_exec_state()):
                output = format_runner_exec_command("/runner-exec allowlist", project_root=project_root, memory_store=store)

            self.assertEqual(
                ACTIVE_READONLY_ALLOWLIST,
                ("/warnings unknown", "/daily doctor", "/exports doctor", "/capabilities safety"),
            )
            self.assertEqual(output.count("ACTIVE_READONLY_ALLOWLIST"), 4)
            self.assertIn("/warnings unknown", output)
            self.assertIn("/daily doctor", output)
            self.assertIn("/exports doctor", output)
            self.assertIn("/capabilities safety", output)
            self.assertIn(EXACT_CONFIRMATION, output)
            self.assertIn(DAILY_DOCTOR_CONFIRMATION, output)
            self.assertIn(EXPORTS_DOCTOR_CONFIRMATION, output)
            self.assertIn(CAPABILITIES_SAFETY_CONFIRMATION, output)
            self.assertIn("expected_writes: none", output)
            self.assertIn("exactly four commands", output)

    def test_runner_exec_dry_run_does_not_execute_or_create_evidence(self) -> None:
        reset_runner_exec_evidence()
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            with patch("proto_mind.runner_exec.ReadOnlyRunnerPilot.read_state", return_value=_runner_exec_state()):
                dry_run = format_runner_exec_command("/runner-exec dry-run", project_root=project_root, memory_store=store)
                evidence = format_runner_exec_command("/runner-exec evidence", project_root=project_root, memory_store=store)

            self.assertIn("Read-only Runner MVP Dry Run", dry_run)
            self.assertIn("command_candidate: /warnings unknown", dry_run)
            self.assertIn(EXACT_CONFIRMATION, dry_run)
            self.assertIn("target command was not executed", dry_run)
            self.assertIn("NOT_AVAILABLE_NO_RUN", evidence)

    def test_runner_exec_daily_doctor_dry_run_is_allowlisted_and_nonexecuting(self) -> None:
        reset_runner_exec_evidence()
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            with patch("proto_mind.runner_exec.ReadOnlyRunnerPilot.read_state", return_value=_runner_exec_state()):
                dry_run = format_runner_exec_command(
                    "/runner-exec dry-run /daily doctor",
                    project_root=project_root,
                    memory_store=store,
                )
                evidence = format_runner_exec_command("/runner-exec evidence", project_root=project_root, memory_store=store)

            self.assertIn("command_candidate: /daily doctor", dry_run)
            self.assertIn("active_allowlist_match: true", dry_run)
            self.assertIn(DAILY_DOCTOR_CONFIRMATION, dry_run)
            self.assertIn("target command was not executed", dry_run)
            self.assertIn("NOT_AVAILABLE_NO_RUN", evidence)

    def test_runner_exec_exports_doctor_dry_run_is_allowlisted_and_nonexecuting(self) -> None:
        reset_runner_exec_evidence()
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            with patch("proto_mind.runner_exec.ReadOnlyRunnerPilot.read_state", return_value=_runner_exec_state()):
                dry_run = format_runner_exec_command(
                    "/runner-exec dry-run /exports doctor",
                    project_root=project_root,
                    memory_store=store,
                )
                evidence = format_runner_exec_command("/runner-exec evidence", project_root=project_root, memory_store=store)

            self.assertIn("command_candidate: /exports doctor", dry_run)
            self.assertIn("active_allowlist_match: true", dry_run)
            self.assertIn(EXPORTS_DOCTOR_CONFIRMATION, dry_run)
            self.assertIn("target command was not executed", dry_run)
            self.assertIn("NOT_AVAILABLE_NO_RUN", evidence)

    def test_runner_exec_capabilities_safety_dry_run_is_allowlisted_and_nonexecuting(self) -> None:
        reset_runner_exec_evidence()
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            with patch("proto_mind.runner_exec.ReadOnlyRunnerPilot.read_state", return_value=_runner_exec_state()):
                dry_run = format_runner_exec_command(
                    "/runner-exec dry-run /capabilities safety",
                    project_root=project_root,
                    memory_store=store,
                )
                evidence = format_runner_exec_command("/runner-exec evidence", project_root=project_root, memory_store=store)

            self.assertIn("command_candidate: /capabilities safety", dry_run)
            self.assertIn("active_allowlist_match: true", dry_run)
            self.assertIn(CAPABILITIES_SAFETY_CONFIRMATION, dry_run)
            self.assertIn("target command was not executed", dry_run)
            self.assertIn("NOT_AVAILABLE_NO_RUN", evidence)

    def test_runner_exec_unknown_dry_run_target_is_blocked_without_evidence(self) -> None:
        reset_runner_exec_evidence()
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            with patch("proto_mind.runner_exec.ReadOnlyRunnerPilot.read_state", return_value=_runner_exec_state()):
                dry_run = format_runner_exec_command(
                    "/runner-exec dry-run /confirm policy",
                    project_root=project_root,
                    memory_store=store,
                )
                evidence = format_runner_exec_command("/runner-exec evidence", project_root=project_root, memory_store=store)

            self.assertIn("active_allowlist_match: false", dry_run)
            self.assertIn("COMMAND_NOT_ALLOWLISTED", dry_run)
            self.assertIn("NOT_AVAILABLE_NO_RUN", evidence)

    def test_runner_exec_missing_confirmation_refuses_and_records_memory_evidence(self) -> None:
        reset_runner_exec_evidence()
        called = 0

        def executor() -> str:
            nonlocal called
            called += 1
            return "must not run"

        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            with patch("proto_mind.runner_exec.ReadOnlyRunnerPilot.read_state", return_value=_runner_exec_state()):
                result = format_runner_exec_command("/runner-exec run", project_root=project_root, memory_store=store, executors=_runner_exec_executors(warnings=executor))
                evidence = format_runner_exec_command("/runner-exec evidence", project_root=project_root, memory_store=store)

            self.assertEqual(called, 0)
            self.assertIn("executed: false", result)
            self.assertIn("refusal_reason: CONFIRMATION_REQUIRED", result)
            self.assertIn("status: REFUSED", evidence)
            self.assertIn("storage: in-memory only", evidence)

    def test_runner_exec_mismatched_confirmation_refuses(self) -> None:
        reset_runner_exec_evidence()
        called = 0

        def executor() -> str:
            nonlocal called
            called += 1
            return "must not run"

        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            command = "/runner-exec run CONFIRM READONLY: /warnings unknown"
            with patch("proto_mind.runner_exec.ReadOnlyRunnerPilot.read_state", return_value=_runner_exec_state()):
                result = format_runner_exec_command(command, project_root=project_root, memory_store=store, executors=_runner_exec_executors(warnings=executor))

            self.assertEqual(called, 0)
            self.assertIn("confirmation_matched: false", result)
            self.assertIn("refusal_reason: CONFIRMATION_MISMATCH", result)

    def test_runner_exec_exact_confirmation_executes_fixed_target_once(self) -> None:
        reset_runner_exec_evidence()
        called = 0

        def executor() -> str:
            nonlocal called
            called += 1
            return "Unknown / Unaccepted Warning Findings\nStatus: OK\nunknown_findings: 0"

        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            command = f"/runner-exec run {EXACT_CONFIRMATION}"
            with patch("proto_mind.runner_exec.ReadOnlyRunnerPilot.read_state", return_value=_runner_exec_state()):
                result = format_runner_exec_command(command, project_root=project_root, memory_store=store, executors=_runner_exec_executors(warnings=executor))

            self.assertEqual(called, 1)
            self.assertIn("command_requested: /warnings unknown", result)
            self.assertIn("executed: true", result)
            self.assertIn("confirmation_matched: true", result)
            self.assertIn("status: COMPLETED", result)
            self.assertIn("result: SUCCESS", result)
            self.assertIn("Unknown / Unaccepted Warning Findings", result)

    def test_runner_exec_daily_doctor_exact_confirmation_executes_only_daily_callback(self) -> None:
        reset_runner_exec_evidence()
        warnings_called = 0
        daily_called = 0

        def warnings_executor() -> str:
            nonlocal warnings_called
            warnings_called += 1
            return "must not run"

        def daily_executor() -> str:
            nonlocal daily_called
            daily_called += 1
            return "Daily Agent Doctor\nStatus: OK"

        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            command = f"/runner-exec run {DAILY_DOCTOR_CONFIRMATION}"
            with patch("proto_mind.runner_exec.ReadOnlyRunnerPilot.read_state", return_value=_runner_exec_state()):
                result = format_runner_exec_command(
                    command,
                    project_root=project_root,
                    memory_store=store,
                    executors=_runner_exec_executors(warnings=warnings_executor, daily=daily_executor),
                )
                evidence = format_runner_exec_command("/runner-exec evidence", project_root=project_root, memory_store=store)

            self.assertEqual(warnings_called, 0)
            self.assertEqual(daily_called, 1)
            self.assertIn("command_requested: /daily doctor", result)
            self.assertIn("Daily Agent Doctor", result)
            self.assertIn("command_executed: /daily doctor", evidence)
            self.assertIn("result: SUCCESS", evidence)

    def test_runner_exec_exports_doctor_exact_confirmation_executes_only_exports_callback(self) -> None:
        reset_runner_exec_evidence()
        warnings_called = 0
        daily_called = 0
        exports_called = 0

        def warnings_executor() -> str:
            nonlocal warnings_called
            warnings_called += 1
            return "must not run"

        def daily_executor() -> str:
            nonlocal daily_called
            daily_called += 1
            return "must not run"

        def exports_executor() -> str:
            nonlocal exports_called
            exports_called += 1
            return "Export Retention Doctor\nStatus: OK"

        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            command = f"/runner-exec run {EXPORTS_DOCTOR_CONFIRMATION}"
            with patch("proto_mind.runner_exec.ReadOnlyRunnerPilot.read_state", return_value=_runner_exec_state()):
                result = format_runner_exec_command(
                    command,
                    project_root=project_root,
                    memory_store=store,
                    executors=_runner_exec_executors(
                        warnings=warnings_executor,
                        daily=daily_executor,
                        exports=exports_executor,
                    ),
                )
                evidence = format_runner_exec_command("/runner-exec evidence", project_root=project_root, memory_store=store)
                evidence_check = format_runner_exec_command("/runner-exec evidence-check", project_root=project_root, memory_store=store)

            self.assertEqual(warnings_called, 0)
            self.assertEqual(daily_called, 0)
            self.assertEqual(exports_called, 1)
            self.assertIn("command_requested: /exports doctor", result)
            self.assertIn("Export Retention Doctor", result)
            self.assertIn("command_executed: /exports doctor", evidence)
            self.assertIn("export_doctor_status: OK", evidence)
            self.assertIn("Status: OK", evidence_check)

    def test_runner_exec_capabilities_safety_exact_confirmation_executes_only_capability_callback(self) -> None:
        reset_runner_exec_evidence()
        other_called = 0
        capabilities_called = 0

        def other_executor() -> str:
            nonlocal other_called
            other_called += 1
            return "must not run"

        def capabilities_executor() -> str:
            nonlocal capabilities_called
            capabilities_called += 1
            return "\n".join(
                [
                    "Command Capability Safety Classification",
                    "- registered read-only/mutates=none commands: 271",
                    "- auto_allowed: 270",
                    "- confirmation_required: 86",
                    "- operator_only: 4",
                ]
            )

        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            with patch("proto_mind.runner_exec.ReadOnlyRunnerPilot.read_state", return_value=_runner_exec_state()):
                result = format_runner_exec_command(
                    f"/runner-exec run {CAPABILITIES_SAFETY_CONFIRMATION}",
                    project_root=project_root,
                    memory_store=store,
                    executors=_runner_exec_executors(
                        warnings=other_executor,
                        daily=other_executor,
                        exports=other_executor,
                        capabilities=capabilities_executor,
                    ),
                )
                evidence = format_runner_exec_command("/runner-exec evidence", project_root=project_root, memory_store=store)
                evidence_check = format_runner_exec_command("/runner-exec evidence-check", project_root=project_root, memory_store=store)

            self.assertEqual(other_called, 0)
            self.assertEqual(capabilities_called, 1)
            self.assertIn("command_requested: /capabilities safety", result)
            self.assertIn("Command Capability Safety Classification", result)
            self.assertIn("command_executed: /capabilities safety", evidence)
            self.assertIn("capabilities_safety_summary: registered read-only/mutates=none commands: 271", evidence)
            self.assertIn("auto_allowed: 270", evidence)
            self.assertIn("Status: OK", evidence_check)

    def test_runner_exec_cross_allowlist_confirmation_mismatch_refuses(self) -> None:
        reset_runner_exec_evidence()
        called = 0

        def executor() -> str:
            nonlocal called
            called += 1
            return "must not run"

        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            runner = ReadOnlyRunnerPilot(project_root=project_root, memory_store=store)
            with patch("proto_mind.runner_exec.ReadOnlyRunnerPilot.read_state", return_value=_runner_exec_state()):
                result = runner.run(
                    candidate=PILOT_COMMAND,
                    confirmation=DAILY_DOCTOR_CONFIRMATION,
                    executors=_runner_exec_executors(warnings=executor, daily=executor),
                )

            self.assertEqual(called, 0)
            self.assertIn("executed: false", result)
            self.assertIn("CONFIRMATION_COMMAND_MISMATCH", result)

    def test_runner_exec_command_outside_allowlist_refuses_without_callback(self) -> None:
        reset_runner_exec_evidence()
        called = 0

        def executor() -> str:
            nonlocal called
            called += 1
            return "must not run"

        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            with patch("proto_mind.runner_exec.ReadOnlyRunnerPilot.read_state", return_value=_runner_exec_state()):
                result = format_runner_exec_command(
                    "/runner-exec run CONFIRM RUN READONLY: /confirm policy",
                    project_root=project_root,
                    memory_store=store,
                    executors=_runner_exec_executors(warnings=executor, daily=executor),
                )

            self.assertEqual(called, 0)
            self.assertIn("command_requested: /confirm policy", result)
            self.assertIn("refusal_reason: COMMAND_NOT_ALLOWLISTED", result)
            self.assertIn("executed: false", result)

    def test_runner_exec_confirmed_run_evidence_proves_sha_unchanged(self) -> None:
        reset_runner_exec_evidence()
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            store.save_persistent_memory([])
            _create_healthy_export_dirs(project_root)
            with patch("proto_mind.runner_exec.ReadOnlyRunnerPilot.read_state", return_value=_runner_exec_state()):
                format_runner_exec_command(
                    f"/runner-exec run {EXACT_CONFIRMATION}",
                    project_root=project_root,
                    memory_store=store,
                    executors=_runner_exec_executors(warnings=lambda: "safe output"),
                )
                evidence = format_runner_exec_command("/runner-exec evidence", project_root=project_root, memory_store=store)

            self.assertIn("command_executed: /warnings unknown", evidence)
            self.assertIn("executed: true", evidence)
            self.assertIn("files_changed_summary: none", evidence)
            self.assertIn("unchanged=true", evidence)
            self.assertIn("refusal_reason: none", evidence)

    def test_runner_exec_evidence_without_run_is_not_available(self) -> None:
        reset_runner_exec_evidence()
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            output = format_runner_exec_command("/runner-exec evidence", project_root=project_root, memory_store=store)

            self.assertIn("status: NOT_AVAILABLE_NO_RUN", output)
            self.assertIn("in-memory only", output)
            self.assertIn("No persistent evidence, log, approval, or runner state exists", output)

    def test_runner_exec_enabled_context_closes_gate(self) -> None:
        reset_runner_exec_evidence()
        called = 0

        def executor() -> str:
            nonlocal called
            called += 1
            return "must not run"

        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            with patch(
                "proto_mind.runner_exec.ReadOnlyRunnerPilot.read_state",
                return_value=_runner_exec_state(context_state="enabled"),
            ):
                result = format_runner_exec_command(
                    f"/runner-exec run {EXACT_CONFIRMATION}",
                    project_root=project_root,
                    memory_store=store,
                    executors=_runner_exec_executors(warnings=executor),
                )

            self.assertEqual(called, 0)
            self.assertIn("context_injection_disabled", result)
            self.assertIn("executed: false", result)
            self.assertIn("GATE_FAILURE", result)

    def test_runner_exec_blocker_gate_refuses(self) -> None:
        reset_runner_exec_evidence()
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            with patch(
                "proto_mind.runner_exec.ReadOnlyRunnerPilot.read_state",
                return_value=_runner_exec_state(blockers=1),
            ):
                result = format_runner_exec_command(
                    f"/runner-exec run {EXACT_CONFIRMATION}",
                    project_root=project_root,
                    memory_store=store,
                    executors=_runner_exec_executors(warnings=lambda: "must not run"),
                )

            self.assertIn("blockers_zero", result)
            self.assertIn("executed: false", result)
            self.assertIn("GATE_FAILURE", result)

    def test_runner_exec_executor_exception_fails_closed(self) -> None:
        reset_runner_exec_evidence()

        def executor() -> str:
            raise RuntimeError("pilot failure")

        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            with patch("proto_mind.runner_exec.ReadOnlyRunnerPilot.read_state", return_value=_runner_exec_state()):
                result = format_runner_exec_command(
                    f"/runner-exec run {EXACT_CONFIRMATION}",
                    project_root=project_root,
                    memory_store=store,
                    executors=_runner_exec_executors(warnings=executor),
                )

            self.assertIn("executed: false", result)
            self.assertIn("result: EXECUTOR_ERROR", result)
            self.assertIn("EXECUTOR_EXCEPTION: RuntimeError: pilot failure", result)

    def test_runner_exec_free_form_or_second_command_never_dispatches(self) -> None:
        reset_runner_exec_evidence()
        called = 0

        def executor() -> str:
            nonlocal called
            called += 1
            return "must not run"

        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            attack = "/runner-exec run CONFIRM RUN READONLY: /warnings unknown; /daily doctor"
            with patch("proto_mind.runner_exec.ReadOnlyRunnerPilot.read_state", return_value=_runner_exec_state()):
                result = format_runner_exec_command(attack, project_root=project_root, memory_store=store, executors=_runner_exec_executors(warnings=executor))

            self.assertEqual(called, 0)
            self.assertIn("CONFIRMATION_MISMATCH", result)
            self.assertIn("executed: false", result)

    def test_runner_exec_doctor_validates_exact_scope(self) -> None:
        reset_runner_exec_evidence()
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            with patch("proto_mind.runner_exec.ReadOnlyRunnerPilot.read_state", return_value=_runner_exec_state()):
                output = format_runner_exec_command("/runner-exec doctor", project_root=project_root, memory_store=store)

            self.assertIn("Real Read-only Runner MVP Doctor", output)
            self.assertIn("Status: OK", output)
            self.assertIn("Active allowlist contains exactly four commands: /warnings unknown, /daily doctor, /exports doctor, and /capabilities safety", output)
            self.assertIn("Exact command-specific confirmation phrases are configured", output)
            self.assertIn("callback lookup uses a fixed map", output)
            self.assertIn("No shell/subprocess/eval/exec", output)
            self.assertIn("Four-command soak/drift summary", output)

    def test_runner_exec_doctor_blocks_enabled_context(self) -> None:
        reset_runner_exec_evidence()
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            with patch(
                "proto_mind.runner_exec.ReadOnlyRunnerPilot.read_state",
                return_value=_runner_exec_state(context_state="enabled"),
            ):
                output = format_runner_exec_command("/runner-exec doctor", project_root=project_root, memory_store=store)

            self.assertIn("Status: BLOCKED", output)
            self.assertIn("Context Injection is enabled; execution gate is closed", output)

    def test_runner_exec_refusal_matrix_is_static_and_does_not_create_evidence(self) -> None:
        reset_runner_exec_evidence()
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            matrix = format_runner_exec_command("/runner-exec refusal-matrix", project_root=project_root, memory_store=store)
            evidence = format_runner_exec_command("/runner-exec evidence", project_root=project_root, memory_store=store)

            self.assertIn("Read-only Runner MVP Refusal Matrix", matrix)
            self.assertEqual(matrix.count("expected_result: REFUSED"), 8)
            self.assertIn("case_id: missing_confirmation", matrix)
            self.assertIn("case_id: near_miss_command", matrix)
            self.assertIn("case_id: suffix_attempt", matrix)
            self.assertIn("case_id: unsafe_or_unknown_target", matrix)
            self.assertIn("cases_executed: false", matrix)
            self.assertIn("NOT_AVAILABLE_NO_RUN", evidence)

    def test_runner_exec_last_refusal_handles_no_refusal(self) -> None:
        reset_runner_exec_evidence()
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            output = format_runner_exec_command("/runner-exec last-refusal", project_root=project_root, memory_store=store)

            self.assertIn("NOT_AVAILABLE_NO_REFUSAL", output)
            self.assertIn("in-memory only", output)

    def test_runner_exec_last_refusal_records_missing_confirmation_without_files(self) -> None:
        reset_runner_exec_evidence()
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            with patch("proto_mind.runner_exec.ReadOnlyRunnerPilot.read_state", return_value=_runner_exec_state()):
                format_runner_exec_command("/runner-exec run", project_root=project_root, memory_store=store, executors=_runner_exec_executors(warnings=lambda: "must not run"))
                output = format_runner_exec_command("/runner-exec last-refusal", project_root=project_root, memory_store=store)

            self.assertIn("confirmation_received: MISSING", output)
            self.assertIn("executed: false", output)
            self.assertIn("refusal_reason: CONFIRMATION_REQUIRED", output)
            self.assertIn("created_at:", output)
            self.assertIn("files_written: none", output)

    def test_runner_exec_outside_target_refusal_redacts_confirmation(self) -> None:
        reset_runner_exec_evidence()
        called = 0

        def executor() -> str:
            nonlocal called
            called += 1
            return "must not run"

        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            with patch("proto_mind.runner_exec.ReadOnlyRunnerPilot.read_state", return_value=_runner_exec_state()):
                format_runner_exec_command(
                    "/runner-exec run CONFIRM RUN READONLY: /confirm policy",
                    project_root=project_root,
                    memory_store=store,
                    executors=_runner_exec_executors(warnings=executor),
                )
                output = format_runner_exec_command("/runner-exec last-refusal", project_root=project_root, memory_store=store)

            self.assertEqual(called, 0)
            self.assertIn("confirmation_received: MISMATCH(chars=", output)
            self.assertIn("sha256=", output)
            self.assertNotIn("CONFIRM RUN READONLY: /confirm policy", output)
            self.assertIn("COMMAND_NOT_ALLOWLISTED", output)

    def test_runner_exec_suffix_attempt_fails_closed(self) -> None:
        reset_runner_exec_evidence()
        called = 0

        def executor() -> str:
            nonlocal called
            called += 1
            return "must not run"

        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            attack = "/runner-exec run CONFIRM RUN READONLY: /warnings unknown; /daily doctor"
            with patch("proto_mind.runner_exec.ReadOnlyRunnerPilot.read_state", return_value=_runner_exec_state()):
                result = format_runner_exec_command(attack, project_root=project_root, memory_store=store, executors=_runner_exec_executors(warnings=executor))

            self.assertEqual(called, 0)
            self.assertIn("CONFIRMATION_MISMATCH: EXTRA_INPUT", result)
            self.assertIn("executed: false", result)

    def test_runner_exec_last_refusal_survives_later_success(self) -> None:
        reset_runner_exec_evidence()
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            with patch("proto_mind.runner_exec.ReadOnlyRunnerPilot.read_state", return_value=_runner_exec_state()):
                format_runner_exec_command("/runner-exec run", project_root=project_root, memory_store=store, executors=_runner_exec_executors(warnings=lambda: "must not run"))
                format_runner_exec_command(
                    f"/runner-exec run {EXACT_CONFIRMATION}",
                    project_root=project_root,
                    memory_store=store,
                    executors=_runner_exec_executors(warnings=lambda: "safe output"),
                )
                refusal = format_runner_exec_command("/runner-exec last-refusal", project_root=project_root, memory_store=store)
                evidence = format_runner_exec_command("/runner-exec evidence", project_root=project_root, memory_store=store)

            self.assertIn("refusal_reason: CONFIRMATION_REQUIRED", refusal)
            self.assertIn("evidence_view: LAST_SUCCESS_EVIDENCE", evidence)
            self.assertIn("executed: true", evidence)

    def test_runner_exec_evidence_check_warns_without_current_process_evidence(self) -> None:
        reset_runner_exec_evidence()
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            output = format_runner_exec_command("/runner-exec evidence-check", project_root=project_root, memory_store=store)

            self.assertIn("Read-only Runner MVP Evidence Check", output)
            self.assertIn("Status: WARN", output)
            self.assertIn("No current-process run or refusal evidence", output)

    def test_runner_exec_evidence_check_validates_refusal_and_success(self) -> None:
        reset_runner_exec_evidence()
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            with patch("proto_mind.runner_exec.ReadOnlyRunnerPilot.read_state", return_value=_runner_exec_state()):
                format_runner_exec_command("/runner-exec run", project_root=project_root, memory_store=store, executors=_runner_exec_executors(warnings=lambda: "must not run"))
                refusal_check = format_runner_exec_command("/runner-exec evidence-check", project_root=project_root, memory_store=store)
                format_runner_exec_command(
                    f"/runner-exec run {EXACT_CONFIRMATION}",
                    project_root=project_root,
                    memory_store=store,
                    executors=_runner_exec_executors(warnings=lambda: "safe output"),
                )
                combined_check = format_runner_exec_command("/runner-exec evidence-check", project_root=project_root, memory_store=store)

            self.assertIn("Status: OK", refusal_check)
            self.assertIn("Validated 1 distinct", refusal_check)
            self.assertIn("Status: OK", combined_check)
            self.assertIn("Validated 2 distinct", combined_check)
            self.assertIn("No command outside the exact four-command allowlist is marked executed", combined_check)

    def test_runner_exec_evidence_check_detects_unsafe_in_memory_shape(self) -> None:
        reset_runner_exec_evidence()
        malformed = {
            "request_id": "runner_exec_bad",
            "created_at": "2026-07-03T00:00:00+00:00",
            "evidence_kind": "success",
            "command_requested": "/warnings unknown",
            "command_executed": "/memory remember unsafe",
            "execution_enabled": True,
            "executed": True,
            "confirmation_received": "EXACT_MATCH",
            "confirmation_matched": True,
            "gates_checked": {},
            "gate_failures": [],
            "output_summary": "",
            "status": "COMPLETED",
            "result": "SUCCESS",
            "files_changed_summary": "none",
            "data_exports_sha256_before_after": "unchanged=true",
            "context_injection_status": "disabled",
            "unknown_warning_count_after": 0,
            "export_doctor_status": "not_applicable",
            "capabilities_safety_summary": "not_applicable",
            "refusal_reason": "",
            "persistent": True,
            "storage": "disk",
            "evidence_file_path": "/tmp/forbidden.json",
        }
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            with patch("proto_mind.runner_exec._LAST_EVIDENCE", malformed):
                output = format_runner_exec_command("/runner-exec evidence-check", project_root=project_root, memory_store=store)

            self.assertIn("Status: ERROR", output)
            self.assertIn("outside the active allowlist", output)
            self.assertIn("forbidden evidence file path", output)
            self.assertIn("persistent evidence state", output)

    def test_runner_exec_stability_reports_exact_scope_without_execution(self) -> None:
        reset_runner_exec_evidence()
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            with patch("proto_mind.runner_exec.ReadOnlyRunnerPilot.read_state", return_value=_runner_exec_state()):
                output = format_runner_exec_command(
                    "/runner-exec stability",
                    project_root=project_root,
                    memory_store=store,
                    executors=_runner_exec_executors(),
                )

            self.assertIn("Read-only Runner Multi-Command Stability Review", output)
            self.assertIn("Status: WARN", output)
            self.assertIn("active_allowlist_count: 4", output)
            self.assertIn("callback_map_status: EXACT", output)
            self.assertIn("active_fifth_command: none", output)
            self.assertIn("free_form_dispatch: false", output)

    def test_runner_exec_sequence_plan_is_print_only(self) -> None:
        reset_runner_exec_evidence()
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            plan = format_runner_exec_command("/runner-exec sequence-plan", project_root=project_root, memory_store=store)
            evidence = format_runner_exec_command("/runner-exec evidence", project_root=project_root, memory_store=store)

            self.assertIn("Read-only Runner Multi-Command Sequence Plan", plan)
            self.assertIn("sequence_executed=false", plan)
            self.assertIn(EXACT_CONFIRMATION, plan)
            self.assertIn(DAILY_DOCTOR_CONFIRMATION, plan)
            self.assertIn(EXPORTS_DOCTOR_CONFIRMATION, plan)
            self.assertIn(CAPABILITIES_SAFETY_CONFIRMATION, plan)
            self.assertIn("COMMAND_NOT_ALLOWLISTED", plan)
            self.assertIn("NOT_AVAILABLE_NO_RUN", evidence)

    def test_runner_exec_sequence_evidence_handles_no_run(self) -> None:
        reset_runner_exec_evidence()
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            output = format_runner_exec_command("/runner-exec sequence-evidence", project_root=project_root, memory_store=store)

            self.assertIn("NOT_AVAILABLE_NO_RUN", output)
            self.assertIn("in-memory only", output)

    def test_runner_exec_sequence_evidence_summarizes_three_commands_and_refusal(self) -> None:
        reset_runner_exec_evidence()
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            with patch("proto_mind.runner_exec.ReadOnlyRunnerPilot.read_state", return_value=_runner_exec_state()):
                for confirmation in (
                    EXACT_CONFIRMATION,
                    DAILY_DOCTOR_CONFIRMATION,
                    EXPORTS_DOCTOR_CONFIRMATION,
                    CAPABILITIES_SAFETY_CONFIRMATION,
                ):
                    format_runner_exec_command(
                        f"/runner-exec run {confirmation}",
                        project_root=project_root,
                        memory_store=store,
                        executors=_runner_exec_executors(),
                    )
                format_runner_exec_command(
                    "/runner-exec run CONFIRM RUN READONLY: /confirm policy",
                    project_root=project_root,
                    memory_store=store,
                    executors=_runner_exec_executors(),
                )
                output = format_runner_exec_command("/runner-exec sequence-evidence", project_root=project_root, memory_store=store)

            self.assertIn("status: AVAILABLE_IN_MEMORY", output)
            self.assertIn("- total: 5", output)
            self.assertIn("- kind:success: 4", output)
            self.assertIn("- kind:refusal: 1", output)
            self.assertIn("- /warnings unknown: request_id=", output)
            self.assertIn("- /daily doctor: request_id=", output)
            self.assertIn("- /exports doctor: request_id=", output)
            self.assertIn("- /capabilities safety: request_id=", output)
            self.assertIn("No full command history is stored", output)

    def test_runner_exec_consistency_check_warns_without_callback_map_or_evidence(self) -> None:
        reset_runner_exec_evidence()
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            with patch("proto_mind.runner_exec.ReadOnlyRunnerPilot.read_state", return_value=_runner_exec_state()):
                output = format_runner_exec_command("/runner-exec consistency-check", project_root=project_root, memory_store=store)

            self.assertIn("Status: WARN", output)
            self.assertIn("Callback map was not supplied", output)
            self.assertIn("No current-process evidence", output)

    def test_runner_exec_consistency_check_is_ok_after_stable_sequence(self) -> None:
        reset_runner_exec_evidence()
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            with patch("proto_mind.runner_exec.ReadOnlyRunnerPilot.read_state", return_value=_runner_exec_state()):
                format_runner_exec_command(
                    f"/runner-exec run {EXPORTS_DOCTOR_CONFIRMATION}",
                    project_root=project_root,
                    memory_store=store,
                    executors=_runner_exec_executors(),
                )
                output = format_runner_exec_command(
                    "/runner-exec consistency-check",
                    project_root=project_root,
                    memory_store=store,
                    executors=_runner_exec_executors(),
                )

            self.assertIn("Status: OK", output)
            self.assertIn("exactly four callable zero-argument targets", output)
            self.assertIn("Current evidence booleans", output)
            self.assertIn("Context Injection is disabled", output)

    def test_runner_exec_consistency_check_blocks_extra_callback_without_invoking_it(self) -> None:
        reset_runner_exec_evidence()
        called = 0

        def extra_callback() -> str:
            nonlocal called
            called += 1
            return "must not run"

        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            executors = _runner_exec_executors()
            executors["/confirm policy"] = extra_callback
            with patch("proto_mind.runner_exec.ReadOnlyRunnerPilot.read_state", return_value=_runner_exec_state()):
                output = format_runner_exec_command(
                    "/runner-exec consistency-check",
                    project_root=project_root,
                    memory_store=store,
                    executors=executors,
                )

            self.assertEqual(called, 0)
            self.assertIn("Status: BLOCKED", output)
            self.assertIn("missing, extra, or non-callable", output)

    def test_runner_exec_stability_commands_route_read_only_through_shared_handler(self) -> None:
        reset_runner_exec_evidence()
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
                process_interactive_input(command, coordinator=coordinator, session_logger=logger, project_root=project_root)
                for command in (
                    "/runner-exec stability",
                    "/runner-exec sequence-plan",
                    "/runner-exec sequence-evidence",
                    "/runner-exec consistency-check",
                )
            ]

            self.assertIn("callback_map_status: EXACT", outputs[0])
            self.assertIn("sequence_executed=false", outputs[1])
            self.assertIn("NOT_AVAILABLE_NO_RUN", outputs[2])
            self.assertIn("Status: WARN", outputs[3])
            self.assertIn("exactly four callable zero-argument targets", outputs[3])
            after_data = {path.name: path.read_bytes() for path in data_dir.glob("*") if path.is_file()}
            after_exports = {
                str(path.relative_to(exports_root)): path.read_bytes()
                for path in exports_root.rglob("*")
                if path.is_file()
            }
            self.assertEqual(after_data, before_data)
            self.assertEqual(after_exports, before_exports)
            self.assertEqual(logger.status().entry_count, 0)

    def test_runner_exec_soak_reports_exact_scope_without_execution(self) -> None:
        reset_runner_exec_evidence()
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            with patch("proto_mind.runner_exec.ReadOnlyRunnerPilot.read_state", return_value=_runner_exec_state()):
                output = format_runner_exec_command(
                    "/runner-exec soak",
                    project_root=project_root,
                    memory_store=store,
                    executors=_runner_exec_executors(),
                )

            self.assertIn("Read-only Runner Four-Command Safety Soak", output)
            self.assertIn("Status: WARN", output)
            self.assertIn("active_allowlist_count: 4", output)
            self.assertIn("callback_map_status: EXACT", output)
            self.assertIn("all_four_succeeded: false", output)
            self.assertIn("active_fifth_command: none", output)
            self.assertIn("context_injection: disabled", output)

    def test_runner_exec_soak_plan_is_print_only(self) -> None:
        reset_runner_exec_evidence()
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            plan = format_runner_exec_command("/runner-exec soak-plan", project_root=project_root, memory_store=store)
            evidence = format_runner_exec_command("/runner-exec evidence", project_root=project_root, memory_store=store)

            self.assertIn("Read-only Runner Four-Command Soak Plan", plan)
            self.assertIn("soak_executed=false", plan)
            self.assertIn(EXACT_CONFIRMATION, plan)
            self.assertIn(DAILY_DOCTOR_CONFIRMATION, plan)
            self.assertIn(EXPORTS_DOCTOR_CONFIRMATION, plan)
            self.assertIn(CAPABILITIES_SAFETY_CONFIRMATION, plan)
            self.assertIn("/confirm policy", plan)
            self.assertIn("CONFIRMATION_COMMAND_MISMATCH", plan)
            self.assertIn("NOT_AVAILABLE_NO_RUN", evidence)

    def test_runner_exec_soak_report_handles_no_run(self) -> None:
        reset_runner_exec_evidence()
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            output = format_runner_exec_command("/runner-exec soak-report", project_root=project_root, memory_store=store)

            self.assertIn("NOT_AVAILABLE_NO_RUN", output)
            self.assertIn("in-memory only", output)

    def test_runner_exec_soak_report_summarizes_full_sequence(self) -> None:
        reset_runner_exec_evidence()
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            with patch("proto_mind.runner_exec.ReadOnlyRunnerPilot.read_state", return_value=_runner_exec_state()):
                format_runner_exec_command(
                    "/runner-exec run",
                    project_root=project_root,
                    memory_store=store,
                    executors=_runner_exec_executors(),
                )
                for confirmation in (
                    EXACT_CONFIRMATION,
                    DAILY_DOCTOR_CONFIRMATION,
                    EXPORTS_DOCTOR_CONFIRMATION,
                    CAPABILITIES_SAFETY_CONFIRMATION,
                ):
                    format_runner_exec_command(
                        f"/runner-exec run {confirmation}",
                        project_root=project_root,
                        memory_store=store,
                        executors=_runner_exec_executors(),
                    )
                output = format_runner_exec_command("/runner-exec soak-report", project_root=project_root, memory_store=store)

            self.assertIn("status: AVAILABLE_IN_MEMORY", output)
            self.assertIn("success_count: 4", output)
            self.assertIn("refusal_count: 1", output)
            self.assertIn("all_four_succeeded: true", output)
            self.assertIn("outside_allowlist_executed: false", output)
            for command in ACTIVE_READONLY_ALLOWLIST:
                self.assertIn(f"- {command}: request_id=", output)

    def test_runner_exec_drift_check_is_ok_after_full_soak(self) -> None:
        reset_runner_exec_evidence()
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            with patch("proto_mind.runner_exec.ReadOnlyRunnerPilot.read_state", return_value=_runner_exec_state()):
                for confirmation in (
                    EXACT_CONFIRMATION,
                    DAILY_DOCTOR_CONFIRMATION,
                    EXPORTS_DOCTOR_CONFIRMATION,
                    CAPABILITIES_SAFETY_CONFIRMATION,
                ):
                    format_runner_exec_command(
                        f"/runner-exec run {confirmation}",
                        project_root=project_root,
                        memory_store=store,
                        executors=_runner_exec_executors(),
                    )
                output = format_runner_exec_command(
                    "/runner-exec drift-check",
                    project_root=project_root,
                    memory_store=store,
                    executors=_runner_exec_executors(),
                )

            self.assertIn("Status: OK", output)
            self.assertIn("/confirm policy remains outside", output)
            self.assertIn("No retained evidence marks an outside-allowlist command", output)
            self.assertIn("no data/export mutation indicator", output)

    def test_runner_exec_drift_check_warns_without_runtime_map_or_evidence(self) -> None:
        reset_runner_exec_evidence()
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            with patch("proto_mind.runner_exec.ReadOnlyRunnerPilot.read_state", return_value=_runner_exec_state()):
                output = format_runner_exec_command("/runner-exec drift-check", project_root=project_root, memory_store=store)

            self.assertIn("Status: WARN", output)
            self.assertIn("Callback map was not supplied", output)
            self.assertIn("No current-process evidence", output)

    def test_runner_exec_drift_check_blocks_confirm_policy_callback_without_invoking_it(self) -> None:
        reset_runner_exec_evidence()
        called = 0

        def forbidden_callback() -> str:
            nonlocal called
            called += 1
            return "must not run"

        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            executors = _runner_exec_executors()
            executors["/confirm policy"] = forbidden_callback
            with patch("proto_mind.runner_exec.ReadOnlyRunnerPilot.read_state", return_value=_runner_exec_state()):
                output = format_runner_exec_command(
                    "/runner-exec drift-check",
                    project_root=project_root,
                    memory_store=store,
                    executors=executors,
                )

            self.assertEqual(called, 0)
            self.assertIn("Status: BLOCKED", output)
            self.assertIn("/confirm policy drifted", output)

    def test_runner_exec_soak_commands_route_read_only_through_shared_handler(self) -> None:
        reset_runner_exec_evidence()
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
                process_interactive_input(command, coordinator=coordinator, session_logger=logger, project_root=project_root)
                for command in (
                    "/runner-exec soak",
                    "/runner-exec soak-plan",
                    "/runner-exec soak-report",
                    "/runner-exec drift-check",
                )
            ]

            self.assertIn("callback_map_status: EXACT", outputs[0])
            self.assertIn("soak_executed=false", outputs[1])
            self.assertIn("NOT_AVAILABLE_NO_RUN", outputs[2])
            self.assertIn("Status: WARN", outputs[3])
            self.assertIn("/confirm policy remains outside", outputs[3])
            after_data = {path.name: path.read_bytes() for path in data_dir.glob("*") if path.is_file()}
            after_exports = {
                str(path.relative_to(exports_root)): path.read_bytes()
                for path in exports_root.rglob("*")
                if path.is_file()
            }
            self.assertEqual(after_data, before_data)
            self.assertEqual(after_exports, before_exports)
            self.assertEqual(logger.status().entry_count, 0)

    def test_runner_exec_shared_handler_confirmed_pilot_is_read_only_and_in_memory(self) -> None:
        reset_runner_exec_evidence()
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
                process_interactive_input(command, coordinator=coordinator, session_logger=logger, project_root=project_root)
                for command in (
                    "/runner-exec status",
                    "/runner-exec allowlist",
                    "/runner-exec dry-run",
                    "/runner-exec dry-run /daily doctor",
                    "/runner-exec dry-run /exports doctor",
                    "/runner-exec dry-run /capabilities safety",
                    "/runner-exec refusal-matrix",
                    "/runner-exec run",
                    "/runner-exec last-refusal",
                    "/runner-exec evidence-check",
                    f"/runner-exec run {EXACT_CONFIRMATION}",
                    "/runner-exec evidence",
                    "/runner-exec evidence-check",
                    f"/runner-exec run {DAILY_DOCTOR_CONFIRMATION}",
                    "/runner-exec evidence",
                    "/runner-exec evidence-check",
                    f"/runner-exec run {EXPORTS_DOCTOR_CONFIRMATION}",
                    "/runner-exec evidence",
                    "/runner-exec evidence-check",
                    f"/runner-exec run {CAPABILITIES_SAFETY_CONFIRMATION}",
                    "/runner-exec evidence",
                    "/runner-exec evidence-check",
                    "/runner-exec doctor",
                    "/runner-exec handoff",
                )
            ]

            self.assertIn("last_evidence: NONE", outputs[0])
            self.assertIn("ACTIVE_READONLY_ALLOWLIST: /warnings unknown", outputs[1])
            self.assertIn("ACTIVE_READONLY_ALLOWLIST: /daily doctor", outputs[1])
            self.assertIn("ACTIVE_READONLY_ALLOWLIST: /exports doctor", outputs[1])
            self.assertIn("ACTIVE_READONLY_ALLOWLIST: /capabilities safety", outputs[1])
            self.assertIn("target command was not executed", outputs[2])
            self.assertIn("command_candidate: /daily doctor", outputs[3])
            self.assertIn("command_candidate: /exports doctor", outputs[4])
            self.assertIn("command_candidate: /capabilities safety", outputs[5])
            self.assertIn("cases_executed: false", outputs[6])
            self.assertIn("CONFIRMATION_REQUIRED", outputs[7])
            self.assertIn("confirmation_received: MISSING", outputs[8])
            self.assertIn("Status: OK", outputs[9])
            self.assertIn("executed: true", outputs[10])
            self.assertIn("Unknown / Unaccepted Warning Findings", outputs[10])
            self.assertIn("command_executed: /warnings unknown", outputs[11])
            self.assertIn("unchanged=true", outputs[11])
            self.assertIn("Validated 2 distinct", outputs[12])
            self.assertIn("command_requested: /daily doctor", outputs[13])
            self.assertIn("Daily Agent Doctor", outputs[13])
            self.assertIn("command_executed: /daily doctor", outputs[14])
            self.assertIn("unchanged=true", outputs[14])
            self.assertIn("Status: OK", outputs[15])
            self.assertIn("command_requested: /exports doctor", outputs[16])
            self.assertIn("Export Retention Doctor", outputs[16])
            self.assertIn("command_executed: /exports doctor", outputs[17])
            self.assertIn("export_doctor_status: OK", outputs[17])
            self.assertIn("Status: OK", outputs[18])
            self.assertIn("command_requested: /capabilities safety", outputs[19])
            self.assertIn("Command Capability Safety Classification", outputs[19])
            self.assertIn("command_executed: /capabilities safety", outputs[20])
            self.assertIn("capabilities_safety_summary:", outputs[20])
            self.assertIn("Status: OK", outputs[21])
            self.assertIn("Status: OK", outputs[22])
            self.assertIn(CAPABILITIES_SAFETY_CONFIRMATION, outputs[23])
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
            self.assertFalse(any(path.name.startswith("runner") for path in data_dir.glob("*") if path.is_file()))

    def test_runner_exec_history_handles_empty_process_state(self) -> None:
        reset_runner_exec_evidence()
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            history = format_runner_exec_command("/runner-exec history", project_root=project_root, memory_store=store)
            summary = format_runner_exec_command("/runner-exec history-summary", project_root=project_root, memory_store=store)

        self.assertIn("NOT_AVAILABLE_NO_HISTORY", history)
        self.assertIn("event_count: 0", history)
        self.assertIn(f"max_size: {EVIDENCE_HISTORY_MAX_SIZE}", history)
        self.assertIn("success_count: 0", summary)
        self.assertIn("refusal_count: 0", summary)
        self.assertIn("persistence_status: process-memory-only", summary)

    def test_runner_exec_history_records_compact_success_and_refusal_events(self) -> None:
        reset_runner_exec_evidence()
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            with patch("proto_mind.runner_exec.ReadOnlyRunnerPilot.read_state", return_value=_runner_exec_state()):
                format_runner_exec_command(
                    "/runner-exec run",
                    project_root=project_root,
                    memory_store=store,
                    executors=_runner_exec_executors(warnings=lambda: "must not run"),
                )
                format_runner_exec_command(
                    f"/runner-exec run {EXACT_CONFIRMATION}",
                    project_root=project_root,
                    memory_store=store,
                    executors=_runner_exec_executors(warnings=lambda: "FULL TARGET OUTPUT MUST NOT ENTER HISTORY"),
                )
                format_runner_exec_command(
                    "/runner-exec run CONFIRM RUN READONLY: super-secret-value",
                    project_root=project_root,
                    memory_store=store,
                    executors=_runner_exec_executors(),
                )
                history = format_runner_exec_command("/runner-exec history", project_root=project_root, memory_store=store)
                summary = format_runner_exec_command("/runner-exec history-summary", project_root=project_root, memory_store=store)

        self.assertIn("event_count: 3", history)
        self.assertIn("event_type: REFUSAL", history)
        self.assertIn("event_type: SUCCESS", history)
        self.assertIn("refusal_reason: CONFIRMATION_REQUIRED", history)
        self.assertIn("command_requested: OUTSIDE_ALLOWLIST(chars=", history)
        self.assertNotIn("super-secret-value", history)
        self.assertNotIn("FULL TARGET OUTPUT", history)
        self.assertNotIn("CONFIRM RUN READONLY", history)
        self.assertIn("success_count: 1", summary)
        self.assertIn("refusal_count: 2", summary)
        self.assertIn("outside_allowlist_executed_count: 0", summary)

    def test_runner_exec_history_ring_evicts_oldest_events_at_bound(self) -> None:
        reset_runner_exec_evidence()
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            with patch("proto_mind.runner_exec.ReadOnlyRunnerPilot.read_state", return_value=_runner_exec_state()):
                for _ in range(EVIDENCE_HISTORY_MAX_SIZE + 5):
                    format_runner_exec_command(
                        "/runner-exec run",
                        project_root=project_root,
                        memory_store=store,
                        executors=_runner_exec_executors(warnings=lambda: "must not run"),
                    )
                history = format_runner_exec_command("/runner-exec history", project_root=project_root, memory_store=store)
                summary = format_runner_exec_command("/runner-exec history-summary", project_root=project_root, memory_store=store)

        self.assertIn(f"event_count: {EVIDENCE_HISTORY_MAX_SIZE}", history)
        self.assertNotIn("event_id: runner_exec_0001\n", history)
        self.assertIn(f"latest_event_id: runner_exec_{EVIDENCE_HISTORY_MAX_SIZE + 5:04d}", summary)
        self.assertIn(f"refusal_count: {EVIDENCE_HISTORY_MAX_SIZE}", summary)

    def test_runner_exec_history_clear_preview_does_not_mutate_ring(self) -> None:
        reset_runner_exec_evidence()
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            with patch("proto_mind.runner_exec.ReadOnlyRunnerPilot.read_state", return_value=_runner_exec_state()):
                format_runner_exec_command(
                    "/runner-exec run",
                    project_root=project_root,
                    memory_store=store,
                    executors=_runner_exec_executors(warnings=lambda: "must not run"),
                )
                before = format_runner_exec_command("/runner-exec history-summary", project_root=project_root, memory_store=store)
                preview = format_runner_exec_command("/runner-exec history-clear-preview", project_root=project_root, memory_store=store)
                after = format_runner_exec_command("/runner-exec history-summary", project_root=project_root, memory_store=store)

        self.assertEqual(before, after)
        self.assertIn("mode: preview-only", preview)
        self.assertIn("history_cleared: false", preview)
        self.assertIn("mutation_performed: false", preview)
        self.assertIn("actual_clear_command: not available", preview)

    def test_runner_exec_history_doctor_is_ok_for_compact_bounded_history(self) -> None:
        reset_runner_exec_evidence()
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            with patch("proto_mind.runner_exec.ReadOnlyRunnerPilot.read_state", return_value=_runner_exec_state()):
                format_runner_exec_command(
                    f"/runner-exec run {DAILY_DOCTOR_CONFIRMATION}",
                    project_root=project_root,
                    memory_store=store,
                    executors=_runner_exec_executors(),
                )
                output = format_runner_exec_command("/runner-exec history-doctor", project_root=project_root, memory_store=store)

        self.assertIn("Status: OK", output)
        self.assertIn(f"bounded max_size={EVIDENCE_HISTORY_MAX_SIZE}", output)
        self.assertIn("compact safe schema", output)
        self.assertIn("No history event marks an outside-allowlist", output)
        self.assertIn("Context Injection is disabled", output)

    def test_runner_exec_evidence_views_include_bounded_history(self) -> None:
        reset_runner_exec_evidence()
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            with patch("proto_mind.runner_exec.ReadOnlyRunnerPilot.read_state", return_value=_runner_exec_state()):
                format_runner_exec_command(
                    f"/runner-exec run {EXPORTS_DOCTOR_CONFIRMATION}",
                    project_root=project_root,
                    memory_store=store,
                    executors=_runner_exec_executors(),
                )
                evidence = format_runner_exec_command("/runner-exec evidence", project_root=project_root, memory_store=store)
                check = format_runner_exec_command("/runner-exec evidence-check", project_root=project_root, memory_store=store)
                sequence = format_runner_exec_command("/runner-exec sequence-evidence", project_root=project_root, memory_store=store)
                soak = format_runner_exec_command("/runner-exec soak-report", project_root=project_root, memory_store=store)

        self.assertIn("history_available: true", evidence)
        self.assertIn("history_latest_event_id: runner_exec_0001", evidence)
        self.assertIn(f"History ring is bounded at {EVIDENCE_HISTORY_MAX_SIZE}", check)
        self.assertIn(f"history_events: 1/{EVIDENCE_HISTORY_MAX_SIZE}", sequence)
        self.assertIn(f"history_events: 1/{EVIDENCE_HISTORY_MAX_SIZE}", soak)

    def test_runner_exec_doctor_and_handoff_include_history_layer(self) -> None:
        reset_runner_exec_evidence()
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            with patch("proto_mind.runner_exec.ReadOnlyRunnerPilot.read_state", return_value=_runner_exec_state()):
                doctor = format_runner_exec_command(
                    "/runner-exec doctor",
                    project_root=project_root,
                    memory_store=store,
                    executors=_runner_exec_executors(),
                )
                handoff = format_runner_exec_command("/runner-exec handoff", project_root=project_root, memory_store=store)

        self.assertIn("Evidence history summary: OK", doctor)
        self.assertIn(f"compact {EVIDENCE_HISTORY_MAX_SIZE}-event ring", handoff)
        self.assertIn("/runner-exec history-clear-preview", handoff)
        self.assertIn("no history is persisted", handoff)

    def test_runner_exec_history_commands_are_registered_and_do_not_expand_execution(self) -> None:
        expected_allowlist = (
            PILOT_COMMAND,
            DAILY_DOCTOR_COMMAND,
            EXPORTS_DOCTOR_COMMAND,
            CAPABILITIES_SAFETY_COMMAND,
        )
        registry = {spec.prefix: spec for spec in COMMAND_REGISTRY}

        self.assertEqual(tuple(ACTIVE_READONLY_ALLOWLIST), expected_allowlist)
        for command in (
            "/runner-exec history",
            "/runner-exec history-summary",
            "/runner-exec history-clear-preview",
            "/runner-exec history-doctor",
        ):
            self.assertIn(command, registry)
            self.assertTrue(registry[command].read_only)
            self.assertEqual(registry[command].mutates, "none")
            self.assertEqual(registry[command].risk, "low")
            self.assertNotIn(command, ACTIVE_READONLY_ALLOWLIST)
