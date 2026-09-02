"""Fixed read-only Native skill evidence view, not a lifecycle writer or runner."""
from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import re
from uuid import UUID

from proto_mind.experience_learning_apply import _raw_memory_records
from proto_mind.experience_learning_skill_outcome import ProceduralSkillOutcomeReviewer
from proto_mind.experience_learning_skill_restore_reevaluation import (
    PROCEDURAL_SKILL_POST_RESTORE_CAPTURE_WRITER_INSTALLED, ProceduralSkillRestoreReevaluationReviewer,
)
from proto_mind.experience_pilot import EXPERIENCE_PILOT_MAX_EVENTS, peek_experience_pilot
from proto_mind.models import MemoryRecord
from proto_mind.native_library import MAX_SOURCE_RECORDS, NativeLibrary, _text
from proto_mind.skill_lifecycle_audit import ProceduralSkillLifecycleAudit
from proto_mind.skill_lifecycle_restore_apply import procedural_skill_restore_apply_receipts_snapshot
from proto_mind.skill_lifecycle_restore_receipt_audit import ProceduralSkillRestoreReceiptAudit


SCHEMA = "proto_mind.native_skill_inspection.v1"
_ID = re.compile(r"^[A-Za-z0-9_.:-]{1,200}$")
_HASH = re.compile(r"^[a-f0-9]{64}$")
STORES = ("skills.jsonl", "persistent_memory.json")


def parse_skill_inspection_request(params: dict) -> dict:
    if set(params) - {"conversation_id", "skill_id", "workspace_root", "expected_sha256"}:
        raise ValueError("Skill inspection accepts only a selection; no commands or operations.")
    identifier = params.get("skill_id")
    if not isinstance(identifier, str) or not _ID.fullmatch(identifier):
        raise ValueError("Select an exact skill ID.")
    conversation = params.get("conversation_id", "")
    if conversation != "":
        try:
            conversation = str(UUID(conversation))
        except (ValueError, TypeError, AttributeError) as exc:
            raise ValueError("Invalid selected conversation.") from exc
    expected = params.get("expected_sha256", "")
    if not isinstance(expected, str) or expected and not _HASH.fullmatch(expected):
        raise ValueError("Expected skill-store SHA-256 must be empty or an exact hash.")
    if "workspace_root" in params and (
        not isinstance(params["workspace_root"], str) or not params["workspace_root"].startswith("/")
        or len(params["workspace_root"]) > 4096
    ):
        raise ValueError("Workspace must be an absolute directory path.")
    return {"conversation_id": conversation, "skill_id": identifier, "expected_sha256": expected}


def _findings(values) -> list[str]:
    values = list(dict.fromkeys(values))
    result = [_text(str(value), 1000) for value in values[:32]]
    if len(values) > 32:
        result.append("Further findings omitted from this bounded view; inspect the source separately.")
    return result


def _transition(kind: str, metadata: dict, *, applied_at: str = "") -> dict:
    return {"kind": kind, "occurred_at": applied_at or str(metadata.get("transitioned_at") or ""),
            "id": str(metadata.get("id") or ""),
            "hash": str(metadata.get("metadata_hash") or metadata.get("provenance_hash") or ""),
            "reason": _text(metadata.get("reason", "operator_confirmed_skill_apply"), 1000),
            "evidence_count": len(metadata.get("evidence_event_ids", []))}


class NativeSkillInspection:
    def __init__(self, root: Path, owner: object | None, request: dict, *, workspace: dict | None) -> None:
        self.root, self.owner, self.request, self.workspace = root, owner, request, workspace

    def report(self) -> dict:
        result = {"schema": SCHEMA, "read_only": True, "no_execution": True,
                  "store_mutation_performed": False, "model_call_performed": False,
                  "network_call_performed": False, "retrieval_performed": False,
                  "consent_state_changed": False, "context_injection_changed": False,
                  "permissions_changed": False, "automatic_action": False,
                  "conversation_id": self.request["conversation_id"], "skill_id": self.request["skill_id"],
                  "workspace_path": str(self.workspace["path"]) if self.workspace else "",
                  "status": "UNAVAILABLE", "name": "", "uses_display": "unknown",
                  "skill_store_scope": "global_legacy_stores", "project_isolation_enforced": False,
                  "store_hashes": {}, "changed_since_selection": False,
                  "lifecycle": None, "transitions": [], "restore": None, "outcome": None,
                  "issues": [], "warnings": [], "history_complete": False}
        warnings, issues, raw = result["warnings"], result["issues"], {}
        reader = NativeLibrary(self.root)
        try:
            for name in STORES:
                try:
                    payload, _ = reader._read_bytes(name)
                except FileNotFoundError:
                    raw[name], result["store_hashes"][name] = [], "missing"
                    warnings.append(f"{name} is missing. Viewing does not create it.")
                    continue
                result["store_hashes"][name] = hashlib.sha256(payload).hexdigest()
                if name.endswith(".jsonl"):
                    payload = b"[" + b",".join(line for line in payload.split(b"\n") if line.strip()) + b"]"
                raw[name] = _raw_memory_records(payload)
                if len(raw[name]) > MAX_SOURCE_RECORDS:
                    raise ValueError("Store exceeds the 5000-record inspection limit; no partial verdict.")
            result["changed_since_selection"] = bool(
                self.request["expected_sha256"] and self.request["expected_sha256"] != result["store_hashes"]["skills.jsonl"]
            )
            if result["changed_since_selection"]:
                warnings.append("Skills changed since the library selection. This report uses the fresh bytes.")
            matches = [row for row in raw["skills.jsonl"] if row["id"] == self.request["skill_id"]]
            if not matches:
                result["status"] = "NOT_FOUND"
                warnings.append("The selected skill is no longer present. No fallback selection was made.")
                return result
            record = matches[0]
            memories = [MemoryRecord.from_dict(row) for row in raw["persistent_memory.json"]]
            lifecycle = ProceduralSkillLifecycleAudit.inspect_record(
                record, memories=memories,
                memory_exists=result["store_hashes"]["persistent_memory.json"] != "missing", memory_error="",
            )
            result["name"] = _text(record.get("name"), 200)
            result["uses_display"] = str(record["uses"]) if type(record.get("uses")) is int else "unknown"
            result["lifecycle"] = lifecycle.to_dict()
            issues.extend(lifecycle.issues)
            warnings.extend(lifecycle.warnings)
            if lifecycle.restart_safe:
                result["transitions"].append(_transition("apply", record["provenance"], applied_at=lifecycle.applied_at))
                if lifecycle.state == "archived_verified":
                    result["transitions"].append(_transition("archive", record["lifecycle"]))
                elif lifecycle.state == "active_restored_verified":
                    metadata = record["lifecycle"]
                    result["transitions"].extend([
                        _transition("archive", metadata["prior_archive_envelope"]), _transition("restore", metadata),
                    ])
                    audit = ProceduralSkillRestoreReceiptAudit(
                        skills_path=self.root / "proto_mind/data/skills.jsonl",
                        persistent_memory_path=self.root / "proto_mind/data/persistent_memory.json",
                        process_receipts=procedural_skill_restore_apply_receipts_snapshot(),
                    ).inspect_record(record, lifecycle)
                    result["restore"] = {key: getattr(audit, key) for key in (
                        "status", "evidence_id", "evidence_hash", "restore_metadata_id", "restore_metadata_hash",
                        "process_receipt_status", "process_receipt_id", "process_receipt_hash",
                        "current_state_verified", "restart_safe", "original_apply_receipt_reconstructed", "process_receipt_persisted",
                    )}
                    issues.extend(audit.issues); warnings.extend(audit.warnings)
            result["outcome"] = self._outcome(record, memories, lifecycle)
            issues.extend(result["outcome"]["issues"])
            warnings.extend(result["outcome"]["warnings"])
            # Avoid publishing a verdict assembled across an observed store change.
            for name, expected in result["store_hashes"].items():
                try:
                    current, _ = reader._read_bytes(name)
                    current_hash = hashlib.sha256(current).hexdigest()
                except FileNotFoundError:
                    current_hash = "missing"
                if current_hash != expected:
                    raise ValueError(f"{name} changed during inspection. Refresh manually; no stale verdict retained.")
            result["status"] = "ERROR" if issues else "WARN" if warnings or not lifecycle.restart_safe else "OK"
        except (OSError, ValueError, TypeError, KeyError, AttributeError, RecursionError, OverflowError) as exc:
            result.update(status="ERROR", lifecycle=None, transitions=[], restore=None, outcome=None)
            issues.append(f"Evidence cannot be safely inspected: {type(exc).__name__}: {exc}")
        result["issues"], result["warnings"] = _findings(issues), _findings(warnings)
        if len(json.dumps(result, allow_nan=False)) > 512_000:
            raise ValueError("Skill inspection exceeds the bounded response limit; no partial verdict.")
        return result

    def _outcome(self, record: dict, memories: list[MemoryRecord], lifecycle) -> dict:
        pilot = peek_experience_pilot(self.owner) if self.owner is not None else None
        events = pilot.snapshot() if pilot is not None else ()
        result = {"status": "UNAVAILABLE", "scope": "selected_conversation_process_memory",
                  "pilot_available": pilot is not None, "event_count": len(events),
                  "manual_use_count": 0, "signal_count": 0, "signals": [], "checks": {},
                  "pre_restore_use_count": 0, "unbound_post_restore_use_count": 0,
                  "post_restore": lifecycle.state == "active_restored_verified",
                  "uses_metric_ignored": True, "automatic_decision_allowed": False,
                  "post_restore_capture_installed": PROCEDURAL_SKILL_POST_RESTORE_CAPTURE_WRITER_INSTALLED,
                  "issues": [], "warnings": []}
        if len(events) > EXPERIENCE_PILOT_MAX_EVENTS or len(json.dumps(events, allow_nan=False)) > 2 * 1024 * 1024:
            result.update(status="ERROR", issues=["Experience snapshot exceeds its bounded view limit; no partial outcome verdict."])
            return result
        if not lifecycle.restart_safe:
            result["warnings"].append("Outcome verdict unavailable: durable provenance/current lifecycle is not verified.")
            return result
        if not events:
            result["status"] = "NEEDS_POST_RESTORE_EVIDENCE" if result["post_restore"] else "UNAVAILABLE"
            result["warnings"].append("No current-conversation Experience events are available. They are not reconstructed from chat, uses or durable metadata.")
            return result
        if result["post_restore"]:
            review = ProceduralSkillRestoreReevaluationReviewer(
                events, [record], memories, skills_path=self.root / "proto_mind/data/skills.jsonl",
                persistent_memory_path=self.root / "proto_mind/data/persistent_memory.json",
            ).review_snapshot(record["id"])
            result.update(manual_use_count=review.bound_post_restore_manual_use_count,
                          pre_restore_use_count=review.pre_restore_manual_use_count,
                          unbound_post_restore_use_count=review.unbound_post_restore_manual_use_count)
        else:
            review = ProceduralSkillOutcomeReviewer(events, [record], memories).review(record["id"])
            result["manual_use_count"] = review.matching_manual_use_count
        result.update(status=review.status, signals=[asdict(signal) for signal in review.signals],
                      signal_count=len(review.signals), checks=review.checks,
                      issues=_findings(review.issues), warnings=_findings(review.warnings))
        return result
