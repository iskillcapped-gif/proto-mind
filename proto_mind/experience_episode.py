from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from dataclasses import asdict, dataclass
from pathlib import Path
import re
from tempfile import TemporaryDirectory
from typing import Any, Iterable

from proto_mind.experience_explainability import ExperienceTraceIndex
from proto_mind.experience_ledger import ExperienceEvent, TemporaryExperienceLedgerStore
from proto_mind.experience_vocabulary import (
    build_failure_correction_trace,
    build_success_lifecycle_trace,
)


@dataclass(frozen=True)
class ExperienceEpisode:
    id: str
    session_id: str
    turn_id: str
    status: str
    goal: dict[str, Any] | None
    expectation_preview: str
    plan: dict[str, Any] | None
    actions: list[dict[str, Any]]
    outcomes: list[dict[str, Any]]
    task_result: dict[str, Any] | None
    corrections: list[dict[str, Any]]
    reflections: list[dict[str, Any]]
    lesson_candidates: list[dict[str, Any]]
    memory_promotions: list[dict[str, Any]]
    verified: bool
    learning_state: str
    source_event_ids: list[str]
    warnings: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ExperienceEpisodeDoctorReport:
    status: str
    event_count: int
    episode_count: int
    verified_count: int
    failed_count: int
    corrected_count: int
    incomplete_count: int
    issues: list[str]
    warnings: list[str]


@dataclass(frozen=True)
class ExperienceEpisodeBenchmarkReport:
    status: str
    event_count: int
    episode_count: int
    success_episode_status: str
    failure_episode_status: str
    temporary_hash_verified: int
    checks: dict[str, bool]
    failed_checks: list[str]
    boundary: str


class ExperienceEpisodeProjectionError(RuntimeError):
    pass


class ExperienceEpisodeProjector:
    """Projects validated evidence into compact episodes without summarization or writes."""

    def __init__(self, events: Iterable[ExperienceEvent | dict[str, Any]]) -> None:
        self._events = [
            event.to_dict() if isinstance(event, ExperienceEvent) else deepcopy(dict(event))
            for event in events
        ]
        self._index = ExperienceTraceIndex(self._events)

    @classmethod
    def from_temporary_store(
        cls,
        store: TemporaryExperienceLedgerStore,
    ) -> "ExperienceEpisodeProjector":
        entries = store.read_entries()
        return cls(
            entry["event"]
            for entry in entries
            if isinstance(entry.get("event"), dict)
        )

    def project(self) -> list[ExperienceEpisode]:
        trace_report = self._index.doctor()
        if trace_report.status == "ERROR":
            raise ExperienceEpisodeProjectionError(
                "Experience trace failed validation: " + "; ".join(trace_report.issues)
            )
        grouped: defaultdict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
        for event in self._events:
            grouped[(str(event.get("session_id", "")), str(event.get("turn_id", "")))].append(
                event
            )
        return [self._project_group(key, group) for key, group in grouped.items()]

    def doctor(self) -> ExperienceEpisodeDoctorReport:
        trace_report = self._index.doctor()
        issues = list(trace_report.issues)
        warnings = list(trace_report.warnings)
        episodes: list[ExperienceEpisode] = []
        if not issues:
            episodes = self.project()
            for episode in episodes:
                warnings.extend(
                    f"Episode {episode.id}: {warning}" for warning in episode.warnings
                )
                for promotion in episode.memory_promotions:
                    if promotion.get("promotion_performed_by_builder") is not False:
                        issues.append(
                            f"Episode {episode.id} has promotion evidence without an explicit "
                            "no-auto-promotion marker."
                        )
                    if promotion.get("operator_confirmation_required") is not True:
                        issues.append(
                            f"Episode {episode.id} promotion lacks operator confirmation boundary."
                        )
        status = "ERROR" if issues else "WARN" if warnings else "OK"
        return ExperienceEpisodeDoctorReport(
            status=status,
            event_count=len(self._events),
            episode_count=len(episodes),
            verified_count=sum(episode.verified for episode in episodes),
            failed_count=sum(episode.status == "failed" for episode in episodes),
            corrected_count=sum(episode.status == "failed_corrected" for episode in episodes),
            incomplete_count=sum(episode.status == "incomplete" for episode in episodes),
            issues=issues,
            warnings=warnings,
        )

    @staticmethod
    def _project_group(
        key: tuple[str, str],
        events: list[dict[str, Any]],
    ) -> ExperienceEpisode:
        session_id, turn_id = key
        by_type: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
        for event in events:
            by_type[str(event.get("event_type"))].append(event)

        goal_event = _first(by_type["goal_created"])
        plan_event = _first(by_type["plan_created"])
        task_event = _first(by_type["task_completed"])
        goal = _select_payload(
            goal_event,
            "goal_id",
            "title_preview",
            "priority",
            "success_criteria_preview",
        )
        plan = _select_payload(plan_event, "plan_id", "goal_id", "step_count", "plan_preview")
        actions = [
            _select_payload(
                event,
                "call_id",
                "capability",
                "input_preview",
                "risk",
                "read_only",
                "execution_performed_by_builder",
            )
            for event in by_type["tool_called"]
        ]
        outcomes = [
            {
                "event_type": event.get("event_type"),
                **_select_payload(
                    event,
                    "call_id",
                    "output_preview",
                    "verified",
                    "error_type",
                    "error_preview",
                    "retryable",
                ),
            }
            for event in events
            if event.get("event_type") in {"tool_succeeded", "tool_failed"}
        ]
        corrections = [
            _select_payload(event, "correction_preview", "target_event_ids")
            for event in by_type["user_corrected"]
        ]
        reflections = [
            _select_payload(
                event,
                "reflection_id",
                "summary_preview",
                "lesson_candidate_count",
            )
            for event in by_type["reflection_created"]
        ]
        lessons = [
            {
                "event_id": event.get("id"),
                **_select_payload(
                    event,
                    "candidate_id",
                    "lesson_preview",
                    "requires_operator_confirmation",
                ),
                "confidence": event.get("confidence"),
            }
            for event in by_type["lesson_candidate_created"]
        ]
        promotions = [
            {
                "event_id": event.get("id"),
                **_select_payload(
                    event,
                    "memory_id",
                    "memory_type",
                    "evidence_event_ids",
                    "operator_confirmation_required",
                    "promotion_performed_by_builder",
                ),
            }
            for event in by_type["memory_promoted"]
        ]
        task_result = _select_payload(task_event, "task_id", "result_preview", "verified")
        tool_success_verified = bool(by_type["tool_succeeded"]) and all(
            event.get("payload", {}).get("verified") is True
            for event in by_type["tool_succeeded"]
        )
        task_verified = bool(task_event) and task_event.get("payload", {}).get("verified") is True
        verified = tool_success_verified and task_verified

        if task_event and verified:
            status = "completed_verified"
        elif task_event:
            status = "completed_unverified"
        elif by_type["user_corrected"]:
            status = "failed_corrected"
        elif by_type["tool_failed"]:
            status = "failed"
        elif by_type["tool_succeeded"]:
            status = "action_succeeded"
        else:
            status = "incomplete"

        if promotions:
            learning_state = "promotion_evidence_confirmation_required"
        elif lessons:
            learning_state = "lesson_candidate_pending"
        elif reflections:
            learning_state = "reflected_without_lesson"
        else:
            learning_state = "no_learning_candidate"

        warnings: list[str] = []
        if goal is None:
            warnings.append("No goal event is available; this is a partial/non-agent episode.")
        if status == "completed_unverified":
            warnings.append("Task completion is present without fully verified outcome evidence.")
        if status == "incomplete":
            warnings.append("No terminal outcome is available.")

        expectation = ""
        if goal:
            expectation = str(goal.get("success_criteria_preview") or "")
        if not expectation and plan:
            expectation = str(plan.get("plan_preview") or "")
        return ExperienceEpisode(
            id=f"episode_{_safe_id(session_id)}_{_safe_id(turn_id)}",
            session_id=session_id,
            turn_id=turn_id,
            status=status,
            goal=goal,
            expectation_preview=expectation,
            plan=plan,
            actions=actions,
            outcomes=outcomes,
            task_result=task_result,
            corrections=corrections,
            reflections=reflections,
            lesson_candidates=lessons,
            memory_promotions=promotions,
            verified=verified,
            learning_state=learning_state,
            source_event_ids=[str(event.get("id")) for event in events],
            warnings=warnings,
        )


def _first(events: list[dict[str, Any]]) -> dict[str, Any] | None:
    return events[0] if events else None


def _select_payload(event: dict[str, Any] | None, *keys: str) -> dict[str, Any] | None:
    if event is None:
        return None
    payload = event.get("payload", {})
    if not isinstance(payload, dict):
        return None
    return {key: deepcopy(payload.get(key)) for key in keys if key in payload}


def _safe_id(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "-", value).strip("-")[:80] or "unknown"


def format_experience_episode(episode: ExperienceEpisode) -> str:
    lines = [
        "Proto-Mind Experience Episode v1",
        "Status: OK" if not episode.warnings else "Status: WARN",
        f"episode_id: {episode.id}",
        f"session_id: {episode.session_id}",
        f"turn_id: {episode.turn_id}",
        f"outcome_status: {episode.status}",
        f"verified: {str(episode.verified).lower()}",
        f"learning_state: {episode.learning_state}",
        f"source_events: {len(episode.source_event_ids)}",
        "Goal:",
        f"- {_compact_mapping(episode.goal)}",
        f"Expectation: {episode.expectation_preview or 'none'}",
        "Plan:",
        f"- {_compact_mapping(episode.plan)}",
        "Actions:",
    ]
    lines.extend(f"- {_compact_mapping(item)}" for item in episode.actions)
    if not episode.actions:
        lines.append("- none")
    lines.append("Outcomes:")
    lines.extend(f"- {_compact_mapping(item)}" for item in episode.outcomes)
    if not episode.outcomes:
        lines.append("- none")
    lines.extend(
        [
            "Task result:",
            f"- {_compact_mapping(episode.task_result)}",
            "Corrections:",
        ]
    )
    lines.extend(f"- {_compact_mapping(item)}" for item in episode.corrections)
    if not episode.corrections:
        lines.append("- none")
    lines.append("Reflections:")
    lines.extend(f"- {_compact_mapping(item)}" for item in episode.reflections)
    if not episode.reflections:
        lines.append("- none")
    lines.append("Lesson candidates:")
    lines.extend(f"- {_compact_mapping(item)}" for item in episode.lesson_candidates)
    if not episode.lesson_candidates:
        lines.append("- none")
    lines.append("Memory promotion evidence:")
    lines.extend(f"- {_compact_mapping(item)}" for item in episode.memory_promotions)
    if not episode.memory_promotions:
        lines.append("- none")
    lines.extend(f"- WARN: {warning}" for warning in episode.warnings)
    lines.append("- Projection only: no memory, task, goal, tool, event, or file was changed.")
    return "\n".join(lines)


def _compact_mapping(value: dict[str, Any] | None) -> str:
    if not value:
        return "none"
    return "; ".join(f"{key}={_compact_value(item)}" for key, item in value.items())


def _compact_value(value: object) -> str:
    if isinstance(value, list):
        return ",".join(str(item) for item in value) or "none"
    if isinstance(value, bool):
        return str(value).lower()
    return str(value) if value is not None and value != "" else "none"


def format_experience_episode_list(episodes: Iterable[ExperienceEpisode]) -> str:
    episode_list = list(episodes)
    lines = [
        "Proto-Mind Experience Episode Projection v1",
        "Status: OK",
        f"episodes: {len(episode_list)}",
    ]
    for episode in episode_list:
        goal_id = episode.goal.get("goal_id") if episode.goal else "none"
        lines.append(
            f"- {episode.id}: status={episode.status}; goal={goal_id}; "
            f"verified={str(episode.verified).lower()}; learning={episode.learning_state}; "
            f"events={len(episode.source_event_ids)}"
        )
    lines.append("- Read-only live projection; no episode is persisted.")
    return "\n".join(lines)


def format_experience_episode_doctor(projector: ExperienceEpisodeProjector) -> str:
    report = projector.doctor()
    lines = [
        "Proto-Mind Experience Episode Doctor v1",
        f"Status: {report.status}",
        f"events: {report.event_count}",
        f"episodes: {report.episode_count}",
        f"verified: {report.verified_count}",
        f"failed: {report.failed_count}",
        f"corrected: {report.corrected_count}",
        f"incomplete: {report.incomplete_count}",
    ]
    lines.extend(f"- ERROR: {issue}" for issue in report.issues)
    lines.extend(f"- WARN: {warning}" for warning in report.warnings)
    if not report.issues and not report.warnings:
        lines.extend(
            [
                "- Episode evidence is structurally valid and terminal states are explicit.",
                "- Lesson candidates remain candidates; promotion retains confirmation boundaries.",
            ]
        )
    lines.append("- Doctor is read-only; no repair, consolidation, promotion, or persistence occurs.")
    return "\n".join(lines)


def run_experience_episode_benchmark() -> ExperienceEpisodeBenchmarkReport:
    success_events = build_success_lifecycle_trace()
    failure_events = build_failure_correction_trace()
    events = success_events + failure_events
    projector = ExperienceEpisodeProjector(events)
    episodes = projector.project()
    success_episode, failure_episode = episodes

    with TemporaryDirectory(prefix="proto-mind-experience-episode-") as temp_dir:
        store = TemporaryExperienceLedgerStore(Path(temp_dir) / "experience.jsonl")
        store.append_events(success_events, stored_at="2026-01-01T06:00:00Z")
        store.append_events(failure_events, stored_at="2026-01-01T06:01:00Z")
        stored_projector = ExperienceEpisodeProjector.from_temporary_store(store)
        stored_episodes = stored_projector.project()
        store_report = store.doctor()

    checks = {
        "episode_doctor_ok": projector.doctor().status == "OK",
        "two_lifecycle_episodes": len(episodes) == 2,
        "success_episode_verified": success_episode.status == "completed_verified"
        and success_episode.verified,
        "failure_episode_corrected": failure_episode.status == "failed_corrected"
        and not failure_episode.verified
        and bool(failure_episode.corrections),
        "success_learning_boundary": success_episode.learning_state
        == "promotion_evidence_confirmation_required"
        and success_episode.memory_promotions[0].get("promotion_performed_by_builder") is False,
        "failure_lesson_pending": failure_episode.learning_state == "lesson_candidate_pending"
        and not failure_episode.memory_promotions,
        "temporary_projection_matches": [episode.to_dict() for episode in stored_episodes]
        == [episode.to_dict() for episode in episodes],
        "temporary_hash_chain_valid": store_report.status == "OK"
        and store_report.hash_verified_count == len(events),
        "source_events_preserved": len(success_episode.source_event_ids) == len(success_events)
        and len(failure_episode.source_event_ids) == len(failure_events),
    }
    failed_checks = [name for name, passed in checks.items() if not passed]
    return ExperienceEpisodeBenchmarkReport(
        status="OK" if not failed_checks else "FAIL",
        event_count=len(events),
        episode_count=len(episodes),
        success_episode_status=success_episode.status,
        failure_episode_status=failure_episode.status,
        temporary_hash_verified=store_report.hash_verified_count,
        checks=checks,
        failed_checks=failed_checks,
        boundary=(
            "Deterministic read-only projection over in-memory and isolated temporary evidence; "
            "no LLM summarization, episode persistence, live capture, execution, domain mutation, "
            "memory promotion, command, or export."
        ),
    )


def format_experience_episode_benchmark(
    report: ExperienceEpisodeBenchmarkReport | None = None,
) -> str:
    report = report or run_experience_episode_benchmark()
    lines = [
        "Proto-Mind Experience Episode Projection v1",
        f"Status: {report.status}",
        f"events: {report.event_count}",
        f"episodes: {report.episode_count}",
        f"success_episode_status: {report.success_episode_status}",
        f"failure_episode_status: {report.failure_episode_status}",
        f"temporary_hash_verified: {report.temporary_hash_verified}/{report.event_count}",
        "Checks:",
    ]
    lines.extend(
        f"- [{'PASS' if passed else 'FAIL'}] {name}" for name, passed in report.checks.items()
    )
    lines.extend(["Boundary:", f"- {report.boundary}"])
    return "\n".join(lines)


def main() -> int:
    report = run_experience_episode_benchmark()
    print(format_experience_episode_benchmark(report))
    return 0 if report.status == "OK" else 1


if __name__ == "__main__":
    raise SystemExit(main())
