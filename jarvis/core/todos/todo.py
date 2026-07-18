"""Todo domain model."""

from dataclasses import asdict, dataclass, field, replace
from datetime import datetime
import uuid


TODO_ACTIVE = "ACTIVE"
TODO_COMPLETED = "COMPLETED"
TODO_CANCELLED = "CANCELLED"


@dataclass(frozen=True)
class TodoRevision:
    """One immutable Todo revision."""

    revision: int
    timestamp: str
    action: str
    changed_fields: tuple[str, ...] = field(default_factory=tuple)
    snapshot: dict = field(default_factory=dict)

    def to_dict(self):
        """Return a JSON-safe revision."""
        return {
            "revision": self.revision,
            "timestamp": self.timestamp,
            "action": self.action,
            "changed_fields": list(self.changed_fields),
            "snapshot": dict(self.snapshot),
        }


@dataclass(frozen=True)
class Todo:
    """One user task."""

    id: str
    title: str
    status: str = TODO_ACTIVE
    created_at: str = ""
    completed_at: str = ""
    due_at: str = ""
    priority: str = "normal"
    related_calendar_id: str = ""
    related_reminder_id: str = ""
    revision: int = 1
    history: tuple[TodoRevision, ...] = field(default_factory=tuple)
    updated_at: str = ""

    def __post_init__(self):
        """Fill timestamps."""
        now = now_iso()

        if self.created_at == "":
            object.__setattr__(self, "created_at", now)

        if self.updated_at == "":
            object.__setattr__(self, "updated_at", self.created_at or now)

    def with_updates(self, **updates):
        """Return updated copy."""
        normalized = dict(updates)

        if "history" in normalized:
            normalized["history"] = tuple(normalized["history"] or ())

        normalized["revision"] = int(normalized.get("revision", self.revision + 1))
        normalized["updated_at"] = now_iso()
        return replace(self, **normalized)

    def to_dict(self):
        """Return JSON-safe Todo."""
        data = asdict(self)
        data["history"] = [item.to_dict() for item in self.history]
        return data


def new_todo(title, **kwargs):
    """Create a new Todo."""
    return Todo(
        id=str(kwargs.get("id") or new_todo_id()),
        title=normalize_title(title),
        status=str(kwargs.get("status") or TODO_ACTIVE),
        due_at=str(kwargs.get("due_at") or ""),
        priority=str(kwargs.get("priority") or "normal"),
        related_calendar_id=str(kwargs.get("related_calendar_id") or ""),
        related_reminder_id=str(kwargs.get("related_reminder_id") or ""),
    )


def normalize_title(value):
    """Normalize title text."""
    return " ".join(str(value or "").strip().split())


def new_todo_id():
    """Return compact Todo ID."""
    return f"todo-{uuid.uuid4().hex[:8]}"


def now_iso():
    """Return local ISO seconds timestamp."""
    return datetime.now().isoformat(timespec="seconds")
