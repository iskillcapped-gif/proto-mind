from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
from typing import Any

from proto_mind.command_registry import COMMAND_REGISTRY
from proto_mind.experience_learning_skill_runtime import (
    PROCEDURAL_SKILL_EXECUTION_INSTALLED,
)
from proto_mind.skill_library import SkillLibrary
from proto_mind.skill_lifecycle_audit import (
    ProceduralSkillLifecycleAudit,
    ProceduralSkillLifecycleAuditError,
)
from proto_mind.skill_lifecycle_restore import (
    PROCEDURAL_SKILL_LIFECYCLE_RESTORE_EXPECTED_CHANGED_FIELDS,
    PROCEDURAL_SKILL_LIFECYCLE_RESTORE_RECEIPT_FIELDS,
    verify_procedural_skill_lifecycle_restore_metadata,
)


PROCEDURAL_SKILL_RESTORE_RECEIPT_AUDIT_VERSION = 1
PROCEDURAL_SKILL_RESTORE_RECEIPT_AUDIT_SCHEMA = (
    "skill.procedure.lifecycle.restore.receipt.evidence.v1"
)
PROCEDURAL_SKILL_RESTORE_RECEIPT_AUDIT_MODE = (
    "read_only_restart_safe_restore_receipt_evidence_without_receipt_invention"
)
PROCEDURAL_SKILL_RESTORE_RECEIPT_AUDIT_WRITER_INSTALLED = False
PROCEDURAL_SKILL_RESTORE_RECEIPT_EXPORT_WRITER_INSTALLED = False
PROCEDURAL_SKILL_RESTORE_PROCESS_RECEIPT_PERSISTENCE_INSTALLED = False

PROCEDURAL_SKILL_RESTORE_RECEIPT_EVIDENCE_FIELDS = (
    "version",
    "schema",
    "id",
    "skill_id",
    "current_status",
    "audit_state",
    "restore_metadata_id",
    "restore_metadata_hash",
    "transitioned_at",
    "prior_archive_id",
    "prior_archive_hash",
    "restore_review_hash",
    "before_record_hash",
    "confirmation_token_hash",
    "current_record_hash",
    "skill_provenance_id",
    "source",
    "original_apply_receipt_reconstructed",
    "process_receipt_persisted",
    "evidence_hash",
)
PROCEDURAL_SKILL_RESTORE_DURABLY_RECOVERABLE_RECEIPT_FIELDS = (
    "applied_at",
    "skill_id",
    "restore_review_hash",
    "restore_metadata_id",
    "restore_metadata_hash",
    "prior_archive_id",
    "prior_archive_hash",
    "before_record_hash",
    "after_record_hash",
    "confirmation_token_hash",
)
PROCEDURAL_SKILL_RESTORE_PROCESS_ONLY_RECEIPT_FIELDS = tuple(
    field
    for field in PROCEDURAL_SKILL_LIFECYCLE_RESTORE_RECEIPT_FIELDS
    if field not in PROCEDURAL_SKILL_RESTORE_DURABLY_RECOVERABLE_RECEIPT_FIELDS
)


@dataclass(frozen=True)
class ProceduralSkillRestoreReceiptEvidenceCheck:
    status: str
    verified: bool
    evidence_id: str
    skill_id: str
    hash_verified: bool
    identity_verified: bool
    issues: list[str]


@dataclass(frozen=True)
class ProceduralSkillRestoreReceiptAuditEntry:
    status: str
    skill_id: str
    current_status: str
    audit_state: str
    restore_metadata_id: str
    restore_metadata_hash: str
    evidence_id: str
    evidence_hash: str
    process_receipt_status: str
    process_receipt_id: str
    process_receipt_hash: str
    durably_recoverable_receipt_fields: list[str]
    process_only_receipt_fields: list[str]
    current_state_verified: bool
    restart_safe: bool
    original_apply_receipt_reconstructed: bool
    process_receipt_persisted: bool
    mutation_performed: bool
    evidence: dict[str, Any]
    issues: list[str]
    warnings: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ProceduralSkillRestoreReceiptAuditReport:
    status: str
    skills_path: str
    total_skills: int
    durable_restore_count: int
    verified_evidence_count: int
    process_receipt_count: int
    matched_process_receipt_count: int
    unavailable_process_receipt_count: int
    legacy_process_receipt_count: int
    orphan_process_receipt_count: int
    entries: list[ProceduralSkillRestoreReceiptAuditEntry]
    issues: list[str]
    warnings: list[str]
    mutation_performed: bool = False
    receipt_history_invented: bool = False


class ProceduralSkillRestoreReceiptAuditError(RuntimeError):
    pass


class ProceduralSkillRestoreReceiptAudit:
    """Reconstructs only receipt evidence preserved in current durable stores."""

    def __init__(
        self,
        *,
        skills_path: Path,
        persistent_memory_path: Path,
        process_receipts: tuple[dict[str, Any], ...] = (),
    ) -> None:
        self.skills_path = Path(skills_path)
        self.persistent_memory_path = Path(persistent_memory_path)
        self.process_receipts = tuple(deepcopy(process_receipts))

    def inspect(self) -> ProceduralSkillRestoreReceiptAuditReport:
        snapshot = SkillLibrary(self.skills_path).read_snapshot()
        if snapshot["error"]:
            raise ProceduralSkillRestoreReceiptAuditError(
                f"Skill Library is unreadable: {snapshot['error']}"
            )
        if snapshot["malformed_count"]:
            raise ProceduralSkillRestoreReceiptAuditError(
                "Skill Library contains "
                f"{snapshot['malformed_count']} malformed JSONL record(s)."
            )
        try:
            lifecycle = ProceduralSkillLifecycleAudit(
                skills_path=self.skills_path,
                persistent_memory_path=self.persistent_memory_path,
            ).inspect()
        except ProceduralSkillLifecycleAuditError as exc:
            raise ProceduralSkillRestoreReceiptAuditError(str(exc)) from exc

        lifecycle_by_id = {entry.skill_id: entry for entry in lifecycle.entries}
        entries = [
            self._entry(record, lifecycle_by_id.get(str(record.get("id") or "")))
            for record in snapshot["records"]
            if isinstance(record.get("lifecycle"), dict)
            and record["lifecycle"].get("schema")
            == "skill.procedure.lifecycle.restore.v1"
        ]
        issues: list[str] = []
        warnings: list[str] = []
        for entry in entries:
            issues.extend(f"{entry.skill_id}: {item}" for item in entry.issues)
            warnings.extend(f"{entry.skill_id}: {item}" for item in entry.warnings)

        matched_keys = {
            value
            for entry in entries
            for value in (entry.skill_id, entry.restore_metadata_id)
            if value
        }
        orphan_receipts = [
            receipt
            for receipt in self.process_receipts
            if str(receipt.get("skill_id") or "") not in matched_keys
            and str(receipt.get("restore_metadata_id") or "") not in matched_keys
        ]
        legacy_receipts = [
            receipt
            for receipt in self.process_receipts
            if set(receipt) != set(PROCEDURAL_SKILL_LIFECYCLE_RESTORE_RECEIPT_FIELDS)
        ]
        for receipt in orphan_receipts:
            warnings.append(
                "Process receipt "
                f"{receipt.get('restore_apply_id') or '<missing>'} has no current durable restore envelope."
            )
        for receipt in legacy_receipts:
            warnings.append(
                "Process receipt "
                f"{receipt.get('restore_apply_id') or '<missing>'} is legacy or incomplete."
            )

        contract_issues = _receipt_audit_contract_issues()
        issues.extend(contract_issues)
        matched = sum(entry.process_receipt_status == "MATCHED" for entry in entries)
        unavailable = sum(
            entry.process_receipt_status == "NOT_AVAILABLE" for entry in entries
        )
        status = "ERROR" if issues else "WARN" if warnings else "OK"
        return ProceduralSkillRestoreReceiptAuditReport(
            status=status,
            skills_path=str(self.skills_path),
            total_skills=len(snapshot["records"]),
            durable_restore_count=len(entries),
            verified_evidence_count=sum(entry.status == "VERIFIED" for entry in entries),
            process_receipt_count=len(self.process_receipts),
            matched_process_receipt_count=matched,
            unavailable_process_receipt_count=unavailable,
            legacy_process_receipt_count=len(legacy_receipts),
            orphan_process_receipt_count=len(orphan_receipts),
            entries=entries,
            issues=_dedupe(issues),
            warnings=_dedupe(warnings),
        )

    def get(self, skill_id: str) -> ProceduralSkillRestoreReceiptAuditEntry | None:
        return next(
            (entry for entry in self.inspect().entries if entry.skill_id == skill_id),
            None,
        )

    def _entry(
        self,
        record: dict[str, Any],
        lifecycle_entry: Any,
    ) -> ProceduralSkillRestoreReceiptAuditEntry:
        skill_id = str(record.get("id") or "")
        metadata = record.get("lifecycle")
        metadata_check = verify_procedural_skill_lifecycle_restore_metadata(metadata)
        issues = list(metadata_check.issues)
        warnings: list[str] = []
        audit_state = str(getattr(lifecycle_entry, "state", "invalid"))
        restart_safe = bool(getattr(lifecycle_entry, "restart_safe", False))
        if audit_state != "active_restored_verified":
            issues.append(
                "Current lifecycle audit does not recover active_restored_verified."
            )
        if record.get("status") != "active":
            issues.append("Durable restore evidence requires current active status.")

        evidence: dict[str, Any] = {}
        evidence_check = ProceduralSkillRestoreReceiptEvidenceCheck(
            status="ERROR",
            verified=False,
            evidence_id="",
            skill_id=skill_id,
            hash_verified=False,
            identity_verified=False,
            issues=["Durable restore metadata is invalid."],
        )
        if metadata_check.verified and not issues:
            evidence = build_procedural_skill_restore_receipt_evidence(record)
            evidence_check = verify_procedural_skill_restore_receipt_evidence(evidence)
            issues.extend(evidence_check.issues)

        matches = [
            receipt
            for receipt in self.process_receipts
            if skill_id
            in {
                str(receipt.get("skill_id") or ""),
                str(receipt.get("restore_metadata_id") or ""),
            }
            or str(metadata.get("id") or "")
            == str(receipt.get("restore_metadata_id") or "")
        ]
        process_status = "NOT_AVAILABLE"
        process_id = ""
        process_hash = ""
        if len(matches) > 1:
            process_status = "INVALID"
            issues.append("Multiple process receipts match one durable restore envelope.")
        elif matches:
            receipt = matches[0]
            process_id = str(receipt.get("restore_apply_id") or "")
            process_hash = str(receipt.get("receipt_hash") or "")
            receipt_issues = _process_receipt_issues(receipt, record, metadata)
            if set(receipt) != set(PROCEDURAL_SKILL_LIFECYCLE_RESTORE_RECEIPT_FIELDS):
                process_status = "LEGACY"
                warnings.extend(receipt_issues)
                warnings.append(
                    "Current process receipt is legacy/incomplete; durable evidence remains independently inspectable."
                )
            elif receipt_issues:
                process_status = "MISMATCH"
                issues.extend(receipt_issues)
            else:
                process_status = "MATCHED"

        return ProceduralSkillRestoreReceiptAuditEntry(
            status="VERIFIED" if not issues and evidence_check.verified else "ERROR",
            skill_id=skill_id,
            current_status=str(record.get("status") or "unknown"),
            audit_state=audit_state,
            restore_metadata_id=str(metadata.get("id") or "")
            if isinstance(metadata, dict)
            else "",
            restore_metadata_hash=str(metadata.get("metadata_hash") or "")
            if isinstance(metadata, dict)
            else "",
            evidence_id=str(evidence.get("id") or ""),
            evidence_hash=str(evidence.get("evidence_hash") or ""),
            process_receipt_status=process_status,
            process_receipt_id=process_id,
            process_receipt_hash=process_hash,
            durably_recoverable_receipt_fields=list(
                PROCEDURAL_SKILL_RESTORE_DURABLY_RECOVERABLE_RECEIPT_FIELDS
            ),
            process_only_receipt_fields=list(
                PROCEDURAL_SKILL_RESTORE_PROCESS_ONLY_RECEIPT_FIELDS
            ),
            current_state_verified=not issues and evidence_check.verified,
            restart_safe=restart_safe and evidence_check.verified,
            original_apply_receipt_reconstructed=False,
            process_receipt_persisted=False,
            mutation_performed=False,
            evidence=evidence,
            issues=_dedupe(issues),
            warnings=_dedupe(warnings),
        )


def build_procedural_skill_restore_receipt_evidence(
    record: dict[str, Any],
) -> dict[str, Any]:
    metadata = record.get("lifecycle")
    check = verify_procedural_skill_lifecycle_restore_metadata(metadata)
    if not check.verified or not isinstance(metadata, dict):
        raise ValueError("Current skill lacks verified durable restore metadata.")
    if record.get("status") != "active" or record.get("id") != metadata.get("skill_id"):
        raise ValueError("Current skill does not match the active restore envelope.")
    provenance = record.get("provenance")
    provenance_id = str(provenance.get("id") or "") if isinstance(provenance, dict) else ""
    material = {
        "version": PROCEDURAL_SKILL_RESTORE_RECEIPT_AUDIT_VERSION,
        "schema": PROCEDURAL_SKILL_RESTORE_RECEIPT_AUDIT_SCHEMA,
        "skill_id": str(record.get("id") or ""),
        "current_status": str(record.get("status") or ""),
        "audit_state": "active_restored_verified",
        "restore_metadata_id": str(metadata.get("id") or ""),
        "restore_metadata_hash": str(metadata.get("metadata_hash") or ""),
        "transitioned_at": str(metadata.get("transitioned_at") or ""),
        "prior_archive_id": str(metadata.get("prior_archive_id") or ""),
        "prior_archive_hash": str(metadata.get("prior_archive_hash") or ""),
        "restore_review_hash": str(metadata.get("restore_review_hash") or ""),
        "before_record_hash": str(metadata.get("before_record_hash") or ""),
        "confirmation_token_hash": str(metadata.get("confirmation_token_hash") or ""),
        "current_record_hash": _hash_json(record),
        "skill_provenance_id": provenance_id,
        "source": "embedded_verified_restore_envelope",
        "original_apply_receipt_reconstructed": False,
        "process_receipt_persisted": False,
    }
    identity_hash = _hash_json(material)
    payload = {**material, "id": f"skillrestoreevidence_{identity_hash[:16]}"}
    payload["evidence_hash"] = _hash_json(payload)
    verified = verify_procedural_skill_restore_receipt_evidence(payload)
    if not verified.verified:
        raise ValueError("; ".join(verified.issues))
    return payload


def verify_procedural_skill_restore_receipt_evidence(
    value: Any,
) -> ProceduralSkillRestoreReceiptEvidenceCheck:
    payload = dict(value) if isinstance(value, dict) else {}
    issues: list[str] = []
    if not isinstance(value, dict):
        issues.append("Restore receipt evidence must be an object.")
    missing = sorted(set(PROCEDURAL_SKILL_RESTORE_RECEIPT_EVIDENCE_FIELDS) - set(payload))
    unexpected = sorted(set(payload) - set(PROCEDURAL_SKILL_RESTORE_RECEIPT_EVIDENCE_FIELDS))
    if missing:
        issues.append(f"Missing receipt evidence fields: {', '.join(missing)}.")
    if unexpected:
        issues.append(f"Unexpected receipt evidence fields: {', '.join(unexpected)}.")
    if payload.get("version") != PROCEDURAL_SKILL_RESTORE_RECEIPT_AUDIT_VERSION:
        issues.append("Restore receipt evidence version is unsupported.")
    if payload.get("schema") != PROCEDURAL_SKILL_RESTORE_RECEIPT_AUDIT_SCHEMA:
        issues.append("Restore receipt evidence schema is unsupported.")
    if payload.get("current_status") != "active":
        issues.append("Restore receipt evidence current status must be active.")
    if payload.get("audit_state") != "active_restored_verified":
        issues.append("Restore receipt evidence audit state is invalid.")
    if payload.get("source") != "embedded_verified_restore_envelope":
        issues.append("Restore receipt evidence source is invalid.")
    for field in ("original_apply_receipt_reconstructed", "process_receipt_persisted"):
        if payload.get(field) is not False:
            issues.append(f"Restore receipt evidence safety field {field} must be false.")
    for field in (
        "restore_metadata_hash",
        "prior_archive_hash",
        "restore_review_hash",
        "before_record_hash",
        "confirmation_token_hash",
        "current_record_hash",
        "evidence_hash",
    ):
        if not _is_sha256(payload.get(field)):
            issues.append(f"Restore receipt evidence field {field} must be SHA-256.")
    for field in (
        "skill_id",
        "restore_metadata_id",
        "transitioned_at",
        "prior_archive_id",
        "skill_provenance_id",
    ):
        if not isinstance(payload.get(field), str) or not payload.get(field):
            issues.append(f"Restore receipt evidence field {field} must be non-empty text.")

    identity_material = {
        key: payload.get(key)
        for key in PROCEDURAL_SKILL_RESTORE_RECEIPT_EVIDENCE_FIELDS
        if key not in {"id", "evidence_hash"}
    }
    expected_id = f"skillrestoreevidence_{_hash_json(identity_material)[:16]}"
    identity_verified = payload.get("id") == expected_id
    if not identity_verified:
        issues.append("Restore receipt evidence identity hash does not verify.")
    expected_hash = _hash_json(
        {
            key: payload.get(key)
            for key in PROCEDURAL_SKILL_RESTORE_RECEIPT_EVIDENCE_FIELDS
            if key != "evidence_hash"
        }
    )
    hash_verified = payload.get("evidence_hash") == expected_hash
    if not hash_verified:
        issues.append("Restore receipt evidence hash does not verify.")
    return ProceduralSkillRestoreReceiptEvidenceCheck(
        status="VERIFIED" if not issues else "ERROR",
        verified=not issues,
        evidence_id=str(payload.get("id") or ""),
        skill_id=str(payload.get("skill_id") or ""),
        hash_verified=hash_verified,
        identity_verified=identity_verified,
        issues=_dedupe(issues),
    )


def format_procedural_skill_restore_receipt_audit_command(
    command: str,
    *,
    skills_path: Path,
    persistent_memory_path: Path,
    process_receipts: tuple[dict[str, Any], ...] = (),
) -> str | None:
    raw = command.strip()
    normalized = " ".join(raw.lower().split())
    recognized = bool(
        normalized == "/skills lifecycle-status --restore-receipt-contract"
        or normalized == "/skills lifecycle-history --restore-receipts"
        or normalized == "/skills lifecycle-doctor --restore-receipts"
        or normalized.startswith("/skills lifecycle-inspect ")
        and any(
            flag in normalized
            for flag in ("--restore-receipt-audit", "--restore-receipt-export")
        )
    )
    if not recognized:
        return None
    if any(marker in raw for marker in ("\n", ";", "&&", "||", "|")):
        return _audit_error("Command chaining and multi-command input are not allowed.")
    if normalized == "/skills lifecycle-status --restore-receipt-contract":
        return format_procedural_skill_restore_receipt_contract()
    audit = ProceduralSkillRestoreReceiptAudit(
        skills_path=skills_path,
        persistent_memory_path=persistent_memory_path,
        process_receipts=process_receipts,
    )
    try:
        report = audit.inspect()
    except ProceduralSkillRestoreReceiptAuditError as exc:
        return _audit_error(str(exc))
    if normalized == "/skills lifecycle-history --restore-receipts":
        return format_procedural_skill_restore_receipt_history(report)
    if normalized == "/skills lifecycle-doctor --restore-receipts":
        return format_procedural_skill_restore_receipt_doctor(report)
    parts = raw.split()
    if len(parts) != 4:
        return _audit_usage()
    entry = next((item for item in report.entries if item.skill_id == parts[2]), None)
    if parts[3].lower() == "--restore-receipt-audit":
        return format_procedural_skill_restore_receipt_inspect(entry, parts[2])
    if parts[3].lower() == "--restore-receipt-export":
        return format_procedural_skill_restore_receipt_export(entry, parts[2])
    return _audit_usage()


def format_procedural_skill_restore_receipt_contract() -> str:
    return "\n".join(
        [
            "Proto-Mind Durable Restore Receipt Evidence Contract v1",
            "Status: DESIGN LOCKED",
            f"mode: {PROCEDURAL_SKILL_RESTORE_RECEIPT_AUDIT_MODE}",
            f"schema: {PROCEDURAL_SKILL_RESTORE_RECEIPT_AUDIT_SCHEMA}",
            f"evidence_fields: {', '.join(PROCEDURAL_SKILL_RESTORE_RECEIPT_EVIDENCE_FIELDS)}",
            "durably_recoverable_receipt_fields: "
            + ", ".join(PROCEDURAL_SKILL_RESTORE_DURABLY_RECOVERABLE_RECEIPT_FIELDS),
            "process_only_receipt_fields: "
            + ", ".join(PROCEDURAL_SKILL_RESTORE_PROCESS_ONLY_RECEIPT_FIELDS),
            "original_apply_receipt_reconstructed: false",
            "process_receipt_persisted: false",
            "export_writer_installed: false",
            *_audit_boundary(),
        ]
    )


def format_procedural_skill_restore_receipt_history(
    report: ProceduralSkillRestoreReceiptAuditReport,
) -> str:
    lines = [
        "Proto-Mind Durable Restore Receipt Evidence History v1",
        f"Status: {report.status}",
        f"durable_restore_records: {report.durable_restore_count}",
        f"verified_evidence: {report.verified_evidence_count}",
        "Evidence:",
    ]
    if not report.entries:
        lines.append("- none")
    for entry in report.entries:
        lines.append(
            f"- {entry.skill_id} | {entry.status} | {entry.evidence_id or 'unavailable'} | "
            f"process_receipt={entry.process_receipt_status}"
        )
    lines.extend(_audit_boundary())
    return "\n".join(lines)


def format_procedural_skill_restore_receipt_inspect(
    entry: ProceduralSkillRestoreReceiptAuditEntry | None,
    identifier: str,
) -> str:
    if entry is None:
        return _audit_error(f"Durable restore evidence for skill {identifier!r} was not found.")
    lines = [
        "Proto-Mind Durable Restore Receipt Evidence Inspection v1",
        f"Status: {entry.status}",
    ]
    lines.extend(
        f"{key}: {_compact(value)}"
        for key, value in entry.to_dict().items()
        if key != "evidence"
    )
    lines.extend(_audit_boundary())
    return "\n".join(lines)


def format_procedural_skill_restore_receipt_export(
    entry: ProceduralSkillRestoreReceiptAuditEntry | None,
    identifier: str,
) -> str:
    if entry is None:
        return _audit_error(f"Durable restore evidence for skill {identifier!r} was not found.")
    if entry.status != "VERIFIED" or not entry.evidence:
        return _audit_error("Durable restore receipt evidence does not verify for export.")
    return "\n".join(
        [
            "Proto-Mind Durable Restore Receipt Evidence Export v1",
            "Status: VERIFIED",
            "format: copyable_json",
            "file_written: false",
            "Evidence JSON:",
            json.dumps(entry.evidence, ensure_ascii=False, indent=2, sort_keys=True),
            *_audit_boundary(),
        ]
    )


def format_procedural_skill_restore_receipt_doctor(
    report: ProceduralSkillRestoreReceiptAuditReport,
) -> str:
    lines = [
        "Proto-Mind Durable Restore Receipt Audit Doctor v1",
        f"Status: {report.status}",
        f"mode: {PROCEDURAL_SKILL_RESTORE_RECEIPT_AUDIT_MODE}",
        f"durable_restore_records: {report.durable_restore_count}",
        f"verified_evidence: {report.verified_evidence_count}",
        f"process_receipts: {report.process_receipt_count}",
        f"matched_process_receipts: {report.matched_process_receipt_count}",
        f"process_receipts_unavailable_after_restart: {report.unavailable_process_receipt_count}",
        f"legacy_process_receipts: {report.legacy_process_receipt_count}",
        f"orphan_process_receipts: {report.orphan_process_receipt_count}",
        "receipt_history_invented: false",
        "mutation_performed: false",
        "writer_installed: false",
        "export_writer_installed: false",
        "process_receipt_persistence_installed: false",
    ]
    lines.extend(f"- ERROR: {issue}" for issue in report.issues)
    lines.extend(f"- WARN: {warning}" for warning in report.warnings)
    if not report.issues and not report.warnings:
        lines.append(
            "- Durable restore envelopes, evidence reconstruction, process-receipt comparison, Registry, and no-invention boundaries are healthy."
        )
    lines.extend(_audit_boundary())
    return "\n".join(lines)


def _process_receipt_issues(
    receipt: dict[str, Any],
    record: dict[str, Any],
    metadata: dict[str, Any],
) -> list[str]:
    issues: list[str] = []
    if set(receipt) != set(PROCEDURAL_SKILL_LIFECYCLE_RESTORE_RECEIPT_FIELDS):
        missing = sorted(set(PROCEDURAL_SKILL_LIFECYCLE_RESTORE_RECEIPT_FIELDS) - set(receipt))
        return [f"Process receipt lacks fixed fields: {', '.join(missing) or 'unknown' }."]
    expected_hash = _hash_json(
        {key: value for key, value in receipt.items() if key != "receipt_hash"}
    )
    if receipt.get("receipt_hash") != expected_hash:
        issues.append("Process receipt hash does not verify.")
    comparisons = {
        "skill_id": record.get("id"),
        "restore_metadata_id": metadata.get("id"),
        "restore_metadata_hash": metadata.get("metadata_hash"),
        "prior_archive_id": metadata.get("prior_archive_id"),
        "prior_archive_hash": metadata.get("prior_archive_hash"),
        "restore_review_hash": metadata.get("restore_review_hash"),
        "before_record_hash": metadata.get("before_record_hash"),
        "confirmation_token_hash": metadata.get("confirmation_token_hash"),
        "after_record_hash": _hash_json(record),
    }
    for field, expected in comparisons.items():
        if receipt.get(field) != expected:
            issues.append(f"Process receipt field {field} differs from durable evidence.")
    if receipt.get("changed_fields") != list(
        PROCEDURAL_SKILL_LIFECYCLE_RESTORE_EXPECTED_CHANGED_FIELDS
    ):
        issues.append("Process receipt changed-field scope is invalid.")
    return _dedupe(issues)


def _receipt_audit_contract_issues() -> list[str]:
    registry = {entry.prefix: entry for entry in COMMAND_REGISTRY}
    issues: list[str] = []
    for prefix in (
        "/skills lifecycle-status",
        "/skills lifecycle-history",
        "/skills lifecycle-inspect",
        "/skills lifecycle-doctor",
    ):
        spec = registry.get(prefix)
        if spec is None or not spec.read_only or spec.mutates != "none" or spec.risk != "low":
            issues.append(f"Registry metadata for {prefix} is missing or unsafe.")
    if PROCEDURAL_SKILL_RESTORE_RECEIPT_AUDIT_WRITER_INSTALLED:
        issues.append("Restore receipt audit writer must remain disabled.")
    if PROCEDURAL_SKILL_RESTORE_RECEIPT_EXPORT_WRITER_INSTALLED:
        issues.append("Restore receipt export writer must remain disabled.")
    if PROCEDURAL_SKILL_RESTORE_PROCESS_RECEIPT_PERSISTENCE_INSTALLED:
        issues.append("Process receipt persistence must remain disabled.")
    if PROCEDURAL_SKILL_EXECUTION_INSTALLED:
        issues.append("Procedural skill execution must remain disabled.")
    example = {
        "version": 1,
        "schema": PROCEDURAL_SKILL_RESTORE_RECEIPT_AUDIT_SCHEMA,
        "skill_id": "skill_example",
        "current_status": "active",
        "audit_state": "active_restored_verified",
        "restore_metadata_id": "skillrestore_example",
        "restore_metadata_hash": "1" * 64,
        "transitioned_at": "2026-07-20T00:00:00+00:00",
        "prior_archive_id": "skillarchive_example",
        "prior_archive_hash": "2" * 64,
        "restore_review_hash": "3" * 64,
        "before_record_hash": "4" * 64,
        "confirmation_token_hash": "5" * 64,
        "current_record_hash": "6" * 64,
        "skill_provenance_id": "skillprov_example",
        "source": "embedded_verified_restore_envelope",
        "original_apply_receipt_reconstructed": False,
        "process_receipt_persisted": False,
    }
    identity_hash = _hash_json(example)
    example["id"] = f"skillrestoreevidence_{identity_hash[:16]}"
    example["evidence_hash"] = _hash_json(example)
    if not verify_procedural_skill_restore_receipt_evidence(example).verified:
        issues.append("Deterministic restore receipt evidence example does not verify.")
    tampered = deepcopy(example)
    tampered["skill_id"] = "tampered"
    if verify_procedural_skill_restore_receipt_evidence(tampered).verified:
        issues.append("Restore receipt evidence tamper check failed.")
    return issues


def _audit_usage() -> str:
    return (
        "Usage: /skills lifecycle-status --restore-receipt-contract | "
        "lifecycle-history --restore-receipts | lifecycle-inspect <id> "
        "--restore-receipt-audit|--restore-receipt-export | "
        "lifecycle-doctor --restore-receipts"
    )


def _audit_error(message: str) -> str:
    return "\n".join(
        [
            "Proto-Mind Durable Restore Receipt Audit Error",
            "Status: ERROR",
            f"- {message}",
            *_audit_boundary(),
        ]
    )


def _audit_boundary() -> list[str]:
    return [
        "Boundary:",
        "- Read-only reconstruction from the current verified restore envelope; the original 21-field apply receipt is never invented.",
        "- Copyable JSON is printed only; no receipt or export file is written.",
        "- No skill, memory, event, queue, export, session log, Context Injection, shell, model/API, procedure, or external action changed.",
    ]


def _compact(value: Any) -> str:
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, list):
        return ", ".join(str(item) for item in value) or "none"
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return str(value) if value not in {None, ""} else "none"


def _hash_json(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _is_sha256(value: Any) -> bool:
    text = str(value or "")
    return len(text) == 64 and all(character in "0123456789abcdef" for character in text)


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))
