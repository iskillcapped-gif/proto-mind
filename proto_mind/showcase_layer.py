from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from proto_mind.action_policy import classify_command
from proto_mind.command_registry import COMMAND_REGISTRY, command_registry_doctor
from proto_mind.experience_pilot import peek_experience_pilot
from proto_mind.experience_turn import CognitiveTurnProjectionError, CognitiveTurnProjector
from proto_mind.memory_card_layer import OperatorMemoryCard
from proto_mind.memory_store import MemoryStore
from proto_mind.operating_loop import OperatingLoop
from proto_mind.runner_exec_config import ACTIVE_READONLY_ALLOWLIST, EXACT_CONFIRMATIONS
from proto_mind.task_queue import PRIORITY_RANK


SHOWCASE_VERSION = 1
SHOWCASE_COMMANDS = (
    "/showcase status",
    "/showcase demo",
    "/showcase script",
    "/showcase doctor",
)
SHOWCASE_DEADLINE = "2026-07-21"
_DEPENDENCY_COMMANDS = (
    "/memory summary",
    "/loop next",
    "/warnings unknown",
    "/context injection status",
    "/experience preview",
    "/experience episodes",
    "/experience episode",
    "/experience events",
    "/experience inspect",
    "/runner-exec dry-run",
    "/capabilities safety",
)
_FORBIDDEN_EXPERIENCE_PREFIXES = (
    "/experience persist",
    "/experience export",
    "/experience apply",
    "/experience promote",
    "/experience backfill",
)


def format_showcase_command(
    command: str,
    *,
    project_root: Path,
    memory_store: MemoryStore,
    owner: object,
) -> str | None:
    normalized = " ".join(command.strip().lower().split())
    if not normalized.startswith("/showcase"):
        return None
    showcase = ContestShowcase(
        project_root=project_root,
        memory_store=memory_store,
        owner=owner,
    )
    if normalized == "/showcase status":
        return showcase.format_status()
    if normalized == "/showcase demo":
        return showcase.format_demo()
    if normalized == "/showcase script":
        return showcase.format_script()
    if normalized == "/showcase doctor":
        return showcase.format_doctor()
    return "Usage:\n" + "\n".join(f"  {item}" for item in SHOWCASE_COMMANDS)


class ContestShowcase:
    """Read-only contest narrative over existing local cognitive and safety state."""

    def __init__(
        self,
        *,
        project_root: Path,
        memory_store: MemoryStore,
        owner: object,
    ) -> None:
        self.project_root = Path(project_root)
        self.memory_store = memory_store
        self.owner = owner
        self.memory_card = OperatorMemoryCard(
            project_root=self.project_root,
            memory_store=self.memory_store,
        )
        self.loop = OperatingLoop.from_project_root(self.project_root)

    def read_state(self) -> dict[str, Any]:
        card = self.memory_card.read_state()
        loop = self.loop.snapshot()
        pilot = peek_experience_pilot(self.owner)
        focused_goal = loop["focused_goals"][0] if loop["focused_goals"] else None
        next_task = _best_task(
            loop["open_tasks"],
            focused_goal_id=str(focused_goal.get("id")) if focused_goal else None,
        )
        context_state = str(card.get("context_state") or "unknown")
        unknown = list(card.get("unknown") or [])
        blockers = int(card.get("blocker_count") or 0)
        safe = context_state == "disabled" and not unknown and blockers == 0
        experience_events = pilot.snapshot() if pilot is not None else ()
        latest_episode = _latest_turn_episode(experience_events)
        return {
            "showcase_status": "READY" if safe else "BLOCKED",
            "showcase_safe": safe,
            "identity": card.get("identity") or {},
            "accepted_baseline": card.get("accepted_baseline") or "not detected",
            "test_baseline": card.get("test_baseline") or "not checked",
            "context_state": context_state,
            "accepted_warnings": list(card.get("accepted") or []),
            "unknown_warnings": unknown,
            "blocker_count": blockers,
            "latest_snapshot": card.get("latest_snapshot"),
            "latest_diff": card.get("latest_diff"),
            "focused_goal": focused_goal,
            "next_task": next_task,
            "memory": loop["memory"],
            "open_task_count": len(loop["open_tasks"]),
            "open_experiment_count": len(loop["open_experiments"]),
            "open_world_count": len(loop["open_world"]),
            "active_skill_count": len(loop["active_skills"]),
            "reflection_count": len(loop["reflections"]),
            "experience_state": pilot.state if pilot is not None else "not_started",
            "experience_session_id": pilot.session_id if pilot is not None else "none",
            "experience_turns": pilot.captured_turns if pilot is not None else 0,
            "experience_event_count": pilot.event_count if pilot is not None else 0,
            "experience_byte_count": pilot.byte_count if pilot is not None else 0,
            "experience_events": experience_events,
            "latest_experience_episode": latest_episode,
            "registry_commands": len(COMMAND_REGISTRY),
            "registry_categories": len({item.category for item in COMMAND_REGISTRY}),
            "runner_allowlist": tuple(ACTIVE_READONLY_ALLOWLIST),
        }

    def format_status(self) -> str:
        state = self.read_state()
        return "\n".join(
            [
                "Proto-Mind Contest Showcase v1",
                f"Status: {state['showcase_status']}",
                f"submission_target: {SHOWCASE_DEADLINE}",
                f"project_root: {self.project_root}",
                f"command_registry: {state['registry_commands']} commands / {state['registry_categories']} categories",
                f"test_baseline: {state['test_baseline']}",
                f"context_injection: {state['context_state']}",
                f"warnings: accepted={len(state['accepted_warnings'])}, unknown={len(state['unknown_warnings'])}, blockers={state['blocker_count']}",
                f"experience_pilot: state={state['experience_state']}, turns={state['experience_turns']}, events={state['experience_event_count']}",
                f"read_only_runner_allowlist: {len(state['runner_allowlist'])}",
                f"showcase_safe: {str(state['showcase_safe']).lower()}",
                "",
                "Available commands:",
                *[f"- {item}" for item in SHOWCASE_COMMANDS],
                "",
                "Boundary:",
                "- Read-only live presentation only; no command, consent, model call, snapshot, export, store, or runner evidence was created or changed.",
            ]
        )

    def format_demo(self) -> str:
        state = self.read_state()
        identity = state["identity"]
        memory = state["memory"]
        recent_events = list(state["experience_events"])[-3:]
        latest_episode = state["latest_experience_episode"]
        lines = [
            "PROTO-MIND | LOCAL COGNITIVE OPERATING SYSTEM",
            f"Showcase readiness: {state['showcase_status']}",
            "",
            "1. CONTINUITY",
            f"- Identity: {identity.get('name') or 'Proto-Mind'} | {identity.get('role') or 'local-first cognitive assistant'}",
            f"- Focused goal: {_goal_line(state['focused_goal'])}",
            f"- Next task: {_task_line(state['next_task'])}",
            f"- Active explicit memory: {memory.get('active_explicit', 0)} records",
            f"- Live work: tasks={state['open_task_count']}, experiments={state['open_experiment_count']}, predictions={state['open_world_count']}",
            "",
            "2. EXPLAINABLE EXPERIENCE",
            f"- Pilot: {state['experience_state']} | session={state['experience_session_id']}",
            f"- Evidence: turns={state['experience_turns']}, events={state['experience_event_count']}, bytes={state['experience_byte_count']}",
            "- Consent: preview first, then an exact session-bound phrase",
            "- Privacy: deterministic credential redaction before compact previews",
            "- Retention: process memory only; restart discards evidence",
        ]
        if recent_events:
            if latest_episode:
                lines.append(
                    "- Latest cognitive episode: "
                    f"turn={latest_episode['turn_id']} | intent={latest_episode['intent']} | "
                    f"recall={latest_episode['selected_count']} selected | "
                    f"store={str(latest_episode['should_store']).lower()} | "
                    f"grounding={latest_episode['grounding_status']}"
                )
                lines.append("- Inspect cognitive path: /experience episode latest")
            lines.append("- Latest typed evidence:")
            lines.extend(
                f"  {event.get('id')} | {event.get('event_type')} | turn={event.get('turn_id')}"
                for event in recent_events
            )
            lines.append(f"- Inspect provenance: /experience inspect {recent_events[-1].get('id')}")
        else:
            lines.append("- Next manual step: /experience preview")
        lines.extend(
            [
                "",
                "3. GOVERNANCE",
                f"- Context Injection: {state['context_state']}",
                f"- Warnings: accepted-known={len(state['accepted_warnings'])}, unknown={len(state['unknown_warnings'])}, blockers={state['blocker_count']}",
                "- Persistent Experience capture: disabled",
                "- Automatic memory promotion and learning apply: unavailable",
                "",
                "4. BOUNDED ACTION",
                f"- Active read-only capabilities: {len(state['runner_allowlist'])}",
                *[f"  {command} | exact per-run confirmation required" for command in state["runner_allowlist"]],
                "- Transport: fixed internal callbacks only; no shell, free-form dispatch, network, or background runner",
                "",
                "WHY IT MATTERS",
                "- Proto-Mind preserves local continuity, turns a consented cognitive turn into inspectable evidence, and keeps action behind explicit deterministic gates.",
                "",
                "No command executed. No state mutated. This report is a live read-only view.",
            ]
        )
        return "\n".join(lines)

    def format_script(self) -> str:
        return "\n".join(
            [
                "Proto-Mind Contest Showcase | 3-Minute Operator Script",
                "",
                "Act 1 | Continuity (35 sec)",
                "1. Run: /showcase status",
                "2. Run: /showcase demo",
                "3. Say: Proto-Mind keeps identity, focus, memory, experiments, predictions, and skills local and inspectable.",
                "",
                "Act 2 | Consent and Experience (75 sec)",
                "1. Run: /experience preview",
                "2. Copy and run the exact session-bound consent command printed by preview.",
                "3. Ask one normal question, for example: What do you remember about our current Proto-Mind direction?",
                "4. Point out the visible 'Experience pilot: captured turn' indicator.",
                "5. Run: /experience events --last 7",
                "6. Run: /experience episode latest",
                "7. Optionally run: /experience inspect <latest_event_id>",
                "8. Say: one compact episode connects observe, intent, recall, response, memory decision, reflection, verification, and provenance.",
                "",
                "Act 3 | Safe Action (50 sec)",
                "1. Run: /runner-exec dry-run /daily doctor",
                f"2. Show the exact phrase: {EXACT_CONFIRMATIONS['/daily doctor']}",
                "3. Optionally run the displayed exact /runner-exec run command.",
                "4. Run: /runner-exec evidence-check",
                "5. Say: only four fixed read-only internal callbacks exist; no shell or free-form execution exists.",
                "",
                "Act 4 | Close (20 sec)",
                "1. Run: /showcase demo",
                "2. Run: /experience stop",
                "3. Say: continuity, evidence, and action are connected, but consent and safety boundaries stay explicit.",
                "",
                "Demo recovery:",
                "- If Context Injection is enabled, disable it manually before starting the pilot: /context injection disable",
                "- If the pilot is stopped, restart Proto-Mind; consent never survives a process restart.",
                "- If a doctor warns, explain the finding rather than hiding or repairing it during the demo.",
                "",
                "Script boundary:",
                "- Text guidance only; this command ran no step, captured no consent, and changed no file or runtime evidence.",
            ]
        )

    def doctor_report(self) -> dict[str, Any]:
        state = self.read_state()
        by_prefix = {item.prefix: item for item in COMMAND_REGISTRY}
        findings: list[dict[str, str]] = []
        missing = [item for item in SHOWCASE_COMMANDS + _DEPENDENCY_COMMANDS if item not in by_prefix]
        if missing:
            findings.append({"severity": "ERROR", "message": f"Required commands missing from Registry: {', '.join(missing)}"})
        else:
            findings.append({"severity": "OK", "message": "Showcase and dependency commands are registered."})
        unsafe_showcase = [
            item
            for item in SHOWCASE_COMMANDS
            if item in by_prefix and (not by_prefix[item].read_only or by_prefix[item].mutates != "none")
        ]
        if unsafe_showcase:
            findings.append({"severity": "ERROR", "message": f"Showcase commands are not read-only: {', '.join(unsafe_showcase)}"})
        else:
            findings.append({"severity": "OK", "message": "All Showcase commands are read-only with mutates=none."})
        registry_report = command_registry_doctor()
        findings.append(
            {
                "severity": "OK" if registry_report["status"] == "OK" else "ERROR",
                "message": f"Command Registry Doctor status: {registry_report['status']}.",
            }
        )
        invalid_runner = [
            command
            for command in ACTIVE_READONLY_ALLOWLIST
            if command not in by_prefix
            or not by_prefix[command].read_only
            or by_prefix[command].mutates != "none"
            or classify_command(command).policy_class != "auto_allowed"
        ]
        if len(ACTIVE_READONLY_ALLOWLIST) != 4 or invalid_runner:
            findings.append({"severity": "ERROR", "message": "Read-only runner allowlist drifted from its four-command safety contract."})
        else:
            findings.append({"severity": "OK", "message": "Runner remains exactly four read-only, mutates=none, auto-allowed commands."})
        persistent_surface = [
            item.prefix
            for item in COMMAND_REGISTRY
            if item.prefix.startswith(_FORBIDDEN_EXPERIENCE_PREFIXES)
        ]
        if persistent_surface:
            findings.append({"severity": "ERROR", "message": f"Forbidden persistent Experience commands exposed: {', '.join(persistent_surface)}"})
        else:
            findings.append({"severity": "OK", "message": "Experience persistence, export, apply, promotion, and backfill commands remain absent."})
        if state["context_state"] != "disabled":
            findings.append({"severity": "WARN", "message": "Context Injection is enabled; disable it before the supervised Experience demo."})
        else:
            findings.append({"severity": "OK", "message": "Context Injection is disabled."})
        if state["unknown_warnings"] or state["blocker_count"]:
            findings.append({"severity": "WARN", "message": "Unknown warnings or blockers should be inspected before recording the demo."})
        else:
            findings.append({"severity": "OK", "message": "Unknown warnings and blockers are zero."})
        status = "ERROR" if any(item["severity"] == "ERROR" for item in findings) else "WARN" if any(item["severity"] == "WARN" for item in findings) else "OK"
        return {"status": status, "findings": findings}

    def format_doctor(self) -> str:
        report = self.doctor_report()
        return "\n".join(
            [
                "Proto-Mind Contest Showcase Doctor v1",
                f"Status: {report['status']}",
                "Checks:",
                *[f"- [{item['severity']}] {item['message']}" for item in report["findings"]],
                "",
                "Doctor boundary:",
                "- Read-only diagnostics only; no demo step, command, consent, snapshot, export, repair, store mutation, or external action occurred.",
            ]
        )


def _latest_turn_episode(events: tuple[dict[str, Any], ...]) -> dict[str, Any] | None:
    if not events:
        return None
    try:
        episodes = CognitiveTurnProjector(events).project()
    except CognitiveTurnProjectionError:
        return None
    if not episodes:
        return None
    episode = episodes[-1]
    return {
        "turn_id": episode.turn_id,
        "intent": episode.interpret.get("query_type", "unknown"),
        "selected_count": episode.recall.get("selected_count", 0),
        "should_store": episode.memory_decision.get("should_store"),
        "grounding_status": episode.verify.get("grounding_status", "unavailable"),
    }


def _best_task(tasks: list[dict[str, Any]], *, focused_goal_id: str | None) -> dict[str, Any] | None:
    if not tasks:
        return None

    def key(item: dict[str, Any]) -> tuple[int, int, int, str]:
        focused_rank = 0 if focused_goal_id and item.get("goal_id") == focused_goal_id else 1
        status_rank = 0 if item.get("status") == "in_progress" else 1
        return (
            status_rank,
            focused_rank,
            PRIORITY_RANK.get(str(item.get("priority") or "normal"), 1),
            str(item.get("created_at") or ""),
        )

    return sorted(tasks, key=key)[0]


def _goal_line(goal: dict[str, Any] | None) -> str:
    if not goal:
        return "none"
    return f"{goal.get('id')} | {goal.get('title')} | priority={goal.get('priority', 'normal')}"


def _task_line(task: dict[str, Any] | None) -> str:
    if not task:
        return "none"
    return f"{task.get('id')} | {task.get('title')} | {task.get('status')} | priority={task.get('priority', 'normal')}"
