"""Selected-image boundaries on disposable files; no real accounts or images."""
from __future__ import annotations

import base64
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import struct
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from uuid import uuid4
import zlib

from proto_mind import native_bridge as bridge, native_codex as codex, native_images as images
from proto_mind.config import ProtoMindConfig
from proto_mind.native_agent import FULL_ACCESS_CONFIRMATION
from proto_mind.native_work_sessions import workspace_identity
from proto_mind.tests.test_native import FakeRPC, FakeSubscription
from proto_mind.tests.test_native_agent import AgentRPC


def chunk(kind, content):
    return struct.pack(">I", len(content)) + kind + content + struct.pack(">I", zlib.crc32(kind + content) & 0xffffffff)


def png(width=3, height=2, color=(40, 100, 200), extra=b""):
    pixels = (b"\0" + bytes(color) * width) * height
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + (chunk(b"tEXt", extra) if extra else b"") + chunk(b"IDAT", zlib.compress(pixels)) + chunk(b"IEND", b""))


# A 3x2 JPEG generated locally with AppKit, not a user's photo.
JPEG = base64.b64decode(
    "/9j/4AAQSkZJRgABAQAASABIAAD/4QBARXhpZgAATU0AKgAAAAgAAYdpAAQAAAABAAAAGgAAAAAAAqACAAQAAAABAAAAA6ADAAQAAAABAAAAAgAAAAD/7QA4UGhvdG9zaG9wIDMuMAA4QklNBAQAAAAAAAA4QklNBCUAAAAAABDUHYzZjwCyBOmACZjs+EJ+/8AAEQgAAgADAwEiAAIRAQMRAf/EAB8AAAEFAQEBAQEBAAAAAAAAAAABAgMEBQYHCAkKC//EALUQAAIBAwMCBAMFBQQEAAABfQECAwAEEQUSITFBBhNRYQcicRQygZGhCCNCscEVUtHwJDNicoIJChYXGBkaJSYnKCkqNDU2Nzg5OkNERUZHSElKU1RVVldYWVpjZGVmZ2hpanN0dXZ3eHl6g4SFhoeIiYqSk5SVlpeYmZqio6Slpqeoqaqys7S1tre4ubrCw8TFxsfIycrS09TV1tfY2drh4uPk5ebn6Onq8fLz9PX29/j5+v/EAB8BAAMBAQEBAQEBAQEAAAAAAAABAgMEBQYHCAkKC//EALURAAIBAgQEAwQHBQQEAAECdwABAgMRBAUhMQYSQVEHYXETIjKBCBRCkaGxwQkjM1LwFWJy0QoWJDThJfEXGBkaJicoKSo1Njc4OTpDREVGR0hJSlNUVVZXWFlaY2RlZmdoaWpzdHV2d3h5eoKDhIWGh4iJipKTlJWWl5iZmqKjpKWmp6ipqrKztLW2t7i5usLDxMXGx8jJytLT1NXW19jZ2uLj5OXm5+jp6vLz9PX29/j5+v/bAEMAAgICAgICAwICAwQDAwMEBQQEBAQFBwUFBQUFBwgHBwcHBwcICAgICAgICAoKCgoKCgsLCwsLDQ0NDQ0NDQ0NDf/bAEMBAgICAwMDBgMDBg0JBwkNDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDf/dAAQAAf/aAAwDAQACEQMRAD8A/n/ooooA/9k="
)


class ImageSubscription(FakeSubscription):
    def answer(self, *args, images=None, **kwargs):
        self.images = images or []
        return super().answer(*args, **kwargs)

    def agent_answer(self, *args, workspace, on_activity, **kwargs):
        self.workspace = workspace
        kwargs.pop("criteria", None)
        return self.answer(*args, **kwargs)


class NativeImageTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="native-selected-images-")
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name).resolve()
        self.root, self.state, self.workspace = (self.base / name for name in ("core", "private", "workspace"))
        self.workspace.mkdir()
        self.backend = bridge.NativeBackend(self.root, self.state, subscription_factory=ImageSubscription)
        self.addCleanup(self.backend.close)
        self.reader = self.backend.image_reader()
        self.conversation = str(uuid4())
        config = patch.object(ProtoMindConfig, "from_env", return_value=ProtoMindConfig(data_dir=self.root / "proto_mind/data"))
        config.start(); self.addCleanup(config.stop)

    def write(self, name="fixture.png", data=None):
        path = self.workspace / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(png() if data is None else data)
        return path

    def files(self):
        return {str(path.relative_to(self.base)): path.read_bytes() for path in self.base.rglob("*") if path.is_file() and not path.is_symlink()}

    def spec(self, path=None):
        path = path or self.write()
        return self.reader.read(str(path)).metadata

    def params(self, **changes):
        return {"text": "Describe the selected image.", "provider": "codex", "cloud_consent": True,
                "conversation_id": self.conversation, "workspace_root": str(self.workspace), **changes}

    def test_preview_is_local_read_only_and_includes_exact_original_bytes(self):
        path = self.write(data=png(extra=b"Comment\0fixture metadata retained"))
        before = self.files()
        with patch("subprocess.Popen", side_effect=AssertionError("No process")), patch.object(self.backend, "_coordinator", side_effect=AssertionError("No core")):
            preview = self.backend.dispatch("image_preview", {"path": str(path)}, lambda _: self.fail("No events"), "preview")
        self.assertTrue(preview["read_only"] and preview["no_execution"])
        self.assertEqual(base64.b64decode(preview["data_base64"]), path.read_bytes())
        self.assertEqual(preview["image"]["width"], 3)
        self.assertEqual(preview["image"]["sha256"], hashlib.sha256(path.read_bytes()).hexdigest())
        self.assertEqual(before, self.files())
        self.assertFalse(self.root.exists() or self.state.exists())
        self.assertFalse(self.backend.subscription.calls)

    def test_jpeg_and_unicode_image_names_are_supported(self):
        path = self.write("снимок экрана.JPEG", JPEG)
        image = self.reader.read(str(path))
        self.assertEqual((image.mime_type, image.width, image.height), ("image/jpeg", 3, 2))
        self.assertEqual(image.metadata["name"], path.name)

    def test_urls_relative_traversal_hidden_and_protected_paths_refuse(self):
        for path in ("https://example.invalid/image.png", "file:///tmp/a.png", "image.png", str(self.workspace / "../image.png"),
                     str(self.write(".secret/a.png")), str(self.write("backups/a.png")), str(self.root / "proto_mind/data/a.png"),
                     str(self.root / "proto_mind/exports/a.png"), str(self.state / "a.png")):
            with self.subTest(path=path), self.assertRaises(ValueError):
                self.reader.read(path)

    def test_symlink_files_and_parent_directories_refuse(self):
        source = self.write()
        link = self.workspace / "link.png"
        link.symlink_to(source)
        directory = self.base / "linked-workspace"
        directory.symlink_to(self.workspace, target_is_directory=True)
        for path in (link, directory / source.name):
            with self.subTest(path=path), self.assertRaisesRegex(ValueError, "symlink"):
                self.reader.read(str(path))

    def test_nonregular_and_oversize_files_refuse_without_blocking(self):
        fifo = self.workspace / "pipe.png"
        os.mkfifo(fifo)
        with self.assertRaisesRegex(ValueError, "regular"):
            self.reader.read(str(fifo))
        path = self.write(data=b"x" * (images.MAX_IMAGE_BYTES + 1))
        with self.assertRaisesRegex(ValueError, "4 MiB"):
            self.reader.read(str(path))

    def test_invalid_container_crc_extension_animation_and_dimensions_refuse(self):
        crc = bytearray(png()); crc[-5] ^= 1
        with patch.object(images, "MAX_IMAGE_PIXELS", 1), self.assertRaisesRegex(ValueError, "megapixel"):
            self.reader.read(str(self.write()))
        animation = png()[:33] + chunk(b"acTL", struct.pack(">II", 2, 0)) + png()[33:]
        for data in (b"not an image", png()[:-2], bytes(crc), png() + b"tail", animation):
            with self.subTest(size=len(data)), self.assertRaises(ValueError):
                self.reader.read(str(self.write(data=data)))
        with self.assertRaisesRegex(ValueError, "matching extension"):
            self.reader.read(str(self.write("mismatch.png", JPEG)))

    @unittest.skipUnless(codex.sys.platform == "darwin", "macOS selected URL aliases")
    def test_macos_system_tmp_alias_is_supported_without_allowing_user_symlinks(self):
        path = self.write()
        alias = str(path).removeprefix("/private")
        self.assertEqual(self.reader.read(alias).data, path.read_bytes())
        self.assertEqual(self.reader.read(alias).path, alias)

    def test_stale_preview_is_refused_and_never_shows_replacement_bytes(self):
        path = self.write()
        spec = self.spec(path)
        path.write_bytes(png(color=(200, 100, 40)))
        before = self.files()
        with self.assertRaisesRegex(ValueError, "changed"):
            self.reader.preview(str(path), spec["sha256"])
        with self.assertRaisesRegex(ValueError, "changed"):
            self.backend.process(self.params(images=[spec]), lambda _: None, "send")
        result = self.backend.preview_context(self.params(images=[spec]))
        self.assertEqual(result["image_sources"][0]["state"], "changed")
        self.assertNotIn("data_base64", json.dumps(result))
        self.assertFalse(result["attachments_ready"])
        self.assertEqual(result["manifest"]["images"], [])
        self.assertEqual(before, self.files())
        self.assertFalse(self.backend.subscription.calls)

    def test_image_list_count_duplicates_total_size_and_payloads_are_bounded(self):
        spec = self.spec()
        for values in (None, {}, [{}], [spec] * 4, [spec, spec], [{**spec, "data_base64": "not allowed"}], [{**spec, "sha256": "wrong"}]):
            with self.subTest(values=values), self.assertRaises(ValueError):
                self.reader.selected(values)
        with patch.object(images, "MAX_TOTAL_IMAGE_BYTES", 1), self.assertRaisesRegex(ValueError, "8 MiB"):
            self.reader.selected([spec])

    def test_context_preview_has_metadata_only_and_does_not_connect(self):
        spec = self.spec()
        before = self.files()
        preview = self.backend.preview_context(self.params(images=[spec], cloud_consent=False))
        self.assertTrue(preview["attachments_ready"])
        self.assertFalse(preview["cloud_consent"])
        self.assertEqual(preview["manifest"]["images"], [spec])
        self.assertEqual(preview["manifest"]["destination"], "openai_cloud")
        self.assertFalse(preview["manifest"]["context_injection"]["enabled"])
        self.assertNotIn("data_base64", json.dumps(preview))
        self.assertEqual(before, self.files())
        self.assertFalse(self.backend.subscription.calls)

    def test_operator_commands_skip_images_without_reading_or_consuming_them(self):
        spec = self.spec()
        self.write(data=b"changed and invalid")
        with patch.object(images.ImageReader, "read", side_effect=AssertionError("No image read")):
            for text in ("/data doctor", "проверь систему"):
                result = self.backend.process(self.params(text=text, images=[spec]), lambda _: None, "operator")
                self.assertTrue(result["operator"])
                self.assertEqual(result["image_context"], [])
            preview = self.backend.preview_context(self.params(text="/data doctor", images=[spec]))
        self.assertEqual(preview["excluded_image_count"], 1)
        self.assertEqual(preview["manifest"]["images"], [])
        self.assertFalse(self.backend.subscription.calls)

    def test_cloud_consent_and_unsupported_local_providers_refuse_before_dispatch(self):
        spec = self.spec()
        before = self.files()
        for changes in ({"cloud_consent": False}, {"provider": "mock"}, {"provider": "ollama"}):
            with self.subTest(changes=changes), self.assertRaises(ValueError), patch.object(self.backend, "_coordinator", side_effect=AssertionError("No core")):
                self.backend.process(self.params(images=[spec], **changes), lambda _: None, "send")
        self.assertEqual(before, self.files())
        self.assertFalse(self.backend.preview_context(self.params(images=[spec], provider="mock"))["attachments_ready"])

    def test_send_uses_selected_bytes_and_saves_only_metadata_in_private_evidence(self):
        path = self.write()
        spec = self.spec(path)
        original = path.read_bytes()
        result = self.backend.process(self.params(images=[spec]), lambda _: None, "image-send")
        self.assertEqual(self.backend.subscription.images[0].data, original)
        self.assertEqual(result["image_context"], [spec])
        self.assertEqual(result["work_session"]["context_manifest"]["images"], [spec])
        self.assertEqual(path.read_bytes(), original)
        self.assertNotIn(str(self.workspace), self.backend.subscription.calls[0][0])
        self.assertIn("untrusted", self.backend.subscription.calls[0][0])
        serialized = json.dumps(result)
        self.assertNotIn("data_base64", serialized)
        self.assertNotIn(base64.b64encode(original).decode(), serialized)
        for content in self.files().values():
            self.assertNotIn(b"data:image/", content)
        self.assertEqual(result["work_session"]["sources"], [])

    def test_missing_image_cleanly_refuses_without_creating_work_session(self):
        spec = self.spec()
        Path(spec["path"]).unlink()
        with self.assertRaisesRegex(ValueError, "unreadable"):
            self.backend.process(self.params(images=[spec]), lambda _: None, "missing")
        self.assertFalse(self.state.exists())

    def test_full_access_images_keep_separate_explicit_grant(self):
        spec = self.spec()
        with self.assertRaises(ValueError):
            self.backend.process(self.params(images=[spec], access_mode="full_access"), lambda _: None, "denied")
        grant = self.backend.dispatch("agent_access", self.params(mode="full_access", confirmation=FULL_ACCESS_CONFIRMATION), lambda _: None, "grant")
        result = self.backend.process(self.params(images=[spec], access_mode="full_access", access_token=grant["token"]), lambda _: None, "full")
        self.assertEqual(self.backend.subscription.images[0].metadata, spec)
        self.assertEqual(result["work_session"]["access_mode"], "full_access")

    def test_image_byte_capture_is_immutable_after_validation(self):
        path = self.write()
        spec = self.spec(path)
        selected = self.reader.selected([spec])
        self.write(data=png(color=(200, 20, 10)))
        payload = images.image_input_items(selected)[0]["url"].split(",", 1)[1]
        self.assertEqual(hashlib.sha256(base64.b64decode(payload)).hexdigest(), spec["sha256"])

    def test_continuation_does_not_replay_image_inputs(self):
        result = self.backend.process(self.params(images=[self.spec()]), lambda _: None, "first")
        run = result["work_session"]
        request = self.params(continuation={"run_id": run["id"], "fingerprint": run["fingerprint"]})
        continuation = self.backend.dispatch("work_session_continuation", request, lambda _: None, "read")
        self.assertIn("изображения не прикреплены повторно", continuation["draft"])
        self.assertEqual(continuation["sources"], [])

    def test_work_session_rejects_corrupt_image_manifest_without_repair(self):
        result = self.backend.process(self.params(images=[self.spec()]), lambda _: None, "send")
        path = self.state / "work_sessions" / (result["work_session"]["id"] + ".json")
        record = json.loads(path.read_text())
        record["context_manifest"]["images"][0]["data_base64"] = "should not be persisted"
        path.write_text(json.dumps(record))
        before = self.files()
        self.assertTrue(self.backend.work_sessions.page(self.conversation)["warnings"])
        self.assertEqual(before, self.files())


class CodexImageTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="codex-image-adapter-")
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name).resolve()
        path = self.base / "fixture.png"; path.write_bytes(png())
        self.image = images.ImageReader(protected_roots=()).read(str(path))
        self.rpcs = []

        def factory(*args, **kwargs):
            rpc = AgentRPC(*args, **kwargs)
            rpc.model_data[0]["inputModalities"] = ["text", "image"]
            self.rpcs.append(rpc)
            return rpc
        self.client = codex.CodexSubscription(self.base / "state", transport_factory=factory)
        self.conversation = str(uuid4())
        self.logical_workspace = workspace_identity(self.base)
        self.addCleanup(self.client.close)
        executable = patch.object(codex.shutil, "which", return_value="/not-executed/codex")
        executable.start(); self.addCleanup(executable.stop)

    def test_codex_chat_sends_inline_image_without_local_file_or_tool_access(self):
        progress = []
        self.client.connect().events.insert(0, {"method": "item/started", "params": {"threadId": "thread", "turnId": "turn",
            "item": {"type": "userMessage", "id": "user", "content": images.image_input_items([self.image])}}})
        result = self.client.answer("Inspect this.", "Instructions", "", lambda _: None,
                                    conversation=self.conversation, logical_workspace=self.logical_workspace,
                                    history=[], on_progress=lambda e: progress.append(deepcopy(e)), images=[self.image])
        calls = dict(self.rpcs[-1].calls)
        self.assertEqual(result, "Hello operator.")
        self.assertEqual(calls["thread/start"]["sandbox"], "read-only")
        self.assertEqual(calls["turn/start"]["input"][1], images.image_input_items([self.image])[0])
        self.assertNotIn(self.image.path, json.dumps(calls["turn/start"]))
        self.assertNotIn("data:image/", json.dumps(progress))

    def test_image_support_is_catalog_driven_and_unknown_capability_fails_closed(self):
        for modalities in (None, [], ["text"], "image", {"image": True}):
            rpc = self.client.connect()
            rpc.model_data[0]["inputModalities"] = modalities
            rpc.calls.clear()
            with self.subTest(modalities=modalities), self.assertRaisesRegex(codex.CodexConnectionError, "does not confirm image"):
                self.client.answer("Inspect.", "Instructions", "", lambda _: None,
                                   conversation=self.conversation, logical_workspace=self.logical_workspace,
                                   history=[], images=[self.image])
            self.assertFalse(any(name in {"thread/start", "turn/start"} for name, _ in rpc.calls))
        options = codex.model_options([{"model": "fixture", "inputModalities": ["text", "image"], "private": "never copied"}])
        self.assertEqual(options[0]["input_modalities"], ["text", "image"])
        self.assertNotIn("private", options[0])

    def test_legacy_catalog_text_turn_still_works_without_image_support(self):
        self.client.connect().model_data[0].pop("inputModalities")
        self.assertEqual(self.client.answer("Text only.", "Instructions", "", lambda _: None,
                                            conversation=self.conversation, logical_workspace=self.logical_workspace,
                                            history=[]), "Hello operator.")
        self.assertEqual(len(dict(self.rpcs[-1].calls)["turn/start"]["input"]), 1)

    def test_full_access_uses_same_image_payload_and_closes_agent_process(self):
        self.client.agent_answer("Inspect.", "Instructions", "", lambda _: None,
                                 conversation=self.conversation, logical_workspace=self.logical_workspace, history=[],
                                 workspace=self.base, on_activity=lambda _: None, images=[self.image])
        self.assertEqual(dict(self.rpcs[-1].calls)["turn/start"]["input"][1], images.image_input_items([self.image])[0])
        self.assertTrue(self.rpcs[-1].closed)

    def test_unsupported_image_model_never_opens_full_access_transport(self):
        self.client.connect().model_data[0]["inputModalities"] = ["text"]
        with self.assertRaisesRegex(codex.CodexConnectionError, "does not confirm image"):
            self.client.agent_answer("Inspect.", "Instructions", "", lambda _: None,
                                     conversation=self.conversation, logical_workspace=self.logical_workspace, history=[],
                                     workspace=self.base, on_activity=lambda _: None, images=[self.image])
        self.assertFalse(any(rpc.full_access for rpc in self.rpcs))

    def test_rpc_handles_partial_writes_and_rejects_oversize_requests(self):
        captured = bytearray()
        def write(data):
            captured.extend(data[:7]); return min(7, len(data))
        rpc = codex.CodexRPC.__new__(codex.CodexRPC)
        rpc.lock, rpc.closed = threading.Lock(), False
        rpc.process = SimpleNamespace(poll=lambda: None, stdin=SimpleNamespace(write=write, flush=lambda: None))
        message = {"method": "turn/start", "input": images.image_input_items([self.image])}
        rpc._send(message)
        self.assertEqual(json.loads(captured), message)
        with patch.object(codex, "MAX_RPC_LINE", 20), self.assertRaisesRegex(codex.CodexConnectionError, "protocol limit"):
            rpc._send(message)
