"""Read-only catalog/quotas through the pinned, unmodified Claude Code process.

Never query a model or read credentials. The get_usage control message is a
versioned CLI capability, not an HTTP/OAuth client. Unsupported CLI responses
remain unavailable rather than turning into invented zero usage.
"""
from __future__ import annotations

import asyncio
from datetime import datetime
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import threading
import time

from proto_mind.native_claude import ClaudeTransport, MODEL, environment, executable, runtime_path, status

SCHEMA = "proto_mind.claude_account.v1"
EFFORTS = {"low", "medium", "high", "xhigh", "max"}


def account_ref(account: dict) -> str:
    fields = [account.get(key, "") for key in ("email", "authMethod", "apiProvider", "subscriptionType")]
    return hashlib.sha256(json.dumps(fields).encode()).hexdigest() if account.get("connected") else ""


def model_title(identifier: str, fallback: str) -> str:
    match = re.fullmatch(r"claude-(opus|sonnet|haiku|fable)-(\d+)(?:-(\d{1,2}))?(?:-\d{8})?(?:\[1m\])?", identifier)
    if not match: return fallback[:100] or identifier
    family, major, minor = match.groups()
    return f"{family.capitalize()} {major}" + (f".{minor}" if minor else "")


def normalize_models(raw) -> list[dict]:
    if not isinstance(raw, list): return []
    result, seen = [], set()
    for row in raw[:64]:
        if not isinstance(row, dict): continue
        alias, resolved = row.get("value"), row.get("resolvedModel")
        if not isinstance(alias, str) or not MODEL.fullmatch(alias): continue
        if not isinstance(resolved, str) or not MODEL.fullmatch(resolved): continue
        identifier = "" if alias == "default" else resolved + ("[1m]" if alias.endswith("[1m]") and not resolved.endswith("[1m]") else "")
        if identifier in seen: continue
        seen.add(identifier)
        result.append({"id": identifier, "alias": "" if alias == "default" else alias,
                       "resolved_id": resolved, "title": model_title(resolved, str(row.get("displayName", ""))),
                       "description": str(row.get("description", ""))[:500],
                       "efforts": [value for value in row.get("supportedEffortLevels", []) if isinstance(value, str) and value in EFFORTS]
                       if isinstance(row.get("supportedEffortLevels"), list) and row.get("supportsEffort") is True else []})
    return result


def number(value):
    return float(value) if type(value) in (int, float) and math.isfinite(value) and value >= 0 else None


def reset_time(value):
    if isinstance(value, str):
        try:
            date = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return date.timestamp() if date.tzinfo is not None else None
        except (ValueError, OverflowError): return None
    return number(value)


def normalize_usage(raw: dict) -> dict:
    available = raw.get("rate_limits_available") is True
    rates = raw.get("rate_limits")
    windows = []
    if available and isinstance(rates, dict):
        def append(identifier, row, minutes, title=""):
            if not isinstance(row, dict): return
            # get_usage reports percent (3 means 3%); stream RateLimitEvent's
            # utilization is a different contract and must not be mixed in.
            used = number(row.get("utilization"))
            windows.append({"id": identifier, "title": title, "window_minutes": minutes,
                            "used_percent": used, "remaining_percent": max(0, 100-used) if used is not None else None,
                            "resets_at": reset_time(row.get("resets_at"))})
        for key, minutes in [("seven_day", 10080), ("five_hour", 300)]:
            append(key, rates.get(key), minutes)
        scoped = rates.get("limits")
        if isinstance(scoped, list):
            for row in scoped[:32]:
                if not isinstance(row, dict) or row.get("kind") != "weekly_scoped": continue
                scope = row.get("scope")
                model = scope.get("model") if isinstance(scope, dict) else None
                if not isinstance(model, dict) or not isinstance(model.get("display_name"), str): continue
                title = model["display_name"][:100]
                identifier = "model_" + hashlib.sha256(title.encode()).hexdigest()[:16]
                if any(value["id"] == identifier for value in windows): continue
                append(identifier, {"utilization": row.get("percent"), "resets_at": row.get("resets_at")}, 10080, title)
        if not any(row["title"] for row in windows):
            for key, title in [("seven_day_opus", "Opus"), ("seven_day_sonnet", "Sonnet")]:
                append(key, rates.get(key), 10080, title)
    return {"limits_available": available, "windows": windows}


async def probe(payload):
    from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient
    options = ClaudeAgentOptions(cli_path=payload["cli"], cwd=payload["directory"], tools=[],
                                 permission_mode="dontAsk", setting_sources=[], strict_mcp_config=True,
                                 extra_args={"no-session-persistence": None})
    async with ClaudeSDKClient(options=options) as client:
        info = await client.get_server_info()
        models = normalize_models(info.get("models") if isinstance(info, dict) else None)
        result = {"models": models, "models_error": "" if models else "catalog_unavailable",
                  "windows": [], "limits_available": False, "limits_error": ""}
        try:
            # Python SDK has no public wrapper yet. Isolate this single pinned
            # CLI control command, and fail visibly if its contract changes.
            usage = await asyncio.wait_for(client._query._send_control_request({"subtype": "get_usage"}), timeout=15)
            if not isinstance(usage, dict): raise ValueError("Invalid usage response")
            result.update(normalize_usage(usage))
        except Exception:
            result["limits_error"] = "usage_unavailable"
        return result


class ClaudeMetadataReader:
    def __init__(self, state: Path):
        self.state = state
        self.transport = ClaudeTransport(state, workspace=None, full_access=False)
        self.read_lock = threading.Lock()

    def close(self):
        self.transport.cancel()

    def read(self) -> dict:
        with self.read_lock:
            if self.transport.cancelled.is_set(): raise RuntimeError("Claude metadata reader closed.")
            account = status(self.state)
            result = {"schema": SCHEMA, "installed": account.get("installed", False),
                      "connected": account.get("connected", False), "email": account.get("email", ""),
                      "plan": account.get("subscriptionType", ""), "account_ref": account_ref(account),
                      "models": [], "windows": [], "models_error": "", "limits_error": "",
                      "limits_available": False, "checked_at": time.time(),
                      "models_updated_at": None, "limits_updated_at": None}
            if not account.get("connected"):
                if account.get("error"): result.update(models_error="account_unavailable", limits_error="account_unavailable")
                return result
            process = None
            try:
                env = environment(self.state)
                env["PYTHONPATH"] = os.pathsep.join([str(runtime_path()), str(Path(__file__).resolve().parent.parent)])
                with self.transport.lock:
                    if self.transport.cancelled.is_set(): raise RuntimeError("Claude metadata reader closed.")
                    process = subprocess.Popen([sys.executable, "-S", "-m", "proto_mind.native_claude_metadata"],
                        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                        cwd=self.state, env=env, start_new_session=True)
                    self.transport.process = process
                output, _ = process.communicate(json.dumps({"cli": str(executable()), "directory": str(self.state / "claude-profile")}).encode(), timeout=30)
                if process.returncode != 0 or len(output) > 131_072: raise ValueError("Invalid metadata worker response")
                payload = json.loads(output)
                if not isinstance(payload, dict) or not isinstance(payload.get("models"), list): raise ValueError("Invalid metadata")
                # An external sign-in may race this read, even though Native
                # blocks its own auth controls while a refresh is in flight.
                after = status(self.state)
                if account_ref(account) != account_ref(after):
                    return {**result, "connected": False, "email": "", "plan": "", "account_ref": "",
                            "models_error": "account_changed", "limits_error": "account_changed"}
                now = time.time()
                result.update(payload, checked_at=now,
                              models_updated_at=now if not payload.get("models_error") else None,
                              limits_updated_at=now if not payload.get("limits_error") and payload.get("limits_available") else None)
                return result
            except (OSError, ValueError, subprocess.TimeoutExpired):
                return {**result, "models_error": "metadata_unavailable", "limits_error": "metadata_unavailable"}
            finally:
                if process is not None:
                    self.transport._terminate(process)
                    for stream in [process.stdin, process.stdout]:
                        if stream: stream.close()
                with self.transport.lock: self.transport.process = None


if __name__ == "__main__":
    try:
        payload = json.loads(sys.stdin.buffer.read(16_385))
        print(json.dumps(asyncio.run(probe(payload)), allow_nan=False))
    except Exception:
        sys.exit(1)  # Never return SDK diagnostics, account tokens or exception text.
