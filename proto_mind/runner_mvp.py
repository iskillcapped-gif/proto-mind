from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from proto_mind.action_policy import classify_command
from proto_mind.activation_layer import RunnerActivationPreconditions
from proto_mind.command_registry import COMMAND_REGISTRY
from proto_mind.memory_store import MemoryStore


RUNNER_MVP_COMMANDS = (
    "/runner-mvp status",
    "/runner-mvp design",
    "/runner-mvp allowlist",
    "/runner-mvp confirmation",
    "/runner-mvp evidence",
    "/runner-mvp stop-conditions",
    "/runner-mvp doctor",
    "/runner-mvp handoff",
)
MVP_ALLOWLIST_CANDIDATES = (
    ("/warnings unknown", "Expose unaccepted warnings before any future execution.", "warning inventory"),
    ("/daily doctor", "Validate daily operating-layer safety.", "doctor report"),
    ("/exports doctor", "Inspect export health without cleanup or retention mutation.", "doctor report"),
    ("/runner disabled", "Prove runner execution remains disabled before a future run.", "disabled-state report"),
    ("/capabilities safety", "Expose current Registry/Policy safety classification.", "safety classification"),
)
CONFIRMATION_TEMPLATE = "CONFIRM RUN READONLY: <exact command>"
_DEPENDENCY_COMMANDS = (
    "/activation status",
    "/activation preconditions",
    "/activation blockers",
    "/runner-candidates status",
    "/runner-candidates list",
    "/runner status",
    "/runner disabled",
    "/sandbox status",
    "/sandbox denied",
    "/confirm status",
    "/confirm policy",
    "/plan gates",
    "/capabilities safety",
)
_STOP_CONDITIONS = (
    "unknown warnings > 0",
    "blockers > 0",
    "Context Injection unexpectedly enabled",
    "command not present in the separately approved active allowlist",
    "command not Registry-known",
    "command not read-only or mutates is not none",
    "command high-risk, operator-only, unknown, or unlisted",
    "proto_mind/data or proto_mind/exports mutation risk",
    "confirmation phrase mismatch",
    "dry-run plan not shown",
    "evidence capture unavailable or incomplete",
    "shell/subprocess/eval/exec or arbitrary code requested",
    "network or hidden background work requested",
    "any unexpected exception or metadata drift",
)
_EVIDENCE_FIELDS = (
    "command_requested",
    "command_executed",
    "execution_enabled",
    "confirmation_matched",
    "gates_checked",
    "stdout_stderr_summary",
    "status_code",
    "files_changed_summary",
    "data_exports_sha256_summary",
    "context_injection_status",
    "warnings_unknown_count",
    "post_run_acceptance_recommendation",
    "refusal_reason",
)


def format_runner_mvp_command(command: str, *, project_root: Path, memory_store: MemoryStore) -> str | None:
    normalized = " ".join(command.strip().lower().split())
    if normalized != "/runner-mvp" and not normalized.startswith("/runner-mvp "):
        return None
    layer = RunnerMVPDesignLock(project_root=project_root, memory_store=memory_store)
    if normalized == "/runner-mvp status":
        return layer.format_status()
    if normalized == "/runner-mvp design":
        return layer.format_design()
    if normalized == "/runner-mvp allowlist":
        return layer.format_allowlist()
    if normalized == "/runner-mvp confirmation":
        return layer.format_confirmation()
    if normalized == "/runner-mvp evidence":
        return layer.format_evidence()
    if normalized == "/runner-mvp stop-conditions":
        return layer.format_stop_conditions()
    if normalized == "/runner-mvp doctor":
        return layer.format_doctor()
    if normalized == "/runner-mvp handoff":
        return layer.format_handoff()
    return "Usage:\n" + "\n".join(f"  {item}" for item in RUNNER_MVP_COMMANDS)


class RunnerMVPDesignLock:
    def __init__(self, *, project_root: Path, memory_store: MemoryStore) -> None:
        self.project_root = project_root
        self.memory_store = memory_store
        self.activation = RunnerActivationPreconditions(project_root=project_root, memory_store=memory_store)

    def read_state(self) -> dict[str, Any]:
        activation = self.activation.read_state()
        if activation["unknown"] or activation["blocker_count"]:
            readiness = "BLOCKED"
        elif activation["accepted"] or activation["system_status"] != "OK" or activation["context_state"] == "enabled":
            readiness = "WARN"
        else:
            readiness = "OK"
        design_lock_safe = (
            not activation["unknown"]
            and activation["blocker_count"] == 0
            and activation["context_state"] == "disabled"
            and activation["activation_design_may_be_considered"]
        )
        return {
            **activation,
            "mvp_design_lock_readiness": readiness,
            "mvp_design_lock_safe": design_lock_safe,
            "design_lock_status": "LOCKED_DESIGN_ONLY",
            "active_allowlist": False,
            "execution_enabled": False,
            "execution_engine": False,
        }

    @staticmethod
    def _allowlist_rows() -> list[dict[str, Any]]:
        registry = {spec.prefix: spec for spec in COMMAND_REGISTRY}
        rows: list[dict[str, Any]] = []
        for command, reason, output_type in MVP_ALLOWLIST_CANDIDATES:
            spec = registry.get(command)
            policy = classify_command(command) if spec else None
            verified = bool(
                spec
                and spec.read_only
                and spec.mutates == "none"
                and spec.risk == "low"
                and policy
                and policy.policy_class == "auto_allowed"
            )
            rows.append(
                {
                    "command": command,
                    "reason": reason,
                    "output_type": output_type,
                    "spec": spec,
                    "policy": policy,
                    "verified": verified,
                }
            )
        return rows

    def format_status(self) -> str:
        state = self.read_state()
        categories = Counter(spec.category for spec in COMMAND_REGISTRY)
        rows = self._allowlist_rows()
        return "\n".join(
            [
                "Read-only Runner MVP Design Lock Status",
                f"Status: {state['mvp_design_lock_readiness']}",
                f"project_root: {self.project_root}",
                f"command_registry: commands={len(COMMAND_REGISTRY)} categories={len(categories)}",
                f"context_injection: {state['context_state']}",
                f"activation_readiness: {state['activation_readiness']}",
                f"runner_candidate_readiness: {state['candidate_set_readiness']}",
                f"confirmation_gate_readiness: {state['confirmation_readiness']}",
                f"sandbox_blueprint_readiness: {state['sandbox_readiness']}",
                f"accepted_known_warnings: {len(state['accepted'])}",
                f"unknown_warnings: {len(state['unknown'])}",
                f"blockers: {state['blocker_count']}",
                f"design_lock_status: {state['design_lock_status']}",
                f"mvp_allowlist_candidates: {len(rows)}/5 verified={sum(row['verified'] for row in rows)}",
                "active_allowlist: none/inactive",
                "execution_enabled=false",
                f"mvp_design_lock_safe: {str(state['mvp_design_lock_safe']).lower()}",
                "",
                "Design-lock boundary:",
                "- The design is fixed for review only; no active allowlist, runner dispatch, approval, authorization, execution, or persistent state exists.",
            ]
        )

    def format_design(self) -> str:
        refusals = (
            "unknown warnings > 0 or blockers > 0",
            "Context Injection unexpectedly enabled",
            "candidate not in the separately approved active allowlist",
            "candidate not Registry-known/read-only/mutates=none/low-risk",
            "command writes proto_mind/data or proto_mind/exports",
            "command high-risk/operator-only/unknown/unlisted",
            "confirmation phrase mismatch",
            "dry-run or evidence capture unavailable",
        )
        lines = [
            "Locked Read-only Runner MVP Design",
            "design_lock_status: LOCKED_DESIGN_ONLY",
            "execution_enabled=false",
            "",
            "Scope and transport:",
            "- Read-only commands only.",
            "- Future transport: internal Proto-Mind command router/handler only; never shell transport.",
            "- No subprocess, shell, pipeline, eval, exec, arbitrary code, or free-form command execution.",
            "- No command outside a separately approved active allowlist.",
            "- No mutating, high-risk, operator-only, unknown, or unlisted command.",
            "",
            "Required future flow:",
            "1. Show a dry-run plan.",
            "2. Revalidate Registry and Policy metadata.",
            "3. Require exact command-specific human confirmation, never broad confirmation.",
            "4. Execute at most one active-allowlisted read-only command through the internal handler.",
            "5. Capture evidence and changed-path/SHA assertions.",
            "6. Require post-run operator Acceptance Review.",
            "",
            "Mandatory refusal conditions:",
        ]
        lines.extend(f"- {item}" for item in refusals)
        lines.extend(
            [
                "",
                "Implementation boundary:",
                "- This command locks architecture text only; no transport, allowlist, confirmation capture, evidence collector, or executor is implemented.",
            ]
        )
        return "\n".join(lines)

    def format_allowlist(self) -> str:
        lines = [
            "Locked Proposed MVP Allowlist Candidates",
            "design_lock_status: LOCKED_DESIGN_ONLY",
            "active_allowlist: none/inactive",
            "execution_enabled=false",
        ]
        for row in self._allowlist_rows():
            spec = row["spec"]
            policy = row["policy"]
            safety = (
                f"category={spec.category}, read_only={str(spec.read_only).lower()}, mutates={spec.mutates}, risk={spec.risk}, policy={policy.policy_class}"
                if spec and policy
                else "NEEDS_REVIEW"
            )
            lines.extend(
                [
                    "",
                    f"{row['command']}:",
                    "- marker: MVP_ALLOWLIST_CANDIDATE | NOT_ACTIVE | NOT_EXECUTABLE_YET",
                    f"- verification: {'REGISTRY_VERIFIED' if row['verified'] else 'NEEDS_REVIEW'}",
                    f"- reason: {row['reason']}",
                    f"- expected_output: {row['output_type']}",
                    f"- safety_class: {safety}",
                    "- required_gates: Rule 0, warnings/blockers=0, Context disabled, dry-run, exact confirmation, evidence, Acceptance Review.",
                ]
            )
        lines.extend(
            [
                "",
                "Allowlist boundary:",
                "- Proposed candidates are not active and cannot be executed by this layer.",
            ]
        )
        return "\n".join(lines)

    def format_confirmation(self) -> str:
        return "\n".join(
            [
                "Locked MVP Confirmation Rules",
                f"exact_phrase_template: {CONFIRMATION_TEMPLATE}",
                "- Confirmation must match the exact command byte-for-byte after the fixed prefix.",
                "- Future confirmation expires immediately after one attempted run.",
                "- Broad confirmations such as 'do all' or 'run everything' are invalid.",
                "- Confirmation cannot be reused, cached, inherited, or inferred from prior chat.",
                "- High-risk, operator-only, unknown, mutating, or non-allowlisted commands cannot be confirmed.",
                "- Hidden, implicit, default, or background confirmations are forbidden.",
                "",
                "Capture boundary:",
                "- No confirmation is parsed, captured, matched, stored, or consumed in this design-lock layer.",
            ]
        )

    def format_evidence(self) -> str:
        lines = [
            "Locked MVP Execution Evidence Model",
            "",
            "Current design-only evidence:",
        ]
        lines.extend(f"- {field}: NOT_AVAILABLE_DESIGN_ONLY" for field in _EVIDENCE_FIELDS)
        lines.extend(
            [
                "",
                "Future evidence rules:",
                "- Evidence must be tied to one request and exact command, disclose refusal/success status, and fail closed when any field is unavailable.",
                "- File-change and data/exports SHA-256 summaries must prove the read-only invariant.",
                "",
                "Evidence boundary:",
                "- No execution occurred, so evidence is explicitly unavailable rather than simulated as real.",
            ]
        )
        return "\n".join(lines)

    def format_stop_conditions(self) -> str:
        lines = [
            "Locked MVP Stop / Refusal Conditions",
            "",
            "A future runner must refuse or stop when:",
        ]
        lines.extend(f"- {item}" for item in _STOP_CONDITIONS)
        lines.extend(
            [
                "",
                "Stop policy:",
                "- Any uncertain, missing, mismatched, or exceptional state fails closed.",
                "- This layer evaluates no command and triggers no stop because execution does not exist.",
            ]
        )
        return "\n".join(lines)

    def format_doctor(self) -> str:
        report = self.doctor_report()
        lines = ["Read-only Runner MVP Design Lock Doctor", f"Status: {report['status']}", "", "Checks:"]
        lines.extend(f"- [{item['severity']}] {item['message']}" for item in report["findings"])
        lines.extend(
            [
                "",
                "Mutation policy:",
                "- Read-only design diagnostics only; no allowlist, runner, command, confirmation, evidence, file, approval, authorization, or execution state was created or changed.",
            ]
        )
        return "\n".join(lines)

    def doctor_report(self) -> dict[str, Any]:
        findings: list[dict[str, str]] = []
        registry = {spec.prefix: spec for spec in COMMAND_REGISTRY}
        missing = [command for command in RUNNER_MVP_COMMANDS if command not in registry]
        findings.append(
            {"severity": "ERROR", "message": f"Runner MVP commands missing from Registry: {', '.join(missing)}"}
            if missing
            else {"severity": "OK", "message": "All runner-mvp commands are registered."}
        )
        unsafe = [
            command
            for command in RUNNER_MVP_COMMANDS
            if command in registry and (not registry[command].read_only or registry[command].mutates != "none" or registry[command].risk != "low")
        ]
        findings.append(
            {"severity": "ERROR", "message": f"Runner MVP commands expose unsafe metadata: {', '.join(unsafe)}"}
            if unsafe
            else {"severity": "OK", "message": "Runner MVP commands are low-risk, read-only, and mutates=none."}
        )
        unavailable = [command for command in _DEPENDENCY_COMMANDS if command not in registry]
        findings.append(
            {"severity": "WARN", "message": f"Optional MVP design dependencies unavailable: {', '.join(unavailable)}"}
            if unavailable
            else {"severity": "OK", "message": "Activation, Runner Candidates, Runner Contract, Sandbox, Confirmation, Plan, and Capability helpers are reachable."}
        )
        invalid_candidates = [row["command"] for row in self._allowlist_rows() if not row["verified"]]
        findings.append(
            {"severity": "ERROR", "message": f"MVP allowlist candidates need review: {', '.join(invalid_candidates)}"}
            if invalid_candidates
            else {"severity": "OK", "message": f"All {len(MVP_ALLOWLIST_CANDIDATES)} MVP candidates are Registry-known read-only/mutates=none/low-risk/auto_allowed metadata."}
        )
        try:
            state = self.read_state()
        except Exception as exc:
            findings.append({"severity": "ERROR", "message": f"MVP design-lock readiness could not be computed: {exc}"})
        else:
            findings.append(
                {
                    "severity": "OK",
                    "message": f"Warning state is computable: accepted={len(state['accepted'])}, unknown={len(state['unknown'])}, blockers={state['blocker_count']}.",
                }
            )
            if state["unknown"] or state["blocker_count"]:
                findings.append({"severity": "BLOCKED", "message": "Unknown warnings or blockers prevent safe MVP design-lock progression."})
            if state["context_state"] == "enabled":
                findings.append({"severity": "WARN", "message": "Context Injection is explicitly enabled; Runner MVP Design Lock did not change it."})
            else:
                findings.append({"severity": "OK", "message": "Context Injection is disabled."})
        findings.append(
            {
                "severity": "OK",
                "message": "MVP allowlist remains proposed/inactive and all candidates remain NOT_ACTIVE/NOT_EXECUTABLE_YET.",
            }
        )
        findings.append(
            {
                "severity": "OK",
                "message": "Execution remains disabled and no active allowlist, runner dispatch, execution callback, subprocess/shell/eval/exec path, confirmation capture, authorization engine, execution engine, evidence implementation, persistence, or dangerous action is exposed.",
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
        rows = self._allowlist_rows()
        return "\n".join(
            [
                "Proto-Mind Read-only Runner MVP Design Lock Handoff",
                f"Project: {self.project_root}",
                f"Current baseline: {state['accepted_baseline'] or 'not detected'}",
                "Rule 0: before changes run scripts/run_cli.sh, then /memory backup.",
                f"Registry: {len(COMMAND_REGISTRY)} commands across {len(categories)} categories",
                f"MVP scope: {len(rows)} read-only candidates; verified={sum(row['verified'] for row in rows)}",
                f"Warnings: accepted={len(state['accepted'])}, unknown={len(state['unknown'])}, blockers={state['blocker_count']}",
                f"Context Injection: {state['context_state']}",
                "design_lock_status: LOCKED_DESIGN_ONLY",
                "active_allowlist: none/inactive",
                "execution_enabled=false",
                "",
                "Locked MVP allowlist candidates:",
                *[f"- MVP_ALLOWLIST_CANDIDATE | NOT_ACTIVE | NOT_EXECUTABLE_YET | {row['command']}" for row in rows],
                "",
                "Confirmation rule:",
                f"- {CONFIRMATION_TEMPLATE}; exact command match, one future run, no reuse/broad/implicit confirmation.",
                "",
                "Evidence model:",
                "- Exact command, enabled/executed state, confirmation, gates, output/status, changed files, SHA-256, context, warnings, acceptance, and refusal reason.",
                "- Current evidence values remain NOT_AVAILABLE_DESIGN_ONLY.",
                "",
                "Stop conditions:",
                *[f"- {item}" for item in _STOP_CONDITIONS],
                "",
                "Verification commands:",
                "- scripts/which_python.sh",
                "- scripts/run_tests.sh",
                "- /opt/homebrew/opt/python@3.11/bin/python3.11 -m compileall proto_mind",
                "",
                "Required final report fields:",
                "- backup path; files changed; MVP commands/design; Registry counts; tests/compileall; smoke; allowlist/confirmation/evidence/stops; Context Injection; data/exports SHA-256; limitations/warnings.",
                "",
                "Next milestone:",
                "- A future real v3.0 runner implementation requires a separate explicit checkpointed task; this handoff grants no activation or execution authority.",
                "",
                "Handoff safety:",
                "- Copyable text only; no clipboard, design state, allowlist, runner, command, subprocess, shell, eval/exec, confirmation, evidence, approval, authorization, file, snapshot, backup, or external call occurred.",
            ]
        )
