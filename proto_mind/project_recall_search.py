"""Shared local note ranking; never reads files, changes notes or calls a model."""
from collections import Counter
import re

from proto_mind.project_recall_terms import content_terms
from proto_mind.text_normalization import normalize_text

ALGORITHM = "local_content_terms_v3"
TECHNOLOGIES = frozenset("redis postgresql sqlite python swift docker github typescript javascript selenium wayforpay mongodb mysql".split())
ENVIRONMENTS = frozenset({"local", "production", "staging"})
PATH_WORD = re.compile(r"(?<![\w@])(?:\.{0,2}/|/)?[\w.-]+(?:/[\w.-]+)*/?")


def qualifiers(text: str, *, document: bool = False) -> tuple[set[str], set[str], set[str]]:
    terms = content_terms(text)
    paths = set()
    for match in PATH_WORD.finditer(normalize_text(text)):
        value = match.group().rstrip(".,;:!?").rstrip("/")
        if ("/" in match.group() or "_" in value or re.search(r"\w\.\w", value)
                or value.startswith(".") and len(value) > 1):
            paths.add(value)
            if document:
                paths.add(value.rsplit("/", 1)[-1])
    return paths, terms & TECHNOLOGIES, terms & ENVIRONMENTS


def rank_notes(records: list[dict], query: str) -> list[dict]:
    query_terms = content_terms(query)
    required = qualifiers(query)
    candidates = []
    for row in records:
        # The source/basis explains provenance; it is not note content.
        content = row["body"]["content"]
        available = qualifiers(content, document=True)
        if any(wanted and not wanted & found for wanted, found in zip(required, available)):
            continue
        matched = query_terms & content_terms(content)
        matched.update("literal:" + value for value in required[0] & available[0])
        if matched:
            candidates.append((matched, row))
    # A lone generic overlap adds no useful specificity when another note covers
    # that same term together with more of the question. Independent topics stay.
    stronger_terms = set().union(*(terms for terms, _ in candidates if len(terms) > 1))
    candidates = [(terms, row) for terms, row in candidates
                  if len(terms) > 1 or not terms & stronger_terms]
    frequency = Counter(term for terms, _ in candidates for term in terms)
    return [row for _, row in sorted(candidates, key=lambda pair: (
        len(pair[0]), sum(1 / frequency[term] for term in sorted(pair[0])),
        pair[1]["saved_at"], pair[1]["id"]), reverse=True)]


def requested_algorithm(params: dict) -> str:
    # No option means a pre-v3 Native client. Its old receipt format stays usable.
    value = params.get("project_recall_algorithm", "local_content_terms_v2")
    if not isinstance(value, str) or value not in {"local_content_terms_v2", ALGORITHM}:
        raise ValueError("Unknown project recall algorithm.")
    return value
