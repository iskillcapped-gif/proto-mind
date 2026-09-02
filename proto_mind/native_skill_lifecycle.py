"""Native entry to existing exact keep/durable-archive gates, never a new writer."""
from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import re

from proto_mind.experience_learning_skill_lifecycle_apply import (
    ProceduralSkillLifecycleApplyError, procedural_skill_lifecycle_apply_confirmation_token,
)
from proto_mind.experience_learning_skill_lifecycle_metadata_apply import (
    ProceduralSkillLifecycleMetadataApplyError, procedural_skill_lifecycle_metadata_apply_confirmation_token,
)
from proto_mind.experience_learning_skill_lifecycle_readiness import ProceduralSkillLifecycleApplyReadiness
from proto_mind.native_library import NativeLibrary
from proto_mind.native_skill_authoring import _hash
from proto_mind.native_skill_decision import NativeSkillDecision
from proto_mind.native_skill_inspection import _findings, parse_skill_inspection_request
from proto_mind.native_skill_outcome import _boundary
from proto_mind.native_work_sessions import workspace_identity


METHODS = frozenset({"skill_lifecycle_review", "skill_lifecycle_preview", "skill_lifecycle_confirm"})
ARCHIVE_FIELDS = ["lifecycle", "status", "updated_at"]


def parse_skill_lifecycle_request(params: dict, *, method: str) -> dict:
    fields = {"conversation_id", "skill_id", "workspace_root", "expected_sha256"}
    allowed = fields | {"decision_receipt_id"}
    if method == "skill_lifecycle_confirm":
        allowed |= {"preview_fingerprint", "confirmation_token", "acknowledge_global_skills"}
    if method not in METHODS or set(params) - allowed:
        raise ValueError("Only an exact existing lifecycle decision is supported; no revision, restore, command or batch.")
    result = parse_skill_inspection_request({key: value for key, value in params.items() if key in fields})
    identifier = params.get("decision_receipt_id")
    if not result["conversation_id"] or not isinstance(identifier, str) or not re.fullmatch(r"skilloutdec_[a-f0-9]{16}", identifier):
        raise ValueError("Select the current conversation and exact decision receipt before reviewing application.")
    result["decision_receipt_id"] = identifier
    return result


class NativeSkillLifecycle:
    def __init__(self, root: Path, owner: object | None, request: dict, *, workspace: dict | None,
                 native_apply_used: bool = False) -> None:
        self.root, self.owner, self.request, self.workspace = root, owner, request, workspace
        self.native_apply_used, self.apply_attempted = native_apply_used, False
        self.decision_view = NativeSkillDecision(root, owner, request, workspace=workspace)
        self.source, self.pilot = self.decision_view.source, self.decision_view.pilot
        self.decision = self.pilot.skill_outcome_decisions.get(request["decision_receipt_id"]) if self.pilot else None
        self.choice = self.decision.decision if self.decision else "unknown"
        self.session = (self.pilot.skill_lifecycle_metadata_applies if self.choice == "archive" else
                        self.pilot.skill_lifecycle_applies) if self.pilot else None
        self.applied = self.session.get(request["decision_receipt_id"]) if self.session else None
        self.snapshots = self._apply_snapshots()
        self.issues = list(self.source.issues)
        self.reviewer = self.review = None
        self.stored_status = "unavailable"
        try:
            if any(len(rows) > 1 for rows in self.snapshots) or len(json.dumps(self.snapshots, allow_nan=False)) > 256_000:
                raise ValueError("Lifecycle receipts exceed the bounded process review limit.")
            if self.decision_view.builder is not None:
                builder = self.decision_view.builder
                builder.skill_library.skills_path = root / "proto_mind/data/skills.jsonl"
                builder.memory_store.expected_persistent_sha256 = self.source.hashes.get("persistent_memory.json")
                self.reviewer = ProceduralSkillLifecycleApplyReadiness(builder=builder, skill_library=builder.skill_library)
                rows = builder.skill_library.read_snapshot()["records"]
                record = next((row for row in rows if row.get("id") == request["skill_id"]), {})
                self.stored_status = str(record.get("status", "unavailable"))
                if self.decision is not None:
                    self.review = self.session.review(self.decision, reviewer=self.reviewer)
            self.decision_view._check_current()
            self._validate_dependencies()
        except (OSError, ValueError, TypeError, KeyError, AttributeError, RecursionError, OverflowError,
                ProceduralSkillLifecycleApplyError, ProceduralSkillLifecycleMetadataApplyError) as exc:
            self.issues.append(f"Lifecycle state cannot be safely reviewed: {type(exc).__name__}: {exc}")

    def _apply_snapshots(self) -> tuple:
        return (self.pilot.skill_lifecycle_applies.snapshot(), self.pilot.skill_lifecycle_metadata_applies.snapshot()) if self.pilot else ((), ())

    def _validate_dependencies(self) -> None:
        # The shared writer compares skill bytes itself; other dependencies must also stay current after writing.
        reader = NativeLibrary(self.root)
        for name, expected in self.source.hashes.items():
            if name != "skills.jsonl" and hashlib.sha256(reader._read_bytes(name)[0]).hexdigest() != expected:
                raise ValueError(f"{name} changed during lifecycle review/application.")
        if self.pilot and (self.pilot.state != self.decision_view.pilot_state or self.pilot.snapshot() != self.source.events
                           or self.pilot.skill_outcome_captures.snapshot() != self.source.receipts
                           or self.pilot.skill_outcome_decisions.snapshot() != self.decision_view.decisions):
            raise ValueError("Conversation evidence or consent state changed; no new lifecycle authority.")
        if self.workspace and workspace_identity(Path(self.workspace["path"])) != self.workspace:
            raise ValueError("Workspace identity changed; inspect the selected folder again.")

    def _reasons(self) -> list[str]:
        reasons = list(self.issues)
        if not self.source.context_disabled:
            reasons.append("Readable explicitly disabled Context Injection is required. No automatic setting change.")
        if self.decision is None or self.decision.skill_id != self.request["skill_id"]:
            reasons.append("The exact terminal decision is absent in this conversation's current process.")
        if self.applied:
            reasons.append("This decision was already applied. Inspect the receipt; no replay.")
        if self.native_apply_used or any(self.snapshots):
            reasons.append("The single Native lifecycle apply attempt is already used. Inspect receipts/state; no automatic retry.")
        if self.choice not in {"keep", "archive"}:
            reasons.append("Only keep or durable archive is supported. Revision and restore need separate workflows.")
        if not self.source.eligible:
            reasons.append(self.source.source_reason)
        if self.decision:
            receipt = self.decision_view._receipt(self.decision.to_dict())
            if receipt["verification_status"] != "VERIFIED" or receipt["evidence_state"] != "CURRENT":
                reasons.append("Decision integrity/current evidence is not verified. Historical decisions are not apply authority.")
        if self.review is None:
            reasons.append("The existing lifecycle gate could not be reviewed.")
        elif not self.review.confirmable:
            reasons.extend(self.review.issues)
        return _findings(reasons)

    def _base(self, kind: str, *, read_only: bool = True, changed: bool = False) -> dict:
        return {"schema": f"proto_mind.native_skill_lifecycle_{kind}.v1", **self.source._identity(),
                "decision_receipt_id": self.request["decision_receipt_id"], **_boundary(read_only=read_only),
                "store_mutation_performed": changed, "skill_mutation_performed": changed,
                "experience_mutation_performed": False, "batch_apply_performed": False}

    def _receipt(self) -> dict | None:
        if self.applied is None:
            return None
        raw = self.applied.to_dict()
        audit = self.session.doctor(reviewer=self.reviewer) if self.reviewer else None
        verified = audit is not None and not audit.issues
        rows = self.reviewer.skill_library.read_snapshot()["records"] if self.reviewer else []
        record = next((row for row in rows if row.get("id") == self.request["skill_id"]), None)
        current = verified and record is not None and _hash(record) == raw["after_record_hash"]
        return {"id": raw.get("lifecycle_apply_id", raw.get("id")), "skill_id": raw["skill_id"],
                "decision_receipt_id": raw["decision_receipt_id"], "decision": self.choice,
                "applied_at": raw["applied_at"], "decision_hash": raw["decision_hash"],
                **{key: raw[key] for key in ("before_store_sha256", "after_store_sha256", "before_record_hash", "after_record_hash",
                                           "confirmation_token_hash", "receipt_hash", "post_state_verified",
                                           "durable_provenance_preserved", "persistent_memory_unchanged")},
                "actual_record_mutations": raw.get("exact_record_mutations", raw.get("actual_record_mutations")),
                "changed_fields": raw.get("changed_fields", raw.get("allowed_changed_fields")),
                "metadata_id": raw.get("metadata_id", ""), "metadata_hash": raw.get("metadata_hash", ""),
                "verification_status": "VERIFIED" if verified else "ERROR" if audit else "UNAVAILABLE",
                "evidence_state": "CURRENT" if current else "HISTORICAL" if verified else "UNAVAILABLE",
                "detailed_receipt_persistence": "process_memory_only",
                "lifecycle_metadata_persistence": "skill_record" if self.choice == "archive" else "none",
                "warnings": _findings([*(audit.issues if audit else []), *(audit.warnings if audit else []),
                                        "Detailed receipt expires on restart; archive metadata survives in the skill. Restore is a separate gate."]),
                "details": json.dumps(raw, ensure_ascii=False, sort_keys=True, indent=2)}

    def report(self) -> dict:
        reasons = self._reasons()
        return {**self._base("review"), "status": "ERROR" if self.issues else "APPLIED" if self.applied else "READY" if not reasons else "NOT_READY",
                "name": self.source.name, "decision": self.choice, "stored_skill_status": self.stored_status,
                "decision_hash": self.decision.decision_hash if self.decision else "", "can_apply": not reasons,
                "native_apply_slot_available": not self.native_apply_used and not any(self.snapshots),
                "context_injection_disabled": self.source.context_disabled, "store_hashes": self.source.hashes,
                "checks": self.review.checks if self.review else {}, "reasons": reasons, "issues": _findings(self.issues),
                "warnings": _findings(self.review.warnings if self.review else []), "receipt": self._receipt(),
                "skill_store_scope": "global_legacy_stores", "project_isolation_enforced": False}

    def preview(self) -> dict:
        reasons = self._reasons()
        if not reasons:
            try:
                self.decision_view._check_current()
                self._validate_dependencies()
                if self._apply_snapshots() != self.snapshots:
                    raise ValueError("Lifecycle apply state changed; preview again.")
            except (OSError, ValueError) as exc:
                reasons.append(str(exc))
        token = ""
        if not reasons:
            token = (procedural_skill_lifecycle_metadata_apply_confirmation_token(self.review) if self.choice == "archive"
                     else procedural_skill_lifecycle_apply_confirmation_token(self.review))
        material = {"request": self.request, "workspace": self.workspace, "hashes": self.source.hashes,
                    "events": self.source.events, "captures": self.source.receipts, "decisions": self.decision_view.decisions,
                    "pilot_state": self.decision_view.pilot_state, "applies": self.snapshots,
                    "native_apply_used": self.native_apply_used, "review": asdict(self.review) if self.review else None, "reasons": reasons}
        return {**self._base("preview"), "ready": not reasons, "decision": self.choice,
                "decision_hash": self.decision.decision_hash if self.decision else "",
                "preview_fingerprint": _hash(material), "confirmation_token": token, "reasons": _findings(reasons),
                "before_store_sha256": self.review.before_store_sha256 if self.review else "",
                "before_record_hash": self.review.before_record_hash if self.review else "",
                "metadata_blueprint_hash": getattr(self.review, "metadata_blueprint_hash", ""),
                "expected_record_mutations": 1 if self.choice == "archive" else 0,
                "expected_changed_fields": ARCHIVE_FIELDS if self.choice == "archive" else [],
                "future_mutation": "skills_one_durable_archive" if self.choice == "archive" else "process_memory_keep_receipt",
                "requires_global_skills_acknowledgement": True, "store_hashes": self.source.hashes}

    def confirm(self, params: dict) -> dict:
        preview = self.preview()
        if not preview["ready"]:
            raise ValueError("Lifecycle application refused: " + "; ".join(preview["reasons"]))
        if params.get("preview_fingerprint") != preview["preview_fingerprint"]:
            raise ValueError("Lifecycle sources, decision or scope changed. Preview again; no apply attempted.")
        if params.get("confirmation_token") != preview["confirmation_token"]:
            raise ValueError("Exact lifecycle apply token mismatch. No apply attempted.")
        if params.get("acknowledge_global_skills") is not True:
            raise ValueError("Acknowledge the exact shared Skill Library transition before applying.")
        self.decision_view._check_current()
        self._validate_dependencies()
        self.apply_attempted = True
        try:
            self.session.apply(self.decision, token=params["confirmation_token"], reviewer=self.reviewer,
                               validate_dependencies=self._validate_dependencies)
        except (OSError, ValueError, ProceduralSkillLifecycleApplyError, ProceduralSkillLifecycleMetadataApplyError) as exc:
            raise ValueError(f"Lifecycle apply attempt ended: {exc} No automatic retry. Inspect the skill and receipts.") from exc
        refreshed = NativeSkillLifecycle(self.root, self.owner, self.request, workspace=self.workspace, native_apply_used=True)
        receipt = refreshed._receipt()
        if receipt is None:
            raise ValueError("Apply returned but the receipt is unavailable. Do not repeat; inspect the skill.")
        return {**self._base("result", read_only=False, changed=self.choice == "archive"), "decision": self.choice,
                "mutation": preview["future_mutation"], "events_appended": 0, "receipt": receipt}
