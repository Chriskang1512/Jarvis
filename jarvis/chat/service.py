class ChatService:
    """Conversation service that hides the concrete ChatProvider."""

    def __init__(self, provider, prompt_builder):
        """Create a chat service with injected provider and prompt builder."""
        self.provider = provider
        self.prompt_builder = prompt_builder

    def generate_reply(self, message):
        """Build a prompt and ask the provider to generate a reply."""
        prompt = self.prompt_builder.build(message)
        return self.provider.generate_reply(prompt)
