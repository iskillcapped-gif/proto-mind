"""Content-free error categories and bounded pending tool replies."""
import asyncio
from collections import deque
import json
from uuid import uuid4

ERROR_CODES = {"authentication_failed", "billing_error", "rate_limit", "invalid_request", "server_error"}


def error_code(message, previous=None):
    category = getattr(message, "error", None)
    if category in ERROR_CODES: return category
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

    async def read(self, reader):
        try:
            while True:
                raw = await reader.readline()
                if not raw or len(raw) > 1_048_576: break
                reply = json.loads(raw)
                if not isinstance(reply, dict) or not isinstance(reply.get("id"), str): break
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
