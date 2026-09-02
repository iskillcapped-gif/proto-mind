"""Operator-prepared use of a verified procedure as guidance, never a skill interpreter."""
from copy import deepcopy
from pathlib import Path
from proto_mind.native_private_records import digest, encoded, HASH
from proto_mind.native_review import validate_criteria, criteria_contract
from proto_mind.native_skill_inspection import parse_skill_inspection_request
from proto_mind.native_skill_outcome import NativeSkillOutcome
from proto_mind.native_work_sessions import workspace_identity


PREVIEW_SCHEMA = "proto_mind.native_skill_task_preview.v1"
TASK_SCHEMA = "proto_mind.native_skill_task.v1"
SELECT_FIELDS = {"skill_id", "goal", "criteria", "preview_fingerprint"}


def parse_task_request(params: dict) -> dict:
    fields = {"conversation_id", "workspace_root", "skill_id", "expected_sha256", "goal", "criteria", "provider", "access_mode"}
    if not isinstance(params, dict) or set(params) - fields:
        raise ValueError("Skill task preparation accepts a fixed operator goal and criteria, not commands or grants.")
    scope = parse_skill_inspection_request({key: value for key, value in params.items() if key in {"conversation_id", "workspace_root", "skill_id", "expected_sha256"}})
    if not scope["conversation_id"] or not params.get("workspace_root"):
        raise ValueError("Select the exact conversation and project folder for this task.")
    goal = params.get("goal", "")
    if (not isinstance(goal, str) or len(goal) > 4000 or goal != goal.strip()
            or any((ord(char) < 32 and char not in "\n\t") or 0xD800 <= ord(char) <= 0xDFFF for char in goal)):
        raise ValueError("The task goal must be plain text of at most 4000 characters.")
    provider, mode = params.get("provider", "mock"), params.get("access_mode", "chat")
    if provider not in {"codex", "ollama", "mock"} or mode not in {"chat", "full_access"} or mode == "full_access" and provider != "codex":
        raise ValueError("Skill guidance cannot change the existing provider/access boundaries.")
    return {**scope, "goal": goal, "criteria": validate_criteria(params.get("criteria", [])), "provider": provider, "access_mode": mode}


class NativeSkillTask:
    def __init__(self, root: Path, request: dict, *, workspace: dict, is_operator):
        self.root, self.request, self.workspace, self.is_operator = root, request, workspace, is_operator

    def preview(self) -> dict:
        request = self.request
        reasons, warnings, body = [], [], None
        source = NativeSkillOutcome(self.root, None, request, workspace=self.workspace)
        try:
            if source.issues or source.builder is None:
                raise ValueError("Source stores cannot be verified: " + "; ".join(source.issues))
            if not source.context_disabled:
                raise ValueError("Context Injection must stay disabled for reviewed skill tasks.")
            if request["expected_sha256"] and request["expected_sha256"] != source.hashes["skills.jsonl"]:
                raise ValueError("The skill library changed since selection. Refresh and review the current record.")
            record = next((row for row in source.builder.skill_library.read_snapshot()["records"] if row["id"] == request["skill_id"]), None)
            if record is None:
                raise ValueError("Selected skill no longer exists. No substitute was chosen.")
            contract, lifecycle = source.verified_guidance(record)
            provenance = record["provenance"]
            body = {"schema": TASK_SCHEMA, "conversation_id": request["conversation_id"], "project_root": str(self.root),
                    "workspace": self.workspace, "skill_id": record["id"], "skill_name": record["name"],
                    "skill_record_hash": digest(record), "source_lesson_id": provenance["source_lesson_id"],
                    "provenance_id": provenance["id"], "provenance_hash": provenance["provenance_hash"],
                    "lifecycle_state": lifecycle.state, "store_hashes": deepcopy(source.hashes),
                    "contract": contract, "contract_hash": digest(contract), "goal": request["goal"],
                    "success_criteria": criteria_contract(request["criteria"]), "provider": request["provider"], "access_mode": request["access_mode"],
                    "execution_path": "existing_operator_sent_provider_turn", "skill_interpreter_installed": False,
                    "permission_granted": False, "automatic_execution": False, "automatic_learning": False,
                    "quality_verification": "not_assessed", "shared_skill_library": True}
            warnings.extend(lifecycle.warnings)
            source._check_sources()
            if workspace_identity(Path(self.workspace["path"])) != self.workspace:
                raise ValueError("Workspace identity changed while preparing the task.")
        except (OSError, ValueError, TypeError, KeyError, RuntimeError) as exc:
            reasons.append(str(exc)); body = None
        if not request["goal"]:
            reasons.append("Enter the operator goal before preparing a task.")
        elif self.is_operator(request["goal"]):
            reasons.append("Slash, natural command and exit routes cannot be wrapped as skill tasks.")
        if not request["criteria"]:
            reasons.append("Declare at least one observable success criterion before Send.")
        warnings.append("Provenance is verified, not effectiveness. Check preconditions, observe actual results and review each criterion before acceptance.")
        warnings.append("This is guidance for an ordinary operator-sent task, not an interpreter, permission, autonomous execution or automatic learning.")
        if request["access_mode"] == "chat":
            warnings.append("Chat has no tools: explanation/planning only. Full Mac requires the separate existing explicit grant.")
        if request["provider"] == "mock":
            warnings.append("Mock is a deterministic UI fixture, not a skill-understanding or task-execution model.")
        ready = body is not None and not reasons
        return {"schema": PREVIEW_SCHEMA, "conversation_id": request["conversation_id"], "workspace": self.workspace,
                "skill_id": request["skill_id"], "status": "READY" if ready else "NOT_READY", "reasons": reasons, "warnings": warnings,
                "body": body, "hash_material": encoded(body).decode() if body else "",
                "preview_fingerprint": digest(body) if ready else "", "read_only": True, "no_execution": True,
                "permission_granted": False, "store_mutation_performed": False, "model_call_performed": False}

    def selected(self, selection: dict, *, text: str, criteria: list[str]) -> dict:
        if (not isinstance(selection, dict) or set(selection) != SELECT_FIELDS
                or not isinstance(selection.get("preview_fingerprint"), str) or not HASH.fullmatch(selection["preview_fingerprint"])):
            raise ValueError("An exact reviewed skill-task selection is required.")
        if selection["goal"] != text or selection["criteria"] != criteria:
            raise ValueError("Task goal or success criteria changed. Review the skill task again or detach it; no fallback execution.")
        preview = self.preview()
        if preview["status"] != "READY" or preview["preview_fingerprint"] != selection["preview_fingerprint"]:
            raise ValueError("Skill task is stale or no longer eligible. " + "; ".join(preview["reasons"] or ["source, workspace or selected mode changed"]))
        return {**preview["body"], "preview_fingerprint": preview["preview_fingerprint"]}
