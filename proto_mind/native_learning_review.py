"""Private Native review UI over the existing supervised learning state machine.

Inspection uses detached fixed-store snapshots. Confirmation calls the same core
decision/proposal/apply sessions as the CLI, never a slash-command dispatcher.
"""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import re
from typing import Any
from uuid import UUID

from proto_mind.experience_learning_apply import (
    LearningMemoryApplyError,
    _raw_memory_records,
    learning_memory_apply_confirmation_token,
)
from proto_mind.experience_learning_bridge import (
    CognitiveLearningBridgeError,
    OperatorReviewedLearningBridge,
)
from proto_mind.experience_learning_decision import (
    LearningDecisionError,
    learning_candidate_hash,
    learning_confirmation_token,
)
from proto_mind.experience_learning_eligibility import (
    LearningEligibilityRequest,
    LearningPromotionEligibilityReviewer,
)
from proto_mind.experience_learning_proposal import (
    LearningProposalError,
    LearningPromotionProposalBuilder,
    learning_proposal_confirmation_token,
)
from proto_mind.experience_pilot import peek_experience_pilot
from proto_mind.models import MemoryRecord
from proto_mind.native_library import NativeLibrary


REVIEW_SCHEMA = "proto_mind.native_learning_review.v1"
PREVIEW_SCHEMA = "proto_mind.native_learning_confirmation.v1"
RESULT_SCHEMA = "proto_mind.native_learning_result.v1"
OPERATIONS = frozenset({"accept", "reject", "propose", "apply"})
MAX_REFERENCES = 20
MAX_REFERENCE_OPTIONS = 100
_IDENTIFIER = re.compile(r"^[A-Za-z0-9_.:-]{1,200}$")


class NativeLearningError(ValueError):
    pass


def _hash(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=True,
                                     allow_nan=False, separators=(",", ":")).encode()).hexdigest()


def _text(value: object, limit: int) -> str:
    return value if isinstance(value, str) and len(value) <= limit and not any(
        ord(char) < 32 and char not in "\n\t" or 0xD800 <= ord(char) <= 0xDFFF for char in value
    ) else ""


def parse_learning_request(params: dict, *, method: str) -> dict:
    allowed = {"conversation_id", "candidate_id", "workspace_root", "memory_ids", "query", "reason"}
    if method != "memory_learning_review":
        allowed.add("operation")
    if method == "memory_learning_confirm":
        allowed.update({"preview_fingerprint", "confirmation_token", "acknowledge_global_memory"})
    if set(params) - allowed:
        raise NativeLearningError("Unexpected learning-review parameter. Nothing was changed.")
    try:
        conversation = str(UUID(params.get("conversation_id", "")))
    except (ValueError, TypeError, AttributeError) as exc:
        raise NativeLearningError("A valid selected conversation is required.") from exc
    candidate = params.get("candidate_id")
    if not isinstance(candidate, str) or not _IDENTIFIER.fullmatch(candidate):
        raise NativeLearningError("A bounded exact candidate ID is required.")
    memory_ids = params.get("memory_ids", [])
    if not isinstance(memory_ids, list) or len(memory_ids) > MAX_REFERENCES or any(
        not isinstance(value, str) or not _IDENTIFIER.fullmatch(value) for value in memory_ids
    ) or len(set(memory_ids)) != len(memory_ids):
        raise NativeLearningError("Select at most 20 distinct exact memory IDs.")
    query, reason = params.get("query", ""), params.get("reason", "")
    if not isinstance(query, str) or _text(query, 200) != query:
        raise NativeLearningError("Reference search is limited to 200 plain-text characters.")
    if not isinstance(reason, str) or _text(reason, 160) != reason:
        raise NativeLearningError("Decision reason is limited to 160 plain-text characters.")
    operation = params.get("operation", "")
    if method != "memory_learning_review" and (not isinstance(operation, str) or operation not in OPERATIONS):
        raise NativeLearningError("Only accept, reject, propose and one memory apply are supported.")
    return {"conversation_id": conversation, "candidate_id": candidate,
            "memory_ids": list(memory_ids), "query": query, "reason": reason,
            "operation": operation}


class _MemorySnapshot:
    def __init__(self, root: Path, working: list[dict], persistent: list[dict]) -> None:
        self.working_path = root / "proto_mind/data/working_memory.json"
        self.persistent_path = root / "proto_mind/data/persistent_memory.json"
        self.working = self._records(working)
        self.persistent = self._records(persistent)

    @staticmethod
    def _records(rows: list[dict]) -> list[MemoryRecord]:
        records = []
        for row in rows:
            if not isinstance(row.get("timestamp"), str) or not row["timestamp"]:
                raise NativeLearningError("A memory timestamp is missing; review must not invent it.")
            record = MemoryRecord.from_dict(row)
            if not all(isinstance(value, str) for value in (record.id, record.content, record.type, record.source)):
                raise NativeLearningError("Memory identity/content fields are malformed.")
            if type(record.active) is not bool:
                raise NativeLearningError("Memory active state is malformed.")
            records.append(record)
        return records

    def load_working_memory(self):
        return deepcopy(self.working)

    def load_persistent_memory(self):
        return deepcopy(self.persistent)


class _SkillSnapshot:
    def __init__(self, records: list[dict]) -> None:
        self.records = records

    def read_snapshot(self):
        return {"records": deepcopy(self.records), "malformed_count": 0,
                "error": "", "mutation_performed": False}


class NativeLearningReview:
    def __init__(self, root: Path, owner: object | None, request: dict, *, workspace: dict | None,
                 native_apply_used: bool = False) -> None:
        self.root, self.owner, self.request = root, owner, request
        self.workspace, self.native_apply_used = workspace, native_apply_used
        self.pilot = peek_experience_pilot(owner) if owner is not None else None
        self.events = self.pilot.snapshot() if self.pilot is not None else ()
        self.issues: list[str] = []
        self.candidates = {}
        try:
            bridge = OperatorReviewedLearningBridge(self.events)
            doctor = bridge.doctor()
            self.issues.extend(doctor.issues)
            self.candidates = {candidate.id: candidate for review in bridge.review() for candidate in review.candidates}
        except CognitiveLearningBridgeError as exc:
            self.issues.append(str(exc))
        self.candidate = self.candidates.get(request["candidate_id"])
        self.decision = self.pilot.learning_decisions.get(request["candidate_id"]) if self.pilot else None
        self.proposal = self.pilot.learning_proposals.get(request["candidate_id"]) if self.pilot else None
        self.applied = self.pilot.learning_applies.get(request["candidate_id"]) if self.pilot else None
        if self.proposal and request["memory_ids"] and request["memory_ids"] != list(self.proposal.requested_memory_ids):
            self.issues.append("Reference selection no longer matches the already-confirmed proposal.")
        self.hashes: dict[str, str] = {}
        self.memory = None
        self.skills = None
        try:
            library = NativeLibrary(root)
            raw = {}
            for name in ("working_memory.json", "persistent_memory.json", "skills.jsonl"):
                try:
                    payload, _ = library._read_bytes(name)
                except FileNotFoundError:
                    raw[name], self.hashes[name] = [], "missing"
                    continue
                self.hashes[name] = hashlib.sha256(payload).hexdigest()
                if name.endswith("jsonl"):
                    payload = b"[" + b",".join(line for line in payload.splitlines() if line.strip()) + b"]"
                raw[name] = _raw_memory_records(payload)
            self.memory = _MemorySnapshot(root, raw["working_memory.json"], raw["persistent_memory.json"])
            self.skills = _SkillSnapshot(raw["skills.jsonl"])
        except (OSError, ValueError, TypeError, RecursionError, OverflowError) as exc:
            self.issues.append(f"Fixed local stores cannot be reviewed safely: {type(exc).__name__}: {exc}")

    @property
    def reference_ids(self) -> list[str]:
        return list(self.proposal.requested_memory_ids) if self.proposal else self.request["memory_ids"]

    def _eligibility(self):
        if self.candidate is None or self.memory is None or self.skills is None:
            return None
        return LearningPromotionEligibilityReviewer(memory_store=self.memory, skill_library=self.skills).review(
            self.candidate, self.decision, target="memory", memory_ids=self.reference_ids,
        )

    def _apply_review(self):
        if self.pilot is None or self.proposal is None or self.memory is None or self.skills is None:
            return None
        return self.pilot.learning_applies.review(
            self.proposal, candidates=self.candidates, decisions=self.pilot.learning_decisions,
            memory_store=self.memory, skill_library=self.skills,
        )

    def _receipt(self, kind: str, value, *, memory_store=None) -> dict | None:
        if value is None:
            return None
        raw = value.to_dict()
        created = raw.get("created_at", raw.get("applied_at", ""))
        status = raw.get("decision", "created" if kind == "proposal" else "applied")
        verification = "not_applicable"
        warnings = []
        if kind == "apply":
            if memory_store is None and self.memory is None:
                verification, warnings = "ERROR", ["The current memory store could not be inspected safely."]
            else:
                doctor = self.pilot.learning_applies.doctor(memory_store or self.memory)
                verification, warnings = doctor.status, [*doctor.issues, *doctor.warnings]
        return {"kind": kind, "id": raw["id"], "candidate_id": raw["candidate_id"],
                "created_at": created, "status": status,
                "target_schema": raw.get("target_schema", ""),
                "content": raw.get("proposed_payload", {}).get("content", ""),
                "record_id": raw.get("created_record_id", ""),
                "durable_provenance_id": raw.get("durable_provenance_id", ""),
                "receipt_hash": raw.get("receipt_hash", raw.get("proposal_hash", raw.get("candidate_hash", ""))),
                "before_store_sha256": raw.get("before_store_sha256", ""),
                "after_store_sha256": raw.get("after_store_sha256", ""),
                "rollback_suggestion": raw.get("rollback_suggestion", ""),
                "verification_status": verification, "warnings": warnings,
                "process_memory_only": True,
                "details": json.dumps(raw, ensure_ascii=False, sort_keys=True, indent=2)}

    def _references(self) -> tuple[list[dict], int]:
        if self.memory is None:
            return [], 0
        rows = [("working", row) for row in self.memory.working] + [("persistent", row) for row in self.memory.persistent]
        counts = Counter(row.id for _, row in rows)
        query = self.request["query"].casefold().strip()
        options = []
        for store, row in rows:
            if not row.active or query and query not in f"{row.id} {row.content}".casefold():
                continue
            options.append({"id": f"{store}:{row.id}", "record_id": row.id, "store": store,
                            "preview": " ".join(row.content.split())[:160],
                            "selectable": counts[row.id] == 1 and bool(_IDENTIFIER.fullmatch(row.id))})
        return options[:MAX_REFERENCE_OPTIONS], max(0, len(options) - MAX_REFERENCE_OPTIONS)

    def report(self) -> dict:
        eligibility = self._eligibility()
        readiness = self._apply_review()
        references, omitted = self._references()
        return {"schema": REVIEW_SCHEMA, "read_only": True,
                "conversation_id": self.request["conversation_id"], "candidate_id": self.request["candidate_id"],
                "status": "ERROR" if self.issues else "NOT FOUND" if self.candidate is None else "APPLIED" if self.applied else "REVIEW",
                "candidate": self.candidate.to_dict() if self.candidate else None,
                "decision": self._receipt("decision", self.decision),
                "proposal": self._receipt("proposal", self.proposal),
                "apply_receipt": self._receipt("apply", self.applied),
                "references": references, "omitted_reference_count": omitted,
                "requested_memory_ids": self.reference_ids,
                "eligibility_status": eligibility.status if eligibility else "NOT CHECKED",
                "eligibility_warnings": [*eligibility.issues, *eligibility.warnings] if eligibility else [],
                "apply_status": readiness.status if readiness else "NOT READY",
                "apply_checks": readiness.checks if readiness else {},
                "apply_warnings": [*readiness.issues, *readiness.warnings] if readiness else [],
                "store_hashes": self.hashes,
                "native_apply_slot_available": not self.native_apply_used,
                "project_isolation_enforced": False, "memory_store_scope": "global_legacy_stores",
                "workspace_path": str(self.workspace.get("path", "")) if self.workspace else "",
                "workspace_identity_hash": _hash(self.workspace) if self.workspace else "",
                "issues": self.issues,
                "warnings": ["Reference IDs limit duplicate review, not project access. A saved lesson enters shared global memory.",
                             "Decisions, proposals and detailed receipts expire with the bridge process. Only applied lesson provenance survives restart."],
                "command_execution_performed": False, "model_call_performed": False,
                "network_call_performed": False, "retrieval_performed": False,
                "consent_state_changed": False, "store_mutation_performed": False,
                "automatic_promotion": False}

    def preview(self) -> dict:
        operation = self.request["operation"]
        issues = list(self.issues)
        if self.candidate is None or self.pilot is None:
            issues.append("Candidate is absent from the current consented process-memory evidence. Nothing is recreated.")
        blueprint = None
        readiness = None
        token = ""
        if not issues:
            if operation in {"accept", "reject"}:
                if self.decision is not None:
                    issues.append("Candidate already has a terminal operator decision.")
                elif operation == "accept" and self.candidate.review_status != "operator_review_required":
                    issues.append("Candidate needs more evidence or is blocked; acceptance is unavailable.")
                else:
                    token = learning_confirmation_token(self.candidate)
            elif operation == "propose":
                if self.proposal is not None:
                    issues.append("Candidate already has a process-memory proposal.")
                else:
                    try:
                        blueprint = LearningPromotionProposalBuilder(memory_store=self.memory, skill_library=self.skills).build(
                            self.candidate, self.decision, LearningEligibilityRequest(
                                self.candidate.id, "memory", self.request["memory_ids"], [],
                            ),
                        )
                        token = learning_proposal_confirmation_token(blueprint)
                    except (LearningProposalError, ValueError, TypeError) as exc:
                        issues.append(str(exc))
            elif operation == "apply":
                readiness = self._apply_review()
                if self.native_apply_used:
                    issues.append("This Native bridge process already used its one memory apply slot.")
                if self.applied is not None:
                    issues.append("This candidate was already applied. Inspect its receipt; do not replay it.")
                if readiness is None:
                    issues.append("An explicitly confirmed memory proposal is required first.")
                elif not readiness.confirmable:
                    issues.extend(readiness.issues)
                else:
                    token = learning_memory_apply_confirmation_token(readiness)
        material = {"conversation_id": self.request["conversation_id"], "candidate_id": self.request["candidate_id"],
                    "operation": operation, "workspace": self.workspace, "reason": self.request["reason"],
                    "memory_ids": self.reference_ids, "events_hash": _hash(self.events),
                    "candidate_hash": learning_candidate_hash(self.candidate) if self.candidate else "",
                    "decision": self.decision.to_dict() if self.decision else None,
                    "proposal": self.proposal.to_dict() if self.proposal else None,
                    "apply_receipt": self.applied.to_dict() if self.applied else None,
                    "store_hashes": self.hashes, "native_apply_used": self.native_apply_used,
                    "blueprint": asdict(blueprint) if blueprint else None,
                    "readiness_checks": readiness.checks if readiness else {}, "issues": issues}
        fingerprint = _hash(material)
        if operation == "reject" and not issues:
            token = f"CONFIRM-LEARNING-REJECT-{fingerprint[:12].upper()}"
        return {"schema": PREVIEW_SCHEMA, "read_only": True,
                "conversation_id": self.request["conversation_id"], "candidate_id": self.request["candidate_id"],
                "operation": operation, "ready": not issues, "preview_fingerprint": fingerprint,
                "confirmation_token": token if not issues else "", "issues": issues,
                "future_mutation": "persistent_memory_one_lesson" if operation == "apply" else "process_memory_only",
                "content": self.candidate.text if self.candidate else "",
                "target_schema": "memory.lesson.v1", "requested_memory_ids": self.reference_ids,
                "store_hashes": self.hashes, "requires_global_memory_acknowledgement": operation == "apply",
                "command_execution_performed": False, "model_call_performed": False,
                "network_call_performed": False, "retrieval_performed": False,
                "consent_state_changed": False, "store_mutation_performed": False,
                "automatic_promotion": False}

    def confirm(self, params: dict) -> dict:
        preview = self.preview()
        if not preview["ready"]:
            raise NativeLearningError("Confirmation refused: " + "; ".join(preview["issues"]))
        if params.get("preview_fingerprint") != preview["preview_fingerprint"]:
            raise NativeLearningError("Evidence, selection, workspace or store changed. Preview again; nothing was changed.")
        if params.get("confirmation_token") != preview["confirmation_token"]:
            raise NativeLearningError("Exact confirmation token mismatch. Nothing was changed.")
        operation = self.request["operation"]
        try:
            if operation in {"accept", "reject"}:
                receipt = self.pilot.learning_decisions.decide(
                    self.candidate, "accepted" if operation == "accept" else "rejected",
                    token=params["confirmation_token"], reason=self.request["reason"],
                )
                kind = "decision"
            elif operation == "propose":
                blueprint = LearningPromotionProposalBuilder(memory_store=self.memory, skill_library=self.skills).build(
                    self.candidate, self.decision, LearningEligibilityRequest(
                        self.candidate.id, "memory", self.request["memory_ids"], [],
                    ),
                )
                receipt = self.pilot.learning_proposals.create(blueprint, token=params["confirmation_token"])
                kind = "proposal"
            else:
                if params.get("acknowledge_global_memory") is not True:
                    raise NativeLearningError("Acknowledge that this one lesson enters shared global memory before applying.")
                store = getattr(getattr(self.owner, "memory_keeper", None), "store", None)
                if store is None or store.persistent_path != self.memory.persistent_path or store.working_path != self.memory.working_path:
                    raise NativeLearningError("The existing Native memory writer does not match the fixed core store.")
                receipt = self.pilot.learning_applies.apply(
                    self.proposal, token=params["confirmation_token"], candidates=self.candidates,
                    decisions=self.pilot.learning_decisions, memory_store=store, skill_library=self.skills,
                )
                kind = "apply"
        except (LearningDecisionError, LearningProposalError, LearningMemoryApplyError) as exc:
            raise NativeLearningError(str(exc)) from exc
        return {"schema": RESULT_SCHEMA, "conversation_id": self.request["conversation_id"],
                "candidate_id": self.request["candidate_id"], "operation": operation,
                "receipt": self._receipt(kind, receipt, memory_store=store if kind == "apply" else None),
                "mutation": "persistent_memory_one_lesson" if operation == "apply" else "process_memory_only",
                "memory_mutation_performed": operation == "apply", "skill_mutation_performed": False,
                "command_execution_performed": False, "model_call_performed": False,
                "network_call_performed": False, "retrieval_performed": False, "consent_state_changed": False,
                "automatic_promotion": False, "batch_apply_performed": False}
