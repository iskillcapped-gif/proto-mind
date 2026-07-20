from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass
from datetime import datetime
import hashlib
import json
from pathlib import Path
from typing import Any

from proto_mind.command_registry import COMMAND_REGISTRY
from proto_mind.skill_library import (
    SKILL_LIFECYCLE_DIRECT_STATUS_GUARD_INSTALLED,
    SKILL_LIFECYCLE_PAYLOAD_GUARD_INSTALLED,
    SkillLibrary,
)
from proto_mind.skill_lifecycle_audit import (
    ProceduralSkillLifecycleAudit,
    ProceduralSkillLifecycleAuditError,
)
from proto_mind.skill_lifecycle_metadata import (
    verify_procedural_skill_lifecycle_metadata,
)


PROCEDURAL_SKILL_LIFECYCLE_RESTORE_VERSION = 1
PROCEDURAL_SKILL_LIFECYCLE_RESTORE_SCHEMA = (
    "skill.procedure.lifecycle.restore.v1"
)
PROCEDURAL_SKILL_LIFECYCLE_RESTORE_MODE = (
    "read_only_embedded_archive_restore_design_review"
)
PROCEDURAL_SKILL_LIFECYCLE_RESTORE_WRITER_INSTALLED = True
PROCEDURAL_SKILL_LIFECYCLE_RESTORE_REASON = "operator_confirmed_reactivation"
PROCEDURAL_SKILL_LIFECYCLE_RESTORE_MAX_ARCHIVE_BYTES = 16_384
PROCEDURAL_SKILL_LIFECYCLE_RESTORE_EXPECTED_CHANGED_FIELDS = (
    "lifecycle",
    "status",
    "updated_at",
)
PROCEDURAL_SKILL_LIFECYCLE_RESTORE_DYNAMIC_FIELDS = (
    "id",
    "transitioned_at",
    "confirmation_token_hash",
    "metadata_hash",
)
PROCEDURAL_SKILL_LIFECYCLE_RESTORE_FIELDS = (
    "version",
    "schema",
    "id",
    "skill_id",
    "skill_provenance_id",
    "transition",
    "reason",
    "from_status",
    "to_status",
    "transitioned_at",
    "prior_archive_id",
    "prior_archive_hash",
    "prior_archive_envelope",
    "restore_review_hash",
    "before_record_hash",
    "confirmation_method",
    "confirmation_token_hash",
    "evidence_retention",
    "evidence_replay_available",
    "automatic",
    "procedure_execution_performed",
    "payload_mutation_performed",
    "metadata_hash",
)
PROCEDURAL_SKILL_LIFECYCLE_RESTORE_RECEIPT_FIELDS = (
    "restore_apply_id",
    "applied_at",
    "skill_id",
    "restore_review_hash",
    "restore_metadata_id",
    "restore_metadata_hash",
    "prior_archive_id",
    "prior_archive_hash",
    "before_store_sha256",
    "after_store_sha256",
    "before_record_hash",
    "after_record_hash",
    "exact_record_mutations",
    "changed_fields",
    "confirmation_token_hash",
    "post_state_verified",
    "archive_evidence_preserved",
    "durable_provenance_preserved",
    "persistent_memory_unchanged",
    "rollback_performed",
    "receipt_hash",
)


@dataclass(frozen=True)
class ProceduralSkillLifecycleRestoreMetadataCheck:
    status: str
    verified: bool
    metadata_id: str
    skill_id: str
    prior_archive_id: str
    hash_verified: bool
    identity_verified: bool
    archive_envelope_verified: bool
    issues: list[str]
    warnings: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ProceduralSkillLifecycleRestoreReadinessReport:
    status: str
    skill_id: str
    audit_state: str
    current_status: str
    provenance_status: str
    archive_metadata_id: str
    archive_metadata_hash: str
    skill_store_sha256: str
    skill_record_hash: str
    restore_review_hash: str
    metadata_blueprint_hash: str
    metadata_blueprint: dict[str, Any]
    expected_changed_fields: list[str]
    future_receipt_fields: list[str]
    active_duplicate_skill_ids: list[str]
    checks: dict[str, bool]
    issues: list[str]
    warnings: list[str]
    ready_for_design_review: bool
    writer_installed: bool = True
    direct_status_guard_installed: bool = True
    payload_guard_installed: bool = True
    apply_token_generated: bool = False
    mutation_performed: bool = False


@dataclass(frozen=True)
class ProceduralSkillLifecycleRestoreDoctorReport:
    status: str
    schema: str
    field_count: int
    receipt_field_count: int
    deterministic_example_verified: bool
    tamper_refused: bool
    writer_installed: bool
    direct_status_guard_installed: bool
    payload_guard_installed: bool
    registry_coverage_ok: bool
    issues: list[str]
    warnings: list[str]
    mutation_performed: bool = False


def build_procedural_skill_lifecycle_restore_metadata_preview(
    *,
    skill_id: str,
    skill_provenance_id: str,
    transitioned_at: str,
    prior_archive_envelope: dict[str, Any],
    restore_review_hash: str,
    before_record_hash: str,
    confirmation_token_hash: str,
) -> dict[str, Any]:
    """Build a detached restore envelope without reading or writing storage."""

    archive = deepcopy(prior_archive_envelope)
    archive_check = verify_procedural_skill_lifecycle_metadata(archive)
    if not archive_check.verified:
        raise ValueError(
            "; ".join(archive_check.issues)
            or "Prior archive lifecycle envelope is invalid."
        )
    material = {
        "version": PROCEDURAL_SKILL_LIFECYCLE_RESTORE_VERSION,
        "schema": PROCEDURAL_SKILL_LIFECYCLE_RESTORE_SCHEMA,
        "skill_id": skill_id.strip(),
        "skill_provenance_id": skill_provenance_id.strip(),
        "transition": "restore",
        "reason": PROCEDURAL_SKILL_LIFECYCLE_RESTORE_REASON,
        "from_status": "archived",
        "to_status": "active",
        "transitioned_at": transitioned_at.strip(),
        "prior_archive_id": archive_check.metadata_id,
        "prior_archive_hash": str(archive.get("metadata_hash") or ""),
        "prior_archive_envelope": archive,
        "restore_review_hash": restore_review_hash.strip().lower(),
        "before_record_hash": before_record_hash.strip().lower(),
        "confirmation_method": "exact_current_skill_lifecycle_restore_token",
        "confirmation_token_hash": confirmation_token_hash.strip().lower(),
        "evidence_retention": "embedded_verified_archive_envelope",
        "evidence_replay_available": False,
        "automatic": False,
        "procedure_execution_performed": False,
        "payload_mutation_performed": False,
    }
    identity_hash = _hash_json(material)
    payload = {**material, "id": f"skillrestore_{identity_hash[:16]}"}
    payload["metadata_hash"] = _hash_json(payload)
    check = verify_procedural_skill_lifecycle_restore_metadata(payload)
    if not check.verified:
        raise ValueError(
            "; ".join(check.issues) or "Lifecycle restore metadata is invalid."
        )
    return payload


def verify_procedural_skill_lifecycle_restore_metadata(
    value: Any,
) -> ProceduralSkillLifecycleRestoreMetadataCheck:
    issues: list[str] = []
    warnings: list[str] = []
    payload = dict(value) if isinstance(value, dict) else {}
    if not isinstance(value, dict):
        issues.append("Lifecycle restore metadata must be an object.")

    expected_fields = set(PROCEDURAL_SKILL_LIFECYCLE_RESTORE_FIELDS)
    actual_fields = set(payload)
    missing = sorted(expected_fields - actual_fields)
    unexpected = sorted(actual_fields - expected_fields)
    if missing:
        issues.append(f"Missing lifecycle restore fields: {', '.join(missing)}.")
    if unexpected:
        issues.append(
            f"Unexpected lifecycle restore fields: {', '.join(unexpected)}."
        )
    if payload.get("version") != PROCEDURAL_SKILL_LIFECYCLE_RESTORE_VERSION:
        issues.append("Lifecycle restore metadata version is unsupported.")
    if payload.get("schema") != PROCEDURAL_SKILL_LIFECYCLE_RESTORE_SCHEMA:
        issues.append("Lifecycle restore metadata schema is unsupported.")
    if payload.get("transition") != "restore":
        issues.append("Lifecycle restore contract supports only restore.")
    if payload.get("reason") != PROCEDURAL_SKILL_LIFECYCLE_RESTORE_REASON:
        issues.append("Lifecycle restore reason is outside the v1 contract.")
    if payload.get("from_status") != "archived" or payload.get(
        "to_status"
    ) != "active":
        issues.append("Lifecycle restore metadata must describe archived -> active.")
    for field in ("skill_id", "skill_provenance_id", "prior_archive_id"):
        if not isinstance(payload.get(field), str) or not str(
            payload.get(field)
        ).strip():
            issues.append(f"Lifecycle restore field {field} must be non-empty text.")
    if not _valid_timestamp(payload.get("transitioned_at")):
        issues.append(
            "Lifecycle restore transitioned_at must be timezone-aware ISO-8601."
        )
    for field in (
        "prior_archive_hash",
        "restore_review_hash",
        "before_record_hash",
        "confirmation_token_hash",
    ):
        if not _is_sha256(payload.get(field)):
            issues.append(f"Lifecycle restore field {field} must be SHA-256.")

    archive = payload.get("prior_archive_envelope")
    archive_check = verify_procedural_skill_lifecycle_metadata(archive)
    archive_verified = archive_check.verified
    if not archive_verified:
        issues.extend(
            f"Prior archive envelope: {item}" for item in archive_check.issues
        )
    if _json_size(archive) > PROCEDURAL_SKILL_LIFECYCLE_RESTORE_MAX_ARCHIVE_BYTES:
        issues.append("Prior archive envelope exceeds the restore size bound.")
    if payload.get("prior_archive_id") != archive_check.metadata_id:
        issues.append("Prior archive id does not match the embedded envelope.")
    if isinstance(archive, dict) and payload.get("prior_archive_hash") != archive.get(
        "metadata_hash"
    ):
        issues.append("Prior archive hash does not match the embedded envelope.")
    if archive_check.skill_id and payload.get("skill_id") != archive_check.skill_id:
        issues.append("Restore skill id differs from the prior archive envelope.")
    if isinstance(archive, dict) and payload.get(
        "skill_provenance_id"
    ) != archive.get("skill_provenance_id"):
        issues.append(
            "Restore provenance id differs from the prior archive envelope."
        )
    if payload.get("confirmation_method") != (
        "exact_current_skill_lifecycle_restore_token"
    ):
        issues.append("Lifecycle restore lacks the exact confirmation method.")
    if payload.get("evidence_retention") != (
        "embedded_verified_archive_envelope"
    ):
        issues.append("Lifecycle restore evidence-retention scope is invalid.")
    for field in (
        "evidence_replay_available",
        "automatic",
        "procedure_execution_performed",
        "payload_mutation_performed",
    ):
        if payload.get(field) is not False:
            issues.append(f"Lifecycle restore safety field {field} must be false.")

    identity_material = {
        key: payload.get(key)
        for key in PROCEDURAL_SKILL_LIFECYCLE_RESTORE_FIELDS
        if key not in {"id", "metadata_hash"}
    }
    expected_id = f"skillrestore_{_hash_json(identity_material)[:16]}"
    identity_verified = payload.get("id") == expected_id
    if not identity_verified:
        issues.append("Lifecycle restore identity hash does not verify.")
    hash_material = {
        key: payload.get(key)
        for key in PROCEDURAL_SKILL_LIFECYCLE_RESTORE_FIELDS
        if key != "metadata_hash"
    }
    expected_hash = _hash_json(hash_material)
    hash_verified = payload.get("metadata_hash") == expected_hash
    if not hash_verified:
        issues.append("Lifecycle restore metadata hash does not verify.")
    if payload and not issues:
        warnings.append(
            "Restore integrity preserves archive evidence but does not replay expired process evidence or prove procedure quality."
        )

    return ProceduralSkillLifecycleRestoreMetadataCheck(
        status="ERROR" if issues else "VERIFIED",
        verified=not issues,
        metadata_id=str(payload.get("id") or ""),
        skill_id=str(payload.get("skill_id") or ""),
        prior_archive_id=str(payload.get("prior_archive_id") or ""),
        hash_verified=hash_verified,
        identity_verified=identity_verified,
        archive_envelope_verified=archive_verified,
        issues=_dedupe(issues),
        warnings=_dedupe(warnings),
    )


def review_procedural_skill_lifecycle_restore(
    skill_id: str,
    *,
    skills_path: Path,
    persistent_memory_path: Path,
) -> ProceduralSkillLifecycleRestoreReadinessReport:
    identifier = skill_id.strip()
    library = SkillLibrary(skills_path)
    snapshot = library.read_snapshot()
    records = snapshot["records"]
    matching = [record for record in records if record.get("id") == identifier]
    record = deepcopy(matching[0]) if len(matching) == 1 else {}
    audit_state = "missing"
    provenance_status = "UNAVAILABLE"
    audit_issues: list[str] = []
    try:
        entry = ProceduralSkillLifecycleAudit(
            skills_path=skills_path,
            persistent_memory_path=persistent_memory_path,
        ).get(identifier)
    except ProceduralSkillLifecycleAuditError as exc:
        entry = None
        audit_issues.append(str(exc))
    if entry is not None:
        audit_state = entry.state
        provenance_status = entry.provenance_status
        audit_issues.extend(entry.issues)

    archive = record.get("lifecycle")
    archive_check = verify_procedural_skill_lifecycle_metadata(archive)
    ids = [str(item.get("id") or "") for item in records]
    active_duplicates = _active_duplicate_ids(record, records)
    store_hash = _hash_file(skills_path)
    record_hash = _hash_json(record) if record else ""
    review_material = {
        "skill_id": identifier,
        "audit_state": audit_state,
        "provenance_status": provenance_status,
        "archive_metadata_id": archive_check.metadata_id,
        "archive_metadata_hash": (
            str(archive.get("metadata_hash") or "")
            if isinstance(archive, dict)
            else ""
        ),
        "skill_store_sha256": store_hash,
        "skill_record_hash": record_hash,
        "expected_changed_fields": list(
            PROCEDURAL_SKILL_LIFECYCLE_RESTORE_EXPECTED_CHANGED_FIELDS
        ),
    }
    restore_review_hash = _hash_json(review_material)
    blueprint = _restore_blueprint(
        record=record,
        restore_review_hash=restore_review_hash,
        before_record_hash=record_hash,
    )
    blueprint_hash = _hash_json(blueprint) if blueprint else ""

    registry = {entry.prefix: entry for entry in COMMAND_REGISTRY}
    checks = {
        "skill_id_present": bool(identifier),
        "skill_store_readable": not snapshot["error"],
        "skill_store_well_formed": snapshot["malformed_count"] == 0,
        "skill_record_unique": len(matching) == 1,
        "all_skill_ids_unique": bool(ids)
        and all(ids)
        and len(ids) == len(set(ids)),
        "archived_verified_state": audit_state == "archived_verified",
        "current_status_archived": record.get("status") == "archived",
        "archive_envelope_verified": archive_check.verified,
        "archive_envelope_bound_to_record": bool(
            archive_check.verified
            and archive_check.skill_id == identifier
            and isinstance(record.get("provenance"), dict)
            and archive.get("skill_provenance_id")
            == record["provenance"].get("id")
        ),
        "durable_provenance_current": provenance_status == "VERIFIED",
        "procedure_non_executable": record.get("executable") is False,
        "active_duplicate_absent": not active_duplicates,
        "store_hash_available": _is_sha256(store_hash),
        "record_hash_available": _is_sha256(record_hash),
        "restore_writer_installed": (
            PROCEDURAL_SKILL_LIFECYCLE_RESTORE_WRITER_INSTALLED
        ),
        "direct_status_guard_installed": (
            SKILL_LIFECYCLE_DIRECT_STATUS_GUARD_INSTALLED
        ),
        "payload_guard_installed": SKILL_LIFECYCLE_PAYLOAD_GUARD_INSTALLED,
        "registry_surfaces_read_only": all(
            registry.get(prefix) is not None
            and registry[prefix].read_only
            and registry[prefix].mutates == "none"
            for prefix in ("/skills lifecycle-status", "/skills lifecycle-inspect")
        ),
        "blueprint_bound": bool(blueprint and _is_sha256(blueprint_hash)),
    }
    messages = {
        "skill_id_present": "A skill id is required.",
        "skill_store_readable": "Skill Library is unreadable.",
        "skill_store_well_formed": "Skill Library contains malformed JSONL.",
        "skill_record_unique": "Restore review requires exactly one target skill record.",
        "all_skill_ids_unique": "Skill Library contains missing or duplicate ids.",
        "archived_verified_state": "Only an archived_verified skill may enter restore design review.",
        "current_status_archived": "Restore design requires current archived status.",
        "archive_envelope_verified": "The current archive envelope does not verify.",
        "archive_envelope_bound_to_record": "Archive evidence is not bound to the current skill and provenance.",
        "durable_provenance_current": "Current skill provenance is not VERIFIED.",
        "procedure_non_executable": "Restore design refuses executable skill records.",
        "active_duplicate_absent": "An active duplicate skill already exists.",
        "store_hash_available": "Current Skill Library SHA-256 is unavailable.",
        "record_hash_available": "Current skill record hash is unavailable.",
        "restore_writer_installed": "The separately gated durable restore writer is unavailable.",
        "direct_status_guard_installed": "Generic status mutation guard is unavailable.",
        "payload_guard_installed": "Lifecycle-managed payload/telemetry mutation guard is unavailable.",
        "registry_surfaces_read_only": "Restore design Registry surfaces are missing or mutating.",
        "blueprint_bound": "Restore metadata blueprint is absent or unhashed.",
    }
    issues = list(audit_issues)
    issues.extend(messages[name] for name, passed in checks.items() if not passed)
    warnings = [
        "Restore would reactivate availability only; it would not execute the skill or prove current procedure quality.",
        "The separate apply gate requires an exact token, atomic verification, receipt, and exact-byte rollback.",
        "Generic /skills restore <id> is not authorized; only the separate exact-token --durable gate may perform this transition.",
    ]
    ready = all(checks.values()) and not issues
    return ProceduralSkillLifecycleRestoreReadinessReport(
        status="READY FOR RESTORE DESIGN REVIEW" if ready else "NOT READY",
        skill_id=identifier,
        audit_state=audit_state,
        current_status=str(record.get("status") or "missing"),
        provenance_status=provenance_status,
        archive_metadata_id=archive_check.metadata_id,
        archive_metadata_hash=(
            str(archive.get("metadata_hash") or "")
            if isinstance(archive, dict)
            else ""
        ),
        skill_store_sha256=store_hash,
        skill_record_hash=record_hash,
        restore_review_hash=restore_review_hash,
        metadata_blueprint_hash=blueprint_hash,
        metadata_blueprint=blueprint,
        expected_changed_fields=list(
            PROCEDURAL_SKILL_LIFECYCLE_RESTORE_EXPECTED_CHANGED_FIELDS
        ),
        future_receipt_fields=list(
            PROCEDURAL_SKILL_LIFECYCLE_RESTORE_RECEIPT_FIELDS
        ),
        active_duplicate_skill_ids=active_duplicates,
        checks=checks,
        issues=_dedupe(issues),
        warnings=warnings,
        ready_for_design_review=ready,
        direct_status_guard_installed=(
            SKILL_LIFECYCLE_DIRECT_STATUS_GUARD_INSTALLED
        ),
        payload_guard_installed=SKILL_LIFECYCLE_PAYLOAD_GUARD_INSTALLED,
    )


def procedural_skill_lifecycle_restore_doctor(
) -> ProceduralSkillLifecycleRestoreDoctorReport:
    issues: list[str] = []
    warnings: list[str] = []
    try:
        example = _example_restore_metadata()
    except ValueError as exc:
        example = {}
        issues.append(f"Deterministic restore example failed: {exc}")
    check = verify_procedural_skill_lifecycle_restore_metadata(example)
    if not check.verified:
        issues.extend(check.issues)
    tampered = deepcopy(example)
    if tampered:
        tampered["prior_archive_hash"] = "0" * 64
    tamper_refused = not verify_procedural_skill_lifecycle_restore_metadata(
        tampered
    ).verified
    if not tamper_refused:
        issues.append("Restore archive-binding tamper fixture was not refused.")
    for fields, label in (
        (PROCEDURAL_SKILL_LIFECYCLE_RESTORE_FIELDS, "metadata"),
        (PROCEDURAL_SKILL_LIFECYCLE_RESTORE_RECEIPT_FIELDS, "receipt"),
    ):
        if len(fields) != len(set(fields)):
            issues.append(f"Restore {label} field contract contains duplicates.")
    if not PROCEDURAL_SKILL_LIFECYCLE_RESTORE_WRITER_INSTALLED:
        issues.append("The separately gated durable restore writer is unavailable.")
    if not SKILL_LIFECYCLE_DIRECT_STATUS_GUARD_INSTALLED:
        issues.append("Generic lifecycle status mutation guard is unavailable.")
    if not SKILL_LIFECYCLE_PAYLOAD_GUARD_INSTALLED:
        issues.append("Lifecycle-managed payload/telemetry mutation guard is unavailable.")
    registry = {entry.prefix: entry for entry in COMMAND_REGISTRY}
    registry_ok = all(
        registry.get(prefix) is not None
        and registry[prefix].read_only
        and registry[prefix].mutates == "none"
        for prefix in ("/skills lifecycle-status", "/skills lifecycle-inspect")
    )
    if not registry_ok:
        issues.append("Restore design Registry coverage is missing or unsafe.")
    if not issues:
        warnings.append(
            "Restore review is read-only; only the separate exact-token run-once apply gate may invoke the writer."
        )
    return ProceduralSkillLifecycleRestoreDoctorReport(
        status="ERROR" if issues else "OK",
        schema=PROCEDURAL_SKILL_LIFECYCLE_RESTORE_SCHEMA,
        field_count=len(PROCEDURAL_SKILL_LIFECYCLE_RESTORE_FIELDS),
        receipt_field_count=len(
            PROCEDURAL_SKILL_LIFECYCLE_RESTORE_RECEIPT_FIELDS
        ),
        deterministic_example_verified=check.verified,
        tamper_refused=tamper_refused,
        writer_installed=PROCEDURAL_SKILL_LIFECYCLE_RESTORE_WRITER_INSTALLED,
        direct_status_guard_installed=(
            SKILL_LIFECYCLE_DIRECT_STATUS_GUARD_INSTALLED
        ),
        payload_guard_installed=SKILL_LIFECYCLE_PAYLOAD_GUARD_INSTALLED,
        registry_coverage_ok=registry_ok,
        issues=_dedupe(issues),
        warnings=_dedupe(warnings),
    )


def format_procedural_skill_lifecycle_restore_command(
    command: str,
    *,
    skills_path: Path,
    persistent_memory_path: Path,
) -> str | None:
    raw = command.strip()
    normalized = " ".join(raw.lower().split())
    recognized = bool(
        normalized.startswith("/skills lifecycle-status ")
        and "--restore-contract" in normalized
        or normalized.startswith("/skills lifecycle-doctor ")
        and "--restore-contract" in normalized
        or normalized.startswith("/skills lifecycle-inspect ")
        and any(
            flag in normalized for flag in ("--restore-readiness", "--restore-plan")
        )
    )
    if not recognized:
        return None
    if any(marker in raw for marker in ("\n", ";", "&&", "||", "|")):
        return _restore_error(
            "Command chaining and multi-command input are not allowed."
        )
    if normalized == "/skills lifecycle-status --restore-contract":
        return format_procedural_skill_lifecycle_restore_contract()
    if normalized == "/skills lifecycle-doctor --restore-contract":
        return format_procedural_skill_lifecycle_restore_doctor(
            procedural_skill_lifecycle_restore_doctor()
        )
    if normalized.startswith((
        "/skills lifecycle-status ",
        "/skills lifecycle-doctor ",
    )):
        return (
            "Usage: /skills lifecycle-status --restore-contract | "
            "/skills lifecycle-doctor --restore-contract"
        )
    parts = raw.split()
    if len(parts) != 4:
        return _restore_usage()
    identifier = parts[2]
    flag = parts[3].lower()
    report = review_procedural_skill_lifecycle_restore(
        identifier,
        skills_path=skills_path,
        persistent_memory_path=persistent_memory_path,
    )
    if flag == "--restore-readiness":
        return format_procedural_skill_lifecycle_restore_readiness(report)
    if flag == "--restore-plan":
        return format_procedural_skill_lifecycle_restore_plan(report)
    return _restore_usage()


def format_procedural_skill_lifecycle_restore_contract() -> str:
    report = procedural_skill_lifecycle_restore_doctor()
    example = _example_restore_metadata()
    return "\n".join(
        [
            "Proto-Mind Durable Procedural Skill Lifecycle Restore Contract v1",
            f"Status: {report.status}",
            f"mode: {PROCEDURAL_SKILL_LIFECYCLE_RESTORE_MODE}",
            f"schema: {report.schema}",
            f"field_count: {report.field_count}",
            f"future_receipt_field_count: {report.receipt_field_count}",
            f"writer_installed: {str(report.writer_installed).lower()}",
            f"direct_status_guard_installed: {str(report.direct_status_guard_installed).lower()}",
            f"payload_guard_installed: {str(report.payload_guard_installed).lower()}",
            "transition: archived -> active",
            "meaning: operator-confirmed reactivation only; not procedure-quality proof",
            "prior_archive_retention: full verified archive envelope embedded",
            "expected_changed_fields: lifecycle, status, updated_at",
            f"example_id: {example['id']}",
            f"example_metadata_hash: {example['metadata_hash']}",
            "Required fields:",
            f"- {', '.join(PROCEDURAL_SKILL_LIFECYCLE_RESTORE_FIELDS)}",
            *_restore_boundary(),
        ]
    )


def format_procedural_skill_lifecycle_restore_readiness(
    report: ProceduralSkillLifecycleRestoreReadinessReport,
) -> str:
    lines = [
        "Proto-Mind Durable Procedural Skill Lifecycle Restore Readiness v1",
        f"Status: {report.status}",
        f"mode: {PROCEDURAL_SKILL_LIFECYCLE_RESTORE_MODE}",
        f"skill_id: {report.skill_id or 'missing'}",
        f"audit_state: {report.audit_state}",
        f"current_status: {report.current_status}",
        f"provenance_status: {report.provenance_status}",
        f"archive_metadata_id: {report.archive_metadata_id or 'unavailable'}",
        f"archive_metadata_hash: {report.archive_metadata_hash or 'unavailable'}",
        f"skill_store_sha256: {report.skill_store_sha256}",
        f"skill_record_hash: {report.skill_record_hash or 'unavailable'}",
        f"restore_review_hash: {report.restore_review_hash}",
        f"metadata_blueprint_hash: {report.metadata_blueprint_hash or 'unavailable'}",
        f"active_duplicates: {', '.join(report.active_duplicate_skill_ids) or 'none'}",
        f"writer_installed: {str(report.writer_installed).lower()}",
        f"direct_status_guard_installed: {str(report.direct_status_guard_installed).lower()}",
        f"payload_guard_installed: {str(report.payload_guard_installed).lower()}",
        "apply_token_generated: false",
        "mutation_performed: false",
        "Checks:",
    ]
    lines.extend(
        f"- {name}: {str(value).lower()}" for name, value in report.checks.items()
    )
    lines.extend(f"- BLOCKER: {issue}" for issue in report.issues)
    lines.extend(f"- WARN: {warning}" for warning in report.warnings)
    lines.extend(_restore_boundary())
    return "\n".join(lines)


def format_procedural_skill_lifecycle_restore_plan(
    report: ProceduralSkillLifecycleRestoreReadinessReport,
) -> str:
    lines = [
        "Proto-Mind Durable Procedural Skill Lifecycle Restore Plan v1",
        f"Status: {report.status}",
        f"skill_id: {report.skill_id or 'missing'}",
        "future_transition: archived -> active",
        "future_operation: replace the archive envelope with a restore envelope that embeds the complete prior archive envelope",
        f"current_writer_installed: {str(report.writer_installed).lower()}",
        "separate_confirmation_required: true",
        "expected_skill_record_mutations: 1",
        f"expected_changed_fields: {', '.join(report.expected_changed_fields)}",
        "payload_and_provenance_fields_must_remain_identical: true",
        "persistent_memory_must_remain_unchanged: true",
        "procedure_execution_performed: false",
        "post_write_verification_required: true",
        "rollback_on_any_failure: exact original Skill Library bytes",
        "successful_restore_rollback: manual review; any re-archive needs a separate durable transition contract",
        f"metadata_blueprint_hash: {report.metadata_blueprint_hash or 'unavailable'}",
        "Future receipt fields:",
    ]
    lines.extend(f"- {field}" for field in report.future_receipt_fields)
    lines.extend(f"- BLOCKER: {issue}" for issue in report.issues)
    lines.extend(f"- WARN: {warning}" for warning in report.warnings)
    lines.extend(_restore_boundary())
    return "\n".join(lines)


def format_procedural_skill_lifecycle_restore_doctor(
    report: ProceduralSkillLifecycleRestoreDoctorReport,
) -> str:
    lines = [
        "Proto-Mind Durable Procedural Skill Lifecycle Restore Doctor v1",
        f"Status: {report.status}",
        f"schema: {report.schema}",
        f"field_count: {report.field_count}",
        f"future_receipt_field_count: {report.receipt_field_count}",
        f"deterministic_example_verified: {str(report.deterministic_example_verified).lower()}",
        f"tamper_refused: {str(report.tamper_refused).lower()}",
        f"writer_installed: {str(report.writer_installed).lower()}",
        f"direct_status_guard_installed: {str(report.direct_status_guard_installed).lower()}",
        f"payload_guard_installed: {str(report.payload_guard_installed).lower()}",
        f"registry_coverage_ok: {str(report.registry_coverage_ok).lower()}",
        "apply_token_generated: false",
        "mutation_performed: false",
    ]
    lines.extend(f"- ERROR: {issue}" for issue in report.issues)
    lines.extend(f"- WARN: {warning}" for warning in report.warnings)
    lines.extend(_restore_boundary())
    return "\n".join(lines)


def _restore_blueprint(
    *,
    record: dict[str, Any],
    restore_review_hash: str,
    before_record_hash: str,
) -> dict[str, Any]:
    archive = record.get("lifecycle")
    provenance = record.get("provenance")
    archive_check = verify_procedural_skill_lifecycle_metadata(archive)
    if (
        not archive_check.verified
        or not isinstance(archive, dict)
        or not isinstance(provenance, dict)
    ):
        return {}
    return {
        "version": PROCEDURAL_SKILL_LIFECYCLE_RESTORE_VERSION,
        "schema": PROCEDURAL_SKILL_LIFECYCLE_RESTORE_SCHEMA,
        "skill_id": str(record.get("id") or ""),
        "skill_provenance_id": str(provenance.get("id") or ""),
        "transition": "restore",
        "reason": PROCEDURAL_SKILL_LIFECYCLE_RESTORE_REASON,
        "from_status": "archived",
        "to_status": "active",
        "prior_archive_id": archive_check.metadata_id,
        "prior_archive_hash": str(archive.get("metadata_hash") or ""),
        "prior_archive_envelope": deepcopy(archive),
        "restore_review_hash": restore_review_hash,
        "before_record_hash": before_record_hash,
        "confirmation_method": "exact_current_skill_lifecycle_restore_token",
        "evidence_retention": "embedded_verified_archive_envelope",
        "evidence_replay_available": False,
        "automatic": False,
        "procedure_execution_performed": False,
        "payload_mutation_performed": False,
        "dynamic_fields": list(PROCEDURAL_SKILL_LIFECYCLE_RESTORE_DYNAMIC_FIELDS),
        "expected_metadata_fields": list(
            PROCEDURAL_SKILL_LIFECYCLE_RESTORE_FIELDS
        ),
    }


def _active_duplicate_ids(
    target: dict[str, Any], records: list[dict[str, Any]]
) -> list[str]:
    if not target:
        return []
    values = {
        field: _normalize(str(target.get(field) or ""))
        for field in ("name", "summary", "body")
    }
    duplicates: list[str] = []
    for record in records:
        if record.get("id") == target.get("id") or record.get("status") != "active":
            continue
        if any(
            values[field]
            and _normalize(str(record.get(field) or "")) == values[field]
            for field in values
        ):
            duplicates.append(str(record.get("id") or "unknown"))
    return sorted(set(duplicates))


def _example_restore_metadata() -> dict[str, Any]:
    from proto_mind.skill_lifecycle_metadata import (
        build_procedural_skill_lifecycle_metadata_preview,
    )

    archive = build_procedural_skill_lifecycle_metadata_preview(
        skill_id="skill_example",
        skill_provenance_id="skillprov_example",
        transitioned_at="2026-07-20T00:00:00+00:00",
        decision_receipt_id="skilloutdec_example",
        decision_hash="1" * 64,
        outcome_status="FAILURE_CANDIDATE",
        selected_signal_id="evt_failure",
        evidence_event_ids=("evt_failure",),
        capture_receipt_hashes=("2" * 64,),
        review_hash="3" * 64,
        before_record_hash="4" * 64,
        confirmation_token_hash="5" * 64,
    )
    return build_procedural_skill_lifecycle_restore_metadata_preview(
        skill_id="skill_example",
        skill_provenance_id="skillprov_example",
        transitioned_at="2026-07-20T01:00:00+00:00",
        prior_archive_envelope=archive,
        restore_review_hash="6" * 64,
        before_record_hash="7" * 64,
        confirmation_token_hash="8" * 64,
    )


def _hash_file(path: Path) -> str:
    try:
        payload = path.read_bytes()
    except OSError:
        return "unavailable"
    return hashlib.sha256(payload).hexdigest()


def _hash_json(value: object) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _json_size(value: object) -> int:
    try:
        return len(
            json.dumps(
                value,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        )
    except (TypeError, ValueError):
        return PROCEDURAL_SKILL_LIFECYCLE_RESTORE_MAX_ARCHIVE_BYTES + 1


def _is_sha256(value: Any) -> bool:
    if not isinstance(value, str) or len(value) != 64:
        return False
    try:
        int(value, 16)
    except ValueError:
        return False
    return value == value.lower()


def _valid_timestamp(value: Any) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None


def _normalize(value: str) -> str:
    return " ".join(value.lower().split())


def _restore_usage() -> str:
    return (
        "Usage: /skills lifecycle-inspect <skill_id> "
        "--restore-readiness|--restore-plan"
    )


def _restore_error(message: str) -> str:
    return "\n".join(
        [
            "Proto-Mind Durable Procedural Skill Lifecycle Restore Error",
            "Status: ERROR",
            f"- {message}",
            *_restore_boundary(),
        ]
    )


def _restore_boundary() -> list[str]:
    return [
        "Boundary:",
        "- Restore review commands remain read-only; the v3.5s writer is reachable only through a separate exact-token run-once apply gate.",
        "- Any durable restore must preserve the complete verified archive envelope and exact skill provenance; reactivation is not procedure-quality proof.",
        "- Generic status, payload, tag, and usage mutations remain fail-closed for lifecycle-managed records and are never invoked here.",
        "- No skill, memory, event, queue, export, session log, Context Injection, shell, model/API, procedure, or external action changed.",
    ]


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))
