"""Dependency-free local evals for the Native agent contract and guardrails."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import tempfile

from proto_mind.native_agent import AgentRun
from proto_mind.native_agent_contract import build_agent_contract, validate_agent_contract
from proto_mind.native_codex import CodexConnectionError


SCHEMA = "proto_mind.native_agent_evals.v1"
DEFAULT_CASES = Path(__file__).resolve().parents[1] / "evals" / "native_agent_contract" / "cases.jsonl"


def load_cases(path: Path = DEFAULT_CASES) -> list[dict]:
    rows = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        row = json.loads(line)
        if (not isinstance(row, dict) or set(row) - {"id", "kind", "path", "value", "expected"}
                or not isinstance(row.get("id"), str) or not isinstance(row.get("kind"), str)
                or row.get("expected") not in {"pass", "refused", "classified"}):
            raise ValueError(f"Invalid Native agent eval case at line {line_number}.")
        rows.append(row)
    if not rows or len({row["id"] for row in rows}) != len(rows):
        raise ValueError("Native agent eval cases are empty or duplicated.")
    return rows


def _set_path(value: dict, path: str, replacement: object) -> None:
    allowed = {
        "limits.automatic_retry",
        "permissions.background_execution",
        "tools.computer_use_enabled_tools",
    }
    if path not in allowed:
        raise ValueError("Eval fixture requested an unsupported mutation.")
    parent, key = path.split(".")
    value[parent][key] = replacement


def run_cases(path: Path = DEFAULT_CASES) -> dict:
    outcomes = []
    with tempfile.TemporaryDirectory(prefix="proto-agent-evals-") as directory:
        workspace = Path(directory).resolve()
        base = build_agent_contract(workspace, model="gpt-5.6-sol", reasoning_effort="high",
                                    computer_use=True, criteria=["Return verified evidence."])
        for case in load_cases(path):
            passed, detail = False, ""
            try:
                if case["kind"] == "contract":
                    validate_agent_contract(base)
                    passed = case["expected"] == "pass"
                elif case["kind"] == "contract_mutation":
                    changed = deepcopy(base)
                    _set_path(changed, case["path"], case.get("value"))
                    try:
                        validate_agent_contract(changed)
                        passed = case["expected"] == "pass"
                    except ValueError:
                        passed = case["expected"] == "refused"
                elif case["kind"] == "automation_denied":
                    run = AgentRun(workspace, lambda _: None, computer_use_available=True)
                    run.record({
                        "id": "screen", "type": "mcpToolCall", "server": "computer-use",
                        "tool": "get_app_state", "status": "failed",
                        "arguments": {"app": "Safari", "disableDiff": True},
                        "result": {"content": [{"type": "text", "text":
                            "Computer Use server error -1743: Unknown error"}]},
                    }, True)
                    passed = (case["expected"] == "classified"
                              and run.items["screen"].get("failure_code") == "macos_automation_permission_denied")
                elif case["kind"] == "unexpected_tool":
                    run = AgentRun(workspace, lambda _: None, computer_use_available=True)
                    try:
                        run.record({"id": "bad", "type": "mcpToolCall", "server": "computer-use",
                                    "tool": "run_shell", "status": "completed"}, True)
                    except CodexConnectionError:
                        passed = case["expected"] == "refused"
                else:
                    detail = "unknown eval kind"
            except Exception as exc:
                detail = type(exc).__name__
            outcomes.append({"id": case["id"], "passed": passed, "detail": detail})
    return {"schema": SCHEMA, "read_only": True, "total": len(outcomes),
            "passed": sum(row["passed"] for row in outcomes), "cases": outcomes}


def main() -> None:
    result = run_cases()
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    raise SystemExit(0 if result["passed"] == result["total"] else 1)


if __name__ == "__main__":
    main()
