"""Read-only Native projection of the existing supervised learning pilot.

This module owns no capture, decision, proposal, or persistence state. It only
projects an already-created process-memory pilot for operator inspection.
"""
from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
from typing import Any, Mapping

from proto_mind.experience_learning_bridge import (
    CognitiveLearningBridgeError,
    OperatorReviewedLearningBridge,
)
from proto_mind.experience_pilot import peek_experience_pilot


NATIVE_MEMORY_WORKSHOP_SCHEMA = "proto_mind.native_memory_workshop.v1"
MAX_WORKSHOP_CANDIDATES = 64


def _canonical_hash(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def build_native_memory_workshop(
    owner: object | None,
    *,
    conversation_id: str,
    workspace: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Project current process-only candidates without creating pilot state."""
    pilot = peek_experience_pilot(owner) if owner is not None else None
    events = pilot.snapshot() if pilot is not None else ()
    bridge = OperatorReviewedLearningBridge(events)
    doctor = bridge.doctor()
    warnings = list(doctor.warnings)
    issues = list(doctor.issues)
    try:
        reviews = bridge.review()
    except CognitiveLearningBridgeError as exc:
        reviews = []
        if str(exc) not in issues:
            issues.append(str(exc))

    candidates: list[dict[str, Any]] = []
    for review in reviews:
        for candidate in review.candidates:
            if len(candidates) >= MAX_WORKSHOP_CANDIDATES:
                break
            decision = pilot.learning_decisions.get(candidate.id) if pilot is not None else None
            candidates.append(
                {
                    **candidate.to_dict(),
                    "episode_status": review.episode_status,
                    "created_at": review.created_at,
                    "decision": decision.decision if decision is not None else "undecided",
                    "review_command": f"/experience learning decision {candidate.id}",
                    "preview_command": f"/experience learning preview {candidate.turn_id}",
                }
            )
    total_candidates = sum(len(review.candidates) for review in reviews)
    omitted_candidates = max(0, total_candidates - len(candidates))
    if omitted_candidates:
        warnings.append(
            f"{omitted_candidates} candidates are omitted from this bounded Native view."
        )

    workspace_value = dict(workspace) if workspace is not None else None
    scope = {
        "workspace_selected": workspace_value is not None,
        "workspace_path": str(workspace_value.get("path") or "") if workspace_value else "",
        "workspace_identity_hash": _canonical_hash(workspace_value) if workspace_value else "",
        "memory_store_scope": "global_legacy_stores",
        "project_isolation_enforced": False,
        "explanation": (
            "The selected workspace identifies the current work context, but existing memory stores "
            "are global legacy stores. This view does not claim project isolation."
        ),
    }
    if workspace_value is not None:
        warnings.append(
            "Workspace context is selected, but persistent/working memory is not yet isolated per project."
        )

    pilot_state = pilot.state if pilot is not None else "not_started"
    status = "ERROR" if issues else "REVIEW" if candidates else "EMPTY"
    return {
        "schema": NATIVE_MEMORY_WORKSHOP_SCHEMA,
        "read_only": True,
        "conversation_id": conversation_id,
        "status": status,
        "pilot_present": pilot is not None,
        "pilot_state": pilot_state,
        "process_memory_only": True,
        "captured_turns": pilot.captured_turns if pilot is not None else 0,
        "event_count": pilot.event_count if pilot is not None else 0,
        "episode_count": len(reviews),
        "candidate_count": total_candidates,
        "omitted_candidate_count": omitted_candidates,
        "candidates": candidates,
        "doctor": asdict(doctor),
        "scope": scope,
        "warnings": warnings,
        "issues": issues,
        "commands": {
            "start_preview": "/experience preview",
            "status": "/experience status",
            "episodes": "/experience episodes",
            "learning_status": "/experience learning status",
            "learning_doctor": "/experience learning doctor",
        },
        "operator_review_required": True,
        "automatic_promotion": False,
        "command_execution_performed": False,
        "consent_state_changed": False,
        "retrieval_performed": False,
        "model_call_performed": False,
        "network_call_performed": False,
        "store_mutation_performed": False,
        "notice": (
            "This workshop only projects existing bounded process-memory evidence. "
            "Buttons may prepare an operator command in the composer; they never run it."
        ),
    }
