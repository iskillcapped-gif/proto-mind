"""Read-only live Session Spine preview for one exact Native turn.

This adapter reads one caller-selected work-session record by ID and fingerprint,
revalidates its content-free lineage, and returns a bounded content-free view of
the existing in-memory P1 projection. It never writes or replays an event.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Mapping
from uuid import UUID

from proto_mind.native_session_spine import NativeSessionProjectionError, project_native_turn
from proto_mind.native_turn_lineage import NativeTurnLineageError, verify_turn_reference
from proto_mind.native_work_sessions import WorkSessionError, WorkSessionStore


SCHEMA = "proto_mind.native_session_spine_live_preview.v1"
MAX_TIMELINE_EVENTS = 132
_REQUEST_FIELDS = {"conversation_id", "run", "turn_reference", "user_message", "assistant_message"}
_USER_FIELDS = {"id", "role", "text", "isError", "operatorInput"}
_ASSISTANT_FIELDS = {"id", "role", "text", "raw", "isError", "operatorInput"}
_SUGGESTION_FIELDS = {"memorySuggestions", "memorySuggestionSourceID"}
_TIMELINE_FIELDS = {
    "seq", "event_type", "time_ms", "surface_visible", "source_event_seqs",
    "stream", "part", "parts", "characters", "sha256", "tool_kind",
    "tool_status", "state", "outcome",
}
_HASH = re.compile(r"^[0-9a-f]{64}$")


class NativeSessionSpineLiveError(ValueError):
    """The selected Native turn cannot be previewed without widening or guessing."""


def _object(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise NativeSessionSpineLiveError(f"{label} must be an object.")
    return dict(value)


def _canonical_hash(value: object) -> str:
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError):
        raise NativeSessionSpineLiveError("Live Session Spine preview is not canonical JSON.") from None
    return hashlib.sha256(encoded).hexdigest()


def _normalized_uuid(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise NativeSessionSpineLiveError(f"{label} is invalid.")
    try:
        normalized = str(UUID(value))
    except ValueError:
        raise NativeSessionSpineLiveError(f"{label} is invalid.") from None
    if normalized != value:
        raise NativeSessionSpineLiveError(f"{label} is not normalized.")
    return value


def _messages(params: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    user = _object(params.get("user_message"), "Native user message")
    assistant = _object(params.get("assistant_message"), "Native assistant message")
    if set(user) != _USER_FIELDS:
        raise NativeSessionSpineLiveError("Native user message does not match the closed preview request.")
    assistant_fields = set(assistant)
    if assistant_fields != _ASSISTANT_FIELDS and assistant_fields != _ASSISTANT_FIELDS | _SUGGESTION_FIELDS:
        raise NativeSessionSpineLiveError("Native assistant message does not match the closed preview request.")
    if bool(assistant_fields & _SUGGESTION_FIELDS) != _SUGGESTION_FIELDS.issubset(assistant_fields):
        raise NativeSessionSpineLiveError("Native memory-suggestion lineage is incomplete.")
    return user, assistant


def _timeline(projection) -> list[dict[str, Any]]:
    visible = set(projection.surface.nodes)
    rows: list[dict[str, Any]] = []
    if len(projection.events) > MAX_TIMELINE_EVENTS:
        raise NativeSessionSpineLiveError("Live Session Spine timeline exceeds its UI boundary.")
    for event in projection.events:
        data = event.data
        row: dict[str, Any] = {
            "seq": event.seq,
            "event_type": event.event_type,
            "time_ms": event.time_ms,
            "surface_visible": event.seq in visible,
            "source_event_seqs": list(event.source_event_seqs or ()),
            "stream": None,
            "part": None,
            "parts": None,
            "characters": None,
            "sha256": None,
            "tool_kind": None,
            "tool_status": None,
            "state": None,
            "outcome": None,
        }
        if event.event_type in {"user/chunk", "assistant/chunk"}:
            text = data["text"]
            row.update(
                stream=data["stream"],
                part=data["part"],
                parts=data["parts"],
                characters=len(text),
                sha256=data["text_sha256"],
            )
        elif event.event_type == "user/message":
            content = data["content"]
            row.update(stream=content["stream"], characters=content["characters"], sha256=content["sha256"])
        elif event.event_type == "assistant/message":
            content = data["display_content"]
            row.update(stream=content["stream"], characters=content["characters"], sha256=content["sha256"])
        elif event.event_type == "tool/result":
            tool = data["tool"]
            row.update(tool_kind=tool.get("kind"), tool_status=tool.get("status"))
        elif event.event_type == "turn/start":
            row["state"] = data["display_status"]
        elif event.event_type == "turn/end":
            row["outcome"] = data["outcome"]
        if set(row) != _TIMELINE_FIELDS:
            raise NativeSessionSpineLiveError("Live Session Spine event summary is not closed.")
        rows.append(row)
    return rows


def build_live_session_spine_preview(
    store: WorkSessionStore,
    params: Mapping[str, Any],
) -> dict[str, Any]:
    """Resolve and preview one explicit Native turn; never scan, write, or execute."""
    if not isinstance(store, WorkSessionStore) or not isinstance(params, Mapping) or set(params) != _REQUEST_FIELDS:
        raise NativeSessionSpineLiveError("Live Session Spine preview request is invalid.")
    conversation_id = params.get("conversation_id")
    run_reference = _object(params.get("run"), "Native run reference")
    if set(run_reference) != {"run_id", "fingerprint"}:
        raise NativeSessionSpineLiveError("Native run reference must contain only ID and fingerprint.")
    _normalized_uuid(conversation_id, "Native conversation ID")
    _normalized_uuid(run_reference.get("run_id"), "Native run ID")
    if not isinstance(run_reference.get("fingerprint"), str) or not _HASH.fullmatch(run_reference["fingerprint"]):
        raise NativeSessionSpineLiveError("Native run fingerprint is invalid.")
    user, assistant = _messages(params)
    try:
        run = store.inspect(run_reference, conversation_id)
        response = assistant["raw"] or assistant["text"]
        reference = verify_turn_reference(
            params.get("turn_reference"),
            conversation_id=conversation_id,
            source_message_id=user["id"],
            input_text=user["text"],
            response=response,
            work_session=run,
        )
        projection = project_native_turn(
            conversation_id=conversation_id,
            user_message=user,
            assistant_message=assistant,
            work_session=run,
        )
    except (WorkSessionError, NativeTurnLineageError, NativeSessionProjectionError, TypeError, KeyError) as error:
        raise NativeSessionSpineLiveError(str(error)) from None
    if projection.display_status != "completed" or projection.assistant_message_seq is None:
        raise NativeSessionSpineLiveError("Only a completed exact Native turn can be previewed live.")

    material = {
        "schema": SCHEMA,
        "read_only": True,
        "source_record_read": True,
        "source_record_write": False,
        "no_write": True,
        "no_export": True,
        "no_migration": True,
        "no_model_call": True,
        "no_command_execution": True,
        "no_tool_replay": True,
        "no_permission_change": True,
        "context_injection_changed": False,
        "input_text_returned": False,
        "response_text_returned": False,
        "private_reasoning_included": False,
        "authoritative_history": False,
        "source": {
            "conversation_id": reference["conversation_id"],
            "user_message_id": user["id"],
            "assistant_message_id": assistant["id"],
            "run_id": projection.run_id,
            "run_fingerprint": projection.run_fingerprint,
            "reference_hash": reference["reference_hash"],
            "turn_receipt_hash": reference["turn_receipt_hash"],
            "display_status": projection.display_status,
            "provider": reference["provider"],
            "mode": reference["mode"],
        },
        "projection": projection.to_dict(),
        "timeline": _timeline(projection),
        "limitations": [
            "in_memory_projection_only",
            "not_authoritative_history",
            "no_task_success_or_provider_delivery_proof",
            "tool_evidence_not_replayable",
        ],
    }
    return {**material, "preview_hash": _canonical_hash(material)}
