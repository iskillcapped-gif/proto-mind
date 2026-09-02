from __future__ import annotations

from dataclasses import replace
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from proto_mind.experience_pilot import EXPERIENCE_PILOT_ATTR, SupervisedExperiencePilot
from proto_mind.native_bridge import NativeBackend
from proto_mind.native_skill_decision import NativeSkillDecision
from proto_mind.tests.test_flow import (
    build_test_applied_procedural_skill, build_test_durably_archived_procedural_skill,
    build_test_restored_procedural_skill,
)
from proto_mind.tests.test_native import FakeSubscription


CONVERSATION = "00000000-0000-0000-0000-000000000001"
OTHER = "00000000-0000-0000-0000-000000000002"


class NativeSkillDecisionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.root = self.base / "project"
        self.data = self.root / "proto_mind/data"
        self.data.mkdir(parents=True)
        self.seed("active")
        (self.data / "context_injection.json").write_text('{"enabled":false}\n')
        self.backend = NativeBackend(self.root, self.base / "private", subscription_factory=FakeSubscription)
        self.addCleanup(self.backend.close)

    def seed(self, state):
        builder = {"active": build_test_applied_procedural_skill, "archived": build_test_durably_archived_procedural_skill,
                   "restored": build_test_restored_procedural_skill}[state]
        memory, skills, *_ = builder(self.base / f"seed-{state}")
        (self.data / "persistent_memory.json").write_bytes(memory.persistent_path.read_bytes())
        (self.data / "skills.jsonl").write_bytes(skills.skills_path.read_bytes())
        self.skill = json.loads(skills.skills_path.read_text().splitlines()[0])

    def consent(self, conversation=CONVERSATION):
        pilot = SupervisedExperiencePilot(self.root)
        pilot.preview(); pilot.consent(pilot.expected_consent_phrase)
        self.backend.sessions[conversation] = SimpleNamespace(**{EXPERIENCE_PILOT_ATTR: pilot})
        return pilot

    def files(self):
        return {str(path.relative_to(self.base)): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in self.base.rglob("*") if path.is_file()}

    def request(self, **extra):
        return {"conversation_id": CONVERSATION, "skill_id": self.skill["id"], **extra}

    def call(self, method, params=None):
        return self.backend.dispatch(method, params if params is not None else self.request(),
                                     lambda _: self.fail("No target execution"), "fixture")

    def capture(self, outcome="success", evidence="Manually checked the synthetic result.", **extra):
        params = self.request(outcome=outcome, evidence=evidence, **extra)
        preview = self.call("skill_outcome_preview", params)
        self.assertTrue(preview["ready"], preview["reasons"])
        return self.call("skill_outcome_confirm", {**params, "preview_fingerprint": preview["preview_fingerprint"],
                         "confirmation_token": preview["confirmation_token"], "acknowledge_manual_only": True})

    def ready(self, decision="keep", **extra):
        params = self.request(decision=decision, **extra)
        preview = self.call("skill_decision_preview", params)
        self.assertTrue(preview["ready"], preview["reasons"])
        return {**params, "preview_fingerprint": preview["preview_fingerprint"],
                "confirmation_token": preview["confirmation_token"], "acknowledge_decision_only": True}

    def allowed(self, report):
        return [choice["decision"] for choice in report["choices"] if choice["allowed"]]

    def test_opening_and_preview_do_not_create_pilot_consent_or_stores(self):
        before = self.files()
        with patch.object(self.backend, "_coordinator", side_effect=AssertionError("No coordinator")), \
                patch.object(self.backend, "process", side_effect=AssertionError("No command")), \
                patch("subprocess.Popen", side_effect=AssertionError("No provider or shell")):
            report = self.call("skill_decision_review")
            preview = self.call("skill_decision_preview", self.request(decision="archive"))
        self.assertEqual(report["status"], "NOT_READY")
        self.assertEqual(report["pilot_state"], "not_started")
        self.assertFalse(preview["ready"])
        self.assertEqual(preview["confirmation_token"], "")
        self.assertEqual(self.allowed(report), [])
        self.assertEqual(self.backend.sessions, {})
        self.assertEqual(self.files(), before)

    def test_consented_but_empty_evidence_cannot_become_a_decision(self):
        pilot = self.consent()
        report = self.call("skill_decision_review")
        self.assertEqual(self.allowed(report), [])
        self.assertEqual(pilot.snapshot(), ())
        self.assertEqual(pilot.skill_outcome_decisions.snapshot(), ())

    def test_success_allows_keep_only_and_never_preselects_a_choice(self):
        self.consent(); self.capture()
        report = self.call("skill_decision_review")
        self.assertEqual(self.allowed(report), ["keep"])
        self.assertEqual(report["outcome_status"], "SUCCESS_CANDIDATE")
        self.assertIsNone(report["receipt"])
        self.assertNotIn("selected_decision", report)
        for choice in ("archive", "revise"):
            self.assertFalse(self.call("skill_decision_preview", self.request(decision=choice))["ready"])

    def test_failure_and_mixed_evidence_allow_revise_or_archive_not_keep(self):
        self.consent(); self.capture("failure")
        self.assertEqual(self.allowed(self.call("skill_decision_review")), ["revise", "archive"])
        self.capture("success", "A later manual attempt succeeded.")
        report = self.call("skill_decision_review")
        self.assertEqual(report["outcome_status"], "MIXED_EVIDENCE")
        self.assertEqual(self.allowed(report), ["revise", "archive"])
        self.assertFalse(self.call("skill_decision_preview", self.request(decision="keep"))["ready"])

    def test_exact_confirmation_records_one_core_receipt_without_events_or_writes(self):
        pilot = self.consent(); self.capture()
        before, events, captures = self.files(), pilot.snapshot(), pilot.skill_outcome_captures.snapshot()
        params = self.ready()
        with patch.object(self.backend, "process", side_effect=AssertionError("No command")), \
                patch.object(self.backend, "_coordinator", side_effect=AssertionError("No new coordinator")), \
                patch("subprocess.Popen", side_effect=AssertionError("No tool or model")):
            result = self.call("skill_decision_confirm", params)
        self.assertFalse(result["read_only"])
        self.assertEqual(result["events_appended"], 0)
        self.assertEqual(result["receipt"]["verification_status"], "VERIFIED")
        self.assertEqual(result["receipt"]["evidence_state"], "CURRENT")
        self.assertFalse(result["lifecycle_apply_performed"])
        self.assertFalse(result["future_apply_ready"])
        self.assertEqual(len(pilot.skill_outcome_decisions.snapshot()), 1)
        self.assertEqual(pilot.snapshot(), events)
        self.assertEqual(pilot.skill_outcome_captures.snapshot(), captures)
        self.assertEqual(self.files(), before)

    def test_archive_choice_is_not_archive_apply(self):
        pilot = self.consent(); self.capture("failure")
        before = self.files()
        result = self.call("skill_decision_confirm", self.ready("archive"))
        self.assertEqual(result["receipt"]["decision"], "archive")
        self.assertFalse(result["receipt"]["skill_mutation_performed"])
        self.assertEqual(json.loads((self.data / "skills.jsonl").read_text().splitlines()[0])["status"], "active")
        self.assertEqual(pilot.skill_lifecycle_metadata_applies.snapshot(), ())
        self.assertEqual(self.files(), before)

    def test_revise_choice_never_edits_or_replaces_the_procedure(self):
        self.consent(); self.capture("failure")
        before = self.files()
        result = self.call("skill_decision_confirm", self.ready("revise"))
        self.assertEqual(result["receipt"]["decision"], "revise")
        self.assertEqual(self.files(), before)

    def test_wrong_token_missing_ack_and_stale_fingerprint_all_refuse(self):
        pilot = self.consent(); self.capture()
        params = self.ready()
        for field, value in (("confirmation_token", "WRONG"), ("preview_fingerprint", "0" * 64),
                             ("acknowledge_decision_only", False), ("acknowledge_decision_only", 1)):
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                self.call("skill_decision_confirm", {**params, field: value})
        self.assertEqual(pilot.skill_outcome_decisions.snapshot(), ())

    def test_changed_choice_requires_new_preview_and_token(self):
        pilot = self.consent(); self.capture("failure")
        params = self.ready("revise")
        with self.assertRaises(ValueError):
            self.call("skill_decision_confirm", {**params, "decision": "archive"})
        self.assertEqual(pilot.skill_outcome_decisions.snapshot(), ())

    def test_terminal_receipt_refuses_replay_and_alternative_choice(self):
        pilot = self.consent(); self.capture("failure")
        params = self.ready("revise")
        self.call("skill_decision_confirm", params)
        before, decisions = self.files(), pilot.skill_outcome_decisions.snapshot()
        for choice in ("revise", "archive"):
            preview = self.call("skill_decision_preview", self.request(decision=choice))
            self.assertFalse(preview["ready"])
            self.assertEqual(preview["confirmation_token"], "")
            with self.assertRaises(ValueError):
                self.call("skill_decision_confirm", {**params, "decision": choice})
        report = self.call("skill_decision_review")
        self.assertEqual(report["status"], "RECORDED")
        self.assertEqual(self.allowed(report), [])
        self.assertEqual(pilot.skill_outcome_decisions.snapshot(), decisions)
        self.assertEqual(self.files(), before)

    def test_later_evidence_marks_receipt_historical_without_redeciding(self):
        pilot = self.consent(); self.capture()
        self.call("skill_decision_confirm", self.ready())
        decisions = pilot.skill_outcome_decisions.snapshot()
        self.capture("failure", "A later manual attempt failed.")
        report = self.call("skill_decision_review")
        self.assertEqual(report["outcome_status"], "MIXED_EVIDENCE")
        self.assertEqual(report["receipt"]["verification_status"], "VERIFIED")
        self.assertEqual(report["receipt"]["evidence_state"], "HISTORICAL")
        self.assertEqual(self.allowed(report), [])
        self.assertEqual(pilot.skill_outcome_decisions.snapshot(), decisions)

    def test_new_capture_invalidates_pending_preview(self):
        pilot = self.consent(); self.capture()
        params = self.ready()
        self.capture("success", "Another manual check confirmed the result.")
        with self.assertRaises(ValueError):
            self.call("skill_decision_confirm", params)
        self.assertEqual(pilot.skill_outcome_decisions.snapshot(), ())

    def test_conversation_and_workspace_scope_are_bound(self):
        pilot = self.consent(); self.capture()
        other = self.consent(OTHER); self.capture(conversation_id=OTHER)
        params = self.ready(workspace_root=str(self.root))
        for extra in ({"conversation_id": OTHER}, {"workspace_root": str(self.base)}, {"skill_id": "missing"}):
            with self.assertRaises(ValueError):
                self.call("skill_decision_confirm", {**params, **extra})
        self.assertEqual(pilot.skill_outcome_decisions.snapshot(), ())
        self.assertEqual(other.skill_outcome_decisions.snapshot(), ())

    def test_source_byte_drift_is_refused_even_when_json_semantics_match(self):
        pilot = self.consent(); self.capture()
        for name in ("skills.jsonl", "persistent_memory.json", "context_injection.json"):
            params = self.ready()
            path = self.data / name
            path.write_bytes(path.read_bytes() + b"\n")
            with self.assertRaises(ValueError):
                self.call("skill_decision_confirm", params)
        self.assertEqual(pilot.skill_outcome_decisions.snapshot(), ())

    def test_stop_invalidates_preview_but_fresh_decision_does_not_resume_capture(self):
        pilot = self.consent(); self.capture()
        params = self.ready()
        pilot.stop()
        with self.assertRaises(ValueError):
            self.call("skill_decision_confirm", params)
        events = pilot.snapshot()
        self.call("skill_decision_confirm", self.ready())
        self.assertEqual(pilot.state, "stopped")
        self.assertEqual(pilot.snapshot(), events)

    def test_decision_needs_no_extra_event_capacity(self):
        pilot = self.consent(); self.capture()
        pilot._buffer.max_events = len(pilot.snapshot())
        result = self.call("skill_decision_confirm", self.ready())
        self.assertEqual(result["events_appended"], 0)

    def test_corrupt_or_missing_capture_receipt_cannot_authorize_decision(self):
        pilot = self.consent(); self.capture()
        captures = pilot.skill_outcome_captures
        original = captures.snapshot()[0]
        captures._receipts.clear()
        self.assertEqual(self.allowed(self.call("skill_decision_review")), [])
        with patch.object(captures, "snapshot", return_value=({**original, "receipt_hash": "0" * 64},)):
            self.assertFalse(self.call("skill_decision_preview", self.request(decision="keep"))["ready"])

    def test_corrupt_decision_receipt_is_error_not_current(self):
        pilot = self.consent(); self.capture()
        self.call("skill_decision_confirm", self.ready())
        session = pilot.skill_outcome_decisions
        receipt = session.get(self.skill["id"])
        session._receipts[self.skill["id"]] = replace(receipt, receipt_hash="0" * 64)
        report = self.call("skill_decision_review")
        self.assertEqual(report["status"], "ERROR")
        self.assertEqual(report["receipt"]["verification_status"], "ERROR")
        self.assertEqual(report["receipt"]["evidence_state"], "UNAVAILABLE")

    def test_archive_restore_or_legacy_source_cannot_enter_decision_path(self):
        self.consent(); self.capture()
        for state in ("archived", "restored"):
            self.seed(state)
            report = self.call("skill_decision_review")
            self.assertEqual(self.allowed(report), [])
        (self.data / "skills.jsonl").write_text(json.dumps({"id": "legacy", "name": "Legacy", "status": "active"}) + "\n")
        self.assertEqual(self.allowed(self.call("skill_decision_review", self.request(skill_id="legacy"))), [])

    def test_missing_corrupt_and_symlink_sources_refuse_without_repair(self):
        self.consent(); self.capture()
        path = self.data / "context_injection.json"
        for content in ('{"enabled":true}', '{"enabled":false,"enabled":false}', '{"enabled":NaN}', 'broken'):
            path.write_text(content)
            before = self.files()
            self.assertFalse(self.call("skill_decision_preview", self.request(decision="keep"))["ready"])
            self.assertEqual(self.files(), before)
        path.unlink()
        self.assertFalse(self.call("skill_decision_preview", self.request(decision="keep"))["ready"])
        target = self.base / "outside-context.json"
        target.write_text('{"enabled":false}')
        path.symlink_to(target)
        self.assertEqual(self.allowed(self.call("skill_decision_review")), [])
        self.assertEqual(target.read_text(), '{"enabled":false}')

    def test_changes_observed_at_final_check_refuse_before_decision(self):
        pilot = self.consent(); self.capture()
        params = self.ready()
        original = NativeSkillDecision._check_current
        calls = 0
        def check(review):
            nonlocal calls
            calls += 1
            if calls == 3:
                path = self.data / "skills.jsonl"
                path.write_bytes(path.read_bytes() + b"\n")
            return original(review)
        with patch.object(NativeSkillDecision, "_check_current", check), self.assertRaises(ValueError):
            self.call("skill_decision_confirm", params)
        self.assertEqual(pilot.skill_outcome_decisions.snapshot(), ())

    def test_strict_rpc_surface_refuses_execution_payloads_and_invalid_choices(self):
        for method in ("skill_decision_review", "skill_decision_preview", "skill_decision_confirm"):
            for extra in ({"execute": True}, {"command": "/skills archive id"}, {"revision": "new text"},
                          {"target_path": str(self.data)}, {"skill_id": "x; /memory wipe"}, {"conversation_id": ""}):
                with self.subTest(method=method, extra=extra), self.assertRaises(ValueError):
                    self.call(method, self.request(**extra))
        for value in (None, [], True, "keep;anything", "KEEP", "keep ", "/archive"):
            with self.assertRaises(ValueError):
                self.call("skill_decision_preview", self.request(decision=value))

    def test_busy_and_closing_bridge_refuse_without_decision(self):
        pilot = self.consent(); self.capture()
        params = self.ready()
        self.backend.busy.acquire()
        try:
            with self.assertRaises(ValueError):
                self.call("skill_decision_confirm", params)
        finally:
            self.backend.busy.release()
        self.backend.closing.set()
        with self.assertRaises(ValueError):
            self.call("skill_decision_confirm", params)
        self.assertEqual(pilot.skill_outcome_decisions.snapshot(), ())

    def test_restart_expires_decision_and_does_not_reconstruct_from_durable_skill(self):
        self.consent(); self.capture()
        params = self.ready()
        self.call("skill_decision_confirm", params)
        before = self.files()
        self.backend.sessions.clear()
        report = self.call("skill_decision_review")
        self.assertIsNone(report["receipt"])
        self.assertEqual(report["decision_count"], 0)
        self.assertEqual(report["pilot_state"], "not_started")
        with self.assertRaises(ValueError):
            self.call("skill_decision_confirm", params)
        self.assertEqual(self.files(), before)
