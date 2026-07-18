"""Todo repository."""

from dataclasses import dataclass
from datetime import datetime

from jarvis.core.events import BaseEvent
from jarvis.core.todos.todo import TODO_ACTIVE, TODO_CANCELLED, TODO_COMPLETED, TodoRevision, new_todo, now_iso


@dataclass
class TodoRepositoryMetrics:
    """Todo counters."""

    todo_created: int = 0
    todo_completed: int = 0
    todo_deleted: int = 0
    todo_updated: int = 0
    todo_list: int = 0
    total_execution_ms: int = 0
    execution_count: int = 0

    @property
    def average_execution_ms(self):
        """Return average execution time."""
        if self.execution_count == 0:
            return 0
        return int(self.total_execution_ms / self.execution_count)

    def to_dict(self):
        """Return metrics dict."""
        return {
            "todo_created": self.todo_created,
            "todo_completed": self.todo_completed,
            "todo_deleted": self.todo_deleted,
            "todo_updated": self.todo_updated,
            "todo_list": self.todo_list,
            "average_execution_ms": self.average_execution_ms,
        }


class TodoRepository:
    """In-memory Todo repository with EventBus publication."""

    provider_name = "memory"

    def __init__(self, event_bus=None):
        """Create repository."""
        self.todos = {}
        self.events = []
        self.event_bus = event_bus
        self.metrics = TodoRepositoryMetrics()
        self.last_visible_todo_ids = ()
        self.last_visible_status = ""
        self.last_visible_date_scope = ""

    def create(self, title, due_at="", priority="normal", correlation_id="", trace_id=""):
        """Create one todo."""
        todo = new_todo(title, due_at=due_at, priority=priority)
        todo = self.record_revision(todo, "created", ("id", "title", "due_at", "priority"))
        self.todos[todo.id] = todo
        self.metrics.todo_created += 1
        self.publish("TodoCreated", todo, ("id", "title", "due_at", "priority"), correlation_id, trace_id)
        return todo

    def update(self, todo_id, **changes):
        """Patch one todo."""
        todo = self.find(todo_id)

        if todo is None:
            return None

        changed = changed_fields(todo, changes)
        updated = todo.with_updates(**{key: value for key, value in changes.items() if value not in [None, ""]})
        updated = self.record_revision(updated, "updated", changed)
        self.todos[updated.id] = updated
        self.metrics.todo_updated += 1
        self.publish("TodoUpdated", updated, changed, changes.get("correlation_id", ""), changes.get("trace_id", ""))
        return updated

    def complete(self, todo_id, correlation_id="", trace_id=""):
        """Mark one todo complete."""
        todo = self.find(todo_id)

        if todo is None:
            return None

        updated = todo.with_updates(status=TODO_COMPLETED, completed_at=now_iso())
        updated = self.record_revision(updated, "completed", ("status", "completed_at"))
        self.todos[updated.id] = updated
        self.metrics.todo_completed += 1
        self.publish("TodoCompleted", updated, ("status", "completed_at"), correlation_id, trace_id)
        return updated

    def delete(self, todo_id, correlation_id="", trace_id=""):
        """Cancel one todo."""
        todo = self.find(todo_id)

        if todo is None:
            return None

        updated = todo.with_updates(status=TODO_CANCELLED)
        updated = self.record_revision(updated, "deleted", ("status",))
        self.todos[updated.id] = updated
        self.metrics.todo_deleted += 1
        self.publish("TodoDeleted", updated, ("status",), correlation_id, trace_id)
        return updated

    def restore(self, todo_id):
        """Restore a cancelled todo to active."""
        todo = self.find(todo_id)

        if todo is None:
            return None

        updated = todo.with_updates(status=TODO_ACTIVE, completed_at="")
        updated = self.record_revision(updated, "restored", ("status", "completed_at"))
        self.todos[updated.id] = updated
        self.publish("TodoRestored", updated, ("status", "completed_at"), "", "")
        return updated

    def list(self, status=None, date_scope=""):
        """List todos."""
        self.metrics.todo_list += 1
        todos = list(self.todos.values())

        if status:
            todos = [todo for todo in todos if todo.status == status]
        else:
            todos = [todo for todo in todos if todo.status != TODO_CANCELLED]

        if date_scope:
            todos = [todo for todo in todos if matches_date_scope(todo, date_scope)]

        return sorted(todos, key=lambda item: item.created_at)

    def find(self, todo_id):
        """Find by ID."""
        return self.todos.get(str(todo_id or ""))

    def remember_visible_list(self, todos, status="", date_scope=""):
        """Remember the last list shown to the user for ordinal references."""
        self.last_visible_todo_ids = tuple(getattr(todo, "id", "") for todo in todos or ())
        self.last_visible_status = str(status or "")
        self.last_visible_date_scope = str(date_scope or "")

    def last_visible_todos(self):
        """Return the last todos shown to the user."""
        return tuple(todo for todo in (self.find(todo_id) for todo_id in self.last_visible_todo_ids) if todo is not None)

    def find_by_title(self, title):
        """Find the first todo containing title text."""
        needle = normalize_search(title)

        for todo in self.list():
            if needle and needle in normalize_search(todo.title):
                return todo

        return None

    def first_active(self):
        """Return first active todo."""
        active = self.list(status=TODO_ACTIVE)
        return active[0] if active else None

    def history(self, todo_id):
        """Return todo history."""
        todo = self.find(todo_id)
        return list(todo.history) if todo else []

    def record_revision(self, todo, action, changed):
        """Append one revision snapshot."""
        snapshot = todo.to_dict()
        snapshot.pop("history", None)
        revision = TodoRevision(
            revision=todo.revision,
            timestamp=now_iso(),
            action=action,
            changed_fields=tuple(changed or ()),
            snapshot=snapshot,
        )
        return todo.with_updates(revision=todo.revision, history=(*todo.history, revision))

    def publish(self, event_type, todo, changed_fields, correlation_id, trace_id):
        """Publish a Todo event."""
        event = BaseEvent(
            event_type=event_type,
            aggregate_type="todo",
            aggregate_id=todo.id,
            revision=todo.revision,
            idempotency_key=f"{event_type}:{todo.id}:r{todo.revision}",
            trace_id=trace_id,
            correlation_id=correlation_id,
            source="todo_repository",
            payload={"todo": todo.to_dict(), "changed_fields": list(changed_fields or ())},
            metadata={"provider": self.provider_name},
        )
        self.events.append(event)

        if self.event_bus is not None:
            self.event_bus.publish(event)

        return event


def changed_fields(todo, changes):
    """Return changed field names."""
    changed = []

    for key, value in (changes or {}).items():
        if key in {"correlation_id", "trace_id"}:
            continue
        if value in [None, ""]:
            continue
        if getattr(todo, key, None) != value:
            changed.append(key)

    return tuple(changed or ("revision",))


def matches_date_scope(todo, date_scope):
    """Return whether a todo matches a date scope."""
    if date_scope == "":
        return True

    if todo.due_at == "":
        return date_scope in {"today", "active"}

    due_date = todo.due_at.split("T", 1)[0]
    today = datetime.now().date()

    if date_scope == "today":
        return due_date == today.isoformat()
    if date_scope == "tomorrow":
        from datetime import timedelta

        return due_date == (today + timedelta(days=1)).isoformat()

    return due_date == date_scope


def normalize_search(value):
    """Normalize text for title matching."""
    return str(value or "").replace(" ", "").lower()
