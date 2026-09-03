"""Source-grounded memory suggestions do not promote model output or write on review."""
from copy import deepcopy
import json
from unittest import TestCase
from unittest.mock import patch
from uuid import uuid4

from proto_mind.native_bridge import NativeBackend
from proto_mind.native_memory_suggestions import explicit_statements, suggestions, text_hash
from proto_mind.native_work_sessions import WorkSessionError, workspace_identity
from proto_mind.tests.test_native import FakeSubscription
from proto_mind.tests import test_native_project_memory as memory_fixture


class StatementExtractionTests(TestCase):
    def test_explicit_russian_and_english_kinds_keep_exact_source(self):
        cases = {
            "Я предпочитаю короткие ответы.": "preference",
            "Мне удобнее обсуждать результат по-русски.": "preference",
            "Мы решили использовать бирюзовую палитру.": "decision",
            "В этом проекте используем Python 3.11.": "project_fact",
            "В этом проекте нельзя менять данные без backup.": "constraint",
            "Вывод на будущее: сначала проверять рабочую папку.": "lesson",
            "I prefer concise answers.": "preference",
            "We decided to use the cobalt palette.": "decision",
            "Our project uses Python 3.11.": "project_fact",
            "For this project, never delete runtime data.": "constraint",
            "Lesson learned: verify the working folder first.": "lesson",
        }
        for text, kind in cases.items():
            with self.subTest(text=text):
                records = explicit_statements(text)
                self.assertEqual(len(records), 1)
                self.assertEqual(records[0], {"kind": kind, "start": 0, "end": len(text), "content_sha256": text_hash(text)})

    def test_quotes_questions_hypotheses_and_secrets_are_not_suggestions(self):
        for text in (
            "Привет брат, продолжаем!", "Что мы решили использовать?", "Я предпочитаю короткие ответы?",
            "Раньше мы решили использовать SQLite.", "Мы решили бы использовать SQLite, если получится.",
            "Мы решили, возможно, использовать SQLite.", "Переведи: I prefer concise answers.",
            "> I prefer concise answers.", "```text\nI prefer concise answers.\n```",
            '"I prefer concise answers."', "Вот текст:\nМы решили использовать SQLite.",
            "Например:\nЯ предпочитаю короткие ответы.", "Не запоминай это.\nЯ предпочитаю короткие ответы.",
            "Our project uses API key sk-fixture000000.", "Я предпочитаю пароль example.",
            "We decided to use token=fixture.", "Our project uses https://user:secret@example.test.",
            "I prefer " + "x" * 601, "I prefer " + "x" * 12_000,
        ):
            with self.subTest(text=text[:80]): self.assertEqual(explicit_statements(text), [])

    def test_unicode_offsets_multiple_statements_and_boundaries(self):
        text = "Привет 💙.\n  - брат, Я предпочитаю синий цвет 🎨. Мы решили использовать Python 3.11.\nСледующий вопрос."
        records = explicit_statements(text)
        self.assertEqual([text[row["start"]:row["end"]] for row in records],
                         ["Я предпочитаю синий цвет 🎨.", "Мы решили использовать Python 3.11."])
        self.assertEqual(records, explicit_statements(text))
        self.assertEqual(explicit_statements("Я предпочитаю короткие ответы. Сделай отчёт."), explicit_statements("Я предпочитаю короткие ответы."))


class MemorySuggestionsTests(TestCase):
    setUp = memory_fixture.NativeProjectMemoryTests.setUp
    params = memory_fixture.NativeProjectMemoryTests.params
    call = memory_fixture.NativeProjectMemoryTests.call
    note = memory_fixture.NativeProjectMemoryTests.note
    save = memory_fixture.NativeProjectMemoryTests.save
    files = memory_fixture.NativeProjectMemoryTests.files
    memory = memory_fixture.NativeProjectMemoryTests.memory
    text = "Мы решили использовать бирюзовую палитру."

    def completed(self, text=None, **changes):
        return self.backend.process(self.params(text=text or self.text, provider="codex", model="fixture-model", cloud_consent=True,
                                               memory_suggestions=True) | changes, lambda _: None, "suggestions-fixture")

    def request(self, result, text=None, **changes):
        report = result["memory_suggestions"]
        return {"run": {key: report["source"][key] for key in ("run_id", "fingerprint")},
                "text": text or self.text, "candidate_id": report["candidates"][0]["id"], **changes}

    def reviewed_save(self, request, preview):
        return self.call("memory_suggestion_save", **request, **{key: preview["note_preview"][key] for key in
                         ("preview_fingerprint", "confirmation_token")}, acknowledge_operator_note=True)

    def test_turn_adds_only_content_free_suggestions_without_extra_model_or_note_write(self):
        result = self.completed()
        report = result["memory_suggestions"]
        self.assertEqual(report["state"], "suggested")
        self.assertEqual(report["source"]["fingerprint"], result["work_session"]["fingerprint"])
        self.assertNotIn(self.text, json.dumps(report, ensure_ascii=False))
        self.assertEqual(len(self.backend.subscription.calls), 1)
        self.assertFalse((self.state / "project_memory").exists())
        self.assertTrue(report["read_only"])
        self.assertFalse(report["automatic_save"] or report["permission_granted"] or report["model_call_performed"])

    def test_preview_is_read_only_and_save_writes_only_one_existing_private_note(self):
        result = self.completed()
        request = self.request(result)
        before = self.files()
        with patch.object(self.backend, "_coordinator", side_effect=AssertionError("No cognitive turn")), patch("subprocess.Popen", side_effect=AssertionError("No process")):
            preview = self.call("memory_suggestion_preview", **request)
            self.assertEqual(self.files(), before)
            saved = self.reviewed_save(request, preview)
        after = self.files()
        self.assertEqual({path: after[path] for path in before}, before)
        self.assertEqual(set(after) - set(before), {"private/project_memory/.writer.lock", f"private/project_memory/{saved['item']['id']}.json"})
        self.assertEqual(saved["item"]["content"], self.text)
        self.assertEqual(saved["item"]["verification"], "operator_asserted_not_independently_verified")
        self.assertIn(result["work_session"]["id"], saved["item"]["basis"])
        self.assertIn(text_hash(self.text), saved["item"]["basis"])
        self.assertEqual(saved["item"]["supersedes_id"], "")
        self.assertEqual(len(self.backend.subscription.calls), 1)

    def test_approval_token_and_current_snapshot_are_required(self):
        result = self.completed(); request = self.request(result)
        preview = self.call("memory_suggestion_preview", **request)["note_preview"]
        args = request | {key: preview[key] for key in ("preview_fingerprint", "confirmation_token")} | {"acknowledge_operator_note": True}
        before = self.files()
        for change in ({"acknowledge_operator_note": False}, {"confirmation_token": "wrong"}, {"preview_fingerprint": "a" * 64}):
            with self.subTest(change=change), self.assertRaises(ValueError): self.call("memory_suggestion_save", **(args | change))
        self.assertEqual(before, self.files())
        self.save("Another explicitly saved note.")
        before = self.files()
        with self.assertRaises(ValueError): self.call("memory_suggestion_save", **args)
        self.assertEqual(before, self.files())

    def test_save_and_inspect_survive_restart_without_repeat_or_automatic_promotion(self):
        result = self.completed(); request = self.request(result)
        fresh = NativeBackend(self.root, self.state, subscription_factory=FakeSubscription)
        self.addCleanup(fresh.close)
        before = self.files()
        preview = fresh.dispatch("memory_suggestion_preview", self.params(**request), lambda _: None, "read")
        self.assertEqual(before, self.files())
        saved = self.reviewed_save(request, preview)
        before = self.files()
        with self.assertRaises(ValueError): self.reviewed_save(request, preview)
        self.assertEqual(before, self.files())
        context = fresh.preview_context(self.params(text="Какая палитра? Бирюзовую используем?", provider="codex", auto_project_recall=True))
        self.assertEqual(context["manifest"]["knowledge_context"]["project_recall"]["selected_ids"], [saved["item"]["id"]])
        self.assertEqual(before, self.files()); self.assertEqual(fresh.subscription.calls, [])

    def test_exact_duplicates_are_suppressed_but_new_decisions_never_supersede(self):
        old = self.save("Мы решили использовать янтарную палитру.", kind="decision")
        self.save(self.text.lower().rstrip("."), kind="decision")
        result = self.completed()
        self.assertEqual(result["memory_suggestions"]["state"], "no_candidates")
        new_text = "Мы решили использовать кобальтовую палитру."
        result = self.completed(new_text); request = self.request(result, new_text)
        preview = self.call("memory_suggestion_preview", **request)
        self.assertEqual(preview["note_preview"]["body"]["supersedes_id"], "")
        self.assertEqual(self.memory().inspect(old["id"])["item"]["status"], "active")

    def test_selection_is_capped_whole_quotes_and_same_message_duplicates_are_suppressed(self):
        text = "\n".join([self.text, self.text, "Я предпочитаю короткие ответы.", "Наш проект использует Python 3.11.", "Вывод на будущее: проверять источники."])
        result = self.completed(text)
        report = result["memory_suggestions"]
        self.assertEqual(len(report["candidates"]), 2)
        self.assertEqual(report["omitted_count"], 2)
        self.assertEqual([text[row["start"]:row["end"]] for row in report["candidates"]], [self.text, "Я предпочитаю короткие ответы."])

    def test_changed_missing_foreign_or_forged_source_is_refused_without_writes(self):
        result = self.completed(); request = self.request(result)
        before = self.files()
        other = self.base / "other"; other.mkdir()
        changes = [{"text": "Мы решили использовать чужую палитру."}, {"candidate_id": "a" * 64},
                   {"run": {"run_id": str(uuid4()), "fingerprint": request["run"]["fingerprint"]}},
                   {"run": {"run_id": request["run"]["run_id"], "fingerprint": "a" * 64}},
                   {"conversation_id": str(uuid4())}, {"workspace_root": str(other)}, {"note": self.note()}, {"execute": "yes"}]
        for change in changes:
            with self.subTest(change=change), self.assertRaises((ValueError, WorkSessionError)):
                self.call("memory_suggestion_preview", **(request | change))
        self.assertEqual(before, self.files())
        path = self.state / "work_sessions" / (request["run"]["run_id"] + ".json")
        data = json.loads(path.read_text()); data["answer_preview"] = "Changed by separate operator review."
        path.write_text(json.dumps(data))
        before = self.files()
        with self.assertRaises(WorkSessionError): self.call("memory_suggestion_preview", **request)
        self.assertEqual(before, self.files())

    def test_context_enabled_corrupt_notes_and_replaced_workspace_refuse_saving(self):
        result = self.completed(); request = self.request(result)
        before = self.files()
        with patch("proto_mind.native_memory_suggestions.injection_state", return_value={"enabled": True}):
            self.assertEqual(suggestions(self.root, self.state, result["work_session"], self.text)["state"], "unavailable")
            with self.assertRaises(ValueError): self.call("memory_suggestion_preview", **request)
        self.assertEqual(before, self.files())
        self.workspace.rename(self.base / "old-workspace"); self.workspace.mkdir()
        with self.assertRaises(ValueError): self.call("memory_suggestion_preview", **request)
        self.assertFalse((self.state / "project_memory").exists())

    def test_corrupt_private_note_refuses_suggestion_without_repair(self):
        result = self.completed(); request = self.request(result)
        directory = self.state / "project_memory"; directory.mkdir()
        (directory / ("a" * 64 + ".json")).write_text('{"broken":true}')
        before = self.files()
        report = suggestions(self.root, self.state, result["work_session"], self.text)
        self.assertEqual(report["state"], "unavailable")
        with self.assertRaises(ValueError): self.call("memory_suggestion_preview", **request)
        self.assertEqual(before, self.files())

    def test_deduplication_never_reads_another_project_as_current_knowledge(self):
        other = self.base / "other"; other.mkdir()
        memory = self.memory(other)
        note = self.note(self.text, kind="decision"); preview = memory.preview(note)
        memory.save({"note": note, "preview_fingerprint": preview["preview_fingerprint"],
                     "confirmation_token": preview["confirmation_token"], "acknowledge_operator_note": True})
        result = self.completed()
        self.assertEqual(result["memory_suggestions"]["state"], "suggested")
        self.assertEqual(result["memory_suggestions"]["source"]["workspace"], workspace_identity(self.workspace))

    def test_absent_workspace_and_large_source_preserve_answer_without_guessed_scope(self):
        self.assertIsNone(self.completed(workspace_root=None)["memory_suggestions"])
        text = "I prefer " + "q" * 12_000
        result = self.completed(text)
        self.assertEqual(result["memory_suggestions"]["state"], "no_candidates")
        self.assertFalse((self.state / "project_memory").exists())

    def test_source_is_rechecked_between_preview_and_writer(self):
        result = self.completed(); request = self.request(result)
        preview = self.call("memory_suggestion_preview", **request)
        before = self.files()
        original = self.backend.work_sessions.inspect
        count = 0
        def inspect(*args):
            nonlocal count
            count += 1
            if count == 2: raise WorkSessionError("Source changed before write")
            return original(*args)
        with patch("proto_mind.native_memory_suggestions.WorkSessionStore.inspect", side_effect=inspect):
            with self.assertRaises(WorkSessionError): self.reviewed_save(request, preview)
        self.assertEqual(before, self.files())

    def test_read_only_diagnostics_and_no_candidate_do_not_initialize_missing_store(self):
        result = self.completed("Привет, как дела?")
        self.assertEqual(result["memory_suggestions"]["state"], "no_candidates")
        self.assertFalse((self.state / "project_memory").exists())
        before = self.files()
        run = result["work_session"]
        with self.assertRaises(ValueError): suggestions(self.root, self.state, run, self.text)
        self.assertEqual(before, self.files())

    def test_no_provider_response_attachment_or_history_becomes_source(self):
        for text in ("Summarize the attached file.", "Сделай отчёт.", "Продолжаем."):
            with self.subTest(text=text):
                result = self.completed(text, history=[{"role": "assistant", "content": self.text}])
                self.assertEqual(result["memory_suggestions"]["candidates"], [])
        self.assertFalse((self.state / "project_memory").exists())

    def test_opt_out_operator_and_local_provider_bypass_and_invalid_flag_refuses(self):
        for changes in ({"memory_suggestions": False}, {"provider": "mock", "cloud_consent": False}, {"text": "/data doctor"}):
            with self.subTest(changes=changes): self.assertIsNone(self.completed(**changes)["memory_suggestions"])
        with self.assertRaises(ValueError): self.completed(memory_suggestions="yes")
        self.assertFalse((self.state / "project_memory").exists())

    def test_invalid_optional_inspection_preserves_successful_answer(self):
        with patch("proto_mind.native_bridge.memory_suggestions", side_effect=ValueError("Source unavailable")):
            result = self.completed()
        self.assertEqual(result["work_session"]["status"], "completed")
        self.assertIsNone(result["memory_suggestions"])
        self.assertTrue(any("suggestions unavailable" in notice for notice in result["notices"]))
        self.assertFalse((self.state / "project_memory").exists())

    def test_unfinished_or_non_codex_run_cannot_be_used_as_provenance(self):
        result = self.completed()
        for changes in ({"status": "error"}, {"display_status": "running"}, {"provider": "mock"}, {"workspace": None}):
            run = deepcopy(result["work_session"]); run.update(changes)
            with self.subTest(changes=changes), self.assertRaises(ValueError): suggestions(self.root, self.state, run, self.text)

    def test_active_turn_blocks_preview_or_save(self):
        result = self.completed(); request = self.request(result)
        before = self.files()
        self.backend.busy.acquire()
        try:
            with self.assertRaises(ValueError): self.call("memory_suggestion_preview", **request)
        finally: self.backend.busy.release()
        self.assertEqual(before, self.files())
