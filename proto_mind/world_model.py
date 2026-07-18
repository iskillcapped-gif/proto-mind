from __future__ import annotations

import json
import re
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from proto_mind.experiment_journal import ExperimentJournal
from proto_mind.goal_stack import GoalStack
from proto_mind.task_queue import TaskQueue


VALID_WORLD_STATUSES = {"open", "observed", "scored", "archived"}
VISIBLE_WORLD_STATUSES = {"open", "observed"}


def format_world_command(command: str, *, project_root: Path) -> str | None:
    stripped = command.strip()
    normalized = " ".join(stripped.lower().split())
    if not normalized.startswith("/world"):
        return None

    model = WorldModelLite.from_project_root(project_root)
    if normalized == "/world status":
        return model.format_status()
    if normalized == "/world stats":
        return model.format_stats()
    if normalized.startswith("/world predict"):
        parsed_predict = _parse_predict_command(stripped)
        if isinstance(parsed_predict, str):
            return parsed_predict
        return model.add_prediction(
            parsed_predict["situation"],
            parsed_predict["prediction"],
            confidence=parsed_predict["confidence"],
            goal_id=parsed_predict["goal_id"],
            task_id=parsed_predict["task_id"],
            experiment_id=parsed_predict["experiment_id"],
        )
    if normalized.startswith("/world list"):
        parsed_list = _parse_list_command(stripped)
        if isinstance(parsed_list, str):
            return parsed_list
        return model.format_list(
            include_all=parsed_list["include_all"],
            status=parsed_list["status"],
            goal_id=parsed_list["goal_id"],
            task_id=parsed_list["task_id"],
            experiment_id=parsed_list["experiment_id"],
        )
    if normalized.startswith("/world inspect"):
        record_id = stripped[len("/world inspect") :].strip()
        return model.format_inspect(record_id)
    if normalized.startswith("/world expect"):
        parsed_expect = _parse_id_text_command(stripped, "/world expect", "Usage: /world expect <id> <expected_signal>")
        if isinstance(parsed_expect, str):
            return parsed_expect
        return model.set_field(parsed_expect["id"], "expected_signal", parsed_expect["text"], "Expected signal updated")
    if normalized.startswith("/world observe"):
        parsed_observe = _parse_id_text_command(stripped, "/world observe", "Usage: /world observe <id> <actual_outcome>")
        if isinstance(parsed_observe, str):
            return parsed_observe
        return model.observe(parsed_observe["id"], parsed_observe["text"])
    if normalized.startswith("/world score"):
        parsed_score = _parse_score_command(stripped)
        if isinstance(parsed_score, str):
            return parsed_score
        return model.score(parsed_score["id"], parsed_score["score"])
    if normalized.startswith("/world lesson"):
        parsed_lesson = _parse_id_text_command(stripped, "/world lesson", "Usage: /world lesson <id> <lesson text>")
        if isinstance(parsed_lesson, str):
            return parsed_lesson
        return model.set_field(parsed_lesson["id"], "lesson", parsed_lesson["text"], "Lesson updated")
    if normalized.startswith("/world archive"):
        record_id = stripped[len("/world archive") :].strip()
        return model.set_status(record_id, "archived")
    if normalized.startswith("/world reopen"):
        record_id = stripped[len("/world reopen") :].strip()
        return model.set_status(record_id, "open")
    return (
        "Usage:\n"
        "  /world status\n"
        "  /world predict <situation> -> <prediction> [--confidence 0.0-1.0] [--goal <goal_id>] [--task <task_id>] [--experiment <experiment_id>]\n"
        "  /world list [--all] [--status open|observed|scored|archived] [--goal <goal_id>] [--task <task_id>] [--experiment <experiment_id>]\n"
        "  /world inspect <id>\n"
        "  /world expect <id> <expected_signal>\n"
        "  /world observe <id> <actual_outcome>\n"
        "  /world score <id> <0-5>\n"
        "  /world lesson <id> <lesson text>\n"
        "  /world archive <id>\n"
        "  /world reopen <id>\n"
        "  /world stats"
    )


class WorldModelLite:
    def __init__(self, world_path: Path, *, project_root: Path) -> None:
        self.world_path = world_path
        self.project_root = project_root

    @classmethod
    def from_project_root(cls, project_root: Path) -> "WorldModelLite":
        return cls(project_root / "proto_mind" / "data" / "world_model.jsonl", project_root=project_root)

    def format_status(self) -> str:
        state = self._read_state()
        records = state.records
        status_counts = {status: sum(1 for record in records if record.get("status") == status) for status in sorted(VALID_WORLD_STATUSES)}
        scored = [record for record in records if isinstance(record.get("score"), int)]
        latest = _latest_record(records)
        health = "ok"
        if state.error:
            health = "error"
        elif state.malformed_count:
            health = "malformed_jsonl"
        elif not self.world_path.exists():
            health = "missing"
        lines = [
            "World Model Lite status:",
            f"  path: {self.world_path}",
            f"  exists: {self.world_path.exists()}",
            f"  total_records: {len(records)}",
            f"  open: {status_counts.get('open', 0)}",
            f"  observed: {status_counts.get('observed', 0)}",
            f"  scored: {status_counts.get('scored', 0)}",
            f"  archived: {status_counts.get('archived', 0)}",
            f"  average_score: {_average_score(scored)}",
            f"  malformed_entries: {state.malformed_count}",
            f"  file_health: {health}",
            f"  latest_prediction: {_record_preview(latest) if latest else 'none'}",
        ]
        if state.error:
            lines.append(f"  error: {state.error}")
        return "\n".join(lines)

    def add_prediction(
        self,
        situation: str,
        prediction: str,
        *,
        confidence: float = 0.5,
        goal_id: str | None = None,
        task_id: str | None = None,
        experiment_id: str | None = None,
    ) -> str:
        if goal_id and not _goal_exists(self.project_root, goal_id):
            return f"Goal not found: {goal_id}"
        if task_id and not _task_exists(self.project_root, task_id):
            return f"Task not found: {task_id}"
        if experiment_id and not _experiment_exists(self.project_root, experiment_id):
            return f"Experiment not found: {experiment_id}"
        state = self._read_state()
        if state.has_load_problem:
            return _mutation_refused(state)
        now = _utc_now()
        record = {
            "id": _new_world_id(now),
            "created_at": now,
            "updated_at": now,
            "situation": situation.strip(),
            "prediction": prediction.strip(),
            "expected_signal": "",
            "actual_outcome": "",
            "score": None,
            "status": "open",
            "lesson": "",
            "confidence": confidence,
            "source": "operator",
            "goal_id": goal_id,
            "task_id": task_id,
            "experiment_id": experiment_id,
            "tags": [],
        }
        self._write_records([*state.records, record])
        return f"Prediction recorded:\n  {record['id']} — {_preview(record['situation'])} -> {_preview(record['prediction'])}{_link_note(record)}"

    def format_list(
        self,
        *,
        include_all: bool = False,
        status: str | None = None,
        goal_id: str | None = None,
        task_id: str | None = None,
        experiment_id: str | None = None,
    ) -> str:
        state = self._read_state()
        if state.error:
            return f"World Model Lite error: {state.error}"
        records = state.records
        if status:
            records = [record for record in records if record.get("status") == status]
        elif not include_all:
            records = [record for record in records if record.get("status") in VISIBLE_WORLD_STATUSES]
        if goal_id:
            records = [record for record in records if record.get("goal_id") == goal_id]
        if task_id:
            records = [record for record in records if record.get("task_id") == task_id]
        if experiment_id:
            records = [record for record in records if record.get("experiment_id") == experiment_id]
        heading = "World predictions:" if not include_all else "World predictions (all):"
        if status:
            heading += f" status={status}"
        if goal_id:
            heading += f" goal={goal_id}"
        if task_id:
            heading += f" task={task_id}"
        if experiment_id:
            heading += f" experiment={experiment_id}"
        lines = [heading]
        if state.malformed_count:
            lines.append(f"  malformed_entries_skipped: {state.malformed_count}")
        if not records:
            lines.append("  (none)")
            return "\n".join(lines)
        for record in sorted(records, key=lambda item: str(item.get("created_at", "")), reverse=True):
            lines.append(
                "  - "
                f"{record.get('id', 'unknown')} "
                f"[{record.get('status', 'unknown')}] "
                f"score={record.get('score')} confidence={record.get('confidence', 0.5)}"
                f"{_link_note(record)} "
                f"{_preview(str(record.get('situation', '')))} -> {_preview(str(record.get('prediction', '')))}"
            )
        return "\n".join(lines)

    def format_inspect(self, record_id: str) -> str:
        record_id = record_id.strip()
        if not record_id:
            return "Usage: /world inspect <id>"
        state = self._read_state()
        if state.error:
            return f"World Model Lite error: {state.error}"
        record = _find_record(state.records, record_id)
        if not record:
            return f"World prediction not found: {record_id}"
        return _format_record(record)

    def set_field(self, record_id: str, field_name: str, text: str, label: str) -> str:
        if not record_id.strip() or not text.strip():
            return f"Usage: /world {'expect' if field_name == 'expected_signal' else field_name} <id> <text>"
        state = self._read_state()
        if state.has_load_problem:
            return _mutation_refused(state)
        record = _find_record(state.records, record_id.strip())
        if not record:
            return f"World prediction not found: {record_id.strip()}"
        record[field_name] = text.strip()
        record["updated_at"] = _utc_now()
        self._write_records(state.records)
        return f"{label}:\n  {record_id.strip()} — {_preview(text)}"

    def observe(self, record_id: str, outcome: str) -> str:
        if not record_id.strip() or not outcome.strip():
            return "Usage: /world observe <id> <actual_outcome>"
        state = self._read_state()
        if state.has_load_problem:
            return _mutation_refused(state)
        record = _find_record(state.records, record_id.strip())
        if not record:
            return f"World prediction not found: {record_id.strip()}"
        record["actual_outcome"] = outcome.strip()
        record["status"] = "observed"
        record["updated_at"] = _utc_now()
        self._write_records(state.records)
        return f"Outcome observed:\n  {record_id.strip()} — {_preview(outcome)}"

    def score(self, record_id: str, score: int) -> str:
        state = self._read_state()
        if state.has_load_problem:
            return _mutation_refused(state)
        record = _find_record(state.records, record_id.strip())
        if not record:
            return f"World prediction not found: {record_id.strip()}"
        if not str(record.get("actual_outcome") or "").strip():
            return "Cannot score without an observed outcome. Use /world observe <id> <actual_outcome> first."
        record["score"] = score
        record["status"] = "scored"
        record["updated_at"] = _utc_now()
        self._write_records(state.records)
        return f"Prediction scored:\n  {record_id.strip()} — score={score}"

    def set_status(self, record_id: str, status: str) -> str:
        record_id = record_id.strip()
        if not record_id:
            return f"Usage: /world {status if status != 'open' else 'reopen'} <id>"
        state = self._read_state()
        if state.has_load_problem:
            return _mutation_refused(state)
        record = _find_record(state.records, record_id)
        if not record:
            return f"World prediction not found: {record_id}"
        record["status"] = status
        record["updated_at"] = _utc_now()
        self._write_records(state.records)
        return f"{_status_label(status)} prediction:\n  {record_id} — {_preview(str(record.get('prediction', '')))}"

    def format_stats(self) -> str:
        state = self._read_state()
        if state.error:
            return f"World Model Lite error: {state.error}"
        scored = [record for record in state.records if isinstance(record.get("score"), int)]
        score_counts = Counter(int(record.get("score")) for record in scored)
        high_conf_wrong = [
            record for record in scored if float(record.get("confidence") or 0.0) >= 0.8 and int(record.get("score")) <= 2
        ]
        low_conf_right = [
            record for record in scored if float(record.get("confidence") or 0.0) <= 0.4 and int(record.get("score")) >= 4
        ]
        tag_counts = Counter(str(tag) for record in state.records for tag in record.get("tags") or [])
        lines = [
            "World Model Lite stats:",
            f"  scored_count: {len(scored)}",
            f"  average_score: {_average_score(scored)}",
            f"  score_counts: {_format_score_counts(score_counts)}",
            f"  high_confidence_wrong: {len(high_conf_wrong)}",
            f"  low_confidence_correct: {len(low_conf_right)}",
            f"  top_tags: {_format_counter(tag_counts)}",
        ]
        if high_conf_wrong:
            lines.append("High-confidence wrong predictions:")
            for record in high_conf_wrong[:5]:
                lines.append(f"  - {_record_preview(record)}")
        if low_conf_right:
            lines.append("Low-confidence correct predictions:")
            for record in low_conf_right[:5]:
                lines.append(f"  - {_record_preview(record)}")
        return "\n".join(lines)

    def _read_state(self) -> "_WorldReadState":
        if not self.world_path.exists():
            return _WorldReadState(records=[], malformed_count=0, error=None)
        try:
            lines = self.world_path.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            return _WorldReadState(records=[], malformed_count=0, error=str(exc))
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
                records.append(_normalize_record(parsed))
            else:
                malformed_count += 1
        return _WorldReadState(records=records, malformed_count=malformed_count, error=None)

    def _write_records(self, records: list[dict[str, Any]]) -> None:
        self.world_path.parent.mkdir(parents=True, exist_ok=True)
        payload = "".join(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n" for record in records)
        temp_path = self.world_path.with_name(f".{self.world_path.name}.{uuid4().hex}.tmp")
        temp_path.write_text(payload, encoding="utf-8")
        temp_path.replace(self.world_path)


class _WorldReadState:
    def __init__(self, *, records: list[dict[str, Any]], malformed_count: int, error: str | None) -> None:
        self.records = records
        self.malformed_count = malformed_count
        self.error = error

    @property
    def has_load_problem(self) -> bool:
        return bool(self.error or self.malformed_count)


def _parse_predict_command(command: str) -> dict[str, Any] | str:
    remainder = command.strip()[len("/world predict") :].strip()
    if "->" not in remainder:
        return "Usage: /world predict <situation> -> <prediction> [--confidence 0.0-1.0] [--goal <goal_id>] [--task <task_id>] [--experiment <experiment_id>]"
    before_arrow, after_arrow = remainder.split("->", 1)
    situation = before_arrow.strip()
    prediction_text, flags_or_error = _strip_predict_flags(after_arrow.strip())
    if isinstance(flags_or_error, str):
        return flags_or_error
    if not situation or not prediction_text:
        return "Usage: /world predict <situation> -> <prediction> [--confidence 0.0-1.0] [--goal <goal_id>] [--task <task_id>] [--experiment <experiment_id>]"
    return {
        "situation": situation,
        "prediction": prediction_text,
        "confidence": flags_or_error["confidence"],
        "goal_id": flags_or_error["goal_id"],
        "task_id": flags_or_error["task_id"],
        "experiment_id": flags_or_error["experiment_id"],
    }


def _strip_predict_flags(text: str) -> tuple[str, dict[str, Any] | str]:
    parts = text.split()
    confidence = 0.5
    goal_id: str | None = None
    task_id: str | None = None
    experiment_id: str | None = None
    prediction_parts: list[str] = []
    index = 0
    while index < len(parts):
        token = parts[index].lower()
        if token == "--confidence":
            if index + 1 >= len(parts):
                return "", "Invalid --confidence value. Usage: /world predict <situation> -> <prediction> [--confidence 0.0-1.0]"
            try:
                confidence = float(parts[index + 1])
            except ValueError:
                return "", "Invalid --confidence value. Usage: /world predict <situation> -> <prediction> [--confidence 0.0-1.0]"
            if confidence < 0.0 or confidence > 1.0:
                return "", "Invalid --confidence value. Must be between 0.0 and 1.0."
            index += 2
            continue
        if token == "--goal":
            if index + 1 >= len(parts):
                return "", "Invalid --goal value. Usage: /world predict <situation> -> <prediction> [--goal <goal_id>]"
            goal_id = parts[index + 1]
            index += 2
            continue
        if token == "--task":
            if index + 1 >= len(parts):
                return "", "Invalid --task value. Usage: /world predict <situation> -> <prediction> [--task <task_id>]"
            task_id = parts[index + 1]
            index += 2
            continue
        if token == "--experiment":
            if index + 1 >= len(parts):
                return "", "Invalid --experiment value. Usage: /world predict <situation> -> <prediction> [--experiment <experiment_id>]"
            experiment_id = parts[index + 1]
            index += 2
            continue
        prediction_parts.append(parts[index])
        index += 1
    return " ".join(prediction_parts).strip(), {
        "confidence": confidence,
        "goal_id": goal_id,
        "task_id": task_id,
        "experiment_id": experiment_id,
    }


def _parse_list_command(command: str) -> dict[str, Any] | str:
    parts = command.strip().split()
    include_all = False
    status: str | None = None
    goal_id: str | None = None
    task_id: str | None = None
    experiment_id: str | None = None
    index = 2
    while index < len(parts):
        token = parts[index].lower()
        if token == "--all":
            include_all = True
            index += 1
            continue
        if token == "--status":
            if index + 1 >= len(parts):
                return "Invalid --status value. Usage: /world list [--status open|observed|scored|archived]"
            status = parts[index + 1].lower()
            if status not in VALID_WORLD_STATUSES:
                return "Invalid --status value. Usage: /world list [--status open|observed|scored|archived]"
            index += 2
            continue
        if token == "--goal":
            if index + 1 >= len(parts):
                return "Invalid --goal value. Usage: /world list [--goal <goal_id>]"
            goal_id = parts[index + 1]
            index += 2
            continue
        if token == "--task":
            if index + 1 >= len(parts):
                return "Invalid --task value. Usage: /world list [--task <task_id>]"
            task_id = parts[index + 1]
            index += 2
            continue
        if token == "--experiment":
            if index + 1 >= len(parts):
                return "Invalid --experiment value. Usage: /world list [--experiment <experiment_id>]"
            experiment_id = parts[index + 1]
            index += 2
            continue
        return "Usage: /world list [--all] [--status open|observed|scored|archived] [--goal <goal_id>] [--task <task_id>] [--experiment <experiment_id>]"
    return {
        "include_all": include_all,
        "status": status,
        "goal_id": goal_id,
        "task_id": task_id,
        "experiment_id": experiment_id,
    }


def _parse_id_text_command(command: str, prefix: str, usage: str) -> dict[str, str] | str:
    remainder = command.strip()[len(prefix) :].strip()
    parts = remainder.split(maxsplit=1)
    if len(parts) != 2 or not parts[1].strip():
        return usage
    return {"id": parts[0], "text": parts[1].strip()}


def _parse_score_command(command: str) -> dict[str, Any] | str:
    parts = command.strip().split()
    if len(parts) != 4:
        return "Usage: /world score <id> <0-5>"
    try:
        score = int(parts[3])
    except ValueError:
        return "Invalid score. Usage: /world score <id> <0-5>"
    if score < 0 or score > 5:
        return "Invalid score. Score must be an integer from 0 to 5."
    return {"id": parts[2], "score": score}


def _normalize_record(record: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(record)
    normalized.setdefault("expected_signal", "")
    normalized.setdefault("actual_outcome", "")
    normalized.setdefault("score", None)
    normalized.setdefault("status", "open")
    normalized.setdefault("lesson", "")
    normalized.setdefault("confidence", 0.5)
    normalized.setdefault("source", "operator")
    normalized.setdefault("goal_id", None)
    normalized.setdefault("task_id", None)
    normalized.setdefault("experiment_id", None)
    normalized.setdefault("tags", [])
    return normalized


def _format_record(record: dict[str, Any]) -> str:
    return "\n".join(
        [
            "World prediction:",
            f"  id: {record.get('id', 'unknown')}",
            f"  situation: {record.get('situation', '')}",
            f"  prediction: {record.get('prediction', '')}",
            f"  expected_signal: {record.get('expected_signal', '')}",
            f"  actual_outcome: {record.get('actual_outcome', '')}",
            f"  score: {record.get('score')}",
            f"  status: {record.get('status', 'unknown')}",
            f"  lesson: {record.get('lesson', '')}",
            f"  confidence: {record.get('confidence', 0.5)}",
            f"  source: {record.get('source', 'unknown')}",
            f"  goal_id: {record.get('goal_id')}",
            f"  task_id: {record.get('task_id')}",
            f"  experiment_id: {record.get('experiment_id')}",
            f"  tags: {record.get('tags', [])}",
            f"  created_at: {record.get('created_at', 'unknown')}",
            f"  updated_at: {record.get('updated_at', 'unknown')}",
        ]
    )


def _find_record(records: list[dict[str, Any]], record_id: str) -> dict[str, Any] | None:
    for record in records:
        if record.get("id") == record_id:
            return record
    return None


def _latest_record(records: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not records:
        return None
    return sorted(records, key=lambda item: str(item.get("created_at", "")), reverse=True)[0]


def _record_preview(record: dict[str, Any]) -> str:
    return f"{record.get('id', 'unknown')} [{record.get('status', 'unknown')}] score={record.get('score')} — {_preview(str(record.get('prediction', '')))}"


def _goal_exists(project_root: Path, goal_id: str) -> bool:
    state = GoalStack.from_project_root(project_root)._read_state()
    return any(goal.get("id") == goal_id for goal in state.records)


def _task_exists(project_root: Path, task_id: str) -> bool:
    state = TaskQueue.from_project_root(project_root)._read_state()
    return any(task.get("id") == task_id for task in state.records)


def _experiment_exists(project_root: Path, experiment_id: str) -> bool:
    state = ExperimentJournal.from_project_root(project_root)._read_state()
    return any(experiment.get("id") == experiment_id for experiment in state.records)


def _mutation_refused(state: _WorldReadState) -> str:
    if state.error:
        return f"World Model Lite error: {state.error}"
    return "World Model Lite error: world_model file contains malformed JSONL; refusing to modify."


def _average_score(records: list[dict[str, Any]]) -> str:
    scores = [int(record["score"]) for record in records if isinstance(record.get("score"), int)]
    if not scores:
        return "none"
    return f"{sum(scores) / len(scores):.2f}"


def _format_score_counts(counter: Counter[int]) -> str:
    if not counter:
        return "none"
    return ", ".join(f"{score}={counter.get(score, 0)}" for score in range(0, 6) if counter.get(score, 0))


def _format_counter(counter: Counter[str]) -> str:
    if not counter:
        return "none"
    return ", ".join(f"{key}={value}" for key, value in counter.most_common(5))


def _status_label(status: str) -> str:
    return {
        "open": "Reopened",
        "observed": "Observed",
        "scored": "Scored",
        "archived": "Archived",
    }.get(status, status.capitalize())


def _link_note(record: dict[str, Any]) -> str:
    parts: list[str] = []
    if record.get("goal_id"):
        parts.append(f"goal={record.get('goal_id')}")
    if record.get("task_id"):
        parts.append(f"task={record.get('task_id')}")
    if record.get("experiment_id"):
        parts.append(f"experiment={record.get('experiment_id')}")
    return (" " + " ".join(parts)) if parts else ""


def _new_world_id(timestamp: str) -> str:
    compact = re.sub(r"[^0-9]", "", timestamp)[:14]
    return f"wm_{compact}_{uuid4().hex[:4]}"


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _preview(text: str, limit: int = 120) -> str:
    normalized = " ".join(text.split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 3] + "..."
