"""Pure ordered multi-turn composition for explicit copied Native fixtures.

The caller supplies immutable fixture bytes plus their exact SHA-256 order. This
module does not discover history, open paths, write a store, or infer ordering.
It revalidates every turn through P1, rebases only sequence references, then
uses the P2a builder and parser to prove one detached candidate image.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import re
from typing import Any
from uuid import UUID

from proto_mind.native_session_spine import NativeTurnProjection
from proto_mind.session_spine import (
    SessionEvent,
    SessionSpineError,
    SurfaceReplace,
    SurfaceSnapshot,
    fold_surface,
)
from proto_mind.session_spine_store import (
    FORMAT_VERSION as STORE_FORMAT_VERSION,
    STORE_SCHEMA,
    SessionSpineStoreError,
    build_store_image,
    inspect_store_image,
)
from proto_mind.session_spine_transfer import (
    FIXTURE_SCHEMA,
    MAX_FIXTURE_BYTES,
    SessionSpineTransferError,
    project_native_fixture,
)


SCHEMA = "proto_mind.session_spine_composition_preview.v1"
ORDER_SCHEMA = "proto_mind.session_spine_composition_order.v1"
FORMAT_VERSION = 1
MIN_TURNS = 2
MAX_TURNS = 64
MAX_TOTAL_FIXTURE_BYTES = 16 * 1024 * 1024
HASH = re.compile(r"^[0-9a-f]{64}$")


class SessionSpineCompositionError(RuntimeError):
    """Explicit fixtures cannot be combined without guessing or widening authority."""


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError):
        raise SessionSpineCompositionError("Composition evidence is not lossless JSON.") from None


def _canonical_uuid(value: object, label: str) -> str:
    try:
        result = str(UUID(str(value)))
    except (ValueError, TypeError, AttributeError):
        raise SessionSpineCompositionError(f"{label} is invalid.") from None
    if result != value:
        raise SessionSpineCompositionError(f"{label} must use canonical lowercase UUID text.")
    return result


def _message_id(projection: NativeTurnProjection, sequence: int | None, label: str) -> str | None:
    if sequence is None:
        return None
    try:
        event = projection.events[sequence]
    except IndexError:
        raise SessionSpineCompositionError(f"{label} is outside its source turn.") from None
    value = event.data.get("native_message_id")
    return _canonical_uuid(value, label)


def _event_payload_sha256(events: tuple[SessionEvent, ...]) -> str:
    payload = [
        {
            "type": event.event_type,
            "time_ms": event.time_ms,
            "data_json": event.data_json,
            "ignorable": event.ignorable,
        }
        for event in events
    ]
    return hashlib.sha256(_canonical(payload)).hexdigest()


def rebase_session_event(event: SessionEvent, offset: int) -> SessionEvent:
    """Return one sequence-rebased event without changing its canonical data."""
    if not isinstance(event, SessionEvent) or type(offset) is not int or offset < 0:
        raise SessionSpineCompositionError("Event rebasing requires a validated event and non-negative offset.")
    operation = event.surface_op
    if isinstance(operation, SurfaceReplace):
        operation = SurfaceReplace(operation.start + offset, operation.end + offset)
    sources = None
    if event.source_event_seqs is not None:
        sources = tuple(sequence + offset for sequence in event.source_event_seqs)
    try:
        return SessionEvent(
            seq=event.seq + offset,
            time_ms=event.time_ms,
            event_type=event.event_type,
            data_json=event.data_json,
            ignorable=event.ignorable,
            surface_op=operation,
            source_event_seqs=sources,
        )
    except SessionSpineError as error:
        raise SessionSpineCompositionError(f"Rebased Session Spine event is invalid: {error}") from None


@dataclass(frozen=True)
class CompositionTurnLineage:
    ordinal: int
    fixture_sha256: str
    fixture_bytes: int
    run_id: str
    run_fingerprint: str
    display_status: str
    source_event_start: int
    source_event_end: int
    rebased_event_start: int
    rebased_event_end: int
    source_surface_nodes: tuple[int, ...]
    rebased_surface_nodes: tuple[int, ...]
    source_surface_fingerprint: str
    event_payload_sha256: str
    input_sha256: str
    displayed_answer_sha256: str | None
    raw_answer_sha256: str | None
    work_log_sha256: str
    memory_candidate_ids: tuple[str, ...]
    source_tool_event_seqs: tuple[int, ...]
    rebased_tool_event_seqs: tuple[int, ...]
    source_user_message_seq: int
    rebased_user_message_seq: int
    source_assistant_message_seq: int | None
    rebased_assistant_message_seq: int | None
    start_ms: int
    end_ms: int
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "ordinal": self.ordinal,
            "fixture": {
                "schema": FIXTURE_SCHEMA,
                "sha256": self.fixture_sha256,
                "bytes": self.fixture_bytes,
            },
            "source": {
                "run_id": self.run_id,
                "run_fingerprint": self.run_fingerprint,
                "display_status": self.display_status,
                "event_range": [self.source_event_start, self.source_event_end],
                "surface_nodes": list(self.source_surface_nodes),
                "surface_fingerprint": self.source_surface_fingerprint,
                "event_payload_sha256": self.event_payload_sha256,
                "user_message_seq": self.source_user_message_seq,
                "assistant_message_seq": self.source_assistant_message_seq,
                "tool_event_seqs": list(self.source_tool_event_seqs),
                "start_ms": self.start_ms,
                "end_ms": self.end_ms,
            },
            "rebased": {
                "event_range": [self.rebased_event_start, self.rebased_event_end],
                "surface_nodes": list(self.rebased_surface_nodes),
                "user_message_seq": self.rebased_user_message_seq,
                "assistant_message_seq": self.rebased_assistant_message_seq,
                "tool_event_seqs": list(self.rebased_tool_event_seqs),
            },
            "content": {
                "input_sha256": self.input_sha256,
                "displayed_answer_sha256": self.displayed_answer_sha256,
                "raw_answer_sha256": self.raw_answer_sha256,
                "work_log_sha256": self.work_log_sha256,
                "memory_candidate_ids": list(self.memory_candidate_ids),
                "preserved": True,
            },
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True)
class SessionSpineCompositionPreview:
    session_id: str
    owner_id: str
    created_ms: int
    order_manifest_sha256: str
    turns: tuple[CompositionTurnLineage, ...]
    surface: SurfaceSnapshot
    candidate_sha256: str
    candidate_bytes: int
    _fixture_raws: tuple[bytes, ...] = field(repr=False)
    _events: tuple[SessionEvent, ...] = field(repr=False)
    _candidate_raw: bytes = field(repr=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": SCHEMA,
            "format_version": FORMAT_VERSION,
            "read_only": True,
            "no_file_access": True,
            "no_write": True,
            "execute": False,
            "fixture_only": True,
            "personal_archive_scanned": False,
            "archive_pairing_inferred": False,
            "ordering": {
                "mode": "caller_bound_sha256_manifest",
                "inferred": False,
                "manifest_schema": ORDER_SCHEMA,
                "manifest_sha256": self.order_manifest_sha256,
                "fixture_sha256": [turn.fixture_sha256 for turn in self.turns],
            },
            "session_id": self.session_id,
            "owner_id": self.owner_id,
            "created_ms": self.created_ms,
            "composition": {
                "turn_count": len(self.turns),
                "event_count": len(self._events),
                "surface_nodes": list(self.surface.nodes),
                "surface_fingerprint": self.surface.fingerprint,
                "sequence_rebase_only": True,
                "source_identity_rewritten": False,
                "exact_event_parity": True,
                "task_success_inferred": False,
            },
            "turns": [turn.to_dict() for turn in self.turns],
            "candidate": {
                "store_schema": STORE_SCHEMA,
                "store_format_version": STORE_FORMAT_VERSION,
                "sha256": self.candidate_sha256,
                "bytes": self.candidate_bytes,
                "exact_replay_parity": True,
                "contains_exact_source_content": True,
                "safe_to_publish": False,
            },
            "authority": {
                "store_authoritative": False,
                "apply_installed": False,
                "restore_installed": False,
                "delete_installed": False,
                "compaction_installed": False,
                "production_caller_installed": False,
                "separate_checkpoint_required": True,
            },
        }


def _validate_projection(
    projection: NativeTurnProjection,
    *,
    conversation_id: str,
    previous_end_ms: int | None,
) -> tuple[int, int, str, str | None]:
    events = projection.events
    if (
        len(events) < 2
        or events[0].event_type != "turn/start"
        or events[-1].event_type != "turn/end"
        or any(event.event_type == "turn/start" for event in events[1:])
        or any(event.event_type == "turn/end" for event in events[:-1])
    ):
        raise SessionSpineCompositionError("Each explicit fixture must project exactly one closed turn.")
    if events[0].data.get("conversation_id") != conversation_id:
        raise SessionSpineCompositionError("Explicit fixtures do not share the expected conversation ID.")
    start_ms = events[0].time_ms
    end_ms = events[-1].time_ms
    if any(event.time_ms < start_ms or event.time_ms > end_ms for event in events):
        raise SessionSpineCompositionError("A fixture event falls outside its explicit turn boundary.")
    if previous_end_ms is not None and start_ms <= previous_end_ms:
        raise SessionSpineCompositionError(
            "Explicit fixture order overlaps or is not strictly later; composition will not sort or guess."
        )
    user_id = _message_id(projection, projection.user_message_seq, "Native user message ID")
    assistant_id = _message_id(projection, projection.assistant_message_seq, "Native assistant message ID")
    if user_id is None:
        raise SessionSpineCompositionError("Native fixture has no projected user message identity.")
    return start_ms, end_ms, user_id, assistant_id


def compose_native_fixtures(
    fixture_raws: tuple[bytes, ...],
    *,
    expected_order: tuple[str, ...],
    expected_conversation_id: str,
    owner_id: str,
) -> SessionSpineCompositionPreview:
    """Compose caller-bound fixture bytes into one detached P2a candidate image."""
    if type(fixture_raws) is not tuple or type(expected_order) is not tuple:
        raise SessionSpineCompositionError("Fixtures and their order manifest must be immutable tuples.")
    if not MIN_TURNS <= len(fixture_raws) <= MAX_TURNS:
        raise SessionSpineCompositionError("Multi-turn composition requires two to 64 explicit fixtures.")
    if len(expected_order) != len(fixture_raws):
        raise SessionSpineCompositionError("Fixture count does not match the explicit order manifest.")
    if any(not isinstance(value, str) or not HASH.fullmatch(value) for value in expected_order):
        raise SessionSpineCompositionError("Order manifest entries must be lowercase SHA-256 digests.")
    if len(set(expected_order)) != len(expected_order):
        raise SessionSpineCompositionError("Order manifest contains duplicate fixture digests.")
    if any(type(raw) is not bytes or not raw or len(raw) > MAX_FIXTURE_BYTES for raw in fixture_raws):
        raise SessionSpineCompositionError("Every fixture must be bounded immutable canonical bytes.")
    if sum(len(raw) for raw in fixture_raws) > MAX_TOTAL_FIXTURE_BYTES:
        raise SessionSpineCompositionError("Explicit fixture set exceeds the composition byte boundary.")

    session_id = _canonical_uuid(expected_conversation_id, "Expected conversation ID")
    projections: list[NativeTurnProjection] = []
    for ordinal, (raw, expected_hash) in enumerate(zip(fixture_raws, expected_order, strict=True)):
        actual_hash = hashlib.sha256(raw).hexdigest()
        if actual_hash != expected_hash:
            raise SessionSpineCompositionError(f"Fixture {ordinal} does not match its explicit order digest.")
        try:
            projections.append(project_native_fixture(raw))
        except SessionSpineTransferError as error:
            raise SessionSpineCompositionError(f"Fixture {ordinal} failed detached P1 validation: {error}") from None

    rows: list[SessionEvent] = []
    turns: list[CompositionTurnLineage] = []
    expected_surface_nodes: list[int] = []
    run_ids: set[str] = set()
    message_ids: set[str] = set()
    previous_end_ms: int | None = None
    for ordinal, (raw, fixture_hash, projection) in enumerate(
        zip(fixture_raws, expected_order, projections, strict=True)
    ):
        start_ms, end_ms, user_id, assistant_id = _validate_projection(
            projection,
            conversation_id=session_id,
            previous_end_ms=previous_end_ms,
        )
        if projection.run_id in run_ids:
            raise SessionSpineCompositionError("Explicit fixtures reuse a Native run ID.")
        run_ids.add(projection.run_id)
        current_ids = {user_id} if assistant_id is None else {user_id, assistant_id}
        if len(current_ids) != (1 if assistant_id is None else 2) or message_ids.intersection(current_ids):
            raise SessionSpineCompositionError("Explicit fixtures reuse a Native message ID.")
        message_ids.update(current_ids)

        offset = len(rows)
        rebased = tuple(rebase_session_event(event, offset) for event in projection.events)
        payload_sha256 = _event_payload_sha256(projection.events)
        if _event_payload_sha256(rebased) != payload_sha256:
            raise SessionSpineCompositionError("Sequence rebasing changed canonical source event payloads.")
        rows.extend(rebased)
        rebased_surface = tuple(sequence + offset for sequence in projection.surface.nodes)
        expected_surface_nodes.extend(rebased_surface)
        turns.append(CompositionTurnLineage(
            ordinal=ordinal,
            fixture_sha256=fixture_hash,
            fixture_bytes=len(raw),
            run_id=projection.run_id,
            run_fingerprint=projection.run_fingerprint,
            display_status=projection.display_status,
            source_event_start=0,
            source_event_end=len(projection.events) - 1,
            rebased_event_start=offset,
            rebased_event_end=offset + len(projection.events) - 1,
            source_surface_nodes=projection.surface.nodes,
            rebased_surface_nodes=rebased_surface,
            source_surface_fingerprint=projection.surface.fingerprint,
            event_payload_sha256=payload_sha256,
            input_sha256=projection.input_sha256,
            displayed_answer_sha256=projection.displayed_answer_sha256,
            raw_answer_sha256=projection.raw_answer_sha256,
            work_log_sha256=projection.work_log_sha256,
            memory_candidate_ids=projection.memory_candidate_ids,
            source_tool_event_seqs=projection.tool_event_seqs,
            rebased_tool_event_seqs=tuple(sequence + offset for sequence in projection.tool_event_seqs),
            source_user_message_seq=projection.user_message_seq,
            rebased_user_message_seq=projection.user_message_seq + offset,
            source_assistant_message_seq=projection.assistant_message_seq,
            rebased_assistant_message_seq=(
                None if projection.assistant_message_seq is None else projection.assistant_message_seq + offset
            ),
            start_ms=start_ms,
            end_ms=end_ms,
            warnings=projection.warnings,
        ))
        previous_end_ms = end_ms

    events = tuple(rows)
    try:
        surface = fold_surface(events)
    except SessionSpineError as error:
        raise SessionSpineCompositionError(f"Composed Session Spine surface does not replay: {error}") from None
    if surface.nodes != tuple(expected_surface_nodes):
        raise SessionSpineCompositionError("Composed surface does not preserve per-turn P1 visibility.")
    created_ms = events[0].time_ms
    try:
        candidate = build_store_image(
            session_id=session_id,
            created_ms=created_ms,
            owner_id=owner_id,
            events=events,
        )
        snapshot = inspect_store_image(candidate, session_id)
    except SessionSpineStoreError as error:
        raise SessionSpineCompositionError(f"Composed P2a candidate cannot be built or replayed: {error}") from None
    if snapshot.events != events or snapshot.surface != surface or snapshot.recovery_state != "closed":
        raise SessionSpineCompositionError("Composed candidate does not have exact closed replay parity.")

    order_manifest = {
        "schema": ORDER_SCHEMA,
        "conversation_id": session_id,
        "fixture_sha256": list(expected_order),
    }
    return SessionSpineCompositionPreview(
        session_id=session_id,
        owner_id=owner_id,
        created_ms=created_ms,
        order_manifest_sha256=hashlib.sha256(_canonical(order_manifest)).hexdigest(),
        turns=tuple(turns),
        surface=surface,
        candidate_sha256=hashlib.sha256(candidate).hexdigest(),
        candidate_bytes=len(candidate),
        _fixture_raws=fixture_raws,
        _events=events,
        _candidate_raw=candidate,
    )
