from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from threading import RLock
from typing import Any
from uuid import uuid4

from proto_mind.experience_capture import LIVE_CAPTURE_HOOK_INSTALLED
from proto_mind.experience_capture_soak import BoundedExperiencePreviewBuffer
from proto_mind.experience_consent import CONSENT_STATES, SessionConsentStateMachineSpec
from proto_mind.experience_explainability import (
    ExperienceTraceIndex,
    format_experience_event_explanation,
)
from proto_mind.experience_ledger import (
    LIVE_EXPERIENCE_PERSISTENCE_ENABLED,
    ExperienceTraceBuilder,
    compact_preview,
)
from proto_mind.experience_learning_bridge import (
    OperatorReviewedLearningBridge,
    format_learning_bridge_command,
)
from proto_mind.experience_learning_decision import (
    OperatorReviewedLearningDecisionSession,
    format_learning_decision_command,
)
from proto_mind.experience_learning_eligibility import format_learning_eligibility_command
from proto_mind.experience_learning_proposal import (
    OperatorReviewedLearningProposalSession,
    format_learning_proposal_command,
)
from proto_mind.experience_learning_apply import (
    OperatorReviewedLearningMemoryApplySession,
    format_learning_memory_apply_command,
)
from proto_mind.experience_learning_outcome import format_learning_outcome_command
from proto_mind.experience_learning_lifecycle import (
    OperatorReviewedLearningLifecycleSession,
    format_learning_lifecycle_command,
)
from proto_mind.experience_learning_lifecycle_readiness import (
    format_learning_lifecycle_readiness_command,
)
from proto_mind.experience_learning_lifecycle_apply import (
    OperatorReviewedLearningLifecycleApplySession,
    format_learning_lifecycle_apply_command,
)
from proto_mind.experience_learning_lifecycle_audit import (
    format_learning_lifecycle_audit_command,
)
from proto_mind.experience_learning_skill_contract import (
    format_procedural_skill_contract_command,
)
from proto_mind.experience_learning_readiness import format_learning_apply_readiness_command
from proto_mind.experience_turn import (
    format_cognitive_turn_episode,
    format_cognitive_turn_list,
)
from proto_mind.models import InteractionResult, utc_now_iso
from proto_mind.memory_store import MemoryStore
from proto_mind.skill_library import SkillLibrary


EXPERIENCE_PILOT_VERSION = 1
EXPERIENCE_PILOT_MODE = "supervised_process_memory_only"
EXPERIENCE_PILOT_ATTR = "_proto_mind_experience_pilot_v1"
EXPERIENCE_PILOT_MAX_EVENTS_PER_TURN = 12
EXPERIENCE_PILOT_MAX_EVENTS = 256
EXPERIENCE_PILOT_MAX_BYTES = 512 * 1024


@dataclass(frozen=True)
class ExperiencePilotObservation:
    state: str
    reason: str
    capture_performed: bool
    captured_turn: int | None
    captured_event_count: int
    total_event_count: int
    total_bytes: int
    event_ids: list[str]
    persistence_performed: bool = False


@dataclass(frozen=True)
class ExperiencePilotDoctorReport:
    status: str
    state: str
    captured_turns: int
    event_count: int
    byte_count: int
    issues: list[str]
    warnings: list[str]
    process_memory_only: bool = True
    live_writer_installed: bool = LIVE_CAPTURE_HOOK_INSTALLED
    live_persistence_enabled: bool = LIVE_EXPERIENCE_PERSISTENCE_ENABLED


class SupervisedExperiencePilot:
    """Explicit-session normal-turn capture into bounded process memory only."""

    def __init__(
        self,
        project_root: Path,
        *,
        session_id: str | None = None,
        max_events_per_turn: int = EXPERIENCE_PILOT_MAX_EVENTS_PER_TURN,
        max_events: int = EXPERIENCE_PILOT_MAX_EVENTS,
        max_bytes: int = EXPERIENCE_PILOT_MAX_BYTES,
    ) -> None:
        self.project_root = Path(project_root)
        self.session_id = session_id or f"pilot-{uuid4().hex[:10]}"
        self._consent = SessionConsentStateMachineSpec(self.session_id)
        self._state = "disabled"
        self._captured_turns = 0
        self._buffer = BoundedExperiencePreviewBuffer(
            max_events_per_turn=max_events_per_turn,
            max_events=max_events,
            max_bytes=max_bytes,
        )
        self._builder = ExperienceTraceBuilder(
            session_id=self.session_id,
            source="supervised_in_memory_pilot",
        )
        self._learning_decisions = OperatorReviewedLearningDecisionSession()
        self._learning_proposals = OperatorReviewedLearningProposalSession()
        self._learning_applies = OperatorReviewedLearningMemoryApplySession()
        self._learning_lifecycle = OperatorReviewedLearningLifecycleSession()
        self._learning_lifecycle_applies = OperatorReviewedLearningLifecycleApplySession()
        self._lock = RLock()

    @property
    def state(self) -> str:
        return self._state

    @property
    def captured_turns(self) -> int:
        return self._captured_turns

    @property
    def event_count(self) -> int:
        return self._buffer.event_count

    @property
    def byte_count(self) -> int:
        return self._buffer.byte_count

    @property
    def max_events(self) -> int:
        return self._buffer.max_events

    @property
    def max_bytes(self) -> int:
        return self._buffer.max_bytes

    @property
    def expected_consent_phrase(self) -> str:
        return self._consent.expected_phrase()

    @property
    def learning_decisions(self) -> OperatorReviewedLearningDecisionSession:
        return self._learning_decisions

    @property
    def learning_proposals(self) -> OperatorReviewedLearningProposalSession:
        return self._learning_proposals

    @property
    def learning_applies(self) -> OperatorReviewedLearningMemoryApplySession:
        return self._learning_applies

    @property
    def learning_lifecycle(self) -> OperatorReviewedLearningLifecycleSession:
        return self._learning_lifecycle

    @property
    def learning_lifecycle_applies(self) -> OperatorReviewedLearningLifecycleApplySession:
        return self._learning_lifecycle_applies

    def preview(self) -> str:
        with self._lock:
            transition = self._consent.evaluate(self._state, "preview_shown")
            self._state = transition.next_state
            lines = [
                "Proto-Mind Supervised Experience Pilot Preview v1",
                f"Status: {'READY_FOR_CONSENT' if transition.accepted else 'REFUSED'}",
                f"session_id: {self.session_id}",
                f"state: {self._state}",
                f"mode: {EXPERIENCE_PILOT_MODE}",
                "scope: successful normal cognitive turns only",
                "excluded: slash commands, natural routes, internal reports, history/backfill",
                "privacy: deterministic credential redaction; compact typed previews only",
                (
                    "bounds: "
                    f"events_per_turn<={self._buffer.max_events_per_turn}; "
                    f"events<={self._buffer.max_events}; bytes<={self._buffer.max_bytes}"
                ),
                "persistence: none; process restart discards all pilot events",
                "Context Injection: must remain disabled; active injection stops the pilot fail-closed",
                "Exact consent command:",
                f"/experience consent {self.expected_consent_phrase}",
                "- Preview changes only in-memory consent state; no turn was captured.",
            ]
            if not transition.accepted:
                lines.append(f"- reason: {transition.reason}")
            return "\n".join(lines)

    def consent(self, provided_phrase: str) -> str:
        with self._lock:
            transition = self._consent.evaluate(
                self._state,
                "consent_submitted",
                provided_phrase=provided_phrase,
            )
            self._state = transition.next_state
            return "\n".join(
                [
                    "Proto-Mind Supervised Experience Pilot Consent v1",
                    f"Status: {'CONSENTED' if transition.accepted else 'REFUSED'}",
                    f"state: {self._state}",
                    f"reason: {transition.reason}",
                    f"scope_allowed: {str(transition.accepted and self._state == 'consented').lower()}",
                    "capture_performed: false",
                    "persistence_performed: false",
                    "- The supplied phrase was compared but is not retained by the pilot.",
                ]
            )

    def stop(self, *, reason: str = "operator_requested") -> str:
        with self._lock:
            transition = self._consent.evaluate(self._state, "stop_requested")
            self._state = transition.next_state
            return "\n".join(
                [
                    "Proto-Mind Supervised Experience Pilot Stop v1",
                    "Status: STOPPED",
                    f"state: {self._state}",
                    f"reason: {reason}",
                    f"captured_turns: {self._captured_turns}",
                    f"events_retained_in_process_memory: {self.event_count}",
                    "persistence_performed: false",
                    "- Existing process-memory previews remain inspectable until process exit.",
                ]
            )

    def observe_normal_turn(
        self,
        user_input: str,
        result: InteractionResult,
        *,
        context_injection_applied: bool = False,
    ) -> ExperiencePilotObservation:
        with self._lock:
            if self._state != "consented":
                return self._observation("consent_not_active", capture_performed=False)
            if not user_input.strip():
                return self._observation("empty_input_bypassed", capture_performed=False)
            if user_input.lstrip().startswith("/"):
                return self._observation("slash_command_bypassed", capture_performed=False)
            if context_injection_applied:
                self._fail_closed("context_injection_active")
                return self._observation(
                    "context_injection_active_fail_closed",
                    capture_performed=False,
                )

            scope = self._consent.evaluate(self._state, "normal_prompt_observed")
            if not scope.scope_allowed:
                return self._observation(scope.reason, capture_performed=False)

            next_turn = self._captured_turns + 1
            try:
                events = self._builder.build_turn_events(
                    user_input,
                    result,
                    turn_id=next_turn,
                    trace_id=f"pilot-{next_turn:04d}",
                    created_at=utc_now_iso(),
                )
                decision = self._buffer.consider_batch(events)
            except Exception:
                self._fail_closed("event_build_failed")
                return self._observation("event_build_failed_fail_closed", capture_performed=False)

            if not decision.accepted:
                self._fail_closed(decision.reason)
                return self._observation(
                    f"{decision.reason}_fail_closed",
                    capture_performed=False,
                )

            self._captured_turns = next_turn
            return ExperiencePilotObservation(
                state=self._state,
                reason="captured_to_bounded_process_memory",
                capture_performed=True,
                captured_turn=next_turn,
                captured_event_count=len(events),
                total_event_count=self.event_count,
                total_bytes=self.byte_count,
                event_ids=[event.id for event in events],
            )

    def snapshot(self) -> tuple[dict[str, Any], ...]:
        with self._lock:
            return self._buffer.snapshot()

    def doctor(self) -> ExperiencePilotDoctorReport:
        with self._lock:
            issues: list[str] = []
            warnings: list[str] = []
            if self._state not in CONSENT_STATES:
                issues.append("Pilot consent state is invalid.")
            if LIVE_CAPTURE_HOOK_INSTALLED or LIVE_EXPERIENCE_PERSISTENCE_ENABLED:
                issues.append("A live writer or persistence policy is active during the in-memory pilot.")
            buffer_report = self._buffer.doctor()
            if buffer_report.status == "ERROR":
                issues.extend(buffer_report.issues)
            if self._state == "consented" and not self._captured_turns:
                warnings.append("Pilot is consented but has not captured a normal turn yet.")
            if self._state in {"stopped", "expired"}:
                warnings.append("Pilot is terminal for this process session; restart is required for new consent.")
            status = "ERROR" if issues else "WARN" if warnings else "OK"
            return ExperiencePilotDoctorReport(
                status=status,
                state=self._state,
                captured_turns=self._captured_turns,
                event_count=self.event_count,
                byte_count=self.byte_count,
                issues=issues,
                warnings=warnings,
            )

    def _fail_closed(self, reason: str) -> None:
        transition = self._consent.evaluate(self._state, "capture_failure_observed")
        self._state = transition.next_state

    def _observation(
        self,
        reason: str,
        *,
        capture_performed: bool,
    ) -> ExperiencePilotObservation:
        return ExperiencePilotObservation(
            state=self._state,
            reason=reason,
            capture_performed=capture_performed,
            captured_turn=None,
            captured_event_count=0,
            total_event_count=self.event_count,
            total_bytes=self.byte_count,
            event_ids=[],
        )


_OWNER_LOCK = RLock()


def get_experience_pilot(owner: object, *, project_root: Path) -> SupervisedExperiencePilot:
    with _OWNER_LOCK:
        pilot = getattr(owner, EXPERIENCE_PILOT_ATTR, None)
        if isinstance(pilot, SupervisedExperiencePilot):
            return pilot
        pilot = SupervisedExperiencePilot(project_root)
        setattr(owner, EXPERIENCE_PILOT_ATTR, pilot)
        return pilot


def peek_experience_pilot(owner: object) -> SupervisedExperiencePilot | None:
    pilot = getattr(owner, EXPERIENCE_PILOT_ATTR, None)
    return pilot if isinstance(pilot, SupervisedExperiencePilot) else None


def observe_experience_pilot_if_active(
    owner: object,
    user_input: str,
    result: InteractionResult,
    *,
    context_injection_applied: bool,
) -> ExperiencePilotObservation | None:
    pilot = peek_experience_pilot(owner)
    if pilot is None or pilot.state != "consented":
        return None
    if not user_input.strip() or user_input.lstrip().startswith("/"):
        return None
    return pilot.observe_normal_turn(
        user_input,
        result,
        context_injection_applied=context_injection_applied,
    )


def format_experience_pilot_command(
    command: str,
    *,
    owner: object,
    project_root: Path,
) -> str | None:
    raw = command.strip()
    normalized = " ".join(raw.lower().split())
    if not normalized.startswith("/experience"):
        return None
    pilot = get_experience_pilot(owner, project_root=project_root)

    if normalized == "/experience status":
        return _format_status(pilot)
    if normalized == "/experience preview":
        return pilot.preview()
    consent_prefix = "/experience consent "
    if raw.lower().startswith(consent_prefix):
        return pilot.consent(raw[len(consent_prefix) :].strip())
    if normalized == "/experience consent":
        return "Usage: /experience consent <exact phrase from /experience preview>"
    if normalized == "/experience stop":
        return pilot.stop()
    if normalized == "/experience episodes":
        return format_cognitive_turn_list(pilot.snapshot())
    if normalized == "/experience episode":
        return format_cognitive_turn_episode(pilot.snapshot())
    if normalized.startswith("/experience episode "):
        parts = raw.split(maxsplit=2)
        return format_cognitive_turn_episode(pilot.snapshot(), parts[2].strip())
    if normalized == "/experience learning" or normalized.startswith(
        "/experience learning "
    ):
        events = pilot.snapshot()
        lifecycle_output = format_learning_lifecycle_command(
            raw,
            events=events,
            memory_store=_owner_memory_store(owner),
            session=pilot.learning_lifecycle,
        )
        if lifecycle_output is not None:
            return lifecycle_output
        lifecycle_readiness_output = format_learning_lifecycle_readiness_command(
            raw,
            events=events,
            memory_store=_owner_memory_store(owner),
            session=pilot.learning_lifecycle,
        )
        if lifecycle_readiness_output is not None:
            return lifecycle_readiness_output
        lifecycle_audit_output = format_learning_lifecycle_audit_command(
            raw,
            memory_store=_owner_memory_store(owner),
        )
        if lifecycle_audit_output is not None:
            return lifecycle_audit_output
        skill_contract_output = format_procedural_skill_contract_command(
            raw,
            memory_store=_owner_memory_store(owner),
            project_root=project_root,
        )
        if skill_contract_output is not None:
            return skill_contract_output
        lifecycle_apply_output = format_learning_lifecycle_apply_command(
            raw,
            events=events,
            memory_store=_owner_memory_store(owner),
            lifecycle_session=pilot.learning_lifecycle,
            apply_session=pilot.learning_lifecycle_applies,
        )
        if lifecycle_apply_output is not None:
            return lifecycle_apply_output
        outcome_output = format_learning_outcome_command(
            raw,
            events=events,
            memory_store=_owner_memory_store(owner),
        )
        if outcome_output is not None:
            return outcome_output
        decision_output = format_learning_decision_command(
            raw,
            OperatorReviewedLearningBridge(events),
            pilot.learning_decisions,
        )
        if decision_output is not None:
            return decision_output
        eligibility_output = format_learning_eligibility_command(
            raw,
            bridge=OperatorReviewedLearningBridge(events),
            decisions=pilot.learning_decisions,
            memory_store=_owner_memory_store(owner),
            skill_library=SkillLibrary.from_project_root(project_root),
        )
        if eligibility_output is not None:
            return eligibility_output
        proposal_output = format_learning_proposal_command(
            raw,
            bridge=OperatorReviewedLearningBridge(events),
            decisions=pilot.learning_decisions,
            proposals=pilot.learning_proposals,
            memory_store=_owner_memory_store(owner),
            skill_library=SkillLibrary.from_project_root(project_root),
        )
        if proposal_output is not None:
            return proposal_output
        apply_output = format_learning_memory_apply_command(
            raw,
            bridge=OperatorReviewedLearningBridge(events),
            decisions=pilot.learning_decisions,
            proposals=pilot.learning_proposals,
            applies=pilot.learning_applies,
            memory_store=_owner_memory_store(owner),
            skill_library=SkillLibrary.from_project_root(project_root),
        )
        if apply_output is not None:
            return apply_output
        readiness_output = format_learning_apply_readiness_command(
            raw,
            bridge=OperatorReviewedLearningBridge(events),
            decisions=pilot.learning_decisions,
            proposals=pilot.learning_proposals,
            memory_store=_owner_memory_store(owner),
            skill_library=SkillLibrary.from_project_root(project_root),
        )
        if readiness_output is not None:
            return readiness_output
        learning_output = format_learning_bridge_command(
            raw,
            events,
            pilot_state=pilot.state,
        )
        if learning_output is not None:
            return learning_output
    if normalized.startswith("/experience events"):
        return _format_events_command(raw, pilot)
    if normalized.startswith("/experience inspect"):
        parts = raw.split(maxsplit=2)
        if len(parts) < 3 or not parts[2].strip():
            return "Usage: /experience inspect <event_id>"
        return format_experience_event_explanation(
            ExperienceTraceIndex(pilot.snapshot()),
            parts[2].strip(),
        )
    if normalized == "/experience doctor":
        return _format_doctor(pilot)
    return _usage()


def _format_status(pilot: SupervisedExperiencePilot) -> str:
    return "\n".join(
        [
            "Proto-Mind Supervised Experience Pilot v1",
            "Status: ACTIVE" if pilot.state == "consented" else "Status: INACTIVE",
            f"state: {pilot.state}",
            f"session_id: {pilot.session_id}",
            f"mode: {EXPERIENCE_PILOT_MODE}",
            f"captured_turns: {pilot.captured_turns}",
            f"events: {pilot.event_count}/{pilot.max_events}",
            f"bytes: {pilot.byte_count}/{pilot.max_bytes}",
            "persistence: disabled",
            "live_writer: absent",
            "Commands: /experience preview | consent | episodes | episode | learning | events | inspect | doctor | stop",
        ]
    )


def _format_events_command(command: str, pilot: SupervisedExperiencePilot) -> str:
    parts = command.split()
    limit = 20
    if len(parts) == 4 and parts[2] == "--last":
        try:
            limit = int(parts[3])
        except ValueError:
            return "Usage: /experience events [--last N]"
        if not 1 <= limit <= 100:
            return "Experience events error: --last must be from 1 to 100."
    elif len(parts) != 2:
        return "Usage: /experience events [--last N]"

    events = pilot.snapshot()
    selected = events[-limit:]
    lines = [
        "Proto-Mind Supervised Experience Events v1",
        f"Status: {'OK' if events else 'EMPTY'}",
        f"session_id: {pilot.session_id}",
        f"showing: {len(selected)}/{len(events)}",
        "Events:",
    ]
    if not selected:
        lines.append("- none; enable the pilot explicitly and complete a normal turn first.")
    for event in selected:
        preview = _event_preview(event.get("payload"))
        suffix = f" | {preview}" if preview else ""
        lines.append(
            f"- {event.get('id')} | {event.get('event_type')} | turn={event.get('turn_id')}{suffix}"
        )
    lines.append("- Process-memory inspection only; no file or store was read or written.")
    return "\n".join(lines)


def _event_preview(payload: object) -> str:
    if not isinstance(payload, dict):
        return ""
    for key in sorted(payload):
        if key.endswith("_preview") and isinstance(payload[key], str) and payload[key]:
            return f"{key}={compact_preview(payload[key], 80)}"
    return ""


def _format_doctor(pilot: SupervisedExperiencePilot) -> str:
    report = pilot.doctor()
    lines = [
        "Proto-Mind Supervised Experience Pilot Doctor v1",
        f"Status: {report.status}",
        f"state: {report.state}",
        f"captured_turns: {report.captured_turns}",
        f"events: {report.event_count}",
        f"bytes: {report.byte_count}",
        f"process_memory_only: {str(report.process_memory_only).lower()}",
        f"live_writer_installed: {str(report.live_writer_installed).lower()}",
        f"live_persistence_enabled: {str(report.live_persistence_enabled).lower()}",
    ]
    lines.extend(f"- ERROR: {issue}" for issue in report.issues)
    lines.extend(f"- WARN: {warning}" for warning in report.warnings)
    if not report.issues and not report.warnings:
        lines.append("- Consent state, bounded evidence, provenance, and no-persistence boundary are healthy.")
    lines.append("- No repair, export, memory promotion, skill creation, or external action performed.")
    return "\n".join(lines)


def format_experience_pilot_observation(observation: ExperiencePilotObservation) -> str:
    if observation.capture_performed:
        return (
            "Experience pilot: captured turn "
            f"{observation.captured_turn} ({observation.captured_event_count} events; "
            f"total={observation.total_event_count}, {observation.total_bytes} bytes; process-memory only)"
        )
    if observation.state == "stopped":
        return f"Experience pilot: stopped fail-closed ({observation.reason}); no event captured."
    return f"Experience pilot: bypassed ({observation.reason}); no event captured."


def _usage() -> str:
    return "\n".join(
        [
            "Experience Pilot commands:",
            "/experience status",
            "/experience preview",
            "/experience consent <exact phrase>",
            "/experience episodes",
            "/experience episode [latest|<turn_id>]",
            "/experience learning status|preview [latest|<turn_id>]|doctor",
            "/experience learning decisions|decision <candidate_id>|decision-doctor",
            "/experience learning confirm-preview|promotion-preview <candidate_id>",
            "/experience learning decide accept <candidate_id> <token>",
            "/experience learning decide reject <candidate_id> [reason]",
            "/experience learning eligibility|eligibility-doctor <candidate_id> --target memory|skill [--memory <id>]... [--skill <id>]...",
            "/experience learning proposal-preview <candidate_id> --target memory|skill [--memory <id>]... [--skill <id>]...",
            "/experience learning propose <candidate_id> <exact token> --target memory|skill [--memory <id>]... [--skill <id>]...",
            "/experience learning proposals|proposal <proposal_id|candidate_id>|proposal-doctor",
            "/experience learning apply-readiness|apply-plan <proposal_id|candidate_id>|apply-doctor",
            "/experience learning apply-preview <proposal_id|candidate_id>",
            "/experience learning apply <proposal_id|candidate_id> <exact token>",
            "/experience learning apply-status|apply-receipt <id>|apply-doctor",
            "/experience learning outcome-review <memory_id>|outcome-doctor",
            "/experience learning outcome-confirm-preview <memory_id>",
            "/experience learning decide outcome <keep|reject|supersede> <memory_id> <exact token>",
            "/experience learning outcome-decisions|outcome-decision <id>|outcome-decision-doctor",
            "/experience learning lifecycle-readiness|lifecycle-plan <memory_id|receipt_id>",
            "/experience learning lifecycle-readiness-doctor",
            "/experience learning lifecycle-apply-preview <memory_id|receipt_id>",
            "/experience learning apply lifecycle <memory_id|receipt_id> <exact token>",
            "/experience learning lifecycle-apply-status|lifecycle-apply-receipt <id>|lifecycle-apply-doctor",
            "/experience learning lifecycle-audit-status|lifecycle-history [--all]",
            "/experience learning lifecycle-inspect <memory_id>|lifecycle-audit-doctor",
            "/experience learning skill-contract-status|skill-contract-doctor",
            "/experience learning skill-contract-preview|template|checklist <memory_id>",
            "/experience events [--last N]",
            "/experience inspect <event_id>",
            "/experience doctor",
            "/experience stop",
        ]
    )


def _owner_memory_store(owner: object) -> MemoryStore | None:
    memory_keeper = getattr(owner, "memory_keeper", None)
    memory_store = getattr(memory_keeper, "store", None)
    return memory_store if isinstance(memory_store, MemoryStore) else None
