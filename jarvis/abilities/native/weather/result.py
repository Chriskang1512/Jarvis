from dataclasses import asdict, dataclass

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
    date_label: str = "오늘"
    raw_text: str = ""
    confidence: float = 1.0

    def to_dict(self):
        """Return a serializable weather result."""
        return asdict(self)

    def to_natural_language(self):
        """Return a compact Korean weather response for voice output."""
        if self.mode == WEATHER_MODE_FORECAST:
            text = (
                f"{self.date_label} {self.location} 날씨는 "
                f"{format_number(self.temperature)}도이며 "
                f"{self.condition}입니다. "
                f"체감온도는 {format_number(self.feels_like)}도, "
                f"습도는 {self.humidity}%이고 "
                f"강수확률은 {self.precipitation_probability}%입니다."
            )
            return text

        text = (
            f"현재 {self.location}은 {format_number(self.temperature)}도이며 "
            f"{self.condition}입니다. "
            f"체감온도는 {format_number(self.feels_like)}도, "
            f"습도는 {self.humidity}%이고 "
            f"강수확률은 {self.precipitation_probability}%입니다."
        )
        return text


def format_number(value):
    """Format whole-number floats without a trailing decimal."""
    if float(value).is_integer():
        return str(int(value))

    return str(value)

