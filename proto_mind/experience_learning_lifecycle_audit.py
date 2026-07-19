from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime
import json
from typing import Any

from proto_mind.memory_provenance import verify_memory_provenance
from proto_mind.memory_store import MemoryStore
from proto_mind.models import MemoryRecord


LEARNING_LIFECYCLE_AUDIT_VERSION = 1
LEARNING_LIFECYCLE_AUDIT_MODE = "read_only_durable_lesson_state_reconstruction"
LIFECYCLE_REJECT_REASON = "verified_learning_outcome_reject"
LIFECYCLE_SUPERSEDE_REASON = "verified_learning_outcome_supersede"
OPERATOR_FORGET_REASON = "Forgotten by operator."


@dataclass(frozen=True)
class LearningLifecycleAuditEntry:
    memory_id: str
    state: str
    active: bool
    content_preview: str
    provenance_status: str
    provenance_id: str
    source_apply_id: str
    applied_at: str
    lifecycle_at: str
    lifecycle_reason: str
    replacement_memory_id: str
    replacement_status: str
    restart_safe: bool
    issues: list[str]
    warnings: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class LearningLifecycleAuditReport:
    status: str
    persistent_path: str
    learned_lesson_count: int
    active_count: int
    rejected_count: int
    superseded_count: int
    forgotten_count: int
    unclassified_count: int
    invalid_count: int
    entries: list[LearningLifecycleAuditEntry]
    issues: list[str]
    warnings: list[str]
    mutation_performed: bool = False


class LearningLifecycleAuditError(RuntimeError):
    pass


class LearningLifecycleTransitionAudit:
    """Reconstructs current learned-lesson lifecycle state without changing storage."""

    def __init__(self, memory_store: MemoryStore) -> None:
        self.memory_store = memory_store

    def inspect(self) -> LearningLifecycleAuditReport:
        records = self._load_records()
        ids = [record.id for record in records]
        duplicate_ids = sorted(
            record_id for record_id, count in Counter(ids).items() if count > 1
        )
        by_id = {record.id: record for record in records}
        learned = [record for record in records if _is_learned_lesson(record)]
        entries = [self._entry(record, by_id) for record in learned]
        issues = [f"Duplicate persistent memory id: {record_id}." for record_id in duplicate_ids]
        warnings: list[str] = []
        for entry in entries:
            issues.extend(f"{entry.memory_id}: {issue}" for issue in entry.issues)
            warnings.extend(f"{entry.memory_id}: {warning}" for warning in entry.warnings)
        cycles = _reference_cycles(learned)
        issues.extend(f"Lifecycle replacement cycle detected: {' -> '.join(cycle)}." for cycle in cycles)
        counts = Counter(entry.state for entry in entries)
        status = "ERROR" if issues else "WARN" if warnings else "OK"
        return LearningLifecycleAuditReport(
            status=status,
            persistent_path=str(self.memory_store.persistent_path),
            learned_lesson_count=len(entries),
            active_count=counts["active"],
            rejected_count=counts["rejected"],
            superseded_count=counts["superseded"],
            forgotten_count=counts["forgotten"],
            unclassified_count=counts["inactive_unclassified"],
            invalid_count=counts["invalid"],
            entries=entries,
            issues=_dedupe(issues),
            warnings=_dedupe(warnings),
        )

    def get(self, memory_id: str) -> LearningLifecycleAuditEntry | None:
        return next(
            (entry for entry in self.inspect().entries if entry.memory_id == memory_id),
            None,
        )

    def _load_records(self) -> list[MemoryRecord]:
        try:
            return self.memory_store.load_persistent_memory()
        except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise LearningLifecycleAuditError(f"Persistent memory is unreadable: {exc}") from exc

    def _entry(
        self,
        record: MemoryRecord,
        by_id: dict[str, MemoryRecord],
    ) -> LearningLifecycleAuditEntry:
        provenance = verify_memory_provenance(record)
        reason = record.superseded_reason or ""
        replacement_id = record.superseded_by or ""
        replacement = by_id.get(replacement_id) if replacement_id else None
        issues: list[str] = []
        warnings: list[str] = []
        state = _lifecycle_state(record)

        if not provenance.verified:
            issues.append("Durable learning provenance does not verify.")
            state = "invalid"
        if record.active and any(
            (record.superseded_by, record.superseded_at, record.superseded_reason)
        ):
            issues.append("Active lesson carries terminal lifecycle fields.")
            state = "invalid"
        if reason == LIFECYCLE_REJECT_REASON:
            if record.active or replacement_id or not record.superseded_at:
                issues.append("Reject transition fields violate the v3.4g contract.")
                state = "invalid"
        elif reason == LIFECYCLE_SUPERSEDE_REASON:
            if record.active or not replacement_id or not record.superseded_at:
                issues.append("Supersede transition fields violate the v3.4g contract.")
                state = "invalid"
            if replacement_id == record.id:
                issues.append("Supersede replacement points to the old lesson itself.")
                state = "invalid"
            if replacement is None:
                issues.append("Supersede replacement is missing from persistent memory.")
                state = "invalid"
            elif not _is_learned_lesson(replacement):
                issues.append("Supersede replacement is not a learned lesson.")
                state = "invalid"
            else:
                replacement_provenance = verify_memory_provenance(replacement)
                if not replacement.active:
                    issues.append("Supersede replacement is not active.")
                    state = "invalid"
                if not replacement_provenance.verified:
                    issues.append("Supersede replacement provenance does not verify.")
                    state = "invalid"
                if not _timestamp_not_earlier(
                    _provenance_time(replacement),
                    _provenance_time(record),
                ):
                    issues.append("Supersede replacement is older than the old lesson.")
                    state = "invalid"
        elif not record.active and reason == OPERATOR_FORGET_REASON:
            state = "forgotten"
        elif not record.active and not reason and not replacement_id:
            warnings.append("Inactive learned lesson has no classified lifecycle reason.")
            state = "inactive_unclassified"
        elif not record.active and reason not in {
            LIFECYCLE_REJECT_REASON,
            LIFECYCLE_SUPERSEDE_REASON,
            OPERATOR_FORGET_REASON,
        }:
            warnings.append("Inactive learned lesson uses a non-v3.4g lifecycle reason.")
            state = "inactive_unclassified"

        if record.superseded_at and not _valid_timestamp(record.superseded_at):
            issues.append("Lifecycle timestamp is invalid.")
            state = "invalid"
        elif record.superseded_at and not _timestamp_not_earlier(
            record.superseded_at,
            _provenance_time(record),
        ):
            issues.append("Lifecycle timestamp predates the original lesson apply time.")
            state = "invalid"

        replacement_status = "none"
        if replacement_id:
            if replacement is None:
                replacement_status = "missing"
            else:
                replacement_status = (
                    "active_verified"
                    if replacement.active and verify_memory_provenance(replacement).verified
                    else "present_not_active_or_verified"
                )
        source_apply_id = ""
        applied_at = ""
        if isinstance(record.provenance, dict):
            source_apply_id = str(record.provenance.get("apply_id") or "")
            applied_at = str(record.provenance.get("applied_at") or "")
        restart_safe = bool(
            provenance.verified
            and (
                state == "active"
                or state == "forgotten"
                or (
                    state in {"rejected", "superseded"}
                    and record.superseded_at
                    and record.superseded_reason
                )
            )
        )
        return LearningLifecycleAuditEntry(
            memory_id=record.id,
            state=state,
            active=record.active,
            content_preview=_preview(record.content),
            provenance_status=provenance.status,
            provenance_id=provenance.provenance_id,
            source_apply_id=source_apply_id,
            applied_at=applied_at,
            lifecycle_at=record.superseded_at or "",
            lifecycle_reason=reason,
            replacement_memory_id=replacement_id,
            replacement_status=replacement_status,
            restart_safe=restart_safe,
            issues=_dedupe(issues),
            warnings=_dedupe(warnings),
        )


def format_learning_lifecycle_audit_command(
    command: str,
    *,
    memory_store: MemoryStore | None,
) -> str | None:
    raw = command.strip()
    normalized = " ".join(raw.lower().split())
    prefixes = (
        "/experience learning lifecycle-audit-status",
        "/experience learning lifecycle-history",
        "/experience learning lifecycle-inspect",
        "/experience learning lifecycle-audit-doctor",
    )
    if not any(normalized == prefix or normalized.startswith(prefix + " ") for prefix in prefixes):
        return None
    if any(marker in raw for marker in ("\n", ";", "&&", "||")):
        return _audit_error("Command chaining and multi-command input are not allowed.")
    if memory_store is None:
        return _audit_error("MemoryStore is unavailable from the shared handler.")
    audit = LearningLifecycleTransitionAudit(memory_store)
    try:
        report = audit.inspect()
    except LearningLifecycleAuditError as exc:
        return _audit_error(str(exc))

    if normalized == "/experience learning lifecycle-audit-status":
        return format_learning_lifecycle_audit_status(report)
    if normalized == "/experience learning lifecycle-audit-doctor":
        return format_learning_lifecycle_audit_doctor(report)
    if normalized == "/experience learning lifecycle-history":
        return format_learning_lifecycle_history(report, include_all=False)
    if normalized == "/experience learning lifecycle-history --all":
        return format_learning_lifecycle_history(report, include_all=True)
    if normalized.startswith("/experience learning lifecycle-history "):
        return "Usage: /experience learning lifecycle-history [--all]"
    if normalized == "/experience learning lifecycle-inspect":
        return "Usage: /experience learning lifecycle-inspect <memory_id>"
    identifier = raw[len("/experience learning lifecycle-inspect") :].strip()
    if not identifier or " " in identifier:
        return "Usage: /experience learning lifecycle-inspect <memory_id>"
    entry = next((item for item in report.entries if item.memory_id == identifier), None)
    return format_learning_lifecycle_inspect(entry, identifier=identifier)


def format_learning_lifecycle_audit_status(report: LearningLifecycleAuditReport) -> str:
    return "\n".join(
        [
            "Proto-Mind Learning Lifecycle Audit Status v1",
            f"Status: {report.status}",
            f"mode: {LEARNING_LIFECYCLE_AUDIT_MODE}",
            f"persistent_path: {report.persistent_path}",
            f"learned_lessons: {report.learned_lesson_count}",
            f"active: {report.active_count}",
            f"rejected: {report.rejected_count}",
            f"superseded: {report.superseded_count}",
            f"forgotten: {report.forgotten_count}",
            f"inactive_unclassified: {report.unclassified_count}",
            f"invalid: {report.invalid_count}",
            "Commands: lifecycle-history [--all] | lifecycle-inspect <id> | lifecycle-audit-doctor",
            *_audit_boundary(),
        ]
    )


def format_learning_lifecycle_history(
    report: LearningLifecycleAuditReport,
    *,
    include_all: bool,
) -> str:
    entries = report.entries if include_all else [entry for entry in report.entries if not entry.active]
    lines = [
        "Proto-Mind Learning Lifecycle Durable State View v1",
        f"Status: {report.status}",
        f"showing: {len(entries)}/{len(report.entries)}",
        "Learned lessons:",
    ]
    if not entries:
        lines.append("- none")
    for entry in entries:
        replacement = (
            f" | replacement={entry.replacement_memory_id} ({entry.replacement_status})"
            if entry.replacement_memory_id
            else ""
        )
        lines.append(
            f"- {entry.memory_id} | {entry.state} | lifecycle_at={entry.lifecycle_at or 'none'}"
            f"{replacement} | {entry.content_preview}"
        )
    lines.extend(
        [
            "- This reconstructs current durable state; it is not an append-only event history.",
            *_audit_boundary(),
        ]
    )
    return "\n".join(lines)


def format_learning_lifecycle_inspect(
    entry: LearningLifecycleAuditEntry | None,
    *,
    identifier: str,
) -> str:
    if entry is None:
        return _audit_error(f"Learned lesson {identifier!r} was not found.")
    lines = [
        "Proto-Mind Learning Lifecycle Durable State Inspection v1",
        f"Status: {'ERROR' if entry.issues else 'WARN' if entry.warnings else 'OK'}",
    ]
    lines.extend(f"{key}: {_compact(value)}" for key, value in entry.to_dict().items())
    lines.extend(_audit_boundary())
    return "\n".join(lines)


def format_learning_lifecycle_audit_doctor(report: LearningLifecycleAuditReport) -> str:
    lines = [
        "Proto-Mind Learning Lifecycle Audit Doctor v1",
        f"Status: {report.status}",
        f"mode: {LEARNING_LIFECYCLE_AUDIT_MODE}",
        f"learned_lessons: {report.learned_lesson_count}",
        f"active: {report.active_count}",
        f"rejected: {report.rejected_count}",
        f"superseded: {report.superseded_count}",
        f"forgotten: {report.forgotten_count}",
        f"inactive_unclassified: {report.unclassified_count}",
        f"invalid: {report.invalid_count}",
    ]
    lines.extend(f"- ERROR: {issue}" for issue in report.issues)
    lines.extend(f"- WARN: {warning}" for warning in report.warnings)
    if not report.issues and not report.warnings:
        lines.append(
            "- Provenance, lifecycle fields, timestamps, replacements, and reference acyclicity are healthy."
        )
    lines.extend(_audit_boundary())
    return "\n".join(lines)


def _lifecycle_state(record: MemoryRecord) -> str:
    if record.active:
        return "active"
    if record.superseded_reason == LIFECYCLE_REJECT_REASON:
        return "rejected"
    if record.superseded_reason == LIFECYCLE_SUPERSEDE_REASON:
        return "superseded"
    if record.superseded_reason == OPERATOR_FORGET_REASON:
        return "forgotten"
    return "inactive_unclassified"


def _is_learned_lesson(record: MemoryRecord) -> bool:
    return record.type == "lesson" and record.provenance is not None


def _reference_cycles(records: list[MemoryRecord]) -> list[list[str]]:
    links = {
        record.id: record.superseded_by
        for record in records
        if record.superseded_by
    }
    cycles: list[list[str]] = []
    seen_cycles: set[tuple[str, ...]] = set()
    for start in links:
        path: list[str] = []
        positions: dict[str, int] = {}
        current = start
        while current in links:
            if current in positions:
                cycle = path[positions[current] :] + [current]
                canonical = _canonical_cycle(cycle[:-1])
                if canonical not in seen_cycles:
                    seen_cycles.add(canonical)
                    cycles.append([*canonical, canonical[0]])
                break
            positions[current] = len(path)
            path.append(current)
            current = str(links[current])
    return cycles


def _canonical_cycle(cycle: list[str]) -> tuple[str, ...]:
    rotations = [tuple(cycle[index:] + cycle[:index]) for index in range(len(cycle))]
    return min(rotations)


def _provenance_time(record: MemoryRecord) -> str:
    if not isinstance(record.provenance, dict):
        return ""
    return str(record.provenance.get("applied_at") or "")


def _valid_timestamp(value: str) -> bool:
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return False
    return True


def _timestamp_not_earlier(later: str, earlier: str) -> bool:
    if not _valid_timestamp(later) or not _valid_timestamp(earlier):
        return False
    try:
        return datetime.fromisoformat(later.replace("Z", "+00:00")) >= datetime.fromisoformat(
            earlier.replace("Z", "+00:00")
        )
    except TypeError:
        return False


def _preview(value: str, limit: int = 120) -> str:
    normalized = " ".join(value.split())
    return normalized if len(normalized) <= limit else normalized[: limit - 3] + "..."


def _compact(value: object) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)


def _audit_error(message: str) -> str:
    return "\n".join(
        [
            "Proto-Mind Learning Lifecycle Audit Error",
            "Status: ERROR",
            f"- {message}",
            *_audit_boundary(),
        ]
    )


def _audit_boundary() -> list[str]:
    return [
        "Boundary:",
        "- Read-only reconstruction from persistent learned lessons; no process receipt is invented.",
        "- No lesson, provenance, memory file, skill, Experience event, queue, export, or Context Injection changed.",
        "- No repair, reactivation, rollback, command execution, shell, model/API call, or automatic decision occurred.",
    ]


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))
