from __future__ import annotations

import re

from proto_mind.topic_utils import extract_topic_tags, topic_weight


HISTORICAL_MARKERS = (
    "previously",
    "previous decisions",
    "before",
    "used to",
    "historical",
    "historically",
    "superseded",
    "old decision",
    "earlier",
    "former",
    "раньше",
    "ранее",
    "до этого",
    "прежде",
    "историческ",
    "предыдущ",
    "старое решение",
    "устаревш",
)

CURRENT_STATE_MARKERS = (
    "currently using",
    "current storage",
    "current system",
    "current architectural decision",
    "current decision",
    "we use",
    "we are using",
    "should use",
    "active decision",
    "сейчас используем",
    "теперь используем",
    "текущее хранилище",
    "текущая система",
    "текущее архитектурное решение",
    "текущее решение",
    "используем",
    "мы используем",
    "следует использовать",
    "активное решение",
)

CURRENT_DECISION_MARKERS = (
    "current architectural decision",
    "current decision",
    "active decision",
    "current direction",
    "we decided",
    "we should use",
    "текущее архитектурное решение",
    "текущая архитектурная цель",
    "текущее решение",
    "активное решение",
    "текущее направление",
    "мы решили",
    "нам следует использовать",
    "сейчас используем",
    "теперь используем",
)

CURRENT_IMPLEMENTATION_MARKERS = (
    "current implementation",
    "implemented storage",
    "currently implemented",
    "implementation is",
    "code currently",
    "текущая реализация",
    "реализованное хранилище",
    "сейчас реализовано",
    "в коде сейчас",
)

MEMORY_CLAIM_MARKERS = (
    "i remember",
    "we decided",
    "we chose",
    "the project currently",
    "your preference is",
    "active decision",
    "stored memory says",
    "current stored memory",
    "current decision",
    "current architectural decision",
    "preferences:",
    "previous decisions",
    "я помню",
    "мы решили",
    "мы выбрали",
    "в проекте сейчас",
    "ваше предпочтение",
    "твоё предпочтение",
    "твое предпочтение",
    "активное решение",
    "в памяти записано",
    "текущая память",
    "текущее решение",
    "текущее архитектурное решение",
    "предпочтения:",
    "предыдущие решения",
)

_GENERIC_SIGNAL_STOPWORDS = {
    "should",
    "current",
    "memory",
    "proto-mind",
    "который",
    "текущий",
    "текущая",
    "текущее",
    "сейчас",
    "память",
    "проект",
}


def split_clauses(text: str) -> list[str]:
    return [clause for clause in re.split(r"(?:[.;!?]\s*|\n+)", text.lower()) if clause]


def has_historical_phrasing(text: str) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in HISTORICAL_MARKERS)


def term_is_rejected_alternative(clause: str, term: str) -> bool:
    lowered = clause.lower()
    patterns = (
        f"instead of {term}",
        f"rather than {term}",
        f"not {term}",
        f"moved away from {term}",
        f"вместо {term}",
        f"а не {term}",
        f"отказались от {term}",
        f"больше не используем {term}",
    )
    if any(pattern in lowered for pattern in patterns):
        return True
    return re.search(rf"(?<![\w-])не\s+{re.escape(term)}\b", lowered) is not None


def term_shares_marker_clause(text: str, term: str, markers: tuple[str, ...]) -> bool:
    for clause in split_clauses(text):
        if has_historical_phrasing(clause):
            continue
        if term_is_rejected_alternative(clause, term):
            continue
        if term in clause and any(marker in clause for marker in markers):
            return True
    return False


def term_present_as_asserted(text: str, term: str) -> bool:
    return any(
        term in clause and not term_is_rejected_alternative(clause, term)
        for clause in split_clauses(text)
    )


def decision_current_system(content: str) -> str | None:
    lowered = content.lower()
    sqlite_override = (
        "instead of json",
        "from json to sqlite",
        "replace json with sqlite",
        "вместо json",
        "с json на sqlite",
        "заменили json на sqlite",
        "отказались от json",
    )
    json_override = (
        "instead of sqlite",
        "from sqlite to json",
        "replace sqlite with json",
        "вместо sqlite",
        "с sqlite на json",
        "заменили sqlite на json",
        "отказались от sqlite",
    )
    if "sqlite" in lowered and any(marker in lowered for marker in sqlite_override):
        return "sqlite"
    if "json" in lowered and any(marker in lowered for marker in json_override):
        return "json"

    has_sqlite = "sqlite" in lowered
    has_json = "json" in lowered
    if has_sqlite and not has_json:
        return "sqlite"
    if has_json and not has_sqlite:
        return "json"
    return None


def makes_memory_claim(text: str) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in MEMORY_CLAIM_MARKERS)


def signal_terms(text: str) -> set[str]:
    topics = {topic for topic in extract_topic_tags(text) if topic_weight(topic) >= 0.6}
    tokens = {
        token
        for token in re.findall(r"[a-zа-яё0-9-]+", text.lower())
        if len(token) >= 5 and token not in _GENERIC_SIGNAL_STOPWORDS
    }
    return topics | tokens
