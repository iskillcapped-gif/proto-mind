from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any

from proto_mind.experience_learning_skill_authoring import (
    ProceduralSkillAuthoringReceipt,
    procedural_skill_authoring_receipt_hash,
)
from proto_mind.memory_provenance import verify_memory_provenance
from proto_mind.models import MemoryRecord


PROCEDURAL_SKILL_PROVENANCE_VERSION = 1
PROCEDURAL_SKILL_PROVENANCE_SCHEMA = "skill.procedure.provenance.v1"
PROCEDURAL_SKILL_TARGET_SCHEMA = "skill.procedure.v1"


@dataclass(frozen=True)
class ProceduralSkillProvenanceCheck:
    status: str
    skill_id: str
    provenance_id: str
    source_lesson_id: str
    source_status: str
    current_payload_matches: bool
    issues: list[str]
    warnings: list[str]
    verified: bool


@dataclass(frozen=True)
class ProceduralSkillProvenanceDoctorReport:
    status: str
    total_skills: int
    provenanced_count: int
    verified_count: int
    historical_count: int
    drifted_count: int
    legacy_applied_count: int
    unavailable_count: int
    issues: list[str]
    warnings: list[str]


def build_procedural_skill_provenance(
    receipt: ProceduralSkillAuthoringReceipt,
    *,
    skill_id: str,
    applied_at: str,
    target_payload_hash: str,
    apply_confirmation_token_hash: str,
) -> dict[str, Any]:
    material = {
        "version": PROCEDURAL_SKILL_PROVENANCE_VERSION,
        "schema": PROCEDURAL_SKILL_PROVENANCE_SCHEMA,
        "skill_id": skill_id,
        "applied_at": applied_at,
        "target_schema": PROCEDURAL_SKILL_TARGET_SCHEMA,
        "source_lesson_id": receipt.source_lesson_id,
        "source_provenance_id": receipt.source_provenance_id,
        "source_apply_id": receipt.source_apply_id,
        "source_record_hash": receipt.source_record_hash,
        "base_contract_id": receipt.base_contract_id,
        "base_contract_hash": receipt.base_contract_hash,
        "contract_schema": receipt.contract_schema,
        "storage_schema": receipt.storage_schema,
        "authoring_receipt_id": receipt.id,
        "authoring_hash": receipt.authoring_hash,
        "authored_contract": receipt.authored_contract,
        "storage_projection": receipt.storage_projection,
        "target_payload_hash": target_payload_hash,
        "authoring_confirmation_method": receipt.confirmation_method,
        "authoring_confirmation_token_hash": receipt.confirmation_token_hash,
        "apply_confirmation_method": "exact_current_skill_readiness_token",
        "apply_confirmation_token_hash": apply_confirmation_token_hash,
        "operator_confirmation_recorded": True,
        "automatic_apply": False,
        "executable": False,
        "persistence": "embedded_skill_record",
    }
    digest = _hash_json(material)
    return {
        "id": f"skillprov_{digest[:16]}",
        **material,
        "provenance_hash": digest,
    }


def verify_procedural_skill_provenance(
    skill: dict[str, Any],
    *,
    memory_records: list[MemoryRecord] | None = None,
    memory_error: str = "",
    memory_exists: bool = True,
) -> ProceduralSkillProvenanceCheck:
    skill_id = str(skill.get("id") or "")
    provenance = skill.get("provenance")
    if provenance is None:
        warning = "This skill has no embedded durable procedural provenance."
        if skill.get("source") == "experience_learning_skill_apply":
            warning = "This is a legacy supervised-applied skill without v3.5e embedded provenance."
        return ProceduralSkillProvenanceCheck(
            status="UNAVAILABLE",
            skill_id=skill_id,
            provenance_id="",
            source_lesson_id=str(skill.get("source_lesson_id") or ""),
            source_status="unavailable",
            current_payload_matches=False,
            issues=[],
            warnings=[warning],
            verified=False,
        )
    if not isinstance(provenance, dict):
        return ProceduralSkillProvenanceCheck(
            status="ERROR",
            skill_id=skill_id,
            provenance_id="",
            source_lesson_id="",
            source_status="unavailable",
            current_payload_matches=False,
            issues=["Embedded skill provenance is not a JSON object."],
            warnings=[],
            verified=False,
        )

    issues: list[str] = []
    warnings: list[str] = []
    provenance_id = str(provenance.get("id") or "")
    source_lesson_id = str(provenance.get("source_lesson_id") or "")
    required = (
        "id",
        "version",
        "schema",
        "skill_id",
        "applied_at",
        "target_schema",
        "source_lesson_id",
        "source_provenance_id",
        "source_apply_id",
        "source_record_hash",
        "base_contract_id",
        "base_contract_hash",
        "contract_schema",
        "storage_schema",
        "authoring_receipt_id",
        "authoring_hash",
        "authored_contract",
        "storage_projection",
        "target_payload_hash",
        "authoring_confirmation_method",
        "authoring_confirmation_token_hash",
        "apply_confirmation_method",
        "apply_confirmation_token_hash",
        "operator_confirmation_recorded",
        "automatic_apply",
        "executable",
        "persistence",
        "provenance_hash",
    )
    missing = [field for field in required if field not in provenance]
    if missing:
        issues.append(f"Required provenance fields are missing: {', '.join(missing)}.")
    if provenance.get("version") != PROCEDURAL_SKILL_PROVENANCE_VERSION:
        issues.append("Skill provenance version is not supported.")
    if provenance.get("schema") != PROCEDURAL_SKILL_PROVENANCE_SCHEMA:
        issues.append("Skill provenance schema is not skill.procedure.provenance.v1.")
    if provenance.get("skill_id") != skill_id:
        issues.append("Provenance skill_id does not match the skill record id.")
    if provenance.get("target_schema") != PROCEDURAL_SKILL_TARGET_SCHEMA:
        issues.append("Provenance target schema is not skill.procedure.v1.")
    if skill.get("schema") != PROCEDURAL_SKILL_TARGET_SCHEMA:
        issues.append("Skill record schema is not skill.procedure.v1.")
    if skill.get("source") != "experience_learning_skill_apply":
        issues.append("Skill source does not match the supervised apply path.")
    if skill.get("executable") is not False or provenance.get("executable") is not False:
        issues.append("Procedural skill or provenance incorrectly claims executable capability.")
    if provenance.get("operator_confirmation_recorded") is not True:
        issues.append("Provenance lacks explicit operator confirmation.")
    if provenance.get("automatic_apply") is not False:
        issues.append("Provenance incorrectly claims automatic apply.")
    if provenance.get("persistence") != "embedded_skill_record":
        issues.append("Skill provenance persistence mode is invalid.")
    if provenance.get("apply_confirmation_method") != "exact_current_skill_readiness_token":
        issues.append("Provenance lacks the exact skill-apply confirmation method.")
    if provenance.get("authoring_confirmation_method") != "exact_source_and_authored_contract_token":
        issues.append("Provenance lacks the exact authoring confirmation method.")

    for field in (
        "source_record_hash",
        "base_contract_hash",
        "authoring_hash",
        "target_payload_hash",
        "authoring_confirmation_token_hash",
        "apply_confirmation_token_hash",
        "provenance_hash",
    ):
        if not _is_sha256(provenance.get(field)):
            issues.append(f"{field} is not a valid SHA-256 value.")

    authoring_hash = str(provenance.get("authoring_hash") or "")
    if provenance.get("authoring_receipt_id") != f"skillauth_{authoring_hash[:16]}":
        issues.append("Authoring receipt id does not match the authoring hash.")
    if skill_id != f"skilllearn_{authoring_hash[:16]}":
        issues.append("Skill id does not match the authoring hash.")
    base_hash = str(provenance.get("base_contract_hash") or "")
    if provenance.get("base_contract_id") != f"skillcontract_{base_hash[:16]}":
        issues.append("Base contract id does not match the base contract hash.")

    authoring_material = {
        field: provenance.get(field)
        for field in (
            "source_lesson_id",
            "source_provenance_id",
            "source_apply_id",
            "source_record_hash",
            "base_contract_id",
            "base_contract_hash",
            "contract_schema",
            "storage_schema",
            "authored_contract",
            "storage_projection",
        )
    }
    if authoring_hash != procedural_skill_authoring_receipt_hash(authoring_material):
        issues.append("Embedded authoring material does not match the authoring hash.")

    projection = provenance.get("storage_projection")
    projection_hash = _hash_json(projection)
    if provenance.get("target_payload_hash") != projection_hash:
        issues.append("Embedded storage projection does not match the target payload hash.")
    flat_pairs = {
        "source_lesson_id": "source_lesson_id",
        "source_provenance_id": "source_provenance_id",
        "source_record_hash": "source_record_hash",
        "authoring_receipt_id": "authoring_receipt_id",
        "authoring_hash": "authoring_hash",
        "target_payload_hash": "target_payload_hash",
    }
    for record_field, provenance_field in flat_pairs.items():
        if skill.get(record_field) != provenance.get(provenance_field):
            issues.append(f"Skill {record_field} does not match embedded provenance.")

    current_payload_matches = _current_payload_matches(skill, projection)
    if not current_payload_matches:
        warnings.append("Current skill fields differ from the operator-confirmed storage projection.")

    hash_material = {
        key: value
        for key, value in provenance.items()
        if key not in {"id", "provenance_hash"}
    }
    expected_hash = _hash_json(hash_material)
    if provenance.get("provenance_hash") != expected_hash:
        issues.append("Skill provenance hash does not match its stored fields.")
    if provenance_id != f"skillprov_{expected_hash[:16]}":
        issues.append("Skill provenance id does not match its deterministic hash.")

    source_status = "unavailable"
    if memory_error:
        issues.append(f"Persistent memory is unreadable: {memory_error}")
    elif not memory_exists:
        warnings.append("Persistent memory file is missing; source lesson cannot be revalidated.")
        source_status = "missing"
    elif memory_records is not None:
        matches = [record for record in memory_records if record.id == source_lesson_id]
        if len(matches) > 1:
            issues.append("Persistent memory contains duplicate source lesson ids.")
            source_status = "duplicate"
        elif not matches:
            warnings.append("Source lesson is no longer present in persistent memory.")
            source_status = "missing"
        else:
            source = matches[0]
            source_check = verify_memory_provenance(source)
            if not source_check.verified:
                issues.append("Source lesson embedded provenance does not verify.")
                issues.extend(f"Source: {item}" for item in source_check.issues)
                source_status = "invalid"
            elif source_check.provenance_id != provenance.get("source_provenance_id"):
                issues.append("Source lesson provenance id differs from the skill provenance.")
                source_status = "invalid"
            elif _hash_json(source.to_dict()) != provenance.get("source_record_hash"):
                warnings.append("Source lesson is valid but its lifecycle record changed after skill apply.")
                source_status = "historical"
            elif not source.active:
                warnings.append("Source lesson is no longer active.")
                source_status = "historical"
            else:
                source_status = "current"

    issues = _dedupe(issues)
    warnings = _dedupe(warnings)
    if issues:
        status = "ERROR"
    elif not current_payload_matches:
        status = "DRIFTED"
    elif source_status in {"historical", "missing", "unavailable"}:
        status = "HISTORICAL"
    else:
        status = "VERIFIED"
    return ProceduralSkillProvenanceCheck(
        status=status,
        skill_id=skill_id,
        provenance_id=provenance_id,
        source_lesson_id=source_lesson_id,
        source_status=source_status,
        current_payload_matches=current_payload_matches,
        issues=issues,
        warnings=warnings,
        verified=not issues,
    )


def format_skill_why(
    skills_path: Path,
    persistent_memory_path: Path,
    skill_id: str,
) -> str:
    identifier = skill_id.strip()
    if not identifier:
        return "Usage: /skills why <id>"
    skills, malformed, skill_error = _read_skill_records(skills_path)
    if skill_error or malformed:
        detail = skill_error or f"{malformed} malformed JSONL record(s)"
        return _error_report(f"Skill Library is unreadable or malformed: {detail}")
    matches = [skill for skill in skills if skill.get("id") == identifier]
    if not matches:
        return "\n".join(
            [
                "Procedural Skill Provenance v1",
                "Status: NOT FOUND",
                f"skill_id: {identifier}",
                "- Read-only explanation; no file was changed.",
            ]
        )
    if len(matches) > 1:
        return _error_report(f"Skill id is duplicated: {identifier}")
    memories, memory_exists, memory_error = _read_memory_records(persistent_memory_path)
    skill = matches[0]
    check = verify_procedural_skill_provenance(
        skill,
        memory_records=memories,
        memory_error=memory_error,
        memory_exists=memory_exists,
    )
    provenance = skill.get("provenance") if isinstance(skill.get("provenance"), dict) else {}
    lines = [
        "Procedural Skill Provenance v1",
        f"Status: {check.status}",
        f"skill_id: {check.skill_id}",
        f"name: {skill.get('name') or ''}",
        f"status: {skill.get('status') or 'unknown'}",
        f"source: {skill.get('source') or 'unknown'}",
        f"executable: {str(skill.get('executable') is True).lower()}",
        f"provenance_id: {check.provenance_id or 'unavailable'}",
        f"provenance_schema: {provenance.get('schema') or 'unavailable'}",
        f"provenance_hash: {provenance.get('provenance_hash') or 'unavailable'}",
        f"source_lesson_id: {check.source_lesson_id or 'unavailable'}",
        f"source_status: {check.source_status}",
        f"authoring_receipt_id: {provenance.get('authoring_receipt_id') or 'unavailable'}",
        f"authoring_hash: {provenance.get('authoring_hash') or 'unavailable'}",
        f"target_payload_hash: {provenance.get('target_payload_hash') or 'unavailable'}",
        f"current_payload_matches: {str(check.current_payload_matches).lower()}",
        "operator_confirmation_recorded: "
        + str(provenance.get("operator_confirmation_recorded") is True).lower(),
        "automatic_apply: false",
        "procedure_execution_enabled: false",
    ]
    lines.extend(f"- ERROR: {issue}" for issue in check.issues)
    lines.extend(f"- WARN: {warning}" for warning in check.warnings)
    if check.status == "UNAVAILABLE":
        lines.append("- Proto-Mind will not invent a provenance chain for this operator/legacy skill.")
    elif check.verified:
        lines.extend(
            [
                "Why this skill exists:",
                "- A verified lesson was projected into an operator-authored procedural contract.",
                "- The operator confirmed authoring and then supplied a separate exact skill-apply token.",
                "- The restart-safe envelope retains the source, contract, payload, and confirmation hashes.",
            ]
        )
    lines.extend(_read_only_boundary())
    return "\n".join(lines)


def skill_provenance_doctor(
    skills_path: Path,
    persistent_memory_path: Path,
) -> ProceduralSkillProvenanceDoctorReport:
    skills, malformed, skill_error = _read_skill_records(skills_path)
    memories, memory_exists, memory_error = _read_memory_records(persistent_memory_path)
    issues: list[str] = []
    warnings: list[str] = []
    if skill_error:
        issues.append(f"Skill Library is unreadable: {skill_error}")
    if malformed:
        issues.append(f"Skill Library contains {malformed} malformed JSONL record(s).")
    if memory_error:
        issues.append(f"Persistent memory is unreadable: {memory_error}")
    ids = [str(skill.get("id") or "") for skill in skills]
    duplicate_ids = sorted(value for value, count in Counter(ids).items() if value and count > 1)
    if any(not value for value in ids):
        issues.append("Skill Library contains a record without an id.")
    if duplicate_ids:
        issues.append("Skill Library contains duplicate ids: " + ", ".join(duplicate_ids) + ".")

    provenanced_count = 0
    verified_count = 0
    historical_count = 0
    drifted_count = 0
    legacy_applied_count = 0
    unavailable_count = 0
    for skill in skills:
        label = str(skill.get("id") or "<missing>")
        if skill.get("provenance") is None:
            unavailable_count += 1
            if skill.get("source") == "experience_learning_skill_apply":
                legacy_applied_count += 1
                warnings.append(f"Skill {label} is a legacy supervised apply without embedded provenance.")
            continue
        provenanced_count += 1
        check = verify_procedural_skill_provenance(
            skill,
            memory_records=memories,
            memory_error=memory_error,
            memory_exists=memory_exists,
        )
        if check.status == "ERROR":
            issues.extend(f"Skill {label}: {item}" for item in check.issues)
        elif check.status == "DRIFTED":
            drifted_count += 1
            warnings.append(f"Skill {label} differs from its confirmed storage projection.")
        elif check.status == "HISTORICAL":
            historical_count += 1
            warnings.extend(f"Skill {label}: {item}" for item in check.warnings)
        elif check.status == "VERIFIED":
            verified_count += 1

    try:
        from proto_mind.command_registry import COMMAND_REGISTRY

        for prefix in ("/skills why", "/skills provenance-doctor"):
            spec = next((item for item in COMMAND_REGISTRY if item.prefix == prefix), None)
            if spec is None or not spec.read_only or spec.mutates != "none":
                issues.append(f"Registry metadata for {prefix} is missing or unsafe.")
    except (ImportError, AttributeError) as exc:
        issues.append(f"Command Registry is unavailable: {exc}")

    status = "ERROR" if issues else "WARN" if warnings else "OK"
    return ProceduralSkillProvenanceDoctorReport(
        status=status,
        total_skills=len(skills),
        provenanced_count=provenanced_count,
        verified_count=verified_count,
        historical_count=historical_count,
        drifted_count=drifted_count,
        legacy_applied_count=legacy_applied_count,
        unavailable_count=unavailable_count,
        issues=_dedupe(issues),
        warnings=_dedupe(warnings),
    )


def format_skill_provenance_doctor(report: ProceduralSkillProvenanceDoctorReport) -> str:
    lines = [
        "Procedural Skill Provenance Doctor v1",
        f"Status: {report.status}",
        f"total_skills: {report.total_skills}",
        f"provenanced: {report.provenanced_count}",
        f"verified: {report.verified_count}",
        f"historical: {report.historical_count}",
        f"drifted: {report.drifted_count}",
        f"legacy_supervised_without_provenance: {report.legacy_applied_count}",
        f"operator_or_legacy_unavailable: {report.unavailable_count}",
        "procedure_execution_enabled: false",
    ]
    lines.extend(f"- ERROR: {issue}" for issue in report.issues)
    lines.extend(f"- WARN: {warning}" for warning in report.warnings)
    if not report.issues and not report.warnings:
        lines.append("- Embedded skill/source/authoring/payload hashes and read-only Registry gates are healthy.")
    lines.extend(_read_only_boundary())
    return "\n".join(lines)


def _current_payload_matches(skill: dict[str, Any], projection: object) -> bool:
    if not isinstance(projection, dict):
        return False
    return all(
        skill.get(field) == projection.get(field)
        for field in ("schema", "name", "summary", "body", "category", "tags")
    )


def _read_skill_records(path: Path) -> tuple[list[dict[str, Any]], int, str]:
    if not path.exists():
        return [], 0, ""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        return [], 0, str(exc)
    records: list[dict[str, Any]] = []
    malformed = 0
    for raw in lines:
        if not raw.strip():
            continue
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            malformed += 1
            continue
        if isinstance(parsed, dict):
            records.append(parsed)
        else:
            malformed += 1
    return records, malformed, ""


def _read_memory_records(path: Path) -> tuple[list[MemoryRecord], bool, str]:
    if not path.exists():
        return [], False, ""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, list):
            return [], True, "persistent memory root is not a JSON array"
        if any(not isinstance(item, dict) for item in payload):
            return [], True, "persistent memory contains a non-object record"
        return [MemoryRecord.from_dict(item) for item in payload], True, ""
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        return [], True, str(exc)


def _hash_json(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _is_sha256(value: object) -> bool:
    return bool(
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _error_report(message: str) -> str:
    return "\n".join(
        [
            "Procedural Skill Provenance v1",
            "Status: ERROR",
            f"- {message}",
            *_read_only_boundary(),
        ]
    )


def _read_only_boundary() -> list[str]:
    return [
        "Boundary:",
        "- Read-only provenance inspection; no skill, memory, queue, export, session log, or Context Injection changed.",
        "- No procedure execution, apply, repair, migration, shell, arbitrary dispatch, model/API call, or background action occurred.",
    ]


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))
