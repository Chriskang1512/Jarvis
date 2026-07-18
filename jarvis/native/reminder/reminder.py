from dataclasses import asdict, dataclass
from datetime import datetime
from uuid import uuid4


REMINDER_PENDING = "pending"
REMINDER_COMPLETED = "completed"
REMINDER_CANCELLED = "cancelled"


@dataclass(frozen=True)
class ReminderEntry:
    """One scheduled reminder."""

    id: str
    title: str
    datetime: str
    remind_before: int = 30
    state: str = REMINDER_PENDING
    status: str = ""
    provider: str = "mock"
    created_at: str = ""
    updated_at: str = ""
    source: str = ""
    source_id: str = ""
    calendar_id: str = ""
    trigger_time: str = ""
    recurrence: str = ""
    snooze_until: str = ""
    priority: str = "normal"

    def __post_init__(self):
        """Fill derived defaults."""
        if self.id == "":
            object.__setattr__(self, "id", create_reminder_id())

        if self.created_at == "":
            object.__setattr__(self, "created_at", now_iso())

        if self.updated_at == "":
            object.__setattr__(self, "updated_at", self.created_at)

        if self.status == "":
            object.__setattr__(self, "status", self.state)

        if self.state != self.status:
            object.__setattr__(self, "state", self.status)

        if self.calendar_id == "" and self.source == "calendar":
            object.__setattr__(self, "calendar_id", self.source_id)

        if self.trigger_time == "":
            object.__setattr__(self, "trigger_time", self.remind_at)

    @property
    def remind_at(self):
        """Return ISO datetime when this reminder should fire."""
        from datetime import timedelta

        return (datetime.fromisoformat(self.datetime) - timedelta(minutes=self.remind_before)).isoformat(
            timespec="seconds"
        )

    def to_dict(self):
        """Return serializable reminder data."""
        return asdict(self)


def create_reminder_id():
    """Return a compact reminder ID."""
    return f"reminder-{uuid4().hex[:8]}"


def now_iso():
    """Return local timestamp."""
    return datetime.now().isoformat(timespec="seconds")
