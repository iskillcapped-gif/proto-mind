"""Read-only account usage projection; no token prices, thread reads or reset actions."""
from __future__ import annotations

from datetime import date
import math
import time

SCHEMA = "proto_mind.codex_usage.v1"


def number(value, *, maximum=9_007_199_254_740_991):
    if type(value) not in {int, float} or not math.isfinite(value) or not 0 <= value <= maximum: return None
    return value


def integer(value, *, maximum=9_007_199_254_740_991):
    parsed = number(value, maximum=maximum)
    return int(parsed) if parsed is not None and int(parsed) == parsed else None


def label(value):
    return value.strip()[:160] if isinstance(value, str) else ""


def limits(value: dict) -> dict:
    buckets = value.get("rateLimitsByLimitId")
    if buckets is None or buckets == {}:
        legacy = value.get("rateLimits")
        buckets = {label(legacy.get("limitId")) or "codex": legacy} if isinstance(legacy, dict) else {}
    if not isinstance(buckets, dict) or len(buckets) > 64: raise ValueError("Invalid quota buckets")
    result = []
    for key in sorted(buckets, key=lambda name: (name != "codex", name)):
        raw = buckets[key]
        if not isinstance(raw, dict): continue
        windows = []
        for kind in ["primary", "secondary"]:
            window = raw.get(kind)
            if not isinstance(window, dict): continue
            used = number(window.get("usedPercent"))
            windows.append({"kind": kind, "used_percent": used,
                            "remaining_percent": max(0, min(100, 100 - used)) if used is not None else None,
                            "window_minutes": integer(window.get("windowDurationMins"), maximum=5_256_000) or None,
                            "resets_at": integer(window.get("resetsAt"), maximum=253_402_300_799)})
        result.append({"id": label(key), "name": label(raw.get("limitName")) or ("Codex" if key == "codex" else label(key)),
                       "plan": label(raw.get("planType")), "windows": windows})
    resets = value.get("rateLimitResetCredits")
    return {"buckets": result, "reset_credits": integer(resets.get("availableCount")) if isinstance(resets, dict) else None}


def activity(value: dict) -> dict:
    raw = value.get("summary")
    if raw is not None and not isinstance(raw, dict): raise ValueError("Invalid usage summary")
    summary = {key: integer((raw or {}).get(key)) for key in ["lifetimeTokens", "peakDailyTokens", "currentStreakDays"]}
    daily = value.get("dailyUsageBuckets")
    if daily is None: return {"summary": summary, "daily": []}
    if not isinstance(daily, list) or len(daily) > 10_000: raise ValueError("Invalid daily usage")
    days = {}
    for row in daily:
        if not isinstance(row, dict): continue
        day, tokens = row.get("startDate"), integer(row.get("tokens"))
        try:
            if not isinstance(day, str) or date.fromisoformat(day).isoformat() != day or tokens is None: continue
        except ValueError: continue
        if day in days: raise ValueError("Duplicate daily usage")
        days[day] = tokens
    return {"summary": summary, "daily": [{"date": day, "tokens": days[day]} for day in sorted(days, reverse=True)[:7]]}


def read_usage(subscription, reset_store=None, *, include_activity=True) -> dict:
    # Use the same managed ChatGPT login as PM. Never inspect credentials or the
    # Desktop profile, and never send a model turn to measure quota.
    account = subscription.account()
    result = {"schema": SCHEMA, "connected": account["connected"], "plan": label(account["plan"]),
              "email": label(account["email"]), "buckets": [], "reset_credits": None,
              "activity": None, "limits_error": "", "activity_error": "", "reset": None, "reset_error": "", "checked_at": int(time.time()),
              "limits_updated_at": None, "activity_updated_at": None}
    if not account["connected"]: return result
    rpc = subscription.connect()
    # Partial endpoint failure must not erase a successfully read independent section.
    sections = [("account/rateLimits/read", limits, "limits_error", "limits_updated_at")]
    if include_activity:
        sections.append(("account/usage/read", activity, "activity_error", "activity_updated_at"))
    for method, parser, field, timestamp in sections:
        try:
            raw = rpc.request(method, {}, timeout=15)
            value = parser(raw)
            if field == "limits_error": result.update(value)
            else: result["activity"] = value
            result[timestamp] = int(time.time())
            if field == "limits_error" and reset_store is not None:
                try: result["reset"] = reset_store.inspect(raw, account)
                except (ValueError, RuntimeError, OSError):
                    result["reset_error"] = "Не удалось проверить предыдущую попытку сброса. Новый сброс недоступен."
        except (ValueError, RuntimeError, OSError):
            result[field] = "Codex сейчас не вернул эти данные. Попробуйте обновить позже."
    return result
