from __future__ import annotations

import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from proto_mind.experience_pilot import get_experience_pilot
from proto_mind.models import (
    GroundingAuditResult, InteractionResult, InteractionSummary, MemoryRecord,
    ObserverState, SelfReflectionResult,
)
from proto_mind.native_bridge import NativeBackend
from proto_mind.native_library import NativeLibrary
from proto_mind.tests.test_native import FakeSubscription


CONVERSATION = "00000000-0000-0000-0000-000000000001"
OTHER_CONVERSATION = "00000000-0000-0000-0000-000000000002"


class NativeLearningReviewTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "project"
        self.data = self.root / "proto_mind/data"
        self.data.mkdir(parents=True)
        self.state = Path(self.temporary.name) / "private"
        reference = MemoryRecord("Known reference, not a lesson.", "project_fact", 0.7, "operator", id="reference")
        self.write("persistent_memory.json", [reference.to_dict()])
        self.write("working_memory.json", [])
        self.write("context_injection.json", {"enabled": False})
        (self.data / "skills.jsonl").write_text("", encoding="utf-8")
        self.backend = NativeBackend(self.root, self.state, subscription_factory=FakeSubscription)
        self.addCleanup(self.backend.close)

    def write(self, name, value):
        (self.data / name).write_text(json.dumps(value, indent=2), encoding="utf-8")

    def files(self):
        return {str(path.relative_to(self.temporary.name)): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in Path(self.temporary.name).rglob("*") if path.is_file()}

    def seed(self, conversation=CONVERSATION, hint="Inspect the exact evidence before choosing a correction."):
        owner = self.backend._coordinator(conversation)
        pilot = get_experience_pilot(owner, project_root=self.root)
        pilot.preview()
        pilot.consent(pilot.expected_consent_phrase)
        result = InteractionResult(
            response="Current evidence only.",
            observer_state=ObserverState("continuity_followup", True, 0.8, ["project"]),
            retrieved_memory=[], retrieval_trace=None,
            memory_summary=InteractionSummary("none", "", 0.0, [], False),
            working_memory_snapshot=[], persistent_memory_snapshot=[], reasoner_backend="fixture",
            self_reflection=SelfReflectionResult(False, "ok", "ok", "ok", "low", "low", "high"),
            grounding_audit=GroundingAuditResult(False, "not_needed", "not_needed", "not_needed", "not_needed"),
            previous_correction_hints=[hint],
        )
        pilot.observe_normal_turn("Продолжим проект.", result)
        workshop = self.call("memory_workshop", {"conversation_id": conversation})
        candidate = workshop["candidates"][0]["id"]
        return pilot, candidate

    def call(self, method, params):
        return self.backend.dispatch(method, params, lambda _: self.fail("No event dispatch"), "fixture")

    def request(self, candidate, operation="", **extra):
        value = {"conversation_id": CONVERSATION, "candidate_id": candidate, **extra}
        if operation:
            value["operation"] = operation
        return value

    def confirm(self, candidate, operation, **extra):
        params = self.request(candidate, operation, **extra)
        preview = self.call("memory_learning_preview", params)
        self.assertTrue(preview["ready"], preview["issues"])
        return self.call("memory_learning_confirm", {
            **params, "preview_fingerprint": preview["preview_fingerprint"],
            "confirmation_token": preview["confirmation_token"], "acknowledge_global_memory": operation == "apply",
        })

    def proposal(self, candidate, **extra):
        self.confirm(candidate, "accept", **extra)
        return self.confirm(candidate, "propose", memory_ids=["reference"], **extra)

    def test_missing_pilot_review_does_not_create_session_or_files(self):
        before = self.files()
        with patch.object(self.backend, "process", side_effect=AssertionError("No dispatcher")), \
                patch("subprocess.Popen", side_effect=AssertionError("No model or shell")):
            report = self.call("memory_learning_review", self.request("missing"))
            preview = self.call("memory_learning_preview", self.request("missing", "accept"))
        self.assertEqual(report["status"], "NOT FOUND")
        self.assertFalse(preview["ready"])
        self.assertEqual(preview["confirmation_token"], "")
        self.assertEqual(self.backend.sessions, {})
        self.assertEqual(self.files(), before)

    def test_candidate_review_is_read_only_and_exposes_exact_reference_scope(self):
        pilot, candidate = self.seed()
        before, events = self.files(), pilot.snapshot()
        report = self.call("memory_learning_review", self.request(candidate))
        self.assertEqual(report["candidate"]["id"], candidate)
        self.assertEqual(report["references"][0]["record_id"], "reference")
        self.assertEqual(report["requested_memory_ids"], [])
        self.assertFalse(report["project_isolation_enforced"])
        self.assertEqual(report["memory_store_scope"], "global_legacy_stores")
        self.assertTrue(report["read_only"])
        self.assertIsNone(report["decision"])
        self.assertEqual(self.files(), before)
        self.assertEqual(pilot.snapshot(), events)

    def test_accept_requires_exact_current_token_and_only_changes_process_decision(self):
        pilot, candidate = self.seed()
        before = self.files()
        params = self.request(candidate, "accept", reason="Checked the source evidence.")
        preview = self.call("memory_learning_preview", params)
        with self.assertRaisesRegex(ValueError, "token mismatch"):
            self.call("memory_learning_confirm", {**params, "preview_fingerprint": preview["preview_fingerprint"], "confirmation_token": "WRONG"})
        self.assertEqual(pilot.learning_decisions.snapshot(), ())
        result = self.confirm(candidate, "accept", reason="Checked the source evidence.")
        self.assertEqual(result["receipt"]["status"], "accepted")
        self.assertEqual(result["mutation"], "process_memory_only")
        self.assertFalse(result["memory_mutation_performed"])
        self.assertEqual(self.files(), before)
        again = self.call("memory_learning_preview", params)
        self.assertFalse(again["ready"])

    def test_reject_is_terminal_process_memory_only(self):
        pilot, candidate = self.seed()
        before = self.files()
        result = self.confirm(candidate, "reject", reason="Insufficient confidence.")
        self.assertEqual(result["receipt"]["status"], "rejected")
        self.assertEqual(pilot.learning_decisions.get(candidate).reason, "Insufficient confidence.")
        self.assertFalse(self.call("memory_learning_preview", self.request(candidate, "propose", memory_ids=["reference"]))["ready"])
        self.assertEqual(self.files(), before)

    def test_proposal_requires_accepted_candidate_and_explicit_reference_ids(self):
        _, candidate = self.seed()
        before = self.files()
        self.assertFalse(self.call("memory_learning_preview", self.request(candidate, "propose", memory_ids=["reference"]))["ready"])
        self.confirm(candidate, "accept")
        self.assertFalse(self.call("memory_learning_preview", self.request(candidate, "propose"))["ready"])
        self.assertFalse(self.call("memory_learning_preview", self.request(candidate, "propose", memory_ids=["missing"]))["ready"])
        result = self.confirm(candidate, "propose", memory_ids=["reference"])
        self.assertEqual(result["receipt"]["target_schema"], "memory.lesson.v1")
        self.assertEqual(result["mutation"], "process_memory_only")
        self.assertEqual(self.files(), before)

    def test_apply_requires_global_ack_and_changes_exactly_one_store_once(self):
        pilot, candidate = self.seed()
        self.proposal(candidate)
        before = self.files()
        rows = json.loads((self.data / "persistent_memory.json").read_bytes())
        params = self.request(candidate, "apply")
        preview = self.call("memory_learning_preview", params)
        confirmation = {**params, "preview_fingerprint": preview["preview_fingerprint"], "confirmation_token": preview["confirmation_token"]}
        with self.assertRaisesRegex(ValueError, "Acknowledge"):
            self.call("memory_learning_confirm", confirmation)
        self.assertEqual(self.files(), before)
        result = self.call("memory_learning_confirm", {**confirmation, "acknowledge_global_memory": True})
        after = self.files()
        self.assertEqual([path for path in after if after[path] != before.get(path)], ["project/proto_mind/data/persistent_memory.json"])
        current = json.loads((self.data / "persistent_memory.json").read_bytes())
        self.assertEqual(current[:-1], rows)
        self.assertEqual(result["receipt"]["verification_status"], "OK")
        self.assertEqual(result["receipt"]["record_id"], current[-1]["id"])
        self.assertFalse(result["command_execution_performed"])
        self.assertTrue(result["memory_mutation_performed"])
        with self.assertRaisesRegex(ValueError, "already|slot"):
            self.call("memory_learning_confirm", {**confirmation, "acknowledge_global_memory": True})
        self.assertEqual(self.files(), after)
        self.assertEqual(len(pilot.learning_applies.snapshot()), 1)

    def test_changed_reference_or_store_invalidates_confirmation(self):
        _, candidate = self.seed()
        self.proposal(candidate)
        params = self.request(candidate, "apply")
        preview = self.call("memory_learning_preview", params)
        path = self.data / "working_memory.json"
        path.write_text("[ ]\n", encoding="utf-8")
        before = self.files()
        with self.assertRaisesRegex(ValueError, "changed"):
            self.call("memory_learning_confirm", {**params, "preview_fingerprint": preview["preview_fingerprint"],
                                                    "confirmation_token": preview["confirmation_token"], "acknowledge_global_memory": True})
        self.assertEqual(self.files(), before)

    def test_changed_reason_and_workspace_cannot_reuse_preview(self):
        _, candidate = self.seed()
        params = self.request(candidate, "accept", workspace_root=str(self.root))
        preview = self.call("memory_learning_preview", params)
        before = self.files()
        with self.assertRaisesRegex(ValueError, "changed"):
            self.call("memory_learning_confirm", {**params, "reason": "different", "preview_fingerprint": preview["preview_fingerprint"],
                                                    "confirmation_token": preview["confirmation_token"]})
        other = Path(self.temporary.name) / "other"
        other.mkdir()
        with self.assertRaisesRegex(ValueError, "changed"):
            self.call("memory_learning_confirm", {**params, "workspace_root": str(other), "preview_fingerprint": preview["preview_fingerprint"],
                                                    "confirmation_token": preview["confirmation_token"]})
        self.assertEqual(self.files(), before)

    def test_other_conversation_cannot_confirm_candidate(self):
        _, candidate = self.seed()
        params = self.request(candidate, "accept")
        preview = self.call("memory_learning_preview", params)
        before = self.files()
        with self.assertRaisesRegex(ValueError, "absent"):
            self.call("memory_learning_confirm", {**params, "conversation_id": OTHER_CONVERSATION,
                                                    "preview_fingerprint": preview["preview_fingerprint"], "confirmation_token": preview["confirmation_token"]})
        self.assertNotIn(OTHER_CONVERSATION, self.backend.sessions)
        self.assertEqual(self.files(), before)

    def test_busy_closing_and_arbitrary_operation_are_refused(self):
        _, candidate = self.seed()
        before = self.files()
        self.backend.busy.acquire()
        try:
            with self.assertRaisesRegex(ValueError, "active turn"):
                self.call("memory_learning_review", self.request(candidate))
        finally:
            self.backend.busy.release()
        with self.assertRaisesRegex(ValueError, "Only accept"):
            self.call("memory_learning_preview", self.request(candidate, "shell"))
        with self.assertRaisesRegex(ValueError, "Unexpected"):
            self.call("memory_learning_preview", self.request(candidate, "accept", command="/memory forget reference"))
        self.backend.closing.set()
        with self.assertRaisesRegex(ValueError, "active turn"):
            self.call("memory_learning_review", self.request(candidate))
        self.assertEqual(self.files(), before)

    def test_global_duplicate_refuses_apply_outside_selected_scope(self):
        _, candidate = self.seed()
        self.proposal(candidate)
        report = self.call("memory_learning_review", self.request(candidate))
        rows = json.loads((self.data / "persistent_memory.json").read_bytes())
        rows.append(MemoryRecord(report["candidate"]["text"], "lesson", 0.8, "operator", id="duplicate").to_dict())
        self.write("persistent_memory.json", rows)
        before = self.files()
        preview = self.call("memory_learning_preview", self.request(candidate, "apply"))
        self.assertFalse(preview["ready"])
        self.assertTrue(any("duplicate" in item for item in preview["issues"]))
        self.assertEqual(self.files(), before)

    def test_native_apply_budget_covers_multiple_conversations(self):
        _, candidate = self.seed()
        self.proposal(candidate)
        self.confirm(candidate, "apply")
        _, other = self.seed(OTHER_CONVERSATION, "Check different evidence before changing a plan.")
        self.proposal(other, conversation_id=OTHER_CONVERSATION)
        before = self.files()
        preview = self.call("memory_learning_preview", self.request(other, "apply", conversation_id=OTHER_CONVERSATION))
        self.assertFalse(preview["ready"])
        self.assertTrue(any("Native bridge process" in item for item in preview["issues"]))
        self.assertEqual(self.files(), before)

    def test_exit_does_not_renew_the_native_apply_budget(self):
        _, candidate = self.seed()
        self.proposal(candidate)
        self.confirm(candidate, "apply")
        before = self.files()
        result = self.backend.process({"conversation_id": CONVERSATION, "provider": "mock", "text": "/exit"}, lambda _: None, "fixture-exit")
        self.assertTrue(result["exit_requested"])
        self.assertNotIn(CONVERSATION, self.backend.sessions)
        _, next_candidate = self.seed(OTHER_CONVERSATION, "Verify a new source before accepting the next conclusion.")
        self.proposal(next_candidate, conversation_id=OTHER_CONVERSATION)
        preview = self.call("memory_learning_preview", self.request(next_candidate, "apply", conversation_id=OTHER_CONVERSATION))
        self.assertFalse(preview["ready"])
        self.assertTrue(any("Native bridge process" in issue for issue in preview["issues"]))
        self.assertEqual(self.files(), before)

    def test_response_projection_failure_after_apply_still_consumes_budget(self):
        from proto_mind.native_learning_review import NativeLearningReview
        _, candidate = self.seed()
        self.proposal(candidate)
        with patch.object(NativeLearningReview, "_receipt", side_effect=ValueError("response fixture")):
            with self.assertRaisesRegex(ValueError, "response fixture"):
                self.confirm(candidate, "apply")
        self.assertTrue(self.backend._native_learning_apply_used)
        report = self.call("memory_learning_review", self.request(candidate))
        self.assertEqual(report["apply_receipt"]["verification_status"], "OK")
        before = self.files()
        self.assertFalse(self.call("memory_learning_preview", self.request(candidate, "apply"))["ready"])
        self.assertEqual(self.files(), before)

    def test_restart_loses_process_review_but_preserves_verified_memory_provenance(self):
        _, candidate = self.seed()
        self.proposal(candidate)
        result = self.confirm(candidate, "apply")
        before = self.files()
        restarted = NativeBackend(self.root, self.state, subscription_factory=FakeSubscription)
        self.addCleanup(restarted.close)
        report = restarted.dispatch("memory_learning_review", self.request(candidate), lambda _: None, "restart")
        self.assertEqual(report["status"], "NOT FOUND")
        detail = NativeLibrary(self.root).inspect("memory", "persistent:" + result["receipt"]["record_id"])
        self.assertEqual(detail["memory_evidence"]["status"], "VERIFIED")
        self.assertEqual(self.files(), before)

    def test_malformed_or_symlink_source_never_gets_confirmation_token(self):
        _, candidate = self.seed()
        path = self.data / "persistent_memory.json"
        original = path.read_bytes()
        path.write_text("{bad", encoding="utf-8")
        before = self.files()
        preview = self.call("memory_learning_preview", self.request(candidate, "accept"))
        self.assertFalse(preview["ready"])
        self.assertEqual(preview["confirmation_token"], "")
        self.assertEqual(self.files(), before)
        path.unlink()
        target = Path(self.temporary.name) / "outside.json"
        target.write_bytes(original)
        path.symlink_to(target)
        before = self.files()
        self.assertFalse(self.call("memory_learning_preview", self.request(candidate, "accept"))["ready"])
        self.assertEqual(self.files(), before)

    def test_request_parser_refuses_malformed_or_unbounded_selectors(self):
        _, candidate = self.seed()
        before = self.files()
        for extra in ({"operation": []}, {"operation": {}}, {"memory_ids": ["reference", "reference"]},
                      {"memory_ids": ["/memory remember x"]}, {"query": "x" * 201}, {"reason": "x" * 161},
                      {"reason": "bad\x00reason"}, {"conversation_id": "bad"}, {"candidate_id": "../outside"}):
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                self.call("memory_learning_preview", {**self.request(candidate, "accept"), **extra})
        self.assertEqual(self.files(), before)

    def test_proposal_reference_selection_cannot_silently_change(self):
        _, candidate = self.seed()
        self.proposal(candidate)
        before = self.files()
        preview = self.call("memory_learning_preview", self.request(candidate, "apply", memory_ids=["different"]))
        self.assertFalse(preview["ready"])
        self.assertEqual(preview["confirmation_token"], "")
        self.assertTrue(any("selection" in issue for issue in preview["issues"]))
        self.assertEqual(self.files(), before)

    def test_duplicate_key_and_missing_timestamp_fail_closed_without_rewriting(self):
        _, candidate = self.seed()
        for raw in (b'[{"id":"reference","id":"different"}]', b'[{"id":"reference","content":"legacy"}]'):
            (self.data / "persistent_memory.json").write_bytes(raw)
            before = self.files()
            report = self.call("memory_learning_review", self.request(candidate))
            preview = self.call("memory_learning_preview", self.request(candidate, "accept"))
            self.assertEqual(report["status"], "ERROR")
            self.assertFalse(preview["ready"])
            self.assertEqual(self.files(), before)

    def test_expired_proposal_has_no_apply_token(self):
        from dataclasses import replace
        pilot, candidate = self.seed()
        self.proposal(candidate)
        proposal = pilot.learning_proposals.get(candidate)
        # A stale receipt is never made fresh by the Native inspector.
        with patch.object(pilot.learning_proposals, "get", return_value=replace(proposal, created_at="2000-01-01T00:00:00+00:00")):
            before = self.files()
            preview = self.call("memory_learning_preview", self.request(candidate, "apply"))
            self.assertFalse(preview["ready"])
            self.assertEqual(preview["confirmation_token"], "")
            self.assertTrue(any("15-minute" in issue for issue in preview["issues"]))
            self.assertEqual(self.files(), before)


if __name__ == "__main__":
    unittest.main()
