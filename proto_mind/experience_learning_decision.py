from __future__ import annotations

from collections import Counter
from copy import deepcopy
from dataclasses import asdict, dataclass
import hashlib
import json
from threading import RLock
from typing import Any

from proto_mind.experience_learning_bridge import (
    CognitiveLearningBridgeError,
    CognitiveLearningPreviewCandidate,
    CognitiveLearningTurnReview,
    OperatorReviewedLearningBridge,
)
from proto_mind.experience_ledger import compact_preview
from proto_mind.models import utc_now_iso


LEARNING_DECISION_VERSION = 1
LEARNING_DECISION_MODE = "operator_review_process_memory_only"
LEARNING_DECISION_MAX_RECEIPTS = 64
LEARNING_DECISIONS = frozenset({"accepted", "rejected"})


@dataclass(frozen=True)
class LearningCandidateDecisionReceipt:
    id: str
    created_at: str
    candidate_id: str
    candidate_hash: str
    decision: str
    reason: str
    confirmation_method: str
    evidence_event_ids: list[str]
    source_kinds: list[str]
    review_status_at_decision: str
    suggested_target: str
    operator_confirmation_recorded: bool
    promotion_performed: bool = False
    apply_performed: bool = False
    persistence_performed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class LearningPromotionDryRunReceipt:
    id: str
    candidate_id: str
    decision_id: str
    candidate_hash: str
    proposed_target: str
    proposed_content: str
    evidence_event_ids: list[str]
    source_kinds: list[str]
    operator_confirmation_recorded: bool
    eligible_for_future_review: bool = True
    executable: bool = False
    promotion_performed: bool = False
    apply_performed: bool = False
    persistence_performed: bool = False


@dataclass(frozen=True)
class LearningDecisionDoctorReport:
    status: str
    decision_count: int
    accepted_count: int
    rejected_count: int
    issues: list[str]
    warnings: list[str]


class LearningDecisionError(RuntimeError):
    pass


class OperatorReviewedLearningDecisionSession:
    """Keeps explicit candidate decisions in process memory without promotion."""

    def __init__(self) -> None:
        self._receipts: dict[str, LearningCandidateDecisionReceipt] = {}
        self._lock = RLock()

    def snapshot(self) -> tuple[dict[str, Any], ...]:
        with self._lock:
            return tuple(deepcopy(receipt.to_dict()) for receipt in self._receipts.values())

    def get(self, candidate_id: str) -> LearningCandidateDecisionReceipt | None:
        with self._lock:
            return self._receipts.get(candidate_id)

    def decide(
        self,
        candidate: CognitiveLearningPreviewCandidate,
        decision: str,
        *,
        token: str = "",
        reason: str = "",
    ) -> LearningCandidateDecisionReceipt:
        if decision not in LEARNING_DECISIONS:
            raise LearningDecisionError(f"Unsupported decision {decision!r}.")
        with self._lock:
            if candidate.id in self._receipts:
                existing = self._receipts[candidate.id]
                raise LearningDecisionError(
                    f"Candidate already has terminal process-memory decision {existing.decision}."
                )
            if len(self._receipts) >= LEARNING_DECISION_MAX_RECEIPTS:
                raise LearningDecisionError("Process-memory decision receipt limit reached.")
            candidate_hash = learning_candidate_hash(candidate)
            if decision == "accepted":
                if candidate.review_status != "operator_review_required":
                    raise LearningDecisionError(
                        "Candidate is not accept-eligible; more evidence or a complete episode is required."
                    )
                expected = learning_confirmation_token(candidate)
                if token != expected:
                    raise LearningDecisionError("Confirmation token mismatch.")
                confirmation_method = "exact_candidate_token"
                confirmation_recorded = True
            else:
                confirmation_method = "explicit_operator_reject"
                confirmation_recorded = False

            receipt = LearningCandidateDecisionReceipt(
                id=f"learndec_{candidate_hash[:16]}",
                created_at=utc_now_iso(),
                candidate_id=candidate.id,
                candidate_hash=candidate_hash,
                decision=decision,
                reason=compact_preview(reason) if reason else "",
                confirmation_method=confirmation_method,
                evidence_event_ids=list(candidate.evidence_event_ids),
                source_kinds=list(candidate.source_kinds),
                review_status_at_decision=candidate.review_status,
                suggested_target=candidate.suggested_target,
                operator_confirmation_recorded=confirmation_recorded,
            )
            self._receipts[candidate.id] = receipt
            return receipt

    def doctor(
        self,
        candidates: dict[str, CognitiveLearningPreviewCandidate],
    ) -> LearningDecisionDoctorReport:
        issues: list[str] = []
        warnings: list[str] = []
        receipts = self.snapshot()
        counts = Counter(str(receipt.get("decision", "")) for receipt in receipts)
        if len(receipts) > LEARNING_DECISION_MAX_RECEIPTS:
            issues.append("Process-memory decision receipt limit is exceeded.")
        ids: set[str] = set()
        for receipt in receipts:
            receipt_id = str(receipt.get("id", ""))
            candidate_id = str(receipt.get("candidate_id", ""))
            decision = str(receipt.get("decision", ""))
            if not receipt_id or receipt_id in ids:
                issues.append("Decision receipt id is missing or duplicated.")
            ids.add(receipt_id)
            if decision not in LEARNING_DECISIONS:
                issues.append(f"Decision {receipt_id or '<missing>'} has invalid state {decision!r}.")
            candidate_hash = str(receipt.get("candidate_hash", ""))
            evidence_ids = list(receipt.get("evidence_event_ids") or [])
            if not candidate_id or len(candidate_hash) != 64 or not evidence_ids:
                issues.append(f"Decision {receipt_id or '<missing>'} lacks bounded evidence identity.")
            if decision == "accepted" and (
                receipt.get("review_status_at_decision") != "operator_review_required"
                or receipt.get("confirmation_method") != "exact_candidate_token"
                or receipt.get("operator_confirmation_recorded") is not True
            ):
                issues.append(f"Accepted decision {receipt_id} lacks valid review confirmation.")
            if decision == "rejected" and receipt.get("confirmation_method") != "explicit_operator_reject":
                issues.append(f"Rejected decision {receipt_id} lacks explicit rejection metadata.")
            if any(
                receipt.get(field) is not False
                for field in ("promotion_performed", "apply_performed", "persistence_performed")
            ):
                issues.append(f"Decision {receipt_id} claims forbidden promotion/apply/persistence.")
            candidate = candidates.get(candidate_id)
            if candidate is None:
                warnings.append(
                    f"Decision {receipt_id or '<missing>'} references a candidate absent from current process evidence."
                )
                continue
            if receipt.get("candidate_hash") != learning_candidate_hash(candidate):
                issues.append(f"Decision {receipt_id} candidate hash no longer matches evidence.")
            if list(receipt.get("evidence_event_ids") or []) != candidate.evidence_event_ids:
                issues.append(f"Decision {receipt_id} evidence ids no longer match the candidate.")

        status = "ERROR" if issues else "WARN" if warnings else "OK"
        return LearningDecisionDoctorReport(
            status=status,
            decision_count=len(receipts),
            accepted_count=counts["accepted"],
            rejected_count=counts["rejected"],
            issues=issues,
            warnings=warnings,
        )


def learning_candidate_hash(candidate: CognitiveLearningPreviewCandidate) -> str:
    payload = {
        "candidate_id": candidate.id,
        "session_id": candidate.session_id,
        "turn_id": candidate.turn_id,
        "text": candidate.text,
        "source_kinds": candidate.source_kinds,
        "evidence_event_ids": candidate.evidence_event_ids,
        "confidence": candidate.confidence,
        "review_status": candidate.review_status,
        "suggested_target": candidate.suggested_target,
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def learning_confirmation_token(candidate: CognitiveLearningPreviewCandidate) -> str:
    return f"CONFIRM-LEARNING-{learning_candidate_hash(candidate)[:12].upper()}"


def build_promotion_dry_run(
    candidate: CognitiveLearningPreviewCandidate,
    decision: LearningCandidateDecisionReceipt,
) -> LearningPromotionDryRunReceipt:
    if decision.decision != "accepted":
        raise LearningDecisionError("Candidate must have an accepted decision first.")
    candidate_hash = learning_candidate_hash(candidate)
    if decision.candidate_hash != candidate_hash:
        raise LearningDecisionError("Accepted decision no longer matches current evidence.")
    return LearningPromotionDryRunReceipt(
        id=f"promodry_{candidate_hash[:16]}",
        candidate_id=candidate.id,
        decision_id=decision.id,
        candidate_hash=candidate_hash,
        proposed_target=candidate.suggested_target,
        proposed_content=candidate.text,
        evidence_event_ids=list(candidate.evidence_event_ids),
        source_kinds=list(candidate.source_kinds),
        operator_confirmation_recorded=decision.operator_confirmation_recorded,
    )


def format_learning_decision_command(
    command: str,
    bridge: OperatorReviewedLearningBridge,
    session: OperatorReviewedLearningDecisionSession,
) -> str | None:
    raw = command.strip()
    normalized = " ".join(raw.lower().split())
    handled = (
        "/experience learning decisions",
        "/experience learning decision",
        "/experience learning confirm-preview",
        "/experience learning decide",
        "/experience learning promotion-preview",
        "/experience learning decision-doctor",
    )
    if not any(normalized == prefix or normalized.startswith(prefix + " ") for prefix in handled):
        return None
    if normalized == "/experience learning decisions":
        return format_learning_decisions(session)

    candidate_map, error = _candidate_map(bridge)
    if error:
        return error
    if normalized == "/experience learning decision-doctor":
        return format_learning_decision_doctor(session, candidate_map)

    parts = raw.split(maxsplit=5)
    if normalized.startswith("/experience learning decision "):
        candidate_id = raw.split(maxsplit=3)[3].strip()
        return format_learning_decision(candidate_id, candidate_map, session)
    if normalized == "/experience learning decision":
        return "Usage: /experience learning decision <candidate_id>"
    if normalized.startswith("/experience learning confirm-preview "):
        candidate_id = raw.split(maxsplit=3)[3].strip()
        return format_learning_confirmation_preview(candidate_id, candidate_map, session)
    if normalized == "/experience learning confirm-preview":
        return "Usage: /experience learning confirm-preview <candidate_id>"
    if normalized.startswith("/experience learning promotion-preview "):
        candidate_id = raw.split(maxsplit=3)[3].strip()
        return format_learning_promotion_preview(candidate_id, candidate_map, session)
    if normalized == "/experience learning promotion-preview":
        return "Usage: /experience learning promotion-preview <candidate_id>"
    if len(parts) >= 5 and normalized.startswith("/experience learning decide "):
        action = parts[3].casefold()
        candidate_id = parts[4]
        remainder = parts[5].strip() if len(parts) == 6 else ""
        if action == "accept":
            return format_learning_accept(candidate_id, remainder, candidate_map, session)
        if action == "reject":
            return format_learning_reject(candidate_id, remainder, candidate_map, session)
    return "Usage: /experience learning decide accept <candidate_id> <exact token> | reject <candidate_id> [reason]"


def format_learning_decisions(session: OperatorReviewedLearningDecisionSession) -> str:
    receipts = session.snapshot()
    counts = Counter(str(item.get("decision", "")) for item in receipts)
    lines = [
        "Proto-Mind Learning Candidate Decisions v1",
        f"Status: {'OK' if receipts else 'EMPTY'}",
        f"mode: {LEARNING_DECISION_MODE}",
        f"decisions: {len(receipts)}/{LEARNING_DECISION_MAX_RECEIPTS}",
        f"accepted: {counts['accepted']}",
        f"rejected: {counts['rejected']}",
        "Decisions:",
    ]
    if not receipts:
        lines.append("- none")
    for receipt in receipts:
        lines.append(
            f"- {receipt['id']} | {receipt['decision']} | {receipt['candidate_id']} | {receipt['created_at']}"
        )
    lines.append("- Process memory only; restart discards all decisions.")
    return "\n".join(lines)


def format_learning_decision(
    candidate_id: str,
    candidates: dict[str, CognitiveLearningPreviewCandidate],
    session: OperatorReviewedLearningDecisionSession,
) -> str:
    candidate = candidates.get(candidate_id)
    if candidate is None:
        return _candidate_not_found(candidate_id, candidates)
    receipt = session.get(candidate_id)
    lines = [
        "Proto-Mind Learning Candidate Decision v1",
        f"candidate_id: {candidate.id}",
        f"review_status: {candidate.review_status}",
        f"candidate_hash: {learning_candidate_hash(candidate)}",
        f"evidence_event_ids: {', '.join(candidate.evidence_event_ids)}",
        f"decision: {receipt.decision if receipt else 'none'}",
    ]
    if receipt:
        lines.extend(
            [
                f"decision_id: {receipt.id}",
                f"created_at: {receipt.created_at}",
                f"reason: {receipt.reason}",
                f"confirmation_method: {receipt.confirmation_method}",
                f"operator_confirmation_recorded: {str(receipt.operator_confirmation_recorded).lower()}",
            ]
        )
    lines.extend(_no_promotion_boundary())
    return "\n".join(lines)


def format_learning_confirmation_preview(
    candidate_id: str,
    candidates: dict[str, CognitiveLearningPreviewCandidate],
    session: OperatorReviewedLearningDecisionSession,
) -> str:
    candidate = candidates.get(candidate_id)
    if candidate is None:
        return _candidate_not_found(candidate_id, candidates)
    existing = session.get(candidate_id)
    eligible = candidate.review_status == "operator_review_required" and existing is None
    lines = [
        "Proto-Mind Learning Candidate Confirmation Preview v1",
        f"Status: {'CONFIRMABLE' if eligible else 'NOT CONFIRMABLE'}",
        f"candidate_id: {candidate.id}",
        f"review_status: {candidate.review_status}",
        f"finding: {candidate.text}",
        f"evidence_event_ids: {', '.join(candidate.evidence_event_ids)}",
        f"existing_decision: {existing.decision if existing else 'none'}",
    ]
    if eligible:
        token = learning_confirmation_token(candidate)
        lines.extend(
            [
                f"confirmation_token: {token}",
                "Exact acceptance command:",
                f"/experience learning decide accept {candidate.id} {token}",
            ]
        )
    else:
        lines.append(
            "- Acceptance requires operator_review_required evidence and no existing terminal decision."
        )
    lines.extend(_no_promotion_boundary())
    return "\n".join(lines)


def format_learning_accept(
    candidate_id: str,
    token: str,
    candidates: dict[str, CognitiveLearningPreviewCandidate],
    session: OperatorReviewedLearningDecisionSession,
) -> str:
    candidate = candidates.get(candidate_id)
    if candidate is None:
        return _candidate_not_found(candidate_id, candidates)
    try:
        receipt = session.decide(candidate, "accepted", token=token)
    except LearningDecisionError as exc:
        return _decision_refused("Acceptance", exc)
    return "\n".join(
        [
            "Proto-Mind Learning Candidate Acceptance v1",
            "Status: ACCEPTED FOR FUTURE REVIEW",
            f"decision_id: {receipt.id}",
            f"candidate_id: {receipt.candidate_id}",
            f"candidate_hash: {receipt.candidate_hash}",
            f"evidence_event_ids: {', '.join(receipt.evidence_event_ids)}",
            "operator_confirmation_recorded: true",
            *_no_promotion_boundary(),
        ]
    )


def format_learning_reject(
    candidate_id: str,
    reason: str,
    candidates: dict[str, CognitiveLearningPreviewCandidate],
    session: OperatorReviewedLearningDecisionSession,
) -> str:
    candidate = candidates.get(candidate_id)
    if candidate is None:
        return _candidate_not_found(candidate_id, candidates)
    try:
        receipt = session.decide(candidate, "rejected", reason=reason)
    except LearningDecisionError as exc:
        return _decision_refused("Rejection", exc)
    return "\n".join(
        [
            "Proto-Mind Learning Candidate Rejection v1",
            "Status: REJECTED",
            f"decision_id: {receipt.id}",
            f"candidate_id: {receipt.candidate_id}",
            f"reason: {receipt.reason}",
            *_no_promotion_boundary(),
        ]
    )


def format_learning_promotion_preview(
    candidate_id: str,
    candidates: dict[str, CognitiveLearningPreviewCandidate],
    session: OperatorReviewedLearningDecisionSession,
) -> str:
    candidate = candidates.get(candidate_id)
    if candidate is None:
        return _candidate_not_found(candidate_id, candidates)
    decision = session.get(candidate_id)
    if decision is None or decision.decision != "accepted":
        return "\n".join(
            [
                "Proto-Mind Learning Promotion Dry-Run v1",
                "Status: NOT ELIGIBLE",
                "- An accepted process-memory decision is required first.",
                *_no_promotion_boundary(),
            ]
        )
    try:
        receipt = build_promotion_dry_run(candidate, decision)
    except LearningDecisionError as exc:
        return _decision_refused("Promotion dry-run", exc)
    return "\n".join(
        [
            "Proto-Mind Learning Promotion Dry-Run v1",
            "Status: DRY RUN ONLY",
            f"receipt_id: {receipt.id}",
            f"candidate_id: {receipt.candidate_id}",
            f"decision_id: {receipt.decision_id}",
            f"proposed_target: {receipt.proposed_target}",
            f"proposed_content: {receipt.proposed_content}",
            f"evidence_event_ids: {', '.join(receipt.evidence_event_ids)}",
            "eligible_for_future_review: true",
            "executable: false",
            *_no_promotion_boundary(),
        ]
    )


def format_learning_decision_doctor(
    session: OperatorReviewedLearningDecisionSession,
    candidates: dict[str, CognitiveLearningPreviewCandidate],
) -> str:
    report = session.doctor(candidates)
    lines = [
        "Proto-Mind Learning Candidate Decision Doctor v1",
        f"Status: {report.status}",
        f"decisions: {report.decision_count}/{LEARNING_DECISION_MAX_RECEIPTS}",
        f"accepted: {report.accepted_count}",
        f"rejected: {report.rejected_count}",
    ]
    lines.extend(f"- ERROR: {issue}" for issue in report.issues)
    lines.extend(f"- WARN: {warning}" for warning in report.warnings)
    if not report.issues and not report.warnings:
        lines.append("- Decision hashes, evidence links, and no-promotion boundaries are healthy.")
    lines.extend(_no_promotion_boundary())
    return "\n".join(lines)


def _candidate_map(
    bridge: OperatorReviewedLearningBridge,
) -> tuple[dict[str, CognitiveLearningPreviewCandidate], str]:
    try:
        reviews: list[CognitiveLearningTurnReview] = bridge.review()
    except CognitiveLearningBridgeError as exc:
        return {}, "\n".join(
            [
                "Proto-Mind Learning Candidate Decision v1",
                "Status: ERROR",
                f"- {exc}",
                "- No decision, promotion, apply, persistence, or store mutation occurred.",
            ]
        )
    return {
        candidate.id: candidate
        for review in reviews
        for candidate in review.candidates
    }, ""


def _candidate_not_found(
    candidate_id: str,
    candidates: dict[str, CognitiveLearningPreviewCandidate],
) -> str:
    available = ", ".join(candidates) or "none"
    return "\n".join(
        [
            "Proto-Mind Learning Candidate Decision v1",
            "Status: NOT FOUND",
            f"- Candidate {candidate_id!r} is absent from current process evidence.",
            f"- Available candidates: {available}",
            "- No decision, promotion, apply, persistence, or store mutation occurred.",
        ]
    )


def _decision_refused(kind: str, error: Exception) -> str:
    return "\n".join(
        [
            f"Proto-Mind Learning Candidate {kind} v1",
            "Status: REFUSED",
            f"- {error}",
            "- No decision, promotion, apply, persistence, or store mutation occurred.",
        ]
    )


def _no_promotion_boundary() -> list[str]:
    return [
        "promotion_performed: false",
        "apply_performed: false",
        "persistence_performed: false",
        "- Process-memory review metadata only; restart discards it.",
    ]
