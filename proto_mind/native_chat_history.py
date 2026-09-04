"""Read-only v6 conversation storage adapter for an exact Session Spine turn.

The complete manifest is hashed into the detached v5 turn snapshot. Only the
selected immutable conversation is opened; no history migration or writer runs.
"""
from __future__ import annotations

import hashlib
import json
import fcntl
import os
import stat
from collections.abc import Callable
from functools import wraps
from uuid import UUID


FILE_LIMIT = 50 * 1024 * 1024


class NativeChatHistoryError(ValueError):
    pass


def locked_history_read(function):
    """Hold the existing Native history lock across an exact writer operation.

    Legacy reads do not initialize a missing lock. A v6 Native save creates it
    before publishing the first manifest and never replaces its inode.
    """
    @wraps(function)
    def locked(work_sessions, state_root, params):
        try:
            descriptor = os.open(state_root / ".history.lock", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        except FileNotFoundError:
            return function(work_sessions, state_root, params)
        try:
            if not stat.S_ISREG(os.fstat(descriptor).st_mode):
                raise NativeChatHistoryError("History lock is not a regular file.")
            try:
                fcntl.flock(descriptor, fcntl.LOCK_SH | fcntl.LOCK_NB)
            except BlockingIOError:
                raise NativeChatHistoryError("History is being saved by another Native process. Recheck after it finishes.") from None
            return function(work_sessions, state_root, params)
        finally:
            os.close(descriptor)
    return locked


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise NativeChatHistoryError("Duplicate history field.")
        result[key] = value
    return result


def _constant(value):
    raise NativeChatHistoryError("Non-finite history number.")


def _decode(raw):
    if type(raw) is not bytes or not 0 < len(raw) < FILE_LIMIT:
        raise NativeChatHistoryError("History source is not bounded bytes.")
    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs, parse_constant=_constant)
    except (UnicodeError, ValueError, TypeError, RecursionError) as error:
        raise NativeChatHistoryError("Invalid history JSON.") from error


def _uuid(value):
    if not isinstance(value, str):
        raise NativeChatHistoryError("Invalid history identity.")
    try:
        normalized = str(UUID(value))
    except ValueError:
        raise NativeChatHistoryError("Invalid history identity.") from None
    if value not in {normalized, normalized.upper()}:
        raise NativeChatHistoryError("Noncanonical history identity.")
    return normalized


def exact_turn_history(raw: bytes, conversation_id: str, read_object: Callable[[str], bytes]) -> bytes:
    manifest = _decode(raw)
    if not isinstance(manifest, dict) or type(manifest.get("version")) is not int:
        raise NativeChatHistoryError("Unsupported history format.")
    if manifest["version"] in {1, 2, 3, 4, 5}:
        return raw
    if (manifest["version"] != 6 or set(manifest) - {"version", "selectedID", "conversations"}
            or not isinstance(manifest.get("conversations"), list) or len(manifest["conversations"]) > 10_000):
        raise NativeChatHistoryError("Unsupported conversation manifest.")
    seen, runs, selected = set(), set(), None
    for entry in manifest["conversations"]:
        if not isinstance(entry, dict) or set(entry) != {"id", "sha256", "bytes", "runIDs"}:
            raise NativeChatHistoryError("Invalid conversation entry.")
        identifier = _uuid(entry["id"])
        digest = entry["sha256"]
        if (identifier in seen or not isinstance(digest, str) or len(digest) != 64
                or any(char not in "0123456789abcdef" for char in digest)
                or type(entry["bytes"]) is not int or not 0 < entry["bytes"] < FILE_LIMIT
                or not isinstance(entry["runIDs"], list)):
            raise NativeChatHistoryError("Invalid conversation digest or size.")
        seen.add(identifier)
        for run in entry["runIDs"]:
            if _uuid(run) != run or run in runs:
                raise NativeChatHistoryError("Ambiguous turn ownership in history.")
            runs.add(run)
        if identifier == conversation_id:
            selected = entry
    if manifest.get("selectedID") is not None and _uuid(manifest["selectedID"]) not in seen:
        raise NativeChatHistoryError("Selected conversation is absent.")
    if selected is None:
        raise NativeChatHistoryError("Exact conversation is absent.")
    conversation_raw = read_object(selected["sha256"] + ".json")
    if (type(conversation_raw) is not bytes or len(conversation_raw) != selected["bytes"]
            or hashlib.sha256(conversation_raw).hexdigest() != selected["sha256"]):
        raise NativeChatHistoryError("Conversation bytes changed or disappeared.")
    conversation = _decode(conversation_raw)
    if (not isinstance(conversation, dict) or _uuid(conversation.get("id")) != conversation_id
            or not isinstance(conversation.get("messages"), list)
            or any(not isinstance(message, dict) for message in conversation["messages"])):
        raise NativeChatHistoryError("Invalid conversation content.")
    references = [message.get("turnReference") for message in conversation["messages"] if message.get("turnReference") is not None]
    if any(not isinstance(reference, dict) for reference in references) or [ref.get("run_id") for ref in references] != selected["runIDs"]:
        raise NativeChatHistoryError("Conversation lineage differs from its manifest.")
    suffix = ('],"selectedID":"' + conversation_id.upper() + '","storage_manifest_sha256":"'
              + hashlib.sha256(raw).hexdigest() + '","version":5}').encode("ascii")
    return b'{"conversations":[' + conversation_raw + suffix
