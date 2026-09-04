"""Ukrainian memory intent, storage, supersession and retrieval as one flow."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unicodedata
import unittest

from proto_mind.memory_keeper import MemoryKeeper
from proto_mind.memory_store import MemoryStore
from proto_mind.observer import Observer
from proto_mind.topic_utils import extract_topic_tags


class UkrainianMemoryTests(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        self.store = MemoryStore(root / "working.json", root / "persistent.json")
        self.keeper = MemoryKeeper(self.store)
        self.observer = Observer()

    def remember(self, text):
        state = self.observer.analyze(text)
        summary = self.keeper.evaluate_interaction(text, "The model answer must not become memory.", state, [])
        self.assertTrue(summary.should_store, (text, state))
        return self.keeper.apply_memory_updates(summary)

    def test_inventory_normalizes_typographic_apostrophes_case_and_unicode(self):
        expected = self.observer.analyze("Що ти пам'ятаєш?")
        self.assertEqual(expected.query_type, "memory_inventory")
        self.assertTrue(expected.needs_memory)
        self.assertIn("memory", expected.topic_tags)
        for apostrophe in ("'", "’", "ʼ", "‘", "`"):
            for text in (f"ЩО ТИ ПАМ{apostrophe}ЯТАЄШ?", unicodedata.normalize("NFD", f"Що ти пам{apostrophe}ятаєш?")):
                with self.subTest(text=text):
                    self.assertEqual(self.observer.analyze(text), expected)

    def test_ordinary_continuity_requests_use_memory_without_becoming_new_facts(self):
        for text in ("Продовжимо роботу.", "Продовжуємо роботу над проєктом.", "Як ми обговорювали, продовжимо з інтерфейсу.", "Нагадай мені про проєкт."):
            with self.subTest(text=text):
                state = self.observer.analyze(text)
                self.assertEqual(state.query_type, "continuity_followup")
                self.assertTrue(state.needs_memory)
                summary = self.keeper.evaluate_interaction(text, "", state, [])
                self.assertFalse(summary.should_store)

    def test_decisions_supersede_and_current_and_historical_recall_stay_distinct(self):
        old = self.remember("Ми вирішили використовувати JSON для зберігання пам’яті.")
        new = self.remember("Тепер використовуємо SQLite замість JSON для зберігання пам’яті.")
        self.assertTrue(new.override_detected)
        self.assertIn(old.stored_record_id, new.superseded_record_ids)
        self.assertEqual(new.stored_record_type, "decision")
        current_text = "Яку систему зберігання використовуємо зараз?"
        current_state = self.observer.analyze(current_text)
        self.assertEqual(current_state.query_type, "memory_inventory")
        current = self.keeper.retrieve(current_state, user_input=current_text)
        self.assertTrue(current)
        self.assertTrue(current[0].active)
        self.assertIn("SQLite", current[0].content)
        historical_text = "Що використовували раніше для зберігання пам’яті?"
        historical = self.keeper.retrieve(self.observer.analyze(historical_text), user_input=historical_text)
        self.assertFalse(historical[0].active)
        self.assertIn("JSON", historical[0].content)

    def test_preference_is_stored_and_found_across_ukrainian_and_russian(self):
        self.remember("Я віддаю перевагу коротким відповідям.")
        before = {path: path.read_bytes() for path in self.store.persistent_path.parent.iterdir()}
        for text in ("Який стиль відповіді використовувати в майбутньому?", "Какой стиль ответа использовать?"):
            with self.subTest(text=text):
                state = self.observer.analyze(text)
                self.assertTrue(state.needs_memory)
                records = self.keeper.retrieve(state, user_input=text)
                self.assertEqual(records[0].type, "preference")
                self.assertIn("коротким відповідям", records[0].content)
                self.assertFalse(self.keeper.evaluate_interaction(text, "", state, records).should_store)
        self.assertEqual({path: path.read_bytes() for path in before}, before)
        self.assertTrue({"short", "response_style"} <= set(extract_topic_tags("коротким відповідям")))

    def test_explicit_remember_request_keeps_original_text_as_a_fact(self):
        text = "Запам’ятай, що порт сервера 4317."
        self.assertEqual(self.observer.analyze(text).query_type, "personal_context")
        summary = self.remember(text)
        record = next(r for r in self.store.load_working_memory() if r.id == summary.stored_record_id)
        self.assertEqual(record.content, text)

    def test_questions_about_decisions_never_create_a_decision(self):
        for text in ("Що ми вирішили про SQLite?", "Чи ми вирішили використовувати SQLite", "Рішення використовувати SQLite?",
                     "We decided to use SQLite?", "Мы решили использовать SQLite?"):
            with self.subTest(text=text):
                state = self.observer.analyze(text)
                self.assertFalse(self.keeper.evaluate_interaction(text, "", state, []).should_store)

    def test_unrelated_ukrainian_question_stays_a_new_question(self):
        state = self.observer.analyze("Скільки буде два плюс два?")
        self.assertEqual(state.query_type, "new_question")
        self.assertFalse(state.needs_memory)


if __name__ == "__main__":
    unittest.main()
