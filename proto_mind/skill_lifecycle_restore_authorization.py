from __future__ import annotations

from dataclasses import asdict, dataclass
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
from proto_mind.skill_lifecycle_restore import (
    PROCEDURAL_SKILL_LIFECYCLE_RESTORE_EXPECTED_CHANGED_FIELDS,
    PROCEDURAL_SKILL_LIFECYCLE_RESTORE_RECEIPT_FIELDS,
    PROCEDURAL_SKILL_LIFECYCLE_RESTORE_SCHEMA,
    PROCEDURAL_SKILL_LIFECYCLE_RESTORE_WRITER_INSTALLED,
    procedural_skill_lifecycle_restore_doctor,
    review_procedural_skill_lifecycle_restore,
)


PROCEDURAL_SKILL_RESTORE_AUTHORIZATION_VERSION = 1
PROCEDURAL_SKILL_RESTORE_AUTHORIZATION_SCHEMA = (
    "skill.procedure.lifecycle.restore.authorization.v1"
)
PROCEDURAL_SKILL_RESTORE_AUTHORIZATION_MODE = (
    "read_only_exact_restore_authorization_readiness"
)
PROCEDURAL_SKILL_RESTORE_AUTHORIZATION_ENGINE_INSTALLED = False
PROCEDURAL_SKILL_RESTORE_TOKEN_GENERATOR_INSTALLED = False
PROCEDURAL_SKILL_RESTORE_RUN_ONCE_STATE_INSTALLED = False
PROCEDURAL_SKILL_RESTORE_MAX_SUCCESSFUL_APPLIES_PER_PROCESS = 1
PROCEDURAL_SKILL_RESTORE_CONFIRMATION_METHOD = (
    "exact_current_skill_lifecycle_restore_token"
)
PROCEDURAL_SKILL_RESTORE_CONFIRMATION_TEMPLATE = (
    "CONFIRM DURABLE SKILL RESTORE <skill_id> <authorization_blueprint_hash>"
)
PROCEDURAL_SKILL_RESTORE_RUN_ONCE_SCOPE = (
    "one_success_per_process_bound_to_current_record_and_store_hashes"
)
PROCEDURAL_SKILL_RESTORE_TOKEN_BINDING_FIELDS = (
    "skill_id",
    "restore_review_hash",
    "restore_metadata_blueprint_hash",
    "authorization_blueprint_hash",
    "before_store_sha256",
    "before_record_hash",
    "prior_archive_id",
    "prior_archive_hash",
)
PROCEDURAL_SKILL_RESTORE_AUTHORIZATION_BLUEPRINT_FIELDS = (
    "version",
    "schema",
    "skill_id",
    "restore_schema",
    "restore_review_hash",
    "restore_metadata_blueprint_hash",
    "before_store_sha256",
    "before_record_hash",
    "prior_archive_id",
    "prior_archive_hash",
    "from_status",
    "to_status",
    "confirmation_method",
    "confirmation_template",
    "token_binding_fields",
    "max_successful_applies_per_process",
    "run_once_scope",
    "expected_skill_record_mutations",
    "expected_changed_fields",
    "immutable_record_fields",
    "prior_archive_retention",
    "persistent_memory_unchanged",
    "post_write_verification_required",
    "exact_byte_rollback_required",
    "future_receipt_fields",
    "automatic",
    "procedure_execution_performed",
    "authorization_engine_installed",
    "token_generated",
    "writer_installed",
)


@dataclass(frozen=True)
class ProceduralSkillRestoreAuthorizationReadinessReport:
    status: str
    skill_id: str
    base_restore_status: str
    audit_state: str
    current_status: str
    skill_store_sha256: str
    skill_record_hash: str
    restore_review_hash: str
    restore_metadata_blueprint_hash: str
    authorization_blueprint_hash: str
    authorization_blueprint: dict[str, Any]
    checks: dict[str, bool]
    issues: list[str]
    warnings: list[str]
    ready_for_authorization_design_review: bool
    authorization_engine_installed: bool = False
    token_generator_installed: bool = False
    token_generated: bool = False
    run_once_state_installed: bool = False
    writer_installed: bool = False
    mutation_performed: bool = False
    procedure_execution_performed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ProceduralSkillRestoreAuthorizationDoctorReport:
    status: str
    schema: str
    blueprint_field_count: int
    future_receipt_field_count: int
    deterministic_example_verified: bool
    tamper_refused: bool
    restore_contract_healthy: bool
    direct_status_guard_installed: bool
    payload_guard_installed: bool
    registry_coverage_ok: bool
    issues: list[str]
    warnings: list[str]
    authorization_engine_installed: bool = False
    token_generator_installed: bool = False
    run_once_state_installed: bool = False
    writer_installed: bool = False
    mutation_performed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def review_procedural_skill_restore_authorization(
    skill_id: str,
    *,
    skills_path: Path,
    persistent_memory_path: Path,
) -> ProceduralSkillRestoreAuthorizationReadinessReport:
    identifier = skill_id.strip()
    base = review_procedural_skill_lifecycle_restore(
        identifier,
        skills_path=skills_path,
        persistent_memory_path=persistent_memory_path,
    )
    snapshot = SkillLibrary(skills_path).read_snapshot()
    matching = [
        record for record in snapshot["records"] if record.get("id") == identifier
    ]
    record = matching[0] if len(matching) == 1 else None
    blueprint = (
        _authorization_blueprint(base=base, record=record)
        if record is not None and base.metadata_blueprint
        else {}
    )
    blueprint_hash = _hash_json(blueprint) if blueprint else ""
    blueprint_issues = (
        _authorization_blueprint_issues(blueprint)
        if blueprint
        else [
            "Authorization blueprint is unavailable until the base restore review is ready."
        ]
    )
    registry = {entry.prefix: entry for entry in COMMAND_REGISTRY}

    checks = {
        "base_restore_design_ready": base.ready_for_design_review,
        "archived_verified_state": base.audit_state == "archived_verified",
        "current_status_archived": base.current_status == "archived",
        "restore_writer_absent": not PROCEDURAL_SKILL_LIFECYCLE_RESTORE_WRITER_INSTALLED,
        "direct_status_guard_installed": SKILL_LIFECYCLE_DIRECT_STATUS_GUARD_INSTALLED,
        "payload_guard_installed": SKILL_LIFECYCLE_PAYLOAD_GUARD_INSTALLED,
        "current_record_hash_bound": bool(
            record is not None
            and _hash_json(record) == base.skill_record_hash
            and _is_sha256(base.skill_record_hash)
        ),
        "current_store_hash_bound": _is_sha256(base.skill_store_sha256),
        "restore_blueprint_bound": bool(
            base.metadata_blueprint
            and _is_sha256(base.metadata_blueprint_hash)
            and _hash_json(base.metadata_blueprint) == base.metadata_blueprint_hash
        ),
        "authorization_blueprint_complete": bool(
            blueprint and not blueprint_issues and _is_sha256(blueprint_hash)
        ),
        "future_receipt_contract_fixed": bool(
            blueprint.get("future_receipt_fields")
            == list(PROCEDURAL_SKILL_LIFECYCLE_RESTORE_RECEIPT_FIELDS)
        ),
        "exact_confirmation_scope_fixed": bool(
            blueprint.get("confirmation_method")
            == PROCEDURAL_SKILL_RESTORE_CONFIRMATION_METHOD
            and blueprint.get("token_binding_fields")
            == list(PROCEDURAL_SKILL_RESTORE_TOKEN_BINDING_FIELDS)
        ),
        "authorization_engine_absent": not (
            PROCEDURAL_SKILL_RESTORE_AUTHORIZATION_ENGINE_INSTALLED
        ),
        "token_generator_absent": not (
            PROCEDURAL_SKILL_RESTORE_TOKEN_GENERATOR_INSTALLED
        ),
        "run_once_state_absent": not (
            PROCEDURAL_SKILL_RESTORE_RUN_ONCE_STATE_INSTALLED
        ),
        "registry_surfaces_read_only": all(
            registry.get(prefix) is not None
            and registry[prefix].read_only
            and registry[prefix].mutates == "none"
            for prefix in ("/skills lifecycle-status", "/skills lifecycle-inspect")
        ),
        "token_not_generated": True,
        "mutation_not_performed": True,
    }
    messages = {
        "base_restore_design_ready": "Base v3.5o restore design review is not current.",
        "archived_verified_state": "Authorization review requires archived_verified durable lifecycle state.",
        "current_status_archived": "Authorization review requires current archived status.",
        "restore_writer_absent": "Restore writer must remain absent through v3.5r.",
        "direct_status_guard_installed": "Generic lifecycle status guard is unavailable.",
        "payload_guard_installed": "Lifecycle payload/telemetry guard is unavailable.",
        "current_record_hash_bound": "Current target record is unavailable or differs from the restore review hash.",
        "current_store_hash_bound": "Current Skill Library hash is unavailable.",
        "restore_blueprint_bound": "Restore metadata blueprint is absent or not bound to its reported hash.",
        "authorization_blueprint_complete": "Authorization blueprint is incomplete or invalid.",
        "future_receipt_contract_fixed": "Future restore receipt fields are not fixed.",
        "exact_confirmation_scope_fixed": "Future exact-confirmation binding fields are not fixed.",
        "authorization_engine_absent": "Authorization engine must remain absent in v3.5r.",
        "token_generator_absent": "Restore token generator must remain absent in v3.5r.",
        "run_once_state_absent": "Restore run-once state must remain absent in v3.5r.",
        "registry_surfaces_read_only": "Restore authorization Registry surfaces are missing or mutating.",
        "token_not_generated": "Authorization readiness must never generate a token.",
        "mutation_not_performed": "Authorization readiness must never mutate the Skill Library.",
    }
    issues = list(base.issues)
    issues.extend(blueprint_issues)
    issues.extend(messages[name] for name, passed in checks.items() if not passed)
    ready = all(checks.values()) and not issues
    warnings = [
        "This is authorization design readiness only; no exact token can be generated or consumed.",
        "A future apply must revalidate every bound hash immediately before one atomic write.",
        "A successful restore would reactivate availability only and would not execute or re-prove the procedure.",
    ]
    return ProceduralSkillRestoreAuthorizationReadinessReport(
        status="READY FOR AUTHORIZATION DESIGN REVIEW" if ready else "NOT READY",
        skill_id=identifier,
        base_restore_status=base.status,
        audit_state=base.audit_state,
        current_status=base.current_status,
        skill_store_sha256=base.skill_store_sha256,
        skill_record_hash=base.skill_record_hash,
        restore_review_hash=base.restore_review_hash,
        restore_metadata_blueprint_hash=base.metadata_blueprint_hash,
        authorization_blueprint_hash=blueprint_hash,
        authorization_blueprint=blueprint,
        checks=checks,
        issues=_dedupe(issues),
        warnings=warnings,
        ready_for_authorization_design_review=ready,
    )


def procedural_skill_restore_authorization_doctor(
) -> ProceduralSkillRestoreAuthorizationDoctorReport:
    restore_doctor = procedural_skill_lifecycle_restore_doctor()
    example = _example_authorization_blueprint()
    example_issues = _authorization_blueprint_issues(example)
    tampered = dict(example)
    tampered["expected_changed_fields"] = ["status", "updated_at", "body"]
    tamper_refused = bool(_authorization_blueprint_issues(tampered))
    registry = {entry.prefix: entry for entry in COMMAND_REGISTRY}
    registry_ok = all(
        registry.get(prefix) is not None
        and registry[prefix].read_only
        and registry[prefix].mutates == "none"
        for prefix in (
            "/skills lifecycle-status",
            "/skills lifecycle-inspect",
            "/skills lifecycle-doctor",
        )
    )
    issues = list(example_issues)
    if len(PROCEDURAL_SKILL_RESTORE_AUTHORIZATION_BLUEPRINT_FIELDS) != len(
        set(PROCEDURAL_SKILL_RESTORE_AUTHORIZATION_BLUEPRINT_FIELDS)
    ):
        issues.append("Authorization blueprint field contract contains duplicates.")
    if len(PROCEDURAL_SKILL_LIFECYCLE_RESTORE_RECEIPT_FIELDS) != len(
        set(PROCEDURAL_SKILL_LIFECYCLE_RESTORE_RECEIPT_FIELDS)
    ):
        issues.append("Future restore receipt field contract contains duplicates.")
    if restore_doctor.status != "OK":
        issues.append("Base durable restore contract doctor is not OK.")
    if not tamper_refused:
        issues.append("Authorization blueprint tamper fixture was not refused.")
    if not SKILL_LIFECYCLE_DIRECT_STATUS_GUARD_INSTALLED:
        issues.append("Generic lifecycle status guard is unavailable.")
    if not SKILL_LIFECYCLE_PAYLOAD_GUARD_INSTALLED:
        issues.append("Lifecycle payload/telemetry guard is unavailable.")
    if PROCEDURAL_SKILL_RESTORE_AUTHORIZATION_ENGINE_INSTALLED:
        issues.append("Authorization engine must remain absent through v3.5r.")
    if PROCEDURAL_SKILL_RESTORE_TOKEN_GENERATOR_INSTALLED:
        issues.append("Restore token generator must remain absent through v3.5r.")
    if PROCEDURAL_SKILL_RESTORE_RUN_ONCE_STATE_INSTALLED:
        issues.append("Restore run-once state must remain absent through v3.5r.")
    if PROCEDURAL_SKILL_LIFECYCLE_RESTORE_WRITER_INSTALLED:
        issues.append("Restore writer must remain absent through v3.5r.")
    if not registry_ok:
        issues.append("Restore authorization Registry coverage is missing or unsafe.")
    warnings = [] if issues else [
        "Authorization is design-only; no token, state, writer, or restore authority exists."
    ]
    return ProceduralSkillRestoreAuthorizationDoctorReport(
        status="ERROR" if issues else "OK",
        schema=PROCEDURAL_SKILL_RESTORE_AUTHORIZATION_SCHEMA,
        blueprint_field_count=len(
            PROCEDURAL_SKILL_RESTORE_AUTHORIZATION_BLUEPRINT_FIELDS
        ),
        future_receipt_field_count=len(
            PROCEDURAL_SKILL_LIFECYCLE_RESTORE_RECEIPT_FIELDS
        ),
        deterministic_example_verified=not example_issues,
        tamper_refused=tamper_refused,
        restore_contract_healthy=restore_doctor.status == "OK",
        direct_status_guard_installed=(
            SKILL_LIFECYCLE_DIRECT_STATUS_GUARD_INSTALLED
        ),
        payload_guard_installed=SKILL_LIFECYCLE_PAYLOAD_GUARD_INSTALLED,
        registry_coverage_ok=registry_ok,
        issues=_dedupe(issues),
        warnings=warnings,
    )


def format_procedural_skill_restore_authorization_command(
    command: str,
    *,
    skills_path: Path,
    persistent_memory_path: Path,
) -> str | None:
    raw = command.strip()
    normalized = " ".join(raw.lower().split())
    recognized = bool(
        normalized.startswith("/skills lifecycle-status ")
        and "--restore-authorization-contract" in normalized
        or normalized.startswith("/skills lifecycle-doctor ")
        and "--restore-authorization" in normalized
        or normalized.startswith("/skills lifecycle-inspect ")
        and any(
            flag in normalized
            for flag in (
                "--restore-authorization",
                "--restore-authorization-plan",
            )
        )
    )
    if not recognized:
        return None
    if any(marker in raw for marker in ("\n", ";", "&&", "||", "|")):
        return _authorization_error(
            "Command chaining and multi-command input are not allowed."
        )
    if normalized == (
        "/skills lifecycle-status --restore-authorization-contract"
    ):
        return format_procedural_skill_restore_authorization_contract()
    if normalized == "/skills lifecycle-doctor --restore-authorization":
        return format_procedural_skill_restore_authorization_doctor(
            procedural_skill_restore_authorization_doctor()
        )
    if normalized.startswith((
        "/skills lifecycle-status ",
        "/skills lifecycle-doctor ",
    )):
        return _authorization_usage()
    parts = raw.split()
    if len(parts) != 4:
        return _authorization_usage()
    report = review_procedural_skill_restore_authorization(
        parts[2],
        skills_path=skills_path,
        persistent_memory_path=persistent_memory_path,
    )
    flag = parts[3].lower()
    if flag == "--restore-authorization":
        return format_procedural_skill_restore_authorization_readiness(report)
    if flag == "--restore-authorization-plan":
        return format_procedural_skill_restore_authorization_plan(report)
    return _authorization_usage()


def format_procedural_skill_restore_authorization_contract() -> str:
    report = procedural_skill_restore_authorization_doctor()
    example = _example_authorization_blueprint()
    return "\n".join(
        [
            "Proto-Mind Durable Skill Restore Authorization Contract v1",
            f"Status: {report.status}",
            f"mode: {PROCEDURAL_SKILL_RESTORE_AUTHORIZATION_MODE}",
            f"schema: {report.schema}",
            f"blueprint_field_count: {report.blueprint_field_count}",
            f"future_receipt_field_count: {report.future_receipt_field_count}",
            f"authorization_engine_installed: {str(report.authorization_engine_installed).lower()}",
            f"token_generator_installed: {str(report.token_generator_installed).lower()}",
            f"run_once_state_installed: {str(report.run_once_state_installed).lower()}",
            f"writer_installed: {str(report.writer_installed).lower()}",
            f"confirmation_template: {PROCEDURAL_SKILL_RESTORE_CONFIRMATION_TEMPLATE}",
            f"max_successful_applies_per_process: {PROCEDURAL_SKILL_RESTORE_MAX_SUCCESSFUL_APPLIES_PER_PROCESS}",
            f"example_blueprint_hash: {_hash_json(example)}",
            "Required blueprint fields:",
            f"- {', '.join(PROCEDURAL_SKILL_RESTORE_AUTHORIZATION_BLUEPRINT_FIELDS)}",
            *_authorization_boundary(),
        ]
    )


def format_procedural_skill_restore_authorization_readiness(
    report: ProceduralSkillRestoreAuthorizationReadinessReport,
) -> str:
    lines = [
        "Proto-Mind Durable Skill Restore Authorization Readiness v1",
        f"Status: {report.status}",
        f"mode: {PROCEDURAL_SKILL_RESTORE_AUTHORIZATION_MODE}",
        f"skill_id: {report.skill_id or 'missing'}",
        f"base_restore_status: {report.base_restore_status}",
        f"audit_state: {report.audit_state}",
        f"current_status: {report.current_status}",
        f"skill_store_sha256: {report.skill_store_sha256}",
        f"skill_record_hash: {report.skill_record_hash or 'unavailable'}",
        f"restore_review_hash: {report.restore_review_hash}",
        f"restore_metadata_blueprint_hash: {report.restore_metadata_blueprint_hash or 'unavailable'}",
        f"authorization_blueprint_hash: {report.authorization_blueprint_hash or 'unavailable'}",
        f"confirmation_template: {PROCEDURAL_SKILL_RESTORE_CONFIRMATION_TEMPLATE}",
        "exact_confirmation_required: true",
        f"authorization_engine_installed: {str(report.authorization_engine_installed).lower()}",
        f"token_generator_installed: {str(report.token_generator_installed).lower()}",
        "token_generated: false",
        f"run_once_state_installed: {str(report.run_once_state_installed).lower()}",
        f"writer_installed: {str(report.writer_installed).lower()}",
        "mutation_performed: false",
        "procedure_execution_performed: false",
        "Checks:",
    ]
    lines.extend(
        f"- {name}: {str(value).lower()}" for name, value in report.checks.items()
    )
    lines.extend(f"- BLOCKER: {issue}" for issue in report.issues)
    lines.extend(f"- WARN: {warning}" for warning in report.warnings)
    lines.extend(_authorization_boundary())
    return "\n".join(lines)


def format_procedural_skill_restore_authorization_plan(
    report: ProceduralSkillRestoreAuthorizationReadinessReport,
) -> str:
    blueprint = report.authorization_blueprint
    lines = [
        "Proto-Mind Durable Skill Restore Authorization Plan v1",
        f"Status: {report.status}",
        f"skill_id: {report.skill_id or 'missing'}",
        f"authorization_blueprint_hash: {report.authorization_blueprint_hash or 'unavailable'}",
        f"future_confirmation_template: {PROCEDURAL_SKILL_RESTORE_CONFIRMATION_TEMPLATE}",
        f"future_token_binding_fields: {', '.join(PROCEDURAL_SKILL_RESTORE_TOKEN_BINDING_FIELDS)}",
        f"future_run_once_scope: {PROCEDURAL_SKILL_RESTORE_RUN_ONCE_SCOPE}",
        f"future_max_successful_applies_per_process: {PROCEDURAL_SKILL_RESTORE_MAX_SUCCESSFUL_APPLIES_PER_PROCESS}",
        "future_expected_skill_record_mutations: 1",
        f"future_expected_changed_fields: {', '.join(PROCEDURAL_SKILL_LIFECYCLE_RESTORE_EXPECTED_CHANGED_FIELDS)}",
        f"future_immutable_record_fields: {', '.join(blueprint.get('immutable_record_fields') or []) or 'unavailable'}",
        "future_prior_archive_retention: embedded_verified_archive_envelope",
        "future_persistent_memory_unchanged: true",
        "future_post_write_verification_required: true",
        "future_exact_byte_rollback_required: true",
        "current_authorization_engine_installed: false",
        "current_token_generated: false",
        "current_run_once_state_installed: false",
        "current_writer_installed: false",
        "mutation_performed: false",
        "Future receipt fields:",
    ]
    lines.extend(
        f"- {field}" for field in PROCEDURAL_SKILL_LIFECYCLE_RESTORE_RECEIPT_FIELDS
    )
    lines.extend(f"- BLOCKER: {issue}" for issue in report.issues)
    lines.extend(f"- WARN: {warning}" for warning in report.warnings)
    lines.extend(_authorization_boundary())
    return "\n".join(lines)


def format_procedural_skill_restore_authorization_doctor(
    report: ProceduralSkillRestoreAuthorizationDoctorReport,
) -> str:
    lines = [
        "Proto-Mind Durable Skill Restore Authorization Doctor v1",
        f"Status: {report.status}",
        f"schema: {report.schema}",
        f"blueprint_field_count: {report.blueprint_field_count}",
        f"future_receipt_field_count: {report.future_receipt_field_count}",
        f"deterministic_example_verified: {str(report.deterministic_example_verified).lower()}",
        f"tamper_refused: {str(report.tamper_refused).lower()}",
        f"restore_contract_healthy: {str(report.restore_contract_healthy).lower()}",
        f"direct_status_guard_installed: {str(report.direct_status_guard_installed).lower()}",
        f"payload_guard_installed: {str(report.payload_guard_installed).lower()}",
        f"registry_coverage_ok: {str(report.registry_coverage_ok).lower()}",
        f"authorization_engine_installed: {str(report.authorization_engine_installed).lower()}",
        f"token_generator_installed: {str(report.token_generator_installed).lower()}",
        f"run_once_state_installed: {str(report.run_once_state_installed).lower()}",
        f"writer_installed: {str(report.writer_installed).lower()}",
        "mutation_performed: false",
    ]
    lines.extend(f"- ERROR: {issue}" for issue in report.issues)
    lines.extend(f"- WARN: {warning}" for warning in report.warnings)
    lines.extend(_authorization_boundary())
    return "\n".join(lines)


def _authorization_blueprint(*, base: Any, record: dict[str, Any]) -> dict[str, Any]:
    immutable_fields = sorted(
        set(record) - set(PROCEDURAL_SKILL_LIFECYCLE_RESTORE_EXPECTED_CHANGED_FIELDS)
    )
    return {
        "version": PROCEDURAL_SKILL_RESTORE_AUTHORIZATION_VERSION,
        "schema": PROCEDURAL_SKILL_RESTORE_AUTHORIZATION_SCHEMA,
        "skill_id": base.skill_id,
        "restore_schema": PROCEDURAL_SKILL_LIFECYCLE_RESTORE_SCHEMA,
        "restore_review_hash": base.restore_review_hash,
        "restore_metadata_blueprint_hash": base.metadata_blueprint_hash,
        "before_store_sha256": base.skill_store_sha256,
        "before_record_hash": base.skill_record_hash,
        "prior_archive_id": base.archive_metadata_id,
        "prior_archive_hash": base.archive_metadata_hash,
        "from_status": "archived",
        "to_status": "active",
        "confirmation_method": PROCEDURAL_SKILL_RESTORE_CONFIRMATION_METHOD,
        "confirmation_template": PROCEDURAL_SKILL_RESTORE_CONFIRMATION_TEMPLATE,
        "token_binding_fields": list(PROCEDURAL_SKILL_RESTORE_TOKEN_BINDING_FIELDS),
        "max_successful_applies_per_process": (
            PROCEDURAL_SKILL_RESTORE_MAX_SUCCESSFUL_APPLIES_PER_PROCESS
        ),
        "run_once_scope": PROCEDURAL_SKILL_RESTORE_RUN_ONCE_SCOPE,
        "expected_skill_record_mutations": 1,
        "expected_changed_fields": list(
            PROCEDURAL_SKILL_LIFECYCLE_RESTORE_EXPECTED_CHANGED_FIELDS
        ),
        "immutable_record_fields": immutable_fields,
        "prior_archive_retention": "embedded_verified_archive_envelope",
        "persistent_memory_unchanged": True,
        "post_write_verification_required": True,
        "exact_byte_rollback_required": True,
        "future_receipt_fields": list(
            PROCEDURAL_SKILL_LIFECYCLE_RESTORE_RECEIPT_FIELDS
        ),
        "automatic": False,
        "procedure_execution_performed": False,
        "authorization_engine_installed": False,
        "token_generated": False,
        "writer_installed": False,
    }


def _authorization_blueprint_issues(value: Any) -> list[str]:
    payload = dict(value) if isinstance(value, dict) else {}
    issues: list[str] = []
    if not isinstance(value, dict):
        issues.append("Authorization blueprint must be an object.")
    expected = set(PROCEDURAL_SKILL_RESTORE_AUTHORIZATION_BLUEPRINT_FIELDS)
    actual = set(payload)
    if expected - actual:
        issues.append("Authorization blueprint is missing required fields.")
    if actual - expected:
        issues.append("Authorization blueprint contains unexpected fields.")
    if payload.get("version") != PROCEDURAL_SKILL_RESTORE_AUTHORIZATION_VERSION:
        issues.append("Authorization blueprint version is unsupported.")
    if payload.get("schema") != PROCEDURAL_SKILL_RESTORE_AUTHORIZATION_SCHEMA:
        issues.append("Authorization blueprint schema is unsupported.")
    if payload.get("restore_schema") != PROCEDURAL_SKILL_LIFECYCLE_RESTORE_SCHEMA:
        issues.append("Authorization blueprint restore schema is unsupported.")
    if not str(payload.get("skill_id") or "").strip():
        issues.append("Authorization blueprint skill id is missing.")
    for field in (
        "restore_review_hash",
        "restore_metadata_blueprint_hash",
        "before_store_sha256",
        "before_record_hash",
        "prior_archive_hash",
    ):
        if not _is_sha256(payload.get(field)):
            issues.append(f"Authorization blueprint {field} must be SHA-256.")
    if not str(payload.get("prior_archive_id") or "").strip():
        issues.append("Authorization blueprint prior archive id is missing.")
    if payload.get("from_status") != "archived" or payload.get("to_status") != "active":
        issues.append("Authorization blueprint must describe archived -> active.")
    if payload.get("confirmation_method") != PROCEDURAL_SKILL_RESTORE_CONFIRMATION_METHOD:
        issues.append("Authorization blueprint confirmation method is invalid.")
    if payload.get("confirmation_template") != PROCEDURAL_SKILL_RESTORE_CONFIRMATION_TEMPLATE:
        issues.append("Authorization blueprint confirmation template is invalid.")
    if payload.get("token_binding_fields") != list(
        PROCEDURAL_SKILL_RESTORE_TOKEN_BINDING_FIELDS
    ):
        issues.append("Authorization blueprint token binding fields are invalid.")
    if payload.get("max_successful_applies_per_process") != 1:
        issues.append("Authorization blueprint must permit one future success per process.")
    if payload.get("run_once_scope") != PROCEDURAL_SKILL_RESTORE_RUN_ONCE_SCOPE:
        issues.append("Authorization blueprint run-once scope is invalid.")
    if payload.get("expected_skill_record_mutations") != 1:
        issues.append("Authorization blueprint must permit exactly one record mutation.")
    if payload.get("expected_changed_fields") != list(
        PROCEDURAL_SKILL_LIFECYCLE_RESTORE_EXPECTED_CHANGED_FIELDS
    ):
        issues.append("Authorization blueprint changed-field scope is invalid.")
    immutable = payload.get("immutable_record_fields")
    if (
        not isinstance(immutable, list)
        or not immutable
        or immutable != sorted(set(str(item) for item in immutable))
        or set(immutable) & set(PROCEDURAL_SKILL_LIFECYCLE_RESTORE_EXPECTED_CHANGED_FIELDS)
    ):
        issues.append("Authorization blueprint immutable field scope is invalid.")
    if payload.get("prior_archive_retention") != "embedded_verified_archive_envelope":
        issues.append("Authorization blueprint archive-retention scope is invalid.")
    if payload.get("future_receipt_fields") != list(
        PROCEDURAL_SKILL_LIFECYCLE_RESTORE_RECEIPT_FIELDS
    ):
        issues.append("Authorization blueprint future receipt fields are invalid.")
    for field in (
        "persistent_memory_unchanged",
        "post_write_verification_required",
        "exact_byte_rollback_required",
    ):
        if payload.get(field) is not True:
            issues.append(f"Authorization blueprint safety field {field} must be true.")
    for field in (
        "automatic",
        "procedure_execution_performed",
        "authorization_engine_installed",
        "token_generated",
        "writer_installed",
    ):
        if payload.get(field) is not False:
            issues.append(f"Authorization blueprint safety field {field} must be false.")
    return _dedupe(issues)


def _example_authorization_blueprint() -> dict[str, Any]:
    return {
        "version": PROCEDURAL_SKILL_RESTORE_AUTHORIZATION_VERSION,
        "schema": PROCEDURAL_SKILL_RESTORE_AUTHORIZATION_SCHEMA,
        "skill_id": "skill_example",
        "restore_schema": PROCEDURAL_SKILL_LIFECYCLE_RESTORE_SCHEMA,
        "restore_review_hash": "1" * 64,
        "restore_metadata_blueprint_hash": "2" * 64,
        "before_store_sha256": "3" * 64,
        "before_record_hash": "4" * 64,
        "prior_archive_id": "skilllife_example",
        "prior_archive_hash": "5" * 64,
        "from_status": "archived",
        "to_status": "active",
        "confirmation_method": PROCEDURAL_SKILL_RESTORE_CONFIRMATION_METHOD,
        "confirmation_template": PROCEDURAL_SKILL_RESTORE_CONFIRMATION_TEMPLATE,
        "token_binding_fields": list(PROCEDURAL_SKILL_RESTORE_TOKEN_BINDING_FIELDS),
        "max_successful_applies_per_process": 1,
        "run_once_scope": PROCEDURAL_SKILL_RESTORE_RUN_ONCE_SCOPE,
        "expected_skill_record_mutations": 1,
        "expected_changed_fields": list(
            PROCEDURAL_SKILL_LIFECYCLE_RESTORE_EXPECTED_CHANGED_FIELDS
        ),
        "immutable_record_fields": ["body", "id", "provenance", "summary"],
        "prior_archive_retention": "embedded_verified_archive_envelope",
        "persistent_memory_unchanged": True,
        "post_write_verification_required": True,
        "exact_byte_rollback_required": True,
        "future_receipt_fields": list(
            PROCEDURAL_SKILL_LIFECYCLE_RESTORE_RECEIPT_FIELDS
        ),
        "automatic": False,
        "procedure_execution_performed": False,
        "authorization_engine_installed": False,
        "token_generated": False,
        "writer_installed": False,
    }


def _authorization_usage() -> str:
    return "\n".join(
        [
            "Usage:",
            "  /skills lifecycle-status --restore-authorization-contract",
            "  /skills lifecycle-inspect <skill_id> --restore-authorization",
            "  /skills lifecycle-inspect <skill_id> --restore-authorization-plan",
            "  /skills lifecycle-doctor --restore-authorization",
        ]
    )


def _authorization_error(message: str) -> str:
    return "\n".join(
        [
            "Proto-Mind Durable Skill Restore Authorization Error",
            "Status: ERROR",
            f"- {message}",
            *_authorization_boundary(),
        ]
    )


def _authorization_boundary() -> list[str]:
    return [
        "Boundary:",
        "- v3.5r is read-only authorization design readiness; it generates no exact token and captures no approval.",
        "- Authorization engine, run-once state, restore writer, migration, repair, and procedure execution remain absent.",
        "- A future writer must revalidate all hashes, preserve immutable fields and prior archive evidence, verify one atomic three-field mutation, and roll back exact bytes on any failure.",
        "- No skill, memory, event, queue, export, session log, Context Injection, shell, model/API, or external action changed.",
    ]


def _hash_json(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _is_sha256(value: Any) -> bool:
    text = str(value or "")
    return len(text) == 64 and all(char in "0123456789abcdef" for char in text)


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))
