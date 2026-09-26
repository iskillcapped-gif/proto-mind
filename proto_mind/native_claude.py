"""Claude Code through Anthropic's unmodified Agent SDK and account flow.

The SDK runs in a separate interpreter so its dependencies and process lifetime
cannot contaminate another provider. Credentials are owned by Claude Code;
Proto-Mind only reads its public authentication status.
"""
from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import threading
from contextlib import nullcontext
from uuid import uuid4

from proto_mind.native_api import NativeAPIReasoner
from proto_mind.native_codex import TurnCancelled
from proto_mind.native_progress import WorkLog, timestamp
from proto_mind.native_workspace_tools import TOOLS
from proto_mind.native_claude_contract import turn_context_message, validate_effort
from proto_mind.native_claude_sessions import INTERRUPTED_NOTICE, invalidate_login, text_hash

MAX_LINE = 1_048_576
MODEL = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/\[\]-]{0,159}\Z")


def runtime_path() -> Path:
    root = Path(__file__).resolve().parent.parent
    bundled = root / "claude_packages"
    return bundled if bundled.is_dir() else root / "dist" / f"claude-runtime-{sys.version_info.major}.{sys.version_info.minor}"


def executable() -> Path:
    runtime = runtime_path()
    binary = runtime / "claude_agent_sdk/_bundled/claude"
    if not (runtime / "proto-mind-claude-runtime.json").is_file() or not binary.is_file() or not os.access(binary, os.X_OK):
        raise ValueError("Claude runtime is missing. Install the current Proto-Mind build.")
    return binary


def profile_directory(state: Path, *, create=False) -> Path:
    profile = state / "claude-profile"
    if state.is_symlink() or profile.is_symlink():
        raise ValueError("Claude profile must not be a symbolic link.")
    if create:
        profile.mkdir(parents=True, exist_ok=True, mode=0o700)
        profile.chmod(0o700)
    return profile


def environment(state: Path) -> dict[str, str]:
    # In particular, never inherit ANTHROPIC_API_KEY, OAuth tokens, alternate
    # provider endpoints or SDK switches from another application's environment.
    env = {key: value for key, value in os.environ.items()
           if key in {"HOME", "USER", "LOGNAME", "LANG", "LC_ALL", "TMPDIR", "SHELL"}}
    env.update(PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin",
               CLAUDE_CONFIG_DIR=str(profile_directory(state)), PYTHONNOUSERSITE="1",
               PYTHONDONTWRITEBYTECODE="1", DISABLE_UPDATES="1", ENABLE_CLAUDEAI_MCP_SERVERS="false")
    return env


def status(state: Path) -> dict:
    try:
        binary = executable()
    except ValueError:
        return {"installed": False, "connected": False}
    result = {"installed": True, "connected": False}
    if not profile_directory(state).is_dir():
        return result
    try:
        response = subprocess.run([str(binary), "auth", "status", "--json"], env=environment(state),
                                  stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                  timeout=20, cwd=state)
        if len(response.stdout) > 65_536:
            raise ValueError("Claude authentication status is too large.")
        value = json.loads(response.stdout)
        if not isinstance(value, dict):
            raise ValueError("Invalid Claude authentication status.")
        result["connected"] = value.get("loggedIn") is True
        for key in ["authMethod", "email", "subscriptionType", "apiProvider"]:
            if isinstance(value.get(key), str):
                result[key] = value[key][:200]
        return result
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return {**result, "error": "Could not read Claude Code account status. No model request was made."}


def authentication_command(state: Path, operation: str) -> dict:
    if operation not in {"login", "logout"}:
        raise ValueError("Unknown Claude authentication action.")
    binary = executable()
    profile = profile_directory(state, create=True)
    invalidate_login(state)
    return {"executable": str(binary), "arguments": ["auth", operation],
            "environment": environment(state), "directory": str(profile)}


class ClaudeTransport:
    def __init__(self, state: Path, *, workspace: Path | None, full_access: bool, effort="", images=(), session_plan=None):
        self.state, self.workspace, self.full_access = state, workspace, full_access
        self.effort, self.images = effort, images
        self.session_plan = session_plan
        self.usage = None
        self.undelivered_updates = []
        self.workspace_tools = None
        self.on_activity = lambda _: None
        self.on_progress = lambda _: None
        self.on_steering = lambda _: None
        self.write_lock = threading.Lock()
        self.update_acks = {}
        self.tool_rows = {}
        self.cancelled = threading.Event()
        self.process = None
        self.lock = threading.Lock()
        self.termination_lock = threading.Lock()

    def cancel(self):
        self.cancelled.set()
        if self.workspace_tools is not None:
            self.workspace_tools.cancel()
        with self.lock:
            process = self.process
        if process is not None:
            self._terminate(process)

    def _terminate(self, process):
        # Only the group created for this exact SDK worker, never other Claude
        # sessions or the shared desktop. Detached children remain a Full Mac limit.
        with self.termination_lock:
            # Cancellation and the stream's finally block can arrive together.
            # Reap before signalling: macOS may return EPERM for an exited group.
            if process.poll() is not None: return
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            except PermissionError:
                if process.poll() is not None: return
                process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                try: os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError: pass
                process.wait(timeout=3)

    def answer(self, model, instructions, history, prompt, on_delta):
        if self.cancelled.is_set(): raise TurnCancelled("Claude task stopped.")
        if model and not MODEL.fullmatch(model):
            raise ValueError("Invalid Claude model identifier.")
        validate_effort(self.effort)
        account = status(self.state)
        if not account["connected"]:
            raise ValueError("Sign in through Claude Code in Settings → Connections first.")
        if self.session_plan and self.session_plan.binding["account"] != text_hash(json.dumps(
                {key: account.get(key) for key in ("email", "authMethod", "apiProvider")}, sort_keys=True)):
            raise ValueError("Claude account changed before dispatch. No task was sent.")
        with self.session_plan.lease() if self.session_plan else nullcontext():
            return self._answer(model, instructions, history, prompt, on_delta)

    def _write(self, process, value):
        # Tool replies and operator updates share the worker's stdin.
        with self.write_lock:
            process.stdin.write(json.dumps(value, ensure_ascii=False).encode() + b"\n"); process.stdin.flush()

    def steer(self, identifier, text, images=()):
        """Adds an operator update to the running turn: accepted, rejected or unknown."""
        with self.lock:
            process = self.process
        if process is None or process.poll() is not None or self.cancelled.is_set():
            return "rejected"
        try:
            blocks = [{"type": "text", "text": text}, *(claude_image(item) for item in images)]
        except (AttributeError, KeyError, ValueError):
            return "rejected"
        waiter = threading.Event()
        self.update_acks[identifier] = [waiter, "unknown"]
        try:
            self._write(process, {"event": "update", "id": identifier, "content": blocks})
        except (OSError, ValueError):
            return self.update_acks.pop(identifier)[1]
        waiter.wait(10)
        return self.update_acks.pop(identifier)[1]

    def _receipt(self, status):
        rows = list(self.tool_rows.values())
        kinds = [row.get("kind") for row in rows]
        return {"schema": "proto_mind.claude_agent_run.v1", "provider": "claude", "run_id": str(uuid4()),
                "status": status, "items": rows[-64:], "items_truncated": len(rows) > 64,
                "workspace_root": str(self.workspace) if self.workspace else "",
                "command_count": kinds.count("commandExecution"), "web_search_count": kinds.count("webSearch"),
                "computer_use_count": 0, "finished_at": timestamp(),
                "execution_may_have_occurred": any(kind not in {"fileRead", "search", "webSearch"} for kind in kinds),
                "network_access_performed": "webSearch" in kinds, "computer_use_performed": False, "screen_access_performed": False}

    def _abandon_unusable_session(self, progressed, code):
        # A resumed session that fails before producing anything, for no known
        # account/service reason, may be missing or damaged. Do not offer it again.
        plan = self.session_plan
        if plan and plan.resumed and not progressed and code in {None, "unknown"} and not self.cancelled.is_set():
            try: plan.abandon()
            except (OSError, ValueError): pass

    def _confirm_session(self, session_id, answer):
        if self.session_plan:
            # The answer itself is complete; a failed binding update only means
            # the next turn starts a fresh session from local history.
            try: self.session_plan.complete(session_id, answer)
            except (OSError, ValueError): pass

    def _answer(self, model, instructions, history, prompt, on_delta):
        binary = executable()
        env = environment(self.state)
        env["PYTHONPATH"] = os.pathsep.join([str(runtime_path()), str(Path(__file__).resolve().parent.parent)])
        if self.session_plan and self.session_plan.interrupted:
            prompt = INTERRUPTED_NOTICE + prompt
        payload = {"model": model, "effort": self.effort, "instructions": instructions,
                   "history": self.session_plan.history if self.session_plan else history,
                   "session_id": self.session_plan.session_id if self.session_plan else None,
                   "resume": self.session_plan.resumed if self.session_plan else False,
                   "prompt": prompt, "full_access": self.full_access,
                   "cli": str(binary), "workspace": str(self.workspace or profile_directory(self.state)),
                   "tools": TOOLS if self.workspace_tools else [],
                   "images": [{"type": "image", "source": {"type": "base64", "media_type": image.mime_type,
                               "data": base64.b64encode(image.data).decode()}} for image in self.images]}
        progress = WorkLog(self.on_progress, "full_access" if self.full_access else "chat")
        outcome = "failed"
        process = None
        seen_calls = set()
        progressed = False
        try:
            with self.lock:
                if self.cancelled.is_set(): raise TurnCancelled("Claude task stopped.")
                process = subprocess.Popen([sys.executable, "-S", "-u", "-m", "proto_mind.native_claude_worker"],
                    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                    env=env, cwd=profile_directory(self.state), start_new_session=True)
                self.process = process
            self._write(process, payload)
            while not self.cancelled.is_set():
                raw = process.stdout.readline(MAX_LINE + 1)
                if not raw: break
                if len(raw) > MAX_LINE: raise RuntimeError("Claude event exceeded its buffer limit.")
                event = json.loads(raw)
                kind = event.get("event")
                progressed = progressed or kind in {"delta", "commentary", "stage", "activity", "tool"}
                if kind == "delta":
                    on_delta(event["text"])
                elif kind == "commentary":
                    progress.commentary(event["id"], event["text"], True)
                    self.on_progress({"event": "answer_reset"})
                elif kind == "stage": progress.stage(event["stage"])
                elif kind == "activity":
                    row = event["item"]
                    self.tool_rows.pop(row["id"], None); self.tool_rows[row["id"]] = row
                    self.on_activity({"event": "agent_activity", "item": row}); progress.tool(row)
                elif kind == "tool":
                    call_id = event["id"]
                    if self.workspace_tools is None or call_id in seen_calls:
                        raise RuntimeError("Claude requested an unavailable or repeated workspace call.")
                    seen_calls.add(call_id)
                    try:
                        result = self.workspace_tools.call(event["name"], event["arguments"])
                        reply = {"id": call_id, "result": result, "success": True}
                    except (ValueError, RuntimeError) as exc:
                        reply = {"id": call_id, "error": str(exc)[:600], "success": False}
                    if self.cancelled.is_set(): break
                    self._write(process, reply)
                elif kind == "steering_ready":
                    self.on_steering(self)
                elif kind == "update_ack":
                    entry = self.update_acks.get(event.get("id"))
                    if entry and event.get("status") in {"accepted", "rejected", "unknown"}:
                        entry[1] = event["status"]; entry[0].set()
                elif kind == "result":
                    if self.cancelled.is_set(): raise TurnCancelled("Claude task stopped.")
                    answer = event.get("text")
                    if event.get("success") is not True or not isinstance(answer, str) or not answer.strip() or len(answer) > 250_000:
                        self._abandon_unusable_session(progressed, event.get("error_code"))
                        raise RuntimeError(claude_error(event.get("error_code")))
                    self.usage = event.get("usage") if usage_notice(event.get("usage")) else None
                    undelivered = event.get("undelivered_updates")
                    self.undelivered_updates = undelivered if isinstance(undelivered, list) and len(undelivered) <= 32 else []
                    self._confirm_session(event.get("session_id"), answer.strip())
                    outcome = "completed"
                    return answer.strip()
                elif kind == "error":
                    self._abandon_unusable_session(progressed, event.get("error_code"))
                    raise RuntimeError(claude_error(event.get("error_code")))
            if self.cancelled.is_set(): raise TurnCancelled("Claude task stopped. Earlier changes are not rolled back.")
            self._abandon_unusable_session(progressed, None)
            raise RuntimeError("Claude Code disconnected before completing the task. PM did not resubmit it.")
        except (OSError, ValueError, KeyError, TypeError):
            if self.cancelled.is_set(): raise TurnCancelled("Claude task stopped.") from None
            self._abandon_unusable_session(progressed, None)
            raise RuntimeError("Claude transport failed. PM did not resubmit the task or change providers.") from None
        finally:
            self.on_steering(None)
            if self.tool_rows:
                # Saved answers keep their actions, as a Codex agent receipt does.
                self.on_activity({"event": "agent_run", "receipt": self._receipt(
                    "interrupted" if self.cancelled.is_set() else outcome)})
            if process is not None:
                self._terminate(process)
                for stream in [process.stdin, process.stdout]:
                    if stream: stream.close()
            with self.lock:
                if self.process is process: self.process = None
            progress.finish("interrupted" if self.cancelled.is_set() else outcome)


class NativeClaudeReasoner(NativeAPIReasoner):
    backend_name = "claude_subscription"
    instruction_provider = "claude"

    def _dispatch(self, prepared, prompt):
        # A resumed session keeps its first system prompt, so only the stable
        # part goes there; current memory and Observer labels ride the message.
        return self.transport.answer(self.model, prepared.system_text, self.history,
                                     turn_context_message(prepared.turn_context) + prompt, self.on_delta)


def claude_image(item):
    """A validated `data:` image item from PM's attachment reader as an Anthropic image block."""
    header, data = item["url"].split(",", 1)
    mime = header.removeprefix("data:").removesuffix(";base64")
    if item.get("type") != "image" or not header.endswith(";base64") or mime not in {"image/png", "image/jpeg", "image/gif", "image/webp"}:
        raise ValueError("Unsupported update image.")
    return {"type": "image", "source": {"type": "base64", "media_type": mime, "data": data}}


USAGE_KEYS = ("requests", "subagent_requests", "context_max", "input_tokens", "cache_creation_input_tokens",
              "cache_read_input_tokens", "output_tokens", "thinking_tokens")


def usage_notice(usage):
    """One content-free line for the answer details, or None without per-request counts."""
    if (not isinstance(usage, dict) or set(usage) != set(USAGE_KEYS) or not usage["requests"]
            or any(type(usage[key]) is not int or not 0 <= usage[key] < 10**12 for key in USAGE_KEYS)):
        return None
    def size(value):
        return (f"{value / 1e6:.1f}M" if value >= 999_500 else f"{value / 1e3:.0f}K" if value >= 9_950
                else f"{value / 1e3:.1f}K" if value >= 1000 else str(value))
    subagents = f" plus {usage['subagent_requests']} by subagents" if usage["subagent_requests"] else ""
    thinking = f" including {size(usage['thinking_tokens'])} thinking" if usage["thinking_tokens"] else ""
    plural = "" if usage["requests"] == 1 else "s"
    return (f"Claude usage for this turn: {usage['requests']} model request{plural}{subagents}, context up to "
            f"{size(usage['context_max'])} tokens. Every request re-reads the context: tokens read from cache "
            f"{size(usage['cache_read_input_tokens'])}, written to cache {size(usage['cache_creation_input_tokens'])}, "
            f"uncached input {size(usage['input_tokens'])}, output {size(usage['output_tokens'])}{thinking}.")


def claude_error(code):
    messages = {
        "authentication_failed": "Claude: войдите в аккаунт заново в настройках подключения.",
        "rate_limit": "Claude: достигнут лимит. После обновления (время — в разделе «Лимиты») следующее сообщение продолжит эту же сессию; автоматического повтора не было.",
        "billing_error": "Claude: провайдер сообщил о проблеме оплаты или доступного баланса.",
        "access_denied": "Claude: аккаунту недоступен этот запрос или выбранная модель.",
        "invalid_request": "Claude: запрос или выбранная модель не поддерживается. Проверьте настройки модели.",
        "server_error": "Claude: временная ошибка сервиса. Задача не отправлялась повторно.",
        "cancelled": "Задача Claude остановлена. Уже выполненные действия не отменены.",
        "workspace_connection": "Claude: связь с инструментами PM прервана. Проверьте результат перед продолжением.",
        "max_turns": "Claude: достигнут предел шагов провайдера. Проверьте частичный результат.",
        "max_budget": "Claude: достигнут предел бюджета провайдера. Проверьте частичный результат.",
    }
    return messages.get(code, "Claude не подтвердил завершение ответа. Проверьте подключение и частичный результат; автоматического повтора не было.")
