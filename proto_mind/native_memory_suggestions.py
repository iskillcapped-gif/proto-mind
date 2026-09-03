"""Bounded operator-statement suggestions; only an explicit review saves a project note."""
from copy import deepcopy
import hashlib
from pathlib import Path
import re
from uuid import UUID

from proto_mind.native_desk import injection_state
from proto_mind.native_private_records import HASH
from proto_mind.native_project_memory import NativeProjectMemory
from proto_mind.native_work_sessions import WorkSessionError, WorkSessionStore, workspace_identity


SCHEMA = "proto_mind.native_memory_suggestions.v1"
METHODS = frozenset({"memory_suggestion_preview", "memory_suggestion_save"})
MAX_SOURCE = 12_000
MAX_QUOTE = 600
MAX_CANDIDATES = 2
ALGORITHM = "explicit_operator_statements_v1"
PATTERNS = (
    ("preference", r"(?:я предпочитаю|мне удобнее|i prefer|my preference is)\s+\S"),
    ("decision", r"(?:мы решили|решили|we decided|our decision is)\s+\S"),
    ("project_fact", r"(?:в (?:этом )?проекте используем|наш проект использует|in this project we use|our project uses)\s+\S"),
    ("constraint", r"(?:в (?:этом )?проекте (?:нельзя|не используем|только)|for this project[, ]+\s*(?:never|only|do not))\s+\S"),
    ("lesson", r"(?:вывод на будущее|урок на будущее|lesson learned)\s*:\s*\S"),
)
PREFIXES = [(kind, re.compile(pattern, re.IGNORECASE)) for kind, pattern in PATTERNS]
# A conservative first slice intentionally ignores pasted, quoted and hypothetical material.
UNSAFE_SOURCE = re.compile(
    r"```|~~~|^[ \t]*>|[<>]|\b(?:translate|translation|quote|quoted|example|hypothetically|suppose)\b"
    r"|\b(?:переведи|перевод|цитата|цитирую|пример|например|допустим|предположим)\b"
    r"|(?:вот|ниже)\s+(?:чужой\s+)?(?:текст|сообщение|инструкции)|\b(?:he said|she said|pasted text)\b"
    r"|(?:не|don't|do not)\s+(?:запоминай|сохраняй|remember|save)", re.IGNORECASE | re.MULTILINE)
UNCERTAIN = re.compile(r"[?¿]|\b(?:если|может|возможно|раньше|когда-то|if|maybe|perhaps|previously|used to)\b", re.IGNORECASE)
SENSITIVE = re.compile(
    r"\b(?:password|passwd|secret|api[_ -]?key|(?:access[_ -]?)?token|парол\w*|секрет\w*|токен\w*)\b"
    r"|\bsk-[A-Za-z0-9_-]{8,}|-----BEGIN|://[^\s/]+@", re.IGNORECASE)


def text_hash(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def candidate_id(run_id, input_hash, kind, start, end, quote_hash):
    return text_hash(f"{run_id}\n{input_hash}\n{kind}\n{start}:{end}\n{quote_hash}")


def normalized_note(text):
    return " ".join(text.casefold().split()).rstrip(".!; ")


def explicit_statements(text):
    """Return whole original sentences and Unicode-code-point offsets, never a paraphrase."""
    if (not isinstance(text, str) or not 1 <= len(text) <= MAX_SOURCE or UNSAFE_SOURCE.search(text)
            or SENSITIVE.search(text) or any(ord(char) < 32 and char not in "\n\t\r" for char in text)):
        return []
    found = []
    # Split at sentence boundaries, not decimal/version dots or abbreviations inside a sentence.
    for match in re.finditer(r"[^\n]+", text):
        line = match.group()
        for sentence in re.finditer(r".+?(?:[.!?](?=\s|$)|$)", line):
            raw = sentence.group()
            leading = re.match(r"\s*(?:(?:[-*]|\d+[.)])\s+)?(?:(?:брат|bro)[, :]\s*)?", raw, re.IGNORECASE).end()
            quote = raw[leading:].strip()
            if not 12 <= len(quote) <= MAX_QUOTE or UNCERTAIN.search(quote):
                continue
            kind = next((kind for kind, pattern in PREFIXES if pattern.match(quote)), None)
            if kind:
                start = match.start() + sentence.start() + leading
                found.append({"kind": kind, "start": start, "end": start + len(quote), "content_sha256": text_hash(quote)})
    return found


def _check_source(run, text, workspace):
    if (not isinstance(run, dict) or run.get("status") != "completed" or run.get("display_status") != "completed"
            or run.get("provider") != "codex" or not workspace or run.get("workspace") != workspace
            or not isinstance(text, str) or not 1 <= len(text) <= 32_000
            or run.get("input_sha256") != text_hash(text) or run.get("input_chars") != len(text)
            or not HASH.fullmatch(str(run.get("fingerprint", "")))):
        raise ValueError("The original completed Codex message and exact project folder must verify. Nothing saved.")
    UUID(run["id"]); UUID(run["conversation_id"])


def suggestions(root, state_dir, run, text):
    workspace = run.get("workspace")
    _check_source(run, text, workspace)
    source = {key: deepcopy(run[key]) for key in ("conversation_id", "workspace", "input_sha256", "input_chars")}
    source.update(run_id=run["id"], fingerprint=run["fingerprint"])
    report = {"schema": SCHEMA, "algorithm": ALGORITHM, "source": source, "state": "no_candidates", "reason": "no_explicit_statement",
              "candidates": [], "omitted_count": 0, "read_only": True, "model_call_performed": False,
              "automatic_save": False, "permission_granted": False}
    candidates = explicit_statements(text)
    if not candidates:
        return report
    try:
        if injection_state(root)["enabled"] is not False or workspace_identity(Path(workspace["path"])) != workspace:
            raise ValueError("Scope or Context setting changed.")
        memory = NativeProjectMemory(root, state_dir, run["conversation_id"], workspace)
        _, records, replaced, issues = memory._read()
        if issues:
            raise ValueError("Private note integrity needs review.")
        seen = {normalized_note(row["body"]["content"]) for row in records if row["id"] not in replaced}
        for candidate in candidates:
            quote = text[candidate["start"]:candidate["end"]]
            normalized = normalized_note(quote)
            if normalized in seen:
                continue
            seen.add(normalized)
            if len(report["candidates"]) == MAX_CANDIDATES:
                report["omitted_count"] += 1
                continue
            report["candidates"].append({"id": candidate_id(run["id"], source["input_sha256"], candidate["kind"],
                                                           candidate["start"], candidate["end"], candidate["content_sha256"]), **candidate})
        report["state"] = "suggested" if report["candidates"] else "no_candidates"
        report["reason"] = "explicit_operator_statement" if report["candidates"] else "already_in_current_notes"
    except (ValueError, OSError, WorkSessionError):
        report.update(state="unavailable", reason="scope_settings_or_notes_need_review", candidates=[], omitted_count=0)
    return report


def parse_request(method, params):
    fields = {"conversation_id", "workspace_root", "run", "text", "candidate_id"}
    if method == "memory_suggestion_save":
        fields |= {"preview_fingerprint", "confirmation_token", "acknowledge_operator_note"}
    if method not in METHODS or not isinstance(params, dict) or set(params) != fields:
        raise ValueError("Only exact source-bound suggestion review/save is supported; no arbitrary note or command.")
    UUID(params["conversation_id"])
    reference = params["run"]
    if (not isinstance(reference, dict) or set(reference) != {"run_id", "fingerprint"}
            or not isinstance(params["workspace_root"], str) or not params["workspace_root"].startswith("/")
            or not HASH.fullmatch(str(reference["fingerprint"])) or not HASH.fullmatch(str(params["candidate_id"]))):
        raise ValueError("Invalid source or project reference.")
    UUID(reference["run_id"])


class NativeMemorySuggestion:
    def __init__(self, root, state_dir, workspace, params):
        self.root, self.state, self.workspace, self.params = root, state_dir, workspace, params
        self.runs = WorkSessionStore(state_dir, root)
        self.memory = NativeProjectMemory(root, state_dir, params["conversation_id"], workspace)

    def preview(self):
        run = self.runs.inspect(self.params["run"], self.params["conversation_id"])
        text = self.params["text"]
        _check_source(run, text, self.workspace)
        report = suggestions(self.root, self.state, run, text)
        candidate = next((item for item in report["candidates"] if item["id"] == self.params["candidate_id"]), None)
        if candidate is None:
            raise ValueError("Suggestion is no longer eligible, already saved, or not an explicit operator statement. Nothing saved.")
        quote = text[candidate["start"]:candidate["end"]]
        note = {"kind": candidate["kind"], "content": quote, "supersedes_id": "",
                "basis": f"Operator message in Native run {run['id']}; input SHA-256 {run['input_sha256']}; "
                         f"Unicode characters {candidate['start']}:{candidate['end']}. Explicitly reviewed, not independently verified."}
        preview = self.memory.preview(note)
        return {"schema": "proto_mind.native_memory_suggestion_review.v1", "source": report["source"],
                "candidate": candidate, "note_preview": preview, "read_only": True, "automatic_save": False,
                "model_call_performed": False, "permission_granted": False}

    def save(self):
        review = self.preview()
        preview = review["note_preview"]
        # Revalidate the saved source immediately before the existing snapshot-guarded writer.
        self.runs.inspect(self.params["run"], self.params["conversation_id"])
        note = {key: preview["body"][key] for key in ("kind", "content", "basis", "supersedes_id")}
        return self.memory.save({"note": note, **{key: self.params[key] for key in
                                ("preview_fingerprint", "confirmation_token", "acknowledge_operator_note")}})
