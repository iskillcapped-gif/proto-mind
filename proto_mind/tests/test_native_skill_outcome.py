from __future__ import annotations

import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from proto_mind.experience_pilot import EXPERIENCE_PILOT_ATTR, SupervisedExperiencePilot
from proto_mind.native_bridge import NativeBackend
from proto_mind.native_skill_outcome import NativeSkillOutcome
from proto_mind.tests.test_flow import (
    build_test_applied_procedural_skill, build_test_durably_archived_procedural_skill,
    build_test_restored_procedural_skill,
)
from proto_mind.tests.test_native import FakeSubscription


CONVERSATION = "00000000-0000-0000-0000-000000000001"
OTHER = "00000000-0000-0000-0000-000000000002"


class NativeSkillOutcomeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.root = self.base / "project"
        self.data = self.root / "proto_mind/data"
        self.data.mkdir(parents=True)
        self.seed("active")
        self.context = self.data / "context_injection.json"
        self.context.write_text('{"enabled":false}\n')
        self.backend = NativeBackend(self.root, self.base / "private", subscription_factory=FakeSubscription)
        self.addCleanup(self.backend.close)

    def seed(self, state):
        builder = {"active": build_test_applied_procedural_skill, "archived": build_test_durably_archived_procedural_skill,
                   "restored": build_test_restored_procedural_skill}[state]
        store, library, *_ = builder(self.base / f"seed-{state}")
        (self.data / "persistent_memory.json").write_bytes(store.persistent_path.read_bytes())
        (self.data / "skills.jsonl").write_bytes(library.skills_path.read_bytes())
        self.record = json.loads(library.skills_path.read_text().splitlines()[0])

    def consent(self, conversation=CONVERSATION, **limits):
        pilot = SupervisedExperiencePilot(self.root, **limits)
        pilot.preview(); pilot.consent(pilot.expected_consent_phrase)
        self.backend.sessions[conversation] = SimpleNamespace(**{EXPERIENCE_PILOT_ATTR: pilot})
        return pilot

    def files(self):
        return {str(path.relative_to(self.base)): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in self.base.rglob("*") if path.is_file()}

    def request(self, **extra):
        return {"conversation_id": CONVERSATION, "skill_id": self.record["id"], **extra}

    def call(self, method, params):
        return self.backend.dispatch(method, params, lambda _: self.fail("No target execution"), "fixture")

    def ready(self, **extra):
        params = self.request(outcome="success", evidence="I manually compared the expected result with the local evidence.")
        params.update(extra)
        preview = self.call("skill_outcome_preview", params)
        self.assertTrue(preview["ready"], preview["reasons"])
        return {**params, "preview_fingerprint": preview["preview_fingerprint"],
                "confirmation_token": preview["confirmation_token"], "acknowledge_manual_only": True}

    def test_view_and_preview_do_not_start_pilot_or_create_stores(self):
        before = self.files()
        with patch.object(self.backend, "process", side_effect=AssertionError("No dispatcher")), \
                patch.object(self.backend, "_coordinator", side_effect=AssertionError("No coordinator creation")), \
                patch("subprocess.Popen", side_effect=AssertionError("No model or shell")):
            report = self.call("skill_outcome_review", self.request())
            preview = self.call("skill_outcome_preview", self.request(outcome="success", evidence="Manual result."))
        self.assertTrue(report["source_eligible"])
        self.assertFalse(report["capture_available"])
        self.assertEqual(report["pilot_state"], "not_started")
        self.assertFalse(preview["ready"])
        self.assertEqual(preview["confirmation_token"], "")
        self.assertEqual(self.backend.sessions, {})
        self.assertEqual(self.files(), before)

    def test_existing_stopped_or_unconsented_pilot_is_not_reenabled(self):
        pilot = self.consent()
        for state in ("disabled", "previewed", "stopped", "expired"):
            pilot._state = state
            report = self.call("skill_outcome_review", self.request())
            self.assertFalse(report["capture_available"])
            self.assertEqual(pilot.state, state)
            self.assertEqual(pilot.snapshot(), ())

    def test_success_capture_appends_exact_core_batch_without_file_or_target_mutation(self):
        pilot = self.consent()
        before = self.files()
        params = self.ready()
        self.assertEqual(pilot.snapshot(), ())
        with patch.object(self.backend, "process", side_effect=AssertionError("No command")), \
                patch("subprocess.Popen", side_effect=AssertionError("No model or shell")):
            result = self.call("skill_outcome_confirm", params)
        self.assertEqual(result["events_appended"], 4)
        self.assertFalse(result["read_only"])
        self.assertTrue(result["no_execution"])
        self.assertEqual(len(pilot.snapshot()), 4)
        self.assertEqual(result["receipt"]["verification_status"], "VERIFIED")
        self.assertTrue(result["receipt"]["operator_reported"])
        self.assertFalse(result["receipt"]["execution_performed_by_proto_mind"])
        review = self.call("skill_inspection", self.request())
        self.assertEqual(review["outcome"]["status"], "SUCCESS_CANDIDATE")
        self.assertEqual(self.files(), before)

    def test_failure_and_correction_remain_operator_reported_failure(self):
        pilot = self.consent()
        result = self.call("skill_outcome_confirm", self.ready(outcome="failure", evidence="I corrected the path after the manual check failed."))
        self.assertEqual(result["receipt"]["outcome"], "failure")
        self.assertEqual(pilot.snapshot()[-1]["event_type"], "tool_failed")
        self.assertEqual(self.call("skill_inspection", self.request())["outcome"]["status"], "FAILURE_CANDIDATE")

    def test_separate_conflicting_outcomes_stay_mixed_not_auto_decided(self):
        pilot = self.consent()
        self.call("skill_outcome_confirm", self.ready())
        self.call("skill_outcome_confirm", self.ready(outcome="failure", evidence="A later manual use failed."))
        review = self.call("skill_inspection", self.request())
        self.assertEqual(review["outcome"]["status"], "MIXED_EVIDENCE")
        self.assertFalse(review["outcome"]["automatic_decision_allowed"])
        self.assertEqual(pilot.skill_outcome_decisions.snapshot(), ())

    def test_exact_token_fingerprint_and_manual_acknowledgement_are_all_required(self):
        pilot = self.consent()
        params = self.ready()
        before = self.files()
        for key, value in (("confirmation_token", "WRONG"), ("preview_fingerprint", "stale"),
                           ("acknowledge_manual_only", False), ("acknowledge_manual_only", 1)):
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                self.call("skill_outcome_confirm", {**params, key: value})
            self.assertEqual(pilot.snapshot(), ())
        self.assertEqual(self.files(), before)

    def test_edited_evidence_or_outcome_invalidates_preview(self):
        pilot = self.consent()
        params = self.ready()
        for extra in ({"evidence": "Changed result."}, {"outcome": "failure"}, {"evidence": params["evidence"] + " "}):
            with self.assertRaises(ValueError):
                self.call("skill_outcome_confirm", {**params, **extra})
            self.assertEqual(pilot.snapshot(), ())

    def test_conversation_and_workspace_scope_drift_is_refused(self):
        pilot = self.consent()
        other = self.consent(OTHER)
        params = self.ready(workspace_root=str(self.root))
        for extra in ({"conversation_id": OTHER}, {"workspace_root": str(self.base)}, {"skill_id": "missing"}):
            with self.assertRaises(ValueError):
                self.call("skill_outcome_confirm", {**params, **extra})
        self.assertEqual(pilot.snapshot(), ())
        self.assertEqual(other.snapshot(), ())

    def test_source_byte_drift_refuses_confirmation_even_if_json_semantics_match(self):
        pilot = self.consent()
        for name in ("skills.jsonl", "persistent_memory.json", "context_injection.json"):
            params = self.ready()
            path = self.data / name
            path.write_bytes(path.read_bytes() + b"\n")
            with self.assertRaises(ValueError):
                self.call("skill_outcome_confirm", params)
        self.assertEqual(pilot.snapshot(), ())

    def test_intervening_capture_invalidates_old_preview(self):
        pilot = self.consent()
        pending = self.ready(evidence="Earlier form awaiting confirmation.")
        self.call("skill_outcome_confirm", self.ready(evidence="A different manual result."))
        snapshot = pilot.snapshot()
        with self.assertRaises(ValueError):
            self.call("skill_outcome_confirm", pending)
        self.assertEqual(pilot.snapshot(), snapshot)

    def test_consent_revocation_refuses_without_restarting_pilot(self):
        pilot = self.consent()
        params = self.ready()
        pilot.stop()
        with self.assertRaises(ValueError):
            self.call("skill_outcome_confirm", params)
        self.assertEqual(pilot.state, "stopped")
        self.assertEqual(pilot.snapshot(), ())

    def test_context_enabled_or_missing_is_refused_without_repair(self):
        pilot = self.consent()
        params = self.ready()
        for settings in ('{"enabled":true}', '{"enabled":"false"}', '{"enabled":false,"enabled":false}', '{"enabled":false,"x":NaN}'):
            self.context.write_text(settings)
            before = self.files()
            with self.assertRaises(ValueError):
                self.call("skill_outcome_confirm", params)
            self.assertEqual(self.files(), before)
        self.context.unlink()
        with self.assertRaises(ValueError):
            self.call("skill_outcome_confirm", params)
        self.assertFalse(self.context.exists())
        self.assertEqual(pilot.snapshot(), ())

    def test_replay_and_lost_response_do_not_append_second_batch(self):
        pilot = self.consent()
        params = self.ready()
        first = self.call("skill_outcome_confirm", params)
        before, events = self.files(), pilot.snapshot()
        with self.assertRaises(ValueError):
            self.call("skill_outcome_confirm", params)
        report = self.call("skill_outcome_review", self.request())
        self.assertEqual(report["receipts"][0], first["receipt"])
        self.assertEqual(pilot.snapshot(), events)
        self.assertEqual(self.files(), before)

    def test_full_event_buffer_refuses_without_partial_capture(self):
        pilot = self.consent(max_events=3)
        report = self.call("skill_outcome_review", self.request())
        self.assertFalse(report["capture_available"])
        self.assertEqual(pilot.snapshot(), ())

    def test_core_byte_limit_refuses_without_partial_batch_or_receipt(self):
        pilot = self.consent(max_bytes=10)
        params = self.ready()
        before = self.files()
        with self.assertRaises(ValueError):
            self.call("skill_outcome_confirm", params)
        self.assertEqual(pilot.snapshot(), ())
        self.assertEqual(pilot.skill_outcome_captures.snapshot(), ())
        self.assertEqual(pilot.state, "stopped")
        self.assertEqual(self.files(), before)

    def test_sixteen_receipt_limit_is_preserved(self):
        pilot = self.consent()
        for index in range(16):
            self.call("skill_outcome_confirm", self.ready(evidence=f"Distinct manual result {index}."))
        self.assertFalse(self.call("skill_outcome_review", self.request())["capture_available"])
        self.assertEqual(len(pilot.skill_outcome_captures.snapshot()), 16)
        self.assertEqual(len(pilot.snapshot()), 64)

    def test_archived_restored_and_legacy_skills_are_not_repaired_or_captured(self):
        pilot = self.consent()
        for state in ("archived", "restored"):
            self.seed(state)
            before = self.files()
            report = self.call("skill_outcome_review", self.request())
            self.assertFalse(report["source_eligible"])
            self.assertEqual(self.files(), before)
        self.record = {"id": "legacy", "status": "active", "uses": 500}
        (self.data / "skills.jsonl").write_text(json.dumps(self.record) + "\n")
        self.assertFalse(self.call("skill_outcome_review", self.request())["source_eligible"])
        self.assertEqual(pilot.snapshot(), ())

    def test_malformed_duplicate_nonfinite_and_overlimit_sources_fail_closed(self):
        self.consent()
        path = self.data / "skills.jsonl"
        original = path.read_bytes()
        for data in (b"{broken", original * 2, b'{"id":"x","id":"y"}\n', b'{"id":"x","uses":NaN}\n'):
            path.write_bytes(data)
            before = self.files()
            self.assertEqual(self.call("skill_outcome_review", self.request())["status"], "ERROR")
            self.assertEqual(self.files(), before)
        path.write_bytes(original)
        with patch("proto_mind.native_skill_outcome.MAX_SOURCE_RECORDS", 0):
            self.assertEqual(self.call("skill_outcome_review", self.request())["status"], "ERROR")

    def test_symlink_source_and_data_directory_are_refused(self):
        self.consent()
        path = self.data / "skills.jsonl"
        target = self.base / "external.jsonl"
        path.rename(target); path.symlink_to(target)
        self.assertEqual(self.call("skill_outcome_review", self.request())["status"], "ERROR")
        path.unlink(); target.rename(path)
        target = self.base / "outside-data"
        self.data.rename(target); self.data.symlink_to(target, target_is_directory=True)
        self.assertEqual(self.call("skill_outcome_review", self.request())["status"], "ERROR")

    def test_change_detected_immediately_before_capture_does_not_append(self):
        pilot = self.consent()
        params = self.ready()
        original = NativeSkillOutcome._check_sources
        calls = []
        def changed(review):
            calls.append(True)
            if len(calls) == 3:
                self.context.write_text('{"enabled":true}')
            return original(review)
        with patch.object(NativeSkillOutcome, "_check_sources", changed), self.assertRaises(ValueError):
            self.call("skill_outcome_confirm", params)
        self.assertEqual(pilot.snapshot(), ())

    def test_strict_rpc_surface_rejects_commands_invalid_selectors_and_text(self):
        self.consent()
        for extra in ({"conversation_id": ""}, {"conversation_id": "bad"}, {"skill_id": "../../file"}, {"workspace_root": 5},
                      {"expected_sha256": "wrong"}, {"command": "/action run all"}, {"execute": True}, {"operation": "restore"}):
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                self.call("skill_outcome_review", self.request(**extra))
        for evidence in ("", " ", "x" * 801, "\x00bad", "\ud800", 1):
            with self.assertRaises(ValueError):
                self.call("skill_outcome_preview", self.request(outcome="success", evidence=evidence))

    def test_arbitrary_text_is_only_operator_evidence_not_dispatched(self):
        self.consent()
        evidence = "I manually inspected /memory remember hello; no command should run && never auto-execute."
        with patch.object(self.backend, "process", side_effect=AssertionError("No dispatcher")):
            result = self.call("skill_outcome_confirm", self.ready(evidence=evidence))
        self.assertTrue(result["no_execution"])

    def test_evidence_is_redacted_by_existing_core_before_events_or_receipts(self):
        pilot = self.consent()
        secret = "sk-" + "x" * 48
        result = self.call("skill_outcome_confirm", self.ready(evidence=f"Checked with token {secret}; result matched."))
        self.assertNotIn(secret, json.dumps(result))
        self.assertNotIn(secret, json.dumps(pilot.snapshot()))
        self.assertNotIn(secret, json.dumps(pilot.skill_outcome_captures.snapshot()))

    def test_busy_or_closing_bridge_refuses_before_any_capture(self):
        pilot = self.consent()
        params = self.ready()
        self.backend.busy.acquire()
        try:
            with self.assertRaises(ValueError):
                self.call("skill_outcome_confirm", params)
        finally:
            self.backend.busy.release()
        self.backend.closing.set()
        with self.assertRaises(ValueError):
            self.call("skill_outcome_confirm", params)
        self.assertEqual(pilot.snapshot(), ())

    def test_restart_expires_receipts_consent_and_pending_confirmation(self):
        self.consent()
        params = self.ready()
        self.call("skill_outcome_confirm", params)
        before = self.files()
        self.backend.close()
        self.backend = NativeBackend(self.root, self.base / "private", subscription_factory=FakeSubscription)
        self.addCleanup(self.backend.close)
        report = self.call("skill_outcome_review", self.request())
        self.assertEqual(report["receipts"], [])
        self.assertEqual(report["pilot_state"], "not_started")
        with self.assertRaises(ValueError):
            self.call("skill_outcome_confirm", params)
        self.assertEqual(self.files(), before)


if __name__ == "__main__":
    unittest.main()
