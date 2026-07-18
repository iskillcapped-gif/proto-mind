from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from proto_mind.command_registry import COMMAND_REGISTRY
from proto_mind.daily_layer import _read_test_baseline
from proto_mind.memory_store import MemoryStore
from proto_mind.prechange_layer import PreChangeRitual
from proto_mind.session_rituals import read_ledger_section_lead


FOCUS_COMMANDS = (
    "/focus status",
    "/focus plan",
    "/focus checklist",
    "/focus doctor",
    "/focus handoff",
)
_DEPENDENCY_COMMANDS = (
    "/prechange status",
    "/prechange checklist",
    "/prechange doctor",
    "/agenda status",
    "/agenda next",
    "/session end-summary",
    "/session handoff-brief",
    "/milestone next",
    "/warnings unknown",
    "/warnings accepted",
    "/exports doctor",
)


def format_focus_command(command: str, *, project_root: Path, memory_store: MemoryStore) -> str | None:
    normalized = " ".join(command.strip().lower().split())
    if not normalized.startswith("/focus"):
        return None
    focus = FocusMode(project_root=project_root, memory_store=memory_store)
    if normalized == "/focus status":
        return focus.format_status()
    if normalized == "/focus plan":
        return focus.format_plan()
    if normalized == "/focus checklist":
        return focus.format_checklist()
    if normalized == "/focus doctor":
        return focus.format_doctor()
    if normalized == "/focus handoff":
        return focus.format_handoff()
    return "Usage:\n" + "\n".join(f"  {item}" for item in FOCUS_COMMANDS)


class FocusMode:
    def __init__(self, *, project_root: Path, memory_store: MemoryStore) -> None:
        self.project_root = project_root
        self.memory_store = memory_store
        self.prechange = PreChangeRitual(project_root=project_root, memory_store=memory_store)

    def read_state(self) -> dict[str, Any]:
        state = self.prechange.read_state()
        if state["unknown"] or state["blocker_count"]:
            readiness = "BLOCKED"
        elif state["accepted"] or state["system_status"] != "OK" or state["context_state"] == "enabled":
            readiness = "WARN"
        else:
            readiness = "OK"
        planning_safe = (
            not state["unknown"]
            and state["blocker_count"] == 0
            and state["context_state"] == "disabled"
            and state["agenda_doctor_status"] != "ERROR"
            and state["export_doctor_status"] != "ERROR"
        )
        return {**state, "focus_readiness": readiness, "focus_planning_safe": planning_safe}

    def format_status(self) -> str:
        state = self.read_state()
        categories = Counter(spec.category for spec in COMMAND_REGISTRY)
        return "\n".join(
            [
                "Focus Mode Status",
                f"Status: {state['focus_readiness']}",
                f"project_root: {self.project_root}",
                f"command_registry: commands={len(COMMAND_REGISTRY)} categories={len(categories)}",
                f"context_injection: {state['context_state']}",
                f"prechange_readiness: {state['readiness']}",
                f"agenda_state: {state['overall']}",
                f"accepted_known_warnings: {len(state['accepted'])}",
                f"unknown_warnings: {len(state['unknown'])}",
                f"blockers: {state['blocker_count']}",
                f"focus_planning_safe: {str(state['focus_planning_safe']).lower()}",
                "",
                "Planning-only reminder:",
                "- Focus Mode does not execute commands, persist a session, choose work autonomously, or modify state.",
            ]
        )

    def format_plan(self) -> str:
        state = self.read_state()
        if state["unknown"]:
            objective = "Understand unknown warnings before selecting implementation work."
            focus_area = "Warning inspection and operator classification"
            steps = [
                ("Run /warnings unknown manually.", "Inspect only; do not repair or accept automatically."),
                ("Review /warnings inspect and source doctors.", "Keep existing source findings visible."),
                ("Decide whether to stop, document, or create a separate reviewed migration task.", "No mutation in this focus session."),
                ("Finish with /session end-summary and /session handoff-brief.", "Reports only; no files or clipboard actions."),
            ]
        else:
            objective = "Prepare and complete one small, explicitly scoped Proto-Mind milestone safely."
            focus_area = "Pre-change review, one focused task, verification, and handoff"
            steps = [
                ("Run /prechange checklist manually.", "Confirm Rule 0 and all write boundaries before coding."),
                ("Run /milestone next and select one milestone manually.", "Selection remains an operator decision."),
                ("Generate /prechange handoff and give Codex one small task.", "No automatic planning or command dispatch."),
                ("Implement only the allowed files and behavior.", "Do not expand scope or mutate runtime stores."),
                ("Run scripts/which_python.sh, scripts/run_tests.sh, and compileall.", "Verification is explicit and reviewed by the operator."),
                ("Run task-specific manual smoke and compare data/exports SHA-256 when runtime must remain read-only.", "Stop if unexpected mutation is detected."),
                ("Run /acceptance checklist, choose a human decision, review /baseline checklist, then finish with /session end-summary, /closure handoff, and /session handoff-brief if needed.", "Review guidance only; no decision, baseline, closure, or summary is persisted."),
            ]
        lines = [
            "Focused Work Session Plan",
            f"Status: {state['focus_readiness']}",
            f"Session objective: {objective}",
            f"Suggested focus area: {focus_area}",
            "",
            "Ordered manual steps:",
        ]
        for index, (action, safety) in enumerate(steps, start=1):
            lines.extend([f"{index}. {action}", f"   safety: {safety}"])
        lines.extend(
            [
                "",
                "Safety constraints:",
                "- No autonomous execution, background work, LLM planning, hidden writes, auto-apply, repair, cleanup, migration, backup, or snapshot creation.",
                "- Context Injection must remain disabled unless a separate explicit task changes that policy.",
                "",
                "Verification commands:",
                "- scripts/which_python.sh",
                "- scripts/run_tests.sh",
                "- /opt/homebrew/opt/python@3.11/bin/python3.11 -m compileall proto_mind",
                "",
                "Done criteria:",
                "- One scoped objective completed; tests and compile checks pass; manual smoke is recorded; forbidden stores remain unchanged; limitations are reported.",
                "",
                "Suggested end-of-session commands:",
                "- /acceptance checklist",
                "- /acceptance decision-guide",
                "- /baseline status",
                "- /baseline checklist",
                "- /session end-summary",
                "- /closure handoff",
                "- /session handoff-brief",
                "",
                "No automatic execution:",
                "- This plan was generated locally and was not persisted; none of its commands or steps were run.",
            ]
        )
        return "\n".join(lines)

    def format_checklist(self) -> str:
        return "\n".join(
            [
                "Focused Session Manual Checklist",
                "1. Define one concrete session objective.",
                "2. Confirm allowed writes.",
                "3. Confirm forbidden writes.",
                "4. Confirm Rule 0 backup/checkpoint exists for this task.",
                "5. Run /warnings unknown and stop if findings exist.",
                "6. Run /prechange status and review readiness.",
                "7. Give Codex one small task with explicit scope and constraints.",
                "8. Verify with scripts/which_python.sh, scripts/run_tests.sh, and Python 3.11 compileall.",
                "9. Run task-specific manual smoke commands.",
                "10. For read-only runtime work, compare proto_mind/data and proto_mind/exports SHA-256 with the Rule 0 checkpoint.",
                "11. Summarize the result, limitations, and explicit acceptance decision.",
                "",
                "Checklist behavior:",
                "- Printed only; no backup, command, test, hash, state, file, or acceptance decision was created.",
            ]
        )

    def format_doctor(self) -> str:
        report = self.doctor_report()
        lines = ["Focus Mode Doctor", f"Status: {report['status']}", "", "Checks:"]
        lines.extend(f"- [{item['severity']}] {item['message']}" for item in report["findings"])
        lines.extend(
            [
                "",
                "Mutation policy:",
                "- Read-only diagnostics only; no focus/session state, command, backup, snapshot, repair, cleanup, migration, or write occurred.",
            ]
        )
        return "\n".join(lines)

    def doctor_report(self) -> dict[str, Any]:
        findings: list[dict[str, str]] = []
        registry = {spec.prefix: spec for spec in COMMAND_REGISTRY}
        missing = [command for command in FOCUS_COMMANDS if command not in registry]
        findings.append(
            {"severity": "ERROR", "message": f"Focus commands missing from Registry: {', '.join(missing)}"}
            if missing
            else {"severity": "OK", "message": "All focus commands are registered."}
        )
        unsafe = [
            command
            for command in FOCUS_COMMANDS
            if command in registry and (not registry[command].read_only or registry[command].mutates != "none")
        ]
        findings.append(
            {"severity": "ERROR", "message": f"Focus commands expose mutation: {', '.join(unsafe)}"}
            if unsafe
            else {"severity": "OK", "message": "Focus commands are read-only with mutates=none."}
        )
        unavailable = [command for command in _DEPENDENCY_COMMANDS if command not in registry]
        findings.append(
            {"severity": "WARN", "message": f"Optional Focus dependencies unavailable: {', '.join(unavailable)}"}
            if unavailable
            else {"severity": "OK", "message": "Pre-Change, Agenda, Session, Milestone, Warning, and Export helpers are reachable."}
        )
        try:
            state = self.read_state()
        except Exception as exc:
            findings.append({"severity": "ERROR", "message": f"Focus readiness could not be computed: {exc}"})
            state = None
        else:
            findings.append(
                {
                    "severity": "OK",
                    "message": f"Warning readiness is computable: accepted={len(state['accepted'])}, unknown={len(state['unknown'])}, blockers={state['blocker_count']}.",
                }
            )
            if state["unknown"] or state["blocker_count"]:
                findings.append({"severity": "BLOCKED", "message": "Unknown warnings or blockers prevent safe focus planning."})
            if state["context_state"] == "enabled":
                findings.append({"severity": "WARN", "message": "Context Injection is explicitly enabled; Focus Mode did not change it."})
            else:
                findings.append({"severity": "OK", "message": "Context Injection is disabled."})
        dangerous = [
            spec.prefix
            for spec in COMMAND_REGISTRY
            if spec.category == "focus" and (spec.risk == "high" or not spec.read_only or spec.mutates != "none")
        ]
        findings.append(
            {"severity": "ERROR", "message": f"Dangerous Focus actions exposed: {', '.join(dangerous)}"}
            if dangerous
            else {"severity": "OK", "message": "No execution, persistence, backup, snapshot, repair, cleanup, migration, deletion, move, or compression action is exposed."}
        )
        if any(item["severity"] == "ERROR" for item in findings):
            status = "ERROR"
        elif any(item["severity"] == "BLOCKED" for item in findings):
            status = "BLOCKED"
        elif any(item["severity"] == "WARN" for item in findings):
            status = "WARN"
        else:
            status = "OK"
        return {"status": status, "findings": findings}

    def format_handoff(self) -> str:
        state = self.read_state()
        categories = Counter(spec.category for spec in COMMAND_REGISTRY)
        milestone = read_ledger_section_lead(self.project_root, "Last Completed Milestone") or "not detected"
        return "\n".join(
            [
                "Proto-Mind Focused Session Handoff",
                f"Project: {self.project_root}",
                f"Current milestone: {milestone}",
                f"Registry baseline: {len(COMMAND_REGISTRY)} commands across {len(categories)} categories",
                f"Test baseline: {_read_test_baseline(self.project_root)}",
                f"Focus readiness: {state['focus_readiness']}",
                f"Warning baseline: accepted={len(state['accepted'])}, unknown={len(state['unknown'])}, blockers={state['blocker_count']}",
                f"Context Injection: {state['context_state']}",
                "",
                "Rule 0:",
                "- Create a backup/checkpoint before changes with scripts/run_cli.sh and /memory backup.",
                "",
                "Focus-mode safety constraints:",
                "- Choose one small objective; state allowed/forbidden writes; no autonomous execution, hidden mutation, repair, cleanup, migration, backup, or snapshot creation.",
                "",
                "Suggested next milestone:",
                "- <operator-selected milestone after /milestone next and /prechange checklist>",
                "",
                "Verification:",
                "- scripts/which_python.sh",
                "- scripts/run_tests.sh",
                "- /opt/homebrew/opt/python@3.11/bin/python3.11 -m compileall proto_mind",
                "",
                "Manual smoke:",
                "- Define task-specific commands and expected mutation/read-only behavior.",
                "",
                "Runtime data integrity:",
                "- For read-only runtime tasks, compare proto_mind/data and proto_mind/exports SHA-256 against the Rule 0 checkpoint.",
                "",
                "Handoff behavior:",
                "- Copyable text only; no file, clipboard, command, model, external call, or focus state was created.",
            ]
        )
