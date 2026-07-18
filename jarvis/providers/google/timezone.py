"""Timezone helpers for Google providers."""

from datetime import timezone, timedelta
from zoneinfo import ZoneInfo


def safe_timezone(timezone_name):
    """Return a timezone, falling back when tzdata is unavailable on Windows."""
    name = str(timezone_name or "Asia/Seoul")

    try:
        return ZoneInfo(name)
    except Exception:
        if name in {"Asia/Seoul", "KST"}:
            return timezone(timedelta(hours=9), name="KST")
        if name in {"UTC", "Z"}:
            return timezone.utc
        return timezone.utc
