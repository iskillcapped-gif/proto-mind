"""Pure append-only session surface contract for future Proto-Mind integration.

This pilot has no storage or execution path. It validates detached events and
folds their append/replace surface operations without mutating the event log.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from itertools import islice
import json
import re
from typing import Any, Iterable, Mapping


SCHEMA = "proto_mind.session_spine.v1"
MAX_EVENT_DATA_BYTES = 64 * 1024
MAX_SOURCE_EVENT_REFS = 4096
EVENT_TYPE = re.compile(r"^[a-z][a-z0-9_-]{0,39}/[a-z][a-z0-9_-]{0,39}$")

SURFACE_EVENT_TYPES = frozenset({"user/message", "assistant/message", "tool/result"})
LOG_EVENT_TYPES = frozenset({
    "turn/start",
    "turn/end",
    "tool/call",
    "assistant/chunk",
    "reasoning/chunk",
    "usage/recorded",
    "session/error",
})
KNOWN_EVENT_TYPES = SURFACE_EVENT_TYPES | LOG_EVENT_TYPES


class SessionSpineError(ValueError):
    """The event log cannot be replayed without guessing."""


def _integer(value: object, label: str) -> int:
    if type(value) is not int or value < 0:
        raise SessionSpineError(f"{label} must be a non-negative integer.")
    return value


def _canonical_data(value: object) -> str:
    if not isinstance(value, Mapping):
        raise SessionSpineError("Event data must be a JSON object.")
    try:
        encoded = json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError):
        raise SessionSpineError("Event data must be lossless JSON.") from None
    if len(encoded.encode("utf-8")) > MAX_EVENT_DATA_BYTES:
        raise SessionSpineError("Event data exceeds the bounded pilot contract.")
    return encoded


def _bounded_sources(values: Iterable[int] | None) -> tuple[int, ...] | None:
    if values is None:
        return None
    sources = tuple(islice(values, MAX_SOURCE_EVENT_REFS + 1))
    if len(sources) > MAX_SOURCE_EVENT_REFS:
        raise SessionSpineError("Source event sequences exceed the bounded pilot contract.")
    return sources


@dataclass(frozen=True)
class SurfaceReplace:
    start: int
    end: int

    def __post_init__(self) -> None:
        _integer(self.start, "Replacement start")
        _integer(self.end, "Replacement end")

    def to_dict(self) -> dict[str, int | str]:
        return {"op": "replace", "start": self.start, "end": self.end}


@dataclass(frozen=True)
class SessionEvent:
    seq: int
    time_ms: int
    event_type: str
    data_json: str
    ignorable: bool = False
    surface_op: str | SurfaceReplace | None = None
    source_event_seqs: tuple[int, ...] | None = None

    def __post_init__(self) -> None:
        _integer(self.seq, "Event sequence")
        _integer(self.time_ms, "Event time")
        if not isinstance(self.event_type, str) or not EVENT_TYPE.fullmatch(self.event_type):
            raise SessionSpineError("Event type is invalid.")
        if type(self.ignorable) is not bool:
            raise SessionSpineError("Event ignorable marker must be boolean.")
        try:
            canonical = _canonical_data(json.loads(self.data_json))
        except (json.JSONDecodeError, TypeError):
            raise SessionSpineError("Event data encoding is invalid.") from None
        if canonical != self.data_json:
            raise SessionSpineError("Event data must use canonical JSON encoding.")

        sources = self.source_event_seqs
        if sources is not None:
            if not isinstance(sources, tuple) or any(type(value) is not int for value in sources):
                raise SessionSpineError("Source event sequences must be an immutable integer tuple.")
            if len(sources) > MAX_SOURCE_EVENT_REFS:
                raise SessionSpineError("Source event sequences exceed the bounded pilot contract.")
            if any(value < 0 or value >= self.seq for value in sources):
                raise SessionSpineError("Source event sequences must reference earlier events.")
            if tuple(sorted(set(sources))) != sources:
                raise SessionSpineError("Source event sequences must be unique and increasing.")

        if self.event_type not in KNOWN_EVENT_TYPES:
            if not self.ignorable:
                raise SessionSpineError("Unknown required event blocks replay.")
            if self.surface_op is not None or sources is not None:
                raise SessionSpineError("Unknown informational events cannot change the surface.")
            return

        if self.event_type in SURFACE_EVENT_TYPES:
            if self.surface_op != "append" and not isinstance(self.surface_op, SurfaceReplace):
                raise SessionSpineError("Surface events require an append or replace operation.")
            if isinstance(self.surface_op, SurfaceReplace) and sources is None:
                raise SessionSpineError("Replacement events must cite their source events.")
            if sources == () and self.event_type != "assistant/message":
                raise SessionSpineError("Only an assistant message may cite a known-empty source stream.")
        elif self.surface_op is not None or sources is not None:
            raise SessionSpineError("Log-only events cannot carry surface metadata.")

    @property
    def data(self) -> dict[str, Any]:
        return json.loads(self.data_json)

    @classmethod
    def create(
        cls,
        seq: int,
        time_ms: int,
        event_type: str,
        data: Mapping[str, Any],
        *,
        ignorable: bool = False,
        surface_op: str | SurfaceReplace | None = None,
        source_event_seqs: Iterable[int] | None = None,
    ) -> "SessionEvent":
        sources = _bounded_sources(source_event_seqs)
        return cls(seq, time_ms, event_type, _canonical_data(data), ignorable, surface_op, sources)

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "type": self.event_type,
            "seq": self.seq,
            "time_ms": self.time_ms,
            "data": self.data,
        }
        if self.ignorable:
            result["ignorable"] = True
        if self.surface_op == "append":
            result["surface_op"] = "append"
        elif isinstance(self.surface_op, SurfaceReplace):
            result["surface_op"] = self.surface_op.to_dict()
        if self.source_event_seqs is not None:
            result["source_event_seqs"] = list(self.source_event_seqs)
        return result


@dataclass(frozen=True)
class SurfaceReplacement:
    event_seq: int
    start: int
    end: int
    shadowed_seqs: tuple[int, ...]


@dataclass(frozen=True)
class SurfaceSnapshot:
    nodes: tuple[int, ...]
    replacements: tuple[SurfaceReplacement, ...]
    event_count: int
    fingerprint: str
    schema: str = SCHEMA


def event_from_dict(value: object) -> SessionEvent:
    if not isinstance(value, dict):
        raise SessionSpineError("Session event must be an object.")
    allowed = {"type", "seq", "time_ms", "data", "ignorable", "surface_op", "source_event_seqs"}
    if set(value) - allowed or not {"type", "seq", "time_ms", "data"}.issubset(value):
        raise SessionSpineError("Session event fields do not match the closed pilot schema.")
    op = value.get("surface_op")
    if isinstance(op, dict):
        if set(op) != {"op", "start", "end"} or op.get("op") != "replace":
            raise SessionSpineError("Replacement operation is invalid.")
        op = SurfaceReplace(_integer(op["start"], "Replacement start"), _integer(op["end"], "Replacement end"))
    elif op not in {None, "append"}:
        raise SessionSpineError("Surface operation is invalid.")
    sources = value.get("source_event_seqs")
    if sources is not None and not isinstance(sources, list):
        raise SessionSpineError("Source event sequences must be an array on the wire.")
    return SessionEvent.create(
        _integer(value["seq"], "Event sequence"),
        _integer(value["time_ms"], "Event time"),
        value["type"],
        value["data"],
        ignorable=value.get("ignorable", False),
        surface_op=op,
        source_event_seqs=sources,
    )


def fold_surface(events: Iterable[SessionEvent]) -> SurfaceSnapshot:
    """Replay one complete log from seq 0 and return a detached surface."""
    rows = tuple(events)
    nodes: list[int] = []
    replacements: list[SurfaceReplacement] = []
    canonical: list[dict[str, Any]] = []

    for expected, event in enumerate(rows):
        if not isinstance(event, SessionEvent):
            raise SessionSpineError("Surface replay accepts validated SessionEvent values only.")
        if event.seq != expected:
            raise SessionSpineError("Session event sequences must be contiguous from zero.")
        canonical.append(event.to_dict())
        if event.event_type not in SURFACE_EVENT_TYPES:
            continue
        if event.surface_op == "append":
            nodes.append(event.seq)
            continue

        replacement = event.surface_op
        if not isinstance(replacement, SurfaceReplace):
            raise SessionSpineError("Validated surface event lost its operation.")
        try:
            start_index = nodes.index(replacement.start)
            end_index = nodes.index(replacement.end)
        except ValueError:
            raise SessionSpineError("Replacement boundaries are not on the current surface.") from None
        if end_index < start_index:
            raise SessionSpineError("Replacement boundaries are reversed on the current surface.")
        shadowed = tuple(nodes[start_index : end_index + 1])
        if not set(shadowed).issubset(set(event.source_event_seqs or ())):
            raise SessionSpineError("Replacement provenance does not cite every shadowed surface event.")
        nodes[start_index : end_index + 1] = [event.seq]
        replacements.append(SurfaceReplacement(event.seq, replacement.start, replacement.end, shadowed))

    payload = json.dumps(
        {"schema": SCHEMA, "events": canonical},
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return SurfaceSnapshot(tuple(nodes), tuple(replacements), len(rows), hashlib.sha256(payload).hexdigest())


def visible_events(events: Iterable[SessionEvent]) -> tuple[SessionEvent, ...]:
    rows = tuple(events)
    snapshot = fold_surface(rows)
    by_seq = {event.seq: event for event in rows}
    return tuple(by_seq[seq] for seq in snapshot.nodes)
