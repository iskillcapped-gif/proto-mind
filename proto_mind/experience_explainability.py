from __future__ import annotations

from collections import Counter, defaultdict
from copy import deepcopy
from dataclasses import asdict, dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Iterable

from proto_mind.experience_ledger import (
    ExperienceEvent,
    TemporaryExperienceLedgerStore,
    inspect_experience_events,
)
from proto_mind.experience_vocabulary import (
    build_failure_correction_trace,
    build_success_lifecycle_trace,
)


@dataclass(frozen=True)
class ExperienceEventExplanation:
    event_id: str
    event_type: str
    session_id: str
    turn_id: str
    source: str
    direct_source_ids: list[str]
    direct_child_ids: list[str]
    lineage_event_ids: list[str]
    lineage_event_types: list[str]
    payload: dict[str, Any]
    why: str
    safety_note: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ExperienceExplainabilityDoctorReport:
    status: str
    event_count: int
    root_count: int
    leaf_count: int
    max_depth: int
    event_type_counts: dict[str, int]
    issues: list[str]
    warnings: list[str]


@dataclass(frozen=True)
class ExperienceExplainabilityBenchmarkReport:
    status: str
    event_count: int
    promotion_lineage_depth: int
    correction_lineage_depth: int
    temporary_hash_verified: int
    checks: dict[str, bool]
    failed_checks: list[str]
    boundary: str


class ExperienceTraceIndex:
    """Immutable read model for deterministic provenance explanations."""

    def __init__(self, events: Iterable[ExperienceEvent | dict[str, Any]]) -> None:
        self._events = [
            event.to_dict() if isinstance(event, ExperienceEvent) else deepcopy(dict(event))
            for event in events
        ]
        self._by_id = {
            str(event.get("id")): event
            for event in self._events
            if isinstance(event.get("id"), str)
        }
        children: defaultdict[str, list[str]] = defaultdict(list)
        for event in self._events:
            event_id = event.get("id")
            for source_id in event.get("source_event_ids", []):
                if isinstance(source_id, str) and isinstance(event_id, str):
                    children[source_id].append(event_id)
        self._children = {key: list(value) for key, value in children.items()}
        self._event_doctor = inspect_experience_events(self._events)

    @classmethod
    def from_temporary_store(
        cls,
        store: TemporaryExperienceLedgerStore,
    ) -> "ExperienceTraceIndex":
        entries = store.read_entries()
        return cls(
            entry["event"]
            for entry in entries
            if isinstance(entry.get("event"), dict)
        )

    @property
    def event_count(self) -> int:
        return len(self._events)

    def event_ids(self) -> list[str]:
        return [str(event.get("id")) for event in self._events if event.get("id")]

    def source_chain(self, event_id: str, *, include_target: bool = True) -> list[dict[str, Any]]:
        if event_id not in self._by_id:
            return []
        ordered_ids: list[str] = []
        visited: set[str] = set()
        visiting: set[str] = set()

        def visit(current_id: str) -> None:
            if current_id in visited or current_id in visiting:
                return
            visiting.add(current_id)
            current = self._by_id.get(current_id)
            if current is None:
                visiting.remove(current_id)
                return
            for source_id in current.get("source_event_ids", []):
                if isinstance(source_id, str):
                    visit(source_id)
            visiting.remove(current_id)
            visited.add(current_id)
            ordered_ids.append(current_id)

        visit(event_id)
        if not include_target and ordered_ids and ordered_ids[-1] == event_id:
            ordered_ids.pop()
        return [deepcopy(self._by_id[current_id]) for current_id in ordered_ids]

    def explain(self, event_id: str) -> ExperienceEventExplanation | None:
        event = self._by_id.get(event_id)
        if event is None:
            return None
        lineage = self.source_chain(event_id)
        event_type = str(event.get("event_type", "unknown"))
        return ExperienceEventExplanation(
            event_id=event_id,
            event_type=event_type,
            session_id=str(event.get("session_id", "")),
            turn_id=str(event.get("turn_id", "")),
            source=str(event.get("source", "")),
            direct_source_ids=list(event.get("source_event_ids", [])),
            direct_child_ids=list(self._children.get(event_id, [])),
            lineage_event_ids=[str(item.get("id")) for item in lineage],
            lineage_event_types=[str(item.get("event_type")) for item in lineage],
            payload=deepcopy(event.get("payload", {})),
            why=_why_event_exists(event_type, event.get("payload", {})),
            safety_note=_event_safety_note(event_type, event.get("payload", {})),
        )

    def find_by_entity_id(self, entity_id: str) -> list[ExperienceEventExplanation]:
        query = str(entity_id).strip()
        if not query:
            return []
        matches: list[ExperienceEventExplanation] = []
        for event in self._events:
            if _payload_contains_exact_value(event.get("payload", {}), query):
                explanation = self.explain(str(event.get("id")))
                if explanation:
                    matches.append(explanation)
        return matches

    def doctor(self) -> ExperienceExplainabilityDoctorReport:
        issues = list(self._event_doctor.issues)
        warnings = list(self._event_doctor.warnings)
        roots = [
            event
            for event in self._events
            if not event.get("source_event_ids")
        ]
        leaves = [
            event
            for event in self._events
            if not self._children.get(str(event.get("id")))
        ]
        if self._events and not roots:
            issues.append("Trace has events but no provenance root.")
        max_depth = max(
            (len(self.source_chain(str(event.get("id")))) for event in self._events),
            default=0,
        )
        counts = Counter(str(event.get("event_type")) for event in self._events)
        status = "ERROR" if issues else "WARN" if warnings else "OK"
        return ExperienceExplainabilityDoctorReport(
            status=status,
            event_count=len(self._events),
            root_count=len(roots),
            leaf_count=len(leaves),
            max_depth=max_depth,
            event_type_counts=dict(sorted(counts.items())),
            issues=issues,
            warnings=warnings,
        )


def _why_event_exists(event_type: str, payload: object) -> str:
    data = payload if isinstance(payload, dict) else {}
    explanations = {
        "conversation_observed": "Records that a compact operator input was observed.",
        "intent_detected": "Records the deterministic interpretation attached to the observed input.",
        "memory_retrieved": "Records which compact memory references were selected for the turn.",
        "response_generated": "Records that a response was generated, using a compact preview only.",
        "memory_evaluated": "Records the memory write decision without silently changing it here.",
        "memory_recorded": "Links a separately recorded memory id to its evaluation evidence.",
        "reflection_evaluated": "Records the deterministic response-alignment review.",
        "grounding_evaluated": "Records whether memory-sensitive claims had supporting evidence.",
        "correction_guidance_applied": "Records compact prior correction guidance used for one turn.",
        "goal_created": f"Establishes lifecycle root goal {data.get('goal_id', 'unknown')}.",
        "plan_created": f"Links plan {data.get('plan_id', 'unknown')} to its goal evidence.",
        "tool_called": "Records a modeled capability request; this event alone is not proof of execution.",
        "tool_succeeded": "Records a reported successful tool outcome linked to its call evidence.",
        "tool_failed": "Records a reported failed tool outcome linked to its call evidence.",
        "user_corrected": "Preserves an operator correction and the exact event it corrects.",
        "task_completed": "Records a claimed task completion linked to verified outcome evidence.",
        "reflection_created": "Records a structured reflection derived from completion, failure, or correction.",
        "lesson_candidate_created": "Records a candidate lesson derived from reflection, not active memory.",
        "memory_promoted": "Links a proposed/promoted memory id to its lesson evidence and approval boundary.",
    }
    return explanations.get(event_type, "Records a typed experience event with explicit provenance.")


def _event_safety_note(event_type: str, payload: object) -> str:
    data = payload if isinstance(payload, dict) else {}
    if event_type == "tool_called":
        return (
            "Evidence only; execution_performed_by_builder="
            f"{str(data.get('execution_performed_by_builder', False)).lower()}."
        )
    if event_type == "memory_promoted":
        return (
            "No automatic memory write; operator_confirmation_required="
            f"{str(data.get('operator_confirmation_required', True)).lower()}, "
            "promotion_performed_by_builder="
            f"{str(data.get('promotion_performed_by_builder', False)).lower()}."
        )
    if event_type == "lesson_candidate_created":
        return (
            "Candidate only; requires_operator_confirmation="
            f"{str(data.get('requires_operator_confirmation', True)).lower()}."
        )
    return "Read-only explanation of stored compact evidence; no command or mutation is performed."


def _payload_contains_exact_value(value: object, query: str) -> bool:
    if isinstance(value, dict):
        return any(_payload_contains_exact_value(item, query) for item in value.values())
    if isinstance(value, list):
        return any(_payload_contains_exact_value(item, query) for item in value)
    return isinstance(value, str) and value == query


def format_experience_event_explanation(index: ExperienceTraceIndex, event_id: str) -> str:
    explanation = index.explain(event_id)
    if explanation is None:
        return "\n".join(
            [
                "Proto-Mind Experience Event Explanation v1",
                "Status: NOT_FOUND",
                f"event_id: {event_id or 'missing'}",
                "- No event matched. No file, store, or trace was modified.",
            ]
        )
    lines = [
        "Proto-Mind Experience Event Explanation v1",
        "Status: OK",
        f"event_id: {explanation.event_id}",
        f"event_type: {explanation.event_type}",
        f"session_id: {explanation.session_id}",
        f"turn_id: {explanation.turn_id}",
        f"source: {explanation.source}",
        f"why: {explanation.why}",
        f"safety: {explanation.safety_note}",
        "direct_sources: " + (", ".join(explanation.direct_source_ids) or "none"),
        "direct_children: " + (", ".join(explanation.direct_child_ids) or "none"),
        "Source chain:",
    ]
    for position, (lineage_id, lineage_type) in enumerate(
        zip(explanation.lineage_event_ids, explanation.lineage_event_types),
        start=1,
    ):
        lines.append(f"{position}. {lineage_type} ({lineage_id})")
    lines.append("Payload (compact typed fields):")
    for key, value in sorted(explanation.payload.items()):
        lines.append(f"- {key}: {_format_payload_value(value)}")
    lines.append("- Read-only explanation: no event, domain store, or live state was changed.")
    return "\n".join(lines)


def _format_payload_value(value: object) -> str:
    if isinstance(value, list):
        return ", ".join(str(item) for item in value) or "none"
    if isinstance(value, bool):
        return str(value).lower()
    return str(value) if value is not None and value != "" else "none"


def format_experience_trace_map(index: ExperienceTraceIndex) -> str:
    report = index.doctor()
    lines = [
        "Proto-Mind Experience Trace Map v1",
        f"Status: {report.status}",
        f"events: {report.event_count}",
        f"roots: {report.root_count}",
        f"leaves: {report.leaf_count}",
        f"max_depth: {report.max_depth}",
        "Events:",
    ]
    for event_id in index.event_ids():
        explanation = index.explain(event_id)
        if explanation:
            source_types = [
                index.explain(source_id).event_type
                for source_id in explanation.direct_source_ids
                if index.explain(source_id)
            ]
            lines.append(
                f"- {explanation.event_type} ({event_id}) <- "
                + (", ".join(source_types) or "ROOT")
            )
    lines.append("- Read-only map: no event or store was changed.")
    return "\n".join(lines)


def format_experience_explainability_doctor(index: ExperienceTraceIndex) -> str:
    report = index.doctor()
    lines = [
        "Proto-Mind Experience Trace Explainability Doctor v1",
        f"Status: {report.status}",
        f"events: {report.event_count}",
        f"roots: {report.root_count}",
        f"leaves: {report.leaf_count}",
        f"max_depth: {report.max_depth}",
    ]
    lines.extend(f"- ERROR: {issue}" for issue in report.issues)
    lines.extend(f"- WARN: {warning}" for warning in report.warnings)
    if not report.issues and not report.warnings:
        lines.extend(
            [
                "- Event ids, roots, source links, payload contracts, and lineage are explainable.",
                "- Tool-call evidence is not treated as execution proof.",
                "- Lesson candidates and memory promotion retain approval boundaries.",
            ]
        )
    lines.append("- Doctor is read-only; no repair, capture, promotion, or execution is performed.")
    return "\n".join(lines)


def run_experience_explainability_benchmark() -> ExperienceExplainabilityBenchmarkReport:
    events = build_success_lifecycle_trace() + build_failure_correction_trace()
    index = ExperienceTraceIndex(events)
    promotion = next(event for event in events if event.event_type == "memory_promoted")
    correction = next(event for event in events if event.event_type == "user_corrected")
    promotion_explanation = index.explain(promotion.id)
    correction_explanation = index.explain(correction.id)

    with TemporaryDirectory(prefix="proto-mind-experience-explainability-") as temp_dir:
        store = TemporaryExperienceLedgerStore(Path(temp_dir) / "experience.jsonl")
        store.append_events(events[:8], stored_at="2026-01-01T05:00:00Z")
        store.append_events(events[8:], stored_at="2026-01-01T05:01:00Z")
        stored_index = ExperienceTraceIndex.from_temporary_store(store)
        store_report = store.doctor()

    promotion_lineage = promotion_explanation.lineage_event_types if promotion_explanation else []
    correction_lineage = correction_explanation.lineage_event_types if correction_explanation else []
    promotion_matches = index.find_by_entity_id("memory_vocabulary")
    checks = {
        "trace_doctor_ok": index.doctor().status == "OK",
        "promotion_lineage_complete": promotion_lineage
        == [
            "goal_created",
            "plan_created",
            "tool_called",
            "tool_succeeded",
            "task_completed",
            "reflection_created",
            "lesson_candidate_created",
            "memory_promoted",
        ],
        "correction_lineage_complete": correction_lineage
        == [
            "goal_created",
            "plan_created",
            "tool_called",
            "tool_failed",
            "user_corrected",
        ],
        "entity_query_finds_promotion": len(promotion_matches) == 1
        and promotion_matches[0].event_id == promotion.id,
        "missing_event_is_clean": index.explain("evt_missing") is None,
        "temporary_store_index_matches": stored_index.event_ids() == index.event_ids(),
        "temporary_hash_chain_valid": store_report.status == "OK"
        and store_report.hash_verified_count == len(events),
        "tool_call_not_execution_proof": "not proof of execution"
        in _why_event_exists("tool_called", {}),
        "promotion_approval_boundary_visible": promotion_explanation is not None
        and "operator_confirmation_required=true" in promotion_explanation.safety_note,
    }
    failed_checks = [name for name, passed in checks.items() if not passed]
    return ExperienceExplainabilityBenchmarkReport(
        status="OK" if not failed_checks else "FAIL",
        event_count=len(events),
        promotion_lineage_depth=len(promotion_lineage),
        correction_lineage_depth=len(correction_lineage),
        temporary_hash_verified=store_report.hash_verified_count,
        checks=checks,
        failed_checks=failed_checks,
        boundary=(
            "Read-only in-memory and isolated temporary trace inspection only; no live capture, "
            "tool execution, memory promotion, domain mutation, command, export, or LLM/API call."
        ),
    )


def format_experience_explainability_benchmark(
    report: ExperienceExplainabilityBenchmarkReport | None = None,
) -> str:
    report = report or run_experience_explainability_benchmark()
    lines = [
        "Proto-Mind Experience Trace Explainability v1",
        f"Status: {report.status}",
        f"events: {report.event_count}",
        f"promotion_lineage_depth: {report.promotion_lineage_depth}",
        f"correction_lineage_depth: {report.correction_lineage_depth}",
        f"temporary_hash_verified: {report.temporary_hash_verified}/{report.event_count}",
        "Checks:",
    ]
    lines.extend(
        f"- [{'PASS' if passed else 'FAIL'}] {name}" for name, passed in report.checks.items()
    )
    lines.extend(["Boundary:", f"- {report.boundary}"])
    return "\n".join(lines)


def main() -> int:
    report = run_experience_explainability_benchmark()
    print(format_experience_explainability_benchmark(report))
    return 0 if report.status == "OK" else 1


if __name__ == "__main__":
    raise SystemExit(main())
