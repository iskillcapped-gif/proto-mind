from __future__ import annotations

import json
import re
import string
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4


IDENTITY_VERSION = 1
PROFILE_FIELDS = {"name", "role", "style", "operator_name", "mission"}
SECTION_BY_COMMAND = {
    "/identity add-value": "values",
    "/identity add-principle": "principles",
    "/identity add-boundary": "boundaries",
}
SECTION_LABELS = {
    "values": "value",
    "principles": "principle",
    "boundaries": "boundary",
}


def format_identity_command(command: str, *, project_root: Path) -> str | None:
    stripped = command.strip()
    normalized = " ".join(stripped.lower().split())
    if not normalized.startswith("/identity"):
        return None

    store = IdentityStore.from_project_root(project_root)
    if normalized == "/identity status":
        return store.format_status()
    if normalized == "/identity show":
        return store.format_show()
    if normalized.startswith("/identity set"):
        parsed_set = _parse_set_command(stripped)
        if isinstance(parsed_set, str):
            return parsed_set
        return store.set_profile_field(parsed_set["field"], parsed_set["value"])
    for prefix, section in SECTION_BY_COMMAND.items():
        if normalized.startswith(prefix):
            text = stripped[len(prefix) :].strip()
            return store.add_item(section, text)
    if normalized.startswith("/identity archive"):
        item_id = stripped[len("/identity archive") :].strip()
        return store.set_item_active(item_id, False)
    if normalized.startswith("/identity restore"):
        item_id = stripped[len("/identity restore") :].strip()
        return store.set_item_active(item_id, True)
    if normalized.startswith("/identity history"):
        parsed_history = _parse_history_command(stripped)
        if isinstance(parsed_history, str):
            return parsed_history
        return store.format_history(limit=parsed_history["limit"])
    if normalized == "/identity doctor":
        return store.format_doctor()
    return _usage()


class IdentityStore:
    def __init__(self, identity_path: Path) -> None:
        self.identity_path = identity_path

    @classmethod
    def from_project_root(cls, project_root: Path) -> "IdentityStore":
        return cls(project_root / "proto_mind" / "data" / "identity.json")

    def format_status(self) -> str:
        state = self._read_state(initialize=True)
        if state.error:
            return f"Identity error: {state.error}"
        data = state.data
        profile = data.get("profile", {})
        lines = [
            "Identity / Values status:",
            f"  path: {self.identity_path}",
            f"  exists: {self.identity_path.exists()}",
            f"  version: {data.get('version', 'unknown')}",
            f"  name: {profile.get('name', '')}",
            f"  role: {profile.get('role', '')}",
            f"  values_count: {len(_active_items(data, 'values'))}",
            f"  principles_count: {len(_active_items(data, 'principles'))}",
            f"  boundaries_count: {len(_active_items(data, 'boundaries'))}",
            f"  history_count: {len(data.get('history') or [])}",
            f"  updated_at: {data.get('updated_at', '')}",
        ]
        return "\n".join(lines)

    def format_show(self) -> str:
        state = self._read_state(initialize=True)
        if state.error:
            return f"Identity error: {state.error}"
        data = state.data
        profile = data.get("profile", {})
        lines = [
            "Identity / Values",
            "",
            "Profile:",
            f"  name: {profile.get('name', '')}",
            f"  role: {profile.get('role', '')}",
            f"  style: {profile.get('style', '')}",
            f"  operator_name: {profile.get('operator_name', '')}",
            f"  mission: {profile.get('mission', '')}",
            "",
            "Values:",
        ]
        lines.extend(_format_items(_active_items(data, "values")))
        lines.append("Principles:")
        lines.extend(_format_items(_active_items(data, "principles")))
        lines.append("Boundaries:")
        lines.extend(_format_items(_active_items(data, "boundaries")))
        return "\n".join(lines)

    def set_profile_field(self, field: str, value: str) -> str:
        field = field.strip()
        value = value.strip()
        if field not in PROFILE_FIELDS or not value:
            return _allowed_fields_message()
        state = self._read_state(initialize=True)
        if state.error:
            return f"Identity error: {state.error}"
        data = state.data
        old_value = str(data["profile"].get(field, ""))
        data["profile"][field] = value
        self._touch(data)
        _append_history(data, action="set_profile", field=f"profile.{field}", old=old_value, new=value)
        self._write_data(data)
        return f"Identity field updated:\n  {field}: {value}"

    def add_item(self, section: str, text: str) -> str:
        text = text.strip()
        if section not in {"values", "principles", "boundaries"} or not text:
            return _add_usage(section)
        state = self._read_state(initialize=True)
        if state.error:
            return f"Identity error: {state.error}"
        data = state.data
        for existing in _active_items(data, section):
            if _normalize_text(str(existing.get("text") or "")) == _normalize_text(text):
                return f"Identity {SECTION_LABELS[section]} already exists:\n  {existing.get('id')} — {_preview(text)}"
        now = _utc_now()
        item = {
            "id": _new_item_id(section, now),
            "text": text,
            "created_at": now,
            "active": True,
        }
        data[section].append(item)
        self._touch(data)
        _append_history(data, action=f"add_{SECTION_LABELS[section]}", field=section, old="", new=text)
        self._write_data(data)
        return f"Identity {SECTION_LABELS[section]} added:\n  {item['id']} — {_preview(text)}"

    def set_item_active(self, item_id: str, active: bool) -> str:
        item_id = item_id.strip()
        if not item_id:
            return f"Usage: /identity {'restore' if active else 'archive'} <id>"
        state = self._read_state(initialize=True)
        if state.error:
            return f"Identity error: {state.error}"
        data = state.data
        found = _find_item(data, item_id)
        if not found:
            return f"Identity item not found: {item_id}"
        section, item = found
        old = str(item.get("active", True))
        item["active"] = active
        self._touch(data)
        _append_history(
            data,
            action="restore" if active else "archive",
            field=f"{section}.{item_id}.active",
            old=old,
            new=str(active),
        )
        self._write_data(data)
        label = "Restored" if active else "Archived"
        return f"{label} identity item:\n  {item_id} — {_preview(str(item.get('text', '')))}"

    def format_history(self, *, limit: int = 10) -> str:
        state = self._read_state(initialize=True)
        if state.error:
            return f"Identity error: {state.error}"
        history = list(state.data.get("history") or [])
        rows = sorted(history, key=lambda item: str(item.get("created_at", "")), reverse=True)[:limit]
        lines = [f"Identity history: last {limit}"]
        if not rows:
            lines.append("  (none)")
            return "\n".join(lines)
        for entry in rows:
            lines.append(
                "  - "
                f"{entry.get('id', 'unknown')} "
                f"{entry.get('created_at', '')} "
                f"{entry.get('action', '')} "
                f"{entry.get('field', '')}: "
                f"{_preview(str(entry.get('old', '')), limit=40)} -> {_preview(str(entry.get('new', '')), limit=80)}"
            )
        return "\n".join(lines)

    def format_doctor(self) -> str:
        state = self._read_state(initialize=False)
        findings: list[dict[str, str]] = []
        if state.error:
            findings.append({"severity": "ERROR", "message": f"Identity file cannot be loaded: {state.error}"})
            return _format_doctor_report(findings)
        if state.data is None:
            findings.append({"severity": "WARN", "message": "Identity file not found."})
            return _format_doctor_report(findings)
        data = state.data
        for key in ("version", "updated_at", "profile", "values", "principles", "boundaries", "history"):
            if key not in data:
                findings.append({"severity": "WARN", "message": f"Missing top-level key: {key}"})
        profile = data.get("profile") if isinstance(data.get("profile"), dict) else {}
        for field in PROFILE_FIELDS:
            if field not in profile:
                findings.append({"severity": "WARN", "message": f"Missing profile field: {field}"})
        for section in ("values", "principles", "boundaries"):
            items = data.get(section)
            if not isinstance(items, list):
                findings.append({"severity": "WARN", "message": f"{section} is not a list"})
                continue
            active_items = [item for item in items if isinstance(item, dict) and item.get("active", True)]
            if not active_items:
                findings.append({"severity": "WARN", "message": f"No active {section}."})
            for item in items:
                if not isinstance(item, dict):
                    findings.append({"severity": "WARN", "message": f"Malformed item in {section}."})
                    continue
                if not str(item.get("text") or "").strip():
                    findings.append({"severity": "WARN", "message": f"Empty text in {section}: {item.get('id', 'unknown')}"})
            for text, count in _duplicate_text_counts(active_items).items():
                if count > 1:
                    findings.append({"severity": "WARN", "message": f"Duplicate active {section}: {_preview(text)} x{count}"})
        if not isinstance(data.get("history"), list) or not data.get("history"):
            findings.append({"severity": "WARN", "message": "Identity history is empty."})
        if not data.get("updated_at"):
            findings.append({"severity": "WARN", "message": "updated_at is missing."})
        return _format_doctor_report(findings)

    def read_summary(self) -> dict[str, Any]:
        state = self._read_state(initialize=False)
        if state.error:
            return {"status": "ERROR", "error": state.error, "name": "unknown", "role": "unknown", "active_values": 0, "active_boundaries": 0}
        if state.data is None:
            return {"status": "missing", "name": "none", "role": "none", "active_values": 0, "active_boundaries": 0}
        data = state.data
        profile = data.get("profile", {}) if isinstance(data.get("profile"), dict) else {}
        return {
            "status": "OK",
            "name": profile.get("name", ""),
            "role": profile.get("role", ""),
            "active_values": len(_active_items(data, "values")),
            "active_boundaries": len(_active_items(data, "boundaries")),
        }

    def _read_state(self, *, initialize: bool) -> "_IdentityReadState":
        if not self.identity_path.exists():
            if not initialize:
                return _IdentityReadState(data=None, error=None)
            data = _default_identity()
            self._write_data(data)
            return _IdentityReadState(data=data, error=None)
        try:
            parsed = json.loads(self.identity_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            return _IdentityReadState(data=None, error=str(exc))
        if not isinstance(parsed, dict):
            return _IdentityReadState(data=None, error="identity root is not an object")
        return _IdentityReadState(data=_normalize_identity(parsed), error=None)

    def _write_data(self, data: dict[str, Any]) -> None:
        self.identity_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self.identity_path.with_name(f".{self.identity_path.name}.{uuid4().hex}.tmp")
        temp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        temp_path.replace(self.identity_path)

    def _touch(self, data: dict[str, Any]) -> None:
        data["updated_at"] = _utc_now()


class _IdentityReadState:
    def __init__(self, *, data: dict[str, Any] | None, error: str | None) -> None:
        self.data = data
        self.error = error


def _default_identity() -> dict[str, Any]:
    now = _utc_now()
    data = {
        "version": IDENTITY_VERSION,
        "updated_at": now,
        "profile": {
            "name": "Proto-Mind",
            "role": "local-first cognitive assistant",
            "style": "clear, careful, transparent, operator-guided",
            "operator_name": "",
            "mission": "Help maintain continuity across memory, reflection, goals, tasks, experiments, skills, and operating loop.",
        },
        "values": [],
        "principles": [],
        "boundaries": [],
        "history": [],
    }
    for text in [
        "Local-first by default.",
        "Memory integrity matters.",
        "Operator transparency over hidden behavior.",
        "Safety boundaries before autonomy.",
        "Prefer small reversible steps over risky large changes.",
    ]:
        data["values"].append(_new_default_item("values", text, now))
    for text in [
        "Create checkpoint before modifying code or memory structure.",
        "Prefer deterministic diagnostics before auto-fixes.",
        "Suggest commands rather than silently mutating state.",
        "Keep CLI, Desktop UI, and tests stable.",
        "Record lessons as experiments/skills before relying on them.",
    ]:
        data["principles"].append(_new_default_item("principles", text, now))
    for text in [
        "No autonomous shell execution.",
        "No hidden memory edits.",
        "No destructive actions without explicit operator approval.",
        "No external-world actions without explicit operator approval.",
        "No self-modification without checkpoint and operator approval.",
    ]:
        data["boundaries"].append(_new_default_item("boundaries", text, now))
    _append_history(data, action="init", field="", old="", new="default identity v1")
    data["updated_at"] = now
    return data


def _new_default_item(section: str, text: str, timestamp: str) -> dict[str, Any]:
    return {"id": _new_item_id(section, timestamp), "text": text, "created_at": timestamp, "active": True}


def _normalize_identity(data: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(data)
    normalized.setdefault("version", IDENTITY_VERSION)
    normalized.setdefault("updated_at", "")
    profile = dict(normalized.get("profile") or {})
    profile.setdefault("name", "")
    profile.setdefault("role", "")
    profile.setdefault("style", "")
    profile.setdefault("operator_name", "")
    profile.setdefault("mission", "")
    normalized["profile"] = profile
    for section in ("values", "principles", "boundaries", "history"):
        if not isinstance(normalized.get(section), list):
            normalized[section] = []
    for section in ("values", "principles", "boundaries"):
        normalized[section] = [_normalize_item(item) for item in normalized[section] if isinstance(item, dict)]
    normalized["history"] = [_normalize_history(item) for item in normalized["history"] if isinstance(item, dict)]
    return normalized


def _normalize_item(item: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(item)
    normalized.setdefault("id", "")
    normalized.setdefault("text", "")
    normalized.setdefault("created_at", "")
    normalized.setdefault("active", True)
    return normalized


def _normalize_history(item: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(item)
    normalized.setdefault("id", "")
    normalized.setdefault("created_at", "")
    normalized.setdefault("action", "")
    normalized.setdefault("field", "")
    normalized.setdefault("old", "")
    normalized.setdefault("new", "")
    return normalized


def _parse_set_command(command: str) -> dict[str, str] | str:
    remainder = command.strip()[len("/identity set") :].strip()
    parts = remainder.split(maxsplit=1)
    if len(parts) != 2:
        return "Usage: /identity set <field> <value>\n" + _allowed_fields_message()
    field, value = parts[0].strip(), parts[1].strip()
    if field not in PROFILE_FIELDS or not value:
        return _allowed_fields_message()
    return {"field": field, "value": value}


def _parse_history_command(command: str) -> dict[str, int] | str:
    parts = command.strip().split()
    limit = 10
    if len(parts) == 2:
        return {"limit": limit}
    if len(parts) == 4 and parts[2].lower() == "--limit":
        try:
            limit = int(parts[3])
        except ValueError:
            return "Invalid --limit value. Usage: /identity history [--limit N]"
        if limit <= 0:
            return "--limit must be greater than 0."
        return {"limit": limit}
    return "Usage: /identity history [--limit N]"


def _append_history(data: dict[str, Any], *, action: str, field: str, old: str, new: str) -> None:
    now = _utc_now()
    history = data.setdefault("history", [])
    history.append(
        {
            "id": _new_history_id(now),
            "created_at": now,
            "action": action,
            "field": field,
            "old": old,
            "new": new,
        }
    )


def _find_item(data: dict[str, Any], item_id: str) -> tuple[str, dict[str, Any]] | None:
    for section in ("values", "principles", "boundaries"):
        for item in data.get(section) or []:
            if isinstance(item, dict) and item.get("id") == item_id:
                return section, item
    return None


def _active_items(data: dict[str, Any], section: str) -> list[dict[str, Any]]:
    return [item for item in data.get(section) or [] if isinstance(item, dict) and item.get("active", True)]


def _format_items(items: list[dict[str, Any]]) -> list[str]:
    if not items:
        return ["  (none)"]
    return [f"  - {item.get('id', 'unknown')} — {item.get('text', '')}" for item in items]


def _duplicate_text_counts(items: list[dict[str, Any]]) -> dict[str, int]:
    counts = Counter(_normalize_text(str(item.get("text") or "")) for item in items if str(item.get("text") or "").strip())
    return {text: count for text, count in counts.items() if count > 1}


def _normalize_text(text: str) -> str:
    table = str.maketrans("", "", string.punctuation)
    return " ".join(text.casefold().translate(table).split())


def _format_doctor_report(findings: list[dict[str, str]]) -> str:
    status = "OK"
    if any(item["severity"] == "ERROR" for item in findings):
        status = "ERROR"
    elif any(item["severity"] == "WARN" for item in findings):
        status = "WARN"
    lines = ["Identity Doctor", f"Status: {status}", "", "Findings:"]
    if not findings:
        lines.append("- [OK] Identity profile appears healthy.")
    else:
        for finding in findings:
            lines.append(f"- [{finding['severity']}] {finding['message']}")
    lines.append("")
    lines.append("Recommendations:")
    if status == "OK":
        lines.append("- No action needed.")
    else:
        lines.append("- Inspect with /identity show and update manually if needed.")
    return "\n".join(lines)


def _allowed_fields_message() -> str:
    return "Allowed fields: name, role, style, operator_name, mission"


def _add_usage(section: str) -> str:
    command = {
        "values": "/identity add-value <text>",
        "principles": "/identity add-principle <text>",
        "boundaries": "/identity add-boundary <text>",
    }.get(section, "/identity add-value <text>")
    return f"Usage: {command}"


def _usage() -> str:
    return (
        "Usage:\n"
        "  /identity status\n"
        "  /identity show\n"
        "  /identity set <name|role|style|operator_name|mission> <value>\n"
        "  /identity add-value <text>\n"
        "  /identity add-principle <text>\n"
        "  /identity add-boundary <text>\n"
        "  /identity archive <id>\n"
        "  /identity restore <id>\n"
        "  /identity history [--limit N]\n"
        "  /identity doctor"
    )


def _new_item_id(section: str, timestamp: str) -> str:
    prefix = {"values": "val", "principles": "pr", "boundaries": "bnd"}.get(section, "id")
    return f"{prefix}_{_compact_timestamp(timestamp)}_{uuid4().hex[:4]}"


def _new_history_id(timestamp: str) -> str:
    return f"hist_{_compact_timestamp(timestamp)}_{uuid4().hex[:4]}"


def _compact_timestamp(timestamp: str) -> str:
    return re.sub(r"[^0-9]", "", timestamp)[:14]


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _preview(text: str, limit: int = 120) -> str:
    normalized = " ".join(text.split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 3] + "..."
