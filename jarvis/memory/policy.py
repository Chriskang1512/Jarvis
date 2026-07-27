"""Conservative policy that decides whether user information is durable."""

import re

from jarvis.memory.models import MemoryType, StoreDecision


class MemoryStorePolicy:
    def decide(self, text):
        normalized = str(text or "").strip().rstrip(".!?")
        if not normalized:
            return StoreDecision(False, "empty")

        preference = parse_preference(normalized)
        if preference is not None:
            key, value = preference
            return StoreDecision(
                True,
                "explicit_preference",
                MemoryType.PREFERENCE,
                key,
                value,
                0.98,
            )

        user_location = re.fullmatch(
            r"(?:나는|난|저는|전)\s*(?P<value>.+?)에\s*(?:살아|살고\s*있어)",
            normalized,
        )
        if user_location:
            return StoreDecision(
                True,
                "durable_user_fact",
                MemoryType.LONG_TERM,
                "user.location",
                user_location.group("value").strip(),
                0.97,
            )

        relationship = re.fullmatch(
            r"(?P<name>[가-힣A-Za-z0-9_]+)[은는]\s*"
            r"(?P<value>.+?)(?:에\s*살아|에\s*살고\s*있어)",
            normalized,
        )
        if relationship:
            name = relationship.group("name").strip().lower()
            return StoreDecision(
                True,
                "durable_relationship_fact",
                MemoryType.LONG_TERM,
                f"relationship.{name}.location",
                relationship.group("value").strip(),
                0.95,
            )

        return StoreDecision(False, "ephemeral_or_unclassified")


def parse_preference(text):
    location = re.fullmatch(
        r"(?:앞으로\s*)?기본\s*날씨(?:\s*지역)?(?:은|는|을|를)?\s*"
        r"(?P<value>[가-힣A-Za-z0-9_\-\s]+?)(?:으로|로)\s*해\s*줘",
        text,
    )
    if location:
        return "preference.weather.default_location", location.group("value").strip()
    tts_speed = re.fullmatch(
        r"(?:앞으로\s*)?TTS\s*속도(?:는|를|은|을)?\s*"
        r"(?P<value>\d+(?:\.\d+)?)(?:로)?\s*해\s*줘",
        text,
        flags=re.IGNORECASE,
    )
    if tts_speed:
        return "preference.tts.speed", tts_speed.group("value")
    voice = re.fullmatch(
        r"(?:앞으로\s*)?(?:기본\s*)?(?:목소리|보이스|voice)"
        r"(?:는|를|은|을)?\s*(?P<value>[A-Za-z0-9_-]+?)(?:로)?\s*해\s*줘",
        text,
        flags=re.IGNORECASE,
    )
    if voice:
        return "preference.tts.voice", voice.group("value").lower()
    return None
