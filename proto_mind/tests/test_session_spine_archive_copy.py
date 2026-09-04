"""Archive-wide copied-history compatibility evidence for Session Spine P2e."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock
from uuid import uuid4

from proto_mind.native_instructions import PreparedLocalInstructions, build_instruction_receipt
from proto_mind.native_session_spine import project_native_turn
from proto_mind.native_turn_lineage import build_turn_reference
from proto_mind.native_work_sessions import WorkSessionError, WorkSessionStore, inspect_work_session_copy
from proto_mind.session_spine_archive_copy import (
    SCHEMA,
    SessionSpineArchiveCopyError,
    audit_native_archive_copy,
)


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


class SessionSpineArchiveCopyTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="proto-spine-archive-copy-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / "project"
        self.root.mkdir()
        self.state = Path(temporary.name) / "private"
        self.store = WorkSessionStore(self.state, self.root)
        self.conversation = str(uuid4())
        self.messages: list[dict] = []
        self.run_raws: dict[str, bytes] = {}
        self.secrets: list[str] = []

    @staticmethod
    def message(identifier: str, role: str, text: str, **extra) -> dict:
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

    def add_turn(self, ordinal: int, *, linked: bool = True) -> tuple[str, str, str]:
        run_id, user_id, assistant_id = (str(uuid4()) for _ in range(3))
        prompt = f"Private copied prompt {ordinal} {uuid4()}"
        answer = f"Private copied answer {ordinal} {uuid4()}"
        self.secrets.extend((prompt, answer))
        instruction = build_instruction_receipt(
            provider="codex",
            mode="chat",
            prepared=PreparedLocalInstructions(
                "synthetic local instructions",
                "legacy_cognitive_core_current_projection",
                None,
            ),
            developer_instructions="synthetic archive-copy contract",
        )
        with self.store.begin(
            run_id=run_id,
            conversation_id=self.conversation,
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
        name = run_id + ".json"
        self.run_raws[name] = (self.store.directory / name).read_bytes()
        reference = build_turn_reference(
            receipt=completed["turn_receipt"],
            source_message_id=user_id,
            input_text=prompt,
            response=answer,
        )
        self.messages.append(self.message(user_id, "user", prompt))
        extra = {"raw": answer}
        if linked:
            extra["turnReference"] = reference
        self.messages.append(self.message(assistant_id, "assistant", answer, **extra))
        return run_id, user_id, assistant_id

    def history(self, *, version: int = 5, messages: list[dict] | None = None) -> bytes:
        conversation = {
            "id": self.conversation,
            "title": "Private title not emitted by audit",
            "createdAt": 800_000_000,
            "updatedAt": 800_000_001,
            "messages": self.messages if messages is None else messages,
            "provider": "codex",
            "model": "synthetic-no-provider-call",
        }
        return json.dumps(
            {"version": version, "selectedID": self.conversation, "conversations": [conversation]},
            ensure_ascii=False,
        ).encode("utf-8")

    def manifest(self, raws: dict[str, bytes] | None = None) -> tuple[tuple[str, str], ...]:
        values = self.run_raws if raws is None else raws
        return tuple(sorted((name, _sha256(raw)) for name, raw in values.items()))

    def audit(self, history: bytes | None = None, raws: dict[str, bytes] | None = None):
        history = self.history() if history is None else history
        raws = self.run_raws if raws is None else raws
        return audit_native_archive_copy(
            history,
            raws,
            expected_history_sha256=_sha256(history),
            expected_work_session_manifest=self.manifest(raws),
        )

    def test_complete_copy_revalidates_two_exact_turns_through_p1(self):
        first_run, _, _ = self.add_turn(1)
        self.add_turn(2)
        report = self.audit()
        self.assertEqual(report["schema"], SCHEMA)
        self.assertEqual(report["status"], "OK")
        self.assertEqual(report["coverage"]["compatible_turns"], 2)
        self.assertEqual(report["coverage"]["linked_compatible_runs"], 2)
        self.assertEqual(report["checks"]["p1_projection_revalidated_count"], 2)

        first = report["turn_findings"][0]
        name = first_run + ".json"
        run = inspect_work_session_copy(self.run_raws[name], name)
        direct = project_native_turn(
            conversation_id=self.conversation,
            user_message=self.messages[0],
            assistant_message=self.messages[1],
            work_session=run,
        )
        self.assertEqual(first["projection"]["event_count"], len(direct.events))
        self.assertEqual(first["projection"]["surface_fingerprint"], direct.surface.fingerprint)

    def test_mixed_legacy_and_orphaned_copy_remains_visible_as_warn(self):
        self.add_turn(1)
        orphan_run, _, _ = self.add_turn(2, linked=False)
        legacy_user, legacy_assistant = str(uuid4()), str(uuid4())
        self.messages.extend([
            self.message(legacy_user, "user", "Legacy input"),
            self.message(legacy_assistant, "assistant", "Legacy answer", raw="Legacy answer"),
        ])
        report = self.audit()
        self.assertEqual(report["status"], "WARN")
        self.assertEqual(report["coverage"]["legacy_unlinked_turns"], 2)
        self.assertEqual(report["coverage"]["orphaned_lineage_runs"], 1)
        orphan = next(row for row in report["run_findings"] if row["run_id"] == orphan_run)
        self.assertEqual(orphan["category"], "orphaned_lineage")

    def test_missing_referenced_run_is_error_and_never_uses_another_run(self):
        missing_run, _, _ = self.add_turn(1)
        self.add_turn(2, linked=False)
        raws = {name: raw for name, raw in self.run_raws.items() if name != missing_run + ".json"}
        report = self.audit(raws=raws)
        self.assertEqual(report["status"], "ERROR")
        self.assertEqual(report["turn_findings"][0]["category"], "missing_run")
        self.assertFalse(report["checks"]["latest_or_adjacent_run_fallback"])

    def test_changed_message_fails_exact_lineage(self):
        self.add_turn(1)
        changed = deepcopy(self.messages)
        changed[0]["text"] = "Changed copied prompt"
        report = self.audit(history=self.history(messages=changed))
        self.assertEqual(report["status"], "ERROR")
        self.assertEqual(report["turn_findings"][0]["category"], "lineage_mismatch")

    def test_tampered_reference_hash_is_reported_as_invalid(self):
        self.add_turn(1)
        changed = deepcopy(self.messages)
        changed[1]["turnReference"]["reference_hash"] = "0" * 64
        report = self.audit(history=self.history(messages=changed))
        self.assertEqual(report["status"], "ERROR")
        self.assertEqual(report["turn_findings"][0]["category"], "invalid_reference")
        self.assertEqual(report["coverage"]["compatible_turns"], 0)

    def test_invalid_referenced_run_is_reported_without_repair(self):
        run_id, _, _ = self.add_turn(1)
        raws = dict(self.run_raws)
        raws[run_id + ".json"] = b"{}"
        report = self.audit(raws=raws)
        self.assertEqual(report["status"], "ERROR")
        self.assertEqual(report["turn_findings"][0]["category"], "invalid_run")
        self.assertEqual(report["run_findings"][0]["category"], "invalid_record")

    def test_duplicate_source_and_run_reference_is_not_accepted_twice(self):
        self.add_turn(1)
        duplicate = deepcopy(self.messages[1])
        duplicate["id"] = str(uuid4())
        self.messages.append(duplicate)
        report = self.audit()
        self.assertEqual(report["status"], "ERROR")
        self.assertEqual(report["turn_findings"][1]["category"], "duplicate_lineage")
        self.assertEqual(report["run_findings"][0]["category"], "referenced_ambiguous")

    def test_manifest_mismatch_unsorted_rows_and_wrong_history_digest_fail_closed(self):
        self.add_turn(1)
        self.add_turn(2)
        history = self.history()
        valid = self.manifest()
        cases = (
            ("history", "0" * 64, valid),
            ("record", _sha256(history), ((valid[0][0], "0" * 64), valid[1])),
            ("order", _sha256(history), tuple(reversed(valid))),
            ("missing", _sha256(history), valid[:1]),
        )
        for label, history_digest, manifest in cases:
            with self.subTest(label=label), self.assertRaises(SessionSpineArchiveCopyError):
                audit_native_archive_copy(
                    history,
                    self.run_raws,
                    expected_history_sha256=history_digest,
                    expected_work_session_manifest=manifest,
                )

    def test_malformed_unsupported_and_duplicate_field_history_fail_closed(self):
        duplicate = (
            b'{"version":5,"version":5,"selectedID":null,"conversations":[]}'
        )
        unsupported = json.dumps({"version": 6, "selectedID": None, "conversations": []}).encode()
        for raw in (b"not-json", duplicate, unsupported):
            with self.subTest(raw=raw), self.assertRaises(SessionSpineArchiveCopyError):
                self.audit(history=raw, raws={})

    def test_duplicate_message_identity_is_a_content_free_error(self):
        self.add_turn(1)
        changed = deepcopy(self.messages)
        changed[1]["id"] = changed[0]["id"]
        report = self.audit(history=self.history(messages=changed))
        self.assertEqual(report["status"], "ERROR")
        self.assertEqual(report["archive_issues"][0]["category"], "duplicate_message_id")

    def test_empty_valid_copy_warns_without_inventing_lineage(self):
        history = json.dumps({"version": 5, "selectedID": None, "conversations": []}).encode()
        report = self.audit(history=history, raws={})
        self.assertEqual(report["status"], "WARN")
        self.assertEqual(report["notices"][0]["category"], "no_linked_turns")
        self.assertEqual(report["coverage"]["compatible_turns"], 0)

    def test_all_native_history_versions_are_accepted_without_migration(self):
        for version in range(1, 6):
            history = json.dumps({"version": version, "selectedID": None, "conversations": []}).encode()
            with self.subTest(version=version):
                report = self.audit(history=history, raws={})
                self.assertEqual(report["inputs"]["history"]["version"], version)
                self.assertEqual(report["checks"]["native_history_versions_accepted"], [1, 2, 3, 4, 5])
                self.assertFalse(report["boundaries"]["migration_installed"])

    def test_swift_uppercase_archive_ids_normalize_without_weakening_lineage(self):
        self.add_turn(1)
        changed = deepcopy(self.messages)
        changed[0]["id"] = changed[0]["id"].upper()
        changed[1]["id"] = changed[1]["id"].upper()
        history = json.loads(self.history(messages=changed))
        history["selectedID"] = history["selectedID"].upper()
        history["conversations"][0]["id"] = history["conversations"][0]["id"].upper()
        raw = json.dumps(history, ensure_ascii=False).encode("utf-8")
        report = self.audit(history=raw)
        self.assertEqual(report["status"], "OK")
        self.assertEqual(report["coverage"]["compatible_turns"], 1)
        self.assertEqual(report["turn_findings"][0]["conversation_id"], self.conversation)
        self.assertEqual(report["turn_findings"][0]["message_id"], changed[1]["id"].lower())

    def test_report_is_deterministic_content_free_and_has_no_authority(self):
        self.add_turn(1)
        history = self.history()
        before_history = bytes(history)
        before_runs = deepcopy(self.run_raws)
        with mock.patch("builtins.open", side_effect=AssertionError("audit opened a path")):
            first = self.audit(history=history)
            second = self.audit(history=history)
        self.assertEqual(first, second)
        self.assertEqual(history, before_history)
        self.assertEqual(self.run_raws, before_runs)
        rendered = json.dumps(first, ensure_ascii=False)
        for secret in self.secrets:
            self.assertNotIn(secret, rendered)
        self.assertTrue(first["read_only"])
        self.assertTrue(first["no_file_access"])
        self.assertTrue(first["report_content_free"])
        self.assertFalse(first["inputs"]["source_archive_completeness_verified"])
        self.assertFalse(first["boundaries"]["authoritative_writer_installed"])
        self.assertFalse(first["authority"]["ready_for_authoritative_writer"])
        material = {key: value for key, value in first.items() if key != "audit_hash"}
        self.assertEqual(first["audit_hash"], _sha256(json.dumps(
            material,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")))

    def test_noncanonical_or_mutable_work_session_copy_is_refused(self):
        run_id, _, _ = self.add_turn(1)
        name = run_id + ".json"
        parsed = json.loads(self.run_raws[name])
        pretty = json.dumps(parsed, indent=2).encode()
        with self.assertRaisesRegex(WorkSessionError, "canonical"):
            inspect_work_session_copy(pretty, name)
        with self.assertRaises(WorkSessionError):
            inspect_work_session_copy(b"\xff", name)
        with self.assertRaises(SessionSpineArchiveCopyError):
            audit_native_archive_copy(
                self.history(),
                {name: bytearray(self.run_raws[name])},
                expected_history_sha256=_sha256(self.history()),
                expected_work_session_manifest=((name, _sha256(self.run_raws[name])),),
            )


if __name__ == "__main__":
    unittest.main()
