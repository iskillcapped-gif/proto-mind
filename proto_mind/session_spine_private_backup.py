"""Explicit, read-only Session Spine audit for one private Native backup.

P2f opens only the absolute archive path supplied by its caller and requires an
independently supplied SHA-256. It never discovers backups, extracts files to
disk, writes a report, calls a provider, or changes Session Spine authority.
"""
from __future__ import annotations

from collections import Counter
from io import BytesIO
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import tarfile
from typing import Any
from uuid import UUID

from proto_mind.native_work_sessions import MAX_RECORD_BYTES, MAX_RUNS
from proto_mind.session_spine_archive_copy import (
    MAX_HISTORY_BYTES,
    audit_native_archive_copy,
)


SCHEMA = "proto_mind.session_spine_private_backup_audit.v1"
FORMAT_VERSION = 1
MAX_ARCHIVE_BYTES = 200 * 1024 * 1024
MAX_ARCHIVE_MEMBERS = MAX_RUNS * 2 + 10
MAX_IGNORED_METADATA_BYTES = 8 * 1024 * 1024
MAX_APPLEDOUBLE_BYTES = 64 * 1024
HASH = re.compile(r"[0-9a-f]{64}\Z")
RUN_NAME = re.compile(
    r"work_sessions/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-"
    r"[0-9a-f]{4}-[0-9a-f]{12})\.json\Z"
)
ROOT_METADATA = frozenset({"codex_threads.json", "preferences.json"})
IGNORED_FILES = ROOT_METADATA | {"work_sessions/.writer.lock"}
ALLOWED_PAX_KEYS = frozenset({
    "mtime",
    "LIBARCHIVE.xattr.com.apple.provenance",
    "SCHILY.xattr.com.apple.provenance",
})


class SessionSpinePrivateBackupError(RuntimeError):
    """The private backup cannot be audited within the closed P2f contract."""


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
        raise SessionSpinePrivateBackupError("Private-backup evidence is not canonical JSON.") from None


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _digest(value: object) -> str:
    if not isinstance(value, str) or not HASH.fullmatch(value):
        raise SessionSpinePrivateBackupError("Expected archive digest must be lowercase SHA-256.")
    return value


def _read_exact_archive(path: Path, expected_sha256: str) -> tuple[bytes, os.stat_result]:
    if not isinstance(path, Path) or not path.is_absolute() or not path.name.endswith(".tar.gz"):
        raise SessionSpinePrivateBackupError("Choose one explicit absolute .tar.gz backup path.")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError:
        raise SessionSpinePrivateBackupError("The explicit backup cannot be opened as a regular file.") from None
    try:
        try:
            before = os.fstat(descriptor)
            if not stat.S_ISREG(before.st_mode) or before.st_size <= 0 or before.st_size > MAX_ARCHIVE_BYTES:
                raise SessionSpinePrivateBackupError("The explicit backup is not a bounded regular file.")
            chunks: list[bytes] = []
            remaining = before.st_size + 1
            while remaining:
                chunk = os.read(descriptor, min(1024 * 1024, remaining))
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            raw = b"".join(chunks)
            after = os.fstat(descriptor)
        except OSError:
            raise SessionSpinePrivateBackupError("The explicit backup could not be read stably.") from None
    finally:
        os.close(descriptor)
    stable = (
        before.st_dev == after.st_dev
        and before.st_ino == after.st_ino
        and before.st_size == after.st_size == len(raw)
        and before.st_mtime_ns == after.st_mtime_ns
    )
    if not stable:
        raise SessionSpinePrivateBackupError("The backup changed while it was being read.")
    if _sha256(raw) != expected_sha256:
        raise SessionSpinePrivateBackupError("The backup bytes do not match the expected SHA-256.")
    return raw, after


def _validate_uuid(value: str) -> None:
    try:
        normalized = str(UUID(value))
    except (ValueError, AttributeError):
        raise SessionSpinePrivateBackupError("A work-session member has an invalid UUID filename.") from None
    if normalized != value:
        raise SessionSpinePrivateBackupError("Work-session member UUID filenames must be canonical lowercase text.")


def _member_kind(name: str) -> tuple[str, str | None]:
    path = PurePosixPath(name)
    if path.is_absolute() or not path.parts or any(part in {"", ".", ".."} for part in path.parts):
        raise SessionSpinePrivateBackupError("Backup contains an unsafe member path.")
    if "\\" in name or path.as_posix() != name:
        raise SessionSpinePrivateBackupError("Backup member paths must use canonical POSIX text.")
    if name == "conversations.json":
        return "history", None
    if name == "work_sessions":
        return "directory", None
    if name in IGNORED_FILES:
        return "ignored_metadata", None
    match = RUN_NAME.fullmatch(name)
    if match:
        _validate_uuid(match.group(1))
        return "work_session", match.group(1) + ".json"
    last = path.name
    if last.startswith("._") and len(last) > 2:
        base_name = last[2:]
        base = PurePosixPath(*path.parts[:-1], base_name).as_posix()
        base_kind, _ = _member_kind(base)
        if base_kind in {"history", "directory", "ignored_metadata", "work_session"}:
            return "appledouble", None
    raise SessionSpinePrivateBackupError("Backup contains a member outside the credential-free P2f allowlist.")


def _read_member(archive: tarfile.TarFile, member: tarfile.TarInfo, maximum: int) -> bytes:
    if member.size <= 0 or member.size > maximum:
        raise SessionSpinePrivateBackupError("Backup contains an empty or oversized audited member.")
    source = archive.extractfile(member)
    if source is None:
        raise SessionSpinePrivateBackupError("Backup member bytes are unavailable.")
    raw = source.read(maximum + 1)
    if len(raw) != member.size or len(raw) > maximum:
        raise SessionSpinePrivateBackupError("Backup member size does not match its bounded payload.")
    return raw


def _read_members(raw: bytes) -> tuple[bytes, dict[str, bytes], dict[str, Any]]:
    history: bytes | None = None
    work_sessions: dict[str, bytes] = {}
    seen: set[str] = set()
    kind_counts: Counter[str] = Counter()
    broad_member_modes = 0
    member_count = 0
    try:
        with tarfile.open(fileobj=BytesIO(raw), mode="r:gz") as archive:
            if archive.pax_headers:
                raise SessionSpinePrivateBackupError("Backup contains unsupported global PAX metadata.")
            for member in archive:
                member_count += 1
                if member_count > MAX_ARCHIVE_MEMBERS:
                    raise SessionSpinePrivateBackupError("Backup contains too many members for P2f.")
                if member.name in seen:
                    raise SessionSpinePrivateBackupError("Backup contains duplicate member names.")
                seen.add(member.name)
                if (
                    set(member.pax_headers) - ALLOWED_PAX_KEYS
                    or any(
                        not isinstance(value, str) or len(key) > 128 or len(value) > 4096
                        for key, value in member.pax_headers.items()
                    )
                ):
                    raise SessionSpinePrivateBackupError("Backup contains unsupported member metadata.")
                kind, run_name = _member_kind(member.name)
                kind_counts[kind] += 1
                if member.mode & 0o077:
                    broad_member_modes += 1
                if kind == "directory":
                    if not member.isdir() or member.size != 0:
                        raise SessionSpinePrivateBackupError("The work-session container is not a directory marker.")
                    continue
                if not member.isreg() or member.issparse():
                    raise SessionSpinePrivateBackupError("Backup contains a link, sparse file, or special member.")
                if member.size < 0:
                    raise SessionSpinePrivateBackupError("Backup contains an invalid member size.")
                if kind == "appledouble":
                    if member.size > MAX_APPLEDOUBLE_BYTES:
                        raise SessionSpinePrivateBackupError("AppleDouble metadata exceeds the P2f bound.")
                    continue
                if kind == "ignored_metadata":
                    if member.size > MAX_IGNORED_METADATA_BYTES:
                        raise SessionSpinePrivateBackupError("Ignored Native metadata exceeds the P2f bound.")
                    continue
                if kind == "history":
                    if history is not None:
                        raise SessionSpinePrivateBackupError("Backup contains more than one Native history member.")
                    history = _read_member(archive, member, MAX_HISTORY_BYTES - 1)
                    continue
                if run_name is None or len(work_sessions) >= MAX_RUNS:
                    raise SessionSpinePrivateBackupError("Backup exceeds the work-session record bound.")
                work_sessions[run_name] = _read_member(archive, member, MAX_RECORD_BYTES)
    except SessionSpinePrivateBackupError:
        raise
    except (tarfile.TarError, EOFError, OSError, ValueError, RecursionError):
        raise SessionSpinePrivateBackupError("The explicit backup is not a readable bounded gzip tar archive.") from None
    if history is None or kind_counts["directory"] != 1:
        raise SessionSpinePrivateBackupError("Backup must contain one history file and one work-session directory marker.")
    metadata = {
        "member_count": member_count,
        "kind_counts": dict(sorted(kind_counts.items())),
        "ignored_member_count": kind_counts["ignored_metadata"] + kind_counts["appledouble"],
        "broad_member_mode_count": broad_member_modes,
        "closed_allowlist_verified": True,
        "credential_named_member_detected": False,
    }
    return history, dict(sorted(work_sessions.items())), metadata


def audit_native_private_backup(
    archive_path: Path,
    *,
    expected_archive_sha256: str,
) -> dict[str, Any]:
    """Audit one explicitly authorized private backup without extracting it."""
    expected = _digest(expected_archive_sha256)
    archive_raw, archive_stat = _read_exact_archive(archive_path, expected)
    history, work_sessions, member_metadata = _read_members(archive_raw)
    history_sha256 = _sha256(history)
    manifest = tuple((name, _sha256(payload)) for name, payload in work_sessions.items())
    compatibility = audit_native_archive_copy(
        history,
        work_sessions,
        expected_history_sha256=history_sha256,
        expected_work_session_manifest=manifest,
    )

    findings: list[dict[str, str]] = []
    archive_owner_only = archive_stat.st_mode & 0o077 == 0
    if not archive_owner_only:
        findings.append({
            "category": "archive_file_mode",
            "severity": "WARN",
            "reason": "private_backup_is_not_owner_only",
        })
    if member_metadata["broad_member_mode_count"]:
        findings.append({
            "category": "archived_member_mode",
            "severity": "WARN",
            "reason": "one_or_more_archived_members_are_not_owner_only",
        })
    severity_counts = Counter(item["severity"] for item in findings)
    status = (
        "ERROR" if compatibility["status"] == "ERROR"
        else "WARN" if compatibility["status"] == "WARN" or severity_counts["WARN"]
        else "OK"
    )
    report: dict[str, Any] = {
        "schema": SCHEMA,
        "format_version": FORMAT_VERSION,
        "status": status,
        "read_only": True,
        "no_write": True,
        "no_disk_extraction": True,
        "report_content_free": True,
        "input": {
            "archive_kind": "explicit_private_native_tar_gzip_copy",
            "archive_sha256": expected,
            "archive_bytes": len(archive_raw),
            "archive_mode": f"{stat.S_IMODE(archive_stat.st_mode):04o}",
            "archive_owner_only": archive_owner_only,
            "member_count": member_metadata["member_count"],
            "kind_counts": member_metadata["kind_counts"],
            "ignored_member_count": member_metadata["ignored_member_count"],
            "work_session_count": len(work_sessions),
            "history_sha256": history_sha256,
            "work_session_manifest_sha256": _sha256(_canonical(manifest)),
        },
        "checks": {
            "explicit_absolute_path_required": True,
            "archive_byte_sha256_verified": True,
            "archive_stable_during_read": True,
            "final_path_symlink_refused": True,
            "closed_member_allowlist_verified": member_metadata["closed_allowlist_verified"],
            "credential_named_member_detected": member_metadata["credential_named_member_detected"],
            "duplicate_members_refused": True,
            "links_sparse_and_special_members_refused": True,
            "macos_appledouble_metadata_ignored": True,
            "p2e_revalidation_status": compatibility["status"],
        },
        "findings": findings,
        "compatibility": compatibility,
        "boundaries": {
            "backup_discovery_performed": False,
            "live_native_state_opened": False,
            "archive_extracted_to_disk": False,
            "source_bytes_returned": False,
            "source_text_returned": False,
            "report_written": False,
            "migration_performed": False,
            "repair_performed": False,
            "permission_changed": False,
            "model_call_performed": False,
            "provider_call_performed": False,
            "command_executed": False,
            "tool_replayed": False,
            "production_caller_installed": False,
            "authoritative_writer_installed": False,
        },
        "authority": {
            "backup_member_set_closed": True,
            "live_source_completeness_verified": False,
            "operator_authorization_verified_by_code": False,
            "compatibility_evidence_available": compatibility["status"] != "ERROR",
            "ready_for_authoritative_writer": False,
            "separate_migration_design_required": True,
        },
    }
    report["audit_hash"] = _sha256(_canonical(report))
    return report
