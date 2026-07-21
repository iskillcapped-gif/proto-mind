from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Iterable

from proto_mind.coordinator import Coordinator
from proto_mind.experience_explainability import ExperienceTraceIndex
from proto_mind.experience_ledger import ExperienceEvent, ExperienceTraceBuilder
from proto_mind.memory_keeper import MemoryKeeper
from proto_mind.memory_provenance import (
    build_learning_lesson_provenance,
    verify_memory_provenance,
)
from proto_mind.memory_store import MemoryStore
from proto_mind.models import MemoryRecord
from proto_mind.observer import Observer
from proto_mind.reasoner import MockReasoner


LEARNING_OUTCOME_REVIEW_VERSION = 1
LEARNING_OUTCOME_MODE = "read_only_exact_provenance_outcome_review"
LEARNING_OUTCOME_STATUSES = frozenset(
    {
        "KEEP_CANDIDATE",
        "SUPERSEDE_CANDIDATE",
        "REJECT_CANDIDATE",
        "NEEDS_MORE_EVIDENCE",
        "NOT_FOUND",
        "ERROR",
    }
)


@dataclass(frozen=True)
class LearningOutcomeSignal:
    event_id: str
    event_type: str
    created_at: str
    signal: str
    reason: str
    replacement_memory_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class LearningOutcomeReview:
    status: str
    lesson_memory_id: str
    provenance_id: str
    applied_at: str
    trace_status: str
    matching_retrieval_count: int
    later_evidence_count: int
    selected_signal_id: str
    replacement_memory_id: str
    signals: list[LearningOutcomeSignal]
    checks: dict[str, bool]
    issues: list[str]
    warnings: list[str]
    mutation_performed: bool = False
    automatic_apply_allowed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class LearningOutcomeDoctorReport:
    status: str
    event_count: int
    lesson_count: int
    verified_lesson_count: int
    reviewable_lesson_count: int
    issues: list[str]
    warnings: list[str]


@dataclass(frozen=True)
class LearningOutcomeBenchmarkReport:
    status: str
    keep_status: str
    reject_status: str
    supersede_status: str
    insufficient_status: str
    persistent_bytes_unchanged: bool
    working_bytes_unchanged: bool
    checks: dict[str, bool]
    failed_checks: list[str]
    boundary: str


class LearningOutcomeReviewer:
    """Reviews exact later evidence without changing a lesson or its source trace."""

    def __init__(
        self,
        events: Iterable[ExperienceEvent | dict[str, Any]],
        records: Iterable[MemoryRecord],
    ) -> None:
        self.events = [
            event.to_dict() if isinstance(event, ExperienceEvent) else deepcopy(dict(event))
            for event in events
        ]
        self.records = list(records)
        self.index = ExperienceTraceIndex(self.events)
        self.trace_report = self.index.doctor()
        self._records_by_id = {record.id: record for record in self.records}
        self._event_order = {
            str(event.get("id") or ""): position
            for position, event in enumerate(self.events)
        }

    def review(self, memory_id: str) -> LearningOutcomeReview:
        record = self._records_by_id.get(memory_id)
        checks = {
            "memory_found": record is not None,
            "lesson_type": bool(record and record.type == "lesson"),
            "durable_provenance_verified": False,
            "experience_trace_valid": self.trace_report.status != "ERROR",
            "later_exact_retrieval_found": False,
            "decisive_signal_found": False,
        }
        if record is None:
            return self._result(
                status="NOT_FOUND",
                memory_id=memory_id,
                checks=checks,
                issues=["Memory record was not found."],
            )
        provenance = verify_memory_provenance(record)
        checks["durable_provenance_verified"] = provenance.verified
        if record.type != "lesson" or not provenance.verified:
            issues = list(provenance.issues)
            if record.type != "lesson":
                issues.insert(0, "Memory record is not a learned lesson.")
            if not issues:
                issues.extend(provenance.warnings or ["Durable lesson provenance is unavailable."])
            return self._result(
                status="ERROR",
                memory_id=record.id,
                provenance_id=provenance.provenance_id,
                applied_at=_provenance_applied_at(record),
                checks=checks,
                issues=issues,
            )
        if self.trace_report.status == "ERROR":
            return self._result(
                status="ERROR",
                memory_id=record.id,
                provenance_id=provenance.provenance_id,
                applied_at=_provenance_applied_at(record),
                checks=checks,
                issues=list(self.trace_report.issues),
                warnings=list(self.trace_report.warnings),
            )

        applied_at = _provenance_applied_at(record)
        retrieval_ids = {
            str(event.get("id"))
            for event in self.events
            if event.get("event_type") == "memory_retrieved"
            and _event_is_later(event, applied_at)
            and _retrieval_selected_memory(event, record.id)
        }
        checks["later_exact_retrieval_found"] = bool(retrieval_ids)
        later_descendants = [
            event
            for event in self.events
            if _event_is_later(event, applied_at)
            and retrieval_ids.intersection(self._lineage_ids(str(event.get("id") or "")))
        ]
        correction_ids = {
            str(event.get("id"))
            for event in later_descendants
            if event.get("event_type") == "user_corrected"
        }
        signals: list[LearningOutcomeSignal] = []
        warnings: list[str] = list(self.trace_report.warnings)

        for event in later_descendants:
            event_id = str(event.get("id") or "")
            event_type = str(event.get("event_type") or "")
            payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
            if event_type == "grounding_evaluated" and _grounding_is_clean(payload):
                if not self._has_correction_descendant(event_id, correction_ids):
                    signals.append(
                        LearningOutcomeSignal(
                            event_id=event_id,
                            event_type=event_type,
                            created_at=str(event.get("created_at") or ""),
                            signal="KEEP_CANDIDATE",
                            reason="A later exact lesson retrieval produced clean grounded evidence without correction.",
                        )
                    )
            elif event_type == "user_corrected":
                signals.append(
                    LearningOutcomeSignal(
                        event_id=event_id,
                        event_type=event_type,
                        created_at=str(event.get("created_at") or ""),
                        signal="REJECT_CANDIDATE",
                        reason="A later explicit operator correction descends from the lesson retrieval.",
                    )
                )
            elif event_type == "memory_promoted" and correction_ids.intersection(
                self._lineage_ids(event_id)
            ):
                replacement_id = str(payload.get("memory_id") or "")
                replacement = self._records_by_id.get(replacement_id)
                replacement_check = (
                    verify_memory_provenance(replacement) if replacement is not None else None
                )
                if (
                    replacement is not None
                    and replacement.id != record.id
                    and replacement.active
                    and replacement_check is not None
                    and replacement_check.verified
                    and _event_is_later(
                        {"created_at": _provenance_applied_at(replacement)},
                        applied_at,
                    )
                ):
                    signals.append(
                        LearningOutcomeSignal(
                            event_id=event_id,
                            event_type=event_type,
                            created_at=str(event.get("created_at") or ""),
                            signal="SUPERSEDE_CANDIDATE",
                            reason=(
                                "A correction lineage points to a newer active lesson with verified "
                                "durable provenance."
                            ),
                            replacement_memory_id=replacement.id,
                        )
                    )
                else:
                    warnings.append(
                        f"Promotion event {event_id} did not resolve to a newer active verified lesson."
                    )

        signals.sort(key=lambda item: self._event_order.get(item.event_id, -1))
        selected = signals[-1] if signals else None
        checks["decisive_signal_found"] = selected is not None
        if selected is None:
            if not retrieval_ids:
                warnings.append("No later Experience retrieval selected this exact lesson id.")
            elif later_descendants:
                warnings.append("Later evidence was present but did not satisfy a decisive outcome contract.")
            return self._result(
                status="NEEDS_MORE_EVIDENCE",
                memory_id=record.id,
                provenance_id=provenance.provenance_id,
                applied_at=applied_at,
                trace_status=self.trace_report.status,
                matching_retrieval_count=len(retrieval_ids),
                later_evidence_count=len(later_descendants),
                signals=signals,
                checks=checks,
                warnings=warnings,
            )
        return self._result(
            status=selected.signal,
            memory_id=record.id,
            provenance_id=provenance.provenance_id,
            applied_at=applied_at,
            trace_status=self.trace_report.status,
            matching_retrieval_count=len(retrieval_ids),
            later_evidence_count=len(later_descendants),
            selected_signal_id=selected.event_id,
            replacement_memory_id=selected.replacement_memory_id,
            signals=signals,
            checks=checks,
            warnings=warnings,
        )

    def doctor(self) -> LearningOutcomeDoctorReport:
        issues = list(self.trace_report.issues)
        warnings = list(self.trace_report.warnings)
        ids = [record.id for record in self.records]
        if len(ids) != len(set(ids)):
            issues.append("Memory snapshot contains duplicate ids.")
        lessons = [record for record in self.records if record.type == "lesson"]
        verified = [record for record in lessons if verify_memory_provenance(record).verified]
        for record in lessons:
            if not verify_memory_provenance(record).verified:
                issues.append(f"Lesson {record.id} has invalid or unavailable durable provenance.")
        reviewable = 0
        if not issues:
            for record in verified:
                if self.review(record.id).matching_retrieval_count:
                    reviewable += 1
        if verified and not reviewable:
            warnings.append("Verified lessons exist, but no later exact retrieval evidence is reviewable.")
        status = "ERROR" if issues else "WARN" if warnings else "OK"
        return LearningOutcomeDoctorReport(
            status=status,
            event_count=len(self.events),
            lesson_count=len(lessons),
            verified_lesson_count=len(verified),
            reviewable_lesson_count=reviewable,
            issues=issues,
            warnings=warnings,
        )

    def _lineage_ids(self, event_id: str) -> set[str]:
        explanation = self.index.explain(event_id)
        return set(explanation.lineage_event_ids if explanation else [])

    def _has_correction_descendant(self, event_id: str, correction_ids: set[str]) -> bool:
        return any(event_id in self._lineage_ids(correction_id) for correction_id in correction_ids)

    def _result(
        self,
        *,
        status: str,
        memory_id: str,
        provenance_id: str = "",
        applied_at: str = "",
        trace_status: str | None = None,
        matching_retrieval_count: int = 0,
        later_evidence_count: int = 0,
        selected_signal_id: str = "",
        replacement_memory_id: str = "",
        signals: list[LearningOutcomeSignal] | None = None,
        checks: dict[str, bool],
        issues: list[str] | None = None,
        warnings: list[str] | None = None,
    ) -> LearningOutcomeReview:
        return LearningOutcomeReview(
            status=status,
            lesson_memory_id=memory_id,
            provenance_id=provenance_id,
            applied_at=applied_at,
            trace_status=trace_status or self.trace_report.status,
            matching_retrieval_count=matching_retrieval_count,
            later_evidence_count=later_evidence_count,
            selected_signal_id=selected_signal_id,
            replacement_memory_id=replacement_memory_id,
            signals=list(signals or []),
            checks=checks,
            issues=list(issues or []),
            warnings=list(dict.fromkeys(warnings or [])),
        )


def format_learning_outcome_command(
    command: str,
    *,
    events: Iterable[ExperienceEvent | dict[str, Any]],
    memory_store: MemoryStore | None,
) -> str | None:
    raw = command.strip()
    normalized = " ".join(raw.lower().split())
    prefixes = (
        "/experience learning outcome-review",
        "/experience learning outcome-doctor",
    )
    if not any(normalized == prefix or normalized.startswith(prefix + " ") for prefix in prefixes):
        return None
    if any(marker in raw for marker in ("\n", ";", "&&", "||")):
        return _outcome_error("Command chaining and multi-command input are not allowed.")
    if memory_store is None:
        return _outcome_error("MemoryStore is unavailable from the shared handler.")
    try:
        records = memory_store.load_working_memory() + memory_store.load_persistent_memory()
    except (OSError, TypeError, ValueError) as exc:
        return _outcome_error(f"Memory store is unreadable: {exc}")
    reviewer = LearningOutcomeReviewer(events, records)
    if normalized == "/experience learning outcome-doctor":
        return format_learning_outcome_doctor(reviewer.doctor())
    if normalized == "/experience learning outcome-review":
        return "Usage: /experience learning outcome-review <memory_id>"
    parts = raw.split()
    if len(parts) != 4:
        return "Usage: /experience learning outcome-review <memory_id>"
    return format_learning_outcome_review(reviewer.review(parts[3]))


def format_learning_outcome_review(review: LearningOutcomeReview) -> str:
    lines = [
        "Proto-Mind Learning Outcome Review v1",
        f"Status: {review.status}",
        f"lesson_memory_id: {review.lesson_memory_id or 'missing'}",
        f"provenance_id: {review.provenance_id or 'unavailable'}",
        f"applied_at: {review.applied_at or 'unavailable'}",
        f"trace_status: {review.trace_status}",
        f"matching_later_retrievals: {review.matching_retrieval_count}",
        f"later_evidence_events: {review.later_evidence_count}",
        f"selected_signal_id: {review.selected_signal_id or 'none'}",
        f"replacement_memory_id: {review.replacement_memory_id or 'none'}",
        "Checks:",
    ]
    lines.extend(f"- {name}: {str(value).lower()}" for name, value in review.checks.items())
    lines.append("Outcome signals:")
    if not review.signals:
        lines.append("- none")
    for signal in review.signals:
        replacement = (
            f" | replacement={signal.replacement_memory_id}"
            if signal.replacement_memory_id
            else ""
        )
        lines.append(
            f"- {signal.signal} | {signal.event_type} ({signal.event_id}){replacement}: "
            f"{signal.reason}"
        )
    lines.extend(f"- ERROR: {issue}" for issue in review.issues)
    lines.extend(f"- WARN: {warning}" for warning in review.warnings)
    lines.extend(["Suggested manual review:", *_outcome_suggestion(review), *_outcome_boundary()])
    return "\n".join(lines)


def format_learning_outcome_doctor(report: LearningOutcomeDoctorReport) -> str:
    lines = [
        "Proto-Mind Learning Outcome Review Doctor v1",
        f"Status: {report.status}",
        f"mode: {LEARNING_OUTCOME_MODE}",
        f"events: {report.event_count}",
        f"lessons: {report.lesson_count}",
        f"verified_lessons: {report.verified_lesson_count}",
        f"reviewable_lessons: {report.reviewable_lesson_count}",
    ]
    lines.extend(f"- ERROR: {issue}" for issue in report.issues)
    lines.extend(f"- WARN: {warning}" for warning in report.warnings)
    if not report.issues and not report.warnings:
        lines.append("- Provenance, trace, exact-id linkage, and no-mutation boundaries are healthy.")
    lines.extend(_outcome_boundary())
    return "\n".join(lines)


def run_learning_outcome_benchmark() -> LearningOutcomeBenchmarkReport:
    with TemporaryDirectory(prefix="proto-mind-learning-outcome-") as temp_dir:
        root = Path(temp_dir)
        old = _fixture_lesson(
            memory_id="mem_learn_outcome_old",
            content="Inspect provenance before retrying a failed verification.",
            applied_at="2026-07-19T00:00:00+00:00",
            digest_char="a",
        )
        replacement = _fixture_lesson(
            memory_id="mem_learn_outcome_new",
            content="Inspect provenance and isolate the failed check before retrying.",
            applied_at="2026-07-20T00:00:00+00:00",
            digest_char="b",
        )
        store = MemoryStore(root / "working.json", root / "persistent.json")
        store.save_persistent_memory([old])
        base_events = _grounded_recall_events(old, store)
        store.save_persistent_memory([old, replacement])
        before_persistent = store.persistent_path.read_bytes()
        before_working = store.working_path.read_bytes()
        correction = _correction_event(base_events)
        reject_events = [*base_events, correction]
        supersede_events = [
            *reject_events,
            *_replacement_events(correction, replacement.id),
        ]
        records = store.load_persistent_memory()
        keep = LearningOutcomeReviewer(base_events, records).review(old.id)
        reject = LearningOutcomeReviewer(reject_events, records).review(old.id)
        supersede = LearningOutcomeReviewer(supersede_events, records).review(old.id)
        unsafe_replacement = MemoryRecord(
            id=replacement.id,
            content=replacement.content,
            type="lesson",
            importance=replacement.importance,
            source="legacy",
        )
        unsafe_supersede = LearningOutcomeReviewer(
            supersede_events,
            [old, unsafe_replacement],
        ).review(old.id)
        insufficient = LearningOutcomeReviewer([], records).review(old.id)
        persistent_unchanged = before_persistent == store.persistent_path.read_bytes()
        working_unchanged = before_working == store.working_path.read_bytes()

    checks = {
        "keep_candidate_from_clean_grounded_reuse": keep.status == "KEEP_CANDIDATE",
        "reject_candidate_from_explicit_correction": reject.status == "REJECT_CANDIDATE",
        "supersede_candidate_requires_verified_replacement": (
            supersede.status == "SUPERSEDE_CANDIDATE"
            and supersede.replacement_memory_id == replacement.id
        ),
        "unverified_replacement_cannot_supersede": (
            unsafe_supersede.status == "REJECT_CANDIDATE"
            and not unsafe_supersede.replacement_memory_id
        ),
        "no_evidence_remains_inconclusive": insufficient.status == "NEEDS_MORE_EVIDENCE",
        "persistent_bytes_unchanged": persistent_unchanged,
        "working_bytes_unchanged": working_unchanged,
        "all_reviews_non_mutating": all(
            not review.mutation_performed and not review.automatic_apply_allowed
            for review in (keep, reject, supersede, insufficient)
        ),
    }
    failed = [name for name, passed in checks.items() if not passed]
    return LearningOutcomeBenchmarkReport(
        status="OK" if not failed else "ERROR",
        keep_status=keep.status,
        reject_status=reject.status,
        supersede_status=supersede.status,
        insufficient_status=insufficient.status,
        persistent_bytes_unchanged=persistent_unchanged,
        working_bytes_unchanged=working_unchanged,
        checks=checks,
        failed_checks=failed,
        boundary=(
            "Temporary stores and compact typed evidence only; no lesson mutation, apply, "
            "promotion, capture, export, Context Injection, or LLM/API call."
        ),
    )


def format_learning_outcome_benchmark(
    report: LearningOutcomeBenchmarkReport | None = None,
) -> str:
    active = report or run_learning_outcome_benchmark()
    lines = [
        "Proto-Mind Learning Outcome Review Benchmark v1",
        f"Status: {active.status}",
        f"keep_case: {active.keep_status}",
        f"reject_case: {active.reject_status}",
        f"supersede_case: {active.supersede_status}",
        f"insufficient_case: {active.insufficient_status}",
        "Checks:",
    ]
    lines.extend(
        f"- [{'PASS' if passed else 'FAIL'}] {name}"
        for name, passed in active.checks.items()
    )
    lines.extend(["Boundary:", f"- {active.boundary}"])
    return "\n".join(lines)


def _grounded_recall_events(record: MemoryRecord, store: MemoryStore) -> list[ExperienceEvent]:
    coordinator = Coordinator(
        observer=Observer(),
        memory_keeper=MemoryKeeper(store),
        reasoner=MockReasoner(),
    )
    query = "As we discussed earlier, what should we do after failed verification?"
    result = coordinator.handle(query)
    return ExperienceTraceBuilder(
        session_id="learning-outcome-benchmark",
        source="learning_outcome_benchmark",
    ).build_turn_events(
        query,
        result,
        turn_id="1",
        trace_id="outcome-review",
        created_at="2026-07-21T00:00:00+00:00",
    )


def _correction_event(events: list[ExperienceEvent]) -> ExperienceEvent:
    grounding = next(event for event in events if event.event_type == "grounding_evaluated")
    return ExperienceEvent(
        id="evt_outcome-review_1_08_user_corrected",
        created_at=_event_time_offset(grounding.created_at, minutes=1),
        event_type="user_corrected",
        session_id=grounding.session_id,
        turn_id=grounding.turn_id,
        source="learning_outcome_benchmark",
        source_event_ids=[grounding.id],
        payload={
            "correction_preview": "The prior lesson needs correction after the verified result.",
            "target_event_ids": [grounding.id],
        },
        confidence=1.0,
    )


def _replacement_events(
    correction: ExperienceEvent,
    replacement_memory_id: str,
) -> list[ExperienceEvent]:
    reflection = ExperienceEvent(
        id="evt_outcome-review_1_09_reflection_created",
        created_at=_event_time_offset(correction.created_at, minutes=1),
        event_type="reflection_created",
        session_id=correction.session_id,
        turn_id=correction.turn_id,
        source="learning_outcome_benchmark",
        source_event_ids=[correction.id],
        payload={
            "reflection_id": "reflection_outcome_review",
            "summary_preview": "The correction produced a narrower replacement lesson.",
            "lesson_candidate_count": 1,
        },
        confidence=0.9,
    )
    lesson = ExperienceEvent(
        id="evt_outcome-review_1_10_lesson_candidate_created",
        created_at=_event_time_offset(correction.created_at, minutes=2),
        event_type="lesson_candidate_created",
        session_id=correction.session_id,
        turn_id=correction.turn_id,
        source="learning_outcome_benchmark",
        source_event_ids=[reflection.id],
        payload={
            "candidate_id": "lesson_outcome_replacement",
            "lesson_preview": "Inspect provenance and isolate the failed check before retrying.",
            "requires_operator_confirmation": True,
        },
        confidence=0.9,
    )
    promotion = ExperienceEvent(
        id="evt_outcome-review_1_11_memory_promoted",
        created_at=_event_time_offset(correction.created_at, minutes=3),
        event_type="memory_promoted",
        session_id=correction.session_id,
        turn_id=correction.turn_id,
        source="learning_outcome_benchmark",
        source_event_ids=[lesson.id],
        payload={
            "memory_id": replacement_memory_id,
            "memory_type": "lesson",
            "evidence_event_ids": [lesson.id],
            "operator_confirmation_required": True,
            "promotion_performed_by_builder": False,
        },
        confidence=0.9,
    )
    return [reflection, lesson, promotion]


def _event_time_offset(value: str, *, minutes: int) -> str:
    base = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return (base + timedelta(minutes=minutes)).isoformat()


def _fixture_lesson(
    *,
    memory_id: str,
    content: str,
    applied_at: str,
    digest_char: str,
) -> MemoryRecord:
    proposal_hash = digest_char * 64
    payload = {
        "schema": "memory.lesson.v1",
        "content": content,
        "type": "lesson",
        "importance": 0.9,
        "source": "experience_learning_proposal",
        "tags": ["verification", "provenance", "retry"],
        "confidence": 0.9,
    }
    provenance = build_learning_lesson_provenance(
        memory_id=memory_id,
        applied_at=applied_at,
        proposal_id=f"learnprop_{proposal_hash[:16]}",
        proposal_hash=proposal_hash,
        candidate_id=f"learncand_outcome_{digest_char}",
        candidate_hash=("c" if digest_char == "a" else "d") * 64,
        decision_id=f"learndec_outcome_{digest_char}",
        eligibility_receipt_id=f"learnelig_outcome_{digest_char}",
        selected_scope_hash=("e" if digest_char == "a" else "f") * 64,
        proposed_payload=payload,
        evidence_event_ids=[f"evt_outcome_source_{digest_char}"],
        source_kinds=["correction"],
    )
    return MemoryRecord(
        id=memory_id,
        content=content,
        type="lesson",
        importance=0.9,
        source="experience_learning_proposal",
        tags=["verification", "provenance", "retry"],
        timestamp=applied_at,
        confidence=0.9,
        updated_at=applied_at,
        provenance=provenance,
    )


def _retrieval_selected_memory(event: dict[str, Any], memory_id: str) -> bool:
    payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
    selected = payload.get("selected_records")
    return isinstance(selected, list) and any(
        isinstance(item, dict) and item.get("id") == memory_id for item in selected
    )


def _grounding_is_clean(payload: dict[str, Any]) -> bool:
    return (
        payload.get("available") is True
        and payload.get("grounding_status") == "grounded"
        and int(payload.get("warning_count") or 0) == 0
        and int(payload.get("unsupported_claim_count") or 0) == 0
    )


def _provenance_applied_at(record: MemoryRecord) -> str:
    provenance = record.provenance if isinstance(record.provenance, dict) else {}
    return str(provenance.get("applied_at") or "")


def _event_is_later(event: dict[str, Any], applied_at: str) -> bool:
    try:
        return _parse_timestamp(str(event.get("created_at") or "")) > _parse_timestamp(applied_at)
    except ValueError:
        return False


def _parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _outcome_suggestion(review: LearningOutcomeReview) -> list[str]:
    if review.status == "KEEP_CANDIDATE":
        return [f"- Inspect provenance: /memory why {review.lesson_memory_id}", "- Leave the lesson unchanged unless later evidence disagrees."]
    if review.status == "SUPERSEDE_CANDIDATE":
        return [
            f"- Inspect current lesson: /memory why {review.lesson_memory_id}",
            f"- Inspect replacement: /memory why {review.replacement_memory_id}",
            "- Any supersede mutation requires a separate operator-reviewed milestone.",
        ]
    if review.status == "REJECT_CANDIDATE":
        return [
            f"- Inspect provenance first: /memory why {review.lesson_memory_id}",
            f"- Optional manual rollback after review: /memory forget {review.lesson_memory_id}",
        ]
    return ["- Capture or inspect later verified evidence before deciding."]


def _outcome_boundary() -> list[str]:
    return [
        "Boundary:",
        "- Candidate classification only; it is not truth, authorization, or an automatic decision.",
        "- No memory/skill/event/store mutation, apply, promotion, capture, model call, or command execution occurred.",
    ]


def _outcome_error(message: str) -> str:
    return "\n".join(
        [
            "Proto-Mind Learning Outcome Review v1",
            "Status: ERROR",
            f"- ERROR: {message}",
            *_outcome_boundary(),
        ]
    )


def main() -> int:
    report = run_learning_outcome_benchmark()
    print(format_learning_outcome_benchmark(report))
    return 0 if report.status == "OK" else 1


if __name__ == "__main__":
    raise SystemExit(main())
