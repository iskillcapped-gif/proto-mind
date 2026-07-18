from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ProtoMindConfig:
    reasoner_backend: str = "mock"
    ollama_model: str = "qwen3:8b"
    ollama_url: str = "http://localhost:11434"
    data_dir: Path | None = None

    @classmethod
    def from_env(cls, base_dir: Path | None = None) -> "ProtoMindConfig":
        root = base_dir or Path(__file__).resolve().parent
        data_dir_env = os.getenv("PROTO_MIND_DATA_DIR")
        data_dir = Path(data_dir_env) if data_dir_env else root / "data"
        return cls(
            reasoner_backend=os.getenv("PROTO_MIND_REASONER", "mock").strip().lower(),
            ollama_model=os.getenv("PROTO_MIND_OLLAMA_MODEL", "qwen3:8b").strip(),
            ollama_url=os.getenv("PROTO_MIND_OLLAMA_URL", "http://localhost:11434").strip(),
            data_dir=data_dir,
        )
