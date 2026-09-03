"""Crash, ownership, integrity, and no-repair checks for Session Spine P2."""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import stat
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch
from uuid import uuid4

from proto_mind.session_spine import SessionEvent
from proto_mind.native_progress import display_text
from proto_mind.native_session_spine import project_native_turn
from proto_mind.session_spine_store import (
    COMMIT_SCHEMA,
    MAX_EVENTS,
    PROJECTION_SCHEMA,
    RETENTION_SCHEMA,
    SessionSpineStore,
    SessionSpineStoreBusy,
    SessionSpineStoreError,
    SessionSpineStoreMissing,
)


class SessionSpineStoreTests(TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.parent = Path(self.temporary.name).resolve()
        self.root = self.parent / "session-spine"
        self.session_id = str(uuid4())
        self.store = SessionSpineStore(self.root)

    def tearDown(self):
        self.temporary.cleanup()

    def event(self, sequence, event_type="turn/start", **data):
        return SessionEvent.create(sequence, 1000 + sequence, event_type, data or {"turn": 1})

    def data_path(self):
        return self.root / f"{self.session_id}.spine.jsonl"

    def lock_path(self):
        return self.root / f"{self.session_id}.spine.lock"

    def create_complete(self):
        with self.store.writer(self.session_id, "owner.first", created_ms=1000) as writer:
            receipts = [
                writer.append(self.event(0)),
                writer.append(SessionEvent.create(1, 1001, "user/message", {"text": "hello"}, surface_op="append")),
                writer.append(SessionEvent.create(2, 1002, "assistant/message", {"text": "hi"}, surface_op="append")),
                writer.append(self.event(3, "turn/end", outcome="response_recorded")),
            ]
        return receipts

    def test_missing_inspection_is_read_only(self):
        with self.assertRaisesRegex(SessionSpineStoreMissing, "created nothing"):
            self.store.inspect(self.session_id)
        self.assertFalse(self.root.exists())

    def test_new_store_requires_explicit_absolute_path_time_and_owner(self):
        with self.assertRaisesRegex(SessionSpineStoreError, "absolute"):
            SessionSpineStore(Path("relative"))
        with self.assertRaisesRegex(SessionSpineStoreError, "creation time"):
            with self.store.writer(self.session_id, "owner.first"):
                pass
        self.assertFalse(self.root.exists())
        with self.assertRaisesRegex(SessionSpineStoreError, "owner"):
            self.store.writer(self.session_id, "owner with spaces", created_ms=1000)

    def test_committed_turn_replays_after_restart_with_hash_chain(self):
        receipts = self.create_complete()
        reopened = SessionSpineStore(self.root).inspect(self.session_id)
        self.assertEqual(reopened.recovery_state, "closed")
        self.assertEqual([event.event_type for event in reopened.events],
                         ["turn/start", "user/message", "assistant/message", "turn/end"])
        self.assertEqual(reopened.surface.nodes, (1, 2))
        self.assertEqual(receipts[1].previous_commit_hash, receipts[0].commit_hash)
        self.assertEqual(reopened.last_commit_hash, receipts[-1].commit_hash)
        self.assertEqual(reopened.file_sha256, receipts[-1].file_sha256)
        self.assertEqual(reopened.to_dict()["schema"], PROJECTION_SCHEMA)
        self.assertTrue(reopened.to_dict()["read_only"])
        self.assertFalse(reopened.to_dict()["task_success_inferred"])

    def test_receipt_records_explicit_owner_and_no_target_execution(self):
        with self.store.writer(self.session_id, "owner.alpha", created_ms=5) as writer:
            receipt = writer.append(self.event(0))
        value = receipt.to_dict()
        self.assertEqual(value["owner_id"], "owner.alpha")
        self.assertTrue(value["durable_commit_requested"])
        self.assertFalse(value["target_command_executed"])
        self.assertEqual(self.store.inspect(self.session_id).created_by, "owner.alpha")

    def test_native_p1_projection_round_trips_through_p2_without_loss(self):
        conversation = str(uuid4())
        run_id = str(uuid4())
        user_id = str(uuid4())
        assistant_id = str(uuid4())
        prompt = "Inspect a detached fixture."
        displayed = "Rendered answer"
        raw = "Raw provider answer"
        run = {
            "schema": "proto_mind.native_work_session.v1", "id": run_id,
            "conversation_id": conversation, "project_root": "/synthetic/project",
            "workspace": {"path": "/synthetic/project", "device": 1, "inode": 2},
            "created_at": "2026-09-03T10:00:00.000000Z",
            "updated_at": "2026-09-03T10:01:00.000000Z",
            "finished_at": "2026-09-03T10:01:00.000000Z", "status": "completed",
            "display_status": "completed", "provider": "codex", "requested_model": "gpt-5.6-sol",
            "requested_effort": "high", "access_mode": "chat",
            "input_preview": display_text(prompt, 800), "input_chars": len(prompt),
            "input_sha256": hashlib.sha256(prompt.encode()).hexdigest(), "answer_preview": display_text(raw, 1600),
            "sources": [], "parent_run_id": None, "tools": [], "work_log": {},
            "network_access_performed": False, "computer_use_performed": False,
            "screen_access_performed": False, "verification": "not_assessed",
            "acceptance": "not_recorded", "fingerprint": "a" * 64, "automatic_resume": False,
        }
        projection = project_native_turn(
            conversation_id=conversation,
            user_message={"id": user_id, "role": "user", "text": prompt,
                          "isError": False, "operatorInput": False},
            assistant_message={"id": assistant_id, "role": "assistant", "text": displayed,
                               "raw": raw, "isError": False},
            work_session=run,
        )
        with self.store.writer(self.session_id, "owner.projection", created_ms=1000) as writer:
            for event in projection.events:
                writer.append(event)
        restored = self.store.inspect(self.session_id)
        self.assertEqual(restored.events, projection.events)
        self.assertEqual(restored.surface, projection.surface)
        self.assertEqual(restored.recovery_state, "closed")

    def test_existing_clean_session_requires_fresh_inspected_fingerprint(self):
        self.create_complete()
        before = self.data_path().read_bytes()
        with self.assertRaisesRegex(SessionSpineStoreError, "supply its exact fingerprint"):
            with self.store.writer(self.session_id, "owner.second", created_ms=2000):
                pass
        self.assertEqual(self.data_path().read_bytes(), before)

    def test_stale_fingerprint_refuses_without_touching_session_data_or_lock(self):
        self.create_complete()
        before_data = self.data_path().read_bytes()
        before_lock = self.lock_path().read_bytes()
        with self.assertRaisesRegex(SessionSpineStoreError, "changed after inspection"):
            with self.store.writer(self.session_id, "owner.second", expected_fingerprint="0" * 64):
                pass
        self.assertEqual(self.data_path().read_bytes(), before_data)
        self.assertEqual(self.lock_path().read_bytes(), before_lock)

    def test_fresh_fingerprint_allows_a_new_turn_under_a_new_owner(self):
        self.create_complete()
        snapshot = self.store.inspect(self.session_id)
        with self.store.writer(
            self.session_id,
            "owner.second",
            expected_fingerprint=snapshot.file_sha256,
        ) as writer:
            receipt = writer.append(self.event(4, turn=2))
        reopened = self.store.inspect(self.session_id)
        self.assertEqual(receipt.owner_id, "owner.second")
        self.assertEqual(reopened.recovery_state, "unknown")
        self.assertEqual(reopened.append_owners, ("owner.first", "owner.second"))
        self.assertFalse(reopened.appendable)

    def test_only_one_writer_and_no_unstable_reader(self):
        with self.store.writer(self.session_id, "owner.first", created_ms=1000):
            with self.assertRaises(SessionSpineStoreBusy):
                with self.store.writer(self.session_id, "owner.second", created_ms=1000):
                    pass
            with self.assertRaises(SessionSpineStoreBusy):
                self.store.inspect(self.session_id)

    def test_committed_open_turn_recovers_as_unknown_and_cannot_auto_resume(self):
        with self.store.writer(self.session_id, "owner.first", created_ms=1000) as writer:
            writer.append(self.event(0))
        before = self.data_path().read_bytes()
        snapshot = self.store.inspect(self.session_id)
        self.assertEqual(snapshot.recovery_state, "unknown")
        self.assertIn("outcome remains unknown", snapshot.warnings[0])
        with self.assertRaisesRegex(SessionSpineStoreError, "automatic resume"):
            with self.store.writer(
                self.session_id,
                "owner.recovery",
                expected_fingerprint=snapshot.file_sha256,
            ):
                pass
        self.assertEqual(self.data_path().read_bytes(), before)

    def test_complete_prepare_without_commit_is_not_replayed_or_repaired(self):
        with self.store.writer(self.session_id, "owner.first", created_ms=1000) as writer:
            original = writer._write_and_sync
            calls = 0

            def fail_commit(payload):
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise OSError("simulated commit failure")
                original(payload)

            writer._write_and_sync = fail_commit
            with self.assertRaisesRegex(SessionSpineStoreError, "Do not retry"):
                writer.append(self.event(0))
        before = self.data_path().read_bytes()
        snapshot = self.store.inspect(self.session_id)
        self.assertEqual(snapshot.events, ())
        self.assertEqual(snapshot.uncommitted_event_seq, 0)
        self.assertEqual(snapshot.recovery_state, "unknown")
        self.assertFalse(snapshot.appendable)
        self.assertEqual(self.data_path().read_bytes(), before)
        with self.assertRaisesRegex(SessionSpineStoreError, "incomplete tail"):
            with self.store.writer(
                self.session_id,
                "owner.recovery",
                expected_fingerprint=snapshot.file_sha256,
            ):
                pass

    def test_partial_prepare_is_a_torn_tail_and_never_replayed(self):
        with self.store.writer(self.session_id, "owner.first", created_ms=1000) as writer:
            def tear(payload):
                os.write(writer.data, payload[:23])
                os.fsync(writer.data)
                raise OSError("simulated torn write")

            writer._write_and_sync = tear
            with self.assertRaisesRegex(SessionSpineStoreError, "Do not retry"):
                writer.append(self.event(0))
        before = self.data_path().read_bytes()
        snapshot = self.store.inspect(self.session_id)
        self.assertEqual(snapshot.events, ())
        self.assertEqual(snapshot.torn_tail_bytes, 23)
        self.assertEqual(snapshot.recovery_state, "unknown")
        self.assertIn("no repair", " ".join(snapshot.warnings).lower())
        self.assertEqual(self.data_path().read_bytes(), before)

    def test_writer_refuses_retry_after_uncertain_append(self):
        with self.store.writer(self.session_id, "owner.first", created_ms=1000) as writer:
            def fail(_: bytes):
                raise OSError("simulated")

            writer._write_and_sync = fail
            with self.assertRaises(SessionSpineStoreError):
                writer.append(self.event(0))
            with self.assertRaisesRegex(SessionSpineStoreError, "previous append outcome is unknown"):
                writer.append(self.event(0))

    def test_tampered_committed_event_fails_closed(self):
        self.create_complete()
        lines = self.data_path().read_bytes().splitlines()
        prepared = json.loads(lines[1])
        prepared["event"]["data"]["turn"] = 99
        lines[1] = json.dumps(prepared, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        self.data_path().write_bytes(b"\n".join(lines) + b"\n")
        with self.assertRaisesRegex(SessionSpineStoreError, "hash does not verify"):
            self.store.inspect(self.session_id)

    def test_malformed_committed_line_is_corruption_not_a_torn_tail(self):
        self.create_complete()
        lines = self.data_path().read_bytes().splitlines()
        lines[2] = b"{}"
        self.data_path().write_bytes(b"\n".join(lines) + b"\n")
        with self.assertRaisesRegex(SessionSpineStoreError, "commit"):
            self.store.inspect(self.session_id)

    def test_noncanonical_committed_json_is_refused(self):
        self.create_complete()
        lines = self.data_path().read_bytes().splitlines()
        lines[2] = json.dumps(json.loads(lines[2]), indent=2).encode()
        self.data_path().write_bytes(b"\n".join(lines) + b"\n")
        with self.assertRaisesRegex(SessionSpineStoreError, "canonical"):
            self.store.inspect(self.session_id)

    def test_data_without_lock_is_not_silently_adopted(self):
        self.create_complete()
        self.lock_path().unlink()
        before = self.data_path().read_bytes()
        with self.assertRaisesRegex(SessionSpineStoreError, "without its ownership lock"):
            self.store.inspect(self.session_id)
        self.assertEqual(self.data_path().read_bytes(), before)
        self.assertFalse(self.lock_path().exists())

    def test_symlinked_directory_data_and_lock_are_refused(self):
        outside = self.parent / "outside"
        outside.mkdir(mode=0o700)
        alias = self.parent / "alias"
        alias.symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(SessionSpineStoreError, "unsafe"):
            SessionSpineStore(alias).inspect(self.session_id)

        self.create_complete()
        target = self.parent / "target"
        target.write_text("not evidence")
        self.data_path().unlink()
        self.data_path().symlink_to(target)
        with self.assertRaisesRegex(SessionSpineStoreError, "unsafe"):
            self.store.inspect(self.session_id)

        self.data_path().unlink()
        target.write_bytes(b"unused")
        self.data_path().write_bytes(b"unused")
        os.chmod(self.data_path(), 0o600)
        self.lock_path().unlink()
        self.lock_path().symlink_to(target)
        with self.assertRaisesRegex(SessionSpineStoreError, "unsafe"):
            self.store.inspect(self.session_id)

    def test_replacing_open_data_file_is_detected_before_append(self):
        with self.store.writer(self.session_id, "owner.first", created_ms=1000) as writer:
            original = self.data_path().with_suffix(".old")
            self.data_path().rename(original)
            self.data_path().write_bytes(original.read_bytes())
            os.chmod(self.data_path(), 0o600)
            with self.assertRaisesRegex(SessionSpineStoreError, "changed while"):
                writer.append(self.event(0))

    def test_invalid_turn_sequence_is_refused_before_write(self):
        with self.store.writer(self.session_id, "owner.first", created_ms=1000) as writer:
            before = self.data_path().read_bytes()
            with self.assertRaisesRegex(SessionSpineStoreError, "never started"):
                writer.append(self.event(0, "turn/end"))
            self.assertEqual(self.data_path().read_bytes(), before)

    def test_event_limit_refuses_without_automatic_compaction(self):
        with patch("proto_mind.session_spine_store.MAX_EVENTS", 1):
            with self.store.writer(self.session_id, "owner.first", created_ms=1000) as writer:
                writer.append(self.event(0))
                before = self.data_path().read_bytes()
                with self.assertRaisesRegex(SessionSpineStoreError, "limit reached"):
                    writer.append(SessionEvent.create(1, 1001, "user/message", {}, surface_op="append"))
                self.assertEqual(self.data_path().read_bytes(), before)

    def test_session_count_is_bounded_under_a_catalog_lock(self):
        second = str(uuid4())
        with patch("proto_mind.session_spine_store.MAX_SESSIONS", 1):
            with self.store.writer(self.session_id, "owner.first", created_ms=1000):
                pass
            with self.assertRaisesRegex(SessionSpineStoreError, "Session count limit"):
                with self.store.writer(second, "owner.second", created_ms=1000):
                    pass
        self.assertFalse((self.root / f"{second}.spine.jsonl").exists())
        self.assertFalse((self.root / f"{second}.spine.lock").exists())

    def test_retention_preview_is_read_only_and_never_compacts(self):
        self.create_complete()
        before = self.data_path().read_bytes()
        preview = self.store.retention_preview(self.session_id)
        self.assertEqual(preview["schema"], RETENTION_SCHEMA)
        self.assertTrue(preview["read_only"])
        self.assertFalse(preview["automatic_compaction"])
        self.assertFalse(preview["automatic_deletion"])
        self.assertTrue(preview["export_required_before_compaction"])
        self.assertEqual(self.data_path().read_bytes(), before)

    def test_files_are_private_and_reader_does_not_change_timestamps_or_bytes(self):
        self.create_complete()
        before_data = self.data_path().read_bytes()
        before_lock = self.lock_path().read_bytes()
        before_stats = (self.data_path().stat().st_mtime_ns, self.lock_path().stat().st_mtime_ns)
        self.store.inspect(self.session_id)
        self.assertEqual(stat.S_IMODE(self.data_path().stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(self.lock_path().stat().st_mode), 0o600)
        self.assertEqual(self.data_path().read_bytes(), before_data)
        self.assertEqual(self.lock_path().read_bytes(), before_lock)
        self.assertEqual((self.data_path().stat().st_mtime_ns, self.lock_path().stat().st_mtime_ns), before_stats)

    def test_snapshot_and_sources_are_immutable_detached_values(self):
        source = self.event(0, metadata={"value": 1})
        source_dict = deepcopy(source.to_dict())
        with self.store.writer(self.session_id, "owner.first", created_ms=1000) as writer:
            writer.append(source)
        snapshot = self.store.inspect(self.session_id)
        self.assertEqual(source.to_dict(), source_dict)
        with self.assertRaises(AttributeError):
            snapshot.events = ()

    def test_unexpected_commit_where_prepare_is_required_fails_closed(self):
        with self.store.writer(self.session_id, "owner.first", created_ms=1000):
            pass
        lines = self.data_path().read_bytes().splitlines()
        fake = {
            "schema": COMMIT_SCHEMA,
            "session_id": self.session_id,
            "ordinal": 0,
            "owner_id": "owner.first",
            "previous_commit_hash": "0" * 64,
            "prepare_hash": "0" * 64,
            "commit_hash": "0" * 64,
        }
        lines.append(json.dumps(fake, sort_keys=True, separators=(",", ":")).encode())
        self.data_path().write_bytes(b"\n".join(lines) + b"\n")
        with self.assertRaisesRegex(SessionSpineStoreError, "Prepared session event"):
            self.store.inspect(self.session_id)

    def test_limit_constant_remains_bounded(self):
        self.assertLessEqual(MAX_EVENTS, 1024)
