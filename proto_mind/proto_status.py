from __future__ import annotations

import json
import re
import shlex
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from proto_mind.action_policy import format_policy_doctor
from proto_mind.action_preview import format_action_doctor
from proto_mind.action_queue import ActionProposalQueue
from proto_mind.command_registry import COMMAND_REGISTRY, format_command_doctor
from proto_mind.consolidation import ConsolidationPreview, ConsolidationQueue
from proto_mind.context_pack import ContextInjectionSettingsStore
from proto_mind.data_integrity import DataIntegrityDoctor
from proto_mind.memory_commands import format_memory_doctor
from proto_mind.memory_store import MemoryStore
from proto_mind.natural_commands import format_natural_doctor
from proto_mind.operating_loop import OperatingLoop


PROTO_STATUS_VERSION = "v1.4"
_SEVERITY_RANK = {"OK": 0, "WARN": 1, "ERROR": 2}
_TRIAGE_DOCTORS = (
    "/data doctor",
    "/data refs-doctor",
    "/consolidation queue-doctor",
    "/action queue-doctor",
    "/action readiness-doctor",
    "/action run-audit",
    "/memory doctor",
    "/loop doctor",
    "/natural doctor",
    "/commands doctor",
    "/policy doctor",
)


def format_proto_command(command: str, *, project_root: Path, memory_store: MemoryStore) -> str | None:
    normalized = " ".join(command.strip().lower().split())
    if not normalized.startswith("/proto"):
        return None
    overview = ProtoOverview(project_root=project_root, memory_store=memory_store)
    if normalized == "/proto status":
        return overview.format_status()
    if normalized == "/proto doctor":
        return overview.format_doctor()
    if normalized == "/proto next":
        return overview.format_next()
    if normalized == "/proto warnings":
        return overview.format_warnings()
    if normalized == "/proto warnings-explain":
        return overview.format_warnings_explain()
    if normalized == "/proto cleanup-preview":
        return overview.format_cleanup_preview()
    if normalized == "/proto snapshot":
        return overview.format_snapshot()
    if normalized == "/proto snapshot-export":
        return overview.export_snapshot()
    if normalized == "/proto snapshot-status":
        return overview.format_snapshot_status()
    if normalized == "/proto snapshot-list":
        return overview.format_snapshot_list()
    if normalized == "/proto snapshot-diff-status":
        return overview.format_snapshot_diff_status()
    if normalized == "/proto snapshot-diff-export-latest":
        return overview.export_snapshot_diff_latest()
    if normalized.startswith("/proto snapshot-diff-export"):
        parsed = _parse_snapshot_diff_command(command, prefix="/proto snapshot-diff-export")
        if isinstance(parsed, str):
            return parsed
        return overview.export_snapshot_diff(parsed[0], parsed[1])
    if normalized == "/proto snapshot-diff-latest":
        return overview.format_snapshot_diff_latest()
    if normalized.startswith("/proto snapshot-diff"):
        parsed = _parse_snapshot_diff_command(command)
        if isinstance(parsed, str):
            return parsed
        return overview.format_snapshot_diff(parsed[0], parsed[1])
    return (
        "Usage:\n"
        "  /proto status\n"
        "  /proto doctor\n"
        "  /proto next\n"
        "  /proto warnings\n"
        "  /proto warnings-explain\n"
        "  /proto cleanup-preview\n"
        "  /proto snapshot\n"
        "  /proto snapshot-export\n"
        "  /proto snapshot-status\n"
        "  /proto snapshot-list\n"
        "  /proto snapshot-diff <old_json_path_or_name> <new_json_path_or_name>\n"
        "  /proto snapshot-diff-latest\n"
        "  /proto snapshot-diff-export <old_json_path_or_name> <new_json_path_or_name>\n"
        "  /proto snapshot-diff-export-latest\n"
        "  /proto snapshot-diff-status"
    )


class ProtoOverview:
    def __init__(self, *, project_root: Path, memory_store: MemoryStore) -> None:
        self.project_root = project_root
        self.memory_store = memory_store
        self.loop = OperatingLoop.from_project_root(project_root)
        self.action_queue = ActionProposalQueue.from_project_root(project_root)

    @property
    def snapshot_export_dir(self) -> Path:
        return self.project_root / "proto_mind" / "exports" / "proto_snapshots"

    @property
    def snapshot_diff_export_dir(self) -> Path:
        return self.project_root / "proto_mind" / "exports" / "proto_snapshot_diffs"

    def format_status(self) -> str:
        snap = self.loop.snapshot()
        focused = _first(snap["focused_goals"])
        next_task = _best_next_task(snap["tasks_state"].records, focused)
        high_priority = [
            task
            for task in snap["tasks_state"].records
            if task.get("status") in {"open", "in_progress", "blocked"} and task.get("priority") == "high"
        ]
        identity = _read_identity_profile(self.project_root)
        memory = _read_memory_counts(self.memory_store.persistent_path)
        injection = ContextInjectionSettingsStore.from_project_root(self.project_root).read_settings(initialize=False)
        action_state = self.action_queue._read_state()
        action_records = action_state["records"]
        action_statuses = Counter(str(item.get("status") or "missing") for item in action_records)
        execution_states = Counter(_execution_state(item) for item in action_records)
        latest_executed = _latest_executed(action_records)
        doctors = self._doctor_results()
        selected = {
            name: doctors[name]["status"]
            for name in (
                "/data doctor",
                "/data refs-doctor",
                "/natural doctor",
                "/commands doctor",
                "/policy doctor",
                "/action queue-doctor",
                "/action readiness-doctor",
                "/action run-audit",
            )
        }
        warning_doctors = [f"{name}={status}" for name, status in selected.items() if status != "OK"]
        status = _overall_status(selected.values())
        lines = [
            "Proto-Mind System Status",
            f"Status: {status}",
            f"Overview version: {PROTO_STATUS_VERSION}",
            "",
            "Identity:",
            f"- system: {identity['name']} - {identity['role']}",
            f"- operator: {identity['operator_name'] or 'not set'}",
            "",
            "Focus:",
            f"- focused goal: {_goal_line(focused) if focused else 'none'}",
            f"- next task: {_task_line(next_task) if next_task else 'none'}",
            f"- open high-priority tasks: {len(high_priority)}",
            "",
            "Memory / Context:",
            f"- persistent records: {memory['total']}",
            f"- active records: {memory['active']}",
            f"- active explicit memories: {memory['active_explicit']}",
            f"- context injection: {'enabled' if injection.get('enabled') else 'disabled'}",
            "",
            "Health:",
        ]
        lines.extend(f"- {name}: {doctor_status}" for name, doctor_status in selected.items())
        lines.extend(
            [
                "",
                "Action State:",
                f"- proposals: total={len(action_records)} proposed={action_statuses['proposed']} approved={action_statuses['approved']}",
                f"- execution: confirmed={execution_states['confirmed']} executed={execution_states['executed']}",
                f"- latest executed action: {_action_line(latest_executed) if latest_executed else 'none'}",
                "",
                "Known warnings:",
            ]
        )
        lines.extend(f"- {item}" for item in warning_doctors or ["none"])
        lines.extend(["", "Mutation policy:", "- Read-only overview; no stores or queues were changed."])
        return "\n".join(lines)

    def format_doctor(self) -> str:
        doctors = self._doctor_results()
        overall = _overall_status(result["status"] for result in doctors.values())
        warnings: list[str] = []
        errors: list[str] = []
        for command, result in doctors.items():
            for finding in result["findings"][:3]:
                target = errors if finding["severity"] == "ERROR" else warnings
                target.append(f"{command}: {finding['message']}")
        lines = [
            "Proto-Mind System Doctor",
            f"Status: {overall}",
            f"Doctors checked: {len(doctors)}",
            "",
            "Doctor results:",
        ]
        lines.extend(f"- {command}: {result['status']}" for command, result in doctors.items())
        lines.extend(["", "Errors:"])
        lines.extend(_limited_findings(errors))
        lines.extend(["", "Warnings:"])
        lines.extend(_limited_findings(warnings))
        lines.extend(
            [
                "",
                "Mutation policy:",
                "- Aggregated read-only diagnostics only; no target commands or repairs were executed.",
            ]
        )
        return "\n".join(lines)

    def format_next(self) -> str:
        snap = self.loop.snapshot()
        focused = _first(snap["focused_goals"])
        next_task = _best_next_task(snap["tasks_state"].records, focused)
        action_state = self.action_queue._read_state()
        proposals = [item for item in action_state["records"] if item.get("status") == "proposed"]
        approved_unconfirmed = [
            item
            for item in action_state["records"]
            if item.get("status") == "approved" and _execution_state(item) == "unconfirmed"
        ]
        consolidation = ConsolidationPreview.from_project_root(self.project_root).build_preview_data()
        candidate_count = sum(
            len(consolidation[key])
            for key in ("memory_candidates", "skill_candidates", "followup_candidates")
        )
        suggestions = ["/loop next"]
        if proposals:
            suggestions.append("/action proposals")
        if approved_unconfirmed:
            suggestions.append(f"/action confirm-preview {approved_unconfirmed[0].get('id')}")
        if candidate_count:
            suggestions.append("/consolidation preview")
        suggestions.append("/proto doctor")
        lines = [
            "Proto-Mind Next",
            "Status: OK",
            "",
            "Operating Loop:",
            self.loop.format_next(),
            "",
            "Focus:",
            f"- focused goal: {_goal_line(focused) if focused else 'none'}",
            f"- next task: {_task_line(next_task) if next_task else 'none'}",
            "",
            "Pending Signals:",
            f"- proposed actions: {len(proposals)}",
            f"- approved but unconfirmed actions: {len(approved_unconfirmed)}",
            f"- consolidation candidates: {candidate_count}",
            "",
            "Suggested manual commands:",
        ]
        lines.extend(f"- {command}" for command in suggestions)
        lines.extend(["", "Mutation policy:", "- Read-only aggregation; suggested commands were not executed."])
        return "\n".join(lines)

    def format_warnings(self) -> str:
        items = self._warning_triage()
        status = _overall_status(item["doctor_status"] for item in items)
        lines = [
            "Proto-Mind Warning Triage",
            f"Status: {status}",
            f"Unique findings: {len(items)}",
            "",
            "Warnings / Errors:",
        ]
        if not items:
            lines.append("- none")
        for index, item in enumerate(items, start=1):
            lines.extend(
                [
                    f"{index}. source: {', '.join(item['sources'])}",
                    f"   source_status: {item['doctor_status']}",
                    f"   category: {item['category']}",
                    f"   severity: {item['severity']}",
                    f"   safe_to_ignore_temporarily: {'yes' if item['safe_to_ignore'] else 'no'}",
                    f"   summary: {item['message']}",
                    f"   inspect: {item['inspect_command']}",
                ]
            )
        lines.extend(
            [
                "",
                "Mutation policy:",
                "- Read-only triage only; warnings were not suppressed and no stores were changed.",
            ]
        )
        return "\n".join(lines)

    def format_warnings_explain(self) -> str:
        explanations = (
            (
                "legacy action receipt",
                "An action executed before receipt v2 lacks run_id, command-count, metadata, or hash fields.",
                "It is historical metadata debt, not evidence that the action ran again.",
                "Usually safe to keep temporarily when the command was read-only; integrity verification remains incomplete.",
                "/action run-receipt <action_id>; /action run-verify <action_id>",
                "No automatic repair exists; export with /action queue-export and preserve the legacy record.",
            ),
            (
                "old dangling consolidation reference",
                "An applied consolidation item points to a missing memory/skill id or lacks applied_record_id.",
                "Older apply receipts did not always capture the created target id.",
                "Usually historical, but rollback and cross-store verification cannot be proven.",
                "/consolidation queue-inspect <queue_id>; /data refs-doctor",
                "/consolidation queue-export, then optionally /consolidation queue-archive <queue_id> after review.",
            ),
            (
                "approved but unconfirmed action proposal",
                "The proposal was reviewed but has not passed the explicit confirmation gate.",
                "Approval and confirmation are intentionally separate lifecycle states.",
                "Safe to leave temporarily; no target command has executed.",
                "/action inspect <action_id>; /action confirm-preview <action_id>",
                "/action archive <action_id> or /action reject <action_id> \"reason\" if no longer needed.",
            ),
            (
                "legacy applied consolidation item without applied_record_id",
                "The queue records an apply result but cannot identify the exact target memory or skill.",
                "The original command result predates structured apply receipts or id extraction failed.",
                "Not immediately destructive, but automatic rollback must not be attempted.",
                "/consolidation queue-apply-receipt <queue_id>; /consolidation queue-inspect <queue_id>",
                "Export first; archive only after operator review. Do not fabricate an id.",
            ),
            (
                "policy drift",
                "Stored proposal policy differs from the current Command Registry or Action Safety Policy.",
                "Registry metadata or policy rules changed after proposal creation.",
                "Do not run until inspected and re-proposed under current policy.",
                "/action inspect <action_id>; /action run-preview <action_id>",
                "/action reject <action_id> \"policy drift\" or /action archive <action_id> after export.",
            ),
            (
                "missing store",
                "An expected local JSON/JSONL store does not exist.",
                "The module may be unused or its store has not yet been initialized.",
                "Often safe for optional empty modules; unexpected loss requires backup review.",
                "/data inventory; /data doctor",
                "No generic cleanup command; initialize through the owning module or restore from backup deliberately.",
            ),
            (
                "malformed json/jsonl",
                "A store contains invalid JSON or malformed JSONL records.",
                "A partial/manual write or filesystem interruption may have damaged the file.",
                "Potentially dangerous: mutating commands should remain refused until manually reviewed.",
                "/data inventory; /data doctor",
                "Create/export a backup, inspect the file manually, and use a module-specific recovery path; no auto-fix.",
            ),
        )
        lines = ["Proto-Mind Warning Explanations", "Status: OK"]
        for title, meaning, cause, danger, inspect, cleanup in explanations:
            lines.extend(
                [
                    "",
                    f"{title}:",
                    f"- meaning: {meaning}",
                    f"- why: {cause}",
                    f"- danger: {danger}",
                    f"- inspect: {inspect}",
                    f"- manual cleanup: {cleanup}",
                ]
            )
        lines.extend(["", "Mutation policy:", "- Explanations only; no commands were executed."])
        return "\n".join(lines)

    def format_cleanup_preview(self) -> str:
        items = self._warning_triage()
        preview = self._cleanup_preview_data(items)
        lines = [
            "Proto-Mind Cleanup Preview",
            f"Status: {'WARN' if items else 'OK'}",
            "",
            "1. Export before cleanup:",
        ]
        lines.extend(_command_bullets(preview["export_commands"]))
        lines.extend(["", "2. Inspect before deciding:"])
        lines.extend(_command_bullets(preview["inspect_commands"]))
        lines.extend(["", "3. Optional lifecycle cleanup after review:"])
        lines.extend(_command_bullets(preview["lifecycle_commands"]))
        lines.extend(["", "Notes:"])
        lines.extend(f"- {note}" for note in preview["notes"])
        lines.extend(
            [
                "",
                "Mutation policy:",
                "- Fully read-only preview; no queue, store, context, or session data was changed.",
            ]
        )
        return "\n".join(lines)

    def format_snapshot(self) -> str:
        return _render_snapshot_markdown(self.build_snapshot(), heading="Proto-Mind Snapshot")

    def format_snapshot_status(self) -> str:
        files = self._snapshot_export_files()
        stems = {path.stem for path in files}
        newest = files[0] if files else None
        newest_time = datetime.fromtimestamp(newest.stat().st_mtime, UTC).isoformat() if newest else "none"
        return "\n".join(
            [
                "Proto-Mind Snapshot Export Status",
                f"export_dir: {self.snapshot_export_dir}",
                f"exists: {self.snapshot_export_dir.exists()}",
                f"snapshot_sets: {len(stems)}",
                f"export_files: {len(files)}",
                f"newest_snapshot: {newest or 'none'}",
                f"newest_timestamp: {newest_time}",
                "",
                "Available commands:",
                "- /proto snapshot-status",
                "- /proto snapshot",
                "- /proto snapshot-export",
                "- /proto snapshot-list",
                "- /proto snapshot-diff <old> <new>",
                "- /proto snapshot-diff-latest",
                "",
                "Mutation policy:",
                "- Read-only status; the export directory was not created or changed.",
            ]
        )

    def format_snapshot_list(self) -> str:
        files = self._snapshot_json_files()
        lines = [
            "Proto-Mind Snapshot List",
            f"export_dir: {self.snapshot_export_dir}",
            f"json_snapshots: {len(files)}",
            "",
            "Snapshots:",
        ]
        if not files:
            lines.append("- none")
        for path in files:
            loaded = _load_snapshot_json(path)
            stat = path.stat()
            modified = datetime.fromtimestamp(stat.st_mtime, UTC).isoformat()
            if loaded["error"]:
                lines.append(
                    f"- {path.name} | error={loaded['error']} | size={stat.st_size} | modified={modified}"
                )
                continue
            data = loaded["data"]
            warning_summary = _snapshot_warning_summary(data)
            lines.append(
                "- "
                f"{path.name} | generated_at={data.get('generated_at') or 'unknown'} "
                f"| status={data.get('status') or 'unknown'} "
                f"| warnings={warning_summary['count']} "
                f"| categories={_format_mapping(warning_summary['categories'])} "
                f"| size={stat.st_size} | modified={modified}"
            )
        lines.extend(["", "Mutation policy:", "- Read-only list; snapshot files were not changed."])
        return "\n".join(lines)

    def format_snapshot_diff(self, old_reference: str, new_reference: str) -> str:
        payload, error = self._build_snapshot_diff_payload(old_reference, new_reference)
        if error:
            return _snapshot_diff_error(error)
        return _render_snapshot_diff_text(payload)

    def _build_snapshot_diff_payload(
        self, old_reference: str, new_reference: str
    ) -> tuple[dict[str, Any], str]:
        old_path, old_error = self._resolve_snapshot_reference(old_reference)
        if old_error:
            return {}, old_error
        new_path, new_error = self._resolve_snapshot_reference(new_reference)
        if new_error:
            return {}, new_error
        old_loaded = _load_snapshot_json(old_path)
        if old_loaded["error"]:
            return {}, f"Could not read old snapshot {old_path}: {old_loaded['error']}"
        new_loaded = _load_snapshot_json(new_path)
        if new_loaded["error"]:
            return {}, f"Could not read new snapshot {new_path}: {new_loaded['error']}"
        return _build_snapshot_diff_data(old_path, old_loaded["data"], new_path, new_loaded["data"]), ""

    def format_snapshot_diff_latest(self) -> str:
        files = self._snapshot_json_files()
        if len(files) < 2:
            return "\n".join(
                [
                    "Proto-Mind Snapshot Diff Latest",
                    f"Available JSON snapshots: {len(files)}",
                    "Need at least 2 snapshot JSON exports. Run /proto snapshot-export twice.",
                    "No snapshot files were modified.",
                ]
            )
        return self.format_snapshot_diff(str(files[1]), str(files[0]))

    def format_snapshot_diff_status(self) -> str:
        files = self._snapshot_diff_export_files()
        stems = {path.stem for path in files}
        newest = files[0] if files else None
        newest_time = datetime.fromtimestamp(newest.stat().st_mtime, UTC).isoformat() if newest else "none"
        return "\n".join(
            [
                "Proto-Mind Snapshot Diff Export Status",
                f"export_dir: {self.snapshot_diff_export_dir}",
                f"exists: {self.snapshot_diff_export_dir.exists()}",
                f"diff_export_sets: {len(stems)}",
                f"export_files: {len(files)}",
                f"newest_diff_export: {newest or 'none'}",
                f"newest_timestamp: {newest_time}",
                "",
                "Available commands:",
                "- /proto snapshot-diff-status",
                "- /proto snapshot-diff-export <old> <new>",
                "- /proto snapshot-diff-export-latest",
                "",
                "Mutation policy:",
                "- Read-only status; no export or snapshot files were changed.",
            ]
        )

    def export_snapshot_diff(self, old_reference: str, new_reference: str) -> str:
        payload, error = self._build_snapshot_diff_payload(old_reference, new_reference)
        if error:
            return _snapshot_diff_export_error(error)
        self.snapshot_diff_export_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.fromisoformat(payload["generated_at"]).strftime("%Y%m%d_%H%M%S")
        stem = f"proto_snapshot_diff_{stamp}_{uuid4().hex[:6]}"
        markdown_path = self.snapshot_diff_export_dir / f"{stem}.md"
        json_path = self.snapshot_diff_export_dir / f"{stem}.json"
        _atomic_write_text(markdown_path, _render_snapshot_diff_markdown(payload) + "\n")
        _atomic_write_text(json_path, json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
        return "\n".join(
            [
                "Proto-Mind Snapshot Diff Export",
                f"generated_at: {payload['generated_at']}",
                f"diff_status: {payload['diff_status']}",
                f"changed_sections: {', '.join(payload['changed_sections']) or 'none'}",
                f"markdown: {markdown_path}",
                f"json: {json_path}",
                "no_mutation: true",
                "Only diff export files were created; snapshots and core stores were not changed.",
            ]
        )

    def export_snapshot_diff_latest(self) -> str:
        files = self._snapshot_json_files()
        if len(files) < 2:
            return "\n".join(
                [
                    "Proto-Mind Snapshot Diff Export Latest",
                    f"Available JSON snapshots: {len(files)}",
                    "Need at least 2 snapshot JSON exports. Run /proto snapshot-export twice.",
                    "No diff export files were created.",
                ]
            )
        return self.export_snapshot_diff(str(files[1]), str(files[0]))

    def _snapshot_export_files(self) -> list[Path]:
        if not self.snapshot_export_dir.exists():
            return []
        return sorted(
            (path for path in self.snapshot_export_dir.glob("proto_snapshot_*") if path.is_file()),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )

    def _snapshot_json_files(self) -> list[Path]:
        return [path for path in self._snapshot_export_files() if path.suffix.lower() == ".json"]

    def _snapshot_diff_export_files(self) -> list[Path]:
        if not self.snapshot_diff_export_dir.exists():
            return []
        return sorted(
            (path for path in self.snapshot_diff_export_dir.glob("proto_snapshot_diff_*") if path.is_file()),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )

    def _resolve_snapshot_reference(self, reference: str) -> tuple[Path, str]:
        raw = reference.strip()
        if not raw:
            return Path(), "Snapshot reference is empty."
        requested = Path(raw).expanduser()
        if requested.is_absolute():
            path = requested
        else:
            if requested.name != raw or requested.parent != Path("."):
                return Path(), "Relative snapshot references must be filenames within the proto_snapshots export directory."
            path = self.snapshot_export_dir / requested.name
        if path.suffix.lower() != ".json":
            return path, f"Snapshot diff accepts JSON files only: {path}"
        if not path.exists():
            return path, f"Snapshot JSON file not found: {path}"
        if not path.is_file():
            return path, f"Snapshot reference is not a file: {path}"
        return path.resolve(), ""

    def export_snapshot(self) -> str:
        self.snapshot_export_dir.mkdir(parents=True, exist_ok=True)
        data = self.build_snapshot()
        stamp = datetime.fromisoformat(data["generated_at"]).strftime("%Y%m%d_%H%M%S")
        suffix = uuid4().hex[:6]
        stem = f"proto_snapshot_{stamp}_{suffix}"
        markdown_path = self.snapshot_export_dir / f"{stem}.md"
        json_path = self.snapshot_export_dir / f"{stem}.json"
        _atomic_write_text(markdown_path, _render_snapshot_markdown(data, heading="# Proto-Mind Snapshot") + "\n")
        _atomic_write_text(json_path, json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
        return "\n".join(
            [
                "Proto-Mind Snapshot Export",
                f"generated_at: {data['generated_at']}",
                f"status: {data['status']}",
                f"markdown: {markdown_path}",
                f"json: {json_path}",
                f"warnings: {len(data['warnings'])}",
                "no_mutation: true",
                "Only snapshot export files were created; no core stores or queues were changed.",
            ]
        )

    def build_snapshot(self) -> dict[str, Any]:
        generated_at = datetime.now(UTC).isoformat()
        loop_snapshot = self.loop.snapshot()
        focused = _first(loop_snapshot["focused_goals"])
        tasks = loop_snapshot["tasks_state"].records
        open_tasks = [task for task in tasks if task.get("status") in {"open", "in_progress", "blocked"}]
        next_task = _best_next_task(tasks, focused)
        memory = _read_memory_counts(self.memory_store.persistent_path)
        identity = _read_identity_profile(self.project_root)
        injection = ContextInjectionSettingsStore.from_project_root(self.project_root).read_settings(initialize=False)
        doctors = self._doctor_results()
        doctor_status = _overall_status(result["status"] for result in doctors.values())
        warnings = self._warning_triage(doctors)
        cleanup = self._cleanup_preview_data(warnings)
        action_state = self.action_queue._read_state()
        action_records = action_state["records"]
        action_statuses = Counter(str(item.get("status") or "missing") for item in action_records)
        execution_states = Counter(_execution_state(item) for item in action_records)
        latest_executed = _latest_executed(action_records)
        run_audit = self.action_queue.run_audit_report()
        consolidation_queue = ConsolidationQueue.from_project_root(self.project_root)
        consolidation_state = consolidation_queue._read_state()
        consolidation_statuses = Counter(
            str(item.get("status") or "missing") for item in consolidation_state["records"]
        )
        consolidation_preview = ConsolidationPreview.from_project_root(self.project_root).build_preview_data()
        candidate_count = sum(
            len(consolidation_preview[key])
            for key in ("memory_candidates", "skill_candidates", "followup_candidates")
        )
        proposed = [item for item in action_records if item.get("status") == "proposed"]
        approved_unconfirmed = [
            item
            for item in action_records
            if item.get("status") == "approved" and _execution_state(item) == "unconfirmed"
        ]
        next_commands = ["/loop next"]
        if proposed:
            next_commands.append("/action proposals")
        if approved_unconfirmed:
            next_commands.append(f"/action confirm-preview {approved_unconfirmed[0].get('id')}")
        if candidate_count:
            next_commands.append("/consolidation preview")
        next_commands.append("/proto doctor")
        return {
            "generated_at": generated_at,
            "status": doctor_status,
            "identity": identity,
            "focus": {
                "focused_goal": _compact_goal(focused),
                "next_task": _compact_task(next_task),
            },
            "task_summary": {
                "open_total": len(open_tasks),
                "open_high_priority": sum(1 for task in open_tasks if task.get("priority") == "high"),
                "status_counts": dict(sorted(Counter(str(task.get("status") or "missing") for task in tasks).items())),
            },
            "memory_summary": memory,
            "context_injection": {
                "enabled": bool(injection.get("enabled")),
                "mode": str(injection.get("mode") or "preview_safe"),
                "max_chars": int(injection.get("max_chars") or 0),
                "health": "ERROR" if injection.get("error") else "OK",
            },
            "doctor_summary": {
                "overall_status": doctor_status,
                "doctors": {command: result["status"] for command, result in doctors.items()},
            },
            "registry_summary": {"registered_commands": len(COMMAND_REGISTRY)},
            "warnings": warnings,
            "warning_summary": {
                "count": len(warnings),
                "categories": dict(sorted(Counter(item["category"] for item in warnings).items())),
                "errors": sum(1 for item in warnings if item["severity"] == "error"),
            },
            "cleanup_preview": cleanup,
            "action_summary": {
                "path": str(self.action_queue.queue_path),
                "total": len(action_records),
                "status_counts": dict(sorted(action_statuses.items())),
                "execution_state_counts": dict(sorted(execution_states.items())),
                "malformed_count": action_state["malformed_count"],
                "error": action_state["error"],
                "latest_executed": _compact_action(latest_executed),
            },
            "action_run_audit_summary": {
                key: value for key, value in run_audit.items() if key != "findings"
            },
            "consolidation_summary": {
                "path": str(consolidation_queue.queue_path),
                "total": len(consolidation_state["records"]),
                "status_counts": dict(sorted(consolidation_statuses.items())),
                "malformed_count": consolidation_state["malformed_count"],
                "error": consolidation_state["error"],
                "candidate_count": candidate_count,
            },
            "next_summary": {
                "focused_goal": _compact_goal(focused),
                "next_task": _compact_task(next_task),
                "proposed_actions": len(proposed),
                "approved_unconfirmed_actions": len(approved_unconfirmed),
                "consolidation_candidates": candidate_count,
                "suggested_commands": next_commands,
            },
            "source_notes": [
                "Deterministic snapshot assembled from existing local stores and read-only doctor APIs.",
                "Warning classification is heuristic and signature-based; source doctor output remains authoritative.",
                "Cleanup commands are suggestions for operator review and were not executed.",
            ],
            "no_mutation": True,
        }

    def _cleanup_preview_data(self, items: list[dict[str, Any]]) -> dict[str, Any]:
        action_state = self.action_queue._read_state()
        approved_unconfirmed = [
            item
            for item in action_state["records"]
            if item.get("status") == "approved" and _execution_state(item) == "unconfirmed"
        ]
        legacy_action_ids = _ids_from_triage(items, "act_", category="legacy")
        other_action_ids = [
            item_id for item_id in _ids_from_triage(items, "act_") if item_id not in legacy_action_ids
        ]
        consolidation_ids = _ids_from_triage(items, "cq_")
        has_action = bool(
            legacy_action_ids
            or other_action_ids
            or approved_unconfirmed
            or any("/action " in source for item in items for source in item["sources"])
        )
        has_consolidation = bool(
            consolidation_ids
            or any("consolidation" in source or item["category"] == "dangling_ref" for item in items for source in item["sources"])
        )
        exports: list[str] = []
        if has_action:
            exports.append("/action queue-export")
        if has_consolidation:
            exports.append("/consolidation queue-export")
        inspect: list[str] = []
        for item_id in legacy_action_ids:
            inspect.extend([f"/action run-receipt {item_id}", f"/action run-verify {item_id}"])
        for item_id in other_action_ids:
            inspect.append(f"/action inspect {item_id}")
        for item_id in consolidation_ids:
            inspect.append(f"/consolidation queue-inspect {item_id}")
        for item in approved_unconfirmed:
            command = f"/action inspect {item.get('id')}"
            if command not in inspect:
                inspect.append(command)
        lifecycle: list[str] = []
        for item in approved_unconfirmed:
            lifecycle.append(f"/action archive {item.get('id')}")
        for item_id in consolidation_ids:
            lifecycle.append(f"/consolidation queue-archive {item_id}")
        return {
            "export_commands": exports,
            "inspect_commands": inspect,
            "lifecycle_commands": lifecycle,
            "notes": [
                "Legacy action receipt metadata is never auto-repaired; archiving does not make its hash verifiable.",
                "Archiving a legacy applied consolidation item removes it from active receipt-reference checks but does not reconstruct applied_record_id.",
                "Reject/archive commands are suggestions only and were not executed.",
            ],
        }

    def _warning_triage(self, doctors: dict[str, dict[str, Any]] | None = None) -> list[dict[str, Any]]:
        doctors = doctors or self._doctor_results()
        grouped: dict[str, dict[str, Any]] = {}
        for source in _TRIAGE_DOCTORS:
            result = doctors[source]
            if result["status"] == "OK":
                continue
            for finding in result["findings"]:
                message = finding["message"].strip()
                key = " ".join(message.lower().split())
                if key in grouped:
                    grouped[key]["sources"].append(source)
                    grouped[key]["doctor_status"] = _overall_status(
                        (grouped[key]["doctor_status"], result["status"])
                    )
                    continue
                category = _warning_category(source, message)
                grouped[key] = {
                    "sources": [source],
                    "doctor_status": result["status"],
                    "message": message,
                    "category": category,
                    "severity": "error" if finding["severity"] == "ERROR" else "warn",
                    "safe_to_ignore": _safe_to_ignore(category, message, finding["severity"]),
                    "inspect_command": _warning_inspect_command(source, message, category),
                }
        return list(grouped.values())

    def _doctor_results(self) -> dict[str, dict[str, Any]]:
        data = DataIntegrityDoctor.from_project_root(self.project_root)
        consolidation_queue = ConsolidationQueue.from_project_root(self.project_root)
        checks: tuple[tuple[str, Callable[[], str]], ...] = (
            ("/data doctor", data.format_doctor),
            ("/data refs-doctor", data.format_references_doctor),
            ("/loop doctor", self.loop.format_doctor),
            ("/memory doctor", lambda: format_memory_doctor(self.memory_store)),
            ("/consolidation queue-doctor", consolidation_queue.format_doctor),
            ("/natural doctor", format_natural_doctor),
            ("/commands doctor", format_command_doctor),
            ("/policy doctor", format_policy_doctor),
            ("/action doctor", format_action_doctor),
            ("/action queue-doctor", self.action_queue.format_doctor),
            ("/action readiness-doctor", self.action_queue.format_readiness_doctor),
            ("/action run-audit", self.action_queue.format_run_audit),
        )
        results: dict[str, dict[str, Any]] = {}
        for command, check in checks:
            try:
                output = check()
            except Exception as exc:  # Keep the top-level doctor available when one subsystem is broken.
                results[command] = {
                    "status": "ERROR",
                    "findings": [{"severity": "ERROR", "message": f"doctor failed: {exc}"}],
                }
                continue
            results[command] = _parse_doctor_output(output)
        return results


def _parse_doctor_output(output: str) -> dict[str, Any]:
    status = "ERROR"
    findings: list[dict[str, str]] = []
    for line in output.splitlines():
        stripped = line.strip()
        if stripped.startswith("Status:"):
            candidate = stripped.split(":", 1)[1].strip().upper()
            if candidate in _SEVERITY_RANK:
                status = candidate
        if "[WARN]" in stripped:
            findings.append({"severity": "WARN", "message": stripped.split("[WARN]", 1)[1].strip()})
        elif "[ERROR]" in stripped:
            findings.append({"severity": "ERROR", "message": stripped.split("[ERROR]", 1)[1].strip()})
    if status == "ERROR" and not findings and "Status:" not in output:
        findings.append({"severity": "ERROR", "message": "doctor output did not contain a valid status"})
    return {"status": status, "findings": findings}


def _read_identity_profile(project_root: Path) -> dict[str, str]:
    fallback = {"name": "Proto-Mind", "role": "local-first cognitive assistant", "operator_name": ""}
    path = project_root / "proto_mind" / "data" / "identity.json"
    if not path.exists():
        return fallback
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return fallback
    profile = data.get("profile") if isinstance(data, dict) else None
    if not isinstance(profile, dict):
        return fallback
    return {
        "name": str(profile.get("name") or fallback["name"]),
        "role": str(profile.get("role") or fallback["role"]),
        "operator_name": str(profile.get("operator_name") or ""),
    }


def _read_memory_counts(path: Path) -> dict[str, int]:
    result = {"total": 0, "active": 0, "active_explicit": 0}
    if not path.exists():
        return result
    try:
        records = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return result
    if not isinstance(records, list):
        return result
    typed = [record for record in records if isinstance(record, dict)]
    active = [record for record in typed if record.get("active", True) is not False]
    result["total"] = len(typed)
    result["active"] = len(active)
    result["active_explicit"] = sum(1 for record in active if record.get("type") == "explicit")
    return result


def _best_next_task(tasks: list[dict[str, Any]], focused: dict[str, Any] | None) -> dict[str, Any] | None:
    def key(task: dict[str, Any]) -> tuple[int, int, str]:
        status_rank = 0 if task.get("status") == "in_progress" else 1
        priority_rank = {"high": 0, "normal": 1, "low": 2}.get(str(task.get("priority") or "normal"), 1)
        return status_rank, priority_rank, str(task.get("created_at") or "")

    in_progress = [task for task in tasks if task.get("status") == "in_progress"]
    if in_progress:
        return sorted(in_progress, key=key)[0]
    if focused:
        focused_open = [
            task for task in tasks if task.get("status") == "open" and task.get("goal_id") == focused.get("id")
        ]
        if focused_open:
            return sorted(focused_open, key=key)[0]
    open_tasks = [task for task in tasks if task.get("status") == "open"]
    return sorted(open_tasks, key=key)[0] if open_tasks else None


def _execution_state(item: dict[str, Any]) -> str:
    return str(item.get("execution_state") or "unconfirmed")


def _latest_executed(records: list[dict[str, Any]]) -> dict[str, Any] | None:
    executed = [item for item in records if _execution_state(item) == "executed"]
    return max(executed, key=lambda item: str(item.get("executed_at") or ""), default=None)


def _overall_status(statuses: Any) -> str:
    return max((str(status) for status in statuses), key=lambda status: _SEVERITY_RANK.get(status, 2), default="OK")


def _limited_findings(findings: list[str], *, limit: int = 20) -> list[str]:
    if not findings:
        return ["- none"]
    lines = [f"- {finding}" for finding in findings[:limit]]
    if len(findings) > limit:
        lines.append(f"- ... {len(findings) - limit} more")
    return lines


def _first(records: list[dict[str, Any]]) -> dict[str, Any] | None:
    return records[0] if records else None


def _goal_line(goal: dict[str, Any]) -> str:
    return f"{goal.get('id')} [{goal.get('status')}] {goal.get('title')}"


def _task_line(task: dict[str, Any]) -> str:
    return f"{task.get('id')} [{task.get('status')}] priority={task.get('priority')} {task.get('title')}"


def _action_line(item: dict[str, Any]) -> str:
    return f"{item.get('id')} run_id={item.get('run_id') or 'none'} executed_at={item.get('executed_at') or 'unknown'}"


def _warning_category(source: str, message: str) -> str:
    lowered = message.lower()
    if source.startswith("/action ") and any(
        marker in lowered
        for marker in ("missing run_id", "missing executed_command_count", "missing receipt_hash", "missing metadata")
    ):
        return "legacy"
    if "missing applied_record_id" in lowered or "references missing" in lowered:
        return "dangling_ref"
    if any(
        marker in lowered
        for marker in (
            "policy mismatch",
            "policy drift",
            "current policy",
            "stored policy",
            "not auto_allowed",
            "not read-only",
            "declares mutation target",
        )
    ):
        return "policy_drift"
    if any(
        marker in lowered
        for marker in (
            "missing expected store",
            "export directory missing",
            "backup directory missing",
            "malformed",
            "invalid json",
            "unreadable",
            "read error",
        )
    ):
        return "data_integrity"
    if any(marker in lowered for marker in ("approved but unconfirmed", "old proposed", "duplicate proposal", "invalid status")):
        return "queue_hygiene"
    if "queue" in source:
        return "queue_hygiene"
    return "unknown"


def _safe_to_ignore(category: str, message: str, severity: str) -> bool:
    if severity == "ERROR":
        return False
    if category in {"legacy", "dangling_ref", "queue_hygiene"}:
        return True
    if category == "data_integrity":
        lowered = message.lower()
        return any(marker in lowered for marker in ("missing expected store", "export directory missing", "backup directory missing"))
    return False


def _warning_inspect_command(source: str, message: str, category: str) -> str:
    action_id = _first_id(message, "act_")
    queue_id = _first_id(message, "cq_")
    if category == "legacy" and action_id:
        return f"/action run-receipt {action_id}"
    if category == "dangling_ref" and queue_id:
        return f"/consolidation queue-inspect {queue_id}"
    if source.startswith("/action ") and action_id:
        return f"/action inspect {action_id}"
    if source.startswith("/consolidation ") and queue_id:
        return f"/consolidation queue-inspect {queue_id}"
    if category in {"data_integrity", "dangling_ref"}:
        return "/data inventory"
    return source


def _first_id(text: str, prefix: str) -> str:
    match = re.search(rf"\b{re.escape(prefix)}[A-Za-z0-9_]+\b", text)
    return match.group(0) if match else ""


def _ids_from_triage(items: list[dict[str, Any]], prefix: str, *, category: str | None = None) -> list[str]:
    ids: list[str] = []
    for item in items:
        if category is not None and item.get("category") != category:
            continue
        item_id = _first_id(item["message"], prefix)
        if item_id and item_id not in ids:
            ids.append(item_id)
    return ids


def _command_bullets(commands: list[str]) -> list[str]:
    return [f"- {command}" for command in commands] if commands else ["- none"]


def _compact_goal(goal: dict[str, Any] | None) -> dict[str, Any] | None:
    if not goal:
        return None
    return {
        "id": goal.get("id"),
        "title": goal.get("title"),
        "status": goal.get("status"),
        "priority": goal.get("priority"),
        "focus": bool(goal.get("focus")),
    }


def _compact_task(task: dict[str, Any] | None) -> dict[str, Any] | None:
    if not task:
        return None
    return {
        "id": task.get("id"),
        "title": task.get("title"),
        "status": task.get("status"),
        "priority": task.get("priority"),
        "goal_id": task.get("goal_id"),
    }


def _compact_action(item: dict[str, Any] | None) -> dict[str, Any] | None:
    if not item:
        return None
    return {
        "id": item.get("id"),
        "run_id": item.get("run_id"),
        "executed_at": item.get("executed_at"),
        "original_input": item.get("original_input"),
        "commands": item.get("commands") if isinstance(item.get("commands"), list) else [],
    }


def _render_snapshot_markdown(data: dict[str, Any], *, heading: str) -> str:
    identity = data["identity"]
    focus = data["focus"]
    tasks = data["task_summary"]
    memory = data["memory_summary"]
    context = data["context_injection"]
    warnings = data["warnings"]
    warning_summary = data["warning_summary"]
    action = data["action_summary"]
    audit = data["action_run_audit_summary"]
    consolidation = data["consolidation_summary"]
    next_summary = data["next_summary"]
    cleanup = data["cleanup_preview"]
    lines = [
        heading,
        f"Generated: {data['generated_at']}",
        f"Status: {data['status']}",
        "",
        "## Identity",
        f"- System: {identity['name']} - {identity['role']}",
        f"- Operator: {identity['operator_name'] or 'not set'}",
        "",
        "## Focus And Tasks",
        f"- Focused goal: {_compact_record_line(focus['focused_goal'], 'title')}",
        f"- Next task: {_compact_record_line(focus['next_task'], 'title')}",
        f"- Open tasks: {tasks['open_total']}",
        f"- Open high-priority tasks: {tasks['open_high_priority']}",
        "",
        "## Memory And Context",
        f"- Persistent records: {memory['total']}",
        f"- Active records: {memory['active']}",
        f"- Active explicit memories: {memory['active_explicit']}",
        f"- Context injection: {'enabled' if context['enabled'] else 'disabled'} ({context['mode']}, max_chars={context['max_chars']})",
        f"- Registered commands: {_as_dict(data.get('registry_summary')).get('registered_commands', 'unknown')}",
        "",
        "## Doctor Summary",
        f"- Overall: {data['doctor_summary']['overall_status']}",
    ]
    lines.extend(
        f"- {command}: {status}"
        for command, status in data["doctor_summary"]["doctors"].items()
    )
    lines.extend(
        [
            "",
            "## Warning Summary",
            f"- Findings: {warning_summary['count']}",
            f"- Categories: {_format_mapping(warning_summary['categories'])}",
            f"- Errors: {warning_summary['errors']}",
        ]
    )
    if warnings:
        for item in warnings[:20]:
            lines.append(
                f"- [{item['severity']}] {item['category']} | {', '.join(item['sources'])} | {item['message']}"
            )
    else:
        lines.append("- none")
    lines.extend(
        [
            "",
            "## Action Queue",
            f"- Total: {action['total']}",
            f"- Statuses: {_format_mapping(action['status_counts'])}",
            f"- Execution states: {_format_mapping(action['execution_state_counts'])}",
            f"- Latest executed: {_compact_record_line(action['latest_executed'], 'original_input')}",
            "",
            "## Action Run Audit",
            f"- Status: {audit['status']}",
            f"- Executed: {audit['executed_count']}",
            f"- Receipt v2: {audit['v2_count']}",
            f"- Legacy receipts: {audit['legacy_count']}",
            f"- Hash verified: {audit['hash_verified_count']}",
            f"- Hash mismatch: {audit['hash_mismatch_count']}",
            "",
            "## Consolidation Queue",
            f"- Total: {consolidation['total']}",
            f"- Statuses: {_format_mapping(consolidation['status_counts'])}",
            f"- Consolidation candidates: {consolidation['candidate_count']}",
            "",
            "## Next Summary",
            f"- Focused goal: {_compact_record_line(next_summary['focused_goal'], 'title')}",
            f"- Next task: {_compact_record_line(next_summary['next_task'], 'title')}",
            f"- Proposed actions: {next_summary['proposed_actions']}",
            f"- Approved unconfirmed actions: {next_summary['approved_unconfirmed_actions']}",
            f"- Consolidation candidates: {next_summary['consolidation_candidates']}",
            "- Suggested commands:",
        ]
    )
    lines.extend(f"  - `{command}`" for command in next_summary["suggested_commands"])
    lines.extend(["", "## Cleanup Preview", "- Export first:"])
    lines.extend(f"  - `{command}`" for command in cleanup["export_commands"] or ["none"])
    lines.append("- Inspect:")
    lines.extend(f"  - `{command}`" for command in cleanup["inspect_commands"] or ["none"])
    lines.append("- Optional lifecycle cleanup:")
    lines.extend(f"  - `{command}`" for command in cleanup["lifecycle_commands"] or ["none"])
    lines.extend(["", "## Source Notes"])
    lines.extend(f"- {note}" for note in data["source_notes"])
    lines.extend(["", "## Mutation Policy", "- no_mutation: true", "- Snapshot generation did not mutate core stores or execute actions."])
    return "\n".join(lines)


def _compact_record_line(record: dict[str, Any] | None, label_field: str) -> str:
    if not record:
        return "none"
    return f"{record.get('id')} [{record.get('status', 'unknown')}] {record.get(label_field) or ''}".strip()


def _format_mapping(values: dict[str, Any]) -> str:
    return ", ".join(f"{key}={value}" for key, value in values.items()) if values else "none"


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    temp_path.write_text(text, encoding="utf-8")
    temp_path.replace(path)


def _parse_snapshot_diff_command(command: str, *, prefix: str = "/proto snapshot-diff") -> tuple[str, str] | str:
    try:
        parts = shlex.split(command)
    except ValueError as exc:
        return f"Snapshot diff parse error: {exc}\nUsage: {prefix} <old_json_path_or_name> <new_json_path_or_name>"
    prefix_parts = shlex.split(prefix)
    if len(parts) != len(prefix_parts) + 2 or parts[: len(prefix_parts)] != prefix_parts:
        return f"Usage: {prefix} <old_json_path_or_name> <new_json_path_or_name>"
    return parts[-2], parts[-1]


def _load_snapshot_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        return {"data": {}, "error": f"read error: {exc}"}
    except json.JSONDecodeError as exc:
        return {"data": {}, "error": f"invalid JSON: {exc}"}
    if not isinstance(payload, dict):
        return {"data": {}, "error": "snapshot root is not an object"}
    return {"data": payload, "error": ""}


def _snapshot_warning_summary(data: dict[str, Any]) -> dict[str, Any]:
    summary = _as_dict(data.get("warning_summary"))
    warnings = data.get("warnings") if isinstance(data.get("warnings"), list) else []
    categories = _as_dict(summary.get("categories"))
    if not categories:
        categories = dict(
            sorted(
                Counter(
                    str(item.get("category") or "unknown")
                    for item in warnings
                    if isinstance(item, dict)
                ).items()
            )
        )
    count = summary.get("count")
    if not isinstance(count, int):
        count = len(warnings)
    return {"count": count, "categories": categories}


def _snapshot_diff_error(message: str) -> str:
    return "\n".join(
        [
            "Proto-Mind Snapshot Diff",
            "Status: ERROR",
            f"Error: {message}",
            "No snapshot files were modified.",
        ]
    )


def _snapshot_diff_export_error(message: str) -> str:
    return "\n".join(
        [
            "Proto-Mind Snapshot Diff Export",
            "Status: ERROR",
            f"Error: {message}",
            "No diff export files were created.",
        ]
    )


_DIFF_SECTION_TITLES = {
    "overall_status": "Overall Status",
    "doctor_status": "Doctor Status Changes",
    "warnings": "Warning Changes",
    "action": "Action Summary Changes",
    "consolidation": "Consolidation Summary Changes",
    "context_injection": "Context Injection Changes",
    "memory_task_focus": "Memory / Task / Focus Changes",
    "registry": "Registry Changes",
    "source_metadata": "Source Metadata Changes",
}


def _build_snapshot_diff_data(
    old_path: Path, old: dict[str, Any], new_path: Path, new: dict[str, Any]
) -> dict[str, Any]:
    sections: dict[str, list[dict[str, Any]]] = {key: [] for key in _DIFF_SECTION_TITLES}
    changed_fields = 0

    def add(section: str, field: str, old_value: Any, new_value: Any, *, always: bool = False) -> None:
        nonlocal changed_fields
        changed = old_value != new_value
        if changed:
            changed_fields += 1
        if changed or always:
            sections[section].append(
                {"field": field, "old": old_value, "new": new_value, "changed": changed}
            )

    def add_mapping(section: str, field: str, old_values: Any, new_values: Any) -> None:
        old_map = _as_dict(old_values)
        new_map = _as_dict(new_values)
        for key in sorted(set(old_map) | set(new_map)):
            add(section, f"{field}.{key}", old_map.get(key, 0), new_map.get(key, 0))

    add("overall_status", "status", old.get("status", "unknown"), new.get("status", "unknown"), always=True)
    add_mapping(
        "doctor_status",
        "doctor",
        _as_dict(old.get("doctor_summary")).get("doctors"),
        _as_dict(new.get("doctor_summary")).get("doctors"),
    )
    old_warnings = _snapshot_warning_summary(old)
    new_warnings = _snapshot_warning_summary(new)
    add("warnings", "warning_count", old_warnings["count"], new_warnings["count"])
    add_mapping("warnings", "category", old_warnings["categories"], new_warnings["categories"])

    old_action = _as_dict(old.get("action_summary"))
    new_action = _as_dict(new.get("action_summary"))
    add("action", "total", old_action.get("total"), new_action.get("total"))
    add_mapping("action", "status", old_action.get("status_counts"), new_action.get("status_counts"))
    add_mapping("action", "execution_state", old_action.get("execution_state_counts"), new_action.get("execution_state_counts"))
    add(
        "action",
        "latest_executed_id",
        _as_dict(old_action.get("latest_executed")).get("id"),
        _as_dict(new_action.get("latest_executed")).get("id"),
    )

    old_consolidation = _as_dict(old.get("consolidation_summary"))
    new_consolidation = _as_dict(new.get("consolidation_summary"))
    add("consolidation", "total", old_consolidation.get("total"), new_consolidation.get("total"))
    add_mapping("consolidation", "status", old_consolidation.get("status_counts"), new_consolidation.get("status_counts"))
    add(
        "consolidation",
        "candidate_count",
        old_consolidation.get("candidate_count"),
        new_consolidation.get("candidate_count"),
    )

    old_context = _as_dict(old.get("context_injection"))
    new_context = _as_dict(new.get("context_injection"))
    for field in ("enabled", "mode", "max_chars", "health"):
        add("context_injection", field, old_context.get(field), new_context.get(field))

    old_memory = _as_dict(old.get("memory_summary"))
    new_memory = _as_dict(new.get("memory_summary"))
    for field in ("total", "active", "active_explicit"):
        add("memory_task_focus", f"memory.{field}", old_memory.get(field), new_memory.get(field))
    old_tasks = _as_dict(old.get("task_summary"))
    new_tasks = _as_dict(new.get("task_summary"))
    for field in ("open_total", "open_high_priority"):
        add("memory_task_focus", f"tasks.{field}", old_tasks.get(field), new_tasks.get(field))
    add_mapping("memory_task_focus", "tasks.status", old_tasks.get("status_counts"), new_tasks.get("status_counts"))
    old_focus = _as_dict(old.get("focus"))
    new_focus = _as_dict(new.get("focus"))
    for record_name in ("focused_goal", "next_task"):
        old_record = _as_dict(old_focus.get(record_name))
        new_record = _as_dict(new_focus.get(record_name))
        add("memory_task_focus", f"{record_name}.id", old_record.get("id"), new_record.get("id"))
        add("memory_task_focus", f"{record_name}.status", old_record.get("status"), new_record.get("status"))

    add(
        "registry",
        "registered_commands",
        _as_dict(old.get("registry_summary")).get("registered_commands"),
        _as_dict(new.get("registry_summary")).get("registered_commands"),
    )
    add("source_metadata", "no_mutation", old.get("no_mutation"), new.get("no_mutation"))
    add(
        "source_metadata",
        "source_note_count",
        len(old.get("source_notes") or []) if isinstance(old.get("source_notes"), list) else 0,
        len(new.get("source_notes") or []) if isinstance(new.get("source_notes"), list) else 0,
    )
    changed_sections = [
        section for section, entries in sections.items() if any(entry["changed"] for entry in entries)
    ]
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "old_snapshot": {
            "path": str(old_path),
            "filename": old_path.name,
            "generated_at": old.get("generated_at"),
            "status": old.get("status"),
        },
        "new_snapshot": {
            "path": str(new_path),
            "filename": new_path.name,
            "generated_at": new.get("generated_at"),
            "status": new.get("status"),
        },
        "diff_status": "CHANGED" if changed_fields else "NO STRUCTURAL CHANGES",
        "changed_fields": changed_fields,
        "changed_sections": changed_sections,
        "structured_diff": sections,
        "no_mutation": True,
    }


def _render_snapshot_diff_text(data: dict[str, Any]) -> str:
    old = data["old_snapshot"]
    new = data["new_snapshot"]
    lines = [
        "Proto-Mind Snapshot Diff",
        "Status: OK",
        f"Old: {old['path']}",
        f"New: {new['path']}",
        f"Period: {old.get('generated_at') or 'unknown'} -> {new.get('generated_at') or 'unknown'}",
        f"Result: {data['diff_status']}",
        f"Changed fields: {data['changed_fields']}",
    ]
    for section, title in _DIFF_SECTION_TITLES.items():
        entries = data["structured_diff"][section]
        lines.extend(["", f"{title}:"])
        lines.extend([_format_diff_entry(entry) for entry in entries] or ["- none"])
    lines.extend(
        [
            "",
            "Mutation policy:",
            "- Read-only JSON comparison; no snapshot or core store files were modified.",
        ]
    )
    return "\n".join(lines)


def _render_snapshot_diff_markdown(data: dict[str, Any]) -> str:
    old = data["old_snapshot"]
    new = data["new_snapshot"]
    lines = [
        "# Proto-Mind Snapshot Diff",
        "",
        f"Generated: {data['generated_at']}",
        f"Diff status: **{data['diff_status']}**",
        f"Changed fields: {data['changed_fields']}",
        f"Changed sections: {', '.join(data['changed_sections']) or 'none'}",
        "",
        "## Snapshots",
        "",
        f"- Old: `{old['filename']}` | generated_at={old.get('generated_at') or 'unknown'} | status={old.get('status') or 'unknown'}",
        f"- New: `{new['filename']}` | generated_at={new.get('generated_at') or 'unknown'} | status={new.get('status') or 'unknown'}",
    ]
    for section, title in _DIFF_SECTION_TITLES.items():
        entries = data["structured_diff"][section]
        lines.extend(["", f"## {title}", ""])
        lines.extend([_format_diff_entry(entry) for entry in entries] or ["- none"])
    lines.extend(
        [
            "",
            "## Mutation Policy",
            "",
            "- no_mutation: true",
            "- This export did not modify snapshots or any Proto-Mind core store.",
        ]
    )
    return "\n".join(lines)


def _format_diff_entry(entry: dict[str, Any]) -> str:
    suffix = "changed" if entry["changed"] else "same"
    return (
        f"- {entry['field']}: {_display_value(entry.get('old'))} -> "
        f"{_display_value(entry.get('new'))} ({suffix})"
    )


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _display_value(value: Any) -> str:
    if value is None:
        return "missing"
    if isinstance(value, bool):
        return str(value).lower()
    return str(value)
