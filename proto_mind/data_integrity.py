from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class StoreSpec:
    name: str
    relative_path: str
    store_type: str
    expected_root: str | None = None
    important: bool = True


KNOWN_STORES = [
    StoreSpec("working_memory", "proto_mind/data/working_memory.json", "json", "list"),
    StoreSpec("persistent_memory", "proto_mind/data/persistent_memory.json", "json", "list"),
    StoreSpec("reflection_journal", "proto_mind/data/reflection_journal.jsonl", "jsonl"),
    StoreSpec("goals", "proto_mind/data/goals.jsonl", "jsonl"),
    StoreSpec("tasks", "proto_mind/data/tasks.jsonl", "jsonl"),
    StoreSpec("experiments", "proto_mind/data/experiments.jsonl", "jsonl"),
    StoreSpec("skills", "proto_mind/data/skills.jsonl", "jsonl"),
    StoreSpec("world_model", "proto_mind/data/world_model.jsonl", "jsonl"),
    StoreSpec("identity", "proto_mind/data/identity.json", "json", "dict"),
    StoreSpec("context_injection", "proto_mind/data/context_injection.json", "json", "dict"),
    StoreSpec("context_injection_audit", "proto_mind/data/context_injection_audit.jsonl", "jsonl"),
    StoreSpec("consolidation_queue", "proto_mind/data/consolidation_queue.jsonl", "jsonl"),
    StoreSpec("action_queue", "proto_mind/data/action_queue.jsonl", "jsonl"),
    StoreSpec("session_operator_log", "logs/session_operator_log.jsonl", "jsonl", important=False),
]

EXPORT_DIRS = [
    "context_packs",
    "context_prompts",
    "consolidation",
    "consolidation_queue",
    "action_queue",
    "proto_snapshots",
    "proto_snapshot_diffs",
]


def format_data_command(command: str, *, project_root: Path) -> str | None:
    normalized = " ".join(command.strip().lower().split())
    if not normalized.startswith("/data"):
        return None
    doctor = DataIntegrityDoctor.from_project_root(project_root)
    if normalized == "/data status":
        return doctor.format_status()
    if normalized == "/data inventory":
        return doctor.format_inventory()
    if normalized == "/data doctor":
        return doctor.format_doctor()
    if normalized == "/data refs":
        return doctor.format_references()
    if normalized == "/data refs-doctor":
        return doctor.format_references_doctor()
    return "Usage:\n  /data status\n  /data inventory\n  /data doctor\n  /data refs\n  /data refs-doctor"


class DataIntegrityDoctor:
    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root
        self.data_dir = project_root / "proto_mind" / "data"
        self.exports_dir = project_root / "proto_mind" / "exports"
        self.backups_dir = project_root / "backups"

    @classmethod
    def from_project_root(cls, project_root: Path) -> "DataIntegrityDoctor":
        return cls(project_root)

    def inventory(self) -> dict[str, Any]:
        stores = [self._inspect_store(spec) for spec in KNOWN_STORES]
        exports = [self._inspect_export_dir(name) for name in EXPORT_DIRS]
        return {"stores": stores, "exports": exports}

    def format_status(self) -> str:
        inventory = self.inventory()
        stores = inventory["stores"]
        existing = [store for store in stores if store["exists"]]
        total_size = sum(int(store["size_bytes"]) for store in stores if store["exists"])
        export_count = sum(1 for item in inventory["exports"] if item["exists"])
        lines = [
            "Data Integrity Status",
            f"data_dir: {self.data_dir}",
            f"exports_dir: {self.exports_dir}",
            f"backups_dir: {self.backups_dir}",
            f"known_stores: {len(stores)}",
            f"existing_stores: {len(existing)}",
            f"missing_stores: {len(stores) - len(existing)}",
            f"export_dirs_present: {export_count}/{len(EXPORT_DIRS)}",
            f"approx_store_size_bytes: {total_size}",
            f"backups_dir_exists: {self.backups_dir.exists()}",
            "",
            "Available commands:",
            "- /data status",
            "- /data inventory",
            "- /data doctor",
            "- /data refs",
            "- /data refs-doctor",
        ]
        return "\n".join(lines)

    def format_inventory(self) -> str:
        inventory = self.inventory()
        lines = [
            "Data Inventory",
            "",
            "Stores:",
        ]
        for store in inventory["stores"]:
            lines.append(
                "- "
                f"{store['name']}: path={store['path']} exists={store['exists']} "
                f"type={store['type']} records={store['record_count']} "
                f"size={store['size_bytes']} modified={store['modified_at']}"
            )
            if store["error"]:
                lines.append(f"  error: {store['error']}")
            if store["malformed_count"]:
                lines.append(f"  malformed_lines: {store['malformed_count']}")
        lines.extend(["", "Export directories:"])
        for export in inventory["exports"]:
            lines.append(
                "- "
                f"{export['name']}: path={export['path']} exists={export['exists']} "
                f"files={export['file_count']} size={export['size_bytes']}"
            )
        return "\n".join(lines)

    def format_doctor(self) -> str:
        report = self.doctor_report()
        lines = [
            "Data Integrity Doctor",
            f"Status: {report['status']}",
            "",
            "Summary:",
            f"- stores checked: {len(report['stores'])}",
            f"- export dirs checked: {len(report['exports'])}",
            f"- total store size bytes: {report['total_size_bytes']}",
            "",
            "Findings:",
        ]
        if not report["findings"]:
            lines.append("- [OK] Data stores look healthy.")
        else:
            for finding in report["findings"]:
                lines.append(f"- [{finding['severity']}] {finding['message']}")
        lines.extend(["", "Mutation policy:", "- Read-only diagnostics only; no files were changed."])
        return "\n".join(lines)

    def format_references(self) -> str:
        report = self.reference_report()
        lines = [
            "Cross-Store Reference Inventory",
            "",
            "Focused goal:",
        ]
        focused = report["focused_goals"]
        if focused:
            for goal in focused:
                lines.append(
                    f"- {goal.get('id', 'unknown')} status={goal.get('status', 'unknown')} "
                    f"title={_preview(str(goal.get('title') or ''))}"
                )
        else:
            lines.append("- none")
        lines.extend(["", "Reference groups:"])
        for group_name, group in report["groups"].items():
            lines.append(
                f"- {group_name}: total={len(group)} "
                f"resolved={sum(1 for item in group if item['resolved'])} "
                f"missing={sum(1 for item in group if not item['resolved'])}"
            )
            for item in group:
                state = "resolved" if item["resolved"] else "missing"
                target = item["target_id"] or "(empty)"
                lines.append(
                    f"  - {item['source_id']} -> {item['target_type']}:{target} [{state}]"
                )
        if report["source_issues"]:
            lines.extend(["", "Source health:"])
            for issue in report["source_issues"]:
                lines.append(f"- [{issue['severity']}] {issue['message']}")
        lines.extend(["", "Mutation policy:", "- Read-only inventory only; no files were changed."])
        return "\n".join(lines)

    def format_references_doctor(self) -> str:
        report = self.references_doctor_report()
        lines = [
            "Cross-Store Reference Doctor",
            f"Status: {report['status']}",
            "",
            "Summary:",
            f"- focused goals: {len(report['focused_goals'])}",
            f"- references checked: {report['references_checked']}",
            f"- dangling references: {report['dangling_count']}",
            "",
            "Findings:",
        ]
        if not report["findings"]:
            lines.append("- [OK] Cross-store references look consistent.")
        else:
            for finding in report["findings"]:
                lines.append(f"- [{finding['severity']}] {finding['message']}")
        lines.extend(["", "Mutation policy:", "- Read-only diagnostics only; no files were changed."])
        return "\n".join(lines)

    def reference_report(self) -> dict[str, Any]:
        stores = {
            "goals": self._read_reference_jsonl("goals.jsonl"),
            "tasks": self._read_reference_jsonl("tasks.jsonl"),
            "experiments": self._read_reference_jsonl("experiments.jsonl"),
            "world_model": self._read_reference_jsonl("world_model.jsonl"),
            "skills": self._read_reference_jsonl("skills.jsonl"),
            "consolidation_queue": self._read_reference_jsonl("consolidation_queue.jsonl"),
            "persistent_memory": self._read_reference_json("persistent_memory.json", expected_root=list),
            "working_memory": self._read_reference_json("working_memory.json", expected_root=list),
        }
        source_issues: list[dict[str, str]] = []
        for name, state in stores.items():
            if state["missing"]:
                source_issues.append({"severity": "WARN", "message": f"Reference source missing: {name}"})
            if state["error"]:
                source_issues.append({"severity": "ERROR", "message": f"Reference source {name}: {state['error']}"})
            if state["malformed_count"]:
                source_issues.append(
                    {"severity": "WARN", "message": f"Reference source {name} has malformed lines: {state['malformed_count']}"}
                )

        records = {name: state["records"] for name, state in stores.items()}
        goals = _records_by_id(records["goals"])
        tasks = _records_by_id(records["tasks"])
        experiments = _records_by_id(records["experiments"])
        skills = _records_by_id(records["skills"])
        memories = _records_by_id([*records["persistent_memory"], *records["working_memory"]])
        groups: dict[str, list[dict[str, Any]]] = {
            "tasks -> goals": [],
            "experiments -> goals/tasks": [],
            "world_model -> goals/tasks/experiments": [],
            "applied queue receipts -> memories/skills": [],
        }
        for task in records["tasks"]:
            _append_reference(groups["tasks -> goals"], task, "goal", task.get("goal_id"), goals)
        for experiment in records["experiments"]:
            _append_reference(groups["experiments -> goals/tasks"], experiment, "goal", experiment.get("goal_id"), goals)
            _append_reference(groups["experiments -> goals/tasks"], experiment, "task", experiment.get("task_id"), tasks)
        for world in records["world_model"]:
            _append_reference(groups["world_model -> goals/tasks/experiments"], world, "goal", world.get("goal_id"), goals)
            _append_reference(groups["world_model -> goals/tasks/experiments"], world, "task", world.get("task_id"), tasks)
            _append_reference(
                groups["world_model -> goals/tasks/experiments"], world, "experiment", world.get("experiment_id"), experiments
            )
        for item in records["consolidation_queue"]:
            if item.get("status") != "applied":
                continue
            kind = _queue_applied_kind(item)
            if kind == "memory":
                _append_reference(groups["applied queue receipts -> memories/skills"], item, "memory", item.get("applied_record_id"), memories, include_empty=True)
            elif kind in {"skill", "skill_body"}:
                _append_reference(groups["applied queue receipts -> memories/skills"], item, "skill", item.get("applied_record_id"), skills, include_empty=True)
        return {
            "stores": stores,
            "records": records,
            "focused_goals": [goal for goal in records["goals"] if goal.get("focus") is True],
            "groups": groups,
            "source_issues": source_issues,
            "indexes": {"goals": goals, "tasks": tasks, "experiments": experiments, "skills": skills, "memories": memories},
        }

    def references_doctor_report(self) -> dict[str, Any]:
        report = self.reference_report()
        findings = list(report["source_issues"])
        focused = report["focused_goals"]
        goals_state = report["stores"]["goals"]
        if not focused and not goals_state["missing"] and not goals_state["error"]:
            findings.append({"severity": "WARN", "message": "No focused goal is selected"})
        if len(focused) > 1:
            findings.append({"severity": "WARN", "message": f"Multiple focused goals detected: {', '.join(_record_id(goal) for goal in focused)}"})
        for goal in focused:
            if goal.get("status") != "active":
                findings.append(
                    {"severity": "WARN", "message": f"Focused goal is not active: {_record_id(goal)} status={goal.get('status', 'unknown')}"}
                )

        dangling_count = 0
        for group in report["groups"].values():
            for reference in group:
                if reference["resolved"]:
                    continue
                dangling_count += 1
                if reference["target_id"]:
                    message = (
                        f"{reference['source_type']} {_record_id(reference['source'])} references missing "
                        f"{reference['target_type']}: {reference['target_id']}"
                    )
                else:
                    message = (
                        f"Applied queue item {_record_id(reference['source'])} is missing applied_record_id "
                        f"for {reference['target_type']} receipt"
                    )
                findings.append({"severity": "WARN", "message": message})

        goals = report["indexes"]["goals"]
        for task in report["records"]["tasks"]:
            goal_id = str(task.get("goal_id") or "").strip()
            goal = goals.get(goal_id)
            if (
                goal
                and goal.get("status") in {"completed", "cancelled"}
                and task.get("status") in {"open", "in_progress", "blocked"}
            ):
                findings.append(
                    {
                        "severity": "WARN",
                        "message": f"Active task {_record_id(task)} is linked to terminal goal {goal_id} status={goal.get('status')}",
                    }
                )

        for item in report["records"]["consolidation_queue"]:
            if item.get("status") != "applied":
                continue
            undo = str(item.get("undo_suggestion") or "").strip()
            undo_target = _undo_target(undo)
            if not undo_target:
                continue
            target_type, target_id = undo_target
            target_index = report["indexes"]["memories" if target_type == "memory" else "skills"]
            if target_id not in target_index:
                findings.append(
                    {
                        "severity": "WARN",
                        "message": f"Applied queue item {_record_id(item)} undo suggestion points to missing {target_type}: {target_id}",
                    }
                )

        status = "OK"
        if any(finding["severity"] == "ERROR" for finding in findings):
            status = "ERROR"
        elif any(finding["severity"] == "WARN" for finding in findings):
            status = "WARN"
        references_checked = sum(len(group) for group in report["groups"].values())
        return {
            "status": status,
            "focused_goals": focused,
            "references_checked": references_checked,
            "dangling_count": dangling_count,
            "findings": findings,
        }

    def _read_reference_jsonl(self, filename: str) -> dict[str, Any]:
        path = self.data_dir / filename
        state = {"path": path, "records": [], "missing": not path.exists(), "error": "", "malformed_count": 0}
        if state["missing"]:
            return state
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            state["error"] = f"unreadable: {exc}"
            return state
        for line in lines:
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                state["malformed_count"] += 1
                continue
            if isinstance(record, dict):
                state["records"].append(record)
            else:
                state["malformed_count"] += 1
        return state

    def _read_reference_json(self, filename: str, *, expected_root: type) -> dict[str, Any]:
        path = self.data_dir / filename
        state = {"path": path, "records": [], "missing": not path.exists(), "error": "", "malformed_count": 0}
        if state["missing"]:
            return state
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except OSError as exc:
            state["error"] = f"unreadable: {exc}"
            return state
        except json.JSONDecodeError as exc:
            state["error"] = f"invalid JSON: {exc}"
            return state
        if not isinstance(payload, expected_root):
            state["error"] = f"wrong JSON root type: expected {expected_root.__name__}"
            return state
        state["records"] = [record for record in payload if isinstance(record, dict)]
        return state

    def doctor_report(self) -> dict[str, Any]:
        inventory = self.inventory()
        findings: list[dict[str, str]] = []
        now = datetime.now(UTC)
        for store in inventory["stores"]:
            if not store["exists"]:
                severity = "WARN" if store["important"] else "INFO"
                findings.append({"severity": severity, "message": f"Missing expected store: {store['name']} ({store['path']})"})
                continue
            if store["error"]:
                severity = "ERROR" if store["error_kind"] in {"unreadable", "invalid_json"} else "WARN"
                findings.append({"severity": severity, "message": f"{store['name']} read/parse issue: {store['error']}"})
            if store["wrong_root"]:
                findings.append({"severity": "ERROR", "message": f"{store['name']} has wrong JSON root type: expected {store['expected_root']}"})
            if store["malformed_count"]:
                findings.append({"severity": "WARN", "message": f"{store['name']} has malformed JSONL lines: {store['malformed_count']}"})
            if store["important"] and store["record_count"] == 0 and store["type"] in {"json", "jsonl"}:
                findings.append({"severity": "WARN", "message": f"{store['name']} is empty"})
            if store["size_bytes"] > 5_000_000:
                findings.append({"severity": "WARN", "message": f"{store['name']} is unusually large: {store['size_bytes']} bytes"})
            if store["duplicate_ids"]:
                findings.append({"severity": "WARN", "message": f"{store['name']} has duplicate ids: {', '.join(store['duplicate_ids'][:5])}"})
            if store["missing_id_count"]:
                findings.append({"severity": "WARN", "message": f"{store['name']} records missing id: {store['missing_id_count']}"})
            if store["future_timestamps"]:
                findings.append({"severity": "WARN", "message": f"{store['name']} has future timestamps: {', '.join(store['future_timestamps'][:5])}"})
            modified_at = store.get("modified_datetime")
            if isinstance(modified_at, datetime) and modified_at > now + timedelta(minutes=5):
                findings.append({"severity": "WARN", "message": f"{store['name']} file modified time is in the future"})
        if not self.backups_dir.exists():
            findings.append({"severity": "WARN", "message": f"Backup directory missing: {self.backups_dir}"})
        for export in inventory["exports"]:
            if not export["exists"]:
                findings.append({"severity": "WARN", "message": f"Export directory missing: {export['name']} ({export['path']})"})
        status = "OK"
        if any(finding["severity"] == "ERROR" for finding in findings):
            status = "ERROR"
        elif any(finding["severity"] == "WARN" for finding in findings):
            status = "WARN"
        return {
            "status": status,
            "stores": inventory["stores"],
            "exports": inventory["exports"],
            "findings": findings,
            "total_size_bytes": sum(int(store["size_bytes"]) for store in inventory["stores"] if store["exists"]),
        }

    def _inspect_store(self, spec: StoreSpec) -> dict[str, Any]:
        path = self.project_root / spec.relative_path
        base: dict[str, Any] = {
            "name": spec.name,
            "path": str(path),
            "exists": path.exists(),
            "type": spec.store_type,
            "expected_root": spec.expected_root or "",
            "important": spec.important,
            "record_count": 0,
            "size_bytes": 0,
            "modified_at": "missing",
            "modified_datetime": None,
            "error": "",
            "error_kind": "",
            "malformed_count": 0,
            "wrong_root": False,
            "duplicate_ids": [],
            "missing_id_count": 0,
            "future_timestamps": [],
        }
        if not path.exists():
            return base
        try:
            stat = path.stat()
        except OSError as exc:
            base["error"] = str(exc)
            base["error_kind"] = "unreadable"
            return base
        base["size_bytes"] = stat.st_size
        modified = datetime.fromtimestamp(stat.st_mtime, UTC)
        base["modified_datetime"] = modified
        base["modified_at"] = modified.isoformat()
        if spec.store_type == "json":
            self._inspect_json_store(path, spec, base)
        elif spec.store_type == "jsonl":
            self._inspect_jsonl_store(path, base)
        return base

    def _inspect_json_store(self, path: Path, spec: StoreSpec, base: dict[str, Any]) -> None:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except OSError as exc:
            base["error"] = str(exc)
            base["error_kind"] = "unreadable"
            return
        except json.JSONDecodeError as exc:
            base["error"] = f"invalid JSON: {exc}"
            base["error_kind"] = "invalid_json"
            return
        if spec.expected_root == "list" and not isinstance(payload, list):
            base["wrong_root"] = True
        if spec.expected_root == "dict" and not isinstance(payload, dict):
            base["wrong_root"] = True
        records = payload if isinstance(payload, list) else [payload] if isinstance(payload, dict) else []
        base["record_count"] = len(records)
        _add_record_diagnostics(base, records, expect_ids=isinstance(payload, list))

    def _inspect_jsonl_store(self, path: Path, base: dict[str, Any]) -> None:
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            base["error"] = str(exc)
            base["error_kind"] = "unreadable"
            return
        records: list[Any] = []
        malformed = 0
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
        base["record_count"] = len(records)
        base["malformed_count"] = malformed
        if malformed:
            base["error"] = f"malformed JSONL lines: {malformed}"
            base["error_kind"] = "malformed_jsonl"
        _add_record_diagnostics(base, records, expect_ids=True)

    def _inspect_export_dir(self, name: str) -> dict[str, Any]:
        path = self.exports_dir / name
        if not path.exists():
            return {"name": name, "path": str(path), "exists": False, "file_count": 0, "size_bytes": 0}
        files = [item for item in path.rglob("*") if item.is_file()]
        size = sum(item.stat().st_size for item in files)
        return {"name": name, "path": str(path), "exists": True, "file_count": len(files), "size_bytes": size}


def _add_record_diagnostics(base: dict[str, Any], records: list[Any], *, expect_ids: bool) -> None:
    ids: list[str] = []
    missing_ids = 0
    future_timestamps: list[str] = []
    now = datetime.now(UTC)
    for index, record in enumerate(records, start=1):
        if not isinstance(record, dict):
            continue
        record_id = str(record.get("id") or "")
        if record_id:
            ids.append(record_id)
        elif expect_ids and _record_should_have_id(record):
            missing_ids += 1
        for field in ("created_at", "updated_at", "applied_at", "last_used_at", "timestamp"):
            value = record.get(field)
            if isinstance(value, str) and _is_future_timestamp(value, now):
                future_timestamps.append(record_id or f"record#{index}:{field}")
    counts = Counter(ids)
    base["duplicate_ids"] = sorted(record_id for record_id, count in counts.items() if count > 1)
    base["missing_id_count"] = missing_ids
    base["future_timestamps"] = future_timestamps


def _record_should_have_id(record: dict[str, Any]) -> bool:
    return any(key in record for key in ("created_at", "updated_at", "content", "title", "name", "status", "event"))


def _is_future_timestamp(value: str, now: datetime) -> bool:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed > now + timedelta(minutes=5)


def _records_by_id(records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {_record_id(record): record for record in records if _record_id(record)}


def _record_id(record: dict[str, Any]) -> str:
    return str(record.get("id") or "unknown")


def _append_reference(
    group: list[dict[str, Any]],
    source: dict[str, Any],
    target_type: str,
    target_id: Any,
    target_index: dict[str, dict[str, Any]],
    *,
    include_empty: bool = False,
) -> None:
    normalized_id = str(target_id or "").strip()
    if not normalized_id and not include_empty:
        return
    group.append(
        {
            "source": source,
            "source_id": _record_id(source),
            "source_type": _source_type(source),
            "target_type": target_type,
            "target_id": normalized_id,
            "resolved": bool(normalized_id and normalized_id in target_index),
        }
    )


def _source_type(record: dict[str, Any]) -> str:
    record_id = _record_id(record)
    if record_id.startswith("task_"):
        return "Task"
    if record_id.startswith("exp_"):
        return "Experiment"
    if record_id.startswith("wm_"):
        return "World prediction"
    if record_id.startswith("cq_"):
        return "Consolidation queue item"
    return "Record"


def _queue_applied_kind(item: dict[str, Any]) -> str:
    kind = str(item.get("applied_kind") or "").strip()
    if kind:
        return kind
    command = str(item.get("applied_command") or item.get("suggested_command") or "").strip()
    if command.startswith("/memory remember "):
        return "memory"
    if command.startswith("/skills add "):
        return "skill"
    if command.startswith("/skills body "):
        return "skill_body"
    return "unknown"


def _undo_target(undo_suggestion: str) -> tuple[str, str] | None:
    parts = undo_suggestion.split()
    if len(parts) == 3 and parts[:2] == ["/memory", "forget"]:
        return "memory", parts[2]
    if len(parts) == 3 and parts[:2] == ["/skills", "archive"]:
        return "skill", parts[2]
    return None


def _preview(text: str, limit: int = 80) -> str:
    compact = " ".join(text.split())
    return compact if len(compact) <= limit else compact[: limit - 3].rstrip() + "..."
