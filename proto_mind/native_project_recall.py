"""Read-only, bounded recall from explicitly saved notes in one exact workspace."""
from copy import deepcopy
import hashlib
import re
from uuid import UUID

from proto_mind.native_desk import injection_state
from proto_mind.native_private_records import HASH, snapshot_hash
from proto_mind.native_project_memory import NativeProjectMemory


SCHEMA = "proto_mind.native_project_recall.v1"
ALGORITHM = "local_content_token_overlap_v1"
MAX_NOTES = 3
MAX_CHARACTERS = 6000
FIELDS = {"schema", "conversation_id", "workspace", "goal_sha256", "access_mode", "state", "algorithm",
          "source_snapshot_hash", "total_count", "active_count", "matching_count", "selected_ids", "characters",
          "omitted_count", "reason", "read_only", "model_call_performed", "permission_granted", "automatic_learning"}
HISTORY_BOUNDARY = ("Project notes from earlier provider history are historical, not current project memory. "
                    "Only project notes attached to THIS turn are a current selection. If none are attached, do not invent a recall, "
                    "claim a historical note was checked, or treat it as current authority.\n")
STOP_WORDS = frozenset("""
the and for this that with from have has what which where when why how please project current about into only
can could would should make want use using now here there they them their our your you work task help tell
это этот эта эти того потому чтобы для как что где когда почему какой какая какие нужно надо пожалуйста
проект проекта проекте текущий текущего сейчас тут там мне меня мы нам наш наша наши ваш брат давай давайте
сделай сделать использовать используй расскажи покажи помоги работа задачу задачи можно есть было будет
проверь продолжим продолжаем дальше привет спасибо хорошо отлично просто
""".split())


def tokens(text: str) -> set[str]:
    return {token for token in re.findall(r"[^\W_]+", text.casefold().replace("ё", "е"), flags=re.UNICODE)
            if 3 <= len(token) <= 80 and token not in STOP_WORDS}


def validate_project_recall(value, *, notes=None, record=None):
    if (not isinstance(value, dict) or set(value) != FIELDS or value["schema"] != SCHEMA
            or value["algorithm"] != ALGORITHM or not isinstance(value["state"], str) or value["state"] not in {"selected", "no_match", "empty", "unavailable"}
            or not isinstance(value["conversation_id"], str) or str(UUID(value["conversation_id"])) != value["conversation_id"]
            or not isinstance(value["access_mode"], str) or value["access_mode"] not in {"chat", "full_access"}
            or not isinstance(value["goal_sha256"], str) or not HASH.fullmatch(value["goal_sha256"])
            or any(type(value[key]) is not int or not 0 <= value[key] <= 200
                   for key in ("total_count", "active_count", "matching_count", "omitted_count"))
            or type(value["characters"]) is not int or not 0 <= value["characters"] <= MAX_CHARACTERS
            or not isinstance(value["selected_ids"], list) or len(value["selected_ids"]) > MAX_NOTES
            or any(not isinstance(item, str) or not HASH.fullmatch(item) for item in value["selected_ids"])
            or len(set(value["selected_ids"])) != len(value["selected_ids"])
            or not isinstance(value["reason"], str) or not 1 <= len(value["reason"]) <= 400
            or any(ord(char) < 32 for char in value["reason"])
            or value["read_only"] is not True
            or any(value[key] is not False for key in ("model_call_performed", "permission_granted", "automatic_learning"))):
        raise ValueError("Automatic project recall metadata does not verify.")
    workspace = value["workspace"]
    if workspace is not None and (not isinstance(workspace, dict) or set(workspace) != {"path", "device", "inode"}
            or not isinstance(workspace["path"], str) or not workspace["path"].startswith("/") or len(workspace["path"]) > 4096
            or any(type(workspace[key]) is not int or workspace[key] < 0 for key in ("device", "inode"))):
        raise ValueError("Automatic recall requires an exact workspace identity.")
    count = len(value["selected_ids"])
    if (not count <= value["matching_count"] <= value["active_count"] <= value["total_count"]
            or value["omitted_count"] != value["matching_count"] - count
            or bool(count) != (value["state"] == "selected") or bool(value["characters"]) != bool(count)
            or value["state"] == "empty" and value["active_count"] != 0
            or value["state"] == "no_match" and (not value["active_count"] or value["matching_count"])
            or value["state"] == "unavailable" and (value["source_snapshot_hash"] is not None or value["total_count"])
            or value["state"] != "unavailable" and (workspace is None or not isinstance(value["source_snapshot_hash"], str)
                                                        or not HASH.fullmatch(value["source_snapshot_hash"]))):
        raise ValueError("Inconsistent automatic recall state/counts.")
    if notes is not None and ([row["id"] for row in notes] != value["selected_ids"]
            or any(row["workspace"] != workspace for row in notes)
            or sum(row["characters"] for row in notes) > value["characters"]):
        raise ValueError("Recalled note provenance differs from the selection.")
    if record is not None and (value["conversation_id"] != record.get("conversation_id")
            or workspace != record.get("workspace") or value["access_mode"] != record.get("access_mode")
            or value["goal_sha256"] != record.get("input_sha256") or record.get("provider") != "codex"):
        raise ValueError("Recall belongs to another task, project or provider.")


class ProjectRecall:
    def __init__(self, root, state_dir, *, conversation, workspace, text, mode):
        self.root, self.workspace = root, deepcopy(workspace)
        self.memory = NativeProjectMemory(root, state_dir, conversation, workspace) if workspace is not None else None
        self.notes = []
        self.report = {"schema": SCHEMA, "conversation_id": str(UUID(conversation)), "workspace": deepcopy(workspace),
                       "goal_sha256": hashlib.sha256(text.encode()).hexdigest(), "access_mode": mode,
                       "state": "unavailable", "algorithm": ALGORITHM, "source_snapshot_hash": None,
                       "total_count": 0, "active_count": 0, "matching_count": 0, "selected_ids": [], "characters": 0,
                       "omitted_count": 0, "reason": "Select a project folder to recall its explicitly saved notes.",
                       "read_only": True, "model_call_performed": False, "permission_granted": False, "automatic_learning": False}
        if self.memory is None:
            return
        if injection_state(root)["enabled"] is not False:
            self.report["reason"] = "Project recall is unavailable while disabled Context Injection cannot be verified. Settings were not changed."
            return
        all_records, records, replaced, issues = self.memory._read()
        if issues:
            self.report["reason"] = "Project-note storage or replacement history needs inspection. Ordinary turn without recalled notes; no repair."
            return
        self.memory._check_workspace()
        active = [row for row in records if row["id"] not in replaced]
        query = tokens(text)
        ranked = []
        for row in active:
            # Basis is provenance, not a relevance signal; generic words cannot select an unrelated note.
            overlap = len(query & tokens(row["body"]["content"]))
            if overlap:
                ranked.append((overlap, row["saved_at"], row["id"], row))
        characters = 0
        for _, _, _, row in sorted(ranked, reverse=True):
            size = len(row["body"]["content"]) + len(row["body"]["basis"])
            if len(self.notes) < MAX_NOTES and characters + size <= MAX_CHARACTERS:
                self.notes.append({**self.memory._item(row, replaced), "workspace": deepcopy(workspace)})
                characters += size
        state = "selected" if self.notes else "no_match" if active else "empty"
        self.report.update(state=state, source_snapshot_hash=snapshot_hash(all_records), total_count=len(records), active_count=len(active),
                           matching_count=len(ranked), selected_ids=[row["id"] for row in self.notes], characters=characters,
                           omitted_count=len(ranked) - len(self.notes), reason={
                               "selected": "Current notes matched informative words in this task. Local selection, not independent factual verification.",
                               "no_match": "No informative content-word match. No note was added and relevance was not guessed.",
                               "empty": "No active notes for this exact project. No store was initialized or old memory migrated.",
                           }[state])
        self.revalidate()
        validate_project_recall(self.report)

    def revalidate(self):
        if self.report["state"] == "unavailable":
            return
        all_records, _, _, issues = self.memory._read()
        if (issues or snapshot_hash(all_records) != self.report["source_snapshot_hash"]
                or injection_state(self.root)["enabled"] is not False):
            raise ValueError("Project notes or settings changed during recall. Main task not started; no replacement or automatic retry.")
        self.memory._check_workspace()
        if self.notes and self.memory.selected([{key: row[key] for key in ("id", "record_hash")} for row in self.notes]) != self.notes:
            raise ValueError("Selected project notes changed before execution. No automatic retry.")
