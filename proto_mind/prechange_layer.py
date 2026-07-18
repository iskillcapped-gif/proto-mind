from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from proto_mind.agenda_layer import OperatorAgenda
from proto_mind.command_registry import COMMAND_REGISTRY
from proto_mind.daily_layer import _latest_line, _read_test_baseline
from proto_mind.export_retention import ExportRetention
from proto_mind.memory_store import MemoryStore
from proto_mind.session_rituals import read_ledger_section_lead


PRECHANGE_COMMANDS = (
    "/prechange status",
    "/prechange checklist",
    "/prechange doctor",
    "/prechange handoff",
)
_DEPENDENCY_COMMANDS = (
    "/agenda status",
    "/agenda next",
    "/agenda doctor",
    "/warnings accepted",
    "/warnings unknown",
    "/warnings doctor",
    "/exports doctor",
    "/proto snapshot-status",
    "/proto snapshot-diff-status",
    "/context injection status",
)


def format_prechange_command(command: str, *, project_root: Path, memory_store: MemoryStore) -> str | None:
    normalized = " ".join(command.strip().lower().split())
    if not normalized.startswith("/prechange"):
        return None
    ritual = PreChangeRitual(project_root=project_root, memory_store=memory_store)
    if normalized == "/prechange status":
        return ritual.format_status()
    if normalized == "/prechange checklist":
        return ritual.format_checklist()
    if normalized == "/prechange doctor":
        return ritual.format_doctor()
    if normalized == "/prechange handoff":
        return ritual.format_handoff()
    return "Usage:\n" + "\n".join(f"  {item}" for item in PRECHANGE_COMMANDS)


class PreChangeRitual:
    def __init__(self, *, project_root: Path, memory_store: MemoryStore) -> None:
        self.project_root = project_root
        self.memory_store = memory_store
        self.agenda = OperatorAgenda(project_root=project_root, memory_store=memory_store)
        self.exports = ExportRetention.from_project_root(project_root)

    def read_state(self) -> dict[str, Any]:
        agenda_state = self.agenda.read_state()
        agenda_doctor = self.agenda.doctor_report()
        export_doctor = self.exports.doctor_report()
        unknown_count = len(agenda_state["unknown"])
        blocker_count = agenda_state["blocker_count"]
        accepted_count = len(agenda_state["accepted"])
        if unknown_count or blocker_count:
            readiness = "BLOCKED"
        elif accepted_count or agenda_state["system_status"] != "OK" or agenda_state["context_state"] == "enabled":
            readiness = "WARN"
        else:
            readiness = "OK"
        safe_to_begin = (
            unknown_count == 0
            and blocker_count == 0
            and agenda_state["context_state"] == "disabled"
            and agenda_doctor["status"] != "ERROR"
            and export_doctor["status"] != "ERROR"
        )
        return {
            **agenda_state,
            "readiness": readiness,
            "safe_to_begin": safe_to_begin,
            "agenda_doctor_status": agenda_doctor["status"],
            "export_doctor_status": export_doctor["status"],
        }

    def format_status(self) -> str:
        state = self.read_state()
        categories = Counter(spec.category for spec in COMMAND_REGISTRY)
        return "\n".join(
            [
                "Pre-Change Readiness",
                f"Status: {state['readiness']}",
                f"project_root: {self.project_root}",
                f"command_registry: commands={len(COMMAND_REGISTRY)} categories={len(categories)}",
                f"context_injection: {state['context_state']}",
                f"accepted_known_warnings: {len(state['accepted'])}",
                f"unknown_warnings: {len(state['unknown'])}",
                f"blockers: {state['blocker_count']}",
                f"agenda_doctor: {state['agenda_doctor_status']}",
                f"exports_doctor: {state['export_doctor_status']}",
                f"latest_snapshot: {_latest_line(state['latest_snapshot'])}",
                f"latest_snapshot_diff: {_latest_line(state['latest_diff'])}",
                f"safe_to_begin_manual_change: {str(state['safe_to_begin']).lower()}",
                "",
                "Rule 0:",
                "- A manual backup/checkpoint is required before every change, even when readiness is OK or WARN.",
                "",
                "Mutation policy:",
                "- Readiness inspection only; no backup, snapshot, command, store, export, context, or checklist state was created or changed.",
            ]
        )

    def format_checklist(self) -> str:
        return "\n".join(
            [
                "Pre-Change Manual Checklist",
                "",
                "Before giving Codex a task:",
                "1. Rule 0: run scripts/run_cli.sh and create /memory backup manually.",
                "2. Run /warnings unknown and stop for review if the count is greater than zero.",
                "3. Run /agenda status or /agenda next.",
                "4. Run /exports doctor.",
                "5. Run /proto snapshot-diff-status and review existing snapshot/diff state.",
                "6. Confirm /context injection status reports disabled.",
                "7. Define allowed writes and forbidden writes explicitly in the task brief.",
                "8. Define verification commands and manual smoke expectations.",
                "",
                "After implementation:",
                "9. Run scripts/which_python.sh.",
                "10. Run scripts/run_tests.sh.",
                "11. Run python -m compileall proto_mind with the selected Python 3.11 interpreter.",
                "12. For read-only runtime tasks, compare SHA-256 for all files under proto_mind/data and proto_mind/exports against the Rule 0 checkpoint.",
                "",
                "No automatic execution:",
                "- This checklist did not run tests, commands, backups, snapshots, hashes, repairs, or cleanup actions.",
            ]
        )

    def format_doctor(self) -> str:
        report = self.doctor_report()
        lines = ["Pre-Change Ritual Doctor", f"Status: {report['status']}", "", "Checks:"]
        lines.extend(f"- [{item['severity']}] {item['message']}" for item in report["findings"])
        lines.extend(
            [
                "",
                "Mutation policy:",
                "- Read-only diagnostics only; no command, backup, snapshot, repair, cleanup, migration, or write occurred.",
            ]
        )
        return "\n".join(lines)

    def doctor_report(self) -> dict[str, Any]:
        findings: list[dict[str, str]] = []
        registry = {spec.prefix: spec for spec in COMMAND_REGISTRY}
        missing = [command for command in PRECHANGE_COMMANDS if command not in registry]
        findings.append(
            {"severity": "ERROR", "message": f"Pre-change commands missing from Registry: {', '.join(missing)}"}
            if missing
            else {"severity": "OK", "message": "All pre-change commands are registered."}
        )
        unsafe = [
            command
            for command in PRECHANGE_COMMANDS
            if command in registry and (not registry[command].read_only or registry[command].mutates != "none")
        ]
        findings.append(
            {"severity": "ERROR", "message": f"Pre-change commands expose mutation: {', '.join(unsafe)}"}
            if unsafe
            else {"severity": "OK", "message": "Pre-change commands are read-only with mutates=none."}
        )
        unavailable = [command for command in _DEPENDENCY_COMMANDS if command not in registry]
        findings.append(
            {"severity": "WARN", "message": f"Optional pre-change dependencies unavailable: {', '.join(unavailable)}"}
            if unavailable
            else {"severity": "OK", "message": "Agenda, Warning, Export, Snapshot, and Context helpers are reachable."}
        )
        if self.agenda.warning_inspector.accepted_ledger_path.is_file():
            findings.append({"severity": "OK", "message": "Accepted-known warnings ledger is reachable."})
        else:
            findings.append({"severity": "WARN", "message": "Accepted-known warnings ledger is missing."})
        try:
            state = self.read_state()
        except Exception as exc:
            findings.append({"severity": "ERROR", "message": f"Pre-change state could not be computed: {exc}"})
            state = None
        else:
            findings.append(
                {
                    "severity": "OK",
                    "message": f"Warning readiness is computable: accepted={len(state['accepted'])}, unknown={len(state['unknown'])}, blockers={state['blocker_count']}.",
                }
            )
            if state["unknown"] or state["blocker_count"]:
                findings.append({"severity": "BLOCKED", "message": "Unknown warnings or blockers require manual inspection before changes."})
            if state["context_state"] == "enabled":
                findings.append({"severity": "WARN", "message": "Context Injection is explicitly enabled; Pre-Change Ritual did not change it."})
            else:
                findings.append({"severity": "OK", "message": "Context Injection is disabled."})
        dangerous = [
            spec.prefix
            for spec in COMMAND_REGISTRY
            if spec.category == "prechange" and (spec.risk == "high" or not spec.read_only or spec.mutates != "none")
        ]
        findings.append(
            {"severity": "ERROR", "message": f"Dangerous pre-change actions exposed: {', '.join(dangerous)}"}
            if dangerous
            else {"severity": "OK", "message": "No execution, backup, snapshot, repair, cleanup, migration, deletion, move, or compression action is exposed."}
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
                "Proto-Mind Pre-Change Task Header",
                f"Project: {self.project_root}",
                f"Current milestone: {milestone}",
                f"Registry baseline: {len(COMMAND_REGISTRY)} commands across {len(categories)} categories",
                f"Test baseline: {_read_test_baseline(self.project_root)}",
                f"Warning baseline: accepted={len(state['accepted'])}, unknown={len(state['unknown'])}, blockers={state['blocker_count']}",
                f"Context Injection: {state['context_state']}",
                "",
                "Rule 0:",
                "- Before changes, run scripts/run_cli.sh and create /memory backup manually.",
                "",
                "Safety requirements:",
                "- State allowed and forbidden writes explicitly; do not add autonomous execution, hidden mutation, repair, cleanup, or Context Injection changes unless separately requested.",
                "- Suggestions and inspection commands must remain manual unless the task explicitly authorizes otherwise.",
                "",
                "Verification:",
                "- scripts/which_python.sh",
                "- scripts/run_tests.sh",
                "- /opt/homebrew/opt/python@3.11/bin/python3.11 -m compileall proto_mind",
                "",
                "Manual smoke:",
                "- Define task-specific commands and expected read-only/mutation behavior before implementation.",
                "",
                "Runtime data integrity:",
                "- For read-only runtime tasks, compare proto_mind/data and proto_mind/exports SHA-256 against the Rule 0 checkpoint.",
                "",
                "Handoff safety:",
                "- Copyable text only; no file, clipboard, backup, snapshot, command, model, or external call was produced by this command.",
            ]
        )
