"""Pure ordered multi-turn Session Spine composition checks for P2c."""
from copy import deepcopy
import hashlib
import json
from unittest import TestCase, mock
from uuid import uuid4

from proto_mind.native_progress import display_text
from proto_mind.native_session_spine import materialize_message_text
from proto_mind.session_spine import SessionEvent, SurfaceReplace
from proto_mind.session_spine_composition import (
    MAX_TURNS,
    SessionSpineCompositionError,
    compose_native_fixtures,
    rebase_session_event,
)
from proto_mind.session_spine_store import inspect_store_image
from proto_mind.session_spine_transfer import FIXTURE_SCHEMA, project_native_fixture


def _canonical_line(value):
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8") + b"\n"


class SessionSpineCompositionTests(TestCase):
    def setUp(self):
        self.conversation = str(uuid4())
        self.owner = "composition.preview"
        self.prompts = ("Первый точный запрос.", "Второй точный запрос.")
        self.answers = ("Первый точный ответ.", "Второй точный ответ.")

    def fixture(self, ordinal, **changes):
        times = (
            ("2026-09-03T10:00:00.000000Z", "2026-09-03T10:01:00.000000Z"),
            ("2026-09-03T10:02:00.000000Z", "2026-09-03T10:03:00.000000Z"),
            ("2026-09-03T10:04:00.000000Z", "2026-09-03T10:05:00.000000Z"),
            ("2026-09-03T10:06:00.000000Z", "2026-09-03T10:07:00.000000Z"),
            ("2026-09-03T10:08:00.000000Z", "2026-09-03T10:09:00.000000Z"),
            ("2026-09-03T10:10:00.000000Z", "2026-09-03T10:11:00.000000Z"),
            ("2026-09-03T10:12:00.000000Z", "2026-09-03T10:13:00.000000Z"),
            ("2026-09-03T10:14:00.000000Z", "2026-09-03T10:15:00.000000Z"),
        )
        prompt = self.prompts[ordinal] if ordinal < len(self.prompts) else f"Prompt {ordinal}"
        answer = self.answers[ordinal] if ordinal < len(self.answers) else f"Answer {ordinal}"
        run_id = changes.pop("run_id", str(uuid4()))
        user_id = changes.pop("user_id", str(uuid4()))
        assistant_id = changes.pop("assistant_id", str(uuid4()))
        conversation = changes.pop("conversation_id", self.conversation)
        tools = changes.pop("tools", [])
        created_at, finished_at = changes.pop("times", times[ordinal])
        run = {
            "schema": "proto_mind.native_work_session.v1",
            "id": run_id,
            "conversation_id": conversation,
            "project_root": "/synthetic/project",
            "workspace": {"path": "/synthetic/project", "device": 1, "inode": 2},
            "created_at": created_at,
            "updated_at": finished_at,
            "finished_at": finished_at,
            "status": "completed",
            "provider": "codex",
            "requested_model": "gpt-5.6-sol",
            "requested_effort": "high",
            "access_mode": "chat",
            "input_preview": display_text(prompt, 800),
            "input_chars": len(prompt),
            "input_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
            "answer_preview": display_text(answer, 1600),
            "sources": [],
            "parent_run_id": None,
            "tools": tools,
            "work_log": {},
            "network_access_performed": False,
            "computer_use_performed": False,
            "screen_access_performed": False,
            "verification": "not_assessed",
            "acceptance": "not_recorded",
            "display_status": "completed",
            "fingerprint": hashlib.sha256(f"run-{ordinal}".encode()).hexdigest(),
            "automatic_resume": False,
        }
        run.update(changes.pop("run_changes", {}))
        value = {
            "schema": FIXTURE_SCHEMA,
            "conversation_id": conversation,
            "user_message": {
                "id": user_id,
                "role": "user",
                "text": prompt,
                "isError": False,
                "operatorInput": False,
            },
            "assistant_message": {
                "id": assistant_id,
                "role": "assistant",
                "text": answer,
                "raw": answer,
                "isError": False,
            },
            "work_session": run,
        }
        value.update(changes)
        return value

    def raw_pair(self, **second_changes):
        fixtures = (
            _canonical_line(self.fixture(0)),
            _canonical_line(self.fixture(1, **second_changes)),
        )
        return fixtures, tuple(hashlib.sha256(raw).hexdigest() for raw in fixtures)

    def compose(self, fixtures=None, order=None):
        if fixtures is None:
            fixtures, order = self.raw_pair()
        return compose_native_fixtures(
            fixtures,
            expected_order=order,
            expected_conversation_id=self.conversation,
            owner_id=self.owner,
        )

    def test_two_explicit_turns_compose_with_contiguous_sequences(self):
        result = self.compose()
        self.assertEqual([event.seq for event in result._events], list(range(len(result._events))))
        self.assertEqual(len(result.turns), 2)
        self.assertEqual(result.turns[0].rebased_event_start, 0)
        self.assertEqual(result.turns[1].rebased_event_start, result.turns[0].rebased_event_end + 1)
        self.assertEqual(result.surface.nodes, tuple(
            sequence for turn in result.turns for sequence in turn.rebased_surface_nodes
        ))

    def test_source_references_are_rebased_without_changing_event_data(self):
        fixtures, order = self.raw_pair()
        result = self.compose(fixtures, order)
        second = result.turns[1]
        offset = second.rebased_event_start
        rebased_events = result._events[offset:]
        source_events = project_native_fixture(fixtures[1]).events
        for source, rebased in zip(source_events, rebased_events, strict=True):
            self.assertEqual(rebased.data_json, source.data_json)
            expected_sources = None if source.source_event_seqs is None else tuple(
                value + offset for value in source.source_event_seqs
            )
            self.assertEqual(rebased.source_event_seqs, expected_sources)

    def test_surface_replacement_boundaries_and_sources_rebase_together(self):
        event = SessionEvent.create(
            2,
            3,
            "assistant/message",
            {"content": "replacement"},
            surface_op=SurfaceReplace(0, 1),
            source_event_seqs=(0, 1),
        )
        rebased = rebase_session_event(event, 5)
        self.assertEqual(rebased.seq, 7)
        self.assertEqual(rebased.surface_op, SurfaceReplace(5, 6))
        self.assertEqual(rebased.source_event_seqs, (5, 6))
        self.assertEqual(rebased.data_json, event.data_json)

    def test_candidate_reparses_with_exact_closed_event_and_surface_parity(self):
        result = self.compose()
        snapshot = inspect_store_image(result._candidate_raw, self.conversation)
        self.assertEqual(snapshot.events, result._events)
        self.assertEqual(snapshot.surface, result.surface)
        self.assertEqual(snapshot.recovery_state, "closed")
        self.assertEqual(snapshot.file_sha256, result.candidate_sha256)

    def test_message_content_materializes_after_rebase(self):
        result = self.compose()
        for ordinal, turn in enumerate(result.turns):
            self.assertEqual(
                materialize_message_text(result._events, turn.rebased_user_message_seq),
                self.prompts[ordinal],
            )
            self.assertEqual(
                materialize_message_text(result._events, turn.rebased_assistant_message_seq),
                self.answers[ordinal],
            )

    def test_report_is_metadata_only_and_denies_authority(self):
        report = self.compose().to_dict()
        rendered = json.dumps(report, ensure_ascii=False)
        self.assertNotIn(self.prompts[0], rendered)
        self.assertNotIn(self.answers[1], rendered)
        self.assertTrue(report["read_only"])
        self.assertTrue(report["no_file_access"])
        self.assertFalse(report["ordering"]["inferred"])
        self.assertFalse(report["personal_archive_scanned"])
        self.assertFalse(report["candidate"]["safe_to_publish"])
        self.assertEqual(len(report["turns"][0]["source"]["event_payload_sha256"]), 64)
        self.assertEqual(report["turns"][0]["content"]["memory_candidate_ids"], [])
        self.assertTrue(report["authority"]["separate_checkpoint_required"])
        self.assertFalse(any(
            value for key, value in report["authority"].items() if key != "separate_checkpoint_required"
        ))

    def test_composition_is_deterministic_and_does_not_mutate_inputs(self):
        fixtures, order = self.raw_pair()
        before = deepcopy((fixtures, order))
        first = self.compose(fixtures, order)
        second = self.compose(fixtures, order)
        self.assertEqual((fixtures, order), before)
        self.assertEqual(first, second)

    def test_wrong_hash_or_reordered_hash_manifest_is_refused(self):
        fixtures, order = self.raw_pair()
        for invalid in (("0" * 64, order[1]), tuple(reversed(order))):
            with self.subTest(order=invalid), self.assertRaisesRegex(SessionSpineCompositionError, "digest"):
                self.compose(fixtures, invalid)

    def test_reversed_fixtures_are_not_sorted_or_guessed(self):
        fixtures, order = self.raw_pair()
        with self.assertRaisesRegex(SessionSpineCompositionError, "will not sort or guess"):
            self.compose(tuple(reversed(fixtures)), tuple(reversed(order)))

    def test_overlapping_or_equal_turn_boundary_is_refused(self):
        for times in (
            ("2026-09-03T10:00:30.000000Z", "2026-09-03T10:02:00.000000Z"),
            ("2026-09-03T10:01:00.000000Z", "2026-09-03T10:02:00.000000Z"),
        ):
            fixtures, order = self.raw_pair(times=times)
            with self.subTest(times=times), self.assertRaisesRegex(SessionSpineCompositionError, "overlaps"):
                self.compose(fixtures, order)

    def test_mixed_conversation_is_refused(self):
        fixtures, order = self.raw_pair(conversation_id=str(uuid4()))
        with self.assertRaisesRegex(SessionSpineCompositionError, "conversation"):
            self.compose(fixtures, order)

    def test_duplicate_fixture_digest_is_refused(self):
        raw = _canonical_line(self.fixture(0))
        digest = hashlib.sha256(raw).hexdigest()
        with self.assertRaisesRegex(SessionSpineCompositionError, "duplicate fixture"):
            self.compose((raw, raw), (digest, digest))

    def test_duplicate_run_or_message_identity_is_refused(self):
        first = self.fixture(0)
        for identity in ("run", "user", "assistant"):
            changes = {f"{identity}_id": (
                first["work_session"]["id"] if identity == "run" else first[f"{identity}_message"]["id"]
            )}
            fixtures = (_canonical_line(first), _canonical_line(self.fixture(1, **changes)))
            order = tuple(hashlib.sha256(raw).hexdigest() for raw in fixtures)
            expected = "run" if identity == "run" else "message"
            with self.subTest(identity=identity), self.assertRaisesRegex(SessionSpineCompositionError, expected):
                self.compose(fixtures, order)

    def test_noncanonical_or_invalid_p1_fixture_is_refused(self):
        valid = _canonical_line(self.fixture(1))
        noncanonical = json.dumps(self.fixture(0), ensure_ascii=False).encode() + b"\n"
        invalid = self.fixture(0)
        invalid["work_session"]["input_sha256"] = "0" * 64
        for first in (noncanonical, _canonical_line(invalid), b"{}"):
            fixtures = (first, valid)
            order = tuple(hashlib.sha256(raw).hexdigest() for raw in fixtures)
            with self.subTest(first=first[:20]), self.assertRaisesRegex(SessionSpineCompositionError, "P1"):
                self.compose(fixtures, order)

    def test_single_turn_mutable_inputs_and_excess_turns_are_refused(self):
        fixtures, order = self.raw_pair()
        with self.assertRaisesRegex(SessionSpineCompositionError, "two to 64"):
            self.compose(fixtures[:1], order[:1])
        with self.assertRaisesRegex(SessionSpineCompositionError, "immutable tuples"):
            compose_native_fixtures(
                list(fixtures),
                expected_order=order,
                expected_conversation_id=self.conversation,
                owner_id=self.owner,
            )
        with self.assertRaisesRegex(SessionSpineCompositionError, "two to 64"):
            self.compose(tuple(fixtures[0] for _ in range(MAX_TURNS + 1)), tuple(order[0] for _ in range(MAX_TURNS + 1)))

    def test_total_fixture_byte_limit_is_enforced_before_projection(self):
        fixtures, order = self.raw_pair()
        with mock.patch("proto_mind.session_spine_composition.MAX_TOTAL_FIXTURE_BYTES", 1):
            with self.assertRaisesRegex(SessionSpineCompositionError, "byte boundary"):
                self.compose(fixtures, order)

    def test_p2a_event_limit_blocks_oversized_composition(self):
        fixtures = tuple(_canonical_line(self.fixture(
            ordinal,
            tools=[{
                "id": f"tool-{ordinal}-{index}",
                "kind": "commandExecution",
                "status": "completed",
                "command": "synthetic-read-only",
                "output_preview": "",
            } for index in range(64)],
        )) for ordinal in range(8))
        order = tuple(hashlib.sha256(raw).hexdigest() for raw in fixtures)
        with self.assertRaisesRegex(SessionSpineCompositionError, "event count"):
            self.compose(fixtures, order)

    def test_unknown_turn_remains_explicit_without_success_inference(self):
        second = self.fixture(
            1,
            assistant_message=None,
            run_changes={
                "status": "interrupted",
                "display_status": "unknown",
                "dispatched_at": "2026-09-03T10:02:10.000000Z",
                "answer_preview": "",
            },
        )
        fixtures = (_canonical_line(self.fixture(0)), _canonical_line(second))
        order = tuple(hashlib.sha256(raw).hexdigest() for raw in fixtures)
        result = self.compose(fixtures, order)
        report = result.to_dict()
        self.assertEqual(result.turns[1].display_status, "unknown")
        self.assertIsNone(result.turns[1].rebased_assistant_message_seq)
        self.assertTrue(result.turns[1].warnings)
        self.assertFalse(report["composition"]["task_success_inferred"])
        self.assertEqual(inspect_store_image(result._candidate_raw, self.conversation).recovery_state, "closed")

    def test_composition_has_no_file_or_path_access(self):
        fixtures, order = self.raw_pair()
        with mock.patch("builtins.open", side_effect=AssertionError("unexpected file access")):
            result = self.compose(fixtures, order)
        self.assertEqual(len(result.turns), 2)

    def test_invalid_expected_identity_or_owner_fails_closed(self):
        fixtures, order = self.raw_pair()
        with self.assertRaisesRegex(SessionSpineCompositionError, "conversation"):
            compose_native_fixtures(
                fixtures,
                expected_order=order,
                expected_conversation_id="not-a-uuid",
                owner_id=self.owner,
            )
        with self.assertRaisesRegex(SessionSpineCompositionError, "owner"):
            compose_native_fixtures(
                fixtures,
                expected_order=order,
                expected_conversation_id=self.conversation,
                owner_id="bad owner",
            )
