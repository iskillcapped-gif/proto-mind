"""Native Persona preview boundary tests on disposable local state."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

from proto_mind import native_bridge as bridge
from proto_mind.config import ProtoMindConfig
from proto_mind.identity import IdentityStore
from proto_mind.native_agent import FULL_ACCESS_CONFIRMATION
from proto_mind.native_persona import validate_native_persona_preview
from proto_mind.persona_activation_readiness import validate_persona_activation_readiness
from proto_mind.persona_engine import PersonaValidationError
from proto_mind.tests.test_native import FakeSubscription


class NativePersonaPreviewTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="proto-native-persona-")
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name).resolve()
        self.root = self.base / "core"
        self.state = self.base / "private"
        self.workspace = self.base / "workspace"
        self.workspace.mkdir()
        self.conversation = str(uuid4())
        self.backend = bridge.NativeBackend(self.root, self.state, subscription_factory=FakeSubscription)
        self.addCleanup(self.backend.close)
        config = patch.object(
            ProtoMindConfig,
            "from_env",
            return_value=ProtoMindConfig(ollama_model="qwen-fixture", data_dir=self.root / "proto_mind/data"),
        )
        config.start()
        self.addCleanup(config.stop)

    def files(self):
        return {
            str(path.relative_to(self.base)): path.read_bytes()
            for path in self.base.rglob("*")
            if path.is_file() and not path.is_symlink()
        }

    def params(self, **changes):
        value = {
            "conversation_id": self.conversation,
            "provider": "mock",
            "model": "",
            "cloud_consent": False,
            "access_mode": "chat",
            "workspace_root": str(self.workspace),
        }
        value.update(changes)
        return value

    def preview(self, **changes):
        return self.backend.dispatch(
            "persona_preview",
            self.params(**changes),
            lambda _: self.fail("Persona preview emitted an event"),
            "persona-preview",
        )

    def test_missing_identity_preview_is_read_only_and_runs_no_engine(self):
        before = self.files()
        with patch.object(self.backend, "_coordinator", side_effect=AssertionError("No cognitive turn")):
            result = self.preview()
        self.assertEqual(validate_native_persona_preview(result), result)
        self.assertTrue(result["read_only"] and result["no_execution"])
        self.assertTrue(result["no_model_call"] and result["no_retrieval"] and result["no_store_write"])
        self.assertFalse(result["production_prompt_active"] or result["private_reasoning_included"])
        self.assertEqual(result["snapshot"]["identity"]["source_version"], "missing")
        self.assertEqual(result["snapshot"]["communication_preferences"], [])
        self.assertEqual(result["snapshot"]["relevant_memories"], [])
        self.assertFalse(result["snapshot"]["authorizes_actions"])
        self.assertEqual(before, self.files())
        self.assertFalse(self.root.exists() or self.state.exists())
        self.assertEqual(self.backend.subscription.calls, [])

    def test_existing_identity_is_projected_without_private_operator_name_or_write(self):
        store = IdentityStore.from_project_root(self.root)
        store.format_status()
        store.set_profile_field("name", "Proto-Mind")
        store.set_profile_field("style", "Warm and truthful")
        store.set_profile_field("operator_name", "PRIVATE OPERATOR")
        store.add_item("principles", "Prefer explicit evidence.")
        before = self.files()
        result = self.preview(provider="ollama", model="")
        serialized = json.dumps(result, ensure_ascii=False)
        self.assertEqual(result["snapshot"]["self_model"]["provider"], "ollama")
        self.assertEqual(result["snapshot"]["self_model"]["model"], "qwen-fixture")
        self.assertIn("Prefer explicit evidence.", serialized)
        self.assertNotIn("PRIVATE OPERATOR", serialized)
        self.assertEqual(before, self.files())
        self.assertEqual(self.backend.subscription.calls, [])

    def test_codex_chat_never_claims_tools_or_full_access(self):
        result = self.preview(provider="codex", model="gpt-5.6-sol", cloud_consent=True)
        runtime = result["snapshot"]["self_model"]
        self.assertEqual(runtime["access_mode"], "chat")
        self.assertEqual(runtime["tools"], [])
        self.assertFalse(runtime["can_write_workspace"])
        self.assertFalse(runtime["can_control_computer"])
        self.assertFalse(runtime["can_use_web"])
        self.assertFalse(result["source_summary"]["full_access_grant_verified"])
        self.assertEqual(self.backend.subscription.calls, [])

    def test_full_access_requires_and_reports_only_a_current_grant(self):
        params = self.params(
            provider="codex",
            model="gpt-5.6-sol",
            cloud_consent=True,
            access_mode="full_access",
        )
        with self.assertRaisesRegex(ValueError, "missing or expired"):
            self.backend.preview_persona(params)
        grant = self.backend.agent_grants.enable(self.conversation, self.workspace, FULL_ACCESS_CONFIRMATION)
        self.backend._last_bootstrap_computer_use = {"available": True}
        before = self.files()
        with patch("proto_mind.native_bridge.public_computer_use_capability", side_effect=AssertionError("No discovery during preview")):
            result = self.backend.preview_persona({**params, "access_token": grant["token"]})
        runtime = result["snapshot"]["self_model"]
        self.assertEqual(runtime["access_mode"], "full_access")
        self.assertEqual(runtime["authorization_source"], "operator_explicit_turn_grant")
        self.assertEqual(runtime["tools"], ["computer_use", "shell_and_files", "web_search"])
        self.assertTrue(runtime["can_write_workspace"] and runtime["can_control_computer"] and runtime["can_use_web"])
        self.assertFalse(result["snapshot"]["authorizes_actions"])
        serialized = json.dumps(result, ensure_ascii=False)
        self.assertNotIn(grant["token"], serialized)
        self.assertNotIn(str(self.workspace), serialized)
        self.assertEqual(before, self.files())
        self.assertEqual(self.backend.subscription.calls, [])

    def test_invalid_or_widened_requests_fail_without_writes(self):
        cases = (
            {"provider": "unknown"},
            {"model": "bad\nmodel"},
            {"cloud_consent": "yes"},
            {"conversation_id": "not-a-uuid"},
            {"access_mode": "operator"},
            {"access_token": "unexpected-in-chat"},
            {"extra": True},
        )
        before = self.files()
        for change in cases:
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.preview(**change)
        self.assertEqual(before, self.files())
        self.assertEqual(self.backend.subscription.calls, [])

    def test_context_injection_state_is_visible_but_never_changed(self):
        path = self.root / "proto_mind/data/context_injection.json"
        path.parent.mkdir(parents=True)
        for value, expected in (({"enabled": False}, "disabled"), ({"enabled": True}, "enabled")):
            path.write_text(json.dumps(value), encoding="utf-8")
            before = path.read_bytes()
            result = self.preview()
            self.assertEqual(result["context_injection_state"], expected)
            self.assertFalse(result["context_injection_changed"])
            self.assertEqual(path.read_bytes(), before)
        path.write_text("broken", encoding="utf-8")
        before = path.read_bytes()
        self.assertEqual(self.preview()["context_injection_state"], "unknown")
        self.assertEqual(path.read_bytes(), before)

    def test_preview_validator_rejects_safety_hash_and_runtime_tampering(self):
        result = self.preview()
        changes = []
        for field, value in (
            ("read_only", False),
            ("no_model_call", False),
            ("production_prompt_active", True),
            ("private_reasoning_included", True),
        ):
            changed = deepcopy(result)
            changed[field] = value
            changes.append(changed)
        changed = deepcopy(result)
        changed["snapshot"]["snapshot_hash"] = "0" * 64
        changes.append(changed)
        changed = deepcopy(result)
        changed["snapshot"]["self_model"]["tools"] = ["shell_and_files"]
        changes.append(changed)
        changed = deepcopy(result)
        changed["source_summary"]["memory"] = "all_memory"
        changes.append(changed)
        for changed in changes:
            with self.subTest(change=changed), self.assertRaises(PersonaValidationError):
                validate_native_persona_preview(changed)

    def test_provider_readiness_is_visible_read_only_and_runs_no_engine(self):
        before = self.files()
        params = self.params(provider="codex", model="gpt-5.6-sol", cloud_consent=True)
        with patch.object(self.backend, "_coordinator", side_effect=AssertionError("No cognitive turn")):
            result = self.backend.dispatch("persona_readiness", params, lambda _: self.fail("event"), "readiness")
        self.assertEqual(validate_persona_activation_readiness(result), result)
        self.assertEqual(result["status"], "READY")
        self.assertEqual(result["selected_provider"], "codex_subscription")
        self.assertTrue(result["selected_adapter_ready"])
        self.assertEqual(result["parity"]["activation_providers"], ["codex_subscription", "ollama"])
        self.assertTrue(result["parity"]["mock_control_only"])
        self.assertTrue(result["read_only"] and result["no_model_call"] and result["no_retrieval"])
        self.assertFalse(result["activation_performed"] or result["context_injection_changed"])
        self.assertEqual(before, self.files())
        self.assertEqual(self.backend.subscription.calls, [])

    def test_readiness_blocks_existing_context_injection_without_changing_it(self):
        path = self.root / "proto_mind/data/context_injection.json"
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps({"enabled": True}), encoding="utf-8")
        before = path.read_bytes()
        result = self.backend.preview_persona_readiness(self.params(provider="ollama", model="qwen-fixture"))
        self.assertEqual(result["status"], "NOT_READY")
        self.assertEqual(result["context_injection_state"], "enabled")
        self.assertTrue(result["blockers"])
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(self.backend.subscription.calls, [])

    def test_readiness_never_exposes_full_access_token_or_workspace_path(self):
        grant = self.backend.agent_grants.enable(self.conversation, self.workspace, FULL_ACCESS_CONFIRMATION)
        self.backend._last_bootstrap_computer_use = {"available": True}
        result = self.backend.preview_persona_readiness(self.params(
            provider="codex",
            model="gpt-5.6-sol",
            cloud_consent=True,
            access_mode="full_access",
            access_token=grant["token"],
        ))
        serialized = json.dumps(result, ensure_ascii=False)
        self.assertEqual(result["status"], "READY")
        self.assertNotIn(grant["token"], serialized)
        self.assertNotIn(str(self.workspace), serialized)
        codex = result["adapters"][0]
        self.assertEqual(codex["access_mode"], "full_access")
        self.assertEqual(codex["provider_safety_boundary"], "developer_instructions_separate")


if __name__ == "__main__":
    unittest.main()
