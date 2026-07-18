from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

from proto_mind.coordinator import Coordinator
from proto_mind.experience_ledger import (
    ExperienceTraceBuilder,
    TemporaryExperienceLedgerStore,
    inspect_experience_events,
)
from proto_mind.memory_keeper import MemoryKeeper
from proto_mind.memory_store import MemoryStore
from proto_mind.models import MemoryRecord, ObserverState
from proto_mind.observer import Observer
from proto_mind.reasoners.base import BaseReasoner
from proto_mind.reasoners.mock_reasoner import MockReasoner


CONTRADICTION_TURN = "Проверь текущее решение о хранилище памяти."
CORRECTION_TURN = "Повтори текущее решение о хранилище памяти."


@dataclass(frozen=True)
class ContinuitySoakTurn:
    user_input: str
    expects_store_write: bool = False


TURNS = (
    ContinuitySoakTurn("Я предпочитаю короткие ответы.", True),
    ContinuitySoakTurn("Мы решили использовать JSON для памяти Proto-Mind.", True),
    ContinuitySoakTurn("Что я предпочитаю в стиле ответа?"),
    ContinuitySoakTurn("What preferences and decisions do you currently remember?"),
    ContinuitySoakTurn("Как мы обсуждали раньше, что мы решили по памяти Proto-Mind?"),
    ContinuitySoakTurn("Объясни модуль observer."),
    ContinuitySoakTurn("What do you remember about our memory decision?"),
    ContinuitySoakTurn(
        "На самом деле теперь используем SQLite вместо JSON для памяти Proto-Mind.",
        True,
    ),
    ContinuitySoakTurn("Какое решение о хранилище памяти сейчас активно?"),
    ContinuitySoakTurn("Что мы использовали раньше, до SQLite?"),
    ContinuitySoakTurn(CONTRADICTION_TURN),
    ContinuitySoakTurn(CORRECTION_TURN),
    ContinuitySoakTurn("Как мы продолжим работу после исправления?"),
    ContinuitySoakTurn("Запомни, что текущая цель Proto-Mind — Cognitive Continuity.", True),
    ContinuitySoakTurn("Что ты помнишь о текущей цели проекта Proto-Mind?"),
    ContinuitySoakTurn("Что я предпочитаю в стиле ответа?"),
    ContinuitySoakTurn("What storage decision is current?"),
    ContinuitySoakTurn("Что использовали до SQLite?"),
    ContinuitySoakTurn("Продолжим работу над проектом Proto-Mind."),
    ContinuitySoakTurn("Explain the coordinator briefly."),
    ContinuitySoakTurn("Что я предпочитаю в стиле ответа?"),
    ContinuitySoakTurn("What preferences and decisions do you currently remember?"),
    ContinuitySoakTurn("Как мы обсуждали раньше, что важно для проекта Proto-Mind?"),
    ContinuitySoakTurn("What did we use before SQLite?"),
    ContinuitySoakTurn("Продолжим с текущей целью Proto-Mind."),
)


class _ContinuitySoakReasoner(BaseReasoner):
    backend_name = "continuity-soak"

    def __init__(self) -> None:
        self.fallback = MockReasoner()
        self.seen_correction_hints: list[list[str]] = []

    def respond(
        self,
        user_input: str,
        retrieved_memory: list[MemoryRecord],
        observer_state: ObserverState,
        correction_hints: list[str] | None = None,
    ) -> str:
        self.seen_correction_hints.append(list(correction_hints or []))
        if user_input == CONTRADICTION_TURN:
            return "Текущее архитектурное решение — JSON для хранения памяти."
        if user_input == CORRECTION_TURN:
            return "Текущее архитектурное решение — SQLite для хранения памяти."
        return self.fallback.respond(
            user_input,
            retrieved_memory,
            observer_state,
            correction_hints,
        )


def run_continuity_soak(*, persist_experience_preview: bool = False) -> dict[str, object]:
    with TemporaryDirectory(prefix="proto-mind-continuity-soak-") as temp_dir:
        data_dir = Path(temp_dir) / "data"
        store = MemoryStore(
            working_path=data_dir / "working_memory.json",
            persistent_path=data_dir / "persistent_memory.json",
        )
        reasoner = _ContinuitySoakReasoner()
        coordinator = Coordinator(
            observer=Observer(),
            memory_keeper=MemoryKeeper(store),
            reasoner=reasoner,
        )

        results = []
        experience_events = []
        experience_builder = ExperienceTraceBuilder(session_id="continuity-soak")
        read_only_turns = 0
        unexpected_writes: list[int] = []
        storage_mismatches: list[int] = []
        for turn_number, turn in enumerate(TURNS, start=1):
            before = (store.working_path.read_bytes(), store.persistent_path.read_bytes())
            result = coordinator.handle(turn.user_input)
            experience_events.extend(
                experience_builder.build_turn_events(
                    turn.user_input,
                    result,
                    turn_id=turn_number,
                    trace_id=f"soak-{turn_number:02d}",
                    created_at=f"2026-01-01T00:00:{turn_number:02d}Z",
                )
            )
            after = (store.working_path.read_bytes(), store.persistent_path.read_bytes())
            results.append(result)
            if result.memory_summary.should_store is not turn.expects_store_write:
                storage_mismatches.append(turn_number)
            if not turn.expects_store_write:
                if before == after:
                    read_only_turns += 1
                else:
                    unexpected_writes.append(turn_number)

        working = store.load_working_memory()
        persistent = store.load_persistent_memory()
        all_memory = working + persistent
        normalized_contents = {" ".join(record.content.lower().split()) for record in all_memory}
        known_ids = {record.id for record in all_memory}
        dangling_superseded_refs = [
            record.id
            for record in all_memory
            if record.superseded_by and record.superseded_by not in known_ids
        ]

        contradiction = results[10]
        correction = results[11]
        post_correction = results[12]
        goal_recall = results[14]
        continuity_recall = results[22]
        historical_recall = results[23]
        expected_read_only_turns = sum(not turn.expects_store_write for turn in TURNS)
        experience_doctor = inspect_experience_events(experience_events)
        experience_store_doctor = None
        if persist_experience_preview:
            experience_store = TemporaryExperienceLedgerStore(
                data_dir / "experience_ledger_preview.jsonl"
            )
            experience_store.append_events(
                experience_events,
                stored_at="2026-01-01T01:00:00Z",
            )
            experience_store_doctor = experience_store.doctor()
        expected_experience_events = (
            len(TURNS) * 7
            + sum(bool(result.memory_summary.stored_record_id) for result in results)
            + sum(bool(result.previous_correction_hints) for result in results)
        )

        checks = {
            "turn_count_25": len(results) == 25,
            "storage_contract": not storage_mismatches,
            "read_only_turns_byte_stable": (
                read_only_turns == expected_read_only_turns and not unexpected_writes
            ),
            "bounded_memory_records": len(working) == 4 and len(persistent) == 3,
            "bounded_unique_content": len(normalized_contents) == 4,
            "retrieval_usage_not_implicit": all(record.usage_count == 0 for record in all_memory),
            "compact_user_input_only": all(
                "system response:" not in record.content.lower()
                and "current request:" not in record.content.lower()
                and len(record.content) <= 160
                for record in all_memory
            ),
            "json_decision_superseded": bool(
                [record for record in all_memory if "использовать json" in record.content.lower()]
            )
            and all(
                not record.active
                for record in all_memory
                if "использовать json" in record.content.lower()
            ),
            "sqlite_decision_active": bool(
                [record for record in all_memory if "теперь используем sqlite" in record.content.lower()]
            )
            and all(
                record.active
                for record in all_memory
                if "теперь используем sqlite" in record.content.lower()
            ),
            "superseded_references_resolve": not dangling_superseded_refs,
            "historical_recall_selects_old_decision": any(
                record.type == "decision" and not record.active and "json" in record.content.lower()
                for record in historical_recall.retrieved_memory
            ),
            "continuity_recall_prefers_active_context": bool(continuity_recall.retrieved_memory)
            and continuity_recall.retrieved_memory[0].type == "insight"
            and all(record.active for record in continuity_recall.retrieved_memory),
            "goal_recalled": "Cognitive Continuity" in goal_recall.response,
            "contradiction_detected": contradiction.grounding_audit is not None
            and contradiction.grounding_audit.grounding_status == "contradicted"
            and bool(contradiction.self_reflection and contradiction.self_reflection.correction_hints),
            "correction_hint_carried_once": bool(contradiction.self_reflection)
            and correction.previous_correction_hints == contradiction.self_reflection.correction_hints
            and correction.grounding_audit is not None
            and correction.grounding_audit.grounding_status == "grounded"
            and not post_correction.previous_correction_hints,
            "correction_hints_not_persisted": all(
                "use the active decision as current state" not in record.content.lower()
                for record in all_memory
            ),
            "generic_architecture_turn_not_forced_grounding": results[5].grounding_audit is not None
            and results[5].grounding_audit.grounding_status == "not_needed",
            "experience_event_count_bounded": len(experience_events) == expected_experience_events,
            "experience_event_provenance_valid": experience_doctor.status == "OK",
            "experience_events_preview_only": all(
                "full_response" not in event.payload
                and "user_input" not in event.payload
                and "system_prompt" not in event.payload
                and "injected_prompt" not in event.payload
                for event in experience_events
            ),
            "experience_live_store_absent": not (data_dir / "experience_ledger.jsonl").exists(),
            "experience_temporary_store_hash_chain": (
                not persist_experience_preview
                or (
                    experience_store_doctor is not None
                    and experience_store_doctor.status == "OK"
                    and experience_store_doctor.event_count == len(experience_events)
                    and experience_store_doctor.hash_verified_count == len(experience_events)
                )
            ),
        }
        failed_checks = [name for name, passed in checks.items() if not passed]
        return {
            "status": "OK" if not failed_checks else "FAIL",
            "turn_count": len(results),
            "english_turns": sum(turn.user_input.isascii() for turn in TURNS),
            "russian_or_mixed_turns": sum(not turn.user_input.isascii() for turn in TURNS),
            "expected_store_turns": len(TURNS) - expected_read_only_turns,
            "read_only_turns": expected_read_only_turns,
            "byte_stable_read_only_turns": read_only_turns,
            "working_records": len(working),
            "persistent_records": len(persistent),
            "unique_memory_contents": len(normalized_contents),
            "experience_events": len(experience_events),
            "experience_provenance_edges": experience_doctor.provenance_edge_count,
            "experience_doctor_status": experience_doctor.status,
            "experience_persistence_preview": persist_experience_preview,
            "experience_store_doctor_status": (
                experience_store_doctor.status if experience_store_doctor else "NOT_RUN"
            ),
            "experience_store_hash_verified": (
                experience_store_doctor.hash_verified_count if experience_store_doctor else 0
            ),
            "checks": checks,
            "failed_checks": failed_checks,
            "unexpected_write_turns": unexpected_writes,
            "storage_mismatch_turns": storage_mismatches,
            "dangling_superseded_refs": dangling_superseded_refs,
            "boundary": (
                (
                    "Temporary local store only, with an isolated atomic Experience Ledger preview; "
                    if persist_experience_preview
                    else "Temporary local store only, with in-memory Experience Ledger preview; "
                )
                + "no LLM/API, live store, export, session log, context injection, operator command, "
                "or external action."
            ),
        }


def format_continuity_soak_report(report: dict[str, object] | None = None) -> str:
    report = report or run_continuity_soak()
    lines = [
        "Proto-Mind Cognitive Continuity Soak",
        f"Status: {report['status']}",
        f"turns: {report['turn_count']}",
        f"languages: English={report['english_turns']}; Russian/mixed={report['russian_or_mixed_turns']}",
        (
            "store contract: "
            f"explicit_writes={report['expected_store_turns']}; "
            f"byte_stable_read_only={report['byte_stable_read_only_turns']}/{report['read_only_turns']}"
        ),
        (
            "memory bounds: "
            f"working={report['working_records']}; persistent={report['persistent_records']}; "
            f"unique_content={report['unique_memory_contents']}"
        ),
        (
            "experience preview: "
            f"events={report['experience_events']}; "
            f"provenance_edges={report['experience_provenance_edges']}; "
            f"doctor={report['experience_doctor_status']}"
        ),
        (
            "temporary persistence: "
            f"enabled={str(report['experience_persistence_preview']).lower()}; "
            f"doctor={report['experience_store_doctor_status']}; "
            f"hash_verified={report['experience_store_hash_verified']}"
        ),
        "",
        "Checks:",
    ]
    for name, passed in report["checks"].items():
        lines.append(f"- [{'PASS' if passed else 'FAIL'}] {name}")
    lines.extend(["", "Boundary:", f"- {report['boundary']}"])
    return "\n".join(lines)


def main() -> int:
    report = run_continuity_soak()
    print(format_continuity_soak_report(report))
    return 0 if report["status"] == "OK" else 1


if __name__ == "__main__":
    raise SystemExit(main())
