"""Manual assessment on disposable records, with no model/tool authority."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

from proto_mind import native_bridge as bridge
from proto_mind.native_desk import capture_artifacts
from proto_mind import native_review as review
from proto_mind.native_work_sessions import WorkSessionError, workspace_identity
from proto_mind.config import ProtoMindConfig
from proto_mind.observer import Observer
from proto_mind.tests.test_native import FakeSubscription


class NativeReviewTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="proto-native-review-")
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name).resolve()
        self.root, self.state, self.workspace = (self.base / name for name in ("core", "private", "workspace"))
        self.workspace.mkdir()
        self.file = self.workspace / "result.py"
        self.file.write_text("print('fixture result')\n")
        self.backend = bridge.NativeBackend(self.root, self.state, subscription_factory=FakeSubscription)
        self.addCleanup(self.backend.close)
        config = patch.object(ProtoMindConfig, "from_env", return_value=ProtoMindConfig(data_dir=self.root / "proto_mind/data"))
        config.start(); self.addCleanup(config.stop)
        self.conversation = str(uuid4())
        self.reader = self.backend.workspace({"workspace_root": str(self.workspace)})

    def files(self):
        return {str(path.relative_to(self.base)): path.read_bytes() for path in self.base.rglob("*")
                if path.is_file() and not path.is_symlink()}

    def finished(self, *, criteria=None, capture=True, observed=True):
        values = ["Result is readable", "Required cases checked"] if criteria is None else criteria
        with self.backend.work_sessions.begin(run_id=str(uuid4()), conversation_id=self.conversation,
                text="Fixture goal", provider="mock", model="", effort="", mode="chat",
                workspace=workspace_identity(self.workspace), sources=[], criteria=values) as run:
            run.dispatch()
            if observed:
                run.observe({"event": "agent_activity", "item": {"id": "file", "kind": "fileChange", "status": "completed",
                    "paths": ["result.py"], "diff_preview": "fixture diff (not executed)"}})
            return run.complete("Model claim, not acceptance", artifacts=capture_artifacts(run.record, self.reader) if capture else None)

    def params(self, run, **changes):
        return {"run": {"run_id": run["id"], "fingerprint": run["fingerprint"]},
                "conversation_id": self.conversation, "workspace_root": str(self.workspace),
                "review": {"decision": "accepted", "checks": ["met"] * len((run.get("success_criteria") or {}).get("items", [])), "note": "Checked manually"}, **changes}

    def preview(self, run, **changes):
        return self.backend.dispatch("review_preview", self.params(run, **changes), lambda _: self.fail("No events"), "preview")

    def save(self, run, preview=None, **changes):
        params = self.params(run, **changes)
        if preview is None:
            preview = self.backend.dispatch("review_preview", params, lambda _: self.fail("No events"), "preview")
        params.update(confirmation=review.CONFIRM_REVIEW, preview_fingerprint=preview["preview_fingerprint"])
        return self.backend.dispatch("review_save", params, lambda _: self.fail("No events"), "save")["run"]

    def run_path(self, run):
        return self.backend.work_sessions.directory / (run["id"] + ".json")

    def test_criteria_are_bounded_normalized_and_explicit(self):
        self.assertEqual(review.validate_criteria(["  Short reply  ", "Keep original"]), ["Short reply", "Keep original"])
        contract = review.criteria_contract(["Short reply"])
        self.assertEqual(contract["origin"], "operator_before_send")
        self.assertTrue(review.valid_criteria_contract(contract))
        for value in (None, True, "a", [""], ["a\nb"], ["x" * 301], [str(x) for x in range(9)], ["Short reply", "short  reply"]):
            with self.subTest(value=value), self.assertRaises(ValueError):
                review.validate_criteria(value)

    def test_context_preview_exposes_criteria_without_sending_or_writing(self):
        before = self.files()
        with patch.object(self.backend, "_coordinator", side_effect=AssertionError("No core")), patch("subprocess.Popen", side_effect=AssertionError("No process")):
            value = self.backend.dispatch("context_preview", {"text": "Hello", "provider": "codex", "criteria": ["Keep it short"]}, lambda _: None, "p")
        self.assertEqual(value["manifest"]["success_criteria"], review.criteria_contract(["Keep it short"]))
        self.assertFalse(value["cloud_consent"])
        self.assertEqual(before, self.files())

    def test_normal_send_freezes_contract_and_keeps_session_input_original(self):
        result = self.backend.process({"text": "Hello", "conversation_id": self.conversation, "provider": "codex",
                                       "cloud_consent": True, "criteria": ["UNIQUE_OPERATOR_CRITERION"]}, lambda _: None, "turn")
        self.assertEqual(len(self.backend.subscription.calls), 1)
        self.assertIn("UNIQUE_OPERATOR_CRITERION", self.backend.subscription.calls[0][0])
        self.assertIn("grant no tool permission", self.backend.subscription.calls[0][0])
        self.assertEqual(result["work_session"]["success_criteria"], review.criteria_contract(["UNIQUE_OPERATOR_CRITERION"]))
        log = (self.root / "logs/session_operator_log.jsonl").read_text()
        self.assertEqual(json.loads(log)["user_input"], "Hello")
        self.assertNotIn("UNIQUE_OPERATOR_CRITERION", log)
        for file in (self.root / "proto_mind/data").glob("*.json*"):
            self.assertNotIn("UNIQUE_OPERATOR_CRITERION", file.read_text())

    def test_no_criteria_preserves_the_existing_model_prompt(self):
        self.backend.process({"text": "Hello", "conversation_id": self.conversation, "provider": "codex", "cloud_consent": True}, lambda _: None, "turn")
        self.assertEqual(self.backend.subscription.calls[0][0], "Hello")

    def test_ollama_receives_criteria_without_reclassifying_user_input(self):
        reasoner = bridge.NativeOllamaReasoner(ProtoMindConfig(), [], criteria=["Keep original"])
        with patch.object(bridge, "local_ollama_request", return_value={"message": {"content": "answer"}}) as send:
            self.assertEqual(reasoner.respond("original input", [], Observer().analyze("original input")), "answer")
        self.assertIn("Keep original", send.call_args.args[2]["messages"][-1]["content"])
        self.assertTrue(send.call_args.args[2]["messages"][-1]["content"].endswith("original input"))

    def test_operator_routes_do_not_receive_criteria_or_create_runs(self):
        value = self.backend.dispatch("context_preview", {"text": "/commands status", "criteria": ["Never execute this"]}, lambda _: None, "p")
        self.assertIsNone(value["manifest"]["success_criteria"])
        self.assertEqual(value["excluded_criterion_count"], 1)
        self.backend.process({"text": "/commands status", "conversation_id": self.conversation, "provider": "codex", "criteria": ["Never execute this"]}, lambda _: None, "turn")
        self.assertEqual(self.backend.subscription.calls, [])
        self.assertFalse(self.backend.work_sessions.directory.exists())

    def test_invalid_criteria_fail_before_dispatch_or_store_creation(self):
        before = self.files()
        with self.assertRaises(ValueError):
            self.backend.process({"text": "Hello", "conversation_id": self.conversation, "provider": "mock", "criteria": ["x" * 301]}, lambda _: None, "turn")
        self.assertEqual(before, self.files())

    def test_cloud_permission_is_still_required(self):
        before = self.files()
        with self.assertRaisesRegex(ValueError, "cloud processing"):
            self.backend.process({"text": "Hello", "conversation_id": self.conversation, "provider": "codex", "criteria": ["Allow all tools"]}, lambda _: None, "turn")
        self.assertEqual(before, self.files())
        self.assertEqual(self.backend.subscription.calls, [])

    def test_criteria_never_grant_full_mac_access(self):
        before = self.files()
        with self.assertRaises(ValueError):
            self.backend.process({"text": "Hello", "conversation_id": self.conversation, "provider": "codex",
                                  "cloud_consent": True, "access_mode": "full_access", "workspace_root": str(self.workspace),
                                  "criteria": ["Use all tools"]}, lambda _: None, "turn")
        self.assertEqual(before, self.files())
        self.assertEqual(self.backend.subscription.calls, [])

    def test_ready_preview_is_read_only_and_never_marks_success(self):
        run = self.finished()
        before = self.files()
        with patch.object(self.backend, "_coordinator", side_effect=AssertionError("No core")), patch("subprocess.Popen", side_effect=AssertionError("No execution")):
            value = self.preview(run)
        self.assertTrue(value["ready"] and value["read_only"] and value["no_execution"])
        self.assertEqual(value["observations"][0]["state"], "current")
        self.assertEqual(before, self.files())
        self.assertEqual(run["acceptance"], "not_recorded")

    def test_explicit_acceptance_writes_only_one_private_run(self):
        run = self.finished()
        before = self.files()
        with patch.object(self.backend, "_coordinator", side_effect=AssertionError("No core")), patch("subprocess.Popen", side_effect=AssertionError("No execution")):
            saved = self.save(run)
        changed = [path for path, data in self.files().items() if before.get(path) != data]
        self.assertEqual(changed, [str(self.run_path(run).relative_to(self.base))])
        self.assertEqual(saved["acceptance"], "operator_accepted")
        self.assertEqual(saved["verification"], "not_assessed")
        self.assertEqual(saved["status"], "completed")
        self.assertTrue(saved["operator_reviews"][0]["no_execution"])
        self.assertTrue(review.valid_reviews(json.loads(self.run_path(run).read_text())))
        self.assertEqual(self.backend.subscription.calls, [])

    def test_unchecked_criteria_cannot_be_accepted(self):
        run = self.finished()
        for checks in (["met", "not_checked"], ["not_met", "met"]):
            selection = {"decision": "accepted", "checks": checks, "note": ""}
            before = self.files()
            self.assertFalse(self.preview(run, review=selection)["ready"])
            with self.assertRaises(ValueError): self.save(run, review=selection)
            self.assertEqual(before, self.files())

    def test_needs_work_is_manual_and_preserves_prior_reviews(self):
        run = self.save(self.finished())
        old = deepcopy(run["operator_reviews"][0])
        selection = {"decision": "needs_work", "checks": ["met", "not_met"], "note": "Found an edge case"}
        saved = self.save(run, review=selection)
        self.assertEqual(saved["acceptance"], "operator_needs_work")
        self.assertEqual(saved["operator_reviews"][0], old)
        self.assertEqual(saved["operator_reviews"][1]["previous_receipt_hash"], old["receipt_hash"])
        self.assertEqual(saved["status"], "completed")

    def test_changed_result_cannot_be_accepted_or_silently_rebaselined(self):
        run = self.finished(); before_run = self.run_path(run).read_bytes()
        self.file.write_text("changed after reply")
        value = self.preview(run)
        self.assertFalse(value["ready"])
        self.assertEqual(value["observations"][0]["state"], "changed")
        with self.assertRaises(ValueError): self.save(run, value)
        self.assertEqual(self.run_path(run).read_bytes(), before_run)

    def test_file_changes_between_preview_and_confirmation_refuse(self):
        run = self.finished(); value = self.preview(run)
        self.file.write_text("later")
        before = self.files()
        with self.assertRaises(ValueError): self.save(run, value)
        self.assertEqual(before, self.files())

    def test_rework_preview_is_also_bound_to_exact_observed_file_bytes(self):
        run = self.finished()
        selected = {"decision": "needs_work", "checks": ["met", "not_met"], "note": "Needs a correction"}
        value = self.preview(run, review=selected)
        self.file.write_text("changed again")
        before = self.files()
        with self.assertRaisesRegex(ValueError, "Preview again"): self.save(run, value, review=selected)
        self.assertEqual(before, self.files())

    def test_different_workspace_refuses_acceptance(self):
        run = self.finished(); other = self.base / "other"; other.mkdir()
        value = self.preview(run, workspace_root=str(other))
        self.assertFalse(value["ready"] or value["workspace_matches"])
        self.assertEqual(value["observations"][0]["state"], "unavailable")

    def test_missing_or_symlinked_result_is_not_read_or_accepted(self):
        run = self.finished(); self.file.unlink()
        self.assertFalse(self.preview(run)["ready"])
        outside = self.base / "secret"; outside.write_text("not allowed")
        self.file.symlink_to(outside)
        self.assertFalse(self.preview(run)["ready"])

    def test_unknown_run_never_becomes_completed_through_review(self):
        with self.backend.work_sessions.begin(run_id=str(uuid4()), conversation_id=self.conversation, text="Interrupted",
                provider="mock", model="", effort="", mode="chat", workspace=workspace_identity(self.workspace), sources=[], criteria=["Checked"]) as run:
            run.dispatch()
        saved = self.backend.work_sessions.page(self.conversation)["runs"][0]
        before = self.files()
        self.assertFalse(self.preview(saved)["ready"])
        with self.assertRaises(ValueError): self.save(saved)
        self.assertEqual(before, self.files())
        self.assertEqual(saved["display_status"], "unknown")

    def test_unstarted_or_failed_request_cannot_be_resolved_by_either_review_decision(self):
        for dispatch in (False, True):
            with self.subTest(dispatch=dispatch):
                run_id = str(uuid4())
                with self.backend.work_sessions.begin(run_id=run_id, conversation_id=self.conversation,
                        text="No complete answer", provider="mock", model="", effort="", mode="chat",
                        workspace=workspace_identity(self.workspace), sources=[]) as writer:
                    if dispatch:
                        writer.dispatch()
                run = next(item for item in self.backend.work_sessions.page(self.conversation)["runs"]
                           if item["id"] == run_id)
                self.assertEqual(run["display_status"], "unknown" if dispatch else "not_started")
                before = self.files()
                for decision in ("accepted", "needs_work"):
                    selected = {"decision": decision, "checks": [], "note": "Acknowledged old warning"}
                    preview = self.preview(run, review=selected)
                    self.assertFalse(preview["ready"])
                    self.assertIn("incomplete_run", preview["reason_codes"])
                    with self.assertRaises(ValueError):
                        self.save(run, preview, review=selected)
                self.assertEqual(before, self.files())
                self.assertEqual(self.backend.subscription.calls, [])

    def test_legacy_run_is_not_backfilled_with_criteria_or_hashes(self):
        run = self.finished(criteria=[], capture=False)
        before = self.files()
        value = self.preview(run)
        self.assertFalse(value["ready"])
        self.assertIsNone(value["criteria"])
        self.assertEqual(before, self.files())
        saved = self.save(run, review={"decision": "needs_work", "checks": [], "note": "Legacy result needs a new scoped task"})
        self.assertNotIn("success_criteria", saved)
        self.assertNotIn("artifact_snapshot", saved)

    def test_text_only_task_can_be_manually_accepted_without_fake_artifacts(self):
        run = self.finished(observed=False)
        saved = self.save(run)
        self.assertEqual(saved["operator_reviews"][0]["observations"], [])
        self.assertEqual(saved["verification"], "not_assessed")

    def test_review_requires_exact_confirmation_and_preview_fingerprint(self):
        run = self.finished(); before = self.files()
        params = self.params(run)
        with self.assertRaisesRegex(ValueError, "confirmation"):
            self.backend.dispatch("review_save", params, lambda _: None, "s")
        with self.assertRaisesRegex(ValueError, "Preview again"):
            self.backend.dispatch("review_save", {**params, "confirmation": review.CONFIRM_REVIEW, "preview_fingerprint": "wrong"}, lambda _: None, "s")
        self.assertEqual(before, self.files())

    def test_changed_note_cannot_reuse_an_old_preview(self):
        run = self.finished(); value = self.preview(run); before = self.files()
        with self.assertRaisesRegex(ValueError, "Preview again"):
            self.save(run, value, review={"decision": "accepted", "checks": ["met", "met"], "note": "different"})
        self.assertEqual(before, self.files())

    def test_double_click_or_replay_does_not_append_twice(self):
        run = self.finished(); value = self.preview(run); self.save(run, value); before = self.files()
        with self.assertRaises(WorkSessionError): self.save(run, value)
        self.assertEqual(before, self.files())

    def test_review_belongs_to_exact_conversation_project_and_run(self):
        run = self.finished(); before = self.files()
        with self.assertRaises(WorkSessionError): self.preview(run, conversation_id=str(uuid4()))
        altered = deepcopy(run); altered["id"] = str(uuid4())
        with self.assertRaises(WorkSessionError): self.preview(altered)
        self.backend.work_sessions.project_root = str(self.base / "different-project")
        with self.assertRaises(WorkSessionError): self.preview(run)
        self.assertEqual(before, self.files())

    def test_active_writer_refuses_review_without_mutating_either_run(self):
        run = self.finished()
        with self.backend.work_sessions.begin(run_id=str(uuid4()), conversation_id=self.conversation, text="Another task",
                provider="mock", model="", effort="", mode="chat", workspace=None, sources=[]):
            before = self.files()
            with self.assertRaisesRegex(WorkSessionError, "Another Native window"):
                self.save(run)
            self.assertEqual(before, self.files())

    def test_active_backend_refuses_review(self):
        run = self.finished(); value = self.preview(run); before = self.files()
        self.backend.busy.acquire()
        try:
            with self.assertRaisesRegex(ValueError, "active turn"): self.save(run, value)
        finally: self.backend.busy.release()
        self.assertEqual(before, self.files())

    def test_disk_failure_preserves_original_evidence_and_cleans_temporary_file(self):
        run = self.finished(); value = self.preview(run); before = self.files()
        with patch("proto_mind.native_work_sessions.os.replace", side_effect=OSError("disk full")):
            with self.assertRaises(WorkSessionError): self.save(run, value)
        self.assertEqual(before, self.files())

    def test_changed_run_during_review_refuses_without_overwrite(self):
        run = self.finished(); value = self.preview(run)
        record = json.loads(self.run_path(run).read_text()); record["answer_preview"] = "Changed externally"
        self.run_path(run).write_text(json.dumps(record)); before = self.files()
        with self.assertRaises(WorkSessionError): self.save(run, value)
        self.assertEqual(before, self.files())

    def test_external_edit_after_lock_acquisition_is_not_overwritten(self):
        run = self.finished(); value = self.preview(run)
        original_make = review.make_review
        external = json.loads(self.run_path(run).read_text()); external["answer_preview"] = "External edit during review"
        changed_bytes = json.dumps(external).encode()
        def concurrent_change(record, preview):
            self.run_path(run).write_bytes(changed_bytes)
            return original_make(record, preview)
        with patch("proto_mind.native_work_sessions.make_review", side_effect=concurrent_change):
            with self.assertRaisesRegex(WorkSessionError, "outside its writer"):
                self.save(run, value)
        self.assertEqual(self.run_path(run).read_bytes(), changed_bytes)

    def test_malformed_criteria_contract_cannot_be_loaded_as_operator_fact(self):
        run = self.finished()
        value = json.loads(self.run_path(run).read_text())
        value["success_criteria"]["origin"] = "model_invented"
        self.run_path(run).write_text(json.dumps(value)); before = self.files()
        self.assertTrue(self.backend.work_sessions.page(self.conversation)["warnings"])
        self.assertEqual(before, self.files())

    def test_context_manifest_cannot_claim_different_criteria_from_the_run(self):
        run = self.finished()
        value = json.loads(self.run_path(run).read_text())
        value["context_manifest"] = {"schema": "proto_mind.native_context_manifest.v1", "read_only": True,
                                     "permission_granted": False, "success_criteria": review.criteria_contract(["Different requirement"])}
        self.run_path(run).write_text(json.dumps(value)); before = self.files()
        page = self.backend.work_sessions.page(self.conversation)
        self.assertTrue(page["warnings"])
        self.assertEqual(page["runs"], [])
        self.assertEqual(before, self.files())

    def test_tampered_receipt_and_evidence_are_rejected_without_repair(self):
        run = self.save(self.finished())
        original = json.loads(self.run_path(run).read_text())
        for change in ("receipt", "evidence", "acceptance", "criteria", "chain"):
            damaged = deepcopy(original)
            if change == "receipt": damaged["operator_reviews"][0]["selection"]["note"] = "tampered"
            if change == "evidence": damaged["answer_preview"] = "tampered"
            if change == "acceptance": damaged["acceptance"] = "not_recorded"
            if change == "criteria": damaged["success_criteria"]["items"][0]["text"] = "different"
            if change == "chain": damaged["operator_reviews"][0]["previous_receipt_hash"] = "invented"
            self.run_path(run).write_text(json.dumps(damaged)); before = self.files()
            page = self.backend.work_sessions.page(self.conversation)
            self.assertTrue(page["warnings"], change)
            self.assertEqual(page["runs"], [])
            self.assertEqual(before, self.files())

    def test_review_history_has_a_hard_bound_without_pruning(self):
        run = self.finished()
        for _ in range(review.MAX_REVIEWS): run = self.save(run)
        before = self.files()
        self.assertFalse(self.preview(run)["ready"])
        with self.assertRaises(ValueError): self.save(run)
        self.assertEqual(before, self.files())
        self.assertEqual(len(run["operator_reviews"]), review.MAX_REVIEWS)

    def test_saved_review_survives_restart_and_old_fingerprint_is_stale(self):
        initial = self.finished(); run = self.save(initial)
        reopened = bridge.NativeBackend(self.root, self.state, subscription_factory=FakeSubscription)
        self.addCleanup(reopened.close)
        page = reopened.work_sessions.page(self.conversation)
        self.assertEqual(page["runs"][0]["operator_reviews"], run["operator_reviews"])
        self.assertNotEqual(initial["fingerprint"], run["fingerprint"])
        before = self.files()
        self.assertEqual(page["warnings"], [])
        self.assertEqual(before, self.files())
        self.assertEqual(reopened.subscription.calls, [])

    def test_artifact_desk_distinguishes_manual_acceptance_from_automatic_verification(self):
        run = self.save(self.finished())
        value = self.backend.dispatch("artifact_list", self.params(run), lambda _: None, "p")
        self.assertEqual(value["verification"]["acceptance"], "operator_accepted")
        self.assertEqual(value["verification"]["status"], "not_assessed")
        self.assertEqual(value["verification"]["criteria"], "declared")
        self.assertEqual(value["operator_reviews"], run["operator_reviews"])

    def test_invalid_review_payload_never_executes_or_writes(self):
        run = self.finished(); before = self.files()
        for selected in (None, {}, {"decision": "execute", "checks": [], "note": ""},
                         {"decision": "accepted", "checks": [True, "met"], "note": ""},
                         {"decision": "accepted", "checks": ["met", "met"], "note": "x" * 1001}):
            with self.subTest(selected=selected), self.assertRaises(ValueError): self.preview(run, review=selected)
        self.assertEqual(before, self.files())
        self.assertEqual(self.backend.subscription.calls, [])


if __name__ == "__main__":
    unittest.main()
