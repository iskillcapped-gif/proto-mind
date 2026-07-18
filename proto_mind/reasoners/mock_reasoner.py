from __future__ import annotations

from proto_mind.models import MemoryRecord, ObserverState
from proto_mind.reasoners.base import BaseReasoner


class MockReasoner(BaseReasoner):
    backend_name = "mock"

    def respond(
        self,
        user_input: str,
        retrieved_memory: list[MemoryRecord],
        observer_state: ObserverState,
        correction_hints: list[str] | None = None,
    ) -> str:
        if observer_state.query_type == "memory_inventory":
            return self._memory_inventory_response(user_input, retrieved_memory, observer_state)

        memory_signal = self._summarize_memory(retrieved_memory)
        continuity_heavy = observer_state.query_type == "continuity_followup"
        declaration_heavy = observer_state.query_type in {"personal_context", "decision_request"}
        response_parts = []

        if continuity_heavy:
            response_parts.append("I’m continuing from earlier context rather than treating this as a fresh question.")
        elif observer_state.query_type == "decision_request":
            response_parts.append("I’m weighing this as a decision that may shape future behavior.")
        elif observer_state.query_type == "personal_context":
            response_parts.append("I’m treating this as user-specific context that may matter later.")
        else:
            response_parts.append("I’m answering directly while checking whether memory should shape the reply.")

        if memory_signal and continuity_heavy:
            response_parts.append(f"Relevant memory shaping this answer: {memory_signal}.")
        elif memory_signal:
            response_parts.append(f"Background memory noted but secondary for this turn: {memory_signal}.")

        response_parts.append(f"Current request: {user_input.strip()}")

        if declaration_heavy:
            response_parts.append("The new user statement is primary, so I’m treating it as the main source of truth for this turn.")

        if observer_state.query_type in {"meta_architecture", "project_context"}:
            response_parts.append(
                "For Proto-Mind v0, a clean split between observation, memory management, reasoning, and coordination keeps the MVP extensible."
            )
        elif observer_state.query_type == "decision_request":
            response_parts.append(
                "A good MVP choice is to preserve decisions and preferences in persistent memory, while letting working memory handle recent context and temporary conclusions."
            )
        elif observer_state.query_type == "personal_context":
            response_parts.append(
                "I’ll carry this forward as stable context when it looks like a preference or enduring fact."
            )
        else:
            response_parts.append(
                "The answer is being framed with the retrieved context integrated as internal state, not appended as raw notes."
            )

        return " ".join(response_parts)

    @staticmethod
    def _memory_inventory_response(
        user_input: str,
        retrieved_memory: list[MemoryRecord],
        observer_state: ObserverState,
    ) -> str:
        if not retrieved_memory:
            return "I do not currently have relevant stored memory for that question."

        lowered = user_input.lower()
        wants_history = "historical" in observer_state.topic_tags or "change" in observer_state.topic_tags or "before" in lowered
        wants_current = "current" in observer_state.topic_tags or "now" in lowered or not wants_history

        active_preferences = [record.content for record in retrieved_memory if record.type == "preference" and record.active]
        active_decisions = [record.content for record in retrieved_memory if record.type == "decision" and record.active]
        active_projects = [record.content for record in retrieved_memory if record.type == "project" and record.active]
        active_insights = [record.content for record in retrieved_memory if record.type == "insight" and record.active]
        historical_decisions = [record.content for record in retrieved_memory if record.type == "decision" and not record.active]

        sections: list[str] = []
        if active_preferences:
            sections.append("Preferences: " + " | ".join(active_preferences[:3]))
        if wants_current and active_decisions:
            sections.append("Active decisions: " + " | ".join(active_decisions[:4]))
        if active_projects:
            sections.append("Project memory: " + " | ".join(active_projects[:3]))
        if active_insights:
            sections.append("Relevant facts: " + " | ".join(active_insights[:3]))
        if wants_history and historical_decisions:
            sections.append("Previous decisions: " + " | ".join(historical_decisions[:4]))
        if wants_history and "change" in observer_state.topic_tags and active_decisions:
            sections.append("Current replacement decisions: " + " | ".join(active_decisions[:4]))

        if not sections:
            return "I retrieved memory records, but none of the relevant ones are currently active durable preferences or decisions."
        return "Current stored memory: " + " ".join(sections)

    @staticmethod
    def build_memory_context(retrieved_memory: list[MemoryRecord]) -> str:
        if not retrieved_memory:
            return "No relevant memory was selected for this turn."

        lines = []
        for index, record in enumerate(retrieved_memory[:4], start=1):
            lines.append(
                f"{index}. type={record.type}; importance={record.importance:.2f}; "
                f"usage_count={record.usage_count}; content={record.content}"
            )
        return "\n".join(lines)

    @staticmethod
    def _summarize_memory(retrieved_memory: list[MemoryRecord]) -> str:
        if not retrieved_memory:
            return ""
        fragments = []
        for record in retrieved_memory[:3]:
            state = "active" if record.active else "historical"
            fragments.append(f"[{record.type}:{state}] {record.content}")
        return " | ".join(fragments)
