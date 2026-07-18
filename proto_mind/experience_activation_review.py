from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from proto_mind.cognitive_soak import run_continuity_soak
from proto_mind.command_registry import COMMAND_REGISTRY
from proto_mind.context_pack import ContextInjectionSettingsStore
from proto_mind.experience_capture import LIVE_CAPTURE_HOOK_INSTALLED, ExperienceCaptureGate
from proto_mind.experience_capture_design import (
    SessionCaptureDesignReview,
    run_session_capture_design_benchmark,
)
from proto_mind.experience_capture_soak import run_experience_capture_soak
from proto_mind.experience_consent import run_session_consent_benchmark
from proto_mind.experience_ledger import (
    LIVE_EXPERIENCE_PERSISTENCE_ENABLED,
    format_experience_persistence_policy,
)
from proto_mind.experience_privacy import run_experience_privacy_benchmark


EXPERIENCE_ACTIVATION_REVIEW_VERSION = 1
EXPERIENCE_ACTIVATION_DECISION = "KEEP_DISABLED"
EXPERIENCE_NEXT_STAGE = "SUPERVISED_IN_MEMORY_PILOT_AVAILABLE_PERSISTENCE_DISABLED"


@dataclass(frozen=True)
class ActivationReadinessEvidence:
    name: str
    status: str
    ready: bool
    summary: str
    required: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ExperienceActivationReadinessReport:
    status: str
    decision: str
    evidence_ready: bool
    next_stage: str
    runtime_activation_allowed: bool
    implementation_authorized: bool
    context_injection_enabled: bool
    effective_capture_enabled: bool
    live_writer_installed: bool
    live_persistence_enabled: bool
    settings_exists: bool
    live_ledger_exists: bool
    evidence: list[ActivationReadinessEvidence]
    blockers: list[str]
    notes: list[str]
    mutation_performed: bool = False


@dataclass(frozen=True)
class ExperienceActivationDoctorReport:
    status: str
    evidence_count: int
    ready_count: int
    blocker_count: int
    issues: list[str]
    warnings: list[str]


@dataclass(frozen=True)
class ExperienceActivationBenchmarkReport:
    status: str
    evidence_count: int
    ready_count: int
    files_created: int
    checks: dict[str, bool]
    failed_checks: list[str]
    boundary: str


class ExperienceCaptureActivationReadinessReview:
    """Read-only evidence aggregator; it cannot activate or implement capture."""

    def __init__(self, project_root: Path) -> None:
        self.project_root = Path(project_root)

    def evaluate(self) -> ExperienceActivationReadinessReport:
        gate = ExperienceCaptureGate(self.project_root).status()
        design_review = SessionCaptureDesignReview(self.project_root)
        design_doctor = design_review.doctor()
        design_benchmark = run_session_capture_design_benchmark()
        consent_benchmark = run_session_consent_benchmark()
        privacy_benchmark = run_experience_privacy_benchmark()
        growth_soak = run_experience_capture_soak()
        persistence_soak = run_continuity_soak(persist_experience_preview=True)
        context_settings = ContextInjectionSettingsStore.from_project_root(
            self.project_root
        ).read_settings(initialize=False)
        context_enabled = context_settings.get("enabled") is True
        persistence_policy = format_experience_persistence_policy()

        evidence = [
            self._evidence(
                "design_lock",
                design_doctor.status == "OK"
                and design_benchmark.status == "OK"
                and not design_review.policy.implementation_authorized,
                "Consent, scope, privacy, retention, and failure-isolation design is locked.",
            ),
            self._evidence(
                "session_consent_spec",
                consent_benchmark.status == "OK"
                and consent_benchmark.refusal_case_count == 14
                and consent_benchmark.files_created == 0,
                "Exact session consent, bypass, stop, failure, and expiry cases pass.",
            ),
            self._evidence(
                "privacy_redaction",
                privacy_benchmark.status == "OK"
                and privacy_benchmark.sensitive_case_count == 12
                and privacy_benchmark.files_created == 0,
                "Credential-like previews redact before truncation with benign controls.",
            ),
            self._evidence(
                "bounded_growth",
                growth_soak.status == "OK"
                and growth_soak.event_count <= growth_soak.max_events
                and growth_soak.byte_count <= growth_soak.max_bytes
                and growth_soak.files_created == 0,
                "Consent/redaction soak remains inside per-turn, event, and byte limits.",
            ),
            self._evidence(
                "temporary_integrity",
                persistence_soak["status"] == "OK"
                and persistence_soak["experience_store_doctor_status"] == "OK"
                and persistence_soak["experience_store_hash_verified"]
                == persistence_soak["experience_events"],
                "Isolated temporary preview verifies every contiguous SHA-chain envelope.",
            ),
            self._evidence(
                "live_gate_disabled",
                gate.status == "OK"
                and not gate.enabled_requested
                and not gate.effective_enabled
                and not LIVE_CAPTURE_HOOK_INSTALLED
                and not LIVE_EXPERIENCE_PERSISTENCE_ENABLED,
                "Live gate, writer hook, and persistence policy remain disabled.",
            ),
            self._evidence(
                "live_paths_absent",
                not gate.settings_exists and not gate.live_ledger_exists,
                "No capture config or live Experience Ledger exists.",
            ),
            self._evidence(
                "context_injection_disabled",
                not context_enabled,
                "Context Injection remains disabled for the readiness baseline.",
            ),
            self._evidence(
                "persistence_policy_preview_only",
                "Status: PREVIEW_ONLY" in persistence_policy
                and "live_persistence_enabled: false" in persistence_policy,
                "Persistence policy remains temporary-preview-only and refuses live paths.",
            ),
            self._evidence(
                "persistent_command_surface_absent",
                not any(
                    item.prefix.startswith(
                        (
                            "/experience persist",
                            "/experience export",
                            "/experience apply",
                            "/experience promote",
                            "/experience backfill",
                        )
                    )
                    for item in COMMAND_REGISTRY
                ),
                "No Experience persistence, export, apply, promotion, or backfill command exists.",
            ),
        ]
        blockers = [item.name for item in evidence if item.required and not item.ready]
        evidence_ready = not blockers
        return ExperienceActivationReadinessReport(
            status="OK" if evidence_ready else "BLOCKED",
            decision=EXPERIENCE_ACTIVATION_DECISION,
            evidence_ready=evidence_ready,
            next_stage=EXPERIENCE_NEXT_STAGE if evidence_ready else "BLOCKED_BY_READINESS_EVIDENCE",
            runtime_activation_allowed=False,
            implementation_authorized=False,
            context_injection_enabled=context_enabled,
            effective_capture_enabled=gate.effective_enabled,
            live_writer_installed=LIVE_CAPTURE_HOOK_INSTALLED,
            live_persistence_enabled=LIVE_EXPERIENCE_PERSISTENCE_ENABLED,
            settings_exists=gate.settings_exists,
            live_ledger_exists=gate.live_ledger_exists,
            evidence=evidence,
            blockers=blockers,
            notes=[
                "Evidence readiness does not authorize persistent runtime activation.",
                "A separate explicit-consent, process-memory-only pilot is available.",
                "No persistence hook, writer, config, or live ledger was created by this review.",
            ],
        )

    def doctor(self) -> ExperienceActivationDoctorReport:
        report = self.evaluate()
        issues: list[str] = []
        warnings: list[str] = []
        ready_count = sum(item.ready for item in report.evidence)

        if report.runtime_activation_allowed or report.implementation_authorized:
            issues.append("Readiness review unexpectedly authorizes implementation or activation.")
        if report.decision != EXPERIENCE_ACTIVATION_DECISION:
            issues.append("Readiness decision must remain KEEP_DISABLED.")
        if report.effective_capture_enabled or report.live_writer_installed:
            issues.append("A live capture surface is unexpectedly active.")
        if report.live_persistence_enabled:
            issues.append("Live Experience persistence is unexpectedly enabled.")
        if report.blockers:
            warnings.append("Blocked readiness evidence: " + ", ".join(report.blockers) + ".")

        forbidden_methods = {
            "activate",
            "append",
            "capture",
            "enable",
            "execute",
            "persist",
            "start",
            "write",
        }
        exposed = sorted(forbidden_methods.intersection(dir(self)))
        if exposed:
            issues.append("Review exposes forbidden methods: " + ", ".join(exposed) + ".")

        status = "ERROR" if issues else "WARN" if warnings else "OK"
        return ExperienceActivationDoctorReport(
            status=status,
            evidence_count=len(report.evidence),
            ready_count=ready_count,
            blocker_count=len(report.blockers),
            issues=issues,
            warnings=warnings,
        )

    @staticmethod
    def _evidence(name: str, ready: bool, summary: str) -> ActivationReadinessEvidence:
        return ActivationReadinessEvidence(
            name=name,
            status="READY" if ready else "BLOCKED",
            ready=ready,
            summary=summary,
        )


def format_experience_activation_status(
    review: ExperienceCaptureActivationReadinessReview,
) -> str:
    report = review.evaluate()
    return "\n".join(
        [
            "Proto-Mind Experience Capture Activation Readiness v1",
            f"Status: {report.status}",
            f"decision: {report.decision}",
            f"evidence_ready: {str(report.evidence_ready).lower()}",
            f"next_stage: {report.next_stage}",
            f"runtime_activation_allowed: {str(report.runtime_activation_allowed).lower()}",
            f"implementation_authorized: {str(report.implementation_authorized).lower()}",
            f"context_injection_enabled: {str(report.context_injection_enabled).lower()}",
            f"effective_capture_enabled: {str(report.effective_capture_enabled).lower()}",
            f"blockers: {len(report.blockers)}",
        ]
    )


def format_experience_activation_evidence(
    review: ExperienceCaptureActivationReadinessReview,
) -> str:
    report = review.evaluate()
    lines = [
        "Proto-Mind Experience Activation Evidence Matrix v1",
        f"Status: {report.status}",
        f"decision: {report.decision}",
        "Evidence:",
    ]
    lines.extend(
        f"- [{item.status}] {item.name}: {item.summary}" for item in report.evidence
    )
    lines.append("Notes:")
    lines.extend(f"- {note}" for note in report.notes)
    return "\n".join(lines)


def format_experience_activation_doctor(
    review: ExperienceCaptureActivationReadinessReview,
) -> str:
    report = review.doctor()
    lines = [
        "Proto-Mind Experience Activation Readiness Doctor v1",
        f"Status: {report.status}",
        f"evidence_ready: {report.ready_count}/{report.evidence_count}",
        f"blockers: {report.blocker_count}",
    ]
    lines.extend(f"- ERROR: {issue}" for issue in report.issues)
    lines.extend(f"- WARN: {warning}" for warning in report.warnings)
    if not report.issues and not report.warnings:
        lines.append("- Readiness evidence is complete while runtime activation remains denied.")
    lines.append("- Read-only review: no activation, implementation, capture, or persistence occurred.")
    return "\n".join(lines)


def run_experience_activation_benchmark() -> ExperienceActivationBenchmarkReport:
    with TemporaryDirectory(prefix="proto-mind-experience-activation-review-") as temp_dir:
        root = Path(temp_dir)
        before = list(root.rglob("*"))
        review = ExperienceCaptureActivationReadinessReview(root)
        report = review.evaluate()
        doctor = review.doctor()
        status_output = format_experience_activation_status(review)
        evidence_output = format_experience_activation_evidence(review)
        doctor_output = format_experience_activation_doctor(review)
        after = list(root.rglob("*"))

    checks = {
        "report_ok": report.status == "OK",
        "all_evidence_ready": report.evidence_ready
        and all(item.ready for item in report.evidence),
        "decision_keeps_capture_disabled": report.decision == EXPERIENCE_ACTIVATION_DECISION,
        "next_stage_is_supervised_memory_pilot": report.next_stage == EXPERIENCE_NEXT_STAGE,
        "runtime_activation_denied": not report.runtime_activation_allowed,
        "implementation_not_authorized": not report.implementation_authorized,
        "context_injection_disabled": not report.context_injection_enabled,
        "live_surfaces_absent": not report.effective_capture_enabled
        and not report.live_writer_installed
        and not report.live_persistence_enabled
        and not report.settings_exists
        and not report.live_ledger_exists,
        "doctor_ok": doctor.status == "OK" and doctor.blocker_count == 0,
        "reports_distinguish_readiness_from_activation": "evidence_ready: true" in status_output
        and "runtime_activation_allowed: false" in status_output
        and "[READY] bounded_growth" in evidence_output
        and "no activation" in doctor_output.lower(),
        "no_files_created": before == after,
    }
    failed_checks = [name for name, passed in checks.items() if not passed]
    return ExperienceActivationBenchmarkReport(
        status="OK" if not failed_checks else "ERROR",
        evidence_count=len(report.evidence),
        ready_count=sum(item.ready for item in report.evidence),
        files_created=len(after) - len(before),
        checks=checks,
        failed_checks=failed_checks,
        boundary=(
            "Read-only readiness aggregation only; no activation, capture, consent storage, hook, "
            "writer, config, live ledger, persistence, persistent command, LLM, export, Context Injection "
            "change, domain mutation, or external action."
        ),
    )


def format_experience_activation_benchmark(
    report: ExperienceActivationBenchmarkReport | None = None,
) -> str:
    report = report or run_experience_activation_benchmark()
    lines = [
        "Proto-Mind Experience Activation Readiness Benchmark v1",
        f"Status: {report.status}",
        f"evidence_ready: {report.ready_count}/{report.evidence_count}",
        f"files_created: {report.files_created}",
        "Checks:",
    ]
    lines.extend(f"- [{'PASS' if passed else 'FAIL'}] {name}" for name, passed in report.checks.items())
    lines.extend(["Boundary:", f"- {report.boundary}"])
    return "\n".join(lines)


def main() -> int:
    with TemporaryDirectory(prefix="proto-mind-experience-activation-main-") as temp_dir:
        review = ExperienceCaptureActivationReadinessReview(Path(temp_dir))
        print(format_experience_activation_status(review))
        print()
        print(format_experience_activation_evidence(review))
        print()
        print(format_experience_activation_doctor(review))
    print()
    benchmark = run_experience_activation_benchmark()
    print(format_experience_activation_benchmark(benchmark))
    return 0 if benchmark.status == "OK" else 1


if __name__ == "__main__":
    raise SystemExit(main())
