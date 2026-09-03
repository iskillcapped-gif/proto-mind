"""Fixture-only Session Spine export and migration/rollback previews.

This module has no personal path, archive scanner, restore writer, or production
caller. It accepts one explicit canonical Native turn fixture, reuses the P1
projection and P2a byte builder, and may only create a new private export bundle.
Migration and rollback results are detached plans; neither can change a store.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
import hashlib
import json
import os
from pathlib import Path
import re
import stat
from typing import Any, Iterator, Mapping
from uuid import UUID

from proto_mind.native_session_spine import (
    NativeSessionProjectionError,
    NativeTurnProjection,
    project_native_turn,
)
from proto_mind.session_spine_store import (
    FORMAT_VERSION as STORE_FORMAT_VERSION,
    MAX_FILE_BYTES,
    STORE_SCHEMA,
    SessionSpineStoreError,
    build_store_image,
    inspect_store_image,
)


FIXTURE_SCHEMA = "proto_mind.native_session_spine_migration_fixture.v1"
MIGRATION_SCHEMA = "proto_mind.session_spine_migration_preview.v1"
EXPORT_SCHEMA = "proto_mind.session_spine_export.v1"
EXPORT_RECEIPT_SCHEMA = "proto_mind.session_spine_export_receipt.v1"
EXPORT_VERIFICATION_SCHEMA = "proto_mind.session_spine_export_verification.v1"
ROLLBACK_SCHEMA = "proto_mind.session_spine_rollback_preview.v1"
FORMAT_VERSION = 1
MAX_FIXTURE_BYTES = 2 * 1024 * 1024
MAX_MANIFEST_BYTES = 128 * 1024
SOURCE_FILE = "source.native-session.json"
CANDIDATE_FILE = "candidate.session-spine.jsonl"
ROLLBACK_FILE = "rollback.preimage.jsonl"
MANIFEST_FILE = "manifest.json"
HASH = re.compile(r"^[0-9a-f]{64}$")
OWNER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,119}$")


class SessionSpineTransferError(RuntimeError):
    """A fixture, export, migration, or rollback preview is unsafe or invalid."""


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
        raise SessionSpineTransferError("Session Spine transfer data is not lossless JSON.") from None


def _line(value: object) -> bytes:
    return _canonical(value) + b"\n"


def _digest_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _digest_value(value: object) -> str:
    return _digest_bytes(_canonical(value))


def _pairs(values: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in values:
        if key in result:
            raise SessionSpineTransferError("Duplicate JSON field in Session Spine transfer evidence.")
        result[key] = value
    return result


def _constant(_: str) -> None:
    raise SessionSpineTransferError("Non-finite JSON in Session Spine transfer evidence.")


def _decode_line(raw: bytes, label: str, limit: int) -> dict[str, Any]:
    if type(raw) is not bytes or not raw.endswith(b"\n") or not 1 < len(raw) <= limit:
        raise SessionSpineTransferError(f"{label} must be bounded canonical JSON with one final newline.")
    body = raw[:-1]
    try:
        value = json.loads(body.decode("utf-8"), object_pairs_hook=_pairs, parse_constant=_constant)
    except SessionSpineTransferError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError, RecursionError):
        raise SessionSpineTransferError(f"{label} is not valid canonical JSON.") from None
    if not isinstance(value, dict) or _canonical(value) != body:
        raise SessionSpineTransferError(f"{label} is not a canonical JSON object.")
    return value


def _uuid(value: object, label: str) -> str:
    try:
        result = str(UUID(str(value)))
    except (ValueError, TypeError, AttributeError):
        raise SessionSpineTransferError(f"{label} is invalid.") from None
    if result != value:
        raise SessionSpineTransferError(f"{label} must use canonical lowercase UUID text.")
    return result


def _owner(value: object) -> str:
    if not isinstance(value, str) or not OWNER.fullmatch(value):
        raise SessionSpineTransferError("Session Spine migration owner ID is invalid.")
    return value


def _integer(value: object, label: str) -> int:
    if type(value) is not int or value < 0:
        raise SessionSpineTransferError(f"{label} must be a non-negative integer.")
    return value


def _hash(value: object, label: str) -> str:
    if not isinstance(value, str) or not HASH.fullmatch(value):
        raise SessionSpineTransferError(f"{label} must be a lowercase SHA-256 digest.")
    return value


def _fixture_projection(raw: bytes):
    fixture = _decode_line(raw, "Native migration fixture", MAX_FIXTURE_BYTES)
    expected = {"schema", "conversation_id", "user_message", "assistant_message", "work_session"}
    if set(fixture) != expected or fixture.get("schema") != FIXTURE_SCHEMA:
        raise SessionSpineTransferError("Native migration fixture schema is not supported.")
    conversation_id = _uuid(fixture.get("conversation_id"), "Fixture conversation ID")
    if not isinstance(fixture.get("user_message"), Mapping):
        raise SessionSpineTransferError("Native migration fixture has no user message object.")
    if fixture.get("assistant_message") is not None and not isinstance(fixture["assistant_message"], Mapping):
        raise SessionSpineTransferError("Native migration fixture assistant message must be an object or null.")
    if not isinstance(fixture.get("work_session"), Mapping):
        raise SessionSpineTransferError("Native migration fixture has no work-session object.")
    try:
        projection = project_native_turn(
            conversation_id=conversation_id,
            user_message=fixture["user_message"],
            assistant_message=fixture["assistant_message"],
            work_session=fixture["work_session"],
        )
    except NativeSessionProjectionError as error:
        raise SessionSpineTransferError(f"Native migration fixture does not pass P1 projection: {error}") from None
    if not projection.events or projection.events[0].event_type != "turn/start":
        raise SessionSpineTransferError("Native migration fixture did not produce a bounded turn projection.")
    return fixture, projection


def project_native_fixture(raw: bytes) -> NativeTurnProjection:
    """Revalidate one explicit canonical fixture through the detached P1 adapter."""
    if type(raw) is not bytes:
        raise SessionSpineTransferError("Native migration fixture must be immutable bytes.")
    _, projection = _fixture_projection(raw)
    return projection


@dataclass(frozen=True)
class SessionSpineMigrationPreview:
    session_id: str
    owner_id: str
    created_ms: int
    source_fixture_sha256: str
    source_fixture_bytes: int
    event_count: int
    surface_fingerprint: str
    candidate_sha256: str
    candidate_bytes: int
    target_state: str
    migration_status: str
    future_operation: str
    rollback_state: str
    rollback_sha256: str | None
    rollback_bytes: int
    _source_raw: bytes = field(repr=False)
    _candidate_raw: bytes = field(repr=False)
    _rollback_raw: bytes | None = field(repr=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": MIGRATION_SCHEMA,
            "format_version": FORMAT_VERSION,
            "read_only": True,
            "no_write": True,
            "apply_installed": False,
            "personal_archive_scanned": False,
            "session_id": self.session_id,
            "owner_id": self.owner_id,
            "created_ms": self.created_ms,
            "source": {
                "schema": FIXTURE_SCHEMA,
                "sha256": self.source_fixture_sha256,
                "bytes": self.source_fixture_bytes,
                "explicit_fixture_only": True,
                "contains_exact_source_content": True,
                "safe_to_publish": False,
            },
            "candidate": {
                "store_schema": STORE_SCHEMA,
                "store_format_version": STORE_FORMAT_VERSION,
                "sha256": self.candidate_sha256,
                "bytes": self.candidate_bytes,
                "event_count": self.event_count,
                "surface_fingerprint": self.surface_fingerprint,
                "exact_event_parity": True,
            },
            "target": {
                "state": self.target_state,
                "migration_status": self.migration_status,
                "future_operation": self.future_operation,
                "eligible_for_future_apply_review": self.migration_status == "READY_FOR_SEPARATE_REVIEW",
                "overwrite_allowed": False,
            },
            "rollback": {
                "state": self.rollback_state,
                "sha256": self.rollback_sha256,
                "bytes": self.rollback_bytes,
                "preimage_exact": True,
                "restore_installed": False,
            },
            "separate_checkpoint_required": True,
            "task_success_inferred": False,
        }


def preview_native_fixture_migration(
    fixture_raw: bytes,
    *,
    owner_id: str,
    target_preimage: bytes | None = None,
) -> SessionSpineMigrationPreview:
    """Build an in-memory P2a candidate from one explicit copied Native fixture."""
    if type(fixture_raw) is not bytes:
        raise SessionSpineTransferError("Native migration fixture must be immutable bytes.")
    _, projection = _fixture_projection(fixture_raw)
    session_id = _uuid(projection.events[0].data.get("conversation_id"), "Projected conversation ID")
    owner = _owner(owner_id)
    created_ms = projection.events[0].time_ms
    try:
        candidate = build_store_image(
            session_id=session_id,
            created_ms=created_ms,
            owner_id=owner,
            events=projection.events,
        )
        snapshot = inspect_store_image(candidate, session_id)
    except SessionSpineStoreError as error:
        raise SessionSpineTransferError(f"P2a candidate cannot be built or replayed: {error}") from None
    if snapshot.events != projection.events or snapshot.surface != projection.surface:
        raise SessionSpineTransferError("P1 projection and P2a candidate do not have exact replay parity.")

    rollback_raw: bytes | None = None
    rollback_hash: str | None = None
    rollback_bytes = 0
    if target_preimage is None:
        target_state = "absent"
        migration_status = "READY_FOR_SEPARATE_REVIEW"
        future_operation = "create_new"
        rollback_state = "absence_marker"
    else:
        if type(target_preimage) is not bytes:
            raise SessionSpineTransferError("Target preimage must be immutable bytes or absent.")
        try:
            inspect_store_image(target_preimage, session_id)
        except SessionSpineStoreError as error:
            raise SessionSpineTransferError(f"Target preimage is not a valid P2a image: {error}") from None
        if target_preimage == candidate:
            target_state = "identical"
            migration_status = "NO_CHANGE"
            future_operation = "none"
            rollback_state = "not_required"
        else:
            target_state = "occupied_different"
            migration_status = "BLOCKED"
            future_operation = "none"
            rollback_state = "exact_preimage_captured"
            rollback_raw = target_preimage
            rollback_hash = _digest_bytes(target_preimage)
            rollback_bytes = len(target_preimage)
    return SessionSpineMigrationPreview(
        session_id=session_id,
        owner_id=owner,
        created_ms=created_ms,
        source_fixture_sha256=_digest_bytes(fixture_raw),
        source_fixture_bytes=len(fixture_raw),
        event_count=len(projection.events),
        surface_fingerprint=projection.surface.fingerprint,
        candidate_sha256=_digest_bytes(candidate),
        candidate_bytes=len(candidate),
        target_state=target_state,
        migration_status=migration_status,
        future_operation=future_operation,
        rollback_state=rollback_state,
        rollback_sha256=rollback_hash,
        rollback_bytes=rollback_bytes,
        _source_raw=fixture_raw,
        _candidate_raw=candidate,
        _rollback_raw=rollback_raw,
    )


@contextmanager
def _private_directory(path: Path, *, create: bool = False) -> Iterator[int | None]:
    directory = Path(path)
    if not directory.is_absolute():
        raise SessionSpineTransferError("Session Spine export paths must be explicit and absolute.")
    descriptor: int | None = None
    parent: int | None = None
    try:
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        parent = os.open("/", flags)
        parts = directory.parts[1:]
        for index, part in enumerate(parts):
            if not part or part in {".", ".."}:
                raise SessionSpineTransferError("Session Spine export path is not canonical.")
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
            raise SessionSpineTransferError("Session Spine export directory must be private and non-symlinked.")
        yield descriptor
    except SessionSpineTransferError:
        raise
    except OSError as error:
        raise SessionSpineTransferError(f"Session Spine export directory is unavailable or unsafe: {error.strerror}.") from None
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if parent is not None:
            os.close(parent)


def _read_regular(directory: int, name: str, *, limit: int) -> bytes:
    try:
        descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
    except FileNotFoundError:
        raise SessionSpineTransferError(f"Session Spine export is incomplete; {name} is missing.") from None
    except OSError as error:
        raise SessionSpineTransferError(f"Session Spine export file is unavailable or unsafe: {name}: {error.strerror}.") from None
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_mode & 0o077 or before.st_size > limit:
            raise SessionSpineTransferError(f"Session Spine export file is unsafe or unbounded: {name}.")
        raw = os.pread(descriptor, limit + 1, 0)
        after = os.fstat(descriptor)
        current = os.stat(name, dir_fd=directory, follow_symlinks=False)
        identity = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
        if len(raw) > limit or identity != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
            raise SessionSpineTransferError(f"Session Spine export file changed while reading: {name}.")
        if identity != (current.st_dev, current.st_ino, current.st_size, current.st_mtime_ns):
            raise SessionSpineTransferError(f"Session Spine export path changed while reading: {name}.")
        return raw
    finally:
        os.close(descriptor)


def _write_new(directory: int, name: str, payload: bytes, *, limit: int) -> None:
    if not payload or len(payload) > limit:
        raise SessionSpineTransferError(f"Session Spine export payload is empty or unbounded: {name}.")
    try:
        descriptor = os.open(
            name,
            os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_NONBLOCK,
            0o600,
            dir_fd=directory,
        )
    except OSError as error:
        raise SessionSpineTransferError(f"Session Spine export file could not be created: {name}: {error.strerror}.") from None
    try:
        view = memoryview(payload)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError("zero-byte export write")
            view = view[written:]
        os.fsync(descriptor)
        info = os.fstat(descriptor)
        if (not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077
                or info.st_size != len(payload) or os.pread(descriptor, len(payload) + 1, 0) != payload):
            raise SessionSpineTransferError(f"Session Spine export readback failed: {name}.")
    except SessionSpineTransferError:
        raise
    except OSError as error:
        raise SessionSpineTransferError(
            f"Session Spine export durability is unknown for {name}: {error}. Inspect the partial bundle; do not retry its ID."
        ) from None
    finally:
        os.close(descriptor)


def _manifest(preview: SessionSpineMigrationPreview, export_id: str, generated_ms: int) -> dict[str, Any]:
    rollback_file = ROLLBACK_FILE if preview._rollback_raw is not None else None
    value: dict[str, Any] = {
        "schema": EXPORT_SCHEMA,
        "format_version": FORMAT_VERSION,
        "export_id": export_id,
        "generated_ms": generated_ms,
        "session_id": preview.session_id,
        "owner_id": preview.owner_id,
        "source": {
            "file": SOURCE_FILE,
            "schema": FIXTURE_SCHEMA,
            "sha256": preview.source_fixture_sha256,
            "bytes": preview.source_fixture_bytes,
        },
        "candidate": {
            "file": CANDIDATE_FILE,
            "store_schema": STORE_SCHEMA,
            "store_format_version": STORE_FORMAT_VERSION,
            "created_ms": preview.created_ms,
            "sha256": preview.candidate_sha256,
            "bytes": preview.candidate_bytes,
            "event_count": preview.event_count,
            "surface_fingerprint": preview.surface_fingerprint,
        },
        "rollback": {
            "state": preview.rollback_state,
            "file": rollback_file,
            "sha256": preview.rollback_sha256,
            "bytes": preview.rollback_bytes,
            "preimage_exact": True,
        },
        "migration": {
            "target_state": preview.target_state,
            "status": preview.migration_status,
            "future_operation": preview.future_operation,
            "eligible_for_future_apply_review": preview.migration_status == "READY_FOR_SEPARATE_REVIEW",
            "separate_checkpoint_required": True,
            "overwrite_allowed": False,
            "apply_installed": False,
        },
        "boundaries": {
            "explicit_fixture_only": True,
            "source_read_only": True,
            "export_only": True,
            "contains_exact_source_content": True,
            "safe_to_publish": False,
            "personal_archive_scanned": False,
            "migration_performed": False,
            "rollback_performed": False,
            "store_authority_changed": False,
            "task_success_inferred": False,
        },
    }
    value["manifest_hash"] = _digest_value(value)
    return value


def _revalidate_preview(preview: SessionSpineMigrationPreview) -> SessionSpineMigrationPreview:
    if preview.target_state == "absent":
        target = None
    elif preview.target_state == "identical":
        target = preview._candidate_raw
    elif preview.target_state == "occupied_different":
        target = preview._rollback_raw
    else:
        raise SessionSpineTransferError("Session Spine migration preview target state is invalid.")
    rebuilt = preview_native_fixture_migration(
        preview._source_raw,
        owner_id=preview.owner_id,
        target_preimage=target,
    )
    if rebuilt != preview:
        raise SessionSpineTransferError("Session Spine migration preview metadata does not match its exact source bytes.")
    return rebuilt


@dataclass(frozen=True)
class SessionSpineExportReceipt:
    bundle_path: Path
    export_id: str
    session_id: str
    manifest_hash: str
    candidate_sha256: str
    file_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": EXPORT_RECEIPT_SCHEMA,
            "export_only": True,
            "safe_to_publish": False,
            "migration_performed": False,
            "rollback_performed": False,
            "bundle_path": str(self.bundle_path),
            "export_id": self.export_id,
            "session_id": self.session_id,
            "manifest_hash": self.manifest_hash,
            "candidate_sha256": self.candidate_sha256,
            "file_count": self.file_count,
        }


def export_migration_preview(
    preview: SessionSpineMigrationPreview,
    *,
    export_root: Path,
    export_id: str,
    generated_ms: int,
) -> SessionSpineExportReceipt:
    """Write a new private evidence bundle; never write or replace a store."""
    if not isinstance(preview, SessionSpineMigrationPreview):
        raise SessionSpineTransferError("Session Spine export requires a validated migration preview.")
    preview = _revalidate_preview(preview)
    identifier = _uuid(export_id, "Export ID")
    generated = _integer(generated_ms, "Export generation time")
    bundle_name = identifier + ".session-spine-export"
    with _private_directory(Path(export_root), create=True) as root:
        if root is None:
            raise SessionSpineTransferError("Session Spine export root could not be created.")
        try:
            os.mkdir(bundle_name, mode=0o700, dir_fd=root)
            os.fsync(root)
            bundle = os.open(bundle_name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root)
        except FileExistsError:
            raise SessionSpineTransferError("Session Spine export ID already exists; no overwrite or retry was attempted.") from None
        except OSError as error:
            raise SessionSpineTransferError(f"Session Spine export bundle could not be created safely: {error.strerror}.") from None
        try:
            info = os.fstat(bundle)
            if not stat.S_ISDIR(info.st_mode) or info.st_mode & 0o077:
                raise SessionSpineTransferError("Session Spine export bundle is not a private directory.")
            _write_new(bundle, SOURCE_FILE, preview._source_raw, limit=MAX_FIXTURE_BYTES)
            _write_new(bundle, CANDIDATE_FILE, preview._candidate_raw, limit=MAX_FILE_BYTES)
            if preview._rollback_raw is not None:
                _write_new(bundle, ROLLBACK_FILE, preview._rollback_raw, limit=MAX_FILE_BYTES)
            manifest = _manifest(preview, identifier, generated)
            _write_new(bundle, MANIFEST_FILE, _line(manifest), limit=MAX_MANIFEST_BYTES)
            os.fsync(bundle)
        finally:
            os.close(bundle)

    path = Path(export_root) / bundle_name
    verification = verify_migration_export(path)
    return SessionSpineExportReceipt(
        bundle_path=path,
        export_id=identifier,
        session_id=preview.session_id,
        manifest_hash=verification.manifest_hash,
        candidate_sha256=verification.candidate_sha256,
        file_count=verification.file_count,
    )


@dataclass(frozen=True)
class SessionSpineExportVerification:
    bundle_path: Path
    export_id: str
    session_id: str
    manifest_hash: str
    candidate_sha256: str
    rollback_state: str
    rollback_sha256: str | None
    migration_status: str
    event_count: int
    surface_fingerprint: str
    file_count: int
    _candidate_raw: bytes = field(repr=False)
    _rollback_raw: bytes | None = field(repr=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": EXPORT_VERIFICATION_SCHEMA,
            "status": "VERIFIED",
            "read_only": True,
            "no_write": True,
            "safe_to_publish": False,
            "bundle_path": str(self.bundle_path),
            "export_id": self.export_id,
            "session_id": self.session_id,
            "manifest_hash": self.manifest_hash,
            "candidate_sha256": self.candidate_sha256,
            "rollback_state": self.rollback_state,
            "rollback_sha256": self.rollback_sha256,
            "migration_status": self.migration_status,
            "event_count": self.event_count,
            "surface_fingerprint": self.surface_fingerprint,
            "file_count": self.file_count,
            "exact_p1_p2_parity": True,
            "migration_performed": False,
            "rollback_performed": False,
        }


def _object(value: object, label: str, fields: set[str]) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != fields:
        raise SessionSpineTransferError(f"{label} fields do not match the closed export schema.")
    return value


def verify_migration_export(bundle_path: Path) -> SessionSpineExportVerification:
    """Read and independently verify one complete export bundle without mutation."""
    path = Path(bundle_path)
    with _private_directory(path) as bundle:
        if bundle is None:
            raise SessionSpineTransferError("Session Spine export bundle does not exist.")
        manifest_raw = _read_regular(bundle, MANIFEST_FILE, limit=MAX_MANIFEST_BYTES)
        manifest = _decode_line(manifest_raw, "Session Spine export manifest", MAX_MANIFEST_BYTES)
        expected = {
            "schema", "format_version", "export_id", "generated_ms", "session_id", "owner_id",
            "source", "candidate", "rollback", "migration", "boundaries", "manifest_hash",
        }
        if (set(manifest) != expected or manifest.get("schema") != EXPORT_SCHEMA
                or manifest.get("format_version") != FORMAT_VERSION):
            raise SessionSpineTransferError("Session Spine export manifest schema is not supported.")
        export_id = _uuid(manifest.get("export_id"), "Manifest export ID")
        if path.name != export_id + ".session-spine-export":
            raise SessionSpineTransferError("Session Spine export directory does not match its manifest ID.")
        _integer(manifest.get("generated_ms"), "Manifest generation time")
        session_id = _uuid(manifest.get("session_id"), "Manifest session ID")
        owner_id = _owner(manifest.get("owner_id"))
        manifest_hash = _hash(manifest.get("manifest_hash"), "Manifest hash")
        if _digest_value({key: value for key, value in manifest.items() if key != "manifest_hash"}) != manifest_hash:
            raise SessionSpineTransferError("Session Spine export manifest hash does not verify.")

        source = _object(manifest.get("source"), "Export source", {"file", "schema", "sha256", "bytes"})
        candidate = _object(
            manifest.get("candidate"),
            "Export candidate",
            {"file", "store_schema", "store_format_version", "created_ms", "sha256", "bytes", "event_count", "surface_fingerprint"},
        )
        rollback = _object(
            manifest.get("rollback"),
            "Export rollback",
            {"state", "file", "sha256", "bytes", "preimage_exact"},
        )
        migration = _object(
            manifest.get("migration"),
            "Export migration",
            {"target_state", "status", "future_operation", "eligible_for_future_apply_review",
             "separate_checkpoint_required", "overwrite_allowed", "apply_installed"},
        )
        boundaries = _object(
            manifest.get("boundaries"),
            "Export boundaries",
            {"explicit_fixture_only", "source_read_only", "export_only", "personal_archive_scanned",
             "contains_exact_source_content", "safe_to_publish", "migration_performed", "rollback_performed",
             "store_authority_changed", "task_success_inferred"},
        )
        expected_boundaries = {
            "explicit_fixture_only": True,
            "source_read_only": True,
            "export_only": True,
            "contains_exact_source_content": True,
            "safe_to_publish": False,
            "personal_archive_scanned": False,
            "migration_performed": False,
            "rollback_performed": False,
            "store_authority_changed": False,
            "task_success_inferred": False,
        }
        if boundaries != expected_boundaries:
            raise SessionSpineTransferError("Session Spine export widens its fixture-only authority.")
        if (source.get("file") != SOURCE_FILE or source.get("schema") != FIXTURE_SCHEMA
                or candidate.get("file") != CANDIDATE_FILE or candidate.get("store_schema") != STORE_SCHEMA
                or candidate.get("store_format_version") != STORE_FORMAT_VERSION):
            raise SessionSpineTransferError("Session Spine export uses an unexpected payload contract.")

        source_raw = _read_regular(bundle, SOURCE_FILE, limit=MAX_FIXTURE_BYTES)
        candidate_raw = _read_regular(bundle, CANDIDATE_FILE, limit=MAX_FILE_BYTES)
        if (_hash(source.get("sha256"), "Source fixture hash") != _digest_bytes(source_raw)
                or _integer(source.get("bytes"), "Source fixture size") != len(source_raw)
                or _hash(candidate.get("sha256"), "Candidate hash") != _digest_bytes(candidate_raw)
                or _integer(candidate.get("bytes"), "Candidate size") != len(candidate_raw)):
            raise SessionSpineTransferError("Session Spine export payload hash or size does not verify.")
        _, projection = _fixture_projection(source_raw)
        created_ms = _integer(candidate.get("created_ms"), "Candidate creation time")
        projected_session = _uuid(projection.events[0].data.get("conversation_id"), "Projected conversation ID")
        if projected_session != session_id or projection.events[0].time_ms != created_ms:
            raise SessionSpineTransferError("Export candidate identity or creation time does not match its P1 source.")
        try:
            rebuilt = build_store_image(
                session_id=session_id,
                created_ms=created_ms,
                owner_id=owner_id,
                events=projection.events,
            )
            snapshot = inspect_store_image(candidate_raw, session_id)
        except SessionSpineStoreError as error:
            raise SessionSpineTransferError(f"Exported P2a candidate does not replay: {error}") from None
        if rebuilt != candidate_raw or snapshot.events != projection.events or snapshot.surface != projection.surface:
            raise SessionSpineTransferError("Exported candidate does not preserve exact P1-to-P2 replay parity.")
        if (_integer(candidate.get("event_count"), "Candidate event count") != len(projection.events)
                or candidate.get("surface_fingerprint") != projection.surface.fingerprint):
            raise SessionSpineTransferError("Exported candidate projection metadata does not verify.")

        rollback_raw: bytes | None = None
        state = rollback.get("state")
        if state == "exact_preimage_captured":
            if rollback.get("file") != ROLLBACK_FILE or rollback.get("preimage_exact") is not True:
                raise SessionSpineTransferError("Export rollback preimage contract is invalid.")
            rollback_raw = _read_regular(bundle, ROLLBACK_FILE, limit=MAX_FILE_BYTES)
            if (_hash(rollback.get("sha256"), "Rollback preimage hash") != _digest_bytes(rollback_raw)
                    or _integer(rollback.get("bytes"), "Rollback preimage size") != len(rollback_raw)):
                raise SessionSpineTransferError("Export rollback preimage hash or size does not verify.")
            try:
                inspect_store_image(rollback_raw, session_id)
            except SessionSpineStoreError as error:
                raise SessionSpineTransferError(f"Export rollback preimage does not replay: {error}") from None
        elif state in {"absence_marker", "not_required"}:
            if (rollback.get("file") is not None or rollback.get("sha256") is not None
                    or rollback.get("bytes") != 0 or rollback.get("preimage_exact") is not True):
                raise SessionSpineTransferError("Export rollback marker is invalid.")
        else:
            raise SessionSpineTransferError("Export rollback state is invalid.")

        plans = {
            "absent": ("READY_FOR_SEPARATE_REVIEW", "create_new", True, "absence_marker"),
            "identical": ("NO_CHANGE", "none", False, "not_required"),
            "occupied_different": ("BLOCKED", "none", False, "exact_preimage_captured"),
        }
        target_state = migration.get("target_state")
        if target_state not in plans:
            raise SessionSpineTransferError("Export migration target state is invalid.")
        status_value, operation, eligible, rollback_value = plans[target_state]
        if (migration.get("status"), migration.get("future_operation"), migration.get("eligible_for_future_apply_review"),
                migration.get("separate_checkpoint_required"), migration.get("overwrite_allowed"), migration.get("apply_installed"), state) != (
                    status_value, operation, eligible, True, False, False, rollback_value,
                ):
            raise SessionSpineTransferError("Export migration plan is internally inconsistent.")

        expected_names = {SOURCE_FILE, CANDIDATE_FILE, MANIFEST_FILE}
        if rollback_raw is not None:
            expected_names.add(ROLLBACK_FILE)
        with os.scandir(bundle) as entries:
            actual_names = {entry.name for entry in entries}
        if actual_names != expected_names:
            raise SessionSpineTransferError("Session Spine export contains missing or unexpected files.")
        return SessionSpineExportVerification(
            bundle_path=path,
            export_id=export_id,
            session_id=session_id,
            manifest_hash=manifest_hash,
            candidate_sha256=_digest_bytes(candidate_raw),
            rollback_state=state,
            rollback_sha256=None if rollback_raw is None else _digest_bytes(rollback_raw),
            migration_status=status_value,
            event_count=len(projection.events),
            surface_fingerprint=projection.surface.fingerprint,
            file_count=len(expected_names),
            _candidate_raw=candidate_raw,
            _rollback_raw=rollback_raw,
        )


@dataclass(frozen=True)
class SessionSpineRollbackPreview:
    session_id: str
    status: str
    reason: str
    future_operation: str
    current_target_sha256: str | None
    candidate_sha256: str
    rollback_sha256: str | None
    would_require_delete: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": ROLLBACK_SCHEMA,
            "read_only": True,
            "no_write": True,
            "rollback_installed": False,
            "session_id": self.session_id,
            "status": self.status,
            "reason": self.reason,
            "future_operation": self.future_operation,
            "current_target_sha256": self.current_target_sha256,
            "candidate_sha256": self.candidate_sha256,
            "rollback_sha256": self.rollback_sha256,
            "would_require_delete": self.would_require_delete,
            "separate_checkpoint_required": True,
            "rollback_performed": False,
        }


def preview_export_rollback(
    bundle_path: Path,
    *,
    current_target: bytes | None,
) -> SessionSpineRollbackPreview:
    """Compare current bytes with an export; never restore, delete, or rewrite them."""
    if current_target is not None and type(current_target) is not bytes:
        raise SessionSpineTransferError("Current target must be immutable bytes or absent.")
    if current_target is not None and len(current_target) > MAX_FILE_BYTES:
        raise SessionSpineTransferError("Current target exceeds the bounded P2a image size.")
    verified = verify_migration_export(bundle_path)
    current_hash = None if current_target is None else _digest_bytes(current_target)
    if verified.migration_status == "NO_CHANGE" and current_target == verified._candidate_raw:
        status_value, reason, operation, delete = (
            "NO_CHANGE", "The migration candidate already matched the target; no rollback is required.", "none", False,
        )
    elif verified.rollback_state == "exact_preimage_captured" and current_target == verified._rollback_raw:
        status_value, reason, operation, delete = (
            "ALREADY_RESTORED", "Current bytes already match the exact captured preimage.", "none", False,
        )
    elif verified.rollback_state == "absence_marker" and current_target is None:
        status_value, reason, operation, delete = (
            "ALREADY_RESTORED", "The target is absent, matching the captured pre-migration state.", "none", False,
        )
    elif current_target == verified._candidate_raw:
        if verified.rollback_state == "exact_preimage_captured":
            status_value, reason, operation, delete = (
                "READY_FOR_SEPARATE_REVIEW",
                "Current bytes exactly match the exported candidate and an exact preimage is available.",
                "restore_exact_preimage",
                False,
            )
        elif verified.rollback_state == "absence_marker":
            status_value, reason, operation, delete = (
                "READY_FOR_SEPARATE_REVIEW",
                "Current bytes exactly match the exported candidate; restoring absence would require a separately reviewed delete.",
                "restore_absence",
                True,
            )
        else:
            status_value, reason, operation, delete = (
                "NO_CHANGE", "The export recorded no migration change and no rollback payload.", "none", False,
            )
    else:
        status_value, reason, operation, delete = (
            "BLOCKED",
            "Current target bytes do not match the exported candidate or exact rollback preimage; no stale rollback may proceed.",
            "none",
            False,
        )
    return SessionSpineRollbackPreview(
        session_id=verified.session_id,
        status=status_value,
        reason=reason,
        future_operation=operation,
        current_target_sha256=current_hash,
        candidate_sha256=verified.candidate_sha256,
        rollback_sha256=verified.rollback_sha256,
        would_require_delete=delete,
    )
