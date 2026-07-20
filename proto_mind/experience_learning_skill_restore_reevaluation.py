from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass
from datetime import datetime
import hashlib
import json
from typing import Any, Iterable

from proto_mind.command_registry import COMMAND_REGISTRY
from proto_mind.experience_ledger import ExperienceEvent
from proto_mind.experience_learning_skill_outcome import (
    ProceduralSkillOutcomeReviewer,
    ProceduralSkillOutcomeSignal,
)
from proto_mind.experience_learning_skill_runtime import (
    PROCEDURAL_SKILL_EXECUTION_INSTALLED,
)
from proto_mind.memory_store import MemoryStore
from proto_mind.models import MemoryRecord
from proto_mind.skill_library import SkillLibrary
from proto_mind.skill_lifecycle_audit import (
    ProceduralSkillLifecycleAudit,
    ProceduralSkillLifecycleAuditError,
)
from proto_mind.skill_lifecycle_restore import (
    PROCEDURAL_SKILL_LIFECYCLE_RESTORE_SCHEMA,
    verify_procedural_skill_lifecycle_restore_metadata,
)
from proto_mind.skill_lifecycle_restore_receipt_audit import (
    build_procedural_skill_restore_receipt_evidence,
    verify_procedural_skill_restore_receipt_evidence,
)


PROCEDURAL_SKILL_RESTORE_REEVALUATION_VERSION = 1
PROCEDURAL_SKILL_RESTORE_REEVALUATION_MODE = (
    "read_only_exact_post_restore_manual_evidence_design"
)
PROCEDURAL_SKILL_RESTORE_REEVALUATION_STATUSES = frozenset(
    {
        "POST_RESTORE_SUCCESS_CANDIDATE",
        "POST_RESTORE_FAILURE_CANDIDATE",
        "POST_RESTORE_MIXED_EVIDENCE",
        "NEEDS_POST_RESTORE_EVIDENCE",
        "NOT_RESTORED",
        "NOT_FOUND",
        "ERROR",
    }
)
PROCEDURAL_SKILL_RESTORE_REEVALUATION_REQUIRED_CALL_FIELDS = (
    "skill_id",
    "skill_provenance_id",
    "manual_operator_use",
    "execution_performed_by_proto_mind",
    "post_restore_manual_use",
    "restore_metadata_id",
    "restore_metadata_hash",
    "restore_evidence_hash",
)
PROCEDURAL_SKILL_POST_RESTORE_CAPTURE_WRITER_INSTALLED = False
PROCEDURAL_SKILL_POST_RESTORE_DECISION_WRITER_INSTALLED = False


@dataclass(frozen=True)
class ProceduralSkillRestoreReevaluationReview:
    status: str
    skill_id: str
    provenance_id: str
    restored_at: str
    restore_metadata_id: str
    restore_metadata_hash: str
    restore_evidence_id: str
    restore_evidence_hash: str
    pre_restore_manual_use_count: int
    unbound_post_restore_manual_use_count: int
    bound_post_restore_manual_use_count: int
    post_restore_signal_count: int
    selected_signal_id: str
    signals: list[ProceduralSkillOutcomeSignal]
    review_hash: str
    checks: dict[str, bool]
    issues: list[str]
    warnings: list[str]
    new_capture_contract_required: bool = True
    future_lifecycle_decision_ready: bool = False
    automatic_decision_allowed: bool = False
    mutation_performed: bool = False
    procedure_execution_performed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ProceduralSkillRestoreReevaluationDoctorReport:
    status: str
    event_count: int
    skill_count: int
    restored_skill_count: int
    exact_post_restore_evidence_count: int
    awaiting_new_evidence_count: int
    issues: list[str]
    warnings: list[str]


class ProceduralSkillRestoreReevaluationReviewer:
    """Requires exact new manual evidence after the durable restore boundary."""

    def __init__(
        self,
        events: Iterable[ExperienceEvent | dict[str, Any]],
        skill_records: Iterable[dict[str, Any]],
        memory_records: Iterable[MemoryRecord],
        *,
        skills_path: Any,
        persistent_memory_path: Any,
        skill_store_error: str = "",
        malformed_skill_count: int = 0,
    ) -> None:
        self.events = [
            event.to_dict() if isinstance(event, ExperienceEvent) else deepcopy(dict(event))
            for event in events
        ]
        self.skills = [deepcopy(dict(record)) for record in skill_records]
        self.memories = list(memory_records)
        self.skills_path = skills_path
        self.persistent_memory_path = persistent_memory_path
        self.skill_store_error = skill_store_error
        self.malformed_skill_count = malformed_skill_count

    def review(self, skill_id: str) -> ProceduralSkillRestoreReevaluationReview:
        identifier = skill_id.strip()
        base_checks = {
            "skill_found": False,
            "active_restored_verified": False,
            "restore_envelope_verified": False,
            "restore_evidence_verified": False,
            "manual_use_strictly_after_restore": False,
            "exact_restore_binding_present": False,
            "proto_mind_execution_absent": True,
            "decisive_post_restore_outcome_found": False,
            "legacy_decision_path_blocked": True,
        }
        matches = [record for record in self.skills if record.get("id") == identifier]
        if not matches:
            return self._result(
                status="NOT_FOUND",
                skill_id=identifier,
                checks=base_checks,
                issues=["Skill record was not found."],
            )
        if len(matches) != 1:
            return self._result(
                status="ERROR",
                skill_id=identifier,
                checks=base_checks,
                issues=["Skill Library contains duplicate matching skill ids."],
            )
        base_checks["skill_found"] = True
        record = matches[0]
        metadata = record.get("lifecycle")
        if not isinstance(metadata, dict) or metadata.get("schema") != (
            PROCEDURAL_SKILL_LIFECYCLE_RESTORE_SCHEMA
        ):
            return self._result(
                status="NOT_RESTORED",
                skill_id=identifier,
                checks=base_checks,
                warnings=["Skill has no durable restore envelope; use the ordinary outcome review."],
            )

        metadata_check = verify_procedural_skill_lifecycle_restore_metadata(metadata)
        base_checks["restore_envelope_verified"] = metadata_check.verified
        try:
            lifecycle_entry = ProceduralSkillLifecycleAudit(
                skills_path=self.skills_path,
                persistent_memory_path=self.persistent_memory_path,
            ).get(identifier)
        except ProceduralSkillLifecycleAuditError as exc:
            return self._result(
                status="ERROR",
                skill_id=identifier,
                checks=base_checks,
                issues=[str(exc)],
            )
        active_restored = bool(
            lifecycle_entry is not None
            and lifecycle_entry.state == "active_restored_verified"
            and lifecycle_entry.restart_safe
        )
        base_checks["active_restored_verified"] = active_restored
        if not metadata_check.verified or not active_restored:
            issues = list(metadata_check.issues)
            if not active_restored:
                issues.append("Current skill state is not active_restored_verified.")
            return self._result(
                status="ERROR",
                skill_id=identifier,
                checks=base_checks,
                issues=issues,
            )

        try:
            restore_evidence = build_procedural_skill_restore_receipt_evidence(record)
        except ValueError as exc:
            return self._result(
                status="ERROR",
                skill_id=identifier,
                checks=base_checks,
                issues=[str(exc)],
            )
        evidence_check = verify_procedural_skill_restore_receipt_evidence(restore_evidence)
        base_checks["restore_evidence_verified"] = evidence_check.verified
        provenance = record.get("provenance")
        provenance_id = str(provenance.get("id") or "") if isinstance(provenance, dict) else ""
        restored_at = str(metadata.get("transitioned_at") or "")

        relevant_calls = [
            event
            for event in self.events
            if event.get("event_type") == "tool_called"
            and (
                _payload(event).get("skill_id") == identifier
                or _payload(event).get("capability") == f"skill:{identifier}"
            )
        ]
        pre_restore = [event for event in relevant_calls if not _is_after(event, restored_at)]
        post_restore = [event for event in relevant_calls if _is_after(event, restored_at)]
        unsafe = [
            event
            for event in post_restore
            if _payload(event).get("execution_performed_by_proto_mind") is not False
        ]
        base_checks["proto_mind_execution_absent"] = not unsafe
        eligible_calls = [
            event
            for event in post_restore
            if _is_exact_restore_bound_call(
                event,
                skill_id=identifier,
                provenance_id=provenance_id,
                metadata=metadata,
                evidence=restore_evidence,
            )
        ]
        eligible_ids = {str(event.get("id") or "") for event in eligible_calls}
        eligible_events = _connected_event_subset(self.events, eligible_ids, restored_at)
        unbound_count = len(post_restore) - len(eligible_calls)
        base_checks["manual_use_strictly_after_restore"] = bool(post_restore)
        base_checks["exact_restore_binding_present"] = bool(eligible_calls)

        if unsafe:
            return self._result(
                status="ERROR",
                skill_id=identifier,
                provenance_id=provenance_id,
                restored_at=restored_at,
                metadata=metadata,
                restore_evidence=restore_evidence,
                pre_restore_count=len(pre_restore),
                unbound_count=unbound_count,
                bound_count=len(eligible_calls),
                checks=base_checks,
                issues=[
                    "Post-restore review only accepts manual evidence with execution_performed_by_proto_mind=false."
                ],
            )

        outcome = ProceduralSkillOutcomeReviewer(
            eligible_events,
            [record],
            self.memories,
            skill_store_error=self.skill_store_error,
            malformed_skill_count=self.malformed_skill_count,
        ).review(identifier)
        signals = list(outcome.signals)
        base_checks["decisive_post_restore_outcome_found"] = bool(signals)
        warnings = list(outcome.warnings)
        if pre_restore:
            warnings.append(
                f"Excluded {len(pre_restore)} pre-restore manual-use event(s) from re-evaluation."
            )
        if unbound_count:
            warnings.append(
                f"Excluded {unbound_count} post-restore manual-use event(s) without the exact restore binding contract."
            )
        status_map = {
            "SUCCESS_CANDIDATE": "POST_RESTORE_SUCCESS_CANDIDATE",
            "FAILURE_CANDIDATE": "POST_RESTORE_FAILURE_CANDIDATE",
            "MIXED_EVIDENCE": "POST_RESTORE_MIXED_EVIDENCE",
        }
        status = status_map.get(outcome.status, "NEEDS_POST_RESTORE_EVIDENCE")
        if not eligible_calls:
            warnings.append(
                "A new exact post-restore capture contract is required before any lifecycle decision."
            )
        return self._result(
            status=status,
            skill_id=identifier,
            provenance_id=provenance_id,
            restored_at=restored_at,
            metadata=metadata,
            restore_evidence=restore_evidence,
            pre_restore_count=len(pre_restore),
            unbound_count=unbound_count,
            bound_count=len(eligible_calls),
            signals=signals,
            selected_signal_id=outcome.selected_signal_id,
            checks=base_checks,
            issues=list(outcome.issues) if outcome.status == "ERROR" else [],
            warnings=warnings,
        )

    def doctor(self) -> ProceduralSkillRestoreReevaluationDoctorReport:
        issues: list[str] = []
        warnings: list[str] = []
        if self.skill_store_error:
            issues.append(f"Skill Library is unreadable: {self.skill_store_error}")
        if self.malformed_skill_count:
            issues.append(
                f"Skill Library contains {self.malformed_skill_count} malformed JSONL record(s)."
            )
        issues.extend(_contract_issues())
        restored = [
            record
            for record in self.skills
            if isinstance(record.get("lifecycle"), dict)
            and record["lifecycle"].get("schema") == PROCEDURAL_SKILL_LIFECYCLE_RESTORE_SCHEMA
        ]
        reviews = [self.review(str(record.get("id") or "")) for record in restored]
        issues.extend(
            f"{review.skill_id}: {item}"
            for review in reviews
            for item in review.issues
        )
        ready_statuses = {
            "POST_RESTORE_SUCCESS_CANDIDATE",
            "POST_RESTORE_FAILURE_CANDIDATE",
            "POST_RESTORE_MIXED_EVIDENCE",
        }
        return ProceduralSkillRestoreReevaluationDoctorReport(
            status="ERROR" if issues else "WARN" if warnings else "OK",
            event_count=len(self.events),
            skill_count=len(self.skills),
            restored_skill_count=len(restored),
            exact_post_restore_evidence_count=sum(
                review.status in ready_statuses for review in reviews
            ),
            awaiting_new_evidence_count=sum(
                review.status == "NEEDS_POST_RESTORE_EVIDENCE" for review in reviews
            ),
            issues=_dedupe(issues),
            warnings=_dedupe(warnings),
        )

    def _result(
        self,
        *,
        status: str,
        skill_id: str,
        checks: dict[str, bool],
        provenance_id: str = "",
        restored_at: str = "",
        metadata: dict[str, Any] | None = None,
        restore_evidence: dict[str, Any] | None = None,
        pre_restore_count: int = 0,
        unbound_count: int = 0,
        bound_count: int = 0,
        signals: list[ProceduralSkillOutcomeSignal] | None = None,
        selected_signal_id: str = "",
        issues: list[str] | None = None,
        warnings: list[str] | None = None,
    ) -> ProceduralSkillRestoreReevaluationReview:
        metadata = metadata or {}
        evidence = restore_evidence or {}
        material = {
            "status": status,
            "skill_id": skill_id,
            "provenance_id": provenance_id,
            "restored_at": restored_at,
            "restore_metadata_id": str(metadata.get("id") or ""),
            "restore_metadata_hash": str(metadata.get("metadata_hash") or ""),
            "restore_evidence_id": str(evidence.get("id") or ""),
            "restore_evidence_hash": str(evidence.get("evidence_hash") or ""),
            "pre_restore_manual_use_count": pre_restore_count,
            "unbound_post_restore_manual_use_count": unbound_count,
            "bound_post_restore_manual_use_count": bound_count,
            "post_restore_signal_count": len(signals or []),
            "selected_signal_id": selected_signal_id,
            "signal_ids": [signal.event_id for signal in signals or []],
            "checks": checks,
        }
        return ProceduralSkillRestoreReevaluationReview(
            status=status,
            skill_id=skill_id,
            provenance_id=provenance_id,
            restored_at=restored_at,
            restore_metadata_id=material["restore_metadata_id"],
            restore_metadata_hash=material["restore_metadata_hash"],
            restore_evidence_id=material["restore_evidence_id"],
            restore_evidence_hash=material["restore_evidence_hash"],
            pre_restore_manual_use_count=pre_restore_count,
            unbound_post_restore_manual_use_count=unbound_count,
            bound_post_restore_manual_use_count=bound_count,
            post_restore_signal_count=len(signals or []),
            selected_signal_id=selected_signal_id,
            signals=list(signals or []),
            review_hash=_hash_json(material),
            checks=checks,
            issues=_dedupe(list(issues or [])),
            warnings=_dedupe(list(warnings or [])),
        )


def format_procedural_skill_restore_reevaluation_command(
    command: str,
    *,
    events: Iterable[ExperienceEvent | dict[str, Any]],
    memory_store: MemoryStore | None,
    skill_library: SkillLibrary,
) -> str | None:
    raw = command.strip()
    normalized = " ".join(raw.lower().split())
    recognized = bool(
        normalized.startswith(
            "/experience learning skill-outcome-doctor --post-restore"
        )
        or normalized.startswith("/experience learning skill-outcome-review ")
        and any(flag in normalized for flag in ("--post-restore", "--post-restore-plan"))
    )
    if not recognized:
        return None
    if any(marker in raw for marker in ("\n", ";", "&&", "||", "|")):
        return _error("Command chaining and multi-command input are not allowed.")
    if normalized == "/experience learning skill-outcome-doctor --post-restore-contract":
        return format_procedural_skill_restore_reevaluation_contract()
    if memory_store is None:
        return _error("MemoryStore is unavailable from the shared handler.")
    try:
        memories = memory_store.load_persistent_memory()
    except (OSError, TypeError, ValueError) as exc:
        return _error(f"Persistent memory is unreadable: {exc}")
    snapshot = skill_library.read_snapshot()
    reviewer = ProceduralSkillRestoreReevaluationReviewer(
        events,
        snapshot["records"],
        memories,
        skills_path=skill_library.skills_path,
        persistent_memory_path=memory_store.persistent_path,
        skill_store_error=str(snapshot["error"] or ""),
        malformed_skill_count=int(snapshot["malformed_count"]),
    )
    if normalized == "/experience learning skill-outcome-doctor --post-restore":
        return format_procedural_skill_restore_reevaluation_doctor(reviewer.doctor())
    parts = raw.split()
    if len(parts) != 5:
        return _usage()
    review = reviewer.review(parts[3])
    if parts[4].lower() == "--post-restore-plan":
        return format_procedural_skill_restore_reevaluation_plan(review)
    if parts[4].lower() == "--post-restore":
        return format_procedural_skill_restore_reevaluation(review)
    return _usage()


def format_procedural_skill_restore_reevaluation_contract() -> str:
    return "\n".join(
        [
            "Proto-Mind Restored Skill Re-evaluation Contract v1",
            "Status: DESIGN LOCKED",
            f"mode: {PROCEDURAL_SKILL_RESTORE_REEVALUATION_MODE}",
            "required_tool_called_fields: "
            + ", ".join(PROCEDURAL_SKILL_RESTORE_REEVALUATION_REQUIRED_CALL_FIELDS),
            "temporal_boundary: event.created_at > lifecycle.transitioned_at",
            "pre_restore_evidence_reusable: false",
            "unbound_post_restore_evidence_eligible: false",
            "post_restore_capture_writer_installed: false",
            "post_restore_decision_writer_installed: false",
            "future_lifecycle_decision_ready: false",
            *_boundary(),
        ]
    )


def format_procedural_skill_restore_reevaluation(
    review: ProceduralSkillRestoreReevaluationReview,
) -> str:
    lines = [
        "Proto-Mind Restored Skill Re-evaluation Review v1",
        f"Status: {review.status}",
        f"skill_id: {review.skill_id or 'missing'}",
        f"provenance_id: {review.provenance_id or 'unavailable'}",
        f"restored_at: {review.restored_at or 'unavailable'}",
        f"restore_metadata_id: {review.restore_metadata_id or 'unavailable'}",
        f"restore_metadata_hash: {review.restore_metadata_hash or 'unavailable'}",
        f"restore_evidence_id: {review.restore_evidence_id or 'unavailable'}",
        f"restore_evidence_hash: {review.restore_evidence_hash or 'unavailable'}",
        f"pre_restore_manual_uses_excluded: {review.pre_restore_manual_use_count}",
        f"unbound_post_restore_manual_uses_excluded: {review.unbound_post_restore_manual_use_count}",
        f"bound_post_restore_manual_uses: {review.bound_post_restore_manual_use_count}",
        f"post_restore_signals: {review.post_restore_signal_count}",
        f"selected_signal_id: {review.selected_signal_id or 'none'}",
        f"review_hash: {review.review_hash}",
        "future_lifecycle_decision_ready: false",
        "Checks:",
    ]
    lines.extend(f"- {name}: {str(value).lower()}" for name, value in review.checks.items())
    lines.append("Post-restore signals:")
    if not review.signals:
        lines.append("- none")
    for signal in review.signals:
        lines.append(
            f"- {signal.signal} | {signal.event_type} ({signal.event_id}) | use={signal.use_event_id}"
        )
    lines.extend(f"- ERROR: {issue}" for issue in review.issues)
    lines.extend(f"- WARN: {warning}" for warning in review.warnings)
    lines.extend(_boundary())
    return "\n".join(lines)


def format_procedural_skill_restore_reevaluation_plan(
    review: ProceduralSkillRestoreReevaluationReview,
) -> str:
    lines = [
        "Proto-Mind Restored Skill Re-evaluation Plan v1",
        f"Status: {'READY FOR EVIDENCE REVIEW' if review.status.startswith('POST_RESTORE_') else 'AWAITING NEW EVIDENCE'}",
        f"skill_id: {review.skill_id or 'missing'}",
        f"restore_evidence_hash: {review.restore_evidence_hash or 'unavailable'}",
        "Required future sequence:",
        "1. Operator manually uses the restored procedure; Proto-Mind does not execute it.",
        "2. A separately approved future capture must bind provenance plus restore metadata/evidence hashes.",
        "3. The operator reports a verified success, failure, or correction after restored_at.",
        "4. Re-run --post-restore and inspect every exact signal.",
        "5. Add a separate decision/apply task only after this review; no token or writer exists now.",
        "future_capture_command_available: false",
        "future_decision_token_generated: false",
        "mutation_performed: false",
    ]
    lines.extend(f"- BLOCKER: {issue}" for issue in review.issues)
    lines.extend(f"- WARN: {warning}" for warning in review.warnings)
    lines.extend(_boundary())
    return "\n".join(lines)


def format_procedural_skill_restore_reevaluation_doctor(
    report: ProceduralSkillRestoreReevaluationDoctorReport,
) -> str:
    lines = [
        "Proto-Mind Restored Skill Re-evaluation Doctor v1",
        f"Status: {report.status}",
        f"mode: {PROCEDURAL_SKILL_RESTORE_REEVALUATION_MODE}",
        f"events: {report.event_count}",
        f"skills: {report.skill_count}",
        f"restored_skills: {report.restored_skill_count}",
        f"exact_post_restore_evidence: {report.exact_post_restore_evidence_count}",
        f"awaiting_new_evidence: {report.awaiting_new_evidence_count}",
        "post_restore_capture_writer_installed: false",
        "post_restore_decision_writer_installed: false",
        "procedure_execution_enabled: false",
    ]
    lines.extend(f"- ERROR: {issue}" for issue in report.issues)
    lines.extend(f"- WARN: {warning}" for warning in report.warnings)
    if not report.issues and not report.warnings:
        lines.append(
            "- Temporal boundary, exact restore binding, legacy-path guards, Registry, and no-execution design are healthy."
        )
    lines.extend(_boundary())
    return "\n".join(lines)


def restored_skill_requires_post_restore_contract(record: dict[str, Any]) -> bool:
    lifecycle = record.get("lifecycle")
    return bool(
        isinstance(lifecycle, dict)
        and lifecycle.get("schema") == PROCEDURAL_SKILL_LIFECYCLE_RESTORE_SCHEMA
    )


def _is_exact_restore_bound_call(
    event: dict[str, Any],
    *,
    skill_id: str,
    provenance_id: str,
    metadata: dict[str, Any],
    evidence: dict[str, Any],
) -> bool:
    payload = _payload(event)
    return bool(
        payload.get("skill_id") == skill_id
        and payload.get("skill_provenance_id") == provenance_id
        and payload.get("manual_operator_use") is True
        and payload.get("execution_performed_by_proto_mind") is False
        and payload.get("post_restore_manual_use") is True
        and payload.get("restore_metadata_id") == metadata.get("id")
        and payload.get("restore_metadata_hash") == metadata.get("metadata_hash")
        and payload.get("restore_evidence_hash") == evidence.get("evidence_hash")
    )


def _connected_event_subset(
    events: list[dict[str, Any]],
    eligible_call_ids: set[str],
    restored_at: str,
) -> list[dict[str, Any]]:
    if not eligible_call_ids:
        return []
    by_id = {str(event.get("id") or ""): event for event in events}
    selected = set(eligible_call_ids)
    changed = True
    while changed:
        changed = False
        for event in events:
            event_id = str(event.get("id") or "")
            sources = {
                str(value)
                for value in event.get("source_event_ids", [])
                if isinstance(value, str)
            }
            if event_id in selected:
                for source in sources:
                    if source in by_id and source not in selected:
                        selected.add(source)
                        changed = True
            elif sources.intersection(selected) and _is_after(event, restored_at):
                selected.add(event_id)
                changed = True
    return [deepcopy(event) for event in events if str(event.get("id") or "") in selected]


def _contract_issues() -> list[str]:
    issues: list[str] = []
    registry = {entry.prefix: entry for entry in COMMAND_REGISTRY}
    for prefix in (
        "/experience learning skill-outcome-review",
        "/experience learning skill-outcome-doctor",
    ):
        spec = registry.get(prefix)
        if spec is None or not spec.read_only or spec.mutates != "none" or spec.risk != "low":
            issues.append(f"Registry metadata for {prefix} is missing or unsafe.")
    if PROCEDURAL_SKILL_POST_RESTORE_CAPTURE_WRITER_INSTALLED:
        issues.append("Post-restore capture writer must remain disabled in v1.")
    if PROCEDURAL_SKILL_POST_RESTORE_DECISION_WRITER_INSTALLED:
        issues.append("Post-restore decision writer must remain disabled in v1.")
    if PROCEDURAL_SKILL_EXECUTION_INSTALLED:
        issues.append("Procedural skill execution must remain disabled.")
    if len(PROCEDURAL_SKILL_RESTORE_REEVALUATION_REQUIRED_CALL_FIELDS) != len(
        set(PROCEDURAL_SKILL_RESTORE_REEVALUATION_REQUIRED_CALL_FIELDS)
    ):
        issues.append("Post-restore required event fields are duplicated.")
    return issues


def _payload(event: dict[str, Any]) -> dict[str, Any]:
    payload = event.get("payload")
    return payload if isinstance(payload, dict) else {}


def _is_after(event: dict[str, Any], boundary: str) -> bool:
    try:
        event_time = datetime.fromisoformat(
            str(event.get("created_at") or "").replace("Z", "+00:00")
        )
        boundary_time = datetime.fromisoformat(boundary.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return False
    return event_time > boundary_time


def _usage() -> str:
    return (
        "Usage: /experience learning skill-outcome-review <skill_id> "
        "--post-restore|--post-restore-plan | "
        "skill-outcome-doctor --post-restore|--post-restore-contract"
    )


def _error(message: str) -> str:
    return "\n".join(
        [
            "Proto-Mind Restored Skill Re-evaluation Error",
            "Status: ERROR",
            f"- {message}",
            *_boundary(),
        ]
    )


def _boundary() -> list[str]:
    return [
        "Boundary:",
        "- Read-only design review; pre-restore or unbound evidence cannot authorize a restored-skill lifecycle decision.",
        "- No post-restore capture/decision writer, token, apply path, skill execution, or automatic conclusion exists.",
        "- No Experience event, skill, memory, queue, export, session log, Context Injection, shell, model/API, or external action changed.",
    ]


def _hash_json(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
    ).hexdigest()


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))
