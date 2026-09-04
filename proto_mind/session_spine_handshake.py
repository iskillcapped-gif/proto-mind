"""Detached Native commit/recovery handshake for the forward Session Spine.

P2h binds one already-saved exact Native turn, its canonical Work Session, a
stable installation owner, and a P2g compare-and-swap plan. There is no default
path or production Native caller. Recovery never reconstructs missing text or
pairs legacy evidence by time, order, or proximity.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
from typing import Any, Mapping
from uuid import UUID

from proto_mind.native_turn_lineage import NativeTurnLineageError, validate_turn_reference, verify_turn_reference
from proto_mind.native_work_sessions import WorkSessionError, inspect_work_session_copy
from proto_mind.session_spine import SessionEvent
from proto_mind.session_spine_forward import (
    ForwardNativeTurnPlan,
    SessionSpineForwardError,
    apply_forward_native_turn,
    preview_forward_native_turn,
    validate_forward_native_turn_plan,
)
from proto_mind.session_spine_store import (
    SessionSpineStore,
    SessionSpineStoreError,
    SessionSpineStoreMissing,
    inspect_store_image,
)


OWNER_SCHEMA = "proto_mind.native_session_spine_owner.v1"
HANDSHAKE_SCHEMA = "proto_mind.session_spine_commit_handshake.v1"
RECOVERY_SCHEMA = "proto_mind.session_spine_recovery_report.v1"
APPLY_SCHEMA = "proto_mind.session_spine_handshake_apply_receipt.v1"
NATIVE_APPLICATION_ID = "local.proto-mind.native"
OWNER_ROLE = "session_spine_forward_writer"
MAX_HISTORY_BYTES = 50 * 1024 * 1024
MAX_CONVERSATIONS = 10_000
MAX_MESSAGES = 100_000
HASH = re.compile(r"^[0-9a-f]{64}$")


class SessionSpineHandshakeError(RuntimeError):
    """The detached commit evidence is incomplete, stale, or conflicting."""


class _HistoryTurnError(SessionSpineHandshakeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError):
        raise SessionSpineHandshakeError("Session Spine handshake evidence is not lossless JSON.") from None


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _digest(value: object, label: str) -> str:
    if not isinstance(value, str) or not HASH.fullmatch(value):
        raise SessionSpineHandshakeError(f"{label} must be a lowercase SHA-256 digest.")
    return value


def _uuid(value: object, label: str, *, native: bool = False) -> str:
    if not isinstance(value, str):
        raise SessionSpineHandshakeError(f"{label} is invalid.")
    try:
        normalized = str(UUID(value))
    except (ValueError, AttributeError):
        raise SessionSpineHandshakeError(f"{label} is invalid.") from None
    allowed = {normalized, normalized.upper()} if native else {normalized}
    if value not in allowed:
        raise SessionSpineHandshakeError(f"{label} is not canonical UUID text.")
    return normalized


def _pairs(values: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in values:
        if key in result:
            raise SessionSpineHandshakeError("Native history contains a duplicate JSON field.")
        result[key] = value
    return result


def _constant(_: str) -> None:
    raise SessionSpineHandshakeError("Native history contains non-finite JSON.")


def _decode_history(raw: bytes) -> dict[str, Any]:
    if type(raw) is not bytes or not raw or len(raw) >= MAX_HISTORY_BYTES:
        raise SessionSpineHandshakeError("Native history readback is not bounded immutable bytes.")
    try:
        archive = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_pairs,
            parse_constant=_constant,
        )
    except SessionSpineHandshakeError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError, RecursionError):
        raise SessionSpineHandshakeError("Native history readback is not valid UTF-8 JSON.") from None
    if not isinstance(archive, dict) or type(archive.get("version")) is not int or archive["version"] not in {1, 2, 3, 4, 5}:
        raise SessionSpineHandshakeError("Native history version is unsupported.")
    conversations = archive.get("conversations")
    if not isinstance(conversations, list) or len(conversations) > MAX_CONVERSATIONS:
        raise SessionSpineHandshakeError("Native history conversation list is invalid or unbounded.")
    seen_conversations: set[str] = set()
    message_count = 0
    for conversation in conversations:
        if not isinstance(conversation, dict) or not isinstance(conversation.get("messages"), list):
            raise SessionSpineHandshakeError("Native history conversation shape is incomplete.")
        conversation_id = _uuid(conversation.get("id"), "Native conversation ID", native=True)
        if conversation_id in seen_conversations:
            raise SessionSpineHandshakeError("Native history contains duplicate conversation IDs.")
        seen_conversations.add(conversation_id)
        seen_messages: set[str] = set()
        for message in conversation["messages"]:
            if not isinstance(message, dict):
                raise SessionSpineHandshakeError("Native history message shape is invalid.")
            message_id = _uuid(message.get("id"), "Native message ID", native=True)
            if message_id in seen_messages:
                raise SessionSpineHandshakeError("Native history contains duplicate message IDs.")
            seen_messages.add(message_id)
            message_count += 1
            if message_count > MAX_MESSAGES:
                raise SessionSpineHandshakeError("Native history message count exceeds the handshake bound.")
            reference = message.get("turnReference")
            if reference is not None:
                try:
                    checked = validate_turn_reference(reference)
                except NativeTurnLineageError as error:
                    raise SessionSpineHandshakeError(f"Native history Turn Lineage is invalid: {error}") from None
                if checked["conversation_id"] != conversation_id:
                    raise SessionSpineHandshakeError("Native history Turn Lineage crosses conversation identity.")
    return archive


def _history_turn(
    raw: bytes,
    *,
    conversation_id: str,
    user_message_id: str,
    assistant_message_id: str,
    require_latest: bool,
) -> dict[str, Any]:
    archive = _decode_history(raw)
    conversation = _uuid(conversation_id, "Handshake conversation ID")
    user_id = _uuid(user_message_id, "Handshake user message ID")
    assistant_id = _uuid(assistant_message_id, "Handshake assistant message ID")
    selected = [row for row in archive["conversations"] if _uuid(row["id"], "Native conversation ID", native=True) == conversation]
    if len(selected) != 1:
        raise _HistoryTurnError("conversation_missing", "Exact Native conversation is absent from saved history.")
    messages = selected[0]["messages"]
    user_indexes = [index for index, row in enumerate(messages) if _uuid(row["id"], "Native message ID", native=True) == user_id]
    assistant_indexes = [index for index, row in enumerate(messages) if _uuid(row["id"], "Native message ID", native=True) == assistant_id]
    if len(user_indexes) != 1:
        raise _HistoryTurnError("user_message_missing", "Exact Native source message is absent from saved history.")
    if len(assistant_indexes) != 1:
        raise _HistoryTurnError("assistant_message_missing", "Exact Native assistant message is absent from saved history.")
    user_index, assistant_index = user_indexes[0], assistant_indexes[0]
    if assistant_index != user_index + 1:
        raise _HistoryTurnError("messages_not_adjacent", "Native turn messages are no longer one exact adjacent pair.")
    if require_latest and assistant_index != len(messages) - 1:
        raise _HistoryTurnError("turn_not_latest", "Only the latest saved Native turn can prepare a new commit handshake.")
    user, assistant = messages[user_index], messages[assistant_index]
    if (
        user.get("role") != "user"
        or not isinstance(user.get("text"), str)
        or user.get("isError") is not False
        or user.get("operatorInput") is True
        or assistant.get("role") != "assistant"
        or not isinstance(assistant.get("text"), str)
        or not isinstance(assistant.get("raw", ""), str)
        or assistant.get("isError") is not False
        or assistant.get("operatorInput") is True
    ):
        raise _HistoryTurnError("messages_ineligible", "Saved Native messages are not one eligible completed cognitive turn.")
    reference = assistant.get("turnReference")
    if not isinstance(reference, dict):
        raise _HistoryTurnError("turn_reference_missing", "Saved Native assistant message has no exact Turn Lineage reference.")
    material = {
        "conversation_id": conversation,
        "user_message": user,
        "assistant_message": assistant,
    }
    return {
        "archive": archive,
        "user": {**user, "id": user_id},
        "assistant": {**assistant, "id": assistant_id},
        "reference": reference,
        "turn_sha256": _sha256(_canonical(material)),
        "file_sha256": _sha256(raw),
        "file_bytes": len(raw),
    }


def _reference_count(archive: Mapping[str, Any], run_id: str) -> int:
    count = 0
    for conversation in archive["conversations"]:
        for message in conversation["messages"]:
            reference = message.get("turnReference")
            if isinstance(reference, dict) and reference.get("run_id") == run_id:
                count += 1
    return count


def build_native_owner_identity(
    installation_id: str,
    *,
    application_id: str = NATIVE_APPLICATION_ID,
) -> dict[str, Any]:
    """Build one stable installation-scoped writer identity without granting authority."""
    installation = _uuid(installation_id, "Native installation ID")
    if application_id != NATIVE_APPLICATION_ID:
        raise SessionSpineHandshakeError("Session Spine owner must name the exact Proto-Mind Native bundle.")
    derivation = {
        "schema": OWNER_SCHEMA,
        "format_version": 1,
        "application_id": application_id,
        "installation_id": installation,
        "role": OWNER_ROLE,
        "owner_scope": "native_installation",
    }
    result = {
        **derivation,
        "owner_id": "native-session-spine:" + _sha256(_canonical(derivation))[:32],
        "stable_across_relaunch": True,
        "process_id_bound": False,
        "os_user_bound": False,
        "permission_granted": False,
        "execution_authority_granted": False,
    }
    result["identity_hash"] = _sha256(_canonical(result))
    return result


def validate_native_owner_identity(value: object) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise SessionSpineHandshakeError("Native Session Spine owner identity is invalid.")
    identity = dict(value)
    expected = build_native_owner_identity(
        _uuid(identity.get("installation_id"), "Native installation ID"),
        application_id=identity.get("application_id"),
    )
    if identity != expected:
        raise SessionSpineHandshakeError("Native Session Spine owner identity does not verify.")
    return identity


def _plan_projection(plan: ForwardNativeTurnPlan) -> dict[str, Any]:
    return {
        "status": plan.status,
        "operation": plan.operation,
        "plan_hash": plan.plan_hash,
        "store_scope_sha256": plan.store_scope_sha256,
        "before_file_sha256": plan.before_file_sha256,
        "before_file_bytes": plan.before_file_bytes,
        "after_file_sha256": plan.after_file_sha256,
        "after_file_bytes": plan.after_file_bytes,
        "event_start": plan.event_start,
        "event_end": plan.event_end,
        "event_count": plan.event_count,
        "event_payload_sha256": plan.event_payload_sha256,
        "after_event_count": plan.after_event_count,
        "after_surface_fingerprint": plan.after_surface_fingerprint,
    }


def _plan_source_projection(plan: ForwardNativeTurnPlan, turn_receipt_hash: str) -> dict[str, Any]:
    return {
        "conversation_id": plan.session_id,
        "run_id": plan.run_id,
        "user_message_id": plan.user_message_id,
        "assistant_message_id": plan.assistant_message_id,
        "reference_hash": plan.reference_hash,
        "turn_receipt_hash": turn_receipt_hash,
        "input_sha256": plan.input_sha256,
        "displayed_answer_sha256": plan.displayed_answer_sha256,
        "raw_answer_sha256": plan.raw_answer_sha256,
    }


def prepare_native_turn_handshake(
    store: SessionSpineStore,
    *,
    owner_identity: Mapping[str, Any],
    history_raw: bytes,
    work_session_raw: bytes,
    work_session_name: str,
    conversation_id: str,
    user_message_id: str,
    assistant_message_id: str,
) -> dict[str, Any]:
    """Prepare a content-free handshake after exact Native history readback."""
    if not isinstance(store, SessionSpineStore):
        raise SessionSpineHandshakeError("Handshake preparation requires one explicit detached store.")
    identity = validate_native_owner_identity(owner_identity)
    conversation = _uuid(conversation_id, "Handshake conversation ID")
    user_id = _uuid(user_message_id, "Handshake user message ID")
    assistant_id = _uuid(assistant_message_id, "Handshake assistant message ID")
    try:
        history = _history_turn(
            history_raw,
            conversation_id=conversation,
            user_message_id=user_id,
            assistant_message_id=assistant_id,
            require_latest=True,
        )
        work_session = inspect_work_session_copy(work_session_raw, work_session_name)
        reference = verify_turn_reference(
            history["reference"],
            conversation_id=conversation,
            source_message_id=user_id,
            input_text=history["user"]["text"],
            response=history["assistant"].get("raw") or history["assistant"]["text"],
            work_session=work_session,
        )
    except (_HistoryTurnError, WorkSessionError, NativeTurnLineageError) as error:
        raise SessionSpineHandshakeError(f"Native commit source did not verify: {error}") from None
    if work_session_name != work_session["id"] + ".json":
        raise SessionSpineHandshakeError("Work Session filename does not match the exact Native run ID.")
    if _reference_count(history["archive"], work_session["id"]) != 1:
        raise SessionSpineHandshakeError("Native run identity is not referenced exactly once in saved history.")
    try:
        plan = preview_forward_native_turn(
            store,
            session_id=conversation,
            owner_id=identity["owner_id"],
            conversation_id=conversation,
            user_message=history["user"],
            assistant_message=history["assistant"],
            work_session=work_session,
            turn_reference=reference,
        )
        validate_forward_native_turn_plan(store, plan)
    except SessionSpineForwardError as error:
        raise SessionSpineHandshakeError(f"Forward commit plan did not verify: {error}") from None
    if plan.status != "READY" or plan.operation not in {"create", "append"}:
        raise SessionSpineHandshakeError("A new handshake requires an uncommitted exact forward turn.")

    material: dict[str, Any] = {
        "schema": HANDSHAKE_SCHEMA,
        "format_version": 1,
        "status": "PREPARED",
        "owner_identity": identity,
        "source": {
            "conversation_id": conversation,
            "run_id": work_session["id"],
            "user_message_id": user_id,
            "assistant_message_id": assistant_id,
            "reference_hash": reference["reference_hash"],
            "turn_receipt_hash": work_session["turn_receipt"]["receipt_hash"],
            "input_sha256": plan.input_sha256,
            "displayed_answer_sha256": plan.displayed_answer_sha256,
            "raw_answer_sha256": plan.raw_answer_sha256,
        },
        "history": {
            "file_sha256_at_prepare": history["file_sha256"],
            "file_bytes_at_prepare": history["file_bytes"],
            "turn_sha256": history["turn_sha256"],
            "latest_turn_at_prepare": True,
            "saved_and_read_back": True,
        },
        "work_session": {
            "filename": work_session_name,
            "file_sha256_at_prepare": _sha256(work_session_raw),
            "file_bytes_at_prepare": len(work_session_raw),
            "fingerprint_at_prepare": work_session["fingerprint"],
            "completed": True,
        },
        "spine": _plan_projection(plan),
        "ordering": {
            "steps": [
                "work_session_completed",
                "history_saved",
                "history_read_back",
                "handshake_prepared",
                "spine_compare_and_swap",
            ],
            "history_before_spine": True,
            "spine_before_history_forbidden": True,
        },
        "boundaries": {
            "content_free": True,
            "legacy_backfill": False,
            "inferred_pairing": False,
            "automatic_repair": False,
            "automatic_retry": False,
            "native_activation": False,
            "durable_handshake_store_installed": False,
            "history_write_performed": False,
            "work_session_write_performed": False,
            "spine_write_performed": False,
            "model_call_performed": False,
            "provider_call_performed": False,
            "command_executed": False,
            "permission_changed": False,
        },
    }
    material["handshake_hash"] = _sha256(_canonical(material))
    return material


def validate_native_turn_handshake(value: object) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise SessionSpineHandshakeError("Native turn handshake is invalid.")
    handshake = dict(value)
    digest = handshake.pop("handshake_hash", None)
    expected_top = {
        "schema", "format_version", "status", "owner_identity", "source", "history",
        "work_session", "spine", "ordering", "boundaries",
    }
    if set(handshake) != expected_top or digest != _sha256(_canonical(handshake)):
        raise SessionSpineHandshakeError("Native turn handshake hash or field set does not verify.")
    if handshake["schema"] != HANDSHAKE_SCHEMA or handshake["format_version"] != 1 or handshake["status"] != "PREPARED":
        raise SessionSpineHandshakeError("Native turn handshake schema or state is unsupported.")
    owner = validate_native_owner_identity(handshake["owner_identity"])
    source, history, work, spine = (handshake[name] for name in ("source", "history", "work_session", "spine"))
    if not all(isinstance(item, dict) for item in (source, history, work, spine)):
        raise SessionSpineHandshakeError("Native turn handshake sections are invalid.")
    if set(source) != {
        "conversation_id", "run_id", "user_message_id", "assistant_message_id", "reference_hash",
        "turn_receipt_hash", "input_sha256", "displayed_answer_sha256", "raw_answer_sha256",
    }:
        raise SessionSpineHandshakeError("Native turn handshake source schema is invalid.")
    for field in ("conversation_id", "run_id", "user_message_id", "assistant_message_id"):
        _uuid(source.get(field), f"Handshake {field}")
    for field in ("reference_hash", "turn_receipt_hash", "input_sha256", "displayed_answer_sha256", "raw_answer_sha256"):
        _digest(source.get(field), f"Handshake {field}")
    if set(history) != {"file_sha256_at_prepare", "file_bytes_at_prepare", "turn_sha256", "latest_turn_at_prepare", "saved_and_read_back"}:
        raise SessionSpineHandshakeError("Native turn handshake history schema is invalid.")
    _digest(history.get("file_sha256_at_prepare"), "Handshake history file digest")
    _digest(history.get("turn_sha256"), "Handshake history turn digest")
    if type(history.get("file_bytes_at_prepare")) is not int or history["file_bytes_at_prepare"] <= 0:
        raise SessionSpineHandshakeError("Native turn handshake history byte count is invalid.")
    if history.get("latest_turn_at_prepare") is not True or history.get("saved_and_read_back") is not True:
        raise SessionSpineHandshakeError("Native turn handshake lacks exact history readback evidence.")
    if set(work) != {"filename", "file_sha256_at_prepare", "file_bytes_at_prepare", "fingerprint_at_prepare", "completed"}:
        raise SessionSpineHandshakeError("Native turn handshake Work Session schema is invalid.")
    if work.get("filename") != source["run_id"] + ".json" or work.get("completed") is not True:
        raise SessionSpineHandshakeError("Native turn handshake Work Session identity is invalid.")
    _digest(work.get("file_sha256_at_prepare"), "Handshake Work Session file digest")
    _digest(work.get("fingerprint_at_prepare"), "Handshake Work Session fingerprint")
    if type(work.get("file_bytes_at_prepare")) is not int or work["file_bytes_at_prepare"] <= 0:
        raise SessionSpineHandshakeError("Native turn handshake Work Session byte count is invalid.")
    expected_spine = {
        "status", "operation", "plan_hash", "store_scope_sha256", "before_file_sha256", "before_file_bytes",
        "after_file_sha256", "after_file_bytes", "event_start", "event_end", "event_count",
        "event_payload_sha256", "after_event_count", "after_surface_fingerprint",
    }
    if set(spine) != expected_spine or spine.get("status") != "READY" or spine.get("operation") not in {"create", "append"}:
        raise SessionSpineHandshakeError("Native turn handshake Spine plan schema is invalid.")
    for field in ("plan_hash", "store_scope_sha256", "after_file_sha256", "event_payload_sha256", "after_surface_fingerprint"):
        _digest(spine.get(field), f"Handshake Spine {field}")
    before = spine.get("before_file_sha256")
    if before is not None:
        _digest(before, "Handshake Spine preimage digest")
    for field in ("before_file_bytes", "after_file_bytes", "event_start", "event_end", "event_count", "after_event_count"):
        if type(spine.get(field)) is not int or spine[field] < 0:
            raise SessionSpineHandshakeError(f"Handshake Spine {field} is invalid.")
    if (
        spine["after_file_bytes"] <= 0
        or spine["event_count"] <= 0
        or spine["after_event_count"] < spine["event_count"]
        or spine["event_end"] - spine["event_start"] + 1 != spine["event_count"]
        or (spine["operation"] == "create") != (before is None and spine["before_file_bytes"] == 0)
        or (spine["operation"] == "append" and spine["before_file_bytes"] <= 0)
        or owner["owner_id"] == ""
    ):
        raise SessionSpineHandshakeError("Native turn handshake Spine plan is internally inconsistent.")
    ordering = handshake["ordering"]
    if ordering != {
        "steps": [
            "work_session_completed", "history_saved", "history_read_back",
            "handshake_prepared", "spine_compare_and_swap",
        ],
        "history_before_spine": True,
        "spine_before_history_forbidden": True,
    }:
        raise SessionSpineHandshakeError("Native turn handshake commit ordering is invalid.")
    boundaries = handshake["boundaries"]
    expected_boundaries = {
        "content_free": True,
        "legacy_backfill": False,
        "inferred_pairing": False,
        "automatic_repair": False,
        "automatic_retry": False,
        "native_activation": False,
        "durable_handshake_store_installed": False,
        "history_write_performed": False,
        "work_session_write_performed": False,
        "spine_write_performed": False,
        "model_call_performed": False,
        "provider_call_performed": False,
        "command_executed": False,
        "permission_changed": False,
    }
    if boundaries != expected_boundaries:
        raise SessionSpineHandshakeError("Native turn handshake safety boundaries are invalid.")
    return {**handshake, "handshake_hash": digest}


def _turns(events: tuple[SessionEvent, ...]) -> tuple[tuple[SessionEvent, ...], ...]:
    turns: list[tuple[SessionEvent, ...]] = []
    start: int | None = None
    for index, event in enumerate(events):
        if event.event_type == "turn/start":
            if start is not None:
                raise SessionSpineHandshakeError("Stored Session Spine has overlapping turn boundaries.")
            start = index
        elif event.event_type == "turn/end":
            if start is None:
                raise SessionSpineHandshakeError("Stored Session Spine has an unmatched turn end.")
            turns.append(events[start:index + 1])
            start = None
    if start is not None:
        raise SessionSpineHandshakeError("Stored Session Spine ends inside an unresolved turn.")
    return tuple(turns)


def _turn_identity(events: tuple[SessionEvent, ...]) -> tuple[str, str, str]:
    run_id = _uuid(events[0].data.get("native_run_id"), "Stored Native run ID")
    user = [event.data.get("native_message_id") for event in events if event.event_type == "user/message"]
    assistant = [event.data.get("native_message_id") for event in events if event.event_type == "assistant/message"]
    if len(user) != 1 or len(assistant) != 1:
        raise SessionSpineHandshakeError("Stored Session Spine turn lacks one exact message pair.")
    return run_id, _uuid(user[0], "Stored Native user message ID"), _uuid(assistant[0], "Stored Native assistant message ID")


def _spine_observation(raw: bytes | None, handshake: Mapping[str, Any]) -> dict[str, Any]:
    expected = handshake["spine"]
    source = handshake["source"]
    if raw is None:
        return {
            "present": False,
            "valid": True,
            "owner_matches": True,
            "precondition_matches": expected["before_file_sha256"] is None,
            "target_state": "absent",
            "file_matches_candidate": False,
            "follow_on_turns": False,
            "error": "",
        }
    try:
        snapshot = inspect_store_image(raw, source["conversation_id"])
        if not snapshot.appendable or snapshot.recovery_state not in {"idle", "closed"}:
            raise SessionSpineHandshakeError(
                "Stored Session Spine is not at a verified appendable record boundary."
            )
        owner = handshake["owner_identity"]["owner_id"]
        owner_matches = snapshot.created_by == owner and all(value == owner for value in snapshot.append_owners)
        turns = _turns(snapshot.events)
        identities = tuple(_turn_identity(turn) for turn in turns)
        indexes = [index for index, identity in enumerate(identities) if identity[0] == source["run_id"]]
        if len(indexes) > 1:
            target_state = "duplicate_run"
        elif indexes:
            turn = turns[indexes[0]]
            identity = identities[indexes[0]]
            if identity != (source["run_id"], source["user_message_id"], source["assistant_message_id"]):
                target_state = "identity_conflict"
            elif _sha256(_canonical([event.to_dict() for event in turn])) != expected["event_payload_sha256"]:
                target_state = "payload_conflict"
            else:
                target_state = "exact"
        elif any(
            source["user_message_id"] in identity[1:] or source["assistant_message_id"] in identity[1:]
            for identity in identities
        ):
            target_state = "message_identity_conflict"
        else:
            target_state = "absent"
        file_sha = _sha256(raw)
        target_index = indexes[0] if len(indexes) == 1 else -1
        return {
            "present": True,
            "valid": True,
            "owner_matches": owner_matches,
            "precondition_matches": file_sha == expected["before_file_sha256"],
            "target_state": target_state,
            "file_matches_candidate": file_sha == expected["after_file_sha256"],
            "follow_on_turns": target_state == "exact" and target_index < len(turns) - 1,
            "error": "",
        }
    except (SessionSpineStoreError, SessionSpineHandshakeError) as error:
        return {
            "present": True,
            "valid": False,
            "owner_matches": False,
            "precondition_matches": False,
            "target_state": "unknown",
            "file_matches_candidate": False,
            "follow_on_turns": False,
            "error": str(error),
        }


def _report(
    handshake: Mapping[str, Any],
    *,
    status: str,
    state: str,
    eligible: bool,
    idempotent: bool,
    reasons: list[dict[str, str]],
    observed: dict[str, Any],
    next_action: str,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "schema": RECOVERY_SCHEMA,
        "format_version": 1,
        "status": status,
        "state": state,
        "handshake_hash": handshake["handshake_hash"],
        "source": dict(handshake["source"]),
        "eligible_for_spine_apply": eligible,
        "idempotent_no_write": idempotent,
        "reasons": reasons,
        "observed": observed,
        "next_action": next_action,
        "boundaries": {
            "read_only": True,
            "content_free": True,
            "legacy_backfill": False,
            "inferred_pairing": False,
            "automatic_repair": False,
            "automatic_retry": False,
            "history_write_performed": False,
            "work_session_write_performed": False,
            "spine_write_performed": False,
            "model_call_performed": False,
            "provider_call_performed": False,
            "command_executed": False,
            "permission_changed": False,
            "native_activation": False,
        },
    }
    result["report_hash"] = _sha256(_canonical(result))
    return result


def inspect_native_turn_handshake(
    handshake: Mapping[str, Any],
    *,
    owner_identity: Mapping[str, Any],
    history_raw: bytes | None,
    work_session_raw: bytes | None,
    work_session_name: str,
    spine_raw: bytes | None,
) -> dict[str, Any]:
    """Classify one relaunch/crash window from caller-supplied immutable bytes."""
    contract = validate_native_turn_handshake(handshake)
    source = contract["source"]
    expected_history = contract["history"]
    expected_work = contract["work_session"]
    reasons: list[dict[str, str]] = []

    try:
        current_owner = validate_native_owner_identity(owner_identity)
        owner_matches = current_owner["identity_hash"] == contract["owner_identity"]["identity_hash"]
    except SessionSpineHandshakeError:
        owner_matches = False

    history: dict[str, Any] | None = None
    history_error = ""
    if history_raw is not None:
        try:
            history = _history_turn(
                history_raw,
                conversation_id=source["conversation_id"],
                user_message_id=source["user_message_id"],
                assistant_message_id=source["assistant_message_id"],
                require_latest=False,
            )
        except _HistoryTurnError as error:
            history_error = error.code
        except SessionSpineHandshakeError:
            history_error = "history_invalid"
    else:
        history_error = "history_missing"
    history_snapshot_matches = history is not None and history["turn_sha256"] == expected_history["turn_sha256"]
    history_source_matches = history is not None and (
        _sha256(history["user"]["text"].encode("utf-8")) == source["input_sha256"]
        and _sha256(history["assistant"]["text"].encode("utf-8")) == source["displayed_answer_sha256"]
        and _sha256((history["assistant"].get("raw") or history["assistant"]["text"]).encode("utf-8")) == source["raw_answer_sha256"]
        and history["reference"].get("reference_hash") == source["reference_hash"]
    )
    history_turn_matches = history_snapshot_matches and history_source_matches
    history_file_matches = (
        history is not None
        and history["file_sha256"] == expected_history["file_sha256_at_prepare"]
        and history["file_bytes"] == expected_history["file_bytes_at_prepare"]
    )

    work_session: dict[str, Any] | None = None
    work_error = ""
    if work_session_raw is None:
        work_error = "work_session_missing"
    elif work_session_name != expected_work["filename"]:
        work_error = "work_session_filename_changed"
    else:
        try:
            work_session = inspect_work_session_copy(work_session_raw, work_session_name)
        except WorkSessionError:
            work_error = "work_session_invalid"
    work_identity_matches = work_session is not None and (
        work_session.get("id") == source["run_id"]
        and work_session.get("conversation_id") == source["conversation_id"]
        and (work_session.get("turn_receipt") or {}).get("receipt_hash") == source["turn_receipt_hash"]
        and (work_session.get("turn_receipt") or {}).get("input_sha256") == source["input_sha256"]
        and (work_session.get("turn_receipt") or {}).get("response_sha256") == source["raw_answer_sha256"]
    )
    work_file_matches = (
        work_session is not None
        and _sha256(work_session_raw) == expected_work["file_sha256_at_prepare"]
        and len(work_session_raw) == expected_work["file_bytes_at_prepare"]
    )
    work_fingerprint_matches = work_session is not None and work_session.get("fingerprint") == expected_work["fingerprint_at_prepare"]

    lineage_matches = False
    if history is not None and work_session is not None:
        try:
            verify_turn_reference(
                history["reference"],
                conversation_id=source["conversation_id"],
                source_message_id=source["user_message_id"],
                input_text=history["user"]["text"],
                response=history["assistant"].get("raw") or history["assistant"]["text"],
                work_session=work_session,
            )
            lineage_matches = history["reference"].get("reference_hash") == source["reference_hash"]
        except NativeTurnLineageError:
            lineage_matches = False

    spine = _spine_observation(spine_raw, contract)
    observed = {
        "owner": {"matches": owner_matches, "stable_across_relaunch": owner_matches},
        "history": {
            "present": history_raw is not None,
            "valid_exact_turn": history is not None,
            "snapshot_matches": history_snapshot_matches,
            "content_matches_source": history_source_matches,
            "turn_matches": history_turn_matches,
            "file_matches_prepare": history_file_matches,
            "error": history_error,
        },
        "work_session": {
            "present": work_session_raw is not None,
            "valid": work_session is not None,
            "identity_and_receipt_match": work_identity_matches,
            "file_matches_prepare": work_file_matches,
            "fingerprint_matches_prepare": work_fingerprint_matches,
            "error": work_error,
        },
        "lineage_matches": lineage_matches,
        "spine": spine,
    }

    if not owner_matches:
        reasons.append({"code": "owner_identity_mismatch", "severity": "ERROR", "summary": "Current Native installation owner differs from the prepared writer owner."})
        return _report(contract, status="ERROR", state="OWNER_IDENTITY_MISMATCH", eligible=False, idempotent=False,
                       reasons=reasons, observed=observed, next_action="inspect_owner_identity_no_write")
    if not spine["valid"]:
        reasons.append({"code": "spine_unknown", "severity": "ERROR", "summary": "Session Spine is not at a verifiable record boundary; automatic repair is forbidden."})
        return _report(contract, status="ERROR", state="MANUAL_SPINE_RECOVERY_REQUIRED", eligible=False, idempotent=False,
                       reasons=reasons, observed=observed, next_action="create_separate_manual_recovery_task")
    if not spine["owner_matches"]:
        reasons.append({"code": "spine_owner_mismatch", "severity": "ERROR", "summary": "Current Session Spine is not exclusively owned by this Native installation identity."})
        return _report(contract, status="ERROR", state="SPINE_OWNER_CONFLICT", eligible=False, idempotent=False,
                       reasons=reasons, observed=observed, next_action="inspect_store_owner_no_write")
    if spine["target_state"] in {"duplicate_run", "identity_conflict", "payload_conflict", "message_identity_conflict"}:
        reasons.append({"code": "spine_turn_conflict", "severity": "ERROR", "summary": "Stored run or message identity conflicts with the prepared exact turn."})
        return _report(contract, status="ERROR", state="SPINE_TURN_CONFLICT", eligible=False, idempotent=False,
                       reasons=reasons, observed=observed, next_action="inspect_conflicting_evidence_no_write")

    source_exact = history_turn_matches and work_identity_matches and lineage_matches
    if spine["target_state"] == "exact":
        if not source_exact:
            reasons.append({"code": "committed_source_unverified", "severity": "ERROR", "summary": "Spine contains the turn but its exact saved history or stable Work Session receipt is unavailable or changed."})
            return _report(contract, status="ERROR", state="STORE_ONLY_SOURCE_CONFLICT", eligible=False, idempotent=False,
                           reasons=reasons, observed=observed, next_action="inspect_source_copies_no_reconstruction")
        drift = []
        if not history_file_matches:
            drift.append("history_file_changed_after_prepare")
        if not work_file_matches or not work_fingerprint_matches:
            drift.append("work_session_metadata_changed_after_prepare")
        if not spine["file_matches_candidate"]:
            drift.append("spine_has_later_commits")
        if drift:
            reasons.extend({"code": code, "severity": "WARN", "summary": {
                "history_file_changed_after_prepare": "History file changed, while this exact saved turn still matches.",
                "work_session_metadata_changed_after_prepare": "Mutable Work Session metadata changed, while the stable turn receipt still matches.",
                "spine_has_later_commits": "Session Spine contains later turns after this exact committed turn.",
            }[code]} for code in drift)
            return _report(contract, status="WARN", state="COMMITTED_WITH_SOURCE_DRIFT", eligible=False, idempotent=True,
                           reasons=reasons, observed=observed, next_action="no_write_turn_already_committed")
        reasons.append({"code": "exact_commit_verified", "severity": "INFO", "summary": "Saved history, stable Work Session receipt, and exact Spine turn agree."})
        return _report(contract, status="OK", state="COMMITTED", eligible=False, idempotent=True,
                       reasons=reasons, observed=observed, next_action="none")

    if history is None:
        code = history_error or "history_turn_missing"
        summary = "Completed Work Session has no exact saved assistant turn; full response text is not reconstructed from its bounded preview."
        reasons.append({"code": code, "severity": "WARN", "summary": summary})
        state = "ORPHANED_COMPLETED_RUN" if work_identity_matches else "SOURCE_EVIDENCE_INCOMPLETE"
        return _report(contract, status="WARN", state=state, eligible=False, idempotent=False,
                       reasons=reasons, observed=observed, next_action="inspect_history_and_run_no_auto_reconstruction")
    if work_session is None:
        reasons.append({"code": work_error or "work_session_missing", "severity": "WARN", "summary": "Exact Work Session evidence is unavailable; no Spine write is eligible."})
        return _report(contract, status="WARN", state="SOURCE_EVIDENCE_INCOMPLETE", eligible=False, idempotent=False,
                       reasons=reasons, observed=observed, next_action="inspect_work_session_no_write")
    if not history_turn_matches or not work_identity_matches or not lineage_matches:
        reasons.append({"code": "source_lineage_conflict", "severity": "ERROR", "summary": "Saved messages, Turn Lineage, and stable run receipt do not identify the same exact turn."})
        return _report(contract, status="ERROR", state="SOURCE_LINEAGE_CONFLICT", eligible=False, idempotent=False,
                       reasons=reasons, observed=observed, next_action="inspect_source_conflict_no_write")
    if not history_file_matches or not work_file_matches or not work_fingerprint_matches:
        reasons.append({"code": "prepared_source_drift", "severity": "WARN", "summary": "Source files changed after preparation; rebuild an explicit handshake instead of replaying stale authority."})
        return _report(contract, status="WARN", state="PREPARED_SOURCE_DRIFT", eligible=False, idempotent=False,
                       reasons=reasons, observed=observed, next_action="prepare_new_handshake_after_review")
    if not spine["precondition_matches"]:
        reasons.append({"code": "spine_preimage_drift", "severity": "WARN", "summary": "Session Spine changed after preparation; the stale CAS plan cannot be applied."})
        return _report(contract, status="WARN", state="STALE_SPINE_PREIMAGE", eligible=False, idempotent=False,
                       reasons=reasons, observed=observed, next_action="inspect_spine_then_prepare_new_handshake")
    reasons.append({"code": "exact_sources_ready", "severity": "INFO", "summary": "Exact saved history, canonical Work Session, stable owner, and Spine preimage are ready."})
    return _report(contract, status="OK", state="READY_TO_COMMIT_SPINE", eligible=True, idempotent=False,
                   reasons=reasons, observed=observed, next_action="apply_exact_handshake_or_leave_unchanged")


def _read_store_image(store: SessionSpineStore, session_id: str) -> bytes | None:
    try:
        raw, _ = store.read_image(session_id)
        return raw
    except SessionSpineStoreMissing:
        return None
    except SessionSpineStoreError as error:
        raise SessionSpineHandshakeError(f"Session Spine precondition inspection failed: {error}") from None


def _store_scope_sha256(store: SessionSpineStore) -> str:
    return _sha256(str(Path(store.directory)).encode("utf-8"))


def _apply_receipt(
    handshake: Mapping[str, Any],
    *,
    result: str,
    write_performed: bool,
    forward_receipt: Mapping[str, Any] | None,
    recovery_report: Mapping[str, Any],
) -> dict[str, Any]:
    receipt: dict[str, Any] = {
        "schema": APPLY_SCHEMA,
        "format_version": 1,
        "result": result,
        "handshake_hash": handshake["handshake_hash"],
        "owner_id": handshake["owner_identity"]["owner_id"],
        "conversation_id": handshake["source"]["conversation_id"],
        "run_id": handshake["source"]["run_id"],
        "write_performed": write_performed,
        "written_scope": "explicit_session_spine_store_only" if write_performed else "none",
        "forward_receipt_hash": None if forward_receipt is None else forward_receipt["receipt_hash"],
        "recovery_report_hash": recovery_report["report_hash"],
        "post_state": recovery_report["state"],
        "idempotent_replay": not write_performed,
        "history_write_performed": False,
        "work_session_write_performed": False,
        "legacy_history_modified": False,
        "model_call_performed": False,
        "provider_call_performed": False,
        "command_executed": False,
        "permission_changed": False,
        "native_activation": False,
    }
    receipt["receipt_hash"] = _sha256(_canonical(receipt))
    return receipt


def apply_native_turn_handshake(
    store: SessionSpineStore,
    handshake: Mapping[str, Any],
    *,
    owner_identity: Mapping[str, Any],
    history_raw: bytes,
    work_session_raw: bytes,
    work_session_name: str,
) -> dict[str, Any]:
    """Apply only an exact READY handshake to its explicit detached Spine store."""
    if not isinstance(store, SessionSpineStore):
        raise SessionSpineHandshakeError("Handshake apply requires one explicit detached store.")
    contract = validate_native_turn_handshake(handshake)
    if _store_scope_sha256(store) != contract["spine"]["store_scope_sha256"]:
        raise SessionSpineHandshakeError("Handshake is bound to a different explicit Session Spine store.")
    spine_raw = _read_store_image(store, contract["source"]["conversation_id"])
    before = inspect_native_turn_handshake(
        contract,
        owner_identity=owner_identity,
        history_raw=history_raw,
        work_session_raw=work_session_raw,
        work_session_name=work_session_name,
        spine_raw=spine_raw,
    )
    if before["state"] in {"COMMITTED", "COMMITTED_WITH_SOURCE_DRIFT"}:
        return _apply_receipt(
            contract,
            result="ALREADY_COMMITTED",
            write_performed=False,
            forward_receipt=None,
            recovery_report=before,
        )
    if before["state"] != "READY_TO_COMMIT_SPINE" or before["eligible_for_spine_apply"] is not True:
        raise SessionSpineHandshakeError(f"Handshake is not eligible for Spine apply: {before['state']}.")

    history = _history_turn(
        history_raw,
        conversation_id=contract["source"]["conversation_id"],
        user_message_id=contract["source"]["user_message_id"],
        assistant_message_id=contract["source"]["assistant_message_id"],
        require_latest=True,
    )
    try:
        work_session = inspect_work_session_copy(work_session_raw, work_session_name)
        plan = preview_forward_native_turn(
            store,
            session_id=contract["source"]["conversation_id"],
            owner_id=contract["owner_identity"]["owner_id"],
            conversation_id=contract["source"]["conversation_id"],
            user_message=history["user"],
            assistant_message=history["assistant"],
            work_session=work_session,
            turn_reference=history["reference"],
        )
        validate_forward_native_turn_plan(store, plan)
    except (WorkSessionError, SessionSpineForwardError) as error:
        raise SessionSpineHandshakeError(f"Handshake apply could not reproduce its forward plan: {error}") from None
    if (
        _plan_projection(plan) != contract["spine"]
        or _plan_source_projection(
            plan,
            work_session["turn_receipt"]["receipt_hash"],
        ) != contract["source"]
    ):
        raise SessionSpineHandshakeError("Handshake apply reproduced different forward evidence; no write was attempted.")
    try:
        forward_receipt = apply_forward_native_turn(store, plan)
    except SessionSpineForwardError as error:
        raise SessionSpineHandshakeError(f"Handshake Spine write failed: {error}") from None
    after_raw = _read_store_image(store, contract["source"]["conversation_id"])
    after = inspect_native_turn_handshake(
        contract,
        owner_identity=owner_identity,
        history_raw=history_raw,
        work_session_raw=work_session_raw,
        work_session_name=work_session_name,
        spine_raw=after_raw,
    )
    if after["state"] != "COMMITTED":
        raise SessionSpineHandshakeError("Handshake post-write evidence is not one exact committed turn.")
    return _apply_receipt(
        contract,
        result="COMMITTED",
        write_performed=True,
        forward_receipt=forward_receipt,
        recovery_report=after,
    )
