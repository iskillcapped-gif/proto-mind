from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable
from datetime import UTC, datetime
from json import JSONDecodeError, loads
from uuid import uuid4

from proto_mind.memory_store import MemoryStore
from proto_mind.memory_governance import format_memory_quality_preview, format_memory_write_policy
from proto_mind.models import MemoryRecord, utc_now_iso


LayeredMemory = tuple[str, MemoryRecord]


def format_memory_command(command: str, store: MemoryStore) -> str | None:
    stripped = command.strip()
    normalized = " ".join(stripped.lower().split())
    if normalized == "/memory write-policy":
        return format_memory_write_policy()
    if normalized == "/memory quality-preview":
        return format_memory_quality_preview(store)
    dynamic_output = format_explicit_memory_command(stripped, store)
    if dynamic_output is not None:
        return dynamic_output
    if normalized == "/memory active":
        return format_active_memories(store)
    if normalized == "/memory decisions":
        return format_decision_memories(store)
    if normalized == "/memory preferences":
        return format_preference_memories(store)
    if normalized == "/memory history":
        return format_memory_history(store)
    if normalized == "/memory working":
        return format_layer_memories(store, "working")
    if normalized == "/memory persistent":
        return format_layer_memories(store, "persistent")
    if normalized == "/memory summary":
        return format_memory_summary(store)
    return None


def format_explicit_memory_command(command: str, store: MemoryStore) -> str | None:
    normalized = " ".join(command.strip().split())
    lowered = normalized.lower()
    if lowered == "/memory doctor":
        return format_memory_doctor(store)
    if lowered == "/memory status":
        return format_explicit_memory_status(store)
    if lowered == "/memory list" or lowered == "/memory list --all":
        return format_explicit_memory_list(store, include_all="--all" in lowered.split())
    if lowered.startswith("/memory remember"):
        text = command.strip()[len("/memory remember") :].strip()
        return remember_explicit_memory(store, text)
    if lowered.startswith("/memory inspect"):
        memory_id = normalized[len("/memory inspect") :].strip()
        return inspect_explicit_memory(store, memory_id)
    if lowered.startswith("/memory search"):
        remainder = command.strip()[len("/memory search") :].strip()
        return search_explicit_memories(store, remainder)
    if lowered.startswith("/memory forget"):
        memory_id = normalized[len("/memory forget") :].strip()
        return forget_explicit_memory(store, memory_id)
    return None


def format_explicit_memory_status(store: MemoryStore) -> str:
    loaded = _safe_load_persistent(store)
    if isinstance(loaded, str):
        return loaded
    explicit = _explicit_records(loaded)
    active = [record for record in explicit if _explicit_status(record) == "active"]
    forgotten = [record for record in explicit if _explicit_status(record) == "forgotten"]
    legacy_count = len([record for record in loaded if record.type != "explicit"])
    last_updated = _last_explicit_update(explicit)
    lines = [
        "Memory v2.0 status:",
        f"  persistent_path: {store.persistent_path}",
        f"  working_path: {store.working_path}",
        "  schema: list[MemoryRecord] + explicit type records",
        "  version: explicit-memory-v2.0",
        f"  explicit_active: {len(active)}",
        f"  explicit_forgotten: {len(forgotten)}",
        f"  legacy_records: {legacy_count}",
        f"  last_updated: {last_updated or 'none'}",
    ]
    return "\n".join(lines)


def format_explicit_memory_list(store: MemoryStore, *, include_all: bool = False) -> str:
    loaded = _safe_load_persistent(store)
    if isinstance(loaded, str):
        return loaded
    records = _sorted_explicit_records(_explicit_records(loaded))
    if not include_all:
        records = [record for record in records if _explicit_status(record) == "active"]
    lines = ["Explicit memories:" if not include_all else "Explicit memories (all):"]
    if not records:
        lines.append("  (none)")
        return "\n".join(lines)
    for record in records:
        lines.append(
            f"  - {record.id} [{_explicit_status(record)}] "
            f"{_preview(record.content)} created_at={record.timestamp}"
        )
    return "\n".join(lines)


def remember_explicit_memory(store: MemoryStore, text: str) -> str:
    text = text.strip()
    if not text:
        return "Usage: /memory remember <text>"
    loaded = _safe_load_persistent(store)
    if isinstance(loaded, str):
        return loaded
    now = utc_now_iso()
    record = MemoryRecord(
        content=text,
        type="explicit",
        importance=1.0,
        source="operator",
        tags=[],
        id=_new_explicit_memory_id(now),
        timestamp=now,
        last_used=now,
        usage_count=0,
        weight=1.0,
        active=True,
        confidence=1.0,
        updated_at=now,
    )
    loaded.append(record)
    store.save_persistent_memory(loaded)
    return f"Remembered:\n  {record.id} — {_preview(record.content)}"


def inspect_explicit_memory(store: MemoryStore, memory_id: str) -> str:
    memory_id = memory_id.strip()
    if not memory_id:
        return "Usage: /memory inspect <id>"
    loaded = _safe_load_persistent(store)
    if isinstance(loaded, str):
        return loaded
    record = _find_explicit_record(loaded, memory_id)
    if not record:
        return f"Explicit memory not found: {memory_id}"
    lines = [
        "Explicit memory:",
        f"  id: {record.id}",
        f"  type: {record.type}",
        f"  status: {_explicit_status(record)}",
        f"  text: {record.content}",
        f"  created_at: {record.timestamp}",
        f"  updated_at: {_record_updated_at(record)}",
        f"  source: {record.source}",
        f"  tags: {record.tags}",
        f"  confidence: {_record_confidence(record):.1f}",
    ]
    return "\n".join(lines)


def search_explicit_memories(store: MemoryStore, query: str) -> str:
    include_all = False
    parts = query.split()
    if "--all" in [part.lower() for part in parts]:
        include_all = True
        parts = [part for part in parts if part.lower() != "--all"]
    query_text = " ".join(parts).strip()
    if not query_text:
        return "Usage: /memory search <query> [--all]"
    loaded = _safe_load_persistent(store)
    if isinstance(loaded, str):
        return loaded
    needle = query_text.casefold()
    candidates = _explicit_records(loaded)
    if not include_all:
        candidates = [record for record in candidates if _explicit_status(record) == "active"]
    matches = [
        record
        for record in candidates
        if needle in record.content.casefold()
        or needle in record.id.casefold()
        or any(needle in tag.casefold() for tag in record.tags)
    ]
    lines = [f'Explicit memory search: "{query_text}"']
    if not matches:
        lines.append("No matches found.")
        return "\n".join(lines)
    for record in _sorted_explicit_records(matches):
        lines.append(f"  - {record.id} [{_explicit_status(record)}] {_preview(record.content)}")
    return "\n".join(lines)


def forget_explicit_memory(store: MemoryStore, memory_id: str) -> str:
    memory_id = memory_id.strip()
    if not memory_id:
        return "Usage: /memory forget <id>"
    loaded = _safe_load_persistent(store)
    if isinstance(loaded, str):
        return loaded
    record = _find_explicit_record(loaded, memory_id)
    if not record:
        return f"Explicit memory not found: {memory_id}"
    if _explicit_status(record) == "forgotten":
        return f"Already forgotten:\n  {record.id} — {_preview(record.content)}"
    now = utc_now_iso()
    record.active = False
    record.updated_at = now
    record.last_used = now
    record.superseded_at = now
    record.superseded_reason = "Forgotten by operator."
    store.save_persistent_memory(loaded)
    return f"Forgotten:\n  {record.id} — {_preview(record.content)}"


def format_memory_doctor(store: MemoryStore) -> str:
    path = store.persistent_path
    findings: list[tuple[str, str, list[str]]] = []
    recommendations: list[str] = []
    raw_items: list[object] = []
    records: list[MemoryRecord] = []
    fatal = False

    if not path.exists():
        findings.append(("WARN", "Persistent memory file is missing.", [f"path: {path}"]))
        recommendations.append("Let MemoryStore initialize the file, or restore it from a backup.")
        return _format_memory_doctor_report("WARN", store, [], [], findings, recommendations, malformed_count=0)

    try:
        raw_text = path.read_text(encoding="utf-8")
    except OSError as exc:
        findings.append(("ERROR", "Persistent memory file is not readable.", [str(exc)]))
        recommendations.append("Check filesystem permissions or restore from a backup.")
        return _format_memory_doctor_report("ERROR", store, [], [], findings, recommendations, malformed_count=0)

    if not raw_text.strip():
        findings.append(("WARN", "Persistent memory file is empty.", [f"path: {path}"]))
        recommendations.append("Restore from backup if this was unexpected.")
        return _format_memory_doctor_report("WARN", store, [], [], findings, recommendations, malformed_count=0)

    try:
        raw_payload = loads(raw_text)
    except JSONDecodeError as exc:
        findings.append(("ERROR", "Persistent memory file contains invalid JSON.", [str(exc)]))
        recommendations.append("Restore from backup or manually repair the JSON file.")
        return _format_memory_doctor_report("ERROR", store, [], [], findings, recommendations, malformed_count=0)

    if not isinstance(raw_payload, list):
        findings.append(("ERROR", "Persistent memory JSON root is not a list.", [f"root_type: {type(raw_payload).__name__}"]))
        recommendations.append("Restore from backup or convert the file back to the list-based MemoryRecord format.")
        return _format_memory_doctor_report("ERROR", store, [], [], findings, recommendations, malformed_count=0)

    raw_items = raw_payload
    malformed_count = _append_record_shape_findings(raw_items, findings)

    try:
        records = store.load_persistent_memory()
    except (JSONDecodeError, TypeError, ValueError) as exc:
        fatal = True
        findings.append(("ERROR", "Persistent memory cannot be parsed through MemoryStore.", [str(exc)]))
        recommendations.append("Repair malformed records or restore persistent memory from backup.")

    if records:
        _append_explicit_memory_findings(records, findings, recommendations)

    if not findings:
        findings.append(("OK", "Persistent memory is readable and no notable explicit-memory issues were detected.", []))
        recommendations.append("No action needed.")
    else:
        if not recommendations:
            recommendations.append("Review findings before adding more explicit memories.")
        if any(severity == "WARN" for severity, _, _ in findings):
            recommendations.append("Use /memory inspect <id> for specific records before deciding whether to forget or rewrite them.")

    status = "ERROR" if fatal or any(severity == "ERROR" for severity, _, _ in findings) else "WARN" if any(severity == "WARN" for severity, _, _ in findings) else "OK"
    return _format_memory_doctor_report(status, store, raw_items, records, findings, recommendations, malformed_count=malformed_count)


def load_layered_memories(store: MemoryStore) -> list[LayeredMemory]:
    return [
        *[("working", record) for record in store.load_working_memory()],
        *[("persistent", record) for record in store.load_persistent_memory()],
    ]


def format_memory_summary(store: MemoryStore) -> str:
    layered = load_layered_memories(store)
    records = [record for _, record in layered]
    type_counts = Counter(record.type for record in records)
    active_count = sum(1 for record in records if record.active)
    superseded_count = sum(1 for record in records if not record.active)
    lines = [
        "Memory summary:",
        f"  working: {len(store.load_working_memory())}",
        f"  persistent: {len(store.load_persistent_memory())}",
        f"  active: {active_count}",
        f"  superseded: {superseded_count}",
        f"  preferences: {type_counts.get('preference', 0)}",
        f"  decisions: {type_counts.get('decision', 0)}",
        f"  projects: {type_counts.get('project', 0)}",
        f"  insights: {type_counts.get('insight', 0)}",
    ]
    other_count = sum(count for memory_type, count in type_counts.items() if memory_type not in {"preference", "decision", "project", "insight"})
    if other_count:
        lines.append(f"  other: {other_count}")
    return "\n".join(lines)


def format_active_memories(store: MemoryStore) -> str:
    grouped: dict[str, list[LayeredMemory]] = defaultdict(list)
    for layer, record in load_layered_memories(store):
        if record.active:
            grouped[record.type].append((layer, record))

    lines = ["Active memories:"]
    if not grouped:
        lines.append("  (none)")
        return "\n".join(lines)

    for memory_type in sorted(grouped):
        lines.append(f"{memory_type}:")
        lines.extend(_format_records(grouped[memory_type], include_layer=True))
    return "\n".join(lines)


def format_decision_memories(store: MemoryStore) -> str:
    decisions = [(layer, record) for layer, record in load_layered_memories(store) if record.type == "decision"]
    active = [(layer, record) for layer, record in decisions if record.active]
    historical = [(layer, record) for layer, record in decisions if not record.active]
    lines = ["Decision memories:", "Active decisions:"]
    lines.extend(_format_records(active, include_layer=True))
    lines.append("Superseded/historical decisions:")
    lines.extend(_format_records(historical, include_layer=True, include_superseded_details=True))
    return "\n".join(lines)


def format_preference_memories(store: MemoryStore) -> str:
    preferences = [
        (layer, record)
        for layer, record in load_layered_memories(store)
        if record.type == "preference" and record.active
    ]
    lines = ["Active preference memories:"]
    lines.extend(_format_records(preferences, include_layer=True))
    return "\n".join(lines)


def format_memory_history(store: MemoryStore) -> str:
    historical = [(layer, record) for layer, record in load_layered_memories(store) if not record.active]
    historical.sort(key=lambda item: (item[1].type != "decision", item[1].timestamp))
    lines = ["Superseded/inactive memory history:"]
    lines.extend(_format_records(historical, include_layer=True, include_superseded_details=True))
    return "\n".join(lines)


def format_layer_memories(store: MemoryStore, layer: str) -> str:
    if layer == "working":
        records = [("working", record) for record in store.load_working_memory()]
        title = "Working memory:"
    elif layer == "persistent":
        records = [("persistent", record) for record in store.load_persistent_memory()]
        title = "Persistent memory:"
    else:
        raise ValueError(f"Unknown memory layer: {layer}")

    lines = [title]
    lines.extend(_format_records(records, include_layer=False, include_superseded_details=True))
    return "\n".join(lines)


def _format_records(
    records: Iterable[LayeredMemory],
    *,
    include_layer: bool,
    include_superseded_details: bool = False,
) -> list[str]:
    lines: list[str] = []
    sorted_records = sorted(records, key=lambda item: (item[1].type, not item[1].active, item[1].timestamp))
    for layer, record in sorted_records:
        lines.append(_format_record(layer, record, include_layer=include_layer))
        if include_superseded_details and not record.active:
            detail = _format_superseded_detail(record)
            if detail:
                lines.append(detail)
    if not lines:
        return ["  (none)"]
    return lines


def _format_record(layer: str, record: MemoryRecord, *, include_layer: bool) -> str:
    layer_text = f" [{layer}]" if include_layer else ""
    return (
        f"  - {_short_id(record.id)}{layer_text} {record.type} {_record_state(record)} "
        f"importance={record.importance:.2f} usage={record.usage_count} :: {_preview(record.content)}"
    )


def _format_superseded_detail(record: MemoryRecord) -> str:
    details: list[str] = []
    if record.superseded_by:
        details.append(f"superseded_by={_short_id(record.superseded_by)}")
    if record.superseded_at:
        details.append(f"superseded_at={record.superseded_at}")
    if record.superseded_reason:
        details.append(f"reason={record.superseded_reason}")
    if not details:
        return ""
    return "    " + "; ".join(details)


def _record_state(record: MemoryRecord) -> str:
    if record.active:
        return "active"
    if record.superseded_by:
        return "superseded"
    return "inactive"


def _short_id(record_id: str | None) -> str:
    if not record_id:
        return "-"
    return record_id[:8]


def _preview(content: str, limit: int = 96) -> str:
    normalized = " ".join(content.split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 3] + "..."


def _safe_load_persistent(store: MemoryStore) -> list[MemoryRecord] | str:
    try:
        return store.load_persistent_memory()
    except (JSONDecodeError, TypeError, ValueError) as exc:
        return f"Memory control error: could not read persistent memory: {exc}"


def _format_memory_doctor_report(
    status: str,
    store: MemoryStore,
    raw_items: list[object],
    records: list[MemoryRecord],
    findings: list[tuple[str, str, list[str]]],
    recommendations: list[str],
    *,
    malformed_count: int,
) -> str:
    explicit = _explicit_records(records)
    active_explicit = [record for record in explicit if record.active]
    forgotten_explicit = [record for record in explicit if not record.active]
    legacy_count = len([record for record in records if record.type != "explicit"])
    lines = [
        "Memory Doctor",
        f"Status: {status}",
        "",
        "Summary:",
        f"  memory file: {store.persistent_path}",
        f"  total raw records: {len(raw_items)}",
        f"  parsed records: {len(records)}",
        f"  explicit active: {len(active_explicit)}",
        f"  explicit forgotten: {len(forgotten_explicit)}",
        f"  explicit total: {len(explicit)}",
        f"  legacy/other records: {legacy_count}",
        f"  malformed raw records: {malformed_count}",
        "",
        "Findings:",
    ]
    for index, (severity, title, evidence) in enumerate(findings, start=1):
        lines.append(f"{index}. [{severity}] {title}")
        for item in evidence[:8]:
            lines.append(f"   - {item}")
    lines.extend(["", "Recommendations:"])
    for recommendation in _unique_lines(recommendations):
        lines.append(f"  - {recommendation}")
    return "\n".join(lines)


def _append_record_shape_findings(raw_items: list[object], findings: list[tuple[str, str, list[str]]]) -> int:
    malformed: list[str] = []
    unknown_types: list[str] = []
    empty_content: list[str] = []
    invalid_confidence: list[str] = []
    missing_explicit_updated_at: list[str] = []
    known_types = {"decision", "preference", "project", "insight", "explicit"}
    for index, item in enumerate(raw_items):
        label = f"record[{index}]"
        if not isinstance(item, dict):
            malformed.append(f"{label}: not an object")
            continue
        record_id = str(item.get("id") or label)
        if not item.get("id"):
            malformed.append(f"{record_id}: missing id")
        content = item.get("content")
        if content is None:
            malformed.append(f"{record_id}: missing content")
        elif not str(content).strip():
            empty_content.append(f"{record_id}: empty content")
        memory_type = item.get("type")
        if not memory_type:
            malformed.append(f"{record_id}: missing type")
        elif str(memory_type) not in known_types:
            unknown_types.append(f"{record_id}: unknown type={memory_type}")
        if str(memory_type) == "explicit" and not item.get("updated_at"):
            missing_explicit_updated_at.append(f"{record_id}: missing updated_at")
        if "confidence" in item and item.get("confidence") is not None:
            try:
                confidence = float(item["confidence"])
                if confidence < 0 or confidence > 1:
                    invalid_confidence.append(f"{record_id}: confidence={item['confidence']}")
            except (TypeError, ValueError):
                invalid_confidence.append(f"{record_id}: confidence={item.get('confidence')}")
    if malformed:
        findings.append(("WARN", "Malformed raw memory records found.", malformed))
    if unknown_types:
        findings.append(("WARN", "Unknown memory types found.", unknown_types))
    if empty_content:
        findings.append(("WARN", "Empty memory content found.", empty_content))
    if invalid_confidence:
        findings.append(("WARN", "Invalid confidence values found.", invalid_confidence))
    if missing_explicit_updated_at:
        findings.append(("WARN", "Explicit memories missing updated_at found.", missing_explicit_updated_at))
    return len(malformed)


def _append_explicit_memory_findings(
    records: list[MemoryRecord],
    findings: list[tuple[str, str, list[str]]],
    recommendations: list[str],
) -> None:
    explicit = _explicit_records(records)
    active = [record for record in explicit if record.active]
    forgotten = [record for record in explicit if not record.active]
    duplicate_groups = _active_explicit_duplicate_groups(active)
    if duplicate_groups:
        evidence = [
            f"{', '.join(record.id for record in group)} :: {_preview(group[0].content)}"
            for group in duplicate_groups
        ]
        findings.append(("WARN", "Duplicate active explicit memories detected.", evidence))
        recommendations.append("Consider /memory forget <id> for duplicate active explicit memories after inspection.")
    near_duplicates = _active_explicit_near_duplicates(active)
    if near_duplicates:
        findings.append(("WARN", "Possible near-duplicate active explicit memories detected.", near_duplicates))
        recommendations.append("Review near duplicates manually; this is a heuristic, not a semantic proof.")
    long_records = [
        f"{record.id}: len={len(record.content)} :: {_preview(record.content)}"
        for record in active
        if len(record.content) > 500
    ]
    if long_records:
        findings.append(("WARN", "Long active explicit memories detected.", long_records))
        recommendations.append("Split or summarize long explicit memories into smaller facts.")
    low_info = [
        f"{record.id}: {_preview(record.content)}"
        for record in active
        if _is_low_information(record.content)
    ]
    if low_info:
        findings.append(("WARN", "Possible low-information active explicit memories detected.", low_info))
    if forgotten and len(forgotten) > len(active) and len(forgotten) > 10:
        findings.append(("WARN", "Forgotten explicit memory count is high.", [f"forgotten={len(forgotten)} active={len(active)}"]))
        recommendations.append("A future hard-prune/archive command may be useful; no hard delete is performed by doctor.")
    conflicts = _possible_explicit_conflicts(active)
    if conflicts:
        findings.append(("WARN", "Possible conflicting active explicit memories detected.", conflicts))
        recommendations.append("Inspect possible conflicts and forget or rewrite one side if appropriate.")


def _active_explicit_duplicate_groups(records: list[MemoryRecord]) -> list[list[MemoryRecord]]:
    groups: dict[str, list[MemoryRecord]] = defaultdict(list)
    for record in records:
        normalized = _normalize_memory_text(record.content)
        if normalized:
            groups[normalized].append(record)
    return [group for group in groups.values() if len(group) > 1]


def _active_explicit_near_duplicates(records: list[MemoryRecord]) -> list[str]:
    evidence: list[str] = []
    for left_index, left in enumerate(records):
        left_tokens = _meaningful_tokens(left.content)
        if len(left_tokens) < 4:
            continue
        for right in records[left_index + 1 :]:
            right_tokens = _meaningful_tokens(right.content)
            if len(right_tokens) < 4:
                continue
            score = len(left_tokens & right_tokens) / len(left_tokens | right_tokens)
            if score >= 0.85 and _normalize_memory_text(left.content) != _normalize_memory_text(right.content):
                evidence.append(f"{left.id} ~ {right.id} overlap={score:.2f}")
    return evidence


def _possible_explicit_conflicts(records: list[MemoryRecord]) -> list[str]:
    positives: dict[str, list[MemoryRecord]] = defaultdict(list)
    negatives: dict[str, list[MemoryRecord]] = defaultdict(list)
    for record in records:
        normalized = _normalize_memory_text(record.content)
        for positive_prefix, negative_prefix in [
            ("user likes ", "user does not like "),
            ("user prefers ", "user does not prefer "),
            ("user wants ", "user does not want "),
            ("user is ", "user is not "),
        ]:
            if normalized.startswith(negative_prefix):
                negatives[negative_prefix + normalized.removeprefix(negative_prefix)].append(record)
            elif normalized.startswith(positive_prefix):
                negatives_key = negative_prefix + normalized.removeprefix(positive_prefix)
                positives[negatives_key].append(record)
    evidence: list[str] = []
    for key, positive_records in positives.items():
        negative_records = negatives.get(key, [])
        for positive in positive_records:
            for negative in negative_records:
                evidence.append(f"{positive.id} conflicts-with {negative.id} :: {_preview(positive.content)} / {_preview(negative.content)}")
    return evidence


def _normalize_memory_text(text: str) -> str:
    chars = [char.casefold() if char.isalnum() else " " for char in text]
    return " ".join("".join(chars).split())


def _meaningful_tokens(text: str) -> set[str]:
    stopwords = {"a", "an", "and", "the", "to", "of", "in", "is", "are", "user"}
    return {token for token in _normalize_memory_text(text).split() if len(token) > 2 and token not in stopwords}


def _is_low_information(text: str) -> bool:
    tokens = _meaningful_tokens(text)
    return len(text.strip()) < 5 or len(tokens) < 2


def _unique_lines(lines: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for line in lines:
        if line not in seen:
            seen.add(line)
            unique.append(line)
    return unique


def _explicit_records(records: Iterable[MemoryRecord]) -> list[MemoryRecord]:
    return [record for record in records if record.type == "explicit"]


def _sorted_explicit_records(records: Iterable[MemoryRecord]) -> list[MemoryRecord]:
    return sorted(records, key=lambda record: _record_updated_at(record), reverse=True)


def _find_explicit_record(records: Iterable[MemoryRecord], memory_id: str) -> MemoryRecord | None:
    for record in records:
        if record.type == "explicit" and record.id == memory_id:
            return record
    return None


def _explicit_status(record: MemoryRecord) -> str:
    return "active" if record.active else "forgotten"


def _record_confidence(record: MemoryRecord) -> float:
    if record.confidence is not None:
        return float(record.confidence)
    return float(record.weight)


def _record_updated_at(record: MemoryRecord) -> str:
    return record.updated_at or record.last_used or record.superseded_at or record.timestamp


def _last_explicit_update(records: Iterable[MemoryRecord]) -> str | None:
    updates = [_record_updated_at(record) for record in records]
    return max(updates) if updates else None


def _new_explicit_memory_id(created_at: str) -> str:
    try:
        parsed = datetime.fromisoformat(created_at)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        stamp = parsed.astimezone(UTC).strftime("%Y%m%d_%H%M%S")
    except ValueError:
        stamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    return f"mem_{stamp}_{uuid4().hex[:4]}"
