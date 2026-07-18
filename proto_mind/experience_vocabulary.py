from __future__ import annotations

from dataclasses import dataclass
import re
from tempfile import TemporaryDirectory
from pathlib import Path
from typing import Iterable

from proto_mind.experience_ledger import (
    ExperienceEvent,
    TemporaryExperienceLedgerStore,
    compact_preview,
    inspect_experience_events,
)


@dataclass(frozen=True)
class ExperienceVocabularyReport:
    status: str
    success_trace_events: int
    failure_trace_events: int
    total_events: int
    provenance_edges: int
    hash_verified: int
    checks: dict[str, bool]
    failed_checks: list[str]
    boundary: str


class ExperienceLifecycleBuilder:
    """Builds typed lifecycle evidence; it never runs tools or mutates domain stores."""

    def __init__(
        self,
        *,
        session_id: str,
        trace_id: str,
        turn_id: str | int,
        created_at: str,
    ) -> None:
        if not session_id.strip():
            raise ValueError("session_id must not be empty")
        self.session_id = session_id.strip()
        self.trace_id = self._normalize_identifier(trace_id, fallback="lifecycle")
        self.turn_id = str(turn_id)
        self.created_at = created_at
        self.events: list[ExperienceEvent] = []

    def goal_created(
        self,
        *,
        goal_id: str,
        title: str,
        priority: str = "normal",
        success_criteria: str = "",
    ) -> ExperienceEvent:
        return self._add(
            "goal_created",
            {
                "goal_id": self._identifier(goal_id),
                "title_preview": compact_preview(title),
                "priority": priority if priority in {"high", "normal", "low"} else "normal",
                "success_criteria_preview": compact_preview(success_criteria),
            },
        )

    def plan_created(
        self,
        goal: ExperienceEvent,
        *,
        plan_id: str,
        plan: str,
        step_count: int,
    ) -> ExperienceEvent:
        self._require_event_type(goal, "goal_created")
        return self._add(
            "plan_created",
            {
                "plan_id": self._identifier(plan_id),
                "goal_id": goal.payload["goal_id"],
                "step_count": max(1, min(int(step_count), 100)),
                "plan_preview": compact_preview(plan),
            },
            [goal],
        )

    def tool_called(
        self,
        plan: ExperienceEvent,
        *,
        call_id: str,
        capability: str,
        input_summary: str,
        risk: str = "low",
        read_only: bool = True,
    ) -> ExperienceEvent:
        self._require_event_type(plan, "plan_created")
        return self._add(
            "tool_called",
            {
                "call_id": self._identifier(call_id),
                "capability": self._normalize_identifier(capability, fallback="unknown")[:80],
                "input_preview": compact_preview(input_summary),
                "risk": risk if risk in {"low", "medium", "high"} else "high",
                "read_only": bool(read_only),
                "execution_performed_by_builder": False,
            },
            [plan],
        )

    def tool_succeeded(
        self,
        tool_call: ExperienceEvent,
        *,
        output_summary: str,
        verified: bool,
    ) -> ExperienceEvent:
        self._require_event_type(tool_call, "tool_called")
        return self._add(
            "tool_succeeded",
            {
                "call_id": tool_call.payload["call_id"],
                "output_preview": compact_preview(output_summary),
                "verified": bool(verified),
            },
            [tool_call],
        )

    def tool_failed(
        self,
        tool_call: ExperienceEvent,
        *,
        error_type: str,
        error_summary: str,
        retryable: bool,
    ) -> ExperienceEvent:
        self._require_event_type(tool_call, "tool_called")
        return self._add(
            "tool_failed",
            {
                "call_id": tool_call.payload["call_id"],
                "error_type": self._normalize_identifier(error_type, fallback="unknown")[:80],
                "error_preview": compact_preview(error_summary),
                "retryable": bool(retryable),
            },
            [tool_call],
        )

    def user_corrected(
        self,
        target: ExperienceEvent,
        *,
        correction: str,
    ) -> ExperienceEvent:
        if target.event_type not in {"tool_failed", "response_generated", "grounding_evaluated"}:
            raise ValueError("user correction target must be a failed tool or response evidence event")
        return self._add(
            "user_corrected",
            {
                "correction_preview": compact_preview(correction),
                "target_event_ids": [target.id],
            },
            [target],
        )

    def task_completed(
        self,
        tool_success: ExperienceEvent,
        *,
        task_id: str,
        result: str,
        verified: bool,
    ) -> ExperienceEvent:
        self._require_event_type(tool_success, "tool_succeeded")
        return self._add(
            "task_completed",
            {
                "task_id": self._identifier(task_id),
                "result_preview": compact_preview(result),
                "verified": bool(verified),
            },
            [tool_success],
        )

    def reflection_created(
        self,
        source: ExperienceEvent,
        *,
        reflection_id: str,
        summary: str,
        lesson_candidate_count: int,
    ) -> ExperienceEvent:
        if source.event_type not in {"task_completed", "tool_failed", "user_corrected"}:
            raise ValueError("reflection source must be completion, failure, or correction evidence")
        return self._add(
            "reflection_created",
            {
                "reflection_id": self._identifier(reflection_id),
                "summary_preview": compact_preview(summary),
                "lesson_candidate_count": max(0, min(int(lesson_candidate_count), 20)),
            },
            [source],
        )

    def lesson_candidate_created(
        self,
        reflection: ExperienceEvent,
        *,
        candidate_id: str,
        lesson: str,
        confidence: float,
        requires_operator_confirmation: bool = True,
    ) -> ExperienceEvent:
        self._require_event_type(reflection, "reflection_created")
        normalized_confidence = max(0.0, min(float(confidence), 1.0))
        return self._add(
            "lesson_candidate_created",
            {
                "candidate_id": self._identifier(candidate_id),
                "lesson_preview": compact_preview(lesson),
                "requires_operator_confirmation": bool(requires_operator_confirmation),
            },
            [reflection],
            confidence=normalized_confidence,
        )

    def memory_promoted(
        self,
        lesson: ExperienceEvent,
        *,
        memory_id: str,
        memory_type: str,
    ) -> ExperienceEvent:
        self._require_event_type(lesson, "lesson_candidate_created")
        return self._add(
            "memory_promoted",
            {
                "memory_id": self._identifier(memory_id),
                "memory_type": self._normalize_identifier(memory_type, fallback="lesson")[:80],
                "evidence_event_ids": [lesson.id],
                "operator_confirmation_required": True,
                "promotion_performed_by_builder": False,
            },
            [lesson],
        )

    def _add(
        self,
        event_type: str,
        payload: dict[str, object],
        sources: Iterable[ExperienceEvent] = (),
        *,
        confidence: float | None = None,
    ) -> ExperienceEvent:
        source_list = list(sources)
        known_ids = {event.id for event in self.events}
        unknown_sources = [event.id for event in source_list if event.id not in known_ids]
        if unknown_sources:
            raise ValueError("source events must already exist in this lifecycle trace")
        event = ExperienceEvent(
            id=(
                f"evt_{self.trace_id}_{self.turn_id}_{len(self.events) + 1:02d}_{event_type}"
            ),
            created_at=self.created_at,
            event_type=event_type,
            session_id=self.session_id,
            turn_id=self.turn_id,
            source="experience_vocabulary_preview",
            source_event_ids=[event.id for event in source_list],
            payload=payload,
            confidence=confidence,
        )
        self.events.append(event)
        return event

    @staticmethod
    def _require_event_type(event: ExperienceEvent, expected: str) -> None:
        if event.event_type != expected:
            raise ValueError(f"expected {expected} source event, got {event.event_type}")

    @staticmethod
    def _normalize_identifier(value: str, *, fallback: str) -> str:
        normalized = re.sub(r"[^A-Za-z0-9_.:-]+", "-", str(value).strip()).strip("-")
        return normalized[:120] or fallback

    def _identifier(self, value: str) -> str:
        return self._normalize_identifier(value, fallback="unknown")


def build_success_lifecycle_trace() -> list[ExperienceEvent]:
    builder = ExperienceLifecycleBuilder(
        session_id="experience-vocabulary-soak",
        trace_id="success",
        turn_id=1,
        created_at="2026-01-01T02:00:00Z",
    )
    goal = builder.goal_created(
        goal_id="goal_vocabulary",
        title="Verify typed experience lifecycle",
        priority="high",
        success_criteria="All provenance and privacy checks pass.",
    )
    plan = builder.plan_created(
        goal,
        plan_id="plan_vocabulary",
        plan="Build a local trace, inspect it, then verify a temporary hash chain.",
        step_count=3,
    )
    call = builder.tool_called(
        plan,
        call_id="call_local_doctor",
        capability="experience.doctor",
        input_summary="Inspect an in-memory lifecycle trace.",
        read_only=True,
    )
    success = builder.tool_succeeded(
        call,
        output_summary="Lifecycle doctor returned OK.",
        verified=True,
    )
    completed = builder.task_completed(
        success,
        task_id="task_vocabulary",
        result="Typed lifecycle and provenance checks passed.",
        verified=True,
    )
    reflection = builder.reflection_created(
        completed,
        reflection_id="reflection_vocabulary",
        summary="Explicit provenance makes promotion evidence inspectable.",
        lesson_candidate_count=1,
    )
    lesson = builder.lesson_candidate_created(
        reflection,
        candidate_id="lesson_vocabulary",
        lesson="Promote only verified lessons with operator confirmation.",
        confidence=0.9,
    )
    builder.memory_promoted(
        lesson,
        memory_id="memory_vocabulary",
        memory_type="lesson",
    )
    return list(builder.events)


def build_failure_correction_trace() -> list[ExperienceEvent]:
    builder = ExperienceLifecycleBuilder(
        session_id="experience-vocabulary-soak",
        trace_id="failure-correction",
        turn_id=2,
        created_at="2026-01-01T02:01:00Z",
    )
    goal = builder.goal_created(
        goal_id="goal_failure",
        title="Diagnose a failed local check",
        priority="normal",
    )
    plan = builder.plan_created(
        goal,
        plan_id="plan_failure",
        plan="Run one modeled check and preserve the observed failure.",
        step_count=1,
    )
    call = builder.tool_called(
        plan,
        call_id="call_failed_check",
        capability="local.check",
        input_summary="Modeled check only; no command is executed.",
        read_only=True,
    )
    failure = builder.tool_failed(
        call,
        error_type="validation_error",
        error_summary="Expected evidence was missing from the modeled result.",
        retryable=True,
    )
    correction = builder.user_corrected(
        failure,
        correction="Check the evidence source before retrying.",
    )
    reflection = builder.reflection_created(
        correction,
        reflection_id="reflection_failure",
        summary="The failed assumption must remain linked to the operator correction.",
        lesson_candidate_count=1,
    )
    builder.lesson_candidate_created(
        reflection,
        candidate_id="lesson_failure",
        lesson="Validate evidence availability before claiming task success.",
        confidence=0.8,
    )
    return list(builder.events)


def run_experience_vocabulary_benchmark() -> ExperienceVocabularyReport:
    success_events = build_success_lifecycle_trace()
    failure_events = build_failure_correction_trace()
    success_doctor = inspect_experience_events(success_events)
    failure_doctor = inspect_experience_events(failure_events)
    all_events = success_events + failure_events
    combined_doctor = inspect_experience_events(all_events)

    with TemporaryDirectory(prefix="proto-mind-experience-vocabulary-") as temp_dir:
        store = TemporaryExperienceLedgerStore(Path(temp_dir) / "experience_vocabulary.jsonl")
        store.append_events(success_events, stored_at="2026-01-01T03:00:00Z")
        store.append_events(failure_events, stored_at="2026-01-01T03:01:00Z")
        store_doctor = store.doctor()

    promotion = next(event for event in success_events if event.event_type == "memory_promoted")
    correction = next(event for event in failure_events if event.event_type == "user_corrected")
    checks = {
        "success_trace_valid": success_doctor.status == "OK",
        "failure_correction_trace_valid": failure_doctor.status == "OK",
        "combined_trace_valid": combined_doctor.status == "OK",
        "temporary_hash_chain_valid": store_doctor.status == "OK",
        "all_hashes_verified": store_doctor.hash_verified_count == len(all_events),
        "promotion_requires_confirmation": promotion.payload.get("operator_confirmation_required") is True
        and promotion.payload.get("promotion_performed_by_builder") is False,
        "correction_has_explicit_target": correction.payload.get("target_event_ids")
        == correction.source_event_ids,
        "no_tool_execution": all(
            event.payload.get("execution_performed_by_builder") is False
            for event in all_events
            if event.event_type == "tool_called"
        ),
        "compact_previews_only": all(
            not _contains_oversized_preview(event.payload) for event in all_events
        ),
    }
    failed_checks = [name for name, passed in checks.items() if not passed]
    return ExperienceVocabularyReport(
        status="OK" if not failed_checks else "FAIL",
        success_trace_events=len(success_events),
        failure_trace_events=len(failure_events),
        total_events=len(all_events),
        provenance_edges=combined_doctor.provenance_edge_count,
        hash_verified=store_doctor.hash_verified_count,
        checks=checks,
        failed_checks=failed_checks,
        boundary=(
            "Synthetic in-memory lifecycle adapters and isolated temporary hash-chain only; "
            "no goal/task/memory mutation, tool execution, live capture, command, LLM/API, or export."
        ),
    )


def _contains_oversized_preview(payload: object) -> bool:
    if isinstance(payload, dict):
        for key, value in payload.items():
            if key.endswith("_preview") and isinstance(value, str) and len(value) > 160:
                return True
            if _contains_oversized_preview(value):
                return True
    elif isinstance(payload, list):
        return any(_contains_oversized_preview(item) for item in payload)
    return False


def format_experience_vocabulary_report(
    report: ExperienceVocabularyReport | None = None,
) -> str:
    report = report or run_experience_vocabulary_benchmark()
    lines = [
        "Proto-Mind Experience Event Vocabulary v2",
        f"Status: {report.status}",
        f"success_trace_events: {report.success_trace_events}",
        f"failure_trace_events: {report.failure_trace_events}",
        f"total_events: {report.total_events}",
        f"provenance_edges: {report.provenance_edges}",
        f"temporary_hash_verified: {report.hash_verified}/{report.total_events}",
        "Checks:",
    ]
    lines.extend(
        f"- [{'PASS' if passed else 'FAIL'}] {name}" for name, passed in report.checks.items()
    )
    lines.extend(["Boundary:", f"- {report.boundary}"])
    return "\n".join(lines)


def main() -> int:
    report = run_experience_vocabulary_benchmark()
    print(format_experience_vocabulary_report(report))
    return 0 if report.status == "OK" else 1


if __name__ == "__main__":
    raise SystemExit(main())
