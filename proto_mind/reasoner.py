from __future__ import annotations

from proto_mind.config import ProtoMindConfig
from proto_mind.reasoners import create_reasoner
from proto_mind.reasoners.base import BaseReasoner
from proto_mind.reasoners.mock_reasoner import MockReasoner
from proto_mind.reasoners.ollama_reasoner import OllamaReasoner


Reasoner = MockReasoner

__all__ = [
    "BaseReasoner",
    "MockReasoner",
    "OllamaReasoner",
    "ProtoMindConfig",
    "Reasoner",
    "create_reasoner",
]
