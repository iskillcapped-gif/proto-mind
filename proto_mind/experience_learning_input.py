from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Iterable

from proto_mind.experience_episode import ExperienceEpisode, ExperienceEpisodeProjector
from proto_mind.experience_learning import ExperienceLearningReviewer
from proto_mind.experience_vocabulary import (
    build_failure_correction_trace,
    build_success_lifecycle_trace,
)
from proto_mind.memory_store import MemoryStore
from proto_mind.models import MemoryRecord
from proto_mind.skill_library import SkillLibrary


LEARNING_INPUT_SELECTION_MODE = "explicit_ids_only"
LEARNING_INPUT_PREVIEW_MAX_CHARS = 120


@dataclass(frozen=True)
class ExperienceLearningInputSnapshot:
    status: str
    selection_mode: str
    requested_memory_ids: list[str]
    requested_skill_ids: list[str]
    memory_records: list[dict[str, Any]]
    skill_records: list[dict[str, Any]]
    missing_memory_ids: list[str]
    missing_skill_ids: list[str]
    excluded_memory_ids: list[str]
    excluded_skill_ids: list[str]
    issues: list[str]
    warnings: list[str]
    retrieval_performed: bool = False
    usage_telemetry_recorded: bool = False
    mutation_performed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ExperienceLearningInputDoctorReport:
    status: str
    selected_memory_count: int
    selected_skill_count: int
    missing_count: int
    excluded_count: int
    issues: list[str]
    warnings: list[str]


@dataclass(frozen=True)
class ExperienceLearningInputBenchmarkReport:
    status: str
    selected_memory_count: int
    selected_skill_count: int
    missing_count: int
    excluded_count: int
    reviewer_duplicate_count: int
    files_unchanged: bool
    checks: dict[str, bool]
    failed_checks: list[str]
    boundary: str


class ExperienceLearningInputError(RuntimeError):
    pass


class ExperienceLearningInputAdapter:
    """Builds detached snapshots from exact IDs without retrieval, telemetry, or writes."""

    def __init__(self, *, memory_store: MemoryStore, skill_library: SkillLibrary) -> None:
        self.memory_store = memory_store
        self.skill_library = skill_library

    def build_snapshot(
        self,
        *,
        memory_ids: Iterable[str] = (),
        skill_ids: Iterable[str] = (),
    ) -> ExperienceLearningInputSnapshot:
        requested_memory_ids, repeated_memory_ids = _unique_ids(memory_ids)
        requested_skill_ids, repeated_skill_ids = _unique_ids(skill_ids)
        issues: list[str] = []
        warnings: list[str] = []
        if repeated_memory_ids:
            warnings.append(
                "Repeated requested memory IDs were deduplicated: "
                + ", ".join(repeated_memory_ids)
                + "."
            )
        if repeated_skill_ids:
            warnings.append(
                "Repeated requested skill IDs were deduplicated: "
                + ", ".join(repeated_skill_ids)
                + "."
            )

        memory_rows: list[tuple[str, MemoryRecord]] = []
        try:
            memory_rows.extend(
                ("working", record) for record in self.memory_store.load_working_memory()
            )
            memory_rows.extend(
                ("persistent", record)
                for record in self.memory_store.load_persistent_memory()
            )
        except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
            issues.append(f"Memory snapshot is unreadable: {type(exc).__name__}: {exc}.")

        skill_snapshot = self.skill_library.read_snapshot()
        if skill_snapshot.get("error"):
            issues.append(f"Skill snapshot is unreadable: {skill_snapshot['error']}.")
        if skill_snapshot.get("malformed_count"):
            issues.append(
                f"Skill snapshot contains {skill_snapshot['malformed_count']} malformed records."
            )

        memory_by_id: dict[str, list[tuple[str, MemoryRecord]]] = {}
        for layer, record in memory_rows:
            memory_by_id.setdefault(record.id, []).append((layer, record))
        skill_by_id: dict[str, list[dict[str, Any]]] = {}
        for record in skill_snapshot.get("records", []):
            skill_by_id.setdefault(str(record.get("id") or ""), []).append(record)

        selected_memories: list[dict[str, Any]] = []
        selected_skills: list[dict[str, Any]] = []
        missing_memory_ids: list[str] = []
        missing_skill_ids: list[str] = []
        excluded_memory_ids: list[str] = []
        excluded_skill_ids: list[str] = []

        for record_id in requested_memory_ids:
            matches = memory_by_id.get(record_id, [])
            if not matches:
                missing_memory_ids.append(record_id)
                continue
            if len(matches) != 1:
                issues.append(
                    f"Selected memory ID {record_id} is ambiguous across store layers."
                )
                continue
            layer, record = matches[0]
            if not record.active:
                excluded_memory_ids.append(record_id)
                continue
            payload = record.to_dict()
            payload["layer"] = layer
            selected_memories.append(deepcopy(payload))

        for record_id in requested_skill_ids:
            matches = skill_by_id.get(record_id, [])
            if not matches:
                missing_skill_ids.append(record_id)
                continue
            if len(matches) != 1:
                issues.append(f"Selected skill ID {record_id} is ambiguous in the skill store.")
                continue
            record = matches[0]
            if record.get("status") != "active":
                excluded_skill_ids.append(record_id)
                continue
            selected_skills.append(deepcopy(record))

        if missing_memory_ids:
            warnings.append("Requested memory IDs were not found: " + ", ".join(missing_memory_ids) + ".")
        if missing_skill_ids:
            warnings.append("Requested skill IDs were not found: " + ", ".join(missing_skill_ids) + ".")
        if excluded_memory_ids:
            warnings.append("Inactive memory IDs were excluded: " + ", ".join(excluded_memory_ids) + ".")
        if excluded_skill_ids:
            warnings.append("Archived skill IDs were excluded: " + ", ".join(excluded_skill_ids) + ".")

        status = "ERROR" if issues else "WARN" if warnings else "OK"
        return ExperienceLearningInputSnapshot(
            status=status,
            selection_mode=LEARNING_INPUT_SELECTION_MODE,
            requested_memory_ids=requested_memory_ids,
            requested_skill_ids=requested_skill_ids,
            memory_records=selected_memories,
            skill_records=selected_skills,
            missing_memory_ids=missing_memory_ids,
            missing_skill_ids=missing_skill_ids,
            excluded_memory_ids=excluded_memory_ids,
            excluded_skill_ids=excluded_skill_ids,
            issues=issues,
            warnings=warnings,
        )

    @staticmethod
    def build_reviewer(
        episodes: Iterable[ExperienceEpisode],
        snapshot: ExperienceLearningInputSnapshot,
    ) -> ExperienceLearningReviewer:
        if snapshot.status == "ERROR":
            raise ExperienceLearningInputError(
                "Learning input snapshot failed validation: " + "; ".join(snapshot.issues)
            )
        return ExperienceLearningReviewer(
            episodes,
            active_memories=snapshot.memory_records,
            active_skills=snapshot.skill_records,
        )

    @staticmethod
    def doctor(
        snapshot: ExperienceLearningInputSnapshot,
    ) -> ExperienceLearningInputDoctorReport:
        issues = list(snapshot.issues)
        warnings = list(snapshot.warnings)
        if snapshot.selection_mode != LEARNING_INPUT_SELECTION_MODE:
            issues.append("Selection mode is not explicit_ids_only.")
        if snapshot.retrieval_performed:
            issues.append("Snapshot reports forbidden implicit retrieval.")
        if snapshot.usage_telemetry_recorded:
            issues.append("Snapshot reports forbidden usage telemetry mutation.")
        if snapshot.mutation_performed:
            issues.append("Snapshot reports forbidden store mutation.")
        status = "ERROR" if issues else "WARN" if warnings else "OK"
        return ExperienceLearningInputDoctorReport(
            status=status,
            selected_memory_count=len(snapshot.memory_records),
            selected_skill_count=len(snapshot.skill_records),
            missing_count=len(snapshot.missing_memory_ids) + len(snapshot.missing_skill_ids),
            excluded_count=len(snapshot.excluded_memory_ids) + len(snapshot.excluded_skill_ids),
            issues=issues,
            warnings=warnings,
        )


def _unique_ids(values: Iterable[str]) -> tuple[list[str], list[str]]:
    unique: list[str] = []
    repeated: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = str(value).strip()
        if not normalized:
            continue
        if normalized in seen:
            repeated.append(normalized)
            continue
        seen.add(normalized)
        unique.append(normalized)
    return unique, sorted(set(repeated))


def _preview(value: object, limit: int = LEARNING_INPUT_PREVIEW_MAX_CHARS) -> str:
    text = " ".join(str(value or "").split())
    return text if len(text) <= limit else text[: limit - 3].rstrip() + "..."


def format_experience_learning_input_snapshot(
    snapshot: ExperienceLearningInputSnapshot,
) -> str:
    lines = [
        "Proto-Mind Experience Learning Input Snapshot v1",
        f"Status: {snapshot.status}",
        f"selection_mode: {snapshot.selection_mode}",
        f"requested_memory_ids: {', '.join(snapshot.requested_memory_ids) or 'none'}",
        f"requested_skill_ids: {', '.join(snapshot.requested_skill_ids) or 'none'}",
        f"selected_memories: {len(snapshot.memory_records)}",
    ]
    lines.extend(
        f"- {record.get('id')} [{record.get('layer')}/{record.get('type')}]: "
        f"{_preview(record.get('content'))}"
        for record in snapshot.memory_records
    )
    lines.append(f"selected_skills: {len(snapshot.skill_records)}")
    lines.extend(
        f"- {record.get('id')} [{record.get('category')}]: "
        f"{_preview(record.get('name'))}; summary={_preview(record.get('summary'))}"
        for record in snapshot.skill_records
    )
    lines.extend(f"- ERROR: {issue}" for issue in snapshot.issues)
    lines.extend(f"- WARN: {warning}" for warning in snapshot.warnings)
    lines.extend(
        [
            f"retrieval_performed: {str(snapshot.retrieval_performed).lower()}",
            f"usage_telemetry_recorded: {str(snapshot.usage_telemetry_recorded).lower()}",
            f"mutation_performed: {str(snapshot.mutation_performed).lower()}",
            "- Detached explicit-ID snapshot only; no implicit query, ranking, use increment, or write.",
        ]
    )
    return "\n".join(lines)


def format_experience_learning_input_doctor(
    adapter: ExperienceLearningInputAdapter,
    snapshot: ExperienceLearningInputSnapshot,
) -> str:
    report = adapter.doctor(snapshot)
    lines = [
        "Proto-Mind Experience Learning Input Doctor v1",
        f"Status: {report.status}",
        f"selected_memories: {report.selected_memory_count}",
        f"selected_skills: {report.selected_skill_count}",
        f"missing: {report.missing_count}",
        f"excluded_inactive_or_archived: {report.excluded_count}",
    ]
    lines.extend(f"- ERROR: {issue}" for issue in report.issues)
    lines.extend(f"- WARN: {warning}" for warning in report.warnings)
    if not report.issues and not report.warnings:
        lines.extend(
            [
                "- Explicit selected IDs resolved to active detached records.",
                "- Retrieval, usage telemetry, and mutation remain disabled.",
            ]
        )
    lines.append("- Doctor is read-only; no selection is inferred and no store is rewritten.")
    return "\n".join(lines)


def run_experience_learning_input_benchmark() -> ExperienceLearningInputBenchmarkReport:
    episodes = ExperienceEpisodeProjector(
        build_success_lifecycle_trace() + build_failure_correction_trace()
    ).project()
    success_lesson = str(episodes[0].lesson_candidates[0]["lesson_preview"])
    failure_lesson = str(episodes[1].lesson_candidates[0]["lesson_preview"])
    with TemporaryDirectory(prefix="proto-mind-learning-input-") as temp_dir:
        root = Path(temp_dir)
        memory_store = MemoryStore(
            working_path=root / "data" / "working.json",
            persistent_path=root / "data" / "persistent.json",
        )
        memory_store.save_working_memory(
            [
                MemoryRecord(
                    success_lesson,
                    "lesson",
                    0.9,
                    "operator",
                    id="mem_selected",
                    usage_count=7,
                ),
                MemoryRecord(
                    "Unselected memory must not affect review.",
                    "lesson",
                    0.8,
                    "operator",
                    id="mem_unselected",
                ),
            ]
        )
        memory_store.save_persistent_memory(
            [
                MemoryRecord(
                    "Inactive historical lesson.",
                    "lesson",
                    0.8,
                    "operator",
                    id="mem_inactive",
                    active=False,
                )
            ]
        )
        skills_path = root / "data" / "skills.jsonl"
        skill_records = [
            {
                "id": "skill_selected",
                "name": "Validate evidence",
                "summary": failure_lesson,
                "body": "Explicit test fixture body.",
                "status": "active",
                "category": "testing",
                "source": "operator",
                "tags": [],
                "uses": 3,
            },
            {
                "id": "skill_archived",
                "name": "Archived procedure",
                "summary": "Historical only.",
                "body": "",
                "status": "archived",
                "category": "other",
                "source": "operator",
                "tags": [],
                "uses": 0,
            },
        ]
        skills_path.write_text(
            "".join(json.dumps(record, sort_keys=True) + "\n" for record in skill_records),
            encoding="utf-8",
        )
        skill_library = SkillLibrary(skills_path)
        paths = [memory_store.working_path, memory_store.persistent_path, skills_path]
        before = {str(path): path.read_bytes() for path in paths}

        adapter = ExperienceLearningInputAdapter(
            memory_store=memory_store,
            skill_library=skill_library,
        )
        snapshot = adapter.build_snapshot(
            memory_ids=["mem_selected", "mem_inactive", "mem_missing"],
            skill_ids=["skill_selected", "skill_archived", "skill_missing"],
        )
        candidates = adapter.build_reviewer(episodes, snapshot).review()
        after = {str(path): path.read_bytes() for path in paths}

    duplicate_count = sum(candidate.status == "duplicate" for candidate in candidates)
    checks = {
        "explicit_selection_mode": snapshot.selection_mode == LEARNING_INPUT_SELECTION_MODE,
        "one_active_memory_selected": [record["id"] for record in snapshot.memory_records]
        == ["mem_selected"],
        "one_active_skill_selected": [record["id"] for record in snapshot.skill_records]
        == ["skill_selected"],
        "inactive_and_archived_excluded": snapshot.excluded_memory_ids == ["mem_inactive"]
        and snapshot.excluded_skill_ids == ["skill_archived"],
        "missing_ids_visible": snapshot.missing_memory_ids == ["mem_missing"]
        and snapshot.missing_skill_ids == ["skill_missing"],
        "duplicates_reach_reviewer": duplicate_count == 2,
        "retrieval_not_performed": snapshot.retrieval_performed is False,
        "usage_telemetry_not_recorded": snapshot.usage_telemetry_recorded is False,
        "mutation_not_performed": snapshot.mutation_performed is False,
        "usage_count_unchanged": snapshot.memory_records[0]["usage_count"] == 7,
        "source_files_unchanged": before == after,
    }
    failed_checks = [name for name, passed in checks.items() if not passed]
    return ExperienceLearningInputBenchmarkReport(
        status="OK" if not failed_checks else "FAIL",
        selected_memory_count=len(snapshot.memory_records),
        selected_skill_count=len(snapshot.skill_records),
        missing_count=len(snapshot.missing_memory_ids) + len(snapshot.missing_skill_ids),
        excluded_count=len(snapshot.excluded_memory_ids) + len(snapshot.excluded_skill_ids),
        reviewer_duplicate_count=duplicate_count,
        files_unchanged=before == after,
        checks=checks,
        failed_checks=failed_checks,
        boundary=(
            "Explicit-ID detached snapshots from isolated stores only; no relevance search, "
            "retrieval telemetry, usage increment, automatic selection, live store access, "
            "memory/skill mutation, persistence, command, LLM, execution, or export."
        ),
    )


def format_experience_learning_input_benchmark(
    report: ExperienceLearningInputBenchmarkReport | None = None,
) -> str:
    report = report or run_experience_learning_input_benchmark()
    lines = [
        "Proto-Mind Experience Learning Input Adapter v1",
        f"Status: {report.status}",
        f"selected_memories: {report.selected_memory_count}",
        f"selected_skills: {report.selected_skill_count}",
        f"missing: {report.missing_count}",
        f"excluded: {report.excluded_count}",
        f"reviewer_duplicates: {report.reviewer_duplicate_count}",
        f"files_unchanged: {str(report.files_unchanged).lower()}",
        "Checks:",
    ]
    lines.extend(
        f"- [{'PASS' if passed else 'FAIL'}] {name}" for name, passed in report.checks.items()
    )
    lines.extend(["Boundary:", f"- {report.boundary}"])
    return "\n".join(lines)


def main() -> int:
    report = run_experience_learning_input_benchmark()
    print(format_experience_learning_input_benchmark(report))
    return 0 if report.status == "OK" else 1


if __name__ == "__main__":
    raise SystemExit(main())
