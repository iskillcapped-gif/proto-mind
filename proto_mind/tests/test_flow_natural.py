"""Core flow checks: natural."""
from __future__ import annotations

import unittest
from proto_mind.tests.flow_fixtures import (
    EVENING_REVIEW_BUNDLE,
    HEALTH_CHECK_BUNDLE,
    Path,
    SessionOperatorLogger,
    TemporaryDirectory,
    build_test_system,
    format_context_command,
    format_natural_command,
    format_natural_introspection_command,
    json,
    natural_router_doctor,
    normalize_natural_command,
    process_interactive_input,
    route_natural_command,
)


class NaturalFlowTests(unittest.TestCase):
    def test_natural_command_routes_allowed_russian_and_english_phrases(self) -> None:
        self.assertEqual(route_natural_command("проверь свою систему"), "/session self-check")
        self.assertEqual(route_natural_command("check your system"), "/session self-check")
        self.assertEqual(route_natural_command("  Проверь свою систему!  "), "/session self-check")
        self.assertEqual(route_natural_command("CHECK YOUR SYSTEM?"), "/session self-check")
        self.assertEqual(route_natural_command("run self-check"), "/session self-check")
        self.assertEqual(route_natural_command("run self check"), "/session self-check")
        self.assertEqual(normalize_natural_command("SELF-CHECK…"), "self check")

    def test_natural_command_v2_routes_explicit_workflow_phrases(self) -> None:
        cases = {
            HEALTH_CHECK_BUNDLE: ("проверь систему", "проверь себя", "сделай медосмотр", "есть ли проблемы", "run system check"),
            "/loop next": ("что дальше", "что делать дальше", "какой следующий шаг", "next action"),
            "/loop morning-plan": ("начать день", "утренний план", "morning plan"),
            EVENING_REVIEW_BUNDLE: ("закрыть день", "вечерний обзор", "подвести итоги дня", "evening review"),
            "/context injection enable": ("включи контекст", "возьми рюкзак", "работай с учетом контекста", "enable context"),
            "/context injection disable": ("выключи контекст", "сними рюкзак", "disable context"),
            "/consolidation preview": ("что стоит запомнить", "что нужно сохранить в память", "найди выводы", "memory candidates"),
            "/data inventory": ("покажи хранилища", "инвентаризация данных", "data inventory"),
        }
        for expected, phrases in cases.items():
            for phrase in phrases:
                with self.subTest(phrase=phrase):
                    self.assertEqual(route_natural_command(phrase), expected)

    def test_natural_command_does_not_route_bigger_prompts_containing_allowed_phrases(self) -> None:
        self.assertIsNone(route_natural_command("как сделать чтобы модель проверяла свою систему?"))
        self.assertIsNone(route_natural_command("напиши текст: проверь свою систему"))
        self.assertIsNone(route_natural_command("проверь свою систему и потом измени память"))
        self.assertIsNone(route_natural_command("можешь рассказать про самодиагностику?"))
        self.assertIsNone(route_natural_command("explain what check your system means"))
        self.assertIsNone(route_natural_command("как ты думаешь, что делать дальше в этой ситуации?"))
        self.assertIsNone(route_natural_command("расскажи, зачем нужен утренний план"))

    def test_natural_command_health_bundle_runs_safe_operator_reports(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            coordinator, _, _ = build_test_system(project_root / "proto_mind")
            logger = SessionOperatorLogger.from_project_root(project_root, enabled=False)

            output = process_interactive_input(
                "проверь систему",
                coordinator=coordinator,
                session_logger=logger,
                project_root=project_root,
            )

            self.assertIn("Natural command bundle matched:", output)
            for command in HEALTH_CHECK_BUNDLE:
                self.assertIn(f"=== {command} ===", output)
            self.assertIn("Data Integrity Doctor", output)
            self.assertIn("Cross-Store Reference Doctor", output)
            self.assertIn("Operating Loop Doctor", output)
            self.assertIn("Memory Doctor", output)
            self.assertIn("Consolidation Queue Doctor", output)
            self.assertEqual(logger.status().entry_count, 0)

    def test_natural_command_next_morning_and_evening_workflows(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            coordinator, _, _ = build_test_system(project_root / "proto_mind")
            logger = SessionOperatorLogger.from_project_root(project_root, enabled=False)

            next_output = process_interactive_input(
                "что делать дальше", coordinator=coordinator, session_logger=logger, project_root=project_root
            )
            morning_output = process_interactive_input(
                "начать день", coordinator=coordinator, session_logger=logger, project_root=project_root
            )
            evening_output = process_interactive_input(
                "закрыть день", coordinator=coordinator, session_logger=logger, project_root=project_root
            )

            self.assertIn("Natural command matched: /loop next", next_output)
            self.assertIn("Next action:", next_output)
            self.assertIn("Operating Loop Morning Plan", morning_output)
            self.assertIn("=== /loop evening-review ===", evening_output)
            self.assertIn("Operating Loop Evening Review", evening_output)
            self.assertIn("=== /loop capture-today ===", evening_output)
            self.assertIn("Operating Loop Capture Today", evening_output)

    def test_natural_command_context_toggle_is_explicit_and_reversible(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            coordinator, _, _ = build_test_system(project_root / "proto_mind")
            logger = SessionOperatorLogger.from_project_root(project_root, enabled=False)

            enabled = process_interactive_input(
                "включи контекст", coordinator=coordinator, session_logger=logger, project_root=project_root
            )
            status_enabled = format_context_command("/context injection status", project_root=project_root)
            disabled = process_interactive_input(
                "выключи контекст", coordinator=coordinator, session_logger=logger, project_root=project_root
            )
            status_disabled = format_context_command("/context injection status", project_root=project_root)

            self.assertIn("Natural command matched: /context injection enable", enabled)
            self.assertIn("enabled: True", status_enabled)
            self.assertIn("Natural command matched: /context injection disable", disabled)
            self.assertIn("enabled: False", status_disabled)
            self.assertEqual(logger.status().entry_count, 0)

    def test_natural_command_consolidation_and_inventory_reports(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            coordinator, _, _ = build_test_system(project_root / "proto_mind")
            logger = SessionOperatorLogger.from_project_root(project_root, enabled=False)

            consolidation = process_interactive_input(
                "что стоит запомнить", coordinator=coordinator, session_logger=logger, project_root=project_root
            )
            inventory = process_interactive_input(
                "инвентаризация данных", coordinator=coordinator, session_logger=logger, project_root=project_root
            )

            self.assertIn("Natural command matched: /consolidation preview", consolidation)
            self.assertIn("Consolidation Preview", consolidation)
            self.assertIn("Natural command matched: /data inventory", inventory)
            self.assertIn("Data Inventory", inventory)

    def test_natural_introspection_status_works(self) -> None:
        output = format_natural_introspection_command("/natural status")

        self.assertIn("Natural Command Router Status", output)
        self.assertIn("routes:", output)
        self.assertIn("bundle_routes:", output)
        self.assertIn("single_command_routes:", output)
        self.assertIn("deterministic exact normalized phrase matching", output)
        self.assertIn("llm_routing: disabled", output)
        self.assertIn("fuzzy_routing: disabled", output)

    def test_natural_introspection_list_groups_routes(self) -> None:
        output = format_natural_introspection_command("/natural list")

        self.assertIn("Natural Command Routes", output)
        for group in (
            "health bundle:",
            "session self-check:",
            "loop next:",
            "morning plan:",
            "evening bundle:",
            "context enable:",
            "context disable:",
            "consolidation preview:",
            "data inventory:",
        ):
            self.assertIn(group, output)
        self.assertIn("проверь систему", output)
        self.assertIn("data inventory", output)
        self.assertIn("[auto_allowed]", output)
        self.assertIn("[confirmation_required]", output)

    def test_natural_introspection_explain_match_and_unknown(self) -> None:
        matched = format_natural_introspection_command("/natural explain проверь систему")
        mutating = format_natural_introspection_command("/natural explain “возьми рюкзак”")
        unknown = format_natural_introspection_command("/natural explain какая сегодня погода")

        self.assertIn("normalized: проверь систему", matched)
        self.assertIn("matched: True", matched)
        self.assertIn("target_type: bundle", matched)
        self.assertIn("/data doctor", matched)
        self.assertIn("effect: read-only", matched)
        self.assertIn("policy_class: auto_allowed", matched)
        self.assertIn("bundle_strictest_policy: auto_allowed", matched)
        self.assertIn("category: data", matched)
        self.assertIn("read_only: True", matched)
        self.assertIn("mutates: none", matched)
        self.assertIn("risk: low", matched)
        self.assertIn("bypasses_reasoner: True", matched)
        self.assertIn("effect: explicit mutation", mutating)
        self.assertIn("/context injection enable", mutating)
        self.assertIn("policy_class: confirmation_required", mutating)
        self.assertIn("category: context", mutating)
        self.assertIn("read_only: False", mutating)
        self.assertIn("mutates: context", mutating)
        self.assertIn("risk: medium", mutating)
        self.assertIn("matched: False", unknown)
        self.assertIn("target: none", unknown)

    def test_natural_explain_next_action_shows_registry_and_policy(self) -> None:
        output = format_natural_introspection_command("/natural explain что делать дальше")

        self.assertIn("target: /loop next", output)
        self.assertIn("effect: read-only", output)
        self.assertIn("policy_class: auto_allowed", output)
        self.assertIn("category: loop", output)
        self.assertIn("policy: auto_allowed", output)

    def test_natural_suggest_finds_close_system_phrase_without_execution(self) -> None:
        output = format_natural_introspection_command("/natural suggest “проверь системму”")

        self.assertIn("Natural Command Suggestions", output)
        self.assertIn("matched: False", output)
        self.assertIn("проверь систему -> health bundle", output)
        self.assertIn("/data doctor", output)
        self.assertIn("No command executed.", output)

    def test_natural_suggest_finds_close_context_phrase_without_enabling_it(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            coordinator, _, _ = build_test_system(project_root / "proto_mind")
            logger = SessionOperatorLogger.from_project_root(project_root)

            output = process_interactive_input(
                "/natural suggest включи кантекст",
                coordinator=coordinator,
                session_logger=logger,
                project_root=project_root,
            )

            self.assertIn("включи контекст -> context enable", output)
            self.assertIn("[explicit mutation]", output)
            self.assertIn("No command executed.", output)
            self.assertFalse((project_root / "proto_mind" / "data" / "context_injection.json").exists())
            self.assertEqual(logger.status().entry_count, 0)

    def test_natural_suggest_exact_phrase_explains_target_without_execution(self) -> None:
        output = format_natural_introspection_command("/natural suggest проверь систему")

        self.assertIn("matched: True", output)
        self.assertIn("target_type: bundle", output)
        self.assertIn("target: /data doctor", output)
        self.assertIn("effect: read-only", output)
        self.assertIn("No command executed.", output)
        self.assertNotIn("Data Integrity Doctor\nStatus:", output)

    def test_natural_suggest_unrelated_phrase_has_no_suggestions(self) -> None:
        output = format_natural_introspection_command("/natural suggest какая сегодня погода")

        self.assertIn("matched: False", output)
        self.assertIn("suggestions:\n- none", output)
        self.assertIn("No command executed.", output)

    def test_natural_typo_does_not_execute_closest_route(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            coordinator, _, _ = build_test_system(project_root / "proto_mind")
            logger = SessionOperatorLogger.from_project_root(project_root)
            coordinator.session_logger = logger

            output = process_interactive_input(
                "проверь системму",
                coordinator=coordinator,
                session_logger=logger,
                project_root=project_root,
            )

            self.assertIsNone(route_natural_command("проверь системму"))
            self.assertIn("Proto-Mind:", output)
            self.assertNotIn("Natural command bundle matched", output)
            self.assertNotIn("Data Integrity Doctor", output)
            self.assertEqual(logger.status().entry_count, 1)

    def test_natural_introspection_doctor_returns_ok_for_current_routes(self) -> None:
        output = format_natural_introspection_command("/natural doctor")

        self.assertIn("Natural Command Router Doctor", output)
        self.assertIn("Status: OK", output)
        self.assertIn("Registry/policy targets checked: 65", output)
        self.assertIn("valid and allowlisted", output)
        self.assertIn("Read-only diagnostics only", output)

    def test_natural_router_doctor_detects_invalid_duplicate_and_empty_fixtures(self) -> None:
        report = natural_router_doctor(
            [
                ("", "/loop next"),
                ("Duplicate", "/loop next"),
                (" duplicate! ", "/loop next"),
                ("unsafe", "/shell rm -rf"),
                ("chain", "/loop next; /memory doctor"),
            ]
        )
        messages = "\n".join(item["message"] for item in report["findings"])

        self.assertEqual(report["status"], "ERROR")
        self.assertIn("Empty natural phrases", messages)
        self.assertIn("Duplicate normalized phrases: duplicate", messages)
        self.assertIn("Non-allowlisted command target", messages)
        self.assertIn("Unsafe command target", messages)

    def test_natural_introspection_works_through_shared_handler_without_cognitive_turn(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            coordinator, _, _ = build_test_system(project_root / "proto_mind")
            logger = SessionOperatorLogger.from_project_root(project_root)
            coordinator.session_logger = logger

            output = process_interactive_input(
                "/natural status",
                coordinator=coordinator,
                session_logger=logger,
                project_root=project_root,
            )

            self.assertIn("Natural Command Router Status", output)
            self.assertEqual(logger.status().entry_count, 0)

    def test_natural_command_prints_notice_and_runs_self_check_without_logging(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "exports").mkdir()
            (root / "backups").mkdir()
            log_path = root / "logs" / "session_operator_log.jsonl"
            log_path.parent.mkdir(parents=True)
            log_path.write_text(
                json.dumps(
                    {
                        "turn_id": 1,
                        "user_input": "Existing turn",
                        "reasoner_backend": "ollama",
                        "observer": {"query_type": "new_question"},
                        "retrieved_memory_ids": [],
                        "self_reflection": {"warnings": [], "correction_hints": []},
                        "grounding_audit": {"grounding_status": "grounded", "warnings": []},
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            logger = SessionOperatorLogger(log_path)
            before_bytes = log_path.read_bytes()
            before_count = logger.status().entry_count

            output = format_natural_command("проверь свою систему", logger)

            self.assertIsNotNone(output)
            self.assertIn("Natural command matched: /session self-check", output)
            self.assertIn("Session Self-Check", output)
            self.assertEqual(log_path.read_bytes(), before_bytes)
            self.assertEqual(logger.status().entry_count, before_count)

    def test_natural_command_is_read_only_and_creates_no_export_or_backup_dirs(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            log_path = root / "logs" / "session_operator_log.jsonl"
            log_path.parent.mkdir(parents=True)
            log_path.write_text(json.dumps({"turn_id": 1, "user_input": "Existing"}) + "\n", encoding="utf-8")
            logger = SessionOperatorLogger(log_path)
            before_bytes = log_path.read_bytes()

            output = format_natural_command("check your system", logger)

            self.assertIsNotNone(output)
            self.assertEqual(log_path.read_bytes(), before_bytes)
            self.assertFalse((root / "exports").exists())
            self.assertFalse((root / "backups").exists())
