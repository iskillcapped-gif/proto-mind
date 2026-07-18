from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from dataclasses import asdict, dataclass
from typing import Any, Iterable

from proto_mind.experience_ledger import ExperienceEvent, inspect_experience_events


COGNITIVE_TURN_REQUIRED_TYPES = (
    "conversation_observed",
    "intent_detected",
    "memory_retrieved",
    "response_generated",
    "memory_evaluated",
    "reflection_evaluated",
    "grounding_evaluated",
)
COGNITIVE_TURN_OPTIONAL_TYPES = (
    "correction_guidance_applied",
    "memory_recorded",
)
COGNITIVE_TURN_EVENT_TYPES = frozenset(
    COGNITIVE_TURN_REQUIRED_TYPES + COGNITIVE_TURN_OPTIONAL_TYPES
)
_EVENT_ORDER = {
    event_type: index
    for index, event_type in enumerate(
        (
            "conversation_observed",
            "intent_detected",
            "memory_retrieved",
            "correction_guidance_applied",
            "response_generated",
            "memory_evaluated",
            "memory_recorded",
            "reflection_evaluated",
            "grounding_evaluated",
        )
    )
}


@dataclass(frozen=True)
class CognitiveTurnEpisode:
    session_id: str
    turn_id: str
    created_at: str
    status: str
    observe: dict[str, Any]
    interpret: dict[str, Any]
    recall: dict[str, Any]
    respond: dict[str, Any]
    memory_decision: dict[str, Any]
    memory_record: dict[str, Any] | None
    reflect: dict[str, Any]
    verify: dict[str, Any]
    event_ids: list[str]
    provenance_edge_count: int
    missing_event_types: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class CognitiveTurnProjectionError(RuntimeError):
    pass


class CognitiveTurnProjector:
    """Projects validated normal-turn evidence without writes or summarization."""

    def __init__(self, events: Iterable[ExperienceEvent | dict[str, Any]]) -> None:
        self._events = [
            event.to_dict() if isinstance(event, ExperienceEvent) else deepcopy(dict(event))
            for event in events
        ]

    def project(self) -> list[CognitiveTurnEpisode]:
        report = inspect_experience_events(self._events)
        if report.status == "ERROR":
            raise CognitiveTurnProjectionError(
                "Experience trace failed validation: " + "; ".join(report.issues)
            )

        grouped: defaultdict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
        for event in self._events:
            if event.get("event_type") in COGNITIVE_TURN_EVENT_TYPES:
                grouped[(str(event.get("session_id", "")), str(event.get("turn_id", "")))].append(
                    event
                )

        episodes = [self._project_group(key, events) for key, events in grouped.items()]
        return sorted(episodes, key=lambda item: (_turn_sort_key(item.turn_id), item.session_id))

    @staticmethod
    def _project_group(
        key: tuple[str, str],
        events: list[dict[str, Any]],
    ) -> CognitiveTurnEpisode:
        session_id, turn_id = key
        ordered = sorted(
            enumerate(events),
            key=lambda item: (_EVENT_ORDER.get(str(item[1].get("event_type")), 999), item[0]),
        )
        by_type: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
        for _, event in ordered:
            by_type[str(event.get("event_type"))].append(event)

        missing = [event_type for event_type in COGNITIVE_TURN_REQUIRED_TYPES if not by_type[event_type]]
        event_ids = [
            str(event.get("id"))
            for _, event in ordered
            if isinstance(event.get("id"), str) and event.get("id")
        ]
        return CognitiveTurnEpisode(
            session_id=session_id,
            turn_id=turn_id,
            created_at=str(events[0].get("created_at") or "unknown"),
            status="COMPLETE" if not missing else "INCOMPLETE",
            observe=_payload(by_type, "conversation_observed"),
            interpret=_payload(by_type, "intent_detected"),
            recall=_payload(by_type, "memory_retrieved"),
            respond=_payload(by_type, "response_generated"),
            memory_decision=_payload(by_type, "memory_evaluated"),
            memory_record=_optional_payload(by_type, "memory_recorded"),
            reflect=_payload(by_type, "reflection_evaluated"),
            verify=_payload(by_type, "grounding_evaluated"),
            event_ids=event_ids,
            provenance_edge_count=sum(
                len(event.get("source_event_ids") or []) for _, event in ordered
            ),
            missing_event_types=missing,
        )


def format_cognitive_turn_list(events: Iterable[ExperienceEvent | dict[str, Any]]) -> str:
    try:
        episodes = CognitiveTurnProjector(events).project()
    except CognitiveTurnProjectionError as exc:
        return f"Proto-Mind Cognitive Turn Episodes v1\nStatus: ERROR\n- {exc}"

    lines = [
        "Proto-Mind Cognitive Turn Episodes v1",
        f"Status: {'OK' if episodes else 'EMPTY'}",
        f"turns: {len(episodes)}",
        "Episodes:",
    ]
    if not episodes:
        lines.append("- none; enable the Experience pilot explicitly and complete a normal turn first.")
    for episode in episodes:
        lines.append(
            "- turn={turn} | status={status} | intent={intent} | recall={selected} selected | "
            "store={store} | grounding={grounding} | events={events}".format(
                turn=episode.turn_id,
                status=episode.status,
                intent=episode.interpret.get("query_type", "unknown"),
                selected=episode.recall.get("selected_count", 0),
                store=_bool(episode.memory_decision.get("should_store")),
                grounding=episode.verify.get("grounding_status", "unavailable"),
                events=len(episode.event_ids),
            )
        )
    lines.append("- Read-only projection from bounded process memory; no event or store was changed.")
    return "\n".join(lines)


def format_cognitive_turn_episode(
    events: Iterable[ExperienceEvent | dict[str, Any]],
    selector: str = "latest",
) -> str:
    try:
        episodes = CognitiveTurnProjector(events).project()
    except CognitiveTurnProjectionError as exc:
        return f"Proto-Mind Cognitive Turn Episode v1\nStatus: ERROR\n- {exc}"
    if not episodes:
        return "\n".join(
            [
                "Proto-Mind Cognitive Turn Episode v1",
                "Status: EMPTY",
                "- No captured normal-turn episode is available in process memory.",
                "- No event or store was changed.",
            ]
        )

    normalized = selector.strip() or "latest"
    episode = episodes[-1] if normalized.lower() == "latest" else next(
        (item for item in reversed(episodes) if item.turn_id == normalized),
        None,
    )
    if episode is None:
        return "\n".join(
            [
                "Proto-Mind Cognitive Turn Episode v1",
                "Status: NOT FOUND",
                f"- No captured episode matches turn {normalized!r}.",
                f"- Available turns: {', '.join(item.turn_id for item in episodes)}",
                "- No event or store was changed.",
            ]
        )
    return _format_episode(episode)


def _format_episode(episode: CognitiveTurnEpisode) -> str:
    selected_records = episode.recall.get("selected_records") or []
    reflection_warnings = episode.reflect.get("warning_previews") or []
    grounding_warnings = episode.verify.get("warning_previews") or []
    evidence = episode.verify.get("evidence_previews") or []
    lines = [
        "Proto-Mind Cognitive Turn Episode v1",
        f"Status: {episode.status}",
        f"session_id: {episode.session_id}",
        f"turn_id: {episode.turn_id}",
        f"created_at: {episode.created_at}",
        "",
        "Observe:",
        f"- input: {episode.observe.get('input_preview') or '(empty preview)'}",
        f"- chars: {episode.observe.get('input_chars', 0)} | language: {episode.observe.get('language_hint', 'unknown')}",
        "",
        "Interpret:",
        f"- intent: {episode.interpret.get('query_type', 'unknown')}",
        f"- needs_memory: {_bool(episode.interpret.get('needs_memory'))}",
        f"- importance: {episode.interpret.get('importance_hint', 'unknown')}",
        f"- topics: {_joined(episode.interpret.get('topic_tags'))}",
        "",
        "Recall:",
        f"- performed: {_bool(episode.recall.get('retrieval_performed'))} | mode: {episode.recall.get('query_mode', 'none')}",
        f"- candidates: {episode.recall.get('candidate_count', 0)} | selected: {episode.recall.get('selected_count', 0)}",
    ]
    if selected_records:
        lines.extend(
            f"- memory: {item.get('id')} | {item.get('type')} | {item.get('content_preview')}"
            for item in selected_records
            if isinstance(item, dict)
        )
    else:
        lines.append("- selected memory: none")
    lines.extend(
        [
            "",
            "Respond:",
            f"- backend: {episode.respond.get('reasoner_backend', 'unknown')}",
            f"- output: {episode.respond.get('response_preview') or '(empty preview)'}",
            f"- chars: {episode.respond.get('response_chars', 0)}",
            "",
            "Memory decision:",
            f"- should_store: {_bool(episode.memory_decision.get('should_store'))}",
            f"- type: {episode.memory_decision.get('memory_type') or 'none'} | importance: {episode.memory_decision.get('importance', 'unknown')}",
            f"- stored_record_id: {episode.memory_decision.get('stored_record_id') or 'none'}",
            f"- override: {_bool(episode.memory_decision.get('override_detected'))} | superseded: {_joined(episode.memory_decision.get('superseded_record_ids'))}",
            "",
            "Reflect:",
            f"- available: {_bool(episode.reflect.get('available'))} | needed: {_bool(episode.reflect.get('reflection_needed'))}",
            f"- confidence: {episode.reflect.get('overall_confidence', 'unknown')} | warnings: {episode.reflect.get('warning_count', 0)}",
            f"- warning previews: {_joined(reflection_warnings)}",
            "",
            "Verify:",
            f"- available: {_bool(episode.verify.get('available'))} | needed: {_bool(episode.verify.get('grounding_needed'))}",
            f"- status: {episode.verify.get('grounding_status', 'unavailable')} | memory_support: {episode.verify.get('memory_support', 'unknown')}",
            f"- confidence: {episode.verify.get('confidence', 'unknown')} | unsupported_claims: {episode.verify.get('unsupported_claim_count', 0)}",
            f"- evidence: {_joined(evidence)}",
            f"- warning previews: {_joined(grounding_warnings)}",
            "",
            "Provenance:",
            f"- event_count: {len(episode.event_ids)} | edges: {episode.provenance_edge_count}",
            *[f"- {event_id}" for event_id in episode.event_ids],
        ]
    )
    if episode.missing_event_types:
        lines.append(f"- missing event types: {', '.join(episode.missing_event_types)}")
    lines.extend(
        [
            "",
            "Boundary:",
            "- Deterministic compact projection only; no LLM summarization or inference was used.",
            "- No event, memory, skill, task, file, consent state, or context setting was changed.",
        ]
    )
    return "\n".join(lines)


def _payload(by_type: dict[str, list[dict[str, Any]]], event_type: str) -> dict[str, Any]:
    return _optional_payload(by_type, event_type) or {}


def _optional_payload(
    by_type: dict[str, list[dict[str, Any]]],
    event_type: str,
) -> dict[str, Any] | None:
    events = by_type.get(event_type) or []
    if not events:
        return None
    payload = events[0].get("payload")
    return deepcopy(payload) if isinstance(payload, dict) else {}


def _turn_sort_key(value: str) -> tuple[int, int | str]:
    try:
        return (0, int(value))
    except ValueError:
        return (1, value)


def _bool(value: object) -> str:
    if isinstance(value, bool):
        return str(value).lower()
    return "unknown" if value is None else str(value).lower()


def _joined(value: object) -> str:
    if not isinstance(value, (list, tuple)) or not value:
        return "none"
    return "; ".join(str(item) for item in value)
