"""Native Todo Ability."""

import json
import re
from pathlib import Path
from time import perf_counter

from jarvis.abilities.metadata import AbilityMetadata, AbilityType
from jarvis.abilities.native.todo.formatter import confirmation_message
from jarvis.abilities.native.todo.parser import TodoIntentParser, normalize_query
from jarvis.abilities.native.todo.result import TodoResult
from jarvis.abilities.result import AbilityHealth, AbilityResult
from jarvis.core.todos import TODO_ACTIVE, TODO_COMPLETED, TodoRepository
from jarvis.debug_trace import trace_event
from jarvis.permissions import PermissionLevel


CONFIRM_REQUIRED_ACTIONS = {"create", "update", "delete", "complete", "restore"}
TARGET_REQUIRED_ACTIONS = {"update", "delete", "complete", "restore"}


class TodoAbility:
    """Todo Ability backed by TodoRepository."""

    def __init__(self, repository=None, metadata=None, parser=None):
        """Create TodoAbility."""
        self.repository = repository or TodoRepository()
        self.metadata = metadata or load_todo_metadata()
        self.parser = parser or TodoIntentParser()

    @property
    def id(self):
        """Return ability ID."""
        return self.metadata.id

    def execute(self, input_data):
        """Execute Todo action."""
        started = perf_counter()

        try:
            query = normalize_query(input_data, self.parser)
            correlation_id = extract_correlation_id(input_data)
            trace_event("todo.query", action=query.action, title=query.title, due_at=query.due_at, status=query.status)

            if query.action in TARGET_REQUIRED_ACTIONS and not query.confirmed and not self.has_target(query):
                result = TodoResult(
                    success=False,
                    action=query.action,
                    error_code="todo_not_found",
                    provider=self.repository.provider_name,
                    correlation_id=correlation_id,
                    execution_time_ms=elapsed_ms(started),
                )
                trace_event(
                    "todo.result",
                    action=result.action,
                    success=result.success,
                    todo_id="",
                    error_code=result.error_code,
                    provider=result.provider,
                    execution_time_ms=result.execution_time_ms,
                )
                return AbilityResult(
                    success=False,
                    data=result,
                    error=result.to_natural_language(),
                    metadata={"ability_id": self.id, "query": query},
                )

            if query.action in CONFIRM_REQUIRED_ACTIONS and not query.confirmed:
                trace_event("todo.permission", action=query.action, permission="confirm_required")
                result = TodoResult(
                    success=True,
                    action=query.action,
                    requires_confirmation=True,
                    message=confirmation_message(query.action),
                    provider=self.repository.provider_name,
                    correlation_id=correlation_id,
                    execution_time_ms=elapsed_ms(started),
                )
                return AbilityResult(
                    success=True,
                    data=result,
                    metadata={"ability_id": self.id, "query": query, "permission": "confirm_required"},
                )

            result = self.execute_query(query, correlation_id, extract_trace_id(input_data))
            result = attach_runtime_fields(result, self.repository.provider_name, correlation_id, elapsed_ms(started))
            trace_event(
                "todo.result",
                action=result.action,
                success=result.success,
                todo_id=getattr(result.todo, "id", ""),
                error_code=result.error_code,
                provider=result.provider,
                execution_time_ms=result.execution_time_ms,
            )
            return AbilityResult(
                success=result.success,
                data=result,
                error=result.to_natural_language() if not result.success else "",
                metadata={"ability_id": self.id, "query": query},
            )
        except Exception as error:
            return AbilityResult(success=False, error=str(error), metadata={"ability_id": self.id})

    def execute_query(self, query, correlation_id="", trace_id=""):
        """Execute one TodoQuery."""
        if query.action == "create":
            if query.title == "":
                return TodoResult(success=False, action="create", error_code="title_required")
            todo = self.repository.create(query.title, due_at=query.due_at, priority=query.priority, correlation_id=correlation_id, trace_id=trace_id)
            return self.todo_result("create", todo, ("id", "title", "due_at"))

        if query.action == "list":
            status = query.status or None
            todos = tuple(self.repository.list(status=status, date_scope=query.date_scope))
            self.repository.remember_visible_list(todos, status=query.status, date_scope=query.date_scope)
            return TodoResult(success=True, action="list", todos=todos)

        if query.action == "complete":
            todos = self.resolve_todos(query)

            if len(todos) > 1:
                completed_items = tuple(
                    self.repository.complete(todo.id, correlation_id=correlation_id, trace_id=trace_id)
                    for todo in todos
                )
                completed_items = tuple(todo for todo in completed_items if todo is not None)
                for todo in completed_items:
                    trace_event("todo.completed", id=todo.id, title=todo.title)
                return self.todos_result("complete", completed_items, ("status", "completed_at"))

            todo = todos[0] if todos else None

            if todo is None:
                return TodoResult(success=False, action="complete", error_code="todo_not_found")
            completed = self.repository.complete(todo.id, correlation_id=correlation_id, trace_id=trace_id)
            trace_event("todo.completed", id=completed.id, title=completed.title)
            return self.todo_result("complete", completed, ("status", "completed_at"))

        if query.action == "delete":
            todos = self.resolve_todos(query)

            if len(todos) > 1:
                deleted = tuple(
                    self.repository.delete(todo.id, correlation_id=correlation_id, trace_id=trace_id)
                    for todo in todos
                )
                deleted = tuple(todo for todo in deleted if todo is not None)
                for todo in deleted:
                    trace_event("todo.deleted", id=todo.id, title=todo.title)
                return self.todos_result("delete", deleted, ("status",))

            todo = todos[0] if todos else None
            if todo is None:
                return TodoResult(success=False, action="delete", error_code="todo_not_found")
            deleted = self.repository.delete(todo.id, correlation_id=correlation_id, trace_id=trace_id)
            trace_event("todo.deleted", id=deleted.id, title=deleted.title)
            return self.todo_result("delete", deleted, ("status",))

        if query.action == "restore":
            todo = self.resolve_todo(query)
            if todo is None:
                return TodoResult(success=False, action="restore", error_code="todo_not_found")
            restored = self.repository.restore(todo.id)
            return self.todo_result("restore", restored, ("status",))

        if query.action == "update":
            todo = self.resolve_todo(query)
            if todo is None:
                return TodoResult(success=False, action="update", error_code="todo_not_found")
            updated = self.repository.update(todo.id, title=query.title, due_at=query.due_at, priority=query.priority, correlation_id=correlation_id, trace_id=trace_id)
            return self.todo_result("update", updated, ("title", "due_at", "priority"))

        return TodoResult(success=False, action=query.action, error_code="unsupported_action")

    def resolve_todo(self, query):
        """Resolve TodoQuery to a Todo."""
        todos = self.resolve_todos(query)
        return todos[0] if todos else None

    def resolve_todos(self, query):
        """Resolve TodoQuery to one or more Todos."""
        if query.action == "delete" and query.status and not query.todo_id and not query.title:
            return tuple(self.repository.list(status=query.status))

        if query.todo_id.startswith("ordinal:"):
            index = int(query.todo_id.split(":", 1)[1]) - 1
            visible = self.ordinal_scope_todos()
            return (visible[index],) if 0 <= index < len(visible) else ()

        if query.todo_id.startswith("ordinals:"):
            visible = self.ordinal_scope_todos()
            todos = []

            for value in query.todo_id.split(":", 1)[1].split(","):
                if not value.strip().isdigit():
                    continue
                index = int(value.strip()) - 1
                if 0 <= index < len(visible):
                    todos.append(visible[index])

            return unique_todos(todos)

        if query.todo_id:
            todo = self.repository.find(query.todo_id)
            if todo is not None:
                return (todo,)

        if query.title:
            todos = self.resolve_title_group(query.title)

            if todos:
                return todos

            todo = self.repository.find_by_title(query.title)
            return (todo,) if todo is not None else ()

        todo = self.repository.first_active()
        return (todo,) if todo is not None else ()

    def ordinal_scope_todos(self):
        """Return todos used for ordinal references."""
        visible = self.repository.last_visible_todos()

        if visible:
            return visible

        return tuple(self.repository.list(status=TODO_ACTIVE))

    def resolve_title_group(self, title):
        """Resolve multiple title references in one phrase."""
        parts = split_title_group(title)

        if len(parts) <= 1:
            return ()

        todos = []

        for part in parts:
            todo = self.repository.find_by_title(part)

            if todo is not None:
                todos.append(todo)

        if len(todos) == len(parts):
            return unique_todos(todos)

        return ()

    def has_target(self, query):
        """Return whether a target exists before asking for confirmation."""
        return len(self.resolve_todos(query)) > 0

    def todo_result(self, action, todo, changed_fields):
        """Return TodoResult for one todo."""
        event_id = latest_todo_event_id(self.repository, getattr(todo, "id", ""))
        trace_event("todo.revision", id=getattr(todo, "id", ""), revision=getattr(todo, "revision", 0))
        return TodoResult(
            success=todo is not None,
            action=action,
            todo=todo,
            revision=getattr(todo, "revision", 0),
            event_id=event_id,
            trace_id=event_id,
            changed_fields=tuple(changed_fields or ()),
            error_code="" if todo is not None else "todo_not_found",
        )

    def todos_result(self, action, todos, changed_fields):
        """Return TodoResult for multiple todos."""
        items = tuple(todos or ())
        latest = items[-1] if items else None
        event_id = latest_todo_event_id(self.repository, getattr(latest, "id", ""))
        for todo in items:
            trace_event("todo.revision", id=getattr(todo, "id", ""), revision=getattr(todo, "revision", 0))
        return TodoResult(
            success=len(items) > 0,
            action=action,
            todo=latest,
            todos=items,
            revision=getattr(latest, "revision", 0),
            event_id=event_id,
            trace_id=event_id,
            changed_fields=tuple(changed_fields or ()),
            error_code="" if items else "todo_not_found",
        )

    def health(self):
        """Return health."""
        return AbilityHealth(status="ok", provider=self.repository.provider_name, message="Todo repository is ready.")


def load_todo_metadata():
    """Load Todo manifest."""
    manifest = json.loads(Path(__file__).with_name("manifest.json").read_text(encoding="utf-8"))
    return AbilityMetadata(
        id=manifest["id"],
        name=manifest["name"],
        type=AbilityType(manifest["type"]),
        permission=PermissionLevel(manifest["permission"]),
        version=manifest["version"],
        author=manifest.get("author", "Jarvis"),
        description=manifest["description"],
        capabilities=list(manifest.get("capabilities", [])),
        input_schema=dict(manifest.get("input_schema", {})),
        output_schema=manifest.get("output_schema", "TodoResult"),
        aliases=list(manifest.get("aliases", [])),
        supported_intents=list(manifest.get("supported_intents", [])),
        examples=list(manifest.get("examples", [])),
        input_prefixes=list(manifest.get("input_prefixes", [])),
        route_confidence=float(manifest.get("route_confidence", 0.75)),
    )


def create_ability(repository=None):
    """Factory."""
    return TodoAbility(repository=repository)


def latest_todo_event_id(repository, todo_id):
    """Return latest event ID for todo."""
    for event in reversed(getattr(repository, "events", []) or []):
        if getattr(event, "aggregate_id", "") == todo_id:
            return getattr(event, "event_id", "")
    return ""


def attach_runtime_fields(result, provider, correlation_id, execution_time_ms):
    """Attach runtime fields."""
    from dataclasses import replace

    return replace(result, provider=provider, correlation_id=correlation_id, execution_time_ms=int(execution_time_ms))


def extract_correlation_id(input_data):
    """Extract correlation ID."""
    if isinstance(input_data, dict):
        return str(input_data.get("correlation_id") or input_data.get("trace_id") or "")
    return ""


def extract_trace_id(input_data):
    """Extract trace ID."""
    if isinstance(input_data, dict):
        return str(input_data.get("trace_id") or "")
    return ""


def elapsed_ms(started):
    """Return elapsed milliseconds."""
    return int((perf_counter() - started) * 1000)


def split_title_group(title):
    """Split a phrase that names multiple todos."""
    value = str(title or "").strip()

    if value == "":
        return ()

    parts = re.split(r"\s*(?:랑|하고|과|와|,)\s*", value)
    parts = [part.strip() for part in parts if part.strip()]
    return tuple(parts)


def unique_todos(todos):
    """Return todos de-duplicated by ID while preserving order."""
    unique = []
    seen = set()

    for todo in todos or ():
        todo_id = getattr(todo, "id", "")

        if todo_id in seen:
            continue

        seen.add(todo_id)
        unique.append(todo)

    return tuple(unique)
