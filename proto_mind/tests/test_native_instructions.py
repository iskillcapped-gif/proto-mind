"""Local Native instruction inspection without provider calls or store writes."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

from proto_mind import native_bridge as bridge
from proto_mind.config import ProtoMindConfig
from proto_mind.models import MemoryRecord
from proto_mind.native_agent import AGENT_INSTRUCTIONS
from proto_mind.native_codex import CHAT_DEVELOPER_INSTRUCTIONS
from proto_mind.native_instructions import (
    NativeInstructionError,
    build_instruction_preview,
    legacy_subscription_instructions,
    prepare_local_instructions,
    validate_instruction_preview,
)
from proto_mind.observer import Observer
from proto_mind.persona_activation import PersonaTurnActivation
from proto_mind.persona_engine import PersonaRuntimeContext
from proto_mind.reasoners.ollama_reasoner import OllamaReasoner
from proto_mind.tests.test_native import FakeSubscription


class NativeInstructionContractTests(unittest.TestCase):
    def setUp(self):
        self.observer = Observer().analyze("What do you remember about my response preference?")
        self.memory = MemoryRecord(
            id="instruction-memory-1",
            content="The operator prefers evidence before conclusions.",
            type="preference",
            importance=0.9,
            source="operator",
            tags=["memory", "response_style", "preference"],
        )

    def prepared(self, provider="codex", *, activation=None):
        return prepare_local_instructions(
            provider,
            self.observer,
            [self.memory],
            ["State uncertainty explicitly."],
            persona_activation=activation,
        )

    def test_codex_chat_preview_contains_exact_two_local_layers_and_hashes(self):
        prepared = self.prepared()
        preview = build_instruction_preview(
            provider="codex",
            mode="chat",
            operator=False,
            prepared=prepared,
            developer_instructions=CHAT_DEVELOPER_INSTRUCTIONS,
            selected_memory=[self.memory],
            correction_hints=["State uncertainty explicitly."],
            retrieval_performed=True,
        )

        self.assertIs(validate_instruction_preview(preview), preview)
        self.assertEqual([item["id"] for item in preview["layers"]], ["base_instructions", "developer_instructions"])
        self.assertEqual(preview["layers"][0]["text"], prepared.text)
        self.assertEqual(preview["layers"][1]["text"], CHAT_DEVELOPER_INSTRUCTIONS)
        self.assertEqual(preview["layers"][0]["sha256"], hashlib.sha256(prepared.text.encode()).hexdigest())
        self.assertEqual(preview["persona_state"], "legacy")
        self.assertFalse(preview["provider_owned_instructions"]["available_to_proto_mind"])
        self.assertFalse(preview["private_reasoning_included"])

    def test_full_mac_and_ollama_project_their_actual_distinct_placements(self):
        codex = build_instruction_preview(
            provider="codex",
            mode="full_access",
            operator=False,
            prepared=self.prepared(),
            developer_instructions=AGENT_INSTRUCTIONS,
            selected_memory=[self.memory],
            correction_hints=["State uncertainty explicitly."],
            retrieval_performed=True,
        )
        ollama_prepared = self.prepared("ollama")
        ollama = build_instruction_preview(
            provider="ollama",
            mode="chat",
            operator=False,
            prepared=ollama_prepared,
            developer_instructions=None,
            selected_memory=[self.memory],
            correction_hints=["State uncertainty explicitly."],
            retrieval_performed=True,
        )

        self.assertEqual(codex["layers"][1]["source"], "full_mac_static_contract")
        self.assertEqual(codex["layers"][1]["text"], AGENT_INSTRUCTIONS)
        self.assertEqual([item["placement"] for item in ollama["layers"]], ["ollama_system_message"])
        expected = OllamaReasoner(ProtoMindConfig())._build_system_prompt(
            self.observer, [self.memory], ["State uncertainty explicitly."],
        )
        self.assertEqual(ollama["layers"][0]["text"], expected)

    def test_operator_and_mock_routes_have_no_fabricated_instruction_layer(self):
        operator = build_instruction_preview(
            provider="codex", mode="full_access", operator=True,
            prepared=None, developer_instructions=None,
        )
        mock = build_instruction_preview(
            provider="mock", mode="chat", operator=False,
            prepared=None, developer_instructions=None,
        )

        for preview in (operator, mock):
            self.assertEqual(preview["layers"], [])
            self.assertEqual(preview["persona_state"], "bypassed")
            self.assertFalse(preview["recomputed_on_send"])
            self.assertTrue(preview["no_model_call"] and preview["no_store_write"])

    def test_persona_projection_is_labelled_brother_without_persistence(self):
        with tempfile.TemporaryDirectory(prefix="instruction-persona-") as temporary:
            root = Path(temporary) / "project"
            activation = PersonaTurnActivation(
                project_root=root.resolve(),
                runtime=PersonaRuntimeContext(
                    provider="codex_subscription",
                    model="fixture-model",
                    access_mode="chat",
                    workspace_id="unbound",
                    workspace_label="unbound",
                    network_state="disabled",
                ),
                context_injection_state="default_disabled",
                readiness_hash="a" * 64,
            )
            preview = build_instruction_preview(
                provider="codex",
                mode="chat",
                operator=False,
                prepared=self.prepared(activation=activation),
                developer_instructions=CHAT_DEVELOPER_INSTRUCTIONS,
                selected_memory=[self.memory],
                correction_hints=["State uncertainty explicitly."],
                retrieval_performed=True,
            )

            self.assertEqual(preview["persona_state"], "brother")
            self.assertEqual(preview["layers"][0]["source"], "brother_persona_current_projection")
            self.assertIn("Proto-Mind Persona Context v1", preview["layers"][0]["text"])
            self.assertFalse(root.exists())

    def test_projection_refuses_text_hash_shape_and_canonical_material_tampering(self):
        preview = build_instruction_preview(
            provider="codex",
            mode="chat",
            operator=False,
            prepared=self.prepared(),
            developer_instructions=CHAT_DEVELOPER_INSTRUCTIONS,
            selected_memory=[self.memory],
            correction_hints=["State uncertainty explicitly."],
            retrieval_performed=True,
        )
        mutations = (
            ("layer text", lambda row: row["layers"][0].__setitem__("text", "changed")),
            ("layer hash", lambda row: row["layers"][0].__setitem__("sha256", "0" * 64)),
            ("provider boundary", lambda row: row["provider_owned_instructions"].__setitem__("included", True)),
            ("projection hash", lambda row: row.__setitem__("projection_hash", "0" * 64)),
            ("material", lambda row: row.__setitem__("hash_material", "{}")),
        )
        for label, mutate in mutations:
            changed = deepcopy(preview)
            mutate(changed)
            with self.subTest(label=label), self.assertRaises(NativeInstructionError):
                validate_instruction_preview(changed)

    def test_legacy_codex_builder_remains_byte_compatible(self):
        raw = OllamaReasoner(ProtoMindConfig())._build_system_prompt(
            self.observer, [self.memory], ["State uncertainty explicitly."],
        )
        self.assertEqual(self.prepared().text, legacy_subscription_instructions(raw))


class NativeInstructionBridgeTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="instruction-bridge-")
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.root = self.base / "project"
        self.state = self.base / "private"
        self.data = self.root / "proto_mind/data"
        self.data.mkdir(parents=True)
        self.memory = MemoryRecord(
            id="bridge-memory-1",
            content="The operator prefers evidence before conclusions.",
            type="preference",
            importance=1.0,
            source="operator",
            tags=["memory", "response_style", "preference"],
        )
        (self.data / "persistent_memory.json").write_text(
            json.dumps([self.memory.to_dict()]), encoding="utf-8",
        )
        self.backend = bridge.NativeBackend(self.root, self.state, subscription_factory=FakeSubscription)
        self.addCleanup(self.backend.close)
        config = patch.object(ProtoMindConfig, "from_env", return_value=ProtoMindConfig(data_dir=self.data))
        config.start()
        self.addCleanup(config.stop)

    def files(self):
        return {
            str(path.relative_to(self.base)): path.read_bytes()
            for path in self.base.rglob("*") if path.is_file()
        }

    def test_context_preview_runs_only_read_only_core_retrieval_and_never_contacts_provider(self):
        conversation = str(uuid4())
        coordinator = self.backend._coordinator(conversation)
        coordinator.pending_correction_hints = ["Carry this verified correction once."]
        before = self.files()

        result = self.backend.preview_context({
            "text": "What do you remember about my response preference?",
            "conversation_id": conversation,
            "provider": "codex",
            "model": "fixture-model",
            "cloud_consent": False,
            "persona_enabled": False,
            "history": [],
        })

        preview = result["instruction_preview"]
        self.assertTrue(preview["read_only_retrieval_performed"])
        self.assertEqual(preview["selected_memory_ids"], [self.memory.id])
        self.assertIn(self.memory.content, preview["layers"][0]["text"])
        self.assertIn("Carry this verified correction once.", preview["layers"][0]["text"])
        self.assertEqual(result["manifest"]["recall"], "read_only_current_projection_recomputed_at_send")
        self.assertEqual(self.backend.subscription.calls, [])
        self.assertFalse(self.state.exists())
        self.assertEqual(before, self.files())


if __name__ == "__main__":
    unittest.main()
