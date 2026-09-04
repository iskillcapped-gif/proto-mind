"""Core flow checks: operator contracts."""
from __future__ import annotations

import unittest
from proto_mind.tests.flow_fixtures import (
    COMMAND_REGISTRY,
    CommandSpec,
    ContestShowcase,
    ContextInjectionAuditLog,
    Coordinator,
    ExperimentJournal,
    GoalStack,
    IdentityStore,
    MANY_FILES_THRESHOLD,
    MemoryKeeper,
    MemoryRecord,
    MemoryStore,
    MockReasoner,
    NATURAL_COMMAND_ROUTES,
    Observer,
    OllamaReasoner,
    Path,
    ProtoMindConfig,
    SHOWCASE_COMMANDS,
    SessionOperatorLogger,
    SimpleNamespace,
    TaskQueue,
    TemporaryDirectory,
    _create_healthy_export_dirs,
    _memory_card_state,
    _prechange_state,
    _write_milestone_fixture,
    apply_test_learning_proposal,
    audit_for_test,
    build_contest_provenance,
    build_test_learning_apply,
    build_test_procedural_skill_lifecycle_readiness,
    build_test_system,
    classify_command,
    command_registry_doctor,
    create_project_backup,
    create_reasoner,
    extract_topic_tags,
    format_backup_command,
    format_commands_command,
    format_context_command,
    format_daily_command,
    format_experiment_command,
    format_exports_command,
    format_goal_command,
    format_identity_command,
    format_learning_memory_apply_command,
    format_milestone_command,
    format_natural_command,
    format_prechange_command,
    format_procedural_skill_lifecycle_apply_command,
    format_session_log_command,
    format_showcase_command,
    format_task_command,
    get_experience_pilot,
    is_backup_command,
    is_exit_command,
    is_submission_relevant,
    json,
    match_registered_command,
    os,
    patch,
    peek_experience_pilot,
    process_interactive_input,
    python_env,
    reflect_for_test,
    tarfile,
    verify_memory_provenance,
)


class OperatorContractsTests(unittest.TestCase):
    def test_python_env_guard_helpers_and_dev_scripts(self) -> None:
        old_python = SimpleNamespace(major=3, minor=9, micro=6)
        supported_python = SimpleNamespace(major=3, minor=11, micro=15)
        self.assertEqual(python_env.MIN_PYTHON_VERSION, (3, 11))
        self.assertFalse(python_env.is_supported_python(old_python))
        self.assertTrue(python_env.is_supported_python(supported_python))

        message = python_env.format_unsupported_python_message(old_python)
        self.assertIn("requires Python 3.11+", message)
        self.assertIn("Current Python: 3.9.6", message)
        self.assertIn("/opt/homebrew/opt/python@3.11/bin/python3.11 -m proto_mind.main", message)

        root = Path(__file__).resolve().parents[2]
        common = (root / "scripts" / "python_common.sh").read_text(encoding="utf-8")
        run_cli = (root / "scripts" / "run_cli.sh").read_text(encoding="utf-8")
        run_tests = (root / "scripts" / "run_tests.sh").read_text(encoding="utf-8")
        which_python = (root / "scripts" / "which_python.sh").read_text(encoding="utf-8")

        self.assertIn("/opt/homebrew/opt/python@3.11/bin/python3.11", common)
        self.assertIn("/opt/homebrew/opt/python@3.11/bin/python3", common)
        self.assertIn("sys.version_info >= (3, 11)", common)
        self.assertIn("-m proto_mind.main", run_cli)
        self.assertIn("-m unittest proto_mind.tests.test_flow", run_tests)
        self.assertIn("-m compileall proto_mind", run_tests)
        self.assertIn("pytest not installed; skipping optional pytest run.", run_tests)
        self.assertIn("PySide6 import", which_python)

    def test_backup_command_is_recognized(self) -> None:
        self.assertTrue(is_backup_command("/memory backup"))
        self.assertTrue(is_backup_command("/system checkpoint"))
        self.assertTrue(is_backup_command("  /memory   backup  "))
        self.assertFalse(is_backup_command("/memory summary"))

    def test_backup_function_creates_archive_and_reports_path(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            package_dir = project_root / "proto_mind"
            data_dir = package_dir / "data"
            data_dir.mkdir(parents=True)
            (package_dir / "__init__.py").write_text("", encoding="utf-8")
            (data_dir / "working_memory.json").write_text("[]", encoding="utf-8")
            (data_dir / "persistent_memory.json").write_text("[]", encoding="utf-8")
            (project_root / "ARCHITECTURE_MAP_V2.md").write_text("# Test", encoding="utf-8")

            result = create_project_backup(project_root, timestamp="2026-05-23_12-34-56")
            output = format_backup_command("/memory backup", project_root)

            self.assertTrue(result.archive_path.exists())
            self.assertIn("proto_mind_backup_2026-05-23_12-34-56.tar.gz", result.archive_path.name)
            self.assertIsNotNone(output)
            self.assertIn("Memory backup created:", output)
            self.assertIn(str(project_root / "backups"), output)
            with tarfile.open(result.archive_path, "r:gz") as archive:
                names = set(archive.getnames())
            self.assertIn("proto_mind/data/working_memory.json", names)
            self.assertIn("proto_mind/data/persistent_memory.json", names)
            self.assertIn("ARCHITECTURE_MAP_V2.md", names)
            self.assertFalse(any(name.startswith("backups/") for name in names))

    def test_backup_command_does_not_modify_memory_files_or_records(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            package_dir = project_root / "proto_mind"
            data_dir = package_dir / "data"
            data_dir.mkdir(parents=True)
            working_path = data_dir / "working_memory.json"
            persistent_path = data_dir / "persistent_memory.json"
            working_path.write_text('[{"content": "working"}]', encoding="utf-8")
            persistent_path.write_text('[{"content": "persistent"}]', encoding="utf-8")

            before_working = working_path.read_bytes()
            before_persistent = persistent_path.read_bytes()
            output = format_backup_command("/system checkpoint", project_root)

            self.assertIsNotNone(output)
            self.assertEqual(working_path.read_bytes(), before_working)
            self.assertEqual(persistent_path.read_bytes(), before_persistent)
            self.assertEqual(json.loads(working_path.read_text(encoding="utf-8")), [{"content": "working"}])
            self.assertEqual(json.loads(persistent_path.read_text(encoding="utf-8")), [{"content": "persistent"}])

    def test_command_registry_status_works(self) -> None:
        output = format_commands_command("/commands status")

        self.assertIn("Command Registry Status", output)
        self.assertIn("registered_commands: 387", output)
        self.assertIn("read_only:", output)
        self.assertIn("mutating:", output)
        self.assertIn("category_counts:", output)
        self.assertIn("risk_counts:", output)

    def test_command_registry_list_groups_core_categories(self) -> None:
        output = format_commands_command("/commands list")

        self.assertIn("Command Registry", output)
        for category in (
            "action:",
            "acceptance:",
            "agenda:",
            "baseline:",
            "capabilities:",
            "closure:",
            "confirm:",
            "session:",
            "memory:",
            "memory-card:",
            "reflection:",
            "goals:",
            "tasks:",
            "experiments:",
            "focus:",
            "exports:",
            "skills:",
            "world:",
            "warnings:",
            "loop:",
            "identity:",
            "context:",
            "consolidation:",
            "data:",
            "daily:",
            "milestone:",
            "natural:",
            "policy:",
            "plan:",
            "prechange:",
            "proto:",
        ):
            self.assertIn(category, output)

    def test_command_registry_explain_exact_and_longest_prefix(self) -> None:
        data = format_commands_command("/commands explain /data doctor")
        memory = format_commands_command("/commands explain /memory remember hello")
        matched = match_registered_command("/memory remember hello")

        self.assertIn("command_prefix: /data doctor", data)
        self.assertIn("category: data", data)
        self.assertIn("read_only: True", data)
        self.assertIn("command_prefix: /memory remember", memory)
        self.assertEqual(matched.prefix, "/memory remember")
        self.assertIn("mutates: memory", memory)
        self.assertIn("risk: medium", memory)
        self.assertIn("No command executed.", memory)

    def test_command_registry_explain_unknown_is_clean(self) -> None:
        output = format_commands_command("/commands explain /unknown command")

        self.assertIn("matched: False", output)
        self.assertIn("Command not registered.", output)
        self.assertIn("No command executed.", output)

    def test_command_registry_doctor_returns_ok(self) -> None:
        output = format_commands_command("/commands doctor")

        self.assertIn("Command Registry Doctor", output)
        self.assertIn("Status: OK", output)
        self.assertIn("Commands checked: 387", output)
        self.assertIn("natural-router references are consistent", output)
        self.assertIn("no commands were executed", output)

    def test_command_registry_doctor_detects_duplicate_and_invalid_fixture(self) -> None:
        fixture = [
            CommandSpec("invalid", "bad-category", "", True, "memory", "extreme"),
            CommandSpec("invalid", "data", "Duplicate", False, "none", "high", True),
        ]

        report = command_registry_doctor(fixture)
        messages = "\n".join(item["message"] for item in report["findings"])

        self.assertEqual(report["status"], "ERROR")
        self.assertIn("Duplicate command prefixes", messages)
        self.assertIn("must start with '/'", messages)
        self.assertIn("Empty command description", messages)
        self.assertIn("Invalid category", messages)
        self.assertIn("Invalid risk", messages)
        self.assertIn("Read-only command declares mutation", messages)
        self.assertIn("Mutating command has mutates=none", messages)
        self.assertIn("High-risk command exposed to natural router", messages)

    def test_command_registry_contains_all_natural_router_targets(self) -> None:
        registry = {spec.prefix: spec for spec in COMMAND_REGISTRY}
        natural_targets: set[str] = set()
        for target in NATURAL_COMMAND_ROUTES.values():
            natural_targets.add(target) if isinstance(target, str) else natural_targets.update(target)

        self.assertTrue(natural_targets)
        for target in natural_targets:
            with self.subTest(target=target):
                self.assertIn(target, registry)
                self.assertTrue(registry[target].available_in_natural_router)
                self.assertNotEqual(registry[target].risk, "high")

    def test_command_registry_works_through_shared_handler_without_execution(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            coordinator, _, _ = build_test_system(project_root / "proto_mind")
            logger = SessionOperatorLogger.from_project_root(project_root)
            coordinator.session_logger = logger

            output = process_interactive_input(
                "/commands explain /context injection enable",
                coordinator=coordinator,
                session_logger=logger,
                project_root=project_root,
            )

            self.assertIn("command_prefix: /context injection enable", output)
            self.assertIn("read_only: False", output)
            self.assertIn("No command executed.", output)
            self.assertFalse((project_root / "proto_mind" / "data" / "context_injection.json").exists())
            self.assertEqual(logger.status().entry_count, 0)

    def test_policy_aware_natural_explain_does_not_enable_context(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            coordinator, _, _ = build_test_system(project_root / "proto_mind")
            logger = SessionOperatorLogger.from_project_root(project_root)

            output = process_interactive_input(
                "/natural explain включи контекст",
                coordinator=coordinator,
                session_logger=logger,
                project_root=project_root,
            )

            self.assertIn("policy_class: confirmation_required", output)
            self.assertIn("target: /context injection enable", output)
            self.assertFalse((project_root / "proto_mind" / "data" / "context_injection.json").exists())
            self.assertEqual(logger.status().entry_count, 0)

    def test_unmatched_natural_input_still_uses_normal_cognitive_flow_and_logging(self) -> None:
        with TemporaryDirectory() as temp_dir:
            tmp_path = Path(temp_dir)
            logger = SessionOperatorLogger(tmp_path / "logs" / "session_operator_log.jsonl")
            coordinator, _store, _keeper = build_test_system(tmp_path)
            coordinator.session_logger = logger

            self.assertIsNone(format_natural_command("как сделать чтобы модель проверяла свою систему?", logger))
            result = coordinator.handle("как сделать чтобы модель проверяла свою систему?")

            self.assertIn("как сделать", result.response)
            self.assertEqual(logger.status().entry_count, 1)

    def test_slash_self_check_still_works_without_natural_notice(self) -> None:
        with TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "logs" / "session_operator_log.jsonl"
            log_path.parent.mkdir(parents=True)
            log_path.write_text(json.dumps({"turn_id": 1, "user_input": "Existing"}) + "\n", encoding="utf-8")
            logger = SessionOperatorLogger(log_path)

            output = format_session_log_command("/session self-check", logger)

            self.assertIsNotNone(output)
            self.assertIn("Session Self-Check", output)
            self.assertNotIn("Natural command matched", output)

    def test_cli_exit_command_aliases_are_recognized(self) -> None:
        for alias in ("exit", "quit", "q", "/exit", "/quit", "/q", "  /EXIT  ", " Quit "):
            with self.subTest(alias=alias):
                self.assertTrue(is_exit_command(alias))

    def test_cli_exit_command_does_not_use_substring_matching(self) -> None:
        for text in ("exiting", "как выйти?", "please exit after answering", "/session self-check"):
            with self.subTest(text=text):
                self.assertFalse(is_exit_command(text))

    def test_cli_exit_aliases_do_not_route_or_modify_session_log(self) -> None:
        with TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "logs" / "session_operator_log.jsonl"
            log_path.parent.mkdir(parents=True)
            log_path.write_text(json.dumps({"turn_id": 1, "user_input": "Existing"}) + "\n", encoding="utf-8")
            logger = SessionOperatorLogger(log_path)
            before_bytes = log_path.read_bytes()
            before_count = logger.status().entry_count

            self.assertTrue(is_exit_command("/exit"))
            self.assertIsNone(format_natural_command("/exit", logger))
            self.assertIsNone(format_session_log_command("/exit", logger))

            self.assertEqual(log_path.read_bytes(), before_bytes)
            self.assertEqual(logger.status().entry_count, before_count)

    def test_cli_exit_aliases_do_not_break_self_check_or_natural_router(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "exports").mkdir()
            (root / "backups").mkdir()
            log_path = root / "logs" / "session_operator_log.jsonl"
            log_path.parent.mkdir(parents=True)
            log_path.write_text(json.dumps({"turn_id": 1, "user_input": "Existing"}) + "\n", encoding="utf-8")
            logger = SessionOperatorLogger(log_path)

            slash_output = format_session_log_command("/session self-check", logger)
            natural_output = format_natural_command("check your system", logger)

            self.assertIsNotNone(slash_output)
            self.assertIn("Session Self-Check", slash_output)
            self.assertIsNotNone(natural_output)
            self.assertIn("Natural command matched: /session self-check", natural_output)

    def test_reusable_input_handler_handles_slash_and_natural_commands_without_logging(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "exports").mkdir()
            (root / "backups").mkdir()
            logger = SessionOperatorLogger(root / "logs" / "session_operator_log.jsonl")
            coordinator, _store, _keeper = build_test_system(root)
            coordinator.session_logger = logger

            slash_output = process_interactive_input(
                "/session log status",
                coordinator=coordinator,
                session_logger=logger,
                project_root=root,
            )
            natural_output = process_interactive_input(
                "проверь свою систему",
                coordinator=coordinator,
                session_logger=logger,
                project_root=root,
            )

            self.assertIn("Session operator log:", slash_output)
            self.assertIn("Natural command matched: /session self-check", natural_output)
            self.assertIn("Session Self-Check", natural_output)
            self.assertEqual(logger.status().entry_count, 0)

    def test_reusable_input_handler_normal_prompt_uses_cognitive_flow_and_logs(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            logger = SessionOperatorLogger(root / "logs" / "session_operator_log.jsonl")
            coordinator, _store, _keeper = build_test_system(root)
            coordinator.session_logger = logger

            output = process_interactive_input(
                "как сделать чтобы модель проверяла свою систему?",
                coordinator=coordinator,
                session_logger=logger,
                project_root=root,
            )

            self.assertIn("Proto-Mind:", output)
            self.assertIn("Observer:", output)
            self.assertEqual(logger.status().entry_count, 1)

    def test_reusable_input_handler_exit_alias_returns_none_without_logging(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            log_path = root / "logs" / "session_operator_log.jsonl"
            log_path.parent.mkdir(parents=True)
            log_path.write_text(json.dumps({"turn_id": 1, "user_input": "Existing"}) + "\n", encoding="utf-8")
            logger = SessionOperatorLogger(log_path)
            coordinator, _store, _keeper = build_test_system(root)
            coordinator.session_logger = logger
            before_bytes = log_path.read_bytes()

            output = process_interactive_input(
                "/exit",
                coordinator=coordinator,
                session_logger=logger,
                project_root=root,
            )

            self.assertIsNone(output)
            self.assertEqual(log_path.read_bytes(), before_bytes)
            self.assertEqual(logger.status().entry_count, 1)

    def test_generic_architecture_explanation_does_not_require_memory_grounding(self) -> None:
        state = Observer().analyze("Объясни модуль observer.")
        audit = audit_for_test(
            "Observer классифицирует запрос и извлекает topic tags.",
            user_input="Объясни модуль observer.",
            observer_state=state,
        )

        self.assertEqual(state.query_type, "meta_architecture")
        self.assertFalse(state.needs_memory)
        self.assertFalse(audit.grounding_needed)
        self.assertEqual(audit.grounding_status, "not_needed")

    def test_mock_memory_inventory_includes_active_insights(self) -> None:
        insight = MemoryRecord(
            "Запомни, что текущая цель Proto-Mind — Cognitive Continuity.",
            "insight",
            0.9,
            "test",
            tags=["current", "cognitive", "continuity"],
        )
        state = Observer().analyze("Что ты помнишь о текущей цели Proto-Mind?")

        response = MockReasoner().respond(
            "Что ты помнишь о текущей цели Proto-Mind?",
            [insight],
            state,
        )

        self.assertIn("Relevant facts", response)
        self.assertIn("Cognitive Continuity", response)

    def test_topic_extraction_prioritizes_russian_canonical_tags(self) -> None:
        tags = extract_topic_tags(
            "На самом деле теперь используем SQLite вместо JSON для хранения памяти."
        )

        self.assertEqual(
            tags,
            ["decision", "change", "historical", "current", "storage", "memory", "sqlite", "json"],
        )

    def test_russian_preference_is_stored_and_promoted_compactly(self) -> None:
        with TemporaryDirectory() as temp_dir:
            coordinator, store, _ = build_test_system(Path(temp_dir))
            result = coordinator.handle("Я предпочитаю короткие ответы.")
            working = store.load_working_memory()
            persistent = store.load_persistent_memory()

        self.assertEqual(result.observer_state.query_type, "personal_context")
        self.assertTrue(result.memory_summary.should_store)
        self.assertEqual(result.memory_summary.stored_record_type, "preference")
        self.assertTrue(any(record.content == "Я предпочитаю короткие ответы." for record in working))
        self.assertTrue(any(record.content == "Я предпочитаю короткие ответы." for record in persistent))
        self.assertTrue(all("System response:" not in record.content for record in working + persistent))

    def test_russian_decision_override_supersedes_prior_decision(self) -> None:
        with TemporaryDirectory() as temp_dir:
            coordinator, store, _ = build_test_system(Path(temp_dir))
            first = coordinator.handle("Мы решили использовать JSON для памяти Proto-Mind.")
            second = coordinator.handle(
                "На самом деле теперь используем SQLite вместо JSON для памяти Proto-Mind."
            )
            working = store.load_working_memory()
            persistent = store.load_persistent_memory()

        self.assertEqual(first.memory_summary.stored_record_type, "decision")
        self.assertTrue(second.memory_summary.override_detected)
        self.assertTrue(second.memory_summary.superseded_record_ids)
        old_records = [record for record in working + persistent if "использовать JSON" in record.content]
        new_records = [record for record in working + persistent if "теперь используем SQLite" in record.content]
        self.assertTrue(old_records)
        self.assertTrue(all(not record.active for record in old_records))
        self.assertTrue(new_records)
        self.assertTrue(all(record.active for record in new_records))

    def test_russian_preference_recall_retrieves_saved_memory(self) -> None:
        with TemporaryDirectory() as temp_dir:
            coordinator, _, _ = build_test_system(Path(temp_dir))
            coordinator.handle("Я предпочитаю короткие ответы.")
            result = coordinator.handle("Что я предпочитаю в стиле ответа?")

        self.assertEqual(result.observer_state.query_type, "memory_inventory")
        self.assertTrue(result.observer_state.needs_memory)
        self.assertTrue(result.retrieved_memory)
        self.assertEqual(result.retrieved_memory[0].type, "preference")
        self.assertIn("Я предпочитаю короткие ответы.", result.response)

    def test_russian_continuity_retrieves_project_memory_without_false_specific_tags(self) -> None:
        text = "Important fact: Proto-Mind project roadmap uses small focused patches."
        with TemporaryDirectory() as temp_dir:
            coordinator, store, _ = build_test_system(Path(temp_dir))
            coordinator.handle(text)
            before = (store.working_path.read_bytes(), store.persistent_path.read_bytes())
            result = coordinator.handle(
                "Как мы обсуждали раньше, что важно для проекта Proto-Mind?"
            )
            after = (store.working_path.read_bytes(), store.persistent_path.read_bytes())

        self.assertEqual(result.observer_state.query_type, "continuity_followup")
        self.assertTrue(result.observer_state.needs_memory)
        self.assertNotIn("важно", result.observer_state.topic_tags)
        self.assertTrue(result.retrieved_memory)
        self.assertIn(text, [record.content for record in result.retrieved_memory])
        self.assertEqual(before, after)

    def test_new_project_memory_stores_user_input_without_generated_response(self) -> None:
        text = "Important fact: Proto-Mind project roadmap uses small focused patches."
        with TemporaryDirectory() as temp_dir:
            coordinator, store, _ = build_test_system(Path(temp_dir))
            result = coordinator.handle(text)
            working = store.load_working_memory()

        self.assertTrue(result.memory_summary.should_store)
        self.assertEqual(result.memory_summary.memory_type, "project")
        self.assertEqual(result.memory_summary.content, text)
        self.assertEqual(working[0].content, text)
        self.assertNotIn("System response:", working[0].content)

    def test_store_and_promote_logic(self) -> None:
        with TemporaryDirectory() as temp_dir:
            tmp_path = Path(temp_dir)
            coordinator, store, _ = build_test_system(tmp_path)
            result = coordinator.handle("I prefer concise architectural explanations for future Proto-Mind discussions.")
            working = store.load_working_memory()
            persistent = store.load_persistent_memory()
            self.assertTrue(any(record.type == "preference" for record in working))
            self.assertTrue(any(record.type == "preference" for record in persistent))
            self.assertTrue(result.memory_summary.should_store)
            self.assertTrue(result.memory_summary.should_promote_new)
            self.assertFalse(result.memory_summary.should_promote_existing)
            self.assertTrue(result.memory_summary.promoted_record_ids)
            self.assertIn("stable preference", result.memory_summary.storage_rationale.lower())

    def test_end_to_end_pipeline_flow(self) -> None:
        with TemporaryDirectory() as temp_dir:
            tmp_path = Path(temp_dir)
            coordinator, _, _ = build_test_system(tmp_path)
            first = coordinator.handle("We decided the coordinator should orchestrate observer, memory keeper, and reasoner.")
            self.assertIn("decision", first.response.lower())
            self.assertEqual(first.reasoner_backend, "mock")

            second = coordinator.handle("As we discussed earlier, what is the coordinator responsible for?")
            self.assertTrue(second.retrieved_memory)
            self.assertTrue(
                any("coordinator should orchestrate" in record.content.lower() for record in second.retrieved_memory)
            )
            self.assertIn("relevant memory shaping this answer", second.response.lower())
            self.assertEqual(second.memory_summary.memory_type, "insight")
            self.assertTrue(second.memory_summary.tags)
            self.assertFalse(second.memory_summary.should_store)
            self.assertFalse(second.memory_summary.should_promote_new)

            persistent_payload = json.loads((tmp_path / "data" / "persistent_memory.json").read_text(encoding="utf-8"))
            self.assertTrue(persistent_payload)

    def test_preference_declaration_does_not_retrieve_unrelated_memory(self) -> None:
        with TemporaryDirectory() as temp_dir:
            tmp_path = Path(temp_dir)
            coordinator, store, _ = build_test_system(tmp_path)
            store.save_persistent_memory(
                [
                    MemoryRecord(
                        content="We decided the coordinator owns orchestration.",
                        type="decision",
                        importance=0.9,
                        source="test",
                        tags=["coordinator", "architecture"],
                        usage_count=4,
                    )
                ]
            )
            result = coordinator.handle("I prefer concise architectural explanations for future Proto-Mind discussions.")
            self.assertFalse(result.observer_state.needs_memory)
            self.assertFalse(result.retrieved_memory)
            self.assertNotIn("background memory noted", result.response.lower())

    def test_preference_behavior_query_retrieves_concise_explanation_preference(self) -> None:
        with TemporaryDirectory() as temp_dir:
            tmp_path = Path(temp_dir)
            coordinator, _, _ = build_test_system(tmp_path)
            coordinator.handle("I prefer concise architectural explanations.")
            result = coordinator.handle("How should you explain Proto-Mind later?")
            self.assertTrue(result.observer_state.needs_memory)
            self.assertTrue(result.retrieved_memory)
            self.assertEqual(result.retrieved_memory[0].type, "preference")
            self.assertIn("concise architectural explanations", result.retrieved_memory[0].content.lower())

    def test_preference_behavior_query_retrieves_short_answer_preference(self) -> None:
        with TemporaryDirectory() as temp_dir:
            tmp_path = Path(temp_dir)
            coordinator, _, _ = build_test_system(tmp_path)
            coordinator.handle("I prefer short answers.")
            result = coordinator.handle("What style should you use in future responses?")
            self.assertTrue(result.observer_state.needs_memory)
            self.assertTrue(result.retrieved_memory)
            self.assertEqual(result.retrieved_memory[0].type, "preference")
            self.assertIn("short answers", result.retrieved_memory[0].content.lower())

    def test_direct_preference_outranks_project_summary_for_response_style_query(self) -> None:
        with TemporaryDirectory() as temp_dir:
            tmp_path = Path(temp_dir)
            coordinator, store, _ = build_test_system(tmp_path)
            preference = MemoryRecord(
                "I prefer concise architectural explanations.",
                "preference",
                0.8,
                "test",
                tags=["preference", "concise", "architecture", "explanation", "response_style"],
            )
            project_summary = MemoryRecord(
                "User input: How should you explain Proto-Mind later? | System response: Proto-Mind should be explained as a local cognitive architecture.",
                "project",
                0.95,
                "test",
                tags=["project", "proto-mind", "future_behavior", "explanation", "response_style"],
                usage_count=5,
            )
            store.save_persistent_memory([project_summary, preference])

            result = coordinator.handle("How should you explain Proto-Mind later?")

            self.assertTrue(result.retrieved_memory)
            self.assertEqual(result.retrieved_memory[0].id, preference.id)
            self.assertIsNotNone(result.retrieval_trace)
            preference_trace = next(candidate for candidate in result.retrieval_trace.candidates if candidate.record_id == preference.id)
            project_trace = next(candidate for candidate in result.retrieval_trace.candidates if candidate.record_id == project_summary.id)
            self.assertGreater(preference_trace.preference_priority_contribution, 0)
            self.assertLess(project_trace.preference_priority_contribution, 0)
            self.assertIn("active direct preference", preference_trace.why_selected_summary.lower())
            self.assertTrue(any("direct preference priority" in reason for reason in preference_trace.top_reasons))

    def test_direct_preference_outranks_generic_project_memory_for_future_response_query(self) -> None:
        with TemporaryDirectory() as temp_dir:
            tmp_path = Path(temp_dir)
            coordinator, store, _ = build_test_system(tmp_path)
            preference = MemoryRecord(
                "I prefer short answers.",
                "preference",
                0.75,
                "test",
                tags=["preference", "short", "response_style"],
            )
            generic_project = MemoryRecord(
                "Proto-Mind project notes mention future responses and memory inspection.",
                "project",
                1.0,
                "test",
                tags=["project", "future_behavior", "response_style", "memory"],
                usage_count=5,
            )
            store.save_persistent_memory([generic_project, preference])

            result = coordinator.handle("What style should you use in future responses?")

            self.assertTrue(result.retrieved_memory)
            self.assertEqual(result.retrieved_memory[0].id, preference.id)
            self.assertNotEqual(result.retrieved_memory[0].id, generic_project.id)

    def test_inactive_preference_does_not_outrank_active_preference(self) -> None:
        with TemporaryDirectory() as temp_dir:
            tmp_path = Path(temp_dir)
            coordinator, store, _ = build_test_system(tmp_path)
            inactive = MemoryRecord(
                "I used to prefer verbose response style.",
                "preference",
                1.0,
                "test",
                tags=["preference", "style", "response_style"],
                usage_count=5,
                active=False,
            )
            active = MemoryRecord(
                "I prefer short answers.",
                "preference",
                0.75,
                "test",
                tags=["preference", "short", "response_style"],
            )
            store.save_persistent_memory([inactive, active])

            result = coordinator.handle("What style should you use in future responses?")

            self.assertTrue(result.retrieved_memory)
            self.assertEqual(result.retrieved_memory[0].id, active.id)

    def test_project_memory_can_appear_below_direct_preference_when_specifically_relevant(self) -> None:
        with TemporaryDirectory() as temp_dir:
            tmp_path = Path(temp_dir)
            coordinator, store, _ = build_test_system(tmp_path)
            preference = MemoryRecord(
                "I prefer concise architectural explanations.",
                "preference",
                0.8,
                "test",
                tags=["preference", "concise", "architecture", "explanation", "response_style"],
            )
            project = MemoryRecord(
                "Proto-Mind should be explained as a memory-aware cognitive architecture in future discussions.",
                "project",
                0.9,
                "test",
                tags=["project", "proto-mind", "architecture", "future_behavior", "explanation", "response_style"],
                usage_count=2,
            )
            store.save_persistent_memory([project, preference])

            result = coordinator.handle("How should you explain Proto-Mind later?")
            ids = [record.id for record in result.retrieved_memory]

            self.assertGreaterEqual(len(ids), 2)
            self.assertEqual(ids[0], preference.id)
            self.assertIn(project.id, ids[1:])

    def test_generic_non_preference_memory_does_not_beat_direct_preference_on_style_query(self) -> None:
        with TemporaryDirectory() as temp_dir:
            tmp_path = Path(temp_dir)
            coordinator, store, _ = build_test_system(tmp_path)
            preference = MemoryRecord(
                "I prefer concise architectural explanations.",
                "preference",
                0.7,
                "test",
                tags=["preference", "concise", "explanation", "response_style"],
            )
            generic = MemoryRecord(
                "Project memory: Proto-Mind has a decision log and memory commands.",
                "insight",
                1.0,
                "test",
                tags=["project", "memory", "decision"],
                usage_count=5,
            )
            store.save_persistent_memory([generic, preference])

            result = coordinator.handle("What do I prefer about explanations?")

            self.assertTrue(result.retrieved_memory)
            self.assertEqual(result.retrieved_memory[0].id, preference.id)

    def test_preference_recall_question_is_not_stored_as_new_preference(self) -> None:
        with TemporaryDirectory() as temp_dir:
            tmp_path = Path(temp_dir)
            coordinator, store, _ = build_test_system(tmp_path)
            preference = MemoryRecord(
                "I prefer concise architectural explanations.",
                "preference",
                0.8,
                "test",
                tags=["preference", "concise", "explanation", "response_style"],
            )
            store.save_persistent_memory([preference])

            result = coordinator.handle("What do I prefer about explanations?")
            persistent_preferences = [record for record in store.load_persistent_memory() if record.type == "preference"]

            self.assertTrue(result.observer_state.needs_memory)
            self.assertFalse(result.memory_summary.should_store)
            self.assertEqual([record.id for record in persistent_preferences], [preference.id])

    def test_preference_style_retrieval_question_does_not_store_project_summary(self) -> None:
        with TemporaryDirectory() as temp_dir:
            tmp_path = Path(temp_dir)
            coordinator, store, _ = build_test_system(tmp_path)
            preference = MemoryRecord(
                "I prefer concise architectural explanations.",
                "preference",
                0.8,
                "test",
                tags=["preference", "concise", "architecture", "explanation", "response_style"],
            )
            store.save_persistent_memory([preference])

            result = coordinator.handle("How should you explain Proto-Mind later?")

            self.assertTrue(result.observer_state.needs_memory)
            self.assertFalse(result.memory_summary.should_store)
            self.assertEqual([record.type for record in store.load_working_memory()], [])

    def test_store_promote_consistency_for_followup_turn(self) -> None:
        with TemporaryDirectory() as temp_dir:
            tmp_path = Path(temp_dir)
            coordinator, _, _ = build_test_system(tmp_path)
            coordinator.handle("We decided JSON storage is enough for v0.")
            result = coordinator.handle("As we discussed earlier, what storage decision did we make?")
            self.assertFalse(result.memory_summary.should_store)
            self.assertFalse(result.memory_summary.should_promote_new)
            self.assertEqual(result.memory_summary.should_promote_existing, bool(result.memory_summary.promoted_record_ids))
            self.assertIn("follow-up retrieval turn", result.memory_summary.storage_rationale.lower())
            if result.memory_summary.should_promote_existing:
                self.assertIn("promoted existing memory", result.memory_summary.promotion_rationale.lower())
            else:
                self.assertIn("no promotion happened", result.memory_summary.promotion_rationale.lower())

    def test_overriding_decision_supersedes_prior_one(self) -> None:
        with TemporaryDirectory() as temp_dir:
            tmp_path = Path(temp_dir)
            coordinator, store, _ = build_test_system(tmp_path)
            coordinator.handle("We decided JSON-backed memory is enough for v0.")
            override = coordinator.handle("Actually, we are changing direction: we now use SQLite instead of JSON.")
            persistent = store.load_persistent_memory()
            active_decisions = [record for record in persistent if record.type == "decision" and record.active]
            inactive_decisions = [record for record in persistent if record.type == "decision" and not record.active]
            self.assertTrue(any("sqlite" in record.content.lower() for record in active_decisions))
            self.assertTrue(any("json-backed memory" in record.content.lower() for record in inactive_decisions))
            self.assertTrue(override.memory_summary.override_detected)
            self.assertTrue(override.memory_summary.superseded_record_ids)

            recall = coordinator.handle("What storage system are we using now?")
            self.assertEqual(recall.observer_state.query_type, "memory_inventory")
            self.assertIn("sqlite", recall.response.lower())
            self.assertNotIn("json-backed memory is enough for v0", recall.response.lower())
            self.assertTrue(recall.retrieved_memory)
            self.assertIn("sqlite", recall.retrieved_memory[0].content.lower())

    def test_historical_decision_awareness_prefers_superseded_when_asked(self) -> None:
        with TemporaryDirectory() as temp_dir:
            tmp_path = Path(temp_dir)
            coordinator, _, _ = build_test_system(tmp_path)
            coordinator.handle("We decided Proto-Mind should use JSON-backed memory.")
            coordinator.handle("Actually, we are changing direction: Proto-Mind should use SQLite instead of JSON.")
            result = coordinator.handle("What did we use before SQLite?")
            self.assertEqual(result.observer_state.query_type, "memory_inventory")
            self.assertTrue(result.retrieved_memory)
            self.assertIsNotNone(result.retrieval_trace)
            self.assertTrue(result.retrieval_trace.historical_state_oriented)
            self.assertIn("json-backed memory", result.response.lower())

    def test_change_inventory_mentions_previous_and_current_decisions(self) -> None:
        with TemporaryDirectory() as temp_dir:
            tmp_path = Path(temp_dir)
            coordinator, _, _ = build_test_system(tmp_path)
            coordinator.handle("We decided Proto-Mind should use JSON-backed memory.")
            coordinator.handle("Actually, we are changing direction: Proto-Mind should use SQLite instead of JSON.")

            result = coordinator.handle("What did we change our mind about regarding memory storage?")

            self.assertEqual(result.observer_state.query_type, "memory_inventory")
            self.assertIn("previous decisions", result.response.lower())
            self.assertIn("current replacement decisions", result.response.lower())
            self.assertIn("json-backed memory", result.response.lower())
            self.assertIn("sqlite", result.response.lower())

    def test_russian_decision_word_does_not_look_like_not_json(self) -> None:
        active_sqlite = MemoryRecord(
            "Теперь используем SQLite вместо JSON для хранения памяти.",
            "decision",
            0.95,
            "operator",
            tags=["sqlite", "json", "storage"],
        )

        audit = audit_for_test(
            "Текущее решение JSON противоречит сохранённому направлению.",
            user_input="Какое решение сейчас активно?",
            retrieved_memory=[active_sqlite],
            persistent_memory=[active_sqlite],
        )

        self.assertEqual(audit.active_decision_status, "contradicted")

    def test_normal_no_warning_reflection_does_not_generate_carry_forward_hint(self) -> None:
        active_sqlite = MemoryRecord(
            "Actually, we are changing direction: Proto-Mind should use SQLite instead of JSON.",
            "decision",
            0.95,
            "promoted",
            tags=["sqlite", "storage"],
        )

        reflection = reflect_for_test(
            "SQLite is current.",
            retrieved_memory=[active_sqlite],
            persistent_memory=[active_sqlite],
        )

        self.assertFalse(reflection.correction_hints)
        self.assertFalse(reflection.should_carry_forward)
        self.assertEqual(reflection.carry_forward_scope, "none")

    def test_topic_phrasing_variation_retrieves_same_storage_decision(self) -> None:
        with TemporaryDirectory() as temp_dir:
            tmp_path = Path(temp_dir)
            coordinator, _, _ = build_test_system(tmp_path)
            coordinator.handle("We decided JSON-backed memory is enough for v0.")

            for query in (
                "What storage approach are we using?",
                "What memory backend did we pick?",
                "What did we decide about persistence?",
            ):
                result = coordinator.handle(query)
                self.assertTrue(result.retrieved_memory, msg=query)
                self.assertIn("json-backed memory", result.retrieved_memory[0].content.lower(), msg=query)

    def test_generic_tags_do_not_outrank_specific_storage_match(self) -> None:
        with TemporaryDirectory() as temp_dir:
            tmp_path = Path(temp_dir)
            _, store, keeper = build_test_system(tmp_path)
            store.save_persistent_memory(
                [
                    MemoryRecord(
                        content="We decided the project coordinator should orchestrate the memory flow.",
                        type="decision",
                        importance=0.95,
                        source="test",
                        tags=["decision", "memory", "project", "coordinator"],
                        usage_count=4,
                    ),
                    MemoryRecord(
                        content="We decided JSON-backed memory is enough for v0.",
                        type="decision",
                        importance=0.8,
                        source="test",
                        tags=["decision", "memory", "storage", "json"],
                        usage_count=1,
                    ),
                ]
            )
            state = Observer().analyze("What storage approach are we using?")
            retrieved = keeper.retrieve(state, top_k=2)
            self.assertTrue(retrieved)
            self.assertIn("json-backed memory", retrieved[0].content.lower())
            trace = keeper.last_retrieval_trace
            self.assertIsNotNone(trace)
            generic_candidate = next(
                candidate for candidate in trace.candidates if "project coordinator" in candidate.content_preview.lower()
            )
            self.assertIsNotNone(generic_candidate.why_not_selected_summary)
            self.assertTrue(
                "generic" in generic_candidate.why_not_selected_summary.lower()
                or "specific topical overlap" in generic_candidate.why_not_selected_summary.lower()
            )

    def test_backend_selection_from_env(self) -> None:
        with patch.dict(os.environ, {"PROTO_MIND_REASONER": "ollama"}, clear=False):
            config = ProtoMindConfig.from_env()
            reasoner = create_reasoner(config)
            self.assertIsInstance(reasoner, OllamaReasoner)

    def test_ollama_reasoner_falls_back_to_mock(self) -> None:
        config = ProtoMindConfig(reasoner_backend="ollama", ollama_model="qwen3:8b", ollama_url="http://localhost:11434")
        reasoner = OllamaReasoner(config=config)
        observer_state = Observer().analyze("As we discussed earlier, what did we decide?")
        with patch.object(OllamaReasoner, "_post", side_effect=OSError("connection refused")):
            response = reasoner.respond(
                user_input="As we discussed earlier, what did we decide?",
                retrieved_memory=[
                    MemoryRecord(
                        content="We decided to keep memory as part of reasoning.",
                        type="decision",
                        importance=0.9,
                        source="test",
                        tags=["memory", "decision"],
                    )
                ],
                observer_state=observer_state,
            )
        self.assertIn("falling back to mock reasoning", response.lower())
        self.assertIn("relevant memory shaping this answer", response.lower())

    def test_goal_status_works_when_file_missing(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)

            output = format_goal_command("/goals status", project_root=project_root)

            self.assertIsNotNone(output)
            self.assertIn("Goal Stack status:", output)
            self.assertIn("exists: False", output)
            self.assertIn("total_goals: 0", output)
            self.assertIn("focused_goal: none", output)

    def test_goal_add_creates_schema_and_list_inspect_work(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)

            output = format_goal_command("/goals add Improve memory architecture --priority high", project_root=project_root)
            stack = GoalStack.from_project_root(project_root)
            state = stack._read_state()
            goal = state.records[0]
            goal_id = goal["id"]
            list_output = format_goal_command("/goals list", project_root=project_root)
            inspect_output = format_goal_command(f"/goals inspect {goal_id}", project_root=project_root)

            self.assertIn("Goal added:", output)
            self.assertTrue(goal_id.startswith("goal_"))
            self.assertEqual(goal["title"], "Improve memory architecture")
            self.assertEqual(goal["status"], "active")
            self.assertEqual(goal["priority"], "high")
            self.assertEqual(goal["source"], "operator")
            self.assertFalse(goal["focus"])
            self.assertIn("created_at", goal)
            self.assertIn("updated_at", goal)
            self.assertIn(goal_id, list_output)
            self.assertIn("Goal:", inspect_output)
            self.assertIn("title: Improve memory architecture", inspect_output)

    def test_goal_focus_second_clears_first_focus(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            first_output = format_goal_command("/goals add First goal", project_root=project_root)
            second_output = format_goal_command("/goals add Second goal", project_root=project_root)
            first_id = next(line.strip().split(" — ")[0] for line in first_output.splitlines() if line.strip().startswith("goal_"))
            second_id = next(line.strip().split(" — ")[0] for line in second_output.splitlines() if line.strip().startswith("goal_"))

            first_focus = format_goal_command(f"/goals focus {first_id}", project_root=project_root)
            second_focus = format_goal_command(f"/goals focus {second_id}", project_root=project_root)
            records = GoalStack.from_project_root(project_root)._read_state().records
            focused_ids = [goal["id"] for goal in records if goal.get("focus")]

            self.assertIn("Focused goal:", first_focus)
            self.assertIn("Focused goal:", second_focus)
            self.assertEqual(focused_ids, [second_id])

    def test_goal_pause_complete_cancel_reopen_status_transitions(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            output = format_goal_command("/goals add Lifecycle goal", project_root=project_root)
            goal_id = next(line.strip().split(" — ")[0] for line in output.splitlines() if line.strip().startswith("goal_"))
            format_goal_command(f"/goals focus {goal_id}", project_root=project_root)

            paused = format_goal_command(f"/goals pause {goal_id}", project_root=project_root)
            paused_goal = GoalStack.from_project_root(project_root)._read_state().records[0]
            reopened = format_goal_command(f"/goals reopen {goal_id}", project_root=project_root)
            completed = format_goal_command(f"/goals complete {goal_id}", project_root=project_root)
            after_complete = GoalStack.from_project_root(project_root)._read_state().records[0]
            reopened_again = format_goal_command(f"/goals reopen {goal_id}", project_root=project_root)
            cancelled = format_goal_command(f"/goals cancel {goal_id}", project_root=project_root)
            after_cancel = GoalStack.from_project_root(project_root)._read_state().records[0]

            self.assertIn("Paused goal:", paused)
            self.assertEqual(paused_goal["status"], "paused")
            self.assertFalse(paused_goal["focus"])
            self.assertIn("Active goal:", reopened)
            self.assertIn("Completed goal:", completed)
            self.assertEqual(after_complete["status"], "completed")
            self.assertFalse(after_complete["focus"])
            self.assertIn("Active goal:", reopened_again)
            self.assertIn("Cancelled goal:", cancelled)
            self.assertEqual(after_cancel["status"], "cancelled")

    def test_goal_list_hides_terminal_status_by_default_and_all_shows_them(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            active_output = format_goal_command("/goals add Active goal", project_root=project_root)
            done_output = format_goal_command("/goals add Done goal", project_root=project_root)
            active_id = next(line.strip().split(" — ")[0] for line in active_output.splitlines() if line.strip().startswith("goal_"))
            done_id = next(line.strip().split(" — ")[0] for line in done_output.splitlines() if line.strip().startswith("goal_"))
            format_goal_command(f"/goals complete {done_id}", project_root=project_root)

            default_list = format_goal_command("/goals list", project_root=project_root)
            all_list = format_goal_command("/goals list --all", project_root=project_root)

            self.assertIn(active_id, default_list)
            self.assertNotIn(done_id, default_list)
            self.assertIn(done_id, all_list)
            self.assertIn("[completed", all_list)

    def test_goal_unknown_empty_add_and_corrupted_file_are_clean(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            stack = GoalStack.from_project_root(project_root)
            empty_add = format_goal_command("/goals add   ", project_root=project_root)
            unknown = format_goal_command("/goals focus missing", project_root=project_root)
            stack.goals_path.parent.mkdir(parents=True)
            stack.goals_path.write_text("{not json\n", encoding="utf-8")
            status = format_goal_command("/goals status", project_root=project_root)
            refused = format_goal_command("/goals add Should not overwrite corruption", project_root=project_root)

            self.assertIn("Usage: /goals add", empty_add)
            self.assertIn("Goal not found: missing", unknown)
            self.assertIn("file_health: malformed_jsonl", status)
            self.assertIn("refusing to modify", refused)
            self.assertEqual(stack.goals_path.read_text(encoding="utf-8"), "{not json\n")

    def test_goal_commands_work_through_shared_input_handler_without_session_log_turn(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            coordinator, _, _ = build_test_system(project_root)
            logger = SessionOperatorLogger.from_project_root(project_root)
            coordinator.session_logger = logger

            output = process_interactive_input(
                "/goals add Shared handler goal",
                coordinator=coordinator,
                session_logger=logger,
                project_root=project_root,
            )
            status = process_interactive_input(
                "/goals status",
                coordinator=coordinator,
                session_logger=logger,
                project_root=project_root,
            )

            self.assertIn("Goal added:", output)
            self.assertIn("total_goals: 1", status)
            self.assertEqual(logger.status().entry_count, 0)

    def test_task_status_works_when_file_missing(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)

            output = format_task_command("/tasks status", project_root=project_root)

            self.assertIsNotNone(output)
            self.assertIn("Task Queue status:", output)
            self.assertIn("exists: False", output)
            self.assertIn("total_tasks: 0", output)
            self.assertIn("next_task: none", output)

    def test_task_add_creates_schema_and_list_inspect_work(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)

            output = format_task_command("/tasks add Implement task queue --priority high", project_root=project_root)
            queue = TaskQueue.from_project_root(project_root)
            state = queue._read_state()
            task = state.records[0]
            task_id = task["id"]
            list_output = format_task_command("/tasks list", project_root=project_root)
            inspect_output = format_task_command(f"/tasks inspect {task_id}", project_root=project_root)

            self.assertIn("Task added:", output)
            self.assertTrue(task_id.startswith("task_"))
            self.assertEqual(task["title"], "Implement task queue")
            self.assertEqual(task["status"], "open")
            self.assertEqual(task["priority"], "high")
            self.assertEqual(task["source"], "operator")
            self.assertIsNone(task["goal_id"])
            self.assertIn("created_at", task)
            self.assertIn("updated_at", task)
            self.assertIn(task_id, list_output)
            self.assertIn("Task:", inspect_output)
            self.assertIn("title: Implement task queue", inspect_output)

    def test_task_next_priority_ordering_prefers_in_progress_then_priority(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            low_output = format_task_command("/tasks add Low task --priority low", project_root=project_root)
            normal_output = format_task_command("/tasks add Normal task", project_root=project_root)
            high_output = format_task_command("/tasks add High task --priority high", project_root=project_root)
            low_id = next(line.strip().split(" — ")[0] for line in low_output.splitlines() if line.strip().startswith("task_"))
            normal_id = next(line.strip().split(" — ")[0] for line in normal_output.splitlines() if line.strip().startswith("task_"))
            high_id = next(line.strip().split(" — ")[0] for line in high_output.splitlines() if line.strip().startswith("task_"))

            next_high = format_task_command("/tasks next", project_root=project_root)
            format_task_command(f"/tasks start {normal_id}", project_root=project_root)
            next_started = format_task_command("/tasks next", project_root=project_root)

            self.assertIn(high_id, next_high)
            self.assertIn(normal_id, next_started)
            self.assertNotIn(low_id, next_high.split("Next task:", 1)[1])

    def test_task_lifecycle_start_block_unblock_done_cancel_reopen(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            output = format_task_command("/tasks add Lifecycle task", project_root=project_root)
            task_id = next(line.strip().split(" — ")[0] for line in output.splitlines() if line.strip().startswith("task_"))

            started = format_task_command(f"/tasks start {task_id}", project_root=project_root)
            blocked = format_task_command(f"/tasks block {task_id} waiting for limits", project_root=project_root)
            blocked_task = TaskQueue.from_project_root(project_root)._read_state().records[0]
            unblocked = format_task_command(f"/tasks unblock {task_id}", project_root=project_root)
            unblocked_task = TaskQueue.from_project_root(project_root)._read_state().records[0]
            done = format_task_command(f"/tasks done {task_id} implemented and tested", project_root=project_root)
            done_task = TaskQueue.from_project_root(project_root)._read_state().records[0]
            reopened = format_task_command(f"/tasks reopen {task_id}", project_root=project_root)
            cancelled = format_task_command(f"/tasks cancel {task_id}", project_root=project_root)
            cancelled_task = TaskQueue.from_project_root(project_root)._read_state().records[0]

            self.assertIn("Started task:", started)
            self.assertIn("Blocked task:", blocked)
            self.assertEqual(blocked_task["status"], "blocked")
            self.assertEqual(blocked_task["blocked_reason"], "waiting for limits")
            self.assertIn("Unblocked task:", unblocked)
            self.assertEqual(unblocked_task["status"], "open")
            self.assertEqual(unblocked_task["blocked_reason"], "")
            self.assertIn("Done task:", done)
            self.assertEqual(done_task["status"], "done")
            self.assertEqual(done_task["result"], "implemented and tested")
            self.assertIn("Reopened task:", reopened)
            self.assertIn("Cancelled task:", cancelled)
            self.assertEqual(cancelled_task["status"], "cancelled")

    def test_task_list_hides_done_cancelled_by_default_and_all_shows_them(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            active_output = format_task_command("/tasks add Active task", project_root=project_root)
            done_output = format_task_command("/tasks add Done task", project_root=project_root)
            cancelled_output = format_task_command("/tasks add Cancelled task", project_root=project_root)
            active_id = next(line.strip().split(" — ")[0] for line in active_output.splitlines() if line.strip().startswith("task_"))
            done_id = next(line.strip().split(" — ")[0] for line in done_output.splitlines() if line.strip().startswith("task_"))
            cancelled_id = next(line.strip().split(" — ")[0] for line in cancelled_output.splitlines() if line.strip().startswith("task_"))
            format_task_command(f"/tasks done {done_id}", project_root=project_root)
            format_task_command(f"/tasks cancel {cancelled_id}", project_root=project_root)

            default_list = format_task_command("/tasks list", project_root=project_root)
            all_list = format_task_command("/tasks list --all", project_root=project_root)

            self.assertIn(active_id, default_list)
            self.assertNotIn(done_id, default_list)
            self.assertNotIn(cancelled_id, default_list)
            self.assertIn(done_id, all_list)
            self.assertIn(cancelled_id, all_list)
            self.assertIn("[done]", all_list)
            self.assertIn("[cancelled]", all_list)

    def test_task_unknown_empty_block_and_corrupted_file_are_clean(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            queue = TaskQueue.from_project_root(project_root)
            empty_add = format_task_command("/tasks add   ", project_root=project_root)
            unknown = format_task_command("/tasks start missing", project_root=project_root)
            block_without_reason = format_task_command("/tasks block missing", project_root=project_root)
            queue.tasks_path.parent.mkdir(parents=True)
            queue.tasks_path.write_text("{not json\n", encoding="utf-8")
            status = format_task_command("/tasks status", project_root=project_root)
            refused = format_task_command("/tasks add Should not overwrite corruption", project_root=project_root)

            self.assertIn("Usage: /tasks add", empty_add)
            self.assertIn("Task not found: missing", unknown)
            self.assertIn("Usage: /tasks block <id> <reason>", block_without_reason)
            self.assertIn("file_health: malformed_jsonl", status)
            self.assertIn("refusing to modify", refused)
            self.assertEqual(queue.tasks_path.read_text(encoding="utf-8"), "{not json\n")

    def test_task_goal_link_and_goal_filter(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            goal_output = format_goal_command("/goals add Improve Proto-Mind architecture", project_root=project_root)
            goal_id = next(line.strip().split(" — ")[0] for line in goal_output.splitlines() if line.strip().startswith("goal_"))

            linked_output = format_task_command(
                f"/tasks add Build task queue integration --goal {goal_id}",
                project_root=project_root,
            )
            unlinked_output = format_task_command("/tasks add Other task", project_root=project_root)
            linked_id = next(line.strip().split(" — ")[0] for line in linked_output.splitlines() if line.strip().startswith("task_"))
            unlinked_id = next(line.strip().split(" — ")[0] for line in unlinked_output.splitlines() if line.strip().startswith("task_"))
            filtered = format_task_command(f"/tasks list --goal {goal_id}", project_root=project_root)
            inspect = format_task_command(f"/tasks inspect {linked_id}", project_root=project_root)
            missing_goal = format_task_command("/tasks add Bad link --goal missing_goal", project_root=project_root)

            self.assertIn(f"goal={goal_id}", linked_output)
            self.assertIn(linked_id, filtered)
            self.assertNotIn(unlinked_id, filtered)
            self.assertIn(f"goal_id: {goal_id}", inspect)
            self.assertIn("Goal not found: missing_goal", missing_goal)

    def test_task_commands_work_through_shared_input_handler_without_session_log_turn(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            coordinator, _, _ = build_test_system(project_root)
            logger = SessionOperatorLogger.from_project_root(project_root)
            coordinator.session_logger = logger

            output = process_interactive_input(
                "/tasks add Shared handler task",
                coordinator=coordinator,
                session_logger=logger,
                project_root=project_root,
            )
            status = process_interactive_input(
                "/tasks status",
                coordinator=coordinator,
                session_logger=logger,
                project_root=project_root,
            )

            self.assertIn("Task added:", output)
            self.assertIn("total_tasks: 1", status)
            self.assertEqual(logger.status().entry_count, 0)

    def test_experiment_status_works_when_file_missing(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)

            output = format_experiment_command("/experiments status", project_root=project_root)

            self.assertIsNotNone(output)
            self.assertIn("Experiment Journal status:", output)
            self.assertIn("exists: False", output)
            self.assertIn("total_experiments: 0", output)
            self.assertIn("latest_experiment: none", output)

    def test_experiment_start_creates_schema_and_list_inspect_work(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)

            output = format_experiment_command("/experiments start Check markdown fix", project_root=project_root)
            journal = ExperimentJournal.from_project_root(project_root)
            state = journal._read_state()
            experiment = state.records[0]
            experiment_id = experiment["id"]
            list_output = format_experiment_command("/experiments list", project_root=project_root)
            inspect_output = format_experiment_command(f"/experiments inspect {experiment_id}", project_root=project_root)

            self.assertIn("Experiment started:", output)
            self.assertTrue(experiment_id.startswith("exp_"))
            self.assertEqual(experiment["title"], "Check markdown fix")
            self.assertEqual(experiment["status"], "open")
            self.assertEqual(experiment["source"], "operator")
            self.assertIn("created_at", experiment)
            self.assertIn("updated_at", experiment)
            self.assertIn(experiment_id, list_output)
            self.assertIn("Experiment:", inspect_output)
            self.assertIn("title: Check markdown fix", inspect_output)

    def test_experiment_fields_and_status_cycle(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            output = format_experiment_command("/experiments start Learning cycle", project_root=project_root)
            experiment_id = next(line.strip().split(" — ")[0] for line in output.splitlines() if line.strip().startswith("exp_"))

            hypothesis = format_experiment_command(
                f"/experiments hypothesis {experiment_id} Experiment Journal will store hypothesis cleanly.",
                project_root=project_root,
            )
            prediction = format_experiment_command(
                f"/experiments predict {experiment_id} Commands should work through shared handler.",
                project_root=project_root,
            )
            method = format_experiment_command(f"/experiments method {experiment_id} Run CLI smoke and unit tests.", project_root=project_root)
            running = format_experiment_command(f"/experiments run {experiment_id}", project_root=project_root)
            result = format_experiment_command(f"/experiments result {experiment_id} CLI smoke passed.", project_root=project_root)
            reflection = format_experiment_command(
                f"/experiments reflect {experiment_id} Experiment flow is useful for learning cycles.",
                project_root=project_root,
            )
            lesson = format_experiment_command(
                f"/experiments lesson {experiment_id} Hypothesis-result-lesson can support future world-model-lite.",
                project_root=project_root,
            )
            completed = format_experiment_command(f"/experiments complete {experiment_id}", project_root=project_root)
            record = ExperimentJournal.from_project_root(project_root)._read_state().records[0]

            self.assertIn("Hypothesis updated:", hypothesis)
            self.assertIn("Prediction updated:", prediction)
            self.assertIn("Method updated:", method)
            self.assertIn("Running experiment:", running)
            self.assertIn("Result updated:", result)
            self.assertIn("Reflection updated:", reflection)
            self.assertIn("Lesson updated:", lesson)
            self.assertIn("Completed experiment:", completed)
            self.assertEqual(record["status"], "completed")
            self.assertIn("store hypothesis", record["hypothesis"])
            self.assertIn("shared handler", record["prediction"])
            self.assertIn("unit tests", record["method"])
            self.assertIn("CLI smoke", record["result"])
            self.assertIn("learning cycles", record["reflection"])
            self.assertIn("world-model-lite", record["lesson"])

    def test_experiment_inconclusive_cancel_reopen_and_list_visibility(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            first_output = format_experiment_command("/experiments start First experiment", project_root=project_root)
            second_output = format_experiment_command("/experiments start Second experiment", project_root=project_root)
            third_output = format_experiment_command("/experiments start Third experiment", project_root=project_root)
            first_id = next(line.strip().split(" — ")[0] for line in first_output.splitlines() if line.strip().startswith("exp_"))
            second_id = next(line.strip().split(" — ")[0] for line in second_output.splitlines() if line.strip().startswith("exp_"))
            third_id = next(line.strip().split(" — ")[0] for line in third_output.splitlines() if line.strip().startswith("exp_"))

            inconclusive = format_experiment_command(f"/experiments inconclusive {first_id}", project_root=project_root)
            cancelled = format_experiment_command(f"/experiments cancel {second_id}", project_root=project_root)
            reopened = format_experiment_command(f"/experiments reopen {first_id}", project_root=project_root)
            default_list = format_experiment_command("/experiments list", project_root=project_root)
            all_list = format_experiment_command("/experiments list --all", project_root=project_root)

            self.assertIn("Inconclusive experiment:", inconclusive)
            self.assertIn("Cancelled experiment:", cancelled)
            self.assertIn("Reopened experiment:", reopened)
            self.assertIn(first_id, default_list)
            self.assertIn(third_id, default_list)
            self.assertNotIn(second_id, default_list)
            self.assertIn(second_id, all_list)
            self.assertIn("[cancelled]", all_list)

    def test_experiment_unknown_empty_and_corrupted_file_are_clean(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            journal = ExperimentJournal.from_project_root(project_root)
            empty_start = format_experiment_command("/experiments start   ", project_root=project_root)
            unknown = format_experiment_command("/experiments run missing", project_root=project_root)
            missing_text = format_experiment_command("/experiments result missing", project_root=project_root)
            journal.experiments_path.parent.mkdir(parents=True)
            journal.experiments_path.write_text("{not json\n", encoding="utf-8")
            status = format_experiment_command("/experiments status", project_root=project_root)
            refused = format_experiment_command("/experiments start Should not overwrite corruption", project_root=project_root)

            self.assertIn("Usage: /experiments start", empty_start)
            self.assertIn("Experiment not found: missing", unknown)
            self.assertIn("Usage: /experiments result <id> <text>", missing_text)
            self.assertIn("file_health: malformed_jsonl", status)
            self.assertIn("refusing to modify", refused)
            self.assertEqual(journal.experiments_path.read_text(encoding="utf-8"), "{not json\n")

    def test_experiment_goal_task_links_and_filters(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            goal_output = format_goal_command("/goals add Improve Proto-Mind architecture", project_root=project_root)
            goal_id = next(line.strip().split(" — ")[0] for line in goal_output.splitlines() if line.strip().startswith("goal_"))
            task_output = format_task_command(f"/tasks add Build experiment integration --goal {goal_id}", project_root=project_root)
            task_id = next(line.strip().split(" — ")[0] for line in task_output.splitlines() if line.strip().startswith("task_"))

            linked_output = format_experiment_command(
                f"/experiments start Check experiment links --goal {goal_id} --task {task_id}",
                project_root=project_root,
            )
            other_output = format_experiment_command("/experiments start Other experiment", project_root=project_root)
            linked_id = next(line.strip().split(" — ")[0] for line in linked_output.splitlines() if line.strip().startswith("exp_"))
            other_id = next(line.strip().split(" — ")[0] for line in other_output.splitlines() if line.strip().startswith("exp_"))
            by_goal = format_experiment_command(f"/experiments list --goal {goal_id}", project_root=project_root)
            by_task = format_experiment_command(f"/experiments list --task {task_id}", project_root=project_root)
            inspect = format_experiment_command(f"/experiments inspect {linked_id}", project_root=project_root)
            missing_goal = format_experiment_command("/experiments start Bad goal --goal missing_goal", project_root=project_root)
            missing_task = format_experiment_command("/experiments start Bad task --task missing_task", project_root=project_root)
            complete_linked = format_experiment_command(f"/experiments complete {linked_id}", project_root=project_root)

            self.assertIn(f"goal={goal_id}", linked_output)
            self.assertIn(f"task={task_id}", linked_output)
            self.assertIn(linked_id, by_goal)
            self.assertNotIn(other_id, by_goal)
            self.assertIn(linked_id, by_task)
            self.assertNotIn(other_id, by_task)
            self.assertIn(f"goal_id: {goal_id}", inspect)
            self.assertIn(f"task_id: {task_id}", inspect)
            self.assertIn("Goal not found: missing_goal", missing_goal)
            self.assertIn("Task not found: missing_task", missing_task)
            self.assertIn(f"Linked task: {task_id}", complete_linked)

    def test_experiment_commands_work_through_shared_input_handler_without_session_log_turn(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            coordinator, _, _ = build_test_system(project_root)
            logger = SessionOperatorLogger.from_project_root(project_root)
            coordinator.session_logger = logger

            output = process_interactive_input(
                "/experiments start Shared handler experiment",
                coordinator=coordinator,
                session_logger=logger,
                project_root=project_root,
            )
            status = process_interactive_input(
                "/experiments status",
                coordinator=coordinator,
                session_logger=logger,
                project_root=project_root,
            )

            self.assertIn("Experiment started:", output)
            self.assertIn("total_experiments: 1", status)
            self.assertEqual(logger.status().entry_count, 0)

    def test_identity_status_initializes_defaults_and_show_displays_profile(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            store = IdentityStore.from_project_root(project_root)

            status = format_identity_command("/identity status", project_root=project_root)
            show = format_identity_command("/identity show", project_root=project_root)

            self.assertTrue(store.identity_path.exists())
            self.assertIn("Identity / Values status:", status)
            self.assertIn("version: 1", status)
            self.assertIn("name: Proto-Mind", status)
            self.assertIn("values_count: 4", status)
            self.assertIn("principles_count: 3", status)
            self.assertIn("boundaries_count: 2", status)
            self.assertIn("Identity / Values", show)
            self.assertIn("personal cognitive agent and operational partner", show)
            self.assertIn("style: adaptive to the operator and current conversation", show)
            self.assertIn("Operator goals, continuity, and useful outcomes matter.", show)
            self.assertIn("Use the selected access mode confidently", show)
            self.assertIn("Respect explicit operator stop, read-only, and scope constraints.", show)
            self.assertNotIn("Local-first by default.", show)
            self.assertNotIn("Prefer deterministic diagnostics before auto-fixes.", show)
            self.assertNotIn("Keep CLI, Desktop UI, and tests stable.", show)
            self.assertNotIn("No hidden memory edits.", show)
            self.assertNotIn("No autonomous shell execution.", show)
            self.assertNotIn("Suggest commands rather than silently mutating state.", show)

    def test_identity_set_add_archive_restore_history_and_doctor(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)

            set_style = format_identity_command("/identity set style concise, careful, brotherly", project_root=project_root)
            invalid = format_identity_command("/identity set bad_field nope", project_root=project_root)
            value = format_identity_command("/identity add-value Keep operator reports compact when possible.", project_root=project_root)
            principle = format_identity_command("/identity add-principle Checkpoint first.", project_root=project_root)
            boundary = format_identity_command("/identity add-boundary No surprise network actions.", project_root=project_root)
            value_id = next(line.strip().split(" — ")[0] for line in value.splitlines() if line.strip().startswith("val_"))
            principle_id = next(line.strip().split(" — ")[0] for line in principle.splitlines() if line.strip().startswith("pr_"))
            boundary_id = next(line.strip().split(" — ")[0] for line in boundary.splitlines() if line.strip().startswith("bnd_"))

            archived = format_identity_command(f"/identity archive {value_id}", project_root=project_root)
            restored = format_identity_command(f"/identity restore {value_id}", project_root=project_root)
            history = format_identity_command("/identity history --limit 1", project_root=project_root)
            show = format_identity_command("/identity show", project_root=project_root)
            doctor = format_identity_command("/identity doctor", project_root=project_root)

            self.assertIn("style: concise, careful, brotherly", set_style)
            self.assertIn("Allowed fields:", invalid)
            self.assertIn(value_id, archived)
            self.assertIn(value_id, restored)
            self.assertIn("Identity history: last 1", history)
            self.assertIn("restore", history)
            self.assertIn(value_id, show)
            self.assertIn(principle_id, show)
            self.assertIn(boundary_id, show)
            self.assertIn("Identity Doctor", doctor)
            self.assertIn("Status: OK", doctor)

    def test_identity_doctor_detects_duplicates_empty_text_and_corruption(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            store = IdentityStore.from_project_root(project_root)
            format_identity_command("/identity status", project_root=project_root)
            data = json.loads(store.identity_path.read_text(encoding="utf-8"))
            data["values"].append({"id": "val_dup1", "text": "Duplicate value.", "created_at": "2026-06-26T10:00:00+00:00", "active": True})
            data["values"].append({"id": "val_dup2", "text": "duplicate value", "created_at": "2026-06-26T10:00:00+00:00", "active": True})
            data["principles"].append({"id": "pr_empty", "text": "", "created_at": "2026-06-26T10:00:00+00:00", "active": True})
            store.identity_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

            doctor = format_identity_command("/identity doctor", project_root=project_root)
            before = store.identity_path.read_bytes()
            doctor_again = format_identity_command("/identity doctor", project_root=project_root)
            after = store.identity_path.read_bytes()

            self.assertIn("Status: WARN", doctor)
            self.assertIn("Duplicate active values", doctor)
            self.assertIn("Empty text in principles: pr_empty", doctor)
            self.assertEqual(before, after)
            self.assertIn("Status: WARN", doctor_again)

            store.identity_path.write_text("{not json\n", encoding="utf-8")
            corrupted = format_identity_command("/identity doctor", project_root=project_root)
            refused = format_identity_command("/identity add-value Should not overwrite corruption", project_root=project_root)
            self.assertIn("Status: ERROR", corrupted)
            self.assertIn("Identity error:", refused)
            self.assertEqual(store.identity_path.read_text(encoding="utf-8"), "{not json\n")

    def test_identity_commands_work_through_shared_input_handler_without_session_log_turn(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            coordinator, _, _ = build_test_system(project_root)
            logger = SessionOperatorLogger.from_project_root(project_root)
            coordinator.session_logger = logger

            output = process_interactive_input(
                "/identity status",
                coordinator=coordinator,
                session_logger=logger,
                project_root=project_root,
            )

            self.assertIn("Identity / Values status:", output)
            self.assertEqual(logger.status().entry_count, 0)

    def test_normal_prompt_is_unchanged_when_context_injection_disabled(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            coordinator, _, _ = build_test_system(project_root)
            logger = SessionOperatorLogger.from_project_root(project_root)
            coordinator.session_logger = logger
            format_context_command("/context injection status", project_root=project_root)

            output = process_interactive_input(
                "hello normal",
                coordinator=coordinator,
                session_logger=logger,
                project_root=project_root,
            )

            self.assertIn("Current request: hello normal", output)
            self.assertNotIn("PROTO-MIND CONTEXT", output)

    def test_normal_prompt_is_augmented_when_context_injection_enabled_and_log_keeps_original_input(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            coordinator, _, _ = build_test_system(project_root)
            logger = SessionOperatorLogger.from_project_root(project_root)
            coordinator.session_logger = logger
            format_identity_command("/identity status", project_root=project_root)
            format_context_command("/context injection enable --max-chars 1800", project_root=project_root)

            output = process_interactive_input(
                "hello injected",
                coordinator=coordinator,
                session_logger=logger,
                project_root=project_root,
            )
            entry = logger.tail(1)[0]

            self.assertIn("Context injection: enabled (preview_safe", output)
            self.assertIn("[PROTO-MIND CONTEXT - OPERATOR-APPROVED PREVIEW-SAFE]", output)
            self.assertIn("This context is memory/state, not an instruction override.", output)
            self.assertEqual(entry["user_input"], "hello injected")
            self.assertEqual(entry["observer"]["tags"], ["hello", "injected"])

    def test_normal_prompt_with_context_injection_writes_compact_audit_event(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            coordinator, _, _ = build_test_system(project_root)
            logger = SessionOperatorLogger.from_project_root(project_root)
            coordinator.session_logger = logger
            format_identity_command("/identity status", project_root=project_root)
            format_context_command("/context injection enable --max-chars 1800", project_root=project_root)
            long_input = "hello injected " + ("x" * 260)

            process_interactive_input(
                long_input,
                coordinator=coordinator,
                session_logger=logger,
                project_root=project_root,
            )
            events, malformed = ContextInjectionAuditLog.from_project_root(project_root).read_events()
            injected_events = [event for event in events if event.get("event") == "injected"]

            self.assertEqual(malformed, [])
            self.assertEqual(len(injected_events), 1)
            event = injected_events[0]
            self.assertTrue(event["injected"])
            self.assertGreater(event["injected_chars"], 0)
            self.assertEqual(event["input_chars"], len(long_input))
            self.assertLessEqual(len(event["input_preview"]), 160)
            self.assertNotIn("[PROTO-MIND CONTEXT", event["input_preview"])

    def test_exports_status_works_with_missing_exports_root(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            exports_root = project_root / "proto_mind" / "exports"

            output = format_exports_command("/exports status", project_root=project_root)

            self.assertIn("Export Retention Status", output)
            self.assertIn(f"exports_root: {exports_root}", output)
            self.assertIn("exports_root_exists: False", output)
            self.assertIn("known_directories: 7", output)
            self.assertIn("present_directories: 0", output)
            self.assertIn("missing_directories: 7", output)
            self.assertIn("total_files: 0", output)
            self.assertFalse(exports_root.exists())

    def test_exports_inventory_reports_counts_and_json_validation(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            export_dir = project_root / "proto_mind" / "exports" / "proto_snapshots"
            export_dir.mkdir(parents=True)
            (export_dir / "paired.md").write_text("# Snapshot\n", encoding="utf-8")
            (export_dir / "paired.json").write_text(json.dumps({"status": "OK"}), encoding="utf-8")

            output = format_exports_command("/exports inventory", project_root=project_root)
            cleanup = format_exports_command("/exports cleanup-preview", project_root=project_root)

            self.assertIn("Export Inventory", output)
            self.assertIn("proto_snapshots:", output)
            self.assertIn("files: 2 (md=1, json=1, other=0)", output)
            self.assertIn("newest_json_validation: valid", output)
            self.assertIn("context_packs:", output)
            self.assertIn("exists: False", output)
            self.assertIn("No retention action suggested; directory is small and healthy.", cleanup)

    def test_exports_cleanup_preview_warns_for_many_files_and_is_read_only(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            export_dir = project_root / "proto_mind" / "exports" / "action_queue"
            export_dir.mkdir(parents=True)
            for index in range(MANY_FILES_THRESHOLD + 1):
                (export_dir / f"report_{index}.txt").write_text(str(index), encoding="utf-8")
            before = {path.name: path.read_bytes() for path in export_dir.iterdir()}

            output = format_exports_command("/exports cleanup-preview", project_root=project_root)

            self.assertIn("Export Cleanup Preview", output)
            self.assertIn("Directory is large", output)
            self.assertIn("keeping the newest 10 complete pairs", output)
            self.assertIn("/action queue-export", output)
            self.assertNotIn("rm ", output)
            self.assertNotIn("mv ", output)
            after = {path.name: path.read_bytes() for path in export_dir.iterdir()}
            self.assertEqual(after, before)

    def test_exports_doctor_detects_invalid_json_and_orphan_pairs(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            snapshots = project_root / "proto_mind" / "exports" / "proto_snapshots"
            diffs = project_root / "proto_mind" / "exports" / "proto_snapshot_diffs"
            snapshots.mkdir(parents=True)
            diffs.mkdir(parents=True)
            (snapshots / "orphan_markdown.md").write_text("# orphan\n", encoding="utf-8")
            (snapshots / "invalid_only.json").write_text("{invalid", encoding="utf-8")
            (diffs / "pair.md").write_text("# pair\n", encoding="utf-8")
            (diffs / "pair.json").write_text(json.dumps({"no_mutation": True}), encoding="utf-8")

            output = format_exports_command("/exports doctor", project_root=project_root)

            self.assertIn("Export Retention Doctor", output)
            self.assertIn("Status: WARN", output)
            self.assertIn("Invalid JSON export in proto_snapshots", output)
            self.assertIn("Orphan Markdown export in proto_snapshots: orphan_markdown.md", output)
            self.assertIn("Orphan JSON export in proto_snapshots: invalid_only.json", output)
            self.assertIn("invalid JSON files: 1", output)

    def test_exports_commands_are_read_only_through_shared_handler(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            coordinator, store, _ = build_test_system(project_root / "proto_mind")
            store.save_persistent_memory([])
            logger = SessionOperatorLogger.from_project_root(project_root)
            coordinator.session_logger = logger
            format_context_command("/context injection enable", project_root=project_root)
            export_dir = project_root / "proto_mind" / "exports" / "proto_snapshots"
            export_dir.mkdir(parents=True)
            (export_dir / "pair.md").write_text("# pair\n", encoding="utf-8")
            (export_dir / "pair.json").write_text(json.dumps({"status": "OK"}), encoding="utf-8")
            data_dir = project_root / "proto_mind" / "data"
            before_data = {path.name: path.read_bytes() for path in data_dir.glob("*") if path.is_file()}
            before_exports = {path.name: path.read_bytes() for path in export_dir.iterdir()}

            outputs = [
                process_interactive_input(
                    command,
                    coordinator=coordinator,
                    session_logger=logger,
                    project_root=project_root,
                )
                for command in (
                    "/exports status",
                    "/exports inventory",
                    "/exports cleanup-preview",
                    "/exports doctor",
                )
            ]

            self.assertIn("Export Retention Status", outputs[0])
            self.assertIn("Export Inventory", outputs[1])
            self.assertIn("Export Cleanup Preview", outputs[2])
            self.assertIn("Export Retention Doctor", outputs[3])
            after_data = {path.name: path.read_bytes() for path in data_dir.glob("*") if path.is_file()}
            after_exports = {path.name: path.read_bytes() for path in export_dir.iterdir()}
            self.assertEqual(after_data, before_data)
            self.assertEqual(after_exports, before_exports)
            self.assertEqual(logger.status().entry_count, 0)

    def test_daily_status_reports_registry_exports_snapshots_context_and_baseline(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            _create_healthy_export_dirs(project_root)
            (project_root / "PROTO_MIND_ARCHITECT_LEDGER.md").write_text(
                "- Current test count: 438 unit tests OK.\n", encoding="utf-8"
            )

            output = format_daily_command("/daily status", project_root=project_root, memory_store=store)

            self.assertIn("Daily Agent Status", output)
            self.assertIn(f"project_root: {project_root}", output)
            self.assertIn("command_registry: commands=387 categories=41", output)
            self.assertIn("known_export_dirs: present=7/7", output)
            self.assertIn("latest_snapshot: daily_fixture.json", output)
            self.assertIn("latest_snapshot_diff: daily_fixture.json", output)
            self.assertIn("context_injection: disabled", output)
            self.assertIn("test_baseline: 438 tests OK (Architect Ledger; not re-run by this command)", output)

    def test_daily_brief_is_deterministic_local_and_read_only(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            store.save_persistent_memory([])
            _create_healthy_export_dirs(project_root)
            data_dir = project_root / "proto_mind" / "data"
            before_data = {path.name: path.read_bytes() for path in data_dir.glob("*") if path.is_file()}
            before_exports = {
                str(path.relative_to(project_root)): path.read_bytes()
                for path in (project_root / "proto_mind" / "exports").rglob("*")
                if path.is_file()
            }

            output = format_daily_command("/daily brief", project_root=project_root, memory_store=store)

            self.assertIn("Daily Operating Brief", output)
            self.assertIn("System health:", output)
            self.assertIn("Export health: OK", output)
            self.assertIn("Context injection: disabled", output)
            self.assertIn("Snapshot / Diff:", output)
            self.assertIn("Recent notable warnings:", output)
            self.assertIn("Current deterministic focus:", output)
            self.assertIn("Safe focus for next work session:", output)
            self.assertIn("no LLM/API call", output)
            after_data = {path.name: path.read_bytes() for path in data_dir.glob("*") if path.is_file()}
            after_exports = {
                str(path.relative_to(project_root)): path.read_bytes()
                for path in (project_root / "proto_mind" / "exports").rglob("*")
                if path.is_file()
            }
            self.assertEqual(after_data, before_data)
            self.assertEqual(after_exports, before_exports)

    def test_daily_doctor_returns_ok_for_healthy_read_only_layer(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            _create_healthy_export_dirs(project_root)

            output = format_daily_command("/daily doctor", project_root=project_root, memory_store=store)

            self.assertIn("Daily Agent Doctor", output)
            self.assertIn("Status: OK", output)
            self.assertIn("All required daily commands are registered", output)
            self.assertIn("Export Retention module is reachable", output)
            self.assertIn("Snapshot and diff inspection commands are reachable", output)
            self.assertIn("Context Injection is disabled", output)
            self.assertIn("No deletion, move, repair, compression", output)

    def test_daily_doctor_warns_but_does_not_change_explicit_context_setting(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            _create_healthy_export_dirs(project_root)
            format_context_command("/context injection enable", project_root=project_root)
            settings_path = project_root / "proto_mind" / "data" / "context_injection.json"
            before = settings_path.read_bytes()

            output = format_daily_command("/daily doctor", project_root=project_root, memory_store=store)

            self.assertIn("Status: WARN", output)
            self.assertIn("Context Injection is enabled by operator configuration", output)
            self.assertEqual(settings_path.read_bytes(), before)
            self.assertTrue(json.loads(settings_path.read_text(encoding="utf-8"))["enabled"])

    def test_daily_commands_are_read_only_through_shared_handler_and_next_is_manual(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            coordinator, store, _ = build_test_system(project_root / "proto_mind")
            store.save_persistent_memory([])
            logger = SessionOperatorLogger.from_project_root(project_root)
            coordinator.session_logger = logger
            _create_healthy_export_dirs(project_root)
            format_context_command("/context injection disable", project_root=project_root)
            data_dir = project_root / "proto_mind" / "data"
            exports_root = project_root / "proto_mind" / "exports"
            before_data = {path.name: path.read_bytes() for path in data_dir.glob("*") if path.is_file()}
            before_exports = {
                str(path.relative_to(exports_root)): path.read_bytes()
                for path in exports_root.rglob("*")
                if path.is_file()
            }

            outputs = [
                process_interactive_input(
                    command,
                    coordinator=coordinator,
                    session_logger=logger,
                    project_root=project_root,
                )
                for command in ("/daily status", "/daily brief", "/daily doctor", "/daily next")
            ]

            self.assertIn("Daily Agent Status", outputs[0])
            self.assertIn("Daily Operating Brief", outputs[1])
            self.assertIn("Daily Agent Doctor", outputs[2])
            self.assertIn("Daily Next", outputs[3])
            self.assertIn("scripts/run_tests.sh", outputs[3])
            self.assertIn("Suggestions were not run", outputs[3])
            after_data = {path.name: path.read_bytes() for path in data_dir.glob("*") if path.is_file()}
            after_exports = {
                str(path.relative_to(exports_root)): path.read_bytes()
                for path in exports_root.rglob("*")
                if path.is_file()
            }
            self.assertEqual(after_data, before_data)
            self.assertEqual(after_exports, before_exports)
            self.assertFalse(json.loads((data_dir / "context_injection.json").read_text(encoding="utf-8"))["enabled"])
            self.assertEqual(logger.status().entry_count, 0)

    def test_milestone_status_reports_roadmap_registry_health_and_manual_action(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            store.save_persistent_memory([])
            _create_healthy_export_dirs(project_root)
            _write_milestone_fixture(project_root)

            output = format_milestone_command("/milestone status", project_root=project_root, memory_store=store)

            self.assertIn("Milestone Roadmap Status", output)
            self.assertIn(f"project_root: {project_root}", output)
            self.assertIn("command_registry: commands=387 categories=41", output)
            self.assertIn("current_milestone: Operating Loop v2.2 / Milestone Tracker v1", output)
            self.assertIn("accepted_milestones_detected: 2", output)
            self.assertIn("milestone_docs: 1", output)
            self.assertIn("Health signals:", output)
            self.assertIn("Suggested safe next manual action:", output)

    def test_milestone_list_parses_only_existing_local_records_and_marks_partial_parse(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            _write_milestone_fixture(project_root)

            output = format_milestone_command("/milestone list", project_root=project_root, memory_store=store)

            self.assertIn("Milestone List", output)
            self.assertIn("accepted_milestones_detected: 2", output)
            self.assertIn("Operating Loop v2 / Daily Agent Layer v1", output)
            self.assertIn("Operating Loop v2.1 / Session Rituals v1", output)
            self.assertIn("MILESTONE_TEST_OPERATOR_LOOP.md", output)
            self.assertIn("Partial deterministic parse", output)
            self.assertIn("not inferred or invented", output)
            self.assertNotIn("Autonomous Planner v9", output)

    def test_milestone_current_distinguishes_detected_inferred_and_unknown_fields(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            _write_milestone_fixture(project_root)

            output = format_milestone_command("/milestone current", project_root=project_root, memory_store=store)

            self.assertIn("Current Milestone Detection", output)
            self.assertIn("Detected facts:", output)
            self.assertIn("ledger latest accepted milestone: Operating Loop v2.2 / Milestone Tracker v1", output)
            self.assertIn("milestone commands: 5/5", output)
            self.assertIn("daily commands: 4/4", output)
            self.assertIn("session_ritual commands: 4/4", output)
            self.assertIn("Inferred current phase:", output)
            self.assertIn("Operating Loop v2.2 roadmap-awareness phase", output)
            self.assertIn("Unknown / undetected:", output)
            self.assertIn("not persisted state", output)

    def test_milestone_next_prints_manual_suggestions_without_execution(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            store.save_persistent_memory([])
            _create_healthy_export_dirs(project_root)
            _write_milestone_fixture(project_root)

            output = format_milestone_command("/milestone next", project_root=project_root, memory_store=store)

            self.assertIn("Milestone Next", output)
            self.assertIn("Safe manual suggestions:", output)
            self.assertIn("scripts/run_tests.sh", output)
            self.assertIn("/proto snapshot-status", output)
            self.assertIn("v3.0a Runner MVP Design Lock", output)
            self.assertIn("Suggestions were not run", output)
            self.assertIn("no warning was repaired", output)

    def test_milestone_doctor_checks_sources_dependencies_context_and_dangerous_actions(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            store.save_persistent_memory([])
            _create_healthy_export_dirs(project_root)
            _write_milestone_fixture(project_root)

            output = format_milestone_command("/milestone doctor", project_root=project_root, memory_store=store)

            self.assertIn("Milestone Layer Doctor", output)
            self.assertRegex(output, r"Status: (OK|WARN)")
            self.assertIn("All milestone commands are registered", output)
            self.assertIn("read-only with mutates=none", output)
            self.assertIn("Architect Ledger is reachable", output)
            self.assertIn("Milestone documents reachable: 1", output)
            self.assertIn("Daily, Session Ritual, Export, and Snapshot/Diff commands are reachable", output)
            self.assertIn("Context Injection is disabled", output)
            self.assertIn("No deletion, move, repair, cleanup, compression, or execution action is exposed", output)

    def test_milestone_doctor_warns_without_changing_explicit_context_enablement(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            store.save_persistent_memory([])
            _create_healthy_export_dirs(project_root)
            _write_milestone_fixture(project_root)
            format_context_command("/context injection enable", project_root=project_root)
            settings_path = project_root / "proto_mind" / "data" / "context_injection.json"
            before = settings_path.read_bytes()

            output = format_milestone_command("/milestone doctor", project_root=project_root, memory_store=store)

            self.assertIn("Status: WARN", output)
            self.assertIn("Context Injection is explicitly enabled", output)
            self.assertEqual(settings_path.read_bytes(), before)
            self.assertTrue(json.loads(settings_path.read_text(encoding="utf-8"))["enabled"])

    def test_milestone_commands_are_read_only_through_shared_handler(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            coordinator, store, _ = build_test_system(project_root / "proto_mind")
            store.save_persistent_memory([])
            logger = SessionOperatorLogger.from_project_root(project_root)
            coordinator.session_logger = logger
            _create_healthy_export_dirs(project_root)
            _write_milestone_fixture(project_root)
            format_context_command("/context injection disable", project_root=project_root)
            data_dir = project_root / "proto_mind" / "data"
            exports_root = project_root / "proto_mind" / "exports"
            before_data = {path.name: path.read_bytes() for path in data_dir.glob("*") if path.is_file()}
            before_exports = {
                str(path.relative_to(exports_root)): path.read_bytes()
                for path in exports_root.rglob("*")
                if path.is_file()
            }

            outputs = [
                process_interactive_input(
                    command,
                    coordinator=coordinator,
                    session_logger=logger,
                    project_root=project_root,
                )
                for command in (
                    "/milestone status",
                    "/milestone list",
                    "/milestone current",
                    "/milestone next",
                    "/milestone doctor",
                )
            ]

            self.assertIn("Milestone Roadmap Status", outputs[0])
            self.assertIn("Milestone List", outputs[1])
            self.assertIn("Current Milestone Detection", outputs[2])
            self.assertIn("Milestone Next", outputs[3])
            self.assertIn("Milestone Layer Doctor", outputs[4])
            after_data = {path.name: path.read_bytes() for path in data_dir.glob("*") if path.is_file()}
            after_exports = {
                str(path.relative_to(exports_root)): path.read_bytes()
                for path in exports_root.rglob("*")
                if path.is_file()
            }
            self.assertEqual(after_data, before_data)
            self.assertEqual(after_exports, before_exports)
            self.assertFalse(json.loads((data_dir / "context_injection.json").read_text(encoding="utf-8"))["enabled"])
            self.assertEqual(logger.status().entry_count, 0)

    def test_prechange_status_reports_warn_baseline_and_safe_manual_start(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            with patch("proto_mind.prechange_layer.PreChangeRitual.read_state", return_value=_prechange_state()):
                output = format_prechange_command("/prechange status", project_root=project_root, memory_store=store)

            self.assertIn("Pre-Change Readiness", output)
            self.assertIn("Status: WARN", output)
            self.assertIn(f"project_root: {project_root}", output)
            self.assertIn("command_registry: commands=387 categories=41", output)
            self.assertIn("context_injection: disabled", output)
            self.assertIn("accepted_known_warnings: 12", output)
            self.assertIn("unknown_warnings: 0", output)
            self.assertIn("blockers: 0", output)
            self.assertIn("agenda_doctor: OK", output)
            self.assertIn("exports_doctor: OK", output)
            self.assertIn("latest_snapshot: snapshot.json", output)
            self.assertIn("latest_snapshot_diff: diff.json", output)
            self.assertIn("safe_to_begin_manual_change: true", output)
            self.assertIn("backup/checkpoint is required", output)

    def test_prechange_status_blocks_unknown_warnings_or_blockers(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            with patch(
                "proto_mind.prechange_layer.PreChangeRitual.read_state",
                return_value=_prechange_state(unknown=True, blockers=1),
            ):
                output = format_prechange_command("/prechange status", project_root=project_root, memory_store=store)

            self.assertIn("Status: BLOCKED", output)
            self.assertIn("unknown_warnings: 1", output)
            self.assertIn("blockers: 1", output)
            self.assertIn("safe_to_begin_manual_change: false", output)

    def test_prechange_checklist_is_manual_only_and_complete(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")

            output = format_prechange_command("/prechange checklist", project_root=project_root, memory_store=store)

            self.assertIn("Pre-Change Manual Checklist", output)
            for expected in (
                "scripts/run_cli.sh",
                "/memory backup",
                "/warnings unknown",
                "/agenda status",
                "/exports doctor",
                "/proto snapshot-diff-status",
                "/context injection status",
                "allowed writes and forbidden writes",
                "scripts/which_python.sh",
                "scripts/run_tests.sh",
                "compileall proto_mind",
                "SHA-256",
            ):
                self.assertIn(expected, output)
            self.assertIn("did not run tests, commands, backups, snapshots, hashes, repairs, or cleanup", output)

    def test_prechange_handoff_prints_copyable_baseline_without_writing(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            _write_milestone_fixture(project_root)
            with patch("proto_mind.prechange_layer.PreChangeRitual.read_state", return_value=_prechange_state()):
                output = format_prechange_command("/prechange handoff", project_root=project_root, memory_store=store)

            self.assertIn("Proto-Mind Pre-Change Task Header", output)
            self.assertIn(f"Project: {project_root}", output)
            self.assertIn("Current milestone: Operating Loop v2.2 / Milestone Tracker v1", output)
            self.assertIn("Registry baseline: 387 commands across 41 categories", output)
            self.assertIn("Warning baseline: accepted=12, unknown=0, blockers=0", output)
            self.assertIn("Rule 0:", output)
            self.assertIn("Safety requirements:", output)
            self.assertIn("Verification:", output)
            self.assertIn("Manual smoke:", output)
            self.assertIn("SHA-256", output)
            self.assertIn("Context Injection: disabled", output)
            self.assertIn("no file, clipboard, backup, snapshot, command, model, or external call", output)

    def test_prechange_doctor_checks_helpers_ledger_context_and_dangerous_actions(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            store.save_persistent_memory([])
            _create_healthy_export_dirs(project_root)
            _write_milestone_fixture(project_root)

            with patch("proto_mind.prechange_layer.PreChangeRitual.read_state", return_value=_prechange_state()):
                output = format_prechange_command("/prechange doctor", project_root=project_root, memory_store=store)

            self.assertIn("Pre-Change Ritual Doctor", output)
            self.assertIn("Status: OK", output)
            self.assertIn("All pre-change commands are registered", output)
            self.assertIn("read-only with mutates=none", output)
            self.assertIn("Agenda, Warning, Export, Snapshot, and Context helpers are reachable", output)
            self.assertIn("Accepted-known warnings ledger is reachable", output)
            self.assertIn("Warning readiness is computable", output)
            self.assertIn("Context Injection is disabled", output)
            self.assertIn("No execution, backup, snapshot, repair, cleanup, migration, deletion, move, or compression action is exposed", output)

    def test_prechange_doctor_warns_without_changing_explicit_context_enablement(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            _, store, _ = build_test_system(project_root / "proto_mind")
            store.save_persistent_memory([])
            _create_healthy_export_dirs(project_root)
            _write_milestone_fixture(project_root)
            format_context_command("/context injection enable", project_root=project_root)
            settings_path = project_root / "proto_mind" / "data" / "context_injection.json"
            before = settings_path.read_bytes()

            with patch(
                "proto_mind.prechange_layer.PreChangeRitual.read_state",
                return_value=_prechange_state(context_state="enabled"),
            ):
                output = format_prechange_command("/prechange doctor", project_root=project_root, memory_store=store)

            self.assertIn("Status: WARN", output)
            self.assertIn("Context Injection is explicitly enabled", output)
            self.assertEqual(settings_path.read_bytes(), before)
            self.assertTrue(json.loads(settings_path.read_text(encoding="utf-8"))["enabled"])

    def test_prechange_commands_are_read_only_through_shared_handler(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            coordinator, store, _ = build_test_system(project_root / "proto_mind")
            store.save_persistent_memory([])
            logger = SessionOperatorLogger.from_project_root(project_root)
            coordinator.session_logger = logger
            _create_healthy_export_dirs(project_root)
            _write_milestone_fixture(project_root)
            format_context_command("/context injection disable", project_root=project_root)
            data_dir = project_root / "proto_mind" / "data"
            exports_root = project_root / "proto_mind" / "exports"
            before_data = {path.name: path.read_bytes() for path in data_dir.glob("*") if path.is_file()}
            before_exports = {
                str(path.relative_to(exports_root)): path.read_bytes()
                for path in exports_root.rglob("*")
                if path.is_file()
            }

            outputs = [
                process_interactive_input(
                    command,
                    coordinator=coordinator,
                    session_logger=logger,
                    project_root=project_root,
                )
                for command in (
                    "/prechange status",
                    "/prechange checklist",
                    "/prechange doctor",
                    "/prechange handoff",
                )
            ]

            self.assertIn("Pre-Change Readiness", outputs[0])
            self.assertIn("Pre-Change Manual Checklist", outputs[1])
            self.assertIn("Pre-Change Ritual Doctor", outputs[2])
            self.assertIn("Proto-Mind Pre-Change Task Header", outputs[3])
            after_data = {path.name: path.read_bytes() for path in data_dir.glob("*") if path.is_file()}
            after_exports = {
                str(path.relative_to(exports_root)): path.read_bytes()
                for path in exports_root.rglob("*")
                if path.is_file()
            }
            self.assertEqual(after_data, before_data)
            self.assertEqual(after_exports, before_exports)
            self.assertFalse(json.loads((data_dir / "context_injection.json").read_text(encoding="utf-8"))["enabled"])
            self.assertEqual(logger.status().entry_count, 0)

    def test_apply_receipt_links_restart_safe_why_command(self) -> None:
        with TemporaryDirectory() as temp_dir:
            _, store, pilot, bridge, _, skills, proposal = build_test_learning_apply(
                Path(temp_dir)
            )
            output, receipt = apply_test_learning_proposal(
                store,
                pilot,
                bridge,
                skills,
                proposal,
            )
            receipt_output = format_learning_memory_apply_command(
                f"/experience learning apply-receipt {proposal.id}",
                bridge=bridge,
                decisions=pilot.learning_decisions,
                proposals=pilot.learning_proposals,
                applies=pilot.learning_applies,
                memory_store=store,
                skill_library=skills,
            )

        self.assertIn(f"why_command: /memory why {receipt.created_record_id}", output)
        self.assertIn("durable_provenance_persistence: embedded_memory_record", receipt_output)
        self.assertIn(receipt.durable_provenance_id, receipt_output)

    def test_applied_lesson_is_recalled_with_provenance_after_store_restart(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _, store, pilot, bridge, _, skills, proposal = build_test_learning_apply(root)
            _, receipt = apply_test_learning_proposal(store, pilot, bridge, skills, proposal)
            lesson = next(
                item
                for item in store.load_persistent_memory()
                if item.id == receipt.created_record_id
            )
            store.save_persistent_memory([lesson])
            store.save_working_memory([])
            restarted = MemoryStore(store.working_path, store.persistent_path)
            before = restarted.persistent_path.read_bytes()
            coordinator = Coordinator(
                observer=Observer(),
                memory_keeper=MemoryKeeper(restarted),
                reasoner=MockReasoner(),
            )
            result = coordinator.handle(
                "As we discussed earlier, what did we learn about the active SQLite decision?"
            )
            after = restarted.persistent_path.read_bytes()

        selected = next(
            item for item in result.retrieved_memory if item.id == receipt.created_record_id
        )
        candidate = next(
            item
            for item in result.retrieval_trace.candidates
            if item.record_id == receipt.created_record_id
        )
        self.assertTrue(verify_memory_provenance(selected).verified)
        self.assertTrue(candidate.selected)
        self.assertIn("provenance was verified", candidate.why_selected_summary)
        self.assertTrue(
            any(
                "provenance=verified" in evidence
                for evidence in result.grounding_audit.evidence
            )
        )
        self.assertEqual(before, after)

    def test_tampered_learning_lesson_is_filtered_fail_closed(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _, store, pilot, bridge, _, skills, proposal = build_test_learning_apply(root)
            _, receipt = apply_test_learning_proposal(store, pilot, bridge, skills, proposal)
            records = store.load_persistent_memory()
            lesson = next(item for item in records if item.id == receipt.created_record_id)
            lesson.content = "Tampered SQLite lesson."
            store.save_persistent_memory(records)
            state = Observer().analyze("What did we learn about SQLite?")
            keeper = MemoryKeeper(store)
            keeper.retrieve(state)

        candidate = next(
            item
            for item in keeper.last_retrieval_trace.candidates
            if item.record_id == receipt.created_record_id
        )
        self.assertFalse(candidate.selected)
        self.assertEqual(
            candidate.filtered_reason,
            "filtered_unverified_lesson_provenance",
        )
        self.assertIn("valid durable provenance", candidate.why_not_selected_summary)

    def test_unprovenanced_lesson_is_filtered_but_project_fact_is_unchanged(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = MemoryStore(root / "working.json", root / "persistent.json")
            store.save_persistent_memory(
                [
                    MemoryRecord(
                        id="legacy_lesson",
                        content="SQLite verification lesson.",
                        type="lesson",
                        importance=1.0,
                        source="legacy",
                        tags=["sqlite", "verification"],
                    ),
                    MemoryRecord(
                        id="project_fact",
                        content="SQLite is used for verified project storage.",
                        type="project_fact",
                        importance=1.0,
                        source="operator",
                        tags=["sqlite", "storage"],
                    ),
                ]
            )
            keeper = MemoryKeeper(store)
            selected = keeper.retrieve(Observer().analyze("What is the SQLite storage decision?"))

        traces = {item.record_id: item for item in keeper.last_retrieval_trace.candidates}
        self.assertEqual(
            traces["legacy_lesson"].filtered_reason,
            "filtered_unverified_lesson_provenance",
        )
        self.assertTrue(traces["project_fact"].selected)
        self.assertIn("project_fact", [item.id for item in selected])

    def test_inactive_verified_lesson_is_filtered_outside_historical_lookup(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _, store, pilot, bridge, _, skills, proposal = build_test_learning_apply(root)
            _, receipt = apply_test_learning_proposal(store, pilot, bridge, skills, proposal)
            records = store.load_persistent_memory()
            lesson = next(item for item in records if item.id == receipt.created_record_id)
            lesson.active = False
            store.save_persistent_memory(records)
            keeper = MemoryKeeper(store)
            keeper.retrieve(Observer().analyze("What did we learn about the active SQLite decision?"))

        candidate = next(
            item
            for item in keeper.last_retrieval_trace.candidates
            if item.record_id == receipt.created_record_id
        )
        self.assertEqual(candidate.filtered_reason, "filtered_inactive_lesson")
        self.assertFalse(candidate.selected)

    def test_legacy_skill_lifecycle_archive_redirects_to_durable_gate(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store, library, pilot, _, receipt, reviewer = (
                build_test_procedural_skill_lifecycle_readiness(
                    Path(temp_dir), outcomes=("failure",), decision="archive"
                )
            )
            skill_before = library.skills_path.read_bytes()
            memory_before = store.persistent_path.read_bytes()
            review = pilot.skill_lifecycle_applies.review(receipt, reviewer=reviewer)
            output = format_procedural_skill_lifecycle_apply_command(
                f"/experience learning skill-outcome-lifecycle-apply-preview {receipt.id}",
                decision_session=pilot.skill_outcome_decisions,
                apply_session=pilot.skill_lifecycle_applies,
                reviewer=reviewer,
            )
            skill_after = library.skills_path.read_bytes()
            memory_after = store.persistent_path.read_bytes()

        self.assertFalse(review.confirmable)
        self.assertIn("Status: NOT CONFIRMABLE", output)
        self.assertIn("requires the separately confirmed --durable", output)
        self.assertNotIn("confirmation_token:", output)
        self.assertEqual(skill_after, skill_before)
        self.assertEqual(memory_after, memory_before)

    def test_contest_provenance_scope_excludes_private_and_generated_paths(self) -> None:
        included = (
            "README.md",
            ".gitignore",
            "proto_mind/main.py",
            "proto_mind/tests/test_flow.py",
            "scripts/run_tests.sh",
            "assets/proto_mind_icon.svg",
        )
        excluded = (
            "backups/baseline.tar.gz",
            "proto_mind/data/persistent_memory.json",
            "proto_mind/exports/context.json",
            "logs/session_operator_log.jsonl",
            "contest/provenance/current_manifest.json",
            "proto_mind/__pycache__/main.pyc",
        )

        self.assertTrue(all(is_submission_relevant(path) for path in included))
        self.assertFalse(any(is_submission_relevant(path) for path in excluded))

    def test_contest_provenance_builds_valid_baseline_current_and_delta_manifests(self) -> None:
        with TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            project = temp / "project"
            baseline_tree = temp / "baseline"
            output = project / "contest" / "provenance"
            for root in (project, baseline_tree):
                (root / "proto_mind" / "tests").mkdir(parents=True)
            (baseline_tree / "ARCHITECTURE_MAP_V2.md").write_text(
                "Registry describes 3 command prefixes across 1 categories.\n",
                encoding="utf-8",
            )
            (baseline_tree / "proto_mind" / "tests" / "test_flow.py").write_text(
                "class Tests:\n    def test_old(self):\n        pass\n",
                encoding="utf-8",
            )
            (baseline_tree / "proto_mind" / "old.py").write_text("OLD = True\n", encoding="utf-8")
            archive = temp / "baseline.tar.gz"
            with tarfile.open(archive, "w:gz") as handle:
                for path in baseline_tree.rglob("*"):
                    if path.is_file():
                        handle.add(path, arcname=path.relative_to(baseline_tree))

            (project / "ARCHITECTURE_MAP_V2.md").write_text(
                "Registry describes 5 command prefixes across 2 categories.\n",
                encoding="utf-8",
            )
            (project / "proto_mind" / "tests" / "test_flow.py").write_text(
                "class Tests:\n    def test_old(self):\n        pass\n    def test_new(self):\n        pass\n",
                encoding="utf-8",
            )
            (project / "proto_mind" / "new.py").write_text("NEW = True\n", encoding="utf-8")
            (project / "proto_mind" / "data").mkdir()
            (project / "proto_mind" / "data" / "secret.json").write_text("secret", encoding="utf-8")

            result = build_contest_provenance(
                project,
                archive,
                output,
                generated_at="2026-07-18T20:00:00+00:00",
            )
            regenerated = build_contest_provenance(
                project,
                archive,
                output,
                generated_at="2026-07-19T20:00:00+00:00",
            )
            delta = result["contest_delta"]
            current_manifest = result["current_manifest"]

        self.assertEqual(delta["metrics"]["test_method_count"]["baseline"], 1)
        self.assertEqual(delta["metrics"]["test_method_count"]["current"], 2)
        self.assertEqual(delta["metrics"]["registry_command_count"]["delta"], 2)
        self.assertIn("proto_mind/new.py", delta["files"]["added"])
        self.assertIn("proto_mind/old.py", delta["files"]["removed"])
        self.assertNotIn("proto_mind/data/secret.json", json.dumps(result))
        self.assertTrue(delta["summary"]["meaningful_extension_evidence"])
        self.assertTrue(all(Path(path).suffix == ".json" for path in result["outputs"].values()))
        self.assertEqual(current_manifest["source"]["path"], ".")
        self.assertNotIn(str(project), json.dumps(current_manifest))
        self.assertEqual(regenerated["baseline_manifest"]["generated_at"], "2026-07-18T20:00:00+00:00")
        self.assertEqual(regenerated["current_manifest"]["generated_at"], "2026-07-19T20:00:00+00:00")

    def test_showcase_status_reports_safe_local_demo_readiness(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            coordinator, store, _ = build_test_system(project_root / "proto_mind")
            with patch(
                "proto_mind.showcase_layer.OperatorMemoryCard.read_state",
                return_value=_memory_card_state(),
            ):
                output = format_showcase_command(
                    "/showcase status",
                    project_root=project_root,
                    memory_store=store,
                    owner=coordinator,
                )

        self.assertIn("Proto-Mind Contest Showcase v1", output)
        self.assertIn("Status: READY", output)
        self.assertIn("command_registry: 387 commands / 41 categories", output)
        self.assertIn("context_injection: disabled", output)
        self.assertIn("experience_pilot: state=not_started", output)
        self.assertIn("read_only_runner_allowlist: 4", output)
        self.assertIn("no command, consent, model call", output)

    def test_showcase_demo_connects_continuity_experience_governance_and_action(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            coordinator, store, _ = build_test_system(project_root / "proto_mind")
            with patch(
                "proto_mind.showcase_layer.OperatorMemoryCard.read_state",
                return_value=_memory_card_state(),
            ):
                output = format_showcase_command(
                    "/showcase demo",
                    project_root=project_root,
                    memory_store=store,
                    owner=coordinator,
                )

        for heading in (
            "1. CONTINUITY",
            "2. EXPLAINABLE EXPERIENCE",
            "3. GOVERNANCE",
            "4. BOUNDED ACTION",
            "WHY IT MATTERS",
        ):
            self.assertIn(heading, output)
        self.assertIn("Next manual step: /experience preview", output)
        self.assertIn("Persistent Experience capture: disabled", output)
        self.assertIn("No command executed. No state mutated.", output)

    def test_showcase_demo_reflects_existing_consented_pilot_without_activating_it(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            coordinator, store, _ = build_test_system(project_root / "proto_mind")
            pilot = get_experience_pilot(coordinator, project_root=project_root)
            pilot.preview()
            pilot.consent(pilot.expected_consent_phrase)
            user_input = "Explain the contest-ready continuity path."
            result = coordinator.handle(user_input)
            pilot.observe_normal_turn(user_input, result)
            latest_id = pilot.snapshot()[-1]["id"]

            with patch(
                "proto_mind.showcase_layer.OperatorMemoryCard.read_state",
                return_value=_memory_card_state(),
            ):
                output = format_showcase_command(
                    "/showcase demo",
                    project_root=project_root,
                    memory_store=store,
                    owner=coordinator,
                )

        self.assertIn("Pilot: consented", output)
        self.assertIn("Evidence: turns=1, events=7", output)
        self.assertIn("Latest cognitive episode: turn=1", output)
        self.assertIn("Inspect cognitive path: /experience episode latest", output)
        self.assertIn(latest_id, output)
        self.assertIn(f"/experience inspect {latest_id}", output)
        self.assertEqual(pilot.state, "consented")
        self.assertEqual(pilot.event_count, 7)

    def test_showcase_script_is_copyable_and_executes_nothing(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            coordinator, store, _ = build_test_system(project_root / "proto_mind")
            output = format_showcase_command(
                "/showcase script",
                project_root=project_root,
                memory_store=store,
                owner=coordinator,
            )

        self.assertIn("3-Minute Operator Script", output)
        self.assertIn("/experience preview", output)
        self.assertIn("/runner-exec dry-run /daily doctor", output)
        self.assertIn("CONFIRM RUN READONLY: /daily doctor", output)
        self.assertIn("/experience stop", output)
        self.assertIn("this command ran no step", output)
        self.assertIsNone(peek_experience_pilot(coordinator))

    def test_showcase_doctor_checks_dependencies_and_warns_on_enabled_context(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            coordinator, store, _ = build_test_system(project_root / "proto_mind")
            showcase = ContestShowcase(
                project_root=project_root,
                memory_store=store,
                owner=coordinator,
            )
            with patch(
                "proto_mind.showcase_layer.OperatorMemoryCard.read_state",
                return_value=_memory_card_state(),
            ):
                healthy = showcase.format_doctor()
            with patch(
                "proto_mind.showcase_layer.OperatorMemoryCard.read_state",
                return_value=_memory_card_state(context_state="enabled"),
            ):
                warning = showcase.format_doctor()

        self.assertIn("Status: OK", healthy)
        self.assertIn("Showcase and dependency commands are registered", healthy)
        self.assertIn("exactly four read-only", healthy)
        self.assertIn("Experience persistence, export, apply", healthy)
        self.assertIn("Status: WARN", warning)
        self.assertIn("disable it before", warning)

    def test_showcase_commands_do_not_mutate_stores_or_create_pilot_state(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            coordinator, store, _ = build_test_system(project_root / "proto_mind")
            before = {
                str(path.relative_to(project_root)): path.read_bytes()
                for path in project_root.rglob("*")
                if path.is_file()
            }
            with patch(
                "proto_mind.showcase_layer.OperatorMemoryCard.read_state",
                return_value=_memory_card_state(),
            ):
                outputs = [
                    format_showcase_command(
                        command,
                        project_root=project_root,
                        memory_store=store,
                        owner=coordinator,
                    )
                    for command in SHOWCASE_COMMANDS
                ]
            after = {
                str(path.relative_to(project_root)): path.read_bytes()
                for path in project_root.rglob("*")
                if path.is_file()
            }

        self.assertTrue(all(outputs))
        self.assertEqual(after, before)
        self.assertIsNone(peek_experience_pilot(coordinator))

    def test_showcase_commands_work_through_shared_handler(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            coordinator, store, _ = build_test_system(project_root / "proto_mind")
            logger = SessionOperatorLogger(project_root / "session.jsonl", enabled=False)
            with patch(
                "proto_mind.showcase_layer.OperatorMemoryCard.read_state",
                return_value=_memory_card_state(),
            ):
                output = process_interactive_input(
                    "/showcase demo",
                    coordinator=coordinator,
                    session_logger=logger,
                    project_root=project_root,
                )

        self.assertIn("PROTO-MIND | LOCAL COGNITIVE OPERATING SYSTEM", output)
        self.assertEqual(logger.status().entry_count, 0)
        self.assertIsNone(peek_experience_pilot(coordinator))

    def test_showcase_registry_policy_and_usage_are_safe(self) -> None:
        registry = {item.prefix: item for item in COMMAND_REGISTRY}
        for command in SHOWCASE_COMMANDS:
            self.assertIn(command, registry)
            self.assertTrue(registry[command].read_only)
            self.assertEqual(registry[command].mutates, "none")
            self.assertEqual(registry[command].risk, "low")
            self.assertEqual(classify_command(command).policy_class, "auto_allowed")
        self.assertEqual(len(COMMAND_REGISTRY), 387)
        self.assertEqual(len({item.category for item in COMMAND_REGISTRY}), 41)
        self.assertEqual(command_registry_doctor()["status"], "OK")

        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            coordinator, store, _ = build_test_system(project_root / "proto_mind")
            usage = format_showcase_command(
                "/showcase unknown",
                project_root=project_root,
                memory_store=store,
                owner=coordinator,
            )
        self.assertIn("/showcase demo", usage)
        self.assertIsNone(peek_experience_pilot(coordinator))
