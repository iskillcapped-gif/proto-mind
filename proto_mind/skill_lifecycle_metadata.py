from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
import hashlib
import json
from typing import Any, Iterable


PROCEDURAL_SKILL_LIFECYCLE_METADATA_VERSION = 1
PROCEDURAL_SKILL_LIFECYCLE_METADATA_SCHEMA = "skill.procedure.lifecycle.v1"
PROCEDURAL_SKILL_LIFECYCLE_METADATA_MODE = (
    "hashed_archive_transition_contract_with_supervised_writer"
)
PROCEDURAL_SKILL_LIFECYCLE_METADATA_WRITER_INSTALLED = True
PROCEDURAL_SKILL_LIFECYCLE_METADATA_MAX_EVIDENCE_IDS = 16
PROCEDURAL_SKILL_LIFECYCLE_METADATA_TRANSITIONS = frozenset({"archive"})
PROCEDURAL_SKILL_LIFECYCLE_METADATA_REASON = (
    "verified_operator_reported_outcome_archive"
)
PROCEDURAL_SKILL_LIFECYCLE_METADATA_FIELDS = (
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
    "decision_receipt_id",
    "decision_hash",
    "outcome_status",
    "selected_signal_id",
    "evidence_event_ids",
    "capture_receipt_hashes",
    "review_hash",
    "before_record_hash",
    "confirmation_method",
    "confirmation_token_hash",
    "evidence_retention",
    "evidence_replay_available",
    "automatic",
    "procedure_execution_performed",
    "metadata_hash",
)
PROCEDURAL_SKILL_LIFECYCLE_METADATA_HASH_FIELDS = frozenset(
    {
        "decision_hash",
        "review_hash",
        "before_record_hash",
        "confirmation_token_hash",
    }
)


@dataclass(frozen=True)
class ProceduralSkillLifecycleMetadataCheck:
    status: str
    verified: bool
    metadata_id: str
    skill_id: str
    transition: str
    reason: str
    outcome_status: str
    evidence_event_count: int
    capture_receipt_hash_count: int
    hash_verified: bool
    identity_verified: bool
    operator_confirmation_fingerprinted: bool
    evidence_replay_available: bool
    issues: list[str]
    warnings: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ProceduralSkillLifecycleMetadataDoctorReport:
    status: str
    schema: str
    version: int
    field_count: int
    supported_transitions: list[str]
    writer_installed: bool
    deterministic_example_verified: bool
    tamper_refused: bool
    issues: list[str]
    warnings: list[str]
    mutation_performed: bool = False


def build_procedural_skill_lifecycle_metadata_preview(
    *,
    skill_id: str,
    skill_provenance_id: str,
    transitioned_at: str,
    decision_receipt_id: str,
    decision_hash: str,
    outcome_status: str,
    selected_signal_id: str,
    evidence_event_ids: Iterable[str],
    capture_receipt_hashes: Iterable[str],
    review_hash: str,
    before_record_hash: str,
    confirmation_token_hash: str,
) -> dict[str, Any]:
    """Build a detached future envelope; this function has no storage access."""

    material = {
        "version": PROCEDURAL_SKILL_LIFECYCLE_METADATA_VERSION,
        "schema": PROCEDURAL_SKILL_LIFECYCLE_METADATA_SCHEMA,
        "skill_id": skill_id.strip(),
        "skill_provenance_id": skill_provenance_id.strip(),
        "transition": "archive",
        "reason": PROCEDURAL_SKILL_LIFECYCLE_METADATA_REASON,
        "from_status": "active",
        "to_status": "archived",
        "transitioned_at": transitioned_at.strip(),
        "decision_receipt_id": decision_receipt_id.strip(),
        "decision_hash": decision_hash.strip().lower(),
        "outcome_status": outcome_status.strip(),
        "selected_signal_id": selected_signal_id.strip(),
        "evidence_event_ids": _normalized_values(evidence_event_ids),
        "capture_receipt_hashes": _normalized_hashes(capture_receipt_hashes),
        "review_hash": review_hash.strip().lower(),
        "before_record_hash": before_record_hash.strip().lower(),
        "confirmation_method": "exact_current_skill_lifecycle_readiness_token",
        "confirmation_token_hash": confirmation_token_hash.strip().lower(),
        "evidence_retention": "compact_ids_and_hashes_only",
        "evidence_replay_available": False,
        "automatic": False,
        "procedure_execution_performed": False,
    }
    identity_hash = _hash_json(material)
    payload = {
        **material,
        "id": f"skilllife_{identity_hash[:16]}",
    }
    payload["metadata_hash"] = _hash_json(payload)
    check = verify_procedural_skill_lifecycle_metadata(payload)
    if not check.verified:
        raise ValueError("; ".join(check.issues) or "Lifecycle metadata is invalid.")
    return payload


def verify_procedural_skill_lifecycle_metadata(
    value: Any,
) -> ProceduralSkillLifecycleMetadataCheck:
    issues: list[str] = []
    warnings: list[str] = []
    payload = dict(value) if isinstance(value, dict) else {}
    if not isinstance(value, dict):
        issues.append("Lifecycle metadata must be an object.")

    expected_fields = set(PROCEDURAL_SKILL_LIFECYCLE_METADATA_FIELDS)
    actual_fields = set(payload)
    missing = sorted(expected_fields - actual_fields)
    unexpected = sorted(actual_fields - expected_fields)
    if missing:
        issues.append(f"Missing lifecycle metadata fields: {', '.join(missing)}.")
    if unexpected:
        issues.append(f"Unexpected lifecycle metadata fields: {', '.join(unexpected)}.")
    if payload.get("version") != PROCEDURAL_SKILL_LIFECYCLE_METADATA_VERSION:
        issues.append("Lifecycle metadata version is unsupported.")
    if payload.get("schema") != PROCEDURAL_SKILL_LIFECYCLE_METADATA_SCHEMA:
        issues.append("Lifecycle metadata schema is unsupported.")
    if payload.get("transition") not in PROCEDURAL_SKILL_LIFECYCLE_METADATA_TRANSITIONS:
        issues.append("Only the archive transition is defined by the v1 contract.")
    if payload.get("reason") != PROCEDURAL_SKILL_LIFECYCLE_METADATA_REASON:
        issues.append("Lifecycle metadata reason is outside the v1 contract.")
    if payload.get("from_status") != "active" or payload.get("to_status") != "archived":
        issues.append("Lifecycle metadata must describe active -> archived.")
    if payload.get("outcome_status") not in {
        "FAILURE_CANDIDATE",
        "MIXED_EVIDENCE",
    }:
        issues.append("Archive metadata requires failure or mixed outcome evidence.")
    for field in (
        "skill_id",
        "skill_provenance_id",
        "decision_receipt_id",
        "selected_signal_id",
    ):
        if not isinstance(payload.get(field), str) or not str(payload.get(field)).strip():
            issues.append(f"Lifecycle metadata field {field} must be non-empty text.")
    if not _valid_timestamp(payload.get("transitioned_at")):
        issues.append("Lifecycle metadata transitioned_at must be timezone-aware ISO-8601.")
    for field in PROCEDURAL_SKILL_LIFECYCLE_METADATA_HASH_FIELDS:
        if not _is_sha256(payload.get(field)):
            issues.append(f"Lifecycle metadata field {field} must be SHA-256.")

    event_ids = payload.get("evidence_event_ids")
    capture_hashes = payload.get("capture_receipt_hashes")
    if not _bounded_sorted_unique_strings(event_ids, require_hashes=False):
        issues.append(
            "Evidence event ids must be a sorted unique non-empty bounded list."
        )
    if not _bounded_sorted_unique_strings(capture_hashes, require_hashes=True):
        issues.append(
            "Capture receipt hashes must be a sorted unique non-empty bounded SHA-256 list."
        )
    if payload.get("selected_signal_id") not in (
        event_ids if isinstance(event_ids, list) else []
    ):
        issues.append("Selected outcome signal must appear in evidence_event_ids.")
    if payload.get("confirmation_method") != (
        "exact_current_skill_lifecycle_readiness_token"
    ):
        issues.append("Lifecycle metadata lacks the exact confirmation method.")
    if payload.get("evidence_retention") != "compact_ids_and_hashes_only":
        issues.append("Lifecycle evidence-retention scope is invalid.")
    for field in (
        "evidence_replay_available",
        "automatic",
        "procedure_execution_performed",
    ):
        if payload.get(field) is not False:
            issues.append(f"Lifecycle metadata safety field {field} must be false.")

    material = {
        key: payload.get(key)
        for key in PROCEDURAL_SKILL_LIFECYCLE_METADATA_FIELDS
        if key not in {"id", "metadata_hash"}
    }
    expected_id = f"skilllife_{_hash_json(material)[:16]}"
    identity_verified = payload.get("id") == expected_id
    if not identity_verified:
        issues.append("Lifecycle metadata identity hash does not verify.")
    hash_material = {
        key: payload.get(key)
        for key in PROCEDURAL_SKILL_LIFECYCLE_METADATA_FIELDS
        if key != "metadata_hash"
    }
    expected_hash = _hash_json(hash_material)
    hash_verified = payload.get("metadata_hash") == expected_hash
    if not hash_verified:
        issues.append("Lifecycle metadata hash does not verify.")
    if payload and not issues:
        warnings.append(
            "Envelope integrity does not replay expired process evidence after restart."
        )

    return ProceduralSkillLifecycleMetadataCheck(
        status="ERROR" if issues else "VERIFIED",
        verified=not issues,
        metadata_id=str(payload.get("id") or ""),
        skill_id=str(payload.get("skill_id") or ""),
        transition=str(payload.get("transition") or ""),
        reason=str(payload.get("reason") or ""),
        outcome_status=str(payload.get("outcome_status") or ""),
        evidence_event_count=len(event_ids) if isinstance(event_ids, list) else 0,
        capture_receipt_hash_count=(
            len(capture_hashes) if isinstance(capture_hashes, list) else 0
        ),
        hash_verified=hash_verified,
        identity_verified=identity_verified,
        operator_confirmation_fingerprinted=_is_sha256(
            payload.get("confirmation_token_hash")
        ),
        evidence_replay_available=payload.get("evidence_replay_available") is True,
        issues=_dedupe(issues),
        warnings=_dedupe(warnings),
    )


def procedural_skill_lifecycle_metadata_doctor(
) -> ProceduralSkillLifecycleMetadataDoctorReport:
    issues: list[str] = []
    warnings: list[str] = []
    try:
        example = _example_metadata()
    except ValueError as exc:
        example: dict[str, Any] = {}
        issues.append(f"Deterministic lifecycle metadata example failed: {exc}")
    check = verify_procedural_skill_lifecycle_metadata(example)
    if not check.verified:
        issues.extend(check.issues)
    tampered = dict(example)
    tampered["reason"] = "invented_reason"
    tamper_refused = not verify_procedural_skill_lifecycle_metadata(tampered).verified
    if not tamper_refused:
        issues.append("Lifecycle metadata tamper fixture was not refused.")
    if len(PROCEDURAL_SKILL_LIFECYCLE_METADATA_FIELDS) != len(
        set(PROCEDURAL_SKILL_LIFECYCLE_METADATA_FIELDS)
    ):
        issues.append("Lifecycle metadata field contract contains duplicates.")
    if PROCEDURAL_SKILL_LIFECYCLE_METADATA_TRANSITIONS != {"archive"}:
        issues.append("Lifecycle metadata v1 transition scope expanded unexpectedly.")
    if not PROCEDURAL_SKILL_LIFECYCLE_METADATA_WRITER_INSTALLED:
        issues.append("Lifecycle metadata writer is unavailable after v3.5n activation.")
    if not issues:
        warnings.append(
            "The installed writer is archive-only, exact-token, run-once, and performs no migration."
        )
    return ProceduralSkillLifecycleMetadataDoctorReport(
        status="ERROR" if issues else "OK",
        schema=PROCEDURAL_SKILL_LIFECYCLE_METADATA_SCHEMA,
        version=PROCEDURAL_SKILL_LIFECYCLE_METADATA_VERSION,
        field_count=len(PROCEDURAL_SKILL_LIFECYCLE_METADATA_FIELDS),
        supported_transitions=sorted(
            PROCEDURAL_SKILL_LIFECYCLE_METADATA_TRANSITIONS
        ),
        writer_installed=PROCEDURAL_SKILL_LIFECYCLE_METADATA_WRITER_INSTALLED,
        deterministic_example_verified=check.verified,
        tamper_refused=tamper_refused,
        issues=_dedupe(issues),
        warnings=_dedupe(warnings),
    )


def format_procedural_skill_lifecycle_metadata_contract() -> str:
    report = procedural_skill_lifecycle_metadata_doctor()
    example = _example_metadata()
    lines = [
        "Proto-Mind Durable Procedural Skill Lifecycle Metadata Contract v1",
        f"Status: {report.status}",
        f"mode: {PROCEDURAL_SKILL_LIFECYCLE_METADATA_MODE}",
        f"schema: {report.schema}",
        f"version: {report.version}",
        f"field_count: {report.field_count}",
        f"supported_transitions: {', '.join(report.supported_transitions)}",
        f"writer_installed: {str(report.writer_installed).lower()}",
        "keep_behavior: byte-stable no-op; no durable lifecycle envelope",
        "archive_behavior: separately confirmed active -> archived envelope only",
        "restore_or_revision_behavior: outside v1; separate design required",
        "evidence_retention: compact ids and hashes only",
        "evidence_replay_after_restart: false",
        f"example_id: {example['id']}",
        f"example_metadata_hash: {example['metadata_hash']}",
        "Required fields:",
        f"- {', '.join(PROCEDURAL_SKILL_LIFECYCLE_METADATA_FIELDS)}",
        "Boundary:",
        "- This deterministic schema is used only by the separately confirmed v3.5n archive writer; no migration exists.",
        "- A self-valid envelope attests what the supervised writer recorded; it does not recreate expired process evidence.",
        "- Legacy archived skills remain ambiguous; no migration or lifecycle-envelope backfill exists.",
        "- No skill, memory, event, receipt, queue, export, session log, Context Injection, shell, model/API, or external action changed.",
    ]
    return "\n".join(lines)


def is_procedural_skill_lifecycle_metadata_design(value: Any) -> bool:
    return bool(
        isinstance(value, dict)
        and value.get("schema") == PROCEDURAL_SKILL_LIFECYCLE_METADATA_SCHEMA
        and value.get("version") == PROCEDURAL_SKILL_LIFECYCLE_METADATA_VERSION
    )


def _example_metadata() -> dict[str, Any]:
    return build_procedural_skill_lifecycle_metadata_preview(
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


def _normalized_values(values: Iterable[str]) -> list[str]:
    return sorted({str(value).strip() for value in values if str(value).strip()})


def _normalized_hashes(values: Iterable[str]) -> list[str]:
    return sorted(
        {str(value).strip().lower() for value in values if str(value).strip()}
    )


def _bounded_sorted_unique_strings(value: Any, *, require_hashes: bool) -> bool:
    if not isinstance(value, list) or not value:
        return False
    if len(value) > PROCEDURAL_SKILL_LIFECYCLE_METADATA_MAX_EVIDENCE_IDS:
        return False
    if value != sorted(set(value)):
        return False
    if any(not isinstance(item, str) or not item for item in value):
        return False
    return not require_hashes or all(_is_sha256(item) for item in value)


def _valid_timestamp(value: Any) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None


def _is_sha256(value: Any) -> bool:
    if not isinstance(value, str) or len(value) != 64:
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


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))
