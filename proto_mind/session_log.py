from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from proto_mind.models import InteractionResult


@dataclass(frozen=True)
class SessionLogStatus:
    enabled: bool
    log_path: Path
    exists: bool
    entry_count: int


@dataclass(frozen=True)
class SessionLogExportResult:
    export_path: Path
    entries_exported: int
    export_format: str
    order: str


class SessionOperatorLogger:
    def __init__(self, log_path: Path, *, enabled: bool = True) -> None:
        self.log_path = log_path
        self.enabled = enabled
        self._sequence = self._count_existing_entries()

    @classmethod
    def from_project_root(cls, project_root: Path, *, enabled: bool = True) -> "SessionOperatorLogger":
        return cls(project_root / "logs" / "session_operator_log.jsonl", enabled=enabled)

    def append_turn(self, result: InteractionResult, user_input: str) -> dict[str, Any] | None:
        if not self.enabled:
            return None
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self._sequence += 1
        entry = self._entry(result, user_input, self._sequence)
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")
        return entry

    def status(self) -> SessionLogStatus:
        return SessionLogStatus(
            enabled=self.enabled,
            log_path=self.log_path,
            exists=self.log_path.exists(),
            entry_count=self._count_existing_entries(),
        )

    def tail(self, count: int = 5) -> list[dict[str, Any]]:
        if not self.log_path.exists():
            return []
        lines = self.log_path.read_text(encoding="utf-8").splitlines()
        entries: list[dict[str, Any]] = []
        for line in lines[-max(count, 0):]:
            if line.strip():
                entries.append(json.loads(line))
        return entries

    def warning_entries(self, limit: int = 5) -> list[dict[str, Any]]:
        if not self.log_path.exists():
            return []
        matches: list[dict[str, Any]] = []
        lines = self.log_path.read_text(encoding="utf-8").splitlines()
        for line in reversed(lines):
            if not line.strip():
                continue
            entry = json.loads(line)
            if _entry_has_warning_signal(entry):
                matches.append(entry)
            if len(matches) >= max(limit, 0):
                break
        return list(reversed(matches))

    def search_entries(self, query: str, *, limit: int = 20) -> tuple[list[dict[str, Any]], int]:
        if not self.log_path.exists():
            return ([], 0)
        needle = query.casefold()
        found: list[dict[str, Any]] = []
        lines = self.log_path.read_text(encoding="utf-8").splitlines()
        for line_number, raw_line in enumerate(lines, start=1):
            if not raw_line.strip():
                continue
            result = _search_result_from_line(raw_line, line_number, query)
            searchable_text = result.get("_search_text", "")
            if needle not in str(searchable_text).casefold():
                continue
            result["_search_match_preview"] = _match_preview(str(searchable_text), query)
            found.append(result)
        total = len(found)
        return (list(reversed(found))[: max(limit, 0)], total)

    def export_entries(
        self,
        *,
        last: int = 20,
        export_format: str = "md",
        exports_dir: Path | None = None,
        timestamp: str | None = None,
    ) -> SessionLogExportResult:
        records = _export_records(self.log_path, last)
        destination = exports_dir or self.log_path.parent.parent / "exports"
        destination.mkdir(parents=True, exist_ok=True)
        stamp = timestamp or datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        export_path = destination / f"session_log_export_{stamp}.{export_format}"
        generated_at = datetime.now(UTC).isoformat()
        if export_format == "json":
            payload = {
                "generated_at": generated_at,
                "source": str(self.log_path),
                "entries_exported": len(records),
                "order": "chronological",
                "entries": [_json_export_record(record) for record in records],
            }
            export_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        else:
            export_path.write_text(
                _markdown_export(records, generated_at=generated_at, source=self.log_path),
                encoding="utf-8",
            )
        return SessionLogExportResult(
            export_path=export_path,
            entries_exported=len(records),
            export_format=export_format,
            order="chronological",
        )

    def review_records(self, *, last: int = 20) -> list[dict[str, Any]]:
        return _export_records(self.log_path, last)

    def _count_existing_entries(self) -> int:
        if not self.log_path.exists():
            return 0
        return sum(1 for line in self.log_path.read_text(encoding="utf-8").splitlines() if line.strip())

    @staticmethod
    def _entry(result: InteractionResult, user_input: str, turn_id: int) -> dict[str, Any]:
        retrieval_trace = result.retrieval_trace
        memory_summary = result.memory_summary
        self_reflection = result.self_reflection
        grounding_audit = result.grounding_audit
        return {
            "timestamp": datetime.now(UTC).isoformat(),
            "turn_id": turn_id,
            "user_input": user_input,
            "response_preview": _preview(result.response),
            "reasoner_backend": result.reasoner_backend,
            "observer": {
                "query_type": result.observer_state.query_type,
                "needs_memory": result.observer_state.needs_memory,
                "tags": list(result.observer_state.topic_tags),
            },
            "retrieved_memory_ids": [record.id for record in result.retrieved_memory],
            "retrieval_trace": (
                {
                    "query_mode": retrieval_trace.query_mode,
                    "current_state_oriented": retrieval_trace.current_state_oriented,
                    "historical_state_oriented": retrieval_trace.historical_state_oriented,
                    "candidate_count": len(retrieval_trace.candidates),
                    "selected_count": sum(1 for candidate in retrieval_trace.candidates if candidate.selected),
                }
                if retrieval_trace
                else None
            ),
            "memory_summary": {
                "memory_type": memory_summary.memory_type,
                "should_store": memory_summary.should_store,
                "stored_record_type": memory_summary.stored_record_type,
                "should_promote_new": memory_summary.should_promote_new,
                "should_promote_existing": memory_summary.should_promote_existing,
                "override_detected": memory_summary.override_detected,
                "superseded_record_ids": list(memory_summary.superseded_record_ids),
            },
            "self_reflection": (
                {
                    "memory_alignment": self_reflection.memory_alignment,
                    "preference_alignment": self_reflection.preference_alignment,
                    "active_decision_alignment": self_reflection.active_decision_alignment,
                    "warnings": list(self_reflection.warnings),
                    "correction_hints": list(self_reflection.correction_hints),
                }
                if self_reflection
                else None
            ),
            "grounding_audit": (
                {
                    "grounding_status": grounding_audit.grounding_status,
                    "memory_support": grounding_audit.memory_support,
                    "active_decision_status": grounding_audit.active_decision_status,
                    "superseded_memory_status": grounding_audit.superseded_memory_status,
                    "warnings": list(grounding_audit.warnings),
                }
                if grounding_audit
                else None
            ),
            "previous_correction_hints": list(result.previous_correction_hints),
        }


def format_session_log_command(command: str, logger: SessionOperatorLogger) -> str | None:
    normalized = " ".join(command.strip().lower().split())
    if normalized.startswith("/session self-check"):
        parsed_self_check = _parse_self_check_command(command)
        if isinstance(parsed_self_check, str):
            return parsed_self_check
        return _format_session_self_check(logger, window=parsed_self_check["last"])
    if normalized.startswith("/session doctor"):
        parsed_doctor = _parse_doctor_command(command)
        if isinstance(parsed_doctor, str):
            return parsed_doctor
        return _format_session_doctor(logger, window=parsed_doctor["last"])
    if normalized.startswith("/session health"):
        parsed_health = _parse_health_command(command)
        if isinstance(parsed_health, str):
            return parsed_health
        return _format_session_health(logger, window=parsed_health["last"])
    if normalized.startswith("/session review"):
        parsed_review = _parse_review_command(command)
        if isinstance(parsed_review, str):
            return parsed_review
        if not logger.log_path.exists():
            return f"Session operator log not found.\nPath: {logger.log_path}"
        if _non_empty_line_count(logger.log_path) == 0:
            return f"Session operator log is empty.\nPath: {logger.log_path}"
        return _format_session_review(
            logger.review_records(last=parsed_review["last"]),
            source=logger.log_path,
            window=parsed_review["last"],
        )
    if normalized == "/session log status":
        status = logger.status()
        return (
            "Session operator log:\n"
            f"  enabled: {status.enabled}\n"
            f"  path: {status.log_path}\n"
            f"  exists: {status.exists}\n"
            f"  entries: {status.entry_count}"
        )
    if normalized == "/session log path":
        return f"Session operator log path:\n  {logger.log_path}"
    if normalized.startswith("/session log tail"):
        count = _tail_count(normalized)
        entries = logger.tail(count)
        if not entries:
            return f"Session operator log tail:\n  No entries found at {logger.log_path}"
        lines = [f"Session operator log tail ({len(entries)} entries):"]
        for entry in entries:
            observer = entry.get("observer", {})
            audit = entry.get("grounding_audit") or {}
            reflection = entry.get("self_reflection") or {}
            lines.append(
                "  "
                f"#{entry.get('turn_id')} "
                f"query={observer.get('query_type')} "
                f"grounding={audit.get('grounding_status')} "
                f"reflection={reflection.get('memory_alignment')} "
                f"input={_preview(str(entry.get('user_input', '')), limit=72)}"
            )
        return "\n".join(lines)
    if normalized.startswith("/session log inspect"):
        count = _inspect_count(normalized)
        entries = logger.tail(count)
        if not entries:
            return f"Session log inspect:\n  No entries found at {logger.log_path}"
        lines = [f"Session log inspect ({len(entries)} entr{'y' if len(entries) == 1 else 'ies'}):"]
        for index, entry in enumerate(entries):
            if index:
                lines.append("")
            lines.extend(_format_inspect_entry(entry))
        return "\n".join(lines)
    if normalized.startswith("/session log warnings"):
        count = _warnings_count(normalized)
        entries = logger.warning_entries(count)
        if not entries:
            return "Session log warnings:\nNo warning entries found."
        lines = ["Session log warnings:", f"Found {len(entries)} warning entr{'y' if len(entries) == 1 else 'ies'}."]
        for entry in entries:
            lines.append("")
            lines.extend(_format_warning_entry(entry))
        return "\n".join(lines)
    if normalized.startswith("/session log search"):
        search = _parse_search_command(command)
        if search is None:
            return "Usage:\n  /session log search <text>"
        if not logger.log_path.exists():
            return f"Session operator log not found.\nPath: {logger.log_path}"
        matches, total = logger.search_entries(search["query"], limit=search["limit"])
        return _format_search_results(search["query"], matches, total)
    if normalized.startswith("/session log export"):
        parsed_export = _parse_export_command(command)
        if isinstance(parsed_export, str):
            return parsed_export
        if not logger.log_path.exists():
            return f"Session operator log not found.\nPath: {logger.log_path}"
        if _non_empty_line_count(logger.log_path) == 0:
            return f"Session operator log is empty.\nPath: {logger.log_path}"
        result = logger.export_entries(last=parsed_export["last"], export_format=parsed_export["format"])
        return (
            "Session log export created.\n"
            f"Path: {result.export_path}\n"
            f"Entries exported: {result.entries_exported}\n"
            f"Format: {result.export_format}\n"
            f"Order: {result.order}"
        )
    return None


def _tail_count(command: str) -> int:
    parts = command.split()
    if len(parts) >= 4:
        try:
            return max(1, min(int(parts[3]), 50))
        except ValueError:
            return 5
    return 5


def _inspect_count(command: str) -> int:
    parts = command.split()
    if len(parts) >= 4:
        try:
            return max(1, min(int(parts[3]), 20))
        except ValueError:
            return 1
    return 1


def _warnings_count(command: str) -> int:
    parts = command.split()
    if len(parts) >= 4:
        try:
            return max(1, min(int(parts[3]), 50))
        except ValueError:
            return 5
    return 5


def _parse_search_command(command: str) -> dict[str, Any] | None:
    stripped = command.strip()
    prefix = "/session log search"
    if not stripped.casefold().startswith(prefix):
        return None
    remainder = stripped[len(prefix):].strip()
    if not remainder:
        return None

    limit = 20
    parts = remainder.split()
    if "--limit" in parts:
        index = parts.index("--limit")
        if index + 1 < len(parts):
            try:
                limit = max(1, min(int(parts[index + 1]), 200))
                del parts[index : index + 2]
            except ValueError:
                pass
        else:
            del parts[index]

    query = " ".join(parts).strip()
    if not query:
        return None
    return {"query": query, "limit": limit}


def _parse_export_command(command: str) -> dict[str, Any] | str:
    parts = command.strip().split()
    last = 20
    export_format = "md"
    index = 3
    while index < len(parts):
        token = parts[index]
        if token == "--last":
            if index + 1 >= len(parts):
                return "Invalid --last value. Usage: /session log export [--last N]"
            try:
                last = int(parts[index + 1])
            except ValueError:
                return "Invalid --last value. Usage: /session log export [--last N]"
            if last <= 0:
                return "--last must be greater than 0."
            last = min(last, 1000)
            index += 2
            continue
        if token == "--format":
            if index + 1 >= len(parts):
                return "Invalid --format value. Usage: /session log export [--format md|json]"
            export_format = parts[index + 1].lower()
            if export_format not in {"md", "json"}:
                return "Invalid --format value. Usage: /session log export [--format md|json]"
            index += 2
            continue
        return "Usage: /session log export [--last N] [--format md|json]"
    return {"last": last, "format": export_format}


def _parse_review_command(command: str) -> dict[str, int] | str:
    parts = command.strip().split()
    last = 20
    index = 2
    while index < len(parts):
        token = parts[index]
        if token == "--last":
            if index + 1 >= len(parts):
                return "Invalid --last value. Usage: /session review [--last N]"
            try:
                last = int(parts[index + 1])
            except ValueError:
                return "Invalid --last value. Usage: /session review [--last N]"
            if last <= 0:
                return "--last must be greater than 0."
            last = min(last, 1000)
            index += 2
            continue
        return "Usage: /session review [--last N]"
    return {"last": last}


def _parse_health_command(command: str) -> dict[str, int] | str:
    parts = command.strip().split()
    last = 20
    index = 2
    while index < len(parts):
        token = parts[index]
        if token == "--last":
            if index + 1 >= len(parts):
                return "Invalid --last value. Usage: /session health [--last N]"
            try:
                last = int(parts[index + 1])
            except ValueError:
                return "Invalid --last value. Usage: /session health [--last N]"
            if last <= 0:
                return "--last must be greater than 0."
            last = min(last, 1000)
            index += 2
            continue
        return "Usage: /session health [--last N]"
    return {"last": last}


def _parse_doctor_command(command: str) -> dict[str, int] | str:
    parts = command.strip().split()
    last = 20
    index = 2
    while index < len(parts):
        token = parts[index]
        if token == "--last":
            if index + 1 >= len(parts):
                return "Invalid --last value. Usage: /session doctor [--last N]"
            try:
                last = int(parts[index + 1])
            except ValueError:
                return "Invalid --last value. Usage: /session doctor [--last N]"
            if last <= 0:
                return "--last must be greater than 0."
            last = min(last, 1000)
            index += 2
            continue
        return "Usage: /session doctor [--last N]"
    return {"last": last}


def _parse_self_check_command(command: str) -> dict[str, int] | str:
    parts = command.strip().split()
    last = 20
    index = 2
    while index < len(parts):
        token = parts[index]
        if token == "--last":
            if index + 1 >= len(parts):
                return "Invalid --last value. Usage: /session self-check [--last N]"
            try:
                last = int(parts[index + 1])
            except ValueError:
                return "Invalid --last value. Usage: /session self-check [--last N]"
            if last <= 0:
                return "--last must be greater than 0."
            last = min(last, 1000)
            index += 2
            continue
        return "Usage: /session self-check [--last N]"
    return {"last": last}


def _non_empty_line_count(path: Path) -> int:
    return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())


def _export_records(log_path: Path, last: int) -> list[dict[str, Any]]:
    lines = [
        (line_number, raw_line)
        for line_number, raw_line in enumerate(log_path.read_text(encoding="utf-8").splitlines(), start=1)
        if raw_line.strip()
    ]
    selected = lines[-last:]
    return [_export_record_from_line(raw_line, line_number) for line_number, raw_line in selected]


def _export_record_from_line(raw_line: str, line_number: int) -> dict[str, Any]:
    try:
        entry = json.loads(raw_line)
        if not isinstance(entry, dict):
            entry = {"raw_value": entry}
        malformed = False
    except json.JSONDecodeError:
        entry = {"raw_line": raw_line}
        malformed = True
    return {
        "line_number": line_number,
        "malformed_json": malformed,
        "entry": entry,
    }


def _json_export_record(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "line": record["line_number"],
        "malformed_json": record["malformed_json"],
        "entry": record["entry"],
    }


def _markdown_export(records: list[dict[str, Any]], *, generated_at: str, source: Path) -> str:
    lines = [
        "# Proto-Mind Session Log Export",
        "",
        f"Generated: {generated_at}",
        f"Source: {source}",
        f"Entries exported: {len(records)}",
        "Order: chronological",
        "",
        "---",
    ]
    for index, record in enumerate(records, start=1):
        entry = record["entry"]
        observer = entry.get("observer") or {}
        reflection = entry.get("self_reflection") or {}
        audit = entry.get("grounding_audit") or {}
        lines.extend(
            [
                "",
                f"## Entry {index}",
                "",
                f"- timestamp: {entry.get('timestamp', 'unknown')}",
                f"- turn_id: {entry.get('turn_id', 'unknown')}",
                f"- type: {observer.get('query_type', 'unknown')}",
                f"- grounding: {audit.get('grounding_status', 'unknown')}",
                f"- reflection: {reflection.get('memory_alignment', 'unknown')}",
                f"- line: {record['line_number']}",
                f"- malformed_json: {str(record['malformed_json']).lower()}",
                "",
                "### Input",
                "",
                _markdown_text(str(entry.get("user_input", ""))),
                "",
                "### Response preview",
                "",
                _markdown_text(str(entry.get("response_preview", ""))),
                "",
                "### Retrieved IDs",
                "",
            ]
        )
        lines.extend(_markdown_bullets(entry.get("retrieved_memory_ids")))
        lines.extend(["", "### Reflection warnings", ""])
        lines.extend(_markdown_bullets(reflection.get("warnings")))
        lines.extend(["", "### Correction hints", ""])
        lines.extend(_markdown_bullets(reflection.get("correction_hints")))
        lines.extend(
            [
                "",
                "### Grounding",
                "",
                f"- memory_support: {audit.get('memory_support', 'unknown')}",
                f"- active_decision_status: {audit.get('active_decision_status', 'unknown')}",
                f"- superseded_memory_status: {audit.get('superseded_memory_status', 'unknown')}",
                "",
                "### Grounding warnings",
                "",
            ]
        )
        lines.extend(_markdown_bullets(audit.get("warnings")))
        if record["malformed_json"]:
            lines.extend(["", "### Raw malformed line", "", _markdown_text(str(entry.get("raw_line", "")))])
        lines.extend(["", "---"])
    return "\n".join(lines) + "\n"


def _markdown_bullets(values: object) -> list[str]:
    if not isinstance(values, list) or not values:
        return ["- none"]
    return [f"- {_markdown_text(str(value))}" for value in values]


def _markdown_text(text: str) -> str:
    return text.replace("\r\n", "\n").strip() or "none"


def _format_session_review(records: list[dict[str, Any]], *, source: Path, window: int) -> str:
    type_counts: dict[str, int] = {}
    grounding_counts: dict[str, int] = {}
    reflection_counts: dict[str, int] = {}
    reasoner_counts: dict[str, int] = {}
    tag_counts: dict[str, int] = {}
    retrieved_entries = 0
    total_retrieved_ids = 0
    unique_retrieved_ids: set[str] = set()
    malformed_count = 0
    recent_inputs: list[str] = []
    issues: list[str] = []

    for record in records:
        entry = record["entry"]
        if record["malformed_json"]:
            malformed_count += 1
            issues.append(f"line {record['line_number']}: malformed JSONL entry")
            continue

        observer = entry.get("observer") or {}
        reflection = entry.get("self_reflection") or {}
        audit = entry.get("grounding_audit") or {}
        query_type = str(observer.get("query_type") or "unknown")
        grounding_status = str(audit.get("grounding_status") or "unknown")
        memory_alignment = str(reflection.get("memory_alignment") or "unknown")
        reasoner = str(entry.get("reasoner_backend") or "unknown")
        reflection_status = "warnings" if reflection.get("warnings") else memory_alignment

        _increment(type_counts, query_type)
        _increment(grounding_counts, grounding_status)
        _increment(reflection_counts, reflection_status)
        if reflection.get("correction_hints"):
            _increment(reflection_counts, "hints")
        _increment(reasoner_counts, reasoner)

        for tag in observer.get("tags") or []:
            _increment(tag_counts, str(tag))

        retrieved_ids = entry.get("retrieved_memory_ids") or []
        if isinstance(retrieved_ids, list) and retrieved_ids:
            retrieved_entries += 1
            total_retrieved_ids += len(retrieved_ids)
            unique_retrieved_ids.update(str(record_id) for record_id in retrieved_ids)

        user_input = str(entry.get("user_input") or "").strip()
        if user_input:
            recent_inputs.append(user_input)

        for warning in reflection.get("warnings") or []:
            issues.append(f"turn {entry.get('turn_id', 'unknown')}: reflection warning: {warning}")
        for hint in reflection.get("correction_hints") or []:
            issues.append(f"turn {entry.get('turn_id', 'unknown')}: correction hint: {hint}")
        for warning in audit.get("warnings") or []:
            issues.append(f"turn {entry.get('turn_id', 'unknown')}: grounding warning: {warning}")
        if grounding_status not in {"grounded", "not_needed", "unknown"}:
            issues.append(f"turn {entry.get('turn_id', 'unknown')}: grounding_status={grounding_status}")
        if audit.get("active_decision_status") == "contradicted":
            issues.append(f"turn {entry.get('turn_id', 'unknown')}: active_decision_status=contradicted")
        if audit.get("superseded_memory_status") == "treated_as_current":
            issues.append(f"turn {entry.get('turn_id', 'unknown')}: superseded_memory_status=treated_as_current")

    lines = [
        "Session Review",
        f"Source: {source}",
        f"Entries reviewed: {len(records)}",
        f"Window: last {window}",
        "Order analyzed: chronological",
        "",
        "Types:",
    ]
    lines.extend(_format_count_lines(type_counts))
    lines.extend(["", "Grounding:"])
    lines.extend(_format_count_lines(grounding_counts, defaults=("grounded", "not_needed", "unknown")))
    lines.extend(["", "Reflection:"])
    lines.extend(_format_count_lines(reflection_counts, defaults=("ok", "warnings", "hints", "unknown")))
    lines.extend(["", f"Malformed entries: {malformed_count}", "", "Retrieval:"])
    lines.extend(
        [
            f"- entries with retrieved ids: {retrieved_entries}",
            f"- total retrieved ids referenced: {total_retrieved_ids}",
            f"- unique retrieved ids: {len(unique_retrieved_ids)}",
            "",
            "Reasoners:",
        ]
    )
    lines.extend(_format_count_lines(reasoner_counts, defaults=("mock", "ollama", "unknown")))
    lines.extend(["", "Top observer tags:"])
    lines.extend(_format_count_lines(dict(sorted(tag_counts.items(), key=lambda item: (-item[1], item[0]))[:8])))
    lines.extend(["", "Recent inputs:"])
    for index, user_input in enumerate(recent_inputs[-5:], start=1):
        lines.append(f"{index}. {_preview(user_input, limit=100)}")
    if not recent_inputs:
        lines.append("- none")
    lines.extend(["", "Warnings / issues:"])
    if issues:
        for issue in issues[-10:]:
            lines.append(f"- {_preview(issue, limit=180)}")
    else:
        lines.append("- none")
    return "\n".join(lines)


def _format_session_health(logger: SessionOperatorLogger, *, window: int = 20) -> str:
    log_path = logger.log_path
    project_root = log_path.parent.parent
    exports_path = project_root / "exports"
    backups_path = project_root / "backups"
    notes: list[str] = []
    status = "OK"
    total_entries = 0
    recent_records: list[dict[str, Any]] = []
    read_error: str | None = None
    log_exists = log_path.exists()
    log_readable = False
    entries_readable = False

    if not log_exists:
        status = "WARN"
        notes.append("Session operator log not found.")
        notes.append("Run normal cognitive turns first, or check logging config.")
    else:
        try:
            total_entries = _non_empty_line_count(log_path)
            log_readable = True
            if total_entries == 0:
                status = "WARN"
                notes.append("Session operator log is empty.")
            else:
                recent_records = _export_records(log_path, window)
                entries_readable = True
        except OSError as exc:
            status = "ERROR"
            read_error = str(exc)
            notes.append(f"Unable to read session operator log: {read_error}")

    malformed_entries = sum(1 for record in recent_records if record["malformed_json"])
    reflection_warnings = 0
    correction_hints = 0
    grounding_issues = 0
    for record in recent_records:
        if record["malformed_json"]:
            continue
        entry = record["entry"]
        reflection = entry.get("self_reflection") or {}
        audit = entry.get("grounding_audit") or {}
        reflection_warnings += len(reflection.get("warnings") or [])
        correction_hints += len(reflection.get("correction_hints") or [])
        grounding_issues += _grounding_issue_count(audit)

    if status != "ERROR" and (
        malformed_entries
        or reflection_warnings
        or correction_hints
        or grounding_issues
        or not exports_path.exists()
        or not backups_path.exists()
    ):
        status = "WARN"
    if malformed_entries:
        notes.append("Malformed JSONL entries found in recent window.")
    if not exports_path.exists():
        notes.append("Export directory is missing.")
    if not backups_path.exists():
        notes.append("Backup directory is missing.")

    lines = [
        "Session Health",
        f"Status: {status}",
        "",
        "Checks:",
        f"- session log enabled: {_check(logger.enabled)}",
        f"- session log path configured: {_check(bool(log_path))}",
        f"- session log exists: {_check(log_exists)}",
        f"- session log readable: {_check(log_readable) if log_exists else 'WARN'}",
        f"- entries readable: {_check(entries_readable) if total_entries else 'WARN'}",
        f"- malformed entries: {malformed_entries}",
        f"- recent reflection warnings: {reflection_warnings}",
        f"- recent correction hints: {correction_hints}",
        f"- recent grounding issues: {grounding_issues}",
        f"- export directory exists: {_check(exports_path.exists())}",
        f"- backup directory exists: {_check(backups_path.exists())}",
        "",
        "Source:",
        f"- log: {log_path}",
        f"- exports: {exports_path}",
        f"- backups: {backups_path}",
        "",
        "Window:",
        f"- recent entries checked: {len(recent_records)}",
        f"- configured window: {window}",
        f"- total log entries: {total_entries}",
        "",
        "Notes:",
    ]
    if notes:
        lines.extend(f"- {note}" for note in notes)
    else:
        lines.append("- Use /session review for detailed summary.")
        lines.append("- Use /session log warnings for warning details.")
    return "\n".join(lines)


def _format_session_doctor(logger: SessionOperatorLogger, *, window: int = 20) -> str:
    log_path = logger.log_path
    if not log_path.exists():
        return _format_doctor_report(
            status="WARN",
            source=log_path,
            entries_analyzed=0,
            window=window,
            findings=[
                _finding(
                    "Session operator log not found",
                    "WARN",
                    [],
                    ["Run normal cognitive turns first, or check logging config."],
                )
            ],
        )

    try:
        total_entries = _non_empty_line_count(log_path)
        if total_entries == 0:
            return _format_doctor_report(
                status="WARN",
                source=log_path,
                entries_analyzed=0,
                window=window,
                findings=[
                    _finding(
                        "Session operator log is empty",
                        "WARN",
                        [],
                        ["Run normal cognitive turns first, then re-run /session doctor."],
                    )
                ],
            )
        records = _export_records(log_path, window)
    except OSError as exc:
        return _format_doctor_report(
            status="ERROR",
            source=log_path,
            entries_analyzed=0,
            window=window,
            findings=[
                _finding(
                    "Session operator log cannot be read",
                    "ERROR",
                    [f"error: {exc}"],
                    ["Check file permissions and logging configuration."],
                )
            ],
        )

    findings = _doctor_findings(records)
    status = _doctor_status(findings)
    return _format_doctor_report(
        status=status,
        source=log_path,
        entries_analyzed=len(records),
        window=window,
        findings=findings,
    )


def _format_session_self_check(logger: SessionOperatorLogger, *, window: int = 20) -> str:
    log_path = logger.log_path
    project_root = log_path.parent.parent
    exports_path = project_root / "exports"
    backups_path = project_root / "backups"

    if not log_path.exists():
        return _format_self_check_report(
            overall="WARN",
            source=log_path,
            entries_checked=0,
            window=window,
            health=[
                ("log exists", "WARN"),
                ("log readable", "WARN"),
                ("malformed entries", "0"),
                ("reflection warnings", "0"),
                ("correction hints", "0"),
                ("grounding issues", "0"),
                ("export directory", _check(exports_path.exists())),
                ("backup directory", _check(backups_path.exists())),
            ],
            doctor=["Session operator log not found: WARN"],
            recommendations=["/session log status"],
        )

    try:
        total_entries = _non_empty_line_count(log_path)
        if total_entries == 0:
            return _format_self_check_report(
                overall="WARN",
                source=log_path,
                entries_checked=0,
                window=window,
                health=[
                    ("log exists", "OK"),
                    ("log readable", "OK"),
                    ("malformed entries", "0"),
                    ("reflection warnings", "0"),
                    ("correction hints", "0"),
                    ("grounding issues", "0"),
                    ("export directory", _check(exports_path.exists())),
                    ("backup directory", _check(backups_path.exists())),
                ],
                doctor=["Session operator log is empty: WARN"],
                recommendations=_self_check_recommendations("WARN", window),
            )
        records = _export_records(log_path, window)
    except OSError as exc:
        return _format_self_check_report(
            overall="ERROR",
            source=log_path,
            entries_checked=0,
            window=window,
            health=[
                ("log exists", "OK"),
                ("log readable", "ERROR"),
                ("malformed entries", "unknown"),
                ("reflection warnings", "unknown"),
                ("correction hints", "unknown"),
                ("grounding issues", "unknown"),
                ("export directory", _check(exports_path.exists())),
                ("backup directory", _check(backups_path.exists())),
            ],
            doctor=[f"Session operator log cannot be read: ERROR ({exc})"],
            recommendations=_self_check_recommendations("ERROR", window),
        )

    summary = _self_check_counts(records)
    health_status = "OK"
    if (
        summary["malformed_entries"]
        or summary["reflection_warnings"]
        or summary["correction_hints"]
        or summary["grounding_issues"]
        or not exports_path.exists()
        or not backups_path.exists()
    ):
        health_status = "WARN"
    findings = _doctor_findings(records)
    doctor_status = _doctor_status(findings)
    overall = "WARN" if health_status == "WARN" or doctor_status == "WARN" else "OK"
    doctor_lines = _self_check_doctor_lines(findings)
    return _format_self_check_report(
        overall=overall,
        source=log_path,
        entries_checked=len(records),
        window=window,
        health=[
            ("log exists", "OK"),
            ("log readable", "OK"),
            ("malformed entries", str(summary["malformed_entries"])),
            ("reflection warnings", str(summary["reflection_warnings"])),
            ("correction hints", str(summary["correction_hints"])),
            ("grounding issues", str(summary["grounding_issues"])),
            ("export directory", _check(exports_path.exists())),
            ("backup directory", _check(backups_path.exists())),
        ],
        doctor=doctor_lines,
        recommendations=_self_check_recommendations(overall, window),
    )


def _self_check_counts(records: list[dict[str, Any]]) -> dict[str, int]:
    counts = {
        "malformed_entries": 0,
        "reflection_warnings": 0,
        "correction_hints": 0,
        "grounding_issues": 0,
    }
    for record in records:
        if record["malformed_json"]:
            counts["malformed_entries"] += 1
            continue
        entry = record["entry"]
        reflection = entry.get("self_reflection") or {}
        audit = entry.get("grounding_audit") or {}
        counts["reflection_warnings"] += len(reflection.get("warnings") or [])
        counts["correction_hints"] += len(reflection.get("correction_hints") or [])
        counts["grounding_issues"] += _grounding_issue_count(audit)
    return counts


def _self_check_doctor_lines(findings: list[dict[str, Any]]) -> list[str]:
    lines: list[str] = []
    for finding in findings:
        title = finding["title"]
        severity = finding["severity"]
        evidence = finding.get("evidence") or []
        if title in {"Session log appears readable", "No malformed JSONL entries detected"} and severity == "OK":
            continue
        if title == "Reasoner/backend summary":
            if severity == "INFO" and evidence:
                lines.append(f"Reasoner/backend: {', '.join(evidence)}; consider testing with Ollama")
            elif evidence:
                lines.append(f"Reasoner/backend: {', '.join(evidence)}")
            continue
        label = title.replace(" detected", "")
        line = f"{label}: {severity}"
        if evidence:
            line += f", {'; '.join(evidence[:2])}"
        lines.append(line)
    return lines or ["No doctor findings requiring action: OK"]


def _format_self_check_report(
    *,
    overall: str,
    source: Path,
    entries_checked: int,
    window: int,
    health: list[tuple[str, str]],
    doctor: list[str],
    recommendations: list[str],
) -> str:
    lines = [
        "Session Self-Check",
        f"Overall: {overall}",
        f"Source: {source}",
        f"Entries checked: {entries_checked}",
        f"Window: last {window}",
        "",
        "Health Summary:",
    ]
    lines.extend(f"- {name}: {value}" for name, value in health)
    lines.extend(["", "Doctor Summary:"])
    lines.extend(f"- {item}" for item in doctor)
    lines.extend(["", "Recommended next commands:"])
    lines.extend(f"- {command}" for command in recommendations)
    return "\n".join(lines)


def _self_check_recommendations(overall: str, window: int) -> list[str]:
    if overall == "ERROR":
        return ["/session log status", f"/session health --last {window}"]
    if overall == "WARN":
        return [
            f"/session health --last {window}",
            f"/session doctor --last {window}",
            "/session log warnings",
            f"/session review --last {window}",
            f"/session log export --last {window}",
        ]
    return [f"/session review --last {window}", f"/session log export --last {window}"]


def _doctor_findings(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    malformed_lines: list[str] = []
    reflection_turns: list[str] = []
    correction_turns: list[str] = []
    grounding_turns: list[str] = []
    retrieval_gap_turns: list[str] = []
    reasoner_counts: dict[str, int] = {}
    warning_messages: dict[str, int] = {}
    correction_messages: dict[str, int] = {}

    for record in records:
        if record["malformed_json"]:
            malformed_lines.append(str(record["line_number"]))
            continue
        entry = record["entry"]
        observer = entry.get("observer") or {}
        reflection = entry.get("self_reflection") or {}
        audit = entry.get("grounding_audit") or {}
        turn_id = str(entry.get("turn_id", f"line {record['line_number']}"))
        reasoner = str(entry.get("reasoner_backend") or "unknown")
        _increment(reasoner_counts, reasoner)

        warnings = reflection.get("warnings") or []
        hints = reflection.get("correction_hints") or []
        if warnings:
            reflection_turns.append(turn_id)
            for warning in warnings:
                _increment(warning_messages, str(warning))
        if hints:
            correction_turns.append(turn_id)
            for hint in hints:
                _increment(correction_messages, str(hint))
        if _grounding_issue_count(audit):
            grounding_turns.append(turn_id)
        if _retrieval_gap(entry):
            retrieval_gap_turns.append(turn_id)

    findings = [
        _finding(
            "Session log appears readable",
            "OK",
            [f"entries analyzed: {len(records)}"],
            ["No action needed."],
        )
    ]

    if malformed_lines:
        findings.append(
            _finding(
                "Malformed JSONL entries detected",
                "WARN",
                [f"lines: {_limited_join(malformed_lines)}", f"count: {len(malformed_lines)}"],
                ["Inspect the log source before relying on exports or summaries."],
            )
        )
    else:
        findings.append(
            _finding(
                "No malformed JSONL entries detected",
                "OK",
                [f"entries checked: {len(records)}"],
                ["No action needed."],
            )
        )

    if reflection_turns:
        findings.append(
            _finding(
                "Reflection warnings detected",
                "WARN",
                [f"turns: {_limited_join(reflection_turns)}", f"count: {len(reflection_turns)}"],
                [
                    "Run /session log warnings.",
                    "Inspect affected turns with /session log inspect N.",
                    "Consider tuning self_reflection checks if warnings repeat.",
                ],
            )
        )
    else:
        findings.append(_finding("No reflection warnings detected", "OK", [], ["No action needed."]))

    if correction_turns:
        findings.append(
            _finding(
                "Correction hints detected",
                "INFO",
                [f"turns: {_limited_join(correction_turns)}", f"count: {len(correction_turns)}"],
                [
                    "Review whether hints are useful or noisy.",
                    "If repeated, improve response-style enforcement before generation.",
                ],
            )
        )

    repeated = _top_repeated_message({**warning_messages, **correction_messages})
    if repeated:
        message, count = repeated
        findings.append(
            _finding(
                "Repeated warning theme detected",
                "WARN",
                [f"{message} x{count}"],
                ["Consider targeted tuning for the repeated theme."],
            )
        )

    if grounding_turns:
        findings.append(
            _finding(
                "Grounding issues detected",
                "WARN",
                [f"turns: {_limited_join(grounding_turns)}", f"count: {len(grounding_turns)}"],
                ["Inspect affected turns with /session log inspect N.", "Run /session log warnings."],
            )
        )
    else:
        findings.append(_finding("No grounding issues detected", "OK", [], ["No action needed."]))

    if retrieval_gap_turns:
        findings.append(
            _finding(
                "Potential retrieval gaps detected",
                "INFO",
                [f"turns: {_limited_join(retrieval_gap_turns)}", f"count: {len(retrieval_gap_turns)}"],
                ["Inspect whether these turns expected memory but retrieved no ids."],
            )
        )

    if reasoner_counts:
        reasoner_evidence = [f"{name}: {count}" for name, count in sorted(reasoner_counts.items())]
        recommendations = ["No action needed."]
        severity = "OK"
        if set(reasoner_counts) == {"mock"}:
            severity = "INFO"
            recommendations = ["Current log appears mock-backed; run with Ollama to evaluate local reasoner behavior."]
        findings.append(_finding("Reasoner/backend summary", severity, reasoner_evidence, recommendations))

    return findings


def _format_doctor_report(
    *,
    status: str,
    source: Path,
    entries_analyzed: int,
    window: int,
    findings: list[dict[str, Any]],
) -> str:
    lines = [
        "Session Doctor",
        f"Status: {status}",
        f"Source: {source}",
        f"Entries analyzed: {entries_analyzed}",
        f"Window: last {window}",
        "",
        "Findings:",
    ]
    for index, finding in enumerate(findings, start=1):
        lines.extend(
            [
                "",
                f"{index}. {finding['title']}",
                f"   Severity: {finding['severity']}",
                "   Evidence:",
            ]
        )
        evidence = finding.get("evidence") or []
        if evidence:
            lines.extend(f"   - {item}" for item in evidence)
        else:
            lines.append("   - none")
        lines.append("   Recommendation:")
        lines.extend(f"   - {item}" for item in finding.get("recommendations") or ["No action needed."])
    lines.extend(
        [
            "",
            "Next steps:",
            "- /session health",
            "- /session review",
            "- /session log warnings",
            f"- /session log export --last {window}",
        ]
    )
    return "\n".join(lines)


def _finding(title: str, severity: str, evidence: list[str], recommendations: list[str]) -> dict[str, Any]:
    return {
        "title": title,
        "severity": severity,
        "evidence": evidence,
        "recommendations": recommendations,
    }


def _doctor_status(findings: list[dict[str, Any]]) -> str:
    severities = {finding["severity"] for finding in findings}
    if "ERROR" in severities:
        return "ERROR"
    if "WARN" in severities:
        return "WARN"
    return "OK"


def _limited_join(values: list[str], limit: int = 10) -> str:
    shown = values[:limit]
    suffix = "" if len(values) <= limit else f", +{len(values) - limit} more"
    return ", ".join(shown) + suffix


def _top_repeated_message(messages: dict[str, int]) -> tuple[str, int] | None:
    repeated = [(message, count) for message, count in messages.items() if count > 1]
    if not repeated:
        return None
    return sorted(repeated, key=lambda item: (-item[1], item[0]))[0]


def _retrieval_gap(entry: dict[str, Any]) -> bool:
    observer = entry.get("observer") or {}
    query_type = observer.get("query_type")
    retrieved_ids = entry.get("retrieved_memory_ids")
    memory_sensitive = {
        "memory_inventory",
        "continuity_followup",
        "project_context",
        "personal_context",
        "meta_architecture",
    }
    return query_type in memory_sensitive and isinstance(retrieved_ids, list) and not retrieved_ids


def _grounding_issue_count(audit: dict[str, Any]) -> int:
    count = len(audit.get("warnings") or [])
    grounding_status = audit.get("grounding_status")
    if grounding_status and grounding_status not in {"grounded", "not_needed"}:
        count += 1
    if audit.get("active_decision_status") == "contradicted":
        count += 1
    if audit.get("superseded_memory_status") == "treated_as_current":
        count += 1
    return count


def _check(ok: bool) -> str:
    return "OK" if ok else "WARN"


def _increment(counts: dict[str, int], key: str) -> None:
    counts[key] = counts.get(key, 0) + 1


def _format_count_lines(counts: dict[str, int], defaults: tuple[str, ...] = ()) -> list[str]:
    keys = list(defaults)
    for key in sorted(counts):
        if key not in keys:
            keys.append(key)
    if not keys:
        return ["- none: 0"]
    return [f"- {key}: {counts.get(key, 0)}" for key in keys]


def _search_result_from_line(raw_line: str, line_number: int, query: str) -> dict[str, Any]:
    try:
        entry = json.loads(raw_line)
        if not isinstance(entry, dict):
            entry = {"raw_value": entry}
        malformed = False
        search_text = _searchable_entry_text(entry)
    except json.JSONDecodeError:
        entry = {"raw_line": raw_line}
        malformed = True
        search_text = raw_line
    entry["_search_line_number"] = line_number
    entry["_search_malformed_json"] = malformed
    entry["_search_text"] = search_text
    entry["_search_match_preview"] = _match_preview(search_text, query)
    return entry


def _searchable_entry_text(entry: dict[str, Any]) -> str:
    observer = entry.get("observer") or {}
    reflection = entry.get("self_reflection") or {}
    audit = entry.get("grounding_audit") or {}
    values: list[Any] = [
        entry.get("user_input"),
        entry.get("response_preview"),
        entry.get("reasoner_backend"),
        observer.get("query_type"),
        observer.get("tags"),
        entry.get("retrieved_memory_ids"),
        reflection.get("warnings"),
        reflection.get("correction_hints"),
        audit.get("grounding_status"),
        audit.get("warnings"),
        audit.get("memory_support"),
        audit.get("active_decision_status"),
        audit.get("superseded_memory_status"),
    ]
    return " ".join(_flatten_search_values(values))


def _flatten_search_values(values: object) -> list[str]:
    if values is None:
        return []
    if isinstance(values, list):
        flattened: list[str] = []
        for value in values:
            flattened.extend(_flatten_search_values(value))
        return flattened
    if isinstance(values, dict):
        flattened = []
        for value in values.values():
            flattened.extend(_flatten_search_values(value))
        return flattened
    return [str(values)]


def _format_search_results(query: str, matches: list[dict[str, Any]], total: int) -> str:
    header = [f'Session log search: "{query}"']
    if not matches:
        return "\n".join(header + ["No matches found."])

    header.append(f"Found {total} match(es). Showing {len(matches)} of {total}.")
    lines = header
    for index, entry in enumerate(matches, start=1):
        observer = entry.get("observer") or {}
        reflection = entry.get("self_reflection") or {}
        audit = entry.get("grounding_audit") or {}
        malformed = entry.get("_search_malformed_json", False)
        lines.extend(
            [
                "",
                f"[{index}] {entry.get('timestamp', 'unknown')} | turn_id={entry.get('turn_id', 'unknown')} | type={observer.get('query_type', 'unknown')}",
                f"    input: {_preview(str(entry.get('user_input', entry.get('raw_line', ''))), limit=120)}",
                f"    grounding: {audit.get('grounding_status', 'unknown')} | reflection: {reflection.get('memory_alignment', 'unknown')}",
                f"    response: {_preview(str(entry.get('response_preview', '')), limit=140)}",
                f"    matched: {entry.get('_search_match_preview', '')}",
                f"    line: {entry.get('_search_line_number', 'unknown')}",
            ]
        )
        if malformed:
            lines.append("    malformed_json: true")
    return "\n".join(lines)


def _match_preview(text: str, query: str, *, context: int = 44) -> str:
    normalized = " ".join(text.split())
    index = normalized.casefold().find(query.casefold())
    if index < 0:
        return _preview(normalized, limit=context * 2)
    start = max(index - context, 0)
    end = min(index + len(query) + context, len(normalized))
    prefix = "..." if start > 0 else ""
    suffix = "..." if end < len(normalized) else ""
    return prefix + normalized[start:end] + suffix


def _format_inspect_entry(entry: dict[str, Any]) -> list[str]:
    observer = entry.get("observer") or {}
    reflection = entry.get("self_reflection") or {}
    audit = entry.get("grounding_audit") or {}
    retrieval_trace = entry.get("retrieval_trace") or {}

    lines = [
        f"Turn: {entry.get('turn_id', 'unknown')}",
        f"Timestamp: {entry.get('timestamp', 'unknown')}",
        f"Input: {_preview(str(entry.get('user_input', '')), limit=180)}",
        f"Response preview: {_preview(str(entry.get('response_preview', '')), limit=220)}",
        f"Reasoner: {entry.get('reasoner_backend', 'unknown')}",
        "Observer:",
        f"  query_type: {observer.get('query_type', 'unknown')}",
        f"  needs_memory: {observer.get('needs_memory', 'unknown')}",
        f"  tags: {_format_inline_list(observer.get('tags'))}",
        "Retrieved memory ids:",
    ]
    lines.extend(_format_bullets(entry.get("retrieved_memory_ids"), empty_label="none"))
    lines.extend(
        [
            "Retrieval trace:",
            f"  query_mode: {retrieval_trace.get('query_mode', 'unknown')}",
            f"  current_state_oriented: {retrieval_trace.get('current_state_oriented', 'unknown')}",
            f"  historical_state_oriented: {retrieval_trace.get('historical_state_oriented', 'unknown')}",
            f"  candidates: {retrieval_trace.get('candidate_count', 'unknown')}",
            f"  selected: {retrieval_trace.get('selected_count', 'unknown')}",
            "Self-reflection:",
            f"  memory_alignment: {reflection.get('memory_alignment', 'unknown')}",
            f"  preference_alignment: {reflection.get('preference_alignment', 'unknown')}",
            f"  active_decision_alignment: {reflection.get('active_decision_alignment', 'unknown')}",
            "  warnings:",
        ]
    )
    lines.extend(_format_bullets(reflection.get("warnings"), indent="    ", empty_label="none"))
    lines.append("  correction_hints:")
    lines.extend(_format_bullets(reflection.get("correction_hints"), indent="    ", empty_label="none"))
    lines.extend(
        [
            "Grounding audit:",
            f"  status: {audit.get('grounding_status', 'unknown')}",
            f"  memory_support: {audit.get('memory_support', 'unknown')}",
            f"  active_decision_status: {audit.get('active_decision_status', 'unknown')}",
            f"  superseded_memory_status: {audit.get('superseded_memory_status', 'unknown')}",
            "  warnings:",
        ]
    )
    lines.extend(_format_bullets(audit.get("warnings"), indent="    ", empty_label="none"))
    lines.append("Previous correction hints used:")
    lines.extend(_format_bullets(entry.get("previous_correction_hints"), empty_label="none"))
    return lines


def _format_warning_entry(entry: dict[str, Any]) -> list[str]:
    reflection = entry.get("self_reflection") or {}
    audit = entry.get("grounding_audit") or {}
    lines = [
        f"Turn: {entry.get('turn_id', 'unknown')}",
        f"Timestamp: {entry.get('timestamp', 'unknown')}",
        f"Input: {_preview(str(entry.get('user_input', '')), limit=180)}",
        "Reflection warnings:",
    ]
    lines.extend(_format_bullets(reflection.get("warnings"), indent="  ", empty_label="none"))
    lines.append("Grounding warnings:")
    grounding_warnings = list(audit.get("warnings") or [])
    grounding_status = audit.get("grounding_status")
    if grounding_status and grounding_status not in {"grounded", "not_needed"}:
        grounding_warnings.append(f"grounding_status={grounding_status}")
    if audit.get("active_decision_status") == "contradicted":
        grounding_warnings.append("active_decision_status=contradicted")
    if audit.get("superseded_memory_status") == "treated_as_current":
        grounding_warnings.append("superseded_memory_status=treated_as_current")
    lines.extend(_format_bullets(grounding_warnings, indent="  ", empty_label="none"))
    lines.append("Correction hints:")
    lines.extend(_format_bullets(reflection.get("correction_hints"), indent="  ", empty_label="none"))
    return lines


def _entry_has_warning_signal(entry: dict[str, Any]) -> bool:
    reflection = entry.get("self_reflection") or {}
    audit = entry.get("grounding_audit") or {}
    if reflection.get("warnings"):
        return True
    if reflection.get("correction_hints"):
        return True
    if audit.get("warnings"):
        return True
    grounding_status = audit.get("grounding_status")
    if grounding_status and grounding_status not in {"grounded", "not_needed"}:
        return True
    if audit.get("active_decision_status") == "contradicted":
        return True
    return audit.get("superseded_memory_status") == "treated_as_current"


def _format_bullets(values: object, *, indent: str = "  ", empty_label: str = "none") -> list[str]:
    if not isinstance(values, list) or not values:
        return [f"{indent}- {empty_label}"]
    return [f"{indent}- {_preview(str(value), limit=160)}" for value in values]


def _format_inline_list(values: object) -> str:
    if not isinstance(values, list) or not values:
        return "[]"
    return "[" + ", ".join(str(value) for value in values) + "]"


def _preview(text: str, limit: int = 240) -> str:
    normalized = " ".join(text.split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 3] + "..."
