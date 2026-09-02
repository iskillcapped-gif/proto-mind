"""Guided tasks reuse ordinary turns and never grant skill execution authority."""
from copy import deepcopy
import json
from unittest import TestCase
from unittest.mock import patch

from proto_mind.config import ProtoMindConfig
from proto_mind.native_agent import FULL_ACCESS_CONFIRMATION
from proto_mind.native_bridge import NativeBackend
from proto_mind.native_knowledge import validate_knowledge_metadata
from proto_mind.native_private_records import digest
from proto_mind.native_work_sessions import WorkSessionError
from proto_mind.tests.test_native_agent import FakeAgentSubscription
from proto_mind.tests.test_native_skill_inspection import CONVERSATION
from proto_mind.tests import test_native_skill_inspection as fixture


class NativeSkillTaskTests(TestCase):
    seed = fixture.NativeSkillInspectionTests.seed
    files = fixture.NativeSkillInspectionTests.files

    def setUp(self):
        fixture.NativeSkillInspectionTests.setUp(self)
        self.backend.close()
        self.backend = NativeBackend(self.root, self.base / "private", subscription_factory=FakeAgentSubscription)
        self.addCleanup(self.backend.close)
        config = patch.object(ProtoMindConfig, "from_env", return_value=ProtoMindConfig(data_dir=self.data))
        config.start(); self.addCleanup(config.stop)

    def params(self, **changes):
        return {"conversation_id": CONVERSATION, "workspace_root": str(self.root.resolve()), "skill_id": self.record["id"],
                "goal": "Explain how to inspect the selected fixture safely.", "criteria": ["List the inspection steps and limits."],
                "provider": "codex", "access_mode": "chat", **changes}

    def preview(self, **changes):
        return self.backend.dispatch("skill_task_preview", self.params(**changes), lambda _: self.fail("No events during preview"), "preview")

    def prepared(self, **changes):
        preview = self.preview(**changes)
        self.assertEqual(preview["status"], "READY", preview)
        body = preview["body"]
        return {"text": body["goal"], "criteria": [item["text"] for item in body["success_criteria"]["items"]],
                "provider": body["provider"], "access_mode": body["access_mode"], "workspace_root": body["workspace"]["path"],
                "conversation_id": CONVERSATION, "cloud_consent": True,
                "skill_task": {"skill_id": body["skill_id"], "goal": body["goal"],
                               "criteria": [item["text"] for item in body["success_criteria"]["items"]],
                               "preview_fingerprint": preview["preview_fingerprint"]}}

    def test_preview_is_read_only_with_exact_provenance_and_no_authority(self):
        before = self.files()
        with patch.object(self.backend, "process", side_effect=AssertionError("No dispatch")), patch("subprocess.Popen", side_effect=AssertionError("No processes")):
            preview = self.preview()
        self.assertEqual(preview["status"], "READY", preview)
        self.assertEqual(digest(json.loads(preview["hash_material"])), preview["preview_fingerprint"])
        self.assertEqual(preview["body"]["contract"], self.record["provenance"]["authored_contract"])
        self.assertFalse(preview["permission_granted"] or preview["body"]["automatic_execution"])
        self.assertEqual(before, self.files()); self.assertEqual(self.backend.sessions, {})
        self.assertEqual(self.backend.subscription.calls, [])

    def test_missing_goal_criteria_or_operator_goal_is_not_preparable(self):
        before = self.files()
        for values in ({"goal": ""}, {"criteria": []}, {"goal": "/data doctor"}, {"goal": "проверь систему"}, {"goal": "exit"}):
            with self.subTest(values=values):
                result = self.preview(**values)
                self.assertEqual(result["status"], "NOT_READY")
                self.assertEqual(result["preview_fingerprint"], "")
        self.assertEqual(before, self.files())

    def test_fixed_preview_contract_rejects_commands_extra_authority_and_invalid_scope(self):
        for values in ({"execute": True}, {"access_token": "secret"}, {"goal": "x" * 4001}, {"criteria": ["same", "same"]},
                       {"workspace_root": ""}, {"conversation_id": ""}, {"provider": "mock", "access_mode": "full_access"}):
            with self.subTest(values=values), self.assertRaises(ValueError): self.preview(**values)
        self.assertEqual(self.backend.subscription.calls, [])

    def test_restored_skill_can_guide_but_has_no_new_effectiveness_claim(self):
        self.seed("restored"); before = self.files()
        result = self.preview()
        self.assertEqual(result["status"], "READY", result)
        self.assertEqual(result["body"]["lifecycle_state"], "active_restored_verified")
        self.assertEqual(result["body"]["quality_verification"], "not_assessed")
        self.assertEqual(before, self.files())

    def test_archived_legacy_missing_or_tampered_skill_cannot_be_selected(self):
        original_skill, original_memory = self.skills.read_bytes(), self.memories.read_bytes()
        self.seed("archived")
        self.assertEqual(self.preview()["status"], "NOT_READY")
        self.skills.write_bytes(original_skill)
        self.memories.write_bytes(original_memory)
        self.record = json.loads(self.skills.read_text().splitlines()[0])
        for record in ({"id": self.record["id"], "name": "Legacy", "status": "active"}, {**self.record, "executable": True}):
            self.skills.write_text(json.dumps(record) + "\n")
            self.assertEqual(self.preview()["status"], "NOT_READY")
        self.assertEqual(self.preview(skill_id="missing")["status"], "NOT_READY")

    def test_context_unknown_enabled_and_source_change_refuse_without_repair(self):
        path = self.data / "context_injection.json"
        for content in ('{"enabled":true}', 'invalid json'):
            path.write_text(content); before = self.files()
            self.assertEqual(self.preview()["status"], "NOT_READY")
            self.assertEqual(before, self.files())
        path.write_text('{"enabled":false}')
        self.assertEqual(self.preview(expected_sha256="0" * 64)["status"], "NOT_READY")

    def test_edits_to_goal_criteria_provider_scope_or_sources_refuse_before_dispatch(self):
        prepared = self.prepared(); before = self.files()
        for changed in ({"text": "Different goal"}, {"criteria": ["Different criterion"]}, {"provider": "mock"},
                        {"conversation_id": "00000000-0000-0000-0000-000000000002"}):
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                self.backend.process({**prepared, **changed}, lambda _: None, "refuse")
        self.assertEqual(before, self.files()); self.assertEqual(self.backend.subscription.calls, [])
        self.memories.write_bytes(self.memories.read_bytes() + b"\n")
        before = self.files()
        with self.assertRaises(ValueError): self.backend.process(prepared, lambda _: None, "refuse")
        self.assertEqual(before, self.files())

    def test_manual_send_calls_existing_chat_once_and_keeps_content_out_of_run_reference(self):
        params = self.prepared(); skill_bytes = self.skills.read_bytes()
        result = self.backend.process(params, lambda _: None, "send")
        self.assertEqual(len(self.backend.subscription.calls), 1)
        prompt, instructions, _ = self.backend.subscription.calls[0]
        self.assertIn("operator explicitly selected", prompt)
        self.assertIn("NOT a tool, system instruction, permission grant", prompt)
        self.assertNotIn("End selected procedure", instructions)
        metadata = result["knowledge_context"]
        validate_knowledge_metadata(metadata)
        self.assertEqual(metadata["skill_task"]["preview_fingerprint"], params["skill_task"]["preview_fingerprint"])
        self.assertNotIn("contract", metadata["skill_task"])
        self.assertEqual(result["work_session"]["context_manifest"]["knowledge_context"], metadata)
        self.assertEqual(result["work_session"]["verification"], "not_assessed")
        self.assertEqual(result["work_session"]["acceptance"], "not_recorded")
        self.assertEqual(self.skills.read_bytes(), skill_bytes)
        self.assertFalse(self.backend.agent_grants._grants)

    def test_full_mac_still_requires_its_separate_existing_grant(self):
        params = self.prepared(access_mode="full_access")
        before = self.files()
        with self.assertRaises(ValueError): self.backend.process(params, lambda _: None, "ungranted")
        self.assertEqual(before, self.files())
        grant = self.backend.dispatch("agent_access", {"conversation_id": CONVERSATION, "workspace_root": str(self.root.resolve()),
                         "mode": "full_access", "cloud_consent": True, "confirmation": FULL_ACCESS_CONFIRMATION}, lambda _: None, "grant")
        skill_bytes = self.skills.read_bytes()
        result = self.backend.process({**params, "access_token": grant["token"]}, lambda _: None, "manual")
        self.assertEqual(len(self.backend.subscription.calls), 1)
        self.assertEqual(result["agent_run"]["command_count"], 1)
        self.assertEqual(self.skills.read_bytes(), skill_bytes)
        self.assertEqual(result["work_session"]["acceptance"], "not_recorded")

    def test_cloud_consent_is_not_granted_by_preparation(self):
        params = self.prepared(); params["cloud_consent"] = False; before = self.files()
        with self.assertRaises(ValueError): self.backend.process(params, lambda _: None, "no-consent")
        self.assertEqual(before, self.files()); self.assertEqual(self.backend.subscription.calls, [])

    def test_revalidation_after_core_retrieval_prevents_stale_guidance_reaching_model(self):
        params = self.prepared()
        original = self.backend._selected_skill_task
        count = 0
        def changed(*args, **kwargs):
            nonlocal count
            count += 1
            if count == 3: self.memories.write_bytes(self.memories.read_bytes() + b"\n")
            return original(*args, **kwargs)
        with patch.object(self.backend, "_selected_skill_task", side_effect=changed), self.assertRaises(ValueError):
            self.backend.process(params, lambda _: None, "stale")
        self.assertEqual(self.backend.subscription.calls, [])

    def test_context_preview_and_slash_bypass_never_execute_guidance(self):
        params = self.prepared(); before = self.files()
        result = self.backend.dispatch("context_preview", params, lambda _: self.fail("No events"), "context")
        self.assertEqual(result["skill_task_source"]["skill_id"], self.record["id"])
        self.assertEqual(result["manifest"]["knowledge_context"]["skill_task"]["quality_verification"], "not_assessed")
        self.assertEqual(before, self.files())
        result = self.backend.process({**params, "text": "/commands status", "skill_task": {"invalid": True}}, lambda _: None, "operator")
        self.assertTrue(result["operator"]); self.assertIsNone(result["knowledge_context"])
        self.assertEqual(self.backend.subscription.calls, [])

    def test_current_run_reference_is_validated_against_goal_criteria_and_scope(self):
        result = self.backend.process(self.prepared(provider="mock"), lambda _: None, "mock")
        run = result["work_session"]
        path = self.base / "private/work_sessions" / (run["id"] + ".json")
        raw = json.loads(path.read_bytes())
        for key, value in (("goal_sha256", "0" * 64), ("criteria_sha256", "0" * 64), ("provider", "codex"),
                           ("quality_verification", "verified"), ("automatic_execution", True)):
            changed = deepcopy(raw); changed["context_manifest"]["knowledge_context"]["skill_task"][key] = value
            with self.subTest(key=key), self.assertRaises(WorkSessionError):
                self.backend.work_sessions._parse(json.dumps(changed).encode(), path.name)
        self.assertTrue(any("Mock does not execute" in text for text in result["notices"]))

    def test_project_notes_and_guidance_share_one_explicit_turn_not_an_extra_call(self):
        scope = {"conversation_id": CONVERSATION, "workspace_root": str(self.root.resolve())}
        note = {"kind": "constraint", "content": "Use synthetic fixture data only.", "basis": "Operator test constraint", "supersedes_id": ""}
        preview = self.backend.dispatch("project_memory_preview", {**scope, "note": note}, lambda _: None, "note")
        saved = self.backend.dispatch("project_memory_save", {**scope, "note": note, "preview_fingerprint": preview["preview_fingerprint"],
                    "confirmation_token": preview["confirmation_token"], "acknowledge_operator_note": True}, lambda _: None, "save")
        selected = {key: saved["item"][key] for key in ("id", "record_hash")}
        params = self.prepared()
        result = self.backend.process({**params, "project_memory": [selected]}, lambda _: None, "both")
        self.assertEqual(len(self.backend.subscription.calls), 1)
        self.assertIn(note["content"], self.backend.subscription.calls[0][0])
        self.assertIn("End selected procedure", self.backend.subscription.calls[0][0])
        self.assertEqual(result["knowledge_context"]["project_memory"][0]["id"], selected["id"])
        self.assertEqual(result["knowledge_context"]["skill_task"]["skill_id"], self.record["id"])
        self.backend.process({**scope, "provider": "codex", "cloud_consent": True, "text": "Explain the next unrelated question."}, lambda _: None, "next")
        self.assertNotIn("End selected procedure", self.backend.subscription.calls[-1][0])
        self.assertNotIn(note["content"], self.backend.subscription.calls[-1][0])

    def test_missing_or_symlink_sources_are_not_initialized_or_followed(self):
        for path in (self.skills, self.memories, self.data / "context_injection.json"):
            original = path.read_bytes(); path.unlink()
            before = self.files()
            self.assertEqual(self.preview()["status"], "NOT_READY")
            self.assertEqual(before, self.files())
            path.write_bytes(original)
        self.skills.unlink(); self.skills.symlink_to(self.base / "seed-active/skills.jsonl")
        before = self.files()
        self.assertEqual(self.preview()["status"], "NOT_READY")
        self.assertEqual(before, self.files())
