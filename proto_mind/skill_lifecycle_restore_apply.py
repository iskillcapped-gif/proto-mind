from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
from threading import RLock
from typing import Any
from uuid import uuid4

from proto_mind.command_registry import COMMAND_REGISTRY
from proto_mind.experience_learning_skill_runtime import PROCEDURAL_SKILL_EXECUTION_INSTALLED
from proto_mind.skill_library import SkillLibrary
from proto_mind.skill_lifecycle_restore import (
    PROCEDURAL_SKILL_LIFECYCLE_RESTORE_EXPECTED_CHANGED_FIELDS,
    PROCEDURAL_SKILL_LIFECYCLE_RESTORE_RECEIPT_FIELDS,
    PROCEDURAL_SKILL_LIFECYCLE_RESTORE_WRITER_INSTALLED,
    build_procedural_skill_lifecycle_restore_metadata_preview,
    review_procedural_skill_lifecycle_restore,
    verify_procedural_skill_lifecycle_restore_metadata,
)
from proto_mind.skill_lifecycle_restore_authorization import (
    PROCEDURAL_SKILL_RESTORE_AUTHORIZATION_ENGINE_INSTALLED,
    PROCEDURAL_SKILL_RESTORE_MAX_SUCCESSFUL_APPLIES_PER_PROCESS,
    PROCEDURAL_SKILL_RESTORE_RUN_ONCE_STATE_INSTALLED,
    PROCEDURAL_SKILL_RESTORE_TOKEN_GENERATOR_INSTALLED,
    review_procedural_skill_restore_authorization,
)
from proto_mind.skill_provenance import verify_procedural_skill_provenance


PROCEDURAL_SKILL_RESTORE_APPLY_VERSION = 1
PROCEDURAL_SKILL_RESTORE_APPLY_MODE = "single_exact_confirmed_atomic_durable_restore"
PROCEDURAL_SKILL_RESTORE_APPLY_ENGINE_INSTALLED = True
PROCEDURAL_SKILL_RESTORE_APPLY_MAX_RECEIPTS = (
    PROCEDURAL_SKILL_RESTORE_MAX_SUCCESSFUL_APPLIES_PER_PROCESS
)


@dataclass(frozen=True)
class ProceduralSkillRestoreApplyReview:
    status: str
    skill_id: str
    audit_state: str
    authorization_blueprint_hash: str
    restore_review_hash: str
    restore_metadata_blueprint_hash: str
    restore_metadata_blueprint: dict[str, Any]
    prior_archive_id: str
    prior_archive_hash: str
    before_store_sha256: str
    before_record_hash: str
    expected_changed_fields: list[str]
    immutable_record_fields: list[str]
    checks: dict[str, bool]
    issues: list[str]
    warnings: list[str]
    confirmable: bool
    mutation_performed: bool = False
    procedure_execution_performed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ProceduralSkillRestoreApplyReceipt:
    restore_apply_id: str
    applied_at: str
    skill_id: str
    restore_review_hash: str
    restore_metadata_id: str
    restore_metadata_hash: str
    prior_archive_id: str
    prior_archive_hash: str
    before_store_sha256: str
    after_store_sha256: str
    before_record_hash: str
    after_record_hash: str
    exact_record_mutations: int
    changed_fields: list[str]
    confirmation_token_hash: str
    post_state_verified: bool
    archive_evidence_preserved: bool
    durable_provenance_preserved: bool
    persistent_memory_unchanged: bool
    rollback_performed: bool
    receipt_hash: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ProceduralSkillRestoreApplyDoctorReport:
    status: str
    receipt_count: int
    current_count: int
    historical_count: int
    issues: list[str]
    warnings: list[str]


class ProceduralSkillRestoreApplyError(RuntimeError):
    pass


class OperatorReviewedProceduralSkillRestoreApplySession:
    """Applies at most one exact durable restore transition per process."""

    def __init__(self) -> None:
        self._receipts: dict[str, ProceduralSkillRestoreApplyReceipt] = {}
        self._lock = RLock()

    def snapshot(self) -> tuple[dict[str, Any], ...]:
        with self._lock:
            return tuple(
                deepcopy(receipt.to_dict()) for receipt in self._receipts.values()
            )

    def get(self, identifier: str) -> ProceduralSkillRestoreApplyReceipt | None:
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
                        receipt.restore_apply_id,
                        receipt.skill_id,
                        receipt.restore_metadata_id,
                    }
                ),
                None,
            )

    def review(
        self,
        skill_id: str,
        *,
        skills_path: Path,
        persistent_memory_path: Path,
    ) -> ProceduralSkillRestoreApplyReview:
        with self._lock:
            return self._review_locked(
                skill_id,
                skills_path=skills_path,
                persistent_memory_path=persistent_memory_path,
            )

    def apply(
        self,
        skill_id: str,
        *,
        token: str,
        skills_path: Path,
        persistent_memory_path: Path,
    ) -> ProceduralSkillRestoreApplyReceipt:
        with self._lock:
            review = self._review_locked(
                skill_id,
                skills_path=skills_path,
                persistent_memory_path=persistent_memory_path,
            )
            if not review.confirmable:
                raise ProceduralSkillRestoreApplyError(
                    "; ".join(review.issues) or review.status
                )
            expected_token = procedural_skill_restore_apply_confirmation_token(review)
            if token != expected_token:
                raise ProceduralSkillRestoreApplyError(
                    "Durable restore confirmation token mismatch."
                )

            path = Path(skills_path)
            before_bytes = _read_bytes(path)
            if _hash_bytes(before_bytes) != review.before_store_sha256:
                raise ProceduralSkillRestoreApplyError(
                    "Skill Library changed after restore apply preview."
                )
            original_records = _parse_jsonl(before_bytes)
            target_index = _unique_record_index(original_records, review.skill_id)
            old_record = deepcopy(original_records[target_index])
            if _hash_json(old_record) != review.before_record_hash:
                raise ProceduralSkillRestoreApplyError(
                    "Skill record changed after restore apply preview."
                )

            memory_before = _hash_file(persistent_memory_path)
            applied_at = datetime.now(UTC).isoformat()
            token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
            provenance = old_record.get("provenance")
            if not isinstance(provenance, dict):
                raise ProceduralSkillRestoreApplyError(
                    "Current skill lacks embedded durable provenance."
                )
            restore_metadata = build_procedural_skill_lifecycle_restore_metadata_preview(
                skill_id=review.skill_id,
                skill_provenance_id=str(provenance.get("id") or ""),
                transitioned_at=applied_at,
                prior_archive_envelope=old_record.get("lifecycle"),
                restore_review_hash=review.restore_review_hash,
                before_record_hash=review.before_record_hash,
                confirmation_token_hash=token_hash,
            )
            if not _metadata_matches_blueprint(
                restore_metadata, review.restore_metadata_blueprint
            ):
                raise ProceduralSkillRestoreApplyError(
                    "Generated restore metadata differs from the confirmed blueprint."
                )

            updated_records = deepcopy(original_records)
            updated_records[target_index]["lifecycle"] = restore_metadata
            updated_records[target_index]["status"] = "active"
            updated_records[target_index]["updated_at"] = applied_at
            try:
                _atomic_replace(path, _serialize_jsonl(updated_records))
                verified_record, changed_fields = _verify_restore(
                    skills_path=path,
                    original_records=original_records,
                    target_skill_id=review.skill_id,
                    expected_metadata=restore_metadata,
                    immutable_record_fields=review.immutable_record_fields,
                )
                memory_after = _hash_file(persistent_memory_path)
                if memory_before == "unavailable" or memory_after != memory_before:
                    raise ProceduralSkillRestoreApplyError(
                        "Persistent memory changed during durable restore."
                    )
                provenance_check = verify_procedural_skill_provenance(
                    verified_record,
                    memory_records=_load_memory_records(persistent_memory_path),
                )
                if (
                    not provenance_check.verified
                    or not provenance_check.current_payload_matches
                    or verified_record.get("provenance") != old_record.get("provenance")
                ):
                    raise ProceduralSkillRestoreApplyError(
                        "Durable restore did not preserve exact verified skill provenance."
                    )
                from proto_mind.skill_lifecycle_audit import ProceduralSkillLifecycleAudit

                audit_entry = ProceduralSkillLifecycleAudit(
                    skills_path=path,
                    persistent_memory_path=persistent_memory_path,
                ).get(review.skill_id)
                if (
                    audit_entry is None
                    or audit_entry.state != "active_restored_verified"
                    or not audit_entry.restart_safe
                ):
                    raise ProceduralSkillRestoreApplyError(
                        "Post-write lifecycle audit did not recover active_restored_verified."
                    )
            except (
                OSError,
                TypeError,
                ValueError,
                json.JSONDecodeError,
                ProceduralSkillRestoreApplyError,
            ) as exc:
                _restore_bytes(path, before_bytes)
                if _read_bytes(path) != before_bytes:
                    raise ProceduralSkillRestoreApplyError(
                        "Restore verification failed and exact-byte rollback failed."
                    ) from exc
                raise ProceduralSkillRestoreApplyError(
                    "Durable restore verification failed; exact original Skill Library bytes were restored: "
                    f"{exc}"
                ) from exc

            after_bytes = _read_bytes(path)
            material = {
                "applied_at": applied_at,
                "skill_id": review.skill_id,
                "restore_review_hash": review.restore_review_hash,
                "restore_metadata_id": str(restore_metadata.get("id") or ""),
                "restore_metadata_hash": str(
                    restore_metadata.get("metadata_hash") or ""
                ),
                "prior_archive_id": review.prior_archive_id,
                "prior_archive_hash": review.prior_archive_hash,
                "before_store_sha256": review.before_store_sha256,
                "after_store_sha256": _hash_bytes(after_bytes),
                "before_record_hash": review.before_record_hash,
                "after_record_hash": _hash_json(verified_record),
                "exact_record_mutations": 1,
                "changed_fields": changed_fields,
                "confirmation_token_hash": token_hash,
                "post_state_verified": True,
                "archive_evidence_preserved": True,
                "durable_provenance_preserved": True,
                "persistent_memory_unchanged": True,
                "rollback_performed": False,
            }
            identity_hash = _hash_json(material)
            created = ProceduralSkillRestoreApplyReceipt(
                restore_apply_id=f"skillrestoreapply_{identity_hash[:16]}",
                **material,
            )
            created = replace(
                created,
                receipt_hash=procedural_skill_restore_apply_receipt_hash(
                    created.to_dict()
                ),
            )
            self._receipts[review.skill_id] = created
            return created

    def doctor(
        self,
        *,
        skills_path: Path,
        persistent_memory_path: Path,
    ) -> ProceduralSkillRestoreApplyDoctorReport:
        receipts = self.snapshot()
        issues: list[str] = []
        warnings: list[str] = []
        ids = [str(item.get("restore_apply_id") or "") for item in receipts]
        if len(receipts) > PROCEDURAL_SKILL_RESTORE_APPLY_MAX_RECEIPTS:
            issues.append("Durable restore receipt limit is exceeded.")
        if any(not value for value in ids) or len(ids) != len(set(ids)):
            issues.append("Durable restore receipt id is missing or duplicated.")

        current_count = 0
        historical_count = 0
        snapshot = SkillLibrary(skills_path).read_snapshot()
        for receipt in receipts:
            label = str(receipt.get("restore_apply_id") or "<missing>")
            if set(receipt) != set(PROCEDURAL_SKILL_LIFECYCLE_RESTORE_RECEIPT_FIELDS):
                issues.append(f"Receipt {label} does not match the fixed field contract.")
            expected_id = (
                f"skillrestoreapply_{_hash_json(_receipt_identity_material(receipt))[:16]}"
            )
            if label != expected_id:
                issues.append(f"Receipt {label} identity hash does not verify.")
            if receipt.get("receipt_hash") != procedural_skill_restore_apply_receipt_hash(
                receipt
            ):
                issues.append(f"Receipt {label} hash does not verify.")
            if receipt.get("exact_record_mutations") != 1:
                issues.append(f"Receipt {label} mutation count is invalid.")
            if receipt.get("changed_fields") != list(
                PROCEDURAL_SKILL_LIFECYCLE_RESTORE_EXPECTED_CHANGED_FIELDS
            ):
                issues.append(f"Receipt {label} changed-field scope is invalid.")
            for field in (
                "post_state_verified",
                "archive_evidence_preserved",
                "durable_provenance_preserved",
                "persistent_memory_unchanged",
            ):
                if receipt.get(field) is not True:
                    issues.append(f"Receipt {label} lacks {field} verification.")
            if receipt.get("rollback_performed") is not False:
                issues.append(f"Receipt {label} incorrectly claims rollback after success.")
            for field in (
                "restore_review_hash",
                "restore_metadata_hash",
                "prior_archive_hash",
                "before_store_sha256",
                "after_store_sha256",
                "before_record_hash",
                "after_record_hash",
                "confirmation_token_hash",
                "receipt_hash",
            ):
                if not _is_sha256(receipt.get(field)):
                    issues.append(f"Receipt {label} field {field} is not SHA-256.")

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
                check = verify_procedural_skill_lifecycle_restore_metadata(
                    matches[0].get("lifecycle")
                )
                if not check.verified or matches[0].get("status") != "active":
                    issues.append(
                        f"Receipt {label} current restore metadata/status does not verify."
                    )
                else:
                    current_count += 1

        registry = {entry.prefix: entry for entry in COMMAND_REGISTRY}
        restore_spec = registry.get("/skills restore")
        if (
            restore_spec is None
            or restore_spec.read_only
            or restore_spec.mutates != "skills"
            or restore_spec.risk != "medium"
        ):
            issues.append("Registry metadata for /skills restore is missing or unsafe.")
        for prefix in (
            "/skills lifecycle-status",
            "/skills lifecycle-inspect",
            "/skills lifecycle-doctor",
        ):
            spec = registry.get(prefix)
            if spec is None or not spec.read_only or spec.mutates != "none":
                issues.append(f"Registry metadata for {prefix} is missing or unsafe.")
        if not PROCEDURAL_SKILL_RESTORE_APPLY_ENGINE_INSTALLED:
            issues.append("Durable restore apply engine is unavailable.")
        if not PROCEDURAL_SKILL_LIFECYCLE_RESTORE_WRITER_INSTALLED:
            issues.append("Durable restore writer is unavailable.")
        if not PROCEDURAL_SKILL_RESTORE_AUTHORIZATION_ENGINE_INSTALLED:
            issues.append("Restore authorization engine is unavailable.")
        if not PROCEDURAL_SKILL_RESTORE_TOKEN_GENERATOR_INSTALLED:
            issues.append("Restore token generator is unavailable.")
        if not PROCEDURAL_SKILL_RESTORE_RUN_ONCE_STATE_INSTALLED:
            issues.append("Restore run-once state is unavailable.")
        if PROCEDURAL_SKILL_EXECUTION_INSTALLED:
            issues.append("Procedural skill execution must remain disabled.")
        if not receipts:
            warnings.append("No durable restore occurred this process.")
        return ProceduralSkillRestoreApplyDoctorReport(
            status="ERROR" if issues else "WARN" if warnings else "OK",
            receipt_count=len(receipts),
            current_count=current_count,
            historical_count=historical_count,
            issues=_dedupe(issues),
            warnings=_dedupe(warnings),
        )

    def _review_locked(
        self,
        skill_id: str,
        *,
        skills_path: Path,
        persistent_memory_path: Path,
    ) -> ProceduralSkillRestoreApplyReview:
        identifier = skill_id.strip()
        authorization = review_procedural_skill_restore_authorization(
            identifier,
            skills_path=skills_path,
            persistent_memory_path=persistent_memory_path,
        )
        restore = review_procedural_skill_lifecycle_restore(
            identifier,
            skills_path=skills_path,
            persistent_memory_path=persistent_memory_path,
        )
        blueprint = authorization.authorization_blueprint
        restore_spec = {entry.prefix: entry for entry in COMMAND_REGISTRY}.get(
            "/skills restore"
        )
        checks = {
            "authorization_readiness_current": (
                authorization.ready_for_authorization_design_review
            ),
            "archived_verified_state": authorization.audit_state == "archived_verified",
            "restore_not_applied": identifier not in self._receipts,
            "run_once_slot_available": len(self._receipts)
            < PROCEDURAL_SKILL_RESTORE_APPLY_MAX_RECEIPTS,
            "apply_engine_installed": PROCEDURAL_SKILL_RESTORE_APPLY_ENGINE_INSTALLED,
            "authorization_engine_installed": (
                PROCEDURAL_SKILL_RESTORE_AUTHORIZATION_ENGINE_INSTALLED
            ),
            "token_generator_installed": PROCEDURAL_SKILL_RESTORE_TOKEN_GENERATOR_INSTALLED,
            "run_once_state_installed": PROCEDURAL_SKILL_RESTORE_RUN_ONCE_STATE_INSTALLED,
            "restore_writer_installed": PROCEDURAL_SKILL_LIFECYCLE_RESTORE_WRITER_INSTALLED,
            "registry_apply_gate_safe": bool(
                restore_spec is not None
                and not restore_spec.read_only
                and restore_spec.mutates == "skills"
                and restore_spec.risk == "medium"
            ),
            "procedure_execution_disabled": not PROCEDURAL_SKILL_EXECUTION_INSTALLED,
            "exact_changed_fields_locked": blueprint.get("expected_changed_fields")
            == list(PROCEDURAL_SKILL_LIFECYCLE_RESTORE_EXPECTED_CHANGED_FIELDS),
            "immutable_fields_bound": bool(blueprint.get("immutable_record_fields")),
            "restore_blueprint_bound": bool(
                restore.metadata_blueprint
                and _is_sha256(restore.metadata_blueprint_hash)
                and restore.metadata_blueprint_hash
                == authorization.restore_metadata_blueprint_hash
            ),
        }
        messages = {
            "authorization_readiness_current": "Current restore authorization readiness is not READY.",
            "archived_verified_state": "Only archived_verified state may be restored.",
            "restore_not_applied": "This skill was already restored in this process.",
            "run_once_slot_available": "The single durable restore slot is already used this process.",
            "apply_engine_installed": "Durable restore apply engine is unavailable.",
            "authorization_engine_installed": "Restore authorization engine is unavailable.",
            "token_generator_installed": "Restore token generator is unavailable.",
            "run_once_state_installed": "Restore run-once state is unavailable.",
            "restore_writer_installed": "Durable restore writer is unavailable.",
            "registry_apply_gate_safe": "Registry /skills restore gate is missing or unsafe.",
            "procedure_execution_disabled": "Procedural skill execution must remain disabled.",
            "exact_changed_fields_locked": "Restore changed-field scope is not exact.",
            "immutable_fields_bound": "Restore immutable field scope is absent.",
            "restore_blueprint_bound": "Restore metadata blueprint is absent or stale.",
        }
        issues = list(authorization.issues)
        issues.extend(messages[name] for name, passed in checks.items() if not passed)
        confirmable = all(checks.values()) and not issues
        return ProceduralSkillRestoreApplyReview(
            status="CONFIRMABLE" if confirmable else "NOT CONFIRMABLE",
            skill_id=identifier,
            audit_state=authorization.audit_state,
            authorization_blueprint_hash=authorization.authorization_blueprint_hash,
            restore_review_hash=authorization.restore_review_hash,
            restore_metadata_blueprint_hash=(
                authorization.restore_metadata_blueprint_hash
            ),
            restore_metadata_blueprint=deepcopy(restore.metadata_blueprint),
            prior_archive_id=str(blueprint.get("prior_archive_id") or ""),
            prior_archive_hash=str(blueprint.get("prior_archive_hash") or ""),
            before_store_sha256=authorization.skill_store_sha256,
            before_record_hash=authorization.skill_record_hash,
            expected_changed_fields=list(
                blueprint.get("expected_changed_fields") or []
            ),
            immutable_record_fields=list(
                blueprint.get("immutable_record_fields") or []
            ),
            checks=checks,
            issues=_dedupe(issues),
            warnings=list(authorization.warnings),
            confirmable=confirmable,
        )


_RESTORE_APPLY_SESSION = OperatorReviewedProceduralSkillRestoreApplySession()


def reset_procedural_skill_restore_apply_session() -> None:
    global _RESTORE_APPLY_SESSION
    _RESTORE_APPLY_SESSION = OperatorReviewedProceduralSkillRestoreApplySession()


def procedural_skill_restore_apply_confirmation_token(
    review: ProceduralSkillRestoreApplyReview,
) -> str:
    material = {
        "skill_id": review.skill_id,
        "authorization_blueprint_hash": review.authorization_blueprint_hash,
        "restore_review_hash": review.restore_review_hash,
        "restore_metadata_blueprint_hash": review.restore_metadata_blueprint_hash,
        "before_store_sha256": review.before_store_sha256,
        "before_record_hash": review.before_record_hash,
        "prior_archive_id": review.prior_archive_id,
        "prior_archive_hash": review.prior_archive_hash,
        "expected_changed_fields": review.expected_changed_fields,
        "immutable_record_fields": review.immutable_record_fields,
    }
    return f"CONFIRM-DURABLE-SKILL-RESTORE-{_hash_json(material)[:12].upper()}"


def procedural_skill_restore_apply_receipt_hash(receipt: dict[str, Any]) -> str:
    return _hash_json(
        {key: value for key, value in receipt.items() if key != "receipt_hash"}
    )


def format_procedural_skill_restore_apply_command(
    command: str,
    *,
    skills_path: Path,
    persistent_memory_path: Path,
    apply_session: OperatorReviewedProceduralSkillRestoreApplySession | None = None,
) -> str | None:
    raw = command.strip()
    normalized = " ".join(raw.lower().split())
    recognized = bool(
        normalized == "/skills lifecycle-status --restore-applies"
        or normalized == "/skills lifecycle-doctor --restore-apply"
        or normalized.startswith("/skills lifecycle-inspect ")
        and any(
            flag in normalized
            for flag in ("--restore-apply-preview", "--restore-apply-receipt")
        )
        or normalized.startswith("/skills restore ")
        and "--durable" in normalized
    )
    if not recognized:
        return None
    if any(marker in raw for marker in ("\n", ";", "&&", "||", "|")):
        return _apply_error("Command chaining and multi-command input are not allowed.")
    session = apply_session or _RESTORE_APPLY_SESSION
    parts = raw.split()
    if normalized == "/skills lifecycle-status --restore-applies":
        return format_procedural_skill_restore_applies(session.snapshot())
    if normalized == "/skills lifecycle-doctor --restore-apply":
        return format_procedural_skill_restore_apply_doctor(
            session.doctor(
                skills_path=skills_path,
                persistent_memory_path=persistent_memory_path,
            )
        )
    if normalized.startswith("/skills lifecycle-inspect "):
        if len(parts) != 4:
            return _apply_usage()
        if parts[3].lower() == "--restore-apply-preview":
            return format_procedural_skill_restore_apply_preview(
                session.review(
                    parts[2],
                    skills_path=skills_path,
                    persistent_memory_path=persistent_memory_path,
                )
            )
        if parts[3].lower() == "--restore-apply-receipt":
            return format_procedural_skill_restore_apply_receipt(session.get(parts[2]))
        return _apply_usage()
    if normalized.startswith("/skills restore "):
        if len(parts) != 5 or parts[4].lower() != "--durable":
            return _apply_usage()
        try:
            receipt = session.apply(
                parts[2],
                token=parts[3],
                skills_path=skills_path,
                persistent_memory_path=persistent_memory_path,
            )
        except (
            OSError,
            TypeError,
            ValueError,
            json.JSONDecodeError,
            ProceduralSkillRestoreApplyError,
        ) as exc:
            return _apply_error(str(exc))
        return format_procedural_skill_restored(receipt)
    return _apply_usage()


def format_procedural_skill_restore_apply_preview(
    review: ProceduralSkillRestoreApplyReview,
) -> str:
    lines = [
        "Proto-Mind Durable Skill Restore Apply Preview v1",
        f"Status: {review.status}",
        f"mode: {PROCEDURAL_SKILL_RESTORE_APPLY_MODE}",
        f"skill_id: {review.skill_id or 'missing'}",
        f"audit_state: {review.audit_state}",
        f"authorization_blueprint_hash: {review.authorization_blueprint_hash or 'unavailable'}",
        f"restore_review_hash: {review.restore_review_hash}",
        f"restore_metadata_blueprint_hash: {review.restore_metadata_blueprint_hash or 'unavailable'}",
        f"before_store_sha256: {review.before_store_sha256}",
        f"before_record_hash: {review.before_record_hash or 'unavailable'}",
        f"expected_changed_fields: {', '.join(review.expected_changed_fields) or 'none'}",
        f"immutable_record_fields: {', '.join(review.immutable_record_fields) or 'none'}",
        "procedure_execution_performed: false",
        "mutation_performed: false",
        "Checks:",
    ]
    lines.extend(
        f"- {name}: {str(value).lower()}" for name, value in review.checks.items()
    )
    lines.extend(f"- BLOCKER: {issue}" for issue in review.issues)
    lines.extend(f"- WARN: {warning}" for warning in review.warnings)
    if review.confirmable:
        token = procedural_skill_restore_apply_confirmation_token(review)
        lines.extend(
            [
                f"confirmation_token: {token}",
                "Exact apply command:",
                f"/skills restore {review.skill_id} {token} --durable",
            ]
        )
    lines.extend(_apply_boundary())
    return "\n".join(lines)


def format_procedural_skill_restored(receipt: ProceduralSkillRestoreApplyReceipt) -> str:
    return "\n".join(
        [
            "Proto-Mind Durable Skill Restore Apply v1",
            "Status: APPLIED",
            f"restore_apply_id: {receipt.restore_apply_id}",
            f"skill_id: {receipt.skill_id}",
            f"restore_metadata_id: {receipt.restore_metadata_id}",
            f"restore_metadata_hash: {receipt.restore_metadata_hash}",
            f"exact_record_mutations: {receipt.exact_record_mutations}",
            f"changed_fields: {', '.join(receipt.changed_fields)}",
            f"post_state_verified: {str(receipt.post_state_verified).lower()}",
            f"archive_evidence_preserved: {str(receipt.archive_evidence_preserved).lower()}",
            "procedure_execution_performed: false",
            *_apply_boundary(),
        ]
    )


def format_procedural_skill_restore_applies(
    receipts: tuple[dict[str, Any], ...],
) -> str:
    lines = [
        "Proto-Mind Durable Skill Restore Applies v1",
        f"Status: {'OK' if receipts else 'EMPTY'}",
        f"receipts: {len(receipts)}/{PROCEDURAL_SKILL_RESTORE_APPLY_MAX_RECEIPTS}",
    ]
    if not receipts:
        lines.append("- none")
    for receipt in receipts:
        lines.append(
            f"- {receipt.get('restore_apply_id')} | {receipt.get('skill_id')} | "
            f"metadata={receipt.get('restore_metadata_id')}"
        )
    lines.extend(_apply_boundary())
    return "\n".join(lines)


def format_procedural_skill_restore_apply_receipt(
    receipt: ProceduralSkillRestoreApplyReceipt | None,
) -> str:
    if receipt is None:
        return _apply_error("Durable restore apply receipt was not found.")
    lines = ["Proto-Mind Durable Skill Restore Apply Receipt v1", "Status: OK"]
    lines.extend(f"{key}: {_compact(value)}" for key, value in receipt.to_dict().items())
    lines.extend(_apply_boundary())
    return "\n".join(lines)


def format_procedural_skill_restore_apply_doctor(
    report: ProceduralSkillRestoreApplyDoctorReport,
) -> str:
    lines = [
        "Proto-Mind Durable Skill Restore Apply Doctor v1",
        f"Status: {report.status}",
        f"mode: {PROCEDURAL_SKILL_RESTORE_APPLY_MODE}",
        f"receipts: {report.receipt_count}/{PROCEDURAL_SKILL_RESTORE_APPLY_MAX_RECEIPTS}",
        f"current: {report.current_count}",
        f"historical: {report.historical_count}",
        f"apply_engine_installed: {str(PROCEDURAL_SKILL_RESTORE_APPLY_ENGINE_INSTALLED).lower()}",
        f"writer_installed: {str(PROCEDURAL_SKILL_LIFECYCLE_RESTORE_WRITER_INSTALLED).lower()}",
        "procedure_execution_enabled: false",
    ]
    lines.extend(f"- ERROR: {issue}" for issue in report.issues)
    lines.extend(f"- WARN: {warning}" for warning in report.warnings)
    if not report.issues and not report.warnings:
        lines.append(
            "- Exact confirmation, run-once, receipt, archive evidence, provenance, memory, and rollback boundaries are healthy."
        )
    lines.extend(_apply_boundary())
    return "\n".join(lines)


def _verify_restore(
    *,
    skills_path: Path,
    original_records: list[dict[str, Any]],
    target_skill_id: str,
    expected_metadata: dict[str, Any],
    immutable_record_fields: list[str],
) -> tuple[dict[str, Any], list[str]]:
    snapshot = SkillLibrary(skills_path).read_snapshot()
    if snapshot["error"] or snapshot["malformed_count"]:
        raise ProceduralSkillRestoreApplyError(
            f"Skill Library post-write read failed: {snapshot['error'] or 'malformed JSONL'}"
        )
    current_records = snapshot["records"]
    if len(current_records) != len(original_records):
        raise ProceduralSkillRestoreApplyError("Skill record count changed unexpectedly.")
    old_by_id = {str(record.get("id") or ""): record for record in original_records}
    current_by_id = {str(record.get("id") or ""): record for record in current_records}
    if set(old_by_id) != set(current_by_id) or "" in old_by_id:
        raise ProceduralSkillRestoreApplyError(
            "Skill record identities changed unexpectedly."
        )
    changed_ids = [
        identifier
        for identifier in old_by_id
        if old_by_id[identifier] != current_by_id[identifier]
    ]
    if changed_ids != [target_skill_id]:
        raise ProceduralSkillRestoreApplyError(
            "Durable restore changed an unexpected record set."
        )
    old_record = old_by_id[target_skill_id]
    current = current_by_id[target_skill_id]
    changed_fields = sorted(
        key
        for key in set(old_record) | set(current)
        if old_record.get(key) != current.get(key)
    )
    expected_changed = sorted(PROCEDURAL_SKILL_LIFECYCLE_RESTORE_EXPECTED_CHANGED_FIELDS)
    if changed_fields != expected_changed:
        raise ProceduralSkillRestoreApplyError(
            "Durable restore changed fields outside lifecycle/status/updated_at."
        )
    if current.get("status") != "active" or current.get("lifecycle") != expected_metadata:
        raise ProceduralSkillRestoreApplyError(
            "Durable restore target status or metadata differs from the confirmed write."
        )
    for field in immutable_record_fields:
        if old_record.get(field) != current.get(field):
            raise ProceduralSkillRestoreApplyError(
                f"Durable restore changed immutable field {field}."
            )
    metadata_check = verify_procedural_skill_lifecycle_restore_metadata(
        current.get("lifecycle")
    )
    if not metadata_check.verified:
        raise ProceduralSkillRestoreApplyError(
            "; ".join(metadata_check.issues)
            or "Restore metadata post-write verification failed."
        )
    return current, list(PROCEDURAL_SKILL_LIFECYCLE_RESTORE_EXPECTED_CHANGED_FIELDS)


def _metadata_matches_blueprint(
    metadata: dict[str, Any], blueprint: dict[str, Any]
) -> bool:
    dynamic = set(blueprint.get("dynamic_fields") or [])
    expected_fields = set(blueprint.get("expected_metadata_fields") or [])
    if set(metadata) != expected_fields:
        return False
    for key, expected in blueprint.items():
        if key in {"dynamic_fields", "expected_metadata_fields"} or key in dynamic:
            continue
        if metadata.get(key) != expected:
            return False
    return verify_procedural_skill_lifecycle_restore_metadata(metadata).verified


def _load_memory_records(path: Path) -> list[Any]:
    from proto_mind.memory_store import MemoryStore

    return MemoryStore(
        working_path=Path(path).parent / "working_memory.json",
        persistent_path=Path(path),
    ).load_persistent_memory()


def _unique_record_index(records: list[dict[str, Any]], identifier: str) -> int:
    matches = [
        index for index, record in enumerate(records) if record.get("id") == identifier
    ]
    if len(matches) != 1:
        raise ProceduralSkillRestoreApplyError(
            "Durable restore requires exactly one target skill record."
        )
    return matches[0]


def _parse_jsonl(payload: bytes) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for line_number, raw_line in enumerate(payload.decode("utf-8").splitlines(), 1):
        if not raw_line.strip():
            continue
        parsed = json.loads(raw_line)
        if not isinstance(parsed, dict):
            raise ProceduralSkillRestoreApplyError(
                f"Skill JSONL line {line_number} is not an object."
            )
        records.append(parsed)
    return records


def _serialize_jsonl(records: list[dict[str, Any]]) -> bytes:
    return "".join(
        json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n"
        for record in records
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
    finally:
        if temp_path.exists():
            temp_path.unlink()


def _restore_bytes(path: Path, payload: bytes) -> None:
    _atomic_replace(path, payload)


def _read_bytes(path: Path) -> bytes:
    try:
        return Path(path).read_bytes()
    except OSError as exc:
        raise ProceduralSkillRestoreApplyError(
            f"Skill Library is unreadable: {exc}"
        ) from exc


def _hash_file(path: Path) -> str:
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError:
        return "unavailable"


def _hash_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _hash_json(value: Any) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _receipt_identity_material(receipt: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in receipt.items()
        if key not in {"restore_apply_id", "receipt_hash"}
    }


def _is_sha256(value: Any) -> bool:
    text = str(value or "")
    return len(text) == 64 and all(char in "0123456789abcdef" for char in text)


def _apply_usage() -> str:
    return "\n".join(
        [
            "Usage:",
            "  /skills lifecycle-status --restore-applies",
            "  /skills lifecycle-inspect <skill_id> --restore-apply-preview",
            "  /skills restore <skill_id> <exact_token> --durable",
            "  /skills lifecycle-inspect <skill_id> --restore-apply-receipt",
            "  /skills lifecycle-doctor --restore-apply",
        ]
    )


def _apply_error(message: str) -> str:
    return "\n".join(
        [
            "Proto-Mind Durable Skill Restore Apply Error",
            "Status: ERROR",
            f"- {message}",
            *_apply_boundary(),
        ]
    )


def _apply_boundary() -> list[str]:
    return [
        "Boundary:",
        "- Only one current archived_verified skill may consume one exact hash-bound restore token per process.",
        "- The writer changes one record and only lifecycle/status/updated_at, then verifies receipt, immutable payload/provenance, unchanged memory, restart-safe audit, and rollback readiness.",
        "- Generic restore, repeated/batch restore, revision, procedure execution, shell, model/API, and external actions remain unavailable.",
        "- Context Injection, session log schema, queues, exports, and unrelated stores are unchanged.",
    ]


def _compact(value: Any) -> str:
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, list):
        return ", ".join(str(item) for item in value) or "none"
    return str(value) if value not in {None, ""} else "none"


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))
