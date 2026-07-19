from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from typing import Any

from proto_mind.experience_learning_skill_lifecycle_readiness import (
    ProceduralSkillLifecycleApplyReadiness,
    ProceduralSkillLifecycleReadinessReport,
)
from proto_mind.experience_learning_skill_outcome_decision import (
    ProceduralSkillOutcomeDecisionReceipt,
)
from proto_mind.skill_lifecycle_metadata import (
    PROCEDURAL_SKILL_LIFECYCLE_METADATA_FIELDS,
    PROCEDURAL_SKILL_LIFECYCLE_METADATA_MAX_EVIDENCE_IDS,
    PROCEDURAL_SKILL_LIFECYCLE_METADATA_REASON,
    PROCEDURAL_SKILL_LIFECYCLE_METADATA_SCHEMA,
    PROCEDURAL_SKILL_LIFECYCLE_METADATA_VERSION,
    PROCEDURAL_SKILL_LIFECYCLE_METADATA_WRITER_INSTALLED,
    procedural_skill_lifecycle_metadata_doctor,
)


PROCEDURAL_SKILL_LIFECYCLE_METADATA_READINESS_VERSION = 1
PROCEDURAL_SKILL_LIFECYCLE_METADATA_READINESS_MODE = (
    "read_only_current_archive_decision_to_exact_future_envelope_blueprint"
)
PROCEDURAL_SKILL_LIFECYCLE_METADATA_READINESS_WRITER_INSTALLED = False
PROCEDURAL_SKILL_LIFECYCLE_CURRENT_WRITER_SUPPORTS_METADATA = False
PROCEDURAL_SKILL_LIFECYCLE_METADATA_DYNAMIC_FIELDS = (
    "id",
    "transitioned_at",
    "confirmation_token_hash",
    "metadata_hash",
)
PROCEDURAL_SKILL_LIFECYCLE_METADATA_EXPECTED_CHANGED_FIELDS = (
    "lifecycle",
    "status",
    "updated_at",
)
PROCEDURAL_SKILL_LIFECYCLE_METADATA_FUTURE_RECEIPT_FIELDS = (
    "lifecycle_apply_id",
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
    "exact_record_mutations",
    "changed_fields",
    "confirmation_token_hash",
    "post_state_verified",
    "durable_provenance_preserved",
    "persistent_memory_unchanged",
    "rollback_performed",
    "rollback_suggestion",
    "receipt_hash",
)


@dataclass(frozen=True)
class ProceduralSkillLifecycleMetadataReadinessReport:
    status: str
    decision_receipt_id: str
    skill_id: str
    decision: str
    outcome_status: str
    provenance_id: str
    skill_store_sha256: str
    skill_record_hash: str
    metadata_schema: str
    metadata_blueprint_hash: str
    metadata_blueprint: dict[str, Any]
    expected_changed_fields: list[str]
    future_receipt_fields: list[str]
    checks: dict[str, bool]
    issues: list[str]
    warnings: list[str]
    ready_for_writer_design_review: bool
    metadata_required: bool
    future_writer_ready: bool = False
    writer_installed: bool = False
    current_writer_compatible: bool = False
    apply_token_generated: bool = False
    mutation_performed: bool = False
    procedure_execution_performed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ProceduralSkillLifecycleMetadataReadinessDoctorReport:
    status: str
    metadata_schema: str
    metadata_contract_status: str
    writer_installed: bool
    current_writer_compatible: bool
    expected_changed_fields: list[str]
    future_receipt_field_count: int
    issues: list[str]
    warnings: list[str]
    mutation_performed: bool = False


class ProceduralSkillLifecycleMetadataReadiness:
    """Builds a future archive-envelope plan without generating write authority."""

    def __init__(self, reviewer: ProceduralSkillLifecycleApplyReadiness) -> None:
        self.reviewer = reviewer

    def review(
        self,
        receipt: ProceduralSkillOutcomeDecisionReceipt,
    ) -> ProceduralSkillLifecycleMetadataReadinessReport:
        base = self.reviewer.review(receipt)
        snapshot = self.reviewer.skill_library.read_snapshot()
        matches = [
            record
            for record in snapshot["records"]
            if record.get("id") == receipt.skill_id
        ]
        skill = matches[0] if len(matches) == 1 else None
        provenance = skill.get("provenance") if isinstance(skill, dict) else None
        metadata_report = procedural_skill_lifecycle_metadata_doctor()
        metadata_required = receipt.decision == "archive"
        blueprint = _metadata_blueprint(receipt, base) if metadata_required else {}
        blueprint_hash = _hash_json(blueprint) if blueprint else ""

        if not metadata_required:
            checks = {
                "base_lifecycle_readiness_current": base.ready_for_design_review,
                "keep_is_byte_stable_noop": bool(
                    receipt.decision == "keep"
                    and base.contract.expected_skill_record_mutations == 0
                    and base.contract.future_target_status == "active"
                ),
                "metadata_contract_healthy": metadata_report.status == "OK",
                "future_writer_uninstalled": not (
                    PROCEDURAL_SKILL_LIFECYCLE_METADATA_READINESS_WRITER_INSTALLED
                    or PROCEDURAL_SKILL_LIFECYCLE_METADATA_WRITER_INSTALLED
                ),
                "current_writer_not_claimed_compatible": not (
                    PROCEDURAL_SKILL_LIFECYCLE_CURRENT_WRITER_SUPPORTS_METADATA
                ),
                "apply_token_not_generated": True,
                "mutation_not_performed": True,
            }
            messages = {
                "base_lifecycle_readiness_current": "Base v3.5i lifecycle readiness is not current.",
                "keep_is_byte_stable_noop": (
                    "Only a current keep no-op may bypass durable metadata; revise needs a separate replacement contract."
                ),
                "metadata_contract_healthy": "The v3.5l lifecycle metadata contract is unhealthy.",
                "future_writer_uninstalled": "A lifecycle metadata writer appeared before separate authorization.",
                "current_writer_not_claimed_compatible": "The v3.5j writer must not be treated as metadata-capable.",
                "apply_token_not_generated": "Readiness must never generate an apply token.",
                "mutation_not_performed": "Readiness must never mutate the Skill Library.",
            }
            issues = [messages[name] for name, passed in checks.items() if not passed]
            keep_clean = all(checks.values()) and not issues
            return ProceduralSkillLifecycleMetadataReadinessReport(
                status=(
                    "NO DURABLE METADATA REQUIRED"
                    if keep_clean
                    else "NOT READY"
                ),
                decision_receipt_id=receipt.id,
                skill_id=receipt.skill_id,
                decision=receipt.decision,
                outcome_status=receipt.outcome_status,
                provenance_id=receipt.provenance_id,
                skill_store_sha256=base.skill_store_sha256,
                skill_record_hash=base.skill_record_hash,
                metadata_schema=PROCEDURAL_SKILL_LIFECYCLE_METADATA_SCHEMA,
                metadata_blueprint_hash="",
                metadata_blueprint={},
                expected_changed_fields=[],
                future_receipt_fields=[],
                checks=checks,
                issues=_dedupe(issues),
                warnings=[
                    "Keep remains a byte-stable receipt-only no-op; no lifecycle envelope or Skill Library rewrite is required."
                ],
                ready_for_writer_design_review=False,
                metadata_required=False,
            )

        checks = {
            "base_lifecycle_readiness_current": base.ready_for_design_review,
            "archive_decision_selected": receipt.decision == "archive",
            "archive_outcome_supported": receipt.outcome_status
            in {"FAILURE_CANDIDATE", "MIXED_EVIDENCE"},
            "exact_active_skill_found": bool(
                skill is not None and skill.get("status") == "active"
            ),
            "existing_lifecycle_metadata_absent": bool(
                skill is not None and "lifecycle" not in skill
            ),
            "skill_provenance_matches": bool(
                isinstance(provenance, dict)
                and provenance.get("id") == receipt.provenance_id
            ),
            "skill_record_hash_matches": bool(
                skill is not None and _hash_json(skill) == base.skill_record_hash
            ),
            "metadata_contract_healthy": metadata_report.status == "OK",
            "metadata_schema_fixed": (
                blueprint.get("schema") == PROCEDURAL_SKILL_LIFECYCLE_METADATA_SCHEMA
                if blueprint
                else False
            ),
            "metadata_static_fields_complete": _blueprint_is_complete(blueprint),
            "evidence_ids_bounded": bool(
                receipt.evidence_event_ids
                and len(receipt.evidence_event_ids)
                <= PROCEDURAL_SKILL_LIFECYCLE_METADATA_MAX_EVIDENCE_IDS
            ),
            "capture_hashes_bounded": bool(
                receipt.capture_receipt_hashes
                and len(receipt.capture_receipt_hashes)
                <= PROCEDURAL_SKILL_LIFECYCLE_METADATA_MAX_EVIDENCE_IDS
                and all(_is_sha256(value) for value in receipt.capture_receipt_hashes)
            ),
            "future_writer_uninstalled": not (
                PROCEDURAL_SKILL_LIFECYCLE_METADATA_READINESS_WRITER_INSTALLED
                or PROCEDURAL_SKILL_LIFECYCLE_METADATA_WRITER_INSTALLED
            ),
            "current_writer_not_claimed_compatible": not (
                PROCEDURAL_SKILL_LIFECYCLE_CURRENT_WRITER_SUPPORTS_METADATA
            ),
            "apply_token_not_generated": True,
            "mutation_not_performed": True,
        }
        messages = {
            "base_lifecycle_readiness_current": "Base v3.5i lifecycle readiness is not current.",
            "archive_decision_selected": (
                "Durable metadata v1 applies only to archive; keep needs no envelope and revise needs a separate contract."
            ),
            "archive_outcome_supported": "Archive metadata requires failure or mixed outcome evidence.",
            "exact_active_skill_found": "The exact decided skill is missing or no longer active.",
            "existing_lifecycle_metadata_absent": "The skill already contains lifecycle metadata.",
            "skill_provenance_matches": "Current skill provenance differs from the terminal decision.",
            "skill_record_hash_matches": "Current skill record differs from the base readiness hash.",
            "metadata_contract_healthy": "The v3.5l lifecycle metadata contract is unhealthy.",
            "metadata_schema_fixed": "The future lifecycle metadata schema is not fixed.",
            "metadata_static_fields_complete": "The future lifecycle metadata blueprint is incomplete.",
            "evidence_ids_bounded": "Decision evidence ids exceed or miss the v3.5l bound.",
            "capture_hashes_bounded": "Capture receipt hashes exceed or violate the v3.5l bound.",
            "future_writer_uninstalled": "A lifecycle metadata writer appeared before separate authorization.",
            "current_writer_not_claimed_compatible": "The v3.5j writer must not be treated as metadata-capable.",
            "apply_token_not_generated": "Readiness must never generate an apply token.",
            "mutation_not_performed": "Readiness must never mutate the Skill Library.",
        }
        issues = [messages[name] for name, passed in checks.items() if not passed]
        warnings = [
            "The blueprint binds current decision evidence and skill bytes, but dynamic write-time fields remain absent.",
            "The current v3.5j writer changes only status/updated_at and cannot persist this envelope.",
            "A separate checkpointed writer, token, exact mutation verifier, and byte rollback remain mandatory.",
        ]
        ready = all(checks.values()) and not issues
        status = "READY FOR DURABLE WRITER DESIGN REVIEW" if ready else "NOT READY"
        return ProceduralSkillLifecycleMetadataReadinessReport(
            status=status,
            decision_receipt_id=receipt.id,
            skill_id=receipt.skill_id,
            decision=receipt.decision,
            outcome_status=receipt.outcome_status,
            provenance_id=receipt.provenance_id,
            skill_store_sha256=base.skill_store_sha256,
            skill_record_hash=base.skill_record_hash,
            metadata_schema=PROCEDURAL_SKILL_LIFECYCLE_METADATA_SCHEMA,
            metadata_blueprint_hash=blueprint_hash,
            metadata_blueprint=blueprint,
            expected_changed_fields=list(
                PROCEDURAL_SKILL_LIFECYCLE_METADATA_EXPECTED_CHANGED_FIELDS
            ),
            future_receipt_fields=list(
                PROCEDURAL_SKILL_LIFECYCLE_METADATA_FUTURE_RECEIPT_FIELDS
            ),
            checks=checks,
            issues=_dedupe(issues),
            warnings=_dedupe(warnings),
            ready_for_writer_design_review=ready,
            metadata_required=metadata_required,
        )


def procedural_skill_lifecycle_metadata_readiness_doctor(
) -> ProceduralSkillLifecycleMetadataReadinessDoctorReport:
    metadata_report = procedural_skill_lifecycle_metadata_doctor()
    issues: list[str] = []
    warnings: list[str] = []
    if metadata_report.status != "OK":
        issues.extend(metadata_report.issues)
    if PROCEDURAL_SKILL_LIFECYCLE_METADATA_READINESS_WRITER_INSTALLED:
        issues.append("Durable lifecycle metadata readiness writer must remain absent.")
    if PROCEDURAL_SKILL_LIFECYCLE_CURRENT_WRITER_SUPPORTS_METADATA:
        issues.append("The v3.5j writer must not be labeled metadata-capable.")
    if tuple(sorted(PROCEDURAL_SKILL_LIFECYCLE_METADATA_EXPECTED_CHANGED_FIELDS)) != (
        "lifecycle",
        "status",
        "updated_at",
    ):
        issues.append("Future metadata mutation field set expanded unexpectedly.")
    if len(PROCEDURAL_SKILL_LIFECYCLE_METADATA_FUTURE_RECEIPT_FIELDS) != len(
        set(PROCEDURAL_SKILL_LIFECYCLE_METADATA_FUTURE_RECEIPT_FIELDS)
    ):
        issues.append("Future metadata receipt fields contain duplicates.")
    if not issues:
        warnings.append(
            "Readiness validates a future writer contract only; no token or writer exists."
        )
    return ProceduralSkillLifecycleMetadataReadinessDoctorReport(
        status="ERROR" if issues else "OK",
        metadata_schema=PROCEDURAL_SKILL_LIFECYCLE_METADATA_SCHEMA,
        metadata_contract_status=metadata_report.status,
        writer_installed=PROCEDURAL_SKILL_LIFECYCLE_METADATA_READINESS_WRITER_INSTALLED,
        current_writer_compatible=(
            PROCEDURAL_SKILL_LIFECYCLE_CURRENT_WRITER_SUPPORTS_METADATA
        ),
        expected_changed_fields=list(
            PROCEDURAL_SKILL_LIFECYCLE_METADATA_EXPECTED_CHANGED_FIELDS
        ),
        future_receipt_field_count=len(
            PROCEDURAL_SKILL_LIFECYCLE_METADATA_FUTURE_RECEIPT_FIELDS
        ),
        issues=_dedupe(issues),
        warnings=_dedupe(warnings),
    )


def format_procedural_skill_lifecycle_metadata_readiness(
    report: ProceduralSkillLifecycleMetadataReadinessReport,
) -> str:
    lines = [
        "Proto-Mind Durable Procedural Skill Lifecycle Writer Readiness v1",
        f"Status: {report.status}",
        f"mode: {PROCEDURAL_SKILL_LIFECYCLE_METADATA_READINESS_MODE}",
        f"decision_receipt_id: {report.decision_receipt_id}",
        f"skill_id: {report.skill_id}",
        f"decision: {report.decision}",
        f"outcome_status: {report.outcome_status}",
        f"metadata_required: {str(report.metadata_required).lower()}",
        f"metadata_schema: {report.metadata_schema}",
        f"metadata_blueprint_hash: {report.metadata_blueprint_hash or 'not_applicable'}",
        f"skill_store_sha256: {report.skill_store_sha256}",
        f"skill_record_hash: {report.skill_record_hash}",
        f"writer_installed: {str(report.writer_installed).lower()}",
        f"current_writer_compatible: {str(report.current_writer_compatible).lower()}",
        "future_writer_ready: false",
        "apply_token_generated: false",
        "mutation_performed: false",
        "Checks:",
    ]
    lines.extend(f"- {name}: {str(value).lower()}" for name, value in report.checks.items())
    lines.extend(f"- BLOCKER: {issue}" for issue in report.issues)
    lines.extend(f"- WARN: {warning}" for warning in report.warnings)
    lines.extend(_boundary())
    return "\n".join(lines)


def format_procedural_skill_lifecycle_metadata_plan(
    report: ProceduralSkillLifecycleMetadataReadinessReport,
) -> str:
    if not report.metadata_required:
        return "\n".join(
            [
                "Proto-Mind Durable Procedural Skill Lifecycle Future Writer Plan v1",
                f"Status: {report.status}",
                f"decision_receipt_id: {report.decision_receipt_id}",
                f"skill_id: {report.skill_id}",
                f"decision: {report.decision}",
                "metadata_required: false",
                "expected_record_mutations: 0",
                "expected_changed_fields: none",
                "skill_library_bytes_must_remain_identical: true",
                "apply_token_generated: false",
                "mutation_performed: false",
                *[f"- BLOCKER: {issue}" for issue in report.issues],
                *_boundary(),
            ]
        )
    lines = [
        "Proto-Mind Durable Procedural Skill Lifecycle Future Writer Plan v1",
        f"Status: {report.status}",
        f"decision_receipt_id: {report.decision_receipt_id}",
        f"skill_id: {report.skill_id}",
        f"decision: {report.decision}",
        f"metadata_schema: {report.metadata_schema}",
        f"metadata_blueprint_hash: {report.metadata_blueprint_hash or 'not_applicable'}",
        "expected_record_mutations: 1",
        f"expected_changed_fields: {', '.join(report.expected_changed_fields)}",
        "atomic_write_required: true",
        "exact_previous_bytes_required: true",
        "post_write_metadata_verification_required: true",
        "durable_provenance_must_remain_identical: true",
        "persistent_memory_must_remain_unchanged: true",
        "rollback_on_any_failure: exact original Skill Library bytes",
        f"rollback_suggestion: /skills restore {report.skill_id}",
        "dynamic_write_time_fields:",
    ]
    lines.extend(
        f"- {field}" for field in PROCEDURAL_SKILL_LIFECYCLE_METADATA_DYNAMIC_FIELDS
    )
    lines.append("fixed_blueprint_fields:")
    for key, value in report.metadata_blueprint.items():
        lines.append(f"- {key}: {_compact(value)}")
    lines.append("required_future_receipt_fields:")
    lines.extend(f"- {field}" for field in report.future_receipt_fields)
    lines.extend(f"- BLOCKER: {issue}" for issue in report.issues)
    lines.extend(_boundary())
    return "\n".join(lines)


def format_procedural_skill_lifecycle_metadata_readiness_doctor() -> str:
    report = procedural_skill_lifecycle_metadata_readiness_doctor()
    lines = [
        "Proto-Mind Durable Procedural Skill Lifecycle Writer Readiness Doctor v1",
        f"Status: {report.status}",
        f"mode: {PROCEDURAL_SKILL_LIFECYCLE_METADATA_READINESS_MODE}",
        f"metadata_schema: {report.metadata_schema}",
        f"metadata_contract_status: {report.metadata_contract_status}",
        f"writer_installed: {str(report.writer_installed).lower()}",
        f"current_writer_compatible: {str(report.current_writer_compatible).lower()}",
        f"expected_changed_fields: {', '.join(report.expected_changed_fields)}",
        f"future_receipt_field_count: {report.future_receipt_field_count}",
        "apply_token_generated: false",
        "mutation_performed: false",
    ]
    lines.extend(f"- ERROR: {issue}" for issue in report.issues)
    lines.extend(f"- WARN: {warning}" for warning in report.warnings)
    lines.extend(_boundary())
    return "\n".join(lines)


def _metadata_blueprint(
    receipt: ProceduralSkillOutcomeDecisionReceipt,
    base: ProceduralSkillLifecycleReadinessReport,
) -> dict[str, Any]:
    return {
        "version": PROCEDURAL_SKILL_LIFECYCLE_METADATA_VERSION,
        "schema": PROCEDURAL_SKILL_LIFECYCLE_METADATA_SCHEMA,
        "skill_id": receipt.skill_id,
        "skill_provenance_id": receipt.provenance_id,
        "transition": "archive",
        "reason": PROCEDURAL_SKILL_LIFECYCLE_METADATA_REASON,
        "from_status": "active",
        "to_status": "archived",
        "decision_receipt_id": receipt.id,
        "decision_hash": receipt.decision_hash,
        "outcome_status": receipt.outcome_status,
        "selected_signal_id": receipt.selected_signal_id,
        "evidence_event_ids": sorted(receipt.evidence_event_ids),
        "capture_receipt_hashes": sorted(receipt.capture_receipt_hashes),
        "review_hash": receipt.review_hash,
        "before_record_hash": base.skill_record_hash,
        "confirmation_method": "exact_current_skill_lifecycle_readiness_token",
        "evidence_retention": "compact_ids_and_hashes_only",
        "evidence_replay_available": False,
        "automatic": False,
        "procedure_execution_performed": False,
        "dynamic_fields": list(PROCEDURAL_SKILL_LIFECYCLE_METADATA_DYNAMIC_FIELDS),
        "expected_metadata_fields": list(PROCEDURAL_SKILL_LIFECYCLE_METADATA_FIELDS),
    }


def _blueprint_is_complete(blueprint: dict[str, Any]) -> bool:
    if not blueprint:
        return False
    expected_static = set(PROCEDURAL_SKILL_LIFECYCLE_METADATA_FIELDS) - set(
        PROCEDURAL_SKILL_LIFECYCLE_METADATA_DYNAMIC_FIELDS
    )
    actual_static = set(blueprint) - {"dynamic_fields", "expected_metadata_fields"}
    return bool(
        expected_static == actual_static
        and blueprint.get("dynamic_fields")
        == list(PROCEDURAL_SKILL_LIFECYCLE_METADATA_DYNAMIC_FIELDS)
        and blueprint.get("expected_metadata_fields")
        == list(PROCEDURAL_SKILL_LIFECYCLE_METADATA_FIELDS)
    )


def _is_sha256(value: str) -> bool:
    if len(value) != 64:
        return False
    try:
        int(value, 16)
    except ValueError:
        return False
    return value == value.lower()


def _hash_json(value: object) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _compact(value: Any) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    if isinstance(value, bool):
        return str(value).lower()
    return str(value)


def _boundary() -> list[str]:
    return [
        "Boundary:",
        "- Readiness binds current evidence and bytes to a future envelope blueprint; it creates no token or authorization.",
        "- The current v3.5j writer is not metadata-capable and is never invoked by this layer.",
        "- No skill, memory, event, receipt, queue, export, session log, Context Injection, shell, model/API, or external action changed.",
    ]


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))
