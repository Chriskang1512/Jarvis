"""Todo Ability query."""

from dataclasses import dataclass


@dataclass(frozen=True)
class TodoQuery:
    """Structured Todo input."""

    action: str = "list"
    todo_id: str = ""
    title: str = ""
    due_at: str = ""
    priority: str = "normal"
    status: str = ""
    date_scope: str = ""
    confirmed: bool = False
    raw_text: str = ""

    def to_input_data(self):
        """Return dispatcher-safe dict."""
        return {
            "action": self.action,
            "todo_id": self.todo_id,
            "title": self.title,
            "due_at": self.due_at,
            "priority": self.priority,
            "status": self.status,
            "date_scope": self.date_scope,
            "confirmed": self.confirmed,
            "raw_text": self.raw_text,
        }
