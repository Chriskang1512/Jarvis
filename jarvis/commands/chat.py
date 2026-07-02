from jarvis.commands.base import BaseCommand
from jarvis.events.types import JarvisStatus


class ChatCommand(BaseCommand):
    """Command that asks ChatService to generate a conversation reply."""

    name = "chat"
    description = "Talk with Jarvis using the configured chat service."

    def execute(self, context):
        """Generate a chat reply through context.chat_service."""
        message = context.command_text

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

