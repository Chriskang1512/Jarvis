from dataclasses import dataclass


WEATHER_DATE_TODAY = "today"
WEATHER_DATE_TOMORROW = "tomorrow"
WEATHER_DATE_DAY_AFTER_TOMORROW = "day_after_tomorrow"
WEATHER_MODE_CURRENT = "current"
WEATHER_MODE_FORECAST = "forecast"
WEATHER_CAPABILITY_CURRENT = "current_weather"
WEATHER_CAPABILITY_FORECAST = "forecast"
WEATHER_CAPABILITY_PRECIPITATION = "precipitation"
DEFAULT_WEATHER_LOCATION = "\ud604\uc7ac \uc704\uce58"


@dataclass(frozen=True)
class WeatherQuery:
    """Parsed Weather Ability query."""

    location: str | None
    date: str = WEATHER_DATE_TODAY
    mode: str = WEATHER_MODE_CURRENT
    capability: str = WEATHER_CAPABILITY_CURRENT
    raw_text: str = ""
    confidence: float = 1.0

    @property
    def date_label(self):
        """Return a Korean label for the parsed date."""
        return date_label(self.date)

    def effective_location(self, default_location=DEFAULT_WEATHER_LOCATION):
        """Return location with a provider-safe fallback."""
        if self.location is None or self.location == "":
            if default_location is None or default_location == "":
                return DEFAULT_WEATHER_LOCATION

            return default_location

        return self.location


def date_label(date):
    """Return a Korean date label."""
    if date == WEATHER_DATE_TOMORROW:
        return "\ub0b4\uc77c"

    if date == WEATHER_DATE_DAY_AFTER_TOMORROW:
        return "\ubaa8\ub808"

    return "\uc624\ub298"
