"""Fixed, operator-only Native UI over the existing procedural skill gates.

Durable lessons need no live Experience pilot. Draft receipts use the core's
bounded process-memory sessions; only explicit apply can write skills.jsonl.
"""
from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import re
from uuid import UUID

from proto_mind.experience_learning_apply import _raw_memory_records
from proto_mind.experience_learning_skill_apply import (
    OperatorReviewedProceduralSkillApplySession,
    ProceduralSkillApplyError,
    procedural_skill_apply_confirmation_token,
)
from proto_mind.experience_learning_skill_authoring import (
    OperatorReviewedProceduralSkillAuthoringSession,
    ProceduralSkillAuthoringError,
    ProceduralSkillAuthoringRequest,
    build_procedural_skill_authoring_blueprint,
    procedural_skill_authoring_confirmation_token,
    procedural_skill_authoring_receipt_hash,
)
from proto_mind.experience_learning_skill_contract import (
    ProceduralSkillContractBuilder, ProceduralSkillContractError,
)
from proto_mind.experience_learning_skill_readiness import ProceduralSkillApplyReadiness
from proto_mind.native_learning_review import _MemorySnapshot, _SkillSnapshot
from proto_mind.native_library import NativeLibrary


REVIEW_SCHEMA = "proto_mind.native_skill_authoring.v1"
PREVIEW_SCHEMA = "proto_mind.native_skill_confirmation.v1"
RESULT_SCHEMA = "proto_mind.native_skill_result.v1"
METHODS = frozenset({"skill_authoring_review", "skill_authoring_preview", "skill_authoring_confirm"})
LIST_LIMITS = {"preconditions": 8, "steps": 16, "permissions": 8, "verification": 8, "known_failure_modes": 8}
TEXT_FIELDS = ("name", "summary", "trigger")
_ID = re.compile(r"^[A-Za-z0-9_.:-]{1,200}$")


class NativeSkillError(ValueError):
    pass


def _hash(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=True,
                                     allow_nan=False, separators=(",", ":")).encode()).hexdigest()


def _plain(value: object) -> bool:
    return isinstance(value, str) and len(value) <= 800 and not any(
        ord(char) < 32 or 0xD800 <= ord(char) <= 0xDFFF for char in value
    )


def parse_skill_request(params: dict, *, method: str) -> dict:
    allowed = {"conversation_id", "lesson_id", "workspace_root", "authored"}
    if method != "skill_authoring_review":
        allowed.add("operation")
    if method == "skill_authoring_confirm":
        allowed.update({"preview_fingerprint", "confirmation_token", "acknowledge_global_skills"})
    if method not in METHODS or set(params) - allowed:
        raise NativeSkillError("Unexpected skill-authoring parameter or operation.")
    try:
        conversation = str(UUID(params.get("conversation_id", "")))
    except (ValueError, TypeError, AttributeError) as exc:
        raise NativeSkillError("A valid selected conversation is required.") from exc
    lesson = params.get("lesson_id")
    if not isinstance(lesson, str) or not _ID.fullmatch(lesson):
        raise NativeSkillError("Select an exact persistent lesson ID.")
    authored = params.get("authored", {**dict.fromkeys(TEXT_FIELDS, ""), **{key: [] for key in LIST_LIMITS}})
    if not isinstance(authored, dict) or set(authored) != set(TEXT_FIELDS) | set(LIST_LIMITS):
        raise NativeSkillError("Only the declared descriptive skill fields are supported.")
    if not all(_plain(authored[key]) for key in TEXT_FIELDS) or any(
        not isinstance(authored[key], list) or len(authored[key]) > limit
        or any(not _plain(item) or not item.strip() for item in authored[key])
        for key, limit in LIST_LIMITS.items()
    ) or len(json.dumps(authored, ensure_ascii=False)) > 8000:
        raise NativeSkillError("Skill fields exceed their bounds or contain invalid text. Each item is limited to 800 characters; total 8000.")
    operation = params.get("operation", "")
    if method != "skill_authoring_review" and operation not in ("author", "apply"):
        raise NativeSkillError("Only explicit author and single-skill apply are supported.")
    return {"conversation_id": conversation, "lesson_id": lesson, "authored": authored, "operation": operation}


def _boundary() -> dict:
    return {"no_execution": True, "model_call_performed": False, "network_call_performed": False,
            "retrieval_performed": False, "consent_state_changed": False, "automatic_promotion": False,
            "context_injection_changed": False, "permissions_changed": False, "memory_mutation_performed": False}


class NativeSkillSession:
    def __init__(self) -> None:
        self.authoring = OperatorReviewedProceduralSkillAuthoringSession()
        self.applies = OperatorReviewedProceduralSkillApplySession()
        self.bindings: dict[str, str] = {}


class NativeSkillAuthoring:
    def __init__(self, root: Path, session: NativeSkillSession, request: dict, *, workspace: dict | None,
                 native_apply_used: bool = False) -> None:
        self.root, self.session, self.request, self.workspace = root, session, request, workspace
        self.native_apply_used = native_apply_used or bool(session.applies.snapshot())
        self.binding = _hash({"conversation_id": request["conversation_id"], "workspace": workspace})
        self.authoring = session.authoring.get(request["lesson_id"])
        self.applied = session.applies.get(request["lesson_id"])
        self.issues: list[str] = []
        self.hashes: dict[str, str] = {}
        self.memory = self.skills = self.builder = self.readiness = self.source_review = None
        if self.authoring and session.bindings.get(request["lesson_id"]) != self.binding:
            self.issues.append("The confirmed authoring receipt belongs to another conversation or workspace.")
            self.authoring = self.applied = None
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
            self.memory.expected_persistent_sha256 = self.hashes["persistent_memory.json"]
            self.skills = _SkillSnapshot(raw["skills.jsonl"])
            self.skills.skills_path = root / "proto_mind/data/skills.jsonl"
            self.builder = ProceduralSkillContractBuilder(memory_store=self.memory, skill_library=self.skills)
            self.readiness = ProceduralSkillApplyReadiness(builder=self.builder, skill_library=self.skills)
            self.source_review = self.builder.review(request["lesson_id"])
        except (OSError, ValueError, TypeError, KeyError, RecursionError, OverflowError, ProceduralSkillContractError) as exc:
            self.issues.append(f"Fixed local stores cannot be reviewed safely: {type(exc).__name__}: {exc}")

    def _receipt(self, value, kind: str) -> dict | None:
        if value is None:
            return None
        raw = value.to_dict()
        verification, warnings = "NOT APPLICABLE", []
        if kind == "apply":
            if self.readiness is None:
                verification, warnings = "ERROR", ["Current skill/source stores cannot be verified."]
            else:
                doctor = self.session.applies.doctor(reviewer=self.readiness)
                verification, warnings = doctor.status, [*doctor.issues, *doctor.warnings]
        return {"kind": kind, "id": value.id, "source_lesson_id": value.source_lesson_id,
                "created_at": raw.get("applied_at", raw.get("created_at", "")),
                "authoring_hash": value.authoring_hash, "record_id": raw.get("created_skill_id", ""),
                "before_store_sha256": raw.get("before_store_sha256", ""),
                "after_store_sha256": raw.get("after_store_sha256", ""),
                "receipt_hash": raw.get("receipt_hash", procedural_skill_authoring_receipt_hash(raw)),
                "verification_status": verification, "warnings": warnings,
                "process_memory_only": True, "executable": False,
                "details": json.dumps(raw, ensure_ascii=False, indent=2, sort_keys=True)}

    def report(self) -> dict:
        source = self.source_review
        contract = source.contract if source else None
        current = self.session.applies.review(self.authoring, reviewer=self.readiness) if self.authoring and self.readiness else None
        fields = self.authoring.authored_contract if self.authoring else (
            {key: getattr(contract, key) for key in (*TEXT_FIELDS, *LIST_LIMITS)} if contract else
            {**dict.fromkeys(TEXT_FIELDS, ""), **{key: [] for key in LIST_LIMITS}}
        )
        return {"schema": REVIEW_SCHEMA, "read_only": True,
                "conversation_id": self.request["conversation_id"], "lesson_id": self.request["lesson_id"],
                "workspace_path": str(self.workspace["path"]) if self.workspace else "",
                "status": "ERROR" if self.issues else "APPLIED" if self.applied else "AUTHORED" if self.authoring else "REVIEW",
                "eligible": bool(source and source.eligible_for_operator_authoring and not self.issues),
                "source_status": source.status if source else "UNAVAILABLE",
                "source_content": contract.summary if contract else "",
                "source_provenance_id": contract.source_provenance_id if contract else "",
                "source_record_hash": contract.source_record_hash if contract else "",
                "lifecycle_state": source.lifecycle_state if source else "unavailable",
                "source_checks": source.checks if source else {}, "fields": fields,
                "authoring_receipt": self._receipt(self.authoring, "author"),
                "apply_receipt": self._receipt(self.applied, "apply"),
                "apply_checks": current.checks if current else {},
                "apply_issues": current.issues if current else [],
                "store_hashes": self.hashes, "native_apply_slot_available": not self.native_apply_used,
                "skill_store_scope": "global_legacy_stores", "project_isolation_enforced": False,
                "issues": self.issues,
                "source_issues": source.issues if source else [],
                "warnings": [*(source.warnings if source else []),
                             "Source hashes prove lineage and consistency, not the truth or quality of a procedure.",
                             "Authored permissions are descriptive, never an execution grant. Skills are shared across projects.",
                             "Drafts and authoring receipts expire on app/core restart. Stored skill provenance survives; execution is not installed."],
                "store_mutation_performed": False, **_boundary()}

    def preview(self) -> dict:
        operation = self.request["operation"]
        issues = list(self.issues)
        blueprint = review = None
        token = ""
        if not issues and self.builder is not None:
            try:
                if operation == "author":
                    if self.authoring:
                        raise NativeSkillError("This lesson already has a confirmed process-memory authoring receipt.")
                    blueprint = build_procedural_skill_authoring_blueprint(
                        self.builder, ProceduralSkillAuthoringRequest(memory_id=self.request["lesson_id"], **self.request["authored"]),
                    )
                    if len(self.session.authoring.snapshot()) >= 16:
                        raise NativeSkillError("The bounded 16-receipt authoring session is full.")
                    token = procedural_skill_authoring_confirmation_token(blueprint)
                else:
                    if self.authoring is None:
                        raise NativeSkillError("Confirm the exact authored contract before previewing a save.")
                    if self.request["authored"] != self.authoring.authored_contract:
                        raise NativeSkillError("The form differs from the confirmed authored contract.")
                    if self.native_apply_used:
                        raise NativeSkillError("This Native bridge has already used its single skill apply slot. Inspect the receipt; do not replay.")
                    review = self.session.applies.review(self.authoring, reviewer=self.readiness)
                    if not review.confirmable:
                        issues.extend(review.issues)
                    else:
                        token = procedural_skill_apply_confirmation_token(review)
            except (NativeSkillError, ProceduralSkillAuthoringError, ProceduralSkillContractError, ValueError, TypeError) as exc:
                issues.append(str(exc))
        if self.builder is None and not issues:
            issues.append("Source stores are unavailable.")
        material = {"request": self.request, "workspace": self.workspace, "store_hashes": self.hashes,
                    "authoring": self.authoring.to_dict() if self.authoring else None,
                    "applied": self.applied.to_dict() if self.applied else None,
                    "native_apply_used": self.native_apply_used,
                    "blueprint": asdict(blueprint) if blueprint else None, "review": asdict(review) if review else None,
                    "issues": issues}
        projection = blueprint.storage_projection if blueprint else self.authoring.storage_projection if self.authoring else {}
        return {"schema": PREVIEW_SCHEMA, "read_only": True,
                "conversation_id": self.request["conversation_id"], "lesson_id": self.request["lesson_id"],
                "operation": operation, "ready": not issues, "issues": issues,
                "preview_fingerprint": _hash(material), "confirmation_token": token if not issues else "",
                "target_schema": "skill.procedure.v1",
                "future_mutation": "skills_one_record" if operation == "apply" else "process_memory_only",
                "requires_global_skills_acknowledgement": operation == "apply",
                "name": projection.get("name", ""), "summary": projection.get("summary", ""), "body": projection.get("body", ""),
                "authoring_hash": blueprint.authoring_hash if blueprint else self.authoring.authoring_hash if self.authoring else "",
                "store_hashes": self.hashes, "store_mutation_performed": False, **_boundary()}

    def confirm(self, params: dict) -> dict:
        preview = self.preview()
        if not preview["ready"]:
            raise NativeSkillError("Confirmation refused: " + "; ".join(preview["issues"]))
        if params.get("preview_fingerprint") != preview["preview_fingerprint"]:
            raise NativeSkillError("Source, form, workspace or store changed. Preview again; nothing was saved.")
        if params.get("confirmation_token") != preview["confirmation_token"]:
            raise NativeSkillError("Exact confirmation token mismatch. Nothing was saved.")
        operation = self.request["operation"]
        try:
            if operation == "author":
                blueprint = build_procedural_skill_authoring_blueprint(
                    self.builder, ProceduralSkillAuthoringRequest(memory_id=self.request["lesson_id"], **self.request["authored"]),
                )
                receipt = self.session.authoring.create(blueprint, token=params["confirmation_token"])
                self.session.bindings[receipt.source_lesson_id] = self.binding
            else:
                if params.get("acknowledge_global_skills") is not True:
                    raise NativeSkillError("Acknowledge the shared global Skill Library and non-executable record before saving.")
                receipt = self.session.applies.apply(self.authoring, token=params["confirmation_token"], reviewer=self.readiness)
                # Re-read only after the core writer returns its verified receipt.
                refreshed = NativeSkillAuthoring(self.root, self.session, self.request, workspace=self.workspace, native_apply_used=True)
                self.readiness = refreshed.readiness
        except (ProceduralSkillAuthoringError, ProceduralSkillContractError, ProceduralSkillApplyError) as exc:
            raise NativeSkillError(str(exc)) from exc
        return {"schema": RESULT_SCHEMA, "conversation_id": self.request["conversation_id"],
                "lesson_id": self.request["lesson_id"], "operation": operation,
                "receipt": self._receipt(receipt, operation),
                "mutation": preview["future_mutation"], "skill_mutation_performed": operation == "apply",
                "batch_apply_performed": False, **_boundary()}
