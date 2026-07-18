import logging
from datetime import datetime, timedelta

from jarvis.debug_trace import trace_event
from jarvis.native.reminder.queue import ReminderQueue
from jarvis.native.reminder.reminder import REMINDER_PENDING, ReminderEntry


LOGGER = logging.getLogger("jarvis.reminder")


class ReminderEngine:
    """Create, update, cancel, and trigger reminders."""

    def __init__(self, queue=None, notification_callback=None, provider="mock", default_remind_before=30):
        """Create reminder engine."""
        self.queue = queue or ReminderQueue()
        self.notification_callback = notification_callback
        self.provider = provider
        self.default_remind_before = int(default_remind_before)

    def create(
        self,
        title,
        datetime_value,
        remind_before=None,
        source="",
        source_id="",
        calendar_id="",
        recurrence="",
        snooze_until="",
        priority="normal",
    ):
        """Create one pending reminder."""
        normalized_datetime = normalize_datetime_text(datetime_value)
        resolved_calendar_id = calendar_id or (source_id if source == "calendar" else "")
        reminder = ReminderEntry(
            id="",
            title=title,
            datetime=normalized_datetime,
            remind_before=self.default_remind_before if remind_before is None else int(remind_before),
            state=REMINDER_PENDING,
            status=REMINDER_PENDING,
            provider=self.provider,
            source=source,
            source_id=source_id,
            calendar_id=resolved_calendar_id,
            recurrence=recurrence,
            snooze_until=snooze_until,
            priority=priority,
        )
        reminder = self.queue.enqueue(reminder)
        trace_event(
            "reminder.create",
            id=reminder.id,
            title=reminder.title,
            datetime=reminder.datetime,
            trigger_time=reminder.trigger_time,
            status=reminder.status,
            priority=reminder.priority,
            calendar_id=reminder.calendar_id,
        )
        return reminder

    def create_from_calendar_event(self, event, remind_before=None):
        """Create a reminder for one calendar event."""
        event_datetime = combine_event_datetime(event)
        return self.create(
            title=event.title,
            datetime_value=event_datetime,
            remind_before=remind_before,
            source="calendar",
            source_id=event.id,
            calendar_id=event.id,
        )

    def update_from_calendar_event(self, event, remind_before=None):
        """Replace reminders tied to a calendar event."""
        self.delete_by_source("calendar", event.id)
        reminder = self.create_from_calendar_event(event, remind_before=remind_before)
        trace_event("reminder.update", id=reminder.id, source="calendar", source_id=event.id)
        return reminder

    def delete_by_source(self, source, source_id):
        """Cancel reminders by source."""
        cancelled = self.queue.cancel_by_source(source, source_id)
        trace_event("reminder.delete", source=source, source_id=source_id, count=len(cancelled))
        return cancelled

    def update(self, reminder_id, **changes):
        """Patch one reminder by ID."""
        reminder = self.queue.update(reminder_id, **changes)

        if reminder is not None:
            trace_event("reminder.update", id=reminder.id, source=reminder.source, source_id=reminder.source_id)

        return reminder

    def list(self, state=None):
        """List reminders."""
        return self.queue.list(state=state)

    def tick(self, now=None):
        """Trigger due reminders once."""
        current = now or datetime.now()
        due = self.queue.due(current)
        trace_event("reminder.scheduler.tick", now=normalize_datetime_text(current), due=len(due))
        triggered = []

        for reminder in due:
            trace_event("reminder.trigger", id=reminder.id, title=reminder.title)
            LOGGER.info("reminder.triggered id=%s title=%s", reminder.id, reminder.title)
            self.notify(reminder)
            completed = self.queue.complete(reminder.id)
            trace_event("reminder.completed", id=reminder.id)
            LOGGER.info("reminder.completed id=%s", reminder.id)
            triggered.append(completed)

        return triggered

    def notify(self, reminder):
        """Emit one reminder notification."""
        message = reminder_notification_text(reminder)
        trace_event("reminder.notification", id=reminder.id, message=message)

        if self.notification_callback is not None:
            self.notification_callback(message)

        return message


def combine_event_datetime(event):
    """Return ISO datetime from a CalendarEvent-like object."""
    event_date = getattr(event, "date", "")
    event_time = getattr(event, "time", "") or "00:00"

    if len(event_time.split(":")) == 2:
        event_time = f"{event_time}:00"

    return f"{event_date}T{event_time}"


def normalize_datetime_text(value):
    """Return ISO seconds datetime text."""
    if isinstance(value, datetime):
        return value.isoformat(timespec="seconds")

    text = str(value)

    if "T" not in text and " " in text:
        text = text.replace(" ", "T", 1)

    return datetime.fromisoformat(text).isoformat(timespec="seconds")


def reminder_notification_text(reminder):
    """Return a spoken notification for one reminder."""
    if getattr(reminder, "source", "") != "calendar":
        return f"{reminder.title} 알림입니다."

    if reminder.remind_before >= 60 and reminder.remind_before % 60 == 0:
        amount = reminder.remind_before // 60
        before_text = f"{amount}\uc2dc\uac04 \ud6c4"
    else:
        before_text = f"{reminder.remind_before}\ubd84 \ud6c4"

    return f"{before_text} {reminder.title}\uc640\uc758 \uc77c\uc815\uc774 \uc788\uc2b5\ub2c8\ub2e4."


def reminder_notification_text(reminder):
    """Return a spoken notification for one reminder."""
    if getattr(reminder, "source", "") != "calendar":
        return f"{reminder.title} 알림입니다."

    if reminder.remind_before >= 60 and reminder.remind_before % 60 == 0:
        amount = reminder.remind_before // 60
        before_text = f"{amount}시간 후"
    else:
        before_text = f"{reminder.remind_before}분 후"

    return format_calendar_reminder_message(before_text, reminder.title)


def format_calendar_reminder_message(before_text, title):
    """Return a natural calendar reminder message without broken particles."""
    clean_title = str(title or "").strip()

    if clean_title == "":
        return f"{before_text} 일정이 있습니다."

    person = extract_leading_person(clean_title)

    if person:
        return f"{before_text} {person}와의 약속이 있습니다."

    if clean_title == "약속" or clean_title.endswith("약속"):
        return f"{before_text} {clean_title}이 있습니다."

    if clean_title.endswith("일정"):
        return f"{before_text} {clean_title}이 있습니다."

    return f"{before_text} {clean_title} 일정이 있습니다."


def extract_leading_person(title):
    """Return a known leading person name from a calendar title."""
    for person in ["아야", "유이", "유리"]:
        if title.startswith(person) and any(token in title for token in ["만나", "약속", "보기"]):
            return person

    return ""
