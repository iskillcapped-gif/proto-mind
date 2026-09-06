"""Bounded, credential-free snapshots of Proto-Mind-owned private data."""
from __future__ import annotations

from contextlib import ExitStack, contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import tempfile
from uuid import uuid4

from proto_mind.memory_store import MemoryStore
from proto_mind.private_state_gate import GENERATION_FILE, RESTORE_MARKER, require_available

SCHEMA = "proto_mind.private_backup.v1"
MAX_FILE = 512 * 1024 * 1024
MAX_TOTAL = 2 * 1024 * 1024 * 1024
MAX_FILES = 50_000
MAX_MANIFEST = 16 * 1024 * 1024
NATIVE_ITEMS = {"conversations.json", "chat_objects", "history_backups", "preferences.json", "codex_threads.json",
                "integrations.json", "work_sessions", "project_memory", "learning_history", "session_spine_identity",
                "session_spine_store", "session_spine_intents"}
NATIVE_FILES = {"conversations.json", "preferences.json", "codex_threads.json", "integrations.json"}
EXCLUDED = "Входы и ключи сервисов, история провайдеров, исходные вложения, файлы рабочих проектов и другие резервные копии не входят в архив."


def encoded(value) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def decode(raw: bytes):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result: raise ValueError("Повторяющееся поле в копии.")
            result[key] = value
        return result
    def constant(_): raise ValueError("Недопустимое число в копии.")
    try: return json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)
    except (ValueError, RecursionError): raise ValueError("Не удалось прочитать структуру копии.") from None


def safe_directory(path: Path, *, create=False) -> None:
    if not path.is_absolute(): raise ValueError("Нужен абсолютный путь к папке.")
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current /= part
        if create and not os.path.lexists(current): current.mkdir(mode=0o700)
        mode = current.lstat().st_mode
        if not stat.S_ISDIR(mode): raise ValueError("Путь содержит ссылку или не является обычной папкой.")


def read_file(path: Path, limit=MAX_FILE) -> bytes:
    safe_directory(path.parent)
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, "rb") as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) or not 0 <= before.st_size <= limit:
            raise ValueError("Файл копии имеет неподдерживаемый тип или размер.")
        raw = stream.read(limit + 1)
        after, current = os.fstat(stream.fileno()), path.lstat()
        if stamp(before) != stamp(after) or stamp(before) != stamp(current) or len(raw) != before.st_size:
            raise ValueError("Файл изменился во время чтения. Повторите проверку.")
        return raw


def stamp(info) -> tuple:
    return (info.st_dev, info.st_ino, info.st_mode, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def sync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try: os.fsync(descriptor)
    finally: os.close(descriptor)


def atomic_file(path: Path, raw: bytes) -> None:
    safe_directory(path.parent, create=True)
    if os.path.lexists(path) and not stat.S_ISREG(path.lstat().st_mode):
        raise ValueError("Файл назначения не является обычным файлом.")
    descriptor, temporary = tempfile.mkstemp(prefix=".private-write-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(raw); stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, path)
        sync_directory(path.parent)
    finally:
        if os.path.exists(temporary): os.unlink(temporary)


def lock_file(path: Path) -> bool:
    return path.name.endswith(".lock") or path.name == ".spine-catalog.lock"


def logical_path(value: object) -> str:
    if not isinstance(value, str) or len(value) > 1500 or "\\" in value or "\x00" in value:
        raise ValueError("Некорректный путь в копии.")
    parts = value.split("/")
    if len(parts) < 2 or any(not p or p in {".", ".."} or p.startswith(".") for p in parts):
        raise ValueError("Копия содержит недопустимый путь.")
    if parts[0] not in {"core", "native", "core_exports", "exports", "logs"}:
        raise ValueError("Неизвестная область копии.")
    if parts[0] == "native" and parts[1] not in NATIVE_ITEMS:
        raise ValueError("Копия пытается заменить данные вне своей области.")
    if parts[0] == "native" and ((parts[1] in NATIVE_FILES) != (len(parts) == 2)):
        raise ValueError("Некорректная структура раздела копии.")
    if lock_file(Path(value)): raise ValueError("Копия не должна содержать рабочие блокировки.")
    return value


class PrivateBackup:
    def __init__(self, root: Path, state: Path):
        self.root, self.state = root.resolve(), state.resolve()
        self.roots = {"core": self.root / "proto_mind/data", "native": self.state,
                      "core_exports": self.root / "proto_mind/exports", "exports": self.root / "exports", "logs": self.root / "logs"}
        self.directory = self.state / "private_backups"
        self.marker = self.state / RESTORE_MARKER

    def path(self, name: str) -> Path:
        parts = PurePosixPath(logical_path(name)).parts
        return self.roots[parts[0]].joinpath(*parts[1:])

    def inventory(self) -> dict[str, tuple]:
        result = {}; size = 0
        for scope, root in self.roots.items():
            if not os.path.lexists(root): continue
            safe_directory(root)
            def walk(directory):
                nonlocal size
                for entry in sorted(directory.iterdir()):
                    if entry.name == ".DS_Store" or lock_file(entry) or entry.name in {RESTORE_MARKER, GENERATION_FILE}: continue
                    if scope == "native" and directory == root and entry.name not in NATIVE_ITEMS:
                        if entry.name.startswith("codex-") or entry.name in {"integration-bin", "private_backups"}: continue
                        raise ValueError("Неизвестный раздел локальных данных: " + entry.name)
                    if entry.name.startswith(".private-write-"): continue  # Interrupted atomic write; never authoritative data.
                    info = entry.lstat()
                    if stat.S_ISDIR(info.st_mode): walk(entry)
                    elif stat.S_ISREG(info.st_mode):
                        name = logical_path(scope + "/" + entry.relative_to(root).as_posix())
                        size += info.st_size
                        if info.st_size > MAX_FILE or size > MAX_TOTAL or len(result) >= MAX_FILES:
                            raise ValueError("Локальные данные превышают лимит копии: 2 ГиБ, 50 000 файлов, 512 МиБ на файл.")
                        result[name] = stamp(info)
                    else: raise ValueError("Копия не следует по ссылкам и не читает специальные файлы: " + entry.name)
            walk(root)
        return result

    @contextmanager
    def locks(self, *, write=False):
        # Core read/change/save stays in the same cooperative MemoryStore transaction.
        core = self.roots["core"]
        with ExitStack() as stack:
            memory = MemoryStore(core / "working_memory.json", core / "persistent_memory.json", initialize=False)
            stack.enter_context(memory.transaction())
            paths = {self.state / ".history.lock", self.state / ".integrations.lock", self.state / ".codex_threads.lock"}
            for name in NATIVE_ITEMS:
                base = self.state / name
                if base.is_dir() and not base.is_symlink():
                    paths.update(p for p in base.rglob("*") if lock_file(p))
                    if write and name in {"work_sessions", "project_memory", "learning_history"}: paths.add(base / ".writer.lock")
            for path in sorted(paths):
                if not os.path.lexists(path) and not write: continue
                safe_directory(path.parent, create=write)
                descriptor = os.open(path, os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK | (os.O_CREAT if write else 0), 0o600)
                stack.callback(os.close, descriptor)
                if not stat.S_ISREG(os.fstat(descriptor).st_mode): raise ValueError("Недопустимая блокировка данных.")
                try: fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError: raise ValueError("Данные сейчас используются другой копией Proto-Mind. Дождитесь завершения её работы.") from None
            yield

    def scan(self, *, destination: Path | None = None) -> dict:
        before = self.inventory()
        entries = []
        for name in sorted(before):
            raw = read_file(self.path(name))
            entries.append({"path": name, "size": len(raw), "sha256": digest(raw)})
            if destination is not None:
                atomic_file(destination / name, raw)
        if before != self.inventory(): raise ValueError("Данные изменились во время создания копии. Копия не опубликована.")
        return {"entries": entries, "fingerprint": digest(encoded(entries))}

    def export(self, destination: Path, *, locked=False, recovery=False) -> dict:
        if not recovery:
            require_available(self.state); require_available(self.roots["core"])
        destination = Path(destination)
        safe_directory(destination.parent)
        if os.path.lexists(destination): raise ValueError("По выбранному пути уже есть файл или папка. Выберите новое имя копии.")
        if any(destination == p or p in destination.parents for p in self.roots.values()) and self.directory not in destination.parents:
            raise ValueError("Сохраните копию вне папок исходных данных.")
        if not locked:
            with self.locks(): return self.export(destination, locked=True, recovery=recovery)
        stage = Path(tempfile.mkdtemp(prefix=".private-backup-", dir=destination.parent))
        try:
            snapshot = self.scan(destination=stage / "payload")
            value = {"schema": SCHEMA, "created_at": datetime.now(timezone.utc).isoformat(),
                     "project_root": str(self.root), "state_root": str(self.state), "recovery": recovery,
                     "entries": snapshot["entries"]}
            atomic_file(stage / "manifest.json", encoded(value))
            preview = self.verify(stage)
            if self.scan()["fingerprint"] != snapshot["fingerprint"]: raise ValueError("Исходные данные изменились перед публикацией копии.")
            # rename alone could replace an empty existing directory. Reserve the destination.
            destination.mkdir(mode=0o700)
            try: os.rename(stage, destination)
            except BaseException:
                destination.rmdir(); raise
            sync_directory(destination.parent)
            return {**preview, "path": str(destination)}
        finally:
            if stage.exists(): shutil.rmtree(stage)

    def verify(self, source: Path) -> dict:
        safe_directory(source)
        raw = read_file(source / "manifest.json", MAX_MANIFEST)
        value = decode(raw)
        if not isinstance(value, dict) or set(value) != {"schema", "created_at", "project_root", "state_root", "recovery", "entries"} or value["schema"] != SCHEMA:
            raise ValueError("Неизвестный формат полной копии.")
        if type(value["recovery"]) is not bool or any(not isinstance(value[key], str) or len(value[key]) > 4096 for key in ["created_at", "project_root", "state_root"]):
            raise ValueError("Некорректные сведения об установке в копии.")
        entries = value["entries"]
        if not isinstance(entries, list) or len(entries) > MAX_FILES: raise ValueError("Некорректный список файлов копии.")
        seen = set(); total = 0; counts = {}
        for entry in entries:
            if not isinstance(entry, dict) or set(entry) != {"path", "size", "sha256"}: raise ValueError("Некорректная запись файла копии.")
            name = logical_path(entry["path"])
            if name in seen or type(entry["size"]) is not int or not 0 <= entry["size"] <= MAX_FILE:
                raise ValueError("Повторяющийся или слишком большой файл копии.")
            seen.add(name); total += entry["size"]
            if total > MAX_TOTAL: raise ValueError("Копия превышает лимит 2 ГиБ.")
            body = read_file(source / "payload" / name)
            if len(body) != entry["size"] or digest(body) != entry["sha256"]: raise ValueError("Контрольная сумма файла копии не совпала: " + name)
            scope = name.split("/")[0]; counts[scope] = counts.get(scope, 0) + 1
        actual = set()
        payload = source / "payload"
        if payload.exists():
            safe_directory(payload)
            for path in payload.rglob("*"):
                info = path.lstat()
                if stat.S_ISREG(info.st_mode): actual.add(path.relative_to(payload).as_posix())
                elif not stat.S_ISDIR(info.st_mode): raise ValueError("Копия содержит ссылку или специальный файл.")
        if actual != seen: raise ValueError("Состав копии отличается от её списка файлов.")
        if raw != read_file(source / "manifest.json", MAX_MANIFEST): raise ValueError("Копия изменилась во время проверки.")
        return {"path": str(source), "sha256": digest(raw), "files": len(entries), "bytes": total,
                "created_at": value["created_at"], "counts": counts, "exclusions": EXCLUDED,
                "same_scope": value["project_root"] == str(self.root) and value["state_root"] == str(self.state)}

    def preview(self, source: Path) -> dict:
        require_available(self.state); require_available(self.roots["core"])
        self.check_source_location(source)
        result = self.verify(source)
        result["target_fingerprint"] = self.scan()["fingerprint"]
        return result

    def check_source_location(self, source: Path) -> None:
        if any(source == p or p in source.parents for p in self.roots.values()) and self.directory not in source.parents:
            raise ValueError("Откройте копию вне папок исходных данных.")
