from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from proto_mind.experiment_journal import ExperimentJournal
from proto_mind.goal_stack import GoalStack
from proto_mind.identity import IdentityStore
from proto_mind.reflection_journal import ReflectionJournal
from proto_mind.skill_library import SkillLibrary
from proto_mind.task_queue import PRIORITY_RANK, TaskQueue
from proto_mind.world_model import WorldModelLite


def format_loop_command(command: str, *, project_root: Path) -> str | None:
    normalized = " ".join(command.strip().lower().split())
    if not normalized.startswith("/loop"):
        return None

    loop = OperatingLoop.from_project_root(project_root)
    if normalized == "/loop status":
        return loop.format_status()
    if normalized == "/loop morning":
        return loop.format_morning()
    if normalized == "/loop morning-plan":
        return loop.format_morning_plan()
    if normalized == "/loop evening":
        return loop.format_evening()
    if normalized == "/loop evening-review":
        return loop.format_evening_review()
    if normalized == "/loop capture-today":
        return loop.format_capture_today()
    if normalized == "/loop next":
        return loop.format_next()
    if normalized == "/loop doctor":
        return loop.format_doctor()
    return (
        "Usage:\n"
        "  /loop status\n"
        "  /loop morning\n"
        "  /loop morning-plan\n"
        "  /loop evening\n"
        "  /loop evening-review\n"
        "  /loop capture-today\n"
        "  /loop next\n"
        "  /loop doctor"
    )


class OperatingLoop:
    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root

    @classmethod
    def from_project_root(cls, project_root: Path) -> "OperatingLoop":
        return cls(project_root)

    def snapshot(self) -> dict[str, Any]:
        goals_state = GoalStack.from_project_root(self.project_root)._read_state()
        tasks_state = TaskQueue.from_project_root(self.project_root)._read_state()
        experiments_state = ExperimentJournal.from_project_root(self.project_root)._read_state()
        world_state = WorldModelLite.from_project_root(self.project_root)._read_state()
        skills_state = SkillLibrary.from_project_root(self.project_root)._read_state()
        reflection_journal = ReflectionJournal.from_project_root(self.project_root)
        reflection_records, reflection_malformed = reflection_journal.read_records()
        memory = _read_explicit_memory_counts(self.project_root)
        identity = IdentityStore.from_project_root(self.project_root).read_summary()
        return {
            "goals_state": goals_state,
            "tasks_state": tasks_state,
            "experiments_state": experiments_state,
            "world_state": world_state,
            "skills_state": skills_state,
            "reflections": reflection_records,
            "reflection_malformed": reflection_malformed,
            "memory": memory,
            "identity": identity,
            "focused_goals": [goal for goal in goals_state.records if goal.get("focus")],
            "active_goals": [goal for goal in goals_state.records if goal.get("status") == "active"],
            "open_tasks": [task for task in tasks_state.records if task.get("status") in {"open", "in_progress", "blocked"}],
            "open_experiments": [exp for exp in experiments_state.records if exp.get("status") in {"open", "running"}],
            "open_world": [record for record in world_state.records if record.get("status") in {"open", "observed"}],
            "active_skills": [skill for skill in skills_state.records if skill.get("status") == "active"],
        }

    def format_status(self) -> str:
        snap = self.snapshot()
        status = _overall_status(snap)
        focused = _first(snap["focused_goals"])
        next_task = _best_next_task(snap["tasks_state"].records, focused_goal_id=focused.get("id") if focused else None)
        latest_reflection = _latest(snap["reflections"], "created_at")
        recent_skill = _latest(snap["active_skills"], "last_used_at") or _latest(snap["active_skills"], "updated_at")
        memory = snap["memory"]
        lines = [
            "Operating Loop Status",
            f"Status: {status}",
            "",
            "Focus:",
            f"- focused goal: {_goal_line(focused) if focused else 'none'}",
            "",
            "Next:",
            f"- next task: {_task_line(next_task) if next_task else 'none'}",
            "",
            "Open Work:",
            f"- active/open goals count: {len(snap['active_goals'])}",
            f"- open/in_progress/blocked tasks count: {len(snap['open_tasks'])}",
            f"- open/running experiments count: {len(snap['open_experiments'])}",
            f"- open/observed world predictions count: {len(snap['open_world'])}",
            "",
            "Memory:",
            f"- active explicit memories: {memory['active_explicit']}",
            f"- forgotten explicit memories: {memory['forgotten_explicit']}",
            f"- memory status: {memory['status']}",
            "",
            "Identity:",
            f"- name: {snap['identity']['name']}",
            f"- role: {snap['identity']['role']}",
            f"- active values: {snap['identity']['active_values']}",
            f"- active boundaries: {snap['identity']['active_boundaries']}",
            "",
            "Reflection:",
            f"- reflection journal count: {len(snap['reflections'])}",
            f"- latest reflection: {_reflection_line(latest_reflection) if latest_reflection else 'none'}",
            "",
            "Skills:",
            f"- active skills count: {len(snap['active_skills'])}",
            f"- top/recently used skill: {_skill_line(recent_skill) if recent_skill else 'none'}",
            "",
            "Recommendations:",
        ]
        lines.extend(_format_bullets(_recommendations(snap)))
        return "\n".join(lines)

    def format_morning(self) -> str:
        snap = self.snapshot()
        focused = _first(snap["focused_goals"])
        next_task = _best_next_task(snap["tasks_state"].records, focused_goal_id=focused.get("id") if focused else None)
        open_tasks = sorted(snap["open_tasks"], key=_task_sort_key)[:3]
        open_experiments = sorted(snap["open_experiments"], key=lambda item: str(item.get("created_at", "")), reverse=True)[:3]
        open_world = sorted(snap["open_world"], key=lambda item: str(item.get("created_at", "")), reverse=True)[:3]
        latest_reflection = _latest(snap["reflections"], "created_at")
        action = _next_action(snap)
        lines = [
            "Operating Loop Morning",
            f"Status: {_overall_status(snap)}",
            "",
            f"Focused goal: {_goal_line(focused) if focused else 'none'}",
            f"Identity: {snap['identity']['name']} — {snap['identity']['role']} (values={snap['identity']['active_values']}, boundaries={snap['identity']['active_boundaries']})",
            f"Next task: {_task_line(next_task) if next_task else 'none'}",
            "",
            "Top open tasks:",
        ]
        lines.extend(_format_bullets([_task_line(task) for task in open_tasks]))
        lines.append("Open experiments:")
        lines.extend(_format_bullets([_experiment_line(exp) for exp in open_experiments]))
        lines.append("Open world predictions:")
        lines.extend(_format_bullets([_world_line(record) for record in open_world]))
        lines.append(f"Latest reflection: {_reflection_line(latest_reflection) if latest_reflection else 'none'}")
        lines.append("")
        lines.append("Recommended first action:")
        lines.append(f"- {action['summary']}")
        lines.append(f"- suggested command: {action['command']}")
        return "\n".join(lines)

    def format_morning_plan(self) -> str:
        snap = self.snapshot()
        focused = _first(snap["focused_goals"])
        next_task = _best_next_task(snap["tasks_state"].records, focused_goal_id=focused.get("id") if focused else None)
        open_tasks = sorted(snap["open_tasks"], key=_task_sort_key)[:5]
        open_experiments = sorted(snap["open_experiments"], key=lambda item: str(item.get("updated_at") or item.get("created_at") or ""), reverse=True)[:5]
        open_world = sorted(snap["open_world"], key=lambda item: str(item.get("updated_at") or item.get("created_at") or ""), reverse=True)[:5]
        recent_reflections = sorted(snap["reflections"], key=lambda item: str(item.get("created_at", "")), reverse=True)[:3]
        action = _next_action(snap)
        lines = [
            "Operating Loop Morning Plan",
            f"Status: {_overall_status(snap)}",
            "",
            "Identity:",
            f"- name: {snap['identity']['name']}",
            f"- role: {snap['identity']['role']}",
            f"- values: {snap['identity']['active_values']}",
            f"- boundaries: {snap['identity']['active_boundaries']}",
            "",
            "Focus:",
            f"- focused goal: {_goal_line(focused) if focused else 'none'}",
            f"- next task: {_task_line(next_task) if next_task else 'none'}",
            "",
            "Top open tasks:",
        ]
        lines.extend(_format_bullets([_task_line(task) for task in open_tasks]))
        lines.append("Open experiments:")
        lines.extend(_format_bullets([_experiment_line(exp) for exp in open_experiments]))
        lines.append("Open world predictions:")
        lines.extend(_format_bullets([_world_line(record) for record in open_world]))
        lines.append("Recent reflections:")
        lines.extend(_format_bullets([_reflection_line(reflection) for reflection in recent_reflections]))
        lines.append("")
        lines.append("Suggested first action:")
        lines.append(f"- {action['summary']}")
        lines.append("")
        lines.append("Suggested commands:")
        lines.extend(
            _format_bullets(
                [
                    action["command"],
                    "/loop next",
                    "/tasks list",
                    "/experiments list",
                    "/world list",
                    "/context build",
                ]
            )
        )
        return "\n".join(lines)

    def format_evening(self) -> str:
        snap = self.snapshot()
        recent_done = sorted(
            [task for task in snap["tasks_state"].records if task.get("status") == "done"],
            key=lambda item: str(item.get("updated_at", "")),
            reverse=True,
        )[:5]
        recent_experiments = sorted(
            [exp for exp in snap["experiments_state"].records if exp.get("status") in {"completed", "inconclusive"}],
            key=lambda item: str(item.get("updated_at", "")),
            reverse=True,
        )[:5]
        recent_world = sorted(
            [record for record in snap["world_state"].records if record.get("status") == "scored"],
            key=lambda item: str(item.get("updated_at", "")),
            reverse=True,
        )[:5]
        latest_reflection = _latest(snap["reflections"], "created_at")
        lines = [
            "Operating Loop Evening",
            f"Status: {_overall_status(snap)}",
            "",
            "Recent done tasks:",
        ]
        lines.extend(_format_bullets([_task_line(task) for task in recent_done]))
        lines.append("Recent completed/inconclusive experiments:")
        lines.extend(_format_bullets([_experiment_line(exp) for exp in recent_experiments]))
        lines.append("Recent scored world predictions:")
        lines.extend(_format_bullets([_world_line(record) for record in recent_world]))
        lines.append(f"Latest reflection: {_reflection_line(latest_reflection) if latest_reflection else 'none'}")
        lines.append("")
        lines.append("Suggested review commands:")
        lines.extend(
            _format_bullets(
                [
                    "/reflection now",
                    "/tasks list --all",
                    "Capture durable lessons with /skills add or /memory remember when operator-approved.",
                ]
            )
        )
        return "\n".join(lines)

    def format_evening_review(self) -> str:
        snap = self.snapshot()
        recent_done = _recent_completed_tasks(snap)
        recent_experiments = _recent_completed_experiments(snap)
        recent_world = _recent_scored_world(snap)
        latest_reflection = _latest(snap["reflections"], "created_at")
        warning_findings = [finding for finding in _doctor_findings(snap) if finding["severity"] in {"WARN", "ERROR"}]
        lines = [
            "Operating Loop Evening Review",
            f"Status: {_overall_status(snap)}",
            "",
            "Recent completed tasks:",
        ]
        lines.extend(_format_bullets([_task_line(task) for task in recent_done]))
        lines.append("Recent completed/inconclusive experiments:")
        lines.extend(_format_bullets([_experiment_line(exp) for exp in recent_experiments]))
        lines.append("Recent scored world predictions:")
        lines.extend(_format_bullets([_world_line(record) for record in recent_world]))
        lines.append(f"Latest reflection: {_reflection_line(latest_reflection) if latest_reflection else 'none'}")
        lines.append("")
        lines.append("Loop doctor warnings:")
        if warning_findings:
            lines.extend(f"- [{finding['severity']}] {finding['message']}" for finding in warning_findings[:8])
        else:
            lines.append("- none")
        lines.append("")
        lines.append("Suggested commands:")
        lines.extend(
            _format_bullets(
                [
                    "/reflection now --last 30",
                    "/world stats",
                    "/skills list",
                    "/context export",
                ]
            )
        )
        return "\n".join(lines)

    def format_capture_today(self) -> str:
        snap = self.snapshot()
        in_progress = sorted([task for task in snap["tasks_state"].records if task.get("status") == "in_progress"], key=_task_sort_key)
        blocked = sorted([task for task in snap["tasks_state"].records if task.get("status") == "blocked"], key=_task_sort_key)
        open_world = sorted(snap["open_world"], key=lambda item: str(item.get("updated_at") or item.get("created_at") or ""), reverse=True)[:5]
        running_experiments = sorted(snap["open_experiments"], key=lambda item: str(item.get("updated_at") or item.get("created_at") or ""), reverse=True)[:5]
        latest_reflection = _latest(snap["reflections"], "created_at")
        lines = [
            "Operating Loop Capture Today",
            "Mutation policy: read-only checklist; no goals, tasks, memory, world, skills, or reflections were changed.",
            "",
            "Work to close or preserve:",
            f"- in-progress tasks: {len(in_progress)}",
            f"- blocked tasks: {len(blocked)}",
            f"- open/running experiments: {len(snap['open_experiments'])}",
            f"- open/observed world predictions: {len(snap['open_world'])}",
            f"- latest reflection: {_reflection_line(latest_reflection) if latest_reflection else 'none'}",
            "",
            "Suggested capture commands:",
        ]
        commands = [
            "/tasks list",
            "/tasks list --all",
            "/experiments list",
            "/world list",
            "/reflection now --last 30",
            "/context export",
            "/context injection audit --last 20",
        ]
        for task in in_progress[:3]:
            commands.append(f"/tasks done {task.get('id')} <result>  # or /tasks block {task.get('id')} <reason>")
        for exp in running_experiments[:3]:
            if not exp.get("result"):
                commands.append(f"/experiments result {exp.get('id')} <what happened>")
            if not exp.get("lesson"):
                commands.append(f"/experiments lesson {exp.get('id')} <lesson>")
        for record in open_world[:3]:
            if record.get("status") == "open":
                commands.append(f"/world observe {record.get('id')} <actual outcome>")
            elif record.get("status") == "observed":
                commands.append(f"/world score {record.get('id')} <0-5>")
        commands.extend(
            [
                "/skills add <reusable lesson> --category workflow --summary <short summary>",
                "/skills list",
            ]
        )
        lines.extend(_format_bullets(commands))
        lines.append("")
        lines.append("Reminder:")
        lines.append("- Convert durable lessons manually; this command does not auto-write memory or skills.")
        return "\n".join(lines)

    def format_next(self) -> str:
        action = _next_action(self.snapshot())
        lines = ["Next action:", f"- type: {action['type']}"]
        if action.get("id"):
            lines.append(f"- id: {action['id']}")
        lines.append(f"- summary: {action['summary']}")
        lines.append(f"- suggested command: {action['command']}")
        return "\n".join(lines)

    def format_doctor(self) -> str:
        snap = self.snapshot()
        findings = _doctor_findings(snap)
        status = "OK"
        if any(finding["severity"] == "ERROR" for finding in findings):
            status = "ERROR"
        elif any(finding["severity"] == "WARN" for finding in findings):
            status = "WARN"
        lines = [
            "Operating Loop Doctor",
            f"Status: {status}",
            "",
            "Findings:",
        ]
        if not findings:
            lines.append("- [OK] No cross-module consistency issues found.")
        else:
            for finding in findings:
                lines.append(f"- [{finding['severity']}] {finding['message']}")
        lines.append("")
        lines.append("Recommendations:")
        if status == "OK":
            lines.append("- No action needed.")
        else:
            lines.append("- Inspect linked records before applying manual fixes.")
            lines.append("- Use module-specific commands such as /goals inspect, /tasks inspect, /experiments inspect, /world inspect.")
        return "\n".join(lines)


def _read_explicit_memory_counts(project_root: Path) -> dict[str, Any]:
    path = project_root / "proto_mind" / "data" / "persistent_memory.json"
    if not path.exists():
        return {"status": "missing", "active_explicit": 0, "forgotten_explicit": 0}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"status": f"ERROR: {exc}", "active_explicit": 0, "forgotten_explicit": 0}
    if not isinstance(payload, list):
        return {"status": "ERROR: persistent memory root is not a list", "active_explicit": 0, "forgotten_explicit": 0}
    explicit = [item for item in payload if isinstance(item, dict) and item.get("type") == "explicit"]
    active = [item for item in explicit if item.get("active", True)]
    forgotten = [item for item in explicit if not item.get("active", True)]
    return {"status": "OK", "active_explicit": len(active), "forgotten_explicit": len(forgotten)}


def _overall_status(snap: dict[str, Any]) -> str:
    states = [
        snap["goals_state"],
        snap["tasks_state"],
        snap["experiments_state"],
        snap["world_state"],
        snap["skills_state"],
    ]
    if any(state.error for state in states) or str(snap["memory"]["status"]).startswith("ERROR") or snap["identity"]["status"] == "ERROR":
        return "ERROR"
    if any(state.malformed_count for state in states) or snap["reflection_malformed"]:
        return "WARN"
    return "OK"


def _recommendations(snap: dict[str, Any]) -> list[str]:
    focused = _first(snap["focused_goals"])
    active_goals = snap["active_goals"]
    next_task = _best_next_task(snap["tasks_state"].records, focused_goal_id=focused.get("id") if focused else None)
    recommendations: list[str] = []
    if not focused and active_goals:
        recommendations.append(f"Focus an active goal: /goals focus {active_goals[0].get('id')}")
    elif not focused:
        recommendations.append("Create a goal: /goals add <title>")
    if focused and not _tasks_for_goal(snap["tasks_state"].records, str(focused.get("id"))):
        recommendations.append(f"Add a task for focused goal: /tasks add <title> --goal {focused.get('id')}")
    if next_task:
        if next_task.get("status") == "in_progress":
            recommendations.append(f"Continue in-progress task: /tasks inspect {next_task.get('id')}")
        else:
            recommendations.append(f"Start next task: /tasks start {next_task.get('id')}")
    if snap["open_experiments"]:
        recommendations.append(f"Inspect open experiment: /experiments inspect {snap['open_experiments'][0].get('id')}")
    if snap["open_world"]:
        recommendations.append("Review open world predictions: /world list")
    if str(snap["memory"]["status"]).startswith("ERROR"):
        recommendations.append("Run /memory doctor")
    if not snap["reflections"]:
        recommendations.append("Create a reflection entry: /reflection now")
    return recommendations or ["No immediate operator action suggested."]


def _next_action(snap: dict[str, Any]) -> dict[str, str]:
    focused = _first(snap["focused_goals"])
    tasks = snap["tasks_state"].records
    in_progress = sorted([task for task in tasks if task.get("status") == "in_progress"], key=_task_sort_key)
    if in_progress:
        task = in_progress[0]
        return {"type": "task", "id": str(task.get("id")), "summary": f"Continue {_task_line(task)}", "command": f"/tasks inspect {task.get('id')}"}
    if focused:
        focused_tasks = [
            task
            for task in tasks
            if task.get("goal_id") == focused.get("id") and task.get("status") == "open"
        ]
        if focused_tasks:
            task = sorted(focused_tasks, key=_task_sort_key)[0]
            return {"type": "task", "id": str(task.get("id")), "summary": f"Start focused-goal task {_task_line(task)}", "command": f"/tasks start {task.get('id')}"}
    open_tasks = [task for task in tasks if task.get("status") == "open"]
    if open_tasks:
        task = sorted(open_tasks, key=_task_sort_key)[0]
        return {"type": "task", "id": str(task.get("id")), "summary": f"Start {_task_line(task)}", "command": f"/tasks start {task.get('id')}"}
    for experiment in snap["experiments_state"].records:
        if experiment.get("status") in {"open", "running"} and not experiment.get("result"):
            return {"type": "experiment", "id": str(experiment.get("id")), "summary": f"Record result for {_experiment_line(experiment)}", "command": f"/experiments result {experiment.get('id')} <text>"}
        if experiment.get("status") in {"open", "running"} and not experiment.get("lesson"):
            return {"type": "experiment", "id": str(experiment.get("id")), "summary": f"Capture lesson for {_experiment_line(experiment)}", "command": f"/experiments lesson {experiment.get('id')} <text>"}
    for record in snap["world_state"].records:
        if record.get("status") == "observed" and record.get("score") is None:
            return {"type": "world", "id": str(record.get("id")), "summary": f"Score {_world_line(record)}", "command": f"/world score {record.get('id')} <0-5>"}
        if record.get("status") == "scored" and not record.get("lesson"):
            return {"type": "world", "id": str(record.get("id")), "summary": f"Capture lesson for {_world_line(record)}", "command": f"/world lesson {record.get('id')} <text>"}
    if snap["active_goals"] and not focused:
        goal = snap["active_goals"][0]
        return {"type": "goal", "id": str(goal.get("id")), "summary": f"Focus goal {_goal_line(goal)}", "command": f"/goals focus {goal.get('id')}"}
    if not snap["active_goals"]:
        return {"type": "goal", "id": "", "summary": "Create or focus a goal", "command": "/goals add <title>"}
    return {"type": "reflection", "id": "", "summary": "Capture current state in reflection journal", "command": "/reflection now"}


def _doctor_findings(snap: dict[str, Any]) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    states = {
        "goals": snap["goals_state"],
        "tasks": snap["tasks_state"],
        "experiments": snap["experiments_state"],
        "world": snap["world_state"],
        "skills": snap["skills_state"],
    }
    for name, state in states.items():
        if state.error:
            findings.append({"severity": "ERROR", "message": f"{name} storage read error: {state.error}"})
        if state.malformed_count:
            findings.append({"severity": "ERROR", "message": f"{name} storage has malformed JSONL entries: {state.malformed_count}"})

    goals_by_id = {goal.get("id"): goal for goal in snap["goals_state"].records}
    tasks_by_id = {task.get("id"): task for task in snap["tasks_state"].records}
    experiments_by_id = {exp.get("id"): exp for exp in snap["experiments_state"].records}
    focused = snap["focused_goals"]
    if len(focused) > 1:
        findings.append({"severity": "WARN", "message": f"Multiple focused goals detected: {', '.join(str(goal.get('id')) for goal in focused)}"})
    for goal in focused:
        if goal.get("status") in {"completed", "cancelled"}:
            findings.append({"severity": "WARN", "message": f"Focused goal is terminal: {goal.get('id')} status={goal.get('status')}"})
    for task in snap["tasks_state"].records:
        goal_id = task.get("goal_id")
        if goal_id and goal_id not in goals_by_id:
            findings.append({"severity": "WARN", "message": f"Task {task.get('id')} links to missing goal_id={goal_id}"})
        if goal_id and goal_id in goals_by_id and task.get("status") in {"open", "in_progress", "blocked"}:
            if goals_by_id[goal_id].get("status") in {"completed", "cancelled"}:
                findings.append({"severity": "WARN", "message": f"Open task {task.get('id')} links to terminal goal {goal_id}"})
        if task.get("status") == "done" and not str(task.get("result") or "").strip():
            findings.append({"severity": "WARN", "message": f"Completed task has empty result: {task.get('id')}"})
    for exp in snap["experiments_state"].records:
        goal_id = exp.get("goal_id")
        task_id = exp.get("task_id")
        if goal_id and goal_id not in goals_by_id:
            findings.append({"severity": "WARN", "message": f"Experiment {exp.get('id')} links to missing goal_id={goal_id}"})
        if task_id and task_id not in tasks_by_id:
            findings.append({"severity": "WARN", "message": f"Experiment {exp.get('id')} links to missing task_id={task_id}"})
        if exp.get("status") == "completed" and not str(exp.get("lesson") or "").strip():
            findings.append({"severity": "WARN", "message": f"Completed experiment has empty lesson: {exp.get('id')}"})
    for record in snap["world_state"].records:
        goal_id = record.get("goal_id")
        task_id = record.get("task_id")
        experiment_id = record.get("experiment_id")
        if goal_id and goal_id not in goals_by_id:
            findings.append({"severity": "WARN", "message": f"World prediction {record.get('id')} links to missing goal_id={goal_id}"})
        if task_id and task_id not in tasks_by_id:
            findings.append({"severity": "WARN", "message": f"World prediction {record.get('id')} links to missing task_id={task_id}"})
        if experiment_id and experiment_id not in experiments_by_id:
            findings.append({"severity": "WARN", "message": f"World prediction {record.get('id')} links to missing experiment_id={experiment_id}"})
        if record.get("status") == "scored" and not str(record.get("lesson") or "").strip():
            findings.append({"severity": "WARN", "message": f"Scored world prediction has empty lesson: {record.get('id')}"})
    archived_counts = {
        "world": sum(1 for record in snap["world_state"].records if record.get("status") == "archived"),
        "skills": sum(1 for skill in snap["skills_state"].records if skill.get("status") == "archived"),
    }
    if any(archived_counts.values()):
        findings.append({"severity": "OK", "message": f"Archived records: world={archived_counts['world']}, skills={archived_counts['skills']}"})
    return findings


def _recent_completed_tasks(snap: dict[str, Any], *, limit: int = 5) -> list[dict[str, Any]]:
    return sorted(
        [task for task in snap["tasks_state"].records if task.get("status") == "done"],
        key=lambda item: str(item.get("updated_at", "")),
        reverse=True,
    )[:limit]


def _recent_completed_experiments(snap: dict[str, Any], *, limit: int = 5) -> list[dict[str, Any]]:
    return sorted(
        [exp for exp in snap["experiments_state"].records if exp.get("status") in {"completed", "inconclusive"}],
        key=lambda item: str(item.get("updated_at", "")),
        reverse=True,
    )[:limit]


def _recent_scored_world(snap: dict[str, Any], *, limit: int = 5) -> list[dict[str, Any]]:
    return sorted(
        [record for record in snap["world_state"].records if record.get("status") == "scored"],
        key=lambda item: str(item.get("updated_at", "")),
        reverse=True,
    )[:limit]


def _tasks_for_goal(tasks: list[dict[str, Any]], goal_id: str) -> list[dict[str, Any]]:
    return [task for task in tasks if task.get("goal_id") == goal_id and task.get("status") in {"open", "in_progress", "blocked"}]


def _best_next_task(tasks: list[dict[str, Any]], *, focused_goal_id: object | None = None) -> dict[str, Any] | None:
    in_progress = [task for task in tasks if task.get("status") == "in_progress"]
    if in_progress:
        return sorted(in_progress, key=_task_sort_key)[0]
    if focused_goal_id:
        focused = [task for task in tasks if task.get("goal_id") == focused_goal_id and task.get("status") == "open"]
        if focused:
            return sorted(focused, key=_task_sort_key)[0]
    open_tasks = [task for task in tasks if task.get("status") == "open"]
    if open_tasks:
        return sorted(open_tasks, key=_task_sort_key)[0]
    return None


def _task_sort_key(task: dict[str, Any]) -> tuple[int, int, str]:
    status_rank = 0 if task.get("status") == "in_progress" else 1
    priority_rank = PRIORITY_RANK.get(str(task.get("priority") or "normal"), 1)
    return (status_rank, priority_rank, str(task.get("created_at", "")))


def _goal_line(goal: dict[str, Any]) -> str:
    return f"{goal.get('id')} [{goal.get('status')}] {goal.get('title')}"


def _task_line(task: dict[str, Any]) -> str:
    return f"{task.get('id')} [{task.get('status')}] priority={task.get('priority')} {task.get('title')}"


def _experiment_line(exp: dict[str, Any]) -> str:
    return f"{exp.get('id')} [{exp.get('status')}] {exp.get('title')}"


def _world_line(record: dict[str, Any]) -> str:
    return f"{record.get('id')} [{record.get('status')}] score={record.get('score')} {record.get('prediction')}"


def _reflection_line(reflection: dict[str, Any]) -> str:
    return f"{reflection.get('id')} created_at={reflection.get('created_at')}"


def _skill_line(skill: dict[str, Any]) -> str:
    return f"{skill.get('id')} category={skill.get('category')} uses={skill.get('uses')} {skill.get('name')}"


def _latest(records: list[dict[str, Any]], field: str) -> dict[str, Any] | None:
    candidates = [record for record in records if record.get(field)]
    if not candidates:
        return None
    return sorted(candidates, key=lambda item: str(item.get(field, "")), reverse=True)[0]


def _first(values: list[dict[str, Any]]) -> dict[str, Any] | None:
    return values[0] if values else None


def _format_bullets(values: list[str]) -> list[str]:
    if not values:
        return ["- none"]
    return [f"- {value}" for value in values]
