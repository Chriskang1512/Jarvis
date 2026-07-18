"""Core EventBus handlers."""

from dataclasses import dataclass, field

from jarvis.core.events.event import BaseEvent


@dataclass
class EventHistoryHandler:
    """Keep an in-memory history of handled events."""

    name: str = "HistoryHandler"
    events: list = field(default_factory=list)

    def handle(self, event):
        """Record one event."""
        self.events.append(event)
        return event


@dataclass
class EventMetricsHandler:
    """Count events by type."""

    name: str = "MetricsHandler"
    counts: dict = field(default_factory=dict)

    def handle(self, event):
        """Count one event type."""
        event_type = getattr(event, "event_type", "")
        self.counts[event_type] = int(self.counts.get(event_type, 0)) + 1
        return self.counts[event_type]


class EntityGraphContactHandler:
    """Sync changed contacts into an EntityGraph through the repository."""

    name = "EntityGraphHandler"

    def __init__(self, repository):
        """Create handler."""
        self.repository = repository

    def handle(self, event):
        """Patch one contact node when contact data changes."""
        if getattr(event, "aggregate_type", "") != "contact":
            return None

        contact = self.repository.find_by_id(getattr(event, "aggregate_id", ""))
        if contact is not None:
            return self.repository.sync_entity_graph(contact)
        return None


class ReminderScheduleHandler:
    """Create, update, or delete reminders from calendar events."""

    name = "ReminderScheduleHandler"

    def __init__(self, reminder_engine, event_bus=None):
        """Create handler."""
        self.reminder_engine = reminder_engine
        self.event_bus = event_bus

    def handle(self, event):
        """Synchronize reminders from Calendar events."""
        event_type = getattr(event, "event_type", "")
        payload = dict(getattr(event, "payload", {}) or {})
        events = list(payload.get("events") or [])

        if payload.get("suppress_auto_reminder"):
            return []

        if event_type == "CalendarCreated":
            remind_before = payload.get("remind_before")
            reminders = [
                self.reminder_engine.create_from_calendar_event(as_event_object(item), remind_before=remind_before)
                for item in events
            ]
            self.publish_reminder_events("ReminderCreated", reminders, event)
            return reminders

        if event_type == "CalendarUpdated":
            remind_before = payload.get("remind_before")
            return [self.reminder_engine.update_from_calendar_event(as_event_object(item), remind_before=remind_before) for item in events]

        if event_type == "CalendarDeleted":
            return [self.reminder_engine.delete_by_source("calendar", str(item.get("id", ""))) for item in events]

        if event_type == "TodoCreated":
            todo = dict(payload.get("todo") or {})
            if not todo.get("due_at"):
                return []
            reminder = self.reminder_engine.create(
                title=todo.get("title", ""),
                datetime_value=todo.get("due_at", ""),
                remind_before=0,
                source="todo",
                source_id=todo.get("id", ""),
            )
            self.publish_reminder_events("ReminderCreated", [reminder], event)
            return [reminder]

        if event_type == "TodoUpdated":
            todo = dict(payload.get("todo") or {})
            self.reminder_engine.delete_by_source("todo", todo.get("id", ""))
            if not todo.get("due_at"):
                return []
            reminder = self.reminder_engine.create(
                title=todo.get("title", ""),
                datetime_value=todo.get("due_at", ""),
                remind_before=0,
                source="todo",
                source_id=todo.get("id", ""),
            )
            self.publish_reminder_events("ReminderUpdated", [reminder], event)
            return [reminder]

        if event_type in {"TodoCompleted", "TodoDeleted"}:
            todo = dict(payload.get("todo") or {})
            return self.reminder_engine.delete_by_source("todo", todo.get("id", ""))

        return None

    def publish_reminder_events(self, event_type, reminders, source_event):
        """Publish reminder follow-up events with causation metadata."""
        if self.event_bus is None:
            return []

        published = []

        for reminder in reminders or []:
            event = BaseEvent(
                event_type=event_type,
                aggregate_type="reminder",
                aggregate_id=getattr(reminder, "id", ""),
                trace_id=getattr(source_event, "trace_id", ""),
                correlation_id=getattr(source_event, "correlation_id", ""),
                causation_id=getattr(source_event, "event_id", ""),
                source="reminder",
                payload={"reminder": reminder.to_dict() if hasattr(reminder, "to_dict") else {}},
                metadata={"source_event_type": getattr(source_event, "event_type", "")},
            )
            published.append(self.event_bus.publish(event))

        return published


@dataclass(frozen=True)
class SimpleEventObject:
    """Tiny adapter for event payload dictionaries."""

    id: str
    title: str
    date: str
    time: str = ""
    description: str = ""
    location: str = ""
    participants: tuple = field(default_factory=tuple)


def as_event_object(data):
    """Return an object compatible with ReminderEngine calendar helpers."""
    if hasattr(data, "id"):
        return data

    value = dict(data or {})
    return SimpleEventObject(
        id=str(value.get("id", "")),
        title=str(value.get("title", "")),
        date=str(value.get("date", "")),
        time=str(value.get("time", "")),
        description=str(value.get("description", "")),
        location=str(value.get("location", "")),
        participants=tuple(value.get("participants") or ()),
    )
