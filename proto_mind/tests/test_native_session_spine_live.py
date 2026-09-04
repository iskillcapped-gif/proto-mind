"""Exact read-only live projection from Native history and durable run evidence."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from uuid import uuid4

from proto_mind.native_bridge import NativeBackend
from proto_mind.native_instructions import PreparedLocalInstructions, build_instruction_receipt
from proto_mind.native_session_spine_live import (
    NativeSessionSpineLiveError,
    build_live_session_spine_preview,
)
from proto_mind.native_turn_lineage import build_turn_reference
from proto_mind.native_work_sessions import WorkSessionStore
from proto_mind.tests.test_native import FakeSubscription


class NativeSessionSpineLiveTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="proto-native-spine-live-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / "project"
        self.root.mkdir()
        self.state = Path(temporary.name) / "private"
        self.store = WorkSessionStore(self.state, self.root)
        self.conversation = str(uuid4())
        self.run_id = str(uuid4())
        self.user_id = str(uuid4())
        self.assistant_id = str(uuid4())
        self.prompt = "Покажи точную локальную проекцию этого хода."
        self.answer = "Проекция собрана в памяти; ни одного события не сохранено."
        instruction = build_instruction_receipt(
            provider="codex",
            mode="chat",
            prepared=PreparedLocalInstructions("local fixture", "legacy_cognitive_core_current_projection", None),
            developer_instructions="synthetic local contract",
        )
        with self.store.begin(
            run_id=self.run_id,
            conversation_id=self.conversation,
            text=self.prompt,
            provider="codex",
            model="synthetic-no-provider-call",
            effort="high",
            mode="chat",
            workspace=None,
            sources=[],
        ) as writer:
            writer.dispatch()
            writer.complete(self.answer, instruction_receipt=instruction)
        run = self.store.page(self.conversation)["runs"][0]
        self.reference = build_turn_reference(
            receipt=run["turn_receipt"],
            source_message_id=self.user_id,
            input_text=self.prompt,
            response=self.answer,
        )
        self.params = {
            "conversation_id": self.conversation,
            "run": {"run_id": self.run_id, "fingerprint": run["fingerprint"]},
            "turn_reference": self.reference,
            "user_message": {
                "id": self.user_id,
                "role": "user",
                "text": self.prompt,
                "isError": False,
                "operatorInput": False,
            },
            "assistant_message": {
                "id": self.assistant_id,
                "role": "assistant",
                "text": self.answer,
                "raw": self.answer,
                "isError": False,
                "operatorInput": False,
            },
        }

    def files(self):
        return {str(path.relative_to(self.state)): path.read_bytes() for path in self.state.rglob("*") if path.is_file()}

    def test_exact_turn_builds_content_free_existing_p1_preview(self):
        preview = build_live_session_spine_preview(self.store, self.params)
        self.assertEqual(preview["schema"], "proto_mind.native_session_spine_live_preview.v1")
        self.assertTrue(preview["read_only"])
        self.assertTrue(preview["no_write"])
        self.assertFalse(preview["source_record_write"])
        self.assertTrue(preview["no_model_call"])
        self.assertEqual(preview["source"]["run_id"], self.run_id)
        self.assertEqual(preview["projection"]["schema"], "proto_mind.native_session_spine_projection.v1")
        self.assertEqual(len(preview["timeline"]), preview["projection"]["spine"]["event_count"])
        encoded = json.dumps(preview, ensure_ascii=False)
        self.assertNotIn(self.prompt, encoded)
        self.assertNotIn(self.answer, encoded)

    def test_preview_is_deterministic_and_changes_no_private_bytes(self):
        before = self.files()
        first = build_live_session_spine_preview(self.store, self.params)
        second = build_live_session_spine_preview(self.store, deepcopy(self.params))
        self.assertEqual(first, second)
        self.assertEqual(self.files(), before)
        material = {key: value for key, value in first.items() if key != "preview_hash"}
        encoded = json.dumps(material, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":"))
        self.assertEqual(first["preview_hash"], hashlib.sha256(encoded.encode()).hexdigest())

    def test_message_reference_and_run_drift_fail_closed(self):
        cases = []
        for path, value in (
            (("user_message", "text"), "changed input"),
            (("assistant_message", "raw"), "changed answer"),
            (("turn_reference", "reference_hash"), "0" * 64),
            (("run", "fingerprint"), "0" * 64),
        ):
            changed = deepcopy(self.params)
            changed[path[0]][path[1]] = value
            cases.append((path, changed))
        for path, changed in cases:
            with self.subTest(path=path), self.assertRaises(NativeSessionSpineLiveError):
                build_live_session_spine_preview(self.store, changed)

    def test_missing_or_relabelled_run_is_never_replaced_by_latest(self):
        for run_id in (str(uuid4()), self.run_id.upper()):
            changed = deepcopy(self.params)
            changed["run"]["run_id"] = run_id
            with self.subTest(run_id=run_id), self.assertRaises(NativeSessionSpineLiveError):
                build_live_session_spine_preview(self.store, changed)

    def test_closed_request_rejects_operator_or_extra_fields(self):
        operator = deepcopy(self.params)
        operator["user_message"]["operatorInput"] = True
        extra = deepcopy(self.params)
        extra["assistant_message"]["evidence"] = {"private": "not accepted"}
        partial_suggestion = deepcopy(self.params)
        partial_suggestion["assistant_message"]["memorySuggestions"] = {}
        for changed in (operator, extra, partial_suggestion):
            with self.subTest(changed=changed), self.assertRaises(NativeSessionSpineLiveError):
                build_live_session_spine_preview(self.store, changed)

    def test_bridge_dispatch_is_read_only_and_emits_no_live_events(self):
        backend = NativeBackend(self.root, self.state, subscription_factory=FakeSubscription)
        before = self.files()
        events = []
        preview = backend.dispatch("session_spine_preview", deepcopy(self.params), events.append, "spine-preview")
        self.assertEqual(preview["source"]["run_id"], self.run_id)
        self.assertEqual(events, [])
        self.assertEqual(self.files(), before)
        self.assertFalse(backend.busy.locked())

    def test_bridge_refuses_preview_while_a_turn_owns_the_backend(self):
        backend = NativeBackend(self.root, self.state, subscription_factory=FakeSubscription)
        self.assertTrue(backend.busy.acquire(blocking=False))
        try:
            with self.assertRaisesRegex(ValueError, "active turn"):
                backend.dispatch("session_spine_preview", self.params, lambda _: None, "busy")
        finally:
            backend.busy.release()


if __name__ == "__main__":
    unittest.main()
