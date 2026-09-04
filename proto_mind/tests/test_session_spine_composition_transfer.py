"""Private multi-turn evidence export and parity dossier checks for P2d."""
from copy import deepcopy
from dataclasses import replace
import hashlib
import inspect
import json
import os
from pathlib import Path
import stat
from tempfile import TemporaryDirectory
from unittest import TestCase, mock
from uuid import uuid4

from proto_mind.native_progress import display_text
from proto_mind.session_spine_composition import compose_native_fixtures
from proto_mind.session_spine_composition_transfer import (
    BUNDLE_SUFFIX,
    CANDIDATE_FILE,
    DOSSIER_FILE,
    DOSSIER_SCHEMA,
    EXPORT_SCHEMA,
    MANIFEST_FILE,
    SessionSpineCompositionTransferError,
    export_composition_preview,
    verify_composition_export,
)
from proto_mind.session_spine_transfer import FIXTURE_SCHEMA, SessionSpineTransferError


def _canonical_line(value):
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8") + b"\n"


def _sha256(raw):
    return hashlib.sha256(raw).hexdigest()


class SessionSpineCompositionTransferTests(TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve()
        self.export_root = self.root / "exports"
        self.conversation = str(uuid4())
        self.owner = "composition.export"
        self.prompts = ("Первый закрытый fixture.", "Второй закрытый fixture.")
        self.answers = ("Первый точный ответ.", "Второй точный ответ.")

    def tearDown(self):
        self.temporary.cleanup()

    def fixture(self, ordinal, *, interrupted=False):
        created = f"2026-09-04T10:0{ordinal * 2}:00.000000Z"
        finished = f"2026-09-04T10:0{ordinal * 2 + 1}:00.000000Z"
        prompt = self.prompts[ordinal]
        answer = self.answers[ordinal]
        run = {
            "schema": "proto_mind.native_work_session.v1",
            "id": str(uuid4()),
            "conversation_id": self.conversation,
            "project_root": "/synthetic/copied-history",
            "workspace": {"path": "/synthetic/copied-history", "device": 7, "inode": 9},
            "created_at": created,
            "updated_at": finished,
            "finished_at": finished,
            "status": "interrupted" if interrupted else "completed",
            "provider": "codex",
            "requested_model": "gpt-5.6-sol",
            "requested_effort": "high",
            "access_mode": "chat",
            "input_preview": display_text(prompt, 800),
            "input_chars": len(prompt),
            "input_sha256": _sha256(prompt.encode()),
            "answer_preview": "" if interrupted else display_text(answer, 1600),
            "sources": [],
            "parent_run_id": None,
            "tools": [],
            "work_log": {},
            "network_access_performed": False,
            "computer_use_performed": False,
            "screen_access_performed": False,
            "verification": "not_assessed",
            "acceptance": "not_recorded",
            "display_status": "unknown" if interrupted else "completed",
            "fingerprint": _sha256(f"composition-export-run-{ordinal}".encode()),
            "automatic_resume": False,
        }
        if interrupted:
            run["dispatched_at"] = finished
        return {
            "schema": FIXTURE_SCHEMA,
            "conversation_id": self.conversation,
            "user_message": {
                "id": str(uuid4()),
                "role": "user",
                "text": prompt,
                "isError": False,
                "operatorInput": False,
            },
            "assistant_message": None if interrupted else {
                "id": str(uuid4()),
                "role": "assistant",
                "text": answer,
                "raw": answer,
                "isError": False,
            },
            "work_session": run,
        }

    def fixture_pair(self, *, interrupted_second=False):
        fixtures = (
            _canonical_line(self.fixture(0)),
            _canonical_line(self.fixture(1, interrupted=interrupted_second)),
        )
        return fixtures, tuple(_sha256(raw) for raw in fixtures)

    def preview(self, *, interrupted_second=False):
        fixtures, order = self.fixture_pair(interrupted_second=interrupted_second)
        return compose_native_fixtures(
            fixtures,
            expected_order=order,
            expected_conversation_id=self.conversation,
            owner_id=self.owner,
        )

    def export(self, preview=None, export_id=None):
        return export_composition_preview(
            preview or self.preview(),
            export_root=self.export_root,
            export_id=export_id or str(uuid4()),
            generated_ms=1_788_531_200_000,
        )

    def test_export_creates_private_closed_bundle_with_exact_payloads(self):
        preview = self.preview()
        receipt = self.export(preview)
        expected = {
            "source-000.native-session.json",
            "source-001.native-session.json",
            CANDIDATE_FILE,
            DOSSIER_FILE,
            MANIFEST_FILE,
        }
        self.assertEqual(stat.S_IMODE(self.export_root.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(receipt.bundle_path.stat().st_mode), 0o700)
        self.assertEqual({path.name for path in receipt.bundle_path.iterdir()}, expected)
        self.assertTrue(receipt.bundle_path.name.endswith(BUNDLE_SUFFIX))
        for path in receipt.bundle_path.iterdir():
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        for ordinal, raw in enumerate(preview._fixture_raws):
            self.assertEqual(
                (receipt.bundle_path / f"source-{ordinal:03d}.native-session.json").read_bytes(),
                raw,
            )
        self.assertEqual((receipt.bundle_path / CANDIDATE_FILE).read_bytes(), preview._candidate_raw)
        self.assertEqual(receipt.source_count, 2)
        self.assertEqual(receipt.file_count, 5)

    def test_manifest_is_written_last_and_is_canonical_self_hashed(self):
        names = []
        from proto_mind import session_spine_composition_transfer as module

        original = module._write_new

        def recording_write(directory, name, payload, *, limit):
            names.append(name)
            return original(directory, name, payload, limit=limit)

        with mock.patch.object(module, "_write_new", side_effect=recording_write):
            receipt = self.export()
        self.assertEqual(names[-1], MANIFEST_FILE)
        raw = (receipt.bundle_path / MANIFEST_FILE).read_bytes()
        manifest = json.loads(raw)
        self.assertEqual(raw, _canonical_line(manifest))
        self.assertEqual(manifest["schema"], EXPORT_SCHEMA)
        digest = manifest.pop("manifest_hash")
        canonical = json.dumps(
            manifest,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        self.assertEqual(digest, _sha256(canonical))
        self.assertFalse(manifest["boundaries"]["safe_to_publish"])
        self.assertFalse(manifest["boundaries"]["store_write_performed"])

    def test_dossier_is_content_free_closed_and_denies_authority(self):
        receipt = self.export()
        raw = (receipt.bundle_path / DOSSIER_FILE).read_bytes()
        dossier = json.loads(raw)
        rendered = raw.decode()
        self.assertEqual(raw, _canonical_line(dossier))
        self.assertEqual(dossier["schema"], DOSSIER_SCHEMA)
        self.assertNotIn(self.prompts[0], rendered)
        self.assertNotIn(self.answers[1], rendered)
        self.assertEqual(dossier["ordering"]["source_files"], [
            "source-000.native-session.json",
            "source-001.native-session.json",
        ])
        self.assertTrue(dossier["checks"]["p1_revalidated"])
        self.assertTrue(dossier["composition"]["full_candidate_replay"])
        self.assertFalse(dossier["boundaries"]["personal_archive_scanned"])
        self.assertFalse(dossier["boundaries"]["apply_installed"])
        self.assertFalse(dossier["boundaries"]["restore_installed"])
        self.assertFalse(dossier["boundaries"]["delete_installed"])
        self.assertFalse(dossier["boundaries"]["compaction_installed"])

    def test_verifier_rebuilds_exact_p1_p2c_p2a_parity(self):
        preview = self.preview()
        receipt = self.export(preview)
        verified = verify_composition_export(Path(str(receipt.bundle_path)))
        report = verified.to_dict()
        self.assertEqual(report["status"], "VERIFIED")
        self.assertTrue(report["read_only"])
        self.assertTrue(report["no_write"])
        self.assertTrue(report["exact_p1_p2c_p2a_parity"])
        self.assertTrue(report["dossier_parity"])
        self.assertEqual(verified._source_raws, preview._fixture_raws)
        self.assertEqual(verified._candidate_raw, preview._candidate_raw)
        self.assertEqual(verified.candidate_sha256, preview.candidate_sha256)
        self.assertEqual(verified.surface_fingerprint, preview.surface.fingerprint)

    def test_export_rederives_preview_before_creating_root(self):
        preview = self.preview()
        forged = replace(preview, candidate_sha256="0" * 64)
        with self.assertRaisesRegex(SessionSpineCompositionTransferError, "metadata"):
            self.export(forged)
        self.assertFalse(self.export_root.exists())

    def test_export_id_is_run_once_without_overwrite(self):
        export_id = str(uuid4())
        receipt = self.export(export_id=export_id)
        before = {path.name: path.read_bytes() for path in receipt.bundle_path.iterdir()}
        with self.assertRaisesRegex(SessionSpineCompositionTransferError, "already exists"):
            self.export(export_id=export_id)
        after = {path.name: path.read_bytes() for path in receipt.bundle_path.iterdir()}
        self.assertEqual(after, before)

    def test_source_candidate_dossier_and_manifest_tampering_fail_closed(self):
        names = [
            "source-000.native-session.json",
            CANDIDATE_FILE,
            DOSSIER_FILE,
            MANIFEST_FILE,
        ]
        for name in names:
            with self.subTest(name=name):
                receipt = self.export(export_id=str(uuid4()))
                path = receipt.bundle_path / name
                raw = path.read_bytes()
                path.write_bytes(raw[:-2] + b"x\n")
                with self.assertRaises(SessionSpineCompositionTransferError):
                    verify_composition_export(receipt.bundle_path)

    def test_source_order_swap_is_refused_not_sorted(self):
        receipt = self.export()
        first = receipt.bundle_path / "source-000.native-session.json"
        second = receipt.bundle_path / "source-001.native-session.json"
        temporary = receipt.bundle_path / "temporary"
        first.rename(temporary)
        second.rename(first)
        temporary.rename(second)
        with self.assertRaisesRegex(SessionSpineCompositionTransferError, "source 0"):
            verify_composition_export(receipt.bundle_path)

    def test_missing_or_extra_file_is_refused(self):
        receipt = self.export()
        extra = receipt.bundle_path / "unexpected.txt"
        extra.write_text("not allowed", encoding="utf-8")
        os.chmod(extra, 0o600)
        with self.assertRaisesRegex(SessionSpineCompositionTransferError, "unexpected"):
            verify_composition_export(receipt.bundle_path)

        partial = self.export_root / f"{uuid4()}{BUNDLE_SUFFIX}"
        partial.mkdir(mode=0o700)
        with self.assertRaisesRegex(SessionSpineCompositionTransferError, "missing"):
            verify_composition_export(partial)

    def test_symlink_payload_is_never_followed(self):
        receipt = self.export()
        candidate = receipt.bundle_path / CANDIDATE_FILE
        outside = self.root / "outside"
        outside.write_bytes(candidate.read_bytes())
        candidate.unlink()
        candidate.symlink_to(outside)
        with self.assertRaisesRegex(SessionSpineCompositionTransferError, "unsafe"):
            verify_composition_export(receipt.bundle_path)

    def test_relative_symlink_and_world_readable_directories_are_refused(self):
        with self.assertRaisesRegex(SessionSpineCompositionTransferError, "absolute"):
            export_composition_preview(
                self.preview(),
                export_root=Path("relative"),
                export_id=str(uuid4()),
                generated_ms=1,
            )
        real = self.root / "real"
        real.mkdir(mode=0o700)
        alias = self.root / "alias"
        alias.symlink_to(real, target_is_directory=True)
        with self.assertRaisesRegex(SessionSpineCompositionTransferError, "unsafe"):
            export_composition_preview(
                self.preview(),
                export_root=alias,
                export_id=str(uuid4()),
                generated_ms=1,
            )

        receipt = self.export()
        os.chmod(receipt.bundle_path, 0o755)
        try:
            with self.assertRaisesRegex(SessionSpineCompositionTransferError, "private"):
                verify_composition_export(receipt.bundle_path)
        finally:
            os.chmod(receipt.bundle_path, 0o700)

    def test_world_readable_payload_is_refused(self):
        receipt = self.export()
        dossier = receipt.bundle_path / DOSSIER_FILE
        os.chmod(dossier, 0o644)
        with self.assertRaisesRegex(SessionSpineCompositionTransferError, "unsafe"):
            verify_composition_export(receipt.bundle_path)

    def test_partial_write_remains_visible_without_manifest_or_retry(self):
        from proto_mind import session_spine_composition_transfer as module

        original = module._write_new

        def interrupted_write(directory, name, payload, *, limit):
            if name == DOSSIER_FILE:
                raise SessionSpineTransferError("synthetic interrupted write")
            return original(directory, name, payload, limit=limit)

        export_id = str(uuid4())
        with mock.patch.object(module, "_write_new", side_effect=interrupted_write):
            with self.assertRaisesRegex(SessionSpineCompositionTransferError, "interrupted"):
                self.export(export_id=export_id)
        bundle = self.export_root / f"{export_id}{BUNDLE_SUFFIX}"
        self.assertTrue(bundle.is_dir())
        self.assertFalse((bundle / MANIFEST_FILE).exists())
        self.assertEqual({path.name for path in bundle.iterdir()}, {
            "source-000.native-session.json",
            "source-001.native-session.json",
            CANDIDATE_FILE,
        })
        with self.assertRaisesRegex(SessionSpineCompositionTransferError, "missing"):
            verify_composition_export(bundle)

    def test_invalid_identifier_timestamp_and_metadata_bound_fail_before_write(self):
        preview = self.preview()
        invalid = (("not-a-uuid", 1), (str(uuid4()), -1))
        for export_id, generated_ms in invalid:
            with self.subTest(export_id=export_id, generated_ms=generated_ms):
                with self.assertRaises(SessionSpineCompositionTransferError):
                    export_composition_preview(
                        preview,
                        export_root=self.export_root,
                        export_id=export_id,
                        generated_ms=generated_ms,
                    )
        self.assertFalse(self.export_root.exists())

        from proto_mind import session_spine_composition_transfer as module

        with mock.patch.object(module, "MAX_DOSSIER_BYTES", 1):
            with self.assertRaisesRegex(SessionSpineCompositionTransferError, "metadata"):
                self.export(preview)
        self.assertFalse(self.export_root.exists())

    def test_interrupted_turn_stays_unknown_without_success_inference(self):
        preview = self.preview(interrupted_second=True)
        receipt = self.export(preview)
        dossier = json.loads((receipt.bundle_path / DOSSIER_FILE).read_bytes())
        verified = verify_composition_export(receipt.bundle_path)
        self.assertEqual(dossier["turns"][1]["source"]["display_status"], "unknown")
        self.assertIsNone(dossier["turns"][1]["source"]["assistant_message_seq"])
        self.assertFalse(dossier["composition"]["task_success_inferred"])
        self.assertEqual(verified._candidate_raw, preview._candidate_raw)

    def test_export_and_verification_do_not_mutate_preview_or_bundle(self):
        preview = self.preview()
        before_preview = deepcopy(preview)
        receipt = self.export(preview)
        before = {path.name: _sha256(path.read_bytes()) for path in receipt.bundle_path.iterdir()}
        verify_composition_export(receipt.bundle_path)
        after = {path.name: _sha256(path.read_bytes()) for path in receipt.bundle_path.iterdir()}
        self.assertEqual(preview, before_preview)
        self.assertEqual(after, before)

    def test_public_contract_has_no_default_path_or_lifecycle_authority(self):
        from proto_mind import session_spine_composition_transfer as module

        export_signature = inspect.signature(export_composition_preview)
        verify_signature = inspect.signature(verify_composition_export)
        self.assertEqual(export_signature.parameters["export_root"].default, inspect.Parameter.empty)
        self.assertEqual(verify_signature.parameters["bundle_path"].default, inspect.Parameter.empty)
        report = self.export().to_dict()
        self.assertFalse(report["personal_archive_scanned"])
        self.assertFalse(report["ordering_inferred"])
        self.assertFalse(report["store_write_performed"])
        self.assertFalse(report["store_authority_changed"])
        self.assertFalse(report["safe_to_publish"])
        for name in ("apply", "restore", "delete", "compact", "scan_archive"):
            self.assertFalse(hasattr(module, name))
