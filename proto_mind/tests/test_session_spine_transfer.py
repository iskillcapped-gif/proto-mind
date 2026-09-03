"""Fixture-only export, migration parity, and rollback preview checks for P2b."""
from copy import deepcopy
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import stat
from tempfile import TemporaryDirectory
from unittest import TestCase
from uuid import uuid4

from proto_mind.native_progress import display_text
from proto_mind.session_spine import SessionEvent
from proto_mind.session_spine_store import build_store_image, inspect_store_image
from proto_mind.session_spine_transfer import (
    CANDIDATE_FILE,
    EXPORT_SCHEMA,
    FIXTURE_SCHEMA,
    MANIFEST_FILE,
    ROLLBACK_FILE,
    SOURCE_FILE,
    SessionSpineTransferError,
    export_migration_preview,
    preview_export_rollback,
    preview_native_fixture_migration,
    verify_migration_export,
)


def _canonical_line(value):
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8") + b"\n"


class SessionSpineTransferTests(TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve()
        self.export_root = self.root / "exports"
        self.conversation = str(uuid4())
        self.run_id = str(uuid4())
        self.user_id = str(uuid4())
        self.assistant_id = str(uuid4())
        self.prompt = "Проверь только синтетический fixture."
        self.answer = "Fixture проверен; успех реальной задачи не утверждается."
        self.owner = "migration.preview"

    def tearDown(self):
        self.temporary.cleanup()

    def fixture(self, **changes):
        run = {
            "schema": "proto_mind.native_work_session.v1",
            "id": self.run_id,
            "conversation_id": self.conversation,
            "project_root": "/synthetic/project",
            "workspace": {"path": "/synthetic/project", "device": 1, "inode": 2},
            "created_at": "2026-09-03T10:00:00.000000Z",
            "updated_at": "2026-09-03T10:01:00.000000Z",
            "finished_at": "2026-09-03T10:01:00.000000Z",
            "status": "completed",
            "provider": "codex",
            "requested_model": "gpt-5.6-sol",
            "requested_effort": "high",
            "access_mode": "chat",
            "input_preview": display_text(self.prompt, 800),
            "input_chars": len(self.prompt),
            "input_sha256": hashlib.sha256(self.prompt.encode()).hexdigest(),
            "answer_preview": display_text(self.answer, 1600),
            "sources": [],
            "parent_run_id": None,
            "tools": [],
            "work_log": {},
            "network_access_performed": False,
            "computer_use_performed": False,
            "screen_access_performed": False,
            "verification": "not_assessed",
            "acceptance": "not_recorded",
            "display_status": "completed",
            "fingerprint": "a" * 64,
            "automatic_resume": False,
        }
        value = {
            "schema": FIXTURE_SCHEMA,
            "conversation_id": self.conversation,
            "user_message": {
                "id": self.user_id,
                "role": "user",
                "text": self.prompt,
                "isError": False,
                "operatorInput": False,
            },
            "assistant_message": {
                "id": self.assistant_id,
                "role": "assistant",
                "text": self.answer,
                "raw": self.answer,
                "isError": False,
            },
            "work_session": run,
        }
        value.update(changes)
        return value

    def fixture_raw(self, **changes):
        return _canonical_line(self.fixture(**changes))

    def different_preimage(self):
        events = (
            SessionEvent.create(0, 1, "turn/start", {"fixture": "older"}),
            SessionEvent.create(1, 2, "user/message", {"text": "old"}, surface_op="append"),
            SessionEvent.create(2, 3, "assistant/message", {"text": "old"}, surface_op="append"),
            SessionEvent.create(3, 4, "turn/end", {"outcome": "response_recorded"}),
        )
        return build_store_image(
            session_id=self.conversation,
            created_ms=1,
            owner_id="migration.previous",
            events=events,
        )

    def preview(self, *, target=None):
        return preview_native_fixture_migration(
            self.fixture_raw(),
            owner_id=self.owner,
            target_preimage=target,
        )

    def export(self, preview=None, export_id=None):
        return export_migration_preview(
            preview or self.preview(),
            export_root=self.export_root,
            export_id=export_id or str(uuid4()),
            generated_ms=1_788_448_000_000,
        )

    def test_preview_builds_exact_p1_to_p2_candidate_without_writing(self):
        source = self.fixture_raw()
        before = bytes(source)
        result = preview_native_fixture_migration(source, owner_id=self.owner)
        snapshot = inspect_store_image(result._candidate_raw, self.conversation)

        self.assertEqual(source, before)
        self.assertFalse(self.export_root.exists())
        self.assertEqual(result.migration_status, "READY_FOR_SEPARATE_REVIEW")
        self.assertEqual(result.target_state, "absent")
        self.assertEqual(snapshot.surface.fingerprint, result.surface_fingerprint)
        self.assertEqual(len(snapshot.events), result.event_count)
        self.assertEqual(hashlib.sha256(result._candidate_raw).hexdigest(), result.candidate_sha256)
        report = result.to_dict()
        self.assertTrue(report["read_only"])
        self.assertFalse(report["apply_installed"])
        self.assertFalse(report["task_success_inferred"])
        self.assertFalse(report["source"]["safe_to_publish"])
        self.assertNotIn(self.prompt, str(report))

    def test_preview_is_deterministic_and_does_not_mutate_fixture_object(self):
        fixture = self.fixture()
        before = deepcopy(fixture)
        raw = _canonical_line(fixture)
        first = preview_native_fixture_migration(raw, owner_id=self.owner)
        second = preview_native_fixture_migration(raw, owner_id=self.owner)

        self.assertEqual(fixture, before)
        self.assertEqual(first, second)

    def test_noncanonical_duplicate_or_invalid_projection_fixture_fails_closed(self):
        noncanonical = json.dumps(self.fixture(), ensure_ascii=False).encode() + b"\n"
        duplicate = b'{"schema":"x","schema":"y"}\n'
        invalid = self.fixture()
        invalid["work_session"]["input_sha256"] = "b" * 64
        for raw in (noncanonical, duplicate, _canonical_line(invalid), self.fixture_raw()[:-1]):
            with self.subTest(raw=raw[:40]), self.assertRaises(SessionSpineTransferError):
                preview_native_fixture_migration(raw, owner_id=self.owner)
        self.assertFalse(self.export_root.exists())

    def test_identical_target_is_a_no_change_plan(self):
        initial = self.preview()
        result = preview_native_fixture_migration(
            self.fixture_raw(), owner_id=self.owner, target_preimage=initial._candidate_raw,
        )
        self.assertEqual(result.migration_status, "NO_CHANGE")
        self.assertEqual(result.future_operation, "none")
        self.assertEqual(result.rollback_state, "not_required")
        self.assertIsNone(result._rollback_raw)

    def test_different_valid_target_is_blocked_and_captures_exact_preimage(self):
        target = self.different_preimage()
        result = self.preview(target=target)
        self.assertEqual(result.migration_status, "BLOCKED")
        self.assertEqual(result.target_state, "occupied_different")
        self.assertFalse(result.to_dict()["target"]["overwrite_allowed"])
        self.assertEqual(result._rollback_raw, target)
        self.assertEqual(result.rollback_sha256, hashlib.sha256(target).hexdigest())

    def test_invalid_target_preimage_is_refused_not_replaced(self):
        invalid = b"not a store\n"
        with self.assertRaisesRegex(SessionSpineTransferError, "preimage"):
            self.preview(target=invalid)
        self.assertEqual(invalid, b"not a store\n")
        self.assertFalse(self.export_root.exists())

    def test_export_creates_only_new_private_evidence_bundle(self):
        source = self.fixture_raw()
        preview = preview_native_fixture_migration(source, owner_id=self.owner)
        receipt = self.export(preview)
        bundle = receipt.bundle_path

        self.assertEqual(stat.S_IMODE(self.export_root.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(bundle.stat().st_mode), 0o700)
        self.assertEqual({item.name for item in bundle.iterdir()}, {SOURCE_FILE, CANDIDATE_FILE, MANIFEST_FILE})
        for item in bundle.iterdir():
            self.assertEqual(stat.S_IMODE(item.stat().st_mode), 0o600)
        self.assertEqual((bundle / SOURCE_FILE).read_bytes(), source)
        self.assertEqual((bundle / CANDIDATE_FILE).read_bytes(), preview._candidate_raw)
        self.assertFalse(receipt.to_dict()["migration_performed"])
        self.assertFalse(receipt.to_dict()["rollback_performed"])
        self.assertFalse(receipt.to_dict()["safe_to_publish"])

    def test_blocked_export_preserves_exact_rollback_preimage(self):
        target = self.different_preimage()
        receipt = self.export(self.preview(target=target))
        self.assertEqual((receipt.bundle_path / ROLLBACK_FILE).read_bytes(), target)
        verified = verify_migration_export(receipt.bundle_path)
        self.assertEqual(verified.rollback_state, "exact_preimage_captured")
        self.assertEqual(verified.rollback_sha256, hashlib.sha256(target).hexdigest())
        self.assertEqual(verified.migration_status, "BLOCKED")

    def test_export_verifies_after_restart_with_exact_parity(self):
        receipt = self.export()
        verified = verify_migration_export(Path(str(receipt.bundle_path)))
        self.assertEqual(verified.to_dict()["status"], "VERIFIED")
        self.assertTrue(verified.to_dict()["exact_p1_p2_parity"])
        self.assertEqual(verified.candidate_sha256, receipt.candidate_sha256)
        self.assertEqual(verified.file_count, 3)

    def test_export_id_is_run_once_and_does_not_overwrite(self):
        export_id = str(uuid4())
        receipt = self.export(export_id=export_id)
        before = {item.name: item.read_bytes() for item in receipt.bundle_path.iterdir()}
        with self.assertRaisesRegex(SessionSpineTransferError, "already exists"):
            self.export(export_id=export_id)
        after = {item.name: item.read_bytes() for item in receipt.bundle_path.iterdir()}
        self.assertEqual(after, before)

    def test_export_rederives_preview_before_creating_any_files(self):
        forged = replace(self.preview(), candidate_sha256="0" * 64)
        with self.assertRaisesRegex(SessionSpineTransferError, "metadata"):
            self.export(forged)
        self.assertFalse(self.export_root.exists())

    def test_source_candidate_manifest_and_rollback_tampering_fail_verification(self):
        mutations = {
            SOURCE_FILE: lambda raw: raw.replace(b"synthetic", b"tampered", 1),
            CANDIDATE_FILE: lambda raw: raw[:-2] + b"x\n",
            MANIFEST_FILE: lambda raw: raw.replace(b'"export_only":true', b'"export_only":false', 1),
        }
        for filename, mutate in mutations.items():
            with self.subTest(filename=filename):
                receipt = self.export(export_id=str(uuid4()))
                path = receipt.bundle_path / filename
                path.write_bytes(mutate(path.read_bytes()))
                with self.assertRaises(SessionSpineTransferError):
                    verify_migration_export(receipt.bundle_path)

        blocked = self.export(self.preview(target=self.different_preimage()), export_id=str(uuid4()))
        rollback = blocked.bundle_path / ROLLBACK_FILE
        rollback.write_bytes(rollback.read_bytes()[:-2] + b"x\n")
        with self.assertRaises(SessionSpineTransferError):
            verify_migration_export(blocked.bundle_path)

    def test_unexpected_or_missing_bundle_file_fails_closed(self):
        receipt = self.export()
        extra = receipt.bundle_path / "unexpected.txt"
        extra.write_text("no", encoding="utf-8")
        os.chmod(extra, 0o600)
        with self.assertRaisesRegex(SessionSpineTransferError, "unexpected"):
            verify_migration_export(receipt.bundle_path)

        partial = self.export_root / f"{uuid4()}.session-spine-export"
        partial.mkdir(mode=0o700)
        with self.assertRaisesRegex(SessionSpineTransferError, "missing"):
            verify_migration_export(partial)

    def test_relative_and_symlink_export_paths_are_refused(self):
        with self.assertRaisesRegex(SessionSpineTransferError, "absolute"):
            export_migration_preview(
                self.preview(), export_root=Path("relative"), export_id=str(uuid4()), generated_ms=1,
            )
        real = self.root / "real"
        real.mkdir(mode=0o700)
        alias = self.root / "alias"
        alias.symlink_to(real, target_is_directory=True)
        with self.assertRaisesRegex(SessionSpineTransferError, "unsafe"):
            export_migration_preview(
                self.preview(), export_root=alias, export_id=str(uuid4()), generated_ms=1,
            )

    def test_symlink_payload_is_never_followed(self):
        receipt = self.export()
        candidate = receipt.bundle_path / CANDIDATE_FILE
        outside = self.root / "outside"
        outside.write_bytes(candidate.read_bytes())
        candidate.unlink()
        candidate.symlink_to(outside)
        with self.assertRaisesRegex(SessionSpineTransferError, "unsafe"):
            verify_migration_export(receipt.bundle_path)

    def test_manifest_is_canonical_hashed_and_closed(self):
        receipt = self.export()
        raw = (receipt.bundle_path / MANIFEST_FILE).read_bytes()
        manifest = json.loads(raw)
        self.assertEqual(manifest["schema"], EXPORT_SCHEMA)
        self.assertTrue(raw.endswith(b"\n"))
        self.assertFalse(manifest["migration"]["apply_installed"])
        self.assertTrue(manifest["boundaries"]["contains_exact_source_content"])
        self.assertFalse(manifest["boundaries"]["safe_to_publish"])
        self.assertFalse(manifest["boundaries"]["personal_archive_scanned"])
        self.assertFalse(manifest["boundaries"]["store_authority_changed"])

    def test_absent_preimage_rollback_preview_requires_separate_delete_review(self):
        receipt = self.export()
        verified = verify_migration_export(receipt.bundle_path)
        result = preview_export_rollback(receipt.bundle_path, current_target=verified._candidate_raw)
        self.assertEqual(result.status, "READY_FOR_SEPARATE_REVIEW")
        self.assertEqual(result.future_operation, "restore_absence")
        self.assertTrue(result.would_require_delete)
        self.assertFalse(result.to_dict()["rollback_installed"])
        self.assertFalse(result.to_dict()["rollback_performed"])

    def test_exact_preimage_rollback_preview_handles_ready_restored_and_drift(self):
        target = self.different_preimage()
        receipt = self.export(self.preview(target=target))
        verified = verify_migration_export(receipt.bundle_path)

        ready = preview_export_rollback(receipt.bundle_path, current_target=verified._candidate_raw)
        self.assertEqual(ready.status, "READY_FOR_SEPARATE_REVIEW")
        self.assertEqual(ready.future_operation, "restore_exact_preimage")
        restored = preview_export_rollback(receipt.bundle_path, current_target=target)
        self.assertEqual(restored.status, "ALREADY_RESTORED")
        drift = preview_export_rollback(receipt.bundle_path, current_target=target + b"drift")
        self.assertEqual(drift.status, "BLOCKED")
        self.assertEqual(drift.future_operation, "none")

    def test_no_change_export_has_no_rollback_action(self):
        candidate = self.preview()._candidate_raw
        receipt = self.export(self.preview(target=candidate))
        result = preview_export_rollback(receipt.bundle_path, current_target=candidate)
        self.assertEqual(result.status, "NO_CHANGE")
        self.assertEqual(result.future_operation, "none")
        self.assertFalse(result.would_require_delete)

    def test_export_does_not_change_in_memory_source_or_target(self):
        source = self.fixture_raw()
        target = self.different_preimage()
        source_before, target_before = bytes(source), bytes(target)
        receipt = self.export(preview_native_fixture_migration(source, owner_id=self.owner, target_preimage=target))
        verify_migration_export(receipt.bundle_path)
        self.assertEqual(source, source_before)
        self.assertEqual(target, target_before)
