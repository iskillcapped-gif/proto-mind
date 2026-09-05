"""Explicit, restartable restore with immutable before-images and a durable plan.

Files publish atomically one at a time. This is recoverable multi-store work,
not a claim that several directories change atomically together.
"""
from __future__ import annotations

from pathlib import Path
import os
import re
import stat
from uuid import UUID, uuid4

from proto_mind.native_private_backup import (PrivateBackup, MAX_MANIFEST, atomic_file, decode, digest, encoded,
                                             logical_path, read_file, safe_directory, sync_directory)
from proto_mind.private_state_gate import GENERATION_FILE, RESTORE_MARKER, RESTORE_WRITER, require_available

PLAN_SCHEMA = "proto_mind.private_restore.v1"
HASH = re.compile(r"[0-9a-f]{64}\Z")
METHODS = {"private_backup_status", "private_backup_create", "private_backup_preview", "private_backup_restore",
           "private_backup_resume", "private_backup_rollback"}


def without_authority(name: str, raw: bytes | None) -> bytes | None:
    if raw is None or name == "native/codex_threads.json": return None
    if name in {"native/preferences.json", "native/integrations.json", "core/context_injection.json"}:
        value = decode(raw)
        if not isinstance(value, dict): raise ValueError("Настройки в копии имеют неизвестный формат.")
        if name.endswith("preferences.json"):
            if value.get("version") not in {1, 2}: raise ValueError("Версия настроек в копии не поддерживается.")
            value["cloudProcessingAllowed"] = False
        elif name.endswith("integrations.json"):
            if value.get("schema") != "proto_mind.native_integrations.v1": raise ValueError("Неизвестные настройки подключений в копии.")
            value["github"] = None
        else: value["enabled"] = False
        return encoded(value)
    return raw


class PrivateRestore(PrivateBackup):
    def __init__(self, root: Path, state: Path, *, fault=lambda _: None):
        super().__init__(root, state)
        self.fault = fault

    def _operation(self, identifier: str) -> Path:
        try:
            if str(UUID(identifier)) != identifier: raise ValueError()
        except (ValueError, TypeError, AttributeError): raise ValueError("Недопустимый идентификатор восстановления.") from None
        return self.directory / ("restore-" + identifier)

    def _marker(self, identifier: str, direction: str, plan_hash: str) -> dict:
        return {"schema": PLAN_SCHEMA, "id": identifier, "direction": direction, "plan_sha256": plan_hash}

    def _load_plan(self) -> tuple[dict, dict, Path]:
        marker = decode(read_file(self.marker, 8192))
        if not isinstance(marker, dict) or set(marker) != {"schema", "id", "direction", "plan_sha256"} or marker["schema"] != PLAN_SCHEMA or marker["direction"] not in {"restore", "rollback"}:
            raise ValueError("Журнал восстановления повреждён. Автоматических изменений не было.")
        operation = self._operation(marker["id"])
        raw = read_file(operation / "plan.json", MAX_MANIFEST)
        if digest(raw) != marker["plan_sha256"]: raise ValueError("План восстановления изменился. Данные сохранены для ручной проверки.")
        plan = decode(raw)
        if not isinstance(plan, dict) or set(plan) != {"schema", "id", "root", "state", "window", "files"} or plan["schema"] != PLAN_SCHEMA or plan["id"] != marker["id"] or plan["root"] != str(self.root) or plan["state"] != str(self.state):
            raise ValueError("План восстановления относится к другой установке.")
        files = plan["files"]
        if not isinstance(files, list) or len(files) > 50_000: raise ValueError("Некорректный план восстановления.")
        seen = set()
        for item in files:
            if not isinstance(item, dict) or set(item) != {"path", "before", "restore", "rollback"}: raise ValueError("Некорректный файл плана.")
            name = logical_path(item["path"])
            if name in seen: raise ValueError("Повторяющийся путь в плане восстановления.")
            seen.add(name)
            for key in ["before", "restore", "rollback"]:
                value = item[key]
                if value is not None and (not isinstance(value, str) or not HASH.fullmatch(value)): raise ValueError("Некорректная контрольная сумма плана.")
            for key in ["restore", "rollback"]:
                if item[key] is not None and digest(read_file(operation / "blobs" / item[key])) != item[key]:
                    raise ValueError("Сохранённые данные восстановления изменились.")
        return marker, plan, operation

    def status(self) -> dict:
        result = {"pending": os.path.lexists(self.marker), "copies": [], "error": ""}
        if result["pending"]:
            try:
                marker, plan, operation = self._load_plan()
                result.update(id=marker["id"], direction=marker["direction"], files=len(plan["files"]), recovery_path=str(operation / "before.protomind-backup"))
            except (ValueError, OSError) as error: result["error"] = str(error)
        if self.directory.exists():
            safe_directory(self.directory)
            candidates = list(self.directory.glob("*.protomind-backup")) + list(self.directory.glob("restore-*/before.protomind-backup"))
            for path in sorted(candidates, key=lambda p: p.lstat().st_mtime_ns, reverse=True)[:20]:
                result["copies"].append({"path": str(path), "name": path.parent.name if path.name.startswith("before") else path.name})
        return result

    def _blob(self, directory: Path, raw: bytes | None) -> str | None:
        if raw is None: return None
        key = digest(raw)
        path = directory / "blobs" / key
        if path.exists():
            if read_file(path) != raw: raise ValueError("Сохранённый образ файла изменился.")
        else: atomic_file(path, raw)
        return key

    def _entries(self, archive: Path) -> dict:
        return {row["path"]: row for row in decode(read_file(archive / "manifest.json", MAX_MANIFEST))["entries"]}

    def restore(self, source: Path, expected_hash: str, expected_target: str, window_name: str) -> dict:
        require_available(self.state); require_available(self.roots["core"])
        self.check_source_location(source)
        # Swift preserves the current in-window draft before this RPC. The copy
        # remains usable with the ordinary dialog recovery UI, including after a crash.
        if not isinstance(window_name, str) or not re.fullmatch(r"window-[0-9A-Fa-f-]{36}\.protomind-history", window_name):
            raise ValueError("Сначала сохраните текущие сообщения из окна.")
        window = self.directory / window_name
        raw = read_file(window / "conversations.json", MAX_MANIFEST)
        if decode(raw).get("version") != 6: raise ValueError("Копия сообщений из окна не проверена.")
        with self.locks(write=True):
            preview = self.verify(source)
            if not preview["same_scope"]: raise ValueError("Эта копия относится к другим путям установки. Автоматический перенос связей не выполняется.")
            if preview["sha256"] != expected_hash or self.scan()["fingerprint"] != expected_target:
                raise ValueError("Копия или текущие данные изменились после просмотра. Проверьте копию снова.")
            rows = self._entries(source)
            if "native/conversations.json" not in rows: raise ValueError("В выбранной копии нет списка диалогов.")
            identifier = str(uuid4()); operation = self._operation(identifier)
            safe_directory(operation, create=True)
            self.export(operation / "before.protomind-backup", locked=True, recovery=True)
            previous = self._entries(operation / "before.protomind-backup")
            files = []
            for name in sorted(set(rows) | set(previous)):
                new = read_file(source / "payload" / name) if name in rows else None
                if new is not None and digest(new) != rows[name]["sha256"]: raise ValueError("Копия изменилась перед восстановлением.")
                old = read_file(operation / "before.protomind-backup/payload" / name) if name in previous else None
                files.append({"path": name, "before": digest(old) if old is not None else None,
                              "restore": self._blob(operation, without_authority(name, new)),
                              "rollback": self._blob(operation, without_authority(name, old))})
            plan = {"schema": PLAN_SCHEMA, "id": identifier, "root": str(self.root), "state": str(self.state), "window": window_name, "files": files}
            raw = encoded(plan)
            if len(raw) > MAX_MANIFEST: raise ValueError("План восстановления слишком большой.")
            atomic_file(operation / "plan.json", raw)
            if self.scan()["fingerprint"] != expected_target or self.verify(source)["sha256"] != expected_hash:
                raise ValueError("Данные изменились при подготовке. Восстановление не началось.")
            marker = self._marker(identifier, "restore", digest(raw))
            atomic_file(self.marker, encoded(marker))
            self.fault("native_marker")
            self._core_marker(identifier)
            self.fault("core_marker")
            return self._apply(marker, plan, operation)

    def resume(self, identifier: str, *, rollback=False) -> dict:
        marker, plan, operation = self._load_plan()
        if marker["id"] != identifier: raise ValueError("Выбран другой план восстановления.")
        token = RESTORE_WRITER.set(True)
        try:
            with self.locks(write=True):
                marker, plan, operation = self._load_plan()
                if marker["id"] != identifier: raise ValueError("План восстановления изменился.")
                if rollback:
                    marker = {**marker, "direction": "rollback"}
                    atomic_file(self.marker, encoded(marker))
                self._core_marker(identifier)
                return self._apply(marker, plan, operation)
        finally: RESTORE_WRITER.reset(token)

    def _current(self, name: str) -> str | None:
        path = self.path(name)
        if not os.path.lexists(path): return None
        if stat.S_ISDIR(path.lstat().st_mode): return None
        return digest(read_file(path))

    def _core_marker(self, identifier: str) -> None:
        path = self.roots["core"] / RESTORE_MARKER
        expected = encoded({"state": str(self.state), "id": identifier})
        if os.path.lexists(path) and read_file(path, 8192) != expected:
            raise ValueError("Ядро памяти восстанавливается другим профилем. Его маркер не изменён.")
        atomic_file(path, expected)

    def _apply(self, marker: dict, plan: dict, operation: Path) -> dict:
        direction = marker["direction"]
        known = {item["path"] for item in plan["files"]}
        if set(self.inventory()) - known: raise ValueError("После начала восстановления появились новые данные. Они не перезаписывались.")
        for item in plan["files"]:
            if self._current(item["path"]) not in {item["before"], item["restore"], item["rollback"]}:
                raise ValueError("Файл изменён вне восстановления: " + item["path"])
        # Remove files deepest first for file/directory transitions, then publish
        # immutable objects before the authoritative conversation manifest.
        ordered = sorted(plan["files"], key=lambda row: (row[direction] is not None,
                         row["path"] == "native/conversations.json",
                         -row["path"].count("/") if row[direction] is None else row["path"].count("/"), row["path"]))
        for index, item in enumerate(ordered):
            desired = item[direction]
            current = self._current(item["path"])
            if current == desired: continue
            if current not in {item["before"], item["restore"], item["rollback"]}: raise ValueError("Файл изменился при восстановлении.")
            target = self.path(item["path"])
            if desired is None:
                target.unlink(); sync_directory(target.parent)
            else:
                raw = read_file(operation / "blobs" / desired)
                if digest(raw) != desired: raise ValueError("Образ файла восстановления повреждён.")
                if target.is_dir() and not target.is_symlink(): target.rmdir()  # Refuses nonempty directories, including live locks.
                atomic_file(target, raw)
            self.fault("file:" + str(index))
            if self._current(item["path"]) != desired: raise ValueError("Не удалось подтвердить запись файла восстановления.")
        expected = {item["path"]: item[direction] for item in plan["files"] if item[direction] is not None}
        snapshot = self.scan()
        if {row["path"]: row["sha256"] for row in snapshot["entries"]} != expected:
            raise ValueError("Итоговое состояние отличается от плана. Восстановление остаётся открытым.")
        result = {"id": marker["id"], "completed": True, "direction": direction, "files": len(expected),
                  "recovery_path": str(operation / "before.protomind-backup"), "window_path": str(self.directory / plan["window"]),
                  "restart_required": True, "access_reset": True}
        atomic_file(operation / "receipt.json", encoded(result))
        self.fault("receipt")
        for directory in [self.roots["core"], self.state]:
            atomic_file(directory / GENERATION_FILE, encoded({"id": marker["id"], "direction": direction}))
        self.fault("generation")
        core_marker = self.roots["core"] / RESTORE_MARKER
        if read_file(self.marker, 8192) != encoded(marker) or read_file(core_marker, 8192) != encoded({"state": str(self.state), "id": marker["id"]}):
            raise ValueError("Журнал восстановления изменился. Блокировка сохранена для проверки.")
        core_marker.unlink(); sync_directory(core_marker.parent)
        self.fault("core_unlocked")
        self.marker.unlink(); sync_directory(self.state)
        self.fault("completed")
        return result

    def dispatch(self, method: str, params: dict) -> dict:
        fields = {"private_backup_create": {"path"}, "private_backup_preview": {"path"},
                  "private_backup_restore": {"path", "sha256", "target_fingerprint", "window"},
                  "private_backup_resume": {"id"}, "private_backup_rollback": {"id"}}.get(method, set())
        if set(params) != fields: raise ValueError("Некорректные параметры полной копии.")
        if method == "private_backup_status": return self.status()
        if method in {"private_backup_resume", "private_backup_rollback"}: return self.resume(params["id"], rollback=method.endswith("rollback"))
        value = params["path"]
        if not isinstance(value, str) or not Path(value).is_absolute(): raise ValueError("Выберите папку копии.")
        path = Path(value).parent.resolve(strict=True) / Path(value).name
        if method == "private_backup_create": return self.export(path)
        if method == "private_backup_preview": return self.preview(path)
        if method == "private_backup_restore": return self.restore(path, params["sha256"], params["target_fingerprint"], params["window"])
        raise ValueError("Неизвестная операция полной копии.")
