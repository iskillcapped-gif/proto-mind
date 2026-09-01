"""Deterministic local evals for controlled Persona prompt activation."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
from typing import Any
from unittest.mock import patch

from proto_mind.config import ProtoMindConfig
from proto_mind.models import MemoryRecord
from proto_mind.native_codex import SubscriptionReasoner, _legacy_subscription_instructions
from proto_mind.observer import Observer
from proto_mind.persona_activation import (
    PersonaTurnActivation,
    prepare_persona_turn,
    validate_persona_turn_receipt,
)
from proto_mind.persona_engine import PersonaRuntimeContext, PersonaValidationError
from proto_mind.reasoners.ollama_reasoner import OllamaReasoner


SCHEMA = "proto_mind.persona_runtime_evals.v1"
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CASES = PROJECT_ROOT / "evals/persona/runtime_activation_cases.jsonl"
WORKSPACE_ID = "workspace_0123456789abcdef"
_ALLOWED_FIELDS = {"id", "kind", "provider", "expected"}


def load_cases(path: Path = DEFAULT_CASES) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        row = json.loads(line)
        if (
            not isinstance(row, dict)
            or set(row) - _ALLOWED_FIELDS
            or not isinstance(row.get("id"), str)
            or not row["id"]
            or not isinstance(row.get("kind"), str)
            or not row["kind"]
            or row.get("expected") not in {"pass", "preserved", "refused", "blocked"}
            or ("provider" in row and row["provider"] not in {"codex_subscription", "ollama"})
        ):
            raise ValueError(f"Invalid Persona runtime eval case at line {line_number}.")
        rows.append(row)
    if not rows or len({row["id"] for row in rows}) != len(rows):
        raise ValueError("Persona runtime eval cases are empty or duplicated.")
    return rows


def _runtime(provider: str) -> PersonaRuntimeContext:
    if provider == "codex_subscription":
        model, access, network, authorization = "gpt-5.6-sol", "chat", "disabled", "none"
    elif provider == "ollama":
        model, access, network, authorization = "qwen-local", "local", "local_only", "local_runtime"
    else:
        model, access, network, authorization = "deterministic_mock", "mock", "disabled", "none"
    return PersonaRuntimeContext(
        provider=provider,
        model=model,
        access_mode=access,
        workspace_id=WORKSPACE_ID,
        workspace_label="proto_mind",
        network_state=network,
        authorization_source=authorization,
    )


def _activation(root: Path, provider: str) -> PersonaTurnActivation:
    return PersonaTurnActivation(
        project_root=root,
        runtime=_runtime(provider),
        context_injection_state="default_disabled",
        readiness_hash="a" * 64,
    )


def _memory() -> MemoryRecord:
    return MemoryRecord(
        id="mem_persona_eval",
        content="The operator prefers evidence before conclusions.",
        type="preference",
        importance=0.9,
        source="operator_statement",
        confidence=1.0,
    )


def _prepare(root: Path, provider: str, *, memory: bool = False):
    return prepare_persona_turn(
        _activation(root, provider),
        retrieved_memory=[_memory()] if memory else [],
        observer_state=Observer().analyze("Continue our work."),
        correction_hints=["State uncertainty explicitly."],
        legacy_prompt="legacy prompt bytes",
    )


def _protected_hashes() -> dict[str, str]:
    result: dict[str, str] = {}
    for relative in (Path("proto_mind/data"), Path("proto_mind/exports")):
        root = PROJECT_ROOT / relative
        if not root.exists():
            continue
        for path in sorted(root.rglob("*")):
            if path.is_file() and not path.is_symlink():
                result[str(path.relative_to(PROJECT_ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


class _CaptureSubscription:
    def __init__(self) -> None:
        self.instructions = ""
        self.calls = 0

    def answer(self, prompt, instructions, model, on_delta, **kwargs):
        self.calls += 1
        self.instructions = instructions
        return "fixture"


def _run_case(case: dict[str, str], root: Path) -> bool:
    kind = case["kind"]
    expected = case["expected"]
    if kind == "provider_activation":
        turn = _prepare(root, case["provider"])
        receipt = validate_persona_turn_receipt(turn.receipt)
        return (
            expected == "pass"
            and receipt["provider"] == case["provider"]
            and receipt["active_prompt_hash"] == hashlib.sha256(turn.instructions.encode("utf-8")).hexdigest()
            and receipt["additional_model_calls"] == 0
            and receipt["additional_retrieval_calls"] == 0
            and receipt["store_writes_by_activation"] == 0
        )
    if kind == "provider_invariant":
        codex = _prepare(root, "codex_subscription")
        ollama = _prepare(root, "ollama")
        return expected == "preserved" and (
            codex.receipt["persona_invariant_hash"] == ollama.receipt["persona_invariant_hash"]
        )
    if kind == "memory_provenance":
        receipt = _prepare(root, "codex_subscription", memory=True).receipt
        return (
            expected == "pass"
            and receipt["selected_memory_ids"] == ["mem_persona_eval"]
            and receipt["selected_memory_count"] == 1
            and receipt["memory_provenance"][0]["source"] == "operator_statement"
        )
    if kind == "mock_refusal":
        try:
            _activation(root, "mock")
        except PersonaValidationError:
            return expected == "refused"
        return False
    if kind == "context_drift":
        with patch("proto_mind.persona_activation.injection_state", return_value={"state": "enabled"}):
            try:
                _prepare(root, "codex_subscription")
            except PersonaValidationError:
                return expected == "blocked"
        return False
    if kind == "receipt_tamper":
        changed = deepcopy(_prepare(root, "codex_subscription").receipt)
        changed["no_added_authority"] = False
        try:
            validate_persona_turn_receipt(changed)
        except PersonaValidationError:
            return expected == "refused"
        return False
    if kind == "legacy_rollback":
        observer = Observer().analyze("Continue our work.")
        raw = OllamaReasoner(ProtoMindConfig())._build_system_prompt(observer, [], [])
        subscription = _CaptureSubscription()
        reasoner = SubscriptionReasoner(
            subscription, "gpt-5.6-sol", [], lambda _: None,
            conversation="persona-runtime-eval", logical_workspace=None,
        )
        reasoner.respond("Continue our work.", [], observer)
        return (
            expected == "preserved"
            and subscription.calls == 1
            and subscription.instructions == _legacy_subscription_instructions(raw)
            and reasoner.last_persona_receipt is None
        )
    return False


def run_cases(path: Path = DEFAULT_CASES) -> dict[str, Any]:
    before = _protected_hashes()
    outcomes = []
    with tempfile.TemporaryDirectory(prefix="persona-runtime-evals-") as directory:
        root = Path(directory).resolve()
        for case in load_cases(path):
            passed, detail = False, ""
            try:
                passed = _run_case(case, root)
            except Exception as exc:
                detail = type(exc).__name__
            outcomes.append({"id": case["id"], "passed": passed, "detail": detail})
    if _protected_hashes() != before:
        raise RuntimeError("Persona runtime evals changed a protected project store or export.")
    return {
        "schema": SCHEMA,
        "read_only": True,
        "provider_turns": 0,
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
