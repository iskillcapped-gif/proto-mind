#!/usr/bin/env python3
"""Opt-in live selection and four independently checked tasks on synthetic projects."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from unittest.mock import patch
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from proto_mind.config import ProtoMindConfig
from proto_mind.native_agent import FULL_ACCESS_CONFIRMATION
from proto_mind.native_auto_skills import AutoSkills
from proto_mind.native_bridge import NativeBackend
from proto_mind.native_codex import CodexSubscription
from proto_mind.native_work_sessions import workspace_identity


def hashes(root: Path) -> dict:
    return {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in root.rglob("*") if path.is_file()}


def populate(workspace: Path, diagnosis=False) -> None:
    workspace.mkdir(parents=True)
    (workspace / "README.md").write_text(
        "# Disposable Python project\nEntry point: cli.py. Arithmetic: calculator.py. Tests: test_calculator.py.\n"
        f"Test command: {sys.executable} -B -m unittest -q\n"
        "Synthetic evaluation data, not personal files. No package installation, external service or backup is required.\n")
    (workspace / "calculator.py").write_text("def add(left, right):\n    return left " + ("-" if diagnosis else "+") + " right\n")
    (workspace / "cli.py").write_text("from calculator import add\nprint(add(2, 3))\n")
    (workspace / "test_calculator.py").write_text(
        "import unittest\nfrom calculator import add\n\nclass CalculatorTests(unittest.TestCase):\n"
        "    def test_add(self):\n        self.assertEqual(add(2, 3), 5)\n")
    (workspace / "STATUS.md").write_text(
        "# Historical handoff fixture\nThe parser was implemented. A previous recorded test report says 3 tests passed; not checked in this session.\n"
        "Development port: 8173. Next planned step: reject negative amounts. No active background work.\n")


def verify_task(name, workspace, before, output):
    after = hashes(workspace)
    text = output["result"]["response"] if "result" in output else ""
    # Native returns the public envelope under evidence; use its response, not the raw JSON report.
    text = output.get("evidence", {}).get("response", "") or text or output.get("text", "")
    text = text.lower()
    if name == "project_orientation":
        return before == after and all(item in text for item in ("cli.py", "calculator.py", "test_calculator.py"))
    if name == "failure_diagnosis":
        return before == after and any(item in text for item in ("вычит", "subtr", "left - right", "left-right"))
    if name == "work_handoff":
        return before == after and "8173" in text and any(item in text for item in ("отриц", "negative"))
    changed = {key for key in before.keys() | after.keys() if before.get(key) != after.get(key)}
    if changed != {"calculator.py", "test_calculator.py"}:
        return False
    environment = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    suite = subprocess.run([sys.executable, "-B", "-m", "unittest", "-q"], cwd=workspace, env=environment,
                           capture_output=True, text=True, timeout=15)
    independent = subprocess.run([sys.executable, "-B", "-c",
        "from calculator import add, subtract; assert add(2,3)==5; assert subtract(8,3)==5; assert subtract(3,8)==-5; assert subtract(-2,-3)==1; assert subtract(0,0)==0"],
        cwd=workspace, env=environment, capture_output=True, text=True, timeout=15)
    return suite.returncode == independent.returncode == 0 and hashes(workspace) == after


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--model", required=True)
    parser.add_argument("--profile-state", type=Path, default=Path.home() / "Library/Application Support/ProtoMindNative")
    parser.add_argument("--full-access-pilot", action="store_true", help="Also authorize the four synthetic foreground tasks")
    args = parser.parse_args()
    if not args.live:
        parser.error("--live is required; no model or task was run.")
    profile = args.profile_state.resolve() / "codex-profile"
    if not profile.is_dir():
        parser.error("An existing Native ChatGPT subscription profile is required; no login or credential copy.")
    results = []

    def record(case, passed, **extra):
        row = {"case": case, "passed": passed, **extra}
        results.append(row); print(json.dumps(row, ensure_ascii=False), flush=True)

    with TemporaryDirectory(prefix="proto-starter-skills-live-") as temporary:
        base = Path(temporary).resolve(); root = base / "project"; data = root / "proto_mind/data"
        data.mkdir(parents=True)
        (data / "persistent_memory.json").write_text("[]\n")
        (data / "skills.jsonl").write_text("")
        (data / "context_injection.json").write_text('{"enabled": false}\n')
        core_before = hashes(data)

        def factory(state):
            subscription = CodexSubscription(state); subscription.home = profile
            return subscription

        subscription = factory(base / "selection-state")
        cases = [
            ("ru_orientation", "Разберись в структуре этого проекта: где точка входа, основная логика и тесты? Пока ничего не меняй.", "project_orientation"),
            ("ru_change", "Добавь функцию subtract в калькулятор, допиши тесты и проверь результат.", "verified_change"),
            ("en_change", "Implement subtraction support in this calculator and add regression tests. Verify the final change.", "verified_change"),
            ("ru_diagnosis", "Разберись, почему падает этот тест. Нужна причина с доказательствами, код пока не меняй.", "failure_diagnosis"),
            ("ru_handoff", "Подготовь краткий handoff: что сделано, какие проверки есть и что осталось на следующую сессию.", "work_handoff"),
            ("casual", "Привет, брат, как настроение?", None),
            ("translation", "Переведи на английский: На улице светит солнце.", None),
        ]
        try:
            for name, text, expected in cases:
                subscription.prepare_turn()
                auto = AutoSkills(root, conversation=str(uuid4()), workspace=workspace_identity(root), text=text, mode="chat")
                auto.select(subscription, text=text, history=[], model=args.model, emit=lambda _: None)
                actual = [row["skill_id"] for row in auto.report["selected"]]
                record(name, actual == (["builtin." + expected] if expected else []), selected=actual)
        finally:
            subscription.close()
        if args.full_access_pilot and all(row["passed"] for row in results):
            tasks = {
                "project_orientation": "Разберись в структуре текущего Python-проекта. Назови точку входа, модуль логики и тестовый файл. Ничего не меняй и не запускай тесты.",
                "failure_diagnosis": "Тест add(2, 3) ожидает 5, а получает -1. Разберись по коду, почему он падает. Только диагностика, никаких изменений или запуска тестов.",
                "verified_change": "Добавь в calculator.py функцию subtract(left, right). Допиши проверки в существующем test_calculator.py и запусти тесты. Проверь отрицательный и нулевой результат. Не меняй остальные файлы.",
                "work_handoff": "По STATUS.md подготовь краткий handoff для следующей сессии: что сделано, какие проверки исторические, какой порт используется и какой следующий шаг. Ничего не меняй и не запускай тесты.",
            }
            backend = NativeBackend(root, base / "task-state", subscription_factory=factory)
            try:
                for name, task in tasks.items():
                    workspace = root / "tasks" / name; populate(workspace, diagnosis=name == "failure_diagnosis")
                    before = hashes(workspace); conversation = str(uuid4())
                    with patch.object(ProtoMindConfig, "from_env", return_value=ProtoMindConfig(data_dir=data)), \
                         patch("proto_mind.native_codex.discover_computer_use", return_value={"available": False}):
                        grant = backend.dispatch("agent_access", {"conversation_id": conversation, "workspace_root": str(workspace),
                            "mode": "full_access", "cloud_consent": True, "confirmation": FULL_ACCESS_CONFIRMATION}, lambda _: None, "grant")
                        output = backend.process({"conversation_id": conversation, "workspace_root": str(workspace), "provider": "codex",
                            "model": args.model, "reasoning_effort": "low", "cloud_consent": True, "auto_skills": True,
                            "access_mode": "full_access", "access_token": grant["token"], "text": task +
                            " Это изолированный тест, работай только с файлами текущей папки. Не читай другие папки, память или личные данные. "
                            "Не используй сеть, браузер, Computer Use, git, установку пакетов или команды Proto-Mind. "
                            f"При необходимости Python используй {sys.executable} -B. Не создавай __pycache__."}, lambda _: None, "starter-" + name)
                    selected = [row["skill_id"] for row in output["auto_skills"]["selected"]]
                    passed = (selected == ["builtin." + name] and verify_task(name, workspace, before, output)
                              and hashes(data) == core_before and output["work_session"]["verification"] == "not_assessed"
                              and not output["agent_run"]["network_access_performed"] and not output["agent_run"]["computer_use_performed"])
                    record("task_" + name, passed, selected=selected, command_count=output["agent_run"]["command_count"],
                           core_unchanged=hashes(data) == core_before, verification="host_checked_fixture_not_general_skill_quality")
                    if not passed: break
            finally:
                backend.close()
        passed = all(row["passed"] for row in results) and hashes(data) == core_before
        print(json.dumps({"passed": passed, "cases": len(results), "personal_data_used": False,
                          "core_unchanged": hashes(data) == core_before, "automatic_learning": False}), flush=True)
        return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
