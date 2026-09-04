"""P2l exact-token Native Session Spine writer pilot tests."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest

from proto_mind.native_bridge import NativeBackend
from proto_mind.native_session_spine_writer import (
    NativeSessionSpineWriterError,
    apply_native_session_spine_writer,
    preview_native_session_spine_writer,
)
from proto_mind.session_spine_handshake import build_native_owner_identity
from proto_mind.session_spine_handshake import prepare_native_turn_handshake
from proto_mind.session_spine_intent import SessionSpineIntentStore
from proto_mind.session_spine_store import SessionSpineStore
from proto_mind.tests import test_session_spine_handshake as handshake_tests
from proto_mind.tests.test_native import FakeSubscription


class NativeSessionSpineWriterTests(unittest.TestCase):
    def setUp(self):
        fixture = handshake_tests.SessionSpineHandshakeTests(
            "test_owner_identity_is_explicit_stable_and_non_authorizing"
        )
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.fixture = fixture
        self.state = fixture.native_state
        self.state.chmod(0o700)
        self.history_path = self.state / "conversations.json"
        self.history_path.write_bytes(fixture.history_raw)
        self.history_path.chmod(0o600)
        self.gate = {
            "acceptance_state": "ACCEPTED",
            "candidate_hash": "1" * 64,
            "readiness_report_hash": "2" * 64,
            "rehearsal_hash": "3" * 64,
            "acceptance_report_hash": "4" * 64,
        }
        self.params = {
            "conversation_id": fixture.conversation_id,
            "run": {"run_id": fixture.run_id, "fingerprint": fixture.work_session["fingerprint"]},
            "turn_reference": fixture.reference,
            "user_message": {
                "id": fixture.user_id, "role": "user", "text": fixture.prompt,
                "isError": False, "operatorInput": False,
            },
            "assistant_message": {
                "id": fixture.assistant_id, "role": "assistant", "text": fixture.answer,
                "raw": fixture.answer, "isError": False, "operatorInput": False,
            },
            "gate": self.gate,
        }

    @staticmethod
    def files(root: Path) -> dict[str, bytes]:
        if not root.exists():
            return {}
        return {
            path.relative_to(root).as_posix(): path.read_bytes()
            for path in sorted(root.rglob("*"))
            if path.is_file() and not path.is_symlink()
        }

    @staticmethod
    def canonical_hash(value: object) -> str:
        raw = json.dumps(
            value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()

    def install_identity(self) -> dict:
        identity = build_native_owner_identity(self.fixture.installation_id)
        directory = self.state / "session_spine_identity"
        directory.mkdir(mode=0o700)
        raw = json.dumps(identity, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")).encode()
        path = directory / "installation.json"
        path.write_bytes(raw)
        path.chmod(0o600)
        return identity

    def apply_params(self, preview: dict, identity: dict, **changes) -> dict:
        values = {
            **deepcopy(self.params),
            "preview": preview,
            "confirmation_token": preview["confirmation_token"],
            "owner_identity": identity,
            "history_sha256": hashlib.sha256(self.fixture.history_raw).hexdigest(),
            "history_bytes": len(self.fixture.history_raw),
            "history_write_performed": True,
            "identity_created": preview["identity"]["state"] == "missing",
        }
        values.update(changes)
        return values

    def test_preview_is_content_free_read_only_and_exact_gate_bound(self):
        before = self.files(self.state)
        preview = preview_native_session_spine_writer(self.fixture.work_store, self.state, self.params)
        self.assertEqual(preview["state"], "READY")
        self.assertEqual(preview["status"], "OK")
        self.assertTrue(preview["read_only"])
        self.assertTrue(preview["confirmation_token"].startswith("CONFIRM-SESSION-SPINE-"))
        self.assertEqual(preview["source"]["run_id"], self.fixture.run_id)
        encoded = json.dumps(preview, ensure_ascii=False)
        self.assertNotIn(self.fixture.prompt, encoded)
        self.assertNotIn(self.fixture.answer, encoded)
        self.assertEqual(self.files(self.state), before)

    def test_wrong_token_and_source_drift_write_nothing(self):
        preview = preview_native_session_spine_writer(self.fixture.work_store, self.state, self.params)
        identity = self.install_identity()
        before = self.files(self.state)
        with self.assertRaisesRegex(NativeSessionSpineWriterError, "confirmation failed"):
            apply_native_session_spine_writer(
                self.fixture.work_store, self.state,
                self.apply_params(preview, identity, confirmation_token="CONFIRM-SESSION-SPINE-0000000000000000"),
            )
        self.assertEqual(self.files(self.state), before)
        changed = self.apply_params(preview, identity)
        changed["assistant_message"]["raw"] = "changed answer"
        with self.assertRaises(NativeSessionSpineWriterError):
            apply_native_session_spine_writer(self.fixture.work_store, self.state, changed)
        self.assertEqual(self.files(self.state), before)

    def test_self_consistent_forgery_and_false_identity_transition_are_rejected(self):
        preview = preview_native_session_spine_writer(self.fixture.work_store, self.state, self.params)
        identity = self.install_identity()
        before = self.files(self.state)
        forged = deepcopy(preview)
        forged["candidate_hash"] = "f" * 64
        forged["confirmation_token"] = "CONFIRM-SESSION-SPINE-" + "F" * 16
        forged["preview_hash"] = self.canonical_hash(
            {key: value for key, value in forged.items() if key != "preview_hash"}
        )
        with self.assertRaisesRegex(NativeSessionSpineWriterError, "candidate hash"):
            apply_native_session_spine_writer(
                self.fixture.work_store, self.state, self.apply_params(forged, identity)
            )
        with self.assertRaisesRegex(NativeSessionSpineWriterError, "identity transition"):
            apply_native_session_spine_writer(
                self.fixture.work_store, self.state,
                self.apply_params(preview, identity, identity_created=False),
            )
        self.assertEqual(self.files(self.state), before)

    def test_first_apply_commits_and_lost_response_replay_writes_nothing(self):
        preview = preview_native_session_spine_writer(self.fixture.work_store, self.state, self.params)
        identity = self.install_identity()
        history_before = self.history_path.read_bytes()
        work_before = self.fixture.work_path.read_bytes()
        first = apply_native_session_spine_writer(
            self.fixture.work_store, self.state, self.apply_params(preview, identity)
        )
        self.assertEqual(first["result"], "COMMITTED")
        self.assertTrue(first["spine_write_performed"])
        self.assertTrue(first["intent_prepare_write_performed"])
        self.assertTrue(first["intent_commit_write_performed"])
        self.assertTrue(first["closed"])
        self.assertFalse(first["target_execution_performed"])
        self.assertEqual(self.history_path.read_bytes(), history_before)
        self.assertEqual(self.fixture.work_path.read_bytes(), work_before)
        before_replay = self.files(self.state)
        replay = apply_native_session_spine_writer(
            self.fixture.work_store, self.state, self.apply_params(preview, identity)
        )
        self.assertEqual(replay["result"], "ALREADY_CLOSED")
        self.assertFalse(replay["spine_write_performed"])
        self.assertFalse(replay["intent_prepare_write_performed"])
        self.assertFalse(replay["intent_commit_write_performed"])
        self.assertEqual(self.files(self.state), before_replay)

    def test_closed_turn_is_visible_but_not_confirmable(self):
        preview = preview_native_session_spine_writer(self.fixture.work_store, self.state, self.params)
        identity = self.install_identity()
        apply_native_session_spine_writer(self.fixture.work_store, self.state, self.apply_params(preview, identity))
        recovery_params = deepcopy(self.params)
        recovery_params["gate"] = {**self.gate, "acceptance_state": "RECOVERY_REQUIRED"}
        closed = preview_native_session_spine_writer(self.fixture.work_store, self.state, recovery_params)
        self.assertEqual(closed["state"], "CLOSED")
        self.assertEqual(closed["confirmation_token"], "")
        self.assertEqual(closed["intent_id"], first_intent_id(self.state))

    def test_prepared_intent_recovery_uses_one_new_exact_token(self):
        identity = self.install_identity()
        spine = SessionSpineStore(self.state / "session_spine_store")
        intents = SessionSpineIntentStore(self.state / "session_spine_intents")
        handshake = prepare_native_turn_handshake(
            spine,
            owner_identity=identity,
            history_raw=self.fixture.history_raw,
            work_session_raw=self.fixture.work_raw,
            work_session_name=self.fixture.work_name,
            conversation_id=self.fixture.conversation_id,
            user_message_id=self.fixture.user_id,
            assistant_message_id=self.fixture.assistant_id,
        )
        prepared = intents.prepare(handshake)
        before = self.files(self.state)
        recovery_params = deepcopy(self.params)
        recovery_params["gate"] = {**self.gate, "acceptance_state": "RECOVERY_REQUIRED"}
        preview = preview_native_session_spine_writer(self.fixture.work_store, self.state, recovery_params)
        self.assertEqual(preview["state"], "RECOVERY_READY")
        self.assertEqual(preview["recovery_state"], "READY_TO_APPLY")
        self.assertEqual(preview["intent_id"], prepared["intent_id"])
        self.assertEqual(self.files(self.state), before)
        receipt = apply_native_session_spine_writer(
            self.fixture.work_store,
            self.state,
            self.apply_params(preview, identity, gate=recovery_params["gate"]),
        )
        self.assertEqual(receipt["result"], "COMMITTED")
        self.assertFalse(receipt["intent_prepare_write_performed"])
        self.assertTrue(receipt["spine_write_performed"])

    def test_unknown_or_unrelated_evidence_blocks_without_cleanup(self):
        intent = self.state / "session_spine_intents"
        intent.mkdir(mode=0o700)
        unknown = intent / "unknown.bin"
        unknown.write_bytes(b"do not repair")
        before = self.files(self.state)
        preview = preview_native_session_spine_writer(self.fixture.work_store, self.state, self.params)
        self.assertEqual(preview["state"], "BLOCKED")
        self.assertEqual(preview["confirmation_token"], "")
        self.assertEqual(self.files(self.state), before)

    def test_bridge_methods_are_fixed_busy_gated_and_emit_no_events(self):
        backend = NativeBackend(self.fixture.project, self.state, subscription_factory=FakeSubscription)
        events = []
        preview = backend.dispatch("session_spine_writer_preview", deepcopy(self.params), events.append, "preview")
        self.assertEqual(preview["state"], "READY")
        self.assertEqual(events, [])
        self.assertTrue(backend.busy.acquire(blocking=False))
        try:
            with self.assertRaisesRegex(ValueError, "active turn"):
                backend.dispatch("session_spine_writer_preview", self.params, events.append, "busy")
        finally:
            backend.busy.release()


def first_intent_id(state: Path) -> str:
    names = sorted((state / "session_spine_intents").glob("*.prepared.json"))
    if len(names) != 1:
        raise AssertionError("Expected one prepared intent fixture")
    return names[0].name.split(".", 1)[0]


if __name__ == "__main__":
    unittest.main()
