"""Read-only Native Persona preview contract.

The preview describes the checked-in Brother kernel, a private read-only
Identity projection, and factual Native runtime controls. It is deliberately
outside provider prompts and never performs retrieval, model dispatch, store
writes, command execution, or permission changes.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping
from uuid import UUID

from proto_mind.native_desk import injection_state
from proto_mind.persona_engine import (
    MAX_CONTEXT_CHARS,
    PersonaContextCompiler,
    PersonaRuntimeContext,
    PersonaTaskContext,
    PersonaValidationError,
    render_persona_snapshot,
    validate_persona_snapshot,
    workspace_reference,
)


PERSONA_PREVIEW_SCHEMA = "proto_mind.native_persona_preview.v1"
_REQUEST_FIELDS = {
    "conversation_id",
    "provider",
    "model",
    "cloud_consent",
    "access_mode",
    "workspace_root",
    "access_token",
}
_REQUIRED_REQUEST_FIELDS = {
    "conversation_id",
    "provider",
    "model",
    "cloud_consent",
    "access_mode",
}
_PREVIEW_FIELDS = {
    "schema",
    "read_only",
    "no_execution",
    "no_model_call",
    "no_network_call",
    "no_retrieval",
    "no_store_write",
    "production_prompt_active",
    "private_reasoning_included",
    "context_injection_changed",
    "context_injection_state",
    "snapshot",
    "rendered_preview",
    "source_summary",
    "notices",
}
_SOURCE_FIELDS = {
    "kernel",
    "identity",
    "memory",
    "runtime",
    "workspace",
    "full_access_grant_verified",
}


def _normalized_text(value: object, label: str, *, maximum: int, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or "\x00" in value or "\r" in value or "\n" in value:
        raise ValueError(f"Invalid {label}.")
    normalized = " ".join(value.split())
    if value != normalized or (not normalized and not allow_empty) or len(normalized) > maximum:
        raise ValueError(f"Invalid {label}.")
    return normalized


@dataclass(frozen=True)
class NativePersonaRequest:
    conversation_id: str
    provider: str
    model: str
    cloud_consent: bool
    access_mode: str
    workspace_root: str | None
    access_token: str | None

    @classmethod
    def parse(cls, value: object) -> "NativePersonaRequest":
        if not isinstance(value, dict) or set(value) - _REQUEST_FIELDS or not _REQUIRED_REQUEST_FIELDS <= set(value):
            raise ValueError("Persona preview request has an invalid shape.")
        try:
            conversation_id = str(UUID(str(value["conversation_id"])))
        except (TypeError, ValueError, AttributeError):
            raise ValueError("Invalid Persona preview conversation id.") from None
        provider = value["provider"]
        if provider not in {"codex", "ollama", "mock"}:
            raise ValueError("Unknown Persona preview provider.")
        model = _normalized_text(value["model"], "Persona preview model", maximum=160, allow_empty=True)
        if type(value["cloud_consent"]) is not bool:
            raise ValueError("Invalid Persona preview cloud-consent state.")
        access_mode = value["access_mode"]
        if access_mode not in {"chat", "full_access"}:
            raise ValueError("Unknown Persona preview access mode.")
        workspace_root = value.get("workspace_root")
        if workspace_root is not None:
            if (not isinstance(workspace_root, str) or not workspace_root or len(workspace_root) > 4096
                    or any(character in workspace_root for character in ("\x00", "\r", "\n"))
                    or not Path(workspace_root).is_absolute()):
                raise ValueError("Persona preview workspace must be absolute.")
        access_token = value.get("access_token")
        if access_token is not None:
            access_token = _normalized_text(access_token, "Persona preview access token", maximum=100)
        if access_mode == "chat" and access_token is not None:
            raise ValueError("Chat Persona preview cannot receive a Full Mac token.")
        return cls(
            conversation_id=conversation_id,
            provider=provider,
            model=model,
            cloud_consent=value["cloud_consent"],
            access_mode=access_mode,
            workspace_root=workspace_root,
            access_token=access_token,
        )


def build_native_persona_preview(
    project_root: Path,
    request: NativePersonaRequest,
    *,
    workspace: Path | None,
    full_access_grant_verified: bool,
    computer_use_available: bool,
    ollama_model: str,
) -> dict[str, Any]:
    if type(full_access_grant_verified) is not bool or type(computer_use_available) is not bool:
        raise ValueError("Persona preview runtime evidence is invalid.")
    if request.workspace_root is None and workspace is not None:
        raise ValueError("Persona preview workspace evidence is inconsistent.")
    if request.workspace_root is not None and workspace is None:
        raise ValueError("Persona preview workspace was not verified.")

    workspace_id, workspace_label = ("unbound", "unbound")
    if workspace is not None:
        workspace_id, workspace_label = workspace_reference(workspace)

    provider = {
        "codex": "codex_subscription",
        "ollama": "ollama",
        "mock": "mock",
    }[request.provider]
    if request.provider == "codex":
        model = request.model or "account_default_unresolved"
        access_mode = request.access_mode
        if access_mode == "full_access":
            if request.cloud_consent is not True or not full_access_grant_verified or workspace is None:
                raise ValueError("Full Mac Persona preview requires the current explicit grant and workspace.")
            tools = ["shell_and_files", "web_search"]
            if computer_use_available:
                tools.append("computer_use")
            runtime = PersonaRuntimeContext(
                provider=provider,
                model=model,
                access_mode="full_access",
                workspace_id=workspace_id,
                workspace_label=workspace_label,
                network_state="available",
                tools=tuple(sorted(tools)),
                can_write_workspace=True,
                can_control_computer=computer_use_available,
                can_use_web=True,
                authorization_source="operator_explicit_turn_grant",
            )
        else:
            if full_access_grant_verified:
                raise ValueError("Chat Persona preview cannot claim a verified Full Mac grant.")
            runtime = PersonaRuntimeContext(
                provider=provider,
                model=model,
                access_mode="chat",
                workspace_id=workspace_id,
                workspace_label=workspace_label,
                network_state="disabled",
            )
    elif request.provider == "ollama":
        if request.access_mode != "chat" or full_access_grant_verified:
            raise ValueError("Local Persona preview cannot claim Full Mac authority.")
        runtime = PersonaRuntimeContext(
            provider=provider,
            model=request.model or _normalized_text(ollama_model, "Ollama model", maximum=160),
            access_mode="local",
            workspace_id=workspace_id,
            workspace_label=workspace_label,
            network_state="local_only",
            authorization_source="local_runtime",
        )
    else:
        if request.access_mode != "chat" or full_access_grant_verified:
            raise ValueError("Mock Persona preview cannot claim Full Mac authority.")
        runtime = PersonaRuntimeContext(
            provider=provider,
            model=request.model or "deterministic_mock",
            access_mode="mock",
            workspace_id=workspace_id,
            workspace_label=workspace_label,
            network_state="disabled",
        )

    generated_at = datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")
    snapshot = PersonaContextCompiler().compile_from_project(
        Path(project_root),
        retrieved_memory=[],
        task=PersonaTaskContext(kind="unknown", risk="unknown", workspace_id=workspace_id),
        runtime=runtime,
        generated_at=generated_at,
    )
    context = injection_state(Path(project_root))
    state = context.get("state") if isinstance(context, dict) else "unknown"
    if state not in {"enabled", "disabled", "default_disabled", "unknown"}:
        state = "unknown"
    notices = [
        "Read-only preview only; this PersonaSnapshot is not active in any provider prompt.",
        "No model call, network call, memory retrieval, store write, command execution, or permission change occurred.",
        "Runtime facts describe existing controls and do not grant authority.",
        "No memory was selected; retrieval was not run.",
    ]
    if state == "enabled":
        notices.append("Context Injection is already enabled; this preview did not read or apply its payload.")
    if full_access_grant_verified:
        notices.append("The current per-conversation Full Mac grant was verified but not used.")
    result = {
        "schema": PERSONA_PREVIEW_SCHEMA,
        "read_only": True,
        "no_execution": True,
        "no_model_call": True,
        "no_network_call": True,
        "no_retrieval": True,
        "no_store_write": True,
        "production_prompt_active": False,
        "private_reasoning_included": False,
        "context_injection_changed": False,
        "context_injection_state": state,
        "snapshot": snapshot.to_dict(),
        "rendered_preview": render_persona_snapshot(snapshot),
        "source_summary": {
            "kernel": "checked_in_versioned",
            "identity": "private_read_only",
            "memory": "none_selected_no_retrieval",
            "runtime": "current_native_controls",
            "workspace": "opaque_reference_only",
            "full_access_grant_verified": full_access_grant_verified,
        },
        "notices": notices,
    }
    return validate_native_persona_preview(result)


def validate_native_persona_preview(value: object) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != _PREVIEW_FIELDS:
        raise PersonaValidationError("Native Persona preview has an invalid shape.")
    if value["schema"] != PERSONA_PREVIEW_SCHEMA:
        raise PersonaValidationError("Native Persona preview schema is unsupported.")
    for field in (
        "read_only",
        "no_execution",
        "no_model_call",
        "no_network_call",
        "no_retrieval",
        "no_store_write",
    ):
        if value[field] is not True:
            raise PersonaValidationError(f"Native Persona preview requires {field}=true.")
    for field in ("production_prompt_active", "private_reasoning_included", "context_injection_changed"):
        if value[field] is not False:
            raise PersonaValidationError(f"Native Persona preview requires {field}=false.")
    if value["context_injection_state"] not in {"enabled", "disabled", "default_disabled", "unknown"}:
        raise PersonaValidationError("Native Persona preview Context Injection state is invalid.")
    snapshot = validate_persona_snapshot(value["snapshot"])
    if snapshot.communication_preferences or snapshot.relevant_memories or snapshot.omitted_memory_count:
        raise PersonaValidationError("Native Persona preview cannot imply memory retrieval.")
    rendered = value["rendered_preview"]
    if not isinstance(rendered, str) or len(rendered) > MAX_CONTEXT_CHARS or rendered != render_persona_snapshot(snapshot):
        raise PersonaValidationError("Native Persona rendered preview does not match its snapshot.")
    source = value["source_summary"]
    if not isinstance(source, dict) or set(source) != _SOURCE_FIELDS:
        raise PersonaValidationError("Native Persona preview source summary is invalid.")
    expected_sources = {
        "kernel": "checked_in_versioned",
        "identity": "private_read_only",
        "memory": "none_selected_no_retrieval",
        "runtime": "current_native_controls",
        "workspace": "opaque_reference_only",
    }
    if any(source.get(key) != expected for key, expected in expected_sources.items()):
        raise PersonaValidationError("Native Persona preview source boundary changed.")
    if type(source.get("full_access_grant_verified")) is not bool:
        raise PersonaValidationError("Native Persona preview grant evidence is invalid.")
    if source["full_access_grant_verified"] != (snapshot.self_model.access_mode == "full_access"):
        raise PersonaValidationError("Native Persona preview grant evidence and runtime disagree.")
    notices = value["notices"]
    if not isinstance(notices, list) or not 4 <= len(notices) <= 8:
        raise PersonaValidationError("Native Persona preview notices are invalid.")
    for notice in notices:
        if not isinstance(notice, str) or not notice or len(notice) > 400 or "\x00" in notice:
            raise PersonaValidationError("Native Persona preview notice is invalid.")
    return value
