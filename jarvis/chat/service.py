class ChatService:
    """Conversation service that hides the concrete ChatProvider."""

    def __init__(self, provider):
        """Create a chat service with an injected provider."""
        self.provider = provider

    def generate_reply(self, message):
        """Ask the provider to generate a reply."""
        return self.provider.generate_reply(message)

