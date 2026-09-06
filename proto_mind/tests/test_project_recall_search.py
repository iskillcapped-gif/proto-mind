"""Adversarial selection cases beyond the fixed ordinary-question corpus."""
import json
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from proto_mind.project_recall_search import rank_notes
from proto_mind.project_recall_evals import evaluate


def selected(query, *notes):
    records = [{"id": str(index), "saved_at": f"2026-09-06T00:00:{index:02}",
                "body": {"content": content, "basis": "Do not search this provenance"}}
               for index, content in enumerate(notes)]
    return [row["body"]["content"] for row in rank_notes(records, query)]


class ProjectRecallQualityTests(TestCase):
    def test_ordinary_multilingual_corpus_without_processes_or_network(self):
        path = Path(__file__).resolve().parents[2] / "evals/project_recall/cases.json"
        with patch("subprocess.Popen", side_effect=AssertionError("No process during local recall")), \
                patch("socket.socket.connect", side_effect=AssertionError("No network during local recall")):
            report = evaluate(json.loads(path.read_bytes()))
        self.assertTrue(report["state_byte_stable"])
        for row in report["results"]:
            with self.subTest(mode=row["mode"], case=row["id"]):
                self.assertTrue(row["pass"], row)

    def test_full_path_does_not_fall_back_to_another_directory_with_same_filename(self):
        a, b = "Настройки: service-a/config.json", "Настройки: service-b/config.json"
        self.assertEqual(selected("Что в service-a/config.json?", a, b), [a])
        self.assertEqual(selected("service-c/config.json", a, b), [])
        self.assertEqual(set(selected("config.json", a, b)), {a, b})

    def test_short_paths_dotfiles_and_identifiers_remain_searchable(self):
        for name in ("a.py", ".db", "a/b/", "API_KEY", "réglages.json"):
            note = f"Configuration: {name}"
            with self.subTest(name=name):
                self.assertEqual(selected(f"Find {name}", note, "Other configuration"), [note])
        self.assertEqual(selected("re\u0301glages.json", "Configuration: réglages.json"),
                         ["Configuration: réglages.json"])

    def test_unknown_filename_and_extension_never_use_only_a_shared_fragment(self):
        notes = ("Настройки: config.yaml", "Настройки: settings.json", "Настройки: config.json")
        for query in ("secret.json", "config.toml", "settings.yaml"):
            with self.subTest(query=query):
                self.assertEqual(selected(query, *notes), [])

    def test_named_services_and_multiple_explicit_services(self):
        redis, postgres = "Redis port 6379.", "PostgreSQL port 5432."
        self.assertEqual(selected("Redis port?", redis, postgres), [redis])
        self.assertEqual(selected("MongoDB port?", redis, postgres), [])
        self.assertEqual(set(selected("Redis and Postgres ports?", redis, postgres)), {redis, postgres})

    def test_environment_qualifier_does_not_borrow_another_environment(self):
        local, production = "Локальный сервер: порт 4000.", "Production server port 443."
        self.assertEqual(selected("На якому порту локальний сервер?", local, production), [local])
        self.assertEqual(selected("Production port?", local, production), [production])
        self.assertEqual(selected("Staging port?", local, production), [])

    def test_separate_topics_survive_suppression_of_a_redundant_single_word(self):
        server, palette = "Server port 4000.", "Copper colors."
        self.assertEqual(set(selected("Server port and colors?", "Port forwarding.", server, palette)),
                         {server, palette})

    def test_qualified_file_and_service_have_to_match_in_the_same_note(self):
        correct = "Redis settings are in config.json."
        self.assertEqual(selected("Redis config.json?", correct, "Redis config.yaml", "PostgreSQL config.json"),
                         [correct])

    def test_tie_order_is_stable_and_repetition_cannot_manufacture_weight(self):
        exact, repeated = "Server port 4000.", "Port ports порт порта порту."
        self.assertEqual(selected("server port", repeated, exact), [exact])
        notes = ("Python testing A", "Python testing B", "Python testing C")
        self.assertEqual(selected("Python tests", *notes), selected("Python testing tests tests", *notes))

    def test_provenance_and_filler_never_supply_relevance(self):
        self.assertEqual(selected("provenance", "Copper colors"), [])
        self.assertEqual(selected("Please help with this project", "We use Python for this project"), [])
