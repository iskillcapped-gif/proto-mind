from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import json
from typing import Any

from proto_mind.command_registry import COMMAND_REGISTRY
from proto_mind.experience_learning_bridge import (
    CognitiveLearningBridgeError,
    CognitiveLearningPreviewCandidate,
    OperatorReviewedLearningBridge,
)
from proto_mind.experience_learning_decision import (
    OperatorReviewedLearningDecisionSession,
    learning_candidate_hash,
)
from proto_mind.experience_learning_eligibility import LearningEligibilityRequest
from proto_mind.experience_learning_proposal import (
    LEARNING_PROPOSAL_SCHEMAS,
    LearningPromotionProposalBuilder,
    LearningPromotionProposalReceipt,
    LearningProposalError,
    OperatorReviewedLearningProposalSession,
)
from proto_mind.memory_store import MemoryStore
from proto_mind.skill_library import SkillLibrary


LEARNING_APPLY_READINESS_VERSION = 1
LEARNING_APPLY_READINESS_MODE = "read_only_current_evidence_revalidation"
LEARNING_APPLY_COMMAND_PREFIX = "/experience learning apply"
LEARNING_APPLY_ENGINE_INSTALLED = False


@dataclass(frozen=True)
class LearningApplyReadinessReport:
    status: str
    proposal_id: str
    candidate_id: str
    target: str
    target_schema: str
    stored_proposal_hash: str
    current_proposal_hash: str
    stored_scope_hash: str
    current_scope_hash: str
    checks: dict[str, bool]
    issues: list[str]
    warnings: list[str]
    ready_for_design_review: bool
    apply_engine_installed: bool = LEARNING_APPLY_ENGINE_INSTALLED
    executable: bool = False
    apply_performed: bool = False
    mutation_performed: bool = False
    persistence_performed: bool = False


@dataclass(frozen=True)
class LearningApplyReadinessDoctorReport:
    status: str
    proposal_count: int
    ready_count: int
    not_ready_count: int
    error_count: int
    issues: list[str]
    warnings: list[str]


class LearningPromotionApplyReadiness:
    """Revalidates one proposal against current explicit-ID evidence without applying it."""

    def __init__(self, *, memory_store: MemoryStore, skill_library: SkillLibrary) -> None:
        self.builder = LearningPromotionProposalBuilder(
            memory_store=memory_store,
            skill_library=skill_library,
        )

    def review(
        self,
        receipt: LearningPromotionProposalReceipt,
        *,
        candidates: dict[str, CognitiveLearningPreviewCandidate],
        decisions: OperatorReviewedLearningDecisionSession,
    ) -> LearningApplyReadinessReport:
        checks = {
            "proposal_receipt_safe": _receipt_has_safe_boundary(receipt),
            "candidate_present": False,
            "candidate_hash_matches": False,
            "accepted_decision_present": False,
            "decision_id_matches": False,
            "selected_scope_matches": False,
            "eligibility_receipt_matches": False,
            "eligibility_hash_matches": False,
            "target_schema_matches": False,
            "payload_matches": False,
            "proposal_hash_matches": False,
            "proposal_id_matches": False,
            "apply_engine_absent": not LEARNING_APPLY_ENGINE_INSTALLED,
        }
        issues: list[str] = []
        warnings = [
            "Global novelty was not checked; readiness is limited to current explicit reference IDs.",
            "No apply engine is installed; READY means ready for design review only.",
        ]
        if not checks["proposal_receipt_safe"]:
            issues.append("Proposal receipt claims a forbidden effect, readiness state, or scope.")

        candidate = candidates.get(receipt.candidate_id)
        checks["candidate_present"] = candidate is not None
        if candidate is None:
            issues.append("Proposal candidate is absent from current process evidence.")
        else:
            checks["candidate_hash_matches"] = (
                receipt.candidate_hash == learning_candidate_hash(candidate)
            )
            if not checks["candidate_hash_matches"]:
                issues.append("Current candidate hash differs from the proposal receipt.")

        decision = decisions.get(receipt.candidate_id)
        checks["accepted_decision_present"] = (
            decision is not None and decision.decision == "accepted"
        )
        if not checks["accepted_decision_present"]:
            issues.append("Current accepted candidate decision is missing.")
        else:
            checks["decision_id_matches"] = receipt.decision_id == decision.id
            if not checks["decision_id_matches"]:
                issues.append("Current accepted decision id differs from the proposal receipt.")

        current_proposal_hash = ""
        current_scope_hash = ""
        revalidation_error = ""
        if candidate is not None and decision is not None and decision.decision == "accepted":
            request = LearningEligibilityRequest(
                candidate_id=receipt.candidate_id,
                target=receipt.target,
                memory_ids=list(receipt.requested_memory_ids),
                skill_ids=list(receipt.requested_skill_ids),
            )
            try:
                current = self.builder.build(candidate, decision, request)
            except (LearningProposalError, KeyError, TypeError, ValueError) as exc:
                revalidation_error = str(exc)
                issues.append(f"Current proposal revalidation failed: {exc}")
            else:
                current_proposal_hash = current.proposal_hash
                current_scope_hash = current.selected_scope_hash
                checks["selected_scope_matches"] = (
                    receipt.selected_scope_hash == current.selected_scope_hash
                )
                checks["eligibility_receipt_matches"] = (
                    receipt.eligibility_receipt_id == current.eligibility_receipt_id
                )
                checks["eligibility_hash_matches"] = (
                    receipt.eligibility_hash == current.eligibility_hash
                )
                checks["target_schema_matches"] = (
                    receipt.target_schema == current.target_schema
                    and receipt.target_schema == LEARNING_PROPOSAL_SCHEMAS.get(receipt.target)
                )
                checks["payload_matches"] = receipt.proposed_payload == current.proposed_payload
                checks["proposal_hash_matches"] = (
                    receipt.proposal_hash == current.proposal_hash
                )
                checks["proposal_id_matches"] = (
                    receipt.id == f"learnprop_{receipt.proposal_hash[:16]}"
                )
                for name, message in (
                    ("selected_scope_matches", "Selected reference snapshot has drifted."),
                    ("eligibility_receipt_matches", "Eligibility receipt identity has drifted."),
                    ("eligibility_hash_matches", "Eligibility evidence hash has drifted."),
                    ("target_schema_matches", "Target schema no longer matches the fixed contract."),
                    ("payload_matches", "Proposed target payload has drifted."),
                    ("proposal_hash_matches", "Proposal digest no longer matches current evidence."),
                    ("proposal_id_matches", "Proposal id no longer matches its stored digest."),
                ):
                    if not checks[name]:
                        issues.append(message)

        ready = all(checks.values()) and not issues
        status = "READY FOR APPLY DESIGN REVIEW" if ready else "NOT READY"
        if not checks["proposal_receipt_safe"] or (
            revalidation_error and "unreadable" in revalidation_error.casefold()
        ):
            status = "ERROR"
        return LearningApplyReadinessReport(
            status=status,
            proposal_id=receipt.id,
            candidate_id=receipt.candidate_id,
            target=receipt.target,
            target_schema=receipt.target_schema,
            stored_proposal_hash=receipt.proposal_hash,
            current_proposal_hash=current_proposal_hash,
            stored_scope_hash=receipt.selected_scope_hash,
            current_scope_hash=current_scope_hash,
            checks=checks,
            issues=issues,
            warnings=warnings,
            ready_for_design_review=ready,
        )

    def doctor(
        self,
        proposals: OperatorReviewedLearningProposalSession,
        *,
        candidates: dict[str, CognitiveLearningPreviewCandidate],
        decisions: OperatorReviewedLearningDecisionSession,
    ) -> LearningApplyReadinessDoctorReport:
        issues: list[str] = []
        warnings: list[str] = []
        reports: list[LearningApplyReadinessReport] = []
        for item in proposals.snapshot():
            receipt = proposals.get(str(item.get("id") or ""))
            if receipt is None:
                issues.append("Proposal snapshot contains an unresolvable receipt.")
                continue
            report = self.review(receipt, candidates=candidates, decisions=decisions)
            reports.append(report)
            if report.status == "ERROR":
                issues.append(f"Proposal {receipt.id} revalidation returned ERROR.")
            elif report.status != "READY FOR APPLY DESIGN REVIEW":
                warnings.append(f"Proposal {receipt.id} is not ready: {'; '.join(report.issues)}")

        if any(spec.prefix == LEARNING_APPLY_COMMAND_PREFIX for spec in COMMAND_REGISTRY):
            issues.append("An execution-capable learning apply command is unexpectedly registered.")
        if LEARNING_APPLY_ENGINE_INSTALLED:
            issues.append("Learning apply engine must remain absent in readiness v1.")
        counts = Counter(report.status for report in reports)
        status = "ERROR" if issues else "WARN" if warnings else "OK"
        return LearningApplyReadinessDoctorReport(
            status=status,
            proposal_count=len(reports),
            ready_count=counts["READY FOR APPLY DESIGN REVIEW"],
            not_ready_count=counts["NOT READY"],
            error_count=counts["ERROR"],
            issues=issues,
            warnings=warnings,
        )


def format_learning_apply_readiness_command(
    command: str,
    *,
    bridge: OperatorReviewedLearningBridge,
    decisions: OperatorReviewedLearningDecisionSession,
    proposals: OperatorReviewedLearningProposalSession,
    memory_store: MemoryStore | None,
    skill_library: SkillLibrary,
) -> str | None:
    raw = command.strip()
    normalized = " ".join(raw.lower().split())
    handled = (
        "/experience learning apply-readiness",
        "/experience learning apply-plan",
        "/experience learning apply-doctor",
    )
    if not any(normalized == prefix or normalized.startswith(prefix + " ") for prefix in handled):
        return None
    if memory_store is None:
        return _error_output("MemoryStore is unavailable from the shared handler.")
    candidates, error = _candidate_map(bridge)
    if error:
        return error
    reviewer = LearningPromotionApplyReadiness(
        memory_store=memory_store,
        skill_library=skill_library,
    )
    if normalized == "/experience learning apply-doctor":
        return format_learning_apply_doctor(
            reviewer.doctor(proposals, candidates=candidates, decisions=decisions)
        )
    if normalized == "/experience learning apply-readiness" or normalized == (
        "/experience learning apply-plan"
    ):
        return (
            "Usage: /experience learning apply-readiness <proposal_id|candidate_id>"
            if normalized.endswith("apply-readiness")
            else "Usage: /experience learning apply-plan <proposal_id|candidate_id>"
        )
    prefix = (
        "/experience learning apply-readiness"
        if normalized.startswith("/experience learning apply-readiness ")
        else "/experience learning apply-plan"
    )
    identifier = raw[len(prefix) :].strip()
    receipt = proposals.get(identifier)
    if receipt is None:
        return _not_found(identifier)
    report = reviewer.review(receipt, candidates=candidates, decisions=decisions)
    return (
        format_learning_apply_readiness(report)
        if prefix.endswith("apply-readiness")
        else format_learning_apply_plan(report, receipt)
    )


def format_learning_apply_readiness(report: LearningApplyReadinessReport) -> str:
    lines = [
        "Proto-Mind Learning Promotion Apply Readiness v1",
        f"Status: {report.status}",
        f"proposal_id: {report.proposal_id}",
        f"candidate_id: {report.candidate_id}",
        f"target: {report.target}",
        f"target_schema: {report.target_schema}",
        f"stored_proposal_hash: {report.stored_proposal_hash}",
        f"current_proposal_hash: {report.current_proposal_hash or 'unavailable'}",
        f"stored_scope_hash: {report.stored_scope_hash}",
        f"current_scope_hash: {report.current_scope_hash or 'unavailable'}",
        "Checks:",
    ]
    lines.extend(f"- {name}: {str(value).lower()}" for name, value in report.checks.items())
    lines.extend(f"- ERROR: {issue}" for issue in report.issues)
    lines.extend(f"- WARN: {warning}" for warning in report.warnings)
    lines.extend(_readiness_boundary())
    return "\n".join(lines)


def format_learning_apply_plan(
    report: LearningApplyReadinessReport,
    receipt: LearningPromotionProposalReceipt,
) -> str:
    lines = [
        "Proto-Mind Learning Promotion Future Apply Plan v1",
        f"Status: {'DESIGN REVIEW ONLY' if report.ready_for_design_review else 'NOT READY'}",
        f"proposal_id: {receipt.id}",
        f"target: {receipt.target}",
        f"target_schema: {receipt.target_schema}",
        f"exact_payload: {_compact_payload(receipt.proposed_payload)}",
        "Future operation:",
        f"- Create exactly one {receipt.target} record from this immutable payload.",
        "- No implementation or executable command exists in v3.3g.",
        "Required future receipt fields:",
        "- apply_id, applied_at, proposal_id, proposal_hash, target_schema",
        "- before_store_sha256, after_store_sha256, created_record_id",
        "- exact_payload_hash, result_summary, target_execution_performed",
        "Required future safeguards:",
        "- Rule 0 checkpoint, current readiness revalidation, exact one-shot confirmation",
        "- atomic target-store write, run-once guard, post-write record verification",
        "- no shell, no arbitrary slash dispatch, no batch apply, no cross-store mutation",
        "Rollback preview:",
        f"- {_rollback_suggestion(receipt.target)}",
    ]
    if not report.ready_for_design_review:
        lines.extend(f"- BLOCKER: {issue}" for issue in report.issues)
    lines.extend(_readiness_boundary())
    return "\n".join(lines)


def format_learning_apply_doctor(report: LearningApplyReadinessDoctorReport) -> str:
    lines = [
        "Proto-Mind Learning Promotion Apply Readiness Doctor v1",
        f"Status: {report.status}",
        f"proposals: {report.proposal_count}",
        f"ready_for_design_review: {report.ready_count}",
        f"not_ready: {report.not_ready_count}",
        f"errors: {report.error_count}",
        f"apply_engine_installed: {str(LEARNING_APPLY_ENGINE_INSTALLED).lower()}",
    ]
    lines.extend(f"- ERROR: {issue}" for issue in report.issues)
    lines.extend(f"- WARN: {warning}" for warning in report.warnings)
    if not report.issues and not report.warnings:
        lines.append("- Current proposals revalidate and no apply engine or exact apply command exists.")
    lines.extend(_readiness_boundary())
    return "\n".join(lines)


def _receipt_has_safe_boundary(receipt: LearningPromotionProposalReceipt) -> bool:
    return (
        receipt.scope_limited
        and not receipt.global_duplicate_check_performed
        and not receipt.future_apply_ready
        and not receipt.executable
        and not receipt.promotion_performed
        and not receipt.apply_performed
        and not receipt.persistence_performed
    )


def _candidate_map(
    bridge: OperatorReviewedLearningBridge,
) -> tuple[dict[str, CognitiveLearningPreviewCandidate], str]:
    try:
        reviews = bridge.review()
    except CognitiveLearningBridgeError as exc:
        return {}, _error_output(str(exc))
    return {
        candidate.id: candidate
        for review in reviews
        for candidate in review.candidates
    }, ""


def _rollback_suggestion(target: str) -> str:
    if target == "memory":
        return "If a future receipt records created_memory_id: /memory forget <created_memory_id>"
    if target == "skill":
        return "If a future receipt records created_skill_id: /skills archive <created_skill_id>"
    return "Manual review required; target has no recognized rollback template."


def _compact_payload(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _not_found(identifier: str) -> str:
    return "\n".join(
        [
            "Proto-Mind Learning Promotion Apply Readiness v1",
            "Status: NOT FOUND",
            f"- Proposal or candidate {identifier!r} is absent from process memory.",
            *_readiness_boundary(),
        ]
    )


def _error_output(message: str) -> str:
    return "\n".join(
        [
            "Proto-Mind Learning Promotion Apply Readiness v1",
            "Status: ERROR",
            f"- {message}",
            *_readiness_boundary(),
        ]
    )


def _readiness_boundary() -> list[str]:
    return [
        "mode: apply_design_review_only",
        "apply_engine_installed: false",
        "executable: false",
        "apply_performed: false",
        "mutation_performed: false",
        "persistence_performed: false",
        "- Read-only revalidation only; no target command or rollback command executed.",
    ]
