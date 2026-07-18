from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping
from difflib import get_close_matches
from typing import Any


HEALTH_CHECK_BUNDLE = (
    "/data doctor",
    "/data refs-doctor",
    "/loop doctor",
    "/memory doctor",
    "/consolidation queue-doctor",
)

EVENING_REVIEW_BUNDLE = (
    "/loop evening-review",
    "/loop capture-today",
)

NATURAL_ROUTE_GROUPS = (
    ("health bundle", HEALTH_CHECK_BUNDLE),
    ("session self-check", "/session self-check"),
    ("loop next", "/loop next"),
    ("morning plan", "/loop morning-plan"),
    ("evening bundle", EVENING_REVIEW_BUNDLE),
    ("context enable", "/context injection enable"),
    ("context disable", "/context injection disable"),
    ("consolidation preview", "/consolidation preview"),
    ("data inventory", "/data inventory"),
)

ALLOWED_NATURAL_TARGETS = {
    "/session self-check",
    "/data doctor",
    "/data refs-doctor",
    "/loop doctor",
    "/memory doctor",
    "/consolidation queue-doctor",
    "/loop next",
    "/loop morning-plan",
    "/loop evening-review",
    "/loop capture-today",
    "/context injection enable",
    "/context injection disable",
    "/consolidation preview",
    "/data inventory",
}

EXPLICIT_MUTATION_TARGETS = {
    "/context injection enable",
    "/context injection disable",
}


NATURAL_COMMAND_ROUTES = {
    "проверь свою систему": "/session self-check",
    "проверь систему": HEALTH_CHECK_BUNDLE,
    "проверь себя": HEALTH_CHECK_BUNDLE,
    "сделай медосмотр": HEALTH_CHECK_BUNDLE,
    "есть ли проблемы": HEALTH_CHECK_BUNDLE,
    "проведи самодиагностику": "/session self-check",
    "запусти самодиагностику": "/session self-check",
    "сделай самодиагностику": "/session self-check",
    "самодиагностика": "/session self-check",
    "системная проверка": "/session self-check",
    "check your system": "/session self-check",
    "check the system": "/session self-check",
    "run self check": "/session self-check",
    "run system check": HEALTH_CHECK_BUNDLE,
    "self check": "/session self-check",
    "system self check": "/session self-check",
    "что дальше": "/loop next",
    "что делать дальше": "/loop next",
    "какой следующий шаг": "/loop next",
    "next action": "/loop next",
    "начать день": "/loop morning-plan",
    "утренний план": "/loop morning-plan",
    "morning plan": "/loop morning-plan",
    "закрыть день": EVENING_REVIEW_BUNDLE,
    "вечерний обзор": EVENING_REVIEW_BUNDLE,
    "подвести итоги дня": EVENING_REVIEW_BUNDLE,
    "evening review": EVENING_REVIEW_BUNDLE,
    "включи контекст": "/context injection enable",
    "возьми рюкзак": "/context injection enable",
    "работай с учетом контекста": "/context injection enable",
    "enable context": "/context injection enable",
    "выключи контекст": "/context injection disable",
    "сними рюкзак": "/context injection disable",
    "disable context": "/context injection disable",
    "что стоит запомнить": "/consolidation preview",
    "что нужно сохранить в память": "/consolidation preview",
    "найди выводы": "/consolidation preview",
    "memory candidates": "/consolidation preview",
    "покажи хранилища": "/data inventory",
    "инвентаризация данных": "/data inventory",
    "data inventory": "/data inventory",
}


def normalize_natural_command(text: str) -> str:
    normalized = text.strip().casefold().replace("ё", "е")
    normalized = normalized.replace("-", " ")
    normalized = normalized.rstrip(" \t\r\n.!?…")
    return " ".join(normalized.split())


def route_natural_command(text: str) -> str | tuple[str, ...] | None:
    return NATURAL_COMMAND_ROUTES.get(normalize_natural_command(text))


def format_natural_introspection_command(command: str) -> str | None:
    stripped = command.strip()
    normalized = " ".join(stripped.lower().split())
    if not normalized.startswith("/natural"):
        return None
    if normalized == "/natural status":
        return format_natural_status()
    if normalized == "/natural list":
        return format_natural_list()
    if normalized == "/natural doctor":
        return format_natural_doctor()
    if normalized.startswith("/natural suggest"):
        phrase = stripped[len("/natural suggest") :].strip()
        if not phrase:
            return "Usage: /natural suggest <phrase>"
        return format_natural_suggest(_strip_phrase_quotes(phrase))
    if normalized.startswith("/natural explain"):
        phrase = stripped[len("/natural explain") :].strip()
        if not phrase:
            return "Usage: /natural explain <phrase>"
        return format_natural_explain(_strip_phrase_quotes(phrase))
    return "Usage:\n  /natural status\n  /natural list\n  /natural explain <phrase>\n  /natural suggest <phrase>\n  /natural doctor"


def format_natural_status(routes: Mapping[str, str | tuple[str, ...]] = NATURAL_COMMAND_ROUTES) -> str:
    bundle_count = sum(1 for target in routes.values() if isinstance(target, tuple))
    single_count = len(routes) - bundle_count
    return "\n".join(
        [
            "Natural Command Router Status",
            f"routes: {len(routes)}",
            f"bundle_routes: {bundle_count}",
            f"single_command_routes: {single_count}",
            "mode: deterministic exact normalized phrase matching",
            "llm_routing: disabled",
            "fuzzy_routing: disabled",
            "",
            "Available commands:",
            "- /natural status",
            "- /natural list",
            "- /natural explain <phrase>",
            "- /natural suggest <phrase>",
            "- /natural doctor",
        ]
    )


def format_natural_list(routes: Mapping[str, str | tuple[str, ...]] = NATURAL_COMMAND_ROUTES) -> str:
    lines = ["Natural Command Routes"]
    grouped_phrases: set[str] = set()
    for group_name, group_target in NATURAL_ROUTE_GROUPS:
        phrases = [phrase for phrase, target in routes.items() if target == group_target]
        policy = _target_policy(group_target)
        lines.extend(["", f"{group_name}:", f"  target: {_format_target(group_target)} [{policy['policy_class']}]"])
        if phrases:
            for phrase in sorted(phrases):
                lines.append(f"  - {phrase}")
                grouped_phrases.add(phrase)
        else:
            lines.append("  - (none)")
    ungrouped = [phrase for phrase in routes if phrase not in grouped_phrases]
    if ungrouped:
        lines.extend(["", "ungrouped:"])
        for phrase in sorted(ungrouped):
            lines.append(f"  - {phrase} -> {_format_target(routes[phrase])}")
    return "\n".join(lines)


def format_natural_explain(phrase: str) -> str:
    normalized = normalize_natural_command(phrase)
    target = NATURAL_COMMAND_ROUTES.get(normalized)
    lines = [
        "Natural Route Explain",
        f"input: {phrase}",
        f"normalized: {normalized}",
        f"matched: {target is not None}",
    ]
    if target is None:
        lines.extend(
            [
                "target: none",
                "effect: none",
                "bypasses_reasoner: False",
                "bypasses_context_injection: False",
            ]
        )
    else:
        policy = _target_policy(target)
        lines.extend(
            [
                f"target_type: {'bundle' if isinstance(target, tuple) else 'single_command'}",
                f"target: {_format_target(target)}",
                f"effect: {_route_effect(target)}",
                f"policy_class: {policy['policy_class']}",
                f"safe_for_future_autonomy: {policy['safe_for_future_autonomy']}",
                "bypasses_reasoner: True",
                "bypasses_context_injection: True",
            ]
        )
        if isinstance(target, tuple):
            lines.append(f"bundle_strictest_policy: {policy['policy_class']}")
        lines.extend(["", "Command registry metadata:"])
        for command in _target_commands(target) or ():
            lines.extend(_format_command_metadata(command))
    return "\n".join(lines)


def format_natural_suggest(phrase: str, *, limit: int = 5, cutoff: float = 0.6) -> str:
    normalized = normalize_natural_command(phrase)
    exact_target = NATURAL_COMMAND_ROUTES.get(normalized)
    lines = [
        "Natural Command Suggestions",
        f"input: {phrase}",
        f"normalized: {normalized}",
        f"matched: {exact_target is not None}",
    ]
    if exact_target is not None:
        lines.extend(
            [
                f"target_type: {'bundle' if isinstance(exact_target, tuple) else 'single_command'}",
                f"target: {_format_target(exact_target)}",
                f"effect: {_route_effect(exact_target)}",
                "bypasses_reasoner: True",
                "bypasses_context_injection: True",
            ]
        )
    else:
        suggestions = get_close_matches(
            normalized,
            list(NATURAL_COMMAND_ROUTES),
            n=max(0, min(limit, 5)),
            cutoff=cutoff,
        )
        lines.append("suggestions:")
        if not suggestions:
            lines.append("- none")
        else:
            for suggestion in suggestions:
                target = NATURAL_COMMAND_ROUTES[suggestion]
                lines.append(
                    f"- {suggestion} -> {_target_group_name(target)}: {_format_target(target)} [{_route_effect(target)}]"
                )
    lines.extend(["", "No command executed."])
    return "\n".join(lines)


def natural_router_doctor(
    routes: Mapping[str, str | tuple[str, ...]] | Iterable[tuple[str, str | tuple[str, ...]]] = NATURAL_COMMAND_ROUTES,
) -> dict[str, Any]:
    entries = list(routes.items()) if isinstance(routes, Mapping) else list(routes)
    findings: list[dict[str, str]] = []
    normalized_phrases = [normalize_natural_command(str(phrase)) for phrase, _ in entries]
    empty_indexes = [str(index) for index, phrase in enumerate(normalized_phrases, start=1) if not phrase]
    if empty_indexes:
        findings.append({"severity": "ERROR", "message": f"Empty natural phrases at entries: {', '.join(empty_indexes)}"})
    duplicates = sorted(phrase for phrase, count in Counter(normalized_phrases).items() if phrase and count > 1)
    if duplicates:
        findings.append({"severity": "ERROR", "message": f"Duplicate normalized phrases: {', '.join(duplicates)}"})

    for phrase, target in entries:
        commands = _target_commands(target)
        if commands is None:
            findings.append({"severity": "ERROR", "message": f"Invalid route target type for phrase: {phrase}"})
            continue
        if not commands:
            findings.append({"severity": "ERROR", "message": f"Empty command bundle for phrase: {phrase}"})
            continue
        for command in commands:
            if _looks_like_shell_or_chain(command):
                findings.append({"severity": "ERROR", "message": f"Unsafe command target for phrase '{phrase}': {command}"})
            elif command not in ALLOWED_NATURAL_TARGETS:
                findings.append({"severity": "ERROR", "message": f"Non-allowlisted command target for phrase '{phrase}': {command}"})
        if any(command in EXPLICIT_MUTATION_TARGETS for command in commands) and _route_effect(target) != "explicit mutation":
            findings.append({"severity": "ERROR", "message": f"Context mutation route is not marked explicit: {phrase}"})

        registry_specs = _registry_specs_for_target(target)
        for command, spec in zip(commands, registry_specs):
            if spec is None:
                findings.append({"severity": "ERROR", "message": f"Natural target missing Command Registry metadata: {phrase} -> {command}"})
        policy = _target_policy(target)
        if policy["policy_class"] not in {"auto_allowed", "confirmation_required", "operator_only", "blocked"}:
            findings.append({"severity": "ERROR", "message": f"Natural target has invalid policy classification: {phrase}"})
        if any(spec is not None and not spec.read_only for spec in registry_specs) and policy["policy_class"] == "auto_allowed":
            findings.append({"severity": "ERROR", "message": f"Mutating natural route is auto-allowed: {phrase}"})
        if isinstance(target, tuple):
            expected = _strictest_member_policy(commands)
            if policy["policy_class"] != expected:
                findings.append({"severity": "ERROR", "message": f"Natural bundle policy is not strictest member policy: {phrase}"})

    if not {"/data doctor", "/data refs-doctor"}.issubset(HEALTH_CHECK_BUNDLE):
        findings.append({"severity": "ERROR", "message": "Health bundle is missing required data doctor commands"})
    if not {"/loop evening-review", "/loop capture-today"}.issubset(EVENING_REVIEW_BUNDLE):
        findings.append({"severity": "ERROR", "message": "Evening bundle is missing required loop commands"})
    registry_doctor_status, policy_doctor_status = _dependency_doctor_statuses()
    if registry_doctor_status != "OK":
        findings.append({"severity": "ERROR", "message": f"Command Registry Doctor status is {registry_doctor_status}"})
    if policy_doctor_status != "OK":
        findings.append({"severity": "ERROR", "message": f"Action Safety Policy Doctor status is {policy_doctor_status}"})
    status = "ERROR" if any(item["severity"] == "ERROR" for item in findings) else "WARN" if findings else "OK"
    return {
        "status": status,
        "route_count": len(entries),
        "registry_targets_checked": sum(len(_target_commands(target) or ()) for _, target in entries),
        "findings": findings,
    }


def format_natural_doctor() -> str:
    report = natural_router_doctor()
    lines = [
        "Natural Command Router Doctor",
        f"Status: {report['status']}",
        f"Routes checked: {report['route_count']}",
        f"Registry/policy targets checked: {report['registry_targets_checked']}",
        "",
        "Findings:",
    ]
    if report["findings"]:
        lines.extend(f"- [{item['severity']}] {item['message']}" for item in report["findings"])
    else:
        lines.append("- [OK] All phrases and route targets are valid and allowlisted.")
    lines.extend(["", "Mutation policy:", "- Read-only diagnostics only; no routes or stores were changed."])
    return "\n".join(lines)


def _target_commands(target: object) -> tuple[str, ...] | None:
    if isinstance(target, str):
        return (target,)
    if isinstance(target, tuple) and all(isinstance(item, str) for item in target):
        return target
    return None


def _route_effect(target: str | tuple[str, ...]) -> str:
    commands = _target_commands(target) or ()
    return "explicit mutation" if any(command in EXPLICIT_MUTATION_TARGETS for command in commands) else "read-only"


def _format_target(target: str | tuple[str, ...]) -> str:
    return target if isinstance(target, str) else " | ".join(target)


def _target_group_name(target: str | tuple[str, ...]) -> str:
    for group_name, group_target in NATURAL_ROUTE_GROUPS:
        if target == group_target:
            return group_name
    return "known route"


def _target_policy(target: str | tuple[str, ...]) -> dict[str, Any]:
    from proto_mind.action_policy import classify_natural_route

    return classify_natural_route(target)


def _registry_specs_for_target(target: str | tuple[str, ...]) -> list[Any]:
    from proto_mind.command_registry import match_registered_command

    return [match_registered_command(command) for command in (_target_commands(target) or ())]


def _format_command_metadata(command: str) -> list[str]:
    from proto_mind.action_policy import classify_command
    from proto_mind.command_registry import match_registered_command

    spec = match_registered_command(command)
    decision = classify_command(command)
    if spec is None:
        return [f"- command: {command}", "  registry: missing", f"  policy: {decision.policy_class}"]
    return [
        f"- command: {command}",
        f"  category: {spec.category}",
        f"  read_only: {spec.read_only}",
        f"  mutates: {spec.mutates}",
        f"  risk: {spec.risk}",
        f"  policy: {decision.policy_class}",
    ]


def _strictest_member_policy(commands: tuple[str, ...]) -> str:
    from proto_mind.action_policy import POLICY_STRICTNESS, classify_command

    return max(
        (classify_command(command).policy_class for command in commands),
        key=lambda item: POLICY_STRICTNESS[item],
        default="blocked",
    )


def _dependency_doctor_statuses() -> tuple[str, str]:
    from proto_mind.action_policy import action_policy_doctor
    from proto_mind.command_registry import command_registry_doctor

    return command_registry_doctor()["status"], action_policy_doctor()["status"]


def _looks_like_shell_or_chain(command: str) -> bool:
    return not command.startswith("/") or any(token in command for token in ("\n", "\r", ";", "&&", "||", "`", "$(`"))


def _strip_phrase_quotes(phrase: str) -> str:
    if len(phrase) >= 2 and phrase[0] in {'"', "'", "“", "«"} and phrase[-1] in {'"', "'", "”", "»"}:
        return phrase[1:-1].strip()
    return phrase
