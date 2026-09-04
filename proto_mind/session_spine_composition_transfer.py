"""Private evidence export for explicit multi-turn Session Spine fixtures.

P2d accepts only an already validated P2c composition preview and an explicit
private export root. It rederives the complete preview from its immutable
fixtures before writing a new run-once evidence bundle. Verification performs
the same P1 -> P2c -> P2a path independently from the exported source bytes.

This module does not discover personal history, infer fixture order, apply a
candidate to a store, restore a preimage, delete data, or compact a session.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path
import stat
from typing import Any

from proto_mind.session_spine_composition import (
    FORMAT_VERSION as COMPOSITION_FORMAT_VERSION,
    MAX_TURNS,
    MIN_TURNS,
    ORDER_SCHEMA,
    SCHEMA as COMPOSITION_SCHEMA,
    SessionSpineCompositionError,
    SessionSpineCompositionPreview,
    compose_native_fixtures,
)
from proto_mind.session_spine_store import (
    FORMAT_VERSION as STORE_FORMAT_VERSION,
    MAX_FILE_BYTES,
    STORE_SCHEMA,
)
from proto_mind.session_spine_transfer import (
    FIXTURE_SCHEMA,
    MAX_FIXTURE_BYTES,
    SessionSpineTransferError,
    _decode_line,
    _digest_bytes,
    _digest_value,
    _hash,
    _integer,
    _line,
    _object,
    _owner,
    _private_directory,
    _read_regular,
    _uuid,
    _write_new,
)


EXPORT_SCHEMA = "proto_mind.session_spine_composition_export.v1"
DOSSIER_SCHEMA = "proto_mind.session_spine_composition_parity_dossier.v1"
EXPORT_RECEIPT_SCHEMA = "proto_mind.session_spine_composition_export_receipt.v1"
EXPORT_VERIFICATION_SCHEMA = "proto_mind.session_spine_composition_export_verification.v1"
FORMAT_VERSION = 1
MAX_DOSSIER_BYTES = 512 * 1024
MAX_MANIFEST_BYTES = 256 * 1024
SOURCE_FILE_TEMPLATE = "source-{ordinal:03d}.native-session.json"
CANDIDATE_FILE = "candidate.session-spine.jsonl"
DOSSIER_FILE = "parity-dossier.json"
MANIFEST_FILE = "manifest.json"
BUNDLE_SUFFIX = ".session-spine-composition-export"


class SessionSpineCompositionTransferError(SessionSpineTransferError):
    """A multi-turn evidence export is incomplete, unsafe, or inconsistent."""


def _source_file(ordinal: int) -> str:
    return SOURCE_FILE_TEMPLATE.format(ordinal=ordinal)


def _boundaries() -> dict[str, bool]:
    return {
        "explicit_fixtures_only": True,
        "source_read_only": True,
        "export_only": True,
        "contains_exact_source_content": True,
        "safe_to_publish": False,
        "personal_archive_scanned": False,
        "archive_pairing_inferred": False,
        "ordering_inferred": False,
        "store_write_performed": False,
        "store_authority_changed": False,
        "apply_installed": False,
        "restore_installed": False,
        "delete_installed": False,
        "compaction_installed": False,
        "production_caller_installed": False,
        "task_success_inferred": False,
        "separate_checkpoint_required": True,
    }


def _source_rows(preview: SessionSpineCompositionPreview) -> list[dict[str, Any]]:
    return [
        {
            "ordinal": turn.ordinal,
            "file": _source_file(turn.ordinal),
            "schema": FIXTURE_SCHEMA,
            "sha256": turn.fixture_sha256,
            "bytes": turn.fixture_bytes,
        }
        for turn in preview.turns
    ]


def _dossier(
    preview: SessionSpineCompositionPreview,
    *,
    export_id: str,
    generated_ms: int,
) -> dict[str, Any]:
    sources = _source_rows(preview)
    turns: list[dict[str, Any]] = []
    for source, lineage in zip(sources, preview.turns, strict=True):
        row = lineage.to_dict()
        row["source_file"] = source["file"]
        turns.append(row)
    return {
        "schema": DOSSIER_SCHEMA,
        "format_version": FORMAT_VERSION,
        "export_id": export_id,
        "generated_ms": generated_ms,
        "session_id": preview.session_id,
        "owner_id": preview.owner_id,
        "ordering": {
            "mode": "caller_bound_sha256_manifest",
            "inferred": False,
            "manifest_schema": ORDER_SCHEMA,
            "manifest_sha256": preview.order_manifest_sha256,
            "source_files": [source["file"] for source in sources],
            "fixture_sha256": [source["sha256"] for source in sources],
        },
        "composition": {
            "preview_schema": COMPOSITION_SCHEMA,
            "preview_format_version": COMPOSITION_FORMAT_VERSION,
            "turn_count": len(preview.turns),
            "event_count": len(preview._events),
            "surface_nodes": list(preview.surface.nodes),
            "surface_fingerprint": preview.surface.fingerprint,
            "sequence_rebase_only": True,
            "source_identity_rewritten": False,
            "exact_event_parity": True,
            "visible_surface_parity": True,
            "full_candidate_replay": True,
            "task_success_inferred": False,
        },
        "turns": turns,
        "candidate": {
            "file": CANDIDATE_FILE,
            "store_schema": STORE_SCHEMA,
            "store_format_version": STORE_FORMAT_VERSION,
            "created_ms": preview.created_ms,
            "sha256": preview.candidate_sha256,
            "bytes": preview.candidate_bytes,
            "event_count": len(preview._events),
            "surface_fingerprint": preview.surface.fingerprint,
            "exact_replay_parity": True,
        },
        "checks": {
            "p1_revalidated": True,
            "order_manifest_recomputed": True,
            "source_byte_hashes_verified": True,
            "event_payload_parity_verified": True,
            "surface_parity_verified": True,
            "candidate_byte_parity_verified": True,
            "candidate_replay_verified": True,
        },
        "boundaries": _boundaries(),
    }


def _manifest(
    preview: SessionSpineCompositionPreview,
    *,
    export_id: str,
    generated_ms: int,
    dossier_raw: bytes,
) -> dict[str, Any]:
    value: dict[str, Any] = {
        "schema": EXPORT_SCHEMA,
        "format_version": FORMAT_VERSION,
        "export_id": export_id,
        "generated_ms": generated_ms,
        "session_id": preview.session_id,
        "owner_id": preview.owner_id,
        "ordering": {
            "schema": ORDER_SCHEMA,
            "mode": "caller_bound_sha256_manifest",
            "inferred": False,
            "manifest_sha256": preview.order_manifest_sha256,
        },
        "sources": _source_rows(preview),
        "candidate": {
            "file": CANDIDATE_FILE,
            "store_schema": STORE_SCHEMA,
            "store_format_version": STORE_FORMAT_VERSION,
            "created_ms": preview.created_ms,
            "sha256": preview.candidate_sha256,
            "bytes": preview.candidate_bytes,
            "event_count": len(preview._events),
            "surface_fingerprint": preview.surface.fingerprint,
        },
        "dossier": {
            "file": DOSSIER_FILE,
            "schema": DOSSIER_SCHEMA,
            "format_version": FORMAT_VERSION,
            "sha256": _digest_bytes(dossier_raw),
            "bytes": len(dossier_raw),
        },
        "boundaries": _boundaries(),
    }
    value["manifest_hash"] = _digest_value(value)
    return value


def _revalidate_preview(preview: SessionSpineCompositionPreview) -> SessionSpineCompositionPreview:
    if not isinstance(preview, SessionSpineCompositionPreview):
        raise SessionSpineCompositionTransferError(
            "Composition export requires a validated P2c preview."
        )
    try:
        rebuilt = compose_native_fixtures(
            preview._fixture_raws,
            expected_order=tuple(turn.fixture_sha256 for turn in preview.turns),
            expected_conversation_id=preview.session_id,
            owner_id=preview.owner_id,
        )
    except (SessionSpineCompositionError, SessionSpineTransferError) as error:
        raise SessionSpineCompositionTransferError(
            f"Composition preview cannot be independently revalidated: {error}"
        ) from None
    if rebuilt != preview:
        raise SessionSpineCompositionTransferError(
            "Composition preview metadata does not match its exact fixture bytes."
        )
    return rebuilt


@dataclass(frozen=True)
class SessionSpineCompositionExportReceipt:
    bundle_path: Path
    export_id: str
    session_id: str
    manifest_hash: str
    dossier_sha256: str
    candidate_sha256: str
    source_count: int
    file_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": EXPORT_RECEIPT_SCHEMA,
            "export_only": True,
            "safe_to_publish": False,
            "personal_archive_scanned": False,
            "ordering_inferred": False,
            "store_write_performed": False,
            "store_authority_changed": False,
            "bundle_path": str(self.bundle_path),
            "export_id": self.export_id,
            "session_id": self.session_id,
            "manifest_hash": self.manifest_hash,
            "dossier_sha256": self.dossier_sha256,
            "candidate_sha256": self.candidate_sha256,
            "source_count": self.source_count,
            "file_count": self.file_count,
        }


def _export_composition_preview(
    preview: SessionSpineCompositionPreview,
    *,
    export_root: Path,
    export_id: str,
    generated_ms: int,
) -> SessionSpineCompositionExportReceipt:
    rebuilt = _revalidate_preview(preview)
    identifier = _uuid(export_id, "Composition export ID")
    generated = _integer(generated_ms, "Composition export generation time")
    _owner(rebuilt.owner_id)
    dossier_raw = _line(_dossier(rebuilt, export_id=identifier, generated_ms=generated))
    manifest_raw = _line(_manifest(
        rebuilt,
        export_id=identifier,
        generated_ms=generated,
        dossier_raw=dossier_raw,
    ))
    if len(dossier_raw) > MAX_DOSSIER_BYTES or len(manifest_raw) > MAX_MANIFEST_BYTES:
        raise SessionSpineCompositionTransferError(
            "Composition evidence metadata exceeds its bounded export contract."
        )

    bundle_name = identifier + BUNDLE_SUFFIX
    with _private_directory(Path(export_root), create=True) as root:
        if root is None:
            raise SessionSpineCompositionTransferError(
                "Composition export root could not be created."
            )
        try:
            os.mkdir(bundle_name, mode=0o700, dir_fd=root)
            os.fsync(root)
            bundle = os.open(
                bundle_name,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                dir_fd=root,
            )
        except FileExistsError:
            raise SessionSpineCompositionTransferError(
                "Composition export ID already exists; no overwrite or retry was attempted."
            ) from None
        except OSError as error:
            raise SessionSpineCompositionTransferError(
                f"Composition export bundle could not be created safely: {error.strerror}."
            ) from None
        try:
            info = os.fstat(bundle)
            if not stat.S_ISDIR(info.st_mode) or info.st_mode & 0o077:
                raise SessionSpineCompositionTransferError(
                    "Composition export bundle is not a private directory."
                )
            for ordinal, raw in enumerate(rebuilt._fixture_raws):
                _write_new(bundle, _source_file(ordinal), raw, limit=MAX_FIXTURE_BYTES)
            _write_new(bundle, CANDIDATE_FILE, rebuilt._candidate_raw, limit=MAX_FILE_BYTES)
            _write_new(bundle, DOSSIER_FILE, dossier_raw, limit=MAX_DOSSIER_BYTES)
            # The manifest is the completion marker and is always written last.
            _write_new(bundle, MANIFEST_FILE, manifest_raw, limit=MAX_MANIFEST_BYTES)
            os.fsync(bundle)
        finally:
            os.close(bundle)

    path = Path(export_root) / bundle_name
    verification = _verify_composition_export(path)
    return SessionSpineCompositionExportReceipt(
        bundle_path=path,
        export_id=identifier,
        session_id=rebuilt.session_id,
        manifest_hash=verification.manifest_hash,
        dossier_sha256=verification.dossier_sha256,
        candidate_sha256=verification.candidate_sha256,
        source_count=verification.source_count,
        file_count=verification.file_count,
    )


def export_composition_preview(
    preview: SessionSpineCompositionPreview,
    *,
    export_root: Path,
    export_id: str,
    generated_ms: int,
) -> SessionSpineCompositionExportReceipt:
    """Create one private run-once P2d evidence bundle, never a live store."""
    try:
        return _export_composition_preview(
            preview,
            export_root=export_root,
            export_id=export_id,
            generated_ms=generated_ms,
        )
    except SessionSpineCompositionTransferError:
        raise
    except SessionSpineTransferError as error:
        raise SessionSpineCompositionTransferError(str(error)) from None


@dataclass(frozen=True)
class SessionSpineCompositionExportVerification:
    bundle_path: Path
    export_id: str
    session_id: str
    manifest_hash: str
    dossier_sha256: str
    candidate_sha256: str
    source_count: int
    event_count: int
    surface_fingerprint: str
    file_count: int
    _source_raws: tuple[bytes, ...] = field(repr=False)
    _candidate_raw: bytes = field(repr=False)
    _dossier_raw: bytes = field(repr=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": EXPORT_VERIFICATION_SCHEMA,
            "status": "VERIFIED",
            "read_only": True,
            "no_write": True,
            "safe_to_publish": False,
            "personal_archive_scanned": False,
            "ordering_inferred": False,
            "store_write_performed": False,
            "store_authority_changed": False,
            "bundle_path": str(self.bundle_path),
            "export_id": self.export_id,
            "session_id": self.session_id,
            "manifest_hash": self.manifest_hash,
            "dossier_sha256": self.dossier_sha256,
            "candidate_sha256": self.candidate_sha256,
            "source_count": self.source_count,
            "event_count": self.event_count,
            "surface_fingerprint": self.surface_fingerprint,
            "file_count": self.file_count,
            "exact_p1_p2c_p2a_parity": True,
            "dossier_parity": True,
        }


def _manifest_sources(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not MIN_TURNS <= len(value) <= MAX_TURNS:
        raise SessionSpineCompositionTransferError(
            "Composition export must describe two to 64 ordered source fixtures."
        )
    rows: list[dict[str, Any]] = []
    for ordinal, item in enumerate(value):
        row = _object(
            item,
            f"Composition source {ordinal}",
            {"ordinal", "file", "schema", "sha256", "bytes"},
        )
        expected_file = _source_file(ordinal)
        if (
            row.get("ordinal") != ordinal
            or row.get("file") != expected_file
            or row.get("schema") != FIXTURE_SCHEMA
        ):
            raise SessionSpineCompositionTransferError(
                "Composition source order or filename is not canonical."
            )
        _hash(row.get("sha256"), f"Composition source {ordinal} hash")
        size = _integer(row.get("bytes"), f"Composition source {ordinal} size")
        if not 0 < size <= MAX_FIXTURE_BYTES:
            raise SessionSpineCompositionTransferError(
                "Composition source size is outside the fixture boundary."
            )
        rows.append(row)
    if len({row["sha256"] for row in rows}) != len(rows):
        raise SessionSpineCompositionTransferError(
            "Composition source manifest contains duplicate fixture hashes."
        )
    return rows


def _verify_composition_export(
    bundle_path: Path,
) -> SessionSpineCompositionExportVerification:
    path = Path(bundle_path)
    with _private_directory(path) as bundle:
        if bundle is None:
            raise SessionSpineCompositionTransferError(
                "Composition export bundle does not exist."
            )
        manifest_raw = _read_regular(bundle, MANIFEST_FILE, limit=MAX_MANIFEST_BYTES)
        manifest = _decode_line(
            manifest_raw,
            "Composition export manifest",
            MAX_MANIFEST_BYTES,
        )
        fields = {
            "schema",
            "format_version",
            "export_id",
            "generated_ms",
            "session_id",
            "owner_id",
            "ordering",
            "sources",
            "candidate",
            "dossier",
            "boundaries",
            "manifest_hash",
        }
        if (
            set(manifest) != fields
            or manifest.get("schema") != EXPORT_SCHEMA
            or manifest.get("format_version") != FORMAT_VERSION
        ):
            raise SessionSpineCompositionTransferError(
                "Composition export manifest schema is not supported."
            )
        export_id = _uuid(manifest.get("export_id"), "Composition manifest export ID")
        if path.name != export_id + BUNDLE_SUFFIX:
            raise SessionSpineCompositionTransferError(
                "Composition export directory does not match its manifest ID."
            )
        generated_ms = _integer(
            manifest.get("generated_ms"),
            "Composition manifest generation time",
        )
        session_id = _uuid(manifest.get("session_id"), "Composition manifest session ID")
        owner_id = _owner(manifest.get("owner_id"))
        manifest_hash = _hash(manifest.get("manifest_hash"), "Composition manifest hash")
        unhashed = {key: value for key, value in manifest.items() if key != "manifest_hash"}
        if _digest_value(unhashed) != manifest_hash:
            raise SessionSpineCompositionTransferError(
                "Composition export manifest hash does not verify."
            )

        ordering = _object(
            manifest.get("ordering"),
            "Composition ordering",
            {"schema", "mode", "inferred", "manifest_sha256"},
        )
        if (
            ordering.get("schema") != ORDER_SCHEMA
            or ordering.get("mode") != "caller_bound_sha256_manifest"
            or ordering.get("inferred") is not False
        ):
            raise SessionSpineCompositionTransferError(
                "Composition export does not preserve caller-bound ordering."
            )
        _hash(ordering.get("manifest_sha256"), "Composition order manifest hash")
        source_rows = _manifest_sources(manifest.get("sources"))
        candidate = _object(
            manifest.get("candidate"),
            "Composition candidate",
            {
                "file",
                "store_schema",
                "store_format_version",
                "created_ms",
                "sha256",
                "bytes",
                "event_count",
                "surface_fingerprint",
            },
        )
        dossier = _object(
            manifest.get("dossier"),
            "Composition dossier",
            {"file", "schema", "format_version", "sha256", "bytes"},
        )
        boundaries = _object(
            manifest.get("boundaries"),
            "Composition boundaries",
            set(_boundaries()),
        )
        if boundaries != _boundaries():
            raise SessionSpineCompositionTransferError(
                "Composition export widens its evidence-only authority."
            )
        if (
            candidate.get("file") != CANDIDATE_FILE
            or candidate.get("store_schema") != STORE_SCHEMA
            or candidate.get("store_format_version") != STORE_FORMAT_VERSION
            or dossier.get("file") != DOSSIER_FILE
            or dossier.get("schema") != DOSSIER_SCHEMA
            or dossier.get("format_version") != FORMAT_VERSION
        ):
            raise SessionSpineCompositionTransferError(
                "Composition export uses an unexpected payload contract."
            )

        source_raws = tuple(
            _read_regular(bundle, row["file"], limit=MAX_FIXTURE_BYTES)
            for row in source_rows
        )
        for ordinal, (row, raw) in enumerate(zip(source_rows, source_raws, strict=True)):
            if row["sha256"] != _digest_bytes(raw) or row["bytes"] != len(raw):
                raise SessionSpineCompositionTransferError(
                    f"Composition source {ordinal} hash or size does not verify."
                )
        candidate_raw = _read_regular(bundle, CANDIDATE_FILE, limit=MAX_FILE_BYTES)
        dossier_raw = _read_regular(bundle, DOSSIER_FILE, limit=MAX_DOSSIER_BYTES)
        if (
            _hash(candidate.get("sha256"), "Composition candidate hash")
            != _digest_bytes(candidate_raw)
            or _integer(candidate.get("bytes"), "Composition candidate size")
            != len(candidate_raw)
            or _hash(dossier.get("sha256"), "Composition dossier hash")
            != _digest_bytes(dossier_raw)
            or _integer(dossier.get("bytes"), "Composition dossier size")
            != len(dossier_raw)
        ):
            raise SessionSpineCompositionTransferError(
                "Composition candidate or dossier hash or size does not verify."
            )
        dossier_value = _decode_line(
            dossier_raw,
            "Composition parity dossier",
            MAX_DOSSIER_BYTES,
        )

        try:
            rebuilt = compose_native_fixtures(
                source_raws,
                expected_order=tuple(row["sha256"] for row in source_rows),
                expected_conversation_id=session_id,
                owner_id=owner_id,
            )
        except (SessionSpineCompositionError, SessionSpineTransferError) as error:
            raise SessionSpineCompositionTransferError(
                f"Composition export source fixtures do not pass P1/P2c validation: {error}"
            ) from None
        expected_dossier = _dossier(
            rebuilt,
            export_id=export_id,
            generated_ms=generated_ms,
        )
        expected_dossier_raw = _line(expected_dossier)
        expected_manifest = _manifest(
            rebuilt,
            export_id=export_id,
            generated_ms=generated_ms,
            dossier_raw=expected_dossier_raw,
        )
        if dossier_value != expected_dossier or dossier_raw != expected_dossier_raw:
            raise SessionSpineCompositionTransferError(
                "Composition parity dossier does not match independently rebuilt evidence."
            )
        if manifest != expected_manifest or manifest_raw != _line(expected_manifest):
            raise SessionSpineCompositionTransferError(
                "Composition manifest does not match independently rebuilt evidence."
            )
        if candidate_raw != rebuilt._candidate_raw:
            raise SessionSpineCompositionTransferError(
                "Composition candidate does not preserve exact P1-to-P2c-to-P2a byte parity."
            )
        if (
            _integer(candidate.get("created_ms"), "Composition candidate creation time")
            != rebuilt.created_ms
            or _integer(candidate.get("event_count"), "Composition candidate event count")
            != len(rebuilt._events)
            or candidate.get("surface_fingerprint") != rebuilt.surface.fingerprint
        ):
            raise SessionSpineCompositionTransferError(
                "Composition candidate replay metadata does not verify."
            )

        expected_names = {
            *(row["file"] for row in source_rows),
            CANDIDATE_FILE,
            DOSSIER_FILE,
            MANIFEST_FILE,
        }
        with os.scandir(bundle) as entries:
            actual_names = {entry.name for entry in entries}
        if actual_names != expected_names:
            raise SessionSpineCompositionTransferError(
                "Composition export contains missing or unexpected files."
            )
        return SessionSpineCompositionExportVerification(
            bundle_path=path,
            export_id=export_id,
            session_id=session_id,
            manifest_hash=manifest_hash,
            dossier_sha256=_digest_bytes(dossier_raw),
            candidate_sha256=_digest_bytes(candidate_raw),
            source_count=len(source_raws),
            event_count=len(rebuilt._events),
            surface_fingerprint=rebuilt.surface.fingerprint,
            file_count=len(expected_names),
            _source_raws=source_raws,
            _candidate_raw=candidate_raw,
            _dossier_raw=dossier_raw,
        )


def verify_composition_export(
    bundle_path: Path,
) -> SessionSpineCompositionExportVerification:
    """Read and independently verify one complete P2d bundle without mutation."""
    try:
        return _verify_composition_export(bundle_path)
    except SessionSpineCompositionTransferError:
        raise
    except SessionSpineTransferError as error:
        raise SessionSpineCompositionTransferError(str(error)) from None
