from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from proto_mind.command_registry import COMMAND_REGISTRY
from proto_mind.memory_store import MemoryStore
from proto_mind.milestone_layer import MilestoneTracker
from proto_mind.session_rituals import SessionRituals
from proto_mind.warning_inspector import LegacyWarningInspector


AGENDA_COMMANDS = (
    "/agenda status",
    "/agenda next",
    "/agenda list",
    "/agenda doctor",
)
_DEPENDENCY_COMMANDS = (
    "/daily doctor",
    "/session start-brief",
    "/session handoff-brief",
    "/milestone next",
    "/milestone doctor",
    "/warnings accepted",
    "/warnings unknown",
    "/warnings doctor",
    "/exports doctor",
    "/proto snapshot-status",
    "/proto snapshot-diff-status",
    "/proto snapshot-diff-latest",
)


def format_agenda_command(command: str, *, project_root: Path, memory_store: MemoryStore) -> str | None:
    normalized = " ".join(command.strip().lower().split())
    if not normalized.startswith("/agenda"):
        return None
    agenda = OperatorAgenda(project_root=project_root, memory_store=memory_store)
    if normalized == "/agenda status":
        return agenda.format_status()
    if normalized == "/agenda next":
        return agenda.format_next()
    if normalized == "/agenda list":
        return agenda.format_list()
    if normalized == "/agenda doctor":
        return agenda.format_doctor()
    return "Usage:\n" + "\n".join(f"  {item}" for item in AGENDA_COMMANDS)


class OperatorAgenda:
    def __init__(self, *, project_root: Path, memory_store: MemoryStore) -> None:
        self.project_root = project_root
        self.memory_store = memory_store
        self.session = SessionRituals(project_root=project_root, memory_store=memory_store)
        self.milestones = MilestoneTracker(project_root=project_root, memory_store=memory_store)
        self.warning_inspector = LegacyWarningInspector(project_root=project_root, memory_store=memory_store)

    def read_state(self) -> dict[str, Any]:
        session_state = self.session.read_state()
        warnings = self.warning_inspector.warnings()
        accepted = [item for item in warnings if item["accepted_known"]]
        unknown = [item for item in warnings if not item["accepted_known"]]
        blocker_count = sum(1 for item in unknown if item["operator_severity"] == "BLOCKER")
        if blocker_count:
            overall = "BLOCKED"
        elif unknown or session_state["system_status"] != "OK" or session_state["context_state"] == "enabled":
            overall = "WARN"
        else:
            overall = "OK"
        return {
            **session_state,
            "warnings": warnings,
            "accepted": accepted,
            "unknown": unknown,
            "blocker_count": blocker_count,
            "overall": overall,
        }

    def build_queue(self) -> list[dict[str, str]]:
        state = self.read_state()
        items: list[dict[str, str]] = []
        if state["unknown"]:
            items.append(
                _item(
                    "P0" if state["blocker_count"] else "P1",
                    "Inspect unknown warnings before accepting new work.",
                    f"{len(state['unknown'])} finding(s) do not match the accepted-known ledger.",
                    "Inspection only; do not repair or acknowledge findings automatically.",
                    "/warnings unknown",
                )
            )
        elif state["accepted"] and state["system_status"] != "OK":
            items.append(
                _item(
                    "P1",
                    "Continue milestone review with the accepted-known warning baseline visible.",
                    f"All {len(state['accepted'])} current findings are narrowly accepted and unknown=0.",
                    "Accepted means documented, not suppressed or repaired; runtime gates remain protective.",
                    "/milestone next",
                )
            )
        elif state["system_status"] != "OK":
            items.append(
                _item(
                    "P0",
                    "Inspect current system warnings before selecting a milestone.",
                    f"Current system status is {state['system_status']}.",
                    "Read doctors only; make no automatic changes.",
                    "/proto warnings",
                )
            )

        latest_snapshot = state["latest_snapshot"]
        latest_diff = state["latest_diff"]
        if latest_snapshot is None:
            items.append(
                _item(
                    "P1",
                    "Review snapshot status and decide manually whether to create one.",
                    "No exported Proto snapshot is currently detected.",
                    "Status is read-only; snapshot export remains an explicit operator action.",
                    "/proto snapshot-status",
                )
            )
        elif latest_diff is None:
            items.append(
                _item(
                    "P1",
                    "Review snapshot history before the next milestone.",
                    "No exported snapshot diff is currently detected.",
                    "Do not create or compare exports automatically.",
                    "/proto snapshot-diff-status",
                )
            )
        else:
            diff_status = str(latest_diff.get("status") or "unknown").upper()
            priority = "P1" if diff_status not in {"OK", "NO STRUCTURAL CHANGES"} else "P2"
            items.append(
                _item(
                    priority,
                    "Review the latest snapshot diff manually.",
                    f"Latest detected diff status is {diff_status}.",
                    "Review only; no snapshot or diff export is created by Agenda.",
                    "/proto snapshot-diff-latest",
                )
            )

        focus_item = _item(
            "P1",
            "Open a planning-only focused work session before selecting implementation details.",
            "Focus Mode turns the inspected baseline into one small manual work plan.",
            "Planning text only; no commands, state, backups, or snapshots are created.",
            "/focus plan",
        )
        items.insert(1 if state["unknown"] else 0, focus_item)
        prechange_item = _item(
            "P1",
            "Complete the manual pre-change ritual before the next code or documentation change.",
            "The next milestone should begin from an inspected and checkpointed baseline.",
            "Checklist only; Agenda does not run backups, snapshots, tests, or hashes.",
            "/prechange checklist",
        )
        items.insert(2 if state["unknown"] else 1, prechange_item)
        items.append(
            _item(
                "P1",
                "Run the full test suite before accepting another milestone.",
                "Agenda does not execute tests and the live code baseline should be verified explicitly.",
                "Run manually in the project shell; review failures before any further work.",
                "scripts/run_tests.sh",
            )
        )
        if not any(item["command"] == "/milestone next" for item in items):
            items.append(
                _item(
                    "P2",
                    "Review the next planned milestone.",
                    "Roadmap selection remains an explicit operator decision.",
                    "Suggestion only; no milestone state is persisted or advanced.",
                    "/milestone next",
                )
            )
        items.append(
            _item(
                "P2",
                "Prepare a handoff brief if the work session is ending.",
                "A copyable live summary can preserve operator context without writing a handoff file.",
                "The command prints text only and does not touch the clipboard.",
                "/session handoff-brief",
            )
        )
        return items[:7]

    def format_status(self) -> str:
        state = self.read_state()
        registry = {spec.prefix for spec in COMMAND_REGISTRY}
        categories = Counter(spec.category for spec in COMMAND_REGISTRY)
        availability = {
            "daily": "/daily doctor" in registry,
            "session": "/session handoff-brief" in registry,
            "milestone": "/milestone next" in registry,
            "warnings": "/warnings unknown" in registry,
        }
        safe_to_suggest = all(availability.values()) and state["blocker_count"] == 0
        return "\n".join(
            [
                "Operator Agenda Status",
                f"Status: {state['overall']}",
                f"project_root: {self.project_root}",
                f"command_registry: commands={len(COMMAND_REGISTRY)} categories={len(categories)}",
                f"helper_availability: {', '.join(f'{name}={str(value).lower()}' for name, value in availability.items())}",
                f"accepted_known_warnings: {len(state['accepted'])}",
                f"unknown_warnings: {len(state['unknown'])}",
                f"blockers: {state['blocker_count']}",
                f"can_safely_suggest_next_work: {str(safe_to_suggest).lower()}",
                f"context_injection: {state['context_state']}",
                "",
                "Mutation policy:",
                "- Live readiness only; no agenda, task, warning, snapshot, context, queue, store, or export was changed.",
            ]
        )

    def format_next(self) -> str:
        state = self.read_state()
        item = self.build_queue()[0]
        return "\n".join(
            [
                "Operator Agenda Next",
                f"Status: {state['overall']}",
                f"priority: {item['priority']}",
                f"action: {item['action']}",
                f"reason: {item['reason']}",
                f"safety: {item['safety']}",
                f"manual_command: {item['command']}",
                "",
                "No automatic execution:",
                "- The command was not run and no agenda/task state was persisted.",
            ]
        )

    def format_list(self) -> str:
        items = self.build_queue()
        lines = ["Operator Agenda", "Mode: live read-only queue", f"Items: {len(items)}", ""]
        for index, item in enumerate(items, start=1):
            lines.extend(
                [
                    f"{index}. [{item['priority']}] {item['action']}",
                    f"   reason: {item['reason']}",
                    f"   safety: {item['safety']}",
                    f"   manual command: {item['command']}",
                ]
            )
        lines.extend(
            [
                "",
                "Mutation policy:",
                "- Generated live and not persisted; no item or related command was executed.",
            ]
        )
        return "\n".join(lines)

    def format_doctor(self) -> str:
        report = self.doctor_report()
        lines = ["Operator Agenda Doctor", f"Status: {report['status']}", "", "Checks:"]
        lines.extend(f"- [{item['severity']}] {item['message']}" for item in report["findings"])
        lines.extend(
            [
                "",
                "Mutation policy:",
                "- Read-only diagnostics only; no agenda, command, repair, cleanup, migration, or write occurred.",
            ]
        )
        return "\n".join(lines)

    def doctor_report(self) -> dict[str, Any]:
        findings: list[dict[str, str]] = []
        registry = {spec.prefix: spec for spec in COMMAND_REGISTRY}
        missing = [command for command in AGENDA_COMMANDS if command not in registry]
        findings.append(
            {"severity": "ERROR", "message": f"Agenda commands missing from Registry: {', '.join(missing)}"}
            if missing
            else {"severity": "OK", "message": "All agenda commands are registered."}
        )
        unsafe = [
            command
            for command in AGENDA_COMMANDS
            if command in registry and (not registry[command].read_only or registry[command].mutates != "none")
        ]
        findings.append(
            {"severity": "ERROR", "message": f"Agenda commands expose mutation: {', '.join(unsafe)}"}
            if unsafe
            else {"severity": "OK", "message": "Agenda commands are read-only with mutates=none."}
        )
        unavailable = [command for command in _DEPENDENCY_COMMANDS if command not in registry]
        findings.append(
            {"severity": "WARN", "message": f"Optional Agenda dependencies unavailable: {', '.join(unavailable)}"}
            if unavailable
            else {"severity": "OK", "message": "Daily, Session, Milestone, Warning, Export, and Snapshot helpers are reachable."}
        )
        if self.warning_inspector.accepted_ledger_path.is_file():
            findings.append({"severity": "OK", "message": "Accepted-known warnings ledger is reachable."})
        else:
            findings.append({"severity": "WARN", "message": "Accepted-known warnings ledger is missing."})
        try:
            state = self.read_state()
        except Exception as exc:
            findings.append({"severity": "ERROR", "message": f"Agenda state could not be computed: {exc}"})
            state = None
        else:
            findings.append(
                {
                    "severity": "OK",
                    "message": f"Warning classification is available: accepted={len(state['accepted'])}, unknown={len(state['unknown'])}.",
                }
            )
            if state["context_state"] == "enabled":
                findings.append({"severity": "WARN", "message": "Context Injection is explicitly enabled; Agenda did not change it."})
            else:
                findings.append({"severity": "OK", "message": "Context Injection is disabled."})
        dangerous = [
            spec.prefix
            for spec in COMMAND_REGISTRY
            if spec.category == "agenda" and (spec.risk == "high" or not spec.read_only or spec.mutates != "none")
        ]
        findings.append(
            {"severity": "ERROR", "message": f"Dangerous Agenda actions exposed: {', '.join(dangerous)}"}
            if dangerous
            else {"severity": "OK", "message": "No execution, repair, cleanup, migration, deletion, move, or compression action is exposed."}
        )
        status = "ERROR" if any(item["severity"] == "ERROR" for item in findings) else "WARN" if any(item["severity"] == "WARN" for item in findings) else "OK"
        return {"status": status, "findings": findings}


def _item(priority: str, action: str, reason: str, safety: str, command: str) -> dict[str, str]:
    return {"priority": priority, "action": action, "reason": reason, "safety": safety, "command": command}
