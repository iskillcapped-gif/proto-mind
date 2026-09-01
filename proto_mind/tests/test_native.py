"""Native client boundary tests: no real accounts, network calls, or private stores."""
from __future__ import annotations

import io
import json
import os
from pathlib import Path
import queue
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch
from uuid import uuid4

from proto_mind import native_bridge as bridge
from proto_mind import native_codex as codex
from proto_mind.command_registry import COMMAND_REGISTRY
from proto_mind.config import ProtoMindConfig
from proto_mind.models import MemoryRecord
from proto_mind.observer import Observer


class FakeSubscription:
    def __init__(self, state):
        self.home = state / "codex-profile"
        self.calls = []
        self.interrupted = False
        self.closed = False
        self.failure = None
        self.reasoning_efforts = []
        self.last_thread_info = None

    def prepare_turn(self):
        self.interrupted = False
        self.last_thread_info = None

    def thread_status(self, conversation, workspace, *, mode=None):
        return {"schema": "proto_mind.native_codex_thread_status.v1", "linked": False,
                "workspace_matches": True, "thread_id_short": "", "notice": "fixture"}

    def reset_thread(self, conversation):
        return {"schema": "proto_mind.native_codex_thread_reset.v1", "reset": False,
                "no_provider_call": True, "provider_history_deleted": False, "notice": "fixture"}

    def answer(self, prompt, instructions, model, on_delta, *, conversation, logical_workspace,
               history=None, on_progress=None, reasoning_effort="", images=None):
        self.calls.append((prompt, instructions, model))
        self.reasoning_efforts.append(reasoning_effort)
        if self.failure:
            raise self.failure
        self.last_thread_info = {"schema": "proto_mind.native_codex_thread.v1", "state": "started",
                                 "thread_id_short": "fixture", "persistent": True,
                                 "workspace": logical_workspace, "mode": "chat", "model": model}
        on_delta("A local test ")
        on_delta("answer.")
        return "A local test answer."

    def interrupt(self):
        self.interrupted = True

    def close(self):
        self.closed = True


class NativeBridgeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="proto-native-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "project"
        self.data = self.root / "proto_mind" / "data"
        self.state = Path(self.temp.name) / "native-state"
        self.backend = bridge.NativeBackend(self.root, self.state, subscription_factory=FakeSubscription)
        self.addCleanup(self.backend.close)
        config_patch = patch.object(ProtoMindConfig, "from_env", return_value=ProtoMindConfig(data_dir=self.data))
        config_patch.start()
        self.addCleanup(config_patch.stop)

    def params(self, text="Hello", **kwargs):
        return {"text": text, "conversation_id": str(uuid4()), "provider": "mock", **kwargs}

    def process(self, text="Hello", **kwargs):
        return self.backend.process(self.params(text, **kwargs), lambda event: None, "request")

    def files(self):
        return {str(path.relative_to(self.root)): path.read_bytes() for path in self.root.rglob("*") if path.is_file()}

    def test_bootstrap_missing_stores_is_read_only_and_does_not_connect(self):
        result = self.backend.bootstrap()
        self.assertEqual(result["registry_count"], len(COMMAND_REGISTRY))
        self.assertFalse(result["context_injection"])
        self.assertFalse(result["subscription"]["automatic_connection"])
        self.assertIsInstance(result["agent"]["computer_use"]["available"], bool)
        self.assertEqual(result["agent"]["computer_use"]["scope"], "explicit_full_access_turn_only")
        self.assertNotIn("command", result["agent"]["computer_use"])
        self.assertFalse(self.root.exists())
        self.assertFalse(self.state.exists())
        self.assertEqual(self.backend.subscription.calls, [])

    def test_bootstrap_malformed_profile_and_memory_are_diagnostic_only(self):
        self.data.mkdir(parents=True)
        (self.data / "identity.json").write_text('{"profile": []}', encoding="utf-8")
        (self.data / "persistent_memory.json").write_text('{}', encoding="utf-8")
        (self.data / "context_injection.json").write_text('broken', encoding="utf-8")
        before = self.files()
        result = self.backend.bootstrap()
        self.assertEqual(result["name"], "Proto-Mind")
        self.assertEqual(len(result["notes"]), 3)
        self.assertIsNone(result["context_injection"])
        self.assertEqual(before, self.files())

    def test_registry_commands_remain_reachable_and_mutations_need_confirmation(self):
        for spec in COMMAND_REGISTRY:
            with self.subTest(command=spec.prefix):
                description = bridge.describe_input(spec.prefix)
                self.assertFalse(description["blocked"])
                self.assertTrue(description["operator"])
                if not spec.read_only or spec.risk != "low":
                    self.assertTrue(description["requires_confirmation"])

    def test_unknown_slash_never_falls_through_to_model(self):
        with self.assertRaisesRegex(ValueError, "Unknown command"):
            self.process("/unknown-native-command")
        self.assertFalse(self.root.exists())
        self.assertEqual(self.backend.subscription.calls, [])

    def test_reasoning_effort_reaches_subscription_without_becoming_user_input(self):
        self.process("Hello", provider="codex", cloud_consent=True, reasoning_effort="xhigh")
        self.assertEqual(self.backend.subscription.reasoning_efforts, ["xhigh"])
        self.assertEqual(self.backend.subscription.calls[0][0], "Hello")

    def test_invalid_reasoning_effort_is_refused_without_creating_core_files(self):
        for effort in (None, True, 42, {}, "extreme", "high; /memory remember nope"):
            with self.subTest(effort=effort), self.assertRaisesRegex(ValueError, "reasoning effort"):
                self.process(provider="codex", cloud_consent=True, reasoning_effort=effort)
        self.assertEqual(self.backend.subscription.calls, [])
        self.assertFalse(self.root.exists())

    def test_operator_input_bypasses_model_and_effort_validation(self):
        self.process("/commands status", provider="codex", reasoning_effort="unavailable")
        self.assertEqual(self.backend.subscription.calls, [])
        self.assertEqual(self.backend.subscription.reasoning_efforts, [])

    def test_mutation_requires_exact_operator_confirmation(self):
        text = "/memory remember Native explicit test memory."
        with self.assertRaisesRegex(ValueError, "Confirm the exact"):
            self.process(text, confirmed_text="different")
        self.assertFalse(self.root.exists())
        result = self.process(text, confirmed_text=text)
        self.assertTrue(result["operator"])
        records = json.loads((self.data / "persistent_memory.json").read_text())
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["content"], "Native explicit test memory.")

    def test_read_only_operator_and_natural_commands_never_call_cloud_or_write_stores(self):
        for text in ["/commands status", "что делать дальше"]:
            before = self.files()
            result = self.process(text, provider="codex", cloud_consent=False)
            self.assertTrue(result["operator"])
            self.assertIsNone(result["cognitive_turn"])
            self.assertEqual(self.files(), before)
        self.assertEqual(self.backend.subscription.calls, [])
        self.assertFalse(self.state.exists())

    def test_natural_context_mutation_requires_confirmation(self):
        with self.assertRaisesRegex(ValueError, "Confirm the exact"):
            self.process("включи контекст")
        self.assertFalse(self.root.exists())

    def test_cloud_requires_boolean_consent_before_any_core_processing(self):
        for consent in [False, None, "true", 1]:
            with self.subTest(consent=consent), self.assertRaisesRegex(ValueError, "cloud processing"):
                self.process("Hello", provider="codex", cloud_consent=consent)
        self.assertEqual(self.backend.sessions, {})
        self.assertFalse(self.root.exists())

    def test_normal_cloud_turn_uses_same_pipeline_and_logs_original_input_once(self):
        params = self.params("Hello there", provider="codex", cloud_consent=True, history=[{"role": "user", "content": "earlier"}])
        events = []
        result = self.backend.process(params, events.append, "stream-id")
        self.assertEqual(result["cognitive_turn"]["reasoner_backend"], "codex_subscription")
        self.assertEqual(result["cognitive_turn"]["response"], "A local test answer.")
        self.assertEqual(len(self.backend.subscription.calls), 1)
        self.assertEqual("".join(event["delta"] for event in events), "A local test answer.")
        self.assertTrue(all(event["request_id"] == "stream-id" for event in events))
        log = self.root / "logs" / "session_operator_log.jsonl"
        records = [json.loads(line) for line in log.read_text().splitlines()]
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["user_input"], "Hello there")
        self.assertNotIn("Recent conversation", log.read_text())

    def test_normal_preference_keeps_existing_memory_evaluation_once(self):
        params = self.params("Я предпочитаю короткие ответы.")
        coordinator = self.backend._coordinator(params["conversation_id"])
        keeper = coordinator.memory_keeper
        with (patch.object(keeper, "evaluate_interaction", wraps=keeper.evaluate_interaction) as evaluate,
              patch.object(keeper, "apply_memory_updates", wraps=keeper.apply_memory_updates) as apply,
              patch.object(self.backend.logger, "append_turn", wraps=self.backend.logger.append_turn) as log):
            result = self.backend.process(params, lambda _: None, "id")
        for call in (evaluate, apply, log):
            call.assert_called_once()
        turn = result["cognitive_turn"]
        self.assertTrue(turn["memory_decision"]["should_store"])
        files = [path for path in self.data.glob("*memory.json")]
        records = [item for path in files for item in json.loads(path.read_text())]
        self.assertEqual(len(files), 2)
        self.assertTrue(all(len(json.loads(path.read_text())) == 1 for path in files))
        self.assertEqual(len({record["content"] for record in records}), 1)
        self.assertNotIn(turn["response"], records[0]["content"])

    def test_cloud_failure_and_cancellation_do_not_store_completed_turn(self):
        for failure in [codex.CodexConnectionError("cloud failed"), codex.TurnCancelled("stopped")]:
            self.backend.subscription.failure = failure
            before = self.files()
            with self.assertRaises(codex.CodexConnectionError):
                self.process("Я предпочитаю короткие ответы.", provider="codex", cloud_consent=True)
            self.assertEqual(self.files(), before)
        self.assertFalse(self.backend.busy.locked())

    def test_conversation_state_is_isolated_and_exit_discards_session(self):
        first, second = str(uuid4()), str(uuid4())
        one = self.backend._coordinator(first)
        one.pending_correction_hints = ["first session only"]
        two = self.backend._coordinator(second)
        self.assertEqual(two.pending_correction_hints, [])
        result = self.process("/exit", conversation_id=first)
        self.assertTrue(result["exit_requested"])
        self.assertNotIn(first, self.backend.sessions)
        self.assertEqual(self.backend._coordinator(first).pending_correction_hints, [])
        self.assertFalse(self.root.exists())

    def test_invalid_request_parameters_are_clean_and_do_not_write(self):
        fixtures = [self.params(""), self.params("x" * 32001), self.params("x\x00y"),
                    self.params(conversation_id="bad"), self.params(provider="api_key"),
                    self.params(model="x" * 161), self.params(history=[{"role": "system", "content": "hidden"}])]
        for params in fixtures:
            with self.subTest(params=params.keys()), self.assertRaises(ValueError):
                self.backend.process(params, lambda _: None, "id")
        self.assertFalse(self.root.exists())

    def test_history_is_bounded(self):
        history = [{"role": "user", "content": str(index) + "x" * 3000} for index in range(30)]
        result = bridge.bounded_history(history)
        self.assertEqual(len(result), 12)
        self.assertTrue(result[0]["content"].startswith("18"))
        self.assertTrue(all(len(item["content"]) == 2000 for item in result))

    def test_codex_thread_status_preview_and_reset_are_local_and_explicit(self):
        self.backend.subscription = codex.CodexSubscription(self.state, transport_factory=FakeRPC)
        conversation = str(uuid4())
        self.backend.subscription.threads.record_new(conversation, "thread-fixture", None,
                                                     mode="chat", model="fixture-model")
        status = self.backend.dispatch("codex_thread_status", {"conversation_id": conversation}, lambda _: None, "s")
        self.assertTrue(status["linked"] and status["workspace_matches"])
        preview = self.backend.preview_context({"text": "next", "conversation_id": conversation,
                                                "provider": "codex", "history": [
                                                    {"role": "user", "content": "must not replay"}],
                                                "cloud_consent": False})
        self.assertEqual(preview["history"], [])
        self.assertTrue(preview["manifest"]["provider_thread"]["linked"])
        before = self.backend.subscription.threads.path.read_bytes()
        with self.assertRaisesRegex(ValueError, "Explicit confirmation"):
            self.backend.dispatch("codex_thread_reset", {"conversation_id": conversation,
                                  "confirmation": "wrong"}, lambda _: None, "r")
        self.assertEqual(self.backend.subscription.threads.path.read_bytes(), before)
        result = self.backend.dispatch("codex_thread_reset", {"conversation_id": conversation,
                                       "confirmation": bridge.RESET_CODEX_THREAD_CONFIRMATION}, lambda _: None, "r")
        self.assertTrue(result["reset"] and result["no_provider_call"])
        self.assertFalse(self.backend.subscription.thread_status(conversation, None)["linked"])
        self.assertIsNone(self.backend.subscription.rpc)

    def test_local_ollama_refuses_non_loopback_url(self):
        with patch.object(ProtoMindConfig, "from_env", return_value=ProtoMindConfig(ollama_url="http://example.invalid")):
            with self.assertRaisesRegex(ValueError, "loopback"):
                self.process(provider="ollama")
        self.assertFalse(self.root.exists())

    def test_native_ollama_adds_history_without_changing_legacy_reasoner(self):
        history = [{"role": "assistant", "content": "earlier answer"}]
        reasoner = bridge.NativeOllamaReasoner(ProtoMindConfig(), history)
        payload = {"messages": [{"role": "system", "content": "policy"}, {"role": "user", "content": "now"}]}
        with patch.object(bridge, "local_ollama_request", return_value={"ok": True}) as post:
            reasoner._post("/api/chat", payload)
        self.assertEqual(post.call_args.args[2]["messages"], [payload["messages"][0], *history, payload["messages"][1]])
        self.assertEqual(len(payload["messages"]), 2)

    def test_unavailable_ollama_never_becomes_a_mock_answer_or_memory_write(self):
        with patch.object(bridge, "local_ollama_request", side_effect=OSError("offline")):
            with self.assertRaisesRegex(RuntimeError, "No fallback model"):
                self.process("Я предпочитаю короткие ответы.", provider="ollama")
        self.assertEqual(self.files(), {})

    def test_empty_ollama_answer_is_not_silently_replaced(self):
        with patch.object(bridge, "local_ollama_request", return_value={"message": {"content": ""}}):
            with self.assertRaisesRegex(RuntimeError, "No fallback model"):
                self.process(provider="ollama")
        self.assertEqual(self.files(), {})

    def test_cancel_never_kills_operator_operation(self):
        self.backend.active_request, self.backend.active_provider = "current", "operator"
        self.assertFalse(self.backend.cancel("current")["cancel_requested"])
        self.assertFalse(self.backend.subscription.interrupted)
        self.backend.active_provider = "codex"
        self.assertFalse(self.backend.cancel("wrong")["cancel_requested"])
        self.assertTrue(self.backend.cancel("current")["cancel_requested"])
        self.assertTrue(self.backend.subscription.interrupted)

    def test_stdio_invalid_requests_are_bounded_errors_without_traceback(self):
        source = io.StringIO('bad json\n' + json.dumps({"id": "r", "method": "not_a_method"}) + '\n')
        destination = io.StringIO()
        bridge.serve(self.backend, source, destination)
        rows = [json.loads(line) for line in destination.getvalue().splitlines()]
        self.assertEqual(len(rows), 2)
        self.assertTrue(all("error" in row for row in rows))
        self.assertNotIn("Traceback", destination.getvalue())
        self.assertFalse(self.root.exists())


class FakeRPC:
    def __init__(self, executable, home, workspace):
        self.workspace = workspace
        self.thread_id = "thread"
        self.closed = False
        self.calls = []
        self.account_type = "chatgpt"
        self.sandbox = {"type": "readOnly", "networkAccess": False}
        self.instruction_sources = []
        self.reset_events()
        self.model_data = [{"model": "fixture-model", "displayName": "Fixture Model", "isDefault": True,
                            "defaultReasoningEffort": "medium", "supportedReasoningEfforts": [
                                {"reasoningEffort": effort, "description": effort + " fixture"}
                                for effort in ("low", "medium", "high", "xhigh")]},
                           {"model": "hidden", "hidden": True}]

    def reset_events(self):
        self.events = [
            {"method": "item/reasoning/textDelta", "params": {"threadId": self.thread_id, "delta": "HIDDEN"}},
            {"method": "item/agentMessage/delta", "params": {"threadId": self.thread_id, "itemId": "answer", "delta": "Hello "}},
            {"method": "item/agentMessage/delta", "params": {"threadId": self.thread_id, "itemId": "answer", "delta": "operator."}},
            {"method": "item/completed", "params": {"threadId": self.thread_id, "item": {"type": "agentMessage", "id": "answer", "text": "Hello operator."}}},
            {"method": "turn/completed", "params": {"threadId": self.thread_id, "turn": {"id": "turn", "status": "completed"}}},
        ]

    def request(self, method, params=None, **kwargs):
        self.calls.append((method, params))
        if method in {"thread/start", "thread/resume"}:
            thread_id = self.thread_id if method == "thread/start" else params["threadId"]
            return {"thread": {"id": thread_id}, "sandbox": self.sandbox,
                    "approvalPolicy": "never", "cwd": str(self.workspace),
                    "instructionSources": self.instruction_sources}
        return {
            "account/read": {"account": {"type": self.account_type, "email": "fixture@example.invalid", "planType": "test"}},
            "account/login/start": {"type": "chatgpt", "authUrl": "https://auth.openai.com/authorize?fixture=1", "loginId": "id"},
            "model/list": {"data": self.model_data},
            "turn/start": {"turn": {"id": "turn"}},
        }.get(method, {})

    def next_event(self, timeout):
        if not self.events:
            raise codex.CodexConnectionError("fixture stream ended")
        return self.events.pop(0)

    def close(self):
        self.closed = True


class NativeProcessIsolationTests(unittest.TestCase):
    @unittest.skipUnless(codex.sys.platform == "darwin" and Path("/opt/homebrew/bin/node").exists(), "Homebrew Node check")
    def test_finder_environment_can_start_installed_node_without_shell_profiles(self):
        with tempfile.TemporaryDirectory(prefix="finder-runtime-test-") as temporary:
            root = Path(temporary).resolve()
            home, workspace = root / "profile", root / "workspace"
            for path in (home, workspace, root / "codex-user-home", home / "tmp"):
                path.mkdir()
            with patch.dict(os.environ, {"PATH": "/usr/bin:/bin:/usr/sbin:/sbin"}, clear=True):
                env = codex.codex_environment(home)
            prefix = codex.codex_process_command("/usr/bin/env", home, workspace)[:3]
            result = subprocess.run([*prefix, "/usr/bin/env", "node", "--version"], env=env,
                                    cwd=workspace, capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertRegex(result.stdout, r"^v\d+\.")

    @unittest.skipUnless(codex.sys.platform == "darwin" and Path("/usr/bin/sandbox-exec").exists(), "macOS isolation check")
    def test_provider_process_cannot_read_or_write_outside_its_private_profile(self):
        with tempfile.TemporaryDirectory(prefix="native-sandbox-test-") as temporary:
            root = Path(temporary).resolve()
            home, workspace = root / "profile", root / "workspace"
            for path in (home, workspace, root / "codex-user-home", home / "tmp"):
                path.mkdir()
            private = root / "personal.txt"
            private.write_text("private fixture")
            allowed = home / "fixture.txt"
            allowed.write_text("allowed fixture")
            link = workspace / "link.txt"
            link.symlink_to(private)
            prefix = codex.codex_process_command("/bin/cat", home, workspace)[:3]
            def run(*arguments):
                return subprocess.run([*prefix, *arguments], cwd=workspace,
                                      env=codex.codex_environment(home), capture_output=True,
                                      text=True, timeout=10)
            self.assertEqual(run("/bin/cat", str(allowed)).stdout, "allowed fixture")
            for path in (private, link):
                result = run("/bin/cat", str(path))
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn("private fixture", result.stdout)
            self.assertNotEqual(run("/usr/bin/touch", str(root / "outside-write")).returncode, 0)
            self.assertFalse((root / "outside-write").exists())
            self.assertEqual(private.read_text(), "private fixture")


class CodexAdapterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="codex-adapter-test-")
        self.addCleanup(self.temp.cleanup)
        self.client = codex.CodexSubscription(Path(self.temp.name), transport_factory=FakeRPC)
        self.conversation = str(uuid4())
        self.addCleanup(self.client.close)
        executable = patch.object(codex.shutil, "which", return_value="/not-executed/codex")
        executable.start()
        self.addCleanup(executable.stop)

    def answer(self, prompt="hello", instructions="instructions", model="", on_delta=lambda _: None, **kwargs):
        return self.client.answer(prompt, instructions, model, on_delta,
                                  conversation=self.conversation, logical_workspace=None, **kwargs)

    def test_profile_environment_does_not_inherit_credentials_or_parent_hooks(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "secret", "CODEX_HOME": "/parent", "CODEX_THREAD_ID": "internal", "OPENAI_BASE_URL": "https://untrusted.invalid"}):
            env = codex.codex_environment(self.client.home)
        self.assertEqual(env["CODEX_HOME"], str(self.client.home))
        self.assertEqual(env["HOME"], str(self.client.home.parent / "codex-user-home"))
        self.assertFalse(set(env) & {"OPENAI_API_KEY", "CODEX_THREAD_ID", "OPENAI_BASE_URL"})

    def test_finder_path_has_runtime_and_system_tools_without_relative_search_paths(self):
        with patch.dict(os.environ, {"PATH": ":./unsafe:/custom/bin:/usr/bin:/custom/bin"}, clear=True), patch.object(codex.sys, "platform", "darwin"):
            paths = codex.codex_environment(self.client.home)["PATH"].split(os.pathsep)
        self.assertEqual(paths[:2], ["/opt/homebrew/bin", "/usr/local/bin"])
        self.assertEqual(paths.count("/custom/bin"), 1)
        self.assertTrue(all(Path(path).is_absolute() for path in paths))
        self.assertIn("/usr/bin", paths)
        with patch.dict(os.environ, {}, clear=True):
            self.assertIn("/bin", codex.codex_environment(self.client.home)["PATH"].split(os.pathsep))

    def test_transport_eof_is_not_misreported_as_sign_in_failure(self):
        rpc = codex.CodexRPC.__new__(codex.CodexRPC)
        rpc.pending, rpc.sequence, rpc.closed, rpc.lock = {}, 0, False, threading.Lock()
        rpc.process = Mock()
        rpc.process.poll.return_value = None
        def end_stream(message):
            rpc.pending[message["id"]].put(None)
        with patch.object(rpc, "_send", side_effect=end_stream):
            with self.assertRaisesRegex(codex.CodexConnectionError, "Codex/Node.*sign-in was not checked"):
                rpc.request("initialize")
            with self.assertRaisesRegex(codex.CodexConnectionError, "closed during model/list"):
                rpc.request("model/list")
        self.assertEqual(rpc.pending, {})

    def test_dead_process_before_initialization_has_local_runtime_diagnostic(self):
        rpc = codex.CodexRPC.__new__(codex.CodexRPC)
        rpc.pending, rpc.sequence, rpc.closed, rpc.lock = {}, 0, True, threading.Lock()
        rpc.process = Mock()
        rpc.process.poll.return_value = 127
        with self.assertRaisesRegex(codex.CodexConnectionError, "stopped before initialization"):
            rpc.request("initialize")
        self.assertEqual(rpc.pending, {})

    def test_reader_eof_wakes_waiters_without_provider_error_text(self):
        rpc = codex.CodexRPC.__new__(codex.CodexRPC)
        rpc.lock, rpc.closed = threading.Lock(), False
        mailbox = queue.Queue()
        rpc.pending, rpc.process = {1: mailbox}, Mock(stdout=io.BytesIO())
        rpc._read()
        self.assertTrue(rpc.closed)
        self.assertIsNone(mailbox.get_nowait())

    def test_fixed_codex_arguments_disable_execution_extensions_and_api_fallback(self):
        args = codex.codex_arguments()
        self.assertEqual(args[:4], ["--strict-config", "app-server", "--listen", "stdio://"])
        for feature in codex.DISABLED_CODEX_FEATURES:
            self.assertIn(f"features.{feature}=false", args)
        for option in ['approval_policy="never"', 'sandbox_mode="read-only"', 'web_search="disabled"', 'model_provider="openai"', 'mcp_servers={}', 'notify=[]', 'tools.web_search=false', 'features.code_mode=false']:
            self.assertIn(option, args)
        self.assertNotIn('tools.view_image=false', args)  # Unsupported in Codex 0.136.

    def test_nonempty_provider_workspace_is_refused_without_reading_contents(self):
        self.client.workspace.mkdir()
        (self.client.workspace / "unexpected.txt").write_text("private fixture")
        with self.assertRaisesRegex(codex.CodexConnectionError, "not empty"):
            self.client.connect()
        self.assertIsNone(self.client.rpc)

    def test_missing_os_sandbox_never_falls_back_to_unsandboxed_provider(self):
        with patch.object(codex.os, "access", return_value=False), self.assertRaisesRegex(codex.CodexConnectionError, "unsandboxed"):
            codex.codex_process_command("codex", self.client.home, self.client.workspace)

    def test_login_accepts_only_official_https_hosts(self):
        self.assertEqual(codex.validate_login_url("https://auth.openai.com/authorize"), "https://auth.openai.com/authorize")
        for url in ["http://auth.openai.com", "https://auth.openai.com.evil.invalid", "https://user@auth.openai.com", "file:///tmp/token", "https://auth.openai.com:42", None]:
            with self.subTest(url=url), self.assertRaises(codex.CodexConnectionError):
                codex.validate_login_url(url)

    def test_login_and_model_list_use_installed_protocol_without_tokens(self):
        self.assertIn("auth.openai.com", self.client.login()["url"])
        models = self.client.models()
        self.assertEqual([item["id"] for item in models], ["fixture-model"])
        self.assertIn(("account/login/start", {"type": "chatgpt"}), self.client.rpc.calls)
        self.assertNotIn("secret", repr(self.client.account()))

    def test_model_catalog_projects_supported_efforts_and_no_unrelated_fields(self):
        rpc = self.client.connect()
        rpc.model_data[0]["private_field"] = "PRIVATE"
        rpc.model_data += [{"model": "future-model", "defaultReasoningEffort": "ultra",
                            "supportedReasoningEfforts": [{"reasoningEffort": "max"}, {"reasoningEffort": "ultra"},
                                                          {"reasoningEffort": "ultra"}, {"reasoningEffort": []}, None]},
                           {"model": "fixture-model"}, {"model": ""}, {"model": "bad\nmodel"}, None]
        options = self.client.models()
        self.assertEqual([item["id"] for item in options], ["fixture-model", "future-model"])
        self.assertEqual(options[0]["default_reasoning_effort"], "medium")
        self.assertEqual([item["id"] for item in options[0]["reasoning_efforts"]], ["low", "medium", "high", "xhigh"])
        self.assertEqual([item["id"] for item in options[1]["reasoning_efforts"]], ["max", "ultra"])
        self.assertNotIn("PRIVATE", json.dumps(options))

    def test_selected_effort_is_sent_as_protocol_effort_with_same_sandbox(self):
        self.answer(model="fixture-model", reasoning_effort="xhigh")
        calls = dict(self.client.rpc.calls)
        self.assertEqual(calls["turn/start"]["effort"], "xhigh")
        self.assertEqual(calls["thread/start"]["model"], "fixture-model")
        self.assertEqual(calls["thread/start"]["sandbox"], "read-only")
        self.assertNotIn("reasoning_effort", calls["turn/start"])
        self.assertNotIn("serviceTier", calls["turn/start"])

    def test_defaults_bind_catalog_model_and_its_default_effort(self):
        self.answer()
        calls = dict(self.client.rpc.calls)
        self.assertEqual(calls["thread/start"]["model"], "fixture-model")
        self.assertEqual(calls["turn/start"]["effort"], "medium")

    def test_unknown_model_or_unsupported_effort_never_starts_a_turn(self):
        rpc = self.client.connect()
        for model, effort in (("unknown", ""), ("hidden", ""), ("fixture-model", "ultra"), ("", "max")):
            with self.subTest(model=model, effort=effort), self.assertRaisesRegex(codex.CodexConnectionError, "no fallback"):
                self.answer(model=model, reasoning_effort=effort)
        self.assertFalse(any(method in {"thread/start", "turn/start"} for method, _ in rpc.calls))

    def test_effort_is_revalidated_after_catalog_changes(self):
        rpc = self.client.connect()
        self.assertEqual(len(self.client.models()[0]["reasoning_efforts"]), 4)
        rpc.model_data[0]["supportedReasoningEfforts"] = [{"reasoningEffort": "low"}]
        with self.assertRaisesRegex(codex.CodexConnectionError, "not supported"):
            self.answer(model="fixture-model", reasoning_effort="high")
        self.assertFalse(any(method == "turn/start" for method, _ in rpc.calls))

    def test_missing_effort_metadata_does_not_invent_levels(self):
        rpc = self.client.connect()
        rpc.model_data = [{"model": "legacy", "isDefault": True, "defaultReasoningEffort": "high"}]
        option = self.client.models()[0]
        self.assertEqual(option["reasoning_efforts"], [])
        self.assertEqual(option["default_reasoning_effort"], "")
        self.answer(model="legacy")
        self.assertNotIn("effort", dict(rpc.calls)["turn/start"])

    def test_catalog_pagination_preserves_models_and_refuses_cursor_cycles(self):
        rpc = self.client.connect()
        original = rpc.request
        def paginated(method, params=None, **kwargs):
            if method == "model/list":
                return {"data": [{"model": "second-page"}]} if params.get("cursor") else {"data": rpc.model_data, "nextCursor": "next"}
            return original(method, params, **kwargs)
        with patch.object(rpc, "request", side_effect=paginated):
            self.assertEqual([item["id"] for item in self.client.models()], ["fixture-model", "second-page"])
        def looping(method, params=None, **kwargs):
            return {"data": [], "nextCursor": "same"} if method == "model/list" else original(method, params, **kwargs)
        with patch.object(rpc, "request", side_effect=looping), self.assertRaisesRegex(codex.CodexConnectionError, "incomplete"):
            self.client.models()

    def test_invalid_model_catalog_returns_clean_error(self):
        self.client.connect().model_data = {"bad": "shape"}
        with self.assertRaisesRegex(codex.CodexConnectionError, "invalid model catalog"):
            self.client.models()

    def test_api_key_accounts_are_never_used(self):
        self.client.connect().account_type = "apiKey"
        with self.assertRaisesRegex(codex.CodexConnectionError, "API-key"):
            self.client.models()
        with self.assertRaisesRegex(codex.CodexConnectionError, "API-key fallback"):
            self.answer()
        self.assertFalse(any(method == "thread/start" for method, _ in self.client.rpc.calls))

    def test_stream_forwards_only_assistant_text_not_internal_prompts(self):
        deltas = []
        result = self.answer(instructions="local instructions", model="fixture-model", on_delta=deltas.append)
        self.assertEqual(result, "Hello operator.")
        self.assertEqual("".join(deltas), result)
        self.assertNotIn("HIDDEN", "".join(deltas))
        start = dict(self.client.rpc.calls)["thread/start"]
        self.assertEqual(start["sandbox"], "read-only")
        self.assertEqual(start["approvalPolicy"], "never")
        self.assertFalse(start["ephemeral"])
        self.assertIsNone(self.client.active_turn)

    def test_durable_thread_resumes_without_replaying_local_history(self):
        history = [{"role": "user", "content": "earlier local turn"}]
        self.answer(prompt="first", history=history)
        rpc = self.client.rpc
        first_input = [params for method, params in rpc.calls if method == "turn/start"][0]["input"][0]["text"]
        self.assertIn("earlier local turn", first_input)
        rpc.reset_events()
        self.answer(prompt="second", history=history + [{"role": "assistant", "content": "old answer"}])
        methods = [method for method, _ in rpc.calls]
        self.assertEqual(methods.count("thread/start"), 1)
        self.assertEqual(methods.count("thread/resume"), 1)
        resume = [params for method, params in rpc.calls if method == "thread/resume"][0]
        self.assertEqual(resume["threadId"], "thread")
        self.assertTrue(resume["excludeTurns"])
        second_input = [params for method, params in rpc.calls if method == "turn/start"][1]["input"][0]["text"]
        self.assertEqual(second_input, "second")
        self.assertEqual(self.client.last_thread_info["state"], "resumed")

    def test_durable_thread_uses_exact_legacy_instructions_on_immediate_persona_rollback(self):
        persona = "Proto-Mind Persona Context v1\npersona-active-fixture"
        legacy = "legacy prompt bytes: unchanged"
        self.answer(prompt="persona turn", instructions=persona)
        rpc = self.client.rpc
        rpc.reset_events()

        self.answer(prompt="next turn", instructions=legacy)

        start = next(params for method, params in rpc.calls if method == "thread/start")
        resume = next(params for method, params in rpc.calls if method == "thread/resume")
        self.assertEqual(start["baseInstructions"], persona)
        self.assertEqual(resume["baseInstructions"], legacy)
        self.assertNotIn("Persona Context", resume["baseInstructions"])
        self.assertEqual(sum(method == "turn/start" for method, _ in rpc.calls), 2)

    def test_durable_binding_survives_subscription_restart(self):
        self.answer(prompt="first")
        self.client.close()
        restarted = codex.CodexSubscription(Path(self.temp.name), transport_factory=FakeRPC)
        self.addCleanup(restarted.close)
        result = restarted.answer("after restart", "instructions", "", lambda _: None,
                                  conversation=self.conversation, logical_workspace=None, history=[])
        self.assertEqual(result, "Hello operator.")
        methods = [method for method, _ in restarted.rpc.calls]
        self.assertIn("thread/resume", methods)
        self.assertNotIn("thread/start", methods)
        self.assertEqual(restarted.last_thread_info["state"], "resumed")

    def test_resume_failure_never_creates_replacement_thread_or_turn(self):
        self.answer(prompt="first")
        rpc = self.client.rpc
        before = list(rpc.calls)
        original = rpc.request
        def fail_resume(method, params=None, **kwargs):
            if method == "thread/resume":
                raise codex.CodexConnectionError("fixture provider failure")
            return original(method, params, **kwargs)
        rpc.reset_events()
        with patch.object(rpc, "request", side_effect=fail_resume), self.assertRaisesRegex(
                codex.CodexConnectionError, "no replacement thread"):
            self.answer(prompt="second")
        new_calls = rpc.calls[len(before):]
        self.assertFalse(any(method in {"thread/start", "turn/start"} for method, _ in new_calls))
        self.assertTrue(self.client.thread_status(self.conversation, None)["linked"])

    def test_resume_policy_drift_refuses_before_second_turn(self):
        self.answer(prompt="first")
        rpc = self.client.rpc
        rpc.reset_events()
        rpc.sandbox = {"type": "workspaceWrite"}
        before = len(rpc.calls)
        with self.assertRaisesRegex(codex.CodexConnectionError, "isolated read-only"):
            self.answer(prompt="second")
        new_calls = rpc.calls[before:]
        self.assertTrue(any(method == "thread/resume" for method, _ in new_calls))
        self.assertFalse(any(method in {"thread/start", "turn/start"} for method, _ in new_calls))

    def test_workspace_drift_refuses_resume_until_explicit_reset(self):
        workspace = {"path": "/tmp/project", "device": 1, "inode": 2}
        self.client.answer("first", "instructions", "", lambda _: None,
                           conversation=self.conversation, logical_workspace=workspace, history=[])
        rpc = self.client.rpc
        before = len(rpc.calls)
        changed = {**workspace, "inode": 3}
        with self.assertRaisesRegex(codex.CodexConnectionError, "another workspace"):
            self.client.answer("second", "instructions", "", lambda _: None,
                               conversation=self.conversation, logical_workspace=changed, history=[])
        self.assertFalse(any(method in {"thread/start", "thread/resume", "turn/start"}
                             for method, _ in rpc.calls[before:]))
        reset = self.client.reset_thread(self.conversation)
        self.assertTrue(reset["reset"])
        rpc.reset_events()
        self.client.answer("new session", "instructions", "", lambda _: None,
                           conversation=self.conversation, logical_workspace=changed, history=[])
        self.assertEqual(sum(method == "thread/start" for method, _ in rpc.calls), 2)

    def test_unexpected_server_sandbox_or_instructions_fail_before_turn(self):
        rpc = self.client.connect()
        for sandbox, instructions in [({"type": "workspaceWrite"}, []), ({"type": "readOnly", "networkAccess": True}, []), ({"type": "readOnly"}, []), ({"type": "readOnly", "networkAccess": "false"}, []), ({"type": "readOnly", "networkAccess": False}, ["unexpected AGENTS.md"])]:
            rpc.sandbox, rpc.instruction_sources = sandbox, instructions
            with self.subTest(sandbox=sandbox), self.assertRaisesRegex(codex.CodexConnectionError, "isolated read-only"):
                self.answer()
        self.assertFalse(any(method == "turn/start" for method, _ in rpc.calls))

    def test_non_chat_item_fails_closed_and_interrupts(self):
        rpc = self.client.connect()
        rpc.events.insert(0, {"method": "item/started", "params": {"threadId": "thread", "item": {"type": "commandExecution"}}})
        with self.assertRaisesRegex(codex.CodexConnectionError, "non-chat"):
            self.answer()
        self.assertTrue(any(method == "turn/interrupt" for method, _ in rpc.calls))

    def test_server_tool_requests_fail_closed(self):
        self.client.connect().events.insert(0, {"method": "proto_mind/tool_refused", "params": {}})
        with self.assertRaisesRegex(codex.CodexConnectionError, "tool request"):
            self.answer()

    def test_cancellation_before_start_prevents_cloud_turn(self):
        self.client.interrupt()
        with self.assertRaises(codex.TurnCancelled):
            self.answer()
        self.assertIsNone(self.client.rpc)

    def test_failed_turn_returns_no_answer_and_is_not_retried(self):
        rpc = self.client.connect()
        rpc.events = [{"method": "turn/completed", "params": {"threadId": "thread", "turn": {"id": "turn", "status": "failed"}}}]
        with self.assertRaisesRegex(codex.CodexConnectionError, "did not complete"):
            self.answer()
        self.assertEqual(sum(method == "turn/start" for method, _ in rpc.calls), 1)

    def test_large_answer_is_refused_before_display(self):
        rpc = self.client.connect()
        rpc.events = [{"method": "item/agentMessage/delta", "params": {"threadId": "thread", "delta": "x" * (codex.MAX_ANSWER_CHARS + 1)}}]
        display = Mock()
        with self.assertRaisesRegex(codex.CodexConnectionError, "display limit"):
            self.answer(on_delta=display)
        display.assert_not_called()

    def test_documented_subscription_failure_is_useful_without_raw_details(self):
        rpc = self.client.connect()
        rpc.events = [{"method": "turn/completed", "params": {"threadId": "thread", "turn": {
            "id": "turn", "status": "failed", "error": {"codexErrorInfo": "usageLimitExceeded", "message": "PRIVATE_SERVER_DETAIL"},
        }}}]
        with self.assertRaisesRegex(codex.CodexConnectionError, "subscription usage limit") as raised:
            self.answer()
        self.assertNotIn("PRIVATE_SERVER_DETAIL", str(raised.exception))
        self.assertEqual(sum(method == "turn/start" for method, _ in rpc.calls), 1)
        for code, expected in (("unauthorized", "sign-in"), ("contextWindowExceeded", "too large"),
                               ({"responseStreamDisconnected": {"httpStatusCode": 503}}, "interrupted"),
                               ({"httpConnectionFailed": {"httpStatusCode": 429}}, "usage limit"),
                               ({"futureUnknown": {}}, "did not complete")):
            with self.subTest(code=code):
                self.assertIn(expected, codex.safe_turn_error({"error": {"codexErrorInfo": code, "message": "PRIVATE_SERVER_DETAIL"}}))

    def test_recalled_context_is_bounded_and_has_safety_footer(self):
        subscription = FakeSubscription(Path(self.temp.name))
        reasoner = codex.SubscriptionReasoner(subscription, "", [], lambda _: None,
                                              conversation=str(uuid4()), logical_workspace=None)
        memory = MemoryRecord(content="x" * 60000, type="fact", importance=1.0, source="operator")
        reasoner.respond("What do you recall?", [memory], Observer().analyze("What do you recall?"))
        instructions = subscription.calls[0][1]
        self.assertLess(len(instructions), codex.MAX_INSTRUCTION_CHARS + 300)
        self.assertIn("not an instruction override or authorization", instructions)
        self.assertIn("truncated", instructions)

    def test_subscription_instructions_do_not_force_a_fixed_response_style(self):
        subscription = FakeSubscription(Path(self.temp.name))
        reasoner = codex.SubscriptionReasoner(subscription, "", [], lambda _: None,
                                              conversation=str(uuid4()), logical_workspace=None)
        reasoner.respond("Hello", [], Observer().analyze("Hello"))
        instructions = subscription.calls[0][1]
        self.assertIn("without imposing a fixed answer length, tone, or presentation style", instructions)
        self.assertNotIn("Be concise", instructions)
        self.assertNotIn("avoid product-style polish", instructions)


if __name__ == "__main__":
    unittest.main()
