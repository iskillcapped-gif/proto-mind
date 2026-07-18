from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
import re
from typing import Any, Iterable
from uuid import uuid4

from proto_mind.experience_privacy import (
    filter_sensitive_derived_values,
    find_sensitive_preview_categories,
    redact_experience_preview,
)
from proto_mind.models import InteractionResult, MemoryRecord, utc_now_iso


EXPERIENCE_SCHEMA_VERSION = 1
EXPERIENCE_PREVIEW_MAX_CHARS = 160
EXPERIENCE_SELECTED_MEMORY_LIMIT = 5
EXPERIENCE_ENTRY_VERSION = 1
EXPERIENCE_STORE_MAX_EVENTS_WARNING = 10_000
EXPERIENCE_STORE_MAX_BYTES_WARNING = 10 * 1024 * 1024
LIVE_EXPERIENCE_PERSISTENCE_ENABLED = False
LIVE_DATA_DIR = Path(__file__).resolve().parent / "data"
LIVE_EXPERIENCE_LEDGER_PATH = LIVE_DATA_DIR / "experience_ledger.jsonl"

EXPERIENCE_EVENT_TYPES = frozenset(
    {
        "conversation_observed",
        "intent_detected",
        "memory_retrieved",
        "correction_guidance_applied",
        "response_generated",
        "memory_evaluated",
        "memory_recorded",
        "reflection_evaluated",
        "grounding_evaluated",
        "goal_created",
        "plan_created",
        "tool_called",
        "tool_succeeded",
        "tool_failed",
        "user_corrected",
        "task_completed",
        "reflection_created",
        "lesson_candidate_created",
        "memory_promoted",
    }
)

EXPERIENCE_ROOT_EVENT_TYPES = frozenset({"conversation_observed", "goal_created"})

EXPERIENCE_REQUIRED_PAYLOAD_FIELDS: dict[str, frozenset[str]] = {
    "goal_created": frozenset({"goal_id", "title_preview", "priority"}),
    "plan_created": frozenset({"plan_id", "goal_id", "step_count", "plan_preview"}),
    "tool_called": frozenset(
        {"call_id", "capability", "input_preview", "risk", "read_only"}
    ),
    "tool_succeeded": frozenset({"call_id", "output_preview", "verified"}),
    "tool_failed": frozenset(
        {"call_id", "error_type", "error_preview", "retryable"}
    ),
    "user_corrected": frozenset({"correction_preview", "target_event_ids"}),
    "task_completed": frozenset({"task_id", "result_preview", "verified"}),
    "reflection_created": frozenset(
        {"reflection_id", "summary_preview", "lesson_candidate_count"}
    ),
    "lesson_candidate_created": frozenset(
        {"candidate_id", "lesson_preview", "requires_operator_confirmation"}
    ),
    "memory_promoted": frozenset(
        {"memory_id", "memory_type", "evidence_event_ids"}
    ),
}

EXPERIENCE_REQUIRED_SOURCE_TYPES: dict[str, frozenset[str]] = {
    "plan_created": frozenset({"goal_created"}),
    "tool_called": frozenset({"plan_created"}),
    "tool_succeeded": frozenset({"tool_called"}),
    "tool_failed": frozenset({"tool_called"}),
    "user_corrected": frozenset({"tool_failed", "response_generated", "grounding_evaluated"}),
    "task_completed": frozenset({"tool_succeeded"}),
    "reflection_created": frozenset({"task_completed", "tool_failed", "user_corrected"}),
    "lesson_candidate_created": frozenset({"reflection_created"}),
    "memory_promoted": frozenset({"lesson_candidate_created", "memory_recorded"}),
}

FORBIDDEN_PAYLOAD_KEYS = frozenset(
    {
        "full_context",
        "full_prompt",
        "full_response",
        "hidden_prompt",
        "injected_prompt",
        "raw_context",
        "raw_prompt",
        "response",
        "system_prompt",
        "user_input",
    }
)


def compact_preview(value: object, max_chars: int = EXPERIENCE_PREVIEW_MAX_CHARS) -> str:
    return redact_experience_preview(value, max_chars=max_chars).text


@dataclass(frozen=True)
class ExperienceEvent:
    id: str
    created_at: str
    event_type: str
    session_id: str
    turn_id: str
    source: str
    source_event_ids: list[str]
    payload: dict[str, Any]
    confidence: float | None = None
    schema_version: int = EXPERIENCE_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ExperienceDoctorReport:
    status: str
    event_count: int
    provenance_edge_count: int
    event_type_counts: dict[str, int]
    issues: list[str]
    warnings: list[str]
    privacy_boundary: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ExperienceAppendReceipt:
    path: str
    appended_count: int
    total_count: int
    first_sequence: int
    last_sequence: int
    last_entry_hash: str
    mode: str = "temporary_preview_only"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ExperienceStoreDoctorReport:
    status: str
    path: str
    exists: bool
    event_count: int
    file_size: int
    hash_verified_count: int
    issues: list[str]
    warnings: list[str]
    live_persistence_enabled: bool = LIVE_EXPERIENCE_PERSISTENCE_ENABLED

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ExperienceLedgerError(RuntimeError):
    pass


class ExperienceTraceBuilder:
    """Builds compact provenance events without writing or changing the interaction."""

    def __init__(
        self,
        *,
        session_id: str,
        source: str = "coordinator_preview",
        preview_max_chars: int = EXPERIENCE_PREVIEW_MAX_CHARS,
        selected_memory_limit: int = EXPERIENCE_SELECTED_MEMORY_LIMIT,
    ) -> None:
        if not session_id.strip():
            raise ValueError("session_id must not be empty")
        self.session_id = session_id.strip()
        self.source = source.strip() or "coordinator_preview"
        self.preview_max_chars = max(40, min(int(preview_max_chars), EXPERIENCE_PREVIEW_MAX_CHARS))
        self.selected_memory_limit = max(0, min(int(selected_memory_limit), 10))

    def build_turn_events(
        self,
        user_input: str,
        result: InteractionResult,
        *,
        turn_id: str | int,
        trace_id: str | None = None,
        created_at: str | None = None,
    ) -> list[ExperienceEvent]:
        timestamp = created_at or utc_now_iso()
        normalized_turn_id = str(turn_id)
        trace = self._normalize_trace_id(trace_id or uuid4().hex[:12])
        events: list[ExperienceEvent] = []

        def add(
            event_type: str,
            payload: dict[str, Any],
            source_event_ids: Iterable[str] = (),
            confidence: float | None = None,
        ) -> ExperienceEvent:
            event = ExperienceEvent(
                id=f"evt_{trace}_{normalized_turn_id}_{len(events) + 1:02d}_{event_type}",
                created_at=timestamp,
                event_type=event_type,
                session_id=self.session_id,
                turn_id=normalized_turn_id,
                source=self.source,
                source_event_ids=list(source_event_ids),
                payload=payload,
                confidence=confidence,
            )
            events.append(event)
            return event

        observed = add(
            "conversation_observed",
            {
                "input_preview": self._preview(user_input),
                "input_chars": len(user_input),
                "language_hint": "english" if user_input.isascii() else "russian_or_mixed",
            },
        )
        intent = add(
            "intent_detected",
            {
                "query_type": result.observer_state.query_type,
                "needs_memory": result.observer_state.needs_memory,
                "importance_hint": result.observer_state.importance_hint,
                "topic_tags": filter_sensitive_derived_values(
                    list(result.observer_state.topic_tags[:10]),
                    user_input,
                ),
            },
            [observed.id],
        )
        retrieval = add(
            "memory_retrieved",
            self._retrieval_payload(result),
            [intent.id],
        )

        correction = None
        if result.previous_correction_hints:
            correction = add(
                "correction_guidance_applied",
                {
                    "hint_count": len(result.previous_correction_hints),
                    "hint_previews": [
                        self._preview(hint) for hint in result.previous_correction_hints[:3]
                    ],
                },
                [intent.id, retrieval.id],
            )

        response_sources = [observed.id, intent.id, retrieval.id]
        if correction:
            response_sources.append(correction.id)
        response = add(
            "response_generated",
            {
                "response_preview": self._preview(result.response),
                "response_chars": len(result.response),
                "reasoner_backend": result.reasoner_backend,
            },
            response_sources,
        )

        memory = add(
            "memory_evaluated",
            self._memory_payload(result),
            [observed.id, intent.id, response.id],
        )
        if result.memory_summary.stored_record_id:
            add(
                "memory_recorded",
                {
                    "record_id": result.memory_summary.stored_record_id,
                    "record_type": result.memory_summary.stored_record_type,
                    "content_preview": self._preview(result.memory_summary.content),
                    "promoted_record_ids": list(result.memory_summary.promoted_record_ids),
                    "superseded_record_ids": list(result.memory_summary.superseded_record_ids),
                },
                [memory.id],
            )

        add(
            "reflection_evaluated",
            self._reflection_payload(result),
            [response.id, memory.id],
        )
        add(
            "grounding_evaluated",
            self._grounding_payload(result),
            [response.id, retrieval.id, memory.id],
        )
        return events

    def _preview(self, value: object) -> str:
        return compact_preview(value, self.preview_max_chars)

    @staticmethod
    def _normalize_trace_id(value: str) -> str:
        normalized = re.sub(r"[^A-Za-z0-9_-]+", "-", value.strip()).strip("-")
        return normalized[:40] or uuid4().hex[:12]

    def _retrieval_payload(self, result: InteractionResult) -> dict[str, Any]:
        trace = result.retrieval_trace
        candidates = trace.candidates if trace else []
        return {
            "retrieval_performed": trace is not None,
            "query_mode": trace.query_mode if trace else "none",
            "candidate_count": len(candidates),
            "selected_count": len(result.retrieved_memory),
            "selected_records": [
                self._memory_ref(record) for record in result.retrieved_memory[: self.selected_memory_limit]
            ],
        }

    def _memory_ref(self, record: MemoryRecord) -> dict[str, Any]:
        return {
            "id": record.id,
            "type": record.type,
            "source": record.source,
            "active": record.active,
            "content_preview": self._preview(record.content),
        }

    def _memory_payload(self, result: InteractionResult) -> dict[str, Any]:
        summary = result.memory_summary
        return {
            "should_store": summary.should_store,
            "memory_type": summary.memory_type,
            "importance": summary.importance,
            "content_preview": self._preview(summary.content),
            "stored_record_id": summary.stored_record_id,
            "stored_record_type": summary.stored_record_type,
            "promoted_record_ids": list(summary.promoted_record_ids),
            "override_detected": summary.override_detected,
            "superseded_record_ids": list(summary.superseded_record_ids),
        }

    def _reflection_payload(self, result: InteractionResult) -> dict[str, Any]:
        reflection = result.self_reflection
        if reflection is None:
            return {"available": False, "warning_count": 0, "correction_hint_count": 0}
        return {
            "available": True,
            "reflection_needed": reflection.reflection_needed,
            "memory_alignment": reflection.memory_alignment,
            "preference_alignment": reflection.preference_alignment,
            "active_decision_alignment": reflection.active_decision_alignment,
            "unsupported_claims_risk": reflection.unsupported_claims_risk,
            "overall_confidence": reflection.overall_confidence,
            "warning_count": len(reflection.warnings),
            "warning_previews": [self._preview(item) for item in reflection.warnings[:3]],
            "correction_hint_count": len(reflection.correction_hints),
        }

    def _grounding_payload(self, result: InteractionResult) -> dict[str, Any]:
        grounding = result.grounding_audit
        if grounding is None:
            return {"available": False, "warning_count": 0, "unsupported_claim_count": 0}
        return {
            "available": True,
            "grounding_needed": grounding.grounding_needed,
            "grounding_status": grounding.grounding_status,
            "memory_support": grounding.memory_support,
            "active_decision_status": grounding.active_decision_status,
            "superseded_memory_status": grounding.superseded_memory_status,
            "unsupported_claim_count": len(grounding.unsupported_claims),
            "unsupported_claim_previews": [
                self._preview(item) for item in grounding.unsupported_claims[:3]
            ],
            "warning_count": len(grounding.warnings),
            "warning_previews": [self._preview(item) for item in grounding.warnings[:3]],
            "evidence_previews": [self._preview(item) for item in grounding.evidence[:3]],
            "confidence": grounding.confidence,
        }


def inspect_experience_events(events: Iterable[ExperienceEvent | dict[str, Any]]) -> ExperienceDoctorReport:
    normalized = [event.to_dict() if isinstance(event, ExperienceEvent) else dict(event) for event in events]
    issues: list[str] = []
    warnings: list[str] = []
    seen_ids: set[str] = set()
    counts: Counter[str] = Counter()
    provenance_edges = 0

    if not normalized:
        warnings.append("No experience events were supplied; schema is healthy but no trace was inspected.")

    turn_first_types: dict[tuple[str, str], str] = {}
    for index, event in enumerate(normalized, start=1):
        event_id = event.get("id")
        event_type = event.get("event_type")
        session_id = event.get("session_id")
        turn_id = event.get("turn_id")
        payload = event.get("payload")
        source_ids = event.get("source_event_ids")

        if not isinstance(event_id, str) or not event_id:
            issues.append(f"Event {index} has no valid id.")
        elif event_id in seen_ids:
            issues.append(f"Duplicate event id: {event_id}.")

        if event.get("schema_version") != EXPERIENCE_SCHEMA_VERSION:
            issues.append(f"Event {event_id or index} has unsupported schema_version.")
        if event_type not in EXPERIENCE_EVENT_TYPES:
            issues.append(f"Event {event_id or index} has invalid event_type: {event_type!r}.")
        else:
            counts[event_type] += 1
        if not isinstance(session_id, str) or not session_id:
            issues.append(f"Event {event_id or index} has no session_id.")
        if not isinstance(turn_id, str) or not turn_id:
            issues.append(f"Event {event_id or index} has no turn_id.")
        if not isinstance(event.get("source"), str) or not event.get("source"):
            issues.append(f"Event {event_id or index} has no source.")
        if not isinstance(event.get("created_at"), str) or not _valid_timestamp(event.get("created_at")):
            issues.append(f"Event {event_id or index} has invalid created_at.")
        confidence = event.get("confidence")
        if confidence is not None and (
            not isinstance(confidence, (int, float)) or not 0.0 <= float(confidence) <= 1.0
        ):
            issues.append(f"Event {event_id or index} has confidence outside 0..1.")

        key = (str(session_id), str(turn_id))
        turn_first_types.setdefault(key, str(event_type))
        if not isinstance(source_ids, list) or not all(isinstance(item, str) for item in source_ids):
            issues.append(f"Event {event_id or index} has invalid source_event_ids.")
            source_ids = []
        provenance_edges += len(source_ids)
        for source_id in source_ids:
            if source_id not in seen_ids:
                issues.append(
                    f"Event {event_id or index} references missing or later source event {source_id}."
                )
        source_types = {
            previous.get("event_type")
            for previous in normalized[: index - 1]
            if previous.get("id") in source_ids
        }
        required_source_types = EXPERIENCE_REQUIRED_SOURCE_TYPES.get(str(event_type))
        if required_source_types and not source_types.intersection(required_source_types):
            issues.append(
                f"Event {event_id or index} requires provenance from one of: "
                + ", ".join(sorted(required_source_types))
                + "."
            )

        if not isinstance(payload, dict):
            issues.append(f"Event {event_id or index} payload is not an object.")
        else:
            _inspect_payload(payload, event_id or str(index), issues)
            required_fields = EXPERIENCE_REQUIRED_PAYLOAD_FIELDS.get(str(event_type), frozenset())
            missing_payload_fields = sorted(required_fields - set(payload))
            if missing_payload_fields:
                issues.append(
                    f"Event {event_id or index} is missing payload fields: "
                    + ", ".join(missing_payload_fields)
                    + "."
                )

        if event_type == "memory_recorded" and source_ids:
            if "memory_evaluated" not in source_types:
                issues.append(f"Memory event {event_id or index} lacks memory_evaluated provenance.")

        if isinstance(event_id, str) and event_id:
            seen_ids.add(event_id)

    for (session_id, turn_id), event_type in turn_first_types.items():
        if event_type not in EXPERIENCE_ROOT_EVENT_TYPES:
            issues.append(
                f"Turn {session_id}/{turn_id} starts with {event_type}, not an allowed root event."
            )

    status = "ERROR" if issues else "WARN" if warnings else "OK"
    return ExperienceDoctorReport(
        status=status,
        event_count=len(normalized),
        provenance_edge_count=provenance_edges,
        event_type_counts=dict(sorted(counts.items())),
        issues=issues,
        warnings=warnings,
        privacy_boundary=(
            "Deterministically redacted compact previews only (maximum 160 characters); "
            "no full prompt, response, injected context, hidden/system prompt, or persistence."
        ),
    )


def _inspect_payload(payload: dict[str, Any], event_id: str, issues: list[str]) -> None:
    for key, value in payload.items():
        if key in FORBIDDEN_PAYLOAD_KEYS:
            issues.append(f"Event {event_id} contains forbidden payload key {key!r}.")
        if key.endswith("_preview") and isinstance(value, str) and len(value) > EXPERIENCE_PREVIEW_MAX_CHARS:
            issues.append(f"Event {event_id} contains oversized preview {key!r}.")
        if key.endswith("_preview") and isinstance(value, str):
            sensitive = find_sensitive_preview_categories(value)
            if sensitive:
                issues.append(
                    f"Event {event_id} contains unredacted credential-like value in {key!r}: "
                    + ", ".join(sensitive)
                    + "."
                )
        if key.endswith("_previews") and isinstance(value, list):
            if any(isinstance(item, str) and len(item) > EXPERIENCE_PREVIEW_MAX_CHARS for item in value):
                issues.append(f"Event {event_id} contains oversized preview list {key!r}.")
            sensitive = sorted(
                {
                    category
                    for item in value
                    if isinstance(item, str)
                    for category in find_sensitive_preview_categories(item)
                }
            )
            if sensitive:
                issues.append(
                    f"Event {event_id} contains unredacted credential-like value in {key!r}: "
                    + ", ".join(sensitive)
                    + "."
                )
        if isinstance(value, dict):
            _inspect_payload(value, event_id, issues)
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    _inspect_payload(item, event_id, issues)


def _valid_timestamp(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return True


def format_experience_preview(events: Iterable[ExperienceEvent | dict[str, Any]]) -> str:
    event_list = list(events)
    report = inspect_experience_events(event_list)
    lines = [
        "Proto-Mind Experience Ledger Preview v1",
        f"Status: {report.status}",
        "mode: in-memory preview only",
        f"events: {report.event_count}",
        f"provenance_edges: {report.provenance_edge_count}",
        "event_types:",
    ]
    for event_type, count in report.event_type_counts.items():
        lines.append(f"- {event_type}: {count}")
    lines.extend(
        [
            "",
            "Privacy boundary:",
            f"- {report.privacy_boundary}",
            "- No live Experience Ledger file is created by preview mode.",
        ]
    )
    return "\n".join(lines)


def format_experience_doctor(events: Iterable[ExperienceEvent | dict[str, Any]]) -> str:
    report = inspect_experience_events(events)
    lines = [
        "Proto-Mind Experience Ledger Doctor v1",
        f"Status: {report.status}",
        f"events: {report.event_count}",
        f"provenance_edges: {report.provenance_edge_count}",
    ]
    if report.issues:
        lines.append("Issues:")
        lines.extend(f"- ERROR: {issue}" for issue in report.issues)
    if report.warnings:
        lines.append("Warnings:")
        lines.extend(f"- WARN: {warning}" for warning in report.warnings)
    if not report.issues and not report.warnings:
        lines.append("- Event schema, provenance ordering, and privacy limits are valid.")
    lines.extend(["Boundary:", f"- {report.privacy_boundary}"])
    return "\n".join(lines)


class TemporaryExperienceLedgerStore:
    """Atomic append-only preview store that refuses every live data path."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def append_events(
        self,
        events: Iterable[ExperienceEvent | dict[str, Any]],
        *,
        stored_at: str | None = None,
    ) -> ExperienceAppendReceipt:
        self._refuse_live_path()
        batch = [event.to_dict() if isinstance(event, ExperienceEvent) else dict(event) for event in events]
        if not batch:
            raise ExperienceLedgerError("Experience append batch must not be empty.")
        batch_report = inspect_experience_events(batch)
        if batch_report.status != "OK":
            details = "; ".join(batch_report.issues + batch_report.warnings)
            raise ExperienceLedgerError(f"Experience append batch failed validation: {details}")

        current_report = self.doctor()
        if current_report.status == "ERROR":
            raise ExperienceLedgerError(
                "Existing Experience Ledger preview is not healthy; refusing append: "
                + "; ".join(current_report.issues)
            )
        existing = self.read_entries()
        existing_ids = {
            entry.get("event", {}).get("id")
            for entry in existing
            if isinstance(entry.get("event"), dict)
        }
        duplicate_ids = sorted(
            event.get("id") for event in batch if event.get("id") in existing_ids
        )
        if duplicate_ids:
            raise ExperienceLedgerError(
                "Duplicate experience event ids refused: " + ", ".join(duplicate_ids)
            )

        timestamp = stored_at or utc_now_iso()
        if not _valid_timestamp(timestamp):
            raise ExperienceLedgerError("stored_at must be a valid ISO timestamp.")
        previous_hash = existing[-1]["entry_hash"] if existing else "GENESIS"
        first_sequence = len(existing) + 1
        new_entries: list[dict[str, Any]] = []
        for offset, event in enumerate(batch):
            entry = {
                "entry_version": EXPERIENCE_ENTRY_VERSION,
                "sequence": first_sequence + offset,
                "stored_at": timestamp,
                "previous_hash": previous_hash,
                "event": event,
            }
            entry["entry_hash"] = _experience_entry_hash(entry)
            previous_hash = entry["entry_hash"]
            new_entries.append(entry)

        self._atomic_write_entries(existing + new_entries)
        return ExperienceAppendReceipt(
            path=str(self.path),
            appended_count=len(new_entries),
            total_count=len(existing) + len(new_entries),
            first_sequence=first_sequence,
            last_sequence=new_entries[-1]["sequence"],
            last_entry_hash=new_entries[-1]["entry_hash"],
        )

    def read_entries(self) -> list[dict[str, Any]]:
        entries, issues = self._read_entries_with_issues()
        if issues:
            raise ExperienceLedgerError("; ".join(issues))
        return entries

    def doctor(self) -> ExperienceStoreDoctorReport:
        if not self.path.exists():
            return ExperienceStoreDoctorReport(
                status="WARN",
                path=str(self.path),
                exists=False,
                event_count=0,
                file_size=0,
                hash_verified_count=0,
                issues=[],
                warnings=["Temporary Experience Ledger preview file does not exist."],
            )

        entries, issues = self._read_entries_with_issues()
        warnings: list[str] = []
        file_size = self.path.stat().st_size
        verified_hashes = 0
        expected_previous_hash = "GENESIS"
        events: list[dict[str, Any]] = []
        seen_event_ids: set[str] = set()

        for index, entry in enumerate(entries, start=1):
            missing = [
                key
                for key in (
                    "entry_version",
                    "sequence",
                    "stored_at",
                    "previous_hash",
                    "event",
                    "entry_hash",
                )
                if key not in entry
            ]
            if missing:
                issues.append(f"Entry {index} is missing fields: {', '.join(missing)}.")
                continue
            if entry.get("entry_version") != EXPERIENCE_ENTRY_VERSION:
                issues.append(f"Entry {index} has unsupported entry_version.")
            if entry.get("sequence") != index:
                issues.append(f"Entry {index} has non-contiguous sequence {entry.get('sequence')!r}.")
            if not _valid_timestamp(entry.get("stored_at")):
                issues.append(f"Entry {index} has invalid stored_at.")
            if entry.get("previous_hash") != expected_previous_hash:
                issues.append(f"Entry {index} previous_hash does not match the chain.")
            expected_hash = _experience_entry_hash(entry)
            if entry.get("entry_hash") != expected_hash:
                issues.append(f"Entry {index} entry_hash mismatch.")
            else:
                verified_hashes += 1
            expected_previous_hash = str(entry.get("entry_hash") or "")

            event = entry.get("event")
            if isinstance(event, dict):
                event_id = event.get("id")
                if event_id in seen_event_ids:
                    issues.append(f"Duplicate stored experience event id: {event_id}.")
                if isinstance(event_id, str):
                    seen_event_ids.add(event_id)
                events.append(event)
            else:
                issues.append(f"Entry {index} event is not an object.")

        if events:
            event_report = inspect_experience_events(events)
            issues.extend(event_report.issues)
            warnings.extend(event_report.warnings)
        else:
            warnings.append("Temporary Experience Ledger preview contains no events.")
        if len(entries) > EXPERIENCE_STORE_MAX_EVENTS_WARNING:
            warnings.append(
                f"Event count {len(entries)} exceeds preview threshold "
                f"{EXPERIENCE_STORE_MAX_EVENTS_WARNING}; no automatic retention is performed."
            )
        if file_size > EXPERIENCE_STORE_MAX_BYTES_WARNING:
            warnings.append(
                f"File size {file_size} exceeds preview threshold "
                f"{EXPERIENCE_STORE_MAX_BYTES_WARNING}; no automatic compaction is performed."
            )

        status = "ERROR" if issues else "WARN" if warnings else "OK"
        return ExperienceStoreDoctorReport(
            status=status,
            path=str(self.path),
            exists=True,
            event_count=len(entries),
            file_size=file_size,
            hash_verified_count=verified_hashes,
            issues=issues,
            warnings=warnings,
        )

    def _read_entries_with_issues(self) -> tuple[list[dict[str, Any]], list[str]]:
        if not self.path.exists():
            return [], []
        entries: list[dict[str, Any]] = []
        issues: list[str] = []
        try:
            lines = self.path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeError) as exc:
            return [], [f"Experience Ledger preview is unreadable: {exc}."]
        for line_number, line in enumerate(lines, start=1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                issues.append(f"Malformed JSONL at line {line_number}: {exc.msg}.")
                continue
            if not isinstance(value, dict):
                issues.append(f"JSONL line {line_number} root is not an object.")
                continue
            entries.append(value)
        return entries, issues

    def _atomic_write_entries(self, entries: list[dict[str, Any]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self.path.with_name(f".{self.path.name}.{uuid4().hex}.tmp")
        payload = "".join(
            json.dumps(entry, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
            for entry in entries
        )
        try:
            with temp_path.open("w", encoding="utf-8") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            temp_path.replace(self.path)
        finally:
            if temp_path.exists():
                temp_path.unlink()

    def _refuse_live_path(self) -> None:
        try:
            inside_live_data = self.path.resolve().is_relative_to(LIVE_DATA_DIR.resolve())
        except OSError:
            inside_live_data = False
        if inside_live_data and not LIVE_EXPERIENCE_PERSISTENCE_ENABLED:
            raise ExperienceLedgerError(
                "Live Experience Ledger persistence is disabled in v3.2b; use an isolated "
                "temporary path for preview verification."
            )


def _experience_entry_hash(entry: dict[str, Any]) -> str:
    hash_payload = {key: value for key, value in entry.items() if key != "entry_hash"}
    canonical = json.dumps(
        hash_payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def format_experience_persistence_policy() -> str:
    return "\n".join(
        [
            "Proto-Mind Experience Ledger Persistence Policy v1",
            "Status: PREVIEW_ONLY",
            "live_persistence_enabled: false",
            "allowed_path_scope: isolated temporary paths only",
            "write_strategy: validate batch -> verify existing chain -> atomic rewrite append",
            "integrity: contiguous sequence + SHA-256 previous_hash chain",
            "redaction: deterministic credential filtering before compact previews <= 160 chars; "
            "forbidden prompt/context payload keys",
            "retention: no automatic deletion, truncation, compaction, or migration",
            f"warning_thresholds: events>{EXPERIENCE_STORE_MAX_EVENTS_WARNING}; "
            f"bytes>{EXPERIENCE_STORE_MAX_BYTES_WARNING}",
            "live Coordinator hook: absent",
            "session log integration: absent",
        ]
    )


def format_experience_store_doctor(store: TemporaryExperienceLedgerStore) -> str:
    report = store.doctor()
    lines = [
        "Proto-Mind Temporary Experience Store Doctor v1",
        f"Status: {report.status}",
        f"path: {report.path}",
        f"exists: {str(report.exists).lower()}",
        f"events: {report.event_count}",
        f"file_size: {report.file_size}",
        f"hash_verified: {report.hash_verified_count}/{report.event_count}",
        "live_persistence_enabled: false",
    ]
    if report.issues:
        lines.extend(f"- ERROR: {issue}" for issue in report.issues)
    if report.warnings:
        lines.extend(f"- WARN: {warning}" for warning in report.warnings)
    if not report.issues and not report.warnings:
        lines.append("- JSONL shape, event provenance, sequence, and hash chain are valid.")
    lines.append("- Doctor is read-only; no repair, retention, or migration is performed.")
    return "\n".join(lines)


def _example_events() -> list[ExperienceEvent]:
    created_at = datetime(2026, 1, 1, tzinfo=UTC).isoformat()
    observed = ExperienceEvent(
        id="evt_example_1_01_conversation_observed",
        created_at=created_at,
        event_type="conversation_observed",
        session_id="schema-example",
        turn_id="1",
        source="schema_example",
        source_event_ids=[],
        payload={"input_preview": "Продолжим Proto-Mind.", "input_chars": 22},
    )
    intent = ExperienceEvent(
        id="evt_example_1_02_intent_detected",
        created_at=created_at,
        event_type="intent_detected",
        session_id="schema-example",
        turn_id="1",
        source="schema_example",
        source_event_ids=[observed.id],
        payload={"query_type": "continuation", "needs_memory": True},
    )
    return [observed, intent]


def main() -> int:
    events = _example_events()
    print(format_experience_persistence_policy())
    print()
    print(format_experience_preview(events))
    print()
    print(format_experience_doctor(events))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
