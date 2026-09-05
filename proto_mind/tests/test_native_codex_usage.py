from pathlib import Path
import json
import queue
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from proto_mind.native_codex_usage import activity, limits, read_usage


def window(used=25, minutes=300, reset=1789000000):
    return {"usedPercent": used, "windowDurationMins": minutes, "resetsAt": reset}


class CodexUsageTests(unittest.TestCase):
    def test_multi_bucket_view_is_authoritative_without_duplicate_legacy(self):
        value = limits({"rateLimits": {"primary": window(99)}, "rateLimitsByLimitId": {
            "codex": {"primary": window(25), "secondary": window(42, 10080)},
            "astra": {"limitName": "Astra", "primary": window(7)}}})
        self.assertEqual([b["id"] for b in value["buckets"]], ["codex", "astra"])
        self.assertEqual(value["buckets"][0]["windows"][0]["remaining_percent"], 75)
        self.assertEqual(value["buckets"][0]["windows"][1]["window_minutes"], 10080)

    def test_legacy_and_empty_map_fallback(self):
        for extra in [{}, {"rateLimitsByLimitId": None}, {"rateLimitsByLimitId": {}}]:
            value = limits({"rateLimits": {"primary": window(0)}, **extra})
            self.assertEqual(value["buckets"][0]["windows"][0]["remaining_percent"], 100)

    def test_unknown_percent_never_becomes_zero_usage(self):
        for used in [None, True, "0", float("nan"), float("inf"), -1]:
            row = limits({"rateLimits": {"primary": window(used)}})["buckets"][0]["windows"][0]
            self.assertIsNone(row["used_percent"])
            self.assertIsNone(row["remaining_percent"])

    def test_over_limit_is_clamped_only_for_remaining_progress(self):
        row = limits({"rateLimits": {"primary": window(120.5)}})["buckets"][0]["windows"][0]
        self.assertEqual(row["remaining_percent"], 0)
        self.assertEqual(row["used_percent"], 120.5)

    def test_missing_window_and_reset_are_unknown(self):
        result = limits({"rateLimits": {"primary": window(30, None, None), "secondary": None}})
        self.assertEqual(len(result["buckets"][0]["windows"]), 1)
        self.assertIsNone(result["buckets"][0]["windows"][0]["resets_at"])
        self.assertIsNone(result["reset_credits"])
        self.assertEqual(limits({})["buckets"], [])

    def test_resets_are_read_only_counts_and_other_details_are_not_projected(self):
        result = limits({"rateLimits": {"primary": window(), "credits": {"balance": "secret"}},
                         "rateLimitResetCredits": {"availableCount": 3, "credits": [{"id": "opaque-not-needed"}]},
                         "accountId": "private-id", "rateLimitUpsell": "untrusted banner"})
        self.assertEqual(result["reset_credits"], 3)
        self.assertNotIn("private-id", str(result)); self.assertNotIn("opaque-not-needed", str(result))
        self.assertNotIn("secret", str(result)); self.assertNotIn("banner", str(result))

    def test_activity_preserves_unknown_and_zero(self):
        result = activity({"summary": {"lifetimeTokens": 0, "peakDailyTokens": None}, "dailyUsageBuckets": None})
        self.assertEqual(result["summary"]["lifetimeTokens"], 0)
        self.assertIsNone(result["summary"]["peakDailyTokens"])
        self.assertEqual(result["daily"], [])

    def test_daily_activity_is_bounded_sorted_and_never_fills_missing_days(self):
        days = [{"startDate": f"2026-09-{n:02}", "tokens": n} for n in range(1, 12)]
        days += [{"startDate": "2026-02-30", "tokens": 1}, {"startDate": "2026-09-20", "tokens": -1}]
        result = activity({"dailyUsageBuckets": days})["daily"]
        self.assertEqual(len(result), 7)
        self.assertEqual(result[0], {"date": "2026-09-11", "tokens": 11})

    def test_duplicate_daily_records_are_not_double_counted(self):
        with self.assertRaises(ValueError): activity({"dailyUsageBuckets": [{"startDate": "2026-09-01", "tokens": 10}] * 2})

    def test_signed_out_and_api_key_accounts_do_not_query_subscription_usage(self):
        for kind in ["signed_out", "apiKey"]:
            client = SimpleNamespace(account=lambda: {"connected": False, "plan": "", "email": "", "auth_type": kind}, connect=Mock())
            self.assertFalse(read_usage(client)["connected"])
            client.connect.assert_not_called()

    def test_endpoint_failure_is_partial_and_never_sends_a_turn(self):
        for failed in ["account/rateLimits/read", "account/usage/read"]:
            calls = []
            def request(method, params, **kwargs):
                calls.append((method, params))
                if method == failed: raise RuntimeError("private upstream output")
                return {"rateLimits": {"primary": window()}, "summary": {"lifetimeTokens": 100}}
            client = SimpleNamespace(account=lambda: {"connected": True, "plan": "plus", "email": "fixture@example.invalid"},
                                     connect=lambda: SimpleNamespace(request=request))
            result = read_usage(client)
            self.assertEqual([m for m, _ in calls], ["account/rateLimits/read", "account/usage/read"])
            self.assertTrue(all(p == {} for _, p in calls))
            self.assertNotIn("private upstream", str(result))
            if failed.endswith("rateLimits/read"):
                self.assertTrue(result["limits_error"]); self.assertIsNotNone(result["activity"])
            else:
                self.assertTrue(result["activity_error"]); self.assertTrue(result["buckets"])

    def test_bridge_rejects_usage_parameters_or_busy_core(self):
        from proto_mind.native_bridge import NativeBackend
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            backend = NativeBackend(root, root / "state")
            try:
                with self.assertRaises(ValueError): backend.dispatch("account_usage", {"thread_id": "not-allowed"}, lambda _: None, "usage")
                backend.busy.acquire()
                with self.assertRaises(ValueError): backend.dispatch("account_usage", {}, lambda _: None, "usage")
                backend.busy.release()
            finally: backend.close()

    def test_compact_read_omits_activity_and_reset_journal(self):
        request = Mock(return_value={"rateLimits": {"primary": window(12)}})
        client = SimpleNamespace(account=lambda: {"connected": True, "plan": "plus", "email": "qa@example.invalid"},
                                 connect=lambda: SimpleNamespace(request=request))
        result = read_usage(client, include_activity=False)
        request.assert_called_once_with("account/rateLimits/read", {}, timeout=15)
        self.assertEqual(result["buckets"][0]["windows"][0]["used_percent"], 12)
        self.assertIsNone(result["activity"]); self.assertIsNone(result["reset"])

    def test_background_read_uses_and_closes_an_independent_client_while_core_busy(self):
        from proto_mind.native_bridge import NativeBackend
        for fails in [False, True]:
            clients = []
            def factory(state):
                account = Mock(return_value={"connected": True, "plan": "plus", "email": "qa@example.invalid"})
                if fails: account.side_effect = RuntimeError("account unavailable")
                client = SimpleNamespace(account=account, close=Mock(),
                    connect=lambda: SimpleNamespace(request=Mock(return_value={"rateLimits": {"primary": window()}})))
                clients.append(client)
                return client
            with tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                backend = NativeBackend(root, root / "state", subscription_factory=factory)
                try:
                    with backend.busy:
                        if fails:
                            with self.assertRaises(RuntimeError): backend.dispatch("account_limits", {}, lambda _: None, "limits")
                        else:
                            result = backend.dispatch("account_limits", {}, lambda _: None, "limits")
                            self.assertTrue(result["connected"])
                        self.assertTrue(backend.busy.locked())
                    self.assertEqual(len(clients), 2)
                    clients[0].account.assert_not_called(); clients[0].close.assert_not_called()
                    clients[1].close.assert_called_once()
                    self.assertFalse(backend._limits_read_lock.locked())
                    self.assertFalse((root / "state/codex-reset-attempts.json").exists())
                finally: backend.close()

    def test_background_read_rejects_parameters_concurrent_reads_and_shutdown(self):
        from proto_mind.native_bridge import NativeBackend
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            factory = Mock(return_value=SimpleNamespace(close=Mock()))
            backend = NativeBackend(root, root / "state", subscription_factory=factory)
            try:
                with self.assertRaises(ValueError): backend.dispatch("account_limits", {"reset": True}, lambda _: None, "limits")
                with backend._limits_read_lock:
                    with self.assertRaises(ValueError): backend.dispatch("account_limits", {}, lambda _: None, "limits")
                backend.disconnect()
                with self.assertRaises(ValueError): backend.dispatch("account_limits", {}, lambda _: None, "limits")
                self.assertEqual(factory.call_count, 1)
            finally: backend.close()

    def test_stdio_limits_and_work_do_not_block_each_other_but_work_stays_serial(self):
        from proto_mind.native_bridge import serve
        for blocked_method, independent in [("process", "account_limits"), ("account_limits", "process"),
                                             ("process", "steer"), ("account_limits", "steer")]:
            incoming, outgoing = queue.Queue(), queue.Queue()
            started, release, next_started = threading.Event(), threading.Event(), threading.Event()
            class Source:
                def readline(self, maximum): return incoming.get(timeout=5)
            class Destination:
                def write(self, value): outgoing.put(json.loads(value))
                def flush(self): pass
            def dispatch(method, params, emit, request_id):
                if request_id == "blocked":
                    started.set()
                    if not release.wait(5): raise RuntimeError("fixture timeout")
                if request_id == "next": next_started.set()
                return {"done": True}
            backend = SimpleNamespace(dispatch=dispatch, disconnect=Mock(), close=Mock())
            worker = threading.Thread(target=serve, args=(backend, Source(), Destination()))
            worker.start()
            def send(identifier, method): incoming.put(json.dumps({"id": identifier, "method": method}) + "\n")
            try:
                send("blocked", blocked_method)
                self.assertTrue(started.wait(2))
                send("independent", independent)
                self.assertEqual(outgoing.get(timeout=2)["id"], "independent")
                if blocked_method == "process":
                    send("next", "account_reset")
                    self.assertFalse(next_started.wait(0.05))
                release.set()
                self.assertEqual(outgoing.get(timeout=2)["id"], "blocked")
                if blocked_method == "process": self.assertEqual(outgoing.get(timeout=2)["id"], "next")
            finally:
                release.set(); incoming.put(""); worker.join(5)
            self.assertFalse(worker.is_alive())
            backend.disconnect.assert_called_once(); backend.close.assert_called_once()


if __name__ == "__main__": unittest.main()
