from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
from threading import RLock
from typing import Any, Iterable
from uuid import uuid4

from proto_mind.experience_ledger import ExperienceEvent
from proto_mind.experience_learning_lifecycle import (
    LearningLifecycleDecisionReceipt,
    OperatorReviewedLearningLifecycleSession,
)
from proto_mind.experience_learning_lifecycle_readiness import (
    LEARNING_LIFECYCLE_APPLY_ENGINE_INSTALLED,
    LearningLifecycleApplyReadiness,
    LearningLifecycleReadinessError,
    LearningLifecycleReadinessReport,
)
from proto_mind.memory_provenance import verify_memory_provenance
from proto_mind.memory_store import MemoryStore
from proto_mind.models import MemoryRecord


LEARNING_LIFECYCLE_APPLY_VERSION = 1
LEARNING_LIFECYCLE_APPLY_MODE = "single_exact_confirmed_lesson_transition"
LEARNING_LIFECYCLE_APPLY_MAX_RECEIPTS = 1


@dataclass(frozen=True)
class LearningLifecycleApplyReview:
    status: str
    lifecycle_receipt_id: str
    lesson_memory_id: str
    replacement_memory_id: str
    decision: str
    review_hash: str
    before_store_sha256: str
    transition_expected_record_mutations: int
    checks: dict[str, bool]
    issues: list[str]
    warnings: list[str]
    confirmable: bool


@dataclass(frozen=True)
class LearningLifecycleApplyReceipt:
    id: str
    applied_at: str
    lifecycle_receipt_id: str
    lesson_memory_id: str
    replacement_memory_id: str
    decision: str
    selected_signal_id: str
    review_hash: str
    before_store_sha256: str
    after_store_sha256: str
    before_record_hash: str
    after_record_hash: str
    replacement_record_hash: str
    previous_lesson_state: dict[str, Any]
    resulting_lesson_state: dict[str, Any]
    expected_record_mutations: int
    actual_record_mutations: int
    record_verified: bool
    replacement_verified: bool
    durable_provenance_preserved: bool
    confirmation_method: str
    confirmation_token_hash: str
    apply_result: str
    rollback_suggestion: str
    run_once_guard: bool = True
    transition_performed: bool = True
    memory_mutation_performed: bool = False
    skill_mutation_performed: bool = False
    experience_mutation_performed: bool = False
    batch_apply_performed: bool = False
    receipt_persistence: str = "process_memory_only"
    durable_lifecycle_state: str = "existing_memory_record_fields"
    receipt_hash: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class LearningLifecycleApplyDoctorReport:
    status: str
    receipt_count: int
    keep_count: int
    reject_count: int
    supersede_count: int
    issues: list[str]
    warnings: list[str]


class LearningLifecycleApplyError(RuntimeError):
    pass


class OperatorReviewedLearningLifecycleApplySession:
    """Applies at most one exact, revalidated lesson lifecycle transition per process."""

    def __init__(self) -> None:
        self._receipts: dict[str, LearningLifecycleApplyReceipt] = {}
        self._lock = RLock()

    def snapshot(self) -> tuple[dict[str, Any], ...]:
        with self._lock:
            return tuple(deepcopy(receipt.to_dict()) for receipt in self._receipts.values())

    def get(self, identifier: str) -> LearningLifecycleApplyReceipt | None:
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
                        receipt.lifecycle_receipt_id,
                        receipt.lesson_memory_id,
                    }
                ),
                None,
            )

    def review(
        self,
        receipt: LearningLifecycleDecisionReceipt,
        *,
        events: Iterable[ExperienceEvent | dict[str, Any]],
        memory_store: MemoryStore,
    ) -> LearningLifecycleApplyReview:
        with self._lock:
            return self._review_locked(receipt, events=events, memory_store=memory_store)

    def apply(
        self,
        receipt: LearningLifecycleDecisionReceipt,
        *,
        token: str,
        events: Iterable[ExperienceEvent | dict[str, Any]],
        memory_store: MemoryStore,
    ) -> LearningLifecycleApplyReceipt:
        with self._lock:
            review = self._review_locked(receipt, events=events, memory_store=memory_store)
            if not review.confirmable:
                raise LearningLifecycleApplyError("; ".join(review.issues) or review.status)
            expected_token = learning_lifecycle_apply_confirmation_token(review)
            if token != expected_token:
                raise LearningLifecycleApplyError("Lifecycle apply confirmation token mismatch.")

            try:
                before_bytes = memory_store.persistent_path.read_bytes()
                original_records = memory_store.load_persistent_memory()
            except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
                raise LearningLifecycleApplyError(
                    f"Persistent memory store is unreadable: {exc}"
                ) from exc
            if _hash_bytes(before_bytes) != review.before_store_sha256:
                raise LearningLifecycleApplyError(
                    "Persistent memory changed after lifecycle apply confirmation preview."
                )

            target_index = _unique_record_index(original_records, receipt.lesson_memory_id)
            old_record = original_records[target_index]
            previous_state = _lifecycle_state(old_record)
            applied_at = datetime.now(UTC).isoformat()
            replacement_hash = ""
            replacement_verified = receipt.decision != "supersede"

            if receipt.decision == "keep":
                after_records = memory_store.load_persistent_memory()
                after_bytes = memory_store.persistent_path.read_bytes()
                if after_bytes != before_bytes or _record_dicts(after_records) != _record_dicts(
                    original_records
                ):
                    raise LearningLifecycleApplyError(
                        "Keep transition failed byte-stable no-op verification."
                    )
                verified_record = after_records[target_index]
                actual_mutations = 0
                apply_result = "keep_verified_noop"
            else:
                updated_records = deepcopy(original_records)
                replacement_id = receipt.replacement_memory_id or None
                updated_records[target_index] = replace(
                    updated_records[target_index],
                    active=False,
                    superseded_by=replacement_id,
                    superseded_at=applied_at,
                    superseded_reason=(
                        "verified_learning_outcome_supersede"
                        if receipt.decision == "supersede"
                        else "verified_learning_outcome_reject"
                    ),
                )
                try:
                    memory_store.save_persistent_memory(updated_records)
                    verified_record, actual_mutations, replacement_hash = _verify_transition(
                        memory_store,
                        original_records=original_records,
                        expected_records=updated_records,
                        lesson_memory_id=receipt.lesson_memory_id,
                        replacement_memory_id=receipt.replacement_memory_id,
                    )
                    replacement_verified = receipt.decision != "supersede" or bool(
                        replacement_hash
                    )
                except (
                    OSError,
                    TypeError,
                    ValueError,
                    json.JSONDecodeError,
                    LearningLifecycleApplyError,
                ) as exc:
                    _restore_original_bytes(memory_store.persistent_path, before_bytes)
                    try:
                        restored = memory_store.load_persistent_memory()
                    except (OSError, TypeError, ValueError, json.JSONDecodeError) as rollback_exc:
                        raise LearningLifecycleApplyError(
                            "Post-write verification failed and byte rollback is unreadable: "
                            f"{rollback_exc}"
                        ) from exc
                    if (
                        memory_store.persistent_path.read_bytes() != before_bytes
                        or _record_dicts(restored) != _record_dicts(original_records)
                    ):
                        raise LearningLifecycleApplyError(
                            "Post-write verification failed and byte rollback did not restore "
                            "the exact original store."
                        ) from exc
                    raise LearningLifecycleApplyError(
                        "Post-write verification failed; exact original memory bytes were restored: "
                        f"{exc}"
                    ) from exc
                apply_result = f"{receipt.decision}_soft_transition_verified"
                after_bytes = memory_store.persistent_path.read_bytes()

            provenance_check = verify_memory_provenance(verified_record)
            if not provenance_check.verified or verified_record.provenance != old_record.provenance:
                if receipt.decision != "keep":
                    _restore_original_bytes(memory_store.persistent_path, before_bytes)
                raise LearningLifecycleApplyError(
                    "Lifecycle transition did not preserve the immutable learning provenance."
                )

            material = {
                "applied_at": applied_at,
                "lifecycle_receipt_id": receipt.id,
                "lesson_memory_id": receipt.lesson_memory_id,
                "replacement_memory_id": receipt.replacement_memory_id,
                "decision": receipt.decision,
                "selected_signal_id": receipt.selected_signal_id,
                "review_hash": receipt.review_hash,
                "before_store_sha256": review.before_store_sha256,
                "after_store_sha256": _hash_bytes(after_bytes),
                "before_record_hash": _hash_json(old_record.to_dict()),
                "after_record_hash": _hash_json(verified_record.to_dict()),
                "replacement_record_hash": replacement_hash,
                "previous_lesson_state": previous_state,
                "resulting_lesson_state": _lifecycle_state(verified_record),
                "expected_record_mutations": review.transition_expected_record_mutations,
                "actual_record_mutations": actual_mutations,
                "record_verified": True,
                "replacement_verified": replacement_verified,
                "durable_provenance_preserved": True,
                "confirmation_method": "exact_current_lifecycle_apply_token",
                "confirmation_token_hash": hashlib.sha256(token.encode("utf-8")).hexdigest(),
                "apply_result": apply_result,
                "rollback_suggestion": _rollback_suggestion(receipt, previous_state),
                "run_once_guard": True,
                "transition_performed": True,
                "memory_mutation_performed": receipt.decision != "keep",
                "skill_mutation_performed": False,
                "experience_mutation_performed": False,
                "batch_apply_performed": False,
                "receipt_persistence": "process_memory_only",
                "durable_lifecycle_state": "existing_memory_record_fields",
            }
            receipt_hash = _hash_json(material)
            apply_receipt = LearningLifecycleApplyReceipt(
                id=f"learnlifeapply_{receipt_hash[:16]}",
                **material,
                receipt_hash=receipt_hash,
            )
            self._receipts[receipt.lesson_memory_id] = apply_receipt
            return apply_receipt

    def doctor(self, memory_store: MemoryStore) -> LearningLifecycleApplyDoctorReport:
        receipts = self.snapshot()
        issues: list[str] = []
        warnings: list[str] = []
        if len(receipts) > LEARNING_LIFECYCLE_APPLY_MAX_RECEIPTS:
            issues.append("Process-memory lifecycle apply receipt limit is exceeded.")
        try:
            records = memory_store.load_persistent_memory()
        except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
            return LearningLifecycleApplyDoctorReport(
                status="ERROR",
                receipt_count=len(receipts),
                keep_count=0,
                reject_count=0,
                supersede_count=0,
                issues=[f"Persistent memory store is unreadable: {exc}"],
                warnings=[],
            )
        by_id = {record.id: record for record in records}
        counts = {"keep": 0, "reject": 0, "supersede": 0}
        seen_ids: set[str] = set()
        for item in receipts:
            label = str(item.get("id") or "")
            decision = str(item.get("decision") or "")
            if decision in counts:
                counts[decision] += 1
            else:
                issues.append(f"Lifecycle apply receipt {label or '<missing>'} has invalid decision.")
            if not label or label in seen_ids:
                issues.append("Lifecycle apply receipt id is missing or duplicated.")
            seen_ids.add(label)
            if item.get("receipt_hash") != _receipt_hash_from_dict(item):
                issues.append(f"Lifecycle apply receipt {label} hash does not match its fields.")
            if item.get("run_once_guard") is not True or item.get("batch_apply_performed") is not False:
                issues.append(f"Lifecycle apply receipt {label} violates run-once boundaries.")
            if item.get("skill_mutation_performed") is not False or item.get(
                "experience_mutation_performed"
            ) is not False:
                issues.append(f"Lifecycle apply receipt {label} claims an out-of-scope mutation.")
            expected = 0 if decision == "keep" else 1
            if item.get("expected_record_mutations") != expected or item.get(
                "actual_record_mutations"
            ) != expected:
                issues.append(f"Lifecycle apply receipt {label} has an invalid mutation count.")
            if item.get("memory_mutation_performed") is not (decision != "keep"):
                issues.append(f"Lifecycle apply receipt {label} has an invalid mutation flag.")
            record = by_id.get(str(item.get("lesson_memory_id") or ""))
            if record is None:
                issues.append(f"Lifecycle apply receipt {label} points to a missing lesson.")
                continue
            current_hash = _hash_json(record.to_dict())
            if current_hash != item.get("after_record_hash"):
                warnings.append(
                    f"Lifecycle lesson {record.id} changed after process receipt {label}."
                )
                continue
            if verify_memory_provenance(record).verified is not True:
                issues.append(f"Lifecycle lesson {record.id} has invalid durable provenance.")
            if decision == "keep" and not record.active:
                issues.append(f"Keep receipt {label} does not preserve an active lesson.")
            if decision in {"reject", "supersede"} and record.active:
                issues.append(f"Terminal lifecycle receipt {label} still has an active old lesson.")
            if decision == "supersede":
                replacement = by_id.get(str(item.get("replacement_memory_id") or ""))
                if replacement is None or not replacement.active:
                    issues.append(f"Supersede receipt {label} lacks its active replacement.")
                elif _hash_json(replacement.to_dict()) != item.get("replacement_record_hash"):
                    warnings.append(f"Supersede replacement for receipt {label} changed later.")

        status = "ERROR" if issues else "WARN" if warnings else "OK"
        return LearningLifecycleApplyDoctorReport(
            status=status,
            receipt_count=len(receipts),
            keep_count=counts["keep"],
            reject_count=counts["reject"],
            supersede_count=counts["supersede"],
            issues=_dedupe(issues),
            warnings=_dedupe(warnings),
        )

    def _review_locked(
        self,
        receipt: LearningLifecycleDecisionReceipt,
        *,
        events: Iterable[ExperienceEvent | dict[str, Any]],
        memory_store: MemoryStore,
    ) -> LearningLifecycleApplyReview:
        readiness = LearningLifecycleApplyReadiness(
            memory_store=memory_store,
            events=events,
        ).review(receipt)
        checks = {
            "current_readiness_passed": readiness.ready_for_design_review,
            "bounded_lifecycle_engine_installed": LEARNING_LIFECYCLE_APPLY_ENGINE_INSTALLED,
            "known_transition": receipt.decision in {"keep", "reject", "supersede"},
            "single_apply_slot_available": len(self._receipts)
            < LEARNING_LIFECYCLE_APPLY_MAX_RECEIPTS,
            "lesson_not_applied_in_process": receipt.lesson_memory_id not in self._receipts,
            "persistent_store_hash_bound": readiness.persistent_store_sha256 != "unavailable",
        }
        issues = list(readiness.issues)
        messages = {
            "current_readiness_passed": "Current lifecycle decision no longer passes exact readiness.",
            "bounded_lifecycle_engine_installed": "Bounded lifecycle apply engine is not installed.",
            "known_transition": "Lifecycle decision is not keep, reject, or supersede.",
            "single_apply_slot_available": "This process already used its single lifecycle apply slot.",
            "lesson_not_applied_in_process": "This lesson was already lifecycle-applied in this process.",
            "persistent_store_hash_bound": "Persistent memory SHA-256 is unavailable.",
        }
        for name, passed in checks.items():
            if not passed:
                issues.append(messages[name])
        confirmable = all(checks.values()) and not issues
        return LearningLifecycleApplyReview(
            status="CONFIRMABLE" if confirmable else "NOT READY",
            lifecycle_receipt_id=receipt.id,
            lesson_memory_id=receipt.lesson_memory_id,
            replacement_memory_id=receipt.replacement_memory_id,
            decision=receipt.decision,
            review_hash=receipt.review_hash,
            before_store_sha256=readiness.persistent_store_sha256,
            transition_expected_record_mutations=(
                readiness.transition.expected_record_mutations
            ),
            checks=checks,
            issues=_dedupe(issues),
            warnings=_dedupe(readiness.warnings),
            confirmable=confirmable,
        )


def learning_lifecycle_apply_confirmation_token(
    review: LearningLifecycleApplyReview,
) -> str:
    material = {
        "lifecycle_receipt_id": review.lifecycle_receipt_id,
        "lesson_memory_id": review.lesson_memory_id,
        "replacement_memory_id": review.replacement_memory_id,
        "decision": review.decision,
        "review_hash": review.review_hash,
        "before_store_sha256": review.before_store_sha256,
    }
    return f"CONFIRM-LIFECYCLE-APPLY-{review.decision.upper()}-{_hash_json(material)[:12].upper()}"


def format_learning_lifecycle_apply_command(
    command: str,
    *,
    events: Iterable[ExperienceEvent | dict[str, Any]],
    memory_store: MemoryStore | None,
    lifecycle_session: OperatorReviewedLearningLifecycleSession,
    apply_session: OperatorReviewedLearningLifecycleApplySession,
) -> str | None:
    raw = command.strip()
    normalized = " ".join(raw.lower().split())
    prefixes = (
        "/experience learning lifecycle-apply-preview",
        "/experience learning lifecycle-apply-status",
        "/experience learning lifecycle-apply-receipt",
        "/experience learning lifecycle-apply-doctor",
        "/experience learning apply lifecycle",
    )
    if not any(normalized == prefix or normalized.startswith(prefix + " ") for prefix in prefixes):
        return None
    if any(marker in raw for marker in ("\n", ";", "&&", "||")):
        return _apply_error("Command chaining and multi-command input are not allowed.")
    if memory_store is None:
        return _apply_error("MemoryStore is unavailable from the shared handler.")

    if normalized == "/experience learning lifecycle-apply-status":
        return format_learning_lifecycle_apply_status(apply_session)
    if normalized == "/experience learning lifecycle-apply-doctor":
        if apply_session.snapshot():
            readiness_status = "APPLIED"
        else:
            try:
                readiness_status = LearningLifecycleApplyReadiness(
                    memory_store=memory_store,
                    events=events,
                ).doctor(lifecycle_session).status
            except LearningLifecycleReadinessError as exc:
                return _apply_error(str(exc))
        return format_learning_lifecycle_apply_doctor(
            apply_session.doctor(memory_store),
            readiness_status=readiness_status,
        )
    if normalized == "/experience learning lifecycle-apply-receipt":
        return "Usage: /experience learning lifecycle-apply-receipt <id>"
    if normalized.startswith("/experience learning lifecycle-apply-receipt "):
        identifier = raw[len("/experience learning lifecycle-apply-receipt") :].strip()
        if not identifier or " " in identifier:
            return "Usage: /experience learning lifecycle-apply-receipt <id>"
        return format_learning_lifecycle_apply_receipt(apply_session.get(identifier))
    if normalized == "/experience learning lifecycle-apply-preview":
        return "Usage: /experience learning lifecycle-apply-preview <memory_id|receipt_id>"
    if normalized.startswith("/experience learning lifecycle-apply-preview "):
        identifier = raw[len("/experience learning lifecycle-apply-preview") :].strip()
        if not identifier or " " in identifier:
            return "Usage: /experience learning lifecycle-apply-preview <memory_id|receipt_id>"
        receipt = lifecycle_session.get(identifier)
        if receipt is None:
            return _apply_not_found(identifier)
        try:
            review = apply_session.review(receipt, events=events, memory_store=memory_store)
        except LearningLifecycleReadinessError as exc:
            return _apply_error(str(exc))
        return format_learning_lifecycle_apply_preview(review)

    if normalized == "/experience learning apply lifecycle":
        return "Usage: /experience learning apply lifecycle <memory_id|receipt_id> <exact token>"
    parts = raw.split()
    if len(parts) != 6:
        return "Usage: /experience learning apply lifecycle <memory_id|receipt_id> <exact token>"
    identifier, token = parts[4], parts[5]
    receipt = lifecycle_session.get(identifier)
    if receipt is None:
        return _apply_not_found(identifier)
    try:
        applied = apply_session.apply(
            receipt,
            token=token,
            events=events,
            memory_store=memory_store,
        )
    except (LearningLifecycleApplyError, LearningLifecycleReadinessError) as exc:
        return _apply_error(str(exc))
    return format_learning_lifecycle_applied(applied)


def format_learning_lifecycle_apply_preview(review: LearningLifecycleApplyReview) -> str:
    lines = [
        "Proto-Mind Supervised Lesson Lifecycle Apply Preview v1",
        f"Status: {review.status}",
        f"lifecycle_receipt_id: {review.lifecycle_receipt_id}",
        f"lesson_memory_id: {review.lesson_memory_id}",
        f"replacement_memory_id: {review.replacement_memory_id or 'none'}",
        f"decision: {review.decision}",
        f"review_hash: {review.review_hash}",
        f"before_store_sha256: {review.before_store_sha256}",
        f"expected_record_mutations: {review.transition_expected_record_mutations}",
        "Checks:",
    ]
    lines.extend(f"- {name}: {str(value).lower()}" for name, value in review.checks.items())
    lines.extend(f"- ERROR: {issue}" for issue in review.issues)
    lines.extend(f"- WARN: {warning}" for warning in review.warnings)
    if review.confirmable:
        token = learning_lifecycle_apply_confirmation_token(review)
        lines.extend(
            [
                f"confirmation_token: {token}",
                "Exact apply command:",
                f"/experience learning apply lifecycle {review.lifecycle_receipt_id} {token}",
            ]
        )
    lines.extend(_apply_boundary())
    return "\n".join(lines)


def format_learning_lifecycle_applied(receipt: LearningLifecycleApplyReceipt) -> str:
    return "\n".join(
        [
            "Proto-Mind Supervised Lesson Lifecycle Apply Receipt v1",
            "Status: APPLIED AND VERIFIED",
            f"apply_id: {receipt.id}",
            f"lifecycle_receipt_id: {receipt.lifecycle_receipt_id}",
            f"lesson_memory_id: {receipt.lesson_memory_id}",
            f"replacement_memory_id: {receipt.replacement_memory_id or 'none'}",
            f"decision: {receipt.decision}",
            f"apply_result: {receipt.apply_result}",
            f"expected_record_mutations: {receipt.expected_record_mutations}",
            f"actual_record_mutations: {receipt.actual_record_mutations}",
            f"memory_mutation_performed: {str(receipt.memory_mutation_performed).lower()}",
            f"durable_provenance_preserved: {str(receipt.durable_provenance_preserved).lower()}",
            f"before_store_sha256: {receipt.before_store_sha256}",
            f"after_store_sha256: {receipt.after_store_sha256}",
            f"receipt_hash: {receipt.receipt_hash}",
            f"rollback_suggestion: {receipt.rollback_suggestion}",
            "- One exact lifecycle decision was handled; batch, shell, arbitrary dispatch, and auto-apply are disabled.",
        ]
    )


def format_learning_lifecycle_apply_status(
    session: OperatorReviewedLearningLifecycleApplySession,
) -> str:
    receipts = session.snapshot()
    lines = [
        "Proto-Mind Supervised Lesson Lifecycle Apply Status v1",
        f"Status: {'APPLIED' if receipts else 'EMPTY'}",
        f"mode: {LEARNING_LIFECYCLE_APPLY_MODE}",
        f"receipts: {len(receipts)}/{LEARNING_LIFECYCLE_APPLY_MAX_RECEIPTS}",
        f"apply_engine_installed: {str(LEARNING_LIFECYCLE_APPLY_ENGINE_INSTALLED).lower()}",
        "Receipts:",
    ]
    for receipt in receipts:
        lines.append(
            f"- {receipt['id']} | {receipt['decision']} | {receipt['lesson_memory_id']}"
        )
    if not receipts:
        lines.append("- none")
    lines.extend(_apply_boundary())
    return "\n".join(lines)


def format_learning_lifecycle_apply_receipt(
    receipt: LearningLifecycleApplyReceipt | None,
) -> str:
    if receipt is None:
        return _apply_error("Lifecycle apply receipt was not found in this process.")
    lines = [
        "Proto-Mind Supervised Lesson Lifecycle Apply Receipt v1",
        "Status: FOUND",
    ]
    lines.extend(f"{key}: {_compact(value)}" for key, value in receipt.to_dict().items())
    lines.extend(_apply_boundary())
    return "\n".join(lines)


def format_learning_lifecycle_apply_doctor(
    report: LearningLifecycleApplyDoctorReport,
    *,
    readiness_status: str,
) -> str:
    overall = _worst_status(report.status, readiness_status)
    lines = [
        "Proto-Mind Supervised Lesson Lifecycle Apply Doctor v1",
        f"Status: {overall}",
        f"readiness_doctor: {readiness_status}",
        f"apply_receipt_doctor: {report.status}",
        f"receipts: {report.receipt_count}/{LEARNING_LIFECYCLE_APPLY_MAX_RECEIPTS}",
        f"keep: {report.keep_count}",
        f"reject: {report.reject_count}",
        f"supersede: {report.supersede_count}",
        "single_apply_per_process: true",
        "batch_apply_enabled: false",
        "automatic_apply_enabled: false",
    ]
    lines.extend(f"- ERROR: {issue}" for issue in report.issues)
    lines.extend(f"- WARN: {warning}" for warning in report.warnings)
    if not report.issues and not report.warnings:
        lines.append("- Exact gate, receipt hash, transition scope, and durable provenance are healthy.")
    lines.extend(_apply_boundary())
    return "\n".join(lines)


def _verify_transition(
    memory_store: MemoryStore,
    *,
    original_records: list[MemoryRecord],
    expected_records: list[MemoryRecord],
    lesson_memory_id: str,
    replacement_memory_id: str,
) -> tuple[MemoryRecord, int, str]:
    current = memory_store.load_persistent_memory()
    original_dicts = _record_dicts(original_records)
    expected_dicts = _record_dicts(expected_records)
    current_dicts = _record_dicts(current)
    if current_dicts != expected_dicts:
        raise LearningLifecycleApplyError("Persistent records do not match the exact transition payload.")
    if [record.id for record in current] != [record.id for record in original_records]:
        raise LearningLifecycleApplyError("Lifecycle transition changed memory ids or record order.")
    changed = [
        index
        for index, (before, after) in enumerate(zip(original_dicts, current_dicts, strict=True))
        if before != after
    ]
    if len(changed) != 1 or current[changed[0]].id != lesson_memory_id:
        raise LearningLifecycleApplyError("Lifecycle transition changed records outside the exact lesson.")
    target = current[changed[0]]
    if target.active:
        raise LearningLifecycleApplyError("Lifecycle transition did not deactivate the old lesson.")
    if target.provenance != original_records[changed[0]].provenance:
        raise LearningLifecycleApplyError("Lifecycle transition changed immutable provenance.")
    if not verify_memory_provenance(target).verified:
        raise LearningLifecycleApplyError("Lifecycle lesson provenance no longer verifies.")

    replacement_hash = ""
    if replacement_memory_id:
        replacement = next((record for record in current if record.id == replacement_memory_id), None)
        original_replacement = next(
            (record for record in original_records if record.id == replacement_memory_id),
            None,
        )
        if (
            replacement is None
            or original_replacement is None
            or replacement.to_dict() != original_replacement.to_dict()
            or not replacement.active
            or not verify_memory_provenance(replacement).verified
        ):
            raise LearningLifecycleApplyError("Supersede replacement changed or no longer verifies.")
        replacement_hash = _hash_json(replacement.to_dict())
    return target, len(changed), replacement_hash


def _unique_record_index(records: list[MemoryRecord], record_id: str) -> int:
    matches = [index for index, record in enumerate(records) if record.id == record_id]
    if len(matches) != 1:
        raise LearningLifecycleApplyError(
            f"Expected exactly one persistent lesson {record_id!r}; found {len(matches)}."
        )
    return matches[0]


def _restore_original_bytes(path: Path, payload: bytes) -> None:
    temp_path = path.with_name(f".{path.name}.{uuid4().hex}.lifecycle-rollback.tmp")
    try:
        temp_path.write_bytes(payload)
        temp_path.replace(path)
    except OSError as exc:
        try:
            temp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise LearningLifecycleApplyError(f"Atomic lifecycle rollback failed: {exc}") from exc


def _lifecycle_state(record: MemoryRecord) -> dict[str, Any]:
    return {
        "active": record.active,
        "superseded_by": record.superseded_by,
        "superseded_at": record.superseded_at,
        "superseded_reason": record.superseded_reason,
    }


def _rollback_suggestion(
    receipt: LearningLifecycleDecisionReceipt,
    previous_state: dict[str, Any],
) -> str:
    if receipt.decision == "keep":
        return "No rollback required; keep was a verified no-op."
    return (
        "Manual review required before reactivation; prior state was "
        f"{json.dumps(previous_state, ensure_ascii=False, sort_keys=True)}."
    )


def _record_dicts(records: list[MemoryRecord]) -> list[dict[str, Any]]:
    return [record.to_dict() for record in records]


def _receipt_hash_from_dict(receipt: dict[str, Any]) -> str:
    material = {key: value for key, value in receipt.items() if key not in {"id", "receipt_hash"}}
    return _hash_json(material)


def _hash_json(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _hash_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _compact(value: object) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)


def _apply_not_found(identifier: str) -> str:
    return _apply_error(f"Lifecycle decision receipt {identifier!r} was not found in this process.")


def _apply_error(message: str) -> str:
    return "\n".join(
        [
            "Proto-Mind Supervised Lesson Lifecycle Apply Error",
            "Status: ERROR",
            f"- {message}",
            *_apply_boundary(),
        ]
    )


def _apply_boundary() -> list[str]:
    return [
        "Boundary:",
        "- One exact operator-confirmed lifecycle transition per process; no batch or automatic apply.",
        "- Keep is a byte-stable no-op; reject/supersede may change only the exact old lesson lifecycle fields.",
        "- Learning provenance remains immutable; post-write failure triggers byte-exact rollback.",
        "- No skill, Experience event, queue, export, Context Injection, model/API, shell, or arbitrary command changed.",
    ]


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def _worst_status(*statuses: str) -> str:
    normalized = [status.upper() for status in statuses]
    if any("ERROR" in status for status in normalized):
        return "ERROR"
    if any("WARN" in status or "NOT READY" in status for status in normalized):
        return "WARN"
    return "OK"
