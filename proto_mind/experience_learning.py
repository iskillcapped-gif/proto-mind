from __future__ import annotations

from collections import Counter, defaultdict
from copy import deepcopy
from dataclasses import asdict, dataclass
from pathlib import Path
import re
from tempfile import TemporaryDirectory
from typing import Any, Iterable

from proto_mind.experience_episode import ExperienceEpisode, ExperienceEpisodeProjector
from proto_mind.experience_ledger import TemporaryExperienceLedgerStore
from proto_mind.experience_vocabulary import (
    build_failure_correction_trace,
    build_success_lifecycle_trace,
)


LEARNING_REVIEW_CONFIDENCE_THRESHOLD = 0.8
LEARNING_CANDIDATE_STATUSES = frozenset(
    {"eligible_for_review", "needs_more_evidence", "duplicate", "blocked"}
)


@dataclass(frozen=True)
class ExperienceLearningCandidate:
    id: str
    episode_id: str
    source_candidate_id: str
    text: str
    confidence: float | None
    status: str
    evidence_event_ids: list[str]
    promotion_evidence: list[dict[str, Any]]
    duplicate_matches: list[str]
    operator_confirmation_required: bool
    auto_apply_allowed: bool
    reasons: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ExperienceLearningDoctorReport:
    status: str
    episode_count: int
    candidate_count: int
    eligible_count: int
    needs_evidence_count: int
    duplicate_count: int
    blocked_count: int
    issues: list[str]
    warnings: list[str]


@dataclass(frozen=True)
class ExperienceLearningBenchmarkReport:
    status: str
    event_count: int
    episode_count: int
    candidate_count: int
    eligible_count: int
    needs_evidence_count: int
    duplicate_memory_detected: bool
    duplicate_skill_detected: bool
    temporary_hash_verified: int
    checks: dict[str, bool]
    failed_checks: list[str]
    boundary: str


class ExperienceLearningReviewer:
    """Classifies learning evidence without promoting, persisting, or executing it."""

    def __init__(
        self,
        episodes: Iterable[ExperienceEpisode],
        *,
        active_memories: Iterable[str | dict[str, Any]] = (),
        active_skills: Iterable[str | dict[str, Any]] = (),
    ) -> None:
        self._episodes = deepcopy(list(episodes))
        self._memory_index = _reference_index(active_memories, kind="memory")
        self._skill_index = _reference_index(active_skills, kind="skill")

    def review(self) -> list[ExperienceLearningCandidate]:
        lesson_text_counts = Counter(
            _normalize_text(str(lesson.get("lesson_preview") or ""))
            for episode in self._episodes
            for lesson in episode.lesson_candidates
            if str(lesson.get("lesson_preview") or "").strip()
        )
        candidate_id_counts = Counter(
            str(lesson.get("candidate_id") or "")
            for episode in self._episodes
            for lesson in episode.lesson_candidates
            if str(lesson.get("candidate_id") or "")
        )
        candidates: list[ExperienceLearningCandidate] = []
        for episode in self._episodes:
            for lesson in episode.lesson_candidates:
                candidates.append(
                    self._review_lesson(
                        episode,
                        lesson,
                        lesson_text_counts=lesson_text_counts,
                        candidate_id_counts=candidate_id_counts,
                    )
                )
        return candidates

    def doctor(self) -> ExperienceLearningDoctorReport:
        candidates = self.review()
        issues: list[str] = []
        warnings: list[str] = []
        for candidate in candidates:
            if candidate.status not in LEARNING_CANDIDATE_STATUSES:
                issues.append(f"Candidate {candidate.id} has invalid status {candidate.status}.")
            if candidate.auto_apply_allowed:
                issues.append(f"Candidate {candidate.id} exposes forbidden automatic apply.")
            if candidate.status == "blocked":
                issues.extend(
                    f"Candidate {candidate.id}: {reason}" for reason in candidate.reasons
                )
            if candidate.status == "duplicate":
                warnings.append(
                    f"Candidate {candidate.id} duplicates: {', '.join(candidate.duplicate_matches)}."
                )

        for episode in self._episodes:
            lesson_event_ids = {
                str(lesson.get("event_id") or "") for lesson in episode.lesson_candidates
            }
            for promotion in episode.memory_promotions:
                evidence_ids = {
                    str(value) for value in promotion.get("evidence_event_ids", [])
                }
                if not lesson_event_ids.intersection(evidence_ids):
                    issues.append(
                        f"Episode {episode.id} has promotion evidence not linked to a lesson event."
                    )
            expected_lessons = sum(
                int(reflection.get("lesson_candidate_count") or 0)
                for reflection in episode.reflections
            )
            if expected_lessons > len(episode.lesson_candidates):
                warnings.append(
                    f"Episode {episode.id} declares {expected_lessons} lesson candidates but "
                    f"projects {len(episode.lesson_candidates)}."
                )

        counts = Counter(candidate.status for candidate in candidates)
        status = "ERROR" if issues else "WARN" if warnings else "OK"
        return ExperienceLearningDoctorReport(
            status=status,
            episode_count=len(self._episodes),
            candidate_count=len(candidates),
            eligible_count=counts["eligible_for_review"],
            needs_evidence_count=counts["needs_more_evidence"],
            duplicate_count=counts["duplicate"],
            blocked_count=counts["blocked"],
            issues=issues,
            warnings=warnings,
        )

    def _review_lesson(
        self,
        episode: ExperienceEpisode,
        lesson: dict[str, Any],
        *,
        lesson_text_counts: Counter[str],
        candidate_id_counts: Counter[str],
    ) -> ExperienceLearningCandidate:
        source_candidate_id = str(lesson.get("candidate_id") or "")
        lesson_event_id = str(lesson.get("event_id") or "")
        text = str(lesson.get("lesson_preview") or "").strip()
        normalized_text = _normalize_text(text)
        confidence = _confidence(lesson.get("confidence"))
        reasons: list[str] = []
        duplicates: list[str] = []

        if not source_candidate_id:
            reasons.append("candidate_id is missing")
        elif candidate_id_counts[source_candidate_id] > 1:
            reasons.append("candidate_id is not unique across reviewed episodes")
        if not text:
            reasons.append("lesson text is empty")
        if not lesson_event_id or lesson_event_id not in episode.source_event_ids:
            reasons.append("lesson event provenance is missing from the episode")
        if lesson.get("requires_operator_confirmation") is not True:
            reasons.append("operator confirmation boundary is missing")
        if confidence is None:
            reasons.append("confidence is missing or outside 0..1")

        if normalized_text:
            duplicates.extend(self._memory_index.get(normalized_text, []))
            duplicates.extend(self._skill_index.get(normalized_text, []))
            if lesson_text_counts[normalized_text] > 1:
                duplicates.append("another_learning_candidate")

        promotions = [
            deepcopy(promotion)
            for promotion in episode.memory_promotions
            if lesson_event_id
            and lesson_event_id
            in {str(value) for value in promotion.get("evidence_event_ids", [])}
        ]
        for promotion in promotions:
            evidence_ids = [str(value) for value in promotion.get("evidence_event_ids", [])]
            if any(event_id not in episode.source_event_ids for event_id in evidence_ids):
                reasons.append("promotion evidence references an event outside the episode")
            if promotion.get("operator_confirmation_required") is not True:
                reasons.append("promotion evidence lacks operator confirmation")
            if promotion.get("promotion_performed_by_builder") is not False:
                reasons.append("promotion evidence does not preserve the no-auto-promotion marker")

        if reasons:
            status = "blocked"
        elif duplicates:
            status = "duplicate"
            reasons.append("exact normalized content already exists or repeats in this review")
        elif (
            episode.status == "completed_verified"
            and episode.verified
            and confidence is not None
            and confidence >= LEARNING_REVIEW_CONFIDENCE_THRESHOLD
        ):
            status = "eligible_for_review"
            reasons.append("verified completion and confidence meet the review threshold")
        else:
            status = "needs_more_evidence"
            reasons.append("candidate lacks verified successful outcome evidence")

        return ExperienceLearningCandidate(
            id=f"learn_{_safe_id(episode.id)}_{_safe_id(source_candidate_id)}",
            episode_id=episode.id,
            source_candidate_id=source_candidate_id,
            text=text,
            confidence=confidence,
            status=status,
            evidence_event_ids=[lesson_event_id] if lesson_event_id else [],
            promotion_evidence=promotions,
            duplicate_matches=sorted(set(duplicates)),
            operator_confirmation_required=(
                lesson.get("requires_operator_confirmation") is True
            ),
            auto_apply_allowed=False,
            reasons=reasons,
        )


def _reference_index(
    records: Iterable[str | dict[str, Any]],
    *,
    kind: str,
) -> dict[str, list[str]]:
    index: defaultdict[str, list[str]] = defaultdict(list)
    for position, record in enumerate(deepcopy(list(records)), start=1):
        if isinstance(record, str):
            normalized = _normalize_text(record)
            if normalized:
                index[normalized].append(f"{kind}:{position}")
            continue
        record_id = str(record.get("id") or position)
        fields = ("content",) if kind == "memory" else ("name", "summary", "body")
        for field in fields:
            normalized = _normalize_text(str(record.get(field) or ""))
            if normalized:
                index[normalized].append(f"{kind}:{record_id}:{field}")
    return dict(index)


def _normalize_text(value: str) -> str:
    return " ".join(value.casefold().split())


def _confidence(value: object) -> float | None:
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        return None
    return confidence if 0.0 <= confidence <= 1.0 else None


def _safe_id(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "-", value).strip("-")[:100] or "unknown"


def format_experience_learning_candidate(candidate: ExperienceLearningCandidate) -> str:
    lines = [
        "Proto-Mind Experience Learning Candidate v1",
        f"Status: {candidate.status}",
        f"id: {candidate.id}",
        f"episode_id: {candidate.episode_id}",
        f"source_candidate_id: {candidate.source_candidate_id or 'none'}",
        f"lesson: {candidate.text or 'none'}",
        f"confidence: {candidate.confidence if candidate.confidence is not None else 'none'}",
        f"evidence_event_ids: {', '.join(candidate.evidence_event_ids) or 'none'}",
        f"promotion_evidence_count: {len(candidate.promotion_evidence)}",
        f"duplicate_matches: {', '.join(candidate.duplicate_matches) or 'none'}",
        f"operator_confirmation_required: {str(candidate.operator_confirmation_required).lower()}",
        f"auto_apply_allowed: {str(candidate.auto_apply_allowed).lower()}",
        "Reasons:",
    ]
    lines.extend(f"- {reason}" for reason in candidate.reasons)
    lines.append("- Review only: no memory, skill, episode, event, or file was changed.")
    return "\n".join(lines)


def format_experience_learning_review(reviewer: ExperienceLearningReviewer) -> str:
    candidates = reviewer.review()
    report = reviewer.doctor()
    lines = [
        "Proto-Mind Experience Learning Candidate Review v1",
        f"Status: {report.status}",
        f"episodes: {report.episode_count}",
        f"candidates: {report.candidate_count}",
        f"eligible_for_review: {report.eligible_count}",
        f"needs_more_evidence: {report.needs_evidence_count}",
        f"duplicates: {report.duplicate_count}",
        f"blocked: {report.blocked_count}",
        "Candidates:",
    ]
    for candidate in candidates:
        lines.append(
            f"- {candidate.id}: {candidate.status}; confidence="
            f"{candidate.confidence if candidate.confidence is not None else 'none'}; "
            f"promotion_evidence={len(candidate.promotion_evidence)}; "
            f"lesson={candidate.text or 'none'}"
        )
    if not candidates:
        lines.append("- none")
    lines.extend(
        [
            "Boundary:",
            "- Review results are advisory and ephemeral.",
            "- No automatic apply, memory promotion, skill creation, persistence, or command execution.",
        ]
    )
    return "\n".join(lines)


def format_experience_learning_doctor(reviewer: ExperienceLearningReviewer) -> str:
    report = reviewer.doctor()
    lines = [
        "Proto-Mind Experience Learning Doctor v1",
        f"Status: {report.status}",
        f"episodes: {report.episode_count}",
        f"candidates: {report.candidate_count}",
        f"eligible_for_review: {report.eligible_count}",
        f"needs_more_evidence: {report.needs_evidence_count}",
        f"duplicates: {report.duplicate_count}",
        f"blocked: {report.blocked_count}",
    ]
    lines.extend(f"- ERROR: {issue}" for issue in report.issues)
    lines.extend(f"- WARN: {warning}" for warning in report.warnings)
    if not report.issues and not report.warnings:
        lines.extend(
            [
                "- Candidate provenance and confirmation boundaries are valid.",
                "- Every candidate remains non-executable and non-applying.",
            ]
        )
    lines.append("- Doctor is read-only; it does not repair, promote, persist, or execute.")
    return "\n".join(lines)


def run_experience_learning_benchmark() -> ExperienceLearningBenchmarkReport:
    success_events = build_success_lifecycle_trace()
    failure_events = build_failure_correction_trace()
    events = success_events + failure_events
    episodes = ExperienceEpisodeProjector(events).project()
    reviewer = ExperienceLearningReviewer(episodes)
    candidates = reviewer.review()
    success_candidate, failure_candidate = candidates

    duplicate_memory = ExperienceLearningReviewer(
        [episodes[0]],
        active_memories=[
            {"id": "mem_existing", "content": success_candidate.text}
        ],
    ).review()[0]
    duplicate_skill = ExperienceLearningReviewer(
        [episodes[1]],
        active_skills=[
            {"id": "skill_existing", "summary": failure_candidate.text}
        ],
    ).review()[0]

    with TemporaryDirectory(prefix="proto-mind-experience-learning-") as temp_dir:
        path = Path(temp_dir) / "experience.jsonl"
        store = TemporaryExperienceLedgerStore(path)
        store.append_events(success_events, stored_at="2026-01-01T08:00:00Z")
        store.append_events(failure_events, stored_at="2026-01-01T08:01:00Z")
        before = path.read_bytes()
        stored_episodes = ExperienceEpisodeProjector.from_temporary_store(store).project()
        stored_candidates = ExperienceLearningReviewer(stored_episodes).review()
        store_report = store.doctor()
        temporary_store_unchanged = path.read_bytes() == before

    checks = {
        "learning_doctor_ok": reviewer.doctor().status == "OK",
        "success_eligible_for_review": success_candidate.status == "eligible_for_review",
        "failure_needs_more_evidence": failure_candidate.status == "needs_more_evidence",
        "promotion_provenance_linked": bool(success_candidate.promotion_evidence)
        and success_candidate.evidence_event_ids[0]
        in success_candidate.promotion_evidence[0].get("evidence_event_ids", []),
        "operator_confirmation_required": all(
            candidate.operator_confirmation_required for candidate in candidates
        ),
        "automatic_apply_forbidden": all(
            candidate.auto_apply_allowed is False for candidate in candidates
        ),
        "duplicate_memory_detected": duplicate_memory.status == "duplicate",
        "duplicate_skill_detected": duplicate_skill.status == "duplicate",
        "temporary_projection_matches": [item.to_dict() for item in stored_candidates]
        == [item.to_dict() for item in candidates],
        "temporary_store_unchanged": temporary_store_unchanged,
        "temporary_hash_chain_valid": store_report.status == "OK"
        and store_report.hash_verified_count == len(events),
    }
    failed_checks = [name for name, passed in checks.items() if not passed]
    counts = Counter(candidate.status for candidate in candidates)
    return ExperienceLearningBenchmarkReport(
        status="OK" if not failed_checks else "FAIL",
        event_count=len(events),
        episode_count=len(episodes),
        candidate_count=len(candidates),
        eligible_count=counts["eligible_for_review"],
        needs_evidence_count=counts["needs_more_evidence"],
        duplicate_memory_detected=checks["duplicate_memory_detected"],
        duplicate_skill_detected=checks["duplicate_skill_detected"],
        temporary_hash_verified=store_report.hash_verified_count,
        checks=checks,
        failed_checks=failed_checks,
        boundary=(
            "Deterministic in-memory review over projected and isolated temporary evidence; "
            "no LLM, live capture, persistence, automatic apply, memory/skill mutation, "
            "command, execution, or export."
        ),
    )


def format_experience_learning_benchmark(
    report: ExperienceLearningBenchmarkReport | None = None,
) -> str:
    report = report or run_experience_learning_benchmark()
    lines = [
        "Proto-Mind Experience Learning Candidate Review v1",
        f"Status: {report.status}",
        f"events: {report.event_count}",
        f"episodes: {report.episode_count}",
        f"candidates: {report.candidate_count}",
        f"eligible_for_review: {report.eligible_count}",
        f"needs_more_evidence: {report.needs_evidence_count}",
        f"duplicate_memory_detected: {str(report.duplicate_memory_detected).lower()}",
        f"duplicate_skill_detected: {str(report.duplicate_skill_detected).lower()}",
        f"temporary_hash_verified: {report.temporary_hash_verified}/{report.event_count}",
        "Checks:",
    ]
    lines.extend(
        f"- [{'PASS' if passed else 'FAIL'}] {name}" for name, passed in report.checks.items()
    )
    lines.extend(["Boundary:", f"- {report.boundary}"])
    return "\n".join(lines)


def main() -> int:
    report = run_experience_learning_benchmark()
    print(format_experience_learning_benchmark(report))
    return 0 if report.status == "OK" else 1


if __name__ == "__main__":
    raise SystemExit(main())
