from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from proto_mind.action_policy import POLICY_CLASSES, classify_command
from proto_mind.command_registry import COMMAND_REGISTRY, command_registry_doctor
from proto_mind.memory_card_layer import OperatorMemoryCard
from proto_mind.memory_store import MemoryStore


CAPABILITY_COMMANDS = (
    "/capabilities status",
    "/capabilities list",
    "/capabilities map",
    "/capabilities safety",
    "/capabilities doctor",
    "/capabilities handoff",
)
_DEPENDENCY_COMMANDS = (
    "/memory-card status",
    "/closure status",
    "/baseline status",
    "/acceptance status",
    "/focus status",
    "/prechange status",
    "/agenda next",
    "/session handoff-brief",
    "/milestone next",
    "/warnings accepted",
    "/warnings unknown",
    "/exports doctor",
    "/proto snapshot-diff-status",
)
_FAMILY_DESCRIPTIONS = {
    "daily": "/daily — daily operational status and deterministic next-step signals",
    "session": "/session — session start/end/checkpoint/handoff rituals and log inspection",
    "milestone": "/milestone — roadmap and milestone awareness",
    "warnings": "/warnings — warning inspection and accepted-known baseline",
    "agenda": "/agenda — live manual next-work queue",
    "prechange": "/prechange — pre-change readiness and safety gate",
    "focus": "/focus — focused manual session plan",
    "acceptance": "/acceptance — human review and acceptance decision framework",
    "baseline": "/baseline — accepted baseline awareness and snapshot signals",
    "closure": "/closure — post-acceptance handoff and session closure guidance",
    "memory-card": "/memory-card — compact project-state and Codex context cards",
    "exports": "/exports — export inventory, health, and cleanup preview",
}
_WORKFLOW_GROUPS = (
    (
        "Awareness",
        "Understand current health, roadmap, warnings, and accepted state.",
        ("/daily status", "/milestone current", "/warnings status", "/baseline current"),
        "Read-only inspection; do not treat status as authorization to mutate.",
    ),
    (
        "Pre-work",
        "Prepare one explicit, bounded operator work session.",
        ("/prechange status", "/focus plan", "/agenda next"),
        "Read-only planning; Rule 0 backup remains a separate explicit operator action.",
    ),
    (
        "Implementation support",
        "Transfer compact project context into a human-controlled implementation task.",
        ("/memory-card codex", "/plan dry-run", "/session handoff-brief"),
        "Context text only; no Codex task or command is launched.",
    ),
    (
        "Review",
        "Review evidence and existing baseline signals after implementation.",
        ("/acceptance criteria", "/baseline latest"),
        "Human decision only; no acceptance or snapshot is created.",
    ),
    (
        "Closure / handoff",
        "Close the manual workflow and prepare next-session continuity.",
        ("/closure summary", "/memory-card short", "/session end-summary"),
        "Live text only; no closure, card, or session state is persisted.",
    ),
    (
        "Maintenance",
        "Inspect exports and existing snapshot/diff artifacts.",
        ("/exports doctor", "/proto snapshot-diff-status"),
        "Inspection is read-only; export creation commands remain explicit mutations.",
    ),
)


def format_capability_command(command: str, *, project_root: Path, memory_store: MemoryStore) -> str | None:
    normalized = " ".join(command.strip().lower().split())
    if not normalized.startswith("/capabilities"):
        return None
    capability_map = CommandCapabilityMap(project_root=project_root, memory_store=memory_store)
    if normalized == "/capabilities status":
        return capability_map.format_status()
    if normalized == "/capabilities list":
        return capability_map.format_list()
    if normalized == "/capabilities map":
        return capability_map.format_map()
    if normalized == "/capabilities safety":
        return capability_map.format_safety()
    if normalized == "/capabilities doctor":
        return capability_map.format_doctor()
    if normalized == "/capabilities handoff":
        return capability_map.format_handoff()
    return "Usage:\n" + "\n".join(f"  {item}" for item in CAPABILITY_COMMANDS)


class CommandCapabilityMap:
    def __init__(self, *, project_root: Path, memory_store: MemoryStore) -> None:
        self.project_root = project_root
        self.memory_store = memory_store
        self.memory_card = OperatorMemoryCard(project_root=project_root, memory_store=memory_store)

    def read_state(self) -> dict[str, Any]:
        card = self.memory_card.read_state()
        if card["unknown"] or card["blocker_count"]:
            readiness = "BLOCKED"
        elif card["accepted"] or card["system_status"] != "OK" or card["context_state"] == "enabled":
            readiness = "WARN"
        else:
            readiness = "OK"
        generation_safe = (
            not card["unknown"]
            and card["blocker_count"] == 0
            and card["context_state"] == "disabled"
            and card["memory_card_generation_safe"]
        )
        categories = Counter(spec.category for spec in COMMAND_REGISTRY)
        return {
            **card,
            "capability_readiness": readiness,
            "capability_generation_safe": generation_safe,
            "category_counts": categories,
            "family_count": len(categories),
        }

    def format_status(self) -> str:
        state = self.read_state()
        return "\n".join(
            [
                "Command Family Index Status",
                f"Status: {state['capability_readiness']}",
                f"project_root: {self.project_root}",
                f"command_registry: commands={len(COMMAND_REGISTRY)} categories={state['family_count']}",
                f"context_injection: {state['context_state']}",
                f"accepted_known_warnings: {len(state['accepted'])}",
                f"unknown_warnings: {len(state['unknown'])}",
                f"blockers: {state['blocker_count']}",
                f"detected_command_families: {state['family_count']}",
                f"capability_map_generation_safe: {str(state['capability_generation_safe']).lower()}",
                "",
                "Index boundary:",
                "- Registry-derived documentation only; no command, capability state, file, prompt, or runtime record was created or changed.",
            ]
        )

    def format_list(self) -> str:
        by_category: dict[str, list[Any]] = {}
        for spec in COMMAND_REGISTRY:
            by_category.setdefault(spec.category, []).append(spec)
        lines = ["Command Family Index", "", "Core operator workflow families:"]
        for category, description in _FAMILY_DESCRIPTIONS.items():
            specs = by_category.get(category, [])
            lines.append(f"- {description} [{_family_mode(specs)}; commands={len(specs)}]")
        proto_diff = [spec for spec in COMMAND_REGISTRY if spec.prefix.startswith("/proto snapshot-diff")]
        lines.append(
            f"- /proto snapshot-diff — snapshot/diff status, comparison, and explicit exports [{_family_mode(proto_diff)}; commands={len(proto_diff)}]"
        )
        core_categories = set(_FAMILY_DESCRIPTIONS) | {"proto"}
        lines.extend(["", "Other registered Registry categories:"])
        for category in sorted(set(by_category) - core_categories):
            specs = by_category[category]
            example = min(specs, key=lambda item: item.prefix)
            lines.append(
                f"- /{category} [{_family_mode(specs)}; commands={len(specs)}] — Registry example: {example.prefix}: {example.description}"
            )
        lines.extend(
            [
                "",
                "Classification note:",
                "- Modes come from current Command Registry metadata; mixed families include at least one mutating command.",
                "- Undocumented or unregistered behavior is UNKNOWN, not SAFE.",
                "",
                "No command executed.",
            ]
        )
        return "\n".join(lines)

    def format_map(self) -> str:
        lines = ["Proto-Mind Workflow Capability Map"]
        for phase, purpose, commands, safety in _WORKFLOW_GROUPS:
            lines.extend(
                [
                    "",
                    f"{phase}:",
                    f"- purpose: {purpose}",
                    f"- useful commands: {', '.join(commands)}",
                    f"- safety: {safety}",
                    "- runtime mode: read-only for the listed commands",
                ]
            )
        lines.extend(
            [
                "",
                "Workflow:",
                "- awareness → prechange → focus → dry-run plan → human-controlled Codex work → acceptance → baseline → closure / memory-card",
                "",
                "No automatic execution:",
                "- The map did not run any listed command or advance workflow state.",
            ]
        )
        return "\n".join(lines)

    def format_safety(self) -> str:
        specs = list(COMMAND_REGISTRY)
        read_only = [spec for spec in specs if spec.read_only and spec.mutates == "none"]
        mutating = [spec for spec in specs if not spec.read_only or spec.mutates != "none"]
        high_risk = [spec for spec in specs if spec.risk == "high"]
        policy_counts = Counter(classify_command(spec.prefix, specs).policy_class for spec in specs)
        confirmation = [spec for spec in specs if classify_command(spec.prefix, specs).policy_class == "confirmation_required"]
        operator_only = [spec for spec in specs if classify_command(spec.prefix, specs).policy_class == "operator_only"]
        lines = [
            "Command Capability Safety Classification",
            "",
            "Read-only operator layers:",
            f"- registered read-only/mutates=none commands: {len(read_only)}",
            "- workflow families: /daily, /session rituals, /milestone, /warnings, /agenda, /prechange, /focus, /acceptance, /baseline, /closure, /memory-card, /capabilities, /plan, /exports inspection",
            "",
            "Docs / test implementation boundary:",
            "- Source, tests, and docs may change only inside an explicit checkpointed Codex task; no capability slash command performs implementation.",
            "",
            "Potentially mutating or dangerous commands:",
            f"- mutating Registry commands: {len(mutating)}",
            f"- high-risk Registry commands: {len(high_risk)}",
            f"- examples: {', '.join(spec.prefix for spec in mutating[:8]) or 'none'}",
            "",
            "Action Policy classes:",
        ]
        lines.extend(f"- {name}: {policy_counts.get(name, 0)}" for name in POLICY_CLASSES)
        lines.extend(
            [
                f"- confirmation-required examples: {', '.join(spec.prefix for spec in confirmation[:8]) or 'none'}",
                f"- operator-only examples: {', '.join(spec.prefix for spec in operator_only[:8]) or 'none'}",
                "- Unknown/unregistered commands: UNKNOWN capability and blocked by advisory policy; never classified SAFE.",
                "",
                "Recommended gates before future execution features:",
                "1. Rule 0 backup/checkpoint.",
                "2. /prechange status",
                "3. /warnings unknown",
                "4. /acceptance criteria",
                "5. /baseline current",
                "6. /confirm policy and /confirm levels",
                "7. /sandbox blueprint and /sandbox boundaries",
                "8. /runner contract and /runner disabled",
                "9. /runner-candidates list and /runner-candidates gates",
                "10. /activation preconditions and /activation blockers",
                "11. /runner-mvp design and /runner-mvp stop-conditions",
                "",
                "Safety boundary:",
                "- Classification is advisory only; this command executes nothing and grants no authorization.",
            ]
        )
        return "\n".join(lines)

    def format_doctor(self) -> str:
        report = self.doctor_report()
        lines = ["Command Capability Map Doctor", f"Status: {report['status']}", "", "Checks:"]
        lines.extend(f"- [{item['severity']}] {item['message']}" for item in report["findings"])
        lines.extend(
            [
                "",
                "Mutation policy:",
                "- Read-only diagnostics only; no command, map state, clipboard, file, snapshot, backup, repair, cleanup, migration, or external action occurred.",
            ]
        )
        return "\n".join(lines)

    def doctor_report(self) -> dict[str, Any]:
        findings: list[dict[str, str]] = []
        registry = {spec.prefix: spec for spec in COMMAND_REGISTRY}
        missing = [command for command in CAPABILITY_COMMANDS if command not in registry]
        findings.append(
            {"severity": "ERROR", "message": f"Capability commands missing from Registry: {', '.join(missing)}"}
            if missing
            else {"severity": "OK", "message": "All capability commands are registered."}
        )
        unsafe = [
            command
            for command in CAPABILITY_COMMANDS
            if command in registry and (not registry[command].read_only or registry[command].mutates != "none")
        ]
        findings.append(
            {"severity": "ERROR", "message": f"Capability commands expose mutation: {', '.join(unsafe)}"}
            if unsafe
            else {"severity": "OK", "message": "Capability commands are read-only with mutates=none."}
        )
        registry_health = command_registry_doctor()
        findings.append(
            {"severity": "OK", "message": "Command Registry is reachable and healthy."}
            if registry_health["status"] == "OK"
            else {"severity": "ERROR", "message": f"Command Registry Doctor status is {registry_health['status']}."}
        )
        unavailable = [command for command in _DEPENDENCY_COMMANDS if command not in registry]
        findings.append(
            {"severity": "WARN", "message": f"Optional capability dependencies unavailable: {', '.join(unavailable)}"}
            if unavailable
            else {"severity": "OK", "message": "Memory Card, Closure, Baseline, Acceptance, Focus, Pre-Change, Agenda, Session, Milestone, Warning, Export, and Snapshot helpers are reachable."}
        )
        try:
            state = self.read_state()
        except Exception as exc:
            findings.append({"severity": "ERROR", "message": f"Capability readiness could not be computed: {exc}"})
        else:
            findings.append(
                {
                    "severity": "OK",
                    "message": f"Warning state is computable: accepted={len(state['accepted'])}, unknown={len(state['unknown'])}, blockers={state['blocker_count']}; families={state['family_count']}.",
                }
            )
            if state["unknown"] or state["blocker_count"]:
                findings.append({"severity": "BLOCKED", "message": "Unknown warnings or blockers prevent safe capability-map handoff."})
            if state["context_state"] == "enabled":
                findings.append({"severity": "WARN", "message": "Context Injection is explicitly enabled; Capability Map did not change it."})
            else:
                findings.append({"severity": "OK", "message": "Context Injection is disabled."})
        dangerous = [
            spec.prefix
            for spec in COMMAND_REGISTRY
            if spec.category == "capabilities" and (spec.risk == "high" or not spec.read_only or spec.mutates != "none")
        ]
        findings.append(
            {"severity": "ERROR", "message": f"Dangerous capability actions exposed: {', '.join(dangerous)}"}
            if dangerous
            else {"severity": "OK", "message": "No execution, persistence, clipboard, snapshot, backup, repair, cleanup, migration, deletion, move, compression, or external action is exposed."}
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
        return "\n".join(
            [
                "Proto-Mind Capability Handoff",
                f"Project: {self.project_root}",
                f"Registry: {len(COMMAND_REGISTRY)} commands across {state['family_count']} categories/families",
                "Key families: /daily, /session, /milestone, /warnings, /agenda, /prechange, /focus, /acceptance, /baseline, /closure, /memory-card, /capabilities, /plan, /exports, /proto snapshot-diff",
                f"Warnings: accepted={len(state['accepted'])}, unknown={len(state['unknown'])}, blockers={state['blocker_count']}",
                f"Context Injection: {state['context_state']}",
                "",
                "Safety gates:",
                "- Rule 0 backup/checkpoint; /prechange status; /warnings unknown; /acceptance criteria; /baseline current",
                "",
                "Recommended manual workflow:",
                "- prechange → focus → dry-run plan → human-controlled Codex task → acceptance → baseline → closure / memory-card",
                "",
                "Next milestone:",
                "- Use /activation handoff and /runner-mvp handoff before any separately scoped real runner task; activation remains disabled.",
                "",
                "Handoff safety:",
                "- Copyable text only; no clipboard, command, model, file, capability state, snapshot, backup, or external call occurred.",
            ]
        )


def _family_mode(specs: list[Any]) -> str:
    if not specs:
        return "UNKNOWN"
    if all(spec.read_only and spec.mutates == "none" for spec in specs):
        return "read-only"
    return "mixed / potentially mutating"
