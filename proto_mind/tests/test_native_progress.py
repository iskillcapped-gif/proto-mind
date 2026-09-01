"""Public work timeline contracts. No real model, tools, or personal stores."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

from proto_mind import native_codex as codex
from proto_mind import native_bridge as bridge
from proto_mind import native_computer_use as computer_use_module
from proto_mind.config import ProtoMindConfig
from proto_mind.native_progress import MAX_WORK_ITEMS, PublicMessages, WorkLog, display_text
from proto_mind.native_work_sessions import workspace_identity
from proto_mind.tests.test_native import FakeRPC


def event(method, **params):
    return {"method": method, "params": {"threadId": "thread", "turnId": "turn", **params}}


def message(method, item_id, text="", phase=None):
    return event(method, item={"id": item_id, "type": "agentMessage", "text": text, "phase": phase})


def public_events():
    return [
        message("item/started", "comment", phase="commentary"),
        event("item/agentMessage/delta", itemId="comment", delta="Checking the fixture."),
        message("item/completed", "comment", "Checking the fixture.", "commentary"),
        event("item/started", item={"id": "reason", "type": "reasoning", "content": ["PRIVATE_RAW"], "summary": ["PRIVATE_SUMMARY"]}),
        event("item/reasoning/textDelta", delta="PRIVATE_RAW"),
        event("item/reasoning/summaryTextDelta", delta="PRIVATE_SUMMARY"),
        event("internal/hook", prompt="PRIVATE_HOOK"),
        message("item/started", "answer", phase="final_answer"),
        event("item/agentMessage/delta", itemId="answer", delta="Fixture complete."),
        message("item/completed", "answer", "Fixture complete.", "final_answer"),
        event("turn/completed", turn={"id": "turn", "status": "completed"}),
    ]


class PublicWorkLogTests(unittest.TestCase):
    def setUp(self):
        self.events, self.deltas = [], []
        self.log = WorkLog(self.events.append, "chat")
        self.messages = PublicMessages(self.deltas.append, self.log, limit=200_000, error_type=codex.CodexConnectionError)

    def feed(self, events):
        for item in events:
            self.messages.observe(item["method"], item["params"])

    def test_commentary_stream_is_separate_from_exact_final_answer(self):
        self.feed(public_events())
        self.log.finish("completed")
        self.assertEqual("".join(self.deltas), "Fixture complete.")
        self.assertEqual(self.messages.answer(), "Fixture complete.")
        self.assertEqual(self.events[-1]["log"]["entries"][0]["text"], "Checking the fixture.")
        self.assertTrue(self.events[-1]["log"]["public_only"])
        versions = [item["log"]["state_version"] for item in self.events]
        self.assertEqual(versions, sorted(set(versions)))
        self.assertGreater(versions[0], 0)

    def test_late_commentary_phase_is_not_temporarily_streamed_as_final(self):
        self.feed([message("item/started", "late"), event("item/agentMessage/delta", itemId="late", delta="A progress update")])
        self.assertEqual(self.deltas, [])
        self.feed([message("item/completed", "late", "A progress update", "commentary")])
        self.assertEqual(self.deltas, [])
        self.assertEqual(self.messages.answer(), "")
        self.assertEqual(self.events[-1]["log"]["entries"][0]["text"], "A progress update")

    def test_provider_without_phases_still_returns_legacy_answer_once(self):
        self.feed([event("item/agentMessage/delta", itemId="legacy", delta="Legacy answer")])
        self.assertEqual(self.deltas, [])
        self.feed([message("item/completed", "legacy", "Legacy answer")])
        self.assertEqual(self.deltas, ["Legacy answer"])
        self.assertEqual(self.messages.answer(), "Legacy answer")

    def test_reasoning_summaries_raw_reasoning_and_hooks_are_not_forwarded(self):
        self.feed(public_events())
        self.log.finish("completed")
        self.assertNotIn("PRIVATE_", json.dumps([self.events, self.deltas, self.messages.answer()]))
        self.assertEqual([e["kind"] for e in self.events[-1]["log"]["entries"]], ["commentary"])

    def test_public_plan_and_compaction_use_only_allowed_fields(self):
        self.feed([event("turn/plan/updated", explanation="Visible plan", secret="PRIVATE_PLAN", plan=[
            {"step": "Inspect fixture", "status": "inProgress", "private": "PRIVATE_PLAN"},
            {"step": "Invalid", "status": "execute-now"},
        ]), event("item/completed", item={"type": "contextCompaction", "id": "compact", "content": "PRIVATE_CONTEXT"})])
        entries = self.events[-1]["log"]["entries"]
        self.assertEqual([e["kind"] for e in entries], ["plan", "context_compaction"])
        self.assertEqual(entries[0]["steps"], [{"step": "Inspect fixture", "status": "inProgress"}])
        self.assertNotIn("PRIVATE_", json.dumps(self.events))

    def test_display_bounds_do_not_expand_tool_outputs_or_create_extra_entries(self):
        self.log.tool({"id": "cmd", "kind": "commandExecution", "status": "completed", "output": "PRIVATE_HUGE_TOOL_OUTPUT"})
        for index in range(MAX_WORK_ITEMS + 5):
            self.log.commentary(str(index), "x" * 6000, True)
        self.log.finish("completed")
        result = self.events[-1]["log"]
        self.assertEqual(len(result["entries"]), MAX_WORK_ITEMS)
        self.assertTrue(result["truncated"])
        self.assertLess(len(result["entries"][1]["text"]), 4050)
        self.assertNotIn("PRIVATE_HUGE_TOOL_OUTPUT", json.dumps(result))

    def test_web_search_is_visible_as_a_bounded_tool_reference_only(self):
        self.log.tool({"id": "web", "kind": "webSearch", "status": "completed",
                       "query": "public query", "results": "PRIVATE_RESULTS"})
        result = self.events[-1]["log"]
        self.assertEqual(result["entries"], [{"id": "tool:web", "kind": "tool", "tool_id": "web",
                                               "tool_kind": "webSearch", "status": "completed"}])
        self.assertNotIn("PRIVATE_RESULTS", json.dumps(result))

    def test_computer_use_is_visible_without_screen_or_input_payloads(self):
        self.log.tool({"id": "screen", "kind": "computerUse", "status": "completed",
                       "tool": "type_text", "app": "Calculator", "arguments": "PRIVATE_INPUT",
                       "result": "PRIVATE_SCREENSHOT"})
        result = self.events[-1]["log"]
        self.assertEqual(result["entries"], [{"id": "tool:screen", "kind": "tool", "tool_id": "screen",
                                               "tool_kind": "computerUse", "status": "completed"}])
        self.assertNotIn("PRIVATE", json.dumps(result))

    def test_progress_snapshots_are_immutable_and_finish_is_timed(self):
        self.log.commentary("c", "First", False)
        before = deepcopy(self.events)
        self.log.commentary("c", "Completed", True)
        self.log.finish("completed")
        self.assertEqual(self.events[:len(before)], before)
        result = self.events[-1]["log"]
        self.assertGreaterEqual(result["elapsed_ms"], 0)
        self.assertIn("finished_at", result)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(
            [item["log"]["state_version"] for item in self.events],
            list(range(1, len(self.events) + 1)),
        )

    def test_interruption_does_not_claim_unfinished_commentary_completed(self):
        self.log.commentary("c", "Inspecting", False)
        self.log.finish("interrupted")
        result = self.events[-1]["log"]
        self.assertEqual(result["status"], "interrupted")
        self.assertEqual(result["entries"][0]["status"], "unknown")

    def test_invalid_phase_and_oversized_stream_fail_without_display(self):
        for item in [message("item/completed", "bad", "PRIVATE", "analysis"),
                     event("item/agentMessage/delta", itemId="large", delta="x" * 200_001)]:
            with self.subTest(item=item["method"]), self.assertRaises(codex.CodexConnectionError):
                self.feed([item])
        self.assertEqual(self.deltas, [])
        self.assertNotIn("PRIVATE", json.dumps(self.events))

    def test_display_strips_terminal_controls_not_newlines(self):
        self.assertEqual(display_text("\x1b[31mhello\x1b[0m\x00\nworld", 100), "hello\nworld")


class NativeProgressAdapterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="native-progress-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.events, self.deltas, self.transports = [], [], []
        self.stream = public_events()

        def factory(executable, home, workspace, *, full_access=False, computer_use=None):
            rpc = FakeRPC(executable, home, workspace)
            rpc.events = deepcopy(self.stream)
            if full_access:
                rpc.sandbox = {"type": "dangerFullAccess"}
                rpc.computer_use_tools = set(computer_use_module.COMPUTER_USE_TOOLS) if computer_use else set()
            self.transports.append(rpc)
            return rpc

        self.client = codex.CodexSubscription(self.root / "state", transport_factory=factory)
        self.conversation = str(uuid4())
        self.logical_workspace = workspace_identity(self.root)
        self.addCleanup(self.client.close)
        executable = patch.object(codex.shutil, "which", return_value="/not-executed/codex")
        executable.start()
        self.addCleanup(executable.stop)

    def answer(self):
        return self.client.answer("fixture input", "fixture instructions", "", self.deltas.append,
                                  conversation=self.conversation, logical_workspace=self.logical_workspace,
                                  history=[], on_progress=self.events.append)

    def test_chat_progress_is_scoped_and_still_no_tools(self):
        self.stream.insert(0, message("item/completed", "foreign", "FOREIGN_THREAD", "commentary"))
        self.stream[0]["params"]["threadId"] = "another-thread"
        self.stream.insert(0, message("item/completed", "foreign-turn", "FOREIGN_TURN", "commentary"))
        self.stream[0]["params"]["turnId"] = "another-turn"
        self.assertEqual(self.answer(), "Fixture complete.")
        self.assertNotIn("FOREIGN_", json.dumps(self.events))
        self.assertEqual(self.events[-1]["log"]["access_mode"], "chat")
        self.assertEqual(self.events[-1]["log"]["status"], "completed")
        calls = self.transports[0].calls
        self.assertEqual(sum(method == "turn/start" for method, _ in calls), 1)
        self.assertEqual(dict(calls)["thread/start"]["sandbox"], "read-only")

    def test_failure_preserves_public_progress_without_claiming_success(self):
        self.stream = self.stream[:3] + [event("turn/completed", turn={"id": "turn", "status": "failed"})]
        with self.assertRaises(codex.CodexConnectionError):
            self.answer()
        self.assertEqual(self.events[-1]["log"]["status"], "failed")
        self.assertEqual(self.events[-1]["log"]["entries"][0]["text"], "Checking the fixture.")
        self.assertEqual(self.deltas, [])

    def test_cancel_before_cloud_has_honest_empty_work_log(self):
        self.client.interrupt()
        with self.assertRaises(codex.TurnCancelled):
            self.answer()
        self.assertEqual(self.events[-1]["log"]["status"], "interrupted")
        self.assertEqual(self.events[-1]["log"]["entries"], [])
        self.assertEqual(self.transports, [])

    def test_agent_merges_public_commentary_and_projected_tool_references_in_order(self):
        self.stream.insert(3, event("item/completed", item={"id": "command", "type": "commandExecution",
            "command": "fixture only", "cwd": str(self.root), "status": "completed", "exitCode": 0,
            "aggregatedOutput": "visible tool output", "internal": "PRIVATE_TOOL"}))
        activity = []
        answer = self.client.agent_answer("fixture", "fixture", "", self.deltas.append,
            conversation=self.conversation, logical_workspace=self.logical_workspace, history=[],
            workspace=self.root, on_activity=activity.append, on_progress=self.events.append)
        self.assertEqual(answer, "Fixture complete.")
        result = self.events[-1]["log"]
        self.assertEqual([e["kind"] for e in result["entries"]], ["commentary", "tool"])
        self.assertEqual(result["entries"][1]["tool_id"], "command")
        self.assertEqual(activity[-1]["receipt"]["items"][0]["output_preview"], "visible tool output")
        self.assertNotIn("PRIVATE_", json.dumps([self.events, activity, self.deltas]))
        self.assertEqual(self.deltas, ["Fixture complete."])
        self.assertIsNone(self.client.rpc)

    def test_bridge_returns_work_log_but_core_logs_only_original_input_once(self):
        backend = bridge.NativeBackend(self.root / "project", self.root / "native",
                                       subscription_factory=lambda _: self.client)
        self.addCleanup(backend.close)
        config = ProtoMindConfig(data_dir=backend.root / "proto_mind/data")
        with patch.object(ProtoMindConfig, "from_env", return_value=config):
            result = backend.process({"text": "Hello", "provider": "codex", "cloud_consent": True,
                                      "conversation_id": str(uuid4())}, self.events.append, "request")
        self.assertEqual(result["work_log"]["status"], "completed")
        self.assertEqual(result["cognitive_turn"]["response"], "Fixture complete.")
        self.assertTrue(all(e["request_id"] == "request" for e in self.events))
        log = backend.root / "logs/session_operator_log.jsonl"
        rows = [json.loads(line) for line in log.read_text().splitlines()]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["user_input"], "Hello")
        for path in (backend.root / "proto_mind/data").rglob("*"):
            if path.is_file():
                self.assertNotIn(b"Checking the fixture", path.read_bytes())
        self.assertNotIn("Checking the fixture", log.read_text())

    def test_bridge_operator_report_does_not_start_work_or_model(self):
        backend = bridge.NativeBackend(self.root / "project", self.root / "native",
                                       subscription_factory=lambda _: self.client)
        self.addCleanup(backend.close)
        result = backend.process({"text": "/commands status", "provider": "codex", "cloud_consent": False,
                                  "conversation_id": str(uuid4())}, self.events.append, "request")
        self.assertTrue(result["operator"])
        self.assertFalse(result.get("work_log"))
        self.assertEqual(self.events, [])
        self.assertEqual(self.transports, [])
        self.assertFalse(backend.root.exists())


if __name__ == "__main__":
    unittest.main()
