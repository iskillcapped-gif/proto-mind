from __future__ import annotations

from collections import Counter
from copy import deepcopy
from dataclasses import asdict, dataclass
import hashlib
import json
import shlex
from threading import RLock
from typing import Any, Callable, Iterable

from proto_mind.command_registry import COMMAND_REGISTRY
from proto_mind.experience_ledger import ExperienceEvent, compact_preview
from proto_mind.experience_learning_skill_runtime import (
    PROCEDURAL_SKILL_EXECUTION_INSTALLED,
)
from proto_mind.memory_store import MemoryStore
from proto_mind.models import MemoryRecord, utc_now_iso
from proto_mind.skill_library import SkillLibrary
from proto_mind.skill_provenance import verify_procedural_skill_provenance


PROCEDURAL_SKILL_OUTCOME_CAPTURE_VERSION = 1
PROCEDURAL_SKILL_OUTCOME_CAPTURE_SCHEMA = "skill.outcome.capture.v1"
PROCEDURAL_SKILL_OUTCOME_CAPTURE_MODE = (
    "exact_consent_bounded_process_memory_manual_outcome"
)
PROCEDURAL_SKILL_OUTCOME_CAPTURE_MAX_RECEIPTS = 16
PROCEDURAL_SKILL_OUTCOME_CAPTURE_MAX_EVIDENCE_CHARS = 800
PROCEDURAL_SKILL_OUTCOME_CAPTURE_SOURCE = "supervised_manual_skill_outcome_capture"
PROCEDURAL_SKILL_OUTCOMES = frozenset({"success", "failure"})


@dataclass(frozen=True)
class ProceduralSkillOutcomeCaptureBlueprint:
    schema: str
    session_id: str
    skill_id: str
    skill_provenance_id: str
    skill_provenance_hash: str
    target_payload_hash: str
    outcome: str
    evidence_preview: str
    evidence_fingerprint: str
    evidence_input_chars: int
    blueprint_hash: str
    manual_operator_use: bool = True
    execution_performed_by_proto_mind: bool = False
    process_memory_only: bool = True
    persistence_allowed: bool = False
    skill_mutation_allowed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ProceduralSkillOutcomeCaptureReceipt:
    id: str
    created_at: str
    schema: str
    session_id: str
    skill_id: str
    skill_provenance_id: str
    skill_provenance_hash: str
    target_payload_hash: str
    outcome: str
    evidence_preview: str
    evidence_fingerprint: str
    evidence_input_chars: int
    blueprint_hash: str
    confirmation_method: str
    confirmation_token_hash: str
    event_ids: list[str]
    receipt_hash: str
    operator_confirmation_recorded: bool = True
    operator_reported: bool = True
    manual_operator_use: bool = True
    execution_performed_by_proto_mind: bool = False
    process_memory_only: bool = True
    restart_expiring: bool = True
    persistence_performed: bool = False
    skill_mutation_performed: bool = False
    memory_mutation_performed: bool = False
    session_log_mutation_performed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ProceduralSkillOutcomeCaptureDoctorReport:
    status: str
    pilot_state: str
    receipt_count: int
    success_count: int
    failure_count: int
    event_count: int
    issues: list[str]
    warnings: list[str]


class ProceduralSkillOutcomeCaptureError(RuntimeError):
    pass


class ProceduralSkillOutcomeCaptureBuilder:
    """Builds one exact manual-outcome contract from detached current stores."""

    def __init__(self, *, memory_store: MemoryStore, skill_library: SkillLibrary) -> None:
        self.memory_store = memory_store
        self.skill_library = skill_library

    def build(
        self,
        *,
        session_id: str,
        skill_id: str,
        outcome: str,
        evidence: str,
    ) -> ProceduralSkillOutcomeCaptureBlueprint:
        normalized_session = session_id.strip()
        normalized_skill = skill_id.strip()
        normalized_outcome = outcome.strip().lower()
        normalized_evidence = " ".join(evidence.split())
        if not normalized_session:
            raise ProceduralSkillOutcomeCaptureError("Experience pilot session id is missing.")
        if not normalized_skill:
            raise ProceduralSkillOutcomeCaptureError("Skill id is required.")
        if normalized_outcome not in PROCEDURAL_SKILL_OUTCOMES:
            raise ProceduralSkillOutcomeCaptureError("Outcome must be success or failure.")
        if not normalized_evidence:
            raise ProceduralSkillOutcomeCaptureError("Operator evidence must not be empty.")
        if len(normalized_evidence) > PROCEDURAL_SKILL_OUTCOME_CAPTURE_MAX_EVIDENCE_CHARS:
            raise ProceduralSkillOutcomeCaptureError(
                "Operator evidence exceeds the bounded 800-character input limit."
            )

        memories = self._load_memories()
        skill = self._load_exact_skill(normalized_skill)
        if skill.get("status") != "active":
            raise ProceduralSkillOutcomeCaptureError(
                "Only an active procedural skill can receive a manual outcome record."
            )
        provenance_check = verify_procedural_skill_provenance(
            skill,
            memory_records=memories,
        )
        if not provenance_check.verified or not provenance_check.current_payload_matches:
            details = "; ".join([*provenance_check.issues, *provenance_check.warnings])
            raise ProceduralSkillOutcomeCaptureError(
                "Current skill provenance/payload is not safe for outcome capture."
                + (f" {details}" if details else "")
            )
        provenance = skill.get("provenance")
        if not isinstance(provenance, dict):
            raise ProceduralSkillOutcomeCaptureError("Durable skill provenance is unavailable.")

        redacted_evidence = compact_preview(
            normalized_evidence,
            PROCEDURAL_SKILL_OUTCOME_CAPTURE_MAX_EVIDENCE_CHARS,
        )
        material = {
            "schema": PROCEDURAL_SKILL_OUTCOME_CAPTURE_SCHEMA,
            "session_id": normalized_session,
            "skill_id": normalized_skill,
            "skill_provenance_id": str(provenance.get("id") or ""),
            "skill_provenance_hash": str(provenance.get("provenance_hash") or ""),
            "target_payload_hash": str(provenance.get("target_payload_hash") or ""),
            "outcome": normalized_outcome,
            "evidence_preview": compact_preview(redacted_evidence, 160),
            "evidence_fingerprint": hashlib.sha256(
                redacted_evidence.encode("utf-8")
            ).hexdigest(),
            "evidence_input_chars": len(normalized_evidence),
        }
        return ProceduralSkillOutcomeCaptureBlueprint(
            **material,
            blueprint_hash=_hash_json(material),
        )

    def current_skill_is_valid(self, skill_id: str) -> tuple[bool, str]:
        try:
            memories = self._load_memories()
            skill = self._load_exact_skill(skill_id)
            if skill.get("status") != "active":
                return False, "skill is not active"
            check = verify_procedural_skill_provenance(skill, memory_records=memories)
        except (OSError, TypeError, ValueError, ProceduralSkillOutcomeCaptureError) as exc:
            return False, str(exc)
        if not check.verified or not check.current_payload_matches:
            details = "; ".join([*check.issues, *check.warnings])
            return False, details or "provenance/payload does not verify"
        return True, ""

    def _load_memories(self) -> list[MemoryRecord]:
        try:
            return self.memory_store.load_persistent_memory()
        except (OSError, TypeError, ValueError) as exc:
            raise ProceduralSkillOutcomeCaptureError(
                f"Persistent memory is unreadable: {exc}"
            ) from exc

    def _load_exact_skill(self, skill_id: str) -> dict[str, Any]:
        snapshot = self.skill_library.read_snapshot()
        if snapshot["error"]:
            raise ProceduralSkillOutcomeCaptureError(
                f"Skill Library is unreadable: {snapshot['error']}"
            )
        if snapshot["malformed_count"]:
            raise ProceduralSkillOutcomeCaptureError(
                "Skill Library contains malformed JSONL records."
            )
        matches = [record for record in snapshot["records"] if record.get("id") == skill_id]
        if not matches:
            raise ProceduralSkillOutcomeCaptureError("Skill record was not found.")
        if len(matches) > 1:
            raise ProceduralSkillOutcomeCaptureError(
                "Skill Library contains duplicate matching skill ids."
            )
        return deepcopy(matches[0])


class OperatorReviewedProceduralSkillOutcomeCaptureSession:
    """Stores exact one-off manual outcome receipts in bounded process memory."""

    def __init__(self) -> None:
        self._receipts: dict[str, ProceduralSkillOutcomeCaptureReceipt] = {}
        self._lock = RLock()

    def snapshot(self) -> tuple[dict[str, Any], ...]:
        with self._lock:
            return tuple(deepcopy(receipt.to_dict()) for receipt in self._receipts.values())

    def get(self, identifier: str) -> ProceduralSkillOutcomeCaptureReceipt | None:
        with self._lock:
            return self._receipts.get(identifier)

    def capture(
        self,
        blueprint: ProceduralSkillOutcomeCaptureBlueprint,
        *,
        token: str,
        pilot_state: str,
        append_events: Callable[[list[ExperienceEvent]], Any],
    ) -> ProceduralSkillOutcomeCaptureReceipt:
        with self._lock:
            if pilot_state != "consented":
                raise ProceduralSkillOutcomeCaptureError(
                    "Experience pilot exact session consent is not active."
                )
            if token != procedural_skill_outcome_capture_confirmation_token(blueprint):
                raise ProceduralSkillOutcomeCaptureError(
                    "Manual outcome capture confirmation token mismatch."
                )
            receipt_id = f"skilloutcap_{blueprint.blueprint_hash[:16]}"
            if receipt_id in self._receipts:
                raise ProceduralSkillOutcomeCaptureError(
                    "This exact manual outcome was already captured in the current process."
                )
            if len(self._receipts) >= PROCEDURAL_SKILL_OUTCOME_CAPTURE_MAX_RECEIPTS:
                raise ProceduralSkillOutcomeCaptureError(
                    "Process-memory manual outcome receipt limit reached."
                )
            if any(
                (
                    not blueprint.manual_operator_use,
                    blueprint.execution_performed_by_proto_mind,
                    not blueprint.process_memory_only,
                    blueprint.persistence_allowed,
                    blueprint.skill_mutation_allowed,
                )
            ):
                raise ProceduralSkillOutcomeCaptureError(
                    "Capture blueprint violates the manual-use/no-execution boundary."
                )

            created_at = utc_now_iso()
            events = _build_outcome_events(blueprint, receipt_id, created_at)
            try:
                decision = append_events(events)
            except (OSError, RuntimeError, TypeError, ValueError) as exc:
                raise ProceduralSkillOutcomeCaptureError(
                    f"Bounded process-memory event append failed: {exc}"
                ) from exc
            if not getattr(decision, "accepted", False):
                raise ProceduralSkillOutcomeCaptureError(
                    "Bounded process-memory event append was refused: "
                    f"{getattr(decision, 'reason', 'unknown_reason')}."
                )

            material = {
                **{
                    key: value
                    for key, value in blueprint.to_dict().items()
                    if key
                    not in {
                        "manual_operator_use",
                        "execution_performed_by_proto_mind",
                        "process_memory_only",
                        "persistence_allowed",
                        "skill_mutation_allowed",
                    }
                },
                "id": receipt_id,
                "created_at": created_at,
                "confirmation_method": "exact_session_skill_outcome_token",
                "confirmation_token_hash": hashlib.sha256(token.encode("utf-8")).hexdigest(),
                "event_ids": [event.id for event in events],
            }
            receipt = ProceduralSkillOutcomeCaptureReceipt(
                **material,
                receipt_hash=_hash_json(material),
            )
            self._receipts[receipt.id] = receipt
            return receipt

    def doctor(
        self,
        *,
        builder: ProceduralSkillOutcomeCaptureBuilder,
        events: Iterable[ExperienceEvent | dict[str, Any]],
        pilot_state: str,
    ) -> ProceduralSkillOutcomeCaptureDoctorReport:
        receipts = self.snapshot()
        event_list = [
            event.to_dict() if isinstance(event, ExperienceEvent) else deepcopy(dict(event))
            for event in events
        ]
        event_by_id = {str(event.get("id") or ""): event for event in event_list}
        issues: list[str] = []
        warnings: list[str] = []
        if pilot_state not in {"disabled", "previewed", "consented", "stopped", "expired"}:
            issues.append("Experience pilot state is invalid.")
        if len(receipts) > PROCEDURAL_SKILL_OUTCOME_CAPTURE_MAX_RECEIPTS:
            issues.append("Process-memory manual outcome receipt limit is exceeded.")
        ids = [str(receipt.get("id") or "") for receipt in receipts]
        if any(not value for value in ids) or any(count > 1 for count in Counter(ids).values()):
            issues.append("Manual outcome receipt id is missing or duplicated.")

        for receipt in receipts:
            label = str(receipt.get("id") or "<missing>")
            expected_blueprint_hash = _hash_json(_blueprint_material(receipt))
            if receipt.get("blueprint_hash") != expected_blueprint_hash:
                issues.append(f"Receipt {label} blueprint hash does not verify.")
            if len(str(receipt.get("evidence_fingerprint") or "")) != 64:
                issues.append(f"Receipt {label} evidence fingerprint is invalid.")
            if label != f"skilloutcap_{expected_blueprint_hash[:16]}":
                issues.append(f"Receipt {label} id does not match its blueprint hash.")
            if receipt.get("receipt_hash") != _receipt_hash(receipt):
                issues.append(f"Receipt {label} receipt hash does not verify.")
            if (
                receipt.get("confirmation_method") != "exact_session_skill_outcome_token"
                or receipt.get("operator_confirmation_recorded") is not True
                or len(str(receipt.get("confirmation_token_hash") or "")) != 64
            ):
                issues.append(f"Receipt {label} lacks exact operator confirmation evidence.")
            if any(
                receipt.get(field) is not expected
                for field, expected in {
                    "operator_reported": True,
                    "manual_operator_use": True,
                    "execution_performed_by_proto_mind": False,
                    "process_memory_only": True,
                    "restart_expiring": True,
                    "persistence_performed": False,
                    "skill_mutation_performed": False,
                    "memory_mutation_performed": False,
                    "session_log_mutation_performed": False,
                }.items()
            ):
                issues.append(f"Receipt {label} violates the bounded no-execution boundary.")
            event_ids = receipt.get("event_ids")
            if not isinstance(event_ids, list) or len(event_ids) != 4:
                issues.append(f"Receipt {label} must reference exactly four events.")
            elif any(event_id not in event_by_id for event_id in event_ids):
                issues.append(f"Receipt {label} references missing process-memory events.")
            else:
                linked = [event_by_id[event_id] for event_id in event_ids]
                if not is_valid_procedural_skill_outcome_event_batch(linked):
                    issues.append(f"Receipt {label} event batch violates the manual-outcome contract.")
            valid, reason = builder.current_skill_is_valid(str(receipt.get("skill_id") or ""))
            if not valid:
                warnings.append(f"Receipt {label} current skill is historical/drifted: {reason}.")

        expected_registry = {
            "/experience learning skill-outcome-capture-preview": (True, "none", "low"),
            "/experience learning capture skill-outcome": (False, "session", "medium"),
            "/experience learning skill-outcome-captures": (True, "none", "low"),
            "/experience learning skill-outcome-capture-doctor": (True, "none", "low"),
        }
        registry = {item.prefix: item for item in COMMAND_REGISTRY}
        for prefix, expected in expected_registry.items():
            spec = registry.get(prefix)
            if spec is None or (spec.read_only, spec.mutates, spec.risk) != expected:
                issues.append(f"Registry metadata for {prefix} is missing or unsafe.")
        if PROCEDURAL_SKILL_EXECUTION_INSTALLED:
            issues.append("Procedural skill execution must remain disabled.")
        if not receipts:
            warnings.append("No manual procedural-skill outcome has been captured this process.")
        status = "ERROR" if issues else "WARN" if warnings else "OK"
        return ProceduralSkillOutcomeCaptureDoctorReport(
            status=status,
            pilot_state=pilot_state,
            receipt_count=len(receipts),
            success_count=sum(receipt.get("outcome") == "success" for receipt in receipts),
            failure_count=sum(receipt.get("outcome") == "failure" for receipt in receipts),
            event_count=len(event_list),
            issues=_dedupe(issues),
            warnings=_dedupe(warnings),
        )


def procedural_skill_outcome_capture_confirmation_token(
    blueprint: ProceduralSkillOutcomeCaptureBlueprint,
) -> str:
    return f"CONFIRM-SKILL-OUTCOME-{blueprint.blueprint_hash[:12].upper()}"


def format_procedural_skill_outcome_capture_command(
    command: str,
    *,
    builder: ProceduralSkillOutcomeCaptureBuilder,
    session: OperatorReviewedProceduralSkillOutcomeCaptureSession,
    pilot_state: str,
    pilot_session_id: str,
    events: Iterable[ExperienceEvent | dict[str, Any]],
    append_events: Callable[[list[ExperienceEvent]], Any],
) -> str | None:
    raw = command.strip()
    normalized = " ".join(raw.lower().split())
    prefixes = (
        "/experience learning skill-outcome-capture-preview",
        "/experience learning capture skill-outcome",
        "/experience learning skill-outcome-captures",
        "/experience learning skill-outcome-capture-doctor",
    )
    if not any(normalized == prefix or normalized.startswith(prefix + " ") for prefix in prefixes):
        return None
    if len(raw) > 2_000:
        return _capture_error("Command exceeds the bounded capture input limit.")
    if any(marker in raw for marker in ("\n", ";", "&&", "||")):
        return _capture_error("Command chaining and multi-command input are not allowed.")
    try:
        tokens = shlex.split(_normalize_cli_quotes(raw))
    except ValueError as exc:
        return _capture_error(f"Invalid quoted input: {exc}")

    try:
        if normalized == "/experience learning skill-outcome-capture-doctor":
            return format_procedural_skill_outcome_capture_doctor(
                session.doctor(builder=builder, events=events, pilot_state=pilot_state)
            )
        if normalized == "/experience learning skill-outcome-captures":
            return format_procedural_skill_outcome_captures(session.snapshot())
        if normalized.startswith("/experience learning skill-outcome-captures "):
            if len(tokens) != 4:
                return "Usage: /experience learning skill-outcome-captures [<capture_id>]"
            return format_procedural_skill_outcome_capture_receipt(session.get(tokens[3]))
        if normalized == "/experience learning skill-outcome-capture-preview":
            return _capture_preview_usage()
        if normalized.startswith("/experience learning skill-outcome-capture-preview "):
            request = _parse_preview_tokens(tokens)
            blueprint = builder.build(session_id=pilot_session_id, **request)
            return format_procedural_skill_outcome_capture_preview(blueprint, pilot_state)
        if normalized == "/experience learning capture skill-outcome":
            return _capture_apply_usage()
        if normalized.startswith("/experience learning capture skill-outcome "):
            request, token = _parse_capture_tokens(tokens)
            blueprint = builder.build(session_id=pilot_session_id, **request)
            receipt = session.capture(
                blueprint,
                token=token,
                pilot_state=pilot_state,
                append_events=append_events,
            )
            return format_procedural_skill_outcome_capture_receipt(receipt)
    except ProceduralSkillOutcomeCaptureError as exc:
        return _capture_error(str(exc))
    return None


def format_procedural_skill_outcome_capture_preview(
    blueprint: ProceduralSkillOutcomeCaptureBlueprint,
    pilot_state: str,
) -> str:
    ready = pilot_state == "consented"
    return "\n".join(
        [
            "Proto-Mind Manual Procedural Skill Outcome Capture Preview v1",
            f"Status: {'READY_FOR_EXACT_CONFIRMATION' if ready else 'NOT_READY'}",
            f"pilot_state: {pilot_state}",
            f"session_id: {blueprint.session_id}",
            f"skill_id: {blueprint.skill_id}",
            f"skill_provenance_id: {blueprint.skill_provenance_id}",
            f"outcome: {blueprint.outcome}",
            f"evidence_preview: {blueprint.evidence_preview}",
            f"evidence_fingerprint: {blueprint.evidence_fingerprint}",
            f"evidence_input_chars: {blueprint.evidence_input_chars}",
            f"blueprint_hash: {blueprint.blueprint_hash}",
            "manual_operator_use: true",
            "execution_performed_by_proto_mind: false",
            "process_memory_only: true",
            f"capture_allowed_now: {str(ready).lower()}",
            (
                "Confirmation token: "
                f"{procedural_skill_outcome_capture_confirmation_token(blueprint)}"
            ),
            (
                "- Exact Experience pilot consent is also required; this token authorizes only "
                "the displayed one-off manual outcome."
            ),
            *_capture_boundary(),
        ]
    )


def format_procedural_skill_outcome_captures(
    receipts: Iterable[dict[str, Any]],
) -> str:
    items = list(receipts)
    lines = [
        "Proto-Mind Manual Procedural Skill Outcome Captures v1",
        f"Status: {'OK' if items else 'EMPTY'}",
        f"captures: {len(items)}/{PROCEDURAL_SKILL_OUTCOME_CAPTURE_MAX_RECEIPTS}",
        "Receipts:",
    ]
    if not items:
        lines.append("- none")
    for receipt in items:
        lines.append(
            f"- {receipt.get('id')} | skill={receipt.get('skill_id')} | "
            f"outcome={receipt.get('outcome')} | events={len(receipt.get('event_ids') or [])}"
        )
    lines.extend(_capture_boundary())
    return "\n".join(lines)


def format_procedural_skill_outcome_capture_receipt(
    receipt: ProceduralSkillOutcomeCaptureReceipt | None,
) -> str:
    if receipt is None:
        return _capture_error("Manual outcome capture receipt was not found.")
    return "\n".join(
        [
            "Proto-Mind Manual Procedural Skill Outcome Capture Receipt v1",
            "Status: CAPTURED",
            f"capture_id: {receipt.id}",
            f"created_at: {receipt.created_at}",
            f"session_id: {receipt.session_id}",
            f"skill_id: {receipt.skill_id}",
            f"skill_provenance_id: {receipt.skill_provenance_id}",
            f"outcome: {receipt.outcome}",
            f"evidence_preview: {receipt.evidence_preview}",
            f"evidence_fingerprint: {receipt.evidence_fingerprint}",
            f"event_ids: {', '.join(receipt.event_ids)}",
            f"receipt_hash: {receipt.receipt_hash}",
            "operator_confirmation_recorded: true",
            "manual_operator_use: true",
            "execution_performed_by_proto_mind: false",
            "skill_mutation_performed: false",
            "persistence_performed: false",
            f"Suggested review: /experience learning skill-outcome-review {receipt.skill_id}",
            *_capture_boundary(),
        ]
    )


def format_procedural_skill_outcome_capture_doctor(
    report: ProceduralSkillOutcomeCaptureDoctorReport,
) -> str:
    lines = [
        "Proto-Mind Manual Procedural Skill Outcome Capture Doctor v1",
        f"Status: {report.status}",
        f"mode: {PROCEDURAL_SKILL_OUTCOME_CAPTURE_MODE}",
        f"pilot_state: {report.pilot_state}",
        f"receipts: {report.receipt_count}",
        f"success: {report.success_count}",
        f"failure: {report.failure_count}",
        f"process_memory_events: {report.event_count}",
        "procedure_execution_enabled: false",
    ]
    lines.extend(f"- ERROR: {issue}" for issue in report.issues)
    lines.extend(f"- WARN: {warning}" for warning in report.warnings)
    if not report.issues and not report.warnings:
        lines.append("- Exact confirmation, receipts, events, provenance, and bounds are healthy.")
    lines.extend(_capture_boundary())
    return "\n".join(lines)


def _parse_preview_tokens(tokens: list[str]) -> dict[str, str]:
    if len(tokens) < 7 or tokens[5] != "--evidence":
        raise ProceduralSkillOutcomeCaptureError(_capture_preview_usage())
    return {
        "skill_id": tokens[3],
        "outcome": tokens[4],
        "evidence": " ".join(tokens[6:]),
    }


def _parse_capture_tokens(tokens: list[str]) -> tuple[dict[str, str], str]:
    if len(tokens) < 9 or tokens[3] != "skill-outcome" or tokens[7] != "--evidence":
        raise ProceduralSkillOutcomeCaptureError(_capture_apply_usage())
    return (
        {
            "skill_id": tokens[4],
            "outcome": tokens[5],
            "evidence": " ".join(tokens[8:]),
        },
        tokens[6],
    )


def _build_outcome_events(
    blueprint: ProceduralSkillOutcomeCaptureBlueprint,
    receipt_id: str,
    created_at: str,
) -> list[ExperienceEvent]:
    suffix = blueprint.blueprint_hash[:12]
    turn_id = f"manual-skill-outcome-{suffix}"
    common = {
        "created_at": created_at,
        "session_id": blueprint.session_id,
        "turn_id": turn_id,
        "source": PROCEDURAL_SKILL_OUTCOME_CAPTURE_SOURCE,
        "confidence": 1.0,
    }
    goal = ExperienceEvent(
        id=f"evt_skilloutcome_{suffix}_01_goal_created",
        event_type="goal_created",
        source_event_ids=[],
        payload={
            "goal_id": f"goal_skilloutcome_{suffix}",
            "title_preview": compact_preview(
                f"Record operator-reported manual outcome for {blueprint.skill_id}.", 160
            ),
            "priority": "normal",
            "outcome_capture_id": receipt_id,
        },
        **common,
    )
    plan = ExperienceEvent(
        id=f"evt_skilloutcome_{suffix}_02_plan_created",
        event_type="plan_created",
        source_event_ids=[goal.id],
        payload={
            "plan_id": f"plan_skilloutcome_{suffix}",
            "goal_id": f"goal_skilloutcome_{suffix}",
            "step_count": 1,
            "plan_preview": "Record one already-performed manual procedure outcome.",
            "outcome_capture_id": receipt_id,
        },
        **common,
    )
    called = ExperienceEvent(
        id=f"evt_skilloutcome_{suffix}_03_tool_called",
        event_type="tool_called",
        source_event_ids=[plan.id],
        payload={
            "call_id": f"call_skilloutcome_{suffix}",
            "capability": f"skill:{blueprint.skill_id}",
            "input_preview": "Operator reports a manual use; Proto-Mind did not execute it.",
            "risk": "operator_managed",
            "read_only": False,
            "skill_id": blueprint.skill_id,
            "skill_provenance_id": blueprint.skill_provenance_id,
            "manual_operator_use": True,
            "execution_performed_by_proto_mind": False,
            "outcome_capture_id": receipt_id,
        },
        **common,
    )
    if blueprint.outcome == "success":
        outcome = ExperienceEvent(
            id=f"evt_skilloutcome_{suffix}_04_tool_succeeded",
            event_type="tool_succeeded",
            source_event_ids=[called.id],
            payload={
                "call_id": f"call_skilloutcome_{suffix}",
                "output_preview": blueprint.evidence_preview,
                "verified": True,
                "operator_reported": True,
                "outcome_capture_id": receipt_id,
            },
            **common,
        )
    else:
        outcome = ExperienceEvent(
            id=f"evt_skilloutcome_{suffix}_04_tool_failed",
            event_type="tool_failed",
            source_event_ids=[called.id],
            payload={
                "call_id": f"call_skilloutcome_{suffix}",
                "error_type": "operator_reported_manual_procedure_failure",
                "error_preview": blueprint.evidence_preview,
                "retryable": False,
                "operator_reported": True,
                "outcome_capture_id": receipt_id,
            },
            **common,
        )
    return [goal, plan, called, outcome]


def is_valid_procedural_skill_outcome_event_batch(
    events: Iterable[ExperienceEvent | dict[str, Any]],
) -> bool:
    normalized = [
        event.to_dict() if isinstance(event, ExperienceEvent) else dict(event)
        for event in events
    ]
    if [event.get("event_type") for event in normalized] not in (
        ["goal_created", "plan_created", "tool_called", "tool_succeeded"],
        ["goal_created", "plan_created", "tool_called", "tool_failed"],
    ):
        return False
    if any(
        event.get("source") != PROCEDURAL_SKILL_OUTCOME_CAPTURE_SOURCE
        for event in normalized
    ):
        return False
    called_payload = normalized[2].get("payload")
    outcome_payload = normalized[3].get("payload")
    if not isinstance(called_payload, dict) or not isinstance(outcome_payload, dict):
        return False
    return (
        called_payload.get("manual_operator_use") is True
        and called_payload.get("execution_performed_by_proto_mind") is False
        and outcome_payload.get("operator_reported") is True
    )


def _blueprint_material(receipt: dict[str, Any]) -> dict[str, Any]:
    return {
        key: receipt.get(key)
        for key in (
            "schema",
            "session_id",
            "skill_id",
            "skill_provenance_id",
            "skill_provenance_hash",
            "target_payload_hash",
            "outcome",
            "evidence_preview",
            "evidence_fingerprint",
            "evidence_input_chars",
        )
    }


def _receipt_hash(receipt: dict[str, Any]) -> str:
    material = {
        key: value
        for key, value in receipt.items()
        if key
        not in {
            "receipt_hash",
            "operator_confirmation_recorded",
            "operator_reported",
            "manual_operator_use",
            "execution_performed_by_proto_mind",
            "process_memory_only",
            "restart_expiring",
            "persistence_performed",
            "skill_mutation_performed",
            "memory_mutation_performed",
            "session_log_mutation_performed",
        }
    }
    return _hash_json(material)


def _hash_json(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
    ).hexdigest()


def _normalize_cli_quotes(value: str) -> str:
    return value.translate(str.maketrans({"“": '"', "”": '"', "‘": "'", "’": "'"}))


def _capture_preview_usage() -> str:
    return (
        "Usage: /experience learning skill-outcome-capture-preview "
        '<skill_id> <success|failure> --evidence "<operator evidence>"'
    )


def _capture_apply_usage() -> str:
    return (
        "Usage: /experience learning capture skill-outcome "
        '<skill_id> <success|failure> <exact token> --evidence "<identical evidence>"'
    )


def _capture_error(message: str) -> str:
    return "\n".join(
        [
            "Proto-Mind Manual Procedural Skill Outcome Capture Error",
            "Status: ERROR",
            f"- {message}",
            *_capture_boundary(),
        ]
    )


def _capture_boundary() -> list[str]:
    return [
        "Boundary:",
        "- Records an operator-reported action that already occurred; Proto-Mind did not invoke the skill.",
        "- Evidence and receipts live only in the bounded current-process Experience Pilot and expire on restart.",
        "- No Skill Library, memory, queue, export, session log, model/API, shell, Context Injection, or external action changed.",
    ]


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))
