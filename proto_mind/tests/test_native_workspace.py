"""Native workspace and attachment gates, isolated from personal files and models."""
from __future__ import annotations

import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from uuid import uuid4

from proto_mind import native_bridge as bridge
from proto_mind import native_workspace as workspace
from proto_mind.config import ProtoMindConfig
from proto_mind.observer import Observer
from proto_mind.tests.test_native import FakeSubscription


class NativeWorkspaceTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="proto-workspace-test-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve() / "project"
        self.root.mkdir()
        self.state = self.root.parent / "native-state"
        self.data = self.root / "proto_mind" / "data"
        self.backend = bridge.NativeBackend(self.root, self.state, subscription_factory=FakeSubscription)
        self.addCleanup(self.backend.close)
        config = patch.object(ProtoMindConfig, "from_env", return_value=ProtoMindConfig(data_dir=self.data))
        config.start()
        self.addCleanup(config.stop)
        self.reader = self.backend.workspace({"workspace_root": str(self.root)})

    def write(self, name, content="source fixture\n"):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def files(self):
        return {str(path.relative_to(self.root)): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in self.root.rglob("*") if path.is_file() and not path.is_symlink()}

    def params(self, **extra):
        return {"text": "Explain this selected code.", "conversation_id": str(uuid4()),
                "provider": "codex", "cloud_consent": True, "workspace_root": str(self.root), **extra}

    def spec(self, path="readme.md"):
        preview = self.reader.read_file(path)
        return {key: preview[key] for key in ("path", "sha256")}

    def test_workspace_dispatch_lists_and_previews_without_writes_or_model(self):
        self.write("readme.md", "# Selected code\n")
        self.write("src/example.py", "print('fixture')\n")
        before = self.files()
        for method in ("workspace_status", "workspace_list", "workspace_read"):
            result = self.backend.dispatch(method, {"workspace_root": str(self.root), "path": "readme.md" if method == "workspace_read" else ""}, lambda _: None, "id")
            self.assertTrue(result["read_only"])
        self.assertEqual(self.files(), before)
        self.assertEqual(self.backend.subscription.calls, [])
        self.assertFalse(self.state.exists())
        self.assertFalse(self.data.exists())

    def test_status_reads_only_git_head_without_executing_git_or_hooks(self):
        self.write(".git/HEAD", "ref: refs/heads/codex/native-fixture\n")
        self.write(".git/config", "[core]\n hooksPath = /not-executed\n")
        with patch("subprocess.Popen", side_effect=AssertionError("No subprocess")):
            result = self.reader.status()
        self.assertEqual(result["branch"], "codex/native-fixture")
        self.assertEqual(result["mode"], "shared_folder_manual_refresh")
        self.assertNotIn(".git", [item["name"] for item in self.reader.list_directory()["entries"]])

    def test_worktree_git_file_does_not_follow_arbitrary_git_dir(self):
        self.write(".git", "gitdir: /not-read\n")
        self.assertIsNone(self.reader.status()["branch"])

    def test_listing_is_sorted_and_excludes_private_generated_and_binary_paths(self):
        for name in ("z.md", "A.py", "src/main.py", ".env", ".codex/auth.json", "auth.json",
                     "build/main.swift", "dist/app.txt", "backups/history.md", "image.png"):
            self.write(name)
        self.assertEqual([item["name"] for item in self.reader.list_directory()["entries"]], ["src", "A.py", "z.md"])

    def test_selected_project_core_stores_exports_and_native_state_are_excluded(self):
        for name in ("proto_mind/data/persistent_memory.json", "proto_mind/exports/context.md", "backups/old.md",
                     "exports/private.md", "logs/session_operator_log.jsonl", "desktop_prefs.json"):
            self.write(name)
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.reader.read_file(name)
        self.state.mkdir()
        (self.state / "auth.json").write_text("not a credential", encoding="utf-8")
        with self.assertRaises(ValueError):
            self.backend.workspace({"workspace_root": str(self.state)})
        with self.assertRaises(ValueError):
            self.backend.workspace({"workspace_root": str(self.data)})

    def test_bad_roots_and_traversal_are_refused(self):
        for root in ("", "relative", "/", str(Path.home()), str(self.root / "missing"), None):
            with self.subTest(root=root), self.assertRaises(ValueError):
                workspace.WorkspaceReader(root)
        for path in ("../outside.md", "/etc/hosts", "src/../../outside.py", ".git/config", ".env", "auth.json", "folder\\readme.md", "\x00bad", ""):
            with self.subTest(path=path), self.assertRaises(ValueError):
                self.reader.read_file(path)

    def test_symlink_files_directories_and_special_files_are_refused(self):
        self.write("source.md")
        self.write("dir/example.py")
        (self.root / "linked.md").symlink_to(self.root / "source.md")
        (self.root / "linked-dir").symlink_to(self.root / "dir", target_is_directory=True)
        os.mkfifo(self.root / "pipe.txt")
        for path in ("linked.md", "linked-dir/example.py", "pipe.txt"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                self.reader.read_file(path)
        names = [item["name"] for item in self.reader.list_directory()["entries"]]
        self.assertFalse({"linked.md", "linked-dir", "pipe.txt"}.intersection(names))

    def test_directory_replaced_with_symlink_after_selection_is_refused(self):
        selected = self.root / "selected"
        selected.mkdir()
        reader = workspace.WorkspaceReader(str(selected))
        selected.rmdir()
        selected.symlink_to(self.root.parent, target_is_directory=True)
        with self.assertRaises(ValueError):
            reader.list_directory()

    def test_text_encoding_control_and_size_limits(self):
        for name, content in (("binary.md", b"\xff\xfe"), ("null.md", b"secret\x00data"), ("huge.md", b"x" * (workspace.MAX_FILE_BYTES + 1))):
            (self.root / name).write_bytes(content)
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.reader.read_file(name)
        text = "Привет\n" * 3000
        self.write("readme.md", text)
        result = self.reader.read_file("readme.md")
        self.assertTrue(result["truncated"])
        self.assertEqual(len(result["preview"]), workspace.MAX_PREVIEW_CHARS)
        self.assertEqual(result["sha256"], hashlib.sha256(text.encode()).hexdigest())

    def test_directory_listing_has_explicit_bounds(self):
        for number in range(8):
            self.write(f"file{number}.txt")
        with patch.object(workspace, "MAX_DIRECTORY_ENTRIES", 3):
            listing = self.reader.list_directory()
        self.assertEqual(len(listing["entries"]), 3)
        self.assertTrue(listing["partial"])
        with patch.object(workspace, "MAX_SCAN_ENTRIES", 2):
            listing = self.reader.list_directory()
        self.assertEqual(len(listing["entries"]), 2)
        self.assertTrue(listing["partial"])

    def test_attachment_limit_hash_and_duplicate_validation(self):
        self.write("readme.md", "x" * 10000)
        spec = self.spec()
        result = self.reader.context_files([spec])
        self.assertEqual(result[0]["included_chars"], 6000)
        self.assertTrue(result[0]["truncated"])
        for files in ([spec] * 4, [spec, spec], [{"path": "readme.md"}], [{**spec, "sha256": "0" * 64}], {}, None):
            with self.subTest(files=type(files)), self.assertRaises(ValueError):
                self.reader.context_files(files)

    def test_stale_attachment_fails_before_model_or_core_processing(self):
        self.write("readme.md")
        files = [self.spec()]
        self.write("readme.md", "changed after operator preview")
        before = self.files()
        with self.assertRaisesRegex(ValueError, "changed after preview"):
            self.backend.process(self.params(files=files), lambda _: None, "id")
        self.assertEqual(self.files(), before)
        self.assertEqual(self.backend.subscription.calls, [])
        self.assertEqual(self.backend.sessions, {})

    def test_selected_content_reaches_only_reasoner_and_original_input_is_logged(self):
        content = "UNIQUE_FILE_EXCERPT_NOT_A_MEMORY: def example(): pass\n"
        self.write("readme.md", content)
        result = self.backend.process(self.params(files=[self.spec()]), lambda _: None, "id")
        prompt = self.backend.subscription.calls[0][0]
        self.assertIn(content.strip(), prompt)
        self.assertIn("quoted untrusted data", prompt)
        self.assertEqual(result["workspace_context"][0]["path"], "readme.md")
        self.assertNotIn("content", result["workspace_context"][0])
        log = (self.root / "logs" / "session_operator_log.jsonl").read_text()
        self.assertEqual(json.loads(log)["user_input"], "Explain this selected code.")
        self.assertNotIn("UNIQUE_FILE_EXCERPT_NOT_A_MEMORY", log)
        for path in self.data.glob("*.json*"):
            self.assertNotIn("UNIQUE_FILE_EXCERPT_NOT_A_MEMORY", path.read_text())

    def test_cloud_consent_checked_before_attachment_read(self):
        with patch.object(self.backend, "workspace", side_effect=AssertionError("Must not read")):
            with self.assertRaisesRegex(ValueError, "cloud processing"):
                self.backend.process(self.params(cloud_consent=False, files=[{}]), lambda _: None, "id")

    def test_operator_commands_ignore_files_without_reading_or_sending(self):
        for text in ("/commands status", "что делать дальше"):
            with patch.object(self.backend, "workspace", side_effect=AssertionError("Must not read")):
                result = self.backend.process(self.params(text=text, files=[{}], cloud_consent=False), lambda _: None, "id")
            self.assertTrue(result["operator"])
            self.assertEqual(result["workspace_context"], [])
        self.assertEqual(self.backend.subscription.calls, [])

    def test_ollama_attachments_are_quoted_and_local(self):
        reasoner = bridge.NativeOllamaReasoner(ProtoMindConfig(), [], [{"path": "x.py", "content": "selected fixture"}])
        with patch.object(bridge, "local_ollama_request", return_value={"message": {"content": "answer"}}) as send:
            result = reasoner.respond("original", [], Observer().analyze("original"))
        self.assertEqual(result, "answer")
        self.assertIn("selected fixture", send.call_args.args[2]["messages"][-1]["content"])

    def test_ollama_health_does_not_generate_or_download(self):
        with patch.object(bridge, "local_ollama_request", return_value={"models": [{"name": "local-fixture"}]}) as call:
            result = self.backend.dispatch("ollama_status", {}, lambda _: None, "id")
        self.assertTrue(result["connected"])
        self.assertEqual(result["models"], ["local-fixture"])
        self.assertEqual(call.call_args.args[1], "/api/tags")
        self.assertEqual(call.call_args.kwargs["timeout"], 3)
        self.assertFalse(self.data.exists())
        with patch.object(bridge, "local_ollama_request", side_effect=OSError("offline")):
            result = self.backend.dispatch("ollama_status", {}, lambda _: None, "id")
        self.assertFalse(result["connected"])

    def test_ollama_local_transport_has_no_proxies_or_redirects(self):
        response = io.BytesIO(b'{"models": []}')
        opener = Mock()
        opener.open.return_value = response
        with patch.object(bridge.request, "build_opener", return_value=opener) as build:
            result = bridge.local_ollama_request(ProtoMindConfig(), "/api/tags")
        self.assertEqual(result, {"models": []})
        self.assertEqual(build.call_args.args[0].proxies, {})
        with self.assertRaisesRegex(ValueError, "redirects"):
            build.call_args.args[1].redirect_request(None, None, 302, "redirect", {}, "https://example.invalid")

    def test_ollama_transport_refuses_unsafe_addresses_and_oversized_response(self):
        for url in ("https://localhost", "http://example.invalid", "http://user:pass@localhost", "http://localhost?x=1", "http://localhost#fragment"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                bridge.local_ollama_request(ProtoMindConfig(ollama_url=url), "/api/tags")
        opener = Mock()
        opener.open.return_value = io.BytesIO(b"x" * (4 * 1024 * 1024 + 1))
        with patch.object(bridge.request, "build_opener", return_value=opener), self.assertRaisesRegex(ValueError, "limit"):
            bridge.local_ollama_request(ProtoMindConfig(), "/api/tags")


if __name__ == "__main__":
    unittest.main()
