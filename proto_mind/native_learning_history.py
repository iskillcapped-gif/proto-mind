"""Explicit immutable snapshots of selected-skill evidence, never live pilot rehydration."""
from copy import deepcopy
from dataclasses import fields
from pathlib import Path
from uuid import UUID

from proto_mind.native_private_records import PrivateRecordStore, digest, encoded
from proto_mind.native_skill_inspection import NativeSkillInspection, parse_skill_inspection_request
from proto_mind.native_skill_outcome import NativeSkillOutcome
from proto_mind.native_skill_authoring import _hash
from proto_mind.native_work_sessions import workspace_identity
from proto_mind.experience_learning_skill_outcome_capture import (
    ProceduralSkillOutcomeCaptureReceipt, procedural_skill_outcome_capture_receipt_hash, is_valid_procedural_skill_outcome_event_batch,
)
from proto_mind.experience_learning_skill_outcome_decision import ProceduralSkillOutcomeDecisionReceipt, procedural_skill_outcome_decision_receipt_hash
from proto_mind.experience_learning_skill_lifecycle_apply import ProceduralSkillLifecycleApplyReceipt, procedural_skill_lifecycle_apply_receipt_hash
from proto_mind.experience_learning_skill_lifecycle_metadata_apply import ProceduralSkillLifecycleMetadataApplyReceipt, procedural_skill_lifecycle_metadata_apply_receipt_hash
from proto_mind.skill_lifecycle_restore_apply import (
    ProceduralSkillRestoreApplyReceipt, procedural_skill_restore_apply_receipt_hash, procedural_skill_restore_apply_receipts_snapshot,
)


METHODS = {"skill_history_list", "skill_history_preview", "skill_history_save", "skill_history_inspect"}
SCHEMA = "proto_mind.native_learning_history.v1"
RECEIPTS = {
    "manual_outcome": (ProceduralSkillOutcomeCaptureReceipt, procedural_skill_outcome_capture_receipt_hash),
    "decision": (ProceduralSkillOutcomeDecisionReceipt, procedural_skill_outcome_decision_receipt_hash),
    "lifecycle": (ProceduralSkillLifecycleApplyReceipt, procedural_skill_lifecycle_apply_receipt_hash),
    "archive": (ProceduralSkillLifecycleMetadataApplyReceipt, procedural_skill_lifecycle_metadata_apply_receipt_hash),
    "restore": (ProceduralSkillRestoreApplyReceipt, procedural_skill_restore_apply_receipt_hash),
}
BODY_FIELDS = {"schema", "conversation_id", "workspace", "project_root", "skill_id", "name", "skill_record", "store_hashes",
               "inspection", "receipts", "events", "historical_only", "authority_restored", "automatic_learning", "quality_verification"}


def parse_history_request(method: str, params: dict) -> dict:
    selection_fields = {"conversation_id", "workspace_root", "skill_id", "expected_sha256"}
    extra = {"preview_fingerprint", "confirmation_token", "acknowledge_history_only"} if method == "skill_history_save" else {"record_id"} if method == "skill_history_inspect" else set()
    if method not in METHODS or set(params) - selection_fields - extra:
        raise ValueError("History supports fixed read/save operations only, not import, repair or execution.")
    selection = parse_skill_inspection_request({key: value for key, value in params.items() if key in selection_fields})
    if not selection["conversation_id"]:
        raise ValueError("Select a conversation for its exact historical evidence.")
    return selection


def validate_history(body: dict) -> None:
    if (set(body) != BODY_FIELDS or body["schema"] != SCHEMA or body["historical_only"] is not True
            or body["authority_restored"] is not False or body["automatic_learning"] is not False
            or body["quality_verification"] != "not_independently_verified" or not isinstance(body["name"], str)
            or len(body["name"]) > 200 or not str(body["project_root"]).startswith("/")
            or not isinstance(body["skill_record"], dict) or body["skill_record"].get("id") != body["skill_id"]
            or not isinstance(body["receipts"], list) or len(body["receipts"]) > 40
            or not isinstance(body["events"], list) or len(body["events"]) > 64):
        raise ValueError("Historical evidence contract does not verify.")
    UUID(body["conversation_id"])
    workspace = body["workspace"]
    if workspace is not None and (not isinstance(workspace, dict) or set(workspace) != {"path", "device", "inode"}
                                  or not isinstance(workspace["path"], str) or not workspace["path"].startswith("/")
                                  or any(type(workspace[key]) is not int for key in ("device", "inode"))):
        raise ValueError("Historical workspace identity is malformed.")
    inspection = body["inspection"]
    if (not isinstance(inspection, dict) or inspection.get("schema") != "proto_mind.native_skill_inspection.v1"
            or inspection.get("skill_id") != body["skill_id"] or inspection.get("conversation_id") != body["conversation_id"]
            or inspection.get("read_only") is not True or inspection.get("no_execution") is not True):
        raise ValueError("Historical source inspection is not bound to this selection.")
    by_id = {row["id"]: row for row in body["events"]}
    if len(by_id) != len(body["events"]):
        raise ValueError("Historical event IDs are duplicated.")
    identities = set()
    event_ids = set()
    for row in body["receipts"]:
        if not isinstance(row, dict) or set(row) != {"kind", "raw"} or row["kind"] not in RECEIPTS:
            raise ValueError("Unsupported historical receipt kind.")
        cls, hash_receipt = RECEIPTS[row["kind"]]
        raw = row["raw"]
        if (not isinstance(raw, dict) or set(raw) != {field.name for field in fields(cls)} or raw.get("skill_id") != body["skill_id"]
                or raw.get("receipt_hash") != hash_receipt(raw)):
            raise ValueError("Original receipt schema/hash/skill binding does not verify.")
        identity = (row["kind"], raw["receipt_hash"])
        if identity in identities:
            raise ValueError("Duplicate historical receipt.")
        identities.add(identity)
        if row["kind"] == "manual_outcome":
            linked = [by_id.get(identifier) for identifier in raw["event_ids"]]
            if not all(linked) or not is_valid_procedural_skill_outcome_event_batch(linked) or any(event["session_id"] != raw["session_id"] for event in linked):
                raise ValueError("Manual outcome no longer matches its exact saved events.")
            event_ids.update(raw["event_ids"])
    if set(by_id) != event_ids:
        raise ValueError("Unrelated chat/events cannot be archived as skill evidence.")
    if len(encoded(body)) > 480_000:
        raise ValueError("Selected learning history exceeds the bounded archive limit.")


class NativeLearningHistory:
    def __init__(self, root: Path, state_dir: Path, owner, request: dict, *, workspace: dict | None):
        self.root, self.owner, self.request, self.workspace = root, owner, request, workspace
        self.store = PrivateRecordStore(state_dir, "learning_history")

    def _scope(self, body: dict) -> bool:
        return (body["project_root"] == str(self.root) and body["workspace"] == self.workspace
                and body["conversation_id"] == self.request["conversation_id"] and body["skill_id"] == self.request["skill_id"])

    def _body(self) -> dict:
        source = NativeSkillOutcome(self.root, self.owner, self.request, workspace=self.workspace)
        if source.issues or not source.context_disabled or source.builder is None:
            raise ValueError("History snapshot needs readable sources and disabled Context Injection. " + "; ".join(source.issues))
        record = next((row for row in source.builder.skill_library.read_snapshot()["records"] if row["id"] == self.request["skill_id"]), None)
        if record is None:
            raise ValueError("Selected skill no longer exists. Existing archives can still be inspected.")
        receipts = []
        def collect(kind, rows):
            receipts.extend({"kind": kind, "raw": deepcopy(row)} for row in rows if row.get("skill_id") == self.request["skill_id"])
        collect("manual_outcome", source.receipts)
        pilot = source.pilot
        if pilot:
            collect("decision", pilot.skill_outcome_decisions.snapshot())
            collect("lifecycle", pilot.skill_lifecycle_applies.snapshot())
            collect("archive", pilot.skill_lifecycle_metadata_applies.snapshot())
        collect("restore", procedural_skill_restore_apply_receipts_snapshot())
        wanted = {identifier for row in receipts if row["kind"] == "manual_outcome" for identifier in row["raw"]["event_ids"]}
        events = [deepcopy(event) for event in source.events if event["id"] in wanted]
        inspection = NativeSkillInspection(self.root, self.owner, {**self.request, "expected_sha256": ""}, workspace=self.workspace).report()
        body = {"schema": SCHEMA, "conversation_id": self.request["conversation_id"], "workspace": self.workspace,
                "project_root": str(self.root), "skill_id": record["id"], "name": source.name,
                "skill_record": deepcopy(record), "store_hashes": source.hashes, "inspection": inspection,
                "receipts": receipts, "events": events, "historical_only": True, "authority_restored": False,
                "automatic_learning": False, "quality_verification": "not_independently_verified"}
        validate_history(body)
        source._check_sources()
        if self.workspace and workspace_identity(Path(self.workspace["path"])) != self.workspace:
            raise ValueError("Workspace identity changed during history review.")
        return body

    def _base(self, kind, *, write=False):
        return {"schema": f"proto_mind.native_skill_history_{kind}.v1", "conversation_id": self.request["conversation_id"],
                "skill_id": self.request["skill_id"], "workspace_path": self.workspace["path"] if self.workspace else "",
                "read_only": not write, "no_execution": True, "core_mutation_performed": False,
                "authority_restored": False, "model_call_performed": False, "private_write_performed": write}

    def listing(self):
        rows, issues = self.store.scan(validate_history)
        selected = [row for row in rows if self._scope(row["body"])]
        selected.sort(key=lambda row: (row["saved_at"], row["id"]), reverse=True)
        return {**self._base("list"), "items": [self._summary(row) for row in selected], "issues": issues,
                "directory": str(self.store.directory), "limit": 200}

    @staticmethod
    def _summary(row):
        return {"id": row["id"], "saved_at": row["saved_at"], "record_hash": row["record_hash"],
                "receipt_count": len(row["body"]["receipts"]), "event_count": len(row["body"]["events"])}

    def preview(self):
        body = self._body()
        _, issues = self.store.scan(validate_history)
        if issues:
            raise ValueError("Inspect private history before saving: " + "; ".join(issues))
        fingerprint = digest(body)
        return {**self._base("preview"), "preview_fingerprint": fingerprint, "confirmation_token": "SAVE-SKILL-HISTORY-" + fingerprint[:12].upper(),
                "receipt_count": len(body["receipts"]), "event_count": len(body["events"]), "body": body,
                "hash_material": encoded(body).decode("utf-8"),
                "notice": "Historical copy only. Original receipt flags remain unchanged; no live consent, token, pilot or authority is reloaded."}

    def save(self, params):
        preview = self.preview()
        if (params.get("preview_fingerprint") != preview["preview_fingerprint"] or params.get("confirmation_token") != preview["confirmation_token"]
                or params.get("acknowledge_history_only") is not True):
            raise ValueError("Exact history preview/token and historical-only acknowledgement required. Nothing saved.")
        record, changed = self.store.save(preview["body"], validate_history)
        return {**self._base("saved", write=changed), "record": self._summary(record), "already_saved": not changed}

    def inspect(self, identifier):
        record = self.store.get(identifier, validate_history)
        if not self._scope(record["body"]):
            raise ValueError("Historical evidence belongs to another conversation/project/skill.")
        state = "UNAVAILABLE"
        try:
            source = NativeSkillOutcome(self.root, None, self.request, workspace=self.workspace)
            if not source.issues and source.builder:
                current = next((row for row in source.builder.skill_library.read_snapshot()["records"] if row["id"] == self.request["skill_id"]), None)
                state = "MATCHES_SAVED_RECORD" if current and _hash(current) == _hash(record["body"]["skill_record"]) else "CHANGED_OR_MISSING"
        except (OSError, ValueError):
            pass
        return {**self._base("inspect"), "record": record, "integrity": "VERIFIED", "current_record_state": state,
                "hash_material": encoded({key: value for key, value in record.items() if key != "record_hash"}).decode("utf-8"),
                "notice": "SHA-256 checks consistency, not authorship or procedure quality. Historical snapshots are never live decision/execution authority."}
