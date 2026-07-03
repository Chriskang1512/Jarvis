from dataclasses import dataclass


@dataclass
class CommandContext:
    """Share simple runtime data with command objects."""

    registry: object
    event_bus: object
    chat_service: object = None
    tool_dispatcher: object = None
    config: object = None
    command_text: str = ""
    should_exit: bool = False


class CommandDispatcher:
    """Find and execute commands from user input."""

    def __init__(self, registry, event_bus, chat_service=None, tool_dispatcher=None, config=None):
        """Create a dispatcher with a registry and EventBus."""
        self.registry = registry
        self.event_bus = event_bus
        self.context = CommandContext(
            registry=registry,
            event_bus=event_bus,
            chat_service=chat_service,
            tool_dispatcher=tool_dispatcher,
            config=config,
        )

    def dispatch(self, user_input):
        """Dispatch user input to a registered command object."""
        command_name = parse_command_name(user_input)

        if command_name == "":
            return ""

        command = self.registry.get(command_name)

        if command is None:
            command = self.registry.get("chat")
            self.context.command_text = user_input.strip()
            return command.execute(self.context)

        self.context.command_text = parse_command_text(user_input)
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


def parse_command_text(user_input):
    """Extract the text after the command name."""
    parts = user_input.strip().split(maxsplit=1)

    if len(parts) < 2:
        return ""

    return parts[1]
