"""Turn-scoped language detection and response policy."""

from dataclasses import dataclass
from enum import Enum
import re

from jarvis.debug_trace import trace_event


class LanguagePolicy(str, Enum):
    AUTO = "AUTO"
    FORCE_KO = "FORCE_KO"
    FORCE_JA = "FORCE_JA"
    FORCE_EN = "FORCE_EN"


class LanguageControlAction(str, Enum):
    NONE = "NONE"
    SET_LANGUAGE = "SET_LANGUAGE"
    CLEAR_LANGUAGE_OVERRIDE = "CLEAR_LANGUAGE_OVERRIDE"
    RESET_CONVERSATION_LANGUAGE = "RESET_CONVERSATION_LANGUAGE"
    SET_AUTO_LANGUAGE = "SET_AUTO_LANGUAGE"

    # Transitional aliases for callers written before Conversation Language
    # became distinct from a persistent language override.
    SET_OVERRIDE = "SET_LANGUAGE"
    CLEAR_OVERRIDE = "RESET_CONVERSATION_LANGUAGE"


@dataclass(frozen=True)
class LanguageControlCommand:
    action: LanguageControlAction = LanguageControlAction.NONE
    language: str = ""


class LanguageControlCommandParser:
    """Parse deterministic language-state commands before Planner routing."""

    def parse(self, text):
        normalized = str(text or "").lower().strip()
        if is_auto_language_request(normalized):
            return LanguageControlCommand(
                LanguageControlAction.RESET_CONVERSATION_LANGUAGE
            )
        language = explicit_response_language(normalized)
        if language and is_conversation_language_request(normalized):
            return LanguageControlCommand(
                LanguageControlAction.SET_LANGUAGE,
                language,
            )
        return LanguageControlCommand()


@dataclass(frozen=True)
class LanguageContext:
    detected_language: str = "ko"
    conversation_language: str = "ko"
    response_language: str = "ko"
    tts_voice: str = ""
    stt_provider: str = ""
    confidence: float = 0.0
    policy: LanguagePolicy = LanguagePolicy.AUTO
    explicit_override: bool = False
    conversation_override: bool = False
    override_cleared: bool = False
    response_source: str = "detected"

    def to_dict(self):
        return {
            "detected_language": self.detected_language,
            "conversation_language": self.conversation_language,
            "response_language": self.response_language,
            "tts_voice": self.tts_voice,
            "stt_provider": self.stt_provider,
            "confidence": self.confidence,
            "policy": self.policy.value,
            "explicit_override": self.explicit_override,
            "conversation_override": self.conversation_override,
            "override_cleared": self.override_cleared,
            "response_source": self.response_source,
        }


class LanguageResolver:
    """Resolve one response language while retaining conversation preference."""

    def __init__(self, policy=LanguagePolicy.AUTO, voices=None):
        self.policy = normalize_policy(policy)
        self.voices = {
            "ko": "openai:alloy:ko",
            "ja": "openai:nova:ja",
            "en": "openai:onyx:en",
            **dict(voices or {}),
        }
        self._conversation_languages = {}
        self._conversation_context_languages = {}
        self.control_parser = LanguageControlCommandParser()

    def resolve(
        self,
        text,
        conversation_id="",
        stt_provider="",
        confidence=None,
        preserve_conversation=False,
    ):
        detected, detected_confidence = detect_language(text)
        command = self.control_parser.parse(text)
        explicit = (
            command.language
            if command.action == LanguageControlAction.SET_LANGUAGE
            else explicit_response_language(text)
        )
        conversation_id = str(conversation_id or "")
        override_cleared = False
        reset_actions = {
            LanguageControlAction.CLEAR_LANGUAGE_OVERRIDE,
            LanguageControlAction.RESET_CONVERSATION_LANGUAGE,
            LanguageControlAction.SET_AUTO_LANGUAGE,
        }
        if command.action in reset_actions:
            previous_language = self._conversation_languages.get(conversation_id, "")
            previous_context = self._conversation_context_languages.get(
                conversation_id,
                "",
            )
            self._conversation_languages.pop(conversation_id, None)
            self._conversation_context_languages.pop(conversation_id, None)
            self.policy = LanguagePolicy.AUTO
            override_cleared = True
            trace_event(
                "runtime.language.override_cleared",
                conversation_id=conversation_id,
                detected_language=detected,
                previous_language=previous_language,
                previous=previous_language,
                previous_conversation_language=previous_context,
                conversation_language=detected,
                response_language=detected,
                response_source="explicit_control",
                override_cleared=True,
                current="AUTO",
            )
        if (
            conversation_id
            and command.action == LanguageControlAction.SET_LANGUAGE
        ):
            self._conversation_languages[conversation_id] = explicit
            trace_event(
                "runtime.language.override_set",
                conversation_id=conversation_id,
                override_language=explicit,
            )
        conversation = self._conversation_languages.get(conversation_id, "")
        forced = forced_language(self.policy)
        previous_context = self._conversation_context_languages.get(
            conversation_id,
            "",
        )
        if override_cleared:
            conversation_context = detected
        elif explicit:
            conversation_context = explicit
        elif preserve_conversation and previous_context:
            conversation_context = previous_context
        else:
            conversation_context = detected
        if conversation_id:
            self._conversation_context_languages[conversation_id] = conversation_context
        response = forced or explicit or conversation or (
            conversation_context if preserve_conversation else detected
        )
        response_source = (
            "policy"
            if forced
            else "explicit"
            if explicit
            else "conversation_override"
            if conversation
            else "explicit_control"
            if override_cleared
            else "conversation_continuity"
            if preserve_conversation and previous_context
            else "detected"
        )
        context = LanguageContext(
            detected_language=detected,
            conversation_language=conversation or conversation_context,
            response_language=response,
            tts_voice=self.voices.get(response, f"openai:alloy:{response}"),
            stt_provider=str(stt_provider or ""),
            confidence=round(
                float(confidence if confidence is not None else detected_confidence),
                3,
            ),
            policy=self.policy,
            explicit_override=bool(explicit),
            conversation_override=bool(conversation and not explicit and not forced),
            override_cleared=override_cleared,
            response_source=response_source,
        )
        trace_event("runtime.language.resolved", **context.to_dict())
        return context

    def clear_conversation(self, conversation_id):
        key = str(conversation_id or "")
        self._conversation_languages.pop(key, None)
        self._conversation_context_languages.pop(key, None)

    def stt_language_hint(self, conversation_id=""):
        """Return the language hint for audio transcription in this conversation."""
        forced = forced_language(self.policy)
        conversation = self._conversation_languages.get(
            str(conversation_id or ""),
            "",
        )
        return forced or conversation or "auto"


def normalize_policy(value):
    if isinstance(value, LanguagePolicy):
        return value
    try:
        return LanguagePolicy(str(value or "AUTO").upper())
    except ValueError:
        return LanguagePolicy.AUTO


def forced_language(policy):
    return {
        LanguagePolicy.FORCE_KO: "ko",
        LanguagePolicy.FORCE_JA: "ja",
        LanguagePolicy.FORCE_EN: "en",
    }.get(normalize_policy(policy), "")


def detect_language(text):
    value = str(text or "")
    scoring_value = remove_language_neutral_entities(value)
    meaningful = [character for character in scoring_value if character.isalpha()]
    if not meaningful:
        return "ko", 0.0
    transliterated_japanese = detect_transliterated_japanese(value)
    if transliterated_japanese:
        return "ja", transliterated_japanese
    transliterated_english = detect_transliterated_english(value)
    if transliterated_english:
        return "en", transliterated_english
    japanese = sum(
        "\u3040" <= character <= "\u30ff" for character in meaningful
    )
    korean = sum("\uac00" <= character <= "\ud7a3" for character in meaningful)
    latin = sum(
        ("a" <= character.lower() <= "z") for character in meaningful
    )
    scores = {"ja": japanese, "ko": korean, "en": latin}
    language = max(scores, key=scores.get)
    confidence = scores[language] / max(1, sum(scores.values()))
    return language, confidence


LANGUAGE_NEUTRAL_ENTITIES = (
    "\uac15\ub989",
    "gangneung",
    "\u6c5f\u9675",
    "\uc11c\uc6b8",
    "seoul",
    "\u30bd\u30a6\u30eb",
    "\ubd80\uc0b0",
    "busan",
    "\u91dc\u5c71",
    "\uc624\uc0ac\uce74",
    "osaka",
    "\u5927\u962a",
    "\u304a\u304a\u3055\u304b",
)


def remove_language_neutral_entities(text):
    """Exclude known named entities from mixed-language script scoring."""
    value = str(text or "")
    value = re.sub(
        r"\b\d{4}-\d{2}-\d{2}(?:[T\s]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:\d{2})?)?\b",
        " ",
        value,
        flags=re.IGNORECASE,
    )
    for entity in sorted(LANGUAGE_NEUTRAL_ENTITIES, key=len, reverse=True):
        value = re.sub(re.escape(entity), " ", value, flags=re.IGNORECASE)
    return value


def detect_transliterated_japanese(text):
    """Recognize Japanese that multilingual STT returned as Hangul phonetics."""
    normalized = re.sub(r"[^가-힣a-z0-9]+", " ", str(text or "").lower())
    markers = (
        "오스스메",
        "쿄쿠",
        "아루",
        "아리마스",
        "데스",
        "마스",
        "쿠다사이",
        "오시에테",
        "시테",
        "아시타",
        "텐키",
        "와타시",
        "스키",
    )
    matches = sum(marker in normalized for marker in markers)
    if matches < 2:
        return 0.0
    return min(0.95, 0.75 + (matches * 0.05))


def detect_transliterated_english(text):
    """Recognize English that multilingual STT returned as Hangul phonetics."""
    normalized = re.sub(r"[^가-힣a-z0-9]+", " ", str(text or "").lower())
    expressions = (
        r"(?:애니|아니)\s*송",
        r"두\s*유\s*노",
        r"왓(?:츠|이즈)",
        r"하우\s*(?:아|두)",
        r"캔\s*유",
        r"아이\s*(?:원트|니드|노)",
        r"플리즈",
        r"웨더",
        r"투모로우",
        r"헬로",
        r"땡큐",
    )
    matches = sum(bool(re.search(expression, normalized)) for expression in expressions)
    if matches < 2:
        return 0.0
    return min(0.95, 0.75 + (matches * 0.05))


def explicit_response_language(text):
    normalized = str(text or "").lower()
    patterns = (
        ("ja", (r"일본어로", r"日本語で", r"speak japanese", r"in japanese")),
        ("en", (r"영어로", r"英語で", r"speak english", r"in english")),
        ("ko", (r"한국어로", r"韓国語で", r"speak korean", r"in korean")),
    )
    for language, expressions in patterns:
        if any(re.search(expression, normalized) for expression in expressions):
            return language
    if "일본어 공부하자" in normalized or "日本語を勉強" in normalized:
        return "ja"
    return ""


def is_conversation_language_request(text):
    normalized = str(text or "").lower()
    return any(
        marker in normalized
        for marker in (
            "\uc9c0\uae08\ubd80\ud130",
            "\uc774\uc81c\ubd80\ud130",
            "\uc55e\uc73c\ub85c",
            "\uacc4\uc18d",
            "\ub300\ud654\ud558\uc790",
            "\ub300\ud654\ud574",
            "\ub2f5\ud574",
            "\ub9d0\ud574",
            "대화하자",
            "말하자",
            "계속",
            "앞으로",
            "오늘",
            "only",
            "from now",
            "話そう",
            "これから",
        )
    )


def is_auto_language_request(text):
    """Return whether the user asked to restore input-language AUTO mode."""
    normalized = str(text or "").lower().strip()
    compact = re.sub(r"[\s.,!?。！？_-]+", "", normalized)

    deterministic_markers = (
        "\uc77c\ubc18\ubaa8\ub4dc\ub85c\ub3cc\uc544\uc640",
        "\uc77c\ubc18\ubaa8\ub4dc\ub85c\ub3cc\uc544\uac00",
        "\uc6d0\ub798\ub300\ub85c\ub3cc\uc544\uc640",
        "\uc790\ub3d9\ubaa8\ub4dc\ub85c\ub3cc\uc544\uac00",
        "\uc785\ub825\uc5b8\uc5b4\uc5d0\ub9de\ucdb0\ub300\ub2f5\ud574",
        "\uc5b8\uc5b4\uace0\uc815\ud574\uc81c",
        "\uae30\ubcf8\uc5b8\uc5b4\ubaa8\ub4dc\ub85c\ub3cc\uc544\uac00",
    )
    if any(marker in compact for marker in deterministic_markers):
        return True

    if (
        "\uc77c\ubc18\ubaa8\ub4dc\ub85c\ub3cc\uc544\uc640" in compact
        or "\uc77c\ubc18\ubaa8\ub4dc\ub85c\ub3cc\uc544\uac00" in compact
    ):
        return True

    # Language-mode changes are runtime control commands, not chat requests.
    # Keep common exit phrases deterministic so an LLM cannot merely claim that
    # it changed the mode while leaving the conversation override untouched.
    compact_markers = (
        "\uc6d0\ub798\ub300\ub85c\ub3cc\uc544\uc640",  # 원래대로 돌아와
        "\uc6d0\ub798\ubaa8\ub4dc\ub85c\ub3cc\uc544\uc640",  # 원래 모드로 돌아와
        "\uae30\ubcf8\uc73c\ub85c\ub3cc\uc544\uac00",  # 기본으로 돌아가
        "\uae30\ubcf8\ubaa8\ub4dc\ub85c\ub3cc\uc544\uac00",  # 기본 모드로 돌아가
        "\uc790\ub3d9\uc73c\ub85c\ud574",  # 자동으로 해
        "\uc5b8\uc5b4\uace0\uc815\ud574\uc81c",  # 언어 고정 해제
        "\u65e5\u672c\u8a9e\u30e2\u30fc\u30c9\u89e3\u9664",  # 日本語モード解除
        "\u81ea\u52d5\u8a00\u8a9e\u30e2\u30fc\u30c9\u306b\u623b\u3057\u3066",  # 自動言語モードに戻して
    )
    if any(marker in compact for marker in compact_markers):
        return True

    english_exit_patterns = (
        r"(?:japanese|english|korean)(?:\s+language)?\s+mode\s+(?:off|disable(?:d)?)",
        r"(?:turn|switch)\s+off\s+(?:the\s+)?(?:japanese|english|korean)(?:\s+language)?\s+mode",
        r"(?:go|switch|return)\s+back\s+to\s+(?:the\s+)?(?:original|default|auto(?:matic)?)(?:\s+language)?\s+mode",
    )
    if any(re.search(pattern, normalized) for pattern in english_exit_patterns):
        return True

    patterns = (
        r"(?:이제\s*)?(?:언어\s*)?자동(?:\s*모드)?(?:으로)?\s*(?:돌아가|전환|바꿔|해줘)",
        r"자동\s*언어(?:\s*모드)?(?:로|으로)?\s*(?:돌아가|전환|바꿔|해줘)",
        r"자동\s*감지(?:\s*모드)?(?:로|으로)?\s*(?:돌아가|전환|바꿔|해줘)",
        r"입력\s*언어(?:에\s*맞춰|대로).*(?:답|응답)",
        r"언어\s*(?:설정\s*)?(?:초기화|고정\s*해제)",
        r"기본\s*언어\s*모드(?:로|으로)?\s*돌아가",
        r"(?:switch|go|return|reset).*(?:language\s*)?(?:to\s*)?auto(?:matic)?",
        r"use\s+the\s+language\s+i\s+speak",
        r"clear\s+the\s+language\s+override",
        r"(?:language\s*)?auto(?:matic)?\s*mode",
        r"(?:言語を?)?自動(?:モード)?(?:に)?(?:戻|切り替)",
        r"自動言語モード(?:に)?(?:戻|切り替)",
        r"じどう\s*げんご\s*もーど\s*に\s*もどして",
        r"지도[\s-]*겐고[\s-]*모[\s-]*도니\s*모도시테",
    )
    return any(re.search(pattern, normalized) for pattern in patterns)


def response_language_instruction(language):
    return {
        "ko": "Respond in Korean.",
        "ja": "Respond in natural Japanese.",
        "en": "Respond in English.",
    }.get(str(language or ""), f"Respond in {language}.")
