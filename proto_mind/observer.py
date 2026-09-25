from __future__ import annotations
import re

from proto_mind.models import ObserverState
from proto_mind.topic_utils import extract_topic_tags
from proto_mind.text_normalization import normalize_text


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
        "як ми обговорювали",
        "як ми говорили",
        "нагадай мені",
        "продовжимо з",
        "продовжимо роботу",
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
        "насправді",
        "замість",
        "змінюємо напрям",
        "тепер використовуємо",
        "більше не",
        "заміни",
        "замінити",
        "переходимо на",
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
        "що ти пам'ятаєш",
        "що ти зараз пам'ятаєш",
        "що зберігається в пам'яті",
        "які вподобання ти знаєш",
        "які уподобання ти знаєш",
        "які рішення ми прийняли",
        "що ми вирішили",
        "що використовуємо зараз",
        "яку систему зберігання",
        "який бекенд пам'яті",
        "що використовували раніше",
        "що змінилося",
        "поточний архітектурний напрям",
        "поточний напрям",
        "поточна реалізація",
        "досі актуально",
        "чому я віддаю перевагу",
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
        "як ми обговорювали",
        "як ми говорили",
        "нагадай",
        "раніше",
        "попередн",
        "продовжимо",
        "продовжуємо",
        "повернімося до",
        "повернемося до",
        "вже є",
        "досі",
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
        "я віддаю перевагу",
        "мені подобається",
        "на майбутнє",
        "завжди використовуй",
        "моє уподобання",
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
        "як тобі відповідати",
        "як ти маєш відповідати",
        "який стиль відповіді",
        "чому я віддаю перевагу",
        "у майбутніх відповідях",
        "у майбутніх обговореннях",
        "відповідай мені в майбутньому",
        "пояснюй пізніше",
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
        "ми вирішили",
        "рішення",
        "давай використовувати",
        "нумо використовувати",
        "тепер використовуємо",
        "переходимо на",
    )

    # Generic state phrases that equally describe code under work.
    WORK_STATE_MARKERS = frozenset({
        "what changed", "current implementation", "currently have", "using now",
        "что изменилось", "текущая реализация", "що змінилося", "поточна реалізація",
    })
    WORK_REQUEST = re.compile(
        r"(?:^|[.!?\n;:]\s*)(?:(?:please|can you|could you|пожалуйста|можешь|давай|брат|будь ласка|можеш)[, ]+)*"
        r"(?:fix|implement|refactor|debug|review|inspect|rewrite|build|test|look at|investigate|explore|analy[sz]e|"
        r"audit|run|open|add|remove|update|continue|"
        r"исправь|перепиши|реализуй|проверь код|изучи|проведи аудит|посмотри|глянь|пройдись|запусти|открой|"
        r"сделай|добавь|удали|почини|пофикси|продолжай|приступай|разберись|проанализируй|"
        r"виправ|реалізуй|перевір код|подивись|вивчи|відкрий|зроби|додай|видали|продовжуй|проаналізуй)\b")
    MAX_INVENTORY_HEURISTIC_CHARS = 300

    def analyze(self, user_input: str) -> ObserverState:
        lowered = normalize_text(user_input)
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
        if text.startswith(("remember that", "запомни, что", "запомни что", "запам'ятай, що", "запам'ятай що")):
            return "personal_context"
        if any(phrase in text for phrase in self.EXPLICIT_CONTINUITY_MARKERS):
            return "continuity_followup"
        if self._is_memory_inventory_query(text):
            return "memory_inventory"
        if self._is_override_decision(text):
            return "decision_request"
        if self._has_continuity_signal(text):
            return "continuity_followup"
        if any(phrase in text for phrase in ("remember that", "запомни, что", "запомни что", "запам'ятай, що", "запам'ятай що", *self.PREFERENCE_MARKERS)):
            return "personal_context"
        if any(phrase in text for phrase in self.DECISION_MARKERS):
            return "decision_request"
        if any(phrase in text for phrase in ("architecture", "module", "design", "reasoner", "memory", "архитектур", "модул", "дизайн", "ризонер", "памят", "архітектур", "пам'ят")):
            return "meta_architecture"
        if any(phrase in text for phrase in ("project", "roadmap", "mvp", "proto-mind", "проект", "проєкт", "дорожн", "прото-майнд")):
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
        if any(term in text for term in ("important", "remember", "decision", "preference", "always", "важн", "запомн", "решени", "предпоч", "всегда", "важлив", "запам'ят", "рішенн", "уподоб", "переваг", "завжди")):
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
        # A coding/review request can mention memory or ask what changed. Those
        # words describe the work, not a request to enumerate personal memory;
        # an explicit question about remembered decisions still counts.
        work = bool(self.WORK_REQUEST.search(text))
        if any(phrase in text for phrase in self.MEMORY_INVENTORY_MARKERS
               if not (work and phrase in self.WORK_STATE_MARKERS)):
            return True
        # Word-level matching fits a short question, not a task description.
        if work or len(text) > self.MAX_INVENTORY_HEURISTIC_CHARS:
            return False
        if not self._is_recall_question(text):
            return False

        inventory_verbs = ("remember", "stored", "use", "using", "used", "decide", "decision", "pick", "change", "changed", "current", "помн", "хран", "использ", "реш", "выбра", "измен", "текущ", "пам'ята", "зберіг", "використ", "виріш", "обрал", "змін", "поточ")
        inventory_topics = ("storage", "backend", "persistence", "preference", "decision", "json", "sqlite", "memory", "direction", "implementation", "хранил", "бэкенд", "постоян", "предпоч", "решени", "памят", "направлен", "реализац", "сховищ", "зберіган", "бекенд", "вподоб", "уподоб", "рішенн", "пам'ят", "напрям", "реалізац", "базу даних")
        return any(verb in text for verb in inventory_verbs) and any(topic in text for topic in inventory_topics)

    def _is_override_decision(self, text: str) -> bool:
        if not any(phrase in text for phrase in self.OVERRIDE_DECISION_MARKERS):
            return False
        return any(signal in text for signal in ("should use", "use ", "replace", "instead of", "we now use", "использ", "замен", "вместо", "переходим", "використ", "замін", "замість", "переходимо"))

    def _is_preference_behavior_query(self, text: str) -> bool:
        if any(phrase in text for phrase in self.PREFERENCE_BEHAVIOR_MARKERS):
            return True
        behavior_words = ("explain", "respond", "style", "future", "later", "объяс", "отвеч", "стиль", "будущ", "позже", "поясн", "відповід", "майбут", "пізніше")
        preference_words = ("should you", "should we", "use", "responses", "discussions", "должен", "использ", "ответ", "обсужден", "маєш", "використ", "відповід", "обговор")
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
            "що", "який", "яка", "які", "яку", "нагадай", "згадай",
            "перевір поточ", "повтори поточ", "вже", "досі",
        )
        return "?" in text or text.startswith("чи ") or any(marker in text for marker in recall_markers)
