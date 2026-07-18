from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from proto_mind.closure_layer import PostAcceptanceClosure
from proto_mind.command_registry import COMMAND_REGISTRY
from proto_mind.daily_layer import _latest_line
from proto_mind.identity import IdentityStore
from proto_mind.memory_store import MemoryStore


MEMORY_CARD_COMMANDS = (
    "/memory-card status",
    "/memory-card short",
    "/memory-card full",
    "/memory-card codex",
    "/memory-card doctor",
)
_DEPENDENCY_COMMANDS = (
    "/closure status",
    "/closure handoff",
    "/baseline status",
    "/baseline current",
    "/acceptance status",
    "/focus status",
    "/prechange status",
    "/agenda next",
    "/session handoff-brief",
    "/milestone next",
    "/warnings accepted",
    "/warnings unknown",
    "/exports doctor",
    "/proto snapshot-status",
    "/proto snapshot-diff-status",
)


def format_memory_card_command(command: str, *, project_root: Path, memory_store: MemoryStore) -> str | None:
    normalized = " ".join(command.strip().lower().split())
    if not normalized.startswith("/memory-card"):
        return None
    card = OperatorMemoryCard(project_root=project_root, memory_store=memory_store)
    if normalized == "/memory-card status":
        return card.format_status()
    if normalized == "/memory-card short":
        return card.format_short()
    if normalized == "/memory-card full":
        return card.format_full()
    if normalized == "/memory-card codex":
        return card.format_codex()
    if normalized == "/memory-card doctor":
        return card.format_doctor()
    return "Usage:\n" + "\n".join(f"  {item}" for item in MEMORY_CARD_COMMANDS)


class OperatorMemoryCard:
    def __init__(self, *, project_root: Path, memory_store: MemoryStore) -> None:
        self.project_root = project_root
        self.memory_store = memory_store
        self.closure = PostAcceptanceClosure(project_root=project_root, memory_store=memory_store)
        self.identity = IdentityStore.from_project_root(project_root)

    def read_state(self) -> dict[str, Any]:
        closure = self.closure.read_state()
        identity = self.identity.read_summary()
        if closure["unknown"] or closure["blocker_count"]:
            readiness = "BLOCKED"
        elif closure["accepted"] or closure["system_status"] != "OK" or closure["context_state"] == "enabled":
            readiness = "WARN"
        else:
            readiness = "OK"
        generation_safe = (
            not closure["unknown"]
            and closure["blocker_count"] == 0
            and closure["context_state"] == "disabled"
            and closure["closure_handoff_safe"]
            and identity.get("status") != "ERROR"
        )
        return {
            **closure,
            "memory_card_readiness": readiness,
            "memory_card_generation_safe": generation_safe,
            "identity": identity,
        }

    def _next_action(self, state: dict[str, Any]) -> tuple[str, str]:
        if state["unknown"]:
            return "Inspect unknown warnings before preparing new-session context.", "/warnings unknown"
        if state["blocker_count"]:
            return "Review current blockers before preparing another milestone.", "/acceptance status"
        if not state["memory_card_generation_safe"]:
            return "Review closure and baseline readiness before using the card.", "/closure status"
        return "Review /activation preconditions and /runner-mvp design; any real runner implementation requires a separate explicit task.", "/runner-mvp design"

    def format_status(self) -> str:
        state = self.read_state()
        categories = Counter(spec.category for spec in COMMAND_REGISTRY)
        return "\n".join(
            [
                "Operator Memory Card Status",
                f"Status: {state['memory_card_readiness']}",
                f"project_root: {self.project_root}",
                f"command_registry: commands={len(COMMAND_REGISTRY)} categories={len(categories)}",
                f"context_injection: {state['context_state']}",
                f"closure_readiness: {state['closure_readiness']}",
                f"baseline_readiness: {state['baseline_readiness']}",
                f"acceptance_readiness: {state['acceptance_readiness']}",
                f"accepted_known_warnings: {len(state['accepted'])}",
                f"unknown_warnings: {len(state['unknown'])}",
                f"blockers: {state['blocker_count']}",
                f"latest_snapshot: {_latest_line(state['latest_snapshot'])}",
                f"latest_snapshot_diff: {_latest_line(state['latest_diff'])}",
                f"memory_card_generation_safe: {str(state['memory_card_generation_safe']).lower()}",
                "",
                "Card boundary:",
                "- Generated text only; no memory-card state, file, clipboard, prompt, or runtime record was created or changed.",
            ]
        )

    def format_short(self) -> str:
        state = self.read_state()
        categories = Counter(spec.category for spec in COMMAND_REGISTRY)
        action, command = self._next_action(state)
        identity = state["identity"]
        return "\n".join(
            [
                "Proto-Mind Operator Memory Card (Short)",
                f"Project: {self.project_root}",
                f"Identity: {identity.get('name') or 'Proto-Mind'} — {identity.get('role') or 'local-first cognitive assistant'}",
                f"Accepted baseline: {state['accepted_baseline'] or 'not detected'}",
                f"Registry: {len(COMMAND_REGISTRY)} commands / {len(categories)} categories",
                f"Tests: {state['test_baseline']}",
                f"Context Injection: {state['context_state']}",
                f"Readiness: card={state['memory_card_readiness']}, closure={state['closure_readiness']}, baseline={state['baseline_readiness']}, acceptance={state['acceptance_readiness']}",
                f"Warnings: accepted={len(state['accepted'])}, unknown={len(state['unknown'])}, blockers={state['blocker_count']}",
                f"Snapshot: {_latest_line(state['latest_snapshot'])}",
                f"Diff: {_latest_line(state['latest_diff'])}",
                "Operating phase: post-acceptance continuity / next-milestone selection",
                f"Next: {action}",
                f"Manual command: {command}",
                "Rule 0: before any future change, run scripts/run_cli.sh and /memory backup.",
                "Safety: informational card only; no command executed and no state persisted.",
            ]
        )

    def format_full(self) -> str:
        state = self.read_state()
        categories = Counter(spec.category for spec in COMMAND_REGISTRY)
        action, command = self._next_action(state)
        identity = state["identity"]
        lines = [
            "Proto-Mind Operator Memory Card (Full)",
            "",
            "Project identity:",
            f"- path: {self.project_root}",
            f"- name: {identity.get('name') or 'unknown'}",
            f"- role: {identity.get('role') or 'unknown'}",
            "",
            "Current baseline:",
            f"- accepted milestone: {state['accepted_baseline'] or 'not detected'}",
            f"- Registry: {len(COMMAND_REGISTRY)} commands across {len(categories)} categories",
            f"- tests: {state['test_baseline']}",
            f"- readiness: card={state['memory_card_readiness']}, closure={state['closure_readiness']}, baseline={state['baseline_readiness']}, acceptance={state['acceptance_readiness']}",
            "",
            "Accepted operating-loop layers:",
        ]
        lines.extend(f"- {item}" for item in state["operating_layers"][-7:] or ["not detected from local Ledger"])
        lines.extend(
            [
                "",
                "Available command families:",
                "- /daily, /session, /milestone, /warnings, /agenda, /prechange, /focus",
                "- /acceptance, /baseline, /closure, /memory-card, /capabilities, /plan, /exports, /proto snapshot-diff...",
                "",
                "Safety invariants:",
                f"- Context Injection disabled: {str(state['context_state'] == 'disabled').lower()}",
                f"- unknown warnings = 0: {str(not state['unknown']).lower()}",
                f"- blockers = 0: {str(state['blocker_count'] == 0).lower()}",
                "- Read-only runtime tasks must not change proto_mind/data or proto_mind/exports.",
                "- No autonomous execution, hidden mutation, cleanup, migration, snapshot, or backup creation.",
                "",
                "Warning baseline:",
                f"- accepted-known: {len(state['accepted'])}",
                f"- unknown: {len(state['unknown'])}",
                f"- blockers: {state['blocker_count']}",
                "",
                "Snapshot / diff:",
                f"- snapshot: {_latest_line(state['latest_snapshot'])}",
                f"- diff: {_latest_line(state['latest_diff'])}",
                "",
                "Verification commands:",
                "- scripts/which_python.sh",
                "- scripts/run_tests.sh",
                "- /opt/homebrew/opt/python@3.11/bin/python3.11 -m compileall proto_mind",
                "",
                "Current limitations:",
                "- Deterministic local card only; no persistent card, LLM summary, relevance ranking, clipboard, or automatic prompt injection.",
                "- Test baseline and accepted milestone are documentation-derived and may be stale until docs are updated explicitly.",
                "- Accepted legacy warnings remain visible and are not repaired or suppressed.",
                "",
                "Suggested next manual action:",
                f"- {action}",
                f"- command: {command}",
                "",
                "Mutation policy:",
                "- Printed only; no card, memory, store, export, context setting, session log, or command was created or changed.",
            ]
        )
        return "\n".join(lines)

    def format_codex(self) -> str:
        state = self.read_state()
        categories = Counter(spec.category for spec in COMMAND_REGISTRY)
        return "\n".join(
            [
                "Proto-Mind Codex Context Header",
                f"Project: {self.project_root}",
                "Rule 0: before changes run scripts/run_cli.sh, then /memory backup.",
                f"Current baseline: {state['accepted_baseline'] or 'not detected'}",
                f"Registry/tests: {len(COMMAND_REGISTRY)} commands, {len(categories)} categories; {state['test_baseline']}",
                f"Warnings: accepted={len(state['accepted'])}, unknown={len(state['unknown'])}, blockers={state['blocker_count']}",
                f"Context Injection: {state['context_state']} (must remain disabled unless explicitly authorized).",
                "Safety: deterministic/local; no autonomous execution, background task, LLM/API call, auto-apply, repair, cleanup, migration, deletion, move, compression, snapshot, or hidden mutation.",
                "Authorization vocabulary: review /confirm policy and /confirm levels; these grant no runtime authorization.",
                "Runner blueprint: review /sandbox blueprint and /sandbox boundaries; all entries are design-only and non-executable.",
                "No-op contract: review /runner contract and /runner disabled; execution_enabled=false and executed=false.",
                "Candidate set: review /runner-candidates list and gates; FUTURE_CANDIDATE means NOT_ACTIVE and not executable.",
                "Activation boundary: review /activation preconditions and blockers; design readiness never activates execution.",
                "MVP design lock: review /runner-mvp design and stop-conditions; proposed allowlist entries remain inactive.",
                "Read-only runtime task boundary: do not write proto_mind/data/* or proto_mind/exports/*; compare SHA-256 against Rule 0.",
                "Verification: scripts/which_python.sh; scripts/run_tests.sh; /opt/homebrew/opt/python@3.11/bin/python3.11 -m compileall proto_mind.",
                "Final report: backup path; files changed; commands/behavior; Registry counts; tests/compileall; manual smoke; safety; Context Injection; data/exports SHA-256; limitations/warnings.",
                "Reminder: this header is context, not authorization to execute commands or expand scope.",
            ]
        )

    def format_doctor(self) -> str:
        report = self.doctor_report()
        lines = ["Operator Memory Card Doctor", f"Status: {report['status']}", "", "Checks:"]
        lines.extend(f"- [{item['severity']}] {item['message']}" for item in report["findings"])
        lines.extend(
            [
                "",
                "Mutation policy:",
                "- Read-only diagnostics only; no card, clipboard, command, file, snapshot, backup, repair, cleanup, migration, or external action occurred.",
            ]
        )
        return "\n".join(lines)

    def doctor_report(self) -> dict[str, Any]:
        findings: list[dict[str, str]] = []
        registry = {spec.prefix: spec for spec in COMMAND_REGISTRY}
        missing = [command for command in MEMORY_CARD_COMMANDS if command not in registry]
        findings.append(
            {"severity": "ERROR", "message": f"Memory-card commands missing from Registry: {', '.join(missing)}"}
            if missing
            else {"severity": "OK", "message": "All memory-card commands are registered."}
        )
        unsafe = [
            command
            for command in MEMORY_CARD_COMMANDS
            if command in registry and (not registry[command].read_only or registry[command].mutates != "none")
        ]
        findings.append(
            {"severity": "ERROR", "message": f"Memory-card commands expose mutation: {', '.join(unsafe)}"}
            if unsafe
            else {"severity": "OK", "message": "Memory-card commands are read-only with mutates=none."}
        )
        unavailable = [command for command in _DEPENDENCY_COMMANDS if command not in registry]
        findings.append(
            {"severity": "WARN", "message": f"Optional memory-card dependencies unavailable: {', '.join(unavailable)}"}
            if unavailable
            else {"severity": "OK", "message": "Closure, Baseline, Acceptance, Focus, Pre-Change, Agenda, Session, Milestone, Warning, Export, and Snapshot helpers are reachable."}
        )
        accepted_ledger = self.closure.baseline.acceptance.focus.prechange.agenda.warning_inspector.accepted_ledger_path
        findings.append(
            {"severity": "OK", "message": "Accepted-known warnings ledger is reachable."}
            if accepted_ledger.is_file()
            else {"severity": "WARN", "message": "Accepted-known warnings ledger is missing."}
        )
        try:
            state = self.read_state()
        except Exception as exc:
            findings.append({"severity": "ERROR", "message": f"Memory-card readiness could not be computed: {exc}"})
        else:
            findings.append(
                {
                    "severity": "OK",
                    "message": f"Warning state is computable: accepted={len(state['accepted'])}, unknown={len(state['unknown'])}, blockers={state['blocker_count']}.",
                }
            )
            if state["unknown"] or state["blocker_count"]:
                findings.append({"severity": "BLOCKED", "message": "Unknown warnings or blockers prevent safe memory-card generation."})
            if state["context_state"] == "enabled":
                findings.append({"severity": "WARN", "message": "Context Injection is explicitly enabled; Memory Card Layer did not change it."})
            else:
                findings.append({"severity": "OK", "message": "Context Injection is disabled."})
        dangerous = [
            spec.prefix
            for spec in COMMAND_REGISTRY
            if spec.category == "memory-card" and (spec.risk == "high" or not spec.read_only or spec.mutates != "none")
        ]
        findings.append(
            {"severity": "ERROR", "message": f"Dangerous memory-card actions exposed: {', '.join(dangerous)}"}
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
