from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from proto_mind.command_registry import COMMAND_REGISTRY
from proto_mind.context_pack import ContextInjectionSettingsStore
from proto_mind.data_integrity import EXPORT_DIRS
from proto_mind.export_retention import ExportRetention
from proto_mind.memory_store import MemoryStore
from proto_mind.proto_status import ProtoOverview


DAILY_COMMANDS = ("/daily status", "/daily brief", "/daily doctor", "/daily next")
_SNAPSHOT_COMMANDS = (
    "/proto snapshot",
    "/proto snapshot-status",
    "/proto snapshot-diff",
    "/proto snapshot-diff-status",
)


def format_daily_command(command: str, *, project_root: Path, memory_store: MemoryStore) -> str | None:
    normalized = " ".join(command.strip().lower().split())
    if not normalized.startswith("/daily"):
        return None
    daily = DailyAgentLayer(project_root=project_root, memory_store=memory_store)
    if normalized == "/daily status":
        return daily.format_status()
    if normalized == "/daily brief":
        return daily.format_brief()
    if normalized == "/daily doctor":
        return daily.format_doctor()
    if normalized == "/daily next":
        return daily.format_next()
    return "Usage:\n  /daily status\n  /daily brief\n  /daily doctor\n  /daily next"


class DailyAgentLayer:
    def __init__(self, *, project_root: Path, memory_store: MemoryStore) -> None:
        self.project_root = project_root
        self.memory_store = memory_store
        self.exports = ExportRetention.from_project_root(project_root)
        self.proto = ProtoOverview(project_root=project_root, memory_store=memory_store)

    def format_status(self) -> str:
        export_inventory = self.exports.inventory()
        present = sum(1 for item in export_inventory if item["exists"])
        total_files = sum(item["file_count"] for item in export_inventory)
        total_size = sum(item["size_bytes"] for item in export_inventory)
        latest_snapshot = _latest_json(self.proto.snapshot_export_dir)
        latest_diff = _latest_json(self.proto.snapshot_diff_export_dir)
        settings = ContextInjectionSettingsStore.from_project_root(self.project_root).read_settings(initialize=False)
        categories = Counter(spec.category for spec in COMMAND_REGISTRY)
        baseline = _read_test_baseline(self.project_root)
        return "\n".join(
            [
                "Daily Agent Status",
                f"project_root: {self.project_root}",
                f"command_registry: commands={len(COMMAND_REGISTRY)} categories={len(categories)}",
                f"known_export_dirs: present={present}/{len(EXPORT_DIRS)} files={total_files} size_bytes={total_size}",
                f"latest_snapshot: {_latest_line(latest_snapshot)}",
                f"latest_snapshot_diff: {_latest_line(latest_diff)}",
                f"context_injection: {'enabled' if settings.get('enabled') else 'disabled'}",
                f"test_baseline: {baseline}",
                "",
                "Available commands:",
                "- /daily status",
                "- /daily brief",
                "- /daily doctor",
                "- /daily next",
                "",
                "Mutation policy:",
                "- Read-only status; no command, model, export, or store mutation was performed.",
            ]
        )

    def format_brief(self) -> str:
        doctors = self.proto._doctor_results()
        system_status = _overall_status(result["status"] for result in doctors.values())
        export_report = self.exports.doctor_report()
        latest_snapshot = _latest_json(self.proto.snapshot_export_dir)
        latest_diff = _latest_json(self.proto.snapshot_diff_export_dir)
        warnings = self.proto._warning_triage(doctors)
        settings = ContextInjectionSettingsStore.from_project_root(self.project_root).read_settings(initialize=False)
        focus = self.proto.loop.format_next()
        lines = [
            "Daily Operating Brief",
            f"System health: {system_status} ({_status_counts(doctors)})",
            f"Export health: {export_report['status']} (dirs={export_report['present_count']}/{len(EXPORT_DIRS)}, files={export_report['total_files']})",
            f"Context injection: {'enabled' if settings.get('enabled') else 'disabled'}",
            "",
            "Snapshot / Diff:",
            f"- latest snapshot: {_latest_line(latest_snapshot)}",
            f"- latest diff: {_latest_line(latest_diff)}",
            "",
            "Recent notable warnings:",
        ]
        if warnings:
            for item in warnings[:5]:
                lines.append(f"- [{item['category']}] {item['message']} (inspect: {item['inspect_command']})")
            if len(warnings) > 5:
                lines.append(f"- ... {len(warnings) - 5} more; run /proto warnings")
        else:
            lines.append("- none")
        lines.extend(["", "Current deterministic focus:", focus, "", "Safe focus for next work session:"])
        lines.extend(f"- {item}" for item in self._next_recommendations())
        lines.extend(
            [
                "",
                "Mutation policy:",
                "- Local deterministic brief only; no LLM/API call, background task, or write was performed.",
            ]
        )
        return "\n".join(lines)

    def format_doctor(self) -> str:
        report = self.doctor_report()
        lines = [
            "Daily Agent Doctor",
            f"Status: {report['status']}",
            "",
            "Checks:",
        ]
        lines.extend(f"- [{item['severity']}] {item['message']}" for item in report["findings"])
        lines.extend(
            [
                "",
                "Mutation policy:",
                "- Read-only diagnostics only; no daily action or cleanup command was executed.",
            ]
        )
        return "\n".join(lines)

    def doctor_report(self) -> dict[str, Any]:
        findings: list[dict[str, str]] = []
        by_prefix = {spec.prefix: spec for spec in COMMAND_REGISTRY}
        missing_daily = [command for command in DAILY_COMMANDS if command not in by_prefix]
        if missing_daily:
            findings.append({"severity": "ERROR", "message": f"Daily commands missing from registry: {', '.join(missing_daily)}"})
        else:
            findings.append({"severity": "OK", "message": "All required daily commands are registered."})
        unsafe_daily = [
            command
            for command in DAILY_COMMANDS
            if command in by_prefix and (not by_prefix[command].read_only or by_prefix[command].mutates != "none")
        ]
        if unsafe_daily:
            findings.append({"severity": "ERROR", "message": f"Daily commands are not read-only: {', '.join(unsafe_daily)}"})
        else:
            findings.append({"severity": "OK", "message": "Daily commands are registered as read-only, mutates=none."})

        export_report = self.exports.doctor_report()
        if len(self.exports.inventory()) != len(EXPORT_DIRS):
            findings.append({"severity": "ERROR", "message": "Export Retention inventory is not reachable or incomplete."})
        else:
            findings.append({"severity": "OK", "message": "Export Retention module is reachable."})
        if export_report["status"] != "OK":
            findings.append({"severity": "WARN", "message": f"Export Retention Doctor status is {export_report['status']}."})

        missing_snapshot = [command for command in _SNAPSHOT_COMMANDS if command not in by_prefix]
        if missing_snapshot:
            findings.append({"severity": "ERROR", "message": f"Snapshot commands unavailable: {', '.join(missing_snapshot)}"})
        else:
            findings.append({"severity": "OK", "message": "Snapshot and diff inspection commands are reachable."})

        settings = ContextInjectionSettingsStore.from_project_root(self.project_root).read_settings(initialize=False)
        if settings.get("enabled"):
            findings.append(
                {
                    "severity": "WARN",
                    "message": "Context Injection is enabled by operator configuration; Daily Layer did not change it.",
                }
            )
        else:
            findings.append({"severity": "OK", "message": "Context Injection is disabled."})

        cleanup = self.exports.format_cleanup_preview().lower()
        dangerous = [token for token in ("\nrm ", "\nmv ", "shutil.rmtree", "unlink(") if token in cleanup]
        export_specs = [spec for spec in COMMAND_REGISTRY if spec.category == "exports"]
        if dangerous or any(not spec.read_only or spec.mutates != "none" for spec in export_specs):
            findings.append({"severity": "ERROR", "message": "Dangerous or mutating export cleanup action is exposed."})
        else:
            findings.append({"severity": "OK", "message": "No deletion, move, repair, compression, or mutating cleanup action is exposed."})

        status = "ERROR" if any(item["severity"] == "ERROR" for item in findings) else "WARN" if any(item["severity"] == "WARN" for item in findings) else "OK"
        return {"status": status, "findings": findings}

    def format_next(self) -> str:
        recommendations = self._next_recommendations()
        lines = ["Daily Next", "Status: READY FOR OPERATOR REVIEW", "", "Suggested manual steps:"]
        lines.extend(f"{index}. {item}" for index, item in enumerate(recommendations, start=1))
        lines.extend(
            [
                "",
                "No automatic execution:",
                "- Suggestions were not run; no stores, exports, context settings, or queues were changed.",
            ]
        )
        return "\n".join(lines)

    def _next_recommendations(self) -> list[str]:
        export_report = self.exports.doctor_report()
        latest_snapshot = _latest_json(self.proto.snapshot_export_dir)
        latest_diff = _latest_json(self.proto.snapshot_diff_export_dir)
        settings = ContextInjectionSettingsStore.from_project_root(self.project_root).read_settings(initialize=False)
        warnings = self.proto._warning_triage()
        recommendations: list[str] = []
        if export_report["status"] != "OK":
            recommendations.append("Inspect export health manually with /exports doctor and /exports inventory.")
        if settings.get("enabled"):
            recommendations.append("Confirm Context Injection is intentionally enabled; disable it manually if the session should be context-free.")
        if latest_snapshot is None:
            recommendations.append("Create an operator snapshot manually with /proto snapshot-export.")
        elif latest_diff is None:
            recommendations.append("Review snapshot history and export a latest diff manually when two snapshots are available.")
        if warnings:
            recommendations.append("Review current warnings with /proto warnings before making structural changes.")
        recommendations.extend(
            [
                "Review the deterministic operating signal with /loop next.",
                "Run scripts/run_tests.sh before the next implementation milestone.",
                "Review PROTO_MIND_ARCHITECT_LEDGER.md and choose the next milestone explicitly.",
            ]
        )
        return recommendations


def _latest_json(directory: Path) -> dict[str, Any] | None:
    if not directory.exists():
        return None
    files = sorted(
        (path for path in directory.glob("*.json") if path.is_file()),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not files:
        return None
    path = files[0]
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        payload = {}
    return {
        "path": str(path),
        "filename": path.name,
        "generated_at": payload.get("generated_at") if isinstance(payload, dict) else None,
        "status": (
            payload.get("status") or payload.get("diff_status")
            if isinstance(payload, dict)
            else None
        ),
    }


def _latest_line(item: dict[str, Any] | None) -> str:
    if not item:
        return "none"
    return f"{item['filename']} generated_at={item.get('generated_at') or 'unknown'} status={item.get('status') or 'unknown'}"


def _read_test_baseline(project_root: Path) -> str:
    ledger = project_root / "PROTO_MIND_ARCHITECT_LEDGER.md"
    if not ledger.exists():
        return "not checked in this command"
    try:
        text = ledger.read_text(encoding="utf-8")
    except OSError:
        return "not checked in this command"
    match = re.search(r"Current test count:\s*(\d+) unit tests OK", text)
    return f"{match.group(1)} tests OK (Architect Ledger; not re-run by this command)" if match else "not checked in this command"


def _overall_status(statuses: Any) -> str:
    rank = {"OK": 0, "WARN": 1, "ERROR": 2}
    return max((str(status) for status in statuses), key=lambda status: rank.get(status, 2), default="OK")


def _status_counts(doctors: dict[str, dict[str, Any]]) -> str:
    counts = Counter(result["status"] for result in doctors.values())
    return ", ".join(f"{name}={counts.get(name, 0)}" for name in ("OK", "WARN", "ERROR"))
