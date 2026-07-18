from __future__ import annotations

from datetime import UTC, datetime
from math import exp

from proto_mind.models import (
    InteractionSummary,
    MemoryRecord,
    ObserverState,
    RetrievalCandidateTrace,
    RetrievalTrace,
)
from proto_mind.memory_store import MemoryStore
from proto_mind.topic_utils import extract_topic_tags, topic_weight, weighted_topic_overlap


class MemoryKeeper:
    OVERRIDE_MARKERS = (
        "actually",
        "instead",
        "changing direction",
        "we now use",
        "no longer",
        "replace",
        "на самом деле",
        "вместо",
        "меняем направление",
        "теперь используем",
        "больше не",
        "заменить",
        "переходим на",
    )
    STABLE_PREFERENCE_MARKERS = (
        "i prefer",
        "always use",
        "for future",
        "я предпочитаю",
        "всегда используй",
        "для будущего",
    )
    DECISION_STORAGE_MARKERS = (
        "we decided",
        "let's use",
        "decision",
        "we now use",
        "instead of",
        "changing direction",
        "no longer",
        "мы решили",
        "давай использовать",
        "решение",
        "теперь используем",
        "вместо",
        "меняем направление",
        "больше не",
        "переходим на",
    )
    IMPORTANT_FACT_MARKERS = (
        "remember that",
        "important fact",
        "key insight",
        "запомни, что",
        "запомни что",
        "важный факт",
        "ключевой вывод",
    )

    def __init__(self, store: MemoryStore) -> None:
        self.store = store
        self.last_retrieval_trace: RetrievalTrace | None = None

    def retrieve(
        self,
        observer_state: ObserverState,
        top_k: int = 5,
        user_input: str = "",
        *,
        track_usage: bool = False,
    ) -> list[MemoryRecord]:
        working = self.store.load_working_memory()
        persistent = self.store.load_persistent_memory()
        scored: list[tuple[float, MemoryRecord]] = []
        candidate_traces: list[RetrievalCandidateTrace] = []
        specific_query_topics = [tag for tag in observer_state.topic_tags if topic_weight(tag) >= 0.6]
        query_mode = self._query_mode(observer_state)
        for record in working + persistent:
            breakdown = self._score_breakdown(record, observer_state)
            candidate = RetrievalCandidateTrace(
                record_id=record.id,
                content_preview=self._preview(record.content),
                memory_type=record.type,
                active=record.active,
                stored_tags=list(record.tags),
                normalized_topics=breakdown["record_topics"],
                matched_topics=breakdown["matched_topics"],
                topical_score=breakdown["topical_score"],
                topical_contribution=breakdown["topical_contribution"],
                importance_contribution=breakdown["importance_contribution"],
                recency_contribution=breakdown["recency_contribution"],
                usage_contribution=breakdown["usage_contribution"],
                state_bias_contribution=breakdown["state_bias_contribution"],
                final_total_score=breakdown["final_total_score"],
                preference_priority_contribution=breakdown["preference_priority_contribution"],
            )
            if specific_query_topics and not self._has_specific_topic_overlap(record, specific_query_topics):
                candidate.filtered_reason = "filtered_no_specific_topic_overlap"
                candidate_traces.append(candidate)
                continue
            score = breakdown["final_total_score"]
            if score >= 0.2:
                scored.append((score, record))
            else:
                candidate.filtered_reason = "filtered_below_threshold"
            candidate_traces.append(candidate)
        deduped: dict[str, tuple[float, MemoryRecord]] = {}
        candidate_by_id = {candidate.record_id: candidate for candidate in candidate_traces}
        for score, record in scored:
            key = self._normalize_content(record.content)
            current = deduped.get(key)
            if current is None or score > current[0]:
                if current is not None:
                    replaced = candidate_by_id.get(current[1].id)
                    if replaced and not replaced.selected:
                        replaced.filtered_reason = "deduped_by_content"
                deduped[key] = (score, record)
            else:
                candidate = candidate_by_id.get(record.id)
                if candidate and not candidate.selected:
                    candidate.filtered_reason = "deduped_by_content"
        selected = [record for _, record in sorted(deduped.values(), key=lambda item: item[0], reverse=True)[:top_k]]
        for rank, record in enumerate(selected, start=1):
            candidate = candidate_by_id.get(record.id)
            if candidate:
                candidate.selected = True
                candidate.selected_rank = rank
                candidate.filtered_reason = None
        self._annotate_candidate_explanations(
            candidate_traces=candidate_traces,
            observer_state=observer_state,
            specific_query_topics=specific_query_topics,
        )
        if track_usage:
            self.record_retrieval_usage(selected)
        self.last_retrieval_trace = RetrievalTrace(
            user_input=user_input,
            query_type=observer_state.query_type,
            normalized_query_topics=list(observer_state.topic_tags),
            specific_query_topics=specific_query_topics,
            query_mode=query_mode,
            current_state_oriented="current" in observer_state.topic_tags or observer_state.query_type == "memory_inventory",
            historical_state_oriented=self._historical_state_oriented(observer_state),
            broad_inventory=observer_state.query_type == "memory_inventory",
            top_k=top_k,
            candidates=sorted(candidate_traces, key=lambda item: item.final_total_score, reverse=True),
        )
        return selected

    def score_record(self, record: MemoryRecord, observer_state: ObserverState) -> float:
        return self._score_breakdown(record, observer_state)["final_total_score"]

    def _score_breakdown(self, record: MemoryRecord, observer_state: ObserverState) -> dict[str, object]:
        query_tags = observer_state.topic_tags
        record_topics = self._record_topics(record)
        tag_match = weighted_topic_overlap(record_topics, query_tags)
        importance = max(0.0, min(record.importance * record.weight, 1.0))
        if not record.active:
            importance *= 0.35
        recency = self._recency_score(record.last_used or record.timestamp)
        usage_relevance = min(record.usage_count / 5, 1.0)
        state_alignment = self._state_alignment(record, observer_state)
        preference_priority = self._preference_priority(record, observer_state, record_topics)
        topical_contribution = round(tag_match * 0.45, 4)
        importance_contribution = round(importance * 0.25, 4)
        recency_contribution = round(recency * 0.15, 4)
        usage_contribution = round(usage_relevance * 0.25, 4)
        final_total_score = round(
            topical_contribution
            + importance_contribution
            + recency_contribution
            + usage_contribution
            + state_alignment
            + preference_priority,
            4,
        )
        return {
            "record_topics": record_topics,
            "matched_topics": sorted(set(record_topics) & set(query_tags)),
            "topical_score": tag_match,
            "topical_contribution": topical_contribution,
            "importance_contribution": importance_contribution,
            "recency_contribution": recency_contribution,
            "usage_contribution": usage_contribution,
            "state_bias_contribution": round(state_alignment, 4),
            "preference_priority_contribution": round(preference_priority, 4),
            "final_total_score": final_total_score,
        }

    def evaluate_interaction(
        self,
        user_input: str,
        response: str,
        observer_state: ObserverState,
        retrieved_memory: list[MemoryRecord],
    ) -> InteractionSummary:
        lowered = user_input.lower()
        stable_preference = observer_state.query_type == "personal_context" and any(
            phrase in lowered for phrase in self.STABLE_PREFERENCE_MARKERS
        ) and not self._is_recall_question(lowered)
        decision = observer_state.query_type == "decision_request" and any(
            phrase in lowered for phrase in self.DECISION_STORAGE_MARKERS
        )
        important_fact = any(phrase in lowered for phrase in self.IMPORTANT_FACT_MARKERS)
        should_store = stable_preference or decision or important_fact
        preference_style_retrieval = observer_state.needs_memory and self._is_preference_style_query(observer_state)
        if not should_store and observer_state.query_type == "project_context" and observer_state.importance_hint >= 0.8 and not preference_style_retrieval:
            should_store = True

        memory_type = "insight"
        if stable_preference:
            memory_type = "preference"
        elif decision:
            memory_type = "decision"
        elif observer_state.query_type == "project_context":
            memory_type = "project"

        content = self._build_memory_content(user_input, response, memory_type)
        importance = max(observer_state.importance_hint, 0.55 if should_store else 0.3)
        override_detected = decision and any(marker in lowered for marker in self.OVERRIDE_MARKERS)
        storage_rationale = self._storage_rationale(
            should_store=should_store,
            memory_type=memory_type,
            observer_state=observer_state,
            stable_preference=stable_preference,
            decision=decision,
            important_fact=important_fact,
            override_detected=override_detected,
        )
        should_promote_existing = (
            not should_store
            and observer_state.query_type in {"continuity_followup", "memory_inventory"}
            and any(record.usage_count >= 2 and record.active for record in retrieved_memory)
        )
        return InteractionSummary(
            memory_type=memory_type,
            content=content,
            importance=min(importance, 1.0),
            tags=observer_state.topic_tags,
            should_store=should_store,
            stored_record_type=memory_type if should_store else None,
            should_promote_new=should_store and memory_type in {"decision", "preference"},
            should_promote_existing=should_promote_existing,
            storage_rationale=storage_rationale,
            promotion_rationale="Awaiting memory update application." if (should_store or should_promote_existing) else "No promotion needed.",
            override_detected=override_detected,
            override_rationale="Override detected in current decision." if override_detected else "No override detected.",
        )

    def apply_memory_updates(
        self,
        summary: InteractionSummary,
        retrieved_memory: list[MemoryRecord] | None = None,
    ) -> InteractionSummary:
        self._decay_working_memory()
        if not summary.should_store:
            if summary.should_promote_existing:
                promoted_ids = self._promote_retrieved_records(retrieved_memory or [])
                summary.promoted_record_ids = promoted_ids
                if promoted_ids:
                    summary.promotion_rationale = "Promoted existing memory because it has been reused multiple times."
                else:
                    summary.should_promote_existing = False
                    summary.promotion_rationale = "No existing memory was eligible for promotion."
            else:
                summary.promotion_rationale = "No promotion happened for this retrieval turn."
            return summary

        existing_working = self.store.load_working_memory()
        matching = self._find_similar(existing_working, summary.content)
        if matching:
            matching.importance = max(matching.importance, summary.importance)
            matching.tags = sorted(set(matching.tags + summary.tags))
            self.store.upsert_working_record(matching)
            summary.stored_record_id = matching.id
            summary.stored_record_type = matching.type
            if summary.override_detected and matching.type == "decision":
                summary.superseded_record_ids = self._supersede_prior_decisions(matching)
                summary.override_rationale = (
                    "Superseded prior active decisions with overlapping topics."
                    if summary.superseded_record_ids
                    else "Override detected, but no prior active decisions matched."
                )
            if summary.should_promote_new and self._should_promote_record(matching):
                summary.promoted_record_ids = self._promote(matching)
                summary.promotion_rationale = "Promoted because this new memory is a durable decision or preference."
            else:
                summary.should_promote_new = False
                summary.promotion_rationale = "Stored in working memory only."
            return summary

        record = MemoryRecord(
            content=summary.content,
            type=summary.memory_type,
            importance=summary.importance,
            source="interaction",
            tags=summary.tags,
        )
        self.store.add_working_record(record)
        summary.stored_record_id = record.id
        summary.stored_record_type = record.type
        if summary.override_detected and record.type == "decision":
            summary.superseded_record_ids = self._supersede_prior_decisions(record)
            summary.override_rationale = (
                "Superseded prior active decisions with overlapping topics."
                if summary.superseded_record_ids
                else "Override detected, but no prior active decisions matched."
            )
        if summary.should_promote_new and self._should_promote_record(record):
            summary.promoted_record_ids = self._promote(record)
            summary.promotion_rationale = "Promoted because this new memory is a durable decision or preference."
        else:
            summary.should_promote_new = False
            summary.promotion_rationale = "Stored in working memory only."
        return summary

    def record_retrieval_usage(self, selected: list[MemoryRecord]) -> None:
        working = self.store.load_working_memory()
        persistent = self.store.load_persistent_memory()
        working_map = {record.id: record for record in working}
        persistent_map = {record.id: record for record in persistent}
        working_changed = False
        persistent_changed = False
        for record in selected:
            if record.id in working_map:
                working_map[record.id].touch()
                working_changed = True
            if record.id in persistent_map:
                persistent_map[record.id].touch()
                persistent_changed = True
        if working_changed:
            self.store.save_working_memory(list(working_map.values()))
        if persistent_changed:
            self.store.save_persistent_memory(list(persistent_map.values()))

    def _build_memory_content(self, user_input: str, response: str, memory_type: str) -> str:
        return user_input.strip()

    def _should_promote_record(self, record: MemoryRecord) -> bool:
        return record.importance >= 0.85 or record.type in {"decision", "preference"}

    def _promote(self, record: MemoryRecord) -> list[str]:
        persistent = self.store.load_persistent_memory()
        existing = self._find_similar(persistent, record.content)
        if existing:
            existing.importance = max(existing.importance, record.importance)
            existing.tags = sorted(set(existing.tags + record.tags))
            existing.active = record.active
            existing.superseded_by = record.superseded_by
            existing.superseded_at = record.superseded_at
            existing.superseded_reason = record.superseded_reason
            self.store.upsert_persistent_record(existing)
            return [existing.id]

        promoted = MemoryRecord(
            content=record.content,
            type=record.type,
            importance=record.importance,
            source="promoted",
            tags=record.tags,
            usage_count=record.usage_count,
            last_used=record.last_used,
        )
        self.store.add_persistent_record(promoted)
        return [promoted.id]

    def _promote_retrieved_records(self, retrieved_memory: list[MemoryRecord]) -> list[str]:
        promoted_ids: list[str] = []
        persistent = self.store.load_persistent_memory()
        for record in retrieved_memory:
            if record.usage_count < 2 or record.type not in {"decision", "preference", "insight", "project"} or not record.active:
                continue
            if self._find_similar(persistent, record.content):
                continue
            promoted_ids.extend(self._promote(record))
            persistent = self.store.load_persistent_memory()
        return promoted_ids

    def _supersede_prior_decisions(self, new_record: MemoryRecord) -> list[str]:
        superseded_ids: list[str] = []
        for loader, saver in (
            (self.store.load_working_memory, self.store.save_working_memory),
            (self.store.load_persistent_memory, self.store.save_persistent_memory),
        ):
            records = loader()
            changed = False
            for record in records:
                if record.id == new_record.id or record.type != "decision" or not record.active:
                    continue
                if not self._decisions_conflict(record, new_record):
                    continue
                record.active = False
                record.superseded_by = new_record.id
                record.superseded_at = datetime.now(UTC).isoformat()
                record.superseded_reason = "Superseded by a newer explicit decision."
                superseded_ids.append(record.id)
                changed = True
            if changed:
                saver(records)
        return superseded_ids

    @staticmethod
    def _decisions_conflict(existing: MemoryRecord, new_record: MemoryRecord) -> bool:
        if existing.type != "decision" or new_record.type != "decision":
            return False
        existing_tags = set(existing.tags)
        new_tags = set(new_record.tags)
        lowered = new_record.content.lower()
        return bool(existing_tags & new_tags) or "instead of" in lowered or "вместо" in lowered

    def _decay_working_memory(self) -> None:
        records = self.store.load_working_memory()
        changed = False
        for record in records:
            score = self._recency_score(record.last_used or record.timestamp)
            if score < 0.3 and record.usage_count == 0:
                record.weight = max(0.4, round(record.weight - 0.05, 2))
                changed = True
        if changed:
            self.store.save_working_memory(records)

    @staticmethod
    def _find_similar(records: list[MemoryRecord], content: str) -> MemoryRecord | None:
        normalized = MemoryKeeper._normalize_content(content)
        for record in records:
            if MemoryKeeper._normalize_content(record.content) == normalized:
                return record
        return None

    @staticmethod
    def _normalize_content(content: str) -> str:
        return " ".join(content.lower().split())

    @staticmethod
    def _record_topics(record: MemoryRecord) -> list[str]:
        content_topics = extract_topic_tags(record.content)
        merged: list[str] = []
        seen: set[str] = set()
        for tag in record.tags + content_topics:
            if tag not in seen:
                merged.append(tag)
                seen.add(tag)
        return merged

    def _state_alignment(self, record: MemoryRecord, observer_state: ObserverState) -> float:
        query_tags = set(observer_state.topic_tags)
        wants_history = self._historical_state_oriented(observer_state)
        wants_current = "current" in query_tags or observer_state.query_type == "memory_inventory"
        wants_preference_behavior = bool(query_tags & {"future_behavior", "response_style", "style", "explanation"})

        if wants_history and not record.active:
            base = 0.18
        elif wants_history and record.active:
            base = -0.05
        elif wants_current and record.active:
            base = 0.12
        elif wants_current and not record.active:
            base = -0.12
        else:
            base = 0.08 if record.active else -0.08

        if wants_preference_behavior and record.type == "preference":
            base += 0.14 if record.active else 0.05
        elif wants_preference_behavior and record.type == "decision":
            base -= 0.04

        return round(base, 4)

    def _preference_priority(
        self,
        record: MemoryRecord,
        observer_state: ObserverState,
        record_topics: list[str],
    ) -> float:
        if not self._is_preference_style_query(observer_state):
            return 0.0

        query_tags = set(observer_state.topic_tags)
        record_topic_set = set(record_topics)
        specific_matches = {
            tag
            for tag in query_tags & record_topic_set
            if topic_weight(tag) >= 0.6
        }
        style_matches = specific_matches & {
            "response_style",
            "style",
            "explanation",
            "future_behavior",
            "concise",
            "short",
            "architecture",
        }

        if record.type == "preference":
            if not record.active:
                return -0.08
            if style_matches:
                return 0.22
            if "preference" in record_topic_set:
                return 0.12
            return 0.06

        if record.type in {"project", "insight"}:
            if style_matches and "preference" in record_topic_set:
                return -0.03
            return -0.1

        if record.type == "decision":
            return -0.06

        return 0.0

    @staticmethod
    def _is_preference_style_query(observer_state: ObserverState) -> bool:
        query_tags = set(observer_state.topic_tags)
        return bool(query_tags & {"preference", "future_behavior", "response_style", "style", "explanation", "concise", "short"})

    @staticmethod
    def _is_recall_question(text: str) -> bool:
        return "?" in text or any(
            text.strip().startswith(prefix)
            for prefix in ("what ", "how ", "which ", "do ", "did ", "что ", "как ", "какой ", "какая ", "какие ", "помнишь ", "напомни ")
        )

    def _has_specific_topic_overlap(self, record: MemoryRecord, query_topics: list[str]) -> bool:
        record_topics = [tag for tag in self._record_topics(record) if topic_weight(tag) >= 0.6]
        return bool(set(record_topics) & set(query_topics))

    def _annotate_candidate_explanations(
        self,
        candidate_traces: list[RetrievalCandidateTrace],
        observer_state: ObserverState,
        specific_query_topics: list[str],
    ) -> None:
        current_oriented = "current" in observer_state.topic_tags or observer_state.query_type == "memory_inventory"
        historical_oriented = self._historical_state_oriented(observer_state)
        broad_inventory = observer_state.query_type == "memory_inventory"

        for candidate in candidate_traces:
            reasons: list[str] = []
            if candidate.matched_topics:
                if any(topic_weight(tag) >= 0.6 for tag in candidate.matched_topics):
                    reasons.append(f"matched specific topics {candidate.matched_topics}")
                else:
                    reasons.append(f"only matched broad topics {candidate.matched_topics}")
            else:
                reasons.append("had no topic overlap")

            if candidate.active and candidate.state_bias_contribution > 0.1 and current_oriented:
                reasons.append("benefited from active current-decision bias")
            elif (not candidate.active) and candidate.state_bias_contribution > 0.1 and historical_oriented:
                reasons.append("benefited from historical superseded-decision relevance")
            elif (not candidate.active) and candidate.state_bias_contribution < 0 and current_oriented:
                reasons.append("penalized because it is superseded for a current-oriented query")

            if candidate.filtered_reason == "filtered_no_specific_topic_overlap":
                reasons.append("lacked specific topical overlap")
            elif candidate.filtered_reason == "filtered_below_threshold":
                reasons.append("scored below the retrieval threshold")
            elif candidate.filtered_reason == "deduped_by_content":
                reasons.append("was deduped by a stronger identical memory")

            if candidate.importance_contribution >= 0.2:
                reasons.append("had strong stored importance")
            if candidate.usage_contribution >= 0.15:
                reasons.append("benefited from repeated use")
            if candidate.preference_priority_contribution > 0:
                reasons.append("received direct preference priority for this response-style query")
            elif candidate.preference_priority_contribution < 0:
                reasons.append("was deprioritized because direct preferences are preferred for response-style queries")

            if broad_inventory and candidate.filtered_reason and not candidate.matched_topics:
                reasons.append("broad inventory mode still deprioritized weak topical relevance")

            candidate.top_reasons = reasons[:3]
            if candidate.selected:
                candidate.why_selected_summary = self._selected_summary(candidate)
                candidate.why_not_selected_summary = None
            else:
                candidate.why_not_selected_summary = self._not_selected_summary(candidate, specific_query_topics)
                candidate.why_selected_summary = None

    @staticmethod
    def _selected_summary(candidate: RetrievalCandidateTrace) -> str:
        reasons: list[str] = []
        if candidate.matched_topics:
            if any(topic_weight(tag) >= 0.6 for tag in candidate.matched_topics):
                reasons.append(f"it matched specific {', '.join(candidate.matched_topics[:3])} topics")
            else:
                reasons.append("it still matched the query's broad topics")
        if candidate.preference_priority_contribution > 0 and candidate.memory_type == "preference":
            return "Won because this is an active direct preference matching a response-style query."
        if candidate.active and candidate.state_bias_contribution > 0:
            reasons.append("it is the active current memory")
        elif (not candidate.active) and candidate.state_bias_contribution > 0:
            reasons.append("the query favored historical superseded memory")
        if candidate.usage_contribution >= 0.15:
            reasons.append("it has been reused before")
        if not reasons:
            reasons.append("its overall score was strongest")
        return "Won because " + " and ".join(reasons[:2]) + "."

    @staticmethod
    def _not_selected_summary(candidate: RetrievalCandidateTrace, specific_query_topics: list[str]) -> str:
        if candidate.filtered_reason == "filtered_no_specific_topic_overlap":
            if specific_query_topics:
                return "Deprioritized because it only matched generic tags and lacked specific topical overlap."
            return "Filtered because it lacked topical overlap."
        if candidate.filtered_reason == "filtered_below_threshold":
            if candidate.matched_topics and all(topic_weight(tag) < 0.6 for tag in candidate.matched_topics):
                return "Deprioritized because it only matched broad generic topics and scored too weakly overall."
            return "Deprioritized because its overall score stayed below the retrieval threshold."
        if candidate.filtered_reason == "deduped_by_content":
            return "Filtered because identical content was already represented by a higher-ranked memory."
        if candidate.preference_priority_contribution < 0:
            return "Deprioritized because direct active preferences are preferred for response-style queries."
        if (not candidate.active) and candidate.state_bias_contribution < 0:
            return "Not selected because this query was current-oriented and this memory is superseded."
        if candidate.state_bias_contribution > 0 and not candidate.selected:
            return "Not selected because another memory had a stronger overall score despite similar relevance."
        return "Not selected because stronger candidates matched the query more specifically."

    @staticmethod
    def _query_mode(observer_state: ObserverState) -> str:
        query_tags = set(observer_state.topic_tags)
        if observer_state.query_type == "memory_inventory" and ("historical" in query_tags or "change" in query_tags):
            return "historical_inventory"
        if observer_state.query_type == "memory_inventory":
            return "broad_inventory"
        if observer_state.query_type == "continuity_followup":
            return "generic_followup"
        if "historical" in query_tags or "change" in query_tags:
            return "historical_lookup"
        if "current" in query_tags:
            return "current_state_lookup"
        return "targeted_lookup"

    @staticmethod
    def _historical_state_oriented(observer_state: ObserverState) -> bool:
        query_tags = set(observer_state.topic_tags)
        if "change" in query_tags:
            return True
        if "historical" not in query_tags:
            return False
        return observer_state.query_type != "continuity_followup"

    @staticmethod
    def _preview(content: str, limit: int = 96) -> str:
        normalized = " ".join(content.split())
        if len(normalized) <= limit:
            return normalized
        return normalized[: limit - 3] + "..."

    @staticmethod
    def _recency_score(timestamp: str) -> float:
        dt = datetime.fromisoformat(timestamp)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        age_hours = max((datetime.now(UTC) - dt).total_seconds() / 3600, 0.0)
        return round(exp(-age_hours / 72), 4)

    @staticmethod
    def _storage_rationale(
        should_store: bool,
        memory_type: str,
        observer_state: ObserverState,
        stable_preference: bool,
        decision: bool,
        important_fact: bool,
        override_detected: bool,
    ) -> str:
        if stable_preference:
            return "Stored because this is a stable preference."
        if decision and override_detected:
            return "Stored because this is a new decision that overrides prior direction."
        if decision:
            return "Stored because this is a decision that may shape future reasoning."
        if important_fact:
            return "Stored because this is marked as an important fact or insight."
        if should_store and memory_type == "project":
            return "Stored because this is a meaningful project conclusion."
        if observer_state.query_type == "memory_inventory":
            return "Not stored because this is a memory inventory question."
        if observer_state.query_type == "continuity_followup":
            return "Not stored because this is a follow-up retrieval turn."
        return "Not stored because this turn does not introduce durable new memory."
