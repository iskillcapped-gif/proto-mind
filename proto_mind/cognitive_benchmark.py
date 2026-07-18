from __future__ import annotations

from dataclasses import dataclass

from proto_mind.grounding_auditor import GroundingAuditor
from proto_mind.models import InteractionSummary, MemoryRecord
from proto_mind.observer import Observer
from proto_mind.self_reflection import SelfReflector


@dataclass(frozen=True)
class CognitiveBenchmarkCase:
    case_id: str
    language: str
    text: str
    expected_query_type: str
    expected_needs_memory: bool
    required_tags: tuple[str, ...] = ()


@dataclass(frozen=True)
class CognitiveResponseBenchmarkCase:
    case_id: str
    language: str
    user_input: str
    response: str
    memory_scenario: str
    expected_grounding_status: str
    expected_active_decision_status: str | None = None
    expected_superseded_memory_status: str | None = None
    expected_reflection_decision_alignment: str | None = None
    expected_reflection_preference_alignment: str | None = None
    expected_reflection_superseded_risk: str | None = None
    expected_unsupported_claims_risk: str | None = None


CASES = (
    CognitiveBenchmarkCase(
        "en_continuity",
        "en",
        "As we discussed earlier, what did we decide about Proto-Mind memory?",
        "continuity_followup",
        True,
        ("memory", "proto-mind"),
    ),
    CognitiveBenchmarkCase(
        "ru_continuity",
        "ru",
        "Как мы обсуждали раньше, что мы решили по памяти Proto-Mind?",
        "continuity_followup",
        True,
        ("continuity", "memory", "decision", "proto-mind"),
    ),
    CognitiveBenchmarkCase(
        "en_memory_inventory",
        "en",
        "What preferences and decisions do you currently remember?",
        "memory_inventory",
        True,
        ("preference", "decision", "current"),
    ),
    CognitiveBenchmarkCase(
        "ru_memory_inventory",
        "ru",
        "Что ты сейчас помнишь о моих предпочтениях и наших решениях?",
        "memory_inventory",
        True,
        ("memory", "preference", "decision", "current"),
    ),
    CognitiveBenchmarkCase(
        "en_preference",
        "en",
        "I prefer short answers.",
        "personal_context",
        False,
        ("preference", "short", "response_style"),
    ),
    CognitiveBenchmarkCase(
        "ru_preference",
        "ru",
        "Я предпочитаю короткие ответы.",
        "personal_context",
        False,
        ("preference", "short", "response_style"),
    ),
    CognitiveBenchmarkCase(
        "en_decision_override",
        "en",
        "Actually, we now use SQLite instead of JSON for memory storage.",
        "decision_request",
        False,
        ("decision", "change", "sqlite", "json", "storage"),
    ),
    CognitiveBenchmarkCase(
        "ru_decision_override",
        "ru",
        "На самом деле теперь используем SQLite вместо JSON для хранения памяти.",
        "decision_request",
        False,
        ("decision", "change", "sqlite", "json", "storage", "memory"),
    ),
    CognitiveBenchmarkCase(
        "ru_preference_recall",
        "ru",
        "Что я предпочитаю в стиле ответа?",
        "memory_inventory",
        True,
        ("preference", "style", "response_style"),
    ),
    CognitiveBenchmarkCase(
        "ru_project_continuation",
        "ru",
        "Продолжим работу над проектом Proto-Mind.",
        "continuity_followup",
        True,
        ("continuity", "project", "proto-mind"),
    ),
)


RESPONSE_CASES = (
    CognitiveResponseBenchmarkCase(
        "en_grounded_current_decision",
        "en",
        "What storage system are we using now?",
        "The current architectural decision is SQLite for memory storage.",
        "active_sqlite",
        "grounded",
        expected_active_decision_status="aligned",
        expected_reflection_decision_alignment="ok",
    ),
    CognitiveResponseBenchmarkCase(
        "ru_grounded_current_decision",
        "ru",
        "Какую систему хранения памяти мы используем сейчас?",
        "Текущее архитектурное решение — SQLite для хранения памяти.",
        "active_sqlite",
        "grounded",
        expected_active_decision_status="aligned",
        expected_reflection_decision_alignment="ok",
    ),
    CognitiveResponseBenchmarkCase(
        "en_current_decision_contradiction",
        "en",
        "What storage system are we using now?",
        "The current architectural decision is JSON for memory storage.",
        "active_sqlite",
        "contradicted",
        expected_active_decision_status="contradicted",
        expected_reflection_decision_alignment="warning",
    ),
    CognitiveResponseBenchmarkCase(
        "ru_current_decision_contradiction",
        "ru",
        "Какую систему хранения памяти мы используем сейчас?",
        "Текущее архитектурное решение — JSON для хранения памяти.",
        "active_sqlite",
        "contradicted",
        expected_active_decision_status="contradicted",
        expected_reflection_decision_alignment="warning",
    ),
    CognitiveResponseBenchmarkCase(
        "en_historical_decision",
        "en",
        "What did we use before SQLite?",
        "Previously, the old decision was JSON; the current direction is SQLite.",
        "sqlite_with_old_json",
        "grounded",
        expected_active_decision_status="aligned",
        expected_superseded_memory_status="historical_only",
        expected_reflection_superseded_risk="low",
    ),
    CognitiveResponseBenchmarkCase(
        "ru_historical_decision",
        "ru",
        "Что мы использовали раньше, до SQLite?",
        "Раньше решением был JSON, а сейчас используем SQLite.",
        "sqlite_with_old_json",
        "grounded",
        expected_active_decision_status="aligned",
        expected_superseded_memory_status="historical_only",
        expected_reflection_superseded_risk="low",
    ),
    CognitiveResponseBenchmarkCase(
        "en_unsupported_memory_claim",
        "en",
        "What did we decide about memory storage?",
        "I remember we decided to use JSON for memory storage.",
        "empty",
        "ungrounded",
        expected_unsupported_claims_risk="high",
    ),
    CognitiveResponseBenchmarkCase(
        "ru_unsupported_memory_claim",
        "ru",
        "Что мы решили по хранению памяти?",
        "Я помню, что мы решили использовать JSON для хранения памяти.",
        "empty",
        "ungrounded",
        expected_unsupported_claims_risk="high",
    ),
    CognitiveResponseBenchmarkCase(
        "en_concise_preference_warning",
        "en",
        "How should you answer me?",
        "I will use short answers. " + "detail " * 145,
        "concise_preference_en",
        "grounded",
        expected_reflection_preference_alignment="warning",
    ),
    CognitiveResponseBenchmarkCase(
        "ru_concise_preference_warning",
        "ru",
        "Как тебе отвечать мне?",
        "Я буду давать короткие ответы. " + "подробность " * 145,
        "concise_preference_ru",
        "grounded",
        expected_reflection_preference_alignment="warning",
    ),
)


def _memory_scenario(name: str) -> tuple[list[MemoryRecord], list[MemoryRecord]]:
    active_sqlite = MemoryRecord(
        "Теперь используем SQLite вместо JSON для хранения памяти.",
        "decision",
        0.95,
        "benchmark",
        tags=["sqlite", "json", "storage", "memory"],
        id="benchmark-active-sqlite",
    )
    old_json = MemoryRecord(
        "Раньше мы решили использовать JSON для хранения памяти.",
        "decision",
        0.8,
        "benchmark",
        tags=["json", "storage", "memory"],
        id="benchmark-old-json",
        active=False,
        superseded_by=active_sqlite.id,
    )
    if name == "active_sqlite":
        return [active_sqlite], [active_sqlite]
    if name == "sqlite_with_old_json":
        return [old_json, active_sqlite], [old_json, active_sqlite]
    if name == "concise_preference_en":
        preference = MemoryRecord(
            "I prefer short answers.",
            "preference",
            0.9,
            "benchmark",
            tags=["preference", "short", "response_style"],
            id="benchmark-preference-en",
        )
        return [preference], [preference]
    if name == "concise_preference_ru":
        preference = MemoryRecord(
            "Я предпочитаю короткие ответы.",
            "preference",
            0.9,
            "benchmark",
            tags=["preference", "short", "response_style"],
            id="benchmark-preference-ru",
        )
        return [preference], [preference]
    return [], []


def _run_response_case(case: CognitiveResponseBenchmarkCase, observer: Observer) -> dict[str, object]:
    all_memory, selected_memory = _memory_scenario(case.memory_scenario)
    state = observer.analyze(case.user_input)
    audit = GroundingAuditor().audit(
        user_input=case.user_input,
        response=case.response,
        observer_state=state,
        retrieved_memory=selected_memory,
        retrieval_trace=None,
        working_memory=[],
        persistent_memory=all_memory,
    )
    reflection = SelfReflector().reflect(
        user_input=case.user_input,
        response=case.response,
        observer_state=state,
        retrieved_memory=selected_memory,
        retrieval_trace=None,
        memory_summary=InteractionSummary(
            memory_type="insight",
            content="",
            importance=0.0,
            tags=[],
            should_store=False,
        ),
        working_memory=[],
        persistent_memory=all_memory,
    )
    checks = {
        "grounding_status": (audit.grounding_status, case.expected_grounding_status),
        "active_decision_status": (audit.active_decision_status, case.expected_active_decision_status),
        "superseded_memory_status": (audit.superseded_memory_status, case.expected_superseded_memory_status),
        "reflection_decision_alignment": (
            reflection.active_decision_alignment,
            case.expected_reflection_decision_alignment,
        ),
        "reflection_preference_alignment": (
            reflection.preference_alignment,
            case.expected_reflection_preference_alignment,
        ),
        "reflection_superseded_risk": (
            reflection.superseded_memory_risk,
            case.expected_reflection_superseded_risk,
        ),
        "unsupported_claims_risk": (
            reflection.unsupported_claims_risk,
            case.expected_unsupported_claims_risk,
        ),
    }
    mismatches = {
        name: {"actual": actual, "expected": expected}
        for name, (actual, expected) in checks.items()
        if expected is not None and actual != expected
    }
    return {
        "case_id": case.case_id,
        "language": case.language,
        "layer": "response",
        "passed": not mismatches,
        "grounding_status": audit.grounding_status,
        "active_decision_status": audit.active_decision_status,
        "superseded_memory_status": audit.superseded_memory_status,
        "reflection_decision_alignment": reflection.active_decision_alignment,
        "reflection_preference_alignment": reflection.preference_alignment,
        "unsupported_claims_risk": reflection.unsupported_claims_risk,
        "mismatches": mismatches,
    }


def run_benchmark(observer: Observer | None = None) -> dict[str, object]:
    active_observer = observer or Observer()
    results: list[dict[str, object]] = []
    for case in CASES:
        state = active_observer.analyze(case.text)
        missing_tags = sorted(set(case.required_tags) - set(state.topic_tags))
        passed = (
            state.query_type == case.expected_query_type
            and state.needs_memory is case.expected_needs_memory
            and not missing_tags
        )
        results.append(
            {
                "case_id": case.case_id,
                "language": case.language,
                "layer": "observer",
                "passed": passed,
                "query_type": state.query_type,
                "needs_memory": state.needs_memory,
                "topic_tags": list(state.topic_tags),
                "missing_tags": missing_tags,
            }
        )
    results.extend(_run_response_case(case, active_observer) for case in RESPONSE_CASES)
    passed_count = sum(1 for result in results if result["passed"])
    return {
        "status": "OK" if passed_count == len(results) else "FAIL",
        "case_count": len(results),
        "passed_count": passed_count,
        "failed_count": len(results) - passed_count,
        "results": results,
    }


def format_benchmark_report() -> str:
    report = run_benchmark()
    lines = [
        "Proto-Mind Bilingual Cognitive Benchmark",
        f"Status: {report['status']}",
        f"cases: {report['case_count']}",
        f"passed: {report['passed_count']}",
        f"failed: {report['failed_count']}",
        "mode: deterministic local observer/topic and response grounding/reflection checks",
        "",
        "Results:",
    ]
    for result in report["results"]:
        outcome = "PASS" if result["passed"] else "FAIL"
        if result["layer"] == "observer":
            lines.append(
                f"- [{outcome}] {result['case_id']} ({result['language']}, observer): "
                f"type={result['query_type']} needs_memory={str(result['needs_memory']).lower()} "
                f"tags={','.join(result['topic_tags']) or 'none'}"
            )
            if result["missing_tags"]:
                lines.append(f"  missing_tags: {','.join(result['missing_tags'])}")
        else:
            lines.append(
                f"- [{outcome}] {result['case_id']} ({result['language']}, response): "
                f"grounding={result['grounding_status']} "
                f"decision={result['active_decision_status']} "
                f"preference={result['reflection_preference_alignment']}"
            )
            if result["mismatches"]:
                lines.append(f"  mismatches: {result['mismatches']}")
    lines.extend(
        [
            "",
            "Boundary:",
            "- No LLM/API call, store read/write, session log, context injection, or command execution.",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    report = run_benchmark()
    print(format_benchmark_report())
    return 0 if report["status"] == "OK" else 1


if __name__ == "__main__":
    raise SystemExit(main())
