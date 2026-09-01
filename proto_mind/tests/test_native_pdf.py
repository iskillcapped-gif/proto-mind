"""Selected PDF page contracts on temporary data; no personal files or providers."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from uuid import uuid4

from proto_mind import native_bridge as bridge, native_pdf as pdf
from proto_mind.config import ProtoMindConfig
from proto_mind.tests.test_native import FakeSubscription
from scripts.native_smoke_fixture import text_pdf


class NativePDFTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="native-pdf-")
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name).resolve()
        self.root, self.state, self.workspace = [self.base / name for name in ("core", "private", "workspace")]
        self.workspace.mkdir()
        self.file = self.workspace / "selected.pdf"
        self.file.write_bytes(text_pdf(["FIRST", "SECOND", "THIRD"]))
        self.backend = bridge.NativeBackend(self.root, self.state, subscription_factory=FakeSubscription, pdf_helper=self.base / "ProtoMindPDF")
        self.addCleanup(self.backend.close)
        self.reader = self.backend.pdf_reader()
        self.texts = ["FIRST source text", "SECOND source text", "THIRD not selected"]
        mock = patch.object(pdf, "extract_pdf", side_effect=self.extract)
        self.worker = mock.start(); self.addCleanup(mock.stop)
        config = patch.object(ProtoMindConfig, "from_env", return_value=ProtoMindConfig(data_dir=self.root / "proto_mind/data"))
        config.start(); self.addCleanup(config.stop)
        self.conversation = str(uuid4())

    def extract(self, helper, data, pages):
        rows = [{"number": number, "text": self.texts[number - 1][:pdf.MAX_PAGE_CHARS],
                 "characters": len(self.texts[number - 1]), "included_chars": min(len(self.texts[number - 1]), pdf.MAX_PAGE_CHARS),
                 "truncated": len(self.texts[number - 1]) > pdf.MAX_PAGE_CHARS} for number in pages]
        return {"schema": "proto_mind.native_pdf_text.v1", "engine": "apple_pdfkit_text_v1", "page_count": len(self.texts), "pages": rows}

    def spec(self, pages=None):
        return self.reader.read(str(self.file), pages).metadata

    def params(self, **changes):
        return {"text": "Summarize the selected pages.", "provider": "codex", "cloud_consent": True,
                "conversation_id": self.conversation, "workspace_root": str(self.workspace), **changes}

    def files(self):
        return {str(path.relative_to(self.base)): path.read_bytes() for path in self.base.rglob("*") if path.is_file() and not path.is_symlink()}

    def test_preview_is_read_only_explicit_default_first_page_and_no_provider(self):
        before = self.files()
        with patch.object(self.backend, "_coordinator", side_effect=AssertionError("No core")):
            result = self.backend.dispatch("pdf_preview", {"path": str(self.file)}, lambda _: self.fail("No event"), "preview")
        self.assertTrue(result["read_only"] and result["no_execution"] and result["has_text"])
        self.assertEqual([row["number"] for row in result["pages"]], [1])
        self.assertEqual(result["pages"][0]["text"], self.texts[0])
        self.assertEqual(result["pdf"]["sha256"], hashlib.sha256(self.file.read_bytes()).hexdigest())
        self.assertNotIn("text", result["pdf"]["pages"][0])
        self.assertEqual(before, self.files())
        self.assertFalse(self.backend.subscription.calls or self.state.exists() or self.root.exists())

    def test_page_selection_bounded_and_only_selected_text_used(self):
        selected = self.reader.selected([self.spec([1, 2])])
        prompt = pdf.pdf_context_message(selected)
        self.assertIn(self.texts[0], prompt); self.assertIn(self.texts[1], prompt)
        self.assertNotIn(self.texts[2], prompt)
        self.assertIn("untrusted source data", prompt)
        self.assertNotIn(str(self.file), prompt)
        for value in ([], None, [0], [4], [2, 1], [1, 1], [True], [1.0], ["1"], list(range(1, 10))):
            with self.subTest(value=value), self.assertRaises((ValueError, IndexError)):
                pdf.page_selection(value, 3)

    def test_truncation_and_unicode_use_scalar_character_counts(self):
        self.texts[0] = "Проверка 🙂 " * 1000
        result = self.reader.preview(str(self.file))
        self.assertTrue(result["pages"][0]["truncated"])
        self.assertEqual(len(result["pages"][0]["text"]), 3000)
        self.assertEqual(result["pdf"]["pages"][0]["text_sha256"], hashlib.sha256(self.texts[0][:3000].encode()).hexdigest())

    def test_blank_or_scanned_pages_do_not_attach_or_send(self):
        self.texts = ["", "", ""]
        preview = self.reader.preview(str(self.file))
        self.assertFalse(preview["has_text"])
        with self.assertRaisesRegex(ValueError, "no readable text"):
            self.backend.process(self.params(pdfs=[preview["pdf"]]), lambda _: None, "send")
        self.assertFalse(self.backend.subscription.calls or self.state.exists())

    def test_stale_document_refuses_before_extraction_or_run(self):
        spec = self.spec()
        self.file.write_bytes(text_pdf(["REPLACED"]))
        self.worker.reset_mock()
        before = self.files()
        with self.assertRaisesRegex(ValueError, "changed"):
            self.backend.process(self.params(pdfs=[spec]), lambda _: None, "send")
        self.assertFalse(self.worker.called or self.backend.subscription.calls or self.state.exists())
        self.assertEqual(before, self.files())

    def test_changed_extractor_text_refuses_even_with_same_document_bytes(self):
        spec = self.spec()
        self.texts[0] = "different extraction"
        with self.assertRaisesRegex(ValueError, "text changed"):
            self.reader.selected([spec])
        preview = self.backend.preview_context(self.params(pdfs=[spec]))
        self.assertFalse(preview["attachments_ready"])
        self.assertEqual(preview["manifest"]["pdfs"], [])
        self.assertNotIn("different extraction", json.dumps(preview))

    def test_invalid_paths_symlinks_fifo_protected_and_size_refuse_without_worker(self):
        hidden = self.workspace / ".hidden.pdf"; hidden.write_bytes(self.file.read_bytes())
        link = self.workspace / "linked.pdf"; link.symlink_to(self.file)
        fifo = self.workspace / "pipe.pdf"; os.mkfifo(fifo)
        huge = self.workspace / "huge.pdf"; huge.write_bytes(b"%PDF-" + b"x" * pdf.MAX_PDF_BYTES)
        bad = self.workspace / "bad.pdf"; bad.write_bytes(b"not PDF")
        for path in ("https://example.invalid/a.pdf", "file:///tmp/a.pdf", "a.pdf", str(hidden), str(link), str(fifo),
                     str(huge), str(bad), str(self.root / "proto_mind/data/test.pdf"), str(self.state / "secret.pdf"),
                     str(self.workspace / "../a.pdf")):
            with self.subTest(path=path), self.assertRaises(ValueError):
                self.reader.read(path)
        self.assertFalse(self.worker.called)

    def test_metadata_rejects_payloads_noninteger_pages_and_duplicates(self):
        spec = self.spec()
        bad_page = {**spec, "pages": [{**spec["pages"][0], "number": True}]}
        for value in (None, {}, [spec, spec], [{**spec, "text": "payload"}], [{**spec, "sha256": "bad"}],
                      [{**spec, "pages": []}], [bad_page], [{**spec, "size_bytes": True}]):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.reader.selected(value)

    def test_worker_contract_mismatch_refused(self):
        valid = self.extract(None, b"", [1])
        cases = [None, {}, {**valid, "page_count": True}, {**valid, "pages": []},
                 {**valid, "pages": [{**valid["pages"][0], "number": 2}]},
                 {**valid, "pages": [{**valid["pages"][0], "text": "\x00"}]}]
        for value in cases:
            with self.subTest(value=value), patch.object(pdf, "extract_pdf", return_value=value), self.assertRaises(ValueError):
                self.reader.read(str(self.file))

    def test_context_preview_exact_pages_read_only_without_consent(self):
        spec = self.spec([2])
        before = self.files()
        result = self.backend.preview_context(self.params(pdfs=[spec], cloud_consent=False))
        self.assertTrue(result["attachments_ready"])
        self.assertEqual(result["manifest"]["pdfs"], [spec])
        self.assertEqual(result["pdf_sources"][0]["pages"][0]["text"], self.texts[1])
        self.assertEqual(before, self.files())
        self.assertFalse(self.backend.subscription.calls)

    def test_operator_bypasses_pdf_reads_and_context_inclusion(self):
        spec = self.spec(); self.file.unlink(); self.worker.reset_mock()
        preview = self.backend.preview_context(self.params(text="/commands status", pdfs=[spec]))
        self.assertEqual(preview["excluded_pdf_count"], 1)
        self.assertEqual(preview["pdf_sources"], [])
        result = self.backend.process(self.params(text="/commands status", pdfs=[spec]), lambda _: None, "operator")
        self.assertEqual(result["pdf_context"], [])
        self.assertFalse(self.worker.called or self.backend.subscription.calls or self.state.exists())

    def test_cloud_and_tools_permission_checks_run_before_pdf_reads(self):
        spec = self.spec(); self.worker.reset_mock()
        for changes in ({"cloud_consent": False}, {"access_mode": "full_access", "access_token": "wrong"}):
            with self.assertRaises(ValueError):
                self.backend.process(self.params(pdfs=[spec], **changes), lambda _: None, "send")
        self.assertFalse(self.worker.called or self.backend.subscription.calls or self.state.exists())

    def test_send_receives_only_selected_text_and_journal_stores_metadata(self):
        spec = self.spec([2]); original = self.file.read_bytes()
        result = self.backend.process(self.params(pdfs=[spec]), lambda _: None, "send")
        prompt = self.backend.subscription.calls[0][0]
        self.assertIn(self.texts[1], prompt)
        self.assertNotIn(self.texts[0], prompt); self.assertNotIn(self.texts[2], prompt)
        self.assertEqual(result["pdf_context"], [spec])
        journal = result["work_session"]
        self.assertEqual(journal["context_manifest"]["pdfs"], [spec])
        self.assertNotIn(self.texts[1], json.dumps(journal))
        self.assertEqual(original, self.file.read_bytes())
        for path in self.root.rglob("*.json*"):
            self.assertNotIn(self.texts[1], path.read_text(encoding="utf-8"))

    def test_next_turn_does_not_reattach_previous_pdf(self):
        self.backend.process(self.params(pdfs=[self.spec()]), lambda _: None, "one")
        self.backend.process(self.params(text="A second question"), lambda _: None, "two")
        self.assertNotIn(self.texts[0], self.backend.subscription.calls[-1][0])

    def test_local_ollama_receives_selected_text_only_on_send(self):
        with patch.object(bridge, "local_ollama_request", return_value={"message": {"content": "Local fixture response"}}) as local:
            result = self.backend.process(self.params(provider="ollama", pdfs=[self.spec([2])]), lambda _: None, "send")
        self.assertIn(self.texts[1], json.dumps(local.call_args.args[2]))
        self.assertNotIn(self.texts[0], json.dumps(local.call_args.args[2]))
        self.assertTrue(result["pdf_context"])
        self.assertFalse(self.backend.subscription.calls)

    def test_worker_is_fixed_sandboxed_timed_and_never_receives_file_path(self):
        helper = self.base / "ProtoMindPDF"; helper.write_bytes(b"fixture"); helper.chmod(0o700)
        # Use the real wrapper, replacing only subprocess execution, not PDF policy.
        with patch.object(pdf.sys, "platform", "darwin"), patch.object(pdf.subprocess, "run", return_value=SimpleNamespace(returncode=0, stdout=b'{}')) as run:
            self.real_extract(helper, b"%PDF-fixture", [1, 2])
        args, options = run.call_args
        self.assertEqual(args[0][0], "/usr/bin/sandbox-exec")
        self.assertIn("(deny network*)", args[0][2]); self.assertIn("(deny file-write*)", args[0][2])
        self.assertEqual(args[0][-2:], ["--pages", "1,2"])
        self.assertNotIn(str(self.file), args[0])
        self.assertEqual(options["timeout"], 12)
        self.assertNotIn("shell", options)
        self.assertEqual(options["input"], b"%PDF-fixture")

    def test_worker_timeout_bad_json_and_failure_are_clean_errors(self):
        helper = self.base / "ProtoMindPDF"; helper.write_bytes(b"fixture"); helper.chmod(0o700)
        for effect in (subprocess.TimeoutExpired("helper", 12), OSError("cannot start")):
            with patch.object(pdf.sys, "platform", "darwin"), patch.object(pdf.subprocess, "run", side_effect=effect), self.assertRaises(ValueError):
                self.real_extract(helper, b"", [1])
        for result in (SimpleNamespace(returncode=0, stdout=b"not json"),
                       SimpleNamespace(returncode=1, stdout=b'{"error":"Encrypted PDF not supported"}'),
                       SimpleNamespace(returncode=0, stdout=b"x" * (512 * 1024 + 1))):
            with patch.object(pdf.sys, "platform", "darwin"), patch.object(pdf.subprocess, "run", return_value=result), self.assertRaises(ValueError):
                self.real_extract(helper, b"", [1])
        with self.assertRaises(ValueError):
            self.real_extract(None, b"", [1])

    real_extract = staticmethod(pdf.extract_pdf)
