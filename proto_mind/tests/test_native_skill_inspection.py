from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from proto_mind.experience_pilot import EXPERIENCE_PILOT_ATTR, SupervisedExperiencePilot
from proto_mind.native_bridge import NativeBackend
from proto_mind.native_library import NativeLibrary
from proto_mind.tests.test_flow import (
    build_test_applied_procedural_skill, build_test_durably_archived_procedural_skill,
    build_test_procedural_skill_outcome_events, build_test_restored_procedural_skill,
    build_test_restored_skill_outcome_events,
)
from proto_mind.tests.test_native import FakeSubscription


CONVERSATION = "00000000-0000-0000-0000-000000000001"
OTHER = "00000000-0000-0000-0000-000000000002"


class NativeSkillInspectionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.root = self.base / "project"
        self.data = self.root / "proto_mind/data"
        self.data.mkdir(parents=True)
        self.skills = self.data / "skills.jsonl"
        self.memories = self.data / "persistent_memory.json"
        self.seed("active")
        (self.data / "context_injection.json").write_text('{"enabled":false}\n')
        self.backend = NativeBackend(self.root, self.base / "private", subscription_factory=FakeSubscription)
        self.addCleanup(self.backend.close)

    def seed(self, state):
        builder = {"active": build_test_applied_procedural_skill, "archived": build_test_durably_archived_procedural_skill,
                   "restored": build_test_restored_procedural_skill}[state]
        source = builder(self.base / f"seed-{state}")
        store, library = source[:2]
        self.memories.write_bytes(store.persistent_path.read_bytes())
        self.skills.write_bytes(library.skills_path.read_bytes())
        self.record = json.loads(self.skills.read_text().splitlines()[0])

    def files(self):
        return {str(path.relative_to(self.base)): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in self.base.rglob("*") if path.is_file()}

    def call(self, **extra):
        return self.backend.dispatch("skill_inspection", {"conversation_id": CONVERSATION, "skill_id": self.record["id"], **extra},
                                     lambda _: self.fail("No execution events"), "fixture")

    def events(self, events):
        pilot = SupervisedExperiencePilot(self.root)
        pilot.snapshot = lambda: tuple(event.to_dict() if hasattr(event, "to_dict") else deepcopy(event) for event in events)
        owner = SimpleNamespace(**{EXPERIENCE_PILOT_ATTR: pilot})
        self.backend.sessions[CONVERSATION] = owner
        return pilot

    def write_record(self):
        self.skills.write_text(json.dumps(self.record) + "\n")

    def test_durable_active_skill_is_inspectable_without_pilot_or_store_initialization(self):
        before = self.files()
        with patch.object(self.backend, "process", side_effect=AssertionError("No command dispatch")), \
                patch("subprocess.Popen", side_effect=AssertionError("No shell/model")), \
                patch("proto_mind.skill_lifecycle_audit.MemoryStore", side_effect=AssertionError("No initializing store")), \
                patch("proto_mind.skill_lifecycle_audit.SkillLibrary", side_effect=AssertionError("No initializing library")):
            report = self.call()
        self.assertEqual(report["lifecycle"]["state"], "active_verified")
        self.assertEqual(report["outcome"]["status"], "UNAVAILABLE")
        self.assertFalse(report["outcome"]["pilot_available"])
        self.assertEqual([item["kind"] for item in report["transitions"]], ["apply"])
        self.assertEqual(self.backend.sessions, {})
        self.assertEqual(self.files(), before)

    def test_inspection_without_selected_conversation_is_durable_only(self):
        self.events(build_test_procedural_skill_outcome_events(self.record, outcome="success"))
        report = self.call(conversation_id="")
        self.assertEqual(report["lifecycle"]["state"], "active_verified")
        self.assertFalse(report["outcome"]["pilot_available"])

    def test_missing_skill_and_missing_stores_are_not_created(self):
        before = self.files()
        self.assertEqual(self.call(skill_id="missing")["status"], "NOT_FOUND")
        self.assertEqual(self.files(), before)
        self.skills.unlink(); self.memories.unlink()
        before = self.files()
        self.assertEqual(self.call()["store_hashes"], {"skills.jsonl": "missing", "persistent_memory.json": "missing"})
        self.assertEqual(self.files(), before)

    def test_success_failure_and_mixed_results_use_existing_exact_evidence(self):
        for outcome, expected in (("success", "SUCCESS_CANDIDATE"), ("failure", "FAILURE_CANDIDATE"), ("mixed", "MIXED_EVIDENCE")):
            with self.subTest(outcome=outcome):
                pilot = self.events(build_test_procedural_skill_outcome_events(self.record, outcome=outcome))
                before, events = self.files(), pilot.snapshot()
                report = self.call()
                self.assertEqual(report["outcome"]["status"], expected, report)
                self.assertGreater(report["outcome"]["signal_count"], 0)
                self.assertFalse(report["outcome"]["automatic_decision_allowed"])
                self.assertEqual(pilot.snapshot(), events)
                self.assertEqual(self.files(), before)

    def test_only_selected_conversation_events_are_considered(self):
        self.events(build_test_procedural_skill_outcome_events(self.record, outcome="success"))
        before = self.files()
        report = self.call(conversation_id=OTHER)
        self.assertEqual(report["outcome"]["status"], "UNAVAILABLE")
        self.assertFalse(report["project_isolation_enforced"])
        self.assertNotIn(OTHER, self.backend.sessions)
        self.assertEqual(self.files(), before)

    def test_usage_counter_and_unrelated_events_do_not_prove_success(self):
        self.record["uses"] = 900
        self.write_record()
        events = build_test_procedural_skill_outcome_events(self.record, outcome="success")
        events[2].payload["skill_provenance_id"] = "wrong-provenance"
        self.events(events)
        report = self.call()
        self.assertEqual(report["uses_display"], "900")
        self.assertEqual(report["outcome"]["status"], "NEEDS_MORE_EVIDENCE")
        self.assertEqual(report["outcome"]["signal_count"], 0)

    def test_claimed_automatic_execution_is_rejected_as_evidence(self):
        self.events(build_test_procedural_skill_outcome_events(self.record, outcome="success", execution_performed_by_proto_mind=True))
        report = self.call()
        self.assertEqual(report["status"], "ERROR")
        self.assertTrue(report["no_execution"])
        self.assertEqual(report["outcome"]["status"], "ERROR")

    def test_legacy_record_remains_unprovenanced_without_invented_history(self):
        self.record = {"id": "legacy", "name": "Legacy procedure", "status": "active", "uses": 50}
        self.write_record()
        report = self.call()
        self.assertEqual(report["lifecycle"]["state"], "unprovenanced")
        self.assertEqual(report["transitions"], [])
        self.assertEqual(report["outcome"]["status"], "UNAVAILABLE")
        self.assertEqual(report["status"], "WARN")

    def test_status_only_archive_does_not_invent_a_reason(self):
        self.record["status"] = "archived"
        self.write_record()
        report = self.call()
        self.assertEqual(report["lifecycle"]["state"], "archived_ambiguous")
        self.assertEqual(report["transitions"], [])
        self.assertFalse(report["lifecycle"]["outcome_archive_proven"])

    def test_verified_archive_displays_durable_transition_not_live_success(self):
        self.seed("archived")
        before = self.files()
        report = self.call()
        self.assertEqual(report["lifecycle"]["state"], "archived_verified")
        self.assertEqual([row["kind"] for row in report["transitions"]], ["apply", "archive"])
        self.assertGreater(report["transitions"][-1]["evidence_count"], 0)
        self.assertEqual(report["outcome"]["status"], "UNAVAILABLE")
        self.assertFalse(report["history_complete"])
        self.assertEqual(self.files(), before)

    def test_restore_recovers_envelope_evidence_not_original_receipt(self):
        self.seed("restored")
        before = self.files()
        with patch("proto_mind.skill_lifecycle_audit.MemoryStore", side_effect=AssertionError("No store init")), \
                patch("proto_mind.skill_lifecycle_restore_receipt_audit.SkillLibrary", side_effect=AssertionError("No store init")):
            report = self.call()
        self.assertEqual(report["lifecycle"]["state"], "active_restored_verified", report)
        self.assertEqual([row["kind"] for row in report["transitions"]], ["apply", "archive", "restore"])
        self.assertTrue(report["restore"]["current_state_verified"])
        self.assertEqual(report["restore"]["process_receipt_status"], "NOT_AVAILABLE")
        self.assertFalse(report["restore"]["original_apply_receipt_reconstructed"])
        self.assertEqual(report["outcome"]["status"], "NEEDS_POST_RESTORE_EVIDENCE")
        self.assertEqual(self.files(), before)

    def test_restore_excludes_old_and_unbound_results(self):
        self.seed("restored")
        for values, key in (({"after_restore": False}, "pre_restore_use_count"), ({"exact_restore_binding": False}, "unbound_post_restore_use_count")):
            with self.subTest(values=values):
                self.events(build_test_restored_skill_outcome_events(self.record, **values))
                before = self.files()
                with patch("proto_mind.skill_lifecycle_audit.MemoryStore", side_effect=AssertionError("No hidden store read")):
                    report = self.call()
                self.assertEqual(report["outcome"]["status"], "NEEDS_POST_RESTORE_EVIDENCE", report)
                self.assertEqual(report["outcome"][key], 1)
                self.assertEqual(report["outcome"]["signal_count"], 0)
                self.assertEqual(self.files(), before)

    def test_exact_post_restore_evidence_is_candidate_only(self):
        self.seed("restored")
        self.events(build_test_restored_skill_outcome_events(self.record))
        before = self.files()
        report = self.call()
        self.assertEqual(report["outcome"]["status"], "POST_RESTORE_SUCCESS_CANDIDATE", report)
        self.assertFalse(report["outcome"]["post_restore_capture_installed"])
        self.assertFalse(report["automatic_action"])
        self.assertEqual(self.files(), before)

    def test_tampered_lifecycle_never_shows_verified_transitions(self):
        self.seed("restored")
        self.record["lifecycle"]["metadata_hash"] = "f" * 64
        self.write_record()
        report = self.call()
        self.assertEqual(report["lifecycle"]["state"], "invalid")
        self.assertEqual(report["status"], "ERROR")
        self.assertEqual(report["transitions"], [])
        self.assertIsNone(report["restore"])

    def test_payload_drift_blocks_outcome_verdict(self):
        self.record["body"] += "\nchanged"
        self.write_record()
        self.events(build_test_procedural_skill_outcome_events(self.record, outcome="success"))
        report = self.call()
        self.assertEqual(report["lifecycle"]["state"], "drifted")
        self.assertEqual(report["outcome"]["status"], "UNAVAILABLE")

    def test_source_missing_is_historical_not_new_provenance(self):
        self.memories.unlink()
        report = self.call()
        self.assertEqual(report["lifecycle"]["state"], "active_historical")
        self.assertIn(report["lifecycle"]["source_status"], ("unavailable", "missing"))
        self.assertEqual(report["status"], "WARN")

    def test_corrupt_duplicate_and_nonfinite_stores_fail_closed(self):
        original = self.skills.read_bytes()
        for payload in (b"{broken}\n", original * 2, b'{"id":"x","id":"y"}\n', b'{"id":"x","uses":NaN}\n'):
            with self.subTest(payload=payload[:30]):
                self.skills.write_bytes(payload)
                before = self.files()
                report = self.call()
                self.assertEqual(report["status"], "ERROR")
                self.assertIsNone(report["lifecycle"])
                self.assertEqual(self.files(), before)

    def test_symlink_and_nonregular_sources_are_refused(self):
        original = self.skills.read_bytes()
        self.skills.unlink()
        target = self.base / "external.jsonl"
        target.write_bytes(original)
        self.skills.symlink_to(target)
        self.assertEqual(self.call()["status"], "ERROR")
        self.skills.unlink(); self.skills.mkdir()
        self.assertEqual(self.call()["status"], "ERROR")

    def test_bounded_records_and_events_have_no_partial_verdict(self):
        with patch("proto_mind.native_skill_inspection.MAX_SOURCE_RECORDS", 0):
            self.assertEqual(self.call()["status"], "ERROR")
        self.events(build_test_procedural_skill_outcome_events(self.record, outcome="success"))
        with patch("proto_mind.native_skill_inspection.EXPERIENCE_PILOT_MAX_EVENTS", 1):
            report = self.call()
            self.assertEqual(report["status"], "ERROR")
            self.assertEqual(report["outcome"]["signal_count"], 0)

    def test_selection_drift_uses_fresh_bytes_and_explains_change(self):
        report = self.call(expected_sha256="f" * 64)
        self.assertTrue(report["changed_since_selection"])
        self.assertEqual(report["store_hashes"]["skills.jsonl"], hashlib.sha256(self.skills.read_bytes()).hexdigest())

    def test_observed_store_change_during_review_discards_the_verdict(self):
        original = NativeLibrary._read_bytes
        calls = []

        def changed(reader, name):
            payload, info = original(reader, name)
            previous = calls.count(name)
            calls.append(name)
            return (payload + b" " if name == "skills.jsonl" and previous else payload), info

        before = self.files()
        with patch.object(NativeLibrary, "_read_bytes", changed):
            report = self.call()
        self.assertEqual(report["status"], "ERROR")
        self.assertIsNone(report["lifecycle"])
        self.assertIsNone(report["outcome"])
        self.assertIn("changed during inspection", " ".join(report["issues"]))
        self.assertEqual(self.files(), before)

    def test_symlinked_data_directory_is_not_followed(self):
        destination = self.base / "moved-fixture-data"
        self.data.rename(destination)
        self.data.symlink_to(destination, target_is_directory=True)
        before = self.files()
        self.assertEqual(self.call()["status"], "ERROR")
        self.assertEqual(self.files(), before)

    def test_workspace_alias_is_context_not_a_different_store_root(self):
        workspace = self.base / "selected-workspace"
        workspace.mkdir()
        alias = self.base / "workspace-alias"
        alias.symlink_to(workspace, target_is_directory=True)
        before = self.files()
        report = self.call(workspace_root=str(alias))
        self.assertEqual(report["workspace_path"], str(workspace.resolve()))
        self.assertEqual(report["lifecycle"]["skill_id"], self.record["id"])
        self.assertEqual(self.files(), before)

    def test_rpc_rejects_extra_operations_paths_and_invalid_selectors(self):
        before = self.files()
        for values in ({"operation": "restore"}, {"command": "/skills use x"}, {"path": "/tmp/x"},
                       {"skill_id": "../x"}, {"conversation_id": []}, {"expected_sha256": "bad"}, {"workspace_root": []}):
            with self.subTest(values=values), self.assertRaises(ValueError):
                self.call(**values)
        self.assertEqual(self.files(), before)

    def test_busy_or_closing_bridge_refuses_inspection(self):
        self.backend.busy.acquire()
        try:
            with self.assertRaisesRegex(ValueError, "active turn"):
                self.call()
        finally:
            self.backend.busy.release()
        self.backend.closing.set()
        with self.assertRaises(ValueError):
            self.call()

    def test_restart_discards_process_outcomes_but_preserves_durable_state(self):
        self.events(build_test_procedural_skill_outcome_events(self.record, outcome="success"))
        self.assertEqual(self.call()["outcome"]["status"], "SUCCESS_CANDIDATE")
        self.backend.sessions.clear()
        before = self.files()
        report = self.call()
        self.assertEqual(report["lifecycle"]["state"], "active_verified")
        self.assertEqual(report["outcome"]["status"], "UNAVAILABLE")
        self.assertEqual(self.files(), before)
