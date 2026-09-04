"""Crash/retry/private-state coverage using disposable Native stores, never real models."""
from __future__ import annotations

import errno
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

from proto_mind import native_bridge as bridge
from proto_mind import native_agent_contract as agent_contract
from proto_mind import native_computer_use as computer_use
from proto_mind import native_work_sessions as sessions
from proto_mind.config import ProtoMindConfig
from proto_mind.tests.test_native import FakeSubscription


class WorkSessionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="proto-work-sessions-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "project"
        self.root.mkdir()
        self.state = Path(self.temporary.name) / "private-native"
        self.store = sessions.WorkSessionStore(self.state, self.root)
        self.conversation = str(uuid4())
        self.run_id = str(uuid4())

    def begin(self, **changes):
        values = dict(run_id=self.run_id, conversation_id=self.conversation, text="Inspect the project safely.",
                      provider="mock", model="", effort="", mode="chat", workspace=None, sources=[])
        values.update(changes)
        return self.store.begin(**values)

    def files(self):
        return {str(path.relative_to(self.state)): path.read_bytes() for path in self.state.rglob("*") if path.is_file()}

    def page(self):
        return self.store.page(self.conversation)

    def finish(self, **changes):
        with self.begin(**changes) as run:
            run.dispatch()
            return run.complete("Observed a response; task verification was not performed.")

    def test_read_missing_journal_does_not_initialize_private_state(self):
        page = self.page()
        self.assertEqual(page["runs"], [])
        self.assertTrue(page["read_only"])
        self.assertFalse(self.state.exists())

    def test_prepare_dispatch_completion_have_distinct_truthful_evidence(self):
        with self.begin() as run:
            self.assertEqual(self.page()["runs"][0]["display_status"], "preparing")
            self.assertNotIn("dispatched_at", run.record)
            run.dispatch()
            self.assertEqual(self.page()["runs"][0]["display_status"], "running")
            result = run.complete("Answer")
        self.assertEqual(result["display_status"], "completed")
        self.assertEqual(result["verification"], "not_assessed")
        self.assertEqual(result["acceptance"], "not_recorded")
        self.assertFalse(result["automatic_resume"])
        self.assertEqual(self.page()["runs"][0]["id"], self.run_id)

    def test_crash_before_dispatch_is_not_started_and_read_only(self):
        run = self.begin().__enter__()
        run.close()
        before = self.files()
        self.assertEqual(self.page()["runs"][0]["display_status"], "not_started")
        self.assertEqual(before, self.files())

    def test_actual_process_exit_after_dispatch_is_unknown_not_success(self):
        program = (
            "from pathlib import Path; import os; from proto_mind.native_work_sessions import WorkSessionStore; "
            f"store=WorkSessionStore(Path({str(self.state)!r}), Path({str(self.root)!r})); "
            f"run=store.begin(run_id={self.run_id!r},conversation_id={self.conversation!r},text='crash fixture',"
            "provider='mock',model='',effort='',mode='chat',workspace=None,sources=[]).__enter__(); "
            "run.dispatch(); os._exit(17)"
        )
        result = subprocess.run([sys.executable, "-B", "-c", program], capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 17, result.stderr.decode())
        before = self.files()
        reopened = sessions.WorkSessionStore(self.state, self.root).page(self.conversation)
        self.assertEqual(reopened["runs"][0]["display_status"], "unknown")
        self.assertEqual(before, self.files())

    def test_completed_receipt_survives_lost_ui_reply_without_reexecution(self):
        self.finish()
        before = self.files()
        with self.assertRaisesRegex(sessions.WorkSessionError, "already used"):
            self.finish()
        self.assertEqual(before, self.files())
        self.assertEqual(self.page()["runs"][0]["display_status"], "completed")

    def test_private_modes_and_atomic_replace_keep_valid_record(self):
        with patch.object(sessions.os, "replace", wraps=os.replace) as replace:
            self.finish()
        self.assertEqual(replace.call_count, 3)
        self.assertEqual(self.store.directory.stat().st_mode & 0o777, 0o700)
        for path in self.store.directory.iterdir():
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertFalse(path.name.endswith(".tmp"))
        json.loads((self.store.directory / (self.run_id + ".json")).read_bytes())

    def test_no_double_writer_and_reads_do_not_release_other_writer(self):
        with self.begin() as run:
            run.dispatch()
            before = self.files()
            self.assertEqual(self.page()["runs"][0]["display_status"], "running")
            with self.assertRaisesRegex(sessions.WorkSessionError, "Another Native window"):
                with self.begin(run_id=str(uuid4())):
                    self.fail("second writer entered")
            self.assertEqual(before, self.files())

    def test_duplicate_public_events_upsert_without_raw_reasoning_or_auth(self):
        with self.begin(text="x" * 5000) as run:
            run.dispatch()
            tool = {"event": "agent_activity", "item": {"id": "one", "kind": "commandExecution", "status": "inProgress",
                      "command": "inspect", "output_preview": "z" * 6000, "token": "DO-NOT-COPY", "reasoning": "PRIVATE"}}
            run.observe(tool)
            before = self.files()
            run.observe(tool)
            self.assertEqual(before, self.files())
            tool["item"]["status"] = "completed"
            tool["item"]["exit_code"] = 0
            run.observe(tool)
            run.observe({"event": "raw_reasoning", "text": "PRIVATE"})
            run.observe({"event": "work_log", "log": {"schema": "proto_mind.native_work_log.v1", "public_only": True,
                         "entries": [{"id": "public", "kind": "commentary", "text": "Public update"},
                                     {"id": "hidden", "kind": "reasoning", "text": "PRIVATE"}], "auth": "DO-NOT-COPY"}})
            result = run.complete("a" * 6000)
        self.assertEqual(len(result["tools"]), 1)
        self.assertEqual(result["tools"][0]["exit_code"], 0)
        self.assertLess(len(result["input_preview"]), 850)
        self.assertLess(len(result["answer_preview"]), 1650)
        self.assertLess(len(result["tools"][0]["output_preview"]), 820)
        serialized = json.dumps(result)
        self.assertNotIn("PRIVATE", serialized)
        self.assertNotIn("DO-NOT-COPY", serialized)
        self.assertNotIn("xxxx" * 1000, serialized)

    def test_unknown_tools_remain_unknown_after_restart(self):
        run = self.begin().__enter__()
        run.dispatch()
        run.observe({"event": "agent_activity", "item": {"id": "one", "kind": "fileChange", "status": "inProgress", "paths": ["test.py"]}})
        run.close()
        result = self.page()["runs"][0]
        self.assertEqual(result["display_status"], "unknown")
        self.assertEqual(result["tools"][0]["status"], "unknown")
        self.assertNotIn("answer_preview", result)

    def test_web_search_receipt_is_bounded_and_marks_external_access(self):
        with self.begin() as run:
            run.dispatch()
            run.observe({"event": "agent_activity", "item": {
                "id": "web", "kind": "webSearch", "status": "completed",
                "query": "Codex internet access", "action_type": "openPage",
                "url": "https://example.invalid/docs", "results": "PRIVATE_RESULTS",
            }})
            run.observe({"event": "agent_run", "receipt": {
                "status": "completed", "execution_may_have_occurred": True,
                "network_access_performed": True,
            }})
            result = run.complete("Web result")
        self.assertTrue(result["network_access_performed"])
        self.assertEqual(result["tools"], [{
            "id": "web", "kind": "webSearch", "status": "completed",
            "query": "Codex internet access", "action_type": "openPage",
            "url": "https://example.invalid/docs",
        }])
        self.assertNotIn("PRIVATE_RESULTS", json.dumps(result))

    def test_computer_use_receipt_keeps_only_action_app_and_privacy_note(self):
        with self.begin() as run:
            run.dispatch()
            run.observe({"event": "agent_activity", "item": {
                "id": "screen", "kind": "computerUse", "status": "completed",
                "tool": "type_text", "app": "Calculator", "note": "Typed input omitted.",
                "arguments": {"text": "PRIVATE_TYPED_TEXT", "x": 44},
                "result": {"screenshot": "PRIVATE_SCREENSHOT", "tree": "PRIVATE_UI_TREE"},
            }})
            run.observe({"event": "agent_run", "receipt": {
                "status": "completed", "execution_may_have_occurred": True,
                "computer_use_performed": True, "screen_access_performed": True,
            }})
            result = run.complete("Screen action observed")
        self.assertTrue(result["computer_use_performed"])
        self.assertTrue(result["screen_access_performed"])
        self.assertEqual(result["tools"], [{
            "id": "screen", "kind": "computerUse", "status": "completed",
            "tool": "type_text", "app": "Calculator", "note": "Typed input omitted.",
        }])
        self.assertNotIn("PRIVATE", json.dumps(result))

    def test_agent_contract_and_automation_failure_are_validated_and_bounded(self):
        workspace = sessions.workspace_identity(self.root)
        contract = agent_contract.build_agent_contract(
            self.root, model="gpt-5.6-sol", reasoning_effort="high", computer_use=True,
            criteria=["Inspect Safari."],
        )
        with self.begin(mode="full_access", workspace=workspace) as run:
            run.dispatch()
            run.observe({"event": "agent_activity", "item": {
                "id": "screen", "kind": "computerUse", "status": "failed",
                "tool": "get_app_state", "app": "Safari", "note": "Screen omitted.",
                "failure_code": "macos_automation_permission_denied",
                "failure_message": "macOS denied Automation access required by Computer Use.",
                "recovery": "Open System Settings > Privacy & Security > Automation.",
                "private": "DO-NOT-PERSIST",
            }})
            run.observe({"event": "agent_run", "receipt": {
                "status": "failed", "contract": contract,
                "contract_hash": agent_contract.contract_hash(contract),
                "runtime_inventory": agent_contract.validate_runtime_inventory(
                    contract, set(computer_use.COMPUTER_USE_TOOLS)),
                "execution_may_have_occurred": True,
                "computer_use_performed": True, "screen_access_performed": True,
            }})
            result = run.complete("Permission was denied.")
        self.assertEqual(result["agent_contract"], contract)
        self.assertEqual(result["agent_contract_hash"], agent_contract.contract_hash(contract))
        self.assertTrue(result["agent_runtime_inventory"]["verified"])
        self.assertEqual(result["tools"][0]["failure_code"], "macos_automation_permission_denied")
        self.assertNotIn("DO-NOT-PERSIST", json.dumps(result))

    def test_corrupt_state_is_visible_and_never_overwritten_by_new_turn(self):
        self.finish()
        path = self.store.directory / (self.run_id + ".json")
        path.write_text("broken")
        before = self.files()
        self.assertTrue(self.page()["warnings"])
        with self.assertRaisesRegex(sessions.WorkSessionError, "manual review"):
            self.finish(run_id=str(uuid4()))
        self.assertEqual(before, self.files())

    def test_symlink_record_is_not_followed_or_repaired(self):
        self.finish()
        target = self.root / "private.txt"
        target.write_text("not a run")
        path = self.store.directory / (str(uuid4()) + ".json")
        path.symlink_to(target)
        before = self.files()
        self.assertTrue(self.page()["warnings"])
        with self.assertRaises(sessions.WorkSessionError):
            self.finish(run_id=str(uuid4()))
        self.assertEqual(before, self.files())

    def test_disk_full_before_dispatch_leaves_no_dispatched_record(self):
        with patch.object(sessions.os, "replace", side_effect=OSError(errno.ENOSPC, "fixture disk full")):
            with self.assertRaises(sessions.WorkSessionError):
                self.finish()
        self.assertEqual(self.page()["runs"], [])
        self.assertFalse(list(self.store.directory.glob("*.tmp")))

    def test_disk_full_during_progress_preserves_last_dispatch_boundary(self):
        with self.assertRaises(sessions.WorkSessionError):
            with self.begin() as run:
                run.dispatch()
                before = self.files()
                with patch.object(sessions.os, "replace", side_effect=OSError(errno.ENOSPC, "fixture")):
                    run.observe({"event": "agent_activity", "item": {"id": "one", "kind": "commandExecution", "status": "completed"}})
        self.assertEqual(before, self.files())
        self.assertEqual(self.page()["runs"][0]["display_status"], "unknown")

    def test_external_edit_cannot_be_overwritten_by_writer(self):
        with self.assertRaisesRegex(sessions.WorkSessionError, "outside its writer"):
            with self.begin() as run:
                run.dispatch()
                path = self.store.directory / (self.run_id + ".json")
                path.write_text("external change")
                run.complete("must not overwrite")
        self.assertEqual(path.read_text(), "external change")

    def test_continuation_is_read_only_and_one_child_is_allowed(self):
        parent = self.finish()
        reference = {"run_id": parent["id"], "fingerprint": parent["fingerprint"]}
        before = self.files()
        prepared = self.store.continuation(reference, self.conversation, None)
        again = self.store.continuation(reference, self.conversation, None)
        self.assertEqual(prepared, again)
        self.assertEqual(before, self.files())
        self.assertTrue(prepared["read_only"])
        self.assertFalse(prepared["automatic_resume"])
        self.assertIn("новый запрос", prepared["draft"])
        child = self.finish(run_id=str(uuid4()), continuation=reference)
        self.assertEqual(child["parent_run_id"], parent["id"])
        before = self.files()
        with self.assertRaisesRegex(sessions.WorkSessionError, "continuation already exists"):
            self.finish(run_id=str(uuid4()), continuation=reference)
        self.assertEqual(before, self.files())

    def test_continuation_rejects_foreign_conversation_folder_and_fingerprint(self):
        parent = self.finish(workspace=sessions.workspace_identity(self.root))
        reference = {"run_id": parent["id"], "fingerprint": parent["fingerprint"]}
        before = self.files()
        for conversation, workspace, ref in (
            (str(uuid4()), parent["workspace"], reference),
            (self.conversation, None, reference),
            (self.conversation, {**parent["workspace"], "inode": -1}, reference),
            (self.conversation, parent["workspace"], {**reference, "fingerprint": "0" * 64}),
        ):
            with self.subTest(conversation=conversation, workspace=workspace), self.assertRaises(sessions.WorkSessionError):
                self.store.continuation(ref, conversation, workspace)
        self.assertEqual(before, self.files())

    def test_storage_limit_refuses_new_run_without_automatic_pruning(self):
        self.finish()
        before = self.files()
        with patch.object(sessions, "MAX_RUNS", 1), self.assertRaisesRegex(sessions.WorkSessionError, "limit reached"):
            self.finish(run_id=str(uuid4()))
        self.assertEqual(before, self.files())

    def test_replaced_writer_lock_stops_without_overwriting_run(self):
        with self.assertRaisesRegex(sessions.WorkSessionError, "writer lock changed"):
            with self.begin() as run:
                run.dispatch()
                before = (self.store.directory / (self.run_id + ".json")).read_bytes()
                replacement = self.store.directory / "replacement.lock"
                replacement.write_text("external replacement")
                replacement.replace(self.store.directory / ".writer.lock")
                run.complete("not durable")
        self.assertEqual((self.store.directory / (self.run_id + ".json")).read_bytes(), before)
        self.assertEqual(self.page()["runs"][0]["display_status"], "unknown")

    def test_page_is_bounded_and_malformed_nested_evidence_is_diagnostic(self):
        self.finish()
        self.finish(run_id=str(uuid4()))
        with patch.object(sessions, "MAX_PAGE_BYTES", 1):
            page = self.page()
            self.assertEqual(page["runs"], [])
            self.assertTrue(page["partial"])
        path = self.store.directory / (self.run_id + ".json")
        record = json.loads(path.read_bytes())
        record["tools"] = [42]
        path.write_text(json.dumps(record))
        before = self.files()
        self.assertEqual(len(self.page()["runs"]), 1)
        self.assertTrue(self.page()["warnings"])
        self.assertEqual(before, self.files())

    def test_private_backup_restore_preserves_completed_and_unknown_evidence(self):
        self.finish()
        run = self.begin(run_id=str(uuid4())).__enter__()
        run.dispatch()
        run.close()
        restored_state = Path(self.temporary.name) / "restored-native"
        shutil.copytree(self.state, restored_state)
        before = self.files()
        restored = sessions.WorkSessionStore(restored_state, self.root).page(self.conversation)
        self.assertEqual({record["display_status"] for record in restored["runs"]}, {"completed", "unknown"})
        self.assertTrue(all(record["automatic_resume"] is False for record in restored["runs"]))
        self.assertEqual(before, self.files())
        self.assertEqual(self.store.page(str(uuid4()))["runs"], [])


class WorkSessionBridgeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="proto-work-bridge-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "project"
        self.root.mkdir()
        self.state = Path(self.temp.name) / "state"
        self.backend = bridge.NativeBackend(self.root, self.state, subscription_factory=FakeSubscription)
        self.addCleanup(self.backend.close)
        config_patch = patch.object(ProtoMindConfig, "from_env", return_value=ProtoMindConfig(data_dir=self.root / "proto_mind" / "data"))
        config_patch.start()
        self.addCleanup(config_patch.stop)
        self.params = {"conversation_id": str(uuid4()), "run_id": str(uuid4()), "text": "Hello", "provider": "codex", "cloud_consent": True}

    def process(self, **changes):
        return self.backend.process({**self.params, **changes}, lambda event: None, "request")

    def test_bridge_persists_once_and_duplicate_request_never_calls_model(self):
        result = self.process()
        self.assertEqual(result["work_session"]["display_status"], "completed")
        receipt = result["work_session"]["instruction_receipt"]
        self.assertEqual(receipt["schema"], "proto_mind.native_instruction_receipt.v1")
        self.assertTrue(receipt["content_free"])
        self.assertFalse(receipt["instruction_text_stored"])
        turn = result["work_session"]["turn_receipt"]
        self.assertEqual(turn["run_id"], self.params["run_id"])
        self.assertEqual(turn["conversation_id"], self.params["conversation_id"])
        self.assertEqual(turn["response_sha256"], hashlib.sha256(result["text"].encode()).hexdigest())
        self.assertNotIn(result["text"], json.dumps(turn))
        self.assertEqual(len(self.backend.subscription.calls), 1)
        with self.assertRaisesRegex(sessions.WorkSessionError, "already used"):
            self.process()
        self.assertEqual(len(self.backend.subscription.calls), 1)

    def test_tampered_instruction_receipt_is_visible_and_never_rewritten(self):
        result = self.process()
        path = self.state / "work_sessions" / f"{result['work_session']['id']}.json"
        record = json.loads(path.read_text())
        record["instruction_receipt"]["receipt_hash"] = "0" * 64
        path.write_text(json.dumps(record))
        before = path.read_bytes()

        page = self.backend.work_sessions.page(self.params["conversation_id"])

        self.assertEqual(page["runs"], [])
        self.assertTrue(page["warnings"])
        self.assertEqual(path.read_bytes(), before)

    def test_operator_and_readonly_journal_methods_never_create_run_or_call_provider(self):
        self.process(text="/commands status")
        self.backend.dispatch("work_sessions", self.params, lambda _: None, "read")
        self.assertFalse(self.state.exists())
        self.assertEqual(self.backend.subscription.calls, [])

    def test_durable_prepare_failure_prevents_handler_and_model(self):
        with patch.object(sessions.os, "replace", side_effect=OSError(errno.ENOSPC, "fixture")), patch.object(bridge, "process_interactive_input_with_envelope") as handler:
            with self.assertRaises(sessions.WorkSessionError):
                self.process()
        handler.assert_not_called()
        self.assertEqual(self.backend.subscription.calls, [])

    def test_failure_after_dispatch_is_unknown_and_does_not_leak_error_payload(self):
        self.backend.subscription.failure = RuntimeError("DO-NOT-PERSIST-RAW-ERROR")
        with self.assertRaises(RuntimeError):
            self.process()
        page = self.backend.work_sessions.page(self.params["conversation_id"])
        self.assertEqual(page["runs"][0]["display_status"], "unknown")
        self.assertNotIn("DO-NOT-PERSIST-RAW-ERROR", json.dumps(page))

    def test_mid_turn_storage_failure_requests_stop_and_never_retries(self):
        def answer(prompt, instructions, model, on_delta, *, on_progress, **kwargs):
            with patch.object(sessions.os, "replace", side_effect=OSError(errno.ENOSPC, "fixture")):
                on_progress({"event": "work_log", "log": {"schema": "proto_mind.native_work_log.v1", "public_only": True, "status": "running", "entries": []}})
            return "must not reach"
        with patch.object(self.backend.subscription, "answer", side_effect=answer) as provider:
            with self.assertRaises(sessions.WorkSessionError):
                self.process()
        self.assertEqual(provider.call_count, 1)
        self.assertTrue(self.backend.subscription.interrupted)
        self.assertEqual(self.backend.work_sessions.page(self.params["conversation_id"])["runs"][0]["display_status"], "unknown")

    def test_continuation_rechecks_explicit_source_hash_without_restoring_tools(self):
        source = self.root / "note.txt"
        source.write_text("selected original")
        reader = self.backend.workspace({"workspace_root": str(self.root)})
        manifest = reader.read_file("note.txt")
        result = self.process(workspace_root=str(self.root), files=[manifest])
        parent = result["work_session"]
        params = {**self.params, "workspace_root": str(self.root), "continuation": {"run_id": parent["id"], "fingerprint": parent["fingerprint"]}}
        prepared = self.backend.dispatch("work_session_continuation", params, lambda _: None, "preview")
        self.assertNotIn("access_token", prepared)
        self.assertFalse(prepared["automatic_resume"])
        self.assertEqual(len(self.backend.subscription.calls), 1)
        source.write_text("changed outside the turn")
        with self.assertRaisesRegex(ValueError, "changed after preview"):
            self.backend.dispatch("work_session_continuation", params, lambda _: None, "preview")
        with self.assertRaisesRegex(ValueError, "changed after preview"):
            self.process(run_id=str(uuid4()), workspace_root=str(self.root), continuation=params["continuation"])
        self.assertEqual(len(self.backend.subscription.calls), 1)

    def test_continuation_does_not_reuse_cloud_consent_or_previous_full_access(self):
        result = self.process()
        parent = result["work_session"]
        reference = {"run_id": parent["id"], "fingerprint": parent["fingerprint"]}
        with self.assertRaisesRegex(ValueError, "approve cloud"):
            self.process(run_id=str(uuid4()), continuation=reference, cloud_consent=False)
        with self.assertRaisesRegex(ValueError, "permission is missing"):
            self.process(run_id=str(uuid4()), continuation=reference, workspace_root=str(self.root), access_mode="full_access")
        self.assertEqual(len(self.backend.subscription.calls), 1)


if __name__ == "__main__":
    unittest.main()
