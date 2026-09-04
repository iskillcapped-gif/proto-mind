"""Core flow checks: learning."""
from __future__ import annotations

import unittest
from proto_mind.tests.flow_fixtures import (
    COMMAND_REGISTRY,
    Coordinator,
    ExperienceEvent,
    ExperienceTraceBuilder,
    LEARNING_APPLY_ENGINE_INSTALLED,
    LEARNING_DECISION_MAX_RECEIPTS,
    LEARNING_ELIGIBILITY_MAX_IDS_PER_KIND,
    LEARNING_LIFECYCLE_APPLY_ENGINE_INSTALLED,
    LEARNING_LIFECYCLE_APPLY_MAX_RECEIPTS,
    LEARNING_LIFECYCLE_APPLY_MODE,
    LEARNING_LIFECYCLE_AUDIT_MODE,
    LEARNING_LIFECYCLE_MAX_RECEIPTS,
    LEARNING_LIFECYCLE_MODE,
    LEARNING_LIFECYCLE_READINESS_MODE,
    LEARNING_MEMORY_APPLY_ENGINE_INSTALLED,
    LEARNING_MEMORY_APPLY_MAX_RECEIPTS,
    LEARNING_OUTCOME_MODE,
    LEARNING_OUTCOME_STATUSES,
    LEARNING_PROPOSAL_MAX_RECEIPTS,
    LearningEligibilityRequest,
    LearningLifecycleApplyReadiness,
    LearningLifecycleTransitionAudit,
    LearningOutcomeReviewer,
    LearningPromotionApplyReadiness,
    LearningPromotionEligibilityReviewer,
    LearningPromotionProposalBuilder,
    LearningProposalError,
    MEMORY_LESSON_PROVENANCE_SCHEMA,
    MemoryKeeper,
    MemoryRecord,
    MemoryStore,
    MockReasoner,
    Observer,
    OperatorReviewedLearningBridge,
    OperatorReviewedLearningDecisionSession,
    OperatorReviewedLearningLifecycleApplySession,
    OperatorReviewedLearningLifecycleSession,
    PERSISTENT_EXPERIENCE_COMMAND_PREFIXES,
    Path,
    REDACTION_PREFIX,
    SessionOperatorLogger,
    SimpleNamespace,
    SkillLibrary,
    SupervisedExperiencePilot,
    TemporaryDirectory,
    UTC,
    _correction_event,
    _id_from_output,
    _replacement_events,
    action_policy_doctor,
    apply_test_learning_lifecycle_transition,
    apply_test_learning_proposal,
    build_learning_lesson_provenance,
    build_test_experience_events,
    build_test_learning_apply,
    build_test_learning_candidate,
    build_test_learning_lifecycle_transition,
    build_test_learning_outcome_review,
    build_test_learning_proposal,
    build_test_system,
    classify_command,
    command_registry_doctor,
    datetime,
    deepcopy,
    format_experience_pilot_command,
    format_learning_apply_readiness_command,
    format_learning_bridge_doctor,
    format_learning_bridge_preview,
    format_learning_decision_command,
    format_learning_eligibility_command,
    format_learning_lifecycle_apply_command,
    format_learning_lifecycle_audit_command,
    format_learning_lifecycle_benchmark,
    format_learning_lifecycle_command,
    format_learning_lifecycle_readiness_command,
    format_learning_memory_apply_command,
    format_learning_outcome_benchmark,
    format_learning_outcome_command,
    format_learning_proposal_command,
    format_memory_command,
    get_experience_pilot,
    json,
    learning_confirmation_token,
    learning_lifecycle_apply_confirmation_token,
    learning_lifecycle_confirmation_token,
    learning_lifecycle_transition_contract,
    learning_proposal_confirmation_token,
    patch,
    peek_experience_pilot,
    process_interactive_input,
    replace,
    run_learning_lifecycle_benchmark,
    run_learning_outcome_benchmark,
    timedelta,
    verify_memory_provenance,
)


class LearningFlowTests(unittest.TestCase):
    def test_learning_bridge_empty_state_is_read_only_and_healthy(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            owner = SimpleNamespace()
            pilot = get_experience_pilot(owner, project_root=root)
            before = json.dumps(pilot.snapshot(), sort_keys=True)

            status = format_experience_pilot_command(
                "/experience learning status", owner=owner, project_root=root
            )
            preview = format_experience_pilot_command(
                "/experience learning preview", owner=owner, project_root=root
            )
            doctor = format_experience_pilot_command(
                "/experience learning doctor", owner=owner, project_root=root
            )
            after = json.dumps(pilot.snapshot(), sort_keys=True)

        self.assertIn("Status: EMPTY", status)
        self.assertIn("Status: EMPTY", preview)
        self.assertIn("Status: OK", doctor)
        self.assertEqual(before, after)
        self.assertEqual(list(root.rglob("*")), [])

    def test_learning_bridge_does_not_invent_candidate_for_clean_turn(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            coordinator, _, _ = build_test_system(root / "cognitive")
            pilot = SupervisedExperiencePilot(root, session_id="learning-clean")
            pilot.preview()
            pilot.consent(pilot.expected_consent_phrase)
            user_input = "Explain the current Proto-Mind architecture briefly."
            pilot.observe_normal_turn(user_input, coordinator.handle(user_input))

            output = format_learning_bridge_preview(
                OperatorReviewedLearningBridge(pilot.snapshot())
            )

        self.assertIn("Status: NO CANDIDATE", output)
        self.assertIn("A clean cognitive turn is not treated as a reusable lesson", output)
        self.assertIn("no LLM summarization", output)

    def test_learning_bridge_previews_applied_correction_with_exact_evidence(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            coordinator, _, _ = build_test_system(root / "cognitive")
            coordinator.pending_correction_hints = [
                "Use the active SQLite decision as current state."
            ]
            pilot = SupervisedExperiencePilot(root, session_id="learning-correction")
            pilot.preview()
            pilot.consent(pilot.expected_consent_phrase)
            user_input = "Explain the current storage decision."
            pilot.observe_normal_turn(user_input, coordinator.handle(user_input))

            bridge = OperatorReviewedLearningBridge(pilot.snapshot())
            review = bridge.review()[0]
            output = format_learning_bridge_preview(bridge)

        self.assertEqual(len(review.candidates), 1)
        candidate = review.candidates[0]
        self.assertEqual(candidate.review_status, "operator_review_required")
        self.assertEqual(candidate.source_kinds, ["correction_guidance"])
        self.assertTrue(candidate.evidence_event_ids[0].endswith("correction_guidance_applied"))
        self.assertFalse(candidate.promotion_ready)
        self.assertFalse(candidate.auto_apply_allowed)
        self.assertFalse(candidate.persistence_performed)
        self.assertIn("Status: REVIEW REQUIRED", output)
        self.assertIn("Use the active SQLite decision", output)
        self.assertIn("operator_confirmation_required: true", output)

    def test_learning_bridge_deduplicates_diagnostic_findings_conservatively(self) -> None:
        with TemporaryDirectory() as temp_dir:
            events = [
                event.to_dict()
                for event in build_test_experience_events(Path(temp_dir))
            ]
        finding = "Response needs source verification before reuse."
        for event in events:
            if event["event_type"] == "reflection_evaluated":
                event["payload"]["warning_count"] = 1
                event["payload"]["warning_previews"] = [finding]
                event["payload"]["overall_confidence"] = "medium"
            if event["event_type"] == "grounding_evaluated":
                event["payload"]["warning_count"] = 1
                event["payload"]["warning_previews"] = [finding]
                event["payload"]["confidence"] = 0.7

        review = OperatorReviewedLearningBridge(events).review()[0]

        self.assertEqual(len(review.candidates), 1)
        candidate = review.candidates[0]
        self.assertEqual(candidate.review_status, "needs_more_evidence")
        self.assertEqual(
            candidate.source_kinds,
            ["reflection_warning", "grounding_warning"],
        )
        self.assertEqual(len(candidate.evidence_event_ids), 2)
        self.assertEqual(candidate.confidence, "medium")
        self.assertEqual(candidate.suggested_target, "review_only")

    def test_learning_bridge_selector_and_invalid_trace_fail_cleanly(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            events = build_test_experience_events(root, turn_id=1, trace_id="learn-one")
            events += build_test_experience_events(root, turn_id=2, trace_id="learn-two")
            bridge = OperatorReviewedLearningBridge(events)
            selected = format_learning_bridge_preview(bridge, selector="1")
            missing = format_learning_bridge_preview(bridge, selector="99")
            broken = [event.to_dict() for event in events]
            broken[1]["source_event_ids"] = ["evt_missing"]
            doctor = format_learning_bridge_doctor(OperatorReviewedLearningBridge(broken))

        self.assertIn("turn_id: 1", selected)
        self.assertIn("Status: NOT FOUND", missing)
        self.assertIn("Available turns: 1, 2", missing)
        self.assertIn("Status: ERROR", doctor)
        self.assertIn("missing or later source event", doctor)

    def test_learning_bridge_preserves_privacy_redaction(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            coordinator, _, _ = build_test_system(root / "cognitive")
            secret = "learning-bridge-secret-value"
            coordinator.pending_correction_hints = [
                f"Review credential before reuse. password={secret}"
            ]
            pilot = SupervisedExperiencePilot(root, session_id="learning-redaction")
            pilot.preview()
            pilot.consent(pilot.expected_consent_phrase)
            user_input = "Explain safe credential handling."
            pilot.observe_normal_turn(user_input, coordinator.handle(user_input))

            output = format_learning_bridge_preview(
                OperatorReviewedLearningBridge(pilot.snapshot())
            )

        self.assertNotIn(secret, output)
        self.assertIn(REDACTION_PREFIX, output)
        self.assertIn("Status: REVIEW REQUIRED", output)

    def test_learning_bridge_shared_handler_does_not_mutate_evidence_or_stores(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            coordinator, store, _ = build_test_system(root / "cognitive")
            logger = SessionOperatorLogger(root / "session.jsonl", enabled=False)
            process_interactive_input(
                "/experience preview",
                coordinator=coordinator,
                session_logger=logger,
                project_root=root,
            )
            pilot = peek_experience_pilot(coordinator)
            process_interactive_input(
                f"/experience consent {pilot.expected_consent_phrase}",
                coordinator=coordinator,
                session_logger=logger,
                project_root=root,
            )
            coordinator.pending_correction_hints = ["Verify active decisions before reuse."]
            process_interactive_input(
                "Explain the current decision.",
                coordinator=coordinator,
                session_logger=logger,
                project_root=root,
            )
            before_snapshot = json.dumps(pilot.snapshot(), sort_keys=True)
            before_working = store.working_path.read_bytes()
            before_persistent = store.persistent_path.read_bytes()

            status = process_interactive_input(
                "/experience learning status",
                coordinator=coordinator,
                session_logger=logger,
                project_root=root,
            )
            preview = process_interactive_input(
                "/experience   learning   preview   latest",
                coordinator=coordinator,
                session_logger=logger,
                project_root=root,
            )
            doctor = process_interactive_input(
                "/experience learning doctor",
                coordinator=coordinator,
                session_logger=logger,
                project_root=root,
            )
            after_snapshot = json.dumps(pilot.snapshot(), sort_keys=True)
            after_working = store.working_path.read_bytes()
            after_persistent = store.persistent_path.read_bytes()

        self.assertIn("candidates: 1", status)
        self.assertIn("Status: REVIEW REQUIRED", preview)
        self.assertIn("Status: OK", doctor)
        self.assertEqual(before_snapshot, after_snapshot)
        self.assertEqual(before_working, after_working)
        self.assertEqual(before_persistent, after_persistent)

    def test_learning_bridge_registry_policy_and_no_apply_boundary(self) -> None:
        registry = {spec.prefix: spec for spec in COMMAND_REGISTRY}
        spec = registry["/experience learning"]

        self.assertTrue(spec.read_only)
        self.assertEqual(spec.mutates, "none")
        self.assertEqual(spec.risk, "low")
        self.assertEqual(
            classify_command("/experience learning preview latest").policy_class,
            "auto_allowed",
        )
        self.assertFalse(
            any(spec.prefix.startswith(PERSISTENT_EXPERIENCE_COMMAND_PREFIXES) for spec in COMMAND_REGISTRY)
        )
        self.assertEqual(len(COMMAND_REGISTRY), 387)
        self.assertEqual(len({spec.category for spec in COMMAND_REGISTRY}), 41)
        self.assertEqual(command_registry_doctor()["status"], "OK")

    def test_learning_decision_empty_session_is_read_only_and_healthy(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            bridge = OperatorReviewedLearningBridge([])
            session = OperatorReviewedLearningDecisionSession()

            decisions = format_learning_decision_command(
                "/experience learning decisions", bridge, session
            )
            doctor = format_learning_decision_command(
                "/experience learning decision-doctor", bridge, session
            )

        self.assertIn("Status: EMPTY", decisions)
        self.assertIn("decisions: 0", decisions)
        self.assertIn("Status: OK", doctor)
        self.assertEqual(session.snapshot(), ())
        self.assertEqual(list(root.rglob("*")), [])

    def test_learning_decision_wrong_token_refuses_without_mutation(self) -> None:
        with TemporaryDirectory() as temp_dir:
            _, _, pilot, bridge, candidate = build_test_learning_candidate(Path(temp_dir))
            session = pilot.learning_decisions
            preview = format_learning_decision_command(
                f"/experience learning confirm-preview {candidate.id}", bridge, session
            )
            refused = format_learning_decision_command(
                f"/experience learning decide accept {candidate.id} WRONG-TOKEN",
                bridge,
                session,
            )

        self.assertIn("Status: CONFIRMABLE", preview)
        self.assertIn(learning_confirmation_token(candidate), preview)
        self.assertIn("Status: REFUSED", refused)
        self.assertIn("token mismatch", refused.lower())
        self.assertEqual(session.snapshot(), ())

    def test_learning_decision_exact_acceptance_stores_bounded_receipt_only(self) -> None:
        with TemporaryDirectory() as temp_dir:
            _, _, pilot, bridge, candidate = build_test_learning_candidate(Path(temp_dir))
            session = pilot.learning_decisions
            token = learning_confirmation_token(candidate)
            accepted = format_learning_decision_command(
                f"/experience learning decide accept {candidate.id} {token}",
                bridge,
                session,
            )
            inspected = format_learning_decision_command(
                f"/experience learning decision {candidate.id}", bridge, session
            )
            receipt = session.snapshot()[0]

        self.assertIn("Status: ACCEPTED FOR FUTURE REVIEW", accepted)
        self.assertIn("operator_confirmation_recorded: true", accepted)
        self.assertEqual(receipt["decision"], "accepted")
        self.assertEqual(receipt["confirmation_method"], "exact_candidate_token")
        self.assertEqual(receipt["evidence_event_ids"], candidate.evidence_event_ids)
        self.assertFalse(receipt["promotion_performed"])
        self.assertFalse(receipt["apply_performed"])
        self.assertFalse(receipt["persistence_performed"])
        self.assertIn("decision: accepted", inspected)

    def test_learning_decision_refuses_warning_only_candidate_acceptance(self) -> None:
        with TemporaryDirectory() as temp_dir:
            events = [
                event.to_dict()
                for event in build_test_experience_events(Path(temp_dir))
            ]
        for event in events:
            if event["event_type"] == "reflection_evaluated":
                event["payload"]["warning_count"] = 1
                event["payload"]["warning_previews"] = ["Needs independent verification."]
                event["payload"]["overall_confidence"] = "medium"
        bridge = OperatorReviewedLearningBridge(events)
        candidate = bridge.review()[0].candidates[0]
        session = OperatorReviewedLearningDecisionSession()
        preview = format_learning_decision_command(
            f"/experience learning confirm-preview {candidate.id}", bridge, session
        )
        refused = format_learning_decision_command(
            f"/experience learning decide accept {candidate.id} {learning_confirmation_token(candidate)}",
            bridge,
            session,
        )

        self.assertEqual(candidate.review_status, "needs_more_evidence")
        self.assertIn("Status: NOT CONFIRMABLE", preview)
        self.assertIn("Status: REFUSED", refused)
        self.assertIn("not accept-eligible", refused)
        self.assertEqual(session.snapshot(), ())

    def test_learning_decision_rejection_is_terminal_and_reason_is_redacted(self) -> None:
        with TemporaryDirectory() as temp_dir:
            _, _, pilot, bridge, candidate = build_test_learning_candidate(Path(temp_dir))
            session = pilot.learning_decisions
            secret = "decision-reject-secret"
            rejected = format_learning_decision_command(
                f"/experience learning decide reject {candidate.id} password={secret}",
                bridge,
                session,
            )
            repeated = format_learning_decision_command(
                f"/experience learning decide reject {candidate.id} duplicate",
                bridge,
                session,
            )
            receipt = session.snapshot()[0]

        self.assertIn("Status: REJECTED", rejected)
        self.assertNotIn(secret, rejected)
        self.assertNotIn(secret, receipt["reason"])
        self.assertIn(REDACTION_PREFIX, receipt["reason"])
        self.assertIn("Status: REFUSED", repeated)
        self.assertEqual(len(session.snapshot()), 1)

    def test_learning_promotion_preview_requires_acceptance_and_never_executes(self) -> None:
        with TemporaryDirectory() as temp_dir:
            _, _, pilot, bridge, candidate = build_test_learning_candidate(Path(temp_dir))
            session = pilot.learning_decisions
            before = format_learning_decision_command(
                f"/experience learning promotion-preview {candidate.id}", bridge, session
            )
            token = learning_confirmation_token(candidate)
            format_learning_decision_command(
                f"/experience learning decide accept {candidate.id} {token}", bridge, session
            )
            after = format_learning_decision_command(
                f"/experience learning promotion-preview {candidate.id}", bridge, session
            )

        self.assertIn("Status: NOT ELIGIBLE", before)
        self.assertIn("Status: DRY RUN ONLY", after)
        self.assertIn(f"proposed_content: {candidate.text}", after)
        self.assertIn("executable: false", after)
        self.assertIn("promotion_performed: false", after)
        self.assertIn("apply_performed: false", after)
        self.assertIn("persistence_performed: false", after)

    def test_learning_decisions_expire_on_process_restart(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _, _, pilot, bridge, candidate = build_test_learning_candidate(root)
            token = learning_confirmation_token(candidate)
            format_learning_decision_command(
                f"/experience learning decide accept {candidate.id} {token}",
                bridge,
                pilot.learning_decisions,
            )
            restarted = SupervisedExperiencePilot(root, session_id="learning-restarted")

        self.assertEqual(len(pilot.learning_decisions.snapshot()), 1)
        self.assertEqual(restarted.learning_decisions.snapshot(), ())

    def test_learning_decision_receipt_limit_fails_closed(self) -> None:
        with TemporaryDirectory() as temp_dir:
            _, _, _, bridge, candidate = build_test_learning_candidate(Path(temp_dir))
            session = OperatorReviewedLearningDecisionSession()
            template = session.decide(candidate, "rejected", reason="capacity fixture")
            session._receipts = {
                f"candidate-{index}": replace(
                    template,
                    id=f"learndec_fixture_{index:02d}",
                    candidate_id=f"candidate-{index}",
                )
                for index in range(LEARNING_DECISION_MAX_RECEIPTS)
            }
            refused = format_learning_decision_command(
                f"/experience learning decide accept {candidate.id} {learning_confirmation_token(candidate)}",
                bridge,
                session,
            )

        self.assertIn("Status: REFUSED", refused)
        self.assertIn("receipt limit reached", refused)
        self.assertEqual(len(session.snapshot()), LEARNING_DECISION_MAX_RECEIPTS)

    def test_learning_decision_doctor_detects_forbidden_receipt_claim(self) -> None:
        with TemporaryDirectory() as temp_dir:
            _, _, pilot, bridge, candidate = build_test_learning_candidate(Path(temp_dir))
            session = pilot.learning_decisions
            session.decide(
                candidate,
                "accepted",
                token=learning_confirmation_token(candidate),
            )
            receipt = session.get(candidate.id)
            session._receipts[candidate.id] = replace(receipt, promotion_performed=True)
            output = format_learning_decision_command(
                "/experience learning decision-doctor", bridge, session
            )

        self.assertIn("Status: ERROR", output)
        self.assertIn("forbidden promotion/apply/persistence", output)

    def test_learning_decision_shared_handler_changes_only_process_memory(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            coordinator, store, _ = build_test_system(root / "cognitive")
            logger = SessionOperatorLogger(root / "session.jsonl", enabled=False)
            process_interactive_input(
                "/experience preview", coordinator=coordinator, session_logger=logger, project_root=root
            )
            pilot = peek_experience_pilot(coordinator)
            process_interactive_input(
                f"/experience consent {pilot.expected_consent_phrase}",
                coordinator=coordinator,
                session_logger=logger,
                project_root=root,
            )
            coordinator.pending_correction_hints = ["Verify active decisions before reuse."]
            process_interactive_input(
                "Explain the current decision.",
                coordinator=coordinator,
                session_logger=logger,
                project_root=root,
            )
            candidate = OperatorReviewedLearningBridge(pilot.snapshot()).review()[0].candidates[0]
            token = learning_confirmation_token(candidate)
            events_before = json.dumps(pilot.snapshot(), sort_keys=True)
            working_before = store.working_path.read_bytes()
            persistent_before = store.persistent_path.read_bytes()

            accepted = process_interactive_input(
                f"/experience learning decide accept {candidate.id} {token}",
                coordinator=coordinator,
                session_logger=logger,
                project_root=root,
            )
            dry_run = process_interactive_input(
                f"/experience learning promotion-preview {candidate.id}",
                coordinator=coordinator,
                session_logger=logger,
                project_root=root,
            )
            events_after = json.dumps(pilot.snapshot(), sort_keys=True)
            working_after = store.working_path.read_bytes()
            persistent_after = store.persistent_path.read_bytes()
            log_entries = logger.status().entry_count

        self.assertIn("Status: ACCEPTED FOR FUTURE REVIEW", accepted)
        self.assertIn("Status: DRY RUN ONLY", dry_run)
        self.assertEqual(events_before, events_after)
        self.assertEqual(working_before, working_after)
        self.assertEqual(persistent_before, persistent_after)
        self.assertEqual(log_entries, 0)

    def test_learning_decision_registry_and_policy_are_explicit(self) -> None:
        registry = {spec.prefix: spec for spec in COMMAND_REGISTRY}
        preview_spec = registry["/experience learning"]
        decide_spec = registry["/experience learning decide"]

        self.assertTrue(preview_spec.read_only)
        self.assertEqual(preview_spec.mutates, "none")
        self.assertFalse(decide_spec.read_only)
        self.assertEqual(decide_spec.mutates, "session")
        self.assertEqual(decide_spec.risk, "medium")
        self.assertEqual(
            classify_command("/experience learning decide accept candidate token").policy_class,
            "confirmation_required",
        )
        self.assertEqual(
            classify_command("/experience learning promotion-preview candidate").policy_class,
            "auto_allowed",
        )
        self.assertEqual(len(COMMAND_REGISTRY), 387)
        self.assertEqual(len({spec.category for spec in COMMAND_REGISTRY}), 41)
        self.assertEqual(command_registry_doctor()["status"], "OK")
        self.assertEqual(action_policy_doctor()["status"], "OK")

    def test_learning_eligibility_requires_accepted_decision_without_store_mutation(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _, store, pilot, _, candidate = build_test_learning_candidate(root)
            reviewer = LearningPromotionEligibilityReviewer(
                memory_store=store,
                skill_library=SkillLibrary(root / "skills.jsonl"),
            )
            working_before = store.working_path.read_bytes()
            persistent_before = store.persistent_path.read_bytes()

            receipt = reviewer.review(
                candidate,
                pilot.learning_decisions.get(candidate.id),
                target="memory",
            )
            working_after = store.working_path.read_bytes()
            persistent_after = store.persistent_path.read_bytes()

        self.assertEqual(receipt.status, "NOT ELIGIBLE")
        self.assertEqual(receipt.decision_id, "none")
        self.assertFalse(receipt.retrieval_performed)
        self.assertFalse(receipt.mutation_performed)
        self.assertFalse(receipt.promotion_performed)
        self.assertEqual(working_before, working_after)
        self.assertEqual(persistent_before, persistent_after)

    def test_learning_eligibility_accepted_candidate_without_ids_is_not_checked(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _, store, pilot, _, candidate = build_test_learning_candidate(root)
            decision = pilot.learning_decisions.decide(
                candidate,
                "accepted",
                token=learning_confirmation_token(candidate),
            )
            receipt = LearningPromotionEligibilityReviewer(
                memory_store=store,
                skill_library=SkillLibrary(root / "skills.jsonl"),
            ).review(candidate, decision, target="memory")

        self.assertEqual(receipt.status, "NOT CHECKED")
        self.assertTrue(receipt.scope_limited)
        self.assertFalse(receipt.global_duplicate_check_performed)
        self.assertEqual(receipt.selected_memory_ids, [])

    def test_learning_eligibility_memory_scope_detects_exact_normalized_duplicate(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _, store, pilot, _, candidate = build_test_learning_candidate(root)
            store.save_persistent_memory(
                [
                    MemoryRecord(
                        id="mem_exact",
                        content=f"  {candidate.text.upper()}  ",
                        type="lesson",
                        importance=0.8,
                        source="test",
                    )
                ]
            )
            decision = pilot.learning_decisions.decide(
                candidate,
                "accepted",
                token=learning_confirmation_token(candidate),
            )
            receipt = LearningPromotionEligibilityReviewer(
                memory_store=store,
                skill_library=SkillLibrary(root / "skills.jsonl"),
            ).review(candidate, decision, target="memory", memory_ids=["mem_exact"])

        self.assertEqual(receipt.status, "DUPLICATE")
        self.assertEqual(receipt.duplicate_matches, ["memory:mem_exact:content"])
        self.assertFalse(receipt.global_duplicate_check_performed)

    def test_learning_eligibility_skill_scope_detects_exact_duplicate(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _, store, pilot, _, candidate = build_test_learning_candidate(root)
            skills_path = root / "skills.jsonl"
            skills_path.write_text(
                json.dumps(
                    {
                        "id": "skill_exact",
                        "name": "Review corrected decisions",
                        "summary": candidate.text,
                        "body": "",
                        "status": "active",
                        "category": "workflow",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            decision = pilot.learning_decisions.decide(
                candidate,
                "accepted",
                token=learning_confirmation_token(candidate),
            )
            receipt = LearningPromotionEligibilityReviewer(
                memory_store=store,
                skill_library=SkillLibrary(skills_path),
            ).review(candidate, decision, target="skill", skill_ids=["skill_exact"])

        self.assertEqual(receipt.status, "DUPLICATE")
        self.assertEqual(receipt.duplicate_matches, ["skill:skill_exact:summary"])

    def test_learning_eligibility_does_not_search_unselected_records(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _, store, pilot, _, candidate = build_test_learning_candidate(root)
            store.save_persistent_memory(
                [
                    MemoryRecord(
                        id="mem_unselected_duplicate",
                        content=candidate.text,
                        type="lesson",
                        importance=0.8,
                        source="test",
                    ),
                    MemoryRecord(
                        id="mem_selected_reference",
                        content="A separate operator-selected reference.",
                        type="project_fact",
                        importance=0.7,
                        source="test",
                    ),
                ]
            )
            decision = pilot.learning_decisions.decide(
                candidate,
                "accepted",
                token=learning_confirmation_token(candidate),
            )
            receipt = LearningPromotionEligibilityReviewer(
                memory_store=store,
                skill_library=SkillLibrary(root / "skills.jsonl"),
            ).review(
                candidate,
                decision,
                target="memory",
                memory_ids=["mem_selected_reference"],
            )

        self.assertEqual(receipt.status, "ELIGIBLE IN SELECTED SCOPE")
        self.assertEqual(receipt.duplicate_matches, [])
        self.assertFalse(receipt.global_duplicate_check_performed)

    def test_learning_eligibility_missing_and_inactive_ids_are_incomplete(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _, store, pilot, _, candidate = build_test_learning_candidate(root)
            store.save_persistent_memory(
                [
                    MemoryRecord(
                        id="mem_inactive",
                        content="Historical inactive reference.",
                        type="lesson",
                        importance=0.5,
                        source="test",
                        active=False,
                    )
                ]
            )
            decision = pilot.learning_decisions.decide(
                candidate,
                "accepted",
                token=learning_confirmation_token(candidate),
            )
            receipt = LearningPromotionEligibilityReviewer(
                memory_store=store,
                skill_library=SkillLibrary(root / "skills.jsonl"),
            ).review(
                candidate,
                decision,
                target="memory",
                memory_ids=["mem_missing", "mem_inactive"],
            )

        self.assertEqual(receipt.status, "INCOMPLETE")
        self.assertEqual(receipt.missing_memory_ids, ["mem_missing"])
        self.assertEqual(receipt.excluded_memory_ids, ["mem_inactive"])

    def test_learning_eligibility_limit_and_corrupted_store_fail_closed(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _, store, pilot, bridge, candidate = build_test_learning_candidate(root)
            pilot.learning_decisions.decide(
                candidate,
                "accepted",
                token=learning_confirmation_token(candidate),
            )
            too_many_ids = " ".join(
                f"--memory mem_{index}" for index in range(LEARNING_ELIGIBILITY_MAX_IDS_PER_KIND + 1)
            )
            limited = format_learning_eligibility_command(
                f"/experience learning eligibility {candidate.id} --target memory {too_many_ids}",
                bridge=bridge,
                decisions=pilot.learning_decisions,
                memory_store=store,
                skill_library=SkillLibrary(root / "skills.jsonl"),
            )
            store.working_path.write_text("{broken", encoding="utf-8")
            corrupted = format_learning_eligibility_command(
                f"/experience learning eligibility {candidate.id} --target memory",
                bridge=bridge,
                decisions=pilot.learning_decisions,
                memory_store=store,
                skill_library=SkillLibrary(root / "skills.jsonl"),
            )

        self.assertIn("Status: ERROR", limited)
        self.assertIn("Explicit memory ID limit", limited)
        self.assertIn("Status: ERROR", corrupted)
        self.assertIn("Memory snapshot is unreadable", corrupted)

    def test_learning_eligibility_doctor_rejects_forbidden_effect_claims(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _, store, pilot, _, candidate = build_test_learning_candidate(root)
            store.save_persistent_memory(
                [
                    MemoryRecord(
                        id="mem_reference",
                        content="A separate selected reference.",
                        type="project_fact",
                        importance=0.7,
                        source="test",
                    )
                ]
            )
            decision = pilot.learning_decisions.decide(
                candidate,
                "accepted",
                token=learning_confirmation_token(candidate),
            )
            reviewer = LearningPromotionEligibilityReviewer(
                memory_store=store,
                skill_library=SkillLibrary(root / "skills.jsonl"),
            )
            receipt = reviewer.review(
                candidate,
                decision,
                target="memory",
                memory_ids=["mem_reference"],
            )
            report = reviewer.doctor(replace(receipt, mutation_performed=True))

        self.assertEqual(report.status, "ERROR")
        self.assertIn("forbidden side effect", " ".join(report.issues))

    def test_learning_eligibility_shared_handler_is_byte_stable(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            coordinator, store, _ = build_test_system(root / "cognitive")
            logger = SessionOperatorLogger(root / "session.jsonl", enabled=False)
            process_interactive_input(
                "/experience preview",
                coordinator=coordinator,
                session_logger=logger,
                project_root=root,
            )
            pilot = peek_experience_pilot(coordinator)
            process_interactive_input(
                f"/experience consent {pilot.expected_consent_phrase}",
                coordinator=coordinator,
                session_logger=logger,
                project_root=root,
            )
            coordinator.pending_correction_hints = ["Verify active decisions before reuse."]
            process_interactive_input(
                "Explain the current decision.",
                coordinator=coordinator,
                session_logger=logger,
                project_root=root,
            )
            candidate = OperatorReviewedLearningBridge(pilot.snapshot()).review()[0].candidates[0]
            pilot.learning_decisions.decide(
                candidate,
                "accepted",
                token=learning_confirmation_token(candidate),
            )
            store.save_persistent_memory(
                [
                    MemoryRecord(
                        id="mem_shared_reference",
                        content="An unrelated explicit reference.",
                        type="project_fact",
                        importance=0.7,
                        source="test",
                    )
                ]
            )
            events_before = json.dumps(pilot.snapshot(), sort_keys=True)
            decisions_before = json.dumps(pilot.learning_decisions.snapshot(), sort_keys=True)
            working_before = store.working_path.read_bytes()
            persistent_before = store.persistent_path.read_bytes()
            skill_path = root / "proto_mind" / "data" / "skills.jsonl"
            skill_before = skill_path.read_bytes() if skill_path.exists() else None
            log_before = logger.status().entry_count

            review = process_interactive_input(
                f"/experience learning eligibility {candidate.id} "
                "--target memory --memory mem_shared_reference",
                coordinator=coordinator,
                session_logger=logger,
                project_root=root,
            )
            doctor = process_interactive_input(
                f"/experience learning eligibility-doctor {candidate.id} "
                "--target memory --memory mem_shared_reference",
                coordinator=coordinator,
                session_logger=logger,
                project_root=root,
            )
            events_after = json.dumps(pilot.snapshot(), sort_keys=True)
            decisions_after = json.dumps(pilot.learning_decisions.snapshot(), sort_keys=True)
            working_after = store.working_path.read_bytes()
            persistent_after = store.persistent_path.read_bytes()
            skill_after = skill_path.read_bytes() if skill_path.exists() else None
            log_after = logger.status().entry_count

        self.assertIn("Status: ELIGIBLE IN SELECTED SCOPE", review)
        self.assertIn("Status: WARN", doctor)
        self.assertIn("global_duplicate_check_performed: false", review)
        self.assertEqual(events_before, events_after)
        self.assertEqual(decisions_before, decisions_after)
        self.assertEqual(working_before, working_after)
        self.assertEqual(persistent_before, persistent_after)
        self.assertEqual(skill_before, skill_after)
        self.assertEqual(log_before, log_after)

    def test_learning_eligibility_reuses_read_only_registry_policy(self) -> None:
        spec = {entry.prefix: entry for entry in COMMAND_REGISTRY}["/experience learning"]

        self.assertTrue(spec.read_only)
        self.assertEqual(spec.mutates, "none")
        self.assertEqual(spec.risk, "low")
        self.assertEqual(
            classify_command(
                "/experience learning eligibility candidate --target memory --memory mem_ref"
            ).policy_class,
            "auto_allowed",
        )
        self.assertEqual(len(COMMAND_REGISTRY), 387)
        self.assertEqual(len({entry.category for entry in COMMAND_REGISTRY}), 41)
        self.assertEqual(command_registry_doctor()["status"], "OK")
        self.assertEqual(action_policy_doctor()["status"], "OK")

    def test_learning_proposal_preview_requires_accepted_eligible_candidate(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _, store, pilot, bridge, candidate = build_test_learning_candidate(root)
            store.save_persistent_memory(
                [
                    MemoryRecord(
                        id="mem_ref",
                        content="Separate reference.",
                        type="project_fact",
                        importance=0.7,
                        source="test",
                    )
                ]
            )
            output = format_learning_proposal_command(
                f"/experience learning proposal-preview {candidate.id} "
                "--target memory --memory mem_ref",
                bridge=bridge,
                decisions=pilot.learning_decisions,
                proposals=pilot.learning_proposals,
                memory_store=store,
                skill_library=SkillLibrary(root / "skills.jsonl"),
            )

        self.assertIn("Status: NOT PROPOSABLE", output)
        self.assertIn("accepted process-memory", output)
        self.assertEqual(pilot.learning_proposals.snapshot(), ())

    def test_learning_proposal_preview_builds_exact_memory_schema_and_token(self) -> None:
        with TemporaryDirectory() as temp_dir:
            _, _, _, _, candidate, _, blueprint = build_test_learning_proposal(Path(temp_dir))
            token = learning_proposal_confirmation_token(blueprint)

        self.assertEqual(blueprint.target_schema, "memory.lesson.v1")
        self.assertEqual(blueprint.proposed_payload["content"], candidate.text)
        self.assertEqual(blueprint.proposed_payload["type"], "lesson")
        self.assertEqual(len(blueprint.proposal_hash), 64)
        self.assertTrue(token.startswith("CONFIRM-PROPOSAL-"))
        self.assertFalse(blueprint.global_duplicate_check_performed)
        self.assertFalse(blueprint.future_apply_ready)
        self.assertFalse(blueprint.executable)

    def test_learning_proposal_skill_target_uses_fixed_procedure_schema(self) -> None:
        with TemporaryDirectory() as temp_dir:
            _, _, _, _, candidate, _, blueprint = build_test_learning_proposal(
                Path(temp_dir),
                target="skill",
            )

        self.assertEqual(blueprint.target_schema, "skill.procedure.v1")
        self.assertEqual(blueprint.proposed_payload["summary"], candidate.text)
        self.assertEqual(blueprint.proposed_payload["body"], "")
        self.assertEqual(blueprint.proposed_payload["status"], "active")
        self.assertFalse(blueprint.future_apply_ready)

    def test_learning_proposal_wrong_token_refuses_without_receipt(self) -> None:
        with TemporaryDirectory() as temp_dir:
            _, _, pilot, _, _, _, blueprint = build_test_learning_proposal(Path(temp_dir))

            with self.assertRaisesRegex(LearningProposalError, "token mismatch"):
                pilot.learning_proposals.create(blueprint, token="WRONG-TOKEN")

        self.assertEqual(pilot.learning_proposals.snapshot(), ())

    def test_learning_proposal_exact_token_stores_bounded_receipt_only(self) -> None:
        with TemporaryDirectory() as temp_dir:
            _, store, pilot, _, candidate, skills, blueprint = build_test_learning_proposal(
                Path(temp_dir)
            )
            working_before = store.working_path.read_bytes()
            persistent_before = store.persistent_path.read_bytes()
            skills_before = skills.skills_path.read_bytes() if skills.skills_path.exists() else None
            receipt = pilot.learning_proposals.create(
                blueprint,
                token=learning_proposal_confirmation_token(blueprint),
            )
            working_after = store.working_path.read_bytes()
            persistent_after = store.persistent_path.read_bytes()
            skills_after = skills.skills_path.read_bytes() if skills.skills_path.exists() else None

        self.assertEqual(receipt.candidate_id, candidate.id)
        self.assertEqual(receipt.proposal_hash, blueprint.proposal_hash)
        self.assertEqual(receipt.confirmation_method, "exact_proposal_token")
        self.assertTrue(receipt.operator_confirmation_recorded)
        self.assertFalse(receipt.future_apply_ready)
        self.assertFalse(receipt.promotion_performed)
        self.assertFalse(receipt.apply_performed)
        self.assertFalse(receipt.persistence_performed)
        self.assertEqual(working_before, working_after)
        self.assertEqual(persistent_before, persistent_after)
        self.assertEqual(skills_before, skills_after)

    def test_learning_proposal_token_detects_selected_scope_drift(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _, store, pilot, _, candidate, skills, blueprint = build_test_learning_proposal(root)
            token = learning_proposal_confirmation_token(blueprint)
            store.save_persistent_memory(
                [
                    MemoryRecord(
                        id="mem_proposal_ref",
                        content="Changed selected reference.",
                        type="project_fact",
                        importance=0.7,
                        source="test",
                    )
                ]
            )
            request = LearningEligibilityRequest(
                candidate_id=candidate.id,
                target="memory",
                memory_ids=["mem_proposal_ref"],
                skill_ids=[],
            )
            changed = LearningPromotionProposalBuilder(
                memory_store=store,
                skill_library=skills,
            ).build(
                candidate,
                pilot.learning_decisions.get(candidate.id),
                request,
            )

            with self.assertRaisesRegex(LearningProposalError, "token mismatch"):
                pilot.learning_proposals.create(changed, token=token)

        self.assertNotEqual(blueprint.selected_scope_hash, changed.selected_scope_hash)
        self.assertNotEqual(blueprint.proposal_hash, changed.proposal_hash)
        self.assertEqual(pilot.learning_proposals.snapshot(), ())

    def test_learning_proposal_refuses_duplicate_scope_and_duplicate_receipt(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _, store, pilot, bridge, candidate = build_test_learning_candidate(root)
            store.save_persistent_memory(
                [
                    MemoryRecord(
                        id="mem_duplicate",
                        content=candidate.text,
                        type="lesson",
                        importance=0.8,
                        source="test",
                    )
                ]
            )
            pilot.learning_decisions.decide(
                candidate,
                "accepted",
                token=learning_confirmation_token(candidate),
            )
            duplicate = format_learning_proposal_command(
                f"/experience learning proposal-preview {candidate.id} "
                "--target memory --memory mem_duplicate",
                bridge=bridge,
                decisions=pilot.learning_decisions,
                proposals=pilot.learning_proposals,
                memory_store=store,
                skill_library=SkillLibrary(root / "skills.jsonl"),
            )

        self.assertIn("Status: NOT PROPOSABLE", duplicate)
        self.assertIn("got DUPLICATE", duplicate)
        self.assertEqual(pilot.learning_proposals.snapshot(), ())

        with TemporaryDirectory() as temp_dir:
            _, _, pilot, _, _, _, blueprint = build_test_learning_proposal(Path(temp_dir))
            token = learning_proposal_confirmation_token(blueprint)
            pilot.learning_proposals.create(blueprint, token=token)
            with self.assertRaisesRegex(LearningProposalError, "already has"):
                pilot.learning_proposals.create(blueprint, token=token)

    def test_learning_proposal_session_limit_fails_closed(self) -> None:
        with TemporaryDirectory() as temp_dir:
            _, _, pilot, _, _, _, blueprint = build_test_learning_proposal(Path(temp_dir))
            template = pilot.learning_proposals.create(
                blueprint,
                token=learning_proposal_confirmation_token(blueprint),
            )
            pilot.learning_proposals._receipts = {
                f"candidate-{index}": replace(
                    template,
                    id=f"learnprop_fixture_{index:02d}",
                    candidate_id=f"candidate-{index}",
                    proposal_hash=f"{index:064x}",
                )
                for index in range(LEARNING_PROPOSAL_MAX_RECEIPTS)
            }
            with self.assertRaisesRegex(LearningProposalError, "receipt limit reached"):
                pilot.learning_proposals.create(
                    blueprint,
                    token=learning_proposal_confirmation_token(blueprint),
                )

        self.assertEqual(len(pilot.learning_proposals.snapshot()), LEARNING_PROPOSAL_MAX_RECEIPTS)

    def test_learning_proposal_list_inspect_and_doctor_are_read_only(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _, store, pilot, bridge, candidate, skills, blueprint = build_test_learning_proposal(root)
            receipt = pilot.learning_proposals.create(
                blueprint,
                token=learning_proposal_confirmation_token(blueprint),
            )
            dependencies = {
                "bridge": bridge,
                "decisions": pilot.learning_decisions,
                "proposals": pilot.learning_proposals,
                "memory_store": store,
                "skill_library": skills,
            }
            before = json.dumps(pilot.learning_proposals.snapshot(), sort_keys=True)
            listing = format_learning_proposal_command(
                "/experience learning proposals",
                **dependencies,
            )
            inspected = format_learning_proposal_command(
                f"/experience learning proposal {receipt.id}",
                **dependencies,
            )
            doctor = format_learning_proposal_command(
                "/experience learning proposal-doctor",
                **dependencies,
            )
            after = json.dumps(pilot.learning_proposals.snapshot(), sort_keys=True)

        self.assertIn(receipt.id, listing)
        self.assertIn(f"candidate_id: {candidate.id}", inspected)
        self.assertIn("target_schema: memory.lesson.v1", inspected)
        self.assertIn("Status: OK", doctor)
        self.assertEqual(before, after)

    def test_learning_proposal_doctor_detects_tampering(self) -> None:
        with TemporaryDirectory() as temp_dir:
            _, _, pilot, bridge, candidate, _, blueprint = build_test_learning_proposal(
                Path(temp_dir)
            )
            receipt = pilot.learning_proposals.create(
                blueprint,
                token=learning_proposal_confirmation_token(blueprint),
            )
            pilot.learning_proposals._receipts[candidate.id] = replace(
                receipt,
                apply_performed=True,
            )
            candidates = {
                item.id: item
                for review in bridge.review()
                for item in review.candidates
            }
            report = pilot.learning_proposals.doctor(candidates, pilot.learning_decisions)

        self.assertEqual(report.status, "ERROR")
        self.assertIn("forbidden effect", " ".join(report.issues))

    def test_learning_proposals_expire_on_process_restart(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _, _, pilot, _, _, _, blueprint = build_test_learning_proposal(root)
            pilot.learning_proposals.create(
                blueprint,
                token=learning_proposal_confirmation_token(blueprint),
            )
            restarted = SupervisedExperiencePilot(root, session_id="proposal-restarted")

        self.assertEqual(len(pilot.learning_proposals.snapshot()), 1)
        self.assertEqual(restarted.learning_proposals.snapshot(), ())

    def test_learning_proposal_shared_handler_mutates_process_receipt_only(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            coordinator, store, _ = build_test_system(root / "cognitive")
            logger = SessionOperatorLogger(root / "session.jsonl", enabled=False)
            process_interactive_input(
                "/experience preview",
                coordinator=coordinator,
                session_logger=logger,
                project_root=root,
            )
            pilot = peek_experience_pilot(coordinator)
            process_interactive_input(
                f"/experience consent {pilot.expected_consent_phrase}",
                coordinator=coordinator,
                session_logger=logger,
                project_root=root,
            )
            coordinator.pending_correction_hints = ["Verify active decisions before reuse."]
            process_interactive_input(
                "Explain the current decision.",
                coordinator=coordinator,
                session_logger=logger,
                project_root=root,
            )
            candidate = OperatorReviewedLearningBridge(pilot.snapshot()).review()[0].candidates[0]
            pilot.learning_decisions.decide(
                candidate,
                "accepted",
                token=learning_confirmation_token(candidate),
            )
            store.save_persistent_memory(
                [
                    MemoryRecord(
                        id="mem_shared_proposal",
                        content="Separate shared-handler reference.",
                        type="project_fact",
                        importance=0.7,
                        source="test",
                    )
                ]
            )
            preview = process_interactive_input(
                f"/experience learning proposal-preview {candidate.id} "
                "--target memory --memory mem_shared_proposal",
                coordinator=coordinator,
                session_logger=logger,
                project_root=root,
            )
            token = _id_from_output(preview, "confirmation_token:")
            events_before = json.dumps(pilot.snapshot(), sort_keys=True)
            decisions_before = json.dumps(pilot.learning_decisions.snapshot(), sort_keys=True)
            working_before = store.working_path.read_bytes()
            persistent_before = store.persistent_path.read_bytes()
            skill_path = root / "proto_mind" / "data" / "skills.jsonl"
            skill_before = skill_path.read_bytes() if skill_path.exists() else None
            log_before = logger.status().entry_count

            proposed = process_interactive_input(
                f"/experience learning propose {candidate.id} {token} "
                "--target memory --memory mem_shared_proposal",
                coordinator=coordinator,
                session_logger=logger,
                project_root=root,
            )
            doctor = process_interactive_input(
                "/experience learning proposal-doctor",
                coordinator=coordinator,
                session_logger=logger,
                project_root=root,
            )
            events_after = json.dumps(pilot.snapshot(), sort_keys=True)
            decisions_after = json.dumps(pilot.learning_decisions.snapshot(), sort_keys=True)
            working_after = store.working_path.read_bytes()
            persistent_after = store.persistent_path.read_bytes()
            skill_after = skill_path.read_bytes() if skill_path.exists() else None
            log_after = logger.status().entry_count

        self.assertIn("Status: PROPOSED IN PROCESS MEMORY", proposed)
        self.assertIn("Status: OK", doctor)
        self.assertEqual(len(pilot.learning_proposals.snapshot()), 1)
        self.assertEqual(events_before, events_after)
        self.assertEqual(decisions_before, decisions_after)
        self.assertEqual(working_before, working_after)
        self.assertEqual(persistent_before, persistent_after)
        self.assertEqual(skill_before, skill_after)
        self.assertEqual(log_before, log_after)

    def test_learning_proposal_registry_and_policy_are_explicit(self) -> None:
        registry = {entry.prefix: entry for entry in COMMAND_REGISTRY}
        preview = registry["/experience learning"]
        propose = registry["/experience learning propose"]

        self.assertTrue(preview.read_only)
        self.assertEqual(preview.mutates, "none")
        self.assertFalse(propose.read_only)
        self.assertEqual(propose.mutates, "session")
        self.assertEqual(propose.risk, "medium")
        self.assertEqual(
            classify_command(
                "/experience learning proposal-preview candidate --target memory --memory mem_ref"
            ).policy_class,
            "auto_allowed",
        )
        self.assertEqual(
            classify_command(
                "/experience learning propose candidate token --target memory --memory mem_ref"
            ).policy_class,
            "confirmation_required",
        )
        self.assertEqual(len(COMMAND_REGISTRY), 387)
        self.assertEqual(len({entry.category for entry in COMMAND_REGISTRY}), 41)
        self.assertEqual(command_registry_doctor()["status"], "OK")
        self.assertEqual(action_policy_doctor()["status"], "OK")

    def test_learning_apply_readiness_handles_empty_process_state(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _, store, pilot, bridge, _ = build_test_learning_candidate(root)
            dependencies = {
                "bridge": bridge,
                "decisions": pilot.learning_decisions,
                "proposals": pilot.learning_proposals,
                "memory_store": store,
                "skill_library": SkillLibrary(root / "skills.jsonl"),
            }
            missing = format_learning_apply_readiness_command(
                "/experience learning apply-readiness missing",
                **dependencies,
            )
            doctor = format_learning_apply_readiness_command(
                "/experience learning apply-doctor",
                **dependencies,
            )

        self.assertIn("Status: NOT FOUND", missing)
        self.assertIn("Status: OK", doctor)
        self.assertIn("proposals: 0", doctor)
        self.assertEqual(pilot.learning_proposals.snapshot(), ())

    def test_learning_apply_readiness_revalidates_current_proposal(self) -> None:
        with TemporaryDirectory() as temp_dir:
            _, store, pilot, bridge, _, skills, blueprint = build_test_learning_proposal(
                Path(temp_dir)
            )
            receipt = pilot.learning_proposals.create(
                blueprint,
                token=learning_proposal_confirmation_token(blueprint),
            )
            candidates = {
                item.id: item
                for review in bridge.review()
                for item in review.candidates
            }
            report = LearningPromotionApplyReadiness(
                memory_store=store,
                skill_library=skills,
            ).review(
                receipt,
                candidates=candidates,
                decisions=pilot.learning_decisions,
            )

        self.assertEqual(report.status, "READY FOR APPLY DESIGN REVIEW")
        self.assertTrue(report.ready_for_design_review)
        self.assertTrue(all(report.checks.values()))
        self.assertEqual(report.stored_proposal_hash, report.current_proposal_hash)
        self.assertEqual(report.stored_scope_hash, report.current_scope_hash)
        self.assertTrue(report.apply_engine_installed)
        self.assertFalse(report.executable)
        self.assertFalse(report.apply_performed)

    def test_learning_apply_plan_prints_memory_receipt_and_rollback_requirements(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _, store, pilot, bridge, _, skills, blueprint = build_test_learning_proposal(root)
            receipt = pilot.learning_proposals.create(
                blueprint,
                token=learning_proposal_confirmation_token(blueprint),
            )
            before = (
                store.working_path.read_bytes(),
                store.persistent_path.read_bytes(),
                json.dumps(pilot.learning_proposals.snapshot(), sort_keys=True),
            )
            output = format_learning_apply_readiness_command(
                f"/experience learning apply-plan {receipt.id}",
                bridge=bridge,
                decisions=pilot.learning_decisions,
                proposals=pilot.learning_proposals,
                memory_store=store,
                skill_library=skills,
            )
            after = (
                store.working_path.read_bytes(),
                store.persistent_path.read_bytes(),
                json.dumps(pilot.learning_proposals.snapshot(), sort_keys=True),
            )

        self.assertIn("Status: DESIGN REVIEW ONLY", output)
        self.assertIn("before_store_sha256", output)
        self.assertIn("created_record_id", output)
        self.assertIn("/memory forget <created_memory_id>", output)
        self.assertIn("separate exact-token memory apply command", output)
        self.assertEqual(before, after)

    def test_learning_apply_plan_prints_skill_rollback_template(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _, store, pilot, bridge, _, skills, blueprint = build_test_learning_proposal(
                root,
                target="skill",
            )
            receipt = pilot.learning_proposals.create(
                blueprint,
                token=learning_proposal_confirmation_token(blueprint),
            )
            output = format_learning_apply_readiness_command(
                f"/experience learning apply-plan {receipt.id}",
                bridge=bridge,
                decisions=pilot.learning_decisions,
                proposals=pilot.learning_proposals,
                memory_store=store,
                skill_library=skills,
            )

        self.assertIn("target_schema: skill.procedure.v1", output)
        self.assertIn("/skills archive <created_skill_id>", output)
        self.assertIn("apply_engine_installed: true", output)

    def test_learning_apply_readiness_detects_selected_scope_drift(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _, store, pilot, bridge, _, skills, blueprint = build_test_learning_proposal(root)
            receipt = pilot.learning_proposals.create(
                blueprint,
                token=learning_proposal_confirmation_token(blueprint),
            )
            store.save_persistent_memory(
                [
                    MemoryRecord(
                        id="mem_proposal_ref",
                        content="Reference changed after proposal creation.",
                        type="project_fact",
                        importance=0.7,
                        source="test",
                    )
                ]
            )
            candidates = {
                item.id: item
                for review in bridge.review()
                for item in review.candidates
            }
            reviewer = LearningPromotionApplyReadiness(
                memory_store=store,
                skill_library=skills,
            )
            report = reviewer.review(
                receipt,
                candidates=candidates,
                decisions=pilot.learning_decisions,
            )
            doctor = reviewer.doctor(
                pilot.learning_proposals,
                candidates=candidates,
                decisions=pilot.learning_decisions,
            )

        self.assertEqual(report.status, "NOT READY")
        self.assertFalse(report.checks["selected_scope_matches"])
        self.assertIn("snapshot has drifted", " ".join(report.issues))
        self.assertEqual(doctor.status, "WARN")
        self.assertEqual(doctor.not_ready_count, 1)

    def test_learning_apply_readiness_requires_current_accepted_decision(self) -> None:
        with TemporaryDirectory() as temp_dir:
            _, store, pilot, bridge, _, skills, blueprint = build_test_learning_proposal(
                Path(temp_dir)
            )
            receipt = pilot.learning_proposals.create(
                blueprint,
                token=learning_proposal_confirmation_token(blueprint),
            )
            pilot.learning_decisions._receipts.clear()
            candidates = {
                item.id: item
                for review in bridge.review()
                for item in review.candidates
            }
            report = LearningPromotionApplyReadiness(
                memory_store=store,
                skill_library=skills,
            ).review(
                receipt,
                candidates=candidates,
                decisions=pilot.learning_decisions,
            )

        self.assertEqual(report.status, "NOT READY")
        self.assertFalse(report.checks["accepted_decision_present"])
        self.assertIn("accepted candidate decision is missing", " ".join(report.issues))

    def test_learning_apply_doctor_rejects_forbidden_effect_receipt(self) -> None:
        with TemporaryDirectory() as temp_dir:
            _, store, pilot, bridge, candidate, skills, blueprint = build_test_learning_proposal(
                Path(temp_dir)
            )
            receipt = pilot.learning_proposals.create(
                blueprint,
                token=learning_proposal_confirmation_token(blueprint),
            )
            pilot.learning_proposals._receipts[candidate.id] = replace(
                receipt,
                apply_performed=True,
            )
            candidates = {
                item.id: item
                for review in bridge.review()
                for item in review.candidates
            }
            reviewer = LearningPromotionApplyReadiness(
                memory_store=store,
                skill_library=skills,
            )
            report = reviewer.review(
                pilot.learning_proposals.get(candidate.id),
                candidates=candidates,
                decisions=pilot.learning_decisions,
            )
            doctor = reviewer.doctor(
                pilot.learning_proposals,
                candidates=candidates,
                decisions=pilot.learning_decisions,
            )

        self.assertEqual(report.status, "ERROR")
        self.assertFalse(report.checks["proposal_receipt_safe"])
        self.assertEqual(doctor.status, "ERROR")

    def test_learning_apply_readiness_fails_cleanly_on_corrupted_store(self) -> None:
        with TemporaryDirectory() as temp_dir:
            _, store, pilot, bridge, _, skills, blueprint = build_test_learning_proposal(
                Path(temp_dir)
            )
            receipt = pilot.learning_proposals.create(
                blueprint,
                token=learning_proposal_confirmation_token(blueprint),
            )
            store.working_path.write_text("{broken", encoding="utf-8")
            candidates = {
                item.id: item
                for review in bridge.review()
                for item in review.candidates
            }
            report = LearningPromotionApplyReadiness(
                memory_store=store,
                skill_library=skills,
            ).review(
                receipt,
                candidates=candidates,
                decisions=pilot.learning_decisions,
            )

        self.assertEqual(report.status, "ERROR")
        self.assertIn("unreadable", " ".join(report.issues).lower())
        self.assertFalse(report.ready_for_design_review)

    def test_learning_apply_commands_are_read_only_through_shared_handler(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            coordinator, store, _ = build_test_system(root / "cognitive")
            logger = SessionOperatorLogger(root / "session.jsonl", enabled=False)
            process_interactive_input(
                "/experience preview",
                coordinator=coordinator,
                session_logger=logger,
                project_root=root,
            )
            pilot = peek_experience_pilot(coordinator)
            process_interactive_input(
                f"/experience consent {pilot.expected_consent_phrase}",
                coordinator=coordinator,
                session_logger=logger,
                project_root=root,
            )
            coordinator.pending_correction_hints = ["Verify active decisions before reuse."]
            process_interactive_input(
                "Explain the current decision.",
                coordinator=coordinator,
                session_logger=logger,
                project_root=root,
            )
            candidate = OperatorReviewedLearningBridge(pilot.snapshot()).review()[0].candidates[0]
            pilot.learning_decisions.decide(
                candidate,
                "accepted",
                token=learning_confirmation_token(candidate),
            )
            store.save_persistent_memory(
                [
                    MemoryRecord(
                        id="mem_readiness_ref",
                        content="Separate readiness reference.",
                        type="project_fact",
                        importance=0.7,
                        source="test",
                    )
                ]
            )
            preview = process_interactive_input(
                f"/experience learning proposal-preview {candidate.id} "
                "--target memory --memory mem_readiness_ref",
                coordinator=coordinator,
                session_logger=logger,
                project_root=root,
            )
            token = _id_from_output(preview, "confirmation_token:")
            proposed = process_interactive_input(
                f"/experience learning propose {candidate.id} {token} "
                "--target memory --memory mem_readiness_ref",
                coordinator=coordinator,
                session_logger=logger,
                project_root=root,
            )
            proposal_id = _id_from_output(proposed, "proposal_id:")
            before = (
                store.working_path.read_bytes(),
                store.persistent_path.read_bytes(),
                json.dumps(pilot.snapshot(), sort_keys=True),
                json.dumps(pilot.learning_decisions.snapshot(), sort_keys=True),
                json.dumps(pilot.learning_proposals.snapshot(), sort_keys=True),
                logger.status().entry_count,
            )
            readiness = process_interactive_input(
                f"/experience learning apply-readiness {proposal_id}",
                coordinator=coordinator,
                session_logger=logger,
                project_root=root,
            )
            plan = process_interactive_input(
                f"/experience learning apply-plan {proposal_id}",
                coordinator=coordinator,
                session_logger=logger,
                project_root=root,
            )
            doctor = process_interactive_input(
                "/experience learning apply-doctor",
                coordinator=coordinator,
                session_logger=logger,
                project_root=root,
            )
            after = (
                store.working_path.read_bytes(),
                store.persistent_path.read_bytes(),
                json.dumps(pilot.snapshot(), sort_keys=True),
                json.dumps(pilot.learning_decisions.snapshot(), sort_keys=True),
                json.dumps(pilot.learning_proposals.snapshot(), sort_keys=True),
                logger.status().entry_count,
            )

        self.assertIn("Status: READY FOR APPLY DESIGN REVIEW", readiness)
        self.assertIn("Status: DESIGN REVIEW ONLY", plan)
        self.assertIn("Status: OK", doctor)
        self.assertEqual(before, after)

    def test_learning_apply_readiness_registry_policy_and_absent_engine(self) -> None:
        registry = {entry.prefix: entry for entry in COMMAND_REGISTRY}
        broad = registry["/experience learning"]

        self.assertTrue(broad.read_only)
        self.assertEqual(broad.mutates, "none")
        self.assertTrue(LEARNING_APPLY_ENGINE_INSTALLED)
        self.assertIn("/experience learning apply", registry)
        self.assertFalse(registry["/experience learning apply"].read_only)
        self.assertEqual(registry["/experience learning apply"].mutates, "memory")
        for command in (
            "/experience learning apply-readiness proposal",
            "/experience learning apply-plan proposal",
            "/experience learning apply-doctor",
        ):
            self.assertEqual(classify_command(command).policy_class, "auto_allowed")
        self.assertEqual(len(COMMAND_REGISTRY), 387)
        self.assertEqual(len({entry.category for entry in COMMAND_REGISTRY}), 41)
        self.assertEqual(command_registry_doctor()["status"], "OK")
        self.assertEqual(action_policy_doctor()["status"], "OK")

    def test_learning_memory_apply_preview_is_confirmable_and_read_only(self) -> None:
        with TemporaryDirectory() as temp_dir:
            _, store, pilot, bridge, _, skills, proposal = build_test_learning_apply(
                Path(temp_dir)
            )
            before = (
                store.working_path.read_bytes(),
                store.persistent_path.read_bytes(),
                json.dumps(pilot.learning_proposals.snapshot(), sort_keys=True),
                json.dumps(pilot.learning_applies.snapshot(), sort_keys=True),
            )
            output = format_learning_memory_apply_command(
                f"/experience learning apply-preview {proposal.id}",
                bridge=bridge,
                decisions=pilot.learning_decisions,
                proposals=pilot.learning_proposals,
                applies=pilot.learning_applies,
                memory_store=store,
                skill_library=skills,
            )
            after = (
                store.working_path.read_bytes(),
                store.persistent_path.read_bytes(),
                json.dumps(pilot.learning_proposals.snapshot(), sort_keys=True),
                json.dumps(pilot.learning_applies.snapshot(), sort_keys=True),
            )

        self.assertIn("Status: CONFIRMABLE", output)
        self.assertIn("confirmation_token: CONFIRM-LEARNING-APPLY-", output)
        self.assertIn("global_exact_duplicate_absent: true", output)
        self.assertIn("exactly one fresh", output)
        self.assertEqual(before, after)

    def test_learning_memory_apply_status_is_available_before_any_apply(self) -> None:
        with TemporaryDirectory() as temp_dir:
            _, store, pilot, _, _, skills, _ = build_test_learning_apply(Path(temp_dir))
            before = (
                store.working_path.read_bytes(),
                store.persistent_path.read_bytes(),
                json.dumps(pilot.learning_applies.snapshot(), sort_keys=True),
            )
            output = format_learning_memory_apply_command(
                "/experience learning apply-status",
                bridge=OperatorReviewedLearningBridge([{"invalid": True}]),
                decisions=pilot.learning_decisions,
                proposals=pilot.learning_proposals,
                applies=pilot.learning_applies,
                memory_store=store,
                skill_library=skills,
            )
            after = (
                store.working_path.read_bytes(),
                store.persistent_path.read_bytes(),
                json.dumps(pilot.learning_applies.snapshot(), sort_keys=True),
            )

        self.assertIn("Status: EMPTY", output)
        self.assertIn("receipts: 0/1", output)
        self.assertEqual(before, after)

    def test_learning_memory_apply_wrong_token_refuses_without_mutation(self) -> None:
        with TemporaryDirectory() as temp_dir:
            _, store, pilot, bridge, _, skills, proposal = build_test_learning_apply(
                Path(temp_dir)
            )
            before = store.persistent_path.read_bytes()
            output = format_learning_memory_apply_command(
                f"/experience learning apply {proposal.id} WRONG-TOKEN",
                bridge=bridge,
                decisions=pilot.learning_decisions,
                proposals=pilot.learning_proposals,
                applies=pilot.learning_applies,
                memory_store=store,
                skill_library=skills,
            )
            after = store.persistent_path.read_bytes()
            receipts_after = pilot.learning_applies.snapshot()

        self.assertIn("Status: REFUSED", output)
        self.assertIn("token mismatch", output)
        self.assertEqual(before, after)
        self.assertEqual(receipts_after, ())

    def test_learning_memory_apply_restores_store_when_verification_fails(self) -> None:
        with TemporaryDirectory() as temp_dir:
            _, store, pilot, bridge, _, skills, proposal = build_test_learning_apply(
                Path(temp_dir)
            )
            dependencies = {
                "bridge": bridge,
                "decisions": pilot.learning_decisions,
                "proposals": pilot.learning_proposals,
                "applies": pilot.learning_applies,
                "memory_store": store,
                "skill_library": skills,
            }
            preview = format_learning_memory_apply_command(
                f"/experience learning apply-preview {proposal.id}",
                **dependencies,
            )
            token = _id_from_output(preview, "confirmation_token:")
            before = store.persistent_path.read_bytes()
            with patch(
                "proto_mind.experience_learning_apply._verify_created_record",
                side_effect=ValueError("verification fixture"),
            ):
                output = format_learning_memory_apply_command(
                    f"/experience learning apply {proposal.id} {token}",
                    **dependencies,
                )
            after = store.persistent_path.read_bytes()
            receipts_after = pilot.learning_applies.snapshot()

        self.assertIn("Status: REFUSED", output)
        self.assertIn("original memory records were restored", output)
        self.assertEqual(before, after)
        self.assertEqual(receipts_after, ())

    def test_learning_memory_apply_refuses_stale_proposal(self) -> None:
        with TemporaryDirectory() as temp_dir:
            _, store, pilot, bridge, candidate, skills, proposal = build_test_learning_apply(
                Path(temp_dir)
            )
            stale = replace(
                proposal,
                created_at=(datetime.now(UTC) - timedelta(minutes=16)).isoformat(),
            )
            pilot.learning_proposals._receipts[candidate.id] = stale
            before = store.persistent_path.read_bytes()
            output = format_learning_memory_apply_command(
                f"/experience learning apply-preview {proposal.id}",
                bridge=bridge,
                decisions=pilot.learning_decisions,
                proposals=pilot.learning_proposals,
                applies=pilot.learning_applies,
                memory_store=store,
                skill_library=skills,
            )
            after = store.persistent_path.read_bytes()

        self.assertIn("Status: NOT READY", output)
        self.assertIn("older than the 15-minute", output)
        self.assertEqual(before, after)

    def test_learning_memory_apply_refuses_skill_target(self) -> None:
        with TemporaryDirectory() as temp_dir:
            _, store, pilot, bridge, _, skills, proposal = build_test_learning_apply(
                Path(temp_dir),
                target="skill",
            )
            skills_before = skills.skills_path.read_bytes()
            output = format_learning_memory_apply_command(
                f"/experience learning apply-preview {proposal.id}",
                bridge=bridge,
                decisions=pilot.learning_decisions,
                proposals=pilot.learning_proposals,
                applies=pilot.learning_applies,
                memory_store=store,
                skill_library=skills,
            )
            skills_after = skills.skills_path.read_bytes()
            receipts_after = pilot.learning_applies.snapshot()

        self.assertIn("Status: NOT READY", output)
        self.assertIn("Skill apply remains disabled", output)
        self.assertEqual(skills_before, skills_after)
        self.assertEqual(receipts_after, ())

    def test_learning_memory_apply_refuses_global_exact_duplicate(self) -> None:
        with TemporaryDirectory() as temp_dir:
            _, store, pilot, bridge, candidate, skills, proposal = build_test_learning_apply(
                Path(temp_dir)
            )
            records = store.load_persistent_memory()
            records.append(
                MemoryRecord(
                    id="mem_unselected_duplicate",
                    content=candidate.text,
                    type="lesson",
                    importance=0.7,
                    source="test",
                )
            )
            store.save_persistent_memory(records)
            before = store.persistent_path.read_bytes()
            output = format_learning_memory_apply_command(
                f"/experience learning apply-preview {proposal.id}",
                bridge=bridge,
                decisions=pilot.learning_decisions,
                proposals=pilot.learning_proposals,
                applies=pilot.learning_applies,
                memory_store=store,
                skill_library=skills,
            )
            after = store.persistent_path.read_bytes()

        self.assertIn("Status: NOT READY", output)
        self.assertIn("active exact duplicate", output)
        self.assertEqual(before, after)

    def test_learning_memory_apply_token_binds_current_store_hash(self) -> None:
        with TemporaryDirectory() as temp_dir:
            _, store, pilot, bridge, _, skills, proposal = build_test_learning_apply(
                Path(temp_dir)
            )
            dependencies = {
                "bridge": bridge,
                "decisions": pilot.learning_decisions,
                "proposals": pilot.learning_proposals,
                "applies": pilot.learning_applies,
                "memory_store": store,
                "skill_library": skills,
            }
            preview = format_learning_memory_apply_command(
                f"/experience learning apply-preview {proposal.id}",
                **dependencies,
            )
            token = _id_from_output(preview, "confirmation_token:")
            records = store.load_persistent_memory()
            records.append(MemoryRecord("Store drift", "project_fact", 0.6, "test"))
            store.save_persistent_memory(records)
            before = store.persistent_path.read_bytes()
            output = format_learning_memory_apply_command(
                f"/experience learning apply {proposal.id} {token}",
                **dependencies,
            )
            after = store.persistent_path.read_bytes()
            receipts_after = pilot.learning_applies.snapshot()

        self.assertIn("Status: REFUSED", output)
        self.assertIn("token mismatch", output)
        self.assertEqual(before, after)
        self.assertEqual(receipts_after, ())

    def test_learning_memory_apply_creates_one_verified_record_and_receipt(self) -> None:
        with TemporaryDirectory() as temp_dir:
            _, store, pilot, bridge, candidate, skills, proposal = build_test_learning_apply(
                Path(temp_dir)
            )
            dependencies = {
                "bridge": bridge,
                "decisions": pilot.learning_decisions,
                "proposals": pilot.learning_proposals,
                "applies": pilot.learning_applies,
                "memory_store": store,
                "skill_library": skills,
            }
            working_before = store.working_path.read_bytes()
            skills_before = skills.skills_path.read_bytes() if skills.skills_path.exists() else None
            count_before = len(store.load_persistent_memory())
            preview = format_learning_memory_apply_command(
                f"/experience learning apply-preview {proposal.id}",
                **dependencies,
            )
            token = _id_from_output(preview, "confirmation_token:")
            output = format_learning_memory_apply_command(
                f"/experience learning apply {proposal.id} {token}",
                **dependencies,
            )
            records = store.load_persistent_memory()
            receipt = pilot.learning_applies.get(proposal.id)
            working_after = store.working_path.read_bytes()
            skills_after = skills.skills_path.read_bytes() if skills.skills_path.exists() else None

        self.assertIn("Status: APPLIED AND VERIFIED", output)
        self.assertEqual(len(records), count_before + 1)
        created = next(record for record in records if record.id == receipt.created_record_id)
        self.assertEqual(created.content, candidate.text)
        self.assertEqual(created.type, "lesson")
        self.assertEqual(created.source, "experience_learning_proposal")
        self.assertEqual(created.tags, ["experience", "operator_reviewed"])
        self.assertTrue(receipt.record_verified)
        self.assertTrue(receipt.run_once_guard)
        self.assertEqual(receipt.rollback_suggestion, f"/memory forget {created.id}")
        self.assertNotEqual(receipt.before_store_sha256, receipt.after_store_sha256)
        self.assertEqual(working_before, working_after)
        self.assertEqual(skills_before, skills_after)

    def test_learning_memory_apply_run_once_refuses_second_execution(self) -> None:
        with TemporaryDirectory() as temp_dir:
            _, store, pilot, bridge, _, skills, proposal = build_test_learning_apply(
                Path(temp_dir)
            )
            dependencies = {
                "bridge": bridge,
                "decisions": pilot.learning_decisions,
                "proposals": pilot.learning_proposals,
                "applies": pilot.learning_applies,
                "memory_store": store,
                "skill_library": skills,
            }
            preview = format_learning_memory_apply_command(
                f"/experience learning apply-preview {proposal.id}",
                **dependencies,
            )
            token = _id_from_output(preview, "confirmation_token:")
            first = format_learning_memory_apply_command(
                f"/experience learning apply {proposal.id} {token}",
                **dependencies,
            )
            before = (
                store.persistent_path.read_bytes(),
                json.dumps(pilot.learning_applies.snapshot(), sort_keys=True),
            )
            second = format_learning_memory_apply_command(
                f"/experience learning apply {proposal.id} {token}",
                **dependencies,
            )
            after = (
                store.persistent_path.read_bytes(),
                json.dumps(pilot.learning_applies.snapshot(), sort_keys=True),
            )

        self.assertIn("Status: APPLIED AND VERIFIED", first)
        self.assertIn("Status: REFUSED", second)
        self.assertIn("already applied", second)
        self.assertEqual(before, after)

    def test_learning_memory_apply_receipt_and_doctor_verify_record(self) -> None:
        with TemporaryDirectory() as temp_dir:
            _, store, pilot, bridge, _, skills, proposal = build_test_learning_apply(
                Path(temp_dir)
            )
            dependencies = {
                "bridge": bridge,
                "decisions": pilot.learning_decisions,
                "proposals": pilot.learning_proposals,
                "applies": pilot.learning_applies,
                "memory_store": store,
                "skill_library": skills,
            }
            preview = format_learning_memory_apply_command(
                f"/experience learning apply-preview {proposal.id}",
                **dependencies,
            )
            token = _id_from_output(preview, "confirmation_token:")
            format_learning_memory_apply_command(
                f"/experience learning apply {proposal.id} {token}",
                **dependencies,
            )
            receipt_output = format_learning_memory_apply_command(
                f"/experience learning apply-receipt {proposal.id}",
                **dependencies,
            )
            doctor = format_learning_memory_apply_command(
                "/experience learning apply-doctor",
                **dependencies,
            )

        self.assertIn("Status: FOUND", receipt_output)
        self.assertIn("receipt_hash:", receipt_output)
        self.assertIn("rollback_suggestion: /memory forget mem_learn_", receipt_output)
        self.assertIn("Status: OK", doctor)
        self.assertIn("record verification are healthy", doctor)

    def test_learning_memory_apply_doctor_detects_record_drift(self) -> None:
        with TemporaryDirectory() as temp_dir:
            _, store, pilot, bridge, _, skills, proposal = build_test_learning_apply(
                Path(temp_dir)
            )
            dependencies = {
                "bridge": bridge,
                "decisions": pilot.learning_decisions,
                "proposals": pilot.learning_proposals,
                "applies": pilot.learning_applies,
                "memory_store": store,
                "skill_library": skills,
            }
            preview = format_learning_memory_apply_command(
                f"/experience learning apply-preview {proposal.id}",
                **dependencies,
            )
            token = _id_from_output(preview, "confirmation_token:")
            format_learning_memory_apply_command(
                f"/experience learning apply {proposal.id} {token}",
                **dependencies,
            )
            receipt = pilot.learning_applies.get(proposal.id)
            records = store.load_persistent_memory()
            next(record for record in records if record.id == receipt.created_record_id).content = "drift"
            store.save_persistent_memory(records)
            doctor = format_learning_memory_apply_command(
                "/experience learning apply-doctor",
                **dependencies,
            )

        self.assertIn("Status: ERROR", doctor)
        self.assertIn("no longer matches", doctor)

    def test_learning_memory_apply_works_through_shared_handler_only_for_memory(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            coordinator, store, pilot, _, _, skills, proposal = build_test_learning_apply(root)
            setattr(coordinator, "_proto_mind_experience_pilot_v1", pilot)
            logger = SessionOperatorLogger(root / "session.jsonl", enabled=False)
            working_before = store.working_path.read_bytes()
            skills_before = skills.skills_path.read_bytes() if skills.skills_path.exists() else None
            preview = process_interactive_input(
                f"/experience learning apply-preview {proposal.id}",
                coordinator=coordinator,
                session_logger=logger,
                project_root=root,
            )
            token = _id_from_output(preview, "confirmation_token:")
            output = process_interactive_input(
                f"/experience learning apply {proposal.id} {token}",
                coordinator=coordinator,
                session_logger=logger,
                project_root=root,
            )
            working_after = store.working_path.read_bytes()
            skills_after = skills.skills_path.read_bytes() if skills.skills_path.exists() else None
            receipt_count = len(pilot.learning_applies.snapshot())
            log_count = logger.status().entry_count

        self.assertIn("Status: APPLIED AND VERIFIED", output)
        self.assertEqual(receipt_count, 1)
        self.assertEqual(working_before, working_after)
        self.assertEqual(skills_before, skills_after)
        self.assertEqual(log_count, 0)

    def test_learning_memory_apply_registry_policy_and_process_boundary(self) -> None:
        registry = {entry.prefix: entry for entry in COMMAND_REGISTRY}
        spec = registry["/experience learning apply"]

        self.assertTrue(LEARNING_MEMORY_APPLY_ENGINE_INSTALLED)
        self.assertEqual(LEARNING_MEMORY_APPLY_MAX_RECEIPTS, 1)
        self.assertFalse(spec.read_only)
        self.assertEqual(spec.mutates, "memory")
        self.assertEqual(spec.risk, "medium")
        self.assertEqual(
            classify_command("/experience learning apply proposal token").policy_class,
            "confirmation_required",
        )
        self.assertEqual(
            classify_command("/experience learning apply-preview proposal").policy_class,
            "auto_allowed",
        )
        self.assertNotIn("/experience learning apply-batch", registry)
        self.assertEqual(len(COMMAND_REGISTRY), 387)
        self.assertEqual(len({entry.category for entry in COMMAND_REGISTRY}), 41)
        self.assertEqual(command_registry_doctor()["status"], "OK")
        self.assertEqual(action_policy_doctor()["status"], "OK")

    def test_learning_memory_apply_embeds_verified_durable_provenance(self) -> None:
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
            created = next(
                record
                for record in store.load_persistent_memory()
                if record.id == receipt.created_record_id
            )
            check = verify_memory_provenance(created)

        self.assertIn("Status: APPLIED AND VERIFIED", output)
        self.assertIsNotNone(created.provenance)
        self.assertEqual(created.provenance["schema"], MEMORY_LESSON_PROVENANCE_SCHEMA)
        self.assertEqual(created.provenance["proposal_id"], proposal.id)
        self.assertEqual(created.provenance["candidate_id"], proposal.candidate_id)
        self.assertEqual(created.provenance["decision_id"], proposal.decision_id)
        self.assertEqual(created.provenance["evidence_event_ids"], proposal.evidence_event_ids)
        self.assertEqual(receipt.durable_provenance_id, created.provenance["id"])
        self.assertTrue(check.verified)

    def test_learning_lesson_rollback_suggestion_soft_forgets_verified_record(self) -> None:
        with TemporaryDirectory() as temp_dir:
            _, store, pilot, bridge, _, skills, proposal = build_test_learning_apply(
                Path(temp_dir)
            )
            _, receipt = apply_test_learning_proposal(
                store,
                pilot,
                bridge,
                skills,
                proposal,
            )
            output = format_memory_command(receipt.rollback_suggestion, store)
            why = format_memory_command(f"/memory why {receipt.created_record_id}", store)
            record = next(
                item
                for item in store.load_persistent_memory()
                if item.id == receipt.created_record_id
            )

        self.assertIn("Forgotten:", output)
        self.assertFalse(record.active)
        self.assertIn("Status: VERIFIED", why)
        self.assertIn("active: false", why)

    def test_learning_outcome_benchmark_covers_all_safe_candidates(self) -> None:
        report = run_learning_outcome_benchmark()

        self.assertEqual(report.status, "OK")
        self.assertEqual(report.keep_status, "KEEP_CANDIDATE")
        self.assertEqual(report.reject_status, "REJECT_CANDIDATE")
        self.assertEqual(report.supersede_status, "SUPERSEDE_CANDIDATE")
        self.assertEqual(report.insufficient_status, "NEEDS_MORE_EVIDENCE")
        self.assertTrue(all(report.checks.values()))
        self.assertFalse(report.failed_checks)

    def test_learning_outcome_benchmark_is_non_mutating_and_readable(self) -> None:
        report = run_learning_outcome_benchmark()
        output = format_learning_outcome_benchmark(report)

        self.assertTrue(report.persistent_bytes_unchanged)
        self.assertTrue(report.working_bytes_unchanged)
        self.assertIn("Status: OK", output)
        self.assertIn("keep_case: KEEP_CANDIDATE", output)
        self.assertIn("no lesson mutation", output)
        self.assertIn("no lesson mutation, apply, promotion", output)

    def test_learning_outcome_review_finds_grounded_later_use_after_restart(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _, store, pilot, bridge, _, skills, proposal = build_test_learning_apply(root)
            _, receipt = apply_test_learning_proposal(store, pilot, bridge, skills, proposal)
            lesson = next(
                record
                for record in store.load_persistent_memory()
                if record.id == receipt.created_record_id
            )
            store.save_persistent_memory([lesson])
            store.save_working_memory([])
            coordinator = Coordinator(
                observer=Observer(),
                memory_keeper=MemoryKeeper(MemoryStore(store.working_path, store.persistent_path)),
                reasoner=MockReasoner(),
            )
            query = "As we discussed earlier, what did we learn about the active SQLite decision?"
            result = coordinator.handle(query)
            events = ExperienceTraceBuilder(
                session_id="outcome-live-test",
                source="test",
            ).build_turn_events(
                query,
                result,
                turn_id="1",
                trace_id="outcome-live",
                created_at=(datetime.now(UTC) + timedelta(seconds=1)).isoformat(),
            )
            before = store.persistent_path.read_bytes()
            output = format_learning_outcome_command(
                f"/experience learning outcome-review {lesson.id}",
                events=events,
                memory_store=store,
            )
            after = store.persistent_path.read_bytes()

        self.assertIn("Status: KEEP_CANDIDATE", output)
        self.assertIn(lesson.provenance["id"], output)
        self.assertIn("grounding_evaluated", output)
        self.assertIn(f"/memory why {lesson.id}", output)
        self.assertEqual(before, after)

    def test_learning_outcome_review_refuses_unknown_and_unprovenanced_memory(self) -> None:
        unprovenanced = MemoryRecord(
            id="legacy_lesson",
            content="Legacy lesson without evidence.",
            type="lesson",
            importance=0.8,
            source="legacy",
        )
        reviewer = LearningOutcomeReviewer([], [unprovenanced])

        missing = reviewer.review("missing_lesson")
        legacy = reviewer.review(unprovenanced.id)

        self.assertEqual(missing.status, "NOT_FOUND")
        self.assertEqual(legacy.status, "ERROR")
        self.assertFalse(legacy.checks["durable_provenance_verified"])
        self.assertIn(legacy.status, LEARNING_OUTCOME_STATUSES)

    def test_learning_outcome_review_rejects_malformed_experience_trace(self) -> None:
        with TemporaryDirectory() as temp_dir:
            _, store, pilot, bridge, _, skills, proposal = build_test_learning_apply(
                Path(temp_dir)
            )
            _, receipt = apply_test_learning_proposal(store, pilot, bridge, skills, proposal)
            lesson = next(
                record
                for record in store.load_persistent_memory()
                if record.id == receipt.created_record_id
            )
            malformed = ExperienceEvent(
                id="evt_bad",
                created_at="not-a-timestamp",
                event_type="memory_retrieved",
                session_id="bad",
                turn_id="1",
                source="test",
                source_event_ids=["evt_missing"],
                payload={"selected_records": [{"id": lesson.id}]},
            )
            review = LearningOutcomeReviewer([malformed], [lesson]).review(lesson.id)

        self.assertEqual(review.status, "ERROR")
        self.assertFalse(review.checks["experience_trace_valid"])
        self.assertTrue(any("invalid created_at" in issue for issue in review.issues))

    def test_learning_outcome_doctor_handles_empty_state_without_writes(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = MemoryStore(root / "working.json", root / "persistent.json")
            before = (
                store.working_path.read_bytes(),
                store.persistent_path.read_bytes(),
            )
            output = format_learning_outcome_command(
                "/experience learning outcome-doctor",
                events=[],
                memory_store=store,
            )
            usage = format_learning_outcome_command(
                "/experience learning outcome-review",
                events=[],
                memory_store=store,
            )
            after = (
                store.working_path.read_bytes(),
                store.persistent_path.read_bytes(),
            )

        self.assertIn("Learning Outcome Review Doctor v1", output)
        self.assertIn("lessons: 0", output)
        self.assertIn("Usage: /experience learning outcome-review <memory_id>", usage)
        self.assertEqual(before, after)

    def test_learning_outcome_commands_work_through_shared_handler_without_logging(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            coordinator, store, _ = build_test_system(root / "cognitive")
            logger = SessionOperatorLogger(root / "session.jsonl", enabled=False)
            before = (
                store.working_path.read_bytes(),
                store.persistent_path.read_bytes(),
            )
            output = process_interactive_input(
                "/experience learning outcome-doctor",
                coordinator=coordinator,
                session_logger=logger,
                project_root=root,
            )
            after = (
                store.working_path.read_bytes(),
                store.persistent_path.read_bytes(),
            )

        self.assertIn("Learning Outcome Review Doctor v1", output)
        self.assertEqual(before, after)
        self.assertEqual(logger.status().entry_count, 0)

    def test_learning_outcome_stays_inside_read_only_registry_family(self) -> None:
        registry = {entry.prefix: entry for entry in COMMAND_REGISTRY}
        spec = registry["/experience learning"]

        self.assertEqual(LEARNING_OUTCOME_MODE, "read_only_exact_provenance_outcome_review")
        self.assertTrue(spec.read_only)
        self.assertEqual(spec.mutates, "none")
        self.assertEqual(
            classify_command("/experience learning outcome-review mem_learn_x").policy_class,
            "auto_allowed",
        )
        self.assertEqual(len(COMMAND_REGISTRY), 387)
        self.assertEqual(len({entry.category for entry in COMMAND_REGISTRY}), 41)
        self.assertEqual(command_registry_doctor()["status"], "OK")
        self.assertEqual(action_policy_doctor()["status"], "OK")

    def test_learning_lifecycle_benchmark_covers_exact_operator_gate(self) -> None:
        report = run_learning_lifecycle_benchmark()
        output = format_learning_lifecycle_benchmark(report)

        self.assertEqual(report.status, "OK")
        self.assertEqual(report.receipt_count, 3)
        self.assertTrue(all(report.checks.values()))
        self.assertIn("wrong_token_refused", output)
        self.assertIn("no memory/skill/event mutation", output)

    def test_learning_lifecycle_preview_and_decision_bind_current_outcome(self) -> None:
        with TemporaryDirectory() as temp_dir:
            _, store, events, review = build_test_learning_outcome_review(Path(temp_dir))
            session = OperatorReviewedLearningLifecycleSession()
            before = (store.working_path.read_bytes(), store.persistent_path.read_bytes())
            preview = format_learning_lifecycle_command(
                f"/experience learning outcome-confirm-preview {review.lesson_memory_id}",
                events=events,
                memory_store=store,
                session=session,
            )
            token = _id_from_output(preview, "confirmation_token:")
            recorded = format_learning_lifecycle_command(
                f"/experience learning decide outcome keep {review.lesson_memory_id} {token}",
                events=events,
                memory_store=store,
                session=session,
            )
            after = (store.working_path.read_bytes(), store.persistent_path.read_bytes())
            receipt = session.get(review.lesson_memory_id)

        self.assertIn("Status: CONFIRMABLE", preview)
        self.assertEqual(token, learning_lifecycle_confirmation_token(review))
        self.assertIn("Status: RECORDED IN PROCESS MEMORY", recorded)
        self.assertEqual(receipt.decision, "keep")
        self.assertFalse(receipt.memory_mutation_performed)
        self.assertFalse(receipt.persistence_performed)
        self.assertEqual(before, after)

    def test_learning_lifecycle_refuses_wrong_token_and_weak_evidence(self) -> None:
        with TemporaryDirectory() as temp_dir:
            _, store, events, review = build_test_learning_outcome_review(Path(temp_dir))
            wrong_session = OperatorReviewedLearningLifecycleSession()
            wrong = format_learning_lifecycle_command(
                f"/experience learning decide outcome keep {review.lesson_memory_id} WRONG-TOKEN",
                events=events,
                memory_store=store,
                session=wrong_session,
            )
            mismatch_session = OperatorReviewedLearningLifecycleSession()
            mismatch = format_learning_lifecycle_command(
                f"/experience learning decide outcome reject {review.lesson_memory_id} "
                f"{learning_lifecycle_confirmation_token(review)}",
                events=events,
                memory_store=store,
                session=mismatch_session,
            )
            weak_session = OperatorReviewedLearningLifecycleSession()
            weak_preview = format_learning_lifecycle_command(
                f"/experience learning outcome-confirm-preview {review.lesson_memory_id}",
                events=[],
                memory_store=store,
                session=weak_session,
            )
            weak = format_learning_lifecycle_command(
                f"/experience learning decide outcome keep {review.lesson_memory_id} "
                "CONFIRM-OUTCOME-KEEP-UNAVAILABLE",
                events=[],
                memory_store=store,
                session=weak_session,
            )

        self.assertIn("confirmation token mismatch", wrong.lower())
        self.assertEqual(wrong_session.snapshot(), ())
        self.assertIn("requires decision 'keep'", mismatch)
        self.assertEqual(mismatch_session.snapshot(), ())
        self.assertIn("Status: NOT CONFIRMABLE", weak_preview)
        self.assertIn("not decision-eligible", weak)
        self.assertEqual(weak_session.snapshot(), ())

    def test_learning_lifecycle_terminal_receipt_refuses_second_decision(self) -> None:
        with TemporaryDirectory() as temp_dir:
            _, store, events, review = build_test_learning_outcome_review(Path(temp_dir))
            session = OperatorReviewedLearningLifecycleSession()
            token = learning_lifecycle_confirmation_token(review)
            first = format_learning_lifecycle_command(
                f"/experience learning decide outcome keep {review.lesson_memory_id} {token}",
                events=events,
                memory_store=store,
                session=session,
            )
            snapshot = json.dumps(session.snapshot(), sort_keys=True)
            second = format_learning_lifecycle_command(
                f"/experience learning decide outcome keep {review.lesson_memory_id} {token}",
                events=events,
                memory_store=store,
                session=session,
            )

        self.assertIn("RECORDED IN PROCESS MEMORY", first)
        self.assertIn("already has terminal", second)
        self.assertEqual(snapshot, json.dumps(session.snapshot(), sort_keys=True))

    def test_learning_lifecycle_receipt_inspection_and_doctor(self) -> None:
        with TemporaryDirectory() as temp_dir:
            _, store, events, review = build_test_learning_outcome_review(Path(temp_dir))
            session = OperatorReviewedLearningLifecycleSession()
            token = learning_lifecycle_confirmation_token(review)
            session.decide(review, "keep", token=token)
            inspected = format_learning_lifecycle_command(
                f"/experience learning outcome-decision {review.lesson_memory_id}",
                events=events,
                memory_store=store,
                session=session,
            )
            doctor = format_learning_lifecycle_command(
                "/experience learning outcome-decision-doctor",
                events=events,
                memory_store=store,
                session=session,
            )

        self.assertIn("Learning Lifecycle Decision Receipt v1", inspected)
        self.assertIn("memory_mutation_performed: False", inspected)
        self.assertIn("Status: OK", doctor)
        self.assertIn("receipts: 1/32", doctor)

    def test_learning_lifecycle_doctor_detects_forbidden_mutation_claim(self) -> None:
        with TemporaryDirectory() as temp_dir:
            _, _, events, review = build_test_learning_outcome_review(Path(temp_dir))
            session = OperatorReviewedLearningLifecycleSession()
            receipt = session.decide(
                review,
                "keep",
                token=learning_lifecycle_confirmation_token(review),
            )
            session._receipts[review.lesson_memory_id] = replace(
                receipt,
                id="learnlife_tampered",
                evidence_event_ids=["evt_unrelated"],
                memory_mutation_performed=True,
            )
            report = session.doctor({review.lesson_memory_id: review})

        self.assertEqual(report.status, "ERROR")
        self.assertIn("forbidden mutation", " ".join(report.issues))
        self.assertIn("does not match its review hash", " ".join(report.issues))
        self.assertIn("outside its evidence ids", " ".join(report.issues))

    def test_learning_lifecycle_receipts_expire_on_process_restart(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _, _, _, review = build_test_learning_outcome_review(root)
            pilot = SupervisedExperiencePilot(root, session_id="lifecycle-original")
            pilot.learning_lifecycle.decide(
                review,
                "keep",
                token=learning_lifecycle_confirmation_token(review),
            )
            restarted = SupervisedExperiencePilot(root, session_id="lifecycle-restarted")

        self.assertEqual(len(pilot.learning_lifecycle.snapshot()), 1)
        self.assertEqual(restarted.learning_lifecycle.snapshot(), ())

    def test_learning_lifecycle_shared_handler_changes_process_receipt_only(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            coordinator, store, _, review = build_test_learning_outcome_review(root)
            logger = SessionOperatorLogger(root / "session.jsonl", enabled=False)
            pilot = get_experience_pilot(coordinator, project_root=root)
            pilot.preview()
            pilot.consent(pilot.expected_consent_phrase)
            query = "As we discussed earlier, what did we learn about the active SQLite decision?"
            observation = pilot.observe_normal_turn(query, coordinator.handle(query))
            self.assertTrue(observation.capture_performed)
            preview = process_interactive_input(
                f"/experience learning outcome-confirm-preview {review.lesson_memory_id}",
                coordinator=coordinator,
                session_logger=logger,
                project_root=root,
            )
            token = _id_from_output(preview, "confirmation_token:")
            before = (
                store.working_path.read_bytes(),
                store.persistent_path.read_bytes(),
                json.dumps(pilot.snapshot(), sort_keys=True),
            )
            recorded = process_interactive_input(
                f"/experience learning decide outcome keep {review.lesson_memory_id} {token}",
                coordinator=coordinator,
                session_logger=logger,
                project_root=root,
            )
            after = (
                store.working_path.read_bytes(),
                store.persistent_path.read_bytes(),
                json.dumps(pilot.snapshot(), sort_keys=True),
            )

        self.assertIn("RECORDED IN PROCESS MEMORY", recorded)
        self.assertEqual(before, after)
        self.assertEqual(logger.status().entry_count, 0)

    def test_learning_lifecycle_reuses_registered_mutating_decision_gate(self) -> None:
        registry = {entry.prefix: entry for entry in COMMAND_REGISTRY}
        decide = registry["/experience learning decide"]

        self.assertEqual(
            LEARNING_LIFECYCLE_MODE,
            "operator_confirmed_process_memory_outcome_decision",
        )
        self.assertEqual(LEARNING_LIFECYCLE_MAX_RECEIPTS, 32)
        self.assertFalse(decide.read_only)
        self.assertEqual(decide.mutates, "session")
        self.assertEqual(
            classify_command(
                "/experience learning decide outcome keep mem_lesson CONFIRM-OUTCOME-KEEP-ABC"
            ).policy_class,
            "confirmation_required",
        )
        self.assertEqual(
            classify_command(
                "/experience learning outcome-confirm-preview mem_lesson"
            ).policy_class,
            "auto_allowed",
        )
        self.assertEqual(len(COMMAND_REGISTRY), 387)
        self.assertEqual(len({entry.category for entry in COMMAND_REGISTRY}), 41)
        self.assertEqual(command_registry_doctor()["status"], "OK")
        self.assertEqual(action_policy_doctor()["status"], "OK")

    def test_learning_lifecycle_readiness_revalidates_current_exact_evidence(self) -> None:
        with TemporaryDirectory() as temp_dir:
            _, store, events, review = build_test_learning_outcome_review(Path(temp_dir))
            session = OperatorReviewedLearningLifecycleSession()
            receipt = session.decide(
                review,
                "keep",
                token=learning_lifecycle_confirmation_token(review),
            )
            before = (
                store.working_path.read_bytes(),
                store.persistent_path.read_bytes(),
                json.dumps(session.snapshot(), sort_keys=True),
            )
            report = LearningLifecycleApplyReadiness(
                memory_store=store,
                events=events,
            ).review(receipt)
            after = (
                store.working_path.read_bytes(),
                store.persistent_path.read_bytes(),
                json.dumps(session.snapshot(), sort_keys=True),
            )

        self.assertEqual(report.status, "READY FOR LIFECYCLE DESIGN REVIEW")
        self.assertTrue(report.ready_for_design_review)
        self.assertTrue(all(report.checks.values()))
        self.assertTrue(report.lifecycle_engine_installed)
        self.assertFalse(report.executable)
        self.assertEqual(report.transition.expected_record_mutations, 0)
        self.assertEqual(before, after)

    def test_learning_lifecycle_readiness_and_plan_are_readable_and_non_mutating(self) -> None:
        with TemporaryDirectory() as temp_dir:
            _, store, events, review = build_test_learning_outcome_review(Path(temp_dir))
            session = OperatorReviewedLearningLifecycleSession()
            receipt = session.decide(
                review,
                "keep",
                token=learning_lifecycle_confirmation_token(review),
            )
            before = (store.working_path.read_bytes(), store.persistent_path.read_bytes())
            readiness = format_learning_lifecycle_readiness_command(
                f"/experience learning lifecycle-readiness {receipt.id}",
                events=events,
                memory_store=store,
                session=session,
            )
            plan = format_learning_lifecycle_readiness_command(
                f"/experience learning lifecycle-plan {review.lesson_memory_id}",
                events=events,
                memory_store=store,
                session=session,
            )
            after = (store.working_path.read_bytes(), store.persistent_path.read_bytes())

        self.assertIn("READY FOR LIFECYCLE DESIGN REVIEW", readiness)
        self.assertIn("lifecycle_engine_installed: true", readiness)
        self.assertIn("Status: DESIGN REVIEW ONLY", plan)
        self.assertIn("expected_record_mutations: 0", plan)
        self.assertIn("fresh exact lifecycle apply preview", plan)
        self.assertEqual(before, after)

    def test_learning_lifecycle_readiness_fails_closed_on_evidence_drift(self) -> None:
        with TemporaryDirectory() as temp_dir:
            _, store, events, review = build_test_learning_outcome_review(Path(temp_dir))
            session = OperatorReviewedLearningLifecycleSession()
            receipt = session.decide(
                review,
                "keep",
                token=learning_lifecycle_confirmation_token(review),
            )
            report = LearningLifecycleApplyReadiness(
                memory_store=store,
                events=[],
            ).review(receipt)

        self.assertEqual(report.status, "NOT READY")
        self.assertFalse(report.checks["current_outcome_matches"])
        self.assertFalse(report.checks["current_review_hash_matches"])
        self.assertFalse(report.ready_for_design_review)
        self.assertFalse(report.mutation_performed)

    def test_learning_lifecycle_readiness_fails_closed_on_inactive_lesson(self) -> None:
        with TemporaryDirectory() as temp_dir:
            _, store, events, review = build_test_learning_outcome_review(Path(temp_dir))
            session = OperatorReviewedLearningLifecycleSession()
            receipt = session.decide(
                review,
                "keep",
                token=learning_lifecycle_confirmation_token(review),
            )
            records = store.load_persistent_memory()
            records[0].active = False
            store.save_persistent_memory(records)
            report = LearningLifecycleApplyReadiness(
                memory_store=store,
                events=events,
            ).review(receipt)

        self.assertEqual(report.status, "NOT READY")
        self.assertFalse(report.checks["lesson_active"])
        self.assertFalse(report.ready_for_design_review)

    def test_learning_lifecycle_supersede_requires_active_verified_replacement(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _, store, events, keep_review = build_test_learning_outcome_review(root)
            old = store.load_persistent_memory()[0]
            base_time = datetime.now(UTC) + timedelta(seconds=2)
            payload = {
                "schema": "memory.lesson.v1",
                "content": "Use a narrower verified replacement lesson.",
                "type": "lesson",
                "importance": 0.9,
                "source": "experience_learning_proposal",
                "tags": ["replacement"],
                "confidence": 0.9,
            }
            proposal_hash = "b" * 64
            replacement_id = "mem_lifecycle_replacement"
            provenance = build_learning_lesson_provenance(
                memory_id=replacement_id,
                applied_at=base_time.isoformat(),
                proposal_id=f"learnprop_{proposal_hash[:16]}",
                proposal_hash=proposal_hash,
                candidate_id="learncand_lifecycle_replacement",
                candidate_hash="c" * 64,
                decision_id="learndec_lifecycle_replacement",
                eligibility_receipt_id="learnelig_lifecycle_replacement",
                selected_scope_hash="d" * 64,
                proposed_payload=payload,
                evidence_event_ids=["evt_lifecycle_replacement_source"],
                source_kinds=["correction"],
            )
            replacement = MemoryRecord(
                id=replacement_id,
                content=payload["content"],
                type="lesson",
                importance=0.9,
                source="experience_learning_proposal",
                tags=["replacement"],
                timestamp=base_time.isoformat(),
                updated_at=base_time.isoformat(),
                confidence=0.9,
                provenance=provenance,
            )
            correction = _correction_event(events)
            supersede_events = [
                *events,
                correction,
                *_replacement_events(correction, replacement_id),
            ]
            store.save_persistent_memory([old, replacement])
            supersede_review = LearningOutcomeReviewer(
                supersede_events,
                store.load_persistent_memory(),
            ).review(old.id)
            session = OperatorReviewedLearningLifecycleSession()
            receipt = session.decide(
                supersede_review,
                "supersede",
                token=learning_lifecycle_confirmation_token(supersede_review),
            )
            ready = LearningLifecycleApplyReadiness(
                memory_store=store,
                events=supersede_events,
            ).review(receipt)
            replacement.active = False
            store.save_persistent_memory([old, replacement])
            inactive = LearningLifecycleApplyReadiness(
                memory_store=store,
                events=supersede_events,
            ).review(receipt)

        self.assertEqual(keep_review.status, "KEEP_CANDIDATE")
        self.assertEqual(supersede_review.status, "SUPERSEDE_CANDIDATE")
        self.assertEqual(ready.status, "READY FOR LIFECYCLE DESIGN REVIEW")
        self.assertTrue(ready.checks["replacement_contract_valid"])
        self.assertEqual(ready.transition.expected_record_mutations, 1)
        self.assertEqual(inactive.status, "NOT READY")
        self.assertFalse(inactive.checks["replacement_contract_valid"])
        self.assertFalse(inactive.ready_for_design_review)

    def test_learning_lifecycle_readiness_doctor_rejects_unsafe_receipt(self) -> None:
        with TemporaryDirectory() as temp_dir:
            _, store, events, review = build_test_learning_outcome_review(Path(temp_dir))
            session = OperatorReviewedLearningLifecycleSession()
            receipt = session.decide(
                review,
                "keep",
                token=learning_lifecycle_confirmation_token(review),
            )
            session._receipts[review.lesson_memory_id] = replace(
                receipt,
                persistence_performed=True,
            )
            report = LearningLifecycleApplyReadiness(
                memory_store=store,
                events=events,
            ).doctor(session)

        self.assertEqual(report.status, "ERROR")
        self.assertIn("forbidden mutation", " ".join(report.issues))

    def test_learning_lifecycle_readiness_doctor_handles_empty_state(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _, store, _ = build_test_system(root)
            session = OperatorReviewedLearningLifecycleSession()
            before = (store.working_path.read_bytes(), store.persistent_path.read_bytes())
            doctor = format_learning_lifecycle_readiness_command(
                "/experience learning lifecycle-readiness-doctor",
                events=[],
                memory_store=store,
                session=session,
            )
            missing = format_learning_lifecycle_readiness_command(
                "/experience learning lifecycle-readiness missing",
                events=[],
                memory_store=store,
                session=session,
            )
            after = (store.working_path.read_bytes(), store.persistent_path.read_bytes())

        self.assertIn("Status: OK", doctor)
        self.assertIn("receipts: 0", doctor)
        self.assertIn("lifecycle_engine_installed: true", doctor)
        self.assertIn("Status: NOT FOUND", missing)
        self.assertEqual(before, after)

    def test_learning_lifecycle_transition_contracts_are_bounded(self) -> None:
        keep = learning_lifecycle_transition_contract("keep")
        reject = learning_lifecycle_transition_contract("reject")
        supersede = learning_lifecycle_transition_contract("supersede")
        unknown = learning_lifecycle_transition_contract("unknown")

        self.assertEqual(keep.expected_record_mutations, 0)
        self.assertEqual(reject.expected_record_mutations, 1)
        self.assertEqual(supersede.expected_record_mutations, 1)
        self.assertTrue(supersede.replacement_required)
        self.assertIn("never delete", supersede.rollback)
        self.assertEqual(unknown.expected_record_mutations, 0)
        self.assertIn("refuse", unknown.operation)

    def test_learning_lifecycle_readiness_uses_existing_read_only_family(self) -> None:
        registry = {entry.prefix: entry for entry in COMMAND_REGISTRY}
        family = registry["/experience learning"]

        self.assertEqual(
            LEARNING_LIFECYCLE_READINESS_MODE,
            "read_only_current_lifecycle_revalidation",
        )
        self.assertTrue(LEARNING_LIFECYCLE_APPLY_ENGINE_INSTALLED)
        self.assertTrue(family.read_only)
        self.assertEqual(family.mutates, "none")
        self.assertFalse(
            any(
                prefix.startswith("/experience learning lifecycle-apply")
                for prefix in registry
            )
        )
        self.assertEqual(
            classify_command(
                "/experience learning lifecycle-readiness mem_lesson"
            ).policy_class,
            "auto_allowed",
        )
        self.assertEqual(
            classify_command(
                "/experience learning apply lifecycle mem_lesson CONFIRM-LIFECYCLE-APPLY"
            ).policy_class,
            "confirmation_required",
        )
        self.assertEqual(len(COMMAND_REGISTRY), 387)
        self.assertEqual(len({entry.category for entry in COMMAND_REGISTRY}), 41)
        self.assertEqual(command_registry_doctor()["status"], "OK")
        self.assertEqual(action_policy_doctor()["status"], "OK")

    def test_learning_lifecycle_apply_status_and_doctor_are_safe_when_empty(self) -> None:
        with TemporaryDirectory() as temp_dir:
            _, store, _ = build_test_system(Path(temp_dir))
            lifecycle = OperatorReviewedLearningLifecycleSession()
            applies = OperatorReviewedLearningLifecycleApplySession()
            before = (store.working_path.read_bytes(), store.persistent_path.read_bytes())
            status = format_learning_lifecycle_apply_command(
                "/experience learning lifecycle-apply-status",
                events=[],
                memory_store=store,
                lifecycle_session=lifecycle,
                apply_session=applies,
            )
            doctor = format_learning_lifecycle_apply_command(
                "/experience learning lifecycle-apply-doctor",
                events=[],
                memory_store=store,
                lifecycle_session=lifecycle,
                apply_session=applies,
            )
            after = (store.working_path.read_bytes(), store.persistent_path.read_bytes())

        self.assertIn("Status: EMPTY", status)
        self.assertIn("apply_engine_installed: true", status)
        self.assertIn("Status: OK", doctor)
        self.assertEqual(before, after)

    def test_learning_lifecycle_apply_refuses_wrong_token_without_mutation(self) -> None:
        with TemporaryDirectory() as temp_dir:
            _, store, events, review, lifecycle, applies = (
                build_test_learning_lifecycle_transition(Path(temp_dir))
            )
            before = store.persistent_path.read_bytes()
            output = format_learning_lifecycle_apply_command(
                f"/experience learning apply lifecycle {review.lesson_memory_id} WRONG-TOKEN",
                events=events,
                memory_store=store,
                lifecycle_session=lifecycle,
                apply_session=applies,
            )
            after = store.persistent_path.read_bytes()

        self.assertIn("confirmation token mismatch", output.lower())
        self.assertEqual(after, before)
        self.assertEqual(applies.snapshot(), ())

    def test_learning_lifecycle_keep_apply_is_byte_stable_run_once_noop(self) -> None:
        with TemporaryDirectory() as temp_dir:
            _, store, events, review, lifecycle, applies = (
                build_test_learning_lifecycle_transition(Path(temp_dir))
            )
            before = store.persistent_path.read_bytes()
            preview = format_learning_lifecycle_apply_command(
                f"/experience learning lifecycle-apply-preview {review.lesson_memory_id}",
                events=events,
                memory_store=store,
                lifecycle_session=lifecycle,
                apply_session=applies,
            )
            token = _id_from_output(preview, "confirmation_token:")
            review_contract = applies.review(
                lifecycle.get(review.lesson_memory_id),
                events=events,
                memory_store=store,
            )
            output = format_learning_lifecycle_apply_command(
                f"/experience learning apply lifecycle {review.lesson_memory_id} {token}",
                events=events,
                memory_store=store,
                lifecycle_session=lifecycle,
                apply_session=applies,
            )
            after_first = store.persistent_path.read_bytes()
            snapshot = json.dumps(applies.snapshot(), sort_keys=True)
            second = format_learning_lifecycle_apply_command(
                f"/experience learning apply lifecycle {review.lesson_memory_id} {token}",
                events=events,
                memory_store=store,
                lifecycle_session=lifecycle,
                apply_session=applies,
            )
            receipt = applies.get(review.lesson_memory_id)
            after_second = store.persistent_path.read_bytes()

        self.assertIn("Status: CONFIRMABLE", preview)
        self.assertEqual(token, learning_lifecycle_apply_confirmation_token(review_contract))
        self.assertIn("keep_verified_noop", output)
        self.assertEqual(before, after_first)
        self.assertEqual(receipt.actual_record_mutations, 0)
        self.assertFalse(receipt.memory_mutation_performed)
        self.assertIn("single lifecycle apply slot", second)
        self.assertEqual(snapshot, json.dumps(applies.snapshot(), sort_keys=True))
        self.assertEqual(after_first, after_second)

    def test_learning_lifecycle_reject_apply_changes_only_old_lifecycle_state(self) -> None:
        with TemporaryDirectory() as temp_dir:
            _, store, events, review, lifecycle, applies = (
                build_test_learning_lifecycle_transition(Path(temp_dir), decision="reject")
            )
            before_record = store.load_persistent_memory()[0]
            before_provenance = deepcopy(before_record.provenance)
            preview = format_learning_lifecycle_apply_command(
                f"/experience learning lifecycle-apply-preview {review.lesson_memory_id}",
                events=events,
                memory_store=store,
                lifecycle_session=lifecycle,
                apply_session=applies,
            )
            token = _id_from_output(preview, "confirmation_token:")
            output = format_learning_lifecycle_apply_command(
                f"/experience learning apply lifecycle {review.lesson_memory_id} {token}",
                events=events,
                memory_store=store,
                lifecycle_session=lifecycle,
                apply_session=applies,
            )
            after_record = store.load_persistent_memory()[0]
            receipt = applies.get(review.lesson_memory_id)
            why = format_memory_command(f"/memory why {review.lesson_memory_id}", store)

        before_payload = before_record.to_dict()
        after_payload = after_record.to_dict()
        changed_fields = {
            key for key in before_payload if before_payload.get(key) != after_payload.get(key)
        }
        self.assertEqual(review.status, "REJECT_CANDIDATE")
        self.assertIn("reject_soft_transition_verified", output)
        self.assertFalse(after_record.active)
        self.assertIsNone(after_record.superseded_by)
        self.assertEqual(after_record.superseded_reason, "verified_learning_outcome_reject")
        self.assertEqual(
            changed_fields,
            {"active", "superseded_at", "superseded_reason"},
        )
        self.assertEqual(after_record.provenance, before_provenance)
        self.assertTrue(verify_memory_provenance(after_record).verified)
        self.assertEqual(receipt.actual_record_mutations, 1)
        self.assertTrue(receipt.memory_mutation_performed)
        self.assertIn("Lifecycle state:", why)
        self.assertIn("verified_learning_outcome_reject", why)

    def test_learning_lifecycle_supersede_apply_preserves_verified_replacement(self) -> None:
        with TemporaryDirectory() as temp_dir:
            _, store, events, review, lifecycle, applies = (
                build_test_learning_lifecycle_transition(Path(temp_dir), decision="supersede")
            )
            before = {record.id: record.to_dict() for record in store.load_persistent_memory()}
            preview = format_learning_lifecycle_apply_command(
                f"/experience learning lifecycle-apply-preview {review.lesson_memory_id}",
                events=events,
                memory_store=store,
                lifecycle_session=lifecycle,
                apply_session=applies,
            )
            token = _id_from_output(preview, "confirmation_token:")
            output = format_learning_lifecycle_apply_command(
                f"/experience learning apply lifecycle {review.lesson_memory_id} {token}",
                events=events,
                memory_store=store,
                lifecycle_session=lifecycle,
                apply_session=applies,
            )
            after_records = {record.id: record for record in store.load_persistent_memory()}
            receipt = applies.get(review.lesson_memory_id)

        old = after_records[review.lesson_memory_id]
        replacement = after_records[review.replacement_memory_id]
        self.assertIn("supersede_soft_transition_verified", output)
        self.assertFalse(old.active)
        self.assertEqual(old.superseded_by, replacement.id)
        self.assertEqual(old.superseded_reason, "verified_learning_outcome_supersede")
        self.assertTrue(replacement.active)
        self.assertEqual(replacement.to_dict(), before[replacement.id])
        self.assertTrue(verify_memory_provenance(old).verified)
        self.assertTrue(verify_memory_provenance(replacement).verified)
        self.assertTrue(receipt.replacement_verified)
        self.assertEqual(len(receipt.replacement_record_hash), 64)

    def test_learning_lifecycle_apply_fails_closed_on_evidence_drift(self) -> None:
        with TemporaryDirectory() as temp_dir:
            _, store, _, review, lifecycle, applies = build_test_learning_lifecycle_transition(
                Path(temp_dir)
            )
            before = store.persistent_path.read_bytes()
            output = format_learning_lifecycle_apply_command(
                f"/experience learning lifecycle-apply-preview {review.lesson_memory_id}",
                events=[],
                memory_store=store,
                lifecycle_session=lifecycle,
                apply_session=applies,
            )
            after = store.persistent_path.read_bytes()

        self.assertIn("Status: NOT READY", output)
        self.assertIn("outcome", output.lower())
        self.assertEqual(after, before)
        self.assertEqual(applies.snapshot(), ())

    def test_learning_lifecycle_apply_rolls_back_exact_bytes_on_verification_failure(self) -> None:
        with TemporaryDirectory() as temp_dir:
            _, store, events, review, lifecycle, applies = (
                build_test_learning_lifecycle_transition(Path(temp_dir), decision="reject")
            )
            preview = format_learning_lifecycle_apply_command(
                f"/experience learning lifecycle-apply-preview {review.lesson_memory_id}",
                events=events,
                memory_store=store,
                lifecycle_session=lifecycle,
                apply_session=applies,
            )
            token = _id_from_output(preview, "confirmation_token:")
            before = store.persistent_path.read_bytes()
            with patch(
                "proto_mind.experience_learning_lifecycle_apply._verify_transition",
                side_effect=ValueError("forced post-write failure"),
            ):
                output = format_learning_lifecycle_apply_command(
                    f"/experience learning apply lifecycle {review.lesson_memory_id} {token}",
                    events=events,
                    memory_store=store,
                    lifecycle_session=lifecycle,
                    apply_session=applies,
                )
            after = store.persistent_path.read_bytes()

        self.assertIn("exact original memory bytes were restored", output)
        self.assertEqual(after, before)
        self.assertEqual(applies.snapshot(), ())

    def test_learning_lifecycle_apply_receipt_and_doctor_detect_tampering(self) -> None:
        with TemporaryDirectory() as temp_dir:
            _, store, events, review, lifecycle, applies = (
                build_test_learning_lifecycle_transition(Path(temp_dir))
            )
            preview = format_learning_lifecycle_apply_command(
                f"/experience learning lifecycle-apply-preview {review.lesson_memory_id}",
                events=events,
                memory_store=store,
                lifecycle_session=lifecycle,
                apply_session=applies,
            )
            token = _id_from_output(preview, "confirmation_token:")
            format_learning_lifecycle_apply_command(
                f"/experience learning apply lifecycle {review.lesson_memory_id} {token}",
                events=events,
                memory_store=store,
                lifecycle_session=lifecycle,
                apply_session=applies,
            )
            receipt = applies.get(review.lesson_memory_id)
            inspected = format_learning_lifecycle_apply_command(
                f"/experience learning lifecycle-apply-receipt {receipt.id}",
                events=events,
                memory_store=store,
                lifecycle_session=lifecycle,
                apply_session=applies,
            )
            healthy = applies.doctor(store)
            applies._receipts[review.lesson_memory_id] = replace(
                receipt,
                actual_record_mutations=9,
            )
            tampered = applies.doctor(store)

        self.assertIn("Status: FOUND", inspected)
        self.assertIn("receipt_hash:", inspected)
        self.assertEqual(healthy.status, "OK")
        self.assertEqual(tampered.status, "ERROR")
        self.assertIn("hash does not match", " ".join(tampered.issues))
        self.assertIn("invalid mutation count", " ".join(tampered.issues))

    def test_learning_lifecycle_apply_reuses_confirmation_required_memory_gate(self) -> None:
        registry = {entry.prefix: entry for entry in COMMAND_REGISTRY}
        apply_spec = registry["/experience learning apply"]

        self.assertEqual(
            LEARNING_LIFECYCLE_APPLY_MODE,
            "single_exact_confirmed_lesson_transition",
        )
        self.assertEqual(LEARNING_LIFECYCLE_APPLY_MAX_RECEIPTS, 1)
        self.assertFalse(apply_spec.read_only)
        self.assertEqual(apply_spec.mutates, "memory")
        self.assertEqual(
            classify_command(
                "/experience learning apply lifecycle mem_lesson CONFIRM-LIFECYCLE-APPLY"
            ).policy_class,
            "confirmation_required",
        )
        self.assertEqual(len(COMMAND_REGISTRY), 387)
        self.assertEqual(command_registry_doctor()["status"], "OK")
        self.assertEqual(action_policy_doctor()["status"], "OK")

    def test_learning_lifecycle_apply_works_through_shared_handler(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            coordinator, store, _, review = build_test_learning_outcome_review(root)
            logger = SessionOperatorLogger(root / "session.jsonl", enabled=False)
            pilot = get_experience_pilot(coordinator, project_root=root)
            pilot.preview()
            pilot.consent(pilot.expected_consent_phrase)
            query = "As we discussed earlier, what did we learn about the active SQLite decision?"
            self.assertTrue(
                pilot.observe_normal_turn(query, coordinator.handle(query)).capture_performed
            )
            decision_preview = process_interactive_input(
                f"/experience learning outcome-confirm-preview {review.lesson_memory_id}",
                coordinator=coordinator,
                session_logger=logger,
                project_root=root,
            )
            decision_token = _id_from_output(decision_preview, "confirmation_token:")
            process_interactive_input(
                f"/experience learning decide outcome keep {review.lesson_memory_id} "
                f"{decision_token}",
                coordinator=coordinator,
                session_logger=logger,
                project_root=root,
            )
            apply_preview = process_interactive_input(
                f"/experience learning lifecycle-apply-preview {review.lesson_memory_id}",
                coordinator=coordinator,
                session_logger=logger,
                project_root=root,
            )
            apply_token = _id_from_output(apply_preview, "confirmation_token:")
            before = store.persistent_path.read_bytes()
            output = process_interactive_input(
                f"/experience learning apply lifecycle {review.lesson_memory_id} {apply_token}",
                coordinator=coordinator,
                session_logger=logger,
                project_root=root,
            )
            after = store.persistent_path.read_bytes()

        self.assertIn("APPLIED AND VERIFIED", output)
        self.assertIn("keep_verified_noop", output)
        self.assertEqual(before, after)
        self.assertEqual(logger.status().entry_count, 0)

    def test_learning_lifecycle_apply_receipt_expires_but_durable_state_survives_restart(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _, store, events, review, lifecycle, applies = (
                build_test_learning_lifecycle_transition(root, decision="reject")
            )
            preview = format_learning_lifecycle_apply_command(
                f"/experience learning lifecycle-apply-preview {review.lesson_memory_id}",
                events=events,
                memory_store=store,
                lifecycle_session=lifecycle,
                apply_session=applies,
            )
            token = _id_from_output(preview, "confirmation_token:")
            format_learning_lifecycle_apply_command(
                f"/experience learning apply lifecycle {review.lesson_memory_id} {token}",
                events=events,
                memory_store=store,
                lifecycle_session=lifecycle,
                apply_session=applies,
            )
            restarted = SupervisedExperiencePilot(root, session_id="lifecycle-apply-restarted")
            durable = store.load_persistent_memory()[0]

        self.assertEqual(len(applies.snapshot()), 1)
        self.assertEqual(restarted.learning_lifecycle_applies.snapshot(), ())
        self.assertFalse(durable.active)
        self.assertEqual(durable.superseded_reason, "verified_learning_outcome_reject")
        self.assertTrue(verify_memory_provenance(durable).verified)

    def test_learning_lifecycle_audit_empty_state_is_read_only(self) -> None:
        with TemporaryDirectory() as temp_dir:
            _, store, _ = build_test_system(Path(temp_dir))
            before = (store.working_path.read_bytes(), store.persistent_path.read_bytes())
            status = format_learning_lifecycle_audit_command(
                "/experience learning lifecycle-audit-status",
                memory_store=store,
            )
            history = format_learning_lifecycle_audit_command(
                "/experience learning lifecycle-history",
                memory_store=store,
            )
            doctor = format_learning_lifecycle_audit_command(
                "/experience learning lifecycle-audit-doctor",
                memory_store=store,
            )
            after = (store.working_path.read_bytes(), store.persistent_path.read_bytes())

        self.assertIn("Status: OK", status)
        self.assertIn("learned_lessons: 0", status)
        self.assertIn("showing: 0/0", history)
        self.assertIn("Status: OK", doctor)
        self.assertEqual(before, after)

    def test_learning_lifecycle_history_distinguishes_active_from_terminal(self) -> None:
        with TemporaryDirectory() as temp_dir:
            _, store, _, review = build_test_learning_outcome_review(Path(temp_dir))
            before = store.persistent_path.read_bytes()
            terminal_only = format_learning_lifecycle_audit_command(
                "/experience learning lifecycle-history",
                memory_store=store,
            )
            all_records = format_learning_lifecycle_audit_command(
                "/experience learning lifecycle-history --all",
                memory_store=store,
            )
            after = store.persistent_path.read_bytes()

        self.assertIn("showing: 0/1", terminal_only)
        self.assertNotIn(review.lesson_memory_id, terminal_only)
        self.assertIn("showing: 1/1", all_records)
        self.assertIn(f"{review.lesson_memory_id} | active", all_records)
        self.assertIn("not an append-only event history", all_records)
        self.assertEqual(before, after)

    def test_learning_lifecycle_audit_reconstructs_reject_after_restart(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _, store, events, review, lifecycle, applies = (
                build_test_learning_lifecycle_transition(root, decision="reject")
            )
            apply_test_learning_lifecycle_transition(
                store, events, review, lifecycle, applies
            )
            restarted = LearningLifecycleTransitionAudit(
                MemoryStore(store.working_path, store.persistent_path)
            )
            report = restarted.inspect()
            entry = restarted.get(review.lesson_memory_id)
            inspected = format_learning_lifecycle_audit_command(
                f"/experience learning lifecycle-inspect {review.lesson_memory_id}",
                memory_store=store,
            )

        self.assertEqual(report.status, "OK")
        self.assertEqual(report.rejected_count, 1)
        self.assertEqual(entry.state, "rejected")
        self.assertTrue(entry.restart_safe)
        self.assertEqual(entry.provenance_status, "VERIFIED")
        self.assertIn("lifecycle_reason: verified_learning_outcome_reject", inspected)

    def test_learning_lifecycle_audit_reconstructs_supersede_link(self) -> None:
        with TemporaryDirectory() as temp_dir:
            _, store, events, review, lifecycle, applies = (
                build_test_learning_lifecycle_transition(Path(temp_dir), decision="supersede")
            )
            apply_test_learning_lifecycle_transition(
                store, events, review, lifecycle, applies
            )
            report = LearningLifecycleTransitionAudit(store).inspect()
            entry = next(
                item for item in report.entries if item.memory_id == review.lesson_memory_id
            )
            history = format_learning_lifecycle_audit_command(
                "/experience learning lifecycle-history",
                memory_store=store,
            )

        self.assertEqual(report.status, "OK")
        self.assertEqual(report.superseded_count, 1)
        self.assertEqual(entry.state, "superseded")
        self.assertEqual(entry.replacement_memory_id, review.replacement_memory_id)
        self.assertEqual(entry.replacement_status, "active_verified")
        self.assertTrue(entry.restart_safe)
        self.assertIn(review.replacement_memory_id, history)

    def test_learning_lifecycle_audit_classifies_operator_forget_separately(self) -> None:
        with TemporaryDirectory() as temp_dir:
            _, store, _, review = build_test_learning_outcome_review(Path(temp_dir))
            forgotten = format_memory_command(
                f"/memory forget {review.lesson_memory_id}",
                store,
            )
            report = LearningLifecycleTransitionAudit(store).inspect()
            entry = report.entries[0]

        self.assertIn("Forgotten:", forgotten)
        self.assertEqual(report.status, "OK")
        self.assertEqual(report.forgotten_count, 1)
        self.assertEqual(entry.state, "forgotten")
        self.assertNotEqual(entry.lifecycle_reason, "verified_learning_outcome_reject")

    def test_learning_lifecycle_audit_detects_dangling_replacement(self) -> None:
        with TemporaryDirectory() as temp_dir:
            _, store, events, review, lifecycle, applies = (
                build_test_learning_lifecycle_transition(Path(temp_dir), decision="supersede")
            )
            apply_test_learning_lifecycle_transition(
                store, events, review, lifecycle, applies
            )
            old = next(
                record
                for record in store.load_persistent_memory()
                if record.id == review.lesson_memory_id
            )
            store.save_persistent_memory([old])
            report = LearningLifecycleTransitionAudit(store).inspect()

        self.assertEqual(report.status, "ERROR")
        self.assertEqual(report.invalid_count, 1)
        self.assertIn("replacement is missing", " ".join(report.issues))

    def test_learning_lifecycle_audit_detects_tampered_provenance(self) -> None:
        with TemporaryDirectory() as temp_dir:
            _, store, _, _ = build_test_learning_outcome_review(Path(temp_dir))
            record = store.load_persistent_memory()[0]
            record.provenance["candidate_id"] = "tampered_candidate"
            store.save_persistent_memory([record])
            report = LearningLifecycleTransitionAudit(store).inspect()

        self.assertEqual(report.status, "ERROR")
        self.assertEqual(report.invalid_count, 1)
        self.assertIn("provenance does not verify", " ".join(report.issues))

    def test_learning_lifecycle_audit_detects_reference_cycle(self) -> None:
        with TemporaryDirectory() as temp_dir:
            _, store, events, review, lifecycle, applies = (
                build_test_learning_lifecycle_transition(Path(temp_dir), decision="supersede")
            )
            apply_test_learning_lifecycle_transition(
                store, events, review, lifecycle, applies
            )
            records = store.load_persistent_memory()
            old = next(record for record in records if record.id == review.lesson_memory_id)
            replacement = next(
                record for record in records if record.id == review.replacement_memory_id
            )
            replacement.active = False
            replacement.superseded_by = old.id
            replacement.superseded_at = (datetime.now(UTC) + timedelta(seconds=5)).isoformat()
            replacement.superseded_reason = "verified_learning_outcome_supersede"
            store.save_persistent_memory([old, replacement])
            report = LearningLifecycleTransitionAudit(store).inspect()

        self.assertEqual(report.status, "ERROR")
        self.assertIn("cycle detected", " ".join(report.issues))

    def test_learning_lifecycle_audit_marks_unclassified_inactive_lesson_warn(self) -> None:
        with TemporaryDirectory() as temp_dir:
            _, store, _, _ = build_test_learning_outcome_review(Path(temp_dir))
            record = store.load_persistent_memory()[0]
            record.active = False
            store.save_persistent_memory([record])
            report = LearningLifecycleTransitionAudit(store).inspect()

        self.assertEqual(report.status, "WARN")
        self.assertEqual(report.unclassified_count, 1)
        self.assertIn("no classified lifecycle reason", " ".join(report.warnings))

    def test_learning_lifecycle_audit_detects_invalid_transition_timestamp(self) -> None:
        with TemporaryDirectory() as temp_dir:
            _, store, events, review, lifecycle, applies = (
                build_test_learning_lifecycle_transition(Path(temp_dir), decision="reject")
            )
            apply_test_learning_lifecycle_transition(
                store, events, review, lifecycle, applies
            )
            record = store.load_persistent_memory()[0]
            record.superseded_at = "not-a-timestamp"
            store.save_persistent_memory([record])
            report = LearningLifecycleTransitionAudit(store).inspect()

        self.assertEqual(report.status, "ERROR")
        self.assertEqual(report.invalid_count, 1)
        self.assertIn("timestamp is invalid", " ".join(report.issues))

    def test_learning_lifecycle_audit_shared_handler_is_read_only_and_registered(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            coordinator, store, _, _ = build_test_learning_outcome_review(root)
            logger = SessionOperatorLogger(root / "session.jsonl", enabled=False)
            before = (store.working_path.read_bytes(), store.persistent_path.read_bytes())
            output = process_interactive_input(
                "/experience learning lifecycle-audit-doctor",
                coordinator=coordinator,
                session_logger=logger,
                project_root=root,
            )
            after = (store.working_path.read_bytes(), store.persistent_path.read_bytes())
            family = next(
                spec for spec in COMMAND_REGISTRY if spec.prefix == "/experience learning"
            )

        self.assertIn("Learning Lifecycle Audit Doctor v1", output)
        self.assertIn("Status: OK", output)
        self.assertEqual(before, after)
        self.assertEqual(logger.status().entry_count, 0)
        self.assertEqual(
            LEARNING_LIFECYCLE_AUDIT_MODE,
            "read_only_durable_lesson_state_reconstruction",
        )
        self.assertTrue(family.read_only)
        self.assertEqual(family.mutates, "none")
        self.assertEqual(
            classify_command(
                "/experience learning lifecycle-audit-doctor"
            ).policy_class,
            "auto_allowed",
        )
        self.assertEqual(len(COMMAND_REGISTRY), 387)
        self.assertEqual(command_registry_doctor()["status"], "OK")
        self.assertEqual(action_policy_doctor()["status"], "OK")
