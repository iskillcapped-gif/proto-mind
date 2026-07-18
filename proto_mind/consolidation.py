from __future__ import annotations

import json
import re
import shlex
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from proto_mind.experiment_journal import ExperimentJournal
from proto_mind.memory_commands import format_memory_command
from proto_mind.memory_store import MemoryStore
from proto_mind.reflection_journal import ReflectionJournal
from proto_mind.skill_library import SkillLibrary, format_skill_command
from proto_mind.task_queue import TaskQueue
from proto_mind.world_model import WorldModelLite


VALID_QUEUE_STATUSES = {"pending", "approved", "rejected", "archived", "applied"}
VALID_QUEUE_KINDS = {"memory", "skill", "world_followup", "experiment_followup", "other"}


def format_consolidation_command(command: str, *, project_root: Path) -> str | None:
    normalized = " ".join(command.strip().lower().split())
    if not normalized.startswith("/consolidation"):
        return None

    preview = ConsolidationPreview.from_project_root(project_root)
    queue = ConsolidationQueue.from_project_root(project_root)
    if normalized == "/consolidation queue-status":
        return queue.format_status()
    if normalized == "/consolidation queue-doctor":
        return queue.format_doctor()
    if normalized == "/consolidation queue-cleanup-preview":
        return queue.format_cleanup_preview()
    if normalized.startswith("/consolidation queue-list"):
        parsed_list = _parse_queue_list(command)
        if isinstance(parsed_list, str):
            return parsed_list
        return queue.format_list(include_all=parsed_list["include_all"])
    if normalized.startswith("/consolidation queue-add"):
        parsed_add = _parse_queue_add(command)
        if isinstance(parsed_add, str):
            return parsed_add
        return queue.add_item(
            parsed_add["kind"],
            parsed_add["title"],
            suggested_command=parsed_add["suggested_command"],
            rationale=parsed_add["rationale"],
        )
    if normalized.startswith("/consolidation queue-inspect"):
        item_id = command.strip()[len("/consolidation queue-inspect") :].strip()
        return queue.format_inspect(item_id)
    if normalized.startswith("/consolidation queue-apply-receipt"):
        item_id = command.strip()[len("/consolidation queue-apply-receipt") :].strip()
        return queue.format_apply_receipt(item_id)
    if normalized.startswith("/consolidation queue-apply-preview"):
        item_id = command.strip()[len("/consolidation queue-apply-preview") :].strip()
        return queue.format_apply_preview(item_id)
    if normalized.startswith("/consolidation queue-apply"):
        item_id = command.strip()[len("/consolidation queue-apply") :].strip()
        return queue.apply_item(item_id)
    if normalized.startswith("/consolidation queue-undo-preview"):
        item_id = command.strip()[len("/consolidation queue-undo-preview") :].strip()
        return queue.format_undo_preview(item_id)
    if normalized.startswith("/consolidation queue-approve"):
        item_id = command.strip()[len("/consolidation queue-approve") :].strip()
        return queue.set_status(item_id, "approved")
    if normalized.startswith("/consolidation queue-reject"):
        parsed_reject = _parse_queue_id_reason(command, "/consolidation queue-reject")
        if isinstance(parsed_reject, str):
            return parsed_reject
        return queue.reject_item(parsed_reject["id"], parsed_reject["reason"])
    if normalized.startswith("/consolidation queue-archive"):
        item_id = command.strip()[len("/consolidation queue-archive") :].strip()
        return queue.set_status(item_id, "archived")
    if normalized == "/consolidation queue-export":
        return queue.export()
    if normalized == "/consolidation status":
        return preview.format_status()
    if normalized == "/consolidation preview":
        return preview.format_preview()
    if normalized == "/consolidation export":
        return preview.export()
    if normalized == "/consolidation export-status":
        return preview.format_export_status()
    if normalized == "/consolidation doctor":
        return preview.format_doctor()
    return (
        "Usage:\n"
        "  /consolidation status\n"
        "  /consolidation preview\n"
        "  /consolidation export\n"
        "  /consolidation export-status\n"
        "  /consolidation queue-status\n"
        "  /consolidation queue-list [--all]\n"
        "  /consolidation queue-add <kind> <title> --command <suggested_command> [--rationale <text>]\n"
        "  /consolidation queue-inspect <id>\n"
        "  /consolidation queue-apply-receipt <id>\n"
        "  /consolidation queue-apply-preview <id>\n"
        "  /consolidation queue-apply <id>\n"
        "  /consolidation queue-undo-preview <id>\n"
        "  /consolidation queue-approve <id>\n"
        "  /consolidation queue-reject <id> [reason]\n"
        "  /consolidation queue-archive <id>\n"
        "  /consolidation queue-export\n"
        "  /consolidation queue-doctor\n"
        "  /consolidation queue-cleanup-preview\n"
        "  /consolidation doctor"
    )


class ConsolidationQueue:
    def __init__(self, queue_path: Path, *, project_root: Path) -> None:
        self.queue_path = queue_path
        self.project_root = project_root

    @classmethod
    def from_project_root(cls, project_root: Path) -> "ConsolidationQueue":
        return cls(project_root / "proto_mind" / "data" / "consolidation_queue.jsonl", project_root=project_root)

    @property
    def export_dir(self) -> Path:
        return self.project_root / "proto_mind" / "exports" / "consolidation_queue"

    def format_status(self) -> str:
        state = self._read_state()
        records = state["records"]
        counts = {status: sum(1 for item in records if item.get("status") == status) for status in sorted(VALID_QUEUE_STATUSES)}
        latest = _latest_queue_item(records)
        health = "ok"
        if state["error"]:
            health = "error"
        elif state["malformed_count"]:
            health = "malformed_jsonl"
        elif not self.queue_path.exists():
            health = "missing"
        lines = [
            "Consolidation Queue status:",
            f"  path: {self.queue_path}",
            f"  exists: {self.queue_path.exists()}",
            f"  total_items: {len(records)}",
            f"  pending: {counts.get('pending', 0)}",
            f"  approved: {counts.get('approved', 0)}",
            f"  applied: {counts.get('applied', 0)}",
            f"  rejected: {counts.get('rejected', 0)}",
            f"  archived: {counts.get('archived', 0)}",
            f"  malformed_entries: {state['malformed_count']}",
            f"  file_health: {health}",
            f"  latest_item: {_queue_line(latest) if latest else 'none'}",
            "  available_commands:",
            "    /consolidation queue-status",
            "    /consolidation queue-list [--all]",
            "    /consolidation queue-add <kind> <title> --command <suggested_command> [--rationale <text>]",
            "    /consolidation queue-inspect <id>",
            "    /consolidation queue-apply-receipt <id>",
            "    /consolidation queue-apply-preview <id>",
            "    /consolidation queue-apply <id>",
            "    /consolidation queue-undo-preview <id>",
            "    /consolidation queue-approve <id>",
            "    /consolidation queue-reject <id> [reason]",
            "    /consolidation queue-archive <id>",
            "    /consolidation queue-export",
            "    /consolidation queue-doctor",
            "    /consolidation queue-cleanup-preview",
        ]
        if state["error"]:
            lines.append(f"  error: {state['error']}")
        return "\n".join(lines)

    def format_doctor(self) -> str:
        report = self._doctor_report()
        lines = [
            "Consolidation Queue Doctor",
            f"Status: {report['status']}",
            f"Path: {self.queue_path}",
            "",
            "Summary:",
            f"- exists: {report['exists']}",
            f"- readable: {report['readable']}",
            f"- total records: {report['total_records']}",
            f"- malformed records: {report['malformed_count']}",
            f"- status counts: {_format_counter(report['status_counts'])}",
            f"- kind counts: {_format_counter(report['kind_counts'])}",
            "",
            "Findings:",
        ]
        if not report["findings"]:
            lines.append("- [OK] Queue is healthy.")
        else:
            for finding in report["findings"]:
                lines.append(f"- [{finding['severity']}] {finding['message']}")
        lines.append("")
        lines.append("Recommendations:")
        if report["status"] == "OK":
            lines.append("- No cleanup needed.")
        else:
            lines.append("- Run /consolidation queue-cleanup-preview for manual cleanup suggestions.")
            lines.append("- Run /consolidation queue-export before applying manual queue cleanup.")
        return "\n".join(lines)

    def format_cleanup_preview(self) -> str:
        report = self._doctor_report()
        lines = [
            "Consolidation Queue Cleanup Preview",
            "Mutation policy: read-only suggestions only; queue was not changed.",
            "",
            "Suggested commands:",
            "- /consolidation queue-export",
        ]
        commands = _queue_cleanup_commands(report)
        lines.extend(_format_bullets(commands))
        lines.append("")
        lines.append("Notes:")
        if not report["findings"]:
            lines.append("- No cleanup issues detected.")
        else:
            for finding in report["findings"]:
                lines.append(f"- [{finding['severity']}] {finding['message']}")
        return "\n".join(lines)

    def add_item(self, kind: str, title: str, *, suggested_command: str, rationale: str = "") -> str:
        kind = kind.strip()
        title = title.strip()
        suggested_command = suggested_command.strip()
        if kind not in VALID_QUEUE_KINDS:
            return f"Invalid kind: {kind}. Allowed: {', '.join(sorted(VALID_QUEUE_KINDS))}"
        if not title or not suggested_command:
            return "Usage: /consolidation queue-add <kind> <title> --command <suggested_command> [--rationale <text>]"
        state = self._read_state()
        if state["error"] or state["malformed_count"]:
            return _queue_mutation_refused(state)
        now = _utc_now()
        item = {
            "id": _new_queue_id(now),
            "created_at": now,
            "updated_at": now,
            "status": "pending",
            "kind": kind,
            "source": "operator",
            "title": title,
            "suggested_command": suggested_command,
            "rationale": rationale.strip(),
            "tags": [],
        }
        self._write_records([*state["records"], item])
        return f"Consolidation queue item added:\n  {item['id']} — {_preview(title)}"

    def format_list(self, *, include_all: bool = False) -> str:
        state = self._read_state()
        if state["error"]:
            return f"Consolidation Queue error: {state['error']}"
        records = state["records"] if include_all else [item for item in state["records"] if item.get("status") == "pending"]
        lines = ["Consolidation queue:" if not include_all else "Consolidation queue (all):"]
        if state["malformed_count"]:
            lines.append(f"  malformed_entries_skipped: {state['malformed_count']}")
        if not records:
            lines.append("  (none)")
            return "\n".join(lines)
        for item in sorted(records, key=lambda value: str(value.get("created_at", "")), reverse=True):
            lines.append(f"  - {_queue_line(item)}")
        return "\n".join(lines)

    def format_inspect(self, item_id: str) -> str:
        item_id = item_id.strip()
        if not item_id:
            return "Usage: /consolidation queue-inspect <id>"
        state = self._read_state()
        item = _find_by_id(state["records"], item_id)
        if not item:
            return f"Consolidation queue item not found: {item_id}"
        lines = [
            "Consolidation Queue Item",
            f"id: {item.get('id')}",
            f"status: {item.get('status')}",
            f"kind: {item.get('kind')}",
            f"source: {item.get('source')}",
            f"title: {item.get('title')}",
            f"created_at: {item.get('created_at')}",
            f"updated_at: {item.get('updated_at')}",
            f"suggested_command: {item.get('suggested_command')}",
            f"rationale: {item.get('rationale') or ''}",
            f"applied_at: {item.get('applied_at') or ''}",
            f"applied_command: {item.get('applied_command') or ''}",
            f"applied_kind: {item.get('applied_kind') or ''}",
            f"applied_record_id: {item.get('applied_record_id') or ''}",
            f"apply_result: {item.get('apply_result') or ''}",
            f"undo_suggestion: {item.get('undo_suggestion') or ''}",
            f"tags: {', '.join(item.get('tags') or []) if item.get('tags') else 'none'}",
        ]
        return "\n".join(lines)

    def format_apply_receipt(self, item_id: str) -> str:
        item_id = item_id.strip()
        if not item_id:
            return "Usage: /consolidation queue-apply-receipt <id>"
        state = self._read_state()
        item = _find_by_id(state["records"], item_id)
        if not item:
            return f"Consolidation queue item not found: {item_id}"
        if item.get("status") != "applied":
            return (
                "Consolidation Queue Apply Receipt unavailable:\n"
                f"  id: {item_id}\n"
                f"  status: {item.get('status')}\n"
                "  reason: item has not been applied."
            )
        return _format_apply_receipt(item)

    def format_undo_preview(self, item_id: str) -> str:
        item_id = item_id.strip()
        if not item_id:
            return "Usage: /consolidation queue-undo-preview <id>"
        state = self._read_state()
        item = _find_by_id(state["records"], item_id)
        if not item:
            return f"Consolidation queue item not found: {item_id}"
        if item.get("status") != "applied":
            return (
                "Consolidation Queue Undo Preview unavailable:\n"
                f"  id: {item_id}\n"
                f"  status: {item.get('status')}\n"
                "  reason: item has not been applied."
            )
        undo = str(item.get("undo_suggestion") or "").strip()
        lines = [
            "Consolidation Queue Undo Preview",
            f"id: {item_id}",
            f"title: {item.get('title')}",
            "Mutation policy: preview only; no undo was performed.",
            "",
            "Suggested rollback:",
        ]
        if undo.startswith("/"):
            lines.append(f"  {undo}")
        else:
            lines.append(f"  {undo or 'Manual review required; no safe rollback command is available.'}")
        return "\n".join(lines)

    def format_apply_preview(self, item_id: str) -> str:
        item_id = item_id.strip()
        if not item_id:
            return "Usage: /consolidation queue-apply-preview <id>"
        state = self._read_state()
        item = _find_by_id(state["records"], item_id)
        if not item:
            return f"Consolidation queue item not found: {item_id}"
        allowed = _classify_apply_command(str(item.get("suggested_command") or ""))
        lines = [
            "Consolidation Queue Apply Preview",
            f"id: {item_id}",
            f"status: {item.get('status')}",
            f"applyable: {item.get('status') == 'approved' and allowed['allowed']}",
            f"command_type: {allowed['kind'] or 'none'}",
            f"reason: {allowed['reason']}",
            "command:",
            f"  {item.get('suggested_command')}",
            "Mutation policy: preview only; no stores were changed.",
        ]
        return "\n".join(lines)

    def apply_item(self, item_id: str) -> str:
        item_id = item_id.strip()
        if not item_id:
            return "Usage: /consolidation queue-apply <id>"
        state = self._read_state()
        if state["error"] or state["malformed_count"]:
            return _queue_mutation_refused(state)
        records = state["records"]
        item = _find_by_id(records, item_id)
        if not item:
            return f"Consolidation queue item not found: {item_id}"
        if item.get("status") != "approved":
            return (
                "Consolidation queue apply refused:\n"
                f"  id: {item_id}\n"
                f"  status: {item.get('status')}\n"
                "  reason: only approved items can be applied."
            )
        command = str(item.get("suggested_command") or "").strip()
        allowed = _classify_apply_command(command)
        if not allowed["allowed"]:
            return (
                "Consolidation queue apply refused:\n"
                f"  id: {item_id}\n"
                f"  reason: {allowed['reason']}\n"
                "Manual command for operator review:\n"
                f"  {command}"
            )
        result = _execute_allowlisted_apply_command(command, project_root=self.project_root)
        receipt = _build_apply_receipt(command, allowed["kind"], result)
        now = _utc_now()
        item["status"] = "applied"
        item["updated_at"] = now
        item["applied_at"] = now
        item["apply_result"] = _preview(result, 220)
        item["applied_command"] = command
        item["applied_kind"] = receipt["applied_kind"]
        item["applied_record_id"] = receipt["applied_record_id"]
        item["undo_suggestion"] = receipt["undo_suggestion"]
        self._write_records(records)
        return "\n".join(
            [
                "Consolidation queue item applied:",
                f"  id: {item_id}",
                f"  command_type: {allowed['kind']}",
                f"  applied_kind: {item['applied_kind']}",
                f"  applied_record_id: {item['applied_record_id'] or 'unknown'}",
                f"  undo_suggestion: {item['undo_suggestion']}",
                "Result preview:",
                f"  {item['apply_result']}",
                "Mutation policy: only allowlisted target store and queue apply metadata were changed.",
            ]
        )

    def set_status(self, item_id: str, status: str) -> str:
        item_id = item_id.strip()
        if not item_id:
            return f"Usage: /consolidation queue-{status} <id>"
        state = self._read_state()
        if state["error"] or state["malformed_count"]:
            return _queue_mutation_refused(state)
        records = state["records"]
        item = _find_by_id(records, item_id)
        if not item:
            return f"Consolidation queue item not found: {item_id}"
        item["status"] = status
        item["updated_at"] = _utc_now()
        self._write_records(records)
        lines = [f"Consolidation queue item {status}: {item_id}"]
        if status == "approved":
            lines.extend(["Suggested command for manual run:", f"  {item.get('suggested_command')}"])
            lines.append("Note: command was not executed.")
        return "\n".join(lines)

    def reject_item(self, item_id: str, reason: str = "") -> str:
        item_id = item_id.strip()
        if not item_id:
            return "Usage: /consolidation queue-reject <id> [reason]"
        state = self._read_state()
        if state["error"] or state["malformed_count"]:
            return _queue_mutation_refused(state)
        records = state["records"]
        item = _find_by_id(records, item_id)
        if not item:
            return f"Consolidation queue item not found: {item_id}"
        item["status"] = "rejected"
        if reason.strip():
            existing = str(item.get("rationale") or "").strip()
            rejection_note = f"Rejected: {reason.strip()}"
            item["rationale"] = f"{existing}\n{rejection_note}".strip() if existing else rejection_note
        item["updated_at"] = _utc_now()
        self._write_records(records)
        return f"Consolidation queue item rejected: {item_id}"

    def export(self) -> str:
        state = self._read_state()
        now = _utc_now()
        export_id = _new_export_id(now)
        md_path = self.export_dir / f"consolidation_queue_{export_id}.md"
        json_path = self.export_dir / f"consolidation_queue_{export_id}.json"
        payload = {
            "created_at": now,
            "path": str(self.queue_path),
            "records": state["records"],
            "malformed_count": state["malformed_count"],
            "error": state["error"],
        }
        self.export_dir.mkdir(parents=True, exist_ok=True)
        _atomic_write(md_path, _render_queue_markdown(payload))
        _atomic_write(json_path, json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
        return "\n".join(
            [
                "Consolidation queue export created:",
                f"  markdown: {md_path}",
                f"  json: {json_path}",
                f"  items: {len(state['records'])}",
                "Mutation policy: only queue export files were created.",
            ]
        )

    def _doctor_report(self) -> dict[str, Any]:
        raw = self._read_raw_records()
        records = raw["records"]
        findings: list[dict[str, str]] = []
        if raw["error"]:
            findings.append({"severity": "ERROR", "message": f"Queue file unreadable: {raw['error']}"})
        if raw["malformed_count"]:
            findings.append({"severity": "ERROR", "message": f"Malformed JSONL records: {raw['malformed_count']}"})
        required = {
            "id",
            "created_at",
            "updated_at",
            "status",
            "kind",
            "source",
            "title",
            "suggested_command",
            "rationale",
            "tags",
        }
        for index, record in enumerate(records, start=1):
            record_id = str(record.get("id") or f"record#{index}")
            missing = sorted(field for field in required if field not in record)
            if missing:
                findings.append({"severity": "WARN", "message": f"{record_id} missing required fields: {', '.join(missing)}"})
            status = str(record.get("status") or "")
            kind = str(record.get("kind") or "")
            if status and status not in VALID_QUEUE_STATUSES:
                findings.append({"severity": "WARN", "message": f"{record_id} has invalid status: {status}"})
            if kind and kind not in VALID_QUEUE_KINDS:
                findings.append({"severity": "WARN", "message": f"{record_id} has invalid kind: {kind}"})
            if status == "pending" and not str(record.get("suggested_command") or "").strip():
                findings.append({"severity": "WARN", "message": f"{record_id} is pending with empty suggested_command"})
            if status == "pending" and _is_old_pending(record):
                findings.append({"severity": "WARN", "message": f"{record_id} has been pending for a long time"})
        for duplicate in _duplicate_pending(records, field="title"):
            findings.append({"severity": "WARN", "message": f"Duplicate pending title: {_preview(duplicate)}"})
        for duplicate in _duplicate_pending(records, field="suggested_command"):
            findings.append({"severity": "WARN", "message": f"Duplicate pending suggested_command: {_preview(duplicate)}"})
        for record in records:
            if record.get("status") == "approved" and _approved_reflected(record, self.project_root):
                findings.append({"severity": "WARN", "message": f"Approved item may already be reflected in memory/skills: {record.get('id')}"})
        if len(records) > 100:
            findings.append({"severity": "WARN", "message": f"Queue has more than 100 records: {len(records)}"})
        status = "OK"
        if any(finding["severity"] == "ERROR" for finding in findings):
            status = "ERROR"
        elif any(finding["severity"] == "WARN" for finding in findings):
            status = "WARN"
        return {
            "status": status,
            "exists": self.queue_path.exists(),
            "readable": not raw["error"],
            "total_records": len(records),
            "malformed_count": raw["malformed_count"],
            "status_counts": Counter(str(record.get("status") or "missing") for record in records),
            "kind_counts": Counter(str(record.get("kind") or "missing") for record in records),
            "findings": findings,
            "records": records,
        }

    def _read_state(self) -> dict[str, Any]:
        if not self.queue_path.exists():
            return {"records": [], "malformed_count": 0, "error": ""}
        records: list[dict[str, Any]] = []
        malformed = 0
        try:
            lines = self.queue_path.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            return {"records": [], "malformed_count": 0, "error": str(exc)}
        for line in lines:
            if not line.strip():
                continue
            try:
                parsed = json.loads(line)
            except json.JSONDecodeError:
                malformed += 1
                continue
            if isinstance(parsed, dict):
                records.append(_normalize_queue_record(parsed))
            else:
                malformed += 1
        return {"records": records, "malformed_count": malformed, "error": ""}

    def _read_raw_records(self) -> dict[str, Any]:
        if not self.queue_path.exists():
            return {"records": [], "malformed_count": 0, "error": ""}
        records: list[dict[str, Any]] = []
        malformed = 0
        try:
            lines = self.queue_path.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            return {"records": [], "malformed_count": 0, "error": str(exc)}
        for line in lines:
            if not line.strip():
                continue
            try:
                parsed = json.loads(line)
            except json.JSONDecodeError:
                malformed += 1
                continue
            if isinstance(parsed, dict):
                records.append(parsed)
            else:
                malformed += 1
        return {"records": records, "malformed_count": malformed, "error": ""}

    def _write_records(self, records: list[dict[str, Any]]) -> None:
        self.queue_path.parent.mkdir(parents=True, exist_ok=True)
        payload = "".join(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n" for record in records)
        _atomic_write(self.queue_path, payload)


class ConsolidationPreview:
    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root

    @classmethod
    def from_project_root(cls, project_root: Path) -> "ConsolidationPreview":
        return cls(project_root)

    def snapshot(self) -> dict[str, Any]:
        tasks_state = TaskQueue.from_project_root(self.project_root)._read_state()
        experiments_state = ExperimentJournal.from_project_root(self.project_root)._read_state()
        world_state = WorldModelLite.from_project_root(self.project_root)._read_state()
        skills_state = SkillLibrary.from_project_root(self.project_root)._read_state()
        reflections, reflection_malformed = ReflectionJournal.from_project_root(self.project_root).read_records()
        memories = _read_explicit_memories(self.project_root)
        return {
            "tasks_state": tasks_state,
            "experiments_state": experiments_state,
            "world_state": world_state,
            "skills_state": skills_state,
            "reflections": reflections,
            "reflection_malformed": reflection_malformed,
            "active_memories": memories["active"],
            "forgotten_memories": memories["forgotten"],
            "memory_error": memories["error"],
        }

    @property
    def export_dir(self) -> Path:
        return self.project_root / "proto_mind" / "exports" / "consolidation"

    def format_status(self) -> str:
        snap = self.snapshot()
        completed_tasks = [task for task in snap["tasks_state"].records if task.get("status") == "done"]
        world_lessons = [record for record in snap["world_state"].records if record.get("status") == "scored" and str(record.get("lesson") or "").strip()]
        lines = [
            "Consolidation Preview status:",
            "  module: OK",
            "  source_stores_checked:",
            "    - reflection_journal",
            "    - tasks",
            "    - experiments",
            "    - world_model",
            "    - skills",
            "    - active_explicit_memories",
            f"  reflections: {len(snap['reflections'])}",
            f"  done_tasks: {len(completed_tasks)}",
            f"  world_lessons: {len(world_lessons)}",
            f"  skills: {len(snap['skills_state'].records)}",
            f"  active_memories: {len(snap['active_memories'])}",
            "  available_commands:",
            "    /consolidation status",
            "    /consolidation preview",
            "    /consolidation export",
            "    /consolidation export-status",
            "    /consolidation doctor",
        ]
        if snap["memory_error"]:
            lines.append(f"  memory_error: {snap['memory_error']}")
        return "\n".join(lines)

    def format_preview(self) -> str:
        data = self.build_preview_data()
        memory_candidates = data["memory_candidates"]
        skill_candidates = data["skill_candidates"]
        followups = data["followup_candidates"]
        skip_notes = data["skip_notes"]
        lines = [
            "Consolidation Preview",
            "Mutation policy: read-only suggestions only; no stores were changed.",
            "",
            "Memory candidates:",
        ]
        lines.extend(_format_bullets([candidate["command"] for candidate in memory_candidates]))
        lines.append("Skill candidates:")
        skill_lines: list[str] = []
        for candidate in skill_candidates:
            skill_lines.append(candidate["command"])
            if candidate.get("body_command"):
                skill_lines.append(candidate["body_command"])
        lines.extend(_format_bullets(skill_lines))
        lines.append("World/experiment follow-up candidates:")
        lines.extend(_format_bullets([candidate["command"] for candidate in followups]))
        lines.append("Duplicates/skip notes:")
        lines.extend(_format_bullets(skip_notes))
        return "\n".join(lines)

    def build_preview_data(self) -> dict[str, Any]:
        snap = self.snapshot()
        candidates = _build_candidates(snap)
        memory_candidates, skill_candidates, followups, skip_notes = _dedupe_candidates(candidates, snap)
        completed_tasks = [task for task in snap["tasks_state"].records if task.get("status") == "done"]
        world_lessons = [record for record in snap["world_state"].records if record.get("status") == "scored" and str(record.get("lesson") or "").strip()]
        return {
            "created_at": _utc_now(),
            "summary": {
                "reflections": len(snap["reflections"]),
                "done_tasks": len(completed_tasks),
                "world_lessons": len(world_lessons),
                "skills": len(snap["skills_state"].records),
                "active_memories": len(snap["active_memories"]),
            },
            "memory_candidates": memory_candidates,
            "skill_candidates": skill_candidates,
            "followup_candidates": followups,
            "skip_notes": skip_notes,
            "suggested_commands": _suggested_commands(memory_candidates, skill_candidates, followups),
            "mutation_policy": "Only export files may be created; core stores are read-only.",
        }

    def export(self) -> str:
        data = self.build_preview_data()
        export_id = _new_export_id(data["created_at"])
        md_path = self.export_dir / f"consolidation_{export_id}.md"
        json_path = self.export_dir / f"consolidation_{export_id}.json"
        self.export_dir.mkdir(parents=True, exist_ok=True)
        _atomic_write(md_path, _render_markdown(data))
        _atomic_write(json_path, json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
        lines = [
            "Consolidation export created:",
            f"  markdown: {md_path}",
            f"  json: {json_path}",
            f"  memory_candidates: {len(data['memory_candidates'])}",
            f"  skill_candidates: {len(data['skill_candidates'])}",
            f"  followup_candidates: {len(data['followup_candidates'])}",
            f"  skip_notes: {len(data['skip_notes'])}",
            "Mutation policy: only export files were created.",
        ]
        return "\n".join(lines)

    def format_export_status(self) -> str:
        files = sorted([item for item in self.export_dir.glob("consolidation_*") if item.is_file()], key=lambda item: item.stat().st_mtime, reverse=True) if self.export_dir.exists() else []
        latest = files[0] if files else None
        latest_time = datetime.fromtimestamp(latest.stat().st_mtime, UTC).isoformat() if latest else "none"
        lines = [
            "Consolidation Export Status",
            f"  export_dir: {self.export_dir}",
            f"  exists: {self.export_dir.exists()}",
            f"  export_files: {len(files)}",
            f"  latest_export: {latest if latest else 'none'}",
            f"  latest_export_time: {latest_time}",
            "  available_commands:",
            "    /consolidation export",
            "    /consolidation export-status",
            "    /consolidation preview",
            "    /consolidation doctor",
        ]
        return "\n".join(lines)

    def format_doctor(self) -> str:
        snap = self.snapshot()
        findings = _doctor_findings(snap)
        status = "OK"
        if any(finding["severity"] == "ERROR" for finding in findings):
            status = "ERROR"
        elif any(finding["severity"] == "WARN" for finding in findings):
            status = "WARN"
        lines = [
            "Consolidation Doctor",
            f"Status: {status}",
            "",
            "Findings:",
        ]
        if not findings:
            lines.append("- [OK] No consolidation issues detected.")
        else:
            for finding in findings:
                lines.append(f"- [{finding['severity']}] {finding['message']}")
        lines.append("")
        lines.append("Recommendations:")
        if status == "OK":
            lines.append("- Review /consolidation preview when you want manual memory or skill promotion suggestions.")
        else:
            lines.append("- Use source module commands to fill missing results or lessons before manual consolidation.")
            lines.append("- Use /memory doctor and /skills list --all for duplicate review.")
        return "\n".join(lines)


def _build_candidates(snap: dict[str, Any]) -> dict[str, list[dict[str, str]]]:
    memory: list[dict[str, str]] = []
    skills: list[dict[str, str]] = []
    followups: list[dict[str, str]] = []

    for task in snap["tasks_state"].records:
        task_id = str(task.get("id") or "unknown")
        result = str(task.get("result") or "").strip()
        if task.get("status") == "done" and result:
            text = f"Task {task.get('title')}: {result}"
            memory.append(_candidate("task_result", task_id, text, f"/memory remember {text}"))
        elif task.get("status") == "done" and not result:
            followups.append(_candidate("task_missing_result", task_id, "", f"/tasks done {task_id} <result>"))

    for exp in snap["experiments_state"].records:
        exp_id = str(exp.get("id") or "unknown")
        lesson = str(exp.get("lesson") or "").strip()
        if exp.get("status") in {"completed", "inconclusive"} and lesson:
            text = f"Experiment {exp.get('title')} lesson: {lesson}"
            memory.append(_candidate("experiment_lesson", exp_id, text, f"/memory remember {text}"))
            skills.append(_skill_candidate("experiment_lesson", exp_id, f"Apply experiment lesson: {_preview(str(exp.get('title') or exp_id), 60)}", lesson))
        elif exp.get("status") in {"completed", "inconclusive"} and not lesson:
            followups.append(_candidate("experiment_missing_lesson", exp_id, "", f"/experiments lesson {exp_id} <lesson>"))

    for record in snap["world_state"].records:
        world_id = str(record.get("id") or "unknown")
        lesson = str(record.get("lesson") or "").strip()
        if record.get("status") == "scored" and lesson:
            text = f"World prediction lesson: {lesson}"
            memory.append(_candidate("world_lesson", world_id, text, f"/memory remember {text}"))
            skills.append(_skill_candidate("world_lesson", world_id, f"Apply world-model lesson: {_preview(lesson, 60)}", lesson))
        elif record.get("status") == "scored" and not lesson:
            followups.append(_candidate("world_missing_lesson", world_id, "", f"/world lesson {world_id} <lesson>"))
        elif record.get("status") == "observed" and record.get("score") is None:
            followups.append(_candidate("world_missing_score", world_id, "", f"/world score {world_id} <0-5>"))

    for reflection in sorted(snap["reflections"], key=lambda item: str(item.get("created_at", "")), reverse=True)[:5]:
        summary = str(reflection.get("summary") or "").strip()
        if summary:
            text = f"Reflection {reflection.get('id')}: {summary}"
            memory.append(_candidate("reflection_summary", str(reflection.get("id") or "unknown"), text, f"/memory remember {text}"))

    return {"memory": memory, "skills": skills, "followups": followups}


def _candidate(source: str, record_id: str, text: str, command: str) -> dict[str, str]:
    return {"source": source, "id": record_id, "text": text, "command": command}


def _skill_candidate(source: str, record_id: str, name: str, body: str) -> dict[str, str]:
    return {
        "source": source,
        "id": record_id,
        "text": f"{name} {body}",
        "command": f"/skills add {name} --category workflow --summary {_preview(body, 100)}",
        "body_command": f"/skills body <skill_id> {body}",
    }


def _dedupe_candidates(
    candidates: dict[str, list[dict[str, str]]],
    snap: dict[str, Any],
) -> tuple[list[dict[str, str]], list[dict[str, str]], list[dict[str, str]], list[str]]:
    active_memory_norms = {_normalize(str(item.get("content") or item.get("text") or "")) for item in snap["active_memories"]}
    skill_norms = set()
    for skill in snap["skills_state"].records:
        if skill.get("status") == "active":
            skill_norms.add(_normalize(str(skill.get("name") or "")))
            skill_norms.add(_normalize(str(skill.get("summary") or "")))
            skill_norms.add(_normalize(str(skill.get("body") or "")))

    memory_out: list[dict[str, str]] = []
    skill_out: list[dict[str, str]] = []
    notes: list[str] = []
    seen_candidates: set[str] = set()

    for candidate in candidates["memory"]:
        norm = _normalize(candidate["text"])
        if not norm:
            continue
        if norm in seen_candidates:
            notes.append(f"Repeated candidate skipped: {_preview(candidate['text'])}")
            continue
        seen_candidates.add(norm)
        if norm in active_memory_norms:
            notes.append(f"Memory candidate already present in active explicit memory: {_preview(candidate['text'])}")
            continue
        memory_out.append(candidate)

    for candidate in candidates["skills"]:
        norm = _normalize(candidate["text"])
        name_norm = _normalize(candidate["command"])
        if norm in skill_norms or name_norm in skill_norms:
            notes.append(f"Skill candidate resembles existing active skill: {_preview(candidate['text'])}")
            continue
        skill_out.append(candidate)

    return memory_out, skill_out, candidates["followups"], notes


def _doctor_findings(snap: dict[str, Any]) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    states = {
        "tasks": snap["tasks_state"],
        "experiments": snap["experiments_state"],
        "world": snap["world_state"],
        "skills": snap["skills_state"],
    }
    for name, state in states.items():
        if state.error:
            findings.append({"severity": "ERROR", "message": f"{name} storage read error: {state.error}"})
        if state.malformed_count:
            findings.append({"severity": "ERROR", "message": f"{name} storage has malformed JSONL entries: {state.malformed_count}"})
    if snap["memory_error"]:
        findings.append({"severity": "ERROR", "message": f"persistent memory read error: {snap['memory_error']}"})
    if snap["reflection_malformed"]:
        findings.append({"severity": "ERROR", "message": f"reflection journal malformed entries: {snap['reflection_malformed']}"})

    if not snap["active_memories"]:
        findings.append({"severity": "WARN", "message": "No active explicit memories found."})

    candidates = _build_candidates(snap)
    memory_candidates, _, _, _ = _dedupe_candidates(candidates, snap)
    if snap["reflections"] and not memory_candidates:
        findings.append({"severity": "WARN", "message": "Reflections exist but no new memory candidates were found."})

    for task in snap["tasks_state"].records:
        if task.get("status") == "done" and not str(task.get("result") or "").strip():
            findings.append({"severity": "WARN", "message": f"Completed task without result: {task.get('id')}"})
    for exp in snap["experiments_state"].records:
        if exp.get("status") in {"completed", "inconclusive"} and not str(exp.get("lesson") or "").strip():
            findings.append({"severity": "WARN", "message": f"Completed/inconclusive experiment without lesson: {exp.get('id')}"})
    for record in snap["world_state"].records:
        if record.get("status") == "scored" and not str(record.get("lesson") or "").strip():
            findings.append({"severity": "WARN", "message": f"Scored world prediction without lesson: {record.get('id')}"})

    repeated_candidates = _duplicates([candidate["text"] for group in candidates.values() for candidate in group if candidate.get("text")])
    for text in repeated_candidates:
        findings.append({"severity": "WARN", "message": f"Repeated candidate text: {_preview(text)}"})
    duplicate_memories = _duplicates([str(item.get("content") or item.get("text") or "") for item in snap["active_memories"]])
    for text in duplicate_memories:
        findings.append({"severity": "WARN", "message": f"Possible duplicate active memory: {_preview(text)}"})
    duplicate_skills = _duplicates([str(skill.get("summary") or skill.get("name") or "") for skill in snap["skills_state"].records if skill.get("status") == "active"])
    for text in duplicate_skills:
        findings.append({"severity": "WARN", "message": f"Possible duplicate active skill summary: {_preview(text)}"})
    return findings


def _read_explicit_memories(project_root: Path) -> dict[str, Any]:
    path = project_root / "proto_mind" / "data" / "persistent_memory.json"
    if not path.exists():
        return {"active": [], "forgotten": [], "error": ""}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"active": [], "forgotten": [], "error": str(exc)}
    if not isinstance(payload, list):
        return {"active": [], "forgotten": [], "error": "persistent memory root is not a list"}
    explicit = [item for item in payload if isinstance(item, dict) and item.get("type") == "explicit"]
    active = [item for item in explicit if item.get("active", True)]
    forgotten = [item for item in explicit if not item.get("active", True)]
    return {"active": active, "forgotten": forgotten, "error": ""}


def _suggested_commands(
    memory_candidates: list[dict[str, str]],
    skill_candidates: list[dict[str, str]],
    followups: list[dict[str, str]],
) -> list[str]:
    commands = [candidate["command"] for candidate in memory_candidates]
    for candidate in skill_candidates:
        commands.append(candidate["command"])
        if candidate.get("body_command"):
            commands.append(candidate["body_command"])
    commands.extend(candidate["command"] for candidate in followups)
    return commands


def _render_markdown(data: dict[str, Any]) -> str:
    summary = data["summary"]
    lines = [
        "# Consolidation Preview Export",
        "",
        f"Created: {data['created_at']}",
        "",
        "## Summary",
        "",
        f"- reflections: {summary['reflections']}",
        f"- done_tasks: {summary['done_tasks']}",
        f"- world_lessons: {summary['world_lessons']}",
        f"- skills: {summary['skills']}",
        f"- active_memories: {summary['active_memories']}",
        "",
        "## Memory Candidates",
        "",
    ]
    lines.extend(_markdown_candidate_lines(data["memory_candidates"], include_body=False))
    lines.extend(["", "## Skill Candidates", ""])
    lines.extend(_markdown_candidate_lines(data["skill_candidates"], include_body=True))
    lines.extend(["", "## Follow-Up Candidates", ""])
    lines.extend(_markdown_candidate_lines(data["followup_candidates"], include_body=False))
    lines.extend(["", "## Duplicate / Skip Notes", ""])
    lines.extend(_markdown_text_lines(data["skip_notes"]))
    lines.extend(["", "## Suggested Commands", ""])
    lines.extend(_markdown_text_lines(data["suggested_commands"]))
    lines.extend(["", "## Mutation Policy", "", f"- {data['mutation_policy']}", ""])
    return "\n".join(lines)


def _markdown_candidate_lines(candidates: list[dict[str, str]], *, include_body: bool) -> list[str]:
    if not candidates:
        return ["- none"]
    lines: list[str] = []
    for candidate in candidates:
        lines.append(f"- source: `{candidate.get('source', 'unknown')}` id: `{candidate.get('id', 'unknown')}`")
        if candidate.get("text"):
            lines.append(f"  - text: {candidate['text']}")
        lines.append(f"  - command: `{candidate['command']}`")
        if include_body and candidate.get("body_command"):
            lines.append(f"  - body command: `{candidate['body_command']}`")
    return lines


def _markdown_text_lines(values: list[str]) -> list[str]:
    if not values:
        return ["- none"]
    return [f"- `{value}`" if value.startswith("/") else f"- {value}" for value in values]


def _parse_queue_list(command: str) -> dict[str, bool] | str:
    normalized = command.strip().replace("–", "--")
    remainder = normalized[len("/consolidation queue-list") :].strip()
    if not remainder:
        return {"include_all": False}
    if remainder == "--all":
        return {"include_all": True}
    return "Usage: /consolidation queue-list [--all]"


def _parse_queue_add(command: str) -> dict[str, str] | str:
    normalized = _normalize_cli_quotes(command.strip().replace("–", "--"))
    remainder = normalized[len("/consolidation queue-add") :].strip()
    if not remainder:
        return "Usage: /consolidation queue-add <kind> <title> --command <suggested_command> [--rationale <text>]"
    try:
        parts = shlex.split(remainder)
    except ValueError as exc:
        return f"Invalid queue-add syntax: {exc}"
    if len(parts) < 4:
        return "Usage: /consolidation queue-add <kind> <title> --command <suggested_command> [--rationale <text>]"
    kind = parts[0]
    if kind not in VALID_QUEUE_KINDS:
        return f"Invalid kind: {kind}. Allowed: {', '.join(sorted(VALID_QUEUE_KINDS))}"
    title_parts: list[str] = []
    index = 1
    while index < len(parts) and parts[index] not in {"--command", "--rationale"}:
        title_parts.append(parts[index])
        index += 1
    suggested_command = ""
    rationale = ""
    while index < len(parts):
        flag = parts[index]
        if index + 1 >= len(parts):
            return "Usage: /consolidation queue-add <kind> <title> --command <suggested_command> [--rationale <text>]"
        value = parts[index + 1]
        if flag == "--command":
            suggested_command = value
        elif flag == "--rationale":
            rationale = value
        else:
            return "Usage: /consolidation queue-add <kind> <title> --command <suggested_command> [--rationale <text>]"
        index += 2
    title = " ".join(title_parts).strip()
    if not title or not suggested_command:
        return "Usage: /consolidation queue-add <kind> <title> --command <suggested_command> [--rationale <text>]"
    return {"kind": kind, "title": title, "suggested_command": suggested_command, "rationale": rationale}


def _parse_queue_id_reason(command: str, prefix: str) -> dict[str, str] | str:
    normalized = _normalize_cli_quotes(command.strip().replace("–", "--"))
    remainder = normalized[len(prefix) :].strip()
    if not remainder:
        return f"Usage: {prefix} <id> [reason]"
    try:
        parts = shlex.split(remainder)
    except ValueError as exc:
        return f"Invalid syntax: {exc}"
    if not parts:
        return f"Usage: {prefix} <id> [reason]"
    return {"id": parts[0], "reason": " ".join(parts[1:])}


def _normalize_cli_quotes(text: str) -> str:
    return (
        text.replace("“", '"')
        .replace("”", '"')
        .replace("‘", "'")
        .replace("’", "'")
    )


def _normalize_queue_record(record: dict[str, Any]) -> dict[str, Any]:
    normalized = {
        "id": str(record.get("id") or ""),
        "created_at": str(record.get("created_at") or ""),
        "updated_at": str(record.get("updated_at") or record.get("created_at") or ""),
        "status": str(record.get("status") or "pending"),
        "kind": str(record.get("kind") or "other"),
        "source": str(record.get("source") or "operator"),
        "title": str(record.get("title") or ""),
        "suggested_command": str(record.get("suggested_command") or ""),
        "rationale": str(record.get("rationale") or ""),
        "tags": record.get("tags") if isinstance(record.get("tags"), list) else [],
    }
    if record.get("applied_at"):
        normalized["applied_at"] = str(record.get("applied_at") or "")
    if record.get("apply_result"):
        normalized["apply_result"] = str(record.get("apply_result") or "")
    if record.get("applied_command"):
        normalized["applied_command"] = str(record.get("applied_command") or "")
    if record.get("applied_kind"):
        normalized["applied_kind"] = str(record.get("applied_kind") or "unknown")
    if record.get("applied_record_id"):
        normalized["applied_record_id"] = str(record.get("applied_record_id") or "")
    if record.get("undo_suggestion"):
        normalized["undo_suggestion"] = str(record.get("undo_suggestion") or "")
    if normalized["status"] not in VALID_QUEUE_STATUSES:
        normalized["status"] = "pending"
    if normalized["kind"] not in VALID_QUEUE_KINDS:
        normalized["kind"] = "other"
    return normalized


def _queue_line(item: dict[str, Any] | None) -> str:
    if not item:
        return "none"
    return (
        f"{item.get('id', 'unknown')} "
        f"[{item.get('status', 'unknown')}] "
        f"kind={item.get('kind', 'other')} "
        f"{_preview(str(item.get('title') or ''))}"
    )


def _latest_queue_item(records: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not records:
        return None
    return sorted(records, key=lambda item: str(item.get("updated_at") or item.get("created_at") or ""), reverse=True)[0]


def _find_by_id(records: list[dict[str, Any]], item_id: str) -> dict[str, Any] | None:
    for record in records:
        if record.get("id") == item_id:
            return record
    return None


def _queue_mutation_refused(state: dict[str, Any]) -> str:
    if state["error"]:
        return f"Consolidation Queue mutation refused: storage error: {state['error']}"
    return f"Consolidation Queue mutation refused: malformed entries present: {state['malformed_count']}"


def _render_queue_markdown(payload: dict[str, Any]) -> str:
    records = payload["records"]
    lines = [
        "# Consolidation Queue Export",
        "",
        f"Created: {payload['created_at']}",
        f"Queue path: `{payload['path']}`",
        f"Items: {len(records)}",
        f"Malformed entries: {payload['malformed_count']}",
        "",
        "## Items",
        "",
    ]
    if not records:
        lines.append("- none")
    for item in records:
        lines.extend(
            [
                f"- `{item.get('id')}` [{item.get('status')}] kind={item.get('kind')}",
                f"  - title: {item.get('title')}",
                f"  - suggested_command: `{item.get('suggested_command')}`",
                f"  - rationale: {item.get('rationale') or ''}",
                f"  - applied_at: {item.get('applied_at') or ''}",
                f"  - applied_command: `{item.get('applied_command') or ''}`",
                f"  - applied_kind: {item.get('applied_kind') or ''}",
                f"  - applied_record_id: {item.get('applied_record_id') or ''}",
                f"  - apply_result: {item.get('apply_result') or ''}",
                f"  - undo_suggestion: `{item.get('undo_suggestion') or ''}`",
            ]
        )
    lines.extend(["", "## Mutation Policy", "", "- Queue export creates files only and does not execute suggested commands.", ""])
    return "\n".join(lines)


def _queue_cleanup_commands(report: dict[str, Any]) -> list[str]:
    commands: list[str] = []
    records = report["records"]
    seen_pending_title: set[str] = set()
    seen_pending_command: set[str] = set()
    for record in records:
        item_id = str(record.get("id") or "")
        if not item_id:
            continue
        status = str(record.get("status") or "")
        title_norm = _normalize(str(record.get("title") or ""))
        command_norm = _normalize(str(record.get("suggested_command") or ""))
        if status == "approved":
            commands.append(f"/consolidation queue-archive {item_id}")
        if status == "pending" and (not str(record.get("suggested_command") or "").strip()):
            commands.append(f"/consolidation queue-inspect {item_id}")
        if status == "pending" and title_norm:
            if title_norm in seen_pending_title:
                commands.append(f"/consolidation queue-reject {item_id} duplicate pending title")
            seen_pending_title.add(title_norm)
        if status == "pending" and command_norm:
            if command_norm in seen_pending_command:
                commands.append(f"/consolidation queue-reject {item_id} duplicate pending command")
            seen_pending_command.add(command_norm)
        if status == "pending" and _is_old_pending(record):
            commands.append(f"/consolidation queue-inspect {item_id}")
    return _unique_preserve_order(commands)


def _duplicate_pending(records: list[dict[str, Any]], *, field: str) -> list[str]:
    values: list[str] = []
    for record in records:
        if record.get("status") == "pending":
            values.append(str(record.get(field) or ""))
    return _duplicates(values)


def _is_old_pending(record: dict[str, Any]) -> bool:
    if record.get("status") != "pending":
        return False
    created_at = str(record.get("created_at") or "")
    try:
        created = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    except ValueError:
        return False
    if created.tzinfo is None:
        created = created.replace(tzinfo=UTC)
    return (datetime.now(UTC) - created).days >= 14


def _approved_reflected(record: dict[str, Any], project_root: Path) -> bool:
    command = str(record.get("suggested_command") or "")
    if command.startswith("/memory remember "):
        text = command[len("/memory remember ") :].strip()
        memories = _read_explicit_memories(project_root)
        target = _normalize(text)
        return any(_normalize(str(item.get("content") or item.get("text") or "")) == target for item in memories["active"])
    if command.startswith("/skills add "):
        text = command[len("/skills add ") :].strip()
        target = _normalize(text.split("--", 1)[0].strip())
        state = SkillLibrary.from_project_root(project_root)._read_state()
        return any(
            _normalize(str(skill.get("name") or "")) == target or _normalize(str(skill.get("summary") or "")) == target
            for skill in state.records
            if skill.get("status") == "active"
        )
    return False


def _classify_apply_command(command: str) -> dict[str, Any]:
    command = command.strip()
    if not command:
        return {"allowed": False, "kind": "", "reason": "empty suggested_command"}
    if _looks_like_command_chain(command):
        return {"allowed": False, "kind": "", "reason": "multi-command chains are not supported in v1.3"}
    if command.startswith("/memory remember "):
        text = command[len("/memory remember ") :].strip()
        if not text:
            return {"allowed": False, "kind": "memory", "reason": "empty memory text"}
        return {"allowed": True, "kind": "memory_remember", "reason": "allowlisted /memory remember"}
    if command.startswith("/skills add "):
        parsed = _parse_allowlisted_skills_add(command)
        if isinstance(parsed, str):
            return {"allowed": False, "kind": "skill", "reason": parsed}
        return {"allowed": True, "kind": "skills_add", "reason": "allowlisted /skills add"}
    if command.startswith("/skills body "):
        parsed_body = _parse_allowlisted_skills_body(command)
        if isinstance(parsed_body, str):
            return {"allowed": False, "kind": "skill", "reason": parsed_body}
        return {"allowed": True, "kind": "skills_body", "reason": "allowlisted /skills body"}
    return {"allowed": False, "kind": "", "reason": "command is not in the consolidation apply allowlist"}


def _looks_like_command_chain(command: str) -> bool:
    return "\n" in command or "\r" in command or "&&" in command or "||" in command or ";" in command


def _parse_allowlisted_skills_add(command: str) -> dict[str, str] | str:
    try:
        parts = shlex.split(_normalize_cli_quotes(command))
    except ValueError as exc:
        return f"invalid /skills add syntax: {exc}"
    if len(parts) < 3 or parts[0] != "/skills" or parts[1] != "add":
        return "expected /skills add <name> [--category <category>] [--summary <summary>]"
    name_parts: list[str] = []
    index = 2
    while index < len(parts):
        token = parts[index]
        if token == "--category":
            if index + 1 >= len(parts) or parts[index + 1].startswith("--"):
                return "missing value for --category"
            index += 2
            continue
        if token == "--summary":
            index += 1
            if index >= len(parts) or parts[index] == "--category":
                return "missing value for --summary"
            while index < len(parts) and parts[index] != "--category":
                if parts[index].startswith("--"):
                    return f"unsupported /skills add flag: {parts[index]}"
                index += 1
            continue
        if token.startswith("--"):
            return f"unsupported /skills add flag: {token}"
        name_parts.append(token)
        index += 1
    if not " ".join(name_parts).strip():
        return "empty skill name"
    return {"ok": "true"}


def _parse_allowlisted_skills_body(command: str) -> dict[str, str] | str:
    try:
        parts = shlex.split(_normalize_cli_quotes(command))
    except ValueError as exc:
        return f"invalid /skills body syntax: {exc}"
    if len(parts) < 4 or parts[0] != "/skills" or parts[1] != "body":
        return "expected /skills body <id> <text>"
    if not parts[2].strip():
        return "empty skill id"
    if not " ".join(parts[3:]).strip():
        return "empty skill body"
    return {"id": parts[2], "text": " ".join(parts[3:])}


def _execute_allowlisted_apply_command(command: str, *, project_root: Path) -> str:
    if command.startswith("/memory remember "):
        data_dir = project_root / "proto_mind" / "data"
        store = MemoryStore(
            working_path=data_dir / "working_memory.json",
            persistent_path=data_dir / "persistent_memory.json",
        )
        output = format_memory_command(command, store)
    else:
        output = format_skill_command(command, project_root=project_root)
    return output or "No output returned by allowlisted command."


def _build_apply_receipt(command: str, command_kind: str, result: str) -> dict[str, str]:
    record_id = _extract_applied_record_id(result, command_kind, command)
    applied_kind = _receipt_kind_for_command(command_kind)
    undo = _undo_suggestion_for_receipt(applied_kind, record_id)
    return {
        "applied_kind": applied_kind,
        "applied_record_id": record_id,
        "undo_suggestion": undo,
    }


def _receipt_kind_for_command(command_kind: str) -> str:
    if command_kind == "memory_remember":
        return "memory"
    if command_kind == "skills_add":
        return "skill"
    if command_kind == "skills_body":
        return "skill_body"
    return "unknown"


def _extract_applied_record_id(result: str, command_kind: str, command: str) -> str:
    if command_kind == "memory_remember":
        match = re.search(r"\b(mem_[0-9]{8}_[0-9]{6}_[0-9a-f]{4})\b", result)
        return match.group(1) if match else ""
    if command_kind == "skills_add":
        match = re.search(r"\b(skill_[0-9]{14}_[0-9a-f]{4})\b", result)
        return match.group(1) if match else ""
    if command_kind == "skills_body":
        parsed = _parse_allowlisted_skills_body(command)
        if isinstance(parsed, dict):
            return parsed.get("id", "")
    return ""


def _undo_suggestion_for_receipt(applied_kind: str, record_id: str) -> str:
    if applied_kind == "memory" and record_id:
        return f"/memory forget {record_id}"
    if applied_kind == "skill" and record_id:
        return f"/skills archive {record_id}"
    if applied_kind == "skill_body":
        return "Manual review required: skill body was changed; inspect the skill and edit intentionally."
    return "Manual review required; no safe rollback command is available."


def _format_apply_receipt(item: dict[str, Any]) -> str:
    return "\n".join(
        [
            "Consolidation Queue Apply Receipt",
            f"id: {item.get('id')}",
            f"title: {item.get('title')}",
            f"status: {item.get('status')}",
            f"applied_at: {item.get('applied_at') or ''}",
            f"applied_command: {item.get('applied_command') or item.get('suggested_command') or ''}",
            f"applied_kind: {item.get('applied_kind') or 'unknown'}",
            f"applied_record_id: {item.get('applied_record_id') or ''}",
            f"apply_result: {item.get('apply_result') or ''}",
            f"undo_suggestion: {item.get('undo_suggestion') or ''}",
        ]
    )


def _unique_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _format_counter(counter: Counter[str]) -> str:
    if not counter:
        return "none"
    return ", ".join(f"{key}={counter[key]}" for key in sorted(counter))


def _atomic_write(path: Path, text: str) -> None:
    temp_path = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    temp_path.write_text(text, encoding="utf-8")
    temp_path.replace(path)


def _new_export_id(timestamp: str) -> str:
    return f"{_compact_timestamp(timestamp)}_{uuid4().hex[:4]}"


def _new_queue_id(timestamp: str) -> str:
    return f"cq_{_compact_timestamp(timestamp)}_{uuid4().hex[:4]}"


def _compact_timestamp(timestamp: str) -> str:
    return re.sub(r"[^0-9]", "", timestamp)[:14]


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _duplicates(values: list[str]) -> list[str]:
    by_norm: dict[str, str] = {}
    counts: Counter[str] = Counter()
    for value in values:
        norm = _normalize(value)
        if not norm:
            continue
        by_norm.setdefault(norm, value)
        counts[norm] += 1
    return [by_norm[norm] for norm, count in counts.items() if count > 1]


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s-]", " ", text.casefold())).strip()


def _preview(text: str, limit: int = 120) -> str:
    normalized = " ".join(text.split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 3] + "..."


def _format_bullets(values: list[str]) -> list[str]:
    if not values:
        return ["- none"]
    return [f"- {value}" for value in values]
