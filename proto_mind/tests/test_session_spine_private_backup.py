"""Private-backup acceptance boundary for Session Spine P2f."""
from __future__ import annotations

from io import BytesIO
import hashlib
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest import mock
from uuid import uuid4

from proto_mind.native_instructions import PreparedLocalInstructions, build_instruction_receipt
from proto_mind.native_turn_lineage import build_turn_reference
from proto_mind.native_work_sessions import WorkSessionStore
from proto_mind.session_spine_private_backup import (
    ALLOWED_PAX_KEYS,
    MAX_APPLEDOUBLE_BYTES,
    SCHEMA,
    SessionSpinePrivateBackupError,
    audit_native_private_backup,
)


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


class SessionSpinePrivateBackupTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="proto-spine-private-backup-")
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.project = self.base / "project"
        self.project.mkdir()
        self.private = self.base / "private"
        self.store = WorkSessionStore(self.private, self.project)
        self.archive = self.base / f"private-name-{uuid4()}.tar.gz"
        self.conversation_id = str(uuid4())
        self.secrets: list[str] = []

    @staticmethod
    def _message(identifier: str, role: str, text: str, **extra) -> dict:
        return {
            "id": identifier,
            "role": role,
            "text": text,
            "raw": "",
            "evidence": None,
            "notices": [],
            "createdAt": 800_000_000,
            "isError": False,
            **extra,
        }

    def _linked_copy(self) -> tuple[bytes, dict[str, bytes]]:
        run_id, user_id, assistant_id = (str(uuid4()) for _ in range(3))
        prompt = f"Private archive prompt {uuid4()}"
        answer = f"Private archive answer {uuid4()}"
        self.secrets.extend((prompt, answer, self.archive.name))
        instruction = build_instruction_receipt(
            provider="codex",
            mode="chat",
            prepared=PreparedLocalInstructions(
                "synthetic local instructions",
                "legacy_cognitive_core_current_projection",
                None,
            ),
            developer_instructions="synthetic P2f fixture",
        )
        with self.store.begin(
            run_id=run_id,
            conversation_id=self.conversation_id,
            text=prompt,
            provider="codex",
            model="synthetic-no-provider-call",
            effort="high",
            mode="chat",
            workspace=None,
            sources=[],
        ) as writer:
            writer.dispatch()
            completed = writer.complete(answer, instruction_receipt=instruction)
        run_name = run_id + ".json"
        run_raw = (self.store.directory / run_name).read_bytes()
        reference = build_turn_reference(
            receipt=completed["turn_receipt"],
            source_message_id=user_id,
            input_text=prompt,
            response=answer,
        )
        messages = [
            self._message(user_id.upper(), "user", prompt),
            self._message(assistant_id.upper(), "assistant", answer, raw=answer, turnReference=reference),
        ]
        history = json.dumps({
            "version": 5,
            "selectedID": self.conversation_id.upper(),
            "conversations": [{
                "id": self.conversation_id.upper(),
                "title": "Private fixture title",
                "createdAt": 800_000_000,
                "updatedAt": 800_000_001,
                "messages": messages,
                "provider": "codex",
                "model": "synthetic-no-provider-call",
            }],
        }, ensure_ascii=False).encode("utf-8")
        return history, {run_name: run_raw}

    @staticmethod
    def _add_member(
        archive: tarfile.TarFile,
        name: str,
        raw: bytes = b"",
        *,
        mode: int = 0o600,
        member_type: bytes = tarfile.REGTYPE,
        linkname: str = "",
        pax_headers: dict[str, str] | None = None,
    ) -> None:
        info = tarfile.TarInfo(name)
        info.mode = mode
        info.type = member_type
        info.linkname = linkname
        info.pax_headers = dict(pax_headers or {})
        info.size = len(raw) if member_type == tarfile.REGTYPE else 0
        archive.addfile(info, BytesIO(raw) if member_type == tarfile.REGTYPE else None)

    def _write_archive(
        self,
        history: bytes | None,
        runs: dict[str, bytes],
        *,
        include_directory: bool = True,
        history_pax: dict[str, str] | None = None,
        extra_members: tuple[dict, ...] = (),
        mode: int = 0o600,
    ) -> str:
        with tarfile.open(self.archive, "w:gz", format=tarfile.PAX_FORMAT) as archive:
            if history is not None:
                self._add_member(archive, "conversations.json", history, pax_headers=history_pax)
            self._add_member(archive, "codex_threads.json", b"{}")
            self._add_member(archive, "preferences.json", b"{}")
            if include_directory:
                self._add_member(
                    archive,
                    "work_sessions",
                    mode=0o700,
                    member_type=tarfile.DIRTYPE,
                )
            self._add_member(archive, "work_sessions/.writer.lock", b"fixture-lock")
            for name, raw in runs.items():
                self._add_member(archive, "work_sessions/" + name, raw)
            for member in extra_members:
                self._add_member(archive, **member)
        self.archive.chmod(mode)
        return _sha256(self.archive.read_bytes())

    def _audit(self, digest: str):
        return audit_native_private_backup(self.archive, expected_archive_sha256=digest)

    def test_exact_private_backup_revalidates_one_linked_turn(self):
        history, runs = self._linked_copy()
        report = self._audit(self._write_archive(history, runs))
        self.assertEqual(report["schema"], SCHEMA)
        self.assertEqual(report["status"], "OK")
        self.assertEqual(report["checks"]["p2e_revalidation_status"], "OK")
        self.assertEqual(report["compatibility"]["coverage"]["compatible_turns"], 1)
        self.assertEqual(report["input"]["work_session_count"], 1)

    def test_report_is_deterministic_content_free_and_does_not_extract_or_write(self):
        history, runs = self._linked_copy()
        digest = self._write_archive(history, runs)
        before_bytes = self.archive.read_bytes()
        before_names = tuple(sorted(path.relative_to(self.base) for path in self.base.rglob("*")))
        first = self._audit(digest)
        second = self._audit(digest)
        after_names = tuple(sorted(path.relative_to(self.base) for path in self.base.rglob("*")))
        self.assertEqual(first, second)
        self.assertEqual(self.archive.read_bytes(), before_bytes)
        self.assertEqual(after_names, before_names)
        rendered = json.dumps(first, ensure_ascii=False)
        for secret in self.secrets:
            self.assertNotIn(secret, rendered)
        self.assertNotIn(str(self.archive), rendered)
        self.assertTrue(first["read_only"])
        self.assertTrue(first["no_write"])
        self.assertTrue(first["no_disk_extraction"])

    def test_digest_relative_path_and_final_symlink_fail_closed(self):
        history, runs = self._linked_copy()
        digest = self._write_archive(history, runs)
        with self.assertRaises(SessionSpinePrivateBackupError):
            audit_native_private_backup(Path(self.archive.name), expected_archive_sha256=digest)
        with self.assertRaises(SessionSpinePrivateBackupError):
            self._audit("0" * 64)
        with self.assertRaises(SessionSpinePrivateBackupError):
            self._audit("invalid")
        alias = self.base / "alias.tar.gz"
        alias.symlink_to(self.archive)
        with self.assertRaises(SessionSpinePrivateBackupError):
            audit_native_private_backup(alias, expected_archive_sha256=digest)
        with mock.patch(
            "proto_mind.session_spine_private_backup.os.read",
            side_effect=OSError("synthetic read failure"),
        ):
            with self.assertRaisesRegex(
                SessionSpinePrivateBackupError,
                "could not be read stably",
            ):
                self._audit(digest)

    def test_missing_history_or_directory_marker_is_refused(self):
        empty = json.dumps({"version": 5, "selectedID": None, "conversations": []}).encode()
        digest = self._write_archive(None, {})
        with self.assertRaises(SessionSpinePrivateBackupError):
            self._audit(digest)
        digest = self._write_archive(empty, {}, include_directory=False)
        with self.assertRaises(SessionSpinePrivateBackupError):
            self._audit(digest)

    def test_duplicate_unknown_and_unsafe_paths_are_refused(self):
        history, _ = self._linked_copy()
        cases = (
            {"name": "conversations.json", "raw": history},
            {"name": "auth.json", "raw": b"credential-shaped member"},
            {"name": "../conversations.json", "raw": history},
            {"name": "/private/conversations.json", "raw": history},
        )
        for member in cases:
            with self.subTest(name=member["name"]):
                digest = self._write_archive(history, {}, extra_members=(member,))
                with self.assertRaises(SessionSpinePrivateBackupError):
                    self._audit(digest)

    def test_links_and_special_members_are_never_followed(self):
        history, _ = self._linked_copy()
        cases = (
            {"name": "work_sessions/" + str(uuid4()) + ".json", "member_type": tarfile.SYMTYPE,
             "linkname": "conversations.json"},
            {"name": "work_sessions/" + str(uuid4()) + ".json", "member_type": tarfile.LNKTYPE,
             "linkname": "conversations.json"},
            {"name": "work_sessions/" + str(uuid4()) + ".json", "member_type": tarfile.FIFOTYPE},
        )
        for member in cases:
            with self.subTest(member_type=member["member_type"]):
                digest = self._write_archive(history, {}, extra_members=(member,))
                with self.assertRaises(SessionSpinePrivateBackupError):
                    self._audit(digest)

    def test_known_macos_appledouble_and_pax_metadata_are_ignored(self):
        history, runs = self._linked_copy()
        run_name = next(iter(runs))
        known_pax = {key: "fixture" for key in ALLOWED_PAX_KEYS}
        sidecars = (
            {"name": "._conversations.json", "raw": b"appledouble"},
            {"name": "._work_sessions", "raw": b"appledouble"},
            {"name": "work_sessions/._" + run_name, "raw": b"appledouble"},
            {"name": "work_sessions/._.writer.lock", "raw": b"appledouble"},
        )
        digest = self._write_archive(history, runs, history_pax=known_pax, extra_members=sidecars)
        report = self._audit(digest)
        self.assertEqual(report["status"], "OK")
        self.assertEqual(report["input"]["ignored_member_count"], 7)
        self.assertTrue(report["checks"]["macos_appledouble_metadata_ignored"])

    def test_oversized_appledouble_and_unknown_pax_are_refused(self):
        history, _ = self._linked_copy()
        digest = self._write_archive(
            history,
            {},
            extra_members=({"name": "._conversations.json", "raw": b"x" * (MAX_APPLEDOUBLE_BYTES + 1)},),
        )
        with self.assertRaises(SessionSpinePrivateBackupError):
            self._audit(digest)
        digest = self._write_archive(history, {}, history_pax={"comment": "not allowlisted"})
        with self.assertRaises(SessionSpinePrivateBackupError):
            self._audit(digest)
        digest = self._write_archive(history, {}, history_pax={"mtime": "x" * 4097})
        with self.assertRaises(SessionSpinePrivateBackupError):
            self._audit(digest)

    def test_non_owner_only_archive_mode_is_visible_but_not_rewritten(self):
        history, runs = self._linked_copy()
        digest = self._write_archive(history, runs, mode=0o644)
        before_mode = self.archive.stat().st_mode & 0o777
        report = self._audit(digest)
        self.assertEqual(report["status"], "WARN")
        self.assertFalse(report["input"]["archive_owner_only"])
        self.assertEqual(report["findings"][0]["category"], "archive_file_mode")
        self.assertEqual(self.archive.stat().st_mode & 0o777, before_mode)

    def test_empty_complete_backup_warns_without_inventing_lineage(self):
        history = json.dumps({"version": 5, "selectedID": None, "conversations": []}).encode()
        report = self._audit(self._write_archive(history, {}))
        self.assertEqual(report["status"], "WARN")
        self.assertEqual(report["checks"]["p2e_revalidation_status"], "WARN")
        self.assertEqual(report["compatibility"]["coverage"]["compatible_turns"], 0)

    def test_invalid_copied_run_remains_an_error_without_repair(self):
        history, runs = self._linked_copy()
        run_name = next(iter(runs))
        report = self._audit(self._write_archive(history, {run_name: b"{}"}))
        self.assertEqual(report["status"], "ERROR")
        self.assertEqual(report["checks"]["p2e_revalidation_status"], "ERROR")
        self.assertEqual(report["compatibility"]["coverage"]["invalid_or_incompatible_runs"], 1)
        self.assertFalse(report["boundaries"]["repair_performed"])

    def test_report_explicitly_denies_live_authority_and_external_actions(self):
        history, runs = self._linked_copy()
        report = self._audit(self._write_archive(history, runs))
        self.assertTrue(report["authority"]["backup_member_set_closed"])
        self.assertFalse(report["authority"]["live_source_completeness_verified"])
        self.assertFalse(report["authority"]["operator_authorization_verified_by_code"])
        self.assertFalse(report["authority"]["ready_for_authoritative_writer"])
        self.assertFalse(report["boundaries"]["live_native_state_opened"])
        self.assertFalse(report["boundaries"]["model_call_performed"])
        self.assertFalse(report["boundaries"]["provider_call_performed"])
        self.assertFalse(report["boundaries"]["permission_changed"])
        self.assertFalse(report["boundaries"]["production_caller_installed"])
        material = {key: value for key, value in report.items() if key != "audit_hash"}
        self.assertEqual(report["audit_hash"], _sha256(json.dumps(
            material,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")))


if __name__ == "__main__":
    unittest.main()
