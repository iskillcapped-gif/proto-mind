#!/usr/bin/env python3
"""Opt-in subscription evaluation using synthetic skills in a disposable project.

No credentials are copied or read by this script. Codex uses its existing Native
profile. --full-access-pilot additionally authorizes one task in the fixture.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from unittest.mock import patch
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from proto_mind.config import ProtoMindConfig
from proto_mind.experience_learning_skill_apply import OperatorReviewedProceduralSkillApplySession, procedural_skill_apply_confirmation_token
from proto_mind.experience_learning_skill_authoring import (
    OperatorReviewedProceduralSkillAuthoringSession, ProceduralSkillAuthoringRequest,
    build_procedural_skill_authoring_blueprint, procedural_skill_authoring_confirmation_token,
)
from proto_mind.experience_learning_skill_contract import ProceduralSkillContractBuilder
from proto_mind.experience_learning_skill_readiness import ProceduralSkillApplyReadiness
from proto_mind.native_agent import FULL_ACCESS_CONFIRMATION
from proto_mind.native_auto_skills import AutoSkills
from proto_mind.native_bridge import NativeBackend
from proto_mind.native_codex import CodexSubscription
from proto_mind.native_work_sessions import workspace_identity
from proto_mind.skill_library import SkillLibrary
from proto_mind.tests.test_flow import build_test_learning_outcome_review


CONTRACTS = [
    {"name": "CSV amount total", "summary": "Validate a CSV amount column and compute an exact decimal total in a requested JSON report.",
     "trigger": "The user asks to sum a CSV ledger or reconcile numeric amounts from a local CSV file.",
     "preconditions": ["The operator named the input CSV and output report inside the selected project.", "The input has an amount column with decimal values."],
     "steps": ["Read the selected CSV with a CSV parser; do not execute data as code.", "Parse amount values using Decimal, count rows and sum exactly.",
               "Create only the requested JSON report with rows and total; do not overwrite an existing report.",
               "Read the report back and check count and decimal sum against the input."],
     "permissions": ["Existing separately granted file and terminal access; no permission is granted by this procedure."],
     "verification": ["The source file bytes are unchanged.", "The report contains the actual row count and exact total, not a guessed value."],
     "known_failure_modes": ["Missing column, invalid decimal, existing report or denied file access must be reported, not hidden."]},
    {"name": "Python project inspection", "summary": "Inspect Python project structure and tests without changing source files.",
     "trigger": "The user asks to inspect a Python repository, understand its tests or diagnose a repeated test failure.",
     "preconditions": ["The operator identified the project and limited the inspection scope."],
     "steps": ["Read project instructions and identify the test runner.", "Inspect relevant Python code and evidence for the reported failure.",
               "Explain findings with source references and separate observed facts from hypotheses."],
     "permissions": ["Read-only project access; run tests only if requested under existing tool permissions."],
     "verification": ["No project source file was changed.", "Claims refer to inspected code or test output."],
     "known_failure_modes": ["Missing dependencies or unavailable evidence are not passing test results."]},
]


def seed(root: Path) -> dict[str, str]:
    data = root / "proto_mind/data"
    data.mkdir(parents=True)
    ids, memories, skills = {}, [], []
    for index, fields in enumerate(CONTRACTS):
        source = root / ("source-fixture-" + str(index))
        _, store, _, review = build_test_learning_outcome_review(source)
        library = SkillLibrary(source / "skills.jsonl")
        builder = ProceduralSkillContractBuilder(memory_store=store, skill_library=library)
        blueprint = build_procedural_skill_authoring_blueprint(builder, ProceduralSkillAuthoringRequest(memory_id=review.lesson_memory_id, **fields))
        receipt = OperatorReviewedProceduralSkillAuthoringSession().create(blueprint, token=procedural_skill_authoring_confirmation_token(blueprint))
        readiness = ProceduralSkillApplyReadiness(builder=builder, skill_library=library)
        session = OperatorReviewedProceduralSkillApplySession()
        applied = session.apply(receipt, token=procedural_skill_apply_confirmation_token(session.review(receipt, reviewer=readiness)), reviewer=readiness)
        ids[fields["name"]] = applied.created_skill_id
        memories.extend(json.loads(store.persistent_path.read_text()))
        skills.extend(json.loads(line) for line in library.skills_path.read_text().splitlines())
    if len({row["id"] for row in memories}) != len(memories):
        raise ValueError("Fixture lesson IDs must be distinct.")
    (data / "persistent_memory.json").write_text(json.dumps(memories) + "\n")
    (data / "skills.jsonl").write_text("".join(json.dumps(row) + "\n" for row in skills))
    (data / "context_injection.json").write_text('{"enabled": false}\n')
    return ids


def source_hashes(root: Path) -> dict:
    return {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in (root / "proto_mind/data").iterdir()
            if path.name in {"persistent_memory.json", "skills.jsonl", "context_injection.json"}}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="Allow bounded model requests through the signed-in Native Codex profile")
    parser.add_argument("--profile-state", type=Path, default=Path.home() / "Library/Application Support/ProtoMindNative")
    parser.add_argument("--model", required=True)
    parser.add_argument("--full-access-pilot", action="store_true", help="Also run one exact synthetic CSV task with existing Full Mac tools")
    args = parser.parse_args()
    if not args.live:
        parser.error("--live is required. No cloud call or task was performed.")
    profile = args.profile_state.resolve() / "codex-profile"
    if not profile.is_dir():
        parser.error("Existing Native Codex profile is required; this evaluation does not log in or copy credentials.")
    results = []
    with TemporaryDirectory(prefix="proto-auto-skills-live-") as temporary:
        base = Path(temporary).resolve()
        root = base / "project"
        ids = seed(root)
        before = source_hashes(root)

        def subscription_factory(state):
            subscription = CodexSubscription(state)
            subscription.home = profile
            return subscription

        subscription = subscription_factory(base / "selector-state")
        try:
            cases = [
                ("ru_csv", "В ledger.csv список сумм. Посчитай точный итог и количество строк, результат запиши в report.json.", [[ids["CSV amount total"]]]),
                ("en_csv", "Reconcile the amount column in ledger.csv and put the precise sum and number of entries in report.json.", [[ids["CSV amount total"]]]),
                # Both contracts now explicitly cover read-only test-failure diagnosis; unrelated or redundant selections still fail.
                ("ru_python", "В этом Python-проекте снова падает один и тот же тест. Разберись по коду, пока ничего не меняй.",
                 [[ids["Python project inspection"]], ["builtin.failure_diagnosis"]]),
                ("casual", "Привет, брат, как настроение? Просто поболтаем.", [[]]),
                ("unrelated", "Переведи на английский: Сегодня мы идём гулять в парк.", [[]]),
            ]
            for name, text, accepted_selections in cases:
                subscription.prepare_turn()
                auto = AutoSkills(root, conversation=str(uuid4()), workspace=workspace_identity(root), text=text, mode="chat")
                auto.select(subscription, text=text, history=[], model=args.model, emit=lambda _: None)
                actual = [row["skill_id"] for row in auto.report["selected"]]
                result = {"case": name, "passed": actual in accepted_selections, "state": auto.report["state"],
                          "accepted_selections": accepted_selections,
                          "selected_names": [row["skill_name"] for row in auto.report["selected"]],
                          "selector_model": auto.report["selector_model"], "selector_effort": auto.report["selector_effort"]}
                results.append(result); print(json.dumps(result, ensure_ascii=False), flush=True)
        finally:
            subscription.close()
        if args.full_access_pilot and all(row["passed"] for row in results):
            ledger = b"label,amount\nfirst,12.50\nsecond,7.25\nrefund,-2.00\n"
            (root / "ledger.csv").write_bytes(ledger)
            conversation = str(uuid4())
            backend = NativeBackend(root, base / "task-state", subscription_factory=subscription_factory)
            try:
                with patch.object(ProtoMindConfig, "from_env", return_value=ProtoMindConfig(data_dir=root / "proto_mind/data")), \
                     patch("proto_mind.native_codex.discover_computer_use", return_value={"available": False}):
                    grant = backend.dispatch("agent_access", {"conversation_id": conversation, "workspace_root": str(root),
                        "mode": "full_access", "cloud_consent": True, "confirmation": FULL_ACCESS_CONFIRMATION}, lambda _: None, "grant")
                    output = backend.process({"conversation_id": conversation, "workspace_root": str(root), "provider": "codex",
                        "model": args.model, "reasoning_effort": "low", "cloud_consent": True, "auto_skills": True,
                        "access_mode": "full_access", "access_token": grant["token"],
                        "text": "Это изолированный тест. Только в текущей папке: прочитай ledger.csv, посчитай строки и точную сумму amount. "
                                "Создай report.json с полями rows (число) и total (десятичная строка с двумя знаками). Проверь файл повторным чтением. "
                                "Входной файл не меняй. Другие файлы и папки не открывай и не меняй. Не используй сеть, браузер, Computer Use, память или команды Proto-Mind. "
                                "Если есть подходящий навык, используй его как ориентир. В конце коротко сообщи фактический результат.",
                    }, lambda _: None, "live-auto-skill-task")
                actual = json.loads((root / "report.json").read_text()) if (root / "report.json").is_file() else None
                passed = (actual == {"rows": 3, "total": "17.75"} and (root / "ledger.csv").read_bytes() == ledger
                          and source_hashes(root) == before and output["auto_skills"]["state"] == "selected"
                          and [row["skill_id"] for row in output["auto_skills"]["selected"]] == [ids["CSV amount total"]]
                          and output["work_session"]["verification"] == "not_assessed"
                          and not output["agent_run"]["network_access_performed"]
                          and not output["agent_run"]["computer_use_performed"])
                result = {"case": "full_access_csv_task", "passed": passed, "output": actual,
                          "source_unchanged": source_hashes(root) == before, "command_count": output["agent_run"]["command_count"],
                          "verification": "fixture_checked_by_evaluation_not_general_skill_quality",
                          "selected_names": [row["skill_name"] for row in output["auto_skills"]["selected"]]}
                results.append(result); print(json.dumps(result, ensure_ascii=False), flush=True)
            finally:
                backend.close()
        unchanged = source_hashes(root) == before
        passed = all(row["passed"] for row in results) and unchanged
        print(json.dumps({"passed": passed, "cases": len(results), "synthetic_skill_sources_unchanged": unchanged,
                          "personal_stores_used": False, "automatic_learning": False, "automatic_retry": False}), flush=True)
        return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
