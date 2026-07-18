from __future__ import annotations

import re
from collections import Counter
from pathlib import Path
from typing import Any

from proto_mind.command_registry import COMMAND_REGISTRY
from proto_mind.context_pack import ContextInjectionSettingsStore
from proto_mind.daily_layer import DailyAgentLayer, _latest_json, _latest_line, _read_test_baseline
from proto_mind.export_retention import ExportRetention
from proto_mind.memory_store import MemoryStore
from proto_mind.proto_status import ProtoOverview


SESSION_RITUAL_COMMANDS = (
    "/session start-brief",
    "/session end-summary",
    "/session checkpoint-advice",
    "/session handoff-brief",
)


def format_session_ritual_command(
    command: str,
    *,
    project_root: Path,
    memory_store: MemoryStore,
) -> str | None:
    normalized = " ".join(command.strip().lower().split())
    if normalized == "/session start-brief":
        return SessionRituals(project_root=project_root, memory_store=memory_store).format_start_brief()
    if normalized == "/session end-summary":
        return SessionRituals(project_root=project_root, memory_store=memory_store).format_end_summary()
    if normalized == "/session checkpoint-advice":
        return SessionRituals(project_root=project_root, memory_store=memory_store).format_checkpoint_advice()
    if normalized == "/session handoff-brief":
        return SessionRituals(project_root=project_root, memory_store=memory_store).format_handoff_brief()
    if any(normalized.startswith(f"{prefix} ") for prefix in SESSION_RITUAL_COMMANDS):
        return "Usage:\n" + "\n".join(f"  {prefix}" for prefix in SESSION_RITUAL_COMMANDS)
    return None


class SessionRituals:
    def __init__(self, *, project_root: Path, memory_store: MemoryStore) -> None:
        self.project_root = project_root
        self.memory_store = memory_store
        self.daily = DailyAgentLayer(project_root=project_root, memory_store=memory_store)
        self.exports = ExportRetention.from_project_root(project_root)
        self.proto = ProtoOverview(project_root=project_root, memory_store=memory_store)

    def format_start_brief(self) -> str:
        state = self.read_state()
        categories = Counter(spec.category for spec in COMMAND_REGISTRY)
        lines = [
            "Session Start Brief",
            f"project_root: {self.project_root}",
            f"command_registry: commands={len(COMMAND_REGISTRY)} categories={len(categories)}",
            f"daily_doctor: {state['daily_status']}",
            f"export_doctor: {state['export_status']}",
            f"latest_snapshot: {_latest_line(state['latest_snapshot'])}",
            f"latest_snapshot_diff: {_latest_line(state['latest_diff'])}",
            "",
            "Known warnings:",
        ]
        lines.extend(_warning_lines(state["warnings"]))
        lines.extend(
            [
                "",
                "Suggested first safe manual action:",
                f"- {self._first_safe_action(state)}",
                "",
                "Mutation policy:",
                "- Live read-only summary only; no command, model, checkpoint, store, export, or session-log write occurred.",
            ]
        )
        return "\n".join(lines)

    def format_end_summary(self) -> str:
        state = self.read_state()
        lines = [
            "Session End Summary",
            f"system_status: {state['system_status']}",
            f"export_health: {state['export_status']}",
            f"latest_snapshot: {_latest_line(state['latest_snapshot'])}",
            f"latest_snapshot_diff: {_latest_line(state['latest_diff'])}",
            "",
            "Current warnings:",
        ]
        lines.extend(_warning_lines(state["warnings"]))
        lines.extend(
            [
                "",
                "Recommended manual wrap-up:",
                "- Run scripts/run_tests.sh when verification is required.",
                "- Review /proto snapshot-status and create /proto snapshot-export only if the operator wants a persisted snapshot.",
                "- Review /proto snapshot-diff-latest when at least two snapshots exist.",
                "- Use /context export or copy /session handoff-brief only when a handoff is needed.",
                "",
                "Mutation policy:",
                "- This is a live report, not a persistent log; no wrap-up action was executed and no file was written.",
            ]
        )
        return "\n".join(lines)

    def format_checkpoint_advice(self) -> str:
        state = self.read_state()
        reasons: list[str] = []
        if state["latest_snapshot"] is None:
            reasons.append("No exported Proto snapshot is available.")
        if state["latest_diff"] is None:
            reasons.append("No exported snapshot diff is available.")
        else:
            diff_status = str(state["latest_diff"].get("status") or "unknown").upper()
            if diff_status not in {"NO STRUCTURAL CHANGES", "OK"}:
                reasons.append(f"Latest snapshot diff reports {diff_status}.")
        if state["export_status"] != "OK":
            reasons.append(f"Export Doctor reports {state['export_status']}.")
        if state["warnings"]:
            reasons.append(f"Proto warning triage currently has {len(state['warnings'])} finding(s).")
        recommendation = "RECOMMENDED" if reasons else "OPTIONAL"
        lines = [
            "Session Checkpoint Advice",
            f"Recommendation: {recommendation}",
            f"test_status: {_read_test_baseline(self.project_root)}",
            f"latest_snapshot: {_latest_line(state['latest_snapshot'])}",
            f"latest_snapshot_diff: {_latest_line(state['latest_diff'])}",
            f"export_health: {state['export_status']}",
            "",
            "Read-only signals:",
        ]
        lines.extend(f"- {reason}" for reason in reasons or ["No urgent checkpoint signal was detected."])
        lines.extend(
            [
                "",
                "Manual options:",
                "- Project checkpoint: run scripts/run_cli.sh, then /memory backup.",
                "- System-state export: run /proto snapshot-export.",
                "- Verification: run scripts/run_tests.sh separately if needed.",
                "",
                "No automatic action:",
                "- No checkpoint, snapshot, test, export, or repair command was run.",
            ]
        )
        return "\n".join(lines)

    def format_handoff_brief(self) -> str:
        state = self.read_state()
        categories = Counter(spec.category for spec in COMMAND_REGISTRY)
        milestone = read_ledger_section_lead(self.project_root, "Last Completed Milestone") or "not recorded"
        next_candidate = read_ledger_first_bullet(self.project_root, "Next Candidate Tasks") or self._first_safe_action(state)
        lines = [
            "Proto-Mind Session Handoff Brief",
            f"Project: {self.project_root}",
            f"Current milestone: {milestone}",
            f"Registry: {len(COMMAND_REGISTRY)} commands across {len(categories)} categories",
            f"Current system status: {state['system_status']}",
            f"Context Injection: {state['context_state']}",
            "",
            "Safety commands:",
            "- /proto doctor; /data doctor; /data refs-doctor; /commands doctor; /policy doctor",
            "- /action readiness-doctor; /action run-audit; /consolidation queue-doctor",
            "",
            "Daily commands:",
            "- /daily status; /daily brief; /daily doctor; /daily next",
            "",
            "Operator Agenda commands:",
            "- /agenda status; /agenda next; /agenda list; /agenda doctor",
            "",
            "Pre-Change Ritual commands:",
            "- /prechange status; /prechange checklist; /prechange doctor; /prechange handoff",
            "",
            "Focus Mode commands:",
            "- /focus status; /focus plan; /focus checklist; /focus doctor; /focus handoff",
            "",
            "Acceptance Review commands:",
            "- /acceptance status; /acceptance checklist; /acceptance criteria; /acceptance decision-guide; /acceptance doctor; /acceptance handoff",
            "",
            "Accepted Baseline commands:",
            "- /baseline status; /baseline current; /baseline latest; /baseline checklist; /baseline doctor; /baseline handoff",
            "",
            "Post-Acceptance Closure commands:",
            "- /closure status; /closure summary; /closure next; /closure handoff; /closure doctor",
            "",
            "Operator Memory Card commands:",
            "- /memory-card status; /memory-card short; /memory-card full; /memory-card codex; /memory-card doctor",
            "",
            "Capability Map commands:",
            "- /capabilities status; /capabilities list; /capabilities map; /capabilities safety; /capabilities doctor; /capabilities handoff",
            "",
            "Dry-Run Plan commands:",
            "- /plan status; /plan next; /plan dry-run; /plan gates; /plan doctor; /plan handoff",
            "",
            "Confirmation Vocabulary commands:",
            "- /confirm status; /confirm policy; /confirm levels; /confirm requirements; /confirm doctor; /confirm handoff",
            "- /sandbox status; /sandbox blueprint; /sandbox boundaries; /sandbox allowlist; /sandbox denied; /sandbox doctor; /sandbox handoff",
            "- /runner status; /runner contract; /runner noop; /runner evidence; /runner disabled; /runner doctor; /runner handoff",
            "- /runner-candidates status; /runner-candidates list; /runner-candidates explain; /runner-candidates denied; /runner-candidates gates; /runner-candidates doctor; /runner-candidates handoff",
            "- /activation status; /activation preconditions; /activation checklist; /activation blockers; /activation forbidden; /activation doctor; /activation handoff",
            "- /runner-mvp status; /runner-mvp design; /runner-mvp allowlist; /runner-mvp confirmation; /runner-mvp evidence; /runner-mvp stop-conditions; /runner-mvp doctor; /runner-mvp handoff",
            "",
            "Export inspection commands:",
            "- /exports status; /exports inventory; /exports cleanup-preview; /exports doctor",
            "",
            "Snapshot / diff commands:",
            "- /proto snapshot-status; /proto snapshot-list; /proto snapshot-diff-status; /proto snapshot-diff-latest",
            "- Export commands are manual only: /proto snapshot-export; /proto snapshot-diff-export-latest",
            "",
            "Known warnings:",
        ]
        lines.extend(_warning_lines(state["warnings"]))
        lines.extend(
            [
                "",
                "Suggested next milestone/manual action:",
                f"- {next_candidate}",
                "",
                "Rule 0:",
                "- Before any changes, create a backup/checkpoint first with scripts/run_cli.sh and /memory backup.",
                "",
                "Handoff safety:",
                "- Copyable text only; no clipboard, file, external call, model call, or command execution occurred.",
            ]
        )
        return "\n".join(lines)

    def read_state(self) -> dict[str, Any]:
        doctors = self.proto._doctor_results()
        warnings = self.proto._warning_triage(doctors)
        return {
            "daily_status": self.daily.doctor_report()["status"],
            "export_status": self.exports.doctor_report()["status"],
            "system_status": _overall_status(result["status"] for result in doctors.values()),
            "latest_snapshot": _latest_json(self.proto.snapshot_export_dir),
            "latest_diff": _latest_json(self.proto.snapshot_diff_export_dir),
            "warnings": warnings,
            "context_state": "enabled" if _context_enabled(self.daily) else "disabled",
        }

    def _first_safe_action(self, state: dict[str, Any]) -> str:
        if state["daily_status"] != "OK":
            return "Inspect /daily doctor."
        if state["export_status"] != "OK":
            return "Inspect /exports doctor."
        if state["warnings"]:
            return "Inspect /proto warnings before structural work."
        if state["latest_snapshot"] is None:
            return "Review /proto snapshot-status and decide whether to create a manual snapshot."
        return "Review /daily next and choose one manual milestone."


def _context_enabled(daily: DailyAgentLayer) -> bool:
    settings = ContextInjectionSettingsStore.from_project_root(daily.project_root).read_settings(initialize=False)
    return bool(settings.get("enabled"))


def _warning_lines(warnings: list[dict[str, Any]], *, limit: int = 4) -> list[str]:
    if not warnings:
        return ["- none"]
    lines = [f"- [{item['category']}] {item['message']}" for item in warnings[:limit]]
    if len(warnings) > limit:
        lines.append(f"- ... {len(warnings) - limit} more; inspect with /proto warnings")
    return lines


def _overall_status(statuses: Any) -> str:
    rank = {"OK": 0, "WARN": 1, "ERROR": 2}
    return max((str(status) for status in statuses), key=lambda status: rank.get(status, 2), default="OK")


def read_ledger_section_lead(project_root: Path, section: str) -> str | None:
    text = _read_ledger(project_root)
    if text is None:
        return None
    match = re.search(rf"^## {re.escape(section)}\s*$\n+\s*([^\n]+)", text, flags=re.MULTILINE)
    return match.group(1).strip().rstrip(":") if match else None


def read_ledger_first_bullet(project_root: Path, section: str) -> str | None:
    text = _read_ledger(project_root)
    if text is None:
        return None
    in_section = False
    for line in text.splitlines():
        if line.strip() == f"## {section}":
            in_section = True
            continue
        if in_section and line.startswith("## "):
            break
        if in_section and line.startswith("- "):
            return line[2:].strip()
    return None


def _read_ledger(project_root: Path) -> str | None:
    try:
        return (project_root / "PROTO_MIND_ARCHITECT_LEDGER.md").read_text(encoding="utf-8")
    except OSError:
        return None
