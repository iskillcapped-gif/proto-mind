from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
from typing import Any

from proto_mind.command_registry import COMMAND_REGISTRY
from proto_mind.experience_learning_lifecycle_audit import (
    LearningLifecycleAuditError,
    LearningLifecycleTransitionAudit,
)
from proto_mind.memory_provenance import verify_memory_provenance
from proto_mind.memory_store import MemoryStore
from proto_mind.models import MemoryRecord
from proto_mind.skill_library import SkillLibrary


PROCEDURAL_SKILL_CONTRACT_VERSION = 1
PROCEDURAL_SKILL_CONTRACT_SCHEMA = "skill.procedure.contract.v1"
PROCEDURAL_SKILL_STORAGE_SCHEMA = "skill.procedure.v1"
PROCEDURAL_SKILL_CONTRACT_MODE = "read_only_operator_authoring_contract"
PROCEDURAL_SKILL_APPLY_ENGINE_INSTALLED = False
PROCEDURAL_SKILL_REQUIRED_FIELDS = (
    "trigger",
    "preconditions",
    "steps",
    "permissions",
    "verification",
    "known_failure_modes",
)


@dataclass(frozen=True)
class ProceduralSkillContract:
    id: str
    schema: str
    version: int
    source_lesson_id: str
    source_provenance_id: str
    source_apply_id: str
    source_record_hash: str
    name: str
    summary: str
    trigger: str
    preconditions: list[str]
    steps: list[str]
    permissions: list[str]
    verification: list[str]
    known_failure_modes: list[str]
    storage_schema: str
    storage_projection: dict[str, Any]
    required_operator_fields: list[str]
    complete: bool = False
    executable: bool = False
    promotion_allowed: bool = False
    automatic_synthesis_performed: bool = False
    mutation_performed: bool = False
    contract_hash: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ProceduralSkillContractReview:
    status: str
    memory_id: str
    lifecycle_state: str
    duplicate_skill_ids: list[str]
    checks: dict[str, bool]
    issues: list[str]
    warnings: list[str]
    contract: ProceduralSkillContract | None
    eligible_for_operator_authoring: bool
    mutation_performed: bool = False


@dataclass(frozen=True)
class ProceduralSkillContractDoctorReport:
    status: str
    learned_lesson_count: int
    active_lesson_count: int
    eligible_count: int
    duplicate_count: int
    skill_count: int
    malformed_skill_count: int
    issues: list[str]
    warnings: list[str]
    mutation_performed: bool = False


class ProceduralSkillContractError(RuntimeError):
    pass


class ProceduralSkillContractBuilder:
    """Builds bounded skill-authoring contracts without synthesizing or writing skills."""

    def __init__(
        self,
        *,
        memory_store: MemoryStore,
        skill_library: SkillLibrary,
    ) -> None:
        self.memory_store = memory_store
        self.skill_library = skill_library

    def review(self, memory_id: str) -> ProceduralSkillContractReview:
        records = self._load_memory()
        matching = [record for record in records if record.id == memory_id]
        record = matching[0] if len(matching) == 1 else None
        skill_snapshot = self.skill_library.read_snapshot()
        try:
            lifecycle_report = LearningLifecycleTransitionAudit(self.memory_store).inspect()
        except LearningLifecycleAuditError as exc:
            raise ProceduralSkillContractError(str(exc)) from exc
        lifecycle_entry = next(
            (entry for entry in lifecycle_report.entries if entry.memory_id == memory_id),
            None,
        )
        provenance = verify_memory_provenance(record) if record is not None else None
        duplicate_ids = (
            _duplicate_skill_ids(record, skill_snapshot["records"])
            if record is not None
            else []
        )
        checks = {
            "exact_memory_id_found": len(matching) == 1,
            "learned_lesson": bool(record and record.type == "lesson" and record.provenance),
            "lesson_active": bool(record and record.active),
            "lifecycle_state_active": bool(lifecycle_entry and lifecycle_entry.state == "active"),
            "durable_provenance_verified": bool(provenance and provenance.verified),
            "lifecycle_audit_safe": lifecycle_report.status != "ERROR",
            "skill_store_readable": not bool(skill_snapshot["error"]),
            "skill_store_well_formed": skill_snapshot["malformed_count"] == 0,
            "active_exact_duplicate_absent": not duplicate_ids,
            "skill_apply_engine_absent": not PROCEDURAL_SKILL_APPLY_ENGINE_INSTALLED,
        }
        messages = {
            "exact_memory_id_found": "Persistent memory must contain exactly one matching id.",
            "learned_lesson": "Source is not a durable learned lesson.",
            "lesson_active": "Only an active learned lesson can enter skill authoring.",
            "lifecycle_state_active": "Lifecycle audit does not classify the lesson as active.",
            "durable_provenance_verified": "Source lesson provenance does not verify.",
            "lifecycle_audit_safe": "Lifecycle audit reports an error.",
            "skill_store_readable": "Skill Library is unreadable.",
            "skill_store_well_formed": "Skill Library contains malformed JSONL entries.",
            "active_exact_duplicate_absent": "An active exact skill duplicate already exists.",
            "skill_apply_engine_absent": "A procedural skill apply engine is unexpectedly installed.",
        }
        issues = [messages[name] for name, passed in checks.items() if not passed]
        warnings = list(lifecycle_report.warnings)
        if duplicate_ids:
            warnings.append(f"Duplicate active skills: {', '.join(duplicate_ids)}.")
        contract = (
            _build_contract(record, provenance.provenance_id)
            if record is not None and provenance is not None and provenance.verified
            else None
        )
        eligible = all(checks.values()) and not issues and contract is not None
        if eligible:
            status = "ELIGIBLE FOR OPERATOR AUTHORING"
        elif duplicate_ids and all(
            passed for name, passed in checks.items() if name != "active_exact_duplicate_absent"
        ):
            status = "DUPLICATE"
        elif (
            not checks["skill_store_readable"]
            or len(matching) > 1
            or (record is not None and not checks["durable_provenance_verified"])
        ):
            status = "ERROR"
        else:
            status = "NOT ELIGIBLE"
        return ProceduralSkillContractReview(
            status=status,
            memory_id=memory_id,
            lifecycle_state=lifecycle_entry.state if lifecycle_entry else "unavailable",
            duplicate_skill_ids=duplicate_ids,
            checks=checks,
            issues=_dedupe(issues),
            warnings=_dedupe(warnings),
            contract=contract,
            eligible_for_operator_authoring=eligible,
        )

    def doctor(self) -> ProceduralSkillContractDoctorReport:
        records = self._load_memory()
        skill_snapshot = self.skill_library.read_snapshot()
        learned = [record for record in records if record.type == "lesson" and record.provenance]
        issues: list[str] = []
        warnings: list[str] = []
        ids = [record.id for record in records]
        duplicate_memory_ids = [
            record_id for record_id, count in Counter(ids).items() if count > 1
        ]
        issues.extend(f"Duplicate persistent memory id: {record_id}." for record_id in duplicate_memory_ids)
        if skill_snapshot["error"]:
            issues.append(f"Skill Library is unreadable: {skill_snapshot['error']}")
        if skill_snapshot["malformed_count"]:
            warnings.append(
                f"Skill Library contains {skill_snapshot['malformed_count']} malformed JSONL entries."
            )
        skill_ids = [str(skill.get("id") or "") for skill in skill_snapshot["records"]]
        duplicate_skill_ids = [
            skill_id for skill_id, count in Counter(skill_ids).items() if skill_id and count > 1
        ]
        issues.extend(f"Duplicate skill id: {skill_id}." for skill_id in duplicate_skill_ids)

        reviews: list[ProceduralSkillContractReview] = []
        if not issues:
            for record in learned:
                review = self.review(record.id)
                reviews.append(review)
                if review.status == "ERROR":
                    issues.append(f"Lesson {record.id} contract review returned ERROR.")
                elif review.status == "NOT ELIGIBLE" and record.active:
                    warnings.append(
                        f"Active learned lesson {record.id} is not eligible: {'; '.join(review.issues)}"
                    )

        family = next(
            (spec for spec in COMMAND_REGISTRY if spec.prefix == "/experience learning"),
            None,
        )
        if family is None or not family.read_only or family.mutates != "none":
            issues.append("Procedural contract commands lack the safe read-only Registry family.")
        if any("skill-contract-apply" in spec.prefix for spec in COMMAND_REGISTRY):
            issues.append("A procedural skill contract apply prefix is unexpectedly registered.")
        if PROCEDURAL_SKILL_APPLY_ENGINE_INSTALLED:
            issues.append("Procedural skill apply engine must remain absent in v3.5a.")
        if set(PROCEDURAL_SKILL_REQUIRED_FIELDS) != {
            "trigger",
            "preconditions",
            "steps",
            "permissions",
            "verification",
            "known_failure_modes",
        }:
            issues.append("Procedural skill required-field contract is invalid.")

        eligible_count = sum(review.eligible_for_operator_authoring for review in reviews)
        duplicate_count = sum(review.status == "DUPLICATE" for review in reviews)
        status = "ERROR" if issues else "WARN" if warnings else "OK"
        return ProceduralSkillContractDoctorReport(
            status=status,
            learned_lesson_count=len(learned),
            active_lesson_count=sum(record.active for record in learned),
            eligible_count=eligible_count,
            duplicate_count=duplicate_count,
            skill_count=len(skill_snapshot["records"]),
            malformed_skill_count=int(skill_snapshot["malformed_count"]),
            issues=_dedupe(issues),
            warnings=_dedupe(warnings),
        )

    def _load_memory(self) -> list[MemoryRecord]:
        try:
            return self.memory_store.load_persistent_memory()
        except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ProceduralSkillContractError(f"Persistent memory is unreadable: {exc}") from exc


def format_procedural_skill_contract_command(
    command: str,
    *,
    memory_store: MemoryStore | None,
    project_root: Path,
) -> str | None:
    raw = command.strip()
    normalized = " ".join(raw.lower().split())
    prefixes = (
        "/experience learning skill-contract-status",
        "/experience learning skill-contract-preview",
        "/experience learning skill-contract-template",
        "/experience learning skill-contract-checklist",
        "/experience learning skill-contract-doctor",
    )
    if not any(normalized == prefix or normalized.startswith(prefix + " ") for prefix in prefixes):
        return None
    if any(marker in raw for marker in ("\n", ";", "&&", "||")):
        return _contract_error("Command chaining and multi-command input are not allowed.")
    if memory_store is None:
        return _contract_error("MemoryStore is unavailable from the shared handler.")
    builder = ProceduralSkillContractBuilder(
        memory_store=memory_store,
        skill_library=SkillLibrary.from_project_root(project_root),
    )
    try:
        if normalized == "/experience learning skill-contract-doctor":
            return format_procedural_skill_contract_doctor(builder.doctor())
        if normalized == "/experience learning skill-contract-status":
            return format_procedural_skill_contract_status(builder.doctor())
        for suffix in ("preview", "template", "checklist"):
            prefix = f"/experience learning skill-contract-{suffix}"
            if normalized == prefix:
                return f"Usage: {prefix} <memory_id>"
            if normalized.startswith(prefix + " "):
                identifier = raw[len(prefix) :].strip()
                if not identifier or " " in identifier:
                    return f"Usage: {prefix} <memory_id>"
                review = builder.review(identifier)
                if suffix == "preview":
                    return format_procedural_skill_contract_preview(review)
                if suffix == "template":
                    return format_procedural_skill_contract_template(review)
                return format_procedural_skill_contract_checklist(review)
    except ProceduralSkillContractError as exc:
        return _contract_error(str(exc))
    return None


def format_procedural_skill_contract_status(
    report: ProceduralSkillContractDoctorReport,
) -> str:
    return "\n".join(
        [
            "Proto-Mind Procedural Skill Contract Status v1",
            f"Status: {report.status}",
            f"mode: {PROCEDURAL_SKILL_CONTRACT_MODE}",
            f"contract_schema: {PROCEDURAL_SKILL_CONTRACT_SCHEMA}",
            f"storage_schema: {PROCEDURAL_SKILL_STORAGE_SCHEMA}",
            f"learned_lessons: {report.learned_lesson_count}",
            f"active_lessons: {report.active_lesson_count}",
            f"eligible_for_operator_authoring: {report.eligible_count}",
            f"exact_skill_duplicates: {report.duplicate_count}",
            f"skills: {report.skill_count}",
            f"skill_apply_engine_installed: {str(PROCEDURAL_SKILL_APPLY_ENGINE_INSTALLED).lower()}",
            "Commands: skill-contract-preview|template|checklist <memory_id> | skill-contract-doctor",
            *_contract_boundary(),
        ]
    )


def format_procedural_skill_contract_preview(
    review: ProceduralSkillContractReview,
) -> str:
    lines = [
        "Proto-Mind Procedural Skill Contract Preview v1",
        f"Status: {review.status}",
        f"memory_id: {review.memory_id}",
        f"lifecycle_state: {review.lifecycle_state}",
        f"eligible_for_operator_authoring: {str(review.eligible_for_operator_authoring).lower()}",
        "Checks:",
    ]
    lines.extend(f"- {name}: {str(value).lower()}" for name, value in review.checks.items())
    lines.extend(f"- ERROR: {issue}" for issue in review.issues)
    lines.extend(f"- WARN: {warning}" for warning in review.warnings)
    if review.contract is not None:
        contract = review.contract
        lines.extend(
            [
                "Draft contract:",
                f"- contract_id: {contract.id}",
                f"- contract_hash: {contract.contract_hash}",
                f"- source_provenance_id: {contract.source_provenance_id}",
                f"- name: {contract.name}",
                f"- summary: {contract.summary}",
                f"- required_operator_fields: {', '.join(contract.required_operator_fields)}",
                "- complete: false",
                "- executable: false",
                "- promotion_allowed: false",
            ]
        )
    lines.extend(_contract_boundary())
    return "\n".join(lines)


def format_procedural_skill_contract_template(
    review: ProceduralSkillContractReview,
) -> str:
    if not review.eligible_for_operator_authoring or review.contract is None:
        return _not_eligible(review)
    contract = review.contract
    template = {
        "schema": contract.schema,
        "version": contract.version,
        "contract_id": contract.id,
        "source_lesson_id": contract.source_lesson_id,
        "source_provenance_id": contract.source_provenance_id,
        "source_record_hash": contract.source_record_hash,
        "name": contract.name,
        "summary": contract.summary,
        "trigger": "<operator required>",
        "preconditions": ["<operator required>"],
        "steps": ["<operator required>"],
        "permissions": ["<operator required; least privilege>"],
        "verification": ["<operator required>"],
        "known_failure_modes": ["<operator required>"],
        "complete": False,
        "executable": False,
        "promotion_allowed": False,
    }
    return "\n".join(
        [
            "Proto-Mind Procedural Skill Contract Authoring Template v1",
            "Status: OPERATOR INPUT REQUIRED",
            json.dumps(template, ensure_ascii=False, indent=2, sort_keys=True),
            "- Template was printed only; it was not stored or submitted.",
            *_contract_boundary(),
        ]
    )


def format_procedural_skill_contract_checklist(
    review: ProceduralSkillContractReview,
) -> str:
    lines = [
        "Proto-Mind Procedural Skill Contract Checklist v1",
        f"Status: {'READY FOR OPERATOR AUTHORING' if review.eligible_for_operator_authoring else review.status}",
        f"memory_id: {review.memory_id}",
        "Required operator-authored fields:",
        "- trigger: when this procedure is applicable",
        "- preconditions: facts and state that must be true before use",
        "- steps: ordered bounded actions; no hidden or chained action",
        "- permissions: explicit least-privilege capabilities",
        "- verification: observable success criteria",
        "- known_failure_modes: stop/recovery conditions",
        "Mandatory future gates:",
        "- exact source lesson/provenance/hash revalidation",
        "- exact duplicate check against the current active Skill Library",
        "- separate operator confirmation and fixed storage projection",
        "- atomic one-skill write, receipt, post-write verification, and rollback suggestion",
        "- no execution merely because a skill was authored or stored",
    ]
    lines.extend(f"- BLOCKER: {issue}" for issue in review.issues)
    lines.extend(_contract_boundary())
    return "\n".join(lines)


def format_procedural_skill_contract_doctor(
    report: ProceduralSkillContractDoctorReport,
) -> str:
    lines = [
        "Proto-Mind Procedural Skill Contract Doctor v1",
        f"Status: {report.status}",
        f"mode: {PROCEDURAL_SKILL_CONTRACT_MODE}",
        f"learned_lessons: {report.learned_lesson_count}",
        f"active_lessons: {report.active_lesson_count}",
        f"eligible: {report.eligible_count}",
        f"duplicates: {report.duplicate_count}",
        f"skills: {report.skill_count}",
        f"malformed_skills: {report.malformed_skill_count}",
        f"skill_apply_engine_installed: {str(PROCEDURAL_SKILL_APPLY_ENGINE_INSTALLED).lower()}",
    ]
    lines.extend(f"- ERROR: {issue}" for issue in report.issues)
    lines.extend(f"- WARN: {warning}" for warning in report.warnings)
    if not report.issues and not report.warnings:
        lines.append(
            "- Source provenance, lifecycle gate, duplicate review, schema, Registry, and no-writer boundary are healthy."
        )
    lines.extend(_contract_boundary())
    return "\n".join(lines)


def _build_contract(
    record: MemoryRecord,
    provenance_id: str,
) -> ProceduralSkillContract:
    provenance = record.provenance if isinstance(record.provenance, dict) else {}
    source_record_hash = _hash_json(record.to_dict())
    name = _preview(record.content, 80)
    summary = _preview(record.content, 240)
    material = {
        "schema": PROCEDURAL_SKILL_CONTRACT_SCHEMA,
        "version": PROCEDURAL_SKILL_CONTRACT_VERSION,
        "source_lesson_id": record.id,
        "source_provenance_id": provenance_id,
        "source_apply_id": str(provenance.get("apply_id") or ""),
        "source_record_hash": source_record_hash,
        "name": name,
        "summary": summary,
        "trigger": "",
        "preconditions": [],
        "steps": [],
        "permissions": [],
        "verification": [],
        "known_failure_modes": [],
        "storage_schema": PROCEDURAL_SKILL_STORAGE_SCHEMA,
        "storage_projection": _storage_projection(name, summary),
        "required_operator_fields": list(PROCEDURAL_SKILL_REQUIRED_FIELDS),
        "complete": False,
        "executable": False,
        "promotion_allowed": False,
        "automatic_synthesis_performed": False,
        "mutation_performed": False,
    }
    contract_hash = _hash_json(material)
    return ProceduralSkillContract(
        id=f"skillcontract_{contract_hash[:16]}",
        **material,
        contract_hash=contract_hash,
    )


def _storage_projection(name: str, summary: str) -> dict[str, Any]:
    body = "\n".join(
        [
            "Trigger:",
            "<operator required>",
            "",
            "Preconditions:",
            "- <operator required>",
            "",
            "Steps:",
            "1. <operator required>",
            "",
            "Permissions:",
            "- <operator required; least privilege>",
            "",
            "Verification:",
            "- <operator required>",
            "",
            "Known failure modes:",
            "- <operator required>",
        ]
    )
    return {
        "schema": PROCEDURAL_SKILL_STORAGE_SCHEMA,
        "name": name,
        "summary": summary,
        "body": body,
        "status": "active",
        "category": "workflow",
        "source": "experience_learning_skill_contract",
        "tags": ["experience", "operator_reviewed", "procedural_contract"],
    }


def _duplicate_skill_ids(
    record: MemoryRecord,
    skills: list[dict[str, Any]],
) -> list[str]:
    content = _normalize(record.content)
    matches: list[str] = []
    for skill in skills:
        if skill.get("status") != "active":
            continue
        values = (
            str(skill.get("summary") or ""),
            str(skill.get("body") or ""),
            str(skill.get("name") or ""),
        )
        if skill.get("source_lesson_id") == record.id or any(
            _normalize(value) == content for value in values if value.strip()
        ):
            matches.append(str(skill.get("id") or "unknown"))
    return sorted(set(matches))


def _not_eligible(review: ProceduralSkillContractReview) -> str:
    lines = [
        "Proto-Mind Procedural Skill Contract Authoring Template v1",
        f"Status: {review.status}",
    ]
    lines.extend(f"- BLOCKER: {issue}" for issue in review.issues)
    lines.extend(_contract_boundary())
    return "\n".join(lines)


def _contract_error(message: str) -> str:
    return "\n".join(
        [
            "Proto-Mind Procedural Skill Contract Error",
            "Status: ERROR",
            f"- {message}",
            *_contract_boundary(),
        ]
    )


def _contract_boundary() -> list[str]:
    return [
        "Boundary:",
        "- Read-only operator-authoring contract; no procedure was synthesized, accepted, stored, or executed.",
        "- No lesson, skill, memory, Experience event, queue, export, session log, or Context Injection changed.",
        "- Skill apply engine is absent; no shell, arbitrary dispatch, model/API call, auto-promotion, or background action occurred.",
    ]


def _hash_json(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _normalize(value: str) -> str:
    return " ".join(value.casefold().split())


def _preview(value: str, limit: int) -> str:
    normalized = " ".join(value.split())
    return normalized if len(normalized) <= limit else normalized[: limit - 3] + "..."


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))
