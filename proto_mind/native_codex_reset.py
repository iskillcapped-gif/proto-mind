"""Explicit earned-reset redemption with a durable, account-bound retry key.

This journal is excluded from private-state backups, like the Codex login: a
restored copy must never roll an already spent reset back into an unused attempt.
"""
from __future__ import annotations

from contextlib import contextmanager
import fcntl
import hashlib
import os
from pathlib import Path
import re
import stat
from uuid import UUID

from proto_mind.native_private_backup import atomic_file, decode, encoded, read_file, safe_directory

SCHEMA = "proto_mind.codex_reset_attempts.v1"
CONFIRMATION = "USE ONE CODEX RESET"
OUTCOMES = {"reset", "alreadyRedeemed", "nothingToReset", "noCredit"}
REF = re.compile(r"[0-9a-f]{64}")


def account_reference(raw, account):
    # accountId is optional in the installed protocol. Managed login email is
    # stable across refresh/restart; the selected opaque credit further binds a
    # redemption when the service provides credit details.
    email = account.get("email")
    value = "email:" + email.strip().casefold() if isinstance(email, str) and email.strip() else raw.get("accountId")
    if not isinstance(value, str) or not value.strip() or len(value) > 512: return None
    return hashlib.sha256(value.encode()).hexdigest()


def available_credit_ids(raw):
    summary = raw.get("rateLimitResetCredits")
    rows = summary.get("credits") if isinstance(summary, dict) else None
    if not isinstance(rows, list): return []
    return [row["id"] for row in rows[:1000] if isinstance(row, dict)
            and row.get("status") == "available" and row.get("resetType") == "codexRateLimits"
            and isinstance(row.get("id"), str) and 0 < len(row["id"]) <= 1024]


def valid_key(value):
    try: return isinstance(value, str) and str(UUID(value)) == value
    except ValueError: return False


class CodexResetStore:
    def __init__(self, state: Path):
        self.state = state
        self.path = state / "codex-reset-attempts.json"

    def read(self):
        try: value = decode(read_file(self.path, 128 * 1024))
        except FileNotFoundError: return {}
        if not isinstance(value, dict) or set(value) != {"schema", "accounts"} or value["schema"] != SCHEMA:
            raise ValueError("Не удалось проверить предыдущую попытку сброса.")
        rows = value["accounts"]
        if not isinstance(rows, dict) or len(rows) > 64: raise ValueError("Некорректный журнал сбросов.")
        for reference, row in rows.items():
            if (not REF.fullmatch(reference) or not isinstance(row, dict) or set(row) != {"key", "outcome", "credit_id"}
                    or not valid_key(row["key"]) or not isinstance(row["outcome"], str)
                    or row["outcome"] not in OUTCOMES | {"pending"}
                    or (row["credit_id"] is not None and (not isinstance(row["credit_id"], str) or not 0 < len(row["credit_id"]) <= 1024))):
                raise ValueError("Не удалось проверить предыдущую попытку сброса.")
        return rows

    def inspect(self, raw_limits, account):
        reference = account_reference(raw_limits, account)
        if reference is None: return None
        row = self.read().get(reference, {})
        credit = row.get("credit_id") if row.get("outcome") == "pending" else next(iter(available_credit_ids(raw_limits)), None)
        return {"account_ref": reference, "attempt_key": row.get("key", ""), "outcome": row.get("outcome", ""), "credit_id": credit}

    def save(self, rows):
        atomic_file(self.path, encoded({"schema": SCHEMA, "accounts": rows}))
        if self.read() != rows: raise ValueError("Не удалось сохранить попытку сброса.")

    @contextmanager
    def locked(self):
        safe_directory(self.state, create=True)
        fd = os.open(self.state / ".codex-reset.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode): raise ValueError("Некорректная блокировка сброса.")
            try: fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError: raise ValueError("Сброс уже выполняется в другой копии Proto-Mind.") from None
            yield
        finally: os.close(fd)


def consume_reset(subscription, store: CodexResetStore, params: dict) -> dict:
    from proto_mind.native_codex_usage import limits, read_usage

    if (set(params) != {"account_ref", "expected_attempt", "idempotency_key", "confirmation", "credit_id"}
            or params.get("confirmation") != CONFIRMATION
            or not isinstance(params.get("account_ref"), str) or not REF.fullmatch(params["account_ref"])
            or not valid_key(params.get("idempotency_key"))
            or (params.get("expected_attempt") != "" and not valid_key(params.get("expected_attempt")))
            or (params.get("credit_id") is not None and (not isinstance(params["credit_id"], str) or not 0 < len(params["credit_id"]) <= 1024))):
        raise ValueError("Подтвердите один сброс в окне использования Codex.")
    account = subscription.account()
    if not account["connected"]:
        raise ValueError("Войдите в ChatGPT перед сбросом лимита.")
    rpc = subscription.connect()
    reference, key = params["account_ref"], params["idempotency_key"]
    with store.locked():
        fresh = rpc.request("account/rateLimits/read", {}, timeout=15)
        if account_reference(fresh, account) != reference:
            raise ValueError("Аккаунт изменился или не удалось его проверить. Обновите лимиты.")
        rows = store.read()
        previous = rows.get(reference, {})
        if previous.get("key") != key:
            if previous.get("outcome") == "pending" or previous.get("key", "") != params["expected_attempt"]:
                raise ValueError("Состояние предыдущего сброса изменилось. Обновите лимиты.")
            if not (limits(fresh)["reset_credits"] or 0) > 0:
                raise ValueError("Доступных сбросов сейчас нет. Обновите лимиты.")
            if params["credit_id"] is not None and params["credit_id"] not in available_credit_ids(fresh):
                raise ValueError("Выбранный сброс больше недоступен. Обновите лимиты.")
            if reference not in rows and len(rows) >= 64: raise ValueError("Журнал сбросов заполнен.")
            rows[reference] = {"key": key, "outcome": "pending", "credit_id": params["credit_id"]}
            # Must be durable before the first external write. No automatic retry.
            store.save(rows)
        outcome = rows[reference]["outcome"]
        if outcome == "pending":
            try:
                request = {"idempotencyKey": key}
                if rows[reference]["credit_id"] is not None: request["creditId"] = rows[reference]["credit_id"]
                result = rpc.request("account/rateLimitResetCredit/consume", request, timeout=30)
                outcome = result.get("outcome")
                if not isinstance(outcome, str) or outcome not in OUTCOMES: raise ValueError("Unknown reset outcome")
                rows[reference]["outcome"] = outcome
                store.save(rows)
            except (ValueError, RuntimeError, OSError):
                outcome = "pending"
    # Always read the service's actual quota, even after an ambiguous response.
    # A failed refresh cannot erase the known redemption outcome.
    try: usage, refresh_error = read_usage(subscription, store), ""
    except (ValueError, RuntimeError, OSError):
        usage, refresh_error = None, "Не удалось обновить лимиты. Нажмите «Обновить»."
    return {"outcome": outcome, "usage": usage, "refresh_error": refresh_error}
