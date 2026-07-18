from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from proto_mind.goal_stack import GoalStack
from proto_mind.task_queue import TaskQueue


VALID_EXPERIMENT_STATUSES = {"open", "running", "completed", "inconclusive", "cancelled"}
ACTIVE_EXPERIMENT_STATUSES = {"open", "running"}


def format_experiment_command(command: str, *, project_root: Path) -> str | None:
    stripped = command.strip()
    normalized = " ".join(stripped.lower().split())
    if not normalized.startswith("/experiments"):
        return None

    journal = ExperimentJournal.from_project_root(project_root)
    if normalized == "/experiments status":
        return journal.format_status()
    if normalized.startswith("/experiments list"):
        parsed_list = _parse_list_command(stripped)
        if isinstance(parsed_list, str):
            return parsed_list
        return journal.format_list(
            include_all=parsed_list["include_all"],
            goal_id=parsed_list["goal_id"],
            task_id=parsed_list["task_id"],
        )
    if normalized.startswith("/experiments start"):
        parsed_start = _parse_start_command(stripped)
        if isinstance(parsed_start, str):
            return parsed_start
        return journal.start_experiment(
            parsed_start["title"],
            goal_id=parsed_start["goal_id"],
            task_id=parsed_start["task_id"],
        )
    if normalized.startswith("/experiments inspect"):
        experiment_id = stripped[len("/experiments inspect") :].strip()
        return journal.format_inspect(experiment_id)
    for field_name, verb in (
        ("hypothesis", "hypothesis"),
        ("prediction", "predict"),
        ("method", "method"),
        ("result", "result"),
        ("reflection", "reflect"),
        ("lesson", "lesson"),
    ):
        prefix = f"/experiments {verb}"
        if normalized.startswith(prefix):
            parsed_field = _parse_field_command(stripped, prefix, field_name)
            if isinstance(parsed_field, str):
                return parsed_field
            return journal.set_experiment_field(parsed_field["experiment_id"], field_name, parsed_field["text"])
    if normalized.startswith("/experiments run"):
        experiment_id = stripped[len("/experiments run") :].strip()
        return journal.set_experiment_status(experiment_id, "running")
    if normalized.startswith("/experiments complete"):
        experiment_id = stripped[len("/experiments complete") :].strip()
        return journal.set_experiment_status(experiment_id, "completed")
    if normalized.startswith("/experiments inconclusive"):
        experiment_id = stripped[len("/experiments inconclusive") :].strip()
        return journal.set_experiment_status(experiment_id, "inconclusive")
    if normalized.startswith("/experiments cancel"):
        experiment_id = stripped[len("/experiments cancel") :].strip()
        return journal.set_experiment_status(experiment_id, "cancelled")
    if normalized.startswith("/experiments reopen"):
        experiment_id = stripped[len("/experiments reopen") :].strip()
        return journal.set_experiment_status(experiment_id, "open")
    return (
        "Usage:\n"
        "  /experiments status\n"
        "  /experiments start <title> [--goal <goal_id>] [--task <task_id>]\n"
        "  /experiments list [--all] [--goal <goal_id>] [--task <task_id>]\n"
        "  /experiments inspect <id>\n"
        "  /experiments hypothesis <id> <text>\n"
        "  /experiments predict <id> <text>\n"
        "  /experiments method <id> <text>\n"
        "  /experiments run <id>\n"
        "  /experiments result <id> <text>\n"
        "  /experiments reflect <id> <text>\n"
        "  /experiments lesson <id> <text>\n"
        "  /experiments complete <id>\n"
        "  /experiments inconclusive <id>\n"
        "  /experiments cancel <id>\n"
        "  /experiments reopen <id>"
    )


class ExperimentJournal:
    def __init__(self, experiments_path: Path, *, project_root: Path) -> None:
        self.experiments_path = experiments_path
        self.project_root = project_root

    @classmethod
    def from_project_root(cls, project_root: Path) -> "ExperimentJournal":
        return cls(project_root / "proto_mind" / "data" / "experiments.jsonl", project_root=project_root)

    def format_status(self) -> str:
        state = self._read_state()
        records = state.records
        status_counts = {
            status: sum(1 for experiment in records if experiment.get("status") == status)
            for status in sorted(VALID_EXPERIMENT_STATUSES)
        }
        latest = _latest_experiment(records)
        health = "ok"
        if state.error:
            health = "error"
        elif state.malformed_count:
            health = "malformed_jsonl"
        elif not self.experiments_path.exists():
            health = "missing"
        lines = [
            "Experiment Journal status:",
            f"  path: {self.experiments_path}",
            f"  exists: {self.experiments_path.exists()}",
            f"  total_experiments: {len(records)}",
            f"  open: {status_counts.get('open', 0)}",
            f"  running: {status_counts.get('running', 0)}",
            f"  completed: {status_counts.get('completed', 0)}",
            f"  inconclusive: {status_counts.get('inconclusive', 0)}",
            f"  cancelled: {status_counts.get('cancelled', 0)}",
            f"  malformed_entries: {state.malformed_count}",
            f"  file_health: {health}",
            f"  latest_experiment: {_experiment_preview(latest) if latest else 'none'}",
        ]
        if state.error:
            lines.append(f"  error: {state.error}")
        return "\n".join(lines)

    def start_experiment(self, title: str, *, goal_id: str | None = None, task_id: str | None = None) -> str:
        title = title.strip()
        if not title:
            return "Usage: /experiments start <title> [--goal <goal_id>] [--task <task_id>]"
        if goal_id and not _goal_exists(self.project_root, goal_id):
            return f"Goal not found: {goal_id}"
        if task_id and not _task_exists(self.project_root, task_id):
            return f"Task not found: {task_id}"
        state = self._read_state()
        if state.has_load_problem:
            return _mutation_refused(state)
        now = _utc_now()
        experiment = {
            "id": _new_experiment_id(now),
            "created_at": now,
            "updated_at": now,
            "title": title,
            "status": "open",
            "hypothesis": "",
            "prediction": "",
            "method": "",
            "result": "",
            "reflection": "",
            "lesson": "",
            "goal_id": goal_id,
            "task_id": task_id,
            "source": "operator",
            "tags": [],
        }
        self._write_records([*state.records, experiment])
        link_note = _link_note(goal_id=goal_id, task_id=task_id)
        return f"Experiment started:\n  {experiment['id']} — {_preview(title)}{link_note}"

    def format_list(
        self,
        *,
        include_all: bool = False,
        goal_id: str | None = None,
        task_id: str | None = None,
    ) -> str:
        state = self._read_state()
        if state.error:
            return f"Experiment Journal error: {state.error}"
        records = state.records
        if goal_id:
            records = [experiment for experiment in records if experiment.get("goal_id") == goal_id]
        if task_id:
            records = [experiment for experiment in records if experiment.get("task_id") == task_id]
        if not include_all:
            records = [experiment for experiment in records if experiment.get("status") in ACTIVE_EXPERIMENT_STATUSES]
        heading = "Experiments:" if not include_all else "Experiments (all):"
        if goal_id:
            heading += f" goal={goal_id}"
        if task_id:
            heading += f" task={task_id}"
        lines = [heading]
        if state.malformed_count:
            lines.append(f"  malformed_entries_skipped: {state.malformed_count}")
        if not records:
            lines.append("  (none)")
            return "\n".join(lines)
        for experiment in sorted(records, key=lambda item: str(item.get("created_at", "")), reverse=True):
            lines.append(
                "  - "
                f"{experiment.get('id', 'unknown')} "
                f"[{experiment.get('status', 'unknown')}]"
                f"{_link_note(goal_id=experiment.get('goal_id'), task_id=experiment.get('task_id'))} "
                f"{_preview(str(experiment.get('title', '')))} "
                f"created_at={experiment.get('created_at', 'unknown')}"
            )
        return "\n".join(lines)

    def format_inspect(self, experiment_id: str) -> str:
        experiment_id = experiment_id.strip()
        if not experiment_id:
            return "Usage: /experiments inspect <id>"
        state = self._read_state()
        if state.error:
            return f"Experiment Journal error: {state.error}"
        experiment = _find_experiment(state.records, experiment_id)
        if not experiment:
            return f"Experiment not found: {experiment_id}"
        return _format_experiment_record(experiment)

    def set_experiment_field(self, experiment_id: str, field_name: str, text: str) -> str:
        experiment_id = experiment_id.strip()
        text = text.strip()
        if not experiment_id or not text:
            return f"Usage: /experiments {_field_to_command(field_name)} <id> <text>"
        state = self._read_state()
        if state.has_load_problem:
            return _mutation_refused(state)
        experiment = _find_experiment(state.records, experiment_id)
        if not experiment:
            return f"Experiment not found: {experiment_id}"
        experiment[field_name] = text
        experiment["updated_at"] = _utc_now()
        self._write_records(state.records)
        label = field_name.capitalize()
        return f"{label} updated:\n  {experiment_id} — {_preview(text)}"

    def set_experiment_status(self, experiment_id: str, status: str) -> str:
        experiment_id = experiment_id.strip()
        if not experiment_id:
            return f"Usage: /experiments {_status_to_command(status)} <id>"
        if status not in VALID_EXPERIMENT_STATUSES:
            return f"Invalid experiment status: {status}"
        state = self._read_state()
        if state.has_load_problem:
            return _mutation_refused(state)
        experiment = _find_experiment(state.records, experiment_id)
        if not experiment:
            return f"Experiment not found: {experiment_id}"
        experiment["status"] = status
        experiment["updated_at"] = _utc_now()
        self._write_records(state.records)
        lines = [f"{_status_label(status)} experiment:", f"  {experiment_id} — {_preview(str(experiment.get('title', '')))}"]
        if status == "completed" and experiment.get("task_id"):
            lines.append(f"  Linked task: {experiment.get('task_id')}. You may mark it done with /tasks done {experiment.get('task_id')} ...")
        return "\n".join(lines)

    def _read_state(self) -> "_ExperimentReadState":
        if not self.experiments_path.exists():
            return _ExperimentReadState(records=[], malformed_count=0, error=None)
        try:
            lines = self.experiments_path.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            return _ExperimentReadState(records=[], malformed_count=0, error=str(exc))
        records: list[dict[str, Any]] = []
        malformed_count = 0
        for raw_line in lines:
            if not raw_line.strip():
                continue
            try:
                parsed = json.loads(raw_line)
            except json.JSONDecodeError:
                malformed_count += 1
                continue
            if isinstance(parsed, dict):
                records.append(_normalize_experiment_record(parsed))
            else:
                malformed_count += 1
        return _ExperimentReadState(records=records, malformed_count=malformed_count, error=None)

    def _write_records(self, records: list[dict[str, Any]]) -> None:
        self.experiments_path.parent.mkdir(parents=True, exist_ok=True)
        payload = "".join(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n" for record in records)
        temp_path = self.experiments_path.with_name(f".{self.experiments_path.name}.{uuid4().hex}.tmp")
        temp_path.write_text(payload, encoding="utf-8")
        temp_path.replace(self.experiments_path)


class _ExperimentReadState:
    def __init__(self, *, records: list[dict[str, Any]], malformed_count: int, error: str | None) -> None:
        self.records = records
        self.malformed_count = malformed_count
        self.error = error

    @property
    def has_load_problem(self) -> bool:
        return bool(self.error or self.malformed_count)


def _parse_start_command(command: str) -> dict[str, str | None] | str:
    remainder = command.strip()[len("/experiments start") :].strip()
    if not remainder:
        return "Usage: /experiments start <title> [--goal <goal_id>] [--task <task_id>]"
    goal_id: str | None = None
    task_id: str | None = None
    parts = remainder.split()
    index = 0
    title_parts: list[str] = []
    while index < len(parts):
        token = parts[index].lower()
        if token == "--goal":
            if index + 1 >= len(parts):
                return "Invalid --goal value. Usage: /experiments start <title> [--goal <goal_id>] [--task <task_id>]"
            goal_id = parts[index + 1]
            index += 2
            continue
        if token == "--task":
            if index + 1 >= len(parts):
                return "Invalid --task value. Usage: /experiments start <title> [--goal <goal_id>] [--task <task_id>]"
            task_id = parts[index + 1]
            index += 2
            continue
        title_parts.append(parts[index])
        index += 1
    title = " ".join(title_parts).strip()
    if not title:
        return "Usage: /experiments start <title> [--goal <goal_id>] [--task <task_id>]"
    return {"title": title, "goal_id": goal_id, "task_id": task_id}


def _parse_list_command(command: str) -> dict[str, Any] | str:
    parts = command.strip().split()
    include_all = False
    goal_id: str | None = None
    task_id: str | None = None
    index = 2
    while index < len(parts):
        token = parts[index].lower()
        if token == "--all":
            include_all = True
            index += 1
            continue
        if token == "--goal":
            if index + 1 >= len(parts):
                return "Invalid --goal value. Usage: /experiments list [--all] [--goal <goal_id>] [--task <task_id>]"
            goal_id = parts[index + 1]
            index += 2
            continue
        if token == "--task":
            if index + 1 >= len(parts):
                return "Invalid --task value. Usage: /experiments list [--all] [--goal <goal_id>] [--task <task_id>]"
            task_id = parts[index + 1]
            index += 2
            continue
        return "Usage: /experiments list [--all] [--goal <goal_id>] [--task <task_id>]"
    return {"include_all": include_all, "goal_id": goal_id, "task_id": task_id}


def _parse_field_command(command: str, prefix: str, field_name: str) -> dict[str, str] | str:
    remainder = command.strip()[len(prefix) :].strip()
    parts = remainder.split(maxsplit=1)
    if len(parts) != 2 or not parts[1].strip():
        return f"Usage: /experiments {_field_to_command(field_name)} <id> <text>"
    return {"experiment_id": parts[0], "text": parts[1].strip()}


def _normalize_experiment_record(record: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(record)
    normalized.setdefault("status", "open")
    normalized.setdefault("hypothesis", "")
    normalized.setdefault("prediction", "")
    normalized.setdefault("method", "")
    normalized.setdefault("result", "")
    normalized.setdefault("reflection", "")
    normalized.setdefault("lesson", "")
    normalized.setdefault("goal_id", None)
    normalized.setdefault("task_id", None)
    normalized.setdefault("source", "operator")
    normalized.setdefault("tags", [])
    return normalized


def _format_experiment_record(experiment: dict[str, Any]) -> str:
    return "\n".join(
        [
            "Experiment:",
            f"  id: {experiment.get('id', 'unknown')}",
            f"  title: {experiment.get('title', '')}",
            f"  status: {experiment.get('status', 'unknown')}",
            f"  hypothesis: {experiment.get('hypothesis', '')}",
            f"  prediction: {experiment.get('prediction', '')}",
            f"  method: {experiment.get('method', '')}",
            f"  result: {experiment.get('result', '')}",
            f"  reflection: {experiment.get('reflection', '')}",
            f"  lesson: {experiment.get('lesson', '')}",
            f"  goal_id: {experiment.get('goal_id')}",
            f"  task_id: {experiment.get('task_id')}",
            f"  created_at: {experiment.get('created_at', 'unknown')}",
            f"  updated_at: {experiment.get('updated_at', 'unknown')}",
            f"  source: {experiment.get('source', 'unknown')}",
            f"  tags: {experiment.get('tags', [])}",
        ]
    )


def _find_experiment(records: list[dict[str, Any]], experiment_id: str) -> dict[str, Any] | None:
    for experiment in records:
        if experiment.get("id") == experiment_id:
            return experiment
    return None


def _latest_experiment(records: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not records:
        return None
    return sorted(records, key=lambda item: str(item.get("created_at", "")), reverse=True)[0]


def _experiment_preview(experiment: dict[str, Any]) -> str:
    return f"{experiment.get('id', 'unknown')} [{experiment.get('status', 'unknown')}] — {_preview(str(experiment.get('title', '')))}"


def _goal_exists(project_root: Path, goal_id: str) -> bool:
    state = GoalStack.from_project_root(project_root)._read_state()
    return any(goal.get("id") == goal_id for goal in state.records)


def _task_exists(project_root: Path, task_id: str) -> bool:
    state = TaskQueue.from_project_root(project_root)._read_state()
    return any(task.get("id") == task_id for task in state.records)


def _mutation_refused(state: _ExperimentReadState) -> str:
    if state.error:
        return f"Experiment Journal error: {state.error}"
    return "Experiment Journal error: experiments file contains malformed JSONL; refusing to modify."


def _field_to_command(field_name: str) -> str:
    return {"prediction": "predict", "reflection": "reflect"}.get(field_name, field_name)


def _status_to_command(status: str) -> str:
    return status


def _status_label(status: str) -> str:
    return {
        "open": "Reopened",
        "running": "Running",
        "completed": "Completed",
        "inconclusive": "Inconclusive",
        "cancelled": "Cancelled",
    }.get(status, status.capitalize())


def _link_note(*, goal_id: object, task_id: object) -> str:
    parts: list[str] = []
    if goal_id:
        parts.append(f"goal={goal_id}")
    if task_id:
        parts.append(f"task={task_id}")
    return (" " + " ".join(parts)) if parts else ""


def _new_experiment_id(timestamp: str) -> str:
    compact = re.sub(r"[^0-9]", "", timestamp)[:14]
    return f"exp_{compact}_{uuid4().hex[:4]}"


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _preview(text: str, limit: int = 120) -> str:
    normalized = " ".join(text.split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 3] + "..."
