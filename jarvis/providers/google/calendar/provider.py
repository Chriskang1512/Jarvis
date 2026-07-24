"""Google Calendar provider."""

from datetime import datetime, time, timedelta
from time import perf_counter

from jarvis.abilities.native.calendar.filters import ambiguous_calendar_result, apply_calendar_query_filters
from jarvis.abilities.native.calendar.result import CalendarResult, format_event_detail
from jarvis.date_calculator import today
from jarvis.debug_trace import trace_event
from jarvis.providers.google.client_factory import GoogleClientFactory
from jarvis.providers.google.config import GoogleProviderConfig
from jarvis.providers.google.errors import (
    CREATE_FAILED,
    DELETE_FAILED,
    EVENT_NOT_FOUND,
    GoogleProviderError,
    INVALID_PROVIDER_RESPONSE,
    UPDATE_FAILED,
    google_error_message,
    map_google_exception,
)
from jarvis.providers.google.calendar.mapper import GoogleCalendarMapper
from jarvis.providers.google.timezone import safe_timezone
from jarvis.providers.google.context import GoogleProviderContext


class GoogleCalendarProvider:
    """Google Calendar provider implementing the Calendar provider boundary."""

    provider_name = "google"

    def __init__(self, client=None, client_factory=None, mapper=None, config=None, context=None):
        """Create provider with optional fake client for tests."""
        self.context = context or GoogleProviderContext.create(config=config)
        self.config = self.context.config
        self.client = client
        self.client_factory = client_factory or self.context.client_factory
        self.request_executor = self.context.request_executor
        self.error_mapper = self.context.error_mapper
        self.mapper = mapper or GoogleCalendarMapper(timezone_name=self.config.timezone)

    def list_events(self, query):
        """Return matching Google Calendar events."""
        started = perf_counter()
        trace_event("google_calendar.request", action="list", provider=self.provider_name)

        try:
            window = resolve_query_window(query, self.config.timezone)
            service = self.google_calendar_client()
            request = service.events().list(
                calendarId=self.config.calendar_id,
                timeMin=window["time_min"].isoformat(),
                timeMax=window["time_max"].isoformat() if window["time_max"] is not None else None,
                maxResults=window["limit"],
                singleEvents=True,
                orderBy=window["order_by"],
                timeZone=window["timezone"],
            )
            response = self.execute_google_request(lambda: request)
            events = apply_calendar_query_filters(self.mapper.list_to_calendar_events(response), query)
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
            service = self.google_calendar_client()
            response = self.execute_google_request(
                lambda: service.events().get(calendarId=self.config.calendar_id, eventId=str(event_id))
            )
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
        """Create a Google Calendar event and verify it by re-reading it."""
        started = perf_counter()
        trace_event("google_calendar.request", action="create", provider=self.provider_name)

        try:
            service = self.google_calendar_client()
            body = create_google_event_body(query, self.config.timezone)
            response = self.execute_google_request(
                lambda: service.events().insert(calendarId=self.config.calendar_id, body=body)
            )
            event_id = str(response.get("id") or "")

            if event_id == "":
                raise GoogleProviderError(CREATE_FAILED)

            verified = self.get_event(event_id)

            if not verified.success or len(verified.events) == 0:
                raise GoogleProviderError(CREATE_FAILED)

            event = verified.events[0]

            if not event_matches_query(event, query, require_reminder=True):
                raise GoogleProviderError(INVALID_PROVIDER_RESPONSE)

            trace_event("google_calendar.response", events=1, provider=self.provider_name)
            return CalendarResult(
                success=True,
                action="create",
                events=[event],
                count=1,
                provider=self.provider_name,
                date=event.date,
                message=verified_write_message("create", event),
                execution_time_ms=elapsed_ms(started),
            )
        except GoogleProviderError as error:
            return error_result("create", error, started, getattr(query, "date", ""))
        except Exception as error:
            return error_result("create", map_google_exception(error), started, getattr(query, "date", ""))

    def update_event(self, query):
        """Patch a Google Calendar event and verify it by re-reading it."""
        started = perf_counter()
        trace_event("google_calendar.request", action="update", provider=self.provider_name)

        try:
            service = self.google_calendar_client()
            event_id = resolve_target_event_id(self, query)

            if event_id == "":
                raise GoogleProviderError(EVENT_NOT_FOUND)

            body = update_google_event_body(query, self.config.timezone)

            if not body:
                raise GoogleProviderError(UPDATE_FAILED)

            self.execute_google_request(
                lambda: service.events().patch(calendarId=self.config.calendar_id, eventId=event_id, body=body)
            )
            verified = self.get_event(event_id)

            if not verified.success or len(verified.events) == 0:
                raise GoogleProviderError(UPDATE_FAILED)

            event = verified.events[0]

            if not event_matches_query(event, query, require_reminder=getattr(query, "remind_before_minutes", None) is not None):
                raise GoogleProviderError(INVALID_PROVIDER_RESPONSE)

            trace_event("google_calendar.response", events=1, provider=self.provider_name)
            return CalendarResult(
                success=True,
                action="update",
                events=[event],
                count=1,
                provider=self.provider_name,
                date=event.date,
                message=verified_write_message("update", event),
                execution_time_ms=elapsed_ms(started),
            )
        except GoogleProviderError as error:
            return error_result("update", error, started, getattr(query, "date", ""))
        except Exception as error:
            return error_result("update", map_google_exception(error), started, getattr(query, "date", ""))

    def delete_event(self, query):
        """Delete a Google Calendar event and verify it is gone."""
        started = perf_counter()
        trace_event("google_calendar.request", action="delete", provider=self.provider_name)

        try:
            service = self.google_calendar_client()
            event_id = resolve_target_event_id(self, query)

            if event_id == "":
                raise GoogleProviderError(EVENT_NOT_FOUND)

            try:
                self.execute_google_request(
                    lambda: service.events().delete(calendarId=self.config.calendar_id, eventId=event_id)
                )
            except Exception as error:
                mapped = map_google_exception(error)

                if getattr(mapped, "code", "") == EVENT_NOT_FOUND:
                    trace_event("google_calendar.response", events=0, provider=self.provider_name)
                    return CalendarResult(
                        success=True,
                        action="delete",
                        events=[],
                        count=0,
                        provider=self.provider_name,
                        date=getattr(query, "date", ""),
                        message="일정을 삭제했습니다.",
                        execution_time_ms=elapsed_ms(started),
                    )

                raise

            if not verify_event_deleted(service, self.config.calendar_id, event_id):
                raise GoogleProviderError(DELETE_FAILED)

            trace_event("google_calendar.response", events=0, provider=self.provider_name)
            return CalendarResult(
                success=True,
                action="delete",
                events=[],
                count=1,
                provider=self.provider_name,
                date=getattr(query, "date", ""),
                message="일정을 삭제했습니다.",
                execution_time_ms=elapsed_ms(started),
            )
        except GoogleProviderError as error:
            return error_result("delete", error, started, getattr(query, "date", ""))
        except Exception as error:
            return error_result("delete", map_google_exception(error), started, getattr(query, "date", ""))

    def google_calendar_client(self):
        """Return a Calendar client with read/write capability."""
        return self.client or self.client_factory.calendar_client()

    def execute_google_request(self, request_factory):
        """Execute one Google request through the shared executor."""
        result = self.request_executor.execute(request_factory)

        if result.success:
            return result.response

        raise result.error


def create_google_calendar_provider(config=None, client=None):
    """Create Google Calendar provider from config."""
    return GoogleCalendarProvider(config=config, client=client)


def create_google_event_body(query, timezone_name):
    """Return a Google Calendar event body for create."""
    body = update_google_event_body(query, timezone_name)

    if "summary" not in body:
        body["summary"] = "새 일정"

    if "start" not in body or "end" not in body:
        date_value = str(getattr(query, "date", "") or "")

        if date_value == "":
            raise GoogleProviderError(CREATE_FAILED)

        body["start"] = {"date": date_value}
        body["end"] = {"date": (datetime.fromisoformat(date_value) + timedelta(days=1)).date().isoformat()}

    return body


def update_google_event_body(query, timezone_name):
    """Return a Google Calendar event body for patch."""
    body = {}
    title = str(getattr(query, "title", "") or "").strip()
    description = str(getattr(query, "description", "") or "").strip()
    location = str(getattr(query, "location", "") or "").strip()
    participants = [str(value).strip() for value in getattr(query, "participants", []) or [] if str(value).strip()]

    if title:
        body["summary"] = title

    if description:
        body["description"] = description

    if location:
        body["location"] = location

    if participants:
        attendees = [{"email": value} for value in participants if "@" in value]

        if attendees:
            body["attendees"] = attendees

    date_value = str(getattr(query, "date", "") or "").strip()
    time_value = str(getattr(query, "time", "") or "").strip()

    if date_value and time_value:
        start = combine_query_datetime(date_value, time_value, timezone_name)
        end = start + timedelta(hours=1)
        body["start"] = {"dateTime": start.isoformat(), "timeZone": timezone_name}
        body["end"] = {"dateTime": end.isoformat(), "timeZone": timezone_name}
    elif date_value:
        start_date = datetime.fromisoformat(date_value).date()
        body["start"] = {"date": start_date.isoformat()}
        body["end"] = {"date": (start_date + timedelta(days=1)).isoformat()}

    reminder_minutes = getattr(query, "remind_before_minutes", None)

    if reminder_minutes is not None:
        try:
            minutes = int(reminder_minutes)
        except (TypeError, ValueError) as error:
            raise GoogleProviderError(CREATE_FAILED, cause=error) from error

        body["reminders"] = {
            "useDefault": False,
            "overrides": [
                {
                    "method": "popup",
                    "minutes": minutes,
                }
            ],
        }

    return body


def combine_query_datetime(date_value, time_value, timezone_name):
    """Return an aware datetime from CalendarQuery date/time."""
    tz = safe_timezone(timezone_name or "Asia/Seoul")
    text = f"{date_value}T{time_value}"

    if len(time_value.split(":")) == 2:
        text = f"{text}:00"

    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as error:
        raise GoogleProviderError(CREATE_FAILED, cause=error) from error

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=tz)

    return parsed


def resolve_target_event_id(provider, query):
    """Resolve an update/delete target event id from a query."""
    event_id = str(getattr(query, "event_id", "") or "").strip()

    if event_id:
        return event_id

    result = provider.list_events(query)

    if not result.success:
        return ""

    title = str(getattr(query, "title", "") or "").strip()
    matches = []

    for event in result.events:
        if title == "" or event.title == title or title in event.title:
            matches.append(event)

    if len(matches) > 1:
        action = str(getattr(query, "action", "") or "")
        ambiguous = ambiguous_calendar_result(query, provider.provider_name, action, matches)
        raise GoogleProviderError("AMBIGUOUS_EVENT", ambiguous.message)

    if len(matches) == 1:
        return matches[0].id

    return result.events[0].id if result.events else ""


def event_matches_query(event, query, require_reminder=False):
    """Return whether a re-read event matches the requested write."""
    title = str(getattr(query, "title", "") or "").strip()
    date_value = str(getattr(query, "date", "") or "").strip()
    time_value = str(getattr(query, "time", "") or "").strip()
    reminder_minutes = getattr(query, "remind_before_minutes", None)

    if title and event.title != title:
        return False

    if date_value and event.date != date_value:
        return False

    if time_value and event.time != normalize_time_value(time_value):
        return False

    if require_reminder and reminder_minutes is not None:
        try:
            expected = int(reminder_minutes)
        except (TypeError, ValueError):
            return False

        return expected in [int(value) for value in event.reminder_minutes]

    return True


def verify_event_deleted(service, calendar_id, event_id):
    """Return whether Google reports an event as removed or cancelled."""
    try:
        response = service.events().get(calendarId=calendar_id, eventId=event_id).execute()
    except Exception as error:
        mapped = map_google_exception(error)
        return getattr(mapped, "code", "") == EVENT_NOT_FOUND

    if not isinstance(response, dict):
        return False

    return str(response.get("status") or "").lower() == "cancelled"


def normalize_time_value(value):
    """Normalize HH:MM or HH:MM:SS to HH:MM."""
    parts = str(value or "").split(":")

    if len(parts) >= 2:
        return f"{int(parts[0]):02d}:{int(parts[1]):02d}"

    return str(value or "")


def verified_write_message(action, event):
    """Return a user-facing message after verified Google write."""
    if action == "create":
        return f"일정을 등록했습니다. {format_event_detail(event)}"

    return f"일정을 수정했습니다. {format_event_detail(event)}"


def format_event_time(event):
    """Return a compact Korean event date/time phrase."""
    if event.time:
        return f"{event.date} {event.time}"

    return event.date


def format_reminder_sentence(minutes):
    """Return reminder confirmation sentence suffix."""
    if not minutes:
        return "."

    value = int(minutes[0])

    if value == 1440:
        return ". 하루 전 알림이 설정되어 있습니다."

    if value % 60 == 0:
        return f". {value // 60}시간 전 알림이 설정되어 있습니다."

    return f". {value}분 전 알림이 설정되어 있습니다."


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
        message=getattr(error, "safe_message", "") or google_error_message(code),
        date=date_value,
        execution_time_ms=elapsed_ms(started),
    )


def elapsed_ms(started):
    """Return elapsed ms."""
    return int((perf_counter() - started) * 1000)
