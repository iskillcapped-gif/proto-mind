"""Read-only Native-to-Spine parity over synthetic detached records."""
from copy import deepcopy
import hashlib
from unittest import TestCase
from unittest.mock import patch
from uuid import uuid4

from proto_mind.native_memory_suggestions import candidate_id
from proto_mind.native_progress import display_text
from proto_mind.native_session_spine import (
    MAX_ANSWER_CHARS,
    NativeSessionProjectionError,
    materialize_message_text,
    project_native_turn,
)


DEFAULT_ASSISTANT = object()


class NativeSessionSpineTests(TestCase):
    def setUp(self):
        self.conversation = str(uuid4())
        self.run_id = str(uuid4())
        self.user_id = str(uuid4())
        self.assistant_id = str(uuid4())
        self.input = "Inspect the synthetic project safely."
        self.answer = "The synthetic inspection completed; task success was not independently verified."

    def user(self, text=None, **changes):
        value = {"id": self.user_id, "role": "user", "text": text or self.input, "isError": False,
                 "operatorInput": False, "evidence": {"private": "NOT_PROJECTED"}}
        value.update(changes)
        return value

    def assistant(self, text=None, **changes):
        value = {"id": self.assistant_id, "role": "assistant", "text": text or self.answer,
                 "raw": text or self.answer, "isError": False, "notices": ["NOT_PROJECTED"]}
        value.update(changes)
        return value

    def work_session(self, *, input_text=None, answer=None, status="completed", display_status="completed", **changes):
        input_text = input_text or self.input
        answer = self.answer if answer is None and status == "completed" else answer
        value = {
            "schema": "proto_mind.native_work_session.v1",
            "id": self.run_id,
            "conversation_id": self.conversation,
            "project_root": "/synthetic/project",
            "workspace": {"path": "/synthetic/project", "device": 1, "inode": 2},
            "created_at": "2026-09-03T10:00:00.000000Z",
            "updated_at": "2026-09-03T10:01:00.000000Z",
            "status": status,
            "provider": "codex",
            "requested_model": "gpt-5.6-sol",
            "requested_effort": "high",
            "access_mode": "chat",
            "input_preview": display_text(input_text, 800),
            "input_chars": len(input_text),
            "input_sha256": hashlib.sha256(input_text.encode()).hexdigest(),
            "sources": [],
            "parent_run_id": None,
            "tools": [],
            "work_log": {},
            "network_access_performed": False,
            "computer_use_performed": False,
            "screen_access_performed": False,
            "verification": "not_assessed",
            "acceptance": "not_recorded",
            "display_status": display_status,
            "fingerprint": "a" * 64,
            "automatic_resume": False,
        }
        if status == "completed":
            value.update(finished_at="2026-09-03T10:01:00.000000Z", answer_preview=display_text(answer, 1600))
        if display_status == "unknown":
            value["dispatched_at"] = "2026-09-03T10:00:01.000000Z"
            value["execution_may_have_occurred"] = True
        value.update(changes)
        return value

    def project(self, *, user=None, assistant=DEFAULT_ASSISTANT, run=None):
        return project_native_turn(
            conversation_id=self.conversation,
            user_message=user or self.user(),
            assistant_message=self.assistant() if assistant is DEFAULT_ASSISTANT else assistant,
            work_session=run or self.work_session(),
        )

    def test_completed_turn_preserves_exact_input_and_answer(self):
        result = self.project()
        self.assertEqual(materialize_message_text(result.events, result.user_message_seq), self.input)
        self.assertEqual(materialize_message_text(result.events, result.assistant_message_seq), self.answer)
        self.assertEqual(result.display_status, "completed")
        self.assertEqual([result.events[index].event_type for index in result.surface.nodes],
                         ["user/message", "assistant/message"])
        self.assertTrue(result.to_dict()["read_only"])
        self.assertFalse(result.to_dict()["execute"])

    def test_long_unicode_answer_is_losslessly_chunked_beyond_one_event_limit(self):
        answer = "💙" * 70_000
        result = self.project(assistant=self.assistant(answer), run=self.work_session(answer=answer))
        self.assertEqual(materialize_message_text(result.events, result.assistant_message_seq), answer)
        self.assertGreater(sum(event.event_type == "assistant/chunk" for event in result.events), 1)

    def test_distinct_display_and_raw_streams_are_both_preserved(self):
        displayed = "Rendered cognitive answer"
        raw = "Raw provider answer"
        result = self.project(assistant=self.assistant(displayed, raw=raw), run=self.work_session(answer=raw))
        self.assertEqual(materialize_message_text(result.events, result.assistant_message_seq), displayed)
        self.assertEqual(materialize_message_text(result.events, result.assistant_message_seq, stream="raw"), raw)
        self.assertNotEqual(result.displayed_answer_sha256, result.raw_answer_sha256)

    def test_public_tool_evidence_is_preserved_but_marked_non_replayable(self):
        tools = [
            {"id": "cmd", "kind": "commandExecution", "status": "completed", "command": "python -m unittest",
             "cwd": "/synthetic/project", "output_preview": "OK", "exit_code": 0},
            {"id": "web", "kind": "webSearch", "status": "completed", "query": "official docs",
             "action_type": "openPage", "url": "https://example.invalid/docs"},
        ]
        result = self.project(run=self.work_session(tools=tools, network_access_performed=True))
        self.assertEqual(len(result.tool_event_seqs), 2)
        for sequence, expected in zip(result.tool_event_seqs, tools):
            data = result.events[sequence].data
            self.assertEqual(data["tool"], expected)
            self.assertTrue(data["evidence_only"])
            self.assertFalse(data["replayable"])

    def test_private_or_unknown_tool_fields_fail_closed(self):
        tool = {"id": "cmd", "kind": "commandExecution", "status": "completed", "command": "inspect",
                "token": "PRIVATE"}
        with self.assertRaisesRegex(NativeSessionProjectionError, "private"):
            self.project(run=self.work_session(tools=[tool]))

    def test_work_log_is_validated_and_represented_by_stable_hash(self):
        log = {"schema": "proto_mind.native_work_log.v1", "id": "log", "access_mode": "chat",
               "started_at": "2026-09-03T10:00:00Z", "finished_at": "2026-09-03T10:01:00Z",
               "status": "completed", "stage": "answering", "public_only": True, "truncated": False,
               "state_version": 3, "entries": [{"id": "public", "kind": "commentary", "text": "Checked", "status": "completed"}]}
        result = self.project(run=self.work_session(work_log=log))
        self.assertEqual(result.work_log_sha256, result.to_dict()["work_log_sha256"])
        self.assertNotIn("Checked", str(result.to_dict()))

    def test_memory_suggestion_lineage_binds_message_run_and_exact_quote(self):
        text = "Я предпочитаю короткие ответы."
        quote_hash = hashlib.sha256(text.encode()).hexdigest()
        item_id = candidate_id(self.run_id, quote_hash, "preference", 0, len(text), quote_hash)
        report = {
            "schema": "proto_mind.native_memory_suggestions.v1",
            "algorithm": "explicit_operator_statements_v1",
            "source": {"conversation_id": self.conversation, "run_id": self.run_id, "fingerprint": "a" * 64,
                       "input_sha256": quote_hash, "input_chars": len(text),
                       "workspace": {"path": "/synthetic/project", "device": 1, "inode": 2}},
            "state": "suggested", "reason": "explicit_operator_statement", "omitted_count": 0,
            "candidates": [{"id": item_id, "kind": "preference", "start": 0, "end": len(text),
                            "content_sha256": quote_hash}],
            "read_only": True, "automatic_save": False, "model_call_performed": False, "permission_granted": False,
        }
        result = self.project(
            user=self.user(text),
            assistant=self.assistant(memorySuggestions=report, memorySuggestionSourceID=self.user_id),
            run=self.work_session(input_text=text),
        )
        self.assertEqual(result.memory_candidate_ids, (item_id,))
        assistant_event = result.events[result.assistant_message_seq].data
        self.assertEqual(assistant_event["memory_suggestions"]["source_message_id"], self.user_id)
        self.assertFalse(assistant_event["memory_suggestions"]["automatic_save"])

    def test_memory_suggestion_lineage_mismatch_is_refused(self):
        text = "Я предпочитаю короткие ответы."
        quote_hash = hashlib.sha256(text.encode()).hexdigest()
        item_id = candidate_id(self.run_id, quote_hash, "preference", 0, len(text), quote_hash)
        base = {
            "schema": "proto_mind.native_memory_suggestions.v1", "algorithm": "explicit_operator_statements_v1",
            "source": {"conversation_id": self.conversation, "run_id": self.run_id, "fingerprint": "a" * 64,
                       "input_sha256": quote_hash, "input_chars": len(text),
                       "workspace": {"path": "/synthetic/project", "device": 1, "inode": 2}},
            "state": "suggested", "reason": "explicit_operator_statement", "omitted_count": 0,
            "candidates": [{"id": item_id, "kind": "preference", "start": 0, "end": len(text), "content_sha256": quote_hash}],
            "read_only": True, "automatic_save": False, "model_call_performed": False, "permission_granted": False,
        }
        cases = [
            (base, str(uuid4())),
            ({**base, "source": {**base["source"], "run_id": str(uuid4())}}, self.user_id),
            ({**base, "source": {**base["source"], "fingerprint": "b" * 64}}, self.user_id),
            ({**base, "permission_granted": True}, self.user_id),
        ]
        for report, source_id in cases:
            with self.subTest(report=report, source_id=source_id), self.assertRaises(NativeSessionProjectionError):
                self.project(user=self.user(text), assistant=self.assistant(
                    memorySuggestions=report, memorySuggestionSourceID=source_id), run=self.work_session(input_text=text))

    def test_input_hash_length_and_preview_drift_fail_closed(self):
        for change in ({"input_sha256": "b" * 64}, {"input_chars": 1}, {"input_preview": "different"}):
            with self.subTest(change=change), self.assertRaisesRegex(NativeSessionProjectionError, "operator input"):
                self.project(run=self.work_session(**change))

    def test_answer_preview_drift_fails_closed(self):
        with self.assertRaisesRegex(NativeSessionProjectionError, "answer"):
            self.project(run=self.work_session(answer_preview="different"))

    def test_unknown_run_preserves_uncertainty_without_an_assistant_answer(self):
        result = self.project(assistant=None, run=self.work_session(status="dispatching", display_status="unknown"))
        self.assertIsNone(result.assistant_message_seq)
        self.assertEqual(result.display_status, "unknown")
        self.assertTrue(result.warnings)
        self.assertIn("session/error", [event.event_type for event in result.events])
        self.assertEqual([result.events[index].event_type for index in result.surface.nodes], ["user/message"])

    def test_not_started_run_never_invents_dispatch_or_output(self):
        result = self.project(assistant=None, run=self.work_session(status="prepared", display_status="not_started"))
        self.assertEqual(result.display_status, "not_started")
        self.assertIsNone(result.to_dict()["answer"])
        self.assertFalse(result.events[-1].data["execution_may_have_occurred"])

    def test_incomplete_run_rejects_an_assistant_message(self):
        with self.assertRaisesRegex(NativeSessionProjectionError, "cannot acquire"):
            self.project(run=self.work_session(status="dispatching", display_status="unknown"))

    def test_live_run_views_are_not_stable_projection_sources(self):
        for status, display in (("prepared", "preparing"), ("dispatching", "running")):
            with self.subTest(display=display), self.assertRaisesRegex(NativeSessionProjectionError, "stable"):
                self.project(assistant=None, run=self.work_session(status=status, display_status=display))

    def test_projection_is_deterministic_and_does_not_mutate_sources(self):
        user, assistant, run = self.user(), self.assistant(), self.work_session()
        before = deepcopy((user, assistant, run))
        first = project_native_turn(conversation_id=self.conversation, user_message=user,
                                    assistant_message=assistant, work_session=run)
        second = project_native_turn(conversation_id=self.conversation, user_message=user,
                                     assistant_message=assistant, work_session=run)
        self.assertEqual(first, second)
        self.assertEqual((user, assistant, run), before)

    def test_projection_performs_no_file_access(self):
        with patch("builtins.open", side_effect=AssertionError("file access")):
            result = self.project()
        self.assertTrue(result.to_dict()["no_file_access"])
        self.assertTrue(result.to_dict()["no_write"])

    def test_operator_error_and_slash_messages_are_refused(self):
        for user in (self.user(operatorInput=True), self.user(isError=True), self.user("/data doctor")):
            with self.subTest(user=user), self.assertRaises(NativeSessionProjectionError):
                self.project(user=user, run=self.work_session(input_text=user["text"]))

    def test_answer_limit_is_enforced_before_projection(self):
        answer = "x" * (MAX_ANSWER_CHARS + 1)
        with self.assertRaisesRegex(NativeSessionProjectionError, "exceeds"):
            self.project(assistant=self.assistant(answer), run=self.work_session(answer=answer))

    def test_materializer_detects_missing_or_tampered_chunks(self):
        result = self.project()
        rows = list(result.events)
        source = rows[result.events[result.user_message_seq].source_event_seqs[0]]
        rows[source.seq] = type(source).create(source.seq, source.time_ms, source.event_type,
                                               {**source.data, "text": "tampered"})
        with self.assertRaises(NativeSessionProjectionError):
            materialize_message_text(rows, result.user_message_seq)
