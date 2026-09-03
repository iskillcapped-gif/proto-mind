"""Crash-aware private Session Spine store foundation.

The store has no default location and no production caller. A writer must be
given an explicit absolute directory, session ID, and owner ID. Readers never
create files, while writers commit each event as a prepare/commit pair with an
fsync boundary. Incomplete tails remain visible as UNKNOWN and are never
repaired or resumed automatically.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import fcntl
import hashlib
from itertools import islice
import json
import os
from pathlib import Path
import re
import stat
from typing import Any, Iterable, Iterator, Mapping
from uuid import UUID

from proto_mind.session_spine import SessionEvent, SurfaceSnapshot, event_from_dict, fold_surface


STORE_SCHEMA = "proto_mind.session_spine_store.v1"
HEADER_SCHEMA = "proto_mind.session_spine_store_header.v1"
PREPARE_SCHEMA = "proto_mind.session_spine_store_prepare.v1"
COMMIT_SCHEMA = "proto_mind.session_spine_store_commit.v1"
PROJECTION_SCHEMA = "proto_mind.session_spine_store_projection.v1"
RETENTION_SCHEMA = "proto_mind.session_spine_store_retention.v1"
FORMAT_VERSION = 1
MAX_EVENTS = 512
MAX_SESSIONS = 256
MAX_FILE_BYTES = 48 * 1024 * 1024
MAX_RECORD_BYTES = 96 * 1024
MAX_LOCK_BYTES = 512
CATALOG_LOCK = ".store.lock"
HASH = re.compile(r"^[0-9a-f]{64}$")
OWNER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,119}$")


class SessionSpineStoreError(RuntimeError):
    """Stored session evidence is missing, busy, unsafe, or invalid."""


class SessionSpineStoreMissing(SessionSpineStoreError):
    """The requested detached store/session has not been created."""


class SessionSpineStoreBusy(SessionSpineStoreError):
    """Another writer currently owns this session."""


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
        raise SessionSpineStoreError("Session store data is not lossless JSON.") from None


def _line(value: object) -> bytes:
    return _canonical(value) + b"\n"


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _pairs(values: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in values:
        if key in result:
            raise SessionSpineStoreError("Duplicate JSON field in committed session evidence.")
        result[key] = value
    return result


def _constant(_: str) -> None:
    raise SessionSpineStoreError("Non-finite JSON in committed session evidence.")


def _decode(raw: bytes, label: str) -> dict[str, Any]:
    if not raw or len(raw) > MAX_RECORD_BYTES:
        raise SessionSpineStoreError(f"{label} is empty or exceeds the record boundary.")
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs, parse_constant=_constant)
    except SessionSpineStoreError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError, RecursionError):
        raise SessionSpineStoreError(f"{label} is not valid canonical JSON.") from None
    if not isinstance(value, dict) or _canonical(value) != raw:
        raise SessionSpineStoreError(f"{label} is not a canonical JSON object.")
    return value


def _uuid(value: object, label: str) -> str:
    try:
        result = str(UUID(str(value)))
    except (ValueError, TypeError, AttributeError):
        raise SessionSpineStoreError(f"{label} is invalid.") from None
    if result != value:
        raise SessionSpineStoreError(f"{label} must use canonical lowercase UUID text.")
    return result


def _owner(value: object) -> str:
    if not isinstance(value, str) or not OWNER.fullmatch(value):
        raise SessionSpineStoreError("Session writer owner ID is invalid.")
    return value


def _hash(value: object, label: str) -> str:
    if not isinstance(value, str) or not HASH.fullmatch(value):
        raise SessionSpineStoreError(f"{label} is not a lowercase SHA-256 digest.")
    return value


def _integer(value: object, label: str) -> int:
    if type(value) is not int or value < 0:
        raise SessionSpineStoreError(f"{label} must be a non-negative integer.")
    return value


def _without(value: Mapping[str, Any], key: str) -> dict[str, Any]:
    return {name: item for name, item in value.items() if name != key}


@dataclass(frozen=True)
class _ParsedLog:
    header: dict[str, Any]
    events: tuple[SessionEvent, ...]
    append_owners: tuple[str, ...]
    raw: bytes
    last_commit_hash: str
    uncommitted_event_seq: int | None
    torn_tail_bytes: int


@dataclass(frozen=True)
class SessionSpineStoreSnapshot:
    session_id: str
    created_ms: int
    created_by: str
    events: tuple[SessionEvent, ...]
    append_owners: tuple[str, ...]
    surface: SurfaceSnapshot
    file_bytes: int
    file_sha256: str
    last_commit_hash: str
    recovery_state: str
    appendable: bool
    uncommitted_event_seq: int | None
    torn_tail_bytes: int
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": PROJECTION_SCHEMA,
            "store_schema": STORE_SCHEMA,
            "format_version": FORMAT_VERSION,
            "read_only": True,
            "no_repair": True,
            "automatic_resume": False,
            "session_id": self.session_id,
            "created_ms": self.created_ms,
            "created_by": self.created_by,
            "committed_event_count": len(self.events),
            "append_owners": list(self.append_owners),
            "surface_nodes": list(self.surface.nodes),
            "surface_fingerprint": self.surface.fingerprint,
            "file_bytes": self.file_bytes,
            "file_sha256": self.file_sha256,
            "last_commit_hash": self.last_commit_hash,
            "recovery_state": self.recovery_state,
            "appendable": self.appendable,
            "uncommitted_event_seq": self.uncommitted_event_seq,
            "torn_tail_bytes": self.torn_tail_bytes,
            "warnings": list(self.warnings),
            "task_success_inferred": False,
        }


@dataclass(frozen=True)
class SessionSpineAppendReceipt:
    session_id: str
    owner_id: str
    event_seq: int
    event_hash: str
    prepare_hash: str
    commit_hash: str
    previous_commit_hash: str
    file_sha256: str
    file_bytes: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "proto_mind.session_spine_store_append_receipt.v1",
            "session_id": self.session_id,
            "owner_id": self.owner_id,
            "event_seq": self.event_seq,
            "event_hash": self.event_hash,
            "prepare_hash": self.prepare_hash,
            "commit_hash": self.commit_hash,
            "previous_commit_hash": self.previous_commit_hash,
            "file_sha256": self.file_sha256,
            "file_bytes": self.file_bytes,
            "durable_commit_requested": True,
            "target_command_executed": False,
        }


def _event_records(
    *,
    session_id: str,
    owner_id: str,
    event: SessionEvent,
    previous_commit_hash: str,
) -> tuple[bytes, bytes, dict[str, Any], dict[str, Any]]:
    event_value = event.to_dict()
    event_hash = _digest(event_value)
    prepared: dict[str, Any] = {
        "schema": PREPARE_SCHEMA,
        "session_id": session_id,
        "ordinal": event.seq,
        "owner_id": owner_id,
        "previous_commit_hash": previous_commit_hash,
        "event": event_value,
        "event_hash": event_hash,
    }
    prepared["prepare_hash"] = _digest(prepared)
    committed: dict[str, Any] = {
        "schema": COMMIT_SCHEMA,
        "session_id": session_id,
        "ordinal": event.seq,
        "owner_id": owner_id,
        "previous_commit_hash": previous_commit_hash,
        "prepare_hash": prepared["prepare_hash"],
    }
    committed["commit_hash"] = _digest(committed)
    prepare_line, commit_line = _line(prepared), _line(committed)
    if len(prepare_line) > MAX_RECORD_BYTES or len(commit_line) > MAX_RECORD_BYTES:
        raise SessionSpineStoreError("Session event envelope exceeds its bounded record size.")
    return prepare_line, commit_line, prepared, committed


def _header(value: Mapping[str, Any], session_id: str) -> dict[str, Any]:
    expected = {"schema", "store_schema", "format_version", "session_id", "created_ms", "created_by"}
    if (set(value) != expected or value.get("schema") != HEADER_SCHEMA
            or value.get("store_schema") != STORE_SCHEMA or value.get("format_version") != FORMAT_VERSION
            or value.get("session_id") != session_id):
        raise SessionSpineStoreError("Session store header schema does not verify.")
    _integer(value.get("created_ms"), "Session creation time")
    _owner(value.get("created_by"))
    return dict(value)


def _prepare(
    value: Mapping[str, Any],
    *,
    session_id: str,
    ordinal: int,
    previous_commit_hash: str,
) -> tuple[dict[str, Any], SessionEvent]:
    expected = {
        "schema", "session_id", "ordinal", "owner_id", "previous_commit_hash",
        "event", "event_hash", "prepare_hash",
    }
    if (set(value) != expected or value.get("schema") != PREPARE_SCHEMA
            or value.get("session_id") != session_id or value.get("ordinal") != ordinal
            or value.get("previous_commit_hash") != previous_commit_hash):
        raise SessionSpineStoreError("Prepared session event breaks its sequence or hash chain.")
    _owner(value.get("owner_id"))
    _hash(value.get("event_hash"), "Prepared event hash")
    _hash(value.get("prepare_hash"), "Prepare hash")
    if _digest(value.get("event")) != value["event_hash"] or _digest(_without(value, "prepare_hash")) != value["prepare_hash"]:
        raise SessionSpineStoreError("Prepared session event hash does not verify.")
    try:
        event = event_from_dict(value["event"])
    except (TypeError, ValueError) as error:
        raise SessionSpineStoreError(f"Prepared Session Spine event is invalid: {error}") from None
    if event.seq != ordinal:
        raise SessionSpineStoreError("Prepared Session Spine event sequence does not match its envelope.")
    return dict(value), event


def _commit(
    value: Mapping[str, Any],
    *,
    session_id: str,
    ordinal: int,
    prepared: Mapping[str, Any],
    previous_commit_hash: str,
) -> str:
    expected = {
        "schema", "session_id", "ordinal", "owner_id", "previous_commit_hash",
        "prepare_hash", "commit_hash",
    }
    if (set(value) != expected or value.get("schema") != COMMIT_SCHEMA
            or value.get("session_id") != session_id or value.get("ordinal") != ordinal
            or value.get("owner_id") != prepared.get("owner_id")
            or value.get("previous_commit_hash") != previous_commit_hash
            or value.get("prepare_hash") != prepared.get("prepare_hash")):
        raise SessionSpineStoreError("Session commit does not match its prepared event.")
    commit_hash = _hash(value.get("commit_hash"), "Commit hash")
    if _digest(_without(value, "commit_hash")) != commit_hash:
        raise SessionSpineStoreError("Session commit hash does not verify.")
    return commit_hash


def _parse(raw: bytes, session_id: str) -> _ParsedLog:
    if not raw:
        raise SessionSpineStoreError("Session store has no committed header.")
    if len(raw) > MAX_FILE_BYTES:
        raise SessionSpineStoreError("Session store exceeds its bounded file size.")
    boundary = raw.rfind(b"\n") + 1
    complete = raw[:boundary]
    tail = raw[boundary:]
    if len(tail) > MAX_RECORD_BYTES:
        raise SessionSpineStoreError("Torn session tail exceeds the record boundary.")
    lines = complete.splitlines()
    if not lines:
        raise SessionSpineStoreError("Session store has no committed header.")
    header = _header(_decode(lines[0], "Session store header"), session_id)
    previous = _digest(header)
    events: list[SessionEvent] = []
    owners: list[str] = []
    pending: int | None = None
    index = 1
    while index < len(lines):
        prepared, event = _prepare(
            _decode(lines[index], "Prepared session event"),
            session_id=session_id,
            ordinal=len(events),
            previous_commit_hash=previous,
        )
        if index + 1 == len(lines):
            pending = event.seq
            break
        previous = _commit(
            _decode(lines[index + 1], "Session event commit"),
            session_id=session_id,
            ordinal=len(events),
            prepared=prepared,
            previous_commit_hash=previous,
        )
        events.append(event)
        if prepared["owner_id"] not in owners:
            owners.append(prepared["owner_id"])
        if len(events) > MAX_EVENTS:
            raise SessionSpineStoreError("Session store exceeds its bounded event count.")
        index += 2
    return _ParsedLog(header, tuple(events), tuple(owners), raw, previous, pending, len(tail))


def _turn_state(events: tuple[SessionEvent, ...], uncertain_tail: bool) -> str:
    active = False
    completed = 0
    for event in events:
        if event.event_type == "turn/start":
            if active:
                raise SessionSpineStoreError("Committed session evidence contains overlapping turns.")
            active = True
        elif event.event_type == "turn/end":
            if not active:
                raise SessionSpineStoreError("Committed session evidence ends a turn that never started.")
            active = False
            completed += 1
    if uncertain_tail or active:
        return "unknown"
    return "closed" if completed else "idle"


def _snapshot(parsed: _ParsedLog) -> SessionSpineStoreSnapshot:
    uncertain = parsed.uncommitted_event_seq is not None or parsed.torn_tail_bytes > 0
    state = _turn_state(parsed.events, uncertain)
    surface = fold_surface(parsed.events)
    warnings: list[str] = []
    if parsed.uncommitted_event_seq is not None:
        warnings.append(
            f"Event {parsed.uncommitted_event_seq} has prepare evidence without a durable commit; it was not replayed."
        )
    if parsed.torn_tail_bytes:
        warnings.append(f"Ignored {parsed.torn_tail_bytes} torn tail bytes; no repair was attempted.")
    if state == "unknown" and not uncertain:
        warnings.append("The committed log ends inside a turn; outcome remains unknown after restart.")
    if len(parsed.events) >= MAX_EVENTS:
        warnings.append("Session event limit reached; export and review before any future retention decision.")
    return SessionSpineStoreSnapshot(
        session_id=parsed.header["session_id"],
        created_ms=parsed.header["created_ms"],
        created_by=parsed.header["created_by"],
        events=parsed.events,
        append_owners=parsed.append_owners,
        surface=surface,
        file_bytes=len(parsed.raw),
        file_sha256=hashlib.sha256(parsed.raw).hexdigest(),
        last_commit_hash=parsed.last_commit_hash,
        recovery_state=state,
        appendable=not uncertain and state != "unknown" and len(parsed.events) < MAX_EVENTS,
        uncommitted_event_seq=parsed.uncommitted_event_seq,
        torn_tail_bytes=parsed.torn_tail_bytes,
        warnings=tuple(warnings),
    )


def inspect_store_image(raw: bytes, session_id: str) -> SessionSpineStoreSnapshot:
    """Validate one detached store image without opening a path or changing bytes."""
    if type(raw) is not bytes:
        raise SessionSpineStoreError("Detached Session Spine image must be immutable bytes.")
    return _snapshot(_parse(raw, _uuid(session_id, "Session ID")))


def build_store_image(
    *,
    session_id: str,
    created_ms: int,
    owner_id: str,
    events: Iterable[SessionEvent],
) -> bytes:
    """Build the exact canonical P2a bytes for an explicitly supplied event fixture."""
    session = _uuid(session_id, "Session ID")
    created = _integer(created_ms, "Session creation time")
    owner = _owner(owner_id)
    try:
        rows = tuple(islice(iter(events), MAX_EVENTS + 1))
    except TypeError:
        raise SessionSpineStoreError("Session image events must be an iterable of validated events.") from None
    if len(rows) > MAX_EVENTS:
        raise SessionSpineStoreError("Session store exceeds its bounded event count.")
    for expected, event in enumerate(rows):
        if not isinstance(event, SessionEvent) or event.seq != expected:
            raise SessionSpineStoreError("Session image requires contiguous validated events from sequence zero.")
    try:
        fold_surface(rows)
        _turn_state(rows, False)
    except SessionSpineStoreError:
        raise
    except ValueError as error:
        raise SessionSpineStoreError(f"Session image events do not replay: {error}") from None

    header = {
        "schema": HEADER_SCHEMA,
        "store_schema": STORE_SCHEMA,
        "format_version": FORMAT_VERSION,
        "session_id": session,
        "created_ms": created,
        "created_by": owner,
    }
    raw = _line(header)
    previous = _digest(header)
    for event in rows:
        prepare_line, commit_line, _, committed = _event_records(
            session_id=session,
            owner_id=owner,
            event=event,
            previous_commit_hash=previous,
        )
        if len(raw) + len(prepare_line) + len(commit_line) > MAX_FILE_BYTES:
            raise SessionSpineStoreError("Session store file limit reached; no automatic cleanup.")
        raw += prepare_line + commit_line
        previous = committed["commit_hash"]

    snapshot = inspect_store_image(raw, session)
    if snapshot.events != rows or snapshot.last_commit_hash != previous:
        raise SessionSpineStoreError("Built Session Spine image did not survive exact replay.")
    return raw


class SessionSpineStore:
    """Explicit detached store; constructing or inspecting it performs no writes."""

    def __init__(self, directory: Path) -> None:
        self.directory = Path(directory)
        if not self.directory.is_absolute():
            raise SessionSpineStoreError("Session Spine storage requires an explicit absolute directory.")

    @contextmanager
    def _directory(self, *, create: bool = False) -> Iterator[int | None]:
        descriptor: int | None = None
        parent: int | None = None
        try:
            flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
            parent = os.open("/", flags)
            parts = self.directory.parts[1:]
            for index, part in enumerate(parts):
                if not part or part in {".", ".."}:
                    raise SessionSpineStoreError("Session store path is not canonical.")
                final = index == len(parts) - 1
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
                raise SessionSpineStoreError("Session store directory must be private and non-symlinked.")
            yield descriptor
        except SessionSpineStoreError:
            raise
        except OSError as error:
            raise SessionSpineStoreError(f"Session store directory is unavailable or unsafe: {error.strerror}.") from None
        finally:
            if descriptor is not None:
                os.close(descriptor)
            if parent is not None:
                os.close(parent)

    @staticmethod
    def _names(session_id: str) -> tuple[str, str]:
        session = _uuid(session_id, "Session ID")
        return session + ".spine.jsonl", session + ".spine.lock"

    @staticmethod
    def _regular(directory: int, name: str, flags: int, *, limit: int) -> int:
        try:
            descriptor = os.open(name, flags | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        except FileNotFoundError:
            raise
        except OSError as error:
            raise SessionSpineStoreError(f"Session Spine file is unavailable or unsafe: {name}: {error.strerror}.") from None
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077 or info.st_size > limit:
            os.close(descriptor)
            raise SessionSpineStoreError(f"Unsafe or unbounded Session Spine file: {name}.")
        return descriptor

    @staticmethod
    def _raw(descriptor: int) -> bytes:
        info = os.fstat(descriptor)
        if info.st_size > MAX_FILE_BYTES:
            raise SessionSpineStoreError("Session store exceeds its bounded file size.")
        raw = os.pread(descriptor, MAX_FILE_BYTES + 1, 0)
        if len(raw) > MAX_FILE_BYTES:
            raise SessionSpineStoreError("Session store exceeds its bounded file size.")
        return raw

    @staticmethod
    def _catalog_sessions(directory: int) -> set[str]:
        sessions: set[str] = set()
        with os.scandir(directory) as entries:
            for entry in entries:
                name = entry.name
                if name == CATALOG_LOCK:
                    continue
                suffix = ".spine.jsonl" if name.endswith(".spine.jsonl") else ".spine.lock" if name.endswith(".spine.lock") else None
                if suffix is None:
                    raise SessionSpineStoreError(f"Unexpected file in dedicated Session Spine store: {name[:160]}.")
                session_id = name.removesuffix(suffix)
                _uuid(session_id, "Stored session filename")
                if suffix == ".spine.jsonl":
                    sessions.add(session_id)
        if len(sessions) > MAX_SESSIONS:
            raise SessionSpineStoreError("Session store exceeds its bounded session count.")
        return sessions

    def inspect(self, session_id: str) -> SessionSpineStoreSnapshot:
        data_name, lock_name = self._names(session_id)
        with self._directory() as directory:
            if directory is None:
                raise SessionSpineStoreMissing("Session Spine store does not exist; inspection created nothing.")
            try:
                lock = self._regular(directory, lock_name, os.O_RDONLY, limit=MAX_LOCK_BYTES)
            except FileNotFoundError:
                try:
                    os.stat(data_name, dir_fd=directory, follow_symlinks=False)
                except FileNotFoundError:
                    raise SessionSpineStoreMissing("Session Spine session does not exist; inspection created nothing.") from None
                raise SessionSpineStoreError("Session data exists without its ownership lock.") from None
            try:
                try:
                    fcntl.flock(lock, fcntl.LOCK_SH | fcntl.LOCK_NB)
                except BlockingIOError:
                    raise SessionSpineStoreBusy("Session currently has an active writer; no unstable read was attempted.") from None
                try:
                    data = self._regular(directory, data_name, os.O_RDONLY, limit=MAX_FILE_BYTES)
                except FileNotFoundError:
                    raise SessionSpineStoreError("Session ownership lock exists without session data.") from None
                try:
                    before = os.fstat(data)
                    raw = self._raw(data)
                    after = os.fstat(data)
                    current = os.stat(data_name, dir_fd=directory, follow_symlinks=False)
                    stable = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
                    if (stable != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
                            or stable != (current.st_dev, current.st_ino, current.st_size, current.st_mtime_ns)):
                        raise SessionSpineStoreError("Session data changed during inspection; no unstable view was returned.")
                    return _snapshot(_parse(raw, _uuid(session_id, "Session ID")))
                finally:
                    os.close(data)
            finally:
                os.close(lock)

    def retention_preview(self, session_id: str) -> dict[str, Any]:
        snapshot = self.inspect(session_id)
        event_ratio = len(snapshot.events) / MAX_EVENTS
        byte_ratio = snapshot.file_bytes / MAX_FILE_BYTES
        pressure = "high" if max(event_ratio, byte_ratio) >= 0.9 else "watch" if max(event_ratio, byte_ratio) >= 0.75 else "normal"
        return {
            "schema": RETENTION_SCHEMA,
            "read_only": True,
            "no_write": True,
            "automatic_compaction": False,
            "automatic_deletion": False,
            "session_id": snapshot.session_id,
            "committed_event_count": len(snapshot.events),
            "event_limit": MAX_EVENTS,
            "file_bytes": snapshot.file_bytes,
            "file_byte_limit": MAX_FILE_BYTES,
            "pressure": pressure,
            "export_required_before_compaction": True,
            "recommendation": (
                "Export and manually review this session before any future retention or compaction operation."
                if pressure != "normal" else
                "No retention action is needed; preserve the append-only evidence."
            ),
        }

    def writer(
        self,
        session_id: str,
        owner_id: str,
        *,
        created_ms: int | None = None,
        expected_fingerprint: str | None = None,
    ) -> "SessionSpineWriter":
        return SessionSpineWriter(
            self,
            _uuid(session_id, "Session ID"),
            _owner(owner_id),
            created_ms=created_ms,
            expected_fingerprint=expected_fingerprint,
        )


class SessionSpineWriter:
    """Exclusive two-phase event appender for one explicitly selected session."""

    def __init__(
        self,
        store: SessionSpineStore,
        session_id: str,
        owner_id: str,
        *,
        created_ms: int | None,
        expected_fingerprint: str | None,
    ) -> None:
        self.store = store
        self.session_id = session_id
        self.owner_id = owner_id
        self.created_ms = created_ms
        self.expected_fingerprint = expected_fingerprint
        self.directory_context = None
        self.directory: int | None = None
        self.catalog: int | None = None
        self.lock: int | None = None
        self.data: int | None = None
        self.events: tuple[SessionEvent, ...] = ()
        self.raw = b""
        self.last_commit_hash = ""
        self.failed = False

    def __enter__(self) -> "SessionSpineWriter":
        data_name, lock_name = self.store._names(self.session_id)
        try:
            if self.expected_fingerprint is None and self.created_ms is None:
                raise SessionSpineStoreError("A new session needs a creation time; an existing session needs an inspected fingerprint.")
            self.directory_context = self.store._directory(
                create=self.expected_fingerprint is None and self.created_ms is not None,
            )
            self.directory = self.directory_context.__enter__()
            if self.directory is None:
                raise SessionSpineStoreError("Expected Session Spine storage is missing; nothing was created.")
            try:
                self.catalog = os.open(
                    CATALOG_LOCK,
                    os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK,
                    0o600,
                    dir_fd=self.directory,
                )
            except OSError as error:
                raise SessionSpineStoreError(f"Session catalog lock is unavailable: {error.strerror}.") from None
            catalog_info = os.fstat(self.catalog)
            if not stat.S_ISREG(catalog_info.st_mode) or catalog_info.st_mode & 0o077 or catalog_info.st_size > MAX_LOCK_BYTES:
                raise SessionSpineStoreError("Session catalog lock is unsafe or unbounded.")
            try:
                fcntl.flock(self.catalog, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise SessionSpineStoreBusy("Another Session Spine writer is opening a session.") from None
            sessions = self.store._catalog_sessions(self.directory)
            try:
                current_data = os.stat(data_name, dir_fd=self.directory, follow_symlinks=False)
                data_exists = True
                if not stat.S_ISREG(current_data.st_mode):
                    raise SessionSpineStoreError("Session data path is not a regular file.")
            except FileNotFoundError:
                data_exists = False
            if not data_exists and self.expected_fingerprint is not None:
                raise SessionSpineStoreError("Expected session evidence is missing; no replacement was created.")
            if not data_exists and len(sessions) >= MAX_SESSIONS:
                raise SessionSpineStoreError("Session count limit reached; no automatic retention or cleanup.")
            try:
                lock_flags = os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK
                if not data_exists:
                    lock_flags |= os.O_CREAT
                self.lock = os.open(
                    lock_name,
                    lock_flags,
                    0o600,
                    dir_fd=self.directory,
                )
            except OSError as error:
                raise SessionSpineStoreError(f"Session ownership lock is unavailable: {error.strerror}.") from None
            lock_info = os.fstat(self.lock)
            if not stat.S_ISREG(lock_info.st_mode) or lock_info.st_mode & 0o077 or lock_info.st_size > MAX_LOCK_BYTES:
                raise SessionSpineStoreError("Session ownership lock is unsafe or unbounded.")
            try:
                fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise SessionSpineStoreBusy("Another writer already owns this Session Spine session.") from None

            created = False
            if data_exists:
                self.data = os.open(
                    data_name,
                    os.O_RDWR | os.O_APPEND | os.O_NOFOLLOW | os.O_NONBLOCK,
                    dir_fd=self.directory,
                )
            else:
                if self.created_ms is None:
                    raise SessionSpineStoreError("A new Session Spine session requires an explicit creation time.") from None
                _integer(self.created_ms, "Session creation time")
                self.data = os.open(
                    data_name,
                    os.O_RDWR | os.O_APPEND | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_NONBLOCK,
                    0o600,
                    dir_fd=self.directory,
                )
                created = True
            data_info = os.fstat(self.data)
            if not stat.S_ISREG(data_info.st_mode) or data_info.st_mode & 0o077 or data_info.st_size > MAX_FILE_BYTES:
                raise SessionSpineStoreError("Session data file is unsafe or unbounded.")
            if created:
                header = {
                    "schema": HEADER_SCHEMA,
                    "store_schema": STORE_SCHEMA,
                    "format_version": FORMAT_VERSION,
                    "session_id": self.session_id,
                    "created_ms": self.created_ms,
                    "created_by": self.owner_id,
                }
                try:
                    self._write_and_sync(_line(header))
                    os.fsync(self.directory)
                except OSError as error:
                    raise SessionSpineStoreError(
                        f"Session header durability is unknown: {error}. Inspect before any retry."
                    ) from None
            parsed = _parse(self.store._raw(self.data), self.session_id)
            snapshot = _snapshot(parsed)
            if parsed.uncommitted_event_seq is not None or parsed.torn_tail_bytes:
                raise SessionSpineStoreError("Session has an incomplete tail; inspect it manually. No repair or append.")
            if not created:
                if self.expected_fingerprint is None:
                    raise SessionSpineStoreError("Inspect the current session and supply its exact fingerprint before appending.")
                _hash(self.expected_fingerprint, "Expected session fingerprint")
                if snapshot.file_sha256 != self.expected_fingerprint:
                    raise SessionSpineStoreError("Session changed after inspection; no stale append was attempted.")
                if snapshot.recovery_state == "unknown":
                    raise SessionSpineStoreError("Interrupted session outcome is unknown; automatic resume is forbidden.")
            try:
                os.ftruncate(self.lock, 0)
                owner_bytes = memoryview((self.owner_id + "\n").encode("ascii"))
                while owner_bytes:
                    written = os.write(self.lock, owner_bytes)
                    if written <= 0:
                        raise OSError("zero-byte owner write")
                    owner_bytes = owner_bytes[written:]
                os.fsync(self.lock)
            except OSError as error:
                raise SessionSpineStoreError(f"Session owner marker could not be committed: {error}.") from None
            self.events = parsed.events
            self.raw = parsed.raw
            self.last_commit_hash = parsed.last_commit_hash
            os.close(self.catalog)
            self.catalog = None
            return self
        except SessionSpineStoreError:
            self.close()
            raise
        except OSError as error:
            self.close()
            raise SessionSpineStoreError(f"Session writer setup is unavailable or unsafe: {error.strerror}.") from None
        except BaseException:
            self.close()
            raise

    def _write_and_sync(self, payload: bytes) -> None:
        if self.data is None:
            raise SessionSpineStoreError("Session writer is not open.")
        view = memoryview(payload)
        while view:
            written = os.write(self.data, view)
            if written <= 0:
                raise OSError("zero-byte session append")
            view = view[written:]
        os.fsync(self.data)

    def _identity(self) -> None:
        if self.directory is None or self.data is None:
            raise SessionSpineStoreError("Session writer is not open.")
        data_name, _ = self.store._names(self.session_id)
        opened = os.fstat(self.data)
        current = os.stat(data_name, dir_fd=self.directory, follow_symlinks=False)
        if not stat.S_ISREG(current.st_mode) or (opened.st_dev, opened.st_ino) != (current.st_dev, current.st_ino):
            raise SessionSpineStoreError("Session data file changed while its writer was active.")

    def append(self, event: SessionEvent) -> SessionSpineAppendReceipt:
        if self.failed:
            raise SessionSpineStoreError("A previous append outcome is unknown; close and inspect without retrying.")
        if not isinstance(event, SessionEvent) or event.seq != len(self.events):
            raise SessionSpineStoreError("Session append requires the exact next validated event sequence.")
        if len(self.events) >= MAX_EVENTS:
            raise SessionSpineStoreError("Session event limit reached; no automatic retention or compaction.")
        write_started = False
        try:
            self._identity()
            prospective = (*self.events, event)
            fold_surface(prospective)
            _turn_state(prospective, False)
            previous = self.last_commit_hash
            prepare_line, commit_line, prepared, committed = _event_records(
                session_id=self.session_id,
                owner_id=self.owner_id,
                event=event,
                previous_commit_hash=previous,
            )
            if len(self.raw) + len(prepare_line) + len(commit_line) > MAX_FILE_BYTES:
                raise SessionSpineStoreError("Session store file limit reached; no automatic cleanup.")
            write_started = True
            self._write_and_sync(prepare_line)
            self._write_and_sync(commit_line)
            expected_raw = self.raw + prepare_line + commit_line
            self._identity()
            if self.store._raw(self.data) != expected_raw:
                raise SessionSpineStoreError("Session append readback does not match the exact committed bytes.")
            self.raw = expected_raw
            self.events = prospective
            self.last_commit_hash = committed["commit_hash"]
            return SessionSpineAppendReceipt(
                session_id=self.session_id,
                owner_id=self.owner_id,
                event_seq=event.seq,
                event_hash=prepared["event_hash"],
                prepare_hash=prepared["prepare_hash"],
                commit_hash=committed["commit_hash"],
                previous_commit_hash=previous,
                file_sha256=hashlib.sha256(self.raw).hexdigest(),
                file_bytes=len(self.raw),
            )
        except SessionSpineStoreError as error:
            if write_started:
                self.failed = True
                raise SessionSpineStoreError(
                    f"Session append outcome is unknown after writing began: {error} Do not retry; inspect first."
                ) from None
            raise
        except (OSError, ValueError) as error:
            self.failed = True
            raise SessionSpineStoreError(
                f"Session append did not reach a confirmed commit boundary: {error}. Do not retry; inspect first."
            ) from None

    def close(self) -> None:
        if self.data is not None:
            os.close(self.data)
            self.data = None
        if self.lock is not None:
            os.close(self.lock)
            self.lock = None
        if self.catalog is not None:
            os.close(self.catalog)
            self.catalog = None
        if self.directory_context is not None:
            self.directory_context.__exit__(None, None, None)
            self.directory_context = None
            self.directory = None

    def __exit__(self, *_: object) -> None:
        self.close()
