from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

from proto_mind.coordinator import Coordinator
from proto_mind.memory_keeper import MemoryKeeper
from proto_mind.memory_provenance import (
    build_learning_lesson_provenance,
    verify_memory_provenance,
)
from proto_mind.memory_store import MemoryStore
from proto_mind.models import MemoryRecord
from proto_mind.observer import Observer
from proto_mind.reasoner import MockReasoner


LESSON_RECALL_BENCHMARK_VERSION = 1
LESSON_RECALL_FIXTURE_TIMESTAMP = "2026-07-19T00:00:00+00:00"
LESSON_RECALL_CASES = (
    (
        "en",
        "As we discussed earlier, what should we do after failed verification?",
    ),
    (
        "ru",
        "Как мы обсуждали, что делать после ошибки проверки provenance?",
    ),
)


@dataclass(frozen=True)
class VerifiedLessonRecallCase:
    language: str
    query: str
    selected_memory_ids: list[str]
    lesson_selected: bool
    trace_provenance_visible: bool
    grounding_status: str
    grounding_provenance_visible: bool
    persistent_bytes_unchanged: bool
    working_bytes_unchanged: bool
    usage_unchanged: bool
    memory_count_unchanged: bool
    passed: bool

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class VerifiedLessonRecallBenchmark:
    status: str
    version: int
    case_count: int
    passed_count: int
    verified_memory_id: str
    verified_provenance_id: str
    invalid_lesson_filtered: bool
    unprovenanced_lesson_filtered: bool
    cases: list[VerifiedLessonRecallCase]
    issues: list[str]
    writes_to_project: bool = False
    retrieval_usage_tracking_enabled: bool = False
    automatic_memory_write: bool = False
    automatic_learning: bool = False

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def run_verified_lesson_recall_benchmark() -> VerifiedLessonRecallBenchmark:
    with TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        store = MemoryStore(root / "working_memory.json", root / "persistent_memory.json")
        verified = _verified_lesson()
        invalid = _invalid_lesson()
        unprovenanced = MemoryRecord(
            id="mem_lesson_unprovenanced",
            content="After failed verification, retry without reviewing provenance.",
            type="lesson",
            importance=1.0,
            source="legacy",
            tags=["verification", "provenance"],
            timestamp=verified.timestamp,
            confidence=0.9,
        )
        store.save_persistent_memory([verified, invalid, unprovenanced])
        provenance_check = verify_memory_provenance(verified)
        baseline_count = len(store.load_persistent_memory())
        cases: list[VerifiedLessonRecallCase] = []
        invalid_filtered = True
        unprovenanced_filtered = True

        for language, query in LESSON_RECALL_CASES:
            before_persistent = store.persistent_path.read_bytes()
            before_working = store.working_path.read_bytes()
            before_records = {record.id: record.to_dict() for record in store.load_persistent_memory()}
            coordinator = Coordinator(
                observer=Observer(),
                memory_keeper=MemoryKeeper(store),
                reasoner=MockReasoner(),
            )
            result = coordinator.handle(query)
            trace = result.retrieval_trace
            selected_ids = [record.id for record in result.retrieved_memory]
            selected_trace = next(
                (
                    candidate
                    for candidate in (trace.candidates if trace else [])
                    if candidate.record_id == verified.id
                ),
                None,
            )
            invalid_trace = next(
                (
                    candidate
                    for candidate in (trace.candidates if trace else [])
                    if candidate.record_id == invalid.id
                ),
                None,
            )
            unprovenanced_trace = next(
                (
                    candidate
                    for candidate in (trace.candidates if trace else [])
                    if candidate.record_id == unprovenanced.id
                ),
                None,
            )
            invalid_filtered = invalid_filtered and bool(
                invalid_trace
                and invalid_trace.filtered_reason == "filtered_unverified_lesson_provenance"
            )
            unprovenanced_filtered = unprovenanced_filtered and bool(
                unprovenanced_trace
                and unprovenanced_trace.filtered_reason
                == "filtered_unverified_lesson_provenance"
            )
            after_records = {record.id: record.to_dict() for record in store.load_persistent_memory()}
            audit = result.grounding_audit
            trace_visible = bool(
                selected_trace
                and selected_trace.selected
                and "provenance" in (selected_trace.why_selected_summary or "")
            )
            grounding_visible = bool(
                audit
                and any(
                    provenance_check.provenance_id in evidence
                    and "provenance=verified" in evidence
                    for evidence in audit.evidence
                )
            )
            case = VerifiedLessonRecallCase(
                language=language,
                query=query,
                selected_memory_ids=selected_ids,
                lesson_selected=verified.id in selected_ids,
                trace_provenance_visible=trace_visible,
                grounding_status=audit.grounding_status if audit else "missing",
                grounding_provenance_visible=grounding_visible,
                persistent_bytes_unchanged=before_persistent == store.persistent_path.read_bytes(),
                working_bytes_unchanged=before_working == store.working_path.read_bytes(),
                usage_unchanged=(
                    before_records[verified.id]["usage_count"]
                    == after_records[verified.id]["usage_count"]
                    and before_records[verified.id]["last_used"]
                    == after_records[verified.id]["last_used"]
                ),
                memory_count_unchanged=len(after_records) == baseline_count,
                passed=False,
            )
            case = VerifiedLessonRecallCase(
                **{
                    **case.to_dict(),
                    "passed": all(
                        (
                            case.lesson_selected,
                            case.trace_provenance_visible,
                            case.grounding_status == "grounded",
                            case.grounding_provenance_visible,
                            case.persistent_bytes_unchanged,
                            case.working_bytes_unchanged,
                            case.usage_unchanged,
                            case.memory_count_unchanged,
                        )
                    ),
                }
            )
            cases.append(case)

    issues: list[str] = []
    if not provenance_check.verified:
        issues.append("Synthetic applied lesson provenance did not verify.")
    if not invalid_filtered:
        issues.append("Tampered lesson was not filtered fail-closed in every case.")
    if not unprovenanced_filtered:
        issues.append("Unprovenanced lesson was not filtered fail-closed in every case.")
    failed_languages = [case.language for case in cases if not case.passed]
    if failed_languages:
        issues.append(f"Recall cases failed: {', '.join(failed_languages)}.")
    passed_count = sum(1 for case in cases if case.passed)
    return VerifiedLessonRecallBenchmark(
        status=(
            "OK"
            if provenance_check.verified
            and invalid_filtered
            and unprovenanced_filtered
            and passed_count == len(LESSON_RECALL_CASES)
            and not issues
            else "ERROR"
        ),
        version=LESSON_RECALL_BENCHMARK_VERSION,
        case_count=len(LESSON_RECALL_CASES),
        passed_count=passed_count,
        verified_memory_id=verified.id,
        verified_provenance_id=provenance_check.provenance_id,
        invalid_lesson_filtered=invalid_filtered,
        unprovenanced_lesson_filtered=unprovenanced_filtered,
        cases=cases,
        issues=issues,
    )


def format_verified_lesson_recall_benchmark(
    report: VerifiedLessonRecallBenchmark | None = None,
) -> str:
    active = report or run_verified_lesson_recall_benchmark()
    lines = [
        "Proto-Mind Verified Lesson Recall Benchmark v1",
        f"Status: {active.status}",
        f"cases: {active.passed_count}/{active.case_count}",
        f"verified_memory_id: {active.verified_memory_id}",
        f"verified_provenance_id: {active.verified_provenance_id}",
        f"invalid_lesson_filtered: {str(active.invalid_lesson_filtered).lower()}",
        f"unprovenanced_lesson_filtered: {str(active.unprovenanced_lesson_filtered).lower()}",
        "Cases:",
    ]
    for case in active.cases:
        lines.append(
            f"- {case.language}: {'PASS' if case.passed else 'FAIL'} | "
            f"selected={case.lesson_selected} | grounding={case.grounding_status} | "
            f"bytes_stable={case.persistent_bytes_unchanged and case.working_bytes_unchanged}"
        )
    lines.extend(f"- ERROR: {issue}" for issue in active.issues)
    lines.extend(
        [
            "Boundary:",
            "- local temporary stores only; no project data/export write",
            "- retrieval usage tracking disabled; usage_count and last_used remain unchanged",
            "- no automatic memory write, learning apply, skill creation, LLM/API call, or Context Injection",
        ]
    )
    return "\n".join(lines)


def _verified_lesson() -> MemoryRecord:
    applied_at = LESSON_RECALL_FIXTURE_TIMESTAMP
    proposal_hash = "a" * 64
    memory_id = f"mem_learn_{proposal_hash[:16]}"
    payload = {
        "schema": "memory.lesson.v1",
        "content": (
            "After failed verification, inspect provenance before retrying. "
            "После ошибки проверки проверь provenance перед повтором."
        ),
        "type": "lesson",
        "importance": 0.85,
        "source": "experience_learning_proposal",
        "tags": ["verification", "provenance", "retry"],
        "confidence": 0.9,
    }
    provenance = build_learning_lesson_provenance(
        memory_id=memory_id,
        applied_at=applied_at,
        proposal_id=f"learnprop_{proposal_hash[:16]}",
        proposal_hash=proposal_hash,
        candidate_id="learncand_verified_recall",
        candidate_hash="b" * 64,
        decision_id="learndec_verified_recall",
        eligibility_receipt_id="learnelig_verified_recall",
        selected_scope_hash="c" * 64,
        proposed_payload=payload,
        evidence_event_ids=["evt_verified_lesson_recall"],
        source_kinds=["correction"],
    )
    return MemoryRecord(
        id=memory_id,
        content=str(payload["content"]),
        type="lesson",
        importance=float(payload["importance"]),
        source=str(payload["source"]),
        tags=list(payload["tags"]),
        timestamp=applied_at,
        confidence=float(payload["confidence"]),
        updated_at=applied_at,
        provenance=provenance,
    )


def _invalid_lesson() -> MemoryRecord:
    record = _verified_lesson()
    record.id = "mem_lesson_tampered"
    record.content = "Failed verification should be ignored without provenance review."
    record.provenance = dict(record.provenance or {})
    record.provenance["memory_id"] = record.id
    return record
