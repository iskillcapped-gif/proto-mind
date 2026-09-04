"""Durable detached intent lifecycle for Native Session Spine commits.

P2i stores only the content-free P2h handshake and its verified apply receipt.
The store has no default path and no production caller. Prepared and committed
records are immutable create-once files so a relaunch can distinguish a pending
Spine CAS from a lost apply response without rewriting source history.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
from typing import Any, Iterator, Mapping
from uuid import uuid4

from proto_mind.session_spine_handshake import (
    SessionSpineHandshakeError,
    apply_native_turn_handshake,
    inspect_native_turn_handshake,
    validate_native_turn_apply_receipt,
    validate_native_turn_handshake,
)
from proto_mind.session_spine_store import (
    SessionSpineStore,
    SessionSpineStoreError,
    SessionSpineStoreMissing,
)


PREPARED_SCHEMA = "proto_mind.session_spine_intent_prepared.v1"
COMMITTED_SCHEMA = "proto_mind.session_spine_intent_committed.v1"
PROJECTION_SCHEMA = "proto_mind.session_spine_intent_projection.v1"
WRITE_RECEIPT_SCHEMA = "proto_mind.session_spine_intent_write_receipt.v1"
RECOVERY_SCHEMA = "proto_mind.session_spine_intent_recovery.v1"
APPLY_RECEIPT_SCHEMA = "proto_mind.session_spine_intent_apply_receipt.v1"
FORMAT_VERSION = 1
MAX_INTENTS = 256
MAX_RECORD_BYTES = 256 * 1024
MAX_LOCK_BYTES = 512
CATALOG_LOCK = ".intent-store.lock"
HASH = re.compile(r"^[0-9a-f]{64}$")
INTENT_ID = re.compile(r"^[0-9a-f]{32}$")
RECORD_NAME = re.compile(r"^([0-9a-f]{32})\.(prepared|committed)\.json$")


class SessionSpineIntentError(RuntimeError):
    """Durable intent evidence is missing, unsafe, stale, or conflicting."""


class SessionSpineIntentMissing(SessionSpineIntentError):
    """The requested explicit intent record does not exist."""


class SessionSpineIntentBusy(SessionSpineIntentError):
    """Another cooperative intent writer currently owns the store."""


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
        raise SessionSpineIntentError("Session Spine intent is not lossless JSON.") from None


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _digest(value: object, label: str) -> str:
    if not isinstance(value, str) or not HASH.fullmatch(value):
        raise SessionSpineIntentError(f"{label} must be a lowercase SHA-256 digest.")
    return value


def _intent_id(value: object) -> str:
    if not isinstance(value, str) or not INTENT_ID.fullmatch(value):
        raise SessionSpineIntentError("Session Spine intent ID is invalid.")
    return value


def _pairs(values: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in values:
        if key in result:
            raise SessionSpineIntentError("Session Spine intent contains a duplicate JSON field.")
        result[key] = value
    return result


def _constant(_: str) -> None:
    raise SessionSpineIntentError("Session Spine intent contains non-finite JSON.")


def _decode(raw: bytes, label: str) -> dict[str, Any]:
    if not raw or len(raw) > MAX_RECORD_BYTES:
        raise SessionSpineIntentError(f"{label} is empty or exceeds its bounded size.")
    try:
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_pairs,
            parse_constant=_constant,
        )
    except SessionSpineIntentError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError, RecursionError):
        raise SessionSpineIntentError(f"{label} is not valid UTF-8 JSON.") from None
    if not isinstance(value, dict) or _canonical(value) != raw:
        raise SessionSpineIntentError(f"{label} is not one canonical JSON object.")
    return value


def _scope_sha256(directory: Path) -> str:
    return _sha256(str(directory).encode("utf-8"))


def _intent_material(handshake: Mapping[str, Any], intent_store_scope_sha256: str) -> dict[str, str]:
    return {
        "handshake_hash": handshake["handshake_hash"],
        "owner_id": handshake["owner_identity"]["owner_id"],
        "conversation_id": handshake["source"]["conversation_id"],
        "run_id": handshake["source"]["run_id"],
        "spine_store_scope_sha256": handshake["spine"]["store_scope_sha256"],
        "intent_store_scope_sha256": intent_store_scope_sha256,
    }


def _derived_intent_id(handshake: Mapping[str, Any], scope: str) -> str:
    return _sha256(_canonical(_intent_material(handshake, scope)))[:32]


def build_prepared_intent(
    handshake: Mapping[str, Any],
    *,
    intent_store_scope_sha256: str,
) -> dict[str, Any]:
    contract = validate_native_turn_handshake(handshake)
    scope = _digest(intent_store_scope_sha256, "Intent store scope")
    record: dict[str, Any] = {
        "schema": PREPARED_SCHEMA,
        "format_version": FORMAT_VERSION,
        "state": "prepared",
        "intent_id": _derived_intent_id(contract, scope),
        "identity": _intent_material(contract, scope),
        "handshake": contract,
        "boundaries": {
            "content_free": True,
            "prompt_text_stored": False,
            "answer_text_stored": False,
            "history_bytes_stored": False,
            "work_session_bytes_stored": False,
            "source_store_write_performed": False,
            "automatic_retry": False,
            "automatic_repair": False,
            "legacy_backfill": False,
            "native_activation": False,
            "model_call_performed": False,
            "provider_call_performed": False,
            "command_executed": False,
            "permission_changed": False,
        },
    }
    record["record_hash"] = _sha256(_canonical(record))
    return record


def validate_prepared_intent(value: object) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise SessionSpineIntentError("Prepared Session Spine intent is invalid.")
    record = dict(value)
    digest = record.pop("record_hash", None)
    if (
        set(record) != {"schema", "format_version", "state", "intent_id", "identity", "handshake", "boundaries"}
        or digest != _sha256(_canonical(record))
        or record.get("schema") != PREPARED_SCHEMA
        or record.get("format_version") != FORMAT_VERSION
        or record.get("state") != "prepared"
    ):
        raise SessionSpineIntentError("Prepared Session Spine intent hash or schema does not verify.")
    contract = validate_native_turn_handshake(record["handshake"])
    identity = record.get("identity")
    if not isinstance(identity, dict) or set(identity) != {
        "handshake_hash", "owner_id", "conversation_id", "run_id",
        "spine_store_scope_sha256", "intent_store_scope_sha256",
    }:
        raise SessionSpineIntentError("Prepared Session Spine intent identity is invalid.")
    for field in ("handshake_hash", "spine_store_scope_sha256", "intent_store_scope_sha256"):
        _digest(identity.get(field), f"Intent identity {field}")
    if identity != _intent_material(contract, identity["intent_store_scope_sha256"]):
        raise SessionSpineIntentError("Prepared Session Spine intent conflicts with its handshake identity.")
    identifier = _intent_id(record.get("intent_id"))
    if identifier != _derived_intent_id(contract, identity["intent_store_scope_sha256"]):
        raise SessionSpineIntentError("Prepared Session Spine intent ID does not verify.")
    if record.get("boundaries") != {
        "content_free": True,
        "prompt_text_stored": False,
        "answer_text_stored": False,
        "history_bytes_stored": False,
        "work_session_bytes_stored": False,
        "source_store_write_performed": False,
        "automatic_retry": False,
        "automatic_repair": False,
        "legacy_backfill": False,
        "native_activation": False,
        "model_call_performed": False,
        "provider_call_performed": False,
        "command_executed": False,
        "permission_changed": False,
    }:
        raise SessionSpineIntentError("Prepared Session Spine intent widens its safety boundary.")
    return {**record, "record_hash": digest}


def build_committed_intent(
    prepared: Mapping[str, Any],
    apply_receipt: Mapping[str, Any],
) -> dict[str, Any]:
    intent = validate_prepared_intent(prepared)
    try:
        receipt = validate_native_turn_apply_receipt(apply_receipt)
    except SessionSpineHandshakeError as error:
        raise SessionSpineIntentError(f"Session Spine apply receipt did not verify: {error}") from None
    identity = intent["identity"]
    if (
        receipt["handshake_hash"] != identity["handshake_hash"]
        or receipt["owner_id"] != identity["owner_id"]
        or receipt["conversation_id"] != identity["conversation_id"]
        or receipt["run_id"] != identity["run_id"]
    ):
        raise SessionSpineIntentError("Session Spine apply receipt belongs to another durable intent.")
    record: dict[str, Any] = {
        "schema": COMMITTED_SCHEMA,
        "format_version": FORMAT_VERSION,
        "state": "committed",
        "intent_id": intent["intent_id"],
        "prepared_record_hash": intent["record_hash"],
        "handshake_hash": identity["handshake_hash"],
        "apply_receipt": receipt,
        "boundaries": {
            "immutable_commit_marker": True,
            "source_history_modified": False,
            "work_session_modified": False,
            "automatic_retry": False,
            "automatic_repair": False,
            "legacy_backfill": False,
            "native_activation": False,
        },
    }
    record["record_hash"] = _sha256(_canonical(record))
    return record


def validate_committed_intent(
    value: object,
    *,
    prepared: Mapping[str, Any],
) -> dict[str, Any]:
    intent = validate_prepared_intent(prepared)
    if not isinstance(value, Mapping):
        raise SessionSpineIntentError("Committed Session Spine intent is invalid.")
    record = dict(value)
    digest = record.pop("record_hash", None)
    if (
        set(record) != {
            "schema", "format_version", "state", "intent_id", "prepared_record_hash",
            "handshake_hash", "apply_receipt", "boundaries",
        }
        or digest != _sha256(_canonical(record))
        or record.get("schema") != COMMITTED_SCHEMA
        or record.get("format_version") != FORMAT_VERSION
        or record.get("state") != "committed"
        or record.get("intent_id") != intent["intent_id"]
        or record.get("prepared_record_hash") != intent["record_hash"]
        or record.get("handshake_hash") != intent["identity"]["handshake_hash"]
        or record.get("boundaries") != {
            "immutable_commit_marker": True,
            "source_history_modified": False,
            "work_session_modified": False,
            "automatic_retry": False,
            "automatic_repair": False,
            "legacy_backfill": False,
            "native_activation": False,
        }
    ):
        raise SessionSpineIntentError("Committed Session Spine intent hash or schema does not verify.")
    expected = build_committed_intent(intent, record["apply_receipt"])
    if {**record, "record_hash": digest} != expected:
        raise SessionSpineIntentError("Committed Session Spine intent does not reproduce its receipt.")
    return expected


@dataclass(frozen=True)
class SessionSpineIntentSnapshot:
    intent_id: str
    state: str
    prepared: dict[str, Any]
    committed: dict[str, Any] | None
    store_scope_sha256: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": PROJECTION_SCHEMA,
            "format_version": FORMAT_VERSION,
            "read_only": True,
            "intent_id": self.intent_id,
            "state": self.state,
            "store_scope_sha256": self.store_scope_sha256,
            "owner_id": self.prepared["identity"]["owner_id"],
            "conversation_id": self.prepared["identity"]["conversation_id"],
            "run_id": self.prepared["identity"]["run_id"],
            "handshake_hash": self.prepared["identity"]["handshake_hash"],
            "prepared_record_hash": self.prepared["record_hash"],
            "committed_record_hash": None if self.committed is None else self.committed["record_hash"],
            "content_free": True,
            "automatic_retry": False,
            "automatic_repair": False,
            "native_activation": False,
        }


class SessionSpineIntentStore:
    """Explicit private create-once store; reading never creates state."""

    def __init__(self, directory: Path) -> None:
        self.directory = Path(directory)
        if not self.directory.is_absolute():
            raise SessionSpineIntentError("Session Spine intent store requires an explicit absolute directory.")

    @property
    def scope_sha256(self) -> str:
        return _scope_sha256(self.directory)

    @contextmanager
    def _directory(self, *, create: bool = False) -> Iterator[int | None]:
        descriptor: int | None = None
        parent: int | None = None
        try:
            flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
            parent = os.open("/", flags)
            for index, part in enumerate(self.directory.parts[1:]):
                if not part or part in {".", ".."}:
                    raise SessionSpineIntentError("Session Spine intent path is not canonical.")
                final = index == len(self.directory.parts[1:]) - 1
                try:
                    child = os.open(part, flags, dir_fd=parent)
                except FileNotFoundError:
                    if not create or not final:
                        os.close(parent)
                        parent = None
                        yield None
                        return
                    os.mkdir(part, mode=0o700, dir_fd=parent)
                    os.fsync(parent)
                    child = os.open(part, flags, dir_fd=parent)
                os.close(parent)
                parent = child
            descriptor, parent = parent, None
            info = os.fstat(descriptor)
            if not stat.S_ISDIR(info.st_mode) or info.st_mode & 0o077:
                raise SessionSpineIntentError("Session Spine intent directory must be private and non-symlinked.")
            yield descriptor
        except SessionSpineIntentError:
            raise
        except OSError as error:
            raise SessionSpineIntentError(f"Session Spine intent directory is unsafe: {error.strerror}.") from None
        finally:
            if descriptor is not None:
                os.close(descriptor)
            if parent is not None:
                os.close(parent)

    @contextmanager
    def _lock(self, directory: int, *, write: bool) -> Iterator[None]:
        flags = os.O_RDWR if write else os.O_RDONLY
        if write:
            flags |= os.O_CREAT
        try:
            descriptor = os.open(
                CATALOG_LOCK,
                flags | os.O_NOFOLLOW | os.O_NONBLOCK,
                0o600,
                dir_fd=directory,
            )
        except FileNotFoundError:
            raise SessionSpineIntentError("Intent records exist without their cooperative store lock.") from None
        except OSError as error:
            raise SessionSpineIntentError(f"Session Spine intent lock is unsafe: {error.strerror}.") from None
        try:
            info = os.fstat(descriptor)
            if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077 or info.st_size > MAX_LOCK_BYTES:
                raise SessionSpineIntentError("Session Spine intent lock is unsafe or unbounded.")
            try:
                fcntl.flock(
                    descriptor,
                    (fcntl.LOCK_EX if write else fcntl.LOCK_SH) | fcntl.LOCK_NB,
                )
            except BlockingIOError:
                raise SessionSpineIntentBusy("Session Spine intent store has an active writer.") from None
            yield
        finally:
            os.close(descriptor)

    @staticmethod
    def _names(intent_id: str) -> tuple[str, str]:
        identifier = _intent_id(intent_id)
        return identifier + ".prepared.json", identifier + ".committed.json"

    @staticmethod
    def _catalog(directory: int) -> tuple[set[str], set[str]]:
        prepared: set[str] = set()
        committed: set[str] = set()
        with os.scandir(directory) as entries:
            for entry in entries:
                if entry.name == CATALOG_LOCK:
                    continue
                match = RECORD_NAME.fullmatch(entry.name)
                if match is None or not entry.is_file(follow_symlinks=False):
                    raise SessionSpineIntentError(
                        f"Unexpected or unsafe file in dedicated intent store: {entry.name[:160]}."
                    )
                (prepared if match.group(2) == "prepared" else committed).add(match.group(1))
        if len(prepared) > MAX_INTENTS:
            raise SessionSpineIntentError("Session Spine intent store reached its bounded record count.")
        if committed - prepared:
            raise SessionSpineIntentError("Committed Session Spine intent exists without its prepared record.")
        return prepared, committed

    @staticmethod
    def _read(directory: int, name: str) -> bytes:
        try:
            descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        except FileNotFoundError:
            raise
        except OSError as error:
            raise SessionSpineIntentError(f"Session Spine intent file is unsafe: {error.strerror}.") from None
        try:
            before = os.fstat(descriptor)
            if not stat.S_ISREG(before.st_mode) or before.st_mode & 0o077 or before.st_size > MAX_RECORD_BYTES:
                raise SessionSpineIntentError("Session Spine intent file is unsafe or unbounded.")
            raw = os.pread(descriptor, MAX_RECORD_BYTES + 1, 0)
            after = os.fstat(descriptor)
            current = os.stat(name, dir_fd=directory, follow_symlinks=False)
            identity = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
            if (
                len(raw) > MAX_RECORD_BYTES
                or identity != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
                or identity != (current.st_dev, current.st_ino, current.st_size, current.st_mtime_ns)
            ):
                raise SessionSpineIntentError("Session Spine intent changed during inspection.")
            return raw
        finally:
            os.close(descriptor)

    @classmethod
    def _write_once(cls, directory: int, name: str, raw: bytes) -> bool:
        if len(raw) > MAX_RECORD_BYTES:
            raise SessionSpineIntentError("Session Spine intent record exceeds its bounded size.")
        try:
            current = cls._read(directory, name)
        except FileNotFoundError:
            current = None
        if current is not None:
            if current != raw:
                raise SessionSpineIntentError("Immutable Session Spine intent record conflicts with existing bytes.")
            return False
        temporary = f".intent-write-{uuid4().hex}.tmp"
        descriptor: int | None = None
        try:
            descriptor = os.open(
                temporary,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o600,
                dir_fd=directory,
            )
            view = memoryview(raw)
            while view:
                written = os.write(descriptor, view)
                if written <= 0:
                    raise OSError("zero-byte Session Spine intent write")
                view = view[written:]
            os.fsync(descriptor)
            os.close(descriptor)
            descriptor = None
            os.link(
                temporary,
                name,
                src_dir_fd=directory,
                dst_dir_fd=directory,
                follow_symlinks=False,
            )
            os.fsync(directory)
            os.unlink(temporary, dir_fd=directory)
            os.fsync(directory)
            if cls._read(directory, name) != raw:
                raise SessionSpineIntentError("Committed Session Spine intent bytes did not survive readback.")
            return True
        except FileExistsError:
            if cls._read(directory, name) != raw:
                raise SessionSpineIntentError("Concurrent Session Spine intent record conflicts with prepared bytes.") from None
            return False
        except SessionSpineIntentError:
            raise
        except OSError as error:
            raise SessionSpineIntentError(f"Session Spine intent durability is unknown: {error}.") from None
        finally:
            if descriptor is not None:
                os.close(descriptor)
            try:
                os.unlink(temporary, dir_fd=directory)
            except OSError:
                pass

    @staticmethod
    def _write_receipt(
        *,
        operation: str,
        result: str,
        write_performed: bool,
        intent_id: str,
        record_hash: str,
    ) -> dict[str, Any]:
        receipt: dict[str, Any] = {
            "schema": WRITE_RECEIPT_SCHEMA,
            "format_version": FORMAT_VERSION,
            "operation": operation,
            "result": result,
            "intent_id": intent_id,
            "record_hash": record_hash,
            "write_performed": write_performed,
            "written_scope": "explicit_session_spine_intent_store_only" if write_performed else "none",
            "source_history_modified": False,
            "work_session_modified": False,
            "model_call_performed": False,
            "provider_call_performed": False,
            "command_executed": False,
            "permission_changed": False,
            "native_activation": False,
        }
        receipt["receipt_hash"] = _sha256(_canonical(receipt))
        return receipt

    def prepare(self, handshake: Mapping[str, Any]) -> dict[str, Any]:
        record = build_prepared_intent(
            handshake,
            intent_store_scope_sha256=self.scope_sha256,
        )
        identifier = record["intent_id"]
        prepared_name, _ = self._names(identifier)
        with self._directory(create=True) as directory:
            if directory is None:
                raise SessionSpineIntentError("Explicit Session Spine intent directory could not be created.")
            with self._lock(directory, write=True):
                prepared, _ = self._catalog(directory)
                if identifier not in prepared and len(prepared) >= MAX_INTENTS:
                    raise SessionSpineIntentError("Session Spine intent store is full; no automatic cleanup.")
                written = self._write_once(directory, prepared_name, _canonical(record))
        return self._write_receipt(
            operation="prepare",
            result="PREPARED" if written else "ALREADY_PREPARED",
            write_performed=written,
            intent_id=identifier,
            record_hash=record["record_hash"],
        )

    def inspect(self, intent_id: str) -> SessionSpineIntentSnapshot:
        identifier = _intent_id(intent_id)
        prepared_name, committed_name = self._names(identifier)
        with self._directory() as directory:
            if directory is None:
                raise SessionSpineIntentMissing("Session Spine intent store does not exist; inspection created nothing.")
            try:
                lock = self._lock(directory, write=False)
                with lock:
                    prepared_ids, committed_ids = self._catalog(directory)
                    if identifier not in prepared_ids:
                        raise SessionSpineIntentMissing("Requested Session Spine intent does not exist.")
                    prepared = validate_prepared_intent(_decode(self._read(directory, prepared_name), "Prepared intent"))
                    if prepared["intent_id"] != identifier or prepared["identity"]["intent_store_scope_sha256"] != self.scope_sha256:
                        raise SessionSpineIntentError("Prepared intent filename or store scope does not verify.")
                    committed = None
                    if identifier in committed_ids:
                        committed = validate_committed_intent(
                            _decode(self._read(directory, committed_name), "Committed intent"),
                            prepared=prepared,
                        )
                    return SessionSpineIntentSnapshot(
                        intent_id=identifier,
                        state="committed" if committed is not None else "prepared",
                        prepared=prepared,
                        committed=committed,
                        store_scope_sha256=self.scope_sha256,
                    )
            except SessionSpineIntentMissing:
                raise

    def find_by_source(
        self,
        *,
        owner_id: str,
        conversation_id: str,
        run_id: str,
    ) -> tuple[SessionSpineIntentSnapshot | None, int]:
        """Find one exact source-bound intent while validating the whole bounded catalog."""
        matches: list[SessionSpineIntentSnapshot] = []
        with self._directory() as directory:
            if directory is None:
                return None, 0
            with self._lock(directory, write=False):
                prepared_ids, committed_ids = self._catalog(directory)
                for identifier in sorted(prepared_ids):
                    prepared_name, committed_name = self._names(identifier)
                    prepared = validate_prepared_intent(_decode(self._read(directory, prepared_name), "Prepared intent"))
                    if (
                        prepared["intent_id"] != identifier
                        or prepared["identity"]["intent_store_scope_sha256"] != self.scope_sha256
                    ):
                        raise SessionSpineIntentError("Prepared intent filename or store scope does not verify.")
                    committed = None
                    if identifier in committed_ids:
                        committed = validate_committed_intent(
                            _decode(self._read(directory, committed_name), "Committed intent"),
                            prepared=prepared,
                        )
                    identity = prepared["identity"]
                    if (
                        identity["owner_id"] == owner_id
                        and identity["conversation_id"] == conversation_id
                        and identity["run_id"] == run_id
                    ):
                        matches.append(SessionSpineIntentSnapshot(
                            intent_id=identifier,
                            state="committed" if committed is not None else "prepared",
                            prepared=prepared,
                            committed=committed,
                            store_scope_sha256=self.scope_sha256,
                        ))
        if len(matches) > 1:
            raise SessionSpineIntentError("Multiple durable intents claim the same exact Native turn.")
        return (matches[0] if matches else None), len(prepared_ids)

    def commit(self, intent_id: str, apply_receipt: Mapping[str, Any]) -> dict[str, Any]:
        identifier = _intent_id(intent_id)
        prepared_name, committed_name = self._names(identifier)
        with self._directory() as directory:
            if directory is None:
                raise SessionSpineIntentMissing("Session Spine intent store does not exist.")
            with self._lock(directory, write=True):
                prepared_ids, committed_ids = self._catalog(directory)
                if identifier not in prepared_ids:
                    raise SessionSpineIntentMissing("Prepared Session Spine intent does not exist.")
                prepared = validate_prepared_intent(_decode(self._read(directory, prepared_name), "Prepared intent"))
                if prepared["identity"]["intent_store_scope_sha256"] != self.scope_sha256:
                    raise SessionSpineIntentError("Prepared intent belongs to another explicit store.")
                record = build_committed_intent(prepared, apply_receipt)
                written = self._write_once(directory, committed_name, _canonical(record))
                if identifier in committed_ids and written:
                    raise SessionSpineIntentError("Committed intent catalog changed while locked.")
        return self._write_receipt(
            operation="commit",
            result="COMMITTED" if written else "ALREADY_COMMITTED",
            write_performed=written,
            intent_id=identifier,
            record_hash=record["record_hash"],
        )


def _current_spine_raw(store: SessionSpineStore, conversation_id: str) -> bytes | None:
    try:
        return store.read_image(conversation_id)[0]
    except SessionSpineStoreMissing:
        return None
    except SessionSpineStoreError as error:
        raise SessionSpineIntentError(f"Session Spine inspection failed: {error}") from None


def inspect_native_turn_intent(
    intent_store: SessionSpineIntentStore,
    spine_store: SessionSpineStore,
    intent_id: str,
    *,
    owner_identity: Mapping[str, Any],
    history_raw: bytes | None,
    work_session_raw: bytes | None,
    work_session_name: str,
) -> dict[str, Any]:
    """Read-only relaunch classification for one durable P2i intent."""
    if not isinstance(intent_store, SessionSpineIntentStore) or not isinstance(spine_store, SessionSpineStore):
        raise SessionSpineIntentError("Intent recovery requires explicit detached intent and Spine stores.")
    snapshot = intent_store.inspect(intent_id)
    handshake = snapshot.prepared["handshake"]
    if _scope_sha256(spine_store.directory) != snapshot.prepared["identity"]["spine_store_scope_sha256"]:
        raise SessionSpineIntentError("Durable intent is bound to another explicit Session Spine store.")
    try:
        handshake_report = inspect_native_turn_handshake(
            handshake,
            owner_identity=owner_identity,
            history_raw=history_raw,
            work_session_raw=work_session_raw,
            work_session_name=work_session_name,
            spine_raw=_current_spine_raw(spine_store, handshake["source"]["conversation_id"]),
        )
    except SessionSpineHandshakeError as error:
        raise SessionSpineIntentError(f"Durable intent source inspection failed: {error}") from None
    handshake_state = handshake_report["state"]
    if snapshot.committed is not None:
        if handshake_state in {"COMMITTED", "COMMITTED_WITH_SOURCE_DRIFT"}:
            state = "CLOSED"
            status = "WARN" if handshake_state.endswith("DRIFT") else "OK"
            next_action = "none"
        else:
            state, status = "COMMITTED_INTENT_EVIDENCE_CONFLICT", "ERROR"
            next_action = "inspect_sources_and_spine_no_write"
    elif handshake_state == "READY_TO_COMMIT_SPINE":
        state, status = "READY_TO_APPLY", "OK"
        next_action = "explicit_detached_apply_or_leave_prepared"
    elif handshake_state in {"COMMITTED", "COMMITTED_WITH_SOURCE_DRIFT"}:
        state = "COMMIT_MARKER_RECOVERY_REQUIRED"
        status = "WARN"
        next_action = "record_verified_apply_receipt_without_repeating_spine_write"
    else:
        state = handshake_state
        status = handshake_report["status"]
        next_action = handshake_report["next_action"]
    report: dict[str, Any] = {
        "schema": RECOVERY_SCHEMA,
        "format_version": FORMAT_VERSION,
        "status": status,
        "state": state,
        "intent": snapshot.to_dict(),
        "handshake_state": handshake_state,
        "handshake_report_hash": handshake_report["report_hash"],
        "eligible_for_detached_apply": state in {"READY_TO_APPLY", "COMMIT_MARKER_RECOVERY_REQUIRED"},
        "spine_write_needed": state == "READY_TO_APPLY",
        "commit_marker_write_needed": state in {"READY_TO_APPLY", "COMMIT_MARKER_RECOVERY_REQUIRED"},
        "next_action": next_action,
        "boundaries": {
            "read_only": True,
            "content_free": True,
            "automatic_retry": False,
            "automatic_repair": False,
            "source_store_write_performed": False,
            "spine_write_performed": False,
            "intent_write_performed": False,
            "native_activation": False,
        },
    }
    report["report_hash"] = _sha256(_canonical(report))
    return report


def _lifecycle_apply_receipt(
    snapshot: SessionSpineIntentSnapshot,
    *,
    result: str,
    spine_write_performed: bool,
    intent_write_performed: bool,
    handshake_apply_receipt_hash: str,
    intent_commit_receipt_hash: str,
) -> dict[str, Any]:
    receipt: dict[str, Any] = {
        "schema": APPLY_RECEIPT_SCHEMA,
        "format_version": FORMAT_VERSION,
        "result": result,
        "intent_id": snapshot.intent_id,
        "handshake_hash": snapshot.prepared["identity"]["handshake_hash"],
        "spine_write_performed": spine_write_performed,
        "intent_write_performed": intent_write_performed,
        "handshake_apply_receipt_hash": handshake_apply_receipt_hash,
        "intent_commit_receipt_hash": intent_commit_receipt_hash,
        "source_history_modified": False,
        "work_session_modified": False,
        "automatic_retry": False,
        "automatic_repair": False,
        "native_activation": False,
        "model_call_performed": False,
        "provider_call_performed": False,
        "command_executed": False,
        "permission_changed": False,
    }
    receipt["receipt_hash"] = _sha256(_canonical(receipt))
    return receipt


def apply_native_turn_intent(
    intent_store: SessionSpineIntentStore,
    spine_store: SessionSpineStore,
    intent_id: str,
    *,
    owner_identity: Mapping[str, Any],
    history_raw: bytes,
    work_session_raw: bytes,
    work_session_name: str,
) -> dict[str, Any]:
    """Apply one explicit detached intent once, preserving crash recovery evidence."""
    before = inspect_native_turn_intent(
        intent_store,
        spine_store,
        intent_id,
        owner_identity=owner_identity,
        history_raw=history_raw,
        work_session_raw=work_session_raw,
        work_session_name=work_session_name,
    )
    snapshot = intent_store.inspect(intent_id)
    if before["state"] == "CLOSED":
        committed = snapshot.committed
        if committed is None:
            raise SessionSpineIntentError("Closed durable intent has no immutable commit marker.")
        return _lifecycle_apply_receipt(
            snapshot,
            result="ALREADY_CLOSED",
            spine_write_performed=False,
            intent_write_performed=False,
            handshake_apply_receipt_hash=committed["apply_receipt"]["receipt_hash"],
            intent_commit_receipt_hash=committed["record_hash"],
        )
    if before["state"] not in {"READY_TO_APPLY", "COMMIT_MARKER_RECOVERY_REQUIRED"}:
        raise SessionSpineIntentError(f"Durable intent is not eligible for apply: {before['state']}.")
    try:
        apply_receipt = apply_native_turn_handshake(
            spine_store,
            snapshot.prepared["handshake"],
            owner_identity=owner_identity,
            history_raw=history_raw,
            work_session_raw=work_session_raw,
            work_session_name=work_session_name,
        )
    except SessionSpineHandshakeError as error:
        raise SessionSpineIntentError(f"Detached Session Spine apply failed: {error}") from None
    commit_receipt = intent_store.commit(intent_id, apply_receipt)
    after = intent_store.inspect(intent_id)
    if after.state != "committed" or after.committed is None:
        raise SessionSpineIntentError("Durable intent commit marker did not survive exact readback.")
    recovered = apply_receipt["result"] == "ALREADY_COMMITTED"
    return _lifecycle_apply_receipt(
        after,
        result="RECOVERED_COMMIT_MARKER" if recovered else "COMMITTED",
        spine_write_performed=apply_receipt["write_performed"],
        intent_write_performed=commit_receipt["write_performed"],
        handshake_apply_receipt_hash=apply_receipt["receipt_hash"],
        intent_commit_receipt_hash=after.committed["record_hash"],
    )
