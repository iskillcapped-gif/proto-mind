from copy import deepcopy
import hashlib
import json
import fcntl
import unittest
from uuid import uuid4

from proto_mind.native_chat_history import NativeChatHistoryError, exact_turn_history
from proto_mind.native_session_spine_writer import preview_native_session_spine_writer, apply_native_session_spine_writer
from proto_mind.tests import test_native_session_spine_writer as writer_tests


def encoded(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()


class NativeChatHistoryTests(unittest.TestCase):
    def setUp(self):
        self.fixture = writer_tests.NativeSessionSpineWriterTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.conversation = self.fixture.fixture.conversation_id
        old = json.loads(self.fixture.history_path.read_bytes())
        self.raw = encoded(old["conversations"][0])
        self.digest = hashlib.sha256(self.raw).hexdigest()
        self.entry = {"id": self.conversation.upper(), "sha256": self.digest, "bytes": len(self.raw),
                      "runIDs": [self.fixture.fixture.run_id]}
        self.manifest = {"version": 6, "selectedID": self.conversation.upper(), "conversations": [self.entry]}
        self.objects = self.fixture.state / "chat_objects"
        self.objects.mkdir(mode=0o700)
        (self.objects / (self.digest + ".json")).write_bytes(self.raw)
        self.fixture.history_path.write_bytes(encoded(self.manifest))

    def read(self, name):
        return (self.objects / name).read_bytes()

    def test_old_inline_history_is_returned_exactly_without_object_reads(self):
        old = self.fixture.fixture.history_raw
        self.assertEqual(exact_turn_history(old, self.conversation, lambda _: self.fail("No object lookup for legacy history")), old)

    def test_v6_snapshot_binds_whole_manifest_and_exact_conversation_read_only(self):
        before = self.fixture.files(self.fixture.state)
        raw = encoded(self.manifest)
        snapshot = exact_turn_history(raw, self.conversation, self.read)
        self.assertEqual(json.loads(snapshot)["storage_manifest_sha256"], hashlib.sha256(raw).hexdigest())
        self.assertEqual(json.loads(snapshot)["conversations"], [json.loads(self.raw)])
        self.assertIn(self.raw, snapshot)
        self.assertEqual(self.fixture.files(self.fixture.state), before)

    def test_manifest_or_entry_tampering_is_refused_before_object_read(self):
        for key, value in (("id", str(uuid4())), ("sha256", "../escape"), ("bytes", True),
                           ("runIDs", [self.entry["runIDs"][0]] * 2), ("extra", "unexpected")):
            changed = deepcopy(self.manifest)
            changed["conversations"][0][key] = value
            with self.subTest(key=key), self.assertRaises(NativeChatHistoryError):
                exact_turn_history(encoded(changed), self.conversation, lambda _: self.fail("Invalid manifest must not read paths"))

    def test_changed_missing_or_relabelled_conversation_is_refused(self):
        for raw in (b"broken", self.raw + b" ", encoded(json.loads(self.raw) | {"id": str(uuid4())})):
            with self.assertRaises(NativeChatHistoryError):
                exact_turn_history(encoded(self.manifest), self.conversation, lambda _: raw)
        (self.objects / (self.digest + ".json")).unlink()
        with self.assertRaises(FileNotFoundError):
            exact_turn_history(encoded(self.manifest), self.conversation, self.read)

    def test_duplicate_cross_conversation_lineage_is_refused(self):
        changed = deepcopy(self.manifest)
        changed["conversations"].append(self.entry | {"id": str(uuid4())})
        with self.assertRaises(NativeChatHistoryError):
            exact_turn_history(encoded(changed), self.conversation, self.read)

    def test_unrelated_conversation_updates_invalidate_the_bound_snapshot(self):
        before = exact_turn_history(encoded(self.manifest), self.conversation, self.read)
        changed = deepcopy(self.manifest)
        changed["conversations"].append(self.entry | {"id": str(uuid4()), "sha256": "a" * 64, "runIDs": []})
        after = exact_turn_history(encoded(changed), self.conversation, self.read)
        self.assertNotEqual(before, after)
        self.assertEqual(json.loads(before)["conversations"], json.loads(after)["conversations"])

    def test_v6_writer_preview_apply_and_replay_keep_history_objects_unchanged(self):
        source = self.fixture
        snapshot = exact_turn_history(encoded(self.manifest), self.conversation, self.read)
        preview = preview_native_session_spine_writer(source.fixture.work_store, source.state, source.params)
        self.assertEqual(preview["state"], "READY")
        identity = source.install_identity()
        parameters = source.apply_params(preview, identity, history_sha256=hashlib.sha256(snapshot).hexdigest(), history_bytes=len(snapshot))
        history_before, objects_before = source.history_path.read_bytes(), source.files(self.objects)
        result = apply_native_session_spine_writer(source.fixture.work_store, source.state, parameters)
        self.assertEqual(result["result"], "COMMITTED")
        replay = apply_native_session_spine_writer(source.fixture.work_store, source.state, parameters)
        self.assertEqual(replay["result"], "ALREADY_CLOSED")
        self.assertEqual(source.history_path.read_bytes(), history_before)
        self.assertEqual(source.files(self.objects), objects_before)

    def test_duplicate_fields_and_boolean_schema_are_refused(self):
        for raw in (b'{"version":6,"version":5,"conversations":[]}', b'{"version":true,"conversations":[]}'):
            with self.assertRaises(NativeChatHistoryError):
                exact_turn_history(raw, self.conversation, self.read)

    def test_native_writer_lock_prevents_history_drift_during_spine_inspection(self):
        source = self.fixture
        lock = source.state / ".history.lock"
        with lock.open("wb") as writer:
            fcntl.flock(writer, fcntl.LOCK_EX | fcntl.LOCK_NB)
            before = source.files(source.state)
            with self.assertRaisesRegex(NativeChatHistoryError, "being saved"):
                preview_native_session_spine_writer(source.fixture.work_store, source.state, source.params)
            self.assertEqual(source.files(source.state), before)
        self.assertEqual(preview_native_session_spine_writer(source.fixture.work_store, source.state, source.params)["state"], "READY")

    def test_spine_inspection_never_creates_a_missing_history_lock(self):
        source = self.fixture
        before = source.files(source.state)
        preview_native_session_spine_writer(source.fixture.work_store, source.state, source.params)
        self.assertFalse((source.state / ".history.lock").exists())
        self.assertEqual(source.files(source.state), before)
