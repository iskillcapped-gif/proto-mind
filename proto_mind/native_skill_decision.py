"""Exact Native choices over existing manual outcomes; no lifecycle apply path."""
from __future__ import annotations

import json
from pathlib import Path

from proto_mind.experience_learning_skill_outcome_decision import (
    PROCEDURAL_SKILL_OUTCOME_DECISION_MAX_RECEIPTS,
    PROCEDURAL_SKILL_OUTCOME_DECISIONS,
    ProceduralSkillOutcomeDecisionBuilder,
    ProceduralSkillOutcomeDecisionError,
    procedural_skill_outcome_decision_confirmation_token,
)
from proto_mind.native_skill_authoring import _hash
from proto_mind.native_skill_inspection import _findings, parse_skill_inspection_request
from proto_mind.native_skill_outcome import NativeSkillOutcome, _boundary


METHODS = frozenset({"skill_decision_review", "skill_decision_preview", "skill_decision_confirm"})
CHOICES = ("keep", "revise", "archive")


def parse_skill_decision_request(params: dict, *, method: str) -> dict:
    fields = {"conversation_id", "skill_id", "workspace_root", "expected_sha256"}
    allowed = fields.copy()
    if method != "skill_decision_review":
        allowed.add("decision")
    if method == "skill_decision_confirm":
        allowed.update({"preview_fingerprint", "confirmation_token", "acknowledge_decision_only"})
    if method not in METHODS or set(params) - allowed:
        raise ValueError("Only a fixed skill decision is supported; no apply, command or revision payload.")
    result = parse_skill_inspection_request({key: value for key, value in params.items() if key in fields})
    if not result["conversation_id"]:
        raise ValueError("Select a conversation to review its skill decisions.")
    if method != "skill_decision_review":
        decision = params.get("decision")
        if not isinstance(decision, str) or decision not in PROCEDURAL_SKILL_OUTCOME_DECISIONS:
            raise ValueError("Choose exactly keep, revise or archive; no action is executed.")
        result["decision"] = decision
    return result


class NativeSkillDecision:
    def __init__(self, root: Path, owner: object | None, request: dict, *, workspace: dict | None) -> None:
        self.request = request
        self.source = NativeSkillOutcome(root, owner, request, workspace=workspace)
        self.pilot = self.source.pilot
        self.pilot_state = self.pilot.state if self.pilot else "not_started"
        self.decisions = self.pilot.skill_outcome_decisions.snapshot() if self.pilot else ()
        self.issues = list(self.source.issues)
        self.builder = None
        self.outcome = None
        self.audit = None
        self.blueprints = {}
        self.choice_reasons = {}
        try:
            if len(self.decisions) > PROCEDURAL_SKILL_OUTCOME_DECISION_MAX_RECEIPTS or len(
                json.dumps(self.decisions, allow_nan=False)
            ) > 512_000:
                raise ValueError("Decision receipts exceed the bounded process review limit.")
            if self.source.builder is not None and self.pilot is not None:
                self.builder = ProceduralSkillOutcomeDecisionBuilder(
                    events=self.source.events, memory_store=self.source.builder.memory_store,
                    skill_library=self.source.builder.skill_library, capture_session=self.pilot.skill_outcome_captures,
                )
                self.outcome = self.builder.review(request["skill_id"])
                for decision in CHOICES:
                    try:
                        self.blueprints[decision] = self.builder.build(request["skill_id"], decision)
                    except ProceduralSkillOutcomeDecisionError as exc:
                        self.choice_reasons[decision] = str(exc)
                self.audit = self.pilot.skill_outcome_decisions.doctor(self.builder)
                self.issues.extend(self.audit.issues)
            self._check_current()
        except (OSError, ValueError, TypeError, KeyError, AttributeError, RecursionError,
                OverflowError, ProceduralSkillOutcomeDecisionError) as exc:
            self.issues.append(f"Decision evidence cannot be safely reviewed: {type(exc).__name__}: {exc}")
            self.blueprints = {}

    def _check_current(self) -> None:
        self.source._check_sources()
        if self.pilot is not None and (
            self.pilot.state != self.pilot_state or self.pilot.snapshot() != self.source.events
            or self.pilot.skill_outcome_captures.snapshot() != self.source.receipts
            or self.pilot.skill_outcome_decisions.snapshot() != self.decisions
        ):
            raise ValueError("Process evidence or consent state changed. Review again; no decision recorded.")

    def _existing(self) -> dict | None:
        return next((row for row in self.decisions if row.get("skill_id") == self.request["skill_id"]), None)

    def _reasons(self) -> list[str]:
        reasons = list(self.issues)
        if not self.source.eligible:
            reasons.append(self.source.source_reason)
        if not self.source.context_disabled:
            reasons.append("Context Injection must be explicitly disabled in readable settings; no automatic change.")
        if self.pilot is None:
            reasons.append("No current-conversation Experience evidence. Record an explicit manual outcome first.")
        if self._existing() is not None:
            reasons.append("This skill already has a terminal decision in this conversation's current process. Inspect its receipt; no replay or replacement.")
        if len(self.decisions) >= PROCEDURAL_SKILL_OUTCOME_DECISION_MAX_RECEIPTS:
            reasons.append("The 16-decision process limit is reached.")
        return reasons

    def _base(self, kind: str, *, read_only: bool = True) -> dict:
        return {"schema": f"proto_mind.native_skill_decision_{kind}.v1", **self.source._identity(),
                **_boundary(read_only=read_only), "experience_mutation_performed": False,
                "lifecycle_apply_performed": False, "future_apply_ready": False}

    def _receipt(self, raw: dict) -> dict:
        current = self.blueprints.get(raw.get("decision"))
        audit = self.pilot.skill_outcome_decisions.doctor(self.builder) if self.builder is not None else None
        verified = audit is not None and not audit.issues
        return {**raw, "verification_status": "VERIFIED" if verified else "ERROR" if audit else "UNAVAILABLE",
                "evidence_state": "CURRENT" if verified and current and current.decision_hash == raw.get("decision_hash") else
                "HISTORICAL" if verified else "UNAVAILABLE"}

    def report(self) -> dict:
        reasons = self._reasons()
        existing = self._existing()
        choices = [{"decision": decision, "allowed": not reasons and decision in self.blueprints,
                    "reasons": _findings(reasons or ([self.choice_reasons.get(decision, "No exact confirmed manual evidence.")]
                                                     if decision not in self.blueprints else []))} for decision in CHOICES]
        available = any(choice["allowed"] for choice in choices)
        if not reasons and not available:
            reasons.append("No outcome is eligible for a decision backed by exact confirmed capture receipts.")
        return {**self._base("review"), "status": "ERROR" if self.issues else "RECORDED" if existing else "READY" if available else "NOT_READY",
                "name": self.source.name, "source_eligible": self.source.eligible,
                "context_injection_disabled": self.source.context_disabled, "pilot_state": self.pilot_state,
                "session_id": self.pilot.session_id if self.pilot else "",
                "event_count": len(self.source.events), "capture_receipt_count": len(self.source.receipts),
                "decision_count": len(self.decisions), "decision_limit": PROCEDURAL_SKILL_OUTCOME_DECISION_MAX_RECEIPTS,
                "outcome_status": self.outcome.status if self.outcome else "UNAVAILABLE",
                "manual_use_count": self.outcome.matching_manual_use_count if self.outcome else 0,
                "signal_count": len(self.outcome.signals) if self.outcome else 0,
                "choices": choices, "receipt": self._receipt(existing) if existing else None,
                "store_hashes": self.source.hashes,
                "changed_since_selection": bool(self.request["expected_sha256"] and
                                                self.request["expected_sha256"] != self.source.hashes.get("skills.jsonl")),
                "skill_store_scope": "global_legacy_stores", "project_isolation_enforced": False,
                "reasons": _findings(reasons), "issues": _findings(self.issues),
                "warnings": _findings((self.outcome.warnings if self.outcome else []) +
                                      (self.audit.warnings if self.audit and self.decisions else []))}

    def preview(self) -> dict:
        decision = self.request["decision"]
        reasons = self._reasons()
        blueprint = self.blueprints.get(decision)
        if blueprint is None:
            reasons.append(self.choice_reasons.get(decision, "No exact confirmed manual evidence supports this decision."))
        if not reasons:
            try:
                self._check_current()
            except (OSError, ValueError) as exc:
                reasons.append(str(exc))
        material = {"request": self.request, "workspace": self.source.workspace, "store_hashes": self.source.hashes,
                    "session_id": self.pilot.session_id if self.pilot else "", "pilot_state": self.pilot_state,
                    "events": self.source.events, "captures": self.source.receipts, "decisions": self.decisions,
                    "blueprint": blueprint.to_dict() if blueprint else None, "reasons": reasons}
        return {**self._base("preview"), "ready": not reasons, "decision": decision,
                "preview_fingerprint": _hash(material), "reasons": _findings(reasons),
                "confirmation_token": procedural_skill_outcome_decision_confirmation_token(blueprint) if not reasons else "",
                "blueprint": blueprint.to_dict() if blueprint and not reasons else None,
                "future_mutation": "process_memory_one_terminal_decision_receipt",
                "requires_decision_only_acknowledgement": True, "store_hashes": self.source.hashes}

    def confirm(self, params: dict) -> dict:
        preview = self.preview()
        if not preview["ready"]:
            raise ValueError("Skill decision refused: " + "; ".join(preview["reasons"]))
        if params.get("preview_fingerprint") != preview["preview_fingerprint"]:
            raise ValueError("Decision, sources, evidence, consent state or scope changed. Preview again; no decision recorded.")
        if params.get("confirmation_token") != preview["confirmation_token"]:
            raise ValueError("Exact skill-decision token mismatch. No decision recorded.")
        if params.get("acknowledge_decision_only") is not True:
            raise ValueError("Acknowledge a process-only decision, not lifecycle apply or execution.")
        self._check_current()
        try:
            receipt = self.pilot.skill_outcome_decisions.decide(
                self.blueprints[self.request["decision"]], token=params["confirmation_token"],
            )
        except ProceduralSkillOutcomeDecisionError as exc:
            raise ValueError(str(exc)) from exc
        return {**self._base("result", read_only=False), "mutation": "process_memory_one_terminal_decision_receipt",
                "events_appended": 0, "receipt": self._receipt(receipt.to_dict())}
