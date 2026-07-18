from __future__ import annotations

from abc import ABC, abstractmethod

from proto_mind.models import MemoryRecord, ObserverState


class BaseReasoner(ABC):
    backend_name = "base"

    @abstractmethod
    def respond(
        self,
        user_input: str,
        retrieved_memory: list[MemoryRecord],
        observer_state: ObserverState,
        correction_hints: list[str] | None = None,
    ) -> str:
        raise NotImplementedError
