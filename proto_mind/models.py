from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


@dataclass
class MemoryRecord:
    content: str
    type: str
    importance: float
    source: str
    tags: list[str] = field(default_factory=list)
    id: str = field(default_factory=lambda: str(uuid4()))
    timestamp: str = field(default_factory=utc_now_iso)
    last_used: str | None = None
    usage_count: int = 0
    weight: float = 1.0
    active: bool = True
    superseded_by: str | None = None
    superseded_at: str | None = None
    superseded_reason: str | None = None
    confidence: float | None = None
    updated_at: str | None = None

    def touch(self) -> None:
        self.last_used = utc_now_iso()
        self.usage_count += 1

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MemoryRecord":
        known_fields = {field.name for field in fields(cls)}
        return cls(**{key: value for key, value in data.items() if key in known_fields})


@dataclass
class ObserverState:
    query_type: str
    needs_memory: bool
    importance_hint: float
    topic_tags: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RetrievalCandidateTrace:
    record_id: str
    content_preview: str
    memory_type: str
    active: bool
    stored_tags: list[str]
    normalized_topics: list[str]
    matched_topics: list[str]
    topical_score: float
    topical_contribution: float
    importance_contribution: float
    recency_contribution: float
    usage_contribution: float
    state_bias_contribution: float
    final_total_score: float
    preference_priority_contribution: float = 0.0
    selected: bool = False
    selected_rank: int | None = None
    filtered_reason: str | None = None
    top_reasons: list[str] = field(default_factory=list)
    why_selected_summary: str | None = None
    why_not_selected_summary: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RetrievalTrace:
    user_input: str
    query_type: str
    normalized_query_topics: list[str]
    specific_query_topics: list[str]
    query_mode: str
    current_state_oriented: bool
    historical_state_oriented: bool
    broad_inventory: bool
    top_k: int
    candidates: list[RetrievalCandidateTrace] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "user_input": self.user_input,
            "query_type": self.query_type,
            "normalized_query_topics": list(self.normalized_query_topics),
            "specific_query_topics": list(self.specific_query_topics),
            "query_mode": self.query_mode,
            "current_state_oriented": self.current_state_oriented,
            "historical_state_oriented": self.historical_state_oriented,
            "broad_inventory": self.broad_inventory,
            "top_k": self.top_k,
            "candidates": [candidate.to_dict() for candidate in self.candidates],
        }


@dataclass
class SelfReflectionResult:
    reflection_needed: bool
    memory_alignment: str
    preference_alignment: str
    active_decision_alignment: str
    superseded_memory_risk: str
    unsupported_claims_risk: str
    overall_confidence: str
    warnings: list[str] = field(default_factory=list)
    suggested_next_turn_adjustments: list[str] = field(default_factory=list)
    correction_hints: list[str] = field(default_factory=list)
    should_carry_forward: bool = False
    carry_forward_scope: str = "none"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class GroundingAuditResult:
    grounding_needed: bool
    grounding_status: str
    memory_support: str
    active_decision_status: str
    superseded_memory_status: str
    unsupported_claims: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    confidence: str = "high"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class InteractionResult:
    response: str
    observer_state: ObserverState
    retrieved_memory: list[MemoryRecord]
    retrieval_trace: RetrievalTrace | None
    memory_summary: "InteractionSummary"
    working_memory_snapshot: list[MemoryRecord]
    persistent_memory_snapshot: list[MemoryRecord]
    reasoner_backend: str
    self_reflection: SelfReflectionResult | None = None
    grounding_audit: GroundingAuditResult | None = None
    previous_correction_hints: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "response": self.response,
            "observer_state": self.observer_state.to_dict(),
            "retrieved_memory": [record.to_dict() for record in self.retrieved_memory],
            "retrieval_trace": self.retrieval_trace.to_dict() if self.retrieval_trace else None,
            "memory_summary": self.memory_summary.to_dict(),
            "working_memory_snapshot": [record.to_dict() for record in self.working_memory_snapshot],
            "persistent_memory_snapshot": [record.to_dict() for record in self.persistent_memory_snapshot],
            "reasoner_backend": self.reasoner_backend,
            "self_reflection": self.self_reflection.to_dict() if self.self_reflection else None,
            "grounding_audit": self.grounding_audit.to_dict() if self.grounding_audit else None,
            "previous_correction_hints": list(self.previous_correction_hints),
        }


@dataclass
class InteractionSummary:
    memory_type: str
    content: str
    importance: float
    tags: list[str]
    should_store: bool
    stored_record_type: str | None = None
    stored_record_id: str | None = None
    should_promote_new: bool = False
    should_promote_existing: bool = False
    promoted_record_ids: list[str] = field(default_factory=list)
    storage_rationale: str = ""
    promotion_rationale: str = ""
    override_detected: bool = False
    superseded_record_ids: list[str] = field(default_factory=list)
    override_rationale: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class MemoryHygieneRecordRef:
    id: str
    layer: str
    content_preview: str
    memory_type: str
    source: str
    importance: float
    usage_count: int
    active: bool
    superseded_by: str | None
    timestamp: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class MemoryHygieneCleanupCandidate:
    id: str
    layer: str
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class MemoryHygieneDuplicateGroup:
    normalized_content: str
    records: list[MemoryHygieneRecordRef]
    keep_record_id: str
    keep_layer: str
    cleanup_candidates: list[MemoryHygieneCleanupCandidate]
    recommendation_reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "normalized_content": self.normalized_content,
            "records": [record.to_dict() for record in self.records],
            "keep_record_id": self.keep_record_id,
            "keep_layer": self.keep_layer,
            "cleanup_candidates": [candidate.to_dict() for candidate in self.cleanup_candidates],
            "recommendation_reason": self.recommendation_reason,
        }


@dataclass
class MemoryHygienePreview:
    duplicate_groups: list[MemoryHygieneDuplicateGroup]
    cleanup_candidate_count: int
    safe_to_apply: bool
    replacement_record_ids: dict[str, str] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "duplicate_groups": [group.to_dict() for group in self.duplicate_groups],
            "cleanup_candidate_count": self.cleanup_candidate_count,
            "safe_to_apply": self.safe_to_apply,
            "replacement_record_ids": dict(self.replacement_record_ids),
            "notes": list(self.notes),
        }


@dataclass
class MemoryHygieneReferenceRepair:
    record_id: str
    layer: str
    old_superseded_by: str
    new_superseded_by: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class MemoryHygieneOrphanReference:
    record_id: str
    layer: str
    content_preview: str
    memory_type: str
    missing_superseded_by: str
    candidate_record_id: str | None
    candidate_layer: str | None
    candidate_content_preview: str | None
    shared_topics: list[str]
    auto_repairable: bool
    confidence: str
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class MemoryHygieneReferenceRepairPreview:
    orphaned_references: list[MemoryHygieneOrphanReference]
    repairable_count: int
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "orphaned_references": [reference.to_dict() for reference in self.orphaned_references],
            "repairable_count": self.repairable_count,
            "notes": list(self.notes),
        }


@dataclass
class MemoryHygieneReferenceRepairApplyResult:
    preview: MemoryHygieneReferenceRepairPreview
    repaired_superseded_by_refs: list[MemoryHygieneReferenceRepair] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "preview": self.preview.to_dict(),
            "repaired_superseded_by_refs": [repair.to_dict() for repair in self.repaired_superseded_by_refs],
        }


@dataclass
class MemoryHygieneApplyResult:
    preview: MemoryHygienePreview
    removed_working_ids: list[str]
    removed_persistent_ids: list[str]
    repaired_superseded_by_refs: list[MemoryHygieneReferenceRepair] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "preview": self.preview.to_dict(),
            "removed_working_ids": list(self.removed_working_ids),
            "removed_persistent_ids": list(self.removed_persistent_ids),
            "repaired_superseded_by_refs": [repair.to_dict() for repair in self.repaired_superseded_by_refs],
        }
