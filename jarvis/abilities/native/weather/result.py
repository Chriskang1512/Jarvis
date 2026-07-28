from dataclasses import asdict, dataclass, field
from datetime import datetime

from jarvis.abilities.native.weather.query import WEATHER_MODE_FORECAST


@dataclass(frozen=True)
class WeatherResult:
    """Structured result returned by weather providers."""

    location: str
    temperature: float
    feels_like: float
    condition: str
    humidity: int
    wind_speed: float
    precipitation_probability: int
    provider: str
    timestamp: str
    date: str = "today"
    mode: str = "current"
    capability: str = "current_weather"
    date_label: str = "\uc624\ub298"
    raw_text: str = ""
    confidence: float = 1.0
    temperature_min: float | None = None
    temperature_max: float | None = None
    forecast_at: str = ""
    semantic_type: str = "WeatherReport"
    location_names: dict = field(default_factory=dict)

    def to_dict(self):
        """Return a serializable weather result."""
        return asdict(self)

    def to_natural_language(self, language="ko"):
        """Return a compact localized weather response for voice output."""
        language = str(language or "ko").lower()
        if language == "ja":
            return self._to_japanese()
        if language == "en":
            return self._to_english()
        location = self.localized_location("ko")
        if self.mode == WEATHER_MODE_FORECAST:
            forecast_time = format_forecast_time(self.forecast_at)
            forecast_basis = f"{forecast_time}\uae30\uc900 " if forecast_time else ""
            range_text = ""
            if self.temperature_min is not None and self.temperature_max is not None:
                range_text = (
                    f" \ucd5c\uace0 {format_number(self.temperature_max)}\ub3c4, "
                    f"\ucd5c\uc800 {format_number(self.temperature_min)}\ub3c4\ub85c \uc608\uc0c1\ub429\ub2c8\ub2e4."
                )
            return (
                f"{self.date_label} {location} \ub0a0\uc528\ub294 {forecast_basis}"
                f"{format_number(self.temperature)}\ub3c4, {self.condition}\uc77c \uac83\uc73c\ub85c \uc608\uc0c1\ub429\ub2c8\ub2e4."
                f"{range_text} "
                f"\uac15\uc218\ud655\ub960\uc740 \ucd5c\ub300 {self.precipitation_probability}%\uc785\ub2c8\ub2e4."
            )

        return (
            f"\ud604\uc7ac {location}{topic_particle(location)} "
            f"{format_number(self.temperature)}\ub3c4\uc774\uba70 "
            f"{self.condition}\uc785\ub2c8\ub2e4. "
            f"\uccb4\uac10\uc628\ub3c4\ub294 {format_number(self.feels_like)}\ub3c4, "
            f"\uc2b5\ub3c4\ub294 {self.humidity}%\uc774\uace0 "
            f"\uac15\uc218\ud655\ub960\uc740 {self.precipitation_probability}%\uc785\ub2c8\ub2e4."
        )

    def _to_japanese(self):
        condition = localized_condition(self.condition, "ja")
        location = self.localized_location("ja")
        if self.mode == WEATHER_MODE_FORECAST:
            range_text = ""
            if self.temperature_min is not None and self.temperature_max is not None:
                range_text = (
                    f"\u6700\u9ad8{format_number(self.temperature_max)}\u5ea6\u3001"
                    f"\u6700\u4f4e{format_number(self.temperature_min)}\u5ea6\u306e\u4e88\u60f3\u3067\u3059\u3002"
                )
            label = {
                "today": "\u4eca\u65e5",
                "tomorrow": "\u660e\u65e5",
                "day_after_tomorrow": "\u660e\u5f8c\u65e5",
            }.get(self.date, self.date_label)
            return (
                f"{location}\u306e{label}\u306e\u5929\u6c17\u306f"
                f"{format_number(self.temperature)}\u5ea6\u3001"
                f"{condition}\u306e\u4e88\u60f3\u3067\u3059\u3002{range_text}"
                f"\u964d\u6c34\u78ba\u7387\u306f\u6700\u5927{self.precipitation_probability}%\u3067\u3059\u3002"
            )
        return (
            f"\u73fe\u5728\u306e{location}\u306f{format_number(self.temperature)}\u5ea6\u3001"
            f"{condition}\u3067\u3059\u3002\u4f53\u611f\u6e29\u5ea6\u306f"
            f"{format_number(self.feels_like)}\u5ea6\u3001\u6e7f\u5ea6\u306f{self.humidity}%\u3001"
            f"\u964d\u6c34\u78ba\u7387\u306f{self.precipitation_probability}%\u3067\u3059\u3002"
        )

    def _to_english(self):
        condition = localized_condition(self.condition, "en")
        location = self.localized_location("en")
        if self.mode == WEATHER_MODE_FORECAST:
            range_text = ""
            if self.temperature_min is not None and self.temperature_max is not None:
                range_text = (
                    f" The high will be {format_number(self.temperature_max)}°C "
                    f"and the low {format_number(self.temperature_min)}°C."
                )
            label = {
                "today": "Today",
                "tomorrow": "Tomorrow",
                "day_after_tomorrow": "The day after tomorrow",
            }.get(self.date, self.date_label)
            return (
                f"{label} in {location}, expect {condition} around "
                f"{format_number(self.temperature)}°C.{range_text} "
                f"The maximum chance of rain is {self.precipitation_probability}%."
            )
        return (
            f"It is currently {format_number(self.temperature)}°C in {location} "
            f"with {condition}. It feels like {format_number(self.feels_like)}°C, "
            f"humidity is {self.humidity}%, and the chance of rain is "
            f"{self.precipitation_probability}%."
        )

    def localized_location(self, language):
        """Return the resolved display label for the requested response language."""
        return str(self.location_names.get(language) or self.location)


def format_number(value):
    """Format whole-number floats without a trailing decimal."""
    if float(value).is_integer():
        return str(int(value))
    return str(value)


def topic_particle(value):
    """Return the Korean topic particle 은/는 for a place name."""
    text = str(value or "").strip()
    if not text:
        return "\uc740"
    last = ord(text[-1])
    if 0xAC00 <= last <= 0xD7A3:
        return "\uc740" if (last - 0xAC00) % 28 else "\ub294"
    return "\uc740"


def localized_condition(value, language):
    """Translate common provider conditions without an LLM round trip."""
    condition = str(value or "").strip()
    key = condition.casefold().replace(" ", "")
    aliases = {
        "\ub9d1\uc74c": ("晴れ", "clear skies"),
        "\uad6c\ub984\uc870\uae08": ("晴れ時々曇り", "a few clouds"),
        "\ud750\ub9bc": ("曇り", "cloudy skies"),
        "\uc628\ud750\ub9bc": ("曇り", "overcast skies"),
        "\ube44": ("雨", "rain"),
        "\uac15\ud55c\ube44": ("\u5927\u96e8", "heavy rain"),
        "\uc57d\ud55c\ube44": ("\u5c0f\u96e8", "light rain"),
        "\ubcf4\ud1b5\ube44": ("\u96e8", "moderate rain"),
        "\uc2e4\ube44": ("\u5c0f\u96e8", "drizzle"),
        "\ud3ed\uc6b0": ("\u8c6a\u96e8", "heavy rain"),
        "\uc18c\ub098\uae30": ("にわか雨", "showers"),
        "\ub208": ("雪", "snow"),
        "\uc548\uac1c": ("霧", "fog"),
        "clear": ("晴れ", "clear skies"),
        "clouds": ("曇り", "cloudy skies"),
        "rain": ("雨", "rain"),
        "snow": ("雪", "snow"),
        "mist": ("霧", "mist"),
    }
    japanese, english = aliases.get(key, (condition, condition))
    return japanese if language == "ja" else english


def format_forecast_time(value):
    """Return a user-facing local forecast time label."""
    if not value:
        return ""
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return ""
    period = "\uc624\uc804" if parsed.hour < 12 else "\uc624\ud6c4"
    hour = parsed.hour % 12 or 12
    return f"{period} {hour}\uc2dc "
