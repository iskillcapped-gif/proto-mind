from __future__ import annotations

from copy import deepcopy
import json
import re
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4


VALID_SKILL_STATUSES = {"active", "archived"}
DEFAULT_SKILL_CATEGORY = "other"


def format_skill_command(
    command: str,
    *,
    project_root: Path,
    persistent_memory_path: Path | None = None,
) -> str | None:
    stripped = command.strip()
    normalized = " ".join(stripped.lower().split())
    if not normalized.startswith("/skills"):
        return None

    library = SkillLibrary.from_project_root(project_root)
    memory_path = persistent_memory_path or (
        project_root / "proto_mind" / "data" / "persistent_memory.json"
    )
    if normalized.startswith("/skills lifecycle"):
        from proto_mind.skill_lifecycle_restore import (
            format_procedural_skill_lifecycle_restore_command,
        )

        restore_output = format_procedural_skill_lifecycle_restore_command(
            stripped,
            skills_path=library.skills_path,
            persistent_memory_path=memory_path,
        )
        if restore_output is not None:
            return restore_output
        from proto_mind.skill_lifecycle_audit import (
            format_skill_lifecycle_audit_command,
        )

        lifecycle_output = format_skill_lifecycle_audit_command(
            stripped,
            skills_path=library.skills_path,
            persistent_memory_path=memory_path,
        )
        if lifecycle_output is not None:
            return lifecycle_output
    if normalized == "/skills status":
        return library.format_status()
    if normalized.startswith("/skills list"):
        parsed_list = _parse_list_command(stripped)
        if isinstance(parsed_list, str):
            return parsed_list
        return library.format_list(include_all=parsed_list["include_all"], category=parsed_list["category"])
    if normalized.startswith("/skills add"):
        parsed_add = _parse_add_command(stripped)
        if isinstance(parsed_add, str):
            return parsed_add
        return library.add_skill(parsed_add["name"], category=parsed_add["category"], summary=parsed_add["summary"])
    if normalized.startswith("/skills inspect"):
        skill_id = stripped[len("/skills inspect") :].strip()
        return library.format_inspect(skill_id)
    if normalized.startswith("/skills why"):
        from proto_mind.skill_provenance import format_skill_why

        skill_id = stripped[len("/skills why") :].strip()
        return format_skill_why(library.skills_path, memory_path, skill_id)
    if normalized == "/skills provenance-doctor":
        from proto_mind.skill_provenance import (
            format_skill_provenance_doctor,
            skill_provenance_doctor,
        )

        return format_skill_provenance_doctor(
            skill_provenance_doctor(library.skills_path, memory_path)
        )
    if normalized.startswith("/skills update"):
        parsed_update = _parse_update_command(stripped)
        if isinstance(parsed_update, str):
            return parsed_update
        return library.update_summary(parsed_update["skill_id"], parsed_update["summary"])
    if normalized.startswith("/skills body"):
        parsed_body = _parse_id_text_command(stripped, "/skills body", "Usage: /skills body <id> <text>")
        if isinstance(parsed_body, str):
            return parsed_body
        return library.set_body(parsed_body["id"], parsed_body["text"])
    if normalized.startswith("/skills append"):
        parsed_append = _parse_id_text_command(stripped, "/skills append", "Usage: /skills append <id> <text>")
        if isinstance(parsed_append, str):
            return parsed_append
        return library.append_body(parsed_append["id"], parsed_append["text"])
    if normalized.startswith("/skills tag"):
        parsed_tag = _parse_id_text_command(stripped, "/skills tag", "Usage: /skills tag <id> <tag>")
        if isinstance(parsed_tag, str):
            return parsed_tag
        return library.add_tag(parsed_tag["id"], parsed_tag["text"])
    if normalized.startswith("/skills untag"):
        parsed_untag = _parse_id_text_command(stripped, "/skills untag", "Usage: /skills untag <id> <tag>")
        if isinstance(parsed_untag, str):
            return parsed_untag
        return library.remove_tag(parsed_untag["id"], parsed_untag["text"])
    if normalized.startswith("/skills search"):
        parsed_search = _parse_search_command(stripped)
        if isinstance(parsed_search, str):
            return parsed_search
        return library.search(parsed_search["query"], include_all=parsed_search["include_all"])
    if normalized.startswith("/skills use"):
        skill_id = stripped[len("/skills use") :].strip()
        return library.use_skill(skill_id)
    if normalized.startswith("/skills archive"):
        skill_id = stripped[len("/skills archive") :].strip()
        return library.set_status(skill_id, "archived")
    if normalized.startswith("/skills restore"):
        skill_id = stripped[len("/skills restore") :].strip()
        return library.set_status(skill_id, "active")
    return (
        "Usage:\n"
        "  /skills status\n"
        "  /skills add <name> [--category <category>] [--summary <summary>]\n"
        "  /skills list [--all] [--category <category>]\n"
        "  /skills inspect <id>\n"
        "  /skills why <id>\n"
        "  /skills provenance-doctor\n"
        "  /skills lifecycle-status [--contract|--restore-contract]\n"
        "  /skills lifecycle-history [--all]\n"
        "  /skills lifecycle-inspect <id> [--restore-readiness|--restore-plan]\n"
        "  /skills lifecycle-doctor [--restore-contract]\n"
        "  /skills update <id> --summary <text>\n"
        "  /skills body <id> <text>\n"
        "  /skills append <id> <text>\n"
        "  /skills tag <id> <tag>\n"
        "  /skills untag <id> <tag>\n"
        "  /skills search <query> [--all]\n"
        "  /skills use <id>\n"
        "  /skills archive <id>\n"
        "  /skills restore <id>"
    )


class SkillLibrary:
    def __init__(self, skills_path: Path) -> None:
        self.skills_path = skills_path

    @classmethod
    def from_project_root(cls, project_root: Path) -> "SkillLibrary":
        return cls(project_root / "proto_mind" / "data" / "skills.jsonl")

    def format_status(self) -> str:
        state = self._read_state()
        records = state.records
        active = [skill for skill in records if skill.get("status") == "active"]
        archived = [skill for skill in records if skill.get("status") == "archived"]
        categories = Counter(str(skill.get("category") or DEFAULT_SKILL_CATEGORY) for skill in records)
        latest = _latest_skill(records)
        health = "ok"
        if state.error:
            health = "error"
        elif state.malformed_count:
            health = "malformed_jsonl"
        elif not self.skills_path.exists():
            health = "missing"
        lines = [
            "Skill Library status:",
            f"  path: {self.skills_path}",
            f"  exists: {self.skills_path.exists()}",
            f"  total_skills: {len(records)}",
            f"  active: {len(active)}",
            f"  archived: {len(archived)}",
            f"  categories: {_format_counter(categories)}",
            f"  malformed_entries: {state.malformed_count}",
            f"  file_health: {health}",
            f"  most_recently_updated: {_skill_preview(latest) if latest else 'none'}",
        ]
        if state.error:
            lines.append(f"  error: {state.error}")
        return "\n".join(lines)

    def read_snapshot(self) -> dict[str, Any]:
        """Return detached read-only data for explicit internal review adapters."""
        state = self._read_state()
        return {
            "records": deepcopy(state.records),
            "malformed_count": state.malformed_count,
            "error": state.error,
            "mutation_performed": False,
        }

    def add_skill(self, name: str, *, category: str = DEFAULT_SKILL_CATEGORY, summary: str = "") -> str:
        name = name.strip()
        if not name:
            return "Usage: /skills add <name> [--category <category>] [--summary <summary>]"
        state = self._read_state()
        if state.has_load_problem:
            return _mutation_refused(state)
        now = _utc_now()
        skill = {
            "id": _new_skill_id(now),
            "created_at": now,
            "updated_at": now,
            "name": name,
            "summary": summary.strip(),
            "body": "",
            "status": "active",
            "category": _normalize_category(category),
            "source": "operator",
            "tags": [],
            "uses": 0,
            "last_used_at": None,
        }
        self._write_records([*state.records, skill])
        return f"Skill added:\n  {skill['id']} — {_preview(name)}"

    def format_list(self, *, include_all: bool = False, category: str | None = None) -> str:
        state = self._read_state()
        if state.error:
            return f"Skill Library error: {state.error}"
        records = state.records
        if category:
            records = [skill for skill in records if str(skill.get("category") or "").casefold() == category.casefold()]
        if not include_all:
            records = [skill for skill in records if skill.get("status") == "active"]
        heading = "Skills:" if not include_all else "Skills (all):"
        if category:
            heading += f" category={category}"
        lines = [heading]
        if state.malformed_count:
            lines.append(f"  malformed_entries_skipped: {state.malformed_count}")
        if not records:
            lines.append("  (none)")
            return "\n".join(lines)
        for skill in sorted(records, key=lambda item: str(item.get("updated_at", "")), reverse=True):
            lines.append(
                "  - "
                f"{skill.get('id', 'unknown')} "
                f"[{skill.get('status', 'unknown')}] "
                f"category={skill.get('category', DEFAULT_SKILL_CATEGORY)} "
                f"{_preview(str(skill.get('name', '')))}"
                f"{_summary_suffix(skill)}"
            )
        return "\n".join(lines)

    def format_inspect(self, skill_id: str) -> str:
        skill_id = skill_id.strip()
        if not skill_id:
            return "Usage: /skills inspect <id>"
        state = self._read_state()
        if state.error:
            return f"Skill Library error: {state.error}"
        skill = _find_skill(state.records, skill_id)
        if not skill:
            return f"Skill not found: {skill_id}"
        return _format_skill_record(skill)

    def update_summary(self, skill_id: str, summary: str) -> str:
        if not skill_id.strip() or not summary.strip():
            return "Usage: /skills update <id> --summary <text>"
        return self._mutate_skill(skill_id, lambda skill: _set_field(skill, "summary", summary.strip()), "Summary updated")

    def set_body(self, skill_id: str, body: str) -> str:
        if not skill_id.strip() or not body.strip():
            return "Usage: /skills body <id> <text>"
        return self._mutate_skill(skill_id, lambda skill: _set_field(skill, "body", body.strip()), "Body updated")

    def append_body(self, skill_id: str, text: str) -> str:
        if not skill_id.strip() or not text.strip():
            return "Usage: /skills append <id> <text>"

        def callback(skill: dict[str, Any]) -> None:
            existing = str(skill.get("body") or "").rstrip()
            skill["body"] = f"{existing}\n{text.strip()}" if existing else text.strip()

        return self._mutate_skill(skill_id, callback, "Body appended")

    def add_tag(self, skill_id: str, tag: str) -> str:
        tag = tag.strip()
        if not skill_id.strip() or not tag:
            return "Usage: /skills tag <id> <tag>"

        def callback(skill: dict[str, Any]) -> None:
            tags = [str(item) for item in skill.get("tags") or []]
            if tag not in tags:
                tags.append(tag)
            skill["tags"] = tags

        return self._mutate_skill(skill_id, callback, "Tag added")

    def remove_tag(self, skill_id: str, tag: str) -> str:
        tag = tag.strip()
        if not skill_id.strip() or not tag:
            return "Usage: /skills untag <id> <tag>"

        def callback(skill: dict[str, Any]) -> None:
            skill["tags"] = [str(item) for item in skill.get("tags") or [] if str(item) != tag]

        return self._mutate_skill(skill_id, callback, "Tag removed")

    def search(self, query: str, *, include_all: bool = False) -> str:
        query = query.strip()
        if not query:
            return "Usage: /skills search <query> [--all]"
        state = self._read_state()
        if state.error:
            return f"Skill Library error: {state.error}"
        needle = query.casefold()
        records = state.records if include_all else [skill for skill in state.records if skill.get("status") == "active"]
        matches = [skill for skill in records if needle in _skill_search_text(skill).casefold()]
        lines = [f'Skill search: "{query}"' + (" (all)" if include_all else "")]
        if not matches:
            lines.append("No matches found.")
            return "\n".join(lines)
        for skill in sorted(matches, key=lambda item: str(item.get("updated_at", "")), reverse=True):
            lines.append(
                "  - "
                f"{skill.get('id', 'unknown')} "
                f"[{skill.get('status', 'unknown')}] "
                f"category={skill.get('category', DEFAULT_SKILL_CATEGORY)} "
                f"{_preview(str(skill.get('name', '')))}"
                f"{_summary_suffix(skill)}"
            )
        return "\n".join(lines)

    def use_skill(self, skill_id: str) -> str:
        skill_id = skill_id.strip()
        if not skill_id:
            return "Usage: /skills use <id>"
        state = self._read_state()
        if state.has_load_problem:
            return _mutation_refused(state)
        skill = _find_skill(state.records, skill_id)
        if not skill:
            return f"Skill not found: {skill_id}"
        now = _utc_now()
        skill["uses"] = int(skill.get("uses") or 0) + 1
        skill["last_used_at"] = now
        skill["updated_at"] = now
        self._write_records(state.records)
        return "\n".join(
            [
                "Skill used:",
                f"  id: {skill.get('id')}",
                f"  name: {skill.get('name', '')}",
                f"  category: {skill.get('category', DEFAULT_SKILL_CATEGORY)}",
                f"  uses: {skill.get('uses', 0)}",
                "Body:",
                str(skill.get("body") or "(empty)"),
            ]
        )

    def set_status(self, skill_id: str, status: str) -> str:
        if not skill_id.strip():
            return f"Usage: /skills {'archive' if status == 'archived' else 'restore'} <id>"
        if status not in VALID_SKILL_STATUSES:
            return f"Invalid skill status: {status}"
        return self._mutate_skill(skill_id, lambda skill: _set_field(skill, "status", status), f"{status.capitalize()} skill")

    def _mutate_skill(self, skill_id: str, callback: object, label: str) -> str:
        state = self._read_state()
        if state.has_load_problem:
            return _mutation_refused(state)
        skill = _find_skill(state.records, skill_id.strip())
        if not skill:
            return f"Skill not found: {skill_id.strip()}"
        callback(skill)
        skill["updated_at"] = _utc_now()
        self._write_records(state.records)
        return f"{label}:\n  {skill.get('id')} — {_preview(str(skill.get('name', '')))}"

    def _read_state(self) -> "_SkillReadState":
        if not self.skills_path.exists():
            return _SkillReadState(records=[], malformed_count=0, error=None)
        try:
            lines = self.skills_path.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            return _SkillReadState(records=[], malformed_count=0, error=str(exc))
        records: list[dict[str, Any]] = []
        malformed_count = 0
        for raw_line in lines:
            if not raw_line.strip():
                continue
            try:
                parsed = json.loads(raw_line)
            except json.JSONDecodeError:
                malformed_count += 1
                continue
            if isinstance(parsed, dict):
                records.append(_normalize_skill_record(parsed))
            else:
                malformed_count += 1
        return _SkillReadState(records=records, malformed_count=malformed_count, error=None)

    def _write_records(self, records: list[dict[str, Any]]) -> None:
        self.skills_path.parent.mkdir(parents=True, exist_ok=True)
        payload = "".join(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n" for record in records)
        temp_path = self.skills_path.with_name(f".{self.skills_path.name}.{uuid4().hex}.tmp")
        temp_path.write_text(payload, encoding="utf-8")
        temp_path.replace(self.skills_path)


class _SkillReadState:
    def __init__(self, *, records: list[dict[str, Any]], malformed_count: int, error: str | None) -> None:
        self.records = records
        self.malformed_count = malformed_count
        self.error = error

    @property
    def has_load_problem(self) -> bool:
        return bool(self.error or self.malformed_count)


def _parse_add_command(command: str) -> dict[str, str] | str:
    remainder = command.strip()[len("/skills add") :].strip()
    if not remainder:
        return "Usage: /skills add <name> [--category <category>] [--summary <summary>]"
    parsed = _parse_name_flags(remainder, default_category=DEFAULT_SKILL_CATEGORY)
    if not parsed["name"]:
        return "Usage: /skills add <name> [--category <category>] [--summary <summary>]"
    return parsed


def _parse_name_flags(text: str, *, default_category: str) -> dict[str, str]:
    category = default_category
    summary = ""
    name_parts: list[str] = []
    parts = text.split()
    index = 0
    while index < len(parts):
        token = parts[index].lower()
        if token == "--category":
            if index + 1 < len(parts):
                category = parts[index + 1]
                index += 2
                continue
        if token == "--summary":
            index += 1
            summary_parts: list[str] = []
            while index < len(parts) and parts[index].lower() != "--category":
                summary_parts.append(parts[index])
                index += 1
            summary = " ".join(summary_parts).strip()
            continue
        name_parts.append(parts[index])
        index += 1
    return {"name": " ".join(name_parts).strip(), "category": _normalize_category(category), "summary": summary}


def _parse_list_command(command: str) -> dict[str, Any] | str:
    parts = command.strip().split()
    include_all = False
    category: str | None = None
    index = 2
    while index < len(parts):
        token = parts[index].lower()
        if token == "--all":
            include_all = True
            index += 1
            continue
        if token == "--category":
            if index + 1 >= len(parts):
                return "Invalid --category value. Usage: /skills list [--all] [--category <category>]"
            category = _normalize_category(parts[index + 1])
            index += 2
            continue
        return "Usage: /skills list [--all] [--category <category>]"
    return {"include_all": include_all, "category": category}


def _parse_update_command(command: str) -> dict[str, str] | str:
    remainder = command.strip()[len("/skills update") :].strip()
    parts = remainder.split(maxsplit=1)
    if len(parts) != 2:
        return "Usage: /skills update <id> --summary <text>"
    skill_id, rest = parts
    rest = rest.strip()
    if not rest.lower().startswith("--summary "):
        return "Usage: /skills update <id> --summary <text>"
    summary = rest[len("--summary ") :].strip()
    if not summary:
        return "Usage: /skills update <id> --summary <text>"
    return {"skill_id": skill_id, "summary": summary}


def _parse_id_text_command(command: str, prefix: str, usage: str) -> dict[str, str] | str:
    remainder = command.strip()[len(prefix) :].strip()
    parts = remainder.split(maxsplit=1)
    if len(parts) != 2 or not parts[1].strip():
        return usage
    return {"id": parts[0], "text": parts[1].strip()}


def _parse_search_command(command: str) -> dict[str, Any] | str:
    remainder = command.strip()[len("/skills search") :].strip()
    if not remainder:
        return "Usage: /skills search <query> [--all]"
    parts = remainder.split()
    include_all = "--all" in [part.lower() for part in parts]
    query = " ".join(part for part in parts if part.lower() != "--all").strip()
    if not query:
        return "Usage: /skills search <query> [--all]"
    return {"query": query, "include_all": include_all}


def _normalize_skill_record(record: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(record)
    normalized.setdefault("summary", "")
    normalized.setdefault("body", "")
    normalized.setdefault("status", "active")
    normalized.setdefault("category", DEFAULT_SKILL_CATEGORY)
    normalized.setdefault("source", "operator")
    normalized.setdefault("tags", [])
    normalized.setdefault("uses", 0)
    normalized.setdefault("last_used_at", None)
    return normalized


def _format_skill_record(skill: dict[str, Any]) -> str:
    return "\n".join(
        [
            "Skill:",
            f"  id: {skill.get('id', 'unknown')}",
            f"  name: {skill.get('name', '')}",
            f"  summary: {skill.get('summary', '')}",
            f"  body: {skill.get('body', '')}",
            f"  status: {skill.get('status', 'unknown')}",
            f"  category: {skill.get('category', DEFAULT_SKILL_CATEGORY)}",
            f"  source: {skill.get('source', 'unknown')}",
            f"  tags: {skill.get('tags', [])}",
            f"  uses: {skill.get('uses', 0)}",
            f"  last_used_at: {skill.get('last_used_at')}",
            f"  created_at: {skill.get('created_at', 'unknown')}",
            f"  updated_at: {skill.get('updated_at', 'unknown')}",
        ]
    )


def _find_skill(records: list[dict[str, Any]], skill_id: str) -> dict[str, Any] | None:
    for skill in records:
        if skill.get("id") == skill_id:
            return skill
    return None


def _latest_skill(records: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not records:
        return None
    return sorted(records, key=lambda item: str(item.get("updated_at", "")), reverse=True)[0]


def _skill_preview(skill: dict[str, Any]) -> str:
    return f"{skill.get('id', 'unknown')} [{skill.get('status', 'unknown')}] — {_preview(str(skill.get('name', '')))}"


def _skill_search_text(skill: dict[str, Any]) -> str:
    values = [
        skill.get("id"),
        skill.get("name"),
        skill.get("summary"),
        skill.get("body"),
        skill.get("category"),
        " ".join(str(tag) for tag in skill.get("tags") or []),
    ]
    return " ".join(str(value or "") for value in values)


def _summary_suffix(skill: dict[str, Any]) -> str:
    summary = str(skill.get("summary") or "").strip()
    return f" — {_preview(summary, limit=80)}" if summary else ""


def _set_field(record: dict[str, Any], field_name: str, value: object) -> None:
    record[field_name] = value


def _mutation_refused(state: _SkillReadState) -> str:
    if state.error:
        return f"Skill Library error: {state.error}"
    return "Skill Library error: skills file contains malformed JSONL; refusing to modify."


def _format_counter(counter: Counter[str]) -> str:
    if not counter:
        return "none"
    return ", ".join(f"{key}={value}" for key, value in sorted(counter.items()))


def _normalize_category(category: str) -> str:
    normalized = category.strip().lower().replace(" ", "_")
    return normalized or DEFAULT_SKILL_CATEGORY


def _new_skill_id(timestamp: str) -> str:
    compact = re.sub(r"[^0-9]", "", timestamp)[:14]
    return f"skill_{compact}_{uuid4().hex[:4]}"


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _preview(text: str, limit: int = 120) -> str:
    normalized = " ".join(text.split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 3] + "..."
