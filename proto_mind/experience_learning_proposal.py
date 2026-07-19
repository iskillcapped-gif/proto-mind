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
    OperatorReviewedLearningBridge,
)
from proto_mind.experience_learning_decision import (
    LearningCandidateDecisionReceipt,
    OperatorReviewedLearningDecisionSession,
    learning_candidate_hash,
)
from proto_mind.experience_learning_eligibility import (
    LearningEligibilityRequest,
    LearningPromotionEligibilityReceipt,
    LearningPromotionEligibilityReviewer,
    parse_learning_eligibility_request,
)
from proto_mind.experience_ledger import compact_preview
from proto_mind.memory_store import MemoryStore
from proto_mind.models import utc_now_iso
from proto_mind.skill_library import SkillLibrary


LEARNING_PROPOSAL_VERSION = 1
LEARNING_PROPOSAL_MODE = "operator_confirmed_process_memory_proposal_only"
LEARNING_PROPOSAL_MAX_RECEIPTS = 32
LEARNING_PROPOSAL_SCHEMAS = {
    "memory": "memory.lesson.v1",
    "skill": "skill.procedure.v1",
}


@dataclass(frozen=True)
class LearningPromotionProposalBlueprint:
    candidate_id: str
    candidate_hash: str
    decision_id: str
    eligibility_receipt_id: str
    eligibility_hash: str
    eligibility_status: str
    selected_scope_hash: str
    target: str
    target_schema: str
    proposed_payload: dict[str, Any]
    requested_memory_ids: list[str]
    requested_skill_ids: list[str]
    selected_reference_ids: list[str]
    evidence_event_ids: list[str]
    source_kinds: list[str]
    confidence: str
    proposal_hash: str
    scope_limited: bool = True
    global_duplicate_check_performed: bool = False
    future_apply_ready: bool = False
    executable: bool = False
    promotion_performed: bool = False
    apply_performed: bool = False
    persistence_performed: bool = False


@dataclass(frozen=True)
class LearningPromotionProposalReceipt:
    id: str
    created_at: str
    candidate_id: str
    candidate_hash: str
    decision_id: str
    eligibility_receipt_id: str
    eligibility_hash: str
    eligibility_status: str
    selected_scope_hash: str
    target: str
    target_schema: str
    proposed_payload: dict[str, Any]
    requested_memory_ids: list[str]
    requested_skill_ids: list[str]
    selected_reference_ids: list[str]
    evidence_event_ids: list[str]
    source_kinds: list[str]
    confidence: str
    proposal_hash: str
    confirmation_method: str
    operator_confirmation_recorded: bool
    scope_limited: bool = True
    global_duplicate_check_performed: bool = False
    future_apply_ready: bool = False
    executable: bool = False
    promotion_performed: bool = False
    apply_performed: bool = False
    persistence_performed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class LearningProposalDoctorReport:
    status: str
    proposal_count: int
    memory_count: int
    skill_count: int
    issues: list[str]
    warnings: list[str]


@dataclass(frozen=True)
class LearningProposalRequest:
    eligibility: LearningEligibilityRequest
    token: str = ""


class LearningProposalError(RuntimeError):
    pass


class LearningPromotionProposalBuilder:
    """Builds one immutable proposal blueprint from accepted, selected-scope evidence."""

    def __init__(self, *, memory_store: MemoryStore, skill_library: SkillLibrary) -> None:
        self.eligibility = LearningPromotionEligibilityReviewer(
            memory_store=memory_store,
            skill_library=skill_library,
        )

    def build(
        self,
        candidate: CognitiveLearningPreviewCandidate,
        decision: LearningCandidateDecisionReceipt | None,
        request: LearningEligibilityRequest,
    ) -> LearningPromotionProposalBlueprint:
        eligibility = self.eligibility.review(
            candidate,
            decision,
            target=request.target,
            memory_ids=request.memory_ids,
            skill_ids=request.skill_ids,
        )
        if decision is None or decision.decision != "accepted":
            raise LearningProposalError("An accepted process-memory candidate decision is required.")
        if eligibility.status != "ELIGIBLE IN SELECTED SCOPE":
            raise LearningProposalError(
                f"Eligibility status must be ELIGIBLE IN SELECTED SCOPE, got {eligibility.status}."
            )
        payload = _target_payload(candidate, request.target)
        eligibility_hash = _hash_json(eligibility.to_dict())
        material = {
            "candidate_id": candidate.id,
            "candidate_hash": learning_candidate_hash(candidate),
            "decision_id": decision.id,
            "eligibility_receipt_id": eligibility.id,
            "eligibility_hash": eligibility_hash,
            "eligibility_status": eligibility.status,
            "selected_scope_hash": eligibility.selected_scope_hash,
            "target": request.target,
            "target_schema": LEARNING_PROPOSAL_SCHEMAS[request.target],
            "proposed_payload": payload,
            "requested_memory_ids": eligibility.requested_memory_ids,
            "requested_skill_ids": eligibility.requested_skill_ids,
            "selected_reference_ids": (
                eligibility.selected_memory_ids
                if request.target == "memory"
                else eligibility.selected_skill_ids
            ),
            "evidence_event_ids": candidate.evidence_event_ids,
            "source_kinds": candidate.source_kinds,
            "confidence": candidate.confidence,
        }
        return LearningPromotionProposalBlueprint(
            **material,
            proposal_hash=_hash_json(material),
        )


class OperatorReviewedLearningProposalSession:
    """Retains bounded immutable proposal receipts for the current process only."""

    def __init__(self) -> None:
        self._receipts: dict[str, LearningPromotionProposalReceipt] = {}
        self._lock = RLock()

    def snapshot(self) -> tuple[dict[str, Any], ...]:
        with self._lock:
            return tuple(deepcopy(receipt.to_dict()) for receipt in self._receipts.values())

    def get(self, identifier: str) -> LearningPromotionProposalReceipt | None:
        with self._lock:
            direct = self._receipts.get(identifier)
            if direct is not None:
                return direct
            return next(
                (receipt for receipt in self._receipts.values() if receipt.id == identifier),
                None,
            )

    def create(
        self,
        blueprint: LearningPromotionProposalBlueprint,
        *,
        token: str,
    ) -> LearningPromotionProposalReceipt:
        with self._lock:
            if token != learning_proposal_confirmation_token(blueprint):
                raise LearningProposalError("Proposal confirmation token mismatch.")
            if blueprint.candidate_id in self._receipts:
                raise LearningProposalError("Candidate already has a process-memory proposal.")
            if len(self._receipts) >= LEARNING_PROPOSAL_MAX_RECEIPTS:
                raise LearningProposalError("Process-memory proposal receipt limit reached.")
            receipt = LearningPromotionProposalReceipt(
                id=f"learnprop_{blueprint.proposal_hash[:16]}",
                created_at=utc_now_iso(),
                candidate_id=blueprint.candidate_id,
                candidate_hash=blueprint.candidate_hash,
                decision_id=blueprint.decision_id,
                eligibility_receipt_id=blueprint.eligibility_receipt_id,
                eligibility_hash=blueprint.eligibility_hash,
                eligibility_status=blueprint.eligibility_status,
                selected_scope_hash=blueprint.selected_scope_hash,
                target=blueprint.target,
                target_schema=blueprint.target_schema,
                proposed_payload=deepcopy(blueprint.proposed_payload),
                requested_memory_ids=list(blueprint.requested_memory_ids),
                requested_skill_ids=list(blueprint.requested_skill_ids),
                selected_reference_ids=list(blueprint.selected_reference_ids),
                evidence_event_ids=list(blueprint.evidence_event_ids),
                source_kinds=list(blueprint.source_kinds),
                confidence=blueprint.confidence,
                proposal_hash=blueprint.proposal_hash,
                confirmation_method="exact_proposal_token",
                operator_confirmation_recorded=True,
            )
            self._receipts[receipt.candidate_id] = receipt
            return receipt

    def doctor(
        self,
        candidates: dict[str, CognitiveLearningPreviewCandidate],
        decisions: OperatorReviewedLearningDecisionSession,
    ) -> LearningProposalDoctorReport:
        receipts = self.snapshot()
        issues: list[str] = []
        warnings: list[str] = []
        if len(receipts) > LEARNING_PROPOSAL_MAX_RECEIPTS:
            issues.append("Process-memory proposal receipt limit is exceeded.")
        receipt_ids: set[str] = set()
        proposal_hashes: set[str] = set()
        for receipt in receipts:
            label = str(receipt.get("id") or "<missing>")
            if label == "<missing>" or label in receipt_ids:
                issues.append("Proposal receipt id is missing or duplicated.")
            receipt_ids.add(label)
            proposal_hash = str(receipt.get("proposal_hash") or "")
            if len(proposal_hash) != 64 or proposal_hash in proposal_hashes:
                issues.append(f"Proposal {label} hash is missing, invalid, or duplicated.")
            proposal_hashes.add(proposal_hash)
            if label != f"learnprop_{proposal_hash[:16]}":
                issues.append(f"Proposal {label} id does not match its digest.")
            target = str(receipt.get("target") or "")
            if target not in LEARNING_PROPOSAL_SCHEMAS:
                issues.append(f"Proposal {label} target is invalid.")
            elif receipt.get("target_schema") != LEARNING_PROPOSAL_SCHEMAS[target]:
                issues.append(f"Proposal {label} target schema is invalid.")
            if not _valid_target_payload(target, receipt.get("proposed_payload")):
                issues.append(f"Proposal {label} payload does not match its fixed target schema.")
            if receipt.get("eligibility_status") != "ELIGIBLE IN SELECTED SCOPE":
                issues.append(f"Proposal {label} lacks clean selected-scope eligibility.")
            if len(str(receipt.get("eligibility_hash") or "")) != 64:
                issues.append(f"Proposal {label} eligibility hash is invalid.")
            if len(str(receipt.get("selected_scope_hash") or "")) != 64:
                issues.append(f"Proposal {label} selected-scope hash is invalid.")
            if not list(receipt.get("selected_reference_ids") or []):
                issues.append(f"Proposal {label} has no selected target references.")
            if (
                receipt.get("confirmation_method") != "exact_proposal_token"
                or receipt.get("operator_confirmation_recorded") is not True
            ):
                issues.append(f"Proposal {label} lacks exact operator confirmation.")
            if receipt.get("scope_limited") is not True or receipt.get(
                "global_duplicate_check_performed"
            ) is not False:
                issues.append(f"Proposal {label} overstates duplicate-review scope.")
            if any(
                receipt.get(field) is not False
                for field in (
                    "future_apply_ready",
                    "executable",
                    "promotion_performed",
                    "apply_performed",
                    "persistence_performed",
                )
            ):
                issues.append(f"Proposal {label} claims a forbidden effect or readiness state.")
            if proposal_hash and proposal_hash != _proposal_hash_from_receipt(receipt):
                issues.append(f"Proposal {label} digest no longer matches its receipt fields.")
            candidate_id = str(receipt.get("candidate_id") or "")
            candidate = candidates.get(candidate_id)
            if candidate is None:
                warnings.append(f"Proposal {label} candidate is absent from current evidence.")
            elif receipt.get("candidate_hash") != learning_candidate_hash(candidate):
                issues.append(f"Proposal {label} candidate hash no longer matches evidence.")
            decision = decisions.get(candidate_id)
            if decision is None or decision.decision != "accepted":
                issues.append(f"Proposal {label} has no current accepted decision.")
            elif receipt.get("decision_id") != decision.id:
                issues.append(f"Proposal {label} decision id no longer matches process state.")

        counts = Counter(str(receipt.get("target") or "") for receipt in receipts)
        status = "ERROR" if issues else "WARN" if warnings else "OK"
        return LearningProposalDoctorReport(
            status=status,
            proposal_count=len(receipts),
            memory_count=counts["memory"],
            skill_count=counts["skill"],
            issues=issues,
            warnings=warnings,
        )


def learning_proposal_confirmation_token(
    blueprint: LearningPromotionProposalBlueprint,
) -> str:
    return f"CONFIRM-PROPOSAL-{blueprint.proposal_hash[:12].upper()}"


def format_learning_proposal_command(
    command: str,
    *,
    bridge: OperatorReviewedLearningBridge,
    decisions: OperatorReviewedLearningDecisionSession,
    proposals: OperatorReviewedLearningProposalSession,
    memory_store: MemoryStore | None,
    skill_library: SkillLibrary,
) -> str | None:
    raw = command.strip()
    normalized = " ".join(raw.lower().split())
    handled = (
        "/experience learning proposal-preview",
        "/experience learning propose",
        "/experience learning proposals",
        "/experience learning proposal",
        "/experience learning proposal-doctor",
    )
    if not any(normalized == prefix or normalized.startswith(prefix + " ") for prefix in handled):
        return None
    if memory_store is None:
        return _error_output("MemoryStore is unavailable from the shared handler.")
    candidate_map, error = _candidate_map(bridge)
    if error:
        return error
    if normalized == "/experience learning proposals":
        return format_learning_proposals(proposals)
    if normalized == "/experience learning proposal-doctor":
        return format_learning_proposal_doctor(proposals, candidate_map, decisions)
    if normalized.startswith("/experience learning proposal "):
        identifier = raw.split(maxsplit=3)[3].strip()
        return format_learning_proposal(identifier, proposals)
    if normalized == "/experience learning proposal":
        return "Usage: /experience learning proposal <proposal_id|candidate_id>"

    preview_mode = normalized == "/experience learning proposal-preview" or normalized.startswith(
        "/experience learning proposal-preview "
    )
    command_name = (
        "/experience learning proposal-preview"
        if preview_mode
        else "/experience learning propose"
    )
    parsed = _parse_proposal_request(raw, command_name=command_name, require_token=not preview_mode)
    if isinstance(parsed, str):
        return parsed
    candidate = candidate_map.get(parsed.eligibility.candidate_id)
    if candidate is None:
        return _candidate_not_found(parsed.eligibility.candidate_id, candidate_map)
    builder = LearningPromotionProposalBuilder(
        memory_store=memory_store,
        skill_library=skill_library,
    )
    try:
        blueprint = builder.build(
            candidate,
            decisions.get(candidate.id),
            parsed.eligibility,
        )
    except LearningProposalError as exc:
        return _not_proposable(str(exc))
    if preview_mode:
        return format_learning_proposal_preview(blueprint)
    try:
        receipt = proposals.create(blueprint, token=parsed.token)
    except LearningProposalError as exc:
        return _proposal_refused(str(exc))
    return format_learning_proposal_created(receipt)


def format_learning_proposal_preview(
    blueprint: LearningPromotionProposalBlueprint,
) -> str:
    token = learning_proposal_confirmation_token(blueprint)
    return "\n".join(
        [
            "Proto-Mind Learning Promotion Proposal Preview v1",
            "Status: CONFIRMABLE",
            f"candidate_id: {blueprint.candidate_id}",
            f"decision_id: {blueprint.decision_id}",
            f"eligibility_receipt_id: {blueprint.eligibility_receipt_id}",
            f"selected_scope_hash: {blueprint.selected_scope_hash}",
            f"target: {blueprint.target}",
            f"target_schema: {blueprint.target_schema}",
            f"proposed_payload: {_compact_json(blueprint.proposed_payload)}",
            f"selected_reference_ids: {', '.join(blueprint.selected_reference_ids)}",
            f"proposal_hash: {blueprint.proposal_hash}",
            f"confirmation_token: {token}",
            "Exact proposal command:",
            _canonical_propose_command(blueprint, token),
            *_proposal_boundary(),
        ]
    )


def format_learning_proposal_created(receipt: LearningPromotionProposalReceipt) -> str:
    return "\n".join(
        [
            "Proto-Mind Learning Promotion Proposal Receipt v1",
            "Status: PROPOSED IN PROCESS MEMORY",
            f"proposal_id: {receipt.id}",
            f"candidate_id: {receipt.candidate_id}",
            f"target: {receipt.target}",
            f"target_schema: {receipt.target_schema}",
            f"proposal_hash: {receipt.proposal_hash}",
            f"created_at: {receipt.created_at}",
            "operator_confirmation_recorded: true",
            *_proposal_boundary(),
        ]
    )


def format_learning_proposals(session: OperatorReviewedLearningProposalSession) -> str:
    receipts = session.snapshot()
    counts = Counter(str(receipt.get("target") or "") for receipt in receipts)
    lines = [
        "Proto-Mind Learning Promotion Proposals v1",
        f"Status: {'OK' if receipts else 'EMPTY'}",
        f"mode: {LEARNING_PROPOSAL_MODE}",
        f"proposals: {len(receipts)}/{LEARNING_PROPOSAL_MAX_RECEIPTS}",
        f"memory: {counts['memory']}",
        f"skill: {counts['skill']}",
        "Proposals:",
    ]
    if not receipts:
        lines.append("- none")
    for receipt in receipts:
        lines.append(
            f"- {receipt['id']} | {receipt['target']} | {receipt['candidate_id']} | "
            f"{receipt['created_at']}"
        )
    lines.append("- Process memory only; restart discards all proposals.")
    return "\n".join(lines)


def format_learning_proposal(
    identifier: str,
    session: OperatorReviewedLearningProposalSession,
) -> str:
    receipt = session.get(identifier)
    if receipt is None:
        return "\n".join(
            [
                "Proto-Mind Learning Promotion Proposal Receipt v1",
                "Status: NOT FOUND",
                f"- Proposal or candidate {identifier!r} is absent from process memory.",
                *_proposal_boundary(),
            ]
        )
    return "\n".join(
        [
            "Proto-Mind Learning Promotion Proposal Receipt v1",
            "Status: FOUND",
            f"proposal_id: {receipt.id}",
            f"created_at: {receipt.created_at}",
            f"candidate_id: {receipt.candidate_id}",
            f"candidate_hash: {receipt.candidate_hash}",
            f"decision_id: {receipt.decision_id}",
            f"eligibility_receipt_id: {receipt.eligibility_receipt_id}",
            f"eligibility_hash: {receipt.eligibility_hash}",
            f"selected_scope_hash: {receipt.selected_scope_hash}",
            f"target: {receipt.target}",
            f"target_schema: {receipt.target_schema}",
            f"proposed_payload: {_compact_json(receipt.proposed_payload)}",
            f"selected_reference_ids: {', '.join(receipt.selected_reference_ids)}",
            f"evidence_event_ids: {', '.join(receipt.evidence_event_ids)}",
            f"proposal_hash: {receipt.proposal_hash}",
            f"confirmation_method: {receipt.confirmation_method}",
            "operator_confirmation_recorded: true",
            *_proposal_boundary(),
        ]
    )


def format_learning_proposal_doctor(
    session: OperatorReviewedLearningProposalSession,
    candidates: dict[str, CognitiveLearningPreviewCandidate],
    decisions: OperatorReviewedLearningDecisionSession,
) -> str:
    report = session.doctor(candidates, decisions)
    lines = [
        "Proto-Mind Learning Promotion Proposal Doctor v1",
        f"Status: {report.status}",
        f"proposals: {report.proposal_count}/{LEARNING_PROPOSAL_MAX_RECEIPTS}",
        f"memory: {report.memory_count}",
        f"skill: {report.skill_count}",
    ]
    lines.extend(f"- ERROR: {issue}" for issue in report.issues)
    lines.extend(f"- WARN: {warning}" for warning in report.warnings)
    if not report.issues and not report.warnings:
        lines.append("- Proposal digests, schemas, confirmations, and no-apply boundaries are healthy.")
    lines.extend(_proposal_boundary())
    return "\n".join(lines)


def _parse_proposal_request(
    command: str,
    *,
    command_name: str,
    require_token: bool,
) -> LearningProposalRequest | str:
    parts = command.split()
    prefix_parts = command_name.split()
    usage = (
        f"Usage: {command_name} <candidate_id> "
        f"{'<exact token> ' if require_token else ''}--target memory|skill "
        "[--memory <id>]... [--skill <id>]..."
    )
    required = len(prefix_parts) + (2 if require_token else 1)
    if len(parts) < required:
        return usage
    if [part.casefold() for part in parts[: len(prefix_parts)]] != [
        part.casefold() for part in prefix_parts
    ]:
        return usage
    candidate_id = parts[len(prefix_parts)]
    token = parts[len(prefix_parts) + 1] if require_token else ""
    if require_token and (not token or token.startswith("--")):
        return usage
    remainder_index = len(prefix_parts) + (2 if require_token else 1)
    reconstructed = " ".join([command_name, candidate_id, *parts[remainder_index:]])
    parsed = parse_learning_eligibility_request(
        reconstructed,
        command_name=command_name,
    )
    if isinstance(parsed, str):
        return usage
    return LearningProposalRequest(eligibility=parsed, token=token)


def _target_payload(
    candidate: CognitiveLearningPreviewCandidate,
    target: str,
) -> dict[str, Any]:
    if target == "memory":
        return {
            "schema": LEARNING_PROPOSAL_SCHEMAS[target],
            "content": candidate.text,
            "type": "lesson",
            "importance": 0.7,
            "source": "experience_learning_proposal",
            "tags": ["experience", "operator_reviewed"],
            "confidence": _confidence_value(candidate.confidence),
        }
    return {
        "schema": LEARNING_PROPOSAL_SCHEMAS[target],
        "name": compact_preview(candidate.text, 96),
        "summary": candidate.text,
        "body": "",
        "status": "active",
        "category": "other",
        "source": "experience_learning_proposal",
        "tags": ["experience", "operator_reviewed"],
    }


def _valid_target_payload(target: str, payload: object) -> bool:
    if not isinstance(payload, dict) or payload.get("schema") != LEARNING_PROPOSAL_SCHEMAS.get(target):
        return False
    if target == "memory":
        return (
            isinstance(payload.get("content"), str)
            and bool(payload["content"].strip())
            and payload.get("type") == "lesson"
            and payload.get("source") == "experience_learning_proposal"
        )
    if target == "skill":
        return (
            isinstance(payload.get("name"), str)
            and bool(payload["name"].strip())
            and isinstance(payload.get("summary"), str)
            and payload.get("status") == "active"
            and payload.get("source") == "experience_learning_proposal"
        )
    return False


def _proposal_hash_from_receipt(receipt: dict[str, Any]) -> str:
    keys = (
        "candidate_id",
        "candidate_hash",
        "decision_id",
        "eligibility_receipt_id",
        "eligibility_hash",
        "eligibility_status",
        "selected_scope_hash",
        "target",
        "target_schema",
        "proposed_payload",
        "requested_memory_ids",
        "requested_skill_ids",
        "selected_reference_ids",
        "evidence_event_ids",
        "source_kinds",
        "confidence",
    )
    return _hash_json({key: receipt.get(key) for key in keys})


def _canonical_propose_command(
    blueprint: LearningPromotionProposalBlueprint,
    token: str,
) -> str:
    parts = [
        "/experience learning propose",
        blueprint.candidate_id,
        token,
        "--target",
        blueprint.target,
    ]
    for memory_id in blueprint.requested_memory_ids:
        parts.extend(["--memory", memory_id])
    for skill_id in blueprint.requested_skill_ids:
        parts.extend(["--skill", skill_id])
    return " ".join(parts)


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
            "Proto-Mind Learning Promotion Proposal v1",
            "Status: NOT FOUND",
            f"- Candidate {candidate_id!r} is absent from current process evidence.",
            f"- Available candidates: {', '.join(candidates) or 'none'}",
            *_proposal_boundary(),
        ]
    )


def _not_proposable(message: str) -> str:
    return "\n".join(
        [
            "Proto-Mind Learning Promotion Proposal Preview v1",
            "Status: NOT PROPOSABLE",
            f"- {message}",
            *_proposal_boundary(),
        ]
    )


def _proposal_refused(message: str) -> str:
    return "\n".join(
        [
            "Proto-Mind Learning Promotion Proposal Receipt v1",
            "Status: REFUSED",
            f"- {message}",
            *_proposal_boundary(),
        ]
    )


def _error_output(message: str) -> str:
    return "\n".join(
        [
            "Proto-Mind Learning Promotion Proposal v1",
            "Status: ERROR",
            f"- {message}",
            *_proposal_boundary(),
        ]
    )


def _confidence_value(value: str) -> float:
    return {"high": 0.9, "medium": 0.7, "low": 0.5}.get(value, 0.5)


def _hash_json(payload: object) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _compact_json(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _proposal_boundary() -> list[str]:
    return [
        "scope_limited: true",
        "global_duplicate_check_performed: false",
        "future_apply_ready: false",
        "executable: false",
        "promotion_performed: false",
        "apply_performed: false",
        "persistence_performed: false",
        "- Process-memory proposal only; no domain store, queue, file, or external action changed.",
    ]
