"""Context/artifact views on disposable local state; no provider or real user files."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

from proto_mind import native_bridge as bridge
from proto_mind import native_desk as desk
from proto_mind.native_work_sessions import WorkSessionError, workspace_identity
from proto_mind.config import ProtoMindConfig
from proto_mind.tests.test_native import FakeSubscription


class NativeDeskTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="proto-native-desk-")
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name).resolve()
        self.root, self.state = self.base / "core", self.base / "private"
        self.workspace = self.base / "workspace"
        self.workspace.mkdir()
        self.backend = bridge.NativeBackend(self.root, self.state, subscription_factory=FakeSubscription)
        self.addCleanup(self.backend.close)
        self.conversation = str(uuid4())
        config = patch.object(ProtoMindConfig, "from_env", return_value=ProtoMindConfig(data_dir=self.root / "proto_mind/data"))
        config.start()
        self.addCleanup(config.stop)
        self.reader = self.backend.workspace({"workspace_root": str(self.workspace)})

    def write(self, name="result.py", content="print('original')\n"):
        path = self.workspace / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def files(self):
        return {str(path.relative_to(self.base)): path.read_bytes() for path in self.base.rglob("*")
                if path.is_file() and not path.is_symlink()}

    def spec(self, name="result.py"):
        source = self.reader.read_file(name)
        return {key: source[key] for key in ("path", "sha256")}

    def params(self, **changes):
        return {"text": "Inspect the selected source.", "history": [], "provider": "codex", "model": "",
                "cloud_consent": False, "conversation_id": self.conversation,
                "workspace_root": str(self.workspace), **changes}

    def context(self, **changes):
        return self.backend.dispatch("context_preview", self.params(**changes), lambda _: self.fail("no events"), "preview")

    def finished(self, *, paths=None, status="completed", sources=None, capture=True, command_exit=0):
        with self.backend.work_sessions.begin(run_id=str(uuid4()), conversation_id=self.conversation,
                text="Fixture task", provider="mock", model="", effort="", mode="chat",
                workspace=workspace_identity(self.workspace), sources=sources or []) as run:
            run.dispatch()
            run.observe({"event": "agent_activity", "item": {"id": "change", "kind": "fileChange", "status": status,
                "paths": paths or ["result.py"], "diff_preview": "--- result.py\n+++ result.py\n-original\n+new\n"}})
            run.observe({"event": "agent_activity", "item": {"id": "command", "kind": "commandExecution", "status": "completed",
                "command": "fixture-test-command (not executed)", "exit_code": command_exit, "output_preview": "Observed fixture output"}})
            artifacts = desk.capture_artifacts(run.record, self.reader) if capture else None
            return run.complete("Model claim, not independent verification.", artifacts=artifacts)

    def request(self, saved, **changes):
        result = self.params(run={"run_id": saved["id"], "fingerprint": saved["fingerprint"]})
        result.update(changes)
        return result

    def artifacts(self, run):
        return self.backend.dispatch("artifact_list", self.request(run), lambda _: self.fail("no events"), "read")

    def preview(self, run, **changes):
        identifier = self.artifacts(run)["items"][0]["id"]
        return self.backend.dispatch("artifact_preview", self.request(run, artifact_id=identifier, **changes), lambda _: self.fail("no events"), "read")

    def test_empty_context_is_local_and_does_not_initialize_core_or_private_state(self):
        before = self.files()
        with patch.object(self.backend, "_coordinator", side_effect=AssertionError("No reasoning")), patch("subprocess.Popen", side_effect=AssertionError("No process")):
            result = self.context(text="")
        self.assertTrue(result["read_only"] and result["no_execution"] and result["draft_empty"])
        self.assertEqual(result["manifest"]["context_injection"]["state"], "default_disabled")
        self.assertEqual(before, self.files())
        self.assertFalse(self.root.exists() or self.state.exists())
        self.assertEqual(self.backend.subscription.calls, [])

    def test_selected_file_excerpt_matches_exact_existing_send_context(self):
        self.write(content="local text\n" * 900)
        spec = self.spec()
        result = self.context(files=[spec])
        sent = self.reader.context_files([spec])[0]
        self.assertEqual(result["sources"][0]["excerpt"], sent["content"])
        self.assertEqual(result["sources"][0]["included_chars"], 6000)
        self.assertTrue(result["sources"][0]["truncated"])
        self.assertEqual(result["manifest"]["files"][0]["sha256"], sent["sha256"])
        self.assertTrue(result["attachments_ready"])

    def test_stale_source_never_reselects_or_exposes_replacement_as_attached(self):
        self.write()
        spec = self.spec()
        self.write(content="new unchosen bytes")
        before = self.files()
        result = self.context(files=[spec])
        self.assertEqual(result["sources"][0]["state"], "changed")
        self.assertEqual(result["sources"][0]["excerpt"], "")
        self.assertEqual(result["manifest"]["files"], [])
        self.assertFalse(result["attachments_ready"])
        self.assertEqual(before, self.files())
        with self.assertRaisesRegex(ValueError, "changed"):
            self.backend.process(self.params(files=[spec], cloud_consent=True), lambda _: None, "send")
        self.assertEqual(self.backend.subscription.calls, [])

    def test_missing_source_is_visible_without_repair(self):
        result = self.context(files=[{"path": "missing.py", "sha256": "0" * 64}])
        self.assertEqual(result["sources"][0]["state"], "unavailable")
        self.assertFalse((self.workspace / "missing.py").exists())

    def test_context_rejects_bad_manifest_and_bounds(self):
        self.write()
        for files in (None, {}, [{}], [self.spec()] * 4, [self.spec(), self.spec()], [{"path": "x", "sha256": "invalid"}]):
            with self.subTest(files=files), self.assertRaises(ValueError):
                self.context(files=files)

    def test_context_excludes_symlink_traversal_credentials_and_binary(self):
        self.write("secret.txt", "not to attach")
        self.write("auth.json", "not to attach")
        self.write("image.png", "not supported")
        (self.workspace / "link.py").symlink_to(self.workspace / "secret.txt")
        for name in ("link.py", "../workspace/secret.txt", "auth.json", "image.png"):
            with self.subTest(name=name):
                result = self.context(files=[{"path": name, "sha256": "0" * 64}])
                self.assertEqual(result["sources"][0]["state"], "unavailable")
                self.assertEqual(result["sources"][0]["excerpt"], "")

    def test_history_has_same_bounds_as_send_and_only_public_roles(self):
        history = [{"role": "user", "content": "x" * 2100 + str(index)} for index in range(20)]
        result = self.context(history=history)
        self.assertEqual(result["history"], bridge.bounded_history(history))
        self.assertEqual(result["manifest"]["history"]["messages"], 12)
        self.assertEqual(result["manifest"]["history"]["characters"], 24000)
        for role in ("system", "tool", "analysis"):
            with self.assertRaises(ValueError):
                self.context(history=[{"role": role, "content": "never include"}])

    def test_context_does_not_read_irrelevant_memory_or_claim_project_isolation(self):
        data = self.root / "proto_mind/data"
        data.mkdir(parents=True)
        (data / "persistent_memory.json").write_text("DO NOT INCLUDE CORE CONTENT")
        result = self.context()
        self.assertEqual(result["manifest"]["memory_scope"], "shared_core_not_workspace")
        self.assertEqual(result["manifest"]["memory_root"], str(data))
        self.assertEqual(result["manifest"]["recall"], "read_only_current_projection_recomputed_at_send")
        self.assertFalse(result["instruction_preview"]["read_only_retrieval_performed"])
        self.assertNotIn("DO NOT INCLUDE", json.dumps(result))

    def test_cloud_disclosure_does_not_connect_or_authorize(self):
        for consent in (False, True):
            result = self.context(cloud_consent=consent, access_mode="full_access")
            self.assertEqual(result["cloud_consent"], consent)
            self.assertEqual(result["manifest"]["destination"], "openai_cloud")
            self.assertFalse(result["manifest"]["permission_granted"])
        self.assertEqual(self.backend.subscription.calls, [])
        with self.assertRaisesRegex(ValueError, "missing or expired"):
            self.backend.process(self.params(access_mode="full_access", cloud_consent=True), lambda _: None, "send")

    def test_operator_and_natural_commands_do_not_read_attachments_or_execute(self):
        for text in ("/context injection enable", "включи контекст", "/unknown command"):
            with patch.object(self.reader, "read_file", side_effect=AssertionError("Must bypass")):
                result = self.context(text=text, files=[{"path": "never.py", "sha256": "0" * 64}], history=[{"role": "user", "content": "private"}])
            self.assertTrue(result["manifest"]["operator"])
            self.assertEqual(result["manifest"]["destination"], "operator_local")
            self.assertEqual(result["history"], [])
            self.assertEqual(result["sources"], [])
            self.assertEqual(result["excluded_attachment_count"], 1)
        self.assertFalse(self.root.exists() or self.state.exists())

    def test_injection_setting_is_read_without_initialization_or_change(self):
        path = self.root / "proto_mind/data/context_injection.json"
        path.parent.mkdir(parents=True)
        for value, expected in (({"enabled": False}, False), ({"enabled": True}, True), ({"enabled": "false"}, None)):
            path.write_text(json.dumps(value))
            before = path.read_bytes()
            self.assertIs(self.context()["manifest"]["context_injection"]["enabled"], expected)
            self.assertEqual(path.read_bytes(), before)
        path.write_text("broken")
        self.assertEqual(self.context()["manifest"]["context_injection"]["state"], "unknown")

    def test_injection_symlink_is_not_followed(self):
        target = self.write("settings.json", '{"enabled":true}')
        path = self.root / "proto_mind/data/context_injection.json"
        path.parent.mkdir(parents=True)
        path.symlink_to(target)
        self.assertEqual(self.context()["manifest"]["context_injection"]["state"], "unknown")

    def test_normal_turn_persists_compact_manifest_without_full_history_or_file(self):
        self.write(content="UNIQUE FILE CONTENT")
        result = self.backend.process(self.params(provider="mock", files=[self.spec()], text="Hello.",
                    history=[{"role": "user", "content": "UNIQUE HISTORY CONTENT"}]), lambda _: None, "send")
        run = result["work_session"]
        self.assertEqual(run["context_manifest"]["history"]["messages"], 1)
        self.assertEqual(run["context_manifest"]["files"][0]["included_chars"], 19)
        raw = (self.state / "work_sessions" / (run["id"] + ".json")).read_text()
        self.assertNotIn("UNIQUE FILE CONTENT", raw)
        self.assertNotIn("UNIQUE HISTORY CONTENT", raw)
        self.assertFalse(run["context_manifest"]["permission_granted"])

    def test_artifact_has_observed_run_tool_and_capture_hash(self):
        self.write()
        source = self.spec()
        self.write(content="print('new')\n")
        run = self.finished(sources=[source])
        item = self.artifacts(run)["items"][0]
        self.assertEqual(item["tool_id"], "change")
        self.assertEqual(item["original_sha256"], source["sha256"])
        self.assertEqual(item["sha256"], self.spec()["sha256"])
        self.assertEqual(run["artifact_snapshot"]["run_id"], run["id"])
        self.assertEqual(run["artifact_snapshot"]["capture_boundary"], "turn_completion_not_tool_transaction")

    def test_artifact_current_preview_and_changed_source_are_distinguished(self):
        self.write()
        run = self.finished()
        result = self.preview(run)
        self.assertEqual(result["state"], "current")
        self.write(content="later edit")
        result = self.preview(run)
        self.assertEqual(result["state"], "changed")
        self.assertEqual(result["current"]["preview"], "later edit")
        self.assertNotEqual(result["current"]["sha256"], result["artifact"]["sha256"])

    def test_artifact_read_does_not_mutate_or_connect(self):
        self.write()
        run = self.finished()
        before = self.files()
        with patch("subprocess.Popen", side_effect=AssertionError("No subprocess")), patch.object(self.backend, "_coordinator", side_effect=AssertionError("No core turn")):
            self.assertTrue(self.artifacts(run)["read_only"])
            self.assertTrue(self.preview(run)["no_execution"])
        self.assertEqual(self.files(), before)
        self.assertEqual(self.backend.subscription.calls, [])

    def test_artifact_never_claims_task_verification_from_exit_zero(self):
        self.write()
        run = self.finished()
        result = self.artifacts(run)
        self.assertEqual(result["verification"], {"status": "not_assessed", "acceptance": "not_recorded", "criteria": "not_structured", "exit_zero": 1, "exit_nonzero": 0, "unknown": 0})
        self.assertEqual(result["commands"][0]["output_preview"], "Observed fixture output")

    def test_failed_command_is_evidence_not_success(self):
        self.write()
        result = self.artifacts(self.finished(command_exit=2))
        self.assertEqual(result["verification"]["exit_nonzero"], 1)
        self.assertEqual(result["verification"]["status"], "not_assessed")

    def test_missing_run_and_wrong_ids_are_refused_without_initializing(self):
        with self.assertRaisesRegex(WorkSessionError, "missing"):
            self.backend.dispatch("artifact_list", self.params(run={"run_id": str(uuid4()), "fingerprint": "0" * 64}), lambda _: None, "read")
        self.assertFalse(self.state.exists())

    def test_foreign_conversation_project_or_stale_reference_cannot_read_run(self):
        self.write()
        run = self.finished()
        reference = {"run_id": run["id"], "fingerprint": run["fingerprint"]}
        for changes in ({"conversation_id": str(uuid4())}, {"run": {**reference, "fingerprint": "0" * 64}}):
            with self.subTest(changes=changes), self.assertRaises(WorkSessionError):
                self.backend.dispatch("artifact_list", self.request(run, **changes), lambda _: None, "read")
        other = bridge.NativeBackend(self.base / "other-core", self.state, subscription_factory=FakeSubscription)
        self.addCleanup(other.close)
        with self.assertRaises(WorkSessionError):
            other.dispatch("artifact_list", self.request(run), lambda _: None, "read")

    def test_wrong_artifact_id_is_not_a_file_read_primitive(self):
        self.write()
        run = self.finished()
        with self.assertRaises(ValueError):
            self.backend.dispatch("artifact_preview", self.request(run, artifact_id="../auth.json"), lambda _: None, "read")

    def test_foreign_or_replaced_workspace_does_not_supply_current_artifact(self):
        self.write()
        run = self.finished()
        other = self.base / "other-workspace"
        other.mkdir()
        (other / "result.py").write_text("unrelated")
        self.assertEqual(self.preview(run, workspace_root=str(other))["state"], "unavailable")
        self.workspace.rename(self.base / "old-workspace")
        self.workspace.mkdir()
        self.write(content="replaced root")
        self.assertEqual(self.preview(run)["state"], "unavailable")

    def test_outside_hidden_binary_and_truncated_paths_are_not_artifact_reads(self):
        secret = self.base / "outside.py"
        secret.write_text("not to read")
        for path in (str(secret), "../outside.py", "auth.json", "image.png", "bad.py\n[preview truncated]"):
            run = self.finished(paths=[path])
            self.assertEqual(self.artifacts(run)["items"][0]["state"], "unavailable")
            self.assertIsNone(self.preview(run)["current"])

    def test_core_stores_are_never_artifact_sources(self):
        self.workspace = self.root
        self.workspace.mkdir()
        self.reader = self.backend.workspace({"workspace_root": str(self.workspace)})
        self.write("proto_mind/data/persistent_memory.json", "[]")
        run = self.finished(paths=["proto_mind/data/persistent_memory.json"])
        self.assertEqual(self.preview(run)["state"], "unavailable")

    def test_symlink_replacement_after_artifact_capture_cannot_escape(self):
        source = self.write()
        run = self.finished()
        outside = self.base / "outside.py"
        outside.write_text("private replacement")
        source.unlink()
        source.symlink_to(outside)
        self.assertIsNone(self.preview(run)["current"])

    def test_plain_html_preview_is_data_without_process_or_rendering(self):
        self.write("result.html", "<script>dangerous()</script>")
        with patch("subprocess.Popen", side_effect=AssertionError("No renderer or shell")):
            run = self.finished(paths=["result.html"])
            result = self.preview(run)
        self.assertEqual(result["current"]["preview"], "<script>dangerous()</script>")
        self.assertEqual(result["artifact"]["media_type"], "text/plain")

    def test_legacy_and_unknown_runs_do_not_invent_historical_hash_or_completion(self):
        self.write()
        run = self.finished(capture=False)
        before = self.files()
        self.assertEqual(self.artifacts(run)["items"][0]["state"], "not_captured")
        self.assertEqual(self.preview(run)["state"], "not_captured")
        self.assertEqual(self.files(), before)
        active = self.backend.work_sessions.begin(run_id=str(uuid4()), conversation_id=self.conversation, text="Interrupted", provider="mock", model="", effort="", mode="chat", workspace=workspace_identity(self.workspace), sources=[]).__enter__()
        active.dispatch()
        active.observe({"event": "agent_activity", "item": {"id": "changing", "kind": "fileChange", "status": "inProgress", "paths": ["result.py"]}})
        active.close()
        unknown = next(item for item in self.backend.work_sessions.page(self.conversation)["runs"] if item["id"] == active.record["id"])
        self.assertEqual(self.artifacts(unknown)["run_status"], "unknown")
        self.assertEqual(self.artifacts(unknown)["items"][0]["tool_status"], "unknown")

    def test_hash_capture_does_not_imply_unknown_tool_succeeded(self):
        self.write()
        run = self.finished(status="inProgress")
        self.assertEqual(self.artifacts(run)["items"][0]["state"], "unavailable")
        self.assertEqual(self.preview(run)["state"], "not_captured")

    def test_artifact_snapshot_is_bounded_and_deduplicated(self):
        record = {"id": str(uuid4()), "sources": [], "tools": []}
        for index in range(12):
            record["tools"].append({"id": str(index), "kind": "fileChange", "status": "completed", "paths": [f"{index}/{number}.py" for number in range(8)]})
        result = desk.capture_artifacts(record, self.reader)
        self.assertEqual(len(result["items"]), desk.MAX_ARTIFACTS)
        self.assertEqual(result["total"], 96)
        self.assertTrue(result["partial"])
        record["tools"] = [{"id": "one", "kind": "fileChange", "status": "completed", "paths": ["same.py", "same.py"]}]
        self.assertEqual(len(desk.capture_artifacts(record, self.reader)["items"]), 1)

    def test_malformed_or_foreign_artifact_metadata_is_diagnosed_not_rewritten(self):
        self.write()
        run = self.finished()
        path = self.state / "work_sessions" / (run["id"] + ".json")
        original = json.loads(path.read_bytes())
        item = original["artifact_snapshot"]["items"][0]
        for change in ({"run_id": str(uuid4())}, {"items": [None]}, {"items": [{"id": "fake"}]},
                       {"capture_boundary": "tool_verified"}, {"total": True}, {"partial": True},
                       {"items": [{**item, "original_sha256": "f" * 64}]},
                       {"items": [{**item, "tool_status": "inProgress"}]},
                       {"items": [{**item, "state": "unavailable"}]},
                       {"items": original["artifact_snapshot"]["items"] * 2}):
            value = deepcopy(original)
            value["artifact_snapshot"].update(change)
            path.write_text(json.dumps(value))
            before = path.read_bytes()
            self.assertTrue(self.backend.work_sessions.page(self.conversation)["warnings"])
            self.assertEqual(path.read_bytes(), before)

    def test_real_bridge_projects_observed_file_change_without_extra_execution(self):
        source = self.write()
        old_spec = self.spec()
        from proto_mind.native_agent import FULL_ACCESS_CONFIRMATION
        grant = self.backend.dispatch("agent_access", self.params(mode="full_access", cloud_consent=True, confirmation=FULL_ACCESS_CONFIRMATION), lambda _: None, "grant")
        calls = []
        def fake_agent(prompt, instructions, model, on_delta, *, workspace, on_activity, **kwargs):
            calls.append(prompt)
            source.write_text("fixture produced file\n")
            on_activity({"event": "agent_activity", "item": {"id": "produced", "kind": "fileChange", "status": "completed", "paths": [str(source)], "diff_preview": "-original\n+fixture produced file"}})
            on_activity({"event": "agent_activity", "item": {"id": "verification", "kind": "commandExecution", "status": "completed", "command": "fixture verification", "exit_code": 0, "output_preview": "fixture ok"}})
            return "Fixture response."
        with patch.object(self.backend.subscription, "agent_answer", fake_agent, create=True):
            result = self.backend.process(self.params(access_mode="full_access", cloud_consent=True, access_token=grant["token"], files=[old_spec]), lambda _: None, "send")
        run = result["work_session"]
        self.assertEqual(len(calls), 1)
        self.assertEqual(self.preview(run)["state"], "current")
        self.assertEqual(self.preview(run)["artifact"]["original_sha256"], old_spec["sha256"])
        self.assertEqual(self.artifacts(run)["verification"]["exit_zero"], 1)
        self.assertNotIn(grant["token"], json.dumps(run))


if __name__ == "__main__":
    unittest.main()
