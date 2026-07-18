from __future__ import annotations

from proto_mind.python_env import enforce_python_version

enforce_python_version()

from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from proto_mind.action_policy import format_policy_command
from proto_mind.action_preview import format_action_command
from proto_mind.action_queue import format_action_queue_command
from proto_mind.activation_layer import format_activation_command
from proto_mind.acceptance_layer import format_acceptance_command
from proto_mind.agenda_layer import format_agenda_command
from proto_mind.backup_utils import format_backup_command
from proto_mind.baseline_layer import format_baseline_command
from proto_mind.capability_map import format_capability_command
from proto_mind.command_registry import format_commands_command
from proto_mind.closure_layer import format_closure_command
from proto_mind.confirmation_layer import format_confirmation_command
from proto_mind.config import ProtoMindConfig
from proto_mind.consolidation import format_consolidation_command
from proto_mind.context_pack import format_context_command, prepare_context_injection, record_context_injection_skip
from proto_mind.coordinator import Coordinator
from proto_mind.data_integrity import format_data_command
from proto_mind.daily_layer import format_daily_command
from proto_mind.experiment_journal import format_experiment_command
from proto_mind.experience_pilot import (
    format_experience_pilot_command,
    format_experience_pilot_observation,
    observe_experience_pilot_if_active,
)
from proto_mind.export_retention import format_exports_command
from proto_mind.focus_layer import format_focus_command
from proto_mind.goal_stack import format_goal_command
from proto_mind.identity import format_identity_command
from proto_mind.memory_commands import format_memory_command
from proto_mind.memory_card_layer import format_memory_card_command
from proto_mind.memory_hygiene import MemoryHygiene
from proto_mind.memory_keeper import MemoryKeeper
from proto_mind.memory_store import MemoryStore
from proto_mind.milestone_layer import format_milestone_command
from proto_mind.natural_commands import format_natural_introspection_command, route_natural_command
from proto_mind.observer import Observer
from proto_mind.operating_loop import format_loop_command
from proto_mind.plan_layer import format_plan_command
from proto_mind.prechange_layer import format_prechange_command
from proto_mind.proto_status import format_proto_command
from proto_mind.reasoners import create_reasoner
from proto_mind.reflection_journal import format_reflection_command
from proto_mind.runner_layer import format_runner_command
from proto_mind.runner_candidates import format_runner_candidates_command
from proto_mind.runner_exec import format_runner_exec_command
from proto_mind.runner_exec_config import (
    CAPABILITIES_SAFETY_COMMAND,
    DAILY_DOCTOR_COMMAND,
    EXPORTS_DOCTOR_COMMAND,
    PILOT_COMMAND as PILOT_RUNNER_TARGET,
)
from proto_mind.runner_mvp import format_runner_mvp_command
from proto_mind.sandbox_layer import format_sandbox_command
from proto_mind.session_log import SessionOperatorLogger, format_session_log_command
from proto_mind.session_rituals import format_session_ritual_command
from proto_mind.showcase_layer import format_showcase_command
from proto_mind.skill_library import format_skill_command
from proto_mind.task_queue import format_task_command
from proto_mind.world_model import format_world_command
from proto_mind.warning_inspector import format_warning_command


def build_coordinator(
    base_dir: Path | None = None,
    config: ProtoMindConfig | None = None,
    session_logger: SessionOperatorLogger | None = None,
) -> Coordinator:
    root = base_dir or Path(__file__).resolve().parent
    app_config = config or ProtoMindConfig.from_env(root)
    data_dir = app_config.data_dir or (root / "data")
    store = MemoryStore(
        working_path=data_dir / "working_memory.json",
        persistent_path=data_dir / "persistent_memory.json",
    )
    return Coordinator(
        observer=Observer(),
        memory_keeper=MemoryKeeper(store),
        reasoner=create_reasoner(app_config),
        config=app_config,
        session_logger=session_logger,
    )


def main() -> None:
    project_root = Path(__file__).resolve().parents[1]
    session_logger = SessionOperatorLogger.from_project_root(project_root)
    coordinator = build_coordinator(session_logger=session_logger)
    hygiene = MemoryHygiene(coordinator.memory_keeper.store)
    print(
        "Proto-Mind v0 interactive shell. "
        f"Backend={coordinator.reasoner.backend_name}. Type 'exit' to stop."
    )
    while True:
        try:
            user_input = input("You: ").strip()
        except EOFError:
            break
        output = process_interactive_input(
            user_input,
            coordinator=coordinator,
            session_logger=session_logger,
            project_root=project_root,
            hygiene=hygiene,
        )
        if output is None:
            break
        print(output)


def process_interactive_input(
    user_input: str,
    *,
    coordinator: Coordinator,
    session_logger: SessionOperatorLogger,
    project_root: Path,
    hygiene: MemoryHygiene | None = None,
) -> str | None:
    user_input = user_input.strip()
    if is_exit_command(user_input):
        return None
    experience_output = format_experience_pilot_command(
        user_input,
        owner=coordinator,
        project_root=project_root,
    )
    if experience_output is not None:
        _record_context_skip(project_root, user_input, "slash_command")
        return experience_output
    showcase_output = format_showcase_command(
        user_input,
        project_root=project_root,
        memory_store=coordinator.memory_keeper.store,
        owner=coordinator,
    )
    if showcase_output is not None:
        return showcase_output
    proto_output = format_proto_command(
        user_input,
        project_root=project_root,
        memory_store=coordinator.memory_keeper.store,
    )
    if proto_output is not None:
        return proto_output
    exports_output = format_exports_command(user_input, project_root=project_root)
    if exports_output is not None:
        return exports_output
    daily_output = format_daily_command(
        user_input,
        project_root=project_root,
        memory_store=coordinator.memory_keeper.store,
    )
    if daily_output is not None:
        return daily_output
    session_ritual_output = format_session_ritual_command(
        user_input,
        project_root=project_root,
        memory_store=coordinator.memory_keeper.store,
    )
    if session_ritual_output is not None:
        return session_ritual_output
    milestone_output = format_milestone_command(
        user_input,
        project_root=project_root,
        memory_store=coordinator.memory_keeper.store,
    )
    if milestone_output is not None:
        return milestone_output
    warning_output = format_warning_command(
        user_input,
        project_root=project_root,
        memory_store=coordinator.memory_keeper.store,
    )
    if warning_output is not None:
        return warning_output
    agenda_output = format_agenda_command(
        user_input,
        project_root=project_root,
        memory_store=coordinator.memory_keeper.store,
    )
    if agenda_output is not None:
        return agenda_output
    prechange_output = format_prechange_command(
        user_input,
        project_root=project_root,
        memory_store=coordinator.memory_keeper.store,
    )
    if prechange_output is not None:
        return prechange_output
    focus_output = format_focus_command(
        user_input,
        project_root=project_root,
        memory_store=coordinator.memory_keeper.store,
    )
    if focus_output is not None:
        return focus_output
    acceptance_output = format_acceptance_command(
        user_input,
        project_root=project_root,
        memory_store=coordinator.memory_keeper.store,
    )
    if acceptance_output is not None:
        return acceptance_output
    baseline_output = format_baseline_command(
        user_input,
        project_root=project_root,
        memory_store=coordinator.memory_keeper.store,
    )
    if baseline_output is not None:
        return baseline_output
    closure_output = format_closure_command(
        user_input,
        project_root=project_root,
        memory_store=coordinator.memory_keeper.store,
    )
    if closure_output is not None:
        return closure_output
    memory_card_output = format_memory_card_command(
        user_input,
        project_root=project_root,
        memory_store=coordinator.memory_keeper.store,
    )
    if memory_card_output is not None:
        return memory_card_output
    capability_output = format_capability_command(
        user_input,
        project_root=project_root,
        memory_store=coordinator.memory_keeper.store,
    )
    if capability_output is not None:
        return capability_output
    plan_output = format_plan_command(
        user_input,
        project_root=project_root,
        memory_store=coordinator.memory_keeper.store,
    )
    if plan_output is not None:
        return plan_output
    confirmation_output = format_confirmation_command(
        user_input,
        project_root=project_root,
        memory_store=coordinator.memory_keeper.store,
    )
    if confirmation_output is not None:
        return confirmation_output
    sandbox_output = format_sandbox_command(
        user_input,
        project_root=project_root,
        memory_store=coordinator.memory_keeper.store,
    )
    if sandbox_output is not None:
        return sandbox_output
    runner_output = format_runner_command(
        user_input,
        project_root=project_root,
        memory_store=coordinator.memory_keeper.store,
    )
    if runner_output is not None:
        return runner_output
    runner_candidates_output = format_runner_candidates_command(
        user_input,
        project_root=project_root,
        memory_store=coordinator.memory_keeper.store,
    )
    if runner_candidates_output is not None:
        return runner_candidates_output
    activation_output = format_activation_command(
        user_input,
        project_root=project_root,
        memory_store=coordinator.memory_keeper.store,
    )
    if activation_output is not None:
        return activation_output
    runner_mvp_output = format_runner_mvp_command(
        user_input,
        project_root=project_root,
        memory_store=coordinator.memory_keeper.store,
    )
    if runner_mvp_output is not None:
        return runner_mvp_output
    runner_exec_output = format_runner_exec_command(
        user_input,
        project_root=project_root,
        memory_store=coordinator.memory_keeper.store,
        executors={
            PILOT_RUNNER_TARGET: lambda: _execute_runner_warning_target(
                project_root=project_root,
                memory_store=coordinator.memory_keeper.store,
            ),
            DAILY_DOCTOR_COMMAND: lambda: _execute_runner_daily_doctor_target(
                project_root=project_root,
                memory_store=coordinator.memory_keeper.store,
            ),
            EXPORTS_DOCTOR_COMMAND: lambda: _execute_runner_exports_doctor_target(project_root=project_root),
            CAPABILITIES_SAFETY_COMMAND: lambda: _execute_runner_capabilities_safety_target(
                project_root=project_root,
                memory_store=coordinator.memory_keeper.store,
            ),
        },
    )
    if runner_exec_output is not None:
        return runner_exec_output
    action_queue_output = format_action_queue_command(
        user_input,
        project_root=project_root,
        executor=lambda command: _execute_read_only_action_target(
            command,
            coordinator=coordinator,
            session_logger=session_logger,
            project_root=project_root,
            hygiene=hygiene,
        ),
    )
    if action_queue_output is not None:
        if not " ".join(user_input.lower().split()).startswith("/action run "):
            _record_context_skip(project_root, user_input, "slash_command")
        return action_queue_output
    action_output = format_action_command(user_input)
    if action_output is not None:
        _record_context_skip(project_root, user_input, "slash_command")
        return action_output
    policy_output = format_policy_command(user_input)
    if policy_output is not None:
        _record_context_skip(project_root, user_input, "slash_command")
        return policy_output
    command_registry_output = format_commands_command(user_input)
    if command_registry_output is not None:
        _record_context_skip(project_root, user_input, "slash_command")
        return command_registry_output
    natural_introspection_output = format_natural_introspection_command(user_input)
    if natural_introspection_output is not None:
        _record_context_skip(project_root, user_input, "slash_command")
        return natural_introspection_output
    natural_command_output = format_natural_command(
        user_input,
        session_logger,
        project_root=project_root,
        coordinator=coordinator,
    )
    if natural_command_output is not None:
        _record_context_skip(project_root, user_input, "natural_routed_command")
        return natural_command_output
    session_log_output = format_session_log_command(user_input, session_logger)
    if session_log_output is not None:
        _record_context_skip(project_root, user_input, "slash_command")
        return session_log_output
    backup_output = format_backup_command(user_input, project_root)
    if backup_output is not None:
        _record_context_skip(project_root, user_input, "slash_command")
        return backup_output
    reflection_output = format_reflection_command(
        user_input,
        project_root=project_root,
        session_logger=session_logger,
    )
    if reflection_output is not None:
        _record_context_skip(project_root, user_input, "slash_command")
        return reflection_output
    goal_output = format_goal_command(user_input, project_root=project_root)
    if goal_output is not None:
        _record_context_skip(project_root, user_input, "slash_command")
        return goal_output
    task_output = format_task_command(user_input, project_root=project_root)
    if task_output is not None:
        _record_context_skip(project_root, user_input, "slash_command")
        return task_output
    experiment_output = format_experiment_command(user_input, project_root=project_root)
    if experiment_output is not None:
        _record_context_skip(project_root, user_input, "slash_command")
        return experiment_output
    skill_output = format_skill_command(user_input, project_root=project_root)
    if skill_output is not None:
        _record_context_skip(project_root, user_input, "slash_command")
        return skill_output
    world_output = format_world_command(user_input, project_root=project_root)
    if world_output is not None:
        _record_context_skip(project_root, user_input, "slash_command")
        return world_output
    identity_output = format_identity_command(user_input, project_root=project_root)
    if identity_output is not None:
        _record_context_skip(project_root, user_input, "slash_command")
        return identity_output
    consolidation_output = format_consolidation_command(user_input, project_root=project_root)
    if consolidation_output is not None:
        _record_context_skip(project_root, user_input, "slash_command")
        return consolidation_output
    data_output = format_data_command(user_input, project_root=project_root)
    if data_output is not None:
        _record_context_skip(project_root, user_input, "slash_command")
        return data_output
    context_output = format_context_command(user_input, project_root=project_root)
    if context_output is not None:
        return context_output
    loop_output = format_loop_command(user_input, project_root=project_root)
    if loop_output is not None:
        _record_context_skip(project_root, user_input, "slash_command")
        return loop_output
    memory_command_output = format_memory_command(user_input, coordinator.memory_keeper.store)
    if memory_command_output is not None:
        _record_context_skip(project_root, user_input, "slash_command")
        return memory_command_output
    active_hygiene = hygiene or MemoryHygiene(coordinator.memory_keeper.store)
    if user_input in {"/memory hygiene", "/memory hygiene-preview", "/memory cleanup-preview"}:
        _record_context_skip(project_root, user_input, "slash_command")
        return _format_hygiene_preview(active_hygiene.preview_cleanup())
    if user_input == "/memory cleanup-apply":
        _record_context_skip(project_root, user_input, "slash_command")
        result = active_hygiene.apply_cleanup()
        lines = [
            _format_hygiene_preview(result.preview),
            f"Cleanup applied: removed working={result.removed_working_ids}; persistent={result.removed_persistent_ids}",
        ]
        if result.repaired_superseded_by_refs:
            lines.append("Repaired superseded_by references:")
            for repair in result.repaired_superseded_by_refs:
                lines.append(
                    "  "
                    f"{repair.record_id[:8]}:{repair.layer} "
                    f"{repair.old_superseded_by[:8]} -> {repair.new_superseded_by[:8]}"
                )
        return "\n".join(lines)
    if user_input in {"/memory repair-preview", "/memory references-preview"}:
        _record_context_skip(project_root, user_input, "slash_command")
        return _format_reference_repair_preview(active_hygiene.preview_reference_repair())
    if user_input == "/memory repair-apply":
        _record_context_skip(project_root, user_input, "slash_command")
        result = active_hygiene.apply_reference_repair()
        return "\n".join(
            [
                _format_reference_repair_preview(result.preview),
                _format_reference_repairs(result.repaired_superseded_by_refs),
            ]
        )
    injection = prepare_context_injection(user_input, project_root=project_root)
    result = coordinator.handle(user_input, reasoner_input=injection.get("reasoner_input"))
    pilot_observation = observe_experience_pilot_if_active(
        coordinator,
        user_input,
        result,
        context_injection_applied=bool(injection.get("applied")),
    )
    return _format_interaction_result(
        result,
        context_injection=injection,
        experience_pilot=pilot_observation,
    )


def _record_context_skip(project_root: Path, user_input: str, reason: str) -> None:
    if user_input.startswith(("/context injection", "/experience")):
        return
    record_context_injection_skip(project_root=project_root, user_input=user_input, skip_reason=reason)


def _execute_runner_warning_target(*, project_root: Path, memory_store: MemoryStore) -> str:
    output = format_warning_command(PILOT_RUNNER_TARGET, project_root=project_root, memory_store=memory_store)
    if output is None:
        raise RuntimeError("Fixed warning runner target is unavailable")
    return output


def _execute_runner_daily_doctor_target(*, project_root: Path, memory_store: MemoryStore) -> str:
    output = format_daily_command(DAILY_DOCTOR_COMMAND, project_root=project_root, memory_store=memory_store)
    if output is None:
        raise RuntimeError("Fixed daily-doctor runner target is unavailable")
    return output


def _execute_runner_exports_doctor_target(*, project_root: Path) -> str:
    output = format_exports_command(EXPORTS_DOCTOR_COMMAND, project_root=project_root)
    if output is None:
        raise RuntimeError("Fixed exports-doctor runner target is unavailable")
    return output


def _execute_runner_capabilities_safety_target(*, project_root: Path, memory_store: MemoryStore) -> str:
    output = format_capability_command(
        CAPABILITIES_SAFETY_COMMAND,
        project_root=project_root,
        memory_store=memory_store,
    )
    if output is None:
        raise RuntimeError("Fixed capabilities-safety runner target is unavailable")
    return output


def _execute_read_only_action_target(
    command: str,
    *,
    coordinator: Coordinator,
    session_logger: SessionOperatorLogger,
    project_root: Path,
    hygiene: MemoryHygiene | None,
) -> str:
    formatters = (
        lambda: format_action_queue_command(command, project_root=project_root),
        lambda: format_action_command(command),
        lambda: format_policy_command(command),
        lambda: format_commands_command(command),
        lambda: format_natural_introspection_command(command),
        lambda: format_session_log_command(command, session_logger),
        lambda: format_reflection_command(command, project_root=project_root, session_logger=session_logger),
        lambda: format_goal_command(command, project_root=project_root),
        lambda: format_task_command(command, project_root=project_root),
        lambda: format_experiment_command(command, project_root=project_root),
        lambda: format_skill_command(command, project_root=project_root),
        lambda: format_world_command(command, project_root=project_root),
        lambda: format_identity_command(command, project_root=project_root),
        lambda: format_consolidation_command(command, project_root=project_root),
        lambda: format_data_command(command, project_root=project_root),
        lambda: format_context_command(command, project_root=project_root),
        lambda: format_loop_command(command, project_root=project_root),
        lambda: format_memory_command(command, coordinator.memory_keeper.store),
    )
    for formatter in formatters:
        output = formatter()
        if output is not None:
            return output
    active_hygiene = hygiene or MemoryHygiene(coordinator.memory_keeper.store)
    if command in {"/memory hygiene", "/memory hygiene-preview", "/memory cleanup-preview"}:
        return _format_hygiene_preview(active_hygiene.preview_cleanup())
    if command in {"/memory repair-preview", "/memory references-preview"}:
        return _format_reference_repair_preview(active_hygiene.preview_reference_repair())
    raise ValueError(f"No safe internal read-only handler for registered command: {command}")


def _capture_print(callback: object, *args: object) -> str:
    buffer = StringIO()
    with redirect_stdout(buffer):
        callback(*args)
    return buffer.getvalue().rstrip()


def _format_hygiene_preview(preview: object) -> str:
    return _capture_print(_print_hygiene_preview, preview)


def _format_reference_repair_preview(preview: object) -> str:
    return _capture_print(_print_reference_repair_preview, preview)


def _format_reference_repairs(repairs: object) -> str:
    return _capture_print(_print_reference_repairs, repairs)


def _format_interaction_result(
    result: object,
    *,
    context_injection: dict[str, object] | None = None,
    experience_pilot: object | None = None,
) -> str:
    lines = [f"Proto-Mind: {result.response}"]
    if context_injection:
        if context_injection.get("applied"):
            lines.append(
                "Context injection: enabled "
                f"({context_injection.get('mode')}, {context_injection.get('context_chars')} chars"
                f"{', truncated' if context_injection.get('truncated') else ''})"
            )
        elif context_injection.get("enabled") and context_injection.get("warning"):
            lines.append(f"Context injection: skipped ({context_injection.get('warning')})")
    if experience_pilot is not None:
        lines.append(format_experience_pilot_observation(experience_pilot))
    if result.previous_correction_hints:
        lines.append("Using previous correction hints:")
        for hint in result.previous_correction_hints:
            lines.append(f"  - {hint}")
    lines.append(f"Observer: {result.observer_state.to_dict()}")
    if result.retrieved_memory:
        lines.append("Memory used:")
        for record in result.retrieved_memory:
            lines.append(f"  - ({record.type}) {record.content}")
    if result.retrieval_trace:
        lines.append("Retrieval trace:")
        lines.append(
            "  "
            f"mode={result.retrieval_trace.query_mode}; "
            f"topics={result.retrieval_trace.normalized_query_topics}; "
            f"current={result.retrieval_trace.current_state_oriented}; "
            f"historical={result.retrieval_trace.historical_state_oriented}"
        )
        selected = [candidate for candidate in result.retrieval_trace.candidates if candidate.selected]
        filtered = [candidate for candidate in result.retrieval_trace.candidates if not candidate.selected][:3]
        for candidate in selected:
            lines.append(
                "  "
                f"selected#{candidate.selected_rank} "
                f"{candidate.record_id[:8]} "
                f"score={candidate.final_total_score:.4f} "
                f"type={candidate.memory_type} active={candidate.active} "
                f"matched={candidate.matched_topics} "
                f"preview={candidate.content_preview}"
            )
            if candidate.why_selected_summary:
                lines.append(f"    -> {candidate.why_selected_summary}")
        for candidate in filtered:
            lines.append(
                "  "
                f"filtered {candidate.record_id[:8]} "
                f"score={candidate.final_total_score:.4f} "
                f"reason={candidate.filtered_reason} "
                f"matched={candidate.matched_topics} "
                f"preview={candidate.content_preview}"
            )
            if candidate.why_not_selected_summary:
                lines.append(f"    -> {candidate.why_not_selected_summary}")
    lines.append(f"Memory decision: {result.memory_summary.to_dict()}")
    if result.grounding_audit:
        lines.append(_capture_print(_print_grounding_audit, result.grounding_audit))
    if result.self_reflection:
        lines.append(_capture_print(_print_self_reflection, result.self_reflection))
    return "\n".join(lines)


def _print_hygiene_preview(preview: object) -> None:
    data = preview.to_dict()
    print("Memory hygiene preview:")
    print(f"  duplicate_groups={len(data['duplicate_groups'])}; cleanup_candidates={data['cleanup_candidate_count']}")
    for group in data["duplicate_groups"]:
        print(
            "  "
            f"group keep={group['keep_record_id'][:8]}:{group['keep_layer']} "
            f"cleanup={len(group['cleanup_candidates'])} "
            f"content={group['normalized_content'][:72]}"
        )
        for record in group["records"]:
            state = "active" if record["active"] else "superseded"
            print(
                "    "
                f"{record['id'][:8]} {record['layer']} {record['memory_type']} {state} "
                f"importance={record['importance']} usage={record['usage_count']}"
            )
        for candidate in group["cleanup_candidates"]:
            print(f"    cleanup {candidate['id'][:8]}:{candidate['layer']} -> {candidate['reason']}")
    if not data["duplicate_groups"]:
        print("  No exact normalized-content duplicates found.")


def _print_reference_repair_preview(preview: object) -> None:
    data = preview.to_dict()
    print("Memory reference repair preview:")
    print(f"  orphaned_references={len(data['orphaned_references'])}; repairable={data['repairable_count']}")
    for reference in data["orphaned_references"]:
        state = "auto-repairable" if reference["auto_repairable"] else "manual"
        print(
            "  "
            f"{reference['record_id'][:8]}:{reference['layer']} "
            f"missing={reference['missing_superseded_by'][:8]} "
            f"{state} confidence={reference['confidence']}"
        )
        print(f"    record={reference['content_preview']}")
        if reference["candidate_record_id"]:
            print(
                "    "
                f"candidate={reference['candidate_record_id'][:8]}:{reference['candidate_layer']} "
                f"topics={reference['shared_topics']} "
                f"preview={reference['candidate_content_preview']}"
            )
        print(f"    reason={reference['reason']}")
    if not data["orphaned_references"]:
        print("  No orphaned superseded_by references found.")


def _print_reference_repairs(repairs: object) -> None:
    if not repairs:
        print("Reference repair applied: no safe repairs were made.")
        return
    print("Reference repair applied:")
    for repair in repairs:
        print(
            "  "
            f"{repair.record_id[:8]}:{repair.layer} "
            f"{repair.old_superseded_by[:8]} -> {repair.new_superseded_by[:8]}"
        )


def _print_self_reflection(reflection: object) -> None:
    data = reflection.to_dict()
    print("Self-reflection:")
    print(f"  memory_alignment: {data['memory_alignment']}")
    print(f"  preference_alignment: {data['preference_alignment']}")
    print(f"  active_decision_alignment: {data['active_decision_alignment']}")
    print(f"  superseded_memory_risk: {data['superseded_memory_risk']}")
    print(f"  unsupported_claims_risk: {data['unsupported_claims_risk']}")
    print(f"  overall_confidence: {data['overall_confidence']}")
    if data["warnings"]:
        print("  warnings:")
        for warning in data["warnings"]:
            print(f"    - {warning}")
    else:
        print("  warnings: none")
    if data["suggested_next_turn_adjustments"]:
        print("  suggested_next_turn_adjustments:")
        for adjustment in data["suggested_next_turn_adjustments"]:
            print(f"    - {adjustment}")
    if data["correction_hints"]:
        print("  correction_hints:")
        for hint in data["correction_hints"]:
            print(f"    - {hint}")
        print(f"  carry_forward_scope: {data['carry_forward_scope']}")


def _print_grounding_audit(audit: object) -> None:
    data = audit.to_dict()
    print("Grounding audit:")
    print(f"  status: {data['grounding_status']}")
    print(f"  memory_support: {data['memory_support']}")
    print(f"  active_decision_status: {data['active_decision_status']}")
    print(f"  superseded_memory_status: {data['superseded_memory_status']}")
    print(f"  confidence: {data['confidence']}")
    if data["warnings"]:
        print("  warnings:")
        for warning in data["warnings"]:
            print(f"    - {warning}")
    else:
        print("  warnings: none")
    if data["unsupported_claims"]:
        print("  unsupported_claims:")
        for claim in data["unsupported_claims"]:
            print(f"    - {claim}")
    if data["evidence"]:
        print("  evidence:")
        for item in data["evidence"][:3]:
            print(f"    - {item}")


def format_natural_command(
    user_input: str,
    session_logger: SessionOperatorLogger,
    *,
    project_root: Path | None = None,
    coordinator: Coordinator | None = None,
) -> str | None:
    route = route_natural_command(user_input)
    if route is None:
        return None
    commands = (route,) if isinstance(route, str) else route
    outputs: list[tuple[str, str]] = []
    for command in commands:
        output = _format_natural_operator_command(
            command,
            session_logger=session_logger,
            project_root=project_root,
            coordinator=coordinator,
        )
        if output is None:
            output = "Natural route unavailable in the current runtime."
        outputs.append((command, output))
    if len(outputs) == 1:
        command, output = outputs[0]
        return f"Natural command matched: {command}\n\n{output}"
    lines = ["Natural command bundle matched:"]
    lines.extend(f"- {command}" for command, _ in outputs)
    for command, output in outputs:
        lines.extend(["", f"=== {command} ===", output])
    return "\n".join(lines)


def _format_natural_operator_command(
    command: str,
    *,
    session_logger: SessionOperatorLogger,
    project_root: Path | None,
    coordinator: Coordinator | None,
) -> str | None:
    if command.startswith("/session "):
        return format_session_log_command(command, session_logger)
    if project_root is None:
        return None
    if command.startswith("/data "):
        return format_data_command(command, project_root=project_root)
    if command.startswith("/loop "):
        return format_loop_command(command, project_root=project_root)
    if command.startswith("/consolidation "):
        return format_consolidation_command(command, project_root=project_root)
    if command.startswith("/context injection "):
        return format_context_command(command, project_root=project_root)
    if command.startswith("/memory ") and coordinator is not None:
        return format_memory_command(command, coordinator.memory_keeper.store)
    return None


def is_exit_command(text: str) -> bool:
    return text.strip().lower() in {"exit", "quit", "q", "/exit", "/quit", "/q"}


if __name__ == "__main__":
    main()
