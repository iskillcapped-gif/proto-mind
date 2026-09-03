"""Pure session-spine replay never edits history or invents provenance."""
from copy import deepcopy
import math
from unittest import TestCase

from proto_mind.session_spine import (
    MAX_SOURCE_EVENT_REFS,
    SessionEvent,
    SessionSpineError,
    SurfaceReplace,
    event_from_dict,
    fold_surface,
    visible_events,
)


def event(seq, event_type, *, op=None, sources=None, data=None, ignorable=False):
    return SessionEvent.create(
        seq,
        1_000 + seq,
        event_type,
        data or {"value": seq},
        ignorable=ignorable,
        surface_op=op,
        source_event_seqs=sources,
    )


class SessionSpineTests(TestCase):
    def test_append_surface_preserves_message_order(self):
        rows = (
            event(0, "turn/start"),
            event(1, "user/message", op="append"),
            event(2, "assistant/chunk"),
            event(3, "assistant/message", op="append", sources=[2]),
            event(4, "turn/end"),
        )
        snapshot = fold_surface(rows)
        self.assertEqual(snapshot.nodes, (1, 3))
        self.assertEqual(snapshot.event_count, 5)
        self.assertEqual([row.seq for row in visible_events(rows)], [1, 3])
        self.assertEqual(snapshot.replacements, ())

    def test_replace_shadows_surface_without_changing_log(self):
        rows = [
            event(0, "user/message", op="append"),
            event(1, "assistant/message", op="append", sources=[]),
            event(2, "user/message", op="append"),
            event(3, "assistant/message", op="append", sources=[]),
        ]
        before = [row.to_dict() for row in rows]
        rows.append(event(4, "assistant/message", op=SurfaceReplace(0, 2), sources=[0, 1, 2]))
        snapshot = fold_surface(rows)
        self.assertEqual(snapshot.nodes, (4, 3))
        self.assertEqual(snapshot.replacements[0].shadowed_seqs, (0, 1, 2))
        self.assertEqual([row.to_dict() for row in rows[:4]], before)

    def test_replace_may_cite_additional_log_only_sources(self):
        rows = (
            event(0, "user/message", op="append"),
            event(1, "assistant/chunk"),
            event(2, "assistant/message", op="append", sources=[1]),
            event(3, "assistant/message", op=SurfaceReplace(0, 2), sources=[0, 1, 2]),
        )
        self.assertEqual(fold_surface(rows).nodes, (3,))

    def test_replace_requires_every_shadowed_source(self):
        rows = (
            event(0, "user/message", op="append"),
            event(1, "assistant/message", op="append", sources=[]),
            event(2, "assistant/message", op=SurfaceReplace(0, 1), sources=[0]),
        )
        with self.assertRaisesRegex(SessionSpineError, "every shadowed"):
            fold_surface(rows)

    def test_replace_boundaries_must_be_current_and_ordered(self):
        base = [event(0, "user/message", op="append"), event(1, "assistant/message", op="append", sources=[])]
        for replacement in (SurfaceReplace(0, 9), SurfaceReplace(1, 0)):
            with self.subTest(replacement=replacement), self.assertRaises(SessionSpineError):
                fold_surface((*base, event(2, "assistant/message", op=replacement, sources=[0, 1])))

    def test_sequences_are_contiguous_from_zero(self):
        for rows in (
            (event(1, "turn/start"),),
            (event(0, "turn/start"), event(0, "turn/end")),
            (event(0, "turn/start"), event(2, "turn/end")),
        ):
            with self.subTest(rows=rows), self.assertRaisesRegex(SessionSpineError, "contiguous"):
                fold_surface(rows)

    def test_unknown_required_event_blocks_decode(self):
        raw = {"type": "plugin/custom", "seq": 0, "time_ms": 1, "data": {}}
        with self.assertRaisesRegex(SessionSpineError, "Unknown required"):
            event_from_dict(raw)

    def test_unknown_ignorable_event_is_retained_but_not_projected(self):
        raw = {"type": "plugin/custom", "seq": 0, "time_ms": 1, "data": {"note": "safe"}, "ignorable": True}
        decoded = event_from_dict(raw)
        snapshot = fold_surface((decoded, event(1, "user/message", op="append")))
        self.assertEqual(snapshot.nodes, (1,))
        self.assertEqual(decoded.to_dict(), raw)

    def test_unknown_event_cannot_smuggle_surface_metadata(self):
        raw = {"type": "plugin/custom", "seq": 0, "time_ms": 1, "data": {}, "ignorable": True,
               "surface_op": "append"}
        with self.assertRaisesRegex(SessionSpineError, "cannot change"):
            event_from_dict(raw)

    def test_log_only_event_cannot_change_surface(self):
        with self.assertRaisesRegex(SessionSpineError, "Log-only"):
            event(0, "turn/start", op="append")

    def test_surface_event_requires_explicit_operation(self):
        with self.assertRaisesRegex(SessionSpineError, "require an append"):
            event(0, "user/message")

    def test_source_references_are_prior_unique_and_increasing(self):
        for sources in ([2], [0, 0], [1, 0]):
            with self.subTest(sources=sources), self.assertRaises(SessionSpineError):
                event(2, "assistant/message", op="append", sources=sources)

    def test_source_references_are_bounded_before_materializing_an_untrusted_iterable(self):
        sources = (value for value in range(MAX_SOURCE_EVENT_REFS + 1))
        with self.assertRaisesRegex(SessionSpineError, "exceed"):
            event(MAX_SOURCE_EVENT_REFS + 1, "assistant/message", op="append", sources=sources)

    def test_only_assistant_message_may_have_known_empty_sources(self):
        self.assertEqual(event(0, "assistant/message", op="append", sources=[]).source_event_seqs, ())
        for event_type in ("user/message", "tool/result"):
            with self.subTest(event_type=event_type), self.assertRaisesRegex(SessionSpineError, "known-empty"):
                event(0, event_type, op="append", sources=[])

    def test_data_is_canonical_detached_and_fingerprint_stable(self):
        source = {"nested": {"z": 2, "a": [1, 2]}, "text": "Привет"}
        first = event(0, "turn/start", data=source)
        source["nested"]["z"] = 9
        detached = first.data
        detached["nested"]["z"] = 8
        self.assertEqual(first.data["nested"]["z"], 2)
        second = event(0, "turn/start", data={"text": "Привет", "nested": {"a": [1, 2], "z": 2}})
        self.assertEqual(first.data_json, second.data_json)
        self.assertEqual(fold_surface((first,)).fingerprint, fold_surface((second,)).fingerprint)

    def test_invalid_json_numbers_and_oversized_data_fail_closed(self):
        with self.assertRaisesRegex(SessionSpineError, "lossless JSON"):
            event(0, "turn/start", data={"value": math.nan})
        with self.assertRaisesRegex(SessionSpineError, "exceeds"):
            event(0, "turn/start", data={"value": "x" * (65 * 1024)})

    def test_wire_schema_rejects_unknown_fields_and_non_array_sources(self):
        base = {"type": "assistant/message", "seq": 0, "time_ms": 1, "data": {}, "surface_op": "append"}
        with self.assertRaisesRegex(SessionSpineError, "closed pilot schema"):
            event_from_dict(base | {"execute": True})
        with self.assertRaisesRegex(SessionSpineError, "array on the wire"):
            event_from_dict(base | {"source_event_seqs": (0,)})

    def test_snapshot_is_deterministic_and_input_list_is_unchanged(self):
        rows = [event(0, "user/message", op="append"), event(1, "assistant/message", op="append", sources=[])]
        before = deepcopy([row.to_dict() for row in rows])
        self.assertEqual(fold_surface(rows), fold_surface(tuple(rows)))
        self.assertEqual([row.to_dict() for row in rows], before)
