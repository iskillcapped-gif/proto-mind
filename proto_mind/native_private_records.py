"""Bounded immutable private records. Reads never create; explicit saves never overwrite."""
from contextlib import contextmanager
from datetime import UTC, datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
from uuid import uuid4


MAX_BYTES = 512 * 1024
MAX_RECORDS = 200
NAMESPACES = frozenset({"learning_history", "project_memory"})
SCHEMA = "proto_mind.native_private_record.v1"
HASH = re.compile(r"[0-9a-f]{64}")


def encoded(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def digest(value) -> str:
    return hashlib.sha256(encoded(value)).hexdigest()


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON field in private evidence.")
        result[key] = value
    return result


def _constant(_):
    raise ValueError("Non-finite JSON in private evidence.")


class PrivateRecordStore:
    def __init__(self, state_dir: Path, namespace: str):
        if namespace not in NAMESPACES:
            raise ValueError("Unknown fixed private namespace.")
        self.directory = state_dir / namespace
        self.namespace = namespace

    @contextmanager
    def _directory(self, create=False):
        fd = None
        try:
            if not self.directory.is_absolute():
                raise ValueError("Private state requires an absolute path.")
            flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
            fd = os.open("/", flags)
            for part in self.directory.parts[1:]:
                if create:
                    try:
                        os.mkdir(part, mode=0o700, dir_fd=fd)
                    except FileExistsError:
                        pass
                try:
                    child = os.open(part, flags, dir_fd=fd)
                except FileNotFoundError:
                    if create:
                        raise
                    os.close(fd); fd = None
                    break
                os.close(fd); fd = child
            yield fd
        finally:
            if fd is not None:
                os.close(fd)

    def _read(self, directory: int, name: str, validate) -> dict:
        if not HASH.fullmatch(name.removesuffix(".json")) or not name.endswith(".json"):
            raise ValueError("Invalid private record filename.")
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_BYTES:
                raise ValueError("Private evidence is not a bounded regular file.")
            with os.fdopen(fd, "rb", closefd=False) as source:
                raw = source.read(MAX_BYTES + 1)
            if len(raw) > MAX_BYTES:
                raise ValueError("Private evidence exceeds its size limit.")
            record = json.loads(raw, object_pairs_hook=_object, parse_constant=_constant)
            if (not isinstance(record, dict) or set(record) != {"schema", "namespace", "id", "saved_at", "body", "record_hash"}
                    or record["schema"] != SCHEMA or record["namespace"] != self.namespace
                    or record["id"] + ".json" != name or not isinstance(record["body"], dict)
                    or digest(record["body"]) != record["id"]
                    or digest({key: value for key, value in record.items() if key != "record_hash"}) != record["record_hash"]):
                raise ValueError("Private evidence schema or SHA-256 does not verify.")
            if datetime.fromisoformat(record["saved_at"]).tzinfo is None:
                raise ValueError("Private evidence timestamp needs a timezone.")
            validate(record["body"])
            return record
        finally:
            os.close(fd)

    def _scan(self, directory, validate):
        if directory is None:
            return [], []
        rows, issues, names = [], [], []
        with os.scandir(directory) as entries:
            for entry in entries:
                if entry.name == ".writer.lock":
                    continue
                names.append(entry.name)
                if len(names) > MAX_RECORDS:
                    return [], ["Private record limit exceeded. No partial history or automatic cleanup."]
        for name in sorted(names):
            try:
                rows.append(self._read(directory, name, validate))
            except (OSError, ValueError, TypeError, KeyError, RecursionError, OverflowError):
                issues.append(f"Unreadable or invalid private record: {name[:100]}. No repair attempted.")
        return rows, issues

    def scan(self, validate):
        try:
            with self._directory() as directory:
                return self._scan(directory, validate)
        except (OSError, ValueError):
            return [], ["Private evidence directory is unavailable, unsafe or unreadable. No initialization/repair."]

    def get(self, identifier: str, validate):
        if not isinstance(identifier, str) or not HASH.fullmatch(identifier):
            raise ValueError("Select an exact saved evidence ID.")
        with self._directory() as directory:
            if directory is None:
                raise ValueError("Private evidence was not saved.")
            return self._read(directory, identifier + ".json", validate)

    def save(self, body: dict, validate, *, expected_snapshot: str | None = None) -> tuple[dict, bool]:
        validate(body)
        record = {"schema": SCHEMA, "namespace": self.namespace, "id": digest(body),
                  "saved_at": datetime.now(UTC).isoformat(), "body": body}
        record["record_hash"] = digest(record)
        payload = encoded(record)
        if len(payload) > MAX_BYTES:
            raise ValueError("Private evidence exceeds the 512 KiB limit. Nothing saved.")
        with self._directory(create=True) as directory:
            lock = os.open(".writer.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600, dir_fd=directory)
            try:
                if not stat.S_ISREG(os.fstat(lock).st_mode):
                    raise ValueError("Unsafe private writer lock.")
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                rows, issues = self._scan(directory, validate)
                if issues:
                    raise ValueError("Private storage needs inspection before saving: " + "; ".join(issues))
                existing = next((row for row in rows if row["id"] == record["id"]), None)
                if existing is not None:
                    return existing, False
                if expected_snapshot is not None and snapshot_hash(rows) != expected_snapshot:
                    raise ValueError("Private records changed after preview. Review the current state; nothing saved.")
                if len(rows) >= MAX_RECORDS:
                    raise ValueError("Private record limit reached. No cleanup or overwrite.")
                temporary = ".pending-" + uuid4().hex
                fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory)
                inode = os.fstat(fd).st_ino
                try:
                    with os.fdopen(fd, "wb", closefd=False) as target:
                        target.write(payload); target.flush(); os.fsync(fd)
                    # Linking is atomic and cannot replace a concurrently created destination.
                    os.link(temporary, record["id"] + ".json", src_dir_fd=directory, dst_dir_fd=directory, follow_symlinks=False)
                    os.fsync(directory)
                    if self._read(directory, record["id"] + ".json", validate) != record:
                        raise ValueError("Saved evidence readback differs. Inspect it; no automatic retry.")
                    return record, True
                finally:
                    os.close(fd)
                    try:
                        if os.stat(temporary, dir_fd=directory, follow_symlinks=False).st_ino == inode:
                            os.unlink(temporary, dir_fd=directory)
                    except FileNotFoundError:
                        pass
            finally:
                os.close(lock)


def snapshot_hash(records: list[dict]) -> str:
    return digest(sorted((record["id"], record["record_hash"]) for record in records))
