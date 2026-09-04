"""Detached compatibility audit for an explicitly supplied Native archive copy.

P2e accepts immutable bytes for one complete ``conversations.json`` copy and
an exact caller-bound manifest of copied work-session records. It never opens
a path, discovers personal state, writes a report, pairs by proximity beyond
the persisted immediate-message reference, or grants Session Spine authority.
"""
from __future__ import annotations

from collections import Counter
import hashlib
import json
import math
import re
from typing import Any, Mapping
from uuid import UUID

from proto_mind.native_session_spine import (
    NativeSessionProjectionError,
    project_native_turn,
)
from proto_mind.native_turn_lineage import (
    NativeTurnLineageError,
    validate_turn_reference,
    verify_turn_reference,
)
from proto_mind.native_work_sessions import (
    MAX_RECORD_BYTES,
    MAX_RUNS,
    WorkSessionError,
    inspect_work_session_copy,
)


SCHEMA = "proto_mind.session_spine_archive_copy_audit.v1"
MANIFEST_SCHEMA = "proto_mind.session_spine_archive_copy_manifest.v1"
FORMAT_VERSION = 1
MAX_HISTORY_BYTES = 50 * 1024 * 1024
MAX_TOTAL_COPY_BYTES = MAX_HISTORY_BYTES + MAX_RUNS * MAX_RECORD_BYTES
MAX_CONVERSATIONS = 10_000
MAX_MESSAGES = 100_000
HASH = re.compile(r"[0-9a-f]{64}\Z")


class SessionSpineArchiveCopyError(RuntimeError):
    """The supplied copy cannot be audited without guessing or widening scope."""


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
        raise SessionSpineArchiveCopyError("Archive-copy evidence is not lossless JSON.") from None


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _pairs(values: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in values:
        if key in result:
            raise SessionSpineArchiveCopyError("Archive copy contains a duplicate JSON field.")
        result[key] = value
    return result


def _constant(_: str) -> None:
    raise SessionSpineArchiveCopyError("Archive copy contains non-finite JSON.")


def _digest(value: object, label: str) -> str:
    if not isinstance(value, str) or not HASH.fullmatch(value):
        raise SessionSpineArchiveCopyError(f"{label} must be a lowercase SHA-256 digest.")
    return value


def _uuid(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise SessionSpineArchiveCopyError(f"{label} is invalid.")
    try:
        normalized = str(UUID(value))
    except (ValueError, AttributeError):
        raise SessionSpineArchiveCopyError(f"{label} is invalid.") from None
    if normalized != value:
        raise SessionSpineArchiveCopyError(f"{label} must use canonical lowercase UUID text.")
    return value


def _archive_uuid(value: object, label: str) -> str:
    """Accept the two canonical UUID forms emitted by Python and Swift stores."""
    if not isinstance(value, str):
        raise SessionSpineArchiveCopyError(f"{label} is invalid.")
    try:
        normalized = str(UUID(value))
    except (ValueError, AttributeError):
        raise SessionSpineArchiveCopyError(f"{label} is invalid.") from None
    if value not in {normalized, normalized.upper()}:
        raise SessionSpineArchiveCopyError(f"{label} is not canonical Native UUID text.")
    return normalized


def _optional_uuid(value: object) -> str | None:
    try:
        return _uuid(value, "Referenced ID")
    except SessionSpineArchiveCopyError:
        return None


def _text(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise SessionSpineArchiveCopyError(f"{label} is invalid.")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        raise SessionSpineArchiveCopyError(f"{label} is not valid UTF-8 text.") from None
    return value


def _date(value: object, label: str) -> int | float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise SessionSpineArchiveCopyError(f"{label} is invalid.")
    return value


def _decode_history(raw: bytes) -> tuple[dict[str, Any], tuple[dict[str, Any], ...], int]:
    if type(raw) is not bytes or not raw or len(raw) >= MAX_HISTORY_BYTES:
        raise SessionSpineArchiveCopyError("Native history copy is not bounded immutable bytes.")
    try:
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_pairs,
            parse_constant=_constant,
        )
    except SessionSpineArchiveCopyError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError, RecursionError):
        raise SessionSpineArchiveCopyError("Native history copy is not valid UTF-8 JSON.") from None
    if not isinstance(value, dict):
        raise SessionSpineArchiveCopyError("Native history copy must be a JSON object.")
    version = value.get("version")
    conversations = value.get("conversations")
    if type(version) is not int or version not in {1, 2, 3, 4, 5} or not isinstance(conversations, list):
        raise SessionSpineArchiveCopyError("Native history version or conversation list is unsupported.")
    if len(conversations) > MAX_CONVERSATIONS:
        raise SessionSpineArchiveCopyError("Native history conversation count exceeds the audit bound.")
    selected = value.get("selectedID")
    if selected is not None:
        _archive_uuid(selected, "Selected conversation ID")

    conversation_ids: set[str] = set()
    issues: list[dict[str, Any]] = []
    message_count = 0
    required_conversation = {"id", "title", "createdAt", "updatedAt", "messages", "provider", "model"}
    required_message = {"id", "role", "text", "raw", "evidence", "notices", "createdAt", "isError"}
    for conversation_index, conversation in enumerate(conversations):
        if not isinstance(conversation, dict) or not required_conversation.issubset(conversation):
            raise SessionSpineArchiveCopyError("Native conversation shape is incomplete.")
        conversation_id = _archive_uuid(conversation["id"], "Native conversation ID")
        if conversation_id in conversation_ids:
            raise SessionSpineArchiveCopyError("Native history contains duplicate conversation IDs.")
        conversation_ids.add(conversation_id)
        for field in ("title", "provider", "model"):
            _text(conversation[field], f"Native conversation {field}")
        _date(conversation["createdAt"], "Native conversation createdAt")
        _date(conversation["updatedAt"], "Native conversation updatedAt")
        messages = conversation["messages"]
        if not isinstance(messages, list):
            raise SessionSpineArchiveCopyError("Native conversation messages must be an array.")
        message_count += len(messages)
        if message_count > MAX_MESSAGES:
            raise SessionSpineArchiveCopyError("Native history message count exceeds the audit bound.")
        seen_messages: set[str] = set()
        for message_index, message in enumerate(messages):
            if not isinstance(message, dict) or not required_message.issubset(message):
                raise SessionSpineArchiveCopyError("Native message shape is incomplete.")
            message_id = _archive_uuid(message["id"], "Native message ID")
            if message_id in seen_messages:
                issues.append({
                    "category": "duplicate_message_id",
                    "severity": "ERROR",
                    "reason": "message_identity_is_ambiguous",
                    "conversation_id": conversation_id,
                    "conversation_index": conversation_index,
                    "message_index": message_index,
                    "message_id": message_id,
                })
            seen_messages.add(message_id)
            _text(message["role"], "Native message role")
            _text(message["text"], "Native message text")
            _text(message["raw"], "Native message raw text")
            if not isinstance(message["notices"], list) or any(not isinstance(item, str) for item in message["notices"]):
                raise SessionSpineArchiveCopyError("Native message notices are invalid.")
            _date(message["createdAt"], "Native message createdAt")
            if type(message["isError"]) is not bool:
                raise SessionSpineArchiveCopyError("Native message error marker is invalid.")
            if message.get("operatorInput") is not None and type(message["operatorInput"]) is not bool:
                raise SessionSpineArchiveCopyError("Native operator-input marker is invalid.")
            source = message.get("memorySuggestionSourceID")
            if source is not None:
                _archive_uuid(source, "Memory suggestion source ID")
    return value, tuple(issues), message_count


def _manifest(
    history_sha256: str,
    work_session_raws: Mapping[str, bytes],
    expected: tuple[tuple[str, str], ...],
) -> tuple[tuple[tuple[str, bytes], ...], str, int]:
    if not isinstance(work_session_raws, Mapping) or type(expected) is not tuple:
        raise SessionSpineArchiveCopyError("Work-session copy and manifest have invalid container types.")
    supplied_items = tuple(work_session_raws.items())
    if any(not isinstance(name, str) for name, _ in supplied_items):
        raise SessionSpineArchiveCopyError("Supplied work-session filename is invalid.")
    supplied = tuple(sorted(supplied_items))
    if len(supplied) > MAX_RUNS:
        raise SessionSpineArchiveCopyError("Work-session copy exceeds the Native record-count bound.")
    checked: list[tuple[str, str]] = []
    for row in expected:
        if type(row) is not tuple or len(row) != 2:
            raise SessionSpineArchiveCopyError("Work-session manifest rows must be immutable name/digest pairs.")
        name, digest = row
        if not isinstance(name, str) or not name.endswith(".json"):
            raise SessionSpineArchiveCopyError("Work-session manifest filename is invalid.")
        _uuid(name[:-5], "Work-session manifest filename")
        checked.append((name, _digest(digest, "Work-session manifest digest")))
    checked_manifest = tuple(checked)
    if checked_manifest != tuple(sorted(checked_manifest)) or len({name for name, _ in checked_manifest}) != len(checked_manifest):
        raise SessionSpineArchiveCopyError("Work-session manifest must be unique and sorted by filename.")
    if tuple(name for name, _ in supplied) != tuple(name for name, _ in checked_manifest):
        raise SessionSpineArchiveCopyError("Supplied work-session files do not exactly match the caller manifest.")

    total = 0
    immutable: list[tuple[str, bytes]] = []
    for (name, raw), (_, expected_digest) in zip(supplied, checked_manifest, strict=True):
        if type(raw) is not bytes or not raw or len(raw) > MAX_RECORD_BYTES:
            raise SessionSpineArchiveCopyError("Work-session copy contains unbounded or mutable record data.")
        if _sha256(raw) != expected_digest:
            raise SessionSpineArchiveCopyError("Work-session copy digest does not match the caller manifest.")
        total += len(raw)
        immutable.append((name, raw))
    material = {
        "schema": MANIFEST_SCHEMA,
        "history": {"name": "conversations.json", "sha256": history_sha256},
        "work_sessions": [{"name": name, "sha256": digest} for name, digest in checked_manifest],
    }
    return tuple(immutable), _sha256(_canonical(material)), total


def _turn_finding(
    *,
    category: str,
    severity: str,
    reason: str,
    conversation_id: str,
    conversation_index: int,
    message_index: int,
    message_id: str,
    source_message_id: str | None = None,
    run_id: str | None = None,
    reference_hash: str | None = None,
    projection: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "category": category,
        "severity": severity,
        "reason": reason,
        "conversation_id": conversation_id,
        "conversation_index": conversation_index,
        "message_index": message_index,
        "message_id": message_id,
        "source_message_id": source_message_id,
        "run_id": run_id,
        "reference_hash": reference_hash,
        "projection": projection,
    }


def audit_native_archive_copy(
    history_raw: bytes,
    work_session_raws: Mapping[str, bytes],
    *,
    expected_history_sha256: str,
    expected_work_session_manifest: tuple[tuple[str, str], ...],
) -> dict[str, Any]:
    """Audit exact copied bytes and return content-free deterministic evidence."""
    expected_history = _digest(expected_history_sha256, "Native history digest")
    if type(history_raw) is not bytes or _sha256(history_raw) != expected_history:
        raise SessionSpineArchiveCopyError("Native history copy digest does not match the caller manifest.")
    archive, archive_issues, message_count = _decode_history(history_raw)
    copied_runs, manifest_sha256, run_bytes = _manifest(
        expected_history,
        work_session_raws,
        expected_work_session_manifest,
    )
    if len(history_raw) + run_bytes > MAX_TOTAL_COPY_BYTES:
        raise SessionSpineArchiveCopyError("Archive copy exceeds the bounded aggregate audit contract.")

    runs: dict[str, dict[str, Any]] = {}
    invalid_run_ids: set[str] = set()
    run_digests: dict[str, str] = {}
    for name, raw in copied_runs:
        run_id = name[:-5]
        run_digests[run_id] = _sha256(raw)
        try:
            runs[run_id] = inspect_work_session_copy(raw, name)
        except WorkSessionError:
            invalid_run_ids.add(run_id)

    turn_findings: list[dict[str, Any]] = []
    referenced_run_counts: Counter[str] = Counter()
    compatible_run_ids: set[str] = set()
    used_sources: set[tuple[str, str]] = set()
    used_runs: set[str] = set()
    eligible_assistant_count = 0
    linked_reference_count = 0

    for conversation_index, conversation in enumerate(archive["conversations"]):
        conversation_id = _archive_uuid(conversation["id"], "Native conversation ID")
        messages = conversation["messages"]
        for message_index, message in enumerate(messages):
            message_id = _archive_uuid(message["id"], "Native message ID")
            reference_raw = message.get("turnReference")
            eligible_assistant = (
                message["role"] == "assistant"
                and message["isError"] is False
                and message.get("operatorInput") is not True
            )
            if eligible_assistant:
                eligible_assistant_count += 1
            if reference_raw is None:
                if eligible_assistant:
                    turn_findings.append(_turn_finding(
                        category="legacy_unlinked",
                        severity="WARN",
                        reason="assistant_has_no_persisted_turn_reference",
                        conversation_id=conversation_id,
                        conversation_index=conversation_index,
                        message_index=message_index,
                        message_id=message_id,
                    ))
                continue

            linked_reference_count += 1
            candidate_run_id = reference_raw.get("run_id") if isinstance(reference_raw, dict) else None
            run_id = _optional_uuid(candidate_run_id)
            source_id = None
            reference_hash = None
            try:
                reference = validate_turn_reference(reference_raw)
                run_id = reference["run_id"]
                source_id = reference["source_message_id"]
                reference_hash = reference["reference_hash"]
                referenced_run_counts[run_id] += 1
            except NativeTurnLineageError:
                turn_findings.append(_turn_finding(
                    category="invalid_reference",
                    severity="ERROR",
                    reason="turn_reference_schema_or_hash_failed",
                    conversation_id=conversation_id,
                    conversation_index=conversation_index,
                    message_index=message_index,
                    message_id=message_id,
                    run_id=run_id,
                ))
                continue

            source_key = (conversation_id, source_id)
            if source_key in used_sources or run_id in used_runs:
                turn_findings.append(_turn_finding(
                    category="duplicate_lineage",
                    severity="ERROR",
                    reason="source_or_run_reference_is_reused",
                    conversation_id=conversation_id,
                    conversation_index=conversation_index,
                    message_index=message_index,
                    message_id=message_id,
                    source_message_id=source_id,
                    run_id=run_id,
                    reference_hash=reference_hash,
                ))
                continue
            used_sources.add(source_key)
            used_runs.add(run_id)

            previous = messages[message_index - 1] if message_index > 0 else None
            if (
                not isinstance(previous, dict)
                or message["role"] != "assistant"
                or message["isError"] is not False
                or message.get("operatorInput") is True
                or _archive_uuid(previous["id"], "Native source message ID") != source_id
                or previous["role"] != "user"
                or previous["isError"] is not False
                or previous.get("operatorInput") is True
            ):
                turn_findings.append(_turn_finding(
                    category="invalid_message_pair",
                    severity="ERROR",
                    reason="reference_does_not_name_the_immediately_preceding_operator_message",
                    conversation_id=conversation_id,
                    conversation_index=conversation_index,
                    message_index=message_index,
                    message_id=message_id,
                    source_message_id=source_id,
                    run_id=run_id,
                    reference_hash=reference_hash,
                ))
                continue
            if run_id in invalid_run_ids:
                turn_findings.append(_turn_finding(
                    category="invalid_run",
                    severity="ERROR",
                    reason="referenced_work_session_copy_failed_validation",
                    conversation_id=conversation_id,
                    conversation_index=conversation_index,
                    message_index=message_index,
                    message_id=message_id,
                    source_message_id=source_id,
                    run_id=run_id,
                    reference_hash=reference_hash,
                ))
                continue
            run = runs.get(run_id)
            if run is None:
                turn_findings.append(_turn_finding(
                    category="missing_run",
                    severity="ERROR",
                    reason="exact_referenced_work_session_is_absent",
                    conversation_id=conversation_id,
                    conversation_index=conversation_index,
                    message_index=message_index,
                    message_id=message_id,
                    source_message_id=source_id,
                    run_id=run_id,
                    reference_hash=reference_hash,
                ))
                continue

            response = message["raw"] or message["text"]
            try:
                verify_turn_reference(
                    reference,
                    conversation_id=conversation_id,
                    source_message_id=source_id,
                    input_text=previous["text"],
                    response=response,
                    work_session=run,
                )
            except NativeTurnLineageError:
                turn_findings.append(_turn_finding(
                    category="lineage_mismatch",
                    severity="ERROR",
                    reason="reference_does_not_match_exact_message_and_run_bytes",
                    conversation_id=conversation_id,
                    conversation_index=conversation_index,
                    message_index=message_index,
                    message_id=message_id,
                    source_message_id=source_id,
                    run_id=run_id,
                    reference_hash=reference_hash,
                ))
                continue
            try:
                projected = project_native_turn(
                    conversation_id=conversation_id,
                    user_message=previous,
                    assistant_message=message,
                    work_session=run,
                )
            except NativeSessionProjectionError:
                turn_findings.append(_turn_finding(
                    category="projection_error",
                    severity="ERROR",
                    reason="exact_linked_turn_does_not_pass_existing_p1_projection",
                    conversation_id=conversation_id,
                    conversation_index=conversation_index,
                    message_index=message_index,
                    message_id=message_id,
                    source_message_id=source_id,
                    run_id=run_id,
                    reference_hash=reference_hash,
                ))
                continue
            compatible_run_ids.add(run_id)
            turn_findings.append(_turn_finding(
                category="compatible",
                severity="INFO",
                reason="exact_reference_run_and_p1_projection_verified",
                conversation_id=conversation_id,
                conversation_index=conversation_index,
                message_index=message_index,
                message_id=message_id,
                source_message_id=source_id,
                run_id=run_id,
                reference_hash=reference_hash,
                projection={
                    "schema": projected.to_dict()["schema"],
                    "event_count": len(projected.events),
                    "surface_fingerprint": projected.surface.fingerprint,
                    "run_fingerprint": projected.run_fingerprint,
                    "input_sha256": projected.input_sha256,
                    "displayed_answer_sha256": projected.displayed_answer_sha256,
                    "raw_answer_sha256": projected.raw_answer_sha256,
                    "work_log_sha256": projected.work_log_sha256,
                    "memory_candidate_count": len(projected.memory_candidate_ids),
                },
            ))

    run_findings: list[dict[str, Any]] = []
    for name, _ in copied_runs:
        run_id = name[:-5]
        if run_id in invalid_run_ids:
            category, severity, reason = "invalid_record", "ERROR", "copied_work_session_failed_current_validation"
            run = None
        else:
            run = runs[run_id]
            references = referenced_run_counts[run_id]
            if references > 1:
                category, severity, reason = "referenced_ambiguous", "ERROR", "run_is_referenced_more_than_once"
            elif run_id in compatible_run_ids:
                category, severity, reason = "linked_compatible", "INFO", "exact_linked_turn_passed_p1_projection"
            elif references:
                category, severity, reason = "referenced_incompatible", "ERROR", "referenced_turn_failed_compatibility_checks"
            elif run.get("turn_receipt") is not None:
                category, severity, reason = "orphaned_lineage", "WARN", "lineage_capable_run_has_no_history_reference"
            elif run["display_status"] == "completed":
                category, severity, reason = "legacy_unlinked", "WARN", "completed_legacy_run_has_no_turn_receipt"
            else:
                category, severity, reason = "unlinked_incomplete", "WARN", "noncompleted_run_has_no_history_reference"
        run_findings.append({
            "category": category,
            "severity": severity,
            "reason": reason,
            "name": name,
            "run_id": run_id,
            "record_sha256": run_digests[run_id],
            "conversation_id": None if run is None else run["conversation_id"],
            "source_status": None if run is None else run["status"],
            "display_status": None if run is None else run["display_status"],
            "has_turn_receipt": False if run is None else run.get("turn_receipt") is not None,
            "run_fingerprint": None if run is None else run["fingerprint"],
            "reference_count": referenced_run_counts[run_id],
        })

    notices: list[dict[str, str]] = []
    if linked_reference_count == 0:
        notices.append({
            "category": "no_linked_turns",
            "severity": "WARN",
            "reason": "copy_contains_no_persisted_exact_turn_lineage",
        })
    all_findings = [*archive_issues, *turn_findings, *run_findings, *notices]
    severity_counts = Counter(item["severity"] for item in all_findings)
    status = "ERROR" if severity_counts["ERROR"] else "WARN" if severity_counts["WARN"] else "OK"
    turn_counts = Counter(item["category"] for item in turn_findings)
    run_counts = Counter(item["category"] for item in run_findings)

    report: dict[str, Any] = {
        "schema": SCHEMA,
        "format_version": FORMAT_VERSION,
        "status": status,
        "read_only": True,
        "no_file_access": True,
        "no_write": True,
        "execute": False,
        "report_content_free": True,
        "inputs": {
            "history": {
                "name": "conversations.json",
                "sha256": expected_history,
                "bytes": len(history_raw),
                "version": archive["version"],
                "conversation_count": len(archive["conversations"]),
                "message_count": message_count,
            },
            "work_sessions": {
                "record_count": len(copied_runs),
                "bytes": run_bytes,
                "manifest_schema": MANIFEST_SCHEMA,
                "manifest_sha256": manifest_sha256,
            },
            "supplied_manifest_verified": True,
            "source_archive_completeness_verified": False,
        },
        "coverage": {
            "eligible_assistant_messages": eligible_assistant_count,
            "linked_references": linked_reference_count,
            "compatible_turns": turn_counts["compatible"],
            "legacy_unlinked_turns": turn_counts["legacy_unlinked"],
            "incompatible_linked_turns": sum(
                count for category, count in turn_counts.items() if category not in {"compatible", "legacy_unlinked"}
            ),
            "copied_work_sessions": len(copied_runs),
            "linked_compatible_runs": run_counts["linked_compatible"],
            "orphaned_lineage_runs": run_counts["orphaned_lineage"],
            "legacy_or_incomplete_runs": run_counts["legacy_unlinked"] + run_counts["unlinked_incomplete"],
            "invalid_or_incompatible_runs": sum(
                count for category, count in run_counts.items()
                if category in {"invalid_record", "referenced_ambiguous", "referenced_incompatible"}
            ),
            "turn_categories": dict(sorted(turn_counts.items())),
            "run_categories": dict(sorted(run_counts.items())),
            "severity_counts": {key: severity_counts[key] for key in ("INFO", "WARN", "ERROR")},
        },
        "archive_issues": list(archive_issues),
        "turn_findings": turn_findings,
        "run_findings": run_findings,
        "notices": notices,
        "checks": {
            "history_byte_sha256_verified": True,
            "work_session_manifest_verified": True,
            "work_session_byte_sha256_verified": True,
            "duplicate_json_fields_rejected": True,
            "native_history_versions_accepted": [1, 2, 3, 4, 5],
            "immediate_source_pairing_only": True,
            "latest_or_adjacent_run_fallback": False,
            "turn_reference_revalidated": True,
            "p1_projection_revalidated_count": turn_counts["compatible"],
        },
        "boundaries": {
            "personal_archive_scanned": False,
            "path_discovery_installed": False,
            "input_bytes_retained": False,
            "pairing_inferred": False,
            "model_call_performed": False,
            "provider_call_performed": False,
            "command_executed": False,
            "tool_replayed": False,
            "permission_changed": False,
            "migration_installed": False,
            "apply_installed": False,
            "restore_installed": False,
            "delete_installed": False,
            "compaction_installed": False,
            "production_caller_installed": False,
            "authoritative_writer_installed": False,
        },
        "authority": {
            "compatibility_evidence_available": status != "ERROR",
            "ready_for_authoritative_writer": False,
            "task_success_inferred": False,
            "provider_delivery_verified": False,
            "separate_checkpoint_required": True,
        },
    }
    report["audit_hash"] = _sha256(_canonical(report))
    return report
