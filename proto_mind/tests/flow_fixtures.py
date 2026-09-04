"""Shared deterministic core fixtures; no test cases or discovery side effects."""
from __future__ import annotations

from copy import deepcopy
import json
import os
import shlex
import tarfile
import unittest
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from proto_mind import python_env
from proto_mind.action_policy import (
    action_policy_doctor,
    classify_command,
    classify_command_bundle,
    classify_natural_route,
    format_policy_command,
)
from proto_mind.action_preview import action_preview_doctor, build_action_preview, format_action_command
from proto_mind.action_queue import ActionProposalQueue, format_action_queue_command
from proto_mind.activation_layer import RunnerActivationPreconditions, format_activation_command
from proto_mind.acceptance_layer import AcceptanceReview, format_acceptance_command
from proto_mind.agenda_layer import OperatorAgenda, format_agenda_command
from proto_mind.backup_utils import create_project_backup, format_backup_command, is_backup_command
from proto_mind.baseline_layer import SnapshotBaselineRegistry, format_baseline_command
from proto_mind.command_registry import (
    COMMAND_REGISTRY,
    CommandSpec,
    command_registry_doctor,
    format_commands_command,
    match_registered_command,
)
from proto_mind.capability_contracts import (
    LOCAL_CAPABILITY_CONTRACTS,
    build_local_capability_result,
    get_local_capability_contract,
    local_capability_contract_doctor,
)
from proto_mind.capability_map import CommandCapabilityMap, format_capability_command
from proto_mind.closure_layer import PostAcceptanceClosure, format_closure_command
from proto_mind.confirmation_layer import ConfirmationVocabulary, format_confirmation_command
from proto_mind.config import ProtoMindConfig
from proto_mind.cognitive_benchmark import (
    CASES as COGNITIVE_BENCHMARK_CASES,
    RESPONSE_CASES as COGNITIVE_RESPONSE_BENCHMARK_CASES,
    format_benchmark_report,
    run_benchmark,
)
from proto_mind.cognitive_soak import format_continuity_soak_report, run_continuity_soak
from proto_mind.cognitive_turn_envelope import (
    COGNITIVE_TURN_SCHEMA,
    COGNITIVE_TURN_VERSION,
    ENVELOPE_UNAVAILABLE_WARNING,
    MEMORY_PREVIEW_MAX_CHARS,
    InteractiveResponse,
    build_cognitive_turn_envelope,
    project_interactive_response,
)
from proto_mind.cognitive_turn_view_model import (
    CARD_HINT_LIMIT,
    CARD_MEMORY_LIMIT,
    CARD_UNAVAILABLE_NOTICE,
    CARD_WARNING_LIMIT,
    project_cognitive_turn_card,
)
from proto_mind.consolidation import format_consolidation_command
from proto_mind.contest_provenance import (
    build_contest_provenance,
    is_submission_relevant,
)
from proto_mind.context_pack import ContextInjectionAuditLog, ContextPackBuilder, build_context_prompt_preview, format_context_command
from proto_mind.coordinator import Coordinator
from proto_mind.data_integrity import EXPORT_DIRS, format_data_command
from proto_mind.daily_layer import format_daily_command
from proto_mind.experiment_journal import ExperimentJournal, format_experiment_command
from proto_mind.experience_capture import (
    DEFAULT_CAPTURE_SETTINGS,
    LIVE_CAPTURE_HOOK_INSTALLED,
    ExperienceCaptureGate,
    format_experience_capture_doctor,
    format_experience_capture_preview,
    format_experience_capture_status,
)
from proto_mind.experience_capture_design import (
    SESSION_CAPTURE_CONSENT_MODEL,
    SESSION_CAPTURE_DESIGN_STATUS,
    SESSION_CAPTURE_FAILURE_MODE,
    SessionCaptureDesignReview,
    format_session_capture_design_benchmark,
    format_session_capture_design_checklist,
    format_session_capture_design_doctor,
    format_session_capture_design_review,
    format_session_capture_design_status,
    run_session_capture_design_benchmark,
)
from proto_mind.experience_capture_soak import (
    SOAK_MAX_BYTES,
    SOAK_MAX_EVENTS,
    SOAK_MAX_EVENTS_PER_TURN,
    SOAK_NORMAL_TURNS,
    BoundedExperiencePreviewBuffer,
    format_experience_capture_soak,
    run_experience_capture_soak,
)
from proto_mind.experience_pilot import (
    EXPERIENCE_PILOT_ATTR,
    EXPERIENCE_PILOT_MAX_BYTES,
    EXPERIENCE_PILOT_MAX_EVENTS,
    SupervisedExperiencePilot,
    format_experience_pilot_command,
    get_experience_pilot,
    peek_experience_pilot,
)
from proto_mind.experience_turn import (
    CognitiveTurnProjector,
    format_cognitive_turn_episode,
    format_cognitive_turn_list,
)
from proto_mind.experience_activation_review import (
    EXPERIENCE_ACTIVATION_DECISION,
    EXPERIENCE_NEXT_STAGE,
    ExperienceCaptureActivationReadinessReview,
    format_experience_activation_benchmark,
    format_experience_activation_doctor,
    format_experience_activation_evidence,
    format_experience_activation_status,
    run_experience_activation_benchmark,
)
from proto_mind.experience_consent import (
    CONSENT_PHRASE_PREFIX,
    SessionConsentStateMachineSpec,
    format_session_consent_benchmark,
    format_session_consent_doctor,
    format_session_consent_refusals,
    format_session_consent_status,
    format_session_consent_transitions,
    run_session_consent_benchmark,
)
from proto_mind.experience_privacy import (
    REDACTION_PREFIX,
    find_sensitive_preview_categories,
    format_experience_privacy_benchmark,
    format_experience_privacy_doctor,
    format_experience_privacy_status,
    inspect_experience_privacy,
    redact_experience_preview,
    run_experience_privacy_benchmark,
)
from proto_mind.experience_episode import (
    ExperienceEpisodeProjectionError,
    ExperienceEpisodeProjector,
    format_experience_episode,
    format_experience_episode_benchmark,
    format_experience_episode_doctor,
    format_experience_episode_list,
    run_experience_episode_benchmark,
)
from proto_mind.experience_explainability import (
    ExperienceTraceIndex,
    format_experience_event_explanation,
    format_experience_explainability_benchmark,
    format_experience_explainability_doctor,
    format_experience_trace_map,
    run_experience_explainability_benchmark,
)
from proto_mind.experience_ledger import (
    EXPERIENCE_PREVIEW_MAX_CHARS,
    EXPERIENCE_ROOT_EVENT_TYPES,
    LIVE_EXPERIENCE_LEDGER_PATH,
    LIVE_EXPERIENCE_PERSISTENCE_ENABLED,
    ExperienceEvent,
    ExperienceLedgerError,
    ExperienceTraceBuilder,
    TemporaryExperienceLedgerStore,
    compact_preview,
    format_experience_doctor,
    format_experience_persistence_policy,
    format_experience_preview,
    format_experience_store_doctor,
    inspect_experience_events,
)
from proto_mind.experience_learning import (
    ExperienceLearningReviewer,
    format_experience_learning_benchmark,
    format_experience_learning_candidate,
    format_experience_learning_doctor,
    format_experience_learning_review,
    run_experience_learning_benchmark,
)
from proto_mind.experience_learning_bridge import (
    CognitiveLearningPreviewCandidate,
    OperatorReviewedLearningBridge,
    format_learning_bridge_doctor,
    format_learning_bridge_preview,
    format_learning_bridge_status,
)
from proto_mind.experience_learning_decision import (
    LEARNING_DECISION_MAX_RECEIPTS,
    OperatorReviewedLearningDecisionSession,
    format_learning_decision_command,
    learning_confirmation_token,
)
from proto_mind.experience_learning_input import (
    LEARNING_INPUT_SELECTION_MODE,
    ExperienceLearningInputAdapter,
    ExperienceLearningInputError,
    format_experience_learning_input_benchmark,
    format_experience_learning_input_doctor,
    format_experience_learning_input_snapshot,
    run_experience_learning_input_benchmark,
)
from proto_mind.experience_learning_outcome import (
    LEARNING_OUTCOME_MODE,
    LEARNING_OUTCOME_STATUSES,
    LearningOutcomeReviewer,
    format_learning_outcome_benchmark,
    format_learning_outcome_command,
    run_learning_outcome_benchmark,
    _correction_event,
    _replacement_events,
)
from proto_mind.experience_learning_lifecycle import (
    LEARNING_LIFECYCLE_MAX_RECEIPTS,
    LEARNING_LIFECYCLE_MODE,
    OperatorReviewedLearningLifecycleSession,
    format_learning_lifecycle_benchmark,
    format_learning_lifecycle_command,
    learning_lifecycle_confirmation_token,
    run_learning_lifecycle_benchmark,
)
from proto_mind.experience_learning_lifecycle_readiness import (
    LEARNING_LIFECYCLE_APPLY_ENGINE_INSTALLED,
    LEARNING_LIFECYCLE_READINESS_MODE,
    LearningLifecycleApplyReadiness,
    format_learning_lifecycle_readiness_command,
    learning_lifecycle_transition_contract,
)
from proto_mind.experience_learning_lifecycle_apply import (
    LEARNING_LIFECYCLE_APPLY_MAX_RECEIPTS,
    LEARNING_LIFECYCLE_APPLY_MODE,
    OperatorReviewedLearningLifecycleApplySession,
    format_learning_lifecycle_apply_command,
    learning_lifecycle_apply_confirmation_token,
)
from proto_mind.experience_learning_lifecycle_audit import (
    LEARNING_LIFECYCLE_AUDIT_MODE,
    LearningLifecycleTransitionAudit,
    format_learning_lifecycle_audit_command,
)
from proto_mind.experience_learning_skill_contract import (
    PROCEDURAL_SKILL_APPLY_ENGINE_INSTALLED,
    PROCEDURAL_SKILL_CONTRACT_MODE,
    PROCEDURAL_SKILL_CONTRACT_SCHEMA,
    ProceduralSkillContractBuilder,
    format_procedural_skill_contract_command,
)
from proto_mind.experience_learning_skill_authoring import (
    PROCEDURAL_SKILL_AUTHORING_MAX_RECEIPTS,
    PROCEDURAL_SKILL_AUTHORING_MODE,
    PROCEDURAL_SKILL_EXECUTION_INSTALLED,
    PROCEDURAL_SKILL_WRITER_INSTALLED,
    OperatorReviewedProceduralSkillAuthoringSession,
    ProceduralSkillAuthoringError,
    build_procedural_skill_authoring_blueprint,
    format_procedural_skill_authoring_command,
    parse_procedural_skill_authoring_request,
    procedural_skill_authoring_confirmation_token,
)
from proto_mind.experience_learning_skill_readiness import (
    PROCEDURAL_SKILL_APPLY_ENGINE_INSTALLED,
    PROCEDURAL_SKILL_FUTURE_RECEIPT_FIELDS,
    PROCEDURAL_SKILL_READINESS_MODE,
    ProceduralSkillApplyReadiness,
    format_procedural_skill_readiness_command,
)
from proto_mind.experience_learning_skill_apply import (
    PROCEDURAL_SKILL_APPLY_MAX_RECEIPTS,
    PROCEDURAL_SKILL_APPLY_MODE,
    PROCEDURAL_SKILL_EXECUTION_ENABLED,
    OperatorReviewedProceduralSkillApplySession,
    ProceduralSkillApplyError,
    format_procedural_skill_apply_command,
    procedural_skill_apply_confirmation_token,
)
from proto_mind.experience_learning_skill_outcome import (
    PROCEDURAL_SKILL_OUTCOME_MODE,
    PROCEDURAL_SKILL_OUTCOME_STATUSES,
    ProceduralSkillOutcomeReviewer,
    format_procedural_skill_outcome_command,
)
from proto_mind.experience_learning_skill_outcome_capture import (
    PROCEDURAL_SKILL_OUTCOME_CAPTURE_MAX_RECEIPTS,
    PROCEDURAL_SKILL_OUTCOME_CAPTURE_MODE,
    OperatorReviewedProceduralSkillOutcomeCaptureSession,
    ProceduralSkillOutcomeCaptureBuilder,
    ProceduralSkillOutcomeCaptureError,
    format_procedural_skill_outcome_capture_command,
    procedural_skill_outcome_capture_confirmation_token,
)
from proto_mind.experience_learning_skill_outcome_decision import (
    PROCEDURAL_SKILL_OUTCOME_DECISION_MAX_RECEIPTS,
    PROCEDURAL_SKILL_OUTCOME_DECISION_MODE,
    OperatorReviewedProceduralSkillOutcomeDecisionSession,
    ProceduralSkillOutcomeDecisionBuilder,
    ProceduralSkillOutcomeDecisionError,
    format_procedural_skill_outcome_decision_command,
    procedural_skill_outcome_decision_confirmation_token,
)
from proto_mind.experience_learning_skill_lifecycle_readiness import (
    PROCEDURAL_SKILL_LIFECYCLE_FUTURE_RECEIPT_FIELDS,
    PROCEDURAL_SKILL_LIFECYCLE_READINESS_MODE,
    ProceduralSkillLifecycleApplyReadiness,
    format_procedural_skill_lifecycle_readiness_command,
)
from proto_mind.experience_learning_skill_lifecycle_metadata_readiness import (
    PROCEDURAL_SKILL_LIFECYCLE_CURRENT_WRITER_SUPPORTS_METADATA,
    PROCEDURAL_SKILL_LIFECYCLE_METADATA_EXPECTED_CHANGED_FIELDS,
    PROCEDURAL_SKILL_LIFECYCLE_METADATA_FUTURE_RECEIPT_FIELDS,
    PROCEDURAL_SKILL_LIFECYCLE_METADATA_READINESS_MODE,
    PROCEDURAL_SKILL_LIFECYCLE_METADATA_READINESS_WRITER_INSTALLED,
    ProceduralSkillLifecycleMetadataReadiness,
    format_procedural_skill_lifecycle_metadata_plan,
    format_procedural_skill_lifecycle_metadata_readiness,
    procedural_skill_lifecycle_metadata_readiness_doctor,
)
from proto_mind.experience_learning_skill_lifecycle_metadata_apply import (
    PROCEDURAL_SKILL_LIFECYCLE_METADATA_APPLY_MAX_RECEIPTS,
    PROCEDURAL_SKILL_LIFECYCLE_METADATA_APPLY_MODE,
    OperatorReviewedProceduralSkillLifecycleMetadataApplySession,
    ProceduralSkillLifecycleMetadataApplyError,
    format_procedural_skill_lifecycle_metadata_apply_command,
    procedural_skill_lifecycle_metadata_apply_confirmation_token,
    procedural_skill_lifecycle_metadata_apply_receipt_hash,
)
from proto_mind.experience_learning_skill_lifecycle_apply import (
    PROCEDURAL_SKILL_LIFECYCLE_APPLY_MAX_RECEIPTS,
    PROCEDURAL_SKILL_LIFECYCLE_APPLY_MODE,
    OperatorReviewedProceduralSkillLifecycleApplySession,
    ProceduralSkillLifecycleApplyError,
    format_procedural_skill_lifecycle_apply_command,
    procedural_skill_lifecycle_apply_confirmation_token,
)
from proto_mind.skill_provenance import (
    PROCEDURAL_SKILL_PROVENANCE_SCHEMA,
    format_skill_provenance_doctor,
    format_skill_why,
    skill_provenance_doctor,
    verify_procedural_skill_provenance,
)
from proto_mind.skill_lifecycle_audit import (
    PROCEDURAL_SKILL_LIFECYCLE_AUDIT_MODE,
    ProceduralSkillLifecycleAudit,
    format_skill_lifecycle_audit_command,
)
from proto_mind.skill_lifecycle_metadata import (
    PROCEDURAL_SKILL_LIFECYCLE_METADATA_FIELDS,
    PROCEDURAL_SKILL_LIFECYCLE_METADATA_MODE,
    PROCEDURAL_SKILL_LIFECYCLE_METADATA_REASON,
    PROCEDURAL_SKILL_LIFECYCLE_METADATA_SCHEMA,
    PROCEDURAL_SKILL_LIFECYCLE_METADATA_WRITER_INSTALLED,
    build_procedural_skill_lifecycle_metadata_preview,
    format_procedural_skill_lifecycle_metadata_contract,
    procedural_skill_lifecycle_metadata_doctor,
    verify_procedural_skill_lifecycle_metadata,
)
from proto_mind.skill_lifecycle_restore import (
    PROCEDURAL_SKILL_LIFECYCLE_RESTORE_EXPECTED_CHANGED_FIELDS,
    PROCEDURAL_SKILL_LIFECYCLE_RESTORE_FIELDS,
    PROCEDURAL_SKILL_LIFECYCLE_RESTORE_MODE,
    PROCEDURAL_SKILL_LIFECYCLE_RESTORE_RECEIPT_FIELDS,
    PROCEDURAL_SKILL_LIFECYCLE_RESTORE_SCHEMA,
    PROCEDURAL_SKILL_LIFECYCLE_RESTORE_WRITER_INSTALLED,
    build_procedural_skill_lifecycle_restore_metadata_preview,
    format_procedural_skill_lifecycle_restore_command,
    procedural_skill_lifecycle_restore_doctor,
    review_procedural_skill_lifecycle_restore,
    verify_procedural_skill_lifecycle_restore_metadata,
)
from proto_mind.skill_lifecycle_restore_authorization import (
    PROCEDURAL_SKILL_RESTORE_AUTHORIZATION_BLUEPRINT_FIELDS,
    PROCEDURAL_SKILL_RESTORE_AUTHORIZATION_ENGINE_INSTALLED,
    PROCEDURAL_SKILL_RESTORE_AUTHORIZATION_SCHEMA,
    PROCEDURAL_SKILL_RESTORE_RUN_ONCE_STATE_INSTALLED,
    PROCEDURAL_SKILL_RESTORE_TOKEN_GENERATOR_INSTALLED,
    format_procedural_skill_restore_authorization_command,
    procedural_skill_restore_authorization_doctor,
    review_procedural_skill_restore_authorization,
)
from proto_mind.skill_lifecycle_restore_apply import (
    PROCEDURAL_SKILL_RESTORE_APPLY_ENGINE_INSTALLED,
    PROCEDURAL_SKILL_RESTORE_APPLY_MAX_RECEIPTS,
    OperatorReviewedProceduralSkillRestoreApplySession,
    ProceduralSkillRestoreApplyError,
    format_procedural_skill_restore_apply_command,
    procedural_skill_restore_apply_confirmation_token,
    procedural_skill_restore_apply_receipt_hash,
    reset_procedural_skill_restore_apply_session,
)
from proto_mind.skill_lifecycle_restore_receipt_audit import (
    PROCEDURAL_SKILL_RESTORE_DURABLY_RECOVERABLE_RECEIPT_FIELDS,
    PROCEDURAL_SKILL_RESTORE_PROCESS_ONLY_RECEIPT_FIELDS,
    PROCEDURAL_SKILL_RESTORE_RECEIPT_AUDIT_MODE,
    PROCEDURAL_SKILL_RESTORE_RECEIPT_AUDIT_SCHEMA,
    PROCEDURAL_SKILL_RESTORE_RECEIPT_EVIDENCE_FIELDS,
    ProceduralSkillRestoreReceiptAudit,
    build_procedural_skill_restore_receipt_evidence,
    format_procedural_skill_restore_receipt_audit_command,
    verify_procedural_skill_restore_receipt_evidence,
)
from proto_mind.experience_learning_skill_restore_reevaluation import (
    PROCEDURAL_SKILL_RESTORE_REEVALUATION_MODE,
    PROCEDURAL_SKILL_RESTORE_REEVALUATION_REQUIRED_CALL_FIELDS,
    ProceduralSkillRestoreReevaluationReviewer,
    format_procedural_skill_restore_reevaluation_command,
)
from proto_mind.experience_learning_skill_restore_capture_readiness import (
    PROCEDURAL_SKILL_RESTORE_CAPTURE_FUTURE_RECEIPT_FIELDS,
    PROCEDURAL_SKILL_RESTORE_CAPTURE_READINESS_MODE,
    ProceduralSkillRestoreCaptureReadiness,
    ProceduralSkillRestoreCaptureReadinessError,
    format_procedural_skill_restore_capture_readiness_command,
    verify_procedural_skill_restore_capture_blueprint,
)
from proto_mind.experience_learning_eligibility import (
    LEARNING_ELIGIBILITY_MAX_IDS_PER_KIND,
    LearningEligibilityRequest,
    LearningPromotionEligibilityReviewer,
    format_learning_eligibility_command,
)
from proto_mind.experience_learning_proposal import (
    LEARNING_PROPOSAL_MAX_RECEIPTS,
    LearningProposalError,
    LearningPromotionProposalBlueprint,
    LearningPromotionProposalBuilder,
    OperatorReviewedLearningProposalSession,
    format_learning_proposal_command,
    learning_proposal_confirmation_token,
)
from proto_mind.experience_learning_apply import (
    LEARNING_MEMORY_APPLY_ENGINE_INSTALLED,
    LEARNING_MEMORY_APPLY_MAX_RECEIPTS,
    OperatorReviewedLearningMemoryApplySession,
    format_learning_memory_apply_command,
    learning_memory_apply_confirmation_token,
)
from proto_mind.experience_learning_readiness import (
    LEARNING_APPLY_ENGINE_INSTALLED,
    LearningPromotionApplyReadiness,
    format_learning_apply_readiness_command,
)
from proto_mind.experience_vocabulary import (
    ExperienceLifecycleBuilder,
    build_failure_correction_trace,
    build_success_lifecycle_trace,
    format_experience_vocabulary_report,
    run_experience_vocabulary_benchmark,
)
from proto_mind.export_retention import MANY_FILES_THRESHOLD, format_exports_command
from proto_mind.focus_layer import FocusMode, format_focus_command
from proto_mind.goal_stack import GoalStack, format_goal_command
from proto_mind.grounding_auditor import GroundingAuditor
from proto_mind.identity import IdentityStore, format_identity_command
from proto_mind.lesson_recall_benchmark import (
    LESSON_RECALL_BENCHMARK_VERSION,
    format_verified_lesson_recall_benchmark,
    run_verified_lesson_recall_benchmark,
)
from proto_mind.memory_commands import format_memory_command
from proto_mind.memory_governance import inspect_memory_quality, memory_write_policy
from proto_mind.memory_provenance import (
    MEMORY_LESSON_PROVENANCE_SCHEMA,
    build_learning_lesson_provenance,
    verify_memory_provenance,
)
from proto_mind.memory_card_layer import OperatorMemoryCard, format_memory_card_command
from proto_mind.memory_hygiene import MemoryHygiene
from proto_mind.memory_keeper import MemoryKeeper
from proto_mind.memory_store import MemoryStore
from proto_mind.milestone_layer import format_milestone_command
from proto_mind.models import (
    GroundingAuditResult,
    InteractionResult,
    InteractionSummary,
    MemoryRecord,
    ObserverState,
    RetrievalTrace,
    SelfReflectionResult,
)
from proto_mind.natural_commands import (
    EVENING_REVIEW_BUNDLE,
    HEALTH_CHECK_BUNDLE,
    NATURAL_COMMAND_ROUTES,
    format_natural_introspection_command,
    natural_router_doctor,
    normalize_natural_command,
    route_natural_command,
)
from proto_mind.observer import Observer
from proto_mind.operating_loop import format_loop_command
from proto_mind.proto_status import format_proto_command
from proto_mind.prechange_layer import PreChangeRitual, format_prechange_command
from proto_mind.plan_layer import ActionDryRunPlan, format_plan_command
from proto_mind.reasoner import MockReasoner, OllamaReasoner
from proto_mind.reasoners import create_reasoner
from proto_mind.reasoners.base import BaseReasoner
from proto_mind.reflection_journal import ReflectionJournal, format_reflection_command
from proto_mind.runner_layer import NoOpRunnerContract, format_runner_command
from proto_mind.runner_candidates import FUTURE_RUNNER_CANDIDATES, RunnerCandidateSet, format_runner_candidates_command
from proto_mind.runner_exec import (
    ACTIVE_READONLY_ALLOWLIST,
    CAPABILITIES_SAFETY_COMMAND,
    CAPABILITIES_SAFETY_CONFIRMATION,
    DAILY_DOCTOR_COMMAND,
    DAILY_DOCTOR_CONFIRMATION,
    EVIDENCE_HISTORY_MAX_SIZE,
    EXACT_CONFIRMATION,
    EXPORTS_DOCTOR_COMMAND,
    EXPORTS_DOCTOR_CONFIRMATION,
    PILOT_COMMAND,
    ReadOnlyRunnerPilot,
    format_runner_exec_command,
    reset_runner_exec_evidence,
)
from proto_mind.runner_mvp import MVP_ALLOWLIST_CANDIDATES, RunnerMVPDesignLock, format_runner_mvp_command
from proto_mind.sandbox_layer import ExecutionSandboxBlueprint, format_sandbox_command
from proto_mind.self_reflection import SelfReflector
from proto_mind.session_log import SessionOperatorLogger, format_session_log_command
from proto_mind.session_rituals import format_session_ritual_command
from proto_mind.showcase_layer import (
    SHOWCASE_COMMANDS,
    ContestShowcase,
    format_showcase_command,
)
from proto_mind.skill_library import (
    SKILL_LIFECYCLE_DIRECT_STATUS_GUARD_INSTALLED,
    SKILL_LIFECYCLE_PAYLOAD_GUARD_INSTALLED,
    SkillLibrary,
    format_skill_command,
)
from proto_mind.task_queue import TaskQueue, format_task_command
from proto_mind.topic_utils import extract_topic_tags
from proto_mind.main import (
    _format_interaction_result,
    _format_turn_notices,
    format_natural_command,
    is_exit_command,
    process_interactive_input,
    process_interactive_input_with_envelope,
)
from proto_mind import desktop_app, pyside_app
from proto_mind.desktop_view_model import (
    LOCAL_CAPABILITY_CARD_BADGES,
    build_local_capability_card_html,
    project_local_capability_card,
    render_local_capability_card_html,
)
from proto_mind.world_model import WorldModelLite, format_world_command
from proto_mind.warning_inspector import LegacyWarningInspector, format_warning_command


PERSISTENT_EXPERIENCE_COMMAND_PREFIXES = (
    "/experience persist",
    "/experience export",
    "/experience apply",
    "/experience promote",
    "/experience backfill",
)


def build_test_system(tmp_path: Path) -> tuple[Coordinator, MemoryStore, MemoryKeeper]:
    data_dir = tmp_path / "data"
    store = MemoryStore(
        working_path=data_dir / "working_memory.json",
        persistent_path=data_dir / "persistent_memory.json",
    )
    keeper = MemoryKeeper(store)
    coordinator = Coordinator(
        observer=Observer(),
        memory_keeper=keeper,
        reasoner=MockReasoner(),
    )
    return coordinator, store, keeper


def build_test_cognitive_turn_result() -> InteractionResult:
    recalled = MemoryRecord(
        "Prefer concise answers.", "preference", 0.9, "operator",
        id="turn-memory-1", timestamp="2026-01-01T00:00:00Z",
        provenance={"private_source": "NOT_A_PROJECTED_PROVENANCE_BLOB"},
    )
    unrelated = MemoryRecord(
        "NOT_A_PROJECTED_STORE_SNAPSHOT", "insight", 0.5, "test",
        id="unretrieved-memory", timestamp="2026-01-01T00:00:00Z",
    )
    return InteractionResult(
        response="A concise answer.\nObserver: this line belongs to the answer, not metadata.",
        observer_state=ObserverState("continuity_followup", True, 0.8, ["preference"]),
        retrieved_memory=[recalled],
        retrieval_trace=RetrievalTrace(
            user_input="NOT_A_PROJECTED_ORIGINAL_PROMPT",
            query_type="continuity_followup",
            normalized_query_topics=["preference"],
            specific_query_topics=["preference"],
            query_mode="current_state",
            current_state_oriented=True,
            historical_state_oriented=False,
            broad_inventory=False,
            top_k=5,
        ),
        memory_summary=InteractionSummary(
            "insight", "NOT_A_PROJECTED_MEMORY_INPUT", 0.3, ["preference"], False,
            storage_rationale="No new durable fact.",
            promotion_rationale="No promotion happened.",
            override_rationale="No override detected.",
        ),
        working_memory_snapshot=[unrelated],
        persistent_memory_snapshot=[recalled, unrelated],
        reasoner_backend="scripted",
        grounding_audit=GroundingAuditResult(
            True, "supported", "supported", "not_applicable", "not_applicable",
            evidence=["turn-memory-1: operator preference"],
        ),
        self_reflection=SelfReflectionResult(
            True, "aligned", "aligned", "not_applicable", "low", "low", "high",
            warnings=["fixture reflection warning"],
            suggested_next_turn_adjustments=["Stay concise."],
            correction_hints=["Use the stored preference."],
            should_carry_forward=True,
            carry_forward_scope="next_turn",
        ),
        previous_correction_hints=["Earlier correction."],
    )


def build_test_cognitive_card_response(result: InteractionResult | None = None) -> InteractiveResponse:
    result = result or build_test_cognitive_turn_result()
    return project_interactive_response(_format_interaction_result(result), result)


def build_test_cognitive_card_ui(*, debug: bool = False, mode: str = "normal") -> SimpleNamespace:
    calls: list[tuple[str, object]] = []
    ui = SimpleNamespace(
        calls=calls, cancel_requested_for_current_worker=False, current_display_mode=mode,
        last_raw_response="", runtime_state="ready", closed=False,
        debug_checkbox=SimpleNamespace(isChecked=lambda: debug),
        input_box=SimpleNamespace(setFocus=lambda: None),
        _set_busy=lambda busy: calls.append(("busy", busy)),
        _append_typed_card=lambda html: calls.append(("card", html)),
        append_system_message=lambda text: calls.append(("system", text)),
        append_report_message=lambda text: calls.append(("report", text)),
        append_assistant_message=lambda text: calls.append(("assistant", text)),
        _update_panel_from_output=lambda text: calls.append(("panel", text)),
        _finish_status_refresh_response=lambda text: calls.append(("refresh", text)),
        _refresh_panel=lambda: None,
    )
    ui.close = lambda: setattr(ui, "closed", True)
    return ui


def build_test_experience_events(
    tmp_path: Path,
    *,
    turn_id: int = 1,
    trace_id: str = "store-test",
) -> list[ExperienceEvent]:
    coordinator, _, _ = build_test_system(tmp_path)
    user_input = "Explain the current Proto-Mind focus briefly."
    result = coordinator.handle(user_input)
    return ExperienceTraceBuilder(session_id="store-test-session").build_turn_events(
        user_input,
        result,
        turn_id=turn_id,
        trace_id=trace_id,
        created_at=f"2026-01-01T00:00:{turn_id:02d}Z",
    )


def build_test_learning_candidate(
    tmp_path: Path,
) -> tuple[
    Coordinator,
    MemoryStore,
    SupervisedExperiencePilot,
    OperatorReviewedLearningBridge,
    CognitiveLearningPreviewCandidate,
]:
    coordinator, store, _ = build_test_system(tmp_path / "cognitive")
    coordinator.pending_correction_hints = [
        "Use the active SQLite decision as current state."
    ]
    pilot = SupervisedExperiencePilot(tmp_path, session_id="learning-decision-test")
    pilot.preview()
    pilot.consent(pilot.expected_consent_phrase)
    user_input = "Explain the current storage decision."
    pilot.observe_normal_turn(user_input, coordinator.handle(user_input))
    bridge = OperatorReviewedLearningBridge(pilot.snapshot())
    candidate = bridge.review()[0].candidates[0]
    return coordinator, store, pilot, bridge, candidate


def build_test_learning_proposal(
    tmp_path: Path,
    *,
    target: str = "memory",
) -> tuple[
    Coordinator,
    MemoryStore,
    SupervisedExperiencePilot,
    OperatorReviewedLearningBridge,
    CognitiveLearningPreviewCandidate,
    SkillLibrary,
    LearningPromotionProposalBlueprint,
]:
    coordinator, store, pilot, bridge, candidate = build_test_learning_candidate(tmp_path)
    skills = SkillLibrary(tmp_path / "skills.jsonl")
    if target == "memory":
        store.save_persistent_memory(
            [
                MemoryRecord(
                    id="mem_proposal_ref",
                    content="Separate proposal reference.",
                    type="project_fact",
                    importance=0.7,
                    source="test",
                )
            ]
        )
        request = LearningEligibilityRequest(
            candidate_id=candidate.id,
            target="memory",
            memory_ids=["mem_proposal_ref"],
            skill_ids=[],
        )
    else:
        skills.skills_path.write_text(
            json.dumps(
                {
                    "id": "skill_proposal_ref",
                    "name": "Separate proposal reference",
                    "summary": "Unrelated procedure.",
                    "body": "",
                    "status": "active",
                    "category": "workflow",
                }
            )
            + "\n",
            encoding="utf-8",
        )
        request = LearningEligibilityRequest(
            candidate_id=candidate.id,
            target="skill",
            memory_ids=[],
            skill_ids=["skill_proposal_ref"],
        )
    decision = pilot.learning_decisions.decide(
        candidate,
        "accepted",
        token=learning_confirmation_token(candidate),
    )
    blueprint = LearningPromotionProposalBuilder(
        memory_store=store,
        skill_library=skills,
    ).build(candidate, decision, request)
    return coordinator, store, pilot, bridge, candidate, skills, blueprint


def build_test_learning_apply(
    tmp_path: Path,
    *,
    target: str = "memory",
) -> tuple[
    Coordinator,
    MemoryStore,
    SupervisedExperiencePilot,
    OperatorReviewedLearningBridge,
    CognitiveLearningPreviewCandidate,
    SkillLibrary,
    object,
]:
    coordinator, store, pilot, bridge, candidate, skills, blueprint = (
        build_test_learning_proposal(tmp_path, target=target)
    )
    proposal = pilot.learning_proposals.create(
        blueprint,
        token=learning_proposal_confirmation_token(blueprint),
    )
    return coordinator, store, pilot, bridge, candidate, skills, proposal


def _id_from_output(output: str, label: str) -> str:
    prefix = label.strip()
    for line in output.splitlines():
        stripped = line.strip()
        if stripped.startswith(prefix):
            return stripped[len(prefix) :].strip()
    raise AssertionError(f"Missing {label!r} in output: {output}")


def _test_skill_authoring_flags() -> str:
    return " ".join(
        [
            '--name "Diagnose repeated verified failure"',
            '--summary "Inspect exact evidence before choosing a bounded response."',
            '--trigger "When the same verified failure recurs"',
            '--precondition "The source lesson remains active and provenance-verified"',
            '--step "Inspect the exact source evidence"',
            '--step "Choose one bounded reversible response"',
            '--permission "Read-only project inspection"',
            '--verify "Observed evidence matches the source lesson"',
            '--failure "Stop when provenance or current state drifts"',
        ]
    )


def apply_test_learning_proposal(
    store: MemoryStore,
    pilot: SupervisedExperiencePilot,
    bridge: OperatorReviewedLearningBridge,
    skills: SkillLibrary,
    proposal: object,
) -> tuple[str, object]:
    dependencies = {
        "bridge": bridge,
        "decisions": pilot.learning_decisions,
        "proposals": pilot.learning_proposals,
        "applies": pilot.learning_applies,
        "memory_store": store,
        "skill_library": skills,
    }
    preview = format_learning_memory_apply_command(
        f"/experience learning apply-preview {proposal.id}",
        **dependencies,
    )
    token = _id_from_output(preview, "confirmation_token:")
    output = format_learning_memory_apply_command(
        f"/experience learning apply {proposal.id} {token}",
        **dependencies,
    )
    receipt = pilot.learning_applies.get(proposal.id)
    if receipt is None:
        raise AssertionError(f"Learning apply did not create a receipt: {output}")
    return output, receipt


def build_test_learning_outcome_review(
    tmp_path: Path,
) -> tuple[Coordinator, MemoryStore, list[ExperienceEvent], object]:
    _, store, pilot, bridge, _, skills, proposal = build_test_learning_apply(tmp_path)
    _, receipt = apply_test_learning_proposal(store, pilot, bridge, skills, proposal)
    lesson = next(
        record
        for record in store.load_persistent_memory()
        if record.id == receipt.created_record_id
    )
    store.save_persistent_memory([lesson])
    store.save_working_memory([])
    coordinator = Coordinator(
        observer=Observer(),
        memory_keeper=MemoryKeeper(MemoryStore(store.working_path, store.persistent_path)),
        reasoner=MockReasoner(),
    )
    query = "As we discussed earlier, what did we learn about the active SQLite decision?"
    events = ExperienceTraceBuilder(
        session_id="lifecycle-test",
        source="test",
    ).build_turn_events(
        query,
        coordinator.handle(query),
        turn_id="1",
        trace_id="lifecycle-test",
        created_at=(datetime.now(UTC) + timedelta(seconds=1)).isoformat(),
    )
    review = LearningOutcomeReviewer(events, [lesson]).review(lesson.id)
    return coordinator, store, events, review


def build_test_procedural_skill_authoring(
    tmp_path: Path,
) -> tuple[
    Coordinator,
    MemoryStore,
    object,
    SkillLibrary,
    ProceduralSkillContractBuilder,
    OperatorReviewedProceduralSkillAuthoringSession,
    object,
]:
    coordinator, store, _, review = build_test_learning_outcome_review(tmp_path)
    library = SkillLibrary(tmp_path / "skills.jsonl")
    builder = ProceduralSkillContractBuilder(memory_store=store, skill_library=library)
    request = parse_procedural_skill_authoring_request(
        shlex.split(f"{review.lesson_memory_id} {_test_skill_authoring_flags()}")
    )
    blueprint = build_procedural_skill_authoring_blueprint(builder, request)
    session = OperatorReviewedProceduralSkillAuthoringSession()
    receipt = session.create(
        blueprint,
        token=procedural_skill_authoring_confirmation_token(blueprint),
    )
    return coordinator, store, review, library, builder, session, receipt


def build_test_applied_procedural_skill(
    tmp_path: Path,
) -> tuple[MemoryStore, SkillLibrary, object, object]:
    _, store, _, library, builder, _, receipt = build_test_procedural_skill_authoring(tmp_path)
    reviewer = ProceduralSkillApplyReadiness(builder=builder, skill_library=library)
    apply_session = OperatorReviewedProceduralSkillApplySession()
    token = procedural_skill_apply_confirmation_token(
        apply_session.review(receipt, reviewer=reviewer)
    )
    applied = apply_session.apply(receipt, token=token, reviewer=reviewer)
    return store, library, receipt, applied


def build_test_procedural_skill_outcome_events(
    skill: dict[str, object],
    *,
    outcome: str,
    execution_performed_by_proto_mind: bool = False,
) -> list[ExperienceEvent]:
    provenance = skill["provenance"]
    assert isinstance(provenance, dict)
    applied_at = datetime.fromisoformat(str(provenance["applied_at"]).replace("Z", "+00:00"))
    base = applied_at + timedelta(minutes=1)
    skill_id = str(skill["id"])
    provenance_id = str(provenance["id"])
    goal = ExperienceEvent(
        id="evt_skill_outcome_goal",
        created_at=base.isoformat(),
        event_type="goal_created",
        session_id="skill-outcome-test",
        turn_id="1",
        source="skill_outcome_test",
        source_event_ids=[],
        payload={
            "goal_id": "goal_skill_outcome",
            "title_preview": "Review a manually used procedural skill.",
            "priority": "normal",
        },
        confidence=1.0,
    )
    plan = ExperienceEvent(
        id="evt_skill_outcome_plan",
        created_at=(base + timedelta(seconds=1)).isoformat(),
        event_type="plan_created",
        session_id=goal.session_id,
        turn_id=goal.turn_id,
        source=goal.source,
        source_event_ids=[goal.id],
        payload={
            "plan_id": "plan_skill_outcome",
            "goal_id": "goal_skill_outcome",
            "step_count": 1,
            "plan_preview": "Operator manually follows the stored procedure.",
        },
        confidence=1.0,
    )
    call = ExperienceEvent(
        id="evt_skill_outcome_call",
        created_at=(base + timedelta(seconds=2)).isoformat(),
        event_type="tool_called",
        session_id=goal.session_id,
        turn_id=goal.turn_id,
        source=goal.source,
        source_event_ids=[plan.id],
        payload={
            "call_id": "call_skill_outcome",
            "capability": f"skill:{skill_id}",
            "input_preview": "Operator-reported manual use.",
            "risk": "low",
            "read_only": True,
            "skill_id": skill_id,
            "skill_provenance_id": provenance_id,
            "manual_operator_use": True,
            "execution_performed_by_proto_mind": execution_performed_by_proto_mind,
        },
        confidence=1.0,
    )
    events = [goal, plan, call]
    if outcome in {"success", "mixed"}:
        events.append(
            ExperienceEvent(
                id="evt_skill_outcome_success",
                created_at=(base + timedelta(seconds=3)).isoformat(),
                event_type="tool_succeeded",
                session_id=goal.session_id,
                turn_id=goal.turn_id,
                source=goal.source,
                source_event_ids=[call.id],
                payload={
                    "call_id": "call_skill_outcome",
                    "output_preview": "Operator verified the procedure result.",
                    "verified": True,
                    "operator_reported": True,
                },
                confidence=1.0,
            )
        )
    if outcome in {"failure", "mixed"}:
        events.append(
            ExperienceEvent(
                id="evt_skill_outcome_failure",
                created_at=(base + timedelta(seconds=4)).isoformat(),
                event_type="tool_failed",
                session_id=goal.session_id,
                turn_id=goal.turn_id,
                source=goal.source,
                source_event_ids=[call.id],
                payload={
                    "call_id": "call_skill_outcome",
                    "error_type": "operator_reported_failure",
                    "error_preview": "The manual procedure did not satisfy verification.",
                    "retryable": False,
                    "operator_reported": True,
                },
                confidence=1.0,
            )
        )
    return events


def build_test_captured_procedural_skill_outcomes(
    tmp_path: Path,
    *,
    outcomes: tuple[str, ...] = ("success",),
) -> tuple[
    MemoryStore,
    SkillLibrary,
    SupervisedExperiencePilot,
    dict[str, object],
]:
    store, library, _, _ = build_test_applied_procedural_skill(tmp_path)
    record = library.read_snapshot()["records"][0]
    pilot = SupervisedExperiencePilot(tmp_path, session_id="skill-outcome-decision-test")
    pilot.preview()
    pilot.consent(pilot.expected_consent_phrase)
    builder = ProceduralSkillOutcomeCaptureBuilder(
        memory_store=store,
        skill_library=library,
    )
    for index, outcome in enumerate(outcomes, start=1):
        evidence = f"Operator reported {outcome} evidence {index}."
        blueprint = builder.build(
            session_id=pilot.session_id,
            skill_id=str(record["id"]),
            outcome=outcome,
            evidence=evidence,
        )
        pilot.skill_outcome_captures.capture(
            blueprint,
            token=procedural_skill_outcome_capture_confirmation_token(blueprint),
            pilot_state=pilot.state,
            append_events=pilot.append_supervised_manual_skill_outcome_events,
        )
    return store, library, pilot, record


def build_test_procedural_skill_lifecycle_readiness(
    tmp_path: Path,
    *,
    outcomes: tuple[str, ...] = ("success",),
    decision: str = "keep",
) -> tuple[
    MemoryStore,
    SkillLibrary,
    SupervisedExperiencePilot,
    dict[str, object],
    object,
    ProceduralSkillLifecycleApplyReadiness,
]:
    store, library, pilot, record = build_test_captured_procedural_skill_outcomes(
        tmp_path,
        outcomes=outcomes,
    )
    builder = ProceduralSkillOutcomeDecisionBuilder(
        events=pilot.snapshot(),
        memory_store=store,
        skill_library=library,
        capture_session=pilot.skill_outcome_captures,
    )
    blueprint = builder.build(str(record["id"]), decision)
    receipt = pilot.skill_outcome_decisions.decide(
        blueprint,
        token=procedural_skill_outcome_decision_confirmation_token(blueprint),
    )
    reviewer = ProceduralSkillLifecycleApplyReadiness(
        builder=builder,
        skill_library=library,
    )
    return store, library, pilot, record, receipt, reviewer


def build_test_durably_archived_procedural_skill(
    tmp_path: Path,
) -> tuple[MemoryStore, SkillLibrary, dict[str, object]]:
    store, library, pilot, record, receipt, reviewer = (
        build_test_procedural_skill_lifecycle_readiness(
            tmp_path,
            outcomes=("failure",),
            decision="archive",
        )
    )
    review = pilot.skill_lifecycle_metadata_applies.review(
        receipt, reviewer=reviewer
    )
    pilot.skill_lifecycle_metadata_applies.apply(
        receipt,
        token=procedural_skill_lifecycle_metadata_apply_confirmation_token(review),
        reviewer=reviewer,
    )
    current = library.read_snapshot()["records"][0]
    assert current["id"] == record["id"]
    return store, library, current


def build_test_restored_procedural_skill(
    tmp_path: Path,
) -> tuple[MemoryStore, SkillLibrary, dict[str, object]]:
    store, library, archived = build_test_durably_archived_procedural_skill(tmp_path)
    session = OperatorReviewedProceduralSkillRestoreApplySession()
    review = session.review(
        str(archived["id"]),
        skills_path=library.skills_path,
        persistent_memory_path=store.persistent_path,
    )
    session.apply(
        str(archived["id"]),
        token=procedural_skill_restore_apply_confirmation_token(review),
        skills_path=library.skills_path,
        persistent_memory_path=store.persistent_path,
    )
    return store, library, library.read_snapshot()["records"][0]


def build_test_restored_skill_outcome_events(
    skill: dict[str, object],
    *,
    outcome: str = "success",
    after_restore: bool = True,
    exact_restore_binding: bool = True,
    execution_performed_by_proto_mind: bool = False,
) -> list[dict[str, object]]:
    events = [
        event.to_dict()
        for event in build_test_procedural_skill_outcome_events(
            skill,
            outcome=outcome,
            execution_performed_by_proto_mind=execution_performed_by_proto_mind,
        )
    ]
    lifecycle = skill["lifecycle"]
    assert isinstance(lifecycle, dict)
    restored_at = datetime.fromisoformat(
        str(lifecycle["transitioned_at"]).replace("Z", "+00:00")
    )
    offset = timedelta(minutes=1 if after_restore else -2)
    for index, event in enumerate(events):
        event["created_at"] = (restored_at + offset + timedelta(seconds=index)).isoformat()
    if exact_restore_binding:
        evidence = build_procedural_skill_restore_receipt_evidence(skill)
        payload = events[2]["payload"]
        assert isinstance(payload, dict)
        payload.update(
            {
                "post_restore_manual_use": True,
                "restore_metadata_id": lifecycle["id"],
                "restore_metadata_hash": lifecycle["metadata_hash"],
                "restore_evidence_hash": evidence["evidence_hash"],
            }
        )
    return events


def build_test_learning_lifecycle_transition(
    tmp_path: Path,
    *,
    decision: str = "keep",
) -> tuple[
    Coordinator,
    MemoryStore,
    list[ExperienceEvent],
    object,
    OperatorReviewedLearningLifecycleSession,
    OperatorReviewedLearningLifecycleApplySession,
]:
    coordinator, store, events, keep_review = build_test_learning_outcome_review(tmp_path)
    review = keep_review
    if decision in {"reject", "supersede"}:
        old = store.load_persistent_memory()[0]
        correction = _correction_event(events)
        transition_events = [*events, correction]
        if decision == "supersede":
            replacement_id = "mem_lifecycle_apply_replacement"
            applied_at = (datetime.now(UTC) + timedelta(seconds=2)).isoformat()
            payload = {
                "schema": "memory.lesson.v1",
                "content": "Use the narrower verified lifecycle replacement lesson.",
                "type": "lesson",
                "importance": 0.9,
                "source": "experience_learning_proposal",
                "tags": ["replacement"],
                "confidence": 0.9,
            }
            proposal_hash = "e" * 64
            provenance = build_learning_lesson_provenance(
                memory_id=replacement_id,
                applied_at=applied_at,
                proposal_id=f"learnprop_{proposal_hash[:16]}",
                proposal_hash=proposal_hash,
                candidate_id="learncand_lifecycle_apply_replacement",
                candidate_hash="f" * 64,
                decision_id="learndec_lifecycle_apply_replacement",
                eligibility_receipt_id="learnelig_lifecycle_apply_replacement",
                selected_scope_hash="1" * 64,
                proposed_payload=payload,
                evidence_event_ids=["evt_lifecycle_apply_replacement_source"],
                source_kinds=["correction"],
            )
            replacement = MemoryRecord(
                id=replacement_id,
                content=payload["content"],
                type="lesson",
                importance=0.9,
                source="experience_learning_proposal",
                tags=["replacement"],
                timestamp=applied_at,
                updated_at=applied_at,
                confidence=0.9,
                provenance=provenance,
            )
            store.save_persistent_memory([old, replacement])
            transition_events.extend(_replacement_events(correction, replacement_id))
        review = LearningOutcomeReviewer(
            transition_events,
            store.load_persistent_memory(),
        ).review(old.id)
        events = transition_events
    lifecycle_session = OperatorReviewedLearningLifecycleSession()
    lifecycle_session.decide(
        review,
        decision,
        token=learning_lifecycle_confirmation_token(review),
    )
    return (
        coordinator,
        store,
        events,
        review,
        lifecycle_session,
        OperatorReviewedLearningLifecycleApplySession(),
    )


def apply_test_learning_lifecycle_transition(
    store: MemoryStore,
    events: list[ExperienceEvent],
    review: object,
    lifecycle: OperatorReviewedLearningLifecycleSession,
    applies: OperatorReviewedLearningLifecycleApplySession,
) -> object:
    preview = format_learning_lifecycle_apply_command(
        f"/experience learning lifecycle-apply-preview {review.lesson_memory_id}",
        events=events,
        memory_store=store,
        lifecycle_session=lifecycle,
        apply_session=applies,
    )
    token = _id_from_output(preview, "confirmation_token:")
    output = format_learning_lifecycle_apply_command(
        f"/experience learning apply lifecycle {review.lesson_memory_id} {token}",
        events=events,
        memory_store=store,
        lifecycle_session=lifecycle,
        apply_session=applies,
    )
    receipt = applies.get(review.lesson_memory_id)
    if receipt is None:
        raise AssertionError(f"Lifecycle apply did not create a receipt: {output}")
    return receipt


def _single_action_record(project_root: Path) -> dict[str, object]:
    path = project_root / "proto_mind" / "data" / "action_queue.jsonl"
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(records) != 1:
        raise AssertionError(f"Expected one action proposal, got {len(records)}")
    return records[0]


def _confirmed_action(project_root: Path, action_input: str) -> tuple[str, str]:
    created = format_action_queue_command(f"/action propose {action_input}", project_root=project_root)
    proposal_id = _id_from_output(created, "id:")
    format_action_queue_command(f"/action approve {proposal_id}", project_root=project_root)
    preview = format_action_queue_command(f"/action confirm-preview {proposal_id}", project_root=project_root)
    token = _id_from_output(preview, "confirmation_token:")
    confirmed = format_action_queue_command(f"/action confirm {proposal_id} {token}", project_root=project_root)
    if "Action proposal confirmed" not in confirmed:
        raise AssertionError(f"Could not confirm action fixture: {confirmed}")
    return proposal_id, token


def _executed_action(project_root: Path, action_input: str = "/data doctor") -> str:
    proposal_id, _ = _confirmed_action(project_root, action_input)
    output = format_action_queue_command(
        f"/action run {proposal_id}", project_root=project_root, executor=lambda command: f"output for {command}"
    )
    if "Status: RUN" not in output:
        raise AssertionError(f"Could not execute action fixture: {output}")
    return proposal_id


def _snapshot_diff_fixture(
    *,
    status: str = "OK",
    enabled: bool = False,
    warning_count: int = 0,
    legacy_count: int = 0,
) -> dict[str, object]:
    return {
        "generated_at": "2026-06-30T10:00:00+00:00" if status == "OK" else "2026-06-30T11:00:00+00:00",
        "status": status,
        "doctor_summary": {"overall_status": status, "doctors": {"/data doctor": "OK"}},
        "warnings": [],
        "warning_summary": {
            "count": warning_count,
            "categories": {"legacy": legacy_count} if legacy_count else {},
            "errors": 0,
        },
        "action_summary": {
            "total": 1,
            "status_counts": {"approved": 1},
            "execution_state_counts": {"unconfirmed": 1},
            "latest_executed": None,
        },
        "consolidation_summary": {
            "total": 1,
            "status_counts": {"approved": 1},
            "candidate_count": 1,
        },
        "context_injection": {"enabled": enabled, "mode": "preview_safe", "max_chars": 2540, "health": "OK"},
        "memory_summary": {"total": 1, "active": 1, "active_explicit": 1},
        "task_summary": {"open_total": 0, "open_high_priority": 0, "status_counts": {}},
        "focus": {"focused_goal": None, "next_task": None},
        "registry_summary": {"registered_commands": 202},
        "source_notes": ["fixture"],
        "no_mutation": True,
    }


def _create_healthy_export_dirs(project_root: Path) -> None:
    exports_root = project_root / "proto_mind" / "exports"
    for name in EXPORT_DIRS:
        (exports_root / name).mkdir(parents=True, exist_ok=True)
    for name, payload in (
        ("proto_snapshots", {"generated_at": "2026-07-01T06:00:00+00:00", "status": "OK"}),
        (
            "proto_snapshot_diffs",
            {"generated_at": "2026-07-01T06:05:00+00:00", "diff_status": "NO STRUCTURAL CHANGES"},
        ),
    ):
        directory = exports_root / name
        (directory / "daily_fixture.md").write_text("# Daily fixture\n", encoding="utf-8")
        (directory / "daily_fixture.json").write_text(json.dumps(payload), encoding="utf-8")


def _write_milestone_fixture(project_root: Path) -> None:
    (project_root / "PROTO_MIND_ARCHITECT_LEDGER.md").write_text(
        "# Proto-Mind Architect Ledger\n\n"
        "## Major Modules And Versions\n\n"
        "- Operating Loop v2 / Daily Agent Layer v1: read-only daily reports.\n"
        "- Operating Loop v2.1 / Session Rituals v1: read-only session reports.\n\n"
        "## Last Completed Milestone\n\n"
        "Operating Loop v2.2 / Milestone Tracker v1:\n\n"
        "- Deterministic roadmap awareness.\n\n"
        "## Next Candidate Tasks\n\n"
        "- Review legacy receipts before Operating Loop v2.3.\n",
        encoding="utf-8",
    )
    (project_root / "MILESTONE_TEST_OPERATOR_LOOP.md").write_text(
        "# Existing milestone fixture\n", encoding="utf-8"
    )
    (project_root / "KNOWN_WARNINGS_LEDGER.md").write_text(
        "# Known Warnings Ledger fixture\n\nDocumentation only.\n", encoding="utf-8"
    )


def _warning_fixture() -> list[dict[str, object]]:
    return [
        {
            "sources": ["/action queue-doctor", "/action run-audit"],
            "doctor_status": "WARN",
            "message": "act_20260628165932_d2a9: executed record is missing run_id",
            "category": "legacy",
            "severity": "warn",
            "safe_to_ignore": True,
            "inspect_command": "/action run-receipt act_20260628165932_d2a9",
        },
        {
            "sources": ["/data refs-doctor"],
            "doctor_status": "WARN",
            "message": "Applied queue item cq_20260626201008_e7ed is missing applied_record_id for memory receipt",
            "category": "dangling_ref",
            "severity": "warn",
            "safe_to_ignore": True,
            "inspect_command": "/consolidation queue-inspect cq_20260626201008_e7ed",
        },
        {
            "sources": ["/future doctor"],
            "doctor_status": "WARN",
            "message": "Unrecognized future warning signature",
            "category": "novel_signal",
            "severity": "warn",
            "safe_to_ignore": False,
            "inspect_command": "/data doctor",
        },
    ]


def _accepted_warning_fixture() -> list[dict[str, object]]:
    return [
        *_warning_fixture()[:2],
        {
            "sources": ["/action readiness-doctor"],
            "doctor_status": "WARN",
            "message": "act_20260628170033_9176: run command is not read-only: /context injection enable",
            "category": "policy_drift",
            "severity": "warn",
            "safe_to_ignore": False,
            "inspect_command": "/action inspect act_20260628170033_9176",
        },
        {
            "sources": ["/action readiness-doctor"],
            "doctor_status": "WARN",
            "message": "Approved but unconfirmed proposals: 2",
            "category": "queue_hygiene",
            "severity": "warn",
            "safe_to_ignore": True,
            "inspect_command": "/action readiness-doctor",
        },
    ]


def _agenda_state(*, unknown: bool = False, context_state: str = "disabled") -> dict[str, object]:
    accepted = [
        {"accepted_known": True, "operator_severity": "INFO", "category": "legacy"}
        for _ in range(12)
    ]
    unknown_items = (
        [
            {
                "accepted_known": False,
                "operator_severity": "WARN",
                "category": "novel_signal",
                "message": "New warning",
            }
        ]
        if unknown
        else []
    )
    return {
        "daily_status": "OK",
        "export_status": "OK",
        "system_status": "WARN" if accepted or unknown_items else "OK",
        "latest_snapshot": {"filename": "snapshot.json", "status": "WARN"},
        "latest_diff": {"filename": "diff.json", "status": "NO STRUCTURAL CHANGES"},
        "warnings": [*accepted, *unknown_items],
        "accepted": accepted,
        "unknown": unknown_items,
        "blocker_count": 0,
        "overall": "WARN" if accepted or unknown_items or context_state == "enabled" else "OK",
        "context_state": context_state,
    }


def _prechange_state(*, unknown: bool = False, blockers: int = 0, context_state: str = "disabled") -> dict[str, object]:
    state = _agenda_state(unknown=unknown, context_state=context_state)
    state["blocker_count"] = blockers
    state["readiness"] = "BLOCKED" if unknown or blockers else "WARN"
    state["safe_to_begin"] = not unknown and blockers == 0 and context_state == "disabled"
    state["agenda_doctor_status"] = "OK"
    state["export_doctor_status"] = "OK"
    return state


def _focus_state(*, unknown: bool = False, blockers: int = 0, context_state: str = "disabled") -> dict[str, object]:
    state = _prechange_state(unknown=unknown, blockers=blockers, context_state=context_state)
    state["focus_readiness"] = "BLOCKED" if unknown or blockers else "WARN"
    state["focus_planning_safe"] = not unknown and blockers == 0 and context_state == "disabled"
    return state


def _acceptance_state(*, unknown: bool = False, blockers: int = 0, context_state: str = "disabled") -> dict[str, object]:
    state = _focus_state(unknown=unknown, blockers=blockers, context_state=context_state)
    state["acceptance_readiness"] = "BLOCKED" if unknown or blockers else "WARN"
    state["acceptance_review_safe"] = not unknown and blockers == 0 and context_state == "disabled"
    return state


def _baseline_state(*, unknown: bool = False, blockers: int = 0, context_state: str = "disabled") -> dict[str, object]:
    state = _acceptance_state(unknown=unknown, blockers=blockers, context_state=context_state)
    state.update(
        {
            "baseline_readiness": "BLOCKED" if unknown or blockers else "WARN",
            "baseline_review_safe": not unknown and blockers == 0 and context_state == "disabled",
            "accepted_baseline": "Snapshot Baseline Registry v1",
            "test_baseline": "671 tests OK (Architect Ledger; not re-run by this command)",
            "latest_snapshot": {
                "filename": "snapshot.json",
                "generated_at": "2026-07-01T06:00:00+00:00",
                "status": "WARN",
            },
            "latest_diff": {
                "filename": "diff.json",
                "generated_at": "2026-07-01T06:05:00+00:00",
                "status": "NO STRUCTURAL CHANGES",
            },
        }
    )
    return state


def _closure_state(*, unknown: bool = False, blockers: int = 0, context_state: str = "disabled") -> dict[str, object]:
    state = _baseline_state(unknown=unknown, blockers=blockers, context_state=context_state)
    state.update(
        {
            "closure_readiness": "BLOCKED" if unknown or blockers else "WARN",
            "closure_handoff_safe": not unknown and blockers == 0 and context_state == "disabled",
            "operating_layers": [
                "Operating Loop v2.6 / Acceptance Review Ritual v1",
                "Snapshot Baseline Registry v1",
            ],
        }
    )
    return state


def _memory_card_state(*, unknown: bool = False, blockers: int = 0, context_state: str = "disabled") -> dict[str, object]:
    state = _closure_state(unknown=unknown, blockers=blockers, context_state=context_state)
    state.update(
        {
            "memory_card_readiness": "BLOCKED" if unknown or blockers else "WARN",
            "memory_card_generation_safe": not unknown and blockers == 0 and context_state == "disabled",
            "identity": {
                "status": "OK",
                "name": "Proto-Mind",
                "role": "local-first cognitive assistant",
                "active_values": 5,
                "active_boundaries": 5,
            },
        }
    )
    return state


def _capability_state(*, unknown: bool = False, blockers: int = 0, context_state: str = "disabled") -> dict[str, object]:
    state = _memory_card_state(unknown=unknown, blockers=blockers, context_state=context_state)
    state.update(
        {
            "capability_readiness": "BLOCKED" if unknown or blockers else "WARN",
            "capability_generation_safe": not unknown and blockers == 0 and context_state == "disabled",
            "category_counts": {},
            "family_count": 41,
        }
    )
    return state


def _plan_state(*, unknown: bool = False, blockers: int = 0, context_state: str = "disabled") -> dict[str, object]:
    state = _capability_state(unknown=unknown, blockers=blockers, context_state=context_state)
    state.update(
        {
            "plan_readiness": "BLOCKED" if unknown or blockers else "WARN",
            "dry_run_planning_safe": not unknown and blockers == 0 and context_state == "disabled",
        }
    )
    return state


def _confirmation_state(*, unknown: bool = False, blockers: int = 0, context_state: str = "disabled") -> dict[str, object]:
    state = _plan_state(unknown=unknown, blockers=blockers, context_state=context_state)
    state.update(
        {
            "confirmation_readiness": "BLOCKED" if unknown or blockers else "WARN",
            "confirmation_policy_generation_safe": not unknown and blockers == 0 and context_state == "disabled",
        }
    )
    return state


def _sandbox_state(*, unknown: bool = False, blockers: int = 0, context_state: str = "disabled") -> dict[str, object]:
    state = _confirmation_state(unknown=unknown, blockers=blockers, context_state=context_state)
    state.update(
        {
            "sandbox_readiness": "BLOCKED" if unknown or blockers else "WARN",
            "sandbox_blueprint_generation_safe": not unknown and blockers == 0 and context_state == "disabled",
        }
    )
    return state


def _runner_state(*, unknown: bool = False, blockers: int = 0, context_state: str = "disabled") -> dict[str, object]:
    state = _sandbox_state(unknown=unknown, blockers=blockers, context_state=context_state)
    state.update(
        {
            "runner_readiness": "BLOCKED" if unknown or blockers else "WARN",
            "noop_runner_contract_generation_safe": not unknown and blockers == 0 and context_state == "disabled",
            "execution_enabled": False,
            "active_allowlist": False,
        }
    )
    return state


def _runner_candidates_state(*, unknown: bool = False, blockers: int = 0, context_state: str = "disabled") -> dict[str, object]:
    state = _runner_state(unknown=unknown, blockers=blockers, context_state=context_state)
    state.update(
        {
            "candidate_set_readiness": "BLOCKED" if unknown or blockers else "WARN",
            "candidate_set_generation_safe": not unknown and blockers == 0 and context_state == "disabled",
            "active_allowlist": False,
            "execution_enabled": False,
        }
    )
    return state


def _activation_state(*, unknown: bool = False, blockers: int = 0, context_state: str = "disabled") -> dict[str, object]:
    state = _runner_candidates_state(unknown=unknown, blockers=blockers, context_state=context_state)
    state.update(
        {
            "activation_readiness": "BLOCKED" if unknown or blockers else "WARN",
            "activation_design_may_be_considered": not unknown and blockers == 0 and context_state == "disabled",
            "active_allowlist": False,
            "execution_enabled": False,
            "approval_capture": False,
            "authorization_engine": False,
            "execution_engine": False,
            "actual_execution_blocked": True,
        }
    )
    return state


def _runner_mvp_state(*, unknown: bool = False, blockers: int = 0, context_state: str = "disabled") -> dict[str, object]:
    state = _activation_state(unknown=unknown, blockers=blockers, context_state=context_state)
    state.update(
        {
            "mvp_design_lock_readiness": "BLOCKED" if unknown or blockers else "WARN",
            "mvp_design_lock_safe": not unknown and blockers == 0 and context_state == "disabled",
            "design_lock_status": "LOCKED_DESIGN_ONLY",
            "active_allowlist": False,
            "execution_enabled": False,
            "execution_engine": False,
        }
    )
    return state


def _runner_exec_state(*, unknown: bool = False, blockers: int = 0, context_state: str = "disabled") -> dict[str, object]:
    state = _runner_mvp_state(unknown=unknown, blockers=blockers, context_state=context_state)
    enabled = blockers == 0 and context_state == "disabled"
    state.update(
        {
            "runner_exec_safety_state": "BLOCKED" if not enabled else "WARN",
            "command_safety": {
                "/warnings unknown": True,
                "/daily doctor": True,
                "/exports doctor": True,
                "/capabilities safety": True,
            },
            "pilot_command_safe": True,
            "daily_doctor_command_safe": True,
            "exports_doctor_command_safe": True,
            "capabilities_safety_command_safe": True,
            "execution_enabled": enabled,
            "active_allowlist": ("/warnings unknown", "/daily doctor", "/exports doctor", "/capabilities safety"),
        }
    )
    return state


def _runner_exec_executors(
    *,
    warnings: object | None = None,
    daily: object | None = None,
    exports: object | None = None,
    capabilities: object | None = None,
) -> dict[str, object]:
    return {
        "/warnings unknown": warnings or (lambda: "warnings output"),
        "/daily doctor": daily or (lambda: "daily doctor output"),
        "/exports doctor": exports or (lambda: "Export Retention Doctor\nStatus: OK"),
        "/capabilities safety": capabilities
        or (
            lambda: "Command Capability Safety Classification\n- registered read-only/mutates=none commands: 271\n- auto_allowed: 270\n- confirmation_required: 86\n- operator_only: 4"
        ),
    }


def reflect_for_test(
    response: str,
    *,
    retrieved_memory: list[MemoryRecord] | None = None,
    working_memory: list[MemoryRecord] | None = None,
    persistent_memory: list[MemoryRecord] | None = None,
    observer_state: object | None = None,
):
    state = observer_state or Observer().analyze("What storage system are we using now?")
    return SelfReflector().reflect(
        user_input="What storage system are we using now?",
        response=response,
        observer_state=state,
        retrieved_memory=retrieved_memory or [],
        retrieval_trace=None,
        memory_summary=InteractionSummary(
            memory_type="insight",
            content="",
            importance=0.0,
            tags=[],
            should_store=False,
        ),
        working_memory=working_memory or [],
        persistent_memory=persistent_memory or [],
    )


def audit_for_test(
    response: str,
    *,
    user_input: str = "What storage system are we using now?",
    retrieved_memory: list[MemoryRecord] | None = None,
    working_memory: list[MemoryRecord] | None = None,
    persistent_memory: list[MemoryRecord] | None = None,
    observer_state: object | None = None,
):
    state = observer_state or Observer().analyze(user_input)
    return GroundingAuditor().audit(
        user_input=user_input,
        response=response,
        observer_state=state,
        retrieved_memory=retrieved_memory or [],
        retrieval_trace=None,
        working_memory=working_memory or [],
        persistent_memory=persistent_memory or [],
    )


class ScriptedReasoner(BaseReasoner):
    backend_name = "scripted"

    def __init__(self, responses: list[str]) -> None:
        self.responses = responses
        self.seen_correction_hints: list[list[str]] = []

    def respond(
        self,
        user_input: str,
        retrieved_memory: list[MemoryRecord],
        observer_state,
        correction_hints: list[str] | None = None,
    ) -> str:
        self.seen_correction_hints.append(list(correction_hints or []))
        if self.responses:
            return self.responses.pop(0)
        return "SQLite is current."
