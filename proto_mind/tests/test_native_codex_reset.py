"""Synthetic reset service: these tests never contact or spend a real account credit."""
from copy import deepcopy
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from uuid import uuid4

from proto_mind.native_codex_reset import CodexResetStore, CONFIRMATION, OUTCOMES, consume_reset
from proto_mind.native_codex_usage import read_usage


class CodexResetTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.store = CodexResetStore(Path(self.temporary.name).resolve() / "state")
        self.account = {"connected": True, "email": "fixture@example.invalid", "plan": "plus"}
        self.quota = {"rateLimits": {"primary": {"usedPercent": 100, "windowDurationMins": 300}},
                      "rateLimitResetCredits": {"availableCount": 3, "credits": [
                          {"id": "fixture-credit", "status": "available", "resetType": "codexRateLimits"}]}}
        self.calls, self.outcome = [], "reset"
        self.client = SimpleNamespace(account=lambda: deepcopy(self.account), connect=lambda: SimpleNamespace(request=self.request))

    def request(self, method, params, **kwargs):
        self.calls.append((method, deepcopy(params)))
        if method == "account/rateLimits/read": return deepcopy(self.quota)
        if method == "account/usage/read": return {}
        self.assertEqual(method, "account/rateLimitResetCredit/consume")
        row = next(iter(self.store.read().values()))
        self.assertEqual(row["key"], params["idempotencyKey"])
        self.assertEqual(row["outcome"], "pending")  # durable before the external action
        if isinstance(self.outcome, Exception): raise self.outcome
        self.quota["rateLimits"]["primary"]["usedPercent"] = 7
        return {"outcome": self.outcome}

    def params(self, **changes):
        reset = read_usage(self.client, self.store)["reset"]
        return {"account_ref": reset["account_ref"], "expected_attempt": reset["attempt_key"],
                "idempotency_key": reset["attempt_key"] if reset["outcome"] == "pending" else str(uuid4()),
                "credit_id": reset["credit_id"], "confirmation": CONFIRMATION, **changes}

    def writes(self): return [p for m, p in self.calls if m.endswith("/consume")]

    def test_read_only_usage_never_creates_attempt_state(self):
        value = read_usage(self.client, self.store)
        self.assertTrue(value["reset"]["account_ref"])
        self.assertEqual(value["reset"]["attempt_key"], "")
        self.assertFalse(self.store.state.exists())
        self.assertEqual(self.writes(), [])

    def test_all_known_outcomes_and_real_quota_readback(self):
        for outcome in OUTCOMES:
            self.outcome = outcome
            result = consume_reset(self.client, self.store, self.params())
            self.assertEqual(result["outcome"], outcome)
            self.assertEqual(result["usage"]["buckets"][0]["windows"][0]["remaining_percent"], 93)
            self.assertEqual(self.writes()[-1]["creditId"], "fixture-credit")
            self.assertEqual(self.calls[-2][0], "account/rateLimits/read")

    def test_completed_duplicate_never_consumes_again(self):
        params = self.params()
        consume_reset(self.client, self.store, params)
        consume_reset(self.client, self.store, params)
        self.assertEqual(len(self.writes()), 1)

    def test_timeout_survives_restart_and_reuses_key_and_credit_even_at_zero_count(self):
        params = self.params()
        self.outcome = RuntimeError("uncertain upstream secret")
        result = consume_reset(self.client, self.store, params)
        self.assertEqual(result["outcome"], "pending")
        self.assertNotIn("secret", str(result))
        self.store = CodexResetStore(self.store.state)
        self.quota["rateLimitResetCredits"] = {"availableCount": 0, "credits": []}
        self.outcome = "alreadyRedeemed"
        retry = self.params()
        self.assertEqual(retry["idempotency_key"], params["idempotency_key"])
        self.assertEqual(consume_reset(self.client, self.store, retry)["outcome"], "alreadyRedeemed")
        self.assertEqual(self.writes(), [self.writes()[0]] * 2)

    def test_pending_attempt_cannot_be_replaced_by_new_key(self):
        self.outcome = RuntimeError()
        consume_reset(self.client, self.store, self.params())
        with self.assertRaises(ValueError): consume_reset(self.client, self.store, self.params(idempotency_key=str(uuid4())))
        self.assertEqual(len(self.writes()), 1)

    def test_stale_confirmation_cannot_start_an_additional_attempt(self):
        first, stale = self.params(), self.params()
        consume_reset(self.client, self.store, first)
        with self.assertRaises(ValueError): consume_reset(self.client, self.store, stale)
        self.assertEqual(len(self.writes()), 1)

    def test_missing_unknown_and_zero_count_block_new_attempt(self):
        for count in [0, None, "3"]:
            params = self.params()
            self.quota["rateLimitResetCredits"]["availableCount"] = count
            with self.assertRaises(ValueError): consume_reset(self.client, self.store, params)
        self.assertEqual(self.writes(), [])

    def test_changed_account_or_expired_credit_blocks_before_external_write(self):
        params = self.params()
        self.account["email"] = "different@example.invalid"
        with self.assertRaises(ValueError): consume_reset(self.client, self.store, params)
        self.account["email"] = "fixture@example.invalid"
        self.quota["rateLimitResetCredits"]["credits"] = []
        with self.assertRaises(ValueError): consume_reset(self.client, self.store, params)
        self.assertEqual(self.writes(), [])

    def test_count_only_service_can_select_credit(self):
        self.quota["rateLimitResetCredits"]["credits"] = None
        consume_reset(self.client, self.store, self.params())
        self.assertEqual(set(self.writes()[0]), {"idempotencyKey"})

    def test_unverifiable_account_has_no_reset_control(self):
        self.account["email"] = None
        self.assertIsNone(read_usage(self.client, self.store)["reset"])
        self.quota["accountId"] = "fixture-account"
        self.assertIsNotNone(read_usage(self.client, self.store)["reset"])

    def test_unknown_outcome_stays_pending(self):
        self.outcome = {"malformed": True}
        result = consume_reset(self.client, self.store, self.params())
        self.assertEqual(result["outcome"], "pending")
        self.assertEqual(result["usage"]["reset"]["outcome"], "pending")

    def test_failure_to_persist_attempt_prevents_external_write(self):
        params = self.params()
        with patch.object(self.store, "save", side_effect=OSError("disk full")):
            with self.assertRaises(OSError): consume_reset(self.client, self.store, params)
        self.assertEqual(self.writes(), [])

    def test_failure_to_save_result_retains_retry_key(self):
        params, save = self.params(), self.store.save
        def fail_outcome(rows):
            if next(iter(rows.values()))["outcome"] != "pending": raise OSError("disk full")
            save(rows)
        with patch.object(self.store, "save", side_effect=fail_outcome):
            self.assertEqual(consume_reset(self.client, self.store, params)["outcome"], "pending")
        self.assertEqual(self.params()["idempotency_key"], params["idempotency_key"])

    def test_failed_refresh_preserves_known_outcome(self):
        params = self.params()
        with patch("proto_mind.native_codex_usage.read_usage", side_effect=RuntimeError("offline")):
            result = consume_reset(self.client, self.store, params)
        self.assertEqual(result["outcome"], "reset")
        self.assertIsNone(result["usage"])
        self.assertTrue(result["refresh_error"])

    def test_other_process_lock_and_unreadable_journal_block(self):
        params = self.params()
        with self.store.locked():
            with self.assertRaises(ValueError): consume_reset(self.client, CodexResetStore(self.store.state), params)
        self.store.path.write_text('{"broken":true}')
        value = read_usage(self.client, self.store)
        self.assertTrue(value["buckets"])
        self.assertTrue(value["reset_error"])
        self.assertIsNone(value["reset"])
        with self.assertRaises(ValueError): consume_reset(self.client, self.store, params)
        self.assertEqual(self.writes(), [])

    def test_missing_confirmation_bad_key_and_signed_out_are_refused(self):
        for changes in [{"confirmation": "yes"}, {"idempotency_key": ""}, {"extra": True}]:
            with self.assertRaises(ValueError): consume_reset(self.client, self.store, self.params(**changes))
        params = self.params()
        self.account["connected"] = False
        with self.assertRaises(ValueError): consume_reset(self.client, self.store, params)
        self.assertEqual(self.writes(), [])

    def test_bridge_serializes_reset_and_account_switches(self):
        from proto_mind.native_bridge import NativeBackend
        backend = NativeBackend(self.store.state.parent / "project", self.store.state)
        try:
            backend.busy.acquire()
            for method in ["account_reset", "account_login", "account_logout"]:
                with self.assertRaises(ValueError): backend.dispatch(method, {}, lambda _: None, "fixture")
            backend.busy.release()
        finally: backend.close()


if __name__ == "__main__": unittest.main()
