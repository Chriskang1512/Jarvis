from jarvis.commands.base import BaseCommand
from jarvis.events.types import JarvisStatus
from jarvis.brain import BrainToolRouter
from jarvis.commands.tool import format_tool_output


class ChatCommand(BaseCommand):
    """Command that asks ChatService to generate a conversation reply."""

    name = "chat"
    description = "Talk with Jarvis using the configured chat service."

    def __init__(self, brain_tool_router=None):
        """Create a chat command with optional natural tool routing."""
        self.brain_tool_router = brain_tool_router or BrainToolRouter()

    def execute(self, context):
        """Generate a chat reply through context.chat_service."""
        message = context.command_text
        tool_reply = self.try_execute_brain_tool(context, message)

        if tool_reply is not None:
            return tool_reply

        self.publish_status(
            context,
            JarvisStatus.THINKING,
            "Chat provider is generating response",
        )

        reply = context.chat_service.generate_reply(message)

        self.publish_status(
            context,
            JarvisStatus.SPEAKING,
            "Chat response ready",
        )
        self.publish_status(context, JarvisStatus.SUCCESS, "Chat command completed")

        return reply

    def try_execute_brain_tool(self, context, message):
        """Execute a safe tool when Brain can identify one from plain language."""
        if context.tool_dispatcher is None:
            return None

        request = self.brain_tool_router.plan(
            message,
            registry=context.tool_dispatcher.registry,
            permission_layer=context.tool_dispatcher.permission_layer,
        )

        if request is None:
            return None

        self.publish_status(context, JarvisStatus.WORKING, f"Brain selected tool: {request.tool_name}")
        result = context.tool_dispatcher.execute(request)

        if not result.success:
            self.publish_status(context, JarvisStatus.ERROR, "Brain tool execution failed")
            return f"Tool failed: {result.error}"

        self.publish_status(context, JarvisStatus.SUCCESS, "Brain tool execution completed")
        return format_tool_output(result.output)
