from __future__ import annotations

from collections import Counter
from copy import deepcopy
from dataclasses import asdict, dataclass
import hashlib
import json
from threading import RLock
from typing import Any, Iterable

from proto_mind.experience_ledger import ExperienceEvent
from proto_mind.experience_learning_outcome import (
    LearningOutcomeReview,
    LearningOutcomeReviewer,
)
from proto_mind.memory_store import MemoryStore
from proto_mind.models import MemoryRecord, utc_now_iso


LEARNING_LIFECYCLE_VERSION = 1
LEARNING_LIFECYCLE_MODE = "operator_confirmed_process_memory_outcome_decision"
LEARNING_LIFECYCLE_MAX_RECEIPTS = 32
LEARNING_LIFECYCLE_DECISIONS = frozenset({"keep", "reject", "supersede"})
OUTCOME_DECISIONS = {
    "KEEP_CANDIDATE": "keep",
    "REJECT_CANDIDATE": "reject",
    "SUPERSEDE_CANDIDATE": "supersede",
}


@dataclass(frozen=True)
class LearningLifecycleDecisionReceipt:
    id: str
    created_at: str
    lesson_memory_id: str
    provenance_id: str
    outcome_status: str
    decision: str
    selected_signal_id: str
    replacement_memory_id: str
    review_hash: str
    confirmation_method: str
    confirmation_token_hash: str
    evidence_event_ids: list[str]
    operator_confirmation_recorded: bool = True
    terminal_process_decision: bool = True
    memory_mutation_performed: bool = False
    skill_mutation_performed: bool = False
    experience_mutation_performed: bool = False
    persistence_performed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class LearningLifecycleDoctorReport:
    status: str
    receipt_count: int
    keep_count: int
    reject_count: int
    supersede_count: int
    issues: list[str]
    warnings: list[str]


@dataclass(frozen=True)
class LearningLifecycleBenchmarkReport:
    status: str
    receipt_count: int
    checks: dict[str, bool]
    failed_checks: list[str]
    boundary: str


class LearningLifecycleError(RuntimeError):
    pass


class OperatorReviewedLearningLifecycleSession:
    """Keeps terminal lesson-outcome decisions in bounded process memory."""

    def __init__(self) -> None:
        self._receipts: dict[str, LearningLifecycleDecisionReceipt] = {}
        self._lock = RLock()

    def snapshot(self) -> tuple[dict[str, Any], ...]:
        with self._lock:
            return tuple(deepcopy(receipt.to_dict()) for receipt in self._receipts.values())

    def get(self, identifier: str) -> LearningLifecycleDecisionReceipt | None:
        with self._lock:
            direct = self._receipts.get(identifier)
            if direct is not None:
                return direct
            return next(
                (
                    receipt
                    for receipt in self._receipts.values()
                    if identifier in {receipt.id, receipt.lesson_memory_id}
                ),
                None,
            )

    def decide(
        self,
        review: LearningOutcomeReview,
        decision: str,
        *,
        token: str,
    ) -> LearningLifecycleDecisionReceipt:
        expected_decision = OUTCOME_DECISIONS.get(review.status)
        if decision not in LEARNING_LIFECYCLE_DECISIONS:
            raise LearningLifecycleError(f"Unsupported lifecycle decision {decision!r}.")
        if expected_decision is None:
            raise LearningLifecycleError(
                f"Outcome {review.status} is not decision-eligible; more valid evidence is required."
            )
        if decision != expected_decision:
            raise LearningLifecycleError(
                f"Outcome {review.status} requires decision {expected_decision!r}, not {decision!r}."
            )
        if not review.selected_signal_id:
            raise LearningLifecycleError("Outcome candidate has no selected evidence signal.")
        if decision == "supersede" and not review.replacement_memory_id:
            raise LearningLifecycleError("Supersede outcome has no verified replacement memory id.")

        with self._lock:
            if review.lesson_memory_id in self._receipts:
                existing = self._receipts[review.lesson_memory_id]
                raise LearningLifecycleError(
                    f"Lesson already has terminal process-memory decision {existing.decision}."
                )
            if len(self._receipts) >= LEARNING_LIFECYCLE_MAX_RECEIPTS:
                raise LearningLifecycleError("Process-memory lifecycle receipt limit reached.")
            expected_token = learning_lifecycle_confirmation_token(review)
            if token != expected_token:
                raise LearningLifecycleError("Lifecycle confirmation token mismatch.")

            review_hash = learning_outcome_review_hash(review)
            receipt = LearningLifecycleDecisionReceipt(
                id=f"learnlife_{review_hash[:16]}",
                created_at=utc_now_iso(),
                lesson_memory_id=review.lesson_memory_id,
                provenance_id=review.provenance_id,
                outcome_status=review.status,
                decision=decision,
                selected_signal_id=review.selected_signal_id,
                replacement_memory_id=review.replacement_memory_id,
                review_hash=review_hash,
                confirmation_method="exact_current_outcome_token",
                confirmation_token_hash=hashlib.sha256(token.encode("utf-8")).hexdigest(),
                evidence_event_ids=[signal.event_id for signal in review.signals],
            )
            self._receipts[review.lesson_memory_id] = receipt
            return receipt

    def doctor(
        self,
        current_reviews: dict[str, LearningOutcomeReview],
    ) -> LearningLifecycleDoctorReport:
        receipts = self.snapshot()
        issues: list[str] = []
        warnings: list[str] = []
        counts = Counter(str(receipt.get("decision") or "") for receipt in receipts)
        if len(receipts) > LEARNING_LIFECYCLE_MAX_RECEIPTS:
            issues.append("Process-memory lifecycle receipt limit is exceeded.")

        receipt_ids: set[str] = set()
        lesson_ids: set[str] = set()
        for receipt in receipts:
            receipt_id = str(receipt.get("id") or "")
            lesson_id = str(receipt.get("lesson_memory_id") or "")
            decision = str(receipt.get("decision") or "")
            outcome_status = str(receipt.get("outcome_status") or "")
            if not receipt_id or receipt_id in receipt_ids:
                issues.append("Lifecycle receipt id is missing or duplicated.")
            receipt_ids.add(receipt_id)
            if not lesson_id or lesson_id in lesson_ids:
                issues.append(f"Lifecycle receipt {receipt_id or '<missing>'} has missing/duplicate lesson id.")
            lesson_ids.add(lesson_id)
            if decision not in LEARNING_LIFECYCLE_DECISIONS:
                issues.append(f"Lifecycle receipt {receipt_id} has invalid decision {decision!r}.")
            if OUTCOME_DECISIONS.get(outcome_status) != decision:
                issues.append(f"Lifecycle receipt {receipt_id} does not match its outcome status.")
            if len(str(receipt.get("review_hash") or "")) != 64:
                issues.append(f"Lifecycle receipt {receipt_id} has invalid review hash.")
            elif receipt_id != f"learnlife_{str(receipt.get('review_hash'))[:16]}":
                issues.append(f"Lifecycle receipt {receipt_id} does not match its review hash.")
            if len(str(receipt.get("confirmation_token_hash") or "")) != 64:
                issues.append(f"Lifecycle receipt {receipt_id} lacks confirmation token evidence.")
            if not receipt.get("selected_signal_id") or not receipt.get("evidence_event_ids"):
                issues.append(f"Lifecycle receipt {receipt_id} lacks bounded evidence identity.")
            elif receipt.get("selected_signal_id") not in receipt.get("evidence_event_ids"):
                issues.append(f"Lifecycle receipt {receipt_id} selected signal is outside its evidence ids.")
            if decision == "supersede" and not receipt.get("replacement_memory_id"):
                issues.append(f"Lifecycle receipt {receipt_id} lacks replacement memory id.")
            if (
                receipt.get("confirmation_method") != "exact_current_outcome_token"
                or receipt.get("operator_confirmation_recorded") is not True
                or receipt.get("terminal_process_decision") is not True
            ):
                issues.append(f"Lifecycle receipt {receipt_id} lacks exact operator confirmation.")
            if any(
                receipt.get(field) is not False
                for field in (
                    "memory_mutation_performed",
                    "skill_mutation_performed",
                    "experience_mutation_performed",
                    "persistence_performed",
                )
            ):
                issues.append(f"Lifecycle receipt {receipt_id} claims a forbidden mutation.")

            current = current_reviews.get(lesson_id)
            if current is None:
                warnings.append(
                    f"Lifecycle receipt {receipt_id} has no current reviewable lesson evidence."
                )
            elif learning_outcome_review_hash(current) != receipt.get("review_hash"):
                warnings.append(
                    f"Lifecycle receipt {receipt_id} is historical; current outcome evidence has changed."
                )

        status = "ERROR" if issues else "WARN" if warnings else "OK"
        return LearningLifecycleDoctorReport(
            status=status,
            receipt_count=len(receipts),
            keep_count=counts["keep"],
            reject_count=counts["reject"],
            supersede_count=counts["supersede"],
            issues=issues,
            warnings=warnings,
        )


def learning_outcome_review_hash(review: LearningOutcomeReview) -> str:
    payload = {
        "lesson_memory_id": review.lesson_memory_id,
        "provenance_id": review.provenance_id,
        "applied_at": review.applied_at,
        "status": review.status,
        "selected_signal_id": review.selected_signal_id,
        "replacement_memory_id": review.replacement_memory_id,
        "signals": [
            {
                "event_id": signal.event_id,
                "signal": signal.signal,
                "replacement_memory_id": signal.replacement_memory_id,
            }
            for signal in review.signals
        ],
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def learning_lifecycle_confirmation_token(review: LearningOutcomeReview) -> str:
    decision = OUTCOME_DECISIONS.get(review.status, "unavailable")
    digest = learning_outcome_review_hash(review)[:12].upper()
    return f"CONFIRM-OUTCOME-{decision.upper()}-{digest}"


def format_learning_lifecycle_command(
    command: str,
    *,
    events: Iterable[ExperienceEvent | dict[str, Any]],
    memory_store: MemoryStore | None,
    session: OperatorReviewedLearningLifecycleSession,
) -> str | None:
    raw = command.strip()
    normalized = " ".join(raw.lower().split())
    prefixes = (
        "/experience learning outcome-confirm-preview",
        "/experience learning outcome-decisions",
        "/experience learning outcome-decision",
        "/experience learning outcome-decision-doctor",
        "/experience learning decide outcome",
    )
    if not any(normalized == prefix or normalized.startswith(prefix + " ") for prefix in prefixes):
        return None
    if any(marker in raw for marker in ("\n", ";", "&&", "||")):
        return _lifecycle_error("Command chaining and multi-command input are not allowed.")
    if memory_store is None:
        return _lifecycle_error("MemoryStore is unavailable from the shared handler.")
    try:
        records = memory_store.load_working_memory() + memory_store.load_persistent_memory()
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        return _lifecycle_error(f"Memory store is unreadable: {exc}")
    reviewer = LearningOutcomeReviewer(events, records)

    if normalized == "/experience learning outcome-decisions":
        return format_learning_lifecycle_decisions(session)
    if normalized == "/experience learning outcome-decision-doctor":
        reviews = {
            record.id: reviewer.review(record.id)
            for record in records
            if record.type == "lesson"
        }
        return format_learning_lifecycle_doctor(session.doctor(reviews))
    if normalized == "/experience learning outcome-confirm-preview":
        return "Usage: /experience learning outcome-confirm-preview <memory_id>"
    if normalized.startswith("/experience learning outcome-confirm-preview "):
        parts = raw.split()
        if len(parts) != 4:
            return "Usage: /experience learning outcome-confirm-preview <memory_id>"
        return format_learning_lifecycle_preview(reviewer.review(parts[3]), session)
    if normalized == "/experience learning outcome-decision":
        return "Usage: /experience learning outcome-decision <memory_id|receipt_id>"
    if normalized.startswith("/experience learning outcome-decision "):
        parts = raw.split()
        if len(parts) != 4:
            return "Usage: /experience learning outcome-decision <memory_id|receipt_id>"
        return format_learning_lifecycle_receipt(session.get(parts[3]))
    if normalized == "/experience learning decide outcome":
        return (
            "Usage: /experience learning decide outcome "
            "<keep|reject|supersede> <memory_id> <exact token>"
        )

    parts = raw.split()
    if len(parts) != 7:
        return (
            "Usage: /experience learning decide outcome "
            "<keep|reject|supersede> <memory_id> <exact token>"
        )
    decision, memory_id, token = parts[4], parts[5], parts[6]
    review = reviewer.review(memory_id)
    try:
        receipt = session.decide(review, decision.lower(), token=token)
    except LearningLifecycleError as exc:
        return _lifecycle_error(str(exc))
    return format_learning_lifecycle_recorded(receipt)


def format_learning_lifecycle_preview(
    review: LearningOutcomeReview,
    session: OperatorReviewedLearningLifecycleSession,
) -> str:
    decision = OUTCOME_DECISIONS.get(review.status)
    existing = session.get(review.lesson_memory_id)
    confirmable = bool(decision and review.selected_signal_id and existing is None)
    if decision == "supersede" and not review.replacement_memory_id:
        confirmable = False
    lines = [
        "Proto-Mind Learning Lifecycle Confirmation Preview v1",
        f"Status: {'CONFIRMABLE' if confirmable else 'NOT CONFIRMABLE'}",
        f"lesson_memory_id: {review.lesson_memory_id or 'missing'}",
        f"outcome_status: {review.status}",
        f"recommended_decision: {decision or 'none'}",
        f"selected_signal_id: {review.selected_signal_id or 'none'}",
        f"replacement_memory_id: {review.replacement_memory_id or 'none'}",
        f"review_hash: {learning_outcome_review_hash(review)}",
    ]
    if existing is not None:
        lines.append(f"- Existing terminal process decision: {existing.decision} ({existing.id}).")
    elif confirmable:
        token = learning_lifecycle_confirmation_token(review)
        lines.extend(
            [
                f"confirmation_token: {token}",
                "Exact decision command:",
                (
                    f"/experience learning decide outcome {decision} "
                    f"{review.lesson_memory_id} {token}"
                ),
            ]
        )
    else:
        lines.append("- Current exact evidence is not eligible for a lifecycle decision.")
    lines.extend(_lifecycle_boundary())
    return "\n".join(lines)


def format_learning_lifecycle_recorded(receipt: LearningLifecycleDecisionReceipt) -> str:
    lines = [
        "Proto-Mind Learning Lifecycle Decision v1",
        "Status: RECORDED IN PROCESS MEMORY",
        f"receipt_id: {receipt.id}",
        f"lesson_memory_id: {receipt.lesson_memory_id}",
        f"outcome_status: {receipt.outcome_status}",
        f"decision: {receipt.decision}",
        f"selected_signal_id: {receipt.selected_signal_id}",
        f"replacement_memory_id: {receipt.replacement_memory_id or 'none'}",
        f"created_at: {receipt.created_at}",
    ]
    lines.extend(_lifecycle_boundary())
    return "\n".join(lines)


def format_learning_lifecycle_decisions(
    session: OperatorReviewedLearningLifecycleSession,
) -> str:
    receipts = session.snapshot()
    lines = [
        "Proto-Mind Learning Lifecycle Decisions v1",
        f"Status: {'OK' if receipts else 'EMPTY'}",
        f"receipts: {len(receipts)}/{LEARNING_LIFECYCLE_MAX_RECEIPTS}",
    ]
    for receipt in receipts:
        lines.append(
            f"- {receipt['id']} | {receipt['decision']} | {receipt['lesson_memory_id']} | "
            f"outcome={receipt['outcome_status']}"
        )
    lines.extend(_lifecycle_boundary())
    return "\n".join(lines)


def format_learning_lifecycle_receipt(
    receipt: LearningLifecycleDecisionReceipt | None,
) -> str:
    if receipt is None:
        return _lifecycle_error("Lifecycle decision receipt was not found.")
    lines = [
        "Proto-Mind Learning Lifecycle Decision Receipt v1",
        "Status: OK",
    ]
    lines.extend(f"{key}: {value}" for key, value in receipt.to_dict().items())
    lines.extend(_lifecycle_boundary())
    return "\n".join(lines)


def format_learning_lifecycle_doctor(report: LearningLifecycleDoctorReport) -> str:
    lines = [
        "Proto-Mind Learning Lifecycle Doctor v1",
        f"Status: {report.status}",
        f"mode: {LEARNING_LIFECYCLE_MODE}",
        f"receipts: {report.receipt_count}/{LEARNING_LIFECYCLE_MAX_RECEIPTS}",
        f"keep: {report.keep_count}",
        f"reject: {report.reject_count}",
        f"supersede: {report.supersede_count}",
    ]
    lines.extend(f"- ERROR: {issue}" for issue in report.issues)
    lines.extend(f"- WARN: {warning}" for warning in report.warnings)
    if not report.issues and not report.warnings:
        lines.append("- Exact confirmation, evidence binding, bounds, and no-mutation claims are healthy.")
    lines.extend(_lifecycle_boundary())
    return "\n".join(lines)


def run_learning_lifecycle_benchmark() -> LearningLifecycleBenchmarkReport:
    session = OperatorReviewedLearningLifecycleSession()
    reviews = {
        "keep": _benchmark_review("mem_keep", "KEEP_CANDIDATE", "evt_keep"),
        "reject": _benchmark_review("mem_reject", "REJECT_CANDIDATE", "evt_reject"),
        "supersede": _benchmark_review(
            "mem_old",
            "SUPERSEDE_CANDIDATE",
            "evt_supersede",
            replacement_memory_id="mem_new",
        ),
        "inconclusive": _benchmark_review(
            "mem_unknown",
            "NEEDS_MORE_EVIDENCE",
            "",
        ),
    }
    recorded: dict[str, LearningLifecycleDecisionReceipt] = {}
    for name in ("keep", "reject", "supersede"):
        review = reviews[name]
        recorded[name] = session.decide(
            review,
            OUTCOME_DECISIONS[review.status],
            token=learning_lifecycle_confirmation_token(review),
        )
    wrong_token_refused = _benchmark_refused(
        OperatorReviewedLearningLifecycleSession(),
        reviews["keep"],
        "keep",
        "WRONG-TOKEN",
    )
    inconclusive_refused = _benchmark_refused(
        session,
        reviews["inconclusive"],
        "keep",
        learning_lifecycle_confirmation_token(reviews["inconclusive"]),
    )
    duplicate_refused = _benchmark_refused(
        session,
        reviews["keep"],
        "keep",
        learning_lifecycle_confirmation_token(reviews["keep"]),
    )
    restarted = OperatorReviewedLearningLifecycleSession()
    checks = {
        "keep_requires_exact_current_outcome": recorded["keep"].decision == "keep",
        "reject_requires_exact_current_outcome": recorded["reject"].decision == "reject",
        "supersede_binds_verified_replacement_id": (
            recorded["supersede"].replacement_memory_id == "mem_new"
        ),
        "wrong_token_refused": wrong_token_refused,
        "inconclusive_outcome_refused": inconclusive_refused,
        "terminal_run_once_guard": duplicate_refused,
        "all_receipts_claim_no_mutation": all(
            not receipt.memory_mutation_performed
            and not receipt.skill_mutation_performed
            and not receipt.experience_mutation_performed
            and not receipt.persistence_performed
            for receipt in recorded.values()
        ),
        "restart_expires_receipts": restarted.snapshot() == (),
    }
    failed = [name for name, passed in checks.items() if not passed]
    return LearningLifecycleBenchmarkReport(
        status="OK" if not failed else "ERROR",
        receipt_count=len(session.snapshot()),
        checks=checks,
        failed_checks=failed,
        boundary=(
            "Process-memory operator decisions only; no memory/skill/event mutation, lifecycle "
            "apply, persistence, Context Injection, command execution, or LLM/API call."
        ),
    )


def format_learning_lifecycle_benchmark(
    report: LearningLifecycleBenchmarkReport | None = None,
) -> str:
    active = report or run_learning_lifecycle_benchmark()
    lines = [
        "Proto-Mind Learning Lifecycle Benchmark v1",
        f"Status: {active.status}",
        f"receipts: {active.receipt_count}",
        "Checks:",
    ]
    lines.extend(
        f"- [{'PASS' if passed else 'FAIL'}] {name}"
        for name, passed in active.checks.items()
    )
    lines.extend(["Boundary:", f"- {active.boundary}"])
    return "\n".join(lines)


def _benchmark_review(
    memory_id: str,
    status: str,
    signal_id: str,
    *,
    replacement_memory_id: str = "",
) -> LearningOutcomeReview:
    from proto_mind.experience_learning_outcome import LearningOutcomeSignal

    signals = []
    if signal_id:
        signals.append(
            LearningOutcomeSignal(
                event_id=signal_id,
                event_type="grounding_evaluated",
                created_at="2026-07-21T00:00:00+00:00",
                signal=status,
                reason="Deterministic lifecycle benchmark signal.",
                replacement_memory_id=replacement_memory_id,
            )
        )
    return LearningOutcomeReview(
        status=status,
        lesson_memory_id=memory_id,
        provenance_id=f"prov_{memory_id}",
        applied_at="2026-07-20T00:00:00+00:00",
        trace_status="OK",
        matching_retrieval_count=1 if signal_id else 0,
        later_evidence_count=1 if signal_id else 0,
        selected_signal_id=signal_id,
        replacement_memory_id=replacement_memory_id,
        signals=signals,
        checks={"durable_provenance_verified": True},
        issues=[],
        warnings=[],
    )


def _benchmark_refused(
    session: OperatorReviewedLearningLifecycleSession,
    review: LearningOutcomeReview,
    decision: str,
    token: str,
) -> bool:
    try:
        session.decide(review, decision, token=token)
    except LearningLifecycleError:
        return True
    return False


def _lifecycle_error(message: str) -> str:
    return "\n".join(
        [
            "Proto-Mind Learning Lifecycle Error",
            "Status: ERROR",
            f"- {message}",
            *_lifecycle_boundary(),
        ]
    )


def _lifecycle_boundary() -> list[str]:
    return [
        "Boundary:",
        "- Receipt is bounded process-memory review state and expires on restart.",
        "- No lesson, memory, skill, Experience event, queue, export, or Context Injection was changed.",
        "- Decision is not lifecycle apply authorization; no command or model was executed.",
    ]
