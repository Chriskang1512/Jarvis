import json
import os
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen

from jarvis.abilities.result import AbilityHealth
from jarvis.abilities.native.weather.query import WeatherQuery
from jarvis.abilities.native.weather.resolver import WeatherLocationResolver
from jarvis.abilities.native.weather.result import WeatherResult
from jarvis.debug_trace import trace_event


OPENWEATHER_ENDPOINT = "https://api.openweathermap.org/data/2.5/weather"


class WeatherProvider(Protocol):
    """Provider boundary for current weather data."""

    provider_name: str

    def get_current_weather(self, location):
        """Return current weather for one location."""
        ...

    def get_weather(self, query):
        """Return weather for one parsed query."""
        ...

    def health(self):
        """Return provider health."""
        ...


class MockWeatherProvider:
    """Deterministic provider for local development and tests."""

    def __init__(self, result=None, provider_name="mock", default_location=None):
        """Create a mock provider with optional canned result."""
        self.result = result
        self.provider_name = provider_name
        self.default_location = default_location

    def get_current_weather(self, location):
        """Return predictable weather data for one location."""
        return self.get_weather(WeatherQuery(location=location))

    def get_weather(self, query):
        """Return predictable weather data for one parsed query."""
        trace_event(
            "weather.provider",
            provider_requested=self.provider_name,
            provider_used=self.provider_name,
            fallback_used=False,
            fallback_reason="",
            api_key_loaded=False,
            endpoint="mock",
            location=query.location,
            date=query.date,
            mode=query.mode,
            capability=query.capability,
        )
        if self.result is not None:
            return replace_query(self.result, query, provider=self.provider_name)

        location = query.effective_location(self.default_location)
        condition = "맑음"
        precipitation_probability = 10

        if query.capability == "precipitation":
            condition = "비 가능성 낮음"
            precipitation_probability = 20

        return WeatherResult(
            location=location,
            temperature=27.0,
            feels_like=28.0,
            condition=condition,
            humidity=45,
            wind_speed=2.1,
            precipitation_probability=precipitation_probability,
            provider=self.provider_name,
            timestamp=datetime.now().isoformat(timespec="seconds"),
            date=query.date,
            mode=query.mode,
            capability=query.capability,
            date_label=query.date_label,
            raw_text=query.raw_text,
            confidence=query.confidence,
        )

    def health(self):
        """Return mock provider health."""
        return AbilityHealth(
            status="ok",
            provider=self.provider_name,
            message="Mock weather provider is ready.",
        )


class OpenWeatherProvider:
    """Reserved OpenWeather provider boundary for future integration."""

    provider_name = "openweather"

    def __init__(
        self,
        api_key=None,
        endpoint=OPENWEATHER_ENDPOINT,
        lang="kr",
        timeout=5,
        resolver=None,
        default_location=None,
    ):
        """Create an OpenWeather provider using environment-based credentials."""
        self.api_key = api_key or read_env_value("OPENWEATHER_API_KEY")
        self.endpoint = endpoint
        self.lang = lang
        self.timeout = timeout
        self.resolver = resolver or WeatherLocationResolver()
        self.default_location = default_location

    def get_current_weather(self, location):
        """Fetch current weather from OpenWeather and normalize it."""
        return self.get_weather(WeatherQuery(location=location))

    def get_weather(self, query):
        """Fetch weather from OpenWeather and normalize it for the query."""
        effective_location = query.effective_location(self.default_location)
        provider_query = query if query.location else replace(query, location=effective_location)
        resolved_location = self.resolver.resolve(effective_location)
        trace_event(
            "weather.provider",
            provider_requested=self.provider_name,
            provider_used=self.provider_name,
            fallback_used=False,
            fallback_reason="",
            api_key_loaded=self.api_key != "",
            endpoint=self.endpoint,
            location=query.location,
            resolved_location=resolved_location,
            date=query.date,
            mode=query.mode,
            capability=query.capability,
        )
        if self.api_key == "":
            raise ValueError("OPENWEATHER_API_KEY is not set.")

        data = self.fetch_current_weather(resolved_location)
        return normalize_openweather_response(data, query=provider_query)

    def health(self):
        """Return provider configuration health."""
        if self.api_key == "":
            return AbilityHealth(
                status="unconfigured",
                provider=self.provider_name,
                message="OPENWEATHER_API_KEY is not set.",
            )

        return AbilityHealth(
            status="ok",
            provider=self.provider_name,
            message="OpenWeather provider is configured.",
        )

    def fetch_current_weather(self, location):
        """Call the OpenWeather current weather API."""
        query = urlencode(
            {
                "q": location,
                "appid": self.api_key,
                "units": "metric",
                "lang": self.lang,
            }
        )
        url = f"{self.endpoint}?{query}"

        try:
            with urlopen(url, timeout=self.timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"OpenWeather request failed: {error.code} {detail}") from error
        except URLError as error:
            raise RuntimeError(f"OpenWeather request failed: {error.reason}") from error


class WeatherApiProvider:
    """Reserved WeatherAPI provider boundary for future integration."""

    def __init__(self, api_key=None):
        """Create a WeatherAPI provider boundary."""
        self.api_key = api_key or read_env_value("WEATHERAPI_API_KEY")
        self.provider_name = "weatherapi"

    def get_current_weather(self, location):
        """Fail closed until API transport and credentials are configured."""
        return self.get_weather(WeatherQuery(location=location))

    def get_weather(self, query):
        """Fail closed until API transport and credentials are configured."""
        trace_event(
            "weather.provider",
            provider_requested=self.provider_name,
            provider_used=self.provider_name,
            fallback_used=False,
            fallback_reason="not_configured",
            api_key_loaded=self.api_key != "",
            endpoint="weatherapi",
            location=query.location,
            date=query.date,
            mode=query.mode,
            capability=query.capability,
        )
        raise NotImplementedError("WeatherAPI provider is not configured.")

    def health(self):
        """Return provider health before credentials are configured."""
        if self.api_key == "":
            return AbilityHealth(
                status="unconfigured",
                provider=self.provider_name,
                message="WEATHERAPI_API_KEY is not set.",
            )

        return AbilityHealth(
            status="unconfigured",
            provider=self.provider_name,
            message="WeatherAPI provider is not configured.",
        )


class FallbackWeatherProvider:
    """Try a primary provider and fall back to mock when it fails."""

    def __init__(self, primary, fallback=None):
        """Create a fallback provider wrapper."""
        self.primary = primary
        default_location = getattr(primary, "default_location", None)
        self.fallback = fallback or MockWeatherProvider(
            provider_name="mock_fallback",
            default_location=default_location,
        )
        self.provider_name = getattr(primary, "provider_name", "weather")
        self.default_location = default_location

    def get_current_weather(self, location):
        """Return primary weather data or a marked mock fallback result."""
        return self.get_weather(WeatherQuery(location=location))

    def get_weather(self, query):
        """Return primary weather data or a marked mock fallback result."""
        provider_requested = getattr(self.primary, "provider_name", "weather")
        try:
            if hasattr(self.primary, "get_weather"):
                return self.primary.get_weather(query)

            return self.primary.get_current_weather(query.location)
        except Exception as error:
            trace_event(
                "weather.provider",
                provider_requested=provider_requested,
                provider_used=getattr(self.fallback, "provider_name", "mock_fallback"),
                fallback_used=True,
                fallback_reason=str(error),
                api_key_loaded=getattr(self.primary, "api_key", "") != "",
                endpoint=getattr(self.primary, "endpoint", provider_requested),
                location=query.location,
                resolved_location=resolve_provider_location(self.primary, query),
                date=query.date,
                mode=query.mode,
                capability=query.capability,
            )
            fallback_query = query
            if fallback_query.location is None and self.default_location:
                fallback_query = replace(fallback_query, location=self.default_location)

            if hasattr(self.fallback, "get_weather"):
                return self.fallback.get_weather(fallback_query)

            return self.fallback.get_current_weather(fallback_query.location)

    def health(self):
        """Return primary health when possible."""
        if hasattr(self.primary, "health"):
            return self.primary.health()

        return AbilityHealth(status="ok", provider=self.provider_name)


def create_weather_provider(config):
    """Create the configured weather provider."""
    provider_name = str(getattr(config, "provider", "mock")).lower()

    if provider_name == "openweather":
        provider = OpenWeatherProvider(
            lang=getattr(config, "openweather_lang", "kr"),
            default_location=getattr(config, "default_location", None),
        )
        return with_fallback(provider, config)

    if provider_name == "weatherapi":
        provider = WeatherApiProvider()
        return with_fallback(provider, config)

    return MockWeatherProvider(default_location=getattr(config, "default_location", None))


def with_fallback(provider, config):
    """Wrap real providers with mock fallback when enabled."""
    if getattr(config, "fallback_to_mock", True):
        return FallbackWeatherProvider(provider)

    return provider


def resolve_provider_location(provider, query):
    """Resolve location through a provider resolver when available."""
    resolver = getattr(provider, "resolver", None)

    if resolver is None:
        return query.effective_location()

    return resolver.resolve(query.effective_location(getattr(provider, "default_location", None)))


def normalize_openweather_response(data, query=None):
    """Normalize OpenWeather current weather JSON into WeatherResult."""
    query = query or WeatherQuery(location=str(data.get("name", "")))
    weather = first_item(data.get("weather", []))
    main = data.get("main", {})
    wind = data.get("wind", {})

    return WeatherResult(
        location=query.effective_location(str(data.get("name", "")) or None),
        temperature=float(main.get("temp", 0.0)),
        feels_like=float(main.get("feels_like", main.get("temp", 0.0))),
        condition=str(weather.get("description", weather.get("main", ""))),
        humidity=int(main.get("humidity", 0)),
        wind_speed=float(wind.get("speed", 0.0)),
        precipitation_probability=estimate_precipitation_probability(data),
        provider="openweather",
        timestamp=datetime.fromtimestamp(
            int(data.get("dt", datetime.now().timestamp())),
            tz=timezone.utc,
        ).isoformat(),
        date=query.date,
        mode=query.mode,
        capability=query.capability,
        date_label=query.date_label,
        raw_text=query.raw_text,
        confidence=query.confidence,
    )


def estimate_precipitation_probability(data):
    """Estimate precipitation probability from current API precipitation fields."""
    if "rain" in data or "snow" in data:
        return 100

    return 0


def first_item(items):
    """Return the first item from a list, or an empty dict."""
    if len(items) == 0:
        return {}

    return items[0]


def read_env_value(key):
    """Read a secret from process env or local .env without committing it."""
    value = os.getenv(key, "")

    if value != "":
        return value

    env_path = Path(".env")

    if not env_path.exists():
        return ""

    with env_path.open("r", encoding="utf-8") as file:
        for line in file:
            env_key, env_value = parse_env_line(line)

            if env_key == key:
                return env_value

    return ""


def parse_env_line(line):
    """Parse one simple KEY=VALUE line."""
    stripped_line = line.strip()

    if stripped_line == "" or stripped_line.startswith("#") or "=" not in stripped_line:
        return "", ""

    env_key, value = stripped_line.split("=", 1)
    return env_key.strip(), clean_env_value(value)


def clean_env_value(value):
    """Remove simple wrapping quotes from an env value."""
    cleaned_value = value.strip()

    if len(cleaned_value) >= 2 and cleaned_value[0] == cleaned_value[-1]:
        if cleaned_value[0] in ["'", '"']:
            return cleaned_value[1:-1]

    return cleaned_value


def replace_location(result, location):
    """Return a canned result with the requested location."""
    return replace_query(result, WeatherQuery(location=location), provider=result.provider)


def replace_query(result, query, provider=None):
    """Return a canned result with parsed query fields."""
    return WeatherResult(
        location=query.effective_location(),
        temperature=result.temperature,
        feels_like=result.feels_like,
        condition=result.condition,
        humidity=result.humidity,
        wind_speed=result.wind_speed,
        precipitation_probability=result.precipitation_probability,
        provider=provider or result.provider,
        timestamp=result.timestamp,
        date=query.date,
        mode=query.mode,
        capability=query.capability,
        date_label=query.date_label,
        raw_text=query.raw_text,
        confidence=query.confidence,
    )
