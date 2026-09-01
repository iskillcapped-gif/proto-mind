"""Deterministic no-model evals for Persona provider readiness."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

from proto_mind.models import MemoryRecord
from proto_mind.persona_activation_readiness import (
    build_persona_activation_readiness,
    build_persona_prompt_projection,
    validate_persona_prompt_projection,
)
from proto_mind.persona_engine import (
    PersonaContextCompiler,
    PersonaRuntimeContext,
    PersonaTaskContext,
    PersonaValidationError,
)


SCHEMA = "proto_mind.persona_activation_evals.v1"
DEFAULT_CASES = Path(__file__).resolve().parents[1] / "evals/persona/activation_cases.jsonl"
FIXED_TIME = "2026-09-01T21:45:00+00:00"
WORKSPACE_ID = "workspace_0123456789abcdef"
PROVIDERS = ("codex_subscription", "ollama", "mock")


def load_cases(path: Path = DEFAULT_CASES) -> list[dict]:
    rows = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        row = json.loads(line)
        if (
            not isinstance(row, dict)
            or set(row) != {"id", "kind", "expected"}
            or not all(isinstance(row[field], str) and row[field] for field in row)
            or row["expected"] not in {"pass", "blocked", "refused"}
        ):
            raise ValueError(f"Invalid Persona activation eval case at line {number}.")
        rows.append(row)
    if not rows or len({row["id"] for row in rows}) != len(rows):
        raise ValueError("Persona activation eval cases are empty or duplicated.")
    return rows


def _identity(mission: str = "Preserve truthful continuity.") -> dict:
    return {
        "status": "OK",
        "version": 1,
        "updated_at": FIXED_TIME,
        "profile": {
            "name": "Proto-Mind",
            "role": "local cognitive system",
            "style": "warm and truthful",
            "operator_name": "Operator",
            "mission": mission,
        },
        "values": [{"id": "truth", "text": "Truth before approval.", "created_at": FIXED_TIME}],
        "principles": [{"id": "evidence", "text": "Use evidence.", "created_at": FIXED_TIME}],
        "boundaries": [{"id": "authority", "text": "No hidden authority.", "created_at": FIXED_TIME}],
    }


def _runtime(provider: str) -> PersonaRuntimeContext:
    values = {
        "codex_subscription": ("gpt-5.6-sol", "chat", "disabled", "none"),
        "ollama": ("qwen-local", "local", "local_only", "local_runtime"),
        "mock": ("deterministic_mock", "mock", "disabled", "none"),
    }[provider]
    return PersonaRuntimeContext(
        provider=provider,
        model=values[0],
        access_mode=values[1],
        workspace_id=WORKSPACE_ID,
        workspace_label="proto_mind",
        network_state=values[2],
        authorization_source=values[3],
    )


def _snapshots(*, mission: str = "Preserve truthful continuity.", memory=None) -> dict:
    compiler = PersonaContextCompiler()
    task = PersonaTaskContext(kind="conversation", risk="low", workspace_id=WORKSPACE_ID)
    return {
        provider: compiler.compile(
            identity_source=_identity(mission),
            retrieved_memory=[] if memory is None else memory,
            task=task,
            runtime=_runtime(provider),
            generated_at=FIXED_TIME,
        )
        for provider in PROVIDERS
    }


def run_cases(path: Path = DEFAULT_CASES) -> dict:
    outcomes = []
    for case in load_cases(path):
        passed = False
        detail = ""
        try:
            kind = case["kind"]
            rows = _snapshots()
            if kind == "provider_parity":
                report = build_persona_activation_readiness(
                    rows, selected_provider="codex_subscription", context_injection_state="disabled",
                )
                passed = case["expected"] == "pass" and report["status"] == "READY" and all(
                    report["parity"][field]
                    for field in ("kernel_equal", "identity_equal", "memory_equal", "task_equal")
                )
            elif kind == "prompt_placement":
                codex = build_persona_prompt_projection(rows["codex_subscription"])
                ollama = build_persona_prompt_projection(rows["ollama"])
                passed = (
                    case["expected"] == "pass"
                    and codex["placement"] == "base_instructions"
                    and ollama["placement"] == "system_message"
                    and codex["persona_invariant_hash"] == ollama["persona_invariant_hash"]
                )
            elif kind == "memory_provenance":
                rows = _snapshots(memory=[MemoryRecord(
                    id="mem_eval",
                    content="Operator prefers direct answers.",
                    type="preference",
                    importance=0.8,
                    source="operator_statement",
                )])
                projection = build_persona_prompt_projection(rows["ollama"])
                reference = projection["provenance"]["memory"]["references"][0]
                passed = (
                    case["expected"] == "pass"
                    and reference["record_id"] == "mem_eval"
                    and reference["provenance_id"] == "memory:mem_eval"
                    and projection["no_retrieval"] is True
                )
            elif kind == "mock_control":
                report = build_persona_activation_readiness(
                    rows, selected_provider="mock", context_injection_state="disabled",
                )
                passed = case["expected"] == "pass" and report["status"] == "WARN" and not report["selected_adapter_ready"]
            elif kind == "context_gate":
                report = build_persona_activation_readiness(
                    rows, selected_provider="codex_subscription", context_injection_state="enabled",
                )
                passed = case["expected"] == "blocked" and report["status"] == "NOT_READY"
            elif kind == "identity_drift":
                rows["ollama"] = _snapshots(mission="Provider-specific drift.")["ollama"]
                report = build_persona_activation_readiness(
                    rows, selected_provider="codex_subscription", context_injection_state="disabled",
                )
                passed = case["expected"] == "blocked" and report["status"] == "NOT_READY"
            elif kind == "projection_tamper":
                projection = build_persona_prompt_projection(rows["codex_subscription"])
                changed = deepcopy(projection)
                changed["provider_safety_boundary"] = "replaceable"
                try:
                    validate_persona_prompt_projection(changed, rows["codex_subscription"])
                except PersonaValidationError:
                    passed = case["expected"] == "refused"
            else:
                detail = "unknown eval kind"
        except Exception as exc:
            detail = type(exc).__name__
        outcomes.append({"id": case["id"], "passed": passed, "detail": detail})
    return {
        "schema": SCHEMA,
        "read_only": True,
        "activation_performed": False,
        "model_calls": 0,
        "network_calls": 0,
        "retrieval_calls": 0,
        "store_writes": 0,
        "total": len(outcomes),
        "passed": sum(item["passed"] for item in outcomes),
        "cases": outcomes,
    }


def main() -> None:
    result = run_cases()
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    raise SystemExit(0 if result["passed"] == result["total"] else 1)


if __name__ == "__main__":
    main()
