from jarvis.chat.providers import OpenAIChatProvider
from jarvis.llm.metadata import LLMProviderMetadata


class OpenAILLMProvider:
    """LLM provider adapter for OpenAI."""

    def __init__(self, model, temperature, env_path=".env"):
        """Create an OpenAI LLM provider."""
        self.provider = OpenAIChatProvider(
            model=model,
            temperature=temperature,
            env_path=env_path,
        )
        self.last_metadata = self.provider.last_metadata

    def generate(self, prompt, **options):
        """Generate one OpenAI response."""
        reply = self.provider.generate_reply(prompt, **options)
        self.last_metadata = self.provider.last_metadata
        return reply

    def generate_stream(self, prompt):
        """Yield one OpenAI response as a single chunk until streaming is added."""
        yield self.generate(prompt)

    def metadata(self):
        """Return OpenAI capability metadata."""
        return LLMProviderMetadata(
            id="openai",
            name="OpenAI",
            model=self.provider.model,
            supports_stream=False,
            supports_tools=False,
            supports_images=False,
            supports_reasoning=True,
        )

    def generate_reply(self, message, **options):
        """Backward-compatible chat provider method."""
        return self.generate(message, **options)
