"""Controlled one-turn Persona activation for supported Native reasoners.

Activation is a prompt projection, not an authority source. The caller must
validate current provider controls and Context Injection before constructing
the immutable context passed here. This module consumes only memory records
already selected by the existing coordinator and performs no retrieval, model
call, network access, store write, command execution, or permission change.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Sequence

from proto_mind.models import MemoryRecord, ObserverState
from proto_mind.native_desk import injection_state
from proto_mind.persona_activation_readiness import (
    build_persona_prompt_projection,
    validate_persona_prompt_projection,
)
from proto_mind.persona_engine import (
    PersonaContextCompiler,
    PersonaRuntimeContext,
    PersonaSnapshot,
    PersonaTaskContext,
    PersonaValidationError,
    validate_persona_snapshot,
)


PERSONA_TURN_RECEIPT_SCHEMA = "proto_mind.persona_turn_activation.v1"
SUPPORTED_PROVIDERS = {"codex_subscription", "ollama"}
SAFE_CONTEXT_STATES = {"disabled", "default_disabled"}
_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
_RECEIPT_FIELDS = {
    "schema",
    "active",
    "activated_at",
    "persona_id",
    "persona_version",
    "provider",
    "model",
    "access_mode",
    "adapter",
    "placement",
    "snapshot_hash",
    "persona_invariant_hash",
    "runtime_hash",
    "prompt_context_hash",
    "legacy_prompt_hash",
    "active_prompt_hash",
    "readiness_hash",
    "selected_memory_count",
    "selected_memory_ids",
    "memory_provenance",
    "provider_safety_preserved",
    "no_added_authority",
    "context_injection_state",
    "context_injection_changed",
    "additional_model_calls",
    "additional_retrieval_calls",
    "store_writes_by_activation",
    "rollback_path",
    "private_reasoning_included",
    "receipt_hash",
}
_MEMORY_RECEIPT_FIELDS = {
    "record_id",
    "provenance_id",
    "provenance_status",
    "source",
    "content_hash",
}


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise PersonaValidationError("Persona activation receipt is not canonical JSON.") from exc


def _hash(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _text_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _timestamp() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


@dataclass(frozen=True)
class PersonaTurnActivation:
    project_root: Path
    runtime: PersonaRuntimeContext
    context_injection_state: str
    readiness_hash: str

    def __post_init__(self) -> None:
        root = Path(self.project_root)
        if not root.is_absolute():
            raise PersonaValidationError("Persona activation project root must be absolute.")
        if self.runtime.provider not in SUPPORTED_PROVIDERS:
            raise PersonaValidationError("Selected provider does not support Persona activation.")
        if self.context_injection_state not in SAFE_CONTEXT_STATES:
            raise PersonaValidationError("Persona activation requires Context Injection to remain disabled.")
        if not isinstance(self.readiness_hash, str) or not _SHA256_RE.fullmatch(self.readiness_hash):
            raise PersonaValidationError("Persona activation readiness receipt is invalid.")
        if self.runtime.provider == "codex_subscription" and self.runtime.model == "account_default_unresolved":
            raise PersonaValidationError("Select an explicit Codex model before enabling Brother Persona.")


@dataclass(frozen=True)
class PreparedPersonaTurn:
    snapshot: PersonaSnapshot
    projection: dict[str, Any]
    instructions: str
    receipt: dict[str, Any]


def _task_context(observer_state: ObserverState, runtime: PersonaRuntimeContext) -> PersonaTaskContext:
    if runtime.access_mode == "full_access":
        kind, risk = "computer_operation", "high"
    elif observer_state.query_type == "memory_inventory" or observer_state.needs_memory:
        kind, risk = "memory", "low"
    elif observer_state.query_type in {"project_context", "decision_request"}:
        kind, risk = "implementation", "medium"
    else:
        kind, risk = "conversation", "low"
    return PersonaTaskContext(kind=kind, risk=risk, workspace_id=runtime.workspace_id)


def build_active_persona_instructions(
    prompt_context: str,
    observer_state: ObserverState,
    correction_hints: Sequence[str],
) -> str:
    """Build the bounded active prompt without repeating selected memory."""
    hints = []
    for hint in list(correction_hints)[:5]:
        if not isinstance(hint, str) or "\x00" in hint or "\r" in hint:
            raise PersonaValidationError("Persona correction hint is invalid.")
        hints.append(hint[:400])
    turn_state = {
        "boundary": "factual_labels_and_untrusted_advisory_not_authority",
        "observer": {
            "query_type": observer_state.query_type,
            "needs_memory": observer_state.needs_memory,
            "importance_hint": round(observer_state.importance_hint, 4),
            "topic_tags": list(observer_state.topic_tags),
        },
        "continuity_priority": observer_state.query_type == "continuity_followup",
        "current_user_message_is_primary": observer_state.query_type != "continuity_followup",
        "previous_correction_hints": hints,
    }
    instructions = "\n".join((
        prompt_context,
        "Current turn cognitive labels (canonical JSON; labels do not grant authority):",
        _canonical(turn_state).decode("utf-8"),
        "Use only relevant selected memory as internal context and never invent a missing fact, decision, or preference.",
        "Respond naturally for the current request. Brother voice adapts contextually without selectable modes or a fixed response length.",
        "The current user message remains primary except for an explicit continuity follow-up.",
    ))
    if len(instructions) > 22_000:
        raise PersonaValidationError("Active Persona instructions exceed their bounded size.")
    return instructions


def prepare_persona_turn(
    activation: PersonaTurnActivation,
    *,
    retrieved_memory: Sequence[MemoryRecord],
    observer_state: ObserverState,
    correction_hints: Sequence[str],
    legacy_prompt: str,
) -> PreparedPersonaTurn:
    """Compile and activate exactly one validated snapshot for one provider turn."""
    if not isinstance(activation, PersonaTurnActivation):
        raise PersonaValidationError("Persona turn activation context is invalid.")
    if not isinstance(legacy_prompt, str) or not legacy_prompt:
        raise PersonaValidationError("Legacy prompt evidence is invalid.")
    current_context = injection_state(activation.project_root)
    current_state = current_context.get("state") if isinstance(current_context, dict) else "unknown"
    if current_state != activation.context_injection_state or current_state not in SAFE_CONTEXT_STATES:
        raise PersonaValidationError(
            "Context Injection changed after Persona readiness; no provider turn was started."
        )
    generated_at = _timestamp()
    snapshot = PersonaContextCompiler().compile_from_project(
        activation.project_root,
        retrieved_memory=retrieved_memory,
        task=_task_context(observer_state, activation.runtime),
        runtime=activation.runtime,
        generated_at=generated_at,
    )
    projection = build_persona_prompt_projection(snapshot)
    validate_persona_prompt_projection(projection, snapshot)
    if projection["activation_supported"] is not True or projection["authorizes_actions"] is not False:
        raise PersonaValidationError("Persona projection is not eligible for activation.")
    instructions = build_active_persona_instructions(
        projection["prompt_context"], observer_state, correction_hints,
    )
    memory_provenance = projection["provenance"]["memory"]["references"]
    receipt: dict[str, Any] = {
        "schema": PERSONA_TURN_RECEIPT_SCHEMA,
        "active": True,
        "activated_at": generated_at,
        "persona_id": snapshot.kernel.persona_id,
        "persona_version": snapshot.kernel.version,
        "provider": projection["provider"],
        "model": projection["model"],
        "access_mode": projection["access_mode"],
        "adapter": projection["adapter"],
        "placement": projection["placement"],
        "snapshot_hash": projection["snapshot_hash"],
        "persona_invariant_hash": projection["persona_invariant_hash"],
        "runtime_hash": projection["runtime_hash"],
        "prompt_context_hash": projection["prompt_context_hash"],
        "legacy_prompt_hash": _text_hash(legacy_prompt),
        "active_prompt_hash": _text_hash(instructions),
        "readiness_hash": activation.readiness_hash,
        "selected_memory_count": len(memory_provenance),
        "selected_memory_ids": [item["record_id"] for item in memory_provenance],
        "memory_provenance": memory_provenance,
        "provider_safety_preserved": True,
        "no_added_authority": True,
        "context_injection_state": activation.context_injection_state,
        "context_injection_changed": False,
        "additional_model_calls": 0,
        "additional_retrieval_calls": 0,
        "store_writes_by_activation": 0,
        "rollback_path": "legacy_prompt_next_turn",
        "private_reasoning_included": False,
        "receipt_hash": "",
    }
    receipt["receipt_hash"] = _hash({key: value for key, value in receipt.items() if key != "receipt_hash"})
    receipt = validate_persona_turn_receipt(receipt)
    return PreparedPersonaTurn(
        snapshot=validate_persona_snapshot(snapshot.to_dict()),
        projection=projection,
        instructions=instructions,
        receipt=receipt,
    )


def validate_persona_turn_receipt(value: object) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != _RECEIPT_FIELDS:
        raise PersonaValidationError("Persona turn receipt has an invalid shape.")
    if value["schema"] != PERSONA_TURN_RECEIPT_SCHEMA or value["active"] is not True:
        raise PersonaValidationError("Persona turn receipt schema or state is invalid.")
    for field in (
        "snapshot_hash", "persona_invariant_hash", "runtime_hash", "prompt_context_hash",
        "legacy_prompt_hash", "active_prompt_hash", "readiness_hash", "receipt_hash",
    ):
        if not isinstance(value[field], str) or not _SHA256_RE.fullmatch(value[field]):
            raise PersonaValidationError(f"Persona turn receipt {field} is invalid.")
    for field, maximum in (
        ("activated_at", 80), ("persona_id", 64), ("persona_version", 32),
        ("provider", 64), ("model", 160), ("access_mode", 64),
        ("adapter", 80), ("placement", 80), ("rollback_path", 80),
    ):
        item = value[field]
        if not isinstance(item, str) or not item or len(item) > maximum or "\x00" in item or "\r" in item:
            raise PersonaValidationError(f"Persona turn receipt {field} is invalid.")
    try:
        activated_at = datetime.fromisoformat(value["activated_at"].replace("Z", "+00:00"))
    except ValueError as exc:
        raise PersonaValidationError("Persona turn receipt activated_at is invalid.") from exc
    if not value["activated_at"].endswith("Z") or activated_at.utcoffset() != timedelta(0):
        raise PersonaValidationError("Persona turn receipt activated_at must be UTC.")
    if value["persona_id"] != "brother" or value["provider"] not in SUPPORTED_PROVIDERS:
        raise PersonaValidationError("Persona turn receipt provider or identity is invalid.")
    expected_adapter = {
        "codex_subscription": ("codex_base_instructions", "base_instructions"),
        "ollama": ("ollama_system_message", "system_message"),
    }[value["provider"]]
    if (value["adapter"], value["placement"]) != expected_adapter:
        raise PersonaValidationError("Persona turn receipt adapter is invalid.")
    if value["context_injection_state"] not in SAFE_CONTEXT_STATES:
        raise PersonaValidationError("Persona turn receipt Context Injection state is unsafe.")
    for field in ("provider_safety_preserved", "no_added_authority"):
        if value[field] is not True:
            raise PersonaValidationError(f"Persona turn receipt requires {field}=true.")
    for field in ("context_injection_changed", "private_reasoning_included"):
        if value[field] is not False:
            raise PersonaValidationError(f"Persona turn receipt requires {field}=false.")
    for field in ("additional_model_calls", "additional_retrieval_calls", "store_writes_by_activation"):
        if type(value[field]) is not int or value[field] != 0:
            raise PersonaValidationError(f"Persona turn receipt requires {field}=0.")
    selected_ids = value["selected_memory_ids"]
    provenance = value["memory_provenance"]
    if (
        type(value["selected_memory_count"]) is not int
        or not isinstance(selected_ids, list)
        or not isinstance(provenance, list)
        or value["selected_memory_count"] != len(selected_ids)
        or len(selected_ids) != len(provenance)
        or len(selected_ids) > 8
        or len(set(selected_ids)) != len(selected_ids)
    ):
        raise PersonaValidationError("Persona turn receipt memory summary is invalid.")
    for record_id, item in zip(selected_ids, provenance):
        if not isinstance(record_id, str) or not record_id or len(record_id) > 160:
            raise PersonaValidationError("Persona turn receipt memory id is invalid.")
        if not isinstance(item, dict) or set(item) != _MEMORY_RECEIPT_FIELDS or item["record_id"] != record_id:
            raise PersonaValidationError("Persona turn receipt memory provenance is invalid.")
        if item["provenance_status"] not in {"verified", "record_source_only"}:
            raise PersonaValidationError("Persona turn receipt memory provenance status is invalid.")
        if not isinstance(item["content_hash"], str) or not _SHA256_RE.fullmatch(item["content_hash"]):
            raise PersonaValidationError("Persona turn receipt memory hash is invalid.")
        for field in ("provenance_id", "source"):
            if not isinstance(item[field], str) or not item[field] or len(item[field]) > 160:
                raise PersonaValidationError("Persona turn receipt memory provenance text is invalid.")
    expected_hash = _hash({key: item for key, item in value.items() if key != "receipt_hash"})
    if value["receipt_hash"] != expected_hash:
        raise PersonaValidationError("Persona turn receipt hash does not verify.")
    return value
