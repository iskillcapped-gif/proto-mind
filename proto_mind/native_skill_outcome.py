"""Native manual-outcome form over the existing consented process-only capture gate."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from proto_mind.experience_learning_apply import _raw_memory_records
from proto_mind.experience_learning_skill_outcome_capture import (
    PROCEDURAL_SKILL_OUTCOME_CAPTURE_MAX_RECEIPTS,
    ProceduralSkillOutcomeCaptureBuilder, ProceduralSkillOutcomeCaptureError,
    is_valid_procedural_skill_outcome_event_batch,
    procedural_skill_outcome_capture_confirmation_token,
    procedural_skill_outcome_capture_receipt_hash,
)
from proto_mind.experience_pilot import peek_experience_pilot
from proto_mind.native_learning_review import _MemorySnapshot, _SkillSnapshot
from proto_mind.native_library import MAX_SOURCE_RECORDS, NativeLibrary, _text
from proto_mind.native_skill_authoring import _hash
from proto_mind.native_skill_inspection import parse_skill_inspection_request


METHODS = frozenset({"skill_outcome_review", "skill_outcome_preview", "skill_outcome_confirm"})
STORES = ("skills.jsonl", "persistent_memory.json", "context_injection.json")


def parse_skill_outcome_request(params: dict, *, method: str) -> dict:
    fields = {"conversation_id", "skill_id", "workspace_root", "expected_sha256"}
    allowed = fields.copy()
    if method != "skill_outcome_review":
        allowed.update({"outcome", "evidence"})
    if method == "skill_outcome_confirm":
        allowed.update({"preview_fingerprint", "confirmation_token", "acknowledge_manual_only"})
    if method not in METHODS or set(params) - allowed:
        raise ValueError("Only fixed manual-outcome form parameters are supported.")
    result = parse_skill_inspection_request({key: value for key, value in params.items() if key in fields})
    if not result["conversation_id"]:
        raise ValueError("Select a conversation before recording a manual skill outcome.")
    if method != "skill_outcome_review":
        evidence = params.get("evidence")
        if params.get("outcome") not in ("success", "failure"):
            raise ValueError("Outcome must be success or failure; no execution or lifecycle operation is supported.")
        if not isinstance(evidence, str) or not evidence.strip() or len(evidence) > 800 or any(
            (ord(char) < 32 and char not in "\n\t") or 0xD800 <= ord(char) <= 0xDFFF for char in evidence
        ):
            raise ValueError("Describe the manual result in 1 to 800 characters, without control characters.")
        result.update(outcome=params["outcome"], evidence=evidence)
    return result


def _boundary(*, read_only: bool) -> dict:
    return {"read_only": read_only, "no_execution": True, "store_mutation_performed": False,
            "model_call_performed": False, "network_call_performed": False, "retrieval_performed": False,
            "context_injection_changed": False, "permissions_changed": False, "consent_state_changed": False,
            "automatic_promotion": False, "session_log_mutation_performed": False,
            "skill_mutation_performed": False, "memory_mutation_performed": False}


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key in Context Injection settings.")
        result[key] = value
    return result


def _invalid_number(_):
    raise ValueError("Non-finite number in Context Injection settings.")


class NativeSkillOutcome:
    def __init__(self, root: Path, owner: object | None, request: dict, *, workspace: dict | None) -> None:
        self.root, self.request, self.workspace = root, request, workspace
        self.pilot = peek_experience_pilot(owner) if owner is not None else None
        self.events = self.pilot.snapshot() if self.pilot else ()
        self.receipts = self.pilot.skill_outcome_captures.snapshot() if self.pilot else ()
        self.hashes: dict[str, str] = {}
        self.issues: list[str] = []
        self.source_reason = "Source stores are unavailable."
        self.eligible = self.context_disabled = False
        self.name = ""
        self.builder = None
        try:
            if len(self.events) > 256 or len(self.receipts) > PROCEDURAL_SKILL_OUTCOME_CAPTURE_MAX_RECEIPTS or len(
                json.dumps([self.events, self.receipts], allow_nan=False)
            ) > 2 * 1024 * 1024:
                raise ValueError("Existing process evidence exceeds its bounded view limit.")
            raw = {}
            reader = NativeLibrary(root)
            for name in STORES:
                payload, _ = reader._read_bytes(name)
                self.hashes[name] = hashlib.sha256(payload).hexdigest()
                if name == "context_injection.json":
                    settings = json.loads(payload, object_pairs_hook=_unique_object, parse_constant=_invalid_number)
                    self.context_disabled = isinstance(settings, dict) and settings.get("enabled") is False
                    continue
                if name.endswith("jsonl"):
                    payload = b"[" + b",".join(line for line in payload.split(b"\n") if line.strip()) + b"]"
                raw[name] = _raw_memory_records(payload)
                if len(raw[name]) > MAX_SOURCE_RECORDS:
                    raise ValueError("Store exceeds the 5000-record review limit.")
            memory = _MemorySnapshot(root, [], raw["persistent_memory.json"])
            skills = _SkillSnapshot(raw["skills.jsonl"])
            self.builder = ProceduralSkillOutcomeCaptureBuilder(memory_store=memory, skill_library=skills)
            self.eligible, self.source_reason = self.builder.current_skill_is_valid(request["skill_id"])
            selected = next((row for row in raw["skills.jsonl"] if row["id"] == request["skill_id"]), {})
            self.name = _text(selected.get("name"), 200)
            self._check_sources()
        except (OSError, ValueError, TypeError, KeyError, RecursionError, OverflowError) as exc:
            self.issues.append(f"Local evidence cannot be safely reviewed: {type(exc).__name__}: {exc}")
            self.builder = None
            self.eligible = False

    def _check_sources(self) -> None:
        reader = NativeLibrary(self.root)
        for name, expected in self.hashes.items():
            payload, _ = reader._read_bytes(name)
            if hashlib.sha256(payload).hexdigest() != expected:
                raise ValueError(f"{name} changed during review. Preview again; no outcome recorded.")

    def verified_guidance(self, record: dict) -> tuple[dict, object]:
        """Shared eligibility boundary for manual and automatic procedure guidance."""
        from copy import deepcopy
        from proto_mind.experience_learning_skill_authoring import _validate_authored_contract
        from proto_mind.native_skill_authoring import parse_skill_request
        from proto_mind.skill_lifecycle_audit import ProceduralSkillLifecycleAudit

        if self.builder is None or self.issues or not self.context_disabled:
            raise ValueError("Current skill sources and disabled Context Injection must be verifiable.")
        lifecycle = ProceduralSkillLifecycleAudit.inspect_record(
            record, memories=self.builder.memory_store.load_persistent_memory(), memory_exists=True, memory_error="")
        if (lifecycle.state not in {"active_verified", "active_restored_verified"} or lifecycle.issues
                or lifecycle.source_status != "current" or not lifecycle.restart_safe or record.get("executable") is not False):
            raise ValueError("Only active, current-provenance verified procedures can guide a task. "
                             + "; ".join(lifecycle.issues or [lifecycle.state]))
        contract = deepcopy(record["provenance"]["authored_contract"])
        _validate_authored_contract(contract)
        parse_skill_request({"conversation_id": self.request["conversation_id"],
                             "lesson_id": record["provenance"]["source_lesson_id"],
                             "authored": contract}, method="skill_authoring_review")
        return contract, lifecycle

    def _identity(self) -> dict:
        return {"conversation_id": self.request["conversation_id"], "skill_id": self.request["skill_id"],
                "workspace_path": str(self.workspace["path"]) if self.workspace else ""}

    def _reasons(self) -> list[str]:
        reasons = list(self.issues)
        if not self.eligible:
            reasons.append(self.source_reason)
        if not self.context_disabled:
            reasons.append("Context Injection must be explicitly disabled in readable local settings. Nothing is changed automatically.")
        if self.pilot is None or self.pilot.state != "consented":
            reasons.append("Exact Experience consent is required in this conversation. Viewing never starts or enables capture.")
        if self.pilot is not None and self.pilot.event_count + 4 > self.pilot.max_events:
            reasons.append("Not enough capacity for the four-event manual outcome; no partial batch is allowed.")
        if len(self.receipts) >= PROCEDURAL_SKILL_OUTCOME_CAPTURE_MAX_RECEIPTS:
            reasons.append("The 16-receipt process-memory capture limit is reached.")
        return reasons

    def _receipt(self, raw: dict) -> dict:
        by_id = {event["id"]: event for event in self.events}
        linked = [by_id.get(identifier) for identifier in raw["event_ids"]]
        verified = (raw["receipt_hash"] == procedural_skill_outcome_capture_receipt_hash(raw)
                    and len(linked) == 4 and all(linked)
                    and is_valid_procedural_skill_outcome_event_batch(linked)
                    and all(event["session_id"] == raw["session_id"] for event in linked))
        return {**{key: raw[key] for key in ("id", "created_at", "session_id", "skill_id", "outcome", "evidence_preview",
                                           "evidence_fingerprint", "blueprint_hash", "receipt_hash", "event_ids",
                                           "operator_reported", "manual_operator_use", "execution_performed_by_proto_mind",
                                           "process_memory_only", "restart_expiring", "persistence_performed")},
                "verification_status": "VERIFIED" if verified else "ERROR"}

    def report(self) -> dict:
        reasons = self._reasons()
        return {"schema": "proto_mind.native_skill_outcome_review.v1", **self._identity(), **_boundary(read_only=True),
                "status": "ERROR" if self.issues else "NOT_READY" if reasons else "READY", "name": self.name,
                "source_eligible": self.eligible, "capture_available": not reasons,
                "pilot_state": self.pilot.state if self.pilot else "not_started",
                "session_id": self.pilot.session_id if self.pilot else "", "context_injection_disabled": self.context_disabled,
                "event_count": len(self.events), "event_limit": self.pilot.max_events if self.pilot else 256,
                "receipt_count": len(self.receipts), "receipt_limit": PROCEDURAL_SKILL_OUTCOME_CAPTURE_MAX_RECEIPTS,
                "receipts": [self._receipt(raw) for raw in reversed(self.receipts) if raw["skill_id"] == self.request["skill_id"]],
                "store_hashes": self.hashes,
                "changed_since_selection": bool(self.request["expected_sha256"] and
                                                self.request["expected_sha256"] != self.hashes.get("skills.jsonl")),
                "skill_store_scope": "global_legacy_stores", "project_isolation_enforced": False,
                "reasons": reasons, "issues": self.issues}

    def preview(self) -> dict:
        reasons = self._reasons()
        blueprint = None
        if not reasons:
            try:
                blueprint = self.builder.build(session_id=self.pilot.session_id, skill_id=self.request["skill_id"],
                                               outcome=self.request["outcome"], evidence=self.request["evidence"])
                if self.pilot.skill_outcome_captures.get(f"skilloutcap_{blueprint.blueprint_hash[:16]}"):
                    reasons.append("This exact manual outcome is already recorded. Inspect its receipt; do not replay.")
                self._check_sources()
            except (OSError, ValueError, TypeError, ProceduralSkillOutcomeCaptureError) as exc:
                reasons.append(str(exc))
        material = {"request": self.request, "workspace": self.workspace, "store_hashes": self.hashes,
                    "session_id": self.pilot.session_id if self.pilot else "", "pilot_state": self.pilot.state if self.pilot else "",
                    "events": self.events, "receipts": self.receipts,
                    "blueprint": blueprint.to_dict() if blueprint else None, "reasons": reasons}
        return {"schema": "proto_mind.native_skill_outcome_preview.v1", **self._identity(), **_boundary(read_only=True),
                "ready": not reasons, "reasons": reasons, "preview_fingerprint": _hash(material),
                "session_id": self.pilot.session_id if self.pilot else "",
                "blueprint_hash": blueprint.blueprint_hash if blueprint else "",
                "confirmation_token": procedural_skill_outcome_capture_confirmation_token(blueprint) if not reasons else "",
                "outcome": self.request["outcome"], "evidence_preview": blueprint.evidence_preview if blueprint else "",
                "evidence_fingerprint": blueprint.evidence_fingerprint if blueprint else "",
                "evidence_input_chars": blueprint.evidence_input_chars if blueprint else 0,
                "future_mutation": "process_memory_four_events_one_receipt", "operator_reported": True,
                "requires_manual_acknowledgement": True, "process_memory_only": True, "restart_expiring": True,
                "store_hashes": self.hashes}

    def confirm(self, params: dict) -> dict:
        preview = self.preview()
        if not preview["ready"]:
            raise ValueError("Manual outcome refused: " + "; ".join(preview["reasons"]))
        if params.get("preview_fingerprint") != preview["preview_fingerprint"]:
            raise ValueError("Form, source stores, consent, events or workspace changed. Preview again; no outcome recorded.")
        if params.get("confirmation_token") != preview["confirmation_token"]:
            raise ValueError("Exact manual-outcome token mismatch. No outcome recorded.")
        if params.get("acknowledge_manual_only") is not True:
            raise ValueError("Acknowledge operator-reported, process-only evidence before confirming.")
        self._check_sources()
        try:
            blueprint = self.builder.build(session_id=self.pilot.session_id, skill_id=self.request["skill_id"],
                                           outcome=self.request["outcome"], evidence=self.request["evidence"])
            receipt = self.pilot.skill_outcome_captures.capture(
                blueprint, token=params["confirmation_token"], pilot_state=self.pilot.state,
                append_events=self.pilot.append_supervised_manual_skill_outcome_events,
            )
        except ProceduralSkillOutcomeCaptureError as exc:
            raise ValueError(str(exc)) from exc
        self.events = self.pilot.snapshot()
        return {"schema": "proto_mind.native_skill_outcome_result.v1", **self._identity(), **_boundary(read_only=False),
                "mutation": "process_memory_four_events_one_receipt", "events_appended": 4,
                "receipt": self._receipt(receipt.to_dict())}
