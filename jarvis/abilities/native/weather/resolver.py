import json
import math
import re
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from threading import RLock
from time import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen


OPENWEATHER_GEOCODING_ENDPOINT = "https://api.openweathermap.org/geo/1.0/direct"


LOCATION_MAP = {
    "\uac15\ub989": ("Gangneung", "KR", 37.7519, 128.8761),
    "gangneung": ("Gangneung", "KR", 37.7519, 128.8761),
    "\u6c5f\u9675": ("Gangneung", "KR", 37.7519, 128.8761),
    "\uc11c\uc6b8": ("Seoul", "KR", 37.5665, 126.9780),
    "seoul": ("Seoul", "KR", 37.5665, 126.9780),
    "\u30bd\u30a6\u30eb": ("Seoul", "KR", 37.5665, 126.9780),
    "\uc7a0\uc2e4": ("Seoul", "KR", 37.5665, 126.9780),
    "\ubd80\uc0b0": ("Busan", "KR", 35.1796, 129.0756),
    "busan": ("Busan", "KR", 35.1796, 129.0756),
    "\u91dc\u5c71": ("Busan", "KR", 35.1796, 129.0756),
    "\uc778\ucc9c": ("Incheon", "KR", 37.4563, 126.7052),
    "incheon": ("Incheon", "KR", 37.4563, 126.7052),
    "\ubaa9\ud3ec": ("Mokpo", "KR", 34.8118, 126.3922),
    "mokpo": ("Mokpo", "KR", 34.8118, 126.3922),
    "\uad11\uc8fc": ("Gwangju", "KR", 35.1595, 126.8526),
    "gwangju": ("Gwangju", "KR", 35.1595, 126.8526),
    "\uc624\uc0ac\uce74": ("Osaka", "JP", 34.6937, 135.5023),
    "osaka": ("Osaka", "JP", 34.6937, 135.5023),
    "\u5927\u962a": ("Osaka", "JP", 34.6937, 135.5023),
    "\u304a\u304a\u3055\u304b": ("Osaka", "JP", 34.6937, 135.5023),
}
LOCATION_DISPLAY_NAMES = {
    "Gangneung": {"ko": "\uac15\ub989", "ja": "\u6c5f\u9675", "en": "Gangneung"},
    "Seoul": {"ko": "\uc11c\uc6b8", "ja": "\u30bd\u30a6\u30eb", "en": "Seoul"},
    "Busan": {"ko": "\ubd80\uc0b0", "ja": "\u91dc\u5c71", "en": "Busan"},
    "Osaka": {"ko": "\uc624\uc0ac\uce74", "ja": "\u5927\u962a", "en": "Osaka"},
}


@dataclass(frozen=True)
class ResolvedWeatherLocation:
    """Canonical weather location independent from user spelling."""

    original: str
    normalized: str
    canonical_name: str
    country_code: str = ""
    provider_query: str = ""
    latitude: float | None = None
    longitude: float | None = None
    resolution_source: str = "passthrough"
    display_names: dict | None = None


class AmbiguousWeatherLocationError(RuntimeError):
    """Raised when geocoding returns multiple distinct places."""


class WeatherLocationCache:
    """Small local JSON cache for successful geocoding results."""

    def __init__(self, path=None, ttl_seconds=30 * 24 * 60 * 60, clock=None):
        self.path = Path(path or "output/cache/weather_locations.json")
        self.ttl_seconds = max(0.0, float(ttl_seconds))
        self.clock = clock or time
        self._lock = RLock()

    def get(self, key):
        with self._lock:
            data = self._read()
        cache_key = normalize_location(key).casefold()
        item = data.get(cache_key)
        if not isinstance(item, dict):
            return None
        cached_at = float(item.get("_cached_at", 0.0) or 0.0)
        if (
            self.ttl_seconds
            and cached_at
            and self.clock() - cached_at > self.ttl_seconds
        ):
            with self._lock:
                data.pop(cache_key, None)
                self._write(data)
            return None
        payload = {key: value for key, value in item.items() if not key.startswith("_")}
        try:
            return ResolvedWeatherLocation(**payload)
        except TypeError:
            return None

    def put(self, key, location):
        with self._lock:
            data = self._read()
            data[normalize_location(key).casefold()] = {
                **asdict(location),
                "_cached_at": self.clock(),
            }
            self._write(data)

    def clear(self):
        """Remove cached geocoding entries without touching other runtime data."""
        with self._lock:
            self._write({})

    def _write(self, data):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        temporary.replace(self.path)

    def _read(self):
        if not self.path.exists():
            return {}
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except (OSError, ValueError):
            return {}


class OpenWeatherGeoResolver:
    """Resolve an unknown place with OpenWeather Direct Geocoding."""

    def __init__(
        self,
        api_key,
        endpoint=OPENWEATHER_GEOCODING_ENDPOINT,
        timeout=5,
        fetcher=None,
    ):
        self.api_key = str(api_key or "")
        self.endpoint = endpoint
        self.timeout = timeout
        self.fetcher = fetcher

    def resolve(self, location):
        if not self.api_key:
            return None
        items = self._fetch(location)
        candidates = deduplicate_geocoding_candidates(items)
        if not candidates:
            return None
        if len(candidates) > 1:
            labels = ", ".join(
                f"{item.get('name', '')},{item.get('country', '')}"
                for item in candidates
            )
            raise AmbiguousWeatherLocationError(
                f"Weather location is ambiguous: {location} -> {labels}"
            )
        item = candidates[0]
        canonical = str(item.get("name", "") or location)
        country = str(item.get("country", ""))
        return ResolvedWeatherLocation(
            original=str(location),
            normalized=normalize_location(location),
            canonical_name=canonical,
            country_code=country,
            provider_query=f"{canonical},{country}" if country else canonical,
            latitude=float(item["lat"]),
            longitude=float(item["lon"]),
            resolution_source="geocoding",
            display_names=location_display_names(canonical, original=location),
        )

    def _fetch(self, location):
        if self.fetcher is not None:
            return self.fetcher(location)
        query = urlencode(
            {
                "q": location,
                "limit": 5,
                "appid": self.api_key,
            }
        )
        try:
            with urlopen(f"{self.endpoint}?{query}", timeout=self.timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                f"OpenWeather geocoding failed: {error.code} {detail}"
            ) from error
        except URLError as error:
            raise RuntimeError(
                f"OpenWeather geocoding failed: {error.reason}"
            ) from error


class WeatherLocationResolver:
    """Resolve multilingual user location text to provider-safe locations."""

    def __init__(self, location_map=None, api_key="", geocoder=None, cache=None):
        """Create a resolver with an optional alias registry."""
        source = location_map or LOCATION_MAP
        self.location_map = {
            normalize_location(key).casefold(): value
            for key, value in dict(source).items()
        }
        self.geocoder = geocoder or (
            OpenWeatherGeoResolver(api_key) if api_key else None
        )
        self.cache = cache or WeatherLocationCache()

    def resolve(self, location):
        """Return the provider query for backward compatibility."""
        resolved = self.resolve_location(location)
        return None if resolved is None else resolved.provider_query

    def resolve_location(self, location):
        """Return canonical metadata for one user-facing location."""
        if location is None:
            return None

        original = str(location)
        normalized = normalize_location(original)
        entry = self.location_map.get(normalized.casefold())
        if entry is None:
            cached = self.cache.get(normalized) if self.cache is not None else None
            if cached is not None:
                return replace(
                    cached,
                    original=original,
                    normalized=normalized,
                    resolution_source="cache",
                )
            geocoded = self.geocoder.resolve(normalized) if self.geocoder else None
            if geocoded is not None:
                if self.cache is not None:
                    self.cache.put(normalized, geocoded)
                return geocoded
            return ResolvedWeatherLocation(
                original=original,
                normalized=normalized,
                canonical_name=normalized,
                provider_query=normalized,
                display_names=location_display_names(normalized, original=original),
            )

        if isinstance(entry, str):
            canonical, separator, country = entry.partition(",")
            latitude = longitude = None
        else:
            canonical, country, latitude, longitude = entry
            separator = "," if country else ""
        provider_query = f"{canonical}{separator}{country}" if separator else canonical
        return ResolvedWeatherLocation(
            original=original,
            normalized=normalized,
            canonical_name=canonical,
            country_code=country,
            provider_query=provider_query,
            latitude=latitude,
            longitude=longitude,
            resolution_source="alias_registry",
            display_names=location_display_names(canonical, original=original),
        )


def location_display_names(canonical, original=""):
    """Return stable UI/voice labels for a canonical weather location."""
    known = LOCATION_DISPLAY_NAMES.get(str(canonical or ""))
    if known is not None:
        return dict(known)
    fallback = str(canonical or original or "")
    return {"ko": fallback, "ja": fallback, "en": fallback}


def normalize_location(location):
    """Remove provider-hostile wrappers while preserving the city spelling."""
    normalized = " ".join(str(location).strip().split())
    lowered = normalized.casefold()
    for prefix in ("in ", "at ", "for ", "from "):
        if lowered.startswith(prefix):
            normalized = normalized[len(prefix):].strip()
            break
    # Korean particles frequently remain attached after intent extraction
    # (for example "오사카의 날씨"). They are grammar, not part of a city name.
    normalized = re.sub(
        r"(?<=[\uac00-\ud7a3])(?:\uc5d0\uc11c|\uc73c\ub85c|\uc758|\uc740|\ub294|\uc774|\uac00|\uc5d0)$",
        "",
        normalized,
    ).strip()
    return normalized


def deduplicate_geocoding_candidates(items):
    """Return distinct geocoding candidates by country and coordinates."""
    unique = {}
    for item in items or []:
        if not isinstance(item, dict) or "lat" not in item or "lon" not in item:
            continue
        key = (
            str(item.get("country", "")).upper(),
            round(float(item["lat"]), 4),
            round(float(item["lon"]), 4),
        )
        unique.setdefault(key, item)
    candidates = list(unique.values())
    merged = []
    for item in candidates:
        country = str(item.get("country", "")).upper()
        name = _geocoding_base_name(item.get("name", ""))
        latitude = float(item["lat"])
        longitude = float(item["lon"])
        duplicate = False
        for existing in merged:
            if country != str(existing.get("country", "")).upper():
                continue
            if name != _geocoding_base_name(existing.get("name", "")):
                continue
            # Direct geocoding may return a city and its administrative "-si"
            # label a few kilometres apart. Treat those as one place.
            lat_delta = (latitude - float(existing["lat"])) * 111.0
            lon_delta = (
                (longitude - float(existing["lon"]))
                * 111.0
                * max(0.2, abs(math.cos(math.radians(latitude))))
            )
            if (lat_delta * lat_delta + lon_delta * lon_delta) ** 0.5 <= 25.0:
                duplicate = True
                break
        if not duplicate:
            merged.append(item)
    return merged


def _geocoding_base_name(name):
    normalized = re.sub(r"[\s_-]+", "", str(name or "").casefold())
    return re.sub(r"(?:city|si)$", "", normalized)
