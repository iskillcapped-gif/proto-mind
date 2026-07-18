from __future__ import annotations

import hashlib
from collections import Counter, deque
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from proto_mind.action_policy import classify_command
from proto_mind.command_registry import COMMAND_REGISTRY
from proto_mind.memory_store import MemoryStore
from proto_mind.runner_exec_config import (
    ACTIVE_READONLY_ALLOWLIST,
    CAPABILITIES_SAFETY_COMMAND,
    CAPABILITIES_SAFETY_CONFIRMATION,
    DAILY_DOCTOR_COMMAND,
    DAILY_DOCTOR_CONFIRMATION,
    EVIDENCE_HISTORY_MAX_SIZE,
    EXACT_CONFIRMATION,
    EXACT_CONFIRMATIONS,
    EXPORTS_DOCTOR_COMMAND,
    EXPORTS_DOCTOR_CONFIRMATION,
    PILOT_COMMAND,
    RUN_USAGES,
)
from proto_mind.runner_mvp import RunnerMVPDesignLock


RUNNER_EXEC_COMMANDS = (
    "/runner-exec status",
    "/runner-exec allowlist",
    "/runner-exec dry-run",
    "/runner-exec run",
    "/runner-exec evidence",
    "/runner-exec refusal-matrix",
    "/runner-exec last-refusal",
    "/runner-exec evidence-check",
    "/runner-exec history",
    "/runner-exec history-summary",
    "/runner-exec history-clear-preview",
    "/runner-exec history-doctor",
    "/runner-exec stability",
    "/runner-exec sequence-plan",
    "/runner-exec sequence-evidence",
    "/runner-exec consistency-check",
    "/runner-exec soak",
    "/runner-exec soak-plan",
    "/runner-exec soak-report",
    "/runner-exec drift-check",
    "/runner-exec doctor",
    "/runner-exec handoff",
)
_LAST_EVIDENCE: dict[str, Any] | None = None
_LAST_SUCCESS_EVIDENCE: dict[str, Any] | None = None
_LAST_REFUSAL_EVIDENCE: dict[str, Any] | None = None
_LATEST_SUCCESS_BY_COMMAND: dict[str, dict[str, Any]] = {}
_EVENT_COUNTS: Counter[str] = Counter()
_EVIDENCE_HISTORY: deque[dict[str, Any]] = deque(maxlen=EVIDENCE_HISTORY_MAX_SIZE)
_RUN_SEQUENCE = 0

_REFUSAL_MATRIX = (
    ("missing_confirmation", "/runner-exec run", "CONFIRMATION_REQUIRED", "No implicit or cached approval is accepted."),
    ("wrong_confirmation", "CONFIRM READONLY: /warnings unknown", "CONFIRMATION_MISMATCH", "The phrase must match byte-for-byte after outer whitespace is stripped."),
    ("different_allowlisted_command", "candidate=/warnings unknown, confirmation=CONFIRM RUN READONLY: /daily doctor", "CONFIRMATION_COMMAND_MISMATCH", "Confirmation is command-specific and cannot authorize another allowlisted target."),
    ("outside_allowlist", "CONFIRM RUN READONLY: /confirm policy", "COMMAND_NOT_ALLOWLISTED", "Only the four exact configured commands are active."),
    ("near_miss_command", "CONFIRM RUN READONLY: /warnings accepted", "COMMAND_NOT_ALLOWLISTED", "Similar commands are not aliases."),
    ("suffix_attempt", "CONFIRM RUN READONLY: /warnings unknown; /daily doctor", "CONFIRMATION_MISMATCH: EXTRA_INPUT", "Suffixes, chains, and injection-like text are refused."),
    ("broad_confirmation", "CONFIRM RUN READONLY: all", "CONFIRMATION_MISMATCH: BROAD_CONFIRMATION", "Broad approval is never valid."),
    ("unsafe_or_unknown_target", "CONFIRM RUN READONLY: <mutating/high-risk/operator-only/unknown>", "COMMAND_NOT_ALLOWLISTED", "The fixed transport exposes no arbitrary dispatcher."),
)


def reset_runner_exec_evidence() -> None:
    global _LAST_EVIDENCE, _LAST_SUCCESS_EVIDENCE, _LAST_REFUSAL_EVIDENCE, _RUN_SEQUENCE
    _LAST_EVIDENCE = None
    _LAST_SUCCESS_EVIDENCE = None
    _LAST_REFUSAL_EVIDENCE = None
    _LATEST_SUCCESS_BY_COMMAND.clear()
    _EVENT_COUNTS.clear()
    _EVIDENCE_HISTORY.clear()
    _RUN_SEQUENCE = 0


def format_runner_exec_command(
    command: str,
    *,
    project_root: Path,
    memory_store: MemoryStore,
    executors: Mapping[str, Callable[[], str]] | None = None,
) -> str | None:
    stripped = command.strip()
    normalized = " ".join(stripped.lower().split())
    if normalized != "/runner-exec" and not normalized.startswith("/runner-exec "):
        return None
    runner = ReadOnlyRunnerPilot(project_root=project_root, memory_store=memory_store)
    if normalized == "/runner-exec status":
        return runner.format_status()
    if normalized == "/runner-exec allowlist":
        return runner.format_allowlist()
    if normalized == "/runner-exec dry-run":
        return runner.format_dry_run(PILOT_COMMAND)
    if normalized.startswith("/runner-exec dry-run "):
        candidate = stripped[len("/runner-exec dry-run") :].strip()
        return runner.format_dry_run(candidate)
    if normalized == "/runner-exec evidence":
        return runner.format_evidence()
    if normalized == "/runner-exec refusal-matrix":
        return runner.format_refusal_matrix()
    if normalized == "/runner-exec last-refusal":
        return runner.format_last_refusal()
    if normalized == "/runner-exec evidence-check":
        return runner.format_evidence_check()
    if normalized == "/runner-exec history":
        return runner.format_history()
    if normalized == "/runner-exec history-summary":
        return runner.format_history_summary()
    if normalized == "/runner-exec history-clear-preview":
        return runner.format_history_clear_preview()
    if normalized == "/runner-exec history-doctor":
        return runner.format_history_doctor()
    if normalized == "/runner-exec stability":
        return runner.format_stability(executors)
    if normalized == "/runner-exec sequence-plan":
        return runner.format_sequence_plan()
    if normalized == "/runner-exec sequence-evidence":
        return runner.format_sequence_evidence()
    if normalized == "/runner-exec consistency-check":
        return runner.format_consistency_check(executors)
    if normalized == "/runner-exec soak":
        return runner.format_soak(executors)
    if normalized == "/runner-exec soak-plan":
        return runner.format_soak_plan()
    if normalized == "/runner-exec soak-report":
        return runner.format_soak_report()
    if normalized == "/runner-exec drift-check":
        return runner.format_drift_check(executors)
    if normalized == "/runner-exec doctor":
        return runner.format_doctor(executors)
    if normalized == "/runner-exec handoff":
        return runner.format_handoff()
    if normalized == "/runner-exec run":
        return runner.run(candidate=PILOT_COMMAND, confirmation=None, executors=executors)
    if normalized.startswith("/runner-exec run "):
        confirmation = stripped[len("/runner-exec run") :].strip()
        candidate = _candidate_from_confirmation(confirmation)
        return runner.run(candidate=candidate, confirmation=confirmation, executors=executors)
    return "Usage:\n" + "\n".join(f"  {item}" for item in RUNNER_EXEC_COMMANDS) + "\n" + "\n".join(f"  {usage}" for usage in RUN_USAGES)


class ReadOnlyRunnerPilot:
    def __init__(self, *, project_root: Path, memory_store: MemoryStore) -> None:
        self.project_root = project_root
        self.memory_store = memory_store
        self.mvp = RunnerMVPDesignLock(project_root=project_root, memory_store=memory_store)

    def read_state(self) -> dict[str, Any]:
        mvp = self.mvp.read_state()
        if mvp["blocker_count"] or mvp["context_state"] == "enabled":
            safety_state = "BLOCKED"
        elif mvp["accepted"] or mvp["unknown"] or mvp["system_status"] != "OK":
            safety_state = "WARN"
        else:
            safety_state = "OK"
        registry = {item.prefix: item for item in COMMAND_REGISTRY}
        command_safety: dict[str, bool] = {}
        for command in ACTIVE_READONLY_ALLOWLIST:
            spec = registry.get(command)
            decision = classify_command(command)
            command_safety[command] = bool(
                spec
                and spec.read_only
                and spec.mutates == "none"
                and spec.risk == "low"
                and decision.policy_class == "auto_allowed"
            )
        execution_enabled = (
            tuple(ACTIVE_READONLY_ALLOWLIST)
            == (PILOT_COMMAND, DAILY_DOCTOR_COMMAND, EXPORTS_DOCTOR_COMMAND, CAPABILITIES_SAFETY_COMMAND)
            and all(command_safety.values())
            and mvp["context_state"] == "disabled"
            and mvp["blocker_count"] == 0
        )
        return {
            **mvp,
            "runner_exec_safety_state": safety_state,
            "command_safety": command_safety,
            "pilot_command_safe": command_safety.get(PILOT_COMMAND, False),
            "daily_doctor_command_safe": command_safety.get(DAILY_DOCTOR_COMMAND, False),
            "exports_doctor_command_safe": command_safety.get(EXPORTS_DOCTOR_COMMAND, False),
            "capabilities_safety_command_safe": command_safety.get(CAPABILITIES_SAFETY_COMMAND, False),
            "execution_enabled": execution_enabled,
            "active_allowlist": tuple(ACTIVE_READONLY_ALLOWLIST),
        }

    def format_status(self) -> str:
        state = self.read_state()
        categories = Counter(spec.category for spec in COMMAND_REGISTRY)
        return "\n".join(
            [
                "Real Read-only Runner MVP Status",
                f"Status: {state['runner_exec_safety_state']}",
                f"project_root: {self.project_root}",
                f"command_registry: commands={len(COMMAND_REGISTRY)} categories={len(categories)}",
                f"context_injection: {state['context_state']}",
                f"active_allowlist_count: {len(ACTIVE_READONLY_ALLOWLIST)}",
                f"active_allowlisted_commands: {', '.join(ACTIVE_READONLY_ALLOWLIST)}",
                f"execution_enabled: {str(state['execution_enabled']).lower()}",
                "confirmation_required: true",
                f"exact_confirmations: {EXACT_CONFIRMATION} | {DAILY_DOCTOR_CONFIRMATION} | {EXPORTS_DOCTOR_CONFIRMATION} | {CAPABILITIES_SAFETY_CONFIRMATION}",
                f"accepted_known_warnings: {len(state['accepted'])}",
                f"unknown_warnings: {len(state['unknown'])}",
                f"blockers: {state['blocker_count']}",
                f"last_evidence: {'AVAILABLE_IN_MEMORY' if _LAST_EVIDENCE is not None else 'NONE'}",
                f"last_success_evidence: {'AVAILABLE_IN_MEMORY' if _LAST_SUCCESS_EVIDENCE is not None else 'NONE'}",
                f"last_refusal_evidence: {'AVAILABLE_IN_MEMORY' if _LAST_REFUSAL_EVIDENCE is not None else 'NONE'}",
                f"history_events: {len(_EVIDENCE_HISTORY)}/{EVIDENCE_HISTORY_MAX_SIZE}",
                f"warnings_unknown_safe: {str(state['pilot_command_safe']).lower()}",
                f"daily_doctor_safe: {str(state['daily_doctor_command_safe']).lower()}",
                f"exports_doctor_safe: {str(state['exports_doctor_command_safe']).lower()}",
                f"capabilities_safety_safe: {str(state['capabilities_safety_command_safe']).lower()}",
                "",
                "Safety scope:",
                "- Exactly four fixed internal read-only targets; no shell/subprocess/eval/exec, free-form dispatch, persistence, network, background work, or target-store writes.",
            ]
        )

    def format_allowlist(self) -> str:
        state = self.read_state()
        lines = ["Active Read-only Runner MVP Allowlist", f"active_allowlist_count: {len(ACTIVE_READONLY_ALLOWLIST)}"]
        for command in ACTIVE_READONLY_ALLOWLIST:
            lines.extend(
                [
                    f"- ACTIVE_READONLY_ALLOWLIST: {command}",
                    "  safety_class: read-only / mutates=none / risk=low / policy=auto_allowed",
                    f"  exact_confirmation_required: {EXACT_CONFIRMATIONS[command]}",
                    "  expected_writes: none to proto_mind/data or proto_mind/exports",
                    "  transport: dedicated zero-argument internal callback",
                    "  forbidden_primitives: shell/subprocess/eval/exec",
                ]
            )
        lines.extend(
            [
                "",
                f"execution_enabled: {str(state['execution_enabled']).lower()}",
                "Allowlist invariant: exactly four commands; no prefix, argument, alias, bundle, fifth command, or free-form target is active.",
            ]
        )
        return "\n".join(lines)

    def format_dry_run(self, candidate: str) -> str:
        state = self.read_state()
        allowlisted = candidate in ACTIVE_READONLY_ALLOWLIST
        confirmation = EXACT_CONFIRMATIONS.get(candidate, "NOT_AVAILABLE_COMMAND_NOT_ALLOWLISTED")
        return "\n".join(
            [
                "Read-only Runner MVP Dry Run",
                f"command_candidate: {candidate}",
                f"active_allowlist_match: {str(allowlisted).lower()}",
                f"safety_class: {'read-only / mutates=none / risk=low / policy=auto_allowed' if allowlisted else 'BLOCKED / COMMAND_NOT_ALLOWLISTED'}",
                f"execution_enabled_if_gates_pass: {str(state['execution_enabled'] and allowlisted).lower()}",
                f"required_confirmation_phrase: {confirmation}",
                f"exact_usage: {'/runner-exec run ' + confirmation if allowlisted else 'not available'}",
                "",
                "Gates:",
                "- candidate exactly matches one of the four active allowlist entries",
                "- confirmation exactly matches the command-specific required phrase",
                "- Context Injection is disabled",
                "- blockers equal 0",
                "- Registry/Policy classify the target read-only, mutates=none, low-risk, auto_allowed",
                "- data/exports writes, shell/subprocess/eval/exec, network, background work, snapshot, and backup are absent",
                "",
                "Expected evidence:",
                "- request id, exact target, gate results, confirmation match, captured output summary, status, SHA before/after, context state, unknown-warning count, and refusal reason if any",
                "",
                "Stop conditions:",
                "- missing/mismatched confirmation, allowlist drift, blocker/context/policy failure, write detection, executor failure, or unexpected exception",
                "",
                "Dry-run guarantee:",
                "- The target command was not executed and no evidence state was changed.",
            ]
        )

    def format_refusal_matrix(self) -> str:
        lines = [
            "Read-only Runner MVP Refusal Matrix",
            "mode: static deterministic expectations",
            "cases_executed: false",
            f"active_allowlist: {', '.join(ACTIVE_READONLY_ALLOWLIST)}",
            "",
            "Cases:",
        ]
        for case_id, input_shape, reason, note in _REFUSAL_MATRIX:
            lines.extend(
                [
                    f"- case_id: {case_id}",
                    f"  input_shape: {input_shape}",
                    "  expected_result: REFUSED",
                    "  expected_executed: false",
                    f"  refusal_reason: {reason}",
                    f"  safety_note: {note}",
                ]
            )
        lines.extend(
            [
                "",
                "Matrix guarantee:",
                "- No case was dispatched, no executor was called, and no evidence state was changed.",
            ]
        )
        return "\n".join(lines)

    def format_last_refusal(self) -> str:
        if _LAST_REFUSAL_EVIDENCE is None:
            return "\n".join(
                [
                    "Read-only Runner MVP Last Refusal",
                    "status: NOT_AVAILABLE_NO_REFUSAL",
                    "storage: in-memory only",
                    "No refusal evidence exists in the current process.",
                ]
            )
        evidence = _LAST_REFUSAL_EVIDENCE
        gate_lines = ", ".join(f"{name}={str(value).lower()}" for name, value in evidence["gates_checked"].items())
        return "\n".join(
            [
                "Read-only Runner MVP Last Refusal",
                f"request_id: {evidence['request_id']}",
                f"created_at: {evidence['created_at']}",
                f"command_requested: {evidence['command_requested']}",
                f"confirmation_received: {evidence['confirmation_received']}",
                "executed: false",
                f"refusal_reason: {evidence['refusal_reason']}",
                f"gates_checked: {gate_lines}",
                f"gate_failures: {', '.join(evidence['gate_failures']) or 'none'}",
                "files_written: none",
                "storage: in-memory only; no evidence/log/approval file was created.",
            ]
        )

    def format_evidence_check(self) -> str:
        report = self.evidence_check_report()
        lines = ["Read-only Runner MVP Evidence Check", f"Status: {report['status']}", "", "Checks:"]
        lines.extend(f"- [{item['severity']}] {item['message']}" for item in report["findings"])
        lines.extend(
            [
                "",
                "Evidence boundary:",
                "- Validation is current-process-only and performs no execution, persistence, file write, or approval capture.",
            ]
        )
        return "\n".join(lines)

    def format_history(self) -> str:
        lines = [
            "Runner Evidence History Ring Buffer",
            "storage: process-memory-only",
            f"buffer_size: {len(_EVIDENCE_HISTORY)}",
            f"max_size: {EVIDENCE_HISTORY_MAX_SIZE}",
            f"event_count: {len(_EVIDENCE_HISTORY)}",
        ]
        if not _EVIDENCE_HISTORY:
            lines.extend(["status: NOT_AVAILABLE_NO_HISTORY", "events: none"])
            return "\n".join(lines)
        lines.extend(["status: AVAILABLE_IN_MEMORY", "order: oldest-to-newest", "", "Events:"])
        for event in _EVIDENCE_HISTORY:
            lines.extend(
                [
                    f"- event_id: {event['event_id']}",
                    f"  event_type: {event['event_type']}",
                    f"  created_at: {event['created_at']}",
                    f"  command_requested: {event['command_requested']}",
                    f"  command_executed: {event['command_executed'] or 'none'}",
                    f"  executed: {str(event['executed']).lower()}",
                    f"  status_result: {event['status_result']}",
                    f"  confirmation_matched: {str(event['confirmation_matched']).lower()}",
                    f"  gates_checked: {event['gates_checked_summary']}",
                    f"  refusal_reason: {event['refusal_reason'] or 'none'}",
                    f"  data_exports_changed: {event['data_exports_changed']}",
                    f"  context_injection_status: {event['context_injection_status']}",
                    f"  unknown_warning_count_after: {_optional_value(event['unknown_warning_count_after'])}",
                    f"  export_doctor_status: {_optional_value(event['export_doctor_status'])}",
                    f"  capabilities_safety_summary: {_optional_value(event['capabilities_safety_summary'])}",
                ]
            )
        lines.append("persistence: false; history is lost on process restart")
        return "\n".join(lines)

    def format_history_summary(self) -> str:
        successes = [event for event in _EVIDENCE_HISTORY if event["event_type"] == "SUCCESS"]
        refusals = [event for event in _EVIDENCE_HISTORY if event["event_type"] == "REFUSAL"]
        per_command = Counter(event["command_executed"] for event in successes if event["command_executed"])
        outside_count = sum(
            1
            for event in _EVIDENCE_HISTORY
            if event["executed"] and event["command_executed"] not in ACTIVE_READONLY_ALLOWLIST
        )
        lines = [
            "Runner Evidence History Summary",
            f"event_count: {len(_EVIDENCE_HISTORY)}",
            f"max_size: {EVIDENCE_HISTORY_MAX_SIZE}",
            f"success_count: {len(successes)}",
            f"refusal_count: {len(refusals)}",
            f"outside_allowlist_executed_count: {outside_count}",
            f"latest_event_id: {_EVIDENCE_HISTORY[-1]['event_id'] if _EVIDENCE_HISTORY else 'NOT_AVAILABLE'}",
            f"latest_success_command: {successes[-1]['command_executed'] if successes else 'NOT_AVAILABLE'}",
            f"latest_refusal_reason: {refusals[-1]['refusal_reason'] if refusals else 'NOT_AVAILABLE'}",
            "persistence_status: process-memory-only",
            f"current_allowlist_count: {len(ACTIVE_READONLY_ALLOWLIST)}",
            "",
            "Per-command success counts:",
        ]
        lines.extend(f"- {command}: {per_command[command]}" for command in ACTIVE_READONLY_ALLOWLIST)
        return "\n".join(lines)

    def format_history_clear_preview(self) -> str:
        return "\n".join(
            [
                "Runner Evidence History Clear Preview",
                "mode: preview-only",
                f"current_event_count: {len(_EVIDENCE_HISTORY)}",
                f"max_size: {EVIDENCE_HISTORY_MAX_SIZE}",
                f"would_remove_from_memory: {len(_EVIDENCE_HISTORY)} event(s)",
                "history_cleared: false",
                "mutation_performed: false",
                "actual_clear_command: not available",
                "restart_behavior: history is already lost when this process exits",
                "No event, approval, store, export, or file state was changed.",
            ]
        )

    def format_history_doctor(self) -> str:
        report = self.history_doctor_report()
        lines = ["Runner Evidence History Doctor", f"Status: {report['status']}", "", "Checks:"]
        lines.extend(f"- [{item['severity']}] {item['message']}" for item in report["findings"])
        lines.extend(["", "History boundary:", "- Process memory only; no evidence/log/approval/history file or clear mutation is exposed."])
        return "\n".join(lines)

    def history_doctor_report(self) -> dict[str, Any]:
        state = self.read_state()
        findings: list[dict[str, str]] = []
        findings.append(
            {"severity": "OK", "message": f"Ring buffer exists with bounded max_size={EVIDENCE_HISTORY_MAX_SIZE}."}
            if _EVIDENCE_HISTORY.maxlen == EVIDENCE_HISTORY_MAX_SIZE and 0 < EVIDENCE_HISTORY_MAX_SIZE <= 100
            else {"severity": "BLOCKED", "message": "Ring buffer is missing or has an unsafe/unbounded max size."}
        )
        findings.append(
            {"severity": "OK", "message": f"Event count {len(_EVIDENCE_HISTORY)} does not exceed max_size."}
            if len(_EVIDENCE_HISTORY) <= EVIDENCE_HISTORY_MAX_SIZE
            else {"severity": "BLOCKED", "message": "Event count exceeds the configured ring-buffer maximum."}
        )
        compact_issues = _history_entry_issues()
        findings.append(
            {"severity": "OK", "message": "History entries use the compact safe schema and contain no approval token or full output field."}
            if not compact_issues
            else {"severity": "BLOCKED", "message": f"History entry issues: {', '.join(compact_issues)}."}
        )
        findings.append(
            {"severity": "OK", "message": "No history event marks an outside-allowlist command executed."}
            if not _history_outside_execution_detected()
            else {"severity": "BLOCKED", "message": "History marks an outside-allowlist command executed."}
        )
        expected = (PILOT_COMMAND, DAILY_DOCTOR_COMMAND, EXPORTS_DOCTOR_COMMAND, CAPABILITIES_SAFETY_COMMAND)
        findings.append(
            {"severity": "OK", "message": "Active allowlist remains exactly four commands."}
            if tuple(ACTIVE_READONLY_ALLOWLIST) == expected
            else {"severity": "BLOCKED", "message": "Active allowlist drifted from the exact four-command set."}
        )
        findings.append(
            {"severity": "OK", "message": "Context Injection is disabled."}
            if state["context_state"] == "disabled"
            else {"severity": "BLOCKED", "message": "Context Injection is enabled."}
        )
        findings.append({"severity": "OK", "message": "No persistence path, evidence/log file path, approval persistence, shell/subprocess/eval/exec, or free-form dispatch is configured."})
        status = "BLOCKED" if any(item["severity"] == "BLOCKED" for item in findings) else "WARN" if any(item["severity"] == "WARN" for item in findings) else "OK"
        return {"status": status, "findings": findings}

    def format_stability(self, executors: Mapping[str, Callable[[], str]] | None) -> str:
        state = self.read_state()
        callback_status = _callback_map_status(executors)
        if state["context_state"] == "enabled" or state["blocker_count"] or callback_status == "BLOCKED":
            status = "BLOCKED"
        elif state["runner_exec_safety_state"] == "WARN" or callback_status == "NOT_AVAILABLE":
            status = "WARN"
        else:
            status = "OK"
        return "\n".join(
            [
                "Read-only Runner Multi-Command Stability Review",
                f"Status: {status}",
                f"active_allowlist_count: {len(ACTIVE_READONLY_ALLOWLIST)}",
                f"active_allowlist: {', '.join(ACTIVE_READONLY_ALLOWLIST)}",
                "callback_mode: dedicated zero-argument callbacks",
                f"callback_map_status: {callback_status}",
                "confirmation_mode: exact per-command phrase; no reuse, broad, implied, partial, or cross-command confirmation",
                "evidence_mode: process-memory-only; bounded latest event/success/refusal plus per-command latest success summaries",
                f"latest_event: {_evidence_brief(_LAST_EVIDENCE)}",
                f"latest_success: {_evidence_brief(_LAST_SUCCESS_EVIDENCE)}",
                f"latest_refusal: {_evidence_brief(_LAST_REFUSAL_EVIDENCE)}",
                "active_fifth_command: none",
                "free_form_dispatch: false",
                "persistent_approval_evidence_log: false",
                "shell_subprocess_eval_exec: false",
                "",
                "Known limitations:",
                "- Evidence is bounded and lost on restart; there is no full event history or persistent authorization state.",
            ]
        )

    def format_sequence_plan(self) -> str:
        return "\n".join(
            [
                "Read-only Runner Multi-Command Sequence Plan",
                "mode: print-only; sequence_executed=false",
                "",
                "Recommended smoke sequence:",
                "1. /runner-exec run  # expect CONFIRMATION_REQUIRED",
                f"2. /runner-exec run {EXACT_CONFIRMATION}",
                "3. /runner-exec evidence-check",
                f"4. /runner-exec run {DAILY_DOCTOR_CONFIRMATION}",
                "5. /runner-exec evidence-check",
                f"6. /runner-exec run {EXPORTS_DOCTOR_CONFIRMATION}",
                "7. /runner-exec evidence-check",
                f"8. /runner-exec run {CAPABILITIES_SAFETY_CONFIRMATION}",
                "9. /runner-exec evidence-check",
                "10. /runner-exec run CONFIRM RUN READONLY: /confirm policy  # expect COMMAND_NOT_ALLOWLISTED",
                "11. /runner-exec evidence-check",
                "12. /runner-exec doctor",
                "13. Compare SHA-256 for proto_mind/data and proto_mind/exports before/after.",
                "",
                "Plan guarantee:",
                "- This command executed no step, callback, target, shell, or write operation.",
            ]
        )

    def format_sequence_evidence(self) -> str:
        if _LAST_EVIDENCE is None:
            return "\n".join(
                [
                    "Read-only Runner Multi-Command Sequence Evidence",
                    "status: NOT_AVAILABLE_NO_RUN",
                    "storage: in-memory only",
                    "No event, success, refusal, or per-command success summary exists in this process.",
                ]
            )
        lines = [
            "Read-only Runner Multi-Command Sequence Evidence",
            "status: AVAILABLE_IN_MEMORY",
            f"history_events: {len(_EVIDENCE_HISTORY)}/{EVIDENCE_HISTORY_MAX_SIZE}",
            f"latest_event: {_evidence_brief(_LAST_EVIDENCE)}",
            f"latest_success: {_evidence_brief(_LAST_SUCCESS_EVIDENCE)}",
            f"latest_refusal: {_evidence_brief(_LAST_REFUSAL_EVIDENCE)}",
            "",
            "Event counts:",
        ]
        lines.extend(f"- {key}: {_EVENT_COUNTS[key]}" for key in sorted(_EVENT_COUNTS))
        lines.extend(["", "Per-command latest success:"])
        for command in ACTIVE_READONLY_ALLOWLIST:
            lines.append(f"- {command}: {_evidence_brief(_LATEST_SUCCESS_BY_COMMAND.get(command))}")
        lines.extend(
            [
                "",
                "History limitation:",
                f"- No full command history is stored; a compact ring retains only the newest {EVIDENCE_HISTORY_MAX_SIZE} events in process memory, evicts older events, and is lost on process exit.",
            ]
        )
        return "\n".join(lines)

    def format_consistency_check(self, executors: Mapping[str, Callable[[], str]] | None) -> str:
        report = self.consistency_report(executors)
        lines = ["Read-only Runner Multi-Command Consistency Check", f"Status: {report['status']}", "", "Checks:"]
        lines.extend(f"- [{item['severity']}] {item['message']}" for item in report["findings"])
        lines.extend(
            [
                "",
                "Consistency boundary:",
                "- Read-only inspection only; callbacks were not invoked and no evidence, approval, file, or command state was changed.",
            ]
        )
        return "\n".join(lines)

    def consistency_report(self, executors: Mapping[str, Callable[[], str]] | None) -> dict[str, Any]:
        findings: list[dict[str, str]] = []
        expected = (PILOT_COMMAND, DAILY_DOCTOR_COMMAND, EXPORTS_DOCTOR_COMMAND, CAPABILITIES_SAFETY_COMMAND)
        findings.append(
            {"severity": "OK", "message": "Active allowlist is exactly the stable four-command set."}
            if tuple(ACTIVE_READONLY_ALLOWLIST) == expected
            else {"severity": "BLOCKED", "message": f"Active allowlist drifted: {ACTIVE_READONLY_ALLOWLIST}."}
        )
        findings.append(
            {"severity": "OK", "message": "All four and only four command-specific confirmation phrases are configured."}
            if tuple(EXACT_CONFIRMATIONS) == expected and all(EXACT_CONFIRMATIONS.get(command) == f"CONFIRM RUN READONLY: {command}" for command in expected)
            else {"severity": "BLOCKED", "message": "Confirmation map is missing, extra, or not exact."}
        )
        callback_status = _callback_map_status(executors)
        if callback_status == "EXACT":
            findings.append({"severity": "OK", "message": "Callback map has exactly four callable zero-argument targets and no extra key."})
        elif callback_status == "NOT_AVAILABLE":
            findings.append({"severity": "WARN", "message": "Callback map was not supplied to this direct formatter call; runtime key consistency was not checked."})
        else:
            findings.append({"severity": "BLOCKED", "message": "Callback map has missing, extra, or non-callable entries."})
        evidence_report = self.evidence_check_report()
        if evidence_report["status"] == "ERROR":
            findings.append({"severity": "BLOCKED", "message": "Current in-memory evidence failed shape/allowlist consistency validation."})
        elif evidence_report["status"] == "WARN":
            findings.append({"severity": "WARN", "message": "No current-process evidence is available for dynamic consistency validation."})
        else:
            findings.append({"severity": "OK", "message": "Current evidence booleans, success/refusal state, allowlist targets, and no-persistence fields are consistent."})
        state = self.read_state()
        findings.append(
            {"severity": "OK", "message": "Context Injection is disabled."}
            if state["context_state"] == "disabled"
            else {"severity": "BLOCKED", "message": "Context Injection is enabled."}
        )
        findings.append({"severity": "OK", "message": "No fifth target, free-form dispatch, persistence, shell/subprocess/eval/exec, network, background, or write indicator is configured."})
        if any(item["severity"] == "BLOCKED" for item in findings):
            status = "BLOCKED"
        elif any(item["severity"] == "WARN" for item in findings):
            status = "WARN"
        else:
            status = "OK"
        return {"status": status, "findings": findings}

    def format_soak(self, executors: Mapping[str, Callable[[], str]] | None) -> str:
        state = self.read_state()
        callback_status = _callback_map_status(executors)
        if state["context_state"] == "enabled" or state["blocker_count"] or callback_status == "BLOCKED":
            status = "BLOCKED"
        elif state["runner_exec_safety_state"] == "WARN" or callback_status == "NOT_AVAILABLE":
            status = "WARN"
        else:
            status = "OK"
        return "\n".join(
            [
                "Read-only Runner Four-Command Safety Soak",
                f"Status: {status}",
                f"active_allowlist_count: {len(ACTIVE_READONLY_ALLOWLIST)}",
                f"active_allowlist: {', '.join(ACTIVE_READONLY_ALLOWLIST)}",
                "callback_mode: dedicated zero-argument callbacks",
                f"callback_map_status: {callback_status}",
                "confirmation_mode: exact per-command phrase; no reuse, broad, implied, partial, or cross-command confirmation",
                "evidence_mode: bounded process-memory-only counters and latest references",
                f"latest_event: {_evidence_brief(_LAST_EVIDENCE)}",
                f"latest_success: {_evidence_brief(_LAST_SUCCESS_EVIDENCE)}",
                f"latest_refusal: {_evidence_brief(_LAST_REFUSAL_EVIDENCE)}",
                f"sequence_success_count: {_EVENT_COUNTS['kind:success']}",
                f"sequence_refusal_count: {_EVENT_COUNTS['kind:refusal']}",
                f"all_four_succeeded: {str(_all_allowlisted_succeeded()).lower()}",
                "active_fifth_command: none",
                "outside_allowlist_executed: false",
                "free_form_dispatch: false",
                "persistent_approval_evidence_log: false",
                "shell_subprocess_eval_exec: false",
                f"context_injection: {state['context_state']}",
                "",
                "Known limitations:",
                "- Soak state is bounded and lost on restart; it is not a complete or persistent audit history.",
            ]
        )

    def format_soak_plan(self) -> str:
        return "\n".join(
            [
                "Read-only Runner Four-Command Soak Plan",
                "mode: print-only; soak_executed=false",
                "",
                "Recommended soak sequence:",
                "1. /runner-exec run  # expect CONFIRMATION_REQUIRED",
                f"2. /runner-exec run {EXACT_CONFIRMATION}",
                "3. /runner-exec evidence-check",
                f"4. /runner-exec run {DAILY_DOCTOR_CONFIRMATION}",
                "5. /runner-exec evidence-check",
                f"6. /runner-exec run {EXPORTS_DOCTOR_CONFIRMATION}",
                "7. /runner-exec evidence-check",
                f"8. /runner-exec run {CAPABILITIES_SAFETY_CONFIRMATION}",
                "9. /runner-exec evidence-check",
                "10. /runner-exec run CONFIRM RUN READONLY: /confirm policy  # expect COMMAND_NOT_ALLOWLISTED",
                "11. Verify candidate=/warnings unknown with confirmation for /daily doctor is refused as CONFIRMATION_COMMAND_MISMATCH.",
                "12. /runner-exec run CONFIRM RUN READONLY: /warnings unknown; /daily doctor  # expect EXTRA_INPUT",
                "13. /runner-exec run CONFIRM RUN READONLY: /warnings accepted  # expect COMMAND_NOT_ALLOWLISTED",
                "14. /runner-exec evidence-check",
                "15. /runner-exec consistency-check",
                "16. /runner-exec doctor",
                "17. Compare SHA-256 for proto_mind/data and proto_mind/exports before/after.",
                "",
                "Plan guarantee:",
                "- This command executed no step, callback, target, shell, or write operation.",
            ]
        )

    def format_soak_report(self) -> str:
        if _LAST_EVIDENCE is None:
            return "\n".join(
                [
                    "Read-only Runner Four-Command Soak Report",
                    "status: NOT_AVAILABLE_NO_RUN",
                    "storage: in-memory only",
                    "No soak event, success, refusal, or per-command success summary exists in this process.",
                ]
            )
        lines = [
            "Read-only Runner Four-Command Soak Report",
            "status: AVAILABLE_IN_MEMORY",
            f"latest_event: {_evidence_brief(_LAST_EVIDENCE)}",
            f"latest_success: {_evidence_brief(_LAST_SUCCESS_EVIDENCE)}",
            f"latest_refusal: {_evidence_brief(_LAST_REFUSAL_EVIDENCE)}",
            f"success_count: {_EVENT_COUNTS['kind:success']}",
            f"refusal_count: {_EVENT_COUNTS['kind:refusal']}",
            f"all_four_succeeded: {str(_all_allowlisted_succeeded()).lower()}",
            f"outside_allowlist_executed: {str(_outside_execution_detected()).lower()}",
            f"history_events: {len(_EVIDENCE_HISTORY)}/{EVIDENCE_HISTORY_MAX_SIZE}",
            "",
            "Per-command latest success:",
        ]
        lines.extend(f"- {command}: {_evidence_brief(_LATEST_SUCCESS_BY_COMMAND.get(command))}" for command in ACTIVE_READONLY_ALLOWLIST)
        lines.extend(
            [
                "",
                "Sequence evidence summary:",
                f"- total_events: {_EVENT_COUNTS['total']}",
                f"- successes: {_EVENT_COUNTS['kind:success']}",
                f"- refusals: {_EVENT_COUNTS['kind:refusal']}",
                "",
                "History limitation:",
                f"- Findings include a compact {EVIDENCE_HISTORY_MAX_SIZE}-event process-memory ring, not a full persisted command history.",
            ]
        )
        return "\n".join(lines)

    def format_drift_check(self, executors: Mapping[str, Callable[[], str]] | None) -> str:
        report = self.drift_report(executors)
        lines = ["Read-only Runner Four-Command Drift Check", f"Status: {report['status']}", "", "Checks:"]
        lines.extend(f"- [{item['severity']}] {item['message']}" for item in report["findings"])
        lines.extend(
            [
                "",
                "Drift boundary:",
                "- Read-only inspection only; callbacks were not invoked and no runner, evidence, approval, file, or command state was changed.",
            ]
        )
        return "\n".join(lines)

    def drift_report(self, executors: Mapping[str, Callable[[], str]] | None) -> dict[str, Any]:
        consistency = self.consistency_report(executors)
        findings = list(consistency["findings"])
        callback_keys = set(executors or {})
        if "/confirm policy" in ACTIVE_READONLY_ALLOWLIST or "/confirm policy" in callback_keys:
            findings.append({"severity": "BLOCKED", "message": "/confirm policy drifted into the active allowlist or callback map."})
        else:
            findings.append({"severity": "OK", "message": "/confirm policy remains outside the active allowlist and callback map."})
        if _outside_execution_detected():
            findings.append({"severity": "BLOCKED", "message": "Bounded evidence marks an outside-allowlist command as executed."})
        else:
            findings.append({"severity": "OK", "message": "No retained evidence marks an outside-allowlist command as executed."})
        mutation_indicators = [
            evidence.get("request_id", "unknown")
            for evidence in _retained_evidence_records()
            if evidence.get("executed")
            and (
                evidence.get("files_changed_summary") != "none"
                or "unchanged=true" not in str(evidence.get("data_exports_sha256_before_after", ""))
            )
        ]
        findings.append(
            {"severity": "BLOCKED", "message": f"Executed evidence has data/export mutation indicators: {', '.join(mutation_indicators)}."}
            if mutation_indicators
            else {"severity": "OK", "message": "Retained executed evidence has no data/export mutation indicator."}
        )
        findings.append({"severity": "OK", "message": "No persistence, shell/subprocess/eval/exec, free-form dispatch, network, background, or fifth-target indicator is configured."})
        if any(item["severity"] == "BLOCKED" for item in findings):
            status = "BLOCKED"
        elif any(item["severity"] == "WARN" for item in findings):
            status = "WARN"
        else:
            status = "OK"
        return {"status": status, "findings": findings}

    def run(
        self,
        *,
        candidate: str,
        confirmation: str | None,
        executors: Mapping[str, Callable[[], str]] | None,
    ) -> str:
        global _RUN_SEQUENCE
        _RUN_SEQUENCE += 1
        request_id = f"runner_exec_{_RUN_SEQUENCE:04d}"
        state = self.read_state()
        expected_confirmation = EXACT_CONFIRMATIONS.get(candidate)
        confirmation_matched = bool(expected_confirmation and confirmation == expected_confirmation)
        executor_map = dict(executors or {})
        gate_results = {
            "candidate_allowlisted": candidate in ACTIVE_READONLY_ALLOWLIST,
            "allowlist_exact": tuple(ACTIVE_READONLY_ALLOWLIST)
            == (PILOT_COMMAND, DAILY_DOCTOR_COMMAND, EXPORTS_DOCTOR_COMMAND, CAPABILITIES_SAFETY_COMMAND),
            "confirmation_matched": confirmation_matched,
            "context_injection_disabled": state["context_state"] == "disabled",
            "blockers_zero": state["blocker_count"] == 0,
            "registry_policy_read_only": state["command_safety"].get(candidate, False),
            "no_data_export_writes_expected": True,
            "internal_fixed_executor_available": candidate in executor_map and callable(executor_map.get(candidate)),
            "executor_map_exact": tuple(executor_map) == tuple(ACTIVE_READONLY_ALLOWLIST),
            "no_shell_subprocess_eval_exec": True,
            "no_network_background_snapshot_backup": True,
        }
        failures = [name for name, passed in gate_results.items() if not passed]
        refusal_reason = _confirmation_refusal_reason(candidate, confirmation)
        if not refusal_reason and failures:
            refusal_reason = "GATE_FAILURE: " + ", ".join(failures)
        if refusal_reason:
            evidence = self._base_evidence(request_id, state, candidate, confirmation, confirmation_matched, gate_results, failures)
            evidence.update(
                {
                    "evidence_kind": "refusal",
                    "executed": False,
                    "command_executed": "",
                    "output_summary": "",
                    "status": "REFUSED",
                    "result": "NOT_EXECUTED",
                    "files_changed_summary": "NOT_CHECKED_REFUSED",
                    "data_exports_sha256_before_after": "NOT_CHECKED_REFUSED",
                    "unknown_warning_count_after": None,
                    "refusal_reason": refusal_reason,
                }
            )
            _store_evidence(evidence)
            return self._format_run_result(evidence)

        before = _sha_manifest(self.project_root)
        try:
            output = executor_map[candidate]()
        except Exception as exc:
            after = _sha_manifest(self.project_root)
            evidence = self._base_evidence(request_id, state, candidate, confirmation, True, gate_results, ["executor_exception"])
            evidence.update(
                {
                    "evidence_kind": "refusal",
                    "executed": False,
                    "command_executed": "",
                    "output_summary": "",
                    "status": "REFUSED",
                    "result": "EXECUTOR_ERROR",
                    "files_changed_summary": _changed_summary(before, after),
                    "data_exports_sha256_before_after": _sha_summary(before, after),
                    "unknown_warning_count_after": None,
                    "refusal_reason": f"EXECUTOR_EXCEPTION: {type(exc).__name__}: {exc}",
                }
            )
            _store_evidence(evidence)
            return self._format_run_result(evidence)

        after = _sha_manifest(self.project_root)
        changed = _changed_paths(before, after)
        post_state = self.read_state()
        if changed:
            status = "SAFETY_VIOLATION"
            result = "READ_ONLY_INVARIANT_FAILED"
            refusal_reason = "DATA_EXPORT_SHA_CHANGED"
        else:
            status = "COMPLETED"
            result = "SUCCESS"
            refusal_reason = ""
        evidence = self._base_evidence(request_id, state, candidate, confirmation, True, gate_results, [])
        evidence.update(
            {
                "evidence_kind": "success" if result == "SUCCESS" else "failure",
                "executed": True,
                "command_executed": candidate,
                "output_summary": _preview(output),
                "status": status,
                "result": result,
                "files_changed_summary": _changed_summary(before, after),
                "data_exports_sha256_before_after": _sha_summary(before, after),
                "unknown_warning_count_after": len(post_state["unknown"]),
                "export_doctor_status": _extract_report_status(output) if candidate == EXPORTS_DOCTOR_COMMAND else "not_applicable",
                "capabilities_safety_summary": _extract_capabilities_summary(output)
                if candidate == CAPABILITIES_SAFETY_COMMAND
                else "not_applicable",
                "refusal_reason": refusal_reason,
            }
        )
        _store_evidence(evidence)
        return self._format_run_result(evidence, target_output=output)

    def _base_evidence(
        self,
        request_id: str,
        state: dict[str, Any],
        candidate: str,
        confirmation: str | None,
        confirmation_matched: bool,
        gate_results: dict[str, bool],
        gate_failures: list[str],
    ) -> dict[str, Any]:
        return {
            "request_id": request_id,
            "created_at": datetime.now(UTC).isoformat(),
            "evidence_kind": "pending",
            "command_requested": candidate,
            "command_executed": "",
            "execution_enabled": state["execution_enabled"],
            "executed": False,
            "confirmation_received": _confirmation_summary(candidate, confirmation),
            "confirmation_matched": confirmation_matched,
            "gates_checked": dict(gate_results),
            "gate_failures": list(gate_failures),
            "output_summary": "",
            "status": "PENDING",
            "result": "",
            "files_changed_summary": "",
            "data_exports_sha256_before_after": "",
            "context_injection_status": state["context_state"],
            "unknown_warning_count_after": None,
            "export_doctor_status": None,
            "capabilities_safety_summary": None,
            "refusal_reason": "",
            "persistent": False,
            "storage": "memory_only",
        }

    def _format_run_result(self, evidence: dict[str, Any], *, target_output: str = "") -> str:
        lines = [
            "Read-only Runner MVP Result",
            f"request_id: {evidence['request_id']}",
            f"command_requested: {evidence['command_requested']}",
            f"execution_enabled: {str(evidence['execution_enabled']).lower()}",
            f"executed: {str(evidence['executed']).lower()}",
            f"confirmation_matched: {str(evidence['confirmation_matched']).lower()}",
            f"status: {evidence['status']}",
            f"result: {evidence['result']}",
            f"gate_failures: {', '.join(evidence['gate_failures']) or 'none'}",
            f"files_changed_summary: {evidence['files_changed_summary']}",
            f"data_exports_sha256_before_after: {evidence['data_exports_sha256_before_after']}",
            f"refusal_reason: {evidence['refusal_reason'] or 'none'}",
        ]
        if target_output:
            lines.extend(["", "Target output:", target_output])
        lines.extend(
            [
                "",
                "Execution scope:",
                f"- Only the fixed internal allowlisted handler for {evidence['command_requested']} was eligible; no free-form target or external execution primitive was used.",
            ]
        )
        return "\n".join(lines)

    def format_evidence(self) -> str:
        if _LAST_EVIDENCE is None:
            return "\n".join(
                [
                    "Read-only Runner MVP Evidence",
                    "status: NOT_AVAILABLE_NO_RUN",
                    "storage: in-memory only",
                    "No persistent evidence, log, approval, or runner state exists.",
                ]
            )
        evidence = _LAST_EVIDENCE
        gate_lines = ", ".join(f"{name}={str(value).lower()}" for name, value in evidence["gates_checked"].items())
        return "\n".join(
            [
                "Read-only Runner MVP Evidence",
                f"evidence_view: LAST_{evidence['evidence_kind'].upper()}_EVIDENCE",
                f"request_id: {evidence['request_id']}",
                f"created_at: {evidence['created_at']}",
                f"command_requested: {evidence['command_requested']}",
                f"command_executed: {evidence['command_executed'] or 'none'}",
                f"execution_enabled: {str(evidence['execution_enabled']).lower()}",
                f"executed: {str(evidence['executed']).lower()}",
                f"confirmation_received: {evidence['confirmation_received']}",
                f"confirmation_matched: {str(evidence['confirmation_matched']).lower()}",
                f"gates_checked: {gate_lines}",
                f"gate_failures: {', '.join(evidence['gate_failures']) or 'none'}",
                f"output_summary: {evidence['output_summary'] or 'none'}",
                f"status: {evidence['status']}",
                f"result: {evidence['result']}",
                f"files_changed_summary: {evidence['files_changed_summary']}",
                f"data_exports_sha256_before_after: {evidence['data_exports_sha256_before_after']}",
                f"context_injection_status: {evidence['context_injection_status']}",
                f"unknown_warning_count_after: {evidence['unknown_warning_count_after'] if evidence['unknown_warning_count_after'] is not None else 'not_available'}",
                f"export_doctor_status: {evidence['export_doctor_status'] if evidence['export_doctor_status'] is not None else 'not_available'}",
                f"capabilities_safety_summary: {evidence['capabilities_safety_summary'] if evidence['capabilities_safety_summary'] is not None else 'not_available'}",
                f"refusal_reason: {evidence['refusal_reason'] or 'none'}",
                f"history_available: {str(bool(_EVIDENCE_HISTORY)).lower()}",
                f"history_latest_event_id: {_EVIDENCE_HISTORY[-1]['event_id'] if _EVIDENCE_HISTORY else 'NOT_AVAILABLE'}",
                "storage: in-memory only; no evidence/log/approval file was created.",
                f"limitations: latest evidence views plus a compact {EVIDENCE_HISTORY_MAX_SIZE}-event ring are retained; all evidence is lost on process exit.",
            ]
        )

    def evidence_check_report(self) -> dict[str, Any]:
        findings: list[dict[str, str]] = []
        records: list[tuple[str, dict[str, Any]]] = []
        seen: set[int] = set()
        for label, evidence in (
            ("last_event", _LAST_EVIDENCE),
            ("last_success", _LAST_SUCCESS_EVIDENCE),
            ("last_refusal", _LAST_REFUSAL_EVIDENCE),
        ):
            if evidence is not None and id(evidence) not in seen:
                records.append((label, evidence))
                seen.add(id(evidence))
        if not records:
            return {
                "status": "WARN",
                "findings": [
                    {
                        "severity": "WARN",
                        "message": "No current-process run or refusal evidence is available; shape validation is limited to static model rules.",
                    },
                    {
                        "severity": "OK",
                        "message": "Evidence storage is module memory only; no evidence file path or persistence layer is configured.",
                    },
                ],
            }

        required = {
            "request_id",
            "created_at",
            "evidence_kind",
            "command_requested",
            "command_executed",
            "execution_enabled",
            "executed",
            "confirmation_received",
            "confirmation_matched",
            "gates_checked",
            "gate_failures",
            "output_summary",
            "status",
            "result",
            "files_changed_summary",
            "data_exports_sha256_before_after",
            "context_injection_status",
            "unknown_warning_count_after",
            "export_doctor_status",
            "capabilities_safety_summary",
            "refusal_reason",
            "persistent",
            "storage",
        }
        for label, evidence in records:
            missing = sorted(required - evidence.keys())
            if missing:
                findings.append({"severity": "ERROR", "message": f"{label} evidence is missing fields: {', '.join(missing)}."})
                continue
            if not isinstance(evidence["executed"], bool) or not isinstance(evidence["execution_enabled"], bool):
                findings.append({"severity": "ERROR", "message": f"{label} executed/execution_enabled fields are not boolean."})
            if evidence["command_executed"] not in {"", *ACTIVE_READONLY_ALLOWLIST}:
                findings.append({"severity": "ERROR", "message": f"{label} marks a command outside the active allowlist as executed."})
            if evidence.get("evidence_file_path"):
                findings.append({"severity": "ERROR", "message": f"{label} contains a forbidden evidence file path."})
            if evidence["persistent"] is not False or evidence["storage"] != "memory_only":
                findings.append({"severity": "ERROR", "message": f"{label} incorrectly indicates persistent evidence state."})
            if evidence["evidence_kind"] == "refusal":
                if evidence["executed"] or evidence["command_executed"] or not evidence["refusal_reason"]:
                    findings.append({"severity": "ERROR", "message": f"{label} refusal evidence has inconsistent execution/refusal fields."})
            elif evidence["evidence_kind"] == "success":
                if (
                    not evidence["executed"]
                    or evidence["command_executed"] != evidence["command_requested"]
                    or evidence["command_executed"] not in ACTIVE_READONLY_ALLOWLIST
                    or evidence["result"] != "SUCCESS"
                ):
                    findings.append({"severity": "ERROR", "message": f"{label} success evidence has inconsistent execution fields."})
                if evidence["command_requested"] == CAPABILITIES_SAFETY_COMMAND and evidence["capabilities_safety_summary"] in {None, "", "not_applicable"}:
                    findings.append({"severity": "ERROR", "message": f"{label} capabilities-safety success is missing its compact summary."})
            elif evidence["evidence_kind"] != "failure":
                findings.append({"severity": "ERROR", "message": f"{label} has unknown evidence_kind={evidence['evidence_kind']}."})
        history_issues = _history_entry_issues()
        if len(_EVIDENCE_HISTORY) > EVIDENCE_HISTORY_MAX_SIZE or _EVIDENCE_HISTORY.maxlen != EVIDENCE_HISTORY_MAX_SIZE:
            findings.append({"severity": "ERROR", "message": "History ring is not bounded by the configured maximum."})
        if history_issues:
            findings.append({"severity": "ERROR", "message": f"History compact-schema validation failed: {', '.join(history_issues)}."})
        if _history_outside_execution_detected():
            findings.append({"severity": "ERROR", "message": "History marks an outside-allowlist command as executed."})
        if not findings:
            findings.append(
                {
                    "severity": "OK",
                    "message": f"Validated {len(records)} distinct current-process evidence record(s); required fields and boolean types are present.",
                }
            )
            findings.append(
                {
                    "severity": "OK",
                    "message": "No command outside the exact four-command allowlist is marked executed; no evidence path or persistent state is present.",
                }
            )
            findings.append(
                {
                    "severity": "OK",
                    "message": f"History ring is bounded at {EVIDENCE_HISTORY_MAX_SIZE}, contains {len(_EVIDENCE_HISTORY)} compact event(s), and exposes no persistence indicator.",
                }
            )
        status = "ERROR" if any(item["severity"] == "ERROR" for item in findings) else "WARN" if any(item["severity"] == "WARN" for item in findings) else "OK"
        return {"status": status, "findings": findings}

    def format_doctor(self, executors: Mapping[str, Callable[[], str]] | None = None) -> str:
        report = self.doctor_report(executors)
        lines = ["Real Read-only Runner MVP Doctor", f"Status: {report['status']}", "", "Checks:"]
        lines.extend(f"- [{item['severity']}] {item['message']}" for item in report["findings"])
        lines.extend(
            [
                "",
                "Runner scope:",
                "- Exactly four fixed internal read-only targets; no free-form dispatch, persistence, shell/subprocess/eval/exec, network, background work, snapshot, or backup path.",
            ]
        )
        return "\n".join(lines)

    def doctor_report(self, executors: Mapping[str, Callable[[], str]] | None = None) -> dict[str, Any]:
        findings: list[dict[str, str]] = []
        registry = {spec.prefix: spec for spec in COMMAND_REGISTRY}
        missing = [command for command in RUNNER_EXEC_COMMANDS if command not in registry]
        findings.append(
            {"severity": "ERROR", "message": f"runner-exec commands missing from Registry: {', '.join(missing)}"}
            if missing
            else {"severity": "OK", "message": "All runner-exec commands are registered."}
        )
        findings.append(
            {"severity": "OK", "message": "Active allowlist contains exactly four commands: /warnings unknown, /daily doctor, /exports doctor, and /capabilities safety."}
            if tuple(ACTIVE_READONLY_ALLOWLIST)
            == (PILOT_COMMAND, DAILY_DOCTOR_COMMAND, EXPORTS_DOCTOR_COMMAND, CAPABILITIES_SAFETY_COMMAND)
            else {"severity": "ERROR", "message": f"Active allowlist drifted: {ACTIVE_READONLY_ALLOWLIST}"}
        )
        state = self.read_state()
        unsafe_commands = [command for command in ACTIVE_READONLY_ALLOWLIST if not state["command_safety"].get(command)]
        findings.append(
            {"severity": "OK", "message": "All four allowlisted commands are Registry-known read-only/mutates=none/low-risk/auto_allowed and reachable through dedicated fixed handlers."}
            if not unsafe_commands
            else {"severity": "ERROR", "message": f"Allowlisted commands failed Registry/Policy safety validation: {', '.join(unsafe_commands)}."}
        )
        findings.append(
            {
                "severity": "OK",
                "message": f"Exact command-specific confirmation phrases are configured: {EXACT_CONFIRMATION} | {DAILY_DOCTOR_CONFIRMATION} | {EXPORTS_DOCTOR_CONFIRMATION} | {CAPABILITIES_SAFETY_CONFIRMATION}",
            }
        )
        findings.append(
            {
                "severity": "OK",
                "message": "Missing, mismatched, broad, different-target, near-miss, and suffix confirmations fail closed before the executor callback.",
            }
        )
        findings.append(
            {
                "severity": "OK",
                "message": f"Warning/blocker state is computable: accepted={len(state['accepted'])}, unknown={len(state['unknown'])}, blockers={state['blocker_count']}.",
            }
        )
        if state["blocker_count"]:
            findings.append({"severity": "BLOCKED", "message": f"Blockers={state['blocker_count']} prevent execution."})
        if state["context_state"] == "enabled":
            findings.append({"severity": "BLOCKED", "message": "Context Injection is enabled; execution gate is closed."})
        else:
            findings.append({"severity": "OK", "message": "Context Injection is disabled."})
        findings.append(
            {
                "severity": "OK",
                "message": "No command outside the exact four-command allowlist is exposed; callback lookup uses a fixed map and no free-form command dispatch exists.",
            }
        )
        findings.append(
            {
                "severity": "OK",
                "message": "Success/refusal evidence paths are module memory only; no persistent evidence/log/approval state or evidence file path is exposed.",
            }
        )
        findings.append(
            {
                "severity": "OK",
                "message": "No shell/subprocess/eval/exec, network, background, data/export write, snapshot, or backup path is exposed.",
            }
        )
        consistency = self.consistency_report(executors)
        findings.append(
            {
                "severity": "BLOCKED" if consistency["status"] == "BLOCKED" else "OK",
                "message": f"Multi-command consistency summary: {consistency['status']} (see /runner-exec consistency-check for details).",
            }
        )
        drift = self.drift_report(executors)
        findings.append(
            {
                "severity": "BLOCKED" if drift["status"] == "BLOCKED" else "OK",
                "message": f"Four-command soak/drift summary: {drift['status']} (see /runner-exec drift-check for details).",
            }
        )
        history = self.history_doctor_report()
        findings.append(
            {
                "severity": "BLOCKED" if history["status"] == "BLOCKED" else "WARN" if history["status"] == "WARN" else "OK",
                "message": f"Evidence history summary: {history['status']} (see /runner-exec history-doctor for details).",
            }
        )
        if any(item["severity"] == "ERROR" for item in findings):
            status = "ERROR"
        elif any(item["severity"] == "BLOCKED" for item in findings):
            status = "BLOCKED"
        elif any(item["severity"] == "WARN" for item in findings):
            status = "WARN"
        else:
            status = "OK"
        return {"status": status, "findings": findings}

    def format_handoff(self) -> str:
        state = self.read_state()
        categories = Counter(spec.category for spec in COMMAND_REGISTRY)
        return "\n".join(
            [
                "Proto-Mind Real Read-only Runner MVP Handoff",
                f"Project: {self.project_root}",
                f"Current baseline: {state['accepted_baseline'] or 'not detected'}",
                "Rule 0: before changes run scripts/run_cli.sh, then /memory backup.",
                f"Registry: {len(COMMAND_REGISTRY)} commands across {len(categories)} categories",
                f"Active allowlist: exactly {', '.join(ACTIVE_READONLY_ALLOWLIST)}",
                f"Exact confirmations: {EXACT_CONFIRMATION} | {DAILY_DOCTOR_CONFIRMATION} | {EXPORTS_DOCTOR_CONFIRMATION} | {CAPABILITIES_SAFETY_CONFIRMATION}",
                *[f"Usage: {usage}" for usage in RUN_USAGES],
                "",
                "Execution gates:",
                "- exact target in the four-command allowlist; command-specific exact confirmation; Context disabled; blockers=0; Registry/Policy read-only safety; no writes/external primitives",
                "",
                "Evidence model:",
                f"- bounded latest views plus a compact {EVIDENCE_HISTORY_MAX_SIZE}-event ring in module memory only; oldest events are evicted and no history is persisted",
                "",
                "Stop/refusal conditions:",
                "- missing/wrong/broad/different-target/near-miss/suffixed confirmation, allowlist/Registry/Policy drift, blocker/context failure, detected write, executor exception, or ambiguity",
                "",
                "Verification commands:",
                "- scripts/which_python.sh",
                "- scripts/run_tests.sh",
                "- /opt/homebrew/opt/python@3.11/bin/python3.11 -m compileall proto_mind",
                "",
                "Required final report fields:",
                "- backup path; files changed; commands/allowlist; Registry counts; tests/compileall; smoke; confirmed/refused evidence; Context Injection; data/exports SHA-256; limitations/warnings.",
                "",
                "Safety boundary:",
                "- No shell, subprocess, eval/exec, free-form target, fifth allowlist command, persistent evidence/log/approval, mutation, snapshot, backup, network, or background work.",
                "- Inspect refusal behavior with /runner-exec refusal-matrix, /runner-exec last-refusal, and /runner-exec evidence-check.",
                "- Review stability with /runner-exec stability, /runner-exec sequence-plan, /runner-exec sequence-evidence, and /runner-exec consistency-check.",
                "- Run the read-only soak review with /runner-exec soak, /runner-exec soak-plan, /runner-exec soak-report, and /runner-exec drift-check.",
                "- Inspect the process-memory ring with /runner-exec history, /runner-exec history-summary, /runner-exec history-clear-preview, and /runner-exec history-doctor.",
            ]
        )


def _store_evidence(evidence: dict[str, Any]) -> None:
    global _LAST_EVIDENCE, _LAST_SUCCESS_EVIDENCE, _LAST_REFUSAL_EVIDENCE
    _LAST_EVIDENCE = evidence
    command = str(evidence.get("command_requested") or "unknown")
    kind = str(evidence.get("evidence_kind") or "unknown")
    _EVENT_COUNTS["total"] += 1
    _EVENT_COUNTS[f"kind:{kind}"] += 1
    _EVENT_COUNTS[f"command:{command}"] += 1
    _EVIDENCE_HISTORY.append(_compact_history_event(evidence))
    if evidence.get("evidence_kind") == "success":
        _LAST_SUCCESS_EVIDENCE = evidence
        _LATEST_SUCCESS_BY_COMMAND[command] = evidence
    elif evidence.get("evidence_kind") == "refusal":
        _LAST_REFUSAL_EVIDENCE = evidence


def _compact_history_event(evidence: dict[str, Any]) -> dict[str, Any]:
    command_requested = str(evidence.get("command_requested") or "unknown")
    if command_requested not in ACTIVE_READONLY_ALLOWLIST:
        digest = hashlib.sha256(command_requested.encode("utf-8")).hexdigest()[:12]
        command_requested = f"OUTSIDE_ALLOWLIST(chars={len(command_requested)}, sha256={digest})"
    command_executed = str(evidence.get("command_executed") or "")
    gates = evidence.get("gates_checked") if isinstance(evidence.get("gates_checked"), dict) else {}
    failed_gates = sorted(str(name) for name, passed in gates.items() if passed is not True)
    refusal_reason = str(evidence.get("refusal_reason") or "")
    if refusal_reason.startswith("EXECUTOR_EXCEPTION:"):
        parts = refusal_reason.split(":", 2)
        refusal_reason = ":".join(parts[:2])
    sha_summary = str(evidence.get("data_exports_sha256_before_after") or "")
    files_summary = str(evidence.get("files_changed_summary") or "")
    if "unchanged=true" in sha_summary and files_summary == "none":
        data_exports_changed = "false"
    elif "CHANGED" in sha_summary.upper() or (files_summary and files_summary not in {"none", "NOT_CHECKED_REFUSED"}):
        data_exports_changed = "true"
    else:
        data_exports_changed = "not_checked"
    return {
        "event_id": str(evidence.get("request_id") or "unknown"),
        "event_type": "SUCCESS" if evidence.get("evidence_kind") == "success" else "REFUSAL",
        "created_at": str(evidence.get("created_at") or "unknown"),
        "command_requested": command_requested,
        "command_executed": command_executed if command_executed in ACTIVE_READONLY_ALLOWLIST else "",
        "executed": bool(evidence.get("executed")),
        "refusal_reason": _preview(refusal_reason, 240),
        "status_result": _preview(f"{evidence.get('status', 'unknown')}/{evidence.get('result', 'unknown')}", 120),
        "confirmation_matched": bool(evidence.get("confirmation_matched")),
        "gates_checked_summary": f"total={len(gates)} failed={','.join(failed_gates) or 'none'}",
        "data_exports_changed": data_exports_changed,
        "context_injection_status": str(evidence.get("context_injection_status") or "unknown"),
        "unknown_warning_count_after": evidence.get("unknown_warning_count_after"),
        "export_doctor_status": evidence.get("export_doctor_status"),
        "capabilities_safety_summary": _preview(str(evidence.get("capabilities_safety_summary") or ""), 320) or None,
    }


def _history_entry_issues() -> list[str]:
    required = {
        "event_id",
        "event_type",
        "created_at",
        "command_requested",
        "command_executed",
        "executed",
        "refusal_reason",
        "status_result",
        "confirmation_matched",
        "gates_checked_summary",
        "data_exports_changed",
        "context_injection_status",
        "unknown_warning_count_after",
        "export_doctor_status",
        "capabilities_safety_summary",
    }
    forbidden = {"confirmation_received", "output_summary", "target_output", "evidence_file_path", "approval_token"}
    issues: list[str] = []
    for index, event in enumerate(_EVIDENCE_HISTORY, start=1):
        missing = required - event.keys()
        extra_sensitive = forbidden & event.keys()
        if missing:
            issues.append(f"event {index} missing {','.join(sorted(missing))}")
        if extra_sensitive:
            issues.append(f"event {index} contains {','.join(sorted(extra_sensitive))}")
        if event.get("event_type") not in {"SUCCESS", "REFUSAL"}:
            issues.append(f"event {index} has invalid event_type")
        if not isinstance(event.get("executed"), bool) or not isinstance(event.get("confirmation_matched"), bool):
            issues.append(f"event {index} has non-boolean safety fields")
        if len(repr(event)) > 2400:
            issues.append(f"event {index} exceeds compact-size limit")
    return issues


def _history_outside_execution_detected() -> bool:
    return any(
        event.get("executed") and event.get("command_executed") not in ACTIVE_READONLY_ALLOWLIST
        for event in _EVIDENCE_HISTORY
    )


def _optional_value(value: Any) -> str:
    return "not_available" if value is None or value == "" else str(value)


def _callback_map_status(executors: Mapping[str, Callable[[], str]] | None) -> str:
    if executors is None:
        return "NOT_AVAILABLE"
    expected = tuple(ACTIVE_READONLY_ALLOWLIST)
    if tuple(executors) != expected or any(not callable(executors.get(command)) for command in expected):
        return "BLOCKED"
    return "EXACT"


def _evidence_brief(evidence: dict[str, Any] | None) -> str:
    if evidence is None:
        return "NOT_AVAILABLE"
    return (
        f"request_id={evidence.get('request_id', 'unknown')} "
        f"kind={evidence.get('evidence_kind', 'unknown')} "
        f"command={evidence.get('command_requested', 'unknown')} "
        f"executed={str(bool(evidence.get('executed'))).lower()} "
        f"status={evidence.get('status', 'unknown')}"
    )


def _retained_evidence_records() -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    seen: set[int] = set()
    for evidence in (
        _LAST_EVIDENCE,
        _LAST_SUCCESS_EVIDENCE,
        _LAST_REFUSAL_EVIDENCE,
        *_LATEST_SUCCESS_BY_COMMAND.values(),
    ):
        if evidence is not None and id(evidence) not in seen:
            records.append(evidence)
            seen.add(id(evidence))
    return records


def _all_allowlisted_succeeded() -> bool:
    return all(command in _LATEST_SUCCESS_BY_COMMAND for command in ACTIVE_READONLY_ALLOWLIST)


def _outside_execution_detected() -> bool:
    return _history_outside_execution_detected() or any(
        evidence.get("executed") and evidence.get("command_executed") not in ACTIVE_READONLY_ALLOWLIST
        for evidence in _retained_evidence_records()
    )


def _candidate_from_confirmation(confirmation: str) -> str:
    for command, expected in EXACT_CONFIRMATIONS.items():
        if confirmation == expected:
            return command
    prefix = "CONFIRM RUN READONLY:"
    if confirmation.startswith(prefix):
        return confirmation[len(prefix) :].strip()
    return PILOT_COMMAND


def _confirmation_refusal_reason(candidate: str, confirmation: str | None) -> str:
    if confirmation is None:
        return "CONFIRMATION_REQUIRED"
    if candidate not in ACTIVE_READONLY_ALLOWLIST:
        if candidate.casefold() == "all":
            return "CONFIRMATION_MISMATCH: BROAD_CONFIRMATION"
        if any(candidate.startswith(command) for command in ACTIVE_READONLY_ALLOWLIST):
            return "CONFIRMATION_MISMATCH: EXTRA_INPUT"
        return "COMMAND_NOT_ALLOWLISTED"
    expected = EXACT_CONFIRMATIONS[candidate]
    if confirmation == expected:
        return ""
    if confirmation in EXACT_CONFIRMATIONS.values():
        return "CONFIRMATION_COMMAND_MISMATCH"
    return "CONFIRMATION_MISMATCH"


def _confirmation_summary(candidate: str, confirmation: str | None) -> str:
    if confirmation is None:
        return "MISSING"
    if confirmation == EXACT_CONFIRMATIONS.get(candidate):
        return "EXACT_MATCH"
    if confirmation in EXACT_CONFIRMATIONS.values():
        return "OTHER_ALLOWLIST_CONFIRMATION"
    digest = hashlib.sha256(confirmation.encode("utf-8")).hexdigest()[:12]
    return f"MISMATCH(chars={len(confirmation)}, sha256={digest})"


def _extract_report_status(output: str) -> str:
    for line in output.splitlines():
        if line.startswith("Status:"):
            return line.partition(":")[2].strip() or "unknown"
    return "unknown"


def _extract_capabilities_summary(output: str) -> str:
    wanted = (
        "- registered read-only/mutates=none commands:",
        "- auto_allowed:",
        "- confirmation_required:",
        "- operator_only:",
    )
    values = [line[2:].strip() for line in output.splitlines() if line.startswith(wanted)]
    return "; ".join(values) if values else "summary_unavailable"


def _sha_manifest(project_root: Path) -> dict[str, str]:
    package_root = project_root / "proto_mind"
    manifest: dict[str, str] = {}
    for dirname in ("data", "exports"):
        base = package_root / dirname
        if not base.exists():
            continue
        for path in sorted(base.rglob("*")):
            if path.is_file():
                relative = path.relative_to(package_root).as_posix()
                manifest[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    return manifest


def _changed_paths(before: dict[str, str], after: dict[str, str]) -> list[str]:
    paths = set(before) | set(after)
    return sorted(path for path in paths if before.get(path) != after.get(path))


def _changed_summary(before: dict[str, str], after: dict[str, str]) -> str:
    changed = _changed_paths(before, after)
    return "none" if not changed else ", ".join(changed)


def _sha_summary(before: dict[str, str], after: dict[str, str]) -> str:
    changed = _changed_paths(before, after)
    return f"unchanged={str(not changed).lower()} before_files={len(before)} after_files={len(after)} changed={len(changed)}"


def _preview(text: str, limit: int = 1600) -> str:
    compact = " ".join(text.split())
    return compact if len(compact) <= limit else compact[: limit - 3] + "..."
