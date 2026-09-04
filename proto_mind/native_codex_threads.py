"""Private Native conversation-to-Codex thread bindings.

The store contains identifiers and workspace identity only. Codex owns its
durable rollout data inside the separate Native Codex profile.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import stat
import threading
from uuid import UUID, uuid4


LEGACY_SCHEMA = "proto_mind.native_codex_threads.v1"
MODE_SCHEMA = "proto_mind.native_codex_threads.v2"
SCHEMA = "proto_mind.native_codex_threads.v3"
STATUS_SCHEMA = "proto_mind.native_codex_threads.v1"
MAX_BINDINGS = 500
MAX_STORE_BYTES = 512 * 1024
LEGACY_FIELDS = frozenset({"conversation_id", "thread_id", "workspace", "created_at", "updated_at", "last_mode", "last_model"})
MODE_FIELDS = LEGACY_FIELDS | {"instruction_mode"}
FIELDS = MODE_FIELDS | {"instruction_contract_hash"}
WORKSPACE_FIELDS = frozenset({"path", "device", "inode"})
MODES = frozenset({"chat", "full_access"})
LEGACY_MODE = "legacy_unknown"
UNKNOWN_INSTRUCTION_CONTRACT = "legacy_unknown"


class CodexThreadStoreError(RuntimeError):
    pass


def timestamp() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def conversation_id(value: object) -> str:
    try:
        return str(UUID(str(value)))
    except (ValueError, TypeError, AttributeError):
        raise CodexThreadStoreError("Invalid Native conversation ID; no Codex session was changed.") from None


def thread_id(value: object) -> str:
    if (not isinstance(value, str) or not 1 <= len(value) <= 160
            or any(ord(char) < 33 or ord(char) > 126 for char in value)):
        raise CodexThreadStoreError("Codex returned an invalid thread ID; no turn was started.")
    return value


def workspace_identity(value: object) -> dict | None:
    if value is None:
        return None
    if (not isinstance(value, dict) or set(value) != WORKSPACE_FIELDS
            or not isinstance(value.get("path"), str) or not Path(value["path"]).is_absolute()
            or len(value["path"]) > 4096 or any(ord(char) < 32 for char in value["path"])
            or type(value.get("device")) is not int or value["device"] < 0
            or type(value.get("inode")) is not int or value["inode"] < 0):
        raise CodexThreadStoreError("Invalid workspace identity; no Codex session was changed.")
    return {key: value[key] for key in ("path", "device", "inode")}


def _valid_stamp(value: object) -> str:
    if not isinstance(value, str) or len(value) > 64:
        raise CodexThreadStoreError("Invalid Codex thread timestamp.")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise CodexThreadStoreError("Invalid Codex thread timestamp.") from None
    if parsed.tzinfo is None:
        raise CodexThreadStoreError("Invalid Codex thread timestamp.")
    return value


def _contract_hash(value: object, *, unknown: bool = False) -> str:
    if unknown:
        return UNKNOWN_INSTRUCTION_CONTRACT
    if value == UNKNOWN_INSTRUCTION_CONTRACT:
        return value
    if (not isinstance(value, str) or len(value) != 64
            or any(char not in "0123456789abcdef" for char in value)):
        raise CodexThreadStoreError("Invalid Codex instruction contract hash.")
    return value


def validate_binding(value: object, *, schema: str = SCHEMA) -> dict:
    expected = {LEGACY_SCHEMA: LEGACY_FIELDS, MODE_SCHEMA: MODE_FIELDS, SCHEMA: FIELDS}.get(schema)
    if expected is None:
        raise CodexThreadStoreError("Unknown Codex thread registry format.")
    if not isinstance(value, dict) or set(value) != expected:
        raise CodexThreadStoreError("Invalid Codex thread binding.")
    mode, model = value.get("last_mode"), value.get("last_model")
    if mode not in MODES:
        raise CodexThreadStoreError("Invalid Codex thread access mode.")
    instruction_mode = LEGACY_MODE if schema == LEGACY_SCHEMA else value.get("instruction_mode")
    if instruction_mode not in MODES | {LEGACY_MODE}:
        raise CodexThreadStoreError("Invalid Codex thread instruction mode.")
    if instruction_mode in MODES and instruction_mode != mode:
        raise CodexThreadStoreError("Codex thread mode metadata is inconsistent.")
    if not isinstance(model, str) or len(model) > 160 or any(ord(char) < 32 for char in model):
        raise CodexThreadStoreError("Invalid Codex thread model metadata.")
    return {
        "conversation_id": conversation_id(value.get("conversation_id")),
        "thread_id": thread_id(value.get("thread_id")),
        "workspace": workspace_identity(value.get("workspace")),
        "created_at": _valid_stamp(value.get("created_at")),
        "updated_at": _valid_stamp(value.get("updated_at")),
        "last_mode": mode,
        "last_model": model,
        "instruction_mode": instruction_mode,
        "instruction_contract_hash": _contract_hash(
            value.get("instruction_contract_hash"), unknown=schema != SCHEMA
        ),
    }


class CodexThreadStore:
    """Small atomic binding store; malformed state is never overwritten."""

    def __init__(self, state_dir: Path) -> None:
        self.directory = state_dir.resolve()
        self.path = self.directory / "codex_threads.json"
        self.write_blocked = False
        self.lock = threading.Lock()

    def _load(self) -> list[dict]:
        if not os.path.lexists(self.path):
            return []
        descriptor = None
        try:
            descriptor = os.open(self.path, os.O_RDONLY | os.O_NOFOLLOW)
            info = os.fstat(descriptor)
            if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_STORE_BYTES:
                raise CodexThreadStoreError("Codex thread registry is not a bounded regular file.")
            raw = bytearray()
            while len(raw) <= MAX_STORE_BYTES:
                chunk = os.read(descriptor, min(65_536, MAX_STORE_BYTES + 1 - len(raw)))
                if not chunk:
                    break
                raw.extend(chunk)
            if len(raw) > MAX_STORE_BYTES:
                raise CodexThreadStoreError("Codex thread registry exceeds its local size limit.")
            value = json.loads(raw)
            if (not isinstance(value, dict) or set(value) != {"schema", "bindings"}
                    or value.get("schema") not in {LEGACY_SCHEMA, MODE_SCHEMA, SCHEMA}):
                raise CodexThreadStoreError("Unknown Codex thread registry format.")
            rows = value.get("bindings")
            if not isinstance(rows, list) or len(rows) > MAX_BINDINGS:
                raise CodexThreadStoreError("Invalid Codex thread registry size.")
            result = [validate_binding(row, schema=value["schema"]) for row in rows]
            pairs = {(row["conversation_id"], row["instruction_mode"]) for row in result}
            workspaces = {}
            for row in result:
                workspaces.setdefault(row["conversation_id"], []).append(row["workspace"])
            if (len(pairs) != len(result) or len({row["thread_id"] for row in result}) != len(result)
                    or any(any(workspace != values[0] for workspace in values[1:])
                           for values in workspaces.values())):
                raise CodexThreadStoreError("Duplicate Codex thread binding; no automatic repair was attempted.")
            return result
        except (OSError, ValueError, TypeError, UnicodeError, RecursionError, CodexThreadStoreError) as exc:
            self.write_blocked = True
            if isinstance(exc, CodexThreadStoreError):
                raise
            raise CodexThreadStoreError("Could not read the Codex thread registry; the file remains unchanged.") from None
        finally:
            if descriptor is not None:
                os.close(descriptor)

    def _save(self, rows: list[dict]) -> None:
        if self.write_blocked:
            raise CodexThreadStoreError("Codex thread registry writes are blocked to preserve unreadable state.")
        value = {"schema": SCHEMA, "bindings": [validate_binding(row) for row in rows]}
        raw = json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        if len(raw) > MAX_STORE_BYTES:
            raise CodexThreadStoreError("Codex thread registry reached its local size limit.")
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.directory, 0o700)
        directory = os.open(self.directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        temporary = f".codex_threads.{uuid4().hex}.tmp"
        descriptor = None
        try:
            descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                                 0o600, dir_fd=directory)
            remaining = memoryview(raw)
            while remaining:
                written = os.write(descriptor, remaining)
                if not written:
                    raise OSError("Short Codex thread registry write")
                remaining = remaining[written:]
            os.fsync(descriptor)
            os.close(descriptor)
            descriptor = None
            os.replace(temporary, self.path.name, src_dir_fd=directory, dst_dir_fd=directory)
        except OSError:
            try:
                os.unlink(temporary, dir_fd=directory)
            except OSError:
                pass
            raise CodexThreadStoreError("Could not save the Codex thread registry; no provider turn was started.") from None
        finally:
            if descriptor is not None:
                os.close(descriptor)
            os.close(directory)

    def status(self, conversation: object, workspace: object, *, mode: str | None = None,
               instruction_contracts: dict[str, str] | None = None) -> dict:
        identifier, identity = conversation_id(conversation), workspace_identity(workspace)
        if mode is not None and mode not in MODES:
            raise CodexThreadStoreError("Invalid Codex thread access mode.")
        if instruction_contracts is not None:
            if (not isinstance(instruction_contracts, dict)
                    or set(instruction_contracts) != MODES):
                raise CodexThreadStoreError("Invalid current instruction contracts.")
            instruction_contracts = {
                key: _contract_hash(value) for key, value in instruction_contracts.items()
            }
        with self.lock:
            rows = [item for item in self._load() if item["conversation_id"] == identifier]
        if not rows:
            return {"schema": STATUS_SCHEMA, "linked": False, "workspace_matches": True,
                    "available_modes": [], "legacy_binding": False,
                    "refresh_required": False, "stale_modes": [],
                    "notice": "Следующее сообщение создаст новую постоянную сессию Codex."}
        matches = all(row["workspace"] == identity for row in rows)
        mode_rows = [row for row in rows if row["instruction_mode"] in MODES]
        available = sorted(row["instruction_mode"] for row in mode_rows)
        selected = (next((row for row in mode_rows if row["instruction_mode"] == mode), None)
                    if mode is not None else max(mode_rows, key=lambda row: row["updated_at"], default=None))
        stale_modes = sorted(
            row["instruction_mode"] for row in mode_rows
            if instruction_contracts is not None
            and row["instruction_contract_hash"] != instruction_contracts[row["instruction_mode"]]
        )
        refresh_required = selected is not None and selected["instruction_mode"] in stale_modes
        linked = selected is not None and not refresh_required
        display = selected or max(rows, key=lambda row: row["updated_at"])
        if not matches:
            notice = "Сессия Codex привязана к другой рабочей папке. Начните новую сессию явно."
        elif refresh_required:
            notice = ("Статические инструкции этого режима изменились. Следующее сообщение создаст свежую "
                      "сессию Codex, один раз добавит bounded локальную историю и сохранит прежний rollout как историю.")
        elif display["instruction_mode"] == LEGACY_MODE:
            notice = "Старая связь Codex сохранена только как история и не будет автоматически продолжена."
        elif linked:
            notice = "Сессия Codex будет продолжена в том же режиме доступа."
        else:
            notice = "Для выбранного режима будет создана отдельная сессия Codex с bounded локальной историей."
        result = {"schema": STATUS_SCHEMA, "linked": linked, "workspace_matches": matches,
                  "created_at": display["created_at"], "updated_at": display["updated_at"],
                  "last_mode": display["last_mode"], "last_model": display["last_model"],
                  "workspace": deepcopy(display["workspace"]), "available_modes": available,
                  "legacy_binding": any(row["instruction_mode"] == LEGACY_MODE for row in rows),
                  "refresh_required": refresh_required, "stale_modes": stale_modes,
                  "notice": notice}
        if linked:
            result["thread_id_short"] = selected["thread_id"][:8]
        if selected is not None:
            current_hash = selected["instruction_contract_hash"]
            result["instruction_contract_current"] = not refresh_required
            result["instruction_contract_hash_short"] = (
                current_hash[:12] if current_hash != UNKNOWN_INSTRUCTION_CONTRACT else "legacy"
            )
        return result

    def binding(self, conversation: object, workspace: object, *, mode: str) -> dict | None:
        identifier, identity = conversation_id(conversation), workspace_identity(workspace)
        if mode not in MODES:
            raise CodexThreadStoreError("Invalid Codex thread access mode.")
        with self.lock:
            rows = [item for item in self._load() if item["conversation_id"] == identifier]
        if rows and any(row["workspace"] != identity for row in rows):
            raise CodexThreadStoreError(
                "Saved Codex session belongs to another workspace. Use Model Settings > Start New Codex Session; no fallback was used."
            )
        row = next((item for item in rows if item["instruction_mode"] == mode), None)
        return deepcopy(row)

    def record_new(self, conversation: object, provider_thread: object, workspace: object,
                   *, mode: str, model: str,
                   instruction_contract_hash: str = UNKNOWN_INSTRUCTION_CONTRACT) -> dict:
        identifier, provider_id = conversation_id(conversation), thread_id(provider_thread)
        identity = workspace_identity(workspace)
        if mode not in MODES:
            raise CodexThreadStoreError("Invalid Codex thread access mode.")
        now = timestamp()
        row = validate_binding({"conversation_id": identifier, "thread_id": provider_id, "workspace": identity,
                                "created_at": now, "updated_at": now, "last_mode": mode, "last_model": model,
                                "instruction_mode": mode,
                                "instruction_contract_hash": _contract_hash(instruction_contract_hash)})
        with self.lock:
            rows = self._load()
            if any((item["conversation_id"], item["instruction_mode"]) == (identifier, mode)
                   or item["thread_id"] == provider_id for item in rows):
                raise CodexThreadStoreError("Codex thread binding changed concurrently; no turn was started.")
            if len(rows) >= MAX_BINDINGS:
                raise CodexThreadStoreError("Codex thread registry is full. Archive/export state before starting another session.")
            self._save([*rows, row])
        return deepcopy(row)

    def touch(self, conversation: object, provider_thread: object, workspace: object,
              *, mode: str, model: str,
              instruction_contract_hash: str = UNKNOWN_INSTRUCTION_CONTRACT) -> dict:
        identifier, provider_id = conversation_id(conversation), thread_id(provider_thread)
        identity = workspace_identity(workspace)
        if mode not in MODES:
            raise CodexThreadStoreError("Invalid Codex thread access mode.")
        with self.lock:
            rows = self._load()
            index = next((i for i, item in enumerate(rows)
                          if (item["conversation_id"], item["instruction_mode"]) == (identifier, mode)), None)
            if index is None or rows[index]["thread_id"] != provider_id or rows[index]["workspace"] != identity:
                raise CodexThreadStoreError("Codex thread binding changed before dispatch; no turn was started.")
            if rows[index]["instruction_contract_hash"] != _contract_hash(instruction_contract_hash):
                raise CodexThreadStoreError("Codex instruction contract changed before dispatch; no turn was started.")
            rows[index] = validate_binding({**rows[index], "updated_at": timestamp(), "last_mode": mode, "last_model": model})
            self._save(rows)
            return deepcopy(rows[index])

    def refresh_contract(self, conversation: object, previous_provider_thread: object,
                         provider_thread: object, workspace: object, *, mode: str,
                         model: str, instruction_contract_hash: str) -> dict:
        """Replace one stale mode binding after a new provider thread is verified."""
        identifier = conversation_id(conversation)
        previous_id, provider_id = thread_id(previous_provider_thread), thread_id(provider_thread)
        identity = workspace_identity(workspace)
        current_contract = _contract_hash(instruction_contract_hash)
        if mode not in MODES:
            raise CodexThreadStoreError("Invalid Codex thread access mode.")
        now = timestamp()
        replacement = validate_binding({
            "conversation_id": identifier, "thread_id": provider_id, "workspace": identity,
            "created_at": now, "updated_at": now, "last_mode": mode, "last_model": model,
            "instruction_mode": mode, "instruction_contract_hash": current_contract,
        })
        with self.lock:
            rows = self._load()
            index = next((i for i, item in enumerate(rows)
                          if (item["conversation_id"], item["instruction_mode"]) == (identifier, mode)), None)
            if (index is None or rows[index]["thread_id"] != previous_id
                    or rows[index]["workspace"] != identity):
                raise CodexThreadStoreError("Codex thread binding changed before contract refresh; no turn was started.")
            if rows[index]["instruction_contract_hash"] == current_contract:
                raise CodexThreadStoreError("Codex instruction contract was already current; no replacement was saved.")
            if provider_id == previous_id or any(
                    item["thread_id"] == provider_id for i, item in enumerate(rows) if i != index):
                raise CodexThreadStoreError("Codex returned a reused thread ID; no replacement was saved.")
            rows[index] = replacement
            self._save(rows)
        return deepcopy(replacement)

    def reset(self, conversation: object) -> bool:
        identifier = conversation_id(conversation)
        with self.lock:
            rows = self._load()
            next_rows = [row for row in rows if row["conversation_id"] != identifier]
            if len(next_rows) == len(rows):
                return False
            self._save(next_rows)
        return True
