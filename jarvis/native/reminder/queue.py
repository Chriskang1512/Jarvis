from dataclasses import replace
from datetime import datetime

from jarvis.native.reminder.reminder import REMINDER_CANCELLED, REMINDER_COMPLETED, now_iso


class ReminderQueue:
    """In-memory reminder queue."""

    def __init__(self):
        """Create an empty queue."""
        self._entries = {}

    def enqueue(self, reminder):
        """Add or replace one reminder."""
        duplicate = self.find_duplicate(reminder)

        if duplicate is not None:
            return duplicate

        self._entries[reminder.id] = reminder
        return reminder

    def find_duplicate(self, reminder):
        """Return an equivalent pending reminder when one already exists."""
        for existing in self.list(state="pending"):
            if reminder.calendar_id != "" and existing.calendar_id == reminder.calendar_id:
                return existing

            if existing.title == reminder.title and existing.trigger_time == reminder.trigger_time:
                return existing

        return None

    def list(self, state=None):
        """Return reminders ordered by due time."""
        reminders = list(self._entries.values())

        if state is not None:
            reminders = [reminder for reminder in reminders if reminder.status == state or reminder.state == state]

        return sorted(reminders, key=lambda reminder: (reminder.datetime, reminder.title))

    def get(self, reminder_id):
        """Return a reminder by ID."""
        return self._entries.get(reminder_id)

    def cancel(self, reminder_id):
        """Cancel one reminder by ID."""
        reminder = self._entries.get(reminder_id)

        if reminder is None:
            return None

        cancelled = replace(reminder, state=REMINDER_CANCELLED, status=REMINDER_CANCELLED, updated_at=now_iso())
        self._entries[reminder_id] = cancelled
        return cancelled

    def update(self, reminder_id, **changes):
        """Patch one reminder by ID."""
        reminder = self._entries.get(reminder_id)

        if reminder is None:
            return None

        patch = {key: value for key, value in changes.items() if value not in [None, ""]}

        if len(patch) == 0:
            return reminder

        updated = replace(reminder, **patch, updated_at=now_iso())
        self._entries[reminder_id] = updated
        return updated

    def cancel_by_source(self, source, source_id):
        """Cancel reminders matching a source object."""
        cancelled = []

        for reminder in list(self._entries.values()):
            if reminder.source == source and reminder.source_id == source_id and reminder.status == "pending":
                cancelled.append(self.cancel(reminder.id))

        return [reminder for reminder in cancelled if reminder is not None]

    def due(self, now):
        """Return pending reminders ready to trigger."""
        current = coerce_datetime(now)
        due_reminders = []

        for reminder in self.list(state="pending"):
            reminder_datetime = coerce_datetime(reminder.datetime)

            if int(getattr(reminder, "remind_before", 0) or 0) > 0 and is_due_or_past(reminder_datetime, current):
                continue

            if is_due_or_past(coerce_datetime(reminder.trigger_time or reminder.remind_at), current):
                due_reminders.append(reminder)

        return due_reminders

    def complete(self, reminder_id):
        """Mark one reminder completed."""
        reminder = self._entries.get(reminder_id)

        if reminder is None:
            return None

        completed = replace(reminder, state=REMINDER_COMPLETED, status=REMINDER_COMPLETED, updated_at=now_iso())
        self._entries[reminder_id] = completed
        return completed


def coerce_datetime(value):
    """Return datetime from ISO text or datetime."""
    if isinstance(value, datetime):
        return value

    return datetime.fromisoformat(str(value))


def is_due_or_past(target, current):
    """Return whether target is due while handling timezone-aware timestamps."""
    if getattr(target, "tzinfo", None) is not None and getattr(current, "tzinfo", None) is None:
        current = current.replace(tzinfo=target.tzinfo)

    if getattr(target, "tzinfo", None) is None and getattr(current, "tzinfo", None) is not None:
        target = target.replace(tzinfo=current.tzinfo)

    return target <= current
