from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from proto_mind.action_policy import classify_command
from proto_mind.command_registry import COMMAND_REGISTRY, CommandSpec
from proto_mind.runner_exec_config import ACTIVE_READONLY_ALLOWLIST


CAPABILITY_CONTRACT_VERSION = 1
LOCAL_CAPABILITY_TRANSPORT = "none"
LOCAL_CAPABILITY_EXECUTION_MODE = "dedicated_zero_argument_callback"
LOCAL_CAPABILITY_RESULT_KEYS = ("structuredContent", "content", "_meta")
_STATUS_PATTERN = re.compile(
    r"^(?:status|overall_status):\s*(OK|WARN|BLOCKED|ERROR)\b",
    flags=re.IGNORECASE | re.MULTILINE,
)
_SAFE_TOOL_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
_CONTRACT_IDENTITIES = {
    "/warnings unknown": (
        "warnings_unknown",
        "Inspect unknown warnings",
        "Use this when the operator needs to inspect warnings not covered by the accepted-known baseline.",
    ),
    "/daily doctor": (
        "daily_doctor",
        "Check daily layer",
        "Use this when the operator needs a deterministic health check of the local Daily Layer.",
    ),
    "/exports doctor": (
        "exports_doctor",
        "Check local exports",
        "Use this when the operator needs to validate local export health without changing any export.",
    ),
    "/capabilities safety": (
        "capabilities_safety",
        "Inspect capability safety",
        "Use this when the operator needs Registry and Action Policy safety classifications.",
    ),
}


@dataclass(frozen=True)
class CapabilityAnnotations:
    read_only_hint: bool
    destructive_hint: bool
    open_world_hint: bool
    idempotent_hint: bool

    def to_dict(self) -> dict[str, bool]:
        return {
            "readOnlyHint": self.read_only_hint,
            "destructiveHint": self.destructive_hint,
            "openWorldHint": self.open_world_hint,
            "idempotentHint": self.idempotent_hint,
        }


@dataclass(frozen=True)
class LocalCapabilityContract:
    name: str
    title: str
    command: str
    description: str
    input_schema: Mapping[str, Any]
    output_schema: Mapping[str, Any]
    annotations: CapabilityAnnotations
    local_only: bool = True
    transport: str = LOCAL_CAPABILITY_TRANSPORT
    execution_mode: str = LOCAL_CAPABILITY_EXECUTION_MODE

    def to_descriptor(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "title": self.title,
            "description": self.description,
            "inputSchema": dict(self.input_schema),
            "outputSchema": dict(self.output_schema),
            "annotations": self.annotations.to_dict(),
            "_meta": {
                "proto_mind": {
                    "contract_version": CAPABILITY_CONTRACT_VERSION,
                    "source_command": self.command,
                    "local_only": self.local_only,
                    "transport": self.transport,
                    "execution_mode": self.execution_mode,
                    "network_access": False,
                    "store_mutation": False,
                    "external_exposure": False,
                }
            },
        }


@dataclass(frozen=True)
class LocalCapabilityResult:
    structured_content: Mapping[str, Any]
    content: tuple[Mapping[str, str], ...]
    meta: Mapping[str, Any]

    def to_mcp_result(self) -> dict[str, Any]:
        return {
            "structuredContent": dict(self.structured_content),
            "content": [dict(item) for item in self.content],
            "_meta": dict(self.meta),
        }


def _input_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    }


def _output_schema(command: str) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "command": {"type": "string", "const": command},
            "contract": {"type": "string"},
            "status": {"type": "string", "enum": ["OK", "WARN", "BLOCKED", "ERROR", "UNKNOWN"]},
            "summary": {"type": "string"},
            "read_only": {"type": "boolean", "const": True},
            "local_only": {"type": "boolean", "const": True},
            "output_chars": {"type": "integer", "minimum": 0},
        },
        "required": [
            "command",
            "contract",
            "status",
            "summary",
            "read_only",
            "local_only",
            "output_chars",
        ],
        "additionalProperties": False,
    }


def _build_contracts() -> tuple[LocalCapabilityContract, ...]:
    contracts: list[LocalCapabilityContract] = []
    for command in ACTIVE_READONLY_ALLOWLIST:
        name, title, description = _CONTRACT_IDENTITIES[command]
        contracts.append(
            LocalCapabilityContract(
                name=name,
                title=title,
                command=command,
                description=description,
                input_schema=_input_schema(),
                output_schema=_output_schema(command),
                annotations=CapabilityAnnotations(
                    read_only_hint=True,
                    destructive_hint=False,
                    open_world_hint=False,
                    idempotent_hint=True,
                ),
            )
        )
    return tuple(contracts)


LOCAL_CAPABILITY_CONTRACTS = _build_contracts()


def get_local_capability_contract(query: str) -> LocalCapabilityContract | None:
    normalized = " ".join(query.strip().lower().split())
    for contract in LOCAL_CAPABILITY_CONTRACTS:
        if normalized in {contract.name, contract.command}:
            return contract
    return None


def build_local_capability_result(command: str, output: str) -> LocalCapabilityResult:
    contract = get_local_capability_contract(command)
    if contract is None or contract.command != " ".join(command.strip().lower().split()):
        raise ValueError(f"Command has no local capability contract: {command}")
    status = _detect_status(output)
    summary = _first_nonempty_line(output)
    return LocalCapabilityResult(
        structured_content={
            "command": contract.command,
            "contract": contract.name,
            "status": status,
            "summary": summary,
            "read_only": True,
            "local_only": True,
            "output_chars": len(output),
        },
        content=({"type": "text", "text": output},),
        meta={
            "proto_mind": {
                "contract_version": CAPABILITY_CONTRACT_VERSION,
                "source_command": contract.command,
                "local_only": True,
                "transport": LOCAL_CAPABILITY_TRANSPORT,
                "execution_mode": LOCAL_CAPABILITY_EXECUTION_MODE,
                "network_access": False,
                "store_mutation": False,
                "external_exposure": False,
                "full_output_exportable": False,
            }
        },
    )


def local_capability_contract_doctor(
    *,
    contracts: Iterable[LocalCapabilityContract] = LOCAL_CAPABILITY_CONTRACTS,
    registry: Iterable[CommandSpec] = COMMAND_REGISTRY,
) -> dict[str, Any]:
    checked = list(contracts)
    specs = {spec.prefix: spec for spec in registry}
    findings: list[dict[str, str]] = []
    names = [contract.name for contract in checked]
    commands = [contract.command for contract in checked]

    if tuple(commands) != tuple(ACTIVE_READONLY_ALLOWLIST):
        findings.append(
            {
                "severity": "ERROR",
                "message": "Contract commands do not exactly match the active read-only runner allowlist.",
            }
        )
    if len(set(names)) != len(names):
        findings.append({"severity": "ERROR", "message": "Duplicate local capability contract names detected."})
    if len(set(commands)) != len(commands):
        findings.append({"severity": "ERROR", "message": "Duplicate local capability commands detected."})

    for contract in checked:
        label = contract.name or contract.command or "<empty>"
        spec = specs.get(contract.command)
        if not _SAFE_TOOL_NAME_PATTERN.fullmatch(contract.name):
            findings.append({"severity": "ERROR", "message": f"Unsafe contract name: {label}"})
        if not contract.description.startswith("Use this when"):
            findings.append({"severity": "ERROR", "message": f"Contract description lacks a usage cue: {label}"})
        if spec is None:
            findings.append({"severity": "ERROR", "message": f"Contract command missing from Registry: {contract.command}"})
        else:
            if not spec.read_only or spec.mutates != "none" or spec.risk != "low":
                findings.append(
                    {
                        "severity": "ERROR",
                        "message": f"Contract command is not read-only/mutates=none/low-risk: {contract.command}",
                    }
                )
            if classify_command(contract.command, specs.values()).policy_class != "auto_allowed":
                findings.append({"severity": "ERROR", "message": f"Contract command is not auto_allowed: {contract.command}"})
        if dict(contract.input_schema) != _input_schema():
            findings.append({"severity": "ERROR", "message": f"Contract accepts arguments: {label}"})
        if dict(contract.output_schema) != _output_schema(contract.command):
            findings.append({"severity": "ERROR", "message": f"Contract output schema drift: {label}"})
        if contract.annotations.to_dict() != {
            "readOnlyHint": True,
            "destructiveHint": False,
            "openWorldHint": False,
            "idempotentHint": True,
        }:
            findings.append({"severity": "ERROR", "message": f"Contract annotations are unsafe: {label}"})
        if (
            not contract.local_only
            or contract.transport != LOCAL_CAPABILITY_TRANSPORT
            or contract.execution_mode != LOCAL_CAPABILITY_EXECUTION_MODE
        ):
            findings.append({"severity": "ERROR", "message": f"Contract leaves the local-only boundary: {label}"})

    status = "ERROR" if findings else "OK"
    return {
        "status": status,
        "contracts_checked": len(checked),
        "expected_commands": tuple(ACTIVE_READONLY_ALLOWLIST),
        "result_keys": LOCAL_CAPABILITY_RESULT_KEYS,
        "findings": findings,
    }


def format_local_capability_contracts() -> str:
    lines = [
        "Local Typed Capability Contracts",
        f"contract_version: {CAPABILITY_CONTRACT_VERSION}",
        f"contracts: {len(LOCAL_CAPABILITY_CONTRACTS)}",
        f"transport: {LOCAL_CAPABILITY_TRANSPORT}",
        "external_exposure: false",
        "result_envelope: structuredContent + content + _meta",
        "",
        "Contracts:",
    ]
    for contract in LOCAL_CAPABILITY_CONTRACTS:
        annotations = contract.annotations.to_dict()
        lines.append(
            f"- {contract.name} -> {contract.command} "
            f"[readOnlyHint={str(annotations['readOnlyHint']).lower()} "
            f"destructiveHint={str(annotations['destructiveHint']).lower()} "
            f"openWorldHint={str(annotations['openWorldHint']).lower()} "
            f"idempotentHint={str(annotations['idempotentHint']).lower()}]"
        )
    lines.extend(
        [
            "",
            "Boundary:",
            "- Local metadata and result shaping only; no MCP server, network transport, external host, command execution, or store write.",
        ]
    )
    return "\n".join(lines)


def _detect_status(output: str) -> str:
    match = _STATUS_PATTERN.search(output)
    if match:
        return match.group(1).upper()
    unknown_count = re.search(r"^(?:unknown_warnings|unknown_count):\s*(\d+)\b", output, re.IGNORECASE | re.MULTILINE)
    if unknown_count:
        return "OK" if int(unknown_count.group(1)) == 0 else "WARN"
    return "UNKNOWN"


def _first_nonempty_line(output: str, *, max_chars: int = 160) -> str:
    first = next((line.strip() for line in output.splitlines() if line.strip()), "")
    if len(first) <= max_chars:
        return first
    return first[: max_chars - 3].rstrip() + "..."
