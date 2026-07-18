from __future__ import annotations

from typing import Any

from proto_mind.action_policy import action_policy_doctor, classify_command, classify_command_bundle
from proto_mind.command_registry import command_registry_doctor
from proto_mind.natural_commands import NATURAL_COMMAND_ROUTES, natural_router_doctor, normalize_natural_command, route_natural_command


def format_action_command(command: str) -> str | None:
    stripped = command.strip()
    normalized = " ".join(stripped.lower().split())
    if not normalized.startswith("/action"):
        return None
    if normalized == "/action status":
        return format_action_status()
    if normalized == "/action doctor":
        return format_action_doctor()
    if normalized.startswith("/action preview"):
        action_input = stripped[len("/action preview") :].strip()
        if not action_input:
            return "Usage: /action preview <slash command or exact natural phrase>"
        return format_action_preview(action_input)
    return "Usage:\n  /action status\n  /action preview <slash command or exact natural phrase>\n  /action doctor"


def format_action_status() -> str:
    return "\n".join(
        [
            "Action Preview Status",
            "mode: read-only",
            "supports: slash commands and exact natural phrases",
            "sources: Natural Router, Command Registry, Action Safety Policy",
            "llm_matching: disabled",
            "fuzzy_matching: disabled",
            "execution: disabled",
            "",
            "Available commands:",
            "- /action status",
            "- /action preview <slash command or exact natural phrase>",
            "- /action doctor",
        ]
    )


def build_action_preview(action_input: str) -> dict[str, Any]:
    stripped = action_input.strip()
    if stripped.startswith("/"):
        decision = classify_command(stripped)
        return {
            "input": action_input,
            "input_type": "slash_command",
            "normalized": " ".join(stripped.lower().split()),
            "matched": decision.matched_spec is not None,
            "natural_phrase": "",
            "steps": [_decision_step(stripped, decision)] if decision.matched_spec is not None else [],
            "policy_class": decision.policy_class,
            "policy_reason": decision.reason,
            "safe_for_future_autonomy": decision.safe_for_future_autonomy,
            "suggestion": "",
        }

    normalized = normalize_natural_command(stripped)
    target = route_natural_command(stripped)
    if target is None:
        return {
            "input": action_input,
            "input_type": "natural_phrase",
            "normalized": normalized,
            "matched": False,
            "natural_phrase": stripped,
            "steps": [],
            "policy_class": "blocked",
            "policy_reason": "No exact natural route matched; no execution plan was created.",
            "safe_for_future_autonomy": False,
            "suggestion": f"/natural suggest {stripped}",
        }

    commands = (target,) if isinstance(target, str) else target
    decisions = [classify_command(command) for command in commands]
    bundle = classify_command_bundle(commands)
    if len(decisions) == 1:
        aggregate_policy = decisions[0].policy_class
        aggregate_reason = decisions[0].reason
        aggregate_safe = decisions[0].safe_for_future_autonomy
    else:
        aggregate_policy = bundle["policy_class"]
        aggregate_reason = bundle["reason"]
        aggregate_safe = bundle["safe_for_future_autonomy"]
    return {
        "input": action_input,
        "input_type": "natural_phrase",
        "normalized": normalized,
        "matched": True,
        "natural_phrase": stripped,
        "steps": [_decision_step(command, decision) for command, decision in zip(commands, decisions)],
        "policy_class": aggregate_policy,
        "policy_reason": aggregate_reason,
        "safe_for_future_autonomy": aggregate_safe,
        "suggestion": "",
    }


def format_action_preview(action_input: str) -> str:
    preview = build_action_preview(action_input)
    lines = [
        "Action Preview",
        f"input: {preview['input']}",
        f"input_type: {preview['input_type']}",
        f"normalized: {preview['normalized']}",
        f"matched: {preview['matched']}",
    ]
    if preview["input_type"] == "natural_phrase":
        lines.append(f"natural_phrase: {preview['natural_phrase']}")
    if preview["steps"]:
        lines.extend(["", "Execution plan:"])
        for index, step in enumerate(preview["steps"], start=1):
            lines.extend(
                [
                    f"Step {index}:",
                    f"  command: {step['command']}",
                    f"  matched_prefix: {step['matched_prefix']}",
                    f"  category: {step['category']}",
                    f"  read_only: {step['read_only']}",
                    f"  mutates: {step['mutates']}",
                    f"  risk: {step['risk']}",
                    f"  policy_class: {step['policy_class']}",
                    f"  policy_reason: {step['policy_reason']}",
                ]
            )
        if len(preview["steps"]) > 1:
            lines.append(f"strictest_bundle_policy: {preview['policy_class']}")
    else:
        lines.extend(["", "Execution plan: none"])
    lines.extend(
        [
            f"overall_policy: {preview['policy_class']}",
            f"policy_reason: {preview['policy_reason']}",
            f"safe_for_future_autonomy: {preview['safe_for_future_autonomy']}",
        ]
    )
    if preview["suggestion"]:
        lines.append(f"suggestion: {preview['suggestion']}")
    lines.extend(["", "No command executed."])
    return "\n".join(lines)


def action_preview_doctor() -> dict[str, Any]:
    findings: list[dict[str, str]] = []
    known = build_action_preview("/data doctor")
    natural = build_action_preview("что делать дальше")
    bundle = build_action_preview("проверь систему")
    unknown_slash = build_action_preview("/unknown command")
    unknown_natural = build_action_preview("какая сегодня погода")

    if not known["matched"] or known["policy_class"] != "auto_allowed":
        findings.append({"severity": "ERROR", "message": "Known slash command preview did not resolve safely"})
    if not natural["matched"] or not natural["steps"]:
        findings.append({"severity": "ERROR", "message": "Known natural phrase preview did not resolve"})
    expected_bundle = classify_command_bundle(NATURAL_COMMAND_ROUTES[normalize_natural_command("проверь систему")])
    if bundle["policy_class"] != expected_bundle["policy_class"]:
        findings.append({"severity": "ERROR", "message": "Natural bundle preview did not use strictest policy"})
    if unknown_slash["policy_class"] != "blocked" or unknown_slash["matched"]:
        findings.append({"severity": "ERROR", "message": "Unknown slash command is not blocked"})
    if unknown_natural["matched"] or not unknown_natural["suggestion"].startswith("/natural suggest "):
        findings.append({"severity": "ERROR", "message": "Unknown natural phrase did not produce a safe suggestion"})

    dependencies = {
        "Command Registry Doctor": command_registry_doctor()["status"],
        "Action Safety Policy Doctor": action_policy_doctor()["status"],
        "Natural Command Router Doctor": natural_router_doctor()["status"],
    }
    for name, status in dependencies.items():
        if status != "OK":
            findings.append({"severity": "ERROR", "message": f"{name} status is {status}"})

    status = "ERROR" if any(item["severity"] == "ERROR" for item in findings) else "WARN" if findings else "OK"
    return {"status": status, "findings": findings, "dependencies": dependencies}


def format_action_doctor() -> str:
    report = action_preview_doctor()
    lines = ["Action Preview Doctor", f"Status: {report['status']}", "", "Dependency doctors:"]
    lines.extend(f"- {name}: {status}" for name, status in report["dependencies"].items())
    lines.extend(["", "Findings:"])
    if report["findings"]:
        lines.extend(f"- [{item['severity']}] {item['message']}" for item in report["findings"])
    else:
        lines.append("- [OK] Slash, natural, bundle, unknown, and dependency preview checks passed.")
    lines.extend(["", "Mutation policy:", "- Read-only preview only; no commands were executed and no stores were changed."])
    return "\n".join(lines)


def _decision_step(command: str, decision: Any) -> dict[str, Any]:
    spec = decision.matched_spec
    if spec is None:
        return {
            "command": command,
            "matched_prefix": "none",
            "category": "unknown",
            "read_only": "unknown",
            "mutates": "unknown",
            "risk": "unknown",
            "policy_class": decision.policy_class,
            "policy_reason": decision.reason,
        }
    return {
        "command": command,
        "matched_prefix": spec.prefix,
        "category": spec.category,
        "read_only": spec.read_only,
        "mutates": spec.mutates,
        "risk": spec.risk,
        "policy_class": decision.policy_class,
        "policy_reason": decision.reason,
    }
