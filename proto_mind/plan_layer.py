from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from proto_mind.action_policy import POLICY_CLASSES, classify_command
from proto_mind.capability_map import CommandCapabilityMap
from proto_mind.command_registry import COMMAND_REGISTRY
from proto_mind.memory_store import MemoryStore


PLAN_COMMANDS = (
    "/plan status",
    "/plan next",
    "/plan dry-run",
    "/plan gates",
    "/plan doctor",
    "/plan handoff",
)
_DEPENDENCY_COMMANDS = (
    "/capabilities status",
    "/capabilities map",
    "/capabilities safety",
    "/memory-card codex",
    "/warnings unknown",
    "/baseline current",
    "/prechange status",
    "/focus plan",
    "/acceptance criteria",
    "/milestone next",
)
_REQUIRED_GATES = (
    "Rule 0 backup/checkpoint before any implementation change.",
    "/warnings unknown must report 0 unknown findings.",
    "Blocker count must be 0.",
    "Context Injection must remain disabled unless the task explicitly enables it.",
    "/capabilities safety must be reviewed.",
    "/confirm policy and /confirm levels must be reviewed.",
    "Mutating, high-risk, and operator-only commands require explicit human confirmation.",
    "A dry-run plan must be shown before any future execution-capable action.",
    "Allowed writes and forbidden writes must be declared explicitly.",
    "Verification commands and expected evidence must be declared before work starts.",
    "For read-only runtime tasks, compare proto_mind/data and proto_mind/exports SHA-256 against Rule 0.",
)


def format_plan_command(command: str, *, project_root: Path, memory_store: MemoryStore) -> str | None:
    normalized = " ".join(command.strip().lower().split())
    if not normalized.startswith("/plan"):
        return None
    plan = ActionDryRunPlan(project_root=project_root, memory_store=memory_store)
    if normalized == "/plan status":
        return plan.format_status()
    if normalized == "/plan next":
        return plan.format_next()
    if normalized == "/plan dry-run":
        return plan.format_dry_run()
    if normalized == "/plan gates":
        return plan.format_gates()
    if normalized == "/plan doctor":
        return plan.format_doctor()
    if normalized == "/plan handoff":
        return plan.format_handoff()
    return "Usage:\n" + "\n".join(f"  {item}" for item in PLAN_COMMANDS)


class ActionDryRunPlan:
    def __init__(self, *, project_root: Path, memory_store: MemoryStore) -> None:
        self.project_root = project_root
        self.memory_store = memory_store
        self.capabilities = CommandCapabilityMap(project_root=project_root, memory_store=memory_store)

    def read_state(self) -> dict[str, Any]:
        capability = self.capabilities.read_state()
        if capability["unknown"] or capability["blocker_count"]:
            readiness = "BLOCKED"
        elif capability["accepted"] or capability["system_status"] != "OK" or capability["context_state"] == "enabled":
            readiness = "WARN"
        else:
            readiness = "OK"
        planning_safe = (
            not capability["unknown"]
            and capability["blocker_count"] == 0
            and capability["context_state"] == "disabled"
            and capability["capability_generation_safe"]
        )
        return {
            **capability,
            "plan_readiness": readiness,
            "dry_run_planning_safe": planning_safe,
        }

    def format_status(self) -> str:
        state = self.read_state()
        categories = Counter(spec.category for spec in COMMAND_REGISTRY)
        return "\n".join(
            [
                "Proposed Action Plan Status",
                f"Status: {state['plan_readiness']}",
                f"project_root: {self.project_root}",
                f"command_registry: commands={len(COMMAND_REGISTRY)} categories={len(categories)}",
                f"context_injection: {state['context_state']}",
                f"capability_map_readiness: {state['capability_readiness']}",
                f"accepted_known_warnings: {len(state['accepted'])}",
                f"unknown_warnings: {len(state['unknown'])}",
                f"blockers: {state['blocker_count']}",
                f"dry_run_planning_safe: {str(state['dry_run_planning_safe']).lower()}",
                "",
                "Planning boundary:",
                "- Proposal text only; no intent, plan, approval, queue item, command, or runtime state was persisted or executed.",
            ]
        )

    def format_next(self) -> str:
        state = self.read_state()
        if state["unknown"]:
            intent = "Inspect unknown warnings before proposing implementation work."
            action = "Review /warnings unknown and classify every new finding manually."
            commands = ("/warnings unknown", "/capabilities safety")
            risk = "BLOCKED until unknown warnings are resolved or explicitly reviewed"
        elif state["blocker_count"]:
            intent = "Resolve current blockers before proposing implementation work."
            action = "Review /acceptance status and blocker evidence manually."
            commands = ("/acceptance status", "/plan gates")
            risk = "BLOCKED while blockers are present"
        elif state["dry_run_planning_safe"]:
            intent = "Prepare the next explicit, manual-only Proto-Mind milestone."
            action = "Review activation preconditions and the locked read-only Runner MVP design; any real implementation requires a separate explicit task."
            commands = ("/capabilities map", "/plan gates", "/confirm policy", "/activation preconditions", "/activation blockers", "/runner-mvp design", "/runner-mvp allowlist", "/runner-mvp stop-conditions", "/memory-card codex", "/prechange status", "/milestone next")
            risk = "LOW for this read-only proposal; future commands remain UNKNOWN until registered and classified"
        else:
            intent = "Restore safe dry-run planning readiness."
            action = "Review /plan status and /capabilities status before selecting work."
            commands = ("/plan status", "/capabilities status")
            risk = "UNKNOWN / not ready"
        lines = [
            "Proposed Next Action Plan",
            f"Status: {state['plan_readiness']}",
            f"Intent: {intent}",
            f"Recommended manual action: {action}",
            f"Risk class: {risk}",
            "",
            "Related commands to run manually:",
        ]
        lines.extend(f"- {command}" for command in commands)
        lines.extend(["", "Required gates:"])
        lines.extend(f"- {gate}" for gate in _REQUIRED_GATES[:6])
        lines.extend(
            [
                "",
                "Expected evidence:",
                "- Rule 0 backup path; declared scope/writes; Registry and policy classification; tests/compileall; task-specific smoke; Context Injection state; data/exports SHA-256 when read-only.",
                "",
                "Done criteria:",
                "- Scope is explicit, all gates pass, verification evidence is reported, unknown warnings/blockers remain zero, and no forbidden runtime mutation occurred.",
                "",
                "No execution:",
                "- No related command was run and no plan, approval, task, milestone, or authorization state was created.",
            ]
        )
        return "\n".join(lines)

    def format_dry_run(self) -> str:
        return "\n".join(
            [
                "Deterministic Dry-Run Action Plan Template",
                "",
                "Operator Intent:",
                "- State one explicit objective and why it is needed.",
                "",
                "Proposed Commands:",
                "- List exact commands for manual review; do not execute them here.",
                "",
                "Command Safety Classification:",
                "- For each command record Registry match, read_only, mutates, risk, and Action Policy class; UNKNOWN if unregistered.",
                "",
                "Required Gates:",
                "- Rule 0; unknown warnings=0; blockers=0; Context Injection policy; capability safety; declared writes; verification plan.",
                "",
                "Forbidden Actions:",
                "- No shell/arbitrary command, hidden mutation, background task, auto-apply, repair, cleanup, migration, deletion, move, compression, snapshot, or unapproved external action.",
                "",
                "Expected Evidence:",
                "- Backup path, changed files, Registry/policy metadata, tests, compileall, smoke, Context Injection, SHA-256, warnings, and limitations.",
                "",
                "Acceptance Criteria:",
                "- Required behavior passes; safety invariants hold; no unknown warning or blocker remains; documentation matches implementation.",
                "",
                "Rollback / Stop Conditions:",
                "- Stop on failed gate, unexpected write, policy mismatch, unknown command, test regression, Context Injection change, or scope expansion.",
                "",
                "Human Confirmation Required:",
                "- Required before any mutating, high-risk, operator-only, external, destructive, or execution-capable step.",
                "",
                "Template boundary:",
                "- No free text was parsed, no command was classified for execution, and no plan or confirmation was stored.",
            ]
        )

    def format_gates(self) -> str:
        lines = ["Future Execution Safety Gates"]
        lines.extend(f"{index}. {gate}" for index, gate in enumerate(_REQUIRED_GATES, start=1))
        lines.extend(
            [
                "",
                "Gate policy:",
                "- A failed or unknown gate means STOP. This layer cannot waive, satisfy, or execute a gate automatically.",
            ]
        )
        return "\n".join(lines)

    def format_doctor(self) -> str:
        report = self.doctor_report()
        lines = ["Proposed Action Plan Doctor", f"Status: {report['status']}", "", "Checks:"]
        lines.extend(f"- [{item['severity']}] {item['message']}" for item in report["findings"])
        lines.extend(
            [
                "",
                "Mutation policy:",
                "- Read-only diagnostics only; no plan, approval, authorization, queue, command, file, snapshot, backup, repair, cleanup, migration, or external action occurred.",
            ]
        )
        return "\n".join(lines)

    def doctor_report(self) -> dict[str, Any]:
        findings: list[dict[str, str]] = []
        registry = {spec.prefix: spec for spec in COMMAND_REGISTRY}
        missing = [command for command in PLAN_COMMANDS if command not in registry]
        findings.append(
            {"severity": "ERROR", "message": f"Plan commands missing from Registry: {', '.join(missing)}"}
            if missing
            else {"severity": "OK", "message": "All plan commands are registered."}
        )
        unsafe = [
            command
            for command in PLAN_COMMANDS
            if command in registry and (not registry[command].read_only or registry[command].mutates != "none")
        ]
        findings.append(
            {"severity": "ERROR", "message": f"Plan commands expose mutation: {', '.join(unsafe)}"}
            if unsafe
            else {"severity": "OK", "message": "Plan commands are read-only with mutates=none."}
        )
        unavailable = [command for command in _DEPENDENCY_COMMANDS if command not in registry]
        findings.append(
            {"severity": "WARN", "message": f"Optional plan dependencies unavailable: {', '.join(unavailable)}"}
            if unavailable
            else {"severity": "OK", "message": "Capability Map, Warning, Baseline, Pre-Change, Focus, Acceptance, Memory Card, and Milestone helpers are reachable."}
        )
        try:
            state = self.read_state()
        except Exception as exc:
            findings.append({"severity": "ERROR", "message": f"Dry-run planning readiness could not be computed: {exc}"})
        else:
            findings.append(
                {
                    "severity": "OK",
                    "message": f"Warning state is computable: accepted={len(state['accepted'])}, unknown={len(state['unknown'])}, blockers={state['blocker_count']}.",
                }
            )
            if state["unknown"] or state["blocker_count"]:
                findings.append({"severity": "BLOCKED", "message": "Unknown warnings or blockers prevent safe dry-run planning."})
            if state["context_state"] == "enabled":
                findings.append({"severity": "WARN", "message": "Context Injection is explicitly enabled; Plan Layer did not change it."})
            else:
                findings.append({"severity": "OK", "message": "Context Injection is disabled."})
        dangerous = [
            spec.prefix
            for spec in COMMAND_REGISTRY
            if spec.category == "plan" and (spec.risk == "high" or not spec.read_only or spec.mutates != "none")
        ]
        findings.append(
            {"severity": "ERROR", "message": f"Dangerous plan actions exposed: {', '.join(dangerous)}"}
            if dangerous
            else {"severity": "OK", "message": "No execution, authorization, approval, persistence, clipboard, snapshot, backup, repair, cleanup, migration, deletion, move, compression, or external action is exposed."}
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
        policy_counts = Counter(classify_command(spec.prefix).policy_class for spec in COMMAND_REGISTRY)
        return "\n".join(
            [
                "Proto-Mind Dry-Run Planning Handoff",
                f"Project: {self.project_root}",
                f"Current baseline: {state['accepted_baseline'] or 'not detected'}",
                "Rule 0: before changes run scripts/run_cli.sh, then /memory backup.",
                f"Registry: {len(COMMAND_REGISTRY)} commands across {len(categories)} categories",
                f"Capability safety: " + ", ".join(f"{name}={policy_counts.get(name, 0)}" for name in POLICY_CLASSES),
                f"Warnings: accepted={len(state['accepted'])}, unknown={len(state['unknown'])}, blockers={state['blocker_count']}",
                f"Context Injection: {state['context_state']}",
                "",
                "Dry-run requirement:",
                "- Show intent, exact proposed commands, Registry/Policy metadata, gates, evidence, done criteria, and stop conditions before any future execution-capable step.",
                "- Review /confirm policy, /confirm levels, and /confirm requirements before designing authorization behavior.",
                "- Review /sandbox blueprint, /sandbox boundaries, /sandbox allowlist, and /sandbox denied before designing any runner.",
                "- Review /runner contract, /runner noop, and /runner disabled; execution_enabled and executed must remain false.",
                "- Review /runner-candidates list, /runner-candidates denied, and /runner-candidates gates; every candidate must remain NOT_ACTIVE.",
                "- Review /activation preconditions, /activation blockers, and /activation forbidden; no activation is performed.",
                "- Review /runner-mvp design, allowlist, confirmation, evidence, and stop-conditions; design lock grants no implementation authority.",
                "- Execution and authorization are forbidden in Plan Layer v1.",
                "",
                "Required gates:",
                "- Rule 0; unknown warnings=0; blockers=0; Context Injection policy; /capabilities safety; declared writes; verification; read-only SHA-256 when applicable.",
                "",
                "Verification commands:",
                "- scripts/which_python.sh",
                "- scripts/run_tests.sh",
                "- /opt/homebrew/opt/python@3.11/bin/python3.11 -m compileall proto_mind",
                "",
                "Required final report fields:",
                "- backup path; files changed; commands/behavior; Registry counts; tests/compileall; smoke; safety; Context Injection; data/exports SHA-256; limitations/warnings.",
                "",
                "Handoff safety:",
                "- Copyable text only; no clipboard, command, model, plan state, approval, authorization, file, snapshot, backup, or external call occurred.",
            ]
        )
