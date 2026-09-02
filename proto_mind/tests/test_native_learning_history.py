from copy import deepcopy
import json
import os
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from proto_mind.native_bridge import NativeBackend
from proto_mind.native_learning_history import validate_history
from proto_mind.native_private_records import PrivateRecordStore, digest, encoded
from proto_mind.tests.test_native import FakeSubscription
from proto_mind.tests import test_native_skill_decision as fixture
from proto_mind.skill_lifecycle_restore_apply import reset_procedural_skill_restore_apply_session


class NativeLearningHistoryTests(TestCase):
    seed = fixture.NativeSkillDecisionTests.seed
    files = fixture.NativeSkillDecisionTests.files
    consent = fixture.NativeSkillDecisionTests.consent
    request = fixture.NativeSkillDecisionTests.request
    call = fixture.NativeSkillDecisionTests.call
    capture = fixture.NativeSkillDecisionTests.capture
    ready = fixture.NativeSkillDecisionTests.ready

    def setUp(self):
        reset_procedural_skill_restore_apply_session()
        self.addCleanup(reset_procedural_skill_restore_apply_session)
        fixture.NativeSkillDecisionTests.setUp(self)

    def save_history(self):
        preview = self.call("skill_history_preview")
        params = self.request(preview_fingerprint=preview["preview_fingerprint"], confirmation_token=preview["confirmation_token"], acknowledge_history_only=True)
        result = self.call("skill_history_save", params)
        return preview, result, params

    def test_missing_history_read_and_preview_do_not_create_state_or_pilot(self):
        before = self.files()
        with patch.object(self.backend, "_coordinator", side_effect=AssertionError("No coordinator")), \
                patch.object(self.backend, "process", side_effect=AssertionError("No command dispatch")):
            self.assertEqual(self.call("skill_history_list")["items"], [])
            preview = self.call("skill_history_preview")
        self.assertEqual(preview["receipt_count"], 0)
        self.assertEqual(preview["event_count"], 0)
        self.assertEqual(self.files(), before)
        self.assertEqual(self.backend.sessions, {})

    def test_manual_events_and_original_receipts_survive_without_restoring_authority(self):
        pilot = self.consent(); self.capture()
        self.call("skill_decision_confirm", self.ready())
        before, events = self.files(), pilot.snapshot()
        preview, saved, _ = self.save_history()
        self.assertEqual(preview["receipt_count"], 2)
        self.assertEqual(preview["event_count"], 4)
        after = self.files()
        self.assertTrue(all(after[path] == value for path, value in before.items()))
        self.assertEqual(len(set(after) - set(before)), 2)
        self.assertTrue(all(name.startswith("private/learning_history/") for name in set(after) - set(before)))
        self.assertEqual(pilot.snapshot(), events)
        backend = NativeBackend(self.root, self.base / "private", subscription_factory=FakeSubscription)
        self.addCleanup(backend.close)
        self.backend = backend
        report = self.call("skill_history_inspect", self.request(record_id=saved["record"]["id"]))
        self.assertEqual(report["integrity"], "VERIFIED")
        self.assertEqual(report["record"]["body"], preview["body"])
        self.assertFalse(report["authority_restored"])
        self.assertEqual(self.call("skill_decision_review")["status"], "NOT_READY")
        self.assertEqual(backend.sessions, {})
        self.assertEqual(self.files(), after)

    def test_duplicate_save_is_idempotent_and_never_rewrites_record(self):
        _, saved, params = self.save_history()
        before = self.files()
        repeated = self.call("skill_history_save", params)
        self.assertTrue(repeated["already_saved"])
        self.assertFalse(repeated["private_write_performed"])
        self.assertEqual(repeated["record"], saved["record"])
        self.assertEqual(self.files(), before)

    def test_wrong_token_ack_and_stale_source_or_pilot_refuse_without_file_creation(self):
        preview = self.call("skill_history_preview")
        params = self.request(preview_fingerprint=preview["preview_fingerprint"], confirmation_token=preview["confirmation_token"], acknowledge_history_only=True)
        before = self.files()
        for change in ({"confirmation_token": "wrong"}, {"acknowledge_history_only": False}, {"preview_fingerprint": "0" * 64}, {"execute": True}):
            with self.assertRaises(ValueError):
                self.call("skill_history_save", {**params, **change})
        self.assertEqual(self.files(), before)
        self.consent(); self.capture()
        before = self.files()
        with self.assertRaises(ValueError):
            self.call("skill_history_save", params)
        self.assertEqual(self.files(), before)

    def test_saved_history_remains_historical_when_current_skill_changes(self):
        _, saved, _ = self.save_history()
        path = self.data / "skills.jsonl"
        record = json.loads(path.read_text().splitlines()[0]); record["summary"] += " changed"
        path.write_text(json.dumps(record) + "\n")
        before = self.files()
        report = self.call("skill_history_inspect", self.request(record_id=saved["record"]["id"]))
        self.assertEqual(report["current_record_state"], "CHANGED_OR_MISSING")
        self.assertEqual(self.files(), before)

    def test_conversation_and_workspace_scopes_do_not_mix(self):
        _, saved, _ = self.save_history()
        self.assertEqual(self.call("skill_history_list", self.request(conversation_id=fixture.OTHER))["items"], [])
        with self.assertRaises(ValueError):
            self.call("skill_history_inspect", self.request(conversation_id=fixture.OTHER, record_id=saved["record"]["id"]))
        self.assertEqual(self.call("skill_history_list", self.request(workspace_root=str(self.root)))["items"], [])

    def test_tampered_record_is_not_displayed_or_repaired(self):
        _, saved, _ = self.save_history()
        path = self.base / "private/learning_history" / (saved["record"]["id"] + ".json")
        body = json.loads(path.read_bytes()); body["body"]["name"] = "tampered"
        path.write_text(json.dumps(body))
        before = self.files()
        self.assertTrue(self.call("skill_history_list")["issues"])
        with self.assertRaises(ValueError):
            self.call("skill_history_inspect", self.request(record_id=saved["record"]["id"]))
        with self.assertRaises(ValueError):
            self.call("skill_history_preview")
        self.assertEqual(self.files(), before)

    def test_original_receipt_hash_and_event_linkage_are_reverified(self):
        self.consent(); self.capture()
        body = self.call("skill_history_preview")["body"]
        for change in ("receipt", "event", "authority", "extra"):
            invalid = deepcopy(body)
            if change == "receipt":
                invalid["receipts"][0]["raw"]["outcome"] = "failure"
            elif change == "event":
                invalid["events"].pop()
            elif change == "authority":
                invalid["authority_restored"] = True
            else:
                invalid["shell"] = "not allowed"
            with self.assertRaises((ValueError, KeyError)):
                validate_history(invalid)

    def test_only_selected_skill_manual_events_are_saved_not_other_conversation_text(self):
        pilot = self.consent(); self.capture()
        second = self.consent(fixture.OTHER)
        second.preview()
        preview = self.call("skill_history_preview")
        self.assertEqual(len(preview["body"]["events"]), 4)
        self.assertTrue(all(row["session_id"] == pilot.session_id for row in preview["body"]["events"]))
        self.assertNotIn("history", preview["body"])

    def test_directory_symlink_and_duplicate_json_keys_fail_closed(self):
        self.base.joinpath("private").mkdir(exist_ok=True)
        other = self.base / "external"; other.mkdir()
        directory = self.base / "private/learning_history"; directory.symlink_to(other, target_is_directory=True)
        before = self.files()
        self.assertTrue(self.call("skill_history_list")["issues"])
        with self.assertRaises(ValueError):
            self.call("skill_history_preview")
        self.assertEqual(self.files(), before)
        directory.unlink()
        _, saved, _ = self.save_history()
        path = directory / (saved["record"]["id"] + ".json")
        path.write_bytes(path.read_bytes().replace(b'{"body":', b'{"namespace":"wrong","body":', 1))
        self.assertTrue(self.call("skill_history_list")["issues"])

    def test_unknown_namespace_and_oversized_snapshot_are_refused(self):
        with self.assertRaises(ValueError):
            PrivateRecordStore(self.base, "../../data")
        body = self.call("skill_history_preview")["body"]
        body["skill_record"]["body"] = "a" * 600_000
        with self.assertRaises(ValueError):
            PrivateRecordStore(self.base / "private", "learning_history").save(body, validate_history)
        self.assertFalse((self.base / "private/learning_history").exists())

    def test_new_snapshot_appends_instead_of_modifying_previous(self):
        _, first, _ = self.save_history()
        self.consent(); self.capture()
        before = self.files()
        _, second, _ = self.save_history()
        self.assertNotEqual(first["record"]["id"], second["record"]["id"])
        after = self.files()
        self.assertTrue(all(after[name] == value for name, value in before.items()))
        self.assertEqual(len(self.call("skill_history_list")["items"]), 2)

    def test_archive_and_restore_original_receipts_are_preserved_in_full(self):
        self.consent(); self.capture("failure")
        decision = self.call("skill_decision_confirm", self.ready("archive"))["receipt"]
        params = self.request(decision_receipt_id=decision["id"])
        preview = self.call("skill_lifecycle_preview", params)
        self.assertTrue(preview["ready"], preview)
        self.call("skill_lifecycle_confirm", {**params, "preview_fingerprint": preview["preview_fingerprint"],
                  "confirmation_token": preview["confirmation_token"], "acknowledge_global_skills": True})
        restore = self.call("skill_restore_preview")
        self.assertTrue(restore["ready"], restore)
        self.call("skill_restore_confirm", self.request(preview_fingerprint=restore["preview_fingerprint"],
                  confirmation_token=restore["confirmation_token"], acknowledge_global_skills=True))
        history, saved, _ = self.save_history()
        self.assertEqual([row["kind"] for row in history["body"]["receipts"]], ["manual_outcome", "decision", "archive", "restore"])
        restored = self.call("skill_history_inspect", self.request(record_id=saved["record"]["id"]))
        self.assertEqual(restored["record"]["body"], history["body"])
        self.assertFalse(restored["authority_restored"])

    def test_failed_publish_does_not_replace_core_or_previous_private_records(self):
        _, first, _ = self.save_history()
        self.consent(); self.capture()
        before = self.files()
        preview = self.call("skill_history_preview")
        with patch("proto_mind.native_private_records.os.link", side_effect=OSError("disk full")), self.assertRaises(OSError):
            self.call("skill_history_save", self.request(preview_fingerprint=preview["preview_fingerprint"],
                      confirmation_token=preview["confirmation_token"], acknowledge_history_only=True))
        self.assertEqual(self.files(), before)
        self.assertEqual(self.call("skill_history_list")["items"][0]["id"], first["record"]["id"])
