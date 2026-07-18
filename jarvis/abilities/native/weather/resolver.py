LOCATION_MAP = {
    "\uac15\ub989": "Gangneung,KR",
    "\uc11c\uc6b8": "Seoul,KR",
    "\uc7a0\uc2e4": "Seoul,KR",
    "\ubd80\uc0b0": "Busan,KR",
    "\uc624\uc0ac\uce74": "Osaka,JP",
}


class WeatherLocationResolver:
    """Resolve user location text to provider-specific city names."""

    def __init__(self, location_map=None):
        """Create a resolver with an optional override map."""
        self.location_map = dict(location_map or LOCATION_MAP)

    def resolve(self, location):
        """Return an OpenWeather-compatible city query."""
        if location is None:
            return None

        normalized = normalize_location(location)
        return self.location_map.get(normalized, normalized)


def normalize_location(location):
    """Normalize user location text for map lookup."""
    return " ".join(str(location).strip().split())

