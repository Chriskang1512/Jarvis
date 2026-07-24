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


DATE_TOKENS = {
    "\uc624\ub298": WEATHER_DATE_TODAY,
    "\ub0b4\uc77c": WEATHER_DATE_TOMORROW,
    "\ubaa8\ub808": WEATHER_DATE_DAY_AFTER_TOMORROW,
}
CURRENT_TOKENS = ["\uc9c0\uae08", "\ud604\uc7ac", "\ub2f9\uc7a5"]
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
]
PRECIPITATION_PATTERNS = [
    "\ube44 \uc640",
    "\ube44\uc640",
    "\ube44 \uc624\ub2c8",
    "\ube44\uc624\ub2c8",
    "\uc6b0\uc0b0",
]


class WeatherIntentParser:
    """Parse raw weather text into a WeatherQuery."""

    def __init__(self, default_location=DEFAULT_WEATHER_LOCATION):
        """Create a weather parser with a default location."""
        self.default_location = default_location

    def parse(self, raw_text):
        """Return a WeatherQuery for one raw user request."""
        text = normalize_text(raw_text)
        date = parse_date(text)
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
    if date in [WEATHER_DATE_TOMORROW, WEATHER_DATE_DAY_AFTER_TOMORROW]:
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

    for pattern in PRECIPITATION_PATTERNS:
        cleaned = cleaned.replace(pattern, " ")

    for token in COMMAND_TOKENS:
        cleaned = cleaned.replace(token, " ")

    cleaned = re.sub(r"[?!.,]", " ", cleaned)
    cleaned = " ".join(cleaned.split())

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
    weather_tokens = ["\ub0a0\uc528", "\ube44", "\uc6b0\uc0b0"]
    return any(token in text for token in weather_tokens)


def normalize_text(text):
    """Normalize spacing for Korean weather parsing."""
    return " ".join(str(text).strip().split())
