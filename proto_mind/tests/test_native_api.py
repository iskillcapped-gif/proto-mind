from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from uuid import uuid4

from proto_mind.config import ProtoMindConfig
from proto_mind.native_api import APITransport, validate_connection
from proto_mind.native_bridge import NativeBackend
from proto_mind.tests.test_native import FakeSubscription


class APIFixture:
    def __init__(self, events, status=200):
        self.calls = []
        fixture = self
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                fixture.calls.append((self.path, self.headers.get("Authorization"), json.loads(self.rfile.read(int(self.headers["Content-Length"])))))
                self.send_response(status)
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()
                for event in events:
                    self.wfile.write(b"data: " + (event if isinstance(event, bytes) else json.dumps(event).encode()) + b"\n\n")
                    self.wfile.flush()
            def log_message(self, *_):
                pass
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.endpoint = f"http://127.0.0.1:{self.server.server_port}/v1"

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)


class NativeAPITests(unittest.TestCase):
    def fixture(self, events=None, status=200):
        server = APIFixture(events if events is not None else [
            {"type": "response.output_text.delta", "delta": "Привет "},
            {"type": "response.output_text.delta", "delta": "из API"},
            {"type": "response.completed", "response": {"status": "completed"}},
        ], status)
        self.addCleanup(server.close)
        return server

    def connection(self, server, format="responses"):
        return {"endpoint": server.endpoint, "key": "synthetic-test-secret", "format": format}

    def test_responses_stream_preserves_history_and_exact_model(self):
        server = self.fixture()
        transport = APITransport(self.connection(server))
        deltas = []
        answer = transport.answer("model-selected-by-user", "system memory", [{"role": "user", "content": "earlier"}], "next", deltas.append)
        self.assertEqual(answer, "Привет из API")
        self.assertEqual(deltas, ["Привет ", "из API"])
        path, auth, body = server.calls[0]
        self.assertEqual(path, "/v1/responses")
        self.assertEqual(auth, "Bearer synthetic-test-secret")
        self.assertFalse(body["store"])
        self.assertEqual(body["model"], "model-selected-by-user")
        self.assertEqual(body["instructions"], "system memory")
        self.assertEqual(body["input"][0]["content"], "earlier")
        self.assertEqual(transport.connection["key"], "")

    def test_chat_completions_and_keyless_local_server(self):
        server = self.fixture([
            {"choices": [{"delta": {"role": "assistant"}, "finish_reason": None}]},
            {"choices": [{"delta": {"content": "Local answer"}, "finish_reason": None}]},
            {"choices": [{"delta": {}, "finish_reason": "stop"}]}, b"[DONE]",
        ])
        connection = self.connection(server, "chat_completions"); connection["key"] = ""
        result = APITransport(connection).answer("local-model", "memory", [], "hello", lambda _: None)
        self.assertEqual(result, "Local answer")
        self.assertEqual(server.calls[0][0], "/v1/chat/completions")
        self.assertIsNone(server.calls[0][1])
        self.assertEqual(server.calls[0][2]["messages"][0], {"role": "system", "content": "memory"})

    def test_incomplete_or_malformed_stream_is_not_success(self):
        for events in [[{"type": "response.output_text.delta", "delta": "partial"}], [b"not-json"],
                       [{"type": "response.incomplete"}], [{"type": "response.completed", "response": {"status": "failed"}}]]:
            with self.subTest(events=events):
                server = self.fixture(events)
                with self.assertRaises(RuntimeError):
                    APITransport(self.connection(server)).answer("model", "memory", [], "hello", lambda _: None)
                self.assertEqual(len(server.calls), 1)

    def test_http_errors_do_not_echo_server_payload_or_retry(self):
        server = self.fixture([b"synthetic-test-secret"], status=401)
        with self.assertRaisesRegex(RuntimeError, "HTTP 401") as error:
            APITransport(self.connection(server)).answer("model", "memory", [], "hello", lambda _: None)
        self.assertNotIn("synthetic-test-secret", str(error.exception))
        self.assertEqual(len(server.calls), 1)

    def test_cancel_before_dispatch_makes_no_call(self):
        server = self.fixture()
        transport = APITransport(self.connection(server)); transport.cancel()
        with self.assertRaises(RuntimeError):
            transport.answer("model", "memory", [], "hello", lambda _: None)
        self.assertEqual(server.calls, [])

    def test_cancel_interrupts_an_idle_stream_without_retry(self):
        entered, release = threading.Event(), threading.Event()
        calls = []
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                calls.append(self.path)
                self.rfile.read(int(self.headers["Content-Length"]))
                self.send_response(200); self.end_headers()
                self.wfile.write(b'data: {"type":"response.output_text.delta","delta":"partial"}\n\n')
                self.wfile.flush(); entered.set(); release.wait(5)
            def log_message(self, *_): pass
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        worker = threading.Thread(target=server.serve_forever, daemon=True); worker.start()
        transport = APITransport({"endpoint": f"http://127.0.0.1:{server.server_port}/v1", "format": "responses", "key": ""})
        failures = []
        def run():
            try: transport.answer("fixture", "memory", [], "hello", lambda _: None)
            except RuntimeError as error: failures.append(str(error))
        task = threading.Thread(target=run, daemon=True); task.start()
        try:
            self.assertTrue(entered.wait(2))
            transport.cancel(); task.join(timeout=2)
            self.assertFalse(task.is_alive(), "Stop must interrupt a blocked response read")
            self.assertEqual(len(failures), 1)
            self.assertEqual(calls, ["/v1/responses"])
        finally:
            release.set(); transport.cancel(); task.join(timeout=2)
            server.shutdown(); server.server_close(); worker.join(timeout=2)

    def test_endpoint_and_headers_are_validated(self):
        for endpoint in ["http://example.com/v1", "https://user:password@example.com/v1", "file:///tmp", "https://example.com/v1?key=secret", "https://example.com/#fragment", "https://example.com/\n"]:
            with self.subTest(endpoint=endpoint), self.assertRaises(ValueError):
                validate_connection({"endpoint": endpoint, "format": "responses", "key": "key"})
        with self.assertRaises(ValueError):
            validate_connection({"endpoint": "https://example.com/v1", "format": "responses", "key": "key\r\nHeader: value"})

    def test_core_workflow_journals_without_credentials(self):
        server = self.fixture()
        with tempfile.TemporaryDirectory(prefix="proto-api-core-") as temp:
            root, state = Path(temp) / "project", Path(temp) / "state"
            backend = NativeBackend(root, state, subscription_factory=FakeSubscription)
            self.addCleanup(backend.close)
            params = {"text": "Привет", "provider": "api", "model": "fixture-model", "conversation_id": str(uuid4()),
                      "run_id": str(uuid4()), "api_connection": self.connection(server), "cloud_consent": True}
            with patch.object(ProtoMindConfig, "from_env", return_value=ProtoMindConfig(data_dir=root / "proto_mind/data")):
                result = backend.process(params, lambda _: None, "api-test")
            self.assertTrue(result["text"].startswith("Proto-Mind: Привет из API"))
            self.assertEqual(result["work_session"]["status"], "completed")
            self.assertEqual(result["work_session"]["turn_receipt"]["provider"], "api")
            self.assertEqual(result["work_session"]["instruction_receipt"]["provider"], "api")
            self.assertEqual(backend.subscription.calls, [])
            for path in Path(temp).rglob("*"):
                if path.is_file():
                    self.assertNotIn(b"synthetic-test-secret", path.read_bytes(), str(path))

    def test_missing_consent_and_full_mac_are_rejected_before_api(self):
        server = self.fixture()
        with tempfile.TemporaryDirectory(prefix="proto-api-consent-") as temp:
            backend = NativeBackend(Path(temp) / "project", Path(temp) / "state", subscription_factory=FakeSubscription)
            self.addCleanup(backend.close)
            params = {"text": "hello", "provider": "api", "model": "fixture", "conversation_id": str(uuid4()), "api_connection": self.connection(server)}
            for extra in [{"cloud_consent": False}, {"cloud_consent": True, "access_mode": "full_access"}]:
                with self.assertRaises(ValueError):
                    backend.process({**params, **extra}, lambda _: None, "api-blocked")
            self.assertEqual(server.calls, [])


if __name__ == "__main__":
    unittest.main()
