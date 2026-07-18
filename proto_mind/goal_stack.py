from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4


VALID_GOAL_STATUSES = {"active", "paused", "completed", "cancelled"}
VALID_GOAL_PRIORITIES = {"high", "normal", "low"}


def format_goal_command(command: str, *, project_root: Path) -> str | None:
    stripped = command.strip()
    normalized = " ".join(stripped.lower().split())
    if not normalized.startswith("/goals"):
        return None

    stack = GoalStack.from_project_root(project_root)
    if normalized == "/goals status":
        return stack.format_status()
    if normalized == "/goals list" or normalized == "/goals list --all":
        return stack.format_list(include_all="--all" in normalized.split())
    if normalized.startswith("/goals add"):
        parsed_add = _parse_add_command(stripped)
        if isinstance(parsed_add, str):
            return parsed_add
        return stack.add_goal(parsed_add["title"], priority=parsed_add["priority"])
    if normalized.startswith("/goals inspect"):
        goal_id = stripped[len("/goals inspect") :].strip()
        return stack.format_inspect(goal_id)
    if normalized.startswith("/goals focus"):
        goal_id = stripped[len("/goals focus") :].strip()
        return stack.focus_goal(goal_id)
    if normalized.startswith("/goals pause"):
        goal_id = stripped[len("/goals pause") :].strip()
        return stack.set_goal_status(goal_id, "paused", clear_focus=True)
    if normalized.startswith("/goals complete"):
        goal_id = stripped[len("/goals complete") :].strip()
        return stack.set_goal_status(goal_id, "completed", clear_focus=True)
    if normalized.startswith("/goals cancel"):
        goal_id = stripped[len("/goals cancel") :].strip()
        return stack.set_goal_status(goal_id, "cancelled", clear_focus=True)
    if normalized.startswith("/goals reopen"):
        goal_id = stripped[len("/goals reopen") :].strip()
        return stack.set_goal_status(goal_id, "active", clear_focus=False)
    return (
        "Usage:\n"
        "  /goals status\n"
        "  /goals add <title> [--priority high|normal|low]\n"
        "  /goals list [--all]\n"
        "  /goals inspect <id>\n"
        "  /goals focus <id>\n"
        "  /goals pause <id>\n"
        "  /goals complete <id>\n"
        "  /goals cancel <id>\n"
        "  /goals reopen <id>"
    )


class GoalStack:
    def __init__(self, goals_path: Path) -> None:
        self.goals_path = goals_path

    @classmethod
    def from_project_root(cls, project_root: Path) -> "GoalStack":
        return cls(project_root / "proto_mind" / "data" / "goals.jsonl")

    def format_status(self) -> str:
        state = self._read_state()
        records = state.records
        status_counts = {status: sum(1 for goal in records if goal.get("status") == status) for status in sorted(VALID_GOAL_STATUSES)}
        focused = _focused_goal(records)
        health = "ok"
        if state.error:
            health = "error"
        elif state.malformed_count:
            health = "malformed_jsonl"
        elif not self.goals_path.exists():
            health = "missing"
        lines = [
            "Goal Stack status:",
            f"  path: {self.goals_path}",
            f"  exists: {self.goals_path.exists()}",
            f"  total_goals: {len(records)}",
            f"  active: {status_counts.get('active', 0)}",
            f"  paused: {status_counts.get('paused', 0)}",
            f"  completed: {status_counts.get('completed', 0)}",
            f"  cancelled: {status_counts.get('cancelled', 0)}",
            f"  malformed_entries: {state.malformed_count}",
            f"  file_health: {health}",
            f"  focused_goal: {_goal_preview(focused) if focused else 'none'}",
        ]
        if state.error:
            lines.append(f"  error: {state.error}")
        return "\n".join(lines)

    def add_goal(self, title: str, *, priority: str = "normal") -> str:
        title = title.strip()
        if not title:
            return "Usage: /goals add <title> [--priority high|normal|low]"
        if priority not in VALID_GOAL_PRIORITIES:
            return "Invalid --priority value. Usage: /goals add <title> [--priority high|normal|low]"
        state = self._read_state()
        if state.has_load_problem:
            return _mutation_refused(state)
        now = _utc_now()
        goal = {
            "id": _new_goal_id(now),
            "created_at": now,
            "updated_at": now,
            "title": title,
            "description": "",
            "status": "active",
            "priority": priority,
            "tags": [],
            "source": "operator",
            "focus": False,
        }
        records = [*state.records, goal]
        self._write_records(records)
        return f"Goal added:\n  {goal['id']} — {_preview(title)}"

    def format_list(self, *, include_all: bool = False) -> str:
        state = self._read_state()
        if state.error:
            return f"Goal Stack error: {state.error}"
        records = state.records
        if not include_all:
            records = [goal for goal in records if goal.get("status") in {"active", "paused"} or goal.get("focus")]
        lines = ["Goals:" if not include_all else "Goals (all):"]
        if state.malformed_count:
            lines.append(f"  malformed_entries_skipped: {state.malformed_count}")
        if not records:
            lines.append("  (none)")
            return "\n".join(lines)
        for goal in sorted(records, key=lambda item: str(item.get("created_at", "")), reverse=True):
            focus = " focused" if goal.get("focus") else ""
            lines.append(
                "  - "
                f"{goal.get('id', 'unknown')} "
                f"[{goal.get('status', 'unknown')}{focus}] "
                f"priority={goal.get('priority', 'normal')} "
                f"{_preview(str(goal.get('title', '')))} "
                f"created_at={goal.get('created_at', 'unknown')}"
            )
        return "\n".join(lines)

    def format_inspect(self, goal_id: str) -> str:
        goal_id = goal_id.strip()
        if not goal_id:
            return "Usage: /goals inspect <id>"
        state = self._read_state()
        if state.error:
            return f"Goal Stack error: {state.error}"
        goal = _find_goal(state.records, goal_id)
        if not goal:
            return f"Goal not found: {goal_id}"
        return _format_goal_record(goal)

    def focus_goal(self, goal_id: str) -> str:
        goal_id = goal_id.strip()
        if not goal_id:
            return "Usage: /goals focus <id>"
        state = self._read_state()
        if state.has_load_problem:
            return _mutation_refused(state)
        goal = _find_goal(state.records, goal_id)
        if not goal:
            return f"Goal not found: {goal_id}"
        if goal.get("status") != "active":
            return f"Cannot focus goal unless it is active: {goal_id}"
        now = _utc_now()
        for candidate in state.records:
            candidate["focus"] = candidate.get("id") == goal_id
            if candidate.get("id") == goal_id:
                candidate["updated_at"] = now
        self._write_records(state.records)
        return f"Focused goal:\n  {goal_id} — {_preview(str(goal.get('title', '')))}"

    def set_goal_status(self, goal_id: str, status: str, *, clear_focus: bool) -> str:
        goal_id = goal_id.strip()
        if not goal_id:
            return f"Usage: /goals {status_to_command(status)} <id>"
        if status not in VALID_GOAL_STATUSES:
            return f"Invalid goal status: {status}"
        state = self._read_state()
        if state.has_load_problem:
            return _mutation_refused(state)
        goal = _find_goal(state.records, goal_id)
        if not goal:
            return f"Goal not found: {goal_id}"
        goal["status"] = status
        goal["updated_at"] = _utc_now()
        if clear_focus:
            goal["focus"] = False
        self._write_records(state.records)
        label = status.capitalize()
        return f"{label} goal:\n  {goal_id} — {_preview(str(goal.get('title', '')))}"

    def _read_state(self) -> "_GoalReadState":
        if not self.goals_path.exists():
            return _GoalReadState(records=[], malformed_count=0, error=None)
        try:
            lines = self.goals_path.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            return _GoalReadState(records=[], malformed_count=0, error=str(exc))
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
                records.append(_normalize_goal_record(parsed))
            else:
                malformed_count += 1
        return _GoalReadState(records=records, malformed_count=malformed_count, error=None)

    def _write_records(self, records: list[dict[str, Any]]) -> None:
        self.goals_path.parent.mkdir(parents=True, exist_ok=True)
        payload = "".join(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n" for record in records)
        temp_path = self.goals_path.with_name(f".{self.goals_path.name}.{uuid4().hex}.tmp")
        temp_path.write_text(payload, encoding="utf-8")
        temp_path.replace(self.goals_path)


class _GoalReadState:
    def __init__(self, *, records: list[dict[str, Any]], malformed_count: int, error: str | None) -> None:
        self.records = records
        self.malformed_count = malformed_count
        self.error = error

    @property
    def has_load_problem(self) -> bool:
        return bool(self.error or self.malformed_count)


def _parse_add_command(command: str) -> dict[str, str] | str:
    remainder = command.strip()[len("/goals add") :].strip()
    if not remainder:
        return "Usage: /goals add <title> [--priority high|normal|low]"
    priority = "normal"
    parts = remainder.split()
    if "--priority" in [part.lower() for part in parts]:
        lower_parts = [part.lower() for part in parts]
        index = lower_parts.index("--priority")
        if index + 1 >= len(parts):
            return "Invalid --priority value. Usage: /goals add <title> [--priority high|normal|low]"
        priority = parts[index + 1].lower()
        if priority not in VALID_GOAL_PRIORITIES:
            return "Invalid --priority value. Usage: /goals add <title> [--priority high|normal|low]"
        del parts[index : index + 2]
    title = " ".join(parts).strip()
    if not title:
        return "Usage: /goals add <title> [--priority high|normal|low]"
    return {"title": title, "priority": priority}


def _normalize_goal_record(record: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(record)
    normalized.setdefault("description", "")
    normalized.setdefault("status", "active")
    normalized.setdefault("priority", "normal")
    normalized.setdefault("tags", [])
    normalized.setdefault("source", "operator")
    normalized.setdefault("focus", False)
    return normalized


def _format_goal_record(goal: dict[str, Any]) -> str:
    return "\n".join(
        [
            "Goal:",
            f"  id: {goal.get('id', 'unknown')}",
            f"  title: {goal.get('title', '')}",
            f"  description: {goal.get('description', '')}",
            f"  status: {goal.get('status', 'unknown')}",
            f"  priority: {goal.get('priority', 'normal')}",
            f"  focus: {goal.get('focus', False)}",
            f"  created_at: {goal.get('created_at', 'unknown')}",
            f"  updated_at: {goal.get('updated_at', 'unknown')}",
            f"  source: {goal.get('source', 'unknown')}",
            f"  tags: {goal.get('tags', [])}",
        ]
    )


def _find_goal(records: list[dict[str, Any]], goal_id: str) -> dict[str, Any] | None:
    for goal in records:
        if goal.get("id") == goal_id:
            return goal
    return None


def _focused_goal(records: list[dict[str, Any]]) -> dict[str, Any] | None:
    for goal in records:
        if goal.get("focus"):
            return goal
    return None


def _goal_preview(goal: dict[str, Any]) -> str:
    return f"{goal.get('id', 'unknown')} — {_preview(str(goal.get('title', '')))}"


def _mutation_refused(state: _GoalReadState) -> str:
    if state.error:
        return f"Goal Stack error: {state.error}"
    return "Goal Stack error: goals file contains malformed JSONL; refusing to modify."


def status_to_command(status: str) -> str:
    return {"completed": "complete"}.get(status, status)


def _new_goal_id(timestamp: str) -> str:
    compact = re.sub(r"[^0-9]", "", timestamp)[:14]
    return f"goal_{compact}_{uuid4().hex[:4]}"


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _preview(text: str, limit: int = 120) -> str:
    normalized = " ".join(text.split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 3] + "..."
