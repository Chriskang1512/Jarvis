from jarvis.commands.base import ExitCommand, HelpCommand, StatusCommand, VersionCommand
from jarvis.commands.chat import ChatCommand


class CommandRegistry:
    """Store and look up command objects by name."""

    def __init__(self):
        """Create an empty command registry."""
        self.commands = {}

    def register(self, command):
        """Register one command object."""
        self.commands[command.name] = command

    def get(self, command_name):
        """Return one command by name, or None if it does not exist."""
        return self.commands.get(command_name)

    def list(self):
        """Return all registered command objects sorted by name."""
        return [self.commands[name] for name in sorted(self.commands)]

    def exists(self, command_name):
        """Check whether a command name is registered."""
        return command_name in self.commands


def create_default_registry():
    """Create the default command registry for the CLI."""
    registry = CommandRegistry()
    registry.register(ChatCommand())
    registry.register(HelpCommand())
    registry.register(StatusCommand())
    registry.register(VersionCommand())
    registry.register(ExitCommand())
    return registry
