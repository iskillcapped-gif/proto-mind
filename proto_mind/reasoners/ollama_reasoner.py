from __future__ import annotations

import json
from urllib import error, request

from proto_mind.config import ProtoMindConfig
from proto_mind.models import MemoryRecord, ObserverState
from proto_mind.reasoners.base import BaseReasoner
from proto_mind.reasoners.mock_reasoner import MockReasoner


class OllamaReasoner(BaseReasoner):
    backend_name = "ollama"

    def __init__(self, config: ProtoMindConfig, fallback_reasoner: BaseReasoner | None = None) -> None:
        self.config = config
        self.fallback_reasoner = fallback_reasoner or MockReasoner()

    def respond(
        self,
        user_input: str,
        retrieved_memory: list[MemoryRecord],
        observer_state: ObserverState,
        correction_hints: list[str] | None = None,
    ) -> str:
        payload = {
            "model": self.config.ollama_model,
            "messages": [
                {
                    "role": "system",
                    "content": self._build_system_prompt(observer_state, retrieved_memory, correction_hints or []),
                },
                {"role": "user", "content": user_input.strip()},
            ],
            "stream": False,
        }
        try:
            raw = self._post("/api/chat", payload)
            content = raw.get("message", {}).get("content", "").strip()
            if content:
                return content
            raise ValueError("Ollama returned an empty response.")
        except (OSError, error.URLError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
            fallback = self.fallback_reasoner.respond(user_input, retrieved_memory, observer_state, correction_hints)
            return (
                "[Ollama unavailable, falling back to mock reasoning] "
                f"{fallback} (Local error: {exc})"
            )

    def _post(self, path: str, payload: dict[str, object]) -> dict[str, object]:
        body = json.dumps(payload).encode("utf-8")
        req = request.Request(
            url=f"{self.config.ollama_url.rstrip('/')}{path}",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with request.urlopen(req, timeout=60) as response:
            return json.loads(response.read().decode("utf-8"))

    def _build_system_prompt(
        self,
        observer_state: ObserverState,
        retrieved_memory: list[MemoryRecord],
        correction_hints: list[str],
    ) -> str:
        memory_context = MockReasoner.build_memory_context(retrieved_memory)
        correction_context = self._build_correction_context(correction_hints)
        continuity_priority = observer_state.query_type == "continuity_followup"
        return (
            "You are Proto-Mind, a local research cognition layer.\n"
            "Your job is to answer with architectural clarity and continuity.\n"
            "If the user is asking what is currently remembered, answer from stored memory explicitly.\n"
            "Do not improvise extra decisions or preferences that are not present in retrieved memory.\n"
            "Treat the current user message as primary unless the turn is clearly a continuity follow-up.\n"
            "Use retrieved memory as internal cognitive context, not as a raw appendix.\n"
            "Only use the memory that is actually relevant. Avoid dumping all memory back to the user.\n"
            "If memory indicates prior decisions or stable preferences, let those shape the answer without overpowering new declarations.\n"
            "Be concise, transparent, and avoid product-style polish.\n\n"
            f"Observer interpretation:\n"
            f"- query_type: {observer_state.query_type}\n"
            f"- needs_memory: {observer_state.needs_memory}\n"
            f"- importance_hint: {observer_state.importance_hint:.2f}\n"
            f"- topic_tags: {', '.join(observer_state.topic_tags) or 'none'}\n\n"
            f"Reasoning priority:\n"
            f"- continuity_priority: {str(continuity_priority).lower()}\n"
            f"- current_user_message_is_primary: {str(not continuity_priority).lower()}\n\n"
            f"Relevant memory selected by MemoryKeeper:\n{memory_context}\n\n"
            f"Previous self-reflection correction hints:\n{correction_context}\n\n"
            "Answer as if this memory is part of your internal state for the turn."
        )

    @staticmethod
    def _build_correction_context(correction_hints: list[str]) -> str:
        if not correction_hints:
            return "No previous correction hints are active for this turn."
        return "\n".join(f"- {hint}" for hint in correction_hints[:5])
