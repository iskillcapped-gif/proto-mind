from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
from typing import Any

from proto_mind.command_registry import COMMAND_REGISTRY
from proto_mind.experience_learning_skill_outcome_decision import (
    OperatorReviewedProceduralSkillOutcomeDecisionSession,
    ProceduralSkillOutcomeDecisionBuilder,
    ProceduralSkillOutcomeDecisionError,
    ProceduralSkillOutcomeDecisionReceipt,
    procedural_skill_outcome_decision_receipt_hash,
)
from proto_mind.experience_learning_skill_runtime import (
    PROCEDURAL_SKILL_EXECUTION_INSTALLED,
)
from proto_mind.skill_library import SkillLibrary


PROCEDURAL_SKILL_LIFECYCLE_READINESS_VERSION = 1
PROCEDURAL_SKILL_LIFECYCLE_READINESS_MODE = (
    "read_only_current_outcome_decision_and_skill_bytes_revalidation"
)
PROCEDURAL_SKILL_LIFECYCLE_FUTURE_RECEIPT_FIELDS = (
    "lifecycle_apply_id",
    "applied_at",
    "decision_receipt_id",
    "skill_id",
    "decision",
    "before_store_sha256",
    "after_store_sha256",
    "before_record_hash",
    "after_record_hash",
    "exact_record_mutations",
    "confirmation_token_hash",
    "post_state_verified",
    "rollback_suggestion",
    "receipt_hash",
)


@dataclass(frozen=True)
class ProceduralSkillLifecycleContract:
    decision: str
    operation: str
    expected_skill_record_mutations: int
    current_status_required: str
    future_target_status: str
    direct_lifecycle_apply_allowed: bool
    separate_confirmation_required: bool
    atomic_write_required: bool
    post_write_verification_required: bool
    revision_payload_required: bool
    preserve_original_until_verified: bool
    rollback_suggestion: str
    future_receipt_fields: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ProceduralSkillLifecycleReadinessReport:
    status: str
    decision_receipt_id: str
    skill_id: str
    decision: str
    outcome_status: str
    provenance_id: str
    stored_decision_hash: str
    current_decision_hash: str
    skill_store_path: str
    skill_store_sha256: str
    skill_record_hash: str
    contract: ProceduralSkillLifecycleContract
    checks: dict[str, bool]
    issues: list[str]
    warnings: list[str]
    ready_for_design_review: bool
    executable: bool = False
    apply_token_generated: bool = False
    future_apply_ready: bool = False
    skill_mutation_performed: bool = False
    procedure_execution_performed: bool = False
    persistence_performed: bool = False


@dataclass(frozen=True)
class ProceduralSkillLifecycleReadinessDoctorReport:
    status: str
    receipt_count: int
    ready_count: int
    not_ready_count: int
    error_count: int
    keep_count: int
    revise_count: int
    archive_count: int
    issues: list[str]
    warnings: list[str]


class ProceduralSkillLifecycleReadinessError(RuntimeError):
    pass


class ProceduralSkillLifecycleApplyReadiness:
    """Revalidates a v3.5h decision without granting lifecycle apply authority."""

    def __init__(
        self,
        *,
        builder: ProceduralSkillOutcomeDecisionBuilder,
        skill_library: SkillLibrary,
    ) -> None:
        self.builder = builder
        self.skill_library = skill_library

    def review(
        self,
        receipt: ProceduralSkillOutcomeDecisionReceipt,
    ) -> ProceduralSkillLifecycleReadinessReport:
        snapshot = self.skill_library.read_snapshot()
        records = snapshot["records"]
        record_ids = [str(record.get("id") or "") for record in records]
        matches = [record for record in records if record.get("id") == receipt.skill_id]
        skill = matches[0] if len(matches) == 1 else None
        store_hash = _hash_file(self.skill_library.skills_path)
        record_hash = _hash_json(skill) if skill is not None else ""
        contract = _contract_for(receipt.decision, receipt.skill_id)

        current = None
        revalidation_error = ""
        try:
            current = self.builder.build(receipt.skill_id, receipt.decision)
        except ProceduralSkillOutcomeDecisionError as exc:
            revalidation_error = str(exc)

        registry = {item.prefix: item for item in COMMAND_REGISTRY}
        expected_registry = (
            "/experience learning skill-outcome-lifecycle-readiness",
            "/experience learning skill-outcome-lifecycle-plan",
            "/experience learning skill-outcome-lifecycle-doctor",
        )
        registry_safe = all(
            prefix in registry
            and registry[prefix].read_only
            and registry[prefix].mutates == "none"
            and registry[prefix].risk == "low"
            for prefix in expected_registry
        )
        dangerous_apply_absent = not any(
            item.prefix.startswith("/experience learning apply skill-outcome")
            or item.prefix.startswith("/experience learning apply skill-lifecycle")
            for item in COMMAND_REGISTRY
        )
        checks = {
            "decision_receipt_safe": _receipt_is_safe(receipt),
            "decision_receipt_hash_valid": (
                receipt.receipt_hash
                == procedural_skill_outcome_decision_receipt_hash(receipt.to_dict())
            ),
            "current_decision_revalidated": current is not None,
            "decision_hash_matches": bool(
                current and current.decision_hash == receipt.decision_hash
            ),
            "review_hash_matches": bool(
                current and current.review_hash == receipt.review_hash
            ),
            "capture_receipts_match": bool(
                current
                and current.capture_receipt_ids == receipt.capture_receipt_ids
                and current.capture_receipt_hashes == receipt.capture_receipt_hashes
            ),
            "evidence_event_ids_match": bool(
                current and current.evidence_event_ids == receipt.evidence_event_ids
            ),
            "provenance_id_matches": bool(
                current and current.provenance_id == receipt.provenance_id
            ),
            "skill_store_readable": not bool(snapshot["error"]),
            "skill_store_well_formed": snapshot["malformed_count"] == 0,
            "skill_records_valid": all(_valid_skill_record(record) for record in records),
            "skill_record_ids_unique": bool(
                all(record_ids) and len(record_ids) == len(set(record_ids))
            )
            if records
            else True,
            "exact_skill_record_found": len(matches) == 1,
            "current_skill_active": bool(skill and skill.get("status") == "active"),
            "current_skill_non_executable": bool(
                skill and skill.get("executable") is False
            ),
            "skill_store_hash_available": store_hash != "unavailable",
            "skill_record_hash_available": bool(record_hash),
            "future_contract_safe": _contract_is_safe(contract),
            "read_only_registry_metadata": registry_safe,
            "lifecycle_apply_command_absent": dangerous_apply_absent,
            "procedure_execution_absent": not PROCEDURAL_SKILL_EXECUTION_INSTALLED,
            "apply_token_not_generated": True,
        }
        messages = {
            "decision_receipt_safe": "Decision receipt violates its exact-confirmation or no-apply boundary.",
            "decision_receipt_hash_valid": "Decision receipt hash does not verify.",
            "current_decision_revalidated": (
                "Current decision evidence cannot be revalidated: "
                + (revalidation_error or "unavailable")
            ),
            "decision_hash_matches": "Current decision hash differs from the stored terminal decision.",
            "review_hash_matches": "Current outcome review differs from the stored decision review.",
            "capture_receipts_match": "Current confirmed capture receipts differ from the decision receipt.",
            "evidence_event_ids_match": "Current decisive evidence ids differ from the decision receipt.",
            "provenance_id_matches": "Current skill provenance differs from the decision receipt.",
            "skill_store_readable": f"Skill Library is unreadable: {snapshot['error'] or 'unknown error'}",
            "skill_store_well_formed": "Skill Library contains malformed JSONL entries.",
            "skill_records_valid": "Skill Library contains invalid record fields or statuses.",
            "skill_record_ids_unique": "Skill Library contains missing or duplicate record ids.",
            "exact_skill_record_found": "The exact decided skill record is missing or duplicated.",
            "current_skill_active": "Lifecycle readiness requires the decided skill to remain active.",
            "current_skill_non_executable": "The decided skill unexpectedly claims executable capability.",
            "skill_store_hash_available": "Current Skill Library SHA-256 is unavailable.",
            "skill_record_hash_available": "Current exact skill record hash is unavailable.",
            "future_contract_safe": "Future lifecycle safeguard contract is incomplete or unsafe.",
            "read_only_registry_metadata": "Lifecycle readiness Registry metadata is missing or unsafe.",
            "lifecycle_apply_command_absent": "A procedural skill outcome lifecycle apply command is unexpectedly exposed.",
            "procedure_execution_absent": "Procedural skill execution is unexpectedly installed.",
            "apply_token_not_generated": "Readiness must never generate an apply token.",
        }
        issues = [messages[name] for name, passed in checks.items() if not passed]
        warnings = [
            "Readiness is bound to the current process decision, current evidence, and current Skill Library bytes.",
            "No lifecycle apply command or confirmation token exists in v3.5i.",
        ]
        if receipt.decision == "keep":
            warnings.append(
                "A future keep action must be receipt-only and must not rewrite the skill record."
            )
        elif receipt.decision == "archive":
            warnings.append(
                "A future archive action must atomically change only status active to archived and verify rollback metadata."
            )
        else:
            warnings.append(
                "Revision is not directly applyable; a separate versioned replacement payload and confirmation are required."
            )

        ready = all(checks.values()) and not issues
        status = "READY FOR LIFECYCLE APPLY DESIGN REVIEW" if ready else "NOT READY"
        if any(
            not checks[name]
            for name in (
                "decision_receipt_safe",
                "decision_receipt_hash_valid",
                "skill_store_readable",
                "skill_store_well_formed",
                "skill_records_valid",
                "skill_record_ids_unique",
                "current_skill_non_executable",
            )
        ):
            status = "ERROR"
        return ProceduralSkillLifecycleReadinessReport(
            status=status,
            decision_receipt_id=receipt.id,
            skill_id=receipt.skill_id,
            decision=receipt.decision,
            outcome_status=receipt.outcome_status,
            provenance_id=receipt.provenance_id,
            stored_decision_hash=receipt.decision_hash,
            current_decision_hash=current.decision_hash if current else "",
            skill_store_path=str(self.skill_library.skills_path),
            skill_store_sha256=store_hash,
            skill_record_hash=record_hash,
            contract=contract,
            checks=checks,
            issues=_dedupe(issues),
            warnings=_dedupe(warnings),
            ready_for_design_review=ready,
        )

    def doctor(
        self,
        session: OperatorReviewedProceduralSkillOutcomeDecisionSession,
    ) -> ProceduralSkillLifecycleReadinessDoctorReport:
        issues: list[str] = []
        warnings: list[str] = []
        reports: list[ProceduralSkillLifecycleReadinessReport] = []
        receipts = session.snapshot()
        for item in receipts:
            receipt = session.get(str(item.get("id") or ""))
            if receipt is None:
                issues.append("Decision snapshot contains an unresolvable receipt.")
                continue
            report = self.review(receipt)
            reports.append(report)
            if report.status == "ERROR":
                issues.append(f"Decision receipt {receipt.id} readiness returned ERROR.")
            elif not report.ready_for_design_review:
                warnings.append(
                    f"Decision receipt {receipt.id} is not ready: "
                    + "; ".join(report.issues)
                )
        if not receipts:
            warnings.append("No procedural skill outcome decision exists in this process.")

        registry = {item.prefix: item for item in COMMAND_REGISTRY}
        for prefix in (
            "/experience learning skill-outcome-lifecycle-readiness",
            "/experience learning skill-outcome-lifecycle-plan",
            "/experience learning skill-outcome-lifecycle-doctor",
        ):
            spec = registry.get(prefix)
            if (
                spec is None
                or not spec.read_only
                or spec.mutates != "none"
                or spec.risk != "low"
            ):
                issues.append(f"Registry metadata for {prefix} is missing or unsafe.")
        if PROCEDURAL_SKILL_EXECUTION_INSTALLED:
            issues.append("Procedural skill execution must remain disabled.")
        if any(
            item.prefix.startswith("/experience learning apply skill-outcome")
            or item.prefix.startswith("/experience learning apply skill-lifecycle")
            for item in COMMAND_REGISTRY
        ):
            issues.append("A skill outcome lifecycle apply command is unexpectedly registered.")

        counts = Counter(report.status for report in reports)
        decisions = Counter(report.decision for report in reports)
        status = "ERROR" if issues else "WARN" if warnings else "OK"
        return ProceduralSkillLifecycleReadinessDoctorReport(
            status=status,
            receipt_count=len(reports),
            ready_count=sum(report.ready_for_design_review for report in reports),
            not_ready_count=sum(not report.ready_for_design_review for report in reports),
            error_count=counts["ERROR"],
            keep_count=decisions["keep"],
            revise_count=decisions["revise"],
            archive_count=decisions["archive"],
            issues=_dedupe(issues),
            warnings=_dedupe(warnings),
        )


def format_procedural_skill_lifecycle_readiness_command(
    command: str,
    *,
    reviewer: ProceduralSkillLifecycleApplyReadiness,
    session: OperatorReviewedProceduralSkillOutcomeDecisionSession,
) -> str | None:
    raw = command.strip()
    normalized = " ".join(raw.lower().split())
    prefixes = (
        "/experience learning skill-outcome-lifecycle-readiness",
        "/experience learning skill-outcome-lifecycle-plan",
        "/experience learning skill-outcome-lifecycle-doctor",
    )
    lowered = raw.lower()
    if not any(
        lowered.startswith(prefix)
        and (len(lowered) == len(prefix) or lowered[len(prefix)] in " \t\n;&|")
        for prefix in prefixes
    ):
        return None
    if any(marker in raw for marker in ("\n", ";", "&&", "||")):
        return _readiness_error("Command chaining and multi-command input are not allowed.")
    try:
        if normalized == "/experience learning skill-outcome-lifecycle-doctor":
            return format_procedural_skill_lifecycle_readiness_doctor(
                reviewer.doctor(session)
            )
        for suffix in ("readiness", "plan"):
            prefix = f"/experience learning skill-outcome-lifecycle-{suffix}"
            if normalized == prefix:
                return f"Usage: {prefix} <skill_id|decision_receipt_id>"
            if normalized.startswith(prefix + " "):
                identifier = raw[len(prefix) :].strip()
                if not identifier or " " in identifier:
                    return f"Usage: {prefix} <skill_id|decision_receipt_id>"
                receipt = session.get(identifier)
                if receipt is None:
                    return _readiness_error(
                        f"No process-memory skill outcome decision matches {identifier!r}."
                    )
                report = reviewer.review(receipt)
                return (
                    format_procedural_skill_lifecycle_readiness(report)
                    if suffix == "readiness"
                    else format_procedural_skill_lifecycle_plan(report)
                )
    except (OSError, TypeError, ValueError, ProceduralSkillLifecycleReadinessError) as exc:
        return _readiness_error(str(exc))
    return None


def format_procedural_skill_lifecycle_readiness(
    report: ProceduralSkillLifecycleReadinessReport,
) -> str:
    lines = [
        "Proto-Mind Procedural Skill Lifecycle Apply Readiness v1",
        f"Status: {report.status}",
        f"decision_receipt_id: {report.decision_receipt_id}",
        f"skill_id: {report.skill_id}",
        f"decision: {report.decision}",
        f"outcome_status: {report.outcome_status}",
        f"provenance_id: {report.provenance_id}",
        f"stored_decision_hash: {report.stored_decision_hash}",
        f"current_decision_hash: {report.current_decision_hash or 'unavailable'}",
        f"skill_store_path: {report.skill_store_path}",
        f"skill_store_sha256: {report.skill_store_sha256}",
        f"skill_record_hash: {report.skill_record_hash or 'unavailable'}",
        "future_apply_ready: false",
        "apply_token_generated: false",
        "executable: false",
        "Checks:",
    ]
    lines.extend(f"- {name}: {str(value).lower()}" for name, value in report.checks.items())
    lines.extend(f"- BLOCKER: {issue}" for issue in report.issues)
    lines.extend(f"- WARN: {warning}" for warning in report.warnings)
    lines.extend(_readiness_boundary())
    return "\n".join(lines)


def format_procedural_skill_lifecycle_plan(
    report: ProceduralSkillLifecycleReadinessReport,
) -> str:
    contract = report.contract
    lines = [
        "Proto-Mind Procedural Skill Future Lifecycle Plan v1",
        f"Status: {report.status}",
        f"decision_receipt_id: {report.decision_receipt_id}",
        f"skill_id: {report.skill_id}",
        f"decision: {contract.decision}",
        f"operation: {contract.operation}",
        f"current_status_required: {contract.current_status_required}",
        f"future_target_status: {contract.future_target_status}",
        f"expected_skill_record_mutations: {contract.expected_skill_record_mutations}",
        f"direct_lifecycle_apply_allowed: {str(contract.direct_lifecycle_apply_allowed).lower()}",
        f"revision_payload_required: {str(contract.revision_payload_required).lower()}",
        f"preserve_original_until_verified: {str(contract.preserve_original_until_verified).lower()}",
        "separate_confirmation_required: true",
        f"atomic_write_required: {str(contract.atomic_write_required).lower()}",
        "post_write_verification_required: true",
        f"rollback_suggestion: {contract.rollback_suggestion}",
        "Required future receipt fields:",
    ]
    lines.extend(f"- {field}" for field in contract.future_receipt_fields)
    lines.extend(f"- BLOCKER: {issue}" for issue in report.issues)
    lines.extend(_readiness_boundary())
    return "\n".join(lines)


def format_procedural_skill_lifecycle_readiness_doctor(
    report: ProceduralSkillLifecycleReadinessDoctorReport,
) -> str:
    lines = [
        "Proto-Mind Procedural Skill Lifecycle Apply Readiness Doctor v1",
        f"Status: {report.status}",
        f"mode: {PROCEDURAL_SKILL_LIFECYCLE_READINESS_MODE}",
        f"decision_receipts: {report.receipt_count}",
        f"ready: {report.ready_count}",
        f"not_ready: {report.not_ready_count}",
        f"errors: {report.error_count}",
        f"keep: {report.keep_count}",
        f"revise: {report.revise_count}",
        f"archive: {report.archive_count}",
        "future_apply_ready: false",
        "apply_token_generated: false",
        "procedure_execution_enabled: false",
    ]
    lines.extend(f"- ERROR: {issue}" for issue in report.issues)
    lines.extend(f"- WARN: {warning}" for warning in report.warnings)
    if not report.issues and not report.warnings:
        lines.append(
            "- Decision, evidence, captures, provenance, skill bytes, Registry, and future safeguards are current."
        )
    lines.extend(_readiness_boundary())
    return "\n".join(lines)


def _contract_for(decision: str, skill_id: str) -> ProceduralSkillLifecycleContract:
    common = {
        "decision": decision,
        "current_status_required": "active",
        "separate_confirmation_required": True,
        "post_write_verification_required": True,
        "future_receipt_fields": list(PROCEDURAL_SKILL_LIFECYCLE_FUTURE_RECEIPT_FIELDS),
    }
    if decision == "keep":
        return ProceduralSkillLifecycleContract(
            **common,
            operation="record a verified keep receipt without rewriting the skill record",
            expected_skill_record_mutations=0,
            future_target_status="active",
            direct_lifecycle_apply_allowed=True,
            atomic_write_required=False,
            revision_payload_required=False,
            preserve_original_until_verified=True,
            rollback_suggestion="not applicable; the skill record must remain byte-identical",
        )
    if decision == "archive":
        return ProceduralSkillLifecycleContract(
            **common,
            operation="atomically change exactly one skill status from active to archived",
            expected_skill_record_mutations=1,
            future_target_status="archived",
            direct_lifecycle_apply_allowed=True,
            atomic_write_required=True,
            revision_payload_required=False,
            preserve_original_until_verified=True,
            rollback_suggestion=f"/skills restore {skill_id}",
        )
    return ProceduralSkillLifecycleContract(
        **common,
        operation="author a separate versioned replacement before any lifecycle mutation",
        expected_skill_record_mutations=0,
        future_target_status="active until a separately verified replacement exists",
        direct_lifecycle_apply_allowed=False,
        atomic_write_required=False,
        revision_payload_required=True,
        preserve_original_until_verified=True,
        rollback_suggestion="manual review required; no in-place revision is permitted",
    )


def _contract_is_safe(contract: ProceduralSkillLifecycleContract) -> bool:
    if contract.decision == "keep":
        return bool(
            contract.expected_skill_record_mutations == 0
            and contract.future_target_status == "active"
            and contract.direct_lifecycle_apply_allowed
            and not contract.atomic_write_required
            and not contract.revision_payload_required
        )
    if contract.decision == "archive":
        return bool(
            contract.expected_skill_record_mutations == 1
            and contract.future_target_status == "archived"
            and contract.direct_lifecycle_apply_allowed
            and contract.atomic_write_required
            and not contract.revision_payload_required
            and contract.rollback_suggestion.startswith("/skills restore ")
        )
    return bool(
        contract.decision == "revise"
        and contract.expected_skill_record_mutations == 0
        and not contract.direct_lifecycle_apply_allowed
        and contract.revision_payload_required
        and contract.preserve_original_until_verified
    )


def _receipt_is_safe(receipt: ProceduralSkillOutcomeDecisionReceipt) -> bool:
    return bool(
        receipt.id == f"skilloutdec_{receipt.decision_hash[:16]}"
        and receipt.confirmation_method
        == "exact_current_skill_outcome_decision_token"
        and len(receipt.confirmation_token_hash) == 64
        and receipt.operator_confirmation_recorded
        and receipt.terminal_process_decision
        and receipt.process_memory_only
        and receipt.restart_expiring
        and not receipt.future_apply_ready
        and not receipt.skill_mutation_performed
        and not receipt.memory_mutation_performed
        and not receipt.experience_mutation_performed
        and not receipt.persistence_performed
        and not receipt.procedure_execution_performed
        and bool(receipt.capture_receipt_ids)
        and len(receipt.capture_receipt_ids) == len(receipt.capture_receipt_hashes)
        and all(len(value) == 64 for value in receipt.capture_receipt_hashes)
    )


def _valid_skill_record(record: dict[str, Any]) -> bool:
    return bool(
        str(record.get("id") or "").strip()
        and record.get("status") in {"active", "archived"}
        and all(
            isinstance(record.get(field, ""), str)
            for field in ("name", "summary", "body")
        )
    )


def _hash_file(path: Path) -> str:
    try:
        payload = path.read_bytes() if path.exists() else b""
    except OSError:
        return "unavailable"
    return hashlib.sha256(payload).hexdigest()


def _hash_json(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _readiness_error(message: str) -> str:
    return "\n".join(
        [
            "Proto-Mind Procedural Skill Lifecycle Apply Readiness Error",
            "Status: ERROR",
            f"- {message}",
            *_readiness_boundary(),
        ]
    )


def _readiness_boundary() -> list[str]:
    return [
        "Boundary:",
        "- Read-only design readiness only; no lifecycle apply token or apply command exists.",
        "- No skill, memory, Experience event, receipt, queue, export, session log, or Context Injection changed.",
        "- No procedure, shell, arbitrary command, model/API, external action, writer, or background task ran.",
    ]


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))
