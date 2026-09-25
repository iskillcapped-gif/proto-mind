"""Ordinary work must not become an unrelated durable-memory mutation."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from proto_mind.coordinator import Coordinator
from proto_mind.memory_keeper import MemoryKeeper
from proto_mind.memory_store import MemoryStore
from proto_mind.models import MemoryRecord
from proto_mind.observer import Observer
from proto_mind.reasoners.mock_reasoner import MockReasoner


class MemoryIntentTests(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory(); self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        self.store = MemoryStore(root / "working.json", root / "persistent.json")
        self.keeper = MemoryKeeper(self.store)
        self.coordinator = Coordinator(Observer(), self.keeper, MockReasoner())

    def test_temporary_instruction_does_not_store_or_supersede_decisions(self):
        records = [MemoryRecord(text, "decision", .9, "fixture", tags=tags) for text, tags in [
            ("Use SQLite for accounting", ["sqlite", "decision"]),
            ("Release on Fridays", ["release", "decision"])]]
        with self.store.transaction(): self.store.save_persistent_memory(records)
        for text in ["Перепиши функцию вместо старой реализации, используй async",
                     "Rewrite the function instead of the old implementation.",
                     "Перепиши функцію замість старої реалізації."]:
            with self.subTest(text=text):
                result = self.coordinator.handle(text)
                self.assertFalse(result.memory_summary.should_store)
                self.assertTrue(all(r.active for r in self.store.load_persistent_memory()))

    def test_replacement_requires_specific_target_and_same_project(self):
        self.keeper.context_scope = "project-a"
        first = self.coordinator.handle("Мы решили использовать JSON для хранения памяти.")
        self.keeper.context_scope = "project-b"
        self.coordinator.handle("Теперь используем SQLite вместо JSON для хранения памяти.")
        self.assertTrue(next(r for r in self.store.load_working_memory() if r.id == first.memory_summary.stored_record_id).active)
        self.keeper.context_scope = "project-a"
        changed = self.coordinator.handle("Теперь используем SQLite вместо JSON для хранения памяти.")
        self.assertIn(first.memory_summary.stored_record_id, changed.memory_summary.superseded_record_ids)
        self.assertTrue(all(r.active for r in self.store.load_persistent_memory() if r.context_scope == "project-b"))
        selected = self.keeper.retrieve(Observer().analyze("Что используем сейчас для хранения памяти?"))
        self.assertFalse(any(r.context_scope == "project-b" for r in selected))

    def test_ambiguous_replacement_keeps_both_decisions_active(self):
        for text in ["Мы решили использовать JSON для настроек.", "Мы решили использовать JSON для экспорта."]:
            self.coordinator.handle(text)
        changed = self.coordinator.handle("Теперь используем SQLite вместо JSON.")
        self.assertEqual(changed.memory_summary.superseded_record_ids, [])
        self.assertTrue(all(r.active for r in self.store.load_persistent_memory()))

    def test_work_requests_are_not_memory_inventory(self):
        for text in ["Fix the memory backend implementation. What changed in the code?",
                     "Please review the current implementation and fix the bug.",
                     "Исправь память. Что изменилось в реализации?",
                     "Перевір код пам'яті. Що змінилося?"]:
            with self.subTest(text=text): self.assertNotEqual(Observer().analyze(text).query_type, "memory_inventory")
        self.assertEqual(Observer().analyze("Что ты помнишь о моих предпочтениях?").query_type, "memory_inventory")

