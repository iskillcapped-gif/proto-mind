from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from proto_mind.action_policy import classify_command
from proto_mind.command_registry import COMMAND_REGISTRY
from proto_mind.memory_store import MemoryStore
from proto_mind.sandbox_layer import FUTURE_ALLOWLIST_CANDIDATES, ExecutionSandboxBlueprint


RUNNER_COMMANDS = (
    "/runner status",
    "/runner contract",
    "/runner noop",
    "/runner evidence",
    "/runner disabled",
    "/runner doctor",
    "/runner handoff",
)
REQUEST_FIELDS = (
    "request_id",
    "operator_intent",
    "command_candidate",
    "command_family",
    "safety_class",
    "confirmation_level",
    "required_gates",
    "allowed_writes",
    "forbidden_writes",
    "expected_evidence",
    "stop_conditions",
)
RESPONSE_FIELDS = (
    "request_id",
    "status",
    "execution_enabled",
    "executed",
    "reason",
    "simulated_plan",
    "required_confirmation",
    "evidence_required",
    "next_manual_step",
)
_DEPENDENCY_COMMANDS = (
    "/sandbox status",
    "/sandbox blueprint",
    "/sandbox boundaries",
    "/sandbox allowlist",
    "/confirm status",
    "/confirm policy",
    "/capabilities status",
    "/capabilities safety",
    "/plan status",
    "/plan dry-run",
    "/warnings unknown",
)
_REQUIRED_GATES = (
    "Rule 0 backup/checkpoint is complete and visible.",
    "Unknown warnings are 0 and blockers are 0.",
    "Registry, Action Policy, Sandbox Blueprint, Plan, and Confirmation metadata are current.",
    "A separately approved active allowlist exists; FUTURE_CANDIDATE labels are insufficient.",
    "A separately approved task-specific confirmation capture design exists.",
    "Allowed/forbidden paths and writes are exact, bounded, and fail closed.",
    "Execution receipts, SHA-256, tests, smoke, stop conditions, and rollback evidence are designed.",
    "The operator performs post-run Acceptance Review.",
)


def format_runner_command(command: str, *, project_root: Path, memory_store: MemoryStore) -> str | None:
    normalized = " ".join(command.strip().lower().split())
    if normalized != "/runner" and not normalized.startswith("/runner "):
        return None
    runner = NoOpRunnerContract(project_root=project_root, memory_store=memory_store)
    if normalized == "/runner status":
        return runner.format_status()
    if normalized == "/runner contract":
        return runner.format_contract()
    if normalized == "/runner noop":
        return runner.format_noop()
    if normalized == "/runner evidence":
        return runner.format_evidence()
    if normalized == "/runner disabled":
        return runner.format_disabled()
    if normalized == "/runner doctor":
        return runner.format_doctor()
    if normalized == "/runner handoff":
        return runner.format_handoff()
    return "Usage:\n" + "\n".join(f"  {item}" for item in RUNNER_COMMANDS)


class NoOpRunnerContract:
    def __init__(self, *, project_root: Path, memory_store: MemoryStore) -> None:
        self.project_root = project_root
        self.memory_store = memory_store
        self.sandbox = ExecutionSandboxBlueprint(project_root=project_root, memory_store=memory_store)

    def read_state(self) -> dict[str, Any]:
        sandbox = self.sandbox.read_state()
        if sandbox["unknown"] or sandbox["blocker_count"]:
            readiness = "BLOCKED"
        elif sandbox["accepted"] or sandbox["system_status"] != "OK" or sandbox["context_state"] == "enabled":
            readiness = "WARN"
        else:
            readiness = "OK"
        contract_safe = (
            not sandbox["unknown"]
            and sandbox["blocker_count"] == 0
            and sandbox["context_state"] == "disabled"
            and sandbox["sandbox_blueprint_generation_safe"]
        )
        return {
            **sandbox,
            "runner_readiness": readiness,
            "noop_runner_contract_generation_safe": contract_safe,
            "execution_enabled": False,
            "active_allowlist": False,
        }

    @staticmethod
    def capability_counts() -> dict[str, int]:
        specs = list(COMMAND_REGISTRY)
        policy = Counter(classify_command(spec.prefix, specs).policy_class for spec in specs)
        return {
            "read_only": sum(spec.read_only and spec.mutates == "none" for spec in specs),
            "mutating": sum(not spec.read_only or spec.mutates != "none" for spec in specs),
            "high_risk": sum(spec.risk == "high" for spec in specs),
            "confirmation_required": policy["confirmation_required"],
            "operator_only": policy["operator_only"],
        }

    def format_status(self) -> str:
        state = self.read_state()
        categories = Counter(spec.category for spec in COMMAND_REGISTRY)
        return "\n".join(
            [
                "No-Op Runner Contract Status",
                f"Status: {state['runner_readiness']}",
                f"project_root: {self.project_root}",
                f"command_registry: commands={len(COMMAND_REGISTRY)} categories={len(categories)}",
                f"context_injection: {state['context_state']}",
                f"sandbox_blueprint_readiness: {state['sandbox_readiness']}",
                f"confirmation_gate_readiness: {state['confirmation_readiness']}",
                f"capability_map_readiness: {state['capability_readiness']}",
                f"accepted_known_warnings: {len(state['accepted'])}",
                f"unknown_warnings: {len(state['unknown'])}",
                f"blockers: {state['blocker_count']}",
                f"noop_runner_contract_generation_safe: {str(state['noop_runner_contract_generation_safe']).lower()}",
                "execution_enabled=false",
                "active_allowlist=false",
                "",
                "Contract boundary:",
                "- Specification only; no command, subprocess, shell, eval/exec, approval, authorization, runner state, or execution path exists.",
            ]
        )

    def format_contract(self) -> str:
        lines = [
            "Future Runner Interface Contract (No-Op v1)",
            "",
            "Request fields:",
        ]
        lines.extend(f"- {field}" for field in REQUEST_FIELDS)
        lines.extend(["", "Response fields:"])
        lines.extend(f"- {field}" for field in RESPONSE_FIELDS)
        lines.extend(
            [
                "",
                "Current response invariants:",
                "- execution_enabled=false",
                "- executed=false",
                "- status=DRY_RUN_ONLY or EXECUTION_DISABLED",
                "- reason must explain which gate or implementation capability is absent.",
                "- simulated_plan may describe manual steps but must never dispatch them.",
                "",
                "Contract scope:",
                "- No-op interface specification only; no request is parsed into execution and no response authorizes a command.",
            ]
        )
        return "\n".join(lines)

    def format_noop(self) -> str:
        return "\n".join(
            [
                "Sample No-Op Runner Response",
                "request_id: noop_example_001",
                "operator_intent: Inspect unknown warning state safely.",
                "command_candidate: /warnings unknown",
                "command_family: warnings",
                "safety_class: auto_allowed_read_only_metadata",
                "confirmation_level: READ_ONLY_MANUAL",
                "status: DRY_RUN_ONLY",
                "execution_enabled=false",
                "executed=false",
                "reason: Runner implementation and active allowlist are absent; this layer is contract-only.",
                "simulated_plan: Resolve Registry metadata, review gates, then let the operator decide whether to run the exact command manually.",
                "required_confirmation: operator manually initiates the command outside this no-op contract.",
                "evidence_required: NOT_AVAILABLE_NOOP",
                "files_written: none",
                "state_mutation: none",
                "execution_primitives: no subprocess/shell/eval/exec",
                "next_manual_step: Operator may run /warnings unknown manually.",
                "",
                "No-op guarantee:",
                "- The sample command was not executed and no runner state was stored.",
            ]
        )

    def format_evidence(self) -> str:
        fields = (
            "command_requested",
            "safety_classification",
            "gates_checked",
            "confirmation_captured_if_supported",
            "stdout_stderr_summary_if_executed",
            "files_changed_summary",
            "data_exports_sha256_summary",
            "tests_compile_smoke_summary",
            "post_run_acceptance_status",
            "rollback_stop_condition_status",
        )
        lines = [
            "Future Runner Evidence Model",
            "",
            "Current no-op evidence:",
        ]
        lines.extend(f"- {field}: NOT_AVAILABLE_NOOP" for field in fields)
        lines.extend(
            [
                "",
                "Future evidence requirements:",
                "- Evidence must be attributable to one request_id, preserve exact command/metadata, disclose every changed path, and fail closed when incomplete.",
                "- SHA-256, tests, compile, smoke, errors, stop conditions, rollback notes, and operator acceptance must remain inspectable.",
                "",
                "Evidence boundary:",
                "- No command ran, so execution evidence was neither fabricated nor persisted.",
            ]
        )
        return "\n".join(lines)

    def format_disabled(self) -> str:
        return "\n".join(
            [
                "Why Runner Execution Is Disabled",
                "execution_enabled=false",
                "executed=false",
                "- No active allowlist exists; Sandbox entries are FUTURE_CANDIDATE documentation only.",
                "- No approval capture exists.",
                "- No authorization engine exists.",
                "- No execution engine exists.",
                "- Subprocess, shell, pipeline, eval, and exec are not allowed in this layer.",
                "- A future runner requires a separate explicit checkpointed milestone and operator acceptance.",
                "- The operator must run any desired command manually through existing supported interfaces.",
                "",
                "Disabled-state guarantee:",
                "- This report cannot enable execution, activate candidates, capture consent, or dispatch a command.",
            ]
        )

    def format_doctor(self) -> str:
        report = self.doctor_report()
        lines = ["No-Op Runner Contract Doctor", f"Status: {report['status']}", "", "Checks:"]
        lines.extend(f"- [{item['severity']}] {item['message']}" for item in report["findings"])
        lines.extend(
            [
                "",
                "Mutation policy:",
                "- Read-only contract diagnostics only; execution_enabled=false, executed=false, and no command, file, state, approval, authorization, or external action occurred.",
            ]
        )
        return "\n".join(lines)

    def doctor_report(self) -> dict[str, Any]:
        findings: list[dict[str, str]] = []
        registry = {spec.prefix: spec for spec in COMMAND_REGISTRY}
        missing = [command for command in RUNNER_COMMANDS if command not in registry]
        findings.append(
            {"severity": "ERROR", "message": f"Runner commands missing from Registry: {', '.join(missing)}"}
            if missing
            else {"severity": "OK", "message": "All runner commands are registered."}
        )
        unsafe = [
            command
            for command in RUNNER_COMMANDS
            if command in registry and (not registry[command].read_only or registry[command].mutates != "none" or registry[command].risk != "low")
        ]
        findings.append(
            {"severity": "ERROR", "message": f"Runner commands expose unsafe metadata: {', '.join(unsafe)}"}
            if unsafe
            else {"severity": "OK", "message": "Runner commands are low-risk, read-only, and mutates=none."}
        )
        unavailable = [command for command in _DEPENDENCY_COMMANDS if command not in registry]
        findings.append(
            {"severity": "WARN", "message": f"Optional runner-contract dependencies unavailable: {', '.join(unavailable)}"}
            if unavailable
            else {"severity": "OK", "message": "Sandbox, Confirmation, Capability Map, Plan, and Warning helpers are reachable."}
        )
        findings.append(
            {"severity": "OK", "message": f"No active allowlist exists; {len(FUTURE_ALLOWLIST_CANDIDATES)} sandbox entries remain FUTURE_CANDIDATE only."}
        )
        try:
            state = self.read_state()
        except Exception as exc:
            findings.append({"severity": "ERROR", "message": f"Runner readiness could not be computed: {exc}"})
        else:
            findings.append(
                {
                    "severity": "OK",
                    "message": f"Warning state is computable: accepted={len(state['accepted'])}, unknown={len(state['unknown'])}, blockers={state['blocker_count']}.",
                }
            )
            if state["unknown"] or state["blocker_count"]:
                findings.append({"severity": "BLOCKED", "message": "Unknown warnings or blockers prevent safe runner-contract progression."})
            if state["context_state"] == "enabled":
                findings.append({"severity": "WARN", "message": "Context Injection is explicitly enabled; No-Op Runner Contract did not change it."})
            else:
                findings.append({"severity": "OK", "message": "Context Injection is disabled."})
        findings.append(
            {
                "severity": "OK",
                "message": "No execution callback, active allowlist, subprocess/shell/eval/exec path, approval capture, authorization engine, execution engine, persistence, or dangerous action is exposed.",
            }
        )
        findings.append(
            {
                "severity": "OK",
                "message": "No-op invariants are fixed: execution_enabled=false and executed=false.",
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
        counts = self.capability_counts()
        return "\n".join(
            [
                "Proto-Mind No-Op Runner Contract Handoff",
                f"Project: {self.project_root}",
                f"Current baseline: {state['accepted_baseline'] or 'not detected'}",
                "Rule 0: before changes run scripts/run_cli.sh, then /memory backup.",
                f"Registry: {len(COMMAND_REGISTRY)} commands across {len(categories)} categories",
                f"Capability safety: read_only={counts['read_only']}, mutating={counts['mutating']}, high_risk={counts['high_risk']}, confirmation_required={counts['confirmation_required']}, operator_only={counts['operator_only']}",
                f"Warnings: accepted={len(state['accepted'])}, unknown={len(state['unknown'])}, blockers={state['blocker_count']}",
                f"Context Injection: {state['context_state']}",
                "",
                "Runner contract summary:",
                "- Structured request/response fields describe intent, metadata, gates, scope, evidence, stop conditions, reason, and next manual step.",
                "- Current status is DRY_RUN_ONLY or EXECUTION_DISABLED.",
                "- execution_enabled=false; executed=false.",
                "",
                "Absent capabilities:",
                "- Active allowlist: absent. Approval capture: absent. Authorization engine: absent. Execution engine: absent.",
                "- Sandbox allowlist entries remain FUTURE_CANDIDATE only.",
                "",
                "Required gates before any future real runner:",
                *[f"- {gate}" for gate in _REQUIRED_GATES],
                "",
                "Verification commands:",
                "- scripts/which_python.sh",
                "- scripts/run_tests.sh",
                "- /opt/homebrew/opt/python@3.11/bin/python3.11 -m compileall proto_mind",
                "",
                "Required final report fields:",
                "- backup path; files changed; commands/contract; Registry counts; tests/compileall; smoke; no-op and sandbox safety; Context Injection; data/exports SHA-256; limitations/warnings.",
                "",
                "Next milestone:",
                "- Review /activation preconditions and /runner-mvp design; no real runner implementation is approved by this handoff.",
                "",
                "Handoff safety:",
                "- Copyable text only; no clipboard, runner, command, subprocess, shell, eval/exec, confirmation, approval, authorization, file, snapshot, backup, or external call occurred.",
            ]
        )
