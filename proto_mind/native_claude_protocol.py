"""Content-free error categories, public tool activity rows and bounded pending tool replies."""
import asyncio
from collections import deque
import json
import re
from uuid import uuid4

ERROR_CODES = {"authentication_failed", "billing_error", "rate_limit", "invalid_request", "server_error"}
MAX_UPDATE_LINE = 16 * 1024 * 1024


def resume_point_missing(value):
    """Claude Code refused --resume-session-at while loading, before any model request."""
    data = getattr(value, "data", None)
    turns = data.get("num_turns") if isinstance(data, dict) else getattr(value, "num_turns", None)
    errors = getattr(value, "errors", None)
    return (getattr(value, "subtype", None) == "error_during_execution" and turns == 0 and isinstance(errors, list)
            and any(isinstance(item, str) and item.startswith("No message found with message.uuid of:") for item in errors))


def failure_code(error):
    """The category of an exception that ended the worker, without its text."""
    if isinstance(error, WorkspaceReplyError): return "workspace_connection"
    return "resume_point" if resume_point_missing(error) else "unknown"


def error_code(message, previous=None):
    category = getattr(message, "error", None)
    if category in ERROR_CODES: return category
    if resume_point_missing(message): return "resume_point"
    status = getattr(message, "api_error_status", None)
    if status == 401: return "authentication_failed"
    if status == 403: return "access_denied"
    if status == 429: return "rate_limit"
    if type(status) is int and status >= 500: return "server_error"
    reason = getattr(message, "terminal_reason", None)
    if reason in {"aborted_streaming", "aborted_tools"}: return "cancelled"
    subtype = getattr(message, "subtype", None)
    if subtype == "error_max_turns": return "max_turns"
    if subtype == "error_max_budget_usd": return "max_budget"
    return previous if previous in ERROR_CODES else "unknown"


COMPUTER_ROW_TOOLS = {"click": "click", "double_click": "click", "triple_click": "click", "right_click": "click",
                      "middle_click": "click", "mouse_down": "click", "mouse_up": "click", "move": "move", "drag": "drag",
                      "scroll": "scroll", "type": "type_text", "key": "press_key", "hold_key": "press_key", "wait": "wait",
                      "cursor_position": "cursor"}
_ANSI = re.compile(r"\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07\x1b]*(?:\x07|\x1b\\\\))")
FILE_CHANGE_TOOLS = {"Edit", "MultiEdit", "Write", "NotebookEdit"}


def preview(value, limit, *, tail=False):
    """Bounded display text without terminal control sequences."""
    if not isinstance(value, str):
        return ""
    value = "".join(char for char in _ANSI.sub("", value) if char in "\n\t" or ord(char) >= 32)
    if len(value) <= limit:
        return value
    if tail:
        # Command results and errors are usually at the end.
        head = limit // 4
        return value[:head] + "\n[…]\n" + value[-(limit - head):]
    return value[:limit] + "\n[preview truncated]"


def _lines(value):
    return len(value.splitlines()) if isinstance(value, str) else 0


def tool_row(identifier, name, arguments):
    """One Claude Code tool call as a public activity row in PM's shared item kinds."""
    arguments = arguments if isinstance(arguments, dict) else {}
    name = name if isinstance(name, str) else ""
    text = lambda key, limit: preview(arguments.get(key), limit)
    row = {"id": identifier, "status": "inProgress", "tool": name[:80]}
    if name == "Bash":
        row.update(kind="commandExecution", command=text("command", 1600), text=text("description", 300))
    elif name in FILE_CHANGE_TOOLS:
        path = text("file_path", 1024) or text("notebook_path", 1024)
        edits = [edit for edit in arguments.get("edits", []) if isinstance(edit, dict)] if isinstance(arguments.get("edits"), list) else []
        replacement = arguments.get("content", arguments.get("new_source")) if name in {"Write", "NotebookEdit"} else arguments.get("new_string")
        pairs = [(edit.get("old_string"), edit.get("new_string")) for edit in edits] or [(arguments.get("old_string"), replacement)]
        diff = "\n".join(line for old, new in pairs[:4] for line in
                         [*("- " + part for part in (old.splitlines() if isinstance(old, str) else [])),
                          *("+ " + part for part in (new.splitlines() if isinstance(new, str) else []))])
        change = {"path": path, "additions": sum(_lines(new) for _, new in pairs)}
        if name != "Write":  # An overwrite does not say what it replaced.
            change["deletions"] = sum(_lines(old) for old, _ in pairs)
        row.update(kind="fileChange", paths=[path] if path else [], change_count=1, diff_preview=preview(diff, 3000),
                   file_changes=[change] if path else [])
    elif name == "Read":
        row.update(kind="fileRead", path=text("file_path", 1024))
    elif name in {"Grep", "Glob"}:
        row.update(kind="search", query=text("pattern", 400), path=text("path", 1024))
    elif name in {"WebSearch", "WebFetch"}:
        row.update(kind="webSearch", query=text("query", 1000) or text("prompt", 1000), url=text("url", 1600))
    elif name == "mcp__pm__pm_screen_capture":
        row.update(kind="computerUse", tool="get_app_state", app=text("app", 120))
    elif name == "mcp__pm__pm_screen_zoom":
        row.update(kind="computerUse", tool="zoom")
    elif name == "mcp__pm__pm_computer_action":
        # Like Codex's Computer Use rows: the action only, never typed text or coordinates.
        row.update(kind="computerUse", tool=COMPUTER_ROW_TOOLS.get(arguments.get("action"), "computer_action"))
    elif name == "mcp__pm__pm_computer_batch":
        steps = arguments.get("steps") if isinstance(arguments.get("steps"), list) else []
        names = [COMPUTER_ROW_TOOLS.get(step.get("action"), "computer_action") for step in steps[:16] if isinstance(step, dict)]
        row.update(kind="computerUse", tool="batch", note=" · ".join(names))
    elif name.startswith("mcp__pm__"):
        row.update(kind="dynamicToolCall", tool=name[len("mcp__pm__"):][:80])
    else:
        summary = next((value for value in (text(key, 300) for key in ("description", "query", "prompt", "skill")) if value), "")
        row.update(kind="agentTool", text=summary)
    return {key: value for key, value in row.items() if value not in ("", [])}


def tool_result_text(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(block.get("text", "") for block in content if isinstance(block, dict) and block.get("type") == "text")
    return ""


def edit_counts(result):
    """Exact (added, removed) lines from Claude Code's structured edit result: the patch hunks,
    or the whole content of a newly created file. None when the result has no patch."""
    if not isinstance(result, dict) or not isinstance(result.get("structuredPatch"), list):
        return None
    patch = result["structuredPatch"]
    if not patch and result.get("type") == "create" and isinstance(result.get("content"), str):
        return _lines(result["content"]), 0
    lines = [line for hunk in patch if isinstance(hunk, dict) and isinstance(hunk.get("lines"), list)
             for line in hunk["lines"] if isinstance(line, str)]
    return sum(line.startswith("+") for line in lines), sum(line.startswith("-") for line in lines)


def tool_finished(row, content, is_error, duration_ms, structured=None):
    """The same row after its result: status, duration and a bounded result preview."""
    row = {**row, "status": "failed" if is_error else "completed", "duration_ms": max(0, int(duration_ms))}
    result = tool_result_text(content)
    counts = edit_counts(structured) if row.get("kind") == "fileChange" and not is_error else None
    if counts and len(row.get("file_changes") or []) == 1:
        # The arguments only estimate an edit (a rewrite does not say what it replaced); the patch is exact.
        row["file_changes"] = [{**row["file_changes"][0], "additions": counts[0], "deletions": counts[1]}]
    if row.get("kind") == "commandExecution":
        row["output_preview"] = preview(result, 3000, tail=True)
    elif is_error or row.get("kind") in {"search", "webSearch", "dynamicToolCall", "agentTool"}:
        # File contents are not repeated; failures and short results are.
        row["output_preview"] = preview(result, 600)
    return {key: value for key, value in row.items() if value != ""}


class UsageMeter:
    """Content-free token counts for one turn, per provider request.

    A resumed Claude Code session restores its accumulated totals, so the result
    message's usage and cost can span earlier turns; counting each request by
    its message ID keeps the numbers to this turn.
    """
    CONTEXT = ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")
    COUNTS = (*CONTEXT, "output_tokens", "thinking_tokens")

    def __init__(self):
        self.requests, self.current = {}, None

    def observe(self, message):
        """Takes assistant messages (main or subagent) and main-thread stream events."""
        event = getattr(message, "event", None)
        if isinstance(event, dict):
            if event.get("type") == "message_start" and isinstance(event.get("message"), dict):
                self.current = event["message"].get("id")
                self._add(self.current, event["message"].get("usage"), False)
            elif event.get("type") == "message_delta":
                self._add(self.current, event.get("usage"), False)
            return
        self._add(getattr(message, "message_id", None), getattr(message, "usage", None),
                  getattr(message, "parent_tool_use_id", None) is not None)

    def _add(self, identifier, usage, nested):
        if not isinstance(identifier, str) or not isinstance(usage, dict):
            return
        if identifier not in self.requests:
            if len(self.requests) >= 100_000: return
            self.requests[identifier] = {"nested": nested, **dict.fromkeys(self.COUNTS, 0)}
        row, details = self.requests[identifier], usage.get("output_tokens_details")
        values = {**usage, "thinking_tokens": details.get("thinking_tokens") if isinstance(details, dict) else None}
        for key in self.COUNTS:
            # Streamed counts are cumulative within one request.
            if type(values.get(key)) is int and 0 <= values[key] < 10**10:
                row[key] = max(row[key], values[key])

    def summary(self):
        rows = list(self.requests.values())
        return {"requests": sum(not row["nested"] for row in rows), "subagent_requests": sum(row["nested"] for row in rows),
                "context_max": max((sum(row[key] for key in self.CONTEXT) for row in rows), default=0),
                **{key: sum(row[key] for row in rows) for key in self.COUNTS}}


class WorkspaceReplyError(RuntimeError):
    pass


class WorkspaceReplies:
    def __init__(self, emit, *, timeout=95):
        self.emit, self.timeout = emit, timeout
        self.pending = {}
        self.expired, self.expired_order = set(), deque()
        self.failed = False

    async def read(self, reader, on_update=None):
        try:
            while True:
                raw = await reader.readline()
                if not raw or len(raw) > MAX_UPDATE_LINE: break
                reply = json.loads(raw)
                # An operator update for the running turn may carry images;
                # workspace tool replies keep their smaller bound.
                if isinstance(reply, dict) and reply.get("event") == "update" and on_update is not None:
                    await on_update(reply)
                    continue
                if len(raw) > 1_048_576 or not isinstance(reply, dict) or not isinstance(reply.get("id"), str): break
                identifier = reply["id"]
                future = self.pending.get(identifier)
                # A known timed-out/cancelled call cannot satisfy a new call and
                # must not take down unrelated work when its late result arrives.
                if identifier in self.expired or future is not None and future.cancelled(): continue
                if future is None or future.done(): break
                future.set_result(reply)
        except (ValueError, UnicodeError, OSError):
            pass
        self.failed = True
        for future in self.pending.values():
            if not future.done(): future.set_exception(WorkspaceReplyError("Workspace connection closed"))

    async def call(self, name, arguments):
        if self.failed: raise WorkspaceReplyError("Workspace connection closed")
        identifier = str(uuid4())
        future = asyncio.get_running_loop().create_future()
        self.pending[identifier] = future
        self.emit({"event": "tool", "id": identifier, "name": name, "arguments": arguments})
        try:
            return await asyncio.wait_for(future, timeout=self.timeout)
        except (TimeoutError, asyncio.CancelledError) as error:
            self.expired.add(identifier); self.expired_order.append(identifier)
            if len(self.expired_order) > 4096: self.expired.discard(self.expired_order.popleft())
            if isinstance(error, asyncio.CancelledError): raise
            return {"success": False, "error": "The tool reply timed out. Its outcome may be unknown; inspect partial work and do not automatically repeat the action."}
        finally:
            self.pending.pop(identifier, None)

    def close(self):
        self.failed = True
        for future in self.pending.values(): future.cancel()
