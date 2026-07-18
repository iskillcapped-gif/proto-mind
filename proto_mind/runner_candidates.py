from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from proto_mind.action_policy import classify_command
from proto_mind.command_registry import COMMAND_REGISTRY
from proto_mind.memory_store import MemoryStore
from proto_mind.runner_layer import NoOpRunnerContract


RUNNER_CANDIDATE_COMMANDS = (
    "/runner-candidates status",
    "/runner-candidates list",
    "/runner-candidates explain",
    "/runner-candidates denied",
    "/runner-candidates gates",
    "/runner-candidates doctor",
    "/runner-candidates handoff",
)
FUTURE_RUNNER_CANDIDATES = (
    ("/daily doctor", "Validate Daily Layer safety invariants.", "doctor report", "May reflect accepted source WARN state."),
    ("/warnings unknown", "Expose unaccepted findings before any future run.", "warning inventory", "Exact local classification only."),
    ("/warnings accepted", "Keep accepted legacy debt visible.", "accepted-warning summary", "Acceptance is documentation, not suppression."),
    ("/exports doctor", "Inspect export health without retention mutation.", "doctor report", "Does not delete, move, or repair exports."),
    ("/capabilities safety", "Show Registry and Policy safety classes.", "safety classification", "Advisory metadata is not authorization."),
    ("/confirm policy", "Show future confirmation constraints.", "policy report", "Does not capture or enforce confirmation."),
    ("/plan gates", "Show mandatory pre-execution gates.", "gate checklist", "Does not satisfy or execute gates."),
    ("/runner disabled", "Explain why execution remains unavailable.", "disabled-state report", "Always reports execution_enabled=false."),
    ("/runner status", "Show no-op contract readiness.", "status report", "No request dispatch or active allowlist."),
    ("/sandbox denied", "Show denied command and operation classes.", "denial report", "Blueprint rules only; no enforcement engine."),
    ("/memory-card short", "Provide compact local project continuity.", "short summary", "Generated text is not persistent memory."),
    ("/session handoff-brief", "Provide copyable session context.", "handoff report", "No clipboard or file write."),
    ("/proto snapshot-diff-status", "Inspect existing snapshot-diff export status.", "status report", "Does not create snapshots or exports."),
)
_DEPENDENCY_COMMANDS = (
    "/runner status",
    "/runner contract",
    "/runner disabled",
    "/sandbox status",
    "/sandbox allowlist",
    "/confirm status",
    "/confirm policy",
    "/capabilities status",
    "/capabilities safety",
    "/warnings unknown",
)
_ACTIVATION_GATES = (
    "Rule 0 backup/checkpoint is complete and visible.",
    "/warnings unknown reports 0.",
    "Blocker count is 0.",
    "Context Injection is disabled.",
    "/capabilities safety has been reviewed.",
    "/confirm policy has been reviewed.",
    "/runner disabled has been reviewed.",
    "Every candidate exists in Registry and remains read-only/mutates=none/low-risk/auto_allowed.",
    "An active allowlist is implemented only in a separate explicit checkpointed task.",
    "No execution occurs before a separately approved v3.x explicit-confirm runner milestone.",
    "Manual smoke and data/exports SHA-256 checks are required.",
    "/activation preconditions and /activation blockers have been reviewed.",
)


def format_runner_candidates_command(command: str, *, project_root: Path, memory_store: MemoryStore) -> str | None:
    normalized = " ".join(command.strip().lower().split())
    if not normalized.startswith("/runner-candidates"):
        return None
    candidates = RunnerCandidateSet(project_root=project_root, memory_store=memory_store)
    if normalized == "/runner-candidates status":
        return candidates.format_status()
    if normalized == "/runner-candidates list":
        return candidates.format_list()
    if normalized == "/runner-candidates explain":
        return candidates.format_explain()
    if normalized == "/runner-candidates denied":
        return candidates.format_denied()
    if normalized == "/runner-candidates gates":
        return candidates.format_gates()
    if normalized == "/runner-candidates doctor":
        return candidates.format_doctor()
    if normalized == "/runner-candidates handoff":
        return candidates.format_handoff()
    return "Usage:\n" + "\n".join(f"  {item}" for item in RUNNER_CANDIDATE_COMMANDS)


class RunnerCandidateSet:
    def __init__(self, *, project_root: Path, memory_store: MemoryStore) -> None:
        self.project_root = project_root
        self.memory_store = memory_store
        self.runner = NoOpRunnerContract(project_root=project_root, memory_store=memory_store)

    def read_state(self) -> dict[str, Any]:
        runner = self.runner.read_state()
        if runner["unknown"] or runner["blocker_count"]:
            readiness = "BLOCKED"
        elif runner["accepted"] or runner["system_status"] != "OK" or runner["context_state"] == "enabled":
            readiness = "WARN"
        else:
            readiness = "OK"
        generation_safe = (
            not runner["unknown"]
            and runner["blocker_count"] == 0
            and runner["context_state"] == "disabled"
            and runner["noop_runner_contract_generation_safe"]
        )
        return {
            **runner,
            "candidate_set_readiness": readiness,
            "candidate_set_generation_safe": generation_safe,
            "active_allowlist": False,
            "execution_enabled": False,
        }

    @staticmethod
    def _candidate_specs() -> list[dict[str, Any]]:
        registry = {spec.prefix: spec for spec in COMMAND_REGISTRY}
        rows: list[dict[str, Any]] = []
        for command, purpose, output_type, limitation in FUTURE_RUNNER_CANDIDATES:
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
                    "purpose": purpose,
                    "output_type": output_type,
                    "limitation": limitation,
                    "spec": spec,
                    "policy": policy,
                    "verified": verified,
                }
            )
        return rows

    def format_status(self) -> str:
        state = self.read_state()
        categories = Counter(spec.category for spec in COMMAND_REGISTRY)
        rows = self._candidate_specs()
        return "\n".join(
            [
                "Runner Candidate Set Status",
                f"Status: {state['candidate_set_readiness']}",
                f"project_root: {self.project_root}",
                f"command_registry: commands={len(COMMAND_REGISTRY)} categories={len(categories)}",
                f"context_injection: {state['context_state']}",
                f"runner_contract_readiness: {state['runner_readiness']}",
                f"sandbox_blueprint_readiness: {state['sandbox_readiness']}",
                f"confirmation_gate_readiness: {state['confirmation_readiness']}",
                f"capability_map_readiness: {state['capability_readiness']}",
                f"accepted_known_warnings: {len(state['accepted'])}",
                f"unknown_warnings: {len(state['unknown'])}",
                f"blockers: {state['blocker_count']}",
                f"candidate_count: {len(rows)}",
                f"verified_candidates: {sum(row['verified'] for row in rows)}",
                "active_allowlist: none/inactive",
                "execution_enabled=false",
                f"candidate_set_generation_safe: {str(state['candidate_set_generation_safe']).lower()}",
                "",
                "State boundary:",
                "- Candidate metadata is static documentation; no allowlist, runner, command, approval, authorization, or candidate state was activated or stored.",
            ]
        )

    def format_list(self) -> str:
        lines = [
            "Future Read-Only Runner Candidate Set",
            "Status: DESIGN_ONLY",
            "active_allowlist: none/inactive",
            "execution_enabled=false",
            "",
            "Candidates:",
        ]
        for row in self._candidate_specs():
            verification = "REGISTRY_VERIFIED" if row["verified"] else "NEEDS_REVIEW"
            lines.append(
                f"- FUTURE_CANDIDATE | NOT_ACTIVE | NOT_EXECUTABLE_BY_RUNNER_YET | {verification} | {row['command']}"
            )
        lines.extend(
            [
                "",
                "Activation boundary:",
                "- This set is not an allowlist. Listing a command grants no execution or authorization capability.",
            ]
        )
        return "\n".join(lines)

    def format_explain(self) -> str:
        lines = [
            "Runner Candidate Explanations",
            "active_allowlist: none/inactive",
            "execution_enabled=false",
        ]
        for row in self._candidate_specs():
            spec = row["spec"]
            policy = row["policy"]
            safety = (
                f"category={spec.category}, read_only={str(spec.read_only).lower()}, mutates={spec.mutates}, risk={spec.risk}, policy={policy.policy_class}"
                if spec and policy
                else "NEEDS_REVIEW: Registry metadata unavailable"
            )
            lines.extend(
                [
                    "",
                    f"{row['command']}:",
                    f"- marker: FUTURE_CANDIDATE | NOT_ACTIVE | NOT_EXECUTABLE_BY_RUNNER_YET",
                    f"- verification: {'REGISTRY_VERIFIED' if row['verified'] else 'NEEDS_REVIEW'}",
                    f"- purpose: {row['purpose']}",
                    f"- safety: {safety}",
                    f"- expected_output: {row['output_type']}",
                    "- required_gates: all /runner-candidates gates plus separate active-allowlist and explicit-confirm runner milestones.",
                    "- future_value: bounded local safety/status/handoff evidence for operator review.",
                    f"- limitation: {row['limitation']}",
                ]
            )
        lines.extend(
            [
                "",
                "Explanation boundary:",
                "- Metadata inspection only; no candidate was invoked or activated.",
            ]
        )
        return "\n".join(lines)

    def format_denied(self) -> str:
        return "\n".join(
            [
                "Runner Candidate Set Exclusions",
                "- Every mutating command is excluded.",
                "- Every high-risk or operator-only command is excluded.",
                "- Every unknown/unregistered command is excluded and BLOCKED.",
                "- Every command not explicitly listed in the future candidate set is excluded.",
                "- Destructive operations, Context Injection changes, and unscoped data/export writes are excluded.",
                "- Backup/snapshot creation is excluded unless separately and explicitly scoped.",
                "- Shell, subprocess, pipeline, eval, exec, arbitrary code, network calls, and hidden background work are excluded.",
                "",
                "Current state:",
                "- active_allowlist: none/inactive",
                "- execution_enabled=false",
                "- exclusions are design constraints, not an execution filter because no runner exists.",
            ]
        )

    def format_gates(self) -> str:
        lines = [
            "Future Candidate Activation Gates",
            "",
            "Required before any activation:",
        ]
        lines.extend(f"{index}. {gate}" for index, gate in enumerate(_ACTIVATION_GATES, start=1))
        lines.extend(
            [
                "",
                "Gate policy:",
                "- A failed, missing, or unknown gate means STOP.",
                "- This layer cannot satisfy gates, activate an allowlist, capture confirmation, or execute candidates.",
            ]
        )
        return "\n".join(lines)

    def format_doctor(self) -> str:
        report = self.doctor_report()
        lines = ["Runner Candidate Set Doctor", f"Status: {report['status']}", "", "Checks:"]
        lines.extend(f"- [{item['severity']}] {item['message']}" for item in report["findings"])
        lines.extend(
            [
                "",
                "Mutation policy:",
                "- Read-only diagnostics only; no candidate, allowlist, runner, command, file, approval, authorization, or execution state was created or changed.",
            ]
        )
        return "\n".join(lines)

    def doctor_report(self) -> dict[str, Any]:
        findings: list[dict[str, str]] = []
        registry = {spec.prefix: spec for spec in COMMAND_REGISTRY}
        missing_commands = [command for command in RUNNER_CANDIDATE_COMMANDS if command not in registry]
        findings.append(
            {"severity": "ERROR", "message": f"Runner-candidate commands missing from Registry: {', '.join(missing_commands)}"}
            if missing_commands
            else {"severity": "OK", "message": "All runner-candidate commands are registered."}
        )
        unsafe_layer = [
            command
            for command in RUNNER_CANDIDATE_COMMANDS
            if command in registry and (not registry[command].read_only or registry[command].mutates != "none" or registry[command].risk != "low")
        ]
        findings.append(
            {"severity": "ERROR", "message": f"Runner-candidate commands expose unsafe metadata: {', '.join(unsafe_layer)}"}
            if unsafe_layer
            else {"severity": "OK", "message": "Runner-candidate commands are low-risk, read-only, and mutates=none."}
        )
        unavailable = [command for command in _DEPENDENCY_COMMANDS if command not in registry]
        findings.append(
            {"severity": "WARN", "message": f"Optional candidate-set dependencies unavailable: {', '.join(unavailable)}"}
            if unavailable
            else {"severity": "OK", "message": "Runner Contract, Sandbox, Confirmation, Capability Map, and Warning helpers are reachable."}
        )
        invalid_candidates = [row["command"] for row in self._candidate_specs() if not row["verified"]]
        findings.append(
            {"severity": "ERROR", "message": f"Candidates need Registry/Policy review: {', '.join(invalid_candidates)}"}
            if invalid_candidates
            else {"severity": "OK", "message": f"All {len(FUTURE_RUNNER_CANDIDATES)} candidates are Registry-known read-only/mutates=none/low-risk/auto_allowed metadata."}
        )
        try:
            state = self.read_state()
        except Exception as exc:
            findings.append({"severity": "ERROR", "message": f"Candidate-set readiness could not be computed: {exc}"})
        else:
            findings.append(
                {
                    "severity": "OK",
                    "message": f"Warning state is computable: accepted={len(state['accepted'])}, unknown={len(state['unknown'])}, blockers={state['blocker_count']}.",
                }
            )
            if state["unknown"] or state["blocker_count"]:
                findings.append({"severity": "BLOCKED", "message": "Unknown warnings or blockers prevent safe candidate-set progression."})
            if state["context_state"] == "enabled":
                findings.append({"severity": "WARN", "message": "Context Injection is explicitly enabled; Runner Candidate Set did not change it."})
            else:
                findings.append({"severity": "OK", "message": "Context Injection is disabled."})
        findings.append(
            {
                "severity": "OK",
                "message": "No active allowlist, execution callback, subprocess/shell/eval/exec path, approval capture, authorization engine, execution engine, persistence, or dangerous action is exposed.",
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
        rows = self._candidate_specs()
        return "\n".join(
            [
                "Proto-Mind Runner Candidate Set Handoff",
                f"Project: {self.project_root}",
                f"Current baseline: {state['accepted_baseline'] or 'not detected'}",
                "Rule 0: before changes run scripts/run_cli.sh, then /memory backup.",
                f"Registry: {len(COMMAND_REGISTRY)} commands across {len(categories)} categories",
                f"Candidate set: total={len(rows)}, registry_verified={sum(row['verified'] for row in rows)}",
                f"Warnings: accepted={len(state['accepted'])}, unknown={len(state['unknown'])}, blockers={state['blocker_count']}",
                f"Context Injection: {state['context_state']}",
                "active_allowlist: none/inactive",
                "execution_enabled=false",
                "",
                "Candidate summary:",
                *[f"- FUTURE_CANDIDATE | NOT_ACTIVE | NOT_EXECUTABLE_BY_RUNNER_YET | {row['command']}" for row in rows],
                "",
                "Denied classes:",
                "- Mutating, high-risk, operator-only, unknown, destructive, shell/subprocess/eval/exec, network, background, context-changing, data/export-writing, and non-listed commands.",
                "",
                "Required gates before activation:",
                *[f"- {gate}" for gate in _ACTIVATION_GATES],
                "",
                "Verification commands:",
                "- scripts/which_python.sh",
                "- scripts/run_tests.sh",
                "- /opt/homebrew/opt/python@3.11/bin/python3.11 -m compileall proto_mind",
                "",
                "Required final report fields:",
                "- backup path; files changed; commands/candidates; Registry counts; tests/compileall; smoke; candidate/runner safety; Context Injection; data/exports SHA-256; limitations/warnings.",
                "",
                "Next milestone:",
                "- Review /activation preconditions and /runner-mvp design; any real v3.0 implementation remains a separate explicit task.",
                "",
                "Handoff safety:",
                "- Copyable text only; no clipboard, candidate state, allowlist, runner, command, subprocess, shell, eval/exec, approval, authorization, file, snapshot, backup, or external call occurred.",
            ]
        )
