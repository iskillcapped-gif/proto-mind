from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from proto_mind.action_policy import classify_command
from proto_mind.command_registry import COMMAND_REGISTRY
from proto_mind.confirmation_layer import AUTHORIZATION_LEVELS, ConfirmationVocabulary
from proto_mind.memory_store import MemoryStore


SANDBOX_COMMANDS = (
    "/sandbox status",
    "/sandbox blueprint",
    "/sandbox boundaries",
    "/sandbox allowlist",
    "/sandbox denied",
    "/sandbox doctor",
    "/sandbox handoff",
)
FUTURE_ALLOWLIST_CANDIDATES = (
    "/daily doctor",
    "/warnings unknown",
    "/capabilities safety",
    "/plan gates",
    "/confirm policy",
    "/exports doctor",
    "/proto snapshot-diff-status",
    "/memory-card short",
    "/session handoff-brief",
)
_DEPENDENCY_COMMANDS = (
    "/capabilities status",
    "/capabilities safety",
    "/plan status",
    "/plan dry-run",
    "/confirm status",
    "/confirm policy",
    "/warnings unknown",
    "/baseline current",
    "/prechange status",
    "/focus plan",
    "/acceptance criteria",
)
_REQUIRED_GATES = (
    "Rule 0 backup/checkpoint is complete and visible.",
    "/warnings unknown reports 0 and blocker count is 0.",
    "/capabilities safety, /plan dry-run, and /confirm policy have been reviewed.",
    "Exact commands and Registry/Policy metadata are recorded before execution.",
    "Allowed paths/writes and forbidden paths/writes are declared explicitly.",
    "Task-specific human confirmation is captured by a separately approved design.",
    "Execution is scoped, synchronous, cancellable where possible, and run once.",
    "Evidence and receipts are captured without hiding target effects.",
    "Post-run acceptance review is completed by the operator.",
)


def format_sandbox_command(command: str, *, project_root: Path, memory_store: MemoryStore) -> str | None:
    normalized = " ".join(command.strip().lower().split())
    if not normalized.startswith("/sandbox"):
        return None
    sandbox = ExecutionSandboxBlueprint(project_root=project_root, memory_store=memory_store)
    if normalized == "/sandbox status":
        return sandbox.format_status()
    if normalized == "/sandbox blueprint":
        return sandbox.format_blueprint()
    if normalized == "/sandbox boundaries":
        return sandbox.format_boundaries()
    if normalized == "/sandbox allowlist":
        return sandbox.format_allowlist()
    if normalized == "/sandbox denied":
        return sandbox.format_denied()
    if normalized == "/sandbox doctor":
        return sandbox.format_doctor()
    if normalized == "/sandbox handoff":
        return sandbox.format_handoff()
    return "Usage:\n" + "\n".join(f"  {item}" for item in SANDBOX_COMMANDS)


class ExecutionSandboxBlueprint:
    def __init__(self, *, project_root: Path, memory_store: MemoryStore) -> None:
        self.project_root = project_root
        self.memory_store = memory_store
        self.confirmation = ConfirmationVocabulary(project_root=project_root, memory_store=memory_store)

    def read_state(self) -> dict[str, Any]:
        confirmation = self.confirmation.read_state()
        if confirmation["unknown"] or confirmation["blocker_count"]:
            readiness = "BLOCKED"
        elif confirmation["accepted"] or confirmation["system_status"] != "OK" or confirmation["context_state"] == "enabled":
            readiness = "WARN"
        else:
            readiness = "OK"
        generation_safe = (
            not confirmation["unknown"]
            and confirmation["blocker_count"] == 0
            and confirmation["context_state"] == "disabled"
            and confirmation["confirmation_policy_generation_safe"]
        )
        return {
            **confirmation,
            "sandbox_readiness": readiness,
            "sandbox_blueprint_generation_safe": generation_safe,
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
                "Execution Sandbox Blueprint Status",
                f"Status: {state['sandbox_readiness']}",
                f"project_root: {self.project_root}",
                f"command_registry: commands={len(COMMAND_REGISTRY)} categories={len(categories)}",
                f"context_injection: {state['context_state']}",
                f"capability_map_readiness: {state['capability_readiness']}",
                f"plan_layer_readiness: {state['plan_readiness']}",
                f"confirmation_gate_readiness: {state['confirmation_readiness']}",
                f"accepted_known_warnings: {len(state['accepted'])}",
                f"unknown_warnings: {len(state['unknown'])}",
                f"blockers: {state['blocker_count']}",
                f"sandbox_blueprint_generation_safe: {str(state['sandbox_blueprint_generation_safe']).lower()}",
                "",
                "Runtime boundary:",
                "- Architecture text only; no runner, command, subprocess, shell, eval/exec, confirmation, approval, authorization, or sandbox state exists here.",
            ]
        )

    def format_blueprint(self) -> str:
        phases = (
            "Intent parsing: accept only a bounded structured request, never arbitrary executable text.",
            "Capability lookup: resolve every command through Command Registry; unknown means BLOCKED.",
            "Risk classification: apply Action Policy and strictest-bundle classification.",
            "Dry-run plan: show exact commands, scope, writes, risks, evidence, and stop conditions.",
            "Gates check: Rule 0, warnings, blockers, boundaries, verification, and policy must pass.",
            "Explicit confirmation: require task-specific confirmation through a separately approved capture design.",
            "Scoped execution: future runner may invoke only allowlisted internal handlers inside declared scope.",
            "Evidence capture: produce immutable-style receipts and compact output evidence.",
            "Post-run acceptance review: operator inspects results and chooses accept/notes/reject/hold.",
        )
        lines = [
            "Future Command Runner Blueprint (Design Only)",
            "",
            "Purpose:",
            "- Define a narrow, inspectable path for possible future execution of explicitly scoped Proto-Mind commands.",
            "",
            "Non-goals:",
            "- No general shell, autonomous planning, background work, free-text execution, hidden writes, or broad authorization.",
            "",
            "Execution phases:",
        ]
        lines.extend(f"{index}. {phase}" for index, phase in enumerate(phases, start=1))
        lines.extend(
            [
                "",
                "Required invariants:",
                "- No direct shell by default; no unknown command execution.",
                "- No high-risk auto-execution; operator-only commands never auto-execute.",
                "- Mutating commands require explicit task-specific confirmation.",
                "- proto_mind/data and proto_mind/exports writes require declared dedicated task scope.",
                "- Context Injection changes require a dedicated explicit task.",
                "- Fail closed on missing metadata, policy drift, boundary uncertainty, or evidence failure.",
                "",
                "Implementation boundary:",
                "- This is architecture output only. No execution-capable runner code is created or invoked.",
            ]
        )
        return "\n".join(lines)

    def format_boundaries(self) -> str:
        return "\n".join(
            [
                "Future Execution Sandbox Boundaries (Advisory)",
                f"- allowed project root: {self.project_root}",
                "- future read-only families: status, doctor, list, summary, map, policy, handoff, and inspection commands only after exact allowlisting.",
                "",
                "Forbidden paths by default:",
                f"- {self.project_root / 'proto_mind' / 'data'}/*",
                f"- {self.project_root / 'proto_mind' / 'exports'}/*",
                f"- {self.project_root / 'backups'}/*",
                "- every system or user path outside the project root",
                "",
                "Forbidden operation classes:",
                "- deletion, move/rename, destructive overwrite, repair, cleanup, migration, or compression",
                "- network calls unless a dedicated task scopes and approves them",
                "- shell pipelines, subprocesses, eval/exec, or arbitrary code unless separately designed and explicitly allowed",
                "- hidden, detached, scheduled, or background work",
                "",
                "Evidence required after any future run:",
                "- exact command and metadata snapshot; declared scope; start/end time; outputs/errors; changed-path manifest and SHA-256; test/smoke results; operator acceptance decision.",
                "",
                "Boundary status:",
                "- Advisory design only. No path access or operation was attempted.",
            ]
        )

    def format_allowlist(self) -> str:
        registry = {spec.prefix: spec for spec in COMMAND_REGISTRY}
        lines = [
            "Proposed Initial Future Runner Allowlist",
            "Status: DESIGN_ONLY",
            "",
            "Candidates:",
        ]
        for command in FUTURE_ALLOWLIST_CANDIDATES:
            spec = registry.get(command)
            metadata = "registered read_only=true mutates=none risk=low" if spec else "UNAVAILABLE/BLOCKED"
            lines.append(f"- FUTURE_CANDIDATE: {command} [{metadata}]")
        lines.extend(
            [
                "",
                "Activation boundary:",
                "- FUTURE_CANDIDATE is documentation, not an active allowlist. Nothing here is executable through the sandbox layer.",
            ]
        )
        return "\n".join(lines)

    def format_denied(self) -> str:
        return "\n".join(
            [
                "Denied / Blocked Future Runner Classes",
                "- Unknown or unregistered commands: BLOCKED.",
                "- High-risk commands: no auto-execution; blocked until a separate elevated policy exists.",
                "- Operator-only commands: never auto-execute.",
                "- Mutating commands without exact task-specific confirmation: BLOCKED.",
                "- Destructive operations, arbitrary code, command chains, and hidden side effects: BLOCKED.",
                "- proto_mind/data or proto_mind/exports mutation without declared dedicated scope: BLOCKED.",
                "- Context Injection changes without a dedicated explicit task: BLOCKED.",
                "- Backup or snapshot creation without an explicit request: BLOCKED.",
                "- Shell, subprocess, pipeline, eval, or exec execution in this layer: BLOCKED.",
                "",
                "Enforcement boundary:",
                "- These are blueprint rules only; no runner or authorization engine exists in this layer.",
            ]
        )

    def format_doctor(self) -> str:
        report = self.doctor_report()
        lines = ["Execution Sandbox Blueprint Doctor", f"Status: {report['status']}", "", "Checks:"]
        lines.extend(f"- [{item['severity']}] {item['message']}" for item in report["findings"])
        lines.extend(
            [
                "",
                "Mutation policy:",
                "- Read-only diagnostics only; no runner, command, subprocess, shell, eval/exec, approval, authorization, file, snapshot, backup, repair, cleanup, migration, or external action occurred.",
            ]
        )
        return "\n".join(lines)

    def doctor_report(self) -> dict[str, Any]:
        findings: list[dict[str, str]] = []
        registry = {spec.prefix: spec for spec in COMMAND_REGISTRY}
        missing = [command for command in SANDBOX_COMMANDS if command not in registry]
        findings.append(
            {"severity": "ERROR", "message": f"Sandbox commands missing from Registry: {', '.join(missing)}"}
            if missing
            else {"severity": "OK", "message": "All sandbox commands are registered."}
        )
        unsafe = [
            command
            for command in SANDBOX_COMMANDS
            if command in registry and (not registry[command].read_only or registry[command].mutates != "none" or registry[command].risk != "low")
        ]
        findings.append(
            {"severity": "ERROR", "message": f"Sandbox commands expose unsafe metadata: {', '.join(unsafe)}"}
            if unsafe
            else {"severity": "OK", "message": "Sandbox commands are low-risk, read-only, and mutates=none."}
        )
        unavailable = [command for command in _DEPENDENCY_COMMANDS if command not in registry]
        findings.append(
            {"severity": "WARN", "message": f"Optional sandbox-design dependencies unavailable: {', '.join(unavailable)}"}
            if unavailable
            else {"severity": "OK", "message": "Capability Map, Plan, Confirmation, Warning, Baseline, Pre-Change, Focus, and Acceptance helpers are reachable."}
        )
        invalid_candidates = [
            command
            for command in FUTURE_ALLOWLIST_CANDIDATES
            if command not in registry or not registry[command].read_only or registry[command].mutates != "none" or registry[command].risk != "low"
        ]
        findings.append(
            {"severity": "ERROR", "message": f"Future allowlist candidates are not conservative: {', '.join(invalid_candidates)}"}
            if invalid_candidates
            else {"severity": "OK", "message": "Every FUTURE_CANDIDATE is currently registered read-only/mutates=none/low-risk metadata."}
        )
        try:
            state = self.read_state()
        except Exception as exc:
            findings.append({"severity": "ERROR", "message": f"Sandbox readiness could not be computed: {exc}"})
        else:
            findings.append(
                {
                    "severity": "OK",
                    "message": f"Warning state is computable: accepted={len(state['accepted'])}, unknown={len(state['unknown'])}, blockers={state['blocker_count']}.",
                }
            )
            if state["unknown"] or state["blocker_count"]:
                findings.append({"severity": "BLOCKED", "message": "Unknown warnings or blockers prevent safe sandbox-blueprint progression."})
            if state["context_state"] == "enabled":
                findings.append({"severity": "WARN", "message": "Context Injection is explicitly enabled; Sandbox Blueprint did not change it."})
            else:
                findings.append({"severity": "OK", "message": "Context Injection is disabled."})
        findings.append(
            {
                "severity": "OK",
                "message": "No execution callback, runner command, subprocess/shell/eval/exec path, approval capture, authorization state, persistence, or dangerous action is exposed.",
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
                "Proto-Mind Execution Sandbox Design Handoff",
                f"Project: {self.project_root}",
                f"Current baseline: {state['accepted_baseline'] or 'not detected'}",
                "Rule 0: before changes run scripts/run_cli.sh, then /memory backup.",
                f"Registry: {len(COMMAND_REGISTRY)} commands across {len(categories)} categories",
                f"Capability safety: read_only={counts['read_only']}, mutating={counts['mutating']}, high_risk={counts['high_risk']}, confirmation_required={counts['confirmation_required']}, operator_only={counts['operator_only']}",
                f"Warnings: accepted={len(state['accepted'])}, unknown={len(state['unknown'])}, blockers={state['blocker_count']}",
                f"Context Injection: {state['context_state']}",
                "",
                "Confirmation vocabulary:",
                f"- {' | '.join(AUTHORIZATION_LEVELS)}",
                "",
                "Blueprint summary:",
                "- Structured intent -> Registry lookup -> Policy risk -> dry-run -> gates -> explicit confirmation -> scoped execution -> evidence -> human acceptance.",
                "- Execution remains forbidden in Sandbox Blueprint v1.",
                "",
                "Future allowlist candidates:",
                *[f"- FUTURE_CANDIDATE: {command}" for command in FUTURE_ALLOWLIST_CANDIDATES],
                "",
                "Denied classes:",
                "- Unknown, high-risk auto-run, operator-only auto-run, unconfirmed mutation, destructive/path-unsafe operations, shell/subprocess/eval/exec, hidden background work, and unscoped data/export/context changes.",
                "",
                "Required gates before any future runner:",
                *[f"- {gate}" for gate in _REQUIRED_GATES],
                "",
                "Verification commands:",
                "- scripts/which_python.sh",
                "- scripts/run_tests.sh",
                "- /opt/homebrew/opt/python@3.11/bin/python3.11 -m compileall proto_mind",
                "",
                "Required final report fields:",
                "- backup path; files changed; commands/behavior; Registry counts; tests/compileall; smoke; sandbox/confirmation safety; Context Injection; data/exports SHA-256; limitations/warnings.",
                "",
                "Next milestone:",
                "- Review /activation preconditions and /runner-mvp design; no active allowlist or runner is approved.",
                "",
                "Handoff safety:",
                "- Copyable text only; no clipboard, runner, command, subprocess, shell, eval/exec, confirmation, approval, authorization, file, snapshot, backup, or external call occurred.",
            ]
        )
