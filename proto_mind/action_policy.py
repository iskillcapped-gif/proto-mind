from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from proto_mind.command_registry import COMMAND_REGISTRY, CommandSpec, command_registry_doctor, match_registered_command
from proto_mind.natural_commands import NATURAL_COMMAND_ROUTES


POLICY_CLASSES = ("auto_allowed", "confirmation_required", "operator_only", "blocked")
POLICY_STRICTNESS = {name: index for index, name in enumerate(POLICY_CLASSES)}


@dataclass(frozen=True)
class PolicyDecision:
    policy_class: str
    reason: str
    safe_for_future_autonomy: bool
    command_input: str
    matched_spec: CommandSpec | None = None


def format_policy_command(command: str) -> str | None:
    stripped = command.strip()
    normalized = " ".join(stripped.lower().split())
    if not normalized.startswith("/policy"):
        return None
    if normalized == "/policy status":
        return format_policy_status()
    if normalized == "/policy doctor":
        return format_policy_doctor()
    if normalized.startswith("/policy explain"):
        query = stripped[len("/policy explain") :].strip()
        if not query:
            return "Usage: /policy explain <slash command>"
        return format_policy_explain(query)
    return "Usage:\n  /policy status\n  /policy explain <slash command>\n  /policy doctor"


def classify_command(command: str, registry: Iterable[CommandSpec] = COMMAND_REGISTRY) -> PolicyDecision:
    normalized = " ".join(command.strip().lower().split())
    if _looks_like_shell_or_chain(normalized):
        return PolicyDecision(
            "blocked",
            "Shell-like, chained, or non-slash input is blocked by policy.",
            False,
            command,
        )
    spec = match_registered_command(normalized, registry)
    if spec is None:
        return PolicyDecision("blocked", "Unknown command is not present in Command Registry.", False, command)
    if spec.risk == "high":
        return PolicyDecision(
            "operator_only",
            "High-risk commands require direct operator control and are never auto-allowed.",
            False,
            command,
            spec,
        )
    if not spec.read_only:
        return PolicyDecision(
            "confirmation_required",
            f"Command mutates {spec.mutates}; explicit operator confirmation is required.",
            False,
            command,
            spec,
        )
    if spec.risk == "medium":
        return PolicyDecision(
            "confirmation_required",
            "Read-only medium-risk command requires confirmation in policy v1.0.",
            False,
            command,
            spec,
        )
    return PolicyDecision(
        "auto_allowed",
        "Registered read-only low-risk command is advisory-safe for future autonomy.",
        True,
        command,
        spec,
    )


def classify_command_bundle(
    commands: Iterable[str],
    registry: Iterable[CommandSpec] = COMMAND_REGISTRY,
) -> dict[str, Any]:
    command_list = list(commands)
    decisions = [classify_command(command, registry) for command in command_list]
    if not decisions:
        return {
            "policy_class": "blocked",
            "reason": "Empty command bundle is blocked.",
            "safe_for_future_autonomy": False,
            "decisions": [],
        }
    strictest = max(decisions, key=lambda item: POLICY_STRICTNESS[item.policy_class])
    return {
        "policy_class": strictest.policy_class,
        "reason": f"Bundle uses strictest member policy: {strictest.policy_class} ({strictest.command_input}).",
        "safe_for_future_autonomy": all(item.safe_for_future_autonomy for item in decisions),
        "decisions": decisions,
    }


def classify_natural_route(
    target: str | tuple[str, ...],
    registry: Iterable[CommandSpec] = COMMAND_REGISTRY,
) -> dict[str, Any]:
    commands = (target,) if isinstance(target, str) else target
    return classify_command_bundle(commands, registry)


def format_policy_status(registry: Iterable[CommandSpec] = COMMAND_REGISTRY) -> str:
    specs = list(registry)
    counts = Counter(classify_command(spec.prefix, specs).policy_class for spec in specs)
    lines = [
        "Action Safety Policy Status",
        f"registered_commands: {len(specs)}",
        "policy_counts:",
    ]
    lines.extend(f"- {policy_class}: {counts.get(policy_class, 0)}" for policy_class in POLICY_CLASSES)
    lines.extend(
        [
            "",
            "Available commands:",
            "- /policy status",
            "- /policy explain <slash command>",
            "- /policy doctor",
            "",
            "Policy mode: read-only advisory; no command execution or enforcement.",
        ]
    )
    return "\n".join(lines)


def format_policy_explain(command: str) -> str:
    decision = classify_command(command)
    lines = [
        "Action Safety Policy Explain",
        f"input: {command}",
        f"matched: {decision.matched_spec is not None}",
    ]
    if decision.matched_spec is not None:
        spec = decision.matched_spec
        lines.extend(
            [
                f"command_prefix: {spec.prefix}",
                f"category: {spec.category}",
                f"read_only: {spec.read_only}",
                f"mutates: {spec.mutates}",
                f"risk: {spec.risk}",
                f"available_in_natural_router: {spec.available_in_natural_router}",
            ]
        )
    else:
        lines.extend(["command_prefix: none", "category: unknown", "read_only: unknown", "mutates: unknown", "risk: unknown"])
    lines.extend(
        [
            f"policy_class: {decision.policy_class}",
            f"reason: {decision.reason}",
            f"safe_for_future_autonomy: {decision.safe_for_future_autonomy}",
            "No command executed.",
        ]
    )
    return "\n".join(lines)


def action_policy_doctor(registry: Iterable[CommandSpec] = COMMAND_REGISTRY) -> dict[str, Any]:
    specs = list(registry)
    findings: list[dict[str, str]] = []
    registry_health = command_registry_doctor(specs)
    if registry_health["status"] != "OK":
        findings.append({"severity": "ERROR", "message": f"Command Registry Doctor status is {registry_health['status']}"})

    for spec in specs:
        decision = classify_command(spec.prefix, specs)
        if decision.policy_class not in POLICY_STRICTNESS:
            findings.append({"severity": "ERROR", "message": f"No valid policy class for {spec.prefix}"})
        if spec.risk == "high" and decision.policy_class == "auto_allowed":
            findings.append({"severity": "ERROR", "message": f"High-risk command is auto-allowed: {spec.prefix}"})
        if not spec.read_only and decision.policy_class == "auto_allowed":
            findings.append({"severity": "ERROR", "message": f"Mutating command is auto-allowed: {spec.prefix}"})

    if classify_command("/unknown command", specs).policy_class != "blocked":
        findings.append({"severity": "ERROR", "message": "Unknown commands are not blocked"})
    if classify_command("/data doctor; /memory remember unsafe", specs).policy_class != "blocked":
        findings.append({"severity": "ERROR", "message": "Chained commands are not blocked"})

    for phrase, target in NATURAL_COMMAND_ROUTES.items():
        bundle = classify_natural_route(target, specs)
        commands = (target,) if isinstance(target, str) else target
        expected = max(
            (classify_command(command, specs).policy_class for command in commands),
            key=lambda item: POLICY_STRICTNESS[item],
        )
        if bundle["policy_class"] != expected:
            findings.append({"severity": "ERROR", "message": f"Natural bundle does not use strictest policy: {phrase}"})
        for command in commands:
            spec = match_registered_command(command, specs)
            if spec and not spec.read_only and classify_command(command, specs).policy_class == "auto_allowed":
                findings.append({"severity": "ERROR", "message": f"Mutating natural route is auto-allowed: {phrase} -> {command}"})

    status = "ERROR" if any(item["severity"] == "ERROR" for item in findings) else "WARN" if findings else "OK"
    return {"status": status, "commands_checked": len(specs), "natural_routes_checked": len(NATURAL_COMMAND_ROUTES), "findings": findings}


def format_policy_doctor() -> str:
    report = action_policy_doctor()
    lines = [
        "Action Safety Policy Doctor",
        f"Status: {report['status']}",
        f"Commands checked: {report['commands_checked']}",
        f"Natural routes checked: {report['natural_routes_checked']}",
        "",
        "Findings:",
    ]
    if report["findings"]:
        lines.extend(f"- [{item['severity']}] {item['message']}" for item in report["findings"])
    else:
        lines.append("- [OK] Registry commands, unknown inputs, high-risk actions, mutations, and bundles satisfy policy invariants.")
    lines.extend(["", "Mutation policy:", "- Read-only advisory diagnostics only; no commands were executed and no stores were changed."])
    return "\n".join(lines)


def _looks_like_shell_or_chain(command: str) -> bool:
    if not command.startswith("/"):
        return True
    return any(token in command for token in ("\n", "\r", ";", "&&", "||", "`", "$("))
