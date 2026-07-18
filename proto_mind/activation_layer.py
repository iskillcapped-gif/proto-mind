from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from proto_mind.command_registry import COMMAND_REGISTRY
from proto_mind.memory_store import MemoryStore
from proto_mind.runner_candidates import FUTURE_RUNNER_CANDIDATES, RunnerCandidateSet


ACTIVATION_COMMANDS = (
    "/activation status",
    "/activation preconditions",
    "/activation checklist",
    "/activation blockers",
    "/activation forbidden",
    "/activation doctor",
    "/activation handoff",
)
_DEPENDENCY_COMMANDS = (
    "/runner-candidates status",
    "/runner-candidates list",
    "/runner-candidates doctor",
    "/runner status",
    "/runner disabled",
    "/sandbox status",
    "/sandbox denied",
    "/confirm status",
    "/confirm policy",
    "/plan status",
    "/plan gates",
    "/capabilities status",
    "/capabilities safety",
    "/warnings unknown",
)
_PRECONDITIONS = (
    "Rule 0 backup/checkpoint is complete and visible.",
    "Unknown warnings equal 0.",
    "Blocker count equals 0.",
    "Context Injection is disabled unless the explicit task targets it.",
    "Candidate command is Registry-known.",
    "Candidate command is in a separately approved active allowlist.",
    "The active allowlist is implemented only in a separate explicit checkpointed task.",
    "Candidate is classified read-only, mutates=none, low-risk, and not operator-only/unknown.",
    "Candidate cannot write proto_mind/data or proto_mind/exports.",
    "A dry-run plan is shown before execution.",
    "Confirmation policy is shown before execution.",
    "Explicit task-specific human confirmation is captured by a future approved layer.",
    "Execution evidence is captured by a future approved layer.",
    "Post-run Acceptance Review is mandatory.",
    "Shell/subprocess/eval/exec remain forbidden unless a separate highly restricted design is approved.",
    "Network and hidden background work are forbidden.",
    "Stop conditions are explicit and fail closed.",
)
_CHECKLIST_COMMANDS = (
    "/runner-mvp doctor",
    "/runner-candidates doctor",
    "/runner disabled",
    "/sandbox denied",
    "/confirm policy",
    "/plan gates",
    "/capabilities safety",
    "/warnings unknown",
)


def format_activation_command(command: str, *, project_root: Path, memory_store: MemoryStore) -> str | None:
    normalized = " ".join(command.strip().lower().split())
    if normalized != "/activation" and not normalized.startswith("/activation "):
        return None
    layer = RunnerActivationPreconditions(project_root=project_root, memory_store=memory_store)
    if normalized == "/activation status":
        return layer.format_status()
    if normalized == "/activation preconditions":
        return layer.format_preconditions()
    if normalized == "/activation checklist":
        return layer.format_checklist()
    if normalized == "/activation blockers":
        return layer.format_blockers()
    if normalized == "/activation forbidden":
        return layer.format_forbidden()
    if normalized == "/activation doctor":
        return layer.format_doctor()
    if normalized == "/activation handoff":
        return layer.format_handoff()
    return "Usage:\n" + "\n".join(f"  {item}" for item in ACTIVATION_COMMANDS)


class RunnerActivationPreconditions:
    def __init__(self, *, project_root: Path, memory_store: MemoryStore) -> None:
        self.project_root = project_root
        self.memory_store = memory_store
        self.candidates = RunnerCandidateSet(project_root=project_root, memory_store=memory_store)

    def read_state(self) -> dict[str, Any]:
        candidates = self.candidates.read_state()
        if candidates["unknown"] or candidates["blocker_count"]:
            readiness = "BLOCKED"
        elif candidates["accepted"] or candidates["system_status"] != "OK" or candidates["context_state"] == "enabled":
            readiness = "WARN"
        else:
            readiness = "OK"
        design_considerable = (
            not candidates["unknown"]
            and candidates["blocker_count"] == 0
            and candidates["context_state"] == "disabled"
            and candidates["candidate_set_generation_safe"]
        )
        return {
            **candidates,
            "activation_readiness": readiness,
            "activation_design_may_be_considered": design_considerable,
            "active_allowlist": False,
            "execution_enabled": False,
            "approval_capture": False,
            "authorization_engine": False,
            "execution_engine": False,
            "actual_execution_blocked": True,
        }

    def format_status(self) -> str:
        state = self.read_state()
        categories = Counter(spec.category for spec in COMMAND_REGISTRY)
        return "\n".join(
            [
                "Runner Activation Preconditions Status",
                f"Status: {state['activation_readiness']}",
                f"project_root: {self.project_root}",
                f"command_registry: commands={len(COMMAND_REGISTRY)} categories={len(categories)}",
                f"context_injection: {state['context_state']}",
                f"runner_contract_readiness: {state['runner_readiness']}",
                f"runner_candidate_readiness: {state['candidate_set_readiness']}",
                f"sandbox_blueprint_readiness: {state['sandbox_readiness']}",
                f"confirmation_gate_readiness: {state['confirmation_readiness']}",
                f"capability_map_readiness: {state['capability_readiness']}",
                f"accepted_known_warnings: {len(state['accepted'])}",
                f"unknown_warnings: {len(state['unknown'])}",
                f"blockers: {state['blocker_count']}",
                "active_allowlist: none/inactive",
                "execution_enabled=false",
                f"activation_design_may_be_considered: {str(state['activation_design_may_be_considered']).lower()}",
                "actual_execution_blocked=true",
                "activation_performed=false",
                "",
                "Status boundary:",
                "- OK/WARN means design review may be considered; it never means candidates are active or executable.",
            ]
        )

    def format_preconditions(self) -> str:
        lines = [
            "Mandatory Preconditions for a Future v3.x Runner",
            "",
            "Preconditions:",
        ]
        lines.extend(f"{index}. {item}" for index, item in enumerate(_PRECONDITIONS, start=1))
        lines.extend(
            [
                "",
                "Current interpretation:",
                "- Preconditions are documentation only; none activates a candidate or enables execution in v2.15.",
            ]
        )
        return "\n".join(lines)

    def format_checklist(self) -> str:
        lines = [
            "Future Runner Implementation Checklist",
            "",
            "Read-only review commands:",
        ]
        lines.extend(f"- [ ] Run {command}" for command in _CHECKLIST_COMMANDS)
        lines.extend(
            [
                "- [ ] Confirm 0 unknown warnings and 0 blockers.",
                "- [ ] Define the exact candidate allowlist in a separate explicit task.",
                "- [ ] Define task-specific confirmation phrase rules without broad or implicit consent.",
                "- [ ] Define the execution evidence model and receipt integrity rules.",
                "- [ ] Define stop conditions and fail-closed behavior.",
                "- [ ] Define allowed writes and forbidden writes exactly.",
                "- [ ] Define verification commands and expected evidence.",
                "- [ ] Require tests, compileall, manual smoke, and data/exports SHA-256 checks.",
                "",
                "Checklist boundary:",
                "- Printable operator guidance only; no command was run and no checkbox state was stored.",
            ]
        )
        return "\n".join(lines)

    def format_blockers(self) -> str:
        state = self.read_state()
        design_blockers: list[str] = []
        if state["unknown"]:
            design_blockers.append(f"unknown warnings={len(state['unknown'])}")
        if state["blocker_count"]:
            design_blockers.append(f"blockers={state['blocker_count']}")
        if state["context_state"] == "enabled":
            design_blockers.append("Context Injection unexpectedly enabled")
        return "\n".join(
            [
                "Runner Activation Blockers",
                "",
                "Blocker conditions:",
                "- unknown warnings > 0 or blockers > 0",
                "- Context Injection unexpectedly enabled",
                "- candidate missing from Registry or not read-only/mutates=none/low-risk",
                "- candidate classified high-risk/operator-only/unknown",
                "- active allowlist absent when attempting execution",
                "- approval capture, authorization engine, execution engine, or evidence model absent when attempting execution",
                "- shell/subprocess/eval/exec exposure, data/export mutation risk, or missing Rule 0 backup",
                "",
                "Current design blockers:",
                f"- {', '.join(design_blockers) if design_blockers else 'none; v3.x design discussion may be considered'}",
                "",
                "Current execution blockers:",
                "- active allowlist: absent",
                "- approval capture: absent",
                "- authorization engine: absent",
                "- execution engine: absent",
                "- execution evidence implementation: absent",
                "- actual_execution_blocked=true",
                "",
                "Interpretation:",
                "- Design consideration is not activation. Actual execution remains blocked today.",
            ]
        )

    def format_forbidden(self) -> str:
        return "\n".join(
            [
                "Actions Forbidden Before a Separately Approved v3.x Runner",
                "- Executing any command or activating a FUTURE_CANDIDATE automatically.",
                "- Treating the candidate set as an active allowlist.",
                "- Mutating, high-risk, operator-only, unknown, unregistered, or unlisted commands.",
                "- Broad approvals, implicit confirmations, cached consent, or approval inference.",
                "- Hidden/background work, network calls, shell/subprocess/pipeline/eval/exec, or arbitrary code.",
                "- proto_mind/data or proto_mind/exports writes and Context Injection changes.",
                "- Backup or snapshot creation unless a dedicated task explicitly scopes it.",
                "- Repair, cleanup, migration, deletion, move/rename, compression, or destructive overwrite.",
                "",
                "Current state:",
                "- active_allowlist: none/inactive",
                "- execution_enabled=false",
                "- activation_performed=false",
            ]
        )

    def format_doctor(self) -> str:
        report = self.doctor_report()
        lines = ["Runner Activation Preconditions Doctor", f"Status: {report['status']}", "", "Checks:"]
        lines.extend(f"- [{item['severity']}] {item['message']}" for item in report["findings"])
        lines.extend(
            [
                "",
                "Mutation policy:",
                "- Read-only diagnostics only; no activation, allowlist, candidate, runner, command, file, approval, authorization, or execution state was created or changed.",
            ]
        )
        return "\n".join(lines)

    def doctor_report(self) -> dict[str, Any]:
        findings: list[dict[str, str]] = []
        registry = {spec.prefix: spec for spec in COMMAND_REGISTRY}
        missing = [command for command in ACTIVATION_COMMANDS if command not in registry]
        findings.append(
            {"severity": "ERROR", "message": f"Activation commands missing from Registry: {', '.join(missing)}"}
            if missing
            else {"severity": "OK", "message": "All activation commands are registered."}
        )
        unsafe = [
            command
            for command in ACTIVATION_COMMANDS
            if command in registry and (not registry[command].read_only or registry[command].mutates != "none" or registry[command].risk != "low")
        ]
        findings.append(
            {"severity": "ERROR", "message": f"Activation commands expose unsafe metadata: {', '.join(unsafe)}"}
            if unsafe
            else {"severity": "OK", "message": "Activation commands are low-risk, read-only, and mutates=none."}
        )
        unavailable = [command for command in _DEPENDENCY_COMMANDS if command not in registry]
        findings.append(
            {"severity": "WARN", "message": f"Optional activation dependencies unavailable: {', '.join(unavailable)}"}
            if unavailable
            else {"severity": "OK", "message": "Runner Candidates, Runner Contract, Sandbox, Confirmation, Plan, Capability Map, and Warning helpers are reachable."}
        )
        try:
            state = self.read_state()
        except Exception as exc:
            findings.append({"severity": "ERROR", "message": f"Activation readiness could not be computed: {exc}"})
        else:
            findings.append(
                {
                    "severity": "OK",
                    "message": f"Warning state is computable: accepted={len(state['accepted'])}, unknown={len(state['unknown'])}, blockers={state['blocker_count']}.",
                }
            )
            if state["unknown"] or state["blocker_count"]:
                findings.append({"severity": "BLOCKED", "message": "Unknown warnings or blockers prevent safe activation-design consideration."})
            if state["context_state"] == "enabled":
                findings.append({"severity": "WARN", "message": "Context Injection is explicitly enabled; Activation Preconditions did not change it."})
            else:
                findings.append({"severity": "OK", "message": "Context Injection is disabled."})
        findings.append(
            {
                "severity": "OK",
                "message": f"All {len(FUTURE_RUNNER_CANDIDATES)} candidates remain FUTURE_CANDIDATE/NOT_ACTIVE/NOT_EXECUTABLE_BY_RUNNER_YET.",
            }
        )
        findings.append(
            {
                "severity": "OK",
                "message": "Active allowlist remains absent, execution remains disabled, and actual execution remains blocked.",
            }
        )
        findings.append(
            {
                "severity": "OK",
                "message": "No activation API, execution callback, subprocess/shell/eval/exec path, approval capture, authorization engine, execution engine, persistence, or dangerous action is exposed.",
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
                "Proto-Mind Runner Activation Preconditions Handoff",
                f"Project: {self.project_root}",
                f"Current baseline: {state['accepted_baseline'] or 'not detected'}",
                "Rule 0: before changes run scripts/run_cli.sh, then /memory backup.",
                f"Registry: {len(COMMAND_REGISTRY)} commands across {len(categories)} categories",
                f"Candidate set: {len(FUTURE_RUNNER_CANDIDATES)}/13 registry-verified; all FUTURE_CANDIDATE/NOT_ACTIVE/NOT_EXECUTABLE_BY_RUNNER_YET",
                f"Warnings: accepted={len(state['accepted'])}, unknown={len(state['unknown'])}, blockers={state['blocker_count']}",
                f"Context Injection: {state['context_state']}",
                "active_allowlist: none/inactive",
                "execution_enabled=false",
                "actual_execution_blocked=true",
                "",
                "Activation preconditions summary:",
                *[f"- {item}" for item in _PRECONDITIONS],
                "",
                "Current blockers for actual execution:",
                "- Active allowlist, approval capture, authorization engine, execution engine, and execution evidence implementation are absent.",
                "",
                "Forbidden until separate approval:",
                "- Activation, execution, mutation, broad/implicit approval, unknown/high-risk/operator-only commands, shell/subprocess/eval/exec, network/background work, and unscoped data/export/context/backup/snapshot changes.",
                "",
                "Verification commands:",
                "- scripts/which_python.sh",
                "- scripts/run_tests.sh",
                "- /opt/homebrew/opt/python@3.11/bin/python3.11 -m compileall proto_mind",
                "",
                "Required final report fields:",
                "- backup path; files changed; commands/preconditions; Registry counts; tests/compileall; smoke; design/execution blockers; Context Injection; data/exports SHA-256; limitations/warnings.",
                "",
                "Next milestone:",
                "- Review /runner-mvp design, allowlist, confirmation, evidence, and stop-conditions. Any real v3.0 implementation requires a separate explicit checkpointed task.",
                "",
                "Handoff safety:",
                "- Copyable text only; no clipboard, activation state, allowlist, runner, command, subprocess, shell, eval/exec, approval, authorization, file, snapshot, backup, or external call occurred.",
            ]
        )
