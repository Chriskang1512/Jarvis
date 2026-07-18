"""Map Google Calendar API events to Jarvis Calendar models."""

from datetime import date, datetime, timedelta, timezone

from jarvis.abilities.native.calendar.result import CalendarEvent
from jarvis.providers.google.errors import INVALID_PROVIDER_RESPONSE, GoogleProviderError
from jarvis.providers.google.timezone import safe_timezone


class GoogleCalendarMapper:
    """Convert Google API event dictionaries into internal CalendarEvent objects."""

    def __init__(self, timezone_name="Asia/Seoul"):
        """Create mapper."""
        self.timezone_name = timezone_name or "Asia/Seoul"

    def to_calendar_event(self, item):
        """Return one internal CalendarEvent."""
        if not isinstance(item, dict):
            raise GoogleProviderError(INVALID_PROVIDER_RESPONSE)

        event_id = str(item.get("id") or "")
        summary = str(item.get("summary") or "(제목 없음)")
        start = item.get("start") or {}
        description = str(item.get("description") or "")
        location = str(item.get("location") or "")
        attendees = [attendee_label(attendee) for attendee in item.get("attendees", []) or []]
        attendees = [value for value in attendees if value]

        if "date" in start:
            event_date = parse_google_date(start.get("date"))
            return CalendarEvent(
                id=event_id,
                title=summary,
                date=event_date.isoformat(),
                time="",
                description=description,
                location=location,
                participants=attendees,
            )

        if "dateTime" in start:
            start_dt = parse_google_datetime(start.get("dateTime"), start.get("timeZone") or self.timezone_name)
            local_dt = start_dt.astimezone(safe_timezone(self.timezone_name))
            return CalendarEvent(
                id=event_id,
                title=summary,
                date=local_dt.date().isoformat(),
                time=local_dt.strftime("%H:%M"),
                description=description,
                location=location,
                participants=attendees,
            )

        raise GoogleProviderError(INVALID_PROVIDER_RESPONSE)

    def list_to_calendar_events(self, response):
        """Return internal events from a Google list response."""
        if not isinstance(response, dict) or not isinstance(response.get("items", []), list):
            raise GoogleProviderError(INVALID_PROVIDER_RESPONSE)

        return [self.to_calendar_event(item) for item in response.get("items", [])]


def parse_google_date(value):
    """Parse a Google all-day date."""
    try:
        return date.fromisoformat(str(value or ""))
    except ValueError as error:
        raise GoogleProviderError(INVALID_PROVIDER_RESPONSE, cause=error) from error


def parse_google_datetime(value, timezone_name):
    """Parse Google RFC3339 datetime with a fallback timezone."""
    text = str(value or "")

    if text == "":
        raise GoogleProviderError(INVALID_PROVIDER_RESPONSE)

    if text.endswith("Z"):
        text = text[:-1] + "+00:00"

    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as error:
        raise GoogleProviderError(INVALID_PROVIDER_RESPONSE, cause=error) from error

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=safe_timezone(timezone_name or "Asia/Seoul"))

    return parsed


def google_exclusive_end_display_date(value):
    """Return inclusive display end date for Google all-day exclusive end dates."""
    parsed = parse_google_date(value)
    return parsed - timedelta(days=1)


def attendee_label(attendee):
    """Return a stable attendee label."""
    return str(attendee.get("displayName") or attendee.get("email") or "").strip()
