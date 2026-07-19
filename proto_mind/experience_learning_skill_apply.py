from __future__ import annotations

from collections import Counter
from copy import deepcopy
from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
from threading import RLock
from typing import Any
from uuid import uuid4

from proto_mind.command_registry import COMMAND_REGISTRY
from proto_mind.experience_learning_skill_authoring import (
    OperatorReviewedProceduralSkillAuthoringSession,
    ProceduralSkillAuthoringReceipt,
)
from proto_mind.experience_learning_skill_readiness import ProceduralSkillApplyReadiness
from proto_mind.experience_learning_skill_runtime import (
    PROCEDURAL_SKILL_APPLY_ENGINE_INSTALLED,
    PROCEDURAL_SKILL_EXECUTION_INSTALLED,
)
from proto_mind.memory_provenance import verify_memory_provenance
from proto_mind.models import utc_now_iso
from proto_mind.skill_library import SkillLibrary


PROCEDURAL_SKILL_APPLY_VERSION = 1
PROCEDURAL_SKILL_APPLY_MODE = "single_exact_confirmed_atomic_skill_append"
PROCEDURAL_SKILL_APPLY_MAX_RECEIPTS = 1
PROCEDURAL_SKILL_EXECUTION_ENABLED = PROCEDURAL_SKILL_EXECUTION_INSTALLED


@dataclass(frozen=True)
class ProceduralSkillApplyReview:
    status: str
    authoring_receipt_id: str
    source_lesson_id: str
    created_skill_id: str
    before_store_sha256: str
    target_payload_hash: str
    checks: dict[str, bool]
    issues: list[str]
    warnings: list[str]
    confirmable: bool
    executable: bool = False
    mutation_performed: bool = False


@dataclass(frozen=True)
class ProceduralSkillApplyReceipt:
    id: str
    applied_at: str
    authoring_receipt_id: str
    source_lesson_id: str
    source_provenance_id: str
    source_record_hash: str
    authoring_hash: str
    created_skill_id: str
    before_store_sha256: str
    after_store_sha256: str
    created_record_hash: str
    target_payload_hash: str
    confirmation_method: str
    confirmation_token_hash: str
    record_verified: bool
    source_provenance_verified: bool
    exact_record_mutations: int
    rollback_suggestion: str
    run_once_guard: bool
    apply_result: str
    receipt_persistence: str
    target_execution_performed: bool = False
    executable: bool = False
    skill_mutation_performed: bool = True
    memory_mutation_performed: bool = False
    experience_mutation_performed: bool = False
    batch_apply_performed: bool = False
    receipt_hash: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ProceduralSkillApplyDoctorReport:
    status: str
    receipt_count: int
    verified_current_count: int
    historical_count: int
    issues: list[str]
    warnings: list[str]


class ProceduralSkillApplyError(RuntimeError):
    pass


class OperatorReviewedProceduralSkillApplySession:
    """Applies at most one exact procedural skill record per process."""

    def __init__(self) -> None:
        self._receipts: dict[str, ProceduralSkillApplyReceipt] = {}
        self._lock = RLock()

    def snapshot(self) -> tuple[dict[str, Any], ...]:
        with self._lock:
            return tuple(deepcopy(receipt.to_dict()) for receipt in self._receipts.values())

    def get(self, identifier: str) -> ProceduralSkillApplyReceipt | None:
        with self._lock:
            direct = self._receipts.get(identifier)
            if direct is not None:
                return direct
            return next(
                (
                    receipt
                    for receipt in self._receipts.values()
                    if identifier
                    in {
                        receipt.id,
                        receipt.authoring_receipt_id,
                        receipt.source_lesson_id,
                        receipt.created_skill_id,
                    }
                ),
                None,
            )

    def review(
        self,
        receipt: ProceduralSkillAuthoringReceipt,
        *,
        reviewer: ProceduralSkillApplyReadiness,
    ) -> ProceduralSkillApplyReview:
        with self._lock:
            report = reviewer.review(receipt)
            checks = {
                "readiness_current": report.status == "READY FOR SKILL APPLY DESIGN REVIEW",
                "authoring_receipt_not_applied": receipt.id not in self._receipts,
                "run_once_slot_available": len(self._receipts) < PROCEDURAL_SKILL_APPLY_MAX_RECEIPTS,
                "apply_engine_installed": PROCEDURAL_SKILL_APPLY_ENGINE_INSTALLED,
                "procedure_execution_disabled": not PROCEDURAL_SKILL_EXECUTION_ENABLED,
            }
            issues = list(report.issues)
            messages = {
                "readiness_current": "Current procedural skill apply readiness is not READY.",
                "authoring_receipt_not_applied": "Authoring receipt was already applied in this process.",
                "run_once_slot_available": "Single-skill process apply slot is already used.",
                "apply_engine_installed": "Procedural skill apply engine is not installed.",
                "procedure_execution_disabled": "Procedure execution must remain disabled.",
            }
            issues.extend(messages[name] for name, passed in checks.items() if not passed)
            confirmable = all(checks.values()) and not issues
            return ProceduralSkillApplyReview(
                status="CONFIRMABLE" if confirmable else "NOT CONFIRMABLE",
                authoring_receipt_id=receipt.id,
                source_lesson_id=receipt.source_lesson_id,
                created_skill_id=report.contract.target_record_id,
                before_store_sha256=report.skill_store_sha256,
                target_payload_hash=report.contract.target_payload_hash,
                checks=checks,
                issues=_dedupe(issues),
                warnings=list(report.warnings),
                confirmable=confirmable,
            )

    def apply(
        self,
        receipt: ProceduralSkillAuthoringReceipt,
        *,
        token: str,
        reviewer: ProceduralSkillApplyReadiness,
    ) -> ProceduralSkillApplyReceipt:
        with self._lock:
            review = self.review(receipt, reviewer=reviewer)
            if not review.confirmable:
                raise ProceduralSkillApplyError("; ".join(review.issues) or review.status)
            expected_token = procedural_skill_apply_confirmation_token(review)
            if token != expected_token:
                raise ProceduralSkillApplyError("Procedural skill apply confirmation token mismatch.")

            library = reviewer.skill_library
            path = library.skills_path
            existed_before = path.exists()
            before_bytes = _read_original_bytes(path)
            if hashlib.sha256(before_bytes).hexdigest() != review.before_store_sha256:
                raise ProceduralSkillApplyError(
                    "Skill Library changed after apply confirmation preview."
                )
            original_records = _parse_jsonl_records(before_bytes)
            memory_path = reviewer.builder.memory_store.persistent_path
            memory_before = _hash_file(memory_path)
            record = _build_skill_record(receipt, review)
            payload = _append_record_bytes(before_bytes, record)

            try:
                _atomic_replace(path, payload)
                verified_record, exact_mutations = _verify_skill_write(
                    library,
                    original_records=original_records,
                    expected_record=record,
                )
                memory_after = _hash_file(memory_path)
                if memory_before == "unavailable" or memory_after != memory_before:
                    raise ProceduralSkillApplyError(
                        "Persistent memory changed during procedural skill apply."
                    )
                source = next(
                    (
                        item
                        for item in reviewer.builder.memory_store.load_persistent_memory()
                        if item.id == receipt.source_lesson_id
                    ),
                    None,
                )
                provenance = verify_memory_provenance(source) if source is not None else None
                source_verified = bool(
                    provenance
                    and provenance.verified
                    and provenance.provenance_id == receipt.source_provenance_id
                )
                if not source_verified:
                    raise ProceduralSkillApplyError(
                        "Source lesson provenance failed post-write verification."
                    )
                after_hash = _hash_file(path)
                if len(after_hash) != 64:
                    raise ProceduralSkillApplyError(
                        "Post-write Skill Library SHA-256 is unavailable."
                    )
            except (
                OSError,
                UnicodeDecodeError,
                json.JSONDecodeError,
                ProceduralSkillApplyError,
                TypeError,
                ValueError,
            ) as exc:
                _restore_original(path, before_bytes, existed_before=existed_before)
                if _current_bytes(path) != (before_bytes if existed_before else None):
                    raise ProceduralSkillApplyError(
                        "Skill apply failed and exact-byte rollback did not restore the original state."
                    ) from exc
                raise ProceduralSkillApplyError(
                    f"Skill apply verification failed; exact original bytes were restored: {exc}"
                ) from exc

            applied_at = str(record["created_at"])
            created_record_hash = _hash_json(verified_record)
            apply_material = {
                "applied_at": applied_at,
                "authoring_receipt_id": receipt.id,
                "source_lesson_id": receipt.source_lesson_id,
                "source_provenance_id": receipt.source_provenance_id,
                "source_record_hash": receipt.source_record_hash,
                "authoring_hash": receipt.authoring_hash,
                "created_skill_id": review.created_skill_id,
                "before_store_sha256": review.before_store_sha256,
                "after_store_sha256": after_hash,
                "created_record_hash": created_record_hash,
                "target_payload_hash": review.target_payload_hash,
                "confirmation_method": "exact_current_skill_readiness_token",
                "confirmation_token_hash": hashlib.sha256(token.encode("utf-8")).hexdigest(),
                "record_verified": True,
                "source_provenance_verified": source_verified,
                "exact_record_mutations": exact_mutations,
                "rollback_suggestion": f"/skills archive {review.created_skill_id}",
                "run_once_guard": True,
                "apply_result": "single_procedural_skill_append_verified",
                "receipt_persistence": "process_memory_only",
                "target_execution_performed": False,
                "executable": False,
                "skill_mutation_performed": True,
                "memory_mutation_performed": False,
                "experience_mutation_performed": False,
                "batch_apply_performed": False,
            }
            receipt_hash = _hash_json(apply_material)
            applied = ProceduralSkillApplyReceipt(
                id=f"skillapply_{receipt_hash[:16]}",
                **apply_material,
                receipt_hash=receipt_hash,
            )
            self._receipts[receipt.id] = applied
            return applied

    def doctor(
        self,
        *,
        reviewer: ProceduralSkillApplyReadiness,
    ) -> ProceduralSkillApplyDoctorReport:
        receipts = self.snapshot()
        issues: list[str] = []
        warnings: list[str] = []
        verified_current_count = 0
        historical_count = 0
        if len(receipts) > PROCEDURAL_SKILL_APPLY_MAX_RECEIPTS:
            issues.append("Procedural skill apply run-once receipt limit is exceeded.")
        ids = [str(item.get("id") or "") for item in receipts]
        if any(not value for value in ids) or any(count > 1 for count in Counter(ids).values()):
            issues.append("Procedural skill apply receipt id is missing or duplicated.")
        current_records = _safe_library_records(reviewer.skill_library, issues)
        for item in receipts:
            label = str(item.get("id") or "<missing>")
            stored_hash = str(item.get("receipt_hash") or "")
            if len(stored_hash) != 64 or label != f"skillapply_{stored_hash[:16]}":
                issues.append(f"Apply receipt {label} hash identity is invalid.")
            elif _receipt_hash(item) != stored_hash:
                issues.append(f"Apply receipt {label} content hash does not verify.")
            if not _safe_receipt_flags(item):
                issues.append(f"Apply receipt {label} violates the single-write/no-execution boundary.")
            target = next(
                (
                    record
                    for record in current_records
                    if record.get("id") == item.get("created_skill_id")
                ),
                None,
            )
            if target is not None and _hash_json(target) == item.get("created_record_hash"):
                verified_current_count += 1
            else:
                historical_count += 1
                warnings.append(
                    f"Apply receipt {label} target skill is missing or has changed since verified apply."
                )

        apply_spec = next(
            (spec for spec in COMMAND_REGISTRY if spec.prefix == "/experience learning apply skill"),
            None,
        )
        if (
            apply_spec is None
            or apply_spec.read_only
            or apply_spec.mutates != "skills"
            or apply_spec.risk != "medium"
        ):
            issues.append("Procedural skill apply lacks its exact confirmation-required Registry gate.")
        if not PROCEDURAL_SKILL_APPLY_ENGINE_INSTALLED:
            issues.append("Procedural skill apply engine is unexpectedly disabled.")
        if PROCEDURAL_SKILL_EXECUTION_ENABLED:
            issues.append("Procedural skill execution must remain disabled.")
        status = "ERROR" if issues else "WARN" if warnings else "OK"
        return ProceduralSkillApplyDoctorReport(
            status=status,
            receipt_count=len(receipts),
            verified_current_count=verified_current_count,
            historical_count=historical_count,
            issues=_dedupe(issues),
            warnings=_dedupe(warnings),
        )


def procedural_skill_apply_confirmation_token(review: ProceduralSkillApplyReview) -> str:
    material = {
        "authoring_receipt_id": review.authoring_receipt_id,
        "source_lesson_id": review.source_lesson_id,
        "created_skill_id": review.created_skill_id,
        "before_store_sha256": review.before_store_sha256,
        "target_payload_hash": review.target_payload_hash,
    }
    return f"CONFIRM-SKILL-APPLY-{_hash_json(material)[:12].upper()}"


def format_procedural_skill_apply_command(
    command: str,
    *,
    authoring_session: OperatorReviewedProceduralSkillAuthoringSession,
    apply_session: OperatorReviewedProceduralSkillApplySession,
    reviewer: ProceduralSkillApplyReadiness,
) -> str | None:
    raw = command.strip()
    normalized = " ".join(raw.lower().split())
    prefixes = (
        "/experience learning skill-apply-confirm-preview",
        "/experience learning apply skill",
        "/experience learning skill-apply-status",
        "/experience learning skill-apply-receipt",
        "/experience learning skill-apply-pilot-doctor",
    )
    if not any(normalized == prefix or normalized.startswith(prefix + " ") for prefix in prefixes):
        return None
    if any(marker in raw for marker in ("\n", ";", "&&", "||")):
        return _apply_error("Command chaining and multi-command input are not allowed.")
    try:
        if normalized == "/experience learning skill-apply-status":
            return format_procedural_skill_apply_status(
                apply_session.doctor(reviewer=reviewer)
            )
        if normalized == "/experience learning skill-apply-pilot-doctor":
            return format_procedural_skill_apply_doctor(
                apply_session.doctor(reviewer=reviewer)
            )
        if normalized == "/experience learning skill-apply-receipt":
            return "Usage: /experience learning skill-apply-receipt <apply_id|receipt_id|memory_id|skill_id>"
        if normalized.startswith("/experience learning skill-apply-receipt "):
            identifier = raw[len("/experience learning skill-apply-receipt") :].strip()
            if not identifier or " " in identifier:
                return "Usage: /experience learning skill-apply-receipt <apply_id|receipt_id|memory_id|skill_id>"
            return format_procedural_skill_apply_receipt(
                apply_session.get(identifier), identifier
            )
        if normalized == "/experience learning skill-apply-confirm-preview":
            return "Usage: /experience learning skill-apply-confirm-preview <receipt_id|memory_id>"
        if normalized.startswith("/experience learning skill-apply-confirm-preview "):
            identifier = raw[len("/experience learning skill-apply-confirm-preview") :].strip()
            receipt = _authoring_receipt(authoring_session, identifier)
            return format_procedural_skill_apply_preview(
                apply_session.review(receipt, reviewer=reviewer)
            )
        if normalized == "/experience learning apply skill":
            return "Usage: /experience learning apply skill <receipt_id|memory_id> <exact_token>"
        if normalized.startswith("/experience learning apply skill "):
            parts = raw.split()
            if len(parts) != 6:
                return "Usage: /experience learning apply skill <receipt_id|memory_id> <exact_token>"
            receipt = _authoring_receipt(authoring_session, parts[4])
            applied = apply_session.apply(receipt, token=parts[5], reviewer=reviewer)
            return format_procedural_skill_applied(applied)
    except (ProceduralSkillApplyError, OSError, TypeError, ValueError) as exc:
        return _apply_error(str(exc))
    return None


def format_procedural_skill_apply_preview(review: ProceduralSkillApplyReview) -> str:
    lines = [
        "Proto-Mind Procedural Skill Apply Confirmation Preview v1",
        f"Status: {review.status}",
        f"authoring_receipt_id: {review.authoring_receipt_id}",
        f"source_lesson_id: {review.source_lesson_id}",
        f"created_skill_id: {review.created_skill_id}",
        f"before_store_sha256: {review.before_store_sha256}",
        f"target_payload_hash: {review.target_payload_hash}",
        "expected_record_mutations: 1",
        "procedure_execution_enabled: false",
    ]
    lines.extend(f"- {name}: {str(value).lower()}" for name, value in review.checks.items())
    lines.extend(f"- BLOCKER: {issue}" for issue in review.issues)
    lines.extend(f"- WARN: {warning}" for warning in review.warnings)
    if review.confirmable:
        lines.append(
            f"Confirmation token: {procedural_skill_apply_confirmation_token(review)}"
        )
    lines.extend(_apply_boundary())
    return "\n".join(lines)


def format_procedural_skill_applied(receipt: ProceduralSkillApplyReceipt) -> str:
    return "\n".join(
        [
            "Proto-Mind Procedural Skill Apply Receipt v1",
            "Status: APPLIED AND VERIFIED",
            f"apply_id: {receipt.id}",
            f"created_skill_id: {receipt.created_skill_id}",
            f"before_store_sha256: {receipt.before_store_sha256}",
            f"after_store_sha256: {receipt.after_store_sha256}",
            f"created_record_hash: {receipt.created_record_hash}",
            "exact_record_mutations: 1",
            "target_execution_performed: false",
            f"rollback_suggestion: {receipt.rollback_suggestion}",
            *_apply_boundary(),
        ]
    )


def format_procedural_skill_apply_status(report: ProceduralSkillApplyDoctorReport) -> str:
    return "\n".join(
        [
            "Proto-Mind Procedural Skill Apply Status v1",
            f"Status: {report.status}",
            f"mode: {PROCEDURAL_SKILL_APPLY_MODE}",
            f"receipts: {report.receipt_count}/{PROCEDURAL_SKILL_APPLY_MAX_RECEIPTS}",
            f"verified_current: {report.verified_current_count}",
            f"historical: {report.historical_count}",
            "apply_engine_installed: true",
            "procedure_execution_enabled: false",
            "Commands: skill-apply-confirm-preview | apply skill | skill-apply-receipt | skill-apply-pilot-doctor",
            *_apply_boundary(),
        ]
    )


def format_procedural_skill_apply_receipt(
    receipt: ProceduralSkillApplyReceipt | None,
    identifier: str,
) -> str:
    if receipt is None:
        return _apply_error(f"No process-memory procedural skill apply receipt matches {identifier!r}.")
    return "\n".join(
        [
            "Proto-Mind Procedural Skill Apply Receipt Inspect v1",
            "Status: OK",
            json.dumps(receipt.to_dict(), ensure_ascii=False, indent=2, sort_keys=True),
            *_apply_boundary(),
        ]
    )


def format_procedural_skill_apply_doctor(
    report: ProceduralSkillApplyDoctorReport,
) -> str:
    lines = [
        "Proto-Mind Procedural Skill Apply Doctor v1",
        f"Status: {report.status}",
        f"receipts: {report.receipt_count}",
        f"verified_current: {report.verified_current_count}",
        f"historical: {report.historical_count}",
        "apply_engine_installed: true",
        "procedure_execution_enabled: false",
    ]
    lines.extend(f"- ERROR: {issue}" for issue in report.issues)
    lines.extend(f"- WARN: {warning}" for warning in report.warnings)
    if not report.issues and not report.warnings:
        lines.append(
            "- Registry gate, run-once receipt, record hash, current target, rollback, and no-execution boundary are healthy."
        )
    lines.extend(_apply_boundary())
    return "\n".join(lines)


def _authoring_receipt(
    session: OperatorReviewedProceduralSkillAuthoringSession,
    identifier: str,
) -> ProceduralSkillAuthoringReceipt:
    if not identifier or " " in identifier:
        raise ProceduralSkillApplyError("A single authoring receipt or source lesson id is required.")
    receipt = session.get(identifier)
    if receipt is None:
        raise ProceduralSkillApplyError(
            f"No process-memory skill authoring receipt matches {identifier!r}."
        )
    return receipt


def _build_skill_record(
    receipt: ProceduralSkillAuthoringReceipt,
    review: ProceduralSkillApplyReview,
) -> dict[str, Any]:
    projection = receipt.storage_projection
    now = utc_now_iso()
    return {
        "id": review.created_skill_id,
        "created_at": now,
        "updated_at": now,
        "name": projection["name"],
        "summary": projection["summary"],
        "body": projection["body"],
        "status": "active",
        "category": projection["category"],
        "source": "experience_learning_skill_apply",
        "tags": list(projection["tags"]),
        "uses": 0,
        "last_used_at": None,
        "schema": projection["schema"],
        "source_lesson_id": receipt.source_lesson_id,
        "source_provenance_id": receipt.source_provenance_id,
        "source_record_hash": receipt.source_record_hash,
        "authoring_receipt_id": receipt.id,
        "authoring_hash": receipt.authoring_hash,
        "target_payload_hash": review.target_payload_hash,
        "executable": False,
    }


def _verify_skill_write(
    library: SkillLibrary,
    *,
    original_records: list[dict[str, Any]],
    expected_record: dict[str, Any],
) -> tuple[dict[str, Any], int]:
    after_bytes = library.skills_path.read_bytes()
    records = _parse_jsonl_records(after_bytes)
    if len(records) != len(original_records) + 1:
        raise ProceduralSkillApplyError("Skill record count did not increase by exactly one.")
    if records[:-1] != original_records:
        raise ProceduralSkillApplyError("An existing Skill Library record changed during append.")
    if records[-1] != expected_record:
        raise ProceduralSkillApplyError("Created procedural skill record differs from the fixed payload.")
    ids = [str(record.get("id") or "") for record in records]
    if len(ids) != len(set(ids)) or ids.count(str(expected_record["id"])) != 1:
        raise ProceduralSkillApplyError("Post-write Skill Library ids are missing or duplicated.")
    snapshot = library.read_snapshot()
    if snapshot["error"] or snapshot["malformed_count"]:
        raise ProceduralSkillApplyError("Post-write Skill Library is unreadable or malformed.")
    return records[-1], 1


def _read_original_bytes(path: Path) -> bytes:
    try:
        return path.read_bytes() if path.exists() else b""
    except OSError as exc:
        raise ProceduralSkillApplyError(f"Skill Library is unreadable: {exc}") from exc


def _parse_jsonl_records(payload: bytes) -> list[dict[str, Any]]:
    text = payload.decode("utf-8")
    records: list[dict[str, Any]] = []
    for line_number, raw in enumerate(text.splitlines(), 1):
        if not raw.strip():
            continue
        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            raise ProceduralSkillApplyError(
                f"Skill Library line {line_number} is not a JSON object."
            )
        records.append(parsed)
    return records


def _append_record_bytes(before: bytes, record: dict[str, Any]) -> bytes:
    separator = b"" if not before or before.endswith(b"\n") else b"\n"
    encoded = json.dumps(record, ensure_ascii=False, sort_keys=True).encode("utf-8") + b"\n"
    return before + separator + encoded


def _atomic_replace(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        temp_path.write_bytes(payload)
        temp_path.replace(path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def _restore_original(path: Path, before: bytes, *, existed_before: bool) -> None:
    if existed_before:
        _atomic_replace(path, before)
    elif path.exists():
        path.unlink()


def _current_bytes(path: Path) -> bytes | None:
    try:
        return path.read_bytes() if path.exists() else None
    except OSError:
        return None


def _safe_library_records(
    library: SkillLibrary,
    issues: list[str],
) -> list[dict[str, Any]]:
    snapshot = library.read_snapshot()
    if snapshot["error"]:
        issues.append(f"Skill Library is unreadable: {snapshot['error']}")
    if snapshot["malformed_count"]:
        issues.append("Skill Library contains malformed JSONL entries.")
    return snapshot["records"]


def _safe_receipt_flags(item: dict[str, Any]) -> bool:
    return bool(
        item.get("record_verified") is True
        and item.get("source_provenance_verified") is True
        and item.get("exact_record_mutations") == 1
        and item.get("run_once_guard") is True
        and item.get("target_execution_performed") is False
        and item.get("executable") is False
        and item.get("skill_mutation_performed") is True
        and item.get("memory_mutation_performed") is False
        and item.get("experience_mutation_performed") is False
        and item.get("batch_apply_performed") is False
        and item.get("receipt_persistence") == "process_memory_only"
        and str(item.get("rollback_suggestion") or "").startswith("/skills archive ")
    )


def _receipt_hash(item: dict[str, Any]) -> str:
    material = {
        key: value
        for key, value in item.items()
        if key not in {"id", "receipt_hash"}
    }
    return _hash_json(material)


def _hash_file(path: Path) -> str:
    try:
        payload = path.read_bytes() if path.exists() else b""
    except OSError:
        return "unavailable"
    return hashlib.sha256(payload).hexdigest()


def _hash_json(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _apply_error(message: str) -> str:
    return "\n".join(
        [
            "Proto-Mind Procedural Skill Apply Error",
            "Status: ERROR",
            f"- {message}",
            *_apply_boundary(),
        ]
    )


def _apply_boundary() -> list[str]:
    return [
        "Boundary:",
        "- One operator-authored skill record may be stored after two exact confirmations; the procedure itself is never executed.",
        "- No lesson, memory, Experience event, queue, export, session log, Context Injection, shell, or external state changed.",
        "- No batch, automatic selection/apply, arbitrary dispatch, model/API call, procedure runner, or background action exists.",
    ]


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))
