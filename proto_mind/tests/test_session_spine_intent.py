"""Durable intent and relaunch acceptance checks for Session Spine P2i."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import shutil
import unittest
from uuid import uuid4

from proto_mind.session_spine_handshake import (
    SessionSpineHandshakeError,
    apply_native_turn_handshake,
    validate_native_turn_apply_receipt,
)
from proto_mind.session_spine_intent import (
    COMMITTED_SCHEMA,
    PREPARED_SCHEMA,
    SessionSpineIntentError,
    SessionSpineIntentMissing,
    SessionSpineIntentStore,
    apply_native_turn_intent,
    build_committed_intent,
    inspect_native_turn_intent,
    validate_prepared_intent,
)
from proto_mind.session_spine_store import SessionSpineStore
from proto_mind.tests import test_session_spine_handshake as handshake_tests


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


class SessionSpineIntentTests(unittest.TestCase):
    def setUp(self):
        fixture = handshake_tests.SessionSpineHandshakeTests(
            "test_owner_identity_is_explicit_stable_and_non_authorizing"
        )
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.fixture = fixture
        self.intent_root = fixture.base / "intent-store"
        self.intent_store = SessionSpineIntentStore(self.intent_root)
        self.handshake = fixture.prepare()

    def prepare(self) -> tuple[str, dict]:
        receipt = self.intent_store.prepare(self.handshake)
        return receipt["intent_id"], receipt

    def inspect(self, intent_id: str, **changes) -> dict:
        values = {
            "owner_identity": self.fixture.owner,
            "history_raw": self.fixture.history_raw,
            "work_session_raw": self.fixture.work_raw,
            "work_session_name": self.fixture.work_name,
        }
        values.update(changes)
        return inspect_native_turn_intent(
            self.intent_store,
            self.fixture.spine_store,
            intent_id,
            **values,
        )

    def apply(self, intent_id: str, **changes) -> dict:
        values = {
            "owner_identity": self.fixture.owner,
            "history_raw": self.fixture.history_raw,
            "work_session_raw": self.fixture.work_raw,
            "work_session_name": self.fixture.work_name,
        }
        values.update(changes)
        return apply_native_turn_intent(
            self.intent_store,
            self.fixture.spine_store,
            intent_id,
            **values,
        )

    @staticmethod
    def files(root: Path) -> dict[str, bytes]:
        if not root.exists():
            return {}
        return {
            path.relative_to(root).as_posix(): path.read_bytes()
            for path in sorted(root.rglob("*"))
            if path.is_file() and not path.is_symlink()
        }

    def test_missing_inspection_and_relative_store_are_read_only(self):
        with self.assertRaisesRegex(SessionSpineIntentError, "explicit absolute"):
            SessionSpineIntentStore(Path("relative-intents"))
        before = self.files(self.fixture.base)
        with self.assertRaises(SessionSpineIntentMissing):
            self.intent_store.inspect("0" * 32)
        self.assertEqual(self.files(self.fixture.base), before)
        self.assertFalse(self.intent_root.exists())

    def test_prepare_is_private_content_free_and_idempotent(self):
        intent_id, first = self.prepare()
        prepared_path = self.intent_root / f"{intent_id}.prepared.json"
        raw = prepared_path.read_bytes()
        record = validate_prepared_intent(json.loads(raw))
        self.assertEqual(first["result"], "PREPARED")
        self.assertTrue(first["write_performed"])
        self.assertEqual(record["schema"], PREPARED_SCHEMA)
        self.assertEqual(record["intent_id"], intent_id)
        self.assertNotIn(self.fixture.prompt.encode(), raw)
        self.assertNotIn(self.fixture.answer.encode(), raw)
        self.assertEqual(os.stat(self.intent_root).st_mode & 0o777, 0o700)
        self.assertEqual(os.stat(prepared_path).st_mode & 0o777, 0o600)
        before = self.files(self.intent_root)
        second = self.intent_store.prepare(json.loads(json.dumps(self.handshake)))
        self.assertEqual(second["result"], "ALREADY_PREPARED")
        self.assertFalse(second["write_performed"])
        self.assertEqual(self.files(self.intent_root), before)

    def test_prepared_intent_survives_relaunch_and_applies_once(self):
        intent_id, _ = self.prepare()
        relaunched_intents = SessionSpineIntentStore(self.intent_root)
        relaunched_spine = SessionSpineStore(self.fixture.spine_root)
        ready = inspect_native_turn_intent(
            relaunched_intents,
            relaunched_spine,
            intent_id,
            owner_identity=self.fixture.owner,
            history_raw=self.fixture.history_raw,
            work_session_raw=self.fixture.work_raw,
            work_session_name=self.fixture.work_name,
        )
        self.assertEqual(ready["state"], "READY_TO_APPLY")
        self.assertTrue(ready["spine_write_needed"])
        first = apply_native_turn_intent(
            relaunched_intents,
            relaunched_spine,
            intent_id,
            owner_identity=self.fixture.owner,
            history_raw=self.fixture.history_raw,
            work_session_raw=self.fixture.work_raw,
            work_session_name=self.fixture.work_name,
        )
        self.assertEqual(first["result"], "COMMITTED")
        self.assertTrue(first["spine_write_performed"])
        self.assertTrue(first["intent_write_performed"])
        self.assertEqual(relaunched_intents.inspect(intent_id).state, "committed")
        before = self.files(self.fixture.base)
        second = apply_native_turn_intent(
            SessionSpineIntentStore(self.intent_root),
            SessionSpineStore(self.fixture.spine_root),
            intent_id,
            owner_identity=self.fixture.owner,
            history_raw=self.fixture.history_raw,
            work_session_raw=self.fixture.work_raw,
            work_session_name=self.fixture.work_name,
        )
        self.assertEqual(second["result"], "ALREADY_CLOSED")
        self.assertFalse(second["spine_write_performed"])
        self.assertFalse(second["intent_write_performed"])
        self.assertEqual(self.files(self.fixture.base), before)

    def test_lost_apply_response_recovers_marker_without_second_spine_write(self):
        intent_id, _ = self.prepare()
        direct = apply_native_turn_handshake(
            self.fixture.spine_store,
            self.handshake,
            owner_identity=self.fixture.owner,
            history_raw=self.fixture.history_raw,
            work_session_raw=self.fixture.work_raw,
            work_session_name=self.fixture.work_name,
        )
        self.assertEqual(direct["result"], "COMMITTED")
        spine_before = self.files(self.fixture.spine_root)
        report = self.inspect(intent_id)
        self.assertEqual(report["state"], "COMMIT_MARKER_RECOVERY_REQUIRED")
        self.assertFalse(report["spine_write_needed"])
        recovered = self.apply(intent_id)
        self.assertEqual(recovered["result"], "RECOVERED_COMMIT_MARKER")
        self.assertFalse(recovered["spine_write_performed"])
        self.assertTrue(recovered["intent_write_performed"])
        self.assertEqual(self.files(self.fixture.spine_root), spine_before)
        self.assertEqual(self.inspect(intent_id)["state"], "CLOSED")

    def test_source_drift_blocks_apply_and_preserves_both_stores(self):
        intent_id, _ = self.prepare()
        later = self.fixture.message(str(uuid4()), "user", "Later unsent history fixture")
        changed_history = self.fixture.history(messages=[later])
        before = self.files(self.fixture.base)
        report = self.inspect(intent_id, history_raw=changed_history)
        self.assertEqual(report["state"], "PREPARED_SOURCE_DRIFT")
        with self.assertRaisesRegex(SessionSpineIntentError, "not eligible"):
            self.apply(intent_id, history_raw=changed_history)
        self.assertEqual(self.files(self.fixture.base), before)

    def test_apply_receipt_is_strictly_verified_before_commit_marker(self):
        intent_id, _ = self.prepare()
        apply_receipt = apply_native_turn_handshake(
            self.fixture.spine_store,
            self.handshake,
            owner_identity=self.fixture.owner,
            history_raw=self.fixture.history_raw,
            work_session_raw=self.fixture.work_raw,
            work_session_name=self.fixture.work_name,
        )
        self.assertEqual(validate_native_turn_apply_receipt(apply_receipt), apply_receipt)
        changed = deepcopy(apply_receipt)
        changed["native_activation"] = True
        with self.assertRaises(SessionSpineHandshakeError):
            validate_native_turn_apply_receipt(changed)
        for field, value in (
            ("native_activation", True),
            ("write_performed", False),
            ("written_scope", "none"),
            ("post_state", "COMMITTED_WITH_SOURCE_DRIFT"),
        ):
            with self.subTest(field=field):
                rehashed = deepcopy(apply_receipt)
                rehashed[field] = value
                material = {key: item for key, item in rehashed.items() if key != "receipt_hash"}
                rehashed["receipt_hash"] = hashlib.sha256(_canonical(material)).hexdigest()
                with self.assertRaises(SessionSpineHandshakeError):
                    validate_native_turn_apply_receipt(rehashed)
        other = deepcopy(apply_receipt)
        other["conversation_id"] = str(uuid4())
        material = {key: value for key, value in other.items() if key != "receipt_hash"}
        other["receipt_hash"] = hashlib.sha256(_canonical(material)).hexdigest()
        with self.assertRaisesRegex(SessionSpineIntentError, "another durable intent"):
            build_committed_intent(self.intent_store.inspect(intent_id).prepared, other)
        self.assertEqual(self.intent_store.inspect(intent_id).state, "prepared")

    def test_rehashed_prepared_tamper_is_not_authority(self):
        intent_id, _ = self.prepare()
        path = self.intent_root / f"{intent_id}.prepared.json"
        changed = json.loads(path.read_bytes())
        changed["boundaries"]["automatic_retry"] = True
        material = {key: value for key, value in changed.items() if key != "record_hash"}
        changed["record_hash"] = hashlib.sha256(_canonical(material)).hexdigest()
        path.write_bytes(_canonical(changed))
        os.chmod(path, 0o600)
        with self.assertRaisesRegex(SessionSpineIntentError, "widens"):
            self.intent_store.inspect(intent_id)

    def test_symlink_and_unknown_file_require_manual_recovery(self):
        intent_id, _ = self.prepare()
        prepared = self.intent_root / f"{intent_id}.prepared.json"
        outside = self.fixture.base / "outside-prepared.json"
        outside.write_bytes(prepared.read_bytes())
        original = outside.read_bytes()
        prepared.unlink()
        prepared.symlink_to(outside)
        with self.assertRaisesRegex(SessionSpineIntentError, "Unexpected or unsafe"):
            self.intent_store.inspect(intent_id)
        self.assertEqual(outside.read_bytes(), original)

        other_root = self.fixture.base / "unknown-intent-store"
        other = SessionSpineIntentStore(other_root)
        other_id = other.prepare(self.handshake)["intent_id"]
        partial = other_root / ".intent-write-interrupted.tmp"
        partial.write_bytes(b"partial")
        os.chmod(partial, 0o600)
        with self.assertRaisesRegex(SessionSpineIntentError, "Unexpected or unsafe"):
            other.inspect(other_id)
        self.assertEqual(partial.read_bytes(), b"partial")

    def test_copied_intent_cannot_change_its_explicit_store_scope(self):
        intent_id, _ = self.prepare()
        copied_root = self.fixture.base / "copied-intent-store"
        shutil.copytree(self.intent_root, copied_root)
        copied = SessionSpineIntentStore(copied_root)
        with self.assertRaisesRegex(SessionSpineIntentError, "store scope"):
            copied.inspect(intent_id)
        self.assertEqual(self.files(self.intent_root), self.files(copied_root))

    def test_committed_marker_tamper_is_visible_and_never_repaired(self):
        intent_id, _ = self.prepare()
        self.apply(intent_id)
        path = self.intent_root / f"{intent_id}.committed.json"
        path.write_bytes(b"{}")
        os.chmod(path, 0o600)
        before = path.read_bytes()
        with self.assertRaises(SessionSpineIntentError):
            self.intent_store.inspect(intent_id)
        self.assertEqual(path.read_bytes(), before)

    def test_recovery_inspection_is_read_only(self):
        intent_id, _ = self.prepare()
        before = self.files(self.fixture.base)
        report = self.inspect(intent_id)
        self.assertEqual(report["status"], "OK")
        self.assertTrue(report["boundaries"]["read_only"])
        self.assertFalse(report["boundaries"]["native_activation"])
        self.assertEqual(self.files(self.fixture.base), before)

    def test_no_native_or_bridge_production_caller_exists(self):
        root = Path(__file__).resolve().parents[2]
        app_model = (root / "native/Sources/AppModel.swift").read_text(encoding="utf-8")
        bridge = (root / "proto_mind/native_bridge.py").read_text(encoding="utf-8")
        self.assertNotIn("NativeSessionSpineInstallationStore", app_model)
        self.assertNotIn("saveAndReadBack(", app_model)
        self.assertNotIn("session_spine_intent", bridge)
        self.assertNotIn("apply_native_turn_intent", bridge)
        self.assertFalse(self.handshake["boundaries"]["native_activation"])


if __name__ == "__main__":
    unittest.main()
