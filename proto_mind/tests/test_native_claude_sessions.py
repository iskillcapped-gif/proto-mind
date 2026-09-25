import asyncio
import json
from pathlib import Path
import tempfile
import unittest
from uuid import uuid4

from proto_mind.native_claude_sessions import ClaudeSessionPlan, bootstrap_history, invalidate_login, PARTIAL_HISTORY, UNRESUMABLE
from proto_mind.native_claude_protocol import WorkspaceReplies, WorkspaceReplyError
from proto_mind.private_state_gate import GENERATION_FILE, RESTORE_MARKER


class SessionTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.state = Path(temporary.name).resolve()
        self.conversation = str(uuid4())
        self.values = dict(account={"email": "one@example.invalid", "authMethod": "oauth"},
                           workspace={"path": "/fixture", "device": 1, "inode": 2},
                           full_access=True, tools=True, history=[])

    def plan(self, **changes):
        return ClaudeSessionPlan(self.state, self.conversation, **{**self.values, **changes})

    def transcript(self, session_id):
        path = self.state / "claude-profile" / "projects" / "-fixture" / (session_id + ".jsonl")
        path.parent.mkdir(parents=True, exist_ok=True); path.write_text("{}\n")
        return path

    def completed(self):
        plan = self.plan()
        with plan.lease(): plan.complete(plan.session_id, "Saved answer")
        self.transcript(plan.session_id)
        self.values["history"] = [{"role": "user", "content": "Original"},
                                  {"role": "assistant", "content": "Saved answer"}]
        return plan

    def test_planning_is_read_only_and_another_instance_resumes_exact_session(self):
        self.plan(); self.assertEqual(list(self.state.iterdir()), [])
        original = self.completed()
        self.assertFalse(self.plan().interrupted)
        continued = self.plan()
        self.assertTrue(continued.resumed)
        self.assertEqual(continued.session_id, original.session_id)
        self.assertEqual(continued.history, [])
        self.conversation = str(uuid4())
        self.assertFalse(self.plan().resumed)

    def test_account_project_permissions_and_local_history_must_match(self):
        original = self.completed()
        for changes in [dict(account={"email":"two@example.invalid"}), dict(account={}),
                        dict(workspace={"path":"/other", "device":1, "inode":3}),
                        dict(full_access=False), dict(tools=False), dict(history=[]),
                        dict(history=[{"role":"assistant", "content":"Changed answer"}])]:
            with self.subTest(changes=changes):
                candidate = self.plan(**changes)
                self.assertFalse(candidate.resumed)
                self.assertNotEqual(candidate.session_id, original.session_id)

    def test_login_and_restore_invalidate_continuation(self):
        self.completed()
        invalidate_login(self.state)
        self.assertFalse(self.plan().resumed)
        self.completed()
        (self.state / GENERATION_FILE).write_text("new-generation")
        self.assertFalse(self.plan().resumed)
        (self.state / RESTORE_MARKER).write_text("{}")
        with self.assertRaises(ValueError): self.plan()

    def test_interrupted_turn_continues_only_from_the_same_local_position(self):
        original = self.completed()
        attempted = self.plan()
        with attempted.lease(): pass  # Stop, usage limit or error: never a confirmed answer
        continued = self.plan()
        self.assertTrue(continued.resumed and continued.interrupted)
        self.assertEqual(continued.session_id, original.session_id)
        self.assertEqual(continued.history, [])
        # Another provider answered meanwhile: the saved session no longer matches.
        moved = self.plan(history=self.values["history"] + [{"role": "user", "content": "Other"},
                                                            {"role": "assistant", "content": "Codex answer"}])
        self.assertFalse(moved.resumed or moved.interrupted)

    def test_interrupted_first_turn_and_unidentified_position(self):
        first = self.plan()
        with first.lease(): pass
        self.transcript(first.session_id)
        self.assertTrue(self.plan().interrupted)
        odd = self.plan(history=[{"role": "user", "content": "unanswered"}])
        self.assertFalse(odd.resumed)
        with odd.lease(): pass
        self.assertEqual(json.loads(odd.path.read_text())["answer_hash"], UNRESUMABLE)

    def test_missing_transcript_or_abandoned_session_starts_fresh(self):
        original = self.completed()
        self.transcript(original.session_id).unlink()
        self.assertFalse(self.plan().resumed)
        self.transcript(original.session_id)
        damaged = self.plan()
        self.assertTrue(damaged.resumed)
        with damaged.lease(): damaged.abandon()
        self.assertFalse(self.plan().resumed)
        damaged.abandon()  # Outside a lease it never writes.

    def test_changed_session_contract_starts_fresh(self):
        self.completed()
        self.assertTrue(self.plan(contract=1).resumed)
        self.assertFalse(self.plan(contract="new-system-text").resumed)

    def test_lease_excludes_other_writers_and_revalidates_plan(self):
        first, second = self.plan(), self.plan()
        with first.lease():
            with self.assertRaisesRegex(ValueError, "already running"):
                with second.lease(): pass
            with self.assertRaises(ValueError): first.complete(str(uuid4()), "wrong session")
            first.complete(first.session_id, "Saved answer")
        with self.assertRaisesRegex(ValueError, "changed before dispatch"):
            with second.lease(): pass
        self.assertTrue((first.directory / (self.conversation + ".lock")).exists())

    def test_account_or_restore_change_during_turn_cannot_publish_binding(self):
        plan = self.plan()
        with plan.lease():
            invalidate_login(self.state)
            with self.assertRaises(ValueError): plan.complete(plan.session_id, "Saved answer")
        self.assertFalse(self.plan().resumed)

    def test_corrupt_record_and_symlink_are_preserved(self):
        plan = self.completed()
        plan.path.write_text("not json")
        with self.assertRaises(ValueError): self.plan()
        self.assertEqual(plan.path.read_text(), "not json")
        plan.path.unlink()
        target = self.state / "external"; target.write_text("original")
        plan.path.symlink_to(target)
        with self.assertRaises((ValueError, OSError)): self.plan()
        self.assertEqual(target.read_text(), "original")

    def test_large_bootstrap_keeps_long_messages_and_marks_only_actual_omission(self):
        rows = [{"role":"user", "content":str(i) + ":" + "x" * 4000} for i in range(40)]
        self.assertEqual(bootstrap_history(rows), rows)
        rows = [{"role":"assistant", "content":str(i) + ":" + "x" * 40000} for i in range(10)]
        result = bootstrap_history(rows)
        self.assertTrue(result[0]["content"].startswith(PARTIAL_HISTORY))
        self.assertEqual(result[-1], rows[-1])
        self.assertLessEqual(sum(len(row["content"]) for row in result), 300000 + len(PARTIAL_HISTORY))


class ReplyTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.requests = asyncio.Queue()
        self.replies = WorkspaceReplies(self.requests.put_nowait, timeout=.03)
        self.reader = asyncio.StreamReader()
        self.reading = asyncio.create_task(self.replies.read(self.reader))
        self.addAsyncCleanup(self.cleanup)

    async def cleanup(self):
        self.reading.cancel()
        await asyncio.gather(self.reading, return_exceptions=True)
        self.replies.close()

    def reply(self, request):
        self.reader.feed_data(json.dumps({"id":request["id"], "success":True, "result":{"ok":True}}).encode() + b"\n")

    async def test_late_reply_does_not_poison_next_call(self):
        first = asyncio.create_task(self.replies.call("first", {}))
        timed_out = await self.requests.get()
        self.assertFalse((await first)["success"])
        second = asyncio.create_task(self.replies.call("second", {}))
        current = await self.requests.get()
        self.reply(timed_out); self.reply(current)
        self.assertTrue((await second)["success"])
        self.assertFalse(self.replies.failed)

    async def test_cancelled_reply_is_ignored_without_cancelling_other_calls(self):
        first = asyncio.create_task(self.replies.call("first", {}))
        cancelled = await self.requests.get(); first.cancel()
        await asyncio.gather(first, return_exceptions=True)
        second = asyncio.create_task(self.replies.call("second", {}))
        current = await self.requests.get()
        self.reply(cancelled); self.reply(current)
        self.assertTrue((await second)["success"])

    async def test_unknown_reply_or_eof_closes_pending_calls(self):
        pending = asyncio.create_task(self.replies.call("first", {}))
        await self.requests.get()
        self.reply({"id":str(uuid4())})
        with self.assertRaises(WorkspaceReplyError): await pending
        with self.assertRaises(WorkspaceReplyError): await self.replies.call("later", {})

    async def test_eof_is_not_success(self):
        pending = asyncio.create_task(self.replies.call("first", {}))
        await self.requests.get(); self.reader.feed_eof()
        with self.assertRaises(WorkspaceReplyError): await pending
