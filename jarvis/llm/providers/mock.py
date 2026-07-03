from jarvis.chat.providers import MockChatProvider
from jarvis.llm.metadata import LLMProviderMetadata


class MockLLMProvider:
    """LLM provider adapter for the local mock provider."""

    def __init__(self):
        """Create a mock LLM provider."""
        self.provider = MockChatProvider()
        self.last_metadata = self.provider.last_metadata

    def generate(self, prompt):
        """Generate one mock response."""
        reply = self.provider.generate_reply(prompt)
        self.last_metadata = self.provider.last_metadata
        return reply

    def generate_stream(self, prompt):
        """Yield one mock response as a single chunk."""
        yield self.generate(prompt)

    def metadata(self):
        """Return mock provider capability metadata."""
        return LLMProviderMetadata(
            id="mock",
            name="Mock",
            model="mock",
            supports_stream=False,
            supports_tools=False,
            supports_images=False,
            supports_reasoning=False,
        )

    def generate_reply(self, message):
        """Backward-compatible chat provider method."""
        return self.generate(message)
