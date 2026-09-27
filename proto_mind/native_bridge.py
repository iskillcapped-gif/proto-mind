"""Private stdio bridge for the native macOS client; no listening socket."""
from __future__ import annotations

from proto_mind.python_env import enforce_python_version

enforce_python_version()

import argparse
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack, nullcontext, redirect_stdout
from proto_mind.native_workspace_tools import WorkspaceTools
from proto_mind.native_steering import LiveSteering, SteeringAttachments
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
from proto_mind.native_codex import (
    CHAT_DEVELOPER_INSTRUCTIONS,
    CodexSubscription,
    SubscriptionReasoner,
    validate_reasoning_effort,
    resolve_model_selection,
    require_image_model,
)
from proto_mind.native_instructions import (
    build_instruction_receipt,
    build_instruction_preview,
    claude_session_contract,
    prepare_local_instructions,
)
from proto_mind.native_computer_use import public_computer_use_capability
from proto_mind.local_knowledge_capabilities import (
    fetch_local_knowledge,
    local_knowledge_descriptors,
    search_local_knowledge,
)
from proto_mind.native_agent import AGENT_INSTRUCTIONS, AgentGrants, FULL_ACCESS_CONFIRMATION
from proto_mind.native_library import NativeLibrary
from proto_mind.native_codex_usage import read_usage
from proto_mind.native_codex_reset import CodexResetStore, consume_reset
from proto_mind.native_memory_workshop import build_native_memory_workshop
from proto_mind.native_learning_review import NativeLearningReview, parse_learning_request
from proto_mind.native_skill_authoring import NativeSkillAuthoring, NativeSkillSession, parse_skill_request
from proto_mind.native_skill_inspection import NativeSkillInspection, parse_skill_inspection_request
from proto_mind.native_skill_outcome import NativeSkillOutcome, parse_skill_outcome_request
from proto_mind.native_skill_decision import NativeSkillDecision, parse_skill_decision_request
from proto_mind.native_skill_lifecycle import NativeSkillLifecycle, parse_skill_lifecycle_request
from proto_mind.native_skill_restore import NativeSkillRestore, parse_skill_restore_request
from proto_mind.native_learning_history import NativeLearningHistory, parse_history_request
from proto_mind.native_project_memory import NativeProjectMemory, parse_project_memory_request, METHODS as PROJECT_MEMORY_METHODS
from proto_mind.native_memory_suggestions import (NativeMemorySuggestion, suggestions as memory_suggestions,
                                                parse_request as parse_memory_suggestion_request, METHODS as MEMORY_SUGGESTION_METHODS)
from proto_mind.project_recall_search import requested_algorithm
from proto_mind.native_project_recall import ProjectRecall
from proto_mind.native_skill_tasks import NativeSkillTask, parse_task_request, SELECT_FIELDS as SKILL_TASK_SELECT_FIELDS
from proto_mind.native_auto_skills import AutoSkills, HISTORY_BOUNDARY as AUTO_SKILL_HISTORY_BOUNDARY
from proto_mind.native_starter_skills import StarterSkills
from proto_mind.native_knowledge import knowledge_metadata, knowledge_context_message
from proto_mind.native_private_records import HASH, encoded
from proto_mind.skill_lifecycle_restore_apply import procedural_skill_restore_apply_receipts_snapshot
from proto_mind.experience_pilot import peek_experience_pilot
from proto_mind.native_workspace import WorkspaceReader, file_context_message
from proto_mind.native_images import ImageReader, image_specifications, MAX_IMAGES, MAX_IMAGE_BYTES, MAX_TOTAL_IMAGE_BYTES
from proto_mind.native_pdf import PDFReader, SelectedPDF, pdf_context_message
from proto_mind.persona_activation_readiness import build_persona_activation_readiness
from proto_mind.persona_activation import PersonaTurnActivation
from proto_mind.native_persona import (
    NativePersonaRequest,
    build_native_persona_preview,
    build_native_persona_runtime,
)
from proto_mind.persona_engine import validate_persona_snapshot
from proto_mind.native_history_routes import HISTORY_METHODS, dispatch_history
from proto_mind.native_github import GitHubConnection, METHODS as GITHUB_METHODS
from proto_mind.native_private_restore import PrivateRestore, METHODS as PRIVATE_BACKUP_METHODS
from proto_mind.private_state_gate import generation, require_available
from proto_mind.native_work_sessions import WorkSessionStore, WorkSessionError, workspace_identity
from proto_mind.native_desk import context_manifest, context_preview, capture_artifacts, review_observations
from proto_mind.native_review import CONFIRM_REVIEW, criteria_context_message, validate_criteria, review_preview
from proto_mind.observer import Observer
from proto_mind.reasoners.mock_reasoner import MockReasoner
from proto_mind.reasoners.ollama_reasoner import OllamaReasoner
from proto_mind.session_log import SessionOperatorLogger


BRIDGE_VERSION = 1
MAX_INPUT_CHARS = 32_000
MAX_REQUEST_BYTES = 4 * 1024 * 1024
MAX_LIVE_SESSIONS = 32
ATTACHMENT_READ_METHODS = {"image_preview", "pdf_preview", "pdf_render_page", "workspace_status", "workspace_list", "workspace_read"}
RESET_CODEX_THREAD_CONFIRMATION = "START NEW CODEX SESSION"


def _canonical_hash(value: object) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def memory_scope(workspace: dict | None) -> str | None:
    """Core-memory project scope. A linked Git worktree, such as an isolated PM
    task, shares its main checkout's scope; any other folder keeps its own."""
    from proto_mind.native_worktrees import project_workspace
    return _canonical_hash(project_workspace(workspace)) if workspace else None


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
        super().__init__(working_path, persistent_path, initialize=False)

    def _load_records(self, path: Path):
        return super()._load_records(path) if path.exists() else []

    def _save_records(self, path: Path, records) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        super()._save_records(path, records)


from proto_mind.native_api import APITransport, NativeAPIReasoner, validate_connection
from proto_mind.native_claude import ClaudeTransport, NativeClaudeReasoner, usage_notice as claude_usage_notice, status as claude_status, authentication_command as claude_auth_command
from proto_mind.native_claude_contract import validate_effort as claude_effort
from proto_mind.native_claude_metadata import ClaudeMetadataReader


class NativeOllamaReasoner(OllamaReasoner):
    def __init__(self, config: ProtoMindConfig, history: list[dict], files: list[dict] | None = None,
                 criteria: list[str] | None = None, pdfs: list[SelectedPDF] | None = None,
                 persona_activation: PersonaTurnActivation | None = None, project_notes: list[dict] | None = None,
                 skill_task: dict | None = None, before_provider_call=None) -> None:
        super().__init__(config)
        self.history = history
        self.files = files or []
        self.pdfs = pdfs or []
        self.criteria = validate_criteria([] if criteria is None else criteria)
        self.persona_activation = persona_activation
        self.last_persona_receipt: dict | None = None
        self.last_instruction_receipt: dict | None = None
        self.project_notes = project_notes or []
        self.skill_task, self.before_provider_call = skill_task, before_provider_call

    def _post(self, path: str, payload: dict) -> dict:
        messages = payload["messages"]
        return local_ollama_request(self.config, path, {**payload, "messages": [messages[0], *self.history, messages[-1]]})

    def respond(self, user_input, retrieved_memory, observer_state, correction_hints=None) -> str:
        if self.before_provider_call:
            self.before_provider_call()
        hints = correction_hints or []
        prepared = prepare_local_instructions(
            "ollama",
            observer_state,
            retrieved_memory,
            hints,
            persona_activation=self.persona_activation,
        )
        instructions = prepared.text
        self.last_persona_receipt = prepared.persona_receipt
        self.last_instruction_receipt = build_instruction_receipt(
            provider="ollama",
            mode="chat",
            prepared=prepared,
            developer_instructions=None,
            selected_memory=retrieved_memory,
            correction_hints=hints,
        )
        payload = {
            "model": self.config.ollama_model,
            "messages": [
                {"role": "system", "content": instructions},
                {"role": "user", "content": criteria_context_message(self.criteria) + file_context_message(self.files)
                 + pdf_context_message(self.pdfs) + knowledge_context_message(self.project_notes, self.skill_task) + user_input.strip()},
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


def bounded_history(value: object, provider: str = "") -> list[dict]:
    if provider == "claude":
        from proto_mind.native_claude_sessions import bootstrap_history
        return bootstrap_history(value)
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
    text = text.strip()
    preview = build_action_preview(text)
    operator = text.startswith("/")
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
                 pdf_helper: Path | None = None, codex_account: str | None = None) -> None:
        self.root, self.state_dir = project_root.resolve(), state_dir.resolve()
        # The launch-time account is immutable for this bridge. Core/history stay
        # in their existing namespace; credentials and provider sessions do not.
        if codex_account is not None:
            if not isinstance(codex_account, str) or str(UUID(codex_account)) != codex_account:
                raise ValueError("Invalid Codex account profile.")
        self.subscription_state = (self.state_dir / "codex-accounts" / codex_account
                                   if codex_account is not None else self.state_dir)
        self.pdf_helper = pdf_helper
        if codex_account is not None:
            for path in (self.state_dir / "codex-accounts", self.subscription_state,
                         self.state_dir / "codex_account_threads", self.state_dir / "codex_account_threads" / codex_account):
                if path.is_symlink():
                    raise ValueError("Codex account directories must not be symbolic links.")
            self._subscription_factory = lambda state: subscription_factory(
                state, thread_state_dir=self.state_dir / "codex_account_threads" / codex_account)
        else:
            self._subscription_factory = subscription_factory
        self.subscription = self._subscription_factory(self.subscription_state)
        self._limits_read_lock = threading.Lock()
        self.sessions: dict[str, Coordinator] = {}
        self._native_learning_apply_used = False
        self._native_skill_apply_used = False
        self._native_skill_lifecycle_apply_used = False
        self._native_skill_restore_used = False
        self._native_skill_session = NativeSkillSession()
        self.logger = SessionOperatorLogger.from_project_root(self.root)
        self.active_request: str | None = None
        self.active_provider: str | None = None
        self.active_api: APITransport | None = None
        self.active_claude: ClaudeTransport | None = None
        self.claude_metadata = ClaudeMetadataReader(self.state_dir)
        self.active_steering: LiveSteering | None = None
        self.workspace_tools: WorkspaceTools | None = None
        from proto_mind.native_mcp import MCPSession
        self.mcp_session = MCPSession()
        self.busy = threading.Lock()
        self.agent_grants = AgentGrants()
        self.github = GitHubConnection(self.state_dir)
        self.private_backup = PrivateRestore(self.root, self.state_dir)
        self._private_generation = (generation(self.root / "proto_mind/data"), generation(self.state_dir))
        self._private_restart_required = False
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

    def agent_workspace(self, params: dict) -> Path | None:
        # Absence is an explicit projectless scope, never the app's own project.
        return self.workspace(params).root if params.get("workspace_root") is not None else None

    def image_reader(self) -> ImageReader:
        return ImageReader(protected_roots=self.protected_input_roots)

    def pdf_reader(self) -> PDFReader:
        return PDFReader(protected_roots=self.protected_input_roots, helper=self.pdf_helper)

    def _persona_runtime_evidence(self, request: NativePersonaRequest) -> tuple[Path | None, bool, bool]:
        workspace = self.workspace({"workspace_root": request.workspace_root}).root if request.workspace_root is not None else None
        grant_verified = False
        computer_use_available = False
        if request.access_mode == "full_access":
            if request.provider != "codex" or request.cloud_consent is not True:
                raise ValueError("Full Mac Persona preview requires Codex and cloud consent.")
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
        from proto_mind.native_agent_contract import requested_contract_version
        agent_contract_version = requested_contract_version(params)
        tools_version = params.get("workspace_tools_version", 0)
        if type(tools_version) is not int or tools_version not in {0, 1} or type(params.get("api_workspace_tools", False)) is not bool:
            raise ValueError("Invalid workspace tool capability request.")
        if self.closing.is_set():
            raise ValueError("The Native window disconnected. No new turn will start.")
        text = input_text(params)
        session_id = str(UUID(str(params.get("conversation_id", ""))))
        description = describe_input(text)
        persona_enabled = params.get("persona_enabled", False)
        if type(persona_enabled) is not bool:
            raise ValueError("Invalid Brother Persona activation state.")
        if type(params.get("auto_skills", False)) is not bool:
            raise ValueError("Automatic skill selection must be explicitly on or off.")
        if type(params.get("local_skill_selection", False)) is not bool:
            raise ValueError("Invalid local skill selection setting.")
        recall_algorithm = requested_algorithm(params)
        if type(params.get("auto_project_recall", False)) is not bool:
            raise ValueError("Automatic project recall must be explicitly on or off.")
        if type(params.get("memory_suggestions", False)) is not bool:
            raise ValueError("Project memory suggestions must be explicitly on or off.")
        expected_snapshot = params.get("expected_project_snapshot")
        if "expected_project_snapshot" in params and (not isinstance(expected_snapshot, str) or not HASH.fullmatch(expected_snapshot)):
            raise ValueError("Invalid reviewed project-note snapshot.")
        if description["blocked"]:
            raise ValueError(description["notice"])
        if description["requires_confirmation"] and params.get("confirmed_text") != text:
            raise ValueError("Confirm the exact operator command before running it.")
        provider = params.get("provider", "ollama")
        if provider not in {"ollama", "mock", "codex", "api", "claude"}:
            raise ValueError("Unknown model provider.")
        model = params.get("model", "")
        if not isinstance(model, str) or len(model) > 160 or "\x00" in model:
            raise ValueError("Invalid model name.")
        reasoning_effort = validate_reasoning_effort(params.get("reasoning_effort", "")) if provider == "codex" and not description["operator"] else ""
        if provider == "claude" and not description["operator"]:
            reasoning_effort = claude_effort(params.get("reasoning_effort", ""))
            if persona_enabled: raise ValueError("Brother Persona is available through Codex and Ollama. Claude uses the core memory.")
        history = bounded_history(params.get("history", []), provider)
        criteria = [] if description["operator"] else validate_criteria(params.get("criteria", []))
        if provider in {"codex", "api", "claude"} and not description["operator"] and params.get("cloud_consent") is not True:
            raise ValueError("Разрешите облачную обработку в настройках перед отправкой сообщений и памяти API."
                             if provider == "api" else "Select and approve cloud processing before sending messages or recalled memories to the selected cloud provider.")
        if description["operator"] and persona_enabled:
            raise ValueError("Brother Persona is not applied to operator commands. No command was executed.")
        if provider == "api" and not description["operator"]:
            validate_connection(params.get("api_connection"))
            if not model:
                raise ValueError("Выберите точный ID модели API.")
            if persona_enabled:
                raise ValueError("Brother Persona пока поддерживается через Codex и Ollama. API использует базовую память ядра.")
        agent_workspace = None
        mode = "chat"
        if not description["operator"]:
            mode = params.get("access_mode", "chat")
            if mode not in {"chat", "full_access"}:
                raise ValueError("Unknown model access mode.")
            if mode == "full_access":
                if provider not in {"codex", "claude"}:
                    raise ValueError("Full Mac tools currently require the explicitly selected Codex provider.")
                grant = self.agent_grants.validate(session_id, self.agent_workspace(params), params.get("access_token"))
                agent_workspace = Path(grant["execution_root"])
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
            if provider not in {"codex", "claude"}:
                raise ValueError("Image input requires an explicitly selected Codex or Claude model. Ollama, Mock and API images are not implemented; no provider was changed.")
            images = self.image_reader().selected(params["images"])
        pdfs = [] if description["operator"] else self.pdf_reader().selected(params.get("pdfs", []))
        logical_workspace = (workspace_identity(self.workspace(params).root)
                             if not description["operator"] and params.get("workspace_root") else None)
        project_notes = [] if description["operator"] else self._selected_project_notes(params, session_id)
        project_recall = None
        if not description["operator"] and provider in {"codex", "claude"} and params.get("auto_project_recall") is True and not project_notes:
            project_recall = ProjectRecall(self.root, self.state_dir, conversation=session_id,
                                           workspace=logical_workspace, text=text, mode=mode, algorithm=recall_algorithm)
            project_notes = project_recall.notes
        if expected_snapshot is not None and (project_recall is None or expected_snapshot != project_recall.report["source_snapshot_hash"]):
            raise ValueError("Project notes changed since context preview. Preview again; no main task, fallback or automatic retry.")
        recall_report = project_recall.report if project_recall else None
        skill_task = None if description["operator"] else self._selected_skill_task(params, session_id, text=text, criteria=criteria)
        auto_skills = None
        def revalidate_knowledge():
            if project_recall is not None:
                project_recall.revalidate()
            elif project_notes and self._selected_project_notes(params, session_id) != project_notes:
                raise WorkSessionError("Project notes changed before the provider call. Review them again; no fallback.")
            if skill_task and self._selected_skill_task(params, session_id, text=text, criteria=criteria) != skill_task:
                raise WorkSessionError("Skill task changed before the provider call. Review it again; no fallback.")
            if auto_skills and auto_skills.report["state"] in {"selected", "no_match", "local_selected", "local_no_match"}:
                auto_skills.revalidate()
            if agent_workspace is not None:
                self.agent_grants.validate(session_id, self.agent_workspace(params), params.get("access_token"))
        if mode == "full_access" and bool(tools_version) != (agent_contract_version == 3):
            raise ValueError("Workspace tools require an explicit v3 agent contract.")
        provider_thread = (self.subscription.thread_status(session_id, logical_workspace, mode=mode, **({"workspace_tools": True} if tools_version else {}))
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
                claude_plan = None
                if provider == "claude":
                    from proto_mind.native_claude_sessions import ClaudeSessionPlan
                    account = claude_status(self.state_dir)
                    if not account["connected"]:
                        raise ValueError("Sign in through Claude Code in Settings → Connections first.")
                    claude_plan = ClaudeSessionPlan(self.state_dir, session_id, account=account,
                        workspace=logical_workspace, full_access=mode == "full_access", tools=bool(tools_version), history=history,
                        contract=claude_session_contract(full_access=mode == "full_access",
                                                         workspace_tools=mode == "full_access" and bool(tools_version)))
                    provider_history, provider_thread = claude_plan.history, claude_plan.public()
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
                        provider_thread=provider_thread, knowledge_context=knowledge_metadata(project_notes, skill_task, recall=recall_report))))
            if provider == "codex" and not description["operator"]:
                self.subscription.prepare_turn()
                def require_steering_vision():
                    options = self.subscription.models()
                    resolved, _ = resolve_model_selection(options, model, reasoning_effort)
                    require_image_model(options, resolved)
                self.active_steering = LiveSteering(request_id, session_id, emit, attachments=SteeringAttachments(
                    self.workspace(params) if logical_workspace else None, self.image_reader(), self.pdf_reader(), require_steering_vision))
                self.subscription.on_main_turn = self.active_steering.set_active
            elif provider == "claude" and not description["operator"]:
                # Every current Claude model accepts images, so no vision preflight.
                self.active_steering = LiveSteering(request_id, session_id, emit, attachments=SteeringAttachments(
                    self.workspace(params) if logical_workspace else None, self.image_reader(), self.pdf_reader(), lambda: None))
            if params.get("workspace_tools_version") == 1 and not description["operator"] and (mode == "full_access" or provider == "api" and params.get("api_workspace_tools") is True):
                # Claude with Full Mac also gets computer use; Codex has its own.
                self.workspace_tools = WorkspaceTools(request_id, session_id, emit,
                                                      computer_use=provider == "claude" and mode == "full_access")
                self.subscription.workspace_tools = self.workspace_tools
            self.active_request, self.active_provider = request_id, provider if not description["operator"] else "operator"
            if self.closing.is_set():
                raise ValueError("Native disconnected before processing; no new work started.")
            coordinator = self._coordinator(session_id)
            scope = memory_scope(logical_workspace)
            if coordinator.memory_keeper.context_scope != scope:
                coordinator.pending_correction_hints = []
            coordinator.memory_keeper.context_scope = scope
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
                if event.get("event") == "answer_reset":
                    emit({"event": "answer_reset", "request_id": request_id})
                if event.get("event") == "work_log":
                    work_log = event["log"]
                    if work_session is not None:
                        work_session.observe(event)
                    emit({**event, "request_id": request_id})

            if not description["operator"]:
                config = ProtoMindConfig.from_env(self.root / "proto_mind")
                if provider == "codex":
                    if params.get("auto_skills") is True and skill_task is None:
                        auto_skills = AutoSkills(self.root, conversation=session_id, workspace=logical_workspace, text=text, mode=mode)
                        if params.get("local_skill_selection") is True:
                            auto_skills.select_local(text=text, emit=activity)
                        else:
                            auto_skills.select(self.subscription, text=text, history=history, model=model, emit=activity)
                    coordinator.reasoner = SubscriptionReasoner(
                        self.subscription, model, history,
                        lambda delta: emit({"event": "answer_delta", "request_id": request_id, "delta": delta}),
                        conversation=session_id, logical_workspace=logical_workspace,
                        files=files,
                        agent_workspace=agent_workspace, on_activity=activity, on_progress=progress,
                        agent_contract_version=agent_contract_version,
                        reasoning_effort=reasoning_effort,
                        criteria=criteria,
                        images=images,
                        pdfs=pdfs,
                        persona_activation=persona_activation,
                        project_notes=project_notes,
                        project_notes_automatic=project_recall is not None,
                        project_note_history_boundary="auto_project_recall" in params,
                        skill_task=skill_task, before_provider_call=revalidate_knowledge,
                        auto_skill_guidance=(AUTO_SKILL_HISTORY_BOUNDARY if "auto_skills" in params else "") + (auto_skills.guidance() if auto_skills else ""),
                    )
                elif provider == "api":
                    self.active_api = APITransport(params["api_connection"])
                    self.active_api.workspace_tools = self.workspace_tools
                    self.active_api.on_activity = activity
                    self.active_api.on_progress = progress
                    coordinator.reasoner = NativeAPIReasoner(self.active_api, model, history,
                        lambda delta: emit({"event": "answer_delta", "request_id": request_id, "delta": delta}),
                        files=files, criteria=criteria, pdfs=pdfs, project_notes=project_notes,
                        skill_task=skill_task, before_provider_call=revalidate_knowledge)
                elif provider == "claude":
                    self.active_claude = ClaudeTransport(self.state_dir, workspace=agent_workspace,
                        full_access=mode == "full_access", effort=reasoning_effort, images=images, session_plan=claude_plan)
                    self.active_claude.workspace_tools = self.workspace_tools
                    self.active_claude.on_activity = activity
                    self.active_claude.on_progress = progress
                    steering = self.active_steering
                    self.active_claude.on_steering = lambda target: steering.set_active(("claude", request_id) if target else None, target)
                    coordinator.reasoner = NativeClaudeReasoner(self.active_claude, model, history,
                        lambda delta: emit({"event": "answer_delta", "request_id": request_id, "delta": delta}),
                        files=files, criteria=criteria, pdfs=pdfs, project_notes=project_notes,
                        skill_task=skill_task, before_provider_call=revalidate_knowledge)
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
                        project_notes=project_notes,
                        skill_task=skill_task, before_provider_call=revalidate_knowledge,
                    )
                else:
                    coordinator.reasoner = MockReasoner()
            if work_session is not None:
                saved_workspace = work_session.record["workspace"]
                if saved_workspace and workspace_identity(Path(saved_workspace["path"])) != saved_workspace:
                    raise WorkSessionError("Workspace changed before dispatch. Choose and inspect the folder again.")
                revalidate_knowledge()
                work_session.dispatch()
            output = process_interactive_input_with_envelope(
                text, coordinator=coordinator, session_logger=self.logger, project_root=self.root,
                hygiene=MemoryHygiene(coordinator.memory_keeper.store),
                natural_commands=False,
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
            usage = claude_usage_notice(self.active_claude.usage) if provider == "claude" and self.active_claude else None
            if usage:
                serialized["notices"].append(usage)
            if provider == "claude" and self.active_claude and self.active_claude.undelivered_updates:
                serialized["notices"].append("An update sent near the end of this Claude turn was not confirmed as seen by the model. "
                                             "Send it again as a new message if it still matters; nothing was resent automatically.")
            persona_receipt = getattr(coordinator.reasoner, "last_persona_receipt", None)
            instruction_receipt = getattr(coordinator.reasoner, "last_instruction_receipt", None)
            if (not description["operator"] and provider in {"codex", "ollama", "api", "claude"}
                    and not isinstance(instruction_receipt, dict)):
                raise ValueError("Provider instruction assembly did not produce a validated content-free receipt.")
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
            if project_recall is not None:
                serialized["notices"].append("Automatic project recall: " + project_recall.report["reason"]
                                             + " No note writes, learning, extra model call or permission change. Previously sent notes may remain in provider history.")
            elif project_notes:
                serialized["notices"].append("Explicit project notes: operator assertions, not independently verified facts. No automatic recall or permission change. "
                                             + ("Mock does not analyze these notes." if provider == "mock" else "Previously sent notes can remain in provider-side conversation history."))
            if skill_task:
                serialized["notices"].append("Operator-selected skill guidance: " + skill_task["skill_id"]
                                             + ". Provenance checked, task outcome not automatically verified or accepted. Review the journal and each criterion; no automatic skill learning."
                                             + (" Mock does not execute or understand this procedure." if provider == "mock" else ""))
            saved_session = None
            if work_session is not None:
                reader = self._artifact_workspace(params, work_session.record)
                artifacts = capture_artifacts(work_session.record, reader)
                saved_session = work_session.complete(
                    serialized.get("text") or "",
                    artifacts=artifacts,
                    instruction_receipt=instruction_receipt,
                )
            suggestions_report = None
            if params.get("memory_suggestions") is True and provider == "codex" and saved_session and logical_workspace:
                try:
                    suggestions_report = memory_suggestions(self.root, self.state_dir, saved_session, text)
                except (ValueError, OSError, WorkSessionError):
                    serialized["notices"].append("Project memory suggestions unavailable; the completed answer is preserved. No note was saved.")
            return {**serialized, "operator": description["operator"],
                    "conversation_id": session_id, "exit_requested": output.text is None,
                    "agent_run": agent_receipt,
                    "persona_activation": persona_receipt,
                    "work_log": work_log,
                    "provider_thread": self.subscription.last_thread_info if provider == "codex" and not description["operator"] else None,
                    "work_session": saved_session,
                    "auto_skills": auto_skills.report if auto_skills else None,
                    "memory_suggestions": suggestions_report,
                    "image_context": [image.metadata for image in images],
                    "pdf_context": [pdf.metadata for pdf in pdfs],
                    "knowledge_context": knowledge_metadata(project_notes, skill_task, recall=recall_report),
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
                if self.active_steering is not None:
                    self.active_steering.stop()
                    self.active_steering.set_active(None)
                    self.subscription.on_main_turn = None
                    self.active_steering = None
                if self.workspace_tools is not None:
                    self.workspace_tools.cancel()
                    self.workspace_tools = None
                    self.subscription.workspace_tools = None
                self.active_request = self.active_provider = None
                self.active_api = None
                self.active_claude = None
                self.busy.release()

    def _artifact_workspace(self, params: dict, record: dict) -> WorkspaceReader | None:
        try:
            if not params.get("workspace_root") or not record.get("workspace"):
                return None
            reader = self.workspace(params)
            return reader if workspace_identity(reader.root) == record["workspace"] else None
        except (OSError, ValueError):
            return None

    def _instruction_preview(
        self,
        params: dict,
        *,
        text: str,
        provider: str,
        mode: str,
        operator: bool,
        logical_workspace: dict | None = None,
    ) -> dict:
        persona_enabled = params.get("persona_enabled", False)
        if type(persona_enabled) is not bool:
            raise ValueError("Invalid Brother Persona inspection state.")
        if operator or provider == "mock":
            return build_instruction_preview(
                provider=provider,
                mode=mode,
                operator=operator,
                prepared=None,
                developer_instructions=None,
            )

        conversation_id = None
        try:
            if params.get("conversation_id"):
                conversation_id = str(UUID(str(params["conversation_id"])))
        except (TypeError, ValueError, AttributeError):
            raise ValueError("Invalid conversation id for local instruction inspection.") from None
        coordinator = self.sessions.get(conversation_id) if conversation_id else None
        observer = coordinator.observer if coordinator is not None else Observer()
        observer_state = observer.analyze(text)
        scope = memory_scope(logical_workspace)
        correction_hints = (list(coordinator.pending_correction_hints)
                            if coordinator is not None and coordinator.memory_keeper.context_scope == scope else [])
        retrieved_memory = []
        if observer_state.needs_memory:
            data = self.root / "proto_mind" / "data"
            keeper = MemoryKeeper(NativeMemoryStore(
                data / "working_memory.json",
                data / "persistent_memory.json",
            ))
            keeper.context_scope = scope
            top_k = 10 if observer_state.query_type == "memory_inventory" else 5
            retrieved_memory = keeper.retrieve(
                observer_state,
                top_k=top_k,
                user_input=text,
                track_usage=False,
            )

        persona_activation = None
        if persona_enabled:
            if conversation_id is None:
                raise ValueError("Brother Persona inspection requires a valid conversation id.")
            persona_activation = self._prepare_persona_activation(
                params,
                session_id=conversation_id,
                provider=provider,
                model=params.get("model", ""),
                mode=mode,
            )
        prepared = prepare_local_instructions(
            provider,
            observer_state,
            retrieved_memory,
            correction_hints,
            persona_activation=persona_activation,
            claude_full_access=provider == "claude" and mode == "full_access",
            claude_workspace_tools=provider == "claude" and mode == "full_access" and params.get("workspace_tools_version") == 1,
        )
        developer = None
        if provider == "codex":
            developer = AGENT_INSTRUCTIONS if mode == "full_access" else CHAT_DEVELOPER_INSTRUCTIONS
        return build_instruction_preview(
            provider=provider,
            mode=mode,
            operator=False,
            prepared=prepared,
            developer_instructions=developer,
            selected_memory=retrieved_memory,
            correction_hints=correction_hints,
            retrieval_performed=observer_state.needs_memory,
        )

    def preview_context(self, params: dict) -> dict:
        text = params.get("text", "")
        if not isinstance(text, str) or len(text) > MAX_INPUT_CHARS or "\x00" in text:
            raise ValueError("Invalid draft for local context inspection.")
        text = text.strip()
        provider, mode = params.get("provider", "ollama"), params.get("access_mode", "chat")
        if provider not in {"codex", "ollama", "mock", "api", "claude"} or mode not in {"chat", "full_access"}:
            raise ValueError("Unknown provider or access mode.")
        model = params.get("model", "")
        if not isinstance(model, str) or len(model) > 160 or "\x00" in model:
            raise ValueError("Invalid model name.")
        operator = describe_input(text)["operator"] if text else False
        if type(params.get("auto_skills", False)) is not bool:
            raise ValueError("Invalid automatic skill selection setting.")
        recall_algorithm = requested_algorithm(params)
        if type(params.get("auto_project_recall", False)) is not bool:
            raise ValueError("Invalid automatic project recall setting.")
        reader = self.workspace(params) if params.get("workspace_root") and not operator else None
        local_history = bounded_history(params.get("history", []), provider)
        logical_workspace = workspace_identity(reader.root) if reader else None
        provider_thread = (self.subscription.thread_status(params.get("conversation_id", ""), logical_workspace,
                                                           mode=mode, **({"workspace_tools": True} if params.get("workspace_tools_version") == 1 else {}))
                           if provider == "codex" and not operator else None)
        provider_history = [] if provider_thread and provider_thread["linked"] else local_history
        if provider == "claude" and not operator:
            from proto_mind.native_claude_sessions import ClaudeSessionPlan
            tools = params.get("workspace_tools_version") == 1
            plan = ClaudeSessionPlan(self.state_dir, params.get("conversation_id", ""), account=claude_status(self.state_dir),
                workspace=logical_workspace, full_access=mode == "full_access", tools=tools, history=local_history,
                contract=claude_session_contract(full_access=mode == "full_access", workspace_tools=mode == "full_access" and tools))
            provider_history, provider_thread = plan.history, plan.public()
        result = context_preview(root=self.root, text=text, history=provider_history,
                                 provider=provider, model=model,
                                 effort=(claude_effort(params.get("reasoning_effort", "")) if provider == "claude" else validate_reasoning_effort(params.get("reasoning_effort", ""))) if provider in {"codex", "claude"} and not operator else "",
                                 mode=mode, workspace=str(reader.root) if reader else None, operator=operator,
                                 criteria=validate_criteria(params.get("criteria", [])),
                                 reader=reader, specifications=params.get("files", []), cloud_consent=params.get("cloud_consent") is True,
                                 provider_thread=provider_thread)
        result["instruction_preview"] = self._instruction_preview(
            params,
            text=text,
            provider=provider,
            mode=mode,
            operator=operator,
            logical_workspace=logical_workspace,
        )
        if not operator and provider in {"codex", "ollama", "api", "claude"}:
            result["manifest"]["recall"] = "read_only_current_projection_recomputed_at_send"
            result["notes"][1] = (
                "Core Observer, read-only memory retrieval and correction context are included in the current local instruction projection. "
                "Send recomputes them and may differ if local state changes."
            )
            result["notes"][3] = (
                "Exact Proto-Mind-authored instruction layers are shown separately. Provider-owned system instructions and private reasoning are unavailable and are not reconstructed."
            )
        result["draft_empty"] = not text
        if not operator and provider == "codex" and params.get("auto_skills") is True and not params.get("skill_task"):
            auto = AutoSkills(self.root, conversation=str(UUID(params.get("conversation_id", ""))),
                              workspace=logical_workspace, text=text, mode=mode)
            result["auto_skills"] = auto.report
            result["notes"].append("Automatic skills: on Send a separate tool-free Codex turn receives your task, up to four recent messages and a bounded shared-skill catalog. Only selected procedures reach the main turn. No selection or cloud call is performed by this preview.")
        image_specs = params.get("images", [])
        rows, images = self.image_reader().context_rows(image_specs, operator=operator)
        result["image_sources"] = rows
        result["manifest"]["images"] = images
        result["manifest"]["image_limits"] = {"count": MAX_IMAGES, "bytes_each": MAX_IMAGE_BYTES, "bytes_total": MAX_TOTAL_IMAGE_BYTES}
        result["excluded_image_count"] = len(image_specs) if operator else 0
        result["image_provider_ready"] = operator or not image_specs or provider in {"codex", "claude"}
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
        project_notes = [] if operator else self._selected_project_notes(params, str(UUID(params.get("conversation_id", "")))) if params.get("project_memory") else []
        project_recall = None
        skill_task = None
        if not operator and provider in {"codex", "claude"} and params.get("auto_project_recall") is True and not project_notes:
            project_recall = ProjectRecall(self.root, self.state_dir, conversation=str(UUID(params.get("conversation_id", ""))),
                                           workspace=logical_workspace, text=text, mode=mode, algorithm=recall_algorithm)
            project_notes = project_recall.notes
            result["notes"].append("Automatic project recall: exact current project, up to three notes / 6000 characters; informative content-word matching only, no model call or write. Manually selected notes override automatic selection. Only Send transmits the selected content.")
        if project_notes:
            result["project_memory_sources"] = project_notes
            result["notes"].append("Current project notes are operator assertions, not independently verified facts. Legacy core recall remains shared; provider history may retain previously sent context.")
        if params.get("skill_task") is not None and not operator:
            skill_task = self._selected_skill_task(params, str(UUID(params.get("conversation_id", ""))), text=text, criteria=validate_criteria(params.get("criteria", [])))
            result["skill_task_source"] = skill_task
            result["skill_task_hash_material"] = encoded({key: value for key, value in skill_task.items() if key != "preview_fingerprint"}).decode()
            result["notes"].append("The chosen procedure is non-executable reference guidance for the ordinary manually sent task. Preconditions and outcome criteria still require verification; this preview grants no tool authority.")
        knowledge = knowledge_metadata(project_notes, skill_task, recall=project_recall.report if project_recall else None)
        if knowledge is not None:
            result["manifest"]["knowledge_context"] = knowledge
        if provider_thread:
            result["provider_thread"] = provider_thread
            if provider == "claude":
                if provider_thread["linked"]:
                    result["notes"].append("Claude will resume its exact saved session, including its provider and tool history. Local chat history is not sent again and does not reproduce that session in this preview.")
                else:
                    result["notes"].append("Claude will start a new saved session using the local history shown here. An incomplete or mismatched session is never automatically replayed.")
                if provider_thread.get("bootstrap_partial"):
                    result["notes"].append("Earlier local messages exceed the bootstrap budget and are explicitly marked as omitted. This limit applies only when starting a new Claude session.")
            elif not provider_thread["workspace_matches"]:
                result["notes"].append("The saved Codex binding belongs to another workspace. Send is blocked until the operator starts a new Codex session; no automatic contract refresh will rebind it.")
            elif provider_thread["linked"]:
                result["notes"].append("Codex will resume its durable provider thread. Bounded local chat history is not sent again; provider-side history is not reproduced in this local preview.")
            elif provider_thread.get("refresh_required"):
                result["notes"].append("The selected mode has an older static instruction contract. Send will create one fresh durable thread, bootstrap it with the bounded local history shown here and preserve the old provider rollout as history.")
            else:
                result["notes"].append("This will create a durable Codex thread and bootstrap it once with the bounded local chat history shown here.")
            if provider == "codex" and not provider_thread["workspace_matches"]:
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

    def _skill_task_preview(self, params: dict) -> dict:
        request = parse_task_request(params)
        workspace = workspace_identity(self.workspace(params).root)
        return NativeSkillTask(self.root, request, workspace=workspace, is_operator=lambda text: describe_input(text)["operator"]).preview()

    def _selected_skill_task(self, params: dict, conversation: str, *, text: str, criteria: list[str]) -> dict | None:
        selected = params.get("skill_task")
        if selected is None:
            return None
        if not isinstance(selected, dict) or set(selected) != SKILL_TASK_SELECT_FIELDS:
            raise ValueError("Only the exact prepared skill-task reference may be attached.")
        request = parse_task_request({"conversation_id": conversation, "workspace_root": params.get("workspace_root"),
                                      "provider": params.get("provider", "mock"), "access_mode": params.get("access_mode", "chat"),
                                      **{key: selected[key] for key in ("skill_id", "goal", "criteria")}})
        workspace = workspace_identity(self.workspace(params).root)
        return NativeSkillTask(self.root, request, workspace=workspace, is_operator=lambda goal: describe_input(goal)["operator"]).selected(selected, text=text, criteria=criteria)

    def _project_memory(self, params: dict, conversation: str) -> NativeProjectMemory:
        if not params.get("workspace_root"):
            raise ValueError("Select the project folder before using its explicit notes.")
        workspace = workspace_identity(self.workspace(params).root)
        return NativeProjectMemory(self.root, self.state_dir, conversation, workspace)

    def _selected_project_notes(self, params: dict, conversation: str) -> list[dict]:
        specs = params.get("project_memory", [])
        if specs == []:
            return []
        return self._project_memory(params, conversation).selected(specs)

    def project_memory(self, method: str, params: dict) -> dict:
        request = parse_project_memory_request(method, params)
        if self.closing.is_set() or not self.busy.acquire(blocking=False):
            raise ValueError("Wait for the active turn before reviewing project memory.")
        try:
            memory = self._project_memory(params, request["conversation_id"])
            if method == "project_memory_list":
                return memory.listing(include_history=params.get("include_history", False), offset=params.get("offset", 0))
            if method == "project_memory_recall":
                return memory.listing(query=params["query"], include_history=params.get("include_history", False))
            if method == "project_memory_inspect":
                return memory.inspect(params.get("record_id"))
            if method == "project_memory_preview":
                return memory.preview(params.get("note"))
            if method == "project_memory_state_preview":
                return memory.preview_state(params)
            if method == "project_memory_state_save":
                return memory.save_state(params)
            return memory.save(params)
        finally:
            self.busy.release()

    def memory_suggestion(self, method: str, params: dict) -> dict:
        parse_memory_suggestion_request(method, params)
        if self.closing.is_set() or not self.busy.acquire(blocking=False):
            raise ValueError("Wait for the active turn before reviewing a memory suggestion.")
        try:
            workspace = workspace_identity(self.workspace(params).root)
            review = NativeMemorySuggestion(self.root, self.state_dir, workspace, params)
            return review.preview() if method == "memory_suggestion_preview" else review.save()
        finally:
            self.busy.release()

    def skill_history(self, method: str, params: dict) -> dict:
        parsed = parse_history_request(method, params)
        if self.closing.is_set() or not self.busy.acquire(blocking=False):
            raise ValueError("Wait for the active turn before saving or inspecting learning history.")
        try:
            workspace = workspace_identity(self.workspace(params).root) if params.get("workspace_root") else None
            history = NativeLearningHistory(self.root, self.state_dir, self.sessions.get(parsed["conversation_id"]), parsed, workspace=workspace)
            if method == "skill_history_list":
                return history.listing()
            if method == "skill_history_preview":
                return history.preview()
            if method == "skill_history_inspect":
                return history.inspect(params.get("record_id"))
            return history.save(params)
        finally:
            self.busy.release()

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
        if self.closing.is_set() and method in {"workspace_mcp", "workspace_worktree", "document_create"}:
            raise ValueError("Native disconnected. No queued operation was started.")
        if method in PRIVATE_BACKUP_METHODS:
            if self.closing.is_set() or not self.busy.acquire(blocking=False):
                raise ValueError("Дождитесь завершения текущей работы перед операциями с копиями.")
            try:
                if method in {"private_backup_restore", "private_backup_resume", "private_backup_rollback"}:
                    self.agent_grants.revoke()
                result = self.private_backup.dispatch(method, params)
                if result.get("completed"):
                    self.sessions.clear()
                    self._private_restart_required = True
                return result
            finally: self.busy.release()
        require_available(self.state_dir)
        require_available(self.root / "proto_mind/data")
        if self._private_restart_required or self._private_generation != (generation(self.root / "proto_mind/data"), generation(self.state_dir)):
            raise ValueError("Данные восстановлены. Перезапустите Proto-Mind перед продолжением.")
        if method in GITHUB_METHODS:
            if self.closing.is_set() or not self.busy.acquire(blocking=False):
                raise ValueError("Дождитесь завершения текущей задачи перед работой с подключениями.")
            try:
                return self.github.dispatch(method, params)
            finally:
                self.busy.release()
        if method == "starter_skills":
            if params or self.closing.is_set():
                raise ValueError("Starter skills inspection accepts no paths, inputs or actions.")
            return StarterSkills().snapshot()
        if method == "skill_task_preview":
            if self.closing.is_set() or not self.busy.acquire(blocking=False):
                raise ValueError("Wait for the current turn before preparing a skill task.")
            try:
                return self._skill_task_preview(params)
            finally:
                self.busy.release()
        if method in PROJECT_MEMORY_METHODS:
            return self.project_memory(method, params)
        if method in MEMORY_SUGGESTION_METHODS:
            return self.memory_suggestion(method, params)
        if method in {"skill_history_list", "skill_history_preview", "skill_history_save", "skill_history_inspect"}:
            return self.skill_history(method, params)
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
        if method in HISTORY_METHODS:
            return dispatch_history(self, method, params)
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
        if method == "pdf_render_page":
            return self.pdf_reader().render_page(params.get("path"), params.get("page"), params.get("expected_sha256"))
        if method == "workspace_mcp":
            return self.mcp_session.perform(params)
        if method in {"document_environment", "document_read", "document_create"}:
            from proto_mind import native_documents
            if method == "document_environment": return native_documents.environment()
            reader = self.workspace(params)
            if method == "document_read": return native_documents.inspect(reader, params.get("path"))
            return native_documents.create(reader, params.get("path"), params.get("content"))
        if method == "workspace_worktree":
            from proto_mind.native_worktrees import create
            import hashlib
            namespace = hashlib.sha256(str(self.state_dir.resolve()).encode()).hexdigest()[:16]
            destination = self.state_dir.resolve().parent / "ProtoMindWorktrees" / namespace
            return create(self.workspace(params), destination)
        if method == "account_status":
            return self.subscription.account()
        if method == "steer":
            steering = self.active_steering
            if steering is None or self.closing.is_set():
                raise ValueError("Задача уже завершилась. Уточнение не отправлено.")
            return steering.send(params)
        if method in {"account_limits", "account_usage"}:
            if params or self.closing.is_set() or not self._limits_read_lock.acquire(blocking=False):
                raise ValueError("Обновление лимитов сейчас недоступно.")
            try:
                # A separate account-only connection cannot interrupt or wait on
                # the live turn's RPC client. Only the full sheet inspects the
                # reset journal; neither read can consume a credit.
                reader = self._subscription_factory(self.subscription_state)
                try:
                    store = CodexResetStore(self.state_dir) if method == "account_usage" else None
                    return read_usage(reader, store, include_activity=method == "account_usage")
                finally: reader.close()
            finally: self._limits_read_lock.release()
        if method == "account_reset":
            if self.closing.is_set() or not self.busy.acquire(blocking=False):
                raise ValueError("Дождитесь завершения текущей работы перед обновлением лимитов.")
            try:
                store = CodexResetStore(self.state_dir)
                return consume_reset(self.subscription, store, params)
            finally: self.busy.release()
        if method in {"account_login", "account_logout", "account_login_cancel"}:
            if self.closing.is_set() or not self.busy.acquire(blocking=False):
                raise ValueError("Дождитесь завершения текущей работы перед сменой аккаунта.")
            try:
                if method == "account_login": return self.subscription.login()
                if method == "account_login_cancel": return self.subscription.cancel_login()
                self.agent_grants.revoke()
                return self.subscription.logout()
            finally: self.busy.release()
        if method == "codex_thread_status":
            conversation = str(UUID(str(params.get("conversation_id", ""))))
            workspace = workspace_identity(self.workspace(params).root) if params.get("workspace_root") else None
            return self.subscription.thread_status(conversation, workspace, **({"workspace_tools": True} if params.get("workspace_tools_version") == 1 else {}))
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
            workspace = self.agent_workspace(params)
            return self.agent_grants.enable(conversation, workspace, params.get("confirmation"))
        if method == "models":
            return {"models": self.subscription.models()}
        if method == "claude_status":
            return claude_status(self.state_dir)
        if method == "claude_metadata":
            return self.claude_metadata.read()
        if method == "claude_auth_command":
            if self.closing.is_set(): raise ValueError("Native disconnected.")
            return claude_auth_command(self.state_dir, params.get("operation"))
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
        if self.workspace_tools is not None: self.workspace_tools.cancel()
        if self.active_provider == "api" and self.active_api:
            self.active_api.cancel()
            return {"cancel_requested": True, "notice": "Остановка API запрошена."}
        if self.active_provider == "claude" and self.active_claude:
            self.active_claude.cancel()
            return {"cancel_requested": True, "notice": "Claude stop requested."}
        if self.active_provider != "codex":
            return {"cancel_requested": False, "notice": "This operation must finish safely; no process was killed."}
        if self.active_steering is not None: self.active_steering.stop()
        self.subscription.interrupt()
        return {"cancel_requested": True, "notice": "Codex stop requested."}

    def close(self) -> None:
        self.closing.set()
        self.mcp_session.close()
        self.claude_metadata.close()
        if self.active_claude: self.active_claude.cancel()
        if self.active_api: self.active_api.cancel()
        self.agent_grants.revoke()
        self.subscription.close()

    def disconnect(self) -> None:
        self.claude_metadata.close()
        if self.active_claude: self.active_claude.cancel()
        self.closing.set()
        self.mcp_session.close()
        if self.workspace_tools is not None: self.workspace_tools.cancel()
        if self.active_api: self.active_api.cancel()
        if self.active_steering is not None: self.active_steering.stop()
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
            # stdout redirection is process-wide. The account-only reader has
            # no console output and must not nest a redirect from another thread.
            with (nullcontext() if message["method"] in {"account_limits", "account_usage", "claude_metadata", "steer"} | ATTACHMENT_READ_METHODS else redirect_stdout(sys.stderr)):
                result = backend.dispatch(message["method"], message.get("params", {}), emit, request_id)
            emit({"id": request_id, "result": result})
        except Exception as exc:
            # Never copy protocol payloads, prompts, credentials, or tracebacks into the UI.
            safe = str(exc) if isinstance(exc, (ValueError, RuntimeError)) else "Native bridge operation failed. No automatic retry."
            emit({"id": request_id, "error": {"message": safe[:600]}})

    with (ThreadPoolExecutor(max_workers=1, thread_name_prefix="proto-native") as executor,
          ThreadPoolExecutor(max_workers=1, thread_name_prefix="proto-limits") as limits_executor,
          ThreadPoolExecutor(max_workers=1, thread_name_prefix="proto-claude-metadata") as claude_executor,
          ThreadPoolExecutor(max_workers=1, thread_name_prefix="proto-steer") as steering_executor,
          ThreadPoolExecutor(max_workers=1, thread_name_prefix="proto-attachments") as attachment_executor):
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
                if message["method"] == "workspace_tool_result":
                    if backend.workspace_tools is None:
                        raise ValueError("No active workspace tool channel.")
                    result = backend.workspace_tools.resolve(message.get("params", {}))
                    emit({"id": request_id, "result": result})
                elif message["method"] == "cancel":
                    emit({"id": request_id, "result": backend.cancel(str(message.get("params", {}).get("request_id", "")))})
                else:
                    target = (attachment_executor if message["method"] in ATTACHMENT_READ_METHODS else
                              {"account_limits": limits_executor, "account_usage": limits_executor, "claude_metadata": claude_executor, "steer": steering_executor}.get(message["method"], executor))
                    target.submit(run, message)
            except (ValueError, TypeError) as exc:
                emit({"id": request_id, "error": {"message": str(exc)[:200]}})
    backend.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Proto-Mind native stdio bridge")
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--code-root", type=Path, help="Read-only installed source, separate from writable project data")
    parser.add_argument("--pdf-helper", type=Path)
    parser.add_argument("--codex-account", help="Private account UUID; omitted for the existing default login")
    args = parser.parse_args()
    if not ((args.code_root or args.project_root) / "proto_mind" / "main.py").is_file():
        parser.error("Project root does not contain Proto-Mind.")
    backend = NativeBackend(args.project_root, args.state_dir, pdf_helper=args.pdf_helper, codex_account=args.codex_account)
    serve(backend, sys.stdin, sys.stdout)


if __name__ == "__main__":
    main()
