from __future__ import annotations

from collections import Counter
from copy import deepcopy
from dataclasses import asdict, dataclass, replace
import hashlib
import json
import os
from pathlib import Path
from threading import RLock
from typing import Any
from uuid import uuid4

from proto_mind.command_registry import COMMAND_REGISTRY
from proto_mind.experience_learning_skill_lifecycle_metadata_readiness import (
    PROCEDURAL_SKILL_LIFECYCLE_CURRENT_WRITER_SUPPORTS_METADATA,
    PROCEDURAL_SKILL_LIFECYCLE_METADATA_EXPECTED_CHANGED_FIELDS,
    PROCEDURAL_SKILL_LIFECYCLE_METADATA_FUTURE_RECEIPT_FIELDS,
    ProceduralSkillLifecycleMetadataReadiness,
)
from proto_mind.experience_learning_skill_lifecycle_readiness import (
    ProceduralSkillLifecycleApplyReadiness,
)
from proto_mind.experience_learning_skill_outcome_decision import (
    OperatorReviewedProceduralSkillOutcomeDecisionSession,
    ProceduralSkillOutcomeDecisionReceipt,
)
from proto_mind.experience_learning_skill_runtime import (
    PROCEDURAL_SKILL_EXECUTION_INSTALLED,
)
from proto_mind.models import utc_now_iso
from proto_mind.skill_lifecycle_metadata import (
    PROCEDURAL_SKILL_LIFECYCLE_METADATA_SCHEMA,
    PROCEDURAL_SKILL_LIFECYCLE_METADATA_WRITER_INSTALLED,
    build_procedural_skill_lifecycle_metadata_preview,
    verify_procedural_skill_lifecycle_metadata,
)
from proto_mind.skill_provenance import verify_procedural_skill_provenance


PROCEDURAL_SKILL_LIFECYCLE_METADATA_APPLY_VERSION = 1
PROCEDURAL_SKILL_LIFECYCLE_METADATA_APPLY_MODE = (
    "single_exact_confirmed_atomic_durable_archive"
)
PROCEDURAL_SKILL_LIFECYCLE_METADATA_APPLY_MAX_RECEIPTS = 1
PROCEDURAL_SKILL_LIFECYCLE_METADATA_APPLY_ENGINE_INSTALLED = True


@dataclass(frozen=True)
class ProceduralSkillLifecycleMetadataApplyReview:
    status: str
    decision_receipt_id: str
    skill_id: str
    decision: str
    outcome_status: str
    provenance_id: str
    decision_hash: str
    before_store_sha256: str
    before_record_hash: str
    metadata_blueprint_hash: str
    metadata_blueprint: dict[str, Any]
    expected_changed_fields: list[str]
    checks: dict[str, bool]
    issues: list[str]
    warnings: list[str]
    confirmable: bool
    executable: bool = False
    target_execution_allowed: bool = False
    mutation_performed: bool = False


@dataclass(frozen=True)
class ProceduralSkillLifecycleMetadataApplyReceipt:
    lifecycle_apply_id: str
    applied_at: str
    decision_receipt_id: str
    skill_id: str
    decision_hash: str
    metadata_blueprint_hash: str
    metadata_id: str
    metadata_hash: str
    before_store_sha256: str
    after_store_sha256: str
    before_record_hash: str
    after_record_hash: str
    exact_record_mutations: int
    changed_fields: list[str]
    confirmation_token_hash: str
    post_state_verified: bool
    durable_provenance_preserved: bool
    persistent_memory_unchanged: bool
    rollback_performed: bool
    rollback_suggestion: str
    receipt_hash: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ProceduralSkillLifecycleMetadataApplyDoctorReport:
    status: str
    receipt_count: int
    current_count: int
    historical_count: int
    issues: list[str]
    warnings: list[str]


class ProceduralSkillLifecycleMetadataApplyError(RuntimeError):
    pass


class OperatorReviewedProceduralSkillLifecycleMetadataApplySession:
    """Applies one exact durable archive transition per process."""

    def __init__(self) -> None:
        self._receipts: dict[str, ProceduralSkillLifecycleMetadataApplyReceipt] = {}
        self._lock = RLock()

    def snapshot(self) -> tuple[dict[str, Any], ...]:
        with self._lock:
            return tuple(
                deepcopy(receipt.to_dict()) for receipt in self._receipts.values()
            )

    def get(
        self, identifier: str
    ) -> ProceduralSkillLifecycleMetadataApplyReceipt | None:
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
                        receipt.lifecycle_apply_id,
                        receipt.decision_receipt_id,
                        receipt.skill_id,
                        receipt.metadata_id,
                    }
                ),
                None,
            )

    def review(
        self,
        receipt: ProceduralSkillOutcomeDecisionReceipt,
        *,
        reviewer: ProceduralSkillLifecycleApplyReadiness,
    ) -> ProceduralSkillLifecycleMetadataApplyReview:
        with self._lock:
            return self._review_locked(receipt, reviewer=reviewer)

    def apply(
        self,
        receipt: ProceduralSkillOutcomeDecisionReceipt,
        *,
        token: str,
        reviewer: ProceduralSkillLifecycleApplyReadiness,
    ) -> ProceduralSkillLifecycleMetadataApplyReceipt:
        with self._lock:
            review = self._review_locked(receipt, reviewer=reviewer)
            if not review.confirmable:
                raise ProceduralSkillLifecycleMetadataApplyError(
                    "; ".join(review.issues) or review.status
                )
            expected_token = (
                procedural_skill_lifecycle_metadata_apply_confirmation_token(review)
            )
            if token != expected_token:
                raise ProceduralSkillLifecycleMetadataApplyError(
                    "Durable lifecycle apply confirmation token mismatch."
                )

            path = reviewer.skill_library.skills_path
            before_bytes = _read_bytes(path)
            if _hash_bytes(before_bytes) != review.before_store_sha256:
                raise ProceduralSkillLifecycleMetadataApplyError(
                    "Skill Library changed after durable apply confirmation preview."
                )
            original_records = _parse_jsonl(before_bytes)
            target_index = _unique_record_index(original_records, receipt.skill_id)
            old_record = deepcopy(original_records[target_index])
            if _hash_json(old_record) != review.before_record_hash:
                raise ProceduralSkillLifecycleMetadataApplyError(
                    "Skill record changed after durable apply confirmation preview."
                )

            memory_path = reviewer.builder.memory_store.persistent_path
            memory_before = _hash_file(memory_path)
            applied_at = utc_now_iso()
            token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
            metadata = build_procedural_skill_lifecycle_metadata_preview(
                skill_id=receipt.skill_id,
                skill_provenance_id=receipt.provenance_id,
                transitioned_at=applied_at,
                decision_receipt_id=receipt.id,
                decision_hash=receipt.decision_hash,
                outcome_status=receipt.outcome_status,
                selected_signal_id=receipt.selected_signal_id,
                evidence_event_ids=receipt.evidence_event_ids,
                capture_receipt_hashes=receipt.capture_receipt_hashes,
                review_hash=receipt.review_hash,
                before_record_hash=review.before_record_hash,
                confirmation_token_hash=token_hash,
            )
            if not _metadata_matches_blueprint(
                metadata, review.metadata_blueprint
            ):
                raise ProceduralSkillLifecycleMetadataApplyError(
                    "Generated lifecycle metadata differs from the confirmed blueprint."
                )

            updated_records = deepcopy(original_records)
            updated_records[target_index]["lifecycle"] = metadata
            updated_records[target_index]["status"] = "archived"
            updated_records[target_index]["updated_at"] = applied_at
            try:
                _atomic_replace(path, _serialize_jsonl(updated_records))
                verified_record, changed_fields = _verify_durable_archive(
                    reviewer,
                    original_records=original_records,
                    target_skill_id=receipt.skill_id,
                    expected_metadata=metadata,
                )
                memory_after = _hash_file(memory_path)
                if memory_before == "unavailable" or memory_after != memory_before:
                    raise ProceduralSkillLifecycleMetadataApplyError(
                        "Persistent memory changed during durable lifecycle apply."
                    )
                provenance_check = verify_procedural_skill_provenance(
                    verified_record,
                    memory_records=reviewer.builder.memory_store.load_persistent_memory(),
                )
                if (
                    not provenance_check.verified
                    or not provenance_check.current_payload_matches
                    or verified_record.get("provenance") != old_record.get("provenance")
                ):
                    raise ProceduralSkillLifecycleMetadataApplyError(
                        "Durable lifecycle apply did not preserve exact verified skill provenance."
                    )
            except (
                OSError,
                TypeError,
                ValueError,
                ProceduralSkillLifecycleMetadataApplyError,
            ) as exc:
                _restore_bytes(path, before_bytes)
                if _read_bytes(path) != before_bytes:
                    raise ProceduralSkillLifecycleMetadataApplyError(
                        "Durable archive verification failed and exact-byte rollback failed."
                    ) from exc
                raise ProceduralSkillLifecycleMetadataApplyError(
                    "Durable archive verification failed; exact original Skill Library bytes were restored: "
                    f"{exc}"
                ) from exc

            after_bytes = _read_bytes(path)
            after_store_hash = _hash_bytes(after_bytes)
            after_record_hash = _hash_json(verified_record)
            material = {
                "applied_at": applied_at,
                "decision_receipt_id": receipt.id,
                "skill_id": receipt.skill_id,
                "decision_hash": receipt.decision_hash,
                "metadata_blueprint_hash": review.metadata_blueprint_hash,
                "metadata_id": metadata["id"],
                "metadata_hash": metadata["metadata_hash"],
                "before_store_sha256": review.before_store_sha256,
                "after_store_sha256": after_store_hash,
                "before_record_hash": review.before_record_hash,
                "after_record_hash": after_record_hash,
                "exact_record_mutations": 1,
                "changed_fields": changed_fields,
                "confirmation_token_hash": token_hash,
                "post_state_verified": True,
                "durable_provenance_preserved": True,
                "persistent_memory_unchanged": True,
                "rollback_performed": False,
                "rollback_suggestion": (
                    "manual review required; restore needs a separate durable lifecycle transition contract"
                ),
            }
            identity_hash = _hash_json(_receipt_identity_material(material))
            created = ProceduralSkillLifecycleMetadataApplyReceipt(
                lifecycle_apply_id=f"skilllifemetaapply_{identity_hash[:16]}",
                **material,
            )
            created = replace(
                created,
                receipt_hash=procedural_skill_lifecycle_metadata_apply_receipt_hash(
                    created.to_dict()
                ),
            )
            self._receipts[receipt.id] = created
            return created

    def doctor(
        self,
        *,
        reviewer: ProceduralSkillLifecycleApplyReadiness,
    ) -> ProceduralSkillLifecycleMetadataApplyDoctorReport:
        receipts = self.snapshot()
        issues: list[str] = []
        warnings: list[str] = []
        ids = [str(item.get("lifecycle_apply_id") or "") for item in receipts]
        if len(receipts) > PROCEDURAL_SKILL_LIFECYCLE_METADATA_APPLY_MAX_RECEIPTS:
            issues.append("Durable lifecycle apply receipt limit is exceeded.")
        if any(not value for value in ids) or len(ids) != len(set(ids)):
            issues.append("Durable lifecycle apply receipt id is missing or duplicated.")

        current_count = 0
        historical_count = 0
        for receipt in receipts:
            label = str(receipt.get("lifecycle_apply_id") or "<missing>")
            if set(receipt) != set(
                PROCEDURAL_SKILL_LIFECYCLE_METADATA_FUTURE_RECEIPT_FIELDS
            ):
                issues.append(f"Receipt {label} does not match the fixed field contract.")
            identity_hash = _hash_json(_receipt_identity_material(receipt))
            if label != f"skilllifemetaapply_{identity_hash[:16]}":
                issues.append(f"Receipt {label} identity hash does not verify.")
            if receipt.get(
                "receipt_hash"
            ) != procedural_skill_lifecycle_metadata_apply_receipt_hash(receipt):
                issues.append(f"Receipt {label} hash does not verify.")
            if receipt.get("exact_record_mutations") != 1:
                issues.append(f"Receipt {label} mutation count is invalid.")
            if receipt.get("changed_fields") != list(
                PROCEDURAL_SKILL_LIFECYCLE_METADATA_EXPECTED_CHANGED_FIELDS
            ):
                issues.append(f"Receipt {label} changed-field set is invalid.")
            for field in (
                "post_state_verified",
                "durable_provenance_preserved",
                "persistent_memory_unchanged",
            ):
                if receipt.get(field) is not True:
                    issues.append(f"Receipt {label} lacks {field} verification.")
            if receipt.get("rollback_performed") is not False:
                issues.append(f"Receipt {label} incorrectly claims rollback after success.")
            for field in (
                "decision_hash",
                "metadata_blueprint_hash",
                "metadata_hash",
                "before_store_sha256",
                "after_store_sha256",
                "before_record_hash",
                "after_record_hash",
                "confirmation_token_hash",
                "receipt_hash",
            ):
                if not _is_sha256(receipt.get(field)):
                    issues.append(f"Receipt {label} field {field} is not SHA-256.")

            snapshot = reviewer.skill_library.read_snapshot()
            matches = [
                record
                for record in snapshot["records"]
                if record.get("id") == receipt.get("skill_id")
            ]
            if snapshot["error"] or snapshot["malformed_count"] or len(matches) != 1:
                historical_count += 1
                warnings.append(
                    f"Receipt {label} current skill state is unavailable or historical."
                )
            elif _hash_json(matches[0]) != receipt.get("after_record_hash"):
                historical_count += 1
                warnings.append(
                    f"Receipt {label} is historical; the current skill changed later."
                )
            else:
                metadata_check = verify_procedural_skill_lifecycle_metadata(
                    matches[0].get("lifecycle")
                )
                if not metadata_check.verified:
                    issues.extend(
                        f"Receipt {label}: {item}" for item in metadata_check.issues
                    )
                else:
                    current_count += 1

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
        if not PROCEDURAL_SKILL_LIFECYCLE_METADATA_APPLY_ENGINE_INSTALLED:
            issues.append("Durable lifecycle metadata apply engine is unavailable.")
        if not PROCEDURAL_SKILL_LIFECYCLE_METADATA_WRITER_INSTALLED:
            issues.append("Durable lifecycle metadata writer is not installed.")
        if PROCEDURAL_SKILL_LIFECYCLE_CURRENT_WRITER_SUPPORTS_METADATA:
            issues.append("The legacy v3.5j writer must remain metadata-incompatible.")
        if PROCEDURAL_SKILL_EXECUTION_INSTALLED:
            issues.append("Procedural skill execution must remain disabled.")
        if not receipts:
            warnings.append("No durable lifecycle metadata apply occurred this process.")
        return ProceduralSkillLifecycleMetadataApplyDoctorReport(
            status="ERROR" if issues else "WARN" if warnings else "OK",
            receipt_count=len(receipts),
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
    ) -> ProceduralSkillLifecycleMetadataApplyReview:
        readiness = ProceduralSkillLifecycleMetadataReadiness(reviewer).review(
            receipt
        )
        registry = {item.prefix: item for item in COMMAND_REGISTRY}
        apply_spec = registry.get(
            "/experience learning apply skill-outcome-lifecycle"
        )
        checks = {
            "durable_readiness_current": readiness.ready_for_writer_design_review,
            "durable_metadata_required": readiness.metadata_required,
            "archive_only": receipt.decision == "archive",
            "decision_not_applied": receipt.id not in self._receipts,
            "run_once_slot_available": len(self._receipts)
            < PROCEDURAL_SKILL_LIFECYCLE_METADATA_APPLY_MAX_RECEIPTS,
            "durable_apply_engine_installed": (
                PROCEDURAL_SKILL_LIFECYCLE_METADATA_APPLY_ENGINE_INSTALLED
            ),
            "durable_writer_installed": (
                PROCEDURAL_SKILL_LIFECYCLE_METADATA_WRITER_INSTALLED
            ),
            "legacy_writer_not_metadata_capable": not (
                PROCEDURAL_SKILL_LIFECYCLE_CURRENT_WRITER_SUPPORTS_METADATA
            ),
            "registry_apply_gate_safe": bool(
                apply_spec is not None
                and not apply_spec.read_only
                and apply_spec.mutates == "skills"
                and apply_spec.risk == "medium"
            ),
            "procedure_execution_disabled": not PROCEDURAL_SKILL_EXECUTION_INSTALLED,
            "exact_changed_fields_locked": readiness.expected_changed_fields
            == list(PROCEDURAL_SKILL_LIFECYCLE_METADATA_EXPECTED_CHANGED_FIELDS),
            "metadata_blueprint_bound": bool(
                readiness.metadata_blueprint
                and _is_sha256(readiness.metadata_blueprint_hash)
            ),
        }
        messages = {
            "durable_readiness_current": "Current durable lifecycle readiness is not READY.",
            "durable_metadata_required": "Keep requires no durable metadata; revise remains unavailable.",
            "archive_only": "The durable lifecycle writer supports archive only.",
            "decision_not_applied": "This terminal decision was already durably applied in this process.",
            "run_once_slot_available": "The single durable lifecycle apply slot is already used this process.",
            "durable_apply_engine_installed": "Durable lifecycle apply engine is unavailable.",
            "durable_writer_installed": "Durable lifecycle metadata writer is unavailable.",
            "legacy_writer_not_metadata_capable": "The legacy writer must not be reused for durable metadata.",
            "registry_apply_gate_safe": "Lifecycle apply Registry gate is missing or unsafe.",
            "procedure_execution_disabled": "Procedural skill execution must remain disabled.",
            "exact_changed_fields_locked": "Durable apply changed-field scope is not exact.",
            "metadata_blueprint_bound": "Durable metadata blueprint is absent or unhashed.",
        }
        issues = list(readiness.issues)
        issues.extend(messages[name] for name, passed in checks.items() if not passed)
        confirmable = all(checks.values()) and not issues
        return ProceduralSkillLifecycleMetadataApplyReview(
            status="CONFIRMABLE" if confirmable else "NOT CONFIRMABLE",
            decision_receipt_id=receipt.id,
            skill_id=receipt.skill_id,
            decision=receipt.decision,
            outcome_status=receipt.outcome_status,
            provenance_id=receipt.provenance_id,
            decision_hash=receipt.decision_hash,
            before_store_sha256=readiness.skill_store_sha256,
            before_record_hash=readiness.skill_record_hash,
            metadata_blueprint_hash=readiness.metadata_blueprint_hash,
            metadata_blueprint=deepcopy(readiness.metadata_blueprint),
            expected_changed_fields=list(readiness.expected_changed_fields),
            checks=checks,
            issues=_dedupe(issues),
            warnings=list(readiness.warnings),
            confirmable=confirmable,
        )


def procedural_skill_lifecycle_metadata_apply_confirmation_token(
    review: ProceduralSkillLifecycleMetadataApplyReview,
) -> str:
    material = {
        "decision_receipt_id": review.decision_receipt_id,
        "skill_id": review.skill_id,
        "decision": review.decision,
        "decision_hash": review.decision_hash,
        "before_store_sha256": review.before_store_sha256,
        "before_record_hash": review.before_record_hash,
        "metadata_blueprint_hash": review.metadata_blueprint_hash,
        "expected_changed_fields": review.expected_changed_fields,
    }
    return (
        "CONFIRM-DURABLE-SKILL-LIFECYCLE-ARCHIVE-"
        f"{_hash_json(material)[:12].upper()}"
    )


def procedural_skill_lifecycle_metadata_apply_receipt_hash(
    receipt: dict[str, Any],
) -> str:
    return _hash_json(
        {key: value for key, value in receipt.items() if key != "receipt_hash"}
    )


def format_procedural_skill_lifecycle_metadata_apply_command(
    command: str,
    *,
    decision_session: OperatorReviewedProceduralSkillOutcomeDecisionSession,
    apply_session: OperatorReviewedProceduralSkillLifecycleMetadataApplySession,
    reviewer: ProceduralSkillLifecycleApplyReadiness,
) -> str | None:
    raw = command.strip()
    normalized = " ".join(raw.lower().split())
    if "--durable" not in normalized:
        return None
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

    if normalized == (
        "/experience learning skill-outcome-lifecycle-apply-doctor --durable"
    ):
        return format_procedural_skill_lifecycle_metadata_apply_doctor(
            apply_session.doctor(reviewer=reviewer)
        )
    if normalized == (
        "/experience learning skill-outcome-lifecycle-applies --durable"
    ):
        return format_procedural_skill_lifecycle_metadata_applies(
            apply_session.snapshot()
        )
    if normalized.startswith(
        "/experience learning skill-outcome-lifecycle-applies "
    ):
        if len(parts) != 5 or parts[4].lower() != "--durable":
            return _applies_usage()
        return format_procedural_skill_lifecycle_metadata_apply_receipt(
            apply_session.get(parts[3])
        )
    if normalized.startswith(
        "/experience learning skill-outcome-lifecycle-apply-preview "
    ):
        if len(parts) != 5 or parts[4].lower() != "--durable":
            return _preview_usage()
        decision_receipt = decision_session.get(parts[3])
        if decision_receipt is None:
            return _apply_error(
                f"No process-memory skill outcome decision matches {parts[3]!r}."
            )
        return format_procedural_skill_lifecycle_metadata_apply_preview(
            apply_session.review(decision_receipt, reviewer=reviewer)
        )
    if normalized.startswith(
        "/experience learning apply skill-outcome-lifecycle "
    ):
        if len(parts) != 7 or parts[6].lower() != "--durable":
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
        except (
            OSError,
            TypeError,
            ValueError,
            ProceduralSkillLifecycleMetadataApplyError,
        ) as exc:
            return _apply_error(str(exc))
        return format_procedural_skill_lifecycle_metadata_applied(receipt)
    return _apply_error("Unsupported durable lifecycle apply syntax.")


def format_procedural_skill_lifecycle_metadata_apply_preview(
    review: ProceduralSkillLifecycleMetadataApplyReview,
) -> str:
    lines = [
        "Proto-Mind Durable Procedural Skill Lifecycle Apply Preview v1",
        f"Status: {review.status}",
        f"mode: {PROCEDURAL_SKILL_LIFECYCLE_METADATA_APPLY_MODE}",
        f"decision_receipt_id: {review.decision_receipt_id}",
        f"skill_id: {review.skill_id}",
        f"decision: {review.decision}",
        f"outcome_status: {review.outcome_status}",
        f"metadata_schema: {PROCEDURAL_SKILL_LIFECYCLE_METADATA_SCHEMA}",
        f"metadata_blueprint_hash: {review.metadata_blueprint_hash or 'unavailable'}",
        f"before_store_sha256: {review.before_store_sha256}",
        f"before_record_hash: {review.before_record_hash}",
        f"expected_changed_fields: {', '.join(review.expected_changed_fields) or 'none'}",
        "target_execution_allowed: false",
        "mutation_performed: false",
    ]
    lines.extend(f"- {name}: {str(value).lower()}" for name, value in review.checks.items())
    lines.extend(f"- BLOCKER: {issue}" for issue in review.issues)
    lines.extend(f"- WARN: {warning}" for warning in review.warnings)
    if review.confirmable:
        token = procedural_skill_lifecycle_metadata_apply_confirmation_token(review)
        lines.extend(
            [
                f"confirmation_token: {token}",
                "Exact apply command:",
                (
                    "/experience learning apply skill-outcome-lifecycle "
                    f"{review.decision_receipt_id} {token} --durable"
                ),
            ]
        )
    lines.extend(_boundary())
    return "\n".join(lines)


def format_procedural_skill_lifecycle_metadata_applied(
    receipt: ProceduralSkillLifecycleMetadataApplyReceipt,
) -> str:
    return "\n".join(
        [
            "Proto-Mind Durable Procedural Skill Lifecycle Apply v1",
            "Status: APPLIED",
            f"lifecycle_apply_id: {receipt.lifecycle_apply_id}",
            f"skill_id: {receipt.skill_id}",
            f"metadata_id: {receipt.metadata_id}",
            f"metadata_hash: {receipt.metadata_hash}",
            f"exact_record_mutations: {receipt.exact_record_mutations}",
            f"changed_fields: {', '.join(receipt.changed_fields)}",
            f"post_state_verified: {str(receipt.post_state_verified).lower()}",
            "procedure_execution_performed: false",
            f"rollback_suggestion: {receipt.rollback_suggestion}",
            *_boundary(),
        ]
    )


def format_procedural_skill_lifecycle_metadata_applies(
    receipts: tuple[dict[str, Any], ...],
) -> str:
    lines = [
        "Proto-Mind Durable Procedural Skill Lifecycle Applies v1",
        f"Status: {'OK' if receipts else 'EMPTY'}",
        f"receipts: {len(receipts)}/{PROCEDURAL_SKILL_LIFECYCLE_METADATA_APPLY_MAX_RECEIPTS}",
    ]
    if not receipts:
        lines.append("- none")
    for receipt in receipts:
        lines.append(
            f"- {receipt.get('lifecycle_apply_id')} | archive | "
            f"{receipt.get('skill_id')} | metadata={receipt.get('metadata_id')}"
        )
    lines.extend(_boundary())
    return "\n".join(lines)


def format_procedural_skill_lifecycle_metadata_apply_receipt(
    receipt: ProceduralSkillLifecycleMetadataApplyReceipt | None,
) -> str:
    if receipt is None:
        return _apply_error("Durable lifecycle apply receipt was not found.")
    lines = [
        "Proto-Mind Durable Procedural Skill Lifecycle Apply Receipt v1",
        "Status: OK",
    ]
    lines.extend(f"{key}: {_compact(value)}" for key, value in receipt.to_dict().items())
    lines.extend(_boundary())
    return "\n".join(lines)


def format_procedural_skill_lifecycle_metadata_apply_doctor(
    report: ProceduralSkillLifecycleMetadataApplyDoctorReport,
) -> str:
    lines = [
        "Proto-Mind Durable Procedural Skill Lifecycle Apply Doctor v1",
        f"Status: {report.status}",
        f"mode: {PROCEDURAL_SKILL_LIFECYCLE_METADATA_APPLY_MODE}",
        f"receipts: {report.receipt_count}/{PROCEDURAL_SKILL_LIFECYCLE_METADATA_APPLY_MAX_RECEIPTS}",
        f"current: {report.current_count}",
        f"historical: {report.historical_count}",
        f"writer_installed: {str(PROCEDURAL_SKILL_LIFECYCLE_METADATA_WRITER_INSTALLED).lower()}",
        "procedure_execution_enabled: false",
    ]
    lines.extend(f"- ERROR: {issue}" for issue in report.issues)
    lines.extend(f"- WARN: {warning}" for warning in report.warnings)
    if not report.issues and not report.warnings:
        lines.append(
            "- Exact confirmation, metadata, receipt, provenance, memory, rollback, and run-once boundaries are healthy."
        )
    lines.extend(_boundary())
    return "\n".join(lines)


def _verify_durable_archive(
    reviewer: ProceduralSkillLifecycleApplyReadiness,
    *,
    original_records: list[dict[str, Any]],
    target_skill_id: str,
    expected_metadata: dict[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    snapshot = reviewer.skill_library.read_snapshot()
    if snapshot["error"] or snapshot["malformed_count"]:
        raise ProceduralSkillLifecycleMetadataApplyError(
            f"Skill Library post-write read failed: {snapshot['error'] or 'malformed JSONL'}"
        )
    current_records = snapshot["records"]
    if len(current_records) != len(original_records):
        raise ProceduralSkillLifecycleMetadataApplyError(
            "Skill record count changed unexpectedly."
        )
    before_by_id = _records_by_unique_id(original_records)
    after_by_id = _records_by_unique_id(current_records)
    if set(before_by_id) != set(after_by_id):
        raise ProceduralSkillLifecycleMetadataApplyError(
            "Skill record identity set changed unexpectedly."
        )
    changed_ids = [
        identifier
        for identifier in before_by_id
        if before_by_id[identifier] != after_by_id[identifier]
    ]
    if changed_ids != [target_skill_id]:
        raise ProceduralSkillLifecycleMetadataApplyError(
            "Durable archive must change exactly one target skill record."
        )
    before = before_by_id[target_skill_id]
    after = after_by_id[target_skill_id]
    changed_fields = sorted(
        key for key in set(before) | set(after) if before.get(key) != after.get(key)
    )
    if changed_fields != list(PROCEDURAL_SKILL_LIFECYCLE_METADATA_EXPECTED_CHANGED_FIELDS):
        raise ProceduralSkillLifecycleMetadataApplyError(
            "Durable archive changed fields outside lifecycle, status, and updated_at."
        )
    if before.get("status") != "active" or after.get("status") != "archived":
        raise ProceduralSkillLifecycleMetadataApplyError(
            "Durable archive status transition is not active to archived."
        )
    if "lifecycle" in before or after.get("lifecycle") != expected_metadata:
        raise ProceduralSkillLifecycleMetadataApplyError(
            "Durable archive lifecycle envelope does not match the confirmed payload."
        )
    metadata_check = verify_procedural_skill_lifecycle_metadata(
        after.get("lifecycle")
    )
    if not metadata_check.verified:
        raise ProceduralSkillLifecycleMetadataApplyError(
            "; ".join(metadata_check.issues)
            or "Durable archive lifecycle envelope does not verify."
        )
    if after.get("provenance") != before.get("provenance"):
        raise ProceduralSkillLifecycleMetadataApplyError(
            "Durable archive changed immutable provenance."
        )
    if after.get("executable") is not False:
        raise ProceduralSkillLifecycleMetadataApplyError(
            "Archived skill claims executable capability."
        )
    return deepcopy(after), changed_fields


def _metadata_matches_blueprint(
    metadata: dict[str, Any], blueprint: dict[str, Any]
) -> bool:
    ignored = {"dynamic_fields", "expected_metadata_fields"}
    return bool(
        blueprint
        and all(
            metadata.get(key) == value
            for key, value in blueprint.items()
            if key not in ignored
        )
        and set(metadata) == set(blueprint.get("expected_metadata_fields", []))
    )


def _unique_record_index(records: list[dict[str, Any]], skill_id: str) -> int:
    indexes = [
        index for index, record in enumerate(records) if record.get("id") == skill_id
    ]
    if len(indexes) != 1:
        raise ProceduralSkillLifecycleMetadataApplyError(
            "Durable lifecycle apply requires exactly one target skill record."
        )
    return indexes[0]


def _records_by_unique_id(
    records: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for record in records:
        identifier = str(record.get("id") or "")
        if not identifier or identifier in result:
            raise ProceduralSkillLifecycleMetadataApplyError(
                "Skill Library contains missing or duplicate record ids."
            )
        result[identifier] = record
    return result


def _receipt_identity_material(value: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value.get(key)
        for key in (
            "applied_at",
            "decision_receipt_id",
            "skill_id",
            "decision_hash",
            "metadata_blueprint_hash",
            "metadata_id",
            "metadata_hash",
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
        raise ProceduralSkillLifecycleMetadataApplyError(
            f"Skill Library is unreadable: {exc}"
        ) from exc


def _parse_jsonl(payload: bytes) -> list[dict[str, Any]]:
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ProceduralSkillLifecycleMetadataApplyError(
            "Skill Library is not UTF-8."
        ) from exc
    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ProceduralSkillLifecycleMetadataApplyError(
                f"Skill Library line {line_number} is malformed JSON."
            ) from exc
        if not isinstance(parsed, dict):
            raise ProceduralSkillLifecycleMetadataApplyError(
                f"Skill Library line {line_number} is not a JSON object."
            )
        records.append(parsed)
    return records


def _serialize_jsonl(records: list[dict[str, Any]]) -> bytes:
    if not records:
        return b""
    return (
        "\n".join(
            json.dumps(record, ensure_ascii=False, sort_keys=True)
            for record in records
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
            os.fsync(handle.fileno())
        temp_path.replace(path)
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
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
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _is_sha256(value: Any) -> bool:
    if not isinstance(value, str) or len(value) != 64:
        return False
    try:
        int(value, 16)
    except ValueError:
        return False
    return value == value.lower()


def _preview_usage() -> str:
    return (
        "Usage: /experience learning skill-outcome-lifecycle-apply-preview "
        "<skill_id|decision_receipt_id> --durable"
    )


def _apply_usage() -> str:
    return (
        "Usage: /experience learning apply skill-outcome-lifecycle "
        "<skill_id|decision_receipt_id> <exact token> --durable"
    )


def _applies_usage() -> str:
    return (
        "Usage: /experience learning skill-outcome-lifecycle-applies "
        "[<skill_id|decision_receipt_id|apply_receipt_id>] --durable"
    )


def _apply_error(message: str) -> str:
    return "\n".join(
        [
            "Proto-Mind Durable Procedural Skill Lifecycle Apply Error",
            "Status: ERROR",
            f"- {message}",
            *_boundary(),
        ]
    )


def _compact(value: Any) -> str:
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, list):
        return ", ".join(str(item) for item in value) or "none"
    return str(value) if value not in {None, ""} else "none"


def _boundary() -> list[str]:
    return [
        "Boundary:",
        "- Only one separately confirmed archive may persist durable lifecycle metadata per process; keep needs no envelope and revise is refused.",
        "- Success changes one skill record and exactly lifecycle, status, and updated_at; any failed verification restores exact prior bytes.",
        "- The receipt is process-memory-only; the embedded hashed envelope is the restart-safe lifecycle evidence.",
        "- No procedure, shell, arbitrary dispatch, batch, memory/event write, model/API, external action, session log, or Context Injection change occurred.",
    ]


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))
