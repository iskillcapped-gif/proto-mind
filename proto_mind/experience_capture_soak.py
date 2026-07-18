from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Iterable

from proto_mind.experience_capture import LIVE_CAPTURE_HOOK_INSTALLED
from proto_mind.experience_consent import SessionConsentStateMachineSpec
from proto_mind.experience_ledger import (
    LIVE_EXPERIENCE_PERSISTENCE_ENABLED,
    ExperienceEvent,
    ExperienceTraceBuilder,
    inspect_experience_events,
)
from proto_mind.models import (
    GroundingAuditResult,
    InteractionResult,
    InteractionSummary,
    ObserverState,
    SelfReflectionResult,
)


EXPERIENCE_CAPTURE_SOAK_VERSION = 1
SOAK_SESSION_ID = "bounded-growth-soak"
SOAK_NORMAL_TURNS = 36
SOAK_MAX_EVENTS_PER_TURN = 8
SOAK_MAX_EVENTS = 256
SOAK_MAX_BYTES = 512 * 1024


@dataclass(frozen=True)
class PreviewBufferDecision:
    accepted: bool
    reason: str
    batch_event_count: int
    batch_bytes: int
    event_count_before: int
    event_count_after: int
    byte_count_before: int
    byte_count_after: int
    capture_performed: bool = False
    persistence_performed: bool = False


@dataclass(frozen=True)
class PreviewBufferDoctorReport:
    status: str
    event_count: int
    byte_count: int
    max_events: int
    max_bytes: int
    max_events_per_turn: int
    issues: list[str]
    warnings: list[str]
    capture_performed: bool = False
    persistence_performed: bool = False


@dataclass(frozen=True)
class ExperienceCaptureSoakReport:
    status: str
    normal_turns: int
    accepted_normal_turns: int
    bypass_events: int
    event_count: int
    byte_count: int
    max_events: int
    max_bytes: int
    max_events_per_turn: int
    redaction_markers: int
    files_created: int
    checks: dict[str, bool]
    failed_checks: list[str]
    boundary: str


class BoundedExperiencePreviewBuffer:
    """Process-memory-only bounded evidence buffer with no persistence operation."""

    def __init__(
        self,
        *,
        max_events: int = SOAK_MAX_EVENTS,
        max_bytes: int = SOAK_MAX_BYTES,
        max_events_per_turn: int = SOAK_MAX_EVENTS_PER_TURN,
    ) -> None:
        if max_events < 1 or max_bytes < 1 or max_events_per_turn < 1:
            raise ValueError("all preview buffer limits must be positive")
        self.max_events = int(max_events)
        self.max_bytes = int(max_bytes)
        self.max_events_per_turn = int(max_events_per_turn)
        self._events: list[dict[str, Any]] = []
        self._byte_count = 0

    @property
    def event_count(self) -> int:
        return len(self._events)

    @property
    def byte_count(self) -> int:
        return self._byte_count

    def consider_batch(
        self,
        events: Iterable[ExperienceEvent | dict[str, Any]],
    ) -> PreviewBufferDecision:
        normalized = [
            event.to_dict() if isinstance(event, ExperienceEvent) else dict(event)
            for event in events
        ]
        before_events = self.event_count
        before_bytes = self.byte_count
        batch_bytes = sum(len(_canonical_event_bytes(event)) for event in normalized)

        if not normalized:
            return self._decision(
                False,
                "empty_batch_refused",
                normalized,
                batch_bytes,
                before_events,
                before_bytes,
            )
        if len(normalized) > self.max_events_per_turn:
            return self._decision(
                False,
                "per_turn_event_limit",
                normalized,
                batch_bytes,
                before_events,
                before_bytes,
            )
        if before_events + len(normalized) > self.max_events:
            return self._decision(
                False,
                "total_event_limit",
                normalized,
                batch_bytes,
                before_events,
                before_bytes,
            )
        if before_bytes + batch_bytes > self.max_bytes:
            return self._decision(
                False,
                "total_byte_limit",
                normalized,
                batch_bytes,
                before_events,
                before_bytes,
            )

        doctor = inspect_experience_events(normalized)
        if doctor.status != "OK":
            return self._decision(
                False,
                "invalid_event_batch",
                normalized,
                batch_bytes,
                before_events,
                before_bytes,
            )

        detached = [json.loads(_canonical_event_bytes(event)) for event in normalized]
        self._events.extend(detached)
        self._byte_count += batch_bytes
        return self._decision(
            True,
            "accepted_in_memory_preview",
            normalized,
            batch_bytes,
            before_events,
            before_bytes,
        )

    def snapshot(self) -> tuple[dict[str, Any], ...]:
        return tuple(json.loads(_canonical_event_bytes(event)) for event in self._events)

    def doctor(self) -> PreviewBufferDoctorReport:
        issues: list[str] = []
        warnings: list[str] = []
        if self.event_count > self.max_events:
            issues.append("Preview event count exceeds its configured bound.")
        if self.byte_count > self.max_bytes:
            issues.append("Preview byte count exceeds its configured bound.")
        canonical_size = sum(len(_canonical_event_bytes(event)) for event in self._events)
        if canonical_size != self.byte_count:
            issues.append("Preview byte accounting does not match the detached snapshot.")
        if self._events:
            event_report = inspect_experience_events(self._events)
            issues.extend(event_report.issues)
            warnings.extend(event_report.warnings)
        else:
            warnings.append("Preview buffer is empty.")
        status = "ERROR" if issues else "WARN" if warnings else "OK"
        return PreviewBufferDoctorReport(
            status=status,
            event_count=self.event_count,
            byte_count=self.byte_count,
            max_events=self.max_events,
            max_bytes=self.max_bytes,
            max_events_per_turn=self.max_events_per_turn,
            issues=issues,
            warnings=warnings,
        )

    def _decision(
        self,
        accepted: bool,
        reason: str,
        events: list[dict[str, Any]],
        batch_bytes: int,
        before_events: int,
        before_bytes: int,
    ) -> PreviewBufferDecision:
        return PreviewBufferDecision(
            accepted=accepted,
            reason=reason,
            batch_event_count=len(events),
            batch_bytes=batch_bytes,
            event_count_before=before_events,
            event_count_after=self.event_count,
            byte_count_before=before_bytes,
            byte_count_after=self.byte_count,
        )


def _canonical_event_bytes(event: dict[str, Any]) -> bytes:
    return (
        json.dumps(
            event,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def _synthetic_result(user_input: str, turn_number: int) -> InteractionResult:
    secret = f"soak-secret-{turn_number:04d}"
    sensitive_turn = turn_number % 6 == 0
    topic_tags = ["experience", "preview", f"turn-{turn_number:02d}"]
    warnings: list[str] = []
    evidence = ["Synthetic local evidence; no tool or store was used."]
    if sensitive_turn:
        topic_tags.extend(["password", secret])
        warnings.append(f"Credential fixture token={secret}")
        evidence.append(f"Authorization: Bearer {secret}BearerValue")

    return InteractionResult(
        response=f"Synthetic preview response for turn {turn_number}: {user_input}",
        observer_state=ObserverState(
            query_type="new_question",
            needs_memory=False,
            importance_hint=0.2,
            topic_tags=topic_tags,
        ),
        retrieved_memory=[],
        retrieval_trace=None,
        memory_summary=InteractionSummary(
            memory_type="insight",
            content=user_input,
            importance=0.2,
            tags=["experience", "soak"],
            should_store=False,
            storage_rationale="Synthetic no-store soak result.",
        ),
        working_memory_snapshot=[],
        persistent_memory_snapshot=[],
        reasoner_backend="synthetic-no-llm",
        self_reflection=SelfReflectionResult(
            reflection_needed=bool(warnings),
            memory_alignment="neutral",
            preference_alignment="neutral",
            active_decision_alignment="neutral",
            superseded_memory_risk="none",
            unsupported_claims_risk="low",
            overall_confidence="high",
            warnings=warnings,
        ),
        grounding_audit=GroundingAuditResult(
            grounding_needed=False,
            grounding_status="not_needed",
            memory_support="none_needed",
            active_decision_status="not_applicable",
            superseded_memory_status="not_applicable",
            evidence=evidence,
        ),
    )


def _normal_input(turn_number: int) -> tuple[str, list[str]]:
    if turn_number % 6 == 0:
        secret = f"soak-secret-{turn_number:04d}"
        if turn_number % 12 == 0:
            return (
                f"Проверь безопасный preview {turn_number}. пароль={secret}",
                [secret, f"{secret}BearerValue"],
            )
        return (
            f"Review safe preview turn {turn_number}. password={secret}",
            [secret, f"{secret}BearerValue"],
        )
    if turn_number % 2 == 0:
        return f"Проверь локальный preview turn {turn_number} без записи.", []
    return f"Review local preview turn {turn_number} without persistence.", []


def run_experience_capture_soak() -> ExperienceCaptureSoakReport:
    with TemporaryDirectory(prefix="proto-mind-experience-capture-soak-") as temp_dir:
        root = Path(temp_dir)
        before = list(root.rglob("*"))
        consent = SessionConsentStateMachineSpec(SOAK_SESSION_ID)
        state = "disabled"
        transitions = []

        pre_consent = consent.evaluate(state, "normal_prompt_observed")
        transitions.append(pre_consent)
        previewed = consent.evaluate(state, "preview_shown")
        transitions.append(previewed)
        state = previewed.next_state
        wrong = consent.evaluate(state, "consent_submitted", provided_phrase="yes for this session")
        transitions.append(wrong)
        exact = consent.evaluate(
            state,
            "consent_submitted",
            provided_phrase=consent.expected_phrase(),
        )
        transitions.append(exact)
        state = exact.next_state

        buffer = BoundedExperiencePreviewBuffer()
        builder = ExperienceTraceBuilder(session_id=SOAK_SESSION_ID)
        decisions: list[PreviewBufferDecision] = []
        secret_fragments: list[str] = []
        accepted_normal_turns = 0
        max_batch_events = 0

        for turn_number in range(1, SOAK_NORMAL_TURNS + 1):
            user_input, secrets = _normal_input(turn_number)
            secret_fragments.extend(secrets)
            scope = consent.evaluate(state, "normal_prompt_observed")
            transitions.append(scope)
            if not scope.scope_allowed:
                continue
            events = builder.build_turn_events(
                user_input,
                _synthetic_result(user_input, turn_number),
                turn_id=turn_number,
                trace_id=f"bounded-{turn_number:02d}",
                created_at=f"2026-01-01T00:00:{turn_number:02d}Z",
            )
            max_batch_events = max(max_batch_events, len(events))
            decision = buffer.consider_batch(events)
            decisions.append(decision)
            if decision.accepted:
                accepted_normal_turns += 1

        bypass_events = (
            "slash_command_observed",
            "natural_routed_command_observed",
            "internal_report_observed",
            "historical_turn_observed",
        )
        bypass_results = [consent.evaluate(state, event) for event in bypass_events]
        transitions.extend(bypass_results)
        stopped = consent.evaluate(state, "stop_requested")
        after_stop = consent.evaluate(stopped.next_state, "normal_prompt_observed")
        transitions.extend([stopped, after_stop])

        failure_spec = SessionConsentStateMachineSpec("bounded-failure")
        failure_preview = failure_spec.evaluate("disabled", "preview_shown")
        failure_consent = failure_spec.evaluate(
            failure_preview.next_state,
            "consent_submitted",
            provided_phrase=failure_spec.expected_phrase(),
        )
        failed_closed = failure_spec.evaluate(
            failure_consent.next_state,
            "capture_failure_observed",
        )
        restart_spec = SessionConsentStateMachineSpec("bounded-restart")
        restart_preview = restart_spec.evaluate("disabled", "preview_shown")
        restart_consent = restart_spec.evaluate(
            restart_preview.next_state,
            "consent_submitted",
            provided_phrase=restart_spec.expected_phrase(),
        )
        expired = restart_spec.evaluate(restart_consent.next_state, "process_restarted")
        transitions.extend(
            [failure_preview, failure_consent, failed_closed, restart_preview, restart_consent, expired]
        )

        snapshot_before_overflow = buffer.snapshot()
        overflow_events = builder.build_turn_events(
            "Overflow count probe.",
            _synthetic_result("Overflow count probe.", 99),
            turn_id=99,
            trace_id="bounded-overflow-count",
            created_at="2026-01-01T00:01:39Z",
        )
        count_overflow = buffer.consider_batch(overflow_events)
        snapshot_after_overflow = buffer.snapshot()

        per_turn_buffer = BoundedExperiencePreviewBuffer(max_events_per_turn=6)
        per_turn_overflow = per_turn_buffer.consider_batch(overflow_events)
        byte_buffer = BoundedExperiencePreviewBuffer(max_bytes=64)
        byte_overflow = byte_buffer.consider_batch(overflow_events)

        buffer_doctor = buffer.doctor()
        snapshot_json = json.dumps(buffer.snapshot(), ensure_ascii=False, sort_keys=True)
        redaction_markers = snapshot_json.count("[REDACTED:")
        after = list(root.rglob("*"))

    from proto_mind.command_registry import COMMAND_REGISTRY

    checks = {
        "pre_consent_turn_refused": not pre_consent.scope_allowed,
        "wrong_consent_refused": not wrong.accepted and wrong.next_state == "previewed",
        "exact_session_consent_modeled": exact.accepted and exact.next_state == "consented",
        "all_normal_turns_in_scope": accepted_normal_turns == SOAK_NORMAL_TURNS,
        "all_batches_accepted": all(decision.accepted for decision in decisions),
        "per_turn_event_bound": max_batch_events <= SOAK_MAX_EVENTS_PER_TURN,
        "total_event_bound": buffer.event_count <= SOAK_MAX_EVENTS,
        "total_byte_bound": buffer.byte_count <= SOAK_MAX_BYTES,
        "buffer_doctor_ok": buffer_doctor.status == "OK",
        "credential_fixtures_redacted": bool(secret_fragments)
        and all(fragment not in snapshot_json for fragment in secret_fragments)
        and redaction_markers > 0,
        "bypass_events_refused": all(
            not result.accepted and not result.scope_allowed for result in bypass_results
        ),
        "stop_blocks_later_turn": stopped.next_state == "stopped" and not after_stop.scope_allowed,
        "failure_stops_session": failed_closed.next_state == "stopped",
        "restart_expires_consent": expired.next_state == "expired",
        "count_overflow_refused_without_mutation": not count_overflow.accepted
        and count_overflow.reason == "total_event_limit"
        and snapshot_before_overflow == snapshot_after_overflow,
        "per_turn_overflow_refused": not per_turn_overflow.accepted
        and per_turn_overflow.reason == "per_turn_event_limit"
        and per_turn_buffer.event_count == 0,
        "byte_overflow_refused": not byte_overflow.accepted
        and byte_overflow.reason == "total_byte_limit"
        and byte_buffer.event_count == 0,
        "transitions_never_capture_or_persist": all(
            not transition.capture_performed and not transition.persistence_performed
            for transition in transitions
        ),
        "buffer_never_captures_or_persists": all(
            not decision.capture_performed and not decision.persistence_performed
            for decision in decisions + [count_overflow, per_turn_overflow, byte_overflow]
        ),
        "live_capture_boundaries_disabled": not LIVE_CAPTURE_HOOK_INSTALLED
        and not LIVE_EXPERIENCE_PERSISTENCE_ENABLED,
        "no_persistent_experience_commands": not any(
            item.prefix.startswith(
                (
                    "/experience persist",
                    "/experience export",
                    "/experience apply",
                    "/experience promote",
                    "/experience backfill",
                )
            )
            for item in COMMAND_REGISTRY
        ),
        "no_files_created": before == after,
    }
    failed_checks = [name for name, passed in checks.items() if not passed]
    return ExperienceCaptureSoakReport(
        status="OK" if not failed_checks else "ERROR",
        normal_turns=SOAK_NORMAL_TURNS,
        accepted_normal_turns=accepted_normal_turns,
        bypass_events=len(bypass_events),
        event_count=buffer.event_count,
        byte_count=buffer.byte_count,
        max_events=SOAK_MAX_EVENTS,
        max_bytes=SOAK_MAX_BYTES,
        max_events_per_turn=SOAK_MAX_EVENTS_PER_TURN,
        redaction_markers=redaction_markers,
        files_created=len(after) - len(before),
        checks=checks,
        failed_checks=failed_checks,
        boundary=(
            "Synthetic process-memory preview simulation only; no LLM, runtime capture, consent "
            "storage, hook, writer, live or temporary persistence, persistent command, export, Context "
            "Injection change, domain mutation, or external action."
        ),
    )


def format_experience_capture_soak(report: ExperienceCaptureSoakReport | None = None) -> str:
    report = report or run_experience_capture_soak()
    lines = [
        "Proto-Mind Experience Capture Bounded-Growth Soak v1",
        f"Status: {report.status}",
        f"normal_turns: {report.accepted_normal_turns}/{report.normal_turns}",
        f"bypass_events: {report.bypass_events}",
        f"events: {report.event_count}/{report.max_events}",
        f"bytes: {report.byte_count}/{report.max_bytes}",
        f"max_events_per_turn: {report.max_events_per_turn}",
        f"redaction_markers: {report.redaction_markers}",
        f"files_created: {report.files_created}",
        "Checks:",
    ]
    lines.extend(f"- [{'PASS' if passed else 'FAIL'}] {name}" for name, passed in report.checks.items())
    lines.extend(["Boundary:", f"- {report.boundary}"])
    return "\n".join(lines)


def main() -> int:
    report = run_experience_capture_soak()
    print(format_experience_capture_soak(report))
    return 0 if report.status == "OK" else 1


if __name__ == "__main__":
    raise SystemExit(main())
