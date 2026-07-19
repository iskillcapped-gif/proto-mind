from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import hashlib
import json
from threading import RLock
from typing import Any

from proto_mind.experience_learning_bridge import (
    CognitiveLearningBridgeError,
    CognitiveLearningPreviewCandidate,
    OperatorReviewedLearningBridge,
)
from proto_mind.experience_learning_decision import OperatorReviewedLearningDecisionSession
from proto_mind.experience_learning_proposal import (
    LearningPromotionProposalReceipt,
    OperatorReviewedLearningProposalSession,
)
from proto_mind.experience_learning_readiness import (
    LearningPromotionApplyReadiness,
    format_learning_apply_doctor,
)
from proto_mind.memory_store import MemoryStore
from proto_mind.models import MemoryRecord
from proto_mind.skill_library import SkillLibrary


LEARNING_MEMORY_APPLY_VERSION = 1
LEARNING_MEMORY_APPLY_MODE = "single_fresh_confirmed_memory_lesson"
LEARNING_MEMORY_APPLY_MAX_RECEIPTS = 1
LEARNING_MEMORY_APPLY_MAX_AGE_SECONDS = 15 * 60
LEARNING_MEMORY_APPLY_ENGINE_INSTALLED = True


@dataclass(frozen=True)
class LearningMemoryApplyReview:
    status: str
    proposal_id: str
    candidate_id: str
    target: str
    target_schema: str
    proposal_hash: str
    before_store_sha256: str
    created_record_id: str
    proposal_age_seconds: int | None
    checks: dict[str, bool]
    issues: list[str]
    warnings: list[str]
    confirmable: bool


@dataclass(frozen=True)
class LearningMemoryApplyReceipt:
    id: str
    applied_at: str
    proposal_id: str
    proposal_hash: str
    candidate_id: str
    candidate_hash: str
    decision_id: str
    eligibility_receipt_id: str
    selected_scope_hash: str
    target: str
    target_schema: str
    payload_hash: str
    before_store_sha256: str
    after_store_sha256: str
    created_record_id: str
    created_record_hash: str
    record_verified: bool
    confirmation_method: str
    confirmation_token_hash: str
    apply_result: str
    rollback_suggestion: str
    evidence_event_ids: list[str]
    run_once_guard: bool = True
    target_execution_performed: bool = True
    memory_mutation_performed: bool = True
    skill_mutation_performed: bool = False
    batch_apply_performed: bool = False
    receipt_persistence: str = "process_memory_only"
    receipt_hash: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class LearningMemoryApplyDoctorReport:
    status: str
    receipt_count: int
    applied_count: int
    issues: list[str]
    warnings: list[str]


class LearningMemoryApplyError(RuntimeError):
    pass


class OperatorReviewedLearningMemoryApplySession:
    """Applies at most one current memory lesson and retains its receipt in process memory."""

    def __init__(self) -> None:
        self._receipts: dict[str, LearningMemoryApplyReceipt] = {}
        self._lock = RLock()

    def snapshot(self) -> tuple[dict[str, Any], ...]:
        with self._lock:
            return tuple(deepcopy(receipt.to_dict()) for receipt in self._receipts.values())

    def get(self, identifier: str) -> LearningMemoryApplyReceipt | None:
        with self._lock:
            direct = self._receipts.get(identifier)
            if direct is not None:
                return direct
            return next(
                (
                    receipt
                    for receipt in self._receipts.values()
                    if identifier
                    in {
                        receipt.id,
                        receipt.proposal_id,
                        receipt.candidate_id,
                        receipt.created_record_id,
                    }
                ),
                None,
            )

    def review(
        self,
        proposal: LearningPromotionProposalReceipt,
        *,
        candidates: dict[str, CognitiveLearningPreviewCandidate],
        decisions: OperatorReviewedLearningDecisionSession,
        memory_store: MemoryStore,
        skill_library: SkillLibrary,
        now: datetime | None = None,
    ) -> LearningMemoryApplyReview:
        with self._lock:
            return self._review_locked(
                proposal,
                candidates=candidates,
                decisions=decisions,
                memory_store=memory_store,
                skill_library=skill_library,
                now=now,
            )

    def apply(
        self,
        proposal: LearningPromotionProposalReceipt,
        *,
        token: str,
        candidates: dict[str, CognitiveLearningPreviewCandidate],
        decisions: OperatorReviewedLearningDecisionSession,
        memory_store: MemoryStore,
        skill_library: SkillLibrary,
    ) -> LearningMemoryApplyReceipt:
        with self._lock:
            review = self._review_locked(
                proposal,
                candidates=candidates,
                decisions=decisions,
                memory_store=memory_store,
                skill_library=skill_library,
            )
            if not review.confirmable:
                raise LearningMemoryApplyError("; ".join(review.issues) or review.status)
            expected_token = learning_memory_apply_confirmation_token(review)
            if token != expected_token:
                raise LearningMemoryApplyError("Apply confirmation token mismatch.")

            try:
                original_records = memory_store.load_persistent_memory()
            except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
                raise LearningMemoryApplyError(f"Persistent memory store is unreadable: {exc}") from exc
            if _hash_file(memory_store.persistent_path) != review.before_store_sha256:
                raise LearningMemoryApplyError("Persistent memory changed after apply confirmation preview.")

            applied_at = datetime.now(UTC).isoformat()
            record = _record_from_proposal(proposal, review.created_record_id, applied_at)
            updated_records = [*original_records, record]
            try:
                memory_store.save_persistent_memory(updated_records)
                verified_record, after_store_sha256 = _verify_created_record(
                    memory_store,
                    record,
                    expected_count=len(updated_records),
                )
            except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
                try:
                    memory_store.save_persistent_memory(original_records)
                except (OSError, TypeError, ValueError):
                    raise LearningMemoryApplyError(
                        f"Post-write verification failed and rollback also failed: {exc}"
                    ) from exc
                raise LearningMemoryApplyError(
                    f"Post-write verification failed; original memory records were restored: {exc}"
                ) from exc

            material = {
                "applied_at": applied_at,
                "proposal_id": proposal.id,
                "proposal_hash": proposal.proposal_hash,
                "candidate_id": proposal.candidate_id,
                "candidate_hash": proposal.candidate_hash,
                "decision_id": proposal.decision_id,
                "eligibility_receipt_id": proposal.eligibility_receipt_id,
                "selected_scope_hash": proposal.selected_scope_hash,
                "target": proposal.target,
                "target_schema": proposal.target_schema,
                "payload_hash": _hash_json(proposal.proposed_payload),
                "before_store_sha256": review.before_store_sha256,
                "after_store_sha256": after_store_sha256,
                "created_record_id": verified_record.id,
                "created_record_hash": _hash_json(verified_record.to_dict()),
                "record_verified": True,
                "confirmation_method": "exact_apply_token",
                "confirmation_token_hash": hashlib.sha256(token.encode("utf-8")).hexdigest(),
                "apply_result": "memory_record_created_and_verified",
                "rollback_suggestion": f"/memory forget {verified_record.id}",
                "evidence_event_ids": list(proposal.evidence_event_ids),
                "run_once_guard": True,
                "target_execution_performed": True,
                "memory_mutation_performed": True,
                "skill_mutation_performed": False,
                "batch_apply_performed": False,
                "receipt_persistence": "process_memory_only",
            }
            receipt_hash = _hash_json(material)
            receipt = LearningMemoryApplyReceipt(
                id=f"learnapply_{receipt_hash[:16]}",
                **material,
                receipt_hash=receipt_hash,
            )
            self._receipts[proposal.id] = receipt
            return receipt

    def doctor(self, memory_store: MemoryStore) -> LearningMemoryApplyDoctorReport:
        with self._lock:
            receipts = self.snapshot()
        issues: list[str] = []
        warnings: list[str] = []
        if len(receipts) > LEARNING_MEMORY_APPLY_MAX_RECEIPTS:
            issues.append("Process-memory apply receipt limit is exceeded.")
        try:
            records = memory_store.load_persistent_memory()
        except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
            return LearningMemoryApplyDoctorReport(
                status="ERROR",
                receipt_count=len(receipts),
                applied_count=len(receipts),
                issues=[f"Persistent memory store is unreadable: {exc}"],
                warnings=[],
            )
        by_id = {record.id: record for record in records}
        ids: set[str] = set()
        for item in receipts:
            label = str(item.get("id") or "<missing>")
            if label == "<missing>" or label in ids:
                issues.append("Apply receipt id is missing or duplicated.")
            ids.add(label)
            if item.get("target") != "memory" or item.get("target_schema") != "memory.lesson.v1":
                issues.append(f"Apply receipt {label} is outside the memory.lesson.v1 pilot.")
            if item.get("record_verified") is not True:
                issues.append(f"Apply receipt {label} lacks record verification.")
            if item.get("run_once_guard") is not True or item.get("batch_apply_performed") is not False:
                issues.append(f"Apply receipt {label} violates single-run/single-record boundaries.")
            if item.get("memory_mutation_performed") is not True or item.get("skill_mutation_performed") is not False:
                issues.append(f"Apply receipt {label} reports an invalid mutation scope.")
            if item.get("receipt_hash") != _receipt_hash_from_dict(item):
                issues.append(f"Apply receipt {label} hash does not match its fields.")
            record_id = str(item.get("created_record_id") or "")
            record = by_id.get(record_id)
            if record is None:
                issues.append(f"Apply receipt {label} points to missing memory {record_id or '<missing>'}.")
            elif _hash_json(record.to_dict()) != item.get("created_record_hash"):
                if not record.active:
                    warnings.append(
                        f"Applied memory {record_id} is inactive; the rollback suggestion may have been used."
                    )
                else:
                    issues.append(f"Applied memory {record_id} no longer matches its verified receipt.")
        status = "ERROR" if issues else "WARN" if warnings else "OK"
        return LearningMemoryApplyDoctorReport(
            status=status,
            receipt_count=len(receipts),
            applied_count=len(receipts),
            issues=issues,
            warnings=warnings,
        )

    def _review_locked(
        self,
        proposal: LearningPromotionProposalReceipt,
        *,
        candidates: dict[str, CognitiveLearningPreviewCandidate],
        decisions: OperatorReviewedLearningDecisionSession,
        memory_store: MemoryStore,
        skill_library: SkillLibrary,
        now: datetime | None = None,
    ) -> LearningMemoryApplyReview:
        readiness = LearningPromotionApplyReadiness(
            memory_store=memory_store,
            skill_library=skill_library,
        ).review(proposal, candidates=candidates, decisions=decisions)
        checks = {
            "current_evidence_ready": readiness.ready_for_design_review,
            "memory_target_only": proposal.target == "memory",
            "memory_lesson_schema": proposal.target_schema == "memory.lesson.v1",
            "operator_proposal_confirmation": proposal.operator_confirmation_recorded,
            "fresh_proposal": False,
            "process_apply_slot_available": len(self._receipts) < LEARNING_MEMORY_APPLY_MAX_RECEIPTS,
            "proposal_not_applied": proposal.id not in self._receipts,
            "persistent_store_readable": False,
            "global_exact_duplicate_absent": False,
            "created_record_id_available": False,
        }
        issues = list(readiness.issues)
        warnings = [
            warning
            for warning in readiness.warnings
            if "no apply engine" not in warning.casefold()
            and "global novelty" not in warning.casefold()
        ]
        if not checks["memory_target_only"]:
            issues.append("Skill apply remains disabled; v3.4a accepts memory proposals only.")
        if not checks["memory_lesson_schema"]:
            issues.append("Target schema must be exactly memory.lesson.v1.")
        if not checks["operator_proposal_confirmation"]:
            issues.append("Proposal lacks its earlier exact-token operator confirmation.")
        if not checks["process_apply_slot_available"]:
            issues.append("This process already used its single supervised memory apply slot.")
        if not checks["proposal_not_applied"]:
            issues.append("Proposal was already applied in this process; run-once guard is active.")

        age_seconds, age_error = _proposal_age_seconds(proposal.created_at, now=now)
        checks["fresh_proposal"] = age_error == "" and age_seconds is not None and (
            -60 <= age_seconds <= LEARNING_MEMORY_APPLY_MAX_AGE_SECONDS
        )
        if not checks["fresh_proposal"]:
            issues.append(age_error or "Proposal is older than the 15-minute apply window.")

        before_hash = ""
        created_record_id = _created_record_id(proposal)
        try:
            records = memory_store.load_persistent_memory()
            before_hash = _hash_file(memory_store.persistent_path)
        except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
            issues.append(f"Persistent memory store is unreadable: {exc}")
        else:
            checks["persistent_store_readable"] = True
            normalized = _normalize_text(str(proposal.proposed_payload.get("content") or ""))
            duplicate = any(
                record.active and _normalize_text(record.content) == normalized for record in records
            )
            checks["global_exact_duplicate_absent"] = bool(normalized) and not duplicate
            if duplicate:
                issues.append("An active exact duplicate exists in persistent memory.")
            elif not normalized:
                issues.append("Proposed memory content is empty.")
            collision = any(record.id == created_record_id for record in records)
            checks["created_record_id_available"] = not collision
            if collision:
                issues.append(f"Deterministic memory id already exists: {created_record_id}.")

        confirmable = all(checks.values()) and not issues
        error = readiness.status == "ERROR" or not checks["persistent_store_readable"]
        return LearningMemoryApplyReview(
            status="CONFIRMABLE" if confirmable else "ERROR" if error else "NOT READY",
            proposal_id=proposal.id,
            candidate_id=proposal.candidate_id,
            target=proposal.target,
            target_schema=proposal.target_schema,
            proposal_hash=proposal.proposal_hash,
            before_store_sha256=before_hash,
            created_record_id=created_record_id,
            proposal_age_seconds=age_seconds,
            checks=checks,
            issues=_dedupe(issues),
            warnings=_dedupe(warnings),
            confirmable=confirmable,
        )


def learning_memory_apply_confirmation_token(review: LearningMemoryApplyReview) -> str:
    material = {
        "proposal_id": review.proposal_id,
        "proposal_hash": review.proposal_hash,
        "target_schema": review.target_schema,
        "before_store_sha256": review.before_store_sha256,
        "created_record_id": review.created_record_id,
    }
    return f"CONFIRM-LEARNING-APPLY-{_hash_json(material)[:12].upper()}"


def format_learning_memory_apply_command(
    command: str,
    *,
    bridge: OperatorReviewedLearningBridge,
    decisions: OperatorReviewedLearningDecisionSession,
    proposals: OperatorReviewedLearningProposalSession,
    applies: OperatorReviewedLearningMemoryApplySession,
    memory_store: MemoryStore | None,
    skill_library: SkillLibrary,
) -> str | None:
    raw = command.strip()
    normalized = " ".join(raw.lower().split())
    prefixes = (
        "/experience learning apply-preview",
        "/experience learning apply-status",
        "/experience learning apply-receipt",
        "/experience learning apply-doctor",
        "/experience learning apply",
    )
    if not any(normalized == prefix or normalized.startswith(prefix + " ") for prefix in prefixes):
        return None
    if memory_store is None:
        return _error_output("MemoryStore is unavailable from the shared handler.")
    if any(marker in raw for marker in ("\n", ";", "&&", "||")):
        return _refused_output("Command chaining and multi-command input are not allowed.")

    if normalized == "/experience learning apply-status":
        return format_learning_memory_apply_status(applies)
    if normalized == "/experience learning apply-receipt":
        return "Usage: /experience learning apply-receipt <apply_id|proposal_id|candidate_id>"
    if normalized.startswith("/experience learning apply-receipt "):
        identifier = raw[len("/experience learning apply-receipt") :].strip()
        receipt = applies.get(identifier)
        return format_learning_memory_apply_receipt(receipt, identifier=identifier)

    candidates, error = _candidate_map(bridge)
    if error:
        return error
    if normalized == "/experience learning apply-doctor":
        readiness = LearningPromotionApplyReadiness(
            memory_store=memory_store,
            skill_library=skill_library,
        ).doctor(proposals=proposals, candidates=candidates, decisions=decisions)
        return format_learning_memory_apply_doctor(
            readiness_text=format_learning_apply_doctor(readiness),
            report=applies.doctor(memory_store),
        )

    if normalized == "/experience learning apply-preview":
        return "Usage: /experience learning apply-preview <proposal_id|candidate_id>"
    if normalized.startswith("/experience learning apply-preview "):
        identifier = raw[len("/experience learning apply-preview") :].strip()
        proposal = proposals.get(identifier)
        if proposal is None:
            return _not_found_output(identifier)
        review = applies.review(
            proposal,
            candidates=candidates,
            decisions=decisions,
            memory_store=memory_store,
            skill_library=skill_library,
        )
        return format_learning_memory_apply_preview(review)

    if normalized == "/experience learning apply":
        return "Usage: /experience learning apply <proposal_id|candidate_id> <exact token>"
    parts = raw.split()
    if len(parts) != 5:
        return "Usage: /experience learning apply <proposal_id|candidate_id> <exact token>"
    identifier, token = parts[3], parts[4]
    proposal = proposals.get(identifier)
    if proposal is None:
        return _not_found_output(identifier)
    try:
        receipt = applies.apply(
            proposal,
            token=token,
            candidates=candidates,
            decisions=decisions,
            memory_store=memory_store,
            skill_library=skill_library,
        )
    except LearningMemoryApplyError as exc:
        return _refused_output(str(exc))
    return format_learning_memory_applied(receipt)


def format_learning_memory_apply_preview(review: LearningMemoryApplyReview) -> str:
    lines = [
        "Proto-Mind Supervised Memory Lesson Apply Preview v1",
        f"Status: {review.status}",
        f"proposal_id: {review.proposal_id}",
        f"candidate_id: {review.candidate_id}",
        f"target: {review.target}",
        f"target_schema: {review.target_schema}",
        f"proposal_hash: {review.proposal_hash}",
        f"proposal_age_seconds: {review.proposal_age_seconds if review.proposal_age_seconds is not None else 'unknown'}",
        f"before_store_sha256: {review.before_store_sha256 or 'unavailable'}",
        f"created_record_id: {review.created_record_id}",
        "Checks:",
    ]
    lines.extend(f"- {name}: {str(value).lower()}" for name, value in review.checks.items())
    lines.extend(f"- ERROR: {issue}" for issue in review.issues)
    lines.extend(f"- WARN: {warning}" for warning in review.warnings)
    if review.confirmable:
        token = learning_memory_apply_confirmation_token(review)
        lines.extend(
            [
                f"confirmation_token: {token}",
                "Exact apply command:",
                f"/experience learning apply {review.proposal_id} {token}",
            ]
        )
    lines.extend(_apply_boundary())
    return "\n".join(lines)


def format_learning_memory_applied(receipt: LearningMemoryApplyReceipt) -> str:
    return "\n".join(
        [
            "Proto-Mind Supervised Memory Lesson Apply Receipt v1",
            "Status: APPLIED AND VERIFIED",
            f"apply_id: {receipt.id}",
            f"proposal_id: {receipt.proposal_id}",
            f"created_record_id: {receipt.created_record_id}",
            f"applied_at: {receipt.applied_at}",
            f"before_store_sha256: {receipt.before_store_sha256}",
            f"after_store_sha256: {receipt.after_store_sha256}",
            f"created_record_hash: {receipt.created_record_hash}",
            f"receipt_hash: {receipt.receipt_hash}",
            "record_verified: true",
            "run_once_guard: true",
            f"rollback_suggestion: {receipt.rollback_suggestion}",
            "- Exactly one persistent memory lesson was created; no skill or other store changed.",
            "- Apply receipt is process-memory-only; inspect it before process exit.",
        ]
    )


def format_learning_memory_apply_status(
    applies: OperatorReviewedLearningMemoryApplySession,
) -> str:
    receipts = applies.snapshot()
    lines = [
        "Proto-Mind Supervised Memory Lesson Apply Status v1",
        f"Status: {'APPLIED' if receipts else 'EMPTY'}",
        f"mode: {LEARNING_MEMORY_APPLY_MODE}",
        f"receipts: {len(receipts)}/{LEARNING_MEMORY_APPLY_MAX_RECEIPTS}",
        f"apply_engine_installed: {str(LEARNING_MEMORY_APPLY_ENGINE_INSTALLED).lower()}",
        "Receipts:",
    ]
    if not receipts:
        lines.append("- none")
    for receipt in receipts:
        lines.append(
            f"- {receipt['id']} | proposal={receipt['proposal_id']} | memory={receipt['created_record_id']}"
        )
    lines.extend(_apply_boundary())
    return "\n".join(lines)


def format_learning_memory_apply_receipt(
    receipt: LearningMemoryApplyReceipt | None,
    *,
    identifier: str,
) -> str:
    if receipt is None:
        return "\n".join(
            [
                "Proto-Mind Supervised Memory Lesson Apply Receipt v1",
                "Status: NOT FOUND",
                f"- Apply/proposal/candidate {identifier!r} is absent from process memory.",
                *_apply_boundary(),
            ]
        )
    lines = [
        "Proto-Mind Supervised Memory Lesson Apply Receipt v1",
        "Status: FOUND",
    ]
    lines.extend(f"{key}: {_compact(value)}" for key, value in receipt.to_dict().items())
    lines.extend(_apply_boundary())
    return "\n".join(lines)


def format_learning_memory_apply_doctor(
    *,
    readiness_text: str,
    report: LearningMemoryApplyDoctorReport,
) -> str:
    readiness_status = _status_from_output(readiness_text)
    overall = _worst_status(readiness_status, report.status)
    lines = [
        "Proto-Mind Supervised Memory Lesson Apply Doctor v1",
        f"Status: {overall}",
        f"readiness_doctor: {readiness_status}",
        f"apply_receipt_doctor: {report.status}",
        f"receipts: {report.receipt_count}/{LEARNING_MEMORY_APPLY_MAX_RECEIPTS}",
        f"applied: {report.applied_count}",
        "memory_target_only: true",
        "skill_apply_enabled: false",
        "batch_apply_enabled: false",
    ]
    lines.extend(f"- ERROR: {issue}" for issue in report.issues)
    lines.extend(f"- WARN: {warning}" for warning in report.warnings)
    if not report.issues and not report.warnings:
        lines.append("- Single-record receipt, run-once, target scope, and record verification are healthy.")
    lines.extend(_apply_boundary())
    return "\n".join(lines)


def _record_from_proposal(
    proposal: LearningPromotionProposalReceipt,
    record_id: str,
    applied_at: str,
) -> MemoryRecord:
    payload = proposal.proposed_payload
    if proposal.target != "memory" or proposal.target_schema != "memory.lesson.v1":
        raise LearningMemoryApplyError("Only memory.lesson.v1 proposals are supported.")
    return MemoryRecord(
        id=record_id,
        content=str(payload["content"]),
        type=str(payload["type"]),
        importance=float(payload["importance"]),
        source=str(payload["source"]),
        tags=[str(tag) for tag in payload.get("tags", [])],
        timestamp=applied_at,
        last_used=None,
        usage_count=0,
        weight=1.0,
        active=True,
        confidence=float(payload["confidence"]),
        updated_at=applied_at,
    )


def _verify_created_record(
    memory_store: MemoryStore,
    expected: MemoryRecord,
    *,
    expected_count: int,
) -> tuple[MemoryRecord, str]:
    records = memory_store.load_persistent_memory()
    if len(records) != expected_count:
        raise ValueError("Persistent memory count does not match the one-record apply contract.")
    matches = [record for record in records if record.id == expected.id]
    if len(matches) != 1 or matches[0].to_dict() != expected.to_dict():
        raise ValueError("Created memory record does not match the fixed proposal payload.")
    return matches[0], _hash_file(memory_store.persistent_path)


def _candidate_map(
    bridge: OperatorReviewedLearningBridge,
) -> tuple[dict[str, CognitiveLearningPreviewCandidate], str]:
    try:
        reviews = bridge.review()
    except CognitiveLearningBridgeError as exc:
        return {}, _error_output(str(exc))
    candidates = {candidate.id: candidate for review in reviews for candidate in review.candidates}
    return candidates, ""


def _proposal_age_seconds(
    created_at: str,
    *,
    now: datetime | None,
) -> tuple[int | None, str]:
    try:
        created = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        if created.tzinfo is None:
            raise ValueError("timezone is missing")
    except (AttributeError, TypeError, ValueError) as exc:
        return None, f"Proposal created_at is invalid: {exc}"
    current = now or datetime.now(UTC)
    return int((current - created.astimezone(UTC)).total_seconds()), ""


def _created_record_id(proposal: LearningPromotionProposalReceipt) -> str:
    return f"mem_learn_{proposal.proposal_hash[:16]}"


def _receipt_hash_from_dict(receipt: dict[str, Any]) -> str:
    excluded = {"id", "receipt_hash"}
    return _hash_json({key: value for key, value in receipt.items() if key not in excluded})


def _hash_json(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _hash_file(path: Any) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _normalize_text(value: str) -> str:
    return " ".join(value.casefold().split())


def _compact(value: object) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return str(value)


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def _not_found_output(identifier: str) -> str:
    return "\n".join(
        [
            "Proto-Mind Supervised Memory Lesson Apply v1",
            "Status: NOT FOUND",
            f"- Proposal or candidate {identifier!r} is absent from process memory.",
            *_apply_boundary(),
        ]
    )


def _refused_output(reason: str) -> str:
    return "\n".join(
        [
            "Proto-Mind Supervised Memory Lesson Apply v1",
            "Status: REFUSED",
            f"- {reason}",
            *_apply_boundary(),
        ]
    )


def _error_output(reason: str) -> str:
    return "\n".join(
        [
            "Proto-Mind Supervised Memory Lesson Apply v1",
            "Status: ERROR",
            f"- {reason}",
            *_apply_boundary(),
        ]
    )


def _status_from_output(output: str) -> str:
    for line in output.splitlines():
        if line.startswith("Status: "):
            return line.removeprefix("Status: ").strip()
    return "ERROR"


def _worst_status(*statuses: str) -> str:
    if any(status == "ERROR" for status in statuses):
        return "ERROR"
    if any(status not in {"OK", "EMPTY"} for status in statuses):
        return "WARN"
    return "OK"


def _apply_boundary() -> list[str]:
    return [
        "Boundary:",
        f"- mode: {LEARNING_MEMORY_APPLY_MODE}",
        "- exactly one fresh exact-token memory.lesson.v1 apply per process",
        "- no skill apply, batch apply, shell, arbitrary dispatch, or autonomous promotion",
        "- preview/status/receipt/doctor are read-only; only the exact apply command writes memory",
    ]
