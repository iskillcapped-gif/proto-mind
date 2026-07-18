from __future__ import annotations

from proto_mind.cognitive_signals import (
    CURRENT_DECISION_MARKERS,
    CURRENT_IMPLEMENTATION_MARKERS,
    HISTORICAL_MARKERS,
    MEMORY_CLAIM_MARKERS,
    decision_current_system,
    has_historical_phrasing,
    makes_memory_claim,
    signal_terms,
    term_is_rejected_alternative,
    term_present_as_asserted,
    term_shares_marker_clause,
)
from proto_mind.models import GroundingAuditResult, MemoryRecord, ObserverState, RetrievalTrace


class GroundingAuditor:
    """Deterministic audit for memory grounding on memory-sensitive turns."""

    HISTORICAL_MARKERS = HISTORICAL_MARKERS
    MEMORY_CLAIM_MARKERS = MEMORY_CLAIM_MARKERS
    CURRENT_DECISION_MARKERS = CURRENT_DECISION_MARKERS
    CURRENT_IMPLEMENTATION_MARKERS = CURRENT_IMPLEMENTATION_MARKERS

    def audit(
        self,
        *,
        user_input: str,
        response: str,
        observer_state: ObserverState,
        retrieved_memory: list[MemoryRecord],
        retrieval_trace: RetrievalTrace | None,
        working_memory: list[MemoryRecord],
        persistent_memory: list[MemoryRecord],
    ) -> GroundingAuditResult:
        all_memory = working_memory + persistent_memory
        response_lower = response.lower()
        grounding_needed = self._grounding_needed(
            response_lower=response_lower,
            observer_state=observer_state,
            retrieved_memory=retrieved_memory,
        )
        if not grounding_needed:
            return GroundingAuditResult(
                grounding_needed=False,
                grounding_status="not_needed",
                memory_support="none_needed",
                active_decision_status="not_applicable",
                superseded_memory_status="not_applicable",
                confidence="high",
            )

        warnings: list[str] = []
        unsupported_claims: list[str] = []
        evidence: list[str] = []

        memory_support = self._memory_support(
            response=response,
            retrieved_memory=retrieved_memory,
            warnings=warnings,
            evidence=evidence,
        )
        active_decision_status = self._active_decision_status(
            response_lower=response_lower,
            all_memory=all_memory,
            warnings=warnings,
            evidence=evidence,
        )
        superseded_memory_status = self._superseded_memory_status(
            response_lower=response_lower,
            retrieved_memory=retrieved_memory,
            all_memory=all_memory,
            retrieval_trace=retrieval_trace,
            warnings=warnings,
            evidence=evidence,
        )
        unsupported_claims = self._unsupported_claims(
            response_lower=response_lower,
            retrieved_memory=retrieved_memory,
            all_memory=all_memory,
            unsupported_claims=unsupported_claims,
            warnings=warnings,
            evidence=evidence,
        )

        grounding_status = self._grounding_status(
            memory_support=memory_support,
            active_decision_status=active_decision_status,
            superseded_memory_status=superseded_memory_status,
            unsupported_claims=unsupported_claims,
        )
        return GroundingAuditResult(
            grounding_needed=True,
            grounding_status=grounding_status,
            memory_support=memory_support,
            active_decision_status=active_decision_status,
            superseded_memory_status=superseded_memory_status,
            unsupported_claims=self._dedupe(unsupported_claims),
            warnings=self._dedupe(warnings),
            evidence=self._dedupe(evidence),
            confidence=self._confidence(grounding_status, warnings),
        )

    def _grounding_needed(
        self,
        *,
        response_lower: str,
        observer_state: ObserverState,
        retrieved_memory: list[MemoryRecord],
    ) -> bool:
        if observer_state.needs_memory:
            return True
        if observer_state.query_type in {"memory_inventory", "continuity_followup"}:
            return True
        if retrieved_memory and self._makes_memory_claim(response_lower):
            return True
        return False

    def _memory_support(
        self,
        *,
        response: str,
        retrieved_memory: list[MemoryRecord],
        warnings: list[str],
        evidence: list[str],
    ) -> str:
        if not retrieved_memory:
            warnings.append("Grounding was needed, but no selected memory was available.")
            return "insufficient_selected_memory"

        important = [record for record in retrieved_memory if record.importance >= 0.75]
        candidates = important or retrieved_memory[:2]
        used = [record for record in candidates if self._response_reflects_record(response, record)]
        if used:
            evidence.append(self._memory_evidence("Response overlaps selected memory", used[0]))
            return "selected_memory_used"

        warnings.append("Response may ignore selected memory despite grounding-sensitive context.")
        return "selected_memory_ignored"

    def _active_decision_status(
        self,
        *,
        response_lower: str,
        all_memory: list[MemoryRecord],
        warnings: list[str],
        evidence: list[str],
    ) -> str:
        active_storage = [record for record in all_memory if record.type == "decision" and record.active and self._decision_current_system(record)]
        if not active_storage:
            return "not_applicable"

        for decision in active_storage:
            current_system = self._decision_current_system(decision)
            if current_system == "sqlite" and self._claims_json_as_current_architecture(response_lower):
                warnings.append("Response contradicts active SQLite decision by presenting JSON as the current architectural decision.")
                evidence.append(self._memory_evidence("Active decision", decision))
                return "contradicted"
            if current_system == "json" and self._claims_sqlite_as_current_architecture(response_lower):
                warnings.append("Response contradicts active JSON decision by presenting SQLite as the current architectural decision.")
                evidence.append(self._memory_evidence("Active decision", decision))
                return "contradicted"

        evidence.append("Response does not contradict active storage decision.")
        return "aligned"

    def _superseded_memory_status(
        self,
        *,
        response_lower: str,
        retrieved_memory: list[MemoryRecord],
        all_memory: list[MemoryRecord],
        retrieval_trace: RetrievalTrace | None,
        warnings: list[str],
        evidence: list[str],
    ) -> str:
        superseded = [record for record in all_memory if record.type == "decision" and not record.active]
        if not superseded:
            return "not_applicable"

        historical_query = bool(
            retrieval_trace and retrieval_trace.historical_state_oriented
        )
        historical_phrasing = self._has_historical_phrasing(response_lower)
        for record in superseded:
            if not self._response_mentions_decision_system(response_lower, record):
                continue
            if historical_query or historical_phrasing:
                evidence.append(self._memory_evidence("Superseded memory treated historically", record))
                return "historical_only"
            warnings.append("Response appears to present superseded memory as current.")
            evidence.append(self._memory_evidence("Superseded decision", record))
            return "treated_as_current"

        if any(not record.active for record in retrieved_memory):
            return "historical_only" if historical_query or historical_phrasing else "not_applicable"
        return "not_applicable"

    def _unsupported_claims(
        self,
        *,
        response_lower: str,
        retrieved_memory: list[MemoryRecord],
        all_memory: list[MemoryRecord],
        unsupported_claims: list[str],
        warnings: list[str],
        evidence: list[str],
    ) -> list[str]:
        claim_markers = [marker for marker in self.MEMORY_CLAIM_MARKERS if marker in response_lower]
        if not claim_markers:
            return unsupported_claims

        if retrieved_memory:
            evidence.append("Memory/project claim has selected memory context.")
            return unsupported_claims

        supporting_record = self._memory_snapshot_supporting_claim(response_lower, all_memory)
        if supporting_record:
            evidence.append(self._memory_evidence("Memory/project claim has stored support", supporting_record))
            return unsupported_claims

        claim = f"Unsupported memory/project claim marker: {claim_markers[0]}"
        unsupported_claims.append(claim)
        warnings.append("Response made a memory/project claim without selected or stored support.")
        return unsupported_claims

    def _memory_snapshot_supporting_claim(
        self,
        response_lower: str,
        all_memory: list[MemoryRecord],
    ) -> MemoryRecord | None:
        for record in all_memory:
            if self._signal_terms(record.content) & self._signal_terms(response_lower):
                return record
        return None

    def _response_reflects_record(self, response: str, record: MemoryRecord) -> bool:
        response_terms = self._signal_terms(response)
        record_terms = self._signal_terms(record.content)
        if not record_terms:
            return True
        return bool(response_terms & record_terms)

    def _claims_json_as_current_architecture(self, response_lower: str) -> bool:
        if "json" not in response_lower:
            return False
        return self._term_shares_current_clause(response_lower, "json")

    def _claims_sqlite_as_current_architecture(self, response_lower: str) -> bool:
        if "sqlite" not in response_lower:
            return False
        return self._term_shares_current_clause(response_lower, "sqlite")

    def _claims_current_implementation_json(self, response_lower: str) -> bool:
        return "json" in response_lower and any(marker in response_lower for marker in self.CURRENT_IMPLEMENTATION_MARKERS)

    def _response_mentions_decision_system(self, response_lower: str, record: MemoryRecord) -> bool:
        current_system = self._decision_current_system(record)
        if current_system and self._term_present_as_asserted(response_lower, current_system):
            return True
        lowered = record.content.lower()
        return (
            "json" in lowered and self._term_present_as_asserted(response_lower, "json")
        ) or (
            "sqlite" in lowered and self._term_present_as_asserted(response_lower, "sqlite")
        )

    def _has_historical_phrasing(self, response_lower: str) -> bool:
        return has_historical_phrasing(response_lower)

    def _makes_memory_claim(self, response_lower: str) -> bool:
        return makes_memory_claim(response_lower)

    def _term_shares_current_clause(self, response_lower: str, term: str) -> bool:
        return term_shares_marker_clause(response_lower, term, self.CURRENT_DECISION_MARKERS)

    @staticmethod
    def _term_is_rejected_alternative(clause: str, term: str) -> bool:
        return term_is_rejected_alternative(clause, term)

    def _term_present_as_asserted(self, response_lower: str, term: str) -> bool:
        return term_present_as_asserted(response_lower, term)

    @staticmethod
    def _decision_current_system(record: MemoryRecord) -> str | None:
        return decision_current_system(record.content)

    @staticmethod
    def _signal_terms(text: str) -> set[str]:
        return signal_terms(text)

    @staticmethod
    def _memory_evidence(label: str, record: MemoryRecord) -> str:
        return (
            f"{label} [id={record.id}, type={record.type}, source={record.source}]: "
            f"{GroundingAuditor._preview(record.content)}"
        )

    @staticmethod
    def _grounding_status(
        *,
        memory_support: str,
        active_decision_status: str,
        superseded_memory_status: str,
        unsupported_claims: list[str],
    ) -> str:
        if active_decision_status == "contradicted" or superseded_memory_status == "treated_as_current":
            return "contradicted"
        if unsupported_claims:
            return "ungrounded"
        if memory_support == "selected_memory_ignored":
            return "partially_grounded"
        if memory_support == "insufficient_selected_memory":
            return "ungrounded"
        return "grounded"

    @staticmethod
    def _confidence(grounding_status: str, warnings: list[str]) -> str:
        if grounding_status in {"grounded", "not_needed"} and not warnings:
            return "high"
        if grounding_status == "contradicted":
            return "high"
        if warnings:
            return "medium"
        return "high"

    @staticmethod
    def _preview(content: str, limit: int = 112) -> str:
        normalized = " ".join(content.split())
        if len(normalized) <= limit:
            return normalized
        return normalized[: limit - 3] + "..."

    @staticmethod
    def _dedupe(items: list[str]) -> list[str]:
        deduped: list[str] = []
        seen: set[str] = set()
        for item in items:
            if item not in seen:
                deduped.append(item)
                seen.add(item)
        return deduped
