from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from proto_mind.goal_stack import GoalStack


VALID_TASK_STATUSES = {"open", "in_progress", "blocked", "done", "cancelled"}
VALID_TASK_PRIORITIES = {"high", "normal", "low"}
ACTIVE_TASK_STATUSES = {"open", "in_progress", "blocked"}
PRIORITY_RANK = {"high": 0, "normal": 1, "low": 2}


def format_task_command(command: str, *, project_root: Path) -> str | None:
    stripped = command.strip()
    normalized = " ".join(stripped.lower().split())
    if not normalized.startswith("/tasks"):
        return None

    queue = TaskQueue.from_project_root(project_root)
    if normalized == "/tasks status":
        return queue.format_status()
    if normalized.startswith("/tasks list"):
        parsed_list = _parse_list_command(stripped)
        if isinstance(parsed_list, str):
            return parsed_list
        return queue.format_list(include_all=parsed_list["include_all"], goal_id=parsed_list["goal_id"])
    if normalized == "/tasks next":
        return queue.format_next()
    if normalized.startswith("/tasks add"):
        parsed_add = _parse_add_command(stripped)
        if isinstance(parsed_add, str):
            return parsed_add
        return queue.add_task(parsed_add["title"], priority=parsed_add["priority"], goal_id=parsed_add["goal_id"])
    if normalized.startswith("/tasks inspect"):
        task_id = stripped[len("/tasks inspect") :].strip()
        return queue.format_inspect(task_id)
    if normalized.startswith("/tasks start"):
        task_id = stripped[len("/tasks start") :].strip()
        return queue.set_task_status(task_id, "in_progress")
    if normalized.startswith("/tasks block"):
        parsed_block = _parse_block_command(stripped)
        if isinstance(parsed_block, str):
            return parsed_block
        return queue.block_task(parsed_block["task_id"], parsed_block["reason"])
    if normalized.startswith("/tasks unblock"):
        task_id = stripped[len("/tasks unblock") :].strip()
        return queue.unblock_task(task_id)
    if normalized.startswith("/tasks done"):
        parsed_done = _parse_done_command(stripped)
        if isinstance(parsed_done, str):
            return parsed_done
        return queue.done_task(parsed_done["task_id"], parsed_done["result"])
    if normalized.startswith("/tasks cancel"):
        task_id = stripped[len("/tasks cancel") :].strip()
        return queue.set_task_status(task_id, "cancelled", clear_blocked=True)
    if normalized.startswith("/tasks reopen"):
        task_id = stripped[len("/tasks reopen") :].strip()
        return queue.set_task_status(task_id, "open", clear_blocked=True)
    return (
        "Usage:\n"
        "  /tasks status\n"
        "  /tasks add <title> [--priority high|normal|low] [--goal <goal_id>]\n"
        "  /tasks list [--all] [--goal <goal_id>]\n"
        "  /tasks next\n"
        "  /tasks inspect <id>\n"
        "  /tasks start <id>\n"
        "  /tasks block <id> <reason>\n"
        "  /tasks unblock <id>\n"
        "  /tasks done <id> [result text]\n"
        "  /tasks cancel <id>\n"
        "  /tasks reopen <id>"
    )


class TaskQueue:
    def __init__(self, tasks_path: Path, *, project_root: Path) -> None:
        self.tasks_path = tasks_path
        self.project_root = project_root

    @classmethod
    def from_project_root(cls, project_root: Path) -> "TaskQueue":
        return cls(project_root / "proto_mind" / "data" / "tasks.jsonl", project_root=project_root)

    def format_status(self) -> str:
        state = self._read_state()
        records = state.records
        status_counts = {status: sum(1 for task in records if task.get("status") == status) for status in sorted(VALID_TASK_STATUSES)}
        next_task = _next_task(records)
        health = "ok"
        if state.error:
            health = "error"
        elif state.malformed_count:
            health = "malformed_jsonl"
        elif not self.tasks_path.exists():
            health = "missing"
        lines = [
            "Task Queue status:",
            f"  path: {self.tasks_path}",
            f"  exists: {self.tasks_path.exists()}",
            f"  total_tasks: {len(records)}",
            f"  open: {status_counts.get('open', 0)}",
            f"  in_progress: {status_counts.get('in_progress', 0)}",
            f"  blocked: {status_counts.get('blocked', 0)}",
            f"  done: {status_counts.get('done', 0)}",
            f"  cancelled: {status_counts.get('cancelled', 0)}",
            f"  malformed_entries: {state.malformed_count}",
            f"  file_health: {health}",
            f"  next_task: {_task_preview(next_task) if next_task else 'none'}",
        ]
        if state.error:
            lines.append(f"  error: {state.error}")
        return "\n".join(lines)

    def add_task(self, title: str, *, priority: str = "normal", goal_id: str | None = None) -> str:
        title = title.strip()
        if not title:
            return "Usage: /tasks add <title> [--priority high|normal|low] [--goal <goal_id>]"
        if priority not in VALID_TASK_PRIORITIES:
            return "Invalid --priority value. Usage: /tasks add <title> [--priority high|normal|low] [--goal <goal_id>]"
        if goal_id and not _goal_exists(self.project_root, goal_id):
            return f"Goal not found: {goal_id}"
        state = self._read_state()
        if state.has_load_problem:
            return _mutation_refused(state)
        now = _utc_now()
        task = {
            "id": _new_task_id(now),
            "created_at": now,
            "updated_at": now,
            "title": title,
            "description": "",
            "status": "open",
            "priority": priority,
            "goal_id": goal_id,
            "source": "operator",
            "tags": [],
            "result": "",
            "blocked_reason": "",
        }
        self._write_records([*state.records, task])
        goal_note = f" goal={goal_id}" if goal_id else ""
        return f"Task added:\n  {task['id']} — {_preview(title)}{goal_note}"

    def format_list(self, *, include_all: bool = False, goal_id: str | None = None) -> str:
        state = self._read_state()
        if state.error:
            return f"Task Queue error: {state.error}"
        records = state.records
        if goal_id:
            records = [task for task in records if task.get("goal_id") == goal_id]
        if not include_all:
            records = [task for task in records if task.get("status") in ACTIVE_TASK_STATUSES]
        heading = "Tasks:" if not include_all else "Tasks (all):"
        if goal_id:
            heading += f" goal={goal_id}"
        lines = [heading]
        if state.malformed_count:
            lines.append(f"  malformed_entries_skipped: {state.malformed_count}")
        if not records:
            lines.append("  (none)")
            return "\n".join(lines)
        for task in sorted(records, key=_task_sort_key):
            goal = f" goal={task.get('goal_id')}" if task.get("goal_id") else ""
            lines.append(
                "  - "
                f"{task.get('id', 'unknown')} "
                f"[{task.get('status', 'unknown')}] "
                f"priority={task.get('priority', 'normal')}{goal} "
                f"{_preview(str(task.get('title', '')))} "
                f"created_at={task.get('created_at', 'unknown')}"
            )
        return "\n".join(lines)

    def format_next(self) -> str:
        state = self._read_state()
        if state.error:
            return f"Task Queue error: {state.error}"
        task = _next_task(state.records)
        if not task:
            return "Next task:\n  none"
        return "Next task:\n" + _format_task_record(task, indent="  ")

    def format_inspect(self, task_id: str) -> str:
        task_id = task_id.strip()
        if not task_id:
            return "Usage: /tasks inspect <id>"
        state = self._read_state()
        if state.error:
            return f"Task Queue error: {state.error}"
        task = _find_task(state.records, task_id)
        if not task:
            return f"Task not found: {task_id}"
        return _format_task_record(task)

    def set_task_status(self, task_id: str, status: str, *, clear_blocked: bool = False) -> str:
        task_id = task_id.strip()
        if not task_id:
            return f"Usage: /tasks {_status_to_command(status)} <id>"
        if status not in VALID_TASK_STATUSES:
            return f"Invalid task status: {status}"
        state = self._read_state()
        if state.has_load_problem:
            return _mutation_refused(state)
        task = _find_task(state.records, task_id)
        if not task:
            return f"Task not found: {task_id}"
        task["status"] = status
        task["updated_at"] = _utc_now()
        if clear_blocked:
            task["blocked_reason"] = ""
        self._write_records(state.records)
        return f"{_status_label(status)} task:\n  {task_id} — {_preview(str(task.get('title', '')))}"

    def block_task(self, task_id: str, reason: str) -> str:
        task_id = task_id.strip()
        reason = reason.strip()
        if not task_id or not reason:
            return "Usage: /tasks block <id> <reason>"
        state = self._read_state()
        if state.has_load_problem:
            return _mutation_refused(state)
        task = _find_task(state.records, task_id)
        if not task:
            return f"Task not found: {task_id}"
        task["status"] = "blocked"
        task["blocked_reason"] = reason
        task["updated_at"] = _utc_now()
        self._write_records(state.records)
        return f"Blocked task:\n  {task_id} — {_preview(str(task.get('title', '')))}\n  reason: {_preview(reason)}"

    def unblock_task(self, task_id: str) -> str:
        task_id = task_id.strip()
        if not task_id:
            return "Usage: /tasks unblock <id>"
        state = self._read_state()
        if state.has_load_problem:
            return _mutation_refused(state)
        task = _find_task(state.records, task_id)
        if not task:
            return f"Task not found: {task_id}"
        task["status"] = "open"
        task["blocked_reason"] = ""
        task["updated_at"] = _utc_now()
        self._write_records(state.records)
        return f"Unblocked task:\n  {task_id} — {_preview(str(task.get('title', '')))}"

    def done_task(self, task_id: str, result: str = "") -> str:
        task_id = task_id.strip()
        if not task_id:
            return "Usage: /tasks done <id> [result text]"
        state = self._read_state()
        if state.has_load_problem:
            return _mutation_refused(state)
        task = _find_task(state.records, task_id)
        if not task:
            return f"Task not found: {task_id}"
        task["status"] = "done"
        task["updated_at"] = _utc_now()
        task["blocked_reason"] = ""
        if result.strip():
            task["result"] = result.strip()
        self._write_records(state.records)
        result_line = f"\n  result: {_preview(str(task.get('result', '')))}" if task.get("result") else ""
        return f"Done task:\n  {task_id} — {_preview(str(task.get('title', '')))}{result_line}"

    def _read_state(self) -> "_TaskReadState":
        if not self.tasks_path.exists():
            return _TaskReadState(records=[], malformed_count=0, error=None)
        try:
            lines = self.tasks_path.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            return _TaskReadState(records=[], malformed_count=0, error=str(exc))
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
                records.append(_normalize_task_record(parsed))
            else:
                malformed_count += 1
        return _TaskReadState(records=records, malformed_count=malformed_count, error=None)

    def _write_records(self, records: list[dict[str, Any]]) -> None:
        self.tasks_path.parent.mkdir(parents=True, exist_ok=True)
        payload = "".join(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n" for record in records)
        temp_path = self.tasks_path.with_name(f".{self.tasks_path.name}.{uuid4().hex}.tmp")
        temp_path.write_text(payload, encoding="utf-8")
        temp_path.replace(self.tasks_path)


class _TaskReadState:
    def __init__(self, *, records: list[dict[str, Any]], malformed_count: int, error: str | None) -> None:
        self.records = records
        self.malformed_count = malformed_count
        self.error = error

    @property
    def has_load_problem(self) -> bool:
        return bool(self.error or self.malformed_count)


def _parse_add_command(command: str) -> dict[str, str | None] | str:
    remainder = command.strip()[len("/tasks add") :].strip()
    if not remainder:
        return "Usage: /tasks add <title> [--priority high|normal|low] [--goal <goal_id>]"
    priority = "normal"
    goal_id: str | None = None
    parts = remainder.split()
    index = 0
    title_parts: list[str] = []
    while index < len(parts):
        token = parts[index].lower()
        if token == "--priority":
            if index + 1 >= len(parts):
                return "Invalid --priority value. Usage: /tasks add <title> [--priority high|normal|low] [--goal <goal_id>]"
            priority = parts[index + 1].lower()
            if priority not in VALID_TASK_PRIORITIES:
                return "Invalid --priority value. Usage: /tasks add <title> [--priority high|normal|low] [--goal <goal_id>]"
            index += 2
            continue
        if token == "--goal":
            if index + 1 >= len(parts):
                return "Invalid --goal value. Usage: /tasks add <title> [--priority high|normal|low] [--goal <goal_id>]"
            goal_id = parts[index + 1]
            index += 2
            continue
        title_parts.append(parts[index])
        index += 1
    title = " ".join(title_parts).strip()
    if not title:
        return "Usage: /tasks add <title> [--priority high|normal|low] [--goal <goal_id>]"
    return {"title": title, "priority": priority, "goal_id": goal_id}


def _parse_list_command(command: str) -> dict[str, Any] | str:
    parts = command.strip().split()
    include_all = False
    goal_id: str | None = None
    index = 2
    while index < len(parts):
        token = parts[index].lower()
        if token == "--all":
            include_all = True
            index += 1
            continue
        if token == "--goal":
            if index + 1 >= len(parts):
                return "Invalid --goal value. Usage: /tasks list [--all] [--goal <goal_id>]"
            goal_id = parts[index + 1]
            index += 2
            continue
        return "Usage: /tasks list [--all] [--goal <goal_id>]"
    return {"include_all": include_all, "goal_id": goal_id}


def _parse_block_command(command: str) -> dict[str, str] | str:
    remainder = command.strip()[len("/tasks block") :].strip()
    parts = remainder.split(maxsplit=1)
    if len(parts) != 2 or not parts[1].strip():
        return "Usage: /tasks block <id> <reason>"
    return {"task_id": parts[0], "reason": parts[1].strip()}


def _parse_done_command(command: str) -> dict[str, str] | str:
    remainder = command.strip()[len("/tasks done") :].strip()
    if not remainder:
        return "Usage: /tasks done <id> [result text]"
    parts = remainder.split(maxsplit=1)
    return {"task_id": parts[0], "result": parts[1].strip() if len(parts) > 1 else ""}


def _normalize_task_record(record: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(record)
    normalized.setdefault("description", "")
    normalized.setdefault("status", "open")
    normalized.setdefault("priority", "normal")
    normalized.setdefault("goal_id", None)
    normalized.setdefault("source", "operator")
    normalized.setdefault("tags", [])
    normalized.setdefault("result", "")
    normalized.setdefault("blocked_reason", "")
    return normalized


def _format_task_record(task: dict[str, Any], *, indent: str = "") -> str:
    lines = [
        "Task:",
        f"  id: {task.get('id', 'unknown')}",
        f"  title: {task.get('title', '')}",
        f"  description: {task.get('description', '')}",
        f"  status: {task.get('status', 'unknown')}",
        f"  priority: {task.get('priority', 'normal')}",
        f"  goal_id: {task.get('goal_id')}",
        f"  created_at: {task.get('created_at', 'unknown')}",
        f"  updated_at: {task.get('updated_at', 'unknown')}",
        f"  source: {task.get('source', 'unknown')}",
        f"  tags: {task.get('tags', [])}",
        f"  result: {task.get('result', '')}",
        f"  blocked_reason: {task.get('blocked_reason', '')}",
    ]
    if indent:
        return "\n".join(f"{indent}{line}" for line in lines)
    return "\n".join(lines)


def _find_task(records: list[dict[str, Any]], task_id: str) -> dict[str, Any] | None:
    for task in records:
        if task.get("id") == task_id:
            return task
    return None


def _next_task(records: list[dict[str, Any]]) -> dict[str, Any] | None:
    candidates = [task for task in records if task.get("status") in {"open", "in_progress"}]
    if not candidates:
        return None
    return sorted(candidates, key=_task_sort_key)[0]


def _task_sort_key(task: dict[str, Any]) -> tuple[int, int, str]:
    status_rank = 0 if task.get("status") == "in_progress" else 1 if task.get("status") == "open" else 2
    priority_rank = PRIORITY_RANK.get(str(task.get("priority") or "normal"), 1)
    return (status_rank, priority_rank, str(task.get("created_at", "")))


def _task_preview(task: dict[str, Any]) -> str:
    goal = f" goal={task.get('goal_id')}" if task.get("goal_id") else ""
    return f"{task.get('id', 'unknown')} [{task.get('status', 'unknown')}] priority={task.get('priority', 'normal')}{goal} — {_preview(str(task.get('title', '')))}"


def _goal_exists(project_root: Path, goal_id: str) -> bool:
    state = GoalStack.from_project_root(project_root)._read_state()
    return any(goal.get("id") == goal_id for goal in state.records)


def _mutation_refused(state: _TaskReadState) -> str:
    if state.error:
        return f"Task Queue error: {state.error}"
    return "Task Queue error: tasks file contains malformed JSONL; refusing to modify."


def _status_to_command(status: str) -> str:
    return {"in_progress": "start"}.get(status, status)


def _status_label(status: str) -> str:
    return {
        "open": "Reopened",
        "in_progress": "Started",
        "blocked": "Blocked",
        "done": "Done",
        "cancelled": "Cancelled",
    }.get(status, status.capitalize())


def _new_task_id(timestamp: str) -> str:
    compact = re.sub(r"[^0-9]", "", timestamp)[:14]
    return f"task_{compact}_{uuid4().hex[:4]}"


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _preview(text: str, limit: int = 120) -> str:
    normalized = " ".join(text.split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 3] + "..."
