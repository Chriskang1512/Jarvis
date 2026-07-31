"""Shared multilingual follow-up phrase classification."""

from __future__ import annotations

import re
from dataclasses import dataclass


FOLLOW_UP_PHRASES = {
    "en": (
        "how about",
        "what about",
        "how's",
        "and then",
        "and",
        "then",
    ),
    "ja": (
        "じゃあ",
        "じゃ",
        "では",
        "それでは",
    ),
    "ko": (
        "그럼",
        "그러면",
        "그다음",
        "그리고",
    ),
}

TEMPORAL_FOLLOW_UP_PHRASES = {
    "en": (
        "today",
        "tomorrow",
        "day after tomorrow",
        "next week",
        "monday",
        "tuesday",
        "wednesday",
        "thursday",
        "friday",
        "saturday",
        "sunday",
    ),
    "ja": (
        "今日",
        "きょう",
        "明日",
        "あした",
        "明後日",
        "あさって",
        "来週",
        "月曜日",
        "火曜日",
        "水曜日",
        "木曜日",
        "金曜日",
        "土曜日",
        "日曜日",
    ),
    "ko": (
        "오늘",
        "내일",
        "모레",
        "다음 주",
        "다음주",
        "월요일",
        "화요일",
        "수요일",
        "목요일",
        "금요일",
        "토요일",
        "일요일",
    ),
}


@dataclass(frozen=True)
class FollowUpPhraseMatch:
    is_follow_up: bool
    language: str
    discourse_marker: str = ""
    temporal_reference: str = ""

    @property
    def has_temporal_reference(self):
        return bool(self.temporal_reference)


class FollowUpPhraseRegistry:
    """Classify terse follow-ups without binding them to one Ability."""

    def __init__(self, phrases=None, temporal_phrases=None):
        self.phrases = {
            key: tuple(values)
            for key, values in (phrases or FOLLOW_UP_PHRASES).items()
        }
        self.temporal_phrases = {
            key: tuple(values)
            for key, values in (
                temporal_phrases or TEMPORAL_FOLLOW_UP_PHRASES
            ).items()
        }

    def match(self, text, language=""):
        normalized = normalize_follow_up_text(text)
        detected = language or detect_phrase_language(normalized)
        languages = (
            (detected,)
            if detected in self.phrases
            else tuple(self.phrases)
        )
        marker = ""
        temporal = ""
        for candidate_language in languages:
            marker = first_prefix(
                normalized, self.phrases.get(candidate_language, ())
            )
            temporal = first_contained(
                normalized,
                self.temporal_phrases.get(candidate_language, ()),
            )
            if marker or temporal:
                detected = candidate_language
                break
        terse_temporal = bool(temporal) and word_count(normalized) <= 5
        return FollowUpPhraseMatch(
            is_follow_up=bool(marker or terse_temporal),
            language=detected or "unknown",
            discourse_marker=marker,
            temporal_reference=temporal,
        )

    def strip_discourse_markers(self, text):
        value = str(text or "")
        for phrases in self.phrases.values():
            for phrase in sorted(phrases, key=len, reverse=True):
                if phrase.isascii():
                    value = re.sub(
                        rf"\b{re.escape(phrase)}\b",
                        " ",
                        value,
                        flags=re.IGNORECASE,
                    )
                else:
                    value = value.replace(phrase, " ")
        return value.strip()

    def strip_temporal_references(self, text):
        value = str(text or "")
        for phrases in self.temporal_phrases.values():
            for phrase in sorted(phrases, key=len, reverse=True):
                if phrase.isascii():
                    value = re.sub(
                        rf"\b{re.escape(phrase)}\b",
                        " ",
                        value,
                        flags=re.IGNORECASE,
                    )
                else:
                    value = value.replace(phrase, " ")
        return " ".join(value.split())


DEFAULT_FOLLOW_UP_PHRASE_REGISTRY = FollowUpPhraseRegistry()


def normalize_follow_up_text(text):
    value = str(text or "").strip().casefold()
    value = re.sub(r"[?？!！.。]+$", "", value).strip()
    return " ".join(value.split())


def detect_phrase_language(text):
    if re.search(r"[\u3040-\u30ff\u4e00-\u9fff]", text):
        return "ja"
    if re.search(r"[\uac00-\ud7a3]", text):
        return "ko"
    if re.search(r"[a-z]", text):
        return "en"
    return "unknown"


def first_prefix(text, phrases):
    for phrase in sorted(phrases, key=len, reverse=True):
        if (
            text == phrase
            or text.startswith(phrase + " ")
            or (not phrase.isascii() and text.startswith(phrase))
        ):
            return phrase
    return ""


def first_contained(text, phrases):
    for phrase in sorted(phrases, key=len, reverse=True):
        if phrase.isascii():
            if re.search(rf"\b{re.escape(phrase)}\b", text):
                return phrase
        elif phrase in text:
            return phrase
    return ""


def word_count(text):
    return len(re.findall(r"[\w\u3040-\u30ff\u4e00-\u9fff\uac00-\ud7a3]+", text))
