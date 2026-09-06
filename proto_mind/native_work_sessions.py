"""Private, bounded Native turn evidence. Never a queue, permission or auto-resume engine."""
from __future__ import annotations

from proto_mind.native_auto_skills import validate_auto_skills

from contextlib import contextmanager
from copy import deepcopy
from datetime import UTC, datetime
import fcntl
import hashlib
import heapq
import json
import os
from pathlib import Path
import stat
import time
from uuid import UUID, uuid4

from proto_mind.native_locks import open_sidecar
from proto_mind.native_progress import display_text
from proto_mind.native_desk import CONTEXT_SCHEMA, valid_artifact_snapshot
from proto_mind.native_images import validate_image_metadata
from proto_mind.native_pdf import validate_pdf_metadata
from proto_mind.native_review import ACCEPTANCE, criteria_contract, make_review, valid_reviews
from proto_mind.native_knowledge import validate_knowledge_metadata
from proto_mind.native_instructions import validate_instruction_receipt
from proto_mind.native_turn_lineage import build_turn_receipt, validate_turn_receipt
from proto_mind.native_agent_contract import (
    contract_hash,
    public_agent_contract,
    validate_agent_contract,
    validate_runtime_inventory,
)


SCHEMA = "proto_mind.native_work_session.v1"
PAGE_SIZE = 30
MAX_RECORD_BYTES = 256 * 1024
MAX_PAGE_BYTES = 2 * 1024 * 1024
STATES = {"prepared", "dispatching", "completed", "interrupted", "error"}


def timestamp() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


class WorkSessionError(RuntimeError):
    pass


def _id(value: object) -> str:
    try:
        return str(UUID(str(value)))
    except (ValueError, TypeError, AttributeError):
        raise WorkSessionError("Invalid work-session ID. No automatic retry.") from None


def _bytes(value: dict) -> bytes:
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def fingerprint(record: dict) -> str:
    return hashlib.sha256(_bytes(record)).hexdigest()


def inspect_work_session_copy(raw: bytes, name: str) -> dict:
    """Validate one exact copied record without opening or changing a store."""
    if type(raw) is not bytes or not raw or len(raw) > MAX_RECORD_BYTES:
        raise WorkSessionError("Work-session copy is not bounded immutable bytes.")
    try:
        record = WorkSessionStore._parse(raw, name)
        if _bytes(record) != raw:
            raise WorkSessionError("Work-session copy is not the canonical Native record bytes.")
        return WorkSessionStore._view(record, None)
    except WorkSessionError:
        raise
    except (UnicodeDecodeError, UnicodeEncodeError, ValueError, TypeError, RecursionError):
        raise WorkSessionError("Invalid work-session copy. No migration or overwrite was attempted.") from None


def workspace_identity(path: Path | None) -> dict | None:
    if path is None:
        return None
    canonical = path.resolve(strict=True)
    info = canonical.stat()
    return {"path": str(canonical), "device": info.st_dev, "inode": info.st_ino}


def _texts(source: dict, limits: dict[str, int]) -> dict:
    return {key: display_text(source.get(key), limit) for key, limit in limits.items() if isinstance(source.get(key), str)}


def public_work_log(value: dict) -> dict:
    """Project only our public UI contract, never arbitrary provider event fields."""
    if value.get("schema") != "proto_mind.native_work_log.v1" or value.get("public_only") is not True:
        return {}
    result = _texts(value, {"schema": 80, "id": 80, "access_mode": 40, "started_at": 40,
                            "finished_at": 40, "status": 40, "stage": 40})
    result.update(public_only=True, entries=[], truncated=value.get("truncated") is True)
    if type(value.get("state_version")) is int and value["state_version"] > 0:
        result["state_version"] = value["state_version"]
    if type(value.get("elapsed_ms")) is int:
        result["elapsed_ms"] = max(0, value["elapsed_ms"])
    for item in value.get("entries", [])[:96]:
        if not isinstance(item, dict) or item.get("kind") not in {"commentary", "tool", "plan", "context_compaction"}:
            continue
        row = _texts(item, {"id": 200, "kind": 40, "text": 768, "status": 40, "tool_id": 160, "tool_kind": 40})
        if not row.get("id"):
            continue
        if item.get("kind") == "plan":
            row["steps"] = [_texts(step, {"step": 200, "status": 40}) for step in item.get("steps", [])[:12] if isinstance(step, dict)]
        result["entries"] = [old for old in result["entries"] if old["id"] != row["id"]] + [row]
    return result


def public_tool(value: dict) -> dict | None:
    if value.get("kind") not in {"commandExecution", "fileChange", "imageView", "webSearch", "computerUse", "plan"} or not value.get("id"):
        return None
    row = _texts(value, {"id": 160, "kind": 40, "status": 40, "command": 800, "cwd": 1024,
                         "output_preview": 768, "diff_preview": 768, "path": 1024, "text": 768,
                         "query": 768, "action_type": 40, "url": 1600,
                         "tool": 80, "app": 120, "note": 300, "failure_code": 80,
                         "failure_message": 300, "recovery": 500})
    for key in ("exit_code", "duration_ms", "change_count"):
        if type(value.get(key)) is int:
            row[key] = value[key]
    if isinstance(value.get("paths"), list):
        row["paths"] = [display_text(path, 400) for path in value["paths"][:8] if isinstance(path, str)]
    return row


class WorkSessionStore:
    def __init__(self, state_dir: Path, project_root: Path) -> None:
        self.directory = state_dir / "work_sessions"
        self.project_root = str(project_root.resolve())

    @contextmanager
    def _directory(self, *, create: bool = False):
        descriptor = None
        try:
            if create:
                self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
            descriptor = os.open(self.directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        except FileNotFoundError:
            if create:
                raise WorkSessionError("Work-session storage is unavailable. No automatic retry.") from None
        except OSError:
            raise WorkSessionError("Work-session storage is unreadable or not durable. Inspect it manually; no repair was attempted.") from None
        try:
            yield descriptor
        finally:
            if descriptor is not None:
                os.close(descriptor)

    @staticmethod
    def _raw(directory: int, name: str) -> bytes | None:
        descriptor = None
        try:
            descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
            info = os.fstat(descriptor)
            if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_RECORD_BYTES:
                raise WorkSessionError("Work-session record is not a bounded regular file.")
            with os.fdopen(descriptor, "rb", closefd=False) as file:
                result = file.read(MAX_RECORD_BYTES + 1)
            if len(result) > MAX_RECORD_BYTES:
                raise WorkSessionError("Work-session record exceeded the size limit.")
            return result
        except FileNotFoundError:
            return None
        finally:
            if descriptor is not None:
                os.close(descriptor)

    @staticmethod
    def _parse(raw: bytes, name: str) -> dict:
        try:
            record = json.loads(raw)
            if (not isinstance(record, dict) or record.get("schema") != SCHEMA
                    or _id(record.get("id")) + ".json" != name
                    or record.get("status") not in STATES
                    or record.get("verification") != "not_assessed"
                    or not isinstance(record.get("project_root"), str)
                    or not isinstance(record.get("input_preview"), str)
                    or not isinstance(record.get("created_at"), str) or not 1 <= len(record["created_at"]) <= 80
                    or not isinstance(record.get("work_log"), dict)
                    or not isinstance(record.get("tools"), list) or len(record["tools"]) > 64
                    or not isinstance(record.get("sources"), list) or len(record["sources"]) > 3):
                raise ValueError()
            datetime.fromisoformat(record["created_at"].replace("Z", "+00:00"))
            for item in record["tools"]:
                if (not isinstance(item, dict) or not isinstance(item.get("id"), str)
                        or not isinstance(item.get("status"), str) or public_tool(item) is None):
                    raise ValueError()
            for source in record["sources"]:
                if (not isinstance(source, dict) or not isinstance(source.get("path"), str)
                        or not isinstance(source.get("sha256"), str) or len(source["sha256"]) != 64):
                    raise ValueError()
            log = record["work_log"]
            if log and (log.get("schema") != "proto_mind.native_work_log.v1" or log.get("public_only") is not True
                        or not isinstance(log.get("entries"), list) or any(not isinstance(item, dict) for item in log["entries"])):
                raise ValueError()
            if "state_version" in log and (type(log["state_version"]) is not int or log["state_version"] <= 0):
                raise ValueError()
            _id(record.get("conversation_id"))
            if record.get("parent_run_id"):
                _id(record["parent_run_id"])
            if record.get("status") == "completed" and not record.get("finished_at"):
                raise ValueError()
            receipt = record.get("instruction_receipt")
            if receipt is not None:
                validate_instruction_receipt(receipt)
                if (record.get("status") != "completed" or receipt["provider"] != record.get("provider")
                        or receipt["mode"] != record.get("access_mode")):
                    raise ValueError()
            turn_receipt = record.get("turn_receipt")
            if turn_receipt is not None:
                validate_turn_receipt(turn_receipt)
                preview = record.get("answer_preview")
                if (record.get("status") != "completed" or receipt is None
                        or turn_receipt["run_id"] != record.get("id")
                        or turn_receipt["conversation_id"] != record.get("conversation_id")
                        or turn_receipt["provider"] != record.get("provider")
                        or turn_receipt["mode"] != record.get("access_mode")
                        or turn_receipt["input_chars"] != record.get("input_chars")
                        or turn_receipt["input_sha256"] != record.get("input_sha256")
                        or turn_receipt["instruction_receipt_hash"] != receipt["receipt_hash"]
                        or not isinstance(preview, str)
                        or turn_receipt["answer_preview_chars"] != len(preview)
                        or turn_receipt["answer_preview_sha256"] != hashlib.sha256(preview.encode()).hexdigest()):
                    raise ValueError()
            if "auto_skills" in record:
                validate_auto_skills(record["auto_skills"], record)
            if "artifact_snapshot" in record and not valid_artifact_snapshot(record["artifact_snapshot"], record):
                raise ValueError()
            if not valid_reviews(record):
                raise ValueError()
            manifest = record.get("context_manifest")
            if manifest is not None and (not isinstance(manifest, dict) or manifest.get("schema") != CONTEXT_SCHEMA
                                         or manifest.get("read_only") is not True or manifest.get("permission_granted") is not False):
                raise ValueError()
            if manifest is not None and "success_criteria" in manifest and manifest["success_criteria"] != record.get("success_criteria"):
                raise ValueError()
            if manifest is not None:
                validate_image_metadata(manifest.get("images", []))
                validate_pdf_metadata(manifest.get("pdfs", []))
                validate_knowledge_metadata(manifest.get("knowledge_context"))
                recall = (manifest.get("knowledge_context") or {}).get("project_recall")
                if recall is not None:
                    from proto_mind.native_project_recall import validate_project_recall
                    validate_project_recall(recall, record=record)
                if any(row["workspace"] != record.get("workspace") for row in (manifest.get("knowledge_context") or {}).get("project_memory", [])):
                    raise ValueError()
                skill = (manifest.get("knowledge_context") or {}).get("skill_task")
                if skill is not None and (skill["workspace"] != record.get("workspace") or skill["conversation_id"] != record["conversation_id"]
                        or skill["provider"] != record["provider"] or skill["access_mode"] != record["access_mode"]
                        or skill["goal_sha256"] != manifest.get("input", {}).get("sha256")
                        or skill["criteria_sha256"] != (record.get("success_criteria") or {}).get("sha256")):
                    raise ValueError()
            contract = record.get("agent_contract")
            if contract is not None:
                validate_agent_contract(contract)
                if (record.get("agent_contract_hash") != contract_hash(contract)
                        or record.get("access_mode") != "full_access"
                        or record.get("workspace") != contract.get("workspace")):
                    raise ValueError()
                inventory = record.get("agent_runtime_inventory")
                if inventory is not None:
                    tools = inventory.get("computer_use_tools") if isinstance(inventory, dict) else None
                    if (not isinstance(tools, list) or len(tools) > 16
                            or any(not isinstance(item, str) for item in tools)
                            or inventory != validate_runtime_inventory(contract, set(tools))):
                        raise ValueError()
            elif "agent_contract_hash" in record or "agent_runtime_inventory" in record:
                raise ValueError()
            return record
        except (ValueError, TypeError, WorkSessionError):
            raise WorkSessionError("Invalid work-session record. No migration or overwrite was attempted.") from None

    def _records(self, directory: int | None, warnings: list[str]):
        """Stream validated records without retaining the entire journal in memory."""
        if directory is None:
            return
        with os.scandir(directory) as entries:
            for entry in entries:
                if not entry.name.endswith(".json"):
                    continue
                try:
                    raw = self._raw(directory, entry.name)
                    if raw is None:
                        raise WorkSessionError("Work-session record disappeared during reading.")
                    yield self._parse(raw, entry.name)
                except (OSError, WorkSessionError):
                    if not warnings:
                        warnings.append("One or more unreadable or invalid work-session files require manual review; they were not changed.")

    @staticmethod
    def _active(directory: int | None) -> set[str]:
        """Observe owners without creating files or releasing another process's locks."""
        active = set()
        if directory is None:
            return active
        with os.scandir(directory) as entries:
            names = [entry.name for entry in entries if entry.name.startswith(".run-") and entry.name.endswith(".lock")]
        # An old app holds this barrier exclusively and stores its run ID here.
        # New apps hold it shared; each run has its own named ownership lock.
        for name in [".writer.lock", *names]:
            descriptor = None
            try:
                descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
                if not stat.S_ISREG(os.fstat(descriptor).st_mode):
                    raise WorkSessionError("Invalid work-session writer lock.")
                try:
                    operation = fcntl.LOCK_SH if name == ".writer.lock" else fcntl.LOCK_EX
                    fcntl.flock(descriptor, operation | fcntl.LOCK_NB)
                except BlockingIOError:
                    active.add(_id(os.read(descriptor, 100).decode("ascii")) if name == ".writer.lock" else _id(name[5:-5]))
            except FileNotFoundError:
                continue
            finally:
                if descriptor is not None:
                    os.close(descriptor)
        return active

    @staticmethod
    def _view(record: dict, active: set[str] | None) -> dict:
        state = record["status"]
        if state == "prepared":
            state = "preparing" if record["id"] in (active or set()) else "not_started"
        elif state == "dispatching":
            state = "running" if record["id"] in (active or set()) else "unknown"
        elif state in {"error", "interrupted"}:
            state = "unknown" if record.get("dispatched_at") else "not_started"
        result = deepcopy(record)
        result.update(display_status=state, fingerprint=fingerprint(record), automatic_resume=False)
        if state == "unknown":
            for item in result["tools"]:
                if item.get("status") in {"inProgress", "running", "starting"}:
                    item["status"] = "unknown"
        return result

    def _cursor(self, record: dict, conversation: str) -> dict:
        return {"conversation_id": conversation, "project_root": self.project_root,
                "created_at": record["created_at"], "run_id": record["id"]}

    def _cursor_key(self, cursor: object, conversation: str) -> tuple[str, str] | None:
        if cursor is None:
            return None
        if (not isinstance(cursor, dict) or set(cursor) != {"conversation_id", "project_root", "created_at", "run_id"}
                or cursor["conversation_id"] != conversation or cursor["project_root"] != self.project_root
                or not isinstance(cursor["created_at"], str) or not 1 <= len(cursor["created_at"]) <= 80
                or _id(cursor["run_id"]) != cursor["run_id"]):
            raise WorkSessionError("Invalid journal page cursor or conversation/project scope. Refresh the journal.")
        try:
            datetime.fromisoformat(cursor["created_at"].replace("Z", "+00:00"))
        except ValueError:
            raise WorkSessionError("Invalid journal page timestamp. Refresh the journal.") from None
        return cursor["created_at"], cursor["run_id"]

    def page(self, conversation_id: str, cursor: object = None) -> dict:
        conversation = _id(conversation_id)
        boundary = self._cursor_key(cursor, conversation)
        with self._directory() as directory:
            warnings: list[str] = []
            total = remaining = 0

            def candidates():
                nonlocal total, remaining
                for record in self._records(directory, warnings):
                    if record["conversation_id"] != conversation or record["project_root"] != self.project_root:
                        continue
                    total += 1
                    if boundary is None or (record["created_at"], record["id"]) < boundary:
                        remaining += 1
                        yield record

            # Keyset pagination stays stable when newer runs arrive. Only one
            # bounded page of full records is retained while counting the rest.
            selected = heapq.nlargest(PAGE_SIZE, candidates(), key=lambda record: (record["created_at"], record["id"]))
            active = self._active(directory)
            shown, size = [], 0
            for record in selected:
                view = self._view(record, active)
                size += len(_bytes(view))
                if size > MAX_PAGE_BYTES:
                    break
                shown.append(view)
            return {"schema": "proto_mind.native_work_sessions.v1", "read_only": True,
                    "path": str(self.directory), "conversation_id": conversation, "project_root": self.project_root,
                    "total": total, "warnings": warnings, "cursor": deepcopy(cursor),
                    "next_cursor": self._cursor(shown[-1], conversation) if shown and len(shown) < remaining else None,
                    "partial": len(shown) < remaining, "runs": shown}

    def _parent(self, records, continuation: object, conversation: str, workspace: dict | None, active: set[str] | None) -> dict:
        if not isinstance(continuation, dict):
            raise WorkSessionError("Invalid continuation reference.")
        parent_id = _id(continuation.get("run_id"))
        parent = child = None
        for record in records:
            if record["id"] == parent_id:
                parent = record
            if record.get("parent_run_id") == parent_id:
                child = record
        if (parent is None or parent["project_root"] != self.project_root or parent["conversation_id"] != conversation
                or parent.get("workspace") != workspace or continuation.get("fingerprint") != fingerprint(parent)):
            raise WorkSessionError("Saved work or its folder changed. Inspect the journal again before preparing a continuation.")
        if parent_id in (active or set()):
            raise WorkSessionError("This work is still owned by an active writer. No continuation was prepared.")
        if child is not None:
            raise WorkSessionError(f"A continuation already exists: {child['id']}. Inspect that run; do not replay the parent.")
        return parent

    def lookup(self, run_id: str, conversation_id: str) -> dict:
        """Read one exact ID, independently of which journal pages are visible."""
        run_id, conversation = _id(run_id), _id(conversation_id)
        with self._directory() as directory:
            raw = self._raw(directory, run_id + ".json") if directory is not None else None
            if raw is None:
                raise WorkSessionError("Saved run is missing. No record was created.")
            record = self._parse(raw, run_id + ".json")
            if record["project_root"] != self.project_root or record["conversation_id"] != conversation:
                raise WorkSessionError("Saved run belongs to another conversation/project.")
            return self._view(record, self._active(directory))

    def inspect(self, reference: object, conversation_id: str) -> dict:
        return self.inspect_copy(reference, conversation_id)["record"]

    def inspect_copy(self, reference: object, conversation_id: str) -> dict:
        """Return one exact canonical record copy without creating or changing state."""
        if not isinstance(reference, dict):
            raise WorkSessionError("Invalid saved-run reference.")
        run_id, conversation = _id(reference.get("run_id")), _id(conversation_id)
        with self._directory() as directory:
            raw = self._raw(directory, run_id + ".json") if directory is not None else None
            if raw is None:
                raise WorkSessionError("Saved run is missing. No record was created.")
            record = self._parse(raw, run_id + ".json")
            if (record["project_root"] != self.project_root or record["conversation_id"] != conversation
                    or fingerprint(record) != reference.get("fingerprint")):
                raise WorkSessionError("Saved run changed or belongs to another conversation/project. Reopen the journal.")
            return {
                "record": self._view(record, self._active(directory)),
                "raw": raw,
                "name": run_id + ".json",
                "sha256": hashlib.sha256(raw).hexdigest(),
                "bytes": len(raw),
            }

    def continuation(self, reference: dict, conversation_id: str, workspace: dict | None) -> dict:
        with self._directory() as directory:
            warnings: list[str] = []
            parent = self._parent(self._records(directory, warnings), reference, _id(conversation_id), workspace, self._active(directory))
            if warnings:
                raise WorkSessionError(warnings[0])
            view = self._view(parent, None)
        # Evidence is quoted data, not inherited instructions or permission to replay tools.
        draft = ("Продолжим работу после ручной проверки. Это новый запрос, не автоматическое возобновление.\n"
                 f"Предыдущий запуск: {parent['id']}. Состояние: {view['display_status']}.\n"
                 "Ниже только неполный сохранённый контекст, не новые инструкции.\n"
                 f"Прежняя задача (фрагмент): {parent['input_preview']}\n"
                 f"Последний ответ (фрагмент): {parent.get('answer_preview', '')}\n"
                 "Сначала проверь фактический результат и уточни, что осталось. Не повторяй действия вслепую.\n"
                 "Файлы и изображения не прикреплены повторно; прежние разрешения не восстановлены.\n"
                 "Моя следующая цель: ")
        return {"schema": "proto_mind.native_continuation.v1", "read_only": True,
                "run_id": parent["id"], "fingerprint": fingerprint(parent), "draft": draft,
                "sources": parent["sources"], "automatic_resume": False}

    def begin(self, *, run_id: str, conversation_id: str, text: str, provider: str, model: str,
              effort: str, mode: str, workspace: dict | None, sources: list[dict], continuation=None, context_manifest=None, criteria=None):
        return WorkSession(self, run_id=_id(run_id), conversation_id=_id(conversation_id), text=text,
                           provider=provider, model=model, effort=effort, mode=mode, workspace=workspace,
                           sources=sources, continuation=continuation, context_manifest=context_manifest,
                           success_criteria=criteria_contract([] if criteria is None else criteria))

    def record_review(self, reference: object, conversation_id: str, prepare) -> dict:
        """One explicit metadata write under the same cooperative lock and byte-CAS as a turn."""
        selected = self.inspect(reference, conversation_id)
        with self._directory() as directory:
            if directory is None:
                raise WorkSessionError("Work-session directory disappeared. Nothing was recorded.")
            writer = WorkSession(self)
            writer.directory = directory
            try:
                # A real saved run already has this lock. Do not initialize missing evidence.
                writer.lock = os.open(".writer.lock", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
                if not stat.S_ISREG(os.fstat(writer.lock).st_mode):
                    raise WorkSessionError("Invalid work-session writer lock.")
                try:
                    fcntl.flock(writer.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    raise WorkSessionError("Another Native window is writing. Review was not recorded; refresh first.") from None
                raw = self._raw(directory, selected["id"] + ".json")
                if raw is None:
                    raise WorkSessionError("Saved run disappeared. Nothing was recorded.")
                record = self._parse(raw, selected["id"] + ".json")
                if fingerprint(record) != selected["fingerprint"]:
                    raise WorkSessionError("Saved run changed before review. Refresh the journal; no overwrite.")
                preview = prepare(self._view(record, None))
                receipt = make_review(record, preview)
                updated = deepcopy(record)
                updated["operator_reviews"] = [*updated.get("operator_reviews", []), receipt]
                updated.update(acceptance=ACCEPTANCE[receipt["selection"]["decision"]], updated_at=receipt["reviewed_at"])
                if not valid_reviews(updated):
                    raise WorkSessionError("Invalid operator review; the saved run was not changed.")
                writer.record, writer.expected = updated, raw
                writer._save()
                return self._view(updated, None)
            except OSError:
                raise WorkSessionError("Review storage is unavailable. Refresh and inspect; no automatic retry.") from None
            finally:
                writer.close()


class WorkSession:
    """Per-conversation ownership plus a shared barrier against review/restore/old writers."""
    def __init__(self, store: WorkSessionStore, **values) -> None:
        self.store, self.values = store, values
        self.record: dict = {}
        self.expected: bytes | None = None
        self.directory = self.lock = None
        self.ownership_locks: dict[str, int] = {}
        self.directory_context = None
        self.last_publish = float("-inf")
        self.failed_write = False

    def __enter__(self):
        try:
            self.directory_context = self.store._directory(create=True)
            self.directory = self.directory_context.__enter__()
            self.lock = open_sidecar(".writer.lock", directory=self.directory)
            if not stat.S_ISREG(os.fstat(self.lock).st_mode):
                raise WorkSessionError("Invalid work-session writer lock.")
            try:
                fcntl.flock(self.lock, fcntl.LOCK_SH | fcntl.LOCK_NB)
            except BlockingIOError:
                raise WorkSessionError("Another Native window owns the work-session writer. No new turn started.") from None
            values = self.values
            if self.store._raw(self.directory, values["run_id"] + ".json") is not None:
                raise WorkSessionError("This work-session ID was already used. Inspect its result; no repeated turn was dispatched.")
            # Claim the conversation before the run so a duplicate submit does
            # not even create another run lock. Lock files are never unlinked.
            self._claim(f".conversation-{values['conversation_id']}.lock")
            parent = None
            if values["continuation"] is not None:
                warnings: list[str] = []
                parent = self.store._parent(self.store._records(self.directory, warnings), values["continuation"],
                                           values["conversation_id"], values["workspace"], None)
                if warnings:
                    raise WorkSessionError(warnings[0])
            self._claim(f".run-{values['run_id']}.lock")
            if self.store._raw(self.directory, values["run_id"] + ".json") is not None:
                raise WorkSessionError("This work-session ID was already used. No repeated turn was dispatched.")
            self.record = {"schema": SCHEMA, "id": values["run_id"], "conversation_id": values["conversation_id"],
                           "project_root": self.store.project_root, "workspace": values["workspace"],
                           "created_at": timestamp(), "updated_at": timestamp(), "status": "prepared",
                           "provider": values["provider"], "requested_model": values["model"], "requested_effort": values["effort"],
                           "access_mode": values["mode"], "input_preview": display_text(values["text"], 800),
                           "input_chars": len(values["text"]), "input_sha256": hashlib.sha256(values["text"].encode()).hexdigest(),
                           "sources": [_texts(item, {"path": 4096, "sha256": 64}) for item in values["sources"][:3]],
                           "parent_run_id": parent["id"] if parent else None, "tools": [], "work_log": {},
                           "network_access_performed": False, "computer_use_performed": False,
                           "screen_access_performed": False,
                           "verification": "not_assessed", "acceptance": "not_recorded"}
            if values["context_manifest"] is not None:
                self.record["context_manifest"] = deepcopy(values["context_manifest"])
            if values["success_criteria"] is not None:
                self.record["success_criteria"] = deepcopy(values["success_criteria"])
            self._save()
            return self
        except BaseException:
            self.close()
            raise

    def _claim(self, name: str) -> None:
        descriptor = open_sidecar(name, directory=self.directory)
        self.ownership_locks[name] = descriptor
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise WorkSessionError("Invalid work-session ownership lock.")
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise WorkSessionError("Another Native window owns this conversation or run. No new turn started.") from None

    def _save(self) -> None:
        if self.failed_write:
            raise WorkSessionError("Durable work evidence failed. The turn was stopped; inspect its unknown outcome before retrying.")
        temporary = None
        try:
            name = self.record["id"] + ".json"
            if self.store._raw(self.directory, name) != self.expected:
                raise WorkSessionError("Work-session file changed outside its writer. No overwrite or automatic retry.")
            opened, current = os.fstat(self.directory), self.store.directory.stat(follow_symlinks=False)
            if (opened.st_dev, opened.st_ino) != (current.st_dev, current.st_ino):
                raise WorkSessionError("Work-session folder changed. No automatic retry.")
            for lock_name, descriptor in {".writer.lock": self.lock, **self.ownership_locks}.items():
                opened, current = os.fstat(descriptor), os.stat(lock_name, dir_fd=self.directory, follow_symlinks=False)
                if (opened.st_dev, opened.st_ino) != (current.st_dev, current.st_ino):
                    raise WorkSessionError("Work-session writer lock changed. No automatic retry.")
            data = _bytes(self.record)
            if len(data) > MAX_RECORD_BYTES:
                raise WorkSessionError("Work-session evidence exceeded its bounded storage limit.")
            temporary = "." + str(uuid4()) + ".tmp"
            descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=self.directory)
            with os.fdopen(descriptor, "wb") as file:
                file.write(data)
                file.flush()
                os.fsync(file.fileno())
            if self.store._raw(self.directory, name) != self.expected:
                raise WorkSessionError("Work-session file changed during save. No overwrite or automatic retry.")
            os.replace(temporary, name, src_dir_fd=self.directory, dst_dir_fd=self.directory)
            temporary = None
            os.fsync(self.directory)
            self.expected = data
            self.last_publish = time.monotonic()
        except (OSError, ValueError, WorkSessionError) as exc:
            self.failed_write = True
            if isinstance(exc, WorkSessionError):
                raise
            raise WorkSessionError("Could not durably save work evidence. No automatic retry; inspect any partial work.") from None
        finally:
            if temporary is not None:
                try:
                    os.unlink(temporary, dir_fd=self.directory)
                except OSError:
                    pass

    def dispatch(self) -> None:
        self.record.update(status="dispatching", dispatched_at=timestamp(), updated_at=timestamp())
        self._save()

    def observe(self, event: dict) -> None:
        force = False
        if event.get("event") == "auto_skills":
            validate_auto_skills(event.get("report"), self.record)
            self.record["auto_skills"] = deepcopy(event["report"])
            force = True
        elif event.get("event") == "work_log":
            value = public_work_log(event.get("log", {}))
            if not value:
                return
            before = self.record["work_log"]
            force = (value.get("status") != before.get("status")
                     or [(row.get("id"), row.get("status")) for row in value["entries"]]
                     != [(row.get("id"), row.get("status")) for row in before.get("entries", [])])
            self.record["work_log"] = value
        elif event.get("event") == "agent_activity":
            row = public_tool(event.get("item", {}))
            if row is None:
                return
            old = next((item for item in self.record["tools"] if item["id"] == row["id"]), None)
            if old == row:
                return
            if old is None and len(self.record["tools"]) >= 64:
                raise WorkSessionError("Durable activity limit reached. Inspect work before continuing manually.")
            self.record["tools"] = [item for item in self.record["tools"] if item["id"] != row["id"]] + [row]
            force = True
        elif event.get("event") == "agent_run":
            receipt = event.get("receipt", {})
            self.record["agent_status"] = display_text(receipt.get("status"), 40)
            self.record["execution_may_have_occurred"] = receipt.get("execution_may_have_occurred") is True
            self.record["network_access_performed"] = receipt.get("network_access_performed") is True
            self.record["computer_use_performed"] = receipt.get("computer_use_performed") is True
            self.record["screen_access_performed"] = receipt.get("screen_access_performed") is True
            contract = receipt.get("contract")
            if contract is not None:
                try:
                    public = public_agent_contract(contract)
                    digest = contract_hash(public)
                    if receipt.get("contract_hash") != digest or self.record.get("workspace") != public["workspace"]:
                        raise ValueError()
                    self.record["agent_contract"] = public
                    self.record["agent_contract_hash"] = digest
                    inventory = receipt.get("runtime_inventory")
                    if inventory is not None:
                        tools = inventory.get("computer_use_tools") if isinstance(inventory, dict) else None
                        if not isinstance(tools, list) or any(not isinstance(item, str) for item in tools):
                            raise ValueError()
                        verified = validate_runtime_inventory(public, set(tools))
                        if inventory != verified:
                            raise ValueError()
                        self.record["agent_runtime_inventory"] = verified
                except (KeyError, TypeError, ValueError):
                    raise WorkSessionError("Invalid Native agent contract evidence. The turn was stopped without retry.") from None
            force = True
        else:
            return
        self.record["updated_at"] = timestamp()
        if force or time.monotonic() - self.last_publish >= 0.5:
            self._save()

    def complete(self, answer: str, *, artifacts: dict | None = None,
                 instruction_receipt: dict | None = None) -> dict:
        updated = deepcopy(self.record)
        if artifacts is not None:
            if not valid_artifact_snapshot(artifacts, updated):
                raise WorkSessionError("Invalid artifact evidence; no invented success was saved.")
        if instruction_receipt is not None:
            try:
                validate_instruction_receipt(instruction_receipt)
            except ValueError:
                raise WorkSessionError("Invalid instruction receipt. Nothing was saved.") from None
            if (instruction_receipt["provider"] != updated.get("provider")
                    or instruction_receipt["mode"] != updated.get("access_mode")):
                raise WorkSessionError("Instruction receipt does not match this work session. Nothing was saved.")
            updated["instruction_receipt"] = deepcopy(instruction_receipt)
        if artifacts is not None:
            updated["artifact_snapshot"] = deepcopy(artifacts)
        updated.update(status="completed", finished_at=timestamp(), updated_at=timestamp(),
                       answer_preview=display_text(answer, 1600))
        if instruction_receipt is not None:
            try:
                updated["turn_receipt"] = build_turn_receipt(work_session=updated, response=answer)
            except ValueError:
                raise WorkSessionError("Invalid Native turn receipt. Nothing was saved.") from None
        self.record = updated
        self._save()
        return self.store._view(self.record, None)

    def __exit__(self, error_type, error, traceback):
        try:
            if error_type is not None and not self.failed_write and self.record:
                self.record.update(status="error", finished_at=timestamp(), updated_at=timestamp(),
                                   failure="The turn did not return a complete result. Inspect saved evidence; no automatic retry.")
                try:
                    self._save()
                except WorkSessionError:
                    pass
        finally:
            self.close()

    def close(self) -> None:
        for descriptor in self.ownership_locks.values():
            os.close(descriptor)
        self.ownership_locks.clear()
        if self.lock is not None:
            os.close(self.lock)
            self.lock = None
        if self.directory_context is not None:
            self.directory_context.__exit__(None, None, None)
            self.directory_context = None
            self.directory = None
