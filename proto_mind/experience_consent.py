from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import re
from tempfile import TemporaryDirectory
from typing import Any, Iterable

from proto_mind.experience_capture import LIVE_CAPTURE_HOOK_INSTALLED
from proto_mind.experience_ledger import LIVE_EXPERIENCE_PERSISTENCE_ENABLED


SESSION_CONSENT_SPEC_VERSION = 1
CONSENT_PHRASE_PREFIX = "CONSENT EXPERIENCE PREVIEW FOR SESSION:"
CONSENT_STATES = frozenset({"disabled", "previewed", "consented", "stopped", "expired"})
CONSENT_EVENTS = frozenset(
    {
        "preview_shown",
        "consent_submitted",
        "normal_prompt_observed",
        "slash_command_observed",
        "natural_routed_command_observed",
        "internal_report_observed",
        "historical_turn_observed",
        "stop_requested",
        "session_ended",
        "process_restarted",
        "capture_failure_observed",
    }
)


@dataclass(frozen=True)
class SessionConsentTransition:
    session_id: str
    previous_state: str
    event: str
    next_state: str
    accepted: bool
    scope_allowed: bool
    consent_active: bool
    token_matched: bool | None
    reason: str
    capture_performed: bool = False
    implementation_authorized: bool = False
    persistence_performed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SessionConsentDoctorReport:
    status: str
    state_count: int
    event_count: int
    refusal_case_count: int
    issues: list[str]
    warnings: list[str]


@dataclass(frozen=True)
class SessionConsentBenchmarkReport:
    status: str
    transition_count: int
    refusal_case_count: int
    files_created: int
    checks: dict[str, bool]
    failed_checks: list[str]
    boundary: str


class SessionConsentStateMachineSpec:
    """Pure transition specification; it stores no consent and cannot capture anything."""

    def __init__(self, session_id: str) -> None:
        self.session_id = _normalize_session_id(session_id)

    def expected_phrase(self) -> str:
        return f"{CONSENT_PHRASE_PREFIX} {self.session_id}"

    def evaluate(
        self,
        current_state: str,
        event: str,
        *,
        provided_phrase: str = "",
    ) -> SessionConsentTransition:
        state = str(current_state).strip().casefold()
        normalized_event = str(event).strip().casefold()
        if state not in CONSENT_STATES:
            return self._result(
                state,
                normalized_event,
                "disabled",
                accepted=False,
                reason="invalid_state_fail_closed",
            )
        if normalized_event not in CONSENT_EVENTS:
            return self._result(
                state,
                normalized_event,
                state,
                accepted=False,
                reason="unknown_event_refused",
            )

        if normalized_event in {"session_ended", "process_restarted"}:
            return self._result(
                state,
                normalized_event,
                "expired",
                accepted=True,
                reason="consent_expired",
            )
        if normalized_event == "capture_failure_observed":
            return self._result(
                state,
                normalized_event,
                "stopped",
                accepted=True,
                reason="capture_disabled_fail_closed",
            )
        if normalized_event == "stop_requested":
            next_state = "expired" if state == "expired" else "stopped"
            return self._result(
                state,
                normalized_event,
                next_state,
                accepted=True,
                reason="already_expired" if state == "expired" else "consent_stopped",
            )
        if normalized_event == "preview_shown":
            if state == "disabled":
                return self._result(
                    state,
                    normalized_event,
                    "previewed",
                    accepted=True,
                    reason="preview_acknowledged",
                )
            if state == "previewed":
                return self._result(
                    state,
                    normalized_event,
                    state,
                    accepted=True,
                    reason="preview_already_shown",
                )
            return self._result(
                state,
                normalized_event,
                state,
                accepted=False,
                reason="terminal_or_active_state_requires_new_session",
            )
        if normalized_event == "consent_submitted":
            token_matched = provided_phrase.strip() == self.expected_phrase()
            if state in {"stopped", "expired"}:
                return self._result(
                    state,
                    normalized_event,
                    state,
                    accepted=False,
                    token_matched=token_matched,
                    reason="terminal_state_requires_restart",
                )
            if state != "previewed":
                return self._result(
                    state,
                    normalized_event,
                    state,
                    accepted=False,
                    token_matched=token_matched,
                    reason="preview_required_before_consent",
                )
            if not token_matched:
                return self._result(
                    state,
                    normalized_event,
                    state,
                    accepted=False,
                    token_matched=False,
                    reason=_consent_mismatch_reason(provided_phrase, self.expected_phrase()),
                )
            return self._result(
                state,
                normalized_event,
                "consented",
                accepted=True,
                token_matched=True,
                reason="exact_session_consent_matched_design_only",
            )
        if normalized_event == "normal_prompt_observed":
            if state == "consented":
                return self._result(
                    state,
                    normalized_event,
                    state,
                    accepted=True,
                    scope_allowed=True,
                    reason="normal_prompt_in_scope_design_only",
                )
            return self._result(
                state,
                normalized_event,
                state,
                accepted=False,
                reason="consent_not_active",
            )

        bypass_reasons = {
            "slash_command_observed": "slash_command_bypass",
            "natural_routed_command_observed": "natural_routed_command_bypass",
            "internal_report_observed": "internal_report_bypass",
            "historical_turn_observed": "historical_backfill_refused",
        }
        return self._result(
            state,
            normalized_event,
            state,
            accepted=False,
            reason=bypass_reasons[normalized_event],
        )

    def simulate(
        self,
        events: Iterable[str | tuple[str, str]],
        *,
        initial_state: str = "disabled",
    ) -> list[SessionConsentTransition]:
        state = initial_state
        results: list[SessionConsentTransition] = []
        for item in events:
            if isinstance(item, tuple):
                event, phrase = item
            else:
                event, phrase = item, ""
            result = self.evaluate(state, event, provided_phrase=phrase)
            results.append(result)
            state = result.next_state
        return results

    def refusal_matrix(self) -> list[SessionConsentTransition]:
        other_session = SessionConsentStateMachineSpec("other-session")
        cases = (
            self.evaluate("disabled", "consent_submitted", provided_phrase=self.expected_phrase()),
            self.evaluate("previewed", "consent_submitted"),
            self.evaluate("previewed", "consent_submitted", provided_phrase="yes"),
            self.evaluate(
                "previewed",
                "consent_submitted",
                provided_phrase=f"{CONSENT_PHRASE_PREFIX} all",
            ),
            self.evaluate(
                "previewed",
                "consent_submitted",
                provided_phrase=other_session.expected_phrase(),
            ),
            self.evaluate(
                "previewed",
                "consent_submitted",
                provided_phrase=self.expected_phrase() + "; extra",
            ),
            self.evaluate("consented", "slash_command_observed"),
            self.evaluate("consented", "natural_routed_command_observed"),
            self.evaluate("consented", "internal_report_observed"),
            self.evaluate("consented", "historical_turn_observed"),
            self.evaluate("stopped", "normal_prompt_observed"),
            self.evaluate("expired", "consent_submitted", provided_phrase=self.expected_phrase()),
            self.evaluate("consented", "unknown_event"),
            self.evaluate("invalid", "normal_prompt_observed"),
        )
        return list(cases)

    def doctor(self) -> SessionConsentDoctorReport:
        issues: list[str] = []
        warnings: list[str] = []
        happy_path = self.simulate(
            [
                "preview_shown",
                ("consent_submitted", self.expected_phrase()),
                "normal_prompt_observed",
                "slash_command_observed",
                "stop_requested",
                "normal_prompt_observed",
                "process_restarted",
            ]
        )
        expected_states = [
            "previewed",
            "consented",
            "consented",
            "consented",
            "stopped",
            "stopped",
            "expired",
        ]
        if [result.next_state for result in happy_path] != expected_states:
            issues.append("Happy-path state transitions do not match the locked design.")
        if not happy_path[2].scope_allowed or happy_path[3].scope_allowed:
            issues.append("Normal-prompt scope or slash-command bypass is incorrect.")
        refusals = self.refusal_matrix()
        if any(result.accepted or result.scope_allowed for result in refusals):
            issues.append("At least one refusal case was accepted or marked in scope.")
        if any(result.capture_performed for result in happy_path + refusals):
            issues.append("Transition results expose forbidden capture execution.")
        if any(result.implementation_authorized for result in happy_path + refusals):
            issues.append("Transition results expose forbidden implementation authorization.")
        if any(result.persistence_performed for result in happy_path + refusals):
            issues.append("Transition results expose forbidden persistence.")
        if LIVE_CAPTURE_HOOK_INSTALLED or LIVE_EXPERIENCE_PERSISTENCE_ENABLED:
            issues.append("Live capture hook or persistence is active during consent design review.")
        if not self.expected_phrase().endswith(self.session_id):
            issues.append("Expected consent phrase is not bound to the normalized session ID.")
        forbidden_methods = {"capture", "persist", "write", "append", "enable", "activate"}
        if forbidden_methods.intersection(dir(self)):
            issues.append("Consent spec exposes a capture, persistence, or activation method.")
        status = "ERROR" if issues else "WARN" if warnings else "OK"
        return SessionConsentDoctorReport(
            status=status,
            state_count=len(CONSENT_STATES),
            event_count=len(CONSENT_EVENTS),
            refusal_case_count=len(refusals),
            issues=issues,
            warnings=warnings,
        )

    def _result(
        self,
        previous_state: str,
        event: str,
        next_state: str,
        *,
        accepted: bool,
        reason: str,
        scope_allowed: bool = False,
        token_matched: bool | None = None,
    ) -> SessionConsentTransition:
        return SessionConsentTransition(
            session_id=self.session_id,
            previous_state=previous_state,
            event=event,
            next_state=next_state,
            accepted=accepted,
            scope_allowed=scope_allowed,
            consent_active=next_state == "consented",
            token_matched=token_matched,
            reason=reason,
        )


def _normalize_session_id(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9_-]+", "-", str(value).strip()).strip("-")
    if not normalized:
        raise ValueError("session_id must not be empty")
    return normalized[:80]


def _consent_mismatch_reason(provided: str, expected: str) -> str:
    candidate = provided.strip()
    if not candidate:
        return "exact_consent_phrase_required"
    if "\n" in provided or ";" in candidate:
        return "extra_or_chained_input_refused"
    if candidate.casefold() in {"yes", "ok", "confirm", "all", "consent all"}:
        return "broad_or_implicit_consent_refused"
    if candidate.startswith(CONSENT_PHRASE_PREFIX) and candidate != expected:
        return "session_mismatch_or_phrase_modified"
    return "consent_phrase_mismatch"


def format_session_consent_status(spec: SessionConsentStateMachineSpec) -> str:
    return "\n".join(
        [
            "Proto-Mind Session Consent State Machine Spec v1",
            "Status: DESIGN_ONLY_DISABLED",
            f"session_id: {spec.session_id}",
            "initial_state: disabled",
            f"states: {', '.join(sorted(CONSENT_STATES))}",
            f"expected_phrase: {spec.expected_phrase()}",
            "consent_storage: none/process-memory simulation only",
            "implementation_authorized: false",
            "capture_performed: false",
            "- No command, hook, writer, config, ledger, or persistent consent exists.",
        ]
    )


def format_session_consent_transitions(spec: SessionConsentStateMachineSpec) -> str:
    results = spec.simulate(
        [
            "preview_shown",
            ("consent_submitted", spec.expected_phrase()),
            "normal_prompt_observed",
            "slash_command_observed",
            "stop_requested",
            "process_restarted",
        ]
    )
    lines = [
        "Session Consent Transition Preview (Simulation Only)",
        "implementation_authorized: false",
    ]
    lines.extend(
        f"- {result.previous_state} + {result.event} -> {result.next_state}; "
        f"accepted={str(result.accepted).lower()}; scope_allowed="
        f"{str(result.scope_allowed).lower()}; reason={result.reason}"
        for result in results
    )
    lines.append("- Every transition has capture_performed=false and persistence_performed=false.")
    return "\n".join(lines)


def format_session_consent_refusals(spec: SessionConsentStateMachineSpec) -> str:
    lines = [
        "Session Consent Refusal Matrix v1",
        f"cases: {len(spec.refusal_matrix())}",
    ]
    lines.extend(
        f"- state={result.previous_state}; event={result.event}; reason={result.reason}; "
        f"next={result.next_state}; accepted=false; scope_allowed=false"
        for result in spec.refusal_matrix()
    )
    lines.append("- Raw supplied phrases are not retained in transition results.")
    return "\n".join(lines)


def format_session_consent_doctor(spec: SessionConsentStateMachineSpec) -> str:
    report = spec.doctor()
    lines = [
        "Proto-Mind Session Consent State Machine Doctor v1",
        f"Status: {report.status}",
        f"states: {report.state_count}",
        f"events: {report.event_count}",
        f"refusal_cases: {report.refusal_case_count}",
    ]
    lines.extend(f"- ERROR: {issue}" for issue in report.issues)
    lines.extend(f"- WARN: {warning}" for warning in report.warnings)
    if not report.issues and not report.warnings:
        lines.extend(
            [
                "- Exact session-bound consent, expiry, stop, bypass, and refusal transitions are valid.",
                "- Capture, persistence, implementation authorization, and raw token retention remain absent.",
            ]
        )
    lines.append("- Doctor is pure/read-only and stores no consent state.")
    return "\n".join(lines)


def run_session_consent_benchmark() -> SessionConsentBenchmarkReport:
    with TemporaryDirectory(prefix="proto-mind-session-consent-") as temp_dir:
        root = Path(temp_dir)
        before = list(root.rglob("*"))
        spec = SessionConsentStateMachineSpec("benchmark-session")
        happy = spec.simulate(
            [
                "preview_shown",
                ("consent_submitted", spec.expected_phrase()),
                "normal_prompt_observed",
                "natural_routed_command_observed",
                "capture_failure_observed",
                "normal_prompt_observed",
                "process_restarted",
            ]
        )
        refusals = spec.refusal_matrix()
        doctor = spec.doctor()
        after = list(root.rglob("*"))

    checks = {
        "doctor_ok": doctor.status == "OK",
        "preview_before_consent": happy[0].next_state == "previewed",
        "exact_consent_matches": happy[1].next_state == "consented"
        and happy[1].token_matched is True,
        "normal_prompt_scope_design_only": happy[2].scope_allowed
        and happy[2].capture_performed is False,
        "natural_route_bypassed": happy[3].reason == "natural_routed_command_bypass"
        and not happy[3].scope_allowed,
        "failure_stops_session": happy[4].next_state == "stopped"
        and happy[4].reason == "capture_disabled_fail_closed",
        "stopped_consent_not_reused": happy[5].reason == "consent_not_active",
        "restart_expires": happy[6].next_state == "expired",
        "all_refusals_closed": all(
            not result.accepted and not result.scope_allowed for result in refusals
        ),
        "no_capture_or_persistence": all(
            not result.capture_performed
            and not result.persistence_performed
            and not result.implementation_authorized
            for result in happy + refusals
        ),
        "no_raw_phrase_retained": all(
            "provided_phrase" not in result.to_dict() for result in happy + refusals
        ),
        "no_files_created": before == after == [],
    }
    failed_checks = [name for name, passed in checks.items() if not passed]
    return SessionConsentBenchmarkReport(
        status="OK" if not failed_checks else "FAIL",
        transition_count=len(happy),
        refusal_case_count=len(refusals),
        files_created=len(after),
        checks=checks,
        failed_checks=failed_checks,
        boundary=(
            "Pure in-memory transition simulation only; no consent capture, command, hook, "
            "writer, config, ledger, persistence, normal-turn integration, Context Injection "
            "change, LLM, domain mutation, or export."
        ),
    )


def format_session_consent_benchmark(
    report: SessionConsentBenchmarkReport | None = None,
) -> str:
    report = report or run_session_consent_benchmark()
    lines = [
        "Proto-Mind Session Consent State Machine Spec v1",
        f"Status: {report.status}",
        f"transitions: {report.transition_count}",
        f"refusal_cases: {report.refusal_case_count}",
        f"files_created: {report.files_created}",
        "Checks:",
    ]
    lines.extend(
        f"- [{'PASS' if passed else 'FAIL'}] {name}" for name, passed in report.checks.items()
    )
    lines.extend(["Boundary:", f"- {report.boundary}"])
    return "\n".join(lines)


def main() -> int:
    spec = SessionConsentStateMachineSpec("design-preview-session")
    print(format_session_consent_status(spec))
    print()
    print(format_session_consent_transitions(spec))
    print()
    print(format_session_consent_refusals(spec))
    print()
    print(format_session_consent_doctor(spec))
    print()
    report = run_session_consent_benchmark()
    print(format_session_consent_benchmark(report))
    return 0 if spec.doctor().status == "OK" and report.status == "OK" else 1


if __name__ == "__main__":
    raise SystemExit(main())
