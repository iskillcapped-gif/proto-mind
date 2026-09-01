"""Model-independent Persona Engine foundation.

The module is intentionally detached from the live prompt path. It reads an
explicit identity projection and already-selected memories, validates factual
runtime authority, and returns an immutable one-turn snapshot. It never runs a
model, performs retrieval, grants authority, or writes a store.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Iterable, Mapping, Sequence

from proto_mind.identity import IdentityStore
from proto_mind.memory_provenance import verify_memory_provenance
from proto_mind.models import MemoryRecord


KERNEL_SCHEMA = "proto_mind.persona_kernel.v1"
SNAPSHOT_SCHEMA = "proto_mind.persona_snapshot.v1"
CHANGE_CANDIDATE_SCHEMA = "proto_mind.persona_change_candidate.v1"
DEFAULT_KERNEL_DIR = Path(__file__).with_name("persona")

MAX_IDENTITY_ITEMS = 12
MAX_SELECTED_MEMORIES = 8
MAX_PREFERENCES = 4
MAX_MEMORY_INPUTS = 32
MAX_MEMORY_CONTENT_CHARS = 600
MAX_CONTEXT_CHARS = 16_000

_IDENTIFIER_RE = re.compile(r"[a-z][a-z0-9_-]{0,63}\Z")
_VERSION_RE = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+\Z")
_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
_WORKSPACE_RE = re.compile(r"(?:unbound|workspace_[0-9a-f]{16})\Z")

_TASK_KINDS = {
    "conversation",
    "implementation",
    "review",
    "memory",
    "computer_operation",
    "unknown",
}
_RISK_LEVELS = {"low", "medium", "high", "unknown"}
_ACCESS_MODES = {"chat", "full_access", "local", "mock", "unknown"}
_NETWORK_STATES = {"disabled", "local_only", "available", "unknown"}
_AUTHORIZATION_SOURCES = {
    "none",
    "operator_explicit_turn_grant",
    "local_runtime",
    "unknown",
}
_CHANGE_TARGETS = {
    "voice.tone",
    "voice.preferred_address",
    "voice.humor",
    "voice.emoji",
    "communication.response_detail",
}


class PersonaValidationError(ValueError):
    """Raised when persona input is malformed, widened, or unsupported."""


def _canonical(value: Mapping[str, Any]) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise PersonaValidationError("Persona data is not canonical JSON.") from exc


def _hash(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _exact_keys(value: object, expected: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != expected:
        raise PersonaValidationError(f"{label} has an invalid shape.")
    return value


def _text(
    value: object,
    label: str,
    *,
    maximum: int = 400,
    allow_empty: bool = False,
    require_normalized: bool = False,
) -> str:
    if not isinstance(value, str) or "\x00" in value or "\r" in value:
        raise PersonaValidationError(f"{label} is invalid.")
    normalized = " ".join(value.split())
    if (not normalized and not allow_empty) or len(normalized) > maximum:
        raise PersonaValidationError(f"{label} is invalid.")
    if require_normalized and value != normalized:
        raise PersonaValidationError(f"{label} is not normalized.")
    return normalized


def _timestamp(value: object, label: str) -> str:
    text = _text(value, label, maximum=80)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise PersonaValidationError(f"{label} is invalid.") from exc
    if parsed.tzinfo is None:
        raise PersonaValidationError(f"{label} must include a timezone.")
    return text


def _identifier(value: object, label: str) -> str:
    text = _text(value, label, maximum=64)
    if not _IDENTIFIER_RE.fullmatch(text):
        raise PersonaValidationError(f"{label} is invalid.")
    return text


def _bounded_items(value: object, label: str, *, minimum: int, maximum: int) -> tuple[str, ...]:
    if not isinstance(value, list) or not minimum <= len(value) <= maximum:
        raise PersonaValidationError(f"{label} is invalid.")
    items = tuple(_text(item, f"{label} item") for item in value)
    if len({item.casefold() for item in items}) != len(items):
        raise PersonaValidationError(f"{label} contains duplicates.")
    return items


@dataclass(frozen=True)
class PersonaVoice:
    tone: str
    preferred_address: str
    humor: str
    emoji: str
    adaptation: str

    @classmethod
    def from_dict(cls, value: object) -> "PersonaVoice":
        row = _exact_keys(
            value,
            {"tone", "preferred_address", "humor", "emoji", "adaptation"},
            "Persona voice",
        )
        voice = cls(
            tone=_identifier(row["tone"], "Persona voice tone"),
            preferred_address=_text(row["preferred_address"], "Persona preferred address", maximum=80),
            humor=_identifier(row["humor"], "Persona humor"),
            emoji=_identifier(row["emoji"], "Persona emoji policy"),
            adaptation=_identifier(row["adaptation"], "Persona adaptation"),
        )
        if voice.adaptation != "contextual_without_modes":
            raise PersonaValidationError("Persona adaptation must remain contextual without modes.")
        return voice

    def to_dict(self) -> dict[str, str]:
        return {
            "tone": self.tone,
            "preferred_address": self.preferred_address,
            "humor": self.humor,
            "emoji": self.emoji,
            "adaptation": self.adaptation,
        }


@dataclass(frozen=True)
class PersonaKernel:
    schema: str
    persona_id: str
    version: str
    display_name: str
    role: str
    default_language: str
    core_laws: tuple[str, ...]
    voice: PersonaVoice
    boundaries: tuple[str, ...]

    @classmethod
    def from_dict(cls, value: object) -> "PersonaKernel":
        row = _exact_keys(
            value,
            {
                "schema",
                "persona_id",
                "version",
                "display_name",
                "role",
                "default_language",
                "core_laws",
                "voice",
                "boundaries",
            },
            "Persona Kernel",
        )
        if row["schema"] != KERNEL_SCHEMA:
            raise PersonaValidationError("Persona Kernel schema is unsupported.")
        version = _text(row["version"], "Persona Kernel version", maximum=32)
        if not _VERSION_RE.fullmatch(version):
            raise PersonaValidationError("Persona Kernel version is invalid.")
        kernel = cls(
            schema=KERNEL_SCHEMA,
            persona_id=_identifier(row["persona_id"], "Persona id"),
            version=version,
            display_name=_text(row["display_name"], "Persona display name", maximum=80),
            role=_text(row["role"], "Persona role"),
            default_language=_identifier(row["default_language"], "Persona language"),
            core_laws=_bounded_items(row["core_laws"], "Persona core laws", minimum=4, maximum=16),
            voice=PersonaVoice.from_dict(row["voice"]),
            boundaries=_bounded_items(row["boundaries"], "Persona boundaries", minimum=3, maximum=16),
        )
        if kernel.persona_id != "brother" or kernel.display_name != "Brother":
            raise PersonaValidationError("The foundation supports only the single Brother personality.")
        return kernel

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "persona_id": self.persona_id,
            "version": self.version,
            "display_name": self.display_name,
            "role": self.role,
            "default_language": self.default_language,
            "core_laws": list(self.core_laws),
            "voice": self.voice.to_dict(),
            "boundaries": list(self.boundaries),
        }


class PersonaKernelStore:
    """Read-only loader for checked-in, versioned persona kernels."""

    def __init__(self, root: Path = DEFAULT_KERNEL_DIR) -> None:
        self.root = Path(root)

    def versions(self, persona_id: str = "brother") -> tuple[str, ...]:
        identity = _identifier(persona_id, "Persona id")
        if not self.root.is_dir() or self.root.is_symlink():
            raise PersonaValidationError("Persona Kernel directory is unavailable or unsafe.")
        versions = []
        for path in self.root.glob(f"{identity}-*.json"):
            if path.is_symlink() or not path.is_file():
                continue
            version = path.stem[len(identity) + 1 :]
            if _VERSION_RE.fullmatch(version):
                versions.append(version)
        if not versions:
            raise PersonaValidationError("No supported Persona Kernel version exists.")
        return tuple(sorted(set(versions), key=lambda item: tuple(int(part) for part in item.split("."))))

    def load(self, persona_id: str = "brother", version: str | None = None) -> PersonaKernel:
        identity = _identifier(persona_id, "Persona id")
        selected = self.versions(identity)[-1] if version is None else _text(version, "Persona version", maximum=32)
        if not _VERSION_RE.fullmatch(selected):
            raise PersonaValidationError("Persona version is invalid.")
        path = self.root / f"{identity}-{selected}.json"
        try:
            if path.is_symlink() or not path.is_file() or path.resolve().parent != self.root.resolve():
                raise PersonaValidationError("Persona Kernel path is unavailable or unsafe.")
            raw = path.read_text(encoding="utf-8")
            parsed = json.loads(raw)
        except PersonaValidationError:
            raise
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise PersonaValidationError("Persona Kernel cannot be read.") from exc
        kernel = PersonaKernel.from_dict(parsed)
        if kernel.persona_id != identity or kernel.version != selected:
            raise PersonaValidationError("Persona Kernel filename and identity do not match.")
        return kernel


@dataclass(frozen=True)
class PersonaRuntimeContext:
    provider: str
    model: str
    access_mode: str
    workspace_id: str
    workspace_label: str
    network_state: str
    tools: tuple[str, ...] = ()
    can_write_workspace: bool = False
    can_control_computer: bool = False
    can_use_web: bool = False
    authorization_source: str = "none"

    def __post_init__(self) -> None:
        _identifier(self.provider, "Persona runtime provider")
        _text(self.model, "Persona runtime model", maximum=160, require_normalized=True)
        if self.access_mode not in _ACCESS_MODES or self.network_state not in _NETWORK_STATES:
            raise PersonaValidationError("Persona runtime access or network state is invalid.")
        if not _WORKSPACE_RE.fullmatch(self.workspace_id):
            raise PersonaValidationError("Persona runtime workspace id is invalid.")
        _text(self.workspace_label, "Persona runtime workspace label", maximum=120, require_normalized=True)
        if self.authorization_source not in _AUTHORIZATION_SOURCES:
            raise PersonaValidationError("Persona runtime authorization source is invalid.")
        if any(type(value) is not bool for value in (
            self.can_write_workspace,
            self.can_control_computer,
            self.can_use_web,
        )):
            raise PersonaValidationError("Persona runtime capability flags are invalid.")
        if len(self.tools) > 32 or tuple(sorted(set(self.tools))) != self.tools:
            raise PersonaValidationError("Persona runtime tools must be unique and sorted.")
        for tool in self.tools:
            _identifier(tool, "Persona runtime tool")
        if self.access_mode == "chat" and (
            self.tools or self.can_write_workspace or self.can_control_computer or self.can_use_web
        ):
            raise PersonaValidationError("Chat mode cannot claim tool authority.")
        if self.access_mode == "full_access" and self.authorization_source != "operator_explicit_turn_grant":
            raise PersonaValidationError("Full access lacks an explicit operator turn grant.")
        if self.can_write_workspace and "shell_and_files" not in self.tools:
            raise PersonaValidationError("Workspace write capability lacks a matching tool.")
        if self.can_control_computer and "computer_use" not in self.tools:
            raise PersonaValidationError("Computer control capability lacks a matching tool.")
        if self.can_use_web and "web_search" not in self.tools:
            raise PersonaValidationError("Web capability lacks a matching tool.")
        if (
            self.can_write_workspace or self.can_control_computer or self.can_use_web
        ) and self.authorization_source in {"none", "unknown"}:
            raise PersonaValidationError("Runtime capability lacks a factual authorization source.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "model": self.model,
            "access_mode": self.access_mode,
            "workspace_id": self.workspace_id,
            "workspace_label": self.workspace_label,
            "network_state": self.network_state,
            "tools": list(self.tools),
            "can_write_workspace": self.can_write_workspace,
            "can_control_computer": self.can_control_computer,
            "can_use_web": self.can_use_web,
            "authorization_source": self.authorization_source,
        }

    @classmethod
    def from_dict(cls, value: object) -> "PersonaRuntimeContext":
        row = _exact_keys(
            value,
            {
                "provider",
                "model",
                "access_mode",
                "workspace_id",
                "workspace_label",
                "network_state",
                "tools",
                "can_write_workspace",
                "can_control_computer",
                "can_use_web",
                "authorization_source",
            },
            "Persona runtime context",
        )
        tools = row["tools"]
        if not isinstance(tools, list) or not all(isinstance(item, str) for item in tools):
            raise PersonaValidationError("Persona runtime tools are invalid.")
        return cls(
            provider=row["provider"],
            model=row["model"],
            access_mode=row["access_mode"],
            workspace_id=row["workspace_id"],
            workspace_label=row["workspace_label"],
            network_state=row["network_state"],
            tools=tuple(tools),
            can_write_workspace=row["can_write_workspace"],
            can_control_computer=row["can_control_computer"],
            can_use_web=row["can_use_web"],
            authorization_source=row["authorization_source"],
        )


@dataclass(frozen=True)
class PersonaTaskContext:
    kind: str
    risk: str
    goal_id: str = ""
    task_id: str = ""
    workspace_id: str = "unbound"

    def __post_init__(self) -> None:
        if self.kind not in _TASK_KINDS or self.risk not in _RISK_LEVELS:
            raise PersonaValidationError("Persona task kind or risk is invalid.")
        _text(self.goal_id, "Persona goal id", maximum=120, allow_empty=True, require_normalized=True)
        _text(self.task_id, "Persona task id", maximum=120, allow_empty=True, require_normalized=True)
        if not _WORKSPACE_RE.fullmatch(self.workspace_id):
            raise PersonaValidationError("Persona task workspace id is invalid.")

    def to_dict(self) -> dict[str, str]:
        return {
            "kind": self.kind,
            "risk": self.risk,
            "goal_id": self.goal_id,
            "task_id": self.task_id,
            "workspace_id": self.workspace_id,
        }

    @classmethod
    def from_dict(cls, value: object) -> "PersonaTaskContext":
        row = _exact_keys(value, {"kind", "risk", "goal_id", "task_id", "workspace_id"}, "Persona task")
        return cls(**row)


@dataclass(frozen=True)
class PersonaIdentityItem:
    item_id: str
    kind: str
    text: str

    def __post_init__(self) -> None:
        _text(self.item_id, "Persona identity item id", maximum=120, require_normalized=True)
        if self.kind not in {"value", "principle", "boundary"}:
            raise PersonaValidationError("Persona identity item kind is invalid.")
        _text(self.text, "Persona identity item text", require_normalized=True)

    def to_dict(self) -> dict[str, str]:
        return {"item_id": self.item_id, "kind": self.kind, "text": self.text}

    @classmethod
    def from_dict(cls, value: object) -> "PersonaIdentityItem":
        return cls(**_exact_keys(value, {"item_id", "kind", "text"}, "Persona identity item"))


@dataclass(frozen=True)
class PersonaIdentityProjection:
    source: str
    source_version: int | str
    source_updated_at: str
    product_name: str
    product_role: str
    style: str
    mission: str
    items: tuple[PersonaIdentityItem, ...]

    def __post_init__(self) -> None:
        if self.source != "identity.json":
            raise PersonaValidationError("Persona identity source is invalid.")
        if (
            isinstance(self.source_version, bool)
            or not isinstance(self.source_version, (int, str))
            or (isinstance(self.source_version, str) and len(self.source_version) > 40)
        ):
            raise PersonaValidationError("Persona identity source version is invalid.")
        for label, value, maximum in (
            ("updated_at", self.source_updated_at, 80),
            ("product_name", self.product_name, 120),
            ("product_role", self.product_role, 240),
            ("style", self.style, 240),
            ("mission", self.mission, 400),
        ):
            _text(value, f"Persona identity {label}", maximum=maximum, allow_empty=True, require_normalized=True)
        if len(self.items) > MAX_IDENTITY_ITEMS * 3:
            raise PersonaValidationError("Persona identity projection is too large.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "source_version": self.source_version,
            "source_updated_at": self.source_updated_at,
            "product_name": self.product_name,
            "product_role": self.product_role,
            "style": self.style,
            "mission": self.mission,
            "items": [item.to_dict() for item in self.items],
        }

    @classmethod
    def from_dict(cls, value: object) -> "PersonaIdentityProjection":
        row = _exact_keys(
            value,
            {
                "source",
                "source_version",
                "source_updated_at",
                "product_name",
                "product_role",
                "style",
                "mission",
                "items",
            },
            "Persona identity projection",
        )
        version = row["source_version"]
        if (
            row["source"] != "identity.json"
            or isinstance(version, bool)
            or not isinstance(version, (int, str))
            or (isinstance(version, str) and len(version) > 40)
        ):
            raise PersonaValidationError("Persona identity source is invalid.")
        for field in ("source_updated_at", "product_name", "product_role", "style", "mission"):
            _text(row[field], f"Persona identity {field}", maximum=400, allow_empty=True)
        if not isinstance(row["items"], list):
            raise PersonaValidationError("Persona identity items are invalid.")
        items = tuple(PersonaIdentityItem.from_dict(item) for item in row["items"])
        if len(items) > MAX_IDENTITY_ITEMS * 3:
            raise PersonaValidationError("Persona identity projection is too large.")
        return cls(items=items, **{key: row[key] for key in row if key != "items"})


@dataclass(frozen=True)
class PersonaMemoryReference:
    record_id: str
    memory_type: str
    content: str
    source: str
    source_timestamp: str
    confidence: float | None
    provenance_id: str
    provenance_status: str
    content_truncated: bool
    content_is_instruction: bool = False

    def __post_init__(self) -> None:
        _text(self.record_id, "Persona memory id", maximum=160, require_normalized=True)
        _text(self.memory_type, "Persona memory type", maximum=80, require_normalized=True)
        _text(self.content, "Persona memory content", maximum=MAX_MEMORY_CONTENT_CHARS, require_normalized=True)
        _text(self.source, "Persona memory source", maximum=120, require_normalized=True)
        _text(self.source_timestamp, "Persona memory timestamp", maximum=80, allow_empty=True, require_normalized=True)
        _text(self.provenance_id, "Persona memory provenance id", maximum=160, require_normalized=True)
        if self.provenance_status not in {"verified", "record_source_only"}:
            raise PersonaValidationError("Persona memory provenance status is invalid.")
        if self.confidence is not None and (
            isinstance(self.confidence, bool) or not isinstance(self.confidence, (int, float))
            or not 0.0 <= float(self.confidence) <= 1.0
        ):
            raise PersonaValidationError("Persona memory confidence is invalid.")
        if type(self.content_truncated) is not bool or self.content_is_instruction is not False:
            raise PersonaValidationError("Persona memory content boundary is invalid.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "record_id": self.record_id,
            "memory_type": self.memory_type,
            "content": self.content,
            "source": self.source,
            "source_timestamp": self.source_timestamp,
            "confidence": self.confidence,
            "provenance_id": self.provenance_id,
            "provenance_status": self.provenance_status,
            "content_truncated": self.content_truncated,
            "content_is_instruction": False,
        }

    @classmethod
    def from_dict(cls, value: object) -> "PersonaMemoryReference":
        return cls(**_exact_keys(
            value,
            {
                "record_id",
                "memory_type",
                "content",
                "source",
                "source_timestamp",
                "confidence",
                "provenance_id",
                "provenance_status",
                "content_truncated",
                "content_is_instruction",
            },
            "Persona memory reference",
        ))


@dataclass(frozen=True)
class PersonaSnapshot:
    schema: str
    generated_at: str
    kernel: PersonaKernel
    identity: PersonaIdentityProjection
    communication_preferences: tuple[PersonaMemoryReference, ...]
    relevant_memories: tuple[PersonaMemoryReference, ...]
    task: PersonaTaskContext
    self_model: PersonaRuntimeContext
    notices: tuple[str, ...]
    omitted_memory_count: int
    omitted_identity_item_count: int
    read_only: bool
    authorizes_actions: bool
    context_injection_changed: bool
    snapshot_hash: str

    def material(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "generated_at": self.generated_at,
            "kernel": self.kernel.to_dict(),
            "identity": self.identity.to_dict(),
            "communication_preferences": [item.to_dict() for item in self.communication_preferences],
            "relevant_memories": [item.to_dict() for item in self.relevant_memories],
            "task": self.task.to_dict(),
            "self_model": self.self_model.to_dict(),
            "notices": list(self.notices),
            "omitted_memory_count": self.omitted_memory_count,
            "omitted_identity_item_count": self.omitted_identity_item_count,
            "read_only": self.read_only,
            "authorizes_actions": self.authorizes_actions,
            "context_injection_changed": self.context_injection_changed,
        }

    def to_dict(self) -> dict[str, Any]:
        return {**self.material(), "snapshot_hash": self.snapshot_hash}


def validate_persona_snapshot(value: object) -> PersonaSnapshot:
    row = _exact_keys(
        value,
        {
            "schema",
            "generated_at",
            "kernel",
            "identity",
            "communication_preferences",
            "relevant_memories",
            "task",
            "self_model",
            "notices",
            "omitted_memory_count",
            "omitted_identity_item_count",
            "read_only",
            "authorizes_actions",
            "context_injection_changed",
            "snapshot_hash",
        },
        "PersonaSnapshot",
    )
    if row["schema"] != SNAPSHOT_SCHEMA:
        raise PersonaValidationError("PersonaSnapshot schema is unsupported.")
    generated_at = _timestamp(row["generated_at"], "PersonaSnapshot timestamp")
    preferences = row["communication_preferences"]
    memories = row["relevant_memories"]
    notices = row["notices"]
    if not isinstance(preferences, list) or len(preferences) > MAX_PREFERENCES:
        raise PersonaValidationError("PersonaSnapshot preferences are invalid.")
    if (
        not isinstance(memories, list)
        or len(preferences) + len(memories) > MAX_SELECTED_MEMORIES
    ):
        raise PersonaValidationError("PersonaSnapshot memories are invalid.")
    if not isinstance(notices, list) or len(notices) > 32:
        raise PersonaValidationError("PersonaSnapshot notices are invalid.")
    parsed_notices = tuple(_text(item, "PersonaSnapshot notice") for item in notices)
    if any(type(row[field]) is not int or row[field] < 0 for field in (
        "omitted_memory_count",
        "omitted_identity_item_count",
    )):
        raise PersonaValidationError("PersonaSnapshot omitted counts are invalid.")
    if row["read_only"] is not True or row["authorizes_actions"] is not False:
        raise PersonaValidationError("PersonaSnapshot must remain read-only and non-authorizing.")
    if row["context_injection_changed"] is not False:
        raise PersonaValidationError("PersonaSnapshot cannot change Context Injection.")
    snapshot_hash = row["snapshot_hash"]
    if not isinstance(snapshot_hash, str) or not _SHA256_RE.fullmatch(snapshot_hash):
        raise PersonaValidationError("PersonaSnapshot hash is invalid.")
    snapshot = PersonaSnapshot(
        schema=SNAPSHOT_SCHEMA,
        generated_at=generated_at,
        kernel=PersonaKernel.from_dict(row["kernel"]),
        identity=PersonaIdentityProjection.from_dict(row["identity"]),
        communication_preferences=tuple(PersonaMemoryReference.from_dict(item) for item in preferences),
        relevant_memories=tuple(PersonaMemoryReference.from_dict(item) for item in memories),
        task=PersonaTaskContext.from_dict(row["task"]),
        self_model=PersonaRuntimeContext.from_dict(row["self_model"]),
        notices=parsed_notices,
        omitted_memory_count=row["omitted_memory_count"],
        omitted_identity_item_count=row["omitted_identity_item_count"],
        read_only=True,
        authorizes_actions=False,
        context_injection_changed=False,
        snapshot_hash=snapshot_hash,
    )
    if _hash(snapshot.material()) != snapshot.snapshot_hash:
        raise PersonaValidationError("PersonaSnapshot hash does not verify.")
    return snapshot


class PersonaContextCompiler:
    """Compile existing trusted state into a bounded, non-authorizing snapshot."""

    def __init__(self, kernel_store: PersonaKernelStore | None = None) -> None:
        self.kernel_store = kernel_store or PersonaKernelStore()

    def compile_from_project(
        self,
        project_root: Path,
        *,
        retrieved_memory: Sequence[MemoryRecord],
        task: PersonaTaskContext,
        runtime: PersonaRuntimeContext,
        generated_at: str,
        kernel_version: str | None = None,
    ) -> PersonaSnapshot:
        identity = IdentityStore.from_project_root(Path(project_root)).read_persona_source()
        return self.compile(
            identity_source=identity,
            retrieved_memory=retrieved_memory,
            task=task,
            runtime=runtime,
            generated_at=generated_at,
            kernel_version=kernel_version,
        )

    def compile(
        self,
        *,
        identity_source: Mapping[str, Any],
        retrieved_memory: Sequence[MemoryRecord],
        task: PersonaTaskContext,
        runtime: PersonaRuntimeContext,
        generated_at: str,
        kernel_version: str | None = None,
    ) -> PersonaSnapshot:
        kernel = self.kernel_store.load(version=kernel_version)
        timestamp = _timestamp(generated_at, "PersonaSnapshot timestamp")
        if task.workspace_id != runtime.workspace_id:
            raise PersonaValidationError("Persona task and runtime workspace identities differ.")
        identity, identity_omitted, notices = _project_identity(identity_source)
        preferences, memories, memory_omitted, memory_notices = _project_memories(retrieved_memory)
        notices.extend(memory_notices)
        base = PersonaSnapshot(
            schema=SNAPSHOT_SCHEMA,
            generated_at=timestamp,
            kernel=kernel,
            identity=identity,
            communication_preferences=preferences,
            relevant_memories=memories,
            task=task,
            self_model=runtime,
            notices=tuple(notices),
            omitted_memory_count=memory_omitted,
            omitted_identity_item_count=identity_omitted,
            read_only=True,
            authorizes_actions=False,
            context_injection_changed=False,
            snapshot_hash="",
        )
        snapshot = replace(base, snapshot_hash=_hash(base.material()))
        validate_persona_snapshot(snapshot.to_dict())
        if len(render_persona_snapshot(snapshot)) > MAX_CONTEXT_CHARS:
            raise PersonaValidationError("PersonaSnapshot rendered context exceeds its bound.")
        return snapshot


def _project_identity(
    source: Mapping[str, Any],
) -> tuple[PersonaIdentityProjection, int, list[str]]:
    if not isinstance(source, Mapping):
        raise PersonaValidationError("Identity source is invalid.")
    status = source.get("status")
    if status == "ERROR":
        raise PersonaValidationError("Identity source is unreadable; snapshot refused.")
    if status == "missing":
        return (
            PersonaIdentityProjection(
                source="identity.json",
                source_version="missing",
                source_updated_at="",
                product_name="Proto-Mind",
                product_role="",
                style="",
                mission="",
                items=(),
            ),
            0,
            ["Identity source is missing; only the checked-in Persona Kernel is available."],
        )
    row = _exact_keys(
        dict(source),
        {"status", "version", "updated_at", "profile", "values", "principles", "boundaries"},
        "Identity persona source",
    )
    if row["status"] != "OK" or not isinstance(row["version"], (int, str)):
        raise PersonaValidationError("Identity persona source status is invalid.")
    profile = _exact_keys(row["profile"], {"name", "role", "style", "operator_name", "mission"}, "Identity profile")
    projected: list[PersonaIdentityItem] = []
    omitted = 0
    for section, kind in (("values", "value"), ("principles", "principle"), ("boundaries", "boundary")):
        items = row[section]
        if not isinstance(items, list):
            raise PersonaValidationError(f"Identity {section} is invalid.")
        for item in items[:MAX_IDENTITY_ITEMS]:
            item_row = _exact_keys(item, {"id", "text", "created_at"}, f"Identity {kind}")
            projected.append(PersonaIdentityItem(
                item_id=_text(item_row["id"], f"Identity {kind} id", maximum=120),
                kind=kind,
                text=_text(item_row["text"], f"Identity {kind} text"),
            ))
        omitted += max(0, len(items) - MAX_IDENTITY_ITEMS)
    notices = []
    if omitted:
        notices.append(f"{omitted} identity items were omitted by the snapshot bound.")
    projection = PersonaIdentityProjection(
        source="identity.json",
        source_version=row["version"],
        source_updated_at=_text(row["updated_at"], "Identity updated_at", maximum=80, allow_empty=True),
        product_name=_text(profile["name"], "Identity name", maximum=120, allow_empty=True),
        product_role=_text(profile["role"], "Identity role", maximum=240, allow_empty=True),
        style=_text(profile["style"], "Identity style", maximum=240, allow_empty=True),
        mission=_text(profile["mission"], "Identity mission", maximum=400, allow_empty=True),
        items=tuple(projected),
    )
    return projection, omitted, notices


def _memory_reference(record: MemoryRecord) -> tuple[PersonaMemoryReference, bool]:
    record_id = _text(record.id, "Selected memory id", maximum=160)
    source = _text(record.source, "Selected memory source", maximum=120)
    memory_type = _text(record.type, "Selected memory type", maximum=80)
    content = " ".join(_text(record.content, "Selected memory content", maximum=32_000).split())
    truncated = len(content) > MAX_MEMORY_CONTENT_CHARS
    content = content[:MAX_MEMORY_CONTENT_CHARS].rstrip() if truncated else content
    if record.provenance is None:
        provenance_id = f"memory:{record_id}"
        provenance_status = "record_source_only"
    else:
        checked = verify_memory_provenance(record)
        if not checked.verified:
            raise PersonaValidationError(f"Selected memory {record_id} has invalid provenance.")
        provenance_id = _text(checked.provenance_id, "Selected memory provenance id", maximum=160)
        provenance_status = "verified"
    return PersonaMemoryReference(
        record_id=record_id,
        memory_type=memory_type,
        content=content,
        source=source,
        source_timestamp=_text(record.timestamp, "Selected memory timestamp", maximum=80, allow_empty=True),
        confidence=record.confidence,
        provenance_id=provenance_id,
        provenance_status=provenance_status,
        content_truncated=truncated,
        content_is_instruction=False,
    ), truncated


def _project_memories(
    records: Sequence[MemoryRecord],
) -> tuple[tuple[PersonaMemoryReference, ...], tuple[PersonaMemoryReference, ...], int, list[str]]:
    if not isinstance(records, Sequence) or isinstance(records, (str, bytes)) or len(records) > MAX_MEMORY_INPUTS:
        raise PersonaValidationError("Selected memory input is invalid or too large.")
    preferences: list[PersonaMemoryReference] = []
    memories: list[PersonaMemoryReference] = []
    notices: list[str] = []
    omitted = 0
    seen: set[str] = set()
    for record in records:
        if not isinstance(record, MemoryRecord):
            raise PersonaValidationError("Selected memory input contains an invalid record.")
        if not record.active or record.superseded_by or record.superseded_at:
            omitted += 1
            continue
        if record.id in seen:
            raise PersonaValidationError("Selected memory input contains duplicate ids.")
        seen.add(record.id)
        reference, truncated = _memory_reference(record)
        if truncated:
            notices.append(f"Memory {reference.record_id} was truncated to the snapshot content bound.")
        selected_count = len(preferences) + len(memories)
        if reference.memory_type == "preference":
            if len(preferences) < MAX_PREFERENCES and selected_count < MAX_SELECTED_MEMORIES:
                preferences.append(reference)
            else:
                omitted += 1
        elif selected_count < MAX_SELECTED_MEMORIES:
            memories.append(reference)
        else:
            omitted += 1
    if omitted:
        notices.append(f"{omitted} selected memory records were inactive, superseded, or omitted by bounds.")
    return tuple(preferences), tuple(memories), omitted, notices


def render_persona_snapshot(snapshot: PersonaSnapshot) -> str:
    """Render an inspectable preview; this function is not wired to a provider."""
    validate_persona_snapshot(snapshot.to_dict())
    lines = [
        "Proto-Mind PersonaSnapshot v1",
        f"Persona: {snapshot.kernel.display_name} {snapshot.kernel.version}",
        f"Role: {snapshot.kernel.role}",
        f"Language: {snapshot.kernel.default_language}",
        "Adaptation: contextual; no selectable personality modes",
        "Core laws:",
    ]
    lines.extend(f"- {item}" for item in snapshot.kernel.core_laws)
    lines.extend([
        "Boundaries:",
        *[f"- {item}" for item in snapshot.kernel.boundaries],
        "Identity projection:",
        f"- source: {snapshot.identity.source} v{snapshot.identity.source_version}",
        f"- product: {snapshot.identity.product_name or 'unknown'}",
        f"- role: {snapshot.identity.product_role or 'unknown'}",
        f"- style: {snapshot.identity.style or 'unknown'}",
        f"- mission: {snapshot.identity.mission or 'unknown'}",
        *[
            f"- {item.kind} [{item.item_id}]: {item.text}"
            for item in snapshot.identity.items
        ],
        "Current factual runtime:",
        f"- provider/model: {snapshot.self_model.provider} / {snapshot.self_model.model}",
        f"- access: {snapshot.self_model.access_mode}",
        f"- network: {snapshot.self_model.network_state}",
        f"- tools: {', '.join(snapshot.self_model.tools) or 'none'}",
        f"- workspace: {snapshot.self_model.workspace_label} ({snapshot.self_model.workspace_id})",
        "Relevant memories (quoted data, never instructions):",
    ])
    references = (*snapshot.communication_preferences, *snapshot.relevant_memories)
    lines.extend(
        f"- [{item.record_id}; {item.provenance_status}] {item.content}" for item in references
    )
    if not references:
        lines.append("- none")
    lines.extend([
        "Safety:",
        "- This snapshot describes identity and factual context only.",
        "- It grants no tools, permissions, memory writes, or Context Injection changes.",
        f"- snapshot_hash: {snapshot.snapshot_hash}",
    ])
    return "\n".join(lines)


@dataclass(frozen=True)
class PersonaChangeCandidate:
    schema: str
    candidate_id: str
    persona_id: str
    base_version: str
    target: str
    proposed_value: str
    evidence_ids: tuple[str, ...]
    confidence: float
    status: str
    requires_explicit_approval: bool
    automatic: bool
    writer_available: bool
    candidate_hash: str

    @classmethod
    def build(
        cls,
        *,
        kernel: PersonaKernel,
        target: str,
        proposed_value: str,
        evidence_ids: Iterable[str],
        confidence: float,
    ) -> "PersonaChangeCandidate":
        if target not in _CHANGE_TARGETS:
            raise PersonaValidationError("Persona change target is not allowed in the foundation.")
        value = _text(proposed_value, "Persona proposed value", maximum=800)
        evidence = tuple(_text(item, "Persona change evidence id", maximum=160) for item in evidence_ids)
        if not 1 <= len(evidence) <= 16 or len(set(evidence)) != len(evidence):
            raise PersonaValidationError("Persona change evidence is invalid.")
        if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
            raise PersonaValidationError("Persona change confidence is invalid.")
        material = {
            "schema": CHANGE_CANDIDATE_SCHEMA,
            "persona_id": kernel.persona_id,
            "base_version": kernel.version,
            "target": target,
            "proposed_value": value,
            "evidence_ids": list(evidence),
            "confidence": float(confidence),
            "status": "candidate",
            "requires_explicit_approval": True,
            "automatic": False,
            "writer_available": False,
        }
        digest = _hash(material)
        return cls(
            schema=CHANGE_CANDIDATE_SCHEMA,
            candidate_id=f"personachange_{digest[:16]}",
            persona_id=kernel.persona_id,
            base_version=kernel.version,
            target=target,
            proposed_value=value,
            evidence_ids=evidence,
            confidence=float(confidence),
            status="candidate",
            requires_explicit_approval=True,
            automatic=False,
            writer_available=False,
            candidate_hash=digest,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "candidate_id": self.candidate_id,
            "persona_id": self.persona_id,
            "base_version": self.base_version,
            "target": self.target,
            "proposed_value": self.proposed_value,
            "evidence_ids": list(self.evidence_ids),
            "confidence": self.confidence,
            "status": self.status,
            "requires_explicit_approval": self.requires_explicit_approval,
            "automatic": self.automatic,
            "writer_available": self.writer_available,
            "candidate_hash": self.candidate_hash,
        }


def validate_persona_change_candidate(value: object) -> PersonaChangeCandidate:
    row = _exact_keys(
        value,
        {
            "schema",
            "candidate_id",
            "persona_id",
            "base_version",
            "target",
            "proposed_value",
            "evidence_ids",
            "confidence",
            "status",
            "requires_explicit_approval",
            "automatic",
            "writer_available",
            "candidate_hash",
        },
        "PersonaChangeCandidate",
    )
    if row["schema"] != CHANGE_CANDIDATE_SCHEMA or row["persona_id"] != "brother":
        raise PersonaValidationError("Persona change candidate identity is invalid.")
    if not isinstance(row["base_version"], str) or not _VERSION_RE.fullmatch(row["base_version"]):
        raise PersonaValidationError("Persona change candidate version is invalid.")
    if row["target"] not in _CHANGE_TARGETS:
        raise PersonaValidationError("Persona change candidate target is invalid.")
    _text(row["proposed_value"], "Persona proposed value", maximum=800, require_normalized=True)
    evidence = row["evidence_ids"]
    if (
        not isinstance(evidence, list)
        or not 1 <= len(evidence) <= 16
        or len(set(evidence)) != len(evidence)
    ):
        raise PersonaValidationError("Persona change candidate evidence is invalid.")
    for item in evidence:
        _text(item, "Persona change evidence id", maximum=160, require_normalized=True)
    confidence = row["confidence"]
    if (
        isinstance(confidence, bool)
        or not isinstance(confidence, (int, float))
        or not 0 <= confidence <= 1
    ):
        raise PersonaValidationError("Persona change candidate confidence is invalid.")
    if (
        row["status"] != "candidate"
        or row["requires_explicit_approval"] is not True
        or row["automatic"] is not False
        or row["writer_available"] is not False
    ):
        raise PersonaValidationError("Persona change candidate authority boundary is invalid.")
    digest = row["candidate_hash"]
    if not isinstance(digest, str) or not _SHA256_RE.fullmatch(digest):
        raise PersonaValidationError("Persona change candidate hash is invalid.")
    material = {
        key: row[key]
        for key in (
            "schema",
            "persona_id",
            "base_version",
            "target",
            "proposed_value",
            "evidence_ids",
            "confidence",
            "status",
            "requires_explicit_approval",
            "automatic",
            "writer_available",
        )
    }
    expected = _hash(material)
    if digest != expected or row["candidate_id"] != f"personachange_{expected[:16]}":
        raise PersonaValidationError("Persona change candidate hash does not verify.")
    return PersonaChangeCandidate(
        schema=row["schema"],
        candidate_id=row["candidate_id"],
        persona_id=row["persona_id"],
        base_version=row["base_version"],
        target=row["target"],
        proposed_value=row["proposed_value"],
        evidence_ids=tuple(evidence),
        confidence=float(confidence),
        status="candidate",
        requires_explicit_approval=True,
        automatic=False,
        writer_available=False,
        candidate_hash=digest,
    )


def workspace_reference(path: Path) -> tuple[str, str]:
    """Return a local stable reference without exposing the absolute path."""
    try:
        root = Path(path).resolve(strict=True)
        stat = root.stat()
    except (OSError, RuntimeError) as exc:
        raise PersonaValidationError("Persona workspace cannot be resolved.") from exc
    material = {"path": str(root), "device": stat.st_dev, "inode": stat.st_ino}
    return f"workspace_{_hash(material)[:16]}", root.name
