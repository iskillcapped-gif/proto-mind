from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Any

from proto_mind.command_registry import COMMAND_REGISTRY
from proto_mind.memory_store import MemoryStore
from proto_mind.skill_library import SkillLibrary
from proto_mind.skill_lifecycle_metadata import (
    PROCEDURAL_SKILL_LIFECYCLE_METADATA_SCHEMA,
    PROCEDURAL_SKILL_LIFECYCLE_METADATA_WRITER_INSTALLED,
    format_procedural_skill_lifecycle_metadata_contract,
    is_procedural_skill_lifecycle_metadata_design,
    procedural_skill_lifecycle_metadata_doctor,
    verify_procedural_skill_lifecycle_metadata,
)
from proto_mind.skill_provenance import verify_procedural_skill_provenance


PROCEDURAL_SKILL_LIFECYCLE_AUDIT_VERSION = 1
PROCEDURAL_SKILL_LIFECYCLE_AUDIT_MODE = (
    "read_only_durable_skill_state_without_invented_lifecycle_history"
)
PROCEDURAL_SKILL_LIFECYCLE_STATES = frozenset(
    {
        "active_verified",
        "active_historical",
        "archived_verified",
        "archived_ambiguous",
        "drifted",
        "legacy_unprovenanced",
        "unprovenanced",
        "invalid",
    }
)


@dataclass(frozen=True)
class ProceduralSkillLifecycleAuditEntry:
    skill_id: str
    state: str
    status: str
    name_preview: str
    source: str
    provenance_status: str
    provenance_id: str
    source_lesson_id: str
    source_status: str
    applied_at: str
    lifecycle_evidence: str
    lifecycle_reason: str
    outcome_archive_proven: bool
    restart_safe: bool
    executable: bool
    issues: list[str]
    warnings: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ProceduralSkillLifecycleAuditReport:
    status: str
    skills_path: str
    persistent_memory_path: str
    total_skills: int
    supervised_count: int
    active_verified_count: int
    active_historical_count: int
    archived_verified_count: int
    archived_ambiguous_count: int
    drifted_count: int
    legacy_unprovenanced_count: int
    unprovenanced_count: int
    invalid_count: int
    entries: list[ProceduralSkillLifecycleAuditEntry]
    issues: list[str]
    warnings: list[str]
    mutation_performed: bool = False
    lifecycle_history_invented: bool = False


class ProceduralSkillLifecycleAuditError(RuntimeError):
    pass


class ProceduralSkillLifecycleAudit:
    """Classifies only lifecycle facts that survive in current durable stores."""

    def __init__(self, *, skills_path: Path, persistent_memory_path: Path) -> None:
        self.skills_path = Path(skills_path)
        self.persistent_memory_path = Path(persistent_memory_path)

    def inspect(self) -> ProceduralSkillLifecycleAuditReport:
        library = SkillLibrary(self.skills_path)
        snapshot = library.read_snapshot()
        if snapshot["error"]:
            raise ProceduralSkillLifecycleAuditError(
                f"Skill Library is unreadable: {snapshot['error']}"
            )
        if snapshot["malformed_count"]:
            raise ProceduralSkillLifecycleAuditError(
                "Skill Library contains "
                f"{snapshot['malformed_count']} malformed JSONL record(s)."
            )
        records = snapshot["records"]
        memories, memory_exists, memory_error = self._load_memories()
        identifiers = [str(record.get("id") or "") for record in records]
        duplicate_ids = sorted(
            identifier
            for identifier, count in Counter(identifiers).items()
            if identifier and count > 1
        )
        issues = ["Skill record is missing an id."] if any(not value for value in identifiers) else []
        issues.extend(f"Duplicate skill id: {identifier}." for identifier in duplicate_ids)
        entries = [
            self._entry(
                record,
                memories=memories,
                memory_exists=memory_exists,
                memory_error=memory_error,
            )
            for record in records
        ]
        warnings: list[str] = []
        for entry in entries:
            issues.extend(f"{entry.skill_id or '<missing>'}: {item}" for item in entry.issues)
            warnings.extend(
                f"{entry.skill_id or '<missing>'}: {item}" for item in entry.warnings
            )
        counts = Counter(entry.state for entry in entries)
        supervised = sum(
            entry.source == "experience_learning_skill_apply"
            or bool(entry.provenance_id)
            for entry in entries
        )
        status = "ERROR" if issues else "WARN" if warnings else "OK"
        return ProceduralSkillLifecycleAuditReport(
            status=status,
            skills_path=str(self.skills_path),
            persistent_memory_path=str(self.persistent_memory_path),
            total_skills=len(entries),
            supervised_count=supervised,
            active_verified_count=counts["active_verified"],
            active_historical_count=counts["active_historical"],
            archived_verified_count=counts["archived_verified"],
            archived_ambiguous_count=counts["archived_ambiguous"],
            drifted_count=counts["drifted"],
            legacy_unprovenanced_count=counts["legacy_unprovenanced"],
            unprovenanced_count=counts["unprovenanced"],
            invalid_count=counts["invalid"],
            entries=entries,
            issues=_dedupe(issues),
            warnings=_dedupe(warnings),
        )

    def get(self, skill_id: str) -> ProceduralSkillLifecycleAuditEntry | None:
        return next(
            (entry for entry in self.inspect().entries if entry.skill_id == skill_id),
            None,
        )

    def _load_memories(self) -> tuple[list[Any], bool, str]:
        if not self.persistent_memory_path.exists():
            return [], False, ""
        store = MemoryStore(
            working_path=self.persistent_memory_path.parent / "working_memory.json",
            persistent_path=self.persistent_memory_path,
        )
        try:
            return store.load_persistent_memory(), True, ""
        except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
            return [], True, str(exc)

    def _entry(
        self,
        record: dict[str, Any],
        *,
        memories: list[Any],
        memory_exists: bool,
        memory_error: str,
    ) -> ProceduralSkillLifecycleAuditEntry:
        skill_id = str(record.get("id") or "")
        source = str(record.get("source") or "")
        stored_status = str(record.get("status") or "")
        provenance = record.get("provenance")
        provenance_check = verify_procedural_skill_provenance(
            record,
            memory_records=memories,
            memory_exists=memory_exists,
            memory_error=memory_error,
        )
        issues: list[str] = []
        warnings: list[str] = []
        lifecycle_metadata = record.get("lifecycle")
        lifecycle_verified = False
        metadata_reason = ""
        state = "unprovenanced"

        if stored_status not in {"active", "archived"}:
            issues.append("Skill status is not active or archived.")
            state = "invalid"
        if record.get("executable") is True:
            issues.append("Stored procedural skill unexpectedly claims executable capability.")
            state = "invalid"
        if lifecycle_metadata is not None:
            if is_procedural_skill_lifecycle_metadata_design(lifecycle_metadata):
                metadata_check = verify_procedural_skill_lifecycle_metadata(
                    lifecycle_metadata
                )
                if not metadata_check.verified:
                    issues.extend(
                        f"Lifecycle metadata: {item}"
                        for item in metadata_check.issues
                    )
                elif not PROCEDURAL_SKILL_LIFECYCLE_METADATA_WRITER_INSTALLED:
                    issues.append(
                        "Skill contains lifecycle metadata while its supervised writer is unavailable."
                    )
                elif stored_status != "archived":
                    issues.append(
                        "Verified archive lifecycle metadata requires archived skill status."
                    )
                elif metadata_check.skill_id != skill_id:
                    issues.append(
                        "Lifecycle metadata skill_id does not match the skill record."
                    )
                elif not isinstance(provenance, dict) or lifecycle_metadata.get(
                    "skill_provenance_id"
                ) != provenance.get("id"):
                    issues.append(
                        "Lifecycle metadata does not bind the current embedded provenance."
                    )
                else:
                    lifecycle_verified = True
                    metadata_reason = metadata_check.reason
            else:
                issues.append("Skill contains unsupported durable lifecycle metadata.")
            if issues:
                state = "invalid"

        has_provenance = isinstance(provenance, dict)
        if not has_provenance:
            if source == "experience_learning_skill_apply":
                state = "legacy_unprovenanced" if not issues else "invalid"
                warnings.append(
                    "Legacy supervised skill has no durable v3.5e provenance."
                )
            elif not issues:
                state = "unprovenanced"
        elif provenance_check.issues:
            issues.extend(provenance_check.issues)
            state = "invalid"
        elif not provenance_check.current_payload_matches:
            state = "drifted" if not issues else "invalid"
            warnings.extend(
                provenance_check.warnings
                or ["Current skill payload differs from the operator-confirmed projection."]
            )
        elif stored_status == "archived" and lifecycle_verified and not issues:
            state = "archived_verified"
            if provenance_check.status == "HISTORICAL":
                warnings.extend(provenance_check.warnings)
        elif stored_status == "archived" and not issues:
            state = "archived_ambiguous"
            warnings.append(
                "Archive status is durable, but its cause is not; outcome-driven archive is not proven after restart."
            )
        elif provenance_check.status == "VERIFIED" and not issues:
            state = "active_verified"
        elif provenance_check.verified and not issues:
            state = "active_historical"
            warnings.extend(
                provenance_check.warnings
                or ["Skill provenance verifies, but its source lesson is historical or unavailable."]
            )
        elif not issues:
            state = "invalid"
            issues.extend(
                provenance_check.warnings
                or ["Procedural skill provenance cannot be verified."]
            )

        provenance_id = ""
        source_lesson_id = str(record.get("source_lesson_id") or "")
        applied_at = ""
        if isinstance(provenance, dict):
            provenance_id = str(provenance.get("id") or "")
            source_lesson_id = str(
                provenance.get("source_lesson_id") or source_lesson_id
            )
            applied_at = str(provenance.get("applied_at") or "")
        lifecycle_evidence = (
            "verified_operator_outcome_archive"
            if lifecycle_verified
            else "invalid_envelope"
            if is_procedural_skill_lifecycle_metadata_design(lifecycle_metadata)
            else "unsupported_record_field"
            if lifecycle_metadata is not None
            else "none"
        )
        lifecycle_reason = (
            metadata_reason
            if lifecycle_verified
            else "not durably recorded"
            if stored_status == "archived" and lifecycle_metadata is None
            else "none"
        )
        restart_safe = state in {
            "active_verified",
            "active_historical",
            "archived_verified",
        }
        return ProceduralSkillLifecycleAuditEntry(
            skill_id=skill_id,
            state=state,
            status=stored_status or "unknown",
            name_preview=_preview(str(record.get("name") or "")),
            source=source or "unknown",
            provenance_status=provenance_check.status,
            provenance_id=provenance_id,
            source_lesson_id=source_lesson_id,
            source_status=provenance_check.source_status,
            applied_at=applied_at,
            lifecycle_evidence=lifecycle_evidence,
            lifecycle_reason=lifecycle_reason,
            outcome_archive_proven=state == "archived_verified",
            restart_safe=restart_safe,
            executable=record.get("executable") is True,
            issues=_dedupe(issues),
            warnings=_dedupe(warnings),
        )


def format_skill_lifecycle_audit_command(
    command: str,
    *,
    skills_path: Path,
    persistent_memory_path: Path,
) -> str | None:
    raw = command.strip()
    normalized = " ".join(raw.lower().split())
    prefixes = (
        "/skills lifecycle-status",
        "/skills lifecycle-history",
        "/skills lifecycle-inspect",
        "/skills lifecycle-doctor",
    )
    lowered = raw.lower()
    if not any(
        lowered.startswith(prefix)
        and (len(lowered) == len(prefix) or lowered[len(prefix)] in " \t\n;&|")
        for prefix in prefixes
    ):
        return None
    if any(marker in raw for marker in ("\n", ";", "&&", "||", "|")):
        return _audit_error("Command chaining and multi-command input are not allowed.")
    if normalized == "/skills lifecycle-status --contract":
        return format_procedural_skill_lifecycle_metadata_contract()
    audit = ProceduralSkillLifecycleAudit(
        skills_path=skills_path,
        persistent_memory_path=persistent_memory_path,
    )
    try:
        report = audit.inspect()
    except ProceduralSkillLifecycleAuditError as exc:
        return _audit_error(str(exc))

    if normalized == "/skills lifecycle-status":
        return format_skill_lifecycle_status(report)
    if normalized.startswith("/skills lifecycle-status "):
        return "Usage: /skills lifecycle-status [--contract]"
    if normalized == "/skills lifecycle-doctor":
        return format_skill_lifecycle_doctor(report)
    if normalized == "/skills lifecycle-history":
        return format_skill_lifecycle_history(report, include_all=False)
    if normalized == "/skills lifecycle-history --all":
        return format_skill_lifecycle_history(report, include_all=True)
    if normalized.startswith("/skills lifecycle-history "):
        return "Usage: /skills lifecycle-history [--all]"
    if normalized.startswith("/skills lifecycle-inspect"):
        if normalized == "/skills lifecycle-inspect":
            return "Usage: /skills lifecycle-inspect <skill_id>"
        identifier = raw[len("/skills lifecycle-inspect") :].strip()
        if not identifier or " " in identifier:
            return "Usage: /skills lifecycle-inspect <skill_id>"
        entry = next((item for item in report.entries if item.skill_id == identifier), None)
        return format_skill_lifecycle_inspect(entry, identifier=identifier)
    return (
        "Usage: /skills lifecycle-status [--contract] | lifecycle-history [--all] | "
        "lifecycle-inspect <skill_id> | lifecycle-doctor"
    )


def format_skill_lifecycle_status(
    report: ProceduralSkillLifecycleAuditReport,
) -> str:
    return "\n".join(
        [
            "Proto-Mind Procedural Skill Lifecycle Audit Status v1",
            f"Status: {report.status}",
            f"mode: {PROCEDURAL_SKILL_LIFECYCLE_AUDIT_MODE}",
            f"skills_path: {report.skills_path}",
            f"persistent_memory_path: {report.persistent_memory_path}",
            f"total_skills: {report.total_skills}",
            f"supervised: {report.supervised_count}",
            f"active_verified: {report.active_verified_count}",
            f"active_historical: {report.active_historical_count}",
            f"archived_verified: {report.archived_verified_count}",
            f"archived_ambiguous: {report.archived_ambiguous_count}",
            f"drifted: {report.drifted_count}",
            f"legacy_unprovenanced: {report.legacy_unprovenanced_count}",
            f"unprovenanced: {report.unprovenanced_count}",
            f"invalid: {report.invalid_count}",
            f"metadata_schema: {PROCEDURAL_SKILL_LIFECYCLE_METADATA_SCHEMA}",
            f"metadata_writer_installed: {str(PROCEDURAL_SKILL_LIFECYCLE_METADATA_WRITER_INSTALLED).lower()}",
            "Commands: lifecycle-status --contract | lifecycle-history [--all] | lifecycle-inspect <id> | lifecycle-doctor",
            *_audit_boundary(),
        ]
    )


def format_skill_lifecycle_history(
    report: ProceduralSkillLifecycleAuditReport,
    *,
    include_all: bool,
) -> str:
    entries = (
        report.entries
        if include_all
        else [entry for entry in report.entries if entry.state != "unprovenanced"]
    )
    lines = [
        "Proto-Mind Procedural Skill Durable State View v1",
        f"Status: {report.status}",
        f"showing: {len(entries)}/{len(report.entries)}",
        "Skills:",
    ]
    if not entries:
        lines.append("- none")
    for entry in entries:
        lines.append(
            f"- {entry.skill_id} | {entry.state} | status={entry.status} | "
            f"archive_proven={str(entry.outcome_archive_proven).lower()} | {entry.name_preview}"
        )
    lines.extend(
        [
            "- This reconstructs current durable facts; it is not an append-only lifecycle history.",
            *_audit_boundary(),
        ]
    )
    return "\n".join(lines)


def format_skill_lifecycle_inspect(
    entry: ProceduralSkillLifecycleAuditEntry | None,
    *,
    identifier: str,
) -> str:
    if entry is None:
        return _audit_error(f"Skill {identifier!r} was not found.")
    lines = [
        "Proto-Mind Procedural Skill Durable State Inspection v1",
        f"Status: {'ERROR' if entry.issues else 'WARN' if entry.warnings else 'OK'}",
    ]
    lines.extend(f"{key}: {_compact(value)}" for key, value in entry.to_dict().items())
    lines.extend(_audit_boundary())
    return "\n".join(lines)


def format_skill_lifecycle_doctor(
    report: ProceduralSkillLifecycleAuditReport,
) -> str:
    issues = list(report.issues)
    warnings = list(report.warnings)
    metadata_report = procedural_skill_lifecycle_metadata_doctor()
    if metadata_report.status != "OK":
        issues.extend(
            metadata_report.issues
            or ["Procedural skill lifecycle metadata design is unhealthy."]
        )
    registry = {item.prefix: item for item in COMMAND_REGISTRY}
    for prefix in (
        "/skills lifecycle-status",
        "/skills lifecycle-history",
        "/skills lifecycle-inspect",
        "/skills lifecycle-doctor",
    ):
        spec = registry.get(prefix)
        if (
            spec is None
            or not spec.read_only
            or spec.mutates != "none"
            or spec.risk != "low"
        ):
            issues.append(f"Registry metadata for {prefix} is missing or unsafe.")
    status = "ERROR" if issues else "WARN" if warnings else "OK"
    lines = [
        "Proto-Mind Procedural Skill Lifecycle Audit Doctor v1",
        f"Status: {status}",
        f"mode: {PROCEDURAL_SKILL_LIFECYCLE_AUDIT_MODE}",
        f"total_skills: {report.total_skills}",
        f"supervised: {report.supervised_count}",
        f"active_verified: {report.active_verified_count}",
        f"active_historical: {report.active_historical_count}",
        f"archived_verified: {report.archived_verified_count}",
        f"archived_ambiguous: {report.archived_ambiguous_count}",
        f"drifted: {report.drifted_count}",
        f"invalid: {report.invalid_count}",
        f"metadata_contract_status: {metadata_report.status}",
        f"metadata_schema: {metadata_report.schema}",
        f"metadata_writer_installed: {str(metadata_report.writer_installed).lower()}",
        f"metadata_example_verified: {str(metadata_report.deterministic_example_verified).lower()}",
        f"metadata_tamper_refused: {str(metadata_report.tamper_refused).lower()}",
        "lifecycle_history_invented: false",
        "mutation_performed: false",
    ]
    lines.extend(f"- ERROR: {item}" for item in _dedupe(issues))
    lines.extend(f"- WARN: {item}" for item in _dedupe(warnings))
    if not issues and not warnings:
        lines.append(
            "- Durable provenance, current state classification, Registry, and no-invention boundaries are healthy."
        )
    lines.extend(_audit_boundary())
    return "\n".join(lines)


def _preview(value: str, limit: int = 120) -> str:
    compact = " ".join(value.split())
    return compact if len(compact) <= limit else compact[: limit - 3].rstrip() + "..."


def _compact(value: Any) -> str:
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, list):
        return ", ".join(str(item) for item in value) or "none"
    return str(value) if value not in {None, ""} else "none"


def _audit_error(message: str) -> str:
    return "\n".join(
        [
            "Proto-Mind Procedural Skill Lifecycle Audit Error",
            "Status: ERROR",
            f"- {message}",
            *_audit_boundary(),
        ]
    )


def _audit_boundary() -> list[str]:
    return [
        "Boundary:",
        "- Read-only current durable-state reconstruction; no process receipt is treated as restart-safe history.",
        "- Only a verified embedded lifecycle envelope proves outcome-driven archive; legacy archive remains ARCHIVED_AMBIGUOUS.",
        "- No skill, memory, event, receipt, queue, export, session log, Context Injection, shell, model/API, or external action changed.",
    ]


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))
