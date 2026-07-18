from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from proto_mind.memory_store import MemoryStore
from proto_mind.models import MemoryRecord


LONG_CONTENT_THRESHOLD = 1000


@dataclass(frozen=True)
class MemoryQualityFinding:
    layer: str
    record_id: str
    memory_type: str
    content_chars: int
    flags: tuple[str, ...]
    preview: str


def memory_write_policy() -> dict[str, object]:
    return {
        "version": "memory-write-governance-v1",
        "retrieval_store_mutation": False,
        "usage_telemetry": "explicit_api_only",
        "automatic_content_source": "user_input_only",
        "full_response_storage": False,
        "migration_mode": "preview_only",
        "auto_cleanup": False,
    }


def inspect_memory_quality(store: MemoryStore) -> dict[str, object]:
    try:
        layers = {
            "working": store.load_working_memory(),
            "persistent": store.load_persistent_memory(),
        }
    except (OSError, TypeError, ValueError) as exc:
        return {
            "status": "ERROR",
            "error": f"{type(exc).__name__}: {exc}",
            "working_count": 0,
            "persistent_count": 0,
            "findings": [],
            "category_counts": {},
        }

    findings: list[MemoryQualityFinding] = []
    for layer, records in layers.items():
        for record in records:
            flags = _quality_flags(record)
            if not flags:
                continue
            findings.append(
                MemoryQualityFinding(
                    layer=layer,
                    record_id=record.id,
                    memory_type=record.type,
                    content_chars=len(record.content),
                    flags=tuple(flags),
                    preview=_preview(record.content),
                )
            )

    counts = Counter(flag for finding in findings for flag in finding.flags)
    return {
        "status": "WARN" if findings else "OK",
        "error": "",
        "working_count": len(layers["working"]),
        "persistent_count": len(layers["persistent"]),
        "findings": findings,
        "category_counts": dict(sorted(counts.items())),
    }


def format_memory_write_policy() -> str:
    policy = memory_write_policy()
    return "\n".join(
        [
            "Memory Write Governance Policy",
            "Status: OK",
            f"version: {policy['version']}",
            f"retrieval_store_mutation: {str(policy['retrieval_store_mutation']).lower()}",
            f"usage_telemetry: {policy['usage_telemetry']}",
            f"automatic_content_source: {policy['automatic_content_source']}",
            f"full_response_storage: {str(policy['full_response_storage']).lower()}",
            f"migration_mode: {policy['migration_mode']}",
            f"auto_cleanup: {str(policy['auto_cleanup']).lower()}",
            "",
            "Boundary:",
            "- Retrieval is read-only by default. Usage telemetry requires an explicit internal API call.",
            "- New automatic records store compact user input, never the generated response.",
            "- Existing records are not rewritten, archived, deleted, or migrated by this policy command.",
        ]
    )


def format_memory_quality_preview(store: MemoryStore) -> str:
    report = inspect_memory_quality(store)
    lines = [
        "Memory Quality Migration Preview",
        f"Status: {report['status']}",
        f"working_records: {report['working_count']}",
        f"persistent_records: {report['persistent_count']}",
        f"migration_candidates: {len(report['findings'])}",
    ]
    if report["error"]:
        lines.extend([f"error: {report['error']}", "mutation_performed: false"])
        return "\n".join(lines)

    lines.extend(["", "Category counts:"])
    if report["category_counts"]:
        lines.extend(f"- {name}: {count}" for name, count in report["category_counts"].items())
    else:
        lines.append("- none")

    lines.extend(["", "Candidates:"])
    if not report["findings"]:
        lines.append("- none; current records do not match deterministic migration-preview rules")
    for finding in report["findings"]:
        lines.extend(
            [
                f"- {finding.record_id} [{finding.layer}/{finding.memory_type}] chars={finding.content_chars}",
                f"  flags: {', '.join(finding.flags)}",
                f"  preview: {finding.preview}",
                "  suggestion: inspect manually; plan a separate checkpointed migration if this record should be compacted or archived",
            ]
        )
    lines.extend(
        [
            "",
            "Mutation policy:",
            "- mutation_performed: false",
            "- Preview only. No memory record, usage counter, timestamp, active flag, file, or schema was changed.",
        ]
    )
    return "\n".join(lines)


def _quality_flags(record: MemoryRecord) -> list[str]:
    content = record.content.strip()
    lowered = content.casefold()
    flags: list[str] = []
    user_markers = lowered.count("user input:")
    response_markers = lowered.count("system response:")
    if user_markers or response_markers:
        flags.append("response_coupled")
    if user_markers > 1 or response_markers > 1:
        flags.append("recursive_context")
    if len(content) > LONG_CONTENT_THRESHOLD:
        flags.append("long_content")
    if not content:
        flags.append("empty_content")
    return flags


def _preview(text: str, limit: int = 180) -> str:
    compact = " ".join(text.split())
    return compact if len(compact) <= limit else compact[: limit - 3] + "..."
