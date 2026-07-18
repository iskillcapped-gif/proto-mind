from __future__ import annotations

import hashlib
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from proto_mind.command_registry import COMMAND_REGISTRY
from proto_mind.memory_store import MemoryStore
from proto_mind.milestone_layer import MilestoneTracker
from proto_mind.session_rituals import SessionRituals


WARNING_COMMANDS = (
    "/warnings status",
    "/warnings list",
    "/warnings inspect",
    "/warnings accepted",
    "/warnings accepted-ledger",
    "/warnings unknown",
    "/warnings doctor",
)
KNOWN_WARNINGS_LEDGER_FILENAME = "KNOWN_WARNINGS_LEDGER.md"
_DEPENDENCY_COMMANDS = (
    "/daily doctor",
    "/session start-brief",
    "/session handoff-brief",
    "/milestone doctor",
    "/exports doctor",
)
_KNOWN_CATEGORIES = {
    "legacy",
    "dangling_ref",
    "queue_hygiene",
    "policy_drift",
    "data_integrity",
    "missing_store",
}
_HISTORICAL_CATEGORIES = {"legacy", "dangling_ref"}


@dataclass(frozen=True)
class AcceptedWarningRule:
    id: str
    category: str
    required_terms: tuple[str, ...]
    reason: str

    def matches(self, warning: dict[str, Any]) -> bool:
        message = str(warning.get("message") or "").lower()
        return warning.get("category") == self.category and all(term.lower() in message for term in self.required_terms)


ACCEPTED_WARNING_RULES = (
    AcceptedWarningRule(
        "accepted_dangling_consolidation_receipt",
        "dangling_ref",
        ("cq_20260626201008_e7ed", "missing applied_record_id"),
        "Historical consolidation apply receipt predates reliable applied_record_id capture.",
    ),
    AcceptedWarningRule(
        "accepted_legacy_action_receipt_v1",
        "legacy",
        ("act_20260628165932_d2a9",),
        "Historical read-only action receipt predates receipt-v2 metadata and hash fields.",
    ),
    AcceptedWarningRule(
        "accepted_context_enable_readiness_guard",
        "policy_drift",
        ("act_20260628170033_9176",),
        "Stored context-enable proposal is intentionally refused by current read-only run policy.",
    ),
    AcceptedWarningRule(
        "accepted_approved_unconfirmed_queue_state",
        "queue_hygiene",
        ("approved but unconfirmed proposals",),
        "Approved proposals remain gated and require explicit operator lifecycle decisions.",
    ),
)


def format_warning_command(command: str, *, project_root: Path, memory_store: MemoryStore) -> str | None:
    normalized = " ".join(command.strip().lower().split())
    if not normalized.startswith("/warnings"):
        return None
    inspector = LegacyWarningInspector(project_root=project_root, memory_store=memory_store)
    if normalized == "/warnings status":
        return inspector.format_status()
    if normalized == "/warnings list":
        return inspector.format_list()
    if normalized == "/warnings inspect":
        return inspector.format_inspect()
    if normalized == "/warnings accepted":
        return inspector.format_accepted()
    if normalized == "/warnings accepted-ledger":
        return inspector.format_accepted_ledger()
    if normalized == "/warnings unknown":
        return inspector.format_unknown()
    if normalized == "/warnings doctor":
        return inspector.format_doctor()
    return "Usage:\n" + "\n".join(f"  {item}" for item in WARNING_COMMANDS)


class LegacyWarningInspector:
    def __init__(self, *, project_root: Path, memory_store: MemoryStore) -> None:
        self.project_root = project_root
        self.memory_store = memory_store
        self.session = SessionRituals(project_root=project_root, memory_store=memory_store)
        self.milestones = MilestoneTracker(project_root=project_root, memory_store=memory_store)

    @property
    def accepted_ledger_path(self) -> Path:
        return self.project_root / KNOWN_WARNINGS_LEDGER_FILENAME

    def warnings(self) -> list[dict[str, Any]]:
        state = self.session.read_state()
        warnings = [_enrich_warning(item, self.project_root) for item in state["warnings"]]
        for warning in warnings:
            rule = _accepted_rule(warning)
            warning["accepted_rule_id"] = rule.id if rule else None
            warning["accepted_known"] = rule is not None
        return warnings

    def format_status(self) -> str:
        warnings = self.warnings()
        categories = Counter(item["category"] for item in warnings)
        classifications = Counter(item["classification"] for item in warnings)
        accepted_count = sum(1 for item in warnings if item["accepted_known"])
        status = "WARN" if warnings else "OK"
        next_action = (
            f"Inspect {warnings[0]['id']} below with /warnings inspect and its source command {warnings[0]['inspect_command']}."
            if warnings
            else "No warning action is currently required; re-run /warnings status after structural changes."
        )
        return "\n".join(
            [
                "Legacy Warning Inspector Status",
                f"Status: {status}",
                f"known_warnings: {len(warnings)}",
                f"categories: {_counter_line(categories)}",
                f"classifications: {_counter_line(classifications)}",
                f"legacy_or_historical: {sum(1 for item in warnings if item['category'] in _HISTORICAL_CATEGORIES)}",
                f"new_or_unknown: {classifications.get('new_or_unknown', 0)}",
                f"accepted_known: {accepted_count}",
                f"unmatched_unknown: {len(warnings) - accepted_count}",
                "",
                "Suggested safe manual next action:",
                f"- {next_action}",
                "",
                "Mutation policy:",
                "- Read-only warning status only; no warning, receipt, queue, context, store, or export was changed.",
            ]
        )

    def format_list(self) -> str:
        warnings = self.warnings()
        lines = ["Detected Warning List", f"Status: {'WARN' if warnings else 'OK'}", f"Warnings: {len(warnings)}", ""]
        if not warnings:
            lines.append("- none")
        for index, item in enumerate(warnings, start=1):
            lines.extend(
                [
                    f"{index}. id: {item['id']}",
                    f"   category: {item['category']}",
                    f"   severity: {item['operator_severity']}",
                    f"   classification: {item['classification']}",
                    f"   source: {', '.join(item['sources'])}",
                    f"   explanation: {item['message']}",
                ]
            )
        lines.extend(
            [
                "",
                "Mutation policy:",
                "- Stable diagnostic identifiers only; no warning state or source record was rewritten.",
            ]
        )
        return "\n".join(lines)

    def format_accepted(self) -> str:
        warnings = self.warnings()
        accepted = [item for item in warnings if item["accepted_known"]]
        counts = Counter(item["category"] for item in accepted)
        lines = [
            "Accepted Known Warnings",
            f"Status: {'OK' if len(accepted) == len(warnings) else 'WARN'}",
            f"accepted_findings: {len(accepted)}",
            f"total_findings: {len(warnings)}",
            f"accepted_categories: {_counter_line(counts)}",
            "",
            "Accepted rules:",
        ]
        for rule in ACCEPTED_WARNING_RULES:
            matched = sum(1 for item in accepted if item["accepted_rule_id"] == rule.id)
            lines.extend(
                [
                    f"- {rule.id}: category={rule.category} matched={matched}",
                    f"  why accepted: {rule.reason}",
                ]
            )
        lines.extend(
            [
                "",
                "Safety note:",
                "- Runtime gates remain protective; acceptance documents existing debt and does not authorize execution or suppress source warnings.",
                "",
                "Recommended manual policy:",
                "- Leave as known legacy debt unless a future migration/repair task is explicitly planned, checkpointed, reviewed, and tested.",
                "",
                "Mutation policy:",
                "- Read-only classification only; no warning was hidden, acknowledged in data, repaired, or rewritten.",
            ]
        )
        return "\n".join(lines)

    def format_accepted_ledger(self) -> str:
        lines = [
            "Accepted Known Warnings Ledger",
            f"path: {self.accepted_ledger_path}",
        ]
        try:
            content = self.accepted_ledger_path.read_text(encoding="utf-8").strip()
        except OSError as exc:
            lines.extend(["readable: no", f"error: {exc}"])
        else:
            lines.extend(["readable: yes", "", content])
        lines.extend(
            [
                "",
                "Runtime behavior:",
                "- Ledger text was read only; it was not created, refreshed, or modified by this command.",
            ]
        )
        return "\n".join(lines)

    def format_unknown(self) -> str:
        warnings = self.warnings()
        unknown = [item for item in warnings if not item["accepted_known"]]
        lines = [
            "Unknown / Unaccepted Warning Findings",
            f"Status: {'WARN' if unknown else 'OK'}",
            f"unknown_findings: {len(unknown)}",
            f"accepted_findings: {len(warnings) - len(unknown)}",
            "",
            "Findings:",
        ]
        if not unknown:
            lines.append("- none; all current findings match narrow accepted-known rules")
        for item in unknown:
            lines.extend(
                [
                    f"- id: {item['id']}",
                    f"  category/severity: {item['category']} / {item['operator_severity']}",
                    f"  source: {', '.join(item['sources'])}",
                    f"  explanation: {item['message']}",
                    f"  inspect: {item['inspect_command']}",
                ]
            )
        lines.extend(
            [
                "",
                "Visibility policy:",
                "- Accepted findings remain visible in /warnings list and /warnings inspect; this filter suppresses nothing.",
                "",
                "Mutation policy:",
                "- Read-only comparison against static rules; no warning state or accepted ledger was changed.",
            ]
        )
        return "\n".join(lines)

    def format_inspect(self) -> str:
        warnings = self.warnings()
        lines = ["Legacy Warning Inspection", f"Status: {'WARN' if warnings else 'OK'}", f"Warnings inspected: {len(warnings)}"]
        if not warnings:
            lines.extend(["", "- No current warning findings."])
        for item in warnings:
            detail = _warning_detail(item)
            lines.extend(
                [
                    "",
                    f"Warning {item['id']}",
                    f"- category/severity: {item['category']} / {item['operator_severity']}",
                    f"- classification: {item['classification']}",
                    f"- what was found: {item['message']}",
                    f"- source doctor: {', '.join(item['sources'])}",
                    f"- likely source path: {item['source_path']}",
                    f"- why it matters: {detail['why']}",
                    f"- runtime safety: {detail['runtime']}",
                    f"- data integrity: {detail['integrity']}",
                    f"- manual inspect: {item['inspect_command']}",
                    "- manual options: leave as historical/legacy; document as an accepted known warning; create a separate migration/repair task later; inspect the related file manually.",
                ]
            )
        lines.extend(
            [
                "",
                "No repair performed:",
                "- No file, receipt, hash, reference, proposal, context setting, report, or export was created or modified.",
            ]
        )
        return "\n".join(lines)

    def format_doctor(self) -> str:
        report = self.doctor_report()
        lines = ["Warning Inspector Doctor", f"Status: {report['status']}", "", "Checks:"]
        lines.extend(f"- [{item['severity']}] {item['message']}" for item in report["findings"])
        lines.extend(
            [
                "",
                "Mutation policy:",
                "- Inspector diagnostics only; no repair, cleanup, migration, command execution, or write occurred.",
            ]
        )
        return "\n".join(lines)

    def doctor_report(self) -> dict[str, Any]:
        findings: list[dict[str, str]] = []
        registry = {spec.prefix: spec for spec in COMMAND_REGISTRY}
        missing = [command for command in WARNING_COMMANDS if command not in registry]
        if missing:
            findings.append({"severity": "ERROR", "message": f"Warning commands missing from Registry: {', '.join(missing)}"})
        else:
            findings.append({"severity": "OK", "message": "All warning-inspector commands are registered."})
        unsafe = [
            command
            for command in WARNING_COMMANDS
            if command in registry and (not registry[command].read_only or registry[command].mutates != "none")
        ]
        if unsafe:
            findings.append({"severity": "ERROR", "message": f"Warning commands expose mutation: {', '.join(unsafe)}"})
        else:
            findings.append({"severity": "OK", "message": "Warning commands are read-only with mutates=none."})

        unavailable = [command for command in _DEPENDENCY_COMMANDS if command not in registry]
        if unavailable:
            findings.append({"severity": "WARN", "message": f"Optional warning dependencies unavailable: {', '.join(unavailable)}"})
        else:
            state = self.session.read_state()
            milestone_status = self.milestones.doctor_report()["status"]
            findings.append(
                {
                    "severity": "OK",
                    "message": (
                        "Daily, Session Ritual, Milestone, and Export diagnostics are reachable "
                        f"(daily={state['daily_status']}, milestone={milestone_status}, exports={state['export_status']})."
                    ),
                }
            )

        state = self.session.read_state()
        if state["context_state"] == "enabled":
            findings.append({"severity": "WARN", "message": "Context Injection is explicitly enabled; Warning Inspector did not change it."})
        else:
            findings.append({"severity": "OK", "message": "Context Injection is disabled."})
        try:
            self.accepted_ledger_path.read_text(encoding="utf-8")
        except OSError:
            findings.append({"severity": "WARN", "message": f"Accepted warning ledger is missing or unreadable: {self.accepted_ledger_path}."})
        else:
            findings.append({"severity": "OK", "message": "Accepted warning ledger is reachable and read-only."})
        dangerous = [
            spec.prefix
            for spec in COMMAND_REGISTRY
            if spec.category == "warnings" and (spec.risk == "high" or not spec.read_only or spec.mutates != "none")
        ]
        if dangerous:
            findings.append({"severity": "ERROR", "message": f"Dangerous warning actions exposed: {', '.join(dangerous)}"})
        else:
            findings.append({"severity": "OK", "message": "No repair, deletion, move, rewrite, cleanup, compression, or execution action is exposed."})
        warnings = self.warnings()
        findings.append({"severity": "OK", "message": f"Existing Proto warning source is reachable; current findings: {len(warnings)}."})
        accepted = sum(1 for item in warnings if item["accepted_known"])
        findings.append(
            {
                "severity": "OK",
                "message": f"Accepted-known classification is operational: accepted={accepted}, unknown={len(warnings) - accepted}.",
            }
        )
        status = "ERROR" if any(item["severity"] == "ERROR" for item in findings) else "WARN" if any(item["severity"] == "WARN" for item in findings) else "OK"
        return {"status": status, "findings": findings}


def _enrich_warning(item: dict[str, Any], project_root: Path) -> dict[str, Any]:
    enriched = dict(item)
    category = str(item.get("category") or "unknown")
    message = str(item.get("message") or "")
    entity_match = re.search(r"\b(?:act|cq|mem|skill)_\d+_[a-z0-9]+\b", message, flags=re.IGNORECASE)
    digest = hashlib.sha256(" ".join(message.lower().split()).encode("utf-8")).hexdigest()[:10]
    entity = entity_match.group(0).lower() if entity_match else "finding"
    enriched.update(
        {
            "id": f"warn_{category}_{entity}_{digest}",
            "classification": "known_historical" if category in _HISTORICAL_CATEGORIES else "known" if category in _KNOWN_CATEGORIES else "new_or_unknown",
            "operator_severity": _operator_severity(item),
            "source_path": _source_path(project_root, category, message),
        }
    )
    return enriched


def _accepted_rule(warning: dict[str, Any]) -> AcceptedWarningRule | None:
    return next((rule for rule in ACCEPTED_WARNING_RULES if rule.matches(warning)), None)


def _operator_severity(item: dict[str, Any]) -> str:
    if item.get("severity") == "error":
        return "BLOCKER"
    if item.get("category") in _HISTORICAL_CATEGORIES and item.get("safe_to_ignore"):
        return "INFO"
    return "WARN"


def _source_path(project_root: Path, category: str, message: str) -> str:
    data_dir = project_root / "proto_mind" / "data"
    if category == "dangling_ref" or "consolidation" in message.lower() or "cq_" in message.lower():
        return str(data_dir / "consolidation_queue.jsonl")
    if category in {"legacy", "policy_drift", "queue_hygiene"} or "act_" in message.lower():
        return str(data_dir / "action_queue.jsonl")
    return "not determinable from current doctor finding; inspect /data inventory"


def _warning_detail(item: dict[str, Any]) -> dict[str, str]:
    category = item["category"]
    if category == "legacy":
        return {
            "why": "The historical action predates receipt-v2 metadata, so modern hash/field verification is incomplete.",
            "runtime": "No evidence of a new execution; the run-once gate still prevents replay of the executed action.",
            "integrity": "Receipt provenance is incomplete, but this finding does not itself indicate core-store corruption.",
        }
    if category == "dangling_ref":
        return {
            "why": "The applied consolidation receipt cannot prove which memory/skill record it created.",
            "runtime": "No target command is being executed; current runtime behavior remains gated.",
            "integrity": "Cross-store receipt traceability and safe rollback verification are incomplete.",
        }
    if category == "policy_drift":
        return {
            "why": "The stored proposal is not eligible under current read-only auto-allowed execution rules.",
            "runtime": "Protective readiness checks refuse execution; the warning documents that refusal.",
            "integrity": "No core-store corruption is indicated; proposal policy metadata needs operator review.",
        }
    if category == "queue_hygiene":
        return {
            "why": "Queue lifecycle metadata needs operator review but no target action has run.",
            "runtime": "The proposal remains gated and cannot execute without the required lifecycle steps.",
            "integrity": "Queue state is readable; this is operational hygiene rather than evidence of corruption.",
        }
    return {
        "why": "The source doctor reported a condition outside the inspector's known historical signatures.",
        "runtime": "Treat as requiring manual inspection until the source doctor is understood.",
        "integrity": "Impact is undetermined; inspect the source detector and related local store manually.",
    }


def _counter_line(counter: Counter[str]) -> str:
    return ", ".join(f"{key}={counter[key]}" for key in sorted(counter)) if counter else "none"
