from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from proto_mind.acceptance_layer import AcceptanceReview
from proto_mind.command_registry import COMMAND_REGISTRY
from proto_mind.daily_layer import _latest_json, _latest_line, _read_test_baseline
from proto_mind.memory_store import MemoryStore
from proto_mind.proto_status import ProtoOverview
from proto_mind.session_rituals import read_ledger_section_lead


BASELINE_COMMANDS = (
    "/baseline status",
    "/baseline current",
    "/baseline latest",
    "/baseline checklist",
    "/baseline doctor",
    "/baseline handoff",
)
_DEPENDENCY_COMMANDS = (
    "/acceptance status",
    "/acceptance checklist",
    "/focus status",
    "/prechange status",
    "/warnings accepted",
    "/warnings unknown",
    "/proto snapshot-status",
    "/proto snapshot-list",
    "/proto snapshot-diff-status",
    "/proto snapshot-diff-latest",
)


def format_baseline_command(command: str, *, project_root: Path, memory_store: MemoryStore) -> str | None:
    normalized = " ".join(command.strip().lower().split())
    if not normalized.startswith("/baseline"):
        return None
    registry = SnapshotBaselineRegistry(project_root=project_root, memory_store=memory_store)
    if normalized == "/baseline status":
        return registry.format_status()
    if normalized == "/baseline current":
        return registry.format_current()
    if normalized == "/baseline latest":
        return registry.format_latest()
    if normalized == "/baseline checklist":
        return registry.format_checklist()
    if normalized == "/baseline doctor":
        return registry.format_doctor()
    if normalized == "/baseline handoff":
        return registry.format_handoff()
    return "Usage:\n" + "\n".join(f"  {item}" for item in BASELINE_COMMANDS)


class SnapshotBaselineRegistry:
    def __init__(self, *, project_root: Path, memory_store: MemoryStore) -> None:
        self.project_root = project_root
        self.memory_store = memory_store
        self.acceptance = AcceptanceReview(project_root=project_root, memory_store=memory_store)
        self.proto = ProtoOverview(project_root=project_root, memory_store=memory_store)

    def read_state(self) -> dict[str, Any]:
        acceptance = self.acceptance.read_state()
        latest_snapshot = _latest_json(self.proto.snapshot_export_dir)
        latest_diff = _latest_json(self.proto.snapshot_diff_export_dir)
        milestone = read_ledger_section_lead(self.project_root, "Last Completed Milestone")
        test_baseline = _read_test_baseline(self.project_root)
        if acceptance["unknown"] or acceptance["blocker_count"]:
            readiness = "BLOCKED"
        elif acceptance["accepted"] or acceptance["system_status"] != "OK" or acceptance["context_state"] == "enabled":
            readiness = "WARN"
        else:
            readiness = "OK"
        review_safe = (
            not acceptance["unknown"]
            and acceptance["blocker_count"] == 0
            and acceptance["context_state"] == "disabled"
            and acceptance["acceptance_review_safe"]
        )
        return {
            **acceptance,
            "baseline_readiness": readiness,
            "baseline_review_safe": review_safe,
            "accepted_baseline": milestone,
            "test_baseline": test_baseline,
            "latest_snapshot": latest_snapshot,
            "latest_diff": latest_diff,
        }

    def format_status(self) -> str:
        state = self.read_state()
        categories = Counter(spec.category for spec in COMMAND_REGISTRY)
        return "\n".join(
            [
                "Snapshot Baseline Registry Status",
                f"Status: {state['baseline_readiness']}",
                f"project_root: {self.project_root}",
                f"command_registry: commands={len(COMMAND_REGISTRY)} categories={len(categories)}",
                f"accepted_baseline: {state['accepted_baseline'] or 'not detected'}",
                f"latest_snapshot: {_latest_line(state['latest_snapshot'])}",
                f"latest_snapshot_diff: {_latest_line(state['latest_diff'])}",
                f"acceptance_readiness: {state['acceptance_readiness']}",
                f"accepted_known_warnings: {len(state['accepted'])}",
                f"unknown_warnings: {len(state['unknown'])}",
                f"blockers: {state['blocker_count']}",
                f"baseline_review_safe: {str(state['baseline_review_safe']).lower()}",
                "",
                "Awareness only:",
                "- No baseline, snapshot, checkpoint, acceptance state, or runtime record was created or changed.",
            ]
        )

    def format_current(self) -> str:
        state = self.read_state()
        categories = Counter(spec.category for spec in COMMAND_REGISTRY)
        unknown_fields: list[str] = []
        if not state["accepted_baseline"]:
            unknown_fields.append("accepted milestone / phase")
        if state["test_baseline"].startswith("not checked"):
            unknown_fields.append("documented test baseline")
        if state["latest_snapshot"] is None:
            unknown_fields.append("latest snapshot")
        if state["latest_diff"] is None:
            unknown_fields.append("latest snapshot diff")
        lines = [
            "Current Detected Accepted Baseline",
            "",
            "Detected facts:",
            f"- project: {self.project_root}",
            f"- documented milestone: {state['accepted_baseline'] or 'not detected'}",
            f"- command registry: {len(COMMAND_REGISTRY)} commands across {len(categories)} categories",
            f"- test baseline: {state['test_baseline']}",
            f"- warning baseline: accepted={len(state['accepted'])}, unknown={len(state['unknown'])}, blockers={state['blocker_count']}",
            f"- Context Injection: {state['context_state']}",
            "",
            "Inferred baseline:",
            f"- readiness: {state['baseline_readiness']}",
            f"- safe for manual baseline review: {str(state['baseline_review_safe']).lower()}",
            "- inference is based only on local ledger, acceptance state, and existing snapshot metadata.",
            "",
            "Unknown / undetected fields:",
        ]
        lines.extend(f"- {item}" for item in unknown_fields or ["none"])
        lines.extend(
            [
                "",
                "Mutation policy:",
                "- Detection only; no baseline was accepted, persisted, updated, or inferred from external text.",
            ]
        )
        return "\n".join(lines)

    def format_latest(self) -> str:
        state = self.read_state()
        reasons: list[str] = []
        if state["latest_snapshot"] is None:
            reasons.append("No exported Proto snapshot is available.")
        elif str(state["latest_snapshot"].get("status") or "unknown").upper() not in {"OK", "WARN"}:
            reasons.append("Latest snapshot status is unknown or unreadable.")
        if state["latest_diff"] is None:
            reasons.append("No exported snapshot diff is available.")
        elif str(state["latest_diff"].get("status") or "unknown").upper() not in {"OK", "NO STRUCTURAL CHANGES"}:
            reasons.append(f"Latest snapshot diff reports {state['latest_diff'].get('status') or 'unknown'}.")
        if not state["baseline_review_safe"]:
            reasons.append("Acceptance/warning state is not safe for baseline review.")
        elif state["baseline_readiness"] == "WARN":
            reasons.append("Accepted-known/source WARN findings should be reviewed before documenting a baseline.")
        recommendation = "RECOMMENDED" if reasons or state["baseline_readiness"] == "WARN" else "OPTIONAL"
        lines = [
            "Latest Snapshot / Diff Baseline Signals",
            f"latest_snapshot: {_latest_line(state['latest_snapshot'])}",
            f"latest_snapshot_diff: {_latest_line(state['latest_diff'])}",
            f"baseline_readiness: {state['baseline_readiness']}",
            f"manual_review: {recommendation}",
            "",
            "Review reasons:",
        ]
        lines.extend(f"- {reason}" for reason in reasons or ["Existing snapshot/diff signals do not show an urgent structural warning."])
        lines.extend(
            [
                "",
                "Manual options:",
                "- Inspect /proto snapshot-list and /proto snapshot-diff-latest.",
                "- Create a new snapshot only by an explicit operator command after acceptance, if appropriate.",
                "",
                "No automatic action:",
                "- No snapshot, diff, export, backup, or command was created or run.",
            ]
        )
        return "\n".join(lines)

    def format_checklist(self) -> str:
        return "\n".join(
            [
                "Accepted Baseline Manual Checklist",
                "1. Run /acceptance checklist and make the acceptance decision manually.",
                "2. Confirm scripts/which_python.sh, scripts/run_tests.sh, and Python 3.11 compileall passed.",
                "3. Confirm all required manual smoke commands passed.",
                "4. Confirm Context Injection remains disabled unless the task explicitly authorized a change.",
                "5. Confirm unknown warnings = 0 and blockers = 0.",
                "6. For read-only runtime work, confirm proto_mind/data and proto_mind/exports SHA-256 are unchanged from Rule 0.",
                "7. Review existing snapshot status and snapshot diff manually.",
                "8. Create/check a snapshot manually only if appropriate after acceptance.",
                "9. Update architecture docs/ledger only in an explicit implementation task when the accepted baseline changes.",
                "10. Finish with /session end-summary and /session handoff-brief.",
                "",
                "Checklist behavior:",
                "- Printed only; no check, command, snapshot, backup, baseline record, or acceptance state was executed or persisted.",
            ]
        )

    def format_doctor(self) -> str:
        report = self.doctor_report()
        lines = ["Snapshot Baseline Registry Doctor", f"Status: {report['status']}", "", "Checks:"]
        lines.extend(f"- [{item['severity']}] {item['message']}" for item in report["findings"])
        lines.extend(
            [
                "",
                "Mutation policy:",
                "- Read-only diagnostics only; no baseline, snapshot, backup, export, acceptance state, repair, cleanup, migration, or file write occurred.",
            ]
        )
        return "\n".join(lines)

    def doctor_report(self) -> dict[str, Any]:
        findings: list[dict[str, str]] = []
        registry = {spec.prefix: spec for spec in COMMAND_REGISTRY}
        missing = [command for command in BASELINE_COMMANDS if command not in registry]
        findings.append(
            {"severity": "ERROR", "message": f"Baseline commands missing from Registry: {', '.join(missing)}"}
            if missing
            else {"severity": "OK", "message": "All baseline commands are registered."}
        )
        unsafe = [
            command
            for command in BASELINE_COMMANDS
            if command in registry and (not registry[command].read_only or registry[command].mutates != "none")
        ]
        findings.append(
            {"severity": "ERROR", "message": f"Baseline commands expose mutation: {', '.join(unsafe)}"}
            if unsafe
            else {"severity": "OK", "message": "Baseline commands are read-only with mutates=none."}
        )
        unavailable = [command for command in _DEPENDENCY_COMMANDS if command not in registry]
        findings.append(
            {"severity": "WARN", "message": f"Optional baseline dependencies unavailable: {', '.join(unavailable)}"}
            if unavailable
            else {"severity": "OK", "message": "Snapshot, diff, Acceptance, Focus, Pre-Change, and Warning helpers are reachable."}
        )
        ledger_path = self.project_root / "PROTO_MIND_ARCHITECT_LEDGER.md"
        findings.append(
            {"severity": "OK", "message": "Architect Ledger is reachable for accepted-baseline detection."}
            if ledger_path.is_file()
            else {"severity": "WARN", "message": "Architect Ledger is missing; accepted milestone/test baseline may be unknown."}
        )
        accepted_ledger = self.acceptance.focus.prechange.agenda.warning_inspector.accepted_ledger_path
        findings.append(
            {"severity": "OK", "message": "Accepted-known warnings ledger is reachable."}
            if accepted_ledger.is_file()
            else {"severity": "WARN", "message": "Accepted-known warnings ledger is missing."}
        )
        try:
            state = self.read_state()
        except Exception as exc:
            findings.append({"severity": "ERROR", "message": f"Baseline awareness could not be computed: {exc}"})
        else:
            findings.append(
                {
                    "severity": "OK",
                    "message": f"Baseline warning state is computable: accepted={len(state['accepted'])}, unknown={len(state['unknown'])}, blockers={state['blocker_count']}.",
                }
            )
            if state["unknown"] or state["blocker_count"]:
                findings.append({"severity": "BLOCKED", "message": "Unknown warnings or blockers prevent safe baseline review."})
            if state["context_state"] == "enabled":
                findings.append({"severity": "WARN", "message": "Context Injection is explicitly enabled; Baseline Registry did not change it."})
            else:
                findings.append({"severity": "OK", "message": "Context Injection is disabled."})
        dangerous = [
            spec.prefix
            for spec in COMMAND_REGISTRY
            if spec.category == "baseline" and (spec.risk == "high" or not spec.read_only or spec.mutates != "none")
        ]
        findings.append(
            {"severity": "ERROR", "message": f"Dangerous baseline actions exposed: {', '.join(dangerous)}"}
            if dangerous
            else {"severity": "OK", "message": "No snapshot, backup, persistence, execution, repair, cleanup, migration, deletion, move, or compression action is exposed."}
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
        return "\n".join(
            [
                "Proto-Mind Accepted Baseline Handoff",
                f"Project: {self.project_root}",
                f"Accepted baseline: {state['accepted_baseline'] or 'not detected'}",
                f"Registry: {len(COMMAND_REGISTRY)} commands across {len(categories)} categories",
                f"Tests: {state['test_baseline']}",
                f"Warnings: accepted={len(state['accepted'])}, unknown={len(state['unknown'])}, blockers={state['blocker_count']}",
                f"Context Injection: {state['context_state']}",
                f"Latest snapshot: {_latest_line(state['latest_snapshot'])}",
                f"Latest snapshot diff: {_latest_line(state['latest_diff'])}",
                "",
                "Baseline review:",
                "- Review /acceptance checklist, /baseline checklist, /proto snapshot-list, and /proto snapshot-diff-latest manually.",
                "- After human acceptance and baseline review, use /closure status and /closure handoff to close the session manually.",
                "- Use /memory-card short or /memory-card codex for compact next-session context.",
                "- Do not treat this text as persisted acceptance or authorization to create a snapshot.",
                "",
                "Rule 0:",
                "- Before future changes, run scripts/run_cli.sh and /memory backup first.",
                "",
                "Verification commands:",
                "- scripts/which_python.sh",
                "- scripts/run_tests.sh",
                "- /opt/homebrew/opt/python@3.11/bin/python3.11 -m compileall proto_mind",
                "",
                "Handoff safety:",
                "- Copyable text only; no file, clipboard, external call, baseline record, snapshot, backup, or command execution occurred.",
            ]
        )
