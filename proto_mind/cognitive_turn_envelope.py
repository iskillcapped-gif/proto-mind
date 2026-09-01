from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, fields, is_dataclass
from math import isfinite
from typing import Any

from proto_mind.models import InteractionResult


COGNITIVE_TURN_SCHEMA = "proto_mind.cognitive_turn.v1"
COGNITIVE_TURN_VERSION = 1
MEMORY_PREVIEW_MAX_CHARS = 240
ENVELOPE_UNAVAILABLE_WARNING = "Cognitive turn envelope unavailable; original text response preserved."


@dataclass(frozen=True)
class TurnObserver:
    query_type: str
    needs_memory: bool
    importance_hint: float
    topic_tags: tuple[str, ...]


@dataclass(frozen=True)
class TurnMemoryReference:
    record_id: str
    memory_type: str
    source: str
    active: bool
    content_preview: str
    preview_truncated: bool


@dataclass(frozen=True)
class TurnRetrieval:
    query_mode: str
    current_state_oriented: bool
    historical_state_oriented: bool
    broad_inventory: bool
    top_k: int


@dataclass(frozen=True)
class TurnMemoryDecision:
    memory_type: str
    should_store: bool
    stored_record_type: str | None
    stored_record_id: str | None
    should_promote_new: bool
    should_promote_existing: bool
    promoted_record_ids: tuple[str, ...]
    override_detected: bool
    superseded_record_ids: tuple[str, ...]
    storage_rationale: str
    promotion_rationale: str
    override_rationale: str


@dataclass(frozen=True)
class TurnGrounding:
    grounding_needed: bool
    grounding_status: str
    memory_support: str
    active_decision_status: str
    superseded_memory_status: str
    unsupported_claims: tuple[str, ...]
    warnings: tuple[str, ...]
    evidence: tuple[str, ...]
    confidence: str


@dataclass(frozen=True)
class TurnReflection:
    reflection_needed: bool
    memory_alignment: str
    preference_alignment: str
    active_decision_alignment: str
    superseded_memory_risk: str
    unsupported_claims_risk: str
    overall_confidence: str
    warnings: tuple[str, ...]
    suggested_next_turn_adjustments: tuple[str, ...]
    correction_hints: tuple[str, ...]
    should_carry_forward: bool
    carry_forward_scope: str


@dataclass(frozen=True)
class TurnContextInjection:
    enabled: bool
    applied: bool
    mode: str | None
    context_chars: int
    truncated: bool
    warning: str | None


@dataclass(frozen=True)
class CognitiveTurnEnvelope:
    response: str
    reasoner_backend: str
    observer: TurnObserver
    retrieved_memories: tuple[TurnMemoryReference, ...]
    retrieval: TurnRetrieval | None
    memory_decision: TurnMemoryDecision
    grounding: TurnGrounding | None
    reflection: TurnReflection | None
    previous_correction_hints: tuple[str, ...]
    context_injection: TurnContextInjection | None
    schema: str = field(default=COGNITIVE_TURN_SCHEMA, init=False)
    version: int = field(default=COGNITIVE_TURN_VERSION, init=False)
    projection_only: bool = field(default=True, init=False)
    memory_scope: str = field(default="retrieved_for_reasoner_not_proof_of_use", init=False)

    def to_dict(self) -> dict[str, Any]:
        return _plain_data(self)


@dataclass(frozen=True)
class InteractiveResponse:
    """A text response and optional local projection, never a second execution."""

    text: str | None
    cognitive_turn: CognitiveTurnEnvelope | None = None
    envelope_warning: str | None = None
    notices: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return _plain_data(self)


def build_cognitive_turn_envelope(
    result: InteractionResult,
    *,
    context_injection: Mapping[str, Any] | None = None,
) -> CognitiveTurnEnvelope:
    """Copy explicit fields of an already-completed turn without reading stores."""
    if not isinstance(result, InteractionResult):
        raise TypeError("Expected an InteractionResult.")
    observer = result.observer_state
    decision = result.memory_summary
    retrieval = result.retrieval_trace
    grounding = result.grounding_audit
    reflection = result.self_reflection

    memories: list[TurnMemoryReference] = []
    for record in result.retrieved_memory:
        compact = " ".join(_text(record.content).split())
        truncated = len(compact) > MEMORY_PREVIEW_MAX_CHARS
        preview = compact[: MEMORY_PREVIEW_MAX_CHARS - 3].rstrip() + "..." if truncated else compact
        memories.append(
            TurnMemoryReference(
                record_id=_text(record.id),
                memory_type=_text(record.type),
                source=_text(record.source),
                active=_flag(record.active),
                content_preview=preview,
                preview_truncated=truncated,
            )
        )

    return CognitiveTurnEnvelope(
        response=_text(result.response),
        reasoner_backend=_text(result.reasoner_backend),
        observer=TurnObserver(
            query_type=_text(observer.query_type),
            needs_memory=_flag(observer.needs_memory),
            importance_hint=_number(observer.importance_hint),
            topic_tags=_texts(observer.topic_tags),
        ),
        retrieved_memories=tuple(memories),
        retrieval=(
            TurnRetrieval(
                query_mode=_text(retrieval.query_mode),
                current_state_oriented=_flag(retrieval.current_state_oriented),
                historical_state_oriented=_flag(retrieval.historical_state_oriented),
                broad_inventory=_flag(retrieval.broad_inventory),
                top_k=_count(retrieval.top_k),
            )
            if retrieval is not None else None
        ),
        memory_decision=TurnMemoryDecision(
            memory_type=_text(decision.memory_type),
            should_store=_flag(decision.should_store),
            stored_record_type=_optional_text(decision.stored_record_type),
            stored_record_id=_optional_text(decision.stored_record_id),
            should_promote_new=_flag(decision.should_promote_new),
            should_promote_existing=_flag(decision.should_promote_existing),
            promoted_record_ids=_texts(decision.promoted_record_ids),
            override_detected=_flag(decision.override_detected),
            superseded_record_ids=_texts(decision.superseded_record_ids),
            storage_rationale=_text(decision.storage_rationale),
            promotion_rationale=_text(decision.promotion_rationale),
            override_rationale=_text(decision.override_rationale),
        ),
        grounding=(
            TurnGrounding(
                grounding_needed=_flag(grounding.grounding_needed),
                grounding_status=_text(grounding.grounding_status),
                memory_support=_text(grounding.memory_support),
                active_decision_status=_text(grounding.active_decision_status),
                superseded_memory_status=_text(grounding.superseded_memory_status),
                unsupported_claims=_texts(grounding.unsupported_claims),
                warnings=_texts(grounding.warnings),
                evidence=_texts(grounding.evidence),
                confidence=_text(grounding.confidence),
            )
            if grounding is not None else None
        ),
        reflection=(
            TurnReflection(
                reflection_needed=_flag(reflection.reflection_needed),
                memory_alignment=_text(reflection.memory_alignment),
                preference_alignment=_text(reflection.preference_alignment),
                active_decision_alignment=_text(reflection.active_decision_alignment),
                superseded_memory_risk=_text(reflection.superseded_memory_risk),
                unsupported_claims_risk=_text(reflection.unsupported_claims_risk),
                overall_confidence=_text(reflection.overall_confidence),
                warnings=_texts(reflection.warnings),
                suggested_next_turn_adjustments=_texts(reflection.suggested_next_turn_adjustments),
                correction_hints=_texts(reflection.correction_hints),
                should_carry_forward=_flag(reflection.should_carry_forward),
                carry_forward_scope=_text(reflection.carry_forward_scope),
            )
            if reflection is not None else None
        ),
        previous_correction_hints=_texts(result.previous_correction_hints),
        context_injection=(
            TurnContextInjection(
                enabled=_flag(context_injection["enabled"]),
                applied=_flag(context_injection["applied"]),
                mode=_optional_text(context_injection.get("mode")),
                context_chars=_count(context_injection.get("context_chars", 0)),
                truncated=_flag(context_injection.get("truncated", False)),
                warning=_optional_text(context_injection.get("warning")),
            )
            if context_injection is not None else None
        ),
    )


def project_interactive_response(
    text: str,
    result: InteractionResult,
    *,
    context_injection: Mapping[str, Any] | None = None,
    notices: tuple[str, ...] = (),
) -> InteractiveResponse:
    try:
        display_notices = _texts(notices)
        envelope = build_cognitive_turn_envelope(result, context_injection=context_injection)
        if not isinstance(envelope, CognitiveTurnEnvelope):
            raise TypeError("Invalid cognitive turn envelope.")
        return InteractiveResponse(text=text, cognitive_turn=envelope, notices=display_notices)
    except Exception:
        # A projection failure must not retry a completed turn or leak raw exception data.
        return InteractiveResponse(text=text, envelope_warning=ENVELOPE_UNAVAILABLE_WARNING)


def _text(value: object) -> str:
    if not isinstance(value, str):
        raise TypeError("Expected text.")
    return value


def _optional_text(value: object) -> str | None:
    return None if value is None else _text(value)


def _texts(value: object) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        raise TypeError("Expected a text sequence.")
    return tuple(_text(item) for item in value)


def _flag(value: object) -> bool:
    if type(value) is not bool:
        raise TypeError("Expected a boolean.")
    return value


def _count(value: object) -> int:
    if type(value) is not int or value < 0:
        raise ValueError("Expected a nonnegative integer.")
    return value


def _number(value: object) -> float:
    if type(value) not in (float, int) or not isfinite(value):
        raise ValueError("Expected a finite number.")
    return float(value)


def _plain_data(value: Any) -> Any:
    if is_dataclass(value):
        return {item.name: _plain_data(getattr(value, item.name)) for item in fields(value)}
    if isinstance(value, tuple):
        return [_plain_data(item) for item in value]
    return value
