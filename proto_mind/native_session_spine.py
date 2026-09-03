"""Pure projection of one validated Native turn into the Session Spine.

The caller supplies already-loaded chat messages and an inspected work-session
view. This module never opens a path, writes an event, dispatches a command, or
reconciles an archive by guesswork.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
import re
from typing import Any, Mapping, Sequence
from uuid import UUID

from proto_mind.native_progress import display_text
from proto_mind.native_work_sessions import public_tool, public_work_log
from proto_mind.session_spine import SessionEvent, SurfaceSnapshot, fold_surface


SCHEMA = "proto_mind.native_session_spine_projection.v1"
SOURCE_SCHEMA = "proto_mind.native_work_session.v1"
SUGGESTION_SCHEMA = "proto_mind.native_memory_suggestions.v1"
SUGGESTION_ALGORITHM = "explicit_operator_statements_v1"
CONTENT_ENCODING = "utf8_chunks_v1"
MAX_INPUT_CHARS = 32_000
MAX_ANSWER_CHARS = 200_000
TEXT_CHUNK_CHARS = 8_000
MAX_TOOLS = 64
MAX_SUGGESTIONS = 2
HASH = re.compile(r"^[0-9a-f]{64}$")
STABLE_DISPLAY_STATES = frozenset({"completed", "unknown", "not_started"})
SUGGESTION_KINDS = frozenset({"preference", "decision", "project_fact", "constraint", "lesson"})


class NativeSessionProjectionError(ValueError):
    """Native evidence cannot be projected without guessing or widening it."""


def _object(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise NativeSessionProjectionError(f"{label} must be an object.")
    return dict(value)


def _uuid(value: object, label: str) -> str:
    try:
        return str(UUID(str(value)))
    except (ValueError, TypeError, AttributeError):
        raise NativeSessionProjectionError(f"{label} is invalid.") from None


def _digest(value: object, label: str) -> str:
    if not isinstance(value, str) or not HASH.fullmatch(value):
        raise NativeSessionProjectionError(f"{label} must be a lowercase SHA-256 digest.")
    return value


def _text(value: object, label: str, limit: int, *, empty: bool = False) -> str:
    if not isinstance(value, str) or len(value) > limit or (not empty and not value):
        raise NativeSessionProjectionError(f"{label} is missing or exceeds its source boundary.")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        raise NativeSessionProjectionError(f"{label} is not valid UTF-8 text.") from None
    return value


def _timestamp_ms(value: object, label: str) -> int:
    if not isinstance(value, str):
        raise NativeSessionProjectionError(f"{label} is missing.")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError()
        result = int(parsed.timestamp() * 1000)
        if result < 0:
            raise ValueError()
        return result
    except ValueError:
        raise NativeSessionProjectionError(f"{label} is invalid.") from None


def _canonical_hash(value: object) -> str:
    try:
        data = json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(data.encode("utf-8")).hexdigest()
    except (TypeError, ValueError, UnicodeEncodeError):
        raise NativeSessionProjectionError("Native evidence is not lossless JSON.") from None


def _message(value: object, role: str) -> tuple[dict[str, Any], str]:
    message = _object(value, f"Native {role} message")
    if message.get("role") != role or message.get("isError", False) is not False:
        raise NativeSessionProjectionError(f"Native {role} message has the wrong role or error state.")
    if message.get("operatorInput") is True:
        raise NativeSessionProjectionError("Operator routes are not cognitive Native turns.")
    return message, _uuid(message.get("id"), f"Native {role} message ID")


def _validate_run(
    value: object,
    *,
    conversation_id: str,
    input_text: str,
    raw_answer: str | None,
) -> tuple[dict[str, Any], int, int]:
    run = _object(value, "Native work-session view")
    if run.get("schema") != SOURCE_SCHEMA:
        raise NativeSessionProjectionError("Unsupported Native work-session schema.")
    run_id = _uuid(run.get("id"), "Native run ID")
    if run_id != str(run.get("id")) or _uuid(run.get("conversation_id"), "Native conversation ID") != conversation_id:
        raise NativeSessionProjectionError("Native run identity does not match the selected conversation.")
    _digest(run.get("fingerprint"), "Native run fingerprint")
    if run.get("automatic_resume") is not False:
        raise NativeSessionProjectionError("Native run view may not restore automatic execution authority.")

    status = run.get("status")
    display_status = run.get("display_status")
    if status not in {"prepared", "dispatching", "completed", "interrupted", "error"}:
        raise NativeSessionProjectionError("Native run status is invalid.")
    if display_status not in STABLE_DISPLAY_STATES:
        raise NativeSessionProjectionError("Live preparing/running evidence is not a stable projection source.")
    if status == "completed" and display_status != "completed":
        raise NativeSessionProjectionError("A completed Native run must remain completed in its inspected view.")
    if display_status == "completed" and status != "completed":
        raise NativeSessionProjectionError("Native display state invents completion.")
    dispatched = isinstance(run.get("dispatched_at"), str)
    if display_status == "unknown" and not dispatched:
        raise NativeSessionProjectionError("Unknown Native work must have crossed a dispatch boundary.")
    if display_status == "not_started" and dispatched:
        raise NativeSessionProjectionError("A dispatched Native run cannot be projected as not started.")

    expected_input_hash = hashlib.sha256(input_text.encode("utf-8")).hexdigest()
    if (run.get("input_sha256") != expected_input_hash
            or type(run.get("input_chars")) is not int
            or run["input_chars"] != len(input_text)
            or run.get("input_preview") != display_text(input_text, 800)):
        raise NativeSessionProjectionError("Exact Native operator input does not match the work-session evidence.")

    tools = run.get("tools")
    if not isinstance(tools, list) or len(tools) > MAX_TOOLS:
        raise NativeSessionProjectionError("Native tool evidence is invalid or unbounded.")
    for item in tools:
        tool = _object(item, "Native tool evidence")
        if public_tool(tool) != tool:
            raise NativeSessionProjectionError("Native tool evidence contains unknown or private fields.")
    work_log = run.get("work_log")
    if not isinstance(work_log, dict) or public_work_log(work_log) != work_log:
        raise NativeSessionProjectionError("Native public work log contains unknown or private fields.")
    for field in ("network_access_performed", "computer_use_performed", "screen_access_performed"):
        if type(run.get(field)) is not bool:
            raise NativeSessionProjectionError(f"Native {field} must be explicit.")
    if "execution_may_have_occurred" in run and type(run["execution_may_have_occurred"]) is not bool:
        raise NativeSessionProjectionError("Native execution uncertainty must be explicit.")
    if not isinstance(run.get("verification"), str) or not isinstance(run.get("acceptance"), str):
        raise NativeSessionProjectionError("Native verification and acceptance evidence must be explicit strings.")

    created_ms = _timestamp_ms(run.get("created_at"), "Native created_at")
    terminal_ms = _timestamp_ms(run.get("finished_at", run.get("updated_at")), "Native terminal timestamp")
    if terminal_ms < created_ms:
        raise NativeSessionProjectionError("Native terminal timestamp precedes creation.")
    if status == "completed":
        if raw_answer is None or run.get("answer_preview") != display_text(raw_answer, 1600):
            raise NativeSessionProjectionError("Completed Native answer does not match work-session evidence.")
    elif raw_answer is not None:
        raise NativeSessionProjectionError("Incomplete Native work cannot acquire an assistant answer.")
    return run, created_ms, terminal_ms


def _memory_lineage(
    assistant: Mapping[str, Any],
    *,
    user_message_id: str,
    input_text: str,
    run: Mapping[str, Any],
) -> tuple[dict[str, Any] | None, tuple[str, ...]]:
    report_value = assistant.get("memorySuggestions")
    source_message = assistant.get("memorySuggestionSourceID")
    if report_value is None:
        if source_message is not None:
            raise NativeSessionProjectionError("Memory suggestion source exists without a report.")
        return None, ()
    if _uuid(source_message, "Memory suggestion source message ID") != user_message_id:
        raise NativeSessionProjectionError("Memory suggestions do not point to the projected operator message.")
    report = _object(report_value, "Memory suggestions")
    expected_fields = {
        "schema", "algorithm", "source", "state", "reason", "candidates", "omitted_count",
        "read_only", "model_call_performed", "automatic_save", "permission_granted",
    }
    if set(report) != expected_fields or report.get("schema") != SUGGESTION_SCHEMA or report.get("algorithm") != SUGGESTION_ALGORITHM:
        raise NativeSessionProjectionError("Memory suggestion report schema is not the accepted Native contract.")
    if (report.get("read_only") is not True or report.get("model_call_performed") is not False
            or report.get("automatic_save") is not False or report.get("permission_granted") is not False):
        raise NativeSessionProjectionError("Memory suggestion report widens its read-only authority.")
    source = _object(report.get("source"), "Memory suggestion source")
    if set(source) != {"conversation_id", "workspace", "input_sha256", "input_chars", "run_id", "fingerprint"}:
        raise NativeSessionProjectionError("Memory suggestion source schema is invalid.")
    if (_uuid(source.get("conversation_id"), "Suggestion conversation ID") != str(run["conversation_id"])
            or _uuid(source.get("run_id"), "Suggestion run ID") != str(run["id"])
            or source.get("fingerprint") != run["fingerprint"]
            or source.get("workspace") != run.get("workspace")
            or source.get("input_sha256") != run["input_sha256"]
            or type(source.get("input_chars")) is not int
            or source["input_chars"] != len(input_text)):
        raise NativeSessionProjectionError("Memory suggestions do not match the exact Native source run.")
    state = report.get("state")
    candidates = report.get("candidates")
    if (state not in {"suggested", "no_candidates", "unavailable"} or not isinstance(candidates, list)
            or len(candidates) > MAX_SUGGESTIONS or (state == "suggested") != bool(candidates)):
        raise NativeSessionProjectionError("Memory suggestion state and candidates disagree.")
    if type(report.get("omitted_count")) is not int or report["omitted_count"] < 0:
        raise NativeSessionProjectionError("Memory suggestion omitted count is invalid.")
    if not isinstance(report.get("reason"), str) or len(report["reason"]) > 160:
        raise NativeSessionProjectionError("Memory suggestion reason is invalid.")

    candidate_ids: list[str] = []
    kinds: list[str] = []
    for value in candidates:
        candidate = _object(value, "Memory suggestion candidate")
        if set(candidate) != {"id", "kind", "start", "end", "content_sha256"}:
            raise NativeSessionProjectionError("Memory suggestion candidate schema is invalid.")
        candidate_id = _digest(candidate.get("id"), "Memory suggestion candidate ID")
        kind = candidate.get("kind")
        start, end = candidate.get("start"), candidate.get("end")
        if (kind not in SUGGESTION_KINDS or type(start) is not int or type(end) is not int
                or not 0 <= start < end <= len(input_text)):
            raise NativeSessionProjectionError("Memory suggestion candidate bounds or kind are invalid.")
        quote_hash = hashlib.sha256(input_text[start:end].encode("utf-8")).hexdigest()
        if candidate.get("content_sha256") != quote_hash:
            raise NativeSessionProjectionError("Memory suggestion quote changed after selection.")
        material = f"{run['id']}\n{run['input_sha256']}\n{kind}\n{start}:{end}\n{quote_hash}"
        if candidate_id != hashlib.sha256(material.encode("utf-8")).hexdigest():
            raise NativeSessionProjectionError("Memory suggestion candidate ID is not source-bound.")
        candidate_ids.append(candidate_id)
        kinds.append(kind)
    return ({
        "schema": SUGGESTION_SCHEMA,
        "state": state,
        "reason": report["reason"],
        "source_message_id": user_message_id,
        "source_run_id": run["id"],
        "source_run_fingerprint": run["fingerprint"],
        "candidate_ids": candidate_ids,
        "candidate_kinds": kinds,
        "omitted_count": report["omitted_count"],
        "automatic_save": False,
    }, tuple(candidate_ids))


def _chunks(
    events: list[SessionEvent],
    *,
    event_type: str,
    stream: str,
    text: str,
    time_ms: int,
) -> tuple[tuple[int, ...], dict[str, Any]]:
    pieces = tuple(text[index:index + TEXT_CHUNK_CHARS] for index in range(0, len(text), TEXT_CHUNK_CHARS))
    if not pieces:
        raise NativeSessionProjectionError("A projected message cannot have an empty chunk stream.")
    sequences: list[int] = []
    for index, piece in enumerate(pieces):
        sequence = len(events)
        events.append(SessionEvent.create(
            sequence,
            time_ms,
            event_type,
            {
                "stream": stream,
                "part": index,
                "parts": len(pieces),
                "text": piece,
                "text_sha256": hashlib.sha256(piece.encode("utf-8")).hexdigest(),
            },
        ))
        sequences.append(sequence)
    return tuple(sequences), {
        "encoding": CONTENT_ENCODING,
        "stream": stream,
        "parts": len(pieces),
        "characters": len(text),
        "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
    }


@dataclass(frozen=True)
class NativeTurnProjection:
    events: tuple[SessionEvent, ...]
    surface: SurfaceSnapshot
    run_id: str
    run_fingerprint: str
    display_status: str
    user_message_seq: int
    assistant_message_seq: int | None
    tool_event_seqs: tuple[int, ...]
    input_sha256: str
    displayed_answer_sha256: str | None
    raw_answer_sha256: str | None
    work_log_sha256: str
    memory_candidate_ids: tuple[str, ...]
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": SCHEMA,
            "read_only": True,
            "no_file_access": True,
            "no_write": True,
            "execute": False,
            "source": {
                "run_id": self.run_id,
                "run_fingerprint": self.run_fingerprint,
                "display_status": self.display_status,
            },
            "spine": {
                "event_count": len(self.events),
                "surface_nodes": list(self.surface.nodes),
                "fingerprint": self.surface.fingerprint,
            },
            "input": {"event_seq": self.user_message_seq, "sha256": self.input_sha256, "preserved": True},
            "answer": None if self.assistant_message_seq is None else {
                "event_seq": self.assistant_message_seq,
                "displayed_sha256": self.displayed_answer_sha256,
                "raw_sha256": self.raw_answer_sha256,
                "preserved": True,
            },
            "tools": {"count": len(self.tool_event_seqs), "event_seqs": list(self.tool_event_seqs)},
            "work_log_sha256": self.work_log_sha256,
            "memory_candidate_ids": list(self.memory_candidate_ids),
            "warnings": list(self.warnings),
        }


def project_native_turn(
    *,
    conversation_id: str,
    user_message: Mapping[str, Any],
    assistant_message: Mapping[str, Any] | None,
    work_session: Mapping[str, Any],
) -> NativeTurnProjection:
    """Project one explicitly paired, already-inspected Native turn in memory."""
    conversation = _uuid(conversation_id, "Selected Native conversation ID")
    user, user_message_id = _message(user_message, "user")
    input_text = _text(user.get("text"), "Native operator input", MAX_INPUT_CHARS)
    if input_text.startswith("/"):
        raise NativeSessionProjectionError("Slash/operator routes are not cognitive Native turns.")

    assistant: dict[str, Any] | None = None
    assistant_message_id: str | None = None
    displayed_answer: str | None = None
    raw_answer: str | None = None
    if assistant_message is not None:
        assistant, assistant_message_id = _message(assistant_message, "assistant")
        displayed_answer = _text(assistant.get("text"), "Native displayed answer", MAX_ANSWER_CHARS)
        raw_value = _text(assistant.get("raw", ""), "Native raw answer", MAX_ANSWER_CHARS, empty=True)
        raw_answer = raw_value or displayed_answer

    run, created_ms, terminal_ms = _validate_run(
        work_session,
        conversation_id=conversation,
        input_text=input_text,
        raw_answer=raw_answer,
    )

    events: list[SessionEvent] = [SessionEvent.create(0, created_ms, "turn/start", {
        "projection_schema": SCHEMA,
        "source_schema": SOURCE_SCHEMA,
        "native_run_id": run["id"],
        "native_run_fingerprint": run["fingerprint"],
        "conversation_id": conversation,
        "provider": str(run.get("provider", ""))[:80],
        "access_mode": str(run.get("access_mode", ""))[:40],
        "display_status": run["display_status"],
    })]

    user_sources, user_content = _chunks(
        events, event_type="user/chunk", stream="user", text=input_text, time_ms=created_ms,
    )
    user_seq = len(events)
    events.append(SessionEvent.create(
        user_seq,
        created_ms,
        "user/message",
        {"native_message_id": user_message_id, "content": user_content, "operator_input": False},
        surface_op="append",
        source_event_seqs=user_sources,
    ))

    tool_seqs: list[int] = []
    for item in run["tools"]:
        sequence = len(events)
        events.append(SessionEvent.create(
            sequence,
            terminal_ms,
            "tool/result",
            {"native_run_id": run["id"], "evidence_only": True, "replayable": False, "tool": item},
            surface_op="append",
        ))
        tool_seqs.append(sequence)

    assistant_seq = None
    displayed_hash = raw_hash = None
    candidate_ids: tuple[str, ...] = ()
    if assistant is not None and displayed_answer is not None and raw_answer is not None:
        lineage, candidate_ids = _memory_lineage(
            assistant,
            user_message_id=user_message_id,
            input_text=input_text,
            run=run,
        )
        display_sources, display_content = _chunks(
            events, event_type="assistant/chunk", stream="display", text=displayed_answer, time_ms=terminal_ms,
        )
        if raw_answer == displayed_answer:
            raw_sources, raw_content = display_sources, {**display_content, "stream": "display"}
        else:
            raw_sources, raw_content = _chunks(
                events, event_type="assistant/chunk", stream="raw", text=raw_answer, time_ms=terminal_ms,
            )
        assistant_seq = len(events)
        events.append(SessionEvent.create(
            assistant_seq,
            terminal_ms,
            "assistant/message",
            {
                "native_message_id": assistant_message_id,
                "display_content": display_content,
                "raw_content": raw_content,
                "raw_is_display": raw_answer == displayed_answer,
                "memory_suggestions": lineage,
                "task_verification": run["verification"],
                "operator_acceptance": run["acceptance"],
            },
            surface_op="append",
            source_event_seqs=tuple(sorted(set((*tool_seqs, *display_sources, *raw_sources)))),
        ))
        displayed_hash = hashlib.sha256(displayed_answer.encode("utf-8")).hexdigest()
        raw_hash = hashlib.sha256(raw_answer.encode("utf-8")).hexdigest()
    else:
        events.append(SessionEvent.create(len(events), terminal_ms, "session/error", {
            "native_run_id": run["id"],
            "display_status": run["display_status"],
            "failure": display_text(run.get("failure"), 300),
            "execution_may_have_occurred": run.get("execution_may_have_occurred") is True,
            "no_success_inferred": True,
        }))

    outcome = "response_recorded" if run["display_status"] == "completed" else run["display_status"]
    events.append(SessionEvent.create(len(events), terminal_ms, "turn/end", {
        "native_run_id": run["id"],
        "source_status": run["status"],
        "display_status": run["display_status"],
        "outcome": outcome,
        "task_verification": run["verification"],
        "operator_acceptance": run["acceptance"],
        "tool_count": len(tool_seqs),
        "work_log_sha256": _canonical_hash(run["work_log"]),
        "work_log_entries": len(run["work_log"].get("entries", [])),
        "network_access_performed": run["network_access_performed"],
        "computer_use_performed": run["computer_use_performed"],
        "screen_access_performed": run["screen_access_performed"],
        "execution_may_have_occurred": run.get("execution_may_have_occurred") is True,
    }))
    rows = tuple(events)
    surface = fold_surface(rows)
    warnings = () if assistant_seq is not None else (
        f"Native run is {run['display_status']}; no completed assistant output was projected.",
    )
    return NativeTurnProjection(
        events=rows,
        surface=surface,
        run_id=run["id"],
        run_fingerprint=run["fingerprint"],
        display_status=run["display_status"],
        user_message_seq=user_seq,
        assistant_message_seq=assistant_seq,
        tool_event_seqs=tuple(tool_seqs),
        input_sha256=run["input_sha256"],
        displayed_answer_sha256=displayed_hash,
        raw_answer_sha256=raw_hash,
        work_log_sha256=_canonical_hash(run["work_log"]),
        memory_candidate_ids=candidate_ids,
        warnings=warnings,
    )


def materialize_message_text(
    events: Sequence[SessionEvent],
    message_seq: int,
    *,
    stream: str | None = None,
) -> str:
    """Reconstruct one projected message and verify every chunk hash and total."""
    rows = tuple(events)
    surface = fold_surface(rows)
    by_seq = {event.seq: event for event in rows}
    message = by_seq.get(message_seq)
    if message is None or message_seq not in surface.nodes or message.event_type not in {"user/message", "assistant/message"}:
        raise NativeSessionProjectionError("Projected message is missing from the current surface.")
    data = message.data
    if message.event_type == "user/message":
        selected_stream = "user"
        metadata = data.get("content")
        chunk_type = "user/chunk"
    else:
        selected_stream = stream or "display"
        if selected_stream not in {"display", "raw"}:
            raise NativeSessionProjectionError("Assistant stream must be display or raw.")
        if selected_stream == "raw" and data.get("raw_is_display") is True:
            selected_stream = "display"
        metadata = data.get("display_content" if selected_stream == "display" else "raw_content")
        chunk_type = "assistant/chunk"
    meta = _object(metadata, "Projected content metadata")
    if (meta.get("encoding") != CONTENT_ENCODING or meta.get("stream") != selected_stream
            or type(meta.get("parts")) is not int or meta["parts"] <= 0
            or type(meta.get("characters")) is not int or meta["characters"] <= 0):
        raise NativeSessionProjectionError("Projected content metadata is invalid.")
    digest = _digest(meta.get("sha256"), "Projected content digest")
    chunks: list[tuple[int, str]] = []
    for source_seq in message.source_event_seqs or ():
        source = by_seq.get(source_seq)
        if source is None or source.event_type != chunk_type:
            continue
        part = source.data
        if part.get("stream") != selected_stream:
            continue
        if (type(part.get("part")) is not int or part.get("parts") != meta["parts"]
                or not isinstance(part.get("text"), str)
                or part.get("text_sha256") != hashlib.sha256(part["text"].encode("utf-8")).hexdigest()):
            raise NativeSessionProjectionError("Projected message chunk is invalid.")
        chunks.append((part["part"], part["text"]))
    chunks.sort()
    if [part for part, _ in chunks] != list(range(meta["parts"])):
        raise NativeSessionProjectionError("Projected message chunks are incomplete or duplicated.")
    text = "".join(value for _, value in chunks)
    if len(text) != meta["characters"] or hashlib.sha256(text.encode("utf-8")).hexdigest() != digest:
        raise NativeSessionProjectionError("Projected message content does not match its parity digest.")
    return text
