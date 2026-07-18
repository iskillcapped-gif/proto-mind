from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from proto_mind.command_registry import COMMAND_REGISTRY
from proto_mind.memory_store import MemoryStore
from proto_mind.session_rituals import SessionRituals, read_ledger_first_bullet, read_ledger_section_lead


MILESTONE_COMMANDS = (
    "/milestone status",
    "/milestone list",
    "/milestone current",
    "/milestone next",
    "/milestone doctor",
)
_DEPENDENCY_COMMANDS = (
    "/daily status",
    "/daily doctor",
    "/session start-brief",
    "/session handoff-brief",
    "/exports status",
    "/exports doctor",
    "/proto snapshot-status",
    "/proto snapshot-list",
    "/proto snapshot-diff-status",
    "/proto snapshot-diff-latest",
)


def format_milestone_command(command: str, *, project_root: Path, memory_store: MemoryStore) -> str | None:
    normalized = " ".join(command.strip().lower().split())
    if not normalized.startswith("/milestone"):
        return None
    tracker = MilestoneTracker(project_root=project_root, memory_store=memory_store)
    if normalized == "/milestone status":
        return tracker.format_status()
    if normalized == "/milestone list":
        return tracker.format_list()
    if normalized == "/milestone current":
        return tracker.format_current()
    if normalized == "/milestone next":
        return tracker.format_next()
    if normalized == "/milestone doctor":
        return tracker.format_doctor()
    return "Usage:\n" + "\n".join(f"  {item}" for item in MILESTONE_COMMANDS)


class MilestoneTracker:
    def __init__(self, *, project_root: Path, memory_store: MemoryStore) -> None:
        self.project_root = project_root
        self.memory_store = memory_store
        self.ledger_path = project_root / "PROTO_MIND_ARCHITECT_LEDGER.md"
        self.session = SessionRituals(project_root=project_root, memory_store=memory_store)

    @property
    def milestone_docs(self) -> list[Path]:
        return sorted(path for path in self.project_root.glob("MILESTONE_*.md") if path.is_file())

    def format_status(self) -> str:
        state = self.session.read_state()
        roadmap = self._roadmap()
        categories = Counter(spec.category for spec in COMMAND_REGISTRY)
        lines = [
            "Milestone Roadmap Status",
            f"project_root: {self.project_root}",
            f"command_registry: commands={len(COMMAND_REGISTRY)} categories={len(categories)}",
            f"current_milestone: {roadmap['current'] or 'not detected'}",
            f"inferred_phase: {self._inferred_phase(roadmap)}",
            f"accepted_milestones_detected: {len(roadmap['accepted'])}",
            f"milestone_docs: {len(self.milestone_docs)}",
            "",
            "Latest accepted milestones (ledger order):",
        ]
        lines.extend(f"- {item}" for item in roadmap["accepted"][-4:] or ["none detected"])
        lines.extend(
            [
                "",
                "Health signals:",
                f"- system: {state['system_status']}",
                f"- daily doctor: {state['daily_status']}",
                f"- export doctor: {state['export_status']}",
                f"- warning findings: {len(state['warnings'])}",
                "",
                "Suggested safe next manual action:",
                f"- {self._first_manual_action(state)}",
                "",
                "Mutation policy:",
                "- Read-only roadmap awareness only; no milestone state, store, export, context, or command was changed.",
            ]
        )
        return "\n".join(lines)

    def format_list(self) -> str:
        roadmap = self._roadmap()
        lines = [
            "Milestone List",
            f"ledger: {self.ledger_path}",
            f"ledger_readable: {roadmap['ledger_readable']}",
            f"accepted_milestones_detected: {len(roadmap['accepted'])}",
            "",
            "Accepted milestone records:",
        ]
        lines.extend(f"{index}. {item}" for index, item in enumerate(roadmap["accepted"], start=1))
        if not roadmap["accepted"]:
            lines.append("- none detected")
        lines.extend(["", "Milestone documents:"])
        lines.extend(f"- {path.name}" for path in self.milestone_docs or [])
        if not self.milestone_docs:
            lines.append("- none detected")
        lines.extend(
            [
                "",
                "Parsing note:",
                "- Partial deterministic parse of existing Architect Ledger bullets and local MILESTONE_*.md filenames only.",
                "- Missing milestones are not inferred or invented.",
                "",
                "Mutation policy:",
                "- Read-only listing; no roadmap or documentation file was modified.",
            ]
        )
        return "\n".join(lines)

    def format_current(self) -> str:
        roadmap = self._roadmap()
        available = {spec.prefix for spec in COMMAND_REGISTRY}
        groups = {
            "milestone": MILESTONE_COMMANDS,
            "daily": ("/daily status", "/daily brief", "/daily doctor", "/daily next"),
            "session_ritual": (
                "/session start-brief",
                "/session end-summary",
                "/session checkpoint-advice",
                "/session handoff-brief",
            ),
            "exports": ("/exports status", "/exports inventory", "/exports cleanup-preview", "/exports doctor"),
            "snapshot_diff": (
                "/proto snapshot-status",
                "/proto snapshot-list",
                "/proto snapshot-diff-status",
                "/proto snapshot-diff-latest",
            ),
        }
        lines = [
            "Current Milestone Detection",
            "Detected facts:",
            f"- ledger latest accepted milestone: {roadmap['current'] or 'unknown'}",
            f"- Architect Ledger readable: {'yes' if roadmap['ledger_readable'] else 'no'}",
            f"- milestone docs detected: {len(self.milestone_docs)}",
        ]
        for name, commands in groups.items():
            present = sum(1 for command in commands if command in available)
            lines.append(f"- {name} commands: {present}/{len(commands)}")
        lines.extend(
            [
                "",
                "Inferred current phase:",
                f"- {self._inferred_phase(roadmap)}",
                "- This phase label is inferred from local command availability and ledger text; it is not persisted state.",
                "",
                "Unknown / undetected:",
                "- milestone owner, planned completion date, and formal acceptance record are not structurally stored.",
                "",
                "Mutation policy:",
                "- Detection only; no milestone was accepted, advanced, or modified.",
            ]
        )
        return "\n".join(lines)

    def format_next(self) -> str:
        state = self.session.read_state()
        roadmap = self._roadmap()
        lines = [
            "Milestone Next",
            f"current_detected_milestone: {roadmap['current'] or 'unknown'}",
            f"system_status: {state['system_status']}",
            "",
            "Safe manual suggestions:",
        ]
        if state["warnings"]:
            for warning in state["warnings"][:2]:
                lines.append(f"- Inspect [{warning['category']}] with {warning['inspect_command']}: {warning['message']}")
        else:
            lines.append("- Review /proto warnings to confirm the baseline remains clean.")
        lines.extend(
            [
                "- Run scripts/run_tests.sh before accepting another milestone.",
                "- Review /proto snapshot-status and /proto snapshot-diff-latest; create exports only by explicit operator choice.",
                "- Review the v3.0a Runner MVP Design Lock. Any real v3.0 implementation requires a separate explicit task, clean tests, and operator acceptance; execution remains blocked.",
                "",
                "No automatic execution:",
                "- Suggestions were not run; no warning was repaired and no milestone, snapshot, context, store, or queue changed.",
            ]
        )
        return "\n".join(lines)

    def format_doctor(self) -> str:
        report = self.doctor_report()
        lines = ["Milestone Layer Doctor", f"Status: {report['status']}", "", "Checks:"]
        lines.extend(f"- [{item['severity']}] {item['message']}" for item in report["findings"])
        lines.extend(
            [
                "",
                "Mutation policy:",
                "- Read-only diagnostics only; no roadmap, cleanup, repair, checkpoint, export, or command execution occurred.",
            ]
        )
        return "\n".join(lines)

    def doctor_report(self) -> dict[str, Any]:
        findings: list[dict[str, str]] = []
        registry = {spec.prefix: spec for spec in COMMAND_REGISTRY}
        missing = [command for command in MILESTONE_COMMANDS if command not in registry]
        if missing:
            findings.append({"severity": "ERROR", "message": f"Milestone commands missing from Registry: {', '.join(missing)}"})
        else:
            findings.append({"severity": "OK", "message": "All milestone commands are registered."})
        unsafe = [
            command
            for command in MILESTONE_COMMANDS
            if command in registry and (not registry[command].read_only or registry[command].mutates != "none")
        ]
        if unsafe:
            findings.append({"severity": "ERROR", "message": f"Milestone commands expose mutation: {', '.join(unsafe)}"})
        else:
            findings.append({"severity": "OK", "message": "Milestone commands are read-only with mutates=none."})

        if self.ledger_path.is_file() and self._roadmap()["ledger_readable"]:
            findings.append({"severity": "OK", "message": "Architect Ledger is reachable and readable."})
        else:
            findings.append({"severity": "WARN", "message": "Architect Ledger is missing or unreadable; roadmap parsing is partial."})
        if self.milestone_docs:
            findings.append({"severity": "OK", "message": f"Milestone documents reachable: {len(self.milestone_docs)}."})
        else:
            findings.append({"severity": "WARN", "message": "No MILESTONE_*.md documents were detected."})

        unavailable = [command for command in _DEPENDENCY_COMMANDS if command not in registry]
        if unavailable:
            findings.append({"severity": "WARN", "message": f"Optional roadmap dependencies unavailable: {', '.join(unavailable)}"})
        else:
            findings.append({"severity": "OK", "message": "Daily, Session Ritual, Export, and Snapshot/Diff commands are reachable."})

        state = self.session.read_state()
        if state["context_state"] == "enabled":
            findings.append({"severity": "WARN", "message": "Context Injection is explicitly enabled; Milestone Layer did not change it."})
        else:
            findings.append({"severity": "OK", "message": "Context Injection is disabled."})
        if state["system_status"] != "OK":
            findings.append({"severity": "WARN", "message": f"Current read-only system health is {state['system_status']}; review /proto warnings."})

        dangerous = [
            spec.prefix
            for spec in COMMAND_REGISTRY
            if spec.category == "milestone" and (spec.risk == "high" or not spec.read_only or spec.mutates != "none")
        ]
        if dangerous:
            findings.append({"severity": "ERROR", "message": f"Dangerous milestone actions exposed: {', '.join(dangerous)}"})
        else:
            findings.append({"severity": "OK", "message": "No deletion, move, repair, cleanup, compression, or execution action is exposed."})

        status = "ERROR" if any(item["severity"] == "ERROR" for item in findings) else "WARN" if any(item["severity"] == "WARN" for item in findings) else "OK"
        return {"status": status, "findings": findings}

    def _roadmap(self) -> dict[str, Any]:
        try:
            text = self.ledger_path.read_text(encoding="utf-8")
        except OSError:
            return {"ledger_readable": False, "current": None, "accepted": [], "next_candidate": None}
        return {
            "ledger_readable": True,
            "current": read_ledger_section_lead(self.project_root, "Last Completed Milestone"),
            "accepted": _section_bullets(text, "Major Modules And Versions"),
            "next_candidate": read_ledger_first_bullet(self.project_root, "Next Candidate Tasks"),
        }

    def _inferred_phase(self, roadmap: dict[str, Any]) -> str:
        current = str(roadmap.get("current") or "")
        if "Operating Loop v2.2" in current:
            return "Operating Loop v2.2 roadmap-awareness phase"
        registry = {spec.prefix for spec in COMMAND_REGISTRY}
        if all(command in registry for command in MILESTONE_COMMANDS):
            return "Operating Loop roadmap-awareness phase"
        return "unknown"

    def _first_manual_action(self, state: dict[str, Any]) -> str:
        if state["warnings"]:
            return f"Inspect {state['warnings'][0]['inspect_command']} and /proto warnings."
        if state["daily_status"] != "OK":
            return "Inspect /daily doctor."
        if state["export_status"] != "OK":
            return "Inspect /exports doctor."
        return "Run scripts/run_tests.sh, review snapshots, and choose the next milestone explicitly."


def _section_bullets(text: str, section: str) -> list[str]:
    items: list[str] = []
    in_section = False
    for line in text.splitlines():
        if line.strip() == f"## {section}":
            in_section = True
            continue
        if in_section and line.startswith("## "):
            break
        if in_section and line.startswith("- "):
            items.append(line[2:].strip())
    return items
