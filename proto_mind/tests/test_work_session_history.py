"""Unbounded journal retention with bounded pages and exact read-only lookup."""
import json
from unittest import TestCase
from unittest.mock import patch
from uuid import UUID, uuid4

from proto_mind import native_work_sessions as sessions
from proto_mind.native_bridge import NativeBackend
from proto_mind.tests.test_native import FakeSubscription
from proto_mind.tests import test_native_work_sessions as fixture


class WorkSessionHistoryTests(TestCase):
    setUp = fixture.WorkSessionTests.setUp
    begin = fixture.WorkSessionTests.begin
    finish = fixture.WorkSessionTests.finish
    files = fixture.WorkSessionTests.files

    def seed(self, count, **changes):
        if not self.store.directory.exists():
            self.finish()
        original = self.store.directory / (self.run_id + ".json")
        template = json.loads(original.read_bytes())
        records = []
        for index in range(count):
            record = template | {"id": str(UUID(int=index + 1)), "created_at": "2026-09-01T12:00:00.000000Z", **changes}
            (self.store.directory / (record["id"] + ".json")).write_bytes(sessions._bytes(record))
            records.append(record)
        return records

    def test_more_than_500_runs_remain_readable_and_new_runs_preserve_all_old_bytes(self):
        self.seed(605)
        old = {path: path.read_bytes() for path in self.store.directory.glob("*.json")}
        with patch.object(self.store, "_records", side_effect=AssertionError("No history scan for an independent turn")):
            self.finish(run_id=str(uuid4()))
        self.assertEqual({path: path.read_bytes() for path in old}, old)
        self.assertEqual(len(list(self.store.directory.glob("*.json"))), 607)
        page = self.store.page(self.conversation)
        self.assertEqual(page["total"], 607)
        self.assertEqual(len(page["runs"]), 30)
        self.assertTrue(page["partial"])
        self.assertIsNotNone(page["next_cursor"])

    def test_all_pages_are_ordered_unique_and_preserve_bytes_across_restart(self):
        seeded = self.seed(76)
        before = self.files()
        ids, cursor = [], None
        while True:
            store = sessions.WorkSessionStore(self.state, self.root)
            page = store.page(self.conversation, cursor)
            self.assertEqual(page["cursor"], cursor)
            self.assertEqual(page["total"], 77)
            self.assertLessEqual(len(page["runs"]), 30)
            ids.extend(record["id"] for record in page["runs"])
            cursor = page["next_cursor"]
            self.assertEqual(page["partial"], cursor is not None)
            if cursor is None:
                break
        self.assertEqual(ids, [self.run_id] + [record["id"] for record in reversed(seeded)])
        self.assertEqual(len(set(ids)), 77)
        self.assertEqual(before, self.files())

    def test_incoming_newer_run_does_not_shift_or_duplicate_the_next_page(self):
        self.seed(65)
        first = self.store.page(self.conversation)
        expected_second = self.store.page(self.conversation, first["next_cursor"])
        self.finish(run_id=str(uuid4()))
        second = self.store.page(self.conversation, first["next_cursor"])
        self.assertEqual(second["runs"], expected_second["runs"])
        self.assertEqual(second["total"], expected_second["total"] + 1)
        self.assertFalse({row["id"] for row in first["runs"]} & {row["id"] for row in second["runs"]})

    def test_byte_budget_cursor_includes_every_whole_record_on_later_pages(self):
        self.seed(12)
        before = self.files()
        ids, cursor = [], None
        record_size = len(sessions._bytes(self.store.lookup(str(UUID(int=1)), self.conversation)))
        with patch.object(sessions, "MAX_PAGE_BYTES", record_size * 2 + 500):
            while True:
                page = self.store.page(self.conversation, cursor)
                self.assertTrue(page["runs"])
                self.assertLessEqual(sum(len(sessions._bytes(row)) for row in page["runs"]), sessions.MAX_PAGE_BYTES)
                ids.extend(row["id"] for row in page["runs"])
                cursor = page["next_cursor"]
                if cursor is None:
                    break
        self.assertEqual(len(ids), 13)
        self.assertEqual(len(set(ids)), 13)
        self.assertEqual(before, self.files())

    def test_invalid_or_cross_scope_cursors_are_refused_without_writes(self):
        self.seed(32)
        cursor = self.store.page(self.conversation)["next_cursor"]
        before = self.files()
        bad = [False, [], "cursor", {}, cursor | {"conversation_id": str(uuid4())},
               cursor | {"project_root": str(self.root / "other")}, cursor | {"run_id": "../escape"},
               cursor | {"created_at": "not a date"}, cursor | {"created_at": "x" * 81}, cursor | {"extra": True}]
        for value in bad:
            with self.subTest(value=value), self.assertRaises(sessions.WorkSessionError):
                self.store.page(self.conversation, value)
        self.assertEqual(before, self.files())

    def test_exact_lookup_finds_old_run_without_scanning_and_checks_every_scope(self):
        old = self.seed(40)[0]
        before = self.files()
        with patch.object(self.store, "_records", side_effect=AssertionError("No scan for exact lookup")):
            selected = self.store.lookup(old["id"], self.conversation)
            self.assertEqual(selected["id"], old["id"])
            self.assertEqual(selected["fingerprint"], sessions.fingerprint(old))
            for run_id, conversation in ((old["id"], str(uuid4())), (str(uuid4()), self.conversation), ("../escape", self.conversation)):
                with self.assertRaises(sessions.WorkSessionError):
                    self.store.lookup(run_id, conversation)
        other = sessions.WorkSessionStore(self.state, self.root / "other")
        with self.assertRaises(sessions.WorkSessionError):
            other.lookup(old["id"], self.conversation)
        self.assertEqual(before, self.files())

    def test_missing_lookup_and_page_leave_missing_store_uninitialized(self):
        with self.assertRaises(sessions.WorkSessionError):
            self.store.lookup(self.run_id, self.conversation)
        page = self.store.page(self.conversation)
        self.assertEqual(page["total"], 0)
        self.assertIsNone(page["next_cursor"])
        self.assertFalse(page["partial"])
        self.assertFalse(self.state.exists())

    def test_other_conversations_and_projects_are_excluded_from_every_page(self):
        self.seed(32)
        self.finish(run_id=str(uuid4()), conversation_id=str(uuid4()), text="Private other conversation")
        other = sessions.WorkSessionStore(self.state, self.root / "other")
        with other.begin(run_id=str(uuid4()), conversation_id=self.conversation, text="Private other project", provider="mock",
                         model="", effort="", mode="chat", workspace=None, sources=[]) as run:
            run.complete("Other project reply")
        before = self.files()
        first = self.store.page(self.conversation)
        second = self.store.page(self.conversation, first["next_cursor"])
        self.assertEqual(first["total"], 33)
        self.assertEqual(len(first["runs"]) + len(second["runs"]), 33)
        self.assertNotIn("Private other", json.dumps(first) + json.dumps(second))
        self.assertEqual(before, self.files())

    def test_continuation_of_an_old_run_remains_exact_and_run_once(self):
        parent = self.seed(40)[0]
        reference = {"run_id": parent["id"], "fingerprint": sessions.fingerprint(parent)}
        before = self.files()
        preview = self.store.continuation(reference, self.conversation, None)
        self.assertEqual(preview["run_id"], parent["id"])
        self.assertEqual(before, self.files())
        child = self.finish(run_id=str(uuid4()), continuation=reference)
        self.assertEqual(child["parent_run_id"], parent["id"])
        after = self.files()
        with self.assertRaisesRegex(sessions.WorkSessionError, "continuation already exists"):
            self.store.continuation(reference, self.conversation, None)
        self.assertEqual(after, self.files())

    def test_many_corrupt_files_have_bounded_warning_and_do_not_hide_valid_pages(self):
        old = self.seed(35)[0]
        for index in range(80):
            (self.store.directory / (str(uuid4()) + ".json")).write_text("broken")
        before = self.files()
        page = self.store.page(self.conversation)
        self.assertEqual(len(page["warnings"]), 1)
        self.assertEqual(page["total"], 36)
        self.assertEqual(self.store.lookup(old["id"], self.conversation)["id"], old["id"])
        with self.assertRaisesRegex(sessions.WorkSessionError, "manual review"):
            self.store.continuation({"run_id": old["id"], "fingerprint": sessions.fingerprint(old)}, self.conversation, None)
        self.assertEqual(before, self.files())

    def test_bridge_pagination_and_lookup_are_read_only_without_a_provider_or_core_session(self):
        old = self.seed(35)[0]
        backend = NativeBackend(self.root, self.state, subscription_factory=FakeSubscription)
        self.addCleanup(backend.close)
        before = self.files()
        with patch.object(backend, "_coordinator", side_effect=AssertionError("No cognitive turn")):
            first = backend.dispatch("work_sessions", {"conversation_id": self.conversation}, lambda _: None, "first")
            second = backend.dispatch("work_sessions", {"conversation_id": self.conversation, "cursor": first["next_cursor"]}, lambda _: None, "second")
            found = backend.dispatch("work_session_lookup", {"conversation_id": self.conversation, "run_id": old["id"]}, lambda _: None, "lookup")
        self.assertEqual(len(first["runs"]) + len(second["runs"]), 36)
        self.assertTrue(found["read_only"])
        self.assertEqual(found["run"]["id"], old["id"])
        self.assertEqual(before, self.files())
        self.assertEqual(backend.subscription.calls, [])
        self.assertFalse(backend.sessions)
