import re

from jarvis.abilities.native.weather.query import DEFAULT_WEATHER_LOCATION
from jarvis.abilities.native.weather.query import WEATHER_CAPABILITY_CURRENT
from jarvis.abilities.native.weather.query import WEATHER_CAPABILITY_FORECAST
from jarvis.abilities.native.weather.query import WEATHER_CAPABILITY_PRECIPITATION
from jarvis.abilities.native.weather.query import WEATHER_DATE_DAY_AFTER_TOMORROW
from jarvis.abilities.native.weather.query import WEATHER_DATE_TODAY
from jarvis.abilities.native.weather.query import WEATHER_DATE_TOMORROW
from jarvis.abilities.native.weather.query import WEATHER_MODE_CURRENT
from jarvis.abilities.native.weather.query import WEATHER_MODE_FORECAST
from jarvis.abilities.native.weather.query import WeatherQuery
from jarvis.runtime.date_resolver import DateResolver
from jarvis.runtime.follow_up import DEFAULT_FOLLOW_UP_PHRASE_REGISTRY


DATE_TOKENS = {
    "\uc624\ub298": WEATHER_DATE_TODAY,
    "\ub0b4\uc77c": WEATHER_DATE_TOMORROW,
    "\ubaa8\ub808": WEATHER_DATE_DAY_AFTER_TOMORROW,
    "today": WEATHER_DATE_TODAY,
    "tomorrow": WEATHER_DATE_TOMORROW,
    "day after tomorrow": WEATHER_DATE_DAY_AFTER_TOMORROW,
    "\u4eca\u65e5": WEATHER_DATE_TODAY,
    "\u304d\u3087\u3046": WEATHER_DATE_TODAY,
    "\u660e\u65e5": WEATHER_DATE_TOMORROW,
    "\u3042\u3057\u305f": WEATHER_DATE_TOMORROW,
    "\u660e\u5f8c\u65e5": WEATHER_DATE_DAY_AFTER_TOMORROW,
    "\u3042\u3055\u3063\u3066": WEATHER_DATE_DAY_AFTER_TOMORROW,
}
CURRENT_TOKENS = ["\uc9c0\uae08", "\ud604\uc7ac", "\ub2f9\uc7a5", "now", "current", "\u4eca", "\u3044\u307e"]
COMMAND_TOKENS = [
    "\ub0a0\uc528",
    "\uc54c\ub824\uc918",
    "\uc54c\ub824 \uc918",
    "\ub9d0\ud574\uc918",
    "\ub9d0\ud574 \uc918",
    "\uc5b4\ub54c",
    "\uc5b4\ub5a4\uc9c0",
    "\uc9c0\uae08",
    "\ud604\uc7ac",
    "\ub2f9\uc7a5",
    "\ubc16\uc5d0\ub294",
    "\ubc16\uc5d0",
    "\ubc16\uc740",
    "\ubc16",
    "\uc624\ub298",
    "\ub0b4\uc77c",
    "\ubaa8\ub808",
    "weather",
    "forecast",
    "tell me",
    "what's",
    "what is",
    "how is",
    "the",
    "please",
    "is",
    "like",
    "today",
    "tomorrow",
    "day after tomorrow",
    "\u5929\u6c17",
    "\u5929\u5019",
    "\u4e88\u5831",
    "\u6559\u3048\u3066",
    "\u304a\u3057\u3048\u3066",
    "\u3069\u3046",
    "\u3067\u3059\u304b",
    "\u306f",
    "\u306e",
    "\u3092",
    "\u4eca\u65e5",
    "\u304d\u3087\u3046",
    "\u660e\u65e5",
    "\u3042\u3057\u305f",
    "\u660e\u5f8c\u65e5",
    "\u3042\u3055\u3063\u3066",
]
PRECIPITATION_PATTERNS = [
    "\ube44 \uc640",
    "\ube44\uc640",
    "\ube44 \uc624\ub2c8",
    "\ube44\uc624\ub2c8",
    "\uc6b0\uc0b0",
    "rain",
    "raining",
    "umbrella",
    "\u96e8",
    "\u5098",
]
ENGLISH_FOLLOW_UP_PREFIXES = [
    r"how\s+about",
    r"what\s+about",
    r"and\s+then",
    r"then",
    r"and",
]


class WeatherIntentParser:
    """Parse raw weather text into a WeatherQuery."""

    def __init__(self, default_location=DEFAULT_WEATHER_LOCATION, date_resolver=None):
        """Create a weather parser with a default location."""
        self.default_location = default_location
        self.date_resolver = date_resolver or DateResolver()

    def parse(self, raw_text):
        """Return a WeatherQuery for one raw user request."""
        text = normalize_text(raw_text)
        resolved_date = self.date_resolver.resolve(text)
        date = (
            (
                resolved_date.kind
                if resolved_date.kind in {
                    WEATHER_DATE_TODAY,
                    WEATHER_DATE_TOMORROW,
                    WEATHER_DATE_DAY_AFTER_TOMORROW,
                }
                else resolved_date.start_date
            )
            if resolved_date is not None
            else parse_date(text)
        )
        mode = parse_mode(text, date)
        capability = parse_capability(text, mode)
        location = parse_location(text)
        confidence = calculate_confidence(
            text=text,
            location=location,
            date=date,
            mode=mode,
            capability=capability,
        )

        return WeatherQuery(
            location=location,
            date=date,
            mode=mode,
            capability=capability,
            raw_text=str(raw_text),
            confidence=confidence,
        )


def parse_date(text):
    """Parse Korean date expressions."""
    for token, value in DATE_TOKENS.items():
        if token in text:
            return value

    return WEATHER_DATE_TODAY


def parse_mode(text, date):
    """Parse current vs forecast mode."""
    if date in [WEATHER_DATE_TOMORROW, WEATHER_DATE_DAY_AFTER_TOMORROW] or re.fullmatch(
        r"\d{4}-\d{2}-\d{2}",
        str(date),
    ):
        return WEATHER_MODE_FORECAST

    if any(token in text for token in CURRENT_TOKENS):
        return WEATHER_MODE_CURRENT

    return WEATHER_MODE_CURRENT


def parse_capability(text, mode):
    """Parse finer-grained weather capability."""
    if contains_precipitation_intent(text):
        return WEATHER_CAPABILITY_PRECIPITATION

    if mode == WEATHER_MODE_FORECAST:
        return WEATHER_CAPABILITY_FORECAST

    return WEATHER_CAPABILITY_CURRENT


def parse_location(text):
    """Remove command/date tokens and return only location text."""
    cleaned = text
    # These are discourse markers in a follow-up, not location candidates.
    # Context enrichment may prepend a place ("Osaka How about tomorrow?"),
    # so remove the complete phrase wherever it occurs. Explicit places remain:
    # "How about Busan tomorrow?" -> "Busan".
    cleaned = DEFAULT_FOLLOW_UP_PHRASE_REGISTRY.strip_discourse_markers(
        cleaned
    )
    cleaned = DEFAULT_FOLLOW_UP_PHRASE_REGISTRY.strip_temporal_references(
        cleaned
    )
    cleaned = re.sub(
        r"(?<!\d)\d{1,2}\s*(?:\uc6d4|month)\s*\d{1,2}\s*(?:\uc77c|day)?",
        " ",
        cleaned,
        flags=re.IGNORECASE,
    )

    for pattern in PRECIPITATION_PATTERNS:
        cleaned = cleaned.replace(pattern, " ")

    for token in COMMAND_TOKENS:
        if token.isascii():
            cleaned = re.sub(rf"\b{re.escape(token)}\b", " ", cleaned, flags=re.IGNORECASE)
        else:
            cleaned = cleaned.replace(token, " ")

    cleaned = re.sub(r"[?!.,？！，。]", " ", cleaned)
    cleaned = " ".join(cleaned.split())
    cleaned = re.sub(
        r"(?:^|\s)(?:\uc740|\ub294|\uc774|\uac00|\uc744|\ub97c|\uc758)(?=\s|$)",
        " ",
        cleaned,
    )
    cleaned = " ".join(cleaned.split())
    cleaned = re.sub(
        r"(?<=[\uac00-\ud7a3])(?:\uc5d0\uc11c|\uc73c\ub85c|\uc758|\uc740|\ub294|\uc774|\uac00|\uc5d0)$",
        "",
        cleaned,
    ).strip()
    cleaned = re.sub(r"^(?:in|at|for|from)\s+", "", cleaned, flags=re.IGNORECASE)

    if cleaned == "":
        return None

    return cleaned


def calculate_confidence(text, location, date, mode, capability):
    """Estimate confidence of the parsed WeatherQuery."""
    confidence = 0.55

    if has_weather_intent(text):
        confidence += 0.2

    if location is not None:
        confidence += 0.22

    if date != WEATHER_DATE_TODAY:
        confidence += 0.02

    if mode == WEATHER_MODE_FORECAST:
        confidence += 0.01

    if capability == WEATHER_CAPABILITY_PRECIPITATION:
        confidence += 0.02

    return round(min(confidence, 0.99), 2)


def contains_precipitation_intent(text):
    """Return whether the request is about rain or umbrella need."""
    return any(pattern in text for pattern in PRECIPITATION_PATTERNS)


def has_weather_intent(text):
    """Return whether text contains a weather-related command token."""
    normalized = str(text or "").lower()
    weather_tokens = [
        "\ub0a0\uc528",
        "\ube44",
        "\uc6b0\uc0b0",
        "weather",
        "forecast",
        "rain",
        "umbrella",
        "\u5929\u6c17",
        "\u5929\u5019",
        "\u4e88\u5831",
        "\u96e8",
        "\u5098",
    ]
    return any(token in normalized for token in weather_tokens)


def normalize_text(text):
    """Normalize spacing and case for multilingual weather parsing."""
    return " ".join(str(text).strip().split())
