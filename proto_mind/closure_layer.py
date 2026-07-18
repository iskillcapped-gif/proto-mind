from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from proto_mind.baseline_layer import SnapshotBaselineRegistry
from proto_mind.command_registry import COMMAND_REGISTRY
from proto_mind.daily_layer import _latest_line
from proto_mind.memory_store import MemoryStore
from proto_mind.milestone_layer import MilestoneTracker


CLOSURE_COMMANDS = (
    "/closure status",
    "/closure summary",
    "/closure next",
    "/closure handoff",
    "/closure doctor",
)
_DEPENDENCY_COMMANDS = (
    "/baseline status",
    "/baseline current",
    "/baseline latest",
    "/acceptance status",
    "/focus status",
    "/prechange status",
    "/agenda next",
    "/session end-summary",
    "/session handoff-brief",
    "/milestone next",
    "/warnings accepted",
    "/warnings unknown",
    "/exports doctor",
    "/proto snapshot-status",
    "/proto snapshot-diff-status",
)


def format_closure_command(command: str, *, project_root: Path, memory_store: MemoryStore) -> str | None:
    normalized = " ".join(command.strip().lower().split())
    if not normalized.startswith("/closure"):
        return None
    closure = PostAcceptanceClosure(project_root=project_root, memory_store=memory_store)
    if normalized == "/closure status":
        return closure.format_status()
    if normalized == "/closure summary":
        return closure.format_summary()
    if normalized == "/closure next":
        return closure.format_next()
    if normalized == "/closure handoff":
        return closure.format_handoff()
    if normalized == "/closure doctor":
        return closure.format_doctor()
    return "Usage:\n" + "\n".join(f"  {item}" for item in CLOSURE_COMMANDS)


class PostAcceptanceClosure:
    def __init__(self, *, project_root: Path, memory_store: MemoryStore) -> None:
        self.project_root = project_root
        self.memory_store = memory_store
        self.baseline = SnapshotBaselineRegistry(project_root=project_root, memory_store=memory_store)
        self.milestones = MilestoneTracker(project_root=project_root, memory_store=memory_store)

    def read_state(self) -> dict[str, Any]:
        baseline = self.baseline.read_state()
        if baseline["unknown"] or baseline["blocker_count"]:
            readiness = "BLOCKED"
        elif baseline["accepted"] or baseline["system_status"] != "OK" or baseline["context_state"] == "enabled":
            readiness = "WARN"
        else:
            readiness = "OK"
        handoff_safe = (
            not baseline["unknown"]
            and baseline["blocker_count"] == 0
            and baseline["context_state"] == "disabled"
            and baseline["baseline_review_safe"]
            and baseline["acceptance_review_safe"]
        )
        roadmap = self.milestones._roadmap()
        operating_layers = [
            item
            for item in roadmap["accepted"]
            if "Operating Loop" in item or "Baseline Registry" in item or "Acceptance Review" in item
        ]
        return {
            **baseline,
            "closure_readiness": readiness,
            "closure_handoff_safe": handoff_safe,
            "operating_layers": operating_layers,
        }

    def format_status(self) -> str:
        state = self.read_state()
        categories = Counter(spec.category for spec in COMMAND_REGISTRY)
        return "\n".join(
            [
                "Post-Acceptance Closure Status",
                f"Status: {state['closure_readiness']}",
                f"project_root: {self.project_root}",
                f"command_registry: commands={len(COMMAND_REGISTRY)} categories={len(categories)}",
                f"context_injection: {state['context_state']}",
                f"baseline_review: {state['baseline_readiness']}",
                f"acceptance_review: {state['acceptance_readiness']}",
                f"accepted_known_warnings: {len(state['accepted'])}",
                f"unknown_warnings: {len(state['unknown'])}",
                f"blockers: {state['blocker_count']}",
                f"latest_snapshot: {_latest_line(state['latest_snapshot'])}",
                f"latest_snapshot_diff: {_latest_line(state['latest_diff'])}",
                f"closure_handoff_safe: {str(state['closure_handoff_safe']).lower()}",
                "",
                "Closure boundary:",
                "- Status only; no session was closed, logged, persisted, exported, or advanced automatically.",
            ]
        )

    def format_summary(self) -> str:
        state = self.read_state()
        categories = Counter(spec.category for spec in COMMAND_REGISTRY)
        lines = [
            "Post-Acceptance Session Closure Summary",
            f"closure_readiness: {state['closure_readiness']}",
            "",
            "Current baseline facts:",
            f"- accepted baseline: {state['accepted_baseline'] or 'not detected'}",
            f"- registry: {len(COMMAND_REGISTRY)} commands across {len(categories)} categories",
            f"- tests: {state['test_baseline']}",
            f"- warnings: accepted={len(state['accepted'])}, unknown={len(state['unknown'])}, blockers={state['blocker_count']}",
            "",
            "Latest accepted operating layers:",
        ]
        lines.extend(f"- {item}" for item in state["operating_layers"][-5:] or ["not detected from local Ledger"])
        lines.extend(
            [
                "",
                "Snapshot / diff signals:",
                f"- snapshot: {_latest_line(state['latest_snapshot'])}",
                f"- diff: {_latest_line(state['latest_diff'])}",
                "",
                "Safety invariants:",
                f"- Context Injection disabled: {str(state['context_state'] == 'disabled').lower()}",
                f"- unknown warnings = 0: {str(not state['unknown']).lower()}",
                f"- blockers = 0: {str(state['blocker_count'] == 0).lower()}",
                "- For read-only runtime tasks, proto_mind/data and proto_mind/exports should remain unchanged.",
                "",
                "Recommended manual wrap-up:",
                "1. Review /baseline current.",
                "2. Review /session end-summary.",
                "3. Generate /closure handoff for the next session.",
                "4. Prepare the next Codex task only after its own Rule 0 backup/checkpoint.",
                "",
                "Mutation policy:",
                "- Live summary only; no closure state, log, file, snapshot, backup, export, or command was created or changed.",
            ]
        )
        return "\n".join(lines)

    def format_next(self) -> str:
        state = self.read_state()
        if state["unknown"]:
            priority = "P0"
            action = "Inspect unknown warnings before closing or planning another milestone."
            command = "/warnings unknown"
            reason = f"Unknown warning count is {len(state['unknown'])}."
        elif state["blocker_count"]:
            priority = "P0"
            action = "Resolve or explicitly review current blockers before session closure."
            command = "/acceptance status"
            reason = f"Blocker count is {state['blocker_count']}."
        elif state["closure_handoff_safe"]:
            priority = "P1"
            action = "Review /activation preconditions and /runner-mvp design before any separately scoped real runner task."
            command = "/runner-mvp design"
            reason = "Closure and MVP design-lock layers are safe; actual execution remains blocked."
        else:
            priority = "P1"
            action = "Review baseline and acceptance readiness before selecting the next milestone."
            command = "/baseline status"
            reason = "Closure handoff is not currently marked safe."
        return "\n".join(
            [
                "Post-Acceptance Next Manual Action",
                f"Status: {state['closure_readiness']}",
                f"priority: {priority}",
                f"action: {action}",
                f"reason: {reason}",
                f"manual_command: {command}",
                "",
                "Alternative future design tasks:",
                "- Snapshot Baseline Documentation v2.",
                "- Legacy Warning Migration Design v1 (read-only design only).",
                "",
                "No automatic execution:",
                "- No milestone, task, command, closure state, snapshot, context setting, or store was created or changed.",
            ]
        )

    def format_handoff(self) -> str:
        state = self.read_state()
        categories = Counter(spec.category for spec in COMMAND_REGISTRY)
        return "\n".join(
            [
                "Proto-Mind Post-Acceptance Handoff",
                f"Project: {self.project_root}",
                f"Current accepted baseline: {state['accepted_baseline'] or 'not detected'}",
                f"Registry: {len(COMMAND_REGISTRY)} commands across {len(categories)} categories",
                f"Tests: {state['test_baseline']}",
                f"Context Injection: {state['context_state']}",
                f"Warnings: accepted={len(state['accepted'])}, unknown={len(state['unknown'])}, blockers={state['blocker_count']}",
                f"Latest snapshot: {_latest_line(state['latest_snapshot'])}",
                f"Latest snapshot diff: {_latest_line(state['latest_diff'])}",
                "",
                "Operator command families:",
                "- /daily; /session; /milestone; /warnings; /agenda; /prechange; /focus",
                "- /acceptance; /baseline; /closure; /memory-card; /capabilities; /plan; /confirm; /exports; /proto snapshot-diff...",
                "",
                "Rule 0:",
                "- Before the next implementation task, run scripts/run_cli.sh and /memory backup first.",
                "",
                "Verification commands:",
                "- scripts/which_python.sh",
                "- scripts/run_tests.sh",
                "- /opt/homebrew/opt/python@3.11/bin/python3.11 -m compileall proto_mind",
                "",
                "Suggested next milestone:",
                "- Review /activation handoff and /runner-mvp handoff; a real v3.0 runner requires a separate explicit task and remains disabled.",
                "",
                "Handoff safety:",
                "- Copyable text only; no clipboard, file, external call, closure log/state, snapshot, backup, or command execution occurred.",
            ]
        )

    def format_doctor(self) -> str:
        report = self.doctor_report()
        lines = ["Post-Acceptance Closure Doctor", f"Status: {report['status']}", "", "Checks:"]
        lines.extend(f"- [{item['severity']}] {item['message']}" for item in report["findings"])
        lines.extend(
            [
                "",
                "Mutation policy:",
                "- Read-only diagnostics only; no closure state, command, file, snapshot, backup, repair, cleanup, migration, or external action occurred.",
            ]
        )
        return "\n".join(lines)

    def doctor_report(self) -> dict[str, Any]:
        findings: list[dict[str, str]] = []
        registry = {spec.prefix: spec for spec in COMMAND_REGISTRY}
        missing = [command for command in CLOSURE_COMMANDS if command not in registry]
        findings.append(
            {"severity": "ERROR", "message": f"Closure commands missing from Registry: {', '.join(missing)}"}
            if missing
            else {"severity": "OK", "message": "All closure commands are registered."}
        )
        unsafe = [
            command
            for command in CLOSURE_COMMANDS
            if command in registry and (not registry[command].read_only or registry[command].mutates != "none")
        ]
        findings.append(
            {"severity": "ERROR", "message": f"Closure commands expose mutation: {', '.join(unsafe)}"}
            if unsafe
            else {"severity": "OK", "message": "Closure commands are read-only with mutates=none."}
        )
        unavailable = [command for command in _DEPENDENCY_COMMANDS if command not in registry]
        findings.append(
            {"severity": "WARN", "message": f"Optional closure dependencies unavailable: {', '.join(unavailable)}"}
            if unavailable
            else {"severity": "OK", "message": "Baseline, Acceptance, Focus, Pre-Change, Agenda, Session, Milestone, Warning, Export, and Snapshot helpers are reachable."}
        )
        accepted_ledger = self.baseline.acceptance.focus.prechange.agenda.warning_inspector.accepted_ledger_path
        findings.append(
            {"severity": "OK", "message": "Accepted-known warnings ledger is reachable."}
            if accepted_ledger.is_file()
            else {"severity": "WARN", "message": "Accepted-known warnings ledger is missing."}
        )
        try:
            state = self.read_state()
        except Exception as exc:
            findings.append({"severity": "ERROR", "message": f"Closure readiness could not be computed: {exc}"})
        else:
            findings.append(
                {
                    "severity": "OK",
                    "message": f"Warning state is computable: accepted={len(state['accepted'])}, unknown={len(state['unknown'])}, blockers={state['blocker_count']}.",
                }
            )
            if state["unknown"] or state["blocker_count"]:
                findings.append({"severity": "BLOCKED", "message": "Unknown warnings or blockers prevent safe closure handoff."})
            if state["context_state"] == "enabled":
                findings.append({"severity": "WARN", "message": "Context Injection is explicitly enabled; Closure Layer did not change it."})
            else:
                findings.append({"severity": "OK", "message": "Context Injection is disabled."})
        dangerous = [
            spec.prefix
            for spec in COMMAND_REGISTRY
            if spec.category == "closure" and (spec.risk == "high" or not spec.read_only or spec.mutates != "none")
        ]
        findings.append(
            {"severity": "ERROR", "message": f"Dangerous closure actions exposed: {', '.join(dangerous)}"}
            if dangerous
            else {"severity": "OK", "message": "No execution, persistence, snapshot, backup, repair, cleanup, migration, deletion, move, compression, or external action is exposed."}
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
