from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from proto_mind.action_policy import classify_command
from proto_mind.command_registry import COMMAND_REGISTRY
from proto_mind.memory_store import MemoryStore
from proto_mind.plan_layer import ActionDryRunPlan


CONFIRM_COMMANDS = (
    "/confirm status",
    "/confirm policy",
    "/confirm levels",
    "/confirm requirements",
    "/confirm doctor",
    "/confirm handoff",
)
AUTHORIZATION_LEVELS = (
    "NONE",
    "READ_ONLY_MANUAL",
    "CONFIRM_REQUIRED",
    "ELEVATED_CONFIRM_REQUIRED",
    "OPERATOR_ONLY",
    "BLOCKED",
)
_DEPENDENCY_COMMANDS = (
    "/capabilities status",
    "/capabilities safety",
    "/plan status",
    "/plan dry-run",
    "/plan gates",
    "/warnings unknown",
    "/baseline current",
    "/prechange status",
    "/focus plan",
    "/acceptance criteria",
)
_REQUIRED_GATES = (
    "Rule 0 backup/checkpoint is complete.",
    "/warnings unknown reports 0 unknown findings.",
    "Blocker count is 0.",
    "/capabilities safety has been reviewed.",
    "/plan dry-run has been shown and reviewed.",
    "Allowed writes are declared explicitly.",
    "Forbidden writes are declared explicitly.",
    "Verification commands and expected evidence are declared.",
    "A task-specific human confirmation phrase is required by any future execution-capable layer.",
    "Broad confirmations such as 'do it all' are invalid for high-risk actions.",
    "/activation preconditions and /activation blockers must be reviewed before any future activation task.",
)


def format_confirmation_command(command: str, *, project_root: Path, memory_store: MemoryStore) -> str | None:
    normalized = " ".join(command.strip().lower().split())
    if not normalized.startswith("/confirm"):
        return None
    gate = ConfirmationVocabulary(project_root=project_root, memory_store=memory_store)
    if normalized == "/confirm status":
        return gate.format_status()
    if normalized == "/confirm policy":
        return gate.format_policy()
    if normalized == "/confirm levels":
        return gate.format_levels()
    if normalized == "/confirm requirements":
        return gate.format_requirements()
    if normalized == "/confirm doctor":
        return gate.format_doctor()
    if normalized == "/confirm handoff":
        return gate.format_handoff()
    return "Usage:\n" + "\n".join(f"  {item}" for item in CONFIRM_COMMANDS)


class ConfirmationVocabulary:
    def __init__(self, *, project_root: Path, memory_store: MemoryStore) -> None:
        self.project_root = project_root
        self.memory_store = memory_store
        self.plan = ActionDryRunPlan(project_root=project_root, memory_store=memory_store)

    def read_state(self) -> dict[str, Any]:
        plan = self.plan.read_state()
        if plan["unknown"] or plan["blocker_count"]:
            readiness = "BLOCKED"
        elif plan["accepted"] or plan["system_status"] != "OK" or plan["context_state"] == "enabled":
            readiness = "WARN"
        else:
            readiness = "OK"
        generation_safe = (
            not plan["unknown"]
            and plan["blocker_count"] == 0
            and plan["context_state"] == "disabled"
            and plan["dry_run_planning_safe"]
        )
        return {
            **plan,
            "confirmation_readiness": readiness,
            "confirmation_policy_generation_safe": generation_safe,
        }

    def format_status(self) -> str:
        state = self.read_state()
        categories = Counter(spec.category for spec in COMMAND_REGISTRY)
        return "\n".join(
            [
                "Confirmation Gate Vocabulary Status",
                f"Status: {state['confirmation_readiness']}",
                f"project_root: {self.project_root}",
                f"command_registry: commands={len(COMMAND_REGISTRY)} categories={len(categories)}",
                f"context_injection: {state['context_state']}",
                f"capability_map_readiness: {state['capability_readiness']}",
                f"plan_layer_readiness: {state['plan_readiness']}",
                f"accepted_known_warnings: {len(state['accepted'])}",
                f"unknown_warnings: {len(state['unknown'])}",
                f"blockers: {state['blocker_count']}",
                f"confirmation_policy_generation_safe: {str(state['confirmation_policy_generation_safe']).lower()}",
                "",
                "Vocabulary boundary:",
                "- Advisory text only; no approval, authorization, confirmation phrase, command, or runtime state was captured or executed.",
            ]
        )

    def format_policy(self) -> str:
        return "\n".join(
            [
                "Proto-Mind Confirmation Policy (Advisory)",
                "1. Registered read-only commands may be proposed and manually run by the operator.",
                "2. Mutating commands require explicit, task-specific human confirmation in any future execution-capable layer.",
                "3. High-risk commands are blocked from future auto-execution until a separate elevated policy is explicitly designed and approved.",
                "4. Operator-only commands must never be auto-executed.",
                "5. Unknown or unregistered commands are BLOCKED and must never be treated as safe.",
                "6. Context Injection changes require a dedicated explicit task and confirmation.",
                "7. proto_mind/data or proto_mind/exports mutations require a dedicated explicit task and confirmation.",
                "8. Backup and snapshot creation must be explicit and visible, never hidden or incidental.",
                "9. Destructive commands require task-specific elevated confirmation and remain BLOCKED by default.",
                "",
                "Policy scope:",
                "- Read-only advisory vocabulary only; it does not enforce, capture, grant, or persist authorization because no execution engine is connected.",
            ]
        )

    def format_levels(self) -> str:
        return "\n".join(
            [
                "Authorization / Confirmation Vocabulary",
                "",
                "NONE:",
                "- meaning: informational output; no execution is available.",
                "- examples: /confirm policy, /plan dry-run.",
                "- allowed future behavior: display and inspect only.",
                "- forbidden: command execution, approval capture, or implied consent.",
                "",
                "READ_ONLY_MANUAL:",
                "- meaning: registered read-only command the operator may run manually.",
                "- examples: /data doctor, /capabilities map.",
                "- allowed future behavior: propose exact command with Registry metadata.",
                "- forbidden: hidden or automatic execution in this layer.",
                "",
                "CONFIRM_REQUIRED:",
                "- meaning: mutating/medium-risk action requiring explicit task-specific human confirmation.",
                "- examples: /memory remember, /context injection enable.",
                "- allowed future behavior: dry-run proposal after every gate passes.",
                "- forbidden: implicit, broad, cached, or automatic confirmation.",
                "",
                "ELEVATED_CONFIRM_REQUIRED:",
                "- meaning: high-risk action blocked until a separate elevated policy exists.",
                "- examples: /memory cleanup-apply, /action run.",
                "- allowed future behavior: design/review only under a dedicated task.",
                "- forbidden: current or future auto-execution under normal confirmation.",
                "",
                "OPERATOR_ONLY:",
                "- meaning: direct human/operator control only; never auto-execute.",
                "- examples: commands classified high-risk/operator-only by Action Policy.",
                "- allowed future behavior: operator may inspect a dry-run under separate policy.",
                "- forbidden: agent-initiated execution or delegation.",
                "",
                "BLOCKED:",
                "- meaning: unknown, unregistered, forbidden, shell-like, or chained command.",
                "- examples: unknown slash commands and arbitrary command chains.",
                "- allowed future behavior: none until separately registered, classified, and reviewed.",
                "- forbidden: proposal as safe, confirmation capture, or execution.",
                "",
                "Vocabulary note:",
                "- These labels describe future design constraints and grant no runtime authorization.",
            ]
        )

    def format_requirements(self) -> str:
        specs = list(COMMAND_REGISTRY)
        read_only = [spec for spec in specs if spec.read_only and spec.mutates == "none"]
        mutating = [spec for spec in specs if not spec.read_only or spec.mutates != "none"]
        high_risk = [spec for spec in specs if spec.risk == "high"]
        confirmation_required = [spec for spec in specs if classify_command(spec.prefix, specs).policy_class == "confirmation_required"]
        operator_only = [spec for spec in specs if classify_command(spec.prefix, specs).policy_class == "operator_only"]
        lines = [
            "Confirmation Requirements By Capability Class",
            f"- read-only ({len(read_only)}): READ_ONLY_MANUAL; operator runs explicitly; no hidden execution.",
            f"- mutating ({len(mutating)}): CONFIRM_REQUIRED at minimum; dedicated task, exact command, declared writes, verification, and receipt design.",
            f"- high-risk ({len(high_risk)}): ELEVATED_CONFIRM_REQUIRED and BLOCKED from auto-execution until elevated policy exists.",
            f"- confirmation-required ({len(confirmation_required)}): explicit task-specific human phrase; no cached or broad consent.",
            f"- operator-only ({len(operator_only)}): OPERATOR_ONLY; never auto-execute or delegate.",
            "- unknown/unregistered: BLOCKED; never SAFE, proposed as executable, or accepted through free text.",
            "",
            "Required gates:",
        ]
        lines.extend(f"{index}. {gate}" for index, gate in enumerate(_REQUIRED_GATES, start=1))
        lines.extend(
            [
                "",
                "Capture boundary:",
                "- No user input is parsed as confirmation and no approval/authorization state is stored.",
            ]
        )
        return "\n".join(lines)

    def format_doctor(self) -> str:
        report = self.doctor_report()
        lines = ["Confirmation Vocabulary Doctor", f"Status: {report['status']}", "", "Checks:"]
        lines.extend(f"- [{item['severity']}] {item['message']}" for item in report["findings"])
        lines.extend(
            [
                "",
                "Mutation policy:",
                "- Read-only diagnostics only; no confirmation, approval, authorization, command, file, snapshot, backup, repair, cleanup, migration, or external action occurred.",
            ]
        )
        return "\n".join(lines)

    def doctor_report(self) -> dict[str, Any]:
        findings: list[dict[str, str]] = []
        registry = {spec.prefix: spec for spec in COMMAND_REGISTRY}
        missing = [command for command in CONFIRM_COMMANDS if command not in registry]
        findings.append(
            {"severity": "ERROR", "message": f"Confirm commands missing from Registry: {', '.join(missing)}"}
            if missing
            else {"severity": "OK", "message": "All confirm commands are registered."}
        )
        unsafe = [
            command
            for command in CONFIRM_COMMANDS
            if command in registry and (not registry[command].read_only or registry[command].mutates != "none")
        ]
        findings.append(
            {"severity": "ERROR", "message": f"Confirm commands expose mutation: {', '.join(unsafe)}"}
            if unsafe
            else {"severity": "OK", "message": "Confirm commands are read-only with mutates=none."}
        )
        unavailable = [command for command in _DEPENDENCY_COMMANDS if command not in registry]
        findings.append(
            {"severity": "WARN", "message": f"Optional confirmation dependencies unavailable: {', '.join(unavailable)}"}
            if unavailable
            else {"severity": "OK", "message": "Capability Map, Plan, Warning, Baseline, Pre-Change, Focus, and Acceptance helpers are reachable."}
        )
        try:
            state = self.read_state()
        except Exception as exc:
            findings.append({"severity": "ERROR", "message": f"Confirmation readiness could not be computed: {exc}"})
        else:
            findings.append(
                {
                    "severity": "OK",
                    "message": f"Warning state is computable: accepted={len(state['accepted'])}, unknown={len(state['unknown'])}, blockers={state['blocker_count']}.",
                }
            )
            if state["unknown"] or state["blocker_count"]:
                findings.append({"severity": "BLOCKED", "message": "Unknown warnings or blockers prevent safe confirmation-policy design."})
            if state["context_state"] == "enabled":
                findings.append({"severity": "WARN", "message": "Context Injection is explicitly enabled; Confirmation Vocabulary did not change it."})
            else:
                findings.append({"severity": "OK", "message": "Context Injection is disabled."})
        dangerous = [
            spec.prefix
            for spec in COMMAND_REGISTRY
            if spec.category == "confirm" and (spec.risk == "high" or not spec.read_only or spec.mutates != "none")
        ]
        findings.append(
            {"severity": "ERROR", "message": f"Dangerous confirmation actions exposed: {', '.join(dangerous)}"}
            if dangerous
            else {"severity": "OK", "message": "No execution, approval capture, authorization, persistence, clipboard, snapshot, backup, repair, cleanup, migration, deletion, move, compression, or external action is exposed."}
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
                "Proto-Mind Confirmation Vocabulary Handoff",
                f"Project: {self.project_root}",
                f"Current baseline: {state['accepted_baseline'] or 'not detected'}",
                "Rule 0: before changes run scripts/run_cli.sh, then /memory backup.",
                f"Registry: {len(COMMAND_REGISTRY)} commands across {len(categories)} categories",
                f"Warnings: accepted={len(state['accepted'])}, unknown={len(state['unknown'])}, blockers={state['blocker_count']}",
                f"Context Injection: {state['context_state']}",
                "",
                "Confirmation vocabulary:",
                "- NONE | READ_ONLY_MANUAL | CONFIRM_REQUIRED | ELEVATED_CONFIRM_REQUIRED | OPERATOR_ONLY | BLOCKED",
                "",
                "Blocked classes:",
                "- Unknown/unregistered, shell-like/chained, destructive-by-default, high-risk without elevated policy, and operator-only auto-execution.",
                "",
                "Future execution boundary:",
                "- Execution, approval capture, and authorization remain forbidden in this layer.",
                "- Before any future execution feature: Rule 0, warnings/blockers=0, /capabilities safety, /plan dry-run, declared writes, verification, and task-specific confirmation design.",
                "",
                "Verification commands:",
                "- scripts/which_python.sh",
                "- scripts/run_tests.sh",
                "- /opt/homebrew/opt/python@3.11/bin/python3.11 -m compileall proto_mind",
                "",
                "Required final report fields:",
                "- backup path; files changed; commands/behavior; Registry counts; tests/compileall; smoke; safety; Context Injection; data/exports SHA-256; limitations/warnings.",
                "",
                "Next milestone:",
                "- Review /activation preconditions and /runner-mvp confirmation; confirmation capture and execution remain unimplemented.",
                "",
                "Handoff safety:",
                "- Copyable text only; no clipboard, command, model, confirmation, approval, authorization, file, snapshot, backup, or external call occurred.",
            ]
        )
