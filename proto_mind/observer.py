from __future__ import annotations

from proto_mind.models import ObserverState
from proto_mind.topic_utils import extract_topic_tags


class Observer:
    EXPLICIT_CONTINUITY_MARKERS = (
        "as we discussed earlier",
        "remind me",
        "continue from",
        "как мы обсуждали",
        "как мы говорили",
        "напомни мне",
        "продолжим с",
        "продолжим работу",
    )
    OVERRIDE_DECISION_MARKERS = (
        "actually",
        "instead of",
        "changing direction",
        "we now use",
        "no longer",
        "replace",
        "на самом деле",
        "вместо",
        "меняем направление",
        "теперь используем",
        "больше не",
        "замени",
        "заменить",
        "переходим на",
    )
    MEMORY_INVENTORY_MARKERS = (
        "what do you remember",
        "what do you currently remember",
        "what memory do you currently have",
        "what is currently stored",
        "what preferences do you know",
        "what preferences and decisions",
        "what decisions do we have",
        "what decisions are we using now",
        "what durable architectural decisions",
        "what did we decide",
        "what are we using now",
        "what storage approach",
        "what storage system",
        "what memory backend",
        "what backend did we pick",
        "what did we decide about persistence",
        "what did we use before",
        "what changed",
        "current architectural direction",
        "current direction",
        "current implementation",
        "still the current",
        "change our mind",
        "using now",
        "currently have",
        "что ты помнишь",
        "что ты сейчас помнишь",
        "что хранится в памяти",
        "какие предпочтения ты знаешь",
        "какие решения мы приняли",
        "что мы решили",
        "что используем сейчас",
        "какую систему хранения",
        "какой бэкенд памяти",
        "что использовали раньше",
        "что изменилось",
        "текущее архитектурное направление",
        "текущее направление",
        "текущая реализация",
        "всё ещё актуально",
        "все еще актуально",
        "что я предпочитаю",
    )
    CONTINUITY_MARKERS = (
        "as we discussed earlier",
        "remind me",
        "earlier",
        "previous",
        "continue from",
        "already have",
        "so far",
        "как мы обсуждали",
        "как мы говорили",
        "напомни",
        "раньше",
        "предыдущ",
        "продолжим",
        "вернёмся к",
        "вернемся к",
        "уже есть",
        "до сих пор",
    )
    PREFERENCE_MARKERS = (
        "i prefer",
        "my preference",
        "for future",
        "always use",
        "я предпочитаю",
        "мне нравится",
        "для будущего",
        "всегда используй",
    )
    PREFERENCE_BEHAVIOR_MARKERS = (
        "how should you explain",
        "how should you respond",
        "how should you answer",
        "what style should you use",
        "what response style should you use",
        "response style preference",
        "answer style",
        "what do i prefer",
        "future responses",
        "future discussions",
        "answer me in the future",
        "explain proto-mind later",
        "explain later",
        "как тебе отвечать",
        "как ты должен отвечать",
        "какой стиль ответа",
        "что я предпочитаю",
        "в будущих ответах",
        "в будущих обсуждениях",
        "отвечай мне в будущем",
        "объясняй позже",
    )
    DECISION_MARKERS = (
        "we decided",
        "decision",
        "should we choose",
        "let's use",
        "we now use",
        "мы решили",
        "решение",
        "давай использовать",
        "теперь используем",
        "переходим на",
    )

    def analyze(self, user_input: str) -> ObserverState:
        lowered = user_input.lower()
        tags = self._extract_tags(lowered)
        query_type = self._classify_query(lowered)
        needs_memory = self._needs_memory(query_type, lowered)
        importance_hint = self._estimate_importance(query_type, lowered)
        return ObserverState(
            query_type=query_type,
            needs_memory=needs_memory,
            importance_hint=importance_hint,
            topic_tags=tags,
        )

    def _classify_query(self, text: str) -> str:
        if any(phrase in text for phrase in self.EXPLICIT_CONTINUITY_MARKERS):
            return "continuity_followup"
        if self._is_memory_inventory_query(text):
            return "memory_inventory"
        if self._is_override_decision(text):
            return "decision_request"
        if self._has_continuity_signal(text):
            return "continuity_followup"
        if any(phrase in text for phrase in ("remember that", "запомни, что", "запомни что", *self.PREFERENCE_MARKERS)):
            return "personal_context"
        if any(phrase in text for phrase in self.DECISION_MARKERS):
            return "decision_request"
        if any(phrase in text for phrase in ("architecture", "module", "design", "reasoner", "memory", "архитектур", "модул", "дизайн", "ризонер", "памят")):
            return "meta_architecture"
        if any(phrase in text for phrase in ("project", "roadmap", "mvp", "proto-mind", "проект", "дорожн", "прото-майнд")):
            return "project_context"
        return "new_question"

    def _needs_memory(self, query_type: str, text: str) -> bool:
        if query_type == "memory_inventory":
            return True
        if query_type == "personal_context" and not self._is_recall_question(text):
            return False
        if self._is_preference_behavior_query(text):
            return True
        if query_type == "personal_context":
            return False
        if self._has_continuity_signal(text):
            return True
        if query_type == "project_context" and self._is_recall_question(text):
            return True
        if query_type == "meta_architecture" and self._is_recall_question(text):
            return True
        return False

    def _estimate_importance(self, query_type: str, text: str) -> float:
        base_scores = {
            "new_question": 0.35,
            "continuity_followup": 0.7,
            "decision_request": 0.85,
            "personal_context": 0.8,
            "project_context": 0.75,
            "meta_architecture": 0.65,
            "memory_inventory": 0.8,
        }
        score = base_scores.get(query_type, 0.4)
        if any(term in text for term in ("important", "remember", "decision", "preference", "always", "важн", "запомн", "решени", "предпоч", "всегда")):
            score += 0.1
        if self._is_preference_behavior_query(text):
            score += 0.1
        return min(score, 1.0)

    def _extract_tags(self, text: str) -> list[str]:
        tags = extract_topic_tags(text)
        return tags or ["general"]

    def _has_continuity_signal(self, text: str) -> bool:
        return any(phrase in text for phrase in self.CONTINUITY_MARKERS)

    def _is_memory_inventory_query(self, text: str) -> bool:
        if any(phrase in text for phrase in self.MEMORY_INVENTORY_MARKERS):
            return True

        if not self._is_recall_question(text):
            return False

        inventory_verbs = ("remember", "stored", "use", "using", "used", "decide", "decision", "pick", "change", "changed", "current", "помн", "хран", "использ", "реш", "выбра", "измен", "текущ")
        inventory_topics = ("storage", "backend", "persistence", "preference", "decision", "json", "sqlite", "memory", "direction", "implementation", "хранил", "бэкенд", "постоян", "предпоч", "решени", "памят", "направлен", "реализац")
        return any(verb in text for verb in inventory_verbs) and any(topic in text for topic in inventory_topics)

    def _is_override_decision(self, text: str) -> bool:
        if not any(phrase in text for phrase in self.OVERRIDE_DECISION_MARKERS):
            return False
        return any(signal in text for signal in ("should use", "use ", "replace", "instead of", "we now use", "использ", "замен", "вместо", "переходим"))

    def _is_preference_behavior_query(self, text: str) -> bool:
        if any(phrase in text for phrase in self.PREFERENCE_BEHAVIOR_MARKERS):
            return True
        behavior_words = ("explain", "respond", "style", "future", "later", "объяс", "отвеч", "стиль", "будущ", "позже")
        preference_words = ("should you", "should we", "use", "responses", "discussions", "должен", "использ", "ответ", "обсужден")
        return any(word in text for word in behavior_words) and any(word in text for word in preference_words)

    @staticmethod
    def _is_recall_question(text: str) -> bool:
        recall_markers = (
            "what",
            "which",
            "remind",
            "recap",
            "summarize",
            "check the current",
            "restate the current",
            "repeat the current",
            "already",
            "so far",
            "что",
            "какой",
            "какая",
            "какие",
            "напомни",
            "вспомни",
            "проверь текущее",
            "проверь текущую",
            "повтори текущее",
            "повтори текущую",
            "уже",
            "до сих пор",
        )
        return "?" in text or any(marker in text for marker in recall_markers)
