"""Explicit operator-authored project notes; pure local recall and immutable private saves."""
from copy import deepcopy
from pathlib import Path
import re
from uuid import UUID

from proto_mind.native_desk import injection_state
from proto_mind.native_private_records import PrivateRecordStore, digest, encoded, snapshot_hash, HASH
from proto_mind.native_work_sessions import workspace_identity


SCHEMA = "proto_mind.native_project_memory.v1"
KINDS = frozenset({"project_fact", "preference", "decision", "lesson", "constraint"})
METHODS = frozenset({"project_memory_list", "project_memory_recall", "project_memory_inspect", "project_memory_preview", "project_memory_save"})
MAX_SELECTED = 5
BODY_FIELDS = {"schema", "project_root", "workspace", "conversation_id", "kind", "content", "basis", "supersedes_id",
               "source", "verification", "executable", "automatic_learning"}
NOTE_FIELDS = {"kind", "content", "basis", "supersedes_id"}


def _text(value, label: str, limit: int, *, empty=False) -> str:
    if (not isinstance(value, str) or value != value.strip() or (not empty and not value) or len(value) > limit
            or any(ord(char) < 32 and char not in "\n\t" for char in value)):
        raise ValueError(f"Invalid {label}; use bounded plain text.")
    return value


def validate_project_memory(body: dict) -> None:
    if (not isinstance(body, dict) or set(body) != BODY_FIELDS or body["schema"] != SCHEMA
            or body["kind"] not in KINDS or body["source"] != "operator_explicit"
            or body["verification"] != "operator_asserted_not_independently_verified"
            or body["executable"] is not False or body["automatic_learning"] is not False):
        raise ValueError("Project note schema/source/authority does not verify.")
    UUID(body["conversation_id"])
    _text(body["project_root"], "project root", 4096)
    if not body["project_root"].startswith("/"):
        raise ValueError("Project root must be absolute.")
    workspace = body["workspace"]
    if (not isinstance(workspace, dict) or set(workspace) != {"path", "device", "inode"}
            or not isinstance(workspace["path"], str) or not workspace["path"].startswith("/")
            or len(workspace["path"]) > 4096 or any(type(workspace[key]) is not int or workspace[key] < 0 for key in ("device", "inode"))):
        raise ValueError("An exact selected-workspace identity is required.")
    _text(body["content"], "note", 4000)
    _text(body["basis"], "operator source/basis", 1000)
    if not isinstance(body["supersedes_id"], str) or (body["supersedes_id"] and not HASH.fullmatch(body["supersedes_id"])):
        raise ValueError("Use an exact prior note ID or leave replacement empty.")


def parse_project_memory_request(method: str, params: dict) -> dict:
    extras = {"project_memory_list": {"include_history", "offset"}, "project_memory_recall": {"query"},
              "project_memory_inspect": {"record_id"}, "project_memory_preview": {"note"},
              "project_memory_save": {"note", "preview_fingerprint", "confirmation_token", "acknowledge_operator_note"}}
    if method not in METHODS or not isinstance(params, dict) or set(params) - {"conversation_id", "workspace_root"} - extras[method]:
        raise ValueError("Project memory accepts fixed local review/save operations only.")
    conversation = str(UUID(params.get("conversation_id", "")))
    path = _text(params.get("workspace_root"), "selected workspace", 4096)
    if not path.startswith("/"):
        raise ValueError("Select the project folder explicitly.")
    if method == "project_memory_list" and type(params.get("include_history", False)) is not bool:
        raise ValueError("Invalid history filter.")
    if method == "project_memory_list" and (type(params.get("offset", 0)) is not int or not 0 <= params.get("offset", 0) <= 200):
        raise ValueError("Invalid project-memory page offset.")
    if method == "project_memory_recall":
        _text(params.get("query"), "recall query", 500)
    return {"conversation_id": conversation, "workspace_root": path}


class NativeProjectMemory:
    def __init__(self, root: Path, state_dir: Path, conversation: str, workspace: dict):
        self.root, self.conversation, self.workspace = root, str(UUID(conversation)), workspace
        self.store = PrivateRecordStore(state_dir, "project_memory")

    def _same_scope(self, body):
        return body["project_root"] == str(self.root) and body["workspace"] == self.workspace

    def _read(self):
        all_records, issues = self.store.scan(validate_project_memory)
        records = [row for row in all_records if self._same_scope(row["body"])]
        by_id = {row["id"]: row for row in records}
        replaced = set()
        for row in records:
            prior = row["body"]["supersedes_id"]
            if not prior:
                continue
            if prior not in by_id or prior == row["id"] or prior in replaced:
                issues.append("Project note replacement linkage is missing or ambiguous; no repair or automatic recall.")
            replaced.add(prior)
            chain, current = {row["id"]}, prior
            while current in by_id:
                if current in chain:
                    issues.append("Project note replacement cycle; inspect the private ledger.")
                    break
                chain.add(current); current = by_id[current]["body"]["supersedes_id"]
        records.sort(key=lambda row: (row["saved_at"], row["id"]), reverse=True)
        return all_records, records, replaced, list(dict.fromkeys(issues))

    def _check_workspace(self):
        if workspace_identity(Path(self.workspace["path"])) != self.workspace:
            raise ValueError("The selected project folder changed. Select and inspect it again.")

    def _base(self, kind, *, write=False):
        return {"schema": f"proto_mind.native_project_memory_{kind}.v1", "conversation_id": self.conversation,
                "workspace": self.workspace, "read_only": not write, "no_execution": True,
                "core_mutation_performed": False, "model_call_performed": False, "private_write_performed": write,
                "automatic_recall": False, "legacy_memory_migrated": False}

    @staticmethod
    def _item(record, replaced):
        body = record["body"]
        return {"id": record["id"], "record_hash": record["record_hash"], "saved_at": record["saved_at"],
                "kind": body["kind"], "content": body["content"], "basis": body["basis"],
                "status": "superseded" if record["id"] in replaced else "active",
                "supersedes_id": body["supersedes_id"], "verification": body["verification"]}

    def listing(self, *, include_history=False, query=None, offset=0):
        _, records, replaced, issues = self._read()
        selected = records if include_history and query is None else [row for row in records if row["id"] not in replaced]
        if query is not None:
            tokens = set(re.findall(r"[^\W_]+", query.casefold(), flags=re.UNICODE))
            ranked = []
            for row in selected:
                body = row["body"]
                words = set(re.findall(r"[^\W_]+", (body["content"] + " " + body["basis"]).casefold(), flags=re.UNICODE))
                overlap = len(tokens & words)
                if overlap:
                    ranked.append((overlap, row["saved_at"], row["id"], row))
            selected = [row for _, _, _, row in sorted(ranked, reverse=True)[:MAX_SELECTED]] if not issues else []
        self._check_workspace()
        matching = len(selected)
        page_size = MAX_SELECTED if query is not None else 40
        return {**self._base("list"), "items": [self._item(row, replaced) for row in selected[offset:offset + page_size]], "issues": issues,
                "total_count": len(records), "active_count": len(records) - len(replaced & {row["id"] for row in records}),
                "matching_count": matching, "offset": offset, "page_size": page_size,
                "query": query or "", "algorithm": "exact_unicode_token_overlap" if query is not None else "saved_at_descending",
                "directory": str(self.store.directory), "limit": 200,
                "notice": "Only explicitly saved notes for this exact folder. Legacy core memory remains shared and is not migrated. No automatic model attachment or usage-counter write."}

    def inspect(self, identifier):
        record = self.store.get(identifier, validate_project_memory)
        if not self._same_scope(record["body"]):
            raise ValueError("The note belongs to another project folder. Nothing attached.")
        _, _, replaced, issues = self._read()
        self._check_workspace()
        return {**self._base("inspect"), "item": self._item(record, replaced), "record": record,
                "hash_material": encoded({key: value for key, value in record.items() if key != "record_hash"}).decode(),
                "issues": issues, "integrity": "VERIFIED"}

    def preview(self, note):
        if not isinstance(note, dict) or set(note) != NOTE_FIELDS:
            raise ValueError("Use kind, content, basis and an optional exact supersedes_id only.")
        body = {"schema": SCHEMA, "project_root": str(self.root), "workspace": self.workspace,
                "conversation_id": self.conversation, **deepcopy(note), "source": "operator_explicit",
                "verification": "operator_asserted_not_independently_verified", "executable": False, "automatic_learning": False}
        validate_project_memory(body)
        all_records, records, replaced, issues = self._read()
        if issues:
            raise ValueError("Inspect project-memory issues before saving: " + "; ".join(issues))
        if injection_state(self.root)["enabled"] is not False:
            raise ValueError("Context Injection must remain disabled for this explicit memory workflow.")
        if note["supersedes_id"] and not any(row["id"] == note["supersedes_id"] and row["id"] not in replaced for row in records):
            raise ValueError("Only a current note in this exact project can be superseded. No history is rewritten.")
        self._check_workspace()
        snapshot = snapshot_hash(all_records)
        material = {"body": body, "snapshot_hash": snapshot}
        fingerprint = digest(material)
        return {**self._base("preview"), "body": body, "snapshot_hash": snapshot, "hash_material": encoded(material).decode(),
                "preview_fingerprint": fingerprint, "confirmation_token": "SAVE-PROJECT-MEMORY-" + fingerprint[:12].upper(),
                "notice": "Operator assertion, not independently verified. Only one new immutable private note; no shared core write, automatic recall, prompt change or migration."}

    def save(self, params):
        preview = self.preview(params.get("note"))
        if (params.get("confirmation_token") != preview["confirmation_token"] or params.get("preview_fingerprint") != preview["preview_fingerprint"]
                or params.get("acknowledge_operator_note") is not True):
            raise ValueError("Confirm this exact project note and its operator-asserted nature. Nothing saved.")
        record, changed = self.store.save(preview["body"], validate_project_memory, expected_snapshot=preview["snapshot_hash"])
        return {**self._base("saved", write=changed), "item": self._item(record, set()), "already_saved": not changed}

    def selected(self, specifications):
        if not isinstance(specifications, list) or len(specifications) > MAX_SELECTED:
            raise ValueError("Select at most five project notes explicitly.")
        if not specifications:
            return []
        _, records, replaced, issues = self._read()
        if issues:
            raise ValueError("Project notes cannot be sent while private-ledger integrity is uncertain.")
        if injection_state(self.root)["enabled"] is not False:
            raise ValueError("Context Injection must remain disabled for explicit project notes.")
        by_id, selected, seen = {row["id"]: row for row in records}, [], set()
        for spec in specifications:
            if (not isinstance(spec, dict) or set(spec) != {"id", "record_hash"}
                    or not isinstance(spec["id"], str) or not isinstance(spec["record_hash"], str)
                    or not HASH.fullmatch(spec["id"]) or not HASH.fullmatch(spec["record_hash"]) or spec["id"] in seen):
                raise ValueError("Project note selection must contain unique, reviewed IDs and hashes only.")
            record = by_id.get(spec["id"])
            if record is None or record["record_hash"] != spec["record_hash"] or record["id"] in replaced:
                raise ValueError("A project note changed, was superseded or belongs to another folder. Review it again; no fallback.")
            selected.append({**self._item(record, replaced), "workspace": self.workspace})
            seen.add(spec["id"])
        self._check_workspace()
        return selected
