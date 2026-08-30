from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from html import escape
from typing import Any

from proto_mind.capability_contracts import (
    LOCAL_CAPABILITY_RESULT_KEYS,
    LOCAL_CAPABILITY_TRANSPORT,
    build_local_capability_result,
    get_local_capability_contract,
)


LOCAL_CAPABILITY_CARD_BADGES = ("LOCAL", "READ ONLY", "NO NETWORK")
LOCAL_CAPABILITY_CARD_STATUSES = frozenset({"OK", "WARN", "BLOCKED", "ERROR", "UNKNOWN"})


@dataclass(frozen=True)
class LocalCapabilityCardViewModel:
    contract_name: str
    title: str
    command: str
    status: str
    summary: str
    body: str
    local_only: bool
    transport: str
    read_only: bool
    badges: tuple[str, ...] = LOCAL_CAPABILITY_CARD_BADGES


def project_local_capability_card(
    user_input: str,
    response: str,
) -> LocalCapabilityCardViewModel | None:
    """Project an exact local capability result into a presentation-only model."""
    if not isinstance(user_input, str) or not isinstance(response, str):
        return None
    command = " ".join(user_input.strip().lower().split())
    contract = get_local_capability_contract(command)
    if contract is None or command != contract.command:
        return None

    envelope = build_local_capability_result(command, response).to_mcp_result()
    if tuple(envelope) != LOCAL_CAPABILITY_RESULT_KEYS:
        return None
    structured = envelope.get("structuredContent")
    content = envelope.get("content")
    meta = envelope.get("_meta")
    if not isinstance(structured, Mapping) or not isinstance(content, list) or not isinstance(meta, Mapping):
        return None
    if len(content) != 1 or not isinstance(content[0], Mapping):
        return None
    text_item = content[0]
    proto_meta = meta.get("proto_mind")
    if not isinstance(proto_meta, Mapping):
        return None
    if not _has_safe_local_boundary(proto_meta):
        return None
    if (
        structured.get("command") != contract.command
        or structured.get("contract") != contract.name
        or structured.get("read_only") is not True
        or structured.get("local_only") is not True
        or text_item.get("type") != "text"
        or text_item.get("text") != response
    ):
        return None

    status = str(structured.get("status", "UNKNOWN")).upper()
    if status not in LOCAL_CAPABILITY_CARD_STATUSES:
        status = "UNKNOWN"
    summary = str(structured.get("summary", "")).strip() or contract.title
    return LocalCapabilityCardViewModel(
        contract_name=contract.name,
        title=contract.title,
        command=contract.command,
        status=status,
        summary=summary,
        body=response,
        local_only=True,
        transport=LOCAL_CAPABILITY_TRANSPORT,
        read_only=True,
    )


def render_local_capability_card_html(view_model: LocalCapabilityCardViewModel) -> str:
    """Render a fully escaped card for Qt rich text."""
    status_class = view_model.status.lower()
    badges = " ".join(
        f"<span class='capability-badge'>{escape(badge)}</span>"
        for badge in view_model.badges
    )
    return (
        "<div class='message-block'>"
        f"<div class='capability-card capability-status-{status_class}'>"
        "<div class='capability-kicker'>PROTO-MIND LOCAL CAPABILITY</div>"
        f"<div class='capability-title'>{escape(view_model.title)}</div>"
        f"<div class='capability-summary'>{escape(view_model.summary)}</div>"
        "<div class='capability-meta'>"
        f"<span class='capability-command'>{escape(view_model.command)}</span>"
        f"<span class='capability-status'>{escape(view_model.status)}</span>"
        "</div>"
        f"<div class='capability-badges'>{badges}</div>"
        f"<pre class='capability-output'>{escape(view_model.body)}</pre>"
        "<div class='capability-footnote'>"
        "Presentation-only typed view | original local report preserved | text fallback available"
        "</div>"
        "</div>"
        "</div>"
    )


def build_local_capability_card_html(user_input: str, response: str) -> str | None:
    """Build a typed card or fail closed to the existing text renderer."""
    try:
        view_model = project_local_capability_card(user_input, response)
        return render_local_capability_card_html(view_model) if view_model else None
    except Exception:
        # A presentation enhancement must never break the shared desktop response path.
        return None


def _has_safe_local_boundary(meta: Mapping[str, Any]) -> bool:
    return (
        meta.get("local_only") is True
        and meta.get("transport") == LOCAL_CAPABILITY_TRANSPORT
        and meta.get("network_access") is False
        and meta.get("store_mutation") is False
        and meta.get("external_exposure") is False
    )
