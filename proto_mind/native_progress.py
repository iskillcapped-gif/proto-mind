"""Display-only public commentary and observed work, never raw model reasoning."""
from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
import re
import time
from uuid import uuid4


MAX_WORK_ITEMS = 96
_ANSI = re.compile(r"\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07\x1b]*(?:\x07|\x1b\\))")


def display_text(value: object, limit: int) -> str:
    if not isinstance(value, str):
        return ""
    value = _ANSI.sub("", value)
    value = "".join(char for char in value if char in "\n\t" or ord(char) >= 32)
    return value if len(value) <= limit else value[:limit] + "\n[preview truncated]"


def timestamp() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


class WorkLog:
    def __init__(self, emit, mode: str) -> None:
        self.emit = emit or (lambda _: None)
        self.started = time.monotonic()
        self.last_publish = float("-inf")
        self.entries: dict[str, dict] = {}
        self.log = {"schema": "proto_mind.native_work_log.v1", "id": str(uuid4()),
                    "access_mode": mode, "started_at": timestamp(), "status": "running",
                    "stage": "connecting", "public_only": True, "truncated": False,
                    "state_version": 0}
        self.publish(force=True)

    def publish(self, *, force: bool = False) -> None:
        now = time.monotonic()
        if not force and now - self.last_publish < 0.1:
            return
        self.last_publish = now
        self.log["state_version"] += 1
        self.emit({"event": "work_log", "log": deepcopy({**self.log, "entries": list(self.entries.values())})})

    def stage(self, name: str) -> None:
        if name in {"connecting", "working", "answering"} and self.log["stage"] != name:
            self.log["stage"] = name
            self.publish(force=True)

    def _record(self, row: dict, *, force: bool = False) -> None:
        key = row["id"]
        if key not in self.entries and len(self.entries) >= MAX_WORK_ITEMS:
            self.log["truncated"] = True
        else:
            self.entries[key] = row
        self.log["stage"] = "working"
        self.publish(force=force)

    def commentary(self, item_id: str, text: str, completed: bool) -> None:
        self._record({"id": "commentary:" + item_id, "kind": "commentary",
                      "text": display_text(text, 4000), "status": "completed" if completed else "inProgress"}, force=completed)

    def tool(self, item: dict) -> None:
        if item.get("kind") not in {"commandExecution", "fileChange", "imageView", "webSearch", "computerUse", "plan"}:
            return
        # The separately bounded agent receipt owns command/output bodies.
        self._record({"id": "tool:" + item["id"], "kind": "tool", "tool_id": item["id"],
                      "tool_kind": item["kind"], "status": item.get("status", "unknown")}, force=True)

    def observe(self, method: str, params: dict) -> None:
        if method == "turn/plan/updated" and isinstance(params.get("plan"), list):
            steps = [{"step": display_text(step.get("step"), 300), "status": step["status"]}
                     for step in params["plan"][:12] if isinstance(step, dict)
                     and step.get("status") in {"pending", "inProgress", "completed"}
                     and isinstance(step.get("step"), str)]
            if steps:
                self._record({"id": "public-plan", "kind": "plan", "steps": steps,
                              "text": display_text(params.get("explanation"), 1000)}, force=True)
        if method in {"item/started", "item/completed"}:
            item = params.get("item") or {}
            if item.get("type") == "reasoning":
                self.stage("working")  # Presence only; no content or summary is copied.
            if item.get("type") == "contextCompaction" and method == "item/completed":
                self._record({"id": "compaction:" + display_text(item.get("id"), 160),
                              "kind": "context_compaction", "text": "Context compacted by provider.",
                              "status": "completed"}, force=True)

    def finish(self, status: str) -> None:
        self.log.update(status=status, finished_at=timestamp(), elapsed_ms=max(0, int((time.monotonic() - self.started) * 1000)))
        for row in self.entries.values():
            if row.get("status") == "inProgress":
                row["status"] = "unknown"
        self.publish(force=True)


class PublicMessages:
    """Separate commentary from final answers, including providers with late phases."""

    def __init__(self, on_delta, progress: WorkLog, *, limit: int, error_type) -> None:
        self.on_delta, self.progress, self.limit, self.error_type = on_delta, progress, limit, error_type
        self.phases: dict[str, str | None] = {}
        self.texts: dict[str, str] = {}
        self.completed: dict[str, str] = {}
        self.finals: dict[str, str] = {}
        self.streamed: set[str] = set()

    def _text(self, item_id: object, text: object) -> str:
        if not isinstance(item_id, str) or not item_id or len(item_id) > 160 or not isinstance(text, str):
            raise self.error_type("Invalid public answer stream.")
        if item_id not in self.texts and len(self.texts) >= 128:
            raise self.error_type("Answer exceeded the local message limit.")
        if len(text) + sum(len(value) for key, value in self.texts.items() if key != item_id) > self.limit:
            raise self.error_type("Answer exceeded the local display limit.")
        self.texts[item_id] = text
        return item_id

    def observe(self, method: str, params: dict) -> None:
        self.progress.observe(method, params)
        if method in {"item/started", "item/completed"}:
            item = params.get("item") or {}
            if item.get("type") != "agentMessage":
                return
            item_id = self._text(item.get("id"), item.get("text", ""))
            phase = item.get("phase") or self.phases.get(item_id)
            if phase not in {None, "commentary", "final_answer"}:
                raise self.error_type("Unknown public message phase; no internal text was displayed.")
            self.phases[item_id] = phase
            if phase == "commentary":
                self.progress.commentary(item_id, self.texts[item_id], method == "item/completed")
            elif method == "item/completed":
                self.completed[item_id] = self.texts[item_id]
                if phase == "final_answer":
                    self.finals[item_id] = self.texts[item_id]
                if item_id not in self.streamed:
                    self.progress.stage("answering")
                    self.on_delta(self.texts[item_id])
                    self.streamed.add(item_id)
        elif method == "item/agentMessage/delta":
            item_id, delta = params.get("itemId"), params.get("delta")
            if not isinstance(delta, str):
                raise self.error_type("Invalid public answer stream.")
            if len(delta) > self.limit:
                raise self.error_type("Answer exceeded the local display limit.")
            if not isinstance(item_id, str):
                raise self.error_type("Invalid public answer stream.")
            item_id = self._text(item_id, self.texts.get(item_id, "") + delta)
            phase = self.phases.get(item_id)
            if phase == "commentary":
                self.progress.commentary(item_id, self.texts[item_id], False)
            elif phase == "final_answer":
                self.progress.stage("answering")
                self.on_delta(delta)
                self.streamed.add(item_id)
            # Unknown phases wait for completion instead of leaking commentary
            # into the answer or guessing that private reasoning is user-facing.

    def answer(self) -> str:
        candidates = self.finals or dict(list(self.completed.items())[-1:])
        if not candidates:
            candidates = dict([(key, text) for key, text in self.texts.items()
                               if self.phases.get(key) != "commentary"][-1:])
        return "\n\n".join(candidates.values()).strip()
