"""P2l single-turn Native Session Spine writer pilot.

The adapter exposes one read-only preview and one exact-token apply operation.
It derives all writable paths from the Native private state root, reuses the
P2h/P2i contracts, never calls a model/tool/command, and never repairs unknown
evidence.
"""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import stat
from typing import Any, Iterator, Mapping

from proto_mind.native_session_spine_live import NativeSessionSpineLiveError, build_live_session_spine_preview
from proto_mind.native_work_sessions import WorkSessionError, WorkSessionStore
from proto_mind.session_spine_handshake import (
    MAX_HISTORY_BYTES,
    SessionSpineHandshakeError,
    inspect_native_history_turn_copy,
    prepare_native_turn_handshake,
    validate_native_owner_identity,
)
from proto_mind.session_spine_intent import (
    SessionSpineIntentError,
    SessionSpineIntentStore,
    apply_native_turn_intent,
    build_prepared_intent,
    inspect_native_turn_intent,
)
from proto_mind.session_spine_store import SessionSpineStore


PREVIEW_SCHEMA = "proto_mind.native_session_spine_writer_preview.v1"
RECEIPT_SCHEMA = "proto_mind.native_session_spine_writer_receipt.v1"
FORMAT_VERSION = 1
HASH = re.compile(r"^[0-9a-f]{64}$")
INTENT_ID = re.compile(r"^[0-9a-f]{32}$")
TOKEN = re.compile(r"^CONFIRM-SESSION-SPINE-[A-F0-9]{16}$")
BASE_FIELDS = {"conversation_id", "run", "turn_reference", "user_message", "assistant_message"}
GATE_FIELDS = {
    "acceptance_state", "candidate_hash", "readiness_report_hash", "rehearsal_hash", "acceptance_report_hash",
}
SOURCE_FIELDS = {
    "conversation_id", "user_message_id", "assistant_message_id", "run_id", "run_fingerprint",
    "turn_receipt_hash", "reference_hash", "live_preview_hash", "history_sha256", "history_bytes",
    "history_turn_sha256", "work_session_sha256", "work_session_bytes",
}
BOUNDARY_FIELDS = {
    "single_exact_latest_turn", "fixed_private_paths_only", "legacy_backfill", "automatic_retry",
    "automatic_repair", "model_call", "provider_call", "command_execution", "tool_replay", "permission_change",
    "context_injection_change",
}
WRITES_ON_CONFIRM = [
    "native_history_exact_save_and_readback",
    "installation_identity_create_once_if_missing",
    "durable_intent_prepare_once",
    "session_spine_compare_and_swap_once",
    "durable_intent_commit_marker_once",
]
PREVIEW_FIELDS = {
    "schema", "format_version", "status", "state", "read_only", "source", "gate", "identity", "stores",
    "intent_id", "recovery_state", "writes_on_confirm", "boundaries", "candidate_hash", "confirmation_token",
    "preview_hash",
}
PREVIEW_REQUEST_FIELDS = BASE_FIELDS | {"gate"}
APPLY_REQUEST_FIELDS = PREVIEW_REQUEST_FIELDS | {
    "preview", "confirmation_token", "owner_identity", "history_sha256", "history_bytes",
    "history_write_performed", "identity_created",
}


class NativeSessionSpineWriterError(RuntimeError):
    """The exact pilot is stale, unsafe, already closed, or not authorized."""


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(
            value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError):
        raise NativeSessionSpineWriterError("Session Spine writer evidence is not canonical JSON.") from None


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _digest(value: object, label: str) -> str:
    if not isinstance(value, str) or not HASH.fullmatch(value):
        raise NativeSessionSpineWriterError(f"{label} must be a lowercase SHA-256 digest.")
    return value


def _object(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise NativeSessionSpineWriterError(f"{label} must be an object.")
    return dict(value)


def _gate(value: object) -> dict[str, Any]:
    gate = _object(value, "Session Spine writer gate")
    if set(gate) != GATE_FIELDS or gate.get("acceptance_state") not in {"ACCEPTED", "RECOVERY_REQUIRED"}:
        raise NativeSessionSpineWriterError("Session Spine writer gate is incomplete or unsupported.")
    for field in GATE_FIELDS - {"acceptance_state"}:
        _digest(gate.get(field), f"Writer gate {field}")
    return gate


def _state_root(path: Path) -> Path:
    root = Path(path)
    if not root.is_absolute() or root.resolve(strict=True) != root:
        raise NativeSessionSpineWriterError("Native private state root must be one existing canonical path.")
    info = root.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_mode & 0o077:
        raise NativeSessionSpineWriterError("Native private state root must be a private non-symlinked directory.")
    return root


@contextmanager
def _root_descriptor(root: Path) -> Iterator[int]:
    descriptor = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        opened = os.fstat(descriptor)
        current = root.stat(follow_symlinks=False)
        if (opened.st_dev, opened.st_ino) != (current.st_dev, current.st_ino):
            raise NativeSessionSpineWriterError("Native private state root changed during inspection.")
        yield descriptor
    finally:
        os.close(descriptor)


def _read_at(root: Path, name: str, *, limit: int, required: bool) -> bytes | None:
    with _root_descriptor(root) as directory:
        try:
            descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        except FileNotFoundError:
            if required:
                raise NativeSessionSpineWriterError(f"Required Native private file is missing: {name}.") from None
            return None
        try:
            before = os.fstat(descriptor)
            if not stat.S_ISREG(before.st_mode) or before.st_size <= 0 or before.st_size >= limit:
                raise NativeSessionSpineWriterError(f"Native private file is unsafe or unbounded: {name}.")
            raw = os.pread(descriptor, limit, 0)
            after = os.fstat(descriptor)
            current = os.stat(name, dir_fd=directory, follow_symlinks=False)
            identity = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
            if len(raw) != before.st_size or identity != (
                after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns
            ) or identity != (current.st_dev, current.st_ino, current.st_size, current.st_mtime_ns):
                raise NativeSessionSpineWriterError(f"Native private file changed during inspection: {name}.")
            return raw
        finally:
            os.close(descriptor)


def _directory_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"state": "missing", "entry_count": 0}
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_mode & 0o077:
        raise NativeSessionSpineWriterError(f"Private writer path is unsafe: {path}.")
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        names = os.listdir(descriptor)
        if len(names) > 513:
            raise NativeSessionSpineWriterError(f"Private writer path is unbounded: {path}.")
        return {"state": "empty" if not names else "evidence", "entry_count": len(names)}
    finally:
        os.close(descriptor)


def _identity(root: Path) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    directory = root / "session_spine_identity"
    if directory.exists():
        state = _directory_state(directory)
        names = set(os.listdir(directory))
        if names - {"installation.json"}:
            raise NativeSessionSpineWriterError("Installation identity directory contains unknown evidence.")
    else:
        state = {"state": "missing", "entry_count": 0}
    raw = _read_at(directory, "installation.json", limit=16_384, required=False) if directory.exists() else None
    if raw is None:
        return None, {"state": "missing", "path": str(directory / "installation.json"), "identity_hash": None}
    try:
        value = json.loads(raw.decode("utf-8"))
        identity = validate_native_owner_identity(value)
    except (UnicodeDecodeError, ValueError, TypeError, SessionSpineHandshakeError) as error:
        raise NativeSessionSpineWriterError(f"Installation identity did not verify: {error}") from None
    if _canonical(identity) != raw:
        raise NativeSessionSpineWriterError("Installation identity is not canonical JSON.")
    return identity, {
        "state": "verified", "path": str(directory / "installation.json"),
        "identity_hash": identity["identity_hash"], "owner_id": identity["owner_id"],
        "directory_state": state["state"],
    }


def _sources(work_sessions: WorkSessionStore, state_root: Path, params: Mapping[str, Any]) -> dict[str, Any]:
    base = {field: params.get(field) for field in BASE_FIELDS}
    try:
        live = build_live_session_spine_preview(work_sessions, base)
        run_copy = work_sessions.inspect_copy(base["run"], base["conversation_id"])
        history_raw = _read_at(state_root, "conversations.json", limit=MAX_HISTORY_BYTES, required=True)
        if history_raw is None:
            raise NativeSessionSpineWriterError("Native history disappeared during exact inspection.")
        history = inspect_native_history_turn_copy(
            history_raw,
            conversation_id=live["source"]["conversation_id"],
            user_message_id=live["source"]["user_message_id"],
            assistant_message_id=live["source"]["assistant_message_id"],
        )
    except NativeSessionSpineWriterError:
        raise
    except (NativeSessionSpineLiveError, WorkSessionError, SessionSpineHandshakeError) as error:
        raise NativeSessionSpineWriterError(f"Exact Native writer source did not verify: {error}") from None
    expected = {
        "run_id": live["source"]["run_id"],
        "reference_hash": live["source"]["reference_hash"],
        "input_sha256": live["projection"]["input"]["sha256"],
        "displayed_answer_sha256": live["projection"]["answer"]["displayed_sha256"],
        "raw_answer_sha256": live["projection"]["answer"]["raw_sha256"],
    }
    if any(history[name] != value for name, value in expected.items()):
        raise NativeSessionSpineWriterError("Saved history no longer matches the exact Live Session Spine source.")
    return {"base": base, "live": live, "history": history, "history_raw": history_raw, "run": run_copy}


def _source_projection(evidence: Mapping[str, Any]) -> dict[str, Any]:
    live, history, run = evidence["live"], evidence["history"], evidence["run"]
    return {
        "conversation_id": live["source"]["conversation_id"],
        "user_message_id": live["source"]["user_message_id"],
        "assistant_message_id": live["source"]["assistant_message_id"],
        "run_id": live["source"]["run_id"],
        "run_fingerprint": live["source"]["run_fingerprint"],
        "turn_receipt_hash": live["source"]["turn_receipt_hash"],
        "reference_hash": live["source"]["reference_hash"],
        "live_preview_hash": live["preview_hash"],
        "history_sha256": history["file_sha256"],
        "history_bytes": history["file_bytes"],
        "history_turn_sha256": history["turn_sha256"],
        "work_session_sha256": run["sha256"],
        "work_session_bytes": run["bytes"],
    }


def _preview_material(
    work_sessions: WorkSessionStore,
    state_root: Path,
    params: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    if not isinstance(params, Mapping) or set(params) != PREVIEW_REQUEST_FIELDS:
        raise NativeSessionSpineWriterError("Session Spine writer preview request is not closed.")
    gate = _gate(params.get("gate"))
    evidence = _sources(work_sessions, state_root, params)
    source = _source_projection(evidence)
    identity, identity_projection = _identity(state_root)
    spine_store = SessionSpineStore(state_root / "session_spine_store")
    intent_store = SessionSpineIntentStore(state_root / "session_spine_intents")
    stores = {
        "spine": {"path": str(spine_store.directory), **_directory_state(spine_store.directory)},
        "intent": {"path": str(intent_store.directory), **_directory_state(intent_store.directory)},
    }
    state, status, recovery, planned_intent = "READY", "OK", None, None
    if identity is None:
        if stores["spine"]["state"] == "evidence" or stores["intent"]["state"] == "evidence":
            state, status = "BLOCKED", "ERROR"
        identity_projection["transition_on_confirm"] = "create_once_then_exact_readback"
    else:
        snapshot, count = intent_store.find_by_source(
            owner_id=identity["owner_id"], conversation_id=source["conversation_id"], run_id=source["run_id"]
        )
        if snapshot is None and count:
            state, status = "BLOCKED", "ERROR"
        elif snapshot is not None:
            recovery = inspect_native_turn_intent(
                intent_store, spine_store, snapshot.intent_id,
                owner_identity=identity,
                history_raw=evidence["history_raw"],
                work_session_raw=evidence["run"]["raw"],
                work_session_name=evidence["run"]["name"],
            )
            if recovery["state"] in {"READY_TO_APPLY", "COMMIT_MARKER_RECOVERY_REQUIRED"}:
                state, status = "RECOVERY_READY", "WARN"
            elif recovery["state"] == "CLOSED":
                state, status = "CLOSED", recovery["status"]
            else:
                state, status = "BLOCKED", "ERROR"
            planned_intent = snapshot.intent_id
        else:
            handshake = prepare_native_turn_handshake(
                spine_store,
                owner_identity=identity,
                history_raw=evidence["history_raw"],
                work_session_raw=evidence["run"]["raw"],
                work_session_name=evidence["run"]["name"],
                conversation_id=source["conversation_id"],
                user_message_id=source["user_message_id"],
                assistant_message_id=source["assistant_message_id"],
            )
            planned_intent = build_prepared_intent(
                handshake, intent_store_scope_sha256=intent_store.scope_sha256
            )["intent_id"]
    if state == "READY" and gate["acceptance_state"] != "ACCEPTED":
        state, status = "BLOCKED", "ERROR"
    if state in {"RECOVERY_READY", "CLOSED"} and gate["acceptance_state"] not in {"ACCEPTED", "RECOVERY_REQUIRED"}:
        state, status = "BLOCKED", "ERROR"
    material = {
        "schema": PREVIEW_SCHEMA,
        "format_version": FORMAT_VERSION,
        "status": status,
        "state": state,
        "read_only": True,
        "source": source,
        "gate": gate,
        "identity": identity_projection,
        "stores": stores,
        "intent_id": planned_intent,
        "recovery_state": None if recovery is None else recovery["state"],
        "writes_on_confirm": WRITES_ON_CONFIRM,
        "boundaries": {
            "single_exact_latest_turn": True,
            "fixed_private_paths_only": True,
            "legacy_backfill": False,
            "automatic_retry": False,
            "automatic_repair": False,
            "model_call": False,
            "provider_call": False,
            "command_execution": False,
            "tool_replay": False,
            "permission_change": False,
            "context_injection_change": False,
        },
    }
    candidate_hash = _sha256(_canonical(material))
    token = "CONFIRM-SESSION-SPINE-" + candidate_hash[:16].upper() if state in {"READY", "RECOVERY_READY"} else ""
    preview = {**material, "candidate_hash": candidate_hash, "confirmation_token": token}
    preview["preview_hash"] = _sha256(_canonical(preview))
    return preview, evidence


def preview_native_session_spine_writer(
    work_sessions: WorkSessionStore,
    state_dir: Path,
    params: Mapping[str, Any],
) -> dict[str, Any]:
    root = _state_root(state_dir)
    preview, _ = _preview_material(work_sessions, root, params)
    return preview


def _validate_preview(value: object, root: Path) -> dict[str, Any]:
    preview = _object(value, "Session Spine writer preview")
    if set(preview) != PREVIEW_FIELDS:
        raise NativeSessionSpineWriterError("Session Spine writer preview fields are not closed.")
    digest = preview.pop("preview_hash", None)
    if (
        digest != _sha256(_canonical(preview))
        or preview.get("schema") != PREVIEW_SCHEMA
        or preview.get("format_version") != FORMAT_VERSION
        or preview.get("read_only") is not True
        or preview.get("state") not in {"READY", "RECOVERY_READY", "CLOSED", "BLOCKED"}
        or preview.get("writes_on_confirm") != WRITES_ON_CONFIRM
    ):
        raise NativeSessionSpineWriterError("Session Spine writer preview hash or schema does not verify.")
    state = preview["state"]
    expected_statuses = {
        "READY": {"OK"}, "RECOVERY_READY": {"WARN"}, "CLOSED": {"OK", "WARN"}, "BLOCKED": {"ERROR"},
    }
    if preview.get("status") not in expected_statuses[state]:
        raise NativeSessionSpineWriterError("Session Spine writer preview state and status disagree.")
    source = _object(preview.get("source"), "Session Spine writer source")
    if set(source) != SOURCE_FIELDS:
        raise NativeSessionSpineWriterError("Session Spine writer source fields are not closed.")
    for field in SOURCE_FIELDS - {"conversation_id", "user_message_id", "assistant_message_id", "run_id", "history_bytes", "work_session_bytes"}:
        _digest(source.get(field), f"Writer source {field}")
    if type(source.get("history_bytes")) is not int or source["history_bytes"] <= 0:
        raise NativeSessionSpineWriterError("Writer history byte count is invalid.")
    if type(source.get("work_session_bytes")) is not int or source["work_session_bytes"] <= 0:
        raise NativeSessionSpineWriterError("Writer Work Session byte count is invalid.")
    _gate(preview.get("gate"))
    stores = _object(preview.get("stores"), "Session Spine writer stores")
    if set(stores) != {"spine", "intent"}:
        raise NativeSessionSpineWriterError("Session Spine writer store set is not closed.")
    expected_paths = {
        "spine": str(root / "session_spine_store"),
        "intent": str(root / "session_spine_intents"),
    }
    for name, expected_path in expected_paths.items():
        store = _object(stores.get(name), f"Session Spine writer {name} store")
        if (
            set(store) != {"path", "state", "entry_count"}
            or store.get("path") != expected_path
            or store.get("state") not in {"missing", "empty", "evidence"}
            or type(store.get("entry_count")) is not int
            or store["entry_count"] < 0
        ):
            raise NativeSessionSpineWriterError(f"Session Spine writer {name} store evidence is invalid.")
    identity = _object(preview.get("identity"), "Session Spine writer identity")
    expected_identity_path = str(root / "session_spine_identity" / "installation.json")
    if identity.get("path") != expected_identity_path or identity.get("state") not in {"missing", "verified"}:
        raise NativeSessionSpineWriterError("Session Spine writer identity evidence is invalid.")
    if identity["state"] == "missing":
        if set(identity) != {"state", "path", "identity_hash", "transition_on_confirm"} or identity.get("identity_hash") is not None:
            raise NativeSessionSpineWriterError("Missing Session Spine identity transition is not closed.")
        if identity.get("transition_on_confirm") != "create_once_then_exact_readback":
            raise NativeSessionSpineWriterError("Missing Session Spine identity transition is unsupported.")
    else:
        if set(identity) != {"state", "path", "identity_hash", "owner_id", "directory_state"}:
            raise NativeSessionSpineWriterError("Verified Session Spine identity evidence is not closed.")
        _digest(identity.get("identity_hash"), "Writer identity")
        if not isinstance(identity.get("owner_id"), str) or not identity["owner_id"].startswith("native-session-spine:"):
            raise NativeSessionSpineWriterError("Verified Session Spine owner is invalid.")
        if identity.get("directory_state") not in {"empty", "evidence"}:
            raise NativeSessionSpineWriterError("Verified Session Spine identity directory state is invalid.")
    boundaries = _object(preview.get("boundaries"), "Session Spine writer boundaries")
    if set(boundaries) != BOUNDARY_FIELDS:
        raise NativeSessionSpineWriterError("Session Spine writer boundaries are not closed.")
    if any(boundaries[field] is not True for field in {"single_exact_latest_turn", "fixed_private_paths_only"}):
        raise NativeSessionSpineWriterError("Session Spine writer required boundaries are disabled.")
    if any(boundaries[field] is not False for field in BOUNDARY_FIELDS - {"single_exact_latest_turn", "fixed_private_paths_only"}):
        raise NativeSessionSpineWriterError("Session Spine writer boundary was widened.")
    candidate = _digest(preview.get("candidate_hash"), "Writer candidate")
    candidate_material = {
        key: item for key, item in preview.items()
        if key not in {"candidate_hash", "confirmation_token"}
    }
    if candidate != _sha256(_canonical(candidate_material)):
        raise NativeSessionSpineWriterError("Session Spine writer candidate hash does not verify.")
    intent_id = preview.get("intent_id")
    if intent_id is not None and (not isinstance(intent_id, str) or not INTENT_ID.fullmatch(intent_id)):
        raise NativeSessionSpineWriterError("Session Spine writer intent id is invalid.")
    token = preview.get("confirmation_token")
    if preview.get("state") in {"READY", "RECOVERY_READY"}:
        if not isinstance(token, str) or not TOKEN.fullmatch(token) or token != "CONFIRM-SESSION-SPINE-" + preview["candidate_hash"][:16].upper():
            raise NativeSessionSpineWriterError("Session Spine writer confirmation token does not verify.")
    elif token != "":
        raise NativeSessionSpineWriterError("Blocked or closed Session Spine evidence cannot carry a confirmation token.")
    return {**preview, "preview_hash": digest}


def apply_native_session_spine_writer(
    work_sessions: WorkSessionStore,
    state_dir: Path,
    params: Mapping[str, Any],
) -> dict[str, Any]:
    if not isinstance(params, Mapping) or set(params) != APPLY_REQUEST_FIELDS:
        raise NativeSessionSpineWriterError("Session Spine writer apply request is not closed.")
    root = _state_root(state_dir)
    preview = _validate_preview(params.get("preview"), root)
    token = params.get("confirmation_token")
    if preview["state"] not in {"READY", "RECOVERY_READY"} or token != preview["confirmation_token"]:
        raise NativeSessionSpineWriterError("Exact Session Spine writer confirmation failed; no writer was called.")
    if _gate(params.get("gate")) != preview["gate"]:
        raise NativeSessionSpineWriterError("Session Spine writer gate changed after preview.")
    evidence = _sources(work_sessions, root, params)
    source = _source_projection(evidence)
    if source != preview["source"]:
        raise NativeSessionSpineWriterError("Session Spine writer sources changed after preview.")
    if params.get("history_sha256") != source["history_sha256"] or params.get("history_bytes") != source["history_bytes"]:
        raise NativeSessionSpineWriterError("Native history save/readback proof does not match current bytes.")
    if params.get("history_write_performed") is not True or type(params.get("identity_created")) is not bool:
        raise NativeSessionSpineWriterError("Native pre-write receipt is incomplete.")
    try:
        owner = validate_native_owner_identity(params.get("owner_identity"))
    except SessionSpineHandshakeError as error:
        raise NativeSessionSpineWriterError(f"Native owner identity did not verify: {error}") from None
    persisted_owner, _ = _identity(root)
    if persisted_owner != owner:
        raise NativeSessionSpineWriterError("Persisted installation identity does not match the confirmed writer request.")
    expected_identity = preview["identity"]
    if expected_identity["state"] == "verified" and expected_identity.get("identity_hash") != owner["identity_hash"]:
        raise NativeSessionSpineWriterError("Installation identity changed after writer preview.")
    if expected_identity["state"] not in {"missing", "verified"}:
        raise NativeSessionSpineWriterError("Session Spine writer preview has an unsupported identity transition.")
    identity_created = params["identity_created"]
    if (expected_identity["state"] == "missing") != identity_created:
        raise NativeSessionSpineWriterError("Installation identity transition does not match the confirmed preview.")

    spine_store = SessionSpineStore(root / "session_spine_store")
    intent_store = SessionSpineIntentStore(root / "session_spine_intents")
    snapshot, count = intent_store.find_by_source(
        owner_id=owner["owner_id"], conversation_id=source["conversation_id"], run_id=source["run_id"]
    )
    prepare_receipt = None
    if snapshot is None:
        if count:
            raise NativeSessionSpineWriterError("Durable intent store contains unrelated evidence; no write attempted.")
        if preview["state"] != "READY":
            raise NativeSessionSpineWriterError("Expected recovery intent is missing; no write attempted.")
        handshake = prepare_native_turn_handshake(
            spine_store,
            owner_identity=owner,
            history_raw=evidence["history_raw"],
            work_session_raw=evidence["run"]["raw"],
            work_session_name=evidence["run"]["name"],
            conversation_id=source["conversation_id"],
            user_message_id=source["user_message_id"],
            assistant_message_id=source["assistant_message_id"],
        )
        prepare_receipt = intent_store.prepare(handshake)
        snapshot = intent_store.inspect(prepare_receipt["intent_id"])
    elif preview["state"] == "READY" and preview.get("intent_id") not in {None, snapshot.intent_id}:
        raise NativeSessionSpineWriterError("Prepared intent changed after writer preview.")

    apply_receipt = apply_native_turn_intent(
        intent_store, spine_store, snapshot.intent_id,
        owner_identity=owner,
        history_raw=evidence["history_raw"],
        work_session_raw=evidence["run"]["raw"],
        work_session_name=evidence["run"]["name"],
    )
    after = inspect_native_turn_intent(
        intent_store, spine_store, snapshot.intent_id,
        owner_identity=owner,
        history_raw=evidence["history_raw"],
        work_session_raw=evidence["run"]["raw"],
        work_session_name=evidence["run"]["name"],
    )
    if after["state"] != "CLOSED":
        raise NativeSessionSpineWriterError("Session Spine writer did not reach one verified closed state.")
    receipt = {
        "schema": RECEIPT_SCHEMA,
        "format_version": FORMAT_VERSION,
        "result": apply_receipt["result"],
        "candidate_hash": preview["candidate_hash"],
        "preview_hash": preview["preview_hash"],
        "conversation_id": source["conversation_id"],
        "run_id": source["run_id"],
        "intent_id": snapshot.intent_id,
        "owner_id": owner["owner_id"],
        "identity_hash": owner["identity_hash"],
        "history_sha256": source["history_sha256"],
        "work_session_sha256": source["work_session_sha256"],
        "history_saved_and_read_back": True,
        "history_write_performed": True,
        "identity_created": identity_created and apply_receipt["result"] != "ALREADY_CLOSED",
        "intent_prepare_write_performed": prepare_receipt is not None and prepare_receipt["write_performed"],
        "spine_write_performed": apply_receipt["spine_write_performed"],
        "intent_commit_write_performed": apply_receipt["intent_write_performed"],
        "target_execution_performed": False,
        "closed": True,
        "run_once": True,
        "automatic_retry": False,
        "automatic_repair": False,
        "legacy_backfill": False,
        "model_call_performed": False,
        "provider_call_performed": False,
        "command_executed": False,
        "tool_replayed": False,
        "permission_changed": False,
        "context_injection_changed": False,
        "intent_apply_receipt_hash": apply_receipt["receipt_hash"],
        "post_inspection_hash": after["report_hash"],
    }
    receipt["receipt_hash"] = _sha256(_canonical(receipt))
    return receipt
