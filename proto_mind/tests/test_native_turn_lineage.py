from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from uuid import uuid4

from proto_mind.native_instructions import build_instruction_receipt, PreparedLocalInstructions
from proto_mind.native_turn_lineage import (
    NativeTurnLineageError,
    build_turn_receipt,
    validate_turn_receipt,
)
from proto_mind.native_work_sessions import WorkSessionError, WorkSessionStore


class NativeTurnLineageTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="proto-native-turn-lineage-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / "project"
        self.root.mkdir()
        self.state = Path(temporary.name) / "state"
        self.conversation = str(uuid4())
        self.run_id = str(uuid4())
        self.prompt = "Проверь связь ответа с запуском."
        self.answer = "Связь подтверждена локальными хешами."
        self.instruction = build_instruction_receipt(
            provider="codex",
            mode="chat",
            prepared=PreparedLocalInstructions("local instructions", "legacy_cognitive_core_current_projection", None),
            developer_instructions="local developer contract",
        )

    def record(self):
        return {
            "id": self.run_id,
            "conversation_id": self.conversation,
            "provider": "codex",
            "access_mode": "chat",
            "status": "completed",
            "input_chars": len(self.prompt),
            "input_sha256": hashlib.sha256(self.prompt.encode()).hexdigest(),
            "answer_preview": self.answer,
            "instruction_receipt": self.instruction,
        }

    def test_receipt_is_content_free_stable_and_strict(self):
        receipt = build_turn_receipt(work_session=self.record(), response=self.answer)
        self.assertIs(validate_turn_receipt(receipt), receipt)
        self.assertTrue(receipt["content_free"])
        self.assertFalse(receipt["input_text_stored"])
        self.assertFalse(receipt["response_text_stored"])
        serialized = json.dumps(receipt, ensure_ascii=False)
        self.assertNotIn(self.prompt, serialized)
        self.assertNotIn(self.answer, serialized)
        self.assertEqual(receipt, build_turn_receipt(work_session=self.record(), response=self.answer))

        for field, value in (
            ("response_observed", False),
            ("task_success_verified", True),
            ("response_sha256", "0" * 64),
            ("receipt_hash", "0" * 64),
            ("hash_material", "{}"),
        ):
            changed = deepcopy(receipt)
            changed[field] = value
            with self.subTest(field=field), self.assertRaises(NativeTurnLineageError):
                validate_turn_receipt(changed)
        with_text = deepcopy(receipt)
        with_text["response_text"] = self.answer
        with self.assertRaises(NativeTurnLineageError):
            validate_turn_receipt(with_text)

    def test_real_provider_completion_persists_receipt_and_old_mock_record_stays_valid(self):
        store = WorkSessionStore(self.state, self.root)
        with store.begin(
            run_id=self.run_id,
            conversation_id=self.conversation,
            text=self.prompt,
            provider="codex",
            model="fixture",
            effort="high",
            mode="chat",
            workspace=None,
            sources=[],
        ) as run:
            run.dispatch()
            completed = run.complete(self.answer, instruction_receipt=self.instruction)
        receipt = completed["turn_receipt"]
        self.assertEqual(receipt["run_id"], self.run_id)
        self.assertEqual(receipt["response_sha256"], hashlib.sha256(self.answer.encode()).hexdigest())
        self.assertNotIn(self.answer, json.dumps(receipt, ensure_ascii=False))
        self.assertEqual(store.page(self.conversation)["runs"][0]["turn_receipt"], receipt)

        legacy_id = str(uuid4())
        with store.begin(
            run_id=legacy_id,
            conversation_id=self.conversation,
            text="legacy mock",
            provider="mock",
            model="",
            effort="",
            mode="chat",
            workspace=None,
            sources=[],
        ) as run:
            run.dispatch()
            legacy = run.complete("legacy response")
        self.assertNotIn("turn_receipt", legacy)
        self.assertEqual(len(store.page(self.conversation)["runs"]), 2)

    def test_tampered_receipt_is_diagnostic_and_never_rewritten(self):
        store = WorkSessionStore(self.state, self.root)
        with store.begin(
            run_id=self.run_id,
            conversation_id=self.conversation,
            text=self.prompt,
            provider="codex",
            model="fixture",
            effort="high",
            mode="chat",
            workspace=None,
            sources=[],
        ) as run:
            run.dispatch()
            run.complete(self.answer, instruction_receipt=self.instruction)
        path = store.directory / f"{self.run_id}.json"
        record = json.loads(path.read_bytes())
        record["turn_receipt"]["response_sha256"] = "0" * 64
        path.write_text(json.dumps(record))
        before = path.read_bytes()
        page = store.page(self.conversation)
        self.assertEqual(page["runs"], [])
        self.assertTrue(page["warnings"])
        self.assertEqual(path.read_bytes(), before)

    def test_receipt_failure_does_not_save_invalid_completed_state(self):
        store = WorkSessionStore(self.state, self.root)
        bad = deepcopy(self.instruction)
        bad["receipt_hash"] = "0" * 64
        with self.assertRaises(WorkSessionError):
            with store.begin(
                run_id=self.run_id,
                conversation_id=self.conversation,
                text=self.prompt,
                provider="codex",
                model="fixture",
                effort="high",
                mode="chat",
                workspace=None,
                sources=[],
            ) as run:
                run.dispatch()
                run.complete(self.answer, instruction_receipt=bad)
        reopened = store.page(self.conversation)["runs"][0]
        self.assertEqual(reopened["display_status"], "unknown")
        self.assertNotIn("turn_receipt", reopened)


if __name__ == "__main__":
    unittest.main()
