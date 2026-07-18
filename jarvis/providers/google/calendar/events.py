"""Google Calendar event model helpers for future EventBus publishing."""

from jarvis.core.events import BaseEvent


GOOGLE_CALENDAR_AUTH_CHANGED = "GoogleCalendarAuthChanged"
GOOGLE_PROVIDER_FAILED = "GoogleProviderFailed"
GOOGLE_CALENDAR_READ_COMPLETED = "GoogleCalendarReadCompleted"


def google_calendar_read_completed(provider, count, trace_id="", correlation_id=""):
    """Create a GoogleCalendarReadCompleted event."""
    return BaseEvent(
        event_type=GOOGLE_CALENDAR_READ_COMPLETED,
        aggregate_type="google_calendar",
        aggregate_id="primary",
        revision=0,
        trace_id=trace_id,
        correlation_id=correlation_id,
        source=provider,
        payload={"provider": provider, "count": int(count or 0)},
    )


def google_provider_failed(provider, error_code, trace_id="", correlation_id=""):
    """Create a GoogleProviderFailed event."""
    return BaseEvent(
        event_type=GOOGLE_PROVIDER_FAILED,
        aggregate_type="google_provider",
        aggregate_id=provider,
        revision=0,
        trace_id=trace_id,
        correlation_id=correlation_id,
        source=provider,
        payload={"provider": provider, "error_code": error_code},
    )
