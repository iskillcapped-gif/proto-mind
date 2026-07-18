from __future__ import annotations

import re


GENERIC_TOPIC_WEIGHTS = {
    "decision": 0.2,
    "preference": 0.25,
    "memory": 0.25,
    "project": 0.2,
    "proto-mind": 0.3,
    "current": 0.2,
    "historical": 0.2,
    "change": 0.2,
    "continuity": 0.2,
}

MEDIUM_TOPIC_WEIGHTS = {
    "storage": 0.7,
    "backend": 0.7,
    "persistence": 0.75,
    "architecture": 0.6,
    "style": 0.7,
    "explanation": 0.7,
    "response_style": 0.75,
    "future_behavior": 0.75,
    "concise": 0.7,
    "short": 0.7,
}

STOPWORDS = {
    "a",
    "about",
    "an",
    "and",
    "approach",
    "are",
    "as",
    "be",
    "did",
    "do",
    "does",
    "for",
    "have",
    "how",
    "i",
    "if",
    "in",
    "is",
    "it",
    "me",
    "my",
    "now",
    "of",
    "on",
    "or",
    "our",
    "separately",
    "should",
    "that",
    "the",
    "their",
    "them",
    "they",
    "this",
    "to",
    "use",
    "using",
    "we",
    "what",
    "which",
    "with",
    "system",
    "later",
    "как",
    "что",
    "это",
    "для",
    "или",
    "уже",
    "тебе",
    "меня",
    "мне",
    "над",
    "наш",
    "наша",
    "наше",
    "ты",
    "мы",
    "я",
}

PHRASE_CANONICAL_TAGS = {
    "concise architectural explanations": ("preference", "concise", "architecture", "explanation", "response_style"),
    "json-backed memory": ("json", "storage", "persistence", "memory"),
    "json backed memory": ("json", "storage", "persistence", "memory"),
    "short answers": ("preference", "short", "response_style"),
    "response style": ("preference", "style", "response_style"),
    "answer style": ("preference", "style", "response_style"),
    "style preference": ("preference", "style", "response_style"),
    "storage system": ("storage",),
    "storage approach": ("storage",),
    "memory backend": ("storage", "backend", "memory"),
    "backend": ("backend", "storage"),
    "persistence": ("persistence", "storage"),
    "persistent memory": ("persistence", "memory", "storage"),
    "how should you explain": ("future_behavior", "explanation", "response_style"),
    "how should you respond": ("future_behavior", "response_style"),
    "how should you answer": ("future_behavior", "response_style"),
    "what style should you use": ("future_behavior", "style", "response_style"),
    "what response style should you use": ("preference", "future_behavior", "style", "response_style"),
    "how should you answer me": ("future_behavior", "response_style"),
    "what do i prefer": ("preference",),
    "future responses": ("future_behavior", "response_style"),
    "future response": ("future_behavior", "response_style"),
    "future discussions": ("future_behavior",),
    "architecture discussions": ("architecture", "future_behavior"),
    "explain later": ("future_behavior", "explanation"),
    "answer me in the future": ("future_behavior", "response_style"),
    "using now": ("current",),
    "right now": ("current",),
    "currently": ("current",),
    "active decision": ("current", "decision"),
    "used before": ("historical",),
    "before sqlite": ("historical", "sqlite", "storage"),
    "before json": ("historical", "json", "storage"),
    "used to": ("historical",),
    "what changed": ("historical", "change"),
    "changed over time": ("historical", "change"),
    "instead of": ("decision", "change", "historical"),
    "no longer": ("change", "historical"),
    "proto-mind": ("proto-mind",),
    "memory keeper": ("memory", "memory-keeper"),
    "we now use": ("decision", "current"),
    "короткие ответы": ("preference", "short", "response_style"),
    "краткие ответы": ("preference", "short", "response_style"),
    "лаконичные ответы": ("preference", "concise", "response_style"),
    "стиль ответа": ("preference", "style", "response_style"),
    "как отвечать": ("future_behavior", "response_style"),
    "что я предпочитаю": ("preference",),
    "в будущих ответах": ("future_behavior", "response_style"),
    "система хранения": ("storage",),
    "бэкенд памяти": ("backend", "storage", "memory"),
    "постоянная память": ("persistence", "memory", "storage"),
    "используем сейчас": ("current",),
    "прямо сейчас": ("current",),
    "активное решение": ("current", "decision"),
    "использовали раньше": ("historical",),
    "что изменилось": ("historical", "change"),
    "вместо": ("decision", "change", "historical"),
    "больше не": ("change", "historical"),
    "сейчас помнишь": ("current", "memory"),
    "теперь используем": ("decision", "current"),
    "хранения памяти": ("storage", "memory"),
    "стиле ответа": ("preference", "style", "response_style"),
    "как мы обсуждали": ("continuity", "historical"),
    "продолжим работу": ("continuity", "project"),
    "прото-майнд": ("proto-mind",),
}

TOKEN_CANONICAL_TAGS = {
    "active": ("current",),
    "architecture": ("architecture",),
    "backend": ("backend", "storage"),
    "before": ("historical",),
    "change": ("change", "historical"),
    "changed": ("change", "historical"),
    "changing": ("change", "historical"),
    "concise": ("concise", "response_style"),
    "coordinator": ("coordinator",),
    "database": ("storage",),
    "databases": ("storage",),
    "decide": ("decision",),
    "decided": ("decision",),
    "decision": ("decision",),
    "decisions": ("decision",),
    "earlier": ("historical",),
    "explain": ("explanation", "response_style"),
    "explained": ("explanation", "response_style"),
    "explaining": ("explanation", "response_style"),
    "explanation": ("explanation", "response_style"),
    "explanations": ("explanation", "response_style"),
    "former": ("historical",),
    "future": ("future_behavior",),
    "history": ("historical",),
    "json": ("json", "storage"),
    "later": ("future_behavior",),
    "memory": ("memory",),
    "observer": ("observer",),
    "old": ("historical",),
    "persist": ("persistence", "storage"),
    "persistence": ("persistence", "storage"),
    "persistent": ("persistence", "storage"),
    "pick": ("decision",),
    "picked": ("decision",),
    "preference": ("preference",),
    "preferences": ("preference",),
    "project": ("project",),
    "projects": ("project",),
    "proto": ("proto-mind",),
    "previous": ("historical",),
    "previously": ("historical",),
    "reasoner": ("reasoner",),
    "remember": ("memory",),
    "remembered": ("memory",),
    "respond": ("response_style",),
    "response": ("response_style",),
    "responses": ("response_style",),
    "short": ("short", "response_style"),
    "sqlite": ("sqlite", "storage"),
    "storage": ("storage",),
    "stored": ("memory",),
    "style": ("style", "response_style"),
    "superseded": ("historical", "change"),
    "prefer": ("preference",),
    "архитектура": ("architecture",),
    "архитектуре": ("architecture",),
    "архитектуры": ("architecture",),
    "бэкенд": ("backend", "storage"),
    "будущем": ("future_behavior",),
    "будущих": ("future_behavior",),
    "изменили": ("change", "historical"),
    "изменилось": ("change", "historical"),
    "изменение": ("change", "historical"),
    "краткие": ("short", "response_style"),
    "короткие": ("short", "response_style"),
    "лаконично": ("concise", "response_style"),
    "модуль": ("module",),
    "модули": ("module",),
    "объяснять": ("explanation", "response_style"),
    "ответы": ("response_style",),
    "отвечать": ("response_style",),
    "память": ("memory",),
    "памяти": ("memory",),
    "помнишь": ("memory",),
    "предпочитаю": ("preference",),
    "предпочтение": ("preference",),
    "предпочтения": ("preference",),
    "предпочтениях": ("preference",),
    "предыдущий": ("historical",),
    "продолжим": ("continuity",),
    "проект": ("project",),
    "проекта": ("project",),
    "проекте": ("project",),
    "проектом": ("project",),
    "раньше": ("historical",),
    "решение": ("decision",),
    "решения": ("decision",),
    "решениях": ("decision",),
    "решили": ("decision",),
    "сейчас": ("current",),
    "стиль": ("style", "response_style"),
    "стиле": ("style", "response_style"),
    "ответа": ("response_style",),
    "текущая": ("current",),
    "текущее": ("current",),
    "текущий": ("current",),
    "хранение": ("storage",),
    "хранилище": ("storage",),
}


def extract_topic_tags(text: str) -> list[str]:
    lowered = text.lower()
    found: list[str] = []
    seen: set[str] = set()

    for phrase, tags in PHRASE_CANONICAL_TAGS.items():
        if phrase in lowered:
            for tag in tags:
                if tag not in seen:
                    found.append(tag)
                    seen.add(tag)

    tokens = re.findall(r"[a-zа-яё0-9-]+", lowered)
    for token in tokens:
        if token in STOPWORDS:
            continue
        token_tags = TOKEN_CANONICAL_TAGS.get(token)
        if token_tags:
            for tag in token_tags:
                if tag not in seen:
                    found.append(tag)
                    seen.add(tag)
    for token in tokens:
        if token in STOPWORDS or token in TOKEN_CANONICAL_TAGS:
            continue
        if token.isascii() and len(token) > 4 and token not in {"using", "should", "their", "there", "currently"}:
            if token not in seen:
                found.append(token)
                seen.add(token)

    if "sqlite" in seen or "json" in seen or "backend" in seen or "persistence" in seen:
        if "storage" not in seen:
            found.append("storage")

    return found[:8]


def topic_weight(tag: str) -> float:
    if tag in GENERIC_TOPIC_WEIGHTS:
        return GENERIC_TOPIC_WEIGHTS[tag]
    if tag in MEDIUM_TOPIC_WEIGHTS:
        return MEDIUM_TOPIC_WEIGHTS[tag]
    return 1.0


def weighted_topic_overlap(left_topics: list[str], right_topics: list[str]) -> float:
    left = set(left_topics)
    right = set(right_topics)
    if not left or not right:
        return 0.0

    shared_weight = sum(topic_weight(tag) for tag in left & right)
    total_weight = sum(topic_weight(tag) for tag in left | right)
    if total_weight == 0:
        return 0.0
    return round(shared_weight / total_weight, 4)
