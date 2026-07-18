from __future__ import annotations

from proto_mind.config import ProtoMindConfig
from proto_mind.reasoners.base import BaseReasoner
from proto_mind.reasoners.mock_reasoner import MockReasoner
from proto_mind.reasoners.ollama_reasoner import OllamaReasoner


def create_reasoner(config: ProtoMindConfig) -> BaseReasoner:
    if config.reasoner_backend == "ollama":
        return OllamaReasoner(config=config)
    return MockReasoner()
