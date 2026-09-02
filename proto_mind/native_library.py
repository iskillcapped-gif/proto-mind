"""Bounded operator-only views of existing stores, never retrieval or command dispatch.

MemoryStore construction can create files and legacy loaders synthesize defaults.
This boundary reads original bytes without initialization, repair, or usage writes.
Only the fixed stores below are addressable; records never become model context.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import stat

from proto_mind.goal_stack import VALID_GOAL_PRIORITIES, VALID_GOAL_STATUSES
from proto_mind.memory_provenance import verify_memory_provenance
from proto_mind.models import MemoryRecord
from proto_mind.skill_library import VALID_SKILL_STATUSES
from proto_mind.skill_provenance import verify_procedural_skill_provenance


MAX_SOURCE_BYTES = 16 * 1024 * 1024
MAX_SOURCE_RECORDS = 5000
PAGE_SIZE = 100
MAX_DETAIL_CHARS = 24_000
SOURCES = {
    "memory": (("persistent", "persistent_memory.json"), ("working", "working_memory.json")),
    "goals": (("goals", "goals.jsonl"),),
    "skills": (("skills", "skills.jsonl"),),
}


def _text(value: object, limit: int = 200) -> str:
    if not isinstance(value, str):
        return ""
    return "".join("\ufffd" if 0xD800 <= ord(char) <= 0xDFFF else char
                   for char in value[:limit] if ord(char) >= 32 or char in "\n\t")


def _preview(value: object, limit: int = 220) -> str:
    text = " ".join(_text(value, limit * 4).split())
    return text[:limit] + ("..." if len(text) > limit else "")


def _normalized(value: str) -> str:
    return " ".join(value.casefold().split())


def _no_constant(value: str):
    raise ValueError("Non-finite JSON numbers are not supported.")


def _scalar(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return _text(value, 400)
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int) or isinstance(value, float) and math.isfinite(value):
        return str(value)[:80]
    return "unknown"


class NativeLibrary:
    def __init__(self, project_root: Path) -> None:
        self.root = project_root.resolve()

    def _read_bytes(self, filename: str) -> tuple[bytes, os.stat_result]:
        directory = descriptor = None
        try:
            flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
            directory = os.open("/", flags)
            for part in (*self.root.parts[1:], "proto_mind", "data"):
                child = os.open(part, flags, dir_fd=directory)
                os.close(directory)
                directory = child
            descriptor = os.open(filename, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
            info = os.fstat(descriptor)
            if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_SOURCE_BYTES:
                raise ValueError("Store is not a regular file within the 16 MiB view limit.")
            with os.fdopen(descriptor, "rb", closefd=False) as source:
                data = source.read(MAX_SOURCE_BYTES + 1)
            if len(data) > MAX_SOURCE_BYTES:
                raise ValueError("Store grew beyond the view limit; no partial bytes were parsed.")
            return data, info
        finally:
            if descriptor is not None:
                os.close(descriptor)
            if directory is not None:
                os.close(directory)

    def _source(self, collection: str, store: str, filename: str) -> tuple[dict, list[dict]]:
        source = {"store": store, "path": str(self.root / "proto_mind" / "data" / filename),
                  "exists": True, "health": "OK", "record_count": 0, "skipped_count": 0,
                  "sha256": "", "modified_at": "", "message": ""}
        try:
            data, info = self._read_bytes(filename)
            source["sha256"] = hashlib.sha256(data).hexdigest()
            source["modified_at"] = datetime.fromtimestamp(info.st_mtime, timezone.utc).isoformat(timespec="seconds")
            text = data.decode("utf-8")
            invalid_lines = 0
            if filename.endswith(".json"):
                records = json.loads(text, parse_constant=_no_constant)
                if not isinstance(records, list):
                    raise ValueError("Expected a JSON array; the original file was not changed.")
                total = len(records)
                records = records[:MAX_SOURCE_RECORDS]
            else:
                records, total = [], 0
                for line in text.split("\n"):
                    if not line.strip():
                        continue
                    total += 1
                    if total > MAX_SOURCE_RECORDS:
                        continue
                    try:
                        records.append(json.loads(line, parse_constant=_no_constant))
                    except (ValueError, RecursionError):
                        invalid_lines += 1
            source["record_count"] = total
            source["skipped_count"] = invalid_lines + max(0, total - MAX_SOURCE_RECORDS)
            valid = []
            for record in records:
                if not self._valid_identity(collection, record):
                    source["skipped_count"] += 1
                else:
                    valid.append(record)
            counts = Counter(record["id"] for record in valid)
            unique = [record for record in valid if counts[record["id"]] == 1]
            source["skipped_count"] += len(valid) - len(unique)
            if source["skipped_count"]:
                source["health"] = "WARN" if unique else "ERROR"
                source["message"] = "Malformed, ambiguous duplicate-ID, or over-limit entries were omitted; inspect the source manually."
            return source, unique
        except FileNotFoundError:
            source.update(exists=False, health="WARN", message="Store is missing. Viewing does not create it.")
        except (OSError, UnicodeError):
            source.update(health="ERROR", message="Store is unreadable, invalid UTF-8, a symlink, or a non-directory path. No fallback or repair.")
        except (ValueError, RecursionError, OverflowError):
            source.update(health="ERROR", message="Store has invalid JSON/root data or exceeds the bounded view limit. No repair attempted.")
        return source, []

    @staticmethod
    def _valid_identity(collection: str, record: object) -> bool:
        if not isinstance(record, dict):
            return False
        record_id = record.get("id")
        title = record.get({"memory": "content", "goals": "title", "skills": "name"}[collection])
        return (isinstance(record_id, str) and bool(record_id.strip()) and len(record_id) <= 200
                and not any(ord(char) < 32 or 0xD800 <= ord(char) <= 0xDFFF for char in record_id)
                and isinstance(title, str))

    @staticmethod
    def _memory_evidence(store: str, raw: dict) -> dict:
        """Verify embedded learning provenance without inventing legacy evidence."""
        base = {
            "schema": "proto_mind.native_memory_evidence.v1",
            "read_only": True,
            "record_id": _text(raw.get("id"), 200),
            "store": store,
            "memory_type": _text(raw.get("type"), 80) or "unknown",
            "record_source": _text(raw.get("source"), 120) or "unknown",
            "active": raw.get("active", True) is True,
            "status": "UNAVAILABLE",
            "verified": False,
            "provenance_id": "",
            "provenance_schema": "",
            "provenance_hash": "",
            "evidence_event_ids": [],
            "source_kinds": [],
            "confirmation_method": "",
            "operator_confirmation_recorded": False,
            "automatic_promotion": False,
            "selected_scope_hash": "",
            "issues": [],
            "warnings": ["This memory has no embedded durable learning provenance."],
            "explanation": (
                "This is an operator or legacy memory. Proto-Mind will not invent "
                "an evidence chain for it."
            ),
            "no_retrieval": True,
            "no_model_call": True,
            "no_network_call": True,
            "store_mutation": False,
        }
        if "provenance" not in raw:
            return base
        try:
            record = MemoryRecord.from_dict(raw)
            check = verify_memory_provenance(record)
        except (TypeError, ValueError, OverflowError):
            return {
                **base,
                "status": "ERROR",
                "issues": ["Memory fields cannot be validated against the durable provenance contract."],
                "warnings": [],
                "explanation": "Stored provenance is present, but the memory record is malformed.",
            }
        provenance = raw.get("provenance")
        material = provenance if isinstance(provenance, dict) else {}

        def texts(key: str, limit: int = 64) -> list[str]:
            value = material.get(key)
            if not isinstance(value, list):
                return []
            return [_text(item, 200) for item in value[:limit] if isinstance(item, str)]

        return {
            **base,
            "status": check.status,
            "verified": check.verified,
            "provenance_id": _text(check.provenance_id, 200),
            "provenance_schema": _text(check.schema, 200),
            "provenance_hash": _text(material.get("provenance_hash"), 64),
            "evidence_event_ids": texts("evidence_event_ids"),
            "source_kinds": texts("source_kinds"),
            "confirmation_method": _text(material.get("confirmation_method"), 120),
            "operator_confirmation_recorded": material.get("operator_confirmation_recorded") is True,
            "automatic_promotion": material.get("automatic_promotion") is True,
            "selected_scope_hash": _text(material.get("selected_scope_hash"), 64),
            "issues": [_text(item, 500) for item in check.issues[:32]],
            "warnings": [_text(item, 500) for item in check.warnings[:32]],
            "explanation": (
                "Embedded supervised-learning provenance passed its deterministic hash and contract checks."
                if check.verified else
                "Embedded provenance did not pass every deterministic contract and hash check."
            ),
        }

    @staticmethod
    def _item(collection: str, store: str, raw: dict, source: dict) -> dict:
        state = raw.get("status", "active")
        active, focused, priority = False, False, ""
        if collection == "memory":
            enabled = raw.get("active", True)
            state = "active" if enabled is True else "superseded" if enabled is False and raw.get("superseded_by") else "inactive" if enabled is False else "unknown"
            active = state == "active"
            title, preview = _preview(raw["content"], 110), _preview(raw["content"])
            subtype = _text(raw.get("type"), 80) or "unknown"
        elif collection == "goals":
            state = state if isinstance(state, str) and state in VALID_GOAL_STATUSES else "unknown"
            active, focused = state in {"active", "paused"}, raw.get("focus") is True
            priority = raw.get("priority", "normal")
            priority = priority if isinstance(priority, str) and priority in VALID_GOAL_PRIORITIES else "unknown"
            title, preview, subtype = _preview(raw["title"], 110), _preview(raw.get("description")), "goal"
        else:
            state = state if isinstance(state, str) and state in VALID_SKILL_STATUSES else "unknown"
            active = state == "active"
            title, preview = _preview(raw["name"], 110), _preview(raw.get("summary"))
            subtype = _text(raw.get("category", "other"), 80) or "unknown"
        tags = raw.get("tags", [])
        tags = [_text(tag, 80) for tag in tags[:24] if isinstance(tag, str)] if isinstance(tags, list) else []
        return {"id": f"{store}:{raw['id']}", "record_id": raw["id"], "store": store,
                "title": title, "preview": preview, "status": state, "current": active,
                "focused": focused, "priority": priority, "subtype": subtype, "tags": tags,
                "created_at": _text(raw.get("created_at", raw.get("timestamp")), 80),
                "updated_at": _text(raw.get("updated_at") or raw.get("created_at") or raw.get("timestamp"), 80),
                "source": _text(raw.get("source"), 120), "store_sha256": source["sha256"]}

    def _snapshot(self, collection: str) -> tuple[list[dict], list[tuple[dict, dict]]]:
        if not isinstance(collection, str) or collection not in SOURCES:
            raise ValueError("Choose memory, goals, or skills. No arbitrary store path is accepted.")
        sources, entries = [], []
        for store, filename in SOURCES[collection]:
            source, records = self._source(collection, store, filename)
            sources.append(source)
            entries.extend((self._item(collection, store, record, source), record) for record in records)
        entries.sort(key=lambda entry: entry[0]["id"])
        entries.sort(key=lambda entry: entry[0]["updated_at"], reverse=True)
        if collection == "goals":
            entries.sort(key=lambda entry: (not entry[0]["focused"], {"high": 0, "normal": 1, "low": 2}.get(entry[0]["priority"], 3)))
        return sources, entries

    @staticmethod
    def _warnings(sources: list[dict], entries: list[tuple[dict, dict]]) -> list[str]:
        warnings = [f"{source['store']}: {source['message']}" for source in sources if source["message"]]
        if any(item["status"] == "unknown" or item["priority"] == "unknown" for item, _ in entries):
            warnings.append("Some state/priority fields are unknown. Unknown states are not classified as current.")
        if sum(item["focused"] for item, _ in entries) > 1:
            warnings.append("Multiple focused goals are stored; this view does not select or repair them.")
        if any(item["focused"] and not item["current"] for item, _ in entries):
            warnings.append("A terminal/unknown goal is still focused. Review /loop doctor manually.")
        return warnings

    def page(self, collection: str, *, query: str = "", filter: str = "current", offset: int = 0) -> dict:
        if not isinstance(query, str) or len(query) > 200 or any(ord(char) == 0 or 0xD800 <= ord(char) <= 0xDFFF for char in query):
            raise ValueError("Search accepts at most 200 text characters.")
        if not isinstance(filter, str) or filter not in {"current", "history", "all"}:
            raise ValueError("Choose current, history, or all records.")
        if type(offset) is not int or not 0 <= offset <= MAX_SOURCE_RECORDS * 2:
            raise ValueError("Invalid library page offset.")
        sources, entries = self._snapshot(collection)
        needle = _normalized(query)
        matches = []
        for item, raw in entries:
            if filter == "current" and not item["current"] or filter == "history" and item["current"]:
                continue
            if needle:
                fields = (raw.get(key) for key in ("id", "content", "title", "name", "summary", "body", "description", "type", "category", "source"))
                if not any(needle in _normalized(value) for value in fields if isinstance(value, str)) and not any(needle in _normalized(tag) for tag in item["tags"]):
                    continue
            matches.append(item)
        offset = min(offset, (len(matches) - 1) // PAGE_SIZE * PAGE_SIZE) if matches else 0
        return {"schema": "proto_mind.native_library.page.v1", "read_only": True,
                "collection": collection, "query": query, "filter": filter, "offset": offset,
                "limit": PAGE_SIZE, "total_records": sum(source["record_count"] for source in sources),
                "current_records": sum(item["current"] for item, _ in entries),
                "matching_records": len(matches), "omitted_records": sum(source["skipped_count"] for source in sources),
                "items": matches[offset:offset + PAGE_SIZE], "sources": sources,
                "warnings": self._warnings(sources, entries)}

    def _skill_evidence(self, raw: dict) -> dict:
        records, error, exists = None, "", True
        try:
            from proto_mind.experience_learning_apply import _raw_memory_records

            payload, _ = self._read_bytes("persistent_memory.json")
            rows = _raw_memory_records(payload)
            if len(rows) > MAX_SOURCE_RECORDS:
                raise ValueError("Source memory exceeds the bounded provenance inspection limit.")
            records = [MemoryRecord.from_dict(row) for row in rows]
        except FileNotFoundError:
            exists = False
        except (OSError, ValueError, TypeError, KeyError, RecursionError) as exc:
            error = f"{type(exc).__name__}: {exc}"
        try:
            evidence = asdict(verify_procedural_skill_provenance(raw, memory_records=records,
                                                               memory_error=error, memory_exists=exists))
        except (ValueError, TypeError, KeyError, RecursionError):
            evidence = {"status": "ERROR", "skill_id": _text(raw.get("id")), "provenance_id": "",
                        "source_lesson_id": "", "source_status": "invalid", "current_payload_matches": False,
                        "verified": False, "issues": ["Malformed skill provenance cannot be verified."], "warnings": []}
        return {"schema": "proto_mind.native_skill_evidence.v1", "read_only": True, "no_execution": True,
                "store_mutation_performed": False, **evidence}

    def inspect(self, collection: str, record_key: str, *, expected_sha256: str = "") -> dict:
        if not isinstance(record_key, str) or not record_key or len(record_key) > 220 or any(ord(char) < 32 or 0xD800 <= ord(char) <= 0xDFFF for char in record_key):
            raise ValueError("Choose a record from the library list.")
        if not isinstance(expected_sha256, str) or expected_sha256 and (len(expected_sha256) != 64 or any(char not in "0123456789abcdef" for char in expected_sha256)):
            raise ValueError("Invalid source fingerprint.")
        sources, entries = self._snapshot(collection)
        result = {"schema": "proto_mind.native_library.detail.v1", "read_only": True,
                  "collection": collection, "item": None, "blocks": [], "fields": [],
                  "memory_evidence": None,
                  "skill_evidence": None,
                  "sources": sources, "warnings": self._warnings(sources, entries),
                  "changed_since_list": False, "message": "Record unavailable, removed, or ambiguous. Refresh the list; no repair attempted."}
        found = next(((item, raw) for item, raw in entries if item["id"] == record_key), None)
        if found is None:
            return result
        item, raw = found
        result.update(item=item, message="", changed_since_list=bool(expected_sha256 and expected_sha256 != item["store_sha256"]))
        if collection == "memory":
            result["memory_evidence"] = self._memory_evidence(item["store"], raw)
        elif collection == "skills":
            result["skill_evidence"] = self._skill_evidence(raw)
        if result["changed_since_list"]:
            result["warnings"].append("Store changed since the list was loaded. Details show the freshly read record.")
        blocks = {"memory": ("content",), "goals": ("title", "description"), "skills": ("name", "summary", "body")}[collection]
        for key in blocks:
            value = raw.get(key, "")
            if not isinstance(value, str):
                result["warnings"].append(f"{key}: unexpected field type; raw data was not rendered.")
                continue
            rendered = _text(value, MAX_DETAIL_CHARS)
            if rendered != value[:MAX_DETAIL_CHARS]:
                result["warnings"].append(f"{key}: unsupported control/Unicode characters were sanitized for display; the source is unchanged.")
            result["blocks"].append({"key": key, "text": rendered, "truncated": len(value) > MAX_DETAIL_CHARS})
        fields = ("id", "source", "type", "category", "importance", "confidence", "weight", "timestamp", "created_at", "updated_at",
                  "last_used", "usage_count", "last_used_at", "uses", "superseded_by", "superseded_at", "superseded_reason",
                  "source_lesson_id", "source_provenance_id", "source_record_hash", "executable")
        result["fields"] = [{"key": key, "value": _scalar(raw[key])} for key in fields if key in raw and raw[key] is not None]
        for key in ("provenance", "lifecycle"):
            if key in raw:
                value = raw[key]
                schema = _text(value.get("schema"), 160) if isinstance(value, dict) else "invalid"
                result["fields"].append({"key": key, "value": schema or "present"})
                if key != "provenance" or collection not in {"memory", "skills"}:
                    result["warnings"].append(f"{key}: stored metadata only; this view does not re-verify provenance or authorize execution.")
        return result
