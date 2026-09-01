from __future__ import annotations

from dataclasses import dataclass

from proto_mind.cognitive_turn_envelope import (
    COGNITIVE_TURN_SCHEMA,
    COGNITIVE_TURN_VERSION,
    CognitiveTurnEnvelope,
    InteractiveResponse,
    TurnMemoryReference,
)
from proto_mind.natural_commands import route_natural_command


CARD_MEMORY_LIMIT = 3
CARD_WARNING_LIMIT = 4
CARD_HINT_LIMIT = 2
CARD_UNAVAILABLE_NOTICE = "Cognitive turn card unavailable; original text response preserved."


@dataclass(frozen=True)
class CognitiveTurnCardViewModel:
    answer: str
    backend: str
    intent: str
    retrieval_mode: str
    grounding_status: str
    grounding_detail: str
    grounding_tone: str
    reflection_summary: str
    memory_decision: str
    memory_count: int
    memories: tuple[TurnMemoryReference, ...]
    omitted_memories: int
    context_state: str
    notices: tuple[str, ...]
    warnings: tuple[str, ...]
    omitted_warnings: int
    previous_hints: tuple[str, ...]
    omitted_previous_hints: int
    next_hints: tuple[str, ...]
    omitted_next_hints: int


def project_cognitive_turn_card(
    user_input: str,
    response: InteractiveResponse,
) -> CognitiveTurnCardViewModel | None:
    """Project a completed normal turn, without reading files or dispatching input."""
    if not isinstance(user_input, str) or not isinstance(response, InteractiveResponse):
        return None
    text = user_input.strip()
    if not text or text.startswith("/") or text.lower() in {"exit", "quit", "q"}:
        return None
    if route_natural_command(text) is not None or response.envelope_warning is not None:
        return None
    turn = response.cognitive_turn
    if not isinstance(turn, CognitiveTurnEnvelope) or not isinstance(response.text, str):
        return None
    if (
        turn.schema != COGNITIVE_TURN_SCHEMA
        or type(turn.version) is not int
        or turn.version != COGNITIVE_TURN_VERSION
        or turn.projection_only is not True
        or turn.memory_scope != "retrieved_for_reasoner_not_proof_of_use"
    ):
        return None
    answer = _text(turn.response)
    # Bind the card to this response, not to cached metadata from a previous turn.
    if not response.text.startswith(f"Proto-Mind: {answer}\n"):
        return None
    notices = _texts(response.notices)
    memories = turn.retrieved_memories
    if not isinstance(memories, tuple):
        return None
    for memory in memories:
        if not isinstance(memory, TurnMemoryReference) or type(memory.active) is not bool:
            return None
        for value in (memory.record_id, memory.memory_type, memory.source, memory.content_preview):
            _text(value)
        if type(memory.preview_truncated) is not bool:
            return None

    warnings: list[str] = []
    grounding_status = "UNKNOWN"
    grounding_detail = "No grounding audit reported."
    grounding_tone = "unknown"
    grounding = turn.grounding
    if grounding is not None:
        grounding_status = _text(grounding.grounding_status).upper() or "UNKNOWN"
        grounding_detail = (
            f"Memory support: {_text(grounding.memory_support)}; "
            f"decision: {_text(grounding.active_decision_status)}; "
            f"confidence: {_text(grounding.confidence)}"
        )
        if grounding_status == "GROUNDED":
            grounding_tone = "neutral"
        warnings.extend(f"Grounding: {item}" for item in _texts(grounding.warnings))
        warnings.extend(f"Unsupported claim: {item}" for item in _texts(grounding.unsupported_claims))
        if warnings or grounding_status in {"CONTRADICTED", "UNGROUNDED", "PARTIALLY_GROUNDED"}:
            grounding_tone = "warn"

    reflection_summary = "UNKNOWN: no reflection reported."
    next_hints: tuple[str, ...] = ()
    reflection = turn.reflection
    if reflection is not None:
        reflection_summary = (
            f"Memory: {_text(reflection.memory_alignment)}; "
            f"preference: {_text(reflection.preference_alignment)}; "
            f"decision: {_text(reflection.active_decision_alignment)}; "
            f"confidence: {_text(reflection.overall_confidence)}"
        )
        warnings.extend(f"Reflection: {item}" for item in _texts(reflection.warnings))
        next_hints = _texts(reflection.suggested_next_turn_adjustments) + _texts(reflection.correction_hints)

    decision = turn.memory_decision
    stored_id = decision.stored_record_id
    if stored_id is not None:
        memory_decision = f"Stored {_text(decision.stored_record_type or 'record')}: {_text(stored_id)}"
    elif decision.should_store is True:
        memory_decision = "Storage requested; no stored record ID reported."
    elif decision.should_store is False:
        memory_decision = "No new memory record reported."
    else:
        raise TypeError("Invalid memory decision flag.")
    promoted = _texts(decision.promoted_record_ids)
    superseded = _texts(decision.superseded_record_ids)
    if promoted:
        memory_decision += f" Promoted: {len(promoted)}."
    if superseded:
        memory_decision += f" Superseded: {len(superseded)}."

    context_state = "UNKNOWN"
    injection = turn.context_injection
    if injection is not None:
        if type(injection.enabled) is not bool or type(injection.applied) is not bool:
            raise TypeError("Invalid context state.")
        if injection.applied and not injection.enabled:
            raise ValueError("Inconsistent context state.")
        context_state = "APPLIED" if injection.applied else "ENABLED / NOT APPLIED" if injection.enabled else "OFF"
    previous_hints = _texts(turn.previous_correction_hints)
    return CognitiveTurnCardViewModel(
        answer=answer,
        backend=_text(turn.reasoner_backend),
        intent=_text(turn.observer.query_type),
        retrieval_mode=_text(turn.retrieval.query_mode) if turn.retrieval is not None else "UNKNOWN",
        grounding_status=grounding_status,
        grounding_detail=grounding_detail,
        grounding_tone=grounding_tone,
        reflection_summary=reflection_summary,
        memory_decision=memory_decision,
        memory_count=len(memories),
        memories=memories[:CARD_MEMORY_LIMIT],
        omitted_memories=max(0, len(memories) - CARD_MEMORY_LIMIT),
        context_state=context_state,
        notices=notices,
        warnings=tuple(_preview(item) for item in warnings[:CARD_WARNING_LIMIT]),
        omitted_warnings=max(0, len(warnings) - CARD_WARNING_LIMIT),
        previous_hints=tuple(_preview(item) for item in previous_hints[:CARD_HINT_LIMIT]),
        omitted_previous_hints=max(0, len(previous_hints) - CARD_HINT_LIMIT),
        next_hints=tuple(_preview(item) for item in next_hints[:CARD_HINT_LIMIT]),
        omitted_next_hints=max(0, len(next_hints) - CARD_HINT_LIMIT),
    )


def _text(value: object) -> str:
    if not isinstance(value, str):
        raise TypeError("Expected text.")
    return value


def _texts(value: object) -> tuple[str, ...]:
    if not isinstance(value, tuple):
        raise TypeError("Expected immutable text sequence.")
    return tuple(_text(item) for item in value)


def _preview(value: str) -> str:
    compact = " ".join(value.split())
    return compact if len(compact) <= 200 else compact[:197].rstrip() + "..."
