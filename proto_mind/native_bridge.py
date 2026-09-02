"""Private stdio bridge for the native macOS client; no listening socket."""
from __future__ import annotations

from proto_mind.python_env import enforce_python_version

enforce_python_version()

import argparse
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack, redirect_stdout
from dataclasses import asdict, replace
import hashlib
import json
from pathlib import Path
import sys
import threading
from typing import Any, Callable
from urllib.parse import urlparse
from urllib import request
from uuid import UUID, uuid4

from proto_mind.action_preview import build_action_preview
from proto_mind.command_registry import COMMAND_REGISTRY, match_registered_command
from proto_mind.config import ProtoMindConfig
from proto_mind.coordinator import Coordinator
from proto_mind.main import is_exit_command, process_interactive_input_with_envelope
from proto_mind.memory_hygiene import MemoryHygiene
from proto_mind.memory_keeper import MemoryKeeper
from proto_mind.memory_store import MemoryStore
from proto_mind.native_codex import CodexSubscription, SubscriptionReasoner, validate_reasoning_effort
from proto_mind.native_computer_use import public_computer_use_capability
from proto_mind.local_knowledge_capabilities import (
    fetch_local_knowledge,
    local_knowledge_descriptors,
    search_local_knowledge,
)
from proto_mind.native_agent import AgentGrants, FULL_ACCESS_CONFIRMATION
from proto_mind.native_library import NativeLibrary
from proto_mind.native_memory_workshop import build_native_memory_workshop
from proto_mind.native_learning_review import NativeLearningReview, parse_learning_request
from proto_mind.native_skill_authoring import NativeSkillAuthoring, NativeSkillSession, parse_skill_request
from proto_mind.native_skill_inspection import NativeSkillInspection, parse_skill_inspection_request
from proto_mind.native_skill_outcome import NativeSkillOutcome, parse_skill_outcome_request
from proto_mind.native_skill_decision import NativeSkillDecision, parse_skill_decision_request
from proto_mind.native_skill_lifecycle import NativeSkillLifecycle, parse_skill_lifecycle_request
from proto_mind.native_skill_restore import NativeSkillRestore, parse_skill_restore_request
from proto_mind.skill_lifecycle_restore_apply import procedural_skill_restore_apply_receipts_snapshot
from proto_mind.experience_pilot import peek_experience_pilot
from proto_mind.native_workspace import WorkspaceReader, file_context_message
from proto_mind.native_images import ImageReader, image_specifications, MAX_IMAGES, MAX_IMAGE_BYTES, MAX_TOTAL_IMAGE_BYTES
from proto_mind.native_pdf import PDFReader, SelectedPDF, pdf_context_message
from proto_mind.persona_activation_readiness import build_persona_activation_readiness
from proto_mind.persona_activation import PersonaTurnActivation, prepare_persona_turn
from proto_mind.native_persona import (
    NativePersonaRequest,
    build_native_persona_preview,
    build_native_persona_runtime,
)
from proto_mind.persona_engine import validate_persona_snapshot
from proto_mind.native_work_sessions import WorkSessionStore, WorkSessionError, workspace_identity
from proto_mind.native_desk import context_manifest, context_preview, capture_artifacts, artifact_page, artifact_preview, review_observations
from proto_mind.native_review import CONFIRM_REVIEW, criteria_context_message, validate_criteria, review_preview
from proto_mind.natural_commands import route_natural_command
from proto_mind.observer import Observer
from proto_mind.reasoners.mock_reasoner import MockReasoner
from proto_mind.reasoners.ollama_reasoner import OllamaReasoner
from proto_mind.session_log import SessionOperatorLogger


BRIDGE_VERSION = 1
MAX_INPUT_CHARS = 32_000
MAX_REQUEST_BYTES = 512 * 1024
MAX_LIVE_SESSIONS = 32
RESET_CODEX_THREAD_CONFIRMATION = "START NEW CODEX SESSION"


def _canonical_hash(value: object) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class _NoLocalRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("Local Ollama requests cannot follow redirects.")


def local_ollama_request(config: ProtoMindConfig, path: str, payload=None, *, timeout: int = 60) -> dict:
    url = urlparse(config.ollama_url)
    if (url.scheme != "http" or url.hostname not in {"localhost", "127.0.0.1", "::1"}
            or url.username or url.password or url.query or url.fragment):
        raise ValueError("Native local mode accepts loopback Ollama only.")
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    message = request.Request(config.ollama_url.rstrip("/") + path, data=data,
                              headers={"Content-Type": "application/json"})
    # Local mode never inherits proxies or follows a redirect to another host.
    opener = request.build_opener(request.ProxyHandler({}), _NoLocalRedirect())
    with opener.open(message, timeout=timeout) as response:
        raw = response.read(4 * 1024 * 1024 + 1)
    if len(raw) > 4 * 1024 * 1024:
        raise ValueError("Ollama response exceeded the local limit.")
    result = json.loads(raw)
    if not isinstance(result, dict):
        raise ValueError("Unexpected Ollama response shape.")
    return result


class NativeMemoryStore(MemoryStore):
    """Same store format, but browsing the native client must not initialize files."""

    def __init__(self, working_path: Path, persistent_path: Path) -> None:
        self.working_path, self.persistent_path = working_path, persistent_path

    def _load_records(self, path: Path):
        return super()._load_records(path) if path.exists() else []

    def _save_records(self, path: Path, records) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        super()._save_records(path, records)


class NativeOllamaReasoner(OllamaReasoner):
    def __init__(self, config: ProtoMindConfig, history: list[dict], files: list[dict] | None = None,
                 criteria: list[str] | None = None, pdfs: list[SelectedPDF] | None = None,
                 persona_activation: PersonaTurnActivation | None = None) -> None:
        super().__init__(config)
        self.history = history
        self.files = files or []
        self.pdfs = pdfs or []
        self.criteria = validate_criteria([] if criteria is None else criteria)
        self.persona_activation = persona_activation
        self.last_persona_receipt: dict | None = None

    def _post(self, path: str, payload: dict) -> dict:
        messages = payload["messages"]
        return local_ollama_request(self.config, path, {**payload, "messages": [messages[0], *self.history, messages[-1]]})

    def respond(self, user_input, retrieved_memory, observer_state, correction_hints=None) -> str:
        legacy_instructions = self._build_system_prompt(observer_state, retrieved_memory, correction_hints or [])
        if self.persona_activation is None:
            instructions = legacy_instructions
            self.last_persona_receipt = None
        else:
            prepared = prepare_persona_turn(
                self.persona_activation,
                retrieved_memory=retrieved_memory,
                observer_state=observer_state,
                correction_hints=correction_hints or [],
                legacy_prompt=legacy_instructions,
            )
            instructions = prepared.instructions
            self.last_persona_receipt = prepared.receipt
        payload = {
            "model": self.config.ollama_model,
            "messages": [
                {"role": "system", "content": instructions},
                {"role": "user", "content": criteria_context_message(self.criteria) + file_context_message(self.files)
                 + pdf_context_message(self.pdfs) + user_input.strip()},
            ],
            "stream": False,
        }
        try:
            result = self._post("/api/chat", payload)
            content = result.get("message", {}).get("content")
            if not isinstance(content, str) or not content.strip():
                raise ValueError("No usable local answer.")
            return content.strip()
        except (OSError, ValueError, TypeError, AttributeError) as exc:
            # Keep the legacy CLI fallback, but never label a mock answer as a native model reply.
            raise RuntimeError("Ollama did not return an answer. Start Ollama and check the selected model, or explicitly choose Mock. No fallback model was used.") from exc


def bounded_history(value: object) -> list[dict]:
    if not isinstance(value, list) or len(value) > 200:
        raise ValueError("Invalid conversation history.")
    history = []
    for item in value[-12:]:
        if not isinstance(item, dict) or item.get("role") not in {"user", "assistant"}:
            raise ValueError("History accepts user and assistant messages only.")
        content = item.get("content")
        if not isinstance(content, str):
            raise ValueError("History content must be text.")
        history.append({"role": item["role"], "content": content[:2000]})
    return history


def input_text(params: dict) -> str:
    value = params.get("text")
    if not isinstance(value, str) or not value.strip() or len(value) > MAX_INPUT_CHARS or "\x00" in value:
        raise ValueError(f"Enter a non-empty message of at most {MAX_INPUT_CHARS} characters.")
    return value.strip()


def describe_input(text: str) -> dict:
    preview = build_action_preview(text)
    operator = text.startswith("/") or route_natural_command(text) is not None or is_exit_command(text)
    if not operator:
        return {"operator": False, "requires_confirmation": False, "blocked": False,
                "notice": "Normal turn: existing memory and session-log rules apply."}
    if is_exit_command(text):
        return {"operator": True, "requires_confirmation": False, "blocked": False, "steps": []}
    spec = match_registered_command(text) if text.startswith("/") else None
    steps = preview.get("steps", [])
    # Literal slash parameters still belong to the existing formatter, not a shell.
    if not steps and spec is not None:
        steps = [{"command": text, "matched_prefix": spec.prefix, "read_only": spec.read_only,
                  "mutates": spec.mutates, "risk": spec.risk, "category": spec.category}]
    blocked = not steps
    confirm = any(not step.get("read_only", False) or step.get("risk") != "low" for step in steps)
    return {"operator": True, "requires_confirmation": confirm, "blocked": blocked,
            "policy": preview.get("policy_class", "blocked"), "steps": steps,
            "notice": "Unknown command. Use /commands list." if blocked else
            "Only your explicit input is dispatched. Internal command gates still apply."}


class NativeBackend:
    def __init__(self, project_root: Path, state_dir: Path, *, subscription_factory=CodexSubscription,
                 pdf_helper: Path | None = None) -> None:
        self.root, self.state_dir = project_root.resolve(), state_dir.resolve()
        self.pdf_helper = pdf_helper
        self.subscription = subscription_factory(self.state_dir)
        self.sessions: dict[str, Coordinator] = {}
        self._native_learning_apply_used = False
        self._native_skill_apply_used = False
        self._native_skill_lifecycle_apply_used = False
        self._native_skill_restore_used = False
        self._native_skill_session = NativeSkillSession()
        self.logger = SessionOperatorLogger.from_project_root(self.root)
        self.active_request: str | None = None
        self.active_provider: str | None = None
        self.busy = threading.Lock()
        self.agent_grants = AgentGrants()
        self._last_bootstrap_computer_use: dict | None = None
        self.work_sessions = WorkSessionStore(self.state_dir, self.root)
        self.closing = threading.Event()

    def bootstrap(self) -> dict:
        notes = []

        def read_json(name: str, default):
            path = self.root / "proto_mind" / "data" / name
            try:
                return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default
            except (OSError, ValueError):
                notes.append(f"Could not read {name}; no repair attempted.")
                return None

        identity = read_json("identity.json", {})
        profile = identity.get("profile", {}) if isinstance(identity, dict) else {}
        if not isinstance(profile, dict):
            notes.append("Identity profile has an unexpected type.")
            profile = {}
        memories = read_json("persistent_memory.json", [])
        if not isinstance(memories, list):
            notes.append("Persistent memory has an unexpected root type.")
            memories = []
        settings = read_json("context_injection.json", {"enabled": False})
        enabled = settings.get("enabled") if isinstance(settings, dict) else None
        config = ProtoMindConfig.from_env(self.root / "proto_mind")
        computer_use = public_computer_use_capability()
        self._last_bootstrap_computer_use = computer_use
        return {
            "protocol_version": BRIDGE_VERSION, "project_root": str(self.root),
            "name": profile.get("name", "Proto-Mind"), "operator_name": profile.get("operator_name", ""),
            "registry_count": len(COMMAND_REGISTRY),
            "category_count": len({spec.category for spec in COMMAND_REGISTRY}),
            "commands": [asdict(spec) for spec in COMMAND_REGISTRY],
            "memory_count": len(memories),
            "active_memories": sum(item.get("active", True) is True for item in memories if isinstance(item, dict)),
            "context_injection": enabled if type(enabled) is bool else None,
            "ollama_model": config.ollama_model, "notes": notes,
            "subscription": {"automatic_connection": False, "cloud": True,
                             "profile_path": str(self.subscription.home)},
            "agent": {"default_mode": "chat", "available_modes": ["chat", "full_access"],
                      "confirmation": FULL_ACCESS_CONFIRMATION, "persistent_grants": False,
                      "web_search": "live_full_access_only",
                      "computer_use": computer_use},
            "local_knowledge_capabilities": {
                "transport": "private_stdio",
                "contracts": local_knowledge_descriptors(),
            },
        }

    def _coordinator(self, session_id: str) -> Coordinator:
        if session_id not in self.sessions:
            if len(self.sessions) >= MAX_LIVE_SESSIONS:
                raise ValueError("Live session limit reached. Restart the app; chat history is retained locally.")
            data = self.root / "proto_mind" / "data"
            store = NativeMemoryStore(data / "working_memory.json", data / "persistent_memory.json")
            self.sessions[session_id] = Coordinator(
                observer=Observer(), memory_keeper=MemoryKeeper(store), reasoner=MockReasoner(),
                config=ProtoMindConfig.from_env(self.root / "proto_mind"), session_logger=self.logger,
            )
        return self.sessions[session_id]

    @property
    def protected_input_roots(self) -> tuple[Path, ...]:
        return (
            self.root / "proto_mind" / "data", self.root / "proto_mind" / "exports",
            self.root / "exports", self.root / "logs", self.root / "desktop_prefs.json",
            self.root / "backups", self.state_dir,
        )

    def workspace(self, params: dict) -> WorkspaceReader:
        return WorkspaceReader(params.get("workspace_root"), protected_roots=self.protected_input_roots)

    def image_reader(self) -> ImageReader:
        return ImageReader(protected_roots=self.protected_input_roots)

    def pdf_reader(self) -> PDFReader:
        return PDFReader(protected_roots=self.protected_input_roots, helper=self.pdf_helper)

    def _persona_runtime_evidence(self, request: NativePersonaRequest) -> tuple[Path | None, bool, bool]:
        workspace = self.workspace({"workspace_root": request.workspace_root}).root if request.workspace_root is not None else None
        grant_verified = False
        computer_use_available = False
        if request.access_mode == "full_access":
            if request.provider != "codex" or request.cloud_consent is not True or workspace is None:
                raise ValueError("Full Mac Persona preview requires Codex, cloud consent, and a selected workspace.")
            self.agent_grants.validate(
                request.conversation_id,
                workspace,
                request.access_token,
            )
            grant_verified = True
            computer_use_available = bool(
                self._last_bootstrap_computer_use
                and self._last_bootstrap_computer_use.get("available") is True
            )
        return workspace, grant_verified, computer_use_available

    def preview_persona(self, params: dict) -> dict:
        request = NativePersonaRequest.parse(params)
        workspace, grant_verified, computer_use_available = self._persona_runtime_evidence(request)
        config = ProtoMindConfig.from_env(self.root / "proto_mind")
        return build_native_persona_preview(
            self.root,
            request,
            workspace=workspace,
            full_access_grant_verified=grant_verified,
            computer_use_available=computer_use_available,
            ollama_model=config.ollama_model,
        )

    def preview_persona_readiness(self, params: dict) -> dict:
        request = NativePersonaRequest.parse(params)
        workspace, grant_verified, computer_use_available = self._persona_runtime_evidence(request)
        config = ProtoMindConfig.from_env(self.root / "proto_mind")

        def companion(provider: str) -> NativePersonaRequest:
            if request.provider == provider:
                return request
            model = {
                "codex": "account_default_unresolved",
                "ollama": config.ollama_model,
                "mock": "deterministic_mock",
            }[provider]
            return NativePersonaRequest(
                conversation_id=request.conversation_id,
                provider=provider,
                model=model,
                cloud_consent=False,
                access_mode="chat",
                workspace_root=request.workspace_root,
                access_token=None,
            )

        previews = {}
        for provider in ("codex", "ollama", "mock"):
            candidate = companion(provider)
            candidate_grant = grant_verified if candidate is request else False
            preview = build_native_persona_preview(
                self.root,
                candidate,
                workspace=workspace,
                full_access_grant_verified=candidate_grant,
                computer_use_available=computer_use_available if candidate_grant else False,
                ollama_model=config.ollama_model,
            )
            previews[{"codex": "codex_subscription", "ollama": "ollama", "mock": "mock"}[provider]] = (
                validate_persona_snapshot(preview["snapshot"])
            )
        selected = {"codex": "codex_subscription", "ollama": "ollama", "mock": "mock"}[request.provider]
        current_preview = build_native_persona_preview(
            self.root,
            request,
            workspace=workspace,
            full_access_grant_verified=grant_verified,
            computer_use_available=computer_use_available,
            ollama_model=config.ollama_model,
        )
        return build_persona_activation_readiness(
            previews,
            selected_provider=selected,
            context_injection_state=current_preview["context_injection_state"],
        )

    def _prepare_persona_activation(
        self,
        params: dict,
        *,
        session_id: str,
        provider: str,
        model: str,
        mode: str,
    ) -> PersonaTurnActivation:
        if provider == "mock":
            raise ValueError("Brother Persona is not available for Mock. Disable Persona or select Codex/Ollama.")
        if provider == "codex" and not model:
            raise ValueError("Select an explicit Codex model before enabling Brother Persona.")
        request_value = {
            "conversation_id": session_id,
            "provider": provider,
            "model": model,
            "cloud_consent": params.get("cloud_consent", False),
            "access_mode": mode,
        }
        if params.get("workspace_root") is not None:
            request_value["workspace_root"] = params["workspace_root"]
        if mode == "full_access":
            request_value["access_token"] = params.get("access_token")
        request = NativePersonaRequest.parse(request_value)
        readiness = self.preview_persona_readiness(request_value)
        expected_provider = {"codex": "codex_subscription", "ollama": "ollama"}[provider]
        if (
            readiness["status"] != "READY"
            or readiness["selected_provider"] != expected_provider
            or readiness["selected_adapter_ready"] is not True
        ):
            blockers = "; ".join(readiness["blockers"][:3]) or "selected adapter is not ready"
            raise ValueError(f"Brother Persona activation refused: {blockers}.")
        workspace, grant_verified, computer_use_available = self._persona_runtime_evidence(request)
        config = ProtoMindConfig.from_env(self.root / "proto_mind")
        runtime = build_native_persona_runtime(
            request,
            workspace=workspace,
            full_access_grant_verified=grant_verified,
            computer_use_available=computer_use_available,
            ollama_model=config.ollama_model,
        )
        selected_adapter = next(
            (item for item in readiness["adapters"] if item["provider"] == expected_provider),
            None,
        )
        if selected_adapter is None or selected_adapter["runtime_hash"] != _canonical_hash(runtime.to_dict()):
            raise ValueError("Brother Persona runtime changed after readiness. No provider turn was started.")
        return PersonaTurnActivation(
            project_root=self.root,
            runtime=runtime,
            context_injection_state=readiness["context_injection_state"],
            readiness_hash=readiness["activation_fingerprint"],
        )

    def process(self, params: dict, emit: Callable[[dict], None], request_id: str) -> dict:
        if self.closing.is_set():
            raise ValueError("The Native window disconnected. No new turn will start.")
        text = input_text(params)
        session_id = str(UUID(str(params.get("conversation_id", ""))))
        description = describe_input(text)
        persona_enabled = params.get("persona_enabled", False)
        if type(persona_enabled) is not bool:
            raise ValueError("Invalid Brother Persona activation state.")
        if description["blocked"]:
            raise ValueError(description["notice"])
        if description["requires_confirmation"] and params.get("confirmed_text") != text:
            raise ValueError("Confirm the exact operator command before running it.")
        provider = params.get("provider", "ollama")
        if provider not in {"ollama", "mock", "codex"}:
            raise ValueError("Unknown model provider.")
        model = params.get("model", "")
        if not isinstance(model, str) or len(model) > 160 or "\x00" in model:
            raise ValueError("Invalid model name.")
        reasoning_effort = validate_reasoning_effort(params.get("reasoning_effort", "")) if provider == "codex" and not description["operator"] else ""
        history = bounded_history(params.get("history", []))
        criteria = [] if description["operator"] else validate_criteria(params.get("criteria", []))
        if provider == "codex" and not description["operator"] and params.get("cloud_consent") is not True:
            raise ValueError("Select and approve cloud processing before sending messages or recalled memories to Codex.")
        if description["operator"] and persona_enabled:
            raise ValueError("Brother Persona is not applied to operator commands. No command was executed.")
        agent_workspace = None
        mode = "chat"
        if not description["operator"]:
            mode = params.get("access_mode", "chat")
            if mode not in {"chat", "full_access"}:
                raise ValueError("Unknown model access mode.")
            if mode == "full_access":
                if provider != "codex":
                    raise ValueError("Full Mac tools currently require the explicitly selected Codex provider.")
                agent_workspace = self.workspace(params).root
                self.agent_grants.validate(session_id, agent_workspace, params.get("access_token"))
        persona_activation = None
        if persona_enabled:
            persona_activation = self._prepare_persona_activation(
                params,
                session_id=session_id,
                provider=provider,
                model=model,
                mode=mode,
            )
        files = []
        if not description["operator"] and "files" in params:
            files = self.workspace(params).context_files(params["files"])
        images = []
        if not description["operator"] and params.get("images", []) != []:
            image_specifications(params["images"])
            if provider != "codex":
                raise ValueError("Image input currently requires an explicitly selected vision-capable Codex model. Ollama/Mock images are not implemented; no provider was changed.")
            images = self.image_reader().selected(params["images"])
        pdfs = [] if description["operator"] else self.pdf_reader().selected(params.get("pdfs", []))
        logical_workspace = (workspace_identity(self.workspace(params).root)
                             if not description["operator"] and params.get("workspace_root") else None)
        provider_thread = (self.subscription.thread_status(session_id, logical_workspace, mode=mode)
                           if provider == "codex" and not description["operator"] else None)
        provider_history = ([] if provider_thread and provider_thread["linked"] else history)
        if not self.busy.acquire(blocking=False):
            raise ValueError("Another turn is already running.")
        lifecycle = ExitStack()
        work_session = None
        try:
            skill_apply_prefix = "/experience learning apply skill"
            normalized = " ".join(text.casefold().split())
            if description["operator"] and (normalized == skill_apply_prefix or normalized.startswith(skill_apply_prefix + " ")) and self._skill_apply_slot_used():
                raise ValueError("This Native bridge has already used its single skill apply slot. Inspect the saved skill; no command was executed.")
            lifecycle_prefix = "/experience learning apply skill-outcome-lifecycle"
            if description["operator"] and (normalized == lifecycle_prefix or normalized.startswith(lifecycle_prefix + " ")) and self._skill_lifecycle_slot_used():
                raise ValueError("This Native bridge has already used its single lifecycle apply attempt. Inspect the skill and receipts; no command was executed.")
            if description["operator"] and (normalized == "/skills restore" or normalized.startswith("/skills restore ")) and self._skill_restore_slot_used():
                raise ValueError("This Native bridge has already used its restore attempt. Inspect the skill and receipt; no command was executed.")
            if not description["operator"]:
                workspace = logical_workspace
                continuation = params.get("continuation")
                if continuation is not None:
                    prepared = self.work_sessions.continuation(continuation, session_id, workspace)
                    if prepared["sources"]:
                        self.workspace(params).context_files(prepared["sources"])
                work_session = lifecycle.enter_context(self.work_sessions.begin(
                    run_id=params.get("run_id", str(uuid4())), conversation_id=session_id, text=text,
                    provider=provider, model=model, effort=reasoning_effort, mode=mode,
                    workspace=workspace, sources=files, continuation=continuation, criteria=criteria,
                    context_manifest=context_manifest(root=self.root, text=text, history=provider_history, files=files,
                        provider=provider, model=model, effort=reasoning_effort, mode=mode,
                        workspace=workspace["path"] if workspace else None, criteria=criteria,
                        images=[image.metadata for image in images], pdfs=[pdf.metadata for pdf in pdfs],
                        provider_thread=provider_thread)))
            if provider == "codex" and not description["operator"]:
                self.subscription.prepare_turn()
            self.active_request, self.active_provider = request_id, provider if not description["operator"] else "operator"
            if self.closing.is_set():
                raise ValueError("Native disconnected before processing; no new work started.")
            coordinator = self._coordinator(session_id)
            agent_receipt = None
            work_log = None

            def activity(event: dict) -> None:
                nonlocal agent_receipt
                if work_session is not None:
                    work_session.observe(event)
                if event.get("event") == "agent_run":
                    agent_receipt = event["receipt"]
                emit({**event, "request_id": request_id})

            def progress(event: dict) -> None:
                nonlocal work_log
                if event.get("event") == "work_log":
                    work_log = event["log"]
                    if work_session is not None:
                        work_session.observe(event)
                    emit({**event, "request_id": request_id})

            if not description["operator"]:
                config = ProtoMindConfig.from_env(self.root / "proto_mind")
                if provider == "codex":
                    coordinator.reasoner = SubscriptionReasoner(
                        self.subscription, model, history,
                        lambda delta: emit({"event": "answer_delta", "request_id": request_id, "delta": delta}),
                        conversation=session_id, logical_workspace=logical_workspace,
                        files=files,
                        agent_workspace=agent_workspace, on_activity=activity, on_progress=progress,
                        reasoning_effort=reasoning_effort,
                        criteria=criteria,
                        images=images,
                        pdfs=pdfs,
                        persona_activation=persona_activation,
                    )
                elif provider == "ollama":
                    url = urlparse(config.ollama_url)
                    if url.scheme != "http" or url.hostname not in {"localhost", "127.0.0.1", "::1"}:
                        raise ValueError("Native local mode accepts loopback Ollama only.")
                    coordinator.reasoner = NativeOllamaReasoner(
                        replace(config, ollama_model=model or config.ollama_model),
                        history,
                        files,
                        criteria,
                        pdfs,
                        persona_activation=persona_activation,
                    )
                else:
                    coordinator.reasoner = MockReasoner()
            if work_session is not None:
                saved_workspace = work_session.record["workspace"]
                if saved_workspace and workspace_identity(Path(saved_workspace["path"])) != saved_workspace:
                    raise WorkSessionError("Workspace changed before dispatch. Choose and inspect the folder again.")
                work_session.dispatch()
            output = process_interactive_input_with_envelope(
                text, coordinator=coordinator, session_logger=self.logger, project_root=self.root,
                hygiene=MemoryHygiene(coordinator.memory_keeper.store),
            )
            pilot = peek_experience_pilot(coordinator)
            if pilot is not None and pilot.learning_applies.snapshot():
                self._native_learning_apply_used = True
            if pilot is not None and pilot.skill_applies.snapshot():
                self._native_skill_apply_used = True
            if pilot is not None and (pilot.skill_lifecycle_applies.snapshot() or pilot.skill_lifecycle_metadata_applies.snapshot()):
                self._native_skill_lifecycle_apply_used = True
            if output.text is None:
                self.sessions.pop(session_id, None)
            serialized = output.to_dict()
            persona_receipt = getattr(coordinator.reasoner, "last_persona_receipt", None)
            if persona_activation is not None:
                if not isinstance(persona_receipt, dict):
                    raise ValueError("Brother Persona did not produce a validated turn receipt.")
                serialized["notices"].append(
                    "Brother Persona active for this turn · snapshot "
                    f"{persona_receipt['snapshot_hash'][:12]} · rollback is available in Model Settings."
                )
            if files and provider == "mock":
                serialized["notices"].append("Mock is a deterministic UI test backend, not a file-understanding model. No file analysis was performed.")
            if criteria and provider == "mock":
                serialized["notices"].append("Mock does not evaluate completion criteria; they remain operator-declared, not verified.")
            if pdfs and provider == "mock":
                serialized["notices"].append("Mock is a deterministic UI test backend, not a PDF-understanding model. No PDF analysis was performed.")
            saved_session = None
            if work_session is not None:
                reader = self._artifact_workspace(params, work_session.record)
                artifacts = capture_artifacts(work_session.record, reader)
                saved_session = work_session.complete(serialized.get("text") or "", artifacts=artifacts)
            return {**serialized, "operator": description["operator"],
                    "conversation_id": session_id, "exit_requested": output.text is None,
                    "agent_run": agent_receipt,
                    "persona_activation": persona_receipt,
                    "work_log": work_log,
                    "provider_thread": self.subscription.last_thread_info if provider == "codex" and not description["operator"] else None,
                    "work_session": saved_session,
                    "image_context": [image.metadata for image in images],
                    "pdf_context": [pdf.metadata for pdf in pdfs],
                    "workspace_context": [{key: value for key, value in item.items() if key != "content"} for item in files]}
        except BaseException:
            if work_session is not None and work_session.failed_write and provider == "codex":
                self.subscription.interrupt()
            lifecycle.__exit__(*sys.exc_info())
            raise
        finally:
            try:
                lifecycle.close()
            finally:
                self.active_request = self.active_provider = None
                self.busy.release()

    def _artifact_workspace(self, params: dict, record: dict) -> WorkspaceReader | None:
        try:
            if not params.get("workspace_root") or not record.get("workspace"):
                return None
            reader = self.workspace(params)
            return reader if workspace_identity(reader.root) == record["workspace"] else None
        except (OSError, ValueError):
            return None

    def preview_context(self, params: dict) -> dict:
        text = params.get("text", "")
        if not isinstance(text, str) or len(text) > MAX_INPUT_CHARS or "\x00" in text:
            raise ValueError("Invalid draft for local context inspection.")
        text = text.strip()
        provider, mode = params.get("provider", "ollama"), params.get("access_mode", "chat")
        if provider not in {"codex", "ollama", "mock"} or mode not in {"chat", "full_access"}:
            raise ValueError("Unknown provider or access mode.")
        model = params.get("model", "")
        if not isinstance(model, str) or len(model) > 160 or "\x00" in model:
            raise ValueError("Invalid model name.")
        operator = describe_input(text)["operator"] if text else False
        reader = self.workspace(params) if params.get("workspace_root") and not operator else None
        local_history = bounded_history(params.get("history", []))
        logical_workspace = workspace_identity(reader.root) if reader else None
        provider_thread = (self.subscription.thread_status(params.get("conversation_id", ""), logical_workspace,
                                                           mode=mode)
                           if provider == "codex" and not operator else None)
        provider_history = [] if provider_thread and provider_thread["linked"] else local_history
        result = context_preview(root=self.root, text=text, history=provider_history,
                                 provider=provider, model=model,
                                 effort=validate_reasoning_effort(params.get("reasoning_effort", "")) if provider == "codex" and not operator else "",
                                 mode=mode, workspace=str(reader.root) if reader else None, operator=operator,
                                 criteria=validate_criteria(params.get("criteria", [])),
                                 reader=reader, specifications=params.get("files", []), cloud_consent=params.get("cloud_consent") is True,
                                 provider_thread=provider_thread)
        result["draft_empty"] = not text
        image_specs = params.get("images", [])
        rows, images = self.image_reader().context_rows(image_specs, operator=operator)
        result["image_sources"] = rows
        result["manifest"]["images"] = images
        result["manifest"]["image_limits"] = {"count": MAX_IMAGES, "bytes_each": MAX_IMAGE_BYTES, "bytes_total": MAX_TOTAL_IMAGE_BYTES}
        result["excluded_image_count"] = len(image_specs) if operator else 0
        result["image_provider_ready"] = operator or not image_specs or provider == "codex"
        result["attachments_ready"] = (result["attachments_ready"] and result["image_provider_ready"]
                                        and all(row["state"] == "ready" for row in rows))
        pdf_specs = params.get("pdfs", [])
        pdf_rows, pdfs = self.pdf_reader().context_rows(pdf_specs, operator=operator)
        result["pdf_sources"] = pdf_rows
        result["manifest"]["pdfs"] = pdfs
        result["excluded_pdf_count"] = len(pdf_specs) if operator else 0
        result["attachments_ready"] = result["attachments_ready"] and all(row["state"] == "ready" for row in pdf_rows)
        result["notes"].append("PDFs: only selected page text is sent on Send, after byte and text hash revalidation. No original PDF, OCR, layout, automatic page selection or PDF history replay.")
        result["notes"].append("Selected image bytes (including embedded metadata) are sent only on Send; vision capability is rechecked then. No automatic OCR, redaction, image history replay or local Ollama image support.")
        if provider_thread:
            result["provider_thread"] = provider_thread
            if provider_thread["linked"]:
                result["notes"].append("Codex will resume its durable provider thread. Bounded local chat history is not sent again; provider-side history is not reproduced in this local preview.")
            else:
                result["notes"].append("This will create a durable Codex thread and bootstrap it once with the bounded local chat history shown here.")
            if not provider_thread["workspace_matches"]:
                result["attachments_ready"] = False
        return result

    def _review_preview(self, params: dict, record: dict) -> dict:
        reader = self._artifact_workspace(params, record)
        observations, complete = review_observations(record, reader)
        return review_preview(record, params.get("review"), observations,
                              workspace_matches=not record.get("workspace") or reader is not None, artifacts_complete=complete)

    def save_review(self, params: dict) -> dict:
        if params.get("confirmation") != CONFIRM_REVIEW:
            raise ValueError("Explicit operator confirmation is required to record a manual review.")
        if self.closing.is_set() or not self.busy.acquire(blocking=False):
            raise ValueError("Wait until the active turn is finished before recording a review.")
        try:
            def prepare(record):
                preview = self._review_preview(params, record)
                if not preview["ready"]:
                    raise ValueError(" ".join(preview["reasons"]))
                if preview["preview_fingerprint"] != params.get("preview_fingerprint"):
                    raise ValueError("Review inputs, saved run or files changed. Preview again; nothing was recorded.")
                return preview
            run = self.work_sessions.record_review(params.get("run"), params.get("conversation_id", ""), prepare)
            return {"schema": "proto_mind.native_review_saved.v1", "no_execution": True,
                    "mutation": "private_run_review_only", "run": run,
                    "notice": "Manual assessment recorded. No target command executed; automatic verification remains unassessed."}
        finally:
            self.busy.release()

    def learning_review(self, method: str, params: dict) -> dict:
        parsed = parse_learning_request(params, method=method)
        if self.closing.is_set() or not self.busy.acquire(blocking=False):
            raise ValueError("Wait until the active turn is finished before reviewing learning evidence.")
        try:
            workspace = workspace_identity(self.workspace(params).root) if params.get("workspace_root") else None
            pilots = [peek_experience_pilot(owner) for owner in self.sessions.values()]
            used = self._native_learning_apply_used or any(pilot.learning_applies.snapshot() for pilot in pilots if pilot is not None)
            reviewer = NativeLearningReview(
                self.root, self.sessions.get(parsed["conversation_id"]), parsed,
                workspace=workspace, native_apply_used=used,
            )
            if method == "memory_learning_review":
                return reviewer.report()
            if method == "memory_learning_preview":
                return reviewer.preview()
            return reviewer.confirm(params)
        finally:
            # A dropped conversation or lost response must not renew the UI apply budget.
            if method == "memory_learning_confirm":
                self._native_learning_apply_used = self._native_learning_apply_used or any(
                    pilot.learning_applies.snapshot() for owner in self.sessions.values()
                    if (pilot := peek_experience_pilot(owner)) is not None
                )
            self.busy.release()

    def _skill_apply_slot_used(self) -> bool:
        return self._native_skill_apply_used or bool(self._native_skill_session.applies.snapshot()) or any(
            pilot.skill_applies.snapshot() for owner in self.sessions.values()
            if (pilot := peek_experience_pilot(owner)) is not None
        )

    def skill_authoring(self, method: str, params: dict) -> dict:
        parsed = parse_skill_request(params, method=method)
        if self.closing.is_set() or not self.busy.acquire(blocking=False):
            raise ValueError("Wait until the active turn is finished before authoring a skill.")
        try:
            workspace = workspace_identity(self.workspace(params).root) if params.get("workspace_root") else None
            used = self._skill_apply_slot_used()
            reviewer = NativeSkillAuthoring(self.root, self._native_skill_session, parsed,
                                           workspace=workspace, native_apply_used=used)
            if method == "skill_authoring_review":
                return reviewer.report()
            if method == "skill_authoring_preview":
                return reviewer.preview()
            return reviewer.confirm(params)
        finally:
            # The process-wide receipt survives a closed UI conversation or lost response.
            self._native_skill_apply_used = self._native_skill_apply_used or bool(self._native_skill_session.applies.snapshot())
            self.busy.release()

    def _skill_lifecycle_slot_used(self) -> bool:
        return self._native_skill_lifecycle_apply_used or any(
            pilot.skill_lifecycle_applies.snapshot() or pilot.skill_lifecycle_metadata_applies.snapshot()
            for owner in self.sessions.values() if (pilot := peek_experience_pilot(owner)) is not None
        )

    def _skill_restore_slot_used(self) -> bool:
        return self._native_skill_restore_used or bool(procedural_skill_restore_apply_receipts_snapshot())

    def skill_restore(self, method: str, params: dict) -> dict:
        parsed = parse_skill_restore_request(params, method=method)
        if self.closing.is_set() or not self.busy.acquire(blocking=False):
            raise ValueError("Wait until the active turn finishes before reviewing restoration.")
        review = None
        try:
            workspace = workspace_identity(self.workspace(params).root) if params.get("workspace_root") else None
            review = NativeSkillRestore(self.root, parsed, workspace=workspace, native_restore_used=self._skill_restore_slot_used())
            if method == "skill_restore_review":
                return review.report()
            if method == "skill_restore_preview":
                return review.preview()
            return review.confirm(params)
        finally:
            self._native_skill_restore_used = self._skill_restore_slot_used() or bool(review and review.apply_attempted)
            self.busy.release()

    def skill_lifecycle(self, method: str, params: dict) -> dict:
        parsed = parse_skill_lifecycle_request(params, method=method)
        if self.closing.is_set() or not self.busy.acquire(blocking=False):
            raise ValueError("Wait until the active turn finishes before reviewing lifecycle application.")
        review = None
        try:
            workspace = workspace_identity(self.workspace(params).root) if params.get("workspace_root") else None
            review = NativeSkillLifecycle(self.root, self.sessions.get(parsed["conversation_id"]), parsed,
                                          workspace=workspace, native_apply_used=self._skill_lifecycle_slot_used())
            if method == "skill_lifecycle_review":
                return review.report()
            if method == "skill_lifecycle_preview":
                return review.preview()
            return review.confirm(params)
        finally:
            # A lost response, failed verification or closed conversation cannot renew a write attempt.
            self._native_skill_lifecycle_apply_used = self._skill_lifecycle_slot_used() or bool(review and review.apply_attempted)
            self.busy.release()

    def dispatch(self, method: str, params: dict, emit: Callable[[dict], None], request_id: str) -> Any:
        if method == "bootstrap":
            return self.bootstrap()
        if method == "describe":
            return describe_input(input_text(params))
        if method == "process":
            return self.process(params, emit, request_id)
        if method in {"memory_learning_review", "memory_learning_preview", "memory_learning_confirm"}:
            return self.learning_review(method, params)
        if method in {"skill_authoring_review", "skill_authoring_preview", "skill_authoring_confirm"}:
            return self.skill_authoring(method, params)
        if method in {"skill_lifecycle_review", "skill_lifecycle_preview", "skill_lifecycle_confirm"}:
            return self.skill_lifecycle(method, params)
        if method in {"skill_restore_review", "skill_restore_preview", "skill_restore_confirm"}:
            return self.skill_restore(method, params)
        if method in {"skill_decision_review", "skill_decision_preview", "skill_decision_confirm"}:
            parsed = parse_skill_decision_request(params, method=method)
            if self.closing.is_set() or not self.busy.acquire(blocking=False):
                raise ValueError("Wait until the active turn finishes before reviewing skill decisions.")
            try:
                workspace = workspace_identity(self.workspace(params).root) if params.get("workspace_root") else None
                review = NativeSkillDecision(self.root, self.sessions.get(parsed["conversation_id"]), parsed, workspace=workspace)
                if method == "skill_decision_review":
                    return review.report()
                if method == "skill_decision_preview":
                    return review.preview()
                return review.confirm(params)
            finally:
                self.busy.release()
        if method in {"skill_outcome_review", "skill_outcome_preview", "skill_outcome_confirm"}:
            parsed = parse_skill_outcome_request(params, method=method)
            if self.closing.is_set() or not self.busy.acquire(blocking=False):
                raise ValueError("Wait until the active turn finishes before recording skill outcomes.")
            try:
                workspace = workspace_identity(self.workspace(params).root) if params.get("workspace_root") else None
                review = NativeSkillOutcome(self.root, self.sessions.get(parsed["conversation_id"]), parsed, workspace=workspace)
                if method == "skill_outcome_review":
                    return review.report()
                if method == "skill_outcome_preview":
                    return review.preview()
                return review.confirm(params)
            finally:
                self.busy.release()
        if method == "skill_inspection":
            parsed = parse_skill_inspection_request(params)
            if self.closing.is_set() or not self.busy.acquire(blocking=False):
                raise ValueError("Wait until the active turn finishes before inspecting skill evidence.")
            try:
                workspace = workspace_identity(self.workspace(params).root) if params.get("workspace_root") else None
                return NativeSkillInspection(self.root, self.sessions.get(parsed["conversation_id"]), parsed,
                                             workspace=workspace).report()
            finally:
                self.busy.release()
        if method == "work_sessions":
            return self.work_sessions.page(params.get("conversation_id", ""))
        if method == "context_preview":
            return self.preview_context(params)
        if method == "persona_preview":
            return self.preview_persona(params)
        if method == "persona_readiness":
            return self.preview_persona_readiness(params)
        if method == "image_preview":
            return self.image_reader().preview(params.get("path"), params.get("expected_sha256"))
        if method == "pdf_preview":
            return self.pdf_reader().preview(params.get("path"), params.get("pages"), params.get("expected_sha256"))
        if method == "review_preview":
            record = self.work_sessions.inspect(params.get("run"), params.get("conversation_id", ""))
            return self._review_preview(params, record)
        if method == "review_save":
            return self.save_review(params)
        if method in {"artifact_list", "artifact_preview"}:
            record = self.work_sessions.inspect(params.get("run"), params.get("conversation_id", ""))
            if method == "artifact_list":
                return artifact_page(record)
            return artifact_preview(record, params.get("artifact_id", ""), self._artifact_workspace(params, record))
        if method == "work_session_continuation":
            workspace = workspace_identity(self.workspace(params).root) if params.get("workspace_root") else None
            result = self.work_sessions.continuation(params.get("continuation"), params.get("conversation_id", ""), workspace)
            if result["sources"]:
                self.workspace(params).context_files(result["sources"])
            return result
        if method == "account_status":
            return self.subscription.account()
        if method == "account_login":
            return self.subscription.login()
        if method == "account_logout":
            self.agent_grants.revoke()
            return self.subscription.logout()
        if method == "codex_thread_status":
            conversation = str(UUID(str(params.get("conversation_id", ""))))
            workspace = workspace_identity(self.workspace(params).root) if params.get("workspace_root") else None
            return self.subscription.thread_status(conversation, workspace)
        if method == "codex_thread_reset":
            if self.busy.locked() or self.closing.is_set():
                raise ValueError("Wait for the active turn to finish before starting a new Codex session.")
            if params.get("confirmation") != RESET_CODEX_THREAD_CONFIRMATION:
                raise ValueError("Explicit confirmation is required to start a new Codex session.")
            conversation = str(UUID(str(params.get("conversation_id", ""))))
            self.agent_grants.revoke(conversation)
            return self.subscription.reset_thread(conversation)
        if method == "agent_access":
            if self.busy.locked() or self.closing.is_set():
                raise ValueError("Wait for the active turn to finish before changing access.")
            conversation = str(UUID(str(params.get("conversation_id", ""))))
            if params.get("mode") == "chat":
                self.agent_grants.revoke(conversation)
                return {"mode": "chat", "token": ""}
            if params.get("mode") != "full_access" or params.get("cloud_consent") is not True:
                raise ValueError("Full Mac is a separate explicit grant and requires cloud consent.")
            workspace = self.workspace(params).root
            return self.agent_grants.enable(conversation, workspace, params.get("confirmation"))
        if method == "models":
            return {"models": self.subscription.models()}
        if method == "ollama_status":
            config = ProtoMindConfig.from_env(self.root / "proto_mind")
            try:
                response = local_ollama_request(config, "/api/tags", timeout=3)
                models = response.get("models", [])
                if not isinstance(models, list):
                    raise ValueError("Invalid local model list.")
                return {"connected": True, "models": [item["name"] for item in models if isinstance(item, dict) and isinstance(item.get("name"), str)],
                        "notice": "Local model inventory only; no generation or download requested."}
            except (OSError, ValueError):
                return {"connected": False, "models": [], "notice": "Ollama is unavailable. Start it locally; no fallback or model download was attempted."}
        if method == "workspace_status":
            return self.workspace(params).status()
        if method == "workspace_list":
            return self.workspace(params).list_directory(params.get("path", ""))
        if method == "workspace_read":
            return self.workspace(params).read_file(params.get("path", ""))
        if method == "memory_workshop":
            if set(params) - {"conversation_id", "workspace_root"}:
                raise ValueError("Unexpected Memory Workshop parameter. Nothing was executed.")
            conversation = str(UUID(str(params.get("conversation_id", ""))))
            workspace = (
                workspace_identity(self.workspace(params).root)
                if params.get("workspace_root")
                else None
            )
            return build_native_memory_workshop(
                self.sessions.get(conversation),
                conversation_id=conversation,
                workspace=workspace,
            )
        if method == "library_list":
            return NativeLibrary(self.root).page(params.get("collection"), query=params.get("query", ""),
                                                 filter=params.get("filter", "current"), offset=params.get("offset", 0))
        if method == "library_inspect":
            return NativeLibrary(self.root).inspect(params.get("collection"), params.get("record_key"),
                                                    expected_sha256=params.get("expected_sha256", ""))
        if method == "capability_search":
            return search_local_knowledge(NativeLibrary(self.root), params)
        if method == "capability_fetch":
            return fetch_local_knowledge(NativeLibrary(self.root), params)
        raise ValueError("Unknown native bridge method.")

    def cancel(self, request_id: str) -> dict:
        if request_id != self.active_request:
            return {"cancel_requested": False, "notice": "No matching active turn."}
        if self.active_provider != "codex":
            return {"cancel_requested": False, "notice": "This operation must finish safely; no process was killed."}
        self.subscription.interrupt()
        return {"cancel_requested": True, "notice": "Codex stop requested."}

    def close(self) -> None:
        self.agent_grants.revoke()
        self.subscription.close()

    def disconnect(self) -> None:
        self.closing.set()
        self.agent_grants.revoke()
        if self.active_provider == "codex":
            self.subscription.interrupt()


def serve(backend: NativeBackend, source, destination) -> None:
    output_lock = threading.Lock()

    def emit(value: dict) -> None:
        with output_lock:
            destination.write(json.dumps(value, ensure_ascii=False, allow_nan=False) + "\n")
            destination.flush()

    def run(message: dict) -> None:
        request_id = message["id"]
        try:
            with redirect_stdout(sys.stderr):
                result = backend.dispatch(message["method"], message.get("params", {}), emit, request_id)
            emit({"id": request_id, "result": result})
        except Exception as exc:
            # Never copy protocol payloads, prompts, credentials, or tracebacks into the UI.
            safe = str(exc) if isinstance(exc, (ValueError, RuntimeError)) else "Native bridge operation failed. No automatic retry."
            emit({"id": request_id, "error": {"message": safe[:600]}})

    with ThreadPoolExecutor(max_workers=1, thread_name_prefix="proto-native") as executor:
        while True:
            raw = source.readline(MAX_REQUEST_BYTES + 1)
            if not raw:
                backend.disconnect()
                break
            request_id = None
            try:
                if len(raw.encode("utf-8")) > MAX_REQUEST_BYTES:
                    raise ValueError("Native request is too large.")
                message = json.loads(raw)
                if not isinstance(message, dict) or not isinstance(message.get("id"), str) or len(message["id"]) > 100:
                    raise ValueError("Invalid request ID.")
                request_id = message["id"]
                if not isinstance(message.get("method"), str) or not isinstance(message.get("params", {}), dict):
                    raise ValueError("Invalid request shape.")
                if message["method"] == "cancel":
                    emit({"id": request_id, "result": backend.cancel(str(message.get("params", {}).get("request_id", "")))})
                else:
                    executor.submit(run, message)
            except (ValueError, TypeError) as exc:
                emit({"id": request_id, "error": {"message": str(exc)[:200]}})
    backend.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Proto-Mind native stdio bridge")
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--pdf-helper", type=Path)
    args = parser.parse_args()
    if not (args.project_root / "proto_mind" / "main.py").is_file():
        parser.error("Project root does not contain Proto-Mind.")
    backend = NativeBackend(args.project_root, args.state_dir, pdf_helper=args.pdf_helper)
    serve(backend, sys.stdin, sys.stdout)


if __name__ == "__main__":
    main()
