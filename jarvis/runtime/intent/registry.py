from dataclasses import dataclass, field


@dataclass(frozen=True)
class IntentActionSpec:
    """Allowed ability/action combination."""

    ability: str
    action: str
    intent_id: str
    tool_name: str
    write: bool = False
    required_parameters: tuple[str, ...] = ()


@dataclass
class IntentRegistry:
    """Registry of structured intents the AI parser may emit."""

    actions: dict[str, IntentActionSpec] = field(default_factory=dict)

    def register(self, spec: IntentActionSpec):
        """Register one allowed structured intent."""
        self.actions[f"{spec.ability}.{spec.action}"] = spec

    def get(self, ability, action):
        """Return action spec for ability/action."""
        return self.actions.get(f"{ability}.{action}")

    def exists(self, ability, action):
        """Return whether ability/action is allowed."""
        return self.get(ability, action) is not None

    def list_actions(self):
        """Return all ability.action keys."""
        return tuple(sorted(self.actions))

    def list_abilities(self):
        """Return all ability names."""
        return tuple(sorted({spec.ability for spec in self.actions.values()}))


def create_default_intent_registry():
    """Create Sprint 8 structured intent registry."""
    registry = IntentRegistry()

    for action in ["query"]:
        registry.register(IntentActionSpec("weather", action, "weather.query", "weather"))

    for action in ["remember", "recall", "forget", "list"]:
        registry.register(
            IntentActionSpec(
                "memory",
                action,
                f"memory.{action}",
                "memory",
                write=action in ["remember", "forget"],
                required_parameters=("key", "value") if action == "remember" else ("key",) if action in ["recall", "forget"] else (),
            )
        )

    registry.register(IntentActionSpec("calendar", "list", "calendar.list", "calendar"))
    registry.register(
        IntentActionSpec(
            "calendar",
            "create",
            "calendar.create",
            "calendar",
            write=True,
            required_parameters=("date", "time", "title"),
        )
    )
    registry.register(IntentActionSpec("calendar", "update", "calendar.update", "calendar", write=True))
    registry.register(IntentActionSpec("calendar", "delete", "calendar.delete", "calendar", write=True, required_parameters=("title",)))

    registry.register(IntentActionSpec("contacts", "create", "contacts.create", "contacts", write=True, required_parameters=("display_name",)))
    registry.register(IntentActionSpec("contacts", "update", "contacts.update", "contacts", write=True, required_parameters=("display_name",)))
    registry.register(IntentActionSpec("contacts", "get", "contacts.get", "contacts", required_parameters=("display_name",)))
    registry.register(IntentActionSpec("contacts", "delete", "contacts.delete", "contacts", write=True, required_parameters=("display_name",)))
    registry.register(IntentActionSpec("contacts", "list", "contacts.list", "contacts"))

    registry.register(IntentActionSpec("todo", "create", "todo.create", "todo", write=True, required_parameters=("title",)))
    registry.register(IntentActionSpec("todo", "update", "todo.update", "todo", write=True))
    registry.register(IntentActionSpec("todo", "complete", "todo.complete", "todo", write=True))
    registry.register(IntentActionSpec("todo", "delete", "todo.delete", "todo", write=True))
    registry.register(IntentActionSpec("todo", "list", "todo.list", "todo"))
    registry.register(IntentActionSpec("todo", "restore", "todo.restore", "todo", write=True))

    registry.register(
        IntentActionSpec(
            "reminder",
            "create",
            "reminder.create",
            "reminder",
            write=True,
            required_parameters=("title",),
        )
    )
    registry.register(IntentActionSpec("reminder", "cancel", "reminder.cancel", "reminder", write=True))
    registry.register(IntentActionSpec("reminder", "list", "reminder.list", "reminder"))

    registry.register(IntentActionSpec("integration_n8n", "health", "integration.health", "integration_n8n"))
    registry.register(
        IntentActionSpec(
            "integration_n8n",
            "execute",
            "integration.execute",
            "integration_n8n",
            write=True,
            required_parameters=("workflow_key",),
        )
    )

    return registry
