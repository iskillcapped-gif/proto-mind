from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from proto_mind.command_registry import COMMAND_REGISTRY
from proto_mind.daily_layer import _read_test_baseline
from proto_mind.focus_layer import FocusMode
from proto_mind.memory_store import MemoryStore
from proto_mind.session_rituals import read_ledger_section_lead


ACCEPTANCE_COMMANDS = (
    "/acceptance status",
    "/acceptance checklist",
    "/acceptance criteria",
    "/acceptance decision-guide",
    "/acceptance doctor",
    "/acceptance handoff",
)
_DEPENDENCY_COMMANDS = (
    "/focus status",
    "/focus plan",
    "/focus doctor",
    "/prechange status",
    "/prechange doctor",
    "/agenda status",
    "/session end-summary",
    "/session handoff-brief",
    "/milestone next",
    "/warnings accepted",
    "/warnings unknown",
    "/exports doctor",
)


def format_acceptance_command(command: str, *, project_root: Path, memory_store: MemoryStore) -> str | None:
    normalized = " ".join(command.strip().lower().split())
    if not normalized.startswith("/acceptance"):
        return None
    review = AcceptanceReview(project_root=project_root, memory_store=memory_store)
    if normalized == "/acceptance status":
        return review.format_status()
    if normalized == "/acceptance checklist":
        return review.format_checklist()
    if normalized == "/acceptance criteria":
        return review.format_criteria()
    if normalized == "/acceptance decision-guide":
        return review.format_decision_guide()
    if normalized == "/acceptance doctor":
        return review.format_doctor()
    if normalized == "/acceptance handoff":
        return review.format_handoff()
    return "Usage:\n" + "\n".join(f"  {item}" for item in ACCEPTANCE_COMMANDS)


class AcceptanceReview:
    def __init__(self, *, project_root: Path, memory_store: MemoryStore) -> None:
        self.project_root = project_root
        self.memory_store = memory_store
        self.focus = FocusMode(project_root=project_root, memory_store=memory_store)

    def read_state(self) -> dict[str, Any]:
        state = self.focus.read_state()
        if state["unknown"] or state["blocker_count"]:
            readiness = "BLOCKED"
        elif state["accepted"] or state["system_status"] != "OK" or state["context_state"] == "enabled":
            readiness = "WARN"
        else:
            readiness = "OK"
        review_safe = (
            not state["unknown"]
            and state["blocker_count"] == 0
            and state["context_state"] == "disabled"
            and state["agenda_doctor_status"] != "ERROR"
            and state["export_doctor_status"] != "ERROR"
        )
        return {**state, "acceptance_readiness": readiness, "acceptance_review_safe": review_safe}

    def format_status(self) -> str:
        state = self.read_state()
        categories = Counter(spec.category for spec in COMMAND_REGISTRY)
        return "\n".join(
            [
                "Acceptance Review Status",
                f"Status: {state['acceptance_readiness']}",
                f"project_root: {self.project_root}",
                f"command_registry: commands={len(COMMAND_REGISTRY)} categories={len(categories)}",
                f"context_injection: {state['context_state']}",
                f"focus_readiness: {state['focus_readiness']}",
                f"prechange_readiness: {state['readiness']}",
                f"accepted_known_warnings: {len(state['accepted'])}",
                f"unknown_warnings: {len(state['unknown'])}",
                f"blockers: {state['blocker_count']}",
                f"acceptance_review_safe: {str(state['acceptance_review_safe']).lower()}",
                "",
                "Human decision only:",
                "- This layer guides review and never accepts, rejects, holds, parses, or mutates a result automatically.",
            ]
        )

    def format_checklist(self) -> str:
        return "\n".join(
            [
                "Acceptance Review Manual Checklist",
                "1. Confirm the Rule 0 backup path is present in the final report.",
                "2. Confirm all changed files are listed.",
                "3. Confirm added/changed commands and behavior are listed.",
                "4. Confirm Registry command/category counts are reported.",
                "5. Confirm scripts/which_python.sh result is reported.",
                "6. Confirm scripts/run_tests.sh result is reported.",
                "7. Confirm Python 3.11 compileall result is reported.",
                "8. Confirm required manual smoke commands and results are reported.",
                "9. Confirm Context Injection status is reported and unchanged unless explicitly authorized.",
                "10. For read-only runtime work, confirm proto_mind/data and proto_mind/exports SHA-256 comparison is reported.",
                "11. Confirm no dangerous execution, deletion, move, repair, cleanup, compression, or migration was introduced.",
                "12. Confirm limitations and known warnings are reported.",
                "13. Compare the implementation result against the original task brief and allowed/forbidden writes.",
                "14. Choose manually: ACCEPT, ACCEPT WITH NOTES, REJECT / NEEDS FIX, or HOLD / NEEDS MORE INFO.",
                "",
                "Checklist behavior:",
                "- Printed only; no report was parsed, no evidence was collected, and no acceptance decision was stored.",
            ]
        )

    def format_criteria(self) -> str:
        return "\n".join(
            [
                "Reusable Acceptance Criteria",
                "",
                "Hard blockers:",
                "- Missing Rule 0 backup/checkpoint evidence.",
                "- Tests fail without an explicit, credible explanation and operator approval.",
                "- Context Injection changed unexpectedly.",
                "- proto_mind/data or proto_mind/exports changed during a read-only runtime task.",
                "- Dangerous execution, deletion, move, repair, cleanup, compression, or migration was introduced.",
                "- Unknown warnings are greater than zero without explanation and review.",
                "- Command Registry or routing is broken.",
                "- PySide or tkinter imports are broken.",
                "",
                "Soft warnings:",
                "- Accepted-known legacy warnings remain visible.",
                "- Optional pytest is unavailable but the required unittest suite passes.",
                "- Minor documentation or output-format limitations are disclosed.",
                "",
                "Acceptable limitations:",
                "- Deterministic/manual-only behavior explicitly required by the task.",
                "- No persistence, automation, LLM reasoning, or UI controls when out of scope.",
                "",
                "Required verification evidence:",
                "- Rule 0 backup path; files changed; Registry counts; Python selector/imports; tests; compileall; manual smoke; Context Injection state; SHA-256 comparison when required.",
                "",
                "Safety invariants:",
                "- No unauthorized writes or commands; no hidden mutation; no autonomous acceptance; protective gates remain active.",
                "",
                "Documentation expectations:",
                "- README/architecture/Ledger updated when requested; limitations and known warnings stated clearly.",
                "",
                "Criteria behavior:",
                "- Framework only; no external result was inspected and no decision was made.",
            ]
        )

    def format_decision_guide(self) -> str:
        return "\n".join(
            [
                "Acceptance Decision Guide",
                "- ACCEPT: all required checks pass, evidence is complete, no hard blocker exists, and only accepted-known warnings remain.",
                "- ACCEPT WITH NOTES: required checks pass, no hard blocker exists, and minor documented limitations remain.",
                "- REJECT / NEEDS FIX: one or more hard blockers, regressions, unauthorized mutations, or unexplained failures exist.",
                "- HOLD / NEEDS MORE INFO: the report lacks required evidence or the operator cannot verify scope, safety, or results.",
                "",
                "Decision boundary:",
                "- This command does not inspect external text, parse a Codex report, score evidence, or choose a decision.",
            ]
        )

    def format_doctor(self) -> str:
        report = self.doctor_report()
        lines = ["Acceptance Review Doctor", f"Status: {report['status']}", "", "Checks:"]
        lines.extend(f"- [{item['severity']}] {item['message']}" for item in report["findings"])
        lines.extend(
            [
                "",
                "Mutation policy:",
                "- Read-only diagnostics only; no review state, decision, command, backup, snapshot, repair, cleanup, migration, or write occurred.",
            ]
        )
        return "\n".join(lines)

    def doctor_report(self) -> dict[str, Any]:
        findings: list[dict[str, str]] = []
        registry = {spec.prefix: spec for spec in COMMAND_REGISTRY}
        missing = [command for command in ACCEPTANCE_COMMANDS if command not in registry]
        findings.append(
            {"severity": "ERROR", "message": f"Acceptance commands missing from Registry: {', '.join(missing)}"}
            if missing
            else {"severity": "OK", "message": "All acceptance commands are registered."}
        )
        unsafe = [
            command
            for command in ACCEPTANCE_COMMANDS
            if command in registry and (not registry[command].read_only or registry[command].mutates != "none")
        ]
        findings.append(
            {"severity": "ERROR", "message": f"Acceptance commands expose mutation: {', '.join(unsafe)}"}
            if unsafe
            else {"severity": "OK", "message": "Acceptance commands are read-only with mutates=none."}
        )
        unavailable = [command for command in _DEPENDENCY_COMMANDS if command not in registry]
        findings.append(
            {"severity": "WARN", "message": f"Optional Acceptance dependencies unavailable: {', '.join(unavailable)}"}
            if unavailable
            else {"severity": "OK", "message": "Focus, Pre-Change, Agenda, Session, Milestone, Warning, and Export helpers are reachable."}
        )
        ledger_path = self.focus.prechange.agenda.warning_inspector.accepted_ledger_path
        findings.append(
            {"severity": "OK", "message": "Accepted-known warnings ledger is reachable."}
            if ledger_path.is_file()
            else {"severity": "WARN", "message": "Accepted-known warnings ledger is missing."}
        )
        try:
            state = self.read_state()
        except Exception as exc:
            findings.append({"severity": "ERROR", "message": f"Acceptance readiness could not be computed: {exc}"})
            state = None
        else:
            findings.append(
                {
                    "severity": "OK",
                    "message": f"Warning readiness is computable: accepted={len(state['accepted'])}, unknown={len(state['unknown'])}, blockers={state['blocker_count']}.",
                }
            )
            if state["unknown"] or state["blocker_count"]:
                findings.append({"severity": "BLOCKED", "message": "Unknown warnings or blockers prevent safe acceptance review."})
            if state["context_state"] == "enabled":
                findings.append({"severity": "WARN", "message": "Context Injection is explicitly enabled; Acceptance Review did not change it."})
            else:
                findings.append({"severity": "OK", "message": "Context Injection is disabled."})
        dangerous = [
            spec.prefix
            for spec in COMMAND_REGISTRY
            if spec.category == "acceptance" and (spec.risk == "high" or not spec.read_only or spec.mutates != "none")
        ]
        findings.append(
            {"severity": "ERROR", "message": f"Dangerous Acceptance actions exposed: {', '.join(dangerous)}"}
            if dangerous
            else {"severity": "OK", "message": "No automatic decision, execution, persistence, backup, snapshot, repair, cleanup, migration, deletion, move, or compression action is exposed."}
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
                "Proto-Mind Acceptance Review Handoff",
                f"Project: {self.project_root}",
                f"Current milestone: {milestone}",
                f"Registry baseline: {len(COMMAND_REGISTRY)} commands across {len(categories)} categories",
                f"Test baseline: {_read_test_baseline(self.project_root)}",
                f"Acceptance readiness: {state['acceptance_readiness']}",
                f"Warning baseline: accepted={len(state['accepted'])}, unknown={len(state['unknown'])}, blockers={state['blocker_count']}",
                f"Context Injection: {state['context_state']}",
                "",
                "Rule 0:",
                "- Require the task-specific backup/checkpoint path in the final report.",
                "",
                "Required Codex final report fields:",
                "- backup path; files changed; commands/behavior; Registry counts; tests/compileall; manual smoke; safety/mutation statement; Context Injection; data/exports SHA-256 when required; limitations/warnings.",
                "",
                "Verification commands:",
                "- scripts/which_python.sh",
                "- scripts/run_tests.sh",
                "- /opt/homebrew/opt/python@3.11/bin/python3.11 -m compileall proto_mind",
                "",
                "Manual smoke:",
                "- Compare the reported commands and outcomes with the original task brief.",
                "",
                "Decision options:",
                "- ACCEPT | ACCEPT WITH NOTES | REJECT / NEEDS FIX | HOLD / NEEDS MORE INFO",
                "",
                "Runtime data integrity:",
                "- For read-only runtime tasks, require proto_mind/data and proto_mind/exports SHA-256 comparison against Rule 0.",
                "- After a manual acceptance decision, review /baseline status and /baseline checklist before documenting a new baseline.",
                "- Use /closure handoff only after acceptance and baseline review are complete.",
                "",
                "Handoff behavior:",
                "- Copyable instructions only; no external report was parsed and no file, clipboard, decision, or review state was created.",
            ]
        )
