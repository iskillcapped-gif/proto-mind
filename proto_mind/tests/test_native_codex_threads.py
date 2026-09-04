"""Durable Codex thread bindings: private IDs only, no provider or core calls."""
from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

from proto_mind import native_codex_threads as threads


class CodexThreadStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="proto-codex-threads-")
        self.addCleanup(self.temp.cleanup)
        self.state = Path(self.temp.name) / "state"
        self.store = threads.CodexThreadStore(self.state)
        self.conversation = str(uuid4())
        self.workspace = {"path": "/tmp/project", "device": 12, "inode": 34}
        self.contracts = {"chat": "a" * 64, "full_access": "b" * 64}

    def test_missing_status_is_read_only(self):
        status = self.store.status(self.conversation, self.workspace)
        self.assertFalse(status["linked"])
        self.assertFalse(self.state.exists())

    def test_record_persists_private_bounded_binding(self):
        row = self.store.record_new(self.conversation, "thread-fixture", self.workspace,
                                    mode="chat", model="gpt-fixture",
                                    instruction_contract_hash=self.contracts["chat"])
        self.assertEqual(row["thread_id"], "thread-fixture")
        status = threads.CodexThreadStore(self.state).status(self.conversation, self.workspace)
        self.assertTrue(status["linked"] and status["workspace_matches"])
        self.assertEqual(status["thread_id_short"], "thread-f")
        value = json.loads(self.store.path.read_text())
        self.assertEqual(value["schema"], threads.SCHEMA)
        self.assertEqual(value["bindings"][0]["instruction_mode"], "chat")
        self.assertEqual(value["bindings"][0]["instruction_contract_hash"], self.contracts["chat"])
        self.assertNotIn("prompt", self.store.path.read_text())
        self.assertEqual(self.store.path.stat().st_mode & 0o777, 0o600)

    def test_touch_preserves_identity_and_instruction_mode(self):
        original = self.store.record_new(self.conversation, "thread-fixture", self.workspace,
                                         mode="chat", model="first")
        updated = self.store.touch(self.conversation, "thread-fixture", self.workspace,
                                   mode="chat", model="second")
        self.assertEqual(updated["created_at"], original["created_at"])
        self.assertEqual(updated["thread_id"], original["thread_id"])
        self.assertEqual((updated["instruction_mode"], updated["last_mode"], updated["last_model"]),
                         ("chat", "chat", "second"))
        with self.assertRaisesRegex(threads.CodexThreadStoreError, "changed before dispatch"):
            self.store.touch(self.conversation, "thread-fixture", self.workspace,
                             mode="full_access", model="second")

    def test_chat_and_full_access_keep_separate_mode_bound_threads(self):
        self.store.record_new(self.conversation, "thread-chat", self.workspace, mode="chat", model="chat-model")
        self.store.record_new(self.conversation, "thread-full", self.workspace, mode="full_access", model="full-model")
        self.assertEqual(self.store.binding(self.conversation, self.workspace, mode="chat")["thread_id"], "thread-chat")
        self.assertEqual(self.store.binding(self.conversation, self.workspace, mode="full_access")["thread_id"], "thread-full")
        self.assertEqual(self.store.status(self.conversation, self.workspace, mode="chat")["available_modes"],
                         ["chat", "full_access"])

    def test_v2_binding_is_read_only_stale_until_a_provider_refresh(self):
        self.state.mkdir()
        now = threads.timestamp()
        legacy_mode_binding = {"schema": threads.MODE_SCHEMA, "bindings": [{
            "conversation_id": self.conversation, "thread_id": "mode-thread", "workspace": self.workspace,
            "created_at": now, "updated_at": now, "last_mode": "chat", "last_model": "old-model",
            "instruction_mode": "chat",
        }]}
        self.store.path.write_text(json.dumps(legacy_mode_binding), encoding="utf-8")
        before = self.store.path.read_bytes()

        status = self.store.status(
            self.conversation, self.workspace, mode="chat", instruction_contracts=self.contracts,
        )

        self.assertFalse(status["linked"])
        self.assertTrue(status["refresh_required"])
        self.assertEqual(status["stale_modes"], ["chat"])
        self.assertEqual(status["instruction_contract_hash_short"], "legacy")
        self.assertEqual(self.store.path.read_bytes(), before)
        self.assertEqual(
            self.store.binding(self.conversation, self.workspace, mode="chat")["instruction_contract_hash"],
            threads.UNKNOWN_INSTRUCTION_CONTRACT,
        )

    def test_contract_refresh_replaces_only_the_stale_mode_binding(self):
        old_chat = "c" * 64
        self.store.record_new(self.conversation, "thread-chat-old", self.workspace, mode="chat", model="old",
                              instruction_contract_hash=old_chat)
        self.store.record_new(self.conversation, "thread-full", self.workspace, mode="full_access", model="full",
                              instruction_contract_hash=self.contracts["full_access"])
        before_full = self.store.binding(self.conversation, self.workspace, mode="full_access")

        refreshed = self.store.refresh_contract(
            self.conversation, "thread-chat-old", "thread-chat-new", self.workspace,
            mode="chat", model="new", instruction_contract_hash=self.contracts["chat"],
        )

        self.assertEqual(refreshed["thread_id"], "thread-chat-new")
        self.assertEqual(refreshed["instruction_contract_hash"], self.contracts["chat"])
        self.assertEqual(self.store.binding(self.conversation, self.workspace, mode="full_access"), before_full)
        status = self.store.status(
            self.conversation, self.workspace, mode="chat", instruction_contracts=self.contracts,
        )
        self.assertTrue(status["linked"])
        self.assertFalse(status["refresh_required"])
        self.assertEqual(status["stale_modes"], [])

    def test_v2_refresh_preserves_other_mode_as_a_separate_stale_binding(self):
        self.state.mkdir()
        now = threads.timestamp()
        rows = [
            {"conversation_id": self.conversation, "thread_id": "old-chat", "workspace": self.workspace,
             "created_at": now, "updated_at": now, "last_mode": "chat", "last_model": "chat-model",
             "instruction_mode": "chat"},
            {"conversation_id": self.conversation, "thread_id": "old-full", "workspace": self.workspace,
             "created_at": now, "updated_at": now, "last_mode": "full_access", "last_model": "full-model",
             "instruction_mode": "full_access"},
        ]
        self.store.path.write_text(json.dumps({"schema": threads.MODE_SCHEMA, "bindings": rows}), encoding="utf-8")

        self.store.refresh_contract(
            self.conversation, "old-chat", "new-chat", self.workspace,
            mode="chat", model="new-model", instruction_contract_hash=self.contracts["chat"],
        )

        saved = json.loads(self.store.path.read_text(encoding="utf-8"))
        self.assertEqual(saved["schema"], threads.SCHEMA)
        full = self.store.binding(self.conversation, self.workspace, mode="full_access")
        self.assertEqual((full["thread_id"], full["created_at"], full["last_model"]),
                         ("old-full", now, "full-model"))
        self.assertEqual(full["instruction_contract_hash"], threads.UNKNOWN_INSTRUCTION_CONTRACT)
        full_status = self.store.status(
            self.conversation, self.workspace, mode="full_access", instruction_contracts=self.contracts,
        )
        self.assertTrue(full_status["refresh_required"])
        self.assertFalse(full_status["linked"])

    def test_contract_refresh_is_compare_and_swap_and_never_reuses_a_thread_id(self):
        self.store.record_new(self.conversation, "thread-chat", self.workspace, mode="chat", model="old",
                              instruction_contract_hash="c" * 64)
        before = self.store.path.read_bytes()
        with self.assertRaisesRegex(threads.CodexThreadStoreError, "reused thread ID"):
            self.store.refresh_contract(
                self.conversation, "thread-chat", "thread-chat", self.workspace,
                mode="chat", model="new", instruction_contract_hash=self.contracts["chat"],
            )
        self.assertEqual(self.store.path.read_bytes(), before)

    def test_workspace_drift_requires_explicit_reset(self):
        self.store.record_new(self.conversation, "thread-fixture", self.workspace, mode="chat", model="")
        other = {**self.workspace, "inode": 35}
        status = self.store.status(self.conversation, other)
        self.assertTrue(status["linked"] and not status["workspace_matches"])
        with self.assertRaisesRegex(threads.CodexThreadStoreError, "another workspace"):
            self.store.binding(self.conversation, other, mode="chat")
        self.assertEqual(self.store.binding(self.conversation, self.workspace, mode="chat")["thread_id"], "thread-fixture")

    def test_duplicate_conversation_or_thread_is_refused(self):
        self.store.record_new(self.conversation, "thread-fixture", self.workspace, mode="chat", model="")
        self.store.record_new(self.conversation, "full-thread", self.workspace, mode="full_access", model="")
        for conversation, provider, mode in ((self.conversation, "other-thread", "chat"),
                                              (str(uuid4()), "thread-fixture", "chat")):
            with self.subTest(conversation=conversation, provider=provider), self.assertRaisesRegex(
                    threads.CodexThreadStoreError, "concurrently"):
                self.store.record_new(conversation, provider, self.workspace, mode=mode, model="")

    def test_reset_unbinds_only_selected_conversation(self):
        other = str(uuid4())
        self.store.record_new(self.conversation, "thread-one", self.workspace, mode="chat", model="")
        self.store.record_new(self.conversation, "thread-full", self.workspace, mode="full_access", model="")
        self.store.record_new(other, "thread-two", None, mode="chat", model="")
        self.assertTrue(self.store.reset(self.conversation))
        self.assertFalse(self.store.reset(self.conversation))
        self.assertFalse(self.store.status(self.conversation, self.workspace)["linked"])
        self.assertTrue(self.store.status(other, None)["linked"])

    def test_legacy_binding_is_read_only_and_never_reused_as_a_known_mode(self):
        self.state.mkdir()
        now = threads.timestamp()
        legacy = {"schema": threads.LEGACY_SCHEMA, "bindings": [{
            "conversation_id": self.conversation, "thread_id": "legacy-thread", "workspace": self.workspace,
            "created_at": now, "updated_at": now, "last_mode": "full_access", "last_model": "legacy-model",
        }]}
        self.store.path.write_text(json.dumps(legacy), encoding="utf-8")
        before = self.store.path.read_bytes()
        status = self.store.status(self.conversation, self.workspace, mode="full_access")
        self.assertFalse(status["linked"])
        self.assertTrue(status["legacy_binding"])
        self.assertIsNone(self.store.binding(self.conversation, self.workspace, mode="full_access"))
        self.assertEqual(self.store.path.read_bytes(), before)
        self.store.record_new(self.conversation, "fresh-full", self.workspace,
                              mode="full_access", model="current-model")
        value = json.loads(self.store.path.read_text(encoding="utf-8"))
        self.assertEqual(value["schema"], threads.SCHEMA)
        self.assertEqual({row["instruction_mode"] for row in value["bindings"]},
                         {threads.LEGACY_MODE, "full_access"})
        self.assertEqual(self.store.binding(self.conversation, self.workspace,
                                            mode="full_access")["thread_id"], "fresh-full")

    def test_corrupt_registry_is_never_overwritten(self):
        self.state.mkdir()
        damaged = b"not valid json"
        self.store.path.write_bytes(damaged)
        with self.assertRaises(threads.CodexThreadStoreError):
            self.store.status(self.conversation, self.workspace)
        with self.assertRaises(threads.CodexThreadStoreError):
            self.store.record_new(self.conversation, "thread", self.workspace, mode="chat", model="")
        self.assertEqual(self.store.path.read_bytes(), damaged)

    def test_symlink_registry_is_refused_without_touching_target(self):
        self.state.mkdir()
        target = Path(self.temp.name) / "target.json"
        target.write_text("private fixture")
        self.store.path.symlink_to(target)
        with self.assertRaises(threads.CodexThreadStoreError):
            self.store.status(self.conversation, self.workspace)
        self.assertEqual(target.read_text(), "private fixture")
        self.assertTrue(self.store.path.is_symlink())

    def test_failed_atomic_replace_preserves_previous_registry(self):
        self.store.record_new(self.conversation, "thread-one", self.workspace, mode="chat", model="")
        before = self.store.path.read_bytes()
        with patch.object(threads.os, "replace", side_effect=OSError("fixture disk failure")):
            with self.assertRaisesRegex(threads.CodexThreadStoreError, "Could not save"):
                self.store.record_new(str(uuid4()), "thread-two", None, mode="chat", model="")
        self.assertEqual(self.store.path.read_bytes(), before)
        self.assertEqual(list(self.state.glob(".codex_threads.*.tmp")), [])

    def test_invalid_fields_and_limits_are_rejected(self):
        for provider in ("", "with space", "x" * 161, "bad\nthread"):
            with self.subTest(provider=provider), self.assertRaises(threads.CodexThreadStoreError):
                self.store.record_new(self.conversation, provider, self.workspace, mode="chat", model="")
        with self.assertRaises(threads.CodexThreadStoreError):
            self.store.record_new(self.conversation, "thread", self.workspace, mode="automatic", model="")


if __name__ == "__main__":
    unittest.main()
