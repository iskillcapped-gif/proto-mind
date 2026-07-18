from __future__ import annotations

from collections import Counter, defaultdict
from copy import deepcopy
from dataclasses import asdict, dataclass
import hashlib
import re
from typing import Any, Iterable

from proto_mind.experience_ledger import ExperienceEvent, compact_preview
from proto_mind.experience_turn import (
    CognitiveTurnEpisode,
    CognitiveTurnProjectionError,
    CognitiveTurnProjector,
)


LEARNING_BRIDGE_VERSION = 1
LEARNING_BRIDGE_MODE = "operator_review_preview_only"
LEARNING_BRIDGE_MAX_CANDIDATES_PER_TURN = 8
LEARNING_BRIDGE_CANDIDATE_STATUSES = frozenset(
    {"operator_review_required", "needs_more_evidence", "blocked"}
)
LEARNING_BRIDGE_SOURCE_KINDS = frozenset(
    {
        "correction_guidance",
        "reflection_warning",
        "grounding_warning",
        "unsupported_claim",
    }
)

_SOURCE_SPECS = (
    ("correction_guidance_applied", "hint_previews", "correction_guidance", None),
    ("reflection_evaluated", "warning_previews", "reflection_warning", "overall_confidence"),
    ("grounding_evaluated", "warning_previews", "grounding_warning", "confidence"),
    ("grounding_evaluated", "unsupported_claim_previews", "unsupported_claim", "confidence"),
)


@dataclass(frozen=True)
class CognitiveLearningPreviewCandidate:
    id: str
    session_id: str
    turn_id: str
    text: str
    source_kinds: list[str]
    evidence_event_ids: list[str]
    confidence: str
    review_status: str
    suggested_target: str
    rationale: str
    operator_confirmation_required: bool = True
    promotion_ready: bool = False
    auto_apply_allowed: bool = False
    persistence_performed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CognitiveLearningTurnReview:
    id: str
    session_id: str
    turn_id: str
    episode_status: str
    created_at: str
    source_event_ids: list[str]
    candidates: list[CognitiveLearningPreviewCandidate]
    truncated: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CognitiveLearningBridgeDoctorReport:
    status: str
    episode_count: int
    candidate_count: int
    review_required_count: int
    needs_evidence_count: int
    blocked_count: int
    issues: list[str]
    warnings: list[str]


class CognitiveLearningBridgeError(RuntimeError):
    pass


class OperatorReviewedLearningBridge:
    """Projects explicit cognitive findings into non-applying review previews."""

    def __init__(self, events: Iterable[ExperienceEvent | dict[str, Any]]) -> None:
        self._events = [
            event.to_dict() if isinstance(event, ExperienceEvent) else deepcopy(dict(event))
            for event in events
        ]

    def review(self) -> list[CognitiveLearningTurnReview]:
        try:
            episodes = CognitiveTurnProjector(self._events).project()
        except CognitiveTurnProjectionError as exc:
            raise CognitiveLearningBridgeError(str(exc)) from exc

        grouped: defaultdict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
        for event in self._events:
            grouped[(str(event.get("session_id", "")), str(event.get("turn_id", "")))].append(
                event
            )
        return [
            self._review_episode(episode, grouped[(episode.session_id, episode.turn_id)])
            for episode in episodes
        ]

    def doctor(self) -> CognitiveLearningBridgeDoctorReport:
        issues: list[str] = []
        warnings: list[str] = []
        try:
            reviews = self.review()
        except CognitiveLearningBridgeError as exc:
            return CognitiveLearningBridgeDoctorReport(
                status="ERROR",
                episode_count=0,
                candidate_count=0,
                review_required_count=0,
                needs_evidence_count=0,
                blocked_count=0,
                issues=[str(exc)],
                warnings=[],
            )

        candidate_ids: set[str] = set()
        statuses: Counter[str] = Counter()
        for review in reviews:
            if review.episode_status != "COMPLETE":
                warnings.append(
                    f"Turn {review.turn_id} is incomplete; its candidates remain blocked."
                )
            if review.truncated:
                warnings.append(
                    f"Turn {review.turn_id} exceeded the bounded candidate preview limit."
                )
            if len(review.candidates) > LEARNING_BRIDGE_MAX_CANDIDATES_PER_TURN:
                issues.append(f"Turn {review.turn_id} exceeds the candidate preview limit.")

            source_ids = set(review.source_event_ids)
            for candidate in review.candidates:
                statuses[candidate.review_status] += 1
                if candidate.id in candidate_ids:
                    issues.append(f"Candidate id {candidate.id} is duplicated.")
                candidate_ids.add(candidate.id)
                if candidate.review_status not in LEARNING_BRIDGE_CANDIDATE_STATUSES:
                    issues.append(
                        f"Candidate {candidate.id} has invalid status {candidate.review_status}."
                    )
                if not candidate.text or len(candidate.text) > 160:
                    issues.append(f"Candidate {candidate.id} has an invalid compact preview.")
                if not candidate.evidence_event_ids or any(
                    event_id not in source_ids for event_id in candidate.evidence_event_ids
                ):
                    issues.append(f"Candidate {candidate.id} has invalid episode provenance.")
                if not candidate.source_kinds or any(
                    source not in LEARNING_BRIDGE_SOURCE_KINDS
                    for source in candidate.source_kinds
                ):
                    issues.append(f"Candidate {candidate.id} has an invalid source kind.")
                if not candidate.operator_confirmation_required:
                    issues.append(f"Candidate {candidate.id} bypasses operator confirmation.")
                if candidate.promotion_ready or candidate.auto_apply_allowed:
                    issues.append(f"Candidate {candidate.id} exposes forbidden promotion/apply.")
                if candidate.persistence_performed:
                    issues.append(f"Candidate {candidate.id} claims forbidden persistence.")

        status = "ERROR" if issues else "WARN" if warnings else "OK"
        return CognitiveLearningBridgeDoctorReport(
            status=status,
            episode_count=len(reviews),
            candidate_count=sum(len(review.candidates) for review in reviews),
            review_required_count=statuses["operator_review_required"],
            needs_evidence_count=statuses["needs_more_evidence"],
            blocked_count=statuses["blocked"],
            issues=issues,
            warnings=warnings,
        )

    @staticmethod
    def _review_episode(
        episode: CognitiveTurnEpisode,
        events: list[dict[str, Any]],
    ) -> CognitiveLearningTurnReview:
        findings: dict[str, dict[str, Any]] = {}
        truncated = False
        for event_type, payload_key, source_kind, confidence_key in _SOURCE_SPECS:
            for event in events:
                if event.get("event_type") != event_type:
                    continue
                payload = event.get("payload")
                if not isinstance(payload, dict):
                    continue
                values = payload.get(payload_key)
                if not isinstance(values, list):
                    continue
                for value in values:
                    text = compact_preview(value)
                    normalized = _normalize_text(text)
                    if not normalized:
                        continue
                    if (
                        normalized not in findings
                        and len(findings) >= LEARNING_BRIDGE_MAX_CANDIDATES_PER_TURN
                    ):
                        truncated = True
                        continue
                    finding = findings.setdefault(
                        normalized,
                        {
                            "text": text,
                            "source_kinds": [],
                            "evidence_event_ids": [],
                            "confidence": [],
                        },
                    )
                    if source_kind not in finding["source_kinds"]:
                        finding["source_kinds"].append(source_kind)
                    event_id = str(event.get("id") or "")
                    if event_id and event_id not in finding["evidence_event_ids"]:
                        finding["evidence_event_ids"].append(event_id)
                    if confidence_key:
                        finding["confidence"].append(
                            _confidence_label(payload.get(confidence_key))
                        )

        candidates: list[CognitiveLearningPreviewCandidate] = []
        for normalized, finding in findings.items():
            source_kinds = list(finding["source_kinds"])
            review_status = (
                "blocked"
                if episode.status != "COMPLETE"
                else "operator_review_required"
                if "correction_guidance" in source_kinds
                else "needs_more_evidence"
            )
            rationale = (
                "Applied correction guidance is reusable only after explicit operator review."
                if "correction_guidance" in source_kinds
                else "A diagnostic finding is not a verified reusable lesson without more evidence."
            )
            if episode.status != "COMPLETE":
                rationale = "The cognitive episode is incomplete, so promotion review is blocked."
            digest = hashlib.sha256(
                f"{episode.session_id}\0{episode.turn_id}\0{normalized}".encode("utf-8")
            ).hexdigest()[:12]
            candidates.append(
                CognitiveLearningPreviewCandidate(
                    id=f"learnprev_{_safe_id(episode.turn_id)}_{digest}",
                    session_id=episode.session_id,
                    turn_id=episode.turn_id,
                    text=str(finding["text"]),
                    source_kinds=source_kinds,
                    evidence_event_ids=list(finding["evidence_event_ids"]),
                    confidence=_lowest_confidence(finding["confidence"]),
                    review_status=review_status,
                    suggested_target=(
                        "lesson" if "correction_guidance" in source_kinds else "review_only"
                    ),
                    rationale=rationale,
                )
            )

        return CognitiveLearningTurnReview(
            id=f"learnreview_{_safe_id(episode.session_id)}_{_safe_id(episode.turn_id)}",
            session_id=episode.session_id,
            turn_id=episode.turn_id,
            episode_status=episode.status,
            created_at=episode.created_at,
            source_event_ids=list(episode.event_ids),
            candidates=candidates,
            truncated=truncated,
        )


def format_learning_bridge_command(
    command: str,
    events: Iterable[ExperienceEvent | dict[str, Any]],
    *,
    pilot_state: str,
) -> str | None:
    raw = command.strip()
    normalized = " ".join(raw.lower().split())
    if normalized != "/experience learning" and not normalized.startswith(
        "/experience learning "
    ):
        return None
    bridge = OperatorReviewedLearningBridge(events)
    if normalized in {"/experience learning", "/experience learning status"}:
        return format_learning_bridge_status(bridge, pilot_state=pilot_state)
    if normalized == "/experience learning preview":
        return format_learning_bridge_preview(bridge)
    prefix = "/experience learning preview "
    if normalized.startswith(prefix):
        parts = raw.split(maxsplit=3)
        selector = parts[3].strip() if len(parts) == 4 else ""
        return format_learning_bridge_preview(bridge, selector=selector)
    if normalized == "/experience learning doctor":
        return format_learning_bridge_doctor(bridge)
    return _usage()


def format_learning_bridge_status(
    bridge: OperatorReviewedLearningBridge,
    *,
    pilot_state: str,
) -> str:
    try:
        reviews = bridge.review()
    except CognitiveLearningBridgeError as exc:
        return _error_report("Status", exc)
    counts = Counter(
        candidate.review_status
        for review in reviews
        for candidate in review.candidates
    )
    candidate_count = sum(counts.values())
    return "\n".join(
        [
            "Proto-Mind Operator-Reviewed Learning Bridge Preview v1",
            f"Status: {'READY' if reviews else 'EMPTY'}",
            f"mode: {LEARNING_BRIDGE_MODE}",
            f"pilot_state: {pilot_state}",
            f"episodes: {len(reviews)}",
            f"candidates: {candidate_count}",
            f"operator_review_required: {counts['operator_review_required']}",
            f"needs_more_evidence: {counts['needs_more_evidence']}",
            f"blocked: {counts['blocked']}",
            "source: bounded redacted process-memory cognitive episodes",
            "Commands: /experience learning status | preview [latest|<turn_id>] | doctor",
            "- No candidate is persisted, promoted, applied, or written to memory/skills.",
        ]
    )


def format_learning_bridge_preview(
    bridge: OperatorReviewedLearningBridge,
    *,
    selector: str = "latest",
) -> str:
    try:
        reviews = bridge.review()
    except CognitiveLearningBridgeError as exc:
        return _error_report("Preview", exc)
    if not reviews:
        return "\n".join(
            [
                "Proto-Mind Operator-Reviewed Learning Bridge Preview v1",
                "Status: EMPTY",
                "- No captured cognitive episode is available in process memory.",
                "- No candidate, file, memory, or skill was changed.",
            ]
        )

    normalized = selector.strip() or "latest"
    review = reviews[-1] if normalized.lower() == "latest" else next(
        (item for item in reversed(reviews) if item.turn_id == normalized),
        None,
    )
    if review is None:
        return "\n".join(
            [
                "Proto-Mind Operator-Reviewed Learning Bridge Preview v1",
                "Status: NOT FOUND",
                f"- No captured episode matches turn {normalized!r}.",
                f"- Available turns: {', '.join(item.turn_id for item in reviews)}",
                "- No candidate, file, memory, or skill was changed.",
            ]
        )

    lines = [
        "Proto-Mind Operator-Reviewed Learning Bridge Preview v1",
        f"Status: {'REVIEW REQUIRED' if review.candidates else 'NO CANDIDATE'}",
        f"review_id: {review.id}",
        f"session_id: {review.session_id}",
        f"turn_id: {review.turn_id}",
        f"episode_status: {review.episode_status}",
        f"candidates: {len(review.candidates)}",
        "Candidates:",
    ]
    if not review.candidates:
        lines.extend(
            [
                "- none",
                "- A clean cognitive turn is not treated as a reusable lesson by default.",
            ]
        )
    for candidate in review.candidates:
        lines.extend(
            [
                f"- id: {candidate.id}",
                f"  finding: {candidate.text}",
                f"  source_kinds: {', '.join(candidate.source_kinds)}",
                f"  evidence_event_ids: {', '.join(candidate.evidence_event_ids)}",
                f"  confidence: {candidate.confidence}",
                f"  review_status: {candidate.review_status}",
                f"  suggested_target: {candidate.suggested_target}",
                f"  rationale: {candidate.rationale}",
                "  operator_confirmation_required: true",
                "  promotion_ready: false",
                "  auto_apply_allowed: false",
                "  persistence_performed: false",
            ]
        )
    if review.truncated:
        lines.append(
            f"- Candidate display truncated at {LEARNING_BRIDGE_MAX_CANDIDATES_PER_TURN} findings."
        )
    lines.extend(
        [
            "Boundary:",
            "- Exact evidence preview only; no LLM summarization or inferred lesson text.",
            "- Future promotion requires a separate explicit operator-confirmation layer.",
            "- No memory, skill, event, episode, file, consent, or context state was changed.",
        ]
    )
    return "\n".join(lines)


def format_learning_bridge_doctor(bridge: OperatorReviewedLearningBridge) -> str:
    report = bridge.doctor()
    lines = [
        "Proto-Mind Operator-Reviewed Learning Bridge Doctor v1",
        f"Status: {report.status}",
        f"episodes: {report.episode_count}",
        f"candidates: {report.candidate_count}",
        f"operator_review_required: {report.review_required_count}",
        f"needs_more_evidence: {report.needs_evidence_count}",
        f"blocked: {report.blocked_count}",
    ]
    lines.extend(f"- ERROR: {issue}" for issue in report.issues)
    lines.extend(f"- WARN: {warning}" for warning in report.warnings)
    if not report.issues and not report.warnings:
        lines.extend(
            [
                "- Candidate provenance, bounds, and confirmation boundaries are healthy.",
                "- Promotion, automatic apply, and persistence remain unavailable.",
            ]
        )
    lines.append("- Doctor is read-only; it does not repair, promote, persist, or execute.")
    return "\n".join(lines)


def _normalize_text(value: str) -> str:
    return " ".join(value.casefold().split())


def _safe_id(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "-", value).strip("-")[:60] or "unknown"


def _confidence_label(value: object) -> str:
    if isinstance(value, str) and value.casefold() in {"high", "medium", "low"}:
        return value.casefold()
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        return "unknown"
    if confidence >= 0.8:
        return "high"
    if confidence >= 0.5:
        return "medium"
    if 0.0 <= confidence <= 1.0:
        return "low"
    return "unknown"


def _lowest_confidence(values: Iterable[str]) -> str:
    order = {"unknown": 0, "low": 1, "medium": 2, "high": 3}
    normalized = [value if value in order else "unknown" for value in values]
    return min(normalized, key=order.get) if normalized else "unknown"


def _error_report(kind: str, error: Exception) -> str:
    return "\n".join(
        [
            f"Proto-Mind Operator-Reviewed Learning Bridge {kind} v1",
            "Status: ERROR",
            f"- {error}",
            "- No candidate, file, memory, or skill was changed.",
        ]
    )


def _usage() -> str:
    return "\n".join(
        [
            "Experience Learning Bridge commands:",
            "/experience learning status",
            "/experience learning preview [latest|<turn_id>]",
            "/experience learning doctor",
        ]
    )
