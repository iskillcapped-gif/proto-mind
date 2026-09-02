from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from proto_mind.experience_learning_skill_apply import (
    ProceduralSkillApplyError, _atomic_replace, _parse_jsonl_records,
)
from proto_mind.native_bridge import NativeBackend
from proto_mind.native_library import NativeLibrary
from proto_mind.native_skill_authoring import NativeSkillAuthoring
from proto_mind.tests.test_flow import build_test_procedural_skill_authoring
from proto_mind.tests.test_native import FakeSubscription


CONVERSATION = "00000000-0000-0000-0000-000000000001"
OTHER = "00000000-0000-0000-0000-000000000002"


class NativeSkillAuthoringTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.root = self.base / "project"
        self.data = self.root / "proto_mind/data"
        self.data.mkdir(parents=True)
        _, store, _, _, _, _, receipt = build_test_procedural_skill_authoring(self.base / "seed")
        self.lesson = receipt.source_lesson_id
        self.fields = deepcopy(receipt.authored_contract)
        (self.data / "persistent_memory.json").write_bytes(store.persistent_path.read_bytes())
        (self.data / "working_memory.json").write_bytes(store.working_path.read_bytes())
        self.skills = self.data / "skills.jsonl"
        self.skills.write_bytes(b'{"id":"legacy","name":"Unrelated old skill","summary":"Old manual record","body":"read only","status":"archived","custom":{"keep":true}}\n\n')
        (self.data / "context_injection.json").write_text('{"enabled":false}\n')
        self.backend = NativeBackend(self.root, self.base / "private", subscription_factory=FakeSubscription)
        self.addCleanup(self.backend.close)

    def files(self):
        return {str(path.relative_to(self.base)): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in self.base.rglob("*") if path.is_file()}

    def params(self, operation=None, **extra):
        result = {"conversation_id": CONVERSATION, "lesson_id": self.lesson, "authored": deepcopy(self.fields), **extra}
        if operation:
            result["operation"] = operation
        return result

    def call(self, method, params):
        return self.backend.dispatch(method, params, lambda _: self.fail("No emitted execution event"), "fixture")

    def confirmation(self, operation, **extra):
        params = self.params(operation, **extra)
        preview = self.call("skill_authoring_preview", params)
        self.assertTrue(preview["ready"], preview["issues"])
        return {**params, "preview_fingerprint": preview["preview_fingerprint"],
                "confirmation_token": preview["confirmation_token"], "acknowledge_global_skills": operation == "apply"}

    def author(self):
        return self.call("skill_authoring_confirm", self.confirmation("author"))

    def apply(self):
        return self.call("skill_authoring_confirm", self.confirmation("apply"))

    def test_read_only_preview_uses_durable_lesson_without_pilot_or_model(self):
        before = self.files()
        with patch.object(self.backend, "process", side_effect=AssertionError("No command dispatcher")), \
                patch("subprocess.Popen", side_effect=AssertionError("No provider/shell")):
            report = self.call("skill_authoring_review", self.params())
            preview = self.call("skill_authoring_preview", self.params("author"))
        self.assertTrue(report["eligible"], report["source_issues"])
        self.assertTrue(report["read_only"])
        self.assertEqual(report["skill_store_scope"], "global_legacy_stores")
        self.assertFalse(report["project_isolation_enforced"])
        self.assertTrue(preview["ready"])
        self.assertEqual(preview["future_mutation"], "process_memory_only")
        self.assertEqual(self.backend.sessions, {})
        self.assertEqual(self.backend._native_skill_session.authoring.snapshot(), ())
        self.assertEqual(self.files(), before)

    def test_missing_stores_and_missing_lesson_never_initialize_files(self):
        empty = NativeBackend(self.base / "missing", self.base / "missing-state", subscription_factory=FakeSubscription)
        self.addCleanup(empty.close)
        before = self.files()
        result = empty.dispatch("skill_authoring_review", self.params(), lambda _: None, "test")
        preview = empty.dispatch("skill_authoring_preview", self.params("author"), lambda _: None, "test")
        self.assertFalse(result["eligible"])
        self.assertFalse(preview["ready"])
        self.assertEqual(preview["confirmation_token"], "")
        self.assertEqual(self.files(), before)

    def test_author_confirmation_changes_only_existing_core_process_session(self):
        before = self.files()
        params = self.confirmation("author")
        with self.assertRaisesRegex(ValueError, "token mismatch"):
            self.call("skill_authoring_confirm", {**params, "confirmation_token": "WRONG"})
        result = self.call("skill_authoring_confirm", params)
        self.assertFalse(result["skill_mutation_performed"])
        self.assertEqual(result["mutation"], "process_memory_only")
        self.assertEqual(result["receipt"]["authoring_hash"], result["receipt"]["receipt_hash"])
        self.assertTrue(result["no_execution"])
        self.assertEqual(self.backend.sessions, {})
        self.assertEqual(self.files(), before)
        self.assertFalse(self.call("skill_authoring_preview", self.params("author"))["ready"])

    def test_incomplete_duplicate_oversized_and_extra_fields_are_refused(self):
        before = self.files()
        for fields in ({**self.fields, "steps": []}, {**self.fields, "steps": ["inspect", " Inspect "]}):
            preview = self.call("skill_authoring_preview", self.params("author", authored=fields))
            self.assertFalse(preview["ready"])
        for fields in ({**self.fields, "name": "x" * 801}, {**self.fields, "permissions": ["read"] * 9},
                       {**self.fields, "executable": True}, {**self.fields, "name": "bad\x00name"},
                       {**self.fields, "trigger": ["not text"]}):
            with self.assertRaises(ValueError):
                self.call("skill_authoring_preview", self.params("author", authored=fields))
        with self.assertRaises(ValueError):
            self.call("skill_authoring_preview", self.params("execute"))
        with self.assertRaises(ValueError):
            self.call("skill_authoring_confirm", self.params("apply", command="/memory forget all"))
        self.assertEqual(self.files(), before)

    def test_form_and_workspace_drift_invalidate_confirmation(self):
        params = self.confirmation("author", workspace_root=str(self.root))
        before = self.files()
        other = self.base / "workspace"
        other.mkdir()
        for changed in ({"authored": {**self.fields, "trigger": "changed"}}, {"workspace_root": str(other)},
                        {"conversation_id": OTHER}):
            with self.assertRaisesRegex(ValueError, "changed"):
                self.call("skill_authoring_confirm", {**params, **changed})
        self.assertEqual(self.files(), before)

    def test_receipt_bound_to_conversation_and_workspace_without_recreation(self):
        self.author()
        before = self.files()
        result = self.call("skill_authoring_review", self.params(conversation_id=OTHER))
        self.assertEqual(result["status"], "ERROR")
        self.assertIsNone(result["authoring_receipt"])
        preview = self.call("skill_authoring_preview", self.params("apply", conversation_id=OTHER))
        self.assertFalse(preview["ready"])
        self.assertEqual(self.files(), before)

    def test_save_requires_author_receipt_and_separate_global_acknowledgement(self):
        before = self.files()
        self.assertFalse(self.call("skill_authoring_preview", self.params("apply"))["ready"])
        self.author()
        params = self.confirmation("apply")
        with self.assertRaisesRegex(ValueError, "Acknowledge"):
            self.call("skill_authoring_confirm", {**params, "acknowledge_global_skills": False})
        self.assertEqual(self.files(), before)
        self.assertEqual(self.backend._native_skill_session.applies.snapshot(), ())

    def test_apply_changes_one_store_preserves_legacy_bytes_and_never_executes(self):
        self.author()
        before, old_bytes = self.files(), self.skills.read_bytes()
        with patch.object(self.backend, "process", side_effect=AssertionError("No dispatcher")), \
                patch("subprocess.Popen", side_effect=AssertionError("No shell/model")):
            result = self.apply()
        after = self.files()
        self.assertEqual([key for key in after if before.get(key) != after[key]], ["project/proto_mind/data/skills.jsonl"])
        self.assertTrue(self.skills.read_bytes().startswith(old_bytes))
        rows = _parse_jsonl_records(self.skills.read_bytes())
        self.assertEqual(len(rows), 2)
        self.assertFalse(rows[-1]["executable"])
        self.assertEqual(rows[-1]["source_lesson_id"], self.lesson)
        self.assertTrue(rows[-1]["provenance"])
        self.assertEqual(result["receipt"]["verification_status"], "OK")
        self.assertEqual(result["receipt"]["record_id"], rows[-1]["id"])
        self.assertTrue(result["skill_mutation_performed"])
        self.assertFalse(result["memory_mutation_performed"])
        self.assertTrue(result["no_execution"])

    def test_repeat_and_changed_authored_contract_cannot_save_again(self):
        self.author()
        params = self.confirmation("apply")
        with self.assertRaisesRegex(ValueError, "form differs"):
            self.call("skill_authoring_confirm", {**params, "authored": {**self.fields, "summary": "changed"}})
        self.call("skill_authoring_confirm", params)
        before = self.files()
        self.backend.sessions.clear()
        report = self.call("skill_authoring_review", self.params())
        self.assertEqual(report["status"], "APPLIED")
        self.assertFalse(report["native_apply_slot_available"])
        with self.assertRaisesRegex(ValueError, "slot"):
            self.call("skill_authoring_confirm", params)
        self.assertEqual(self.files(), before)

    def test_stale_store_bytes_prevent_apply(self):
        self.author()
        params = self.confirmation("apply")
        self.skills.write_bytes(self.skills.read_bytes() + b"\n")
        before = self.files()
        with self.assertRaisesRegex(ValueError, "changed"):
            self.call("skill_authoring_confirm", params)
        self.assertEqual(self.files(), before)

    def test_inactive_or_tampered_source_cannot_be_saved(self):
        self.author()
        params = self.confirmation("apply")
        path = self.data / "persistent_memory.json"
        rows = json.loads(path.read_bytes())
        lesson = next(row for row in rows if row["id"] == self.lesson)
        lesson["content"] = "Changed, without matching provenance"
        path.write_text(json.dumps(rows))
        before = self.files()
        self.assertFalse(self.call("skill_authoring_review", self.params())["eligible"])
        with self.assertRaises(ValueError):
            self.call("skill_authoring_confirm", params)
        self.assertEqual(self.files(), before)

    def test_invalid_json_symlink_and_duplicate_ids_block_inspection_and_confirmation(self):
        original = self.skills.read_bytes()
        for payload in (b"not json", b'{"id":"same"}\n{"id":"same"}\n', b'{"id":"one","id":"two"}\n'):
            self.skills.write_bytes(payload)
            report = self.call("skill_authoring_review", self.params())
            self.assertEqual(report["status"], "ERROR")
            self.assertFalse(self.call("skill_authoring_preview", self.params("author"))["ready"])
            self.assertEqual(self.skills.read_bytes(), payload)
        target = self.base / "outside-skills.jsonl"
        target.write_bytes(original)
        self.skills.unlink()
        self.skills.symlink_to(target)
        report = self.call("skill_authoring_review", self.params())
        self.assertEqual(report["status"], "ERROR")
        self.assertEqual(target.read_bytes(), original)
        self.assertTrue(self.skills.is_symlink())

    def test_verification_failure_restores_exact_bytes(self):
        self.author()
        params, before = self.confirmation("apply"), self.files()
        with patch("proto_mind.experience_learning_skill_apply._verify_skill_write", side_effect=ProceduralSkillApplyError("fixture failure")):
            with self.assertRaisesRegex(ValueError, "original bytes were restored"):
                self.call("skill_authoring_confirm", params)
        self.assertEqual(self.files(), before)
        self.assertEqual(self.backend._native_skill_session.applies.snapshot(), ())

    def test_verification_failure_never_overwrites_concurrent_change(self):
        self.author()
        params = self.confirmation("apply")
        concurrent = b'{"id":"someone-elses-change"}\n'
        def failure(*args, **kwargs):
            self.skills.write_bytes(concurrent)
            raise ProceduralSkillApplyError("simulated concurrent edit")
        with patch("proto_mind.experience_learning_skill_apply._verify_skill_write", side_effect=failure):
            with self.assertRaisesRegex(ValueError, "concurrent"):
                self.call("skill_authoring_confirm", params)
        self.assertEqual(self.skills.read_bytes(), concurrent)

    def test_lost_success_response_does_not_renew_apply_budget(self):
        self.author()
        params = self.confirmation("apply")
        with patch.object(NativeSkillAuthoring, "_receipt", side_effect=RuntimeError("lost reply")):
            with self.assertRaisesRegex(RuntimeError, "lost reply"):
                self.call("skill_authoring_confirm", params)
        before = self.files()
        self.assertTrue(self.backend._native_skill_apply_used)
        report = self.call("skill_authoring_review", self.params())
        self.assertEqual(report["status"], "APPLIED")
        self.assertEqual(report["apply_receipt"]["verification_status"], "OK")
        with self.assertRaises(ValueError):
            self.call("skill_authoring_confirm", params)
        self.assertEqual(self.files(), before)

    def test_restart_keeps_skill_provenance_but_not_authoring_receipts(self):
        self.author()
        result = self.apply()
        restarted = NativeBackend(self.root, self.base / "private", subscription_factory=FakeSubscription)
        self.addCleanup(restarted.close)
        before = self.files()
        report = restarted.dispatch("skill_authoring_review", self.params(), lambda _: None, "restart")
        self.assertIsNone(report["authoring_receipt"])
        self.assertIsNone(report["apply_receipt"])
        self.assertFalse(report["eligible"])
        self.assertIn("duplicate", " ".join(report["source_issues"]).lower())
        self.assertIn(result["receipt"]["record_id"], self.skills.read_text())
        self.assertEqual(self.files(), before)

    def test_busy_backend_rejects_review_and_confirm_without_session_creation(self):
        self.backend.busy.acquire()
        before = self.files()
        try:
            for method in ("skill_authoring_review", "skill_authoring_preview", "skill_authoring_confirm"):
                params = self.params() if method == "skill_authoring_review" else self.params("author")
                with self.assertRaisesRegex(ValueError, "active turn"):
                    self.call(method, params)
        finally:
            self.backend.busy.release()
        self.assertEqual(self.files(), before)
        self.assertEqual(self.backend.sessions, {})

    def test_missing_skill_store_can_be_created_only_on_confirmed_apply(self):
        self.skills.unlink()
        self.author()
        self.assertFalse(self.skills.exists())
        result = self.apply()
        self.assertEqual(len(_parse_jsonl_records(self.skills.read_bytes())), 1)
        self.assertEqual(result["receipt"]["before_store_sha256"], hashlib.sha256(b"").hexdigest())
        self.assertEqual(self.skills.stat().st_mode & 0o777, 0o600)

    def test_atomic_writer_does_not_remove_or_overwrite_existing_temporary_file(self):
        class FixedUUID:
            hex = "collision"
        temporary = self.skills.with_name(f".{self.skills.name}.collision.tmp")
        temporary.write_bytes(b"owned by someone else")
        before = self.skills.read_bytes()
        with patch("proto_mind.experience_learning_skill_apply.uuid4", return_value=FixedUUID()):
            with self.assertRaises(FileExistsError):
                _atomic_replace(self.skills, b"replacement", expected=before)
        self.assertEqual(self.skills.read_bytes(), before)
        self.assertEqual(temporary.read_bytes(), b"owned by someone else")

    def test_operator_command_cannot_bypass_native_ui_apply_budget(self):
        self.author()
        self.apply()
        before = self.files()
        text = f"/experience learning apply skill {self.lesson} WRONG"
        with self.assertRaisesRegex(ValueError, "single skill apply slot"):
            self.backend.process({"conversation_id": OTHER, "provider": "mock", "text": text, "confirmed_text": text},
                                 lambda _: self.fail("No event"), "operator")
        self.assertNotIn(OTHER, self.backend.sessions)
        self.assertEqual(self.files(), before)

    def test_prior_operator_apply_slot_blocks_native_save(self):
        self.author()
        self.backend._native_skill_apply_used = True
        before = self.files()
        preview = self.call("skill_authoring_preview", self.params("apply"))
        self.assertFalse(preview["ready"])
        self.assertIn("single skill apply slot", " ".join(preview["issues"]))
        self.assertEqual(self.files(), before)

    def test_durable_skill_evidence_is_read_only_and_detects_tampering(self):
        self.author()
        applied = self.apply()
        reader = NativeLibrary(self.root)
        key = "skills:" + applied["receipt"]["record_id"]
        before = self.files()
        evidence = reader.inspect("skills", key)["skill_evidence"]
        self.assertEqual(evidence["status"], "VERIFIED")
        self.assertEqual(evidence["source_lesson_id"], self.lesson)
        self.assertTrue(evidence["no_execution"])
        self.assertEqual(self.files(), before)
        records = _parse_jsonl_records(self.skills.read_bytes())
        records[-1]["provenance"]["provenance_hash"] = "0" * 64
        self.skills.write_text("\n".join(json.dumps(record) for record in records))
        tampered = self.skills.read_bytes()
        self.assertEqual(reader.inspect("skills", key)["skill_evidence"]["status"], "ERROR")
        self.assertEqual(self.skills.read_bytes(), tampered)

    def test_legacy_skill_provenance_remains_unavailable(self):
        before = self.files()
        evidence = NativeLibrary(self.root).inspect("skills", "skills:legacy")["skill_evidence"]
        self.assertEqual(evidence["status"], "UNAVAILABLE")
        self.assertEqual(evidence["provenance_id"], "")
        self.assertFalse(evidence["verified"])
        self.assertEqual(self.files(), before)


if __name__ == "__main__":
    unittest.main()
