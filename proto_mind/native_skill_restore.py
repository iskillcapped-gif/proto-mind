"""Explicit Native restoration through the existing durable skill gate."""
from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
from pathlib import Path

from proto_mind.native_library import NativeLibrary
from proto_mind.native_skill_authoring import _hash
from proto_mind.native_skill_inspection import _findings, parse_skill_inspection_request
from proto_mind.native_skill_outcome import NativeSkillOutcome, _boundary
from proto_mind.native_work_sessions import workspace_identity
from proto_mind.skill_lifecycle_restore_apply import (
    ProceduralSkillRestoreApplyError, procedural_skill_restore_apply_confirmation_token,
    procedural_skill_restore_apply_session,
)


METHODS = frozenset({"skill_restore_review", "skill_restore_preview", "skill_restore_confirm"})
CHANGED_FIELDS = ["lifecycle", "status", "updated_at"]
TOKEN_FIELDS = ("skill_id", "authorization_blueprint_hash", "restore_review_hash", "restore_metadata_blueprint_hash",
                "before_store_sha256", "before_record_hash", "prior_archive_id", "prior_archive_hash",
                "expected_changed_fields", "immutable_record_fields")


def parse_skill_restore_request(params: dict, *, method: str) -> dict:
    fields = {"conversation_id", "skill_id", "workspace_root", "expected_sha256"}
    allowed = fields | ({"preview_fingerprint", "confirmation_token", "acknowledge_global_skills"} if method == "skill_restore_confirm" else set())
    if method not in METHODS or set(params) - allowed:
        raise ValueError("Only an exact skill restoration is supported; no revision, capture, command or batch.")
    selection = parse_skill_inspection_request({key: value for key, value in params.items() if key in fields})
    if not selection["conversation_id"]:
        raise ValueError("Select a conversation before reviewing restoration.")
    return selection


class NativeSkillRestore:
    def __init__(self, root: Path, request: dict, *, workspace: dict | None, native_restore_used: bool = False) -> None:
        self.root, self.request, self.workspace = root, request, workspace
        self.native_restore_used, self.apply_attempted = native_restore_used, False
        self.source = NativeSkillOutcome(root, None, request, workspace=workspace)
        self.session = procedural_skill_restore_apply_session()
        self.snapshots = self.session.snapshot()
        self.applied = self.session.get(request["skill_id"])
        self.paths = {"skills_path": root / "proto_mind/data/skills.jsonl",
                      "persistent_memory_path": root / "proto_mind/data/persistent_memory.json"}
        self.review = None
        self.issues = list(self.source.issues)
        self.stored_status = "unavailable"
        try:
            if len(self.snapshots) > 1 or len(json.dumps(self.snapshots, allow_nan=False)) > 128_000:
                raise ValueError("Restore receipts exceed the bounded process limit.")
            if not self.issues:
                records = self.source.builder.skill_library.read_snapshot()["records"]
                record = next((row for row in records if row["id"] == request["skill_id"]), {})
                self.stored_status = record.get("status", "unavailable")
                self.review = self.session.review(request["skill_id"], **self.paths)
                self.source._check_sources()
                self._dependencies()
        except (OSError, ValueError, TypeError, KeyError, AttributeError, RecursionError, OverflowError, ProceduralSkillRestoreApplyError) as exc:
            self.issues.append(f"Restore evidence cannot be safely reviewed: {type(exc).__name__}: {exc}")

    def _dependencies(self) -> None:
        reader = NativeLibrary(self.root)
        for name, expected in self.source.hashes.items():
            if name != "skills.jsonl" and hashlib.sha256(reader._read_bytes(name)[0]).hexdigest() != expected:
                raise ValueError(f"{name} changed during restoration. No automatic retry.")
        if self.workspace and workspace_identity(Path(self.workspace["path"])) != self.workspace:
            raise ValueError("Workspace identity changed during restoration.")

    def _reasons(self) -> list[str]:
        reasons = list(self.issues)
        if not self.source.context_disabled:
            reasons.append("Readable explicitly disabled Context Injection is required; no setting is changed automatically.")
        if self.native_restore_used or self.snapshots:
            reasons.append("The single Native restore attempt is already used. Inspect the skill and receipt; no replay.")
        if self.review is None:
            reasons.append("The existing restore gate is unavailable.")
        elif not self.review.confirmable:
            reasons.extend(self.review.issues)
        return _findings(reasons)

    def _base(self, kind: str) -> dict:
        changed = kind == "result"
        return {"schema": f"proto_mind.native_skill_restore_{kind}.v1", **self.source._identity(),
                **_boundary(read_only=not changed), "store_mutation_performed": changed, "skill_mutation_performed": changed,
                "experience_mutation_performed": False, "batch_apply_performed": False}

    def _receipt(self) -> dict | None:
        if self.applied is None:
            return None
        raw = self.applied.to_dict()
        audit = self.session.doctor(**self.paths) if not self.issues else None
        verified = audit is not None and not audit.issues
        records = self.source.builder.skill_library.read_snapshot()["records"] if self.source.builder else []
        record = next((row for row in records if row["id"] == self.request["skill_id"]), None)
        current = verified and record is not None and _hash(record) == raw["after_record_hash"]
        return {**raw, "verification_status": "VERIFIED" if verified else "ERROR" if audit else "UNAVAILABLE",
                "evidence_state": "CURRENT" if current else "HISTORICAL" if verified else "UNAVAILABLE",
                "detailed_receipt_persistence": "process_memory_only", "restore_metadata_persistence": "skill_record",
                "warnings": _findings([*(audit.issues if audit else []), *(audit.warnings if audit else []),
                                        "Restoration reactivates availability, not procedure quality, consent or execution authority."])}

    def report(self) -> dict:
        reasons = self._reasons()
        return {**self._base("review"), "status": "ERROR" if self.issues else "RESTORED" if self.applied else "READY" if not reasons else "NOT_READY",
                "name": self.source.name, "stored_skill_status": self.stored_status, "can_restore": not reasons,
                "native_restore_slot_available": not self.native_restore_used and not self.snapshots,
                "context_injection_disabled": self.source.context_disabled, "store_hashes": self.source.hashes,
                "checks": self.review.checks if self.review else {}, "reasons": reasons, "issues": _findings(self.issues),
                "warnings": _findings(self.review.warnings if self.review else []), "receipt": self._receipt(),
                "skill_store_scope": "global_legacy_stores", "project_isolation_enforced": False}

    def preview(self) -> dict:
        reasons = self._reasons()
        if not reasons:
            try:
                self.source._check_sources()
                self._dependencies()
                if self.session.snapshot() != self.snapshots:
                    raise ValueError("Restore attempt state changed. Preview again.")
            except (OSError, ValueError) as exc:
                reasons.append(str(exc))
        review = asdict(self.review) if self.review else {}
        material = {"selection": self.request, "workspace": self.workspace, "store_hashes": self.source.hashes,
                    "restore_used": self.native_restore_used, "receipts": self.snapshots, "review": review, "reasons": reasons}
        return {**self._base("preview"), "ready": not reasons, "reasons": _findings(reasons), "preview_fingerprint": _hash(material),
                "confirmation_token": procedural_skill_restore_apply_confirmation_token(self.review) if not reasons else "",
                "token_material": {key: review[key] for key in TOKEN_FIELDS} if not reasons else {},
                "expected_record_mutations": 1, "expected_changed_fields": CHANGED_FIELDS,
                "future_mutation": "skills_one_durable_restore", "requires_global_skills_acknowledgement": True,
                "store_hashes": self.source.hashes}

    def confirm(self, params: dict) -> dict:
        preview = self.preview()
        if not preview["ready"]:
            raise ValueError("Restore refused: " + "; ".join(preview["reasons"]))
        if params.get("preview_fingerprint") != preview["preview_fingerprint"]:
            raise ValueError("Restore evidence/scope changed; preview again. No attempt consumed.")
        if params.get("confirmation_token") != preview["confirmation_token"]:
            raise ValueError("Exact restore token mismatch. No attempt consumed.")
        if params.get("acknowledge_global_skills") is not True:
            raise ValueError("Acknowledge restoration in the shared Skill Library.")
        self.source._check_sources()
        self._dependencies()
        self.apply_attempted = True
        try:
            self.session.apply(self.request["skill_id"], token=params["confirmation_token"], **self.paths,
                               expected_memory_sha256=self.source.hashes["persistent_memory.json"], validate_dependencies=self._dependencies)
        except (OSError, ValueError, ProceduralSkillRestoreApplyError) as exc:
            raise ValueError(f"Restore attempt ended: {exc} Inspect the skill and receipt; no automatic retry.") from exc
        fresh = NativeSkillRestore(self.root, self.request, workspace=self.workspace, native_restore_used=True)
        receipt = fresh._receipt()
        if receipt is None:
            raise ValueError("Restore returned but the receipt is unavailable. Inspect the skill; do not retry.")
        return {**self._base("result"), "mutation": "skills_one_durable_restore", "events_appended": 0, "receipt": receipt}
