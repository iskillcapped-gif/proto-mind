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
