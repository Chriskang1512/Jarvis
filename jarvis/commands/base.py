from jarvis.events.types import JarvisEventType, JarvisState, JarvisStatus


class BaseCommand:
    """Base class for every Jarvis command object."""

    name = ""
    description = ""

    def execute(self, context):
        """Run the command using the provided command context."""
        raise NotImplementedError("Commands must implement execute().")

    def publish_status(self, context, status, message):
        """Publish a command-specific status update."""
        state = JarvisState(status=status, message=message)
        context.event_bus.publish_state(JarvisEventType.STATUS_CHANGED, state)


class HelpCommand(BaseCommand):
    """Command that lists available commands."""

    name = "help"
    description = "Show available commands."

    def execute(self, context):
        """Return a readable list of registered command names."""
        self.publish_status(context, JarvisStatus.SUCCESS, "Help command completed")
        command_lines = ["Available Commands"]

        for command in context.registry.list():
            command_lines.append(command.name)

        return "\n".join(command_lines)


class StatusCommand(BaseCommand):
    """Command that shows the current Jarvis status."""

    name = "status"
    description = "Show current Jarvis status."

    def execute(self, context):
        """Return the current Jarvis status text."""
        state = JarvisState(status=JarvisStatus.IDLE, message="Jarvis is idle")
        self.publish_status(context, JarvisStatus.SUCCESS, "Status command completed")
        return f"Status : {state.status.value.title()}"


class VersionCommand(BaseCommand):
    """Command that shows the current Jarvis version."""

    name = "version"
    description = "Show current Jarvis version."

    def execute(self, context):
        """Return the current Sprint version."""
        self.publish_status(context, JarvisStatus.SUCCESS, "Version command completed")
        version = getattr(context.config, "version", "unknown")
        return f"Jarvis {version}"


class ExitCommand(BaseCommand):
    """Command that requests the console loop to exit."""

    name = "exit"
    description = "Exit Jarvis."

    def execute(self, context):
        """Mark the command context as finished and return a goodbye message."""
        context.should_exit = True
        self.publish_status(context, JarvisStatus.SUCCESS, "Exit command completed")
        return "Goodbye."
