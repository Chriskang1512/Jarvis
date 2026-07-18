"""Google Calendar read-only provider."""

from datetime import datetime, time, timedelta
from time import perf_counter

from jarvis.abilities.native.calendar.result import CalendarResult
from jarvis.date_calculator import today
from jarvis.debug_trace import trace_event
from jarvis.providers.google.client_factory import GoogleClientFactory
from jarvis.providers.google.config import GoogleProviderConfig
from jarvis.providers.google.errors import FEATURE_NOT_ENABLED, GoogleProviderError, google_error_message, map_google_exception
from jarvis.providers.google.calendar.mapper import GoogleCalendarMapper
from jarvis.providers.google.timezone import safe_timezone


class GoogleCalendarProvider:
    """Read-only Google Calendar provider implementing the Calendar provider boundary."""

    provider_name = "google"

    def __init__(self, client=None, client_factory=None, mapper=None, config=None):
        """Create provider with optional fake client for tests."""
        self.config = config or GoogleProviderConfig()
        self.client = client
        self.client_factory = client_factory or GoogleClientFactory(config=self.config)
        self.mapper = mapper or GoogleCalendarMapper(timezone_name=self.config.timezone)

    def list_events(self, query):
        """Return matching Google Calendar events."""
        started = perf_counter()
        trace_event("google_calendar.request", action="list", provider=self.provider_name)

        try:
            window = resolve_query_window(query, self.config.timezone)
            service = self.client or self.client_factory.calendar_readonly_client()
            request = service.events().list(
                calendarId=self.config.calendar_id,
                timeMin=window["time_min"].isoformat(),
                timeMax=window["time_max"].isoformat() if window["time_max"] is not None else None,
                maxResults=window["limit"],
                singleEvents=True,
                orderBy=window["order_by"],
                timeZone=window["timezone"],
            )
            response = request.execute()
            events = self.mapper.list_to_calendar_events(response)
            trace_event("google_calendar.response", events=len(events), provider=self.provider_name)
            return CalendarResult(
                success=True,
                action="list",
                events=events,
                count=len(events),
                provider=self.provider_name,
                date=getattr(query, "date", "") or window["date_label"],
                execution_time_ms=elapsed_ms(started),
            )
        except GoogleProviderError as error:
            return error_result("list", error, started, getattr(query, "date", ""))
        except Exception as error:
            return error_result("list", map_google_exception(error), started, getattr(query, "date", ""))

    def get_event(self, event_id):
        """Return one Google Calendar event by ID."""
        started = perf_counter()
        trace_event("google_calendar.request", action="get", provider=self.provider_name)

        try:
            service = self.client or self.client_factory.calendar_readonly_client()
            response = service.events().get(calendarId=self.config.calendar_id, eventId=str(event_id)).execute()
            event = self.mapper.to_calendar_event(response)
            trace_event("google_calendar.response", events=1, provider=self.provider_name)
            return CalendarResult(
                success=True,
                action="get",
                events=[event],
                count=1,
                provider=self.provider_name,
                date=event.date,
                execution_time_ms=elapsed_ms(started),
            )
        except GoogleProviderError as error:
            return error_result("get", error, started)
        except Exception as error:
            return error_result("get", map_google_exception(error), started)

    def create_event(self, query):
        """Block writes in Sprint 17.0."""
        return feature_disabled_result("create", self.provider_name)

    def update_event(self, query):
        """Block writes in Sprint 17.0."""
        return feature_disabled_result("update", self.provider_name)

    def delete_event(self, query):
        """Block writes in Sprint 17.0."""
        return feature_disabled_result("delete", self.provider_name)


def create_google_calendar_provider(config=None, client=None):
    """Create Google Calendar provider from config."""
    return GoogleCalendarProvider(config=config, client=client)


def resolve_query_window(query, timezone_name):
    """Resolve existing CalendarQuery fields into an absolute list window."""
    tz = safe_timezone(timezone_name or "Asia/Seoul")
    now = datetime.now(tz)

    time_min = getattr(query, "time_min", None)
    time_max = getattr(query, "time_max", None)

    if time_min is not None:
        if getattr(time_min, "tzinfo", None) is None:
            time_min = time_min.replace(tzinfo=tz)
        if time_max is not None and getattr(time_max, "tzinfo", None) is None:
            time_max = time_max.replace(tzinfo=tz)
        return {
            "time_min": time_min,
            "time_max": time_max,
            "timezone": getattr(query, "timezone", "") or timezone_name,
            "limit": getattr(query, "limit", None) or 10,
            "order_by": "startTime",
            "date_label": "",
        }

    query_date = str(getattr(query, "date", "") or "")

    if query_date in {"", "today"}:
        start_date = now.date()
        end_date = start_date + timedelta(days=1)
        date_label = today()
    elif query_date == "tomorrow":
        start_date = now.date() + timedelta(days=1)
        end_date = start_date + timedelta(days=1)
        date_label = start_date.isoformat()
    elif query_date == "week":
        start_date = google_calendar_week_start(now.date())
        end_date = start_date + timedelta(days=7)
        date_label = "week"
    elif query_date == "next_week":
        start_date = google_calendar_week_start(now.date()) + timedelta(days=7)
        end_date = start_date + timedelta(days=7)
        date_label = "next_week"
    elif query_date == "next":
        return {
            "time_min": now,
            "time_max": None,
            "timezone": timezone_name,
            "limit": 1,
            "order_by": "startTime",
            "date_label": "next",
        }
    else:
        start_date = datetime.fromisoformat(query_date).date()
        end_date = start_date + timedelta(days=1)
        date_label = start_date.isoformat()

    return {
        "time_min": datetime.combine(start_date, time.min, tzinfo=tz),
        "time_max": datetime.combine(end_date, time.min, tzinfo=tz),
        "timezone": timezone_name,
        "limit": getattr(query, "limit", None) or 10,
        "order_by": "startTime",
        "date_label": date_label,
    }


def google_calendar_week_start(value):
    """Return the Sunday week start used by Google Calendar's default web view."""
    days_since_sunday = (value.weekday() + 1) % 7
    return value - timedelta(days=days_since_sunday)


def error_result(action, error, started, date_value=""):
    """Return a CalendarResult for a safe provider error."""
    code = getattr(error, "code", "PROVIDER_UNAVAILABLE")
    return CalendarResult(
        success=False,
        action=action,
        provider="google",
        error_code=code,
        message=google_error_message(code),
        date=date_value,
        execution_time_ms=elapsed_ms(started),
    )


def feature_disabled_result(action, provider):
    """Return a feature-disabled write result."""
    return CalendarResult(
        success=False,
        action=action,
        provider=provider,
        error_code=FEATURE_NOT_ENABLED,
        message=google_error_message(FEATURE_NOT_ENABLED),
    )


def elapsed_ms(started):
    """Return elapsed ms."""
    return int((perf_counter() - started) * 1000)
