from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from typing import Any, Iterable

from proto_mind.experience_learning_bridge import (
    CognitiveLearningBridgeError,
    CognitiveLearningPreviewCandidate,
    OperatorReviewedLearningBridge,
)
from proto_mind.experience_learning_decision import (
    LearningCandidateDecisionReceipt,
    OperatorReviewedLearningDecisionSession,
    learning_candidate_hash,
)
from proto_mind.experience_learning_input import (
    LEARNING_INPUT_SELECTION_MODE,
    ExperienceLearningInputAdapter,
    ExperienceLearningInputSnapshot,
)
from proto_mind.memory_store import MemoryStore
from proto_mind.skill_library import SkillLibrary


LEARNING_ELIGIBILITY_VERSION = 1
LEARNING_ELIGIBILITY_MODE = "explicit_ids_selected_scope_only"
LEARNING_ELIGIBILITY_TARGETS = frozenset({"memory", "skill"})
LEARNING_ELIGIBILITY_STATUSES = frozenset(
    {"ELIGIBLE IN SELECTED SCOPE", "DUPLICATE", "INCOMPLETE", "NOT CHECKED", "NOT ELIGIBLE", "ERROR"}
)
LEARNING_ELIGIBILITY_MAX_IDS_PER_KIND = 20


@dataclass(frozen=True)
class LearningPromotionEligibilityReceipt:
    id: str
    candidate_id: str
    decision_id: str
    candidate_hash: str
    target: str
    status: str
    selection_mode: str
    requested_memory_ids: list[str]
    requested_skill_ids: list[str]
    selected_memory_ids: list[str]
    selected_skill_ids: list[str]
    missing_memory_ids: list[str]
    missing_skill_ids: list[str]
    excluded_memory_ids: list[str]
    excluded_skill_ids: list[str]
    duplicate_matches: list[str]
    warnings: list[str]
    issues: list[str]
    scope_limited: bool = True
    global_duplicate_check_performed: bool = False
    retrieval_performed: bool = False
    usage_telemetry_recorded: bool = False
    mutation_performed: bool = False
    executable: bool = False
    promotion_performed: bool = False
    apply_performed: bool = False
    persistence_performed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class LearningEligibilityDoctorReport:
    status: str
    issues: list[str]
    warnings: list[str]


@dataclass(frozen=True)
class LearningEligibilityRequest:
    candidate_id: str
    target: str
    memory_ids: list[str]
    skill_ids: list[str]


class LearningEligibilityError(RuntimeError):
    pass


class LearningPromotionEligibilityReviewer:
    """Checks exact duplicates in an operator-selected detached reference scope."""

    def __init__(
        self,
        *,
        memory_store: MemoryStore,
        skill_library: SkillLibrary,
    ) -> None:
        self.adapter = ExperienceLearningInputAdapter(
            memory_store=memory_store,
            skill_library=skill_library,
        )

    def review(
        self,
        candidate: CognitiveLearningPreviewCandidate,
        decision: LearningCandidateDecisionReceipt | None,
        *,
        target: str,
        memory_ids: Iterable[str] = (),
        skill_ids: Iterable[str] = (),
    ) -> LearningPromotionEligibilityReceipt:
        normalized_target = target.strip().casefold()
        if normalized_target not in LEARNING_ELIGIBILITY_TARGETS:
            raise LearningEligibilityError("Target must be memory or skill.")
        requested_memories = _bounded_ids(memory_ids, kind="memory")
        requested_skills = _bounded_ids(skill_ids, kind="skill")
        snapshot = self.adapter.build_snapshot(
            memory_ids=requested_memories,
            skill_ids=requested_skills,
        )
        candidate_hash = learning_candidate_hash(candidate)
        issues = list(snapshot.issues)
        warnings = list(snapshot.warnings)
        duplicate_matches = _exact_duplicate_matches(
            candidate.text,
            snapshot,
            target=normalized_target,
        )

        if snapshot.status == "ERROR":
            status = "ERROR"
            decision_id = decision.id if decision is not None else "none"
        elif decision is None or decision.decision != "accepted":
            status = "NOT ELIGIBLE"
            warnings.append("An accepted process-memory candidate decision is required.")
            decision_id = "none"
        elif decision.candidate_hash != candidate_hash:
            status = "ERROR"
            issues.append("Accepted decision no longer matches current candidate evidence.")
            decision_id = decision.id
        elif snapshot.status == "WARN":
            status = "INCOMPLETE"
            decision_id = decision.id
        elif duplicate_matches:
            status = "DUPLICATE"
            warnings.append("Exact normalized content exists in the selected reference scope.")
            decision_id = decision.id
        elif _target_selected_count(normalized_target, snapshot) == 0:
            status = "NOT CHECKED"
            warnings.append(
                f"At least one active explicit {normalized_target} ID is required for target-scoped review."
            )
            decision_id = decision.id
        else:
            status = "ELIGIBLE IN SELECTED SCOPE"
            warnings.append(
                "No exact duplicate was found among selected IDs; global novelty was not checked."
            )
            decision_id = decision.id

        receipt_id = _eligibility_receipt_id(
            candidate_hash,
            normalized_target,
            snapshot.requested_memory_ids,
            snapshot.requested_skill_ids,
        )
        return LearningPromotionEligibilityReceipt(
            id=receipt_id,
            candidate_id=candidate.id,
            decision_id=decision_id,
            candidate_hash=candidate_hash,
            target=normalized_target,
            status=status,
            selection_mode=snapshot.selection_mode,
            requested_memory_ids=list(snapshot.requested_memory_ids),
            requested_skill_ids=list(snapshot.requested_skill_ids),
            selected_memory_ids=[str(record.get("id") or "") for record in snapshot.memory_records],
            selected_skill_ids=[str(record.get("id") or "") for record in snapshot.skill_records],
            missing_memory_ids=list(snapshot.missing_memory_ids),
            missing_skill_ids=list(snapshot.missing_skill_ids),
            excluded_memory_ids=list(snapshot.excluded_memory_ids),
            excluded_skill_ids=list(snapshot.excluded_skill_ids),
            duplicate_matches=duplicate_matches,
            warnings=warnings,
            issues=issues,
        )

    @staticmethod
    def doctor(receipt: LearningPromotionEligibilityReceipt) -> LearningEligibilityDoctorReport:
        issues = list(receipt.issues)
        warnings = list(receipt.warnings)
        if receipt.status not in LEARNING_ELIGIBILITY_STATUSES:
            issues.append("Eligibility status is invalid.")
        if receipt.selection_mode != LEARNING_INPUT_SELECTION_MODE:
            issues.append("Eligibility selection mode is not explicit_ids_only.")
        if receipt.target not in LEARNING_ELIGIBILITY_TARGETS:
            issues.append("Eligibility target is invalid.")
        if len(receipt.candidate_hash) != 64 or not receipt.candidate_id:
            issues.append("Eligibility candidate evidence identity is incomplete.")
        if not receipt.scope_limited or receipt.global_duplicate_check_performed:
            issues.append("Eligibility receipt overstates its selected-ID scope.")
        if any(
            getattr(receipt, field)
            for field in (
                "retrieval_performed",
                "usage_telemetry_recorded",
                "mutation_performed",
                "executable",
                "promotion_performed",
                "apply_performed",
                "persistence_performed",
            )
        ):
            issues.append("Eligibility receipt claims a forbidden side effect or execution path.")
        if receipt.status == "ELIGIBLE IN SELECTED SCOPE" and (
            receipt.duplicate_matches
            or (receipt.target == "memory" and not receipt.selected_memory_ids)
            or (receipt.target == "skill" and not receipt.selected_skill_ids)
        ):
            issues.append("Eligible receipt lacks a clean target-specific selected scope.")
        status = "ERROR" if issues else "WARN" if warnings else "OK"
        return LearningEligibilityDoctorReport(status=status, issues=issues, warnings=warnings)


def format_learning_eligibility_command(
    command: str,
    *,
    bridge: OperatorReviewedLearningBridge,
    decisions: OperatorReviewedLearningDecisionSession,
    memory_store: MemoryStore | None,
    skill_library: SkillLibrary,
) -> str | None:
    raw = command.strip()
    normalized = " ".join(raw.lower().split())
    doctor_mode = normalized == "/experience learning eligibility-doctor" or normalized.startswith(
        "/experience learning eligibility-doctor "
    )
    review_mode = normalized == "/experience learning eligibility" or normalized.startswith(
        "/experience learning eligibility "
    )
    if not doctor_mode and not review_mode:
        return None
    if memory_store is None:
        return _error_output("MemoryStore is unavailable from the shared handler.")
    usage = (
        "/experience learning eligibility-doctor <candidate_id>"
        if doctor_mode
        else "/experience learning eligibility <candidate_id>"
    )
    parsed = _parse_request(raw, command_name=usage.split(" <", 1)[0])
    if isinstance(parsed, str):
        return parsed
    candidate_map, error = _candidate_map(bridge)
    if error:
        return error
    candidate = candidate_map.get(parsed.candidate_id)
    if candidate is None:
        return _candidate_not_found(parsed.candidate_id, candidate_map)
    reviewer = LearningPromotionEligibilityReviewer(
        memory_store=memory_store,
        skill_library=skill_library,
    )
    try:
        receipt = reviewer.review(
            candidate,
            decisions.get(candidate.id),
            target=parsed.target,
            memory_ids=parsed.memory_ids,
            skill_ids=parsed.skill_ids,
        )
    except LearningEligibilityError as exc:
        return _error_output(str(exc))
    return (
        format_learning_eligibility_doctor(receipt, reviewer.doctor(receipt))
        if doctor_mode
        else format_learning_eligibility(receipt)
    )


def format_learning_eligibility(receipt: LearningPromotionEligibilityReceipt) -> str:
    lines = [
        "Proto-Mind Learning Promotion Eligibility Review v1",
        f"Status: {receipt.status}",
        f"receipt_id: {receipt.id}",
        f"candidate_id: {receipt.candidate_id}",
        f"decision_id: {receipt.decision_id}",
        f"target: {receipt.target}",
        f"selection_mode: {receipt.selection_mode}",
        f"requested_memory_ids: {', '.join(receipt.requested_memory_ids) or 'none'}",
        f"requested_skill_ids: {', '.join(receipt.requested_skill_ids) or 'none'}",
        f"selected_memory_ids: {', '.join(receipt.selected_memory_ids) or 'none'}",
        f"selected_skill_ids: {', '.join(receipt.selected_skill_ids) or 'none'}",
        f"duplicate_matches: {', '.join(receipt.duplicate_matches) or 'none'}",
    ]
    lines.extend(f"- ERROR: {issue}" for issue in receipt.issues)
    lines.extend(f"- WARN: {warning}" for warning in receipt.warnings)
    lines.extend(_eligibility_boundary())
    return "\n".join(lines)


def format_learning_eligibility_doctor(
    receipt: LearningPromotionEligibilityReceipt,
    report: LearningEligibilityDoctorReport,
) -> str:
    lines = [
        "Proto-Mind Learning Promotion Eligibility Doctor v1",
        f"Status: {report.status}",
        f"eligibility_status: {receipt.status}",
        f"candidate_id: {receipt.candidate_id}",
        f"target: {receipt.target}",
        f"selected_memories: {len(receipt.selected_memory_ids)}",
        f"selected_skills: {len(receipt.selected_skill_ids)}",
        f"duplicates: {len(receipt.duplicate_matches)}",
    ]
    lines.extend(f"- ERROR: {issue}" for issue in report.issues)
    lines.extend(f"- WARN: {warning}" for warning in report.warnings)
    if not report.issues and not report.warnings:
        lines.append("- Explicit-ID scope and no-effect boundaries are healthy.")
    lines.extend(_eligibility_boundary())
    return "\n".join(lines)


def _parse_request(command: str, *, command_name: str) -> LearningEligibilityRequest | str:
    parts = command.split()
    prefix_parts = command_name.split()
    usage = (
        f"Usage: {command_name} <candidate_id> --target memory|skill "
        "[--memory <id>]... [--skill <id>]..."
    )
    if len(parts) < len(prefix_parts) + 1 or [part.casefold() for part in parts[: len(prefix_parts)]] != [
        part.casefold() for part in prefix_parts
    ]:
        return usage
    candidate_id = parts[len(prefix_parts)]
    target = ""
    memory_ids: list[str] = []
    skill_ids: list[str] = []
    index = len(prefix_parts) + 1
    while index < len(parts):
        flag = parts[index].casefold()
        if flag not in {"--target", "--memory", "--skill"} or index + 1 >= len(parts):
            return usage
        value = parts[index + 1].strip()
        if not value or value.startswith("--"):
            return usage
        if flag == "--target":
            if target:
                return "Learning eligibility error: --target may be supplied only once."
            target = value.casefold()
        elif flag == "--memory":
            memory_ids.append(value)
        else:
            skill_ids.append(value)
        index += 2
    if target not in LEARNING_ELIGIBILITY_TARGETS:
        return usage
    return LearningEligibilityRequest(
        candidate_id=candidate_id,
        target=target,
        memory_ids=memory_ids,
        skill_ids=skill_ids,
    )


def _bounded_ids(values: Iterable[str], *, kind: str) -> list[str]:
    ids = [str(value).strip() for value in values if str(value).strip()]
    if len(ids) > LEARNING_ELIGIBILITY_MAX_IDS_PER_KIND:
        raise LearningEligibilityError(
            f"Explicit {kind} ID limit is {LEARNING_ELIGIBILITY_MAX_IDS_PER_KIND}."
        )
    return ids


def _exact_duplicate_matches(
    text: str,
    snapshot: ExperienceLearningInputSnapshot,
    *,
    target: str,
) -> list[str]:
    normalized = _normalize(text)
    if not normalized:
        return []
    matches: list[str] = []
    if target == "memory":
        for record in snapshot.memory_records:
            if _normalize(str(record.get("content") or "")) == normalized:
                matches.append(f"memory:{record.get('id')}:content")
    if target == "skill":
        for record in snapshot.skill_records:
            for field in ("name", "summary", "body"):
                if _normalize(str(record.get(field) or "")) == normalized:
                    matches.append(f"skill:{record.get('id')}:{field}")
    return sorted(set(matches))


def _target_selected_count(target: str, snapshot: ExperienceLearningInputSnapshot) -> int:
    return len(snapshot.memory_records) if target == "memory" else len(snapshot.skill_records)


def _eligibility_receipt_id(
    candidate_hash: str,
    target: str,
    memory_ids: list[str],
    skill_ids: list[str],
) -> str:
    payload = json.dumps(
        {
            "candidate_hash": candidate_hash,
            "target": target,
            "memory_ids": memory_ids,
            "skill_ids": skill_ids,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return f"eligdry_{hashlib.sha256(payload.encode('utf-8')).hexdigest()[:16]}"


def _candidate_map(
    bridge: OperatorReviewedLearningBridge,
) -> tuple[dict[str, CognitiveLearningPreviewCandidate], str]:
    try:
        reviews = bridge.review()
    except CognitiveLearningBridgeError as exc:
        return {}, _error_output(str(exc))
    return {
        candidate.id: candidate
        for review in reviews
        for candidate in review.candidates
    }, ""


def _candidate_not_found(
    candidate_id: str,
    candidates: dict[str, CognitiveLearningPreviewCandidate],
) -> str:
    return "\n".join(
        [
            "Proto-Mind Learning Promotion Eligibility Review v1",
            "Status: NOT FOUND",
            f"- Candidate {candidate_id!r} is absent from current process evidence.",
            f"- Available candidates: {', '.join(candidates) or 'none'}",
            *_eligibility_boundary(),
        ]
    )


def _error_output(message: str) -> str:
    return "\n".join(
        [
            "Proto-Mind Learning Promotion Eligibility Review v1",
            "Status: ERROR",
            f"- {message}",
            *_eligibility_boundary(),
        ]
    )


def _normalize(value: str) -> str:
    return " ".join(value.casefold().split())


def _eligibility_boundary() -> list[str]:
    return [
        "scope_limited: true",
        "global_duplicate_check_performed: false",
        "retrieval_performed: false",
        "usage_telemetry_recorded: false",
        "mutation_performed: false",
        "executable: false",
        "promotion_performed: false",
        "apply_performed: false",
        "persistence_performed: false",
        "- Exact selected-ID review only; no search, ranking, write, or execution occurred.",
    ]
