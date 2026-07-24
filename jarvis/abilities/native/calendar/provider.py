from dataclasses import replace
from typing import Protocol

from jarvis.abilities.native.calendar.filters import ambiguous_calendar_result, apply_calendar_query_filters
from jarvis.abilities.native.calendar.result import CalendarEvent, CalendarResult
from jarvis.abilities.result import AbilityHealth
from jarvis.date_calculator import today


class CalendarProvider(Protocol):
    """Provider boundary for calendar backends."""

    provider_name: str

    def list_events(self, query):
        """Return matching calendar events."""
        ...

    def create_event(self, query):
        """Create one calendar event."""
        ...

    def delete_event(self, query):
        """Delete one calendar event."""
        ...

    def update_event(self, query):
        """Update one calendar event."""
        ...


class MockCalendarProvider:
    """In-memory calendar provider for Sprint 3 tests."""

    provider_name = "mock"

    def __init__(self, events=None):
        """Create provider with deterministic events."""
        self.events = events if events is not None else create_default_events()

    def list_events(self, query):
        """Return events matching query date scope."""
        events = [event for event in self.events if matches_query_date(event, query.date)]
        events.sort(key=lambda event: (event.date, event.time, event.title))
        events = apply_calendar_query_filters(events, query)
        return CalendarResult(
            success=True,
            action="list",
            events=events,
            count=len(events),
            provider=self.provider_name,
            date=query.date,
        )

    def create_event(self, query):
        """Create one event in memory."""
        event = CalendarEvent(
            id=f"mock-{len(self.events) + 1}",
            title=query.title or "새 일정",
            date=query.date or today(),
            time=query.time,
            description=query.description,
            location=query.location,
            participants=list(query.participants),
        )
        self.events.append(event)
        return CalendarResult(success=True, action="create", events=[event], count=1, provider=self.provider_name, date=event.date)

    def delete_event(self, query):
        """Delete events by title substring or date scope when no title is given."""
        title = query.title.strip()
        event_id = str(getattr(query, "event_id", "") or "").strip()
        matches = matching_events(self.events, query)

        if event_id == "" and title != "" and len(matches) > 1:
            return ambiguous_calendar_result(query, self.provider_name, "delete", matches)

        deleted = []
        kept = []

        for event in self.events:
            if event_id != "" and event.id == event_id:
                deleted.append(event)
            elif title == "" and event_id == "" and matches_query_date(event, query.date):
                deleted.append(event)
            elif event_id == "" and title != "" and title in event.title:
                deleted.append(event)
            else:
                kept.append(event)

        self.events[:] = kept
        return CalendarResult(
            success=True,
            action="delete",
            events=deleted,
            count=len(deleted),
            provider=self.provider_name,
            date=query.date,
        )

    def update_event(self, query):
        """Patch matching events with changed fields only."""
        event_id = str(getattr(query, "event_id", "") or "").strip()
        matches = matching_events(self.events, query)

        if event_id == "" and len(matches) > 1:
            return ambiguous_calendar_result(query, self.provider_name, "update", matches)

        updated = []
        kept = []

        for event in self.events:
            if matches_update_target(event, query):
                patched = patch_calendar_event(event, query)
                updated.append(patched)
                kept.append(patched)
            else:
                kept.append(event)

        self.events[:] = kept
        return CalendarResult(
            success=True,
            action="update",
            events=updated,
            count=len(updated),
            provider=self.provider_name,
            date=query.date or first_updated_date(updated),
        )

    def health(self):
        """Return provider health."""
        return AbilityHealth(status="ok", provider=self.provider_name, message="Mock calendar provider is active.")


class GoogleCalendarProvider:
    """Compatibility wrapper for the real Google Calendar provider."""

    provider_name = "google"

    def __new__(cls, *args, **kwargs):
        """Return the real Google provider without changing legacy imports."""
        from jarvis.providers.google.calendar import GoogleCalendarProvider as RealGoogleCalendarProvider

        return RealGoogleCalendarProvider(*args, **kwargs)


def create_calendar_provider(config=None):
    """Create a Calendar provider from runtime config."""
    import os

    provider_name = os.environ.get("JARVIS_CALENDAR_PROVIDER", getattr(config, "provider", "mock") if config else "mock")
    provider_name = str(provider_name or "mock").lower()

    if provider_name == "google":
        from jarvis.providers.google.config import GOOGLE_CALENDAR_SCOPE, GoogleProviderConfig
        from jarvis.providers.google.calendar import GoogleCalendarProvider as RealGoogleCalendarProvider

        google_config = GoogleProviderConfig(
            credentials_path=getattr(config, "google_credentials_path", "data/credentials/google_token.json"),
            client_secret_path=getattr(config, "google_client_secret_path", "client_secret.json"),
            scopes=(GOOGLE_CALENDAR_SCOPE,),
            timezone=getattr(config, "timezone", "Asia/Seoul"),
        )
        return RealGoogleCalendarProvider(config=google_config)

    return MockCalendarProvider()


def create_default_events():
    """Create deterministic mock calendar events."""
    current_date = today()
    return [
        CalendarEvent(id="mock-1", title="회의", date=current_date, time="10:00"),
        CalendarEvent(id="mock-2", title="치과", date=current_date, time="15:00"),
    ]


def matches_query_date(event, query_date):
    """Return whether an event matches a CalendarQuery date scope."""
    if query_date in ["", "today"]:
        return event.date == today()

    if query_date in ["week", "next", "next_week"]:
        return True

    return event.date == query_date


def matches_update_target(event, query):
    """Return whether an event should receive a patch update."""
    event_id = str(getattr(query, "event_id", "") or "").strip()

    if event_id:
        return event.id == event_id

    title = str(getattr(query, "title", "") or "").strip()

    if title:
        return title in event.title

    query_date = str(getattr(query, "date", "") or "").strip()
    return query_date != "" and matches_query_date(event, query_date)


def matching_events(events, query):
    """Return mutation target candidates for a query."""
    return [event for event in events if matches_update_target(event, query)]


def patch_calendar_event(event, query):
    """Return an event patched only with non-empty query fields."""
    changes = {}

    for field in ["date", "time", "title", "description", "location"]:
        value = getattr(query, field, "")

        if str(value or "").strip() != "":
            changes[field] = value

    participants = list(getattr(query, "participants", []) or [])

    if participants:
        changes["participants"] = participants

    return replace(event, **changes)


def first_updated_date(events):
    """Return the first updated event date for result labels."""
    if len(events) == 0:
        return ""

    return events[0].date
