"""Content-free lineage between one Native prompt, response and durable run."""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any
from uuid import UUID

from proto_mind.native_instructions import validate_instruction_receipt
from proto_mind.native_progress import display_text


TURN_RECEIPT_SCHEMA = "proto_mind.native_turn_receipt.v1"
TURN_REFERENCE_SCHEMA = "proto_mind.native_turn_reference.v1"
_HASH = re.compile(r"[0-9a-f]{64}\Z")
_MATERIAL_FIELDS = {
    "content_free",
    "input_text_stored",
    "response_text_stored",
    "response_observed",
    "task_success_verified",
    "provider_delivery_verified",
    "scope",
    "run_id",
    "conversation_id",
    "provider",
    "mode",
    "input_chars",
    "input_sha256",
    "response_chars",
    "response_sha256",
    "answer_preview_chars",
    "answer_preview_sha256",
    "instruction_receipt_hash",
}
_FIELDS = {"schema", *_MATERIAL_FIELDS, "receipt_hash", "hash_material"}
_REFERENCE_MATERIAL_FIELDS = {
    "content_free",
    "input_text_stored",
    "response_text_stored",
    "scope",
    "source_message_id",
    "run_id",
    "conversation_id",
    "provider",
    "mode",
    "input_chars",
    "input_sha256",
    "response_chars",
    "response_sha256",
    "turn_receipt_hash",
}
_REFERENCE_FIELDS = {
    "schema",
    *_REFERENCE_MATERIAL_FIELDS,
    "reference_hash",
    "hash_material",
}
_MAX_TEXT_CHARS = 100_000_000


class NativeTurnLineageError(ValueError):
    """Raised when content-free Native turn lineage cannot be verified."""


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
        raise NativeTurnLineageError("Native turn receipt is not canonical JSON.") from exc


def _uuid(value: object) -> str:
    if not isinstance(value, str):
        raise NativeTurnLineageError("Native turn receipt UUID is invalid.")
    try:
        normalized = str(UUID(value))
    except (ValueError, AttributeError):
        raise NativeTurnLineageError("Native turn receipt UUID is invalid.") from None
    if normalized != value:
        raise NativeTurnLineageError("Native turn receipt UUID is not normalized.")
    return value


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def build_turn_receipt(*, work_session: dict[str, Any], response: str) -> dict[str, Any]:
    """Fingerprint a completed provider response without retaining prompt or response text."""
    if not isinstance(work_session, dict) or not isinstance(response, str):
        raise NativeTurnLineageError("Native turn receipt inputs are invalid.")
    instruction = work_session.get("instruction_receipt")
    if not isinstance(instruction, dict):
        raise NativeTurnLineageError("A validated instruction receipt is required for turn lineage.")
    try:
        validate_instruction_receipt(instruction)
    except ValueError:
        raise NativeTurnLineageError("A validated instruction receipt is required for turn lineage.") from None
    preview = display_text(response, 1600)
    if (
        work_session.get("status") != "completed"
        or work_session.get("answer_preview") != preview
        or instruction["provider"] != work_session.get("provider")
        or instruction["mode"] != work_session.get("access_mode")
    ):
        raise NativeTurnLineageError("Completed work-session evidence does not match the turn receipt.")
    material = {
        "content_free": True,
        "input_text_stored": False,
        "response_text_stored": False,
        "response_observed": True,
        "task_success_verified": False,
        "provider_delivery_verified": False,
        "scope": "native_turn_metadata",
        "run_id": _uuid(work_session.get("id")),
        "conversation_id": _uuid(work_session.get("conversation_id")),
        "provider": work_session.get("provider"),
        "mode": work_session.get("access_mode"),
        "input_chars": work_session.get("input_chars"),
        "input_sha256": work_session.get("input_sha256"),
        "response_chars": len(response),
        "response_sha256": _sha256(response),
        "answer_preview_chars": len(preview),
        "answer_preview_sha256": _sha256(preview),
        "instruction_receipt_hash": instruction["receipt_hash"],
    }
    encoded = _canonical(material)
    receipt = {
        "schema": TURN_RECEIPT_SCHEMA,
        **material,
        "receipt_hash": hashlib.sha256(encoded).hexdigest(),
        "hash_material": encoded.decode("utf-8"),
    }
    return validate_turn_receipt(receipt)


def validate_turn_receipt(value: object) -> dict[str, Any]:
    """Validate a closed, content-free Native turn receipt."""
    if not isinstance(value, dict) or set(value) != _FIELDS:
        raise NativeTurnLineageError("Native turn receipt has an invalid shape.")
    if value["schema"] != TURN_RECEIPT_SCHEMA:
        raise NativeTurnLineageError("Native turn receipt schema is unsupported.")
    for field, expected in {
        "content_free": True,
        "input_text_stored": False,
        "response_text_stored": False,
        "response_observed": True,
        "task_success_verified": False,
        "provider_delivery_verified": False,
    }.items():
        if value[field] is not expected:
            raise NativeTurnLineageError(f"Native turn receipt {field} is invalid.")
    if value["scope"] != "native_turn_metadata":
        raise NativeTurnLineageError("Native turn receipt scope is invalid.")
    _uuid(value["run_id"])
    _uuid(value["conversation_id"])
    if value["provider"] not in {"codex", "ollama"}:
        raise NativeTurnLineageError("Native turn receipt provider is invalid.")
    if value["mode"] not in {"chat", "full_access"} or (
        value["provider"] == "ollama" and value["mode"] != "chat"
    ):
        raise NativeTurnLineageError("Native turn receipt mode is invalid.")
    for field in ("input_chars", "response_chars", "answer_preview_chars"):
        count = value[field]
        if type(count) is not int or not 0 <= count <= _MAX_TEXT_CHARS:
            raise NativeTurnLineageError("Native turn receipt character count is invalid.")
    if value["answer_preview_chars"] > 1_650:
        raise NativeTurnLineageError("Native turn receipt preview count exceeds its bound.")
    for field in (
        "input_sha256",
        "response_sha256",
        "answer_preview_sha256",
        "instruction_receipt_hash",
        "receipt_hash",
    ):
        if not isinstance(value[field], str) or not _HASH.fullmatch(value[field]):
            raise NativeTurnLineageError("Native turn receipt SHA-256 is invalid.")
    material = {key: value[key] for key in _MATERIAL_FIELDS}
    encoded = _canonical(material)
    if (
        not isinstance(value["hash_material"], str)
        or value["hash_material"] != encoded.decode("utf-8")
        or value["receipt_hash"] != hashlib.sha256(encoded).hexdigest()
    ):
        raise NativeTurnLineageError("Native turn receipt hash does not verify.")
    return value


def build_turn_reference(
    *,
    receipt: dict[str, Any],
    source_message_id: str,
    input_text: str,
    response: str,
) -> dict[str, Any]:
    """Mirror Native's content-free chat-to-run reference for strict local readers."""
    checked = validate_turn_receipt(receipt)
    source_id = _uuid(source_message_id)
    if not isinstance(input_text, str) or not isinstance(response, str):
        raise NativeTurnLineageError("Native turn reference inputs are invalid.")
    if len(input_text) > _MAX_TEXT_CHARS or len(response) > _MAX_TEXT_CHARS:
        raise NativeTurnLineageError("Native turn reference text exceeds its bounded contract.")
    if (
        checked["input_chars"] != len(input_text)
        or checked["input_sha256"] != _sha256(input_text)
        or checked["response_chars"] != len(response)
        or checked["response_sha256"] != _sha256(response)
    ):
        raise NativeTurnLineageError("Native turn reference text does not match its turn receipt.")
    material = {
        "content_free": True,
        "input_text_stored": False,
        "response_text_stored": False,
        "scope": "native_chat_to_work_session",
        "source_message_id": source_id,
        "run_id": checked["run_id"],
        "conversation_id": checked["conversation_id"],
        "provider": checked["provider"],
        "mode": checked["mode"],
        "input_chars": checked["input_chars"],
        "input_sha256": checked["input_sha256"],
        "response_chars": checked["response_chars"],
        "response_sha256": checked["response_sha256"],
        "turn_receipt_hash": checked["receipt_hash"],
    }
    encoded = _canonical(material)
    return validate_turn_reference({
        "schema": TURN_REFERENCE_SCHEMA,
        **material,
        "reference_hash": hashlib.sha256(encoded).hexdigest(),
        "hash_material": encoded.decode("utf-8"),
    })


def validate_turn_reference(value: object) -> dict[str, Any]:
    """Validate the closed Native history reference without opening a journal."""
    if not isinstance(value, dict) or set(value) != _REFERENCE_FIELDS:
        raise NativeTurnLineageError("Native turn reference has an invalid shape.")
    if value["schema"] != TURN_REFERENCE_SCHEMA:
        raise NativeTurnLineageError("Native turn reference schema is unsupported.")
    for field, expected in {
        "content_free": True,
        "input_text_stored": False,
        "response_text_stored": False,
    }.items():
        if value[field] is not expected:
            raise NativeTurnLineageError(f"Native turn reference {field} is invalid.")
    if value["scope"] != "native_chat_to_work_session":
        raise NativeTurnLineageError("Native turn reference scope is invalid.")
    for field in ("source_message_id", "run_id", "conversation_id"):
        _uuid(value[field])
    if value["provider"] not in {"codex", "ollama"}:
        raise NativeTurnLineageError("Native turn reference provider is invalid.")
    if value["mode"] not in {"chat", "full_access"} or (
        value["provider"] == "ollama" and value["mode"] != "chat"
    ):
        raise NativeTurnLineageError("Native turn reference mode is invalid.")
    for field in ("input_chars", "response_chars"):
        count = value[field]
        if type(count) is not int or not 0 <= count <= _MAX_TEXT_CHARS:
            raise NativeTurnLineageError("Native turn reference character count is invalid.")
    for field in (
        "input_sha256",
        "response_sha256",
        "turn_receipt_hash",
        "reference_hash",
    ):
        if not isinstance(value[field], str) or not _HASH.fullmatch(value[field]):
            raise NativeTurnLineageError("Native turn reference SHA-256 is invalid.")
    material = {key: value[key] for key in _REFERENCE_MATERIAL_FIELDS}
    encoded = _canonical(material)
    if (
        not isinstance(value["hash_material"], str)
        or value["hash_material"] != encoded.decode("utf-8")
        or value["reference_hash"] != hashlib.sha256(encoded).hexdigest()
    ):
        raise NativeTurnLineageError("Native turn reference hash does not verify.")
    return value


def verify_turn_reference(
    value: object,
    *,
    conversation_id: str,
    source_message_id: str,
    input_text: str,
    response: str,
    work_session: dict[str, Any],
) -> dict[str, Any]:
    """Bind one checked history reference to exact messages and one inspected run."""
    reference = validate_turn_reference(value)
    conversation = _uuid(conversation_id)
    source_id = _uuid(source_message_id)
    if not isinstance(input_text, str) or not isinstance(response, str) or not isinstance(work_session, dict):
        raise NativeTurnLineageError("Native turn lineage evidence is invalid.")
    receipt = validate_turn_receipt(work_session.get("turn_receipt"))
    expected = {
        "source_message_id": source_id,
        "run_id": receipt["run_id"],
        "conversation_id": conversation,
        "provider": receipt["provider"],
        "mode": receipt["mode"],
        "input_chars": len(input_text),
        "input_sha256": _sha256(input_text),
        "response_chars": len(response),
        "response_sha256": _sha256(response),
        "turn_receipt_hash": receipt["receipt_hash"],
    }
    if any(reference[field] != expected[field] for field in expected):
        raise NativeTurnLineageError("Native turn reference does not match the exact messages and run.")
    if (
        work_session.get("id") != reference["run_id"]
        or work_session.get("conversation_id") != conversation
        or work_session.get("provider") != reference["provider"]
        or work_session.get("access_mode") != reference["mode"]
        or work_session.get("status") != "completed"
        or work_session.get("display_status") != "completed"
    ):
        raise NativeTurnLineageError("Native work session does not match the completed turn reference.")
    return reference
