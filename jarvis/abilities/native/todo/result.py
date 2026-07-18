"""Todo Ability result."""

from dataclasses import dataclass, field

from jarvis.abilities.result import BaseAbilityResult


@dataclass(frozen=True)
class TodoResult(BaseAbilityResult):
    """Structured Todo result contract."""

    action: str = ""
    todo: object = None
    todos: tuple[object, ...] = field(default_factory=tuple)
    revision: int = 0
    event_id: str = ""
    changed_fields: tuple[str, ...] = field(default_factory=tuple)
    requires_confirmation: bool = False
    message: str = ""
    provider: str = "memory"

    def to_natural_language(self):
        """Return formatted response."""
        from jarvis.abilities.native.todo.formatter import format_todo_result

        return format_todo_result(self)
