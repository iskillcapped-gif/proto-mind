from __future__ import annotations

from collections import Counter
from copy import deepcopy
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Iterable

from proto_mind.command_registry import COMMAND_REGISTRY
from proto_mind.experience_explainability import ExperienceTraceIndex
from proto_mind.experience_ledger import ExperienceEvent
from proto_mind.experience_learning_skill_runtime import (
    PROCEDURAL_SKILL_EXECUTION_INSTALLED,
)
from proto_mind.memory_store import MemoryStore
from proto_mind.models import MemoryRecord
from proto_mind.skill_library import SkillLibrary
from proto_mind.skill_provenance import verify_procedural_skill_provenance


PROCEDURAL_SKILL_OUTCOME_VERSION = 1
PROCEDURAL_SKILL_OUTCOME_MODE = "read_only_manual_use_exact_lineage_review"
PROCEDURAL_SKILL_OUTCOME_STATUSES = frozenset(
    {
        "SUCCESS_CANDIDATE",
        "FAILURE_CANDIDATE",
        "MIXED_EVIDENCE",
        "NEEDS_MORE_EVIDENCE",
        "NOT_FOUND",
        "ERROR",
    }
)


@dataclass(frozen=True)
class ProceduralSkillOutcomeSignal:
    event_id: str
    event_type: str
    created_at: str
    signal: str
    reason: str
    use_event_id: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ProceduralSkillOutcomeReview:
    status: str
    skill_id: str
    provenance_id: str
    applied_at: str
    trace_status: str
    matching_manual_use_count: int
    later_evidence_count: int
    selected_signal_id: str
    signals: list[ProceduralSkillOutcomeSignal]
    checks: dict[str, bool]
    issues: list[str]
    warnings: list[str]
    uses_metric_ignored: bool = True
    mutation_performed: bool = False
    automatic_skill_update_allowed: bool = False
    skill_execution_performed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ProceduralSkillOutcomeDoctorReport:
    status: str
    event_count: int
    skill_count: int
    provenanced_skill_count: int
    reviewable_skill_count: int
    issues: list[str]
    warnings: list[str]


class ProceduralSkillOutcomeReviewer:
    """Reviews exact operator-reported skill outcomes without invoking a procedure."""

    def __init__(
        self,
        events: Iterable[ExperienceEvent | dict[str, Any]],
        skill_records: Iterable[dict[str, Any]],
        memory_records: Iterable[MemoryRecord],
        *,
        skill_store_error: str = "",
        malformed_skill_count: int = 0,
    ) -> None:
        self.events = [
            event.to_dict() if isinstance(event, ExperienceEvent) else deepcopy(dict(event))
            for event in events
        ]
        self.skills = [deepcopy(dict(record)) for record in skill_records]
        self.memories = list(memory_records)
        self.skill_store_error = skill_store_error
        self.malformed_skill_count = malformed_skill_count
        self.index = ExperienceTraceIndex(self.events)
        self.trace_report = self.index.doctor()
        self._event_order = {
            str(event.get("id") or ""): position
            for position, event in enumerate(self.events)
        }

    def review(self, skill_id: str) -> ProceduralSkillOutcomeReview:
        identifier = skill_id.strip()
        matches = [record for record in self.skills if record.get("id") == identifier]
        checks = {
            "skill_found": len(matches) == 1,
            "durable_provenance_verified": False,
            "confirmed_payload_current": False,
            "experience_trace_valid": self.trace_report.status != "ERROR",
            "manual_use_anchor_found": False,
            "proto_mind_execution_absent": True,
            "decisive_outcome_found": False,
        }
        if not matches:
            return self._result(
                status="NOT_FOUND",
                skill_id=identifier,
                checks=checks,
                issues=["Skill record was not found."],
            )
        if len(matches) > 1:
            return self._result(
                status="ERROR",
                skill_id=identifier,
                checks=checks,
                issues=["Skill Library contains duplicate matching skill ids."],
            )
        skill = matches[0]
        provenance_check = verify_procedural_skill_provenance(
            skill,
            memory_records=self.memories,
        )
        checks["durable_provenance_verified"] = provenance_check.verified
        checks["confirmed_payload_current"] = provenance_check.current_payload_matches
        provenance = skill.get("provenance") if isinstance(skill.get("provenance"), dict) else {}
        provenance_id = str(provenance.get("id") or "")
        applied_at = str(provenance.get("applied_at") or "")
        if not provenance_check.verified or not provenance_check.current_payload_matches:
            issues = list(provenance_check.issues)
            if not provenance_check.current_payload_matches:
                issues.append(
                    "Current skill fields do not match the operator-confirmed procedure payload."
                )
            if not issues:
                issues.extend(
                    provenance_check.warnings
                    or ["Durable procedural skill provenance is unavailable."]
                )
            return self._result(
                status="ERROR",
                skill_id=identifier,
                provenance_id=provenance_id,
                applied_at=applied_at,
                checks=checks,
                issues=issues,
            )
        if self.trace_report.status == "ERROR":
            return self._result(
                status="ERROR",
                skill_id=identifier,
                provenance_id=provenance_id,
                applied_at=applied_at,
                checks=checks,
                issues=list(self.trace_report.issues),
                warnings=list(self.trace_report.warnings),
            )

        warnings = list(provenance_check.warnings) + list(self.trace_report.warnings)
        exact_capability = f"skill:{identifier}"
        candidate_calls = [
            event
            for event in self.events
            if event.get("event_type") == "tool_called"
            and _payload(event).get("capability") == exact_capability
            and _event_is_later(event, applied_at)
        ]
        unsafe_execution_claims = [
            event
            for event in candidate_calls
            if _payload(event).get("execution_performed_by_proto_mind") is not False
        ]
        checks["proto_mind_execution_absent"] = not unsafe_execution_claims
        if unsafe_execution_claims:
            return self._result(
                status="ERROR",
                skill_id=identifier,
                provenance_id=provenance_id,
                applied_at=applied_at,
                checks=checks,
                issues=[
                    "Outcome review only accepts manual-use evidence with "
                    "execution_performed_by_proto_mind=false."
                ],
            )

        use_events: list[dict[str, Any]] = []
        for event in candidate_calls:
            payload = _payload(event)
            if (
                payload.get("skill_id") == identifier
                and payload.get("skill_provenance_id") == provenance_id
                and payload.get("manual_operator_use") is True
                and payload.get("execution_performed_by_proto_mind") is False
            ):
                use_events.append(event)
            else:
                warnings.append(
                    f"Skill use event {event.get('id')} lacks the exact manual-use/provenance contract."
                )
        checks["manual_use_anchor_found"] = bool(use_events)

        signals: list[ProceduralSkillOutcomeSignal] = []
        later_evidence_ids: set[str] = set()
        for use_event in use_events:
            use_id = str(use_event.get("id") or "")
            call_id = str(_payload(use_event).get("call_id") or "")
            for event in self.events:
                event_id = str(event.get("id") or "")
                if event_id == use_id or not _event_is_later(event, applied_at):
                    continue
                explanation = self.index.explain(event_id)
                if explanation is None or use_id not in explanation.lineage_event_ids:
                    continue
                later_evidence_ids.add(event_id)
                event_type = str(event.get("event_type") or "")
                payload = _payload(event)
                if event_type == "tool_succeeded" and payload.get("call_id") == call_id:
                    if payload.get("operator_reported") is True and payload.get("verified") is True:
                        signals.append(
                            ProceduralSkillOutcomeSignal(
                                event_id=event_id,
                                event_type=event_type,
                                created_at=str(event.get("created_at") or ""),
                                signal="SUCCESS_EVIDENCE",
                                reason=(
                                    "A verified operator-reported success descends from the exact "
                                    "manual skill-use anchor."
                                ),
                                use_event_id=use_id,
                            )
                        )
                    else:
                        warnings.append(
                            f"Success event {event_id} is not both operator-reported and verified."
                        )
                elif event_type == "tool_failed" and payload.get("call_id") == call_id:
                    if payload.get("operator_reported") is True:
                        signals.append(
                            ProceduralSkillOutcomeSignal(
                                event_id=event_id,
                                event_type=event_type,
                                created_at=str(event.get("created_at") or ""),
                                signal="FAILURE_EVIDENCE",
                                reason=(
                                    "An operator-reported failure descends from the exact manual "
                                    "skill-use anchor."
                                ),
                                use_event_id=use_id,
                            )
                        )
                    else:
                        warnings.append(
                            f"Failure event {event_id} is not explicitly operator-reported."
                        )
                elif event_type == "user_corrected":
                    signals.append(
                        ProceduralSkillOutcomeSignal(
                            event_id=event_id,
                            event_type=event_type,
                            created_at=str(event.get("created_at") or ""),
                            signal="FAILURE_EVIDENCE",
                            reason=(
                                "An explicit operator correction descends from the manual "
                                "skill-use lineage."
                            ),
                            use_event_id=use_id,
                        )
                    )

        signals = _dedupe_signals(signals)
        signals.sort(key=lambda item: self._event_order.get(item.event_id, -1))
        kinds = {signal.signal for signal in signals}
        checks["decisive_outcome_found"] = bool(kinds)
        selected_signal_id = signals[-1].event_id if signals else ""
        if not use_events:
            warnings.append(
                "No later exact manual-use Experience event references this skill and provenance id."
            )
            status = "NEEDS_MORE_EVIDENCE"
        elif not kinds:
            warnings.append(
                "Manual-use evidence exists, but no verified operator-reported outcome is linked to it."
            )
            status = "NEEDS_MORE_EVIDENCE"
        elif kinds == {"SUCCESS_EVIDENCE"}:
            status = "SUCCESS_CANDIDATE"
        elif kinds == {"FAILURE_EVIDENCE"}:
            status = "FAILURE_CANDIDATE"
        else:
            status = "MIXED_EVIDENCE"
            warnings.append("Both success and failure evidence exist; no automatic conclusion is safe.")
        return self._result(
            status=status,
            skill_id=identifier,
            provenance_id=provenance_id,
            applied_at=applied_at,
            trace_status=self.trace_report.status,
            matching_manual_use_count=len(use_events),
            later_evidence_count=len(later_evidence_ids),
            selected_signal_id=selected_signal_id,
            signals=signals,
            checks=checks,
            warnings=warnings,
        )

    def doctor(self) -> ProceduralSkillOutcomeDoctorReport:
        issues = list(self.trace_report.issues)
        warnings = list(self.trace_report.warnings)
        if self.skill_store_error:
            issues.append(f"Skill Library is unreadable: {self.skill_store_error}")
        if self.malformed_skill_count:
            issues.append(
                f"Skill Library contains {self.malformed_skill_count} malformed JSONL record(s)."
            )
        ids = [str(record.get("id") or "") for record in self.skills]
        duplicates = sorted(value for value, count in Counter(ids).items() if value and count > 1)
        if any(not value for value in ids):
            issues.append("Skill Library contains a record without an id.")
        if duplicates:
            issues.append("Skill Library contains duplicate ids: " + ", ".join(duplicates) + ".")

        provenanced = [record for record in self.skills if record.get("provenance") is not None]
        valid: list[dict[str, Any]] = []
        for record in provenanced:
            check = verify_procedural_skill_provenance(
                record,
                memory_records=self.memories,
            )
            if not check.verified or not check.current_payload_matches:
                issues.append(
                    f"Skill {record.get('id') or '<missing>'} provenance/payload is not outcome-review safe."
                )
            else:
                valid.append(record)
        reviewable = 0
        if not issues:
            reviewable = sum(
                1
                for record in valid
                if self.review(str(record.get("id") or "")).matching_manual_use_count
            )
        if valid and not reviewable:
            warnings.append(
                "Provenanced skills exist, but no exact manual-use outcome evidence is reviewable."
            )

        for prefix in (
            "/experience learning skill-outcome-review",
            "/experience learning skill-outcome-doctor",
        ):
            spec = next((item for item in COMMAND_REGISTRY if item.prefix == prefix), None)
            if spec is None or not spec.read_only or spec.mutates != "none":
                issues.append(f"Registry metadata for {prefix} is missing or unsafe.")
        if PROCEDURAL_SKILL_EXECUTION_INSTALLED:
            issues.append("Procedural skill execution must remain disabled.")
        status = "ERROR" if issues else "WARN" if warnings else "OK"
        return ProceduralSkillOutcomeDoctorReport(
            status=status,
            event_count=len(self.events),
            skill_count=len(self.skills),
            provenanced_skill_count=len(provenanced),
            reviewable_skill_count=reviewable,
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
        applied_at: str = "",
        trace_status: str | None = None,
        matching_manual_use_count: int = 0,
        later_evidence_count: int = 0,
        selected_signal_id: str = "",
        signals: list[ProceduralSkillOutcomeSignal] | None = None,
        issues: list[str] | None = None,
        warnings: list[str] | None = None,
    ) -> ProceduralSkillOutcomeReview:
        return ProceduralSkillOutcomeReview(
            status=status,
            skill_id=skill_id,
            provenance_id=provenance_id,
            applied_at=applied_at,
            trace_status=trace_status or self.trace_report.status,
            matching_manual_use_count=matching_manual_use_count,
            later_evidence_count=later_evidence_count,
            selected_signal_id=selected_signal_id,
            signals=list(signals or []),
            checks=checks,
            issues=_dedupe(list(issues or [])),
            warnings=_dedupe(list(warnings or [])),
        )


def format_procedural_skill_outcome_command(
    command: str,
    *,
    events: Iterable[ExperienceEvent | dict[str, Any]],
    memory_store: MemoryStore | None,
    skill_library: SkillLibrary,
) -> str | None:
    raw = command.strip()
    normalized = " ".join(raw.lower().split())
    prefixes = (
        "/experience learning skill-outcome-review",
        "/experience learning skill-outcome-doctor",
    )
    if not any(normalized == prefix or normalized.startswith(prefix + " ") for prefix in prefixes):
        return None
    if any(marker in raw for marker in ("\n", ";", "&&", "||")):
        return _outcome_error("Command chaining and multi-command input are not allowed.")
    if memory_store is None:
        return _outcome_error("MemoryStore is unavailable from the shared handler.")
    try:
        memories = memory_store.load_persistent_memory()
    except (OSError, TypeError, ValueError) as exc:
        return _outcome_error(f"Persistent memory is unreadable: {exc}")
    snapshot = skill_library.read_snapshot()
    reviewer = ProceduralSkillOutcomeReviewer(
        events,
        snapshot["records"],
        memories,
        skill_store_error=str(snapshot["error"] or ""),
        malformed_skill_count=int(snapshot["malformed_count"]),
    )
    if normalized == "/experience learning skill-outcome-doctor":
        return format_procedural_skill_outcome_doctor(reviewer.doctor())
    if normalized == "/experience learning skill-outcome-review":
        return "Usage: /experience learning skill-outcome-review <skill_id>"
    parts = raw.split()
    if len(parts) != 4:
        return "Usage: /experience learning skill-outcome-review <skill_id>"
    return format_procedural_skill_outcome_review(reviewer.review(parts[3]))


def format_procedural_skill_outcome_review(
    review: ProceduralSkillOutcomeReview,
) -> str:
    lines = [
        "Proto-Mind Procedural Skill Outcome Review v1",
        f"Status: {review.status}",
        f"skill_id: {review.skill_id or 'missing'}",
        f"provenance_id: {review.provenance_id or 'unavailable'}",
        f"applied_at: {review.applied_at or 'unavailable'}",
        f"trace_status: {review.trace_status}",
        f"matching_manual_uses: {review.matching_manual_use_count}",
        f"later_evidence_events: {review.later_evidence_count}",
        f"selected_signal_id: {review.selected_signal_id or 'none'}",
        "uses_metric_ignored: true",
        "skill_execution_performed: false",
        "Checks:",
    ]
    lines.extend(f"- {name}: {str(value).lower()}" for name, value in review.checks.items())
    lines.append("Outcome signals:")
    if not review.signals:
        lines.append("- none")
    for signal in review.signals:
        lines.append(
            f"- {signal.signal} | {signal.event_type} ({signal.event_id}) | "
            f"use={signal.use_event_id}: {signal.reason}"
        )
    lines.extend(f"- ERROR: {issue}" for issue in review.issues)
    lines.extend(f"- WARN: {warning}" for warning in review.warnings)
    lines.extend(["Suggested manual review:", *_outcome_suggestion(review), *_outcome_boundary()])
    return "\n".join(lines)


def format_procedural_skill_outcome_doctor(
    report: ProceduralSkillOutcomeDoctorReport,
) -> str:
    lines = [
        "Proto-Mind Procedural Skill Outcome Doctor v1",
        f"Status: {report.status}",
        f"mode: {PROCEDURAL_SKILL_OUTCOME_MODE}",
        f"events: {report.event_count}",
        f"skills: {report.skill_count}",
        f"provenanced_skills: {report.provenanced_skill_count}",
        f"reviewable_skills: {report.reviewable_skill_count}",
        "procedure_execution_enabled: false",
    ]
    lines.extend(f"- ERROR: {issue}" for issue in report.issues)
    lines.extend(f"- WARN: {warning}" for warning in report.warnings)
    if not report.issues and not report.warnings:
        lines.append(
            "- Exact manual-use lineage, provenance, Registry, and no-execution boundaries are healthy."
        )
    lines.extend(_outcome_boundary())
    return "\n".join(lines)


def _payload(event: dict[str, Any]) -> dict[str, Any]:
    payload = event.get("payload")
    return payload if isinstance(payload, dict) else {}


def _event_is_later(event: dict[str, Any], applied_at: str) -> bool:
    try:
        return datetime.fromisoformat(str(event.get("created_at") or "").replace("Z", "+00:00")) > datetime.fromisoformat(
            applied_at.replace("Z", "+00:00")
        )
    except (TypeError, ValueError):
        return False


def _dedupe_signals(
    signals: list[ProceduralSkillOutcomeSignal],
) -> list[ProceduralSkillOutcomeSignal]:
    result: list[ProceduralSkillOutcomeSignal] = []
    seen: set[tuple[str, str, str]] = set()
    for signal in signals:
        key = (signal.event_id, signal.signal, signal.use_event_id)
        if key not in seen:
            seen.add(key)
            result.append(signal)
    return result


def _outcome_suggestion(review: ProceduralSkillOutcomeReview) -> list[str]:
    if review.status == "SUCCESS_CANDIDATE":
        return [
            "- Inspect the exact success event and keep the procedure unchanged unless later evidence disagrees."
        ]
    if review.status == "FAILURE_CANDIDATE":
        return [
            "- Inspect the exact failure/correction lineage before manually revising or archiving the skill."
        ]
    if review.status == "MIXED_EVIDENCE":
        return ["- Inspect every listed signal; mixed evidence must not update the skill automatically."]
    if review.status == "NEEDS_MORE_EVIDENCE":
        return [
            "- A future separately approved capture step may record an exact manual-use outcome; do not infer one from uses."
        ]
    return ["- Resolve the reported provenance/trace issue before outcome review."]


def _outcome_error(message: str) -> str:
    return "\n".join(
        [
            "Proto-Mind Procedural Skill Outcome Error",
            "Status: ERROR",
            f"- {message}",
            *_outcome_boundary(),
        ]
    )


def _outcome_boundary() -> list[str]:
    return [
        "Boundary:",
        "- Read-only current-process evidence review; no skill was selected, invoked, scored, updated, or persisted.",
        "- No Experience event, lesson, memory, Skill Library, queue, export, session log, or Context Injection changed.",
        "- No shell, arbitrary dispatch, model/API call, automatic conclusion, procedure execution, or background action occurred.",
    ]


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))
