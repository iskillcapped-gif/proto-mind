from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any

from proto_mind.memory_store import MemoryStore
from proto_mind.models import MemoryRecord


MEMORY_LESSON_PROVENANCE_VERSION = 1
MEMORY_LESSON_PROVENANCE_SCHEMA = "memory.lesson.provenance.v1"
MEMORY_LESSON_TARGET_SCHEMA = "memory.lesson.v1"


@dataclass(frozen=True)
class MemoryProvenanceCheck:
    status: str
    memory_id: str
    provenance_id: str
    schema: str
    issues: list[str]
    warnings: list[str]
    verified: bool


def build_learning_lesson_provenance(
    *,
    memory_id: str,
    applied_at: str,
    proposal_id: str,
    proposal_hash: str,
    candidate_id: str,
    candidate_hash: str,
    decision_id: str,
    eligibility_receipt_id: str,
    selected_scope_hash: str,
    proposed_payload: dict[str, Any],
    evidence_event_ids: list[str],
    source_kinds: list[str],
) -> dict[str, Any]:
    material = {
        "version": MEMORY_LESSON_PROVENANCE_VERSION,
        "schema": MEMORY_LESSON_PROVENANCE_SCHEMA,
        "memory_id": memory_id,
        "applied_at": applied_at,
        "apply_id": f"learnapply_{proposal_hash[:16]}",
        "proposal_id": proposal_id,
        "proposal_hash": proposal_hash,
        "candidate_id": candidate_id,
        "candidate_hash": candidate_hash,
        "decision_id": decision_id,
        "eligibility_receipt_id": eligibility_receipt_id,
        "selected_scope_hash": selected_scope_hash,
        "target_schema": MEMORY_LESSON_TARGET_SCHEMA,
        "payload_hash": _hash_json(proposed_payload),
        "evidence_event_ids": list(evidence_event_ids),
        "source_kinds": list(source_kinds),
        "confirmation_method": "exact_apply_token",
        "operator_confirmation_recorded": True,
        "automatic_promotion": False,
        "persistence": "embedded_memory_record",
    }
    digest = _hash_json(material)
    return {
        "id": f"memprov_{digest[:16]}",
        **material,
        "provenance_hash": digest,
    }


def verify_memory_provenance(record: MemoryRecord) -> MemoryProvenanceCheck:
    provenance = record.provenance
    if provenance is None:
        return MemoryProvenanceCheck(
            status="UNAVAILABLE",
            memory_id=record.id,
            provenance_id="",
            schema="",
            issues=[],
            warnings=["This memory has no embedded durable learning provenance."],
            verified=False,
        )
    if not isinstance(provenance, dict):
        return MemoryProvenanceCheck(
            status="ERROR",
            memory_id=record.id,
            provenance_id="",
            schema="",
            issues=["Embedded provenance is not a JSON object."],
            warnings=[],
            verified=False,
        )

    provenance_id = str(provenance.get("id") or "")
    schema = str(provenance.get("schema") or "")
    issues: list[str] = []
    required = (
        "id",
        "version",
        "schema",
        "memory_id",
        "applied_at",
        "apply_id",
        "proposal_id",
        "proposal_hash",
        "candidate_id",
        "candidate_hash",
        "decision_id",
        "eligibility_receipt_id",
        "selected_scope_hash",
        "target_schema",
        "payload_hash",
        "evidence_event_ids",
        "source_kinds",
        "confirmation_method",
        "operator_confirmation_recorded",
        "automatic_promotion",
        "persistence",
        "provenance_hash",
    )
    missing = [field for field in required if field not in provenance]
    if missing:
        issues.append(f"Required provenance fields are missing: {', '.join(missing)}.")
    if provenance.get("version") != MEMORY_LESSON_PROVENANCE_VERSION:
        issues.append("Provenance version is not supported.")
    if schema != MEMORY_LESSON_PROVENANCE_SCHEMA:
        issues.append("Provenance schema is not memory.lesson.provenance.v1.")
    if provenance.get("memory_id") != record.id:
        issues.append("Provenance memory_id does not match the record id.")
    if provenance.get("target_schema") != MEMORY_LESSON_TARGET_SCHEMA:
        issues.append("Provenance target schema is not memory.lesson.v1.")
    if record.type != "lesson" or record.source != "experience_learning_proposal":
        issues.append("Record type/source does not match a supervised learning lesson.")
    if provenance.get("confirmation_method") != "exact_apply_token":
        issues.append("Provenance lacks the exact apply-token confirmation method.")
    if provenance.get("operator_confirmation_recorded") is not True:
        issues.append("Provenance lacks explicit operator confirmation.")
    if provenance.get("automatic_promotion") is not False:
        issues.append("Provenance incorrectly claims automatic promotion.")
    if provenance.get("persistence") != "embedded_memory_record":
        issues.append("Provenance persistence mode is invalid.")
    proposal_hash = str(provenance.get("proposal_hash") or "")
    if not _is_sha256(proposal_hash):
        issues.append("Proposal hash is invalid.")
    else:
        if provenance.get("proposal_id") != f"learnprop_{proposal_hash[:16]}":
            issues.append("Proposal id does not match the proposal hash.")
        if provenance.get("apply_id") != f"learnapply_{proposal_hash[:16]}":
            issues.append("Apply id does not match the proposal hash.")
    if not _is_sha256(provenance.get("candidate_hash")):
        issues.append("Candidate hash is invalid.")
    if not _is_sha256(provenance.get("selected_scope_hash")):
        issues.append("Selected-scope hash is invalid.")
    if not _is_sha256(provenance.get("payload_hash")):
        issues.append("Payload hash is invalid.")
    for field in ("candidate_id", "decision_id", "eligibility_receipt_id"):
        if not isinstance(provenance.get(field), str) or not provenance[field]:
            issues.append(f"{field} is missing or invalid.")
    evidence = provenance.get("evidence_event_ids")
    if not isinstance(evidence, list) or not evidence or not all(
        isinstance(item, str) and item for item in evidence
    ):
        issues.append("Evidence event ids are missing or invalid.")
    source_kinds = provenance.get("source_kinds")
    if not isinstance(source_kinds, list) or not source_kinds or not all(
        isinstance(item, str) and item for item in source_kinds
    ):
        issues.append("Source kinds are invalid.")

    expected_payload = {
        "schema": MEMORY_LESSON_TARGET_SCHEMA,
        "content": record.content,
        "type": record.type,
        "importance": record.importance,
        "source": record.source,
        "tags": list(record.tags),
        "confidence": record.confidence,
    }
    if provenance.get("payload_hash") != _hash_json(expected_payload):
        issues.append("Record fields no longer match the confirmed proposal payload hash.")

    provenance_hash = str(provenance.get("provenance_hash") or "")
    hash_material = {
        key: value
        for key, value in provenance.items()
        if key not in {"id", "provenance_hash"}
    }
    expected_hash = _hash_json(hash_material)
    if provenance_hash != expected_hash:
        issues.append("Provenance hash does not match its stored fields.")
    if provenance_id != f"memprov_{expected_hash[:16]}":
        issues.append("Provenance id does not match its deterministic hash.")

    return MemoryProvenanceCheck(
        status="ERROR" if issues else "VERIFIED",
        memory_id=record.id,
        provenance_id=provenance_id,
        schema=schema,
        issues=_dedupe(issues),
        warnings=[],
        verified=not issues,
    )


def format_memory_why(store: MemoryStore, memory_id: str) -> str:
    identifier = memory_id.strip()
    if not identifier:
        return "Usage: /memory why <id>"
    try:
        records = store.load_persistent_memory()
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        return "\n".join(
            [
                "Memory Provenance v1",
                "Status: ERROR",
                f"- Persistent memory is unreadable: {exc}",
                "- No file was changed.",
            ]
        )
    record = next((item for item in records if item.id == identifier), None)
    if record is None:
        return "\n".join(
            [
                "Memory Provenance v1",
                "Status: NOT FOUND",
                f"memory_id: {identifier}",
                "- No file was changed.",
            ]
        )

    check = verify_memory_provenance(record)
    lines = [
        "Memory Provenance v1",
        f"Status: {check.status}",
        f"memory_id: {record.id}",
        f"memory_type: {record.type}",
        f"source: {record.source}",
        f"active: {str(record.active).lower()}",
        f"content_preview: {_preview(record.content)}",
    ]
    if record.provenance is None:
        lines.extend(
            [
                "- This is an operator/legacy memory without embedded v3.4b learning provenance.",
                "- Proto-Mind will not invent a source chain for it.",
                "- No file was changed.",
            ]
        )
        return "\n".join(lines)

    provenance = record.provenance if isinstance(record.provenance, dict) else {}
    lines.extend(
        [
            f"provenance_id: {check.provenance_id or 'missing'}",
            f"provenance_schema: {check.schema or 'missing'}",
            f"provenance_hash: {provenance.get('provenance_hash') or 'missing'}",
            f"apply_id: {provenance.get('apply_id') or 'missing'}",
            f"applied_at: {provenance.get('applied_at') or 'missing'}",
            f"proposal_id: {provenance.get('proposal_id') or 'missing'}",
            f"proposal_hash: {provenance.get('proposal_hash') or 'missing'}",
            f"candidate_id: {provenance.get('candidate_id') or 'missing'}",
            f"decision_id: {provenance.get('decision_id') or 'missing'}",
            f"eligibility_receipt_id: {provenance.get('eligibility_receipt_id') or 'missing'}",
            f"selected_scope_hash: {provenance.get('selected_scope_hash') or 'missing'}",
            "evidence_event_ids: "
            + ", ".join(str(item) for item in provenance.get("evidence_event_ids", [])),
            "source_kinds: "
            + ", ".join(str(item) for item in provenance.get("source_kinds", [])),
            f"confirmation_method: {provenance.get('confirmation_method') or 'missing'}",
            "operator_confirmation_recorded: "
            + str(provenance.get("operator_confirmation_recorded") is True).lower(),
            "automatic_promotion: false",
        ]
    )
    lines.extend(f"- ERROR: {issue}" for issue in check.issues)
    if check.verified:
        lines.extend(
            [
                "Why this memory exists:",
                "- An operator accepted the candidate, reviewed selected-scope eligibility,",
                "  confirmed a fixed memory.lesson.v1 proposal, and supplied a separate exact apply token.",
                "- The compact source event ids are retained; full prompts and responses are not embedded.",
                "- Provenance is stored with the memory record and survives process restart.",
            ]
        )
    lines.append("- Read-only explanation; no file was changed.")
    return "\n".join(lines)


def count_durable_provenance(records: list[MemoryRecord]) -> int:
    return sum(1 for record in records if record.provenance is not None)


def durable_provenance_findings(
    records: list[MemoryRecord],
) -> list[tuple[str, str, list[str]]]:
    invalid: list[str] = []
    for record in records:
        if record.provenance is None:
            continue
        check = verify_memory_provenance(record)
        if not check.verified:
            invalid.append(f"{record.id}: {'; '.join(check.issues)}")
    if not invalid:
        return []
    return [("ERROR", "Invalid embedded memory provenance detected.", invalid)]


def _hash_json(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _is_sha256(value: object) -> bool:
    if not isinstance(value, str) or len(value) != 64:
        return False
    return all(character in "0123456789abcdef" for character in value)


def _preview(value: str, limit: int = 160) -> str:
    normalized = " ".join(value.split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 3] + "..."


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))
