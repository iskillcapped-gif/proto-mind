"""Forward-only Session Spine writer/read pilot for exact Native turns.

P2g has no default storage path and no Native production caller. It accepts one
explicit store plus already persisted message, work-session, and Turn Lineage
evidence. Legacy history remains a separate read model and is never backfilled.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Mapping
from uuid import UUID

from proto_mind.native_session_spine import NativeSessionProjectionError, project_native_turn
from proto_mind.native_turn_lineage import NativeTurnLineageError, verify_turn_reference
from proto_mind.native_work_sessions import fingerprint as work_session_fingerprint
from proto_mind.session_spine import SessionEvent
from proto_mind.session_spine_composition import SessionSpineCompositionError, rebase_session_event
from proto_mind.session_spine_store import (
    SessionSpineStore,
    SessionSpineStoreError,
    SessionSpineStoreMissing,
    SessionSpineStoreSnapshot,
    build_store_image,
    extend_store_image,
    inspect_store_image,
)


PLAN_SCHEMA = "proto_mind.session_spine_forward_plan.v1"
APPLY_SCHEMA = "proto_mind.session_spine_forward_apply_receipt.v1"
DUAL_READ_SCHEMA = "proto_mind.session_spine_forward_dual_read.v1"
ARCHIVE_AUDIT_SCHEMA = "proto_mind.session_spine_archive_copy_audit.v1"
OWNER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,119}$")
HASH = re.compile(r"^[0-9a-f]{64}$")


class SessionSpineForwardError(RuntimeError):
    """Forward evidence is stale, ambiguous, unsafe, or incomplete."""


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
        raise SessionSpineForwardError("Forward Session Spine evidence is not lossless JSON.") from None


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _uuid(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise SessionSpineForwardError(f"{label} is invalid.")
    try:
        normalized = str(UUID(value))
    except (ValueError, AttributeError):
        raise SessionSpineForwardError(f"{label} is invalid.") from None
    if normalized != value:
        raise SessionSpineForwardError(f"{label} must use canonical lowercase UUID text.")
    return value


def _owner(value: object) -> str:
    if not isinstance(value, str) or not OWNER.fullmatch(value):
        raise SessionSpineForwardError("Forward Session Spine owner ID is invalid.")
    return value


def _message(value: Mapping[str, Any], role: str) -> tuple[str, str]:
    if not isinstance(value, Mapping) or value.get("role") != role:
        raise SessionSpineForwardError(f"Forward Native {role} message is invalid.")
    identifier = _uuid(value.get("id"), f"Forward Native {role} message ID")
    text = value.get("text")
    if not isinstance(text, str) or value.get("isError") is not False or value.get("operatorInput") is True:
        raise SessionSpineForwardError(f"Forward Native {role} message is not an eligible exact turn message.")
    return identifier, text


def _event_payload_sha256(events: tuple[SessionEvent, ...]) -> str:
    return _sha256(_canonical([event.to_dict() for event in events]))


def _scope_sha256(directory: Path) -> str:
    return _sha256(str(directory).encode("utf-8"))


def _turns(events: tuple[SessionEvent, ...]) -> tuple[tuple[SessionEvent, ...], ...]:
    rows: list[tuple[SessionEvent, ...]] = []
    start: int | None = None
    for index, event in enumerate(events):
        if event.event_type == "turn/start":
            if start is not None:
                raise SessionSpineForwardError("Stored Session Spine contains overlapping turn boundaries.")
            start = index
        elif event.event_type == "turn/end":
            if start is None:
                raise SessionSpineForwardError("Stored Session Spine contains an unmatched turn end.")
            rows.append(events[start:index + 1])
            start = None
    if start is not None:
        raise SessionSpineForwardError("Stored Session Spine ends inside an unresolved turn.")
    return tuple(rows)


def _turn_identity(events: tuple[SessionEvent, ...]) -> tuple[str, str, str]:
    if not events or events[0].event_type != "turn/start" or events[-1].event_type != "turn/end":
        raise SessionSpineForwardError("Stored Session Spine turn boundaries are invalid.")
    run_id = _uuid(events[0].data.get("native_run_id"), "Stored Native run ID")
    user_ids = [event.data.get("native_message_id") for event in events if event.event_type == "user/message"]
    assistant_ids = [event.data.get("native_message_id") for event in events if event.event_type == "assistant/message"]
    if len(user_ids) != 1 or len(assistant_ids) != 1:
        raise SessionSpineForwardError("Stored forward turn does not contain one exact message pair.")
    return (
        run_id,
        _uuid(user_ids[0], "Stored Native user message ID"),
        _uuid(assistant_ids[0], "Stored Native assistant message ID"),
    )


@dataclass(frozen=True)
class ForwardNativeTurnPlan:
    status: str
    operation: str
    session_id: str
    owner_id: str
    store_scope_sha256: str
    run_id: str
    run_fingerprint: str
    reference_hash: str
    user_message_id: str
    assistant_message_id: str
    input_sha256: str
    displayed_answer_sha256: str
    raw_answer_sha256: str
    event_start: int
    event_end: int
    event_count: int
    event_payload_sha256: str
    created_ms: int
    before_file_sha256: str | None
    before_file_bytes: int
    after_file_sha256: str
    after_file_bytes: int
    after_event_count: int
    after_surface_fingerprint: str
    plan_hash: str
    _events: tuple[SessionEvent, ...] = field(repr=False, compare=False)
    _before_raw: bytes | None = field(repr=False, compare=False)
    _candidate_raw: bytes = field(repr=False, compare=False)

    def _material(self) -> dict[str, Any]:
        return {
            "schema": PLAN_SCHEMA,
            "format_version": 1,
            "status": self.status,
            "operation": self.operation,
            "read_only_preview": True,
            "write_performed": False,
            "session_id": self.session_id,
            "owner_id": self.owner_id,
            "store_scope_sha256": self.store_scope_sha256,
            "source": {
                "run_id": self.run_id,
                "run_fingerprint": self.run_fingerprint,
                "reference_hash": self.reference_hash,
                "user_message_id": self.user_message_id,
                "assistant_message_id": self.assistant_message_id,
                "input_sha256": self.input_sha256,
                "displayed_answer_sha256": self.displayed_answer_sha256,
                "raw_answer_sha256": self.raw_answer_sha256,
            },
            "turn": {
                "event_start": self.event_start,
                "event_end": self.event_end,
                "event_count": self.event_count,
                "event_payload_sha256": self.event_payload_sha256,
                "created_ms": self.created_ms,
            },
            "precondition": {
                "file_sha256": self.before_file_sha256,
                "file_bytes": self.before_file_bytes,
            },
            "candidate": {
                "file_sha256": self.after_file_sha256,
                "file_bytes": self.after_file_bytes,
                "committed_event_count": self.after_event_count,
                "surface_fingerprint": self.after_surface_fingerprint,
            },
            "boundaries": {
                "exact_turn_reference_required": True,
                "stable_owner_required": True,
                "compare_and_swap_required": True,
                "legacy_backfill": False,
                "migration": False,
                "automatic_recovery": False,
                "native_activation": False,
                "authoritative_history_active": False,
                "model_call_performed": False,
                "provider_call_performed": False,
                "command_executed": False,
                "permission_changed": False,
            },
        }

    def to_dict(self) -> dict[str, Any]:
        return {**self._material(), "plan_hash": self.plan_hash}


def _make_plan(
    *,
    status: str,
    operation: str,
    store: SessionSpineStore,
    session_id: str,
    owner_id: str,
    projection: Any,
    reference: Mapping[str, Any],
    user_message_id: str,
    assistant_message_id: str,
    event_start: int,
    events: tuple[SessionEvent, ...],
    before_raw: bytes | None,
    candidate_raw: bytes,
) -> ForwardNativeTurnPlan:
    candidate = inspect_store_image(candidate_raw, session_id)
    values = {
        "status": status,
        "operation": operation,
        "session_id": session_id,
        "owner_id": owner_id,
        "store_scope_sha256": _scope_sha256(store.directory),
        "run_id": projection.run_id,
        "run_fingerprint": projection.run_fingerprint,
        "reference_hash": reference["reference_hash"],
        "user_message_id": user_message_id,
        "assistant_message_id": assistant_message_id,
        "input_sha256": projection.input_sha256,
        "displayed_answer_sha256": projection.displayed_answer_sha256,
        "raw_answer_sha256": projection.raw_answer_sha256,
        "event_start": event_start,
        "event_end": event_start + len(events) - 1,
        "event_count": len(events),
        "event_payload_sha256": _event_payload_sha256(events),
        "created_ms": projection.events[0].time_ms,
        "before_file_sha256": None if before_raw is None else _sha256(before_raw),
        "before_file_bytes": 0 if before_raw is None else len(before_raw),
        "after_file_sha256": candidate.file_sha256,
        "after_file_bytes": candidate.file_bytes,
        "after_event_count": len(candidate.events),
        "after_surface_fingerprint": candidate.surface.fingerprint,
        "_events": events,
        "_before_raw": before_raw,
        "_candidate_raw": candidate_raw,
    }
    unsigned = ForwardNativeTurnPlan(plan_hash="", **values)
    return ForwardNativeTurnPlan(plan_hash=_sha256(_canonical(unsigned._material())), **values)


def preview_forward_native_turn(
    store: SessionSpineStore,
    *,
    session_id: str,
    owner_id: str,
    conversation_id: str,
    user_message: Mapping[str, Any],
    assistant_message: Mapping[str, Any],
    work_session: dict[str, Any],
    turn_reference: object,
) -> ForwardNativeTurnPlan:
    """Build one exact CAS plan; no path is opened for writing."""
    if not isinstance(store, SessionSpineStore):
        raise SessionSpineForwardError("Forward Session Spine requires one explicit detached store.")
    session = _uuid(session_id, "Forward Session Spine session ID")
    conversation = _uuid(conversation_id, "Forward Native conversation ID")
    if session != conversation:
        raise SessionSpineForwardError("Forward Native session ID must equal its exact conversation ID.")
    owner = _owner(owner_id)
    user_id, input_text = _message(user_message, "user")
    assistant_id, displayed_answer = _message(assistant_message, "assistant")
    raw_value = assistant_message.get("raw", "")
    if not isinstance(raw_value, str):
        raise SessionSpineForwardError("Forward Native raw assistant response is invalid.")
    raw_answer = raw_value or displayed_answer
    if not isinstance(work_session, dict):
        raise SessionSpineForwardError("Forward Native work session must be one inspected record.")
    stored_fingerprint = work_session.get("fingerprint")
    canonical_record = {
        key: value for key, value in work_session.items()
        if key not in {"display_status", "fingerprint", "automatic_resume"}
    }
    if (
        not isinstance(stored_fingerprint, str)
        or not HASH.fullmatch(stored_fingerprint)
        or work_session_fingerprint(canonical_record) != stored_fingerprint
    ):
        raise SessionSpineForwardError("Forward Native work-session fingerprint does not verify.")
    try:
        reference = verify_turn_reference(
            turn_reference,
            conversation_id=conversation,
            source_message_id=user_id,
            input_text=input_text,
            response=raw_answer,
            work_session=work_session,
        )
        projection = project_native_turn(
            conversation_id=conversation,
            user_message=user_message,
            assistant_message=assistant_message,
            work_session=work_session,
        )
    except (NativeTurnLineageError, NativeSessionProjectionError) as error:
        raise SessionSpineForwardError(f"Exact forward Native turn validation failed: {error}") from None
    if projection.display_status != "completed" or projection.assistant_message_seq is None:
        raise SessionSpineForwardError("Only one completed exact Native turn can enter the forward store.")

    try:
        current_raw, snapshot = store.read_image(session)
    except SessionSpineStoreMissing:
        candidate = build_store_image(
            session_id=session,
            created_ms=projection.events[0].time_ms,
            owner_id=owner,
            events=projection.events,
        )
        return _make_plan(
            status="READY",
            operation="create",
            store=store,
            session_id=session,
            owner_id=owner,
            projection=projection,
            reference=reference,
            user_message_id=user_id,
            assistant_message_id=assistant_id,
            event_start=0,
            events=projection.events,
            before_raw=None,
            candidate_raw=candidate,
        )
    except SessionSpineStoreError as error:
        raise SessionSpineForwardError(f"Forward Session Spine inspection failed: {error}") from None

    if (
        snapshot.created_by != owner
        or any(append_owner != owner for append_owner in snapshot.append_owners)
    ):
        raise SessionSpineForwardError("Existing Session Spine is not exclusively bound to the explicit stable owner.")
    if not snapshot.appendable or snapshot.recovery_state not in {"idle", "closed"}:
        raise SessionSpineForwardError("Existing Session Spine is not at a verified appendable boundary.")

    stored_turns = _turns(snapshot.events)
    identities = tuple(_turn_identity(turn) for turn in stored_turns)
    run_matches = [index for index, identity in enumerate(identities) if identity[0] == projection.run_id]
    if len(run_matches) > 1:
        raise SessionSpineForwardError("Existing Session Spine contains duplicate Native run identity.")
    if run_matches:
        turn = stored_turns[run_matches[0]]
        expected = tuple(rebase_session_event(event, turn[0].seq) for event in projection.events)
        if turn != expected or _turn_identity(turn) != (projection.run_id, user_id, assistant_id):
            raise SessionSpineForwardError("Replayed Native run conflicts with already committed forward evidence.")
        return _make_plan(
            status="ALREADY_COMMITTED",
            operation="none",
            store=store,
            session_id=session,
            owner_id=owner,
            projection=projection,
            reference=reference,
            user_message_id=user_id,
            assistant_message_id=assistant_id,
            event_start=turn[0].seq,
            events=expected,
            before_raw=current_raw,
            candidate_raw=current_raw,
        )

    if any(user_id in identity[1:] or assistant_id in identity[1:] for identity in identities):
        raise SessionSpineForwardError("Native message identity is already bound to another committed run.")
    offset = len(snapshot.events)
    try:
        events = tuple(rebase_session_event(event, offset) for event in projection.events)
        candidate = extend_store_image(
            current_raw,
            session_id=session,
            owner_id=owner,
            events=events,
        )
    except (SessionSpineCompositionError, SessionSpineStoreError) as error:
        raise SessionSpineForwardError(f"Forward Session Spine candidate failed: {error}") from None
    return _make_plan(
        status="READY",
        operation="append",
        store=store,
        session_id=session,
        owner_id=owner,
        projection=projection,
        reference=reference,
        user_message_id=user_id,
        assistant_message_id=assistant_id,
        event_start=offset,
        events=events,
        before_raw=current_raw,
        candidate_raw=candidate,
    )


def _validate_plan(store: SessionSpineStore, plan: ForwardNativeTurnPlan) -> None:
    if not isinstance(store, SessionSpineStore) or not isinstance(plan, ForwardNativeTurnPlan):
        raise SessionSpineForwardError("Forward apply requires one explicit store and validated plan.")
    if _scope_sha256(store.directory) != plan.store_scope_sha256:
        raise SessionSpineForwardError("Forward plan is bound to a different explicit store scope.")
    if _sha256(_canonical(plan._material())) != plan.plan_hash:
        raise SessionSpineForwardError("Forward plan hash does not verify.")
    if plan.status not in {"READY", "ALREADY_COMMITTED"} or plan.operation not in {"create", "append", "none"}:
        raise SessionSpineForwardError("Forward plan state is invalid.")
    if (plan.status == "ALREADY_COMMITTED") != (plan.operation == "none"):
        raise SessionSpineForwardError("Forward plan status and operation disagree.")
    if not plan._events or plan.event_count != len(plan._events):
        raise SessionSpineForwardError("Forward plan lost its exact complete turn events.")
    if not isinstance(plan.plan_hash, str) or not HASH.fullmatch(plan.plan_hash):
        raise SessionSpineForwardError("Forward plan hash is invalid.")
    if plan.event_start != plan._events[0].seq or plan.event_end != plan._events[-1].seq:
        raise SessionSpineForwardError("Forward plan event range does not verify.")
    if plan.created_ms != plan._events[0].time_ms:
        raise SessionSpineForwardError("Forward plan creation time does not match its turn.")
    run_id, user_id, assistant_id = _turn_identity(plan._events)
    if (run_id, user_id, assistant_id) != (
        plan.run_id,
        plan.user_message_id,
        plan.assistant_message_id,
    ):
        raise SessionSpineForwardError("Forward plan identities do not match its exact turn events.")
    start_data = plan._events[0].data
    user_data = next(event.data for event in plan._events if event.event_type == "user/message")
    assistant_data = next(event.data for event in plan._events if event.event_type == "assistant/message")
    if (
        start_data.get("native_run_fingerprint") != plan.run_fingerprint
        or (user_data.get("content") or {}).get("sha256") != plan.input_sha256
        or (assistant_data.get("display_content") or {}).get("sha256") != plan.displayed_answer_sha256
        or (assistant_data.get("raw_content") or {}).get("sha256") != plan.raw_answer_sha256
    ):
        raise SessionSpineForwardError("Forward plan source hashes do not match its exact turn events.")
    if _event_payload_sha256(plan._events) != plan.event_payload_sha256:
        raise SessionSpineForwardError("Forward plan event payload hash does not verify.")
    if _sha256(plan._candidate_raw) != plan.after_file_sha256 or len(plan._candidate_raw) != plan.after_file_bytes:
        raise SessionSpineForwardError("Forward candidate bytes do not match the plan.")
    candidate = inspect_store_image(plan._candidate_raw, plan.session_id)
    if (
        len(candidate.events) != plan.after_event_count
        or candidate.surface.fingerprint != plan.after_surface_fingerprint
        or candidate.events[plan.event_start:plan.event_end + 1] != plan._events
        or candidate.created_by != plan.owner_id
        or any(owner != plan.owner_id for owner in candidate.append_owners)
    ):
        raise SessionSpineForwardError("Forward candidate replay does not match the plan.")
    if plan._before_raw is None:
        if plan.operation != "create" or plan.before_file_sha256 is not None or plan.before_file_bytes != 0:
            raise SessionSpineForwardError("Forward create precondition is invalid.")
        expected = build_store_image(
            session_id=plan.session_id,
            created_ms=plan.created_ms,
            owner_id=plan.owner_id,
            events=plan._events,
        )
    else:
        if (
            _sha256(plan._before_raw) != plan.before_file_sha256
            or len(plan._before_raw) != plan.before_file_bytes
        ):
            raise SessionSpineForwardError("Forward plan preimage does not verify.")
        expected = plan._before_raw if plan.operation == "none" else extend_store_image(
            plan._before_raw,
            session_id=plan.session_id,
            owner_id=plan.owner_id,
            events=plan._events,
        )
    if expected != plan._candidate_raw:
        raise SessionSpineForwardError("Forward plan cannot reproduce its exact candidate bytes.")


def _apply_receipt(
    plan: ForwardNativeTurnPlan,
    *,
    result: str,
    write_performed: bool,
    batch_receipt: dict[str, Any] | None,
) -> dict[str, Any]:
    receipt: dict[str, Any] = {
        "schema": APPLY_SCHEMA,
        "format_version": 1,
        "result": result,
        "session_id": plan.session_id,
        "owner_id": plan.owner_id,
        "run_id": plan.run_id,
        "reference_hash": plan.reference_hash,
        "plan_hash": plan.plan_hash,
        "write_performed": write_performed,
        "written_scope": "explicit_session_spine_store_only" if write_performed else "none",
        "before_file_sha256": plan.before_file_sha256,
        "after_file_sha256": plan.after_file_sha256,
        "after_event_count": plan.after_event_count,
        "post_state_verified": True,
        "batch_receipt": batch_receipt,
        "idempotent_replay": result == "ALREADY_COMMITTED",
        "legacy_history_modified": False,
        "native_activation": False,
        "authoritative_history_active": False,
        "model_call_performed": False,
        "provider_call_performed": False,
        "command_executed": False,
        "permission_changed": False,
    }
    receipt["receipt_hash"] = _sha256(_canonical(receipt))
    return receipt


def apply_forward_native_turn(
    store: SessionSpineStore,
    plan: ForwardNativeTurnPlan,
) -> dict[str, Any]:
    """Apply one validated plan to only its explicit detached Session Spine store."""
    _validate_plan(store, plan)
    try:
        current = store.inspect(plan.session_id)
    except SessionSpineStoreMissing:
        current = None
    except SessionSpineStoreError as error:
        raise SessionSpineForwardError(f"Forward apply precondition inspection failed: {error}") from None

    if current is not None and current.file_sha256 == plan.after_file_sha256:
        if current.events != inspect_store_image(plan._candidate_raw, plan.session_id).events:
            raise SessionSpineForwardError("Candidate fingerprint matched but event replay diverged.")
        return _apply_receipt(plan, result="ALREADY_COMMITTED", write_performed=False, batch_receipt=None)
    if plan.operation == "none":
        raise SessionSpineForwardError("Previously committed forward turn no longer matches its exact candidate.")
    if plan._before_raw is None:
        if current is not None:
            raise SessionSpineForwardError("Forward create lost its absent-store precondition; no write was attempted.")
        writer_args = {"created_ms": plan.created_ms}
    else:
        if current is None or current.file_sha256 != plan.before_file_sha256:
            raise SessionSpineForwardError("Forward append lost its inspected preimage; no stale write was attempted.")
        writer_args = {"expected_fingerprint": plan.before_file_sha256}

    try:
        with store.writer(plan.session_id, plan.owner_id, **writer_args) as writer:
            batch = writer.append_turn(plan._events)
        after = store.inspect(plan.session_id)
    except SessionSpineStoreError as error:
        raise SessionSpineForwardError(f"Forward Session Spine write failed: {error}") from None
    expected = inspect_store_image(plan._candidate_raw, plan.session_id)
    if (
        after.file_sha256 != plan.after_file_sha256
        or after.events != expected.events
        or after.surface.fingerprint != plan.after_surface_fingerprint
    ):
        raise SessionSpineForwardError("Forward post-write state does not match the exact planned candidate.")
    return _apply_receipt(
        plan,
        result="COMMITTED",
        write_performed=True,
        batch_receipt=batch.to_dict(),
    )


def audit_forward_dual_read(
    archive_report: Mapping[str, Any],
    store_snapshots: Mapping[str, SessionSpineStoreSnapshot],
) -> dict[str, Any]:
    """Compare copied legacy/lineage evidence with explicit forward snapshots."""
    if not isinstance(archive_report, Mapping) or not isinstance(store_snapshots, Mapping):
        raise SessionSpineForwardError("Dual-read audit requires explicit archive evidence and snapshots.")
    report = dict(archive_report)
    audit_hash = report.pop("audit_hash", None)
    if (
        archive_report.get("schema") != ARCHIVE_AUDIT_SCHEMA
        or archive_report.get("read_only") is not True
        or archive_report.get("no_write") is not True
        or not isinstance(audit_hash, str)
        or not HASH.fullmatch(audit_hash)
        or _sha256(_canonical(report)) != audit_hash
    ):
        raise SessionSpineForwardError("Archive-copy audit hash or safety boundary does not verify.")
    turns = archive_report.get("turn_findings")
    if not isinstance(turns, list) or any(not isinstance(item, dict) for item in turns):
        raise SessionSpineForwardError("Archive-copy turn findings are invalid.")

    stored: dict[tuple[str, str], dict[str, Any]] = {}
    store_issues: list[dict[str, Any]] = []
    for supplied_session, snapshot in sorted(store_snapshots.items()):
        session = _uuid(supplied_session, "Dual-read supplied session ID")
        if not isinstance(snapshot, SessionSpineStoreSnapshot) or snapshot.session_id != session:
            raise SessionSpineForwardError("Dual-read snapshot key or type is invalid.")
        if snapshot.recovery_state not in {"idle", "closed"}:
            store_issues.append({
                "category": "forward_store_unknown",
                "severity": "ERROR",
                "conversation_id": session,
                "reason": "forward_store_is_not_at_a_closed_boundary",
            })
            continue
        if any(owner != snapshot.created_by for owner in snapshot.append_owners):
            store_issues.append({
                "category": "forward_owner_drift",
                "severity": "ERROR",
                "conversation_id": session,
                "reason": "forward_store_has_multiple_writer_owners",
            })
        for turn in _turns(snapshot.events):
            run_id, user_id, assistant_id = _turn_identity(turn)
            key = (session, run_id)
            if key in stored or any(existing_run == run_id for _, existing_run in stored):
                store_issues.append({
                    "category": "duplicate_forward_run",
                    "severity": "ERROR",
                    "conversation_id": session,
                    "run_id": run_id,
                    "reason": "run_identity_is_not_unique_across_forward_snapshots",
                })
                continue
            stored[key] = {
                "conversation_id": session,
                "run_id": run_id,
                "user_message_id": user_id,
                "assistant_message_id": assistant_id,
                "event_start": turn[0].seq,
                "event_end": turn[-1].seq,
            }

    compatible: dict[tuple[str, str], dict[str, Any]] = {}
    legacy: list[dict[str, Any]] = []
    for item in turns:
        if item.get("category") == "legacy_unlinked":
            legacy.append({
                "category": "legacy_unlinked",
                "conversation_id": item.get("conversation_id"),
                "message_id": item.get("message_id"),
                "reason": item.get("reason"),
            })
        elif item.get("category") == "compatible":
            conversation = _uuid(item.get("conversation_id"), "Compatible conversation ID")
            run_id = _uuid(item.get("run_id"), "Compatible Native run ID")
            key = (conversation, run_id)
            if key in compatible:
                raise SessionSpineForwardError("Archive-copy audit repeats one compatible Native run.")
            compatible[key] = {
                "conversation_id": conversation,
                "run_id": run_id,
                "source_message_id": item.get("source_message_id"),
                "assistant_message_id": item.get("message_id"),
                "reference_hash": item.get("reference_hash"),
            }

    matched: list[dict[str, Any]] = []
    for key in sorted(compatible.keys() & stored.keys()):
        archive_item = compatible[key]
        stored_item = stored[key]
        if (
            archive_item["source_message_id"] != stored_item["user_message_id"]
            or archive_item["assistant_message_id"] != stored_item["assistant_message_id"]
        ):
            store_issues.append({
                "category": "forward_lineage_mismatch",
                "severity": "ERROR",
                "conversation_id": key[0],
                "run_id": key[1],
                "reason": "forward_message_pair_differs_from_exact_archive_reference",
            })
            continue
        matched.append(archive_item)
    recovery = [compatible[key] for key in sorted(compatible.keys() - stored.keys())]
    store_only = [stored[key] for key in sorted(stored.keys() - compatible.keys())]
    findings = [
        *store_issues,
        *({
            "category": "exact_recovery_candidate",
            "severity": "WARN",
            **item,
            "reason": "exact_linked_archive_turn_is_absent_from_forward_store",
        } for item in recovery),
        *({
            "category": "store_only_or_copy_incomplete",
            "severity": "WARN",
            **item,
            "reason": "forward_turn_is_absent_from_non_authoritative_archive_copy",
        } for item in store_only),
    ]
    errors = sum(item["severity"] == "ERROR" for item in findings)
    warnings = len(legacy) + sum(item["severity"] == "WARN" for item in findings)
    status = (
        "ERROR"
        if errors or archive_report.get("status") == "ERROR"
        else "WARN"
        if warnings or archive_report.get("status") == "WARN"
        else "OK"
    )
    result: dict[str, Any] = {
        "schema": DUAL_READ_SCHEMA,
        "format_version": 1,
        "status": status,
        "read_only": True,
        "no_file_access": True,
        "no_write": True,
        "execute": False,
        "report_content_free": True,
        "source": {
            "archive_audit_hash": audit_hash,
            "archive_status": archive_report.get("status"),
            "forward_snapshot_count": len(store_snapshots),
            "source_archive_completeness_verified": False,
        },
        "counts": {
            "legacy_unlinked": len(legacy),
            "linked_compatible": len(compatible),
            "forward_stored": len(matched),
            "exact_recovery_candidates": len(recovery),
            "store_only_or_copy_incomplete": len(store_only),
            "warnings": warnings,
            "errors": errors,
        },
        "legacy_findings": legacy,
        "forward_stored": matched,
        "exact_recovery_candidates": recovery,
        "store_only_or_copy_incomplete": store_only,
        "findings": findings,
        "boundaries": {
            "legacy_and_forward_views_separate": True,
            "legacy_backfill": False,
            "pairing_inferred": False,
            "automatic_recovery": False,
            "archive_copy_declared_complete": False,
            "native_activation": False,
            "authoritative_history_active": False,
            "model_call_performed": False,
            "provider_call_performed": False,
            "command_executed": False,
            "permission_changed": False,
        },
    }
    result["dual_read_hash"] = _sha256(_canonical(result))
    return result
