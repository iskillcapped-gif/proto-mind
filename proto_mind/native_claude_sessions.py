"""Exact Claude session bindings, separate from credentials and private backups.

Planning is read-only. A cross-process lease revalidates the plan before dispatch;
only a confirmed answer can authorize the next resume. No replay on uncertainty.
"""
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import stat
from uuid import UUID, uuid4

from proto_mind.native_locks import open_sidecar
from proto_mind.native_private_backup import atomic_file, read_file, safe_directory, encoded
from proto_mind.private_state_gate import generation, require_available

SCHEMA = "proto_mind.claude_session.v1"
BOOTSTRAP_CHARACTERS = 300_000
BOOTSTRAP_MESSAGES = 2000
PARTIAL_HISTORY = "[Earlier conversation text omitted from this bootstrap; do not infer missing details.]\n"


def text_hash(text):
    return hashlib.sha256(text.strip().encode()).hexdigest()


def bootstrap_history(value):
    if not isinstance(value, list) or len(value) > BOOTSTRAP_MESSAGES:
        raise ValueError("Invalid Claude conversation history.")
    for row in value:
        if not isinstance(row, dict) or row.get("role") not in {"user", "assistant"} or not isinstance(row.get("content"), str):
            raise ValueError("Invalid Claude history message.")
    if sum(len(row["content"]) for row in value) <= BOOTSTRAP_CHARACTERS:
        return [{"role":row["role"], "content":row["content"]} for row in value]
    remaining, selected = BOOTSTRAP_CHARACTERS - len(PARTIAL_HISTORY), []
    for row in reversed(value):
        content = row["content"]
        if remaining <= len(PARTIAL_HISTORY): break
        if len(content) > remaining:
            content = PARTIAL_HISTORY + content[-(remaining-len(PARTIAL_HISTORY)):]
        selected.append({"role": row["role"], "content": content})
        remaining -= len(content)
    selected.reverse()
    if len(selected) < len(value) and selected and not selected[0]["content"].startswith(PARTIAL_HISTORY):
        selected[0]["content"] = PARTIAL_HISTORY + selected[0]["content"]
    return selected


def auth_epoch(state):
    path = state / "claude_sessions" / "auth_epoch"
    return read_file(path, 128).decode() if os.path.lexists(path) else ""


def invalidate_login(state):
    atomic_file(state.resolve() / "claude_sessions" / "auth_epoch", str(uuid4()).encode())


class ClaudeSessionPlan:
    def __init__(self, state, conversation, *, account, workspace, full_access, tools, history):
        self.state = state.resolve()
        self.conversation = str(UUID(conversation))
        self.directory = self.state / "claude_sessions"
        self.path = self.directory / (self.conversation + ".json")
        self.generation = generation(self.state)
        require_available(self.state)
        self.binding = {
            "account": text_hash(json.dumps({key: account.get(key) for key in ("email", "authMethod", "apiProvider")}, sort_keys=True)),
            "login": auth_epoch(self.state), "generation": self.generation.hex() if self.generation else None,
            "workspace": workspace, "mode": "full_access" if full_access else "chat", "tools": bool(tools),
            "contract": 1,
        }
        self.baseline = self._read()
        previous = self._parse(self.baseline) if self.baseline else None
        self.resumed = bool(account.get("email") and previous and previous["state"] == "ready"
                            and previous["binding"] == self.binding and history
                            and history[-1]["role"] == "assistant"
                            and text_hash(history[-1]["content"]) == previous["answer_hash"])
        self.session_id = previous["session_id"] if self.resumed else str(uuid4())
        self.history = [] if self.resumed else bootstrap_history(history)
        self._leased = False

    def _read(self):
        return read_file(self.path, 16_384) if os.path.lexists(self.path) else None

    @staticmethod
    def _parse(raw):
        try:
            value = json.loads(raw)
            if (set(value) != {"schema", "binding", "session_id", "answer_hash", "state"}
                    or value["schema"] != SCHEMA or value["state"] not in {"ready", "in_flight"}
                    or not isinstance(value["binding"], dict)
                    or str(UUID(value["session_id"])) != value["session_id"]
                    or not isinstance(value["answer_hash"], str)
                    or len(value["answer_hash"]) != 64):
                raise ValueError()
            return value
        except (ValueError, TypeError, KeyError, AttributeError):
            raise ValueError("Claude session metadata is unreadable. It was preserved; no task was sent.") from None

    def public(self):
        return {"schema": SCHEMA, "linked": self.resumed, "thread_id_short": self.session_id[:8],
                "bootstrap_messages": len(self.history),
                "bootstrap_partial": bool(self.history and self.history[0]["content"].startswith(PARTIAL_HISTORY))}

    def _save(self, state, answer_hash):
        require_available(self.state)
        if generation(self.state) != self.generation or auth_epoch(self.state) != self.binding["login"]:
            raise ValueError("Claude account or restored data changed. No session continuation was saved.")
        raw = encoded({"schema": SCHEMA, "binding": self.binding, "session_id": self.session_id,
                       "answer_hash": answer_hash, "state": state})
        atomic_file(self.path, raw)
        if self._read() != raw: raise ValueError("Could not verify the saved Claude session.")

    @contextmanager
    def lease(self):
        safe_directory(self.directory, create=True)
        folder = os.open(self.directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        descriptor = None
        try:
            name = self.conversation + ".lock"
            descriptor = open_sidecar(name, directory=folder)
            if not stat.S_ISREG(os.fstat(descriptor).st_mode): raise ValueError("Invalid Claude session lock.")
            try: fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError: raise ValueError("This Claude conversation is already running in another process.") from None
            opened, current = os.fstat(descriptor), os.stat(name, dir_fd=folder, follow_symlinks=False)
            if (opened.st_dev, opened.st_ino) != (current.st_dev, current.st_ino) or self._read() != self.baseline:
                raise ValueError("Claude session changed before dispatch. No task was sent.")
            self._save("in_flight", text_hash(""))
            self._leased = True
            yield self
        finally:
            self._leased = False
            if descriptor is not None: os.close(descriptor)
            os.close(folder)

    def complete(self, session_id, answer):
        if not self._leased or session_id != self.session_id:
            raise ValueError("Claude returned another session. No continuation was saved.")
        self._save("ready", text_hash(answer))
