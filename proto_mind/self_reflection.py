from __future__ import annotations

from proto_mind.cognitive_signals import (
    CURRENT_STATE_MARKERS,
    HISTORICAL_MARKERS,
    MEMORY_CLAIM_MARKERS,
    decision_current_system,
    has_historical_phrasing,
    signal_terms,
    term_is_rejected_alternative,
    term_shares_marker_clause,
)
from proto_mind.models import (
    InteractionSummary,
    MemoryRecord,
    ObserverState,
    RetrievalTrace,
    SelfReflectionResult,
)
from proto_mind.topic_utils import extract_topic_tags


class SelfReflector:
    """Rule-based post-turn inspection for memory and preference faithfulness."""

    HISTORICAL_MARKERS = HISTORICAL_MARKERS
    CURRENT_MARKERS = CURRENT_STATE_MARKERS
    UNSUPPORTED_MEMORY_MARKERS = MEMORY_CLAIM_MARKERS

    def reflect(
        self,
        *,
        user_input: str,
        response: str,
        observer_state: ObserverState,
        retrieved_memory: list[MemoryRecord],
        retrieval_trace: RetrievalTrace | None,
        memory_summary: InteractionSummary,
        working_memory: list[MemoryRecord],
        persistent_memory: list[MemoryRecord],
    ) -> SelfReflectionResult:
        warnings: list[str] = []
        adjustments: list[str] = []
        all_memory = working_memory + persistent_memory

        memory_alignment = self._memory_alignment(
            response=response,
            observer_state=observer_state,
            retrieved_memory=retrieved_memory,
            warnings=warnings,
            adjustments=adjustments,
        )
        preference_alignment = self._preference_alignment(
            response=response,
            retrieved_memory=retrieved_memory,
            all_memory=all_memory,
            warnings=warnings,
            adjustments=adjustments,
        )
        active_decision_alignment = self._active_decision_alignment(
            response=response,
            all_memory=all_memory,
            warnings=warnings,
            adjustments=adjustments,
        )
        superseded_memory_risk = self._superseded_memory_risk(
            response=response,
            all_memory=all_memory,
            warnings=warnings,
            adjustments=adjustments,
        )
        unsupported_claims_risk = self._unsupported_claims_risk(
            response=response,
            observer_state=observer_state,
            retrieved_memory=retrieved_memory,
            warnings=warnings,
            adjustments=adjustments,
        )

        if retrieval_trace and retrieval_trace.candidates and not retrieved_memory:
            warnings.append("Retrieval considered candidates, but none were selected for the final response.")
            adjustments.append("If continuity was expected, inspect retrieval thresholds and topic specificity.")

        if memory_summary.override_detected and not memory_summary.superseded_record_ids:
            adjustments.append("If this override should replace prior decisions, inspect topic overlap for superseding.")

        correction_hints = self._correction_hints(
            response=response,
            warnings=warnings,
            retrieved_memory=retrieved_memory,
            all_memory=all_memory,
        )

        return SelfReflectionResult(
            reflection_needed=bool(retrieved_memory or warnings or observer_state.needs_memory),
            memory_alignment=memory_alignment,
            preference_alignment=preference_alignment,
            active_decision_alignment=active_decision_alignment,
            superseded_memory_risk=superseded_memory_risk,
            unsupported_claims_risk=unsupported_claims_risk,
            overall_confidence=self._overall_confidence(warnings),
            warnings=self._dedupe(warnings),
            suggested_next_turn_adjustments=self._dedupe(adjustments),
            correction_hints=correction_hints,
            should_carry_forward=bool(correction_hints),
            carry_forward_scope="next_turn" if correction_hints else "none",
        )

    def _memory_alignment(
        self,
        *,
        response: str,
        observer_state: ObserverState,
        retrieved_memory: list[MemoryRecord],
        warnings: list[str],
        adjustments: list[str],
    ) -> str:
        if not retrieved_memory:
            return "neutral"

        important = [record for record in retrieved_memory if record.active and record.importance >= 0.75]
        if not important:
            return "ok"

        ignored = [
            record
            for record in important[:3]
            if not self._response_reflects_record(response, record)
        ]
        if ignored and observer_state.needs_memory:
            warnings.append("Response may have ignored important selected memory.")
            adjustments.append("On the next related turn, explicitly ground the answer in the top selected memory.")
            return "warning"
        return "ok"

    def _preference_alignment(
        self,
        *,
        response: str,
        retrieved_memory: list[MemoryRecord],
        all_memory: list[MemoryRecord],
        warnings: list[str],
        adjustments: list[str],
    ) -> str:
        active_preferences = [record for record in all_memory if record.type == "preference" and record.active]
        selected_preferences = [record for record in retrieved_memory if record.type == "preference" and record.active]
        relevant_preferences = selected_preferences or active_preferences
        if not relevant_preferences:
            return "neutral"

        word_count = len(response.split())
        for preference in relevant_preferences:
            preference_topics = set(extract_topic_tags(preference.content))
            if preference_topics.intersection({"short", "concise"}) and word_count > 140:
                warnings.append("Response may not respect the active preference for concise or short answers.")
                adjustments.append("Keep future explanations more concise unless the user asks for depth.")
                return "warning"
        return "ok"

    def _active_decision_alignment(
        self,
        *,
        response: str,
        all_memory: list[MemoryRecord],
        warnings: list[str],
        adjustments: list[str],
    ) -> str:
        active_decisions = [record for record in all_memory if record.type == "decision" and record.active]
        if not active_decisions:
            return "neutral"

        response_lower = response.lower()
        for decision in active_decisions:
            current_system = self._decision_current_system(decision)
            if current_system == "sqlite" and self._claims_current_json(response_lower):
                warnings.append("Response appears to contradict the active SQLite decision by treating JSON as current.")
                adjustments.append("Prefer the active SQLite decision when answering current storage questions.")
                return "warning"
            if current_system == "json" and self._claims_current_sqlite(response_lower):
                warnings.append("Response appears to contradict the active JSON decision by treating SQLite as current.")
                adjustments.append("Prefer the active JSON decision unless a newer override is stored.")
                return "warning"
        return "ok"

    def _superseded_memory_risk(
        self,
        *,
        response: str,
        all_memory: list[MemoryRecord],
        warnings: list[str],
        adjustments: list[str],
    ) -> str:
        superseded_decisions = [record for record in all_memory if record.type == "decision" and not record.active]
        if not superseded_decisions:
            return "low"

        response_lower = response.lower()
        for decision in superseded_decisions:
            decision_lower = decision.content.lower()
            if "json" in decision_lower and self._claims_current_json(response_lower):
                warnings.append("Response may be treating a superseded JSON decision as current.")
                adjustments.append("Separate historical JSON decisions from the current active decision on the next turn.")
                return "high"
            if "sqlite" in decision_lower and self._claims_current_sqlite(response_lower):
                warnings.append("Response may be treating a superseded SQLite decision as current.")
                adjustments.append("Separate historical SQLite decisions from the current active decision on the next turn.")
                return "high"
        return "low"

    def _unsupported_claims_risk(
        self,
        *,
        response: str,
        observer_state: ObserverState,
        retrieved_memory: list[MemoryRecord],
        warnings: list[str],
        adjustments: list[str],
    ) -> str:
        response_lower = response.lower()
        makes_memory_claim = any(marker in response_lower for marker in self.UNSUPPORTED_MEMORY_MARKERS)
        if observer_state.needs_memory and not retrieved_memory and makes_memory_claim:
            warnings.append("Response made memory/project claims even though no relevant memory was selected.")
            adjustments.append("When memory retrieval returns nothing, say so instead of inventing current memory state.")
            return "high"
        if observer_state.query_type == "memory_inventory" and not retrieved_memory:
            return "low"
        return "low"

    def _response_reflects_record(self, response: str, record: MemoryRecord) -> bool:
        response_terms = self._signal_terms(response)
        record_terms = self._signal_terms(record.content)
        if not record_terms:
            return True
        return bool(response_terms & record_terms)

    def _correction_hints(
        self,
        *,
        response: str,
        warnings: list[str],
        retrieved_memory: list[MemoryRecord],
        all_memory: list[MemoryRecord],
    ) -> list[str]:
        hints: list[str] = []
        warning_text = " ".join(warnings).lower()
        if "active sqlite decision" in warning_text or "active json decision" in warning_text:
            active_decision = self._active_storage_decision(all_memory)
            if active_decision:
                hints.append(f"Use the active decision as current state: {self._preview(active_decision.content)}")

        if "superseded" in warning_text:
            superseded = self._mentioned_superseded_memory(response, all_memory)
            if superseded:
                hints.append(f"Treat superseded memory as historical only: {self._preview(superseded.content)}")

        if "preference" in warning_text:
            preference = next((record for record in all_memory if record.type == "preference" and record.active), None)
            if preference:
                hints.append(f"Respect active preference next turn: {self._preview(preference.content)}")

        if "unsupported" in warning_text or "no relevant memory was selected" in warning_text:
            hints.append("Avoid claiming remembered facts unless supported by selected or stored memory.")

        if "ignored important selected memory" in warning_text:
            important = next((record for record in retrieved_memory if record.active and record.importance >= 0.75), None)
            if important:
                hints.append(f"Ground the next related answer in selected memory: {self._preview(important.content)}")

        return self._dedupe(hints)

    @staticmethod
    def _active_storage_decision(all_memory: list[MemoryRecord]) -> MemoryRecord | None:
        for record in all_memory:
            if record.type != "decision" or not record.active:
                continue
            if SelfReflector._decision_current_system(record):
                return record
        return None

    @staticmethod
    def _decision_current_system(record: MemoryRecord) -> str | None:
        return decision_current_system(record.content)

    @staticmethod
    def _mentioned_superseded_memory(response: str, all_memory: list[MemoryRecord]) -> MemoryRecord | None:
        response_lower = response.lower()
        for record in all_memory:
            if record.type != "decision" or record.active:
                continue
            lowered = record.content.lower()
            if "json" in lowered and "json" in response_lower:
                return record
            if "sqlite" in lowered and "sqlite" in response_lower:
                return record
        return None

    @staticmethod
    def _signal_terms(text: str) -> set[str]:
        return signal_terms(text)

    def _claims_current_json(self, response_lower: str) -> bool:
        return self._term_shares_current_clause(response_lower, "json")

    def _claims_current_sqlite(self, response_lower: str) -> bool:
        return self._term_shares_current_clause(response_lower, "sqlite")

    def _term_shares_current_clause(self, response_lower: str, term: str) -> bool:
        return term_shares_marker_clause(response_lower, term, self.CURRENT_MARKERS)

    @staticmethod
    def _term_is_rejected_alternative(clause: str, term: str) -> bool:
        return term_is_rejected_alternative(clause, term)

    def _has_historical_phrasing(self, text: str) -> bool:
        return has_historical_phrasing(text)

    @staticmethod
    def _preview(content: str, limit: int = 112) -> str:
        normalized = " ".join(content.split())
        if len(normalized) <= limit:
            return normalized
        return normalized[: limit - 3] + "..."

    @staticmethod
    def _overall_confidence(warnings: list[str]) -> str:
        if not warnings:
            return "high"
        if len(warnings) <= 2:
            return "medium"
        return "low"

    @staticmethod
    def _dedupe(items: list[str]) -> list[str]:
        deduped: list[str] = []
        seen: set[str] = set()
        for item in items:
            if item not in seen:
                deduped.append(item)
                seen.add(item)
        return deduped
