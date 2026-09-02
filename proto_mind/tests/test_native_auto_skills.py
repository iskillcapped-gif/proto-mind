"""Automatic guidance uses verified sources, a tool-free selector and the existing turn."""
from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from proto_mind.config import ProtoMindConfig
from proto_mind.native_agent import FULL_ACCESS_CONFIRMATION
from proto_mind.native_auto_skills import AutoSkills, MAX_CATALOG, parse_selection, selection_schema, validate_auto_skills
from proto_mind.native_bridge import NativeBackend
from proto_mind.native_codex import CodexSubscription, CodexConnectionError, TurnCancelled
from proto_mind.native_work_sessions import WorkSessionStore, WorkSessionError, workspace_identity
from proto_mind.tests.test_native import FakeRPC
from proto_mind.tests.test_native_agent import FakeAgentSubscription
from proto_mind.tests import test_native_skill_inspection as fixture

CONVERSATION = fixture.CONVERSATION


class AutoSubscription(FakeAgentSubscription):
    def __init__(self, state):
        super().__init__(state)
        self.selections = []
        self.selection_result = None
        self.selection_error = None
        self.selection_hook = lambda: None

    def select_skills(self, prompt, instructions, schema, model):
        self.selections.append((prompt, instructions, schema, model))
        self.selection_hook()
        if self.selection_error:
            raise self.selection_error
        catalog = json.loads(prompt)["catalog"]
        selected = next((row for row in catalog if row.get("origin") == "learned"), catalog[0])
        data = self.selection_result or json.dumps({"skill_ids": [selected["skill_id"]],
                                                   "reason": "The procedure fits this task.", "checks": ["Observe the actual result."]})
        return {"text": data, "model": model or "fixture-model", "effort": "low"}


class AutoSkillTests(TestCase):
    seed = fixture.NativeSkillInspectionTests.seed
    files = fixture.NativeSkillInspectionTests.files

    def setUp(self):
        fixture.NativeSkillInspectionTests.setUp(self)
        self.backend.close()
        self.backend = NativeBackend(self.root, self.base / "private", subscription_factory=AutoSubscription)
        self.addCleanup(self.backend.close)
        config = patch.object(ProtoMindConfig, "from_env", return_value=ProtoMindConfig(data_dir=self.data))
        config.start(); self.addCleanup(config.stop)

    def params(self, **changes):
        return {"text": "Inspect this recurring failure and explain a bounded response.", "conversation_id": CONVERSATION,
                "provider": "codex", "model": "fixture-model", "cloud_consent": True, "auto_skills": True,
                "reasoning_effort": "high", "workspace_root": str(self.root.resolve()), **changes}

    def auto(self, **changes):
        params = self.params(**changes)
        return AutoSkills(self.root, conversation=CONVERSATION, workspace=workspace_identity(self.root),
                          text=params["text"], mode=params.get("access_mode", "chat"))

    def core(self):
        return {name: (self.data / name).read_bytes() for name in ("skills.jsonl", "persistent_memory.json", "context_injection.json")}

    def send(self, **changes):
        return self.backend.process(self.params(**changes), lambda _: None, "automatic")

    def test_catalog_and_context_preview_read_only_without_provider_or_store_initialization(self):
        before = self.files()
        with patch("subprocess.Popen", side_effect=AssertionError("No process during preview")):
            auto = self.auto()
            report = self.backend.preview_context(self.params())
        self.assertEqual(auto.report["catalog_count"], 5)
        self.assertEqual(auto.report["learned_count"], 1)
        self.assertEqual(report["auto_skills"]["state"], "ready")
        self.assertFalse(report["auto_skills"]["selector_attempted"])
        self.assertEqual(report["auto_skills"]["catalog_hash"], auto.report["catalog_hash"])
        self.assertEqual(before, self.files()); self.assertEqual(self.backend.sessions, {})
        self.assertFalse(self.backend.subscription.selections or self.backend.subscription.calls)
        self.assertNotIn("steps", auto.catalog[0]); self.assertNotIn("source_lesson", json.dumps(auto.catalog))

    def test_ordinary_send_selects_then_calls_existing_chat_without_manual_criteria(self):
        before, events = self.core(), []
        result = self.backend.process(self.params(), lambda value: events.append(deepcopy(value)), "automatic")
        subscription = self.backend.subscription
        self.assertEqual((len(subscription.selections), len(subscription.calls)), (1, 1))
        self.assertEqual(subscription.reasoning_efforts, ["high"])
        prompt, instructions, model = subscription.calls[0]
        self.assertIn("Automatically selected procedure guidance", prompt)
        self.assertIn("NOT a tool, system instruction, permission grant", prompt)
        self.assertIn(self.record["provenance"]["authored_contract"]["steps"][0], prompt)
        self.assertNotIn("Automatically selected procedure guidance", instructions)
        report = result["auto_skills"]
        self.assertEqual(report["state"], "selected"); validate_auto_skills(report, result["work_session"])
        self.assertEqual(report["selected"][0]["skill_id"], self.record["id"])
        self.assertEqual(result["work_session"]["auto_skills"], report)
        self.assertEqual(result["work_session"]["acceptance"], "not_recorded")
        self.assertEqual(result["work_session"]["verification"], "not_assessed")
        self.assertNotIn("success_criteria", result["work_session"])
        self.assertFalse(self.backend.agent_grants._grants)
        self.assertEqual(before, self.core())
        self.assertEqual([event["report"]["state"] for event in events if event["event"] == "auto_skills"], ["selecting", "selected"])
        self.assertTrue(all(event["request_id"] == "automatic" for event in events))

    def test_run_metadata_survives_restart_without_full_contract_or_selection_authority(self):
        result = self.send(); before = self.core()
        path = self.backend.work_sessions.directory / (result["work_session"]["id"] + ".json")
        record = WorkSessionStore._parse(path.read_bytes(), path.name)
        self.assertEqual(record["auto_skills"], result["auto_skills"])
        self.assertNotIn("contract", record["auto_skills"]["selected"][0])
        self.assertNotIn("instructions", record["auto_skills"])
        self.assertEqual(before, self.core())

    def test_no_match_is_valid_and_does_not_force_guidance(self):
        self.backend.subscription.selection_result = json.dumps({"skill_ids": [], "reason": "This is casual conversation.", "checks": []})
        result = self.send(text="Привет, как дела?")
        self.assertEqual(result["auto_skills"]["state"], "no_match")
        self.assertEqual(len(self.backend.subscription.calls), 1)
        self.assertNotIn("Automatically selected procedure guidance", self.backend.subscription.calls[0][0])
        self.assertIn("Earlier skill selections", self.backend.subscription.calls[0][0])

    def test_auto_off_or_mock_never_calls_selector(self):
        for changes in ({"auto_skills": False}, {"provider": "mock"}):
            self.assertIsNone(self.send(**changes)["auto_skills"])
        self.assertEqual(self.backend.subscription.selections, [])
        with self.assertRaises(ValueError): self.send(auto_skills="yes")

    def test_manual_selection_wins_over_automatic_setting(self):
        preview = self.backend.dispatch("skill_task_preview", {
            "conversation_id": CONVERSATION, "workspace_root": str(self.root.resolve()), "skill_id": self.record["id"],
            "goal": "Explain the safe procedure.", "criteria": ["Show the steps."], "provider": "codex", "access_mode": "chat",
        }, lambda _: None, "preview")
        self.assertEqual(preview["status"], "READY", preview)
        result = self.send(text="Explain the safe procedure.", criteria=["Show the steps."], skill_task={
            "skill_id": self.record["id"], "goal": "Explain the safe procedure.", "criteria": ["Show the steps."],
            "preview_fingerprint": preview["preview_fingerprint"],
        })
        self.assertIsNone(result["auto_skills"])
        self.assertEqual(self.backend.subscription.selections, [])
        self.assertEqual(result["knowledge_context"]["skill_task"]["skill_id"], self.record["id"])

    def test_slash_natural_and_exit_bypass_auto_selection(self):
        for text in ("/commands status", "что делать дальше", "exit"):
            self.assertIsNone(self.send(text=text)["auto_skills"])
        self.assertFalse(self.backend.subscription.selections or self.backend.subscription.calls)

    def test_cloud_consent_and_existing_full_access_grant_are_still_required(self):
        before = self.files()
        for changes in ({"cloud_consent": False}, {"access_mode": "full_access", "access_token": "invented"}):
            with self.assertRaises(ValueError): self.send(**changes)
        self.assertEqual(before, self.files())
        self.assertFalse(self.backend.subscription.selections or self.backend.subscription.calls)

    def test_full_mac_uses_existing_scoped_handler_and_same_effort(self):
        grant = self.backend.dispatch("agent_access", {"conversation_id": CONVERSATION, "workspace_root": str(self.root.resolve()),
            "mode": "full_access", "cloud_consent": True, "confirmation": FULL_ACCESS_CONFIRMATION}, lambda _: None, "grant")
        before = self.core()
        result = self.send(access_mode="full_access", access_token=grant["token"])
        self.assertEqual(result["agent_run"]["command_count"], 1)
        self.assertEqual(result["auto_skills"]["access_mode"], "full_access")
        self.assertEqual(self.backend.subscription.reasoning_efforts, ["high"])
        self.assertEqual(before, self.core())
        self.assertNotIn(grant["token"], json.dumps(self.backend.subscription.selections))
        self.assertNotIn(grant["token"], json.dumps(result))

    def test_grant_revoked_during_selection_prevents_target_dispatch(self):
        grant = self.backend.dispatch("agent_access", {"conversation_id": CONVERSATION, "workspace_root": str(self.root.resolve()),
            "mode": "full_access", "cloud_consent": True, "confirmation": FULL_ACCESS_CONFIRMATION}, lambda _: None, "grant")
        self.backend.subscription.selection_hook = lambda: self.backend.agent_grants.revoke(CONVERSATION)
        with self.assertRaises(ValueError): self.send(access_mode="full_access", access_token=grant["token"])
        self.assertEqual(self.backend.subscription.calls, [])

    def test_archived_legacy_tampered_and_missing_stores_do_not_supply_guidance(self):
        original = self.core()
        self.seed("archived")
        self.assertEqual(self.auto().report["learned_count"], 0)
        self.assertEqual(self.auto().report["bundled_count"], 4)
        for name, payload in original.items(): (self.data / name).write_bytes(payload)
        self.record = json.loads(original["skills.jsonl"].splitlines()[0])
        for row in ({"id": self.record["id"], "name": "legacy", "status": "active"}, {**self.record, "executable": True}):
            self.skills.write_text(json.dumps(row) + "\n")
            self.assertEqual(self.auto().report["excluded_count"], 1)
        self.skills.unlink(); before = self.files()
        self.assertEqual(self.auto().report["state"], "unavailable")
        self.assertEqual(before, self.files())

    def test_restored_verified_skill_can_be_selected_without_new_quality_claim(self):
        self.seed("restored")
        result = self.send()
        self.assertEqual(result["auto_skills"]["selected"][0]["lifecycle_state"], "active_restored_verified")
        self.assertEqual(result["auto_skills"]["quality_verification"], "not_assessed")

    def test_empty_learned_catalog_uses_starters_but_unavailable_sources_skip_selection(self):
        for payload in ("", "malformed jsonl"):
            self.skills.write_text(payload); before = self.skills.read_bytes()
            result = self.send()
            self.assertEqual(result["auto_skills"]["state"], "selected" if not payload else "unavailable")
            self.assertEqual(before, self.skills.read_bytes())
        self.assertEqual(len(self.backend.subscription.calls), 2)
        self.assertEqual(len(self.backend.subscription.selections), 1)

    def test_context_enabled_unknown_or_malformed_is_not_silently_changed(self):
        path = self.data / "context_injection.json"
        for content in ('{"enabled":true}', '{}', 'invalid', '{"enabled":false,"enabled":false}'):
            path.write_text(content); before = self.files()
            report = self.auto().report
            self.assertEqual(report["state"], "unavailable"); validate_auto_skills(report)
            self.assertEqual(before, self.files())

    def test_malformed_or_fabricated_selection_stops_before_main_turn(self):
        bad = ["not json", '{}', '{"skill_ids":[],"reason":"a","reason":"b","checks":[]}',
               json.dumps({"skill_ids": ["outside-catalog"], "reason": "test", "checks": []}),
               json.dumps({"skill_ids": [self.record["id"], self.record["id"]], "reason": "test", "checks": []}),
               json.dumps({"skill_ids": [], "reason": "test", "checks": ["claim"]}),
               json.dumps({"skill_ids": [], "reason": "test", "checks": [], "execute": True})]
        before = self.core()
        for text in bad:
            self.backend.subscription.selection_result = text
            with self.subTest(text=text), self.assertRaises(ValueError): self.send()
        self.assertEqual(before, self.core()); self.assertEqual(self.backend.subscription.calls, [])
        records = [WorkSessionStore._parse(path.read_bytes(), path.name) for path in self.backend.work_sessions.directory.glob("*.json")]
        self.assertTrue(all(row["auto_skills"]["state"] == "failed" and "dispatched_at" not in row for row in records))

    def test_stop_or_timeout_during_selection_never_starts_or_retries_main_turn(self):
        for failure in (TurnCancelled("stopped"), CodexConnectionError("timeout")):
            self.backend.subscription.selection_error = failure
            with self.subTest(failure=failure), self.assertRaises(CodexConnectionError): self.send()
        self.assertEqual(len(self.backend.subscription.selections), 2)
        self.assertEqual(self.backend.subscription.calls, [])
        self.assertIsNone(self.backend.active_request)
        self.assertFalse(self.backend.busy.locked())

    def test_store_drift_after_selection_fails_closed_without_overwriting_change(self):
        changed = self.skills.read_bytes() + b"\n"
        self.backend.subscription.selection_hook = lambda: self.skills.write_bytes(changed)
        with self.assertRaisesRegex(ValueError, "changed during review"): self.send()
        self.assertEqual(changed, self.skills.read_bytes()); self.assertEqual(self.backend.subscription.calls, [])

    def test_sources_are_rechecked_immediately_before_provider_call(self):
        original = AutoSkills.revalidate
        count = 0
        def revalidate(auto):
            nonlocal count
            count += 1
            if count == 4: self.memories.write_bytes(self.memories.read_bytes() + b"\n")
            original(auto)
        with patch.object(AutoSkills, "revalidate", revalidate), self.assertRaises(ValueError): self.send()
        self.assertEqual(count, 4); self.assertEqual(self.backend.subscription.calls, [])

    def test_selector_gets_bounded_dialogue_not_selected_files_or_private_receipts(self):
        history = [{"role": "user", "content": "history-" + str(index) + " " + "x" * 3000} for index in range(12)]
        self.send(history=history)
        payload = json.loads(self.backend.subscription.selections[0][0])
        self.assertEqual(len(payload["recent_dialogue"]), 4)
        self.assertTrue(all(len(row["content"]) <= 2000 for row in payload["recent_dialogue"]))
        self.assertNotIn("memory", payload); self.assertNotIn("steps", payload["catalog"][0])
        self.assertLess(len(json.dumps(payload)), 96_000)

    def test_report_cannot_claim_execution_acceptance_or_another_scope(self):
        result = self.send(); valid = result["auto_skills"]
        for changes in ({"permission_granted": True}, {"automatic_learning": True}, {"quality_verification": "verified"},
                        {"execution_performed": True}, {"conversation_id": "00000000-0000-0000-0000-000000000002"},
                        {"goal_sha256": "0" * 64}, {"catalog_count": True}, {"selector_attempted": False}, {"suggested_checks": ["x"] * 5}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                validate_auto_skills({**valid, **changes}, result["work_session"])

    def test_catalog_bound_is_explicit_and_stably_ordered(self):
        original = self.record
        records = [{**original, "id": f"skill-{index:03d}"} for index in range(MAX_CATALOG + 2)]
        with patch("proto_mind.native_auto_skills.NativeSkillOutcome") as source_class:
            source = source_class.return_value
            source.issues = []; source.context_disabled = True
            source.hashes = {key: "a" * 64 for key in ("skills.jsonl", "persistent_memory.json", "context_injection.json")}
            source.builder.skill_library.read_snapshot.return_value = {"records": list(reversed(records))}
            from types import SimpleNamespace
            source.verified_guidance.return_value = (original["provenance"]["authored_contract"], SimpleNamespace(state="active_verified"))
            auto = self.auto()
        self.assertEqual(auto.report["eligible_count"], MAX_CATALOG + 6)
        self.assertEqual(sum(row["origin"] == "bundled" for row in auto.catalog), 4)
        self.assertEqual(auto.report["catalog_count"], MAX_CATALOG)
        self.assertTrue(auto.report["catalog_truncated"])
        self.assertEqual([row["skill_id"] for row in auto.catalog], sorted(row["skill_id"] for row in auto.catalog))
        validate_auto_skills(auto.report)


class SelectorTransportTests(TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.state = Path(self.temp.name) / "state"
        self.rpc = FakeRPC("codex", self.state / "codex-profile", self.state / "codex-empty-workspace")
        self.subscription = CodexSubscription(self.state, transport_factory=lambda *args: self.rpc)
        self.addCleanup(self.subscription.close)
        self.answer = json.dumps({"skill_ids": ["skill"], "reason": "Relevant", "checks": []})
        self.rpc.events = [
            {"method": "item/reasoning/textDelta", "params": {"threadId": "thread", "delta": "PRIVATE"}},
            {"method": "item/completed", "params": {"threadId": "thread", "item": {"id": "answer", "type": "agentMessage", "text": self.answer}}},
            {"method": "turn/completed", "params": {"threadId": "thread", "turn": {"id": "turn", "status": "completed"}}},
        ]

    def select(self):
        return self.subscription.select_skills("catalog and task", "selector contract", selection_schema(["skill"]), "fixture-model")

    def test_ephemeral_selector_uses_structured_low_turn_without_changing_durable_thread(self):
        self.subscription.threads.record_new(CONVERSATION, "original-chat", None, mode="chat", model="fixture-model")
        before = self.subscription.threads.path.read_bytes()
        result = self.select()
        params = next(params for method, params in self.rpc.calls if method == "thread/start")
        self.assertTrue(params["ephemeral"])
        self.assertEqual(params["sandbox"], "read-only"); self.assertEqual(params["approvalPolicy"], "never")
        turn = next(params for method, params in self.rpc.calls if method == "turn/start")
        self.assertEqual(turn["outputSchema"], selection_schema(["skill"])); self.assertEqual(turn["effort"], "low")
        self.assertNotIn("dynamicTools", params); self.assertFalse(any(method == "thread/resume" for method, _ in self.rpc.calls))
        self.assertEqual(result, {"text": self.answer, "model": "fixture-model", "effort": "low"})
        self.assertEqual(before, self.subscription.threads.path.read_bytes())
        self.assertTrue(self.rpc.closed); self.assertIsNone(self.subscription.active_turn)

    def test_no_low_uses_current_model_default_not_another_model(self):
        self.rpc.model_data[0]["supportedReasoningEfforts"] = [{"reasoningEffort": "medium"}]
        self.assertEqual(self.select()["effort"], "medium")

    def test_unknown_model_or_api_key_account_refused_without_turn(self):
        for mode in ("model", "account"):
            if mode == "model": self.rpc.model_data = []
            else: self.rpc.account_type = "apiKey"
            with self.assertRaises(CodexConnectionError): self.select()
        self.assertFalse(any(method == "turn/start" for method, _ in self.rpc.calls))

    def test_inherited_instruction_or_wrong_sandbox_refuses_selector(self):
        self.rpc.instruction_sources = [{"path": "AGENTS.md"}]
        with self.assertRaises(CodexConnectionError): self.select()
        self.assertFalse(any(method == "turn/start" for method, _ in self.rpc.calls))

    def test_tool_event_is_refused_and_transport_closed_without_main_call(self):
        self.rpc.events.insert(0, {"method": "item/started", "params": {"threadId": "thread", "item": {"type": "commandExecution"}}})
        with self.assertRaisesRegex(CodexConnectionError, "Non-chat"): self.select()
        self.assertTrue(self.rpc.closed)
        self.assertTrue(any(method == "turn/interrupt" for method, _ in self.rpc.calls))

    def test_stop_before_selection_makes_no_provider_request(self):
        self.subscription.cancelled.set()
        with self.assertRaises(TurnCancelled): self.select()
        self.assertEqual(self.rpc.calls, [])

    def test_stop_during_selection_interrupts_ephemeral_turn(self):
        original = self.rpc.next_event
        def cancelled(timeout):
            self.subscription.cancelled.set()
            return original(timeout)
        self.rpc.next_event = cancelled
        with self.assertRaises(TurnCancelled): self.select()
        self.assertTrue(any(method == "turn/interrupt" for method, _ in self.rpc.calls))
        self.assertTrue(self.rpc.closed)

    def test_selector_response_limit_refuses_excessive_output(self):
        self.rpc.events[1]["params"]["item"]["text"] = "x" * 6001
        with self.assertRaises(CodexConnectionError): self.select()
        self.assertTrue(self.rpc.closed)
