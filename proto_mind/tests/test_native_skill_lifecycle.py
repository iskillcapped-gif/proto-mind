from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
from unittest.mock import patch
from uuid import UUID
import unittest

from proto_mind.experience_learning_skill_lifecycle_metadata_apply import _atomic_replace
from proto_mind.native_bridge import NativeBackend
from proto_mind.skill_lifecycle_metadata import verify_procedural_skill_lifecycle_metadata
from proto_mind.tests import test_native_skill_decision as fixtures
from proto_mind.tests.test_native import FakeSubscription


class NativeSkillLifecycleTests(unittest.TestCase):
    setUp = fixtures.NativeSkillDecisionTests.setUp
    seed = fixtures.NativeSkillDecisionTests.seed
    consent = fixtures.NativeSkillDecisionTests.consent
    files = fixtures.NativeSkillDecisionTests.files
    request = fixtures.NativeSkillDecisionTests.request
    call = fixtures.NativeSkillDecisionTests.call
    capture = fixtures.NativeSkillDecisionTests.capture

    def decide(self, choice="archive", **extra):
        pilot = self.consent()
        self.capture("success" if choice == "keep" else "failure", **extra)
        params = fixtures.NativeSkillDecisionTests.ready(self, choice, **extra)
        self.decision = self.call("skill_decision_confirm", params)["receipt"]
        return pilot

    def params(self, **extra):
        return self.request(decision_receipt_id=getattr(self, "decision", {}).get("id", "skilloutdec_" + "0" * 16), **extra)

    def ready(self, **extra):
        params = self.params(**extra)
        preview = self.call("skill_lifecycle_preview", params)
        self.assertTrue(preview["ready"], preview["reasons"])
        return {**params, "preview_fingerprint": preview["preview_fingerprint"],
                "confirmation_token": preview["confirmation_token"], "acknowledge_global_skills": True}

    def test_views_never_create_pilot_consent_coordinator_or_files(self):
        before = self.files()
        with patch.object(self.backend, "_coordinator", side_effect=AssertionError("No coordinator")), \
                patch.object(self.backend, "process", side_effect=AssertionError("No command")), \
                patch("subprocess.Popen", side_effect=AssertionError("No provider or shell")):
            report = self.call("skill_lifecycle_review", self.params())
            preview = self.call("skill_lifecycle_preview", self.params())
        self.assertEqual(report["status"], "NOT_READY")
        self.assertFalse(preview["ready"])
        self.assertEqual(preview["confirmation_token"], "")
        self.assertEqual(self.backend.sessions, {})
        self.assertEqual(self.files(), before)

    def test_archive_preview_is_exact_and_read_only(self):
        pilot = self.decide()
        before, events = self.files(), pilot.snapshot()
        preview = self.call("skill_lifecycle_preview", self.params())
        self.assertTrue(preview["ready"], preview["reasons"])
        self.assertEqual(preview["expected_record_mutations"], 1)
        self.assertEqual(preview["expected_changed_fields"], ["lifecycle", "status", "updated_at"])
        self.assertEqual(len(preview["metadata_blueprint_hash"]), 64)
        self.assertIn("CONFIRM-DURABLE-SKILL-LIFECYCLE-ARCHIVE-", preview["confirmation_token"])
        self.assertEqual(self.files(), before)
        self.assertEqual(pilot.snapshot(), events)
        self.assertEqual(pilot.skill_lifecycle_metadata_applies.snapshot(), ())

    def test_archive_uses_existing_writer_changes_only_one_record_and_verifies_receipt(self):
        pilot = self.decide()
        before, events, decisions = self.files(), pilot.snapshot(), pilot.skill_outcome_decisions.snapshot()
        params = self.ready()
        with patch.object(self.backend, "process", side_effect=AssertionError("No command")), \
                patch.object(self.backend, "_coordinator", side_effect=AssertionError("No coordinator")), \
                patch("subprocess.Popen", side_effect=AssertionError("No tool or model")):
            result = self.call("skill_lifecycle_confirm", params)
        self.assertTrue(result["skill_mutation_performed"])
        self.assertTrue(result["no_execution"])
        self.assertEqual(result["events_appended"], 0)
        receipt = result["receipt"]
        self.assertEqual(receipt["verification_status"], "VERIFIED")
        self.assertEqual(receipt["evidence_state"], "CURRENT")
        self.assertEqual(receipt["actual_record_mutations"], 1)
        self.assertEqual(receipt["decision_receipt_id"], self.decision["id"])
        self.assertEqual(len(pilot.skill_lifecycle_metadata_applies.snapshot()), 1)
        self.assertEqual(pilot.skill_lifecycle_applies.snapshot(), ())
        after = self.files()
        self.assertEqual([path for path in before if before[path] != after[path]], ["project/proto_mind/data/skills.jsonl"])
        self.assertEqual(set(before), set(after))
        record = json.loads((self.data / "skills.jsonl").read_text())
        self.assertEqual(record["status"], "archived")
        self.assertEqual(record["uses"], self.skill["uses"])
        self.assertEqual(record["provenance"], self.skill["provenance"])
        self.assertTrue(verify_procedural_skill_lifecycle_metadata(record["lifecycle"]).verified)
        self.assertEqual(pilot.snapshot(), events)
        self.assertEqual(pilot.skill_outcome_decisions.snapshot(), decisions)

    def test_keep_is_byte_stable_but_records_its_existing_core_receipt(self):
        pilot = self.decide("keep")
        before = self.files()
        result = self.call("skill_lifecycle_confirm", self.ready())
        self.assertFalse(result["skill_mutation_performed"])
        self.assertFalse(result["store_mutation_performed"])
        self.assertEqual(result["mutation"], "process_memory_keep_receipt")
        self.assertEqual(result["receipt"]["actual_record_mutations"], 0)
        self.assertEqual(result["receipt"]["before_store_sha256"], result["receipt"]["after_store_sha256"])
        self.assertEqual(result["receipt"]["verification_status"], "VERIFIED")
        self.assertEqual(len(pilot.skill_lifecycle_applies.snapshot()), 1)
        self.assertEqual(pilot.skill_lifecycle_metadata_applies.snapshot(), ())
        self.assertEqual(self.files(), before)

    def test_revision_never_becomes_an_edit_or_archive(self):
        self.decide("revise")
        before = self.files()
        self.assertFalse(self.call("skill_lifecycle_preview", self.params())["ready"])
        with self.assertRaisesRegex(ValueError, "Revision"):
            self.call("skill_lifecycle_confirm", self.params())
        self.assertEqual(self.files(), before)
        self.assertFalse(self.backend._native_skill_lifecycle_apply_used)

    def test_wrong_token_ack_and_fingerprint_do_not_consume_attempt(self):
        self.decide()
        params, before = self.ready(), self.files()
        for field, value in (("confirmation_token", "WRONG"), ("preview_fingerprint", "0" * 64),
                             ("acknowledge_global_skills", False), ("acknowledge_global_skills", 1)):
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                self.call("skill_lifecycle_confirm", {**params, field: value})
        self.assertFalse(self.backend._native_skill_lifecycle_apply_used)
        self.assertEqual(self.files(), before)

    def test_decision_token_cannot_authorize_application(self):
        self.decide()
        params = self.ready()
        with self.assertRaisesRegex(ValueError, "token mismatch"):
            self.call("skill_lifecycle_confirm", {**params, "confirmation_token": "CONFIRM-SKILL-ARCHIVE-" + self.decision["decision_hash"][:12].upper()})

    def test_replay_and_reopened_receipt_never_write_again(self):
        self.decide()
        params = self.ready()
        result = self.call("skill_lifecycle_confirm", params)
        before = self.files()
        report = self.call("skill_lifecycle_review", self.params())
        self.assertEqual(report["status"], "APPLIED")
        self.assertEqual(report["stored_skill_status"], "archived")
        self.assertEqual(report["receipt"]["id"], result["receipt"]["id"])
        self.assertFalse(report["can_apply"])
        self.assertFalse(self.call("skill_lifecycle_preview", self.params())["ready"])
        with self.assertRaisesRegex(ValueError, "already applied"):
            self.call("skill_lifecycle_confirm", params)
        self.assertEqual(self.files(), before)

    def test_other_conversation_and_workspace_cannot_reuse_confirmation(self):
        self.decide(workspace_root=str(self.root))
        params = self.ready(workspace_root=str(self.root))
        self.consent(fixtures.OTHER)
        for field, value in (("conversation_id", fixtures.OTHER), ("workspace_root", str(self.base))):
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.call("skill_lifecycle_confirm", {**params, field: value})
        self.assertFalse(self.backend._native_skill_lifecycle_apply_used)

    def test_new_evidence_invalidates_authority_but_not_old_receipt(self):
        pilot = self.decide()
        params = self.ready()
        self.capture("failure", "A later explicit result changes the evidence set.")
        with self.assertRaisesRegex(ValueError, "Historical"):
            self.call("skill_lifecycle_confirm", params)
        self.assertEqual(pilot.skill_lifecycle_metadata_applies.snapshot(), ())

    def test_changed_store_bytes_require_fresh_preview(self):
        self.decide()
        params = self.ready()
        path = self.data / "skills.jsonl"
        path.write_bytes(path.read_bytes() + b"\n")
        before = self.files()
        with self.assertRaisesRegex(ValueError, "changed"):
            self.call("skill_lifecycle_confirm", params)
        self.assertEqual(self.files(), before)
        self.assertTrue(self.call("skill_lifecycle_preview", self.params())["ready"])

    def test_stop_invalidates_old_preview_without_resuming_capture(self):
        pilot = self.decide()
        params = self.ready()
        pilot.stop()
        with self.assertRaisesRegex(ValueError, "changed"):
            self.call("skill_lifecycle_confirm", params)
        result = self.call("skill_lifecycle_confirm", self.ready())
        self.assertEqual(result["receipt"]["verification_status"], "VERIFIED")
        self.assertEqual(pilot.state, "stopped")

    def test_restart_preserves_archive_metadata_not_process_receipt_or_consent(self):
        self.decide()
        self.call("skill_lifecycle_confirm", self.ready())
        before = self.files()
        restarted = NativeBackend(self.root, self.base / "private", subscription_factory=FakeSubscription)
        self.addCleanup(restarted.close)
        report = restarted.dispatch("skill_lifecycle_review", self.params(), lambda _: self.fail(), "fixture")
        self.assertEqual(report["status"], "NOT_READY")
        self.assertIsNone(report["receipt"])
        self.assertFalse(report["can_apply"])
        self.assertTrue(verify_procedural_skill_lifecycle_metadata(json.loads((self.data / "skills.jsonl").read_text())["lifecycle"]).verified)
        self.assertEqual(self.files(), before)

    def test_process_limit_survives_closed_conversation_and_blocks_typed_cli(self):
        self.decide("keep")
        self.call("skill_lifecycle_confirm", self.ready())
        self.backend.sessions.clear()
        self.decide("keep")
        self.assertFalse(self.call("skill_lifecycle_preview", self.params())["ready"])
        command = f"/experience learning apply skill-outcome-lifecycle {self.skill['id']} WRONG"
        with patch.object(self.backend, "_coordinator", side_effect=AssertionError("No dispatch")), self.assertRaisesRegex(ValueError, "single lifecycle"):
            self.backend.process({"conversation_id": fixtures.CONVERSATION, "text": command,
                                  "confirmed_text": command, "provider": "mock"}, lambda _: self.fail(), "fixture")

    def test_closed_or_busy_bridge_cannot_start_a_lifecycle_review(self):
        for closing in (False, True):
            if closing:
                self.backend.closing.set()
            else:
                self.backend.busy.acquire()
            with self.assertRaises(ValueError):
                self.call("skill_lifecycle_review", self.params())
            if not closing:
                self.backend.busy.release()

    def test_arbitrary_payloads_and_scope_mismatches_are_refused(self):
        self.decide()
        for extra in ({"operation": "restore"}, {"command": "/skills archive anything"}, {"decision": "keep"},
                      {"records": []}, {"skills_path": "/tmp/elsewhere"}, {"decision_receipt_id": "bad"},
                      {"skill_id": "missing"}):
            with self.subTest(extra=extra):
                try:
                    report = self.call("skill_lifecycle_preview", {**self.params(), **extra})
                    self.assertFalse(report["ready"])
                except ValueError:
                    pass
        self.assertFalse(self.backend._native_skill_lifecycle_apply_used)

    def test_disabled_context_and_strict_sources_are_mandatory(self):
        self.decide()
        path = self.data / "context_injection.json"
        for content in (b'{"enabled":true}', b'{"enabled":false,"enabled":false}', b'[]', b'{bad', b'{"enabled":false,"x":NaN}'):
            path.write_bytes(content)
            before = self.files()
            self.assertFalse(self.call("skill_lifecycle_preview", self.params())["ready"])
            self.assertEqual(self.files(), before)

    def test_symlink_and_missing_sources_cannot_be_applied(self):
        self.decide()
        path = self.data / "skills.jsonl"
        target = path.with_name("original.jsonl")
        path.rename(target); path.symlink_to(target)
        before = self.files()
        self.assertFalse(self.call("skill_lifecycle_preview", self.params())["ready"])
        self.assertEqual(self.files(), before)
        path.unlink()
        self.assertFalse(self.call("skill_lifecycle_preview", self.params())["ready"])

    def test_corrupt_decision_and_capture_receipts_block_application(self):
        pilot = self.decide()
        original = pilot.skill_outcome_decisions.get(self.decision["id"])
        pilot.skill_outcome_decisions._receipts[self.skill["id"]] = replace(original, receipt_hash="0" * 64)
        self.assertFalse(self.call("skill_lifecycle_preview", self.params())["ready"])

    def test_archive_preserves_neighbor_bytes_blank_lines_and_unknown_fields(self):
        path = self.data / "skills.jsonl"
        neighbor = b' {"id":"legacy","name":"old","status":"active", "extension": [1,2]}  \r\n'
        target = dict(self.skill, extension={"keep": ["original", True]})
        path.write_bytes(b"\r\n" + neighbor + json.dumps(target, ensure_ascii=False).encode() + b"\n\n")
        self.decide()
        self.call("skill_lifecycle_confirm", self.ready())
        self.assertTrue(path.read_bytes().startswith(b"\r\n" + neighbor))
        self.assertTrue(path.read_bytes().endswith(b"\n\n"))
        result = json.loads(path.read_text().splitlines()[2])
        self.assertEqual(result["extension"], target["extension"])

    def test_verification_failure_restores_exact_bytes_and_freezes_native_attempt(self):
        pilot = self.decide()
        params, before = self.ready(), self.files()
        with patch("proto_mind.experience_learning_skill_lifecycle_metadata_apply._verify_durable_archive", side_effect=ValueError("fixture")):
            with self.assertRaisesRegex(ValueError, "exact original Skill Library bytes were restored"):
                self.call("skill_lifecycle_confirm", params)
        self.assertEqual(self.files(), before)
        self.assertEqual(pilot.skill_lifecycle_metadata_applies.snapshot(), ())
        self.assertTrue(self.backend._native_skill_lifecycle_apply_used)
        self.assertFalse(self.call("skill_lifecycle_preview", self.params())["ready"])

    def test_rollback_does_not_clobber_a_later_external_change(self):
        pilot = self.decide()
        params = self.ready()
        path, concurrent = self.data / "skills.jsonl", b'{"id":"external","name":"preserve this"}\n'
        def changed(*args, **kwargs):
            path.write_bytes(concurrent)
            raise ValueError("concurrent fixture")
        with patch("proto_mind.experience_learning_skill_lifecycle_metadata_apply._verify_durable_archive", side_effect=changed):
            with self.assertRaisesRegex(ValueError, "concurrent or unreadable bytes were preserved"):
                self.call("skill_lifecycle_confirm", params)
        self.assertEqual(path.read_bytes(), concurrent)
        self.assertEqual(pilot.skill_lifecycle_metadata_applies.snapshot(), ())

    def test_atomic_replace_failure_and_name_collision_preserve_originals(self):
        self.decide()
        params, before = self.ready(), self.files()
        with patch.object(Path, "replace", side_effect=OSError("replacement fixture")):
            with self.assertRaisesRegex(ValueError, "exact original Skill Library bytes were restored"):
                self.call("skill_lifecycle_confirm", params)
        self.assertEqual(self.files(), before)
        identity = UUID("00000000-0000-0000-0000-000000000001")
        path = self.data / "skills.jsonl"
        collision = path.with_name(f".{path.name}.{identity.hex}.tmp")
        collision.write_bytes(b"preserve unrelated temporary file")
        with patch("proto_mind.experience_learning_skill_apply.uuid4", return_value=identity), self.assertRaises(OSError):
            _atomic_replace(path, b"replacement", expected=path.read_bytes())
        self.assertEqual(collision.read_bytes(), b"preserve unrelated temporary file")

    def test_context_drift_after_write_restores_only_the_skill_not_external_setting(self):
        self.decide()
        params, original = self.ready(), (self.data / "skills.jsonl").read_bytes()
        context = self.data / "context_injection.json"
        def changed(path, payload, **kwargs):
            _atomic_replace(path, payload, **kwargs)
            context.write_text('{"enabled":true}')
        with patch("proto_mind.experience_learning_skill_lifecycle_metadata_apply._atomic_replace", side_effect=changed):
            with self.assertRaisesRegex(ValueError, "exact original Skill Library bytes were restored"):
                self.call("skill_lifecycle_confirm", params)
        self.assertEqual((self.data / "skills.jsonl").read_bytes(), original)
        self.assertTrue(json.loads(context.read_text())["enabled"])


if __name__ == "__main__":
    unittest.main()
