from copy import deepcopy
import json
from unittest import TestCase
from unittest.mock import patch

from proto_mind.native_bridge import NativeBackend
from proto_mind.skill_lifecycle_restore_apply import (
    procedural_skill_restore_apply_session,
    reset_procedural_skill_restore_apply_session,
)
from proto_mind.tests.test_native import FakeSubscription
from proto_mind.tests.test_native_skill_inspection import CONVERSATION
from proto_mind.tests import test_native_skill_inspection as fixture


class NativeSkillRestoreTests(TestCase):
    seed = fixture.NativeSkillInspectionTests.seed
    files = fixture.NativeSkillInspectionTests.files

    def setUp(self):
        reset_procedural_skill_restore_apply_session()
        self.addCleanup(reset_procedural_skill_restore_apply_session)
        fixture.NativeSkillInspectionTests.setUp(self)
        self.seed("archived")

    def call(self, method="skill_restore_review", **extra):
        return self.backend.dispatch(method, {"conversation_id": CONVERSATION, "skill_id": self.record["id"], **extra},
                                     lambda _: self.fail("No task/model events"), "restore-test")

    def ready(self):
        preview = self.call("skill_restore_preview")
        self.assertTrue(preview["ready"], preview)
        return {"preview_fingerprint": preview["preview_fingerprint"], "confirmation_token": preview["confirmation_token"],
                "acknowledge_global_skills": True}

    def test_reads_and_preview_have_no_pilot_authority_or_file_initialization(self):
        before = self.files()
        with patch.object(self.backend, "process", side_effect=AssertionError("No command dispatch")), \
                patch("subprocess.Popen", side_effect=AssertionError("No model/shell")):
            report = self.call()
            preview = self.ready()
        self.assertEqual(report["status"], "READY")
        self.assertTrue(preview["confirmation_token"].startswith("CONFIRM-DURABLE-SKILL-RESTORE-"))
        self.assertEqual(self.backend.sessions, {})
        self.assertEqual(self.files(), before)
        self.assertFalse((self.data / "working_memory.json").exists())

    def test_only_exact_confirm_changes_one_record_and_preserves_archival_evidence(self):
        params = self.ready()
        before = self.files()
        old = deepcopy(self.record)
        with patch.object(self.backend, "process", side_effect=AssertionError("No dispatch")):
            result = self.call("skill_restore_confirm", **params)
        receipt = result["receipt"]
        self.assertEqual(receipt["verification_status"], "VERIFIED", result)
        self.assertEqual(receipt["evidence_state"], "CURRENT", result)
        self.assertEqual(receipt["exact_record_mutations"], 1)
        self.assertEqual(receipt["changed_fields"], ["lifecycle", "status", "updated_at"])
        self.assertTrue(result["no_execution"])
        self.assertEqual(result["events_appended"], 0)
        self.record = json.loads(self.skills.read_text().splitlines()[0])
        self.assertEqual(self.record["status"], "active")
        self.assertEqual(sorted(key for key in old if old[key] != self.record[key]), ["lifecycle", "status", "updated_at"])
        self.assertEqual(self.record["provenance"], old["provenance"])
        after = self.files()
        self.assertEqual(set(before), set(after))
        self.assertEqual([path for path in before if before[path] != after[path]], ["project/proto_mind/data/skills.jsonl"])
        self.assertEqual(self.call()["receipt"]["restore_apply_id"], receipt["restore_apply_id"])
        self.assertFalse(self.call()["can_restore"])

    def test_wrong_token_ack_fingerprint_and_extra_execution_fields_refuse_without_consuming(self):
        params = self.ready()
        before = self.files()
        for extra in ({"confirmation_token": "WRONG"}, {"acknowledge_global_skills": False},
                      {"preview_fingerprint": "0" * 64}, {"execute": True}):
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                self.call("skill_restore_confirm", **{**params, **extra})
        self.assertTrue(self.call()["can_restore"])
        self.assertEqual(self.files(), before)

    def test_restart_has_durable_restore_but_no_process_receipt_consent_or_fresh_success(self):
        self.call("skill_restore_confirm", **self.ready())
        before = self.files()
        reset_procedural_skill_restore_apply_session()
        backend = NativeBackend(self.root, self.base / "private", subscription_factory=FakeSubscription)
        self.addCleanup(backend.close)
        request = {"conversation_id": CONVERSATION, "skill_id": self.record["id"]}
        report = backend.dispatch("skill_restore_review", request, lambda _: None, "restart")
        inspection = backend.dispatch("skill_inspection", request, lambda _: None, "restart")
        self.assertIsNone(report["receipt"])
        self.assertFalse(report["can_restore"])
        self.assertEqual(inspection["lifecycle"]["state"], "active_restored_verified")
        self.assertEqual(inspection["outcome"]["status"], "NEEDS_POST_RESTORE_EVIDENCE")
        self.assertEqual(backend.sessions, {})
        self.assertEqual(self.files(), before)

    def test_replay_and_operator_route_share_the_existing_gate(self):
        params = self.ready()
        self.call("skill_restore_confirm", **params)
        before = self.files()
        with self.assertRaises(ValueError):
            self.call("skill_restore_confirm", **params)
        self.assertTrue(self.backend._skill_restore_slot_used())
        self.assertEqual(len(procedural_skill_restore_apply_session().snapshot()), 1)
        self.assertEqual(self.files(), before)

    def test_core_restore_blocks_native_replay_even_when_native_flag_was_not_set(self):
        params = self.ready()
        procedural_skill_restore_apply_session().apply(self.record["id"], token=params["confirmation_token"],
                                                       skills_path=self.skills, persistent_memory_path=self.memories)
        self.assertFalse(self.call()["native_restore_slot_available"])
        self.assertFalse(self.call()["can_restore"])

    def test_active_ambiguous_legacy_and_missing_targets_fail_closed(self):
        for state in ("active", "ambiguous", "missing"):
            with self.subTest(state=state):
                self.skills.write_bytes((self.base / "seed-active" / "skills.jsonl").read_bytes())
                self.record = json.loads(self.skills.read_text().splitlines()[0])
                if state == "ambiguous":
                    self.record["status"] = "archived"
                    self.skills.write_text(json.dumps(self.record) + "\n")
                before = self.files()
                report = self.call(skill_id="missing" if state == "missing" else self.record["id"])
                self.assertFalse(report["can_restore"])
                self.assertEqual(self.files(), before)

    def test_context_source_and_selection_drift_refuse_without_writes(self):
        params = self.ready()
        context = self.data / "context_injection.json"
        context.write_text('{"enabled":true}')
        before = self.files()
        with self.assertRaises(ValueError):
            self.call("skill_restore_confirm", **params)
        self.assertEqual(self.files(), before)
        context.write_text('{"enabled":false}\n')
        self.memories.write_bytes(self.memories.read_bytes() + b"\n")
        before = self.files()
        with self.assertRaises(ValueError):
            self.call("skill_restore_confirm", **params)
        self.assertEqual(self.files(), before)

    def test_missing_context_memory_or_symlink_is_never_initialized(self):
        for name in ("context_injection.json", "persistent_memory.json", "skills.jsonl"):
            target = self.data / name
            payload = target.read_bytes()
            target.unlink()
            before = self.files()
            self.assertFalse(self.call()["can_restore"])
            self.assertEqual(self.files(), before)
            target.write_bytes(payload)
        self.skills.unlink()
        self.skills.symlink_to(self.base / "seed-archived" / "skills.jsonl")
        self.assertFalse(self.call()["can_restore"])

    def test_failure_rolls_back_only_own_bytes_and_consumes_native_attempt(self):
        params = self.ready()
        before = self.files()
        with patch("proto_mind.skill_lifecycle_restore_apply._verify_restore", side_effect=ValueError("synthetic failure")), self.assertRaises(ValueError):
            self.call("skill_restore_confirm", **params)
        self.assertEqual(self.files(), before)
        self.assertFalse(self.call()["native_restore_slot_available"])
        self.assertEqual(procedural_skill_restore_apply_session().snapshot(), ())

    def test_concurrent_bytes_are_preserved_instead_of_destructively_rolled_back(self):
        params = self.ready()
        foreign = self.skills.read_bytes() + b"\n"
        def drift(**_):
            self.skills.write_bytes(foreign)
            raise ValueError("concurrent edit")
        with patch("proto_mind.skill_lifecycle_restore_apply._verify_restore", side_effect=drift), self.assertRaises(ValueError):
            self.call("skill_restore_confirm", **params)
        self.assertEqual(self.skills.read_bytes(), foreign)
        self.assertEqual(procedural_skill_restore_apply_session().snapshot(), ())

    def test_neighbor_bytes_and_line_endings_are_preserved(self):
        from proto_mind.skill_library import SkillLibrary
        library = SkillLibrary(self.base / "neighbor.jsonl")
        library.add_skill(name="Neighbor", summary="Do not touch.")
        neighbor = library.read_snapshot()["records"][0]
        neighbor_bytes = json.dumps(neighbor, indent=None, sort_keys=True).encode() + b"\r\n"
        self.skills.write_bytes(self.skills.read_bytes() + b"\n" + neighbor_bytes)
        result = self.call("skill_restore_confirm", **self.ready())
        self.assertEqual(result["receipt"]["verification_status"], "VERIFIED")
        self.assertTrue(self.skills.read_bytes().endswith(b"\n" + neighbor_bytes))

    def test_busy_and_unscoped_requests_are_refused(self):
        before = self.files()
        with self.assertRaises(ValueError):
            self.call(conversation_id="")
        self.backend.busy.acquire()
        try:
            with self.assertRaises(ValueError):
                self.call()
        finally:
            self.backend.busy.release()
        self.assertEqual(self.files(), before)
