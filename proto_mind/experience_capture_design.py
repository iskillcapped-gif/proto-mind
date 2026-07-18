from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from proto_mind.experience_capture import (
    LIVE_CAPTURE_HOOK_INSTALLED,
    ExperienceCaptureGate,
)
from proto_mind.experience_ledger import (
    EXPERIENCE_PREVIEW_MAX_CHARS,
    LIVE_EXPERIENCE_PERSISTENCE_ENABLED,
)


SESSION_CAPTURE_DESIGN_VERSION = 1
SESSION_CAPTURE_DESIGN_STATUS = "DESIGN_LOCKED_DISABLED"
SESSION_CAPTURE_CONSENT_MODEL = "explicit_single_session_opt_in"
SESSION_CAPTURE_FAILURE_MODE = "disable_capture_continue_normal_turn"


@dataclass(frozen=True)
class SessionCaptureDesignPolicy:
    version: int = SESSION_CAPTURE_DESIGN_VERSION
    status: str = SESSION_CAPTURE_DESIGN_STATUS
    default_enabled: bool = False
    consent_model: str = SESSION_CAPTURE_CONSENT_MODEL
    process_restart_resets_consent: bool = True
    persistence_default: str = "none"
    backfill_allowed: bool = False
    full_content_allowed: bool = False
    context_injection_payload_allowed: bool = False
    operator_command_capture_allowed: bool = False
    natural_routed_command_capture_allowed: bool = False
    background_capture_allowed: bool = False
    automatic_retention_actions_allowed: bool = False
    automatic_learning_apply_allowed: bool = False
    failure_mode: str = SESSION_CAPTURE_FAILURE_MODE
    implementation_authorized: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SessionCaptureDesignDoctorReport:
    status: str
    gate_status: str
    effective_capture_enabled: bool
    live_writer_installed: bool
    live_persistence_enabled: bool
    settings_exists: bool
    live_ledger_exists: bool
    implementation_authorized: bool
    findings: list[dict[str, str]]


@dataclass(frozen=True)
class SessionCaptureDesignBenchmarkReport:
    status: str
    checks: dict[str, bool]
    failed_checks: list[str]
    files_created: int
    boundary: str


class SessionCaptureDesignReview:
    """Design-only review. It exposes no capture activation or persistence operation."""

    def __init__(self, project_root: Path) -> None:
        self.project_root = Path(project_root)
        self.gate = ExperienceCaptureGate(self.project_root)
        self.policy = SessionCaptureDesignPolicy()

    @staticmethod
    def sections() -> dict[str, tuple[str, ...]]:
        return {
            "consent": (
                "Show the exact compact schema and scope before asking for consent.",
                "Require an explicit opt-in for one current process session only.",
                "Do not infer consent from normal conversation, Context Injection, or old settings.",
                "Provide an explicit stop/revoke path before any future capture implementation.",
                "Expire consent at process/session end; never reuse it after restart.",
            ),
            "scope": (
                "Future capture may observe normal cognitive turns only after consent.",
                "Exclude slash commands, exact natural-routed commands, internal reports, and system events.",
                "Never backfill turns that occurred before consent or import historical session logs.",
                "No background, detached, scheduled, or cross-session capture.",
            ),
            "privacy": (
                f"Store compact typed previews capped at {EXPERIENCE_PREVIEW_MAX_CHARS} characters.",
                "Deny full user messages, generated responses, system/hidden prompts, and raw context packs.",
                "Deny injected context payloads; record only that Context Injection was applied if needed.",
                "Require deterministic secret/redaction regression tests before any writer hook exists.",
                "Reference selected memory by compact ID/type/source evidence, never by hidden full content.",
            ),
            "retention": (
                "Default to no persistence; design review and in-memory preview come first.",
                "Require a separate milestone to approve path, event/byte bounds, retention, export, and archive policy.",
                "Never delete, compact, migrate, archive, or rotate records automatically.",
                "Never backfill old sessions or merge legacy session logs into Experience Ledger.",
                "A future persistent record must preserve append-only provenance and SHA-chain verification.",
            ),
            "failure_isolation": (
                "Event-building failure must not fail or delay the normal user turn.",
                "Write/hash/provenance failure must disable capture for the remaining session and fail closed.",
                "Do not retry in a background loop and do not switch to an alternate path.",
                "Never repair or truncate a corrupt ledger automatically.",
                "Diagnostics must use compact error metadata and never copy the rejected full payload.",
            ),
            "activation_preconditions": (
                "Separate checkpointed implementation task explicitly approved by the operator.",
                "Per-session consent state machine with preview, enable, stop, expiry, and restart tests.",
                "Privacy/redaction benchmark, slash/natural bypass tests, and bounded-growth soak.",
                "Atomic append, SHA/provenance verification, failure isolation, and no-write-disabled tests.",
                "Fresh data/export SHA baseline plus CLI, PySide, tkinter, Context Injection, and full-suite verification.",
            ),
        }

    def read_state(self) -> dict[str, Any]:
        gate_status = self.gate.status()
        return {
            "project_root": str(self.project_root),
            "design": self.policy.to_dict(),
            "gate": gate_status.to_dict(),
            "decision": "KEEP_DISABLED",
            "future_implementation_ready": False,
            "mutation_performed": False,
        }

    def doctor(self) -> SessionCaptureDesignDoctorReport:
        state = self.read_state()
        gate = state["gate"]
        findings: list[dict[str, str]] = []

        def add(severity: str, message: str) -> None:
            findings.append({"severity": severity, "message": message})

        if gate["effective_enabled"]:
            add("ERROR", "Experience Capture is unexpectedly effective during design review.")
        else:
            add("OK", "Experience Capture remains effectively disabled.")
        if LIVE_CAPTURE_HOOK_INSTALLED or LIVE_EXPERIENCE_PERSISTENCE_ENABLED:
            add("ERROR", "A live hook or persistence policy is active before design approval.")
        else:
            add("OK", "No live writer hook or live persistence policy is installed.")
        if gate["settings_exists"]:
            add("WARN", "A capture settings file exists and requires explicit manual inspection.")
        else:
            add("OK", "Missing settings resolve to non-persisted safe defaults.")
        if gate["live_ledger_exists"]:
            add("WARN", "A live ledger path exists and must not be reused or repaired automatically.")
        else:
            add("OK", "No live Experience Ledger file exists.")
        if gate["issues"]:
            add("ERROR", "Capture gate reports invalid settings: " + "; ".join(gate["issues"]))
        for warning in gate["warnings"]:
            add("WARN", warning)

        sections = self.sections()
        required_sections = {
            "consent",
            "scope",
            "privacy",
            "retention",
            "failure_isolation",
            "activation_preconditions",
        }
        if set(sections) != required_sections or any(not rows for rows in sections.values()):
            add("ERROR", "Design review sections are missing or empty.")
        else:
            add("OK", "Consent, scope, privacy, retention, failure isolation, and activation gates are explicit.")

        policy = self.policy
        unsafe_policy = any(
            (
                policy.default_enabled,
                policy.backfill_allowed,
                policy.full_content_allowed,
                policy.context_injection_payload_allowed,
                policy.operator_command_capture_allowed,
                policy.natural_routed_command_capture_allowed,
                policy.background_capture_allowed,
                policy.automatic_retention_actions_allowed,
                policy.automatic_learning_apply_allowed,
                policy.implementation_authorized,
            )
        )
        if unsafe_policy:
            add("ERROR", "Design policy exposes a forbidden activation, content, command, or mutation flag.")
        else:
            add("OK", "All activation, full-content, backfill, command, background, and auto-apply flags are denied.")

        forbidden_methods = {
            "activate",
            "append",
            "capture",
            "enable",
            "persist",
            "run",
            "start",
            "write",
        }
        exposed = sorted(forbidden_methods.intersection(dir(self)))
        if exposed:
            add("ERROR", "Design review exposes forbidden methods: " + ", ".join(exposed) + ".")
        else:
            add("OK", "No activation, capture, append, persistence, run, or write method is exposed.")

        if any(item["severity"] == "ERROR" for item in findings):
            status = "ERROR"
        elif any(item["severity"] == "WARN" for item in findings):
            status = "WARN"
        else:
            status = "OK"
        return SessionCaptureDesignDoctorReport(
            status=status,
            gate_status=str(gate["status"]),
            effective_capture_enabled=bool(gate["effective_enabled"]),
            live_writer_installed=LIVE_CAPTURE_HOOK_INSTALLED,
            live_persistence_enabled=LIVE_EXPERIENCE_PERSISTENCE_ENABLED,
            settings_exists=bool(gate["settings_exists"]),
            live_ledger_exists=bool(gate["live_ledger_exists"]),
            implementation_authorized=policy.implementation_authorized,
            findings=findings,
        )


def format_session_capture_design_status(review: SessionCaptureDesignReview) -> str:
    state = review.read_state()
    design = state["design"]
    gate = state["gate"]
    return "\n".join(
        [
            "Proto-Mind Session Capture Design Review v1",
            f"Status: {design['status']}",
            f"project_root: {state['project_root']}",
            f"decision: {state['decision']}",
            f"default_enabled: {str(design['default_enabled']).lower()}",
            f"consent_model: {design['consent_model']}",
            f"persistence_default: {design['persistence_default']}",
            f"effective_capture_enabled: {str(gate['effective_enabled']).lower()}",
            f"live_writer_installed: {str(gate['live_writer_installed']).lower()}",
            f"live_ledger_exists: {str(gate['live_ledger_exists']).lower()}",
            f"implementation_authorized: {str(design['implementation_authorized']).lower()}",
            "- Design lock only: no consent was requested and no capture or write occurred.",
        ]
    )


def format_session_capture_design_review(review: SessionCaptureDesignReview) -> str:
    lines = [
        "Proto-Mind Session Capture Design Lock v1",
        "Decision: KEEP_DISABLED",
        "implementation_authorized: false",
    ]
    for name, rows in review.sections().items():
        lines.extend(["", name.replace("_", " ").title() + ":"])
        lines.extend(f"- {row}" for row in rows)
    lines.extend(
        [
            "",
            "Boundary:",
            "- This document is an executable-free design report, not activation approval.",
            "- No config, ledger, consent, event, memory, skill, session log, command, or export was changed.",
        ]
    )
    return "\n".join(lines)


def format_session_capture_design_checklist(review: SessionCaptureDesignReview) -> str:
    rows = review.sections()["activation_preconditions"]
    lines = [
        "Future Session Capture Activation Checklist (Not Authorized)",
        "Status: BLOCKED_BY_DESIGN",
    ]
    lines.extend(f"- [ ] {row}" for row in rows)
    lines.extend(
        [
            "- [ ] Operator explicitly approves a separate implementation milestone.",
            "- Current task does not satisfy or execute this checklist.",
        ]
    )
    return "\n".join(lines)


def format_session_capture_design_doctor(review: SessionCaptureDesignReview) -> str:
    report = review.doctor()
    lines = [
        "Proto-Mind Session Capture Design Doctor v1",
        f"Status: {report.status}",
        f"gate_status: {report.gate_status}",
        f"effective_capture_enabled: {str(report.effective_capture_enabled).lower()}",
        f"live_writer_installed: {str(report.live_writer_installed).lower()}",
        f"live_persistence_enabled: {str(report.live_persistence_enabled).lower()}",
        f"settings_exists: {str(report.settings_exists).lower()}",
        f"live_ledger_exists: {str(report.live_ledger_exists).lower()}",
        f"implementation_authorized: {str(report.implementation_authorized).lower()}",
        "Checks:",
    ]
    lines.extend(
        f"- [{finding['severity']}] {finding['message']}" for finding in report.findings
    )
    lines.append("- Doctor is read-only; no initialization, activation, repair, or persistence occurred.")
    return "\n".join(lines)


def run_session_capture_design_benchmark() -> SessionCaptureDesignBenchmarkReport:
    with TemporaryDirectory(prefix="proto-mind-session-capture-design-") as temp_dir:
        project_root = Path(temp_dir)
        before = sorted(path.relative_to(project_root) for path in project_root.rglob("*") if path.is_file())
        review = SessionCaptureDesignReview(project_root)
        state = review.read_state()
        doctor = review.doctor()
        status_output = format_session_capture_design_status(review)
        review_output = format_session_capture_design_review(review)
        checklist_output = format_session_capture_design_checklist(review)
        doctor_output = format_session_capture_design_doctor(review)
        after = sorted(path.relative_to(project_root) for path in project_root.rglob("*") if path.is_file())

    forbidden_methods = {
        "activate",
        "append",
        "capture",
        "enable",
        "persist",
        "run",
        "start",
        "write",
    }
    checks = {
        "doctor_ok": doctor.status == "OK",
        "capture_disabled": state["gate"]["effective_enabled"] is False,
        "writer_hook_absent": state["gate"]["live_writer_installed"] is False,
        "implementation_not_authorized": state["design"]["implementation_authorized"] is False,
        "per_session_consent_required": state["design"]["consent_model"]
        == SESSION_CAPTURE_CONSENT_MODEL,
        "full_content_denied": state["design"]["full_content_allowed"] is False,
        "backfill_denied": state["design"]["backfill_allowed"] is False,
        "operator_commands_denied": state["design"]["operator_command_capture_allowed"] is False,
        "failure_isolation_locked": state["design"]["failure_mode"]
        == SESSION_CAPTURE_FAILURE_MODE,
        "no_activation_api": not forbidden_methods.intersection(dir(review)),
        "no_files_created": before == after == [],
        "reports_state_boundaries": "KEEP_DISABLED" in status_output
        and "implementation_authorized: false" in review_output
        and "BLOCKED_BY_DESIGN" in checklist_output
        and "Status: OK" in doctor_output,
    }
    failed_checks = [name for name, passed in checks.items() if not passed]
    return SessionCaptureDesignBenchmarkReport(
        status="OK" if not failed_checks else "FAIL",
        checks=checks,
        failed_checks=failed_checks,
        files_created=len(after),
        boundary=(
            "Design-only local review; no config, live ledger, consent state, capture hook, "
            "persistence, command, LLM, session-log change, domain mutation, or export."
        ),
    )


def format_session_capture_design_benchmark(
    report: SessionCaptureDesignBenchmarkReport | None = None,
) -> str:
    report = report or run_session_capture_design_benchmark()
    lines = [
        "Proto-Mind Session Capture Design Review v1",
        f"Status: {report.status}",
        f"files_created: {report.files_created}",
        "Checks:",
    ]
    lines.extend(
        f"- [{'PASS' if passed else 'FAIL'}] {name}" for name, passed in report.checks.items()
    )
    lines.extend(["Boundary:", f"- {report.boundary}"])
    return "\n".join(lines)


def main() -> int:
    project_root = Path(__file__).resolve().parent.parent
    review = SessionCaptureDesignReview(project_root)
    print(format_session_capture_design_status(review))
    print()
    print(format_session_capture_design_review(review))
    print()
    print(format_session_capture_design_checklist(review))
    print()
    print(format_session_capture_design_doctor(review))
    print()
    report = run_session_capture_design_benchmark()
    print(format_session_capture_design_benchmark(report))
    return 0 if review.doctor().status != "ERROR" and report.status == "OK" else 1


if __name__ == "__main__":
    raise SystemExit(main())
