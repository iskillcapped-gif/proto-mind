"""Deterministic contract for one explicitly granted Native Full Mac turn."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path

from proto_mind.native_computer_use import COMPUTER_USE_TOOLS, REQUIRED_COMPUTER_USE_TOOLS


SCHEMA = "proto_mind.native_agent_contract.v1"
PROVIDER = "codex_subscription"
ACCESS_MODE = "full_access"
MAX_SECONDS = 900
MAX_OBSERVED_ITEMS = 64
ALLOWED_EFFORTS = {"", "none", "minimal", "low", "medium", "high", "xhigh", "max", "ultra"}
STOP_CONDITIONS = (
    "operator_stop",
    "provider_failure",
    "unexpected_tool",
    "time_limit",
    "activity_limit",
    "durable_evidence_failure",
)


class AgentContractError(ValueError):
    pass


def _canonical(value: dict) -> bytes:
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def contract_hash(contract: dict) -> str:
    validate_agent_contract(contract)
    return hashlib.sha256(_canonical(contract)).hexdigest()


def _criteria_digest(criteria: list[str]) -> str:
    return hashlib.sha256(_canonical({"items": criteria})).hexdigest()


def build_agent_contract(workspace: Path, *, model: str, reasoning_effort: str,
                         computer_use: bool, criteria: list[str] | None = None) -> dict:
    """Freeze authority, budgets and success semantics before provider startup."""
    root = Path(workspace).resolve(strict=True)
    info = root.stat()
    items = [] if criteria is None else list(criteria)
    if (len(items) > 20 or any(not isinstance(item, str) or not item
                               or len(item) > 400 or "\x00" in item for item in items)):
        raise AgentContractError("Native agent success criteria are invalid.")
    contract = {
        "schema": SCHEMA,
        "provider": PROVIDER,
        "access_mode": ACCESS_MODE,
        "goal": "operator_supplied_foreground_task",
        "model": model,
        "reasoning_effort": reasoning_effort,
        "workspace": {"path": str(root), "device": info.st_dev, "inode": info.st_ino},
        "input": {
            "shape": "bounded_text_context_and_explicit_attachments",
            "contract_retains_input": False,
        },
        "output": {
            "shape": "answer_and_bounded_public_evidence",
            "provider_completion_is_verification": False,
        },
        "tools": {
            "shell_and_files": "codex_builtin_user_level",
            "web_search": "live",
            "computer_use": computer_use,
            "computer_use_enabled_tools": sorted(COMPUTER_USE_TOOLS) if computer_use else [],
            "computer_use_required_tools": sorted(REQUIRED_COMPUTER_USE_TOOLS) if computer_use else [],
        },
        "permissions": {
            "grant": "explicit_conversation_workspace_process_memory",
            "approval_policy": "never_after_explicit_full_mac_grant",
            "root": False,
            "project_fence": False,
            "background_execution": False,
        },
        "limits": {
            "max_seconds": MAX_SECONDS,
            "max_observed_items": MAX_OBSERVED_ITEMS,
            "one_active_turn": True,
            "automatic_retry": False,
            "automatic_rollback": False,
        },
        "verification": {
            "declared_criteria_count": len(items),
            "declared_criteria_sha256": _criteria_digest(items),
            "initial_status": "not_assessed",
            "operator_acceptance_is_separate": True,
        },
        "stop_conditions": list(STOP_CONDITIONS),
    }
    validate_agent_contract(contract)
    return contract


def validate_agent_contract(contract: object) -> dict:
    """Fail closed if a future refactor silently broadens the frozen contract."""
    if not isinstance(contract, dict) or set(contract) != {
        "schema", "provider", "access_mode", "goal", "model", "reasoning_effort",
        "workspace", "input", "output", "tools", "permissions", "limits",
        "verification", "stop_conditions",
    }:
        raise AgentContractError("Invalid Native agent contract shape.")
    if (contract["schema"] != SCHEMA or contract["provider"] != PROVIDER
            or contract["access_mode"] != ACCESS_MODE
            or contract["goal"] != "operator_supplied_foreground_task"):
        raise AgentContractError("Native agent contract identity drifted.")
    if (not isinstance(contract["model"], str) or not contract["model"]
            or len(contract["model"]) > 160 or "\x00" in contract["model"]
            or contract["reasoning_effort"] not in ALLOWED_EFFORTS):
        raise AgentContractError("Native agent model contract is invalid.")
    workspace = contract["workspace"]
    if (not isinstance(workspace, dict) or set(workspace) != {"path", "device", "inode"}
            or not isinstance(workspace["path"], str) or not workspace["path"].startswith("/")
            or type(workspace["device"]) is not int or type(workspace["inode"]) is not int):
        raise AgentContractError("Native agent workspace contract is invalid.")
    if contract["input"] != {
        "shape": "bounded_text_context_and_explicit_attachments", "contract_retains_input": False,
    } or contract["output"] != {
        "shape": "answer_and_bounded_public_evidence", "provider_completion_is_verification": False,
    }:
        raise AgentContractError("Native agent input/output contract drifted.")
    tools = contract["tools"]
    if not isinstance(tools, dict) or set(tools) != {
        "shell_and_files", "web_search", "computer_use",
        "computer_use_enabled_tools", "computer_use_required_tools",
    }:
        raise AgentContractError("Native agent tool contract is invalid.")
    enabled = tools["computer_use"] is True
    expected_tools = sorted(COMPUTER_USE_TOOLS) if enabled else []
    expected_required = sorted(REQUIRED_COMPUTER_USE_TOOLS) if enabled else []
    if (tools["shell_and_files"] != "codex_builtin_user_level" or tools["web_search"] != "live"
            or type(tools["computer_use"]) is not bool
            or tools["computer_use_enabled_tools"] != expected_tools
            or tools["computer_use_required_tools"] != expected_required):
        raise AgentContractError("Native agent tool authority drifted.")
    if contract["permissions"] != {
        "grant": "explicit_conversation_workspace_process_memory",
        "approval_policy": "never_after_explicit_full_mac_grant",
        "root": False,
        "project_fence": False,
        "background_execution": False,
    }:
        raise AgentContractError("Native agent permission contract drifted.")
    if contract["limits"] != {
        "max_seconds": MAX_SECONDS,
        "max_observed_items": MAX_OBSERVED_ITEMS,
        "one_active_turn": True,
        "automatic_retry": False,
        "automatic_rollback": False,
    }:
        raise AgentContractError("Native agent execution limits drifted.")
    verification = contract["verification"]
    if (not isinstance(verification, dict) or set(verification) != {
            "declared_criteria_count", "declared_criteria_sha256", "initial_status",
            "operator_acceptance_is_separate",
        } or type(verification["declared_criteria_count"]) is not int
            or not 0 <= verification["declared_criteria_count"] <= 20
            or not isinstance(verification["declared_criteria_sha256"], str)
            or len(verification["declared_criteria_sha256"]) != 64
            or verification["initial_status"] != "not_assessed"
            or verification["operator_acceptance_is_separate"] is not True):
        raise AgentContractError("Native agent verification contract is invalid.")
    if contract["stop_conditions"] != list(STOP_CONDITIONS):
        raise AgentContractError("Native agent stop conditions drifted.")
    return contract


def validate_runtime_inventory(contract: dict, tools: set[str]) -> dict:
    validate_agent_contract(contract)
    if not isinstance(tools, set) or any(not isinstance(item, str) for item in tools):
        raise AgentContractError("Computer Use runtime inventory is invalid.")
    expected = set(contract["tools"]["computer_use_enabled_tools"])
    required = set(contract["tools"]["computer_use_required_tools"])
    if not tools.issubset(expected) or not required.issubset(tools):
        raise AgentContractError("Computer Use runtime inventory drifted from the agent contract.")
    if not contract["tools"]["computer_use"] and tools:
        raise AgentContractError("Computer Use appeared outside the agent contract.")
    return {"verified": True, "computer_use_tools": sorted(tools)}


def public_agent_contract(contract: dict) -> dict:
    validate_agent_contract(contract)
    return deepcopy(contract)
