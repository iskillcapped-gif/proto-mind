from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import shlex
from typing import Any

from proto_mind.command_registry import COMMAND_REGISTRY
from proto_mind.experience_ledger import compact_preview
from proto_mind.experience_learning_skill_outcome_capture import (
    PROCEDURAL_SKILL_OUTCOME_CAPTURE_MAX_EVIDENCE_CHARS,
    PROCEDURAL_SKILL_OUTCOMES,
)
from proto_mind.experience_learning_skill_restore_reevaluation import (
    PROCEDURAL_SKILL_POST_RESTORE_CAPTURE_WRITER_INSTALLED,
    PROCEDURAL_SKILL_RESTORE_REEVALUATION_REQUIRED_CALL_FIELDS,
)
from proto_mind.experience_learning_skill_runtime import (
    PROCEDURAL_SKILL_EXECUTION_INSTALLED,
)
from proto_mind.memory_store import MemoryStore
from proto_mind.skill_library import SkillLibrary
from proto_mind.skill_lifecycle_audit import (
    ProceduralSkillLifecycleAudit,
    ProceduralSkillLifecycleAuditError,
)
from proto_mind.skill_lifecycle_restore import (
    verify_procedural_skill_lifecycle_restore_metadata,
)
from proto_mind.skill_lifecycle_restore_receipt_audit import (
    build_procedural_skill_restore_receipt_evidence,
    verify_procedural_skill_restore_receipt_evidence,
)
from proto_mind.skill_provenance import verify_procedural_skill_provenance


PROCEDURAL_SKILL_RESTORE_CAPTURE_READINESS_VERSION = 1
PROCEDURAL_SKILL_RESTORE_CAPTURE_READINESS_SCHEMA = (
    "skill.outcome.capture.post_restore.readiness.v1"
)
PROCEDURAL_SKILL_RESTORE_CAPTURE_READINESS_MODE = (
    "read_only_exact_restore_bound_capture_authorization_design"
)
PROCEDURAL_SKILL_RESTORE_CAPTURE_EVENT_TYPES = (
    "goal_created",
    "plan_created",
    "tool_called",
    "tool_succeeded_or_failed",
)
PROCEDURAL_SKILL_RESTORE_CAPTURE_FUTURE_RECEIPT_FIELDS = (
    "id",
    "created_at",
    "schema",
    "session_id",
    "skill_id",
    "skill_provenance_id",
    "skill_provenance_hash",
    "target_payload_hash",
    "skill_store_sha256",
    "skill_record_hash",
    "restore_metadata_id",
    "restore_metadata_hash",
    "restore_evidence_id",
    "restore_evidence_hash",
    "restored_at",
    "outcome",
    "evidence_preview",
    "evidence_fingerprint",
    "evidence_input_chars",
    "blueprint_hash",
    "confirmation_method",
    "confirmation_token_hash",
    "event_ids",
    "receipt_hash",
    "operator_confirmation_recorded",
    "manual_operator_use",
    "post_restore_manual_use",
    "execution_performed_by_proto_mind",
    "process_memory_only",
    "restart_expiring",
    "persistence_performed",
    "skill_mutation_performed",
    "memory_mutation_performed",
    "session_log_mutation_performed",
)
PROCEDURAL_SKILL_RESTORE_CAPTURE_CONFIRMATION_PREFIX = (
    "CONFIRM-POST-RESTORE-SKILL-OUTCOME"
)
PROCEDURAL_SKILL_RESTORE_CAPTURE_TOKEN_GENERATOR_INSTALLED = False
PROCEDURAL_SKILL_RESTORE_CAPTURE_EVENT_APPEND_INSTALLED = False


@dataclass(frozen=True)
class ProceduralSkillRestoreCaptureReadinessReport:
    status: str
    schema: str
    session_id: str
    pilot_state: str
    skill_id: str
    skill_provenance_id: str
    skill_provenance_hash: str
    target_payload_hash: str
    skill_store_sha256: str
    skill_record_hash: str
    restore_metadata_id: str
    restore_metadata_hash: str
    restore_evidence_id: str
    restore_evidence_hash: str
    restored_at: str
    outcome: str
    evidence_preview: str
    evidence_fingerprint: str
    evidence_input_chars: int
    required_tool_called_fields: list[str]
    future_event_types: list[str]
    future_receipt_fields: list[str]
    confirmation_token_prefix: str
    blueprint_hash: str
    checks: dict[str, bool]
    issues: list[str]
    warnings: list[str]
    ready_for_authorization_design: bool
    session_consent_required: bool = True
    confirmation_token_generated: bool = False
    writer_installed: bool = False
    event_append_performed: bool = False
    persistence_performed: bool = False
    skill_mutation_performed: bool = False
    memory_mutation_performed: bool = False
    session_log_mutation_performed: bool = False
    procedure_execution_performed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ProceduralSkillRestoreCaptureReadinessDoctorReport:
    status: str
    schema: str
    pilot_state: str
    skill_count: int
    restored_skill_count: int
    active_restored_verified_count: int
    future_receipt_field_count: int
    required_call_field_count: int
    issues: list[str]
    warnings: list[str]
    writer_installed: bool = False
    token_generator_installed: bool = False
    event_append_installed: bool = False
    mutation_performed: bool = False
    procedure_execution_performed: bool = False


class ProceduralSkillRestoreCaptureReadinessError(RuntimeError):
    pass


class ProceduralSkillRestoreCaptureReadiness:
    """Builds a restore-bound future capture blueprint without write authority."""

    def __init__(self, *, memory_store: MemoryStore, skill_library: SkillLibrary) -> None:
        self.memory_store = memory_store
        self.skill_library = skill_library

    def review(
        self,
        *,
        session_id: str,
        pilot_state: str,
        skill_id: str,
        outcome: str,
        evidence: str,
    ) -> ProceduralSkillRestoreCaptureReadinessReport:
        normalized_session = session_id.strip()
        normalized_skill = skill_id.strip()
        normalized_outcome = outcome.strip().lower()
        normalized_evidence = " ".join(evidence.split())
        if not normalized_session:
            raise ProceduralSkillRestoreCaptureReadinessError(
                "Experience pilot session id is missing."
            )
        if not normalized_skill:
            raise ProceduralSkillRestoreCaptureReadinessError("Skill id is required.")
        if normalized_outcome not in PROCEDURAL_SKILL_OUTCOMES:
            raise ProceduralSkillRestoreCaptureReadinessError(
                "Outcome must be success or failure."
            )
        if not normalized_evidence:
            raise ProceduralSkillRestoreCaptureReadinessError(
                "Operator evidence must not be empty."
            )
        if len(normalized_evidence) > PROCEDURAL_SKILL_OUTCOME_CAPTURE_MAX_EVIDENCE_CHARS:
            raise ProceduralSkillRestoreCaptureReadinessError(
                "Operator evidence exceeds the bounded 800-character input limit."
            )

        memories = self._load_memories()
        skill = self._load_exact_skill(normalized_skill)
        provenance = skill.get("provenance")
        metadata = skill.get("lifecycle")
        if not isinstance(provenance, dict):
            raise ProceduralSkillRestoreCaptureReadinessError(
                "Durable skill provenance is unavailable."
            )
        if not isinstance(metadata, dict):
            raise ProceduralSkillRestoreCaptureReadinessError(
                "Skill has no durable restore envelope."
            )

        provenance_check = verify_procedural_skill_provenance(
            skill,
            memory_records=memories,
        )
        metadata_check = verify_procedural_skill_lifecycle_restore_metadata(metadata)
        try:
            lifecycle_entry = ProceduralSkillLifecycleAudit(
                skills_path=self.skill_library.skills_path,
                persistent_memory_path=self.memory_store.persistent_path,
            ).get(normalized_skill)
        except ProceduralSkillLifecycleAuditError as exc:
            raise ProceduralSkillRestoreCaptureReadinessError(str(exc)) from exc
        try:
            restore_evidence = build_procedural_skill_restore_receipt_evidence(skill)
        except ValueError as exc:
            raise ProceduralSkillRestoreCaptureReadinessError(str(exc)) from exc
        restore_evidence_check = verify_procedural_skill_restore_receipt_evidence(
            restore_evidence
        )

        skill_store_sha256 = _hash_file(self.skill_library.skills_path)
        skill_record_hash = _hash_json(skill)
        evidence_material = compact_preview(
            normalized_evidence,
            PROCEDURAL_SKILL_OUTCOME_CAPTURE_MAX_EVIDENCE_CHARS,
        )
        material = {
            "schema": PROCEDURAL_SKILL_RESTORE_CAPTURE_READINESS_SCHEMA,
            "session_id": normalized_session,
            "skill_id": normalized_skill,
            "skill_provenance_id": str(provenance.get("id") or ""),
            "skill_provenance_hash": str(provenance.get("provenance_hash") or ""),
            "target_payload_hash": str(provenance.get("target_payload_hash") or ""),
            "skill_store_sha256": skill_store_sha256,
            "skill_record_hash": skill_record_hash,
            "restore_metadata_id": str(metadata.get("id") or ""),
            "restore_metadata_hash": str(metadata.get("metadata_hash") or ""),
            "restore_evidence_id": str(restore_evidence.get("id") or ""),
            "restore_evidence_hash": str(restore_evidence.get("evidence_hash") or ""),
            "restored_at": str(metadata.get("transitioned_at") or ""),
            "outcome": normalized_outcome,
            "evidence_preview": compact_preview(evidence_material, 160),
            "evidence_fingerprint": hashlib.sha256(
                evidence_material.encode("utf-8")
            ).hexdigest(),
            "evidence_input_chars": len(normalized_evidence),
            "required_tool_called_fields": list(
                PROCEDURAL_SKILL_RESTORE_REEVALUATION_REQUIRED_CALL_FIELDS
            ),
            "future_event_types": list(PROCEDURAL_SKILL_RESTORE_CAPTURE_EVENT_TYPES),
            "future_receipt_fields": list(
                PROCEDURAL_SKILL_RESTORE_CAPTURE_FUTURE_RECEIPT_FIELDS
            ),
            "confirmation_token_prefix": (
                PROCEDURAL_SKILL_RESTORE_CAPTURE_CONFIRMATION_PREFIX
            ),
        }
        blueprint_hash = _hash_json(material)
        current_state = getattr(lifecycle_entry, "state", "")
        checks = {
            "session_consent_active": pilot_state == "consented",
            "skill_status_active": skill.get("status") == "active",
            "active_restored_verified": bool(
                current_state == "active_restored_verified"
                and getattr(lifecycle_entry, "restart_safe", False)
            ),
            "provenance_verified": bool(
                provenance_check.verified and provenance_check.current_payload_matches
            ),
            "restore_metadata_verified": metadata_check.verified,
            "restore_evidence_verified": restore_evidence_check.verified,
            "skill_store_hash_available": _is_sha256(skill_store_sha256),
            "skill_record_hash_available": _is_sha256(skill_record_hash),
            "required_call_fields_exact": tuple(material["required_tool_called_fields"])
            == PROCEDURAL_SKILL_RESTORE_REEVALUATION_REQUIRED_CALL_FIELDS,
            "future_event_batch_fixed": tuple(material["future_event_types"])
            == PROCEDURAL_SKILL_RESTORE_CAPTURE_EVENT_TYPES,
            "future_receipt_fields_unique": len(material["future_receipt_fields"])
            == len(set(material["future_receipt_fields"])),
            "confirmation_token_not_generated": not (
                PROCEDURAL_SKILL_RESTORE_CAPTURE_TOKEN_GENERATOR_INSTALLED
            ),
            "capture_writer_not_installed": not (
                PROCEDURAL_SKILL_POST_RESTORE_CAPTURE_WRITER_INSTALLED
            ),
            "event_append_not_installed": not (
                PROCEDURAL_SKILL_RESTORE_CAPTURE_EVENT_APPEND_INSTALLED
            ),
            "procedure_execution_disabled": not PROCEDURAL_SKILL_EXECUTION_INSTALLED,
        }
        messages = {
            "session_consent_active": (
                "Exact current-process Experience Pilot consent is not active."
            ),
            "skill_status_active": "The restored skill is not active.",
            "active_restored_verified": (
                "Current lifecycle audit is not active_restored_verified and restart-safe."
            ),
            "provenance_verified": (
                "Current durable skill provenance or payload does not verify."
            ),
            "restore_metadata_verified": "Durable restore metadata does not verify.",
            "restore_evidence_verified": "Reconstructed restore evidence does not verify.",
            "skill_store_hash_available": "Current Skill Library SHA-256 is unavailable.",
            "skill_record_hash_available": "Current skill record SHA-256 is unavailable.",
            "required_call_fields_exact": "Required restore-bound event fields drifted.",
            "future_event_batch_fixed": "Future four-event batch contract drifted.",
            "future_receipt_fields_unique": "Future receipt fields contain duplicates.",
            "confirmation_token_not_generated": (
                "Readiness must not generate a confirmation token."
            ),
            "capture_writer_not_installed": (
                "Post-restore capture writer must remain disabled in v1."
            ),
            "event_append_not_installed": (
                "Post-restore event append must remain disabled in v1."
            ),
            "procedure_execution_disabled": (
                "Procedural skill execution must remain disabled."
            ),
        }
        issues = [messages[name] for name, passed in checks.items() if not passed]
        if not provenance_check.verified or not provenance_check.current_payload_matches:
            issues.extend(provenance_check.issues)
            issues.extend(provenance_check.warnings)
        if not metadata_check.verified:
            issues.extend(metadata_check.issues)
        if not restore_evidence_check.verified:
            issues.extend(restore_evidence_check.issues)
        ready = all(checks.values()) and not issues
        return ProceduralSkillRestoreCaptureReadinessReport(
            status="READY FOR AUTHORIZATION DESIGN" if ready else "NOT READY",
            pilot_state=pilot_state,
            blueprint_hash=blueprint_hash,
            checks=checks,
            issues=_dedupe(issues),
            warnings=[
                "This blueprint defines future authority material only; it is not a confirmation token.",
                "A later separately reviewed writer must revalidate every bound hash immediately before append.",
            ],
            ready_for_authorization_design=ready,
            **material,
        )

    def current_state_matches(
        self,
        report: ProceduralSkillRestoreCaptureReadinessReport,
    ) -> tuple[bool, list[str]]:
        issues: list[str] = []
        snapshot = self.skill_library.read_snapshot()
        if snapshot["error"] or snapshot["malformed_count"]:
            return False, ["Skill Library is unreadable or malformed."]
        matches = [
            record
            for record in snapshot["records"]
            if record.get("id") == report.skill_id
        ]
        if len(matches) != 1:
            return False, ["Exact current skill record is unavailable."]
        record = matches[0]
        if _hash_file(self.skill_library.skills_path) != report.skill_store_sha256:
            issues.append("Skill Library bytes changed after readiness review.")
        if _hash_json(record) != report.skill_record_hash:
            issues.append("Skill record changed after readiness review.")
        try:
            evidence = build_procedural_skill_restore_receipt_evidence(record)
        except ValueError as exc:
            issues.append(str(exc))
        else:
            if evidence.get("evidence_hash") != report.restore_evidence_hash:
                issues.append("Restore receipt evidence changed after readiness review.")
        return not issues, _dedupe(issues)

    def doctor(
        self,
        *,
        pilot_state: str,
    ) -> ProceduralSkillRestoreCaptureReadinessDoctorReport:
        issues = _contract_issues()
        warnings: list[str] = []
        snapshot = self.skill_library.read_snapshot()
        if snapshot["error"]:
            issues.append(f"Skill Library is unreadable: {snapshot['error']}")
        if snapshot["malformed_count"]:
            issues.append(
                "Skill Library contains "
                f"{snapshot['malformed_count']} malformed JSONL record(s)."
            )
        records = list(snapshot["records"])
        restored = [record for record in records if isinstance(record.get("lifecycle"), dict)]
        active_verified = 0
        if not issues:
            try:
                audit = ProceduralSkillLifecycleAudit(
                    skills_path=self.skill_library.skills_path,
                    persistent_memory_path=self.memory_store.persistent_path,
                ).inspect()
            except ProceduralSkillLifecycleAuditError as exc:
                issues.append(str(exc))
            else:
                active_verified = sum(
                    entry.state == "active_restored_verified" and entry.restart_safe
                    for entry in audit.entries
                )
        if pilot_state != "consented":
            warnings.append(
                "Experience Pilot consent is not active; readiness previews remain NOT READY."
            )
        return ProceduralSkillRestoreCaptureReadinessDoctorReport(
            status="ERROR" if issues else "WARN" if warnings else "OK",
            schema=PROCEDURAL_SKILL_RESTORE_CAPTURE_READINESS_SCHEMA,
            pilot_state=pilot_state,
            skill_count=len(records),
            restored_skill_count=len(restored),
            active_restored_verified_count=active_verified,
            future_receipt_field_count=len(
                PROCEDURAL_SKILL_RESTORE_CAPTURE_FUTURE_RECEIPT_FIELDS
            ),
            required_call_field_count=len(
                PROCEDURAL_SKILL_RESTORE_REEVALUATION_REQUIRED_CALL_FIELDS
            ),
            issues=_dedupe(issues),
            warnings=_dedupe(warnings),
        )

    def _load_memories(self) -> list[Any]:
        try:
            return self.memory_store.load_persistent_memory()
        except (OSError, TypeError, ValueError) as exc:
            raise ProceduralSkillRestoreCaptureReadinessError(
                f"Persistent memory is unreadable: {exc}"
            ) from exc

    def _load_exact_skill(self, skill_id: str) -> dict[str, Any]:
        snapshot = self.skill_library.read_snapshot()
        if snapshot["error"]:
            raise ProceduralSkillRestoreCaptureReadinessError(
                f"Skill Library is unreadable: {snapshot['error']}"
            )
        if snapshot["malformed_count"]:
            raise ProceduralSkillRestoreCaptureReadinessError(
                "Skill Library contains malformed JSONL records."
            )
        matches = [record for record in snapshot["records"] if record.get("id") == skill_id]
        if not matches:
            raise ProceduralSkillRestoreCaptureReadinessError("Skill record was not found.")
        if len(matches) > 1:
            raise ProceduralSkillRestoreCaptureReadinessError(
                "Skill Library contains duplicate matching skill ids."
            )
        return dict(matches[0])


def verify_procedural_skill_restore_capture_blueprint(value: Any) -> tuple[bool, list[str]]:
    payload = dict(value) if isinstance(value, dict) else {}
    issues: list[str] = []
    expected_fields = set(ProceduralSkillRestoreCaptureReadinessReport.__dataclass_fields__)
    if set(payload) != expected_fields:
        missing = sorted(expected_fields - set(payload))
        unexpected = sorted(set(payload) - expected_fields)
        if missing:
            issues.append(f"Missing blueprint fields: {', '.join(missing)}.")
        if unexpected:
            issues.append(f"Unexpected blueprint fields: {', '.join(unexpected)}.")
    if payload.get("schema") != PROCEDURAL_SKILL_RESTORE_CAPTURE_READINESS_SCHEMA:
        issues.append("Post-restore capture readiness schema is unsupported.")
    for field in (
        "skill_provenance_hash",
        "target_payload_hash",
        "skill_store_sha256",
        "skill_record_hash",
        "restore_metadata_hash",
        "restore_evidence_hash",
        "evidence_fingerprint",
        "blueprint_hash",
    ):
        if not _is_sha256(payload.get(field)):
            issues.append(f"Blueprint field {field} must be SHA-256.")
    if tuple(payload.get("required_tool_called_fields") or ()) != (
        PROCEDURAL_SKILL_RESTORE_REEVALUATION_REQUIRED_CALL_FIELDS
    ):
        issues.append("Required restore-bound tool_called fields do not match the contract.")
    if tuple(payload.get("future_event_types") or ()) != (
        PROCEDURAL_SKILL_RESTORE_CAPTURE_EVENT_TYPES
    ):
        issues.append("Future event batch does not match the fixed contract.")
    if tuple(payload.get("future_receipt_fields") or ()) != (
        PROCEDURAL_SKILL_RESTORE_CAPTURE_FUTURE_RECEIPT_FIELDS
    ):
        issues.append("Future receipt fields do not match the fixed contract.")
    safety_expectations = {
        "session_consent_required": True,
        "confirmation_token_generated": False,
        "writer_installed": False,
        "event_append_performed": False,
        "persistence_performed": False,
        "skill_mutation_performed": False,
        "memory_mutation_performed": False,
        "session_log_mutation_performed": False,
        "procedure_execution_performed": False,
    }
    for field, expected in safety_expectations.items():
        if payload.get(field) is not expected:
            issues.append(f"Blueprint safety field {field} must be {str(expected).lower()}.")
    material_fields = (
        "schema",
        "session_id",
        "skill_id",
        "skill_provenance_id",
        "skill_provenance_hash",
        "target_payload_hash",
        "skill_store_sha256",
        "skill_record_hash",
        "restore_metadata_id",
        "restore_metadata_hash",
        "restore_evidence_id",
        "restore_evidence_hash",
        "restored_at",
        "outcome",
        "evidence_preview",
        "evidence_fingerprint",
        "evidence_input_chars",
        "required_tool_called_fields",
        "future_event_types",
        "future_receipt_fields",
        "confirmation_token_prefix",
    )
    expected_hash = _hash_json({field: payload.get(field) for field in material_fields})
    if payload.get("blueprint_hash") != expected_hash:
        issues.append("Post-restore capture blueprint hash does not verify.")
    return not issues, _dedupe(issues)


def format_procedural_skill_restore_capture_readiness_command(
    command: str,
    *,
    readiness: ProceduralSkillRestoreCaptureReadiness,
    pilot_state: str,
    pilot_session_id: str,
) -> str | None:
    raw = command.strip()
    normalized = " ".join(raw.lower().split())
    recognized = bool(
        normalized.startswith("/experience learning skill-outcome-capture-preview ")
        and any(
            flag in normalized
            for flag in ("--post-restore-readiness", "--post-restore-plan")
        )
        or normalized.startswith(
            "/experience learning skill-outcome-capture-doctor --post-restore"
        )
    )
    if not recognized:
        return None
    if len(raw) > 2_000:
        return _error("Command exceeds the bounded capture input limit.")
    if any(marker in raw for marker in ("\n", ";", "&&", "||", "|")):
        return _error("Command chaining and multi-command input are not allowed.")
    if normalized == "/experience learning skill-outcome-capture-doctor --post-restore-contract":
        return format_procedural_skill_restore_capture_contract()
    if normalized == "/experience learning skill-outcome-capture-doctor --post-restore":
        return format_procedural_skill_restore_capture_doctor(
            readiness.doctor(pilot_state=pilot_state)
        )
    try:
        tokens = shlex.split(_normalize_cli_quotes(raw))
    except ValueError as exc:
        return _error(f"Invalid quoted input: {exc}")
    try:
        request, mode = _parse_preview_tokens(tokens)
        report = readiness.review(
            session_id=pilot_session_id,
            pilot_state=pilot_state,
            **request,
        )
    except ProceduralSkillRestoreCaptureReadinessError as exc:
        return _error(str(exc))
    if mode == "--post-restore-plan":
        return format_procedural_skill_restore_capture_plan(report)
    return format_procedural_skill_restore_capture_readiness(report)


def format_procedural_skill_restore_capture_readiness(
    report: ProceduralSkillRestoreCaptureReadinessReport,
) -> str:
    lines = [
        "Proto-Mind Post-Restore Skill Outcome Capture Readiness v1",
        f"Status: {report.status}",
        f"mode: {PROCEDURAL_SKILL_RESTORE_CAPTURE_READINESS_MODE}",
        f"pilot_state: {report.pilot_state}",
        f"session_id: {report.session_id}",
        f"skill_id: {report.skill_id}",
        f"skill_provenance_id: {report.skill_provenance_id}",
        f"skill_provenance_hash: {report.skill_provenance_hash}",
        f"target_payload_hash: {report.target_payload_hash}",
        f"skill_store_sha256: {report.skill_store_sha256}",
        f"skill_record_hash: {report.skill_record_hash}",
        f"restore_metadata_id: {report.restore_metadata_id}",
        f"restore_metadata_hash: {report.restore_metadata_hash}",
        f"restore_evidence_id: {report.restore_evidence_id}",
        f"restore_evidence_hash: {report.restore_evidence_hash}",
        f"restored_at: {report.restored_at}",
        f"outcome: {report.outcome}",
        f"evidence_preview: {report.evidence_preview}",
        f"evidence_fingerprint: {report.evidence_fingerprint}",
        f"evidence_input_chars: {report.evidence_input_chars}",
        f"blueprint_hash: {report.blueprint_hash}",
        "session_consent_required: true",
        "confirmation_token_generated: false",
        "writer_installed: false",
        "event_append_performed: false",
        "capture_performed: false",
        "required_tool_called_fields: "
        + ", ".join(report.required_tool_called_fields),
        "Checks:",
    ]
    lines.extend(f"- {name}: {str(value).lower()}" for name, value in report.checks.items())
    lines.extend(f"- BLOCKER: {issue}" for issue in report.issues)
    lines.extend(f"- WARN: {warning}" for warning in report.warnings)
    lines.extend(_boundary())
    return "\n".join(lines)


def format_procedural_skill_restore_capture_plan(
    report: ProceduralSkillRestoreCaptureReadinessReport,
) -> str:
    lines = [
        "Proto-Mind Post-Restore Skill Outcome Future Capture Plan v1",
        f"Status: {report.status}",
        f"skill_id: {report.skill_id}",
        f"blueprint_hash: {report.blueprint_hash}",
        f"restore_evidence_hash: {report.restore_evidence_hash}",
        "Future exact sequence:",
        "1. Keep current-process Experience Pilot consent active.",
        "2. Revalidate current skill/store/provenance/restore hashes immediately before append.",
        "3. Generate one separate exact token from the unchanged blueprint in a later reviewed milestone.",
        "4. Append exactly goal_created, plan_created, tool_called, and one outcome event in process memory.",
        "5. Bind tool_called to every required restore field and execution_performed_by_proto_mind=false.",
        "6. Verify a bounded receipt before allowing post-restore outcome review.",
        f"future_confirmation_token_prefix: {report.confirmation_token_prefix}",
        "confirmation_token_generated: false",
        "writer_installed: false",
        "event_append_performed: false",
        "mutation_performed: false",
        "Future receipt fields:",
    ]
    lines.extend(f"- {field}" for field in report.future_receipt_fields)
    lines.extend(f"- BLOCKER: {issue}" for issue in report.issues)
    lines.extend(_boundary())
    return "\n".join(lines)


def format_procedural_skill_restore_capture_contract() -> str:
    return "\n".join(
        [
            "Proto-Mind Post-Restore Skill Outcome Capture Contract v1",
            "Status: DESIGN LOCKED",
            f"mode: {PROCEDURAL_SKILL_RESTORE_CAPTURE_READINESS_MODE}",
            f"schema: {PROCEDURAL_SKILL_RESTORE_CAPTURE_READINESS_SCHEMA}",
            "required_tool_called_fields: "
            + ", ".join(PROCEDURAL_SKILL_RESTORE_REEVALUATION_REQUIRED_CALL_FIELDS),
            "future_event_types: "
            + ", ".join(PROCEDURAL_SKILL_RESTORE_CAPTURE_EVENT_TYPES),
            f"future_receipt_fields: {len(PROCEDURAL_SKILL_RESTORE_CAPTURE_FUTURE_RECEIPT_FIELDS)}",
            "session_consent_required: true",
            "confirmation_token_generated: false",
            "post_restore_capture_writer_installed: false",
            "event_append_installed: false",
            "procedure_execution_enabled: false",
            *_boundary(),
        ]
    )


def format_procedural_skill_restore_capture_doctor(
    report: ProceduralSkillRestoreCaptureReadinessDoctorReport,
) -> str:
    lines = [
        "Proto-Mind Post-Restore Skill Outcome Capture Readiness Doctor v1",
        f"Status: {report.status}",
        f"mode: {PROCEDURAL_SKILL_RESTORE_CAPTURE_READINESS_MODE}",
        f"schema: {report.schema}",
        f"pilot_state: {report.pilot_state}",
        f"skills: {report.skill_count}",
        f"restored_skills: {report.restored_skill_count}",
        f"active_restored_verified: {report.active_restored_verified_count}",
        f"required_call_fields: {report.required_call_field_count}",
        f"future_receipt_fields: {report.future_receipt_field_count}",
        "post_restore_capture_writer_installed: false",
        "confirmation_token_generator_installed: false",
        "event_append_installed: false",
        "procedure_execution_enabled: false",
    ]
    lines.extend(f"- ERROR: {issue}" for issue in report.issues)
    lines.extend(f"- WARN: {warning}" for warning in report.warnings)
    if not report.issues and not report.warnings:
        lines.append(
            "- Registry, restore binding, blueprint, receipt, consent, and no-execution boundaries are healthy."
        )
    lines.extend(_boundary())
    return "\n".join(lines)


def _parse_preview_tokens(tokens: list[str]) -> tuple[dict[str, str], str]:
    flags = {"--post-restore-readiness", "--post-restore-plan"}
    if (
        len(tokens) < 8
        or tokens[5] != "--evidence"
        or tokens[-1].lower() not in flags
        or any(token.lower() in flags for token in tokens[6:-1])
    ):
        raise ProceduralSkillRestoreCaptureReadinessError(_usage())
    return (
        {
            "skill_id": tokens[3],
            "outcome": tokens[4],
            "evidence": " ".join(tokens[6:-1]),
        },
        tokens[-1].lower(),
    )


def _contract_issues() -> list[str]:
    issues: list[str] = []
    registry = {entry.prefix: entry for entry in COMMAND_REGISTRY}
    for prefix in (
        "/experience learning skill-outcome-capture-preview",
        "/experience learning skill-outcome-capture-doctor",
    ):
        spec = registry.get(prefix)
        if spec is None or not spec.read_only or spec.mutates != "none" or spec.risk != "low":
            issues.append(f"Registry metadata for {prefix} is missing or unsafe.")
    if PROCEDURAL_SKILL_POST_RESTORE_CAPTURE_WRITER_INSTALLED:
        issues.append("Post-restore capture writer must remain disabled in v1.")
    if PROCEDURAL_SKILL_RESTORE_CAPTURE_TOKEN_GENERATOR_INSTALLED:
        issues.append("Post-restore confirmation token generator must remain disabled in v1.")
    if PROCEDURAL_SKILL_RESTORE_CAPTURE_EVENT_APPEND_INSTALLED:
        issues.append("Post-restore event append must remain disabled in v1.")
    if PROCEDURAL_SKILL_EXECUTION_INSTALLED:
        issues.append("Procedural skill execution must remain disabled.")
    if len(PROCEDURAL_SKILL_RESTORE_CAPTURE_FUTURE_RECEIPT_FIELDS) != len(
        set(PROCEDURAL_SKILL_RESTORE_CAPTURE_FUTURE_RECEIPT_FIELDS)
    ):
        issues.append("Future post-restore receipt fields contain duplicates.")
    return issues


def _usage() -> str:
    return (
        "Usage: /experience learning skill-outcome-capture-preview "
        '<skill_id> <success|failure> --evidence "<operator evidence>" '
        "--post-restore-readiness|--post-restore-plan | "
        "skill-outcome-capture-doctor --post-restore|--post-restore-contract"
    )


def _error(message: str) -> str:
    return "\n".join(
        [
            "Proto-Mind Post-Restore Skill Outcome Capture Readiness Error",
            "Status: ERROR",
            f"- {message}",
            *_boundary(),
        ]
    )


def _boundary() -> list[str]:
    return [
        "Boundary:",
        "- Read-only design review of a future operator-reported post-restore outcome capture.",
        "- No confirmation token, writer, event append, receipt, skill execution, or automatic lifecycle conclusion exists.",
        "- No Experience event, skill, memory, queue, export, session log, Context Injection, shell, model/API, or external action changed.",
    ]


def _normalize_cli_quotes(value: str) -> str:
    return value.translate(str.maketrans({"“": '"', "”": '"', "‘": "'", "’": "'"}))


def _hash_file(path: Path) -> str:
    try:
        payload = path.read_bytes()
    except OSError:
        return "unavailable"
    return hashlib.sha256(payload).hexdigest()


def _hash_json(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
    ).hexdigest()


def _is_sha256(value: Any) -> bool:
    return bool(
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))
