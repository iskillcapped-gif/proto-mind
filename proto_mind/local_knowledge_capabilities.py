"""Typed, local-only search/fetch capabilities over the Native Library.

These contracts intentionally have no generic dispatcher, model integration,
network transport, or mutation path. The private Native stdio bridge exposes
the two exact callbacks separately and keeps the legacy library methods as a
compatibility fallback for older app bundles.
"""
from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from proto_mind.native_library import MAX_SOURCE_RECORDS, NativeLibrary, SOURCES


LOCAL_KNOWLEDGE_CONTRACT_VERSION = 1
LOCAL_KNOWLEDGE_TRANSPORT = "private_stdio"
LOCAL_KNOWLEDGE_RESULT_KEYS = ("structuredContent", "content", "_meta")
LOCAL_KNOWLEDGE_ANNOTATIONS = {
    "readOnlyHint": True,
    "destructiveHint": False,
    "openWorldHint": False,
    "idempotentHint": True,
}


@dataclass(frozen=True)
class LocalKnowledgeCapability:
    name: str
    title: str
    description: str
    input_schema: Mapping[str, Any]
    output_schema: Mapping[str, Any]

    def to_descriptor(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "title": self.title,
            "description": self.description,
            "inputSchema": deepcopy(dict(self.input_schema)),
            "outputSchema": deepcopy(dict(self.output_schema)),
            "annotations": dict(LOCAL_KNOWLEDGE_ANNOTATIONS),
            "_meta": {
                "proto_mind": {
                    "contract_version": LOCAL_KNOWLEDGE_CONTRACT_VERSION,
                    "local_only": True,
                    "transport": LOCAL_KNOWLEDGE_TRANSPORT,
                    "network_access": False,
                    "store_mutation": False,
                    "model_dispatch": False,
                }
            },
        }


def _search_input_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "collection": {"type": "string", "enum": sorted(SOURCES)},
            "query": {"type": "string", "maxLength": 200},
            "filter": {"type": "string", "enum": ["current", "history", "all"]},
            "offset": {"type": "integer", "minimum": 0, "maximum": MAX_SOURCE_RECORDS * 2},
        },
        "required": ["collection"],
        "additionalProperties": False,
    }


def _fetch_input_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "collection": {"type": "string", "enum": sorted(SOURCES)},
            "record_key": {"type": "string", "minLength": 1, "maxLength": 220},
            "expected_sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
        },
        "required": ["collection", "record_key"],
        "additionalProperties": False,
    }


def _output_schema(schema: str) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "schema": {"type": "string", "const": schema},
            "read_only": {"type": "boolean", "const": True},
            "collection": {"type": "string", "enum": sorted(SOURCES)},
        },
        "required": ["schema", "read_only", "collection"],
        "additionalProperties": True,
    }


LOCAL_KNOWLEDGE_CAPABILITIES = (
    LocalKnowledgeCapability(
        name="search",
        title="Search local Proto-Mind knowledge",
        description="Use this when the operator needs to search local memory, goals, or skills without changing them.",
        input_schema=_search_input_schema(),
        output_schema=_output_schema("proto_mind.native_library.page.v1"),
    ),
    LocalKnowledgeCapability(
        name="fetch",
        title="Fetch one local Proto-Mind record",
        description="Use this when the operator selects one local memory, goal, or skill record for bounded inspection.",
        input_schema=_fetch_input_schema(),
        output_schema=_output_schema("proto_mind.native_library.detail.v1"),
    ),
)


def local_knowledge_descriptors() -> list[dict[str, Any]]:
    return [contract.to_descriptor() for contract in LOCAL_KNOWLEDGE_CAPABILITIES]


def _result(name: str, structured: dict[str, Any], summary: str) -> dict[str, Any]:
    return {
        "structuredContent": structured,
        "content": [{"type": "text", "text": summary}],
        "_meta": {
            "proto_mind": {
                "capability": name,
                "contract_version": LOCAL_KNOWLEDGE_CONTRACT_VERSION,
                "local_only": True,
                "transport": LOCAL_KNOWLEDGE_TRANSPORT,
                "network_access": False,
                "store_mutation": False,
                "model_dispatch": False,
            }
        },
    }


def _validate_params(params: Mapping[str, Any], allowed: set[str]) -> None:
    if not isinstance(params, Mapping) or any(not isinstance(key, str) for key in params):
        raise ValueError("Local knowledge capability parameters must be an object.")
    unexpected = set(params) - allowed
    if unexpected:
        raise ValueError("Unexpected local knowledge capability parameter.")


def search_local_knowledge(library: NativeLibrary, params: Mapping[str, Any]) -> dict[str, Any]:
    _validate_params(params, {"collection", "query", "filter", "offset"})
    page = library.page(
        params.get("collection"),
        query=params.get("query", ""),
        filter=params.get("filter", "current"),
        offset=params.get("offset", 0),
    )
    summary = (
        f"Local search returned {page['matching_records']} matching "
        f"{page['collection']} records. No store was changed."
    )
    return _result("search", page, summary)


def fetch_local_knowledge(library: NativeLibrary, params: Mapping[str, Any]) -> dict[str, Any]:
    _validate_params(params, {"collection", "record_key", "expected_sha256"})
    detail = library.inspect(
        params.get("collection"),
        params.get("record_key"),
        expected_sha256=params.get("expected_sha256", ""),
    )
    state = "found" if detail["item"] is not None else "not found"
    summary = f"Local {detail['collection']} record {state}. No store was changed."
    return _result("fetch", detail, summary)


def local_knowledge_capability_doctor() -> dict[str, Any]:
    findings: list[dict[str, str]] = []
    names = [contract.name for contract in LOCAL_KNOWLEDGE_CAPABILITIES]
    if names != ["search", "fetch"] or len(set(names)) != len(names):
        findings.append({"severity": "ERROR", "message": "Local knowledge capability names drifted."})
    for contract in LOCAL_KNOWLEDGE_CAPABILITIES:
        descriptor = contract.to_descriptor()
        if not contract.description.startswith("Use this when"):
            findings.append({"severity": "ERROR", "message": f"Missing usage cue: {contract.name}"})
        if descriptor["annotations"] != LOCAL_KNOWLEDGE_ANNOTATIONS:
            findings.append({"severity": "ERROR", "message": f"Unsafe annotations: {contract.name}"})
        meta = descriptor["_meta"]["proto_mind"]
        if meta != {
            "contract_version": LOCAL_KNOWLEDGE_CONTRACT_VERSION,
            "local_only": True,
            "transport": LOCAL_KNOWLEDGE_TRANSPORT,
            "network_access": False,
            "store_mutation": False,
            "model_dispatch": False,
        }:
            findings.append({"severity": "ERROR", "message": f"Local boundary drift: {contract.name}"})
    return {
        "status": "ERROR" if findings else "OK",
        "contracts_checked": len(LOCAL_KNOWLEDGE_CAPABILITIES),
        "result_keys": LOCAL_KNOWLEDGE_RESULT_KEYS,
        "findings": findings,
    }
