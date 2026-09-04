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
