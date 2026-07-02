from dataclasses import dataclass


@dataclass
class CommandContext:
    """Share simple runtime data with command objects."""

    registry: object
    event_bus: object
    should_exit: bool = False


class CommandDispatcher:
    """Find and execute commands from user input."""

    def __init__(self, registry, event_bus):
        """Create a dispatcher with a registry and EventBus."""
        self.registry = registry
        self.event_bus = event_bus
        self.context = CommandContext(registry=registry, event_bus=event_bus)

    def dispatch(self, user_input):
        """Dispatch user input to a registered command object."""
        command_name = parse_command_name(user_input)

        if command_name == "":
            return "Please enter a command."

        command = self.registry.get(command_name)

        if command is None:
            return f"Unknown command: {command_name}"

        return command.execute(self.context)

    def should_exit(self):
        """Return whether the console loop should stop."""
        return self.context.should_exit


def parse_command_name(user_input):
    """Extract the command name from raw user input."""
    parts = user_input.strip().split()

    if len(parts) == 0:
        return ""

    return parts[0].lower()
