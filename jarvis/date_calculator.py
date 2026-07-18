import os
from datetime import date, datetime, timedelta, timezone as datetime_timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


DEFAULT_TIMEZONE = "Asia/Seoul"


def get_runtime_timezone():
    """Return the configured runtime timezone."""
    return os.environ.get("JARVIS_TIMEZONE", DEFAULT_TIMEZONE) or DEFAULT_TIMEZONE


def now(timezone=None):
    """Return the current datetime in the configured timezone."""
    timezone_name = timezone or get_runtime_timezone()

    try:
        return datetime.now(ZoneInfo(timezone_name))
    except ZoneInfoNotFoundError:
        return datetime.now(fallback_timezone(timezone_name))


def fallback_timezone(timezone_name):
    """Return a fixed-offset fallback when tzdata is unavailable."""
    if timezone_name in [DEFAULT_TIMEZONE, "KST"]:
        return datetime_timezone(timedelta(hours=9), DEFAULT_TIMEZONE)

    return datetime_timezone.utc


def today(timezone=None):
    """Return today's ISO date in the configured timezone."""
    override = os.environ.get("JARVIS_CURRENT_DATE", "")

    if is_iso_date(override):
        return override

    return now(timezone=timezone).date().isoformat()


def current_time(timezone=None):
    """Return the current local time in the configured timezone."""
    return now(timezone=timezone).time().isoformat(timespec="seconds")


def days_between(date1, date2):
    """Return elapsed days from date1 to date2."""
    start = parse_iso_date(date1)
    end = parse_iso_date(date2)
    return (end - start).days


def elapsed_days_since(start_date, current_date=None, timezone=None):
    """Return elapsed days from start_date to current_date or today."""
    end_date = current_date or today(timezone=timezone)
    return days_between(start_date, end_date)


def parse_iso_date(value):
    """Parse YYYY-MM-DD into a date."""
    if isinstance(value, date):
        return value

    return date.fromisoformat(str(value))


def is_iso_date(value):
    """Return whether the value is an ISO date string."""
    try:
        parse_iso_date(value)
    except (TypeError, ValueError):
        return False

    return True


def format_korean_date(value):
    """Format YYYY-MM-DD as a Korean date string."""
    parsed = parse_iso_date(value)
    return f"{parsed.year}년 {parsed.month}월 {parsed.day}일"
