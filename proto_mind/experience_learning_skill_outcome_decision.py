from __future__ import annotations

from collections import Counter
from copy import deepcopy
from dataclasses import asdict, dataclass
import hashlib
import json
from threading import RLock
from typing import Any, Iterable

from proto_mind.command_registry import COMMAND_REGISTRY
from proto_mind.experience_ledger import ExperienceEvent
from proto_mind.experience_learning_skill_outcome import (
    ProceduralSkillOutcomeReview,
    ProceduralSkillOutcomeReviewer,
)
from proto_mind.experience_learning_skill_outcome_capture import (
    OperatorReviewedProceduralSkillOutcomeCaptureSession,
    procedural_skill_outcome_capture_receipt_hash,
)
from proto_mind.experience_learning_skill_runtime import (
    PROCEDURAL_SKILL_EXECUTION_INSTALLED,
)
from proto_mind.memory_store import MemoryStore
from proto_mind.models import utc_now_iso
from proto_mind.skill_library import SkillLibrary
from proto_mind.experience_learning_skill_restore_reevaluation import (
    restored_skill_requires_post_restore_contract,
)


PROCEDURAL_SKILL_OUTCOME_DECISION_VERSION = 1
PROCEDURAL_SKILL_OUTCOME_DECISION_MODE = (
    "exact_review_and_capture_bound_process_memory_decision"
)
PROCEDURAL_SKILL_OUTCOME_DECISION_MAX_RECEIPTS = 16
PROCEDURAL_SKILL_OUTCOME_DECISIONS = frozenset({"keep", "revise", "archive"})
PROCEDURAL_SKILL_OUTCOME_ALLOWED_DECISIONS = {
    "SUCCESS_CANDIDATE": frozenset({"keep"}),
    "FAILURE_CANDIDATE": frozenset({"revise", "archive"}),
    "MIXED_EVIDENCE": frozenset({"revise", "archive"}),
}


@dataclass(frozen=True)
class ProceduralSkillOutcomeDecisionBlueprint:
    skill_id: str
    provenance_id: str
    outcome_status: str
    decision: str
    selected_signal_id: str
    evidence_event_ids: list[str]
    capture_receipt_ids: list[str]
    capture_receipt_hashes: list[str]
    review_hash: str
    decision_hash: str
    operator_choice_required: bool = True
    terminal_process_decision: bool = True
    future_apply_ready: bool = False
    skill_mutation_allowed: bool = False
    procedure_execution_allowed: bool = False
    persistence_allowed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ProceduralSkillOutcomeDecisionReceipt:
    id: str
    created_at: str
    skill_id: str
    provenance_id: str
    outcome_status: str
    decision: str
    selected_signal_id: str
    evidence_event_ids: list[str]
    capture_receipt_ids: list[str]
    capture_receipt_hashes: list[str]
    review_hash: str
    decision_hash: str
    confirmation_method: str
    confirmation_token_hash: str
    receipt_hash: str
    operator_confirmation_recorded: bool = True
    terminal_process_decision: bool = True
    process_memory_only: bool = True
    restart_expiring: bool = True
    future_apply_ready: bool = False
    skill_mutation_performed: bool = False
    memory_mutation_performed: bool = False
    experience_mutation_performed: bool = False
    persistence_performed: bool = False
    procedure_execution_performed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ProceduralSkillOutcomeDecisionDoctorReport:
    status: str
    receipt_count: int
    keep_count: int
    revise_count: int
    archive_count: int
    current_count: int
    historical_count: int
    issues: list[str]
    warnings: list[str]


class ProceduralSkillOutcomeDecisionError(RuntimeError):
    pass


class ProceduralSkillOutcomeDecisionBuilder:
    """Binds one current outcome review to confirmed v3.5g capture receipts."""

    def __init__(
        self,
        *,
        events: Iterable[ExperienceEvent | dict[str, Any]],
        memory_store: MemoryStore,
        skill_library: SkillLibrary,
        capture_session: OperatorReviewedProceduralSkillOutcomeCaptureSession,
    ) -> None:
        self.events = [
            event.to_dict() if isinstance(event, ExperienceEvent) else deepcopy(dict(event))
            for event in events
        ]
        self.memory_store = memory_store
        self.skill_library = skill_library
        self.capture_session = capture_session

    def review(self, skill_id: str) -> ProceduralSkillOutcomeReview:
        try:
            memories = self.memory_store.load_persistent_memory()
        except (OSError, TypeError, ValueError) as exc:
            raise ProceduralSkillOutcomeDecisionError(
                f"Persistent memory is unreadable: {exc}"
            ) from exc
        snapshot = self.skill_library.read_snapshot()
        reviewer = ProceduralSkillOutcomeReviewer(
            self.events,
            snapshot["records"],
            memories,
            skill_store_error=str(snapshot["error"] or ""),
            malformed_skill_count=int(snapshot["malformed_count"]),
        )
        return reviewer.review(skill_id)

    def build(
        self,
        skill_id: str,
        decision: str,
    ) -> ProceduralSkillOutcomeDecisionBlueprint:
        normalized_decision = decision.strip().lower()
        if normalized_decision not in PROCEDURAL_SKILL_OUTCOME_DECISIONS:
            raise ProceduralSkillOutcomeDecisionError(
                "Decision must be keep, revise, or archive."
            )
        snapshot = self.skill_library.read_snapshot()
        matching = [
            record for record in snapshot["records"] if record.get("id") == skill_id.strip()
        ]
        if len(matching) == 1 and restored_skill_requires_post_restore_contract(
            matching[0]
        ):
            raise ProceduralSkillOutcomeDecisionError(
                "Restored skills require exact new post-restore evidence; the legacy "
                "keep/revise/archive decision path fails closed."
            )
        review = self.review(skill_id.strip())
        allowed = PROCEDURAL_SKILL_OUTCOME_ALLOWED_DECISIONS.get(review.status, frozenset())
        if not allowed:
            details = "; ".join([*review.issues, *review.warnings])
            raise ProceduralSkillOutcomeDecisionError(
                f"Outcome {review.status} is not decision-eligible."
                + (f" {details}" if details else "")
            )
        if normalized_decision not in allowed:
            raise ProceduralSkillOutcomeDecisionError(
                f"Outcome {review.status} permits {', '.join(sorted(allowed))}, "
                f"not {normalized_decision}."
            )
        if not review.selected_signal_id or not review.signals:
            raise ProceduralSkillOutcomeDecisionError(
                "Outcome review has no exact selected evidence signal."
            )

        signal_ids = {signal.event_id for signal in review.signals}
        supporting: list[dict[str, Any]] = []
        supported_event_ids: set[str] = set()
        for receipt in self.capture_session.snapshot():
            if receipt.get("skill_id") != review.skill_id:
                continue
            event_ids = receipt.get("event_ids")
            if not isinstance(event_ids, list) or not signal_ids.intersection(event_ids):
                continue
            if receipt.get("receipt_hash") != procedural_skill_outcome_capture_receipt_hash(
                receipt
            ):
                raise ProceduralSkillOutcomeDecisionError(
                    f"Capture receipt {receipt.get('id') or '<missing>'} hash does not verify."
                )
            if any(
                receipt.get(field) is not expected
                for field, expected in {
                    "operator_confirmation_recorded": True,
                    "operator_reported": True,
                    "manual_operator_use": True,
                    "execution_performed_by_proto_mind": False,
                    "process_memory_only": True,
                    "persistence_performed": False,
                    "skill_mutation_performed": False,
                }.items()
            ):
                raise ProceduralSkillOutcomeDecisionError(
                    f"Capture receipt {receipt.get('id') or '<missing>'} violates its safety boundary."
                )
            supporting.append(receipt)
            supported_event_ids.update(str(value) for value in event_ids)
        if not supporting or review.selected_signal_id not in supported_event_ids:
            raise ProceduralSkillOutcomeDecisionError(
                "Selected outcome signal is not backed by an exact confirmed v3.5g capture receipt."
            )
        if not signal_ids.issubset(supported_event_ids):
            raise ProceduralSkillOutcomeDecisionError(
                "Not every decisive outcome signal is backed by a confirmed capture receipt."
            )

        review_hash = procedural_skill_outcome_review_hash(review)
        capture_ids = sorted(str(receipt.get("id") or "") for receipt in supporting)
        capture_hashes = sorted(str(receipt.get("receipt_hash") or "") for receipt in supporting)
        material = {
            "skill_id": review.skill_id,
            "provenance_id": review.provenance_id,
            "outcome_status": review.status,
            "decision": normalized_decision,
            "selected_signal_id": review.selected_signal_id,
            "evidence_event_ids": sorted(signal_ids),
            "capture_receipt_ids": capture_ids,
            "capture_receipt_hashes": capture_hashes,
            "review_hash": review_hash,
        }
        return ProceduralSkillOutcomeDecisionBlueprint(
            **material,
            decision_hash=_hash_json(material),
        )


class OperatorReviewedProceduralSkillOutcomeDecisionSession:
    """Stores terminal skill-outcome choices in bounded process memory only."""

    def __init__(self) -> None:
        self._receipts: dict[str, ProceduralSkillOutcomeDecisionReceipt] = {}
        self._lock = RLock()

    def snapshot(self) -> tuple[dict[str, Any], ...]:
        with self._lock:
            return tuple(deepcopy(receipt.to_dict()) for receipt in self._receipts.values())

    def get(self, identifier: str) -> ProceduralSkillOutcomeDecisionReceipt | None:
        with self._lock:
            direct = self._receipts.get(identifier)
            if direct is not None:
                return direct
            return next(
                (
                    receipt
                    for receipt in self._receipts.values()
                    if identifier in {receipt.id, receipt.skill_id}
                ),
                None,
            )

    def decide(
        self,
        blueprint: ProceduralSkillOutcomeDecisionBlueprint,
        *,
        token: str,
    ) -> ProceduralSkillOutcomeDecisionReceipt:
        with self._lock:
            if blueprint.skill_id in self._receipts:
                existing = self._receipts[blueprint.skill_id]
                raise ProceduralSkillOutcomeDecisionError(
                    f"Skill already has terminal process decision {existing.decision}."
                )
            if len(self._receipts) >= PROCEDURAL_SKILL_OUTCOME_DECISION_MAX_RECEIPTS:
                raise ProceduralSkillOutcomeDecisionError(
                    "Process-memory skill outcome decision limit reached."
                )
            expected_token = procedural_skill_outcome_decision_confirmation_token(blueprint)
            if token != expected_token:
                raise ProceduralSkillOutcomeDecisionError(
                    "Skill outcome decision confirmation token mismatch."
                )
            if any(
                (
                    not blueprint.operator_choice_required,
                    not blueprint.terminal_process_decision,
                    blueprint.future_apply_ready,
                    blueprint.skill_mutation_allowed,
                    blueprint.procedure_execution_allowed,
                    blueprint.persistence_allowed,
                )
            ):
                raise ProceduralSkillOutcomeDecisionError(
                    "Decision blueprint violates the no-apply/no-execution boundary."
                )

            receipt_id = f"skilloutdec_{blueprint.decision_hash[:16]}"
            material = {
                **{
                    key: value
                    for key, value in blueprint.to_dict().items()
                    if key
                    not in {
                        "operator_choice_required",
                        "terminal_process_decision",
                        "future_apply_ready",
                        "skill_mutation_allowed",
                        "procedure_execution_allowed",
                        "persistence_allowed",
                    }
                },
                "id": receipt_id,
                "created_at": utc_now_iso(),
                "confirmation_method": "exact_current_skill_outcome_decision_token",
                "confirmation_token_hash": hashlib.sha256(token.encode("utf-8")).hexdigest(),
            }
            receipt = ProceduralSkillOutcomeDecisionReceipt(
                **material,
                receipt_hash=_hash_json(material),
            )
            self._receipts[blueprint.skill_id] = receipt
            return receipt

    def doctor(
        self,
        builder: ProceduralSkillOutcomeDecisionBuilder,
    ) -> ProceduralSkillOutcomeDecisionDoctorReport:
        receipts = self.snapshot()
        issues: list[str] = []
        warnings: list[str] = []
        counts = Counter(str(receipt.get("decision") or "") for receipt in receipts)
        if len(receipts) > PROCEDURAL_SKILL_OUTCOME_DECISION_MAX_RECEIPTS:
            issues.append("Process-memory skill outcome decision limit is exceeded.")
        ids = [str(receipt.get("id") or "") for receipt in receipts]
        skill_ids = [str(receipt.get("skill_id") or "") for receipt in receipts]
        if any(not value for value in ids) or any(count > 1 for count in Counter(ids).values()):
            issues.append("Skill outcome decision receipt id is missing or duplicated.")
        if any(not value for value in skill_ids) or any(
            count > 1 for count in Counter(skill_ids).values()
        ):
            issues.append("Skill outcome decision skill id is missing or duplicated.")

        current_count = 0
        historical_count = 0
        for receipt in receipts:
            label = str(receipt.get("id") or "<missing>")
            decision = str(receipt.get("decision") or "")
            outcome_status = str(receipt.get("outcome_status") or "")
            allowed = PROCEDURAL_SKILL_OUTCOME_ALLOWED_DECISIONS.get(
                outcome_status, frozenset()
            )
            if decision not in PROCEDURAL_SKILL_OUTCOME_DECISIONS or decision not in allowed:
                issues.append(f"Receipt {label} decision does not match its outcome status.")
            decision_hash = str(receipt.get("decision_hash") or "")
            if len(decision_hash) != 64 or label != f"skilloutdec_{decision_hash[:16]}":
                issues.append(f"Receipt {label} has invalid decision hash identity.")
            if decision_hash != _hash_json(_decision_material(receipt)):
                issues.append(f"Receipt {label} decision hash does not verify.")
            if receipt.get("receipt_hash") != procedural_skill_outcome_decision_receipt_hash(
                receipt
            ):
                issues.append(f"Receipt {label} receipt hash does not verify.")
            if (
                receipt.get("confirmation_method")
                != "exact_current_skill_outcome_decision_token"
                or receipt.get("operator_confirmation_recorded") is not True
                or len(str(receipt.get("confirmation_token_hash") or "")) != 64
            ):
                issues.append(f"Receipt {label} lacks exact operator confirmation evidence.")
            if not receipt.get("selected_signal_id") or not receipt.get("evidence_event_ids"):
                issues.append(f"Receipt {label} lacks bounded review evidence identity.")
            elif receipt.get("selected_signal_id") not in receipt.get("evidence_event_ids"):
                issues.append(f"Receipt {label} selected signal is outside its evidence ids.")
            if not receipt.get("capture_receipt_ids") or not receipt.get(
                "capture_receipt_hashes"
            ):
                issues.append(f"Receipt {label} lacks confirmed capture receipt evidence.")
            if any(
                receipt.get(field) is not expected
                for field, expected in {
                    "terminal_process_decision": True,
                    "process_memory_only": True,
                    "restart_expiring": True,
                    "future_apply_ready": False,
                    "skill_mutation_performed": False,
                    "memory_mutation_performed": False,
                    "experience_mutation_performed": False,
                    "persistence_performed": False,
                    "procedure_execution_performed": False,
                }.items()
            ):
                issues.append(f"Receipt {label} violates the no-apply/no-execution boundary.")
            try:
                current = builder.build(str(receipt.get("skill_id") or ""), decision)
            except ProceduralSkillOutcomeDecisionError as exc:
                historical_count += 1
                warnings.append(f"Receipt {label} is historical: {exc}")
            else:
                if current.decision_hash == decision_hash:
                    current_count += 1
                else:
                    historical_count += 1
                    warnings.append(
                        f"Receipt {label} is historical; current outcome evidence has changed."
                    )

        expected_registry = {
            "/experience learning skill-outcome-decision-preview": (True, "none", "low"),
            "/experience learning decide skill-outcome": (False, "session", "medium"),
            "/experience learning skill-outcome-decisions": (True, "none", "low"),
            "/experience learning skill-outcome-decision-doctor": (True, "none", "low"),
        }
        registry = {item.prefix: item for item in COMMAND_REGISTRY}
        for prefix, expected in expected_registry.items():
            spec = registry.get(prefix)
            if spec is None or (spec.read_only, spec.mutates, spec.risk) != expected:
                issues.append(f"Registry metadata for {prefix} is missing or unsafe.")
        if PROCEDURAL_SKILL_EXECUTION_INSTALLED:
            issues.append("Procedural skill execution must remain disabled.")
        if not receipts:
            warnings.append("No procedural skill outcome decision has been recorded this process.")
        status = "ERROR" if issues else "WARN" if warnings else "OK"
        return ProceduralSkillOutcomeDecisionDoctorReport(
            status=status,
            receipt_count=len(receipts),
            keep_count=counts["keep"],
            revise_count=counts["revise"],
            archive_count=counts["archive"],
            current_count=current_count,
            historical_count=historical_count,
            issues=_dedupe(issues),
            warnings=_dedupe(warnings),
        )


def procedural_skill_outcome_review_hash(review: ProceduralSkillOutcomeReview) -> str:
    material = {
        "skill_id": review.skill_id,
        "provenance_id": review.provenance_id,
        "applied_at": review.applied_at,
        "status": review.status,
        "matching_manual_use_count": review.matching_manual_use_count,
        "later_evidence_count": review.later_evidence_count,
        "selected_signal_id": review.selected_signal_id,
        "signals": [
            {
                "event_id": signal.event_id,
                "event_type": signal.event_type,
                "signal": signal.signal,
                "use_event_id": signal.use_event_id,
            }
            for signal in review.signals
        ],
    }
    return _hash_json(material)


def procedural_skill_outcome_decision_confirmation_token(
    blueprint: ProceduralSkillOutcomeDecisionBlueprint,
) -> str:
    return (
        f"CONFIRM-SKILL-{blueprint.decision.upper()}-"
        f"{blueprint.decision_hash[:12].upper()}"
    )


def procedural_skill_outcome_decision_receipt_hash(receipt: dict[str, Any]) -> str:
    material = {
        key: value
        for key, value in receipt.items()
        if key
        not in {
            "receipt_hash",
            "operator_confirmation_recorded",
            "terminal_process_decision",
            "process_memory_only",
            "restart_expiring",
            "future_apply_ready",
            "skill_mutation_performed",
            "memory_mutation_performed",
            "experience_mutation_performed",
            "persistence_performed",
            "procedure_execution_performed",
        }
    }
    return _hash_json(material)


def format_procedural_skill_outcome_decision_command(
    command: str,
    *,
    builder: ProceduralSkillOutcomeDecisionBuilder,
    session: OperatorReviewedProceduralSkillOutcomeDecisionSession,
) -> str | None:
    raw = command.strip()
    normalized = " ".join(raw.lower().split())
    prefixes = (
        "/experience learning skill-outcome-decision-preview",
        "/experience learning decide skill-outcome",
        "/experience learning skill-outcome-decisions",
        "/experience learning skill-outcome-decision-doctor",
    )
    lowered = raw.lower()
    if not any(
        lowered.startswith(prefix)
        and (len(lowered) == len(prefix) or lowered[len(prefix)] in " \t\n;&|")
        for prefix in prefixes
    ):
        return None
    if any(marker in raw for marker in ("\n", ";", "&&", "||")):
        return _decision_error("Command chaining and multi-command input are not allowed.")
    parts = raw.split()

    if normalized == "/experience learning skill-outcome-decision-doctor":
        return format_procedural_skill_outcome_decision_doctor(session.doctor(builder))
    if normalized == "/experience learning skill-outcome-decisions":
        return format_procedural_skill_outcome_decisions(session.snapshot())
    if normalized.startswith("/experience learning skill-outcome-decisions "):
        if len(parts) != 4:
            return "Usage: /experience learning skill-outcome-decisions [<skill_id|receipt_id>]"
        return format_procedural_skill_outcome_decision_receipt(session.get(parts[3]))
    if normalized == "/experience learning skill-outcome-decision-preview":
        return _decision_preview_usage()
    if normalized.startswith("/experience learning skill-outcome-decision-preview "):
        if len(parts) != 5:
            return _decision_preview_usage()
        try:
            blueprint = builder.build(parts[3], parts[4])
        except ProceduralSkillOutcomeDecisionError as exc:
            return _decision_error(str(exc))
        return format_procedural_skill_outcome_decision_preview(blueprint, session)
    if normalized == "/experience learning decide skill-outcome":
        return _decision_apply_usage()
    if normalized.startswith("/experience learning decide skill-outcome "):
        if len(parts) != 7:
            return _decision_apply_usage()
        decision, skill_id, token = parts[4].lower(), parts[5], parts[6]
        try:
            blueprint = builder.build(skill_id, decision)
            receipt = session.decide(blueprint, token=token)
        except ProceduralSkillOutcomeDecisionError as exc:
            return _decision_error(str(exc))
        return format_procedural_skill_outcome_decision_recorded(receipt)
    return None


def format_procedural_skill_outcome_decision_preview(
    blueprint: ProceduralSkillOutcomeDecisionBlueprint,
    session: OperatorReviewedProceduralSkillOutcomeDecisionSession,
) -> str:
    existing = session.get(blueprint.skill_id)
    confirmable = existing is None
    lines = [
        "Proto-Mind Procedural Skill Outcome Decision Preview v1",
        f"Status: {'CONFIRMABLE' if confirmable else 'NOT CONFIRMABLE'}",
        f"skill_id: {blueprint.skill_id}",
        f"provenance_id: {blueprint.provenance_id}",
        f"outcome_status: {blueprint.outcome_status}",
        f"decision: {blueprint.decision}",
        f"selected_signal_id: {blueprint.selected_signal_id}",
        f"evidence_event_ids: {', '.join(blueprint.evidence_event_ids)}",
        f"capture_receipt_ids: {', '.join(blueprint.capture_receipt_ids)}",
        f"review_hash: {blueprint.review_hash}",
        f"decision_hash: {blueprint.decision_hash}",
        "future_apply_ready: false",
        "skill_mutation_allowed: false",
        "procedure_execution_allowed: false",
    ]
    if existing is not None:
        lines.append(
            f"- Existing terminal process decision: {existing.decision} ({existing.id})."
        )
    else:
        token = procedural_skill_outcome_decision_confirmation_token(blueprint)
        lines.extend(
            [
                f"confirmation_token: {token}",
                "Exact decision command:",
                (
                    f"/experience learning decide skill-outcome {blueprint.decision} "
                    f"{blueprint.skill_id} {token}"
                ),
            ]
        )
    lines.extend(_decision_boundary())
    return "\n".join(lines)


def format_procedural_skill_outcome_decision_recorded(
    receipt: ProceduralSkillOutcomeDecisionReceipt,
) -> str:
    return "\n".join(
        [
            "Proto-Mind Procedural Skill Outcome Decision v1",
            "Status: RECORDED IN PROCESS MEMORY",
            f"receipt_id: {receipt.id}",
            f"skill_id: {receipt.skill_id}",
            f"outcome_status: {receipt.outcome_status}",
            f"decision: {receipt.decision}",
            f"selected_signal_id: {receipt.selected_signal_id}",
            f"created_at: {receipt.created_at}",
            "future_apply_ready: false",
            "skill_mutation_performed: false",
            "procedure_execution_performed: false",
            *_decision_boundary(),
        ]
    )


def format_procedural_skill_outcome_decisions(
    receipts: Iterable[dict[str, Any]],
) -> str:
    items = list(receipts)
    lines = [
        "Proto-Mind Procedural Skill Outcome Decisions v1",
        f"Status: {'OK' if items else 'EMPTY'}",
        f"receipts: {len(items)}/{PROCEDURAL_SKILL_OUTCOME_DECISION_MAX_RECEIPTS}",
    ]
    if not items:
        lines.append("- none")
    for receipt in items:
        lines.append(
            f"- {receipt.get('id')} | {receipt.get('decision')} | "
            f"{receipt.get('skill_id')} | outcome={receipt.get('outcome_status')}"
        )
    lines.extend(_decision_boundary())
    return "\n".join(lines)


def format_procedural_skill_outcome_decision_receipt(
    receipt: ProceduralSkillOutcomeDecisionReceipt | None,
) -> str:
    if receipt is None:
        return _decision_error("Procedural skill outcome decision receipt was not found.")
    lines = [
        "Proto-Mind Procedural Skill Outcome Decision Receipt v1",
        "Status: OK",
    ]
    lines.extend(f"{key}: {value}" for key, value in receipt.to_dict().items())
    lines.extend(_decision_boundary())
    return "\n".join(lines)


def format_procedural_skill_outcome_decision_doctor(
    report: ProceduralSkillOutcomeDecisionDoctorReport,
) -> str:
    lines = [
        "Proto-Mind Procedural Skill Outcome Decision Doctor v1",
        f"Status: {report.status}",
        f"mode: {PROCEDURAL_SKILL_OUTCOME_DECISION_MODE}",
        f"receipts: {report.receipt_count}/{PROCEDURAL_SKILL_OUTCOME_DECISION_MAX_RECEIPTS}",
        f"keep: {report.keep_count}",
        f"revise: {report.revise_count}",
        f"archive: {report.archive_count}",
        f"current: {report.current_count}",
        f"historical: {report.historical_count}",
        "future_apply_ready: false",
        "procedure_execution_enabled: false",
    ]
    lines.extend(f"- ERROR: {issue}" for issue in report.issues)
    lines.extend(f"- WARN: {warning}" for warning in report.warnings)
    if not report.issues and not report.warnings:
        lines.append("- Exact review, capture, decision, Registry, and no-mutation boundaries are healthy.")
    lines.extend(_decision_boundary())
    return "\n".join(lines)


def _decision_material(receipt: dict[str, Any]) -> dict[str, Any]:
    return {
        key: receipt.get(key)
        for key in (
            "skill_id",
            "provenance_id",
            "outcome_status",
            "decision",
            "selected_signal_id",
            "evidence_event_ids",
            "capture_receipt_ids",
            "capture_receipt_hashes",
            "review_hash",
        )
    }


def _decision_preview_usage() -> str:
    return (
        "Usage: /experience learning skill-outcome-decision-preview "
        "<skill_id> <keep|revise|archive>"
    )


def _decision_apply_usage() -> str:
    return (
        "Usage: /experience learning decide skill-outcome "
        "<keep|revise|archive> <skill_id> <exact token>"
    )


def _decision_error(message: str) -> str:
    return "\n".join(
        [
            "Proto-Mind Procedural Skill Outcome Decision Error",
            "Status: ERROR",
            f"- {message}",
            *_decision_boundary(),
        ]
    )


def _decision_boundary() -> list[str]:
    return [
        "Boundary:",
        "- This is an operator decision receipt, not authorization or readiness to mutate the Skill Library.",
        "- Receipt state is bounded process memory only and expires on restart.",
        "- No skill, memory, Experience event, queue, export, session log, model/API, shell, Context Injection, or external action changed.",
    ]


def _hash_json(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
    ).hexdigest()


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))
