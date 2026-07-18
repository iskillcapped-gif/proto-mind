from __future__ import annotations

import json
import re
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from proto_mind.session_log import SessionOperatorLogger


DEFAULT_REFLECTION_WINDOW = 50
DEFAULT_REFLECTION_LIST_LIMIT = 10


def format_reflection_command(
    command: str,
    *,
    project_root: Path,
    session_logger: SessionOperatorLogger,
) -> str | None:
    stripped = command.strip()
    normalized = " ".join(stripped.lower().split())
    if not normalized.startswith("/reflection"):
        return None

    journal = ReflectionJournal.from_project_root(project_root)
    if normalized == "/reflection status":
        return journal.format_status()
    if normalized.startswith("/reflection list"):
        parsed_list = _parse_list_command(stripped)
        if isinstance(parsed_list, str):
            return parsed_list
        return journal.format_list(limit=parsed_list["limit"])
    if normalized.startswith("/reflection inspect"):
        reflection_id = stripped[len("/reflection inspect") :].strip()
        return journal.format_inspect(reflection_id)
    if normalized.startswith("/reflection now") or normalized.startswith("/reflection last"):
        parsed_now = _parse_now_command(stripped)
        if isinstance(parsed_now, str):
            return parsed_now
        record = journal.create_from_session_log(
            session_logger=session_logger,
            last=parsed_now["last"],
            scope=parsed_now["scope"],
        )
        return journal.format_created(record)
    return (
        "Usage:\n"
        "  /reflection now [--last N]\n"
        "  /reflection last [--last N]\n"
        "  /reflection list [--limit N]\n"
        "  /reflection inspect <id>\n"
        "  /reflection status"
    )


class ReflectionJournal:
    def __init__(self, journal_path: Path) -> None:
        self.journal_path = journal_path

    @classmethod
    def from_project_root(cls, project_root: Path) -> "ReflectionJournal":
        return cls(project_root / "proto_mind" / "data" / "reflection_journal.jsonl")

    def create_from_session_log(
        self,
        *,
        session_logger: SessionOperatorLogger,
        last: int = DEFAULT_REFLECTION_WINDOW,
        scope: str = "last",
    ) -> dict[str, Any]:
        records = _safe_session_records(session_logger, last)
        analysis = analyze_session_records(records, requested_last=last, log_path=session_logger.log_path)
        now = datetime.now(UTC).isoformat()
        record = {
            "id": _new_reflection_id(now),
            "created_at": now,
            "scope": scope,
            "source": "session_log",
            "entries_analyzed": analysis["entries_analyzed"],
            "summary": analysis["summary"],
            "findings": analysis["findings"],
            "recommendations": analysis["recommendations"],
            "tags": analysis["tags"],
            "metadata": {
                "session_log_path": str(session_logger.log_path),
                "requested_last": last,
                "time_span": analysis["time_span"],
                "query_type_counts": analysis["query_type_counts"],
                "backend_counts": analysis["backend_counts"],
                "recent_inputs": analysis["recent_inputs"],
                "recent_operator_commands": analysis["recent_operator_commands"],
                "malformed_entries": analysis["malformed_entries"],
                "reflection_warnings": analysis["reflection_warnings"],
                "correction_hints": analysis["correction_hints"],
                "grounding_issues": analysis["grounding_issues"],
                "memory_command_count": analysis["memory_command_count"],
                "command_counts": analysis["command_counts"],
                "repeated_warning_themes": analysis["repeated_warning_themes"],
            },
        }
        self.append(record)
        return record

    def append(self, record: dict[str, Any]) -> None:
        self.journal_path.parent.mkdir(parents=True, exist_ok=True)
        with self.journal_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")

    def format_created(self, record: dict[str, Any]) -> str:
        metadata = record.get("metadata") or {}
        lines = [
            "Reflection Journal",
            f"Created: {record.get('id', 'unknown')}",
            f"Scope: {record.get('scope', 'unknown')} {metadata.get('requested_last', DEFAULT_REFLECTION_WINDOW)}",
            f"Entries analyzed: {record.get('entries_analyzed', 0)}",
            f"Summary: {record.get('summary', '')}",
            "Findings:",
        ]
        lines.extend(_format_bullets(record.get("findings")))
        lines.append("Recommendations:")
        lines.extend(_format_bullets(record.get("recommendations")))
        lines.append(f"Saved: {self.journal_path}")
        return "\n".join(lines)

    def format_list(self, *, limit: int = DEFAULT_REFLECTION_LIST_LIMIT) -> str:
        records, malformed_count = self.read_records()
        lines = [f"Reflection journal list (last {limit}):", f"Path: {self.journal_path}"]
        if malformed_count:
            lines.append(f"Malformed journal lines skipped: {malformed_count}")
        if not records:
            lines.append("  (none)")
            return "\n".join(lines)
        for record in records[-limit:][::-1]:
            lines.append(
                "  - "
                f"{record.get('id', 'unknown')} "
                f"created_at={record.get('created_at', 'unknown')} "
                f"scope={record.get('scope', 'unknown')} "
                f"summary={_preview(str(record.get('summary', '')), limit=100)}"
            )
        return "\n".join(lines)

    def format_inspect(self, reflection_id: str) -> str:
        reflection_id = reflection_id.strip()
        if not reflection_id:
            return "Usage: /reflection inspect <id>"
        records, _ = self.read_records()
        for record in records:
            if record.get("id") == reflection_id:
                return _format_reflection_record(record)
        return f"Reflection entry not found: {reflection_id}"

    def format_status(self) -> str:
        records, malformed_count = self.read_records()
        exists = self.journal_path.exists()
        health = "ok"
        if malformed_count:
            health = "malformed_jsonl"
        if not exists:
            health = "missing"
        last_created = records[-1].get("created_at") if records else "none"
        return "\n".join(
            [
                "Reflection journal status:",
                f"  path: {self.journal_path}",
                f"  exists: {exists}",
                f"  entries: {len(records)}",
                f"  malformed_entries: {malformed_count}",
                f"  last_reflection: {last_created}",
                f"  file_health: {health}",
            ]
        )

    def read_records(self) -> tuple[list[dict[str, Any]], int]:
        if not self.journal_path.exists():
            return ([], 0)
        records: list[dict[str, Any]] = []
        malformed_count = 0
        try:
            lines = self.journal_path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return ([], 1)
        for raw_line in lines:
            if not raw_line.strip():
                continue
            try:
                parsed = json.loads(raw_line)
            except json.JSONDecodeError:
                malformed_count += 1
                continue
            if isinstance(parsed, dict):
                records.append(parsed)
            else:
                malformed_count += 1
        return (records, malformed_count)


def analyze_session_records(
    records: list[dict[str, Any]],
    *,
    requested_last: int,
    log_path: Path,
) -> dict[str, Any]:
    valid_entries = [record.get("entry") or {} for record in records if not record.get("malformed_json")]
    malformed_entries = sum(1 for record in records if record.get("malformed_json"))
    query_type_counts: Counter[str] = Counter()
    backend_counts: Counter[str] = Counter()
    command_counts: Counter[str] = Counter()
    reflection_warnings: list[str] = []
    correction_hints: list[str] = []
    grounding_issues: list[str] = []
    recent_inputs: list[str] = []
    recent_operator_commands: list[str] = []
    timestamps = [str(entry.get("timestamp")) for entry in valid_entries if entry.get("timestamp")]

    for entry in valid_entries:
        observer = entry.get("observer") or {}
        reflection = entry.get("self_reflection") or {}
        audit = entry.get("grounding_audit") or {}
        query_type_counts[str(observer.get("query_type") or "unknown")] += 1
        backend_counts[str(entry.get("reasoner_backend") or "unknown")] += 1

        user_input = str(entry.get("user_input") or "").strip()
        if user_input:
            recent_inputs.append(_preview(user_input, limit=120))
            if user_input.startswith("/"):
                command = " ".join(user_input.split()[:2])
                command_counts[command] += 1
                recent_operator_commands.append(_preview(user_input, limit=120))

        reflection_warnings.extend(str(item) for item in reflection.get("warnings") or [])
        correction_hints.extend(str(item) for item in reflection.get("correction_hints") or [])

        grounding_status = audit.get("grounding_status")
        if grounding_status and grounding_status not in {"grounded", "not_needed"}:
            grounding_issues.append(f"turn {entry.get('turn_id', 'unknown')}: grounding_status={grounding_status}")
        if audit.get("warnings"):
            grounding_issues.extend(str(item) for item in audit.get("warnings") or [])
        if audit.get("active_decision_status") == "contradicted":
            grounding_issues.append(f"turn {entry.get('turn_id', 'unknown')}: active_decision_status=contradicted")
        if audit.get("superseded_memory_status") == "treated_as_current":
            grounding_issues.append(f"turn {entry.get('turn_id', 'unknown')}: superseded_memory_status=treated_as_current")

    memory_command_count = sum(count for command, count in command_counts.items() if command.startswith("/memory"))
    repeated_warning_themes = _repeated_themes(reflection_warnings + correction_hints)
    time_span = _time_span(timestamps)
    findings = _reflection_findings(
        entries_analyzed=len(records),
        malformed_entries=malformed_entries,
        reflection_warnings=reflection_warnings,
        correction_hints=correction_hints,
        grounding_issues=grounding_issues,
        memory_command_count=memory_command_count,
        repeated_warning_themes=repeated_warning_themes,
        log_path=log_path,
    )
    recommendations = _reflection_recommendations(
        malformed_entries=malformed_entries,
        reflection_warnings=reflection_warnings,
        correction_hints=correction_hints,
        grounding_issues=grounding_issues,
        memory_command_count=memory_command_count,
    )
    tags = ["session_log", "reflection_journal"]
    if reflection_warnings or correction_hints:
        tags.append("warnings")
    if grounding_issues:
        tags.append("grounding")
    if memory_command_count:
        tags.append("memory")
    if malformed_entries:
        tags.append("malformed_jsonl")

    return {
        "entries_analyzed": len(records),
        "summary": _reflection_summary(
            entries_analyzed=len(records),
            requested_last=requested_last,
            time_span=time_span,
            query_type_counts=query_type_counts,
            backend_counts=backend_counts,
            malformed_entries=malformed_entries,
            reflection_warnings=reflection_warnings,
            correction_hints=correction_hints,
            grounding_issues=grounding_issues,
        ),
        "findings": findings,
        "recommendations": recommendations,
        "tags": tags,
        "time_span": time_span,
        "query_type_counts": dict(sorted(query_type_counts.items())),
        "backend_counts": dict(sorted(backend_counts.items())),
        "recent_inputs": recent_inputs[-5:],
        "recent_operator_commands": recent_operator_commands[-5:],
        "malformed_entries": malformed_entries,
        "reflection_warnings": len(reflection_warnings),
        "correction_hints": len(correction_hints),
        "grounding_issues": len(grounding_issues),
        "memory_command_count": memory_command_count,
        "command_counts": dict(command_counts.most_common(10)),
        "repeated_warning_themes": repeated_warning_themes,
    }


def _safe_session_records(session_logger: SessionOperatorLogger, last: int) -> list[dict[str, Any]]:
    if not session_logger.log_path.exists():
        return []
    try:
        return session_logger.review_records(last=last)
    except OSError:
        return []


def _parse_now_command(command: str) -> dict[str, Any] | str:
    parts = command.strip().split()
    if len(parts) < 2 or parts[1].lower() not in {"now", "last"}:
        return "Usage: /reflection now [--last N]"
    last = DEFAULT_REFLECTION_WINDOW
    index = 2
    while index < len(parts):
        token = parts[index].lower()
        if token == "--last":
            if index + 1 >= len(parts):
                return "Invalid --last value. Usage: /reflection now [--last N]"
            try:
                last = int(parts[index + 1])
            except ValueError:
                return "Invalid --last value. Usage: /reflection now [--last N]"
            if last <= 0:
                return "--last must be greater than 0."
            last = min(last, 1000)
            index += 2
            continue
        return "Usage: /reflection now [--last N]"
    return {"last": last, "scope": parts[1].lower()}


def _parse_list_command(command: str) -> dict[str, int] | str:
    parts = command.strip().split()
    limit = DEFAULT_REFLECTION_LIST_LIMIT
    index = 2
    while index < len(parts):
        token = parts[index].lower()
        if token == "--limit":
            if index + 1 >= len(parts):
                return "Invalid --limit value. Usage: /reflection list [--limit N]"
            try:
                limit = int(parts[index + 1])
            except ValueError:
                return "Invalid --limit value. Usage: /reflection list [--limit N]"
            if limit <= 0:
                return "--limit must be greater than 0."
            limit = min(limit, 100)
            index += 2
            continue
        return "Usage: /reflection list [--limit N]"
    return {"limit": limit}


def _reflection_summary(
    *,
    entries_analyzed: int,
    requested_last: int,
    time_span: str,
    query_type_counts: Counter[str],
    backend_counts: Counter[str],
    malformed_entries: int,
    reflection_warnings: list[str],
    correction_hints: list[str],
    grounding_issues: list[str],
) -> str:
    query_summary = _top_counter_summary(query_type_counts)
    backend_summary = _top_counter_summary(backend_counts)
    issue_count = malformed_entries + len(reflection_warnings) + len(correction_hints) + len(grounding_issues)
    if entries_analyzed == 0:
        return f"No session log entries were available in the requested last {requested_last} window."
    if issue_count:
        return (
            f"Analyzed {entries_analyzed} session log entr{'y' if entries_analyzed == 1 else 'ies'} "
            f"from {time_span}; observed {issue_count} warning-like signal(s). "
            f"Query types: {query_summary}. Backends: {backend_summary}."
        )
    return (
        f"Analyzed {entries_analyzed} session log entr{'y' if entries_analyzed == 1 else 'ies'} "
        f"from {time_span}; no urgent warning-like signals found. "
        f"Query types: {query_summary}. Backends: {backend_summary}."
    )


def _reflection_findings(
    *,
    entries_analyzed: int,
    malformed_entries: int,
    reflection_warnings: list[str],
    correction_hints: list[str],
    grounding_issues: list[str],
    memory_command_count: int,
    repeated_warning_themes: list[str],
    log_path: Path,
) -> list[str]:
    findings: list[str] = []
    if entries_analyzed == 0:
        findings.append(f"No session log entries found at {log_path}.")
    else:
        findings.append(f"Analyzed {entries_analyzed} recent session log entr{'y' if entries_analyzed == 1 else 'ies'}.")
    if malformed_entries:
        findings.append(f"Malformed session log entries detected: {malformed_entries}.")
    if reflection_warnings:
        findings.append(f"Self-reflection warnings detected: {len(reflection_warnings)}.")
    if correction_hints:
        findings.append(f"Correction hints detected: {len(correction_hints)}.")
    if grounding_issues:
        findings.append(f"Grounding issue signals detected: {len(grounding_issues)}.")
    if repeated_warning_themes:
        findings.append("Repeated warning themes: " + "; ".join(repeated_warning_themes[:3]) + ".")
    if memory_command_count:
        findings.append(f"Memory commands appeared in recent logged inputs: {memory_command_count}.")
    if len(findings) == 1 and entries_analyzed:
        findings.append("No urgent warning-like issues detected by deterministic checks.")
    return findings


def _reflection_recommendations(
    *,
    malformed_entries: int,
    reflection_warnings: list[str],
    correction_hints: list[str],
    grounding_issues: list[str],
    memory_command_count: int,
) -> list[str]:
    recommendations: list[str] = []
    if reflection_warnings or correction_hints or grounding_issues:
        recommendations.append("Run /session doctor for actionable session-log findings.")
        recommendations.append("Run /session log warnings to inspect warning-like turns.")
    if memory_command_count:
        recommendations.append("Run /memory doctor after explicit memory edits or repeated memory commands.")
    if malformed_entries:
        recommendations.append("Inspect malformed log lines with /session log inspect or export recent entries for repair.")
    if not recommendations:
        recommendations.append("No urgent actions. Continue normal operator workflow.")
    return recommendations


def _format_reflection_record(record: dict[str, Any]) -> str:
    metadata = record.get("metadata") or {}
    lines = [
        "Reflection entry:",
        f"  id: {record.get('id', 'unknown')}",
        f"  created_at: {record.get('created_at', 'unknown')}",
        f"  scope: {record.get('scope', 'unknown')}",
        f"  source: {record.get('source', 'unknown')}",
        f"  entries_analyzed: {record.get('entries_analyzed', 0)}",
        f"  summary: {record.get('summary', '')}",
        f"  tags: {record.get('tags', [])}",
        f"  session_log_path: {metadata.get('session_log_path', 'unknown')}",
        f"  time_span: {metadata.get('time_span', 'unknown')}",
        f"  query_type_counts: {metadata.get('query_type_counts', {})}",
        f"  backend_counts: {metadata.get('backend_counts', {})}",
        f"  recent_inputs: {metadata.get('recent_inputs', [])}",
        f"  recent_operator_commands: {metadata.get('recent_operator_commands', [])}",
        f"  repeated_warning_themes: {metadata.get('repeated_warning_themes', [])}",
        "  findings:",
    ]
    lines.extend(_format_bullets(record.get("findings"), indent="    "))
    lines.append("  recommendations:")
    lines.extend(_format_bullets(record.get("recommendations"), indent="    "))
    return "\n".join(lines)


def _format_bullets(values: object, *, indent: str = "  ") -> list[str]:
    if not isinstance(values, list) or not values:
        return [f"{indent}- none"]
    return [f"{indent}- {_preview(str(value), limit=180)}" for value in values]


def _top_counter_summary(counter: Counter[str]) -> str:
    if not counter:
        return "none"
    return ", ".join(f"{key}={value}" for key, value in counter.most_common(3))


def _time_span(timestamps: list[str]) -> str:
    if not timestamps:
        return "unknown"
    if len(timestamps) == 1:
        return timestamps[0]
    return f"{timestamps[0]} to {timestamps[-1]}"


def _repeated_themes(messages: list[str]) -> list[str]:
    counts = Counter(_normalize_theme(message) for message in messages if message.strip())
    return [f"{theme} x{count}" for theme, count in counts.most_common(5) if count > 1]


def _normalize_theme(message: str) -> str:
    return " ".join(message.strip().split())


def _new_reflection_id(timestamp: str) -> str:
    compact = re.sub(r"[^0-9]", "", timestamp)[:14]
    return f"refl_{compact}_{uuid4().hex[:4]}"


def _preview(text: str, limit: int = 160) -> str:
    normalized = " ".join(text.split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 3] + "..."
