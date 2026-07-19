from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any

from proto_mind.command_registry import COMMAND_REGISTRY
from proto_mind.experience_learning_skill_authoring import (
    OperatorReviewedProceduralSkillAuthoringSession,
    ProceduralSkillAuthoringError,
    ProceduralSkillAuthoringReceipt,
    ProceduralSkillAuthoringRequest,
    build_procedural_skill_authoring_blueprint,
    procedural_skill_authoring_receipt_hash,
)
from proto_mind.experience_learning_skill_runtime import (
    PROCEDURAL_SKILL_APPLY_ENGINE_INSTALLED,
    PROCEDURAL_SKILL_AUTHORING_WRITES_ENABLED,
    PROCEDURAL_SKILL_EXECUTION_INSTALLED,
    PROCEDURAL_SKILL_WRITER_INSTALLED,
)
from proto_mind.experience_learning_skill_contract import (
    PROCEDURAL_SKILL_STORAGE_SCHEMA,
    ProceduralSkillContractBuilder,
    ProceduralSkillContractError,
)
from proto_mind.skill_library import SkillLibrary


PROCEDURAL_SKILL_READINESS_VERSION = 1
PROCEDURAL_SKILL_READINESS_MODE = "read_only_current_skill_contract_revalidation"
PROCEDURAL_SKILL_FUTURE_RECEIPT_FIELDS = (
    "apply_id",
    "applied_at",
    "authoring_receipt_id",
    "source_lesson_id",
    "created_skill_id",
    "before_store_sha256",
    "after_store_sha256",
    "created_record_hash",
    "target_payload_hash",
    "confirmation_token_hash",
    "record_verified",
    "source_provenance_verified",
    "exact_record_mutations",
    "rollback_suggestion",
    "receipt_hash",
)


@dataclass(frozen=True)
class ProceduralSkillApplyContract:
    operation: str
    expected_record_mutations: int
    target_record_id: str
    target_schema: str
    target_payload_hash: str
    future_receipt_fields: list[str]
    rollback: str
    atomic_write_required: bool = True
    post_write_verification_required: bool = True
    separate_confirmation_required: bool = True


@dataclass(frozen=True)
class ProceduralSkillReadinessReport:
    status: str
    receipt_id: str
    source_lesson_id: str
    stored_authoring_hash: str
    current_authoring_hash: str
    skill_store_path: str
    skill_store_sha256: str
    active_duplicate_skill_ids: list[str]
    archived_duplicate_skill_ids: list[str]
    contract: ProceduralSkillApplyContract
    checks: dict[str, bool]
    issues: list[str]
    warnings: list[str]
    ready_for_design_review: bool
    apply_engine_installed: bool = PROCEDURAL_SKILL_APPLY_ENGINE_INSTALLED
    executable: bool = False
    apply_performed: bool = False
    mutation_performed: bool = False
    persistence_performed: bool = False


@dataclass(frozen=True)
class ProceduralSkillReadinessDoctorReport:
    status: str
    receipt_count: int
    ready_count: int
    not_ready_count: int
    error_count: int
    issues: list[str]
    warnings: list[str]


class ProceduralSkillReadinessError(RuntimeError):
    pass


class ProceduralSkillApplyReadiness:
    """Revalidates authored skill receipts without installing or invoking a writer."""

    def __init__(
        self,
        *,
        builder: ProceduralSkillContractBuilder,
        skill_library: SkillLibrary,
    ) -> None:
        self.builder = builder
        self.skill_library = skill_library

    def review(
        self,
        receipt: ProceduralSkillAuthoringReceipt,
    ) -> ProceduralSkillReadinessReport:
        snapshot = self.skill_library.read_snapshot()
        records = snapshot["records"]
        record_ids = [str(record.get("id") or "") for record in records]
        current = None
        revalidation_error = ""
        try:
            request = _request_from_receipt(receipt)
            current = build_procedural_skill_authoring_blueprint(self.builder, request)
        except (ProceduralSkillAuthoringError, ProceduralSkillContractError, KeyError, TypeError, ValueError) as exc:
            revalidation_error = str(exc)

        projection = receipt.storage_projection
        active_duplicates, archived_duplicates = _global_duplicate_ids(records, projection)
        target_record_id = f"skilllearn_{receipt.authoring_hash[:16]}"
        payload_hash = _hash_json(projection)
        apply_contract = ProceduralSkillApplyContract(
            operation="atomically append exactly one operator-authored procedural skill record",
            expected_record_mutations=1,
            target_record_id=target_record_id,
            target_schema=PROCEDURAL_SKILL_STORAGE_SCHEMA,
            target_payload_hash=payload_hash,
            future_receipt_fields=list(PROCEDURAL_SKILL_FUTURE_RECEIPT_FIELDS),
            rollback=f"/skills archive {target_record_id}",
        )
        store_hash = _hash_skill_store(self.skill_library.skills_path)
        family_spec = next(
            (spec for spec in COMMAND_REGISTRY if spec.prefix == "/experience learning"),
            None,
        )
        apply_spec = next(
            (
                spec
                for spec in COMMAND_REGISTRY
                if spec.prefix == "/experience learning apply skill"
            ),
            None,
        )
        checks = {
            "authoring_receipt_safe": _receipt_is_safe(receipt),
            "current_source_revalidated": current is not None,
            "source_record_hash_matches": bool(
                current and current.source_record_hash == receipt.source_record_hash
            ),
            "base_contract_hash_matches": bool(
                current and current.base_contract_hash == receipt.base_contract_hash
            ),
            "authored_contract_hash_matches": bool(
                current and current.authoring_hash == receipt.authoring_hash
            ),
            "storage_projection_matches": bool(
                current and current.storage_projection == receipt.storage_projection
            ),
            "skill_store_readable": not bool(snapshot["error"]),
            "skill_store_well_formed": snapshot["malformed_count"] == 0,
            "skill_records_valid": all(_valid_skill_record(record) for record in records),
            "skill_record_ids_unique": bool(
                all(record_ids) and len(record_ids) == len(set(record_ids))
            )
            if records
            else True,
            "target_record_id_available": target_record_id not in record_ids,
            "active_global_duplicate_absent": not active_duplicates,
            "skill_store_hash_available": store_hash != "unavailable",
            "read_only_registry_family": bool(
                family_spec is not None
                and family_spec.read_only
                and family_spec.mutates == "none"
            ),
            "skill_apply_registry_gate_safe": bool(
                apply_spec is not None
                and not apply_spec.read_only
                and apply_spec.mutates == "skills"
                and apply_spec.risk == "medium"
            ),
            "skill_writer_installed": PROCEDURAL_SKILL_WRITER_INSTALLED,
            "skill_apply_engine_installed": PROCEDURAL_SKILL_APPLY_ENGINE_INSTALLED,
            "authoring_direct_write_disabled": not PROCEDURAL_SKILL_AUTHORING_WRITES_ENABLED,
            "skill_execution_absent": not PROCEDURAL_SKILL_EXECUTION_INSTALLED,
            "future_receipt_contract_complete": len(PROCEDURAL_SKILL_FUTURE_RECEIPT_FIELDS) == 15,
        }
        messages = {
            "authoring_receipt_safe": "Authoring receipt claims an unsafe, executable, persistent, or mutating state.",
            "current_source_revalidated": f"Current source/contract revalidation failed: {revalidation_error or 'unavailable'}",
            "source_record_hash_matches": "Current source lesson hash differs from the authoring receipt.",
            "base_contract_hash_matches": "Current base procedural contract differs from the authoring receipt.",
            "authored_contract_hash_matches": "Current authored contract hash differs from the receipt.",
            "storage_projection_matches": "Current fixed skill storage projection differs from the receipt.",
            "skill_store_readable": f"Skill Library is unreadable: {snapshot['error'] or 'unknown error'}",
            "skill_store_well_formed": "Skill Library contains malformed JSONL entries.",
            "skill_records_valid": "Skill Library contains records with invalid ids, status, or text fields.",
            "skill_record_ids_unique": "Skill Library contains missing or duplicate record ids.",
            "target_record_id_available": "Deterministic future skill record id already exists.",
            "active_global_duplicate_absent": "An active global exact skill duplicate already exists.",
            "skill_store_hash_available": "Current Skill Library SHA-256 is unavailable.",
            "read_only_registry_family": "Skill readiness lacks the safe read-only Registry family.",
            "skill_apply_registry_gate_safe": "The supervised procedural skill apply Registry gate is missing or unsafe.",
            "skill_writer_installed": "The supervised procedural skill writer is unavailable.",
            "skill_apply_engine_installed": "The supervised procedural skill apply engine is unavailable.",
            "authoring_direct_write_disabled": "The authoring command must not write skills directly.",
            "skill_execution_absent": "A procedural skill execution engine is unexpectedly installed.",
            "future_receipt_contract_complete": "Future atomic apply receipt contract is incomplete.",
        }
        issues = [messages[name] for name, passed in checks.items() if not passed]
        warnings = [
            "Readiness is bound to the current process receipt and current Skill Library bytes.",
            "Operator-authored permissions are descriptive text, not runtime enforcement.",
            "Readiness does not invoke the installed writer or generate an apply token; apply requires a separate preview and confirmation.",
        ]
        if archived_duplicates:
            warnings.append(
                "Archived exact skill duplicates exist: " + ", ".join(archived_duplicates) + "."
            )
        ready = all(checks.values()) and not issues
        status = "READY FOR SKILL APPLY DESIGN REVIEW" if ready else "NOT READY"
        if (
            not checks["authoring_receipt_safe"]
            or not checks["skill_store_readable"]
            or not checks["skill_store_well_formed"]
            or not checks["skill_records_valid"]
            or not checks["skill_record_ids_unique"]
        ):
            status = "ERROR"
        return ProceduralSkillReadinessReport(
            status=status,
            receipt_id=receipt.id,
            source_lesson_id=receipt.source_lesson_id,
            stored_authoring_hash=receipt.authoring_hash,
            current_authoring_hash=current.authoring_hash if current else "",
            skill_store_path=str(self.skill_library.skills_path),
            skill_store_sha256=store_hash,
            active_duplicate_skill_ids=active_duplicates,
            archived_duplicate_skill_ids=archived_duplicates,
            contract=apply_contract,
            checks=checks,
            issues=issues,
            warnings=warnings,
            ready_for_design_review=ready,
        )

    def doctor(
        self,
        session: OperatorReviewedProceduralSkillAuthoringSession,
    ) -> ProceduralSkillReadinessDoctorReport:
        authoring_doctor = session.doctor(self.builder)
        issues = list(authoring_doctor.issues)
        warnings = list(authoring_doctor.warnings)
        snapshot = self.skill_library.read_snapshot()
        records = snapshot["records"]
        record_ids = [str(record.get("id") or "") for record in records]
        if snapshot["error"]:
            issues.append(f"Skill Library is unreadable: {snapshot['error']}")
        if snapshot["malformed_count"]:
            issues.append(
                f"Skill Library contains {snapshot['malformed_count']} malformed JSONL entries."
            )
        if any(not _valid_skill_record(record) for record in records):
            issues.append("Skill Library contains invalid record fields or statuses.")
        if any(not record_id for record_id in record_ids) or len(record_ids) != len(
            set(record_ids)
        ):
            issues.append("Skill Library contains missing or duplicate record ids.")
        if _hash_skill_store(self.skill_library.skills_path) == "unavailable":
            issues.append("Current Skill Library SHA-256 is unavailable.")
        reports: list[ProceduralSkillReadinessReport] = []
        for item in session.snapshot():
            receipt = session.get(str(item.get("id") or ""))
            if receipt is None:
                issues.append("Skill authoring snapshot contains an unresolvable receipt.")
                continue
            report = self.review(receipt)
            reports.append(report)
            if report.status == "ERROR":
                issues.append(f"Skill authoring receipt {receipt.id} readiness returned ERROR.")
            elif report.status != "READY FOR SKILL APPLY DESIGN REVIEW":
                warnings.append(
                    f"Skill authoring receipt {receipt.id} is not ready: {'; '.join(report.issues)}"
                )

        family_spec = next(
            (spec for spec in COMMAND_REGISTRY if spec.prefix == "/experience learning"),
            None,
        )
        if family_spec is None or not family_spec.read_only or family_spec.mutates != "none":
            issues.append("Procedural skill readiness lacks safe read-only Registry metadata.")
        apply_spec = next(
            (
                spec
                for spec in COMMAND_REGISTRY
                if spec.prefix == "/experience learning apply skill"
            ),
            None,
        )
        if (
            apply_spec is None
            or apply_spec.read_only
            or apply_spec.mutates != "skills"
            or apply_spec.risk != "medium"
        ):
            issues.append("The supervised procedural skill apply Registry gate is missing or unsafe.")
        if not PROCEDURAL_SKILL_WRITER_INSTALLED or not PROCEDURAL_SKILL_APPLY_ENGINE_INSTALLED:
            issues.append("The supervised procedural skill apply writer/engine is unavailable.")
        if PROCEDURAL_SKILL_AUTHORING_WRITES_ENABLED or PROCEDURAL_SKILL_EXECUTION_INSTALLED:
            issues.append("Direct authoring writes or procedural skill execution are unexpectedly enabled.")

        counts = Counter(report.status for report in reports)
        status = "ERROR" if issues else "WARN" if warnings else "OK"
        return ProceduralSkillReadinessDoctorReport(
            status=status,
            receipt_count=len(reports),
            ready_count=counts["READY FOR SKILL APPLY DESIGN REVIEW"],
            not_ready_count=counts["NOT READY"],
            error_count=counts["ERROR"],
            issues=_dedupe(issues),
            warnings=_dedupe(warnings),
        )


def format_procedural_skill_readiness_command(
    command: str,
    *,
    reviewer: ProceduralSkillApplyReadiness,
    session: OperatorReviewedProceduralSkillAuthoringSession,
) -> str | None:
    raw = command.strip()
    normalized = " ".join(raw.lower().split())
    prefixes = (
        "/experience learning skill-apply-readiness",
        "/experience learning skill-apply-plan",
        "/experience learning skill-apply-doctor",
    )
    if not any(normalized == prefix or normalized.startswith(prefix + " ") for prefix in prefixes):
        return None
    if any(marker in raw for marker in ("\n", ";", "&&", "||")):
        return _readiness_error("Command chaining and multi-command input are not allowed.")
    try:
        if normalized == "/experience learning skill-apply-doctor":
            return format_procedural_skill_readiness_doctor(reviewer.doctor(session))
        for suffix in ("readiness", "plan"):
            prefix = f"/experience learning skill-apply-{suffix}"
            if normalized == prefix:
                return f"Usage: {prefix} <receipt_id|memory_id>"
            if normalized.startswith(prefix + " "):
                identifier = raw[len(prefix) :].strip()
                if not identifier or " " in identifier:
                    return f"Usage: {prefix} <receipt_id|memory_id>"
                receipt = session.get(identifier)
                if receipt is None:
                    return _readiness_error(
                        f"No process-memory skill authoring receipt matches {identifier!r}."
                    )
                report = reviewer.review(receipt)
                return (
                    format_procedural_skill_readiness(report)
                    if suffix == "readiness"
                    else format_procedural_skill_apply_plan(report)
                )
    except (ProceduralSkillReadinessError, ProceduralSkillContractError, OSError, TypeError, ValueError) as exc:
        return _readiness_error(str(exc))
    return None


def format_procedural_skill_readiness(report: ProceduralSkillReadinessReport) -> str:
    lines = [
        "Proto-Mind Procedural Skill Apply Readiness v1",
        f"Status: {report.status}",
        f"receipt_id: {report.receipt_id}",
        f"source_lesson_id: {report.source_lesson_id}",
        f"stored_authoring_hash: {report.stored_authoring_hash}",
        f"current_authoring_hash: {report.current_authoring_hash or 'unavailable'}",
        f"skill_store_path: {report.skill_store_path}",
        f"skill_store_sha256: {report.skill_store_sha256}",
        f"future_target_record_id: {report.contract.target_record_id}",
        f"active_duplicates: {', '.join(report.active_duplicate_skill_ids) or 'none'}",
        f"archived_duplicates: {', '.join(report.archived_duplicate_skill_ids) or 'none'}",
        "Checks:",
    ]
    lines.extend(f"- {name}: {str(value).lower()}" for name, value in report.checks.items())
    lines.extend(f"- BLOCKER: {issue}" for issue in report.issues)
    lines.extend(f"- WARN: {warning}" for warning in report.warnings)
    lines.extend(_readiness_boundary())
    return "\n".join(lines)


def format_procedural_skill_apply_plan(report: ProceduralSkillReadinessReport) -> str:
    contract = report.contract
    lines = [
        "Proto-Mind Procedural Skill Future Apply Plan v1",
        f"Status: {report.status}",
        f"receipt_id: {report.receipt_id}",
        f"operation: {contract.operation}",
        f"target_record_id: {contract.target_record_id}",
        f"target_schema: {contract.target_schema}",
        f"target_payload_hash: {contract.target_payload_hash}",
        f"expected_record_mutations: {contract.expected_record_mutations}",
        "atomic_write_required: true",
        "post_write_verification_required: true",
        "separate_confirmation_required: true",
        f"rollback_suggestion: {contract.rollback}",
        "Required future receipt fields:",
    ]
    lines.extend(f"- {field}" for field in contract.future_receipt_fields)
    lines.extend(f"- BLOCKER: {issue}" for issue in report.issues)
    lines.extend(_readiness_boundary())
    return "\n".join(lines)


def format_procedural_skill_readiness_doctor(
    report: ProceduralSkillReadinessDoctorReport,
) -> str:
    lines = [
        "Proto-Mind Procedural Skill Apply Readiness Doctor v1",
        f"Status: {report.status}",
        f"mode: {PROCEDURAL_SKILL_READINESS_MODE}",
        f"receipts: {report.receipt_count}",
        f"ready: {report.ready_count}",
        f"not_ready: {report.not_ready_count}",
        f"errors: {report.error_count}",
        f"skill_apply_engine_installed: {str(PROCEDURAL_SKILL_APPLY_ENGINE_INSTALLED).lower()}",
    ]
    lines.extend(f"- ERROR: {issue}" for issue in report.issues)
    lines.extend(f"- WARN: {warning}" for warning in report.warnings)
    if not report.issues and not report.warnings:
        lines.append(
            "- Current source, authoring receipt, global duplicate scope, target hash, receipt contract, and supervised apply gates are healthy."
        )
    lines.extend(_readiness_boundary())
    return "\n".join(lines)


def _request_from_receipt(
    receipt: ProceduralSkillAuthoringReceipt,
) -> ProceduralSkillAuthoringRequest:
    contract = receipt.authored_contract
    return ProceduralSkillAuthoringRequest(
        memory_id=receipt.source_lesson_id,
        name=str(contract["name"]),
        summary=str(contract["summary"]),
        trigger=str(contract["trigger"]),
        preconditions=list(contract["preconditions"]),
        steps=list(contract["steps"]),
        permissions=list(contract["permissions"]),
        verification=list(contract["verification"]),
        known_failure_modes=list(contract["known_failure_modes"]),
    )


def _receipt_is_safe(receipt: ProceduralSkillAuthoringReceipt) -> bool:
    return bool(
        receipt.operator_confirmation_recorded
        and receipt.authoring_fields_complete
        and receipt.process_memory_only
        and receipt.restart_expiring
        and not receipt.future_apply_ready
        and not receipt.executable
        and not receipt.promotion_allowed
        and not receipt.skill_write_allowed
        and not receipt.skill_mutation_performed
        and not receipt.memory_mutation_performed
        and not receipt.experience_mutation_performed
        and not receipt.persistence_performed
        and len(receipt.authoring_hash) == 64
        and receipt.id == f"skillauth_{receipt.authoring_hash[:16]}"
        and procedural_skill_authoring_receipt_hash(receipt) == receipt.authoring_hash
        and len(receipt.confirmation_token_hash) == 64
    )


def _global_duplicate_ids(
    records: list[dict[str, Any]],
    projection: dict[str, Any],
) -> tuple[list[str], list[str]]:
    name = _normalize(str(projection.get("name") or ""))
    summary = _normalize(str(projection.get("summary") or ""))
    body = _normalize(str(projection.get("body") or ""))
    active: list[str] = []
    archived: list[str] = []
    for record in records:
        exact = bool(
            (_normalize(str(record.get("name") or "")) == name and name)
            or (_normalize(str(record.get("body") or "")) == body and body)
            or (_normalize(str(record.get("summary") or "")) == summary and summary)
        )
        if not exact:
            continue
        target = active if record.get("status") == "active" else archived
        target.append(str(record.get("id") or "unknown"))
    return sorted(set(active)), sorted(set(archived))


def _valid_skill_record(record: dict[str, Any]) -> bool:
    return bool(
        str(record.get("id") or "").strip()
        and record.get("status") in {"active", "archived"}
        and all(
            isinstance(record.get(field, ""), str)
            for field in ("name", "summary", "body")
        )
    )


def _hash_skill_store(path: Path) -> str:
    try:
        payload = path.read_bytes() if path.exists() else b""
    except OSError:
        return "unavailable"
    return hashlib.sha256(payload).hexdigest()


def _hash_json(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _normalize(value: str) -> str:
    return " ".join(value.casefold().split())


def _readiness_error(message: str) -> str:
    return "\n".join(
        [
            "Proto-Mind Procedural Skill Apply Readiness Error",
            "Status: ERROR",
            f"- {message}",
            *_readiness_boundary(),
        ]
    )


def _readiness_boundary() -> list[str]:
    return [
        "Boundary:",
        "- Read-only design readiness only; no apply token was generated and no skill was written, promoted, or executed.",
        "- No lesson, memory, Skill Library, Experience event, receipt, queue, export, session log, or Context Injection changed.",
        "- The supervised writer/apply engine was not invoked; no shell, arbitrary dispatch, model/API call, auto-apply, or background action occurred.",
    ]


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))
