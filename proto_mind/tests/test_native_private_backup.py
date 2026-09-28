import json
import os
import fcntl
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from proto_mind.memory_store import MemoryStore
from proto_mind.native_private_backup import PrivateBackup, encoded, read_file, digest, logical_path
from proto_mind.native_private_restore import PrivateRestore, without_authority
from proto_mind.private_state_gate import RESTORE_MARKER, generation, require_available


class PrivateBackupTests(unittest.TestCase):
    def test_restore_removes_remembered_mac_access_without_changing_original(self):
        raw = encoded({"version": 3, "cloudProcessingAllowed": True, "personaEnabled": True,
                       "rememberedAgentAccess": [{"conversationID": "fixture", "workspace": None}]})
        result = json.loads(without_authority("native/preferences.json", raw))
        self.assertFalse(result["cloudProcessingAllowed"])
        self.assertEqual(result["rememberedAgentAccess"], [])
        self.assertTrue(result["personaEnabled"])
        self.assertEqual(len(json.loads(raw)["rememberedAgentAccess"]), 1)

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.work = Path(self.temporary.name).resolve()
        self.root, self.state = self.work / "project", self.work / "state"
        self.root.mkdir(); self.state.mkdir()
        self.core = self.root / "proto_mind/data"
        self.memory = MemoryStore(self.core / "working_memory.json", self.core / "persistent_memory.json")
        self.write(self.core / "identity.json", {"name": "Before"})
        self.write(self.core / "context_injection.json", {"enabled": True})
        self.write(self.state / "conversations.json", {"version": 5, "conversations": [], "selectedID": None})
        self.write(self.state / "preferences.json", {"version": 2, "cloudProcessingAllowed": True, "personaEnabled": True})
        self.write(self.state / "integrations.json", {"schema": "proto_mind.native_integrations.v1", "github": {"login": "fixture"}})
        self.write(self.state / "codex_threads.json", {"historical": "binding-not-a-credential"})
        self.write(self.state / "work_sessions/one.json", {"status": "completed"})
        self.write(self.state / "project_memory/note.json", {"source": "saved"})
        self.write(self.state / "codex-profile/auth.json", {"token": "NEVER-COPY-CREDENTIAL-FIXTURE"})
        self.write(self.root / "exports/report.txt", "private report")
        self.write(self.root / "logs/operator.jsonl", "journal")
        (self.state / ".history.lock").touch()
        self.manager = PrivateRestore(self.root, self.state)
        self.source = self.work / "saved.protomind-backup"
        self.manager.export(self.source)
        self.window = "window-00000000-0000-0000-0000-000000000001.protomind-history"
        self.write(self.manager.directory / self.window / "conversations.json", {"version": 6, "conversations": [], "selectedID": None})

    def write(self, path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(encoded(value) if not isinstance(value, str) else value.encode())

    def change(self):
        self.write(self.core / "identity.json", {"name": "After"})
        self.write(self.state / "work_sessions/new.json", {"status": "completed"})

    def restore(self, manager=None):
        manager = manager or self.manager
        preview = manager.preview(self.source)
        return manager.restore(self.source, preview["sha256"], preview["target_fingerprint"], self.window)

    def hashes(self):
        return {row["path"]: row["sha256"] for row in self.manager.scan()["entries"]}

    def assert_restored(self, name="Before"):
        self.assertEqual(json.loads((self.core / "identity.json").read_text())["name"], name)
        self.assertFalse(json.loads((self.state / "preferences.json").read_text())["cloudProcessingAllowed"])
        self.assertIsNone(json.loads((self.state / "integrations.json").read_text())["github"])
        self.assertFalse(json.loads((self.core / "context_injection.json").read_text())["enabled"])
        self.assertFalse((self.state / "codex_threads.json").exists())
        self.assertFalse(self.manager.marker.exists())
        self.assertFalse((self.core / RESTORE_MARKER).exists())

    def test_snapshot_covers_owned_stores_without_credentials_or_live_locks(self):
        preview = self.manager.verify(self.source)
        self.assertTrue(preview["same_scope"])
        names = {p.relative_to(self.source).as_posix() for p in self.source.rglob("*") if p.is_file()}
        self.assertIn("payload/native/project_memory/note.json", names)
        self.assertIn("payload/exports/report.txt", names)
        self.assertIn("payload/logs/operator.jsonl", names)
        self.assertFalse(any("auth.json" in p or p.endswith(".lock") for p in names))
        self.assertNotIn(b"NEVER-COPY", b"".join(p.read_bytes() for p in self.source.rglob("*") if p.is_file()))

    def test_preview_and_status_are_read_only(self):
        before = {str(p): p.read_bytes() for p in self.work.rglob("*") if p.is_file()}
        self.manager.preview(self.source); self.manager.status()
        after = {str(p): p.read_bytes() for p in self.work.rglob("*") if p.is_file()}
        self.assertEqual(before, after)

    def test_existing_destination_is_never_replaced(self):
        before = read_file(self.source / "manifest.json")
        with self.assertRaises(ValueError): self.manager.export(self.source)
        self.assertEqual(before, read_file(self.source / "manifest.json"))

    def test_source_data_symlink_is_refused(self):
        (self.core / "unsafe").symlink_to(self.state / "codex-profile", target_is_directory=True)
        destination = self.work / "rejected"
        with self.assertRaises(ValueError): self.manager.export(destination)
        self.assertFalse(destination.exists())

    def test_archive_symlink_and_extra_file_are_refused(self):
        extra = self.source / "payload/core/extra"
        extra.symlink_to(self.state / "codex-profile/auth.json")
        with self.assertRaises(ValueError): self.manager.verify(self.source)
        extra.unlink(); extra.write_text("unexpected")
        with self.assertRaises(ValueError): self.manager.verify(self.source)

    def test_unsafe_paths_and_authority_paths_are_refused(self):
        for name in ["../core/a", "/core/a", "core/../a", "core//a", "core/a\\b", "native/codex-profile/auth.json", "native/.history.lock", "native/preferences.json/child", "native/chat_objects"]:
            with self.subTest(name=name), self.assertRaises(ValueError): logical_path(name)

    def test_unknown_native_namespace_is_not_silently_omitted(self):
        self.write(self.state / "future-private-store/data.json", {})
        with self.assertRaisesRegex(ValueError, "Неизвестный раздел"): self.manager.scan()

    def test_claude_login_and_provider_sessions_stay_outside_private_backup(self):
        self.write(self.state / "claude-profile/settings.json", {"secret":"NEVER-COPY-CLAUDE"})
        self.write(self.state / "claude_sessions/binding.json", {"session":"NEVER-COPY-CLAUDE"})
        target = self.work / "claude-excluded.protomind-backup"
        self.manager.export(target)
        self.assertNotIn(b"NEVER-COPY-CLAUDE", b"".join(p.read_bytes() for p in target.rglob("*") if p.is_file()))

    def test_attachment_library_copies_stay_outside_private_backup(self):
        # Like the original attachments, the library's copies of sent pictures and files are not archived.
        self.write(self.state / ("attachment_library/" + "a" * 64 + "/entry.json"), {"name": "NEVER-COPY-LIBRARY"})
        (self.state / ("attachment_library/" + "a" * 64 + "/original")).mkdir(parents=True)
        (self.state / ("attachment_library/" + "a" * 64 + "/original/picture.png")).write_bytes(b"NEVER-COPY-LIBRARY")
        target = self.work / "library-excluded.protomind-backup"
        self.manager.export(target)
        self.assertNotIn(b"NEVER-COPY-LIBRARY", b"".join(p.read_bytes() for p in target.rglob("*") if p.is_file()))

    def test_hash_corruption_is_refused_before_live_writes(self):
        (self.source / "payload/core/identity.json").write_text("corrupt")
        before = self.hashes()
        with self.assertRaises(ValueError): self.restore()
        self.assertEqual(before, self.hashes())

    def test_target_and_source_drift_require_a_new_preview(self):
        preview = self.manager.preview(self.source)
        self.change(); before = self.hashes()
        with self.assertRaises(ValueError): self.manager.restore(self.source, preview["sha256"], preview["target_fingerprint"], self.window)
        self.assertEqual(before, self.hashes())
        self.assertFalse(self.manager.marker.exists())

    def test_mid_snapshot_change_never_publishes(self):
        original = self.manager.inventory
        calls = 0
        def changed():
            nonlocal calls
            calls += 1
            if calls == 2: self.change()
            return original()
        destination = self.work / "unstable"
        with patch.object(self.manager, "inventory", side_effect=changed):
            with self.assertRaises(ValueError): self.manager.export(destination)
        self.assertFalse(destination.exists())

    def test_restore_preserves_before_image_and_locks_and_resets_access(self):
        self.change()
        previous = self.hashes()
        history_lock = (self.state / ".history.lock").stat().st_ino
        core_locks = {p.name: p.stat().st_ino for p in self.core.glob("*.lock")}
        result = self.restore()
        self.assert_restored()
        preserved = {row["path"]: row["sha256"] for row in self.manager._entries(Path(result["recovery_path"])).values()}
        self.assertEqual(previous, preserved)
        self.assertEqual(history_lock, (self.state / ".history.lock").stat().st_ino)
        self.assertEqual(core_locks, {p.name: p.stat().st_ino for p in self.core.glob("*.lock")})
        self.assertIn("NEVER-COPY", (self.state / "codex-profile/auth.json").read_text())
        self.assertTrue(Path(result["window_path"]).exists())

    def test_every_durable_boundary_can_resume_without_replaying_remote_work(self):
        for point in ["native_marker", "core_marker", "file:0", "file:3", "receipt", "generation", "core_unlocked"]:
            with self.subTest(point=point):
                self.change()
                def fail(value):
                    if value == point: raise OSError("simulated crash")
                manager = PrivateRestore(self.root, self.state, fault=fail)
                with self.assertRaises(OSError): self.restore(manager)
                pending = self.manager.status()
                self.assertTrue(pending["pending"])
                with self.assertRaises(ValueError): require_available(self.state)
                result = self.manager.resume(pending["id"])
                self.assertTrue(result["completed"])
                self.assert_restored()

    def test_partial_restore_can_return_previous_data_with_access_disabled(self):
        self.change()
        def fail(point):
            if point == "file:3": raise OSError("crash")
        with self.assertRaises(OSError): self.restore(PrivateRestore(self.root, self.state, fault=fail))
        pending = self.manager.status()
        result = self.manager.resume(pending["id"], rollback=True)
        self.assertEqual(result["direction"], "rollback")
        self.assert_restored("After")
        self.assertTrue((self.state / "work_sessions/new.json").exists())

    def test_outside_edits_during_interruption_are_preserved(self):
        def fail(point):
            if point == "core_marker": raise OSError("crash")
        with self.assertRaises(OSError): self.restore(PrivateRestore(self.root, self.state, fault=fail))
        self.write(self.core / "foreign.json", {"must": "survive"})
        pending = self.manager.status()
        with self.assertRaises(ValueError): self.manager.resume(pending["id"])
        self.assertTrue((self.core / "foreign.json").exists())
        self.assertTrue(self.manager.marker.exists())

    def test_corrupt_plan_cannot_resume_or_clear_the_gate(self):
        def fail(point):
            if point == "core_marker": raise OSError("crash")
        with self.assertRaises(OSError): self.restore(PrivateRestore(self.root, self.state, fault=fail))
        pending = self.manager.status()
        (self.manager._operation(pending["id"]) / "plan.json").write_text("{}")
        before = self.hashes()
        with self.assertRaises(ValueError): self.manager.resume(pending["id"])
        self.assertEqual(before, self.hashes())
        self.assertTrue(self.manager.status()["error"])

    def test_old_memory_instances_refuse_writes_after_restore(self):
        self.restore()
        with self.assertRaises(ValueError): self.memory.save_working_memory([])
        fresh = MemoryStore(self.core / "working_memory.json", self.core / "persistent_memory.json")
        self.assertEqual(fresh.load_working_memory(), [])

    def test_other_installation_requires_explicit_migration(self):
        other = PrivateRestore(self.work / "different-root", self.state)
        preview = other.preview(self.source)
        self.assertFalse(preview["same_scope"])
        with self.assertRaises(ValueError): other.restore(self.source, preview["sha256"], preview["target_fingerprint"], self.window)

    def test_file_directory_transitions_restore_and_rollback(self):
        self.write(self.core / "shape", "old file")
        source = self.work / "shape.protomind-backup"
        self.manager.export(source)
        (self.core / "shape").unlink()
        self.write(self.core / "shape/child", "new child")
        self.source = source
        self.restore()
        self.assertEqual((self.core / "shape").read_text(), "old file")

    def test_bridge_blocks_normal_calls_during_and_after_restore(self):
        from proto_mind.native_bridge import NativeBackend
        backend = NativeBackend(self.root, self.state)
        self.addCleanup(backend.close)
        emit = lambda _: None
        self.assertFalse(backend.dispatch("private_backup_status", {}, emit, "test")["pending"])
        self.restore()
        with self.assertRaises(ValueError): backend.dispatch("bootstrap", {}, emit, "test")
        self.assertFalse(backend.dispatch("private_backup_status", {}, emit, "test")["pending"])

    def test_completed_restore_survives_lost_response(self):
        def fail(point):
            if point == "completed": raise OSError("lost reply")
        with self.assertRaises(OSError): self.restore(PrivateRestore(self.root, self.state, fault=fail))
        self.assert_restored()
        identifier = json.loads(generation(self.state))["id"]
        receipt = json.loads(read_file(self.manager._operation(identifier) / "receipt.json"))
        self.assertTrue(receipt["completed"])
        self.assertEqual(generation(self.core), generation(self.state))
        with self.assertRaises(ValueError): self.memory.save_working_memory([])

    def test_restore_rechecks_source_location_without_preview(self):
        with self.assertRaisesRegex(ValueError, "вне папок"):
            self.manager.restore(self.core / "embedded.protomind-backup", "a" * 64, "b" * 64, self.window)
        self.assertFalse(self.manager.marker.exists())

    def test_duplicate_or_oversized_manifest_entries_are_refused(self):
        manifest = self.source / "manifest.json"
        original = manifest.read_bytes()
        for change in [lambda v: v["entries"].append(v["entries"][0]),
                       lambda v: v["entries"][0].update(size=2**32),
                       lambda v: v.update(schema="unknown")]:
            value = json.loads(original); change(value); manifest.write_bytes(encoded(value))
            with self.assertRaises(ValueError): self.manager.verify(self.source)
        manifest.write_bytes(b'{"schema":1,"schema":2}')
        with self.assertRaises(ValueError): self.manager.verify(self.source)
        self.assertFalse(self.manager.marker.exists())

    def test_history_lock_contention_refuses_copy_without_publishing(self):
        with (self.state / ".history.lock").open("rb") as stream:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            destination = self.work / "busy.protomind-backup"
            with self.assertRaises(ValueError): self.manager.export(destination)
            self.assertFalse(destination.exists())

    def test_corrupt_restore_blob_keeps_recovery_pending(self):
        def fail(point):
            if point == "core_marker": raise OSError("crash")
        with self.assertRaises(OSError): self.restore(PrivateRestore(self.root, self.state, fault=fail))
        pending = self.manager.status()
        blob = next((self.manager._operation(pending["id"]) / "blobs").iterdir())
        blob.write_text("corrupt")
        before = self.hashes()
        with self.assertRaises(ValueError): self.manager.resume(pending["id"])
        self.assertEqual(before, self.hashes())
        self.assertTrue(self.manager.marker.exists())

    def test_another_profile_core_marker_is_not_replaced(self):
        def fail(point):
            if point == "native_marker": raise OSError("crash")
        with self.assertRaises(OSError): self.restore(PrivateRestore(self.root, self.state, fault=fail))
        marker = self.core / RESTORE_MARKER
        self.write(marker, {"state": "/other/profile", "id": "other"})
        before = marker.read_bytes()
        with self.assertRaises(ValueError): self.manager.resume(self.manager.status()["id"])
        self.assertEqual(before, marker.read_bytes())

    def test_directory_to_file_and_interrupted_rollback_resume(self):
        self.write(self.core / "shape/child", "old child")
        self.source = self.work / "shape.protomind-backup"
        self.manager.export(self.source)
        (self.core / "shape/child").unlink(); (self.core / "shape").rmdir()
        self.write(self.core / "shape", "new file")
        def fail(point):
            if point == "receipt": raise OSError("crash")
        manager = PrivateRestore(self.root, self.state, fault=fail)
        with self.assertRaises(OSError): self.restore(manager)
        self.assertEqual((self.core / "shape/child").read_text(), "old child")
        identifier = self.manager.status()["id"]
        with self.assertRaises(OSError): manager.resume(identifier, rollback=True)
        self.assertEqual(self.manager.status()["direction"], "rollback")
        self.manager.resume(identifier)
        self.assertEqual((self.core / "shape").read_text(), "new file")


if __name__ == "__main__": unittest.main()
