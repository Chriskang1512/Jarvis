import json
from pathlib import Path

from jarvis.abilities.metadata import AbilityMetadata, AbilityType
from jarvis.abilities.native.weather.parser import WeatherIntentParser
from jarvis.abilities.native.weather.provider import MockWeatherProvider
from jarvis.abilities.result import AbilityHealth, AbilityResult
from jarvis.debug_trace import trace_event
from jarvis.permissions import PermissionLevel


class WeatherAbility:
    """Native ability that asks a weather provider for current conditions."""

    def __init__(self, provider=None, metadata=None):
        """Create Weather with a replaceable provider."""
        self.provider = provider or MockWeatherProvider()
        self.metadata = metadata or load_weather_metadata()
        self.parser = WeatherIntentParser()

    @property
    def id(self):
        """Return the stable ability ID."""
        return self.metadata.id

    @property
    def name(self):
        """Return the display ability name."""
        return self.metadata.name

    @property
    def type(self):
        """Return the ability execution type."""
        return self.metadata.type

    @property
    def description(self):
        """Return the ability description."""
        return self.metadata.description

    @property
    def permission(self):
        """Return the required permission level."""
        return self.metadata.permission

    def execute(self, input_data):
        """Return current weather from the configured provider."""
        try:
            query = normalize_query(input_data, parser=self.parser)
            trace_event(
                "weather.query",
                location=query.location,
                date=query.date,
                mode=query.mode,
                capability=query.capability,
                confidence=query.confidence,
                raw_text=query.raw_text,
            )
            weather = self.provider.get_weather(query)
            trace_event(
                "weather.result",
                provider_used=weather.provider,
                location=weather.location,
                date=weather.date,
                mode=weather.mode,
                capability=weather.capability,
                success=True,
            )
            return AbilityResult(
                success=True,
                data=weather,
                metadata={
                    "ability_id": self.id,
                    "provider": weather.provider,
                    "query": query,
                },
            )
        except Exception as error:
            return AbilityResult(
                success=False,
                error=str(error),
                metadata={
                    "ability_id": self.id,
                },
            )

    def health(self):
        """Return Weather provider health."""
        if hasattr(self.provider, "health"):
            return self.provider.health()

        return AbilityHealth(
            status="ok",
            provider=getattr(self.provider, "provider_name", ""),
            message="Weather provider has no explicit health check.",
        )


def load_weather_metadata():
    """Load Weather metadata from the package manifest."""
    manifest_path = Path(__file__).with_name("manifest.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    return AbilityMetadata(
        id=manifest["id"],
        name=manifest["name"],
        type=AbilityType(manifest["type"]),
        permission=PermissionLevel(manifest["permission"]),
        version=manifest["version"],
        author=manifest.get("author", "Jarvis"),
        description=manifest["description"],
        capabilities=list(manifest.get("capabilities", [])),
        input_schema=dict(manifest.get("input_schema", {})),
        output_schema=manifest.get("output_schema", "WeatherResult"),
        aliases=["weather", "forecast", "날씨", "비", "우산"],
        supported_intents=[
            "weather",
            "forecast",
            "current weather",
            "오늘 날씨 알려줘",
            "비 오니",
            "우산 가져가야 해",
            "오늘 덥나",
        ],
        examples=[
            "오늘 날씨 알려줘",
            "날씨 알려줘",
            "비 오니",
            "우산 가져가야 해",
            "오늘 덥나",
        ],
        input_prefixes=[
            "weather",
            "forecast",
            "weather in",
            "forecast for",
            "날씨",
            "오늘 날씨",
        ],
    )


def normalize_location(input_data):
    """Extract a location from ToolRouter or direct ability input."""
    return normalize_query(input_data).location


def normalize_query(input_data, parser=None):
    """Return a WeatherQuery from direct query or ToolRouter input."""
    if hasattr(input_data, "location") and hasattr(input_data, "mode"):
        return input_data

    parser = parser or WeatherIntentParser()
    raw_text = input_data.get("raw_text") or input_data.get("text") or input_data.get("location") or input_data.get("key")

    if raw_text is None:
        raw_text = ""

    return parser.parse(str(raw_text))


def clean_location(text):
    """Remove common request words when the user omitted a concrete place."""
    request_words = [
        "알려줘",
        "어때",
        "오늘",
        "현재",
        "날씨",
        "비 오니",
        "우산 가져가야 해",
        "덥나",
    ]
    cleaned = text

    for word in request_words:
        cleaned = cleaned.replace(word, "")

    return cleaned.strip()


def create_ability(provider=None):
    """Create the native Weather ability."""
    return WeatherAbility(provider=provider)
