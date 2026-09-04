"""Forward-only writer, replay, rollback, and dual-read checks for P2g."""
from copy import deepcopy
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase, mock
from uuid import uuid4

from proto_mind.native_instructions import PreparedLocalInstructions, build_instruction_receipt
from proto_mind.native_turn_lineage import build_turn_reference
from proto_mind.native_work_sessions import WorkSessionStore
from proto_mind.session_spine import SessionEvent
from proto_mind.session_spine_archive_copy import audit_native_archive_copy
from proto_mind.session_spine_forward import (
    APPLY_SCHEMA,
    DUAL_READ_SCHEMA,
    PLAN_SCHEMA,
    SessionSpineForwardError,
    apply_forward_native_turn,
    audit_forward_dual_read,
    preview_forward_native_turn,
)
from proto_mind.session_spine_store import (
    SessionSpineStore,
    SessionSpineStoreError,
    build_store_image,
    extend_store_image,
    inspect_store_image,
)


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


class SessionSpineTurnBatchTests(TestCase):
    def setUp(self):
        temporary = TemporaryDirectory(prefix="proto-spine-turn-batch-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve() / "spine"
        self.session_id = str(uuid4())
        self.store = SessionSpineStore(self.root)

    @staticmethod
    def turn(offset: int = 0, time_ms: int = 1_000) -> tuple[SessionEvent, ...]:
        return (
            SessionEvent.create(offset, time_ms, "turn/start", {"native_run_id": str(uuid4())}),
            SessionEvent.create(
                offset + 1,
                time_ms + 1,
                "user/message",
                {"native_message_id": str(uuid4()), "text": "private input"},
                surface_op="append",
            ),
            SessionEvent.create(
                offset + 2,
                time_ms + 2,
                "assistant/message",
                {"native_message_id": str(uuid4()), "text": "private output"},
                surface_op="append",
            ),
            SessionEvent.create(offset + 3, time_ms + 3, "turn/end", {"outcome": "response_recorded"}),
        )

    def data_path(self) -> Path:
        return self.root / f"{self.session_id}.spine.jsonl"

    def test_pure_extension_preserves_exact_preimage_and_owner_history(self):
        first = self.turn()
        before = build_store_image(
            session_id=self.session_id,
            created_ms=first[0].time_ms,
            owner_id="owner.forward",
            events=first,
        )
        second = self.turn(len(first), 2_000)
        after = extend_store_image(
            before,
            session_id=self.session_id,
            owner_id="owner.forward",
            events=second,
        )
        snapshot = inspect_store_image(after, self.session_id)
        self.assertTrue(after.startswith(before))
        self.assertEqual(snapshot.events, (*first, *second))
        self.assertEqual(snapshot.append_owners, ("owner.forward",))

    def test_complete_turn_batch_commits_with_verified_receipt(self):
        events = self.turn()
        with self.store.writer(self.session_id, "owner.forward", created_ms=events[0].time_ms) as writer:
            receipt = writer.append_turn(events)
        value = receipt.to_dict()
        self.assertEqual(value["event_count"], len(events))
        self.assertEqual(value["first_event_seq"], 0)
        self.assertEqual(value["last_event_seq"], len(events) - 1)
        self.assertTrue(value["post_state_verified"])
        self.assertFalse(value["crash_atomic"])
        self.assertFalse(value["target_command_executed"])
        self.assertEqual(self.store.inspect(self.session_id).recovery_state, "closed")

    def test_invalid_batch_is_rejected_before_writing(self):
        events = self.turn()[:-1]
        with self.store.writer(self.session_id, "owner.forward", created_ms=1_000) as writer:
            before = self.data_path().read_bytes()
            with self.assertRaisesRegex(SessionSpineStoreError, "start and end"):
                writer.append_turn(events)
            self.assertEqual(self.data_path().read_bytes(), before)
            self.assertFalse(writer.failed)

    def test_partial_batch_failure_restores_exact_preimage_and_blocks_retry(self):
        first = self.turn()
        with self.store.writer(self.session_id, "owner.forward", created_ms=1_000) as writer:
            writer.append_turn(first)
        before = self.data_path().read_bytes()
        second = self.turn(len(first), 2_000)
        snapshot = self.store.inspect(self.session_id)
        with self.store.writer(
            self.session_id,
            "owner.forward",
            expected_fingerprint=snapshot.file_sha256,
        ) as writer:
            def fail_after_partial_write(payload: bytes) -> None:
                os.write(writer.data, payload[:37])
                os.fsync(writer.data)
                raise OSError("simulated partial batch failure")

            writer._write_and_sync = fail_after_partial_write
            with self.assertRaisesRegex(SessionSpineStoreError, "exact preimage was restored"):
                writer.append_turn(second)
            self.assertEqual(self.data_path().read_bytes(), before)
            with self.assertRaisesRegex(SessionSpineStoreError, "previous append outcome is unknown"):
                writer.append_turn(second)
        self.assertEqual(self.data_path().read_bytes(), before)
        self.assertEqual(self.store.inspect(self.session_id).events, first)


class SessionSpineForwardTests(TestCase):
    def setUp(self):
        temporary = TemporaryDirectory(prefix="proto-spine-forward-")
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name).resolve()
        self.project = self.base / "project"
        self.project.mkdir()
        self.native_state = self.base / "native-state"
        self.work_store = WorkSessionStore(self.native_state, self.project)
        self.spine_root = self.base / "forward-spine"
        self.spine_store = SessionSpineStore(self.spine_root)
        self.conversation_id = str(uuid4())
        self.owner_id = "native.forward.owner.v1"
        self.turns: list[dict] = []
        self.run_raws: dict[str, bytes] = {}

    @staticmethod
    def _timestamps(ordinal: int) -> list[str]:
        hour = 10 + ordinal
        return [
            f"2026-09-04T{hour:02d}:00:00.000000Z",
            f"2026-09-04T{hour:02d}:00:00.100000Z",
            f"2026-09-04T{hour:02d}:00:01.000000Z",
            f"2026-09-04T{hour:02d}:00:01.100000Z",
            f"2026-09-04T{hour:02d}:01:00.000000Z",
            f"2026-09-04T{hour:02d}:01:00.100000Z",
        ]

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
            "operatorInput": False,
            **extra,
        }

    def add_turn(self, ordinal: int) -> dict:
        run_id, user_id, assistant_id = (str(uuid4()) for _ in range(3))
        prompt = f"Exact private prompt {ordinal} {uuid4()}"
        answer = f"Exact private answer {ordinal} {uuid4()}"
        instruction = build_instruction_receipt(
            provider="codex",
            mode="chat",
            prepared=PreparedLocalInstructions(
                "synthetic local instructions",
                "legacy_cognitive_core_current_projection",
                None,
            ),
            developer_instructions="synthetic P2g forward contract",
        )
        with mock.patch(
            "proto_mind.native_work_sessions.timestamp",
            side_effect=self._timestamps(ordinal),
        ):
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
        user = self._message(user_id, "user", prompt)
        assistant = self._message(
            assistant_id,
            "assistant",
            answer,
            raw=answer,
            turnReference=reference,
        )
        record = {
            "run_id": run_id,
            "user": user,
            "assistant": assistant,
            "run": run,
            "reference": reference,
            "prompt": prompt,
            "answer": answer,
        }
        self.turns.append(record)
        name = run_id + ".json"
        self.run_raws[name] = (self.work_store.directory / name).read_bytes()
        return record

    def preview(self, turn: dict, **changes):
        values = {
            "session_id": self.conversation_id,
            "owner_id": self.owner_id,
            "conversation_id": self.conversation_id,
            "user_message": turn["user"],
            "assistant_message": turn["assistant"],
            "work_session": turn["run"],
            "turn_reference": turn["reference"],
        }
        values.update(changes)
        return preview_forward_native_turn(self.spine_store, **values)

    def history(self, turns: list[dict] | None = None, *, legacy: bool = False) -> bytes:
        messages: list[dict] = []
        for turn in self.turns if turns is None else turns:
            messages.extend((turn["user"], turn["assistant"]))
        if legacy:
            messages.extend((
                self._message(str(uuid4()), "user", "Legacy text remains private"),
                self._message(str(uuid4()), "assistant", "Legacy answer remains private", raw="Legacy answer remains private"),
            ))
        return json.dumps({
            "version": 5,
            "selectedID": self.conversation_id,
            "conversations": [{
                "id": self.conversation_id,
                "title": "Private title",
                "createdAt": 800_000_000,
                "updatedAt": 800_000_001,
                "messages": messages,
                "provider": "codex",
                "model": "synthetic-no-provider-call",
            }],
        }, ensure_ascii=False).encode("utf-8")

    def archive_report(self, turns: list[dict] | None = None, *, legacy: bool = False) -> dict:
        selected = self.turns if turns is None else turns
        names = {turn["run_id"] + ".json" for turn in selected}
        raws = {name: raw for name, raw in self.run_raws.items() if name in names}
        history = self.history(selected, legacy=legacy)
        manifest = tuple(sorted((name, _sha256(raw)) for name, raw in raws.items()))
        return audit_native_archive_copy(
            history,
            raws,
            expected_history_sha256=_sha256(history),
            expected_work_session_manifest=manifest,
        )

    def test_first_turn_plan_apply_and_lost_response_replay_are_exact(self):
        turn = self.add_turn(0)
        plan = self.preview(turn)
        public = plan.to_dict()
        encoded = json.dumps(public, ensure_ascii=False)
        self.assertEqual(public["schema"], PLAN_SCHEMA)
        self.assertEqual(public["status"], "READY")
        self.assertEqual(public["operation"], "create")
        self.assertNotIn(turn["prompt"], encoded)
        self.assertNotIn(turn["answer"], encoded)
        self.assertNotIn(str(self.spine_root), encoded)
        receipt = apply_forward_native_turn(self.spine_store, plan)
        self.assertEqual(receipt["schema"], APPLY_SCHEMA)
        self.assertEqual(receipt["result"], "COMMITTED")
        self.assertTrue(receipt["write_performed"])
        before_replay = (self.spine_root / f"{self.conversation_id}.spine.jsonl").read_bytes()

        replay_plan = self.preview(turn)
        self.assertEqual(replay_plan.status, "ALREADY_COMMITTED")
        replay = apply_forward_native_turn(self.spine_store, replay_plan)
        self.assertEqual(replay["result"], "ALREADY_COMMITTED")
        self.assertFalse(replay["write_performed"])
        self.assertEqual(
            (self.spine_root / f"{self.conversation_id}.spine.jsonl").read_bytes(),
            before_replay,
        )

    def test_second_turn_append_preserves_exact_preimage(self):
        first = self.add_turn(0)
        apply_forward_native_turn(self.spine_store, self.preview(first))
        path = self.spine_root / f"{self.conversation_id}.spine.jsonl"
        before = path.read_bytes()
        second = self.add_turn(1)
        plan = self.preview(second)
        self.assertEqual(plan.operation, "append")
        self.assertTrue(plan._candidate_raw.startswith(before))
        result = apply_forward_native_turn(self.spine_store, plan)
        self.assertEqual(result["result"], "COMMITTED")
        snapshot = self.spine_store.inspect(self.conversation_id)
        self.assertEqual(len(snapshot.append_owners), 1)
        self.assertEqual(snapshot.append_owners[0], self.owner_id)
        self.assertEqual(len([event for event in snapshot.events if event.event_type == "turn/end"]), 2)

    def test_owner_reference_and_work_session_drift_fail_closed(self):
        turn = self.add_turn(0)
        with self.assertRaisesRegex(SessionSpineForwardError, "reference"):
            changed_reference = deepcopy(turn["reference"])
            changed_reference["reference_hash"] = "0" * 64
            self.preview(turn, turn_reference=changed_reference)
        with self.assertRaisesRegex(SessionSpineForwardError, "fingerprint"):
            changed_run = deepcopy(turn["run"])
            changed_run["fingerprint"] = "0" * 64
            self.preview(turn, work_session=changed_run)
        apply_forward_native_turn(self.spine_store, self.preview(turn))
        second = self.add_turn(1)
        with self.assertRaisesRegex(SessionSpineForwardError, "stable owner"):
            self.preview(second, owner_id="native.other.owner")

    def test_message_identity_cannot_be_rebound_to_another_run(self):
        first = self.add_turn(0)
        apply_forward_native_turn(self.spine_store, self.preview(first))
        second = self.add_turn(1)
        changed_user = deepcopy(second["user"])
        changed_user["id"] = first["user"]["id"]
        changed_reference = build_turn_reference(
            receipt=second["run"]["turn_receipt"],
            source_message_id=changed_user["id"],
            input_text=changed_user["text"],
            response=second["answer"],
        )
        with self.assertRaisesRegex(SessionSpineForwardError, "message identity"):
            self.preview(
                second,
                user_message=changed_user,
                turn_reference=changed_reference,
            )

    def test_stale_absent_store_plan_cannot_overwrite_another_turn(self):
        first = self.add_turn(0)
        first_plan = self.preview(first)
        second = self.add_turn(1)
        second_plan = self.preview(second)
        apply_forward_native_turn(self.spine_store, first_plan)
        before = (self.spine_root / f"{self.conversation_id}.spine.jsonl").read_bytes()
        with self.assertRaisesRegex(SessionSpineForwardError, "absent-store precondition"):
            apply_forward_native_turn(self.spine_store, second_plan)
        self.assertEqual((self.spine_root / f"{self.conversation_id}.spine.jsonl").read_bytes(), before)

    def test_stale_append_plan_cannot_cross_a_new_commit(self):
        first = self.add_turn(0)
        apply_forward_native_turn(self.spine_store, self.preview(first))
        second = self.add_turn(1)
        second_plan = self.preview(second)
        third = self.add_turn(2)
        third_plan = self.preview(third)
        apply_forward_native_turn(self.spine_store, second_plan)
        before = (self.spine_root / f"{self.conversation_id}.spine.jsonl").read_bytes()
        with self.assertRaisesRegex(SessionSpineForwardError, "inspected preimage"):
            apply_forward_native_turn(self.spine_store, third_plan)
        self.assertEqual((self.spine_root / f"{self.conversation_id}.spine.jsonl").read_bytes(), before)

    def test_dual_read_keeps_legacy_and_forward_evidence_separate(self):
        first = self.add_turn(0)
        apply_forward_native_turn(self.spine_store, self.preview(first))
        report = self.archive_report(legacy=True)
        result = audit_forward_dual_read(
            report,
            {self.conversation_id: self.spine_store.inspect(self.conversation_id)},
        )
        self.assertEqual(result["schema"], DUAL_READ_SCHEMA)
        self.assertEqual(result["status"], "WARN")
        self.assertEqual(result["counts"]["legacy_unlinked"], 1)
        self.assertEqual(result["counts"]["forward_stored"], 1)
        self.assertEqual(result["counts"]["exact_recovery_candidates"], 0)
        self.assertFalse(result["boundaries"]["legacy_backfill"])
        self.assertFalse(result["boundaries"]["authoritative_history_active"])
        encoded = json.dumps(result, ensure_ascii=False)
        self.assertNotIn(first["prompt"], encoded)
        self.assertNotIn(first["answer"], encoded)

    def test_dual_read_distinguishes_recovery_candidate_and_incomplete_copy(self):
        first = self.add_turn(0)
        first_report = self.archive_report([first])
        absent = audit_forward_dual_read(first_report, {})
        self.assertEqual(absent["counts"]["exact_recovery_candidates"], 1)

        apply_forward_native_turn(self.spine_store, self.preview(first))
        second = self.add_turn(1)
        apply_forward_native_turn(self.spine_store, self.preview(second))
        store_only = audit_forward_dual_read(
            first_report,
            {self.conversation_id: self.spine_store.inspect(self.conversation_id)},
        )
        self.assertEqual(store_only["counts"]["forward_stored"], 1)
        self.assertEqual(store_only["counts"]["store_only_or_copy_incomplete"], 1)
        self.assertEqual(store_only["status"], "WARN")

    def test_dual_read_refuses_tampered_archive_audit(self):
        turn = self.add_turn(0)
        report = self.archive_report([turn])
        report["coverage"]["compatible_turns"] = 999
        with self.assertRaisesRegex(SessionSpineForwardError, "hash"):
            audit_forward_dual_read(report, {})

    def test_dual_read_rejects_same_run_with_different_message_pair(self):
        turn = self.add_turn(0)
        report = self.archive_report([turn])
        events = (
            SessionEvent.create(0, 1_000, "turn/start", {"native_run_id": turn["run_id"]}),
            SessionEvent.create(
                1,
                1_001,
                "user/message",
                {"native_message_id": str(uuid4())},
                surface_op="append",
            ),
            SessionEvent.create(
                2,
                1_002,
                "assistant/message",
                {"native_message_id": str(uuid4())},
                surface_op="append",
            ),
            SessionEvent.create(3, 1_003, "turn/end", {"outcome": "response_recorded"}),
        )
        raw = build_store_image(
            session_id=self.conversation_id,
            created_ms=1_000,
            owner_id=self.owner_id,
            events=events,
        )
        result = audit_forward_dual_read(
            report,
            {self.conversation_id: inspect_store_image(raw, self.conversation_id)},
        )
        self.assertEqual(result["status"], "ERROR")
        self.assertEqual(result["counts"]["forward_stored"], 0)
        self.assertEqual(result["findings"][0]["category"], "forward_lineage_mismatch")

    def test_forward_contract_has_no_native_activation_or_implicit_path(self):
        turn = self.add_turn(0)
        plan = self.preview(turn)
        public = plan.to_dict()
        self.assertFalse(public["boundaries"]["native_activation"])
        self.assertFalse(public["boundaries"]["authoritative_history_active"])
        self.assertFalse(public["boundaries"]["legacy_backfill"])
        forged = replace(plan, run_id=str(uuid4()), plan_hash="")
        forged = replace(
            forged,
            plan_hash=_sha256(json.dumps(
                forged._material(),
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")),
        )
        with self.assertRaisesRegex(SessionSpineForwardError, "identities"):
            apply_forward_native_turn(self.spine_store, forged)
        with self.assertRaises(SessionSpineStoreError):
            SessionSpineStore(Path("implicit/session-spine"))
