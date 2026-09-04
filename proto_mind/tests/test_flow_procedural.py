"""Core flow checks: procedural."""
from __future__ import annotations

import unittest
from proto_mind.tests.flow_fixtures import (
    COMMAND_REGISTRY,
    MemoryStore,
    OperatorReviewedProceduralSkillApplySession,
    OperatorReviewedProceduralSkillAuthoringSession,
    PROCEDURAL_SKILL_APPLY_ENGINE_INSTALLED,
    PROCEDURAL_SKILL_APPLY_MAX_RECEIPTS,
    PROCEDURAL_SKILL_APPLY_MODE,
    PROCEDURAL_SKILL_AUTHORING_MAX_RECEIPTS,
    PROCEDURAL_SKILL_AUTHORING_MODE,
    PROCEDURAL_SKILL_CONTRACT_MODE,
    PROCEDURAL_SKILL_CONTRACT_SCHEMA,
    PROCEDURAL_SKILL_EXECUTION_ENABLED,
    PROCEDURAL_SKILL_EXECUTION_INSTALLED,
    PROCEDURAL_SKILL_FUTURE_RECEIPT_FIELDS,
    PROCEDURAL_SKILL_OUTCOME_MODE,
    PROCEDURAL_SKILL_OUTCOME_STATUSES,
    PROCEDURAL_SKILL_PROVENANCE_SCHEMA,
    PROCEDURAL_SKILL_READINESS_MODE,
    PROCEDURAL_SKILL_WRITER_INSTALLED,
    Path,
    ProceduralSkillApplyError,
    ProceduralSkillApplyReadiness,
    ProceduralSkillAuthoringError,
    ProceduralSkillContractBuilder,
    ProceduralSkillOutcomeReviewer,
    SessionOperatorLogger,
    SkillLibrary,
    TemporaryDirectory,
    _id_from_output,
    _test_skill_authoring_flags,
    action_policy_doctor,
    apply_test_learning_lifecycle_transition,
    build_procedural_skill_authoring_blueprint,
    build_test_applied_procedural_skill,
    build_test_learning_lifecycle_transition,
    build_test_learning_outcome_review,
    build_test_procedural_skill_authoring,
    build_test_procedural_skill_outcome_events,
    build_test_system,
    classify_command,
    command_registry_doctor,
    format_procedural_skill_apply_command,
    format_procedural_skill_authoring_command,
    format_procedural_skill_contract_command,
    format_procedural_skill_outcome_command,
    format_procedural_skill_readiness_command,
    parse_procedural_skill_authoring_request,
    patch,
    procedural_skill_apply_confirmation_token,
    procedural_skill_authoring_confirmation_token,
    process_interactive_input,
    replace,
    shlex,
    verify_procedural_skill_provenance,
)


class ProceduralFlowTests(unittest.TestCase):
    def test_procedural_skill_contract_status_and_doctor_are_empty_read_only(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _, store, _ = build_test_system(root)
            before = (store.working_path.read_bytes(), store.persistent_path.read_bytes())
            status = format_procedural_skill_contract_command(
                "/experience learning skill-contract-status",
                memory_store=store,
                project_root=root,
            )
            doctor = format_procedural_skill_contract_command(
                "/experience learning skill-contract-doctor",
                memory_store=store,
                project_root=root,
            )
            after = (store.working_path.read_bytes(), store.persistent_path.read_bytes())

        self.assertIn("Status: OK", status)
        self.assertIn("learned_lessons: 0", status)
        self.assertIn("skill_apply_engine_installed: true", status)
        self.assertIn("Status: OK", doctor)
        self.assertEqual(before, after)

    def test_procedural_skill_contract_preview_is_deterministic_and_incomplete(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _, store, _, review = build_test_learning_outcome_review(root)
            builder = ProceduralSkillContractBuilder(
                memory_store=store,
                skill_library=SkillLibrary(root / "skills.jsonl"),
            )
            before = store.persistent_path.read_bytes()
            first = builder.review(review.lesson_memory_id)
            restarted = ProceduralSkillContractBuilder(
                memory_store=MemoryStore(store.working_path, store.persistent_path),
                skill_library=SkillLibrary(root / "skills.jsonl"),
            ).review(review.lesson_memory_id)
            after = store.persistent_path.read_bytes()

        self.assertEqual(first.status, "ELIGIBLE FOR OPERATOR AUTHORING")
        self.assertTrue(first.eligible_for_operator_authoring)
        self.assertEqual(first.lifecycle_state, "active")
        self.assertEqual(first.contract.id, restarted.contract.id)
        self.assertEqual(first.contract.contract_hash, restarted.contract.contract_hash)
        self.assertEqual(first.contract.schema, PROCEDURAL_SKILL_CONTRACT_SCHEMA)
        self.assertFalse(first.contract.complete)
        self.assertFalse(first.contract.executable)
        self.assertFalse(first.contract.promotion_allowed)
        self.assertFalse(first.contract.automatic_synthesis_performed)
        self.assertEqual(before, after)

    def test_procedural_skill_contract_template_requires_operator_fields_without_write(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _, store, _, review = build_test_learning_outcome_review(root)
            skill_path = root / "proto_mind" / "data" / "skills.jsonl"
            before_memory = store.persistent_path.read_bytes()
            before_skill_exists = skill_path.exists()
            template = format_procedural_skill_contract_command(
                f"/experience learning skill-contract-template {review.lesson_memory_id}",
                memory_store=store,
                project_root=root,
            )
            checklist = format_procedural_skill_contract_command(
                f"/experience learning skill-contract-checklist {review.lesson_memory_id}",
                memory_store=store,
                project_root=root,
            )
            after_memory = store.persistent_path.read_bytes()
            after_skill_exists = skill_path.exists()

        self.assertIn("Status: OPERATOR INPUT REQUIRED", template)
        self.assertIn('"trigger": "<operator required>"', template)
        self.assertIn('"steps": [', template)
        self.assertIn('"executable": false', template)
        self.assertIn("Required operator-authored fields:", checklist)
        self.assertIn("known_failure_modes", checklist)
        self.assertIn("no execution", checklist.lower())
        self.assertEqual(before_memory, after_memory)
        self.assertEqual(before_skill_exists, after_skill_exists)

    def test_procedural_skill_contract_rejects_terminal_old_lesson(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _, store, events, review, lifecycle, applies = (
                build_test_learning_lifecycle_transition(root, decision="reject")
            )
            apply_test_learning_lifecycle_transition(
                store, events, review, lifecycle, applies
            )
            result = ProceduralSkillContractBuilder(
                memory_store=store,
                skill_library=SkillLibrary(root / "skills.jsonl"),
            ).review(review.lesson_memory_id)

        self.assertEqual(result.status, "NOT ELIGIBLE")
        self.assertEqual(result.lifecycle_state, "rejected")
        self.assertFalse(result.checks["lesson_active"])
        self.assertFalse(result.eligible_for_operator_authoring)

    def test_procedural_skill_contract_supersede_uses_active_replacement_only(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _, store, events, review, lifecycle, applies = (
                build_test_learning_lifecycle_transition(root, decision="supersede")
            )
            apply_test_learning_lifecycle_transition(
                store, events, review, lifecycle, applies
            )
            builder = ProceduralSkillContractBuilder(
                memory_store=store,
                skill_library=SkillLibrary(root / "skills.jsonl"),
            )
            old = builder.review(review.lesson_memory_id)
            replacement = builder.review(review.replacement_memory_id)

        self.assertEqual(old.status, "NOT ELIGIBLE")
        self.assertEqual(old.lifecycle_state, "superseded")
        self.assertEqual(replacement.status, "ELIGIBLE FOR OPERATOR AUTHORING")
        self.assertEqual(replacement.lifecycle_state, "active")
        self.assertEqual(replacement.contract.source_lesson_id, review.replacement_memory_id)

    def test_procedural_skill_contract_detects_active_exact_skill_duplicate(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _, store, _, review = build_test_learning_outcome_review(root)
            record = store.load_persistent_memory()[0]
            skills = SkillLibrary(root / "skills.jsonl")
            skills.add_skill(
                "Existing verified procedure",
                category="workflow",
                summary=record.content,
            )
            result = ProceduralSkillContractBuilder(
                memory_store=store,
                skill_library=skills,
            ).review(review.lesson_memory_id)

        self.assertEqual(result.status, "DUPLICATE")
        self.assertFalse(result.checks["active_exact_duplicate_absent"])
        self.assertEqual(len(result.duplicate_skill_ids), 1)
        self.assertFalse(result.eligible_for_operator_authoring)

    def test_procedural_skill_contract_fails_closed_on_tampered_provenance(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _, store, _, review = build_test_learning_outcome_review(root)
            record = store.load_persistent_memory()[0]
            record.provenance["decision_id"] = "tampered_decision"
            store.save_persistent_memory([record])
            result = ProceduralSkillContractBuilder(
                memory_store=store,
                skill_library=SkillLibrary(root / "skills.jsonl"),
            ).review(review.lesson_memory_id)

        self.assertEqual(result.status, "ERROR")
        self.assertFalse(result.checks["durable_provenance_verified"])
        self.assertIsNone(result.contract)
        self.assertFalse(result.eligible_for_operator_authoring)

    def test_procedural_skill_contract_doctor_warns_on_malformed_skill_store(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _, store, _, _ = build_test_learning_outcome_review(root)
            skills = SkillLibrary(root / "skills.jsonl")
            skills.skills_path.write_text("{malformed\n", encoding="utf-8")
            report = ProceduralSkillContractBuilder(
                memory_store=store,
                skill_library=skills,
            ).doctor()

        self.assertEqual(report.status, "WARN")
        self.assertEqual(report.malformed_skill_count, 1)
        self.assertIn("malformed JSONL", " ".join(report.warnings))

    def test_procedural_skill_contract_preview_handles_missing_id_cleanly(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _, store, _ = build_test_system(root)
            output = format_procedural_skill_contract_command(
                "/experience learning skill-contract-preview missing",
                memory_store=store,
                project_root=root,
            )

        self.assertIn("Status: NOT ELIGIBLE", output)
        self.assertIn("exact_memory_id_found: false", output)
        self.assertIn("no procedure was synthesized", output)

    def test_procedural_skill_contract_shared_handler_is_read_only_and_registered(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            coordinator, store, _, review = build_test_learning_outcome_review(root)
            logger = SessionOperatorLogger(root / "session.jsonl", enabled=False)
            skill_path = root / "proto_mind" / "data" / "skills.jsonl"
            before = (store.working_path.read_bytes(), store.persistent_path.read_bytes())
            output = process_interactive_input(
                f"/experience learning skill-contract-preview {review.lesson_memory_id}",
                coordinator=coordinator,
                session_logger=logger,
                project_root=root,
            )
            after = (store.working_path.read_bytes(), store.persistent_path.read_bytes())

        self.assertIn("ELIGIBLE FOR OPERATOR AUTHORING", output)
        self.assertEqual(before, after)
        self.assertFalse(skill_path.exists())
        self.assertEqual(logger.status().entry_count, 0)
        self.assertEqual(
            PROCEDURAL_SKILL_CONTRACT_MODE,
            "read_only_operator_authoring_contract",
        )
        self.assertTrue(PROCEDURAL_SKILL_APPLY_ENGINE_INSTALLED)
        self.assertEqual(
            classify_command(
                "/experience learning skill-contract-preview mem_lesson"
            ).policy_class,
            "auto_allowed",
        )
        self.assertEqual(len(COMMAND_REGISTRY), 387)
        self.assertEqual(len({entry.category for entry in COMMAND_REGISTRY}), 41)
        self.assertEqual(command_registry_doctor()["status"], "OK")
        self.assertEqual(action_policy_doctor()["status"], "OK")

    def test_procedural_skill_authoring_status_and_doctor_are_empty_read_only(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _, store, _ = build_test_system(root)
            builder = ProceduralSkillContractBuilder(
                memory_store=store,
                skill_library=SkillLibrary(root / "skills.jsonl"),
            )
            session = OperatorReviewedProceduralSkillAuthoringSession()
            before = (store.working_path.read_bytes(), store.persistent_path.read_bytes())
            status = format_procedural_skill_authoring_command(
                "/experience learning skill-authoring-status",
                builder=builder,
                session=session,
            )
            doctor = format_procedural_skill_authoring_command(
                "/experience learning skill-authoring-doctor",
                builder=builder,
                session=session,
            )
            after = (store.working_path.read_bytes(), store.persistent_path.read_bytes())

        self.assertIn("Status: OK", status)
        self.assertIn(f"receipts: 0/{PROCEDURAL_SKILL_AUTHORING_MAX_RECEIPTS}", status)
        self.assertIn("supervised_skill_writer_installed: true", status)
        self.assertIn("authoring_direct_writes_enabled: false", status)
        self.assertIn("propose skill-contract", status)
        self.assertIn("Status: OK", doctor)
        self.assertEqual(before, after)

    def test_procedural_skill_authoring_preview_binds_exact_visible_fields(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _, store, _, review = build_test_learning_outcome_review(root)
            builder = ProceduralSkillContractBuilder(
                memory_store=store,
                skill_library=SkillLibrary(root / "skills.jsonl"),
            )
            session = OperatorReviewedProceduralSkillAuthoringSession()
            command = (
                f"/experience learning skill-authoring-confirm-preview "
                f"{review.lesson_memory_id} {_test_skill_authoring_flags()}"
            )
            before = store.persistent_path.read_bytes()
            first = format_procedural_skill_authoring_command(
                command, builder=builder, session=session
            )
            second = format_procedural_skill_authoring_command(
                command, builder=builder, session=session
            )
            after = store.persistent_path.read_bytes()

        self.assertIn("Status: CONFIRMABLE", first)
        self.assertIn("step[1]: Inspect the exact source evidence", first)
        self.assertIn("permission[1]: Read-only project inspection", first)
        self.assertIn("future_apply_ready: false", first)
        self.assertIn("executable: false", first)
        self.assertEqual(
            _id_from_output(first, "Confirmation token:"),
            _id_from_output(second, "Confirmation token:"),
        )
        self.assertEqual(before, after)
        self.assertEqual(session.snapshot(), ())

    def test_procedural_skill_authoring_wrong_token_creates_no_receipt(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _, store, _, review = build_test_learning_outcome_review(root)
            builder = ProceduralSkillContractBuilder(
                memory_store=store,
                skill_library=SkillLibrary(root / "skills.jsonl"),
            )
            session = OperatorReviewedProceduralSkillAuthoringSession()
            output = format_procedural_skill_authoring_command(
                f"/experience learning propose skill-contract {review.lesson_memory_id} "
                f"WRONG-TOKEN {_test_skill_authoring_flags()}",
                builder=builder,
                session=session,
            )

        self.assertIn("Status: ERROR", output)
        self.assertIn("token mismatch", output)
        self.assertEqual(session.snapshot(), ())

    def test_procedural_skill_authoring_exact_token_records_process_receipt_only(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _, store, _, review = build_test_learning_outcome_review(root)
            skill_path = root / "skills.jsonl"
            builder = ProceduralSkillContractBuilder(
                memory_store=store,
                skill_library=SkillLibrary(skill_path),
            )
            session = OperatorReviewedProceduralSkillAuthoringSession()
            flags = _test_skill_authoring_flags()
            preview = format_procedural_skill_authoring_command(
                f"/experience learning skill-authoring-confirm-preview "
                f"{review.lesson_memory_id} {flags}",
                builder=builder,
                session=session,
            )
            token = _id_from_output(preview, "Confirmation token:")
            before_memory = store.persistent_path.read_bytes()
            output = format_procedural_skill_authoring_command(
                f"/experience learning propose skill-contract {review.lesson_memory_id} "
                f"{token} {flags}",
                builder=builder,
                session=session,
            )
            receipt = session.get(review.lesson_memory_id)
            after_memory = store.persistent_path.read_bytes()
            doctor = session.doctor(builder)

        self.assertIn("Status: OPERATOR AUTHORING RECORDED", output)
        self.assertIsNotNone(receipt)
        self.assertEqual(
            receipt.authored_contract["steps"],
            [
                "Inspect the exact source evidence",
                "Choose one bounded reversible response",
            ],
        )
        self.assertEqual(receipt.confirmation_method, "exact_source_and_authored_contract_token")
        self.assertTrue(receipt.process_memory_only)
        self.assertTrue(receipt.restart_expiring)
        self.assertFalse(receipt.future_apply_ready)
        self.assertFalse(receipt.executable)
        self.assertFalse(receipt.skill_mutation_performed)
        self.assertEqual(doctor.status, "OK")
        self.assertEqual(doctor.current_count, 1)
        self.assertEqual(before_memory, after_memory)
        self.assertFalse(skill_path.exists())

    def test_procedural_skill_authoring_is_run_once_per_lesson(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _, store, _, review = build_test_learning_outcome_review(root)
            builder = ProceduralSkillContractBuilder(
                memory_store=store,
                skill_library=SkillLibrary(root / "skills.jsonl"),
            )
            request = parse_procedural_skill_authoring_request(
                shlex.split(f"{review.lesson_memory_id} {_test_skill_authoring_flags()}")
            )
            blueprint = build_procedural_skill_authoring_blueprint(builder, request)
            token = procedural_skill_authoring_confirmation_token(blueprint)
            session = OperatorReviewedProceduralSkillAuthoringSession()
            first = session.create(blueprint, token=token)
            output = format_procedural_skill_authoring_command(
                f"/experience learning propose skill-contract {review.lesson_memory_id} "
                f"{token} {_test_skill_authoring_flags()}",
                builder=builder,
                session=session,
            )

        self.assertEqual(session.get(first.id), first)
        self.assertIn("already has a process-memory", output)
        self.assertEqual(len(session.snapshot()), 1)

    def test_procedural_skill_authoring_receipt_expires_on_restart(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _, store, _, review = build_test_learning_outcome_review(root)
            builder = ProceduralSkillContractBuilder(
                memory_store=store,
                skill_library=SkillLibrary(root / "skills.jsonl"),
            )
            request = parse_procedural_skill_authoring_request(
                shlex.split(f"{review.lesson_memory_id} {_test_skill_authoring_flags()}")
            )
            blueprint = build_procedural_skill_authoring_blueprint(builder, request)
            session = OperatorReviewedProceduralSkillAuthoringSession()
            session.create(
                blueprint,
                token=procedural_skill_authoring_confirmation_token(blueprint),
            )
            restarted = OperatorReviewedProceduralSkillAuthoringSession()
            restarted_output = format_procedural_skill_authoring_command(
                "/experience learning skill-authoring-receipts",
                builder=builder,
                session=restarted,
            )

        self.assertEqual(len(session.snapshot()), 1)
        self.assertEqual(restarted.snapshot(), ())
        self.assertIn("Status: EMPTY", restarted_output)

    def test_procedural_skill_authoring_parser_fails_closed(self) -> None:
        with self.assertRaisesRegex(ProceduralSkillAuthoringError, "known_failure_modes"):
            parse_procedural_skill_authoring_request(
                shlex.split(
                    "mem_lesson --trigger when --precondition ready --step inspect "
                    "--permission read --verify done"
                )
            )
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _, store, _, review = build_test_learning_outcome_review(root)
            builder = ProceduralSkillContractBuilder(
                memory_store=store,
                skill_library=SkillLibrary(root / "skills.jsonl"),
            )
            session = OperatorReviewedProceduralSkillAuthoringSession()
            output = format_procedural_skill_authoring_command(
                f"/experience learning skill-authoring-confirm-preview "
                f"{review.lesson_memory_id} {_test_skill_authoring_flags()}; /skills list",
                builder=builder,
                session=session,
            )

        self.assertIn("Command chaining", output)
        self.assertEqual(session.snapshot(), ())

    def test_procedural_skill_authoring_rejects_terminal_lesson(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _, store, events, review, lifecycle, applies = (
                build_test_learning_lifecycle_transition(root, decision="reject")
            )
            apply_test_learning_lifecycle_transition(
                store, events, review, lifecycle, applies
            )
            output = format_procedural_skill_authoring_command(
                f"/experience learning skill-authoring-confirm-preview "
                f"{review.lesson_memory_id} {_test_skill_authoring_flags()}",
                builder=ProceduralSkillContractBuilder(
                    memory_store=store,
                    skill_library=SkillLibrary(root / "skills.jsonl"),
                ),
                session=OperatorReviewedProceduralSkillAuthoringSession(),
            )

        self.assertIn("Status: ERROR", output)
        self.assertIn("not eligible", output)
        self.assertIn("active", output)

    def test_procedural_skill_authoring_doctor_reports_source_drift(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _, store, _, review = build_test_learning_outcome_review(root)
            builder = ProceduralSkillContractBuilder(
                memory_store=store,
                skill_library=SkillLibrary(root / "skills.jsonl"),
            )
            request = parse_procedural_skill_authoring_request(
                shlex.split(f"{review.lesson_memory_id} {_test_skill_authoring_flags()}")
            )
            blueprint = build_procedural_skill_authoring_blueprint(builder, request)
            session = OperatorReviewedProceduralSkillAuthoringSession()
            session.create(
                blueprint,
                token=procedural_skill_authoring_confirmation_token(blueprint),
            )
            lesson = store.load_persistent_memory()[0]
            store.save_persistent_memory([replace(lesson, active=False)])
            report = session.doctor(builder)

        self.assertEqual(report.status, "WARN")
        self.assertEqual(report.drifted_count, 1)
        self.assertIn("historical", " ".join(report.warnings))

    def test_procedural_skill_authoring_doctor_detects_receipt_tamper(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _, store, _, review = build_test_learning_outcome_review(root)
            builder = ProceduralSkillContractBuilder(
                memory_store=store,
                skill_library=SkillLibrary(root / "skills.jsonl"),
            )
            request = parse_procedural_skill_authoring_request(
                shlex.split(f"{review.lesson_memory_id} {_test_skill_authoring_flags()}")
            )
            blueprint = build_procedural_skill_authoring_blueprint(builder, request)
            session = OperatorReviewedProceduralSkillAuthoringSession()
            receipt = session.create(
                blueprint,
                token=procedural_skill_authoring_confirmation_token(blueprint),
            )
            session._receipts[receipt.source_lesson_id] = replace(receipt, executable=True)
            report = session.doctor(builder)

        self.assertEqual(report.status, "ERROR")
        self.assertIn("no-writer boundary", " ".join(report.issues))

    def test_procedural_skill_authoring_shared_handler_uses_existing_proposal_gate(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            coordinator, store, _, review = build_test_learning_outcome_review(root)
            logger = SessionOperatorLogger(root / "session.jsonl", enabled=False)
            flags = _test_skill_authoring_flags()
            before = (store.working_path.read_bytes(), store.persistent_path.read_bytes())
            preview = process_interactive_input(
                f"/experience learning skill-authoring-confirm-preview "
                f"{review.lesson_memory_id} {flags}",
                coordinator=coordinator,
                session_logger=logger,
                project_root=root,
            )
            token = _id_from_output(preview, "Confirmation token:")
            output = process_interactive_input(
                f"/experience learning propose skill-contract {review.lesson_memory_id} "
                f"{token} {flags}",
                coordinator=coordinator,
                session_logger=logger,
                project_root=root,
            )
            receipt_output = process_interactive_input(
                f"/experience learning skill-authoring-receipt {review.lesson_memory_id}",
                coordinator=coordinator,
                session_logger=logger,
                project_root=root,
            )
            after = (store.working_path.read_bytes(), store.persistent_path.read_bytes())
            skill_path = root / "proto_mind" / "data" / "skills.jsonl"

        self.assertIn("OPERATOR AUTHORING RECORDED", output)
        self.assertIn("process_memory_only", receipt_output)
        self.assertEqual(before, after)
        self.assertFalse(skill_path.exists())
        self.assertEqual(logger.status().entry_count, 0)
        self.assertEqual(
            PROCEDURAL_SKILL_AUTHORING_MODE,
            "exact_operator_authored_process_memory_receipt",
        )
        self.assertTrue(PROCEDURAL_SKILL_WRITER_INSTALLED)
        self.assertFalse(PROCEDURAL_SKILL_EXECUTION_INSTALLED)
        self.assertEqual(
            classify_command(
                f"/experience learning propose skill-contract {review.lesson_memory_id} token"
            ).policy_class,
            "confirmation_required",
        )
        self.assertEqual(
            classify_command(
                f"/experience learning skill-authoring-confirm-preview {review.lesson_memory_id}"
            ).policy_class,
            "auto_allowed",
        )
        self.assertEqual(len(COMMAND_REGISTRY), 387)
        self.assertEqual(len({entry.category for entry in COMMAND_REGISTRY}), 41)
        self.assertEqual(command_registry_doctor()["status"], "OK")
        self.assertEqual(action_policy_doctor()["status"], "OK")

    def test_procedural_skill_readiness_doctor_is_empty_read_only(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _, store, _ = build_test_system(root)
            library = SkillLibrary(root / "skills.jsonl")
            reviewer = ProceduralSkillApplyReadiness(
                builder=ProceduralSkillContractBuilder(
                    memory_store=store,
                    skill_library=library,
                ),
                skill_library=library,
            )
            session = OperatorReviewedProceduralSkillAuthoringSession()
            before = (store.working_path.read_bytes(), store.persistent_path.read_bytes())
            output = format_procedural_skill_readiness_command(
                "/experience learning skill-apply-doctor",
                reviewer=reviewer,
                session=session,
            )
            after = (store.working_path.read_bytes(), store.persistent_path.read_bytes())
            skill_file_after_clean = library.skills_path.exists()
            library.skills_path.write_text("{malformed\n", encoding="utf-8")
            broken_output = format_procedural_skill_readiness_command(
                "/experience learning skill-apply-doctor",
                reviewer=reviewer,
                session=session,
            )

        self.assertIn("Status: OK", output)
        self.assertIn("receipts: 0", output)
        self.assertIn("skill_apply_engine_installed: true", output)
        self.assertEqual(before, after)
        self.assertFalse(skill_file_after_clean)
        self.assertIn("Status: ERROR", broken_output)
        self.assertIn("malformed JSONL", broken_output)

    def test_procedural_skill_readiness_revalidates_current_receipt_without_write(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _, store, _, library, builder, session, receipt = (
                build_test_procedural_skill_authoring(root)
            )
            reviewer = ProceduralSkillApplyReadiness(
                builder=builder,
                skill_library=library,
            )
            before = store.persistent_path.read_bytes()
            report = reviewer.review(receipt)
            after = store.persistent_path.read_bytes()

        self.assertEqual(report.status, "READY FOR SKILL APPLY DESIGN REVIEW")
        self.assertTrue(report.ready_for_design_review)
        self.assertTrue(all(report.checks.values()))
        self.assertEqual(report.current_authoring_hash, receipt.authoring_hash)
        self.assertEqual(len(report.skill_store_sha256), 64)
        self.assertEqual(
            report.contract.target_record_id,
            f"skilllearn_{receipt.authoring_hash[:16]}",
        )
        self.assertEqual(report.contract.expected_record_mutations, 1)
        self.assertTrue(report.apply_engine_installed)
        self.assertFalse(report.executable)
        self.assertEqual(before, after)
        self.assertFalse(library.skills_path.exists())
        self.assertEqual(len(session.snapshot()), 1)

    def test_procedural_skill_apply_plan_exposes_future_receipt_and_rollback_contract(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _, _, _, library, builder, session, receipt = (
                build_test_procedural_skill_authoring(root)
            )
            output = format_procedural_skill_readiness_command(
                f"/experience learning skill-apply-plan {receipt.id}",
                reviewer=ProceduralSkillApplyReadiness(
                    builder=builder,
                    skill_library=library,
                ),
                session=session,
            )

        self.assertIn("Status: READY FOR SKILL APPLY DESIGN REVIEW", output)
        self.assertIn("expected_record_mutations: 1", output)
        self.assertIn("atomic_write_required: true", output)
        self.assertIn("post_write_verification_required: true", output)
        self.assertIn("separate_confirmation_required: true", output)
        self.assertIn("rollback_suggestion: /skills archive skilllearn_", output)
        for field in PROCEDURAL_SKILL_FUTURE_RECEIPT_FIELDS:
            self.assertIn(f"- {field}", output)
        self.assertIn("no apply token was generated", output)

    def test_procedural_skill_readiness_handles_missing_receipt_cleanly(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _, store, _ = build_test_system(root)
            library = SkillLibrary(root / "skills.jsonl")
            output = format_procedural_skill_readiness_command(
                "/experience learning skill-apply-readiness missing",
                reviewer=ProceduralSkillApplyReadiness(
                    builder=ProceduralSkillContractBuilder(
                        memory_store=store,
                        skill_library=library,
                    ),
                    skill_library=library,
                ),
                session=OperatorReviewedProceduralSkillAuthoringSession(),
            )

        self.assertIn("Status: ERROR", output)
        self.assertIn("No process-memory skill authoring receipt", output)
        self.assertFalse(library.skills_path.exists())

    def test_procedural_skill_readiness_detects_source_drift(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _, store, _, library, builder, _, receipt = (
                build_test_procedural_skill_authoring(root)
            )
            lesson = store.load_persistent_memory()[0]
            store.save_persistent_memory([replace(lesson, active=False)])
            report = ProceduralSkillApplyReadiness(
                builder=builder,
                skill_library=library,
            ).review(receipt)

        self.assertEqual(report.status, "NOT READY")
        self.assertFalse(report.ready_for_design_review)
        self.assertFalse(report.checks["current_source_revalidated"])
        self.assertIn("revalidation failed", " ".join(report.issues))

    def test_procedural_skill_readiness_blocks_active_global_duplicate(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _, _, _, library, builder, _, receipt = build_test_procedural_skill_authoring(root)
            library.add_skill(
                receipt.authored_contract["name"],
                category="workflow",
                summary="Different summary, exact active name.",
            )
            report = ProceduralSkillApplyReadiness(
                builder=builder,
                skill_library=library,
            ).review(receipt)

        self.assertEqual(report.status, "NOT READY")
        self.assertFalse(report.checks["active_global_duplicate_absent"])
        self.assertEqual(len(report.active_duplicate_skill_ids), 1)
        self.assertIn("active global exact skill duplicate", " ".join(report.issues))

    def test_procedural_skill_readiness_warns_but_allows_archived_duplicate(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _, _, _, library, builder, _, receipt = build_test_procedural_skill_authoring(root)
            library.add_skill(
                receipt.authored_contract["name"],
                category="workflow",
                summary="Archived duplicate name.",
            )
            skill_id = str(library.read_snapshot()["records"][0]["id"])
            library.set_status(skill_id, "archived")
            report = ProceduralSkillApplyReadiness(
                builder=builder,
                skill_library=library,
            ).review(receipt)

        self.assertEqual(report.status, "READY FOR SKILL APPLY DESIGN REVIEW")
        self.assertTrue(report.checks["active_global_duplicate_absent"])
        self.assertEqual(report.archived_duplicate_skill_ids, [skill_id])
        self.assertIn("Archived exact skill duplicates", " ".join(report.warnings))

    def test_procedural_skill_readiness_fails_closed_on_malformed_skill_store(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _, _, _, library, builder, _, receipt = build_test_procedural_skill_authoring(root)
            library.skills_path.write_text("{malformed\n", encoding="utf-8")
            report = ProceduralSkillApplyReadiness(
                builder=builder,
                skill_library=library,
            ).review(receipt)

        self.assertEqual(report.status, "ERROR")
        self.assertFalse(report.checks["skill_store_well_formed"])
        self.assertFalse(report.ready_for_design_review)

    def test_procedural_skill_readiness_fails_closed_on_receipt_tamper(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _, _, _, library, builder, _, receipt = build_test_procedural_skill_authoring(root)
            tampered = replace(receipt, persistence_performed=True)
            report = ProceduralSkillApplyReadiness(
                builder=builder,
                skill_library=library,
            ).review(tampered)

        self.assertEqual(report.status, "ERROR")
        self.assertFalse(report.checks["authoring_receipt_safe"])
        self.assertFalse(report.ready_for_design_review)

    def test_procedural_skill_readiness_shared_handler_is_read_only_and_registered(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            coordinator, store, _, review = build_test_learning_outcome_review(root)
            logger = SessionOperatorLogger(root / "session.jsonl", enabled=False)
            flags = _test_skill_authoring_flags()
            preview = process_interactive_input(
                f"/experience learning skill-authoring-confirm-preview "
                f"{review.lesson_memory_id} {flags}",
                coordinator=coordinator,
                session_logger=logger,
                project_root=root,
            )
            token = _id_from_output(preview, "Confirmation token:")
            process_interactive_input(
                f"/experience learning propose skill-contract {review.lesson_memory_id} "
                f"{token} {flags}",
                coordinator=coordinator,
                session_logger=logger,
                project_root=root,
            )
            before = (store.working_path.read_bytes(), store.persistent_path.read_bytes())
            output = process_interactive_input(
                f"/experience learning skill-apply-readiness {review.lesson_memory_id}",
                coordinator=coordinator,
                session_logger=logger,
                project_root=root,
            )
            plan = process_interactive_input(
                f"/experience learning skill-apply-plan {review.lesson_memory_id}",
                coordinator=coordinator,
                session_logger=logger,
                project_root=root,
            )
            after = (store.working_path.read_bytes(), store.persistent_path.read_bytes())
            skill_path = root / "proto_mind" / "data" / "skills.jsonl"

        self.assertIn("READY FOR SKILL APPLY DESIGN REVIEW", output)
        self.assertIn("Required future receipt fields:", plan)
        self.assertEqual(before, after)
        self.assertFalse(skill_path.exists())
        self.assertEqual(logger.status().entry_count, 0)
        self.assertEqual(
            PROCEDURAL_SKILL_READINESS_MODE,
            "read_only_current_skill_contract_revalidation",
        )
        self.assertTrue(PROCEDURAL_SKILL_APPLY_ENGINE_INSTALLED)
        self.assertEqual(
            classify_command(
                f"/experience learning skill-apply-readiness {review.lesson_memory_id}"
            ).policy_class,
            "auto_allowed",
        )
        self.assertEqual(len(COMMAND_REGISTRY), 387)
        self.assertEqual(len({entry.category for entry in COMMAND_REGISTRY}), 41)
        self.assertEqual(command_registry_doctor()["status"], "OK")
        self.assertEqual(action_policy_doctor()["status"], "OK")

    def test_procedural_skill_apply_status_and_doctor_are_empty_without_write(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _, store, _ = build_test_system(root)
            library = SkillLibrary(root / "skills.jsonl")
            reviewer = ProceduralSkillApplyReadiness(
                builder=ProceduralSkillContractBuilder(
                    memory_store=store,
                    skill_library=library,
                ),
                skill_library=library,
            )
            session = OperatorReviewedProceduralSkillApplySession()
            before = store.persistent_path.read_bytes()
            status = format_procedural_skill_apply_command(
                "/experience learning skill-apply-status",
                authoring_session=OperatorReviewedProceduralSkillAuthoringSession(),
                apply_session=session,
                reviewer=reviewer,
            )
            doctor = format_procedural_skill_apply_command(
                "/experience learning skill-apply-pilot-doctor",
                authoring_session=OperatorReviewedProceduralSkillAuthoringSession(),
                apply_session=session,
                reviewer=reviewer,
            )
            after = store.persistent_path.read_bytes()
            skill_exists = library.skills_path.exists()

        self.assertIn("Status: OK", status)
        self.assertIn("receipts: 0/1", status)
        self.assertIn("apply_engine_installed: true", status)
        self.assertIn("Status: OK", doctor)
        self.assertEqual(after, before)
        self.assertFalse(skill_exists)
        self.assertEqual(PROCEDURAL_SKILL_APPLY_MAX_RECEIPTS, 1)
        self.assertEqual(
            PROCEDURAL_SKILL_APPLY_MODE,
            "single_exact_confirmed_atomic_skill_append",
        )
        self.assertFalse(PROCEDURAL_SKILL_EXECUTION_ENABLED)

    def test_procedural_skill_apply_preview_issues_second_token_without_write(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _, store, _, library, builder, authoring, receipt = (
                build_test_procedural_skill_authoring(root)
            )
            reviewer = ProceduralSkillApplyReadiness(builder=builder, skill_library=library)
            apply_session = OperatorReviewedProceduralSkillApplySession()
            before = store.persistent_path.read_bytes()
            output = format_procedural_skill_apply_command(
                f"/experience learning skill-apply-confirm-preview {receipt.id}",
                authoring_session=authoring,
                apply_session=apply_session,
                reviewer=reviewer,
            )
            after = store.persistent_path.read_bytes()
            skill_exists = library.skills_path.exists()

        self.assertIn("Status: CONFIRMABLE", output)
        self.assertIn("Confirmation token: CONFIRM-SKILL-APPLY-", output)
        self.assertIn("expected_record_mutations: 1", output)
        self.assertEqual(after, before)
        self.assertFalse(skill_exists)
        self.assertEqual(apply_session.snapshot(), ())

    def test_procedural_skill_apply_wrong_token_refuses_without_mutation(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _, store, _, library, builder, authoring, receipt = (
                build_test_procedural_skill_authoring(root)
            )
            apply_session = OperatorReviewedProceduralSkillApplySession()
            before = store.persistent_path.read_bytes()
            output = format_procedural_skill_apply_command(
                f"/experience learning apply skill {receipt.id} WRONG-TOKEN",
                authoring_session=authoring,
                apply_session=apply_session,
                reviewer=ProceduralSkillApplyReadiness(
                    builder=builder,
                    skill_library=library,
                ),
            )
            after = store.persistent_path.read_bytes()
            skill_exists = library.skills_path.exists()

        self.assertIn("Status: ERROR", output)
        self.assertIn("token mismatch", output)
        self.assertEqual(after, before)
        self.assertFalse(skill_exists)
        self.assertEqual(apply_session.snapshot(), ())

    def test_procedural_skill_apply_writes_one_verified_non_executable_record(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _, store, _, library, builder, authoring, receipt = (
                build_test_procedural_skill_authoring(root)
            )
            library.add_skill("Existing unrelated skill", summary="Must remain unchanged.")
            records_before = library.read_snapshot()["records"]
            reviewer = ProceduralSkillApplyReadiness(builder=builder, skill_library=library)
            apply_session = OperatorReviewedProceduralSkillApplySession()
            memory_before = store.persistent_path.read_bytes()
            token = procedural_skill_apply_confirmation_token(
                apply_session.review(receipt, reviewer=reviewer)
            )
            output = format_procedural_skill_apply_command(
                f"/experience learning apply skill {receipt.id} {token}",
                authoring_session=authoring,
                apply_session=apply_session,
                reviewer=reviewer,
            )
            records = library.read_snapshot()["records"]
            applied = apply_session.get(receipt.id)
            memory_after = store.persistent_path.read_bytes()

        self.assertIn("Status: APPLIED AND VERIFIED", output)
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0], records_before[0])
        self.assertEqual(records[1]["id"], f"skilllearn_{receipt.authoring_hash[:16]}")
        self.assertEqual(records[1]["schema"], "skill.procedure.v1")
        self.assertEqual(records[1]["source_lesson_id"], receipt.source_lesson_id)
        self.assertEqual(records[1]["authoring_receipt_id"], receipt.id)
        self.assertEqual(records[1]["source"], "experience_learning_skill_apply")
        self.assertFalse(records[1]["executable"])
        self.assertEqual(memory_after, memory_before)
        self.assertIsNotNone(applied)
        self.assertEqual(applied.exact_record_mutations, 1)
        self.assertTrue(applied.record_verified)
        self.assertTrue(applied.source_provenance_verified)
        self.assertFalse(applied.target_execution_performed)
        self.assertEqual(len(applied.receipt_hash), 64)

    def test_procedural_skill_apply_run_once_refuses_second_write(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _, _, _, library, builder, authoring, receipt = (
                build_test_procedural_skill_authoring(root)
            )
            reviewer = ProceduralSkillApplyReadiness(builder=builder, skill_library=library)
            apply_session = OperatorReviewedProceduralSkillApplySession()
            token = procedural_skill_apply_confirmation_token(
                apply_session.review(receipt, reviewer=reviewer)
            )
            apply_session.apply(receipt, token=token, reviewer=reviewer)
            before = library.skills_path.read_bytes()
            output = format_procedural_skill_apply_command(
                f"/experience learning apply skill {receipt.id} {token}",
                authoring_session=authoring,
                apply_session=apply_session,
                reviewer=reviewer,
            )
            after = library.skills_path.read_bytes()

        self.assertIn("Status: ERROR", output)
        self.assertIn("already applied", output)
        self.assertEqual(after, before)
        self.assertEqual(len(apply_session.snapshot()), 1)

    def test_procedural_skill_apply_stale_preview_token_refuses_store_drift(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _, _, _, library, builder, authoring, receipt = (
                build_test_procedural_skill_authoring(root)
            )
            reviewer = ProceduralSkillApplyReadiness(builder=builder, skill_library=library)
            apply_session = OperatorReviewedProceduralSkillApplySession()
            token = procedural_skill_apply_confirmation_token(
                apply_session.review(receipt, reviewer=reviewer)
            )
            library.add_skill("Unrelated current skill", summary="Store drift fixture")
            before = library.skills_path.read_bytes()
            output = format_procedural_skill_apply_command(
                f"/experience learning apply skill {receipt.id} {token}",
                authoring_session=authoring,
                apply_session=apply_session,
                reviewer=reviewer,
            )
            after = library.skills_path.read_bytes()
            record_count = len(library.read_snapshot()["records"])

        self.assertIn("Status: ERROR", output)
        self.assertIn("token mismatch", output)
        self.assertEqual(after, before)
        self.assertEqual(record_count, 1)
        self.assertEqual(apply_session.snapshot(), ())

    def test_procedural_skill_apply_preview_blocks_active_duplicate(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _, _, _, library, builder, authoring, receipt = (
                build_test_procedural_skill_authoring(root)
            )
            library.add_skill(
                receipt.authored_contract["name"],
                summary="Active duplicate before apply.",
            )
            output = format_procedural_skill_apply_command(
                f"/experience learning skill-apply-confirm-preview {receipt.id}",
                authoring_session=authoring,
                apply_session=OperatorReviewedProceduralSkillApplySession(),
                reviewer=ProceduralSkillApplyReadiness(
                    builder=builder,
                    skill_library=library,
                ),
            )
            record_count = len(library.read_snapshot()["records"])

        self.assertIn("Status: NOT CONFIRMABLE", output)
        self.assertIn("active global exact skill duplicate", output)
        self.assertNotIn("Confirmation token:", output)
        self.assertEqual(record_count, 1)

    def test_procedural_skill_apply_verification_failure_restores_exact_bytes(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _, store, _, library, builder, _, receipt = build_test_procedural_skill_authoring(root)
            library.add_skill("Existing rollback sentinel", summary="Exact bytes must survive.")
            skill_before = library.skills_path.read_bytes()
            reviewer = ProceduralSkillApplyReadiness(builder=builder, skill_library=library)
            apply_session = OperatorReviewedProceduralSkillApplySession()
            token = procedural_skill_apply_confirmation_token(
                apply_session.review(receipt, reviewer=reviewer)
            )
            memory_before = store.persistent_path.read_bytes()
            with patch(
                "proto_mind.experience_learning_skill_apply._verify_skill_write",
                side_effect=ProceduralSkillApplyError("forced verification failure"),
            ):
                with self.assertRaises(ProceduralSkillApplyError):
                    apply_session.apply(receipt, token=token, reviewer=reviewer)
            skill_after = library.skills_path.read_bytes()
            memory_after = store.persistent_path.read_bytes()

        self.assertEqual(skill_after, skill_before)
        self.assertEqual(memory_after, memory_before)
        self.assertEqual(apply_session.snapshot(), ())

    def test_procedural_skill_apply_doctor_tracks_historical_target(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _, _, _, library, builder, _, receipt = build_test_procedural_skill_authoring(root)
            reviewer = ProceduralSkillApplyReadiness(builder=builder, skill_library=library)
            apply_session = OperatorReviewedProceduralSkillApplySession()
            token = procedural_skill_apply_confirmation_token(
                apply_session.review(receipt, reviewer=reviewer)
            )
            applied = apply_session.apply(receipt, token=token, reviewer=reviewer)
            healthy = apply_session.doctor(reviewer=reviewer)
            library.set_status(applied.created_skill_id, "archived")
            historical = apply_session.doctor(reviewer=reviewer)

        self.assertEqual(healthy.status, "OK")
        self.assertEqual(healthy.verified_current_count, 1)
        self.assertEqual(historical.status, "WARN")
        self.assertEqual(historical.historical_count, 1)
        self.assertIn("missing or has changed", " ".join(historical.warnings))

    def test_procedural_skill_apply_shared_handler_uses_exact_registry_gate(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            coordinator, store, _, review = build_test_learning_outcome_review(root)
            logger = SessionOperatorLogger(root / "session.jsonl", enabled=False)
            flags = _test_skill_authoring_flags()
            authoring_preview = process_interactive_input(
                f"/experience learning skill-authoring-confirm-preview "
                f"{review.lesson_memory_id} {flags}",
                coordinator=coordinator,
                session_logger=logger,
                project_root=root,
            )
            authoring_token = _id_from_output(authoring_preview, "Confirmation token:")
            process_interactive_input(
                f"/experience learning propose skill-contract {review.lesson_memory_id} "
                f"{authoring_token} {flags}",
                coordinator=coordinator,
                session_logger=logger,
                project_root=root,
            )
            memory_before = store.persistent_path.read_bytes()
            apply_preview = process_interactive_input(
                f"/experience learning skill-apply-confirm-preview {review.lesson_memory_id}",
                coordinator=coordinator,
                session_logger=logger,
                project_root=root,
            )
            apply_token = _id_from_output(apply_preview, "Confirmation token:")
            applied = process_interactive_input(
                f"/experience learning apply skill {review.lesson_memory_id} {apply_token}",
                coordinator=coordinator,
                session_logger=logger,
                project_root=root,
            )
            skill_path = root / "proto_mind" / "data" / "skills.jsonl"
            records = SkillLibrary(skill_path).read_snapshot()["records"]
            why = process_interactive_input(
                f"/skills why {records[0]['id']}",
                coordinator=coordinator,
                session_logger=logger,
                project_root=root,
            )
            provenance_doctor = process_interactive_input(
                "/skills provenance-doctor",
                coordinator=coordinator,
                session_logger=logger,
                project_root=root,
            )
            memory_after = store.persistent_path.read_bytes()

        self.assertIn("Status: APPLIED AND VERIFIED", applied)
        self.assertEqual(len(records), 1)
        self.assertIn("Status: VERIFIED", why)
        self.assertIn("Status: OK", provenance_doctor)
        self.assertIn("verified: 1", provenance_doctor)
        self.assertEqual(memory_after, memory_before)
        self.assertEqual(logger.status().entry_count, 0)
        self.assertEqual(
            classify_command(
                f"/experience learning apply skill {review.lesson_memory_id} token"
            ).policy_class,
            "confirmation_required",
        )
        self.assertEqual(
            classify_command(
                f"/experience learning skill-apply-confirm-preview {review.lesson_memory_id}"
            ).policy_class,
            "auto_allowed",
        )
        self.assertEqual(len(COMMAND_REGISTRY), 387)
        self.assertEqual(len({entry.category for entry in COMMAND_REGISTRY}), 41)
        self.assertEqual(command_registry_doctor()["status"], "OK")
        self.assertEqual(action_policy_doctor()["status"], "OK")

    def test_procedural_skill_apply_embeds_restart_safe_provenance(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store, library, receipt, _ = build_test_applied_procedural_skill(Path(temp_dir))
            record = library.read_snapshot()["records"][0]
            provenance = record["provenance"]
            check = verify_procedural_skill_provenance(
                record,
                memory_records=store.load_persistent_memory(),
            )

        self.assertEqual(provenance["schema"], PROCEDURAL_SKILL_PROVENANCE_SCHEMA)
        self.assertEqual(provenance["authoring_hash"], receipt.authoring_hash)
        self.assertEqual(provenance["authoring_receipt_id"], receipt.id)
        self.assertEqual(len(provenance["apply_confirmation_token_hash"]), 64)
        self.assertEqual(provenance["persistence"], "embedded_skill_record")
        self.assertFalse(provenance["automatic_apply"])
        self.assertFalse(provenance["executable"])
        self.assertEqual(check.status, "VERIFIED")
        self.assertTrue(check.verified)

    def test_procedural_skill_outcome_needs_exact_evidence_and_ignores_uses(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store, library, _, _ = build_test_applied_procedural_skill(Path(temp_dir))
            record = library.read_snapshot()["records"][0]
            record["uses"] = 99
            reviewer = ProceduralSkillOutcomeReviewer(
                [],
                [record],
                store.load_persistent_memory(),
            )
            review = reviewer.review(str(record["id"]))
            output = format_procedural_skill_outcome_command(
                f"/experience learning skill-outcome-review {record['id']}",
                events=[],
                memory_store=store,
                skill_library=library,
            )

        self.assertEqual(review.status, "NEEDS_MORE_EVIDENCE")
        self.assertEqual(review.matching_manual_use_count, 0)
        self.assertTrue(review.uses_metric_ignored)
        self.assertFalse(review.mutation_performed)
        self.assertIn("do not infer one from uses", output)

    def test_procedural_skill_outcome_finds_verified_success_candidate(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store, library, _, _ = build_test_applied_procedural_skill(Path(temp_dir))
            record = library.read_snapshot()["records"][0]
            events = build_test_procedural_skill_outcome_events(record, outcome="success")
            review = ProceduralSkillOutcomeReviewer(
                events,
                [record],
                store.load_persistent_memory(),
            ).review(str(record["id"]))

        self.assertEqual(review.status, "SUCCESS_CANDIDATE")
        self.assertEqual(review.matching_manual_use_count, 1)
        self.assertEqual([signal.signal for signal in review.signals], ["SUCCESS_EVIDENCE"])
        self.assertTrue(review.checks["proto_mind_execution_absent"])
        self.assertFalse(review.skill_execution_performed)

    def test_procedural_skill_outcome_finds_operator_reported_failure(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store, library, _, _ = build_test_applied_procedural_skill(Path(temp_dir))
            record = library.read_snapshot()["records"][0]
            events = build_test_procedural_skill_outcome_events(record, outcome="failure")
            review = ProceduralSkillOutcomeReviewer(
                events,
                [record],
                store.load_persistent_memory(),
            ).review(str(record["id"]))

        self.assertEqual(review.status, "FAILURE_CANDIDATE")
        self.assertEqual([signal.signal for signal in review.signals], ["FAILURE_EVIDENCE"])

    def test_procedural_skill_outcome_keeps_mixed_evidence_inconclusive(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store, library, _, _ = build_test_applied_procedural_skill(Path(temp_dir))
            record = library.read_snapshot()["records"][0]
            events = build_test_procedural_skill_outcome_events(record, outcome="mixed")
            review = ProceduralSkillOutcomeReviewer(
                events,
                [record],
                store.load_persistent_memory(),
            ).review(str(record["id"]))

        self.assertEqual(review.status, "MIXED_EVIDENCE")
        self.assertEqual(
            {signal.signal for signal in review.signals},
            {"SUCCESS_EVIDENCE", "FAILURE_EVIDENCE"},
        )
        self.assertIn("no automatic conclusion", " ".join(review.warnings))

    def test_procedural_skill_outcome_refuses_proto_mind_execution_claim(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store, library, _, _ = build_test_applied_procedural_skill(Path(temp_dir))
            record = library.read_snapshot()["records"][0]
            events = build_test_procedural_skill_outcome_events(
                record,
                outcome="success",
                execution_performed_by_proto_mind=True,
            )
            review = ProceduralSkillOutcomeReviewer(
                events,
                [record],
                store.load_persistent_memory(),
            ).review(str(record["id"]))

        self.assertEqual(review.status, "ERROR")
        self.assertFalse(review.checks["proto_mind_execution_absent"])
        self.assertIn("execution_performed_by_proto_mind=false", " ".join(review.issues))

    def test_procedural_skill_outcome_refuses_drifted_confirmed_payload(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store, library, _, applied = build_test_applied_procedural_skill(Path(temp_dir))
            library.set_body(applied.created_skill_id, "Changed after operator confirmation.")
            record = library.read_snapshot()["records"][0]
            events = build_test_procedural_skill_outcome_events(record, outcome="success")
            review = ProceduralSkillOutcomeReviewer(
                events,
                [record],
                store.load_persistent_memory(),
            ).review(str(record["id"]))

        self.assertEqual(review.status, "ERROR")
        self.assertFalse(review.checks["confirmed_payload_current"])
        self.assertIn("operator-confirmed", " ".join(review.issues))

    def test_procedural_skill_outcome_doctor_is_read_only(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store, library, _, _ = build_test_applied_procedural_skill(Path(temp_dir))
            record = library.read_snapshot()["records"][0]
            events = build_test_procedural_skill_outcome_events(record, outcome="success")
            skill_before = library.skills_path.read_bytes()
            memory_before = store.persistent_path.read_bytes()
            reviewer = ProceduralSkillOutcomeReviewer(
                events,
                [record],
                store.load_persistent_memory(),
            )
            report = reviewer.doctor()
            output = format_procedural_skill_outcome_command(
                "/experience learning skill-outcome-doctor",
                events=events,
                memory_store=store,
                skill_library=library,
            )
            skill_after = library.skills_path.read_bytes()
            memory_after = store.persistent_path.read_bytes()

        self.assertEqual(report.status, "OK")
        self.assertEqual(report.provenanced_skill_count, 1)
        self.assertEqual(report.reviewable_skill_count, 1)
        self.assertIn("Status: OK", output)
        self.assertIn(PROCEDURAL_SKILL_OUTCOME_MODE, output)
        self.assertEqual(skill_after, skill_before)
        self.assertEqual(memory_after, memory_before)

    def test_procedural_skill_outcome_commands_handle_unknown_and_corrupt_skill_store(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _, store, _ = build_test_system(root)
            library = SkillLibrary(root / "skills.jsonl")
            missing = format_procedural_skill_outcome_command(
                "/experience learning skill-outcome-review missing",
                events=[],
                memory_store=store,
                skill_library=library,
            )
            library.skills_path.write_text("not-json\n", encoding="utf-8")
            doctor = format_procedural_skill_outcome_command(
                "/experience learning skill-outcome-doctor",
                events=[],
                memory_store=store,
                skill_library=library,
            )

        self.assertIn("Status: NOT_FOUND", missing)
        self.assertIn("Status: ERROR", doctor)
        self.assertIn("malformed JSONL", doctor)

    def test_procedural_skill_outcome_shared_handler_and_registry_are_safe(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            coordinator, store, _ = build_test_system(root / "proto_mind")
            logger = SessionOperatorLogger(root / "session.jsonl", enabled=False)
            memory_before = store.persistent_path.read_bytes()
            output = process_interactive_input(
                "/experience learning skill-outcome-doctor",
                coordinator=coordinator,
                session_logger=logger,
                project_root=root,
            )
            memory_after = store.persistent_path.read_bytes()

        self.assertIn("Procedural Skill Outcome Doctor v1", output)
        self.assertIn("procedure_execution_enabled: false", output)
        self.assertEqual(memory_after, memory_before)
        self.assertEqual(logger.status().entry_count, 0)
        self.assertEqual(PROCEDURAL_SKILL_OUTCOME_STATUSES, {
            "SUCCESS_CANDIDATE",
            "FAILURE_CANDIDATE",
            "MIXED_EVIDENCE",
            "NEEDS_MORE_EVIDENCE",
            "NOT_FOUND",
            "ERROR",
        })
        self.assertEqual(len(COMMAND_REGISTRY), 387)
        self.assertEqual(len({entry.category for entry in COMMAND_REGISTRY}), 41)
        self.assertEqual(
            classify_command(
                "/experience learning skill-outcome-review skilllearn_example"
            ).policy_class,
            "auto_allowed",
        )
        self.assertEqual(command_registry_doctor()["status"], "OK")
        self.assertEqual(action_policy_doctor()["status"], "OK")
