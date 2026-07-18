from __future__ import annotations

from proto_mind.config import ProtoMindConfig
from proto_mind.grounding_auditor import GroundingAuditor
from proto_mind.memory_keeper import MemoryKeeper
from proto_mind.models import InteractionResult
from proto_mind.observer import Observer
from proto_mind.reasoners.base import BaseReasoner
from proto_mind.self_reflection import SelfReflector
from proto_mind.session_log import SessionOperatorLogger


class Coordinator:
    def __init__(
        self,
        observer: Observer,
        memory_keeper: MemoryKeeper,
        reasoner: BaseReasoner,
        config: ProtoMindConfig | None = None,
        self_reflector: SelfReflector | None = None,
        grounding_auditor: GroundingAuditor | None = None,
        session_logger: SessionOperatorLogger | None = None,
    ) -> None:
        self.observer = observer
        self.memory_keeper = memory_keeper
        self.reasoner = reasoner
        self.config = config or ProtoMindConfig()
        self.self_reflector = self_reflector or SelfReflector()
        self.grounding_auditor = grounding_auditor or GroundingAuditor()
        self.session_logger = session_logger
        self.pending_correction_hints: list[str] = []

    def handle(self, user_input: str, *, reasoner_input: str | None = None) -> InteractionResult:
        active_reasoner_input = reasoner_input or user_input
        observer_state = self.observer.analyze(user_input)
        retrieved_memory = []
        retrieval_trace = None
        if observer_state.needs_memory:
            top_k = 10 if observer_state.query_type == "memory_inventory" else 5
            retrieved_memory = self.memory_keeper.retrieve(observer_state, top_k=top_k, user_input=user_input)
            retrieval_trace = self.memory_keeper.last_retrieval_trace

        previous_correction_hints = list(self.pending_correction_hints)
        response = self.reasoner.respond(
            user_input=active_reasoner_input,
            retrieved_memory=retrieved_memory,
            observer_state=observer_state,
            correction_hints=previous_correction_hints,
        )

        summary = self.memory_keeper.evaluate_interaction(
            user_input=user_input,
            response=response,
            observer_state=observer_state,
            retrieved_memory=retrieved_memory,
        )
        summary = self.memory_keeper.apply_memory_updates(summary, retrieved_memory=retrieved_memory)
        working_snapshot = self.memory_keeper.store.load_working_memory()
        persistent_snapshot = self.memory_keeper.store.load_persistent_memory()
        self_reflection = self.self_reflector.reflect(
            user_input=user_input,
            response=response,
            observer_state=observer_state,
            retrieved_memory=retrieved_memory,
            retrieval_trace=retrieval_trace,
            memory_summary=summary,
            working_memory=working_snapshot,
            persistent_memory=persistent_snapshot,
        )
        grounding_audit = self.grounding_auditor.audit(
            user_input=user_input,
            response=response,
            observer_state=observer_state,
            retrieved_memory=retrieved_memory,
            retrieval_trace=retrieval_trace,
            working_memory=working_snapshot,
            persistent_memory=persistent_snapshot,
        )
        self.pending_correction_hints = (
            list(self_reflection.correction_hints)
            if self_reflection.should_carry_forward and self_reflection.carry_forward_scope == "next_turn"
            else []
        )

        result = InteractionResult(
            response=response,
            observer_state=observer_state,
            retrieved_memory=retrieved_memory,
            retrieval_trace=retrieval_trace,
            memory_summary=summary,
            working_memory_snapshot=working_snapshot,
            persistent_memory_snapshot=persistent_snapshot,
            reasoner_backend=self.reasoner.backend_name,
            self_reflection=self_reflection,
            grounding_audit=grounding_audit,
            previous_correction_hints=previous_correction_hints,
        )
        if self.session_logger:
            self.session_logger.append_turn(result, user_input)
        return result
