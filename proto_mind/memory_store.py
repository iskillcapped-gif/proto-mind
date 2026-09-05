from __future__ import annotations

from contextlib import contextmanager, ExitStack
import fcntl
import json
import os
from pathlib import Path
from threading import RLock
from uuid import uuid4
from weakref import WeakValueDictionary

from proto_mind.models import MemoryRecord
from proto_mind.private_state_gate import RESTORE_WRITER, generation, require_available


class _MemoryFileLock:
    """Reentrant within a thread, shared by store instances and processes."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.thread_lock = RLock()
        self.depth = 0
        self.descriptor: int | None = None

    @contextmanager
    def acquire(self):
        owner_pid = os.getpid()
        with self.thread_lock:
            if self.depth == 0:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                descriptor = os.open(self.path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
                self.descriptor = descriptor
                try:
                    fcntl.flock(descriptor, fcntl.LOCK_EX)
                except BaseException:
                    os.close(descriptor)
                    self.descriptor = None
                    raise
            self.depth += 1
            try:
                yield
            finally:
                # A forked child already closed inherited descriptors and must
                # not release the parent's context again while unwinding it.
                if os.getpid() == owner_pid:
                    self.depth -= 1
                    if self.depth == 0:
                        os.close(self.descriptor)  # Closing releases flock, including on exceptions.
                        self.descriptor = None


_LOCKS: WeakValueDictionary[str, _MemoryFileLock] = WeakValueDictionary()
_REGISTRY_LOCK = RLock()


def _reset_locks_after_fork() -> None:
    global _LOCKS, _REGISTRY_LOCK
    for lock in list(_LOCKS.values()):
        if lock.descriptor is not None:
            os.close(lock.descriptor)
    _LOCKS = WeakValueDictionary()
    _REGISTRY_LOCK = RLock()


os.register_at_fork(after_in_child=_reset_locks_after_fork)


class MemoryStore:
    def __init__(
        self,
        working_path: str | Path,
        persistent_path: str | Path,
        *, initialize: bool = True,
    ) -> None:
        self.working_path = Path(working_path)
        self.persistent_path = Path(persistent_path)
        require_available(self.working_path.parent)
        self._generation = generation(self.working_path.parent)
        if initialize:
            self._ensure_files()

    def _ensure_files(self) -> None:
        if not all(path.exists() for path in (self.working_path, self.persistent_path)):
            with self.transaction():
                for path in (self.working_path, self.persistent_path):
                    if not path.exists():
                        self._save_records(path, [])

    @contextmanager
    def transaction(self):
        """Serialize a complete read/modify/write operation across both layers.

        Reads alone never create files. Full-list save methods replace a layer;
        callers deriving a replacement from a read must hold this context for
        both operations. This is mutual exclusion, not multi-file crash rollback.
        Sidecar locks must remain in place: replacing/unlinking a held lock would
        let another process lock a different inode.
        """
        self._check_private_state()
        paths = sorted({str(path.resolve()) for path in (self.working_path, self.persistent_path)})
        with _REGISTRY_LOCK:
            locks = []
            for path in paths:
                lock = _LOCKS.get(path)
                if lock is None:
                    target = Path(path)
                    lock = _MemoryFileLock(target.with_name(f".{target.name}.lock"))
                    _LOCKS[path] = lock
                locks.append(lock)
        with ExitStack() as stack:
            for lock in locks:
                stack.enter_context(lock.acquire())
            self._check_private_state()
            yield

    def load_working_memory(self) -> list[MemoryRecord]:
        return self._load_records(self.working_path)

    def load_persistent_memory(self) -> list[MemoryRecord]:
        return self._load_records(self.persistent_path)

    def save_working_memory(self, records: list[MemoryRecord]) -> None:
        with self.transaction():
            self._save_records(self.working_path, records)

    def save_persistent_memory(self, records: list[MemoryRecord]) -> None:
        with self.transaction():
            self._save_records(self.persistent_path, records)

    def add_working_record(self, record: MemoryRecord) -> None:
        with self.transaction():
            records = self.load_working_memory()
            records.append(record)
            self.save_working_memory(records)

    def add_persistent_record(self, record: MemoryRecord) -> None:
        with self.transaction():
            records = self.load_persistent_memory()
            records.append(record)
            self.save_persistent_memory(records)

    def upsert_working_record(self, record: MemoryRecord) -> None:
        with self.transaction():
            records = self.load_working_memory()
            self._upsert(records, record)
            self.save_working_memory(records)

    def upsert_persistent_record(self, record: MemoryRecord) -> None:
        with self.transaction():
            records = self.load_persistent_memory()
            self._upsert(records, record)
            self.save_persistent_memory(records)

    def delete_working_record(self, record_id: str) -> None:
        with self.transaction():
            records = [record for record in self.load_working_memory() if record.id != record_id]
            self.save_working_memory(records)

    def delete_persistent_record(self, record_id: str) -> None:
        with self.transaction():
            records = [record for record in self.load_persistent_memory() if record.id != record_id]
            self.save_persistent_memory(records)

    def _load_records(self, path: Path) -> list[MemoryRecord]:
        self._check_private_state()
        raw = json.loads(path.read_text(encoding="utf-8"))
        return [MemoryRecord.from_dict(item) for item in raw]

    def _check_private_state(self) -> None:
        require_available(self.working_path.parent)
        if not RESTORE_WRITER.get() and generation(self.working_path.parent) != getattr(self, "_generation", None):
            raise ValueError("Локальные данные восстановлены другой копией приложения. Перезапустите Proto-Mind перед продолжением.")

    def _save_records(self, path: Path, records: list[MemoryRecord]) -> None:
        payload = [record.to_dict() for record in records]
        temp_path = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
        # Exclusive creation preserves an existing file even if a name collides.
        with temp_path.open("x", encoding="utf-8") as stream:
            try:
                json.dump(payload, stream, indent=2, allow_nan=False)
                stream.flush()
                os.fsync(stream.fileno())
                temp_path.replace(path)
            finally:
                temp_path.unlink(missing_ok=True)

    @staticmethod
    def _upsert(records: list[MemoryRecord], candidate: MemoryRecord) -> None:
        for index, record in enumerate(records):
            if record.id == candidate.id:
                records[index] = candidate
                return
        records.append(candidate)
