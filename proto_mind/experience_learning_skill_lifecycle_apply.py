from __future__ import annotations

from collections import Counter
from copy import deepcopy
from dataclasses import asdict, dataclass, replace
import hashlib
import json
from pathlib import Path
from threading import RLock
from typing import Any
from uuid import uuid4

from proto_mind.command_registry import COMMAND_REGISTRY
from proto_mind.experience_learning_skill_lifecycle_readiness import (
    ProceduralSkillLifecycleApplyReadiness,
    ProceduralSkillLifecycleReadinessReport,
)
from proto_mind.experience_learning_skill_outcome_decision import (
    OperatorReviewedProceduralSkillOutcomeDecisionSession,
    ProceduralSkillOutcomeDecisionReceipt,
)
from proto_mind.experience_learning_skill_runtime import (
    PROCEDURAL_SKILL_EXECUTION_INSTALLED,
)
from proto_mind.models import utc_now_iso
from proto_mind.skill_provenance import verify_procedural_skill_provenance


PROCEDURAL_SKILL_LIFECYCLE_APPLY_VERSION = 1
PROCEDURAL_SKILL_LIFECYCLE_APPLY_MODE = (
    "legacy_exact_keep_noop_with_archive_redirected_to_durable_gate"
)
PROCEDURAL_SKILL_LIFECYCLE_APPLY_MAX_RECEIPTS = 1
PROCEDURAL_SKILL_LIFECYCLE_APPLY_ENGINE_INSTALLED = True


@dataclass(frozen=True)
class ProceduralSkillLifecycleApplyReview:
    status: str
    decision_receipt_id: str
    skill_id: str
    decision: str
    outcome_status: str
    decision_hash: str
    before_store_sha256: str
    before_record_hash: str
    expected_record_mutations: int
    checks: dict[str, bool]
    issues: list[str]
    warnings: list[str]
    confirmable: bool
    executable: bool = False
    target_execution_allowed: bool = False
    mutation_performed: bool = False


@dataclass(frozen=True)
class ProceduralSkillLifecycleApplyReceipt:
    id: str
    applied_at: str
    decision_receipt_id: str
    skill_id: str
    decision: str
    outcome_status: str
    provenance_id: str
    decision_hash: str
    before_store_sha256: str
    after_store_sha256: str
    before_record_hash: str
    after_record_hash: str
    previous_skill_state: dict[str, Any]
    resulting_skill_state: dict[str, Any]
    expected_record_mutations: int
    actual_record_mutations: int
    allowed_changed_fields: list[str]
    confirmation_method: str
    confirmation_token_hash: str
    post_state_verified: bool
    durable_provenance_preserved: bool
    persistent_memory_unchanged: bool
    apply_result: str
    rollback_suggestion: str
    run_once_guard: bool = True
    target_execution_performed: bool = False
    executable: bool = False
    skill_mutation_performed: bool = False
    memory_mutation_performed: bool = False
    experience_mutation_performed: bool = False
    batch_apply_performed: bool = False
    receipt_persistence: str = "process_memory_only"
    receipt_hash: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ProceduralSkillLifecycleApplyDoctorReport:
    status: str
    receipt_count: int
    keep_count: int
    archive_count: int
    current_count: int
    historical_count: int
    issues: list[str]
    warnings: list[str]


class ProceduralSkillLifecycleApplyError(RuntimeError):
    pass


class OperatorReviewedProceduralSkillLifecycleApplySession:
    """Applies one exact keep/archive lifecycle decision per process."""

    def __init__(self) -> None:
        self._receipts: dict[str, ProceduralSkillLifecycleApplyReceipt] = {}
        self._lock = RLock()

    def snapshot(self) -> tuple[dict[str, Any], ...]:
        with self._lock:
            return tuple(deepcopy(receipt.to_dict()) for receipt in self._receipts.values())

    def get(self, identifier: str) -> ProceduralSkillLifecycleApplyReceipt | None:
        with self._lock:
            direct = self._receipts.get(identifier)
            if direct is not None:
                return direct
            return next(
                (
                    receipt
                    for receipt in self._receipts.values()
                    if identifier
                    in {receipt.id, receipt.decision_receipt_id, receipt.skill_id}
                ),
                None,
            )

    def review(
        self,
        receipt: ProceduralSkillOutcomeDecisionReceipt,
        *,
        reviewer: ProceduralSkillLifecycleApplyReadiness,
    ) -> ProceduralSkillLifecycleApplyReview:
        with self._lock:
            return self._review_locked(receipt, reviewer=reviewer)

    def apply(
        self,
        receipt: ProceduralSkillOutcomeDecisionReceipt,
        *,
        token: str,
        reviewer: ProceduralSkillLifecycleApplyReadiness,
    ) -> ProceduralSkillLifecycleApplyReceipt:
        with self._lock:
            review = self._review_locked(receipt, reviewer=reviewer)
            if not review.confirmable:
                raise ProceduralSkillLifecycleApplyError(
                    "; ".join(review.issues) or review.status
                )
            expected_token = procedural_skill_lifecycle_apply_confirmation_token(review)
            if token != expected_token:
                raise ProceduralSkillLifecycleApplyError(
                    "Procedural skill lifecycle apply confirmation token mismatch."
                )

            path = reviewer.skill_library.skills_path
            before_bytes = _read_bytes(path)
            if _hash_bytes(before_bytes) != review.before_store_sha256:
                raise ProceduralSkillLifecycleApplyError(
                    "Skill Library changed after lifecycle apply confirmation preview."
                )
            original_records = _parse_jsonl(before_bytes)
            target_index = _unique_record_index(original_records, receipt.skill_id)
            old_record = deepcopy(original_records[target_index])
            if _hash_json(old_record) != review.before_record_hash:
                raise ProceduralSkillLifecycleApplyError(
                    "Skill record changed after lifecycle apply confirmation preview."
                )
            memory_path = reviewer.builder.memory_store.persistent_path
            memory_before = _hash_file(memory_path)
            applied_at = utc_now_iso()

            if receipt.decision == "keep":
                after_bytes = _read_bytes(path)
                after_records = _parse_jsonl(after_bytes)
                if after_bytes != before_bytes or after_records != original_records:
                    raise ProceduralSkillLifecycleApplyError(
                        "Keep lifecycle apply failed byte-stable no-op verification."
                    )
                verified_record = deepcopy(after_records[target_index])
                actual_mutations = 0
                changed_fields: list[str] = []
                apply_result = "keep_verified_noop"
                rollback = "not applicable; Skill Library bytes were unchanged"
            else:
                updated_records = deepcopy(original_records)
                updated_records[target_index]["status"] = "archived"
                updated_records[target_index]["updated_at"] = applied_at
                try:
                    _atomic_replace(path, _serialize_jsonl(updated_records))
                    (
                        verified_record,
                        actual_mutations,
                        changed_fields,
                    ) = _verify_archive_transition(
                        reviewer,
                        original_records=original_records,
                        target_skill_id=receipt.skill_id,
                    )
                except (OSError, TypeError, ValueError, ProceduralSkillLifecycleApplyError) as exc:
                    _restore_bytes(path, before_bytes)
                    if _read_bytes(path) != before_bytes:
                        raise ProceduralSkillLifecycleApplyError(
                            "Archive verification failed and exact-byte rollback failed."
                        ) from exc
                    raise ProceduralSkillLifecycleApplyError(
                        "Archive verification failed; exact original Skill Library bytes were restored: "
                        f"{exc}"
                    ) from exc
                after_bytes = _read_bytes(path)
                apply_result = "archive_soft_transition_verified"
                rollback = f"/skills restore {receipt.skill_id}"

            memory_after = _hash_file(memory_path)
            if memory_before == "unavailable" or memory_after != memory_before:
                if receipt.decision == "archive":
                    _restore_bytes(path, before_bytes)
                raise ProceduralSkillLifecycleApplyError(
                    "Persistent memory changed during procedural skill lifecycle apply."
                )
            memories = reviewer.builder.memory_store.load_persistent_memory()
            provenance_check = verify_procedural_skill_provenance(
                verified_record,
                memory_records=memories,
            )
            old_provenance = old_record.get("provenance")
            if (
                not provenance_check.verified
                or not provenance_check.current_payload_matches
                or verified_record.get("provenance") != old_provenance
            ):
                if receipt.decision == "archive":
                    _restore_bytes(path, before_bytes)
                raise ProceduralSkillLifecycleApplyError(
                    "Lifecycle apply did not preserve exact verified procedural skill provenance."
                )

            after_store_hash = _hash_bytes(after_bytes)
            after_record_hash = _hash_json(verified_record)
            material = {
                "applied_at": applied_at,
                "decision_receipt_id": receipt.id,
                "skill_id": receipt.skill_id,
                "decision": receipt.decision,
                "outcome_status": receipt.outcome_status,
                "provenance_id": receipt.provenance_id,
                "decision_hash": receipt.decision_hash,
                "before_store_sha256": review.before_store_sha256,
                "after_store_sha256": after_store_hash,
                "before_record_hash": review.before_record_hash,
                "after_record_hash": after_record_hash,
                "previous_skill_state": _skill_state(old_record),
                "resulting_skill_state": _skill_state(verified_record),
                "expected_record_mutations": review.expected_record_mutations,
                "actual_record_mutations": actual_mutations,
                "allowed_changed_fields": changed_fields,
                "confirmation_method": "exact_current_skill_lifecycle_readiness_token",
                "confirmation_token_hash": hashlib.sha256(token.encode("utf-8")).hexdigest(),
                "post_state_verified": True,
                "durable_provenance_preserved": True,
                "persistent_memory_unchanged": True,
                "apply_result": apply_result,
                "rollback_suggestion": rollback,
                "skill_mutation_performed": receipt.decision == "archive",
            }
            identity_hash = _hash_json(_apply_identity_material(material))
            created = ProceduralSkillLifecycleApplyReceipt(
                id=f"skilllifeapply_{identity_hash[:16]}",
                **material,
            )
            created = replace(
                created,
                receipt_hash=procedural_skill_lifecycle_apply_receipt_hash(
                    created.to_dict()
                ),
            )
            self._receipts[receipt.id] = created
            return created

    def doctor(
        self,
        *,
        reviewer: ProceduralSkillLifecycleApplyReadiness,
    ) -> ProceduralSkillLifecycleApplyDoctorReport:
        receipts = self.snapshot()
        issues: list[str] = []
        warnings: list[str] = []
        ids = [str(receipt.get("id") or "") for receipt in receipts]
        if len(receipts) > PROCEDURAL_SKILL_LIFECYCLE_APPLY_MAX_RECEIPTS:
            issues.append("Process lifecycle apply receipt limit is exceeded.")
        if any(not value for value in ids) or len(ids) != len(set(ids)):
            issues.append("Lifecycle apply receipt id is missing or duplicated.")

        current_count = 0
        historical_count = 0
        for receipt in receipts:
            label = str(receipt.get("id") or "<missing>")
            decision = str(receipt.get("decision") or "")
            if decision not in {"keep", "archive"}:
                issues.append(f"Receipt {label} has unsupported decision {decision!r}.")
            identity_hash = _hash_json(_apply_identity_material(receipt))
            if label != f"skilllifeapply_{identity_hash[:16]}":
                issues.append(f"Receipt {label} identity hash does not verify.")
            if receipt.get("receipt_hash") != procedural_skill_lifecycle_apply_receipt_hash(
                receipt
            ):
                issues.append(f"Receipt {label} hash does not verify.")
            expected = 0 if decision == "keep" else 1
            if (
                receipt.get("expected_record_mutations") != expected
                or receipt.get("actual_record_mutations") != expected
            ):
                issues.append(f"Receipt {label} mutation count is invalid.")
            expected_fields = [] if decision == "keep" else ["status", "updated_at"]
            if receipt.get("allowed_changed_fields") != expected_fields:
                issues.append(f"Receipt {label} changed-field set is invalid.")
            if any(
                receipt.get(field) is not expected_value
                for field, expected_value in {
                    "run_once_guard": True,
                    "target_execution_performed": False,
                    "executable": False,
                    "skill_mutation_performed": decision == "archive",
                    "memory_mutation_performed": False,
                    "experience_mutation_performed": False,
                    "batch_apply_performed": False,
                    "post_state_verified": True,
                    "durable_provenance_preserved": True,
                    "persistent_memory_unchanged": True,
                }.items()
            ):
                issues.append(f"Receipt {label} violates its safety or verification boundary.")
            if (
                receipt.get("confirmation_method")
                != "exact_current_skill_lifecycle_readiness_token"
                or len(str(receipt.get("confirmation_token_hash") or "")) != 64
            ):
                issues.append(f"Receipt {label} lacks exact confirmation evidence.")

            snapshot = reviewer.skill_library.read_snapshot()
            matches = [
                item
                for item in snapshot["records"]
                if item.get("id") == receipt.get("skill_id")
            ]
            if snapshot["error"] or snapshot["malformed_count"] or len(matches) != 1:
                historical_count += 1
                warnings.append(
                    f"Receipt {label} current skill state is unavailable or historical."
                )
            elif _hash_json(matches[0]) == receipt.get("after_record_hash"):
                current_count += 1
            else:
                historical_count += 1
                warnings.append(
                    f"Receipt {label} is historical; the current skill record changed later."
                )

        registry = {item.prefix: item for item in COMMAND_REGISTRY}
        expected_registry = {
            "/experience learning skill-outcome-lifecycle-apply-preview": (
                True,
                "none",
                "low",
            ),
            "/experience learning apply skill-outcome-lifecycle": (
                False,
                "skills",
                "medium",
            ),
            "/experience learning skill-outcome-lifecycle-applies": (
                True,
                "none",
                "low",
            ),
            "/experience learning skill-outcome-lifecycle-apply-doctor": (
                True,
                "none",
                "low",
            ),
        }
        for prefix, expected in expected_registry.items():
            spec = registry.get(prefix)
            if spec is None or (spec.read_only, spec.mutates, spec.risk) != expected:
                issues.append(f"Registry metadata for {prefix} is missing or unsafe.")
        if not PROCEDURAL_SKILL_LIFECYCLE_APPLY_ENGINE_INSTALLED:
            issues.append("Procedural skill lifecycle apply engine is unavailable.")
        if PROCEDURAL_SKILL_EXECUTION_INSTALLED:
            issues.append("Procedural skill execution must remain disabled.")
        if not receipts:
            warnings.append("No procedural skill lifecycle apply occurred this process.")
        counts = Counter(str(receipt.get("decision") or "") for receipt in receipts)
        status = "ERROR" if issues else "WARN" if warnings else "OK"
        return ProceduralSkillLifecycleApplyDoctorReport(
            status=status,
            receipt_count=len(receipts),
            keep_count=counts["keep"],
            archive_count=counts["archive"],
            current_count=current_count,
            historical_count=historical_count,
            issues=_dedupe(issues),
            warnings=_dedupe(warnings),
        )

    def _review_locked(
        self,
        receipt: ProceduralSkillOutcomeDecisionReceipt,
        *,
        reviewer: ProceduralSkillLifecycleApplyReadiness,
    ) -> ProceduralSkillLifecycleApplyReview:
        readiness = reviewer.review(receipt)
        registry = {item.prefix: item for item in COMMAND_REGISTRY}
        apply_spec = registry.get(
            "/experience learning apply skill-outcome-lifecycle"
        )
        checks = {
            "readiness_current": readiness.ready_for_design_review,
            "decision_supported": receipt.decision in {"keep", "archive"},
            "archive_requires_durable_gate": receipt.decision != "archive",
            "revision_refused": receipt.decision != "revise",
            "decision_not_applied": receipt.id not in self._receipts,
            "run_once_slot_available": (
                len(self._receipts) < PROCEDURAL_SKILL_LIFECYCLE_APPLY_MAX_RECEIPTS
            ),
            "apply_engine_installed": PROCEDURAL_SKILL_LIFECYCLE_APPLY_ENGINE_INSTALLED,
            "registry_apply_gate_safe": bool(
                apply_spec is not None
                and not apply_spec.read_only
                and apply_spec.mutates == "skills"
                and apply_spec.risk == "medium"
            ),
            "procedure_execution_disabled": not PROCEDURAL_SKILL_EXECUTION_INSTALLED,
            "future_contract_direct_apply_allowed": (
                readiness.contract.direct_lifecycle_apply_allowed
            ),
        }
        messages = {
            "readiness_current": "Current procedural skill lifecycle readiness is not READY.",
            "decision_supported": "Only keep or archive may enter the v3.5j lifecycle apply gate.",
            "archive_requires_durable_gate": "Archive now requires the separately confirmed --durable metadata gate.",
            "revision_refused": "Revision requires a separate versioned replacement contract.",
            "decision_not_applied": "This terminal decision was already applied in this process.",
            "run_once_slot_available": "The single lifecycle apply slot is already used this process.",
            "apply_engine_installed": "Procedural skill lifecycle apply engine is unavailable.",
            "registry_apply_gate_safe": "Lifecycle apply Registry gate is missing or unsafe.",
            "procedure_execution_disabled": "Procedural skill execution must remain disabled.",
            "future_contract_direct_apply_allowed": "This decision is not directly applyable.",
        }
        issues = list(readiness.issues)
        issues.extend(messages[name] for name, passed in checks.items() if not passed)
        confirmable = all(checks.values()) and not issues
        return ProceduralSkillLifecycleApplyReview(
            status="CONFIRMABLE" if confirmable else "NOT CONFIRMABLE",
            decision_receipt_id=receipt.id,
            skill_id=receipt.skill_id,
            decision=receipt.decision,
            outcome_status=receipt.outcome_status,
            decision_hash=receipt.decision_hash,
            before_store_sha256=readiness.skill_store_sha256,
            before_record_hash=readiness.skill_record_hash,
            expected_record_mutations=(
                readiness.contract.expected_skill_record_mutations
            ),
            checks=checks,
            issues=_dedupe(issues),
            warnings=list(readiness.warnings),
            confirmable=confirmable,
        )


def procedural_skill_lifecycle_apply_confirmation_token(
    review: ProceduralSkillLifecycleApplyReview,
) -> str:
    material = {
        "decision_receipt_id": review.decision_receipt_id,
        "skill_id": review.skill_id,
        "decision": review.decision,
        "decision_hash": review.decision_hash,
        "before_store_sha256": review.before_store_sha256,
        "before_record_hash": review.before_record_hash,
        "expected_record_mutations": review.expected_record_mutations,
    }
    return (
        f"CONFIRM-SKILL-LIFECYCLE-{review.decision.upper()}-"
        f"{_hash_json(material)[:12].upper()}"
    )


def procedural_skill_lifecycle_apply_receipt_hash(receipt: dict[str, Any]) -> str:
    return _hash_json(
        {key: value for key, value in receipt.items() if key != "receipt_hash"}
    )


def format_procedural_skill_lifecycle_apply_command(
    command: str,
    *,
    decision_session: OperatorReviewedProceduralSkillOutcomeDecisionSession,
    apply_session: OperatorReviewedProceduralSkillLifecycleApplySession,
    reviewer: ProceduralSkillLifecycleApplyReadiness,
) -> str | None:
    raw = command.strip()
    normalized = " ".join(raw.lower().split())
    prefixes = (
        "/experience learning skill-outcome-lifecycle-apply-preview",
        "/experience learning apply skill-outcome-lifecycle",
        "/experience learning skill-outcome-lifecycle-applies",
        "/experience learning skill-outcome-lifecycle-apply-doctor",
    )
    lowered = raw.lower()
    if not any(
        lowered.startswith(prefix)
        and (len(lowered) == len(prefix) or lowered[len(prefix)] in " \t\n;&|")
        for prefix in prefixes
    ):
        return None
    if any(marker in raw for marker in ("\n", ";", "&&", "||", "|")):
        return _apply_error("Command chaining and multi-command input are not allowed.")
    parts = raw.split()

    if normalized == "/experience learning skill-outcome-lifecycle-apply-doctor":
        return format_procedural_skill_lifecycle_apply_doctor(
            apply_session.doctor(reviewer=reviewer)
        )
    if normalized == "/experience learning skill-outcome-lifecycle-applies":
        return format_procedural_skill_lifecycle_applies(apply_session.snapshot())
    if normalized.startswith(
        "/experience learning skill-outcome-lifecycle-applies "
    ):
        if len(parts) != 4:
            return (
                "Usage: /experience learning skill-outcome-lifecycle-applies "
                "[<skill_id|decision_receipt_id|apply_receipt_id>]"
            )
        return format_procedural_skill_lifecycle_apply_receipt(
            apply_session.get(parts[3])
        )
    if normalized == "/experience learning skill-outcome-lifecycle-apply-preview":
        return _preview_usage()
    if normalized.startswith(
        "/experience learning skill-outcome-lifecycle-apply-preview "
    ):
        if len(parts) != 4:
            return _preview_usage()
        decision_receipt = decision_session.get(parts[3])
        if decision_receipt is None:
            return _apply_error(
                f"No process-memory skill outcome decision matches {parts[3]!r}."
            )
        review = apply_session.review(decision_receipt, reviewer=reviewer)
        return format_procedural_skill_lifecycle_apply_preview(review)
    if normalized == "/experience learning apply skill-outcome-lifecycle":
        return _apply_usage()
    if normalized.startswith("/experience learning apply skill-outcome-lifecycle "):
        if len(parts) != 6:
            return _apply_usage()
        decision_receipt = decision_session.get(parts[4])
        if decision_receipt is None:
            return _apply_error(
                f"No process-memory skill outcome decision matches {parts[4]!r}."
            )
        try:
            receipt = apply_session.apply(
                decision_receipt,
                token=parts[5],
                reviewer=reviewer,
            )
        except (OSError, TypeError, ValueError, ProceduralSkillLifecycleApplyError) as exc:
            return _apply_error(str(exc))
        return format_procedural_skill_lifecycle_applied(receipt)
    return None


def format_procedural_skill_lifecycle_apply_preview(
    review: ProceduralSkillLifecycleApplyReview,
) -> str:
    lines = [
        "Proto-Mind Procedural Skill Lifecycle Apply Preview v1",
        f"Status: {review.status}",
        f"decision_receipt_id: {review.decision_receipt_id}",
        f"skill_id: {review.skill_id}",
        f"decision: {review.decision}",
        f"outcome_status: {review.outcome_status}",
        f"before_store_sha256: {review.before_store_sha256}",
        f"before_record_hash: {review.before_record_hash}",
        f"expected_record_mutations: {review.expected_record_mutations}",
        "target_execution_allowed: false",
    ]
    lines.extend(f"- {name}: {str(value).lower()}" for name, value in review.checks.items())
    lines.extend(f"- BLOCKER: {issue}" for issue in review.issues)
    lines.extend(f"- WARN: {warning}" for warning in review.warnings)
    if review.confirmable:
        token = procedural_skill_lifecycle_apply_confirmation_token(review)
        lines.extend(
            [
                f"confirmation_token: {token}",
                "Exact apply command:",
                (
                    "/experience learning apply skill-outcome-lifecycle "
                    f"{review.decision_receipt_id} {token}"
                ),
            ]
        )
    lines.extend(_apply_boundary())
    return "\n".join(lines)


def format_procedural_skill_lifecycle_applied(
    receipt: ProceduralSkillLifecycleApplyReceipt,
) -> str:
    return "\n".join(
        [
            "Proto-Mind Procedural Skill Lifecycle Apply v1",
            "Status: APPLIED",
            f"receipt_id: {receipt.id}",
            f"skill_id: {receipt.skill_id}",
            f"decision: {receipt.decision}",
            f"apply_result: {receipt.apply_result}",
            f"actual_record_mutations: {receipt.actual_record_mutations}",
            f"skill_mutation_performed: {str(receipt.skill_mutation_performed).lower()}",
            "target_execution_performed: false",
            f"rollback_suggestion: {receipt.rollback_suggestion}",
            *_apply_boundary(),
        ]
    )


def format_procedural_skill_lifecycle_applies(
    receipts: tuple[dict[str, Any], ...],
) -> str:
    lines = [
        "Proto-Mind Procedural Skill Lifecycle Applies v1",
        f"Status: {'OK' if receipts else 'EMPTY'}",
        f"receipts: {len(receipts)}/{PROCEDURAL_SKILL_LIFECYCLE_APPLY_MAX_RECEIPTS}",
    ]
    if not receipts:
        lines.append("- none")
    for receipt in receipts:
        lines.append(
            f"- {receipt.get('id')} | {receipt.get('decision')} | "
            f"{receipt.get('skill_id')} | {receipt.get('apply_result')}"
        )
    lines.extend(_apply_boundary())
    return "\n".join(lines)


def format_procedural_skill_lifecycle_apply_receipt(
    receipt: ProceduralSkillLifecycleApplyReceipt | None,
) -> str:
    if receipt is None:
        return _apply_error("Procedural skill lifecycle apply receipt was not found.")
    lines = [
        "Proto-Mind Procedural Skill Lifecycle Apply Receipt v1",
        "Status: OK",
    ]
    lines.extend(f"{key}: {value}" for key, value in receipt.to_dict().items())
    lines.extend(_apply_boundary())
    return "\n".join(lines)


def format_procedural_skill_lifecycle_apply_doctor(
    report: ProceduralSkillLifecycleApplyDoctorReport,
) -> str:
    lines = [
        "Proto-Mind Procedural Skill Lifecycle Apply Doctor v1",
        f"Status: {report.status}",
        f"mode: {PROCEDURAL_SKILL_LIFECYCLE_APPLY_MODE}",
        f"receipts: {report.receipt_count}/{PROCEDURAL_SKILL_LIFECYCLE_APPLY_MAX_RECEIPTS}",
        f"keep: {report.keep_count}",
        f"archive: {report.archive_count}",
        f"current: {report.current_count}",
        f"historical: {report.historical_count}",
        "procedure_execution_enabled: false",
    ]
    lines.extend(f"- ERROR: {issue}" for issue in report.issues)
    lines.extend(f"- WARN: {warning}" for warning in report.warnings)
    if not report.issues and not report.warnings:
        lines.append(
            "- Exact confirmation, run-once, receipt, provenance, store, and non-execution boundaries are healthy."
        )
    lines.extend(_apply_boundary())
    return "\n".join(lines)


def _verify_archive_transition(
    reviewer: ProceduralSkillLifecycleApplyReadiness,
    *,
    original_records: list[dict[str, Any]],
    target_skill_id: str,
) -> tuple[dict[str, Any], int, list[str]]:
    snapshot = reviewer.skill_library.read_snapshot()
    if snapshot["error"] or snapshot["malformed_count"]:
        raise ProceduralSkillLifecycleApplyError(
            f"Skill Library post-write read failed: {snapshot['error'] or 'malformed JSONL'}"
        )
    current_records = snapshot["records"]
    if len(current_records) != len(original_records):
        raise ProceduralSkillLifecycleApplyError("Skill record count changed unexpectedly.")
    before_by_id = _records_by_unique_id(original_records)
    after_by_id = _records_by_unique_id(current_records)
    if set(before_by_id) != set(after_by_id):
        raise ProceduralSkillLifecycleApplyError("Skill record identity set changed unexpectedly.")
    changed_ids = [
        identifier
        for identifier in before_by_id
        if before_by_id[identifier] != after_by_id[identifier]
    ]
    if changed_ids != [target_skill_id]:
        raise ProceduralSkillLifecycleApplyError(
            "Archive must change exactly one target skill record."
        )
    before = before_by_id[target_skill_id]
    after = after_by_id[target_skill_id]
    changed_fields = sorted(
        key for key in set(before) | set(after) if before.get(key) != after.get(key)
    )
    if changed_fields != ["status", "updated_at"]:
        raise ProceduralSkillLifecycleApplyError(
            "Archive changed fields outside status and updated_at."
        )
    if before.get("status") != "active" or after.get("status") != "archived":
        raise ProceduralSkillLifecycleApplyError(
            "Archive status transition is not active to archived."
        )
    if after.get("provenance") != before.get("provenance"):
        raise ProceduralSkillLifecycleApplyError("Archive changed immutable provenance.")
    if after.get("executable") is not False:
        raise ProceduralSkillLifecycleApplyError("Archived skill claims executable capability.")
    return deepcopy(after), 1, changed_fields


def _unique_record_index(records: list[dict[str, Any]], skill_id: str) -> int:
    indexes = [index for index, record in enumerate(records) if record.get("id") == skill_id]
    if len(indexes) != 1:
        raise ProceduralSkillLifecycleApplyError(
            "Lifecycle apply requires exactly one current target skill record."
        )
    return indexes[0]


def _records_by_unique_id(records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for record in records:
        identifier = str(record.get("id") or "")
        if not identifier or identifier in result:
            raise ProceduralSkillLifecycleApplyError(
                "Skill Library contains missing or duplicate record ids."
            )
        result[identifier] = record
    return result


def _skill_state(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": record.get("status"),
        "updated_at": record.get("updated_at"),
        "provenance_id": (
            record.get("provenance", {}).get("id")
            if isinstance(record.get("provenance"), dict)
            else ""
        ),
        "executable": record.get("executable"),
    }


def _apply_identity_material(value: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value.get(key)
        for key in (
            "applied_at",
            "decision_receipt_id",
            "skill_id",
            "decision",
            "decision_hash",
            "before_store_sha256",
            "after_store_sha256",
            "before_record_hash",
            "after_record_hash",
            "confirmation_token_hash",
        )
    }


def _read_bytes(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except OSError as exc:
        raise ProceduralSkillLifecycleApplyError(
            f"Skill Library is unreadable: {exc}"
        ) from exc


def _parse_jsonl(payload: bytes) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ProceduralSkillLifecycleApplyError("Skill Library is not UTF-8.") from exc
    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ProceduralSkillLifecycleApplyError(
                f"Skill Library line {line_number} is malformed JSON."
            ) from exc
        if not isinstance(parsed, dict):
            raise ProceduralSkillLifecycleApplyError(
                f"Skill Library line {line_number} is not a JSON object."
            )
        records.append(parsed)
    return records


def _serialize_jsonl(records: list[dict[str, Any]]) -> bytes:
    if not records:
        return b""
    return (
        "\n".join(
            json.dumps(record, ensure_ascii=False, sort_keys=True) for record in records
        )
        + "\n"
    ).encode("utf-8")


def _atomic_replace(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        with temp_path.open("wb") as handle:
            handle.write(payload)
            handle.flush()
        temp_path.replace(path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def _restore_bytes(path: Path, payload: bytes) -> None:
    _atomic_replace(path, payload)


def _hash_file(path: Path) -> str:
    try:
        return _hash_bytes(path.read_bytes())
    except OSError:
        return "unavailable"


def _hash_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _hash_json(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _preview_usage() -> str:
    return (
        "Usage: /experience learning skill-outcome-lifecycle-apply-preview "
        "<skill_id|decision_receipt_id>"
    )


def _apply_usage() -> str:
    return (
        "Usage: /experience learning apply skill-outcome-lifecycle "
        "<skill_id|decision_receipt_id> <exact token>"
    )


def _apply_error(message: str) -> str:
    return "\n".join(
        [
            "Proto-Mind Procedural Skill Lifecycle Apply Error",
            "Status: ERROR",
            f"- {message}",
            *_apply_boundary(),
        ]
    )


def _apply_boundary() -> list[str]:
    return [
        "Boundary:",
        "- This legacy gate permits only one exact confirmed keep no-op per process; archive requires --durable and revise is refused.",
        "- Keep is byte-stable; this path cannot create a new ambiguous archive without durable lifecycle metadata.",
        "- No procedure, shell, arbitrary dispatch, batch, memory/event write, model/API, external action, session log, or Context Injection change occurred.",
    ]


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))
