"""Full Mac permission and activity contracts, without real model/tool execution."""
from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path
import plistlib
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch
from uuid import uuid4

from proto_mind import native_agent as agent
from proto_mind import native_bridge as bridge
from proto_mind import native_codex as codex
from proto_mind import native_codex_threads as codex_threads
from proto_mind import native_computer_use as computer_use
from proto_mind.native_work_sessions import workspace_identity
from proto_mind.config import ProtoMindConfig
from proto_mind.tests.test_native import FakeRPC, FakeSubscription


class FakeAgentSubscription(FakeSubscription):
    def agent_answer(self, prompt, instructions, model, on_delta, *, conversation, logical_workspace,
                     history=None, workspace, on_activity, on_progress=None, reasoning_effort="", images=None,
                     criteria=None):
        self.calls.append((prompt, instructions, model, workspace))
        self.reasoning_efforts.append(reasoning_effort)
        self.last_thread_info = {"schema": "proto_mind.native_codex_thread.v1", "state": "started",
                                 "thread_id_short": "fixture", "persistent": True,
                                 "workspace": logical_workspace, "mode": "full_access", "model": model}
        run = agent.AgentRun(workspace, on_activity)
        run.record({"id": "cmd", "type": "commandExecution", "command": "fixture only",
                    "cwd": str(workspace), "status": "completed", "exitCode": 0,
                    "aggregatedOutput": "fixture output"}, True)
        run.finish("failed" if self.failure else "completed")
        if self.failure:
            raise self.failure
        on_delta("Agent fixture answer.")
        return "Agent fixture answer."


class NativeAgentPermissionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="native-agent-permission-")
        self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name).resolve()
        self.root, self.state, self.workspace = base / "project", base / "state", base / "workspace"
        self.workspace.mkdir()
        self.backend = bridge.NativeBackend(self.root, self.state, subscription_factory=FakeAgentSubscription)
        self.addCleanup(self.backend.close)
        self.conversation = str(uuid4())
        config = patch.object(ProtoMindConfig, "from_env", return_value=ProtoMindConfig(data_dir=self.root / "proto_mind/data"))
        config.start()
        self.addCleanup(config.stop)

    def request(self, **overrides):
        return {"conversation_id": self.conversation, "mode": "full_access", "cloud_consent": True,
                "workspace_root": str(self.workspace), "confirmation": agent.FULL_ACCESS_CONFIRMATION, **overrides}

    def test_agent_instructions_do_not_force_short_operator_updates(self):
        self.assertNotIn("Keep command output concise", agent.AGENT_INSTRUCTIONS)
        self.assertNotIn("brief user-facing commentary", agent.AGENT_INSTRUCTIONS)
        self.assertNotIn("honor Rule 0", agent.AGENT_INSTRUCTIONS)
        self.assertNotIn("ask in your answer rather than guessing", agent.AGENT_INSTRUCTIONS)
        self.assertIn("without asking for routine", agent.AGENT_INSTRUCTIONS)
        self.assertIn("make reasonable assumptions and state them", agent.AGENT_INSTRUCTIONS)
        self.assertIn("Do not print secrets or irrelevant raw output", agent.AGENT_INSTRUCTIONS)

    def grant(self, **overrides):
        return self.backend.dispatch("agent_access", self.request(**overrides), lambda _: None, "grant")

    def params(self, **overrides):
        return {"conversation_id": self.conversation, "text": "Hello", "provider": "codex", "cloud_consent": True,
                "access_mode": "full_access", "workspace_root": str(self.workspace), **overrides}

    def test_enabling_is_separate_explicit_and_does_not_write_or_connect(self):
        for changes in ({"cloud_consent": False}, {"cloud_consent": 1}, {"confirmation": "yes"}, {"mode": "auto"}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.grant(**changes)
        grant = self.grant()
        self.assertEqual(grant["mode"], "full_access")
        self.assertGreaterEqual(len(grant["token"]), 32)
        self.assertFalse(self.root.exists())
        self.assertFalse(self.state.exists())
        self.assertEqual(self.backend.subscription.calls, [])

    def test_turn_cannot_self_authorize_from_boolean_or_confirmation_text(self):
        for token in (None, True, "made-up-token", agent.FULL_ACCESS_CONFIRMATION):
            with self.subTest(token=token), self.assertRaisesRegex(ValueError, "missing or expired"):
                self.backend.process(self.params(access_token=token), lambda _: None, "r")
        self.assertEqual(self.backend.sessions, {})
        self.assertFalse(self.root.exists())

    def test_grant_is_bound_to_conversation_and_workspace(self):
        grant = self.grant()
        other = self.workspace.parent / "other"
        other.mkdir()
        for changes in ({"conversation_id": str(uuid4())}, {"workspace_root": str(other)}):
            with self.subTest(changes=changes), self.assertRaisesRegex(ValueError, "missing or expired"):
                self.backend.process(self.params(access_token=grant["token"], **changes), lambda _: None, "r")
        self.assertFalse(self.root.exists())

    def test_replaced_workspace_invalidates_grant(self):
        grant = self.grant()
        self.workspace.rename(self.workspace.with_name("old-workspace"))
        self.workspace.mkdir()
        with self.assertRaisesRegex(ValueError, "replaced"):
            self.backend.process(self.params(access_token=grant["token"]), lambda _: None, "r")

    def test_revoke_and_restart_invalidate_token_without_storage(self):
        grant = self.grant()
        self.grant(mode="chat")
        with self.assertRaises(ValueError):
            self.backend.process(self.params(access_token=grant["token"]), lambda _: None, "r")
        self.grant()
        self.backend.close()
        with self.assertRaises(ValueError):
            self.backend.agent_grants.validate(self.conversation, self.workspace, grant["token"])
        self.assertFalse(self.state.exists())

    def test_explicit_agent_turn_uses_core_once_and_has_scoped_activity(self):
        grant = self.grant()
        events = []
        result = self.backend.process(self.params(access_token=grant["token"], reasoning_effort="high"), lambda e: events.append(deepcopy(e)), "turn-id")
        self.assertEqual(result["cognitive_turn"]["response"], "Agent fixture answer.")
        self.assertEqual(result["agent_run"]["command_count"], 1)
        self.assertEqual(len(self.backend.subscription.calls), 1)
        self.assertEqual(self.backend.subscription.calls[0][3], self.workspace)
        self.assertEqual(self.backend.subscription.reasoning_efforts, ["high"])
        self.assertTrue(all(e["request_id"] == "turn-id" for e in events))
        self.assertNotIn(grant["token"], json.dumps(result))
        log = self.root / "logs/session_operator_log.jsonl"
        rows = [json.loads(line) for line in log.read_text().splitlines()]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["user_input"], "Hello")
        self.assertNotIn("fixture output", log.read_text())

    def test_chat_remains_chat_even_if_conversation_has_grant(self):
        self.grant()
        result = self.backend.process(self.params(access_mode="chat"), lambda _: None, "r")
        self.assertIsNone(result["agent_run"])
        self.assertEqual(len(self.backend.subscription.calls[0]), 3)

    def test_operator_inputs_bypass_agent_grant_and_model(self):
        self.grant()
        for text in ("/commands status", "что делать дальше"):
            result = self.backend.process(self.params(text=text, cloud_consent=False, access_token="bad"), lambda _: None, "r")
            self.assertTrue(result["operator"])
            self.assertIsNone(result["agent_run"])
        self.assertEqual(self.backend.subscription.calls, [])
        with self.assertRaisesRegex(ValueError, "Confirm the exact"):
            self.backend.process(self.params(text="включи контекст"), lambda _: None, "r")
        self.assertFalse(self.root.exists())

    def test_other_providers_and_unknown_modes_do_not_inherit_tools(self):
        grant = self.grant()
        for changes in ({"provider": "ollama"}, {"provider": "mock"}, {"access_mode": "unrestricted"}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.backend.process(self.params(access_token=grant["token"], **changes), lambda _: None, "r")
        self.assertFalse(self.root.exists())

    def test_failed_tool_turn_keeps_receipt_but_not_completed_memory_turn(self):
        grant = self.grant()
        self.backend.subscription.failure = codex.TurnCancelled("Stopped after a fixture action")
        events = []
        with self.assertRaises(codex.TurnCancelled):
            self.backend.process(self.params(text="I prefer short answers.", access_token=grant["token"]), events.append, "r")
        receipts = [e["receipt"] for e in events if e["event"] == "agent_run"]
        self.assertTrue(receipts[-1]["execution_may_have_occurred"])
        self.assertFalse(self.root.exists())
        self.assertFalse(self.backend.busy.locked())

    def test_disconnect_cancels_model_not_core_writes_and_refuses_queued_turns(self):
        self.grant()
        self.backend.active_request, self.backend.active_provider = "r", "codex"
        self.backend.disconnect()
        self.assertTrue(self.backend.subscription.interrupted)
        with self.assertRaisesRegex(ValueError, "disconnected"):
            self.backend.process(self.params(), lambda _: None, "r2")

    def test_no_arbitrary_native_execution_method_is_exposed(self):
        self.grant()
        with self.assertRaisesRegex(ValueError, "Unknown native bridge method"):
            self.backend.dispatch("command_exec", {"command": "anything"}, lambda _: None, "r")


class AgentRPC(FakeRPC):
    def __init__(self, executable, home, workspace, *, full_access=False, computer_use=None):
        super().__init__(executable, home, workspace)
        self.full_access = full_access
        self.computer_use = computer_use
        self.computer_use_tools = set(agent.COMPUTER_USE_TOOLS) if computer_use else set()
        if full_access:
            self.thread_id = "agent-thread"
            self.sandbox = {"type": "dangerFullAccess"}
            self.events = [
                {"method": "item/started", "params": {"threadId": self.thread_id, "turnId": "turn", "item": {
                    "id": "command", "type": "commandExecution", "command": "fixture-command", "cwd": str(workspace), "status": "inProgress"}}},
                {"method": "item/completed", "params": {"threadId": self.thread_id, "turnId": "turn", "item": {
                    "id": "command", "type": "commandExecution", "command": "fixture-command", "cwd": str(workspace), "status": "completed",
                    "aggregatedOutput": "fixture output", "exitCode": 0, "private_unknown_field": "DO_NOT_FORWARD"}}},
                {"method": "item/started", "params": {"threadId": self.thread_id, "turnId": "turn", "item": {
                    "id": "web", "type": "webSearch", "query": "Codex internet access"}}},
                {"method": "item/completed", "params": {"threadId": self.thread_id, "turnId": "turn", "item": {
                    "id": "web", "type": "webSearch", "query": "Codex internet access",
                    "action": {"type": "openPage", "url": "https://example.invalid/docs?secret=HIDDEN_QUERY#private"},
                    "results": [{"snippet": "PRIVATE_WEB_RESULT"}], "private_unknown_field": "PRIVATE_WEB_FIELD"}}},
                {"method": "item/started", "params": {"threadId": self.thread_id, "turnId": "turn", "item": {
                    "id": "screen", "type": "mcpToolCall", "server": "computer-use", "tool": "type_text",
                    "status": "inProgress", "arguments": {"app_name": "Calculator", "text": "PRIVATE_TYPED_TEXT", "x": 44, "y": 55},
                    "appContext": {"appName": "Calculator"}}}},
                {"method": "item/completed", "params": {"threadId": self.thread_id, "turnId": "turn", "item": {
                    "id": "screen", "type": "mcpToolCall", "server": "computer-use", "tool": "type_text",
                    "status": "completed", "durationMs": 120, "arguments": {"app_name": "Calculator", "text": "PRIVATE_TYPED_TEXT", "x": 44, "y": 55},
                    "appContext": {"appName": "Calculator"}, "result": {"content": ["PRIVATE_SCREENSHOT"],
                    "structuredContent": {"accessibilityTree": "PRIVATE_UI_TREE"}}}}},
                {"method": "item/completed", "params": {"threadId": self.thread_id, "turnId": "turn", "item": {
                    "id": "comment", "type": "agentMessage", "phase": "commentary", "text": "Checking..."}}},
                {"method": "item/reasoning/textDelta", "params": {"threadId": self.thread_id, "turnId": "turn", "delta": "HIDDEN_REASONING"}},
                {"method": "item/completed", "params": {"threadId": self.thread_id, "turnId": "turn", "item": {
                    "id": "answer", "type": "agentMessage", "phase": "final_answer", "text": "Verified fixture."}}},
                {"method": "turn/completed", "params": {"threadId": self.thread_id, "turn": {"id": "turn", "status": "completed"}}},
            ]


class CodexAgentAdapterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="native-agent-adapter-")
        self.addCleanup(self.temp.cleanup)
        self.workspace = Path(self.temp.name).resolve() / "project"
        self.workspace.mkdir()
        self.transports = []
        self.transform = lambda rpc: None

        def factory(*args, **kwargs):
            rpc = AgentRPC(*args, **kwargs)
            self.transports.append(rpc)
            if rpc.full_access:
                self.transform(rpc)
            return rpc

        self.client = codex.CodexSubscription(Path(self.temp.name) / "state", transport_factory=factory)
        self.addCleanup(self.client.close)
        executable = patch.object(codex.shutil, "which", return_value="/not-executed/codex")
        executable.start()
        self.addCleanup(executable.stop)
        self.events = []
        self.conversation = str(uuid4())
        self.logical_workspace = workspace_identity(self.workspace)
        capability = patch.object(codex, "discover_computer_use", return_value={
            "available": True, "provider": "openai_signed_local_service", "version": "fixture",
            "reason": "verified", "command": "/verified/SkyComputerUseClient",
        })
        capability.start()
        self.addCleanup(capability.stop)

    def answer(self):
        return self.client.agent_answer("fixture request", "local context", "", lambda _: None,
                                        conversation=self.conversation, logical_workspace=self.logical_workspace,
                                        history=[], workspace=self.workspace,
                                        on_activity=lambda e: self.events.append(deepcopy(e)))

    def test_full_mode_enables_only_builtins_without_changing_chat_isolation(self):
        full = codex.codex_arguments(full_access=True)
        for option in ('sandbox_mode="danger-full-access"', 'approval_policy="never"', 'web_search="live"',
                       "tools.web_search=true", "features.standalone_web_search=true",
                       "features.shell_tool=true", "features.unified_exec=true"):
            self.assertIn(option, full)
        for feature in set(codex.DISABLED_CODEX_FEATURES) - {"shell_tool", "unified_exec", "standalone_web_search"}:
            self.assertIn(f"features.{feature}=false", full)
        chat = codex.codex_arguments()
        for option in ('web_search="disabled"', "tools.web_search=false", "features.standalone_web_search=false",
                       "features.shell_tool=false", "features.unified_exec=false"):
            self.assertIn(option, chat)
        self.assertEqual(codex.codex_process_command("codex", Path("/tmp/profile"), self.workspace, full_access=True)[0], "codex")
        self.assertEqual(codex.codex_process_command("codex", Path("/tmp/profile"), self.workspace)[0], "/usr/bin/sandbox-exec")
        cua = codex.codex_arguments(full_access=True, computer_use_command="/verified/SkyComputerUseClient")
        for option in ('features.computer_use=true',
                       'notify=["/verified/SkyComputerUseClient", "turn-ended"]',
                       'mcp_servers.computer-use.command="/verified/SkyComputerUseClient"',
                       'mcp_servers.computer-use.args=["mcp"]',
                       'mcp_servers.computer-use.required=true',
                       'mcp_servers.computer-use.supports_parallel_tool_calls=false'):
            self.assertIn(option, cua)
        self.assertIn("mcp_servers.computer-use.enabled_tools=", " ".join(cua))
        self.assertFalse(any("mcp_servers.computer-use.command" in option for option in chat))
        self.assertIn("notify=[]", chat)
        self.assertIn("notify=[]", full)

    def test_computer_use_turn_end_cleanup_hook_is_exact_and_scoped(self):
        cua = codex.codex_arguments(full_access=True, computer_use_command="/verified/SkyComputerUseClient")
        notify = [value for value in cua if value.startswith("notify=")]
        self.assertEqual(notify, ['notify=["/verified/SkyComputerUseClient", "turn-ended"]'])
        self.assertNotIn("turn-ended", codex.codex_arguments(full_access=True))
        self.assertNotIn("turn-ended", codex.codex_arguments())

    def test_computer_use_timeout_is_bounded_without_parallel_retry(self):
        cua = codex.codex_arguments(full_access=True, computer_use_command="/verified/SkyComputerUseClient")
        self.assertIn(f"mcp_servers.computer-use.tool_timeout_sec={codex.COMPUTER_USE_TOOL_TIMEOUT_SECONDS}", cua)
        self.assertEqual(codex.COMPUTER_USE_TOOL_TIMEOUT_SECONDS, 30)
        self.assertIn("mcp_servers.computer-use.supports_parallel_tool_calls=false", cua)

    def test_computer_use_turn_gets_fresh_state_guidance_even_on_durable_thread(self):
        self.assertEqual(self.answer(), "Verified fixture.")
        full = [rpc for rpc in self.transports if rpc.full_access][-1]
        prompt = [params for method, params in full.calls if method == "turn/start"][0]["input"][0]["text"]
        self.assertIn("first get_app_state call for each app", prompt)
        self.assertIn("disableDiff=true", prompt)
        self.assertIn("do not retry the same app", prompt)
        self.assertIn("fixture request", prompt)

    def test_agent_records_actions_and_only_final_answer_then_closes_full_process(self):
        self.assertEqual(self.answer(), "Verified fixture.")
        receipt = self.events[-1]["receipt"]
        self.assertEqual(receipt["status"], "completed")
        self.assertEqual(receipt["command_count"], 1)
        self.assertEqual(receipt["web_search_count"], 1)
        self.assertEqual(receipt["computer_use_count"], 1)
        self.assertTrue(receipt["network_access_performed"])
        self.assertTrue(receipt["computer_use_performed"])
        self.assertTrue(receipt["screen_access_performed"])
        self.assertEqual(receipt["contract"]["provider"], "codex_subscription")
        self.assertEqual(len(receipt["contract_hash"]), 64)
        self.assertTrue(receipt["runtime_inventory"]["verified"])
        self.assertEqual(set(receipt["runtime_inventory"]["computer_use_tools"]), set(computer_use.COMPUTER_USE_TOOLS))
        self.assertFalse(receipt["contract"]["limits"]["automatic_retry"])
        self.assertFalse(receipt["contract"]["permissions"]["background_execution"])
        self.assertEqual(receipt["items"][0]["exit_code"], 0)
        web = next(item for item in receipt["items"] if item["kind"] == "webSearch")
        self.assertEqual(web, {"id": "web", "kind": "webSearch", "status": "completed",
                               "query": "Codex internet access", "action_type": "openPage",
                               "url": "https://example.invalid/docs"})
        screen = next(item for item in receipt["items"] if item["kind"] == "computerUse")
        self.assertEqual(screen, {"id": "screen", "kind": "computerUse", "status": "completed",
                                  "tool": "type_text", "app": "Calculator",
                                  "note": "Typed input omitted from the local journal.", "duration_ms": 120})
        self.assertNotIn("DO_NOT_FORWARD", json.dumps(self.events))
        self.assertNotIn("PRIVATE_WEB", json.dumps(self.events))
        self.assertNotIn("HIDDEN_QUERY", json.dumps(self.events))
        self.assertNotIn("HIDDEN_REASONING", json.dumps(self.events))
        self.assertNotIn("PRIVATE_TYPED_TEXT", json.dumps(self.events))
        self.assertNotIn("PRIVATE_SCREENSHOT", json.dumps(self.events))
        self.assertNotIn("PRIVATE_UI_TREE", json.dumps(self.events))
        self.assertIsNone(self.client.rpc)
        self.assertTrue(all(rpc.closed for rpc in self.transports))
        self.assertFalse(self.client.connect().full_access)

    def test_web_receipt_refuses_credential_or_non_http_locations(self):
        self.assertEqual(agent.safe_web_url("https://user:secret@example.invalid/private?token=1"), "")
        self.assertEqual(agent.safe_web_url("file:///Users/operator/private"), "")
        self.assertEqual(agent.safe_web_url("https://example.invalid/path?token=1#private"),
                         "https://example.invalid/path")

    def test_chat_and_full_access_use_separate_durable_instruction_threads(self):
        self.assertEqual(self.client.answer("chat first", "instructions", "", lambda _: None,
                                           conversation=self.conversation,
                                           logical_workspace=self.logical_workspace, history=[]), "Hello operator.")
        self.assertEqual(self.answer(), "Verified fixture.")
        full = [rpc for rpc in self.transports if rpc.full_access][-1]
        self.assertIn("thread/start", [method for method, _ in full.calls])
        self.assertNotIn("thread/resume", [method for method, _ in full.calls])
        self.assertEqual(self.client.thread_status(self.conversation, self.logical_workspace)["last_mode"], "full_access")
        result = self.client.answer("chat again", "instructions", "", lambda _: None,
                                    conversation=self.conversation,
                                    logical_workspace=self.logical_workspace, history=[])
        self.assertEqual(result, "Hello operator.")
        chat = self.transports[-1]
        self.assertFalse(chat.full_access)
        self.assertIn("thread/resume", [method for method, _ in chat.calls])
        self.assertNotIn("thread/start", [method for method, _ in chat.calls])
        self.assertEqual(self.client.thread_status(self.conversation, self.logical_workspace)["last_mode"], "chat")
        bindings = json.loads((Path(self.temp.name) / "state" / "codex_threads.json").read_text())["bindings"]
        self.assertEqual({row["instruction_mode"] for row in bindings}, {"chat", "full_access"})

    def test_legacy_chat_thread_is_not_resumed_for_full_access_and_history_bootstraps_once(self):
        state = Path(self.temp.name) / "state"
        state.mkdir(parents=True)
        now = codex_threads.timestamp()
        (state / "codex_threads.json").write_text(json.dumps({
            "schema": codex_threads.LEGACY_SCHEMA,
            "bindings": [{"conversation_id": self.conversation, "thread_id": "legacy-chat-thread",
                          "workspace": self.logical_workspace, "created_at": now, "updated_at": now,
                          "last_mode": "full_access", "last_model": "fixture-model"}],
        }), encoding="utf-8")
        history = [{"role": "user", "content": "legacy local continuity"}]
        result = self.client.agent_answer(
            "inspect the visible app", "local context", "", lambda _: None,
            conversation=self.conversation, logical_workspace=self.logical_workspace,
            history=history, workspace=self.workspace, on_activity=lambda _: None,
        )
        self.assertEqual(result, "Verified fixture.")
        full = [rpc for rpc in self.transports if rpc.full_access][-1]
        methods = [method for method, _ in full.calls]
        self.assertIn("thread/start", methods)
        self.assertNotIn("thread/resume", methods)
        sent = [params for method, params in full.calls if method == "turn/start"][0]["input"][0]["text"]
        self.assertIn("legacy local continuity", sent)
        bindings = json.loads((state / "codex_threads.json").read_text(encoding="utf-8"))["bindings"]
        self.assertEqual({row["instruction_mode"] for row in bindings},
                         {codex_threads.LEGACY_MODE, "full_access"})

    def test_agent_turn_passes_supported_effort_without_changing_full_access_policy(self):
        self.client.agent_answer("fixture", "instructions", "", lambda _: None, workspace=self.workspace,
                                 conversation=self.conversation, logical_workspace=self.logical_workspace,
                                 history=[], on_activity=lambda _: None, reasoning_effort="high")
        calls = dict(self.transports[-1].calls)
        self.assertEqual(calls["turn/start"]["effort"], "high")
        self.assertEqual(calls["thread/start"]["model"], "fixture-model")
        self.assertEqual(calls["thread/start"]["sandbox"], "danger-full-access")
        self.assertTrue(all(rpc.closed for rpc in self.transports))

    def test_unsupported_effort_never_opens_a_full_access_process(self):
        with self.assertRaisesRegex(codex.CodexConnectionError, "not supported"):
            self.client.agent_answer("fixture", "instructions", "", lambda _: None, workspace=self.workspace,
                                     conversation=self.conversation, logical_workspace=self.logical_workspace,
                                     history=[], on_activity=self.events.append, reasoning_effort="ultra")
        self.assertFalse(any(rpc.full_access for rpc in self.transports))
        self.assertFalse(self.events[-1]["receipt"]["execution_may_have_occurred"])

    def test_wrong_policy_or_loaded_instructions_refuse_before_generation(self):
        def change(rpc):
            rpc.instruction_sources = ["unexpected AGENTS.md"]
        self.transform = change
        with self.assertRaisesRegex(codex.CodexConnectionError, "no turn.*started"):
            self.answer()
        self.assertFalse(any(method == "turn/start" for method, _ in self.transports[-1].calls))
        self.assertEqual(self.events[-1]["receipt"]["status"], "failed")
        self.assertFalse(self.events[-1]["receipt"]["execution_may_have_occurred"])

    def test_unrelated_notifications_and_internal_prompts_never_enter_receipt(self):
        def change(rpc):
            rpc.events.insert(0, {"method": "item/completed", "params": {"threadId": "other", "item": {
                "id": "foreign", "type": "commandExecution", "command": "FOREIGN_PRIVATE"}}})
            rpc.events.insert(0, {"method": "item/completed", "params": {"threadId": "thread", "turnId": "another-turn", "item": {
                "id": "foreign", "type": "commandExecution", "command": "FOREIGN_PRIVATE"}}})
        self.transform = change
        self.answer()
        self.assertNotIn("FOREIGN_PRIVATE", json.dumps(self.events))

    def test_cancel_keeps_partial_activity_and_does_not_retry(self):
        def change(rpc):
            original = rpc.next_event
            def event(timeout):
                result = original(timeout)
                self.client.cancelled.set()
                return result
            rpc.next_event = event
        self.transform = change
        with self.assertRaises(codex.TurnCancelled):
            self.answer()
        receipt = self.events[-1]["receipt"]
        self.assertEqual(receipt["status"], "interrupted")
        self.assertTrue(receipt["execution_may_have_occurred"])
        self.assertEqual(receipt["items"][0]["status"], "unknown")
        calls = self.transports[-1].calls
        self.assertEqual(sum(method == "turn/start" for method, _ in calls), 1)
        self.assertTrue(any(method == "turn/interrupt" for method, _ in calls))

    def test_unsupported_server_request_stops_but_never_claims_rollback(self):
        def change(rpc):
            rpc.events.insert(2, {"method": "proto_mind/tool_refused", "params": {}})
        self.transform = change
        with self.assertRaisesRegex(codex.CodexConnectionError, "declined"):
            self.answer()
        self.assertTrue(self.events[-1]["receipt"]["execution_may_have_occurred"])
        self.assertEqual(self.events[-1]["receipt"]["status"], "failed")

    def test_timeout_has_receipt_and_bounded_stop(self):
        with patch.object(agent, "MAX_AGENT_SECONDS", 0), self.assertRaisesRegex(codex.CodexConnectionError, "foreground limit"):
            self.answer()
        self.assertEqual(self.events[-1]["receipt"]["status"], "failed")
        self.assertIsNone(self.client.rpc)

    def test_preview_bounds_escape_removal_and_action_limit(self):
        run = agent.AgentRun(self.workspace, lambda _: None)
        run.record({"id": "c", "type": "commandExecution", "command": "x" * 10000,
                    "cwd": str(self.workspace), "aggregatedOutput": "\x1b[31m" + "x" * 20000}, True)
        self.assertLess(len(run.items["c"]["command"]), 1700)
        self.assertLess(len(run.items["c"]["output_preview"]), 3100)
        self.assertNotIn("\x1b", run.items["c"]["output_preview"])
        with patch.object(agent, "MAX_AGENT_ITEMS", 1), self.assertRaisesRegex(codex.CodexConnectionError, "activity limit"):
            run.record({"id": "next", "type": "imageView", "path": "/fixture.png"}, True)

    def test_failed_command_remains_failed_even_when_model_completes_turn(self):
        def change(rpc):
            rpc.events[1]["params"]["item"].update(status="failed", exitCode=1)
        self.transform = change
        self.answer()
        receipt = self.events[-1]["receipt"]
        self.assertEqual(receipt["status"], "completed")
        self.assertEqual(receipt["items"][0]["status"], "failed")
        self.assertEqual(receipt["items"][0]["exit_code"], 1)

    def test_lost_turn_start_reply_is_not_reported_as_proof_of_no_execution(self):
        def change(rpc):
            original = rpc.request
            def request(method, params=None, **kwargs):
                if method == "turn/start":
                    raise codex.CodexConnectionError("Lost start response")
                return original(method, params, **kwargs)
            rpc.request = request
        self.transform = change
        with self.assertRaisesRegex(codex.CodexConnectionError, "Lost start"):
            self.answer()
        self.assertTrue(self.events[-1]["receipt"]["execution_may_have_occurred"])
        self.assertEqual(self.events[-1]["receipt"]["items"], [])

    def test_file_change_receipt_is_bounded_and_not_an_executable_payload(self):
        run = agent.AgentRun(self.workspace, lambda _: None)
        run.record({"id": "edit", "type": "fileChange", "status": "completed", "changes": [
            {"path": "fixture.txt", "diff": "x" * 10000, "kind": {"type": "update"}}
            for _ in range(20)]}, True)
        self.assertEqual(run.items["edit"]["change_count"], 20)
        self.assertEqual(len(run.items["edit"]["paths"]), 8)
        self.assertLess(len(run.items["edit"]["diff_preview"]), 3100)
        self.assertTrue(run.receipt["execution_may_have_occurred"])

    def test_unknown_mcp_server_or_tool_is_refused_without_persisting_arguments(self):
        for server, tool in (("other", "click"), ("computer-use", "run_shell")):
            with self.subTest(server=server, tool=tool):
                run = agent.AgentRun(self.workspace, lambda _: None, computer_use_available=True)
                with self.assertRaisesRegex(codex.CodexConnectionError, "Unexpected MCP"):
                    run.record({"id": server + tool, "type": "mcpToolCall", "server": server, "tool": tool,
                                "status": "completed", "arguments": {"text": "PRIVATE"}}, True)
                self.assertNotIn("PRIVATE", json.dumps(run.receipt))

    def test_automation_denial_is_classified_without_retaining_raw_mcp_payload(self):
        run = agent.AgentRun(self.workspace, lambda _: None, computer_use_available=True)
        run.record({"id": "screen", "type": "mcpToolCall", "server": "computer-use",
                    "tool": "get_app_state", "status": "failed", "arguments": {"app": "Safari"},
                    "result": {"content": [{"type": "text", "text":
                        "Computer Use server error -1743: Unknown error"}], "private": "DO-NOT-PERSIST"}}, True)
        row = run.items["screen"]
        self.assertEqual(row["failure_code"], "macos_automation_permission_denied")
        self.assertIn("Automation", row["failure_message"])
        self.assertIn("System Settings", row["recovery"])
        self.assertNotIn("Unknown error", json.dumps(run.receipt))
        self.assertNotIn("DO-NOT-PERSIST", json.dumps(run.receipt))


class ComputerUseDiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="native-computer-use-")
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name).resolve()
        self.service, self.client_app, self.command = computer_use._paths(self.home)
        self.command.parent.mkdir(parents=True)
        self.command.write_bytes(b"fixture")
        self.command.chmod(0o700)
        (self.service / "Contents" / "Info.plist").write_bytes(plistlib.dumps({
            "CFBundleIdentifier": computer_use.SERVICE_BUNDLE_ID,
            "CFBundleShortVersionString": "fixture-version",
        }))
        (self.client_app / "Contents" / "Info.plist").write_bytes(plistlib.dumps({
            "CFBundleIdentifier": computer_use.CLIENT_BUNDLE_ID,
        }))

    @staticmethod
    def signed_runner(args, **_kwargs):
        path = args[-1]
        bundle = computer_use.CLIENT_BUNDLE_ID if "SkyComputerUseClient" in path else computer_use.SERVICE_BUNDLE_ID
        output = (f"Identifier={bundle}\nTeamIdentifier={computer_use.OPENAI_TEAM_ID}\n"
                  "Authority=Developer ID Application: OpenAI OpCo, LLC (2DC432GLL2)\n")
        return subprocess.CompletedProcess(args, 0, stdout="", stderr=output)

    def test_discovery_requires_canonical_signed_openai_bundles(self):
        found = computer_use.discover_computer_use(home=self.home, runner=self.signed_runner, platform="darwin")
        self.assertTrue(found["available"])
        self.assertEqual(found["version"], "fixture-version")
        self.assertEqual(found["command"], str(self.command))
        public = computer_use.public_computer_use_capability(found)
        self.assertNotIn("command", public)
        self.assertFalse(public["persistent_grant"])
        self.assertFalse(public["stores_screenshots"])

    def test_missing_tampered_or_untrusted_service_fails_closed(self):
        self.command.unlink()
        self.assertFalse(computer_use.discover_computer_use(home=self.home, runner=self.signed_runner,
                                                            platform="darwin")["available"])
        self.command.write_bytes(b"fixture")
        self.command.chmod(0o700)
        untrusted = lambda args, **kwargs: subprocess.CompletedProcess(args, 0, stdout="", stderr="TeamIdentifier=OTHER")
        result = computer_use.discover_computer_use(home=self.home, runner=untrusted, platform="darwin")
        self.assertFalse(result["available"])
        self.assertNotIn("command", result)

    def test_status_requires_one_connected_server_and_bounded_tool_set(self):
        status = {"data": [{"name": "computer-use", "runtimeStatus": "connected",
                            "tools": {name: {} for name in computer_use.COMPUTER_USE_TOOLS}}], "nextCursor": None}
        self.assertEqual(computer_use.validate_computer_use_status(status), set(computer_use.COMPUTER_USE_TOOLS))
        for changed in (
            {"data": [], "nextCursor": None},
            {"data": [{"name": "computer-use", "runtimeStatus": "failed", "tools": {}}], "nextCursor": None},
            {"data": [{"name": "computer-use", "runtimeStatus": "connected",
                       "tools": {**{name: {} for name in computer_use.COMPUTER_USE_TOOLS}, "shell": {}}}], "nextCursor": None},
        ):
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                computer_use.validate_computer_use_status(changed)


if __name__ == "__main__":
    unittest.main()
