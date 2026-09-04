from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest import mock
from uuid import uuid4

from proto_mind.native_instructions import PreparedLocalInstructions, build_instruction_receipt
from proto_mind.native_review import review_preview
from proto_mind.native_turn_lineage import build_turn_reference
from proto_mind.native_work_sessions import WorkSessionStore
from proto_mind.session_spine import SessionEvent
from proto_mind.session_spine_handshake import (
    APPLY_SCHEMA,
    HANDSHAKE_SCHEMA,
    OWNER_SCHEMA,
    RECOVERY_SCHEMA,
    SessionSpineHandshakeError,
    apply_native_turn_handshake,
    build_native_owner_identity,
    inspect_native_turn_handshake,
    prepare_native_turn_handshake,
    validate_native_owner_identity,
    validate_native_turn_handshake,
)
from proto_mind.session_spine_store import SessionSpineStore, build_store_image


class SessionSpineHandshakeTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory(prefix="proto-spine-handshake-")
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name).resolve()
        self.project = self.base / "project"
        self.project.mkdir()
        self.native_state = self.base / "native-state"
        self.work_store = WorkSessionStore(self.native_state, self.project)
        self.spine_root = self.base / "spine"
        self.spine_store = SessionSpineStore(self.spine_root)
        self.conversation_id = str(uuid4())
        self.run_id = str(uuid4())
        self.user_id = str(uuid4())
        self.assistant_id = str(uuid4())
        self.installation_id = str(uuid4())
        self.owner = build_native_owner_identity(self.installation_id)
        self.prompt = f"Exact private handshake prompt {uuid4()}"
        self.answer = f"Exact private handshake answer {uuid4()}"
        self.user = self.message(self.user_id, "user", self.prompt)
        self.work_session = self.completed_work_session()
        self.reference = build_turn_reference(
            receipt=self.work_session["turn_receipt"],
            source_message_id=self.user_id,
            input_text=self.prompt,
            response=self.answer,
        )
        self.assistant = self.message(
            self.assistant_id,
            "assistant",
            self.answer,
            raw=self.answer,
            turnReference=self.reference,
        )
        self.history_raw = self.history()
        self.work_name = self.run_id + ".json"
        self.work_path = self.work_store.directory / self.work_name
        self.work_raw = self.work_path.read_bytes()

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
            "operatorInput": False,
            **extra,
        }

    def completed_work_session(self) -> dict:
        instruction = build_instruction_receipt(
            provider="codex",
            mode="chat",
            prepared=PreparedLocalInstructions(
                "synthetic local instructions",
                "legacy_cognitive_core_current_projection",
                None,
            ),
            developer_instructions="synthetic P2h handshake contract",
        )
        timestamps = [
            "2026-09-04T10:00:00.000000Z",
            "2026-09-04T10:00:00.100000Z",
            "2026-09-04T10:00:01.000000Z",
            "2026-09-04T10:00:01.100000Z",
            "2026-09-04T10:01:00.000000Z",
            "2026-09-04T10:01:00.100000Z",
        ]
        with mock.patch("proto_mind.native_work_sessions.timestamp", side_effect=timestamps):
            with self.work_store.begin(
                run_id=self.run_id,
                conversation_id=self.conversation_id,
                text=self.prompt,
                provider="codex",
                model="synthetic-no-provider-call",
                effort="high",
                mode="chat",
                workspace=None,
                sources=[],
            ) as writer:
                writer.dispatch()
                return writer.complete(self.answer, instruction_receipt=instruction)

    def history(
        self,
        *,
        include_assistant: bool = True,
        assistant: dict | None = None,
        messages: list[dict] | None = None,
    ) -> bytes:
        rows = [self.user]
        if include_assistant:
            rows.append(self.assistant if assistant is None else assistant)
        if messages:
            rows.extend(messages)
        return json.dumps(
            {
                "version": 5,
                "selectedID": self.conversation_id,
                "conversations": [{
                    "id": self.conversation_id,
                    "title": "Private fixture",
                    "createdAt": 800_000_000,
                    "updatedAt": 800_000_001,
                    "messages": rows,
                    "provider": "codex",
                    "model": "synthetic-no-provider-call",
                    "pendingFiles": [],
                    "pendingImages": [],
                    "pendingPDFs": [],
                    "pendingCriteria": [],
                }],
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")

    def prepare(self, **changes) -> dict:
        values = {
            "owner_identity": self.owner,
            "history_raw": self.history_raw,
            "work_session_raw": self.work_raw,
            "work_session_name": self.work_name,
            "conversation_id": self.conversation_id,
            "user_message_id": self.user_id,
            "assistant_message_id": self.assistant_id,
        }
        values.update(changes)
        return prepare_native_turn_handshake(self.spine_store, **values)

    def inspect(self, handshake: dict, **changes) -> dict:
        path = self.spine_root / f"{self.conversation_id}.spine.jsonl"
        values = {
            "owner_identity": self.owner,
            "history_raw": self.history_raw,
            "work_session_raw": self.work_raw,
            "work_session_name": self.work_name,
            "spine_raw": path.read_bytes() if path.exists() else None,
        }
        values.update(changes)
        return inspect_native_turn_handshake(handshake, **values)

    def apply(self, handshake: dict, **changes) -> dict:
        values = {
            "owner_identity": self.owner,
            "history_raw": self.history_raw,
            "work_session_raw": self.work_raw,
            "work_session_name": self.work_name,
        }
        values.update(changes)
        return apply_native_turn_handshake(self.spine_store, handshake, **values)

    def reviewed_work_session(self) -> tuple[dict, bytes]:
        def prepare_review(run: dict) -> dict:
            return review_preview(
                run,
                {"decision": "needs_work", "checks": [], "note": "Review metadata changed after completion."},
                [],
                workspace_matches=False,
                artifacts_complete=False,
            )

        reviewed = self.work_store.record_review(
            {"run_id": self.run_id, "fingerprint": self.work_session["fingerprint"]},
            self.conversation_id,
            prepare_review,
        )
        return reviewed, self.work_path.read_bytes()

    def additional_turn(self) -> dict:
        run_id, user_id, assistant_id = (str(uuid4()) for _ in range(3))
        prompt = f"Second exact prompt {uuid4()}"
        answer = f"Second exact answer {uuid4()}"
        instruction = build_instruction_receipt(
            provider="codex",
            mode="chat",
            prepared=PreparedLocalInstructions(
                "second synthetic local instructions",
                "legacy_cognitive_core_current_projection",
                None,
            ),
            developer_instructions="second synthetic P2h handshake contract",
        )
        timestamps = [
            "2026-09-04T11:00:00.000000Z",
            "2026-09-04T11:00:00.100000Z",
            "2026-09-04T11:00:01.000000Z",
            "2026-09-04T11:00:01.100000Z",
            "2026-09-04T11:01:00.000000Z",
            "2026-09-04T11:01:00.100000Z",
        ]
        with mock.patch("proto_mind.native_work_sessions.timestamp", side_effect=timestamps):
            with self.work_store.begin(
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
                run = writer.complete(answer, instruction_receipt=instruction)
        reference = build_turn_reference(
            receipt=run["turn_receipt"],
            source_message_id=user_id,
            input_text=prompt,
            response=answer,
        )
        user = self.message(user_id, "user", prompt)
        assistant = self.message(
            assistant_id,
            "assistant",
            answer,
            raw=answer,
            turnReference=reference,
        )
        history = self.history(messages=[user, assistant])
        name = run_id + ".json"
        return {
            "run_id": run_id,
            "user_id": user_id,
            "assistant_id": assistant_id,
            "history": history,
            "work_name": name,
            "work_raw": (self.work_store.directory / name).read_bytes(),
        }

    def test_owner_identity_is_explicit_stable_and_non_authorizing(self):
        rebuilt = build_native_owner_identity(self.installation_id)
        self.assertEqual(self.owner, rebuilt)
        self.assertEqual(self.owner["schema"], OWNER_SCHEMA)
        self.assertTrue(self.owner["stable_across_relaunch"])
        self.assertFalse(self.owner["process_id_bound"])
        self.assertFalse(self.owner["os_user_bound"])
        self.assertFalse(self.owner["permission_granted"])
        self.assertEqual(validate_native_owner_identity(self.owner)["identity_hash"], self.owner["identity_hash"])
        self.assertNotEqual(build_native_owner_identity(str(uuid4()))["owner_id"], self.owner["owner_id"])
        with self.assertRaisesRegex(SessionSpineHandshakeError, "bundle"):
            build_native_owner_identity(self.installation_id, application_id="other.app")

    def test_prepare_is_content_free_hashed_and_requires_saved_latest_turn(self):
        handshake = self.prepare()
        validated = validate_native_turn_handshake(handshake)
        encoded = json.dumps(validated, ensure_ascii=False)
        self.assertEqual(validated["schema"], HANDSHAKE_SCHEMA)
        self.assertEqual(validated["status"], "PREPARED")
        self.assertTrue(validated["history"]["saved_and_read_back"])
        self.assertTrue(validated["ordering"]["history_before_spine"])
        self.assertTrue(validated["ordering"]["spine_before_history_forbidden"])
        self.assertNotIn(self.prompt, encoded)
        self.assertNotIn(self.answer, encoded)
        self.assertNotIn(str(self.base), encoded)
        self.assertFalse(validated["boundaries"]["native_activation"])
        trailing = self.message(str(uuid4()), "report", "Local report", isError=True)
        with self.assertRaisesRegex(SessionSpineHandshakeError, "latest"):
            self.prepare(history_raw=self.history(messages=[trailing]))

    def test_handshake_tamper_is_rejected(self):
        handshake = self.prepare()
        changed = deepcopy(handshake)
        changed["source"]["run_id"] = str(uuid4())
        with self.assertRaisesRegex(SessionSpineHandshakeError, "hash"):
            validate_native_turn_handshake(changed)

    def test_rehashed_but_internally_conflicting_source_is_not_authority(self):
        handshake = self.prepare()
        changed = deepcopy(handshake)
        changed["source"]["input_sha256"] = "0" * 64
        material = {key: value for key, value in changed.items() if key != "handshake_hash"}
        changed["handshake_hash"] = hashlib.sha256(json.dumps(
            material,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()).hexdigest()
        validate_native_turn_handshake(changed)
        report = self.inspect(changed)
        self.assertEqual(report["state"], "SOURCE_LINEAGE_CONFLICT")
        with self.assertRaisesRegex(SessionSpineHandshakeError, "SOURCE_LINEAGE_CONFLICT"):
            self.apply(changed)

    def test_serialized_relaunch_reconstructs_ready_without_writing(self):
        handshake = json.loads(json.dumps(self.prepare()))
        before_work = self.work_path.read_bytes()
        reopened = SessionSpineStore(self.spine_root)
        report = inspect_native_turn_handshake(
            handshake,
            owner_identity=build_native_owner_identity(self.installation_id),
            history_raw=self.history_raw,
            work_session_raw=self.work_raw,
            work_session_name=self.work_name,
            spine_raw=None,
        )
        self.assertEqual(report["schema"], RECOVERY_SCHEMA)
        self.assertEqual(report["status"], "OK")
        self.assertEqual(report["state"], "READY_TO_COMMIT_SPINE")
        self.assertTrue(report["eligible_for_spine_apply"])
        self.assertTrue(report["boundaries"]["read_only"])
        self.assertFalse(self.spine_root.exists())
        self.assertEqual(self.work_path.read_bytes(), before_work)
        self.assertEqual(reopened.directory, self.spine_store.directory)

    def test_apply_commits_once_and_lost_response_replay_is_no_write(self):
        handshake = self.prepare()
        history_before, work_before = self.history_raw, self.work_path.read_bytes()
        first = self.apply(handshake)
        self.assertEqual(first["schema"], APPLY_SCHEMA)
        self.assertEqual(first["result"], "COMMITTED")
        self.assertTrue(first["write_performed"])
        self.assertEqual(first["written_scope"], "explicit_session_spine_store_only")
        path = self.spine_root / f"{self.conversation_id}.spine.jsonl"
        spine_after = path.read_bytes()
        second = self.apply(json.loads(json.dumps(handshake)))
        self.assertEqual(second["result"], "ALREADY_COMMITTED")
        self.assertFalse(second["write_performed"])
        self.assertEqual(path.read_bytes(), spine_after)
        self.assertEqual(self.history_raw, history_before)
        self.assertEqual(self.work_path.read_bytes(), work_before)

    def test_completed_run_without_saved_assistant_is_never_reconstructed(self):
        handshake = self.prepare()
        report = self.inspect(handshake, history_raw=self.history(include_assistant=False))
        self.assertEqual(report["status"], "WARN")
        self.assertEqual(report["state"], "ORPHANED_COMPLETED_RUN")
        self.assertFalse(report["eligible_for_spine_apply"])
        self.assertIn("no_auto_reconstruction", report["next_action"])
        with self.assertRaisesRegex(SessionSpineHandshakeError, "ORPHANED_COMPLETED_RUN"):
            self.apply(handshake, history_raw=self.history(include_assistant=False))

    def test_missing_work_session_blocks_recovery(self):
        handshake = self.prepare()
        report = self.inspect(handshake, work_session_raw=None)
        self.assertEqual(report["status"], "WARN")
        self.assertEqual(report["state"], "SOURCE_EVIDENCE_INCOMPLETE")
        self.assertFalse(report["eligible_for_spine_apply"])

    def test_different_installation_owner_fails_closed(self):
        handshake = self.prepare()
        report = self.inspect(handshake, owner_identity=build_native_owner_identity(str(uuid4())))
        self.assertEqual(report["status"], "ERROR")
        self.assertEqual(report["state"], "OWNER_IDENTITY_MISMATCH")
        with self.assertRaisesRegex(SessionSpineHandshakeError, "OWNER_IDENTITY_MISMATCH"):
            self.apply(handshake, owner_identity=build_native_owner_identity(str(uuid4())))

    def test_changed_target_message_is_a_source_conflict(self):
        handshake = self.prepare()
        changed = deepcopy(self.assistant)
        changed["text"] += " changed"
        report = self.inspect(handshake, history_raw=self.history(assistant=changed))
        self.assertEqual(report["status"], "ERROR")
        self.assertEqual(report["state"], "SOURCE_LINEAGE_CONFLICT")

    def test_second_turn_append_survives_relaunch_and_missing_preimage_refuses(self):
        first = self.prepare()
        self.apply(first)
        path = self.spine_root / f"{self.conversation_id}.spine.jsonl"
        first_raw = path.read_bytes()
        second = self.additional_turn()
        handshake = prepare_native_turn_handshake(
            SessionSpineStore(self.spine_root),
            owner_identity=build_native_owner_identity(self.installation_id),
            history_raw=second["history"],
            work_session_raw=second["work_raw"],
            work_session_name=second["work_name"],
            conversation_id=self.conversation_id,
            user_message_id=second["user_id"],
            assistant_message_id=second["assistant_id"],
        )
        self.assertEqual(handshake["spine"]["operation"], "append")
        missing = inspect_native_turn_handshake(
            handshake,
            owner_identity=self.owner,
            history_raw=second["history"],
            work_session_raw=second["work_raw"],
            work_session_name=second["work_name"],
            spine_raw=None,
        )
        self.assertEqual(missing["state"], "STALE_SPINE_PREIMAGE")
        receipt = apply_native_turn_handshake(
            SessionSpineStore(self.spine_root),
            json.loads(json.dumps(handshake)),
            owner_identity=self.owner,
            history_raw=second["history"],
            work_session_raw=second["work_raw"],
            work_session_name=second["work_name"],
        )
        self.assertEqual(receipt["result"], "COMMITTED")
        self.assertTrue(path.read_bytes().startswith(first_raw))

    def test_changed_spine_preimage_refuses_stale_create(self):
        handshake = self.prepare()
        other = str(uuid4())
        events = (
            SessionEvent.create(0, 1_000, "turn/start", {"native_run_id": other}),
            SessionEvent.create(1, 1_001, "user/message", {"native_message_id": str(uuid4())}, surface_op="append"),
            SessionEvent.create(2, 1_002, "assistant/message", {"native_message_id": str(uuid4())}, surface_op="append"),
            SessionEvent.create(3, 1_003, "turn/end", {"native_run_id": other}),
        )
        foreign_preimage = build_store_image(
            session_id=self.conversation_id,
            created_ms=1_000,
            owner_id=self.owner["owner_id"],
            events=events,
        )
        report = self.inspect(handshake, spine_raw=foreign_preimage)
        self.assertEqual(report["status"], "WARN")
        self.assertEqual(report["state"], "STALE_SPINE_PREIMAGE")

    def test_unknown_spine_tail_requires_separate_manual_recovery(self):
        handshake = self.prepare()
        self.apply(handshake)
        path = self.spine_root / f"{self.conversation_id}.spine.jsonl"
        report = self.inspect(handshake, spine_raw=path.read_bytes() + b'{"partial":')
        self.assertEqual(report["status"], "ERROR")
        self.assertEqual(report["state"], "MANUAL_SPINE_RECOVERY_REQUIRED")
        self.assertFalse(report["boundaries"]["automatic_repair"])

    def test_review_fingerprint_drift_before_commit_requires_new_handshake(self):
        handshake = self.prepare()
        reviewed, reviewed_raw = self.reviewed_work_session()
        self.assertEqual(reviewed["turn_receipt"]["receipt_hash"], self.work_session["turn_receipt"]["receipt_hash"])
        self.assertNotEqual(reviewed["fingerprint"], self.work_session["fingerprint"])
        report = self.inspect(handshake, work_session_raw=reviewed_raw)
        self.assertEqual(report["status"], "WARN")
        self.assertEqual(report["state"], "PREPARED_SOURCE_DRIFT")
        self.assertEqual(report["next_action"], "prepare_new_handshake_after_review")

    def test_review_fingerprint_drift_after_commit_preserves_stable_lineage(self):
        handshake = self.prepare()
        self.apply(handshake)
        reviewed, reviewed_raw = self.reviewed_work_session()
        path = self.spine_root / f"{self.conversation_id}.spine.jsonl"
        before = path.read_bytes()
        report = self.inspect(handshake, work_session_raw=reviewed_raw)
        self.assertEqual(report["status"], "WARN")
        self.assertEqual(report["state"], "COMMITTED_WITH_SOURCE_DRIFT")
        self.assertTrue(report["idempotent_no_write"])
        replay = self.apply(handshake, work_session_raw=reviewed_raw)
        self.assertEqual(replay["result"], "ALREADY_COMMITTED")
        self.assertFalse(replay["write_performed"])
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(reviewed["turn_receipt"]["receipt_hash"], self.reference["turn_receipt_hash"])

    def test_committed_store_without_history_is_a_visible_conflict(self):
        handshake = self.prepare()
        self.apply(handshake)
        report = self.inspect(handshake, history_raw=None)
        self.assertEqual(report["status"], "ERROR")
        self.assertEqual(report["state"], "STORE_ONLY_SOURCE_CONFLICT")
        self.assertFalse(report["boundaries"]["inferred_pairing"])

    def test_handshake_is_store_scoped_and_has_no_production_activation(self):
        handshake = self.prepare()
        other_store = SessionSpineStore(self.base / "other-spine")
        with self.assertRaisesRegex(SessionSpineHandshakeError, "different explicit"):
            apply_native_turn_handshake(
                other_store,
                handshake,
                owner_identity=self.owner,
                history_raw=self.history_raw,
                work_session_raw=self.work_raw,
                work_session_name=self.work_name,
            )
        self.assertFalse(handshake["boundaries"]["native_activation"])
        self.assertFalse(handshake["boundaries"]["durable_handshake_store_installed"])
        self.assertFalse((self.base / "other-spine").exists())

    def test_legacy_unlinked_history_cannot_prepare_or_backfill(self):
        unlinked = deepcopy(self.assistant)
        unlinked.pop("turnReference")
        legacy_history = json.dumps({
            "version": 5,
            "selectedID": self.conversation_id,
            "conversations": [{
                "id": self.conversation_id,
                "messages": [self.user, unlinked],
            }],
        }, sort_keys=True, separators=(",", ":")).encode()
        with self.assertRaisesRegex(SessionSpineHandshakeError, "Turn Lineage"):
            self.prepare(history_raw=legacy_history)


if __name__ == "__main__":
    unittest.main()
