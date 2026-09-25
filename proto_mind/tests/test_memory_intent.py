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

    def test_lets_use_is_a_task_instruction_not_a_project_decision(self):
        self.keeper.context_scope = "project-a"
        first = self.coordinator.handle("Мы решили использовать unittest для тестов проекта.")
        for text in ["Давай использовать pytest вместо unittest в этом тесте.",
                     "Let's use pytest instead of unittest for this test.",
                     "Давай використовувати pytest замість unittest у цьому тесті."]:
            with self.subTest(text=text):
                result = self.coordinator.handle(text)
                self.assertFalse(result.memory_summary.should_store)
                self.assertEqual(result.memory_summary.superseded_record_ids, [])
        stored = self.store.load_working_memory() + self.store.load_persistent_memory()
        self.assertTrue(all(r.active for r in stored if r.content == first.memory_summary.content))
        self.assertTrue(self.coordinator.handle("Переходим на pytest вместо unittest для тестов проекта.")
                        .memory_summary.superseded_record_ids)

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

    def test_long_paste_is_not_captured_as_one_memory(self):
        for text in ["Мы решили использовать SQLite для заказов. " + "Подробности отчёта. " * 1200,
                     "Ключевой вывод: " + "строка журнала\n" * 1500]:
            with self.subTest(text=text[:30]):
                result = self.coordinator.handle(text)
                self.assertFalse(result.memory_summary.should_store)
                self.assertIn("too long", result.memory_summary.storage_rationale)
        self.assertEqual(self.store.load_working_memory() + self.store.load_persistent_memory(), [])
        self.assertTrue(self.coordinator.handle("Мы решили использовать SQLite для заказов.").memory_summary.should_store)

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

    def test_task_descriptions_that_mention_memory_are_not_memory_inventory(self):
        for text in ["Посмотри модуль памяти. Что изменилось?",
                     "Can you fix the failing test? What changed in memory?",
                     "Брат, мы пофиксили баги. Пройдись посмотри ещё раз, что изменилось в памяти?",
                     "Please open the memory store and check the current implementation. What changed?",
                     "Брат, посмотри реальный код проекта, познакомься с архитектурой и предложи, как сделать PM лучше. "
                     "Документацию сверяй с кодом. Нас интересуют: что уже сделано хорошо; слабые места; идеи про память "
                     "и параллельные задачи. Какой этап ты бы выбрал?",
                     "Нас интересует, что уже сделано хорошо и что стоит улучшить. Посмотри, как используется память "
                     "в ядре, какие модули за неё отвечают, где хранятся данные и как работает синхронизация между окнами. "
                     "Отдельно интересны параллельные задачи и взаимодействие моделей. Что бы ты выбрал?"]:
            with self.subTest(text=text[:40]): self.assertNotEqual(Observer().analyze(text).query_type, "memory_inventory")
        # Explicit questions about remembered decisions stay memory questions inside a work request.
        for text in ["Посмотри, что мы решили про хранение памяти.", "Fix the bug. What did we decide about persistence?",
                     "What storage system are we using now?", "Что изменилось в нашем решении по хранению памяти?"]:
            with self.subTest(text=text): self.assertEqual(Observer().analyze(text).query_type, "memory_inventory")
