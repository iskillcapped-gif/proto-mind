from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

from proto_mind.command_registry import COMMAND_REGISTRY
from proto_mind.experience_ledger import ExperienceEvent
from proto_mind.experience_learning_lifecycle import (
    OUTCOME_DECISIONS,
    LearningLifecycleDecisionReceipt,
    OperatorReviewedLearningLifecycleSession,
    learning_outcome_review_hash,
)
from proto_mind.experience_learning_outcome import LearningOutcomeReview, LearningOutcomeReviewer
from proto_mind.memory_provenance import verify_memory_provenance
from proto_mind.memory_store import MemoryStore
from proto_mind.models import MemoryRecord


LEARNING_LIFECYCLE_READINESS_VERSION = 1
LEARNING_LIFECYCLE_READINESS_MODE = "read_only_current_lifecycle_revalidation"
LEARNING_LIFECYCLE_APPLY_ENGINE_INSTALLED = False


@dataclass(frozen=True)
class LearningLifecycleTransitionContract:
    decision: str
    operation: str
    expected_record_mutations: int
    rollback: str
    replacement_required: bool


@dataclass(frozen=True)
class LearningLifecycleReadinessReport:
    status: str
    receipt_id: str
    lesson_memory_id: str
    decision: str
    outcome_status: str
    replacement_memory_id: str
    stored_review_hash: str
    current_review_hash: str
    persistent_store_sha256: str
    transition: LearningLifecycleTransitionContract
    checks: dict[str, bool]
    issues: list[str]
    warnings: list[str]
    ready_for_design_review: bool
    lifecycle_engine_installed: bool = LEARNING_LIFECYCLE_APPLY_ENGINE_INSTALLED
    executable: bool = False
    mutation_performed: bool = False
    persistence_performed: bool = False


@dataclass(frozen=True)
class LearningLifecycleReadinessDoctorReport:
    status: str
    receipt_count: int
    ready_count: int
    not_ready_count: int
    error_count: int
    issues: list[str]
    warnings: list[str]


class LearningLifecycleReadinessError(RuntimeError):
    pass


class LearningLifecycleApplyReadiness:
    """Revalidates a lifecycle decision without installing a lifecycle writer."""

    def __init__(
        self,
        *,
        memory_store: MemoryStore,
        events: Iterable[ExperienceEvent | dict[str, Any]],
    ) -> None:
        self.memory_store = memory_store
        self.events = list(events)

    def review(
        self,
        receipt: LearningLifecycleDecisionReceipt,
    ) -> LearningLifecycleReadinessReport:
        working, persistent = self._load_records()
        records = [*working, *persistent]
        record_ids = [record.id for record in records]
        record = next(
            (item for item in persistent if item.id == receipt.lesson_memory_id),
            None,
        )
        current = LearningOutcomeReviewer(self.events, records).review(
            receipt.lesson_memory_id
        )
        provenance = verify_memory_provenance(record) if record is not None else None
        expected_decision = OUTCOME_DECISIONS.get(current.status)
        current_hash = learning_outcome_review_hash(current)
        transition = learning_lifecycle_transition_contract(receipt.decision)
        replacement = (
            next(
                (
                    item
                    for item in persistent
                    if item.id == receipt.replacement_memory_id
                ),
                None,
            )
            if receipt.replacement_memory_id
            else None
        )
        replacement_provenance = (
            verify_memory_provenance(replacement) if replacement is not None else None
        )
        replacement_valid = receipt.decision != "supersede" or bool(
            replacement is not None
            and replacement.id != receipt.lesson_memory_id
            and replacement.type == "lesson"
            and replacement.active
            and replacement_provenance is not None
            and replacement_provenance.verified
            and receipt.replacement_memory_id == current.replacement_memory_id
        )
        checks = {
            "receipt_safe": _receipt_is_safe(receipt),
            "record_ids_unique": len(record_ids) == len(set(record_ids)),
            "lesson_in_persistent_store": record is not None,
            "lesson_active": bool(record and record.active),
            "lesson_type": bool(record and record.type == "lesson"),
            "lesson_provenance_verified": bool(provenance and provenance.verified),
            "provenance_id_matches": bool(
                provenance and provenance.provenance_id == receipt.provenance_id
            ),
            "current_outcome_matches": expected_decision == receipt.decision,
            "outcome_status_matches": current.status == receipt.outcome_status,
            "current_review_hash_matches": current_hash == receipt.review_hash,
            "selected_signal_matches": (
                current.selected_signal_id == receipt.selected_signal_id
            ),
            "replacement_contract_valid": replacement_valid,
            "persistent_store_hash_available": (
                _hash_file(self.memory_store.persistent_path) != "unavailable"
            ),
            "lifecycle_apply_engine_absent": not LEARNING_LIFECYCLE_APPLY_ENGINE_INSTALLED,
        }
        issues: list[str] = []
        messages = {
            "receipt_safe": "Lifecycle receipt claims an unsafe or incomplete boundary.",
            "record_ids_unique": "Current memory snapshot contains duplicate record ids.",
            "lesson_in_persistent_store": "Lifecycle lesson is absent from persistent memory.",
            "lesson_active": "Lifecycle lesson is not currently active.",
            "lesson_type": "Lifecycle target is not a lesson record.",
            "lesson_provenance_verified": "Lifecycle lesson provenance does not verify.",
            "provenance_id_matches": "Current provenance id differs from the decision receipt.",
            "current_outcome_matches": "Current deterministic outcome no longer matches the recorded decision.",
            "outcome_status_matches": "Current outcome status differs from the decision receipt.",
            "current_review_hash_matches": "Current outcome evidence hash differs from the decision receipt.",
            "selected_signal_matches": "Current selected evidence signal differs from the decision receipt.",
            "replacement_contract_valid": "Supersede replacement is missing, inactive, unverified, or no longer current.",
            "persistent_store_hash_available": "Persistent memory SHA-256 is unavailable.",
            "lifecycle_apply_engine_absent": "A lifecycle apply engine is unexpectedly installed.",
        }
        for name, passed in checks.items():
            if not passed:
                issues.append(messages[name])

        ready = all(checks.values()) and not issues
        status = "READY FOR LIFECYCLE DESIGN REVIEW" if ready else "NOT READY"
        if not checks["receipt_safe"] or not checks["record_ids_unique"]:
            status = "ERROR"
        return LearningLifecycleReadinessReport(
            status=status,
            receipt_id=receipt.id,
            lesson_memory_id=receipt.lesson_memory_id,
            decision=receipt.decision,
            outcome_status=current.status,
            replacement_memory_id=receipt.replacement_memory_id,
            stored_review_hash=receipt.review_hash,
            current_review_hash=current_hash,
            persistent_store_sha256=_hash_file(self.memory_store.persistent_path),
            transition=transition,
            checks=checks,
            issues=issues,
            warnings=[
                "Readiness is bound to current process evidence and current persistent-store bytes.",
                "A future mutation would require a separate checkpointed milestone and fresh exact confirmation.",
            ],
            ready_for_design_review=ready,
        )

    def doctor(
        self,
        session: OperatorReviewedLearningLifecycleSession,
    ) -> LearningLifecycleReadinessDoctorReport:
        working, persistent = self._load_records()
        records = [*working, *persistent]
        reviewer = LearningOutcomeReviewer(self.events, records)
        current_reviews = {
            record.id: reviewer.review(record.id)
            for record in records
            if record.type == "lesson"
        }
        lifecycle_doctor = session.doctor(current_reviews)
        issues = list(lifecycle_doctor.issues)
        warnings = list(lifecycle_doctor.warnings)
        reports: list[LearningLifecycleReadinessReport] = []
        for item in session.snapshot():
            receipt = session.get(str(item.get("id") or ""))
            if receipt is None:
                issues.append("Lifecycle snapshot contains an unresolvable receipt.")
                continue
            report = self.review(receipt)
            reports.append(report)
            if report.status == "ERROR":
                issues.append(f"Lifecycle receipt {receipt.id} returned ERROR.")
            elif report.status != "READY FOR LIFECYCLE DESIGN REVIEW":
                warnings.append(
                    f"Lifecycle receipt {receipt.id} is not ready: {'; '.join(report.issues)}"
                )

        family_spec = next(
            (spec for spec in COMMAND_REGISTRY if spec.prefix == "/experience learning"),
            None,
        )
        if family_spec is None or not family_spec.read_only or family_spec.mutates != "none":
            issues.append("The lifecycle readiness family lacks safe read-only Registry metadata.")
        if any(spec.prefix.startswith("/experience learning lifecycle-apply") for spec in COMMAND_REGISTRY):
            issues.append("A lifecycle apply command is registered before an approved engine exists.")
        if LEARNING_LIFECYCLE_APPLY_ENGINE_INSTALLED:
            issues.append("Lifecycle apply engine must remain absent in v3.4f.")

        counts = Counter(report.status for report in reports)
        status = "ERROR" if issues else "WARN" if warnings else "OK"
        return LearningLifecycleReadinessDoctorReport(
            status=status,
            receipt_count=len(reports),
            ready_count=counts["READY FOR LIFECYCLE DESIGN REVIEW"],
            not_ready_count=counts["NOT READY"],
            error_count=counts["ERROR"],
            issues=list(dict.fromkeys(issues)),
            warnings=list(dict.fromkeys(warnings)),
        )

    def _load_records(self) -> tuple[list[MemoryRecord], list[MemoryRecord]]:
        try:
            return (
                self.memory_store.load_working_memory(),
                self.memory_store.load_persistent_memory(),
            )
        except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise LearningLifecycleReadinessError(
                f"Memory store is unreadable: {exc}"
            ) from exc


def learning_lifecycle_transition_contract(
    decision: str,
) -> LearningLifecycleTransitionContract:
    if decision == "keep":
        return LearningLifecycleTransitionContract(
            decision=decision,
            operation="preserve the active lesson unchanged",
            expected_record_mutations=0,
            rollback="No record rollback; keep performs no lesson mutation.",
            replacement_required=False,
        )
    if decision == "reject":
        return LearningLifecycleTransitionContract(
            decision=decision,
            operation="atomically soft-deactivate the exact lesson while preserving provenance",
            expected_record_mutations=1,
            rollback="Restore the prior active state from a verified lifecycle receipt.",
            replacement_required=False,
        )
    if decision == "supersede":
        return LearningLifecycleTransitionContract(
            decision=decision,
            operation="atomically soft-deactivate the old lesson after verifying the active replacement",
            expected_record_mutations=1,
            rollback="Reactivate the old lesson from a verified receipt; never delete either lesson.",
            replacement_required=True,
        )
    return LearningLifecycleTransitionContract(
        decision=decision or "unknown",
        operation="refuse unknown lifecycle transition",
        expected_record_mutations=0,
        rollback="No rollback because no transition is allowed.",
        replacement_required=False,
    )


def format_learning_lifecycle_readiness_command(
    command: str,
    *,
    events: Iterable[ExperienceEvent | dict[str, Any]],
    memory_store: MemoryStore | None,
    session: OperatorReviewedLearningLifecycleSession,
) -> str | None:
    raw = command.strip()
    normalized = " ".join(raw.lower().split())
    prefixes = (
        "/experience learning lifecycle-readiness",
        "/experience learning lifecycle-plan",
        "/experience learning lifecycle-readiness-doctor",
    )
    if not any(normalized == prefix or normalized.startswith(prefix + " ") for prefix in prefixes):
        return None
    if any(marker in raw for marker in ("\n", ";", "&&", "||")):
        return _readiness_error("Command chaining and multi-command input are not allowed.")
    if memory_store is None:
        return _readiness_error("MemoryStore is unavailable from the shared handler.")
    reviewer = LearningLifecycleApplyReadiness(memory_store=memory_store, events=events)
    try:
        if normalized == "/experience learning lifecycle-readiness-doctor":
            return format_learning_lifecycle_readiness_doctor(reviewer.doctor(session))
        if normalized in {
            "/experience learning lifecycle-readiness",
            "/experience learning lifecycle-plan",
        }:
            suffix = "lifecycle-readiness" if normalized.endswith("readiness") else "lifecycle-plan"
            return f"Usage: /experience learning {suffix} <memory_id|receipt_id>"
        prefix = (
            "/experience learning lifecycle-readiness"
            if normalized.startswith("/experience learning lifecycle-readiness ")
            else "/experience learning lifecycle-plan"
        )
        identifier = raw[len(prefix) :].strip()
        if not identifier or " " in identifier:
            return f"Usage: {prefix} <memory_id|receipt_id>"
        receipt = session.get(identifier)
        if receipt is None:
            return _readiness_not_found(identifier)
        report = reviewer.review(receipt)
    except LearningLifecycleReadinessError as exc:
        return _readiness_error(str(exc))
    return (
        format_learning_lifecycle_readiness(report)
        if prefix.endswith("lifecycle-readiness")
        else format_learning_lifecycle_plan(report)
    )


def format_learning_lifecycle_readiness(
    report: LearningLifecycleReadinessReport,
) -> str:
    lines = [
        "Proto-Mind Learning Lifecycle Apply Readiness v1",
        f"Status: {report.status}",
        f"receipt_id: {report.receipt_id}",
        f"lesson_memory_id: {report.lesson_memory_id}",
        f"decision: {report.decision}",
        f"current_outcome_status: {report.outcome_status}",
        f"replacement_memory_id: {report.replacement_memory_id or 'none'}",
        f"stored_review_hash: {report.stored_review_hash}",
        f"current_review_hash: {report.current_review_hash}",
        f"persistent_store_sha256: {report.persistent_store_sha256}",
        f"lifecycle_engine_installed: {str(report.lifecycle_engine_installed).lower()}",
        f"executable: {str(report.executable).lower()}",
        "Checks:",
    ]
    lines.extend(f"- {name}: {str(value).lower()}" for name, value in report.checks.items())
    lines.extend(f"- ERROR: {issue}" for issue in report.issues)
    lines.extend(f"- WARN: {warning}" for warning in report.warnings)
    lines.extend(_readiness_boundary())
    return "\n".join(lines)


def format_learning_lifecycle_plan(
    report: LearningLifecycleReadinessReport,
) -> str:
    transition = report.transition
    lines = [
        "Proto-Mind Learning Lifecycle Future Transition Plan v1",
        f"Status: {'DESIGN REVIEW ONLY' if report.ready_for_design_review else 'NOT READY'}",
        f"receipt_id: {report.receipt_id}",
        f"lesson_memory_id: {report.lesson_memory_id}",
        f"decision: {report.decision}",
        f"replacement_memory_id: {report.replacement_memory_id or 'none'}",
        "Future transition contract:",
        f"- operation: {transition.operation}",
        f"- expected_record_mutations: {transition.expected_record_mutations}",
        f"- replacement_required: {str(transition.replacement_required).lower()}",
        f"- rollback: {transition.rollback}",
        "Required future safeguards:",
        "- separate Rule 0 checkpoint and separately approved lifecycle writer milestone",
        "- fresh exact token bound to receipt id, current review hash, and before-store SHA-256",
        "- atomic persistent-memory rewrite with previous active states retained in the receipt",
        "- post-write record/provenance/hash verification and fail-closed rollback",
        "- one lesson decision only; no batch, shell, arbitrary dispatch, deletion, or auto-apply",
        "Required future receipt fields:",
        "- lifecycle_apply_id, applied_at, decision_receipt_id, decision, selected_signal_id",
        "- lesson_memory_id, replacement_memory_id, before_store_sha256, after_store_sha256",
        "- previous_active_states, verified_record_hashes, result, rollback_suggestion",
    ]
    if not report.ready_for_design_review:
        lines.extend(f"- BLOCKER: {issue}" for issue in report.issues)
    lines.extend(_readiness_boundary())
    return "\n".join(lines)


def format_learning_lifecycle_readiness_doctor(
    report: LearningLifecycleReadinessDoctorReport,
) -> str:
    lines = [
        "Proto-Mind Learning Lifecycle Apply Readiness Doctor v1",
        f"Status: {report.status}",
        f"mode: {LEARNING_LIFECYCLE_READINESS_MODE}",
        f"receipts: {report.receipt_count}",
        f"ready_for_design_review: {report.ready_count}",
        f"not_ready: {report.not_ready_count}",
        f"errors: {report.error_count}",
        f"lifecycle_engine_installed: {str(LEARNING_LIFECYCLE_APPLY_ENGINE_INSTALLED).lower()}",
    ]
    lines.extend(f"- ERROR: {issue}" for issue in report.issues)
    lines.extend(f"- WARN: {warning}" for warning in report.warnings)
    if not report.issues and not report.warnings:
        lines.append("- Current receipts revalidate and no lifecycle apply surface is installed.")
    lines.extend(_readiness_boundary())
    return "\n".join(lines)


def _receipt_is_safe(receipt: LearningLifecycleDecisionReceipt) -> bool:
    return (
        receipt.decision in {"keep", "reject", "supersede"}
        and OUTCOME_DECISIONS.get(receipt.outcome_status) == receipt.decision
        and receipt.operator_confirmation_recorded
        and receipt.terminal_process_decision
        and receipt.confirmation_method == "exact_current_outcome_token"
        and len(receipt.review_hash) == 64
        and receipt.id == f"learnlife_{receipt.review_hash[:16]}"
        and len(receipt.confirmation_token_hash) == 64
        and bool(receipt.evidence_event_ids)
        and receipt.selected_signal_id in receipt.evidence_event_ids
        and (receipt.decision != "supersede" or bool(receipt.replacement_memory_id))
        and not receipt.memory_mutation_performed
        and not receipt.skill_mutation_performed
        and not receipt.experience_mutation_performed
        and not receipt.persistence_performed
    )


def _hash_file(path: Path) -> str:
    try:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return "unavailable"


def _readiness_not_found(identifier: str) -> str:
    return "\n".join(
        [
            "Proto-Mind Learning Lifecycle Apply Readiness v1",
            "Status: NOT FOUND",
            f"receipt_or_memory_id: {identifier or 'missing'}",
            "- Create an exact current-process outcome decision receipt first.",
            *_readiness_boundary(),
        ]
    )


def _readiness_error(message: str) -> str:
    return "\n".join(
        [
            "Proto-Mind Learning Lifecycle Apply Readiness v1",
            "Status: ERROR",
            f"- ERROR: {message}",
            *_readiness_boundary(),
        ]
    )


def _readiness_boundary() -> list[str]:
    return [
        "Boundary:",
        "- Read-only design review only; lifecycle apply engine is absent and executable=false.",
        "- No lesson, memory, skill, Experience event, receipt, queue, export, or Context Injection was changed.",
        "- No command, rollback, model/API call, shell action, or automatic decision was executed.",
    ]
